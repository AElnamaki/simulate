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