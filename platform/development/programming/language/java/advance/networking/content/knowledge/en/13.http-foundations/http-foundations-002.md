# Method, Target URI, Headers, Status Code, and Body

## Lesson Objectives

HTTP (*Hypertext Transfer Protocol*) is an application-layer protocol for the **request/response** model. Reading an HTTP transaction properly means separating the request's **method**, **target URI**, and **headers/body**, while also reading the response's **status code** and **headers/body**. These components serve distinct roles: the method states the intent, the URI locates the resource, headers carry metadata and control information, the status describes the outcome at the protocol level, and the body is the representation or data being transmitted.

After this lesson, you will be able to:

- Read and write the structure of an HTTP/1.1 request/response; understand that these components still carry meaning in HTTP/2 and HTTP/3 even though the wire representation differs.
- Distinguish the semantics of `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE`, and `OPTIONS`; recognize that *safe* and *idempotent* are not synonymous.
- Identify target URI, path, query, authority, and fragment; understand HTTP/1.1 request-target forms and the meaning of `Host`/`:authority`.
- Use `Content-Type`, `Accept`, `Content-Length`, `Authorization`, `Location`, `Cache-Control`, and `ETag` properly; recognize that header names are case-insensitive.
- Explain status code classes `1xx` through `5xx`, especially common codes such as `200`, `201`, `204`, `301`, `304`, `400`, `401`, `403`, `404`, `405`, `409`, `415`, `429`, `500`, and `503`.
- Distinguish **payload body**, **representation metadata**, **byte length on the wire**, encoding, and message boundaries.
- Run a Java 17+ example with an HTTP server/client on loopback to observe method, target URI, headers, status, and response body.
- Avoid security/parsing pitfalls such as confusing query with body, parsing HTTP with arbitrary `readLine` calls, trusting `Host` unconditionally, logging tokens, or mishandling conflicting `Content-Length`/`Transfer-Encoding`.

**Scope:** HTTP foundations with HTTP/1.1 as an intuitive text representation; HTTP/2 and HTTP/3 preserve most semantics while using different framing and header compression. The Java example uses JDK 17 and does not require Internet access.

## 1. What Does an HTTP Exchange Consist Of?

At a conceptual level:

~~~text
Client                             Server
  │                                  │
  ├── HTTP Request ─────────────────►│
  │   Method + Target URI            │
  │   Header fields                  │
  │   (Body if any)                  │
  │                                  │
  │◄───────────────── HTTP Response ─┤
  │                    Status code   │
  │                    Header fields │
  │                    (Body if any) │
~~~

### Request in HTTP/1.1

An illustrative request example:

~~~http
POST /api/notes?notify=true HTTP/1.1
Host: example.org
Content-Type: application/json; charset=utf-8
Accept: application/json
Content-Length: 16

{"title":"Java"}
~~~

The lines above are shown with newlines for readability; **actual HTTP/1.1 uses CRLF** (`\r\n`) at the end of the start-line/header-lines and a blank line `\r\n` to terminate the header section. The body can be bytes of any format, not necessarily text.

Breakdown:

- `POST`: the request **method**.
- `/api/notes?notify=true`: the **request-target** in `origin-form`; consists of path and query.
- `HTTP/1.1`: the HTTP version of the start-line.
- `Host`: the target hostname/authority, especially important when one server serves multiple virtual hosts.
- `Content-Type`: the format of the **body the client is sending** — UTF-8 JSON in this example.
- `Accept`: the representation media type the client wants to receive.
- `Content-Length: 16`: there are **16 bytes** of payload in the ASCII example `{"title":"Java"}` (excluding the separating blank line); not the length of the entire request.
- Blank line after headers: marks the end of headers and the start of the body.
- `{"title":"Java"}`: the **request body** containing the representation of the content being sent, not a component of the URI.

Note: `Content-Length: 16` matches the **16 UTF-8 bytes** of the example string because all characters are ASCII. If the body contains Vietnamese characters/emoji, you must not use `String.length()` to populate the byte count.

### Response in HTTP/1.1

~~~http
HTTP/1.1 201 Created
Content-Type: application/json; charset=utf-8
Location: /api/notes/42
Content-Length: 14

{"id":42}
~~~

**The example above only illustrates syntax, not a `Content-Length` value to reuse:** the body `{"id":42}` is actually **9 bytes** long, so a valid HTTP/1.1 response must state `Content-Length: 9` (or use another valid framing mechanism). Look at the corrected example:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json; charset=utf-8
Location: /api/notes/42
Content-Length: 9

{"id":42}
~~~

In the response:
- `201` is the **status code** for the resource creation outcome.
- `Created` is an illustrative reason phrase in HTTP/1.1; **the code itself determines the semantics**. The reason phrase can change, and HTTP/2/3 do not carry a reason phrase in a text start-line.
- `Location` indicates the URI of the new resource, which may be a relative URI such as `/api/notes/42`.
- `Content-Type` describes the representation of the **response body**.
- The body `{"id":42}` is JSON returned by the application; it is not the HTTP status.

**Key takeaway:** method/URI/headers/status/body are **separate business and protocol concepts**. A server can return `404` along with a JSON body explaining the error; the body provides details, while the status conveys the standardized HTTP outcome.

## 2. Method: Intended Action and Semantics

An HTTP method is a token in the request, such as `GET` or `POST`. **Method names are case-sensitive** per the standard; you should use the standard all-uppercase form, not write `get` and assume it is equivalent.

| Method | Typical meaning | Request body? | Safe? | Idempotent? |
|---|---|---|---|---|
| `GET` | Retrieve a representation/state of a resource | No general semantics defined for content in a GET body; avoid using | Yes | Yes |
| `HEAD` | Like GET, but without transferring response content/body | Usually not needed | Yes | Yes |
| `POST` | Request the resource to process data according to its own semantics (create, action, etc.) | Usually present, **not required** | No | Not assumed by default |
| `PUT` | Create/replace the state of the target resource with the uploaded representation | Usually present | No | Yes |
| `PATCH` | Apply a set of partial changes to a resource | Usually present | No | **Not assumed by default** |
| `DELETE` | Request removal of the association/state of a resource per service semantics | Possible, no guaranteed general semantics | No | Yes |
| `OPTIONS` | Query communication options for a resource/server | Usually not needed | Yes | Yes |

**Safe** means the request is defined with the intent of **not requesting a state change** on the server as a primary business effect. A GET access can still produce logs, increment metrics, or record ad impressions by design; safe does not mean zero technical side effects.

**Idempotent** means multiple **identical** requests have the same *intended effect* on the server as a single request. It does **not** mean returning the same status/body:
- `PUT /settings/theme` sending the same representation twice leaves the same final state.
- `DELETE /items/42` may return `204` the first time and `404` the next; both remain consistent with idempotent semantics if the resource has already been deleted and no other mutating side action occurs.
- `POST /orders` sent twice may create two orders. If a service wants safe retries, it needs a mechanism such as an **idempotency key** and stored transaction state, rather than inferring from the POST name.

### Method Does Not Determine Route Success by Itself

A request `GET /users/42` has method GET and a target URI, yet the server can return `200`, `401`, `403`, `404`, `429`, or `500` depending on actual state. There is no rule that “GET is always 200, POST is always 201”.

You must separate **standard semantics** from the **API contract**:
- The HTTP standard defines the foundational meaning of methods, statuses, and fields.
- The API defines resources, request/response schemas, access permissions, and business rules.
- `PATCH` requires a clear patch format and conflict handling; not every server supports it.

**When a method is not supported by a resource**, use `405 Method Not Allowed` with `Allow` listing the methods supported by the contract. `501 Not Implemented` is different: the server does not recognize or support the functionality required to fulfill that method at the server level.

## 3. Target URI: Scheme, Authority, Path, Query, and Fragment

A URI can be decomposed as:

~~~text
https://api.example.org:8443/v1/notes/42?view=full&lang=vi#details
└─scheme─┘ └──authority────┘└─path─────┘└─query──────────┘└fragment┘
~~~

| Component | Example | Role |
|---|---|---|
| Scheme | `https` | Indicates the access method/outer protocol, typically HTTPS = HTTP over TLS |
| Authority | `api.example.org:8443` | Target host and port (port may be inferred from scheme) |
| Path | `/v1/notes/42` | Path to the resource defined by the API |
| Query | `view=full&lang=vi` | Additional parameters for the request target per application conventions |
| Fragment | `details` | Indicates a position/section within the resource, **not sent in the HTTP request target** |

**Fragment** is processed on the client/user agent side and is not part of the target URI sent in an HTTP request. If a Java `URI` contains `#details`, do not expect `HttpServer` to see `#details` in `getRequestURI()`.

### HTTP/1.1 Request-Target Forms

| Form | Example | Use case |
|---|---|---|
| **origin-form** | `GET /v1/notes?tag=java HTTP/1.1` | Common when a client sends a request to an origin server |
| **absolute-form** | `GET http://example.org/v1/notes HTTP/1.1` | Typically used for requests to an HTTP forward proxy |
| **authority-form** | `CONNECT example.org:443 HTTP/1.1` | Used with CONNECT to request establishing a tunnel |
| **asterisk-form** | `OPTIONS * HTTP/1.1` | OPTIONS targeting the server as a whole |

In origin-form, the scheme/host do not appear directly in the request-line, but the **Host** field indicates the request's authority; HTTP/1.1 clients are required to send `Host` per the standard. In HTTP/2 and HTTP/3, method/scheme/path/authority semantics are primarily represented via pseudo-headers such as `:method`, `:scheme`, `:authority`, and `:path` (depending on request type), **not** a text request-line.

### Query Is Not Body

`GET /search?q=java&limit=5` sends parameters in the **query** of the target URI; `POST /search` can send JSON in the **body**. Both can express similar intent if the API is designed that way, but at the protocol level they are completely different:
- Query is part of the target URI; it can appear in browser history, reverse-proxy logs, and analytics.
- Body is data in the message content and has its own `Content-Type`/`Content-Encoding`.
- Query parameters **do not have a single mandatory parser in core HTTP**: conventions around `&`, `=`, duplicate keys, and `+` are agreements at the URL/form/application level.
- Do not put access tokens, passwords, or sensitive personal data in the URI/query if avoidable; HTTPS protects data on the wire, but logs/history can still record URIs.

### Percent-Encoding and Raw/Decoded

URIs use percent-encoding to represent bytes—for example, space as `%20`, and `/` as segment data when encoded as `%2F`. Java `URI` provides raw/decoded pairs:

~~~java
URI uri = URI.create("https://example.org/a%2Fb?q=hello%20world");
System.out.println(uri.getRawPath()); // /a%2Fb
System.out.println(uri.getPath());    // /a/b
System.out.println(uri.getRawQuery()); // q=hello%20world
System.out.println(uri.getQuery());    // q=hello world
~~~

This is a **snippet** and requires importing `java.net.URI`. Do not decode multiple times or check permissions on the raw path and then route using a differently decoded path, because `%2F` can alter segment splitting and cause security bypasses. For form queries, `+` typically means space **when using `application/x-www-form-urlencoded`**; in URI paths and general queries, you must not arbitrarily replace every `+` with a space.

## 4. Headers: Request/Response Metadata

A header field in HTTP/1.1 is represented by a `Field-Name: field-value` line:

~~~http
Accept: application/json
Content-Type: application/json; charset=utf-8
Authorization: Bearer <redacted>
Cache-Control: no-store
~~~

The example above uses `<redacted>` to indicate a masked value to illustrate **not writing real tokens in articles or logs**.

**Header names are case-insensitive**: `Content-Type` and `content-type` refer to the same field name. Header values, however, have syntax/semantics that depend on the field; not every value is case-insensitive.

### Headers to Know

| Header | Request or response? | Role |
|---|---|---|
| `Host` | HTTP/1.1 Request | Target host/authority the client intends to access |
| `Accept` | Request | Media type of representation the client wants to receive |
| `Content-Type` | Both | Media type of the **body/representation sent in the current message** |
| `Content-Length` | Both when valid | Number of octets associated with the message content per HTTP framing rules |
| `Content-Encoding` | Both | Representation encoding such as `gzip`, not charset |
| `Authorization` | Request | Credentials sent by client to server; must be protected from logging/exposure |
| `WWW-Authenticate` | Response, especially `401` | Provides the authentication challenge |
| `Cookie` / `Set-Cookie` | Request / Response | HTTP-layer session/cookie state; often contains sensitive data |
| `Location` | Response, usually `201` or 3xx | URI of new resource or redirect target depending on status |
| `Cache-Control` | Both | Directives for caching, revalidation, and/or cache privacy |
| `ETag` / `If-None-Match` | Response / Request | Entity tag and conditional requests; can lead to `304` |
| `If-Match` | Request | Update precondition, often used to prevent lost updates |
| `Allow` | Response, especially `405` | Lists methods supported by the target resource |
| `Retry-After` | Response in some cases | Suggests how long to wait before retrying |
| `Vary` | Response | Request headers that affect representation selection when caching |

**`Accept` vs `Content-Type`:** request `Accept: application/json` says the client **wants to receive JSON**. Request `Content-Type: application/json` says the bytes **the client is sending** are JSON. Response `Content-Type: application/json` says the bytes **the server returns** are JSON. Do not swap the two meanings.

**`Content-Type` vs `Content-Encoding`:** `application/json; charset=utf-8` describes the media type and charset; `Content-Encoding: gzip` says the representation is gzip-compressed. If compressed, the receiver must handle content-coding before interpreting the representation according to its media type and charset.

**Repeated header fields:** some fields support list-combining, but **not all**. In particular, `Set-Cookie` must not be arbitrarily combined into a single comma-separated line; repeated or conflicting `Content-Length` headers can make a request/response invalid and dangerous. Do not parse HTTP headers by splitting on commas/colons without following the field's grammar.

**Size limits:** excessively long headers increase memory/CPU usage and may be rejected by servers/proxies. Production systems should enforce limits on total header bytes, number of fields, length per field, and handle invalid newlines to prevent header injection/smuggling.

## 5. Body: Content Bytes, Not a String by Default

An HTTP message **may or may not have content/body**. When a body is present, it is interpreted based on method/status and metadata:
- JSON: `Content-Type: application/json`.
- Plain text: `Content-Type: text/plain; charset=utf-8`.
- Form: `application/x-www-form-urlencoded`.
- Multipart: `multipart/form-data; boundary=...`.
- Binary: `application/octet-stream` or a specific media type.

Do not assume a `POST` request must have a JSON body, or that a `GET` request must have a body. **GET request content has no generally defined semantics in the HTTP standard** and should not be used to carry important business parameters; many proxies/clients do not handle it consistently.

### Byte Length, Not Character Count

In HTTP/1.1, when a body has a known length and `Content-Length` is valid, the value must be in **bytes**, not Java character count:

~~~java
String json = "{\"title\":\"Tiếng Việt\"}";
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
int length = bytes.length; // Number of UTF-8 bytes, do not use json.length().
~~~

This is a Java snippet and requires importing `java.nio.charset.StandardCharsets`. Characters like `ế`/`ệ` typically occupy multiple UTF-8 bytes while occupying a single UTF-16 code unit; emoji can occupy two UTF-16 code units and four UTF-8 bytes.

### Framing in HTTP/1.1

HTTP/1.1 needs to know **where the message content ends** so it can continue reading the next message on the same TCP connection. Key mechanisms:
- **Valid `Content-Length`** specifies the number of content octets, with specific rules for certain methods/statuses.
- **`Transfer-Encoding: chunked`** in HTTP/1.1 uses chunks with sizes in hexadecimal, terminated by a final size-0 chunk and optional trailer fields. Chunk sizes are wire framing, **not** part of the JSON body after decoding framing.
- Some legacy cases frame by closing the connection; however, you should not rely on EOF when you want persistent connections.
- **HTTP/2 and HTTP/3** use frame/stream semantics to delimit content, **not** HTTP/1.1 `Transfer-Encoding: chunked`. Do not manually add `Transfer-Encoding: chunked` to an HTTP/2 request.

**Avoiding request smuggling:** if a reverse proxy and backend disagree on `Content-Length`/`Transfer-Encoding`, they can split requests differently on the same byte stream. Always use a trusted HTTP parser/stack, configure proxy/server with aligned policies, and **reject ambiguous or malformed framing**. Do not write a production HTTP parser using a few `BufferedReader.readLine()` calls.

### Cases Where No Response Body Is Transmitted

- `HEAD`: the server returns headers reflecting GET, but **sends no response content**.
- Status `1xx`, `204 No Content`, and `304 Not Modified`: contain no response content per HTTP rules.
- A successful `CONNECT` transitions into a tunnel after an appropriate response, with special semantics.

Even though `204` has no body, application code may still want to set `ETag` or valid cache metadata. `304` is for conditional cache revalidation, not a synonym for a JSON body containing a “not modified” code.

The body of an **error response** can often contain useful error details, but it should not expose stack traces, secrets, passwords, or internal data to public clients.

## 6. Status Code: HTTP Outcome, Not Application Content

Every response has a **three-digit status code**. The first digit describes the class:

| Class | Name | Meaning |
|---|---|---|
| `1xx` | Informational | Provisional information during processing; e.g., `100 Continue`, `101 Switching Protocols` |
| `2xx` | Successful | Request was successfully processed per status semantics; e.g., `200`, `201`, `202`, `204` |
| `3xx` | Redirection | Need to use/check another URI or cache validation; e.g., `301`, `302`, `303`, `304`, `307`, `308` |
| `4xx` | Client Error | Cannot process the request due to a request/client-side condition per status definition; e.g., `400`, `401`, `403`, `404`, `405`, `409`, `415`, `429` |
| `5xx` | Server Error | Server encountered an error/cannot fulfill; e.g., `500`, `502`, `503`, `504` |

Commonly used statuses in practice:

| Status | Name | When to use / notes |
|---|---|---|
| `200 OK` | Success | Response has a representation appropriate to the method; GET typically returns a body |
| `201 Created` | Resource created | Can use `Location` pointing to the created resource |
| `202 Accepted` | Accepted for processing | Work may not be finished yet; needs a contract to track progress/result |
| `204 No Content` | Success with no content | Do not send a response body |
| `301 Moved Permanently` | Moved permanently | Points to the new target; clients/caches may handle redirects per policy |
| `302 Found` | Moved temporarily | Historical client differences in switching POST to GET; use `307`/`308` to preserve method/body |
| `303 See Other` | See another resource | Usually redirects to GET to view the result of a POST |
| `304 Not Modified` | No need to resend representation | Conditional cache validation; no body |
| `307 Temporary Redirect` | Temporary redirect, **preserves method/body** | Avoids turning POST into GET |
| `308 Permanent Redirect` | Permanent redirect, **preserves method/body** | Used when method semantics must be preserved |
| `400 Bad Request` | Malformed/invalid request | Invalid syntax/parameters/framing per server handling |
| `401 Unauthorized` | Missing valid authentication credentials | Somewhat misleading name; actually means **authentication required/failed**, often accompanied by `WWW-Authenticate` |
| `403 Forbidden` | Server refuses | Identity may be known, yet **not permitted**, or refused by policy |
| `404 Not Found` | Resource not found | Can also be used when the server does not want to reveal whether a resource exists |
| `405 Method Not Allowed` | Method not supported for resource | Response needs `Allow` describing permitted methods |
| `409 Conflict` | State conflict | E.g., version/state conflict, needing resolution before retry |
| `412 Precondition Failed` | Request precondition failed | E.g., `If-Match` mismatch, supporting optimistic concurrency |
| `415 Unsupported Media Type` | Request content format not supported | E.g., API expects JSON but receives another content type |
| `422 Unprocessable Content` | Content syntax understood, but cannot process per instructions | Often used for business validation per contract |
| `429 Too Many Requests` | Rate limit | Can send `Retry-After` to guide the client |
| `500 Internal Server Error` | Uncategorized server error | Do not return sensitive stack traces |
| `502 Bad Gateway` | Gateway/proxy received an invalid upstream response | Distinguish from the application server handling the request |
| `503 Service Unavailable` | Server temporarily unavailable/overloaded | Can include `Retry-After` |
| `504 Gateway Timeout` | Gateway/proxy waited too long for upstream | Not the same as a client read timeout in all cases |

**Status vs app business code:** a body `{"error":"OUT_OF_STOCK"}` can describe a business error, yet the HTTP status still needs accurate semantics. Do not return `200 OK` for every error and expect clients to always read the body to guess success.

**Status is not a security indicator by itself:** both `401` and `403` require proper login/permission handling; a `404` response does not replace backend permission checks. `5xx` can come from the server, upstream, or infrastructure depending on status and architecture.

## 7. Reading a Complete Request/Response

Example of a note-creation transaction:

~~~http
POST /notes HTTP/1.1
Host: api.example.org
Accept: application/json
Content-Type: application/json
Content-Length: 16

{"title":"Java"}
~~~

Response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /notes/42
Content-Length: 16

{"created":true}
~~~

Self-check:
- Request method `POST` is a request to process/create; the target URI is `/notes`.
- `Host` indicates the authority; `Accept` and `Content-Type` perform different jobs.
- The request body `{"title":"Java"}` is **16 ASCII bytes** long.
- Response `201` states a new resource was created; `Location: /notes/42` points to the resource location per the contract.
- The response body `{"created":true}` is also **16 ASCII bytes** long.
- If the client sends `Content-Type: text/plain` while the API only accepts JSON, a `415` response may be more appropriate than having the parser try to interpret it as JSON.
- If URI `/notes/missing` has no resource, `404` is appropriate; if `PATCH` is not supported on the route, `405` with `Allow` is helpful.

The wire examples above depict HTTP/1.1 text. In real operation, header ordering/capitalization, chunked vs. `Content-Length`, and connection management chosen by the HTTP library may vary while semantics remain the same.

## 8. Java 17+ Demo: HTTP Method, Target URI, Headers, Status, and Body

To test without depending on the Internet, use `com.sun.net.httpserver.HttpServer` (the standard JDK `jdk.httpserver` module) for a **loopback HTTP server**, and `java.net.http.HttpClient` for the client. The code forces the client to HTTP/1.1 to tie directly back to the text request/response examples in this lesson.

The demo includes:
- `GET /notes?tag=java` returning `200` and a JSON body.
- `POST /notes` sending a JSON body, returning `201`, header `Location: /notes/42`, and a JSON response.
- Any other route returns `404`; invalid query returns `400`; wrong `Content-Type` returns `415`; body exceeding the demo's limit returns `413`; any other method returns `405` and `Allow`.
- Only printing key parts of the response, avoiding reliance on header ordering or capitalization auto-generated by the HTTP stack.

Save the complete file as **`HttpPartsDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

public class HttpPartsDemo {
    private static void reply(HttpExchange ex, int status,
                              String json) throws IOException {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type",
                                    "application/json; charset=utf-8");
        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static void handle(HttpExchange ex) throws IOException {
        try {
            String method = ex.getRequestMethod();
            String path = ex.getRequestURI().getRawPath();

            if (!"/notes".equals(path)) {
                reply(ex, 404, "{\"error\":\"not found\"}");
                return;
            }
            if ("GET".equals(method)) {
                if (!"tag=java".equals(ex.getRequestURI().getRawQuery())) {
                    reply(ex, 400, "{\"error\":\"invalid query\"}");
                    return;
                }
                reply(ex, 200, "{\"items\":[\"java\"]}");
            } else if ("POST".equals(method)) {
                String type = ex.getRequestHeaders().getFirst("Content-Type");
                if (type == null || !type.equalsIgnoreCase("application/json")) {
                    reply(ex, 415, "{\"error\":\"unsupported type\"}");
                    return;
                }
                byte[] body = ex.getRequestBody().readNBytes(513);
                if (body.length > 512) {
                    reply(ex, 413, "{\"error\":\"too large\"}");
                    return;
                }
                // Demo receives bytes, does not parse/validate JSON.
                ex.getResponseHeaders().set("Location", "/notes/42");
                reply(ex, 201, "{\"created\":true}");
            } else {
                ex.getResponseHeaders().set("Allow", "GET, POST");
                reply(ex, 405, "{\"error\":\"method not allowed\"}");
            }
        } finally {
            ex.close();
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer server = HttpServer.create(
            new InetSocketAddress(loopback, 0), 0);
        server.createContext("/", HttpPartsDemo::handle);
        server.start();
        try {
            int port = server.getAddress().getPort();
            URI base = URI.create("http://127.0.0.1:" + port);
            HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1).build();

            HttpRequest get = HttpRequest.newBuilder(
                    base.resolve("/notes?tag=java"))
                .header("Accept", "application/json")
                .GET().build();
            HttpResponse<String> getResponse = client.send(
                get, HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));

            System.out.println("GET request: " + get.method()
                + " " + get.uri().getRawPath()
                + "?" + get.uri().getRawQuery());
            System.out.println("GET status: " + getResponse.statusCode());
            System.out.println("GET Content-Type: "
                + getResponse.headers().firstValue("Content-Type").orElse(""));
            System.out.println("GET body: " + getResponse.body());

            HttpRequest post = HttpRequest.newBuilder(
                    base.resolve("/notes"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                    "{\"title\":\"Java\"}", StandardCharsets.UTF_8))
                .build();
            HttpResponse<String> postResponse = client.send(
                post, HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));

            System.out.println("POST request: " + post.method()
                + " " + post.uri().getRawPath());
            System.out.println("POST status: " + postResponse.statusCode());
            System.out.println("POST Location: "
                + postResponse.headers().firstValue("Location").orElse(""));
            System.out.println("POST body: " + postResponse.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

### Compiling, Running, and Output

In a directory containing only the demo Java file:

~~~bash
javac -encoding UTF-8 HttpPartsDemo.java
java HttpPartsDemo
~~~

Verified stdout from running with Java on TCP loopback:

~~~text
GET request: GET /notes?tag=java
GET status: 200
GET Content-Type: application/json; charset=utf-8
GET body: {"items":["java"]}
POST request: POST /notes
POST status: 201
POST Location: /notes/42
POST body: {"created":true}
~~~

`HttpServer` binds port `0` on `127.0.0.1`, meaning the OS chooses an ephemeral free port and other machines cannot reach the listener over a public network interface. `server.stop(0)` closes the listener immediately after the test. In a custom runtime image you may need to include the `jdk.httpserver` module; standard JDK 17 runs directly with the commands above.

### Step-by-Step Explanation of the Program

1. **Creating the HTTP listener:** `HttpServer.create(new InetSocketAddress(loopback, 0), 0)` binds a dynamic port; `createContext("/", ...)` dispatches requests to the handler. This is an HTTP library—it does **not** force you to write a parser for `GET ... HTTP/1.1` by hand.
2. **Method and target URI:** `ex.getRequestMethod()` returns the method; `ex.getRequestURI().getRawPath()` is the raw path. The query is obtained via `getRawQuery()`, **not** mixed into the path. The demo compares the literal raw query `tag=java`, rather than acting as a general-purpose query parser.
3. **Headers:** `getRequestHeaders().getFirst("Content-Type")` reads the request header. The client's `.header("Accept", ...)` and `.header("Content-Type", ...)` serve different purposes; the server calls `set("Content-Type",...)` for the response.
4. **Request body:** `getRequestBody().readNBytes(513)` reads at most 513 bytes to enforce the illustrative **512-byte** limit; it does not decode fragments one by one or use `String.length()` to measure payload bytes. The demo **does not parse/validate JSON**, so do not use it as a production JSON API.
5. **Response status:** `sendResponseHeaders(status, bytes.length)` sends the code and length mechanism per the API; for the demo's non-empty body, the server writes the exact number of bytes and closes the response stream. Do not manually add an arbitrary `Content-Length` to `HttpClient`: the library handles wire framing.
6. **`201 Created` and `Location`:** the POST response includes the `Location: /notes/42` header; this is an example of a new resource, not proof that the server persisted anything to a database. The demo only produces static bodies and has no persistence.
7. **`HttpClient`:** `HttpRequest` defines method/URI/headers/body; `BodyPublishers.ofString` converts the request body to UTF-8 bytes; `HttpResponse.BodyHandlers.ofString` decodes the response text.
8. **Reading the response:** `statusCode()` retrieves the status; `headers().firstValue(...)` retrieves a header; `body()` returns the body. You should check the status **before** interpreting the body against a “success” schema.
9. **Resource cleanup:** the server is stopped in `finally`. The example runs a single JVM hosting both client and server, without depending on a public host or external network.

**Demo limitations:** there is no authentication/authorization, persistence, JSON schema validation, concurrency control, structured logging, or rate limiting. Moving to production requires an HTTP stack/framework with request/header size limits, timeouts, TLS, access control, and error handling. `HttpServer` only serves to illustrate the protocol components.

## 9. HTTP/1.1 vs. HTTP/2 and HTTP/3

**Core semantics remain stable:** method, target URI, header fields, status, and content exist across all three versions. The major change is **message framing on the wire**.

| Criterion | HTTP/1.1 | HTTP/2 | HTTP/3 |
|---|---|---|---|
| Common transport | TCP | TCP with TLS in common web deployments | QUIC over UDP |
| Wire message | Start-line + text headers + CRLF + body/framing | Binary frames/streams | QUIC streams + HTTP/3 frames |
| Method/status | Text request-line/status-line | Pseudo-headers `:method`, `:status` | Pseudo-headers with corresponding semantics |
| Authority/path | Host and request-target | `:authority`, `:scheme`, `:path` | Similar at the HTTP/3 layer |
| Header compression | Not required in HTTP/1.1 wire format | HPACK | QPACK |
| Multiplexing | No multiplexed streams per the HTTP/2 model | Multiple streams over one TCP connection | Multiple QUIC streams |
| Chunked transfer encoding | Present in HTTP/1.1 | Does not use `chunked` as message framing | Does not use `chunked` like HTTP/1.1 |

In HTTP/2/3, you will **not** find literal `HTTP/1.1 200 OK` on the wire. Instead, frames carry metadata/status such as `:status: 200`. Header field names in HTTP/2/3 are encoded/normalized per version rules (typically lowercase on the wire). This does not give an HTTP `POST` request a “different meaning” in application semantics.

In Java `HttpClient`, you can request a version via `.version(HttpClient.Version.HTTP_2)`, but **the actual version depends on negotiation/server**; check `HttpResponse.version()`. This lesson's example intentionally selects HTTP/1.1 because of the `HttpServer` demo and intuitive text structure—do not treat the example as evidence that HTTP/2/3 were tested.

## 10. Common Mistakes and Security Risks

| Mistake | Why it is wrong | How to fix |
|---|---|---|
| “GET always returns `200`.” | Status reflects the actual outcome | Handle 2xx/3xx/4xx/5xx |
| “POST always has a JSON body.” | Method does not define content format | Check `Content-Type`, contract, and length |
| “`Accept` describes the JSON the client sends.” | `Accept` describes what the client wants to **receive** | `Content-Type` describes the content being sent |
| “Query is also body.” | Query is in the target URI; body follows headers | Read `getRawQuery()` and the request body separately |
| “`#fragment` is sent to the server.” | Fragment is client-side, not in the request-target | Do not use fragments as server parameters |
| “The hostname in `Host` is always trustworthy.” | Clients can spoof Host; multiple proxies can alter it | Validate allowed hosts and trusted forwarding headers |
| “`String.length()` is `Content-Length`.” | UTF-8 byte length can be larger | Count encoded bytes; let the HTTP library handle framing |
| “Just `readLine` until EOF to parse HTTP.” | Binary bodies, chunked encoding, streaming, and pipelining are complex | Use a standards-compliant HTTP library |
| “`Transfer-Encoding` and `Content-Length` together are always harmless.” | Ambiguous framing between proxy/backend causes request smuggling | Use a trusted parser; reject conflicting HTTP/1.1 framing |
| “Header names are case-sensitive.” | Field names are case-insensitive | Use header lookup APIs instead of manual string comparison |
| “Every repeated header can be joined with commas.” | `Set-Cookie` and some other fields are exceptions | Follow each field's grammar |
| “`204` carries a normal JSON body.” | `204` carries no response content | Choose a status that allows content when a body is needed |
| “`401` means the user is logged in but lacks permission.” | `401` relates to **authentication**; `403` is typically refusal | Distinguish authn vs. authz |
| “`404` always proves the resource does not exist.” | Resources may be hidden by policy | Do not rely on 404 to infer full state |
| “`200` with an `error` body means the status is still right.” | HTTP status must reflect semantics | Use appropriate 4xx/5xx with an explanatory body |
| “With HTTPS, query tokens cannot leak.” | URIs can be recorded in logs/history/analytics | Avoid secrets in URLs; apply redaction |
| “`Content-Type: application/json` means the JSON body is guaranteed valid.” | Header is a declaration, not automatic validation | JSON parser + schema validation |
| “Retrying POST indefinitely is safe.” | POST is not idempotent by default | Idempotency keys and retry policies |
| “Swapping `301`/`302` is equivalent to `307`/`308` for POST.” | Redirect method/body semantics differ | Pick the right status and test clients |
| “No `Content-Length` means no body.” | Chunked or other framing may be used | Rely on the HTTP parser/semantics |
| “`HttpResponse.body()` is always JSON.” | Content may be error HTML, text, or binary | Check status and `Content-Type` before parsing |

### URI and Header Security

- Do not concatenate raw user input into `URI.create("https://host/" + userInput)` without encoding/validating. Characters like `?`, `#`, `/`, or percent escapes can alter path/query semantics.
- If the server/client fetches user-supplied URLs, check for **SSRF** risks: a URL can point to loopback, metadata services, private networks, or redirect to internal addresses. Enforce allowlists/resolution policies and inspect redirects per architecture.
- Do not use untrusted data from `Host`, `Forwarded`, or `X-Forwarded-Host` to generate sensitive redirect/callback URLs unless the source proxy and host policy are validated.
- Do not log verbatim `Authorization`, `Cookie`, `Set-Cookie`, or queries containing secrets; use redaction and control retention.
- Do not decode paths multiple times or apply authorization inconsistently before/after decoding. `%2F`, `%2E`, and normalization can cause route/path traversal if different layers process them differently.
- A response body received over the network is untrusted data; `Content-Type` does not prove a parser should trust the entire payload.

## 11. Checklist When Designing an HTTP Endpoint

Before releasing an endpoint, answer these in order:

1. **Method:** Are GET for reading, POST for processing/creating, PUT for replacing, PATCH for partial updates, and DELETE for deleting appropriate? Which requests are safe to retry?
2. **URI:** Does the resource have a clear path, clear query semantics, and consistent percent-encoding? Are secrets kept out of queries and server-side assumptions about fragments?
3. **Request headers:** Are `Content-Type`, `Accept`, authorization, and conditional/caching headers handled properly? Are unknown/invalid headers ignored or rejected consistently?
4. **Request body:** Is it needed or not; which media type; charset; byte limits; streaming and JSON/schema validation? Are incomplete bodies, wrong lengths, and timeouts handled?
5. **Response status:** Does it return `200`/`201`/`204` for success, `400`/`401`/`403`/`404`/`405`/`409`/`415`/`429` for corresponding errors, and `5xx` for server errors?
6. **Response headers:** Are `Content-Type`, `Location`, `Allow`, `Cache-Control`, and `ETag`/`Vary` sensible? Is sensitive content kept out of public caches?
7. **Response body:** Is the success/error format consistent, free of secrets/stack traces, accurate in byte length, and omitted on forbidden statuses/methods?
8. **Transport:** Are timeouts, TLS, header/body size limits, connection limits, and standards-compliant parsers/proxies in place to prevent request smuggling?
9. **Observability:** Are method/status/latency/bytes metrics tracked per route, logs redacted, and raw tokens/PII excluded from logs?
10. **Testing:** Have you tested wrong methods, percent-encoded queries, large request sizes, missing `Content-Type`, invalid bodies, expired authentication, concurrent updates, conditional requests, redirects, and retries?

Use status codes to describe the outcome; do not turn `status=200` into “everything is fine” when the application content has not been checked.

## 12. Practice Exercises

1. In the request `POST /users?notify=true` with header `Content-Type: application/json`, which parts are the method, target URI, header, and body? Where is `notify=true` located?
2. Why does `GET /search?q=java#results` not cause the server to receive `#results`?
3. Distinguish the meaning of `Accept: application/json` from `Content-Type: application/json` when both appear in a request.
4. A client sends `{"title":"Tiếng Việt"}`. Why cannot `String.length()` be used as `Content-Length`?
5. Give an example of an idempotent request where two submissions can return different statuses.
6. A `POST /notes` succeeds in creating resource `/notes/42`. Which status and header are appropriate? Is a body required?
7. A server receives `PATCH`, but the resource only allows `GET` and `POST`. Which status and header should be used?
8. One API returns `401`, another returns `403`. How do they typically differ?
9. A GET has `If-None-Match` matching the current `ETag`. Which status allows the cache to reuse the representation without sending a body?
10. When a server returns `204`, is it allowed to send a JSON body describing “success”?
11. Why is `Transfer-Encoding: chunked` appropriate framing for HTTP/1.1, but not framing for HTTP/2?
12. Why can conflicting parsing of `Content-Length`/`Transfer-Encoding` between a reverse proxy and backend create a request smuggling vulnerability?
13. In the Java demo code, what do `getRequestURI().getRawPath()` and `getRawQuery()` return for `GET /notes?tag=java`?
14. Try changing the demo's request to `GET /notes?tag=python`. According to the handler, what will the status/body be? Is this a TCP error?
15. Try changing the POST `Content-Type` to `text/plain`. What is the expected status and why?
16. HTTP/2 does not have the line `HTTP/1.1 201 Created` as wire text. Where does the status information reside?

**Key answers:** (1) method POST, target `/users?notify=true`, JSON header describes the body; (2) fragment is client-side; (3) Accept is what you want to receive, Content-Type is what you are sending; (4) `Content-Length` counts bytes after encoding; (5) DELETE returns 204 the first time and 404 the next without changing state; (6) `201` and optionally `Location`; (7) `405` with `Allow`; (8) authentication vs. permission refusal; (9) `304`; (10) no; (11) HTTP/2 is frame-based; (12) two layers can interpret request boundaries differently; (13) `/notes` and `tag=java`; (14) `400` + invalid query JSON, not a TCP error; (15) `415` because the server only accepts JSON in the demo; (16) `:status` pseudo-header.

## 13. Summary

- **Method** specifies the *intended operation*; distinguish safe and idempotent, and do not assign a fixed status to every method.
- **Target URI** identifies the resource; path/query are data distinct from the body; fragments are not sent to the server, and percent-encoding must be handled consistently.
- **Headers** carry metadata/control; `Accept` is the desired response type, `Content-Type` is the type being sent, and `Content-Length` is in **bytes**, not `String.length()`.
- **Status code** conveys HTTP outcome semantics: 2xx success, 3xx redirection/cache, 4xx request-side error, 5xx server/upstream error. The body can explain details but does not replace the status.
- **Body** is representation/content, which can be JSON/text/binary and does not always exist; HTTP parsers must handle framing properly, especially for HTTP/1.1.
- **Java 17:** `HttpRequest` builds method/URI/headers/body, `HttpResponse` returns status/headers/body; use an HTTP library instead of manually parsing HTTP bytes.
- **Security:** enforce byte limits, validate URI/host/headers, check auth, never log secrets, and avoid ambiguous framing between proxies and backends.

### References

- [RFC 9110 — HTTP Semantics: methods, request target, field values, status codes](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 9112 — HTTP/1.1: message syntax, framing, content length and chunked](https://www.rfc-editor.org/rfc/rfc9112.html)
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.html)
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114.html)
- [Oracle Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [Oracle Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html)
- [Oracle Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [Oracle Java SE 17 — HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html)
