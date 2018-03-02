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
        return 'Entry({self.uniqueId!r}, {self.title!r}, ' \
               '{self.link!r}, {self.created_at!r}, ' \
               'description={self.description!r}, ' \
               'tags={self.tags!r}, ' \
               'photo={self.photo!r}, ' \
               'coordinates={self.coordinates!r})'.format(self)
