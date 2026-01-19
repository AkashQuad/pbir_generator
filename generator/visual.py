def generate_visual(ws: dict, table_name: str, x: int = 0, y: int = 0) -> dict:
    """
    Generate a PBIR-style visual definition from worksheet metadata
    Safe against missing or renamed keys
    """

    # Normalize chart type safely
    chart_type = (
        ws.get("type")
        or ws.get("chartType")
        or ws.get("vizType")
        or "table"
    )

    # Get columns safely
    columns = ws.get("columns", []) or ws.get("fields", [])

    # Default visual size
    width = 500
    height = 300

    # Generate bindings
    if chart_type == "table":
        visual_type = "tableEx"
        bindings = {
            "Values": [{"table": table_name, "column": col} for col in columns]
        }
        height = 350

    elif chart_type in ("column", "bar"):
        visual_type = "clusteredColumnChart"
        bindings = {
            "Category": {"table": table_name, "column": columns[0]} if len(columns) > 0 else {"table": table_name, "column": "Unknown"},
            "Values": {"table": table_name, "column": columns[1]} if len(columns) > 1 else {"table": table_name, "column": columns[0] if columns else "Value"}
        }

    else:
        # Fallback to table
        visual_type = "tableEx"
        bindings = {
            "Values": [{"table": table_name, "column": col} for col in columns]
        }

    return {
        "visualType": visual_type,
        "title": ws.get("name", "Auto Visual"),
        "layout": {
            "x": x,
            "y": y,
            "width": width,
            "height": height
        },
        "bindings": bindings
    }
