# @ResponseBody and How It Differs from Returning a View Name from @Controller

## 1. Objective: One String, Two Completely Different Interpretations

Suppose a controller has two methods that both return `"hello"`. In Spring MVC (Servlet stack), the HTTP meaning differs depending on the return value handling mechanism:

~~~java
@Controller
class PageController {
    @GetMapping("/page")
    public String page() {
        return "hello";
    }
}
~~~

Here `"hello"` is a **view name**. Spring selects an appropriate `ViewResolver`, looks up the corresponding template/view, and **renders the result** into the HTTP response. If the view cannot be found, the request may fail depending on the view technology configuration. The return value is **not automatically sent verbatim** as the response body.

~~~java
@Controller
class TextController {
    @GetMapping("/text")
    @ResponseBody
    public String text() {
        return "hello";
    }
}
~~~

Here `"hello"` is the **response body content**, bypassing view lookup. `StringHttpMessageConverter` typically writes it as text according to the selected media type.

And when `@RestController` is placed on the class, `@ResponseBody` semantics apply by default to the handlers:

~~~java
@RestController
class ApiController {
    @GetMapping("/api/hello")
    public String hello() {
        return "hello";
    }
}
~~~

All three fragments only illustrate annotations and return value semantics; the **complete application example** section below includes full files, imports, and tests.

**Learning outcomes:**
1. Distinguish between `@Controller`, `@ResponseBody`, and `@RestController`.
2. Understand how Spring MVC decides when to use `ViewResolver` and when to use `HttpMessageConverter`.
3. Know how `String`, DTOs, `ResponseEntity`, `ModelAndView`, and `redirect:` are handled.
4. Write controllers and MockMvc tests that verify body, media type, model/view, and redirects.
5. Diagnose errors such as accidentally returning a view name, rendering raw text by mistake, wrong Content-Type, or HTTP 406.

Examples target Java 17+ and Spring Boot 3.x / Spring Framework 6.x; the core principles remain valid in modern Spring MVC. Do not use WebFlux examples to infer exact implementation names in the Servlet stack.

## 2. Two Response Handling Branches in Spring MVC

### 2.1. Same Start, Different End

When receiving an HTTP request, Spring MVC:
1. `DispatcherServlet` coordinates with `HandlerMapping` to determine the handler.
2. `HandlerAdapter` resolves parameters and invokes the controller method.
3. A `HandlerMethodReturnValueHandler` matching the **return value type and annotation metadata** processes the result.
4. If it is a model/view, Spring resolves and renders the view; if it is a body, a converter serializes/writes the data.

~~~text
HTTP GET /...
     │
     ▼
DispatcherServlet → HandlerMapping → Controller method
                                         │
                          return "hello" │
                                         ▼
                        HandlerMethodReturnValueHandler
                                  │                │
                     @Controller, String       @ResponseBody
                     (view name)               or @RestController
                                  │                │
                                  ▼                ▼
                            ViewResolver      HttpMessageConverter
                                  │                │
                                  ▼                ▼
                            View.render()     write HTTP response body
                                  │                │
                                  └────────┬───────┘
                                           ▼
                                     HTTP response
~~~

This is a simplified diagram to understand the two branches. At runtime, specific resolvers/handlers, filters, interceptors, exception handlers, and view technology affect the outcome; Spring **does not guess whether a "String looks like HTML" to pick a view**.

### 2.2. What Does `@Controller` Mean?

`@Controller` is a stereotype marking an MVC component discovered by component scanning; it **does not declare that every return value is JSON**.

Example:

~~~java
@Controller
class ShopPageController {
    @GetMapping("/products")
    public String products(Model model) {
        model.addAttribute("title", "Products");
        return "products";
    }
}
~~~

`"products"` is treated as a view name, and `Model` holds data passed into the rendering process. With Thymeleaf and standard configuration, the template may reside at `classpath:/templates/products.html`; with JSP or another view resolver, the path/filename may vary.

Not every method in a `@Controller` is forced to return a view: if it returns `ResponseEntity<?>`, is annotated with `@ResponseBody`, or writes directly to `HttpServletResponse`, Spring can handle the response directly.

### 2.3. What Does `@ResponseBody` Change?

`@ResponseBody` tells Spring to treat the **method's return value as data written to the response body**, via `HttpMessageConverter`. The annotation can be placed on:
- **A single method** inside a `@Controller`, allowing the controller to have both HTML pages and API endpoints.
- **A `@Controller` class**, affecting the corresponding handler methods.

This annotation **does not necessarily mean JSON**. The representation depends on the **Java type**, configured converters, `produces` conditions, the `Accept` header, and content negotiation. A `String` is typically `text/plain`, a DTO is typically JSON if a Jackson converter is available and content negotiation matches, and `byte[]` uses another converter.

`@ResponseBody` also does not create a response object by itself. `null`/`void` values have specific handling depending on the signature and may end up with an empty body; do not use `return null` to indicate a specific status code.

### 2.4. What Is `@RestController` Actually?

`@RestController` is a composed annotation carrying the semantics of **`@Controller` + `@ResponseBody` at the class level**. It fits when handlers are primarily REST APIs, because you do not have to repeat `@ResponseBody` on every method:

~~~java
@RestController
@RequestMapping("/api")
class ProductApi {
    @GetMapping("/health")
    public String health() {
        return "ok";
    }
}
~~~

The response body is `ok`; `"ok"` is not a template name. Therefore, **you should not put methods that return view names inside a `@RestController`** and expect Spring to automatically switch to HTML. If you want an HTML page, use a suitable `@Controller` or explicitly return HTML content with the appropriate media type (a different design approach).

## 3. Comparison Table of Common Return Types

| Controller and return value | How Spring MVC interprets it | What is sent to the client |
| --- | --- | --- |
| `@Controller` + `String "home"` | View name `home` | HTML or result rendered by the view |
| `@Controller` + `String "redirect:/login"` | Special view name to redirect | HTTP redirect, typically 302 |
| `@Controller` + `String "forward:/internal"` | Special view name to forward | Servlet forward per configuration |
| `@Controller` + `@ResponseBody String "home"` | Body content | String `home`, no template lookup |
| `@Controller` + `@ResponseBody ProductDto` | Body via converter | Usually JSON if Jackson is present |
| `@RestController` + `String "redirect:/login"` | Body string | Literal `redirect:/login`, not a redirect |
| `@RestController` + `ProductDto` | Body via converter | Usually JSON |
| `@Controller` + `ResponseEntity<ProductDto>` | Full HTTP response, no `@ResponseBody` needed | Status, headers, and converted body |
| `@Controller` + `ModelAndView` | View + model (and optional status) | Renders view |
| `@Controller` + `Model` or `Map` | Updates model, derives implicit view name if needed | Renders view after resolution |

This table applies to normal handler cases without considering custom return handlers. An often-overlooked point: `ResponseEntity<T>` is a **special return type**; even when the class only has `@Controller`, it can still write a response body without needing `@ResponseBody`.

### 3.1. Why Is `String` Special?

Spring MVC has a handler that interprets a `String`/`CharSequence` as a logical view name when `@ResponseBody` is absent and no other return handler claims it first. `@ResponseBody` routes it through the body-writing handler: `StringHttpMessageConverter` writes the characters. Thus, **the Java type `String` alone is not enough to infer HTTP behavior**.

Common mistake example:

~~~java
@Controller
class MistakeController {
    @GetMapping("/api/status")
    public String status() {
        return "READY";
    }
}
~~~

Even though the developer intends to return `READY` for an API, Spring will look for the **view `READY`**. If no matching template/view exists, the client may receive a server error or an application-specific fallback mechanism instead of the text `READY`. The fix is to add `@ResponseBody` or use `@RestController` if the entire class is an API.

### 3.2. `ResponseEntity` Controls More Than the Body

~~~java
@GetMapping("/api/orders/{id}")
public ResponseEntity<OrderDto> get(@PathVariable long id) {
    OrderDto order = lookup(id);
    if (order == null) {
        return ResponseEntity.notFound().build();
    }
    return ResponseEntity.ok(order);
}
~~~

This is a **fragment** because `OrderDto` and `lookup` depend on the application. Returning `ResponseEntity.ok(order)` sets status 200; `notFound().build()` returns 404 with no body. There is no need to add `@ResponseBody` for Spring to handle `ResponseEntity`. Use `ResponseEntity.created(uri).body(dto)` when you want 201 along with a `Location` header.

`@ResponseStatus` can specify a status for a handler, but it does not support flexible per-branch logic like `ResponseEntity`. Do not equate **having a body** with **HTTP 200**: you can still return 201/204/404 depending on processing, and with 204 the body must be omitted.

## 4. `HttpMessageConverter`: Why Do Objects Become JSON?

When Spring chooses the response body branch, `RequestResponseBodyMethodProcessor` or the corresponding return handler works with `HttpMessageConverter` to **serialize** the value.

Mapping example:

~~~java
@GetMapping(path = "/api/products/7", produces = "application/json")
@ResponseBody
public ProductDto product() {
    return new ProductDto(7L, "Spring MVC");
}
~~~

`ProductDto` in the fragment is a record/POJO defined in the application. With `spring-boot-starter-web` and default Jackson, the body is typically:

~~~json
{"id":7,"name":"Spring MVC"}
~~~

With the same content if written as:

~~~java
@GetMapping(path = "/api/products/title", produces = "text/plain")
@ResponseBody
public String title() {
    return "Spring MVC";
}
~~~

The body is:

~~~text
Spring MVC
~~~

**There is no JSON quote syntax in the text response above**. A `String` is not automatically JSON-encoded just because the method is inside a `@RestController`. Distinguish between:
- `StringHttpMessageConverter`: typically converts `String` to text.
- Jackson JSON converter, in Spring Framework 6.x typically `MappingJackson2HttpMessageConverter`: can serialize records/POJOs to JSON.
- `ByteArrayHttpMessageConverter`, `ResourceHttpMessageConverter`, and other converters: handle their corresponding body types.
- Converters can be customized; actual output depends on HTTP negotiation and application configuration.

### 4.1. `Content-Type`, `Accept`, `produces`

- `Content-Type` in the **response** describes the format of data sent by the server.
- `Accept` in the **request** states which formats the client can receive.
- `@GetMapping(produces = "...")` constrains the handler's representation and participates in mapping selection/negotiation.
- `@PostMapping(consumes = "...")` constrains the Content-Type of the **request body**; it does not make the response always JSON.

If a client sends `Accept: application/xml` while the endpoint only has a mapping producing `application/json`, Spring may return **406 Not Acceptable**. If a client sends a JSON request body to a method that only `consumes=text/plain`, it may encounter **415 Unsupported Media Type**. Not every method returning a DTO is always JSON: compatible converters and media types are required.

**Dangerous mistake:** forcing `produces="application/json"` on a method returning `String` while only returning the literal `hello` without JSON quotes. Because the `String` converter may write the raw string with the JSON media type, the client may receive a payload that is **not valid JSON**. If you want to return a JSON string, control serialization explicitly; for normal APIs, return a **DTO/record** instead of trying to use `String` as a JSON body.

### 4.2. Returned Object Content May Differ from the Java Debugger

Java objects may contain `LocalDate`, enums, nested records, object references, Jackson annotations, and lazy JPA proxies. Serialization configuration determines field names, date formats, null handling, and circular reference errors. **Do not return sensitive entities directly** assuming JSON will only contain the desired fields; define a stable response DTO.

## 5. Complete Example: HTML View, Text Body, and JSON Body in One Application

This Java 17 + Spring Boot 3.x example uses **Thymeleaf** to demonstrate view name resolution and Spring MVC/Jackson to return API data. This is a **single application** with three kinds of endpoints so you can compare them directly.

Project structure:

~~~text
response-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/responsedemo/
    │   │   ├── ResponseDemoApplication.java
    │   │   └── web/
    │   │       ├── GreetingPageController.java
    │   │       ├── GreetingApiController.java
    │   │       └── GreetingDto.java
    │   └── resources/templates/
    │       └── greeting.html
    └── test/java/com/example/responsedemo/web/
        └── GreetingControllerTest.java
~~~

### 5.1. Gradle Dependencies

`settings.gradle`:

~~~groovy
rootProject.name = 'response-demo'
~~~

`build.gradle` (demonstrating a Spring Boot 3.3.5, Java 17 project; you can use any 3.x version managed by your project):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` provides Spring MVC and standard JSON converters; `spring-boot-starter-thymeleaf` provides the view technology, view resolver, and template rendering. If you omit Thymeleaf without providing another view resolver, returning `"greeting"` is **not enough** to render HTML.

Example running with the Gradle wrapper included in the project:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell/CMD you can use `.\gradlew.bat bootRun`. The commands above assume the wrapper and required network dependencies are ready; do not use `javac` directly for Spring-dependent code, as Gradle resolves the classpath.

### 5.2. Spring Boot Entry Point

`src/main/java/com/example/responsedemo/ResponseDemoApplication.java`:

~~~java
package com.example.responsedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResponseDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResponseDemoApplication.class, args);
    }
}
~~~

Placed in the parent package so component scanning discovers controllers under `web`.

### 5.3. `@Controller` Returning a View Name

`src/main/java/com/example/responsedemo/web/GreetingPageController.java`:

~~~java
package com.example.responsedemo.web;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class GreetingPageController {

    @GetMapping("/pages/greeting")
    public String greeting(
            @RequestParam(name = "name", defaultValue = "Guest") String name,
            Model model) {

        model.addAttribute("name", name);
        return "greeting";
    }

    @GetMapping("/pages/home")
    public String home() {
        return "redirect:/pages/greeting?name=Guest";
    }
}
~~~

- Returns `"greeting"` so Spring looks up the view/template; it does not send the literal `greeting`.
- `Model` passes `name` into the rendering process.
- `"redirect:/..."` is a special prefix used by compatible view resolvers to issue an HTTP redirect. It is not printed as page content.
- The rendered HTML code is the result of **template + model**, different from the Java return value.

### 5.4. Thymeleaf Template for the View

`src/main/resources/templates/greeting.html`:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Greeting page</title>
</head>
<body>
    <h1 th:text="'Hello ' + ${name}">Hello Guest</h1>
    <p>This page is rendered from a Thymeleaf template.</p>
</body>
</html>
~~~

With `GET /pages/greeting?name=Lan`, Thymeleaf renders the heading as:

~~~html
<h1>Hello Lan</h1>
~~~

`th:text` escapes text when inserting data, avoiding treating the user's name as arbitrary HTML. Avoid methods that insert untrusted data into templates as unescaped HTML unless an appropriate sanitization policy is in place.

### 5.5. DTO for the REST Response

`src/main/java/com/example/responsedemo/web/GreetingDto.java`:

~~~java
package com.example.responsedemo.web;

public record GreetingDto(long id, String greeting) {
}
~~~

An immutable record clearly defines the JSON shape in the demo.

### 5.6. `@RestController` Returning JSON/Text and Using `ResponseEntity`

`src/main/java/com/example/responsedemo/web/GreetingApiController.java`:

~~~java
package com.example.responsedemo.web;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class GreetingApiController {

    @GetMapping(path = "/greeting", produces = MediaType.APPLICATION_JSON_VALUE)
    public GreetingDto greeting() {
        return new GreetingDto(7L, "Hello Lan");
    }

    @GetMapping(path = "/message", produces = MediaType.TEXT_PLAIN_VALUE)
    public String message() {
        return "Hello Lan";
    }

    @GetMapping(path = "/response", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<GreetingDto> response() {
        return ResponseEntity.ok(new GreetingDto(8L, "Hello from ResponseEntity"));
    }

    @GetMapping(path = "/redirect-text", produces = MediaType.TEXT_PLAIN_VALUE)
    public String redirectText() {
        return "redirect:/pages/greeting";
    }
}
~~~

Observations:
- `GET /api/greeting` uses Jackson to write the record as JSON.
- `GET /api/message` writes the exact string `Hello Lan` into the body, without template lookup.
- `GET /api/response` returns status 200 and the JSON body according to `ResponseEntity`.
- `GET /api/redirect-text` returns the literal string `redirect:/pages/greeting`, **not** a 302 redirect. `@RestController` enables body semantics at the class level.

### 5.7. Example of `@Controller` Enabling Body Semantics on a Single Method

To combine HTML and text serving in one controller, you can add the following method **to `GreetingPageController`**, along with the necessary imports:

~~~java
// Fragment to place inside an existing @Controller:
@GetMapping(path = "/pages/health", produces = MediaType.TEXT_PLAIN_VALUE)
@ResponseBody
public String health() {
    return "UP";
}
~~~

Add imports:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.ResponseBody;
~~~

Then `GET /pages/health` will return the text `UP`. The fragment does not compile standalone because it must live inside `GreetingPageController`; this is a design choice and does not need to be added if the project wants to keep the web-page controller purely view-based.

If the entire class returns machine-readable data, using `@RestController` expresses the intent more clearly. If only a few methods need a body inside a page-serving controller, use method-level `@ResponseBody` to highlight the exception.

## 6. Inspecting via HTTP: Same Data, Different Responses

After starting the application:

~~~bash
curl -i 'http://localhost:8080/pages/greeting?name=Lan'
curl -i 'http://localhost:8080/api/greeting'
curl -i 'http://localhost:8080/api/message'
curl -i 'http://localhost:8080/api/redirect-text'
curl -i 'http://localhost:8080/pages/home'
~~~

Key results:

| URL | Default HTTP | Response format | Notable content |
| --- | --- | --- | --- |
| `/pages/greeting?name=Lan` | 200 | `text/html` | HTML from `greeting.html`, containing `<h1>Hello Lan</h1>` |
| `/api/greeting` | 200 | `application/json` | `{"id":7,"greeting":"Hello Lan"}` |
| `/api/message` | 200 | `text/plain` | `Hello Lan` |
| `/api/redirect-text` | 200 | `text/plain` | `redirect:/pages/greeting` |
| `/pages/home` | 302 common | `Location` header | Browser redirects to `/pages/greeting?name=Guest` |

These results follow the demo code and default Spring Boot/Thymeleaf configuration. Header order, charset, and full HTML formatting may vary by template/version. For redirects, use `curl -i` to see the status/header and **do not add `-L`** if you want to observe the 302 before the client automatically follows it.

`@ResponseBody` does not require the default status to be 201 or 204; if a method completes normally without changing the status, Spring typically returns 200. Return statuses intentionally when building resource creation/deletion APIs.

## 7. MockMvc: Testing Views, Bodies, Media Types, and Redirects

Write tests against the full application so the real Thymeleaf view resolver is present. `src/test/java/com/example/responsedemo/web/GreetingControllerTest.java`:

~~~java
package com.example.responsedemo.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void controllerStringIsViewName() throws Exception {
        mvc.perform(get("/pages/greeting").param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(view().name("greeting"))
                .andExpect(model().attribute("name", "Lan"))
                .andExpect(content().string(containsString("<h1>Hello Lan</h1>")));
    }

    @Test
    void restControllerDtoIsJsonBody() throws Exception {
        mvc.perform(get("/api/greeting").accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.greeting").value("Hello Lan"));
    }

    @Test
    void restControllerStringIsPlainTextBody() throws Exception {
        mvc.perform(get("/api/message").accept(MediaType.TEXT_PLAIN))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_PLAIN))
                .andExpect(content().string("Hello Lan"));
    }

    @Test
    void redirectPrefixIsLiteralTextInRestController() throws Exception {
        mvc.perform(get("/api/redirect-text"))
                .andExpect(status().isOk())
                .andExpect(content().string("redirect:/pages/greeting"));
    }

    @Test
    void redirectPrefixInMvcControllerTriggersRedirect() throws Exception {
        mvc.perform(get("/pages/home"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/pages/greeting?name=Guest"));
    }

    @Test
    void incompatibleAcceptOnJsonMappingIsNotAcceptable() throws Exception {
        mvc.perform(get("/api/greeting").accept(MediaType.APPLICATION_XML))
                .andExpect(status().isNotAcceptable());
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

The test suite intentionally checks **status, media type, view name, model, and body**. If you only assert status 200, a route accidentally returning a body string as a view name could go unnoticed if that view happens to exist.

A few notes:
- `@SpringBootTest` boots the full context so the view resolver/templates are present; testing views with `@WebMvcTest` alone may require additional auto-configuration/beans.
- If the application has Spring Security, filters, or multiple `@ControllerAdvice` beans, MockMvc must be configured with the corresponding authentication and error contract. This is a test environment concern, not the nature of `@ResponseBody`.
- The `406` test can depend on content negotiation/converter customizations. With an explicit `produces=application/json` like in the demo, an incompatible `Accept=application/xml` reasonably expects 406.
- Do not rely on full HTML content or HTTP header order as an immutable contract; focus on important content and metadata.

## 8. When You Need a Real Redirect from an API

It is wrong to use a literal view prefix in a REST method:

~~~java
@RestController
class WrongRedirectController {
    @GetMapping("/wrong-redirect")
    public String wrongRedirect() {
        return "redirect:/pages/greeting";
    }
}
~~~

The result will be a **string body**, not an HTTP redirect. To produce an explicit 302/303 and `Location`, use `ResponseEntity` in the REST controller:

~~~java
// Fragment inside a @RestController with the relevant classes imported:
@GetMapping("/go")
public ResponseEntity<Void> go() {
    return ResponseEntity.status(302)
            .location(URI.create("/pages/greeting"))
            .build();
}
~~~

Needs imports for `java.net.URI` and `org.springframework.http.ResponseEntity`. 302 is only an example; after a POST when you want to direct the client to another resource, **303 See Other** usually expresses the requirement to use GET at the target URL more clearly. Do not use a Java `String` to imply an HTTP status.

In a page controller, `return "redirect:/..."` is simple and tied to MVC/view flow. In a REST API, returning `ResponseEntity` with an explicit URL/Location helps HTTP clients understand protocol semantics immediately.

`forward:` in `@Controller` also acts as a special view prefix for view resolver configurations that support it. When returned from `@RestController` as a `String`, it is merely a literal body. A forward is a server-side request dispatch, **different from an HTTP redirect** seen by the browser.

## 9. Other Confusing Cases

### 9.1. Model/View and Body Do Not Replace Each Other

~~~java
@Controller
class ReportController {
    @GetMapping("/reports")
    public String reports(Model model) {
        model.addAttribute("count", 5);
        return "reports";
    }
}
~~~

`model.addAttribute` serves view rendering; it **does not automatically create a JSON body** containing `{"count":5}`. For a JSON API, return a DTO, a `Map` under `@ResponseBody`, or a `ResponseEntity`; whereas a `@Controller` returning a `Map` without body semantics enabled may be interpreted as adding model attributes and selecting a view.

### 9.2. `ModelAndView` and `View` Are Special Types

`ModelAndView` typically carries a view name (or `View` instance), a model, and an optional status. It has its own return handler. Do not claim that **every** Java object returned from `@RestController` is always JSON-serialized: the framework evaluates **special return handlers** first depending on signature/annotations. However, for readable code, handlers intended to render templates should belong in `@Controller`, while API DTO/body handlers belong in `@RestController`.

### 9.3. `void`, `null`, and Servlet Response

Methods returning `void` or `null` have several contexts: having written directly to `HttpServletResponse`, having `@ResponseStatus`, having satisfied ETag/Last-Modified, or falling back to a default view name. For REST handlers, the body may be empty. Therefore, **do not treat `null` as an instruction to return 404 or 204**. Return `ResponseEntity.noContent().build()` for 204, and `ResponseEntity.notFound().build()` for 404 when that is the API intent.

### 9.4. `@RequestBody` and `@ResponseBody` Have Opposite Directions

| Annotation | Primary location | Data flow |
| --- | --- | --- |
| `@RequestBody` | Handler parameter | **HTTP request body → Java object** via converter |
| `@ResponseBody` | Controller method/class | **Java return value → HTTP response body** via converter |

Similar names, not synonyms. Both can be used on a POST REST endpoint: receiving a JSON request and producing a JSON response, though you only need `@RestController` to replace class-level `@ResponseBody`.

### 9.5. Does Every `@Controller` Need a Template Engine?

No. `@Controller` is just a web component stereotype. A template engine or view resolver is required **when a method uses view rendering**. A plain `@Controller` that accepts requests and returns `ResponseEntity` still works without Thymeleaf. Only when a method returns a view name without a properly configured view technology do you need to inspect the resolver/template.

### 9.6. Why Does Postman Show JSON When a REST Endpoint Returns a String?

Some UI tools attempt to parse/display based on headers or guess on their own. Check the **actual body bytes** and `Content-Type` using curl or integration tests. `"hello"` as a Java `String` may be written as `hello` without quotes; a valid JSON scalar string must have quotes, e.g., `"hello"` (the HTTP payload includes the quote pair).

If the client requires a structured JSON payload, use a DTO like `new MessageDto("hello")` → `{"message":"hello"}`, which is clearer for API contracts, documentation generators, and versioning.

## 10. Common Errors and How to Diagnose Them

| Symptom | Common cause | Check / fix |
| --- | --- | --- |
| Returned `"ok"` but got a view/template error | `@Controller` returned `String` interpreted as a view name | Add `@ResponseBody` or use `@RestController` for the API |
| Wanted HTML but saw literal text `home` | `@RestController` or `@ResponseBody` wrote the literal string as body | Use `@Controller`, ensure view resolver/template exist |
| Returned `"redirect:/login"` but got status 200 and literal body | Return is inside a `@RestController` | Use `@Controller` redirect view or `ResponseEntity` status + Location |
| Template not found / HTTP 500 | Wrong view name, template path, missing Thymeleaf/JSP config | Cross-check `return "viewName"` with resolver/template |
| DTO does not become JSON | Missing Jackson/converter, serialization error, mismatched media type | Check dependencies/converters, DTO, and `Accept`/`produces` |
| 406 when requesting JSON API | `Accept` incompatible with `produces` | Adjust `Accept` or supported representations |
| Response looks like plain text while header claims JSON | Returned raw `String` or mismatched custom converter/produces | Use a DTO so the serializer produces valid JSON |
| JSON accidentally leaks internal info | Returned entity directly with unwanted properties | Create a response DTO, control serialization |
| Empty body when frontend expects an object | Method returned `null`/`void` or 204 response | Design clear status and response schema |
| Endpoint has a response body even though class is `@Controller` | Method returns `ResponseEntity` or has `@ResponseBody` | This is valid behavior; check return type/annotations before concluding |

When debugging, inspect **type- and method-level annotations**, **return type**, **status**, **Content-Type**, **body bytes**, **view resolver**, and **request Accept** together. These elements often explain behavior that looking only at Java's `return` statement would miss.

## 11. Choosing a Design Based on Application Intent

**Server-rendered HTML applications:** use `@Controller`, have methods return logical view names or `ModelAndView`, use `Model` and template/view technology. If a few small endpoints must return text/data, place `@ResponseBody` on those individual methods.

**REST APIs returning DTOs:** use `@RestController` to serialize bodies by default; return records/DTOs and use `ResponseEntity<T>` when status/header control is needed. Specify `produces` when the API must advertise a specific media type; write `Accept` compatibility tests.

**Mixed HTML/API controllers:** you can use `@Controller` for templates and `@ResponseBody`/`ResponseEntity` for data endpoints, though if scope grows large enough, splitting into page controllers and API controllers makes behavior more obvious. Do not try to use `redirect:`-prefixed strings in API controllers to drive HTTP redirects.

**Security note:** View technologies and JSON converters escape/serialize differently. Thymeleaf `th:text` escapes HTML; JSON serialization handles escaping according to JSON rules. Never concatenate HTML directly from request data and return `@ResponseBody String` assuming it has the same protections as a template.

## 12. Summary via Self-Check Questions

**Question 1.** Why does a `@Controller` returning `"home"` without `@ResponseBody` usually not send the body `home`?

**Answer:** `String` is interpreted as a logical view name, requiring a `ViewResolver` and view rendering.

**Question 2.** Does `@RestController` mean responses are always JSON?

**Answer:** No. It enables body semantics at the class level; converter + type + media negotiation determine the representation. A `String` can be plain text.

**Question 3.** Does a `@Controller` returning `ResponseEntity<MyDto>` need `@ResponseBody`?

**Answer:** No. `ResponseEntity` has its own return value handling for status, headers, and body.

**Question 4.** How do you perform a real redirect from a `@RestController`?

**Answer:** Use a 3xx status and the `Location` header, e.g., `ResponseEntity.status(302).location(uri).build()`.

**Question 5.** Which component serializes a Java DTO to JSON?

**Answer:** In Spring MVC, the response body return handler invokes an `HttpMessageConverter`, typically the Jackson JSON converter in the web starter.

**Question 6.** To be sure an endpoint is a view, what should you test?

**Answer:** Check `view().name(...)`, model attributes, and rendered HTML; for body endpoints, check text/JSON bytes, Content-Type, and status.

## 13. Official Documentation

- [Spring Framework 6.2 — `@ResponseBody`](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/responsebody.html): annotation on method/class, `HttpMessageConverter`, and `@RestController`.
- [Spring Framework 6.2 — Return Values](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/return-types.html): `String` view names, `View`, `ModelAndView`, `ResponseEntity`, `@ResponseBody`.
- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html): converters and body types.
- [Spring Framework 6.2 — Mapping Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html): `produces`, `consumes`, and HTTP content negotiation.
- [Spring Framework 6.2 — View Resolution](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-core/viewresolver.html): role of `ViewResolver` in HTML rendering.
- [Spring Boot — Spring MVC with Template Engines](https://docs.spring.io/spring-boot/reference/web/servlet.html): Spring MVC auto-configuration and template engines.

**Key takeaway:** when a method returns `String`, do not guess behavior from the Java type. Identify **which return handler is selected**: `@Controller` typically passes `String` to **ViewResolver**, while `@ResponseBody`/`@RestController` passes the return value to **HttpMessageConverter**. From there you can deduce the actual response and write accurate tests.
