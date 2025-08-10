// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC1155/ERC1155.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "@openzeppelin/contracts/utils/Strings.sol";

/**
 * @title ERC1155Token
 * @dev Multi-token standard implementation with additional features:
 * - Mintable by owner or approved minters
 * - Pausable transfers
 * - URI management per token type
 * - Supply tracking per token type
 * Gas complexity: O(1) for single operations, O(n) for batch operations
 */
contract ERC1155Token is ERC1155, Ownable, Pausable {
    using Strings for uint256;
    
    // Token name
    string public name;
    
    // Token symbol  
    string public symbol;
    
    // Mapping from token ID to token URI
    mapping(uint256 => string) private _tokenURIs;
    
    // Mapping from token ID to total supply
    mapping(uint256 => uint256) public tokenSupply;
    
    // Mapping from token ID to maximum supply (0 = unlimited)
    mapping(uint256 => uint256) public maxSupply;
    
    // Mapping of approved minters
    mapping(address => bool) public approvedMinters;
    
    // Auto-increment token ID counter
    uint256 private _currentTokenId = 0;
    
    event TokenCreated(uint256 indexed tokenId, string tokenURI, uint256 maxSupply);
    event TokenMinted(address indexed to, uint256 indexed tokenId, uint256 amount);
    event TokenBurned(address indexed from, uint256 indexed tokenId, uint256 amount);
    event MinterApproved(address indexed minter);
    event MinterRevoked(address indexed minter);
    event TokenURIUpdated(uint256 indexed tokenId, string newURI);
    
    modifier onlyMinter() {
        require(
            owner() == msg.sender || approvedMinters[msg.sender],
            "Caller is not owner or approved minter"
        );
        _;
    }
    
    constructor(
        string memory name_,
        string memory symbol_,
        string memory baseURI_
    ) ERC1155(baseURI_) {
        name = name_;
        symbol = symbol_;
    }
    
    /**
     * @dev Create a new token type
     * @param tokenURI URI for token metadata
     * @param maxSupply_ Maximum supply for this token (0 = unlimited)
     * @return tokenId The ID of the newly created token type
     */
    function createToken(string memory tokenURI, uint256 maxSupply_) 
        external 
        onlyOwner 
        returns (uint256) 
    {
        require(bytes(tokenURI).length > 0, "Token URI cannot be empty");
        
        uint256 tokenId = _getNextTokenId();
        _tokenURIs[tokenId] = tokenURI;
        maxSupply[tokenId] = maxSupply_;
        
        emit TokenCreated(tokenId, tokenURI, maxSupply_);
        return tokenId;
    }
    
    /**
     * @dev Mint tokens to specified address
     * @param to Address to mint tokens to
     * @param tokenId Token type to mint
     * @param amount Amount of tokens to mint
     * @param data Additional data to pass to recipient
     */
    function mint(
        address to,
        uint256 tokenId,
        uint256 amount,
        bytes memory data
    ) external onlyMinter whenNotPaused {
        require(to != address(0), "Cannot mint to zero address");
        require(amount > 0, "Amount must be greater than 0");
        require(_exists(tokenId), "Token type does not exist");
        
        // Check max supply constraint
        if (maxSupply[tokenId] > 0) {
            require(
                tokenSupply[tokenId] + amount <= maxSupply[tokenId],
                "Would exceed maximum supply"
            );
        }
        
        tokenSupply[tokenId] += amount;
        _mint(to, tokenId, amount, data);
        
        emit TokenMinted(to, tokenId, amount);
    }
    
    /**
     * @dev Batch mint multiple token types to an address
     * @param to Address to mint tokens to
     * @param tokenIds Array of token types to mint
     * @param amounts Array of amounts to mint for each token type
     * @param data Additional data to pass to recipient
     */
    function mintBatch(
        address to,
        uint256[] memory tokenIds,
        uint256[] memory amounts,
        bytes memory data
    ) external onlyMinter whenNotPaused {
        require(to != address(0), "Cannot mint to zero address");
        require(tokenIds.length == amounts.length, "Arrays length mismatch");
        require(tokenIds.length > 0, "Must specify at least one token");
        
        for (uint256 i = 0; i < tokenIds.length; i++) {
            require(amounts[i] > 0, "Amount must be greater than 0");
            require(_exists(tokenIds[i]), "Token type does not exist");
            
            // Check max supply constraint
            if (maxSupply[tokenIds[i]] > 0) {
                require(
                    tokenSupply[tokenIds[i]] + amounts[i] <= maxSupply[tokenIds[i]],
                    "Would exceed maximum supply"
                );
            }
            
            tokenSupply[tokenIds[i]] += amounts[i];
            emit TokenMinted(to, tokenIds[i], amounts[i]);
        }
        
        _mintBatch(to, tokenIds, amounts, data);
    }
    
    /**
     * @dev Burn tokens from caller's balance
     * @param tokenId Token type to burn
     * @param amount Amount of tokens to burn
     */
    function burn(uint256 tokenId, uint256 amount) external {
        require(balanceOf(msg.sender, tokenId) >= amount, "Insufficient balance");
        require(amount > 0, "Amount must be greater than 0");
        
        tokenSupply[tokenId] -= amount;
        _burn(msg.sender, tokenId, amount);
        
        emit TokenBurned(msg.sender, tokenId, amount);
    }
    
    /**
     * @dev Batch burn multiple token types from caller's balance
     * @param tokenIds Array of token types to burn
     * @param amounts Array of amounts to burn for each token type
     */
    function burnBatch(uint256[] memory tokenIds, uint256[] memory amounts) external {
        require(tokenIds.length == amounts.length, "Arrays length mismatch");
        require(tokenIds.length > 0, "Must specify at least one token");
        
        for (uint256 i = 0; i < tokenIds.length; i++) {
            require(balanceOf(msg.sender, tokenIds[i]) >= amounts[i], "Insufficient balance");
            require(amounts[i] > 0, "Amount must be greater than 0");
            
            tokenSupply[tokenIds[i]] -= amounts[i];
            emit TokenBurned(msg.sender, tokenIds[i], amounts[i]);
        }
        
        _burnBatch(msg.sender, tokenIds, amounts);
    }
    
    /**
     * @dev Get URI for a specific token type
     * @param tokenId Token type to query
     * @return Token URI string
     */
    function uri(uint256 tokenId) public view override returns (string memory) {
        require(_exists(tokenId), "Token type does not exist");
        
        string memory tokenURI = _tokenURIs[tokenId];
        
        // If token has specific URI, return it
        if (bytes(tokenURI).length > 0) {
            return tokenURI;
        }
        
        // Otherwise return base URI + token ID
        return string(abi.encodePacked(super.uri(tokenId), tokenId.toString()));
    }
    
    /**
     * @dev Update URI for a specific token type
     * @param tokenId Token type to update
     * @param newURI New URI for the token
     */
    function setTokenURI(uint256 tokenId, string memory newURI) external onlyOwner {
        require(_exists(tokenId), "Token type does not exist");
        
        _tokenURIs[tokenId] = newURI;
        emit TokenURIUpdated(tokenId, newURI);
        emit URI(newURI, tokenId);
    }
    
    /**
     * @dev Check if a token type exists
     * @param tokenId Token type to check
     * @return True if token type exists
     */
    function exists(uint256 tokenId) external view returns (bool) {
        return _exists(tokenId);
    }
    
    /**
     * @dev Get total supply for a token type
     * @param tokenId Token type to query
     * @return Total supply of the token type
     */
    function totalSupply(uint256 tokenId) external view returns (uint256) {
        return tokenSupply[tokenId];
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
    
    /**
     * @dev Internal function to check if token exists
     */
    function _exists(uint256 tokenId) internal view returns (bool) {
        return tokenId > 0 && tokenId <= _currentTokenId;
    }
    
    /**
     * @dev Get next available token ID
     */
    function _getNextTokenId() private returns (uint256) {
        _currentTokenId++;
        return _currentTokenId;
    }
    
    /**
     * @dev Hook that is called before any token transfer
     */
    function _beforeTokenTransfer(
        address operator,
        address from,
        address to,
        uint256[] memory ids,
        uint256[] memory amounts,
        bytes memory data
    ) internal virtual override whenNotPaused {
        super._beforeTokenTransfer(operator, from, to, ids, amounts, data);
    }
}