from src.mapping_uploads.mapping_uploads_sync import sync_mapping_uploads

def sync_mapping_uploads_handler(event, context):
    return sync_mapping_uploads()

if __name__ == "__main__":
    sync_mapping_uploads_handler(None, None)
