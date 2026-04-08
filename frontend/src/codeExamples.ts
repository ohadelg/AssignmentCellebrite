import type { Language } from './api'

/** Five review-rich snippets per language (security, performance, logic, style). */
export const CODE_EXAMPLES: Record<Language, readonly string[]> = {
  python: [
    `def get_user_data(user_id):
    query = "SELECT * FROM users WHERE id = " + str(user_id)
    cursor.execute(query)
    return cursor.fetchall()


if __name__ == "__main__":
    uid = 42
    print("Constructed query:", "SELECT * FROM users WHERE id = " + str(uid))
`,
    `import subprocess


def run_report(filename: str) -> None:
    # User-controlled path in shell string — command injection
    subprocess.call("cat " + filename + " | head -n 20", shell=True)


if __name__ == "__main__":
    print("Unsafe pattern: shell=True with concatenated filename")
`,
    `def append_item(item, items=[]):
    items.append(item)
    return items


def parse_expr(user_input: str):
    try:
        return eval(user_input)
    except:
        return None


if __name__ == "__main__":
    print(append_item(1))
    print(append_item(2))
`,
    `import random


def reset_password_token(user_id: int) -> str:
    return str(random.random()) + str(user_id)


def read_user_file(username: str) -> str:
    path = "/var/data/" + username + ".txt"
    return open(path).read()


if __name__ == "__main__":
    print("token:", reset_password_token(7))
`,
    `import requests

CACHE = {}


def fetch_config(url: str) -> dict:
    if url in CACHE:
        return CACHE[url]
    r = requests.get(url)
    data = r.json()
    CACHE[url] = data
    return data


if __name__ == "__main__":
    print("cache keys (empty until fetch):", list(CACHE.keys()))
    print("demo: fetch_config() not called — would HTTP GET in real use")
`,
  ],

  typescript: [
    `function renderUserCard(username: string, bio: string): string {
  // If this HTML is injected into the page later, bio can carry XSS payloads
  return "<div class=\\"card\\"><h2>" + username + "</h2><p>" + bio + "</p></div>"
}

function parsePrefs(raw: unknown) {
  return JSON.parse(raw as string)
}

const sessionNonce = Math.random().toString(36)

export { renderUserCard, parsePrefs, sessionNonce }

// Sandbox run: tsx executes this file — need top-level side effects (like Python's if __name__)
console.log(renderUserCard("alice", "<img src=x onerror=alert(1)>"))
console.log("parsed ok:", parsePrefs('{"role":"guest"}'))
console.log("nonce prefix:", sessionNonce.slice(0, 4))
`,
    `async function saveAll(records: Record<string, unknown>[]) {
  records.forEach((r) => {
    fetch("/api/save", {
      method: "POST",
      body: JSON.stringify(r),
    })
  })
}

function buildQuery(table: string, filter: string) {
  return \`SELECT * FROM \${table} WHERE \${filter}\`
}

export { saveAll, buildQuery }

console.log("sample SQL:", buildQuery("users", "id = 1"))
// Avoid calling saveAll() here: relative fetch("/api/save") is invalid in Node and obscures the review demo
`,
    `const userCache: Record<string, object> = {}

export function getUser(id: string): object {
  if (userCache[id]) return userCache[id]
  const u = { id, name: "user-" + id, isAdmin: id === "1" }
  userCache[id] = u
  return u
}

export function joinLines(lines: string[]): string {
  let out = ""
  for (let i = 0; i < lines.length; i++) {
    out = out + lines[i] + "\\n"
  }
  return out
}

console.log(getUser("2"))
console.log(joinLines(["alpha", "beta"]))
`,
    `export function matchDangerous(text: string): RegExpMatchArray | null {
  const re = /^(a+)+$/
  return text.match(re)
}

export function mergeConfig(base: object, patch: object) {
  return Object.assign(base, patch)
}

console.log("small match:", matchDangerous("aaab")?.[0] ?? "(no match)")
console.log("merged:", mergeConfig({ x: 1 }, { y: 2 }))
`,
    `export function sumItems(data: { items: number[] }): number {
  let sum = 0
  for (let i = 0; i <= data.items.length; i++) {
    sum += data.items[i]
  }
  return sum
}

export class Counter {
  count = 0
  increment = () => {
    this.count++
  }
}

try {
  console.log("sum:", sumItems({ items: [10, 20] }))
} catch (e) {
  console.log("sumItems (off-by-one):", (e as Error).message)
}
const c = new Counter()
c.increment()
console.log("counter:", c.count)
`,
  ],

  java: [
    `public class Main {
    public static void main(String[] args) {
        String userId = args.length > 0 ? args[0] : "1";
        String sql = "SELECT * FROM users WHERE id = " + userId;
        System.out.println(sql);
    }
}
`,
    `public class Main {
    public static void main(String[] args) throws Exception {
        String userCmd = args.length > 0 ? args[0] : "/bin/echo";
        System.out.println("exec (async, unchecked): " + userCmd);
        Runtime.getRuntime().exec(userCmd);
        System.out.println("returned without waiting for process — review ProcessBuilder + waitFor");
    }
}
`,
    `import java.io.FileReader;
import java.io.IOException;

public class Main {
    static FileReader reader;

    public static void main(String[] args) {
        try {
            reader = new FileReader("data.txt");
            char[] buf = new char[100];
            reader.read(buf);
            System.out.println(buf);
        } catch (IOException e) {
            System.out.println("Sandbox: no data.txt — " + e.getClass().getSimpleName()
                + " (static FileReader / no try-with-resources still a review issue)");
        }
    }
}
`,
    `public class Main {
    public static void main(String[] args) {
        String a = new String("test");
        String b = new String("test");
        if (a == b) {
            System.out.println("same ref");
        } else {
            System.out.println("== compares identity, not string value");
        }
        String user = null;
        try {
            if (user.equals("admin")) {
                System.out.println("admin");
            }
        } catch (NullPointerException e) {
            System.out.println("NPE: equals() on null user — prefer \\"admin\\".equals(user)");
        }
    }
}
`,
    `import java.util.ArrayList;
import java.util.List;
import java.util.Random;

public class Main {
    static final Random rng = new Random();

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("ada");
        names.add("linus");
        try {
            for (int i = 0; i <= names.size(); i++) {
                System.out.println(names.get(i));
            }
        } catch (IndexOutOfBoundsException e) {
            System.out.println("IOOB: loop uses i <= size() — should be < size()");
        }
        System.out.println("token: " + rng.nextInt(1_000_000));
    }
}
`,
  ],
}

export function pickRandomExample(lang: Language): string {
  const pool = CODE_EXAMPLES[lang]
  return pool[Math.floor(Math.random() * pool.length)] ?? pool[0]!
}
