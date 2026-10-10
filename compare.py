from bs4 import BeautifulSoup


def extract_usernames(html_file):
    with open(html_file, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
        # Adjust the selector based on your HTML structure
        return set([tag.text.strip() for tag in soup.find_all('a')])


followers = extract_usernames('followers_kayla.html')
following = extract_usernames('following_kayla.html')

not_following_back = following - followers

print("People you follow who don't follow you back:")
for user in sorted(not_following_back):
    print(user)
