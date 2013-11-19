from django.db import models


class Blag(models.Model):
    name = models.CharField(
        "The name of the blag",
        max_length=255)
    timestamp_created = models.DateTimeField(
        auto_now_add=True)


class Post(models.Model):
    blag = models.ForeignKey('Blag')
    title = models.CharField(
        "Title of the post",
        max_length=255)
    body = models.TextField()
