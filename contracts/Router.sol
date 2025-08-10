// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "./AMM.sol";

/**
 * @title Router
 * @dev Router contract for multi-hop swaps and liquidity operations
 * Features:
 * - Multi-hop token swaps
 * - Path-based routing
 * - Slippage protection
 * - Deadline protection
 * Gas complexity: O(n) for n-hop swaps
 */
contract Router is ReentrancyGuard, Ownable {
    // Mapping of token pair to AMM contract
    mapping(address => mapping(address => address)) public ammPairs;
    
    // Array of all AMM pairs for enumeration
    address[] public allPairs;
    
    event PairCreated(address indexed tokenA, address indexed tokenB, address pair, uint256 allPairsLength);
    event SwapExecuted(
        address indexed sender,
        address[] path,
        uint256[] amounts,
        address indexed to
    );
    
    modifier ensure(uint256 deadline) {
        require(deadline >= block.timestamp, "Router: EXPIRED");
        _;
    }
    
    /**
     * @dev Create a new AMM pair
     * @param tokenA First token address
     * @param tokenB Second token address
     * @return pair Address of created AMM pair
     */
    function createPair(address tokenA, address tokenB) external onlyOwner returns (address pair) {
        require(tokenA != tokenB, "Router: IDENTICAL_ADDRESSES");
        require(tokenA != address(0) && tokenB != address(0), "Router: ZERO_ADDRESS");
        require(ammPairs[tokenA][tokenB] == address(0), "Router: PAIR_EXISTS");
        
        // Sort tokens to ensure consistent pair creation
        (address token0, address token1) = tokenA < tokenB ? (tokenA, tokenB) : (tokenB, tokenA);
        
        // Create AMM pair
        AMM amm = new AMM(
            token0,
            token1,
            string(abi.encodePacked("LP-", IERC20(token0).symbol(), "-", IERC20(token1).symbol())),
            string(abi.encodePacked("LP-", IERC20(token0).symbol(), IERC20(token1).symbol()))
        );
        
        pair = address(amm);
        
        // Store pair in both directions
        ammPairs[token0][token1] = pair;
        ammPairs[token1][token0] = pair;
        allPairs.push(pair);
        
        emit PairCreated(token0, token1, pair, allPairs.length);
    }
    
    /**
     * @dev Add liquidity to a token pair
     * @param tokenA First token address
     * @param tokenB Second token address
     * @param amountADesired Desired amount of token A
     * @param amountBDesired Desired amount of token B
     * @param amountAMin Minimum amount of token A
     * @param amountBMin Minimum amount of token B
     * @param to Address to receive LP tokens
     * @param deadline Transaction deadline
     * @return amountA Actual amount of token A added
     * @return amountB Actual amount of token B added
     * @return liquidity Amount of LP tokens minted
     */
    function addLiquidity(
        address tokenA,
        address tokenB,
        uint256 amountADesired,
        uint256 amountBDesired,
        uint256 amountAMin,
        uint256 amountBMin,
        address to,
        uint256 deadline
    ) external nonReentrant ensure(deadline) returns (uint256 amountA, uint256 amountB, uint256 liquidity) {
        address pair = ammPairs[tokenA][tokenB];
        require(pair != address(0), "Router: PAIR_NOT_EXISTS");
        
        // Transfer tokens to this contract first
        IERC20(tokenA).transferFrom(msg.sender, address(this), amountADesired);
        IERC20(tokenB).transferFrom(msg.sender, address(this), amountBDesired);
        
        // Approve AMM to spend tokens
        IERC20(tokenA).approve(pair, amountADesired);
        IERC20(tokenB).approve(pair, amountBDesired);
        
        // Add liquidity through AMM
        (amountA, amountB, liquidity) = AMM(pair).addLiquidity(
            amountADesired,
            amountBDesired,
            amountAMin,
            amountBMin,
            to
        );
        
        // Refund excess tokens
        if (amountADesired > amountA) {
            IERC20(tokenA).transfer(msg.sender, amountADesired - amountA);
        }
        if (amountBDesired > amountB) {
            IERC20(tokenB).transfer(msg.sender, amountBDesired - amountB);
        }
    }
    
    /**
     * @dev Remove liquidity from a token pair
     * @param tokenA First token address
     * @param tokenB Second token address
     * @param liquidity Amount of LP tokens to burn
     * @param amountAMin Minimum amount of token A to receive
     * @param amountBMin Minimum amount of token B to receive
     * @param to Address to receive tokens
     * @param deadline Transaction deadline
     * @return amountA Amount of token A received
     * @return amountB Amount of token B received
     */
    function removeLiquidity(
        address tokenA,
        address tokenB,
        uint256 liquidity,
        uint256 amountAMin,
        uint256 amountBMin,
        address to,
        uint256 deadline
    ) external nonReentrant ensure(deadline) returns (uint256 amountA, uint256 amountB) {
        address pair = ammPairs[tokenA][tokenB];
        require(pair != address(0), "Router: PAIR_NOT_EXISTS");
        
        // Transfer LP tokens to this contract
        AMM(pair).transferFrom(msg.sender, address(this), liquidity);
        
        // Remove liquidity through AMM
        (amountA, amountB) = AMM(pair).removeLiquidity(
            liquidity,
            amountAMin,
            amountBMin,
            to
        );
    }
    
    /**
     * @dev Swap exact tokens for tokens through a path
     * @param amountIn Amount of input tokens
     * @param amountOutMin Minimum amount of output tokens
     * @param path Array of token addresses representing swap path
     * @param to Address to receive output tokens
     * @param deadline Transaction deadline
     * @return amounts Array of amounts for each step in the path
     */
    function swapExactTokensForTokens(
        uint256 amountIn,
        uint256 amountOutMin,
        address[] calldata path,
        address to,
        uint256 deadline
    ) external nonReentrant ensure(deadline) returns (uint256[] memory amounts) {
        require(path.length >= 2, "Router: INVALID_PATH");
        
        amounts = getAmountsOut(amountIn, path);
        require(amounts[amounts.length - 1] >= amountOutMin, "Router: INSUFFICIENT_OUTPUT_AMOUNT");
        
        // Transfer input tokens from sender
        IERC20(path[0]).transferFrom(msg.sender, address(this), amounts[0]);
        
        // Execute swaps
        _swapSupportingFeeOnTransferTokens(path, amounts, to);
        
        emit SwapExecuted(msg.sender, path, amounts, to);
    }
    
    /**
     * @dev Swap tokens for exact tokens through a path
     * @param amountOut Desired amount of output tokens
     * @param amountInMax Maximum amount of input tokens
     * @param path Array of token addresses representing swap path
     * @param to Address to receive output tokens
     * @param deadline Transaction deadline
     * @return amounts Array of amounts for each step in the path
     */
    function swapTokensForExactTokens(
        uint256 amountOut,
        uint256 amountInMax,
        address[] calldata path,
        address to,
        uint256 deadline
    ) external nonReentrant ensure(deadline) returns (uint256[] memory amounts) {
        require(path.length >= 2, "Router: INVALID_PATH");
        
        amounts = getAmountsIn(amountOut, path);
        require(amounts[0] <= amountInMax, "Router: EXCESSIVE_INPUT_AMOUNT");
        

### contracts/ERC721Token.sol
```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/token/ERC721/extensions/ERC721Enumerable.sol";
import "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

/**
 * @title ERC721Token  
 * @dev Standard ERC721 NFT with additional features:
 * - Enumerable (track all tokens)
 * - URI storage for metadata
 * - Mintable by owner or approved minters
 * - Pausable transfers
 * - Royalty support
 * Gas complexity: O(1) for mint/transfer, O(n) for enumeration
 */
contract ERC721Token is ERC721, ERC721Enumerable, ERC721URIStorage, Ownable, Pausable {
    using Counters for Counters.Counter;
    
    Counters.Counter private _tokenIdCounter;
    
    // Maximum number of tokens that can be minted
    uint256 public constant MAX_SUPPLY = 10000;
    
    // Mapping from token ID to royalty percentage (in basis points, e.g., 250 = 2.5%)
    mapping(uint256 => uint256) private _royalties;
    
    // Default royalty percentage for new tokens
    uint256 public defaultRoyaltyPercentage = 250; // 2.5%
    
    // Mapping of approved minters
    mapping(address => bool) public approvedMinters;
    
    event TokenMinted(address indexed to, uint256 indexed tokenId, string tokenURI);
    event RoyaltySet(uint256 indexed tokenId, uint256 percentage);
    event MinterApproved(address indexed minter);
    event MinterRevoked(address indexed minter);
    
    modifier onlyMinter() {
        require(
            owner() == msg.sender || approvedMinters[msg.sender],
            "Caller is not owner or approved minter"
        );
        _;
    }
    
    constructor(
        string memory name_,
        string memory symbol_
    ) ERC721(name_, symbol_) {
        // Start token IDs at 1
        _tokenIdCounter.increment();
    }
    
    /**
     * @dev Mint NFT to specified address with metadata URI
     * @param to Address to mint NFT to
     * @param tokenURI Metadata URI for the NFT
     * @return tokenId The ID of the newly minted token
     */
    function mintNFT(address to, string memory tokenURI) 
        external 
        onlyMinter 
        whenNotPaused 
        returns (uint256) 
    {
        require(to != address(0), "Cannot mint to zero address");
        require(totalSupply() < MAX_SUPPLY, "Maximum supply reached");
        require(bytes(tokenURI).length > 0, "Token URI cannot be empty");
        
        uint256 tokenId = _tokenIdCounter.current();
        _tokenIdCounter.increment();
        
        _safeMint(to, tokenId);
        _setTokenURI(tokenId, tokenURI);
        _royalties[tokenId] = defaultRoyaltyPercentage;
        
        emit TokenMinted(to, tokenId, tokenURI);
        return tokenId;
    }
    
    /**
     * @dev Batch mint multiple NFTs
     * @param to Address to mint NFTs to
     * @param tokenURIs Array of metadata URIs
     * @return tokenIds Array of newly minted token IDs
     */
    function batchMint(address to, string[] memory tokenURIs) 
        external 
        onlyMinter 
        whenNotPaused 
        returns (uint256[] memory) 
    {
        require(to != address(0), "Cannot mint to zero address");
        require(tokenURIs.length > 0, "Must specify at least one URI");
        require(
            totalSupply() + tokenURIs.length <= MAX_SUPPLY, 
            "Would exceed maximum supply"
        );
        
        uint256[] memory tokenIds = new uint256[](tokenURIs.length);
        
        for (uint256 i = 0; i < tokenURIs.length; i++) {
            require(bytes(tokenURIs[i]).length > 0, "Token URI cannot be empty");
            
            uint256 tokenId = _tokenIdCounter.current();
            _tokenIdCounter.increment();
            
            _safeMint(to, tokenId);
            _setTokenURI(tokenId, tokenURIs[i]);
            _royalties[tokenId] = defaultRoyaltyPercentage;
            
            tokenIds[i] = tokenId;
            emit TokenMinted(to, tokenId, tokenURIs[i]);
        }
        
        return tokenIds;
    }
    
    /**
     * @dev Set royalty percentage for a token
     * @param tokenId Token ID to set royalty for
     * @param percentage Royalty percentage in basis points (e.g., 250 = 2.5%)
     */
    function setTokenRoyalty(uint256 tokenId, uint256 percentage) 
        external 
        onlyOwner 
    {
        require(_exists(tokenId), "Token does not exist");
        require(percentage <= 1000, "Royalty cannot exceed 10%"); // Max 10%
        
        _royalties[tokenId] = percentage;
        emit RoyaltySet(tokenId, percentage);
    }
    
    /**
     * @dev Get royalty information for a token
     * @param tokenId Token ID to query
     * @param salePrice Sale price to calculate royalty for
     * @return receiver Address to receive royalty
     * @return royaltyAmount Amount of royalty to pay
     */
    function royaltyInfo(uint256 tokenId, uint256 salePrice) 
        external 
        view 
        returns (address receiver, uint256 royaltyAmount) 
    {
        require(_exists(tokenId), "Token does not exist");
        
        receiver = owner();
        royaltyAmount = (salePrice * _royalties[tokenId]) / 10000;
    }
    
    /**
     * @dev Approve an address to mint tokens
     * @param minter Address to approve as minter
     */
    function approveMinter(address minter) external onlyOwner {
        require(minter != address(0), "Cannot approve zero address");
        approvedMinters[minter] = true;
        emit MinterApproved(minter);
    }
    
    /**
     * @dev Revoke minting approval from an address
     * @param minter Address to revoke minting from
     */
    function revokeMinter(address minter) external onlyOwner {
        approvedMinters[minter] = false;
        emit MinterRevoked(minter);
    }
    
    /**
     * @dev Pause all token transfers
     */
    function pause() external onlyOwner {
        _pause();
    }
    
    /**
     * @dev Unpause token transfers
     */
    function unpause() external onlyOwner {
        _unpause();
    }
    
    // Override required functions for multiple inheritance
    
    function _beforeTokenTransfer(
        address from,
        address to,
        uint256 tokenId,
        uint256 batchSize
    ) internal override(ERC721, ERC721Enumerable) whenNotPaused {
        super._beforeTokenTransfer(from, to, tokenId, batchSize);
    }
    
    function _burn(uint256 tokenId) internal override(ERC721, ERC721URIStorage) {
        super._burn(tokenId);
        delete _royalties[tokenId];
    }
    
    function tokenURI(uint256 tokenId)
        public
        view
        override(ERC721, ERC721URIStorage)
        returns (string memory)
    {
        return super.tokenURI(tokenId);
    }
    
    function supportsInterface(bytes4 interfaceId)
        public
        view
        override(ERC721, ERC721Enumerable, ERC721URIStorage)
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }
}