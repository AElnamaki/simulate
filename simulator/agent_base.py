#!/usr/bin/env python3
"""
Base Agent Class for Blockchain Simulation
Provides common functionality for all trading agents
"""

import random
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from web3 import Web3
from eth_account import Account
import json
import logging

logger = logging.getLogger(__name__)

class AgentBase(ABC):
    """
    Base class for all simulation agents
    Provides wallet management, transaction handling, and common utilities
    """
    
    def __init__(self, 
                 agent_id: str,
                 private_key: str,
                 w3: Web3,
                 contracts: Dict[str, Any],
                 initial_balance: Dict[str, float] = None,
                 random_seed: Optional[int] = None):
        """
        Initialize base agent
        
        Args:
            agent_id: Unique identifier for agent
            private_key: Private key for agent's wallet
            w3: Web3 instance
            contracts: Dictionary of deployed contracts
            initial_balance: Initial token balances
            random_seed: Seed for deterministic randomness
        """
        self.agent_id = agent_id
        self.w3 = w3
        self.contracts = contracts
        self.account = Account.from_key(private_key)
        self.address = self.account.address
        
        # Setup deterministic randomness
        if random_seed is not None:
            self.random = random.Random(random_seed)
        else:
            self.random = random.Random()
            
        # Transaction management
        self.nonce = self.w3.eth.get_transaction_count(self.address)
        self.gas_limit = 500000
        self.gas_price = self.w3.to_wei('20', 'gwei')
        
        # Performance tracking
        self.pnl = 0.0
        self.total_gas_used = 0
        self.transaction_count = 0
        self.trade_history = []
        
        # Initial balances
        self.initial_balances = initial_balance or {}
        
        logger.info(f"🤖 Agent {self.agent_id} initialized with address {self.address}")
    
    def get_eth_balance(self) -> float:
        """Get ETH balance in ether"""
        balance_wei = self.w3.eth.get_balance(self.address)
        return self.w3.from_wei(balance_wei, 'ether')
    
    def get_token_balance(self, token_address: str) -> int:
        """Get ERC20 token balance"""
        try:
            token_contract = self.w3.eth.contract(
                address=token_address,
                abi=self.contracts[token_address]['abi']
            )
            return token_contract.functions.balanceOf(self.address).call()
        except Exception as e:
            logger.error(f"Failed to get token balance: {e}")
            return 0
    
    def get_all_balances(self) -> Dict[str, float]:
        """Get all token balances for the agent"""
        balances = {
            'ETH': self.get_eth_balance()
        }
        
        # Get ERC20 token balances
        for name, contract_info in self.contracts.items():
            if 'ERC20' in name or name in ['TEST', 'USDC']:
                try:
                    balance = self.get_token_balance(contract_info['address'])
                    decimals = self.get_token_decimals(contract_info['address'])
                    balances[name] = balance / (10 ** decimals)
                except Exception as e:
                    logger.warning(f"Failed to get balance for {name}: {e}")
                    balances[name] = 0.0
        
        return balances
    
    def get_token_decimals(self, token_address: str) -> int:
        """Get token decimals"""
        try:
            token_contract = self.w3.eth.contract(
                address=token_address,
                abi=self.contracts[token_address]['abi']
            )
            return token_contract.functions.decimals().call()
        except:
            return 18  # Default to 18 decimals
    
    def send_transaction(self, transaction: Dict[str, Any]) -> str:
        """
        Send a transaction and wait for confirmation
        
        Args:
            transaction: Transaction dictionary
            
        Returns:
            Transaction hash
        """
        try:
            # Add transaction parameters
            transaction.update({
                'from': self.address,
                'nonce': self.nonce,
                'gas': self.gas_limit,
                'gasPrice': self.gas_price,
                'chainId': self.w3.eth.chain_id
            })
            
            # Sign and send transaction
            signed_tx = self.account.sign_transaction(transaction)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            # Wait for confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt.status == 0:
                raise Exception("Transaction failed")
            
            # Update tracking
            self.nonce += 1
            self.transaction_count += 1
            self.total_gas_used += receipt.gasUsed
            
            logger.debug(f"Agent {self.agent_id} sent transaction {tx_hash.hex()}")
            
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Transaction failed for agent {self.agent_id}: {e}")
            raise
    
    def approve_token_spending(self, token_address: str, spender: str, amount: int) -> str:
        """Approve token spending by another contract"""
        token_contract = self.w3.eth.contract(
            address=token_address,
            abi=self.contracts[token_address]['abi']
        )
        
        transaction = token_contract.functions.approve(spender, amount).build_transaction({})
        return self.send_transaction(transaction)
    
    def transfer_token(self, token_address: str, to: str, amount: int) -> str:
        """Transfer tokens to another address"""
        token_contract = self.w3.eth.contract(
            address=token_address,
            abi=self.contracts[token_address]['abi']
        )
        
        transaction = token_contract.functions.transfer(to, amount).build_transaction({})
        return self.send_transaction(transaction)
    
    def calculate_pnl(self) -> float:
        """Calculate profit/loss based on initial and current balances"""
        current_balances = self.get_all_balances()
        pnl = 0.0
        
        for token, initial_balance in self.initial_balances.items():
            current_balance = current_balances.get(token, 0.0)
            # Simplified PnL calculation (assumes 1:1 USD value)
            pnl += (current_balance - initial_balance)
        
        self.pnl = pnl
        return pnl
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get agent performance statistics"""
        return {
            'agent_id': self.agent_id,
            'address': self.address,
            'pnl': self.calculate_pnl(),
            'total_gas_used': self.total_gas_used,
            'transaction_count': self.transaction_count,
            'avg_gas_per_tx': self.total_gas_used / max(1, self.transaction_count),
            'current_balances': self.get_all_balances(),
            'trade_count': len(self.trade_history)
        }
    
    def log_trade(self, trade_type: str, details: Dict[str, Any]):
        """Log a trade for performance tracking"""
        trade_record = {
            'timestamp': self.w3.eth.get_block('latest')['timestamp'],
            'block_number': self.w3.eth.block_number,
            'agent_id': self.agent_id,
            'trade_type': trade_type,
            **details
        }
        self.trade_history.append(trade_record)
        logger.info(f"Agent {self.agent_id} executed {trade_type}: {details}")
    
    @abstractmethod
    def step(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute one step of agent logic
        
        Args:
            market_data: Current market state data
            
        Returns:
            Dictionary of actions taken
        """
        pass
    
    @abstractmethod
    def should_act(self, market_data: Dict[str, Any]) -> bool:
        """
        Determine if agent should act based on market conditions
        
        Args:
            market_data: Current market state data
            
        Returns:
            True if agent should act
        """
        pass