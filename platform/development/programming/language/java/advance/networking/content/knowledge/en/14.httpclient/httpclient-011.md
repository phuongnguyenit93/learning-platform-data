# Redirect Policies NEVER, NORMAL, ALWAYS and the Previous Response Chain

## 1. Problem Statement and Objectives

When a Java application sends an HTTP request, the server may return status `301 Moved Permanently`, `302 Found`, `303 See Other`, `307 Temporary Redirect`, or `308 Permanent Redirect` along with a `Location` header to direct the client to another URI. The application must decide **whether to automatically send a new request to that URI**, according to **which policy**, and **how to record intermediate responses**.

Since Java 11, the `java.net.http` package provides `HttpClient` with the `HttpClient.Redirect` enum and the `HttpResponse.previousResponse()` method. The three policies supported in Java 17 are:

- **`NEVER`:** do not automatically follow redirects. The application receives the 3xx response to decide on its own.
- **`NORMAL`:** automatically follow valid redirects, **except HTTPS → HTTP** to prevent downgrading from a TLS-protected connection to plaintext.
- **`ALWAYS`:** automatically follow valid redirects including **HTTPS → HTTP**; requires evaluating security risks and application context.

A redirect does not erase all traces of previous requests: the final response can trace back through **intermediate responses** via `previousResponse()`. However, intermediate responses **do not retain the body** like the final response: `body() == null` for a response obtained from `previousResponse()`.

After this lesson, you should be able to:
1. State the default redirect policy of Java 17 `HttpClient` and when to choose each policy.
2. Distinguish a `3xx` returned directly from a `2xx` after multiple automatic redirects.
3. Correctly read `response.uri()`, `response.request().uri()`, `response.statusCode()`, and the `previousResponse()` chain.
4. Understand the effect of `301/302/303/307/308` statuses on the **HTTP method** and **request body**.
5. Know how to resolve a relative `Location` and avoid confusing `Location` with the requested URI.
6. Avoid HTTPS downgrade, redirects to untrusted hosts, SSRF, information leakage, and redirect loops.
7. Compile/run **Java 17+ examples on loopback** to verify cases without needing the Internet.

## 2. A Redirect Is an HTTP Response, Not a TCP Connection Error

A typical HTTP exchange:

```http
GET /old-path HTTP/1.1
Host: example.com

HTTP/1.1 302 Found
Location: /new-path
Content-Type: text/plain

Resource moved
```

The `302` response above **is still a valid HTTP response**. It suggests that the client send **a new request** to `/new-path`. A redirect is not a TCP retry at the transport layer, nor does it guarantee that the next request will succeed.

If the client automatically follows the redirect, the process may look like:

```text
GET https://example.com/old-path
  ↓
302 Location: /new-path
  ↓
GET https://example.com/new-path
  ↓
200 OK (body of the resource)

Application receives the final HttpResponse:
  statusCode() = 200
  uri() = https://example.com/new-path
  previousResponse() -> 302 response of /old-path
```

If the policy does not follow automatically:
- `statusCode()` may be `302`.
- `uri()` is the URI of the request that produced the `302` response, i.e., `/old-path`.
- `headers().firstValue("Location")` may contain `/new-path`.
- `previousResponse()` is normally empty because **there was no intermediate response from following a redirect** in this send.
- The body of the `302` response being returned directly to the caller **can be read** using the chosen `BodyHandler`.

**Important:** a successful `send()` call does not imply receiving status `200`. Statuses 3xx, 4xx, and 5xx are HTTP response content; the API does not turn them all into an `IOException` by default.

## 3. Three Redirect Policies in Java 17

| Policy | Automatically follows valid redirects? | HTTPS → HTTP? | When to use |
| --- | --- | --- | --- |
| `HttpClient.Redirect.NEVER` | No | Does not auto-follow | API clients needing target validation, raw 3xx retrieval, crawlers, security-sensitive |
| `HttpClient.Redirect.NORMAL` | Yes | **No** | Clients following normal redirects while blocking TLS downgrade |
| `HttpClient.Redirect.ALWAYS` | Yes | **Possible** | Only in controlled cases where target safety is well understood |

`NORMAL` differs from `ALWAYS` at the exact core point of the enum: **redirecting from an HTTPS URL to an HTTP URL**. Policies do not force a 304, 300, or a 3xx with missing/invalid `Location` to result in a new network request. Specific implementation rules, status codes, redirect limits, and security settings still determine whether a redirect can be executed.

### Scheme transition table

| From URL | To URL | NEVER | NORMAL | ALWAYS |
| --- | --- | --- | --- | --- |
| `http://a` | `http://b` | Do not follow | May follow | May follow |
| `http://a` | `https://b` | Do not follow | May follow | May follow |
| `https://a` | `https://b` | Do not follow | May follow | May follow |
| `https://a` | `http://b` | Do not follow | **Blocked** | May follow |

The "May follow" cells assume the server returns a **valid redirect response** and there are no separate barriers such as an invalid target URI, redirect limit, or I/O failure. It is not a guarantee that every request will succeed.

An important note: **`NORMAL` only blocks HTTPS → HTTP; it does not control the entire redirect target**. It can still follow `Location` to a different host, IP, or port. For URIs determined by users or untrusted remote servers, an allowlist and application policy are still needed.

## 4. The Default of HttpClient Is NEVER

According to the Java SE 17 documentation:
- `HttpClient.newHttpClient()` is equivalent to `HttpClient.newBuilder().build()` with default values.
- If the builder **does not call** `followRedirects(...)`, the default is **`HttpClient.Redirect.NEVER`**.
- `client.followRedirects()` returns the configured policy.

Example:

```java
HttpClient client = HttpClient.newHttpClient();
System.out.println(client.followRedirects()); // NEVER
```

This is a code snippet with `import java.net.http.HttpClient`, running inside an appropriate method. Do not infer that Java will auto-follow like a browser when the code lacks `followRedirects`. With a default `HttpClient`, a 302 response is still returned directly if there is no other handling.

How to specify it explicitly:

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
```

Once built, `HttpClient` is **immutable in configuration**. There is no `client.setFollowRedirects(...)` to change the policy for that same instance; another client must be created if a different policy is needed. A single client can be reused for many requests and shares its own connection resources.

## 5. NEVER: Receive 3xx to Decide Yourself

Choose `NEVER` when the application:
- Needs to display or log the exact original response from the origin.
- Is building an API gateway/proxy/crawler with its own redirect policy.
- Must inspect **scheme, host, port, resolved address, path** before sending a request to the new target.
- Needs to preserve the exact method/body or check auth/cookies on each hop.
- Does not want a remote server to automatically decide where the client connects next.

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/old"))
        .GET().build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());

System.out.println(response.statusCode());
System.out.println(response.headers().firstValue("Location"));
```

This is a **code snippet**; it requires imports `java.net.URI`, `java.net.http.*` and `throws IOException, InterruptedException` or exception handling. The program requires Internet access and a suitable demo endpoint, so **do not assert fixed stdout**.

If a `302` is encountered, the snippet prints `302` and the `Optional<String>` from `Location`. There is no automatic request to the location; the caller must choose whether to send another request.

**Do not confuse:** the `NEVER` policy does not forbid the program from **writing its own redirect code** afterward. It only disables the **automatic** follow feature in `HttpClient`.

## 6. NORMAL: Auto-Follow Redirects While Avoiding Downgrade from HTTPS to HTTP

`NORMAL` is a convenient choice for many applications that want to automatically follow ordinary redirects:

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .connectTimeout(Duration.ofSeconds(5))
        .build();
```

This is a code snippet; it requires importing `java.net.http.HttpClient` and `java.time.Duration`. Requests should still set `HttpRequest.timeout(...)` as needed.

Logical examples:
- `http://a.example/old` → `https://a.example/new`: allowed by the NORMAL policy.
- `https://a.example/old` → `https://b.example/new`: allowed by NORMAL **in terms of scheme direction**, but cross-host still needs evaluation.
- `https://a.example/old` → `http://a.example/new`: **NORMAL refuses to auto-follow the downgrade**. The application will see the intermediate 3xx if no valid follow is possible, depending on prior steps.

Why block downgrades? If already connected over HTTPS with proper certificate validation, a subsequent request over HTTP would send data **unprotected by TLS**; cookies/headers/body could be exposed on the network, depending on the outgoing request. Using `NORMAL` avoids a class of automatic downgrades.

**What NORMAL does not solve:**
- Does not verify that the redirect target belongs to an allowed host list.
- Does not restrict redirects to private IPs, loopback, cloud metadata, or internal services.
- Does not automatically guarantee that `Authorization`/`Cookie`/custom headers are handled according to the application's security policy.
- Does not prevent a server from logically creating an infinite redirect loop; the implementation has a retry/redirect limit, but the application must treat hitting the limit as a failure mode.
- Does not guarantee idempotency for requests with a body.

## 7. ALWAYS: Follow Redirects Including HTTPS to HTTP

`ALWAYS` allows auto-following more redirect paths than `NORMAL`; specifically, transitioning **HTTPS → HTTP** is what makes this policy require safety consideration:

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.ALWAYS)
        .build();
```

Example:

```text
GET https://shop.example/checkout
  ↓
302 Location: http://shop.example/checkout
  ↓ (ALWAYS may allow following)
GET http://shop.example/checkout
```

As soon as a user/application assumes the entire journey is HTTPS while the request is actually sent over HTTP, data can travel over an unencrypted network. Having seen a valid TLS certificate on the first hop does not protect the next hop. Do not rely on the name `ALWAYS` to conclude "redirects are safe in all cases".

When to consider `ALWAYS`? Usually only when:
- The environment is fully controlled, and the redirect target does not carry sensitive data.
- The protocol/application intentionally permits downgrading.
- There is clear network segmentation and security policy.
- The URIs and transfer of headers/method/body have been vetted.

For APIs containing tokens, sessions, personal information, or critical transactions, **`NEVER` combined with checked manual redirects** or `NORMAL` plus origin controls is usually more appropriate than `ALWAYS`. Using `ALWAYS` merely to "have fewer errors" is an unwarranted security trade-off.

## 8. Location Can Be a Relative Path

A server may return:

```http
HTTP/1.1 302 Found
Location: ../v2/items?page=2
```

This is a **relative URI-reference**, not an absolute URL. For a request to `https://api.example.com/v1/items/42`, Java's `URI.resolve(...)` can resolve the relative reference against the base URI; the specific result depends on the path structure and RFC 3986 rules.

Illustrative code snippet:

```java
URI source = URI.create("https://api.example.com/v1/items/42");
URI target = source.resolve("../v2/items?page=2");
System.out.println(target);
```

When run, target is `https://api.example.com/v1/v2/items?page=2` according to URI relative path resolution rules. This is only **syntactic resolution**, not verification that the target is safe.

Distinguish:
- `Location: /new` → absolute path on the same origin (if the base is a standard HTTP/HTTPS URL).
- `Location: https://other.example/new` → absolute URI to another host.
- `Location: ../new` → relative path based on the base location.
- `Location: //other.example/new` → network-path reference, inherits scheme but **changes host**.
- Missing, malformed, or unsupported-scheme `Location` → do not attempt to follow blindly.

During automatic redirects, `HttpClient` handles the redirect URI according to its implementation. When doing manual redirects, use `URI.resolve(...)` with the exact base of the **current response**, then validate the resolved absolute URI. Do not concatenate URL strings with `+` or assume that a location starting with `/` is inherently safe.

## 9. HttpResponse After the Client Has Auto-Redirected

A hypothetical chain:

```text
GET /start
   │
   └── 302 Location: /middle
          │
          └── 307 Location: /final
                 │
                 └── 200 OK + body "OK-final"
```

If the client auto-follows and completes:
- `response.statusCode() == 200`.
- `response.uri()` is the URI that produced the **final response**, e.g., `.../final`.
- `response.request().uri()` is the URI of the **request corresponding to the final response**, not necessarily the initiating request passed to `send(...)`.
- `response.headers()` are the headers of the final response, not an aggregated set of headers from all hops.
- `response.body()` is the body of the **final response** according to the chosen `BodyHandler<T>`.
- `response.previousResponse()` may contain the response from the previous hop, e.g., 307.
- Calling `previousResponse()` again on the 307 response may yield the 302 response, etc.

A table viewing data after following twice:

| Object | `statusCode()` | `uri().getPath()` | `body()` |
| --- | ---: | --- | --- |
| Main response received by caller | `200` | `/final` | `"OK-final"` |
| `response.previousResponse().get()` | `307` | `/middle` | **`null`** |
| `response.previousResponse().get().previousResponse().get()` | `302` | `/start` | **`null`** |

For this reason, **do not infer the hop count from the final status**. Looking only at `200` does not tell you where the endpoint redirected from or whether it passed through another host. When auditing is needed, collect the chain of each intermediate response.

## 10. previousResponse() Is a Linked Chain, Not a List

Signature in Java 17:

```java
Optional<HttpResponse<T>> previousResponse()
```

The method returns:
- `Optional.empty()` if **there is no preceding intermediate response**.
- `Optional<HttpResponse<T>>` containing the most recent intermediate response if present; it in turn has `previousResponse()`.
- Intermediate responses may appear due to **redirection or authentication**, not just redirects.

Therefore `previousResponse()` is **not** a `List<HttpResponse<?>>`, nor does it automatically report the entire "history of all requests in the client". It only describes intermediate responses related to **one completed HTTP exchange**.

A safe traversal approach:

```java
Optional<HttpResponse<String>> cursor = response.previousResponse();
while (cursor.isPresent()) {
    HttpResponse<String> previous = cursor.get();
    System.out.println(previous.statusCode()
            + " " + previous.uri()
            + " Location=" + previous.headers()
                    .firstValue("Location").orElse("-"));
    cursor = previous.previousResponse();
}
```

This is a code snippet where the variable `response` is an existing `HttpResponse<String>`. This loop walks **from most recent to oldest**:
- The final `200` response does not belong to the `previousResponse` chain; it is in `response`.
- The closest hop may be `307 /middle`.
- The further hop may be `302 /start`.
- At the end of the chain, `Optional.empty()` terminates the loop.

Do not use `while (response.previousResponse().isPresent())` without updating the cursor; that will loop infinitely on the same response object.

## 11. Intermediate Response Bodies Are Discarded, Not Retained

According to Java 17 `HttpResponse.body()`: **if an HttpResponse is returned from `previousResponse()`, `body()` returns `null`**. This holds true even when the server sent a real body in the 302/307 response.

Why? Automatic redirect needs to handle the body of hops to continue the exchange and does not provide it to the application as the final response's body. Metadata such as `statusCode`, `headers`, `uri`, and `request` still support inspecting the chain, but **you cannot use `previousResponse().get().body()` to retrieve the raw payload of a redirect**.

Two different scenarios:

```text
Redirect.NEVER:
  server 302 + body "redirect-body"
  caller receives 302 response directly
  response.body() == "redirect-body"  (with BodyHandlers.ofString)

Redirect.NORMAL:
  server 302 + body "redirect-body", then 200 + body "OK-final"
  caller receives 200 response
  response.body() == "OK-final"
  response.previousResponse().get().body() == null
```

**Do not confuse `null` with the empty string `""`.** `null` on an intermediate body is part of the API specification; it does not necessarily mean the server sent an empty body. If auditing strictly requires keeping the body content of each hop, follow manually with `NEVER` and an appropriate `BodyHandler` to collect it before deciding the next request, with size/timeout limits because remote bodies can be large.

## 12. Runnable Java 17+ Example: NEVER, NORMAL, ALWAYS and 302 → 307 → 200 History

The following program creates a local HTTP server using `com.sun.net.httpserver.HttpServer` and uses `java.net.http.HttpClient` to send requests on **127.0.0.1**. No Internet, public DNS, or TLS certificates are required. The program demonstrates:
- `NEVER` stops at `302`, preserves the initial redirect body, and has no `previousResponse`.
- `NORMAL` and `ALWAYS` on an **HTTP → HTTP path** both follow two redirects to receive `200`.
- `previousResponse()` gives the chain `307 /middle` then `302 /start`, with the body at each hop equal to `null`.
- `HttpResponse.request().uri()` is the final URI.
- How statuses 301/302/303/307/308 affect `POST`.

**Note:** the local demo uses **plaintext HTTP on loopback** solely to test redirects; it **does not** demonstrate sending credentials over HTTP or prove HTTPS → HTTP policy behavior over a real network. The `NORMAL`/`ALWAYS` difference regarding downgrades is described from the API contract itself in sections 3, 6, and 7.

Save with the exact name **`RedirectPolicyDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class RedirectPolicyDemo {
    private static void reply(HttpExchange exchange, int code, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(code, bytes.length);
        try (var output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    private static void redirect(HttpExchange exchange, int code, String target)
            throws IOException {
        exchange.getResponseHeaders().add("Location", target);
        reply(exchange, code, "redirect-body");
    }

    private static String history(HttpResponse<String> response) {
        List<String> hops = new ArrayList<>();
        Optional<HttpResponse<String>> previous = response.previousResponse();
        while (previous.isPresent()) {
            HttpResponse<String> hop = previous.get();
            hops.add(hop.statusCode() + "@" + hop.uri().getPath()
                    + "(body=" + hop.body() + ")");
            previous = hop.previousResponse();
        }
        return hops.isEmpty() ? "-" : String.join(" <- ", hops);
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/start", e -> redirect(e, 302, "/middle"));
        server.createContext("/middle", e -> redirect(e, 307, "/final"));
        server.createContext("/final", e -> reply(e, 200, "OK-final"));
        for (int status : new int[]{301, 302, 303, 307, 308}) {
            int code = status;
            server.createContext("/post" + code,
                    e -> redirect(e, code, "/echo"));
        }
        server.createContext("/echo", e -> reply(e, 200,
                e.getRequestMethod() + ":" +
                new String(e.getRequestBody().readAllBytes(),
                        StandardCharsets.UTF_8)));
        server.start();

        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort());
            System.out.println("default=" +
                    HttpClient.newHttpClient().followRedirects());

            for (HttpClient.Redirect policy : HttpClient.Redirect.values()) {
                HttpClient client = HttpClient.newBuilder()
                        .followRedirects(policy)
                        .connectTimeout(Duration.ofSeconds(3))
                        .version(HttpClient.Version.HTTP_1_1)
                        .build();
                HttpRequest request = HttpRequest.newBuilder(
                        base.resolve("/start"))
                        .timeout(Duration.ofSeconds(5))
                        .GET().build();
                HttpResponse<String> response = client.send(
                        request, HttpResponse.BodyHandlers.ofString());
                System.out.println(policy + ": status=" + response.statusCode()
                        + " uri=" + response.uri().getPath()
                        + " request=" + response.request().uri().getPath()
                        + " body=" + response.body());
                System.out.println("  previous=" + history(response));
            }

            HttpClient client = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NORMAL)
                    .build();
            for (int status : new int[]{301, 302, 303, 307, 308}) {
                HttpRequest request = HttpRequest.newBuilder(
                        base.resolve("/post" + status))
                        .timeout(Duration.ofSeconds(5))
                        .POST(HttpRequest.BodyPublishers.ofString("payload"))
                        .build();
                HttpResponse<String> response = client.send(
                        request, HttpResponse.BodyHandlers.ofString());
                System.out.println("POST " + status + " -> "
                        + response.body() + " previous="
                        + response.previousResponse()
                                .map(HttpResponse::statusCode).orElse(-1));
            }
        } finally {
            server.stop(0);
        }
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac RedirectPolicyDemo.java
java RedirectPolicyDemo
```

Stdout verified with `javac --release 17` and executed:

```text
default=NEVER
NEVER: status=302 uri=/start request=/start body=redirect-body
  previous=-
ALWAYS: status=200 uri=/final request=/final body=OK-final
  previous=307@/middle(body=null) <- 302@/start(body=null)
NORMAL: status=200 uri=/final request=/final body=OK-final
  previous=307@/middle(body=null) <- 302@/start(body=null)
POST 301 -> GET: previous=301
POST 302 -> GET: previous=302
POST 303 -> GET: previous=303
POST 307 -> POST:payload previous=307
POST 308 -> POST:payload previous=308
```

### Reading the output

1. `default=NEVER` confirms that without calling `followRedirects`, the default is not to follow.
2. `NEVER` preserves status 302 and the server's `redirect-body` because this response is returned **directly**.
3. On the test path using only `http://127.0.0.1`, `NORMAL` and `ALWAYS` behave identically: follow `302`, then `307`, and finally `200`.
4. `uri=/final` and `request=/final` show that the final response belongs to the post-redirect request, not the initial URI `/start`.
5. `previous=307@/middle... <- 302@/start...` is ordered **from most recent to oldest**. The body of each intermediate response is `null` even though the server sent `redirect-body`.
6. With `POST`, 301/302/303 change to `GET` in the tested Java 17 implementation; 307/308 preserve `POST` and send the `payload` body to `/echo`.
7. `server.stop(0)` stops the local server when finished. The port is an ephemeral port assigned by the OS, but stdout only prints path/status to avoid depending on the port number.

### Why does ALWAYS appear before NORMAL?

`HttpClient.Redirect.values()` in Java 17 returns enum constants in declaration order: `NEVER`, `ALWAYS`, `NORMAL`. This is the enum declaration order, **not a security recommendation ranking**.

### Limitations of the example

- Testing over local HTTP **does not distinguish NORMAL and ALWAYS on HTTPS downgrade**; the policy table in section 3 is the authoritative API rule.
- `HttpServer` is an example/test server, not representative of a production server.
- There is no authentication, cookies, proxy, cross-host redirects, or HTTPS certificates; those scenarios require separate, controlled testing.
- Uses `HttpResponse.BodyHandlers.ofString()` for small bodies. For large/untrusted bodies, streaming, size limits, and timeouts are required.
- JDK/provider/network conditions may cause a loopback demo to fail if socket binding is not permitted or blocked by a special security policy. That does not change the semantics of the API.

## 13. HTTP Method and Request Body on Redirect

Redirects affect more than just the URI. The **request method** and **body** may change depending on the status code and implementation.

| Status | Common meaning | When Java 17 auto-follows a POST in the example |
| --- | --- | --- |
| `301 Moved Permanently` | Resource moved permanently | **POST → GET**, does not resend original body |
| `302 Found` | Temporarily moved (historically clients changed method) | **POST → GET**, does not resend original body |
| `303 See Other` | Points to another resource to retrieve the result | **POST → GET** |
| `307 Temporary Redirect` | Temporarily moved, must preserve method | **POST remains POST**, resends body when possible |
| `308 Permanent Redirect` | Moved permanently, must preserve method | **POST remains POST**, resends body when possible |

According to Java SE 17 `HttpClient.Redirect`, when an automatic redirect occurs, the method **may be adjusted** according to the 30x status; specifically `301` and `302` turn **POST into GET**. The `303/307/308` rows in the table are verified by the local code and align with the HTTP semantics of those statuses.

Do not conclude that:
- `307`/**`308`** will always retry successfully. The body publisher may not support replay, I/O may fail, or the redirect limit may block it.
- `301`/`302` always preserve the body; in Java 17 POST changed to GET in the demo.
- Every custom method behaves identically to POST; you must test against the specific API and status.
- Redirecting a request with business side effects is always safe. The server may have already processed the initial POST before redirecting or retrying; the application must manage idempotency.

### When are 307/308 useful?

If an endpoint wants to change the URL **without changing the method**, 307/308 are more suitable than 302 for many API operations. However, note body retry/resend:
- With `BodyPublishers.ofString(...)`, the data can be replayed conveniently.
- With a one-shot publisher reading from an input stream/network or a stateful source, you must check whether the publisher **can be re-subscribed/replayed**.
- Do not automatically replay large requests, sensitive uploads, or state-changing transactions without clearly defined behavior and limits.

**Practical recommendation:** servers should return 307/308 when wanting to explicitly preserve the method; clients should check the URI, body replay policy, and transaction semantics before following.

## 14. previousResponse() Does Not Mean "All Requests Sent"

There are at least four different kinds of history to distinguish:

1. **Initiating request:** the `HttpRequest` object that the caller passed to `send(...)` or `sendAsync(...)`. It still exists in the local variable you hold.
2. **Final response:** the `HttpResponse<T>` that the caller receives after the client handles redirects and authentication per configuration.
3. **Intermediate responses:** the `previousResponse()` chain if there were redirects/authentication before the final response.
4. **Application trace/log:** a list recorded by the application itself for each user operation/correlation ID. It may span multiple independent `send(...)` calls and business-layer retries.

`previousResponse()` only covers category **3** within the scope of that single HTTP exchange. It **does not**:
- Report previous completely unrelated requests made by an `HttpClient`.
- Record every network packet, DNS resolution, or TCP retry.
- Guarantee inclusion of all application retries if you call `send` multiple times yourself.
- Contain the full response bodies of redirect hops.
- Replace distributed tracing across reverse proxies/CDNs/backends.

When tracing a redirect chain is needed, store the initiating URI along with the final URI, final status, number of intermediate hops, each status/Location, response duration, and an application-defined correlation ID. Do not log only the final 200.

## 15. Retrieving the Chain in Chronological Order, Not Reversed

The `previousResponse()` method starts from the response **closest to the final one**. Given the chain:

```text
/start (302) → /middle (307) → /final (200)
```

Traversing `previousResponse` from final will yield:
1. `307 /middle`
2. `302 /start`

If you want to log in the order requests actually occurred, collect them and reverse the list:

```java
List<HttpResponse<String>> intermediates = new ArrayList<>();
Optional<HttpResponse<String>> cursor = finalResponse.previousResponse();
while (cursor.isPresent()) {
    HttpResponse<String> hop = cursor.get();
    intermediates.add(hop);
    cursor = hop.previousResponse();
}
Collections.reverse(intermediates);

for (HttpResponse<String> hop : intermediates) {
    System.out.println(hop.statusCode() + " " + hop.uri());
}
System.out.println(finalResponse.statusCode()
        + " " + finalResponse.uri());
```

This is an **illustrative code snippet**; it requires imports `java.util.ArrayList`, `java.util.Collections`, `java.util.List`, `java.util.Optional`, and `java.net.http.HttpResponse`; `finalResponse` is an existing `HttpResponse<String>` result.

For the local example, the desired log order is `302 /start`, `307 /middle`, `200 /final`. If intermediate responses due to authentication appear, the list may also contain non-3xx statuses. When logging, **do not print Authorization, Set-Cookie, tokens, or sensitive query parameters** indiscriminately.

## 16. request().uri(), uri(), and Location Have Different Roles

API questions:

| API | Returns | When redirected |
| --- | --- | --- |
| `initiatingRequest.uri()` | URI originally sent by caller | Still the original URI of the object you hold |
| `finalResponse.request().uri()` | URI of the HttpRequest for the final response | Usually the URL after redirects |
| `finalResponse.uri()` | URI of the final response | The URI from which the final response was received |
| `finalResponse.headers().firstValue("Location")` | Location header of the **final response** if present | Usually empty when final is 200 |
| `finalResponse.previousResponse().get().uri()` | URI of the most recent intermediate response | E.g. `/middle` |
| `hop.headers().firstValue("Location")` | Location advertised by an intermediate hop | E.g. `/final` |

A common mistake:

```java
System.out.println(response.headers().firstValue("Location"));
```

on a final `200` response after a redirect. You will not see the `302`'s Location because `response.headers()` belongs to the **final response**. You must walk `previousResponse` to inspect intermediate 3xx headers.

Another mistake: using `response.request().uri()` as the "starting origin". It may have changed after automatic redirects. If both original and final are needed, **keep the `HttpRequest original` variable when sending**.

## 17. Redirecting Over HTTPS: Policy and Security Layers

Suppose:
- Initial URI: `https://login.example.com/session`.
- Server returns: `302 Location: http://login.example.com/session`.

Per the Java 17 enum:
- `NEVER`: returns the `302` response; does not send a follow-up request.
- `NORMAL`: **does not auto-follow** because it is HTTPS → HTTP.
- `ALWAYS`: allows automatic following down to HTTP if the redirect is valid and there are no other obstacles.

Why care? Plaintext HTTP lacks confidentiality/integrity/endpoint authentication like HTTPS/TLS. URLs, queries, headers, or bodies sent to an HTTP endpoint can be observed or modified by network actors, depending on conditions. The risk increases if tokens, cookies, sessions, or personal information accompany the new request.

**Important statement:** `ALWAYS` is only an auto-follow policy; it **does not** specify or guarantee how the client will resend all headers, cookies, and body. Credential forwarding rules depend on implementation, request, and authentication/cookie configuration. Do not rely on assuming "Java will automatically strip all secrets", nor assume Java sends all secrets verbatim. For sensitive cases, test and **set an explicit policy**.

### Is using NORMAL enough to be safe?

No. `NORMAL` can follow a redirect `https://api.example.com` → `https://evil.example`, still over HTTPS but **changing the target host**. The TLS certificate of `evil.example` may be completely valid for that name; the issue is **whether the application is authorized to send data to that host**, not an invalid certificate.

Therefore, for clients fetching data from URLs controlled by third parties, use `NEVER` and validate each step or use a wrapper with a strict redirect policy. Do not treat TLS as a substitute for an allowlist.

## 18. Redirects, Credentials, and Cross-Origin

A redirect can change:
- **Scheme:** `http` / `https`.
- **Hostname/IP:** from the requested machine to another machine.
- **Port:** from 443 to 8443 or another port.
- **Path/query:** from one endpoint to another, potentially changing data semantics.
- **User identity/cookies/authentication scope:** differs across origins and domains.

A client carrying `Authorization: Bearer ...`, Cookies, or custom internal headers needs explicit decisions on:
- Is following a redirect to another host allowed?
- When changing host/port, should Authorization be kept or stripped/changed?
- Can cookies from CookieHandler be sent to the matching domain per cookie rules?
- Is sending a POST body to an endpoint outside the allowlist acceptable?
- Is a query string containing secrets being sent to a Location chosen by the remote server?

Do not rely on the single enum `Redirect.NORMAL` to handle everything. `NORMAL` **is only a basic redirect policy** (specifically blocking HTTPS → HTTP). Credential policies, host allowlists, redirect counts, size limits, and server behavior must be managed separately by the application or HTTP framework.

**Do not log query secrets:** when auditing a chain, replace full URIs with sanitized host/path or a correlation ID. HTTP client logs can inadvertently expose tokens in URLs.

## 19. Open Redirect and SSRF When Auto-Following

An endpoint `https://api.example.com/lookup?id=42` could be manipulated to return:

```http
HTTP/1.1 302 Found
Location: http://127.0.0.1:8080/admin
```

If a Java application runs inside an internal network and uses `ALWAYS` or `NORMAL` from **an initial HTTP URL** (or another scheme-permitted redirect), it can be led to an unintended internal service. This is a form of **server-side request forgery (SSRF)** via redirect.

Special case: for **HTTPS → HTTP**, `NORMAL` blocks the downgrade, but an attacker can still supply a target like `https://internal.example:8443/`. Therefore **blocking downgrades does not mean blocking SSRF**.

Defense layers:
1. **Accept constrained input** (allowlist scheme, host, port, path, business prefix).
2. **Validate each Location after `resolve`**, not only the first request.
3. **Block private IPs, loopback, link-local, metadata endpoints** when the application is only permitted to access the public Internet, per network requirements.
4. **Consider DNS rebinding/TOCTOU:** merely calling `InetAddress.getAllByName(host)` and then creating a request for `HttpClient` afterward does not guarantee the transport will connect to the exact IPs checked. Egress policies/network firewalls and resolution/connection binding appropriate to the actual HTTP stack are needed.
5. **Disable auto-redirects if per-hop control is absent:** `Redirect.NEVER` lets the application inspect the target before every subsequent request.
6. **Limit hop count, total time, total downloaded bytes, and request bodies** to prevent redirect loops/exhaustion.
7. **Do not forward secrets to disallowed origins**, even if the target uses valid HTTPS.

A URL "returned from a trusted server" can still be influenced by user parameters and open redirect flaws. For APIs taking user-supplied URLs, redirect targets must be treated as **untrusted data** until validated.

## 20. When Per-Hop Control Is Needed: How to Do Manual Redirects

`HttpClient.Redirect.NEVER` lets the client observe each 3xx and decide whether to create a new request. Conceptual flow:

```text
current = initial URI
hops = 0

loop:
  validate current (scheme, host, port, path, and egress policy)
  send one HttpRequest with HttpClient.Redirect.NEVER
  if response is not a redirect to follow:
      return response
  read Location (must be present and valid)
  next = response.uri().resolve(Location)
  validate next + cross-origin credential/method policy
  hops++
  if hops > MAX_HOPS: reject
  current = next
```

This is **pseudocode**, not a directly compilable Java program. A real manual implementation must define in detail:
- Which statuses are followed (301/302/303/307/308).
- When to change `POST` to `GET`, when to keep the body, and whether the publisher can be replayed.
- Which headers are copied and which must be stripped cross-origin.
- How CookieHandler/Authenticator/ProxySelector interact.
- Properly handling/closing the response body of each 3xx without unbounded downloads.
- Per-hop timeout and deadline for the entire chain.
- Redirect count limits and loop detection, plus custom protocol/scheme policies.
- Anti-SSRF mechanisms outside the HTTP layer such as egress ACLs and DNS/connection binding.

**Do not** simply take `Location`, call `HttpRequest.newBuilder(URI.create(location))`, and copy all headers/body from the original. Relative Locations can resolve against the wrong base, credentials can leak, POST semantics can change, and the new URI may fall outside the allowed scope.

### Code snippet for resolving and analyzing the target

```java
Optional<String> location =
        response.headers().firstValue("Location");
if (location.isPresent()) {
    URI target = response.uri().resolve(location.get());
    if (!"https".equalsIgnoreCase(target.getScheme())) {
        throw new IllegalArgumentException("HTTPS required");
    }
    if (!"api.example.com".equalsIgnoreCase(target.getHost())) {
        throw new IllegalArgumentException("Host not allowed");
    }
    // Also need to check port, DNS/IP, path, headers, and other policies.
}
```

This is a **code snippet**, not a complete SSRF defense; the variable `response` is `HttpResponse<?>`, with imports `java.net.URI` and `java.util.Optional`. Do not use a simple host comparison to replace all network/credential controls; it only illustrates validating the target **before** creating a new request.

## 21. Loops, Excessive Redirects, and Resource Limits

Redirect chains can be:
- Valid: `/old` → `/new` → `/final`.
- Looping: `/a` → `/b` → `/a`.
- Abnormally long: hundreds of hops due to misconfiguration.
- Crossing multiple hosts and ports.
- Returning a malformed/unsupported URI or missing Location.
- Hitting a timeout/failure mid-chain.
- Changing POST method/body on a hop, causing unexpected results.

The Java HTTP client implementation has a redirect/retry limit mechanism; Java 17 Networking documentation mentions the implementation-specific system property `jdk.httpclient.redirects.retrylimit` (with a default value noted in that documentation), but **do not use that number as a business guarantee**. The actual limit can be affected by retries from other errors and vary by version/provider. In sensitive applications, set an explicit hop limit at the policy layer when controlling each hop.

Good safeguard conditions:
- Business-specific `MAX_HOPS`, e.g., 5.
- Overall deadline for the entire operation; a per-request timeout is not an absolute substitute for an all-hops operation deadline in all configurations.
- Do not revisit previously visited URIs, accounting for canonicalization/different query cases.
- Limit response body/intermediate payloads.
- Forbid transitioning to schemes/hosts/ports outside the allowlist.
- When the request method/body is non-replayable, stop and report an error instead of silently retrying.

**Do not treat a redirect loop as a scenario where "HttpClient will automatically guarantee throwing exception type X"**. If unable to follow, the client may return the last intermediate 3xx, or the operation may fail due to I/O/timeout. When precision is required, test the behavior on the deployed runtime version and handle both 3xx and exceptions.

## 22. GET, HEAD, POST, and Redirects in Real Applications

An API client performing GETs for data may accept `NORMAL` to handle moved URLs, provided redirect targets remain within a trusted scope. However, requests carrying side effects or credentials require many conditions:

**GET:** 
- Usually safe/idempotent per HTTP semantics, though the request may still carry tokens or sensitive queries.
- Cross-host redirects risk sending credentials/data elsewhere.
- If downloading large data, body size limits and streaming policies are needed.

**HEAD:**
- Used to fetch metadata without a body; some servers redirect to a target and the client may follow.
- Do not use HEAD's success to infer that GET always has identical semantics when the application has custom logic.

**POST:**
- May change to GET on 301/302/303 in Java 17.
- 307/308 are expected to preserve method/body; must ensure payload can be resent, limit retries, and prevent duplicate side effects.
- Do not allow "payment" or "order creation" APIs to auto-redirect to arbitrary endpoints.

**PUT/DELETE/PATCH/custom methods:**
- Depend on HTTP standards, status codes, and client implementation behavior.
- Do not take POST test results and infer every method will behave identically.
- Dedicated integration tests should exist for requests with side effects.

**Server-side design:** if the server needs to direct the client to read a new resource after processing a POST, `303 See Other` usually clearly expresses switching to GET. If the server needs to move an endpoint while preserving method/body, 307/308 are more intentional choices than 302.

## 23. send() and sendAsync(): Redirect Policy Lives on the Client

Java `HttpClient` has synchronous and asynchronous APIs:
- `client.send(request, bodyHandler)` may block the caller until the response completes per BodyHandler and network conditions.
- `client.sendAsync(request, bodyHandler)` returns `CompletableFuture<HttpResponse<T>>`; handle the response when the future completes.

**Both use the redirect policy of the same `HttpClient` instance.** When automatic redirects complete, the final response of both sync and async supports `previousResponse()`.

Async code snippet:

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();

CompletableFuture<HttpResponse<String>> future = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString());

future.thenAccept(response -> {
    System.out.println("Final status: " + response.statusCode());
    System.out.println("Final URI: " + response.uri());
    System.out.println("Has history: " + response.previousResponse().isPresent());
}).exceptionally(error -> {
    System.err.println("HTTP exchange failed: " + error.getMessage());
    return null;
});
```

This is a **code snippet**; `request` is an appropriate `HttpRequest`, with imports `java.net.http.*` and `java.util.concurrent.CompletableFuture`. With async, the process must stay alive long enough for the future to complete; code should not just register a callback and exit the application. Production code needs cancellation, deadlines, executor management, and bounded logging.

**Important:** a `CompletableFuture` failing due to I/O/timeout/SSL is not the same as HTTP response statuses 3xx/4xx/5xx. You must have a branch handling response status **and** a branch handling exceptional completion.

## 24. Testing by Matrix Rather Than Guessing

| Case | Policy | Key expectation |
| --- | --- | --- |
| HTTP 302 `/start → /final` | NEVER | Returns 302, no automatic history, final body may be the 302's body |
| HTTP 302 `/start → /final` | NORMAL | Follows, receives final status if network succeeds |
| HTTP 302 `/start → /final` | ALWAYS | Follows, receives final status if network succeeds |
| HTTPS 302 → HTTP | NORMAL | **Does not auto-follow downgrade** |
| HTTPS 302 → HTTP | ALWAYS | Allows following if redirect is valid |
| HTTPS 302 → HTTPS same host | NORMAL | May follow |
| HTTPS 302 → HTTPS different host | NORMAL | May follow; application must still check host |
| 302 → 307 → 200 | NORMAL | Final 200; history contains 307 then 302 with null bodies |
| 301/302 POST → location | NORMAL/ALWAYS | Java 17 changes POST to GET in demo |
| 303 POST → location | NORMAL/ALWAYS | Changes to GET in demo |
| 307/308 POST → location | NORMAL/ALWAYS | Preserves POST/body in demo; publisher must be replayable |
| 3xx missing Location | Any | Does not follow a missing location; application handles 3xx |
| 302 relative Location | NORMAL/ALWAYS | Resolves from response URI per URI rules |
| Redirect loop | NORMAL/ALWAYS | Not allowed infinitely; outcome depends on limits/implementation |
| 401 authentication challenge response | With authenticator | `previousResponse` may contain intermediate auth response |
| Proxy/auth error, network timeout | Any | May throw exception, do not assume always receiving final 2xx |

Write local integration tests with:
- Ephemeral port `0`, bound to loopback to avoid external network impact.
- Independent tests for each case: GET, POST, relative Location, cross-origin, no Location, loop.
- Checking **how many times the endpoint was called** and the actual URI/method, not just the final status.
- Checking `previousResponse` per hop, status and headers, and verifying `body() == null` for intermediates.
- For HTTPS downgrade, use an HTTPS test server with a valid certificate/test truststore; never enable trust-all just for testing.
- Run tests on the actual deployed JDK/runtime; behavior can differ across libraries/frameworks, not just Java `HttpClient`.

## 25. Observability and Error Handling on Redirects

Useful logs for each logical operation:
- **Request correlation ID** generated by the application.
- **Sanitized initial URI**.
- **Sanitized final URI** after receiving the response.
- **Final HTTP status code**.
- **Redirect policy** in use.
- **Count and status of each intermediate response**.
- **Scheme/host changes** (especially downgrade/cross-origin).
- **Elapsed time, timeout/exception**, and application-layer retry count if any.
- **Initial method and final method** if business logic needs verification.
- **Response byte count** per policy, without logging sensitive bodies.

Example of a log format with query secrets stripped:

```text
operation=fetch-item
policy=NORMAL
initial=https://api.example.com/v1/item
final=https://api.example.com/v2/item
status=200
redirects=1
hops=301:https://api.example.com/v1/item
method=GET
result=success
```

Do not log `Authorization`, `Cookie`, bearer tokens, signed URLs, or raw PII. For `previousResponse`, only log status, filtered host/path, redirect type, and hop count. If a URL carries sensitive information in the path, continue masking according to data policy.

JDK Java HTTP client diagnostics can be used in controlled environments, such as the system property `jdk.httpclient.HttpClient.log`, but detailed logging must be protected and disabled at the right time. Do not treat debug logs as evidence that production must always store full URLs/headers.

## 26. Common Pitfalls

1. **"Java HttpClient follows redirects by default like a browser."** False: the default is `NEVER`.
2. **"NORMAL means only redirecting within the same origin."** False: NORMAL blocks HTTPS → HTTP, not a cross-origin allowlist.
3. **"ALWAYS guarantees every 3xx is followed."** False: status eligibility, `Location`, limits, method/body, and I/O still apply.
4. **"Final 200 means there was no redirect."** False: `previousResponse` may contain 3xx responses.
5. **"`response.headers().firstValue("Location")` gets the Location of the earlier 302."** False when `response` is the final 200; must walk history.
6. **"`previousResponse` is a list."** False: it returns a recursively linked `Optional<HttpResponse<T>>`.
7. **"Bodies of previous responses are fully preserved."** False: `body() == null` for responses from `previousResponse()`.
8. **"`response.uri()` always equals the URI the caller passed to send."** False on auto-follow; it is the URI of the current/final response.
9. **"`response.request().uri()` is always the initiating URI."** False: the request corresponding to the current response may be a redirected request.
10. **"302 always preserves POST and body."** False per Java 17 implementation: POST → GET.
11. **"307/308 need no consideration for body replay."** False: the body publisher must support resending and the business logic needs idempotency.
12. **"A relative Location only needs `URI.create(location)`."** False: must be resolved against the appropriate base URI.
13. **"HTTPS → HTTP redirect is nothing to worry about because the first hop was HTTPS."** False: the subsequent HTTP hop is not protected by TLS.
14. **"Using NORMAL prevents all SSRF."** False: redirects to private HTTPS hosts/IPs or from HTTP to internal HTTP are still possible.
15. **"On a redirect loop Java will always throw the exact same exception."** There is no guarantee of a specific exception type across all implementations/states; test and handle both 3xx and failures.
16. **"Just copy Authorization/Cookie to every redirect target."** False: risk of credential leakage when changing origins; an explicit policy is needed.
17. **"Connect timeout is enough to cover the whole redirect chain."** False: request, response body, multi-hop, and application deadlines also apply.
18. **"previousResponse is the history of all requests called through a client."** False: only the intermediate chain of the current exchange.
19. **"A null redirect body proves the server sent no body."** False: the API does not retain intermediate bodies for the caller in an automatic chain.
20. **"Switching to plaintext HTTP is a safe fallback when TLS fails."** False: that is a downgrade, not a fix for bad certificates/SSL handshakes.

## 27. Policy Selection Checklist per Application

**Choose `NEVER` when:**
- Requests serve user/remote-supplied URLs and must defend against SSRF.
- Sending credentials or sensitive payloads to allowlisted origins.
- Wanting to audit and explicitly decide each redirect hop.
- Needing to retain the 3xx body or custom method/response handling.
- Developing a crawler, proxy, or SDK needing custom redirect rules.

**Choose `NORMAL` when:**
- The client wants to conveniently follow common redirects.
- HTTPS → HTTP downgrade is disallowed.
- Sources/destinations are trusted or have supplementary controls.
- Timeouts, error handling, and tests exist for cross-host/method changes.

**Only consider `ALWAYS` when:**
- HTTPS → HTTP is explicitly permitted with business justification.
- No secrets/credentials need protection on the plaintext hop.
- Infrastructure and target hosts are controlled and tested.
- Risks of redirecting to other hosts/ports are bounded.

**For all policies:**
- Distinguish initial URI, final URI, and the `previousResponse` chain.
- Distinguish redirects from retries, auth challenges, SSL errors, and HTTP non-2xx responses.
- Be careful with POST 301/302/303/307/308 and replay.
- Check for missing/invalid Location, loops, and hop limits.
- Sanitize logs; do not leak tokens via headers/queries.
- If it is a broadly privileged network client, enforce egress/host/IP constraints at the transport/firewall layer rather than only inspecting URL strings.

## 28. Self-Check Exercises

**Q1.** `HttpClient.newHttpClient()` encounters `302 Location: /new`. Does it automatically access `/new`?  
**Answer:** No. The default is `Redirect.NEVER`, so the caller receives the 302 response directly.

**Q2.** `NORMAL` encounters a redirect from `https://a.example/old` to `http://a.example/new`. Does it follow?  
**Answer:** Does not auto-follow the HTTPS → HTTP downgrade; this is a key difference from ALWAYS.

**Q3.** `ALWAYS` encounters a redirect from `https://a.example` to `http://a.example`. Does it allow following per policy?  
**Answer:** Yes, subject to status/Location/limits/I/O. This is why the policy must be used very cautiously with sensitive data.

**Q4.** Chain `302 /start → 307 /middle → 200 /final` with `NORMAL`. What is `response.statusCode()`? What is `previousResponse().get().statusCode()`?  
**Answer:** Final is 200; most recent previous is 307. The previous of 307 is 302.

**Q5.** Why can `previousResponse().get().body()` be `null` even though the server sent a body in the 302?  
**Answer:** Java 17 `HttpResponse` specifies that the body of a response obtained from `previousResponse()` is `null`; intermediate bodies are not provided to the caller like the final body.

**Q6.** `POST` encounters 302 in the verified Java 17 implementation. After the redirect, which method is sent?  
**Answer:** `GET`, without resending the original POST body in the example.

**Q7.** `POST` encounters 307, and the publisher can replay. Which method does the next request use?  
**Answer:** `POST`; 307 requires preserving method/body semantics. However, the target and business side effects still need checking.

**Q8.** Why is `response.request().uri()` unreliable for inferring the original URI?  
**Answer:** It is the request corresponding to the current response, which may be a redirected request; the original `HttpRequest` must be kept separately.

**Q9.** Is `Location: //internal.example/admin` a safe same-host relative path?  
**Answer:** No. It is a network-path reference that **changes the hostname**, inheriting the scheme; host/IP and egress validation are required.

**Q10.** Does `NORMAL` prevent all SSRF because it blocks HTTPS → HTTP?  
**Answer:** No. NORMAL can still follow HTTPS → HTTPS to internal hosts/IPs; destination controls are required at every hop.

**Q11.** Can `previousResponse()` include a 401/authentication response?  
**Answer:** Yes. The JDK describes intermediate responses as coming from redirection **or authentication**.

**Q12.** How do you log the chain in chronological order when `previousResponse` traverses from most recent to oldest?  
**Answer:** Collect the intermediate responses, reverse the list, and then append the final response; do not mix up the URI and status of each hop.

## 29. Official Reference Documentation

- Java SE 17 `HttpClient` — default Redirect.NEVER, client configuration, send/sendAsync: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Java SE 17 `HttpClient.Redirect` — NEVER/NORMAL/ALWAYS and method changes on redirect: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html
- Java SE 17 `HttpClient.Builder` — `followRedirects`, `connectTimeout`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html
- Java SE 17 `HttpResponse` — `request()`, `uri()`, `previousResponse()`, `body()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- Java SE 17 `HttpRequest.Builder` — URI, timeout, method, headers, body publishers: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html
- Java SE 17 `URI` — `resolve` with relative URI-references: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html
- Java SE 17 `HttpServer` — local HTTP test server: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- RFC 9110 — HTTP Semantics, status codes 301/302/303/307/308: https://www.rfc-editor.org/rfc/rfc9110
- RFC 9112 — HTTP/1.1 message syntax and parsing: https://www.rfc-editor.org/rfc/rfc9112
- OWASP Server-Side Request Forgery Prevention Cheat Sheet — validating redirects/egress/destinations: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
