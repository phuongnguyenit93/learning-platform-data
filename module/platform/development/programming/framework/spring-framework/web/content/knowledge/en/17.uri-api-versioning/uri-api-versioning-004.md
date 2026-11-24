# MvcUriComponentsBuilder and Building Links to Controllers in Spring MVC

## 1. Goal and problem

A Spring MVC application has endpoints `GET /books/{id}`, `GET /books/search?q=...`, and several HTML pages. You want to build **links** pointing to those endpoints in JSON, HTML, or redirects. Writing the string `"/books/" + id` is easy at first, yet when a controller changes `@RequestMapping`, adds a context path, renames a parameter, sits behind a reverse proxy, or passes special characters, manually concatenated URLs easily break.

**`MvcUriComponentsBuilder`** (package `org.springframework.web.servlet.mvc.method.annotation`) is a Spring MVC utility for **building URIs from controller/method mapping metadata**, rather than manually copying paths declared in annotations.

This lesson helps you:

1. Distinguish `URI`, `URL`, **URI template**, path variable, query parameter, and **link to an endpoint/controller**.
2. Understand the relationship of `MvcUriComponentsBuilder` with `UriComponentsBuilder`, `ServletUriComponentsBuilder`, `@RequestMapping`, `@PathVariable`, and `@RequestParam`.
3. Generate links using `fromController`, `fromMethodName`, `fromMethodCall(on(...))`, `fromMethod`, and `fromMappingName`; know when each API fits.
4. Understand the **proxy limitations** of `on(...)` — especially with `final` return types such as `String`.
5. Build URIs with a **custom base URL** via `relativeTo` or overloads accepting `UriComponentsBuilder`, handling context path/proxy and query encoding.
6. Build a **Java 17+, Spring Boot 3.x, Spring Framework 6.x** example with an HTML controller, a JSON link-returning API, and MockMvc tests.
7. Avoid open redirects, URI injection, generating internal URLs instead of public HTTPS, choosing the wrong mapping, or passing unencoded data.

**Scope:** Spring MVC running on the Servlet stack. WebFlux has its own URI utilities and a different request context. This lesson uses the `MvcUriComponentsBuilder` API in Spring Framework 6.2; details may change in Framework 7 and Spring Boot 4.

## 2. Why shouldn't you concatenate paths manually?

Suppose a controller:

~~~java
@Controller
@RequestMapping("/catalog/books")
public class BookController {
    @GetMapping("/{id}")
    public ModelAndView detail(@PathVariable("id") long id) {
        return new ModelAndView("book-detail").addObject("id", id);
    }
}
~~~

This is an illustrative snippet. Writing a link such as:

~~~java
String url = "/books/" + id;
~~~

is already wrong because the class has the `/catalog` prefix. Fixing it to `"/catalog/books/" + id` also creates **two places declaring the same route**; after a refactor, links can easily be missed.

Another issue is the **context path**: if the application is deployed under `/learning`, an absolute link might be `https://example.com/learning/catalog/books/7`, not `/catalog/books/7`. In a proxied environment, the internal application may see host `localhost:8080` while the external origin is `https://learning.example.com`.

And there is **encoding**: if a path variable is a string containing spaces, `/`, `?`, `#`, or a query contains `&`, improper URL concatenation can easily alter path/query structure. Building URIs from templates and encoding components in the right context is safer and easier to maintain.

## 3. Big picture: controller mapping → URI template → complete URI

~~~text
@Controller / @RestController
  |
  +-- @RequestMapping("/catalog/books")
        |
        +-- @GetMapping("/{id}")
        |       @PathVariable("id")
        |
        +-- @GetMapping("/search")
                @RequestParam("q"), @RequestParam("page")

MvcUriComponentsBuilder
  |
  +-- reads mapping metadata from class/method
  +-- combines base URL (scheme, host, port, context path)
  +-- contributes path variables and query parameters
  +-- returns UriComponentsBuilder
        |
        +-- build / buildAndExpand
        +-- context-appropriate encode
        +-- toUri() or toUriString()
                |
                v
   https://example.com/catalog/books/7
~~~

`MvcUriComponentsBuilder` **does not send HTTP requests**, does not run business logic to look up resources, and does not guarantee the target exists. It only constructs URIs from controller mapping metadata in the current application or referenced class.

Thus there are two very different concepts:

- **Handler mapping**: the definition Spring MVC uses to match requests to a controller. For example `@GetMapping("/{id}")`.
- **Link generation**: constructing a URI expected to match that mapping. Even when using the same annotation, the link still needs the right base URL, all missing URI variables filled in, and client authorization to access it.

Never invoke `controller.detail(7)` directly just to obtain a URI: that would execute logic, build a model, and possibly query the DB. With the builder, you only need the method's metadata and the **argument values** relevant to the URL.

## 4. Core API of `MvcUriComponentsBuilder`

The class lives in:

~~~java
import org.springframework.web.servlet.mvc.method.annotation.MvcUriComponentsBuilder;
~~~

Ways to build links:

| Call | Metadata source | Advantages | Caveats |
| --- | --- | --- | --- |
| `fromController(BookController.class)` | Class-level mapping | Easy to get a controller's base URL | Does not know specific method/variables |
| `fromMethodName(BookController.class, "detail", 7L)` | Class + method name + arguments | No proxy created; works with `String` return type | String method name; identical overloads can be ambiguous |
| `fromMethodCall(on(BookController.class).detail(7L))` | Method invocation recorded by proxy | Similar to a compile-time type-checked method reference | Return type/class/method must support proxying |
| `fromMethod(BookController.class, method, args)` | Java Reflection `Method` | Explicit method when reflection is already available | Verbose; requires exact `Method` |
| `fromMappingName("BC#detail")` | Mapping name registered in MVC | Useful when mapping identifiers are explicit | Name depends on convention/naming strategy; mapping must exist |
| `relativeTo(base).withMethodName(...)` | Explicitly supplied base URL + controller metadata | Works outside requests, multi-tenant/locale bases | Base must be controlled to avoid malicious links |

The `fromXxx` methods do not return `String` immediately in most cases: most return **`UriComponentsBuilder`** so you can continue with `build()`, `buildAndExpand(...)`, `encode()`, `toUri()`.

### Role of `UriComponentsBuilder` and `UriComponents`

~~~java
UriComponentsBuilder builder = MvcUriComponentsBuilder
        .fromMethodName(BookController.class, "detail", 7L);

UriComponents components = builder.build();
URI uri = components.encode().toUri();
~~~

This is an **illustrative snippet**, requiring a `BookController` class with the `detail` handler above and imports for `UriComponentsBuilder`, `UriComponents`, and `URI`. The path derives from the `/catalog/books/{id}` mapping, with `id=7` supplied from the method argument.

Distinguish two stages:

1. `UriComponentsBuilder` is the object **currently assembling URI components**.
2. `UriComponents` is the built structure, which may still contain unexpanded URI variables.
3. `buildAndExpand(...)` or `expand(...)` fills in remaining variables.
4. `encode()` ensures characters needing encoding are converted to percent-encoding according to the API's rules.
5. `toUri()` returns `java.net.URI`, suitable for `Location`, JSON links, or APIs accepting `URI`.

For many links with simple numeric IDs, `build().encode().toUri()` suffices. When variable values contain reserved characters, carefully read the **URI encoding** section below; encoding a URI after all data is expanded **differs** from encoding the URI template before expansion.

## 5. `fromController`: getting a URI to a class-level mapping

Suppose:

~~~java
@Controller
@RequestMapping("/catalog/books")
class BookController {
    // ...
}
~~~

From a current HTTP request:

~~~java
URI base = MvcUriComponentsBuilder
        .fromController(BookController.class)
        .build()
        .toUri();
~~~

If the public request is `https://shop.example.com/` and the app has no context path, `base` typically corresponds to:

~~~text
https://shop.example.com/catalog/books
~~~

**This is a class-level mapping, not a book detail URL.** If the class declares multiple route alternatives, the Javadoc notes that `fromController` only picks the **first mapping**. It cannot automatically decide a business ID/method when a class hosts multiple endpoints.

For example, given class mapping `/stores/{storeId}/books`, the class-level URI will still contain `{storeId}`; you must expand it:

~~~java
URI uri = MvcUriComponentsBuilder
        .fromController(StoreBookController.class)
        .buildAndExpand(42L)
        .encode()
        .toUri();
~~~

This snippet is **illustrative** with an undefined `StoreBookController` class in the demo. The number `42` is an example for the class-level `storeId` variable. Do not call `toUri()` with unfilled template variables unless the API genuinely needs a URI template rather than a concrete URI.

## 6. `fromMethodName`: building links by method and arguments

Spring MVC controller example:

~~~java
@Controller
@RequestMapping("/catalog/books")
public class BookController {

    @GetMapping("/{id}")
    public ModelAndView detail(@PathVariable("id") long id) {
        return new ModelAndView("book-detail")
                .addObject("id", id);
    }

    @GetMapping("/search")
    public ModelAndView search(
            @RequestParam("q") String q,
            @RequestParam(name = "page", defaultValue = "0") int page) {
        return new ModelAndView("book-search")
                .addObject("q", q)
                .addObject("page", page);
    }
}
~~~

Link to book 7:

~~~java
URI detail = MvcUriComponentsBuilder
        .fromMethodName(BookController.class, "detail", 7L)
        .build()
        .encode()
        .toUri();
~~~

Link to search results:

~~~java
URI search = MvcUriComponentsBuilder
        .fromMethodName(BookController.class, "search", "spring", 0)
        .build()
        .encode()
        .toUri();
~~~

With base URL `http://localhost:8080` and an empty context path, the two expected results are:

~~~text
http://localhost:8080/catalog/books/7
http://localhost:8080/catalog/books/search?q=spring&page=0
~~~

**These are illustrative results when the server receives a request with the corresponding scheme/host/port**, not stdout from a `main` program; query parameter ordering follows Spring's actual contribution/order. Do not hardcode domains in unit tests when you do not control the request host.

### Parameter names and `@RequestParam`

Method parameters annotated with `@PathVariable` and `@RequestParam` primarily determine the URI parts `MvcUriComponentsBuilder` can contribute. Parameters like `Model`, `HttpServletRequest`, `Principal`, `BindingResult`, and internal services **do not automatically turn into query strings** just because the method accepts them.

**Using explicit annotation names** is a good habit:

~~~java
@GetMapping("/{id}")
public ModelAndView detail(@PathVariable("id") long id) { /* ... */ }
~~~

This reduces reliance on Java parameter metadata (`-parameters`) when Spring resolves variable names, especially in custom builds.

### Limitations of String method names

`fromMethodName(BookController.class, "detail", 7L)` uses the **Java method** name, not the URL segment or `@GetMapping` name. If you rename the method, the String will not be caught by the Java compiler; it is usually discovered only at runtime/test time. If the class has multiple overloads named `detail`, the Javadoc notes it may throw `IllegalArgumentException` because no unique matching method is found. In that case:
- Give methods distinct names for clarity;
- Use `fromMethod(Class, Method, args)` with exact reflection;
- Or use `fromMethodCall(on(...))` if the signature supports proxying.

## 7. `fromMethodCall(on(...))`: method-call style links via proxy

Spring supports syntax resembling an actual invocation:

~~~java
import static org.springframework.web.servlet.mvc.method.annotation
        .MvcUriComponentsBuilder.on;

URI uri = MvcUriComponentsBuilder
        .fromMethodCall(on(BookController.class).detail(7L))
        .build()
        .encode()
        .toUri();
~~~

Note: `on(BookController.class).detail(7L)` is a call on a **proxy that records the invocation** so the builder extracts method and argument metadata. It **does not execute** the `detail` method body, query the database, or render a template. Do not confuse it with `new BookController().detail(7L)`.

### 7.1. Benefits

- Method renames during refactoring are typically caught by the compiler at the call site.
- Parameter types are checked by the Java compiler: `detail(7L)` matches `long`.
- For methods with many parameters, code is often easier to associate with the controller method than a String name.

### 7.2. Very important technical limitation: `final` return types

The Spring Framework 6.2 Javadoc warns that methods used with `fromMethodCall` have a **proxy return type** constraint. A method returning **`String`** as a view name is usually **unsuitable**, because `String` is a `final` class and cannot be subclassed as a proxy under this mechanism.

Example of what not to do:

~~~java
@GetMapping("/page")
public String page() {
    return "page-template";
}

// Do not use proxy invocation in this example:
MvcUriComponentsBuilder.fromMethodCall(
        on(PageController.class).page());
~~~

The snippet above is an **unsuitable anti-pattern illustration**, not a runnable guide. Some code compiles yet fails at runtime when creating the proxy/invocation record. **This does not mean returning `String` is wrong in Spring MVC**: it is a valid return type for rendering views; only link generation via `fromMethodCall(on(...))` is restricted.

Solutions:

1. If you want to keep the controller returning `String`, use `fromMethodName(PageController.class, "page")` without changing controller behavior.
2. If it fits the handler design, return a **non-final** type such as `ModelAndView`, allowing the builder to proxy per Spring docs patterns.
3. For methods inconvenient to proxy, use `fromMethod` with an exact Reflection `Method`.

**Besides return types**, non-proxyable classes/methods (such as `final` classes/methods under certain proxy mechanisms) also impose limitations. Do not change a public API solely because you want “prettier” proxy-based link generation; choose the builder API compatible with the existing design.

### 7.3. Missing class-level `@PathVariable`

From the official example:

~~~java
@Controller
@RequestMapping("/hotels/{hotel}")
public class BookingController {

    @GetMapping("/bookings/{booking}")
    public ModelAndView getBooking(
            @PathVariable("booking") Long booking) {
        return new ModelAndView("booking");
    }
}
~~~

Here the **method parameter only provides `booking`**, not `hotel` declared at the class level. You must supply the remaining variable:

~~~java
URI uri = MvcUriComponentsBuilder
        .fromMethodCall(
                on(BookingController.class).getBooking(21L))
        .buildAndExpand(42L)  // hotel
        .encode()
        .toUri();
~~~

With host `https://example.com`, the expanded link is typically:

~~~text
https://example.com/hotels/42/bookings/21
~~~

This is a key point: **the builder does not guess missing variables** from the browser URL, services, or model. When the method lacks an argument for a class-level variable, you must still call `buildAndExpand` with the missing value.

## 8. `fromMethod` and `fromMappingName`: when to use them?

### 8.1. `fromMethod` using Reflection `Method`

If your library already holds a `java.lang.reflect.Method`, you can build a URI from that exact method:

~~~java
Method javaMethod = BookController.class
        .getMethod("detail", long.class);

URI uri = MvcUriComponentsBuilder
        .fromMethod(BookController.class, javaMethod, 7L)
        .build()
        .encode()
        .toUri();
~~~

This is an illustrative snippet inside a Java method `throws ReflectiveOperationException`, requiring imports `java.lang.reflect.Method` and `java.net.URI`. `getMethod` finds only public methods matching the chosen signature, distinguishing overloads if you pass the exact parameter types.

**Do not cache an old controller `Method` across different deployment versions** without control. Reflection metadata still depends on Java bytecode/actual controller mappings. Likewise, never take a Java method name directly from a query parameter and reflect arbitrarily: choose methods by server contract.

### 8.2. `fromMappingName` based on mapping name

Spring MVC can register mapping names via default configuration or via the `name` attribute of `@RequestMapping`/`@GetMapping`. Annotation example:

~~~java
@Controller
@RequestMapping("/catalog/books")
public class BookController {

    @GetMapping(path = "/{id}", name = "details")
    public ModelAndView detail(@PathVariable("id") long id) {
        return new ModelAndView("book-detail");
    }
}
~~~

Under the default naming strategy, the mapping name can combine the **uppercase initials of the controller name** and the **explicit method mapping name**, such as `BC#details` (for `BookController` → `BC`). This is useful when identifying handlers by a registered name, though the exact name should be checked in `HandlerMapping` at runtime. With multiple similarly named classes, custom naming strategies, or duplicate mappings, ambiguity can arise.

A conceptual builder example (depending on an existing mapping name):

~~~java
MvcUriComponentsBuilder.MethodArgumentBuilder builder =
        MvcUriComponentsBuilder.fromMappingName("BC#details");

// Use builder.arg(index, value) to bind method arguments
// by index before building the URI.
~~~

`fromMappingName` **does not look up paths from a database**; it looks up mappings registered with `RequestMappingHandlerMapping`. If the mapping is not found or the name is not unique, an exception can be thrown. In typical applications, `fromMethodName` or `fromMethodCall` is easier to verify.

## 9. Base URLs and how to use `relativeTo`

During a normal Servlet request, the static `fromXxx` methods of `MvcUriComponentsBuilder` typically read scheme, host, port, context path, and servlet path from the **current request** via Servlet URI utilities.

However, there are times when no request is active:
- Background jobs generating confirmation emails.
- Batch document generation.
- Services building callback URLs outside a request.
- Links needing a locale prefix stripped by middleware earlier in the request.
- Applications needing a managed canonical public origin instead of relying on raw `Host` headers.

In those cases, use a **configured and trusted** base URL:

~~~java
UriComponentsBuilder publicBase =
        UriComponentsBuilder.fromUriString(
                "https://docs.example.com/app");

URI uri = MvcUriComponentsBuilder
        .relativeTo(publicBase)
        .withMethodName(BookController.class, "detail", 7L)
        .build()
        .encode()
        .toUri();
~~~

Assuming `BookController` has class mapping `/catalog/books` and method mapping `/{id}`, the result is:

~~~text
https://docs.example.com/app/catalog/books/7
~~~

This is an illustrative snippet inside a method, requiring imports `UriComponentsBuilder` and `URI`. Instance-based `withController`, `withMethodName`, `withMethodCall`, and `withMethod` reuse your chosen base URL. Equivalently, static overloads `fromMethodName(base, ...)` or `fromController(base, ...)` accept the base builder directly.

**Note:** the `/app` base path here is a public URL prefix that you **intentionally** add. If it is already present in the context path, adding it again can yield `/app/app/...`. In setups with multiple reverse proxies or path rewrites, clearly design “who owns the prefix” before building URLs.

### Creating a base from the current context path

When basing on the request while adding a locale segment:

~~~java
UriComponentsBuilder base =
        ServletUriComponentsBuilder.fromCurrentContextPath()
                .path("/vi");

URI uri = MvcUriComponentsBuilder.relativeTo(base)
        .withMethodName(BookController.class, "detail", 7L)
        .build()
        .encode()
        .toUri();
~~~

This is an illustrative snippet inside a **request thread with `ServletRequestAttributes`**; do not use it as-is in a background job without a request. It can generate a path like `/vi/catalog/books/7` based on the current context. Ensure the `/vi` locale prefix is actually accepted by the router/gateway; do not prepend a “plausible-looking” path that does not exist.

## 10. Encoding: path variables and query parameters are not String concatenation

Spring URI builders support URI templates with two very notable encoding approaches:

- **`UriComponentsBuilder#encode()` before expanding variables**: encodes the template and **strictly encodes variable values**, including reserved characters that could alter structure.
- **`UriComponents#encode()` after expanding variables**: encodes per URI component, which may **preserve valid reserved characters** within a component (for example, semicolons in a path).

For user input, you usually want variables treated as **opaque data** rather than URI syntax. Pure `UriComponentsBuilder` example:

~~~java
URI uri = UriComponentsBuilder
        .fromPath("/catalog/books/{id}")
        .queryParam("q", "{q}")
        .encode() // IMPORTANT: encode template before expanding
        .buildAndExpand("a/b", "Java & Spring")
        .toUri();
~~~

Result:

~~~text
/catalog/books/a%2Fb?q=Java%20%26%20Spring
~~~

Here:
- `/` inside `id` is encoded as `%2F`, because it **is variable data**, not a boundary between two path segments.
- `&` inside `q` is encoded as `%26`, preventing it from becoming a query parameter delimiter.
- Space becomes `%20`.

`MvcUriComponentsBuilder` helps bind controller method arguments into URLs. However, if you need to **ensure reserved characters inside variables are strictly encoded**, check how the API contributes/expands arguments before calling `encode()` and write specific URI tests. Do not assume `build().encode()` after any argument substitution will encode every reserved character. With resources identified by numbers or validated slugs, the issue is simpler; with free-form input containing `/`, `&`, `?`, `#`, choose an appropriate URI template/encoding pipeline.

**Avoid double encoding:** if input already contains `%2F`, encoding again can produce `%252F`. Define a contract: pass **raw logical values** into the URI builder and encode exactly once at URI creation time.

### Links in HTML templates

With Thymeleaf in Spring MVC, link template expressions are sometimes simpler:

~~~html
<a th:href="@{/catalog/books/{id}(id=${bookId})}">
  View book
</a>

<a th:href="@{/catalog/books/search(q=${query},page=0)}">
  Search
</a>
~~~

Thymeleaf processes URI templates and the context path via its template engine integration. `MvcUriComponentsBuilder` fits when you want links driven by **Java controller mappings**; Thymeleaf link expressions fit static HTML templates with clear routes. Both still require valid inputs and authorization checks on the target endpoint.

### Do not concatenate raw queries

Example to avoid:

~~~java
String unsafe = "/search?q=" + userInput;
~~~

If `userInput` contains `&admin=true`, it can turn into a new query parameter instead of remaining a value for `q`. Use URI templates + component encoding (and server-side validation) instead of String concatenation.

## 11. Route names, URI context, and API versioning

In the “URI and API Versioning” module, link generation is especially valuable when endpoints carry a prefix:

~~~java
@RestController
@RequestMapping("/api/v1/books")
public class BookApiV1Controller {
    @GetMapping("/{id}")
    public BookDto detail(@PathVariable long id) { /* ... */ }
}
~~~

This is illustrative code, not a standalone compilable file; `BookDto` needs to be defined. Use `fromMethodName` to build links from the `/api/v1/books/{id}` mapping. When moving the path to `/api/v2/books/{id}`, new links follow the code metadata, yet **this does not automatically migrate clients holding old URLs**.

Design rules:
- **The URI version is part of the API contract**. The builder only reflects the current mapping; maintain backward compatibility or a redirect/deprecation policy for v1 while clients still use it.
- If a controller has `@RequestMapping(path={"/v1/books","/v2/books"})`, the builder can encounter **multiple mapping alternatives**; it does not know which version a client should pick. Avoid ambiguous patterns for public links or make the version explicit in the base/path.
- Mappings using **HTTP headers** or **media type versioning** can share the same path across multiple handlers. Building a URI does not automatically add `Accept`, `Content-Type`, or authorization headers.
- A link to `GET` does not describe a `POST` payload. If you want HATEOAS with HTTP methods/media types, use an appropriate format/link relation; `MvcUriComponentsBuilder` only builds URIs.
- Link generation does not replace server routing tests; routes may require regexes/converters/validators that data produced by the builder might not satisfy.

## 12. Runnable Spring Boot 3.x example

The demo application builds links from controller mappings displaying books, returns the URLs in JSON for easy inspection, and includes two simple Thymeleaf templates.

### 12.1. Creating the project

Select **Java 17+**, **Spring Boot 3.x**, **Maven**, dependencies:

- `spring-boot-starter-web` — Spring MVC, Jackson, and embedded Servlet container.
- `spring-boot-starter-thymeleaf` — renders the two HTML views.
- `spring-boot-starter-test` — JUnit 5 and MockMvc.

The main package is `com.example.demo`.

Structure:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/BookController.java
src/main/java/com/example/demo/BookLinkController.java
src/main/resources/templates/book-detail.html
src/main/resources/templates/book-search.html
src/test/java/com/example/demo/BookLinksTest.java
~~~

**The Java files below are Java 17 code you can drop directly into a Spring Boot 3.x project with the right dependencies.** The `http://localhost:8080` URLs apply only when running the server on the default port with no custom context path.

### 12.2. `DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 12.3. `BookController.java`: mapping as the source for URI generation

~~~java
package com.example.demo;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.servlet.ModelAndView;

@Controller
@RequestMapping("/catalog/books")
public class BookController {

    @GetMapping("/{id}")
    public ModelAndView detail(@PathVariable("id") long id) {
        return new ModelAndView("book-detail")
                .addObject("id", id);
    }

    @GetMapping("/search")
    public ModelAndView search(
            @RequestParam("q") String q,
            @RequestParam(name = "page", defaultValue = "0")
            int page) {

        return new ModelAndView("book-search")
                .addObject("q", q)
                .addObject("page", page);
    }
}
~~~

Both `detail` and `search` handlers return **`ModelAndView`** instead of `String` to illustrate compatibility with `fromMethodCall(on(...))`'s proxy mechanism. In an ordinary HTML application, you can still return a `String` view name and choose `fromMethodName` to build links.

Running endpoints:
- `GET /catalog/books/7` — renders `book-detail.html`.
- `GET /catalog/books/search?q=spring&page=0` — renders `book-search.html`.

### 12.4. `BookLinkController.java`: building links with both APIs

~~~java
package com.example.demo;

import java.net.URI;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation
        .MvcUriComponentsBuilder;

import static org.springframework.web.servlet.mvc.method.annotation
        .MvcUriComponentsBuilder.on;

@RestController
@RequestMapping("/api/links")
public class BookLinkController {

    @GetMapping("/books/{id}")
    public Links links(@PathVariable("id") long id) {

        URI byMethodName = MvcUriComponentsBuilder
                .fromMethodName(BookController.class, "detail", id)
                .build()
                .encode()
                .toUri();

        URI byMethodCall = MvcUriComponentsBuilder
                .fromMethodCall(
                        on(BookController.class).detail(id))
                .build()
                .encode()
                .toUri();

        URI search = MvcUriComponentsBuilder
                .fromMethodName(BookController.class, "search",
                        "spring", 0)
                .build()
                .encode()
                .toUri();

        return new Links(
                byMethodName.toString(),
                byMethodCall.toString(),
                search.toString());
    }

    public record Links(String byMethodName,
                        String byMethodCall,
                        String search) {}
}
~~~

**Detailed explanation:**

1. The controller handles `GET /api/links/books/7`; it **does not hardcode** the path `/catalog/books/{id}` anywhere in `BookLinkController`.
2. `fromMethodName(...)` reads the mapping of `BookController.detail`, contributing `id=7`.
3. `fromMethodCall(on(...).detail(id))` uses a proxy to **record the method + argument** without running the `detail` handler; the output path matches the previous approach.
4. `BookController.detail` returns `ModelAndView`, which is non-final, avoiding the `String` final limitation in builder proxies.
5. The search link uses `@GetMapping("/search")` and `@RequestParam("q")`, `@RequestParam("page")` instead of manually appending `?q=`.
6. By default, static builders can take the **base URL from the current Servlet request**. If the application sits behind a proxy without proper forwarded-headers handling, the response can use an internal host/port.
7. `Links` is a Java record for JSON; Jackson serializes the fields `byMethodName`, `byMethodCall`, and `search`.

### 12.5. `book-detail.html` and `book-search.html`

**`src/main/resources/templates/book-detail.html`**

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Book Details</title>
</head>
<body>
  <h1>Book Details</h1>
  <p>ID: <span th:text="${id}">0</span></p>
  <a th:href="@{/catalog/books/search(q='spring',page=0)}">
    Search books
  </a>
</body>
</html>
~~~

**`src/main/resources/templates/book-search.html`**

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Book Search</title>
</head>
<body>
  <h1>Search</h1>
  <p>Query: <span th:text="${q}">query</span></p>
  <p>Page: <span th:text="${page}">0</span></p>
</body>
</html>
~~~

Both templates use `th:text` to escape displayed data. A URI link builder is **not** responsible for HTML-escaping data everywhere; when placing URLs into HTML attributes, the template engine still needs safe attributes like `th:href` (or context-appropriate HTML attribute escaping).

### 12.6. Calling the endpoint with curl

Run:

~~~bash
./mvnw spring-boot:run
~~~

On Windows use `mvnw.cmd spring-boot:run`; if Maven Wrapper is absent and Maven is installed, use `mvn spring-boot:run`.

Call:

~~~bash
curl -i http://localhost:8080/api/links/books/7
~~~

Expected JSON result with default configuration and request host `localhost:8080`:

~~~json
{
  "byMethodName": "http://localhost:8080/catalog/books/7",
  "byMethodCall": "http://localhost:8080/catalog/books/7",
  "search": "http://localhost:8080/catalog/books/search?q=spring&page=0"
}
~~~

The values in this example show the **expected data shape**, not empirical output executed in the workspace. Port, context path, proxy, and `server.forward-headers-strategy` settings can change absolute URLs.

Open the links in a browser:

~~~text
http://localhost:8080/catalog/books/7
http://localhost:8080/catalog/books/search?q=spring&page=0
~~~

If the controller changes `@RequestMapping("/catalog/books")` to `@RequestMapping("/library/books")`, the links generated by the builder update automatically from the mapping metadata (provided application code and tests reflect the new controller).

## 13. MockMvc: verifying actual links and matching mappings

Tests should verify:
- Links built by method name and by proxy call match.
- Paths are generated from `@RequestMapping`, not a hand-written string.
- Query parameters have the expected names.
- A returned link can be used to call the corresponding endpoint.
- After changing a mapping, tests are updated to match the **intended API contract**, rather than merely checking that two builders produce the same wrong output.

**`src/test/java/com/example/demo/BookLinksTest.java`**

~~~java
package com.example.demo;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class BookLinksTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void generatesLinksFromControllerMetadata() throws Exception {
        mockMvc.perform(get("/api/links/books/7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.byMethodName")
                        .value("http://localhost/catalog/books/7"))
                .andExpect(jsonPath("$.byMethodCall")
                        .value("http://localhost/catalog/books/7"))
                .andExpect(jsonPath("$.search")
                        .value("http://localhost/catalog/books/search?q=spring&page=0"));
    }

    @Test
    void generatedDestinationHasWorkingControllerMapping()
            throws Exception {

        mockMvc.perform(get("/catalog/books/7"))
                .andExpect(status().isOk())
                .andExpect(view().name("book-detail"))
                .andExpect(model().attribute("id", 7L));
    }

    @Test
    void searchMappingBindsNamedQueryParameters() throws Exception {
        mockMvc.perform(get("/catalog/books/search")
                        .param("q", "spring")
                        .param("page", "0"))
                .andExpect(status().isOk())
                .andExpect(view().name("book-search"))
                .andExpect(model().attribute("q", "spring"))
                .andExpect(model().attribute("page", 0));
    }
}
~~~

**About the host in MockMvc:** MockMvc's `get("/...")` builder typically creates a mock request with scheme `http`, host `localhost`, and default port 80. Thus the test expects `http://localhost/...`. When running the real server on default port 8080, absolute links include `:8080`. If a project has custom mock request defaults, forwarded headers, or a context path, tests must state base/expected hosts according to that configuration.

The tests above mainly verify link generation and MVC mappings without opening a real TCP connection. For production, add **HTTP integration tests through the reverse proxy** to ensure public scheme/host/context path do not leak internal domains.

Run:

~~~bash
./mvnw test
~~~

If Spring Security is enabled in a real project, MockMvc tests for HTML/API routes may require authentication per policy; these examples omit Security to stay focused on the URI builder.

## 14. Absolute links behind a reverse proxy: Forwarded and X-Forwarded-*

With a TLS-terminating load balancer:

~~~text
Client: https://api.example.com
           |
           v
Reverse proxy: HTTPS -> HTTP
           |
           v
Spring Boot: http://127.0.0.1:8080
~~~

If the builder only inspects the server-side request rewritten by the proxy, it can produce the wrong URI `http://127.0.0.1:8080/catalog/books/7`, whereas the client needs `https://api.example.com/catalog/books/7`.

The proxy may send:
- `Forwarded: proto=https;host=api.example.com` per RFC 7239.
- Or `X-Forwarded-Proto: https`, `X-Forwarded-Host: api.example.com`, `X-Forwarded-Port: 443`, `X-Forwarded-Prefix: /app`.

Spring documentation notes that `MvcUriComponentsBuilder`/`ServletUriComponentsBuilder` do not automatically trust or fully read forwarded headers directly. Configure handling **before** URI building, such as `ForwardedHeaderFilter` or container trusted-proxy support.

In Spring Boot 3.x, one way to enable framework-level forwarded-header handling is:

~~~properties
server.forward-headers-strategy=framework
~~~

**Critically important for security:** enable this only when there is a **trusted reverse proxy** at the trust boundary that:
1. Strips all client-supplied `Forwarded` and `X-Forwarded-*` headers arriving from the Internet.
2. Attaches **fresh**, accurate headers reflecting the public scheme/host/port/prefix.
3. Prevents direct arbitrary traffic from reaching the app by bypassing the reverse proxy if the app trusts these headers.

If any client can inject `X-Forwarded-Host: evil.example` and the server trusts it, absolute links returned in emails or `Location` can suffer from **host header poisoning**. For email/password-reset links, it is safer to use a server-configured, allowlisted **public base URL** rather than an unverified Host header.

If not using forwarded headers to generate URLs, you can explicitly supply a base URI in `relativeTo` sourced from trusted configuration. Do not enable both `ForwardedHeaderFilter` and native proxy handling twice arbitrarily; that can produce wrong context paths/schemes or duplicate prefixes.

## 15. `Location`, redirects, and links in JSON

A resource-creating POST API often needs a **`Location`** header pointing to the newly created resource's GET endpoint. Illustrative example:

~~~java
@PostMapping("/books")
public ResponseEntity<Void> create(@RequestBody CreateBookRequest request) {
    Book saved = bookService.create(request);
    URI location = MvcUriComponentsBuilder
            .fromMethodName(BookController.class, "detail", saved.id())
            .build()
            .encode()
            .toUri();

    return ResponseEntity.created(location).build();
}
~~~

This is an **illustrative handler**, not part of the runnable project in section 12. It requires undefined service/DTO types, imports for `ResponseEntity`, `URI`, MVC annotations, and a corresponding get-detail handler. `ResponseEntity.created(location)` typically returns **201 Created** with a `Location` header. The controller still must validate input, authorize the request, and manage transactions when creating the book.

**Do not** confuse `Location` with `Content-Location`; their HTTP semantics differ. The builder only constructs the URI; it does not confirm the resource has been committed to the database.

### Relative URI or absolute URI?

A link such as `/catalog/books/7` is **path-relative-to-origin**, whereas `https://api.example.com/catalog/books/7` is an absolute URI with scheme/authority. Both have distinct use cases:
- For internal HTML on the same host, root-relative paths help avoid leaking internal hosts.
- For JSON/HATEOAS, notifications/emails, and `Location`, absolute URIs are convenient for out-of-origin clients, provided a trusted public base is used.
- If the application runs under a context path, root-relative URIs must include the right prefix.
- If the API serves multiple domains/tenants, pick the public origin from validated tenant configuration rather than accepting an arbitrary Host header.

Use `UriComponentsBuilder.fromPath("/...")` when intentionally building a request-independent relative path; use `MvcUriComponentsBuilder` when the primary goal is linking via **controller metadata**.

## 16. Safety when building links

`MvcUriComponentsBuilder` is not a universal encoder/sanitizer and does not grant access rights. Principles:

### 16.1. Do not let clients control the entire base URL

~~~java
// ANTI-PATTERN: do not use an untrusted URL as base
UriComponentsBuilder base =
        UriComponentsBuilder.fromUriString(userSuppliedBaseUrl);
~~~

If a user controls the base scheme/host, returned links can point to malicious sites. If the server uses that URL to make outbound calls, there is also **SSRF** risk. Use a host/scheme allowlist or an operator-configured public origin.

### 16.2. Do not use a link builder in place of authorization

Generating `/admin/reports/7` does not prove the recipient has permission to read the report. Authorization must live on the GET endpoint, independent of whether the link appears in UI/JSON. When returning links to private resources, consider visibility per permissions and avoid exposing unnecessary IDs/metadata.

### 16.3. Do not treat raw query data as URI syntax

Query text containing `&`, `=`, `#`, spaces, and Unicode must be encoded properly. Avoid manual concatenation and double-encoding. With typed Path IDs like UUID/long, type validation reduces reserved-character risk; yet never treat type validation as a permission check.

### 16.4. Handling redirects safely

A URI built from an **allowed internal mapping** is much easier to control than redirecting to an arbitrary client-supplied URL. When `Location` needs an absolute base, verify scheme/host first. Avoid redirects like `return "redirect:" + userInput;` because they easily become **open redirects**.

### 16.5. Do not infer the request method from the URI

The URI `/api/books/7` does not tell you whether to use GET or DELETE. `MvcUriComponentsBuilder` reads mappings to build path/query, yet if a response needs to describe HTTP methods, media types, request bodies, or link relations, supply appropriate separate metadata (HAL/JSON:API/REST documentation...). This is especially important with header-based API versioning.

## 17. Common errors and debugging workflow

| Symptom | Common cause | How to verify / fix |
| --- | --- | --- |
| Link misses `/catalog` | Manual concatenation forgot class-level mapping | Use `fromMethodName` or controller-based builder |
| Link host is `localhost:8080` instead of public HTTPS | Proxy termination, forwarded headers unhandled | Trusted proxy config / `server.forward-headers-strategy` / `relativeTo` |
| Link repeats `/app/app` | Both context path and custom base added prefix | Pick a single owner for the base path |
| `fromMethodCall` fails with `String` | String is final, proxy cannot be created | Switch to `fromMethodName` or a suitable return type |
| `fromMethodName` cannot find method | Wrong Java method name, ambiguous overload | Check method signature, use `fromMethod` |
| URI still contains `{id}` | Variable not contributed/expanded | `buildAndExpand` with missing variables |
| Query splits into multiple params | Concatenated unencoded input containing `&` | URI templates and context-appropriate encoding |
| Link has wrong port behind proxy | Untrusted or wrong `X-Forwarded-Port`/Host/Proto | Inspect request wrapper and proxy headers |
| Generated URL causes open redirect | Raw base URL taken from client | Whitelist public origins and strip spoofed headers |
| Link hits 404 even though builder succeeded | Route depends on params/media type/auth or mapping changed | Test actual endpoint and version contract |
| `fromController` picks unexpected path | Controller has multiple class-level mappings | Choose explicit method/mapping |
| Cannot build link in background job | No request-bound base URL available | `relativeTo` from trusted config |
| Unicode/spaces are double-encoded | Input data was already encoded | Pass raw values, encode exactly once |
| Link points to wrong version | Mapping alternatives/header versioning | Define explicit version contract and test |
| `@RequestParam` missing or wrong name | Implicit parameter/annotation naming | Specify `@RequestParam("q")` and test query |
| Link in HTML causes XSS | Inserted unescaped URI/user data in attribute | Use Thymeleaf `th:href`, escaping, and URL validation |

### Debugging workflow

1. Inspect the **controller class-level `@RequestMapping`** and **method-level `@GetMapping`/`@PostMapping`**; identify the template and all URI variables.
2. Note which builder API was used: `fromController`, `fromMethodName`, `fromMethodCall`, or `relativeTo`.
3. Check arguments annotated with `@PathVariable`, `@RequestParam`; supply class-level path variables via `buildAndExpand`.
4. Print/debug the full actual URI including scheme, host, port, contextPath, and percent encoding — not just a path substring.
5. Check forwarded headers at the gateway and after filters if the app runs behind a proxy; strip spoofed client headers.
6. Try GETting the exact URL in a test environment; if 404/405/401 occurs, inspect routing/auth rather than only the builder.
7. Write MockMvc tests asserting both the link and destination mapping; add integration tests through the reverse proxy with real domain/HTTPS.
8. Review versioning, tenant prefixes, query encoding, and authority security when URLs are used in emails/`Location`.

## 18. Review questions

**1. Why use `MvcUriComponentsBuilder` instead of concatenating `"/books/" + id`?**

Because the builder uses class/method `@RequestMapping` metadata and route parameters, reducing duplicate hardcoded paths during refactoring while combining a request-derived or custom base URL.

**2. How do `fromMethodName` and `fromMethodCall` differ?**

`fromMethodName` references the Java method name as a string without needing a return-type proxy. `fromMethodCall` uses a proxy that records the invocation, giving compile-time signature checking, but is constrained by which method/return types can be proxied.

**3. Why can a `String` return type fail with `on(...)`?**

`String` is `final`; the builder proxy cannot create a subclass of it under the limitation documented by Spring. `String` remains completely valid for rendering views; in that case use `fromMethodName`.

**4. If a class route has `/hotels/{hotel}` while the method only has `@PathVariable booking`, what must you do?**

`fromMethodName`/`fromMethodCall` take `booking` from the argument; use `buildAndExpand(hotelId)` to fill in the remaining class-level variable.

**5. When generating a link in a background job, can you use the current request's base URL?**

No, because a request context usually does not exist. Use `relativeTo` or an overload accepting a base `UriComponentsBuilder` from a trusted public URL.

**6. Why does a link in production become `http://localhost:8080` instead of `https://example.com`?**

The app sits behind an HTTPS proxy, yet public scheme/host metadata has not reached the request seen by the builder. Handle forwarded headers at the trust boundary or configure a fixed public base.

**7. If a query input is `Java & Spring`, is concatenating `?q=` safe?**

No. `&` acts as a query parameter delimiter. Use URI templates and proper component/variable encoding before building the URI.

**8. Does a successfully built admin link mean the user is allowed to open it?**

No. Link generation does not replace authentication/authorization at the target endpoint.

## 19. Practical checklist

1. Treat `MvcUriComponentsBuilder` as a tool for **building URIs from controller mappings**, not a REST client, route validator, or authorization layer.
2. For methods returning `String` or hard-to-proxy types, prefer `fromMethodName`; for proxy-compatible types, `fromMethodCall(on(...))` can be used.
3. Name `@PathVariable` and `@RequestParam` explicitly, and fill all remaining variables with `buildAndExpand`.
4. When needing a class URL, use `fromController`, keeping in mind multiple class mappings can be ambiguous.
5. When no request exists or a trusted public origin is required, use `relativeTo` or a base URL overload — never trust user-supplied bases.
6. Control path/query encoding by context, preferring template `encode()` before expansion for variable data containing reserved characters.
7. Do not hardcode version URLs in multiple places; preserve v1/v2 API contracts and test generated links after refactoring.
8. Behind a reverse proxy, handle forwarded headers safely and explicitly, avoiding Host poisoning/duplicate context paths.
9. When rendering links in HTML, use `th:href` and escaping; for `Location`, verify absolute URIs and permissions on the new resource.
10. Test both generated links and destination handlers; verify paths, queries, ports, context paths, proxies, and special characters.

## Official documentation

- [Spring Framework 6.2 — URI Links and Links to Controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-uri-building.html)
- [Spring Framework 6.2 — MvcUriComponentsBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/MvcUriComponentsBuilder.html)
- [Spring Framework 6.2 — MethodArgumentBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/MvcUriComponentsBuilder.MethodArgumentBuilder.html)
- [Spring Framework 6.2 — UriComponentsBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html)
- [Spring Framework 6.2 — Servlet MVC Controller Mappings](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework 6.2 — ForwardedHeaderFilter and security considerations](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html)
- [Spring Boot 3.5 — Common Application Properties (`server.forward-headers-strategy`)](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [RFC 3986 — Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986)
