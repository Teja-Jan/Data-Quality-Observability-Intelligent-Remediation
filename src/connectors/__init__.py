"""
Data Source Connectors — plug-and-play ingestion layer.
All connectors return (pd.DataFrame, source_meta_dict).
"""
from .data_connector import DatabaseConnector, FlatFileConnector, APIConnector

__all__ = ["DatabaseConnector", "FlatFileConnector", "APIConnector"]
