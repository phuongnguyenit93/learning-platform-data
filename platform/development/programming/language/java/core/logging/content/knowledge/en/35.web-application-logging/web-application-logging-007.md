# User-Agent in Java Web Application Logging

## 1. What is User-Agent?

In HTTP, **User-Agent** is a request header that a client can send to self-describe the software making the request: a browser, command-line tool, SDK, crawler, mobile app, or custom client. When stored in web access logs, this field helps group traffic and assist in diagnosing client compatibility issues.

An illustrative HTTP request:

```http
GET /api/orders/123 HTTP/1.1
Host: api.example.test
User-Agent: LearningClient/1.0
Accept: application/json
```

Some User-Agent formats you may encounter:

```text
Mozilla/5.0 (...) Chrome/...
Mozilla/5.0 (...) Firefox/...
curl/8.5.0
PostmanRuntime/...
ExampleBot/1.0
MyCompanyApp/2.4
```

The lines above only illustrate the **shape**. Browser strings often contain multiple tokens for historical compatibility reasons; you cannot infer the primary browser from the first token `Mozilla/5.0`.

Most importantly: **User-Agent is self-declared by the client, not an authenticated identity**. The request sender can craft a string that looks like Chrome, a known bot, or another application. Therefore, never use User-Agent as authentication evidence, an authorization condition, a definitive conclusion about the device, or proof of who actually accessed the system.

### 1.1. Why log it?

In web application logging, common questions include:

- Are 500 errors or timeouts concentrated in a specific client/browser group?
- Is this endpoint receiving a high volume of requests from a self-declared automation tool?
- After an SDK update, is there an increased error rate from clients self-declaring the new version?
- Which **self-declared signals** indicate whether requests originate from a browser, CLI, or mobile app?
- Are there unusual, overly long values or control characters that break log parsers?

UA is valuable for analysis when paired with **request ID/trace ID, route-template endpoint, HTTP method, status, processing duration, and actual outcome**. A line that only logs `User-Agent: ...` is usually insufficient to reconstruct an incident.

### 1.2. Distinguishing Concepts

| Data | What does it answer? | Does it authenticate identity? |
| --- | --- | --- |
| `User-Agent` | Which software the client **claims** to use | No |
| Authenticated principal / session | Which actor the system has verified | Depends on authentication mechanism |
| Request ID | Which logs belong to the same request | No |
| Trace ID | Which spans/events belong to the same trace | No |
| Connection IP | Where the connection or proxy came from | Not sufficient to identify a user |
| `http.route` | Which logical route the server handled | Used for endpoint observability |
| `Sec-CH-UA` and client hints | Additional hints sent by the client/browser | No |

The UA field does not replace authentication, authorization, bot verification, or fraud detection systems.

## 2. How to Read User-Agent in Java Web

In the Servlet API:

```java
// Integration snippet when request is an HttpServletRequest:
String rawUserAgent = request.getHeader("User-Agent");
```

`getHeader` returns the header value or `null` if it does not exist. HTTP header names are case-insensitive; `User-Agent` and `user-agent` are the same name in HTTP semantics.

Note the version differences:

- Older Java Servlet applications and many Spring Boot 2.x applications use `javax.servlet.http.HttpServletRequest`.
- Spring Boot 3.x applications on the Servlet stack use the `jakarta.servlet.http.HttpServletRequest` ecosystem.
- The WebFlux/reactive stack does not use the same Servlet filter mechanism as Spring MVC; you must read the request and write context using the corresponding reactive APIs.

Never assume UA always has data. HTTP clients may omit the header, proxies may modify/strip it, and a request may contain multiple headers with the same name depending on container/gateway behavior. If you need to handle multiple values, check `request.getHeaders("User-Agent")` and define a clear policy; do not blindly concatenate multiple strings without bounds.

### 2.1. Differences in UA Seen at Each Layer

```text
Browser / curl / SDK
         |
   CDN / WAF / gateway
         |
   reverse proxy
         |
   Servlet container / Spring MVC
         |
       Controller
         |
   application logger
         |
     collector / sink
```

A gateway may alter headers before forwarding to the Java app. Requests blocked by a WAF may **never reach the Java application**, so application logs alone cannot provide evidence of all external requests. Access logs at the gateway, container, and application have different observability scopes. If you retain records across multiple layers, you need to identify the emitting layer and use request correlation to avoid double counting.

## 3. What Data Should Be Stored?

An illustrative **structured access event**:

```json
{
  "event": "HTTP_REQUEST_COMPLETED",
  "timestamp": "2026-11-10T02:00:00Z",
  "service": "orders-api",
  "requestId": "req-2001",
  "method": "GET",
  "route": "/api/orders/{id}",
  "status": 200,
  "durationMs": 27,
  "userAgentFamily": "BROWSER",
  "userAgentPresent": true
}
```

This is simulated data, not JSON automatically generated by every backend. The fields help answer "which request, to which route, what status, and what self-declared client type?". The timestamp here is an illustrative point in time.

There are three collection levels:

| Representation | Example | When it is useful |
| --- | --- | --- |
| Raw UA | `Mozilla/5.0 (...) Chrome/...` | Detailed compatibility investigation within permitted scope |
| Sanitized and bounded UA | Truncated string with control characters removed | Controlled text log debugging |
| Coarse family | `BROWSER`, `CLI`, `SDK`, `OTHER`, `UNKNOWN` | Dashboards, aggregation, and metric labels |

**Prioritize minimal collection.** If the goal is only to compare error rates between browsers and CLIs, a `ua.family` group is usually more appropriate than detailed raw UA on every line. If raw UA is needed for investigation, separate policies for access control, storage, and retention must be defined.

Fields should be distinguished clearly:

- `ua.present`: whether the header is present; do not infer that a client was always identified.
- `ua.family`: coarse classification, which may be inaccurate or spoofed.
- `ua.original`: raw data; store only when there is a valid reason and policy.
- `ua.truncated`: records length truncation if needed to analyze missing data.
- `requestId`/route/status/duration: application observability info, not inherent components of UA.

## 4. Java 17: Standalone Example to Read, Sanitize, and Classify UA

The program below simulates four different UAs without needing an HTTP server or external libraries:

1. `curl/8.5.0` self-declares as CLI.
2. A string containing the `Chrome/` token is classified into the browser group.
3. A string containing a newline character simulates the risk of forging log lines.
4. A missing User-Agent is assigned `UNKNOWN`.

This code is only for **demonstrating logging and classification**, not a full User-Agent parser or a reliable bot detection mechanism.

Save the file as **`UserAgentLogDemo.java`**:

```java
import java.util.Locale;

public class UserAgentLogDemo {
    private static final int MAX_CODE_POINTS = 80;

    private static String sanitizeForTextLog(String raw) {
        if (raw == null || raw.isBlank()) {
            return "(missing)";
        }

        StringBuilder out = new StringBuilder();
        int count = 0;

        for (int offset = 0;
                offset < raw.length() && count < MAX_CODE_POINTS;
                count++) {
            int cp = raw.codePointAt(offset);
            offset += Character.charCount(cp);

            boolean unsafe = Character.isISOControl(cp)
                    || Character.getType(cp) == Character.FORMAT
                    || (cp >= 0xD800 && cp <= 0xDFFF)
                    || cp == 34   // double quote
                    || cp == 92   // backslash
                    || cp == 0x2028
                    || cp == 0x2029;

            out.append(unsafe ? "_" : new String(Character.toChars(cp)));
        }

        return out.toString();
    }

    private static String family(String safe) {
        if ("(missing)".equals(safe)) {
            return "UNKNOWN";
        }

        String s = safe.toLowerCase(Locale.ROOT);
        if (s.startsWith("curl/")) {
            return "CLI";
        }
        if (s.contains("chrome/")
                || s.contains("firefox/")
                || s.contains("safari/")) {
            return "BROWSER";
        }
        if (s.contains("bot")) {
            return "BOT_CLAIM";
        }
        return "OTHER";
    }

    public static void main(String[] args) {
        String[] samples = {
                "curl/8.5.0",
                "Mozilla/5.0 (Linux) Chrome/120.0",
                "demo" + (char) 10 + "WARN forged",
                null
        };

        for (int i = 0; i < samples.length; i++) {
            String safe = sanitizeForTextLog(samples[i]);
            System.out.println("req=" + (i + 1)
                    + " family=" + family(safe)
                    + " ua=" + safe);
        }
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac UserAgentLogDemo.java
java UserAgentLogDemo
```

**`stdout`** output:

```text
req=1 family=CLI ua=curl/8.5.0
req=2 family=BROWSER ua=Mozilla/5.0 (Linux) Chrome/120.0
req=3 family=OTHER ua=demo_WARN forged
req=4 family=UNKNOWN ua=(missing)
```

### 4.1. Why does the program produce this output?

- `raw == null || raw.isBlank()` handles missing or blank headers without causing a `NullPointerException`.
- The limit of `80` is the **number of Unicode code points** considered for output; it is **not a byte-size limit for the HTTP header**.
- `codePointAt` + `Character.charCount` avoids splitting a valid UTF-16 surrogate pair in half; invalid code points are replaced with `_`.
- Control characters, double quotes, backslashes, and certain format characters are replaced with `_`; therefore, `demo` + newline + `WARN forged` becomes `demo_WARN forged`, without creating another log line.
- Classification by token matching is only a **heuristic**. A `curl` request can send a string containing `Chrome/` and be labeled `BROWSER`.
- Using `Locale.ROOT` ensures lower-casing is unaffected by the server's locale.

**Limitations:** the example sanitizer does not replace a JSON encoder, logging pipeline escaping standards, standard browser parsing, or privacy policies. Do not use `BROWSER`/`BOT_CLAIM` results for authorization. In production, enforce a **max header size at the gateway/container before running any parser**, because truncating output does not make extremely large input harmless upfront.

### 4.2. Why not use raw `User-Agent` to build file names?

A UA can be very long or contain special characters. If you use UA as an unbounded file name, index, Kafka topic, queue, or cache key, clients can cause the system to create an uncontrolled number of resources, trigger path injection, or exhaust memory/disk space. Map it to a **server-defined finite set of groups**, and validate against an allowlist for any dynamic destination.

## 5. Spring Boot 3+ Servlet Stack: Logging User-Agent Groups

In Spring MVC, you can use `OncePerRequestFilter` to extract the UA and log a normalized event. The snippet below **does not run standalone with JDK**: it requires Spring Boot 3+ (Servlet stack), Spring Web, SLF4J, and a compatible logging provider/backend.

File **`UserAgentLoggingFilter.java`** in a suitable Spring Boot application:

```java
package com.example.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
public class UserAgentLoggingFilter extends OncePerRequestFilter {
    private static final Logger LOG =
            LoggerFactory.getLogger(UserAgentLoggingFilter.class);

    private static String family(String raw) {
        if (raw == null || raw.isBlank()) {
            return "UNKNOWN";
        }

        String s = raw.toLowerCase(Locale.ROOT);
        if (s.startsWith("curl/")) {
            return "CLI";
        }
        if (s.contains("chrome/")
                || s.contains("firefox/")
                || s.contains("safari/")) {
            return "BROWSER";
        }
        return "OTHER";
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String uaFamily = family(request.getHeader("User-Agent"));
        long start = System.nanoTime();

        try {
            filterChain.doFilter(request, response);
        } finally {
            Object mapped = request.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

            String route = mapped instanceof String
                    ? (String) mapped
                    : "UNMATCHED";

            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - start);

            LOG.info(
                    "method={} route={} uaFamily={} durationMs={}",
                    request.getMethod(), route, uaFamily, durationMs);
        }
    }
}
```

### 5.1. Analysis and Limitations of the Integration Snippet

1. The filter reads the `User-Agent` request header properly, but **logs only the group** instead of the raw UA.
2. The route name is retrieved from `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` once Spring MVC has resolved the mapping. The value may be `/api/orders/{id}` rather than a raw path containing individual IDs.
3. For unmatched requests (404), early errors, or special dispatches, this attribute may not exist and the route becomes `UNMATCHED`.
4. `finally` runs when `filterChain.doFilter` returns or throws an exception, but does not guarantee an event is persisted at the final sink.
5. `durationMs` measures the time from entering the filter to exiting it. For **async requests/streaming**, this moment may not be when the response actually completes.
6. The example does not log `response.getStatus()` because exceptions might be handled at another layer after the filter exits; at that point, the observed status may not be the final result.
7. If you need accurate access logs for status, request completion, and async lifecycle, choose instrumentation/hooks at the point when the response truly completes.
8. If the system already has canonical access logs at the gateway/container, avoid duplicating them in both the filter and the server without a clear need.

`@Component` requires the package to be scanned by Spring; imports depend on the project. In a WebFlux system, you must use the corresponding reactive APIs rather than copying this Servlet filter as-is.

## 6. Log Once or Attach to Every Event?

Typically, there are two approaches:

**Approach A — one access event per request:** log `method`, `route`, `status`, `duration`, `requestId`, `uaFamily`; other logs correlate via the request ID. This is usually easier to control for volume and privacy.

**Approach B — attach UA to context:** with SLF4J + a provider supporting MDC, you can attach `ua.family` so the encoder includes it in related logs.

```java
import org.slf4j.MDC;

// Integration code: uaFamily is the validated classification value.
MDC.put("ua.family", uaFamily);
try {
    processRequest();
} finally {
    MDC.remove("ua.family");
}
```

This is a **code snippet**, not a standalone JDK program; it assumes `processRequest()` and the variables are already declared. In Logback, a pattern containing `%X{ua.family}` can display the MDC value if configured in the corresponding encoder.

Notes:

- MDC does not generate an audit/access event on its own; the application must still make logger calls.
- Thread pools reuse worker threads. **You must clear MDC** in `finally` to prevent data from a previous request from leaking into the next request.
- `CompletableFuture`, thread executors, callbacks, and WebFlux may switch to other threads; context does not propagate automatically and requires framework propagation mechanisms.
- Putting raw UA into MDC and copying it into every log can inflate data volume and expand information exposure.
- SLF4J API, Logback, and Log4j 2 have different configurations; do not mix backend XML classes.

## 7. Security: Treat User-Agent as Untrusted Input

### 7.1. Spoofing: Self-Declared Strings Do Not Verify Clients

For example, a user can set any UA:

```bash
curl -A "Mozilla/5.0 Chrome/120.0" https://example.test/
```

This command illustrates how to set User-Agent with `curl`; **it does not assert that the URL is a live environment**. A request made by curl can still claim to be Chrome. Similarly, a bot claiming `ExampleBot/1.0` does not prove it is a verified crawler.

Do not build logic like:

```java
// Security flaw: rawUserAgent is not authentication evidence.
if (rawUserAgent.contains("TrustedBot")) {
    skipSecurityCheck();
}
```

This snippet illustrates behavior **to avoid**, not a complete program. Use authentication/authorization, tokens, WAF policies, network controls, or proper bot verification mechanisms for security decisions. User-Agent can be a secondary signal, never a pass.

### 7.2. Log Injection and Log Forging

An input containing newlines, carriage returns, or control characters can create content that tricks readers into thinking there are multiple log events:

```text
User-Agent: demo
ERROR Payment accepted for another user
```

Modern HTTP containers may reject invalid CR/LF at the protocol layer, but defense-in-depth still requires **never trusting HTTP header data**: systems have multiple proxies/parsers/collectors, and logs may come from other sources.

How to handle it:

1. Limit request/header sizes at the server/gateway.
2. Log only genuinely needed fields; prefer classified groups.
3. Use structured logging with an encoder/serializer that properly escapes JSON.
4. If you must log raw UA in text logs, sanitize control characters, quotes, newlines, and enforce length limits.
5. Never let headers choose the destination file/topic/index or dynamic appender name.
6. Test with payloads containing newlines, Unicode control characters, quotes/backslashes, and oversized inputs.

**SLF4J `{}` is only a formatting placeholder**; it does not sanitize input, perform JSON escaping, or mask secrets. Sanitization for safe display also **does not make UA trustworthy for authorization**.

### 7.3. Privacy and Fingerprinting

UA can reveal or help infer the browser, platform, version, and application characteristics. Combined with IP, cookies, account, path, and timestamp, the data can support **fingerprinting** users/devices.

Principles:

- Restrict raw UA if only a coarse category is needed.
- Do not store UA alongside unnecessary personally identifiable information.
- Define log read permissions, retention, collection purpose, and authorized consumers.
- If raw data must be kept for diagnostics, limit its retention period and store it separately.
- Avoid copying UA into every log, message broker, trace baggage, or metrics system.
- Do not assume UA never contains secrets: custom clients might put unauthorized information into the string.

A truncated and escaped string can still carry sensitive data. **Data minimization** is a separate policy and cannot be replaced by a simple sanitizer.

## 8. User-Agent Client Hints and Client Inconsistency

Some browsers provide Client Hints:

```text
Sec-CH-UA
Sec-CH-UA-Mobile
Sec-CH-UA-Platform
```

Browsers may reduce the granularity of the traditional UA; the availability of client hints varies by browser, policy, origin, and version. Therefore:

- Do not require all requests to include `Sec-CH-UA`.
- Do not treat Client Hints as authentication evidence.
- Do not log excessive device signals without a specific purpose.
- Provide a fallback for missing values and classify as `UNKNOWN`.
- If the application needs compatibility checks, test against real browsers/SDKs rather than guessing purely from strings.

Do not rely on a hand-written regex to assert exact OS and browser versions. When detailed User-Agent parsing is truly necessary, use an evaluated parser and control resources, versions, and false positives; the result is still an **inference from self-declared data**.

## 9. Performance and Cardinality

Raw User-Agent generates a huge number of distinct strings: browsers with different versions, self-declared bots, SDKs, custom clients, etc. Using raw UA as a **metric label** causes cardinality explosion:

```text
http_requests_total{user_agent="Chrome/120 ..."}
http_requests_total{user_agent="Chrome/121 ..."}
http_requests_total{user_agent="CustomClient/xyz"}
```

Replace it with bounded labels:

```text
http_requests_total{ua_family="BROWSER"}
http_requests_total{ua_family="CLI"}
http_requests_total{ua_family="OTHER"}
http_requests_total{ua_family="UNKNOWN"}
```

The metric names above are **examples**, not built-in metrics in every framework. If browser major version analysis is needed, consider bounded groups or offline reporting rather than arbitrarily increasing dynamic labels.

Other performance principles:

- Do not parse UA with expensive regexes on unbounded input.
- Do not cache every raw UA value indefinitely; clients can continuously send new strings.
- Do not repeat raw UA across dozens of log lines for the same request.
- Control input size at the HTTP server, not just by truncating output after processing.
- Measure CPU, allocation, GC, and latency when enabling a parser on the hot request path.
- Do not store raw UA as a dynamically generated resource name, file name, or queue name per request.

If logs are sent through an async queue, high log volume can fill the queue; in that case, blocking/dropping policies will affect latency and reliability. Reducing UA data volume can help, but it does not replace designing a log pipeline sized for the load.

## 10. User-Agent with Request ID, Route, and Status

For error investigation, a structured access event might look like this:

```json
{
  "event": "HTTP_REQUEST_COMPLETED",
  "requestId": "req-1007",
  "httpMethod": "GET",
  "route": "/api/orders/{id}",
  "status": 404,
  "durationMs": 18,
  "userAgentFamily": "CLI"
}
```

When logging across multiple services, request ID/trace ID helps find events in the same processing chain. However, if `requestId` comes from a client-sent HTTP header, it is also **not inherently trustworthy**; the system must validate or generate a canonical ID at the gateway according to policy. Request ID does not replace an authenticated principal.

Prefer **route template** `/api/orders/{id}` over raw path `/api/orders/123` to reduce cardinality and information exposure. Raw query strings may contain tokens or PII; do not dump them into logs just because you are observing User-Agent.

Status and duration must also be computed at the right time. A Servlet filter logging in `finally` might not see the final status after exception handling or async completion. For standard access logging requirements, use instrumentation at the point where the request actually finishes.

## 11. Example HTTP Commands for Testing

If you have a test server on your machine with a corresponding endpoint, you can send requests with custom UAs:

```bash
curl -A "LearningClient/1.0" http://localhost:8080/health
curl -A "curl/8.5.0" http://localhost:8080/health
```

These only illustrate how to set the header; **they do not assert that a server is running on port 8080 or has a `/health` endpoint**. Under the Java example's heuristic, `LearningClient/1.0` maps to `OTHER` and `curl/8.5.0` maps to `CLI`. These labels do not prove the real client.

When testing a real application, capture events at the appender/test collector and verify the exact fields and event count; do not just grep for an arbitrary string in the terminal.

## 12. System Testing: Mandatory Cases

| Case | What to verify |
| --- | --- |
| Missing / null User-Agent | No NPE; consistently logs `UNKNOWN` or `MISSING` |
| Blank or whitespace-only UA | Does not become a fake identification field |
| `curl/...` UA | Classified as CLI according to defined rules |
| UA with multiple browser tokens | Does not treat `Mozilla/5.0` as the primary browser |
| UA claiming to be Chrome from curl | Does not escalate privileges or bypass security controls |
| UA with newline/control | Does not forge log lines; JSON remains valid |
| Very long UA | Enforces limit and policy; does not consume excessive RAM |
| Unusual Unicode strings | Does not break encoder/collector or render incorrectly |
| Header modified by proxy | Known value at each layer and request correlation |
| 404 or exception request | Route/status reflects observability boundaries |
| Async/streaming request | Duration matches the actual request lifecycle |
| 10,000 distinct UAs | Does not create thousands of unbounded metric labels/cache keys |
| Detailed device info | Does not exceed purpose, read permissions, and retention |
| Multiple layers logging access | Does not double-count a single request |
| Slow or failing collector | Clear drop/block policy and backlog monitoring |

Test both **unit tests** for the sanitizer/classifier and **integration tests** for the Filter/Servlet lifecycle; for critical pipelines, add end-to-end tests from gateway through collector. Document heuristic false positives/negatives, as browsers/SDKs can change their UA over time.

## 13. Common Mistakes

### "User-Agent tells us who is using the system"

False. It is self-declared client information, often shared and easily spoofed. True identity requires an authentication mechanism.

### "A UA containing the word bot is a verified bot"

False. `BOT_CLAIM` only represents a string claiming to be a bot. Access decisions must rely on a proper verification process.

### "SLF4J placeholders already prevent log injection"

False. Placeholders do not perform full escaping, size limiting, or redaction. Use a proper encoder/serializer and input data policy.

### "Logging the full UA in MDC and every service log is best"

This easily duplicates data, increases costs, and introduces privacy risks. Usually, a single access event and request ID are sufficient.

### "A filter always knows the final status and duration"

False if exception/async processing has not finished when the filter exits. Instrumentation is needed at the right lifecycle point.

### "Using raw UA as a metric label is very convenient"

Raw UA has high cardinality; use `ua.family` or a bounded group instead.

### "A UA string cannot contain sensitive data"

Custom clients can put anything into it; combined with other data, it also creates fingerprinting risks.

### "Once sanitized, UA can be used for authorization"

Sanitization only protects logging/display to a degree; it does not prove the truthfulness of the header.

### "No need to limit headers because text logs are truncated"

Truncating output does not ensure very large inputs are handled safely at the gateway, parser, or cache. Enforce limits at the HTTP layer first.

## 14. Implementation Checklist

- [ ] Define the purpose of collecting User-Agent and where canonical access logs are written.
- [ ] Read from `HttpServletRequest.getHeader("User-Agent")` or the corresponding API for your web stack.
- [ ] Handle `null`, blank, overly long, multiple headers, and hard-to-parse inputs.
- [ ] Never use UA for authentication, authorization, or bot verification.
- [ ] Limit header/input size, sanitize/escape, use structured logging, and guard against log injection.
- [ ] Prefer `ua.family` for metrics; never use raw UA as a dynamic label.
- [ ] Avoid repeating raw UA in every event or unnecessarily in MDC.
- [ ] Correlate via request ID/trace ID and safe route templates.
- [ ] Ensure status/duration are measured at the appropriate request completion point, especially for async.
- [ ] Check whether logs at gateway/container/app are duplicated or have differing values.
- [ ] Enforce read permissions, retention, data minimization, and privacy.
- [ ] Test from Java unit code to collector, including spoofing, long inputs, newlines, async, and overload.

**Conclusion:** User-Agent is a **useful field for web request observability and diagnostics**, but it only reflects a **client's claim**, not proof of identity or real software. Quality logging requires **sufficient normalization, bounding and protecting inputs, avoiding high cardinality, correlating request context, and respecting privacy**.
