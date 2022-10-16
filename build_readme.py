from python_graphql_client import GraphqlClient
import feedparser
import httpx
import json
import pathlib
import re
import os

root = pathlib.Path(__file__).parent.resolve()
client = GraphqlClient(endpoint="https://api.github.com/graphql")


TOKEN = os.environ.get("AUX_SECRET", "")


def replace_chunk(content, marker, chunk):
    r = re.compile(
        r"<!\-\- {} starts \-\->.*<!\-\- {} ends \-\->".format(marker, marker),
        re.DOTALL,
    )
    chunk = "<!-- {} starts -->\n{}\n<!-- {} ends -->".format(marker, chunk, marker)
    return r.sub(chunk, content)


def make_query(after_cursor=None):
    return """
query {
  viewer {
    repositories(first: 100, privacy: PUBLIC) {
      nodes {
        name,
        defaultBranchRef {
          target {
            ... on Commit {
              history(first:10) {
                edges {
                    node {
                      ... on Commit {
                        committedDate,
                        message,
                        url
                      }
                    }
                }
              }
            }
          }
        },
      },
      pageInfo {
        hasNextPage,
        endCursor
      }
    }
  }
}
""".replace(
        "AFTER", '"{}"'.format(after_cursor) if after_cursor else "null"
    )


def fetch_commits(oauth_token):
    repos = []
    commits = []
    repo_names = set()
    has_next_page = True
    after_cursor = None

    while has_next_page:
        data = client.execute(
            query=make_query(after_cursor),
            headers={"Authorization": "Bearer Base64.strict_encode64({})".format(oauth_token)},
        )
        print()
        print(json.dumps(data, indent=4))
        print()
        for repo in data["data"]["viewer"]["repositories"]["nodes"]:
            if repo["defaultBranchRef"] and repo["defaultBranchRef"]["target"] and repo["name"] not in repo_names:
                repos.append(repo)
                repo_names.add(repo["name"])
                commits.append(
                    {
                        "repo": repo["name"],
                        "last_commit": repo["defaultBranchRef"]["target"]["history"]["edges"][0]["node"]["message"]
                        .replace(repo["name"], "")
                        .strip(),
                        "published_at": repo["defaultBranchRef"]["target"]["history"]["edges"][0]["node"][
                            "committedDate"
                        ].split("T")[0],
                        "url": repo["defaultBranchRef"]["target"]["history"]["edges"][0]["node"]["url"]
                    }
                )
        has_next_page = data["data"]["viewer"]["repositories"]["pageInfo"][
            "hasNextPage"
        ]
        after_cursor = data["data"]["viewer"]["repositories"]["pageInfo"]["endCursor"]
    return commits


if __name__ == "__main__":
    readme = root / "README.md"
    commits = fetch_commits(TOKEN)
    commits.sort(key=lambda r: r["published_at"], reverse=True)
    md = "\n".join(
        [
            "* [{repo}: {last_commit}]({url}) - {published_at}".format(**commit)
            for commit in commits[:5]
        ]
    )
    readme_contents = readme.open().read()
    rewritten = replace_chunk(readme_contents, "recent_releases", "\n" + md + "\n")
    print(md)
    readme.open("w").write(rewritten)
