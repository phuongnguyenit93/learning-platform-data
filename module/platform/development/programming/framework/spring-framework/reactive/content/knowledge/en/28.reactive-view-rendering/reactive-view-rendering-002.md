# Returning View Names, Rendering, and Reactive Model Data in Spring WebFlux

## 1. What Is View Rendering in WebFlux?

Spring WebFlux does not only serve REST APIs returning JSON or binary data. An application can also render HTML on the server using a template engine such as Thymeleaf, FreeMarker, or Mustache. The controller prepares data, selects a logical view, and Spring combines the model with the template to produce the response.

Three concepts to distinguish:

- **View name** is the logical name of a template, for example \`catalog\` or \`account/profile\`. It is not an absolute file path.
- **View** is an object that knows how to render a model into a response. A \`ViewResolver\` looks up and creates a View from a view name.
- **Model** is a collection of data attributes that the template can access, such as \`pageTitle\`, \`featuredProduct\`, and \`products\`.

In WebFlux, the model can also hold reactive values like \`Mono<Product>\` or \`Flux<Product>\`. Spring resolves these publishers before invoking the view to render. As a result, a controller can pass data from a reactive repository without calling \`block()\` or manually calling \`subscribe()\`.

## 2. Processing Flow from Controller to Template

~~~text
HTTP request
     |
     v
HandlerMapping finds controller method
     |
     v
Controller returns String / Mono<String> / Rendering
and model attributes
     |
     v
ViewResolutionResultHandler
     |
     v
ViewResolver looks up View by logical view name
     |
     v
AbstractView resolves model publishers
     |
     +--> Mono<T> to T or no attribute
     |
     +--> Flux<T> is collected into List<T>
     |
     v
View / Thymeleaf / FreeMarker renders template
     |
     v
ServerHttpResponse writes HTML
~~~

Key steps:

1. WebFlux finds a handler for the request.
2. The controller returns a view name or an object describing the rendering.
3. \`ViewResolutionResultHandler\` receives the result and model.
4. \`ViewResolver\` instances are tried in turn to find a View that can handle the view name.
5. Before rendering, \`AbstractView\` resolves reactive model attributes into concrete values.
6. The template engine reads the resolved model and produces the response.

View resolution is part of WebFlux result handling. In normal template rendering, the controller does not read HTML files or concatenate response strings itself.

## 3. View Name Is a Logical Name, Not a File Name

A controller can return a String to select a view:

~~~java
@Controller
public class CatalogController {

    @GetMapping("/catalog")
    public String catalog() {
        return "catalog";
    }
}
~~~

With Spring Boot's default Thymeleaf configuration active, the name \`catalog\` is typically mapped to the template:

~~~text
src/main/resources/templates/catalog.html
~~~

Common default configuration:

- Prefix: \`classpath:/templates/\`
- Suffix: \`.html\`
- View name: \`catalog\`
- Template: \`classpath:/templates/catalog.html\`

With subdirectories, a view name can be \`account/profile\`, corresponding to \`templates/account/profile.html\`.

Do not return a user-supplied filesystem path as a view name. View names should be chosen from logical values controlled by the application; constructing view names from arbitrary input can lead to unintended template access.

## 4. Common Return Value Types for Views

In annotated controllers, WebFlux supports several ways to represent a render result:

| Return value | Meaning |
| --- | --- |
| \`String\` or \`Mono<String>\` | Logical view name |
| \`View\` | Use the View instance directly |
| \`Model\` or \`Map<String, Object>\` | Add model attributes; the default view name may be derived from the request path |
| Object model attribute | Add the object to the model using a conventional name or the name from \`@ModelAttribute\` |
| \`Rendering\` or \`Mono<Rendering>\` | Select view, model, status, and headers in a single object |
| \`void\` or empty publisher in a view context | May use a default view name from the request path if the response has not been handled |

Example returning a view name with a model:

~~~java
@GetMapping("/catalog")
public String catalog(Model model) {
    model.addAttribute("pageTitle", "Product catalog");
    model.addAttribute("category", "Hardware");
    return "catalog";
}
~~~

You can return a reactive view name:

~~~java
@GetMapping("/catalog")
public Mono<String> catalog() {
    return Mono.just("catalog");
}
~~~

WebFlux unwraps reactive return values before handling the result. Therefore, \`Mono<String>\` in a view-rendering controller can supply the view name once the publisher emits a value.

If a handler returns only \`Model\` or \`Map\` without specifying a view name, WebFlux can select a default name based on the request path after stripping leading and trailing slashes. For example, a request to \`/catalog\` may select the \`catalog\` view. Return an explicit view name when the template path differs from the route or when you want clearer code.

## 5. Models Containing Reactive Values

A distinctive feature of view rendering in WebFlux is that the model can contain publishers. The controller does not need to wait for each value by blocking.

Example:

~~~java
@GetMapping("/catalog")
public Mono<String> catalog(Model model) {
    model.addAttribute("pageTitle", "Catalog");
    model.addAttribute("featuredProduct",
        productService.findFeatured());
    model.addAttribute("products",
        productService.findAll());

    return Mono.just("catalog");
}
~~~

In this example:

- \`pageTitle\` is a regular String.
- \`featuredProduct\` is a \`Mono<Product>\`.
- \`products\` is a \`Flux<Product>\`.
- The controller returns \`Mono<String>\` as the view name.

Before rendering, WebFlux resolves model publishers:

| Value in model | Value received by template |
| --- | --- |
| \`Mono<Product>\` emitting one Product | One Product |
| \`Mono.empty()\` | No corresponding attribute in the model |
| \`Flux<Product>\` with multiple items | A \`List<Product>\` containing the items |
| \`Flux.empty()\` | An empty list |
| Regular values like String, Integer, or DTO | Value kept as-is |

This mechanism is handled at the view layer rather than having the controller manually collect every Flux.

### 5.1. Mono in the Model

Use \`Mono<T>\` when an attribute represents a single result:

~~~java
model.addAttribute(
    "featuredProduct",
    productService.findFeatured()
);
~~~

The template can access the object after the Mono is resolved:

~~~html
<section th:if="\${featuredProduct != null}">
    <h2 th:text="\${featuredProduct.name}">Product name</h2>
</section>
~~~

If the Mono completes without emitting a value, that attribute is not added to the resolved model. Templates should check for the attribute's existence before reading nested properties.

### 5.2. Flux in the Model

Use \`Flux<T>\` when a service returns multiple elements:

~~~java
model.addAttribute("products", productService.findAll());
~~~

Before rendering, WebFlux collects the elements into a List. The template can iterate over it:

~~~html
<ul>
    <li th:each="product : \${products}">
        <span th:text="\${product.name}">Product name</span>
    </li>
</ul>
~~~

This is convenient for finite, bounded lists. It does not turn a regular HTML template into an infinite stream. If the Flux never completes, model resolution cannot finish to begin rendering the full view this way.

### 5.3. Do Not Block or Subscribe in the Controller

Do not do the following:

~~~java
Product product = productService.findFeatured().block();
model.addAttribute("featuredProduct", product);
return "catalog";
~~~

Also do not subscribe manually:

~~~java
productService.findAll().subscribe(
    products -> model.addAttribute("products", products)
);
return "catalog";
~~~

Both approaches break the reactive lifecycle: data may not be ready when rendering, errors do not propagate properly, and request cancellation no longer controls the subscription as expected.

Instead, place publishers directly into the model or compose them into a single publisher before returning:

~~~java
return productService.findFeatured()
    .map(product -> Rendering.view("catalog")
        .modelAttribute("pageTitle", "Catalog")
        .modelAttribute("featuredProduct", product)
        .build());
~~~

## 6. Errors, Empty Signals, and Cancellation During Model Resolution

Reactive models still follow Reactor rules:

- \`Mono.empty()\` creates no attribute in the model.
- \`Flux.empty()\` resolves to a list with zero elements.
- If a publisher emits an error, rendering fails and the error enters WebFlux's exception handling mechanism.
- If downstream cancels, subscriptions of publishers resolving the model can be cancelled according to the reactive lifecycle.

Do not convert every service error into an empty value just so the template still renders. If products fail to load due to a database error, turning the error into \`Mono.empty()\` can make the UI look like there are no products and hide the incident. Distinguish "no data" from "failed to load data".

If multiple data sources must all succeed together, combine them with \`Mono.zip\` and then build a Rendering. If part of the data is optional, handle empty/fallback intentionally before adding it to the model.

~~~java
return Mono.zip(
        productService.findFeatured(),
        categoryService.findVisible()
    )
    .map(tuple -> Rendering.view("catalog")
        .modelAttribute("featuredProduct", tuple.getT1())
        .modelAttribute("categories", tuple.getT2())
        .build());
~~~

This creates an explicit combination point when the controller needs a data snapshot to select the view. For independent model attributes, you can also put Mono/Flux directly in the model and let the view layer resolve them.

## 7. Rendering: Explicitly Selecting View and Model

\`Rendering\` is the rendering API for annotated controllers in Spring WebFlux. It plays a role similar to \`ModelAndView\` in Spring MVC while also supporting status and response headers.

Configurable parts:

- A view name or a View instance.
- Model attributes.
- HTTP status.
- HTTP headers.
- Redirect.

Basic example:

~~~java
@GetMapping("/catalog/rendering")
public Rendering catalogRendering() {
    return Rendering.view("catalog")
        .modelAttribute("pageTitle", "Catalog")
        .modelAttribute("category", "Hardware")
        .build();
}
~~~

You can return a reactive wrapper:

~~~java
@GetMapping("/catalog/rendering")
public Mono<Rendering> catalogRendering() {
    return productService.findFeatured()
        .map(product -> Rendering.view("catalog")
            .modelAttribute("pageTitle", "Catalog")
            .modelAttribute("featuredProduct", product)
            .modelAttribute("products", productService.findAll())
            .build());
}
~~~

\`Rendering.view("catalog")\` creates a builder for the view name. \`modelAttribute(name, value)\` adds an attribute to the model. An attribute's value can be a reactive publisher, which is resolved before rendering.

### 7.1. Adding Status and Headers

~~~java
@GetMapping("/catalog/rendering")
public Mono<Rendering> catalogRendering() {
    return productService.findAll().collectList()
        .map(products -> Rendering.view("catalog")
            .modelAttribute("pageTitle", "Catalog")
            .modelAttribute("products", products)
            .status(HttpStatus.OK)
            .header("X-Render-Mode", "rendering")
            .build());
}
~~~

In this example, \`collectList()\` is used intentionally to create a List before building the Rendering. You can pass a Flux directly as a model attribute if you want the View layer to resolve the publisher; collectList is not required in every case.

### 7.2. Using a Map to Add Multiple Model Attributes

~~~java
Map<String, Object> attributes = new HashMap<>();
attributes.put("pageTitle", "Catalog");
attributes.put("products", productService.findAll());

Rendering rendering = Rendering.view("catalog")
    .model(attributes)
    .build();
~~~

Common methods on the builder:

| Method | Effect |
| --- | --- |
| \`view(name)\` | Select logical view name |
| \`modelAttribute(name, value)\` | Add a model attribute with an explicit name |
| \`modelAttribute(value)\` | Add an attribute with an inferred name |
| \`model(map)\` | Add multiple attributes from a Map |
| \`modelAttributes(values...)\` | Add multiple objects with inferred names |
| \`status(status)\` | Select HTTP status |
| \`header(name, values...)\` | Add response header |
| \`headers(httpHeaders)\` | Add a set of response headers |
| \`build()\` | Build the Rendering |

Prefer explicit names with \`modelAttribute("products", ...)\` so the template and controller share a stable contract.

## 8. Redirecting with Rendering

When a controller needs to redirect, it can use the redirect builder:

~~~java
@GetMapping("/old-catalog")
public Rendering redirectCatalog() {
    return Rendering.redirectTo("/catalog").build();
}
~~~

The target path should be decided by the application. Do not pass user-supplied URLs directly into a redirect without validation, as this can create an open redirect.

Besides \`Rendering.redirectTo(...)\`, view resolvers support certain view name conventions such as \`redirect:/catalog\` depending on the resolver. Using Rendering makes redirect intent explicit in WebFlux code.

## 9. Distinguishing @Controller, @RestController, and @ResponseBody

This is a common mistake when starting with view rendering.

~~~java
@Controller
public class PageController {
    @GetMapping("/page")
    public Mono<String> page() {
        return Mono.just("catalog");
    }
}
~~~

In \`@Controller\`, a String is a logical view name if the method does not have \`@ResponseBody\`.

~~~java
@RestController
public class ApiController {
    @GetMapping("/api/message")
    public Mono<String> message() {
        return Mono.just("catalog");
    }
}
~~~

In \`@RestController\`, the String is written to the response body. \`@RestController\` includes \`@ResponseBody\` semantics; it does not select a template named catalog.

You can use \`@ResponseBody\` on a specific method inside a \`@Controller\` class when that method needs to return JSON or text:

~~~java
@Controller
public class MixedController {
    @GetMapping("/page")
    public String page() {
        return "catalog";
    }

    @ResponseBody
    @GetMapping("/api/status")
    public Mono<String> status() {
        return Mono.just("ok");
    }
}
~~~

Decide whether an endpoint renders HTML or returns an API body and choose the corresponding annotation. Do not rely on method names or String contents to guess how Spring handles it.

## 10. ViewResolver and View Technology Configuration

\`ViewResolver\` receives a logical view name and returns a \`View\` capable of rendering. An application can configure one or more resolvers; each resolver can support a different template engine or view convention.

Spring WebFlux provides \`WebFluxConfigurer.configureViewResolvers\` for customization:

~~~java
@Configuration
public class WebViewConfiguration implements WebFluxConfigurer {

    @Override
    public void configureViewResolvers(ViewResolverRegistry registry) {
        // Register a custom ViewResolver if the application needs one.
        // Example: registry.viewResolver(customResolver);
    }
}
~~~

With Spring Boot, supported template engines have auto-configuration. When the appropriate starter is added, templates are located by default in \`src/main/resources/templates\`.

Do not add \`@EnableWebFlux\` merely to customize part of a view resolver in a Spring Boot application. \`@EnableWebFlux\` switches the application to fuller manual control of WebFlux configuration and can disable some Boot customizations. Use \`WebFluxConfigurer\` if you only need to add configuration.

### 10.1. Thymeleaf

Thymeleaf is a server-side template engine commonly used with Spring. Spring Boot has auto-configuration for Thymeleaf in WebFlux. Thymeleaf's reactive integration uses components such as \`SpringWebFluxTemplateEngine\` and \`ThymeleafReactiveViewResolver\`.

HTML templates are usually placed at:

~~~text
src/main/resources/templates/catalog.html
~~~

Example:

~~~html
<!doctype html>
<html xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="\${pageTitle}">Catalog</title>
</head>
<body>
    <h1 th:text="\${pageTitle}">Catalog</h1>

    <section th:if="\${featuredProduct != null}">
        <h2>Featured</h2>
        <p th:text="\${featuredProduct.name}">Featured product</p>
    </section>

    <ul>
        <li th:each="product : \${products}">
            <span th:text="\${product.name}">Product name</span>
            <span th:text="\${product.price}">0.00</span>
        </li>
    </ul>
</body>
</html>
~~~

\`th:text\` writes content as HTML-escaped text. Avoid using \`th:utext\` with untrusted content because it inserts unescaped content into HTML.

Templates have access to beans in the application context through the template engine's integration mechanism. Therefore, only use templates inside the application's trust boundary; do not allow users or external sources to freely edit templates that have access to beans.

### 10.2. FreeMarker and Mustache

Spring WebFlux also supports FreeMarker and Mustache through their respective integrations. View resolver configuration depends on the template engine and dependencies on the classpath.

Spring Boot automatically looks for templates in the templates directory under default configuration. If you change the prefix, suffix, or template resolver, ensure controller view names match the new template paths.

Do not assume every feature of a template engine behaves identically between Servlet MVC and WebFlux. Check the reactive integration documentation when using specialized features.

## 11. Reactive Models and Template Streaming

An important point: a model containing \`Flux<T>\` does not mean the template automatically emits HTML item by item as upstream emits items.

With standard view rendering, Spring resolves multi-value publishers into a List before rendering. This means:

- The template receives a completed collection.
- The Flux source must complete to produce the full list.
- A very large Flux can consume significant memory.
- An infinite Flux is unsuitable as a model attribute for a full view render.

If you need to display a large list, paginate or limit the number of records:

~~~java
Flux<Product> products =
    productService.findPage(page, pageSize);

model.addAttribute("products", products);
~~~

If you need continuous UI updates over time, choose a streaming mechanism such as SSE, WebSocket, or HTML fragments. Do not use an infinite Flux as a model attribute for a standard template.

Spring WebFlux also supports HTML fragments so HTMX/Hotwire applications can update specific UI regions. The \`FragmentsRendering\` API or \`Flux<Fragment>\` can represent multiple fragments, each with its own model and optionally inheriting the request's shared model. This is a dedicated approach for HTML-over-the-wire.

## 12. Using Views to Return JSON/XML via Content Negotiation

View resolution is not limited to HTML. WebFlux provides \`HttpMessageWriterView\` to use available codecs such as the Jackson JSON encoder or XML encoder in the view layer.

Unlike standard template engines, \`HttpMessageWriterView\` does not need a ViewResolver to locate a template file. It is configured as a default view and selects a writer matching the requested media type.

Conceptual configuration example:

~~~java
@Configuration
public class WebViewConfiguration implements WebFluxConfigurer {

    @Override
    public void configureViewResolvers(ViewResolverRegistry registry) {
        // You can register a template resolver for HTML here.
        // You can add HttpMessageWriterView as a default view
        // if content negotiation for JSON/XML is needed.
    }
}
~~~

In typical REST APIs, \`@ResponseBody\` or \`ResponseEntity\` remains the most straightforward way to return JSON. Use \`HttpMessageWriterView\` when the application intentionally uses the same view resolution model for multiple representations.

## 13. WebFlux.fn: RenderingResponse for Functional Endpoints

Annotated controllers use \`org.springframework.web.reactive.result.view.Rendering\`. For WebFlux.fn functional endpoints, the corresponding API is \`RenderingResponse\` in the \`org.springframework.web.reactive.function.server\` package.

Example:

~~~java
Mono<RenderingResponse> renderCatalog(ProductService products) {
    return RenderingResponse.create("catalog")
        .modelAttribute("pageTitle", "Functional catalog")
        .modelAttribute("products", products.findAll())
        .build();
}
~~~

\`RenderingResponse\` is a subtype of \`ServerResponse\` with its own template name and model. It fits handler functions returning \`Mono<ServerResponse>\`.

Distinguish the two APIs:

| Application style | Rendering API |
| --- | --- |
| Annotated controller with \`@Controller\` | \`Rendering\` |
| WebFlux.fn functional endpoint | \`RenderingResponse\` |
| REST endpoint returning JSON | \`@ResponseBody\`, \`ResponseEntity\`, or \`ServerResponse.body(...)\` |

Do not confuse \`RenderingResponse\` with \`Rendering\`; they belong to two different programming models.

## 14. Complete Java 17+ Spring Boot WebFlux Demo

This demo uses Spring Boot 3.5.6, Java 17, and Thymeleaf. Two endpoints render the same template:

- \`GET /catalog\` returns \`Mono<String>\` as the view name and places reactive values in the Model.
- \`GET /catalog/rendering\` returns \`Mono<Rendering>\`, explicitly selecting view, model, status, and header.

### 14.1. Project Structure

~~~text
webflux-view-demo/
  build.gradle
  src/
    main/java/demo/
      DemoApplication.java
      Product.java
      ProductService.java
      CatalogController.java
    main/resources/
      application.properties
      templates/
        catalog.html
    test/java/demo/
      CatalogControllerTest.java
~~~

### 14.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Do not add \`spring-boot-starter-web\` to this demo because the goal is to run a reactive WebFlux application. If both MVC and WebFlux web starters are present, Spring Boot typically prefers auto-configuring MVC.

### 14.3. application.properties

~~~properties
spring.application.name=webflux-view-demo
spring.thymeleaf.cache=false
~~~

Spring Boot auto-configures the Thymeleaf view resolver. Templates are looked up in \`classpath:/templates/\` with the default suffix \`.html\`.

### 14.4. DemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 14.5. Product.java

~~~java
package demo;

import java.math.BigDecimal;

public record Product(
    long id,
    String name,
    BigDecimal price
) {
}
~~~

### 14.6. ProductService.java

~~~java
package demo;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ProductService {

    public Mono<Product> findFeatured() {
        return Mono.just(new Product(
            1L,
            "Mechanical Keyboard",
            new BigDecimal("79.90")
        ));
    }

    public Flux<Product> findAll() {
        return Flux.just(
            new Product(1L, "Mechanical Keyboard",
                new BigDecimal("79.90")),
            new Product(2L, "Wireless Mouse",
                new BigDecimal("25.50")),
            new Product(3L, "USB-C Hub",
                new BigDecimal("39.00"))
        );
    }
}
~~~

The service uses Mono for a featured product and Flux for a list. Hardcoded data is only used so the demo can run immediately; in real applications, replace it with an appropriate reactive repository or service.

### 14.7. CatalogController.java

~~~java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.reactive.result.view.Rendering;
import reactor.core.publisher.Mono;

@Controller
public class CatalogController {
    private final ProductService productService;

    public CatalogController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/catalog")
    public Mono<String> catalog(Model model) {
        model.addAttribute("pageTitle", "Catalog from view name");
        model.addAttribute(
            "featuredProduct",
            productService.findFeatured()
        );
        model.addAttribute(
            "products",
            productService.findAll()
        );

        return Mono.just("catalog");
    }

    @GetMapping("/catalog/rendering")
    public Mono<Rendering> catalogWithRendering() {
        return Mono.just(
            Rendering.view("catalog")
                .modelAttribute(
                    "pageTitle",
                    "Catalog from Rendering"
                )
                .modelAttribute(
                    "featuredProduct",
                    productService.findFeatured()
                )
                .modelAttribute(
                    "products",
                    productService.findAll()
                )
                .status(HttpStatus.OK)
                .header("X-Render-Mode", "rendering")
                .build()
        );
    }
}
~~~

The first method uses Model to add attributes and returns a logical view name. The second method uses Rendering to combine view, model, status, and response header. Both pass Mono/Flux directly into the model; WebFlux resolves them before Thymeleaf renders.

### 14.8. templates/catalog.html

~~~html
<!doctype html>
<html xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="\${pageTitle}">Catalog</title>
</head>
<body>
    <h1 th:text="\${pageTitle}">Catalog</h1>

    <section th:if="\${featuredProduct != null}">
        <h2>Featured product</h2>
        <p th:text="\${featuredProduct.name}">
            Featured product name
        </p>
        <p th:text="\${featuredProduct.price}">
            0.00
        </p>
    </section>

    <h2>All products</h2>
    <ul>
        <li th:each="product : \${products}">
            <span th:text="\${product.name}">Product name</span>
            <span th:text="\${product.price}">0.00</span>
        </li>
    </ul>
</body>
</html>
~~~

Attribute names in the template must match the names the controller adds to the model. Thymeleaf uses \`th:each\` to iterate over the list resolved by WebFlux from the Flux.

### 14.9. CatalogControllerTest.java

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CatalogControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void viewNameResolvesReactiveModelAttributes() {
        client.get()
            .uri("/catalog")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_HTML)
            .expectBody(String.class)
            .consumeWith(result -> {
                String html = result.getResponseBody();

                assertNotNull(html);
                assertTrue(html.contains("Catalog from view name"));
                assertTrue(html.contains("Mechanical Keyboard"));
                assertTrue(html.contains("Wireless Mouse"));
                assertTrue(html.contains("USB-C Hub"));
            });
    }

    @Test
    void renderingSelectsViewAndAddsResponseHeader() {
        client.get()
            .uri("/catalog/rendering")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_HTML)
            .expectHeader()
            .valueEquals("X-Render-Mode", "rendering")
            .expectBody(String.class)
            .consumeWith(result -> {
                String html = result.getResponseBody();

                assertNotNull(html);
                assertTrue(html.contains("Catalog from Rendering"));
                assertTrue(html.contains("Mechanical Keyboard"));
            });
    }
}
~~~

The first test verifies that the view name is resolved and the Mono/Flux model attributes have data when the template renders. The second test verifies that Rendering selects the right view, adds the header, and renders the model. WebTestClient checks the real HTML response rather than just inspecting the object returned by the controller.

### 14.10. Running the Application

In the project directory:

~~~bash
./gradlew bootRun
~~~

Or:

~~~bash
gradle bootRun
~~~

Open the two endpoints:

~~~bash
curl -i http://localhost:8080/catalog
curl -i http://localhost:8080/catalog/rendering
~~~

Both return HTML with the title and product list. The second endpoint includes an additional response header:

~~~http
X-Render-Mode: rendering
~~~

Run tests:

~~~bash
./gradlew test
~~~

The two tests exercise both the view name and Rendering paths, including resolving reactive model attributes and response headers. The demo needs no Thread.sleep, block, or manual subscribe in production code.

## 15. Common Pitfalls When Rendering Views in WebFlux

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Returning String from \`@RestController\` expecting Spring to find a template | String is written as response body | Use \`@Controller\` or \`@ResponseBody\` for its intended purpose |
| Confusing view name with file path | Resolver cannot find template | Return logical name matching configured prefix/suffix |
| Using wrong model attribute name | Template does not see the data | Use clear names in \`addAttribute\` and \`modelAttribute\` |
| Calling block to unwrap Mono | Blocks the reactive thread | Put the publisher in the model or compose publishers |
| Subscribing manually in the controller | Model may render before data arrives | Return publishers for WebFlux to manage |
| Expecting Mono.empty to create a null-valued attribute | Attribute does not appear in resolved model | Check for attribute existence in the template |
| Expecting Flux in model to stream HTML line by line | Flux is collected into a List before standard rendering | Paginate or use SSE/fragment streaming |
| Putting an infinite Flux in the model | View waits for publisher completion | Only use finite publishers for standard view models |
| Collecting a very large list into the model | High memory usage and longer render time | Paginate, limit record counts, or stream via another endpoint |
| Using Rendering in a functional endpoint | Wrong programming model | Use WebFlux.fn's RenderingResponse |
| Using RenderingResponse in an annotated controller | Wrong return value type | Use Rendering |
| Forgetting to configure a template engine | No matching ViewResolver | Add starter or register resolver |
| Adding @EnableWebFlux unnecessarily in Boot | May alter auto-configuration | Use WebFluxConfigurer for additional configuration |
| Returning view names from untrusted input | May select unintended templates | Select view names from an allow-list or internal logic |
| Allowing external sources to edit templates | Templates can access beans in application context | Keep templates within the application's trust boundary |
| Swallowing service errors as empty | UI appears empty and hides failures | Distinguish errors from empty results and handle explicitly |

## 16. View Rendering Design Checklist

Before finalizing a controller, check:

1. Does the endpoint render HTML or return a JSON/text body?
2. Does the controller use \`@Controller\` instead of accidentally using \`@RestController\`?
3. Does the view name match the ViewResolver's prefix/suffix rules?
4. Is the template file in the right directory?
5. Do model attribute names match what the template reads?
6. Are there Mono/Flux values in the model that need resolution?
7. Can a Mono be empty, and how does the template handle a missing attribute?
8. Is any Flux finite and small enough to be collected into a List?
9. Can publishers be passed directly into the model without blocking?
10. Is Rendering needed to set status/headers or pick views conditionally?
11. If using functional routes, was RenderingResponse chosen?
12. Are templates within the trust boundary and escaping data properly?
13. Have the HTML response, status, headers, and reactive data been tested?

| Need | Approach |
| --- | --- |
| Return template by name | \`return "catalog"\` or \`Mono.just("catalog")\` |
| Add model in controller | \`Model.addAttribute(name, value)\` |
| Model holds single async value | \`Mono<T>\` |
| Model holds async list | \`Flux<T>\` resolved into List |
| Select view, model, status, and headers | \`Rendering.view(...)\` |
| Redirect | \`Rendering.redirectTo(...)\` |
| Functional endpoint rendering template | \`RenderingResponse.create(...)\` |
| Configure ViewResolver | \`WebFluxConfigurer.configureViewResolvers(...)\` |
| Render JSON/XML via view layer | \`HttpMessageWriterView\` |
| Test HTML | \`WebTestClient\` |

## 17. Self-Check Questions with Answers

**Question 1.** Is a view name a template file path?

**Answer:** No. It is a logical name mapped by a ViewResolver to a View/template, for example \`catalog\` mapped to \`templates/catalog.html\` under default configuration.

**Question 2.** Which controller is appropriate for returning view names?

**Answer:** Typically a \`@Controller\` method without \`@ResponseBody\`. \`@RestController\` writes Strings to the response body.

**Question 3.** Can \`Mono<String>\` be a view name?

**Answer:** Yes. WebFlux resolves reactive return values and passes the emitted String to the view resolution handler.

**Question 4.** How is \`Mono<Product>\` in the model handled?

**Answer:** Spring resolves it to a Product if the Mono emits a value; if the Mono is empty, the attribute is absent from the resolved model.

**Question 5.** How is \`Flux<Product>\` in the model handled?

**Answer:** Spring collects the elements into a \`List<Product>\` before rendering a standard view.

**Question 6.** Why is an infinite Flux unsuitable for a standard template model?

**Answer:** The view needs to resolve the model before rendering; if the Flux does not complete, the list cannot finish for rendering this way.

**Question 7.** How does Rendering differ from a String view name?

**Answer:** Rendering packages the view together with model attributes, HTTP status, and headers; a String only selects a logical view name.

**Question 8.** Which Spring MVC API is Rendering in WebFlux similar to?

**Answer:** It plays a role similar to ModelAndView, but is an API designed for WebFlux.

**Question 9.** Does a WebFlux.fn functional endpoint use Rendering or RenderingResponse?

**Answer:** It uses RenderingResponse; Rendering is for annotated controllers.

**Question 10.** Should you call block or subscribe in a controller to prepare the model?

**Answer:** No. Put Mono/Flux into the model or compose publishers so WebFlux manages subscription, errors, and cancellation.

**Question 11.** If a controller returns only Model without a view name, which view might WebFlux choose?

**Answer:** A default view name may be derived from the request path after stripping leading/trailing slashes.

**Question 12.** What should you check when a template is not found?

**Answer:** Check the logical view name, prefix/suffix, templates directory, template engine dependency, and ViewResolver configuration.

## 18. Key Takeaways and Official Documentation

- A view name is a logical name; ViewResolver maps that name to a View.
- \`@Controller\` can return String or Mono<String> as a view name.
- \`@RestController\` and \`@ResponseBody\` write the body rather than selecting a template.
- Models can hold regular values or reactive publishers.
- Mono resolves to a single value or no attribute if empty.
- Flux is collected into a List before standard view rendering; do not use an infinite Flux for a template model.
- Rendering combines view, model, status, and headers in annotated controllers.
- RenderingResponse is the corresponding rendering API for WebFlux.fn.
- Spring Boot supports Thymeleaf, FreeMarker, and Mustache; default templates reside in \`src/main/resources/templates\`.
- Do not block or subscribe manually in controllers.
- Keep templates within the application's trust boundary and escape untrusted data.

Official documentation:

1. [Spring Framework Reference — DispatcherHandler and View Resolution](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): how ViewResolutionResultHandler selects views, handles return values, and resolves reactive model attributes.
2. [Spring Framework Reference — View Technologies](https://docs.spring.io/spring-framework/reference/web/webflux-view.html): Thymeleaf, FreeMarker, HTML fragments, JSON/XML, and view technologies.
3. [Spring Framework Javadoc — Rendering](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/view/Rendering.html): rendering API for annotated controllers.
4. [Spring Framework Javadoc — Rendering.Builder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/view/Rendering.Builder.html): modelAttribute, model, status, header, and build.
5. [Spring Framework Reference — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): ViewResolverRegistry and WebFluxConfigurer.
6. [Spring Framework Reference — Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): RouterFunction, ServerResponse, and the functional programming model.
7. [Spring Framework Javadoc — RenderingResponse](https://docs.spring.io/spring-framework/docs/6.2.17/javadoc-api/org/springframework/web/reactive/function/server/RenderingResponse.html): rendering response for WebFlux.fn.
8. [Spring Boot Reference — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): WebFlux auto-configuration and template engine support.
