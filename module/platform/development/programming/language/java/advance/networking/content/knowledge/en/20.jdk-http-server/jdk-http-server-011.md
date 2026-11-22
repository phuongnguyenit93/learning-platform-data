# SimpleFileServer and jwebserver: Serving Static Files for Testing with the JDK

## 1. Real-world scenario: needing an HTTP server right away, without a framework

When learning Java Networking, sometimes we just want an HTTP address so a browser, `curl`, Java `HttpClient`, or a frontend program can access **static** resources:

- Try `GET /index.html` to view a local HTML page.
- Serve `/assets/data.json` containing sample data for a frontend or an API client test.
- Allow downloading `hello.txt`/images from the development machine without writing a manual file-reading `HttpHandler`.
- Test HTTP status behaviors `200`, `404`, `HEAD`, `Content-Type`, or the difference between GET and POST.
- Have a fixture directory to run local integration tests without depending on the Internet.

Since **JDK 18** (JEP 408), the JDK provides two convenient ways:

1. **`jwebserver`**: a command-line program that creates a **Simple Web Server** for a static directory, just by running a command.
2. **`com.sun.net.httpserver.SimpleFileServer`**: a Java API to create a file-serving server or handler, which can be combined with `HttpServer` and custom test endpoints.

Both are primarily intended for **prototyping, development, debugging, and education**. They are **not** production web servers, **do not support HTTPS or HTTP/2** by the Simple Web Server design, and do not provide the full authentication, authorization, resource management, or hardening tools of a dedicated server. <https://openjdk.org/jeps/408>

**Goal of this lesson:** understand when to use each option, deploy a static server on loopback, test actual HTTP responses, know the security/serving limits, and clean up resources yourself. The content focuses on **SimpleFileServer and jwebserver** within the parent context of “JDK's HTTP server”; it does not build a new backend framework.

## 2. Version requirement: this is a Java 18+ feature, not Java 17

This component was introduced in **JDK 18**; JDK 17 has the `jdk.httpserver` module and the `HttpServer` class, but **does not yet have `SimpleFileServer` or the `jwebserver` tool**.

| Component | Available since version | Notes |
| --- | --- | --- |
| `com.sun.net.httpserver.HttpServer` | Available long before JDK 18 | Can manually write GET/POST handlers in Java 17 |
| `com.sun.net.httpserver.SimpleFileServer` | **JDK 18** | Static file handler/server factory |
| `jwebserver` | **JDK 18** | CLI static server bundled with the JDK |
| `java -m jdk.httpserver` | With JDK 18+ Simple Web Server | Way to launch the tool via module |
| `java.net.http.HttpClient` | JDK 11+ | Used as a client to verify examples |

**Check the environment:**

```bash
java -version
javac -version
jwebserver -h
```

If the OS reports `jwebserver: command not found` or an equivalent error, check whether `PATH` points to the **`bin` directory of JDK 18+** or only points to an older JRE/JDK. On Windows, run `where jwebserver`; on Unix, `command -v jwebserver`. You can also use:

```bash
java -m jdk.httpserver -h
```

This command does not create an HTTP resource when passed `-h`; instead, it displays the CLI help. If the IDE compiles with `--release 17`, importing `SimpleFileServer` will not be available in the public target API; use **`--release 18` or newer** and the `jdk.httpserver` module when compiling the sample Java program.

**Note on the tests:** the code in section 8 was **compiled with `javac --release 18` and actually run on JDK 24**. Do not claim that the sample runs on Java 17. Use a JDK version that supports the corresponding API.

## 3. Capabilities of Simple Web Server: serving static content, not business logic

A **document root** (the root directory to publish) is chosen. The server maps the HTTP request path to a resource in that directory tree:

```text
Selected local directory:
  static-demo/
    index.html
    hello.txt
    assets/
      logo.png
      data.json

HTTP server running at http://127.0.0.1:8000/

GET /                  -> static-demo/index.html (if present)
GET /hello.txt         -> static-demo/hello.txt
GET /assets/data.json  -> static-demo/assets/data.json
GET /assets/           -> directory listing if no index
GET /missing.txt       -> 404
HEAD /hello.txt        -> status/headers, no response body
POST /hello.txt        -> not supported as a file-write operation
```

How it works as described in the JDK documentation:

- **Existing file:** sends the file contents in the HTTP response.
- **Directory with an index file:** serves the index file according to the server's rules, typically `index.html`.
- **Directory without an index file:** may return an **HTML directory listing** containing file/subdirectory names.
- **Hidden files and symbolic links:** the Simple Web Server implementation **does not list or serve** these items per the documentation. How hidden files are identified may vary by filesystem/operating system.
- **HTTP methods:** only serves **`GET` and `HEAD`**. Other methods may be answered with `405 Method Not Allowed` or `501 Not Implemented` depending on the method/handling path.
- **Content-Type:** the server uses a built-in MIME table to guess the content type by file type/extension; for example, `.html` is `text/html`, and `.java` or `.txt` is typically `text/plain`.
- **Protocol:** Simple Web Server only serves HTTP/1.1 over HTTP, **not an HTTPS/HTTP2 application server**.

The served directory may have subdirectories. **Directory listing does not inherently have authentication**; a randomly named file in a directory listing **must not be treated as a secret file**. Choose a document root that contains only fixtures permitted to be viewed.

## 4. Getting started right away with `jwebserver`

Suppose you have created a **dedicated directory containing only test files**:

```text
static-demo/
  index.html
  hello.txt
  assets/
    data.json
```

Contents of the sample `index.html` file:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>JDK Static Demo</title>
</head>
<body>
  <h1>Java Simple Web Server</h1>
  <a href="/hello.txt">Open text file</a>
</body>
</html>
```

The `hello.txt` file can contain `Hello from Java!`; the `assets/data.json` file can contain `{"ok":true}`. Do not put private keys, secrets, `.env`, cookie/session dumps, or production configs into the test directory.

From a terminal, run:

```bash
jwebserver -b 127.0.0.1 -p 8000 -d ./static-demo -o info
```

After startup succeeds, browse to **`http://127.0.0.1:8000/`** or call:

```bash
curl -i http://127.0.0.1:8000/
curl -i http://127.0.0.1:8000/hello.txt
curl -I http://127.0.0.1:8000/hello.txt
curl -i http://127.0.0.1:8000/not-found.txt
```

**Observed results should be verified, not hard-coded as response bytes:** GET on a normal file returns `200`, HEAD returns headers without a body, and a non-existent path returns `404`; content bytes/MIME depend on the actual file and JDK. If port 8000 is already in use, switch to an available port, such as `-p 9000`. If `-d ./static-demo` is not found, check the **terminal's working directory** or pass an absolute path.

**Stopping the server:** press **Ctrl+C** in the terminal running `jwebserver`. It runs in the foreground until stopped; do not leave the server listening unintentionally after testing.

An equivalent alternative in intent:

```bash
java -m jdk.httpserver -b 127.0.0.1 -p 8000 -d ./static-demo -o info
```

With the tested JDK version, both the CLI and the module entry point accept the bind, port, directory, and output options. Launching via module **does not mean you have to write a Java class yourself**.

## 5. All `jwebserver` options you need to know

Syntax:

```text
jwebserver [-b bind-address] [-p port] [-d directory]
           [-o none|info|verbose] [-h] [-version]
```

| Flag | Value | Default and notes |
| --- | --- | --- |
| `-b`, `--bind-address` | Local network address | **Loopback** `127.0.0.1` or `::1`; safest for local testing |
| `-p`, `--port` | TCP port | `8000`; port must be available |
| `-d`, `--directory` | Document root path | Current working directory; should not be used if inside a repo containing secrets |
| `-o`, `--output` | `none`, `info`, `verbose` | `info` by default; `verbose` additionally logs headers/path |
| `-h`, `--help` or `-?` | Help | Displays usage, does not start the server |
| `-version`, `--version` | Version | Displays the tool version |

Scenarios:

```bash
# Serve only a test directory on loopback:
jwebserver -b 127.0.0.1 -p 8000 -d ./static-demo -o info

# Reduce logs when running tests:
jwebserver -b 127.0.0.1 -p 9000 -d ./static-demo -o none

# Observe additional HTTP headers and path in an environment WITHOUT secrets:
jwebserver -b 127.0.0.1 -p 8000 -d ./static-demo -o verbose

# Check version:
jwebserver -version
```

**Not recommended:**

```bash
# ANTI-PATTERN: server starts listening on all interfaces.
jwebserver -b 0.0.0.0 -p 8000 -d .
```

The command above can allow other machines on the network to access static files. When the current directory contains a source repo, credentials, unpublished documents, or CI-generated files, the data exposure risk is obvious. `-b 0.0.0.0` is **not** a production networking approach; if you truly need to share fixtures over LAN, obtain permission/approval, choose a clean directory, and use dedicated network controls. It is better to use a server with TLS/auth/firewall for remote access.

## 6. Self-testing GET, HEAD, and POST with an HTTP client

A normal GET request:

```http
GET /hello.txt HTTP/1.1
Host: 127.0.0.1:8000

```

If the resource exists, the server returns status `200 OK` along with the file's bytes and metadata such as `Content-Type`. If the resource is UTF-8 text, the client application should decode using the charset known from the fixture contract, rather than using `String.length()` as the byte size.

**HEAD** is a request that receives equivalent response headers **without a response body**:

```http
HEAD /hello.txt HTTP/1.1
Host: 127.0.0.1:8000

```

You may see response status `200` and header information, but **the client must not attempt to read a file body from HEAD**. A `Content-Length` in a HEAD response, if sent, may represent the body size of the corresponding GET, not the number of body bytes actually present in HEAD.

**POST/PUT/DELETE do not turn Simple Web Server into a writable file store**. With SimpleFileServer, methods other than GET and HEAD do not perform upload/data-modification operations like a REST API. In the section 8 test, `POST /hello.txt` returns `405`. The tool documentation allows `405` or `501` for unsupported requests; do not write tests asserting that every unknown method must return the exact same code.

| Request | Reasonable expectation | Meaning |
| --- | --- | --- |
| `GET /hello.txt` | `200` if present | Reads static bytes |
| `HEAD /hello.txt` | `200`, empty body | Checks metadata |
| `GET /missing.txt` | `404` | File does not exist |
| `GET /` | `200` + index if present | Root index file |
| `GET /assets/` | `200` + listing if no index | Directory listing can easily expose fixture names |
| `POST /hello.txt` | `405`/`501` depending on handling | Not an upload endpoint |
| `GET /private-key.pem` | Must not appear if outside public root | **Protect by not putting secrets in root** |

## 7. `SimpleFileServer` API: server, handler, and output filter

In the `jdk.httpserver` module, the `com.sun.net.httpserver.SimpleFileServer` class provides three static factories:

### 7.1. `createFileServer(...)`

```java
HttpServer server = SimpleFileServer.createFileServer(
        new InetSocketAddress("127.0.0.1", 0),
        documentRoot.toAbsolutePath(),
        SimpleFileServer.OutputLevel.NONE);
server.start();
try {
    int actualPort = server.getAddress().getPort();
    // Run localhost client tests.
} finally {
    server.stop(0);
}
```

*This is a code snippet inside a method that already has `Path documentRoot` and imports; it is not a standalone class. Section 8 has the complete program.*

Explanation:

- `InetSocketAddress("127.0.0.1", 0)` binds to loopback and asks the OS to pick an **ephemeral free port automatically**. After `start()`, read `server.getAddress().getPort()` to learn the actual port.
- `documentRoot.toAbsolutePath()` is important: the API requires `rootDirectory` to be **absolute**, existing, a directory, and readable. If invalid, it may throw `IllegalArgumentException`.
- `OutputLevel.NONE` does not print request logs, which is suitable when you want clean test stdout. You can use `INFO` or `VERBOSE` for debugging.
- `server.start()` starts serving; `server.stop(0)` stops the test in `finally`. For `HttpServer`, the parameter of `stop(delay)` is the number of seconds allowed to finish existing exchanges, **not** a port or a client timeout.
- A server created via this API is an **HTTP-only static server**; the code has no `SSLContext` or `HttpsServer`.

**Tip:** port `0` is very handy for integration tests running in parallel, avoiding hard-coding 8000 which easily collides. Do not assume the chosen port is the same across runs.

### 7.2. `createFileHandler(Path)`

When you already have an `HttpServer` and need to combine a static handler with a small endpoint:

```java
// Fragment, root is the absolute Path of the static directory.
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 0), 0);
server.createContext("/files/",
        SimpleFileServer.createFileHandler(root));

server.createContext("/health", exchange -> {
    try (exchange) {
        byte[] body = "OK".getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(200, body.length);
        exchange.getResponseBody().write(body);
    }
});

server.start();
```

*The snippet above requires importing `HttpServer`, `SimpleFileServer`, `InetSocketAddress`, and `StandardCharsets`, as well as calling `server.stop(0)` in an outer lifecycle-management block.*

Example of a handler mounted at `/files/`:

```text
GET /files/hi.txt -> file root/hi.txt
GET /health       -> "OK" response from custom HttpHandler
GET /hi.txt       -> does not match /files/ or /health, typically 404
```

These three outcomes were **individually tested with Java** in a compatible JDK environment.

**Note:** the ability to attach a custom handler to the same server does not turn `createFileHandler` into a framework with auth/TLS/rate-limits. Each custom context must define its own valid HTTP methods, status codes, body, request limits, and data protection. If the code is only for serving static fixtures, using `jwebserver` is simpler.

In addition, `HttpHandlers.handleOrElse(...)` can be used to choose between handlers based on a predicate. Use this only when there is a clear requirement; adding a PUT handler to a static server can accidentally open up file-writing capability if permissions are not thoroughly designed.

### 7.3. `createOutputFilter(...)`

```java
Filter logs = SimpleFileServer.createOutputFilter(
        System.out, SimpleFileServer.OutputLevel.VERBOSE);
HttpContext context = server.createContext("/files/",
        SimpleFileServer.createFileHandler(root));
context.getFilters().add(logs);
```

*This is a fragment in a context where the server/context is initialized, requiring imports for `Filter`, `HttpContext`, `HttpServer`, and `SimpleFileServer`.*

The filter is used for logging. **`createOutputFilter(..., OutputLevel.NONE)` is not a way to create a no-op filter**: the API specifies that it will throw `IllegalArgumentException` with `NONE`. If logging is not needed, **do not attach the filter**. On the other hand, `createFileServer(..., OutputLevel.NONE)` is a supported case for a server with no logging.

In `VERBOSE` mode, logs can include request/response headers and the absolute path of files. Do not enable verbose in environments with tokens, cookies, private URLs, or sensitive documents; logs are not a place for secrets.

## 8. Runnable Java example: checking all static behaviors over loopback

The following program creates a **temporary, isolated** document root, places a few fixture files in it, runs `SimpleFileServer` on port 0, uses `HttpClient` to check responses; then launches the **actual `jwebserver` command from the JDK** as a child process to test the CLI.

It does not modify the current repository, does not open any network interface outside loopback, and cleans up the test directory itself.

**Filename: `SimpleFileServerDemo.java`**

```java
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;
import com.sun.net.httpserver.SimpleFileServer.OutputLevel;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Comparator;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;

public final class SimpleFileServerDemo {
    static final HttpClient HTTP = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(2))
            .build();

    static HttpResponse<byte[]> request(URI uri, String method)
            throws IOException, InterruptedException {
        HttpRequest req = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3))
                .method(method, HttpRequest.BodyPublishers.noBody())
                .build();
        return HTTP.send(req, HttpResponse.BodyHandlers.ofByteArray());
    }

    static URI url(int port, String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    static int temporaryPort() throws IOException {
        try (ServerSocket socket = new ServerSocket(0, 10,
                InetAddress.getByName("127.0.0.1"))) {
            return socket.getLocalPort();
        }
    }

    static void probeApi(Path root) throws Exception {
        HttpServer server = SimpleFileServer.createFileServer(
                new InetSocketAddress("127.0.0.1", 0),
                root.toAbsolutePath(), OutputLevel.NONE);
        server.start();
        try {
            int port = server.getAddress().getPort();
            HttpResponse<byte[]> file = request(url(port, "/hello.txt"), "GET");
            String text = new String(file.body(), StandardCharsets.UTF_8);
            System.out.println("API GET: " + file.statusCode() + " " + text);
            System.out.println("API MIME: " + file.headers()
                    .firstValue("Content-Type").orElse("(none)"));

            HttpResponse<byte[]> head = request(url(port, "/hello.txt"), "HEAD");
            System.out.println("API HEAD: " + head.statusCode()
                    + " bodyBytes=" + head.body().length);

            HttpResponse<byte[]> rootIndex = request(url(port, "/"), "GET");
            System.out.println("API index: " + rootIndex.statusCode()
                    + " containsTitle=" + new String(rootIndex.body(),
                    StandardCharsets.UTF_8).contains("Test Page"));

            HttpResponse<byte[]> listing = request(url(port, "/assets/"), "GET");
            System.out.println("API listing: " + listing.statusCode()
                    + " hasJson=" + new String(listing.body(),
                    StandardCharsets.UTF_8).contains("data.json"));

            System.out.println("API missing: "
                    + request(url(port, "/not-found.txt"), "GET").statusCode());
            System.out.println("API POST: "
                    + request(url(port, "/hello.txt"), "POST").statusCode());
        } finally {
            server.stop(0);
        }
    }

    static void probeCli(Path root) throws Exception {
        int port = temporaryPort();
        String executable = System.getProperty("os.name")
                .toLowerCase().contains("win") ? "jwebserver.exe" : "jwebserver";
        Path binary = Path.of(System.getProperty("java.home"),
                "bin", executable);
        Process process = new ProcessBuilder(binary.toString(),
                "-b", "127.0.0.1", "-p", Integer.toString(port),
                "-d", root.toString(), "-o", "none")
                .redirectErrorStream(true).start();
        try {
            HttpResponse<byte[]> result = null;
            for (int i = 0; i < 50; i++) {
                try {
                    result = request(url(port, "/hello.txt"), "GET");
                    break;
                } catch (IOException notReady) {
                    Thread.sleep(60);
                }
            }
            if (result == null) {
                throw new IllegalStateException("CLI did not start");
            }
            System.out.println("CLI GET: " + result.statusCode() + " "
                    + new String(result.body(), StandardCharsets.UTF_8));
        } finally {
            process.destroy();
            if (!process.waitFor(2, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                process.waitFor(2, TimeUnit.SECONDS);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("static-fixture-");
        try {
            Files.writeString(root.resolve("index.html"),
                    "<h1>Test Page</h1>", StandardCharsets.UTF_8);
            Files.writeString(root.resolve("hello.txt"),
                    "Xin chào!", StandardCharsets.UTF_8);
            Path assets = Files.createDirectory(root.resolve("assets"));
            Files.writeString(assets.resolve("data.json"), "{\"ok\":true}",
                    StandardCharsets.UTF_8);
            probeApi(root);
            probeCli(root);
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder())
                        .toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

**Compile with JDK 18+** (JDK 24 was tested):

```bash
javac --release 18 --add-modules jdk.httpserver SimpleFileServerDemo.java
java --add-modules jdk.httpserver SimpleFileServerDemo
```

The `--release 18` flag targets the API surface introduced in JDK 18. If the Java runtime used to execute it is **older than 18**, the program still cannot run even if compiled with a newer JDK.

**Actual verified stdout:**

```text
API GET: 200 Xin chào!
API MIME: text/plain
API HEAD: 200 bodyBytes=0
API index: 200 containsTitle=true
API listing: 200 hasJson=true
API missing: 404
API POST: 405
CLI GET: 200 Xin chào!
```

### 8.1. Explanation of each check

**GET 200:** SimpleFileServer maps `/hello.txt` to the fixture file in `root`. Java `HttpClient` receives bytes, and the UTF-8 decoder is explicitly chosen. No need to write a custom handler reading `FileInputStream`.

**MIME text/plain:** the JDK's MIME table returns `Content-Type: text/plain` for `.txt` files. The MIME table may change across versions/implementations; do not use the extension as proof of content safety.

**HEAD 200 bodyBytes=0:** still checks that the resource exists, but the body is empty per HEAD semantics. This **does not prove `Content-Length: 0`**; a 0-byte body and the `Content-Length` header can express two different concepts.

**Index 200:** `root` has `index.html`, so `GET /` serves the index page instead of a directory listing.

**Listing 200:** the `assets` directory has no index, so the server generates a listing containing `data.json`. When using this tool, listing behavior can reveal file/directory names; do not put sensitive information in `root`.

**404:** a non-existent path does not succeed; tests should also check negative paths to avoid a frontend mistaking an HTML 404 response for expected JSON.

**POST 405:** the static server rejects POST; you cannot turn it into an upload server merely by sending `POST` from the client.

**CLI 200:** a separate `jwebserver` process is launched with loopback bind, fixture directory, and test port. `HttpClient` verifies that the CLI server actually returns data, and then the program stops the child process.

### 8.2. Limitations of the demo

- The test code uses **JDK 24** at runtime with **compile target JDK 18**; this is not a test of every version 18–24, every OS, or every filesystem.
- The server only serves **plaintext HTTP on loopback**. There is no TLS, auth, access control, rate limit, DDoS protection, or dynamic API support.
- `temporaryPort()` grabs a temporary port and closes the socket before the CLI binds: there is a **small race** if another program claims the port immediately afterward. In a simple test, the retry loop helps wait for startup but does not completely eliminate port conflicts.
- `probeCli` uses `ProcessBuilder` to access `jwebserver[.exe]` in `java.home/bin`, without modifying the system-wide `PATH`. If run on a custom runtime image **without this tool**, the CLI test is unavailable.
- `Process.destroy()` and `waitFor(...)` handle child-process cleanup; on other operating systems, wait times may need adjustment.
- `Files.walk(root)` deletes fixture files **just created by the program itself**. Do not copy this logic to delete a directory containing real data.
- The code does not enable logging, so stdout output is stable and does not print absolute paths/headers for every request.
- The assertions in stdout only verify **a local test path**, and do not prove production safety, supported features beyond scope, or high load.

## 9. Distinguishing `createFileServer` and `createFileHandler`

| Need | Choice | Why |
| --- | --- | --- |
| Share a few local files for frontend testing | `jwebserver` | No Java code needed |
| Test an HTTP client with self-created local fixtures | `SimpleFileServer.createFileServer(...)` | Has start/stop lifecycle and port 0 inside the test program |
| Already have an `HttpServer`, want to add a static path | `SimpleFileServer.createFileHandler(...)` | Only attaches a handler to the chosen context |
| Want to print per-request logs in tests | `OutputLevel.INFO/VERBOSE` or output filter | Observe requests/responses |
| Want to generate dynamic JSON by request ID, POST/PUT | Custom `HttpHandler` / dedicated test server | Static file server does not process business logic |
| Want to provide downloads with auth/TLS over the Internet | Dedicated web server / reverse proxy | Simple Web Server does not meet these requirements |
| Production service needing HTTP/2, TLS, metrics, rate limit | Appropriate production server | JEP 408 was not designed for that goal |

`createFileServer` returns an `HttpServer` object that can be configured further within the API's scope, but **the static handler part** still has the limitations of Simple Web Server. When custom routes or headers are needed, think clearly about scope: static fixtures can be served by the handler, while dynamic business logic is handled by custom handlers. **API extensibility does not turn the `jwebserver` CLI into a backend framework**.

## 10. The root directory must be kept separate from source code and sensitive documents

Common mistake: running `jwebserver` when the current directory is the project root:

```text
my-project/
  .git/
  .env
  config/
  src/
  target/
  secrets/
  README.md
```

Even though the Simple Web Server documentation states that hidden files and symbolic links are not served, **do not treat that as a security mechanism that lets you casually publish a repo root**. `README.md`, non-hidden config files, newly generated files, or arbitrary files placed by scripts can be exposed. A static test server mechanism is not a sandbox against every link, race, and filesystem change.

Instead, create:

```text
project/
  src/                 # real code: DO NOT serve
  .env                 # secret: DO NOT serve
  config/              # production config: DO NOT serve
  test-fixtures-public/
    index.html
    assets/
      demo.json         # dummy data, contains no personal information
```

Only run:

```bash
jwebserver -b 127.0.0.1 -p 8000 -d ./test-fixtures-public
```

**Path and permission rules:**

1. Root is a directory you intentionally designate and have read permission for.
2. Root contains **only** files permitted to be public within the test scope.
3. Avoid using `.` if unsure of the working directory; use `-d` explicitly.
4. Do not switch `-b` to all interfaces just to fix an inability to access from a container/VM without understanding the network topology.
5. If root contains data that users/third-party components are allowed to write to, do not rely on hidden-file/symlink behavior as a guarantee against all TOCTOU risks.
6. Do not use a static test server to transmit credentials over plaintext HTTP, even on the same LAN.
7. Shut down the server immediately after the test; restrict OS filesystem permissions so the server cannot read secrets outside the fixtures.
8. If the test serves HTML/JS files, remember the browser can execute JavaScript content in the server's localhost origin. Do not open untrusted HTML files and do not place sensitive endpoints on the same origin.

**Listening on loopback means:** only processes on the same host or the same appropriate network namespace can connect; it is **not** authentication. An untrusted application running on the same machine can still call `http://127.0.0.1:8000/` if the firewall/OS allows it. With containers/VMs, `localhost` is inside each environment's network namespace, not automatically the physical host's loopback.

## 11. Static MIME, encoding, and verifying received data

Simple Web Server has a basic MIME table: `.html` is usually `text/html`, `.txt` `text/plain`, and `.json` may be determined by the JDK's MIME table. However, when using it to test a client, separate:

- **File bytes**: the actual content read from the filesystem, not `String.length()`.
- **Content-Type**: the media type the server guesses from the extension/MIME table, which does not prove the file is parseable.
- **Charset**: for text, the client-side decoder must use the appropriate encoding; JSON files typically use UTF-8 per RFC 8259.
- **Content-Length**: when sent, counts bytes per HTTP semantics rather than UTF-16 code units.
- **HTTP status**: 200/404/405 indicates request-handling status, not semantic JSON/HTML validity.
- **Response version**: the server uses HTTP/1.1; do not mistake the client's `HttpClient.Version.HTTP_2` for the server having negotiated HTTP/2.

**Example client reading a JSON fixture:**

```java
// Fragment: client and uri are already initialized.
HttpResponse<String> response = client.send(
        HttpRequest.newBuilder(uri).GET().build(),
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

if (response.statusCode() != 200) {
    throw new IOException("Fixture unavailable");
}
String jsonText = response.body();
// Parse/validate JSON with a JSON library appropriate to the test.
```

This snippet is not a standalone class; it requires importing `HttpClient`/`HttpRequest`/`HttpResponse`, `IOException`, and `StandardCharsets`. **Do not use regex/string splitting to parse complex JSON** just because the file is served by a static server. Additionally, if the test response needs special headers (CORS, cache, auth, content-encoding), do not assume `jwebserver` automatically generates every exact header; use a custom handler or mock server capable of configuring responses.

## 12. Cache, CORS, Range, compression: do not assume full support

A dedicated static HTTP server may strongly support features such as conditional requests, compression, configurable cache headers, byte-range requests, or security headers. **Do not assume Simple Web Server provides all of those capabilities** just because it serves files successfully.

Tests that should be separated:

| Feature | If the test depends on it | Approach |
| --- | --- | --- |
| `ETag`, `If-None-Match`, `If-Modified-Since` | Need to verify spec-compliant caching | Observe actual headers/status or use a mock HTTP handler |
| `Cache-Control` | Want the browser not to cache old fixtures | Use an appropriate handler/proxy; do not assume the static server's cache policy |
| `Access-Control-Allow-Origin` | Different-origin frontend calling fetch | Need CORS response headers from a controlled server; static server may not provide them |
| `Range` / `206 Partial Content` | Testing download resume | Use a server with a verified Range implementation |
| `Content-Encoding: gzip` | Testing decompression and length | Produce properly encoded responses in a custom handler |
| `Authorization` and access control | Data with access permissions | Use a real server with authentication, not a public fixture server |
| HTTP/2/TLS ALPN | Testing performance/security protocols | Use another HTTP/2/HTTPS server; Simple Web Server is cleartext HTTP/1.1 |
| Dynamic JSON based on POST body | Mocking an API with logic | Custom `HttpHandler`, WireMock, or a test framework |

If the frontend reports a CORS error, running `jwebserver` successfully on port 8000 **does not** mean the server automatically added CORS headers for another origin. Do not mistake **CORS** for a server-side authentication mechanism: it is a browser script-control policy; non-browser clients can still send HTTP requests to loopback if they can connect.

If you need a specific header/behavior, **test with an HTTP client and observe the response** instead of documenting assumptions.

## 13. Logging: choose a level sufficient to observe without leaking data

Command-line configuration:

```bash
jwebserver -b 127.0.0.1 -p 8000 -d ./static-demo -o info
```

Distinction:

- **`none`:** prints no request logs. Useful for CI tests that need stable stdout.
- **`info`:** records basic request logs, enough to see URL/method/status.
- **`verbose`:** additionally logs request/response headers and the resource's absolute path, helpful for debugging but easily includes sensitive information.

If you run `jwebserver -o verbose` in an uncontrolled repo, you not only risk serving sensitive files, but also having paths, queries, or headers appear in the console/log pipeline. In applications with `Authorization`/`Cookie` headers, **do not log verbatim**. Enable verbose only when needed, on dummy fixtures, and then turn it off.

The `createFileServer(..., OutputLevel.INFO)` API supports similar log levels. If you have created a custom context and want a log filter, use `createOutputFilter(out, OutputLevel.INFO/VERBOSE)`; do not create a filter with `OutputLevel.NONE`.

## 14. Testing problem: static fixtures are not a dynamic mock API

Using a document root:

```text
fixtures/
  index.html
  api/
    users.json
    products.json
  assets/
    style.css
```

When testing a frontend:

```text
GET /api/users.json
  -> contents of fixtures/api/users.json

GET /api/products.json
  -> contents of fixtures/api/products.json

GET /api/orders
  -> no file, does not dynamically generate data
```

This is a **static stub**: useful when the response content is known in advance and the client only needs to read. If the test needs `POST /orders` to receive a body, validate input, generate an ID, or return status 201/409 conditionally, **SimpleFileServer is not the right choice**. Create a custom `HttpHandler` or use a dedicated mock server.

**When using fixtures for integration tests:**

1. Each test or test suite creates its **own root directory** to avoid overwriting each other.
2. Use port 0 in the API to avoid fixed-port collisions.
3. Write files with an explicit charset, such as `StandardCharsets.UTF_8`, so byte counts do not depend on the environment.
4. Have the client build the URI from the port just assigned to the server; do not hard-code 8000 if tests can run in parallel.
5. Check both success (200) and expected errors (404, unsupported method), not just the body.
6. Use `try/finally` to `stop(0)` the server and clean up test-created fixture files.
7. If you need to test the `jwebserver` CLI, run it in a tightly managed child process, terminate it in `finally`, and do not spawn lingering processes.
8. When testing auth/CORS/cache/Range, create a mock handler with **the exact behavior under test**, rather than "hoping" the default static server will behave like production.
9. Do not use real secrets in fixtures, even if the server only binds to loopback.
10. Ensure test code does not accidentally delete a user's directory: only delete directories created and owned by the test itself.

## 15. Differences between a static server and a custom `HttpServer`

Before JDK 18, a Java 17 lesson typically created an HTTP server like this:

```java
// Fragment illustrating Java 17: no automatic directory serving yet.
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 8000), 0);

server.createContext("/hello", exchange -> {
    try (exchange) {
        byte[] bytes = "Hello".getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(200, bytes.length);
        exchange.getResponseBody().write(bytes);
    }
});
server.start();
```

*Requires importing `HttpServer`, `InetSocketAddress`, and `StandardCharsets`, along with `server.stop(0)` cleanup. This is a fragment, with no runnable main/class.*

With `SimpleFileServer` from JDK 18, if you only want to serve `hello.txt`, you **do not need to manually resolve the URI path**, check path traversal/symlinks as in a manual handler, open `FileInputStream`, determine MIME, and generate directory listings. Using the built-in factory significantly reduces boilerplate.

However, do not infer that a manual custom handler is "safer" or that `SimpleFileServer` is already a security sandbox. Both require choosing network bind, directory, data, auth, and deployment policies appropriate to the environment.

### Is a Maven/Gradle dependency needed?

**No.** `jdk.httpserver` is a JDK module distributed in standard JDKs. With the `jwebserver` CLI, no build file is needed. With Java source using `SimpleFileServer`, JDK 18+ and a compiler/runtime with this module are required; use `--add-modules jdk.httpserver` in sample compile/run commands to make the dependency explicit.

If running in a custom runtime image created by `jlink`, the module or CLI tool may be absent depending on packaging. Do not assume a **minimal JRE** will contain `jwebserver`.

## 16. Troubleshooting common errors

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `jwebserver: command not found` | Older JDK or wrong PATH | Use JDK 18+, check `PATH/JAVA_HOME` |
| `cannot find symbol SimpleFileServer` | Java 17 build target or missing module | Compile with JDK 18+, `--release 18 --add-modules jdk.httpserver` |
| `UnsupportedClassVersionError` | Compiled with newer Java, run on older runtime | Align compile/runtime versions |
| `Address already in use` | Port 8000 is already used by another server | Pick another port or use port 0 in the API |
| Using `-d ./static-demo` and server returns 404 | Working directory differs from expectation or file is not in root | Check absolute path, fixture structure, and URI |
| `403`/file access permission error | Filesystem does not allow reading a resource | Fix fixture permissions; do not run as admin indefinitely |
| `GET /` returns listing instead of HTML | No matching index file | Place `index.html` in root |
| `GET /assets/` exposes filenames | Directory listing is the default behavior when index is missing | Use a clean root containing only test files |
| HEAD has no body | This is correct HTTP semantics | Do not read file bytes from HEAD |
| POST does not create a file | Static server only supports GET/HEAD | Use a custom handler/another service for writes |
| Frontend reports CORS | No header matching the frontend origin | Configure a mock server with CORS response headers |
| Browser caches old file | Cache behavior does not match test | Inspect HTTP headers, disable cache in dev tools, or use an appropriate endpoint |
| `https://localhost:8000` fails | Simple Web Server is plaintext HTTP | Use `http://` for local fixtures; use another server for HTTPS |
| Want HTTP/2 but client receives HTTP/1.1 | Simple Web Server does not support HTTP/2 | Choose another HTTP/2 server for ALPN tests |
| Cannot access from phone | Server binds to dev machine's loopback | Do not switch to 0.0.0.0 without understanding network and data sharing |
| Test hangs because server is still running | Forgot `stop(0)` or Ctrl+C | Manage lifecycle in `finally` |
| Verbose log leaks path/header | Log is too detailed | Reduce to info/none and use dummy fixtures |
| Hidden/symlink files behave unexpectedly | Filesystem/OS/implementation differences | Verify in practice; do not use the server as a sandbox |
| `createOutputFilter(..., NONE)` throws an error | This factory does not accept NONE | Do not create a filter when logging is not needed |

**Systematic diagnosis:** check JDK version → command help → bind address/port → document root → file existence/read permission → request method/path → HTTP status/content-type → stop server. Do not switch to a public network port or run with administrator privileges just to "make the error go away" before knowing the cause.

## 17. Performance and security testing: do not extrapolate from local to production

A minimal static server may suit a few requests from localhost, but should not be used to draw conclusions about:

- HTTP/2 multiplexing, TLS handshake, HTTP/3/QUIC.
- Caching/CDN/edge proxy systems, HTTP compression, complex conditional GETs.
- Load balancing or horizontal scaling.
- Authentication, authorization, personal data protection, and auditing.
- Rate limiting, quotas, body/header limits, and slow-client/DDoS protection.
- Ability to handle many connections and heavy traffic compared to production servers.
- Production logging/observability and graceful shutdown.
- Security headers, content sniffing, clickjacking protection, and CSP of real sites.

**JEP 408 chose minimalism by design.** The more production requirements you have, the more you should use a dedicated framework/container/reverse proxy. Using a learning tool within its proper scope makes tests more reproducible instead of introducing unnecessary risk.

## 18. Recommended test matrix

| Case | Setup | Check |
| --- | --- | --- |
| Static text | `hello.txt` UTF-8 | GET 200, correct body bytes |
| Static HTML | `index.html` | GET / returns index content |
| Directory listing | Subdirectory without index | GET /sub/ returns listing, does not accidentally expose private files |
| Unknown resource | Missing file | 404 |
| HEAD | Existing file | 200, empty body |
| POST | Attempt to POST file | 405 or 501, no file written |
| MIME | `.txt`/`.html` | Content-Type matching the MIME table |
| Nested file | `assets/data.json` | Path maps correctly within root |
| Port collision | Two servers both on 8000 | Second server fails; API port 0 is the test solution |
| Directory invalid | Non-existent/unreadable root | API rejects/CLI errors, does not serve another directory unintentionally |
| Hidden/symlink | Special OS resources | Verify not served outside root; do not treat as a security boundary |
| Unsupported protocol | HTTPS/HTTP2 | Must not assume the server supports them |
| Loopback | `-b 127.0.0.1` | Only local connections needed for learning/testing |
| Verbose log | `-o verbose` | No secrets in URL/header/fixture |
| Cleanup | API stop/CLI Ctrl+C | Process, port, and fixture files are cleaned up |
| Multiple tests | Port 0 + separate root | No state interference, runs independently |

If testing in CI, prefer **the API and port 0** over a CLI with hard-coded port 8000, because it avoids collisions and makes it easy to call `server.stop(0)`. Meanwhile, the `jwebserver` command is ideal for quick manual tasks and introducing static HTTP.

## 19. Practice exercises

**Exercise 1 — Version.** Why does a JDK 17 user get an error when compiling `SimpleFileServer.createFileServer(...)`? Which version and module must be used?

**Exercise 2 — jwebserver.** You have a `demo-public` directory containing only `index.html` and `hello.txt`. Write the command to serve it at `127.0.0.1:9000`, log level `info`, without opening all interfaces.

**Exercise 3 — HTTP methods.** A static server receives `POST /hello.txt`. Should this request be assumed to overwrite the file? What HTTP results are possible?

**Exercise 4 — Directory listing.** Why might `GET /assets/` return HTML containing filenames? How does this relate to the risk of publishing information?

**Exercise 5 — MIME.** If a file is named `report.json` but contains invalid HTML, does the extension-guessed `Content-Type` prove the payload is JSON?

**Exercise 6 — Loopback.** What can `jwebserver -b 0.0.0.0 -d .` do differently from `-b 127.0.0.1 -d ./static-demo`? Why shouldn't the first form be used in a repo?

**Exercise 7 — API.** When using `new InetSocketAddress("127.0.0.1", 0)`, how do you get the actual server port after startup? Why is this useful for tests?

**Exercise 8 — Output filter.** Do `createFileServer(..., OutputLevel.NONE)` and `createOutputFilter(..., OutputLevel.NONE)` have the same result?

**Exercise 9 — Composition.** You already have an `HttpServer` with a `/health` route and want to add static files at `/files/`. Which factory do you use and where do you attach it?

**Exercise 10 — Production.** A team wants to use `jwebserver` as a public download server with accounts, HTTPS, and rate-limits. Is it suitable? What architecture should they switch to?

**Exercise 11 — Testing.** Java `HttpClient` prefers HTTP/2, sends a GET to `jwebserver`, and `response.version()` is `HTTP_1_1`. Is this a bug?

**Exercise 12 — Cleanup.** Why shouldn't you write an integration test that creates files in a real user directory and then runs `Files.walk(...).forEach(delete)` in `finally`?

### Suggested answers

1. JEP 408 appeared in JDK 18, and Java 17 does not have `SimpleFileServer`; use JDK 18+ and the `jdk.httpserver` module.
2. `jwebserver -b 127.0.0.1 -p 9000 -d ./demo-public -o info`.
3. No. Only GET/HEAD are served; other methods receive 405/501 depending on context.
4. When a directory has no index, the server may generate a directory listing. You must serve a clean root directory without unpublished documents.
5. No. A guessed MIME type does not replace actual file content/validation.
6. `0.0.0.0` allows listening on all interfaces, and `.` may contain sensitive documents. Loopback + a public fixture directory significantly reduces scope.
7. `server.getAddress().getPort()`; OS-chosen port 0 avoids conflicts and enables parallel tests.
8. No. `createFileServer` accepts `NONE` for no logging, whereas `createOutputFilter` with `NONE` throws `IllegalArgumentException`.
9. Use `SimpleFileServer.createFileHandler(root)` then `server.createContext("/files/", handler)`.
10. No. Use a production server/reverse proxy with HTTPS/auth/authorization/rate limits and auditing.
11. No. `jwebserver` serves HTTP/1.1; a client preference does not force the server to use HTTP/2.
12. Because it could accidentally delete real data; use a dedicated temporary directory created by the test, verify ownership, and then clean up.

## 20. Official references

- [JEP 408 — Simple Web Server (JDK 18)](https://openjdk.org/jeps/408): goals, scope, and limitations of the tool.
- [Java SE 24 — SimpleFileServer](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): the three factories `createFileServer`, `createFileHandler`, `createOutputFilter`, and the absolute root requirement.
- [Java SE 24 — SimpleFileServer.OutputLevel](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.OutputLevel.html): NONE/INFO/VERBOSE.
- [JDK jwebserver command guide](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jwebserver.html): options, default loopback/port, GET/HEAD methods, and limitations.
- [dev.java — jwebserver tutorial](https://dev.java/learn/jvm/tool/jwebserver/): commands and usage scenarios.
- [Inside Java — Java 18's Simple Web Server](https://inside.java/2022/04/08/simple-web-server/): explains the differences between CLI and API.
- [Java SE 24 — HttpServer](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): lifecycle, context mapping, start/stop, port 0.
- [Java SE 24 — HttpClient](https://docs.oracle.com/en/java/javase/24/docs/api/java.net.http/java/net/http/HttpClient.html): performing HTTP requests in examples.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): GET, HEAD, status codes, Content-Type, and response semantics.
