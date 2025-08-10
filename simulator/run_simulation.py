#!/usr/bin/env python3
"""
Simulation Runner - Orchestrates all agents and runs the simulation
"""

import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, List
import pandas as pd
from web3 import Web3
import click

from .agent_base import AgentBase
from .market_maker import MarketMaker
from .trader import RandomTrader, MomentumTrader, ArbitrageTrader
from .metrics import MetricsCalculator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('simulation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SimulationRunner:
    """
    Main simulation orchestrator
    Manages agents, executes simulation steps, and collects metrics
    """
    
    def __init__(self, 
                 config: Dict[str, Any],
                 ganache_url: str = 'http://localhost:8545',
                 deployed_contracts_file: str = 'deployed.json'):
        """
        Initialize simulation runner
        
        Args:
            config: Simulation configuration
            ganache_url: Ganache RPC URL
            deployed_contracts_file: Path to deployed contracts JSON
        """
        self.config = config
        self.ganache_url = ganache_url
        
        # Initialize Web3 connection
        self.w3 = Web3(Web3.HTTPProvider(ganache_url))
        if not self.w3.is_connected():
            raise Exception(f"Cannot connect to Ganache at {ganache_url}")
        
        # Load deployed contracts
        self.contracts = self._load_contracts(deployed_contracts_file)
        
        # Initialize agents
        self.agents: List[AgentBase] = []
        self._setup_agents()
        
        # Initialize metrics calculator
        self.metrics_calculator = MetricsCalculator(self.w3, self.contracts)
        
        # Simulation state
        self.current_step = 0
        self.max_steps = config.get('max_steps', 100)
        self.step_delay = config.get('step_delay', 1.0)  # Seconds between steps
        
        # Results storage
        self.step_results = []
        self.agent_performance = {}
        
        logger.info(f"🎮 Simulation initialized with {len(self.agents)} agents")
    
    def _load_contracts(self, contracts_file: str) -> Dict[str, Any]:
        """Load deployed contract information"""
        try:
            with open(contracts_file, 'r') as f:
                deployment_info = json.load(f)
            
            contracts = {}
            for name, contract_info in deployment_info['contracts'].items():
                contracts[name] = {
                    'address': contract_info['address'],
                    'abi': contract_info['abi']
                }
                # Also index by address for easy lookup
                contracts[contract_info['address']] = {
                    'address': contract_info['address'],
                    'abi': contract_info['abi']
                }
            
            logger.info(f"📄 Loaded {len(contracts)} deployed contracts")
            return contracts
            
        except FileNotFoundError:
            raise Exception(f"Deployed contracts file not found: {contracts_file}")
        except Exception as e:
            raise Exception(f"Failed to load contracts: {e}")
    
    def _setup_agents(self):
        """Initialize all simulation agents"""
        # Default Ganache accounts (first 10 accounts)
        default_keys = [
            "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d",
            "0x6cbed15c793ce57650b9877cf6fa156fbef513c4e6134f022a85b1ffdd59b2a1",
            "0x6370fd033278c143179d81c5526140625662b8daa446c22ee2d73db3707e620c",
            "0x646f1ce2fdad0e6deeeb5c7e8e5543bdde65e86029e2fd9fc169899c440a7913",
            "0xadd53f9a7e588d003326d1cbf9e4a43c061aadd9bc938c843a79e7b4fd2ad743",
            "0x395df67f0c2d2d9fe1ad08d1bc8b6627011959b79c53d7dd6a3536a33ab8a4fd",
            "0xe485d098507f54e7733a205420dfddbe58db035fa577fc294ebd14db90767a52",
            "0xa453611d9419d0e56f499079478fd72c37b251a94bfde4d19872c44cf65386e3",
            "0x829e924fdf021ba3dbbc4225edfece9aca04b929d6e75613329ca6f1d31c0bb4",
            "0xb0057716d5917badaf911b193b12b910811c1497b5bada8d7711f758981c3773"
        ]
        
        # Get contract addresses
        amm_address = self.contracts['AMM']['address']
        token_a_address = self.contracts['ERC20Token']['address']  # TEST token
        token_b_address = self.contracts['USDC']['address']  # USDC token
        
        agent_configs = self.config.get('agents', [])
        
        for i, agent_config in enumerate(agent_configs):
            agent_type = agent_config['type']
            agent_id = f"{agent_type}_{i}"
            private_key = default_keys[i % len(default_keys)]
            
            # Determine initial balances
            initial_balance = agent_config.get('initial_balance', {})
            
            # Create agent based on type
            if agent_type == 'market_maker':
                agent = MarketMaker(
                    agent_id=agent_id,
                    private_key=private_key,
                    w3=self.w3,
                    contracts=self.contracts,
                    amm_address=amm_address,
                    token_a_address=token_a_address,
                    token_b_address=token_b_address,
                    initial_balance=initial_balance,
                    random_seed=self.config.get('random_seed', 42) + i
                )
                
            elif agent_type == 'random_trader':
                agent = RandomTrader(
                    agent_id=agent_id,
                    private_key=private_key,
                    w3=self.w3,
                    contracts=self.contracts,
                    amm_address=amm_address,
                    token_a_address=token_a_address,
                    token_b_address=token_b_address,
                    initial_balance=initial_balance,
                    trade_frequency=agent_config.get('trade_frequency', 0.1),
                    random_seed=self.config.get('random_seed', 42) + i
                )
                
            elif agent_type == 'momentum_trader':
                agent = MomentumTrader(
                    agent_id=agent_id,
                    private_key=private_key,
                    w3=self.w3,
                    contracts=self.contracts,
                    amm_address=amm_address,
                    token_a_address=token_a_address,
                    token_b_address=token_b_address,
                    initial_balance=initial_balance,
                    lookback_periods=agent_config.get('lookback_periods', 5),
                    momentum_threshold=agent_config.get('momentum_threshold', 0.02),
                    random_seed=self.config.get('random_seed', 42) + i
                )
                
            elif agent_type == 'arbitrage_trader':
                agent = ArbitrageTrader(
                    agent_id=agent_id,
                    private_key=private_key,
                    w3=self.w3,
                    contracts=self.contracts,
                    amm_address=amm_address,
                    token_a_address=token_a_address,
                    token_b_address=token_b_address,
                    initial_balance=initial_balance,
                    min_profit_threshold=agent_config.get('min_profit_threshold', 0.01),
                    random_seed=self.config.get('random_seed', 42) + i
                )
                
            else:
                logger.warning(f"Unknown agent type: {agent_type}")
                continue
            
            self.agents.append(agent)
            logger.info(f"✅ Created agent {agent_id} of type {agent_type}")
    
    def _distribute_initial_tokens(self):
        """Distribute initial tokens to agents"""
        logger.info("💰 Distributing initial tokens to agents...")
        
        # Get token contracts
        test_token = self.w3.eth.contract(
            address=self.contracts['ERC20Token']['address'],
            abi=self.contracts['ERC20Token']['abi']
        )
        
        usdc_token = self.w3.eth.contract(
            address=self.contracts['USDC']['address'],
            abi=self.contracts['USDC']['abi']
        )
        
        # Deployer account (has all initial tokens)
        deployer_key = "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d"
        deployer_account = self.w3.eth.account.from_key(deployer_key)
        
        for agent in self.agents:
            # Transfer TEST tokens
            test_amount = self.w3.to_wei(10000, 'ether')  # 10,000 TEST tokens
            usdc_amount = self.w3.to_wei(10000, 'mwei')   # 10,000 USDC (6 decimals)
            
            # Transfer TEST tokens
            try:
                tx = test_token.functions.transfer(agent.address, test_amount).build_transaction({
                    'from': deployer_account.address,
                    'nonce': self.w3.eth.get_transaction_count(deployer_account.address),
                    'gas': 100000,
                    'gasPrice': self.w3.to_wei('20', 'gwei')
                })
                
                signed_tx = deployer_account.sign_transaction(tx)
                tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                self.w3.eth.wait_for_transaction_receipt(tx_hash)
                
                logger.debug(f"Transferred {self.w3.from_wei(test_amount, 'ether')} TEST to {agent.agent_id}")
                
            except Exception as e:
                logger.error(f"Failed to transfer TEST tokens to {agent.agent_id}: {e}")
            
            # Transfer USDC tokens
            try:
                tx = usdc_token.functions.transfer(agent.address, usdc_amount).build_transaction({
                    'from': deployer_account.address,
                    'nonce': self.w3.eth.get_transaction_count(deployer_account.address),
                    'gas': 100000,
                    'gasPrice': self.w3.to_wei('20', 'gwei')
                })
                
                signed_tx = deployer_account.sign_transaction(tx)
                tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                self.w3.eth.wait_for_transaction_receipt(tx_hash)
                
                logger.debug(f"Transferred {self.w3.from_wei(usdc_amount, 'mwei')} USDC to {agent.agent_id}")
                
            except Exception as e:
                logger.error(f"Failed to transfer USDC tokens to {agent.agent_id}: {e}")
    
    def _advance_blockchain(self):
        """Advance blockchain by mining a block"""
        try:
            # Mine a new block (Ganache auto-mines, but we can still advance time)
            current_timestamp = self.w3.eth.get_block('latest')['timestamp']
            
            # In a real scenario, you might use ganache-cli with --blockTime option
            # or web3.eth.send_transaction with a dummy transaction to advance blocks
            
        except Exception as e:
            logger.debug(f"Failed to advance blockchain: {e}")
    
    def run_step(self) -> Dict[str, Any]:
        """Execute one simulation step"""
        step_start_time = time.time()
        
        logger.info(f"🔄 Executing step {self.current_step}")
        
        # Collect market data
        market_data = self.metrics_calculator.get_current_market_state()
        
        # Execute agent actions
        agent_actions = []
        for agent in self.agents:
            try:
                if agent.should_act(market_data):
                    actions = agent.step(market_data)
                    agent_actions.append(actions)
                    
            except Exception as e:
                logger.error(f"Agent {agent.agent_id} failed in step {self.current_step}: {e}")
        
        # Advance blockchain
        self._advance_blockchain()
        
        # Calculate step metrics
        step_metrics = self.metrics_calculator.calculate_step_metrics(
            self.current_step,
            agent_actions,
            market_data
        )
        
        # Collect agent performance data
        agent_performance = {}
        for agent in self.agents:
            agent_performance[agent.agent_id] = agent.get_performance_stats()
        
        step_result = {
            'step': self.current_step,
            'timestamp': int(time.time()),
            'block_number': self.w3.eth.block_number,
            'execution_time': time.time() - step_start_time,
            'market_data': market_data,
            'agent_actions': agent_actions,
            'step_metrics': step_metrics,
            'agent_performance': agent_performance
        }
        
        self.step_results.append(step_result)
        
        logger.info(f"✅ Step {self.current_step} completed in {step_result['execution_time']:.2f}s")
        
        return step_result
    
    def run_simulation(self) -> Dict[str, Any]:
        """Run the complete simulation"""
        logger.info(f"🚀 Starting simulation with {self.max_steps} steps")
        
        start_time = time.time()
        
        # Distribute initial tokens
        self._distribute_initial_tokens()
        
        # Run simulation steps
        try:
            for step in range(self.max_steps):
                self.current_step = step
                
                # Execute step
                step_result = self.run_step()
                
                # Sleep between steps if configured
                if self.step_delay > 0:
                    time.sleep(self.step_delay)
                
                # Log progress
                if step % 10 == 0:
                    logger.info(f"📊 Progress: {step}/{self.max_steps} steps completed")
        
        except KeyboardInterrupt:
            logger.info("🛑 Simulation interrupted by user")
        except Exception as e:
            logger.error(f"❌ Simulation failed: {e}")
            raise
        
        # Calculate final metrics and generate report
        simulation_results = self._generate_final_report(start_time)
        
        logger.info("🎉 Simulation completed successfully!")
        
        return simulation_results
    
    def _generate_final_report(self, start_time: float) -> Dict[str, Any]:
        """Generate final simulation report"""
        total_time = time.time() - start_time
        
        # Calculate overall metrics
        overall_metrics = self.metrics_calculator.calculate_overall_metrics(self.step_results)
        
        # Collect final agent performance
        final_agent_performance = {}
        for agent in self.agents:
            final_agent_performance[agent.agent_id] = agent.get_performance_stats()
        
        simulation_results = {
            'simulation_config': self.config,
            'execution_summary': {
                'total_steps': self.current_step + 1,
                'total_time': total_time,
                'avg_step_time': total_time / max(1, self.current_step + 1),
                'total_transactions': sum(agent.transaction_count for agent in self.agents),
                'total_gas_used': sum(agent.total_gas_used for agent in self.agents)
            },
            'overall_metrics': overall_metrics,
            'final_agent_performance': final_agent_performance,
            'step_results': self.step_results[-10:]  # Last 10 steps for summary
        }
        
        # Save detailed results
        self._save_results(simulation_results)
        
        return simulation_results
    
    def _save_results(self, results: Dict[str, Any]):
        """Save simulation results to files"""
        timestamp = int(time.time())
        
        # Save JSON results
        results_file = f"simulation_results_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"📄 Results saved to {results_file}")
        
        # Save CSV metrics
        self._save_csv_metrics(timestamp)
    
    def _save_csv_metrics(self, timestamp: int):
        """Save metrics to CSV files"""
        try:
            # Step metrics
            step_data = []
            for step_result in self.step_results:
                row = {
                    'step': step_result['step'],
                    'timestamp': step_result['timestamp'],
                    'block_number': step_result['block_number'],
                    **step_result['step_metrics']
                }
                step_data.append(row)
            
            if step_data:
                df_steps = pd.DataFrame(step_data)
                df_steps.to_csv(f"step_metrics_{timestamp}.csv", index=False)
                logger.info(f"📊 Step metrics saved to step_metrics_{timestamp}.csv")
            
            # Agent performance
            agent_data = []
            for step_result in self.step_results:
                for agent_id, performance in step_result['agent_performance'].items():
                    row = {
                        'step': step_result['step'],
                        'timestamp': step_result['timestamp'],
                        'agent_id': agent_id,
                        **performance
                    }
                    agent_data.append(row)
            
            if agent_data:
                df_agents = pd.DataFrame(agent_data)
                df_agents.to_csv(f"agent_performance_{timestamp}.csv", index=False)
                logger.info(f"📊 Agent performance saved to agent_performance_{timestamp}.csv")
                
        except Exception as e:
            logger.error(f"Failed to save CSV metrics: {e}")


# CLI Interface
@click.command()
@click.option('--config', default='simulation_config.json', help='Simulation configuration file')
@click.option('--ganache-url', default='http://localhost:8545', help='Ganache RPC URL')
@click.option('--contracts', default='deployed.json', help='Deployed contracts file')
@click.option('--steps', default=None, type=int, help='Number of simulation steps (overrides config)')
@click.option('--delay', default=None, type=float, help='Delay between steps in seconds')
def main(config: str, ganache_url: str, contracts: str, steps: int, delay: float):
    """Run blockchain simulation"""
    
    # Load configuration
    try:
        with open(config, 'r') as f:
            simulation_config = json.load(f)
    except FileNotFoundError:
        # Use default configuration
        simulation_config = {
            'max_steps': 50,
            'step_delay': 1.0,
            'random_seed': 42,
            'agents': [
                {
                    'type': 'market_maker',
                    'initial_balance': {'TEST': 50000, 'USDC': 50000}
                },
                {
                    'type': 'random_trader',
                    'trade_frequency': 0.2,
                    'initial_balance': {'TEST': 10000, 'USDC': 10000}
                },
                {
                    'type': 'momentum_trader',
                    'lookback_periods': 5,
                    'momentum_threshold': 0.02,
                    'initial_balance': {'TEST': 10000, 'USDC': 10000}
                }
            ]
        }
        
        # Save default configuration
        with open(config, 'w') as f:
            json.dump(simulation_config, f, indent=2)
        
        logger.info(f"📄 Created default configuration: {config}")
    
    # Override configuration with CLI arguments
    if steps is not None:
        simulation_config['max_steps'] = steps
    if delay is not None:
        simulation_config['step_delay'] = delay
    
    # Run simulation
    try:
        runner = SimulationRunner(simulation_config, ganache_url, contracts)
        results = runner.run_simulation()
        
        print("\n🎉 Simulation Summary:")
        print(f"   Total Steps: {results['execution_summary']['total_steps']}")
        print(f"   Total Time: {results['execution_summary']['total_time']:.2f}s")
        print(f"   Total Transactions: {results['execution_summary']['total_transactions']}")
        print(f"   Total Gas Used: {results['execution_summary']['total_gas_used']:,}")
        
        print("\n📊 Agent Performance:")
        for agent_id, performance in results['final_agent_performance'].items():
            print(f"   {agent_id}: PnL={performance['pnl']:.2f}, Trades={performance['trade_count']}")
        
    except Exception as e:
        logger.error(f"❌ Simulation failed: {e}")
        raise


if __name__ == '__main__':
    main()
                # Complete Blockchain Development Package - RHEL Compatible

## 1 — Project Skeleton (Tree)