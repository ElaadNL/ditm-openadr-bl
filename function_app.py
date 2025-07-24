import azure.functions as func
from src.main import bp

app = func.FunctionApp()

try:
    app.register_functions(bp)
except Exception as exc:
    print(exc)
