class CRMIdConverter:
    regex = '[0-9a-f]{17}'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value