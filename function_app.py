import azure.functions as func
from src.main import bp

app = func.FunctionApp()

app.register_functions(bp)
