import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import ErrorData, ImageContent, TextContent, Tool
from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class ServerSettings(BaseSettings):
    max_file_size: int = Field(
        default=100_000_000, description="Maximum input file size in bytes"
    )
    temp_dir: Optional[str] = Field(
        default=None, description="Temporary directory for processing"
    )
    timeout: int = Field(default=300, description="Command timeout in seconds")
    bedtools_path: str = Field(
        default="bedtools", description="Path to bedtools executable"
    )

    model_config = ConfigDict(env_prefix="BIO_MCP_")


class BedtoolsServer:
    def __init__(self, settings: Optional[ServerSettings] = None):
        self.settings = settings or ServerSettings()
        self.server = Server("bio-mcp-bedtools")
        self._setup_handlers()

    def _setup_handlers(self):
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="bedtools_intersect",
                    description="Find overlapping intervals between two files",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "input_file_a": {
                                "type": "string",
                                "description": "Path to first input file (BED/GFF/VCF)",
                            },
                            "input_file_b": {
                                "type": "string",
                                "description": "Path to second input file (BED/GFF/VCF)",
                            },
                            "write_a": {
                                "type": "boolean",
                                "description": "Write the original entry in A for each overlap",
                                "default": False,
                            },
                            "write_b": {
                                "type": "boolean",
                                "description": "Write the original entry in B for each overlap",
                                "default": False,
                            },
                            "write_overlap": {
                                "type": "boolean",
                                "description": "Write the amount of overlap between features",
                                "default": False,
                            },
                        },
                        "required": ["input_file_a", "input_file_b"],
                    },
                ),
                Tool(
                    name="bedtools_merge",
                    description="Merge overlapping or nearby intervals",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "input_file": {
                                "type": "string",
                                "description": "Path to input BED file",
                            },
                            "distance": {
                                "type": "integer",
                                "description": "Maximum distance between features for merging",
                                "default": 0,
                            },
                        },
                        "required": ["input_file"],
                    },
                ),
                Tool(
                    name="bedtools_sort",
                    description="Sort BED/GFF/VCF files by chromosome and position",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "input_file": {
                                "type": "string",
                                "description": "Path to input file",
                            }
                        },
                        "required": ["input_file"],
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(
            name: str, arguments: Any
        ) -> list[TextContent | ImageContent | ErrorData]:
            if name == "bedtools_intersect":
                return await self._run_bedtools_intersect(arguments)
            elif name == "bedtools_merge":
                return await self._run_bedtools_merge(arguments)
            elif name == "bedtools_sort":
                return await self._run_bedtools_sort(arguments)
            else:
                return [ErrorData(code=500, message=f"Unknown tool: {name}")]

    async def _run_bedtools_intersect(
        self, arguments: dict
    ) -> list[TextContent | ErrorData]:
        try:
            # Validate input files
            input_path_a = Path(arguments["input_file_a"])
            input_path_b = Path(arguments["input_file_b"])

            if not input_path_a.exists():
                return [
                    ErrorData(
                        code=404, message=f"Input file A not found: {input_path_a}"
                    )
                ]
            if not input_path_b.exists():
                return [
                    ErrorData(
                        code=404, message=f"Input file B not found: {input_path_b}"
                    )
                ]

            if input_path_a.stat().st_size > self.settings.max_file_size:
                return [
                    ErrorData(
                        code=413,
                        message=f"File A too large. Maximum size: {self.settings.max_file_size} bytes",
                    )
                ]
            if input_path_b.stat().st_size > self.settings.max_file_size:
                return [
                    ErrorData(
                        code=413,
                        message=f"File B too large. Maximum size: {self.settings.max_file_size} bytes",
                    )
                ]

            # Create temporary directory for processing
            with tempfile.TemporaryDirectory(dir=self.settings.temp_dir) as tmpdir:
                # Copy input files to temp directory
                temp_input_a = Path(tmpdir) / input_path_a.name
                temp_input_b = Path(tmpdir) / input_path_b.name
                temp_input_a.write_bytes(input_path_a.read_bytes())
                temp_input_b.write_bytes(input_path_b.read_bytes())

                # Build bedtools intersect command
                cmd = [
                    self.settings.bedtools_path,
                    "intersect",
                    "-a",
                    str(temp_input_a),
                    "-b",
                    str(temp_input_b),
                ]

                # Add optional parameters
                if arguments.get("write_a", False):
                    cmd.append("-wa")
                if arguments.get("write_b", False):
                    cmd.append("-wb")
                if arguments.get("write_overlap", False):
                    cmd.append("-wo")

                # Execute command
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tmpdir,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=self.settings.timeout
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    return [
                        ErrorData(
                            code=504,
                            message=f"Command timed out after {self.settings.timeout} seconds",
                        )
                    ]

                if process.returncode != 0:
                    return [ErrorData(code=500, message=f"Command failed: {stderr.decode()}")]

                # Process output
                output = stdout.decode()

                # Return results
                return [TextContent(type="text", text=output)]

        except Exception as e:
            logger.error(f"Error running bedtools intersect: {e}", exc_info=True)
            return [ErrorData(code=500, message=f"Error: {str(e)}")]

    async def _run_bedtools_merge(
        self, arguments: dict
    ) -> list[TextContent | ErrorData]:
        try:
            # Validate input file
            input_path = Path(arguments["input_file"])
            if not input_path.exists():
                return [ErrorData(code=404, message=f"Input file not found: {input_path}")]

            if input_path.stat().st_size > self.settings.max_file_size:
                return [
                    ErrorData(
                        code=413, message=f"File too large. Maximum size: {self.settings.max_file_size} bytes"
                    )
                ]

            # Create temporary directory for processing
            with tempfile.TemporaryDirectory(dir=self.settings.temp_dir) as tmpdir:
                # Copy input file to temp directory
                temp_input = Path(tmpdir) / input_path.name
                temp_input.write_bytes(input_path.read_bytes())

                # Build bedtools merge command
                cmd = [self.settings.bedtools_path, "merge", "-i", str(temp_input)]

                # Add optional parameters
                distance = arguments.get("distance", 0)
                if distance > 0:
                    cmd.extend(["-d", str(distance)])

                # Execute command
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tmpdir,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=self.settings.timeout
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    return [
                        ErrorData(
                            code=504,
                            message=f"Command timed out after {self.settings.timeout} seconds",
                        )
                    ]

                if process.returncode != 0:
                    return [
                        ErrorData(
                            code=500, message=f"Command failed: {stderr.decode()}"
                        )
                    ]

                # Process output
                output = stdout.decode()

                # Return results
                return [TextContent(type="text", text=output)]

        except Exception as e:
            logger.error(f"Error running bedtools merge: {e}", exc_info=True)
            return [ErrorData(code=500, message=f"Error: {str(e)}")]

    async def _run_bedtools_sort(
        self, arguments: dict
    ) -> list[TextContent | ErrorData]:
        try:
            # Validate input file
            input_path = Path(arguments["input_file"])
            if not input_path.exists():
                return [ErrorData(code=404, message=f"Input file not found: {input_path}")]

            if input_path.stat().st_size > self.settings.max_file_size:
                return [
                    ErrorData(
                        code=413, message=f"File too large. Maximum size: {self.settings.max_file_size} bytes"
                    )
                ]

            # Create temporary directory for processing
            with tempfile.TemporaryDirectory(dir=self.settings.temp_dir) as tmpdir:
                # Copy input file to temp directory
                temp_input = Path(tmpdir) / input_path.name
                temp_input.write_bytes(input_path.read_bytes())

                # Build bedtools sort command
                cmd = [self.settings.bedtools_path, "sort", "-i", str(temp_input)]

                # Execute command
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tmpdir,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=self.settings.timeout
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    return [
                        ErrorData(
                            code=504,
                            message=f"Command timed out after {self.settings.timeout} seconds",
                        )
                    ]

                if process.returncode != 0:
                    return [
                        ErrorData(
                            code=500, message=f"Command failed: {stderr.decode()}"
                        )
                    ]

                # Process output
                output = stdout.decode()

                # Return results
                return [TextContent(type="text", text=output)]

        except Exception as e:
            logger.error(f"Error running bedtools sort: {e}", exc_info=True)
            return [ErrorData(code=500, message=f"Error: {str(e)}")]

    async def run(self):
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream, {})


async def main():
    logging.basicConfig(level=logging.INFO)
    server = BedtoolsServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
