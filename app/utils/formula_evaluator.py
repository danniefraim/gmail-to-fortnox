import decimal
import re
from typing import Dict, Any, Union, Optional

class FormulaEvaluator:
    """
    Evaluates formulas using extracted values.
    Supports basic arithmetic operations and percentages.
    """
    
    def __init__(self):
        """Initialize the formula evaluator"""
        # Configure decimal context for rounding
        decimal.getcontext().rounding = decimal.ROUND_HALF_UP
    
    def evaluate(self, 
                formula: Union[str, int, float, decimal.Decimal], 
                variables: Dict[str, decimal.Decimal]) -> Optional[decimal.Decimal]:
        """
        Evaluate a formula using the provided variables.
        
        Args:
            formula: Formula to evaluate, can be a string expression or a numeric value
            variables: Dictionary of variable names and their values
            
        Returns:
            Result as a Decimal object, rounded to 2 decimal places, or None if evaluation fails
        """
        if formula is None:
            return None
            
        # If already a number, just return it as Decimal
        if isinstance(formula, (int, float)):
            return decimal.Decimal(str(formula)).quantize(decimal.Decimal('0.01'))
        
        # If already a Decimal, just return it (rounded)
        if isinstance(formula, decimal.Decimal):
            return formula.quantize(decimal.Decimal('0.01'))
            
        # If not a string, can't evaluate it as a formula
        if not isinstance(formula, str):
            print(f"Cannot evaluate formula: {formula} (type: {type(formula)})")
            return None
            
        # If the formula is just a variable name, return its value
        if formula in variables:
            return variables[formula].quantize(decimal.Decimal('0.01'))
            
        try:
            # Replace variable names with their values
            # Sort variables by length (longest first) to avoid partial replacements
            sorted_vars = sorted(variables.keys(), key=len, reverse=True)
            
            # Create a copy of the formula that we'll modify
            expr = formula
            
            # Replace each variable with its value
            for var_name in sorted_vars:
                # Use word boundaries to avoid partial replacements
                # e.g., 'total' shouldn't match part of 'subtotal'
                pattern = r'\b' + re.escape(var_name) + r'\b'
                expr = re.sub(pattern, str(variables[var_name]), expr)
            
            # Handle percentage calculations (e.g., "base_amount * 25%")
            expr = re.sub(r'(\d+)%', r'(\1/100)', expr)
            
            # Evaluate the expression (safely)
            # Note: This uses eval() which is generally unsafe, but we're only allowing
            # numbers, basic arithmetic operators, and parentheses
            if not re.match(r'^[\d\s\+\-\*\/\(\)\.\,]+$', expr):
                raise ValueError(f"Invalid characters in expression: {expr}")
                
            # Replace comma with period for decimal separator
            expr = expr.replace(',', '.')
            
            # Evaluate and convert to Decimal
            result = eval(expr)
            decimal_result = decimal.Decimal(str(result))
            
            # Round to 2 decimal places
            return decimal_result.quantize(decimal.Decimal('0.01'))
            
        except Exception as e:
            print(f"Error evaluating formula '{formula}': {str(e)}")
            return None
    
    def calculate_voucher_entries(self, 
                                 entries: list, 
                                 variables: Dict[str, decimal.Decimal]) -> list:
        """
        Calculate voucher entries using formulas and variables.
        
        Args:
            entries: List of entry dictionaries with account, debit, credit
            variables: Dictionary of variable names and their values
            
        Returns:
            List of calculated entry dictionaries with account, debit, credit as Decimal objects
        """
        calculated_entries = []
        
        for entry in entries:
            calculated_entry = {
                'account': entry['account']
            }
            
            # Evaluate debit formula
            debit_value = entry.get('debit')
            if debit_value is not None:
                calculated_entry['debit'] = self.evaluate(debit_value, variables) or decimal.Decimal('0')
            else:
                calculated_entry['debit'] = decimal.Decimal('0')
                
            # Evaluate credit formula
            credit_value = entry.get('credit')
            if credit_value is not None:
                calculated_entry['credit'] = self.evaluate(credit_value, variables) or decimal.Decimal('0')
            else:
                calculated_entry['credit'] = decimal.Decimal('0')
                
            calculated_entries.append(calculated_entry)
            
        return calculated_entries 