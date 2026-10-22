from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pymongo.errors import PyMongoError

from .auth import router
from .config import Settings
from .database import connect
from .filling import router as filling_router
from .statistics import router as statistics_router
from .surveys import router as surveys_router


def create_app(settings=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.settings = settings or Settings.from_env()
        client, database = connect(app.state.settings)
        app.state.db = database
        try:
            yield
        finally:
            client.close()

    app = FastAPI(title='MongoDB 问卷系统', lifespan=lifespan)
    app.include_router(router)
    app.include_router(surveys_router)
    app.include_router(filling_router)
    app.include_router(statistics_router)

    @app.exception_handler(PyMongoError)
    async def database_error(request: Request, exc: PyMongoError):
        return JSONResponse(status_code=503, content={'detail': '数据库操作失败，请检查数据库服务及结构'})

    @app.middleware('http')
    async def response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/', include_in_schema=False)
    def home():
        return FileResponse(Path(__file__).parent / 'static' / 'index.html')

    @app.get('/survey/{survey_id}', include_in_schema=False)
    def fill_page(survey_id: str):
        return FileResponse(Path(__file__).parent / 'static' / 'index.html')

    @app.get('/health')
    def health(request: Request):
        request.app.state.db.command('ping')
        return {'status': 'ok'}

    return app


app = create_app()
