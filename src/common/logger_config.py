from loguru import logger



# Define a class to intercept stdout and send it to Loguru
class StreamToLoguru:
    def write(self, message):
        message = message.strip()
        if message:  # Avoid logging empty lines
            logger.info(message)

    def flush(self):
        pass  # Needed for compatibility