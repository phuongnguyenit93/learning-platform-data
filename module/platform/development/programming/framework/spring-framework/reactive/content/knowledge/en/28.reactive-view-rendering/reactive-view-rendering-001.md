# View, ViewResolver, and Model Data in Spring WebFlux

## 1. Objectives

Spring WebFlux can return JSON for APIs or render HTML on the server using a template engine. When rendering HTML, the controller does not need to concatenate HTML strings manually. Instead, the controller prepares data in a **Model**, selects a view by logical name or creates a **Rendering** object, and delegates rendering to the **ViewResolver** and **View** mechanism.

Three core concepts:

- **Model:** a collection of named attributes and values used by the template when generating the response.
- **ViewResolver:** resolves a logical view name, such as products/list, into a concrete View object.
- **View:** renders the model into response content, typically HTML, though it can also be JSON/XML via HttpMessageWriterView.

Spring WebFlux keeps this workflow within the reactive model. A controller can return String, Mono<String>, Rendering, Mono<Rendering>, View, Model, or other model values. Resolution and rendering are composed into a reactive pipeline.

This lesson covers the view processing flow, passing data with Model and @ModelAttribute, choosing a template engine, configuring FreeMarker/Thymeleaf, content negotiation, redirects, form handling and validation, models containing Mono/Flux, HTML fragments, template security, and testing with WebTestClient. The complete example uses Java 17+, Spring Boot 3.5.x, and Spring Framework 6.2.x.

## 2. What Are View, ViewResolver, and Model?

### 2.1. Model

Model holds the data for a single request processing cycle. A controller can add attributes using Model:

```java
@GetMapping("/products")
public String list(Model model) {
    model.addAttribute("title", "Product catalog");
    model.addAttribute("products", productService.findAll());
    return "products/list";
}
```

In this example:

- products is the attribute name.
- productService.findAll() is the attribute value.
- products/list is the logical view name.

The template products/list.ftl can read title and products to build the HTML page.

Model is not a database, not a shared cache, and does not automatically persist across multiple requests. Each request has its own model. If you need to store data between requests, use a database, session, or an appropriate storage mechanism; do not treat Model as long-lived state storage.

Model is commonly accessed through these APIs:

| API | Role |
| --- | --- |
| org.springframework.ui.Model | Interface for adding, removing, and querying model attributes |
| ModelMap | Map with support for model operations |
| Map<String, Object> | Can be used as the model attribute collection in a controller signature |
| @ModelAttribute | Initializes, accesses, binds, or marks a model attribute |

### 2.2. View

View is responsible for turning the model into response content. For HTML, View typically uses a template engine such as FreeMarker or Thymeleaf.

At the framework layer, the View contract is reactive:

```java
Mono<Void> render(
        Map<String, ?> model,
        MediaType contentType,
        ServerWebExchange exchange);
```

View receives:

- A Map containing attribute names and their corresponding values.
- The MediaType selected for the response.
- The ServerWebExchange representing the current HTTP request/response.

The Mono<Void> completes when rendering finishes. If rendering fails, the error propagates through the reactive chain for WebFlux to handle.

### 2.3. ViewResolver

ViewResolver maps a logical view name to an actual View. For example, a controller returns products/list; the FreeMarker resolver locates the corresponding template and creates a FreeMarkerView.

Main contract:

```java
Mono<View> resolveViewName(
        String viewName,
        Locale locale);
```

A resolver can:

- Return a Mono containing a View if it can handle the view name.
- Return Mono.empty() if it does not handle that name so the next resolver can try.
- Emit an error if resolution genuinely fails.

A logical view name is not necessarily a file path. Prefix, suffix, and template loader rules depend on the resolver/template engine.

Example:

| View name | Template resolved |
| --- | --- |
| products/list | classpath:/templates/products/list.ftl |
| products/detail | classpath:/templates/products/detail.ftl |
| errors/not-found | classpath:/templates/errors/not-found.ftl |

The table above illustrates a FreeMarker configuration with template loader root classpath:/templates and suffix .ftl.

## 3. View Processing Flow in Spring WebFlux

Spring WebFlux uses DispatcherHandler following the front controller pattern. HandlerMapping locates a controller or functional route, HandlerAdapter invokes the handler, and HandlerResultHandler processes the return value.

General flow:

```text
HTTP request
    |
    v
DispatcherHandler
    |
    v
HandlerMapping
    |  finds matching handler
    v
HandlerAdapter
    |  invokes controller
    v
HandlerResult
    |  return value + model
    v
HandlerResultHandler
    |
    +-- ResponseEntityResultHandler
    |
    +-- ResponseBodyResultHandler
    |
    +-- ViewResolutionResultHandler
             |
             v
         ViewResolver
             |
             v
            View
             |
             v
      HTML / JSON / XML response
```

Result handlers are registered in the WebFlux configuration. Some important default orders:

| Result handler | Typically handled values | Default order |
| --- | --- | --- |
| ResponseEntityResultHandler | ResponseEntity | 0 |
| ServerResponseResultHandler | ServerResponse from functional endpoints | 0 |
| ResponseBodyResultHandler | @ResponseBody or @RestController | 100 |
| ViewResolutionResultHandler | CharSequence, View, Model, Map, Rendering, and other model attributes | Integer.MAX_VALUE |

This explains why a controller annotated with @RestController that returns a String writes the string to the response body instead of looking up a template. @RestController is a composed annotation combining @Controller and @ResponseBody.

If you want to return a view name to render HTML, use @Controller and do not annotate the method with @ResponseBody.

### 3.1. View Resolution vs. Response Body Encoding

Two flows that are often confused:

- **Response body:** @ResponseBody, @RestController, or ResponseEntity. The value is encoded into the response body by an HttpMessageWriter.
- **View rendering:** @Controller returns a view name, View, Model, Map, or Rendering. ViewResolver selects a View and renders the model.

API example:

```java
@RestController
public class ProductApiController {

    @GetMapping("/api/products")
    public Flux<Product> products() {
        return productService.findAll();
    }
}
```

HTML page example:

```java
@Controller
public class ProductPageController {

    @GetMapping("/products")
    public String products(Model model) {
        model.addAttribute("products", productService.findAll());
        return "products/list";
    }
}
```

Both can use the same ProductService, but the way they produce the response is different.

## 4. Return Value Types a Controller Can Return

ViewResolutionResultHandler handles several return value types. Important ones include:

| Return value | Meaning in an HTML controller |
| --- | --- |
| String / CharSequence | Logical view name to resolve |
| View | Use the View instance directly |
| Model or Map | Add attributes to the model; the view name may be derived from the request path |
| Rendering | Explicitly specify view, model, status, headers, or redirect |
| Non-simple POJO | Treated as a model attribute |
| @ModelAttribute on a method | Marks the return value as a model attribute |
| void or Mono<Void> | May use a default view name from the request path if the response has not been handled |
| Mono<String> | Upon completion, the String is interpreted as a view name in @Controller |
| Mono<Rendering> | Rendering is produced asynchronously and then used to render |

### 4.1. String as a View Name in @Controller

```java
@Controller
public class HomeController {

    @GetMapping("/")
    public String home() {
        return "home";
    }
}
```

Spring resolves the name home to a View. With FreeMarker and default configuration, the template may reside at src/main/resources/templates/home.ftlh or the configured extension.

If using @RestController:

```java
@RestController
public class HomeApiController {

    @GetMapping("/message")
    public String message() {
        return "Hello WebFlux";
    }
}
```

The response body is Hello WebFlux. No ViewResolver is invoked for this String because @RestController enables @ResponseBody.

### 4.2. Model or Map and Default View Name

A controller can return Model or Map:

```java
@GetMapping("/products")
public Model products() {
    return new ExtendedModelMap()
            .addAttribute("title", "Products");
}
```

When no view name is provided, WebFlux can select a default view name from the request path, stripping leading/trailing slashes. For GET /products, the default view name is usually products.

This style is concise, but it can be harder to read when routes and templates do not follow the same convention. In controllers with multiple branches, returning String or Rendering with an explicit view name is usually easier to maintain.

### 4.3. Rendering: Explicitly Specifying View and Model

Rendering is Spring WebFlux's dedicated API for scenarios that combine view and model. It is similar in concept to Spring MVC's ModelAndView, but uses WebFlux's own abstraction.

```java
@GetMapping("/products")
public Rendering products() {
    return Rendering.view("products/list")
            .modelAttribute("title", "Products")
            .modelAttribute("products", productService.findAll())
            .build();
}
```

Rendering.Builder can also set status, response headers, and cookies. For example:

```java
return Rendering.view("products/list")
        .modelAttribute("products", products)
        .status(HttpStatus.OK)
        .header("X-Page", "catalog")
        .build();
```

When the view needs to be built from a reactive result:

```java
@GetMapping("/products/{id}")
public Mono<Rendering> detail(@PathVariable long id) {
    return productService.findById(id)
            .map(product -> Rendering.view("products/detail")
                    .modelAttribute("product", product)
                    .build());
}
```

Do not use org.springframework.web.servlet.ModelAndView in a WebFlux controller. That is an API from the Spring MVC/Servlet stack; in WebFlux, use Rendering or other WebFlux-supported return types.

## 5. Working with Model

### 5.1. Adding Attributes

Model provides common operations:

```java
@GetMapping("/dashboard")
public String dashboard(Model model) {
    model.addAttribute("title", "Dashboard");
    model.addAttribute("username", "An");
    model.addAttribute("notifications", 3);
    return "dashboard";
}
```

Attribute names should be stable and clear. Use explicit names like product, products, currentUser, pageTitle instead of relying on automatically inferred class names.

Multiple attributes can be passed via Map:

```java
@GetMapping("/dashboard")
public Rendering dashboard() {
    Map<String, Object> attributes = Map.of(
            "title", "Dashboard",
            "username", "An",
            "notifications", 3);

    return Rendering.view("dashboard")
            .modelAttributes(attributes)
            .build();
}
```

### 5.2. Model Attribute Names

When calling addAttribute(value) without specifying a name, Spring uses a naming convention based on the object type. For example, Product may become product.

So that templates do not depend on inference rules, prefer:

```java
model.addAttribute("product", product);
model.addAttribute("products", products);
```

With method-level @ModelAttribute, the name can be specified explicitly:

```java
@ModelAttribute("pageTitle")
public String pageTitle() {
    return "Product catalog";
}
```

### 5.3. Shared Model Attributes in a Controller

A method annotated with @ModelAttribute at the method level is invoked before handler methods in the same controller. It is suitable for adding common data for views:

```java
@Controller
@RequestMapping("/products")
public class ProductPageController {

    @ModelAttribute("applicationName")
    public String applicationName() {
        return "Catalog";
    }

    @GetMapping
    public String list(Model model) {
        model.addAttribute("products", productService.findAll());
        return "products/list";
    }
}
```

Data can be shared across multiple controllers using @ControllerAdvice with @ModelAttribute methods. Only include genuinely shared data; do not turn this method into a place that runs unnecessary queries on every request.

### 5.4. Model, @ModelAttribute, and SessionAttributes

These three concepts have different scopes:

- Model: data for the current request, used when rendering the response.
- @ModelAttribute: annotation to initialize/access/bind a model object or mark a return value as a model attribute.
- @SessionAttributes: mechanism to retain certain model attributes across multiple requests in the session according to a declared workflow.

Do not confuse Model with session. If data must persist after the response completes, choose a session, database, or appropriate store.

## 6. @ModelAttribute and Form Data Binding

### 6.1. Binding Form Data to an Object

In an HTML controller, @ModelAttribute can bind form data, query parameters, URI path variables, and request headers into an object.

Example:

```java
@PostMapping("/products")
public String create(@ModelAttribute ProductForm form) {
    // form has received data from the request
    return "products/success";
}
```

Spring can look up an existing object in the model, retrieve it from the session if @SessionAttributes is configured, or create a new object using an appropriate constructor and then bind request data.

Form data and query parameters take precedence over URI variables and headers when names collide. A header is only used if it is not overridden by a request parameter with the same name.

### 6.2. Using a Dedicated Form DTO

Do not bind requests directly into a JPA entity or domain object with many sensitive fields. If the binder allows the client to modify every property, a user could send extra fields not shown on the form to alter state or permissions unintentionally.

Create a form DTO containing only the fields allowed to be updated:

```java
public class ProductForm {

    @NotBlank(message = "Name is required")
    @Size(max = 120, message = "Name must be at most 120 characters")
    private String name;

    @NotNull(message = "Price is required")
    @DecimalMin(value = "0.01", message = "Price must be at least 0.01")
    private BigDecimal price;

    public ProductForm() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }
}
```

If constructor binding is needed, you can use a record or explicit constructor and @BindParam to map request parameter names. If still using property binding, restrict allowed fields via WebDataBinder/@InitBinder where appropriate.

### 6.3. Validation and BindingResult

To run validation after data binding, use @Valid or @Validated:

```java
@PostMapping("/products")
public String create(
        @Valid @ModelAttribute("productForm") ProductForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return "products/form";
    }

    // Save data after validation succeeds.
    return "redirect:/products";
}
```

BindingResult must immediately follow the @ModelAttribute parameter it describes. Without BindingResult, binding errors are typically represented by WebExchangeBindException.

When using a reactive wrapper:

```java
@PostMapping("/products")
public Mono<String> create(
        @Valid @ModelAttribute("productForm") Mono<ProductForm> formMono) {

    return formMono
            .flatMap(form -> productService.create(form)
                    .thenReturn("redirect:/products"))
            .onErrorResume(WebExchangeBindException.class,
                    error -> Mono.just("products/form"));
}
```

In this case, errors are handled in the reactive chain. BindingResult is not used the same way with a Mono<ProductForm> parameter; if you need BindingResult as the next parameter, declare the model attribute without a reactive wrapper.

### 6.4. Method-Level @ModelAttribute

A method-level @ModelAttribute can return an object to add to the model:

```java
@ModelAttribute("categories")
public List<Category> categories() {
    return categoryService.findAll();
}
```

Or accept Model and add multiple attributes:

```java
@ModelAttribute
public void populatePage(Model model) {
    model.addAttribute("applicationName", "Catalog");
    model.addAttribute("supportEmail", "support@example.test");
}
```

These methods run before handler methods. They can be shared via @ControllerAdvice when needed across multiple controllers.

## 7. Reactive Data in Model

Spring WebFlux allows the model to contain reactive types such as Mono<T> or Flux<T>. Before rendering, AbstractView resolves asynchronous values into concrete values and updates the model.

Common rules:

- Mono<T> is resolved to a single value T, or no value if the publisher is empty.
- Flux<T> is collected into a List<T>.
- Other compatible reactive types are handled via ReactiveAdapterRegistry.

Example:

```java
@GetMapping("/products")
public String list(Model model) {
    model.addAttribute("products", productService.findAll());
    return "products/list";
}
```

Here findAll() returns Flux<Product>. Before FreeMarker renders, the Flux is collected into a List<Product> for the template to iterate over.

**Note:** putting a Flux into the Model does not mean the template receives each item as soon as it is emitted. View rendering waits to resolve model attributes; the Flux is collected into a List. Therefore, do not put an infinite publisher or a huge dataset into the model. For large data, paginate or limit the number of elements; for UIs that need to stream fragments, see the HTML fragments/SSE section.

## 8. ViewResolver and the View Selection Process

### 8.1. Resolver Chain

ViewResolutionResultHandler receives a logical view name and tries the configured ViewResolvers. A resolver can return a matching view or Mono.empty() so the next resolver handles it.

Resolvers are typically ordered. A specialized resolver can handle names by prefix, while a general resolver handles the remaining names.

Avoid creating multiple resolvers that accept every view name without clear precedence rules. When a template name cannot be found, check which resolver was selected, the prefix/suffix, and the template loader path.

### 8.2. ViewResolver and View Are Two Different Contracts

| Contract | Responsibility |
| --- | --- |
| ViewResolver | Takes a view name and Locale, resolves into a View |
| View | Takes model, content type, and ServerWebExchange and renders the response |
| ViewResolutionResultHandler | Connects controller return values with resolvers and views |
| Rendering | Explicit API for controllers to specify view and model |

A custom View must implement render returning Mono<Void>, support appropriate media types, and handle response content according to the reactive lifecycle. A custom ViewResolver typically implements resolveViewName returning Mono<View>.

### 8.3. Configuring ViewResolver

Spring WebFlux provides WebFluxConfigurer and ViewResolverRegistry:

```java
@Configuration
public class WebViewConfiguration implements WebFluxConfigurer {

    @Override
    public void configureViewResolvers(ViewResolverRegistry registry) {
        registry.freeMarker();
    }
}
```

The registry has shortcuts for FreeMarker and script templates, and also allows registering a custom ViewResolver:

```java
@Override
public void configureViewResolvers(ViewResolverRegistry registry) {
    ViewResolver resolver = customViewResolver();
    registry.viewResolver(resolver);
}
```

If using Spring Boot with a template engine starter, you can usually rely on auto-configuration. Only configure a resolver manually when you need control over prefix/suffix, ordering, default views, or custom integration. Avoid registering a duplicate resolver alongside auto-configuration.

## 9. Template Engines in Spring WebFlux

### 9.1. FreeMarker

Spring Framework provides built-in FreeMarker integration for WebFlux. Spring Boot supports auto-configuration for FreeMarker and looks for templates in src/main/resources/templates by default.

Strengths:

- Flexible text-based templates, usable for HTML and text formats.
- Directives for loops, conditionals, and macros.
- Integrated Spring binding macros for forms.
- Configurable template loader, settings, and shared variables.

Spring Framework manual configuration can use:

```java
@Configuration
public class WebConfiguration implements WebFluxConfigurer {

    @Override
    public void configureViewResolvers(ViewResolverRegistry registry) {
        registry.freeMarker();
    }

    @Bean
    public FreeMarkerConfigurer freeMarkerConfigurer() {
        FreeMarkerConfigurer configurer = new FreeMarkerConfigurer();
        configurer.setTemplateLoaderPath("classpath:/templates/freemarker");
        return configurer;
    }
}
```

With this configuration, the view name welcome resolves to classpath:/templates/freemarker/welcome.ftl.

In Spring Boot, if you use spring-boot-starter-freemarker, templates are auto-configured at src/main/resources/templates. You do not need to create FreeMarkerConfigurer manually unless customization is required.

### 9.2. Thymeleaf

Thymeleaf is a server-side HTML template engine. Spring WebFlux integration is maintained by the Thymeleaf project and typically uses these components:

- SpringResourceTemplateResolver.
- SpringWebFluxTemplateEngine.
- ThymeleafReactiveViewResolver.

Spring Boot provides auto-configuration for Thymeleaf when the corresponding starter is added. Templates are usually placed in src/main/resources/templates. Thymeleaf is a good fit when you want HTML templates that can be previewed in a browser with clean tag/attribute syntax.

### 9.3. Mustache and Other Engines

Spring Boot supports Mustache in reactive applications. Other template engines can be integrated through ViewResolver or ScriptTemplateConfigurer if they meet runtime requirements.

Spring Framework's script views rely on the JSR-223 Java scripting engine; the engine must support ScriptEngine and Invocable. This is a specialized extension path, not the default choice for new applications without a clear need.

### 9.4. Templates Must Not Be Edited by Untrusted Users

Views run within the application's internal trust boundary and can access the Spring application context. Do not allow end users to upload or edit server-side templates and render them directly without designing a safe sandbox. Templates must be controlled code, reviewed, and deployed with the application.

## 10. Complete Example: Spring Boot WebFlux + FreeMarker

This example builds a product list page, a detail page, and an add-product form. The service returns reactive types, the controller builds Model/Rendering, and FreeMarker renders HTML.

### 10.1. Project Structure

```text
src/
 +- main/
 |  +- java/demo/catalog/
 |  |  +- CatalogApplication.java
 |  |  +- Product.java
 |  |  +- ProductForm.java
 |  |  +- ProductCatalogService.java
 |  |  +- ProductPageController.java
 |  +- resources/
 |     +- templates/
 |        +- products/
 |        |  +- list.ftl
 |        |  +- detail.ftl
 |        |  +- form.ftl
 |        +- errors/
 |           +- not-found.ftl
 +- test/
    +- java/demo/catalog/
       +- ProductPageControllerTest.java
```

### 10.2. Dependencies

File build.gradle:

```groovy
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
    implementation 'org.springframework.boot:spring-boot-starter-freemarker'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Spring Boot manages the versions of Spring Framework, Reactor, FreeMarker, and related dependencies through dependency management. Do not override spring-webflux or freemarker individually unless there is a specific compatibility requirement.

### 10.3. Template Configuration

File src/main/resources/application.properties:

```properties
spring.application.name=webflux-view-demo
spring.freemarker.template-loader-path=classpath:/templates/
spring.freemarker.suffix=.ftl
spring.freemarker.charset=UTF-8
```

With Spring Boot auto-configuration, templates are loaded from src/main/resources/templates. If caching or advanced configuration is needed, check each property because not all FreeMarker features are supported on WebFlux.

### 10.4. Application Class

File CatalogApplication.java:

```java
package demo.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

### 10.5. Product Model

File Product.java:

```java
package demo.catalog;

import java.math.BigDecimal;

public record Product(long id, String name, BigDecimal price) {
}
```

Product is a read-only data type used in the view model.

### 10.6. Form DTO

File ProductForm.java:

```java
package demo.catalog;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class ProductForm {

    @NotBlank(message = "Name is required")
    @Size(max = 120, message = "Name must be at most 120 characters")
    private String name;

    @NotNull(message = "Price is required")
    @DecimalMin(value = "0.01", message = "Price must be at least 0.01")
    private BigDecimal price;

    public ProductForm() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }
}
```

ProductForm contains only the two fields the user is allowed to submit. The controller passes this DTO to the service; do not bind requests directly to an entity with administrative fields such as ownerId, status, or createdAt.

### 10.7. ProductCatalogService

File ProductCatalogService.java:

```java
package demo.catalog;

import java.math.BigDecimal;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ProductCatalogService {

    private final ConcurrentSkipListMap<Long, Product> products =
            new ConcurrentSkipListMap<>();

    private final AtomicLong ids = new AtomicLong(2);

    public ProductCatalogService() {
        products.put(1L, new Product(
                1L, "Keyboard", new BigDecimal("49.90")));
        products.put(2L, new Product(
                2L, "Mouse", new BigDecimal("19.50")));
    }

    public Flux<Product> findAll() {
        return Flux.defer(() -> Flux.fromIterable(products.values()));
    }

    public Mono<Product> findById(long id) {
        return Mono.defer(() -> Mono.justOrEmpty(products.get(id)));
    }

    public Mono<Product> create(ProductForm form) {
        return Mono.fromSupplier(() -> {
            long id = ids.incrementAndGet();

            Product product = new Product(
                    id,
                    form.getName().trim(),
                    form.getPrice());

            products.put(id, product);
            return product;
        });
    }
}
```

The example uses an in-memory concurrent map so it can run standalone. In production, replace this with a reactive repository/database. Creating a Product is wrapped in a Mono so it executes when the publisher is subscribed to.

### 10.8. Controller

File ProductPageController.java:

```java
package demo.catalog;

import java.util.List;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.reactive.result.view.Rendering;

import reactor.core.publisher.Mono;

@Controller
@RequestMapping("/products")
public class ProductPageController {

    private final ProductCatalogService productService;

    public ProductPageController(ProductCatalogService productService) {
        this.productService = productService;
    }

    @ModelAttribute("applicationName")
    public String applicationName() {
        return "Product Catalog";
    }

    @GetMapping
    public String list(org.springframework.ui.Model model) {
        model.addAttribute("products", productService.findAll());
        return "products/list";
    }

    @GetMapping("/new")
    public Rendering newForm() {
        return Rendering.view("products/form")
                .modelAttribute("productForm", new ProductForm())
                .build();
    }

    @PostMapping
    public Mono<Rendering> create(
            @Valid @ModelAttribute("productForm") ProductForm form,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            List<String> errors = bindingResult.getFieldErrors()
                    .stream()
                    .map(error -> error.getDefaultMessage() == null
                            ? "Invalid value"
                            : error.getDefaultMessage())
                    .toList();

            return Mono.just(Rendering.view("products/form")
                    .modelAttribute("productForm", form)
                    .modelAttribute("errors", errors)
                    .status(HttpStatus.BAD_REQUEST)
                    .build());
        }

        return productService.create(form)
                .thenReturn(Rendering.redirectTo("/products").build());
    }

    @GetMapping("/{id}")
    public Mono<Rendering> detail(@PathVariable long id) {
        return productService.findById(id)
                .map(product -> Rendering.view("products/detail")
                        .modelAttribute("product", product)
                        .build())
                .switchIfEmpty(Mono.just(
                        Rendering.view("errors/not-found")
                                .status(HttpStatus.NOT_FOUND)
                                .build()));
    }
}
```

Key points to note:

- @Controller allows String to be interpreted as a view name.
- @ModelAttribute("applicationName") adds shared data to the request model.
- list() adds Flux<Product> to the model. Before rendering, Spring resolves the Flux into a List<Product>.
- newForm() uses Rendering to select the view and pass the form object.
- create() places BindingResult right after @ModelAttribute to handle validation errors.
- On successful save, the controller returns a Rendering redirect so the browser navigates back to the list.
- detail() returns Mono<Rendering>, because product data is fetched asynchronously.

### 10.9. List Template

File src/main/resources/templates/products/list.ftl:

```text
<#ftl output_format="HTML" auto_esc=true>
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>${pageTitle!"Products"}</title>
</head>
<body>
    <h1>${applicationName}</h1>
    <p>Product list</p>

    <p><a href="/products/new">Add product</a></p>

    <#if products?has_content>
        <ul>
            <#list products as product>
                <li>
                    <a href="/products/${product.id?c}">
                        ${product.name}
                    </a>
                    -
                    ${product.price?string["0.00"]}
                </li>
            </#list>
        </ul>
    <#else>
        <p>No products yet.</p>
    </#if>
</body>
</html>
```

The template reads model attributes by name. FreeMarker's HTML output format with auto_esc=true escapes values printed into HTML. Do not use ?no_esc for user-submitted data without an appropriate sanitization step.

### 10.10. Form Template

File src/main/resources/templates/products/form.ftl:

```text
<#ftl output_format="HTML" auto_esc=true>
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Add product</title>
</head>
<body>
    <h1>Add product</h1>

    <#if errors?? && errors?has_content>
        <ul>
            <#list errors as error>
                <li>${error}</li>
            </#list>
        </ul>
    </#if>

    <form method="post" action="/products">
        <div>
            <label for="name">Product name</label>
            <input
                id="name"
                name="name"
                type="text"
                value="${(productForm.name)!''}">
        </div>

        <div>
            <label for="price">Price</label>
            <input
                id="price"
                name="price"
                type="number"
                min="0.01"
                step="0.01"
                value="${(productForm.price)!''}">
        </div>

        <button type="submit">Save</button>
    </form>

    <p><a href="/products">Back to list</a></p>
</body>
</html>
```

When validation fails, the controller returns the same form view along with the form data and error list. This prevents users from losing what they entered.

If the application enables Spring Security CSRF, the POST form must include the CSRF token as configured by Spring Security. With FreeMarker, you can use Spring binding macros or include the token in the template in a controlled way; do not disable CSRF protection just to make the form work.

### 10.11. Detail Template

File src/main/resources/templates/products/detail.ftl:

```text
<#ftl output_format="HTML" auto_esc=true>
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>${product.name}</title>
</head>
<body>
    <h1>${product.name}</h1>
    <p>Product ID: ${product.id?c}</p>
    <p>Price: ${product.price?string["0.00"]}</p>
    <p><a href="/products">Back to list</a></p>
</body>
</html>
```

### 10.12. 404 Template

File src/main/resources/templates/errors/not-found.ftl:

```text
<#ftl output_format="HTML" auto_esc=true>
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Not found</title>
</head>
<body>
    <h1>Product not found</h1>
    <p>The product does not exist or has been deleted.</p>
    <a href="/products">Back to list</a>
</body>
</html>
```

The controller sets status 404 in Rendering, so the template is still rendered while the response carries a Not Found status.

### 10.13. Running the Application

Run:

```bash
./gradlew bootRun
```

Open these URLs:

| URL | Result |
| --- | --- |
| http://localhost:8080/products | Product list |
| http://localhost:8080/products/new | Add-product form |
| http://localhost:8080/products/1 | Keyboard details |
| http://localhost:8080/products/999 | 404 page |

Submit the form using curl:

```bash
curl -i -X POST http://localhost:8080/products   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode "name=Monitor"   --data-urlencode "price=149.90"
```

A valid request receives a redirect response to /products. Values are stored in an in-memory service, so they are lost when the application restarts.

## 11. Testing View Rendering with WebTestClient

WebTestClient can verify status, headers, and HTML content without a browser.

File ProductPageControllerTest.java:

```java
package demo.catalog;

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ProductPageControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void rendersProductList() {
        client.get()
                .uri("/products")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.TEXT_HTML)
                .expectBody(String.class)
                .value(html -> {
                    assertTrue(html.contains("Product Catalog"));
                    assertTrue(html.contains("Keyboard"));
                    assertTrue(html.contains("Mouse"));
                });
    }

    @Test
    void invalidFormReturnsRenderedFormWithErrors() {
        client.post()
                .uri("/products")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "")
                        .with("price", "0"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.TEXT_HTML)
                .expectBody(String.class)
                .value(html -> {
                    assertTrue(html.contains("Name is required"));
                    assertTrue(html.contains("Price must be at least 0.01"));
                });
    }

    @Test
    void validFormRedirectsToProductList() {
        client.post()
                .uri("/products")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Monitor")
                        .with("price", "149.90"))
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().value(
                        "Location",
                        location -> assertTrue(location.endsWith("/products")));
    }

    @Test
    void missingProductUsesNotFoundView() {
        client.get()
                .uri("/products/999999")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().isNotFound()
                .expectBody(String.class)
                .value(html ->
                        assertTrue(html.contains("Product not found")));
    }
}
```

Run:

```bash
./gradlew test
```

The tests verify view resolution, template rendering, form binding, validation, redirect, and 404 status. This is integration testing over a random-port HTTP server, which is more useful than only testing a controller method as an isolated Java method.

## 12. Content Negotiation: HTML, JSON, and XML

ViewResolutionResultHandler supports content negotiation. It compares the media types requested by the client against the media types supported by the Views, then picks a matching view.

By default, WebFlux inspects the Accept header to determine requested media types. You can customize this strategy with WebFluxConfigurer.configureContentTypeResolver, for example adding a query parameter-based strategy.

### 12.1. HttpMessageWriterView

To render a model as JSON or XML via view resolution, WebFlux provides HttpMessageWriterView. This view wraps an HttpMessageWriter or Encoder from spring-web.

Unlike FreeMarker/Thymeleaf, HttpMessageWriterView does not need a ViewResolver. It is registered as a default view; when the requested media type matches, the default view is selected.

Example with Spring Framework 6.2 and Jackson 2:

```java
@Configuration
public class JsonViewConfiguration implements WebFluxConfigurer {

    @Override
    public void configureViewResolvers(ViewResolverRegistry registry) {
        Jackson2JsonEncoder encoder = new Jackson2JsonEncoder();

        HttpMessageWriterView jsonView =
                new HttpMessageWriterView(encoder);

        jsonView.setModelKeys(Set.of("products"));
        registry.defaultViews(jsonView);
    }
}
```

When using Spring Framework 7 with Jackson 3, the corresponding encoder class is JacksonJsonEncoder. Use the encoder matching the Spring and Jackson versions in your dependency management.

setModelKeys specifies which model attributes the view is allowed to serialize. If unconfigured, the view determines suitable attributes based on count and HttpMessageWriter writability. When the model has multiple attributes, specifying keys makes the result explicit.

### 12.2. When Should You Use HttpMessageWriterView?

It fits when a controller wants to render the same model in multiple media types, such as HTML for browsers and JSON for other clients. However, if the endpoint is a pure REST API, @RestController and HttpMessageWriter are usually simpler.

Do not use an HTML template to build JSON by concatenating strings. Use HttpMessageWriter/Encoder for proper escaping, serialization, and Content-Type.

## 13. Redirect and Rendering

### 13.1. redirect: Prefix

You can return a view name with the redirect: prefix:

```java
@PostMapping("/save")
public String save() {
    return "redirect:/products";
}
```

UrlBasedViewResolver recognizes the redirect: prefix and creates a redirect to the remaining URL. redirect:/products is a path relative to the current application.

### 13.2. Rendering.redirectTo

A more explicit approach:

```java
@PostMapping("/save")
public Mono<Rendering> save() {
    return productService.save()
            .thenReturn(Rendering.redirectTo("/products").build());
}
```

Rendering.redirectTo also supports URI. Status or headers can be set on the builder when required by the contract.

### 13.3. No forward: in WebFlux

Unlike the Servlet stack, Spring WebFlux does not support FORWARD dispatch. The forward: prefix is not a valid view-forwarding mechanism in WebFlux. If you want to reuse data/views, call the service and pick the appropriate view within the same request or redirect the client to another URL.

## 14. HTML Fragments and HTML-over-the-Wire

Normally a request renders a single view with a single model. With HTMX or Hotwire Turbo, the server can return HTML fragments so the browser replaces part of a page.

Spring WebFlux supports:

- Collection<Fragment>.
- FragmentsRendering.
- Flux<Fragment> or a compatible publisher.
- FragmentsRendering with Flux<Fragment> to stream fragments over SSE.

Example:

```java
@GetMapping("/dashboard")
public FragmentsRendering dashboard() {
    return FragmentsRendering.fragment("dashboard/header")
            .fragment("dashboard/sidebar")
            .fragment("dashboard/content")
            .build();
}
```

Each fragment can have its own model and inherits the request's shared model attributes.

If you need to stream fragments over time:

```java
@GetMapping(
        value = "/updates",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<Fragment> updates() {
    return Flux.interval(Duration.ofSeconds(2))
            .map(index -> Fragment.create(
                    "dashboard/update",
                    Map.of("index", index)));
}
```

This is the right approach for HTML-over-the-wire. It differs from putting Flux<Product> in a regular Model: a Flux model attribute is collected into a List before rendering, whereas Flux<Fragment> is a dedicated return type for fragment rendering/streaming.

## 15. Error Handling and Error Pages

View rendering can fail because a template does not exist, the model lacks an expected attribute, template syntax has an error, or a data source emits an error. Distinguish between:

- View lookup errors: check the view name, prefix/suffix, and template loader.
- Rendering errors: check template syntax, null data, and data types.
- Business errors: handle with an exception handler or appropriate controller branch.
- Binding/validation errors: return the form with errors so the user can correct them.

You can use @ExceptionHandler in @Controller or @ControllerAdvice to return Rendering:

```java
@ControllerAdvice
public class PageExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public Rendering productNotFound(ProductNotFoundException error) {
        return Rendering.view("errors/not-found")
                .modelAttribute("message", "Product was not found")
                .status(HttpStatus.NOT_FOUND)
                .build();
    }
}
```

For application-wide errors, Spring Boot provides WebExceptionHandler and supports error views by HTTP status code under the error directory. You can provide templates for 404, 5xx, or a default error. When machine-readable responses are needed, consider ProblemDetail/application/problem+json instead of an HTML page.

Never return stack traces, SQL, internal paths, or secrets in an error model shown to users.

## 16. Common Pitfalls

| Error | Cause | Fix |
| --- | --- | --- |
| Controller returns String but browser receives plain text | Controller uses @RestController or @ResponseBody | Use @Controller for view rendering |
| Template not found | Wrong view name, prefix, suffix, or template loader | Check view name and template location |
| Returns products/list.html but resolver appends .ftl | Extension included in view name while resolver configures suffix | Return logical name products/list |
| Model attribute missing in template | Wrong key or addAttribute not called | Use consistent model names and check model |
| Flux in model does not stream | AbstractView resolves Flux into List before rendering | Paginate or use Fragment/SSE if streaming is needed |
| View returns content type error | View media type does not support Accept | Check supported media types and default views |
| JSON view serializes unwanted attributes | Model keys not restricted | Configure HttpMessageWriterView.setModelKeys |
| Form validation does not return to form page | Missing BindingResult or unhandled exception | Place BindingResult immediately after @ModelAttribute |
| User can modify fields outside the form | Binding directly to domain object with too many properties | Use dedicated DTO, constructor binding, or allowedFields |
| Template prints raw HTML from input | Auto-escape disabled or no_esc used | Enable HTML escaping, sanitize by context |
| Using Model like a session | Confusing model scope | Use session/store if state must persist across requests |
| Using Servlet ModelAndView in WebFlux | Confusing MVC and reactive stack APIs | Use Rendering |
| Using forward: | WebFlux does not support forward dispatch | Use view directly or redirect |
| Template calls database/service directly | Putting business logic into the view | Load data in service/controller and pass via Model |
| Custom resolver is not called | Resolver ordering or view name condition mismatch | Check order and resolveViewName logic |
| Using user-uploaded templates | Templates can access beans/application context | Only render trusted, controlled templates |
| Putting infinite Flux in Model | View waits to resolve model before rendering | Use SSE/FragmentsRendering or suitable streaming API |

## 17. Performance and Security

### 17.1. Keep Templates Simple

Templates should focus on presentation. Database queries, remote service calls, business calculations, and authorization belong in services/controllers. Having templates call multiple data sources makes latency and errors hard to control.

### 17.2. Avoid Collecting Huge Datasets

WebFlux automatically resolves reactive model attributes before rendering. Flux<T> is collected into List<T>. If the list has millions of items, memory usage can spike.

Use pagination, limit data, or stream fragments when the UI truly needs incremental updates.

### 17.3. Escape Output by Context

HTML text, attributes, URLs, JavaScript, and CSS have different escaping rules. Do not use a single generic replacement for every context. Prefer the template engine's auto-escaping and avoid printing raw HTML from user data.

### 17.4. Do Not Expose Sensitive Domain Objects

Only put necessary fields into the Model. Do not pass password hashes, access tokens, internal flags, database entity lazy proxies, or objects with sensitive data to templates. Use clearly structured view models/DTOs.

### 17.5. Templates Are Trusted Code

Template engines can access beans or features of the application context. Do not allow external users to edit templates and render them with server privileges. Control template sources, review changes, and package templates as part of the application.

### 17.6. Caching and Observability

Template engines can cache compiled/parsed templates, depending on the engine and configuration. Check specific caching capabilities when running on WebFlux; for example, some FreeMarker cache features are not supported on the reactive stack. Monitor resolve/render time, template error counts, response size, and latency of model-producing publishers.

## 18. Implementation Checklist

Before finalizing HTML rendering in WebFlux, verify:

1. Controller uses @Controller if it needs to return view names.
2. No unintended @ResponseBody/@RestController is present.
3. Model attributes have clear names and contain only data needed by the template.
4. Logical view names match resolver prefix/suffix and template locations.
5. ViewResolver is registered once with clear ordering.
6. Return type is appropriate: String, View, Model, Map, or Rendering.
7. Rendering is used when view/model/status/headers must be specified explicitly.
8. Reactive data in the model is bounded; Flux is not infinite.
9. Forms use dedicated DTOs, validation, and BindingResult in the right position.
10. Data binding does not allow clients to modify sensitive fields.
11. Templates auto-escape HTML data.
12. Accept headers and default views are configured if JSON/XML via view rendering is needed.
13. Redirects use redirect: or Rendering.redirectTo; do not use forward:.
14. Templates contain no business queries or secrets.
15. Tests with WebTestClient cover HTML, status, validation, redirect, and error views.
16. Logs and metrics are checked to detect slow or failing template resolution/rendering.

## 19. API Selection Summary

| Need | API |
| --- | --- |
| Add data to the model | Model.addAttribute(name, value) |
| Bind form/query/path/header to object | @ModelAttribute |
| Add shared attributes before handler | Method-level @ModelAttribute |
| Select view by logical name | Return String in @Controller |
| Select view and model explicitly | Rendering.view(name).modelAttribute(...).build() |
| Redirect | redirect:/path or Rendering.redirectTo(path) |
| Register resolver | WebFluxConfigurer.configureViewResolvers |
| Resolve view name | ViewResolver.resolveViewName(name, locale) |
| Render view | View.render(model, contentType, exchange) |
| Render JSON/XML via view | HttpMessageWriterView |
| Render multiple HTML fragments | FragmentsRendering or Collection<Fragment> |
| Handle form validation | @Valid + BindingResult |
| Test HTTP and HTML | WebTestClient |

## 20. Official References

- [Spring Framework – DispatcherHandler and View Resolution](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): DispatcherHandler flow, HandlerResultHandler, ViewResolutionResultHandler, return value handling, reactive model attributes, redirects, and content negotiation.
- [Spring Framework – View Technologies](https://docs.spring.io/spring-framework/reference/web/webflux-view.html): Thymeleaf, FreeMarker, script views, HTML fragments, JSON/XML, and template trust boundary warnings.
- [Spring Framework – WebFlux Config](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): WebFluxConfigurer, ViewResolverRegistry, default views, HttpMessageWriterView, and content type resolver.
- [Spring Framework – @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/modelattrib-method-args.html): form/query/path/header binding, validation, BindingResult, and reactive model attributes.
- [Spring Framework – @Controller](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann.html): differences between @Controller and @RestController.
- [Spring Framework – Rendering Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/view/Rendering.html): builder for view rendering, model attributes, status, headers, and redirects.
- [Spring Framework – ViewResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/view/ViewResolver.html): resolveViewName contract returning Mono<View>.
- [Spring Framework – View Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/view/View.html): render contract returning Mono<Void>.
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): auto-configured template engines and default template locations.
- [Spring Framework – Data Binding](https://docs.spring.io/spring-framework/reference/web/webflux/data-binding.html): constructor/property binding, WebDataBinder, and validation configuration.

## 21. Key Takeaways

**Model holds the request's data; ViewResolver finds the View from a logical name; View renders the data into a response.** In WebFlux, the entire process is integrated into the reactive lifecycle: controllers can return Mono<Rendering>, ViewResolver returns Mono<View>, and View.render returns Mono<Void>.

Use @Controller and String view names for simple pages; use Rendering when you need explicit control over view, model, status, or redirect. Use Model/@ModelAttribute to pass data and handle forms; keep DTOs narrow to prevent mass assignment. FreeMarker, Thymeleaf, and Mustache can all be used with WebFlux. If you need JSON/XML via view resolution, configure HttpMessageWriterView; for a pure REST API, @RestController is usually a better fit. Always remember that Mono/Flux in the Model are resolved before the template runs, and templates must be trusted code with proper output escaping.
