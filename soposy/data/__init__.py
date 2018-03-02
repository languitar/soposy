class Entry(object):

    def __init__(self,
                 uniqueId,
                 title,
                 link,
                 created_at,
                 description=None,
                 tags=None,
                 photo=None,
                 coordinates=None):
        self.uniqueId = uniqueId
        self.title = title
        self.link = link
        self.created_at = created_at
        self.description = description
        self.tags = tags
        self.photo = photo
        self.coordinates = coordinates

    def __str__(self):
        return f'Entry({self.uniqueId!r}, {self.title!r}, ' \
               f'{self.link!r}, {self.created_at!r}, ' \
               f'description={self.description!r}, ' \
               f'tags={self.tags!r}, ' \
               f'photo={self.photo!r}, ' \
               f'coordinates={self.coordinates!r})'
