from typing import Any, Dict, Mapping

import pytest

from gql import Client, gql
from gql.transport.exceptions import (
    TransportAlreadyConnected,
    TransportClosed,
    TransportProtocolError,
    TransportQueryError,
    TransportServerError,
)

from .conftest import (
    TemporaryFile,
    get_localhost_ssl_context_client,
    strip_braces_spaces,
)

# Marking all tests in this file with the httpx marker
pytestmark = pytest.mark.httpx

query1_str = """
    query getContinents {
      continents {
        code
        name
      }
    }
"""

query1_server_answer = (
    '{"data":{"continents":['
    '{"code":"AF","name":"Africa"},{"code":"AN","name":"Antarctica"},'
    '{"code":"AS","name":"Asia"},{"code":"EU","name":"Europe"},'
    '{"code":"NA","name":"North America"},{"code":"OC","name":"Oceania"},'
    '{"code":"SA","name":"South America"}]}}'
)


@pytest.mark.aiohttp
@pytest.mark.asyncio
async def test_httpx_query(aiohttp_server, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    async def handler(request):
        return web.Response(
            text=query1_server_answer,
            content_type="application/json",
            headers={"dummy": "test1234"},
        )

    app = web.Application()
    app.router.add_route("POST", "/", handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    def test_code():
        transport = HTTPXTransport(url=url)

        with Client(transport=transport) as session:

            query = gql(query1_str)

            # Execute query synchronously
            result = session.execute(query)

            continents = result["continents"]

            africa = continents[0]

            assert africa["code"] == "AF"

            # Checking response headers are saved in the transport
            assert hasattr(transport, "response_headers")
            assert isinstance(transport.response_headers, Mapping)
            assert transport.response_headers["dummy"] == "test1234"

    await run_sync_test(server, test_code)


@pytest.mark.aiohttp
@pytest.mark.asyncio
@pytest.mark.parametrize("verify_https", ["disabled", "cert_provided"])
async def test_httpx_query_https(ssl_aiohttp_server, run_sync_test, verify_https):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    async def handler(request):
        return web.Response(
            text=query1_server_answer,
            content_type="application/json",
            headers={"dummy": "test1234"},
        )

    app = web.Application()
    app.router.add_route("POST", "/", handler)
    server = await ssl_aiohttp_server(app)

    url = str(server.make_url("/"))

    assert str(url).startswith("https://")

    def test_code():
        extra_args = {}

        if verify_https == "cert_provided":
            _, ssl_context = get_localhost_ssl_context_client()

            extra_args["verify"] = ssl_context
        elif verify_https == "disabled":
            extra_args["verify"] = False

        transport = HTTPXTransport(
            url=url,
            **extra_args,
        )

        with Client(transport=transport) as session:

            query = gql(query1_str)

            # Execute query synchronously
            result = session.execute(query)

            continents = result["continents"]

            africa = continents[0]

            assert africa["code"] == "AF"

            # Checking response headers are saved in the transport
            assert hasattr(transport, "response_headers")
            assert isinstance(transport.response_headers, Mapping)
            assert transport.response_headers["dummy"] == "test1234"

    await run_sync_test(server, test_code)


@pytest.mark.aiohttp
@pytest.mark.asyncio
@pytest.mark.parametrize("verify_https", ["explicitely_enabled", "default"])
async def test_httpx_query_https_self_cert_fail(
    ssl_aiohttp_server, run_sync_test, verify_https
):
    """By default, we should verify the ssl certificate"""
    from aiohttp import web
    from httpx import ConnectError

    from gql.transport.httpx import HTTPXTransport

    async def handler(request):
        return web.Response(
            text=query1_server_answer,
            content_type="application/json",
            headers={"dummy": "test1234"},
        )

    app = web.Application()
    app.router.add_route("POST", "/", handler)
    server = await ssl_aiohttp_server(app)

    url = str(server.make_url("/"))

    assert str(url).startswith("https://")

    def test_code():
        extra_args: Dict[str, Any] = {}

        if verify_https == "explicitely_enabled":
            extra_args["verify"] = True

        transport = HTTPXTransport(
            url=url,
            **extra_args,
        )

        with pytest.raises(ConnectError) as exc_info:
            with Client(transport=transport) as session:

                query = gql(query1_str)

                # Execute query synchronously
                session.execute(query)

        expected_error = "certificate verify failed: self-signed certificate"

        assert expected_error in str(exc_info.value)

    await run_sync_test(server, test_code)


@pytest.mark.aiohttp
@pytest.mark.asyncio
async def test_httpx_cookies(aiohttp_server, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    async def handler(request):
        assert "COOKIE" in request.headers
        assert "cookie1=val1" == request.headers["COOKIE"]

        return web.Response(text=query1_server_answer, content_type="application/json")

    app = web.Application()
    app.router.add_route("POST", "/", handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    def test_code():
        transport = HTTPXTransport(url=url, cookies={"cookie1": "val1"})

        with Client(transport=transport) as session:

            query = gql(query1_str)

            # Execute query synchronously
            result = session.execute(query)

            continents = result["continents"]

            africa = continents[0]

            assert africa["code"] == "AF"

    await run_sync_test(server, test_code)


@pytest.mark.aiohttp
@pytest.mark.asyncio
async def test_httpx_error_code_401(aiohttp_server, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    async def handler(request):
        # Will generate http error code 401
        return web.Response(
            text='{"error":"Unauthorized","message":"401 Client Error: Unauthorized"}',
            content_type="application/json",
            status=401,
        )

    app = web.Application()
    app.router.add_route("POST", "/", handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    def test_code():
        transport = HTTPXTransport(url=url)

        with Client(transport=transport) as session:

            query = gql(query1_str)

            with pytest.raises(TransportServerError) as exc_info:
                session.execute(query)

            assert "Client error '401 Unauthorized'" in str(exc_info.value)

    await run_sync_test(server, test_code)


@pytest.mark.aiohttp
@pytest.mark.asyncio
async def test_httpx_error_code_429(aiohttp_server, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    async def handler(request):
        # Will generate http error code 429
        return web.Response(
            text="""
<html>
  <head>
     <title>Too Many Requests</title>
  </head>
  <body>
     <h1>Too Many Requests</h1>
     <p>I only allow 50 requests per hour to this Web site per
        logged in user.  Try again soon.</p>
  </body>
</html>""",
            content_type="text/html",
            status=429,
            headers={"Retry-After": "3600"},
        )

    app = web.Application()
    app.router.add_route("POST", "/", handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    def test_code():
        transport = HTTPXTransport(url=url)

        with Client(transport=transport) as session:

            query = gql(query1_str)

            with pytest.raises(TransportServerError) as exc_info:
                session.execute(query)

            assert "429, message='Too Many Requests'" in str(exc_info.value)

        # Checking response headers are saved in the transport
        assert hasattr(transport, "response_headers")
        assert isinstance(transport.response_headers, Mapping)
        assert transport.response_headers["Retry-After"] == "3600"


@pytest.mark.aiohttp
@pytest.mark.asyncio
async def test_httpx_error_code_500(aiohttp_server, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    async def handler(request):
        # Will generate http error code 500
        raise Exception("Server error")

    app = web.Application()
    app.router.add_route("POST", "/", handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    def test_code():
        transport = HTTPXTransport(url=url)

        with Client(transport=transport) as session:

            query = gql(query1_str)

            with pytest.raises(TransportServerError):
                session.execute(query)

    await run_sync_test(server, test_code)


query1_server_error_answer = '{"errors": ["Error 1", "Error 2"]}'


@pytest.mark.aiohttp
@pytest.mark.asyncio
async def test_httpx_error_code(aiohttp_server, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    async def handler(request):
        return web.Response(
            text=query1_server_error_answer, content_type="application/json"
        )

    app = web.Application()
    app.router.add_route("POST", "/", handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    def test_code():
        transport = HTTPXTransport(url=url)

        with Client(transport=transport) as session:

            query = gql(query1_str)

            with pytest.raises(TransportQueryError):
                session.execute(query)

    await run_sync_test(server, test_code)


invalid_protocol_responses = [
    "{}",
    "qlsjfqsdlkj",
    '{"not_data_or_errors": 35}',
]


@pytest.mark.aiohttp
@pytest.mark.asyncio
@pytest.mark.parametrize("response", invalid_protocol_responses)
async def test_httpx_invalid_protocol(aiohttp_server, response, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    async def handler(request):
        return web.Response(text=response, content_type="application/json")

    app = web.Application()
    app.router.add_route("POST", "/", handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    def test_code():
        transport = HTTPXTransport(url=url)

        with Client(transport=transport) as session:

            query = gql(query1_str)

            with pytest.raises(TransportProtocolError):
                session.execute(query)

    await run_sync_test(server, test_code)


@pytest.mark.aiohttp
@pytest.mark.asyncio
async def test_httpx_cannot_connect_twice(aiohttp_server, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    async def handler(request):
        return web.Response(text=query1_server_answer, content_type="application/json")

    app = web.Application()
    app.router.add_route("POST", "/", handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    def test_code():
        transport = HTTPXTransport(url=url)

        with Client(transport=transport) as session:

            with pytest.raises(TransportAlreadyConnected):
                session.transport.connect()

    await run_sync_test(server, test_code)


@pytest.mark.aiohttp
@pytest.mark.asyncio
async def test_httpx_cannot_execute_if_not_connected(aiohttp_server, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    async def handler(request):
        return web.Response(text=query1_server_answer, content_type="application/json")

    app = web.Application()
    app.router.add_route("POST", "/", handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    def test_code():
        transport = HTTPXTransport(url=url)

        query = gql(query1_str)

        with pytest.raises(TransportClosed):
            transport.execute(query)

    await run_sync_test(server, test_code)


query1_server_answer_with_extensions = (
    '{"data":{"continents":['
    '{"code":"AF","name":"Africa"},{"code":"AN","name":"Antarctica"},'
    '{"code":"AS","name":"Asia"},{"code":"EU","name":"Europe"},'
    '{"code":"NA","name":"North America"},{"code":"OC","name":"Oceania"},'
    '{"code":"SA","name":"South America"}]},'
    '"extensions": {"key1": "val1"}'
    "}"
)


@pytest.mark.aiohttp
@pytest.mark.asyncio
async def test_httpx_query_with_extensions(aiohttp_server, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    async def handler(request):
        return web.Response(
            text=query1_server_answer_with_extensions, content_type="application/json"
        )

    app = web.Application()
    app.router.add_route("POST", "/", handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    def test_code():
        transport = HTTPXTransport(url=url)

        with Client(transport=transport) as session:

            query = gql(query1_str)

            execution_result = session.execute(query, get_execution_result=True)

            assert execution_result.extensions["key1"] == "val1"

    await run_sync_test(server, test_code)


file_upload_server_answer = '{"data":{"success":true}}'

file_upload_mutation_1 = """
    mutation($file: Upload!) {
      uploadFile(input:{other_var:$other_var, file:$file}) {
        success
      }
    }
"""

file_upload_mutation_1_operations = (
    '{"query": "mutation ($file: Upload!) {\\n  uploadFile(input: {other_var: '
    '$other_var, file: $file}) {\\n    success\\n  }\\n}", "variables": '
    '{"file": null, "other_var": 42}}'
)

file_upload_mutation_1_map = '{"0": ["variables.file"]}'

file_1_content = """
This is a test file
This file will be sent in the GraphQL mutation
"""


@pytest.mark.aiohttp
@pytest.mark.asyncio
async def test_httpx_file_upload(aiohttp_server, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    async def single_upload_handler(request):
        from aiohttp import web

        reader = await request.multipart()

        field_0 = await reader.next()
        assert field_0.name == "operations"
        field_0_text = await field_0.text()
        assert strip_braces_spaces(field_0_text) == file_upload_mutation_1_operations

        field_1 = await reader.next()
        assert field_1.name == "map"
        field_1_text = await field_1.text()
        assert field_1_text == file_upload_mutation_1_map

        field_2 = await reader.next()
        assert field_2.name == "0"
        field_2_text = await field_2.text()
        assert field_2_text == file_1_content

        field_3 = await reader.next()
        assert field_3 is None

        return web.Response(
            text=file_upload_server_answer, content_type="application/json"
        )

    app = web.Application()
    app.router.add_route("POST", "/", single_upload_handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    def test_code():
        transport = HTTPXTransport(url=url)

        with TemporaryFile(file_1_content) as test_file:
            with Client(transport=transport) as session:
                query = gql(file_upload_mutation_1)

                file_path = test_file.filename

                with open(file_path, "rb") as f:

                    params = {"file": f, "other_var": 42}
                    execution_result = session._execute(
                        query, variable_values=params, upload_files=True
                    )

                    assert execution_result.data["success"]

    await run_sync_test(server, test_code)


@pytest.mark.aiohttp
@pytest.mark.asyncio
async def test_httpx_file_upload_with_content_type(aiohttp_server, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    async def single_upload_handler(request):
        from aiohttp import web

        reader = await request.multipart()

        field_0 = await reader.next()
        assert field_0.name == "operations"
        field_0_text = await field_0.text()
        assert strip_braces_spaces(field_0_text) == file_upload_mutation_1_operations

        field_1 = await reader.next()
        assert field_1.name == "map"
        field_1_text = await field_1.text()
        assert field_1_text == file_upload_mutation_1_map

        field_2 = await reader.next()
        assert field_2.name == "0"
        field_2_text = await field_2.text()
        assert field_2_text == file_1_content

        # Verifying the content_type
        assert field_2.headers["Content-Type"] == "application/pdf"

        field_3 = await reader.next()
        assert field_3 is None

        return web.Response(
            text=file_upload_server_answer, content_type="application/json"
        )

    app = web.Application()
    app.router.add_route("POST", "/", single_upload_handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    def test_code():
        transport = HTTPXTransport(url=url)

        with TemporaryFile(file_1_content) as test_file:
            with Client(transport=transport) as session:
                query = gql(file_upload_mutation_1)

                file_path = test_file.filename

                with open(file_path, "rb") as f:

                    # Setting the content_type
                    f.content_type = "application/pdf"  # type: ignore

                    params = {"file": f, "other_var": 42}
                    execution_result = session._execute(
                        query, variable_values=params, upload_files=True
                    )

                    assert execution_result.data["success"]

    await run_sync_test(server, test_code)


@pytest.mark.aiohttp
@pytest.mark.asyncio
async def test_httpx_file_upload_additional_headers(aiohttp_server, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    async def single_upload_handler(request):
        from aiohttp import web

        assert request.headers["X-Auth"] == "foobar"

        reader = await request.multipart()

        field_0 = await reader.next()
        assert field_0.name == "operations"
        field_0_text = await field_0.text()
        assert strip_braces_spaces(field_0_text) == file_upload_mutation_1_operations

        field_1 = await reader.next()
        assert field_1.name == "map"
        field_1_text = await field_1.text()
        assert field_1_text == file_upload_mutation_1_map

        field_2 = await reader.next()
        assert field_2.name == "0"
        field_2_text = await field_2.text()
        assert field_2_text == file_1_content

        field_3 = await reader.next()
        assert field_3 is None

        return web.Response(
            text=file_upload_server_answer, content_type="application/json"
        )

    app = web.Application()
    app.router.add_route("POST", "/", single_upload_handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    def test_code():
        transport = HTTPXTransport(url=url, headers={"X-Auth": "foobar"})

        with TemporaryFile(file_1_content) as test_file:
            with Client(transport=transport) as session:
                query = gql(file_upload_mutation_1)

                file_path = test_file.filename

                with open(file_path, "rb") as f:

                    params = {"file": f, "other_var": 42}
                    execution_result = session._execute(
                        query, variable_values=params, upload_files=True
                    )

                    assert execution_result.data["success"]

    await run_sync_test(server, test_code)


@pytest.mark.aiohttp
@pytest.mark.asyncio
async def test_httpx_binary_file_upload(aiohttp_server, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    # This is a sample binary file content containing all possible byte values
    binary_file_content = bytes(range(0, 256))

    async def binary_upload_handler(request):

        from aiohttp import web

        reader = await request.multipart()

        field_0 = await reader.next()
        assert field_0.name == "operations"
        field_0_text = await field_0.text()
        assert strip_braces_spaces(field_0_text) == file_upload_mutation_1_operations

        field_1 = await reader.next()
        assert field_1.name == "map"
        field_1_text = await field_1.text()
        assert field_1_text == file_upload_mutation_1_map

        field_2 = await reader.next()
        assert field_2.name == "0"
        field_2_binary = await field_2.read()
        assert field_2_binary == binary_file_content

        field_3 = await reader.next()
        assert field_3 is None

        return web.Response(
            text=file_upload_server_answer, content_type="application/json"
        )

    app = web.Application()
    app.router.add_route("POST", "/", binary_upload_handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    transport = HTTPXTransport(url=url)

    def test_code():
        with TemporaryFile(binary_file_content) as test_file:
            with Client(transport=transport) as session:

                query = gql(file_upload_mutation_1)

                file_path = test_file.filename

                with open(file_path, "rb") as f:

                    params = {"file": f, "other_var": 42}

                    execution_result = session._execute(
                        query, variable_values=params, upload_files=True
                    )

                    assert execution_result.data["success"]

    await run_sync_test(server, test_code)


file_upload_mutation_2_operations = (
    '{"query": "mutation ($file1: Upload!, $file2: Upload!) {\\n  '
    'uploadFile(input: {file1: $file, file2: $file}) {\\n    success\\n  }\\n}", '
    '"variables": {"file1": null, "file2": null}}'
)


@pytest.mark.aiohttp
@pytest.mark.asyncio
async def test_httpx_file_upload_two_files(aiohttp_server, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    file_upload_mutation_2 = """
    mutation($file1: Upload!, $file2: Upload!) {
      uploadFile(input:{file1:$file, file2:$file}) {
        success
      }
    }
    """

    file_upload_mutation_2_map = '{"0": ["variables.file1"], "1": ["variables.file2"]}'

    file_2_content = """
    This is a second test file
    This file will also be sent in the GraphQL mutation
    """

    async def handler(request):

        reader = await request.multipart()

        field_0 = await reader.next()
        assert field_0.name == "operations"
        field_0_text = await field_0.text()
        assert strip_braces_spaces(field_0_text) == file_upload_mutation_2_operations

        field_1 = await reader.next()
        assert field_1.name == "map"
        field_1_text = await field_1.text()
        assert field_1_text == file_upload_mutation_2_map

        field_2 = await reader.next()
        assert field_2.name == "0"
        field_2_text = await field_2.text()
        assert field_2_text == file_1_content

        field_3 = await reader.next()
        assert field_3.name == "1"
        field_3_text = await field_3.text()
        assert field_3_text == file_2_content

        field_4 = await reader.next()
        assert field_4 is None

        return web.Response(
            text=file_upload_server_answer, content_type="application/json"
        )

    app = web.Application()
    app.router.add_route("POST", "/", handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    def test_code():
        transport = HTTPXTransport(url=url)

        with TemporaryFile(file_1_content) as test_file_1:
            with TemporaryFile(file_2_content) as test_file_2:

                with Client(transport=transport) as session:

                    query = gql(file_upload_mutation_2)

                    file_path_1 = test_file_1.filename
                    file_path_2 = test_file_2.filename

                    f1 = open(file_path_1, "rb")
                    f2 = open(file_path_2, "rb")

                    params = {
                        "file1": f1,
                        "file2": f2,
                    }

                    execution_result = session._execute(
                        query, variable_values=params, upload_files=True
                    )

                    assert execution_result.data["success"]

                    f1.close()
                    f2.close()

    await run_sync_test(server, test_code)


file_upload_mutation_3_operations = (
    '{"query": "mutation ($files: [Upload!]!) {\\n  uploadFiles'
    "(input: {files: $files})"
    ' {\\n    success\\n  }\\n}", "variables": {"files": [null, null]}}'
)


@pytest.mark.aiohttp
@pytest.mark.asyncio
async def test_httpx_file_upload_list_of_two_files(aiohttp_server, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    file_upload_mutation_3 = """
    mutation($files: [Upload!]!) {
      uploadFiles(input:{files:$files}) {
        success
      }
    }
    """

    file_upload_mutation_3_map = (
        '{"0": ["variables.files.0"], "1": ["variables.files.1"]}'
    )

    file_2_content = """
    This is a second test file
    This file will also be sent in the GraphQL mutation
    """

    async def handler(request):

        reader = await request.multipart()

        field_0 = await reader.next()
        assert field_0.name == "operations"
        field_0_text = await field_0.text()
        assert strip_braces_spaces(field_0_text) == file_upload_mutation_3_operations

        field_1 = await reader.next()
        assert field_1.name == "map"
        field_1_text = await field_1.text()
        assert field_1_text == file_upload_mutation_3_map

        field_2 = await reader.next()
        assert field_2.name == "0"
        field_2_text = await field_2.text()
        assert field_2_text == file_1_content

        field_3 = await reader.next()
        assert field_3.name == "1"
        field_3_text = await field_3.text()
        assert field_3_text == file_2_content

        field_4 = await reader.next()
        assert field_4 is None

        return web.Response(
            text=file_upload_server_answer, content_type="application/json"
        )

    app = web.Application()
    app.router.add_route("POST", "/", handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    def test_code():
        transport = HTTPXTransport(url=url)

        with TemporaryFile(file_1_content) as test_file_1:
            with TemporaryFile(file_2_content) as test_file_2:
                with Client(transport=transport) as session:

                    query = gql(file_upload_mutation_3)

                    file_path_1 = test_file_1.filename
                    file_path_2 = test_file_2.filename

                    f1 = open(file_path_1, "rb")
                    f2 = open(file_path_2, "rb")

                    params = {"files": [f1, f2]}

                    execution_result = session._execute(
                        query, variable_values=params, upload_files=True
                    )

                    assert execution_result.data["success"]

                    f1.close()
                    f2.close()

    await run_sync_test(server, test_code)


@pytest.mark.aiohttp
@pytest.mark.asyncio
async def test_httpx_error_fetching_schema(aiohttp_server, run_sync_test):
    from aiohttp import web

    from gql.transport.httpx import HTTPXTransport

    error_answer = """
{
    "errors": [
        {
            "errorType": "UnauthorizedException",
            "message": "Permission denied"
        }
    ]
}
"""

    async def handler(request):
        return web.Response(
            text=error_answer,
            content_type="application/json",
        )

    app = web.Application()
    app.router.add_route("POST", "/", handler)
    server = await aiohttp_server(app)

    url = str(server.make_url("/"))

    def test_code():
        transport = HTTPXTransport(url=url)

        with pytest.raises(TransportQueryError) as exc_info:
            with Client(transport=transport, fetch_schema_from_transport=True):
                pass

        expected_error = (
            "Error while fetching schema: "
            "{'errorType': 'UnauthorizedException', 'message': 'Permission denied'}"
        )

        assert expected_error in str(exc_info.value)
        assert transport.client is None

    await run_sync_test(server, test_code)
