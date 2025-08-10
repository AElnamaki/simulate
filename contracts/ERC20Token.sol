// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/Pausable.sol";

/**
 * @title ERC20Token
 * @dev Standard ERC20 token with additional features:
 * - Mintable by owner
 * - Pausable transfers
 * - Burnable tokens
 * Gas complexity: O(1) for all operations
 */
contract ERC20Token is ERC20, Ownable, Pausable {
    uint8 private _customDecimals;
    uint256 public constant MAX_SUPPLY = 1_000_000_000 * 10**18; // 1B tokens max
    
    event TokensMinted(address indexed to, uint256 amount);
    event TokensBurned(address indexed from, uint256 amount);
    
    /**
     * @dev Constructor sets token name, symbol, decimals and initial supply
     * @param name_ Token name
     * @param symbol_ Token symbol  
     * @param decimals_ Token decimals
     * @param initialSupply_ Initial token supply (in wei)
     */
    constructor(
        string memory name_,
        string memory symbol_,
        uint8 decimals_,
        uint256 initialSupply_
    ) ERC20(name_, symbol_) {
        require(initialSupply_ <= MAX_SUPPLY, "Initial supply exceeds maximum");
        _customDecimals = decimals_;
        _mint(msg.sender, initialSupply_);
        emit TokensMinted(msg.sender, initialSupply_);
    }
    
    /**
     * @dev Returns the number of decimals used to get user representation
     * Overrides the default ERC20 decimals (18) with custom value
     */
    function decimals() public view virtual override returns (uint8) {
        return _customDecimals;
    }
    
    /**
     * @dev Mint new tokens to specified address
     * Can only be called by owner when contract is not paused
     * @param to Address to mint tokens to
     * @param amount Amount of tokens to mint (in wei)
     */
    function mint(address to, uint256 amount) external onlyOwner whenNotPaused {
        require(to != address(0), "Cannot mint to zero address");
        require(totalSupply() + amount <= MAX_SUPPLY, "Would exceed maximum supply");
        
        _mint(to, amount);
        emit TokensMinted(to, amount);
    }
    
    /**
     * @dev Burn tokens from caller's balance
     * @param amount Amount of tokens to burn (in wei)
     */
    function burn(uint256 amount) external {
        require(balanceOf(msg.sender) >= amount, "Insufficient balance to burn");
        
        _burn(msg.sender, amount);
        emit TokensBurned(msg.sender, amount);
    }
    
    /**
     * @dev Pause all token transfers
     * Can only be called by owner
     */
    function pause() external onlyOwner {
        _pause();
    }
    
    /**
     * @dev Unpause token transfers
     * Can only be called by owner
     */
    function unpause() external onlyOwner {
        _unpause();
    }
    
    /**
     * @dev Hook that is called before any transfer of tokens
     * Prevents transfers when contract is paused
     */
    function _beforeTokenTransfer(
        address from,
        address to,
        uint256 amount
    ) internal virtual override {
        super._beforeTokenTransfer(from, to, amount);
        require(!paused(), "Token transfers are paused");
    }
}