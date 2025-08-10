// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/Pausable.sol";

/**
 * @title AMM (Automated Market Maker)
 * @dev Constant Product AMM implementation (x * y = k)
 * Features:
 * - Add/remove liquidity
 * - Token swaps with slippage protection
 * - LP token rewards
 * - Configurable fees
 * - Flash loan protection
 * Gas complexity: O(1) for all operations
 */
contract AMM is ERC20, ReentrancyGuard, Ownable, Pausable {
    IERC20 public immutable tokenA;
    IERC20 public immutable tokenB;
    
    // Reserves
    uint256 public reserveA;
    uint256 public reserveB;
    
    // Fee configuration (in basis points, e.g., 30 = 0.3%)
    uint256 public fee = 30; // 0.3% default fee
    uint256 public constant MAX_FEE = 1000; // 10% maximum fee
    
    // Minimum liquidity to prevent division by zero
    uint256 public constant MINIMUM_LIQUIDITY = 10**3;
    
    // Protocol fee (portion of trading fees sent to protocol)
    uint256 public protocolFeeBps = 0; // 0% initially
    address public protocolFeeRecipient;
    
    // Flash loan protection
    uint256 private _unlocked = 1;
    
    // Events
    event Swap(
        address indexed sender,
        address indexed tokenIn,
        address indexed tokenOut,
        uint256 amountIn,
        uint256 amountOut,
        address to
    );
    
    event LiquidityAdded(
        address indexed provider,
        uint256 amountA,
        uint256 amountB,
        uint256 liquidity
    );
    
    event LiquidityRemoved(
        address indexed provider,
        uint256 amountA,
        uint256 amountB,
        uint256 liquidity
    );
    
    event FeeUpdated(uint256 oldFee, uint256 newFee);
    event ProtocolFeeUpdated(uint256 oldFee, uint256 newFee, address recipient);
    event ReservesUpdated(uint256 reserveA, uint256 reserveB);
    
    modifier lock() {
        require(_unlocked == 1, "AMM: LOCKED");
        _unlocked = 0;
        _;
        _unlocked = 1;
    }
    
    /**
     * @dev Constructor initializes the AMM pair
     * @param _tokenA First token in the pair
     * @param _tokenB Second token in the pair
     * @param _name LP token name
     * @param _symbol LP token symbol
     */
    constructor(
        address _tokenA,
        address _tokenB,
        string memory _name,
        string memory _symbol
    ) ERC20(_name, _symbol) {
        require(_tokenA != _tokenB, "AMM: IDENTICAL_ADDRESSES");
        require(_tokenA != address(0) && _tokenB != address(0), "AMM: ZERO_ADDRESS");
        
        tokenA = IERC20(_tokenA);
        tokenB = IERC20(_tokenB);
    }
    
    /**
     * @dev Add liquidity to the pool
     * @param amountADesired Desired amount of token A to add
     * @param amountBDesired Desired amount of token B to add
     * @param amountAMin Minimum amount of token A to add (slippage protection)
     * @param amountBMin Minimum amount of token B to add (slippage protection)
     * @param to Address to receive LP tokens
     * @return amountA Actual amount of token A added
     * @return amountB Actual amount of token B added
     * @return liquidity Amount of LP tokens minted
     */
    function addLiquidity(
        uint256 amountADesired,
        uint256 amountBDesired,
        uint256 amountAMin,
        uint256 amountBMin,
        address to
    ) external nonReentrant whenNotPaused returns (uint256 amountA, uint256 amountB, uint256 liquidity) {
        require(to != address(0), "AMM: ZERO_ADDRESS");
        
        // Calculate optimal amounts
        (amountA, amountB) = _calculateLiquidityAmounts(
            amountADesired,
            amountBDesired,
            amountAMin,
            amountBMin
        );
        
        // Transfer tokens from user
        tokenA.transferFrom(msg.sender, address(this), amountA);
        tokenB.transferFrom(msg.sender, address(this), amountB);
        
        // Calculate liquidity tokens to mint
        uint256 totalSupply = totalSupply();
        if (totalSupply == 0) {
            // First liquidity provision
            liquidity = _sqrt(amountA * amountB) - MINIMUM_LIQUIDITY;
            _mint(address(0xdead), MINIMUM_LIQUIDITY); // Lock minimum liquidity
        } else {
            // Subsequent liquidity provisions
            liquidity = _min(
                (amountA * totalSupply) / reserveA,
                (amountB * totalSupply) / reserveB
            );
        }
        
        require(liquidity > 0, "AMM: INSUFFICIENT_LIQUIDITY_MINTED");
        
        // Mint LP tokens
        _mint(to, liquidity);
        
        // Update reserves
        _updateReserves();
        
        emit LiquidityAdded(to, amountA, amountB, liquidity);
    }
    
    /**
     * @dev Remove liquidity from the pool
     * @param liquidity Amount of LP tokens to burn
     * @param amountAMin Minimum amount of token A to receive
     * @param amountBMin Minimum amount of token B to receive
     * @param to Address to receive tokens
     * @return amountA Amount of token A received
     * @return amountB Amount of token B received
     */
    function removeLiquidity(
        uint256 liquidity,
        uint256 amountAMin,
        uint256 amountBMin,
        address to
    ) external nonReentrant whenNotPaused returns (uint256 amountA, uint256 amountB) {
        require(to != address(0), "AMM: ZERO_ADDRESS");
        require(liquidity > 0, "AMM: INSUFFICIENT_LIQUIDITY");
        
        uint256 totalSupply = totalSupply();
        require(totalSupply > 0, "AMM: NO_LIQUIDITY");
        
        // Calculate token amounts to return
        amountA = (liquidity * reserveA) / totalSupply;
        amountB = (liquidity * reserveB) / totalSupply;
        
        require(amountA >= amountAMin, "AMM: INSUFFICIENT_A_AMOUNT");
        require(amountB >= amountBMin, "AMM: INSUFFICIENT_B_AMOUNT");
        
        // Burn LP tokens
        _burn(msg.sender, liquidity);
        
        // Transfer tokens to user
        tokenA.transfer(to, amountA);
        tokenB.transfer(to, amountB);
        
        // Update reserves
        _updateReserves();
        
        emit LiquidityRemoved(to, amountA, amountB, liquidity);
    }
    
    /**
     * @dev Swap exact amount of input tokens for output tokens
     * @param amountIn Amount of input tokens
     * @param amountOutMin Minimum amount of output tokens (slippage protection)
     * @param tokenIn Address of input token
     * @param to Address to receive output tokens
     * @return amountOut Amount of output tokens received
     */
    function swapExactTokensForTokens(
        uint256 amountIn,
        uint256 amountOutMin,
        address tokenIn,
        address to
    ) external nonReentrant lock whenNotPaused returns (uint256 amountOut) {
        require(to != address(0), "AMM: ZERO_ADDRESS");
        require(amountIn > 0, "AMM: INSUFFICIENT_INPUT_AMOUNT");
        require(
            tokenIn == address(tokenA) || tokenIn == address(tokenB),
            "AMM: INVALID_TOKEN"
        );
        
        bool isTokenA = tokenIn == address(tokenA);
        IERC20 inputToken = isTokenA ? tokenA : tokenB;
        IERC20 outputToken = isTokenA ? tokenB : tokenA;
        uint256 inputReserve = isTokenA ? reserveA : reserveB;
        uint256 outputReserve = isTokenA ? reserveB : reserveA;
        
        // Transfer input tokens from user
        inputToken.transferFrom(msg.sender, address(this), amountIn);
        
        // Calculate output amount (with fee)
        amountOut = _getAmountOut(amountIn, inputReserve, outputReserve);
        require(amountOut >= amountOutMin, "AMM: INSUFFICIENT_OUTPUT_AMOUNT");
        require(amountOut < outputReserve, "AMM: INSUFFICIENT_LIQUIDITY");
        
        // Transfer output tokens to user
        outputToken.transfer(to, amountOut);
        
        // Update reserves
        _updateReserves();
        
        emit Swap(msg.sender, tokenIn, address(outputToken), amountIn, amountOut, to);
    }
    
    /**
     * @dev Get amount of output tokens for given input
     * @param amountIn Amount of input tokens
     * @param reserveIn Input token reserve
     * @param reserveOut Output token reserve
     * @return amountOut Amount of output tokens
     */
    function getAmountOut(uint256 amountIn, uint256 reserveIn, uint256 reserveOut) 
        external 
        view 
        returns (uint256 amountOut) 
    {
        return _getAmountOut(amountIn, reserveIn, reserveOut);
    }
    
    /**
     * @dev Get amount of input tokens needed for desired output
     * @param amountOut Desired amount of output tokens
     * @param reserveIn Input token reserve
     * @param reserveOut Output token reserve
     * @return amountIn Required amount of input tokens
     */
    function getAmountIn(uint256 amountOut, uint256 reserveIn, uint256 reserveOut) 
        external 
        view 
        returns (uint256 amountIn) 
    {
        require(amountOut > 0, "AMM: INSUFFICIENT_OUTPUT_AMOUNT");
        require(reserveIn > 0 && reserveOut > 0, "AMM: INSUFFICIENT_LIQUIDITY");
        require(amountOut < reserveOut, "AMM: INSUFFICIENT_LIQUIDITY");
        
        uint256 numerator = reserveIn * amountOut * 10000;
        uint256 denominator = (reserveOut - amountOut) * (10000 - fee);
        amountIn = (numerator / denominator) + 1;
    }
    
    /**
     * @dev Set trading fee (only owner)
     * @param _fee New fee in basis points
     */
    function setFee(uint256 _fee) external onlyOwner {
        require(_fee <= MAX_FEE, "AMM: FEE_TOO_HIGH");
        uint256 oldFee = fee;
        fee = _fee;
        emit FeeUpdated(oldFee, _fee);
    }
    
    /**
     * @dev Set protocol fee configuration (only owner)
     * @param _protocolFeeBps Protocol fee in basis points (portion of trading fees)
     * @param _protocolFeeRecipient Address to receive protocol fees
     */
    function setProtocolFee(uint256 _protocolFeeBps, address _protocolFeeRecipient) 
        external 
        onlyOwner 
    {
        require(_protocolFeeBps <= 2000, "AMM: PROTOCOL_FEE_TOO_HIGH"); // Max 20%
        require(_protocolFeeRecipient != address(0), "AMM: ZERO_ADDRESS");
        
        uint256 oldFee = protocolFeeBps;
        protocolFeeBps = _protocolFeeBps;
        protocolFeeRecipient = _protocolFeeRecipient;
        
        emit ProtocolFeeUpdated(oldFee, _protocolFeeBps, _protocolFeeRecipient);
    }
    
    /**
     * @dev Emergency pause (only owner)
     */
    function pause() external onlyOwner {
        _pause();
    }
    
    /**
     * @dev Unpause (only owner)
     */
    function unpause() external onlyOwner {
        _unpause();
    }
    
    /**
     * @dev Get current reserves
     * @return _reserveA Current reserve of token A
     * @return _reserveB Current reserve of token B
     */
    function getReserves() external view returns (uint256 _reserveA, uint256 _reserveB) {
        _reserveA = reserveA;
        _reserveB = reserveB;
    }
    
    // Internal functions
    
    /**
     * @dev Calculate optimal liquidity amounts
     */
    function _calculateLiquidityAmounts(
        uint256 amountADesired,
        uint256 amountBDesired,
        uint256 amountAMin,
        uint256 amountBMin
    ) internal view returns (uint256 amountA, uint256 amountB) {
        if (reserveA == 0 && reserveB == 0) {
            // First liquidity provision - use desired amounts
            (amountA, amountB) = (amountADesired, amountBDesired);
        } else {
            // Calculate optimal amount B for given amount A
            uint256 amountBOptimal = (amountADesired * reserveB) / reserveA;
            if (amountBOptimal <= amountBDesired) {
                require(amountBOptimal >= amountBMin, "AMM: INSUFFICIENT_B_AMOUNT");
                (amountA, amountB) = (amountADesired, amountBOptimal);
            } else {
                // Calculate optimal amount A for given amount B
                uint256 amountAOptimal = (amountBDesired * reserveA) / reserveB;
                require(amountAOptimal <= amountADesired && amountAOptimal >= amountAMin, 
                    "AMM: INSUFFICIENT_A_AMOUNT");
                (amountA, amountB) = (amountAOptimal, amountBDesired);
            }
        }
    }
    
    /**
     * @dev Internal function to calculate output amount
     */
    function _getAmountOut(uint256 amountIn, uint256 reserveIn, uint256 reserveOut) 
        internal 
        view 
        returns (uint256 amountOut) 
    {
        require(amountIn > 0, "AMM: INSUFFICIENT_INPUT_AMOUNT");
        require(reserveIn > 0 && reserveOut > 0, "AMM: INSUFFICIENT_LIQUIDITY");
        
        uint256 amountInWithFee = amountIn * (10000 - fee);
        uint256 numerator = amountInWithFee * reserveOut;
        uint256 denominator = (reserveIn * 10000) + amountInWithFee;
        amountOut = numerator / denominator;
    }
    
    /**
     * @dev Update reserves to current token balances
     */
    function _updateReserves() internal {
        reserveA = tokenA.balanceOf(address(this));
        reserveB = tokenB.balanceOf(address(this));
        emit ReservesUpdated(reserveA, reserveB);
    }
    
    /**
     * @dev Square root function (Babylonian method)
     */
    function _sqrt(uint256 y) internal pure returns (uint256 z) {
        if (y > 3) {
            z = y;
            uint256 x = y / 2 + 1;
            while (x < z) {
                z = x;
                x = (y / x + x) / 2;
            }
        } else if (y != 0) {
            z = 1;
        }
    }
    
    /**
     * @dev Return minimum of two numbers
     */
    function _min(uint256 a, uint256 b) internal pure returns (uint256) {
        return a < b ? a : b;
    }
}