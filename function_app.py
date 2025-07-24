import azure.functions as func

try:
    from src.main import bp
except Exception as exc:
    print(exc)

app = func.FunctionApp()

try:
    app.register_functions(bp)
except Exception as exc:
    print(exc)
