# Receiving a Correlation ID in Java Logging

**Receiving a correlation ID** is the step of reading a correlation identifier from the **ingress boundary** of an application (HTTP request, RPC metadata, or message headers), determining whether that identifier is accepted, and establishing an **effective correlation ID** for the entire processing flow. In Java systems, this identifier commonly appears under an HTTP header such as `X-Correlation-ID` or `X-Request-ID`.

The purpose of a correlation ID is to help locate log lines belonging to **the same request or workflow**, even when the call spans multiple layers or services. It is **diagnostic information**, not a password, session token, user ID, identity assertion, or authentication credential.

For example, a client sends:

~~~http
GET /orders HTTP/1.1
Host: example.internal
X-Correlation-ID: req-20261109-01
~~~

If the application accepts that ID, the logs can carry:

~~~text
INFO correlationId=req-20261109-01 event=request_received route=/orders
INFO correlationId=req-20261109-01 event=order_loaded orderId=ord-7
INFO correlationId=req-20261109-01 event=response_sent status=200
~~~

The key point is **not to let each layer generate a different ID** when all of them are handling the same workflow. However, trusting a value from an external network requires explicit validation.

## 1. Where Does a Correlation ID Come From?

A correlation ID can be provided by:

- **HTTP client:** adds `X-Correlation-ID` to the request.
- **API gateway/reverse proxy:** generates an ID at the entry point or forwards an already accepted ID.
- **Upstream service:** propagates the ID when calling a downstream service.
- **Messaging system:** places the ID in queue or event message properties/headers.
- **RPC framework:** uses call metadata to carry the value.
- **Job scheduler:** attaches an ID when initiating an independent batch/job and passes it through processing steps.

A system may have multiple types of IDs:

| ID | Common Meaning | Can It Be the Same as Correlation ID? |
| --- | --- | --- |
| `correlationId` | Groups logs of a processing/business flow | The field managed in this guide |
| `requestId` | Identifies a single HTTP request | May differ from an ID spanning multiple services |
| `traceId` | Identifies a trace in distributed tracing | Can be used to link logs, but has different semantics |
| `spanId` | Identifies a single span within a trace | Not the correlation ID of the entire flow |
| `orderId`, `userId` | Business entity identifiers | Should not replace diagnostic IDs; subject to separate security policies |
| `messageId` | Identifies an individual message | May differ from the ID of a workflow containing multiple messages |

**Do not assume `X-Request-ID`, `X-Correlation-ID`, and W3C `traceparent` are the same protocol.** A system may choose to use a trace ID as the log lookup key, but it must preserve the proper format, semantics, and tracing policy. Never overwrite `traceparent` with an arbitrary UUID.

## 2. Flow for Receiving a Correlation ID over HTTP

Processing flow at ingress:

~~~text
HTTP request
  |
  v
Gateway / load balancer (if any)
  |
  v
Java HTTP server / Servlet filter / framework middleware
  |
  v
Read configured header
  |
  +-- Missing? ---------------------------+
  |                                       |
  +-- Single value? -> Validate ----------+
  |                      |                |
  |                   Invalid             |
  |                      |                |
  +-- Duplicate/ambiguous? ---------------+
  |                                       |
  |                               Generate safe new ID
  |                                       |
  +-- Single valid value -----------------+
  |                 |
  v                 v
Select effective correlation ID
  |
  +--> Put into request context / MDC
  +--> Use when calling dependent services
  +--> Attach to response header per policy
  |
  v
Execute business logic and emit logs
  |
  v
Clean up context in finally / try-with-resources
~~~

These steps should reside at the **entrypoint layer**, before business controllers or services run. If each controller reads the header on its own, it is easy to end up with logs missing the ID, inconsistent validation rules, or MDC not being cleaned up properly.

### Distinguishing "Receiving" and "Propagating"

- **Receiving:** reading the ID from outside; validating and selecting/generating the effective ID.
- **Attaching context:** keeping the ID in the processing scope so logs can access it.
- **Propagating:** sending the effective ID to downstream services or messages.
- **Completing:** clearing the context from the thread and (if appropriate) returning the ID in the response.

This article focuses on **receiving and controlling the ID at ingress**, though the subsequent steps determine whether the ID remains useful.

## 3. HTTP Header Conventions

A simple convention:

~~~text
Request header name:  X-Correlation-ID
Response header name: X-Correlation-ID
Log field name:       correlationId
~~~

`X-Correlation-ID` and `X-Request-ID` are **de facto conventions**, not a guarantee that every gateway or framework supports them automatically. An organization must standardize on **one official name** or clearly document precedence if multiple sources exist.

HTTP header names are **case-insensitive**. Therefore, `X-Correlation-ID` and `x-correlation-id` represent the same header name in HTTP. Do not write security logic that relies on case differences in header names.

### Do Not Accept Multiple Names Without Rules

Suppose a request contains both:

~~~http
X-Request-ID: req-a
X-Correlation-ID: req-b
~~~

If service A picks `X-Request-ID` while service B picks `X-Correlation-ID`, logs can split into two groups. You should clearly define:

1. One officially accepted name, with other names used only for migration according to a defined priority order.
2. If both are present and conflict, either reject the request or use only the ID generated by a trusted gateway.
3. Do not concatenate two IDs into an unschematized string.
4. Do not silently rename the field in each service.

For systems already integrated with distributed tracing, use the appropriate tracing library to receive and propagate `traceparent` per W3C Trace Context rather than applying the same `X-Correlation-ID` validator to every header.

## 4. Trust Boundary: Client-Sent Headers Are Untrusted Data

An external party can arbitrarily set:

~~~http
X-Correlation-ID: admin
~~~

That value does not prove the request was made by an admin. If the log shows `correlationId=admin`, an investigator only knows **the client sent an accepted string**, not the client's identity.

Some risks include:

- **Log forging/spoofing:** an attacker chooses an ID matching another flow's ID to confuse investigations.
- **Log injection:** a string containing newlines or control characters creates fake log entries if unescaped.
- **Oversized data:** megabyte-scale headers consume memory or overload serialization/indexing.
- **High cardinality:** every request uses a different value; useful for tracing but unsuitable as a metric label.
- **Data leakage:** a client stuffs an email, token, address, or sensitive payload into the header and the system logs it.
- **Gateway boundary confusion:** a backend service trusts a header sent directly by the client even though policy intends to accept IDs only from the gateway.

**Format validation makes an ID safer to log and propagate, but it does not turn it into trustworthy identity data.**

### Two Common Trust Policies

**Policy A — Allow clients to propose an ID:** accept an ID with valid syntax/length; otherwise generate a new one. Suitable for APIs that let clients self-correlate requests, provided you understand clients can intentionally reuse IDs.

**Policy B — Gateway as the source of truth:** the edge proxy strips client-supplied headers or generates its own ID, then attaches an internal header managed exclusively by the gateway. Downstream services trust the value **over an authenticated, network-restricted channel**, while still validating format to guard against misconfiguration.

If strong anti-spoofing is required, **UUIDs or regex alone are not enough**. You need source authentication, gateway policies, and independent auditing.

## 5. Input ID Validation Rules

An easy-to-implement illustrative policy:

- Accept **exactly one header value**.
- Limit to **at most 64 characters**.
- Start with an ASCII letter or digit.
- Subsequent characters may only include `A-Z`, `a-z`, `0-9`, dot `.`, underscore `_`, and hyphen `-`.
- Disallow spaces, commas, slashes, quotes, tabs, or newlines.
- Never put an invalid raw ID into MDC, responses, or log messages.
- If missing, invalid, or duplicate, use a newly generated random UUID per the example policy.

Regular expression for the example:

~~~regex
[A-Za-z0-9][A-Za-z0-9._-]{0,63}
~~~

Anchoring is enforced via Java's `Matcher.matches()`, which requires the **entire string** to match. This regex accepts IDs from **1 to 64 characters** long, starting with an ASCII alphanumeric character.

| Input ID | Accepted by Example Policy? | Reason |
| --- | --- | --- |
| `req-20261109-01` | Yes | Characters are in the allowlist |
| `a` | Yes | Valid single starting character |
| `4a93d0b3-2f5c-4bc0-9a61-b47c3f2bc788` | Yes | Text UUID valid under the character set |
| `bad id!` | No | Contains space and exclamation mark |
| `two,values` | No | Contains comma |
| `a/b` | No | Contains slash |
| 200-character string | No | Exceeds length limit |
| Empty string | No | Missing starting character |
| Line with CR/LF | No | Not in allowed character set; HTTP stack may reject early |

**This is an application-chosen policy**, not a universal standard for correlation IDs. A system that only accepts standard UUIDs may use a stricter policy. If using OpenTelemetry trace IDs, follow Trace Context formatting and semantics rather than imposing the generic regex above.

### Do Not Just Trim and Trust

Some HTTP stacks strip leading/trailing whitespace when parsing headers. That behavior does not mean the original input was valid, and arbitrary `trim()` calls can turn `" abc "` into `"abc"` and cause ambiguity.

Controlled normalization can be chosen, but it should be explicitly specified in the contract. The example here **does not auto-trim**: the string reaching the application layer must match the entire allowlist.

### Duplicate Header Cases

A client can send two headers with the same name:

~~~http
X-Correlation-ID: one
X-Correlation-ID: two
~~~

Java HTTP APIs may return these as a **multi-value list**; another proxy might merge them into `one,two`. Both cases must be handled according to policy. The Java example below **only accepts a list with exactly one validly formatted element**; comma-joined strings are also rejected by the regex.

Do not arbitrarily pick **the first element** when a request has multiple unresolved values. If the gateway and application layers pick differently, investigations become inconsistent.

## 6. When Missing or Invalid: Generate, Reject, or Use Gateway ID?

No single policy fits every application.

| Situation | Common Choice | Thing to Keep in Mind |
| --- | --- | --- |
| Missing header | Generate a new ID | Does not mean the request is an error |
| Empty/malformed header | Generate a new ID or return 400 per contract | Do not echo the raw invalid value |
| Duplicate headers | Generate a new ID or reject | Avoid differing interpretations between proxy and service |
| Valid header from external client | Accept if the API allows | Do not treat it as a trusted identity |
| ID issued by a trusted gateway | Reuse after validation | Must protect the link between gateway and service |
| Request starts a brand-new workflow | Can generate a new workflow ID | Define its relationship to request/trace IDs |
| Downstream receives ID from upstream | Keep effective ID if policy allows | Do not regenerate at every hop |

For this learning example, we choose a **graceful fallback** policy: if the input ID is invalid, generate a **new UUID** and continue processing the request. The reason is that a correlation ID serves diagnostics and is not necessarily a mandatory business precondition.

For systems whose contract requires an official ID from the client or gateway, you can return a 400 error instead of regenerating. If you choose that approach, test error paths and ensure malicious raw headers are not logged.

### Why Use `UUID.randomUUID()`?

Java 17 provides:

~~~java
String correlationId = java.util.UUID.randomUUID().toString();
~~~

This method generates a version 4 UUID suitable as a random ID for general correlation purposes. The output is 36 characters long, for example:

~~~text
4a93d0b3-2f5c-4bc0-9a61-b47c3f2bc788
~~~

This is an **example of the format**, not a fixed output of a call. The collision probability under proper use is negligible, but a UUID is not an access credential. Never use a correlation ID as an authentication token, and never rely on its "unpredictability" to authorize data access.

### Should You Record Why a New ID Was Generated?

You can record a metric/counter or a safe log event, such as:

~~~text
event=correlation_id_regenerated reason=INVALID_FORMAT
~~~

**There is no need to log the rejected raw ID.** If you still need to investigate offending sources, log approved metadata such as route template, gateway name, error category, and the new request ID; do not reflect secrets or control characters from the client into logs.

## 7. Storing the ID in Request Context and MDC

After receiving or generating an ID, the application needs to let log lines for the same request share that ID. In Java, **SLF4J MDC** (*Mapped Diagnostic Context*) is a common mechanism.

~~~java
// Illustrative snippet inside a method that has effectiveId and logger.
try (org.slf4j.MDC.MDCCloseable ignored =
        org.slf4j.MDC.putCloseable("correlationId", effectiveId)) {
    logger.info("event=request_received");
    // Execute request business logic.
}
~~~

MDC typically holds **string key–value pairs** in the current thread's context. A backend like Logback can output the value in a pattern:

~~~xml
<pattern>%level | correlationId=%X{correlationId} | %msg%n</pattern>
~~~

If a log call occurs outside the MDC scope, `%X{correlationId}` will usually be empty; if MDC is not cleared in a thread pool, subsequent requests can **accidentally inherit the previous request's ID**.

**Putting the ID into MDC adds logging context; it does not automatically forward the header to downstream HTTP calls.** To propagate the ID, outbound client code or framework instrumentation must attach it to request headers or message metadata.

### Why Is `finally` or `try-with-resources` Needed?

HTTP server threads are usually reused. If a controller throws an exception and MDC is not cleared, the next request on the same thread may pick up the wrong `correlationId`, causing misattributed logs.

`MDC.putCloseable` returns an object usable in `try-with-resources` to remove the key when the scope exits. In frameworks where multiple components manage MDC, establish a clear restore/clear policy to avoid wiping context owned by another component.

### MDC and Asynchrony

Do not assume MDC propagates automatically across:

- `CompletableFuture.supplyAsync`.
- `ExecutorService` worker threads.
- Reactive pipelines.
- Manually spawned threads.
- RPC/message consumers dispatching work onto another thread.

If a service offloads work to an executor, **pass the correlation ID as data** or use the framework's context propagation mechanism, then set MDC inside the worker **with its own scope and cleanup**.

Do not simply set MDC on the HTTP thread and hope background task logs have the right ID. Write tests for thread hops and verify that context is cleaned up afterward.

## 8. Java 17+ Example: Receiving Correlation ID via HTTP Header

This complete example uses:

- **JDK 17+** with `com.sun.net.httpserver.HttpServer` to create a local HTTP endpoint.
- **JDK HttpClient** to send test requests.
- **SLF4J API 2.0.17** for Logger and MDC.
- **Logback 1.5.18** as the SLF4J provider/backend to print MDC to stderr.

The goal of the example is to demonstrate **receiving a single header, preserving a valid ID, replacing missing/invalid/duplicate IDs with a UUID, and cleaning up MDC**. The server binds only to loopback and uses a single worker thread for testing; **it is not an optimal server configuration or a production-ready API**.

### 8.1. Project Structure

~~~text
correlation-receive/
├── pom.xml
└── src/
    └── main/
        ├── java/demo/CorrelationReceiveDemo.java
        └── resources/logback.xml
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>correlation-receive</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.slf4j</groupId>
      <artifactId>slf4j-api</artifactId>
      <version>2.0.17</version>
    </dependency>
    <dependency>
      <groupId>ch.qos.logback</groupId>
      <artifactId>logback-classic</artifactId>
      <version>1.5.18</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

The versions above were used to **compile and verify** the example; this is not a claim that they are the latest releases. In real projects, manage versions via dependency management and framework compatibility.

### 8.3. logback.xml

Create `src/main/resources/logback.xml`:

~~~xml
<configuration>
  <appender name="STDERR" class="ch.qos.logback.core.ConsoleAppender">
    <target>System.err</target>
    <encoder>
      <pattern>%level | correlationId=%X{correlationId} | %msg%n</pattern>
    </encoder>
  </appender>
  <root level="INFO">
    <appender-ref ref="STDERR"/>
  </root>
</configuration>
~~~

Logback reads `%X{correlationId}` from MDC within the request scope. `%msg` is only the message body and does not include the correlation ID automatically; therefore, you must configure an appropriate pattern or JSON encoder.

### 8.4. CorrelationReceiveDemo.java

Create `src/main/java/demo/CorrelationReceiveDemo.java`:

~~~java
package demo;

import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpServer;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class CorrelationReceiveDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(CorrelationReceiveDemo.class);
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");
    private static final String HEADER = "X-Correlation-ID";

    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newSingleThreadExecutor();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.setExecutor(workers);
        server.createContext("/orders", exchange -> {
            String correlationId = receiveCorrelationId(
                    exchange.getRequestHeaders());
            try (MDC.MDCCloseable ignored =
                    MDC.putCloseable("correlationId", correlationId)) {
                LOG.info("event=request_received method={} route=/orders",
                        exchange.getRequestMethod());
                exchange.getResponseHeaders().set(HEADER, correlationId);
                byte[] body = "accepted".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, body.length);
                try (var out = exchange.getResponseBody()) {
                    out.write(body);
                }
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            String url = "http://127.0.0.1:"
                    + server.getAddress().getPort() + "/orders";
            HttpClient client = HttpClient.newHttpClient();

            HttpResponse<String> valid =
                    request(client, url, List.of("req-20261109-01"));
            HttpResponse<String> missing =
                    request(client, url, List.of());
            HttpResponse<String> invalid =
                    request(client, url, List.of("bad id!"));
            HttpResponse<String> duplicate =
                    request(client, url, List.of("one", "two"));

            String validId = value(valid);
            String missingId = value(missing);
            String invalidId = value(invalid);
            String duplicateId = value(duplicate);

            System.out.println("validPreserved="
                    + "req-20261109-01".equals(validId));
            System.out.println("missingGenerated=" + isUuid(missingId));
            System.out.println("invalidReplaced=" + isUuid(invalidId));
            System.out.println("duplicateReplaced=" + isUuid(duplicateId));
            System.out.println("mdcCleared="
                    + workers.submit(() -> MDC.get("correlationId") == null)
                            .get());
            System.out.println("bodyReceived="
                    + (valid.statusCode() == 200
                    && "accepted".equals(valid.body())));
        } finally {
            server.stop(0);
            workers.shutdownNow();
            workers.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static String receiveCorrelationId(Headers headers) {
        List<String> values = headers.get(HEADER);
        if (values != null && values.size() == 1) {
            String id = values.get(0);
            if (id != null && SAFE_ID.matcher(id).matches()) {
                return id;
            }
        }
        return UUID.randomUUID().toString();
    }

    private static HttpResponse<String> request(
            HttpClient client, String url, List<String> ids)
            throws Exception {
        HttpRequest.Builder builder =
                HttpRequest.newBuilder(URI.create(url)).GET();
        for (String id : ids) {
            builder.header(HEADER, id);
        }
        return client.send(builder.build(),
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    }

    private static String value(HttpResponse<?> response) {
        return response.headers().firstValue(HEADER).orElse("");
    }

    private static boolean isUuid(String value) {
        try {
            return value.length() == 36
                    && UUID.fromString(value).toString().equals(value);
        } catch (IllegalArgumentException e) {
            return false;
        }
    }
}
~~~

### 8.5. Running the Program

From the directory containing `pom.xml`, using Maven and JDK 17+:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CorrelationReceiveDemo
~~~

**Verified exact stdout:**

~~~text
validPreserved=true
missingGenerated=true
invalidReplaced=true
duplicateReplaced=true
mdcCleared=true
bodyReceived=true
~~~

In addition to stdout, Logback prints **four INFO lines to stderr** matching the pattern:

~~~text
INFO | correlationId=req-20261109-01 | event=request_received method=GET route=/orders
INFO | correlationId=<generated UUID> | event=request_received method=GET route=/orders
INFO | correlationId=<generated UUID> | event=request_received method=GET route=/orders
INFO | correlationId=<generated UUID> | event=request_received method=GET route=/orders
~~~

The three `<generated UUID>` placeholders in the stderr diagram are **illustrative notation**, not literal output. Actual UUID values change on every run, so the test verifies UUID format rather than printing a hardcoded ID.

### 8.6. Case-by-Case Breakdown

1. **Valid header:** `req-20261109-01` matches the allowlist, is preserved, and is returned via `X-Correlation-ID`.
2. **Missing header:** the receiver finds no value list and generates a new UUID; `missingGenerated=true`.
3. **Invalid header:** `bad id!` contains a space and exclamation mark, failing the regex; the server returns a new UUID instead of echoing the invalid string.
4. **Duplicate header:** the client sends two values under the same name; the server API returns a multi-element list (or a proxy might join them with a comma). The policy only accepts a single valid value, so this case is replaced with a UUID.
5. **MDC cleanup:** the handler uses `try-with-resources`; after all four requests run through the single worker thread, a check task on that same worker confirms `MDC.get("correlationId") == null`.
6. **Response body:** the server returns body `accepted` and status 200; the test verifies the response succeeds.
7. **HTTP scope:** the server binds to loopback and picks an ephemeral port so it does not affect public services. Test connections use localhost.

This is a short example to illustrate **header reception and context boundaries**. In a real application, the handler needs to account for I/O errors, timeouts, cancellation, filter chains, authentication, CORS, and framework-appropriate lifecycles; do not copy the demo test server verbatim as a production deployment skeleton.

### 8.7. Why Use a Logback Pattern Instead of Embedding the ID in Every Message?

If an application writes:

~~~java
logger.info("correlationId={} event=request_received", correlationId);
~~~

every call site must pass the exact ID and field name. With MDC, the encoder/layout can automatically inject `correlationId` into **all log events emitted within the scope**, including business layers that have no direct knowledge of HTTP headers.

However, MDC is neither a security mechanism nor general storage. It simply attaches logging context, requires proper lifecycle cleanup, and must be synchronized across thread switches. For structured logging, configure a JSON encoder to emit `correlationId` as a dedicated field rather than only a text pattern.

## 9. Receiving the ID in a Servlet Filter or Spring Framework

In a Servlet application (Tomcat, Jetty, Spring MVC, etc.), receive the ID in a **centralized filter/interceptor/middleware** at the request boundary. General pseudocode:

~~~text
onRequest:
  read all X-Correlation-ID values
  select effective ID per policy
  store ID in request attribute/context
  set MDC correlationId for this scope
  invoke filter chain or controller
  add response header per policy
finally:
  restore/clear MDC for this scope
~~~

This is **pseudocode**, not a complete Servlet class. In Servlets, a multi-value header method such as `getHeaders(name)` is more useful than just `getHeader(name)` when you need to detect duplicate values. Using only `getHeader` can silently pick **the first value** and miss duplicate-header cases.

### Things to Watch Out for in Framework Implementations

- **Filter order:** if the logging filter runs after filters that can reject requests, authentication error logs may lack the ID. Place it early enough so the ID is present for observable logs.
- **Error responses:** controller errors still need the same correlation ID if a response can still be sent.
- **Async dispatch:** if a Servlet switches to async processing, the initial thread's MDC scope does not automatically cover worker threads or subsequent dispatches.
- **Request attributes:** you can store the effective ID in a request attribute so application code does not depend directly on MDC.
- **Authentication:** receiving an ID does not replace authentication/authorization; never infer permissions from a diagnostic header.
- **Multiple overlapping filters:** avoid having multiple filters each generate different IDs or clear another filter's MDC.
- **Proxy headers:** only trust headers processed by a gateway over a trusted channel.

If your framework already provides trace/correlation instrumentation, integrate with it rather than adding a competing filter that overwrites `requestId`/`traceId`.

## 10. Returning the Correlation ID in the HTTP Response

Returning the effective ID in a response header often helps clients or support teams cross-reference error reports:

~~~http
HTTP/1.1 200 OK
X-Correlation-ID: req-20261109-01
Content-Type: application/json
~~~

In the Java example, the response header is **always the validated or newly generated ID**, never a rejected raw header.

Benefits:

- Users can provide an ID in bug reports without sending sensitive business payloads.
- Clients learn which ID the server actually used if the input value was replaced.
- API gateways and support teams can link events between request and response.

However, keep in mind:

- A correlation ID **does not prove a client owns a request**; customer support must still verify identity through a separate channel.
- Do not allow internal log lookups based solely on knowing a public ID.
- For **cross-origin** browser API calls, the client may need `Access-Control-Expose-Headers: X-Correlation-ID` so JavaScript can read the response header.
- If a browser sends the custom `X-Correlation-ID` request header cross-origin, the server may need CORS preflight and `Access-Control-Allow-Headers` configured per origin policy.
- Do not loosen CORS overly just to expose a correlation ID; continue protecting sensitive endpoints and data.

Some systems choose not to echo the ID back to public clients. That is an API/security design decision, not a requirement for internal logging to work.

## 11. Propagating the Effective ID to Downstream HTTP Services

Receiving an ID only helps if downstream layers use it consistently. With Java 17 `HttpClient`:

~~~java
// Illustrative snippet inside a method with client, uri, and effectiveId variables.
HttpRequest request = HttpRequest.newBuilder(uri)
        .header("X-Correlation-ID", effectiveId)
        .GET()
        .build();
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
~~~

This is **not a standalone program**; `client`, `uri`, and `effectiveId` are variables already available at the call site. The key is to pass the **selected `effectiveId`**, rather than re-reading the raw header from the original request.

If service A receives a valid ID and calls B and then C, preserve the ID across hops when the systems share a correlation contract. Each service can still generate its own internal `requestId`, provided it uses a separate field name so it does not overwrite the workflow-wide correlation ID.

### Do Not Rely on MDC as a Transport Protocol

MDC is only in-process/thread-local logging context and **does not automatically add HTTP headers**. For outbound services to receive the ID, you must either:

- Pass the ID explicitly on the client request; or
- Use a client interceptor/instrumentation configured to read the effective context and attach the header.

An interceptor must also enforce policies to avoid leaking IDs from one trust domain to an unauthorized external domain. Never blindly forward all inbound request headers to outbound HTTP calls; forward only validated, required headers.

## 12. Receiving Correlation IDs Outside HTTP

The same concepts apply to messaging and RPC, though **where metadata lives differs**.

### Queue or Event Bus

A message might carry:

~~~text
topic: payment-events
headers:
  X-Correlation-ID: req-20261109-01
payload:
  event: payment_retry
~~~

This is an illustrative representation, not mandatory API syntax for Kafka, RabbitMQ, or JMS. When a consumer receives a message:

1. Read the correlation ID from **message headers/properties** per the contract.
2. Validate type/encoding, length, and trust policy.
3. Generate a new ID if missing or invalid per the rules.
4. Place the ID into the processing scope and logger context.
5. Propagate the ID when publishing new messages in the same workflow.
6. Clean up the context after processing, including on errors or retries.

If a message is retried, decide to keep the workflow's correlation ID and use an additional attempt/message ID to distinguish individual deliveries. Do not generate a new correlation ID on every retry if doing so breaks log continuity.

### gRPC

gRPC carries metadata according to HTTP/2 and gRPC header rules. Use an appropriate **server interceptor** instead of manually handling raw HTTP headers inside business methods. Pay attention to metadata key types, allowed characters, length limits, and propagation across calls.

### Batch/Job

For work that does not start from an HTTP request, you can generate a new correlation ID at the **start of the job** and attach it to all processing steps or pass it via task context. If a single job triggers many independent transactions, consider separating `jobId` and `correlationId` so unrelated events are not lumped together.

## 13. How Do Correlation IDs Differ from Distributed Tracing?

A **correlation ID** is an application-convention key for linking logs. **Distributed tracing** provides trace/span structure, parent–child relationships, sampling, and standard propagators.

A W3C Trace Context trace uses a header like `traceparent` with its own **trace-id**, **parent-id**, and **trace-flags** rules. Avoid:

- Treating the entire `traceparent` string as `correlationId` without an explicit design.
- Generating a UUID correlation ID and stuffing it into `traceparent` in the wrong format.
- Changing `trace-id` at every hop while expecting spans to remain in the same trace.
- Merging `spanId` and `correlationId` into one field, causing query confusion.
- Trusting tracing headers from the public internet as proof of user authentication.

Practical integration guide:

| Need | Data to Use |
| --- | --- |
| Link logs in the same workflow per application contract | `correlationId` |
| Link a single HTTP request | `requestId` if separated |
| Look up an end-to-end trace | `traceId` provided by tracing instrumentation |
| Look up a single operation/span | `spanId` |

If an application already has standard tracing and every service logs `traceId`, you may not need to invent an extra correlation ID. However, if workflows span beyond a single trace (long-running jobs, multi-message retries, multi-call batches), an independent business-correlation ID remains useful. Choose based on **semantics and the queries you need to answer**, not just for the sake of naming.

## 14. Security, Personal Data, and Abuse Prevention

Even though a correlation ID is not secret data by default, headers received from clients are still external input that must be validated.

Practical safeguards:

1. **Limit length and characters:** prevent newlines/control characters and oversized IDs.
2. **Restrict duplicate/ambiguous headers:** establish clear reject or regenerate policies.
3. **Do not log invalid raw IDs:** log a reason code instead of data that might contain secrets.
4. **Do not use the ID for authorization:** knowing a correlation ID must never grant access to sessions or internal logs.
5. **Do not equate the ID with user identity:** multiple services can share a correlation ID while authenticating the user independently.
6. **Protect trust boundaries:** let the gateway manage internal IDs when policy requires it.
7. **Do not mix PII into IDs:** never use emails, phone numbers, or tokens as correlation IDs.
8. **Control log retention and access:** correlation IDs aid lookup, but logs also contain other sensitive fields.
9. **Do not use `correlationId` as a metric label:** many/unique values cause high cardinality in metrics.
10. **Monitor header quality:** count missing/invalid/duplicate events using low-cardinality metric labels.

### User-Supplied Correlation IDs Can Collide Intentionally

A client can intentionally send the same ID across multiple requests. Under a policy that accepts client-supplied IDs, their logs will be grouped together. If you need to distinguish individual requests, add a separate server-generated internal `requestId`; that is **a distinct field**, not just a regex tweak.

## 15. Performance and Request Lifecycle

Reading a header, checking a short regex, and generating a UUID when needed is rarely expensive in most HTTP services. However, context and logging mechanisms have costs worth considering:

- `UUID.randomUUID()` allocates a new string; do not generate IDs multiple times for the same request.
- MDC is thread/implementation-scoped context; setting and clearing it repeatedly in every method is redundant.
- JSON encoders/structured logging repeat the correlation ID in every event, increasing byte volume.
- Heavy INFO logging on high-throughput endpoints costs far more than receiving the ID itself.
- Async frameworks require proper context propagation; MDC leaks cause subtle data corruption that is harder to detect than runtime overhead.
- If many requests carry high-cardinality correlation IDs, design indexing and storage around per-request lookup needs.

Useful measurements include: percentage of requests with a valid inbound ID, regeneration rate, rate of logs missing `correlationId`, logger encoder overhead, and payload growth. Do not try to "optimize" by sharing one ID across unrelated requests just to reduce cardinality.

## 16. Common Pitfalls

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Logs show `correlationId=null` | MDC not set or pattern/encoder reads wrong key | Verify `correlationId` key and scope |
| Next request carries previous request's ID | Forgot to clear ThreadLocal/MDC in thread pool | Use `try-with-resources` or `finally` |
| One request generates multiple IDs | Multiple filters/controllers generating IDs | Pick effective ID at a single entrypoint |
| Duplicate header picks first value | Calling single-value `getHeader` and ignoring list | Read all values and apply policy |
| Invalid value inserts newlines into logs | Logging raw header without validation | Use allowlist; never log raw invalid values |
| Client sends an ID but response uses another | Gateway overwrote it or validator regenerated | Define contract and return effective ID |
| Microservice B does not see ID from A | MDC does not propagate HTTP headers automatically | Use outbound client interceptor or explicit header |
| Async task loses `correlationId` | Context does not cross executor/reactive boundaries | Propagate context with its own scope |
| Every request on the service has the same ID | Static/global variable or improper context reuse | Scope per request; never store globally |
| Logs searchable by `traceId` but not `correlationId` | Two different ID types without field mapping | Separate fields and log query strategies |
| Correlation ID used to view customer data | Mistaken for an auth token | Always authenticate/authorize separately |
| Metrics explode due to many series | Using `correlationId` as a metric label | Keep IDs in logs/traces only |
| Browser cannot read response ID | Missing CORS expose header | Configure `Access-Control-Expose-Headers` appropriately |
| Browser cannot send custom header cross-origin | CORS preflight/allow headers misconfigured | Configure `Access-Control-Allow-Headers` and origin |
| Logs before controller lack the ID | Filter registered too late | Place middleware early enough in pipeline |
| ID missing after sending a message | Consumer does not read/forward message metadata | Define correlation contract on the bus |
| Invalid ID accepted by mistake | Checking only non-null or trimming/slicing arbitrarily | Use `Matcher.matches`, max length, reject ambiguous |
| Logs contain email/token as correlation ID | Accepting arbitrary strings and logging directly | Enforce allowlist and control input sources |

### Quick Investigation Checklist

1. Confirm whether the header actually reached **Java ingress** or was stripped/rewritten by a gateway.
2. Check which code decides the **effective correlation ID** and when.
3. Verify header count, regex, length, and fallback rules.
4. Check whether MDC/request context is set before the first log line.
5. Confirm the Logback/Log4j2 encoder actually outputs the `correlationId` field.
6. Verify cleanup on both successful responses and exceptions.
7. For async threads, verify separate propagation and cleanup.
8. Inspect outbound headers and downstream service context.
9. Query logs by the effective ID returned in the response, not a rejected raw ID.
10. Confirm collector parsing/indexing and retention to distinguish ID reception bugs from dropped logs.

## 17. Recommended Test Matrix

| Scenario | Input Sent | Expected Result |
| --- | --- | --- |
| Valid header | `req-20261109-01` | Preserved as-is |
| Missing header | No `X-Correlation-ID` | Valid UUID generated |
| Empty header | Empty string | Regenerated or 400 per contract |
| Header with spaces | `bad id!` | Not used verbatim |
| Oversized header | Over 64 characters | Regenerated or 400 |
| Header with control characters | Value rejected by HTTP stack or reaching app | Raw input never written to logs |
| Two headers with same name | `one`, `two` | Regenerated/rejected per policy |
| Different header casing | `x-correlation-id` | Treated as the same HTTP header |
| Success response | 200 | Response header has effective ID |
| Error response | 4xx/5xx after ingress | If response is still writable, returns effective ID |
| Logs across multiple layers in one request | Different service methods | Same `correlationId` |
| Second request on same worker | Thread pool reuse | Does not carry stale MDC |
| `CompletableFuture` | Async hop | ID propagated if configured |
| Downstream call | `HttpClient` or interceptor | Downstream header carries effective ID |
| Message retry | Same workflow | Workflow ID preserved per contract |
| Client reuses same ID for two requests | Valid ID sent repeatedly | Determined by policy; may need separate `requestId` |
| No logging backend/provider | SLF4J API only | Verify provider if no logs appear |
| Collector not indexing field | JSON contains only message text | Check encoder/mapping end-to-end |

Do not test only the ID selection code: test logging before/after exceptions, filter handlers, async dispatches, and middleware ordering, because correlation bugs often appear **after header reception itself is already correct**.

## 18. Exercises and Answers

### Exercise 1 — Missing Header

A client calls `GET /orders` without sending `X-Correlation-ID`.

**Question:** Should the request fail immediately?

**Answer:** It depends on the contract. In most APIs choosing fallback, the application generates a new ID, puts it into logs, and may return it in the response. A missing diagnostic header is not necessarily a business error.

### Exercise 2 — ID with Newline

An external value attempts to inject a newline and the line `ERROR payment succeeded`.

**Question:** Why not put it straight into MDC?

**Answer:** It risks log injection and formatting corruption. The header may be rejected early by the HTTP stack; if it reaches the application layer, validate characters/length and regenerate or reject without logging the malicious raw value.

### Exercise 3 — Duplicate Headers

A proxy forwards two values: `a-1` and `b-2`.

**Question:** Is calling `getHeader` to read the first value enough?

**Answer:** No, if the contract requires detecting duplicates. Read the full list and handle it consistently. For example, regenerate when there is not exactly one valid value.

### Exercise 4 — MDC Not Cleaned Up

A servlet thread handles request A, sets `correlationId` A, and forgets to clear it; it then handles request B, which has no header.

**Question:** What is the consequence?

**Answer:** Logs for B can be tagged with ID A, causing misattribution. Request B needs its own effective ID, and context must be cleaned up in `finally`/`try-with-resources`.

### Exercise 5 — Trace ID vs. Correlation ID

A service has an OpenTelemetry-issued `traceId` while also receiving `X-Correlation-ID` from a workflow.

**Question:** Should `traceId` be overwritten with `correlationId`?

**Answer:** No. Keep separate fields and separate propagation rules; you can log both if helpful for investigations.

### Exercise 6 — Browser Cannot See Response Header

An API returns `X-Correlation-ID`, but cross-origin JavaScript cannot read it.

**Question:** Is the header definitely missing?

**Answer:** Not necessarily. Check CORS `Access-Control-Expose-Headers`; if the client needs to send a custom header, also check preflight and `Access-Control-Allow-Headers` per policy.

### Exercise 7 — ID as a Metric Label

An application adds `correlationId` as a label on a per-request counter.

**Question:** What is the problem?

**Answer:** Very high cardinality, which can exhaust metrics system resources. Use correlation IDs only for logs/traces and targeted searches; use stable metric labels like route template or status class.

### Exercise 8 — Propagating to a Queue

An HTTP request publishes a message for background processing. The consumer logs events, but `correlationId` is missing.

**Question:** If the HTTP header was received properly, why is it still missing?

**Answer:** The HTTP thread's MDC does not automatically cross a message bus. You must place the ID in message metadata, and the consumer must receive it and establish its own scope.

## 19. Pre-Deployment Checklist

- [ ] Standardize the header name and log field name.
- [ ] Decide whether to accept client-supplied IDs or trust only the gateway.
- [ ] Read all header values; do not ignore duplicate cases.
- [ ] Enforce a character allowlist, max length, and clear missing/invalid policy.
- [ ] Never log or echo back invalid raw IDs.
- [ ] Use UUID or an approved ID generator for fallback.
- [ ] Choose **one effective ID** at a single entrypoint per request.
- [ ] Put the ID into request context/MDC early and clear it in `finally`.
- [ ] Never use global/static mutable fields to store request IDs.
- [ ] Test thread-pool cleanup and async propagation.
- [ ] Configure the encoder to output `correlationId` in the desired field/pattern.
- [ ] Propagate the effective ID to outbound HTTP/RPC/messages in the same workflow.
- [ ] Return the effective ID in responses if allowed by contract; check CORS if needed.
- [ ] Separate `correlationId` from `traceId`/`spanId` and business IDs.
- [ ] Never use `correlationId` as an auth token or metric label.
- [ ] Verify gateway policies, header rewrites, and trust boundaries.
- [ ] Prevent personal data/tokens from appearing in correlation IDs.
- [ ] Count missing/invalid/duplicate rates without exposing raw input.
- [ ] Verify logs end-to-end from ingress to collector and search queries.
- [ ] Test missing, invalid, duplicate, exception, retry, async, and multi-service scenarios.

## 20. References

- [SLF4J manual](https://www.slf4j.org/manual.html): Logger, MDC, and integrating the facade with a backend.
- [Logback MDC](https://logback.qos.ch/manual/mdc.html): how to use mapped diagnostic context and pattern output.
- [JDK 17 HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): JDK HTTP server used in the example.
- [JDK 17 HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): sending HTTP requests and reading responses.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): distinguishing standard trace context from application-defined correlation headers.

**Remember:** Receiving a correlation ID properly is not just grabbing a string from an HTTP header. It requires **a source contract, validation of length/characters/value count, selecting an effective ID, scoping context properly, cleaning up MDC, returning or propagating it in a controlled manner**, and finally verifying that all logs of the same workflow can be accurately linked. Above all, a correlation ID aids investigation—**it does not prove identity or access rights**.