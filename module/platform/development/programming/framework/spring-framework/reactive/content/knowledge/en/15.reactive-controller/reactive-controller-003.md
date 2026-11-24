# Paths, PathPattern, and @PathVariable in Spring WebFlux

## 1. Three Concepts to Keep Separate

When building a REST API, an endpoint usually looks like this:

~~~text
GET /api/tenants/acme/orders/42
~~~

Spring needs to solve three things:

1. **Request mapping**: choose the controller method that matches the HTTP method, URL path, and conditions such as header, query parameter, Content-Type, or Accept.
2. **PathPattern**: parse and match the structure of the path, including literals, wildcards, and URI template variables.
3. **@PathVariable**: take the value already captured from the URI template and put it into the method parameter, while also converting it to the declared Java type.

Example:

~~~java
@RestController
@RequestMapping("/api/tenants/{tenantId}/orders")
class OrderController {

    @GetMapping("/{orderId}")
    Mono<String> get(
            @PathVariable("tenantId") String tenantId,
            @PathVariable("orderId") Long orderId) {

        return Mono.just("tenant=" + tenantId + ", order=" + orderId);
    }
}
~~~

With the request:

~~~text
GET /api/tenants/acme/orders/42
~~~

Spring combines the class-level and method-level paths into:

~~~text
/api/tenants/{tenantId}/orders/{orderId}
~~~

After matching, the method receives:

- `tenantId = "acme"`
- `orderId = 42L`

`@PathVariable` does not query the database by itself and does not confirm that the order exists. It only takes a value from the URL and converts that value to the Java parameter type. Checking existence, access rights, and business rules belongs to later layers.

## 2. Request Mapping in a Controller

Spring WebFlux supports annotation-based controllers through `@Controller` and `@RestController`. `@RestController` is the way to combine a controller with the response body, which is suitable when a method returns HTTP data directly.

Commonly used mapping annotations:

| Annotation | HTTP method | Scenario |
| --- | --- | --- |
| `@GetMapping` | GET | Read a resource |
| `@PostMapping` | POST | Create a resource or perform a command |
| `@PutMapping` | PUT | Replace an entire resource according to the contract |
| `@PatchMapping` | PATCH | Partial update |
| `@DeleteMapping` | DELETE | Delete a resource |
| `@RequestMapping` | Can declare many conditions; if no method is specified, it does not restrict the HTTP method by default | General mapping, commonly used at class level |

You can combine conditions at the class level and the method level:

~~~java
@RestController
@RequestMapping("/api/v1/products")
class ProductController {

    @GetMapping
    Mono<String> list() {
        return Mono.just("product-list");
    }

    @GetMapping("/{productId}")
    Mono<String> detail(@PathVariable("productId") Long productId) {
        return Mono.just("product-" + productId);
    }

    @PostMapping
    Mono<String> create() {
        return Mono.just("created");
    }
}
~~~

The corresponding URLs:

| Request | Selected method |
| --- | --- |
| GET `/api/v1/products` | `list()` |
| GET `/api/v1/products/12` | `detail(12L)` |
| POST `/api/v1/products` | `create()` |

The class-level path creates a **shared prefix**; the method-level path describes the remainder. If there is no class-level mapping, the method can declare the full path.

**Note:** do not put multiple annotations from the `@RequestMapping` family on the same element and expect Spring to accumulate them. If it detects multiple mapping annotations on the same class or method, Spring logs a warning and uses only the first mapping. Use a single mapping annotation with the needed attributes.

Besides path and HTTP method, a mapping can also consider:

- `params`: a condition on query parameters.
- `headers`: a condition on request headers.
- `consumes`: the Content-Type the endpoint accepts.
- `produces`: the media type the endpoint can return, matched against Accept.

The topic of this lesson is paths and URI variables; the other conditions help prevent multiple handlers from unintentionally accepting the same kind of request.

## 3. What Is PathPattern?

**`PathPattern`** is a pre-parsed pattern model designed specifically for matching HTTP URL paths. Spring WebFlux uses `PathPattern` and `PathPatternParser` to process URI path patterns.

Instead of treating the URL as an arbitrary character string, WebFlux uses a path structure that has been split into segments. This supports efficient matching and also handles encoding and path parameters more appropriately.

A pattern can consist of:

- Literal segment: a fixed name such as `/orders`.
- Wildcard within a segment: `?` or `*`.
- URI variable: `{id}`.
- URI variable with a regex: `{id:[0-9]+}`.
- Catch-all: `**` or `{*path}` in permitted positions.

### 3.1. PathPattern Syntax Table

| Syntax | Meaning | Example match |
| --- | --- | --- |
| `orders` | Literal segment | `/orders` |
| `?` | Matches exactly one character in a segment | `/pages/t?st` matches `/pages/test` |
| `*` | Matches zero or more characters within a segment | `/files/*.pdf` matches `/files/report.pdf` |
| `**` | Matches zero or more path segments | `/resources/**` matches `/resources/a/b.txt` |
| `{id}` | Captures one segment and names it `id` | `/orders/{id}` matches `/orders/42` |
| `{id:[0-9]+}` | Captures one segment if the value satisfies the regex | `/orders/{id:[0-9]+}` matches `/orders/42` |
| `{*path}` | Captures zero or more remaining segments into one URI variable | `/files/{*path}` matches `/files/docs/a.pdf` |

### 3.2. Distinguishing Wildcards from URI Variables

`*` only helps the pattern match; it does not provide a variable name to retrieve in the method.

~~~java
@GetMapping("/files/*.pdf")
Mono<String> pdf() {
    return Mono.just("pdf");
}
~~~

In the example above, the handler can match a file name ending in `.pdf`, but there is no variable to retrieve the file name.

Conversely:

~~~java
@GetMapping("/files/{fileName}")
Mono<String> file(@PathVariable("fileName") String fileName) {
    return Mono.just(fileName);
}
~~~

`{fileName}` both matches one segment and captures the value to put into the method parameter.

### 3.3. A Regular URI Variable Captures Only One Segment

Pattern:

~~~text
/projects/{project}/versions
~~~

Match:

~~~text
/projects/spring/versions
~~~

Capture:

~~~text
project = spring
~~~

No match:

~~~text
/projects/spring/framework/versions
~~~

Because `{project}` represents only **one segment**, it does not include the `/` separator to capture multiple segments.

If you need to capture multiple segments, use an appropriate catch-all such as `{*path}` instead of trying to force a regular URI variable into a recursive path.

### 3.4. Catch-All and Valid Positions

Valid examples:

~~~text
/resources/**
/resources/{*path}
/**/info
/{*path}/resources
~~~

A pattern may have only **one catch-all instance** from the `**` or `{*path}` group. A catch-all must not be placed arbitrarily in the middle of a pattern.

Invalid examples:

~~~text
/resources/**/file.png
/resources/{*path}/file.png
/**/spring/**
~~~

If you want to start from a prefix and then take the entire remaining part of the path, the clear way is:

~~~java
@GetMapping("/resources/{*path}")
Mono<String> resource(@PathVariable("path") String path) {
    return Mono.just(path);
}
~~~

With the request:

~~~text
GET /resources/images/logo.png
~~~

The value captured by PathPattern is:

~~~text
/images/logo.png
~~~

The catch-all value may include the leading slash of the captured path portion. If the API needs a specific format, normalize and test it explicitly instead of assuming it behaves like a single segment.

## 4. Regex in a URI Variable

Syntax:

~~~text
/{variableName:regular-expression}
~~~

The regex constrains the accepted value right at the route-matching step. Example:

~~~java
@GetMapping("/orders/{orderNumber:[0-9]+}")
Mono<String> byNumber(
        @PathVariable("orderNumber") Long orderNumber) {
    return Mono.just("order=" + orderNumber);
}
~~~

Result:

| URL | Match result |
| --- | --- |
| `/orders/42` | Match; captures `orderNumber=42` |
| `/orders/0007` | Match; captures `orderNumber=0007`, which becomes the number 7 after conversion |
| `/orders/abc` | Does not match this pattern |
| `/orders/42-extra` | Does not match this pattern |

**A regex is a route-selection condition, not a replacement for all business validation.** It is useful for distinguishing the format of an endpoint and for preventing a handler from receiving data of the wrong shape.

Regex example for a slug:

~~~java
@GetMapping("/categories/{slug:[a-z0-9-]+}")
Mono<String> category(@PathVariable("slug") String slug) {
    return Mono.just("category=" + slug);
}
~~~

The regex only allows lowercase ASCII letters, digits, and hyphens according to the declared rules. If the domain allows Unicode or other characters, design the pattern according to the actual contract instead of using an overly narrow regex.

You can use multiple URI variables in one pattern. For example:

~~~java
@GetMapping("/artifacts/{name:[a-z-]+}/{version:[0-9]+}")
Mono<String> artifact(
        @PathVariable("name") String name,
        @PathVariable("version") int version) {
    return Mono.just(name + ":" + version);
}
~~~

In a Java annotation string, a regex must be escaped using Java syntax if it contains a backslash. For example, `\\d+` in a regex must be written `"\\\\d+"` in Java source. For simple numeric patterns, `[0-9]+` is usually more readable.

## 5. Which Pattern Does Spring Choose When Multiple Patterns Match?

A URL can match multiple mappings. For example:

~~~text
GET /orders/new
~~~

It can match all of:

~~~text
/orders/new
/orders/{orderId}
/orders/**
~~~

Spring uses `PathPattern`'s specificity comparison mechanism to choose the best mapping. Practical principles:

1. A fixed literal pattern is usually more specific than a URI variable.
2. A URI variable is usually more specific than a wildcard of the same scope.
3. A catch-all is ranked last.
4. If the comparison score is equal, the longer pattern is preferred according to the comparator.
5. When there are multiple catch-alls, the longer pattern is chosen according to the comparator rules.

Example:

~~~java
@RestController
@RequestMapping("/orders")
class OrderLookupController {

    @GetMapping("/new")
    Mono<String> createForm() {
        return Mono.just("new-order");
    }

    @GetMapping("/{orderId}")
    Mono<String> find(@PathVariable("orderId") String orderId) {
        return Mono.just("order=" + orderId);
    }

    @GetMapping("/**")
    Mono<String> fallback() {
        return Mono.just("fallback");
    }
}
~~~

With `GET /orders/new`, the literal pattern `/orders/new` is more specific than `/orders/{orderId}`. The `createForm()` handler is chosen. The pattern `/orders/**` is a catch-all, so it has lower priority.

**Do not rely on the declaration order of methods in a class to decide the handler.** Design clear patterns, avoid highly ambiguous routes, and test boundary URLs.

## 6. What Does @PathVariable Do?

`@PathVariable` binds a URI template variable in the mapping to a method parameter.

~~~java
@GetMapping("/owners/{ownerId}/pets/{petId}")
Mono<String> pet(
        @PathVariable("ownerId") Long ownerId,
        @PathVariable("petId") Long petId) {
    return Mono.just("owner=" + ownerId + ",pet=" + petId);
}
~~~

Request:

~~~text
GET /owners/12/pets/88
~~~

The values the method receives:

~~~text
ownerId = 12L
petId   = 88L
~~~

A method can have multiple `@PathVariable`s. Each variable must correspond to a name captured in the pattern after combining the class-level and method-level mappings.

### 6.1. Name It Explicitly

Recommended:

~~~java
@GetMapping("/{productId}")
Mono<String> get(@PathVariable("productId") UUID productId) {
    return Mono.just(productId.toString());
}
~~~

You can omit the name in the annotation when the URI variable name matches the Java parameter name and the code is compiled with parameter name information (for example, the Maven compiler with `-parameters` enabled):

~~~java
@GetMapping("/{productId}")
Mono<String> get(@PathVariable UUID productId) {
    return Mono.just(productId.toString());
}
~~~

For important APIs, declaring the name explicitly avoids depending on the compiler configuration or on a refactor that renames the Java variable.

### 6.2. Class-Level and Method-Level Variables

~~~java
@RestController
@RequestMapping("/tenants/{tenantId}/orders")
class TenantOrderController {

    @GetMapping("/{orderId}")
    Mono<String> get(
            @PathVariable("tenantId") String tenantId,
            @PathVariable("orderId") UUID orderId) {
        return Mono.just(tenantId + "/" + orderId);
    }
}
~~~

`tenantId` is in the class-level mapping but can still be injected into the method. `orderId` is in the method-level mapping.

There is no need to repeat `tenantId` in `@GetMapping`; Spring combines the URI templates of the two levels into one complete mapping.

## 7. Automatic Type Conversion of @PathVariable

The original URL value is text. Spring uses its conversion system to convert it to the Java type of the parameter.

Example:

~~~java
@GetMapping("/orders/{id}")
Mono<String> get(
        @PathVariable("id") UUID id) {
    return Mono.just(id.toString());
}
~~~

Some common types:

| Parameter type | Example path value | Result |
| --- | --- | --- |
| `String` | `abc` | `"abc"` |
| `int` / `Integer` | `42` | 42 |
| `long` / `Long` | `9000` | 9000L |
| `UUID` | `550e8400-e29b-41d4-a716-446655440000` | The corresponding UUID |
| `enum` | `PAID` | The enum constant if the name is valid |
| `LocalDate` | `2026-11-08` | Depends on the registered converter/formatter |

Simple types such as int, long, and Date are supported by default; you can register converters/formatters for other types. For Java time types or your own domain types, check the converters present in the configuration and test the actual format.

### 7.1. When Conversion Fails

Example:

~~~java
@GetMapping("/orders/{id}")
Mono<String> get(@PathVariable("id") Long id) {
    return Mono.just("id=" + id);
}
~~~

Request:

~~~text
GET /orders/not-a-number
~~~

The pattern matches because `{id}` accepts one segment. But Spring cannot convert `not-a-number` to `Long`, so parameter binding fails with a type mismatch error. The application usually maps this error to HTTP 400 according to the configured exception handling mechanism.

Contrast with a regex route:

~~~java
@GetMapping("/orders/{id:[0-9]+}")
Mono<String> get(@PathVariable("id") Long id) {
    return Mono.just("id=" + id);
}
~~~

With the URL `/orders/not-a-number`, the regex does not match. The request may end in a **404 route not found** instead of entering the handler and failing at conversion. The two approaches express two different contracts:

- No route match: the URL has no suitable endpoint.
- Route matches but conversion fails: the endpoint exists but the path input cannot be converted to the required type.

Do not use a regex just to turn a 400 into a 404 if that makes the API contract hard to understand.

### 7.2. Converter for Your Own Domain Type

Suppose the domain uses `OrderId` instead of a direct UUID:

~~~java
public record OrderId(UUID value) {
    public OrderId {
        if (value == null) {
            throw new IllegalArgumentException("value is required");
        }
    }
}
~~~

You can register a converter:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
            String.class,
            OrderId.class,
            value -> new OrderId(UUID.fromString(value))
        );
    }
}
~~~

Controller:

~~~java
@GetMapping("/orders/{id}")
Mono<String> get(@PathVariable("id") OrderId id) {
    return Mono.just("order=" + id.value());
}
~~~

The snippets above are **illustrative code spread across multiple files**; you need to import `UUID`, `Configuration`, `WebFluxConfigurer`, `FormatterRegistry`, and the related annotations. When registering a converter, test both valid and invalid values. Do not turn a parse error into a fake ID or a silent default value.

## 8. @PathVariable with a Map

When a method needs all URI template variables instead of declaring each parameter, you can use:

~~~java
@GetMapping("/tenants/{tenantId}/orders/{orderId}")
Mono<String> allVariables(@PathVariable Map<String, String> variables) {
    return Mono.just(variables.toString());
}
~~~

The Map is populated from the URI template variables of the mapping. For example, the request:

~~~text
GET /tenants/acme/orders/42
~~~

The Map contains:

~~~text
tenantId -> acme
orderId  -> 42
~~~

Using a `Map` is useful when an endpoint has many structural variables or a shared handler. However, if the method needs only one or two values, declaring each `@PathVariable("...")` is usually more readable and has better type safety.

Notes:

- `Map<String, String>` holds values as strings; if you need UUID/Long, convert them yourself or declare a parameter with a specific type.
- Do not rely on the entry order in the Map; if you need deterministic output, sort the keys before displaying.
- When the class-level mapping also has variables, the map can include variables from both the class-level and method-level prefixes.
- Do not use a Map to evade validation or authorization for path variables.

## 9. @PathVariable required and Optional Cases

By default, `@PathVariable` is **required**. When the mapping has `{id}`, Spring expects this variable to exist in the selected path.

You can use `required=false` or the `Optional` type when the handler is mapped with multiple patterns, some of which do not contain that variable:

~~~java
@GetMapping(path = {"", "/{id}"})
Mono<String> get(
        @PathVariable(name = "id", required = false)
        Optional<String> id) {

    return Mono.just(id.orElse("all"));
}
~~~

This is an illustrative example; you need to import `Optional` and Mono. The mapping has both an empty path and a path with an ID, so the parameter may be absent in the first branch.

**Setting `required=false` alone does not turn a mandatory path segment into an optional one.** If the only pattern is `/{id}`, a request without that segment still does not match the pattern. Define the route variants clearly before using Optional.

In REST design, if two operations differ significantly, two separate mappings are usually clearer than one method containing too many optional branches.

## 10. Path Variable vs. Query Parameter vs. Request Body

| Where data is passed | Example | Annotation | Used for |
| --- | --- | --- | --- |
| Path segment | `/orders/42` | `@PathVariable("id")` | Resource identity or route structure |
| Query string | `/orders?status=PAID` | `@RequestParam("status")` | Filters, pagination, search options |
| HTTP header | `X-Request-Id: abc` | `@RequestHeader` | Request metadata |
| Request body | JSON `{"status":"PAID"}` | `@RequestBody` | The operation's payload data |

Example of a search endpoint:

~~~java
@GetMapping("/orders/{customerId}")
Mono<String> orders(
        @PathVariable("customerId") UUID customerId,
        @RequestParam(name = "status", required = false) String status,
        @RequestParam(name = "page", defaultValue = "0") int page) {
    return Mono.just(
        "customer=" + customerId +
        ",status=" + status +
        ",page=" + page);
}
~~~

With the request:

~~~text
GET /orders/550e8400-e29b-41d4-a716-446655440000?status=PAID&page=2
~~~

`customerId` determines the resource scope; `status` and `page` are query conditions. Do not put every filter in the path just because `@PathVariable` is convenient.

## 11. Encoding, Slashes, and Semicolons

HTTP paths have their own encoding rules. Spring WebFlux uses `RequestPath`/`PathContainer` to work with a path that has been split into segments; the segments have decoded values available for access. Semicolon content is separated from the part used for path matching and can be accessed through the `@MatrixVariable` mechanism.

Some practical notes:

1. **Do not decode the @PathVariable value a second time yourself** if the framework already provides a decoded value. Double decoding can turn the data into content other than expected.
2. The `/` character separates segments. An ordinary `{id}` does not represent multiple segments.
3. If an ID can contain a slash, do not rely on `%2F` passing through every proxy, gateway, and server in the same way. Design the endpoint to use the catch-all `{*path}` or pass the data as a query parameter when appropriate.
4. Data containing reserved characters must be encoded correctly according to the URI component; when building URLs from a client, use a URI builder instead of manual string concatenation.
5. A semicolon path parameter is not the same as a query string; if the API needs matrix variables, declare and test them explicitly.

Matrix variable example (illustrative snippet):

~~~java
@GetMapping("/cars/{carId}")
Mono<String> car(
        @PathVariable("carId") String carId,
        @MatrixVariable(name = "color", required = false)
        String color) {
    return Mono.just("car=" + carId + ",color=" + color);
}
~~~

A URL can look like `/cars/42;color=red`. A matrix variable is a separate mechanism; do not confuse `color` with the URI variable `{carId}`.

### 11.1. Using a URI Builder on the Client Side

When WebClient calls an endpoint with a path variable, use a template and separate values:

~~~java
webClient.get()
    .uri("/api/orders/{id}", orderId)
    .retrieve()
    .bodyToMono(Order.class);
~~~

The `orderId` value is put into the URI template through the client's builder. This is clear and avoids manual string concatenation that causes reserved characters or whitespace to be encoded incorrectly.

## 12. WebFlux Does Not Automatically Suffix-Match Like Some Older MVC Configurations

In Spring WebFlux, `PathPattern` is used for path matching and **does not support suffix pattern matching** where `/person` automatically matches `/person.json`.

If you need to distinguish the response format, prefer:

- The HTTP `Accept` header and the `produces` attribute in the mapping.
- A query parameter if the API needs an explicit format selector.
- A separate endpoint when the two representations have genuinely different contracts.

Example:

~~~java
@GetMapping(path = "/products/{id}", produces = "application/json")
Mono<Product> json(@PathVariable("id") UUID id) {
    return service.find(id);
}
~~~

This is a structural example; you need to declare Product and the service. Do not rely on a file suffix in the URL as a default content negotiation mechanism.

## 13. Complete Spring Boot WebFlux Source Code

The following example can run standalone and illustrates:

- URI variables at the class and method level.
- UUID and long conversion.
- A regex constraint.
- A catch-all path variable.
- Retrieving all URI variables via a Map.
- A literal route that is more specific than a variable route.

Requirements: **Java 17+**, **Maven 3.9+**, and Spring Boot 4.1.2. When creating a real project, use a patch release supported by your organization and let the Boot BOM manage dependencies.

Structure:

~~~text
path-variable-demo/
  pom.xml
  src/main/java/example/pathdemo/PathVariableDemoApplication.java
  src/main/java/example/pathdemo/OrderPathController.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>path-variable-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

**src/main/java/example/pathdemo/PathVariableDemoApplication.java**

~~~java
package example.pathdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathVariableDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PathVariableDemoApplication.class, args);
    }
}
~~~

**src/main/java/example/pathdemo/OrderPathController.java**

~~~java
package example.pathdemo;

import java.util.Map;
import java.util.TreeMap;
import java.util.UUID;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/tenants/{tenantId}/orders")
public class OrderPathController {

    @GetMapping("/latest")
    public Mono<String> latest(
            @PathVariable("tenantId") String tenantId) {
        return Mono.just("tenant=" + tenantId + ";latest");
    }

    @GetMapping("/{orderId}")
    public Mono<String> byId(
            @PathVariable("tenantId") String tenantId,
            @PathVariable("orderId") UUID orderId) {
        return Mono.just(
                "tenant=" + tenantId + ";orderId=" + orderId);
    }

    @GetMapping("/by-number/{number:\\d+}")
    public Mono<String> byNumber(
            @PathVariable("tenantId") String tenantId,
            @PathVariable("number") long number) {
        return Mono.just(
                "tenant=" + tenantId + ";number=" + number);
    }

    @GetMapping("/files/{*path}")
    public Mono<String> filePath(
            @PathVariable("tenantId") String tenantId,
            @PathVariable("path") String path) {
        return Mono.just(
                "tenant=" + tenantId + ";path=" + path);
    }

    @GetMapping("/variables/{category}/{item}")
    public Mono<String> allVariables(
            @PathVariable Map<String, String> variables) {
        return Mono.just(new TreeMap<>(variables).toString());
    }
}
~~~

### 13.1. Running the Application

In the directory containing `pom.xml`:

~~~bash
mvn clean package
mvn spring-boot:run
~~~

In another terminal, call each endpoint:

~~~bash
curl -s http://localhost:8080/api/tenants/acme/orders/latest
curl -s http://localhost:8080/api/tenants/acme/orders/550e8400-e29b-41d4-a716-446655440000
curl -s http://localhost:8080/api/tenants/acme/orders/by-number/42
curl -s http://localhost:8080/api/tenants/acme/orders/files/manuals/install.pdf
curl -s http://localhost:8080/api/tenants/acme/orders/variables/books/42
~~~

**Expected response bodies**, in the order of the commands:

~~~text
tenant=acme;latest
tenant=acme;orderId=550e8400-e29b-41d4-a716-446655440000
tenant=acme;number=42
tenant=acme;path=/manuals/install.pdf
{category=books, item=42, tenantId=acme}
~~~

Explanation:

- `/latest` selects the literal mapping instead of `/{orderId}`.
- The UUID is converted from the URL segment to `java.util.UUID`.
- `by-number/{number:\\d+}` only matches digit-only segments, which are then converted to `long`.
- `files/{*path}` captures multiple segments and returns the path portion with the leading slash.
- The Map receives the URI variables from the class-level and method-level mappings; `TreeMap` keeps the output in a stable order.

### 13.2. Some Boundary Requests

| Request | Expected result per the demo mapping | Reason |
| --- | --- | --- |
| `GET /api/tenants/acme/orders/latest` | The latest handler | A literal is more specific than a variable |
| `GET /api/tenants/acme/orders/42` | The byId handler but UUID conversion fails | The route variable matches, the value is not a UUID |
| `GET /api/tenants/acme/orders/by-number/42` | The byNumber handler | The regex and the conversion are both valid |
| `GET /api/tenants/acme/orders/by-number/abc` | Does not match byNumber | The regex `[0-9]+` is not satisfied |
| `GET /api/tenants/acme/orders/files/a/b.pdf` | The filePath handler | The catch-all captures multiple segments |
| `POST /api/tenants/acme/orders/latest` | There is no corresponding POST mapping | The HTTP method does not fit |

The actual status still depends on the exception handler, the server, and the application configuration. Usually a non-existent route returns 404, an unsupported HTTP method returns 405, and a type conversion error is handled as a 400 request error. Test your application's status contract, and do not rely only on the controller's output.

## 14. Designing Understandable and Stable URLs

An API with clear paths usually has these characteristics:

- Use nouns for resources: `/orders`, `/customers`, `/products`.
- Use URI variables to identify resources: `/orders/{orderId}`.
- Use nested paths when the parent–child relationship is truly important: `/customers/{customerId}/orders/{orderId}`.
- Use query parameters for filtering, sorting, and pagination: `/orders?status=PAID&page=0`.
- Use the HTTP method to express the operation; avoid creating many different routes just to represent basic CRUD.
- Avoid overly broad catch-alls unless necessary; a catch-all route can make endpoint analysis and data protection harder.
- Do not put tokens, passwords, secrets, or sensitive data in the path, because URLs typically appear in access logs, browser history, tracing, and monitoring.
- Keep naming consistent: `orderId` rather than `id` in some places and `order_id` in others for the same meaning.

Example:

~~~text
GET    /api/orders/{orderId}
POST   /api/orders
PATCH  /api/orders/{orderId}
DELETE /api/orders/{orderId}
GET    /api/customers/{customerId}/orders
~~~

You do not need to nest URLs according to every database relationship. If an order can be accessed independently by orderId, `/orders/{orderId}` may be enough; the server must still check access rights by customer/tenant.

## 15. Security: PathVariable Is Not a Substitute for Authorization

A URI variable sent by the client is **untrusted input**. For example:

~~~text
GET /api/tenants/acme/orders/42
~~~

The fact that the controller receives `tenantId="acme"` and `orderId=42` does not mean the current user is allowed to view that order.

Common risks:

1. **IDOR/BOLA**: the client changes the ID from 42 to 43 and accesses someone else's resource.
2. **Tenant confusion**: the client changes the tenant in the URL itself to try to read another tenant's data.
3. **Path traversal**: a catch-all path is used to read files outside the permitted directory using sequences such as `../` or an equivalent encoded form.
4. **Input confusion**: multiple forms of encoding/normalization can lead to different interpretations between the proxy, the gateway, and the application.
5. **Log leakage**: sensitive IDs or secret data placed in the URL appear in access logs.

Mitigations:

- Authenticate the user at the security boundary.
- Obtain the permitted tenant from a trusted identity/authorization context; if the URL has a tenantId, verify that it matches the user's permissions.
- Check permissions at each resource/service, not just whether the route matches.
- For a catch-all file path, normalize the path, restrict it to the permitted root, and block traversal and symlink escape according to the storage design.
- Do not use a regex as an authorization mechanism; a regex only checks the shape of the route variable.
- Do not return internal details or filesystem paths in HTTP errors.

**PathPattern only helps choose the handler and capture data. It does not grant permissions to the caller.**

## 16. Common Mistakes and Fixes

| Mistake | Cause | How to handle it |
| --- | --- | --- |
| `@PathVariable` does not find a value | The annotation name differs from the URI variable name | Use an explicit `@PathVariable("orderId")` |
| The parameter name cannot be obtained when the annotation value is omitted | The compiler does not retain parameter names | Enable `-parameters` or declare the name explicitly |
| `Long`/`UUID` conversion error | The URL is not in the correct format | Check the contract, handle the type mismatch appropriately |
| Wanting one `{id}` to capture multiple segments | A regular URI variable captures only one segment | Use `{*path}` or design a query parameter |
| A catch-all placed in the middle of a pattern | PathPattern does not allow that structure | Place the catch-all at a valid start/end position and use only one |
| A static route is taken by a variable handler | The pattern design is unclear or the mapping is incorrect | Define a specific literal route and test specificity |
| The URL `/person.json` does not match `/person` | WebFlux does not use suffix pattern matching | Use Accept/produces or a clear route |
| Using @RequestParam to get a path segment | Confusing the query string with the URI template | Use @PathVariable |
| Using @PathVariable to get the query string | Wrong data location | Use @RequestParam |
| Calling a service with the tenantId from the URL without checking permissions | Cross-tenant access is possible | Authorize tenant/resource at the service/security layer |
| Using `%2F` to stuff a slash into a variable | Proxies/servers may handle encoded slashes differently | Design a catch-all or a query per the contract |
| Building client URLs by manual string concatenation | Easy to get encoding wrong | Use URI template/UriBuilder/WebClient |
| Using a regex to replace business validation | A regex only checks the path match | Validate data and permissions in the service |
| A catch-all file path accepts `..` | Risk of path traversal | Normalize, allowlist the root, check the canonical path |
| Assuming a path variable proves the resource exists | Binding only converts the URL value | Query the service/repository and handle NotFound separately |

## 17. How to Test Routes and PathVariable

A controller should have tests for **correct matches**, **non-matches**, **conversion**, **priority**, and **access rights**.

List of scenarios:

1. A literal route is chosen over a variable route when both match.
2. A URI variable receives the correct value at the class level and the method level.
3. UUID/Long are converted successfully.
4. A value that cannot be converted returns an error according to the HTTP contract.
5. A regex accepts only the declared format.
6. A catch-all captures multiple segments correctly.
7. The Map contains the required URI variables.
8. A wrong HTTP method does not invoke the handler.
9. A valid but non-existent ID is handled separately from a badly formatted ID.
10. A user without permission cannot change tenantId/orderId to access another resource.

You can use **WebTestClient** to test reactive endpoints over HTTP, without writing tests that depend on how the controller calls the method itself. An illustrative test snippet:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderPathControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void resolvesPathVariables() {
        client.get()
            .uri("/api/tenants/acme/orders/by-number/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("tenant=acme;number=42");
    }

    @Test
    void capturesCatchAllPath() {
        client.get()
            .uri("/api/tenants/acme/orders/files/manuals/install.pdf")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("tenant=acme;path=/manuals/install.pdf");
    }
}
~~~

This is an **illustrative test snippet** that requires importing JUnit, Spring Boot test, and WebTestClient; the corresponding test dependencies must be added. It assumes the controller from the previous example is already in the application context. When run against a real server, the test verifies the whole process of HTTP parsing, route matching, argument conversion, and response encoding.

## 18. Checklist for Debugging Mapping Errors

When a URL does not reach the right controller method, check in this order:

1. **HTTP method**: does the client send GET or POST? Does the mapping declare that method?
2. **Class-level prefix**: does the controller have a shared `@RequestMapping`?
3. **Method path**: does combining the prefix with the method path give the actual URL?
4. **PathPattern syntax**: are wildcards/catch-alls placed in the right position and number?
5. **Specificity**: is there any other literal/variable/catch-all mapping that also matches?
6. **URI variable name**: does the name in `{...}` match the name declared in `@PathVariable`?
7. **Conversion**: can UUID, Long, enum, or the custom type be parsed?
8. **Encoding**: does a proxy/gateway decode or normalize the path before it reaches WebFlux?
9. **Context path/base path**: does the called URL carry an extra prefix due to deployment/proxy?
10. **Security**: is the request blocked before reaching the controller?

Distinguish errors by stage:

~~~text
No suitable mapping
    -> usually 404

Mapping has the path but the HTTP method does not fit
    -> usually 405

Mapping is selected, but @PathVariable cannot be converted
    -> usually 400

Mapping and binding succeed, but the service does not find the resource
    -> domain NotFound, usually mapped to 404

The resource exists but the user has no permission
    -> 403 or a 404 policy to avoid revealing the resource
~~~

The final status must follow the application's exception handling and security policy; the diagram above helps narrow down the cause.

## 19. Self-Check

**Question 1.** Does the pattern `/orders/{id}` match `/orders/42/history`?

**No.** `{id}` captures only one segment; the URL has an extra `history` segment.

**Question 2.** To capture the entire remainder after `/files`, which pattern should you use?

`/files/{*path}`. The path variable can contain multiple segments and the captured part has a leading slash.

**Question 3.** Does `@PathVariable("orderId") UUID orderId` query the order in the database by itself?

**No.** Spring only converts the URI variable value to a UUID; the service/repository is what checks the resource.

**Question 4.** If both `/orders/new` and `/orders/{id}` match, which route is more specific?

`/orders/new`, because a literal segment is more specific than a URI variable.

**Question 5.** For `limit` or `page` in `/orders?page=2`, should you use PathVariable or RequestParam?

`@RequestParam`, because the data is in the query string.

**Question 6.** If a route has the regex `{id:[0-9]+}` and the URL sends `abc`, does the handler get entered and then fail with a Long conversion error?

Usually **not**. The regex makes the pattern not match from the start; the request is not selected for that handler.

**Question 7.** Can you omit the name in `@PathVariable`?

Yes, if the Java parameter name matches the URI variable name and the compiler retains parameter names; declaring the name explicitly is still easier to maintain.

**Question 8.** Does `@PathVariable(required=false)` make `/{id}` automatically match a URL without an id?

**No.** The pattern must allow that URL to match; optional only affects how the argument is bound when a valid mapping may not provide the variable.

**Question 9.** Is the path variable tenantId enough to prove the user belongs to that tenant?

**No.** You must authenticate and authorize the tenant/resource using a trusted identity.

**Question 10.** Does WebFlux automatically match `/person` with `/person.json`?

**No.** WebFlux does not support suffix pattern matching; use media type/Accept or a clear route.

## 20. Official References

- [Spring Framework — Mapping Requests in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html): RequestMapping, URI patterns, PathPattern, regex, specificity, and @PathVariable.
- [Spring Framework — Annotated Controllers in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html): controller annotations and method mapping.
- [Spring Framework — WebFlux Config](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): PathMatchConfigurer, RequestPath, and path matching configuration.
- [Spring Framework — Method Arguments in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html): the supported argument resolvers.
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html): converters and formatters for String request values.
- [Spring Framework — URI Building](https://docs.spring.io/spring-framework/reference/web/webflux/uri-building.html): UriComponentsBuilder, URI templates, and encoding.
- [Spring Framework — WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): validation for controller methods.
- [Spring Framework — WebFlux Security](https://docs.spring.io/spring-framework/reference/web/webflux/security.html): protecting endpoints and resources.

**Key takeaway:** **PathPattern** decides which URLs match a controller; **@PathVariable** takes the captured URI template variables and converts them to Java types. A regular variable occupies only one segment; a regex restricts the format; the catch-all `{*path}` takes multiple segments. Class-level and method-level mappings are combined, the more specific pattern takes priority, and validating data, finding resources, and authorization remain the application's responsibility.