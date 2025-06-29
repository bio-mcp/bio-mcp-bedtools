"""
Example of how to add queue support to any bioinformatics MCP server
"""
from typing import Any, Optional

from mcp.types import ErrorData, TextContent

from .queue_integration import QueueIntegrationMixin
from .server import BedtoolsServer


class BedtoolsServerWithQueue(QueueIntegrationMixin, BedtoolsServer):
    """Bedtools server with async job queue support"""

    def __init__(self, settings=None, queue_url: Optional[str] = None):
        # Set queue URL before calling parent init
        self.queue_url = queue_url or "http://localhost:8000"
        super().__init__(settings)
        self._setup_async_handlers()

    def _setup_async_handlers(self):
        """Add async handlers to existing tools"""

        # Define which tools should have async variants
        async_tool_configs = {
            "bedtools_intersect": {
                "job_type": "bedtools",
                "description": "Run bedtools intersect analysis",
                "parameters": {
                    "input_file": {
                        "type": "string",
                        "description": "Path to input file"
                    },
                    # Add other tool-specific parameters
                },
                "required_params": ["input_file"]
            }
        }

        @self.server.list_tools()
        async def list_tools():
            # Get base tools from parent
            base_tools = await super(BedtoolsServerWithQueue, self).server.list_tools()

            # Add async variants
            async_tools = self.get_async_tools(async_tool_configs)

            return base_tools + async_tools

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any):
            # Handle async tools
            if name.endswith("_async"):
                base_name = name[:-6]  # Remove _async suffix
                if base_name in async_tool_configs:
                    return await self._handle_async_tool(
                        base_name,
                        async_tool_configs[base_name]["job_type"],
                        arguments
                    )

            # Handle job management tools
            elif name == "get_job_status":
                return await self._handle_job_status(arguments["job_id"])
            elif name == "get_job_result":
                return await self._handle_job_result(arguments["job_id"])
            elif name == "list_my_jobs":
                return await self._handle_list_jobs(arguments)
            elif name == "cancel_job":
                return await self._handle_cancel_job(arguments["job_id"])

            # Otherwise delegate to parent
            else:
                return await super(BedtoolsServerWithQueue, self).server.call_tool(name, arguments)

    async def _handle_async_tool(
        self,
        tool_name: str,
        job_type: str,
        arguments: dict
    ) -> list[TextContent | ErrorData]:
        """Submit tool job to queue"""
        try:
            # Extract queue-specific parameters
            priority = arguments.pop("priority", 5)
            tags = arguments.pop("tags", [])
            notification_email = arguments.pop("notification_email", None)

            # Submit job
            job_info = await self.submit_job(
                job_type=job_type,
                parameters=arguments,
                priority=priority,
                tags=tags
            )

            return [TextContent(
                text=f"Job submitted successfully!\n\n"
                     f"{self.format_job_status(job_info)}\n\n"
                     f"Use 'get_job_status' with job ID to check progress."
            )]

        except Exception as e:
            return [ErrorData(code=500, message=f"Error submitting job: {str(e)}")]

    async def _handle_job_status(self, job_id: str) -> list[TextContent | ErrorData]:
        """Get job status"""
        try:
            job_info = await self.get_job_status(job_id)
            return [TextContent(text=self.format_job_status(job_info))]
        except Exception as e:
            return [ErrorData(code=500, message=str(e))]

    async def _handle_job_result(self, job_id: str) -> list[TextContent | ErrorData]:
        """Get job results"""
        try:
            result = await self.get_job_result(job_id)

            result_text = f"Job {job_id} Results\n"
            result_text += "=" * 40 + "\n\n"

            if "summary" in result:
                result_text += "Summary:\n"
                for key, value in result["summary"].items():
                    result_text += f"  {key}: {value}\n"
                result_text += "\n"

            if "result_url" in result:
                result_text += f"Full results: {result['result_url']}\n"
                result_text += "Results available for 7 days.\n"

            return [TextContent(text=result_text)]

        except Exception as e:
            return [ErrorData(code=500, message=str(e))]

    async def _handle_list_jobs(self, arguments: dict) -> list[TextContent | ErrorData]:
        """List user's jobs - would need to implement in API"""
        return [TextContent(
            text="Job listing not yet implemented.\n"
                 "Use individual job IDs to check status."
        )]

    async def _handle_cancel_job(self, job_id: str) -> list[TextContent | ErrorData]:
        """Cancel a job"""
        try:
            result = await self.cancel_job(job_id)
            return [TextContent(text=f"Job {job_id} cancelled successfully")]
        except Exception as e:
            return [ErrorData(code=500, message=str(e))]
