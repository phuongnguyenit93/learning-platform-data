# HTTP Client Logging, JSSE Debugging, and Credential Redaction During Diagnostics

*Java Advance – networking · Group: Configuration and Observability · Java SE 17+*

## 1. Objectives

When a Java application fails to call an HTTP API, enabling every type of log and sending the raw file externally can expose tokens, cookies, passwords, signed URLs, and personal data. The right diagnostic approach is to **classify the problem by layer**, choose just enough detail, and **avoid creating log records containing secrets in the first place**.

Three key observability sources in Java 17:

- **Application-level logging:** the application logs request ID, HTTP method, route template, outcome, status code, duration, and error category. This is where the field allowlist should be defined.
- **JDK HTTP client logging:** the system property `jdk.httpclient.HttpClient.log` enables event groups for `java.net.http.HttpClient`, sent via Java Util Logging (JUL) under the logger `jdk.httpclient.HttpClient`.
- **JSSE debug:** the system property `javax.net.debug` reveals TLS/SSL handshake activity, trust managers, certificates, TLS records, sessions, and related events at the security layer.

**Do not confuse them:** HTTP client logs are not JSSE logs, and an application logger that redacts secrets does not mean the JDK, reverse proxy, observability SDK, or JSSE automatically redacts secrets in the same way.

~~~text
Business request
     |
     +--> Application log (allowlisted fields)
     |       request_id, method, route_template, status, error_class
     |
     +--> java.net.http.HttpClient (Java 17)
     |       -Djdk.httpclient.HttpClient.log=...
     |       JUL logger: jdk.httpclient.HttpClient
     |
     +--> TLS / JSSE (only if HTTPS/TLS is actually used)
     |       -Djavax.net.debug=ssl:handshake:trustmanager
     |
     +--> TCP / proxy / DNS / origin server
             Has its own logs, metrics, and access controls
~~~

**Principle:** diagnose by default using safe structured logs; enable verbose diagnostics **for a short duration, on synthetic traffic or in a controlled environment**; determine where output goes, who can read it, and when it is deleted.

## 2. Log Each Layer to Answer the Right Question

| Tool | Useful when | Does not automatically provide |
|---|---|---|
| Application log | Knowing which request, which route, latency, HTTP status, timeout/body failure | Full TLS handshake details |
| `jdk.httpclient.HttpClient.log` | Observing JDK HTTP client channels, requests, errors, headers, HTTP/2 frames | Behavior of all HTTP libraries |
| `javax.net.debug` | Investigating truststore, TLS protocol/cipher, handshake, mTLS, certificate | Business status 404/500 |
| DNS/TCP/network metrics | Host resolution, connection refused, port, retransmits | Whether the HTTP body is valid |
| Proxy logs | CONNECT, 407, routing, proxy failures | Whether app logic committed successfully |
| Distributed tracing | Correlating spans/latency across services | Guarantee of automatically redacting all secrets |
| Metrics | Error rate, latency percentiles, retry/timeout counts | Request-level raw forensic details |

Classification examples:

- `401 Unauthorized` and `403 Forbidden` are HTTP statuses from the origin, not TLS errors by default.
- `407 Proxy Authentication Required` relates to proxy authentication; for HTTPS, this error can occur **during CONNECT before TLS to the origin**.
- `SSLHandshakeException` typically occurs before an HTTP response, so there may be **no status code from the origin**.
- `ConnectException`, `UnknownHostException`, or connect timeout requires checking DNS/TCP/proxy; enabling JSSE debug will not help if TLS has not started.
- HTTP `500` can be a complete response; do not treat it as equivalent to an IOException.
- A client receiving 200 headers and then failing while reading the body is a **body failure after headers**, not "the entire request succeeded".

### 2.1. Recommended Structured Fields for App Logs

| Field | Example | Meaning |
|---|---|---|
| `event` | `http_client_response` | Event type |
| `request_id` | `r-f3a7` | Correlates log records, not a token |
| `method` | `GET` | HTTP method |
| `route_template` | `/users/{id}` | No need to log raw path/query |
| `service` | `billing-api` | Allowlisted service label |
| `http_status` | `503` | Present only when an HTTP response was received |
| `phase` | `dns/connect/tls/headers/body` | Stage where the failure occurred |
| `duration_ms` | `244` | Latency measurement |
| `attempt` | `2` | Retry attempt |
| `response_bytes` | `512` | Amount of body received |
| `outcome` | `HTTP_5XX` / `TLS_FAILED` | Outcome category |
| `tls_protocol` | `TLSv1.3` | Metadata if the TLS handshake succeeded |
| `body_logged` | `false` | Easy to audit the no-body-logging policy |

Do not use raw URL or query as default fields. A client-supplied request ID may also contain CR/LF or forged content; validate its schema/length or issue the ID server-side.

## 3. JDK HttpClient Logging: Exact Property and Logger

Oracle Java SE 17 *Java Networking* describes `jdk.httpclient.HttpClient.log`: the property value is a **comma-separated list of categories**, and the JDK emits logs via `java.util.logging` with the logger named **`jdk.httpclient.HttpClient`** at level **INFO**.

~~~text
-Djdk.httpclient.HttpClient.log=errors
~~~

This property is for the **JDK HTTP client (module java.net.http)**; it does not apply generally to `HttpURLConnection`, Apache HttpClient, OkHttp, Netty, or Spring WebClient. If the application uses another library, consult the logging documentation for that specific implementation.

### 3.1. Categories in Java 17

| Category | Used to inspect | Risk |
|---|---|---|
| `errors` | Client-layer errors | May contain endpoint/exception metadata |
| `requests` | Request/lifecycle events | May expose URI path/query |
| `headers` | HTTP request/response headers | **May contain Authorization/Cookie/Set-Cookie/token** |
| `frames` | HTTP/2 frames | High volume and implementation details |
| `frames:control` | Control frames | HTTP/2 settings/goaway information |
| `frames:data` | Data frames | High volume, control payload/metadata |
| `frames:window` | Window/flow-control events | Useful for stalls |
| `frames:all` | All frame types | Very verbose |
| `ssl` | Client-side SSL/TLS events | Does not replace JSSE trust diagnostics |
| `trace` | JDK implementation trace | High volume, format subject to change |
| `channel` | Channel/connectivity events | Useful for connection lifecycle |

The general list described in the Java 17 documentation:

~~~text
errors,requests,headers,frames:control:data:window,ssl,trace,channel
~~~

You can replace `frames:control:data:window` with `frames:all`. **Do not take a category list from JDK 26/27 and assume Java 17 supports every item.**

### 3.2. How to Enable, Following an Incremental Principle

Start as narrow as possible, for example:

~~~bash
java '-Djdk.httpclient.HttpClient.log=errors' -cp out MyHttpApp
~~~

If you need to distinguish request lifecycle and endpoints, you can test in a **sandbox containing only synthetic requests**:

~~~bash
java '-Djdk.httpclient.HttpClient.log=errors,requests' -cp out MyHttpApp
~~~

When deep HTTP/2 troubleshooting is needed:

~~~bash
java '-Djdk.httpclient.HttpClient.log=errors,frames:control:window' -cp out MyHttpApp
~~~

`MyHttpApp` is an **illustrative class name**, not a code file provided in this lesson. In production handling OAuth/JWT/cookies, do not enable `headers` or uncontrolled verbose logging. Only enable high-detail groups such as `headers`, `frames:all`, and `trace` after a security review, using synthetic data and a restricted log sink.

**Do not assume the JDK redacts every secret in every version.** A raw URI in the `requests` category is enough to expose an `access_token` query parameter even without enabling `headers`.

### 3.3. Configuring JUL to Receive INFO Logs

Enabling the property is only part of the setup. `java.util.logging` also has logger levels and handlers. Example config file **`client-logging.properties`**:

~~~properties
handlers = java.util.logging.ConsoleHandler
.level = WARNING
jdk.httpclient.HttpClient.level = INFO
java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
~~~

Startup command:

~~~bash
java '-Djava.util.logging.config.file=client-logging.properties' \
     '-Djdk.httpclient.HttpClient.log=errors' \
     -cp out MyHttpApp
~~~

The config file above must be created by the learner and placed in the appropriate directory of the test environment. JUL's `ConsoleHandler` typically writes to **stderr**, not the HTTP response body. A root WARNING level does not mean a child logger at INFO will be blocked if the child logger and handler are set to INFO according to the JUL hierarchy; verify the actual configuration/bridge.

If the project uses SLF4J, Logback, Log4j2, or a cloud logging agent, JUL logs **do not automatically appear in the same sink by default**. The bridge/handler must be configured properly to avoid bridge loops, duplicate events, and uncontrolled formatting. Do not expect modifying `java.util.logging.config.file` at runtime to update all loggers the same way as at startup.

### 3.4. What Happens When Raw Headers Are Enabled?

This is an **illustration with secrets replaced by placeholders**, not using real credentials:

~~~http
GET /v1/items?access_token=[SENSITIVE] HTTP/1.1
Authorization: Bearer [SENSITIVE]
Cookie: sid=[SENSITIVE]
X-Api-Key: [SENSITIVE]
~~~

The JDK may log different details depending on the version, protocol, and category. Redacting headers at the application layer does not prove that internal JUL logging is redacted. If header diagnostics are unavoidable, use a **synthetic request** in an isolated environment and inspect the actual log destination; do not enable raw header logging for user requests.

## 4. JSSE Debug: A Different Data Source from HTTP Client Logs

`javax.net.debug` is a Java system property for the Java Secure Socket Extension. It shows how far the TLS handshake progresses, which protocol/cipher suite is selected, which certificate chain is received, whether the trust manager accepts or rejects it, and whether an mTLS client certificate is present.

The following commands are only samples for **a real, controlled HTTPS application**. Do not use JSSE commands as a way to fix HTTP 401/404.

~~~bash
java '-Djavax.net.debug=ssl:handshake' -cp out MyHttpsApp
~~~

To inspect certificate trust:

~~~bash
java '-Djavax.net.debug=ssl:handshake:trustmanager' -cp out MyHttpsApp
~~~

Java 17 documentation allows debug options after `ssl` to be separated by colons or commas. JSSE output may contain hostnames, certificate subjects, algorithms/handshake messages, and internal configuration details; treat it as high-sensitivity log data.

### 4.1. Choosing a JSSE Option by Issue

| Option | Content | When to use |
|---|---|---|
| `ssl` | General SSL/TLS debugging | Small tests |
| `handshake` | Handshake messages | Negotiation/handshake errors |
| `trustmanager` | Trust manager and certificate trust path | `PKIX path building failed` |
| `keymanager` | Client certificate/key manager selection | Mutual TLS |
| `sslctx` | SSLContext construction | Misconfigured SSLContext |
| `defaultctx` | Default SSL initialization | Suspected wrong default context |
| `session` | TLS session activity | Session reuse |
| `sessioncache` | Session cache trace | Resumption troubleshooting |
| `record` | Record-level TLS traces | Only for very deep diagnostics |
| `handshake:data` | Hex dump of handshake content | Verbose, contains sensitive metadata |
| `handshake:verbose` | Detailed handshake log | Isolated tests |
| `record:packet` | Raw encrypted TLS packet metadata/bytes | Avoid on live traffic |
| `record:plaintext` | Dumps TLS record plaintext in debug | **Especially dangerous, may expose payload** |
| `all` | All debug output | Do not enable by default |

In Java 17, `javax.net.debug` can emit through the JSSE debug/System.Logger mechanism (typically seen on **stderr**), and does not automatically match the JUL `jdk.httpclient.HttpClient` logger in format or routing. Output details vary across JDKs; **do not write parsers that depend on the exact order/lines of TLS logs**.

### 4.2. Issues That Do Not Need JSSE Enabled

- `UnknownHostException`: hostname/DNS has not resolved.
- `ConnectException` / connect timeout: TCP has not been established.
- Proxy `407` during CONNECT: proxy authentication may have been rejected **before TLS to the origin**.
- HTTP `401` after receiving a response: origin authentication.
- HTTP `429` / `503`: rate limits/overload.
- HTTP body `IOException` after TLS/headers may be a stream/transport failure, not necessarily a handshake failure.

Only enable JSSE debug when the failure is genuinely TLS-related or when higher-level logs indicate a handshake/protocol/trust path that needs investigation.

### 4.3. Reading Some Common TLS Errors

| Error/symptom | Where to look in logs | What to verify |
|---|---|---|
| `SSLHandshakeException: PKIX path building failed` | `ssl:handshake:trustmanager` | CA/truststore used by the app, certificate chain, expired CA |
| `No subject alternative names matching` | Handshake + hostname/SAN | Correct hostname and SAN |
| `Received fatal alert: handshake_failure` | Handshake/KeyManager for mTLS | TLS versions, cipher suites, peer policy, client cert |
| `protocol_version` | Handshake | Versions supported by client/server |
| `certificate_unknown` / `bad_certificate` | Handshake/trust direction | Which side sent the alert, which certificate was rejected |
| mTLS missing client certificate | `ssl:handshake:keymanager` | Keystore/private-key identity properly configured |
| TLS succeeds but HTTP 403 | App HTTP status | Authorization/permissions, do not "fix" TLS |
| Proxy CONNECT returns 407 | HTTP/proxy logs | `Proxy-Authenticate`/credentials for the proxy |

**Do not use a trust-all `X509TrustManager`, disable hostname verification, downgrade to weak TLS versions, or disable mTLS just to make the error disappear.** Those "fixes" undermine connection authenticity. Instead, check the CA chain, truststore, endpoint identity, cert SAN, system clock, and official TLS policy.

### 4.4. TLS Metadata After a Successful Connection

In Java 17, `HttpResponse.sslSession()` can return an `Optional<SSLSession>` if the response used TLS. Once an HTTPS response is received, you can extract the **negotiated protocol/cipher suite** as safer metadata than dumping the entire handshake:

~~~java
// Snippet, response is an HttpResponse<?> of an HTTPS request.
String tlsVersion = response.sslSession()
        .map(session -> session.getProtocol()).orElse("none");
String cipherSuite = response.sslSession()
        .map(session -> session.getCipherSuite()).orElse("none");
~~~

Do not log the raw certificate chain, session ID, peer principal, or private key by default. If the handshake fails before a response is produced, `sslSession()` cannot provide an object from a response that does not exist.

**For plain HTTP, `sslSession().isPresent()` is typically false.** This is the expected result, not a broken JSSE debug setup.

## 5. Types of Data to Exclude from Logs

| Source | Risky information | Policy |
|---|---|---|
| `Authorization` | Basic credentials, JWT, OAuth access token | Do not log value |
| `Proxy-Authorization` | Proxy username/password/token | Do not log value |
| `Cookie` | Session ID, CSRF token, personal activity | Do not log raw |
| `Set-Cookie` | Session cookies | Do not log raw |
| `X-Api-Key` / `X-Auth-Token` | API key/custom bearer token | Do not log value |
| `X-CSRF-Token` | CSRF/session value | Do not log raw |
| `Location` | Signed redirect URL, auth code, token query | Do not log raw URL |
| Query `access_token`, `refresh_token`, `id_token` | OAuth/token | Exclude entire query from event |
| Query `client_secret`, `password`, `api_key` | Password/API credentials | Exclude entire query |
| Query `signature` / `X-Amz-Signature` | Signed URL signature | Exclude raw query, and path if sensitive |
| URI userinfo / path token | `user:pass@host`, reset/invite token | Use route template instead of raw URI |
| HTTP bodies | Password, OTP, PII, payment data, auth responses | Do not log body by default |
| Exceptions | Exception message containing URL/query/headers | Log error type/phase instead of raw message |
| TLS diagnostics | Certificate metadata, internal hostnames | Restrict debug/sink/retention |
| Distributed tracing baggage | User-supplied keys, secrets | Allowlist/validate/truncate |

Do not forget **product-specific custom auth headers and query names**; a denylist of a few header names is not enough. Use a security-approved field allowlist so you do not have to predict every possible way a secret might be placed.

### 5.1. Why Not Log the URI Verbatim?

~~~text
https://api.example.test/v1/reset/TOKEN_VALUE?access_token=TOKEN_VALUE
https://user:password@api.example.test/v1/accounts
https://storage.example.test/object?X-Amz-Signature=SIGNED_VALUE
~~~

These are **illustrative URIs with dummy strings**, not real endpoints. Only log a label like `service=account-api` and a route template such as `/v1/reset/{token}`. Even when a query contains no token, it can still contain emails, phone numbers, names, search terms, or personal data.

Some HTTP clients strip the fragment from the network request, but the **raw URI in Java objects/loggers may still include the fragment/user-info**. Do not assume every component of a URL is public data.

### 5.2. JWTs, Prefix/Suffix Logging, and Hashing

A JWT is a token format with Base64url-encoded parts; the payload is not encrypted just because it looks like a random string. Do not log "the first/last 8 characters" as a supposedly safe redaction method. Short or structured tokens can still be identified, guessed, or abused.

If you need to correlate events within the same authentication session, issue a separate **opaque correlation ID**. Using an HMAC/keyed token fingerprint should only be done after review; do not treat a raw SHA-256 hash of a token as an automatic security solution, especially if the secret has low entropy.

### 5.3. Redact Before Creating the Log Record

Anti-pattern:

~~~java
// DO NOT: easily exposes raw query/headers/body/exception.
LOG.info("uri=" + request.uri());
LOG.info("headers=" + request.headers().map());
LOG.info("request=" + request);
LOG.info("body=" + response.body());
LOG.warning("failure=" + exception);
~~~

Recommended pattern:

~~~java
// SNIPPET: safe... variables are pre-allowlisted/validated.
LOG.info("event=http_response"
    + " request_id=" + safeRequestId
    + " method=" + safeMethod
    + " route=" + approvedRouteTemplate
    + " status=" + httpStatus
    + " body_logged=false");
~~~

The snippets above are not standalone programs; `LOG` and the corresponding variables belong to the application. In particular, do not treat `Throwable.toString()`, `HttpRequest.toString()`, or `HttpHeaders.map().toString()` as safe data by default.

### 5.4. Why Redaction in the Formatter/Log Collector Is Not Enough

~~~text
unsafe request / secret
        |
        v
raw log event
        |
        +-- async queue / backup / alternate handler
        |
        +-- regex redaction --> log file
~~~

If filtering happens only at the end of the pipeline, the raw value **has already passed through the log object** and may be captured by another handler/agent. Regexes easily miss custom header names, percent-encoded queries, nested JSON fields, multiline values, and exception chains. **Build events containing only allowlisted fields first**; additional filtering in handlers/collectors is a second layer of defense, not a replacement.

### 5.5. Preventing Log Forging

A raw `X-Request-ID`, User-Agent, or request URI can contain `\r`/`\n` characters, causing forged lines to appear in logs. With structured logging:

- Use a trusted JSON serializer/encoder instead of printing raw input directly.
- Validate/cap the length of IDs, enums, and route names.
- Escape newlines, tabs, control characters, and invalid characters.
- Do not let raw URIs or user IDs become unbounded-cardinality metric labels.
- Avoid printing secrets in assertion failures/test log output; report only booleans/outcomes.

## 6. Java 17+ Demo: Application Logs Safely Even When Requests Carry Dummy Tokens

This example runs **100% on loopback `127.0.0.1`**: `HttpServer` receives an HTTP request containing **dummy/synthetic** `Authorization`, `Cookie`, and query token values. The server verifies the dummy credentials to prove the full request was sent, then returns HTTP 200.

The application **does not log** the raw URI, headers, or body. It only logs the route template and `[OMITTED]` / `[REDACTED]` labels. To keep the output independent of timestamps, the demo uses a simple `java.util.logging.Handler` that writes messages to the console and a `StringBuilder`. **This handler does not automatically redact**; the log source is safe because the application constructs messages strictly from allowed fields.

**Do not run the demo with verbose flags `-Djdk.httpclient.HttpClient.log=errors,requests,headers` in a real environment**, because the request carries simulated token values to test the difference between application logs and internal JDK logging.

Create **`SafeHttpDiagnosticsDemo.java`**:

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
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SafeHttpDiagnosticsDemo {
    private static final String FAKE_SECRET = "SYNTHETIC_SECRET_NOT_REAL";
    private static final Logger LOG = Logger.getLogger("training.http.safe");
    private static final StringBuilder CAPTURED = new StringBuilder();

    static final class SafeOutputHandler extends Handler {
        @Override public synchronized void publish(LogRecord record) {
            if (!isLoggable(record)) return;
            String message = record.getMessage();
            CAPTURED.append(message).append('\n');
            System.out.println("APP " + message);
        }
        @Override public void flush() {}
        @Override public void close() {}
    }

    private static String routeLabel(URI uri) {
        // Approved route template; do not log the query or raw user path.
        return "/diag".equals(uri.getPath()) ? "/diag" : "[OTHER_ROUTE]";
    }

    private static void reply(HttpExchange exchange, int status)
            throws IOException {
        byte[] bytes = "OK".getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        SafeOutputHandler safeHandler = new SafeOutputHandler();
        safeHandler.setLevel(Level.INFO);
        LOG.addHandler(safeHandler);

        AtomicBoolean sawDemoCredentials = new AtomicBoolean(false);
        HttpServer server = HttpServer.create(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/diag", exchange -> {
            boolean valid = ("Bearer " + FAKE_SECRET).equals(
                    exchange.getRequestHeaders().getFirst("Authorization"))
                    && ("sid=" + FAKE_SECRET).equals(
                    exchange.getRequestHeaders().getFirst("Cookie"));
            sawDemoCredentials.set(valid);
            reply(exchange, valid ? 200 : 401);
        });
        server.start();
        try {
            URI target = URI.create("http://127.0.0.1:" +
                    server.getAddress().getPort() +
                    "/diag?access_token=" + FAKE_SECRET + "&mode=demo");
            HttpRequest request = HttpRequest.newBuilder(target)
                    .timeout(Duration.ofSeconds(3))
                    .header("Authorization", "Bearer " + FAKE_SECRET)
                    .header("Cookie", "sid=" + FAKE_SECRET)
                    .GET().build();
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3)).build();

            LOG.info("http_request id=demo-001 method=" + request.method()
                    + " route=" + routeLabel(request.uri())
                    + " query=[OMITTED] authorization=[REDACTED]"
                    + " cookie=[REDACTED]");
            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());
            LOG.info("http_response id=demo-001 status=" + response.statusCode()
                    + " version=" + response.version()
                    + " body=[NOT_LOGGED]");
            System.out.println("CHECK serverSawDemoCredentials="
                    + sawDemoCredentials.get());
            System.out.println("CHECK appLogContainsSecret="
                    + CAPTURED.toString().contains(FAKE_SECRET));
            System.out.println("CHECK tlsSessionPresent="
                    + response.sslSession().isPresent());
        } finally {
            server.stop(0);
            LOG.removeHandler(safeHandler);
        }
    }
}
~~~

Compile/run with **JDK 17 or later**; `jdk.httpserver` is the module for the local test server:

~~~bash
javac --release 17 --add-modules jdk.httpserver SafeHttpDiagnosticsDemo.java
java --add-modules jdk.httpserver SafeHttpDiagnosticsDemo
~~~

**Exact stdout verified when compiled with `--release 17` and run on OpenJDK 24:**

~~~text
APP http_request id=demo-001 method=GET route=/diag query=[OMITTED] authorization=[REDACTED] cookie=[REDACTED]
APP http_response id=demo-001 status=200 version=HTTP_1_1 body=[NOT_LOGGED]
CHECK serverSawDemoCredentials=true
CHECK appLogContainsSecret=false
CHECK tlsSessionPresent=false
~~~

### 6.1. Interpreting the Output

| Line | Conclusion |
|---|---|
| `APP http_request ... [OMITTED] ... [REDACTED]` | Application log does not contain request query/header values |
| `APP http_response ... status=200` | Client received HTTP 200 and logged metadata only |
| `serverSawDemoCredentials=true` | Server actually received the test credentials |
| `appLogContainsSecret=false` | The `CAPTURED` string of the **application logger** does not contain the fake token |
| `tlsSessionPresent=false` | Loopback HTTP has no TLS, therefore no SSLSession |

**Important distinction:** checking `CAPTURED` does not inspect the contents of a reverse proxy, JDK HTTP internal logging, JSSE, the OS, or an external monitoring agent. The goal of the test is to prove the allowlist at the **application logging boundary**, not to claim the entire system can never log a token.

### 6.2. Why Not Test JSSE with the Same Server?

The example server uses **plaintext HTTP**. There is no `SSLSocket`/TLS handshake, so `javax.net.debug=ssl:handshake` will not produce a TLS handshake for this request. To test JSSE, use a **valid HTTPS endpoint you control**, with a test truststore/keystore containing no real credentials. Never add a trust-all SSLContext just to force output.

## 7. Step-by-Step Diagnostic Workflow

### Step 1: Classify the Outcome in the Application

Log safe fields: `request_id`, `route_template`, `method`, `status` if present, `phase`, `elapsed_ms`, and `error_category`. In particular, distinguish:

~~~text
DNS failed -----------> no HTTP origin response
TCP connect failed ---> no HTTP origin response
TLS handshake failed -> usually no HTTP origin response yet
HTTP 401 / 403 -------> real HTTP response received
HTTP 407 -------------> proxy authentication response
HTTP 503 -------------> server/proxy overload response
HTTP headers received -> body may not be complete yet
HTTP body EOF --------> body completed
body IOException -----> body failed despite an earlier status 200
~~~

### Step 2: Enable Narrow HTTP Client Internal Logging

If the request is made by JDK 17's `java.net.http.HttpClient`, start with `errors`. Confirm that the JUL handler receives INFO. If you need to add `requests`, verify the URI has no raw tokens/PII or use synthetic traffic only. `headers` and `frames:all` should only be enabled in an isolated test with a restricted log sink.

### Step 3: For TLS Errors, Enable Targeted JSSE Debug

Start with `ssl:handshake`. If `PKIX path building failed` appears, add `trustmanager`. If mTLS client certificate selection fails, consider `keymanager`. Do not enable `record:plaintext` or `all` for traffic carrying real data.

### Step 4: Fix the Root Cause, Disable Debug

Fix the CA/truststore, hostname/SAN, mTLS identity, proxy credentials, or network route depending on the error. After verification, **restore log flags**, restrict debug dump retention, and delete or adjust access permissions according to policy; do not post raw files to unauthorized tickets/chats.

## 8. Combining TLS Session Metadata with Request Logs

After a successful HTTPS response, Java's `HttpResponse.sslSession()` can provide TLS metadata. However, do not use `SSLSession.getId()` as a default log value; session identifiers are controlled information. In structured log events, only record `tls_protocol=TLSv1.3`, `cipher_suite=...` if genuinely needed, and enforce logger field lengths.

**A single HTTP/2 connection can carry multiple HTTP requests**, and a TLS session can be reused/resumed. Do not treat every request as a new TLS handshake, nor treat a handshake log as a complete HTTP request.

If status is 200 but `BodyHandlers.ofInputStream()` returns early after headers, the application request log should separate `response_headers_received` and `body_completed`. Do not close the entire trace/metrics span at headers if the goal is to monitor full body consumption.

## 9. Common Mistakes

| Mistake | Why it is wrong | How to fix |
|---|---|---|
| Enabling `headers` in production to debug 401 errors | May expose tokens/cookies of many requests | Use synthetic traffic only; log safe auth result metadata |
| Assuming JDK internal logging is safe because the app logger redacts | Two independent log sources | Control each handler/sink |
| Assuming `jdk.httpclient.HttpClient.log` applies to OkHttp/Apache | It is a JDK HttpClient property | Check the actual HTTP client library |
| Enabling `javax.net.debug=all` across all services | Excessive metadata, may contain sensitive data | Enable narrow handshake/trustmanager |
| Using `record:plaintext` to "inspect the HTTP body" | Exposes application plaintext after TLS | Do not use on live traffic |
| Diagnosing HTTP 401 with JSSE | 401 is an HTTP-layer response | Check application HTTP status/credential scope |
| Logging status 500 on `SSLHandshakeException` | Usually no HTTP origin response exists | Separate network/TLS error category |
| Logging raw `HttpRequest.toString()` | URI may contain tokens/query | Use route template and safe fields |
| Logging response body for every 4xx | May contain PII, tokens, internal errors | Log status and approved error code |
| Assuming masking the last 4 chars of a token is safe | The prefix can still be sensitive | Omit the token; use a separate correlation ID |
| Relying solely on regex in the Formatter | Raw secrets already passed through other loggers/sinks | Allowlist at the source and test sinks |
| Using default `exception.toString()` | May contain raw URL/headers | Log validated exception class/category |
| Logging `X-Request-ID` verbatim | May contain CR/LF or be overly long | Validate, normalize, cap length |
| Leaving verbose logs enabled after investigation | Leakage risk and log cost | Time-box and restore flags |
| Using trust-all to fix PKIX | Breaks peer authentication | Fix truststore/certificate chain |
| Disabling hostname verification to fix SAN | Introduces MITM risk | Use a certificate with the right hostname |
| Treating stderr as safe logging | Containers/agents may ship stderr to the cloud | Review the entire ingestion pipeline |
| Setting status to SUCCESS when 200 headers arrive | Body stream can fail afterward | Log terminal body completion separately |

## 10. Testing the Logging Policy

Use **dummy sentinel values** in multiple places, then inspect application log captures, controlled JUL output/sinks, reverse proxy request logs, and exported traces:

~~~text
Authorization: Bearer FAKE_TOKEN_A
Proxy-Authorization: Basic FAKE_TOKEN_B
Cookie: sid=FAKE_COOKIE_C
X-Api-Key: FAKE_API_KEY_D
URI: /reset/FAKE_PATH_TOKEN?access_token=FAKE_QUERY_E
Body: {"password":"FAKE_PASSWORD_F"}
~~~

The test fails if any sentinel appears in an unauthorized log sink. Do not print the raw sentinel in the test failure report; report only the data type name or number of offending events.

In addition to standard values, test:

- Case-insensitive headers and unusual custom header names.
- URL-encoded, percent-encoded, fragment, user-info, and redirects.
- CR/LF/control characters in request IDs or headers.
- Nested JSON, arrays, body compression, and multipart uploads.
- Exceptions containing raw URLs in the cause chain.
- Logs generated by third-party SDKs and auto-instrumentation.
- Correlating request trace IDs without logging session IDs.
- Retention/export permissions, including log backups and support tickets.

**Do not use a single `appLogContainsSecret=false` test result as certification that all logs are safe**: that test only checks the scope of `CAPTURED` in the example.

## 11. Cost and Operations of Debug Logs

Verbose HTTP/2 frames, SSL record-level debug, or full request logging can generate massive log volumes and impact CPU, disk, network egress, storage, and latency. A collector with a full queue can slow down the application or drop logs. Moreover, log archives are replicated across backups and multiple observability systems.

Define in advance:

| Policy | Minimum to clarify |
|---|---|
| Who may enable | Authorized owner/on-call |
| Scope | One environment/instance/endpoint or synthetic traffic |
| Data | Which fields/categories are allowed to be logged |
| Duration | Maximum enabled window, expiration date |
| Storage | Restricted sink, encrypted transfer/storage |
| Access control | RBAC, access audit logs |
| Retention | Delete per policy, including copies/exports |
| Volume controls | Sampling, size/line limits, disk quotas |
| Restoration | Disable debug and verify flags after incident |

Do not send a raw JSSE handshake dump or HTTP headers containing tokens in a public issue, chat, or email. Before sharing, extract only a **sanitized excerpt** and review for sensitive content.

## 12. Practical Checklist

**Configuration:** identify the JDK runtime and client library; test `jdk.httpclient.HttpClient.log=errors` with JUL logger INFO in a sandbox; use `javax.net.debug` only for TLS; ensure flags are passed to the JVM running the application.

**Diagnostics:** distinguish HTTP status, proxy 407, DNS/TCP errors, TLS handshake failure, and body failure. Collect correlation ID, phase, status, latency, and TLS version if present—never raw secrets.

**Security:** strip query/raw path/tokens from logs; do not print `Authorization`/`Cookie`/`Set-Cookie`/`Proxy-Authorization`; do not use TLS record plaintext; protect JUL/JSSE/proxy/observability sinks; prevent log forging and data exfiltration.

**Post-incident:** disable verbose flags, verify client output is back to normal, do not leave TLS certificate/hostname checks disabled, run redaction tests, and follow retention/debug dump access policy.

## 13. Self-Check Questions

**1. Which API does `jdk.httpclient.HttpClient.log` belong to?** Only JDK `java.net.http.HttpClient` diagnostics.

**2. Which logger and level does Java 17 use?** JUL `jdk.httpclient.HttpClient`, INFO.

**3. What are the Java 17 categories?** `errors,requests,headers,frames,ssl,trace,channel`; frames includes `control,data,window,all`.

**4. Why is `headers` sensitive?** It may contain Authorization, Cookie, API keys, and signed values.

**5. Why is `requests` also risky?** The URI may contain tokens or PII in the path/query.

**6. What does `javax.net.debug` show?** TLS/JSSE diagnostics, not business HTTP response statuses.

**7. What should you choose when suspecting a PKIX trust failure?** `ssl:handshake:trustmanager`.

**8. Why avoid `ssl:record:plaintext`?** It can expose plaintext application data.

**9. Is an HTTP proxy 407 necessarily a JSSE error?** No; it is proxy authentication and can occur before TLS.

**10. Does `SSLHandshakeException` always have an `HttpResponse.statusCode()`?** No; the handshake usually fails before an HTTP response.

**11. How should a certificate hostname mismatch be fixed?** Fix the hostname/SAN/certificate; do not disable verification.

**12. Does the demo use HTTPS and print a JSSE handshake?** No, it uses loopback HTTP and `tlsSessionPresent=false`.

**13. What does `appLogContainsSecret=false` prove?** Only that the app logs held by `CAPTURED` do not contain the dummy sentinel.

**14. Does `SafeOutputHandler` automatically redact secrets?** No; application code selects safe fields before logging.

**15. Why not log raw `HttpRequest.headers().map()`?** The header map may contain multiple credential values.

**16. Should you rely solely on regex redaction in the log collector?** No; secrets may have already passed through other queues/handlers/sinks.

**17. Can you print a token prefix and hash the suffix for safety?** Not by default; omit the token or use a separate opaque correlation ID.

**18. Why test queries/paths?** Secrets can reside in the URL instead of `Authorization`.

**19. Is it safe to log `Throwable.toString()`?** Not guaranteed, as it may contain a URI/token.

**20. What must you do when debugging is complete?** Disable verbose flags, verify TLS configuration is proper, and handle log artifacts per retention/access policy.

## 14. Official References

- [Oracle Java SE 17 – Java Networking](https://docs.oracle.com/en/java/javase/17/core/java-networking.html): `jdk.httpclient.HttpClient.log`, categories, and logger `jdk.httpclient.HttpClient` at INFO.
- [Oracle Java SE 17 – JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): `javax.net.debug`, handshake, trustmanager, session/record debug, TLS diagnostics.
- [Java SE 17 – java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): JUL logger, levels/handlers.
- [Java SE 17 – java.util.logging.LogManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html): JUL configuration file.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): send/sendAsync, HTTP client lifecycle.
- [Java SE 17 – HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): `statusCode`, `sslSession`, body timing.
- [Java SE 17 – SSLSession](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html): `getProtocol`, `getCipherSuite`.
- [Java SE 17 – SSLHandshakeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLHandshakeException.html): TLS handshake failures.
- [Java SE 17 – HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback test HTTP server.
- [OWASP – Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): secrets/PII exclusions, log injection, access control, and retention.
- [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): avoiding logging raw session IDs and using safe correlation.

**Conclusion:** **Application-level structured logs with allowlisted fields** are the default observability layer. When needed, enable `jdk.httpclient.HttpClient.log` to inspect internal JDK HTTP client activity, and `javax.net.debug` for targeted JSSE/TLS investigation. **Do not log raw credentials/URIs/bodies**, do not rely on end-of-pipeline regex alone, do not disable TLS verification, and always manage the scope, access control, cost, and lifecycle of debug logs.
