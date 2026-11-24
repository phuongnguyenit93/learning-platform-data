# Distinguishing Path-Based, Header-Based, and Query Parameter Routing in Spring Boot

## Learning Objectives

After this lesson, you will be able to:

1. Understand **web routing** as the step of selecting which handler/controller will process an HTTP request before handling business logic.
2. Distinguish the three condition sources—**URL path**, **request header**, and **request parameter** (usually in the query string)—in Spring MVC and Spring WebFlux.
3. Correctly use **path/headers/params** on @RequestMapping, @GetMapping, and @PostMapping, while distinguishing them from **@PathVariable, @RequestHeader, and @RequestParam** used to read values.
4. Combine multiple conditions, understand matching behavior, specificity, and how to avoid ambiguous handler mappings.
5. Write a **Spring Boot 3.3.x, Java 17+** application with endpoints illustrating each routing style individually plus an endpoint combining both header and query conditions.
6. Verify routing with **curl** and **MockMvc**, identifying 400, 404, 405, 406, and 415 errors at the right processing layer.
7. Choose API designs that are maintainable, secure, and consistent with caches, proxies, browsers, and client applications.

**Scope:** The content focuses on HTTP handler routing in the Spring Boot web runtime, prioritizing Spring MVC and extending to Spring WebFlux annotated controllers. Examples run on **Spring Boot 3.3.x / Spring Framework 6.1.x / Java 17+**. This lesson does not cover Spring Cloud Gateway routing as an equivalent of controller functionality.

## 1. What is routing? Where does it happen?

Consider three requests:

~~~http
GET /api/items/7 HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

~~~http
GET /api/items?view=summary HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

~~~http
GET /api/channels HTTP/1.1
Host: localhost:8080
X-Channel: mobile
Accept: text/plain
~~~

They may arrive at the same server yet need to be dispatched to different methods:

- The first request identifies the resource using the **path** /api/items/7.
- The second request uses the **query parameter** view=summary to choose how the list is represented.
- The third request uses the **request header** X-Channel: mobile to choose a processing variant.

In Spring MVC, the logical flow:

~~~text
HTTP client
    |
    v
Embedded Tomcat / Servlet container
    |
    v
Servlet filters, Spring Security (if present)
    |
    v
DispatcherServlet
    |
    v
HandlerMapping
    |
    +-- HTTP method? GET/POST/PUT/DELETE?
    +-- URL path matches?
    +-- params condition matches?
    +-- headers condition matches?
    +-- consumes and produces match?
    |
    v
HandlerAdapter -> argument resolvers
    |
    v
Controller method -> service
    |
    v
Response body / view -> HTTP response
~~~

**Routing occurs before the controller is invoked.** Only after a handler is selected does Spring bind values such as @PathVariable, @RequestParam, and @RequestHeader to Java parameters.

In Spring WebFlux annotated controllers, @RequestMapping declarations and path/headers/params conditions work similarly, except requests flow through the reactive **HttpHandler/DispatcherHandler** instead of Servlet DispatcherServlet.

### @RequestMapping is a set of conditions

Example:

~~~java
@GetMapping(
    path = "/api/reports",
    params = {"format=brief", "page"},
    headers = "X-Client=mobile",
    produces = MediaType.APPLICATION_JSON_VALUE
)
~~~

Conceptually, this handler only matches when the request:

- Uses the GET method.
- Has path /api/reports.
- Has request parameter format equal to brief.
- Has request parameter page present.
- Has header X-Client with value mobile.
- Accepts a response compatible with application/json.

If only part of the conditions are met, the handler is not a valid match. A controller may have another mapping handling that request, or the outcome may be an appropriate error response.

## 2. URL structure: path and query are two distinct parts

Example URL:

~~~text
https://shop.example.com:8443/api/products/42?sort=price&limit=10
|------ scheme ---------|  |------ path ------| |--- query ------|
        host + port
~~~

Breakdown:

- Scheme: https.
- Host: shop.example.com.
- Port: 8443.
- Path: /api/products/42.
- Query: sort=price&limit=10.

The question mark **?** separates the path from the query. Anything after ? does not become a path segment just because it appears in the URL.

Example:

~~~text
/api/products/42?lang=vi
/api/products/42?lang=en
/api/products/42
~~~

All three have the **same path** /api/products/42. If a handler only declares path and method, all three usually route to the same handler. Query values can then be bound using @RequestParam.

### Routing does not mean selecting by Host

The Host header or HTTP/2 :authority typically identifies the authority the client is targeting, whereas the basic routing annotations covered here primarily match on path, method, params, headers, and media types. Routing by public domain name usually happens before Spring Boot at DNS, a reverse proxy, an API gateway, or a virtual host.

If multiple services sit behind one gateway, distinguish **gateway routing** from **controller method routing** inside each application.

## 3. Path-based routing

This is the most common choice for identifying resources or explicit HTTP actions.

~~~java
@GetMapping("/api/products")
List<Product> findAll() {
    // ...
}

@GetMapping("/api/products/{id}")
Product findById(@PathVariable long id) {
    // ...
}
~~~

These are two illustrative method snippets, not a standalone Java program. They express:

- GET /api/products selects the list.
- GET /api/products/7 selects the resource with id equal to 7.

**@PathVariable does not create a route on its own.** The route exists thanks to the pattern /api/products/{id} in @GetMapping; @PathVariable extracts the captured portion and converts it into a Java parameter.

### Important path pattern forms

| Pattern | Example matching request | Meaning |
|---|---|---|
| /api/books | /api/books | Static path |
| /api/books/{id} | /api/books/42 | Captures one path segment |
| /api/{kind}/{id} | /api/books/42 | Captures multiple segments |
| /files/*.pdf | /files/report.pdf | Wildcard within one segment |
| /assets/** | /assets/css/main.css | Multiple trailing path segments |
| /users/{id:[0-9]+} | /users/42 | Path variable with regex constraint |

**PathPattern note:** Spring MVC on Boot 3.x uses parsed path patterns in its common default configuration. Certain catch-all patterns with ** in PathPattern are not allowed arbitrarily in the middle of a path; if defined improperly, the application can fail with a mapping error at startup.

### Path specificity

Suppose you have:

~~~java
@GetMapping("/api/products/latest")
Product latest() {
    // ...
}

@GetMapping("/api/products/{id}")
Product byId(@PathVariable String id) {
    // ...
}
~~~

GET /api/products/latest can match both the literal pattern and the variable pattern. Spring uses specificity comparison rules to prioritize the static path /latest in this case. However, do not rely on confusing overlapping patterns for public APIs; clearer paths are easier to test and maintain.

### The trailing slash issue

~~~text
/api/products
/api/products/
~~~

Do not assume both URLs are always treated identically across all versions/configurations. In Spring Framework 6.x, automatically matching an optional trailing slash is no longer the default as it was in some older versions. Use a consistent canonical URL and only enable extra redirects/routes when truly needed.

### Path and context path

Suppose:

~~~properties
server.servlet.context-path=/shop
~~~

and the controller declares:

~~~java
@GetMapping("/api/products")
~~~

For a Spring MVC servlet application, the external URL is normally /shop/api/products. The **/shop** part is provided by the application's context path, not a path segment you should repeat in the annotation.

WebFlux has a different base path mechanism; do not assume server.servlet.context-path applies to a reactive web application.

## 4. Header-based routing: the headers condition

HTTP headers are metadata sent alongside a request. Spring can use headers to select a handler, for example when an API has processing variants for a specific protocol version or representation.

~~~java
@GetMapping(
    path = "/api/catalog",
    headers = "X-Channel=mobile"
)
String mobile() {
    return "mobile";
}

@GetMapping(
    path = "/api/catalog",
    headers = "X-Channel=web"
)
String web() {
    return "web";
}
~~~

This illustrates methods placed in a @RestController. Both share the same path and GET, but differ in the X-Channel header requirement.

Client sends:

~~~http
GET /api/catalog HTTP/1.1
X-Channel: mobile
~~~

The framework can select the mobile method.

### headers syntax

| Expression | Condition |
|---|---|
| headers="X-Debug" | Header X-Debug is present |
| headers="!X-Debug" | Header X-Debug is absent |
| headers="X-Channel=mobile" | Header has value mobile |
| headers="X-Channel!=mobile" | Header does not equal mobile per condition |
| headers={"X-Channel=mobile","X-Trace"} | Both channel value and trace presence must hold |

HTTP header names are **case-insensitive** per HTTP standards; for instance, X-Channel and x-channel refer to the same field name. Do not assume header **values** are also case-insensitive. Value comparison depends on individual field and mapping rules; for custom headers, standardize the exact string.

### Headers can select variants, not authenticate users

Writing:

~~~java
@GetMapping(
    path = "/api/admin",
    headers = "X-Role=admin"
)
~~~

**creates no security.** A client can forge X-Role: admin itself if the header is not controlled by a trusted component. Authentication and authorization must be implemented using Spring Security or an appropriate security mechanism, not via header mapping conditions.

Headers can be used for:

- Routing a clearly contracted HTTP interface variant.
- Experimenting with **non-sensitive** feature/client versions.
- Requiring a protocol-specific header.
- Distinguishing internal clients when requests already have proper authentication and contracts.

Limit creating too many distinct routes driven solely by arbitrary headers: they are hard to observe in URLs, often manipulated by proxies/gateways, and make testing/caching harder.

## 5. Headers for route selection differ from @RequestHeader

Compare two snippets:

~~~java
@GetMapping(
    path = "/api/hello",
    headers = "X-Channel=mobile"
)
String helloMobile() {
    return "hello mobile";
}
~~~

and:

~~~java
@GetMapping("/api/inspect")
String inspect(@RequestHeader("X-Channel") String channel) {
    return "channel=" + channel;
}
~~~

- headers="X-Channel=mobile" is a **condition for selecting the controller method**.
- @RequestHeader("X-Channel") is **how to extract the header after the route has been selected**.

In the second example, the /api/inspect route still matches by path/method even if the header is missing; binding a required @RequestHeader may then trigger **400 Bad Request** after handler selection. This is not the same as "no matching route found".

To make a header optional:

~~~java
@RequestHeader(value = "X-Channel", required = false) String channel
~~~

You can use defaultValue to supply a fallback value instead of receiving null. Multi-value headers can be bound to List or MultiValueMap depending on the API.

A single mapping that only needs to process header data generically should normally declare **one handler + @RequestHeader**, rather than splitting into multiple handlers using headers conditions.

## 6. Query parameter routing: the params condition

Query parameters are key/value pairs following ? in the URL:

~~~text
GET /api/products?view=summary
GET /api/products?view=detail
GET /api/products?view=summary&page=2
~~~

You can select a handler based on the value of view:

~~~java
@GetMapping(path = "/api/products", params = "view=summary")
List<String> summary() {
    return List.of("pen", "notebook");
}

@GetMapping(path = "/api/products", params = "view=detail")
List<Product> detail() {
    // ...
}
~~~

The two mappings differ in **params**. The view value resides in the query string when the client sends GET in this example.

### params syntax

| Expression | Meaning |
|---|---|
| params="debug" | Request parameter debug is present |
| params="!debug" | Request parameter debug is absent |
| params="view=summary" | Parameter view has value summary |
| params="view!=summary" | Value of view does not equal summary per condition |
| params={"debug=true","page"} | debug equals true **and** page is present |

If only params="debug" is specified, URLs ?debug, ?debug=, and ?debug=true can all satisfy the presence condition despite having different values. To require exact true, use params="debug=true".

### Distinguishing query strings from request parameters in Servlet MVC

In Spring MVC, the params attribute of @RequestMapping checks **Servlet request parameters**. For GET, the source is usually the query string. For application/x-www-form-urlencoded in some POST requests, the Servlet API can put form fields into the request parameter map, so do not state as an absolute rule that params only ever inspects URL queries.

Examples in this lesson focus on GET and query strings. When analyzing POST forms, you need to understand Content-Type, @RequestParam/@ModelAttribute, and how the container parses parameters.

### @RequestParam does not automatically create routing conditions

~~~java
@GetMapping("/api/products")
List<Product> list(
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "20") int size) {
    // ...
}
~~~

This method routes by **path /api/products and GET**. Parameters page/size are bound afterward; Spring does not automatically create two separate routes for ?page=1 and ?page=2.

If a required @RequestParam is missing, the route can still be selected, and then the argument binding step returns **400 Bad Request**. By contrast, if a method has params="mode=summary" and the request does not meet that condition, the method is excluded as a candidate handler right at the mapping step.

That is the core difference between a **routing condition** and **argument binding**.

## 7. Comparison table of the three mechanisms

| Criterion | Path | Header | Query parameter |
|---|---|---|---|
| Where it lives | Before ? in the request target | In HTTP request headers | After ? in the URL |
| Route declaration | path or value | headers | params |
| Reading data after route selection | @PathVariable | @RequestHeader | @RequestParam |
| Example | /orders/42 | X-Channel: mobile | ?page=2 |
| Best suited for | Resource identity, API structure | Protocol/client variants, metadata conditions | Filtering, sorting, pagination, display options |
| Directly visible in URL | Yes | No | Yes |
| Cache/proxy considerations | URL path is a common cache key component | Requires checking Vary/custom cache policies | Query is usually part of the URL cache key |
| Can client tamper with it | Yes | Yes | Yes |
| Can it replace authentication | No | No | No |
| Easy to debug via browser address bar | Yes | No, requires devtools/curl | Yes |

**Choose the right domain model:** Resource IDs usually belong in the path; filter/search state usually belongs in the query; metadata unsuitable for URLs can go in headers. Do not put credentials or highly sensitive data in queries just because @RequestParam is convenient: URLs routinely appear in logs, browser history, and analytics systems.

## 8. Combining path, headers, and params: AND and OR logic

Example:

~~~java
@GetMapping(
    path = {"/api/products", "/api/items"},
    params = {"view=summary", "page"},
    headers = {"X-Channel=mobile", "X-Trace"},
    produces = MediaType.APPLICATION_JSON_VALUE
)
~~~

Explanation:

- **Path array:** matches when URL is /api/products **or** /api/items.
- **params array:** must have view=summary **and** page present.
- **headers array:** must have X-Channel=mobile **and** X-Trace present.
- **produces:** response must be compatible with the client's acceptance of application/json.
- **@GetMapping:** HTTP method GET.

Not all annotation arrays share the same logic: **alternative path patterns are OR; multiple params/headers conditions are AND**. Multiple HTTP methods in @RequestMapping(method={...}) are also alternatives for the method.

Example of a matching request:

~~~http
GET /api/products?view=summary&page=2 HTTP/1.1
X-Channel: mobile
X-Trace: request-123
Accept: application/json
~~~

If X-Trace is missing, the mapping above is not a match, even if the path and query are right. If Accept only allows text/plain while the method only produces JSON, the response can be 406 depending on other mappings.

### Class-level and method-level

~~~java
@RestController
@RequestMapping(
    path = "/api",
    headers = "X-App=demo"
)
class ExampleController {

    @GetMapping(path = "/products", params = "view=summary")
    String summary() {
        return "ok";
    }
}
~~~

This is an illustrative snippet. Class-level path /api combines with method-level path /products; the class-level header condition continues to apply. Only when the request has both query view=summary and header X-App=demo does GET /api/products match.

**Exception to remember:** With consumes/produces, a method-level declaration can **override** the same condition type at the class level instead of merely adding to it. Do not generalize the combining rule of path/headers/params to every attribute.

## 9. Request mapping conditions and argument binding are two distinct stages

In Spring MVC:

~~~text
Step 1: HandlerMapping selects the handler
  - HTTP method, path, params, headers, consumes, produces

Step 2: Argument resolvers extract data for the Java method
  - @PathVariable
  - @RequestParam
  - @RequestHeader
  - @RequestBody
  - cookie, model, request/response objects, ...

Step 3: Validation, service, response
~~~

From this, distinguish three cases:

**Case A — No matching route**

Request GET /does-not-exist when no handler matches normally returns 404.

**Case B — Route selected, but parameter cannot be bound**

~~~java
@GetMapping("/api/orders/{id}")
String order(@PathVariable long id) {
    return "order";
}
~~~

GET /api/orders/abc matches the path variable, yet converting abc to long fails; the response is normally 400 rather than 404.

**Case C — Mapping condition present, but not satisfied**

~~~java
@GetMapping(path = "/api/orders", params = "view=summary")
String summary() {
    return "summary";
}
~~~

GET /api/orders?view=detail does not satisfy params. Spring MVC has specific handling for certain mismatches (such as request parameters), so you cannot claim **every** mismatch returns 404. The final status code depends on other mappings, HTTP method, consumes/produces, and exception handlers.

### Path, query, and header are not evaluated in an arbitrary controller-defined order

Spring Framework builds mapping info and compares candidates. Do not assume "the route declared first always wins" or "Spring just tries controllers top-to-bottom". If two mappings are not clearly distinguishable, runtime may fail to choose or produce surprising selection results.

## 10. Complete Spring Boot 3.3.x, Java 17+ example

Create a Spring Boot **Servlet / Spring MVC** application with the starter-web dependency. The example intentionally creates simple URLs with no database dependency.

### 10.1. Dependencies

In a Spring Boot Gradle project already configured with appropriate plugins/repositories:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is only the dependencies block in build.gradle, not a complete standalone build.gradle file. Use Java 17 or newer compatible with the Boot version.

### 10.2. Java application

Create the file **src/main/java/com/example/routing/RouteConditionsApplication.java**:

~~~java
package com.example.routing;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RouteConditionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(RouteConditionsApplication.class, args);
    }

    public record Item(long id, String name) {}

    public record SearchResult(
            String query, int limit, String client) {}

    @RestController
    @RequestMapping("/api")
    static class DemoController {

        // 1. Routing by path + @PathVariable.
        @GetMapping(
                path = "/items/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        Item byId(@PathVariable("id") long id) {
            return new Item(id, "item-" + id);
        }

        // 2a. Same method/path, select handler by query.
        @GetMapping(
                path = "/items",
                params = "view=summary",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        List<String> summary() {
            return List.of("pen", "notebook");
        }

        // 2b. Same method/path, but different query.
        @GetMapping(
                path = "/items",
                params = "view=detail",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        List<Item> details() {
            return List.of(
                    new Item(1, "pen"),
                    new Item(2, "notebook")
            );
        }

        // 3a. Select handler by header value.
        @GetMapping(
                path = "/channels",
                headers = "X-Channel=web",
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        String webChannel() {
            return "channel-web";
        }

        // 3b. Select handler by another header value.
        @GetMapping(
                path = "/channels",
                headers = "X-Channel=mobile",
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        String mobileChannel() {
            return "channel-mobile";
        }

        // 4. Require both query and header simultaneously.
        @GetMapping(
                path = "/combined",
                params = {"debug=true", "page"},
                headers = "X-Trace",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        Map<String, Object> combined(
                @RequestParam("page") int page,
                @RequestHeader("X-Trace") String trace) {
            return Map.of(
                    "page", page,
                    "trace", trace
            );
        }

        // 5. Only bind query/header; do not use them
        //    as handler branching conditions.
        @GetMapping(
                path = "/search",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        SearchResult search(
                @RequestParam(
                        name = "q", defaultValue = "all") String q,
                @RequestParam(
                        name = "limit", defaultValue = "10") int limit,
                @RequestHeader(
                        name = "X-Client",
                        required = false) String client) {
            return new SearchResult(
                    q,
                    limit,
                    client == null ? "none" : client
            );
        }
    }
}
~~~

This is a **complete Java source file for a Spring Boot project**, not a plain javac application requiring no dependencies. The nested static records and @RestController class reside inside package com.example.routing; Spring Boot will component-scan this controller.

All endpoints return illustrative data only. There is no authentication, database, or sensitive data. Therefore, the X-Channel header condition in the example only serves to observe routing, **not to provide security**.

### 10.3. Running the program

Set in src/main/resources/application.yml if you want a fixed port:

~~~yaml
server:
  port: 8080
~~~

Run from the project root directory:

~~~bash
./gradlew bootRun
~~~

In PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Wait for Spring Boot to report that the application has started. If port 8080 is already used by another process, change server.port and update the port in the curl commands.

### 10.4. Testing path-based routing

~~~bash
curl -s -H 'Accept: application/json' \
  http://localhost:8080/api/items/7
~~~

Significant JSON body:

~~~json
{"id":7,"name":"item-7"}
~~~

The controller receives @PathVariable("id") equal to 7, of type long. Calling /api/items/abc may match the pattern, yet converting the string abc to long fails, typically resulting in 400.

### 10.5. Testing query parameter routing

~~~bash
curl -s 'http://localhost:8080/api/items?view=summary'
~~~

Response body:

~~~json
["pen","notebook"]
~~~

~~~bash
curl -s 'http://localhost:8080/api/items?view=detail'
~~~

Response body:

~~~json
[{"id":1,"name":"pen"},{"id":2,"name":"notebook"}]
~~~

Both methods are GET /api/items. The params condition lets Spring differentiate method selection, not @RequestParam in the method signature.

If the URL is /api/items?view=other or omits view, neither mapping matches. **Do not rigidly guess 404**: in Spring MVC, having a mapping that matches path/method while failing a request parameter condition can result in 400 due to UnsatisfiedServletRequestParameterException, depending on context and exception handling.

### 10.6. Testing header-based routing

~~~bash
curl -s 'http://localhost:8080/api/channels' \
  -H 'X-Channel: web'
~~~

Body:

~~~text
channel-web
~~~

~~~bash
curl -s 'http://localhost:8080/api/channels' \
  -H 'X-Channel: mobile'
~~~

Body:

~~~text
channel-mobile
~~~

Header field names are case-insensitive per HTTP. For instance, header x-channel: mobile is normally processed equivalently to X-Channel: mobile.

If X-Channel is missing, do not force every failure into a single status code in the example; first check whether another handler exists on the same URL without a header condition.

### 10.7. Testing simultaneous header and query conditions

~~~bash
curl -s -H 'Accept: application/json' \
  -H 'X-Trace: t-123' \
  'http://localhost:8080/api/combined?debug=true&page=2'
~~~

JSON body contains:

~~~json
{"page":2,"trace":"t-123"}
~~~

Key order in JSON is not a contract. The mapping condition requires debug=true, page present, and X-Trace present; once the handler is selected, @RequestParam extracts page and @RequestHeader extracts X-Trace.

Try omitting either the X-Trace header or the debug=true query to observe that the mapping no longer matches completely. Use curl -i to inspect actual status and response rather than concluding error type solely from the URL.

### 10.8. Testing the difference between binding and routing

~~~bash
curl -s -H 'X-Client: desktop' \
  'http://localhost:8080/api/search?q=java&limit=5'
~~~

JSON body contains:

~~~json
{"query":"java","limit":5,"client":"desktop"}
~~~

Call:

~~~bash
curl -s 'http://localhost:8080/api/search'
~~~

Response contains default values:

~~~json
{"query":"all","limit":10,"client":"none"}
~~~

Both requests pick the **same search method**; @RequestParam and @RequestHeader merely supply data. There are no params or headers mapping conditions on /api/search.

### 10.9. Windows PowerShell

In Windows PowerShell, use **curl.exe** to avoid being interpreted as the Invoke-WebRequest alias:

~~~powershell
curl.exe -s "http://localhost:8080/api/items?view=summary"
curl.exe -s -H "X-Channel: mobile" "http://localhost:8080/api/channels"
curl.exe -s -H "X-Trace: t-123" "http://localhost:8080/api/combined?debug=true&page=2"
~~~

In PowerShell, & inside a URL must be enclosed in a quoted string. Without quotes, the shell may interpret it as a command separator rather than part of the URL.

## 11. Testing routing with MockMvc

With starter-test, create file **src/test/java/com/example/routing/RouteConditionsApplicationTests.java**:

~~~java
package com.example.routing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RouteConditionsApplicationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void routesByPathVariable() throws Exception {
        mockMvc.perform(get("/api/items/7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.name").value("item-7"));
    }

    @Test
    void routesByQueryParameter() throws Exception {
        mockMvc.perform(
                get("/api/items").param("view", "summary"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0]").value("pen"));

        mockMvc.perform(
                get("/api/items").param("view", "detail"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].name").value("pen"));
    }

    @Test
    void routesByHeaderValue() throws Exception {
        mockMvc.perform(
                get("/api/channels").header("X-Channel", "web"))
            .andExpect(status().isOk())
            .andExpect(content().string("channel-web"));

        mockMvc.perform(
                get("/api/channels").header("X-Channel", "mobile"))
            .andExpect(status().isOk())
            .andExpect(content().string("channel-mobile"));
    }

    @Test
    void combinesHeaderAndQueryConditions() throws Exception {
        mockMvc.perform(get("/api/combined")
                    .param("debug", "true")
                    .param("page", "2")
                    .header("X-Trace", "t-123"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page").value(2))
            .andExpect(jsonPath("$.trace").value("t-123"));
    }

    @Test
    void bindsValuesWithoutExtraRoutingConditions() throws Exception {
        mockMvc.perform(get("/api/search")
                    .param("q", "java")
                    .param("limit", "5")
                    .header("X-Client", "desktop"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.query").value("java"))
            .andExpect(jsonPath("$.limit").value(5))
            .andExpect(jsonPath("$.client").value("desktop"));

        mockMvc.perform(get("/api/search"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.query").value("all"))
            .andExpect(jsonPath("$.limit").value(10))
            .andExpect(jsonPath("$.client").value("none"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

With PowerShell:

~~~powershell
.\gradlew.bat test
~~~

MockMvc executes the Spring MVC pipeline **without opening a real TCP port**. It is useful for asserting which mapping was selected, whether the JSON body is correct, and how argument binding behaves.

Do not assert a blanket 404 for all missing query/header scenarios. To test error paths, assert the **actual code defined by the endpoint contract and Framework version**, using isBadRequest/isNotFound/isMethodNotAllowed... for each specific case.

## 12. When is a mapping ambiguous?

Example to avoid:

~~~java
@GetMapping("/api/info")
String infoA() {
    return "a";
}

@GetMapping("/api/info")
String infoB() {
    return "b";
}
~~~

Both methods have the same HTTP method and path, with no additional conditions to distinguish them. Spring may report **Ambiguous mapping** when registering mappings at startup.

A subtler example:

~~~java
@GetMapping(path = "/api/info", params = "debug")
String debug() {
    return "debug";
}

@GetMapping(path = "/api/info", headers = "X-Verbose")
String verbose() {
    return "verbose";
}
~~~

A request with both ?debug and X-Verbose satisfies both condition sets. Depending on mapping specificity rules, selection may be unexpected or ambiguous. Do not design APIs that depend on overlapping cases where readers have to guess the comparator.

**Safer design:**

- Use a single handler for the same operation and bind options as parameters.
- Or partition routes using **mutually exclusive** conditions, such as view=summary and view=detail with an explicit single-value contract.
- When combining conditions, build a matrix of all supported path + method + query + header combinations.
- Add tests for every meaningful combination and missing-condition case.
- Avoid relying on method declaration order inside the class.

### Distinguish path specificity from full mapping specificity

The literal path /api/items/latest is typically more specific than /api/items/{id}. Beyond the path, however, Spring also evaluates other mapping conditions such as params, headers, and media types. A mapping with a matching path is not guaranteed to be chosen if its accompanying conditions do not match.

## 13. Content-Type and Accept are special header cases

HTTP Content-Type and Accept are both headers, yet Spring recommends expressing them via **consumes** and **produces**, rather than writing generic headers conditions instead.

Example:

~~~java
@PostMapping(
    path = "/api/products",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
Product create(@RequestBody ProductInput input) {
    // ...
}
~~~

This is an illustrative snippet and needs to be inside a controller with suitable ProductInput/Product types.

- **consumes** checks the **request body** media type supported by the handler; typically tied to Request Content-Type.
- **produces** checks the representation returned by the server, coordinating with request Accept.
- **headers** handles other header conditions like X-Client or X-Feature.
- **@RequestHeader("Content-Type")** only retrieves the header value; it does not perform JSON decoding or content negotiation.

Status examples:

| Scenario | Typical response |
|---|---|
| Path has no handler | 404 Not Found |
| Path matches but HTTP method is wrong, no other handler | 405 Method Not Allowed |
| Request Content-Type does not match consumes | 415 Unsupported Media Type |
| Request Accept does not match produces | 406 Not Acceptable |
| Controller selected, but @RequestParam int fails parsing | 400 Bad Request |
| Mapping params condition not satisfied | May be 400 in Spring MVC depending on match/exception handling |
| Custom header condition not satisfied | Usually skips that mapping; status depends on other handlers |

Do not guess error codes from a single annotation line without checking all handlers sharing that path, HTTP methods, and exception handlers.

## 14. Multi-value query parameters, URL encoding, and ordering

A query string can repeat the same key:

~~~text
/api/products?tag=java&tag=spring
~~~

Use binding:

~~~java
@GetMapping("/api/products")
List<String> tags(@RequestParam("tag") List<String> tags) {
    return tags;
}
~~~

This is an illustrative method inside a REST controller. It can receive multiple tag values (via binding), though filtering logic is still executed by the application.

To preserve all repeated values and keys, you can use MultiValueMap<String,String> with @RequestParam. Using only Map<String,String> may not retain all repeated values.

### What about params="tag=java" with multiple values?

For repeatable request parameters, single-value matching rules depend on the framework and how the container represents lists. Avoid designing multiple handlers differing only by a key that can hold multiple values, such as tag=java and tag=spring on the same URL. It is usually better to use one handler and **@RequestParam List<String> tag** to filter explicitly.

### URL encoding

~~~text
q=hello%20world
name=Lan%20Anh
~~~

%20 represents a space in URL encoding. Query parameters are decoded before binding to parameters according to Servlet/WebFlux rules. A **+** sign in queries can be decoded as a space under form-style encoding, so when a literal plus sign is needed it must be properly encoded. Do not write ad-hoc String.split("&") / URLDecoder code inside business controllers when the framework already handles binding.

### Case sensitivity and parameter names

Normally **view** and **View** are two distinct parameter names in the request parameter map. Standardize naming conventions (such as lowercase camelCase) and do not assume the framework normalizes casing the way HTTP header field names do.

### Do not use queries for highly sensitive information

URLs routinely appear in:

- Browser history.
- Access logs of web servers, reverse proxies, and CDNs.
- Monitoring/tracing and analytics.
- HTTP cache keys and shared links.

Avoid putting access tokens, passwords, or unnecessary personal information in queries. Query-based routing does not make data safer than sending it in headers/bodies; protect it according to your threat model.

## 15. Header routing with proxies, caches, and browsers

Headers may not be forwarded intact across every network layer:

~~~text
Browser / Mobile
        |
        v
Reverse proxy / API gateway
        |
        v
Spring Boot @RequestMapping(headers=...)
~~~

Proxies may add, strip, or normalize certain headers according to configuration. Before debugging a controller, verify that the request finally **reaching Spring** carries the exact expected header.

### Headers differ from HTTP Host

Client sends:

~~~http
GET /api/catalog HTTP/1.1
Host: shop.example.com
X-Channel: mobile
~~~

Host represents the request authority and can be used by a reverse proxy to select an upstream. X-Channel is custom metadata that a controller can use in a headers condition.

Spring does not automatically route requests to another domain/port just because of @GetMapping(headers="X-Channel=mobile"). Controller routing only decides which method handles a request **that has already arrived at the application**.

### CORS is not header routing

When a browser calls a cross-origin API, a CORS preflight OPTIONS request may occur. A @GetMapping that merely constrains a custom header does not grant the browser permission to send that header. You must configure CORS for appropriate origins, methods, and headers; even when CORS permits it, authentication/authorization must still operate independently.

### HTTP caching and Vary

If the same URL has multiple representations chosen by a request header, an intermediate HTTP cache needs to know when the response varies by that header. A Vary header may be necessary, for example:

~~~http
Vary: X-Channel
~~~

This illustrates cache semantics, not a header that @GetMapping automatically guarantees to emit in all cases. If headers select documents/representations without proper cache configuration, clients may receive cached versions meant for a different header group.

In many cases, placing major variants in the **path** or **query** is easier to observe and more cache-friendly, though each option still requires proper cache key and security design.

## 16. Comparing Spring MVC annotated routing with Spring WebFlux

Both stacks support:

~~~java
@GetMapping(
    path = "/api/items/{id}",
    params = "view=detail",
    headers = "X-Channel=mobile"
)
~~~

Internally, however, they differ:

| Property | Spring MVC | Spring WebFlux |
|---|---|---|
| Web runtime | Servlet | Reactive HTTP stack |
| Front controller | DispatcherServlet | DispatcherHandler |
| Typical handler mapping | RequestMappingHandlerMapping MVC | RequestMappingHandlerMapping WebFlux |
| Route annotation | @RequestMapping/@GetMapping | @RequestMapping/@GetMapping |
| Extracting path/query/header | @PathVariable/@RequestParam/@RequestHeader | Equivalent annotations |
| Reading/writing JSON body | HttpMessageConverter | HttpMessageReader/Writer codecs |
| Controller return | DTO/ResponseEntity/async types | Mono/Flux/DTO/ResponseEntity |
| Functional routing | MVC.fn also has RouterFunction | WebFlux.fn RouterFunction |

Semantically, path/header/query remain parts of the HTTP request. WebFlux does not turn a headers condition into security, nor does it turn @RequestParam into an automatic routing condition.

**Boot note:** If a project includes both spring-boot-starter-web and spring-boot-starter-webflux, Spring Boot typically chooses Servlet/Spring MVC as the default server stack. Using WebClient does not mean the server application is running WebFlux.

### WebFlux.fn and request predicates

In addition to annotations, WebFlux.fn has a RequestPredicate API to combine method, path, query, and headers. Example of a bean in a project **using only starter-webflux**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
class FunctionalRouteConfig {

    @Bean
    RouterFunction<ServerResponse> demoRoute() {
        return RouterFunctions.route()
            .GET(
                "/fn/hello",
                RequestPredicates.queryParam("mode", "brief")
                    .and(RequestPredicates.headers(
                        h -> "yes".equals(h.getFirst("X-Debug")))),
                req -> ServerResponse.ok().bodyValue("hello")
            )
            .build();
    }
}
~~~

This is an **additional configuration class** inside a WebFlux application, not a standalone application. The endpoint only matches GET /fn/hello?mode=brief with header X-Debug: yes. Do not use this configuration to replace spring-boot-starter-web in the Spring MVC example above; the two examples illustrate two different stacks.

In functional routing, RequestPredicate.and combines multiple conditions; or permits either condition. This API is an alternative way to write conditions compared to annotations, not a network routing system at a gateway.

## 17. API design: when should you use path, query, or header?

### Case 1 — Retrieving a single resource

~~~http
GET /api/orders/123
~~~

Use a path variable because 123 identifies the resource.

### Case 2 — Filtering and paginating a resource collection

~~~http
GET /api/orders?status=PAID&page=2&size=20
~~~

Usually one route GET /api/orders is enough. Bind query values with @RequestParam, validate them, and query data. **Do not create a separate controller method for every status or page.**

### Case 3 — Two distinct representations on the same URL

~~~http
GET /api/reports?format=summary
GET /api/reports?format=detail
~~~

You can select two handlers using params if their processing structures truly differ. If only a minor serialization option differs, one handler with @RequestParam may be simpler.

### Case 4 — API representation by media type

~~~http
GET /api/reports HTTP/1.1
Accept: application/json
~~~

If the main difference is representation format (JSON/XML/text), use **produces** and content negotiation instead of inventing arbitrary X-Format headers.

### Case 5 — Protocol-specific metadata

~~~http
GET /api/config HTTP/1.1
X-Channel: mobile
~~~

Header routing can fit when the API contract is clearly defined and proxies/caches are configured consistently. Do not use custom headers in place of OAuth/JWT or authorization policies.

### Case 6 — API versioning

Common approaches:

~~~text
/api/v1/orders/123                  (path version)
/api/orders?version=1               (query version)
X-API-Version: 1                    (custom header version)
Accept: application/vnd.shop.v1+json  (media type version)
~~~

Each approach has trade-offs in URLs, cacheability, tooling, documentation, migration, and gateways. Spring Boot 3.3 / Spring Framework 6.1 can implement these patterns using @RequestMapping conditions, though do not assume newer versioning features in Spring Framework 7 already exist in Boot 3.3.

**Do not change a public API versioning strategy just because an annotation syntax is shorter.** It must align across gateways, docs, SDKs, and clients.

## 18. Reading routing errors through HTTP status codes

A useful checklist:

| Observation | Where to inspect |
|---|---|
| 404 | No matching path/handler, custom header condition did not match, or route was not scanned |
| 405 | Path has a handler, but the HTTP method is unsupported |
| 400 | Missing required @RequestParam, parameter conversion failure, or request-params mapping mismatch in MVC |
| 406 | Request Accept is incompatible with representations the server can produce |
| 415 | Request Content-Type does not match consumes |
| 401/403 | Authentication/authorization at security filter or method security |
| 500 | Application error or ambiguous/runtime mapping error, depending on cause |

**Do not equate 404 with a wrong path.** A GET method on the same path that only matches headers="X-Mode=web" can be skipped when the header is unmet, ending up looking like no handler was found. Conversely, a method matching the path whose @RequestParam long id fails to convert can return 400.

### Step-by-step debugging workflow

1. **HTTP method:** Did the client actually call GET, POST, PUT...? Was it altered by CORS preflight OPTIONS or a proxy?
2. **Path:** Is there a context path, base path, trailing slash, URL encoding, or gateway rewrite?
3. **Route existence:** Was the controller component-scanned? Is @RestController or @Controller configured properly?
4. **params:** Are query keys/values exact? Are there repeated keys, encoding, defaultValue, required=true, or form parameters?
5. **headers:** Did the header reach the server? Are name/value exact, stripped by a proxy, or blocked by browser preflight?
6. **Media types:** Do consumes and produces align with Content-Type and Accept?
7. **Argument binding:** After route selection, did parsing int/long/UUID/enum succeed?
8. **Ambiguity:** Are two methods mapped identically or overlapping? Was there a startup error for duplicate mapping?
9. **Security:** Did 401/403 occur before the controller in Spring Security or at method-level authorization?
10. **Evidence-based observation:** Enable appropriate routing logs and add MockMvc/WebTestClient tests for the specific request.

When debugging, you can temporarily enable:

~~~properties
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
~~~

These logger names apply to Spring MVC. For WebFlux, use loggers under org.springframework.web.reactive. TRACE/DEBUG may expose request metadata in logs; do not leave them continuously enabled in production without data-protection policies.

## 19. Very common misconceptions

### "@RequestParam makes Spring select a handler by query"

False. @RequestParam **binds a value** to an argument. Only when a mapping has a params condition does the parameter value directly participate in selecting a handler.

### "@RequestHeader and headers are the same thing"

False. @RequestHeader retrieves a value inside the controller method; the headers condition is evaluated earlier to decide whether the method matches.

### "The path includes the query string"

False. /api/items/7?view=summary still has path /api/items/7. The query is a separate part.

### "Writing two @GetMapping methods with the same path lets Spring pick by declaration order"

False. Two mappings need sufficiently distinct conditions, and Spring uses matching/comparison rules. Duplicate mappings can prevent the application from starting.

### "Because X-Admin=true is present, the route is protected"

False. Clients can spoof custom headers; routing is not authorization.

### "A missing query condition always returns 404"

Inaccurate. Spring MVC handles request parameter mismatches specifically and may return 400 when path/method match but the params condition is unmet. Status depends on actual routing results and exception handling.

### "Header names must match exact uppercase/lowercase"

False at the HTTP field-name level: X-Channel and x-channel are case-insensitive as field names. **Values** are a separate matter.

### "If CORS allows the header, clients are automatically authorized to call the endpoint safely"

False. CORS governs whether browser cross-origin scripts can send/read requests per policy; it does not replace authentication, firewalls, or permission checking.

### "All clients encode queries the same way"

Not guaranteed. Use URI builders or compliant HTTP libraries to encode queries, path segments, and special characters. Do not concatenate URLs manually with unencoded input.

### "If a route returns 404, Spring Boot definitely isn't running"

False. The server may be running normally while no handler matches the method/path/headers/params. Check HTTP statuses, logs, and other routes before concluding the server is down.

## 20. Practice with a request matrix

Suppose you have three mappings:

~~~java
@GetMapping(
    path = "/api/tasks",
    params = "mode=short",
    headers = "X-Client=web")
String shortWeb() { return "A"; }

@GetMapping(
    path = "/api/tasks",
    params = "mode=long",
    headers = "X-Client=web")
String longWeb() { return "B"; }

@GetMapping(
    path = "/api/tasks",
    params = "mode=short",
    headers = "X-Client=mobile")
String shortMobile() { return "C"; }
~~~

These are illustrative methods inside a REST controller.

| Request | Matching handler per conditions |
|---|---|
| GET /api/tasks?mode=short, X-Client: web | A |
| GET /api/tasks?mode=long, X-Client: web | B |
| GET /api/tasks?mode=short, X-Client: mobile | C |
| GET /api/tasks?mode=long, X-Client: mobile | No handler in this example set |
| GET /api/tasks?mode=short, missing X-Client | No handler in this example set |
| POST /api/tasks?mode=short, X-Client: web | Does not match HTTP method GET |

The table only identifies **which handler satisfies the conditions in this example set**, without asserting every HTTP status, because a real application may have other handlers, exception resolvers, and security filters.

From the matrix, if you want to add a mode=long, X-Client=mobile variant, you must create a new handler or use a shared handler and treat mode/channel as internal data.

## 21. Self-check questions

**Question 1.** For /api/orders/15?include=items, which part is the path and which part is the query?

**Answer:** The path is /api/orders/15. The query parameter include has value items. With route /api/orders/{id}, @PathVariable extracts 15; @RequestParam can extract include.

**Question 2.** Two handlers share GET /api/orders, differing by params="view=summary" and params="view=detail". Where will GET /api/orders?view=detail go?

**Answer:** The handler with params="view=detail", assuming no other condition prevents selection.

**Question 3.** GET /api/orders?view=summary matches params, yet is missing headers="X-Channel=mobile" from the mapping. Is the handler invoked?

**Answer:** No, because all applicable conditions must hold. Check other handlers or error resolvers to determine the resulting status.

**Question 4.** A controller uses @GetMapping("/api/search") and @RequestParam(defaultValue="all") String q. Does GET /api/search?q=java use a different route than GET /api/search?

**Answer:** No. Same route; the value of q differs during binding.

**Question 5.** Can @RequestHeader read X-Trace-Id without adding a headers condition?

**Answer:** Yes. @RequestHeader only binds the value after the route is selected; use required=false or defaultValue if the header is optional.

**Question 6.** Is using headers="X-User=alice" to allow only Alice to call an API secure?

**Answer:** No. Custom headers can be spoofed. Identity authentication and authorization must happen at the security layer.

**Question 7.** To return JSON or XML based on Accept, should you use a headers condition or produces?

**Answer:** Normally use produces and content negotiation; writers/converters must actually support the corresponding representations.

**Question 8.** Both patterns /api/products/latest and /api/products/{id} match /api/products/latest. Which pattern is more specific?

**Answer:** The literal /api/products/latest is more specific and usually wins according to pattern specificity rules.

**Question 9.** Why should ?tag=java&tag=spring usually be handled by one handler instead of splitting routes per tag?

**Answer:** One request can carry multiple values for the same key; branching per value can overlap. @RequestParam List<String> tag and explicit filtering in one handler is usually cleaner to design.

**Question 10.** Why might a header condition work in curl yet fail in a browser calling from another origin?

**Answer:** The browser may have to pass CORS preflight, a proxy may alter headers, or JavaScript may be blocked from sending the request under current policy. Inspect CORS and the request actually received by the server.

## 22. Application checklist

- [ ] Each endpoint has an explicit HTTP method and path.
- [ ] Distinguish route selection from binding @PathVariable/@RequestHeader/@RequestParam.
- [ ] Use paths for resource identity and API structure.
- [ ] Use queries for filters, sorting, pagination, and search options.
- [ ] Only use headers conditions when metadata is genuinely part of the routing contract.
- [ ] Never use custom headers/queries in place of authentication or authorization.
- [ ] For JSON/XML/text, consider consumes/produces and content negotiation before adding custom headers.
- [ ] Never design routes with ambiguous overlapping conditions.
- [ ] Test both successful requests and requests failing path/header/query conditions.
- [ ] Account for URL encoding, repeated parameters, header normalization, and reverse proxies.
- [ ] Do not put sensitive data into URL queries unnecessarily.
- [ ] Maintain logging/tests to distinguish route, binding, media type, security, and business errors.

## References

- [Spring Framework — Mapping Requests in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework — Mapping Requests in Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html)
- [Spring Framework — RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring Framework — RequestHeader](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestheader.html)
- [Spring Framework — WebFlux Functional Endpoints and RequestPredicates](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html)
