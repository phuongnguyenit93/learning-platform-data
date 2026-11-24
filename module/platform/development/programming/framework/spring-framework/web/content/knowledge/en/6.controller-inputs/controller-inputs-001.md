# @PathVariable and @MatrixVariable in Paths — Spring MVC

> **Scope:** Spring MVC on the Servlet stack, for example Java 17+ and Spring Boot using `spring-boot-starter-web`. This guide explains how to extract data from the **URL path portion**, how to distinguish placeholder variables from per-path-segment parameters, and the conditions required for matrix variables to work safely.

## 1. Look at the URL before writing a controller

Consider three HTTP requests:

```text
GET /api/orders/42
GET /api/cars/7;color=red,green;year=2012
GET /api/owners/42;q=11/pets/21;q=22
```

- In `/orders/42`, `42` replaces the `{orderId}` placeholder in the route `/orders/{orderId}`: use `@PathVariable` to receive the order ID.
- In `/cars/7;color=red,green;year=2012`, the path segment has the primary value `7` and metadata `color`, `year` after the semicolon `;`: `@PathVariable` receives `7`; `@MatrixVariable` receives `color` and `year`.
- In `/owners/42;q=11/pets/21;q=22`, the name `q` appears in **two different segments**. `@MatrixVariable(pathVar = "...")` specifies the exact segment to read from.

| Annotation | Where is the data taken from? | Example | Value |
| --- | --- | --- | --- |
| `@PathVariable("orderId")` | The `{orderId}` variable in the path pattern | `/orders/42` | `42` |
| `@MatrixVariable("color")` | The `key=value` pair after `;` in a path segment | `/cars/7;color=red` | `red` |
| `@RequestParam("color")` | Query string after `?` | `/cars/7?color=red` | `red` |

**Remember:** `@PathVariable` identifies a resource or route component; `@MatrixVariable` describes a parameter attached to a **specific path segment**. They can be used together in the same handler method.

## 2. `@PathVariable`: mapping URI templates to Java parameters

### 2.1. Declaring routes and naming explicitly

```java
@RestController
@RequestMapping("/api")
class OrderController {

    @GetMapping("/orders/{orderId}")
    public String findOrder(@PathVariable("orderId") long orderId) {
        return "orderId=" + orderId;
    }
}
```

- `@GetMapping("/orders/{orderId}")` registers the URL pattern; curly braces declare a path variable.
- `@PathVariable("orderId")` extracts the value matching `{orderId}`. `long` instructs Spring to convert the string `42` to a number.
- `GET /api/orders/42` returns the body `orderId=42`.
- `GET /api/orders/abc` matches the route pattern but cannot convert `abc` to `long`, typically returning HTTP **400 Bad Request** due to a type conversion error.
- `GET /api/orders` is missing the required `/{orderId}` segment so it does not match the mapping above, typically returning HTTP **404 Not Found** if no other route exists.

You can omit the name in `@PathVariable` if the Java parameter name matches the route variable name and parameter name metadata is preserved at compile time (e.g., `-parameters`). Explicitly writing `@PathVariable("orderId")` avoids depending on compiler settings and improves readability when the Java name differs from the URI.

### 2.2. Extracting multiple variables and combining class/method mappings

```java
@RestController
@RequestMapping("/owners/{ownerId}")
class PetController {

    @GetMapping("/pets/{petId}")
    public String getPet(
            @PathVariable("ownerId") long ownerId,
            @PathVariable("petId") long petId) {
        return "ownerId=" + ownerId + ", petId=" + petId;
    }
}
```

The request `GET /owners/42/pets/21` returns `ownerId=42, petId=21`. `{ownerId}` at the class-level mapping is still read by the method as usual.

If you need to retrieve all URI template variables without declaring each parameter individually, you can use `@PathVariable Map<String, String> variables`; however, explicit names and concrete data types are usually easier to validate and maintain.

### 2.3. URI pattern constraints and data types

```java
@GetMapping("/versions/{version:v[0-9]+}")
public String version(@PathVariable("version") String version) {
    return version;
}
```

The route above matches `/versions/v12` and does not match `/versions/latest`. The `{version:v[0-9]+}` pattern is a **URL matching condition**, while the `@PathVariable` annotation only receives the extracted value. With `@PathVariable UUID id` or `long id`, type conversion is performed by Spring MVC's conversion system. Regex does not replace business validation, authorization checks, or resource verification.

In modern Spring MVC, `PathPatternParser` processes paths segment by segment. `{id}` typically captures a single segment; the `/` character separates segments. When you need to capture multiple trailing segments, Spring also provides the `{*path}` syntax, but it must only be used in valid positions according to `PathPattern` rules—avoid assuming `{id}` will automatically capture any `/` characters.

## 3. `@MatrixVariable`: `;key=value` parameters attached to a path segment

A **path segment** is the part between two `/` characters. Matrix variables appear directly inside that segment, after a `;` character:

```text
/cars/7;color=red;year=2012
      └── segment: "7;color=red;year=2012"
          ├── path variable carId = "7"
          ├── matrix variable color = "red"
          └── matrix variable year = "2012"
```

The mapping pattern should have a URI variable covering the segment carrying the parameters, such as `/cars/{carId}`:

```java
@GetMapping("/cars/{carId}")
public String getCar(
        @PathVariable("carId") long carId,
        @MatrixVariable(name = "color", pathVar = "carId") String color,
        @MatrixVariable(name = "year", pathVar = "carId") int year) {
    return "carId=" + carId + ", color=" + color + ", year=" + year;
}
```

With `GET /cars/7;color=red;year=2012`, the result is:

```text
carId=7, color=red, year=2012
```

`name` (or `value`) selects the parameter name; `pathVar` selects the URI template variable of the **segment containing it**. If only one segment carries matrix variables and there is no ambiguity, `pathVar` can be omitted. When multiple segments contain the same parameter name, specify `pathVar` explicitly.

### 3.1. Two ways to pass multiple values

Spring MVC supports multiple values separated by commas or by repeating the same key:

```text
/cars/7;color=red,green;year=2012
/cars/7;color=red;color=green;year=2012
```

You can receive `color` as a `List<String>` (via Spring's default value conversion mechanism) or use `MultiValueMap<String, String>` to preserve all values per name. Example receiving a single parameter:

```java
@GetMapping("/cars/{carId}")
public List<String> carColors(
        @MatrixVariable(name = "color", pathVar = "carId") List<String> colors) {
    return colors;
}
```

With `/cars/7;color=red,green`, the corresponding JSON body is:

```json
["red","green"]
```

The code snippet above **illustrates a standalone controller method**; do not declare it simultaneously with another method that shares `@GetMapping("/cars/{carId}")` in the same application, as duplicate mappings can cause Spring to report an ambiguous mapping at startup.

### 3.2. Distinguishing the same name across segments

```java
@GetMapping("/owners/{ownerId}/pets/{petId}")
public String getPet(
        @PathVariable("ownerId") long ownerId,
        @PathVariable("petId") long petId,
        @MatrixVariable(name = "q", pathVar = "ownerId") int ownerQ,
        @MatrixVariable(name = "q", pathVar = "petId") int petQ) {
    return "ownerId=" + ownerId + ", petId=" + petId
            + ", ownerQ=" + ownerQ + ", petQ=" + petQ;
}
```

Request:

```text
GET /owners/42;q=11/pets/21;q=22
```

Returns:

```text
ownerId=42, petId=21, ownerQ=11, petQ=22
```

`pathVar = "ownerId"` reads `q=11` from segment `42;q=11`; `pathVar = "petId"` reads `q=22` from segment `21;q=22`. Do not rely on Spring arbitrarily picking one value when the same name appears in multiple places.

### 3.3. Optionality, default values, and parameter maps

By default, `@MatrixVariable` has `required = true`. When the parameter is absent, Spring MVC typically returns 400 because the required argument cannot be resolved.

```java
@GetMapping("/pets/{petId}")
public String petDetail(
        @PathVariable("petId") long id,
        @MatrixVariable(name = "lang", pathVar = "petId",
                        defaultValue = "vi") String lang,
        @MatrixVariable(name = "page", pathVar = "petId",
                        defaultValue = "1") int page) {
    return "id=" + id + ", lang=" + lang + ", page=" + page;
}
```

With `/pets/21`, the value is `id=21, lang=vi, page=1`. `defaultValue` also makes the parameter no longer required. If you choose `required = false` **without** a `defaultValue`, use the reference type `Integer` instead of `int` to clearly represent a missing value.

To read all matrix variables instead of a single key:

```java
@GetMapping("/owners/{ownerId}/pets/{petId}")
public MultiValueMap<String, String> allPetParameters(
        @MatrixVariable(pathVar = "petId")
        MultiValueMap<String, String> petParameters) {
    return petParameters;
}
```

This illustrative method snippet requires `import org.springframework.util.MultiValueMap;`. The request `/owners/42;q=11/pets/21;q=22;s=23` produces a map for segment `petId` with `q → ["22"]`, `s → ["23"]`. If `pathVar` is omitted on `MultiValueMap`, Spring can collect matrix variables from all segments of the route; for instance, `q` would have two values `11` and `22`. Use `MultiValueMap` when keys might repeat; `Map<String, String>` only represents one value per key.

## 4. How does Spring MVC process these two annotations?

1. `DispatcherServlet` receives the request and locates the handler via `RequestMappingHandlerMapping` based on the registered HTTP method and pattern.
2. The path matching engine resolves template variables (e.g., `ownerId=42`, `petId=21`) and matrix data attached to each segment if the path, configuration, and security layer allow it.
3. The appropriate `HandlerMethodArgumentResolver` processes `@PathVariable` and `@MatrixVariable`; `ConversionService` converts string values into `long`, `int`, collections, or custom types when configured.
4. Spring invokes the controller method with the arguments; `@RestController` serializes the return value into the HTTP response body via a message converter.

Mental model: **pattern selects handler → resolvers extract URL data → conversion converts types → method handles business logic**. Annotations do not automatically perform database queries or verify resource access permissions.

## 5. Complete runnable example — Java 17 + Spring Web

Create a Spring Boot project on [Spring Initializr](https://start.spring.io/) with Java 17 or higher and the **Spring Web** dependency. Using the exact package `com.example.demo`, replace the contents of `src/main/java/com/example/demo/DemoApplication.java` with the entire snippet below. This is **one complete program** (three endpoints with non-overlapping mappings):

```java
package com.example.demo;

import java.util.List;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.MatrixVariable;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api")
class RouteController {

    @GetMapping("/orders/{orderId}")
    public String order(@PathVariable("orderId") long orderId) {
        return "orderId=" + orderId;
    }

    @GetMapping("/cars/{carId}")
    public String car(
            @PathVariable("carId") long carId,
            @MatrixVariable(name = "color", pathVar = "carId",
                            required = false) List<String> colors,
            @MatrixVariable(name = "year", pathVar = "carId",
                            defaultValue = "0") int year) {
        List<String> safeColors = colors == null ? List.of() : colors;
        return "carId=" + carId
                + ", colors=" + safeColors
                + ", year=" + year;
    }

    @GetMapping("/owners/{ownerId}/pets/{petId}")
    public String pet(
            @PathVariable("ownerId") long ownerId,
            @PathVariable("petId") long petId,
            @MatrixVariable(name = "q", pathVar = "ownerId") int ownerQ,
            @MatrixVariable(name = "q", pathVar = "petId") int petQ) {
        return "ownerId=" + ownerId
                + ", petId=" + petId
                + ", ownerQ=" + ownerQ
                + ", petQ=" + petQ;
    }
}
```

From the root directory of the project generated by Spring Initializr, run the Maven wrapper:

```bash
# macOS/Linux
./mvnw spring-boot:run

# Windows PowerShell or Command Prompt
mvnw.cmd spring-boot:run
```

The following cURL commands wrap URLs in quotes so the shell does not interpret `;`. On Windows PowerShell, replace `curl` with `curl.exe` if `curl` is aliased to another command:

```bash
curl -s 'http://localhost:8080/api/orders/42'
# orderId=42

curl -s 'http://localhost:8080/api/cars/7;color=red,green;year=2012'
# carId=7, colors=[red, green], year=2012

curl -s 'http://localhost:8080/api/cars/7'
# carId=7, colors=[], year=0

curl -s 'http://localhost:8080/api/owners/42;q=11/pets/21;q=22'
# ownerId=42, petId=21, ownerQ=11, petQ=22
```

The `# ...` lines are **expected response bodies**, not part of the Java application's stdout. `curl -s` prints the body without the status; if you need to inspect HTTP status/headers, use `curl -i`. Matrix variable results assume the HTTP and security layers actually allow `;` to reach Spring MVC; see section 6 before concluding that the controller is broken.

## 6. Configuration and security: common reasons matrix variables fail to work

### 6.1. Path matching engine differences

Spring MVC 6.0+ uses **`PathPatternParser`** by default: a parser that splits paths by segment and handles path parameters for extracting matrix variables; typically, no legacy `UrlPathHelper` configuration is needed just to read matrix data.

Some older Spring MVC applications use **`AntPathMatcher`** (string pattern matching). With this legacy configuration, if `UrlPathHelper` strips content after `;`, `@MatrixVariable` has no data left to read. Older tutorials often configure:

```java
// Illustrative only for MVC applications using the legacy AntPathMatcher mechanism.
@Override
public void configurePathMatch(PathMatchConfigurer configurer) {
    UrlPathHelper helper = new UrlPathHelper();
    helper.setRemoveSemicolonContent(false);
    configurer.setUrlPathHelper(helper);
}
```

This is an **illustrative configuration method snippet** that needs to be placed inside a `@Configuration implements WebMvcConfigurer` class with the appropriate imports. Do not copy it blindly into modern Spring MVC 6+/7+ configurations, as path matching behavior and compatibility differ. If using legacy mode, verify the active matcher configuration first.

### 6.2. Spring Security blocks semicolons by default

Spring Security's `StrictHttpFirewall` **rejects semicolons in URLs** by default due to HTTP request ambiguity risks and security rule bypasses. This can cause errors before a request even enters the controller, even when `@MatrixVariable` and the mapping are written correctly. If your application genuinely requires matrix parameters and you have assessed the risks, the Spring Security documentation provides this example:

```java
// Standalone configuration snippet; requires spring-security-web on the classpath.
@Bean
StrictHttpFirewall httpFirewall() {
    StrictHttpFirewall firewall = new StrictHttpFirewall();
    firewall.setAllowSemicolon(true);
    return firewall;
}
```

Import `org.springframework.context.annotation.Bean` and `org.springframework.security.web.firewall.StrictHttpFirewall` in your Security configuration class. **Only enable this when genuinely necessary**; afterward, you must test authorization rules, URL normalization, proxies, caches, and parameter limits. With Spring Security, this is a security policy change, not a general mandatory step for Spring MVC. When `spring-boot-starter-web` runs standalone without Spring Security, the example in section 5 does not need this bean.

### 6.3. Proxies, gateways, and clients

The `;` character may be handled by reverse proxies, servers, firewalls, or clients according to their own rules. Inspect the **actual request received by the controller** when debugging, and check gateways and containers. Never put access tokens, passwords, or secrets in paths, matrix parameters, or query strings because URLs can appear in logs, browser history, and caches. For public APIs requiring broad compatibility, `?color=red&year=2012` with `@RequestParam` is usually easier to operate.

## 7. Distinguishing and choosing an endpoint design

| Requirement | Recommendation | Example |
| --- | --- | --- |
| Identifying a specific resource | `@PathVariable` | `GET /orders/42` |
| Identifying nested resources | Multiple `@PathVariable`s | `GET /owners/42/pets/21` |
| General filtering/sorting/pagination of a collection resource | `@RequestParam` | `GET /cars?color=red&page=2` |
| Metadata with **per-segment** semantics | `@MatrixVariable`, if infrastructure supports it | `GET /owners/42;q=11/pets/21;q=22` |

Do not use `@MatrixVariable` to replace `@PathVariable` for IDs; nor assume `@RequestParam` can read `;color=red`. Each annotation extracts data from a different location of the URL.

A maintainable design choice is usually a route with clear resource identifiers plus query parameters for filters. Matrix variables are useful when you need to express options tied to **a specific segment** of the route; the cost is requiring consistent support across clients, gateways, and security layers.

## 8. Common errors and how to isolate them

| Symptom | Cause to check | How to fix |
| --- | --- | --- |
| `404` on `/orders` | Mapping requires `/{orderId}` | Call the full URL or declare a separate route for the collection |
| `400` on `/orders/abc` | `abc` cannot be converted to `long` | Use a valid ID or choose `String` type with validation |
| `400` when `;color=...` is missing | `@MatrixVariable` is required by default | Use `required=false` or `defaultValue` |
| Wrong/ambiguous `q` segment | Same matrix variable name in multiple segments | Use `pathVar="ownerId"` or `pathVar="petId"` |
| Request with `;` rejected early | Spring Security `StrictHttpFirewall` or proxy/container | Identify the blocking layer; only change policy after assessing risks |
| Cannot read matrix param despite route match | Parser/legacy config stripped `;...` content | Check MVC path matching mode and `UrlPathHelper` if using legacy |
| `Name for argument ... not specified` error | Annotation name omitted and parameter names not retained at compile time | Explicitly write `@PathVariable("id")` / `@MatrixVariable("color")` |
| Ambiguous mapping error at startup | Two methods declare the same HTTP method + route | Keep only one handler per equivalent mapping |

Debugging practice: (1) test a simple route `/api/orders/42`, (2) call the matrix route with `curl -i`, (3) check the status and Spring Security/proxy logs, (4) verify that a URI template variable actually covers the segment, (5) cross-check `pathVar` names and Java types. Avoid modifying security configuration reflexively before identifying which layer caused the error.

## 9. Self-check questions

**Question 1.** Given `@GetMapping("/books/{id}")` and `@PathVariable("id") Long id`, what does `id` equal for URL `/books/50`? What can happen if you call `/books/abc`?

**Answer:** `id=50L` after conversion; `abc` cannot be converted to `Long`, so Spring MVC typically returns 400.

**Question 2.** Given `/owners/42;view=compact/pets/21;view=full`, how do you explicitly read `view=full`?

```java
@MatrixVariable(name = "view", pathVar = "petId") String view
```

The corresponding method mapping must have `/owners/{ownerId}/pets/{petId}`, and in this example `view` receives `full`.

**Question 3.** How do `/cars/7;color=red` and `/cars/7?color=red` differ?

**Answer:** The first case is a matrix variable belonging to path segment `7`; the second case is a query parameter, typically read with `@RequestParam("color")`.

**Question 4.** Why might `@MatrixVariable` fail to be read in an application with Spring Security even when the method is written correctly?

**Answer:** A likely cause to check is `StrictHttpFirewall` rejecting URLs containing `;` before the mapping step. Changing configuration requires weighing security risks and considering query parameters as an alternative.

## 10. Official references

- [Spring Framework — Mapping Requests / URI patterns](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): `@PathVariable`, patterns, regex, type conversion.
- [Spring Framework — Matrix Variables](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/matrix-variables.html): `;name=value` syntax, `pathVar`, `defaultValue`, `MultiValueMap`.
- [Spring Framework — Servlet Path Matching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-path.html): `PathPatternParser` and matching differences.
- [Spring Security — HttpFirewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html): default semicolon blocking and exception policy.
- [Spring Framework — Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): role of annotations in the resolver system.

**Practical takeaway:** use `@PathVariable` for components named by a URI pattern, use `@MatrixVariable` when you need to read `key=value` pairs attached to individual segments, specify `pathVar` explicitly when multiple segments exist, and verify security/infrastructure layers before putting `;` into an API contract.
