# Request Header Size Limits and Per-Server Configuration in Spring Boot

## 1. Why Do HTTP Request Headers Need Size Limits?

HTTP requests carry metadata through headers such as `Host`, `Authorization`, `Cookie`, `Accept`, `User-Agent`, `Content-Type`, `Forwarded`, or custom fields. The embedded web server must read and decode headers before the request is dispatched to a Spring MVC controller, a Spring WebFlux handler, or business logic components.

Oversized headers can appear when cookies accumulate, JWTs carry many claims, proxies attach trace/auth information, or clients send long custom headers. If the server does not enforce appropriate limits, large amounts of header data across many concurrent requests can increase memory consumption, overload parsers, or create conditions for Denial of Service (DoS) attacks.

The goals of configuring header limits are:

- Allow legitimate requests within technical and business boundaries.
- Prevent requests with abnormally large headers from consuming excessive resources.
- Keep limits consistent across clients, CDN/WAF, reverse proxies, API gateways, and the embedded server.
- Properly distinguish header limits from request body, file upload, form, and URL limits.
- Understand the differences among Tomcat, Jetty, Undertow, and Reactor Netty.

**Note:** Headers rejected by the HTTP parser usually have not yet reached controllers or `@ControllerAdvice`; debugging should begin with web server or proxy logs, not just Java business code.

## 2. How Is Header Size Calculated?

An HTTP/1.1 request has a structure like:

```http
GET /api/orders?status=paid HTTP/1.1
Host: example.com
Authorization: Bearer eyJhbGciOi...
Cookie: session=abc123
Accept: application/json

```

Distinguish between the different types of limits:

| Limit | Scope | Example |
|---|---|---|
| Request header size | Allowed amount of HTTP header data, according to each server's rules | Total of all headers or size of an individual field |
| Single header field size | Size of one specific header | One long `Cookie` field |
| Header count | Maximum number of header fields | 200 fields even if each field is very short |
| Request line / initial line | Method + request-target + HTTP version in HTTP/1.x | `GET /path?... HTTP/1.1` |
| Request body | Data inside the payload, JSON, multipart, files | A 10MB file is not in the header |

The value `16KB` in Spring Boot uses the `DataSize` type and equals **16 × 1024 = 16,384 bytes**. Bytes on the wire are not always equal to Java's `String.length()`. Some servers also count delimiters, whitespace, CRLF, and the request line.

In particular, Spring Boot documentation explicitly states that **Tomcat applies the threshold to the sum of the request line and all header names and values**; **Netty applies the threshold individually to each header field during decoding**. Therefore, the same `16KB` setting does not guarantee the exact same outcome across all embedded servers.

## 3. Common Configuration in Spring Boot 3.x and 4.x

Standard property:

```properties
# application.properties
server.max-http-request-header-size=16KB
```

Equivalent in YAML:

```yaml
# application.yml
server:
  max-http-request-header-size: 16KB
```

According to the Common Application Properties reference of Spring Boot 3.5 and 4.0, the default value is **8KB**. This is Spring Boot's property default; do not confuse it with the default of a standalone server not configured by Spring Boot.

The value can come from an environment variable:

```properties
server.max-http-request-header-size=${HTTP_REQUEST_HEADER_LIMIT:16KB}
```

Or be passed via the command line when you have a Spring Boot JAR:

```bash
java -jar app.jar --server.max-http-request-header-size=16KB
```

If using multiple profiles, verify the effective configuration of the active profile. The `server.max-http-request-header-size` property is mapped by Spring Boot to the corresponding embedded server factory, but how requests are decoded and rejected is decided by the server.

**When should you use the property?** For general request header limit requirements, always prefer this property before writing a custom `WebServerFactoryCustomizer`. A customizer is appropriate when you need low-level API settings not exposed by properties, such as configuration specific to a connector or server protocol.

### Changes Compared to Spring Boot 2.x

Older examples may use:

```properties
server.max-http-header-size=16KB
```

Spring Boot 3.0 replaced it with `server.max-http-request-header-size` to resolve previous inconsistency. The old name affected both request and response on Tomcat, whereas on Jetty, Netty, and Undertow it mainly applied to requests. The new name focuses on the **request header** limit.

When upgrading from Spring Boot 2.x to 3.x/4.x, switch to the new property and retest on your actual web server. Do not expect a request header setting to simultaneously control response headers.

## 4. Comparing Embedded Servers

| Server | Common Stack | How Request Header Limit Is Applied | What to Check |
|---|---|---|---|
| **Tomcat** | Spring MVC / Servlet | Total of request line and headers, including HTTP/1.x overhead | `maxHttpRequestHeaderSize`, buffers, and memory |
| **Jetty** | Spring MVC / Servlet; some reactive adapters | HTTP parser configuration via `HttpConfiguration` | Request and response have separate settings |
| **Undertow** | Servlet on supported versions | `UndertowOptions.MAX_HEADER_SIZE` | Byte limit differs from header count limit |
| **Reactor Netty** | Spring WebFlux | As described by Boot: per header field limit | Initial line and HTTP/2 have different limits |

Server libraries change between versions. This table describes principles in typical Spring Boot environments; check your actual HTTP version and dependencies before committing to exact boundary behavior.

## 5. Tomcat: Sum of Request Line and Headers

Tomcat's HTTP Connector has the `maxHttpRequestHeaderSize` parameter. For HTTP/1.x, the limit applies to the received bytes of the request line plus headers, including field names, field values, whitespace, line endings, and related overhead.

Hypothetical example:

- Request line and typical headers: about 1.5KB.
- `Authorization`: about 5KB.
- `Cookie`: about 6KB.

The total already exceeds 12KB; such a request can exceed Tomcat's 8KB limit even though no single field is over 8KB.

Spring Boot configuration:

```properties
server.max-http-request-header-size=16KB
```

When you need a separate response header limit:

```properties
server.max-http-request-header-size=16KB
server.tomcat.max-http-response-header-size=16KB
```

The second line controls Tomcat's response header limit in supported Boot versions, for example responses with many `Set-Cookie` headers or a long `Location`; it does not help large request headers get accepted.

Tomcat has other Connector-level parameters such as `maxHeaderCount` to limit the number of headers. That is a count limit, distinct from `maxHttpRequestHeaderSize`. Use `WebServerFactoryCustomizer<TomcatServletWebServerFactory>` only when you truly need to adjust connector properties not exposed via properties, and ensure imports/methods match your Spring Boot version.

**Resource warning:** Apache Tomcat documentation emphasizes that a high `maxHttpRequestHeaderSize` increases buffer allocation for in-progress requests. Raising it to 1MB across hundreds of concurrent requests can place heavy pressure on the heap. Do not set multi-MB thresholds merely to accommodate unreasonable cookies/JWTs.

If Tomcat is deployed **externally** as a servlet container managing a WAR, listener/Connector configuration is the external server's responsibility. Spring Boot's embedded server properties should not be treated as a universal mechanism to control every external Tomcat instance.

## 6. Jetty: Separate Request and Response Configuration

Jetty provides the APIs `HttpConfiguration.setRequestHeaderSize(int)` and `setResponseHeaderSize(int)`; exact application depends on Jetty version and transport.

For request headers, the common Spring Boot configuration remains:

```properties
server.max-http-request-header-size=16KB
```

In supported Spring Boot versions, there is a Jetty-specific property for responses:

```properties
server.jetty.max-http-response-header-size=16KB
```

Do not confuse request size with response size; raising the response limit only allows the server to produce larger response headers and does not change how incoming client requests are parsed.

If you need a specialized Jetty customizer, locate the exact web server factory and `HttpConfiguration` API for the running version. Do not copy code written for Jetty 9/11 assuming full compatibility with Jetty 12. Prefer configuring via common properties before touching connector internals.

## 7. Undertow: Byte Limit Differs from Header Count Limit

Undertow has `UndertowOptions.MAX_HEADER_SIZE`, which expresses the HTTP request header size limit in bytes. In Spring Boot, the baseline configuration is:

```properties
server.max-http-request-header-size=16KB
```

Undertow also has a header count limit:

```properties
server.undertow.max-headers=200
```

These two settings control two different things:

- A request containing 220 short headers may be blocked by `max-headers=200`, even if total bytes are below the byte limit.
- A request with only a few very long headers can still be blocked by the byte size limit.

Properties like `server.undertow.max-cookies` or `server.undertow.max-parameters` are also independent; they cannot be replaced by the header byte limit.

When `server.undertow.options.server.*` is needed, verify the `UndertowOptions` name and property binding against your Spring Boot/Undertow version. Avoid overriding low-level options when a common property already meets the need.

## 8. Reactor Netty and Spring WebFlux

Spring Boot normally uses Reactor Netty as the default server for Spring WebFlux applications. For Reactor Netty, `server.max-http-request-header-size` is documented by Spring Boot as a limit applied **per header field** rather than the total as in Tomcat. Consequently, a request with many small fields may behave differently compared to the same request going through Tomcat.

```properties
server.max-http-request-header-size=16KB
```

A separate option in Spring Boot is:

```properties
server.netty.max-initial-line-length=4KB
```

This property relates to the length of the initial request line and does not replace header field size. If the URL/query string is too long, raising the header limit may not resolve the parser error.

Reactor Netty has decoder APIs such as `maxHeaderSize(int)` on `HttpRequestDecoderSpec`. When configuring deeply via a customizer, base it on the actual Reactor Netty version and test its impact on HTTP/1.1/HTTP/2 rather than assuming decoder APIs are identical across all releases.

## 9. HTTP/1.1 and HTTP/2 Do Not Measure Identically

HTTP/1.1 transmits the request line and header fields in text protocol syntax. HTTP/2 uses HPACK-compressed header blocks and pseudo-headers such as `:method`, `:path`, `:scheme`, and `:authority`.

You cannot take compressed bytes on an HTTP/2 wire and compare them directly against Tomcat's HTTP/1.1 request header limit. An HTTP/2 server/proxy can enforce a limit on the decoded header list size and reject requests in its own way.

To verify whether an issue occurs only on HTTP/2, test the same request over both HTTP versions and inspect protocol-specific logs. Do not rely on a single calculation on `Cookie` or `Authorization` while overlooking pseudo-headers or headers added by proxies.

## 10. Reverse Proxies, Gateways, CDNs, and WAFs

In production, a typical path is:

```text
HTTP client
   |
CDN / WAF
   |
Ingress / API gateway / Reverse proxy
   |
Embedded Tomcat / Jetty / Undertow / Reactor Netty
   |
Spring MVC / WebFlux
```

Each layer can enforce different limits. For example:

- Gateway allows only 8KB; Spring Boot allows 16KB: a 12KB request is blocked at the gateway.
- Gateway allows 32KB; Tomcat allows 8KB: a 12KB request can reach the backend and then be rejected by Tomcat.
- Proxies add multiple `Forwarded`, `X-Forwarded-*`, or tracing headers: total headers received at the backend can be larger than what the client sent.

In Nginx, directives such as `client_header_buffer_size` and `large_client_header_buffers` have their own accounting for the request line or individual fields. Do not treat an Nginx directive as strictly equivalent to a Spring Boot property. For Envoy, Traefik, or Kubernetes Ingress Controllers, consult the documentation for the exact product and version.

When troubleshooting production, observe statuses and logs at each layer, along with request IDs, server types, and HTTP versions. The lowest threshold along the path is usually where the request is rejected first.

## 11. How Does the Application Respond When Headers Exceed the Limit?

HTTP defines status `431 Request Header Fields Too Large`, but actual behavior is inconsistent across parsers, servers, and proxies:

- Some systems return `400 Bad Request` with a message that headers are too large.
- Some systems return `431 Request Header Fields Too Large`.
- Some systems close the connection, causing the client to see `connection reset`, `EOF`, or a protocol error.
- HTTP/2 may handle it via stream reset or an implementation-specific rejection mechanism.

Therefore, **do not write rigid tests asserting that oversized headers will always return 431**. Verify the actual behavior of the deployed stack.

When the parser blocks a request before creating a Spring MVC/WebFlux handler, `@RestController`, `Filter`, or `@ControllerAdvice` may never see the request. Inspect server access logs, proxy logs, decoder stacktraces, and network traces instead of only debugging the controller.

## 12. Creating a Test Spring Boot Application

Assuming a Spring Boot 3.x or 4.x project already has `spring-boot-starter-web` and `@SpringBootApplication`, add a controller:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
```

File `src/main/resources/application.properties`:

```properties
server.port=8080
server.max-http-request-header-size=8KB
```

Use the project's Maven Wrapper:

```bash
./mvnw spring-boot:run
```

Test a short request:

```bash
curl -i http://localhost:8080/ping
```

If the application starts properly, the endpoint returns the body:

```text
pong
```

The controller snippet is not a standalone Java program; it must be run inside a Spring Boot project with the web starter and main class. Do not confuse the body output `pong` with the full response/status/headers or Spring Boot logs.

## 13. Testing Long Headers with Java 17 Without External Libraries

Use a standalone client to send the `X-Header-Size-Probe` header with a value made of many ASCII `a` characters. File **`HeaderLimitProbe.java`**:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.io.IOException;

public class HeaderLimitProbe {

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                "Usage: java HeaderLimitProbe <url> <headerValueLength>");
            System.exit(2);
        }

        String url = args[0];
        int length = Integer.parseInt(args[1]);
        if (length < 0 || length > 100_000) {
            throw new IllegalArgumentException(
                "headerValueLength must be between 0 and 100000");
        }

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .build();

        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                .header("X-Header-Size-Probe", "a".repeat(length))
                .GET()
                .build();

        try {
            HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());
            System.out.println("HTTP status: " + response.statusCode());
        } catch (IOException e) {
            System.out.println(
                "I/O error: " + e.getClass().getSimpleName());
        }
    }
}
```

The code uses Java 17 APIs and compiles standalone without Spring dependencies. `HttpClient` is not placed in a try-with-resources block because Java 17 does not yet have a `close()` method like newer JDK versions.

Compile:

```bash
javac HeaderLimitProbe.java
```

Run against the example Spring Boot server on port 8080:

```bash
java HeaderLimitProbe http://localhost:8080/ping 1000
java HeaderLimitProbe http://localhost:8080/ping 12000
```

Results depend on the server, endpoint, and environment. For a valid request where the server returns `200`, the program prints:

```text
HTTP status: 200
```

If the header is rejected, you may see `400`, `431`, or an I/O error; there is no single fixed output for exceeding the threshold. `headerValueLength` is the number of `a` characters in **one field**, not counting the field name, delimiters, request line, and headers generated by the JDK.

To test boundaries, run both smaller and larger cases near the limit and inspect logs. On Tomcat, the sum of all parts may cross the limit before `X-Header-Size-Probe` alone reaches 8KB. On Reactor Netty, pay attention to the per-field limit noted in the Spring Boot documentation.

## 14. Do Not Confuse with Body, Multipart, and Response Headers

| Configuration / Concept Name | What It Controls |
|---|---|
| `server.max-http-request-header-size` | HTTP request header size, per server rules |
| `server.tomcat.max-http-response-header-size` | Tomcat response header size |
| `server.jetty.max-http-response-header-size` | Jetty response header size |
| `server.netty.max-initial-line-length` | Netty initial request line length |
| `server.undertow.max-headers` | Number of headers Undertow accepts |
| `server.tomcat.max-http-form-post-size` | Form POST content processed by Tomcat |
| `spring.servlet.multipart.max-request-size` | Total multipart request size in the Servlet stack |
| `spring.codec.max-in-memory-size` | Buffer used for codecs in applicable cases |

For example, a rejected 10MB file upload usually involves multipart/body limits and is not solved by raising the header limit. Conversely, a very long JWT in `Authorization` can trigger a request header error even when the body is empty.

## 15. Common Errors and How to Resolve Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Configured 16KB but still failing | Proxy/WAF is still at 8KB or the property is not effective | Check logs at each hop and verify effective config/profiles |
| Tomcat blocks even though each header is under 16KB | Tomcat sums the request line and all headers | Measure total bytes, trim unnecessary Cookies/JWTs |
| Undertow blocks many small headers | `server.undertow.max-headers` limits header count | Check field count and byte limit separately |
| Netty behaves differently from Tomcat | Limits are enforced by different parsers | Test on the exact embedded server/HTTP version |
| `400` without controller running | Request was rejected by the parser | Check connector/decoder or proxy logs |
| Upload rejected after raising header limit | Separate body or multipart limits | Check `spring.servlet.multipart.*` and server body settings |
| Only HTTP/2 fails | Header list/decoder and pseudo-headers differ from HTTP/1.1 | Check HTTP/2 config on both proxy and backend |
| Property no longer works after Boot upgrade | Using old `server.max-http-header-size` | Switch to `server.max-http-request-header-size` |
| Raising limit heavily increases heap/CPU | Request buffers and abnormal traffic | Lower threshold, shrink header sources, measure real load |

### Systematic Debugging Process

1. Record the request ID, HTTP version, status/connection error, and environment.
2. Identify whether the request is blocked at CDN/WAF, gateway, or the Spring Boot embedded server.
3. Check the header count, largest single field size, total bytes, and request line length.
4. Identify the exact server (Tomcat/Jetty/Undertow/Reactor Netty) and its version.
5. Read the effective `server.max-http-request-header-size` along with proxy configuration.
6. Check whether cookies, JWTs, or trace headers carry redundant data.
7. Shrink header sources first; raise limits only with a clear operational justification.
8. Test normal, near-threshold, and over-threshold requests; monitor memory and error rates after changes.

Do not log raw `Authorization`, `Cookie`, or sensitive tokens just to measure size; you can log the **length** and a safe request identifier instead of the content.

## 16. Deployment Checklist

- Identify the Spring Boot version, embedded server, and whether HTTP/1.1 or HTTP/2 is used.
- Use `server.max-http-request-header-size` as the baseline configuration for request headers.
- Understand that the Spring Boot 3.5/4.0 default is 8KB; adjust according to real needs.
- Understand the difference in limit calculation between Tomcat and Netty.
- Remember that request line, header count, response headers, and body are separate limits.
- Verify configuration of all reverse proxies/CDNs/WAFs/Ingress controllers.
- Test valid, boundary, and over-limit requests on the actual runtime.
- Avoid setting excessively high thresholds that increase memory use and DoS risk.
- Prioritize shrinking Cookies, JWTs, and tracing headers before raising thresholds.
- Record test results and monitor 400/431/I/O errors after deployment.

## 17. References

- Spring Boot 3.5 — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 4.0 — Common Application Properties: https://docs.spring.io/spring-boot/4.0/appendix/application-properties/index.html
- Spring Boot 3.0 Migration Guide (renamed header property): https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide
- Apache Tomcat 10.1 — HTTP Connector: https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
- Jetty 12 — HttpConfiguration: https://javadoc.jetty.org/jetty-12/org/eclipse/jetty/server/HttpConfiguration.html
- Undertow — `UndertowOptions.MAX_HEADER_SIZE`: https://github.com/undertow-io/undertow/blob/main/core/src/main/java/io/undertow/UndertowOptions.java
- Reactor Netty — HttpDecoderSpec: https://docs.spring.io/projectreactor/reactor-netty/docs/current/api/reactor/netty/http/HttpDecoderSpec.html
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110