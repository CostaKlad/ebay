import pandas as pd
from bs4 import BeautifulSoup
import requests
import numpy as np


item = input("Enter the item you want: ")
item = item.replace(" ", "+")

ebayURL='https://www.ebay.com/sch/i.html?_odkw=&_ipg=25&_sadis=200&_adv=1&_sop=12&LH_SALE_CURRENCY=0&LH_Sold=1&' \
        '_osacat=0&_from=R40&_dmd=1&LH_Complete=1&_trksid=m570.l1313&_nkw=%s&_sacat=0' % (item)

source = requests.get(ebayURL).text
soup = BeautifulSoup(source, 'html.parser')
Title3 = []
Price3 = []
for Title in soup.find_all('h3', class_="s-item__title s-item__title--has-tags"):
    Title2 = Title.text
    Title3.append(Title2)


for price in soup.find_all('span', class_="POSITIVE"):
    price2 = price.text
    Price3.append(price2)

result = pd.DataFrame({'Card': Title3, 'Sold Price': Price3})
print(result)




