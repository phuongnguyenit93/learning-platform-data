# Request body limits

The GraphQL HTTP endpoint receives requests from clients before parsing operations and executing resolvers. With POST, the body is typically a JSON object containing `query`, `operationName`, `variables`, and `extensions`. Without a body size limit, clients can send oversized payloads that increase memory usage, CPU consumption, parsing time, and pressure on downstream services.

In Spring for GraphQL, request body limits are part of HTTP operations. Set limits at the ingress/reverse proxy or HTTP server, then add appropriate checks in the application. WebFlux codec configuration can bound how much data is buffered during decoding; a filter checking `Content-Length` can reject requests early when their declared length is too large. Each mechanism has its own scope and should not be confused with one another.

Body limits also do not replace GraphQL complexity controls. A short query can trigger thousands of resolvers or database queries; conversely, large variables can produce a large body even when the query document is very simple. The API must guard both HTTP payload size and GraphQL execution cost.

## 1. What does a GraphQL HTTP request body contain?

A JSON POST request typically has the structure:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json

{
  "query": "query Product($id: ID!) { product(id: $id) { id name } }",
  "operationName": "Product",
  "variables": {
    "id": "p-100"
  },
  "extensions": {}
}
~~~

Body size is measured across the entire transmitted JSON content, not just the `query` string. `variables` can contain large input lists, long strings, or nested objects. `extensions` can also carry metadata for persisted queries or extension protocols.

Components to consider:

| Component | Content | Risk when oversized |
| --- | --- | --- |
| `query` | GraphQL document | CPU-intensive parsing and validation; documents may contain many fields/aliases |
| `operationName` | Selected operation name | Usually small, yet still part of the body |
| `variables` | Argument/input values | May contain large lists, long strings, or deeply nested JSON |
| `extensions` | Extension metadata | Can bloat payloads if clients send arbitrary data |

Do not use the character count of `query` as the request body limit. HTTP bodies are measured in bytes; UTF-8 characters can occupy multiple bytes. The server/proxy must enforce byte limits on the actual payload.

## 2. Distinguishing body size, query size, and query cost

These are three distinct limits:

| Limit | Controls | Example |
| --- | --- | --- |
| HTTP request body size | POST body bytes | Maximum 1 MiB JSON |
| GraphQL document size | Length of the query document | Maximum 64 KiB query text |
| Query depth/complexity | Amount of GraphQL work that can be generated | Depth cap or cost score |

A request can exceed the body limit because `variables` contains tens of thousands of items, even though the query has only a few fields. Another request may have a small body yet a deeply nested query, repeated aliases, or repeated calls to expensive fields.

Therefore, you cannot just increase the body limit to fix complex query errors, nor rely solely on a depth limit to block huge JSON payloads. Each limit needs its own target.

## 3. Setting limits at the reverse proxy or ingress

A reverse proxy is the right place to block oversized requests before data reaches the application. It can enforce limits for both requests with `Content-Length` and requests streamed using chunked encoding.

Nginx example:

~~~nginx
server {
    listen 443 ssl;

    location /graphql {
        client_max_body_size 1m;
        proxy_pass http://spring-graphql-app;
    }
}
~~~

The `client_max_body_size` directive specifies the maximum allowed size of the client request body. When exceeded, Nginx returns HTTP 413 Request Entity Too Large and does not forward the request upstream.

1 MiB is only an illustrative value. Choose a threshold suited to your application's largest valid payload, such as a multi-line order import or batch update mutation. Setting the limit too low can break valid use cases; setting it too high weakens protection.

With the Nginx Ingress Controller, you can configure an annotation on the Ingress:

~~~yaml
metadata:
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "1m"
~~~

The annotation name depends on the ingress controller. If using Traefik, Envoy, a cloud load balancer, or an API gateway, configure that product's corresponding body limit. Do not assume Nginx Ingress annotations apply to every controller.

## 4. HTTP 413 and related statuses

HTTP 413 indicates that the request content is larger than the server or proxy is willing to accept. Clients should handle this status at the HTTP layer because requests may be rejected before GraphQL execution starts.

| Status | Meaning | Example cause |
| --- | --- | --- |
| 413 Content Too Large | Request body exceeds limit | JSON POST body larger than proxy/server cap |
| 400 Bad Request | Invalid request | Malformed JSON or improper framing |
| 415 Unsupported Media Type | Content-Type not supported | Sending body as `text/plain` instead of a media type supported by the endpoint |
| 414 URI Too Long | Request URI too long | GET query document or variables encoded in URL exceed URI limit |
| 431 Request Header Fields Too Large | Headers too large | Cookies or headers exceed limits |

Do not handle HTTP 413 using `DataFetcherExceptionResolver` or `@GraphQlExceptionHandler`. Those mechanisms operate inside GraphQL execution; requests rejected by a proxy or container may never reach the GraphQL engine.

Clients should distinguish HTTP transport errors from GraphQL `errors` inside the response body. Do not assume every error has a JSON shape containing `errors`.

## 5. Limiting at the Spring MVC application layer

With Spring MVC/Servlet, you can add a filter checking `Content-Length` to reject POSTs to the GraphQL endpoint early:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
public class GraphQlContentLengthFilter extends OncePerRequestFilter {

    private static final long MAX_BODY_BYTES = 1_048_576L;
    private static final String GRAPHQL_PATH = "/graphql";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        boolean graphQlPost =
            "POST".equalsIgnoreCase(request.getMethod())
                && GRAPHQL_PATH.equals(request.getServletPath());

        long contentLength = request.getContentLengthLong();

        if (graphQlPost && contentLength > MAX_BODY_BYTES) {
            response.sendError(
                HttpServletResponse.SC_REQUEST_ENTITY_TOO_LARGE,
                "GraphQL request body is too large");
            return;
        }

        filterChain.doFilter(request, response);
    }
}
~~~

This filter acts as an early checkpoint when a request declares `Content-Length`. If `Content-Length` exceeds the limit, the application returns 413 before GraphQL parses the body.

This is not a complete streaming limit: `getContentLengthLong()` can return `-1` when length is not declared, such as requests using chunked transfer encoding. The filter above will let that request pass through. Therefore, you still need an actual body limit at the reverse proxy or HTTP server. If the application is allowed to receive traffic directly without a proxy, add a byte-counting stream read limit or configure your container's native limits.

The `/graphql` path is an example. If the application changes `spring.graphql.path`, the filter must use the same actual endpoint path. When a context path or custom servlet path is present, checking `getServletPath()` is preferable to comparing the full request URI.

Do not read the entire request body inside a filter merely to count bytes and then forward it. Reading the stream can consume the body before the GraphQL handler receives it, or force the application to buffer an extra large copy.

## 6. Why Content-Length is not enough

`Content-Length` is the body size declared by the client in HTTP headers. It is useful for early rejection, but it is not the sole mechanism for bounding the actual data received.

Cases to keep in mind:

- Request with `Content-Length` larger than cap: can be rejected immediately.
- Request with small `Content-Length` yet mismatched transmitted content: the HTTP server handles framing/protocol errors.
- Request using chunked transfer encoding: `Content-Length` may be absent.
- Request passing through a proxy: the proxy may buffer or stream the body per its own configuration.
- Compressed request: transmitted size and decompressed size can differ if decompression is supported.

To enforce a hard limit, the receiving layer must count actual bytes while reading the stream or rely on a server/proxy with supported body limits. A filter that only checks `Content-Length` does not guarantee bounds on chunked bodies.

`ContentCachingRequestWrapper` is also not a body-size limiter. This wrapper caches request content that has already been read, typically for logging/auditing; it does not automatically reject requests when bytes exceed a threshold.

## 7. Codec configuration for Spring WebFlux

In WebFlux applications, request bodies are decoded through HTTP message codecs. Spring Boot provides a max in-memory size setting:

~~~yaml
spring:
  codec:
    max-in-memory-size: 1MB
~~~

This value bounds how much data codecs are allowed to buffer in scenarios requiring content aggregation. It is helpful when a GraphQL JSON request is decoded into an in-memory object and bodies exceeding the threshold cause decoding to fail.

This is a limit at the codec/buffering layer and should not be treated as a complete replacement for body limits at the ingress or HTTP server. Exact behavior depends on the decoder, how the body is consumed, and the Spring Framework version. Test against the exact WebFlux stack you run.

The `spring.codec.max-in-memory-size` property can also affect codecs configured elsewhere in the application, including certain client codecs. When a BFF both receives GraphQL requests and uses `WebClient`/`GraphQlClient` to download large payloads, consider the shared impact and configure separate codecs if necessary.

## 8. Servlet containers and commonly confused properties

There is no single Spring Boot property with identical semantics across all servlet containers and all request body types. Several Tomcat properties are commonly mistaken for JSON body limits:

| Tomcat property | Primary scope | Should not be interpreted as |
| --- | --- | --- |
| `maxPostSize` | Limits POST data parsed by Tomcat into parameters for relevant content types/form parsing | General hard cap for all `application/json` bodies |
| `maxSwallowSize` | Amount of body Tomcat continues reading/discarding after a request is rejected or ends early | Maximum accepted request size |
| `maxHttpRequestHeaderSize` | Request header size | JSON body size |

Do not tune `maxSwallowSize` expecting to block GraphQL JSON bodies. Do not rely on `maxPostSize` as a general body cap when the endpoint accepts `application/json`. Check documentation for your exact container version and use a real proxy or body limiter.

If using Jetty or Undertow, native settings may differ in name and semantics. Read the corresponding server documentation, verify whether settings apply to raw request content or only form/multipart parsing, and test both `Content-Length` and chunked transfers.

## 9. Limiting the query document separately

A body size cap bounds total JSON bytes, yet a query document may require its own threshold:

~~~graphql
query LargeDocument {
    product1: product(id: "p-1") { id name }
    product2: product(id: "p-2") { id name }
    product3: product(id: "p-3") { id name }
}
~~~

A document can repeat many aliases or field selections. The body may remain under the byte limit while triggering many resolver invocations.

Mitigations:

- Bound query document length in bytes or characters after decoding.
- Limit operation/alias counts if policy requires.
- Enforce a query depth limit.
- Use query complexity/cost analysis to estimate work.
- Consider persisted queries or allowlists for production clients.

Query length and complexity are two different metrics. Do not use a query length limit as a substitute for complexity analysis.

## 10. Limiting variables and input collections

`variables` is often the largest part of a GraphQL POST body. For example, an import mutation might accept a list of thousands of items:

~~~graphql
mutation ImportProducts($items: [ImportProductInput!]!) {
    importProducts(items: $items) {
        acceptedCount
        rejectedCount
    }
}
~~~

The body cap limits total payload size, yet the application should still validate:

- Maximum element count in each input list.
- Maximum string length.
- Depth and field count of input objects.
- Size of individual blob/text fields if present.
- Total number of items a single mutation is allowed to process.

Do not rely solely on byte limits. A small payload can hold thousands of short items; conversely, a single long description field can make the body huge even with few items.

For very large imports, consider a dedicated upload API or asynchronous job workflow: the client uploads the file to object storage, and the GraphQL mutation receives a validated file/job reference. Do not force a single GraphQL request to hold tens of MBs in memory when the use case can stream.

## 11. GET requests have different limits from POST

GraphQL HTTP can support GET for query operations depending on configuration/transport. With GET, the query and variables are typically encoded into URL query parameters, so the critical limits are URI/request-target size and request headers, not POST body size.

An overly long URL can be rejected with HTTP 414 or rejected by browsers/proxies/servers under their own limits. URI limits can be much lower than body limits.

Mutations should not be sent over GET. Clients must use POST for mutations and requests with large variables. With GET, do not attempt to stuff a large JSON payload into a URL just to bypass a body cap.

Persisted queries can shrink the query document sent in a request by transmitting a hash/identifier, but `variables` remain in the request and must still adhere to body limits.

## 12. Multipart uploads and request bodies

The core GraphQL specification does not define file uploads via `multipart/form-data`. If an application implements the GraphQL multipart request convention or a dedicated upload endpoint, apply dedicated policies:

- Limit total request size.
- Limit individual file size.
- Limit file count and part count.
- Limit metadata and text fields.
- Inspect actual content types rather than trusting only filename/`Content-Type`.
- Stream files to storage instead of buffering everything on the heap.
- Scan or validate files according to business requirements.

`spring.servlet.multipart.max-file-size` and `spring.servlet.multipart.max-request-size` apply to Servlet multipart handling. They are not general limits for `application/json` GraphQL POSTs. If using WebFlux multipart, configure the corresponding multipart reader/server limits.

Do not enable upload extensions simply because the body limit has been raised. File uploads carry a different threat model and resource profile than standard JSON requests.

## 13. Request compression and decompressed size

If the server/proxy supports request `Content-Encoding` such as gzip, determine whether limits apply before or after decompression. A small compressed payload can expand into huge data in memory.

Policies should consider:

- Wire-byte limits at the ingress.
- Decoded/decompressed byte limits if decompression is enabled.
- Time bounds for decompression and reading the body.
- Disabling request compression if unnecessary.
- Testing compressed payloads with high expansion ratios.

Do not assume that `client_max_body_size` or a post-proxy `Content-Length` cap protects memory after decompression. That depends on where and how decompression occurs.

## 14. Choosing appropriate limits

No single body size fits every GraphQL API. Measure real valid payloads and pick a threshold with reasonable headroom:

1. Collect request body sizes in staging or masked telemetry.
2. Identify the largest valid use case, including `variables` and `extensions`.
3. Choose a maximum threshold with sufficient headroom.
4. Set a smaller default if typical clients send only small requests.
5. Apply separate limits for mutations/bulk operations if their needs differ.
6. Keep limits aligned across ingress, server, and app.
7. Monitor the rate of requests near the threshold and HTTP 413 counts.

For instance, an API serving regular queries might start testing with 1 MiB. An API with batch import mutations might need a different cap or a separate import endpoint. These numbers are starting points for measurement, not universal defaults for every system.

## 15. Aligning limits across layers

Suppose ingress caps at 1 MiB, the WebFlux codec caps at 512 KiB, and an app filter allows 2 MiB. A 700 KiB request can be rejected by the codec even though ingress passed it through. A 1.5 MiB request is blocked by ingress before reaching the app. Three layers have different contracts, making diagnostics harder.

Create a configuration table:

| Layer | Example limit | Role |
| --- | --- | --- |
| CDN/API gateway | 1 MiB | Block large payloads at the edge |
| Ingress/reverse proxy | 1 MiB | Block before upstream |
| HTTP server/codec | 1 MiB or matching threshold | Bound receiving/decoding/buffering |
| App validation | 1 MiB and input-specific limits | Additional checks per endpoint/use case |

Layer limits must be compatible. If an inner layer has a lower limit than an outer layer, requests traverse the network only to be rejected later. If an outer layer permits more than an inner layer, clients receive errors from the app/codec instead of the edge. That may be acceptable, but it must be intentional and observable.

## 16. Handling oversized body errors

Bodies rejected before GraphQL execution typically return HTTP 413. The response body may be generated by the proxy or HTTP server and does not necessarily follow the GraphQL error format.

Clients should:

- Check the HTTP status before parsing the GraphQL response.
- Display a message indicating the payload is too large or suggest splitting the batch.
- Not retry the exact same request unchanged, as retries will keep exceeding the limit.
- Keep GraphQL error handling separate from transport error handling.

If the app filter returns 413 itself, you can configure a uniform error response at the gateway or filter. However, there is no need to fake a GraphQL response if the request never reached the GraphQL engine; HTTP status is the standard signal.

Do not return the rejected body content in error messages or logs. Log only the endpoint, content length, request ID, and safe metadata.

## 17. Observing request size without leaking data

Track:

- Count of POST requests to the GraphQL endpoint.
- Histogram of body sizes in bytes.
- Count of 413 rejections by layer.
- Count of decode/codec buffer limit errors.
- Query document size and variables size if safe instrumentation is available.
- Rate of requests approaching the threshold.
- Parse/validation/execution latency.

Do not log raw GraphQL bodies or `variables` by default. `variables` may contain emails, addresses, tokens, personal data, or sensitive business information. If debugging is needed, use masked sampled logging with size bounds and short retention.

Attach a request ID/correlation ID to correlate proxy and application logs. A request rejected with 413 by Nginx may never appear in application logs; check ingress-layer metrics/access logs.

## 18. Testing request body limits

Tests must verify behavior at the exact layer configured:

| Case | Expected outcome |
| --- | --- |
| POST body smaller than limit | Request reaches GraphQL execution |
| POST body equal to limit | Accepted if server/proxy uses an inclusive check |
| POST body exceeding limit | HTTP 413 |
| `Content-Length` larger than limit | Rejected early |
| Chunked body exceeding limit | Bounded by proxy/server stream cap |
| Malformed but small JSON | HTTP 400 or error per transport contract |
| Unsupported `Content-Type` | HTTP 415 |
| Overly long GET URI | HTTP 414 or status per server/proxy |
| Too many items in variables list despite small body | Rejected by application validation |
| Deep query with small body | Rejected by depth/complexity policy |

When testing an app filter, include a test for requests without `Content-Length` to prove the filter is not treated as a hard cap. When testing ingress, send requests through the real ingress or an equivalent integration environment; `MockMvc` cannot verify Nginx limits.

## 19. Example filter test with MockMvc

A `Content-Length` filter can be tested at the servlet layer:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class GraphQlContentLengthFilterTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsDeclaredBodyLargerThanLimit() throws Exception {
        byte[] body = new byte[1_048_577];

        mockMvc.perform(post("/graphql")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isPayloadTooLarge());
    }
}
~~~

This test verifies that the filter rejects requests with `Content-Length` larger than 1 MiB. `MockMvc` generally creates requests with a known content length; it does not fully simulate chunked transfers or reverse proxies. Run integration tests through the HTTP server/ingress to verify hard limits.

If the endpoint path differs from `/graphql` or the application runs under a context path, adjust the test and filter to match the actual configuration. Do not assume the filter is registered for only one servlet mapping if the application defines multiple dispatchers.

## 20. Common configuration pitfalls

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Checking only `Content-Length` | Chunked requests can slip past the filter | Use proxy/server stream caps |
| Using `maxSwallowSize` as a request cap | Request bodies may still be accepted | Use a real body size limit |
| Using `maxPostSize` for all JSON bodies | Misunderstands form parameter parsing scope | Verify container semantics and set a proxy cap |
| Only increasing `max-in-memory-size` | Large payloads are still buffered and consume heap | Pick an appropriate threshold and cap at ingress |
| Confusing body size with query complexity | Small yet very expensive queries still run | Add depth/cost controls |
| Confusing multipart limits with JSON limits | GraphQL JSON is not protected as expected | Configure the right media type and layer |
| Not bounding `variables` | Large input lists/strings spike memory/CPU | Validate size and item counts |
| Not distinguishing GET and POST | Query URLs grow too long or bodies go unchecked | URI limits for GET, body limits for POST |
| Returning GraphQL errors for every 413 | Wrong layer and clients may misparse | Handle HTTP transport status codes |
| Logging entire bodies | Sensitive data leaks and log volume spikes | Log size/request ID and mask content |
| Unintentionally mismatched thresholds across layers | Hard-to-diagnose errors | Align configuration and observe each layer |

## 21. Deployment checklist

- Identify GraphQL endpoints and enabled HTTP methods.
- Determine the largest valid POST payload, including `query`, `variables`, and `extensions`.
- Choose a maximum body size in bytes.
- Configure ingress/reverse proxy to block both `Content-Length` and chunked bodies.
- Check native servlet container limits if the app receives traffic directly.
- For WebFlux, configure an appropriate codec `max-in-memory-size` and verify decoder behavior.
- If using an app filter, treat the `Content-Length` check as an early guard; do not treat it as a hard cap for chunked bodies.
- Set separate limits for query documents, variable lists/strings, and query complexity.
- Handle GET URI size separately; do not send mutations via GET.
- If multipart uploads or request compression are enabled, define separate limits for each.
- Return HTTP 413 when bodies exceed the threshold and guide clients to split payloads.
- Track body-size histograms, 413 rates, and codec failures without logging raw variables.
- Test at both the application layer and the ingress/server layer.

## 22. Request body limiting principles for Spring GraphQL

Request body limits should be enforced before GraphQL parses and executes operations. Prefer hard caps at the ingress/reverse proxy or HTTP server to block actual payloads, then use codecs or app validation as an additional protective layer. In Spring MVC, a `Content-Length` filter helps reject declared-oversized requests early; it does not block chunked bodies on its own. In WebFlux, `spring.codec.max-in-memory-size` bounds codec buffering and should be viewed strictly within the decoder's scope.

Distinguish HTTP body bytes from query document size, `variables` limits, GET URI size, and query complexity. Use HTTP 413 for oversized payloads, and do not rely on GraphQL exception resolvers for requests rejected prior to execution. Keep limits aligned across gateway, proxy, server, and application; test both `Content-Length` and chunked transfers.

Do not set an arbitrarily huge number just to avoid client errors. Measure valid payloads, cap lists/strings per use case, consider separate upload/import workflows for large data, and monitor request sizes without logging sensitive data. This approach protects memory and processing capacity at the GraphQL endpoint while keeping a clear contract for clients.

## References

- [Spring Boot — Web Server Configuration](https://docs.spring.io/spring-boot/reference/howto/webserver.html)
- [Spring Boot — WebFlux Codec Configuration](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring for GraphQL — HTTP Transport](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Nginx — client_max_body_size](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size)
- [GraphQL over HTTP Specification](https://graphql.github.io/graphql-over-http/draft/)
