from django.db import models

class ArchitectureFirm(models.Model):
    name = models.CharField(max_length=64)
    link = models.URLField(max_length=256, blank=True)
    addr = models.TextField()
    phone = models.CharField(max_length=12)
    email = models.EmailField()
    frmid = models.CharField(max_length=64)
    contact_name = models.CharField(max_length=64, default='')
    checked_email = models.BooleanField(default=False)

    def __str__(self):
        return '\n'.join([self.frmid, self.name, self.link, self.addr, self.phone, self.email])

