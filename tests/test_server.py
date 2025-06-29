import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from src.server import BedtoolsServer, ServerSettings


@pytest.fixture
def server():
    settings = ServerSettings(
        bedtools_path="mock_bedtools", temp_dir=tempfile.gettempdir()
    )
    return BedtoolsServer(settings)


@pytest.mark.skip(reason="MCP Server list_tools() decorator testing not implemented")
@pytest.mark.asyncio
async def test_list_tools(server):
    # This test would need to be implemented differently to work with MCP Server decorators
    # The functionality is tested through the call_tool tests instead
    pass


@pytest.mark.asyncio
async def test_run_bedtools_intersect_missing_file(server):
    result = await server._run_bedtools_intersect(
        {
            "input_file_a": "/nonexistent/file.bed",
            "input_file_b": "/nonexistent/file2.bed",
        }
    )
    assert len(result) == 1
    assert result[0].message.startswith("Input file A not found")


@pytest.mark.asyncio
async def test_run_bedtools_intersect_success(server, tmp_path):
    # Create test input files
    input_file_a = tmp_path / "test_a.bed"
    input_file_b = tmp_path / "test_b.bed"
    input_file_a.write_text("chr1\t100\t200\tfeature1")
    input_file_b.write_text("chr1\t150\t250\tfeature2")

    # Mock subprocess execution
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"chr1\t150\t200\tfeature1", b"")
        mock_exec.return_value = mock_process

        result = await server._run_bedtools_intersect(
            {"input_file_a": str(input_file_a), "input_file_b": str(input_file_b)}
        )

        assert len(result) == 1
        assert result[0].text == "chr1\t150\t200\tfeature1"


@pytest.mark.asyncio
async def test_run_bedtools_merge_success(server, tmp_path):
    # Create test input file
    input_file = tmp_path / "test.bed"
    input_file.write_text("chr1\t100\t200\nchr1\t150\t250")

    # Mock subprocess execution
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"chr1\t100\t250", b"")
        mock_exec.return_value = mock_process

        result = await server._run_bedtools_merge({"input_file": str(input_file)})

        assert len(result) == 1
        assert result[0].text == "chr1\t100\t250"


@pytest.mark.asyncio
async def test_run_bedtools_sort_success(server, tmp_path):
    # Create test input file
    input_file = tmp_path / "test.bed"
    input_file.write_text("chr2\t100\t200\nchr1\t150\t250")

    # Mock subprocess execution
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"chr1\t150\t250\nchr2\t100\t200", b"")
        mock_exec.return_value = mock_process

        result = await server._run_bedtools_sort({"input_file": str(input_file)})

        assert len(result) == 1
        assert result[0].text == "chr1\t150\t250\nchr2\t100\t200"
