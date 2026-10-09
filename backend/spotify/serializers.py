from rest_framework import serializers


class SpotifyDeviceSelectionSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=255, trim_whitespace=True)
