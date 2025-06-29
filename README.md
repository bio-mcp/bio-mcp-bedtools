# bio-mcp-bedtools

MCP (Model Context Protocol) server for genome arithmetic and interval operations.

## Overview

This MCP server provides access to bedtools functionality, allowing AI assistants to perform genome arithmetic operations on genomic intervals.

## Features

- Genome arithmetic operations (intersect, union, merge, etc.)
- Support for BED, GFF, VCF, and other genomic formats
- File size limits and timeout protection
- Temporary file management
- Async execution with proper error handling

## Installation

### Using pip

```bash
pip install bio-mcp-bedtools
```

### From source

```bash
git clone https://github.com/bio-mcp/bio-mcp-bedtools
cd bio-mcp-bedtools
pip install -e .
```

## Configuration

Configure your MCP client (e.g., Claude Desktop) by adding to your configuration:

```json
{
  "mcp-servers": {
    "bio-bedtools": {
      "command": "python",
      "args": ["-m", "bio_mcp_bedtools"]
    }
  }
}
```

### Environment Variables

- `BIO_MCP_MAX_FILE_SIZE`: Maximum input file size (default: 100MB)
- `BIO_MCP_TIMEOUT`: Command timeout in seconds (default: 300)
- `BIO_MCP_BEDTOOLS_PATH`: Path to bedtools executable

## Usage

Once configured, the AI assistant can use the following tools:

### `bedtools_intersect`

Find overlapping intervals between two BED/GFF/VCF files

**Parameters:**
- `input_file_a` (required): Path to first input file
- `input_file_b` (required): Path to second input file
- `write_a`: Write the original entry in A for each overlap
- `write_b`: Write the original entry in B for each overlap

**Example:**
```
Find intersections between regions.bed and annotations.gff
```

## Development

### Running tests

```bash
pytest tests/
```

### Building Docker image

```bash
docker build -t bio-mcp-bedtools .
```

## License

MIT License