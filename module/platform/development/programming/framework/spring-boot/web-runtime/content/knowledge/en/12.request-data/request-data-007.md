# Reading HttpServletRequest in MVC and ServerWebExchange in WebFlux

## Learning Objectives

After this lesson, you will be able to:

1. Explain the role of **HttpServletRequest** in Spring MVC and **ServerWebExchange** in Spring WebFlux when accessing data of an HTTP request.
2. Read the method, URI/path, query parameters, headers, cookies, connection details, request attributes, and session using the API appropriate for each web stack.
3. Distinguish **reading metadata** from **consuming the request body**, understand single-read body limits, and diagnose errors when a filter reads the body before the controller.
4. Know when to use @RequestParam, @PathVariable, @RequestHeader, @CookieValue, and @RequestBody instead of accessing the request object directly.
5. Handle request bodies via Servlet InputStream/Reader in MVC and Flux<DataBuffer>/Mono<T> in WebFlux.
6. Understand request lifecycle, thread-locals, asynchronicity, backpressure, cancellation, DataBuffer pooling, sessions, and resource ownership.
7. Write runnable examples with **Spring Boot 3.3.x / Spring Framework 6.1.x / Java 17+**, separating MVC and WebFlux, and test them with MockMvc or WebTestClient.
8. Avoid common pitfalls involving reverse proxies, multipart uploads, form data, content types, security filters, and sensitive data.

**Parent context: Request Data — Spring Boot web-runtime.** The focus is how to read HTTP requests in both models, not how to write an HTTP client or install both server stacks in the same application.

## 1. Why Does Spring Provide Two Different Request Types?

An HTTP request consists of a request line (or equivalent pseudo-headers in HTTP/2), headers, cookies, a query string, and a body. Both Spring MVC and WebFlux must deliver this data to controllers, but they are built on **two different I/O processing models**.

- **Spring MVC:** built on the Servlet API. A container such as Tomcat, Jetty, or Undertow supplies HttpServletRequest and HttpServletResponse for each HTTP request. The common model uses a servlet worker thread handling the request synchronously; MVC also supports asynchronous options on Servlet.
- **Spring WebFlux:** built on a reactive HTTP abstraction. A WebFlux controller can accept **ServerWebExchange**, accessing ServerHttpRequest, ServerHttpResponse, request attributes, WebSession, and body publishers suited to reactive/non-blocking processing.
- **Spring Boot:** selects the ApplicationContext type and web runtime based on dependencies/configuration. If both starter-web and starter-webflux are present, Boot 3.3 typically defaults to **Spring MVC/Servlet**.

These two APIs are not two names for the same object. Do not inject HttpServletRequest into an annotated WebFlux controller expecting Reactor Netty to synthesize a Servlet request. Conversely, a Spring MVC controller normally does not receive ServerWebExchange as a method argument.

### Spring MVC Flow

~~~text
Client
   |
   v
Servlet container (Tomcat/Jetty/Undertow)
   |
   v
jakarta.servlet.http.HttpServletRequest
   |
   v
Servlet Filter chain
   |
   v
DispatcherServlet
   |
   v
HandlerMapping -> HandlerAdapter
   |
   v
Spring MVC controller
   |
   +-- @RequestParam / @RequestHeader / @RequestBody
   +-- Or directly HttpServletRequest
~~~

### Spring WebFlux Flow

~~~text
Client
   |
   v
HTTP runtime (Reactor Netty or reactive adapter)
   |
   v
ServerHttpRequest + ServerHttpResponse
   |
   v
ServerWebExchange
   |
   v
WebFilter chain
   |
   v
DispatcherHandler
   |
   v
HandlerMapping -> HandlerAdapter
   |
   v
Spring WebFlux controller
   |
   +-- @RequestParam / @RequestHeader / @RequestBody
   +-- Or directly ServerWebExchange
~~~

WebFlux can run on a Servlet 3.1+ container through an adapter, yet the standard API of a **WebFlux controller** remains reactive abstractions. Never infer that "running on Tomcat" guarantees HttpServletRequest is available in every controller.

## 2. Quick Comparison Table

| Question | Spring MVC | Spring WebFlux |
|---|---|---|
| Controller object | HttpServletRequest | ServerWebExchange or ServerHttpRequest |
| Package | jakarta.servlet.http | org.springframework.web.server and org.springframework.http.server.reactive |
| HTTP method | request.getMethod() returns String | exchange.getRequest().getMethod() returns HttpMethod |
| URI/path | getRequestURI(), getContextPath(), getServletPath() | getRequest().getURI(), getRequest().getPath() |
| Query parameters | getParameter(), getParameterValues(), getParameterMap() | getRequest().getQueryParams() |
| First header | getHeader("X-Id") | getHeaders().getFirst("X-Id") |
| Multiple header values | getHeaders("X-Id") (Enumeration) | getHeaders().get("X-Id") (List) |
| Cookies | getCookies() (Cookie[] or null) | getCookies() (MultiValueMap<String,HttpCookie>) |
| Request attributes | getAttribute(), setAttribute() | getAttributes(), getAttribute(), getRequiredAttribute() |
| Session | getSession(false), getSession() | getSession() returns Mono<WebSession> |
| Principal | getUserPrincipal() | getPrincipal() returns Mono<T extends Principal> |
| Remote address | getRemoteAddr(), getRemotePort() | getRequest().getRemoteAddress() |
| Raw request body | ServletInputStream or BufferedReader | Flux<DataBuffer> via getBody() |
| Typed JSON body | @RequestBody + HttpMessageConverter | @RequestBody + HttpMessageReader/codecs |
| Form data | Servlet request parameter parsing | exchange.getFormData() returns Mono<MultiValueMap<...>> |
| Multipart | Part, MultipartFile, MultipartResolver | Part/FilePart, getMultipartData(), Flux<PartEvent> |
| Filter | jakarta.servlet.Filter, OncePerRequestFilter | WebFilter |
| Context propagation | Servlet request context, thread-locals with limits | Reactive Context and request/exchange data |
| Writing response | HttpServletResponse or return value | ServerHttpResponse or reactive return value |

Do not assume **ServerWebExchange only holds the request**. The exchange also wraps the response, attributes, session, principal, and coordination tools for an HTTP exchange.

## 3. MVC: Using HttpServletRequest in a Controller

In Spring Boot 3.3 and Spring Framework 6, the exact import is:

~~~java
import jakarta.servlet.http.HttpServletRequest;
~~~

**Do not** use javax.servlet.http.HttpServletRequest in a Boot 3.x project: starting with Spring Framework 6, the Servlet API moved to the **jakarta.servlet** namespace.

An MVC controller receiving the request directly:

~~~java
@GetMapping("/inspect")
Map<String, String> inspect(HttpServletRequest request) {
    return Map.of(
            "method", request.getMethod(),
            "uri", request.getRequestURI()
    );
}
~~~

This is a snippet inside a @RestController with appropriate imports, **not a standalone Java file**. Spring MVC's method argument resolver injects the current HttpServletRequest when invoking the handler.

Accessing the request object is useful when you need varied metadata or Servlet APIs not covered by a specialized annotation. However, to extract a single query parameter, path variable, or header, annotations keep the controller shorter and easier to test.

### Useful Servlet Methods

~~~java
String method = request.getMethod();
String uri = request.getRequestURI();
String query = request.getQueryString();
String host = request.getServerName();
int port = request.getServerPort();
String contentType = request.getContentType();
String agent = request.getHeader("User-Agent");
String firstTag = request.getParameter("tag");
String[] tags = request.getParameterValues("tag");
~~~

All belong in an environment with a request variable of type HttpServletRequest. Query/header/parameter values can be **null**; getParameterValues can return null when the key is absent. Do not pass them straight into Map.of without null checks, since Map.of forbids null values.

- getRequestURI() returns the server request URI without the query string.
- getQueryString() returns the query string **not decoded in the way getParameter does**, or null if there is no query.
- getParameter("tag") returns a single value; if a key repeats, use getParameterValues("tag") to avoid losing values.
- getServerName()/getServerPort() reflect request/container/proxy context, **not** always the real public address called by the client.

## 4. Path, Context Path, and Query in the Servlet API

Suppose a client sends:

~~~http
GET /shop/api/orders/42?include=items&tag=java&tag=spring HTTP/1.1
Host: localhost:8080
~~~

Assume server.servlet.context-path=/shop and the MVC route is /api/orders/{id}. Common values:

| API | Illustrative value |
|---|---|
| getRequestURI() | /shop/api/orders/42 |
| getContextPath() | /shop |
| getQueryString() | include=items&tag=java&tag=spring |
| getParameter("include") | items |
| getParameterValues("tag") | ["java","spring"] |

This is an **example under a specific configuration**, not a guaranteed transcript for every Servlet mapping. getServletPath() and getPathInfo() also depend on servlet mapping configuration; never rely on getServletPath() as an invariant duplicate of getRequestURI().

### Cleaner Binding Alternatives

~~~java
@GetMapping("/api/orders/{id}")
OrderResponse find(
        @PathVariable long id,
        @RequestParam(defaultValue = "false") boolean includeItems,
        @RequestHeader(value = "X-Trace", required = false) String trace) {
    // ...
}
~~~

This is an illustrative snippet. @PathVariable, @RequestParam, and @RequestHeader are bound by the framework; you usually do not need to parse strings into long/boolean manually.

**Choose the raw request when you genuinely need metadata or integration infrastructure**, not just because a controller can inject it. Using @RequestParam for a query key yields a clearer contract and easier validation.

## 5. Reading Request Headers and Cookies in MVC

### Headers

~~~java
String accept = request.getHeader("Accept");
String trace = request.getHeader("X-Trace-Id");
Enumeration<String> traceValues = request.getHeaders("X-Trace-Id");
Enumeration<String> headerNames = request.getHeaderNames();
~~~

getHeader returns one value or null. For multi-valued headers, getHeaders(name) lets you iterate the Enumeration rather than assuming a single value.

Header names are case-insensitive per HTTP standards; **header values** have header-specific rules and should not all be treated as case-insensitive.

### Cookies

~~~java
Cookie[] cookies = request.getCookies();

if (cookies != null) {
    for (Cookie cookie : cookies) {
        if ("theme".equals(cookie.getName())) {
            String value = cookie.getValue();
            // Use value after validating it.
        }
    }
}
~~~

Requires importing jakarta.servlet.http.Cookie. getCookies() can return **null** when the request has no cookies.

If a controller only needs one cookie, Spring MVC offers @CookieValue:

~~~java
@GetMapping("/theme")
String theme(@CookieValue(
        value = "theme", defaultValue = "light") String value) {
    return value;
}
~~~

This is a snippet inside a @RestController; never attach access permissions to an unverified cookie without integrity checks. Session or token cookies have security value only when properly authenticated and managed by the security system.

## 6. Request Attributes: Internal Data for a Single Request

Servlet request attributes form a map used by the server, filters, and controllers **during processing of the same request**:

~~~java
request.setAttribute("demo.trace", "mvc-123");
Object trace = request.getAttribute("demo.trace");
request.removeAttribute("demo.trace");
~~~

Distinguish between:

- **Request parameter:** data from the client, usually query or form.
- **Header:** metadata sent by the client or a proxy.
- **Request attribute:** server-side data attached to a single request; filters, interceptors, or controllers can share it.
- **Session attribute:** data bound to a session that can persist across multiple requests.

A client cannot set a request attribute directly simply by adding an HTTP header with the same name. However, if the application copies an untrusted header into an attribute and then treats that attribute as trusted, the application code itself introduces a spoofing risk.

### When Should a Filter Use Request Attributes?

For example, a filter can attach a request correlation marker that the controller later reads:

~~~java
request.setAttribute("demo.marker", "mvc-filter");
filterChain.doFilter(request, response);
~~~

This is a snippet inside a Servlet Filter, not a complete class. The runnable example later includes both the filter and controller.

Never store long-lived objects or unbounded background tasks in request attributes. Once the request ends, do not retain a reference to HttpServletRequest inside a singleton or static cache.

## 7. Sessions in MVC: getSession() vs. getSession(false)

~~~java
HttpSession existing = request.getSession(false);

if (existing == null) {
    // No current session exists.
}
~~~

- **getSession(false):** returns the existing session or null, **without creating a new session**.
- **getSession():** equivalent to getSession(true), returns the session and creates a new one if none exists.
- **request.getUserPrincipal():** principal provided by the container/security context if available; may be null.

If you only want to check whether the current request already has a session, call getSession(false) to avoid accidentally creating sessions for stateless GET endpoints.

An HttpSession can be accessed concurrently by multiple requests; **do not assume session attributes are thread-safe by default**. When sharing mutable state in a session, design proper concurrency and consistency controls.

### Do Not Treat the Session ID as a Public Value

A session ID is security-sensitive. Never echo raw session IDs in JSON responses or print them into access logs without controlled necessity. The example returns only a boolean indicating whether a session exists.

## 8. Reading the Raw Request Body with ServletInputStream/Reader

An HTTP request may carry a body. The Servlet API provides:

~~~java
ServletInputStream stream = request.getInputStream();
~~~

or:

~~~java
BufferedReader reader = request.getReader();
~~~

These methods have Servlet API usage constraints: do not casually call both getInputStream() and getReader() on the same request expecting independent reads. A body is fundamentally a **stream**: once bytes are consumed, downstream code does not automatically see the original bytes again.

### Example Reading a Text Body (Only for Small Bodies)

~~~java
byte[] bytes = request.getInputStream().readAllBytes();
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

This is a Servlet MVC snippet requiring imports and execution in a request-handling context. readAllBytes() holds the entire body in the heap and is unsuitable for large uploads or unbounded payloads.

Prefer:

~~~java
@PostMapping(
    path = "/echo",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
EchoResponse echo(@RequestBody EchoInput input) {
    return new EchoResponse(input.message());
}
~~~

when binding a JSON DTO. MVC uses HttpMessageConverter with Jackson to read the JSON body. Never read the raw body first in a filter and also expect @RequestBody to work without an appropriate wrapper/caching mechanism.

### Why Reading the Body in a Filter Can Break @RequestBody

~~~text
HTTP body -> ServletInputStream
                 |
                 +--> Filter reads the stream to completion
                 |
                 +--> Controller @RequestBody tries to read next
                            |
                            +--> No bytes remain as before
~~~

A body-logging filter must be written carefully. Spring's **ContentCachingRequestWrapper** caches bytes **as they are read through the wrapper** for observation, but by itself does not turn a consumed body into a stream that any downstream consumer can reread arbitrarily. If you truly need body replay, design a dedicated request wrapper, enforce size limits, handle encoding, and secure logs; usually avoid reading the body if the filter only needs headers or paths.

## 9. Servlet Form Data and getParameter() Can Consume the Body

For a request:

~~~http
POST /submit HTTP/1.1
Content-Type: application/x-www-form-urlencoded

name=An&level=2
~~~

The Servlet container can parse the form body to provide:

~~~java
String name = request.getParameter("name");
String level = request.getParameter("level");
~~~

**Warning:** Calling getParameter/getParameterMap on a form POST can trigger parsing of the request body. Once parsed from the body, the raw InputStream/Reader is not guaranteed to remain intact for other code. Conversely, if you read the stream first, the container may not parse form parameters as expected.

Therefore:

- **JSON:** @RequestBody DTO or JSON converter.
- **Form:** @RequestParam, @ModelAttribute, or appropriate Servlet form APIs.
- **Multipart:** MultipartResolver, MultipartFile, Part, or @RequestPart where appropriate.
- **Raw bytes:** read InputStream with an explicit contract and size limits.

Never call getParameter("message") expecting to read a field from a JSON body. Servlet request parameters do not automatically parse JSON into a Map.

## 10. MVC Request Lifecycle, Threads, and RequestContextHolder

Normally HttpServletRequest is scoped to **a single active request**, not a global singleton.

Dangerous code:

~~~java
@Component
class BadCache {

    private HttpServletRequest remembered;

    void store(HttpServletRequest request) {
        remembered = request;
    }
}
~~~

This is an **anti-pattern**: holding a request reference inside a singleton causes memory leaks, reading data from another client's request, and race conditions across clients. Never implement this pattern.

Spring provides RequestContextHolder to access thread-bound request state in certain MVC situations:

~~~java
RequestAttributes attrs = RequestContextHolder.getRequestAttributes();
~~~

However, thread-local context does not automatically propagate across arbitrary asynchronous callbacks, executors, or schedulers. If you spawn separate threads or tasks, do not assume RequestContextHolder retains the right request. When metadata is needed, **extract the minimal required fields into an immutable value object** and pass it explicitly; never pass HttpServletRequest itself.

Spring MVC supports Servlet async processing (Callable, DeferredResult, WebAsyncTask, and certain reactive return types), so concluding "MVC always runs exclusively on one thread from start to finish" is also incorrect. What matters is managing the request lifecycle properly rather than relying on thread identity as a source of truth.

## 11. Spring WebFlux: What Is ServerWebExchange?

WebFlux encapsulates the HTTP request/response and request-scoped state inside **ServerWebExchange**:

~~~java
import org.springframework.web.server.ServerWebExchange;
~~~

Key methods:

~~~java
ServerHttpRequest request = exchange.getRequest();
ServerHttpResponse response = exchange.getResponse();

Map<String, Object> attrs = exchange.getAttributes();
Mono<WebSession> session = exchange.getSession();
Mono<Principal> principal = exchange.getPrincipal();
~~~

These are illustrative lines inside a WebFlux handler with proper imports. exchange.getSession() and exchange.getPrincipal() return a **Publisher** as a Mono, not a synchronous HttpSession or Principal. When no principal exists, the Mono may be empty.

To access request and response types:

- **ServerHttpRequest** is in org.springframework.http.server.reactive.
- **ServerHttpResponse** is also in org.springframework.http.server.reactive.
- **ServerWebExchange** is in org.springframework.web.server.

A WebFlux controller can accept ServerWebExchange directly:

~~~java
@GetMapping("/inspect")
Mono<String> inspect(ServerWebExchange exchange) {
    return Mono.just(exchange.getRequest().getMethod().name());
}
~~~

This is a WebFlux snippet. On GET /inspect, the body is typically GET; a String may be written as text/plain depending on produces and content negotiation. Never manually subscribe to the Mono inside the controller: the WebFlux framework subscribes to the returned publisher.

## 12. Reading Method, URI, Path, and Query in WebFlux

Example:

~~~java
ServerHttpRequest req = exchange.getRequest();

HttpMethod method = req.getMethod();
URI uri = req.getURI();
RequestPath path = req.getPath();
MultiValueMap<String, String> params = req.getQueryParams();

String q = params.getFirst("q");
List<String> tags = params.get("tag");
~~~

Typical imports:

~~~java
import java.net.URI;
import java.util.List;
import org.springframework.http.HttpMethod;
import org.springframework.http.server.RequestPath;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.util.MultiValueMap;
~~~

Importing RequestPath above illustrates the API type; controllers can use var to reduce imports.

### Difference from Servlet getParameter()

**ServerHttpRequest.getQueryParams()** gives a MultiValueMap of **query parameters**. It does not merge JSON bodies or POST form fields into query parameters as Servlet request parameters do. To read a form body in WebFlux, use exchange.getFormData().

### Path Separated from Query

Example GET /api/books/42?lang=vi:

~~~java
String withinApp = req.getPath().pathWithinApplication().value();
String query = req.getURI().getRawQuery();
~~~

withinApp represents the path within the application without ?lang=vi. URI.getRawQuery() returns the query string undecoded by query-parameter parsing logic. When you need decoded and repeatable parameters, use req.getQueryParams().

Path components may contain percent-encoding or varying context paths; never write custom security checks by slicing the raw request URI string while bypassing normalization and framework path matching.

## 13. Reading Headers, Cookies, and Network Peer in WebFlux

Example:

~~~java
ServerHttpRequest req = exchange.getRequest();

String channel = req.getHeaders().getFirst("X-Channel");
List<String> accept = req.getHeaders().get("Accept");
String contentType = String.valueOf(
        req.getHeaders().getContentType());

MultiValueMap<String, HttpCookie> cookies = req.getCookies();
HttpCookie theme = cookies.getFirst("theme");

InetSocketAddress peer = req.getRemoteAddress();
~~~

This is a snippet, not a standalone Java file. Values can be null: content-type may be omitted, a header may be missing, and remote address is not always available across every runtime.

Unlike Servlet Cookie[], WebFlux returns **MultiValueMap<String,HttpCookie>**. If a request contains multiple cookies with the same name, do not assume there is only one.

### Client IP and Proxies

- MVC request.getRemoteAddr() normally reflects the direct peer connected to the Servlet container.
- WebFlux ServerHttpRequest.getRemoteAddress() normally reflects the direct peer of the HTTP runtime.
- Behind Nginx, a gateway, load balancer, or CDN, the peer may be the proxy, **not the end user's IP**.
- Forwarded, X-Forwarded-For, and similar headers can be forged by clients if the network/proxy does not strip or overwrite them. Trust those headers only with an explicit trusted-proxy strategy.

Never treat an unvalidated remote IP value as proof of authentication or authorization. Proxy headers must be processed by a forward-header strategy/proxy configuration appropriate to your environment.

## 14. Request Attributes in ServerWebExchange

ServerWebExchange holds a map of request attributes used by the framework and application:

~~~java
exchange.getAttributes().put("demo.marker", "webflux-filter");

String marker = exchange.getAttributeOrDefault(
        "demo.marker", "none");
~~~

These attributes are **per-HTTP-exchange state**, serving a role analogous to Servlet request attributes, though not the same object or lifecycle API.

Useful when:

- A WebFilter records processing metadata.
- Routers/handlers share internal metadata.
- Infrastructure attaches a marker or correlation id.
- Small state needs to be shared among components within the same request.

**Note:** Never store large objects or request body contents inside exchange attributes as an unbounded cache. Avoid keeping personal data, tokens, or passwords there unnecessarily.

### WebFilter and Attributes

~~~java
@Bean
WebFilter marker() {
    return (exchange, chain) -> {
        exchange.getAttributes().put(
                "demo.marker", "webflux-filter");
        return chain.filter(exchange);
    };
}
~~~

This is a bean method in a WebFlux application, shown with full imports and application class in the complete example. WebFilter serves the same request-interception purpose as a Servlet Filter, returning **Mono<Void>** to fit the reactive request pipeline.

Do not confuse WebFilter with MVC's HandlerInterceptor, and do not declare a jakarta.servlet.Filter expecting the Reactor Netty WebFlux pipeline to run Servlet filters.

## 15. Session and Principal in WebFlux: Mono Is Part of the Contract

WebFlux does not expose HttpSession in controllers. Use WebSession:

~~~java
Mono<WebSession> sessionMono = exchange.getSession();
~~~

**getSession() returns Mono<WebSession>**, providing access to the session inside the reactive pipeline. Under the Spring Framework 6.1 contract, calling getSession does not automatically start a **started** session; the session object may be created for use, yet it is persisted only when state changes or the session is explicitly started.

Example:

~~~java
Mono<Boolean> hasStarted = exchange.getSession()
        .map(WebSession::isStarted);
~~~

Never log or return the session ID to clients just for debugging. WebSession attributes can persist across multiple requests once saved, unlike per-request exchange attributes.

### Principal

~~~java
Mono<String> username = exchange.<Principal>getPrincipal()
        .map(Principal::getName)
        .defaultIfEmpty("anonymous");
~~~

This snippet belongs in a WebFlux controller with java.security.Principal and reactor.core.publisher.Mono imported.

If the application uses reactive Spring Security, authentication is wired through the reactive security context/pipeline; never assume a client-sent X-User header equals an authenticated principal. If the request has no principal, the Mono may be empty.

## 16. Request Body in WebFlux: Flux<DataBuffer>, Not InputStream

Core API:

~~~java
Flux<DataBuffer> body = exchange.getRequest().getBody();
~~~

Imports:

~~~java
import org.springframework.core.io.buffer.DataBuffer;
import reactor.core.publisher.Flux;
~~~

The body emits DataBuffer chunks as bytes arrive; consumers use subscription and backpressure under the reactive contract. Never call block() or subscribe() manually in a controller just to "read the request immediately":

~~~java
// DO NOT do this in the request path:
exchange.getRequest().getBody().subscribe(buffer -> {
    // Reading as a side effect outside the request pipeline.
});
~~~

This is an **anti-pattern**. Manual subscription creates race conditions with downstream controllers, bypasses error/cancellation propagation, and consumes the body before normal decoders can read it.

### Proper Flow for a JSON DTO

~~~java
@PostMapping(
    path = "/echo",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
Mono<EchoResponse> echo(@RequestBody Mono<EchoInput> input) {
    return input.map(body -> new EchoResponse(body.message()));
}
~~~

This is a WebFlux snippet. Spring uses HttpMessageReader/Decoder (typically the Jackson JSON codec) to decode the body into EchoInput; the controller receives Mono<EchoInput> and preserves the reactive flow.

### If You Truly Need to Read the Raw Body

You can use DataBufferUtils.join to aggregate the stream into a single DataBuffer, **with an explicit size limit**:

~~~java
Mono<String> smallText = DataBufferUtils.join(
        exchange.getRequest().getBody(), 8192)
    .map(buffer -> {
        try {
            byte[] bytes = new byte[buffer.readableByteCount()];
            buffer.read(bytes);
            return new String(bytes, StandardCharsets.UTF_8);
        } finally {
            DataBufferUtils.release(buffer);
        }
    });
~~~

This is a snippet inside a handler requiring imports. The argument 8192 specifies the maximum bytes buffered during join; if exceeded, DataBufferLimitException is thrown. Choose an appropriate threshold for your actual API, not always 8192.

DataBuffers can use pooled/ref-counted memory, so when your code **takes ownership of a buffer**, release it per contract—do not release before reading completes, and do not retain buffers after request cancellation. Never use DataBufferUtils.join to accept unbounded uploads into the heap.

**Single consumption:** if a handler reads request.getBody() and expects to pass the same body onward to @RequestBody, the body does not replay automatically. To replay in a filter, build a ServerHttpRequestDecorator with safe buffering and release handling rather than subscribing twice.

## 17. Form Data in WebFlux via exchange.getFormData()

For:

~~~http
POST /submit HTTP/1.1
Content-Type: application/x-www-form-urlencoded

name=An&level=2
~~~

WebFlux provides:

~~~java
Mono<MultiValueMap<String, String>> form =
        exchange.getFormData();
~~~

Processing example:

~~~java
Mono<String> result = exchange.getFormData()
        .map(values -> values.getFirst("name"))
        .map(name -> name == null ? "none" : name);
~~~

This is a snippet. **Special warning:** Reactor map must never return null. If getFirst("name") returns null, the first map fails before the second map runs. Therefore, that snippet is **unsafe** when name is absent; the correct version handles null inside **one** lambda:

~~~java
Mono<String> safeResult = exchange.getFormData()
        .map(values -> {
            String name = values.getFirst("name");
            return name == null ? "none" : name;
        });
~~~

The fixed version returns "none" when the key is missing. This is a useful demonstration of the Reactor rule prohibiting null emissions in onNext.

### getFormData() Caches the Map, Yet the Raw Body Is Consumed

In Spring Framework 6.1, ServerWebExchange.getFormData() parses application/x-www-form-urlencoded data and caches the resulting MultiValueMap for subsequent getFormData() calls.

**Do not** assume the raw Flux<DataBuffer> remains readable afterward: the underlying body is consumed during parsing, and rereading raw bytes is a separate problem. Consistently use getFormData to access form fields on the same exchange.

Comparison with Servlet:

- MVC uses request.getParameter() and Servlet form parsing.
- WebFlux separates getRequest().getQueryParams() (**query only**) from exchange.getFormData() (**form body**).

This distinction is especially important when migrating MVC endpoints to WebFlux.

## 18. Multipart in MVC and WebFlux

### MVC

Servlet MVC uses Servlet multipart support, MultipartResolver, MultipartFile, and Part:

~~~java
@PostMapping(
    path = "/upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
String upload(@RequestPart("file") MultipartFile file) {
    return file.getOriginalFilename();
}
~~~

This is an illustrative snippet; **never** save a file using a path taken directly from getOriginalFilename(). Enforce size limits, file type checks, safe server-generated names, and antivirus/storage policies where needed.

### WebFlux

APIs include org.springframework.http.codec.multipart.Part and FilePart:

~~~java
Mono<MultiValueMap<String, Part>> allParts =
        exchange.getMultipartData();
~~~

getMultipartData() parses/collects parts by name and caches the resulting map; **individual part contents are not cached indefinitely for arbitrary repeated reads**. Multipart parts and uploads can be large, so prefer FilePart.transferTo or streaming PartEvent as needed.

With Spring WebFlux 6.1, you can use Flux<PartEvent> for streaming multipart processing chunk by chunk without materializing every part into a temp-disk FilePart map. When handling raw buffers directly, release them per contract.

Do not confuse MVC's jakarta.servlet.http.Part with WebFlux's org.springframework.http.codec.multipart.Part: their types and I/O models differ.

## 19. Can the Request Object Be Mutated Directly?

### MVC and HttpServletRequestWrapper

HttpServletRequest provides methods to set request attributes, but mutating the HTTP method, URI, or headers arbitrarily in place is not standard. To change how downstream components see a request, normally wrap it with **HttpServletRequestWrapper** in a Servlet Filter and override specific methods:

~~~java
HttpServletRequestWrapper wrapped =
        new HttpServletRequestWrapper(request) {
            @Override
            public String getHeader(String name) {
                if ("X-Demo".equalsIgnoreCase(name)) {
                    return "from-wrapper";
                }
                return super.getHeader(name);
            }
        };
chain.doFilter(wrapped, response);
~~~

This is a snippet for a Filter with chain, request, response, and imports; it does not override other methods such as getHeaders or getHeaderNames, so treat it strictly as a wrapper illustration, not a complete production header-rewriting solution. When building a full header wrapper, keep all header-reading APIs consistent.

### WebFlux: Mutating the Request and Exchange

ServerHttpRequest and ServerWebExchange provide decorator/mutator builders:

~~~java
ServerHttpRequest altered = exchange.getRequest()
        .mutate()
        .header("X-Demo", "from-filter")
        .build();

ServerWebExchange alteredExchange = exchange.mutate()
        .request(altered)
        .build();

return chain.filter(alteredExchange);
~~~

This is a snippet inside a WebFilter with appropriate imports. Rather than mutating read-only headers in place, build a decorated request and pass the mutated exchange downstream.

**Note:** if X-Demo is a trusted internal header, the filter must **strip or overwrite forged client values** before setting it. Never assume a header value is authenticated merely because a filter sets it.

### mutate() Does Not Automatically Replay the Raw Body

ServerHttpRequest.mutate() works for URI, headers, and builder-supported properties. It **does not** clone a consumed DataBuffer stream. To alter or replay the body, you need an appropriate ServerHttpRequestDecorator handling buffer ownership and cancellation—which is far more complex than modifying a header.

## 20. Controller Arguments: Request Object or Annotations?

| Need | Preferred in MVC | Preferred in WebFlux |
|---|---|---|
| Read a single query value | @RequestParam | @RequestParam |
| Read path id | @PathVariable | @PathVariable |
| Read a single header | @RequestHeader | @RequestHeader |
| Read a cookie | @CookieValue | @CookieValue |
| Deserialize JSON | @RequestBody DTO | @RequestBody Mono<DTO> or DTO depending on use case |
| Read diverse request metadata | HttpServletRequest | ServerWebExchange / ServerHttpRequest |
| Pass internal state from filter | request.setAttribute | exchange.getAttributes().put |
| Read form POST | @RequestParam/@ModelAttribute | exchange.getFormData or @ModelAttribute |
| Handle multipart | MultipartFile/@RequestPart | FilePart/@RequestPart or PartEvent |
| Read raw body | ServletInputStream/Reader | Flux<DataBuffer> with buffer management |
| Session | HttpSession | WebSession/Mono<WebSession> |
| Direct response access | HttpServletResponse | ServerHttpResponse |

Using the raw request object directly is not "more advanced" than using annotations. Annotations provide clearer contracts, easier validation, automatic type conversion, and simpler tests. Raw request objects shine in middleware, tracing, multi-field inspection, or infrastructure integrations.

## 21. Runnable Example 1 — Spring MVC and HttpServletRequest

**First standalone project:** Spring Boot 3.3.x, Java 17+, requiring only starter-web and starter-test.

### 21.1. Dependencies

In the build.gradle of a Spring Boot project with plugins and repositories configured:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is the dependencies block, **not the full build.gradle**. starter-web provides Servlet Spring MVC, embedded Tomcat, and Jackson for JSON.

### 21.2. Java Code

Create **src/main/java/com/example/requestmvc/MvcRequestApplication.java**:

~~~java
package com.example.requestmvc;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class MvcRequestApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcRequestApplication.class, args);
    }

    public record Snapshot(
            String method,
            String uri,
            String query,
            String channel,
            String marker,
            boolean hasSession) {}

    public record EchoInput(String message) {}
    public record EchoReply(String message, String contentType) {}

    @Component
    static class DemoFilter extends OncePerRequestFilter {

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {

            request.setAttribute("demo.marker", "mvc-filter");
            chain.doFilter(request, response);
        }
    }

    @RestController
    @RequestMapping("/demo")
    static class DemoController {

        @GetMapping(
                path = "/inspect",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        Snapshot inspect(HttpServletRequest request) {
            String q = request.getParameter("q");
            String channel = request.getHeader("X-Channel");

            return new Snapshot(
                    request.getMethod(),
                    request.getRequestURI(),
                    q == null ? "none" : q,
                    channel == null ? "none" : channel,
                    (String) request.getAttribute("demo.marker"),
                    request.getSession(false) != null
            );
        }

        @PostMapping(
                path = "/echo",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        EchoReply echo(
                @RequestBody EchoInput input,
                HttpServletRequest request) {
            return new EchoReply(
                    input.message(),
                    request.getContentType()
            );
        }

        @PostMapping(
                path = "/raw",
                consumes = MediaType.TEXT_PLAIN_VALUE,
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        String raw(HttpServletRequest request)
                throws IOException {
            byte[] bytes = request.getInputStream().readAllBytes();
            return new String(bytes, StandardCharsets.UTF_8)
                    .toUpperCase(Locale.ROOT);
        }
    }
}
~~~

Explanation:

- **DemoFilter** runs in the Servlet filter chain and sets a request attribute. The controller reads it via request.getAttribute.
- **GET /demo/inspect** reports method, URI, a query parameter, a header, the filter marker, and whether a session already exists.
- **POST /demo/echo** uses @RequestBody for JSON while also reading the request Content-Type via HttpServletRequest without consuming the body a second time.
- **POST /demo/raw** reads raw text bytes directly. This endpoint has **no** @RequestBody, avoiding body-consumption conflicts with converters.
- raw uses readAllBytes() solely to illustrate small text bodies; production code needs size limits. Content-Type text/plain and UTF-8 encoding must match between client and server.
- Both the filter and controller are nested static classes, picked up by Spring component scan under root package com.example.requestmvc. There is no need for two application contexts.

### 21.3. Running with Gradle

In src/main/resources/application.yml:

~~~yaml
server:
  port: 8080
~~~

From the project directory:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

### 21.4. Testing Metadata Reading

~~~bash
curl -s -H 'Accept: application/json' \
  -H 'X-Channel: mobile' \
  'http://localhost:8080/demo/inspect?q=hello'
~~~

When the request carries no existing session, the response body is equivalent to:

~~~json
{"method":"GET","uri":"/demo/inspect","query":"hello","channel":"mobile","marker":"mvc-filter","hasSession":false}
~~~

JSON key ordering and whitespace depend on Jackson and are not part of the contract. If another environment created a session and sent a session cookie, hasSession may be true.

### 21.5. Testing @RequestBody JSON

~~~bash
curl -i -X POST http://localhost:8080/demo/echo \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"message":"hello"}'
~~~

Equivalent body:

~~~json
{"message":"hello","contentType":"application/json"}
~~~

getContentType() reflects the header sent by the client. If the client includes a valid charset parameter, the returned string can include that parameter.

### 21.6. Testing Raw Body

~~~bash
curl -s -X POST http://localhost:8080/demo/raw \
  -H 'Content-Type: text/plain' \
  --data-binary 'hello'
~~~

Exact response body:

~~~text
HELLO
~~~

This demonstrates raw ServletInputStream usage; it does **not** imply every request should read InputStream manually.

## 22. Testing the MVC Example with MockMvc

Create **src/test/java/com/example/requestmvc/MvcRequestApplicationTests.java**:

~~~java
package com.example.requestmvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvcRequestApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void readsMetadataAndRequestAttribute() throws Exception {
        mvc.perform(get("/demo/inspect")
                    .param("q", "hello")
                    .header("X-Channel", "mobile"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.method").value("GET"))
            .andExpect(jsonPath("$.uri").value("/demo/inspect"))
            .andExpect(jsonPath("$.query").value("hello"))
            .andExpect(jsonPath("$.channel").value("mobile"))
            .andExpect(jsonPath("$.marker").value("mvc-filter"));
    }

    @Test
    void readsJsonWithRequestBodyAndHeadersWithServletApi()
            throws Exception {
        mvc.perform(post("/demo/echo")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"message\":\"hello\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("hello"))
            .andExpect(jsonPath("$.contentType")
                    .value("application/json"));
    }

    @Test
    void readsRawBodyOnlyInItsOwnEndpoint() throws Exception {
        mvc.perform(post("/demo/raw")
                    .contentType(MediaType.TEXT_PLAIN)
                    .content("hello"))
            .andExpect(status().isOk())
            .andExpect(content().string("HELLO"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

MockMvc simulates Servlet requests/responses and runs the MVC infrastructure **without opening a real TCP listener**. These tests verify routes, header/query reading, filter request attributes, JSON bodies, and raw text. They do not verify that a real network port is open or that proxy forwarding is configured properly.

## 23. Runnable Example 2 — Spring WebFlux and ServerWebExchange

**Second standalone project:** Spring Boot 3.3.x, Java 17+, using only starter-webflux and starter-test. Do not add starter-web to this project, as Boot typically selects MVC when both are present.

### 23.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is the dependencies block for a Spring Boot Gradle project with plugins and repositories already configured.

### 23.2. Java Code

Create **src/main/java/com/example/requestwebflux/WebFluxRequestApplication.java**:

~~~java
package com.example.requestwebflux;

import java.nio.charset.StandardCharsets;
import java.security.Principal;
import java.util.Locale;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxRequestApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxRequestApplication.class, args);
    }

    public record Snapshot(
            String method,
            String path,
            String query,
            String channel,
            String marker,
            String principal) {}

    public record EchoInput(String message) {}
    public record EchoReply(String message, String contentType) {}
    public record FormReply(String name) {}

    @Bean
    WebFilter demoMarker() {
        return (exchange, chain) -> {
            exchange.getAttributes().put(
                    "demo.marker", "webflux-filter");
            return chain.filter(exchange);
        };
    }

    @RestController
    @RequestMapping("/demo")
    static class DemoController {

        @GetMapping(
                path = "/inspect",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        Mono<Snapshot> inspect(ServerWebExchange exchange) {
            ServerHttpRequest request = exchange.getRequest();

            String q = request.getQueryParams().getFirst("q");
            String channel = request.getHeaders()
                    .getFirst("X-Channel");
            String marker = exchange.getAttributeOrDefault(
                    "demo.marker", "none");

            return exchange.<Principal>getPrincipal()
                    .map(Principal::getName)
                    .defaultIfEmpty("anonymous")
                    .map(name -> new Snapshot(
                            request.getMethod().name(),
                            request.getPath()
                                    .pathWithinApplication().value(),
                            q == null ? "none" : q,
                            channel == null ? "none" : channel,
                            marker,
                            name
                    ));
        }

        @PostMapping(
                path = "/echo",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        Mono<EchoReply> echo(
                @RequestBody Mono<EchoInput> body,
                ServerWebExchange exchange) {
            return body.map(input -> new EchoReply(
                    input.message(),
                    String.valueOf(
                            exchange.getRequest()
                                    .getHeaders().getContentType())
            ));
        }

        @PostMapping(
                path = "/raw",
                consumes = MediaType.TEXT_PLAIN_VALUE,
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        Mono<String> raw(ServerWebExchange exchange) {
            return DataBufferUtils.join(
                    exchange.getRequest().getBody(),
                    8192
            ).map(buffer -> {
                try {
                    byte[] bytes =
                            new byte[buffer.readableByteCount()];
                    buffer.read(bytes);
                    return new String(
                            bytes, StandardCharsets.UTF_8)
                            .toUpperCase(Locale.ROOT);
                } finally {
                    DataBufferUtils.release(buffer);
                }
            }).defaultIfEmpty("");
        }

        @PostMapping(
                path = "/form",
                consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        Mono<FormReply> form(ServerWebExchange exchange) {
            return exchange.getFormData().map(data -> {
                String name = data.getFirst("name");
                return new FormReply(
                        name == null ? "none" : name);
            });
        }
    }
}
~~~

**Explanation:**

- **WebFilter** adds an exchange attribute before forwarding to the reactive handler.
- **GET /demo/inspect** reads method, path, query, header, attribute, and principal (defaulting to anonymous if absent). Reads the principal via Mono without calling block().
- **POST /demo/echo** reads JSON via @RequestBody Mono<EchoInput>; query/header metadata on exchange can be read without competing to consume the body.
- **POST /demo/raw** uses DataBufferUtils.join with an **8192-byte** limit, reads the buffer, and releases it in finally. Intended only for small text payloads.
- **POST /demo/form** uses getFormData(), avoiding mixing with query params or rereading the raw body.
- Request handlers return Mono, which the framework subscribes to when sending the HTTP response. Controllers never call subscribe or block themselves.
- Spring Security is not configured; the default principal can be empty and becomes anonymous. When authentication is active, principal holds the name provided by the security context.

This is a **complete Java source file** for a Boot 3.3.x project with starter-webflux. It will not run with plain javac without Spring, Reactor, and Jackson on the classpath.

### 23.3. Running and Testing

Configure src/main/resources/application.yml:

~~~yaml
server:
  port: 8080

spring:
  codec:
    max-in-memory-size: 256KB
~~~

The codec setting illustrates a buffer limit for decoders that must aggregate payloads. It is separate from the 8192-byte limit explicitly passed in the raw endpoint; do not assume this property limits the **entire** request body on every endpoint.

Run:

~~~bash
./gradlew bootRun
~~~

On PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

### 23.4. Request Metadata

~~~bash
curl -s -H 'X-Channel: mobile' \
  'http://localhost:8080/demo/inspect?q=hello'
~~~

Expected JSON response:

~~~json
{"method":"GET","path":"/demo/inspect","query":"hello","channel":"mobile","marker":"webflux-filter","principal":"anonymous"}
~~~

JSON field order may vary. When authentication is configured, principal reflects the authenticated principal's name.

### 23.5. JSON Request Body

~~~bash
curl -s -X POST http://localhost:8080/demo/echo \
  -H 'Content-Type: application/json' \
  --data '{"message":"hello"}'
~~~

Equivalent response:

~~~json
{"message":"hello","contentType":"application/json"}
~~~

### 23.6. Raw Text Request Body

~~~bash
curl -s -X POST http://localhost:8080/demo/raw \
  -H 'Content-Type: text/plain' \
  --data-binary 'hello'
~~~

Exact body:

~~~text
HELLO
~~~

### 23.7. Form Data

~~~bash
curl -s -X POST http://localhost:8080/demo/form \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=An'
~~~

Expected response body:

~~~json
{"name":"An"}
~~~

Try changing the request to /demo/form?name=query while sending body name=body: getFormData() in this example reads only the **form body**, without falling back to the query string. If you want to combine query and form inputs, define explicit precedence rules and read from both sources.

### 23.8. PowerShell and Quoting

On Windows PowerShell, use curl.exe to avoid the PowerShell curl alias:

~~~powershell
curl.exe -s -H "X-Channel: mobile" "http://localhost:8080/demo/inspect?q=hello"
curl.exe -s -X POST "http://localhost:8080/demo/raw" -H "Content-Type: text/plain" --data-binary "hello"
curl.exe -s -X POST "http://localhost:8080/demo/form" -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "name=An"
~~~

For JSON on Windows, store JSON in a UTF-8 file such as input.json and pass curl.exe --data-binary "@input.json" to avoid escaping differences across PowerShell versions.

## 24. Testing WebFlux with WebTestClient

Create **src/test/java/com/example/requestwebflux/WebFluxRequestApplicationTests.java**:

~~~java
package com.example.requestwebflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class WebFluxRequestApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void readsMetadataAndExchangeAttribute() {
        client.get()
                .uri("/demo/inspect?q=hello")
                .header("X-Channel", "mobile")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.method").isEqualTo("GET")
                .jsonPath("$.path").isEqualTo("/demo/inspect")
                .jsonPath("$.query").isEqualTo("hello")
                .jsonPath("$.channel").isEqualTo("mobile")
                .jsonPath("$.marker").isEqualTo("webflux-filter");
    }

    @Test
    void decodesJsonAndKeepsHeaderMetadata() {
        client.post()
                .uri("/demo/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"message\":\"hello\"}")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("hello")
                .jsonPath("$.contentType")
                        .isEqualTo("application/json");
    }

    @Test
    void readsRawSmallBodyAndReturnsText() {
        client.post()
                .uri("/demo/raw")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("HELLO");
    }

    @Test
    void parsesFormBodyThroughExchange() {
        client.post()
                .uri("/demo/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "An"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("An");
    }
}
~~~

Command:

~~~bash
./gradlew test
~~~

Unlike MockMvc, WebTestClient in this RANDOM_PORT test sends real HTTP requests to the embedded reactive server on the test-assigned port. Therefore it exercises more of the HTTP transport than bindToController tests, though it still does not replace testing reverse proxies, TLS, or deployment configuration.

## 25. Comparing Servlet Filter with WebFilter and Accessible Data

| Topic | MVC Servlet Filter | WebFlux WebFilter |
|---|---|---|
| Contract | doFilter(request,response,chain) | filter(exchange,chain) returning Mono<Void> |
| Request abstraction | ServletRequest/HttpServletRequest | ServerWebExchange |
| Continuation | chain.doFilter(...) | return chain.filter(exchange) |
| Attributes | request.setAttribute | exchange.getAttributes().put |
| Body | ServletInputStream/Reader | Flux<DataBuffer> |
| Thread-local context | Usable under specific conditions | Never rely on thread-local for request context |
| Modifying headers/URI | Servlet wrapper or proxy configuration | ServerHttpRequest.mutate() and exchange.mutate() |
| Use when | MVC and Servlet container | WebFlux reactive pipeline |

### Do Not Put Blocking Code in a WebFilter on the Event Loop

A WebFilter performing long blocking I/O or Thread.sleep degrades Reactor Netty throughput. If you must call a blocking library, offload it to a suitable scheduler (e.g., boundedElastic) following its contract, with timeouts and concurrency bounds. Never assume wrapping a blocking call in Mono.just makes it non-blocking.

### Why Reading the Body in Middleware Is Complex

- Filters execute before the controller resolves @RequestBody.
- Body streams do not replay automatically across subscribers.
- Buffering bodies for logging increases memory pressure with concurrency.
- Sensitive data can leak into logs.
- Pooled DataBuffers require proper release management.
- Cancellation and error paths must be handled cleanly.

Prefer logging **method/path/response code/correlation id** in middleware, while handling payload validation and explicit redaction at the DTO or business boundary.

## 26. Request Attributes vs. Reactor Context

WebFlux has two concepts that are easily confused:

1. **ServerWebExchange attributes:** A per-HTTP-exchange map accessed by the framework and WebFilters through exchange.
2. **Reactor Context:** Context attached to a subscriber/pipeline, used to propagate data across async operators without relying on ThreadLocal.

A standalone Reactor Context example:

~~~java
Mono<String> value = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("trace", "none")))
    .contextWrite(ctx -> ctx.put("trace", "r-1"));
~~~

When subscribed, the emitted value is "r-1". This is a Reactor snippet and does not mean it reads an exchange attribute. Transferring data between exchange attributes and Reactor Context requires explicit code or integration.

**Never pass an entire HttpServletRequest/ServerWebExchange into long-lived background tasks** just to continue logging. Extract an immutable value object containing traceId and only the fields truly required.

## 27. Error Handling: Which Errors Come from Metadata vs. Body?

### 400 Bad Request

Typically caused by:
- Missing required @RequestParam.
- Parameter value cannot be converted to int/long/enum.
- Malformed JSON or type mismatch.
- Failed @Valid validation.

Never lump every 400 error into "server could not find route". Routing may have succeeded while parsing/binding failed.

### 415 Unsupported Media Type

For example, @PostMapping(consumes=application/json) receiving Content-Type=text/plain. The framework rejects that input media type. Do not change Accept to fix an input Content-Type mismatch.

### 406 Not Acceptable

For example, an endpoint only produces JSON while the client sends Accept: text/plain only. This is a response representation negotiation failure, not a getParameter or getHeader bug.

### Double Body Reads

In MVC you may encounter HttpMessageNotReadableException: required request body is missing after a filter consumed InputStream. In WebFlux, manually subscribing to request.getBody() earlier can leave downstream handlers without a body to decode, resulting in errors, empty results, or race conditions. The exact failure depends on runtime and timing.

### Buffer/Size Limits

WebFlux can throw DataBufferLimitException when a codec or bounded DataBufferUtils.join exceeds its limit. **Do not assume** every such case automatically returns HTTP 413; the response depends on exception mapping, server behavior, and whether response headers have already been committed.

### Session and Request Lifecycle

Trying to use a request object outside HTTP request processing can read invalid state or leak resources. Never work around this by extending a request's lifetime inside a singleton.

## 28. Reverse Proxies, Header Spoofing, and Sensitive Data

In both MVC and WebFlux:

- **X-Forwarded-For**, **Forwarded**, and **X-Real-IP** are trustworthy only when trusted proxies manage and overwrite them properly.
- getRemoteAddr() or getRemoteAddress() reflects the direct runtime peer; that peer may be a gateway.
- Request headers and query params are client-controlled; validate them before selecting accounts, roles, or permissions.
- Cookies can be forged, altered, or stolen; treat session/auth cookies as safe only when verified by proper signing/identity and session infrastructure.
- Never log Authorization, Cookie, Set-Cookie, passwords, tokens, or bodies containing personal data in debug output.
- Avoid dumping all getHeaderNames/getHeaders or getParameters in production without redaction and limits.

### CORS Does Not Replace Security

If a browser request fails due to CORS preflight, the issue is not necessarily HttpServletRequest or ServerWebExchange misreading headers. CORS is a browser enforcement mechanism. It does not replace authentication, authorization, firewalls, or API access control.

### URI and Host Are Not Authentication Sources

HTTP Host and forwarded headers can influence URLs constructed by an application if proxy configuration is lax. When generating redirects or absolute links, configure trusted forwarded headers properly and avoid building security-sensitive links directly from untrusted Host headers.

## 29. When Should You Use WebRequest/NativeWebRequest Instead of Servlet Request?

Spring MVC also supports:

~~~java
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.context.request.NativeWebRequest;
~~~

These abstractions are suitable when reading request parameters or attributes at the Spring level without coupling every operation directly to HttpServletRequest.

However:

- NativeWebRequest provides access to the native Servlet request in MVC.
- Do not assume NativeWebRequest is a reactive equivalent for ServerWebExchange in WebFlux.
- If code only needs a single header or parameter, annotations remain shorter and easier to maintain.

When decoupling business services from the web layer, pass DTOs or value objects rather than entire HttpServletRequest/ServerWebExchange objects so services stay independent of the web runtime.

## 30. Migrating MVC Controllers to WebFlux: API Mapping Checklist

| Current MVC usage | Typical WebFlux equivalent | Notes |
|---|---|---|
| HttpServletRequest request | ServerWebExchange exchange | Not a 1-to-1 cast or adapter |
| getMethod() | getRequest().getMethod() | String vs. HttpMethod |
| getRequestURI() | getRequest().getPath() or getURI() | Path API separates context/query |
| getParameter("x") | getRequest().getQueryParams().getFirst("x") | Does not include form body automatically |
| getParameterValues("x") | getQueryParams().get("x") | List or null |
| getHeader("X") | getHeaders().getFirst("X") | May be null |
| getCookies() | getCookies() | Cookie[] vs. MultiValueMap |
| getAttribute("k") | exchange.getAttribute("k") | Request-scoped |
| getSession(false) | exchange.getSession() / WebSession.isStarted | Mono and different semantics |
| getUserPrincipal() | exchange.getPrincipal() | Mono may be empty |
| getInputStream() | getBody() | ServletInputStream vs. Flux<DataBuffer> |
| @RequestBody DTO | @RequestBody Mono<DTO> or DTO | Reactive readers/codecs |
| MultipartFile | FilePart / Part / PartEvent | Streaming and cleanup differ |
| Servlet Filter | WebFilter | Different chain and return contract |
| MVC @ControllerAdvice | WebFlux @ControllerAdvice per framework | Exception types and handling differ |

**Never port** synchronous body-reading code mechanically to WebFlux by calling .block(). Rethink publisher composition and timeouts to preserve non-blocking semantics.

## 31. Hands-On Exercises

**Exercise 1 — Repeated query parameters:** A client calls /demo/inspect?tag=java&tag=spring. Write an MVC endpoint using getParameterValues("tag") and a WebFlux endpoint using getQueryParams().get("tag") that return both values as a list. Ensure only the first value is not kept by mistake.

**Exercise 2 — Missing header:** Try GET /demo/inspect without X-Channel in both projects. Verify the response returns "none" (per the lesson example) instead of an exception. Then switch to @RequestHeader(required=true) and observe the 400 behavior when missing.

**Exercise 3 — Double body read:** In a separate test environment, add a filter reading the raw body before a @RequestBody controller. Observe the failure, then **restore** the filter to read only metadata. Explain why rereading raw bodies requires a wrapper/decorator and size limits.

**Exercise 4 — Form vs. query:** On WebFlux /demo/form, send query name=query alongside body name=body. Verify getFormData() reads the body. If both are needed, create a handler returning both values separately via getQueryParams and getFormData.

**Exercise 5 — Session:** Add an endpoint that only checks session state. Do not return the session id; return boolean isStarted/hasSession accordingly. Analyze why Servlet's getSession(false) differs from WebFlux's getSession() returning Mono<WebSession>.

**Exercise 6 — Raw text limit:** On WebFlux /demo/raw with a join limit of 8192 bytes, send a larger body and observe the exception/status. Do not assert a universal status across all configurations. Then design size limits at the reverse proxy or endpoint for production.

**Exercise 7 — Filter attributes:** Change the marker set by the filter and verify tests read the updated marker via request/exchange attributes. Then analyze storing the entire request object in a singleton and explain why it is an anti-pattern—**never use this anti-pattern in production code**.

## 32. Self-Check Questions

**Question 1.** In Spring Boot 3.3, why does importing javax.servlet.http.HttpServletRequest usually report a missing package?

**Answer:** Spring Framework 6 / Boot 3 migrated to the Jakarta Servlet API, so the import is jakarta.servlet.http.HttpServletRequest.

**Question 2.** What does WebFlux ServerWebExchange contain besides the request?

**Answer:** The response, exchange attributes, session Mono, principal Mono, locale context, form/multipart parsing, and other HTTP exchange coordination utilities.

**Question 3.** How do request.getParameter("tag") and request.getParameterValues("tag") differ?

**Answer:** getParameter returns a single value or null; getParameterValues returns an array of all values for that name, or null.

**Question 4.** Does ServerHttpRequest.getQueryParams() automatically extract JSON fields from the request body?

**Answer:** No. It only returns parsed query parameters; it does not decode JSON bodies or parse form bodies in place of getFormData().

**Question 5.** Why can a Servlet Filter reading request.getInputStream() early cause @RequestBody to fail?

**Answer:** The body stream is consumed and does not rewind or replay automatically for the controller's message converter.

**Question 6.** In WebFlux, why shouldn't a WebFilter call request.getBody().subscribe(...) to log before calling chain.filter(exchange)?

**Answer:** That side-effect subscription consumes the body outside the main pipeline, risking race conditions, lost error/cancellation propagation, and missing data downstream.

**Question 7.** What is the difference between request attributes and session attributes?

**Answer:** Request attributes belong to a single request/exchange; session attributes belong to a session and can persist across multiple requests.

**Question 8.** If you only want to check whether an MVC request already has a session, should you call getSession() or getSession(false)?

**Answer:** getSession(false), because it does not create a new session if none exists.

**Question 9.** Does WebFlux getSession() always start/persist a session just from reading it?

**Answer:** No. Calling it returns Mono<WebSession>; it does not start a session merely from being accessed unless state changes or start is triggered.

**Question 10.** What does a bounded DataBufferUtils.join help accomplish?

**Answer:** It caps the number of bytes buffered during aggregation, reducing the risk of unbounded memory consumption; code handling pooled buffers directly must still release them per contract.

**Question 11.** Are getRemoteAddr() and getRemoteAddress() always the end user's real IP?

**Answer:** No. Behind proxies or gateways, they may return the direct peer address; forwarded headers must be handled under a trusted-proxy policy.

**Question 12.** When should @RequestParam be preferred over HttpServletRequest or ServerWebExchange?

**Answer:** When the controller only needs a few typed query parameters and can leverage binding, defaultValue, validation, and a cleanly testable contract.

## 33. Pre-Deployment Checklist

- [ ] Confirmed whether the active web stack is Spring MVC or Spring WebFlux.
- [ ] In Boot 3.x, MVC uses jakarta.servlet.http.HttpServletRequest rather than javax.servlet.
- [ ] WebFlux controllers use ServerWebExchange/ServerHttpRequest rather than assuming Servlet APIs.
- [ ] Path, query, header, and cookie values are read via matching APIs with null/missing checks.
- [ ] Query parameters are distinguished from form bodies, especially when migrating MVC to WebFlux.
- [ ] @RequestBody is used for DTO/JSON decoding without duplicate raw body consumption.
- [ ] Sensitive payloads and full request headers are not logged without redaction.
- [ ] Servlet Filters and WebFilters do not consume the body unless a replay/cache design with explicit size limits is in place.
- [ ] Request objects are never stored in singletons, static fields, or long-lived background jobs.
- [ ] MVC ThreadLocals are not relied upon as request context inside reactive pipelines.
- [ ] block()/subscribe() are never called to read WebFlux bodies in controllers or filters.
- [ ] Raw DataBuffer usage enforces aggregation limits, proper release, and cancel/error handling.
- [ ] Existing sessions are distinguished from newly created/started sessions.
- [ ] IP/Forwarded headers are trusted only under an explicit trusted-proxy policy.
- [ ] Tests cover MVC with MockMvc and WebFlux with WebTestClient.
- [ ] Both starter-web and starter-webflux are not placed together in a demo while assuming reactive execution.

## Official References

- [Spring Framework 6.1 — MVC Controller Method Arguments](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring Framework 6.1 — WebFlux Controller Method Arguments](https://docs.spring.io/spring-framework/reference/6.1/web/webflux/controller/ann-methods/arguments.html)
- [Spring Framework 6.1 — ServerWebExchange API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/ServerWebExchange.html)
- [Spring Framework 6.1 — ServerHttpRequest API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html)
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework — WebFlux Form Data and Multipart](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
