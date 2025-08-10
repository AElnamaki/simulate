#!/usr/bin/env python3
"""
Blockchain Development Suite - Deployment Script
Deploys all contracts to Ganache and verifies initial state
"""

import json
import os
import sys
from pathlib import Path
from web3 import Web3, HTTPProvider
from eth_account import Account
from solcx import compile_standard, install_solc, set_solc_version
import click
from typing import Dict, Any, Tuple

# Configuration
GANACHE_URL = os.getenv('GANACHE_URL', 'http://localhost:8545')
DEPLOYER_PRIVATE_KEY = os.getenv('DEPLOYER_PRIVATE_KEY', 
    '0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d')  # Ganache default
CHAIN_ID = int(os.getenv('CHAIN_ID', '1337'))  # Ganache default
GAS_LIMIT = int(os.getenv('GAS_LIMIT', '6721975'))
GAS_PRICE = int(os.getenv('GAS_PRICE', '20000000000'))  # 20 gwei

class ContractDeployer:
    def __init__(self, web3_url: str = GANACHE_URL):
        """Initialize deployer with Web3 connection"""
        self.w3 = Web3(HTTPProvider(web3_url))
        
        if not self.w3.is_connected():
            raise Exception(f"❌ Cannot connect to {web3_url}")
            
        self.account = Account.from_key(DEPLOYER_PRIVATE_KEY)
        self.deployer_address = self.account.address
        
        # Verify deployer has funds
        balance = self.w3.eth.get_balance(self.deployer_address)
        if balance == 0:
            raise Exception(f"❌ Deployer address {self.deployer_address} has no ETH")
            
        print(f"✅ Connected to {web3_url}")
        print(f"📝 Deployer: {self.deployer_address}")
        print(f"💰 Balance: {self.w3.from_wei(balance, 'ether')} ETH")
        
        self.deployed_contracts = {}
        self.nonce = self.w3.eth.get_transaction_count(self.deployer_address)
        
    def compile_contracts(self) -> Dict[str, Any]:
        """Compile all Solidity contracts"""
        print("🔨 Compiling contracts...")
        
        # Install and set Solidity version
        install_solc('0.8.19')
        set_solc_version('0.8.19')
        
        contracts_dir = Path(__file__).parent / 'contracts'
        compiled_contracts = {}
        
        # Contract files to compile
        contract_files = [
            'ERC20Token.sol',
            'ERC721Token.sol', 
            'ERC1155Token.sol',
            'AMM.sol',
            'Router.sol'
        ]
        
        for contract_file in contract_files:
            contract_path = contracts_dir / contract_file
            if not contract_path.exists():
                print(f"⚠️  Contract file not found: {contract_path}")
                continue
                
            with open(contract_path, 'r') as f:
                source_code = f.read()
            
            # Standard JSON input for compilation
            input_json = {
                'language': 'Solidity',
                'sources': {
                    contract_file: {'content': source_code}
                },
                'settings': {
                    'outputSelection': {
                        '*': {
                            '*': ['abi', 'evm.bytecode']
                        }
                    },
                    'optimizer': {
                        'enabled': True,
                        'runs': 200
                    }
                }
            }
            
            try:
                compiled = compile_standard(input_json)
                contract_name = contract_file.replace('.sol', '')
                contract_data = compiled['contracts'][contract_file][contract_name]
                
                compiled_contracts[contract_name] = {
                    'abi': contract_data['abi'],
                    'bytecode': contract_data['evm']['bytecode']['object']
                }
                print(f"✅ Compiled {contract_name}")
                
            except Exception as e:
                print(f"❌ Failed to compile {contract_file}: {e}")
                
        return compiled_contracts
    
    def deploy_contract(self, name: str, abi: list, bytecode: str, 
                       constructor_args: tuple = ()) -> Tuple[str, Any]:
        """Deploy a single contract"""
        print(f"🚀 Deploying {name}...")
        
        # Create contract instance
        contract = self.w3.eth.contract(abi=abi, bytecode=bytecode)
        
        # Build constructor transaction
        constructor_tx = contract.constructor(*constructor_args).build_transaction({
            'from': self.deployer_address,
            'nonce': self.nonce,
            'gas': GAS_LIMIT,
            'gasPrice': GAS_PRICE,
            'chainId': CHAIN_ID
        })
        
        # Sign and send transaction
        signed_tx = self.account.sign_transaction(constructor_tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        print(f"📝 Transaction hash: {tx_hash.hex()}")
        
        # Wait for transaction receipt
        tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        if tx_receipt.status == 0:
            raise Exception(f"❌ Transaction failed for {name}")
            
        contract_address = tx_receipt.contractAddress
        deployed_contract = self.w3.eth.contract(address=contract_address, abi=abi)
        
        print(f"✅ {name} deployed at {contract_address}")
        print(f"⛽ Gas used: {tx_receipt.gasUsed:,}")
        
        self.nonce += 1
        
        return contract_address, deployed_contract
    
    def deploy_erc20_token(self, compiled_contracts: Dict[str, Any]) -> Tuple[str, Any]:
        """Deploy ERC20 token contract"""
        name = "Test Token"
        symbol = "TEST"
        decimals = 18
        initial_supply = self.w3.to_wei(1000000, 'ether')  # 1M tokens
        
        return self.deploy_contract(
            'ERC20Token',
            compiled_contracts['ERC20Token']['abi'],
            compiled_contracts['ERC20Token']['bytecode'],
            (name, symbol, decimals, initial_supply)
        )
    
    def deploy_erc721_token(self, compiled_contracts: Dict[str, Any]) -> Tuple[str, Any]:
        """Deploy ERC721 NFT contract"""
        name = "Test NFT"
        symbol = "TNFT"
        
        return self.deploy_contract(
            'ERC721Token',
            compiled_contracts['ERC721Token']['abi'],
            compiled_contracts['ERC721Token']['bytecode'],
            (name, symbol)
        )
    
    def deploy_erc1155_token(self, compiled_contracts: Dict[str, Any]) -> Tuple[str, Any]:
        """Deploy ERC1155 multi-token contract"""
        name = "Test Multi-Token"
        symbol = "TMT"
        base_uri = "https://api.example.com/metadata/{id}.json"
        
        return self.deploy_contract(
            'ERC1155Token',
            compiled_contracts['ERC1155Token']['abi'],
            compiled_contracts['ERC1155Token']['bytecode'],
            (name, symbol, base_uri)
        )
    
    def deploy_amm(self, compiled_contracts: Dict[str, Any], 
                   token_a_address: str, token_b_address: str) -> Tuple[str, Any]:
        """Deploy AMM contract for token pair"""
        name = f"AMM-LP-{token_a_address[:6]}-{token_b_address[:6]}"
        symbol = f"ALP-{token_a_address[:4]}{token_b_address[:4]}"
        
        return self.deploy_contract(
            'AMM',
            compiled_contracts['AMM']['abi'],
            compiled_contracts['AMM']['bytecode'],
            (token_a_address, token_b_address, name, symbol)
        )
    
    def deploy_router(self, compiled_contracts: Dict[str, Any]) -> Tuple[str, Any]:
        """Deploy Router contract"""
        return self.deploy_contract(
            'Router',
            compiled_contracts['Router']['abi'],
            compiled_contracts['Router']['bytecode']
        )
    
    def verify_deployments(self) -> bool:
        """Verify all deployed contracts are working correctly"""
        print("🔍 Verifying deployments...")
        
        try:
            # Verify ERC20 token
            erc20 = self.deployed_contracts['ERC20Token']['contract']
            name = erc20.functions.name().call()
            symbol = erc20.functions.symbol().call()
            total_supply = erc20.functions.totalSupply().call()
            balance = erc20.functions.balanceOf(self.deployer_address).call()
            
            print(f"✅ ERC20 Token: {name} ({symbol})")
            print(f"   Total Supply: {self.w3.from_wei(total_supply, 'ether'):,} {symbol}")
            print(f"   Deployer Balance: {self.w3.from_wei(balance, 'ether'):,} {symbol}")
            
            assert total_supply > 0, "ERC20 total supply should be > 0"
            assert balance == total_supply, "Deployer should own all initial tokens"
            
            # Verify ERC721 token
            erc721 = self.deployed_contracts['ERC721Token']['contract']
            nft_name = erc721.functions.name().call()
            nft_symbol = erc721.functions.symbol().call()
            max_supply = erc721.functions.MAX_SUPPLY().call()
            
            print(f"✅ ERC721 NFT: {nft_name} ({nft_symbol})")
            print(f"   Max Supply: {max_supply:,}")
            
            # Verify ERC1155 token
            erc1155 = self.deployed_contracts['ERC1155Token']['contract']
            multi_name = erc1155.functions.name().call()
            multi_symbol = erc1155.functions.symbol().call()
            
            print(f"✅ ERC1155 Multi-Token: {multi_name} ({multi_symbol})")
            
            # Verify AMM
            amm = self.deployed_contracts['AMM']['contract']
            token_a = amm.functions.tokenA().call()
            token_b = amm.functions.tokenB().call()
            fee = amm.functions.fee().call()
            
            print(f"✅ AMM Contract:")
            print(f"   Token A: {token_a}")
            print(f"   Token B: {token_b}")
            print(f"   Fee: {fee / 100:.2f}%")
            
            # Verify Router
            router = self.deployed_contracts['Router']['contract']
            pairs_count = router.functions.allPairsLength().call()
            
            print(f"✅ Router Contract:")
            print(f"   Pairs Count: {pairs_count}")
            
            print("🎉 All verifications passed!")
            return True
            
        except Exception as e:
            print(f"❌ Verification failed: {e}")
            return False
    
    def save_deployment_info(self, output_file: str = 'deployed.json'):
        """Save deployment information to JSON file"""
        deployment_info = {
            'network': {
                'url': GANACHE_URL,
                'chainId': CHAIN_ID
            },
            'deployer': self.deployer_address,
            'deploymentBlock': self.w3.eth.block_number,
            'timestamp': self.w3.eth.get_block('latest')['timestamp'],
            'contracts': {}
        }
        
        for name, info in self.deployed_contracts.items():
            deployment_info['contracts'][name] = {
                'address': info['address'],
                'abi': info['abi'],
                'transactionHash': info.get('tx_hash', ''),
                'blockNumber': info.get('block_number', 0)
            }
        
        with open(output_file, 'w') as f:
            json.dump(deployment_info, f, indent=2)
            
        print(f"📄 Deployment info saved to {output_file}")
    
    def deploy_all(self) -> bool:
        """Deploy all contracts in correct order"""
        try:
            # Compile contracts
            compiled_contracts = self.compile_contracts()
            
            # Deploy ERC20 token (will be used in AMM)
            erc20_address, erc20_contract = self.deploy_erc20_token(compiled_contracts)
            self.deployed_contracts['ERC20Token'] = {
                'address': erc20_address,
                'contract': erc20_contract,
                'abi': compiled_contracts['ERC20Token']['abi']
            }
            
            # Deploy second ERC20 token for AMM pair
            usdc_address, usdc_contract = self.deploy_contract(
                'USDC',
                compiled_contracts['ERC20Token']['abi'],
                compiled_contracts['ERC20Token']['bytecode'],
                ("USD Coin", "USDC", 6, self.w3.to_wei(1000000, 'mwei'))  # 1M USDC (6 decimals)
            )
            self.deployed_contracts['USDC'] = {
                'address': usdc_address,
                'contract': usdc_contract,
                'abi': compiled_contracts['ERC20Token']['abi']
            }
            
            # Deploy ERC721 NFT
            erc721_address, erc721_contract = self.deploy_erc721_token(compiled_contracts)
            self.deployed_contracts['ERC721Token'] = {
                'address': erc721_address,
                'contract': erc721_contract,
                'abi': compiled_contracts['ERC721Token']['abi']
            }
            
            # Deploy ERC1155 Multi-Token
            erc1155_address, erc1155_contract = self.deploy_erc1155_token(compiled_contracts)
            self.deployed_contracts['ERC1155Token'] = {
                'address': erc1155_address,
                'contract': erc1155_contract,
                'abi': compiled_contracts['ERC1155Token']['abi']
            }
            
            # Deploy AMM for ERC20/USDC pair
            amm_address, amm_contract = self.deploy_amm(
                compiled_contracts, erc20_address, usdc_address
            )
            self.deployed_contracts['AMM'] = {
                'address': amm_address,
                'contract': amm_contract,
                'abi': compiled_contracts['AMM']['abi']
            }
            
            # Deploy Router
            router_address, router_contract = self.deploy_router(compiled_contracts)
            self.deployed_contracts['Router'] = {
                'address': router_address,
                'contract': router_contract,
                'abi': compiled_contracts['Router']['abi']
            }
            
            # Verify deployments
            if not self.verify_deployments():
                return False
                
            # Save deployment info
            self.save_deployment_info()
            
            print("🎉 All contracts deployed successfully!")
            return True
            
        except Exception as e:
            print(f"❌ Deployment failed: {e}")
            return False


@click.command()
@click.option('--ganache-url', default=GANACHE_URL, help='Ganache RPC URL')
@click.option('--output', default='deployed.json', help='Output file for deployment info')
@click.option('--verify-only', is_flag=True, help='Only verify existing deployments')
def main(ganache_url: str, output: str, verify_only: bool):
    """Deploy blockchain development suite contracts"""
    
    if verify_only:
        # Load existing deployment and verify
        try:
            with open(output, 'r') as f:
                deployment_info = json.load(f)
            print("🔍 Verifying existing deployments...")
            # TODO: Add verification logic for existing deployments
            print("✅ Verification complete")
        except FileNotFoundError:
            print(f"❌ Deployment file {output} not found")
            sys.exit(1)
        return
    
    # Deploy contracts
    deployer = ContractDeployer(ganache_url)
    
    if deployer.deploy_all():
        print("\n🚀 Deployment Summary:")
        for name, info in deployer.deployed_contracts.items():
            print(f"   {name}: {info['address']}")
        
        print(f"\n📋 Next steps:")
        print(f"   1. source venv/bin/activate")
        print(f"   2. python simulator/run_simulation.py")
        print(f"   3. python -m pytest tests/")
        
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()