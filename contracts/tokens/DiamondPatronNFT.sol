// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import "@openzeppelin/contracts/token/ERC721/IERC721.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "./IDiamondPatronNFT.sol";

/**
 * @title DiamondPatronNFT
 * @notice ERC-721 VIP Patron Badge ($DIAMOND) awarded to backers contributing >= 1 ETH.
 * @dev Only the authorized CrowdOpsPlatform contract can mint Diamond Patron badges.
 */
contract DiamondPatronNFT is ERC721URIStorage, Ownable, IDiamondPatronNFT {
    address public platformContract;
    uint256 private _nextTokenId;

    mapping(uint256 => uint256) public mintedAt;

    error UnauthorizedMinter(address caller);
    error ZeroAddress();
    error EmptyMetadataURI();

    event PlatformContractUpdated(address indexed oldPlatform, address indexed newPlatform);
    event DiamondBadgeMinted(
        address indexed recipient,
        uint256 indexed tokenId,
        string metadataURI,
        uint256 mintedAt
    );

    modifier onlyPlatform() {
        if (msg.sender != platformContract) {
            revert UnauthorizedMinter(msg.sender);
        }
        _;
    }

    constructor() ERC721("CrowdOps Diamond Patron", "DIAMOND") Ownable(msg.sender) {}

    /**
     * @notice Sets or updates the authorized CrowdOpsPlatform contract address.
     * @param _platformContract Address of the CrowdOpsPlatform contract.
     */
    function setPlatformContract(address _platformContract) external onlyOwner {
        if (_platformContract == address(0)) revert ZeroAddress();
        address oldPlatform = platformContract;
        platformContract = _platformContract;
        emit PlatformContractUpdated(oldPlatform, _platformContract);
    }

    /**
     * @notice Mints a Diamond Patron NFT badge to a qualifying backer.
     * @param recipient Backer address receiving the badge.
     * @param metadataURI IPFS CID or URI pointing to the badge JSON metadata.
     * @return tokenId Newly minted NFT token ID.
     */
    function mintDiamondBadge(address recipient, string calldata metadataURI)
        external
        override
        onlyPlatform
        returns (uint256 tokenId)
    {
        if (recipient == address(0)) revert ZeroAddress();
        if (bytes(metadataURI).length == 0) revert EmptyMetadataURI();

        _nextTokenId++;
        tokenId = _nextTokenId;

        _safeMint(recipient, tokenId);
        _setTokenURI(tokenId, metadataURI);
        mintedAt[tokenId] = block.timestamp;

        emit DiamondBadgeMinted(recipient, tokenId, metadataURI, block.timestamp);
    }

    /**
     * @notice Returns the total number of Diamond Patron badges minted so far.
     */
    function totalSupply() external view returns (uint256) {
        return _nextTokenId;
    }

    /**
     * @notice Verifies whether an address holds at least one Diamond Patron NFT.
     * @param account Address to check.
     */
    function verifyDiamondPatron(address account) external view returns (bool) {
        return balanceOf(account) > 0;
    }

    /// @inheritdoc IDiamondPatronNFT
    function balanceOf(address owner)
        public
        view
        override(ERC721, IERC721, IDiamondPatronNFT)
        returns (uint256)
    {
        return super.balanceOf(owner);
    }

    /// @inheritdoc IDiamondPatronNFT
    function ownerOf(uint256 tokenId)
        public
        view
        override(ERC721, IERC721, IDiamondPatronNFT)
        returns (address)
    {
        return super.ownerOf(tokenId);
    }
}
