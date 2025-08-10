#!/usr/bin/env python3
"""
Test deployment functionality
"""

import pytest
import json
import subprocess
import time
from pathlib import Path
from web3 import Web3
from deploy import ContractDeployer

class TestDeployment:
    """Test contract deployment"""
    
    @pytest.fixture(scope="class")
    def ganache_process(self):
        """Start Ganache for testing"""
        # Start Ganache
        process = subprocess.Popen([
            'ganache-cli',
            '--host', '0.0.0.0',
            '--port', '8545',
            '--deterministic',
            '--accounts', '10',
            '--defaultBalanceEther', '1000'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Wait for Ganache to be ready
        time.sleep(3)
        
        yield process
        
        # Cleanup
        process.terminate()
        process.wait()
    
    @pytest.fixture
    def deployer(self, ganache_process):
        """Create deployer instance"""
        return ContractDeployer('http://localhost:8545')
    
    def test_web3_connection(self, deployer):
        """Test Web3 connection to Ganache"""
        assert deployer.w3.is_connected()
        assert deployer.w3.eth.block_number >= 0
    
    def test_compile_contracts(self, deployer):
        """Test contract compilation"""
        compiled_contracts = deployer.compile_contracts()
        
        expected_contracts = [
            'ERC20Token', 'ERC721Token', 'ERC1155Token', 
            'AMM', 'Router'
        ]
        
        for contract_name in expected_contracts:
            assert contract_name in compiled_contracts
            assert 'abi' in compiled_contracts[contract_name]
            assert 'bytecode' in compiled_contracts[contract_name]
            assert len(compiled_contracts[contract_name]['bytecode']) > 0
    
    def test_deploy_erc20_token(self, deployer):
        """Test ERC20 token deployment"""
        compiled_contracts = deployer.compile_contracts()
        
        address, contract = deployer.deploy_erc20_token(compiled_contracts)
        
        # Verify deployment
        assert Web3.is_address(address)
        assert contract.functions.name().call() == "Test Token"
        assert contract.functions.symbol().call() == "TEST"
        assert contract.functions.decimals().call() == 18
        assert contract.functions.totalSupply().call() > 0
    
    def test_deploy_amm(self, deployer):
        """Test AMM deployment"""
        compiled_contracts = deployer.compile_contracts()
        
        # Deploy tokens first
        token_a_address, _ = deployer.deploy_erc20_token(compiled_contracts)
        token_b_address, _ = deployer.deploy_contract(
            'USDC',
            compiled_contracts['ERC20Token']['abi'],
            compiled_contracts['ERC20Token']['bytecode'],
            ("USD Coin", "USDC", 6, deployer.w3.to_wei(1000000, 'mwei'))
        )
        
        # Deploy AMM
        amm_address, amm_contract = deployer.deploy_amm(
            compiled_contracts, token_a_address, token_b_address
        )
        
        # Verify AMM deployment
        assert Web3.is_address(amm_address)
        assert amm_contract.functions.tokenA().call() == token_a_address
        assert amm_contract.functions.tokenB().call() == token_b_address
        assert amm_contract.functions.fee().call() == 30  # Default 0.3%
    
    def test_full_deployment(self, deployer):
        """Test complete deployment process"""
        success = deployer.deploy_all()
        assert success
        
        # Verify deployed.json is created
        assert Path('deployed.json').exists()
        
        # Load and verify deployment info
        with open('deployed.json', 'r') as f:
            deployment_info = json.load(f)
        
        assert 'contracts' in deployment_info
        assert 'ERC20Token' in deployment_info['contracts']
        assert 'AMM' in deployment_info['contracts']
        assert 'Router' in deployment_info['contracts']
        
        # Verify contract addresses are valid
        for contract_name, contract_info in deployment_info['contracts'].items():
            assert Web3.is_address(contract_info['address'])
            assert len(contract_info['abi']) > 0