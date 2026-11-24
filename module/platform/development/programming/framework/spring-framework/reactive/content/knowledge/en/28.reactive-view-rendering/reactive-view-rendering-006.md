# Blocking View Technology Limitations and Differences from JSP on Servlet

## 1. View Resolution in Spring WebFlux

Spring WebFlux can render HTML on the server in addition to providing REST APIs. A controller returns a view name and a model; the framework locates the corresponding template, renders the content, and writes it to the HTTP response.

Core components:

- `ViewResolver` maps a logical view name, such as `greeting`, to a `View`.
- `View` receives the model, media type, and exchange to render.
- `ViewResolutionResultHandler` coordinates view resolution inside `DispatcherHandler`.
- `ServerWebExchange` provides the request, response, and context for the HTTP exchange.

~~~text
HTTP Request
     |
     v
DispatcherHandler
     |
     v
HandlerMapping -> @Controller
     |
     v
HandlerResult + Model
     |
     v
ViewResolutionResultHandler
     |
     v
ViewResolver -> View
     |
     v
Template engine + Model
     |
     v
ServerHttpResponse
~~~

WebFlux's rendering contract is reactive:

~~~java
Mono<Void> render(
    Map<String, ?> model,
    MediaType contentType,
    ServerWebExchange exchange
);
~~~

`Mono<Void>` represents when rendering finishes or emits an error. However, a Publisher return type does not automatically make everything inside the template engine non-blocking. The View implementation and custom helpers determine the actual execution thread.

### 1.1. Controller Returning a View Name

Use `@Controller` when you want Spring to treat the result as a template name:

~~~java
@Controller
public class GreetingPageController {

    @GetMapping("/greeting")
    public String greeting(Model model) {
        model.addAttribute("message", "Hello WebFlux");
        return "greeting";
    }
}
~~~

If `@RestController` or `@ResponseBody` is used, the returned string is typically written directly to the response body instead of being interpreted as a view name.

A controller can also return `Mono<String>`:

~~~java
@GetMapping("/greeting")
public Mono<String> greeting(Model model) {
    model.addAttribute("message", "Hello WebFlux");
    return Mono.just("greeting");
}
~~~

### 1.2. Reactive Data in the Model

WebFlux supports model attributes of type Publisher:

~~~java
model.addAttribute("profile", profileService.findProfile(userId));
return Mono.just("profile");
~~~

Before rendering, `AbstractView` resolves asynchronous model attributes:

- `Mono<T>` resolves to a single value or empty if the Mono emits no item.
- `Flux<T>` is collected into a `List<T>`.
- Other publishers are converted if a matching adapter is available.

An infinite `Flux` is unsuitable for standard template models because collecting into a List waits for the source to complete and can accumulate unbounded data. If you need to stream HTML, use HTML fragments or a streaming protocol.

### 1.3. Content Negotiation

`ViewResolutionResultHandler` can pick a view based on the media type requested by the client. WebFlux provides `HttpMessageWriterView` to render models through codecs, such as JSON or XML. There is no need to use a template engine to generate JSON when codecs already handle it.

## 2. Blocking and Its Impact on the Event Loop

### 2.1. Why Is Blocking Dangerous?

WebFlux typically runs on a small fixed number of event-loop worker threads. Each worker can serve many requests using asynchronous I/O and callbacks.

If a callback calls a synchronous library and waits for a result, the current worker cannot process other events during that time. When multiple requests block simultaneously:

- Other requests must wait for the event loop to be freed.
- Latency rises even when CPU may still be underutilized.
- Concurrency drops.
- Template helpers that read files, call JDBC, or make synchronous HTTP calls can stall the processing thread.

Spring MVC on Servlet assumes requests may block and uses a thread pool to absorb wait time. WebFlux assumes the main processing path is non-blocking, so blocking I/O has a much larger impact on concurrency.

### 2.2. Distinguishing I/O-Bound and CPU-Bound Work

| Work | Characteristic | Approach |
| --- | --- | --- |
| Reading files with synchronous APIs | Blocking I/O | boundedElastic or dedicated executor |
| Synchronous JDBC/JPA | Blocking I/O | Isolate; consider R2DBC if end-to-end reactive is needed |
| Calling HTTP with WebClient | Non-blocking I/O | Compose directly in the reactive chain |
| Heavy CPU computation | CPU-bound | Appropriate CPU scheduler or algorithm optimization |
| Rendering templates in memory | Typically CPU and synchronous processing | Measure timing, control output and scheduler |

### 2.3. Isolating Blocking APIs

If a synchronous library must be called, create a Publisher from a callable and shift subscription to boundedElastic:

~~~java
Mono<LegacyReport> report =
    Mono.fromCallable(() -> legacyReportClient.load(reportId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

`subscribeOn` moves subscription and callable execution to the specified scheduler.

Do not confuse this with:

~~~java
Mono.fromCallable(() -> legacyReportClient.load(reportId))
    .publishOn(Schedulers.boundedElastic());
~~~

`publishOn` switches operators downstream of it. The source callable may already run before signals reach publishOn. Use subscribeOn to isolate the blocking source itself.

Do not call `block()`, `Future.get()`, or `Thread.sleep()` directly in controllers, views, or event-loop callbacks. Do not spawn a new thread per request.

### 2.4. Not All View Engines Are Blocking

A view can return `Mono<Void>` while still doing synchronous work internally. Conversely, some WebFlux integrations proactively isolate blocking steps.

For example, `FreeMarkerView` since Spring Framework 6.1 uses boundedElastic for potentially blocking template lookup. Even so, custom directives, macros, helpers, or custom service calls still require independent evaluation.

## 3. Supported View Technologies and Limitations

### 3.1. Thymeleaf

Thymeleaf integration with WebFlux is maintained by the Thymeleaf project. Main components:

- `SpringResourceTemplateResolver` locates templates.
- `SpringWebFluxTemplateEngine` processes templates.
- `ThymeleafReactiveViewResolver` connects the engine to view resolution.

Spring Boot provides auto-configuration for Thymeleaf. Default templates reside in `src/main/resources/templates`.

You can configure reactive chunked mode:

~~~properties
spring.thymeleaf.reactive.max-chunk-size=8KB
spring.thymeleaf.reactive.chunked-mode-view-names=reports/**
~~~

`max-chunk-size` limits the DataBuffer size when writing the response. When configured, matching views can render in CHUNKED mode. `full-mode-view-names` can specify views requiring FULL mode.

### 3.2. FreeMarker

Spring Framework integrates FreeMarker directly for WebFlux via `FreeMarkerConfigurer`, `FreeMarkerViewResolver`, and `FreeMarkerView`. Spring Boot also provides auto-configuration; default templates are searched in `classpath:/templates/` with the default `.ftlh` suffix.

`.ftlh` is FreeMarker's HTML format with output-format-based auto-escaping.

Some Boot FreeMarker properties only support Spring MVC, for example:

- `spring.freemarker.allow-request-override`.
- `spring.freemarker.allow-session-override`.
- `spring.freemarker.expose-request-attributes`.
- `spring.freemarker.expose-session-attributes`.
- `spring.freemarker.expose-spring-macro-helpers`.
- `spring.freemarker.cache`.
- `spring.freemarker.content-type`.

Properties tied to `HttpServletRequest`, `HttpSession`, or Servlet views cannot be applied as-is to a reactive exchange. When migrating from MVC, check metadata for your exact Boot version instead of copying all settings blindly.

Another limitation is output buffering: Spring Framework 6.2's `FreeMarkerView` implementation processes the template into an in-memory buffer before writing the response. Very large pages may require memory proportional to the entire rendered HTML; standard views are not infinite streams. If incremental output is needed, consider Thymeleaf chunked mode or HTML fragments.

### 3.3. Mustache and Script Templates

Spring Boot provides auto-configuration for Mustache in WebFlux. Default templates reside in `src/main/resources/templates` and use the `.mustache` suffix. Mustache fits simple templates with minimal logic and helpers.

Spring Framework also has script views for libraries running on JSR-223. The engine must implement `ScriptEngine` and `Invocable`; it can be configured with `ScriptTemplateConfigurer`:

~~~java
@Override
public void configureViewResolvers(ViewResolverRegistry registry) {
    registry.scriptTemplate();
}
~~~

Thread safety, compilation cost, and blocking behavior depend on the script engine. A non-thread-safe engine may need separate instances or proper synchronization.

### 3.4. How Does JSP on Servlet Differ from WebFlux?

Spring Framework integrates JSP/JSTL with Spring MVC. The typical resolver is `InternalResourceViewResolver`; when using JSTL, Spring MVC uses `JstlView` to prepare i18n and form binding.

| Spring MVC + JSP | Spring WebFlux |
| --- | --- |
| `DispatcherServlet` | `DispatcherHandler` |
| `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange` |
| `InternalResourceViewResolver` | WebFlux `ViewResolver` |
| `JstlView` / JSP servlet | Thymeleaf reactive, FreeMarker WebFlux, Mustache, or custom reactive View |
| Servlet request/response lifecycle | Publishers and `Mono<Void>` |
| Servlet thread pool absorbs blocking | Event loop must avoid blocking |

JSP is compiled and executed via a JSP engine/Servlet container. `InternalResourceViewResolver` dispatches to a Servlet resource; Spring form tags and JSTL rely on servlet requests, page context, and Spring MVC.

The JSP resolver belongs to the `spring-webmvc` module. It is not a WebFlux `ViewResolver` and does not accept `ServerWebExchange` for rendering. Simply adding JSP files or a JSP engine to a WebFlux app does not make JSP a native WebFlux view.

### 3.5. Does Running WebFlux on Tomcat Make JSP Work?

No. Tomcat and Jetty can run both Spring MVC and WebFlux, but the two frameworks use the container differently:

- MVC uses Servlet blocking I/O and grants applications direct access to the Servlet API.
- WebFlux uses the server's non-blocking I/O; when running on a Servlet container, the Servlet API sits behind an adapter and is not exposed directly to application code.

Choosing Tomcat as the reactive server does not mean the application runs Spring MVC or has a JSP resolver. WebFlux also does not require the Servlet API and does not use `src/main/webapp` like a traditional WAR application.

## 4. HTML Streaming and Model Limits

### 4.1. Flux in the Model Does Not Create a Stream Automatically

~~~java
model.addAttribute("orders", orderService.findAll());
return Mono.just("orders");
~~~

If `findAll()` returns `Flux<Order>`, view resolution collects the Flux into a `List<Order>` before rendering. This suits finite lists that fit in memory.

Do not use this pattern for infinite Fluxes, continuous event streams, or huge datasets. Paginate, limit item counts, or use a streaming protocol.

### 4.2. HTML Fragments

Spring Framework 6.2 supports rendering multiple HTML fragments in a single request. A controller can return `Collection<Fragment>` or `FragmentsRendering`:

~~~java
@GetMapping("/dashboard")
public FragmentsRendering dashboard() {
    return FragmentsRendering.fragment("summary")
        .fragment("notifications")
        .build();
}
~~~

If fragments need to be streamed, you can build `FragmentsRendering` from a `Flux<Fragment>` or return `Flux<Fragment>` directly. This fits HTMX/Hotwire Turbo and HTML-over-the-wire.

### 4.3. Redirects, Forwarding, and Static Resources

WebFlux supports redirects via the `redirect:` prefix or `Rendering.redirectTo`. WebFlux does not support Servlet-style `forward:` dispatches.

WebFlux has `ResourceHandler` and `ResourceResolver` to serve static assets. However, there is currently no transparent URL rewriting for the static resource chain like in Spring MVC. When versioned URLs are needed, you can use `ResourceUrlProvider` directly or a dedicated helper; avoid blocking the event loop just to rewrite URLs.

### 4.4. Memory and Template Security

Template rendering can hold the model and output in memory. Pass only needed fields into the model, never call databases or services from template expressions, avoid collecting large Fluxes into Lists, and measure allocation/GC under load.

Template views can access beans in the application context. Do not allow end users or external sources to arbitrarily edit templates rendered inside the trust boundary. Keep templates in controlled sources, escape HTML data, and avoid exposing high-privilege beans unnecessarily.

## 5. Complete Spring Boot 3.5.7 + Java 17 Example

This example uses FreeMarker to render a greeting page. The model contains a `Mono<Greeting>`, and the controller returns `Mono<String>` as the view name. Spring Boot auto-configures WebFlux and FreeMarker.

### 5.1. Project Structure

~~~text
webflux-view-demo/
├── pom.xml
├── src/main/resources/
│   ├── application.properties
│   └── templates/
│       └── greeting.ftlh
├── src/main/java/example/view/
│   ├── WebFluxViewApplication.java
│   ├── Greeting.java
│   ├── GreetingService.java
│   └── GreetingPageController.java
└── src/test/java/example/view/
    └── GreetingPageControllerTest.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-view-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-freemarker</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. application.properties

~~~properties
server.port=8080
spring.freemarker.template-loader-path=classpath:/templates/
spring.freemarker.suffix=.ftlh
spring.freemarker.charset=UTF-8
~~~

### 5.4. WebFluxViewApplication.java

~~~java
package example.view;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxViewApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxViewApplication.class, args);
    }
}
~~~

### 5.5. Greeting.java

~~~java
package example.view;

public record Greeting(
    String message,
    String generatedAt
) {
}
~~~

### 5.6. GreetingService.java

~~~java
package example.view;

import java.time.Instant;
import java.time.Duration;
import java.time.format.DateTimeFormatter;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class GreetingService {

    public Mono<Greeting> loadGreeting() {
        return Mono.delay(Duration.ofMillis(20))
            .map(ignored -> new Greeting(
                "Hello from Spring WebFlux",
                DateTimeFormatter.ISO_INSTANT.format(Instant.now())
            ));
    }
}
~~~

`Mono.delay` illustrates an asynchronous data source. In a real application, the service can call a reactive repository, WebClient, or another Publisher.

### 5.7. GreetingPageController.java

~~~java
package example.view;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

import reactor.core.publisher.Mono;

@Controller
@RequestMapping("/pages")
public class GreetingPageController {

    private final GreetingService greetingService;

    public GreetingPageController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    public Mono<String> greeting(Model model) {
        model.addAttribute("greeting", greetingService.loadGreeting());
        return Mono.just("greeting");
    }
}
~~~

The controller adds `Mono<Greeting>` to the model and returns the view name `greeting`. WebFlux resolves the model Publisher before rendering. Do not call `block()` to retrieve the Greeting.

### 5.8. greeting.ftlh

~~~html
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>WebFlux View Demo</title>
</head>
<body>
    <main>
        <h1>${greeting.message}</h1>
        <p>Generated at: <time>${greeting.generatedAt}</time></p>
    </main>
</body>
</html>
~~~

The `.ftlh` extension uses FreeMarker's HTML output format, supporting auto-escaping for values inserted into the template.

### 5.9. GreetingPageControllerTest.java

~~~java
package example.view;

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class GreetingPageControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void rendersFreeMarkerViewFromReactiveModel() {
        client.get()
            .uri("/pages/greeting")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_HTML)
            .expectBody(String.class)
            .value(html -> {
                assertTrue(html.contains("Hello from Spring WebFlux"));
                assertTrue(html.contains("<time>"));
            });
    }
}
~~~

The test goes through the embedded HTTP server and real view resolution. It verifies status, media type, and the HTML rendered from the reactive model.

### 5.10. Running the Application and Tests

Requires JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Call the endpoint:

~~~bash
curl -i http://localhost:8080/pages/greeting
~~~

The response body looks like:

~~~html
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>WebFlux View Demo</title>
</head>
<body>
    <main>
        <h1>Hello from Spring WebFlux</h1>
        <p>Generated at: 2026-11-08T04:00:00Z</p>
    </main>
</body>
</html>
~~~

The actual timestamp is generated when the request executes, so it will vary. The snippet above only illustrates the HTML structure.

Run the integration test:

~~~bash
mvn test
~~~

## 6. Diagnostics, Common Pitfalls, and Checklist

### 6.1. Diagnosing View Resolution

When a controller returns the wrong HTML or the view name appears as plain text, check:

1. Does the controller use `@Controller` instead of `@RestController`?
2. Does the method have `@ResponseBody`, causing the string to be written straight to the body?
3. Is the appropriate ViewResolver on the classpath?
4. Is the template at the right loader path?
5. Do the view name and suffix match?
6. Does the response have the right Content-Type?
7. Do multiple resolvers match the same view name?

If rendering is slow, record thread names in controllers/services/helpers, separate data-fetching time from rendering time, check for synchronous JDBC/JPA/file I/O/HTTP calls, and measure latency under load. If memory grows, inspect model and output sizes, check whether the engine buffers full HTML or renders in chunks, avoid collecting large Fluxes into Lists, and verify cancellation.

### 6.2. Common Pitfalls

**Mistake 1 — Using @RestController and returning a template name.** The string is written as the response body. Use @Controller when view resolution is needed.

**Mistake 2 — Assuming JSP works automatically because the server is Tomcat.** WebFlux on Tomcat still uses the reactive adapter. The JSP resolver belongs to the Spring MVC Servlet stack.

**Mistake 3 — Adding InternalResourceViewResolver to WebFlux.** That resolver dispatches to Servlet resources and is not a WebFlux ViewResolver.

**Mistake 4 — Seeing Mono<Void> and concluding rendering is non-blocking.** The View implementation may call synchronous APIs. Check the engine, helpers, and execution threads.

**Mistake 5 — Calling JDBC/JPA or reading files synchronously in template expressions.** Rendering may block the event loop. Fetch data in services and isolate blocking APIs before placing values in the model.

**Mistake 6 — Using publishOn after a callable to offload a blocking source.** The callable may already execute before publishOn. Use fromCallable combined with subscribeOn.

**Mistake 7 — Putting an infinite Flux into the model.** View resolution collects Flux into a List and waits for completion. Use Fragment rendering or a streaming protocol.

**Mistake 8 — Assuming FreeMarker always streams HTML line by line.** FreeMarkerView may buffer output before writing. Check memory usage and pick a suitable rendering approach.

**Mistake 9 — Copying all FreeMarker properties from MVC to WebFlux.** Some properties are Servlet-stack only. Check application properties for your exact version.

**Mistake 10 — Using JSTL or Spring JSP form tags in WebFlux.** Those tags depend on JSP/Servlet. Switch to a reactive engine's form binding or use MVC.

**Mistake 11 — Misconfiguring suffix/template path.** The resolver looks up the wrong file. Verify view name, loader path, and suffix.

**Mistake 12 — Template does not auto-escape HTML data.** User data can introduce XSS. Use an output format with auto-escaping.

**Mistake 13 — Allowing external users to edit templates.** Templates can access beans in the application context. Keep templates inside the trust boundary.

**Mistake 14 — Using a view engine for JSON APIs.** Templates are not codecs. Use ResponseBody and HttpMessageWriter for JSON/XML.

**Mistake 15 — Expecting forward: to behave like Servlet.** WebFlux does not support forward dispatches. Use routes, controllers, or redirects.

**Mistake 16 — Enabling both starter-web and starter-webflux while expecting Boot to run WebFlux.** Boot defaults to MVC when both are present. Verify the application type.

**Mistake 17 — Not testing cancellation.** Clients can close connections mid-render. Custom views and data sources must stop when the subscription is cancelled.

**Mistake 18 — Measuring only controller latency.** Total time also includes model resolution, template lookup, processing, and response writing. Measure each stage separately.

### 6.3. View Technology Selection Checklist

1. Does the application need to render HTML or only provide JSON APIs?
2. Is there a need to keep JSP/JSTL or Spring MVC form tags?
3. Does the template engine have official WebFlux integration?
4. Do the view or custom helpers call blocking synchronous APIs?
5. Does the engine offload blocking work or must the application do it?
6. Does the template buffer the entire output in memory?
7. Are chunked rendering or HTML fragments needed?
8. Does the model contain infinite Publishers or large lists?
9. Which FreeMarker properties are MVC-only?
10. Is HTML/JSON content negotiation needed?
11. Do templates have auto-escaping and stay within the trust boundary?
12. Are there integration tests with WebTestClient?
13. Have latency and memory been measured under concurrent rendering requests?
14. Does cancellation propagate when the client closes the connection?
15. Should the MVC UI and WebFlux API be split into two applications?

## 7. Self-Check Exercises

1. What does ViewResolver do? **Maps a logical view name to a concrete View.**
2. What does a WebFlux View's render method return? **Mono<Void>.**
3. What does ViewResolutionResultHandler do? **Resolves views and coordinates response rendering.**
4. Does @RestController automatically resolve view names? **No; strings are handled with ResponseBody semantics.**
5. How is a Mono in the model handled? **Resolved to a single value or empty before rendering.**
6. How is a Flux in a standard view model handled? **Collected into a List before rendering.**
7. Why is an infinite Flux unsuitable for a template model? **It never completes to produce a List and can hold unbounded data.**
8. Which view engines does Spring Boot support for WebFlux? **FreeMarker, Thymeleaf, and Mustache.**
9. Which resolver does Thymeleaf's WebFlux integration use? **ThymeleafReactiveViewResolver.**
10. Does Spring have FreeMarker integration for WebFlux? **Yes, via FreeMarkerView and FreeMarkerViewResolver.**
11. Which framework does the standard JSP resolver belong to? **Spring MVC on the Servlet stack.**
12. Where does InternalResourceViewResolver dispatch to? **Servlet resources, especially JSP.**
13. Does running WebFlux on Tomcat expose the Servlet API? **No; WebFlux uses a non-blocking adapter.**
14. Why are blocking APIs dangerous on the event loop? **They occupy worker threads and force other requests to wait.**
15. How do you isolate a blocking callable in Reactor? **Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic()).**
16. Does publishOn after a callable move the source to a new scheduler? **No; subscribeOn controls source subscription.**
17. What does FreeMarker .ftlh mean? **HTML output format with auto-escaping.**
18. Does WebFlux support forward: like Servlet? **No; use redirects or another route.**
19. How do you render multiple HTML fragments? **Collection<Fragment>, FragmentsRendering, or Flux<Fragment>.**
20. Can JSP be used directly as a native WebFlux view? **No; built-in JSP integration belongs to Spring MVC/Servlet.**

## 8. Key Takeaways and Official References

- WebFlux has its own view resolution via `ViewResolver`, `View`, and `ViewResolutionResultHandler`.
- `View.render` returns `Mono<Void>`, yet a custom view can still block if the engine calls synchronous APIs.
- Spring Boot supports FreeMarker, Thymeleaf, and Mustache for WebFlux; each engine has its own limitations.
- Thymeleaf supports reactive integration and chunked mode when max chunk size is configured.
- FreeMarker has WebFlux integration; some properties only support Spring MVC.
- JSP/JSTL, `InternalResourceViewResolver`, and `JstlView` belong to the Spring MVC/Servlet stack.
- Running WebFlux on Tomcat does not make Servlet API/JSP a native view.
- WebFlux resolves Mono model attributes to values and collects Flux into a List before standard view rendering.
- Use `FragmentsRendering` or `Flux<Fragment>` for HTML fragment streaming.
- Isolate blocking APIs with `subscribeOn(Schedulers.boundedElastic())`; do not block the event loop.
- Templates must be protected within the trust boundary and HTML data must be escaped.

Official references:

1. [Spring Framework 6.2 — View Technologies in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-view.html): Thymeleaf, FreeMarker, script views, HTML fragments, and JSON/XML views.
2. [Spring Framework 6.2 — View Resolution](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html): ViewResolutionResultHandler, reactive model attributes, content negotiation, and redirects.
3. [Spring Framework 6.2 — WebFlux Concurrency Model](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/new-framework.html): event-loop threads, blocking APIs, and schedulers.
4. [Spring Framework 6.2 — JSP and JSTL](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-view/mvc-jsp.html): InternalResourceViewResolver, JstlView, and JSP tag libraries on Servlet.
5. [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): template engine auto-configuration, static resources, and reactive servers.
6. [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): FreeMarker and Thymeleaf reactive properties, plus MVC-only limitations.
7. [Spring Framework 6.2 — FreeMarkerView Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/reactive/result/view/freemarker/FreeMarkerView.html): FreeMarker view implementation and render contract.
