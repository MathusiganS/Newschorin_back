import scrapy


class TamilwinItem(scrapy.Item):
    title = scrapy.Field()
    url = scrapy.Field()
