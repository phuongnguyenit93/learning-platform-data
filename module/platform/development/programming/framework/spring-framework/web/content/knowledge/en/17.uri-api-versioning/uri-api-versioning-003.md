# ServletUriComponentsBuilder and Building URIs from the Current Request in Spring MVC

## 1. The problem: returning accurate links without hardcoding the server

A REST API that receives `POST /api/v1/notes` and creates a new resource can return **201 Created**, accompanied by a **Location** header pointing to the newly created resource's URL. An HTML page might also need links back to the application itself, such as a detail page path or a pagination URL.

If you concatenate strings manually:

```java
String location = "http://localhost:8080/api/v1/notes/" + id;
```

the URL can break when the application runs in another environment, behind HTTPS on a reverse proxy, under a `/shop` context path, on a non-default port, or with a servlet mapping prefix. If a user-supplied ID/slug is attached directly to the URL, the code also risks incorrect encoding.

**`ServletUriComponentsBuilder`** in Spring MVC helps build URIs based on **the components provided by the current Servlet request**: scheme, host, port, context path, servlet mapping, request path, and query, depending on the chosen factory method.

It builds on `UriComponentsBuilder` to systematically add paths, queries, URI templates, and encode variables. However, the builder **does not automatically guarantee that the request host/forwarded headers are trustworthy**, does not replace the application's public URL policy, does not create the resource itself, and does not turn an arbitrary URL into a secure one.

Learning goals after this lesson:

- Understand the exact differences between `fromCurrentRequest()`, `fromCurrentRequestUri()`, `fromCurrentContextPath()`, and `fromCurrentServletMapping()`.
- Know how to use `fromRequest(request)`, `fromRequestUri(request)`, `fromContextPath(request)`, and `fromServletMapping(request)` when an explicit `HttpServletRequest` is available.
- Generate `Location` for 201 responses, pagination links, and links to resources in the same API version.
- Understand `path`, `pathSegment`, `queryParam`, `replaceQueryParam`, `buildAndExpand`, `encode`, and `toUri`.
- Distinguish a request-derived URL from a **canonical public base URL**, especially behind a reverse proxy.
- Avoid Host-header poisoning, forwarded-header spoofing, open redirects, double encoding, duplicate queries, and wrong-context-path URLs.
- Test generated paths using `MockMvc` and simulated requests.

**Scope:** Spring MVC **Servlet stack**, Java 17+, Spring Framework **6.2.x** / Spring Boot **3.5.x**. This is not the builder for Spring WebFlux; WebFlux has different server request URI and forwarding mechanisms. This lesson belongs to the **URI and API Versioning** group.

## 2. What parts make up a URI?

Example of an absolute URI:

```text
https://api.example.org:8443/shop/api/v1/notes/42?lang=vi&page=2
 
|scheme|      |host|   |port| |context|  |request path|  |query|
  https    api.example.org  8443   /shop  /api/v1/notes/42  lang=vi&page=2
```

Components:

| Component | Meaning | Example |
| --- | --- | --- |
| `scheme` | URI protocol; usually HTTP/HTTPS | `https` |
| `host` | Hostname of the origin from the request's perspective | `api.example.org` |
| `port` | Port; default ports may be omitted | `8443` |
| `contextPath` | Prefix where the Servlet application is deployed under a context | `/shop` |
| `servletPath` | Path part related to servlet mapping, not always the whole MVC route | `/api` or value per mapping |
| `requestURI` | Path seen by the Servlet container, excluding the query string | `/shop/api/v1/notes/42` |
| `queryString` | Part after `?` in the HTTP target | `lang=vi&page=2` |
| `fragment` | `#section` part interpreted by the client | Not sent to the server in a standard HTTP request-target |

**`HttpServletRequest#getRequestURL()` is not the same as `getRequestURI()`.** The request URL usually includes scheme/host/port/path; the request URI is only the path in the request, not an absolute URI. `getQueryString()` is the query separately; `getContextPath()` is the Servlet context prefix.

Browsers do not send the **fragment** in an HTTP request, so a builder pulling data from the request cannot “recover the original fragment” from `HttpServletRequest` alone.

In the API model:

```text
Origin                 https://api.example.org
Servlet context path   /shop
MVC route              /api/v1/notes
Resource path          /42
Query                  ?lang=vi

Public full URI:
https://api.example.org/shop/api/v1/notes/42?lang=vi
```

A correct URL must account for the **actual path prefix** where the application is deployed, neither duplicating `/shop` nor omitting it.

## 3. Where does `ServletUriComponentsBuilder` live in Spring?

Class:

```java
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;
```

It extends `org.springframework.web.util.UriComponentsBuilder`, allowing component-by-component URI manipulation. Its factory methods create a builder from a Servlet request either passed directly or fetched from the currently executing request via `RequestContextHolder`.

Simple execution flow:

```text
Client HTTP request
       |
       v
Servlet container
  HttpServletRequest (scheme, host, port, contextPath, requestURI, query)
       |
       v
DispatcherServlet -> @RestController handler
       |
       v
ServletUriComponentsBuilder.fromCurrentRequestUri()
       |
       v
.pathSegment("{id}").encode().buildAndExpand(id).toUri()
       |
       v
java.net.URI
       |
       v
ResponseEntity.created(uri).body(resource)
       |
       v
HTTP 201 Created + Location header
```

**The builder does not send an HTTP response.** It only produces a `URI` or `UriComponents`. `ResponseEntity` / Spring MVC determines status, headers, and body. Nor does anything in the builder write records to a database; it must be called after the application has created the resource per business logic.

### 3.1. Why not always use `URI.create(...)`?

`URI.create("https://example.org/api/notes/42")` is suitable when you already have a valid, safely constructed URI. However, it **does not automatically capture** the context path/current host, nor does it help manage URL templates and path/query components.

`UriComponentsBuilder` and `ServletUriComponentsBuilder` help manipulate components, especially when variables contain spaces, Unicode characters, or characters with special meaning in URIs.

Do not misuse the builder to accept an **entire client-entered URI** as a destination; that involves open redirect/SSRF risks and requires separate validation/allowlisting.

## 4. The four most important factory methods

Assume a hypothetical request:

```http
GET /shop/api/v1/notes?sort=desc&page=2 HTTP/1.1
Host: api.example.org:8443
```

And the Servlet container sees `scheme=https`, `port=8443`, `contextPath=/shop`, with `DispatcherServlet` mapped at `/` by default.

### 4.1. `fromCurrentRequest()` — full path **and query**

```java
URI sameRequest = ServletUriComponentsBuilder
        .fromCurrentRequest()
        .build()
        .toUri();
```

The resulting URI has the form:

```text
https://api.example.org:8443/shop/api/v1/notes?sort=desc&page=2
```

Use this when creating links to **variants of the current request**, replacing query parameters, or preserving list filters/sorts.

**Warning:** if used as the base to construct `Location` for a newly POSTed resource, the POST's query parameters may remain unnecessarily, such as `?debug=true` or `?source=web`. For new resource paths, `fromCurrentRequestUri()` or a context-based builder is usually more appropriate.

### 4.2. `fromCurrentRequestUri()` — has path, **no query**

```java
URI withoutQuery = ServletUriComponentsBuilder
        .fromCurrentRequestUri()
        .build()
        .toUri();
```

Result:

```text
https://api.example.org:8443/shop/api/v1/notes
```

Use for the current collection URI or building child URIs. For example, POST to `/api/v1/notes`, and after saving with ID 42:

```java
URI createdUri = ServletUriComponentsBuilder
        .fromCurrentRequestUri()
        .pathSegment("{id}")
        .encode()
        .buildAndExpand(42)
        .toUri();
```

Expected:

```text
https://api.example.org:8443/shop/api/v1/notes/42
```

**Do not append `"/42"` to a URL that already contains `?sort=desc&page=2` via string concatenation**, as it can become `...?sort=desc&page=2/42`.

### 4.3. `fromCurrentContextPath()` — origin + Servlet context path

```java
URI collection = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .path("/api/v1/notes")
        .build()
        .toUri();
```

Result:

```text
https://api.example.org:8443/shop/api/v1/notes
```

Use when you want to build a link to **another endpoint** within the same application, not necessarily a child of the current request. For example, code in `GET /shop/api/v1/search` wanting to link to `/shop/api/v1/notes`.

**Do not duplicate the context path**:

```java
// Wrong if contextPath is already /shop:
ServletUriComponentsBuilder.fromCurrentContextPath()
        .path("/shop/api/v1/notes");
```

The right way is to append the MVC route **after the context**, without re-inserting `/shop`.

### 4.4. `fromCurrentServletMapping()` — origin + context + servlet prefix

If `DispatcherServlet` is prefix-mapped such as `/main/*`, this builder pulls scheme/host/port/context path **plus the Servlet mapping prefix**:

```java
URI uri = ServletUriComponentsBuilder
        .fromCurrentServletMapping()
        .path("/accounts")
        .build()
        .toUri();
```

With context `/shop` and servlet mapping prefix `/main`, the result looks like:

```text
https://api.example.org:8443/shop/main/accounts
```

When the mapping is `/` or an extension mapping like `*.do`, `fromServletMapping` can behave like `fromContextPath` per Javadoc.

**Do not treat `servletPath` as an invariant route string** across all servlet mapping styles. Spring MVC's `PathPatternParser` and prefix servlet mappings have compatibility constraints depending on the Boot/framework version; if choosing prefix mapping, integration-test URIs and `HandlerMapping` on a real container.

### Comparison summary

| Method | Scheme/host/port | Context path | Servlet mapping prefix | Full request path | Query |
| --- | --- | --- | --- | --- | --- |
| `fromCurrentRequest()` | Yes | Included in full path | Included in full path if present | Yes | Yes |
| `fromCurrentRequestUri()` | Yes | Included in full path | Included in full path if present | Yes | **No** |
| `fromCurrentContextPath()` | Yes | Yes | Does not add separate prefix | No | No |
| `fromCurrentServletMapping()` | Yes | Yes | Yes if prefix mapping | Does not take full handler path | No |

“Current” here means the **Servlet request currently bound in `RequestContextHolder`**. It does not mean “the URL of the browser page open” inside a background job, nor does it infer the application's official URL when no request exists.

## 5. Explicit variants accepting `HttpServletRequest`

Each “current” method has an explicit factory method accepting a request:

| Current method | Method with request parameter |
| --- | --- |
| `fromCurrentRequest()` | `fromRequest(HttpServletRequest)` |
| `fromCurrentRequestUri()` | `fromRequestUri(HttpServletRequest)` |
| `fromCurrentContextPath()` | `fromContextPath(HttpServletRequest)` |
| `fromCurrentServletMapping()` | `fromServletMapping(HttpServletRequest)` |

Example inside a handler:

```java
@GetMapping("/self")
String self(HttpServletRequest request) {
    return ServletUriComponentsBuilder
            .fromRequestUri(request)
            .build()
            .toUriString();
}
```

This is a controller fragment, requiring `import jakarta.servlet.http.HttpServletRequest`. The biggest difference is that **the dependency is declared explicitly**. If code is called from a helper that already has a valid `HttpServletRequest`, this approach makes the data source clearer.

**Do not pass an expired-lifecycle request** into a background thread just to have a builder. A Servlet request belongs to the context of the request currently being processed; links for email/batch tasks should use a canonical base URL from configuration.

### 5.1. How is the current request found?

`ServletUriComponentsBuilder.fromCurrentXxx()` uses `RequestContextHolder`. `DispatcherServlet` normally exposes web request attributes while a handler runs; `RequestContextFilter` / `RequestContextListener` can support other components when configured.

In a scheduler, `@Async` worker, or a manually spawned thread, request attributes are not present by default. Calling `fromCurrentRequestUri()` there can throw an `IllegalStateException` regarding a missing request in the thread context.

**Do not work around this by copying `HttpServletRequest` into a static field or long-lived `ThreadLocal`.** Instead:

- Pass a safely constructed URL/base URI from the web layer if only that data is needed.
- Use a canonical external base URI from configuration when running email/batch tasks.
- In tests, mock the Servlet request or use MockMvc rather than depending on an ambient request outside MVC.
- For Spring MVC async requests, check how the framework binds/unbinds request context across dispatches/threads instead of guessing.

## 6. `path(...)`, `pathSegment(...)`, and URI encoding

### 6.1. `path(String)`

```java
URI uri = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .path("/api/v1/notes/")
        .path("42")
        .build()
        .toUri();
```

`path` appends a path portion to the builder. It is suitable for **static path segments** with proper `/` placement. However, if you concatenate untrusted input directly:

```java
// Anti-pattern: raw path can contain "/" or special characters.
.path("/api/v1/notes/" + userInput)
```

When `userInput` is `a/b`, it becomes **two path segments** instead of a single identifier; when input contains `?`, `#`, `%`, `;`, or Unicode, incorrect encoding can alter path meaning.

### 6.2. `pathSegment(String...)`

Use `pathSegment` for distinct segments:

```java
URI uri = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .pathSegment("api", "v1", "notes", "{slug}")
        .encode()
        .buildAndExpand("Spring MVC / cơ bản")
        .toUri();
```

With `encode()` **called on the builder before expanding**, reserved characters in variables are strictly encoded, so spaces and `/` inside the slug do not become route separators. The path will be percent-encoded, for example:

```text
.../api/v1/notes/Spring%20MVC%20%2F%20c%C6%A1%20b%E1%BA%A3n
```

This shows the UTF-8 percent-encoding form for the slug value; **it is not a mapping example guaranteeing that every Servlet container allows and avoids decoding `%2F` on a GET request**. Some containers/proxies reject or apply separate policies to **encoded slashes**. API design should prefer safe IDs such as numbers or UUIDs for resource paths, and put user strings in query/body if routing cannot be guaranteed.

### 6.3. Order of `encode()` and `buildAndExpand()`

Two easily confused encoding approaches:

```java
// Encode the template first and URI variables in stricter mode.
URI a = UriComponentsBuilder
        .fromUriString("https://api.example.org/items/{id}")
        .encode()
        .buildAndExpand("a/b")
        .toUri();

// Encode after expanding: may preserve some reserved characters
// according to each URI component's semantics.
URI b = UriComponentsBuilder
        .fromUriString("https://api.example.org/items/{id}")
        .buildAndExpand("a/b")
        .encode()
        .toUri();
```

In Spring Framework 6.2, `UriComponentsBuilder#encode()` before expansion is recommended by the docs when URI variables hold **data requiring strict encoding**. `UriComponents#encode()` after expansion has different semantics, especially with delimiters meaningful in that component.

**Do not double encode:** if the input is already `a%2Fb` (pre-encoded), calling encode again under a raw-values policy can turn `%` into `%25`, resulting in `a%252Fb`. Choose a clear contract: helpers take **raw values** or **already-encoded components**, never mixing the two.

### 6.4. `build()` and `toUri()`

| Call | Returns | When to use |
| --- | --- | --- |
| `builder.build()` | `UriComponents` | Need to further inspect/expand/encode |
| `builder.build().toUri()` | `java.net.URI` | Passing to ResponseEntity/HttpHeaders |
| `builder.buildAndExpand(values).toUri()` | `URI` | URI template with variables |
| `builder.encode().buildAndExpand(values).toUri()` | `URI` | Recommended when variables are raw user data |
| `builder.toUriString()` | URI string from builder | When a string is needed; mind encoding policy |
| `UriComponentsBuilder.fromUriString(...)` | Builder from template/string, independent of Servlet request | Background jobs/configured public base |

If the URI has no variables or special characters, `build().toUri()` is simple enough. When variables exist, control how they are encoded so they cannot alter URI structure.

## 7. Query parameters and pagination URLs

Suppose the client calls:

```http
GET /api/v1/notes?page=2&sort=desc HTTP/1.1
Host: api.example.org
```

Build a “next page” link while preserving `sort`:

```java
URI next = ServletUriComponentsBuilder
        .fromCurrentRequest()
        .replaceQueryParam("page", 3)
        .build()
        .toUri();
```

The result looks like:

```text
http://api.example.org/api/v1/notes?page=3&sort=desc
```

Query key ordering can vary across environments/parsers; **do not treat query key order as part of the contract**. Notes:

- `queryParam("page",3)` can **append** a new value alongside the old page. If the goal is to replace the current page, use **`replaceQueryParam`**.
- `replaceQueryParam("page", 3)` removes old values of page by name and adds the new value.
- `replaceQueryParam("page")` has different semantics and can remove the parameter per the API; check the exact overload/Javadoc.
- `replaceQuery(null)` can be used to clear the entire query in the builder when resetting before constructing a new query.
- Do not blindly mirror all query parameters into links if they carry secrets/tokens/debug flags. Consider an **allowlist of fields** such as `page`, `size`, `sort`.
- Never put credentials into the query string of `Location`, pagination, emails, or logs.
- The query builder does not enforce business limits (max page size, valid sort values, number overflow); the controller must validate them.

Example building pagination with only allowed query params:

```java
URI next = ServletUriComponentsBuilder
        .fromCurrentRequestUri()
        .queryParam("page", 3)
        .queryParam("size", 20)
        .queryParam("sort", "createdAt,desc")
        .build()
        .toUri();
```

This snippet drops all previous query inputs and rebuilds **server-selected parameters**. If `sort` comes from the user, validate the sort key/direction against an allowlist.

## 8. Generating Location properly for POST 201 Created

A resource-creating endpoint should execute business logic first, then generate a path to access the new resource.

Flow:

```text
POST /api/v1/notes
Content-Type: application/json
{"title":"Spring MVC"}

       |
       v
Validate -> Store/DB creates id=1001
       |
       v
ServletUriComponentsBuilder.fromCurrentRequestUri()
    .pathSegment("{id}")
    .encode()
    .buildAndExpand(1001)
    .toUri()
       |
       v
ResponseEntity.created(location).body(resource)
       |
       v
HTTP/1.1 201 Created
Location: http://localhost:8080/api/v1/notes/1001

{"id":1001,"title":"Spring MVC"}
```

**Note:** the illustrative response assumes the server is not running behind a proxy/context path and uses port 8080. If the actual HTTP request is handled properly by a proxy, `Location` can be `https://api.example.org/...`; do not hardcode `localhost:8080` in production.

### 8.1. Why is `fromCurrentRequestUri()` appropriate here?

- The POST collection endpoint has path `/api/v1/notes`, so appending `/{id}` points to the member resource.
- It drops old query params from the POST, such as `?notify=true`.
- It preserves the current origin and context path presented by the Servlet request.
- `pathSegment` provides a single-segment boundary for the ID.
- `ResponseEntity.created` sets 201 and `Location`.

**However, if POST creates a resource in a different collection**, e.g. `POST /api/v1/imports` creates `/api/v1/jobs/{id}`, do not append `/{id}` to imports. Build from the **context path** or actual route mapping instead:

```java
URI jobUri = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .pathSegment("api", "v1", "jobs", "{id}")
        .encode()
        .buildAndExpand(jobId)
        .toUri();
```

With a custom servlet mapping prefix, use `fromCurrentServletMapping`/an explicit configured route prefix where compatible; test the path end-to-end.

## 9. Runnable example: Spring Boot 3.5 and Java 17

The project below illustrates:

1. `POST /api/v1/notes` → 201 Created, Location derived from request URI without query.
2. `GET /api/v1/notes/{id}` → resource by ID.
3. `GET /api/v1/links/inspect?page=2&sort=desc` → compares variants with query, without query, context root, and query version page=3.
4. `GET /api/v1/links/catalog` → notes collection URI built from context path even though the current handler lives at another path.
5. You can test Host/scheme/port from the Servlet request; when deploying behind a proxy, add a trust policy as in section 12.

Data stored in `ConcurrentHashMap` is **for demonstration only**; restarting loses data. There is no auth, DB, transactions, or multi-node sharing. Do not use this demo as a production resource service.

### 9.1. Dependencies

For a Spring Boot **3.5.x**, Java 17 project, already configured with the Gradle Boot plugin, repositories, and toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **`build.gradle` fragment**, not a standalone build file. The web starter uses Spring MVC Servlet and Jackson managed by Boot 3. If using Maven, add the corresponding dependencies from the Boot BOM.

### 9.2. Application and controllers

Create **`src/main/java/demo/urilinks/UriLinksApplication.java`**:

```java
package demo.urilinks;

import java.net.URI;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@SpringBootApplication
public class UriLinksApplication {

    public static void main(String[] args) {
        SpringApplication.run(UriLinksApplication.class, args);
    }
}

record NewNote(String title) {}

record Note(long id, String title) {}

@RestController
@RequestMapping("/api/v1/notes")
class NoteController {

    private final AtomicLong sequence = new AtomicLong(1000);
    private final ConcurrentMap<Long, Note> notes =
            new ConcurrentHashMap<>();

    @PostMapping
    ResponseEntity<Note> create(@RequestBody NewNote input) {
        if (input == null || input.title() == null
                || input.title().isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "title is required");
        }

        long id = sequence.incrementAndGet();
        Note saved = new Note(id, input.title());
        notes.put(id, saved);

        URI location = ServletUriComponentsBuilder
                .fromCurrentRequestUri()
                .pathSegment("{id}")
                .encode()
                .buildAndExpand(id)
                .toUri();

        return ResponseEntity.created(location).body(saved);
    }

    @GetMapping("/{id}")
    Note find(@PathVariable long id) {
        Note value = notes.get(id);
        if (value == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Note not found");
        }
        return value;
    }
}

record UriSnapshot(
        String requestWithQuery,
        String requestWithoutQuery,
        String contextRoot,
        String notesCollection,
        String pageThree) {}

@RestController
@RequestMapping("/api/v1/links")
class LinksController {

    @GetMapping("/inspect")
    UriSnapshot inspect() {
        String withQuery = ServletUriComponentsBuilder
                .fromCurrentRequest()
                .build()
                .toUriString();

        String withoutQuery = ServletUriComponentsBuilder
                .fromCurrentRequestUri()
                .build()
                .toUriString();

        String context = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .build()
                .toUriString();

        String collection = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/api/v1/notes")
                .build()
                .toUriString();

        String nextPage = ServletUriComponentsBuilder
                .fromCurrentRequest()
                .replaceQueryParam("page", 3)
                .build()
                .toUriString();

        return new UriSnapshot(
                withQuery, withoutQuery, context,
                collection, nextPage);
    }

    @GetMapping("/catalog")
    ResponseEntity<Void> catalog() {
        URI uri = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/api/v1/notes")
                .build()
                .toUri();

        return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(uri)
                .build();
    }
}
```

This is **a single valid Java 17 file** in a Spring Boot 3.5 project with the dependencies above: only `UriLinksApplication` is public; the records/controllers are package-private and component-scanned under package `demo.urilinks`.

Analysis of the decisions:

- `NoteController#create` uses `fromCurrentRequestUri()` because the URI is generated for a child resource of the requested collection.
- `pathSegment("{id}")` represents the ID as a URI variable; `encode()` is called before `buildAndExpand(id)`.
- `ResponseEntity.created(location)` returns 201 and `Location`. The body is a Java record, serialized to JSON by Jackson.
- `GET /api/v1/notes/{id}` can be called with the path provided by `Location`, because the mapping matches the member URI.
- `LinksController#inspect` compares the factory methods side by side on the same request; `replaceQueryParam("page",3)` preserves other query keys in the example.
- `catalog` builds the URL from the context path, **not** appending `/notes` to `/api/v1/links/catalog`. It uses 303 as an HTTP navigation example; an endpoint does not have to redirect just to return a link.
- A URI builder does not check authentication or resource authorization. If the API is private, Spring Security is required at the appropriate layer.

### 9.3. Running and observing with curl

```bash
./gradlew bootRun
```

Create a note:

```bash
curl -i -X POST \
  'http://localhost:8080/api/v1/notes?notify=true' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Servlet URI Builder"}'
```

If this is the first note, expected response:

```http
HTTP/1.1 201 Created
Location: http://localhost:8080/api/v1/notes/1001
Content-Type: application/json

{"id":1001,"title":"Servlet URI Builder"}
```

**There is no `?notify=true` in `Location`** because `fromCurrentRequestUri()` was chosen. ID 1001 is illustrative and holds only when the counter starts at 1000 and no other POST has occurred.

Request the `Location`:

```bash
curl -i 'http://localhost:8080/api/v1/notes/1001'
```

Expected 200 and JSON of the created note, on the same un-restarted server instance. If scaled across multiple instances using a local map, GET on another node may return 404 — a storage issue, **not a builder bug**.

Inspect URI:

```bash
curl -sS \
  'http://localhost:8080/api/v1/links/inspect?page=2&sort=desc'
```

Illustrative body (JSON field/query param order is not part of the contract):

```json
{
  "requestWithQuery":
      "http://localhost:8080/api/v1/links/inspect?page=2&sort=desc",
  "requestWithoutQuery":
      "http://localhost:8080/api/v1/links/inspect",
  "contextRoot": "http://localhost:8080",
  "notesCollection": "http://localhost:8080/api/v1/notes",
  "pageThree":
      "http://localhost:8080/api/v1/links/inspect?page=3&sort=desc"
}
```

Fetch the collection link from another endpoint:

```bash
curl -i 'http://localhost:8080/api/v1/links/catalog'
```

Expected **303 See Other**, `Location: http://localhost:8080/api/v1/notes`. In the demo there is only a POST collection, with no GET collection declared yet, so **a client following `Location` with GET may receive 405**. This is a limitation of the redirect example lacking a list endpoint; in a real product, only redirect to targets supporting the right HTTP method, or add a GET collection. To avoid redirecting to an endpoint that does not support GET, add a GET handler when using this pattern; see the test example, which only asserts `Location` and does not assume GET succeeds.

## 10. MockMvc testing for URI/Location

MockMvc creates a simulated Servlet request, Spring MVC invokes the controller, and the request context is bound during handling. Use `MockMvcRequestBuilders`, `jsonPath`, and `header` to verify both success and failure cases. Create **`src/test/java/demo/urilinks/UriLinksApplicationTests.java`**:

```java
package demo.urilinks;

import java.net.URI;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UriLinksApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void createdLocationUsesCurrentPathWithoutOldQuery()
            throws Exception {

        MvcResult result = mvc.perform(
                post("/api/v1/notes?notify=true")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"title":"URI Builder"}
                        """))
            .andExpect(status().isCreated())
            .andReturn();

        String rawLocation = result.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(rawLocation);

        URI location = URI.create(rawLocation);
        assertTrue(location.isAbsolute());
        assertTrue(location.getPath().matches(
                "/api/v1/notes/[0-9]+"));
        assertEquals(null, location.getRawQuery());

        mvc.perform(get(location.getRawPath()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("URI Builder"));
    }

    @Test
    void inspectDistinguishesQueryAndRequestUri()
            throws Exception {

        mvc.perform(get(
                "/api/v1/links/inspect?page=2&sort=desc"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.requestWithQuery")
                .value(org.hamcrest.Matchers.containsString(
                    "?page=2&sort=desc")))
            .andExpect(jsonPath("$.requestWithoutQuery")
                .value(org.hamcrest.Matchers.endsWith(
                    "/api/v1/links/inspect")))
            .andExpect(jsonPath("$.notesCollection")
                .value(org.hamcrest.Matchers.endsWith(
                    "/api/v1/notes")))
            .andExpect(jsonPath("$.pageThree")
                .value(org.hamcrest.Matchers.containsString(
                    "page=3")));
    }

    @Test
    void contextRootIncludesServletContextPath()
            throws Exception {

        mvc.perform(get(
                "/shop/api/v1/links/inspect?page=2")
                    .contextPath("/shop")
                    .servletPath("/api/v1/links/inspect"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.contextRoot")
                .value(org.hamcrest.Matchers.endsWith("/shop")))
            .andExpect(jsonPath("$.notesCollection")
                .value(org.hamcrest.Matchers.endsWith(
                    "/shop/api/v1/notes")));
    }

    @Test
    void explicitCurrentOriginComesFromServletRequest()
            throws Exception {

        MvcResult result = mvc.perform(
                post("/api/v1/notes")
                    .scheme("https")
                    .serverName("edge.example.org")
                    .serverPort(443)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"title":"HTTPS"}
                        """))
            .andExpect(status().isCreated())
            .andReturn();

        String location = result.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(location);
        URI uri = URI.create(location);

        assertEquals("https", uri.getScheme());
        assertEquals("edge.example.org", uri.getHost());
        assertTrue(uri.getPath().startsWith("/api/v1/notes/"));
    }

    @Test
    void invalidTitleIsNotPersisted()
            throws Exception {

        mvc.perform(post("/api/v1/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"   "}
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unknownNoteReturns404() throws Exception {
        mvc.perform(get("/api/v1/notes/999999999"))
            .andExpect(status().isNotFound());
    }
}
```

Run:

```bash
./gradlew test
```

The tests are **designed to pass** on Spring Boot 3.5 with the dependencies and demo code shown above. This is an **expectation from reviewing the code**, not the result of an executed Gradle run. Several assertions use `Matchers.endsWith`/`containsString` to avoid depending on MockMvc's default port/host.

**Crucial testing note:** status 201 is not enough. You must verify `Location` actually contains the member URI, drops old query params, the GET resource is reachable, and the link respects the context path. The “host/scheme” test does not prove forwarded-header trust is secure; it only proves the builder reflects what the Servlet request provides.

## 11. Pure unit testing with MockHttpServletRequest when no controller is needed

With `spring-test`, you can create a fake request and call the parameterized builder directly without `RequestContextHolder`:

```java
import java.net.URI;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

MockHttpServletRequest request =
        new MockHttpServletRequest("GET", "/shop/api/v1/notes");

request.setScheme("https");
request.setServerName("example.org");
request.setServerPort(443);
request.setContextPath("/shop");
request.setQueryString("page=2&sort=desc");

URI withQuery = ServletUriComponentsBuilder
        .fromRequest(request)
        .build()
        .toUri();

URI withoutQuery = ServletUriComponentsBuilder
        .fromRequestUri(request)
        .build()
        .toUri();

System.out.println(withQuery);
System.out.println(withoutQuery);
```

This is a **fragment inside a test method**, because `MockHttpServletRequest` requires the `spring-test` dependency (available via starter-test) and is not a standalone `main` file. With the fields above, expected output:

```text
https://example.org/shop/api/v1/notes?page=2&sort=desc
https://example.org/shop/api/v1/notes
```

When constructing a fake request, ensure `requestURI`, `contextPath`, `servletPath`, and `queryString` are consistent with real requests, especially when testing prefix mappings. In a Boot app, integration tests must run after filters/proxies are properly configured.

## 12. Reverse proxies and forwarded headers — security centerpiece

In many deployments, clients do not call Tomcat directly; they call a load balancer or API gateway:

```text
Client:
  https://api.example.org/api/v1/notes

Reverse proxy:
  TLS termination; forwards to http://10.0.0.5:8080/api/v1/notes
  adds headers representing client origin (per trust policy)

Spring Boot backend:
  Internal HttpServletRequest sees http://10.0.0.5:8080
  if trusted forwarding is not configured

Wrong Location:
  http://10.0.0.5:8080/api/v1/notes/42

Desired Location:
  https://api.example.org/api/v1/notes/42
```

Commonly seen headers:

- `Forwarded: proto=https;host=api.example.org` (RFC 7239 standard).
- `X-Forwarded-Proto: https`.
- `X-Forwarded-Host: api.example.org`.
- `X-Forwarded-Port: 443`.
- `X-Forwarded-Prefix: /api` depending on proxy routing.
- `X-Forwarded-For` relates to client address and should not be used to derive the public host.

### 12.1. Why doesn't the builder read raw forwarded headers itself?

**Since Spring Framework 5.1**, `ServletUriComponentsBuilder` no longer automatically interprets `Forwarded` or `X-Forwarded-*` from request headers. Spring recommends using **`ForwardedHeaderFilter`** or container forwarding support so a request wrapper/Servlet container reflects the verified origin before the builder runs.

This cleanly separates who trusts forwarded data from who simply builds URIs from the request, yet **does not guarantee safety on its own**. If you configure the filter to trust headers directly from the Internet, an attacker can still control the host/scheme of generated URLs.

### 12.2. Spring Boot `server.forward-headers-strategy`

With Spring Boot 3.5:

```properties
# Choose ONE appropriate strategy once a trusted proxy is in place.
server.forward-headers-strategy=framework
```

Values:

| Value | Meaning |
| --- | --- |
| `none` | Boot does not automatically apply forwarding support; the app sees existing request/connector info |
| `native` | Uses the Servlet container's forwarded-headers support (e.g., Tomcat RemoteIpValve); header coverage varies by container |
| `framework` | Uses Spring Framework's `ForwardedHeaderFilter` for Servlet MVC |

If the proxy uses `X-Forwarded-Prefix` or complex semantics, `framework` may be needed because native container support does not cover every header. Boot docs note that for proxies setting `X-Forwarded-For`/`X-Forwarded-Proto`, `native` may suffice. **Do not enable both native and framework forwarding simultaneously by guesswork**; that can apply host/scheme/prefix twice or produce wrong results.

When using Tomcat and terminating HTTPS at a reverse proxy, Boot docs also mention configuring `server.tomcat.redirect-context-root=false` where needed so `X-Forwarded-Proto` is respected before container redirects.

### 12.3. The trust boundary is what decides

The reverse proxy/edge must:

1. **Strip/overwrite** all `Forwarded` and `X-Forwarded-*` headers sent by untrusted clients.
2. Only **add fresh headers** based on information verified/observed by the proxy.
3. Block direct Internet access to the backend if the backend trusts forwarded headers.
4. Control hostnames, schemes, ports, and trusted proxy IPs; accept only valid public origins.
5. Test the entire proxy/gateway/Ingress chain with multi-hop forwarding and `X-Forwarded-Prefix`.
6. Never use client-supplied forwarded information to build password reset links, email verification links, or OAuth callback URIs without a strict public-base policy.

Spring's `ForwardedHeaderFilter` can be configured with `removeOnly=true` to **strip** forwarded headers without **using** their values. This mode fits when there is no trusted proxy or when ensuring external forwarded headers cannot affect the request URI.

### 12.4. Host-header poisoning

Even without `X-Forwarded-Host`, the HTTP `Host` sent by a client can be untrusted under certain routing setups. A server returning:

```http
HTTP/1.1 201 Created
Location: https://evil.example/api/v1/notes/42
```

if building the host from an unvalidated request may accidentally generate links pointing to an attacker's domain.

**Security recommendations:**

- For `Location` self-links directly in a response behind a properly configured trusted gateway, a request-derived URL can be reasonable.
- For links **sent out via email**, password resets, magic logins, OAuth redirect URIs, and capability URLs, use a **server-configured canonical public base URI**, not derived from raw Host/Forwarded headers.
- Restrict allowed hosts at the gateway/web server and validate the request host if business logic requires it.
- Do not confuse `ServletUriComponentsBuilder` with an open-redirect validator; the builder only handles URI structure.

## 13. When to use absolute URIs, relative URIs, and canonical bases?

| Scenario | Usually appropriate choice |
| --- | --- |
| `Location` for resource-creating POST behind a trusted proxy | `fromCurrentRequestUri()` + path segment |
| Link to another endpoint in the same Servlet app | `fromCurrentContextPath()` + route |
| Pagination preserving filters/sorts | `fromCurrentRequest()` + `replaceQueryParam` |
| Servlet mapping prefix `/main/*` is used | `fromCurrentServletMapping()`, verify mapping compatibility |
| Generating URLs with no HTTP request (scheduler/email) | Canonical base URI from config |
| Password reset/OAuth callback, signed links | Canonical origin + strict allowlist/policy |
| SPA navigating within the same origin | Root-relative paths can reduce host coupling, though context path must be handled |
| Hypermedia links (HAL/JSON), versioned APIs | Builder or `MvcUriComponentsBuilder` matching actual mappings |
| Links to external websites | Do not build from raw user URLs; partner ID/allowlist and separate validation |

Example using a canonical base `https://api.example.org` for offline tasks:

```java
URI base = URI.create("https://api.example.org");

URI resource = UriComponentsBuilder
        .fromUri(base)
        .pathSegment("api", "v1", "notes", "{id}")
        .encode()
        .buildAndExpand(42)
        .toUri();
```

This code fragment **does not need a Servlet request**, making it convenient in message workers or email services. In a real app, the base should come from **validated configuration properties**, not an untrusted request header. If the external base includes a `/shop` prefix, control route appending to avoid losing or duplicating the prefix.

## 14. API version URIs: `/api/v1` and HATEOAS links

Because this lesson belongs to the **URI and API Versioning** group, putting the version in the path affects how links are built.

Example:

```text
POST /api/v1/notes
GET  /api/v1/notes/{id}

POST /api/v2/notes
GET  /api/v2/notes/{id}
```

If V1 and V2 controllers receive requests at separate collections, `fromCurrentRequestUri().pathSegment("{id}")` automatically picks up the **current collection path**. However, if a V2 POST creates a resource belonging to a different GET route (`/api/v2/documents/{id}`), you must build from the actual resource mapping rather than just appending an ID.

`fromCurrentContextPath()` is useful when building a specific link:

```java
URI v2Note = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .pathSegment("api", "v2", "notes", "{id}")
        .encode()
        .buildAndExpand(42)
        .toUri();
```

**Do not accidentally hardcode v1** in the `Location` of a V2 response. With header/media-type versioning instead of URL paths, URIs may not carry the version; in that case the link contract must document `Accept`/media types or the corresponding version negotiation mechanism.

### 14.1. `MvcUriComponentsBuilder` when basing links on controller mappings

Spring MVC provides **`MvcUriComponentsBuilder`**, which helps generate links based on `@RequestMapping`/`@GetMapping` annotations instead of repeating route strings everywhere. It is helpful when API paths are refactored and you want compiler/framework support to keep links consistent.

Fragment example per Javadoc:

```java
UriComponents components = MvcUriComponentsBuilder
        .fromMethodName(
                NoteController.class, "find", 42L)
        .build();

URI resourceUri = components.encode().toUri();
```

Condition: the `find(long id)` method in the example is annotated with `@GetMapping("/{id}")` and `@PathVariable`; Spring looks up the mapping metadata. With class-level `@RequestMapping("/api/v1/notes")`, the result binds to that route with the appropriate context/base URL.

Another option uses `MvcUriComponentsBuilder.on(...)` to create a proxy invocation:

```java
UriComponents components = MvcUriComponentsBuilder
        .fromMethodCall(
                MvcUriComponentsBuilder.on(NoteController.class)
                        .find(42L))
        .build();

URI uri = components.encode().toUri();
```

**Limitation note:** proxy invocation techniques have constraints on return types, class/method proxyability, and signatures. For instance, `find` returns record `Note` (records are final), so **there is no guarantee the proxy-call fragment works as expected** with a final return type. Use `fromMethodName` or refactor the endpoint to return a proxy-compatible type if you want the method-call API. The two fragments in this section are not needed for runnable demo 9.

Do not assume `MvcUriComponentsBuilder` safely accepts raw forwarded headers on its own; it requires the same request/proxy trust policy as `ServletUriComponentsBuilder`.

## 15. Pagination and the Link header

For a collection GET, an API may return a `Link` header such as:

```http
HTTP/1.1 200 OK
Link: <https://api.example.org/api/v1/notes?page=3&size=20>; rel="next"
Content-Type: application/json
```

`ServletUriComponentsBuilder.fromCurrentRequest().replaceQueryParam("page", ...)` helps construct the URI. However, to avoid leaking query credentials or retaining unauthorized parameters, a production API should explicitly select which fields are kept in the link.

Fragment:

```java
URI next = ServletUriComponentsBuilder
        .fromCurrentRequestUri()
        .queryParam("page", 3)
        .queryParam("size", 20)
        .build()
        .toUri();

return ResponseEntity.ok()
        .header(HttpHeaders.LINK,
                "<" + next + ">; rel=\"next\"")
        .body(pageData);
```

This is a **fragment inside a handler**, requiring `HttpHeaders`, `pageData`, and application-defined pagination logic. If `page` is already the last page, do not generate a meaningless `next` link. Ensure `page/size` are non-negative and within bounds, and that sort ordering is deterministic.

You can use `org.springframework.http.HttpHeaders` APIs and Spring HATEOAS if the application already uses hypermedia; however, **the URI builder itself does not manage resource relationships, pagination semantics, or permissions**.

## 16. Common pitfalls

| Symptom | Cause | How to address |
| --- | --- | --- |
| Location contains `?debug=true` from POST | Used `fromCurrentRequest()` to build child resource | Use `fromCurrentRequestUri()` or reset query |
| URI becomes `/api/v1/links/catalog/notes/42` | Appended path to another endpoint's request URI | Use context path + resource route |
| After deploying under `/shop`, link misses `/shop` | Used hardcoded `http://.../api/...` | Use `fromCurrentContextPath()` |
| URL becomes `/shop/shop/api` | Manually added context path again | Only append route after context |
| URI contains `http://10.x.x.x:8080` | TLS termination at proxy but forwarded headers not trusted/applied | Configure trusted proxy and forwarding strategy |
| Location contains attacker domain | Trusted client Host/Forwarded | Validate allowed hosts, strip forwarding, canonical base |
| `/` character in slug alters route | Concatenated input into `path` | `pathSegment("{slug}").encode().buildAndExpand`; consider safe IDs |
| URI contains `%252F` instead of `%2F` | Double-encoded an already-escaped value | Adopt a raw-value encoding contract |
| Query has `page=2&page=3` | Used `queryParam` instead of replace | `replaceQueryParam("page",3)` |
| `fromCurrent...` fails in async/job | Missing request context | Use explicit base or pass safe URI |
| URL has wrong scheme behind HTTPS proxy | Wrong `server.forward-headers-strategy` or untrusted forwarded headers | Check proxy/backend headers and Boot strategy |
| URL lacks servlet prefix `/main` | Used context path when route needs servlet mapping | Check `fromCurrentServletMapping` and mapping |
| Tests only assert 201 | Did not check Location or GET target | Assert URI path/query/host and follow GET |
| Redirecting POST carries sensitive payload | Chose 307/308 to untrusted target | Do not let input decide redirects; verify status |
| JSON links work on localhost but fail in production | Did not test reverse proxy/context path | HTTP integration tests behind gateway |
| URL uses external host when business only needs relative path | Overused absolute links from Host | Consider controlled root-relative paths |

**Reasonable diagnostic flow:** real request → Servlet fields (scheme, host, port, context, URI, query) → forwarded/proxy handling → chosen factory method → path/query modifications → encoding → HTTP output → URI received by client.

## 17. URI canonicalization and security notes

### 17.1. Open redirect

`ServletUriComponentsBuilder` does not inherently prevent open redirects. If an application does:

```java
@GetMapping("/jump")
String jump(@RequestParam String next) {
    return "redirect:" + next;
}
```

that is a bug of **trusting a user-supplied destination**, not a builder bug. A safe solution usually takes a valid destination key (`dashboard`, `help`) and maps it to a server-defined route, or uses an exact allowlist for external partners.

### 17.2. Host header and absolute links

If you build an absolute URL from the request and put it into a password reset email, the incoming host can influence the link in the email. Prefer a **canonical public URL from configuration**, strict host validation, HTTPS, and avoid logging secrets/query tokens indiscriminately.

### 17.3. CRLF, header injection, and encoded paths

URI builders provide encoding/parsing, yet do not turn untrusted raw input into trusted data. Avoid sending untrusted raw strings into `Location`/`Link`, validate scheme/host/path per contract, and only use verified typed `URI` objects. For reserved characters in path variables, container/proxy policies on encoded slashes, semicolons/matrix params, and path normalization can affect routing/authorization; test against the actual gateway.

### 17.4. A URI built for the client does not guarantee resource accessibility

A syntactically valid `Location` will still fail if the resource has not committed to the DB, another node cannot see the state, or Security denies GET. Ensure proper lifecycle, transactions, permissions, and retention.

`ResponseEntity.created(uri)` sets 201/Location; it **does not** prove the resource was persisted or the GET route is exposed. Test both.

## 18. Testing through a reverse proxy and real container

MockMvc lets you test the builder with request fields, yet does not verify **blocking attacker-sent forwarded headers** or real TLS termination.

For staging behind a gateway:

1. Send `POST /api/v1/notes` to the **public HTTPS URL**.
2. Confirm `201 Created` and `Location` has **scheme=https**, the right public host, port, and context/prefix.
3. Follow GET on `Location` from outside the gateway (with auth if needed), verifying 200 or the expected contract status.
4. Send a disallowed `Host` at the gateway to verify it is rejected/normalized and never appears in `Location`.
5. Check that client-sent `Forwarded` and `X-Forwarded-*` headers **are stripped/overwritten by the edge proxy**.
6. Test `X-Forwarded-Prefix` when the gateway adds/removes a path prefix.
7. With multiple nodes, ensure generated `Location` never exposes a backend IP and GET works when routed to another node.
8. Verify access logs and traces do not store bearer tokens or query secrets.
9. Evaluate an official canonical origin for out-of-request links (emails, scheduled jobs, external callbacks).
10. Do not enable `server.forward-headers-strategy=framework` on a backend directly exposed to the Internet without filtering forwarded headers.

Distinguish **NATIVE vs FRAMEWORK** via integration tests on the real servlet container, especially since Tomcat/Jetty/Undertow and gateways behave differently.

## 19. Choosing the right API for your need

| You want to... | Start from... |
| --- | --- |
| Build a URI identical to the HTTP request including query | `fromCurrentRequest()` |
| Build a URI of the current request path without query | `fromCurrentRequestUri()` |
| Link to another route in the same context | `fromCurrentContextPath()` |
| Link including servlet mapping prefix | `fromCurrentServletMapping()` |
| No ambient current request, but servlet request is available | `fromRequest(request)` / `fromRequestUri(request)` |
| No HTTP request (email, batch job) | `UriComponentsBuilder.fromUriString(configuredBase)` |
| Append a resource ID | `pathSegment("{id}").encode().buildAndExpand(id)` |
| Keep other query params, replace page | `replaceQueryParam("page",n)` |
| Drop old query, build curated query | `fromCurrentRequestUri().queryParam(...)` |
| Return 201 with Location | `ResponseEntity.created(uri).body(...)` |
| Derive from annotation routes | `MvcUriComponentsBuilder`, mind proxy/return-type limits |
| Deploy behind a trusted reverse proxy | `ForwardedHeaderFilter` or container support per Boot strategy |
| Security-sensitive canonical URL | Explicit validated public base from config |

## 20. Coding and deployment checklist

- [ ] Choose the right factory method: `fromCurrentRequest()` when query is needed, `fromCurrentRequestUri()` when it is not.
- [ ] Do not append to the current request path if the target resource belongs to another endpoint.
- [ ] When routes change/differ in version, use context base + controlled route.
- [ ] Use `pathSegment`/URI templates and encode variables in the right order.
- [ ] Do not double-encode already-escaped input; separate raw values from pre-encoded components.
- [ ] Do not place raw passwords/tokens/credentials in URIs/queries/Location.
- [ ] Ensure 201 `Location` points to a resource actually reachable under the API contract.
- [ ] Test context path/servlet mapping prefix/HTTPS/port.
- [ ] Choose the Spring Boot forwarding strategy intentionally; do not mix native and framework arbitrarily.
- [ ] Ensure the edge proxy strips/overwrites untrusted `Forwarded`/`X-Forwarded-*`.
- [ ] Ensure the gateway enforces allowed hosts; absolute email/OAuth/reset links use canonical base.
- [ ] Do not access request-bound builders from background threads lacking a request context.
- [ ] Have integration tests for pagination URLs, Location query stripping, and following GET.
- [ ] Ensure path/media-type API versioning is compatible with link generation.
- [ ] Independently verify security and authorization for generated URIs.

## 21. Self-assessment exercises

1. From request `https://example.org/shop/api/v1/notes?page=2`, write the outputs of `fromCurrentRequest()`, `fromCurrentRequestUri()`, and `fromCurrentContextPath()`.
2. An endpoint `POST /api/v1/notes?notify=true` creates ID 7. Why is `fromCurrentRequestUri().pathSegment("{id}")` better than `fromCurrentRequest().pathSegment("{id}")`?
3. Inside `GET /api/v1/links/inspect`, construct a link to `/api/v1/notes` without the `/api/v1/links/inspect` prefix.
4. When the application runs under `/shop`, why is `fromCurrentContextPath().path("/shop/api/v1/notes")` wrong?
5. Compare `path("/" + userSlug)` with `pathSegment("{slug}").encode().buildAndExpand(userSlug)` when the slug contains `/`.
6. What happens if you use `queryParam("page",3)` on a URL that already has `page=2`? Fix it with `replaceQueryParam`.
7. Why is `RequestContextHolder` not always present in `@Async` or scheduled jobs? How would you generate URLs for emails?
8. Reverse proxy clients use HTTPS while the backend uses HTTP: the URI builder returns the internal host. Which proxy/Boot layer must be fixed before the builder code runs?
9. Why must `X-Forwarded-Host` from the Internet never be trusted? Distinguish remove-only mode from trusted proxy mode.
10. Why does `ServletUriComponentsBuilder` not replace a URL allowlist validator when an app allows external redirects?
11. Write a MockMvc test that reads `Location` after POST and follows GET with the exact ID. Why is asserting status 201 alone insufficient?
12. If API V2 uses path `/api/v2/jobs/{id}` while POST calls `/api/v2/imports`, which factory should you use and how should you append the route?
13. Distinguish `MvcUriComponentsBuilder#fromMethodName` from `fromMethodCall`; why can a final return type impose proxy limitations?
14. If an application needs an absolute link in a password reset email, should the base URL come from the request `Host` or server config? Explain the threat model.
15. When a gateway replaces prefix `/internal` with `/public-api`, what must be checked so `Location` does not contain the internal prefix?

## 22. Official documentation

- [Spring Framework 6.2 — URI Links](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-uri-building.html): `UriComponentsBuilder`, `ServletUriComponentsBuilder`, `MvcUriComponentsBuilder`, URI templates, and encoding.
- [Spring Framework 6.2 — ServletUriComponentsBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html): all `fromCurrent*` and `fromXxx(HttpServletRequest)` methods.
- [Spring Framework 6.2 — UriComponentsBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html): `path`, `pathSegment`, `encode`, `queryParam`, `buildAndExpand`.
- [Spring Framework 6.2 — Servlet Filters / Forwarded Headers](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html): `ForwardedHeaderFilter`, security boundaries, and `X-Forwarded-Prefix`.
- [Spring Boot 3.5 — Embedded Servers / Forwarded Headers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): `server.forward-headers-strategy`, proxy support, and Tomcat.
- [Spring Framework 6.2 — HTTP ResponseEntity](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/ResponseEntity.html): 201 Created and Location header.
- [Spring Framework 6.2 — Path Matching](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-path.html): context/servlet mapping and path safety.
- [RFC 3986 — Uniform Resource Identifier Syntax](https://www.rfc-editor.org/rfc/rfc3986.html): scheme, authority, path, query, and fragment.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): `Location`, 201/303, and redirect semantics.
