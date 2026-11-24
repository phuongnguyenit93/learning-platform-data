# Configuring WebFlux-Compatible Template Technologies

**Context:** Spring Framework Reactive → **View Rendering**.

Spring WebFlux is not only used to build REST APIs returning JSON. A WebFlux application can also generate dynamic HTML on the server with a template engine, serve static files, or combine a reactive backend with a standalone SPA frontend. The rendering technology must integrate with Spring WebFlux's view mechanism and must not depend on the Servlet API in ways exclusive to Spring MVC.

Common options:

- **FreeMarker:** Spring Framework has direct FreeMarker view integration for WebFlux; suitable for HTML, email, and text templates. Some FreeMarker features are not fully supported in WebFlux.
- **Thymeleaf:** WebFlux integration maintained by the Thymeleaf project, with `SpringWebFluxTemplateEngine` and `ThymeleafReactiveViewResolver`.
- **Mustache:** Spring Boot provides auto-configuration for Mustache in WebFlux applications. Template logic is lightweight, with data prepared in the controller/service.
- **Static HTML and SPA:** WebFlux serves pre-built HTML, CSS, and JavaScript files; suitable for React, Vue, Angular, or standalone frontends.
- **Script templates or custom ViewResolver:** Spring Framework provides extension points for template libraries running on JSR-223 or an application-supplied `ViewResolver`.

`JSP` is a Servlet-stack technology, not a view option for WebFlux. WebFlux does not require the Servlet API, does not use `src/main/webapp`, and does not deploy in the traditional Servlet WAR model.

## 1. View Rendering Architecture in WebFlux

In annotated controllers, `DispatcherHandler` acts as the front controller. The controller provides the view name and model; `ViewResolutionResultHandler` finds the corresponding view; and the template engine renders HTML into the HTTP response.

```text
Browser request
      |
      v
WebFlux server adapter
      |
      v
DispatcherHandler
      |
      v
HandlerMapping / Controller
      |
      +---- model attributes
      |
      +---- logical view name: "home"
                    |
                    v
          ViewResolutionResultHandler
                    |
                    v
                ViewResolver
                    |
                    v
           FreeMarker / Thymeleaf /
                 Mustache
                    |
                    v
             Rendered HTML
                    |
                    v
              HTTP response
```

| Component | Role |
|---|---|
| `@Controller` | Handles requests and returns a view name or `Rendering` |
| `Model` / `Rendering` | Passes data to be displayed to the view |
| `ViewResolver` | Maps a logical name such as `home` to a View |
| `View` | Renders the model into the response |
| Template engine | Replaces expressions in the template with data |
| `DispatcherHandler` | Coordinates WebFlux handlers and result handlers |

`@RestController` includes `@ResponseBody`. If a method returns `String` in `@RestController`, the string is written to the response body; Spring does not treat it as a template name. To render HTML via view resolution, use `@Controller` or configure a view/response explicitly.

## 2. Supported Template Technologies

Spring Framework allows switching view technologies by configuring a `ViewResolver`. Spring Boot adds auto-configuration for popular engines when the corresponding dependencies are present.

| Technology | WebFlux Integration | Characteristics and Selection |
|---|---|---|
| FreeMarker | Built-in integration in Spring Framework | `FreeMarkerConfigurer` and resolver; HTML/text templates |
| Thymeleaf | Integration maintained by the Thymeleaf project | Reactive engine and resolver; HTML, forms, Spring EL |
| Mustache | Spring Boot auto-config supports WebFlux | Lightweight logic, model prepared in Java |
| Script template | Spring Framework support via JSR-223 | Requires a script engine and corresponding library |
| Custom ViewResolver | Can be registered directly | Used for custom engines or rendering rules |
| JSP/JSTL | Servlet stack | Not used directly as a WebFlux view engine |

Spring Boot 3.5 supports auto-configuration for FreeMarker, Thymeleaf, and Mustache. Under default configuration, templates are searched in `src/main/resources/templates`. For FreeMarker specifically, Boot documentation notes that not all features are supported with WebFlux; check specific features before using them.

### 2.1. FreeMarker

FreeMarker has direct integration in Spring WebFlux. Key components when configuring manually:

- `FreeMarkerConfigurer`: configures the template loader, settings, shared variables, and encoding.
- `FreeMarkerViewResolver`: maps view names to templates.
- `ViewResolutionRegistry.freeMarker()`: shortcut to register the resolver via `WebFluxConfigurer`.

For example, the view name `welcome` can resolve to `classpath:/templates/freemarker/welcome.ftl` if the loader path is configured that way.

FreeMarker fits applications needing HTML/text templates with expressions, conditionals, and loops. For HTML, prefer template formats with auto-escaping such as the `.ftlh` suffix; do not disable escaping arbitrarily.

### 2.2. Thymeleaf

Thymeleaf generates HTML from templates that can be opened directly in a browser to inspect static structure. WebFlux integration typically uses:

- `SpringResourceTemplateResolver`: locates templates in Spring resources.
- `SpringWebFluxTemplateEngine`: engine dedicated to Spring WebFlux.
- `ThymeleafReactiveViewResolver`: connects the engine to reactive view resolution.

WebFlux integration is maintained by the Thymeleaf project. When using Spring Boot, prefer the starter and auto-configuration compatible with Boot's Spring Framework version. If configuring manually, use the proper Spring integration library; do not plug Spring MVC's `ThymeleafViewResolver` into WebFlux.

Thymeleaf is useful when you need `th:text`, `th:each`, `th:if`, form binding, message bundles, and Spring EL. Templates should remain within the application's trust boundary.

### 2.3. Mustache and Script Templates

Mustache is a logic-light template engine. Templates focus on displaying data; conditionals and business logic belong in Java services/controllers.

```html
<h1>{{pageTitle}}</h1>
<ul>
  {{#books}}
    <li>{{title}}</li>
  {{/books}}
</ul>
```

Spring Boot provides auto-configuration for Mustache in WebFlux. Add the corresponding starter and place templates in the default directory. When complex conditionals, filtering, or calculations are needed, perform them in a service and pass simplified results to the model.

Spring Framework also supports script views for engines running on JSR-223. The engine must implement contracts such as `ScriptEngine` and `Invocable`. Configure using `ScriptTemplateConfigurer`, specifying the engine name, scripts, render function, and resolver.

Not every JavaScript engine is available in modern JDKs. Nashorn was removed from the JDK after Java 14; if you choose a JavaScript engine, you must add a compatible engine separately. For standard FreeMarker, Thymeleaf, or Mustache, prefer the built-in integrations.

## 3. Static HTML, SPA, and Server-Side Templates

Three presentation approaches can coexist:

| Approach | Backend Returns | When Appropriate |
|---|---|---|
| Server-side rendering (SSR) | HTML rendered from templates and models | Request-driven pages, forms, admin pages |
| Static frontend / SPA | Pre-built HTML/JS/CSS; APIs return JSON | Standalone frontend, browser-side routing |
| Hybrid | Static assets, templates, and JSON APIs | SSR landing pages combined with SPA screens |

WebFlux can serve static resources from the classpath:

```text
src/main/resources/
├── static/
│   ├── css/site.css
│   ├── js/app.js
│   └── images/logo.svg
├── templates/
│   └── home.ftlh
└── application.properties
```

Boot serves static content by default from `classpath:/static`, `classpath:/public`, `classpath:/resources`, and `classpath:/META-INF/resources`. Resources are usually mapped under `/**`. You can change the path with `spring.webflux.static-path-pattern` and change locations with `spring.web.resources.static-locations`.

Example:

```properties
spring.webflux.static-path-pattern=/assets/**
spring.web.resources.static-locations=classpath:/static/
```

When overriding `static-locations`, the new value replaces the default list. Boot also supports WebJars via the default `/webjars/**` path, which can be changed with `spring.webflux.webjars-path-pattern`.

Static resources are not rendered by FreeMarker or Thymeleaf. The browser receives the built files as-is. With an SPA, the backend can serve the frontend bundle and provide separate WebFlux APIs; if the frontend is hosted on another origin, configure CORS and authentication properly.

## 4. Controller Returning View Name and Model

A controller using view resolution typically looks like:

```java
@Controller
public class HomeController {

    @GetMapping("/")
    public String home(Model model) {
        model.addAttribute("pageTitle", "Home");
        return "home";
    }
}
```

`"home"` is a logical view name, not a file path. `ViewResolver` selects the matching template, such as `home.ftlh`, `home.html`, or `home.mustache` depending on the engine.

You can use `Rendering` to declare the view and model explicitly:

```java
@Controller
public class HomeController {

    @GetMapping("/about")
    public Rendering about() {
        return Rendering.view("about")
                .modelAttribute("pageTitle", "About")
                .modelAttribute("version", "1.0")
                .build();
    }
}
```

`Rendering` belongs to the `org.springframework.web.reactive.result.view` package. It lets you specify the logical view, model attributes, status, headers, and cookies. If a redirect is needed, you can use `Rendering.redirectTo("/home").build()`.

### 4.1. Models Can Contain Reactive Publishers

WebFlux allows models to contain reactive types such as `Mono` and `Flux`. Before rendering, the framework resolves these model attributes into concrete values:

- `Mono<T>` resolves to a single value, or no value if empty.
- `Flux<T>` is collected into a `List<T>` before the view renders.
- An erroring publisher causes rendering to fail along the request's error flow.

Example:

```java
@Controller
public class CatalogController {

    private final CatalogService catalogService;

    public CatalogController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/catalog")
    public Mono<Rendering> catalog() {
        return Mono.just(
                Rendering.view("catalog")
                        .modelAttribute(
                                "books",
                                catalogService.findAll())
                        .build());
    }
}
```

`catalogService.findAll()` returns `Flux<Book>`. WebFlux resolves the publisher in the model before rendering the template. This lets the service continue using reactive APIs without calling `block()` in the controller.

A `Flux` in the model is collected into a list. Do not put infinite publishers, SSE streams, or millions of items into the model of an HTML page; use pagination, limit results, or use a dedicated streaming endpoint. View rendering does not automatically turn a template into an infinite HTML stream.

## 5. Configuring Spring Boot with FreeMarker

For a Boot application, add the WebFlux starter and the FreeMarker starter. Boot auto-configures the appropriate view support when these dependencies are present.

Sample project structure:

```text
webflux-template-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/TemplateApplication.java
    │   ├── java/demo/HomeController.java
    │   └── resources/
    │       ├── application.properties
    │       ├── templates/home.ftlh
    │       └── static/css/site.css
    └── test/
        └── java/demo/HomePageIntegrationTest.java
```

### 5.1. pom.xml

Example using Java 17 and Spring Boot 3.5.16:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-template-demo</artifactId>
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
```

Spring Boot manages compatible FreeMarker versions through dependency management. Avoid upgrading FreeMarker or Spring Framework individually without checking Boot's compatibility matrix.

### 5.2. TemplateApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TemplateApplication {

    public static void main(String[] args) {
        SpringApplication.run(TemplateApplication.class, args);
    }
}
```

### 5.3. application.properties

```properties
spring.application.name=webflux-template-demo
spring.freemarker.template-loader-path=classpath:/templates/
spring.freemarker.suffix=.ftlh
spring.freemarker.charset=UTF-8
spring.freemarker.cache=true
server.port=8080
```

These properties specify where to locate templates, file suffix, encoding, and caching. In development, you can disable cache for easier template editing; in production, enable cache and package immutable templates with the application.

### 5.4. HomeController.java

```java
package demo;

import java.util.Map;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.reactive.result.view.Rendering;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class HomeController {

    @GetMapping("/")
    public Mono<Rendering> home() {
        Flux<Map<String, String>> books = Flux.just(
                Map.of("title", "Reactive Streams"),
                Map.of("title", "Spring WebFlux"),
                Map.of("title", "Reactive Systems"));

        return Mono.just(
                Rendering.view("home")
                        .modelAttribute(
                                "pageTitle",
                                "Reactive Library")
                        .modelAttribute("books", books)
                        .build());
    }
}
```

The controller uses `@Controller` to enable view resolution. It returns `Mono<Rendering>`; the model contains a `Flux` of books. WebFlux resolves `books` into a list before the template engine runs.

In a real application, replace `Flux.just` with a reactive service/repository. Keep queries in the service; the controller only composes publishers and selects the view. Do not call `block()` or `subscribe()` manually.

### 5.5. home.ftlh

Place the file at `src/main/resources/templates/home.ftlh`:

```html
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>${pageTitle}</title>
    <link rel="stylesheet" href="/css/site.css">
</head>
<body>
    <main>
        <h1>${pageTitle}</h1>
        <p>Available documents:</p>
        <ul>
            <#list books as book>
                <li>${book.title}</li>
            <#else>
                <li>No documents yet.</li>
            </#list>
        </ul>
    </main>
</body>
</html>
```

The `.ftlh` suffix uses FreeMarker's HTML output format and enables auto-escaping by default for this format. When a template receives user-entered data, you must still understand escaping contexts and avoid syntax that disables escaping unless the content is controlled.

### 5.6. site.css

Place the file at `src/main/resources/static/css/site.css`:

```css
body {
    font-family: system-ui, sans-serif;
    margin: 2rem auto;
    max-width: 48rem;
    line-height: 1.6;
    padding: 0 1rem;
}

h1 {
    color: #174a6e;
}

li {
    margin: 0.4rem 0;
}
```

CSS is served as a static resource. The template references `/css/site.css`; it does not need to go through FreeMarker.

## 6. Running and Verifying the Sample Application

From the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

Open `http://localhost:8080/` or call:

```bash
curl -i http://localhost:8080/
```

The response should have status 200 and media type `text/html`. The rendered HTML body should contain content similar to:

```html
<h1>Reactive Library</h1>
<p>Available documents:</p>
<ul>
    <li>Reactive Streams</li>
    <li>Spring WebFlux</li>
    <li>Reactive Systems</li>
</ul>
```

This is an illustrative body snippet; whitespace and line breaks may vary depending on the template renderer. The key values must appear in the rendered HTML.

## 7. Testing with WebTestClient

Tests should go through the WebFlux server and view resolver to catch template path, engine, codec, and media type errors. Example:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HomePageIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void rendersFreeMarkerTemplate() {
        client.get()
                .uri("/")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_HTML)
                .expectBody(String.class)
                .value(html -> {
                    assertThat(html)
                            .contains("<h1>Reactive Library</h1>");
                    assertThat(html)
                            .contains("Reactive Streams");
                    assertThat(html)
                            .contains("Spring WebFlux");
                    assertThat(html)
                            .contains("Reactive Systems");
                });
    }

    @Test
    void staticCssIsServed() {
        client.get()
                .uri("/css/site.css")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith("text/css")
                .expectBody(String.class)
                .value(css ->
                        assertThat(css).contains("font-family"));
    }
}
```

Run tests:

```bash
mvn test
```

The two tests verify that a request to `/` passes through the controller, view resolution, and FreeMarker, returning HTML with the rendered model; the CSS file is also served by WebFlux's static resource handler.

This is an integration test over the embedded reactive server. Unit tests that only call the controller directly will not prove that the template engine and static resource mapping are configured properly.

## 8. Manual FreeMarker Configuration Without Spring Boot

In a plain Spring Framework application, you need to register the view resolver and configurer:

```java
@Configuration
class FreeMarkerWebFluxConfiguration
        implements WebFluxConfigurer {

    @Override
    public void configureViewResolvers(
            ViewResolverRegistry registry) {
        registry.freeMarker();
    }

    @Bean
    FreeMarkerConfigurer freeMarkerConfigurer() {
        FreeMarkerConfigurer configurer =
                new FreeMarkerConfigurer();

        configurer.setTemplateLoaderPath(
                "classpath:/templates/freemarker");

        return configurer;
    }
}
```

The `welcome` template is looked up under the declared loader path, for example `classpath:/templates/freemarker/welcome.ftl` according to the resolver's suffix.

When using Spring Boot, the FreeMarker starter already provides WebFlux auto-configuration. Do not declare an extra manual resolver with duplicate functionality unless needed. If you want to modify Boot's configuration, inspect existing beans and use the proper extension points; in Boot, configuring properties or a customization bean is usually enough.

If adding a `WebFluxConfigurer` in Boot, do not add `@EnableWebFlux` just to register a view resolver. That annotation switches the application to manual WebFlux infrastructure management and causes Boot's WebFlux auto-configuration to back off. Use it only when you genuinely want to take full configuration responsibility.

## 9. Configuring Thymeleaf with WebFlux

In Spring Boot, you can use the starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-thymeleaf</artifactId>
</dependency>
```

Boot auto-configures the appropriate integration when the application runs WebFlux. Default templates reside under `src/main/resources/templates`. Example:

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="${pageTitle}">Home</title>
</head>
<body>
    <h1 th:text="${pageTitle}">Home</h1>
    <ul>
        <li th:each="book : ${books}"
            th:text="${book.title}">
            Book title
        </li>
    </ul>
</body>
</html>
```

For Spring Framework 6.x, Thymeleaf provides the corresponding Spring integration library, typically `thymeleaf-spring6`. Reactive integration uses `SpringResourceTemplateResolver`, `SpringWebFluxTemplateEngine`, and `ThymeleafReactiveViewResolver`. Do not use MVC's `SpringTemplateEngine`/`ThymeleafViewResolver` in place of the reactive integration.

If configuring manually, you must create the template resolver, reactive template engine, and reactive view resolver according to Thymeleaf's documentation for the version in use. Avoid declaring those beans yourself when Boot already auto-configures the same functionality.

## 10. Configuring Mustache with WebFlux

In Spring Boot, add:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mustache</artifactId>
</dependency>
```

Default templates are searched in `src/main/resources/templates`. A `home.mustache` file can contain:

```html
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{{pageTitle}}</title>
</head>
<body>
    <h1>{{pageTitle}}</h1>
    <ul>
        {{#books}}
            <li>{{title}}</li>
        {{/books}}
    </ul>
</body>
</html>
```

The controller prepares a model with the `pageTitle` and `books` keys. Mustache fits when you want minimal template logic; handle filtering, pagination, and calculations in Java services. With Boot configuration, check `spring.mustache.*` properties if you need to change prefix, suffix, or caching.

## 11. WebFlux.fn Can Also Render Templates

Besides annotated controllers, WebFlux supports functional endpoints. `ServerResponse.BodyBuilder` has a `render` method to return a view name with a model:

```java
@Bean
RouterFunction<ServerResponse> pageRoutes() {
    return RouterFunctions.route(
            GET("/welcome"),
            request -> ServerResponse.ok()
                    .render(
                            "home",
                            Map.of(
                                    "pageTitle",
                                    "Welcome page",
                                    "books",
                                    List.of(
                                            Map.of("title", "WebFlux"),
                                            Map.of("title", "Reactor")))));
}
```

This is a snippet requiring static imports and bean configuration. The view resolver and template engine remain beans in the same Spring WebFlux application context. The difference lies in how routes and handlers are declared, not in a separate template mechanism.

Do not mix functional handlers with annotated controllers merely to use another template engine. Choose the programming model based on application structure; view technologies can be shared as long as the corresponding resolver is registered.

## 12. Using Views for HTML and HttpMessageWriterView for JSON/XML

Template engines usually render HTML. If a model needs to be represented as JSON or XML, WebFlux provides `HttpMessageWriterView`, which uses an existing codec/`HttpMessageWriter` to write the model by media type.

Example configuring a default JSON view:

```java
@Configuration
class ViewNegotiationConfiguration
        implements WebFluxConfigurer {

    @Override
    public void configureViewResolvers(
            ViewResolverRegistry registry) {

        registry.freeMarker();

        Jackson2JsonEncoder encoder =
                new Jackson2JsonEncoder();

        registry.defaultViews(
                new HttpMessageWriterView(encoder));
    }
}
```

This is Framework configuration requiring the appropriate imports and Jackson codec. The default view is chosen when the request's media type matches. For public APIs, it is usually clearer to use separate `@RestController` endpoints for JSON and `@Controller` endpoints for HTML.

Do not return a DTO from `@RestController` and expect FreeMarker to render it. `@ResponseBody` instructs WebFlux to write the response with a message writer; view resolution is a different processing path.

## 13. Static Resources, WebJars, and Welcome Page

Boot WebFlux serves static resources from the classpath. Common default locations:

- `classpath:/static/`
- `classpath:/public/`
- `classpath:/resources/`
- `classpath:/META-INF/resources/`

If `index.html` exists in static locations, Boot can use it as the welcome page. If no static index is found, Boot checks for a template named `index`. The welcome page is a fallback; explicitly declared application routes may take precedence depending on `HandlerMapping` ordering.

WebJars package frontend libraries inside JARs. WebFlux can serve WebJars resources under `/webjars/**`. You do not need to manually copy library files into the static folder if you already use a WebJar artifact and matching mapping.

When a frontend builds a bundle, you can place the bundle in `src/main/resources/static`. With a CDN deployment or separate frontend server, configure CORS, CSP, and cookie domains according to the actual origin. Do not use a template engine merely to inline individual static JS/CSS files.

## 14. Forms, Validation, and Data in Templates

Templates can display form data, validation errors, and internationalized messages. Typical flow:

1. The controller receives a form request and binds data into a command object.
2. Bean Validation checks the input data.
3. The service executes business logic.
4. The controller puts data or errors into the model.
5. The view resolver renders the template with the completed model.

With FreeMarker, Spring provides macros supporting form binding and error display in `spring.ftl`. With Thymeleaf, attributes like `th:field`, `th:errors`, and `th:errorclass` support form integration. Exact capabilities and syntax depend on the template engine.

For WebFlux, reactive publishers can live in the model. If a form needs reference data, compose the service publishers and pass the results to the model; do not call `block()` to wait for data.

Security notes:

- Do not place full entities containing passwords, tokens, or internal fields into the model. Use view DTOs containing only the fields needed for display.
- Protect POST forms with CSRF when using Spring Security.
- Escape data according to HTML, attribute, URL, or JavaScript context.
- Do not render user-entered strings as template source.
- Restrict access to templates; templates can access beans in the application context.
- Do not allow external users to edit templates on the server without an appropriate sandbox and threat model.

## 15. Redirects, Errors, and HTML Error Pages

A controller can return a redirect view:

```java
@GetMapping("/old-home")
public Rendering redirect() {
    return Rendering.redirectTo("/").build();
}
```

Or return a logical view name with the `redirect:` prefix if supported by the resolver. A redirect does not render a new template; the server sends a redirect response and the browser issues the next request.

Spring Boot WebFlux has a default error handler. You can provide HTML error templates by convention under `templates/error`, such as `error/404.ftlh` or `error/5xx.ftlh` when using FreeMarker. Static error pages can be placed in `public/error`. Check exact conventions and paths for your Boot version.

For machine-to-machine APIs, return Problem Details or a clear JSON error response; do not return an HTML error page for an endpoint published as JSON. You can separate browser routes and API routes by path or content negotiation.

Never expose stack traces, SQL, tokens, internal paths, or sensitive data in production error templates. Log details on the server and show safe messages to users.

## 16. Reactive Rendering and Resource Limits

A view engine generates HTML before the server sends the response. Even though controllers/services can be reactive, the template rendering step still performs content processing work. Some guidelines:

- Do not call blocking JDBC/JPA directly on the event-loop to prepare the model.
- Use R2DBC or reactive clients when appropriate; if a blocking library must be used, offload work to an appropriate scheduler before rendering.
- Do not put an infinite `Flux` into the model because WebFlux collects multi-value publishers before rendering.
- Paginate long lists; limit the number of records put onto one page.
- Do not render huge files entirely into a single HTML string.
- Cache compiled templates in production if the engine supports it.
- Avoid initializing a new engine or resolver per request.
- Keep templates and models simple to reduce CPU and memory pressure.

If continuous UI updates are needed, use SSE/WebSocket or a dedicated streaming endpoint. Template rendering suits a complete HTML response or a finite fragment; it does not replace event streaming mechanisms.

## 17. Choosing a Technology by Requirement

| Requirement | Suitable Choice | Points to Note |
|---|---|---|
| Traditional server-rendered website | Thymeleaf or FreeMarker | Form, layout, and model integration |
| Lightweight template logic | Mustache | Prepare model in service/controller |
| Email or text templates | FreeMarker | Engine can be used outside HTTP views |
| Standalone SPA frontend | Static assets + WebFlux JSON API | CORS/authentication and frontend routing |
| Simple static page | `index.html` in static resources | No template engine needed |
| HTML/XML/JSON from one model by media type | View resolver + `HttpMessageWriterView` | Configure explicit content negotiation |
| Specialized template engine | Custom `ViewResolver` or `ScriptTemplateConfigurer` | Must manage concurrency and lifecycle |
| Existing JSP/JSTL | Spring MVC | JSP belongs to the Servlet stack, not WebFlux |

There is no single best template engine for every project. Choose based on layout needs, forms, template logic, team experience, version compatibility, and frontend deployment model.

## 18. Common Pitfalls

1. **Using `@RestController` and returning a template name.** The string is written to the response body; use `@Controller` or `Rendering`.
2. **Mistakenly using MVC's `ThymeleafViewResolver`.** WebFlux requires `ThymeleafReactiveViewResolver` and `SpringWebFluxTemplateEngine`.
3. **Adding only the engine library without a view resolver.** Check Boot auto-configuration or register a resolver manually.
4. **Placing templates in the wrong directory.** With Boot defaults, use `src/main/resources/templates`; if changing the loader path, update configuration in sync.
5. **Using JSP with WebFlux.** JSP requires the Servlet API; switch to Thymeleaf/FreeMarker/Mustache or use Spring MVC.
6. **Calling `block()` in a controller to obtain the model.** This blocks the event-loop; return `Mono`/`Flux` and let WebFlux resolve the model.
7. **Putting an infinite Flux into a template model.** The view renderer must collect the list; use SSE/WebSocket for continuous streams.
8. **Collecting very large datasets.** Paginate and limit results before rendering.
9. **Failing to distinguish logical view name from file path.** The controller returns the view name; the resolver combines prefix/suffix to find the file.
10. **Using `@ResponseBody` when intending to render a view.** This annotation routes the result to a message writer.
11. **Configuring two view resolvers that handle the same name.** Set explicit order, view name patterns, and prefix/suffix.
12. **Registering a resolver manually when Boot already auto-configures one.** This can create duplicate resolvers or conflicting configuration; pick one owner.
13. **Assuming every FreeMarker feature works identically to MVC.** Boot warns that some features are unsupported with WebFlux; verify specific features.
14. **Using Thymeleaf MVC integration in WebFlux.** Choose the right artifact and reactive resolver for your Spring version.
15. **Putting entities or secrets into the model.** Create view DTOs and expose only necessary fields.
16. **Disabling auto-escaping to fix broken HTML display.** Fix context-appropriate escaping instead of introducing XSS into templates.
17. **Letting external users edit templates on the server.** Templates can access context beans; keep templates within the trust boundary.
18. **Using overly broad static resource paths.** Check mappings so assets do not shadow API endpoints.
19. **Confusing static resources with templates.** Static files are served as-is; templates need a controller/view resolver.
20. **Not testing real HTTP responses.** Verify status, Content-Type, rendered body, and static assets with WebTestClient.
21. **Using a template engine to return JSON APIs.** Use message codecs or `@RestController`; only use `HttpMessageWriterView` when there is a content negotiation reason.
22. **Rendering errors with stack traces.** Use safe user messages and internal logging.
23. **Omitting CSRF protection for forms.** Check Spring Security configuration and tokens in forms.
24. **Running with both MVC and WebFlux starters while assuming the server is definitely reactive.** Boot typically prefers MVC when both starters are present; check the application type.
25. **Using configuration examples from another version.** View resolver APIs, template integrations, and Boot properties can change; use documentation matching your dependency versions.

## 19. Production Configuration Checklist

Before releasing a WebFlux UI, check:

- Is the application actually running WebFlux or Spring MVC?
- Is the UI a static SPA, server-side templates, or a hybrid model?
- Does the template engine support WebFlux and the current Spring version?
- Have the right starters/dependencies been added?
- Are `@Controller` and `@RestController` used with the right semantics?
- Do view names, resolvers, prefix/suffix, and template paths match?
- Does the model contain reactive publishers? Are there any infinite publishers or oversized lists?
- Are any blocking APIs called on the event-loop while preparing the model?
- Does HTML output have proper auto-escaping and XSS handling?
- Are templates inside the trust boundary? Does the model expose internal secrets/entities?
- Do forms have validation and CSRF protection?
- Are static resources, WebJars, and welcome pages mapped properly?
- Are error pages safe and appropriate for browsers/APIs?
- Are there integration tests via the embedded WebFlux server and WebTestClient?
- Are there dedicated tests for template not found, empty model, service errors, and static resources?
- Are template caching, memory, response size, and latency monitored in production?

**Key takeaway:** WebFlux supports dynamic HTML via view resolution. The controller returns a logical view name or `Rendering`, the model holds data, `ViewResolver` chooses the engine, and the template is rendered into an HTTP response. Spring Boot supports FreeMarker, Thymeleaf, and Mustache; Spring Framework also provides FreeMarker integration, script views, and custom resolvers. Reactive data can live in the model, though a `Flux` is collected into a list before rendering. Static SPA assets are served via resource handlers, whereas JSP belongs to the Servlet stack. Pick the right engine, starter, resolver, and lifecycle; verify escaping, model security, pagination, and test actual responses.

## References

- Spring Boot 3.5 — [Reactive Web Applications: static resources, template engines and WebFlux support](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html).
- Spring Framework 6.2 — [View Technologies in WebFlux: Thymeleaf, FreeMarker and script views](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-view.html).
- Spring Framework 6.2 — [DispatcherHandler and WebFlux view resolution](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html).
- Spring Framework 6.2 — [WebFlux Config: ViewResolverRegistry and FreeMarker configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html).
- Thymeleaf — [Thymeleaf + Spring integration](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html).
- Spring Framework — [Rendering Javadoc for WebFlux](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/result/view/Rendering.html).
- Spring Framework — [ServerResponse.BodyBuilder Javadoc: functional view rendering](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.BodyBuilder.html).
