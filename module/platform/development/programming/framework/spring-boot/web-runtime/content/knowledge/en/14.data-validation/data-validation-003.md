# Constraining Path Variables, Query Parameters, and Nested Objects in Spring Boot

## 1. Problem and Goals

A Spring Boot API does not only need to read HTTP parameters; it must also verify whether that data is valid before calling a business service. Three forms of input that commonly appear together in a single endpoint are:

- **Path variables** (`@PathVariable`): e.g., category ID in `/categories/7/items`.
- **Query parameters** (`@RequestParam`): e.g., `?page=2&sort=price`.
- **Nested objects** built from query/form parameters via `@ModelAttribute` or from JSON via `@RequestBody`: e.g., `range.min=10`, `range.max=100`, `tags[0].name=eco`.

Example request:

~~~text
GET /api/categories/7/items?page=2&sort=price&range.min=10&range.max=100&tags[0].name=eco
~~~

Desired contract:
- `categoryId` must be a positive integer.
- `page` must be within 1–50.
- `sort` accepts only `name` or `price`.
- `range.min` and `range.max` must not be missing, must not be negative, and min must not exceed max.
- Each `tags[i].name` must not be blank; at most three tags.
- Invalid input must be rejected before business processing runs.
- Disallowed data must not be arbitrarily bound onto DTO/domain objects.

In Spring MVC 6.1+ (Spring Boot 3.2+), **constraints on method parameters** and **validation of an object argument** have distinct processing paths and exceptions. Without distinguishing them, `@RestControllerAdvice` can easily catch only half the errors.

This lesson uses **Spring Boot 3.5.x, Java 17+, Spring Framework 6.2.x, Jakarta Bean Validation**. The main examples run on Servlet MVC; the end of the lesson points out similarities and differences in Spring WebFlux.

## 2. Four Stages: Routing, Type Conversion, Binding, Validation

Before a controller is invoked, Spring MVC goes through these steps:

~~~text
HTTP request
   |
DispatcherServlet / HandlerMapping
   |  Does the URL pattern match /categories/{categoryId}/items?
   v
HandlerMethodArgumentResolver
   | @PathVariable, @RequestParam, @ModelAttribute, @RequestBody
   v
Type conversion / data binding / JSON deserialization
   |  "7" -> long 7; "2" -> int 2; "range.min" -> BigDecimal
   v
Jakarta Bean Validation / method validation if present
   |  @Positive, @Min, @Max, @Pattern, @Valid, @NotNull...
   v
Controller is invoked if input is valid
   v
Service -> HTTP response
~~~

**Key takeaway:** binding and validation are not the same thing.

- **Routing:** Does the URL match a mapping? No matching handler typically results in 404.
- **Conversion:** Turns string data into `long`, `int`, enum, `BigDecimal`, `LocalDate`, etc. For example, `page=abc` cannot convert to `int`.
- **Binding:** Populates multiple data values onto an object, including nested properties and indexed collections.
- **Validation:** Only after compatible values exist are `@Min(1)`, `@NotBlank`, `@AssertTrue`, and cross-field constraints evaluated.

Thus `/categories/abc/items` and `/categories/-3/items` can both lead to HTTP 400 for different reasons: the first is path variable type conversion; the second is Bean Validation `@Positive` if enabled.

## 3. Required Dependency to Use Jakarta Bean Validation

In Spring Boot 3.x, the web starter provides Spring MVC, but **you should not assume** it always includes a full Bean Validation provider. To use `@NotBlank`, `@Min`, `@Valid`, add:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

This starter normally brings Hibernate Validator and the compatible Jakarta Validation API onto the classpath. Spring Boot integrates the validator into MVC when a Bean Validation provider is present.

Typical imports:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
~~~

**Common mistake:** importing `javax.validation.*` from Spring Boot 2.x guides into a Boot 3.x project. Boot 3 uses the **`jakarta.validation.*`** namespace.

Do not consider `@Valid` itself a constraint. It triggers checking constraints on the marked object and can trigger cascade validation; if the DTO has no constraints or no provider is configured, the annotation does not automatically validate input.

## 4. Constraining Path Variables with @PathVariable

Example:

~~~java
@GetMapping("/categories/{categoryId}/items")
ResponseEntity<?> items(
        @PathVariable("categoryId") @Positive long categoryId) {
    // Use categoryId after it has been converted and validated.
    return ResponseEntity.ok().build();
}
~~~

This is a controller fragment and requires imports; the full example is shown in section 10.

Explanation:
- `{categoryId}` is a URI template variable.
- `@PathVariable("categoryId")` binds the route segment string to the Java parameter.
- Spring converts `"7"` to `long 7`.
- `@Positive` requires the number to be greater than 0.
- When conversion/validation fails, Spring MVC normally returns 400 before entering the controller, unless the application customizes error handling.

### 4.1. States to Distinguish

| Request | Does route match pattern? | Typical Result |
|---|---|---|
| `/categories/7/items` | Yes | `categoryId=7`, passes `@Positive` check |
| `/categories/0/items` | Yes | Type conversion succeeds, `@Positive` fails: 400 |
| `/categories/-4/items` | Usually yes | Type conversion succeeds, `@Positive` fails: 400 |
| `/categories/abc/items` | Yes | Cannot convert `abc` to `long`: usually 400 |
| `/categories/items` | Does not match pattern with ID | Usually 404, not a `@Positive` error |
| `/categories/7/items/extra` | Does not match declared mapping | Usually 404 |

Note: route constraints such as `/categories/{categoryId:[0-9]+}/items` can **reject invalid values at the routing step** and result in 404 instead of Bean Validation 400. The two designs produce different HTTP contracts: route regex decides handler matching, whereas `@Positive` validates an already-matched argument.

### 4.2. @Pattern and UUID Path Variables

If an ID is a formatted string, you can use:

~~~java
@GetMapping("/orders/{orderCode}")
String order(@PathVariable @Pattern(
        regexp = "[A-Z]{3}-[0-9]{4}") String orderCode) {
    return orderCode;
}
~~~

This is a controller fragment. `@Pattern` checks **the value after binding**, rather than replacing the route matcher. For `UUID` types, Spring has a dedicated converter; malformed UUID strings are typically rejected during conversion before validation.

Do not use `@NotBlank` on a `long` number; choose constraints compatible with the data type. `@Positive`/`@Min` are for numbers; `@Pattern` is for `CharSequence`.

## 5. Constraining Query Parameters with @RequestParam

Spring MVC uses `@RequestParam` to read query parameters and, with Servlet, form parameters when applicable.

~~~java
@GetMapping("/search")
Map<String, Object> search(
        @RequestParam(name = "page", defaultValue = "1")
        @Min(1) @Max(50) int page,

        @RequestParam(name = "sort", defaultValue = "name")
        @Pattern(regexp = "name|price") String sort) {

    return Map.of("page", page, "sort", sort);
}
~~~

This is a fragment requiring imports for `Map`, `@GetMapping`, `@RequestParam`, and constraints. Note:
- Query missing `page` or having an empty value per `@RequestParam`'s default mechanism: `defaultValue="1"` is used.
- `page=2`: converted to int and passes `@Min`/`@Max`.
- `page=0`: converted, but fails `@Min(1)`.
- `page=xyz`: conversion fails, not a `@Min` error.
- `sort=price`: valid.
- `sort=random`: fails `@Pattern`.

### 5.1. required, defaultValue, and null

| Declaration | When query key is missing | Notes |
|---|---|---|
| `@RequestParam String q` | Usually 400 since required=true by default | Does not mean q is non-blank |
| `@RequestParam(required=false) String q` | Can be null | `@Size` usually allows null; add a constraint if a value is required |
| `@RequestParam(defaultValue="1") int page` | Receives default value 1 | `defaultValue` implicitly sets required=false |
| `@RequestParam Optional<String> q` | `Optional.empty()` | Constraints directly on container/element must target the right type |
| `@RequestParam List<String> tags` | Can receive repeated params | Add size/element constraints if required by business rules |

To require a query parameter to have meaningful content, `required=true` **only** ensures presence per the request parameter contract; it does not forbid `q=` or whitespace-only strings. For `String`, add `@NotBlank` if blank is disallowed.

### 5.2. Repeated Query Keys and Collection Element Constraints

Example:

~~~java
@GetMapping("/tags")
List<String> tags(
        @RequestParam(name = "tag")
        @Size(max = 3) List<@NotBlank String> tags) {
    return tags;
}
~~~

This fragment demonstrates constraint types:
- `@Size(max=3)` checks **element count**.
- `List<@NotBlank String>` checks **each string** when container element validation executes.
- A client can send `?tag=eco&tag=new`.
- `@NotBlank` cannot be applied directly to the `List` type because that constraint is for strings.

Test thoroughly when placing collection constraints directly on method parameters because that triggers method validation; do not assume an empty list and an omitted query are always treated identically.

## 6. @ModelAttribute: Multiple Query Fields into a Nested Object

When there are dozens of query/form parameters, writing an `@RequestParam` for every field becomes verbose and hard to manage. Spring MVC can populate an object via `@ModelAttribute`:

~~~java
@GetMapping("/catalog")
ResponseEntity<?> catalog(
        @Valid @ModelAttribute("criteria") SearchCriteria criteria) {
    return ResponseEntity.ok(criteria);
}
~~~

This is a fragment; `SearchCriteria` is defined below.

Request:

~~~text
GET /catalog?range.min=10&range.max=100&tags[0].name=eco&tags[1].name=organic
~~~

The binder resolves each path:
- `range.min` → `criteria.range.min`;
- `range.max` → `criteria.range.max`;
- `tags[0].name` → first element in the `tags` list;
- `tags[1].name` → second element.

In Spring MVC, `@ModelAttribute` can create the model object via constructor or JavaBean property binding. The binder can auto-grow collections when encountering indexed properties; this feature has limits and must be controlled to prevent resource exhaustion.

### 6.1. Constraints on Parent and Child Classes

Mutable DTO pattern:

~~~java
class SearchCriteria {
    @Valid
    @NotNull
    private PriceRange range = new PriceRange();

    @Size(max = 3)
    private List<@Valid TagFilter> tags = new ArrayList<>();

    // Getters/setters defined in the actual class.
}

class PriceRange {
    @NotNull @DecimalMin("0")
    private BigDecimal min;

    @NotNull @DecimalMin("0")
    private BigDecimal max;
}

class TagFilter {
    @NotBlank
    private String name;
}
~~~

This is a fragment requiring imports and getters/setters, not a standalone source file. Validation relationships:

1. `@Valid` on the `SearchCriteria` argument requests validating the input object.
2. `@Valid` on field `range` requests **descending into** `PriceRange`.
3. `@NotNull` on `range` ensures the child object is non-null; `@Valid` alone does not report an error if the child is null.
4. `@NotNull` and `@DecimalMin` check each monetary value.
5. `List<@Valid TagFilter>` requests validating each list element; `@NotBlank` checks `name`.
6. `@Size(max=3)` checks tag count, not each tag.
7. Spring converts decimal strings to `BigDecimal` before Jakarta Bean Validation evaluates the values.

**If `@Valid` is missing in the right place, constraints inside nested objects can be skipped.** Placing `@NotNull` only on the parent is not enough to check `range.min` and `range.max`.

### 6.2. What Errors Can Nested Paths and Collection Indexes Cause?

| Input | Cause |
|---|---|
| `range.min=abc` | Cannot convert `abc` to BigDecimal |
| `range.min=-1` | Type conversion succeeds; violates `@DecimalMin("0")` |
| `range.min` omitted | May remain null; violates `@NotNull` |
| `tags[0].name=` | Tag is created, but `@NotBlank` fails |
| `tags[0].name=eco&tags[1].name=new` | Two valid elements if other constraints pass |
| `tags[3].name=extra` with max size 3 | May create 4 elements and then violate `@Size(max=3)` |
| `tags[999999].name=boom` | May exceed the auto-grow limit and fail binding |

Do not raise `autoGrowCollectionLimit` indefinitely just to accept large indexes. Set limits on the binder and enforce collection/payload size limits at the entry point appropriately. Relying only on `@Size` **after** binding does not replace limiting allocation cost when instantiating objects.

## 7. Cross-Field Validation: min Must Be Less Than or Equal to max

Per-field constraints cannot catch `min=100, max=10` if both are non-negative. That is a **cross-field constraint**.

A concise JavaBean approach:

~~~java
@AssertTrue(message = "min must be less than or equal to max")
public boolean isOrderValid() {
    return min == null || max == null || min.compareTo(max) <= 0;
}
~~~

This method is placed in `PriceRange`, which has two fields `BigDecimal min, max`. JavaBean conventions treat it as a boolean property `orderValid`; Bean Validation evaluates `@AssertTrue`. When a field is null, the method returns true to leave the “required field” error to `@NotNull` rather than producing duplicate errors.

In larger projects, cross-field constraints should be modeled as a **class-level custom constraint** with `ConstraintValidator` to attach errors to the appropriate path, reuse across DTOs, support i18n, and unit-test in isolation.

Do not manually check min/max inside every controller after allowing the service to run. Validation should sit at the input contract layer or business layer as required.

## 8. Method Validation: An Important Difference Since Spring Framework 6.1

Spring MVC has two common validation levels:

### 8.1. Validating a Single Object Argument

Example:

~~~java
@PostMapping("/products")
ResponseEntity<?> create(
        @Valid @RequestBody CreateProductRequest input) {
    // ...
    return ResponseEntity.ok().build();
}
~~~

If only `CreateProductRequest` needs object validation and no other direct constraints force method validation, Spring MVC may throw `MethodArgumentNotValidException` when the DTO is invalid.

### 8.2. Validating the Entire Handler Method

Example:

~~~java
@GetMapping("/categories/{id}")
String get(
        @PathVariable @Positive long id,
        @RequestParam @Min(1) int page) {
    return "ok";
}
~~~

`@Positive` and `@Min` placed directly on method parameters require **method validation**. Spring MVC 6.1+ has built-in method validation support and normally throws `HandlerMethodValidationException` when input is invalid.

When a single handler simultaneously has:
- `@Positive` on `@PathVariable`;
- `@Min` on `@RequestParam`;
- `@Valid` on `@ModelAttribute` or `@RequestBody`;

method validation can include nested object validation and **supersedes** standalone per-argument validation. Therefore `@RestControllerAdvice` should handle both `HandlerMethodValidationException` and `MethodArgumentNotValidException` depending on handler signatures.

> `@Valid` is **not** a direct constraint. Alone, it does not trigger method validation; `@Min`, `@NotBlank`, `@NotNull` placed directly on parameters are examples of constraints that trigger that mechanism.

### 8.3. Do Not Use Controller-Level @Validated Mechanically

In Spring Framework 6.1+, `@Validated` at the **class level** of a controller can cause method validation to run through an AOP proxy instead of MVC's built-in support. Exceptions and semantics can differ from `HandlerMethodValidationException`.

If you want to use Spring MVC's built-in method validation, the Framework documentation recommends removing `@Validated` from controller classes. Do not copy Spring Boot 2.x tutorials saying “add @Validated on the controller to validate query params” without checking newer versions.

Spring Boot requires a compatible Bean Validation provider; simply using annotations without the validation dependency is insufficient to guarantee checks execute.

## 9. BindingResult and Designing Error Responses

### 9.1. BindingResult Must Immediately Follow Its Target Object

In a form controller:

~~~java
@PostMapping("/filter")
ResponseEntity<?> filter(
        @Valid @ModelAttribute("criteria") SearchCriteria criteria,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body(errors.getFieldErrors()
                .stream().map(error -> error.getField()).toList());
    }
    return ResponseEntity.ok().build();
}
~~~

This is a fragment, not a method from the full example below. `BindingResult` must stand **immediately after** the object it describes. When constraints exist on other method parameters, the controller is only invoked if every error has an adjacent `Errors` argument; if errors occur on parameters without a local Errors argument, `HandlerMethodValidationException` is still thrown.

With `@RequestBody` malformed JSON, there is no object to validate; `BindingResult` **cannot** catch `HttpMessageNotReadableException`.

### 9.2. Errors That Can Occur

| Error Category | Example | Typical Spring MVC Exception |
|---|---|---|
| Path/query conversion failure | `categoryId=abc`, `page=xyz` | `MethodArgumentTypeMismatchException` and conversion error branch |
| Missing required query | Missing `q` when `required=true` | `MissingServletRequestParameterException` |
| Object binding / validation | `@Valid @ModelAttribute` violates constraint | `MethodArgumentNotValidException` when per-object validation applies |
| Method-level validation | `@Positive` on path, `@Min` on query | `HandlerMethodValidationException` |
| Unreadable JSON | Malformed JSON body or cannot deserialize | `HttpMessageNotReadableException` |
| Wrong `Content-Type` | Endpoint only accepts JSON, text/plain sent | `HttpMediaTypeNotSupportedException` |
| No route matching | Missing category ID segment | Usually 404, does not reach validation |

Default behavior for most input errors returns **400 Bad Request**; wrong media type usually returns **415**. Custom exception handlers, security, routing, and framework versions can alter response codes; test your API contract rather than hardcoding assumptions about default error bodies.

### 9.3. Safe Error Details

Return a consistent error code such as `validation_failed`, a list of fields/paths, and safe messages. When client i18n is needed, Spring provides `MessageSource` and Bean Validation message codes. Do not return stack traces, full entities, or sensitive request bodies.

An `@RestControllerAdvice` can:
- Handle `MethodArgumentNotValidException` via `getBindingResult()`.
- Handle `HandlerMethodValidationException` via its list of `ParameterValidationResult`.
- Let the framework handle type conversion/404/415 errors, or define dedicated handlers when required by the API.

The complete example in section 10 implements the two validation exception branches while leaving framework defaults for the remaining errors.

## 10. Runnable Spring Boot 3.5 and Java 17+ Application Example

We will build an MVC application with:
- GET: path variable + query parameters + nested `@ModelAttribute`.
- POST: path variable + nested JSON `@RequestBody`.
- Both apply method validation to the path variable; objects are recursively validated.
- The query binder allows only necessary property paths.
- Automatically returns 400 on invalid input via Spring MVC and validation handlers.

### 10.1. pom.xml

Create a Maven project directory with `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>nested-validation-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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

With Java 17+ and Maven, the project uses `spring-boot-starter-web`, running Spring MVC on the default Servlet container (typically Tomcat). Do not add the WebFlux starter in this example.

### 10.2. Complete Java Source

Create `src/main/java/example/validation/NestedValidationApplication.java`:

~~~java
package example.validation;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@SpringBootApplication
public class NestedValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(NestedValidationApplication.class, args);
    }
}

@RestController
@RequestMapping("/api")
class CatalogController {

    @InitBinder("criteria")
    void limitFields(WebDataBinder binder) {
        binder.setAllowedFields("range.min", "range.max", "tags[*].name");
        binder.setAutoGrowCollectionLimit(8);
    }

    @GetMapping("/categories/{categoryId}/items")
    Map<String, Object> browse(
            @PathVariable("categoryId") @Positive long categoryId,
            @RequestParam(name = "page", defaultValue = "1")
            @Min(1) @Max(50) int page,
            @RequestParam(name = "sort", defaultValue = "name")
            @Pattern(regexp = "name|price") String sort,
            @Valid @ModelAttribute("criteria") SearchCriteria criteria) {

        return Map.of(
                "categoryId", categoryId,
                "page", page,
                "sort", sort,
                "min", criteria.getRange().getMin(),
                "max", criteria.getRange().getMax(),
                "tags", criteria.getTags().stream()
                        .map(TagChoice::getName).toList());
    }

    @PostMapping(
            path = "/categories/{categoryId}/items/search",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Map<String, Object>> searchJson(
            @PathVariable("categoryId") @Positive long categoryId,
            @Valid @RequestBody JsonSearch input) {

        return ResponseEntity.ok(Map.of(
                "categoryId", categoryId,
                "min", input.range().min(),
                "max", input.range().max(),
                "tags", input.tags().stream()
                        .map(JsonTag::name).toList()));
    }
}

@RestControllerAdvice
class InputValidationAdvice {

    @ExceptionHandler(HandlerMethodValidationException.class)
    ResponseEntity<Map<String, Object>> onMethodValidation(
            HandlerMethodValidationException exception) {

        List<String> messages = exception.getAllValidationResults()
                .stream()
                .flatMap(result -> result.getResolvableErrors().stream())
                .map(error -> String.valueOf(error.getDefaultMessage()))
                .toList();

        return ResponseEntity.status(exception.getStatusCode())
                .body(Map.of(
                        "error", "validation_failed",
                        "details", messages));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<Map<String, Object>> onObjectValidation(
            MethodArgumentNotValidException exception) {

        List<String> messages = exception.getBindingResult()
                .getAllErrors()
                .stream()
                .map(error -> String.valueOf(error.getDefaultMessage()))
                .toList();

        return ResponseEntity.badRequest()
                .body(Map.of(
                        "error", "validation_failed",
                        "details", messages));
    }
}

class SearchCriteria {

    @Valid
    @NotNull
    private PriceBounds range = new PriceBounds();

    @Size(max = 3)
    private List<@Valid TagChoice> tags = new ArrayList<>();

    public SearchCriteria() {}

    public PriceBounds getRange() { return range; }
    public void setRange(PriceBounds range) { this.range = range; }

    public List<TagChoice> getTags() { return tags; }
    public void setTags(List<TagChoice> tags) { this.tags = tags; }
}

class PriceBounds {

    @NotNull
    @DecimalMin("0")
    private BigDecimal min;

    @NotNull
    @DecimalMin("0")
    private BigDecimal max;

    public PriceBounds() {}

    public BigDecimal getMin() { return min; }
    public void setMin(BigDecimal min) { this.min = min; }

    public BigDecimal getMax() { return max; }
    public void setMax(BigDecimal max) { this.max = max; }

    @AssertTrue(message = "min must be less than or equal to max")
    public boolean isOrderValid() {
        return min == null || max == null || min.compareTo(max) <= 0;
    }
}

class TagChoice {

    @NotBlank
    private String name;

    public TagChoice() {}

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}

record JsonSearch(
        @Valid @NotNull JsonPrice range,
        @NotNull @Size(max = 3) List<@Valid JsonTag> tags) {}

record JsonPrice(
        @NotNull @DecimalMin("0") BigDecimal min,
        @NotNull @DecimalMin("0") BigDecimal max) {

    @AssertTrue(message = "min must be less than or equal to max")
    public boolean isOrderValid() {
        return min == null || max == null || min.compareTo(max) <= 0;
    }
}

record JsonTag(@NotBlank String name) {}
~~~

Code notes:
- The file has a single `public class` matching the filename; the remaining DTOs, controller, and advice are package-private.
- `@Valid` is placed on method arguments and nested types; `@Positive`, `@Min`, `@Max`, `@Pattern` are placed directly on parameters.
- `@InitBinder("criteria")` only restricts property binding for the `criteria` model attribute; it does not apply to Jackson deserialization of `@RequestBody`.
- `tags[*].name` is an allowedFields wildcard matching indexed property paths `tags[0].name`, `tags[1].name`, etc.
- `setAutoGrowCollectionLimit(8)` blocks excessively large collection indexes in the binder; `@Size(max=3)` enforces the stricter business limit.
- The controller class does **not** declare `@Validated` at the type level, because it uses Spring MVC 6.1+ built-in method validation.
- `@RestControllerAdvice` illustrates the two main validation exceptions; malformed JSON, type mismatches, unmatched routes, and invalid media types still use Spring MVC defaults.
- The import `org.springframework.validation.annotation.Validated` in the sample is unused and can be removed without changing behavior.

This is a demo application and does not access a database. When input is valid, the endpoints return a `Map` describing the bound values for easy verification.

### 10.3. Starting Up

In the Maven project directory:

~~~bash
mvn spring-boot:run
~~~

Assuming port 8080 is free and there is no proxy or extra security starter. This build fetches dependencies automatically if the Maven repository is reachable.

## 11. Testing with curl: One Request, Multiple Validation Layers

### 11.1. Valid GET with Query + Nested Model Attributes

~~~bash
curl -i -G "http://localhost:8080/api/categories/7/items" \
  --data-urlencode "page=2" \
  --data-urlencode "sort=price" \
  --data-urlencode "range.min=10" \
  --data-urlencode "range.max=100" \
  --data-urlencode "tags[0].name=eco"
~~~

Meaningful output:

~~~json
{"categoryId":7,"page":2,"sort":"price","min":10,"max":100,"tags":["eco"]}
~~~

Expected HTTP status **200 OK**. JSON property order has no contract guarantee; do not write tests depending on `Map` key ordering.

### 11.2. POST JSON with Nested Objects

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/categories/7/items/search" \
  -H "Content-Type: application/json" \
  -d '{"range":{"min":10,"max":100},"tags":[{"name":"eco"}]}'
~~~

Meaningful output:

~~~json
{"categoryId":7,"min":10,"max":100,"tags":["eco"]}
~~~

Expected HTTP status **200 OK**. Spring MVC uses the Jackson HTTP message converter to create the `JsonSearch` record, then validation descends into `JsonPrice` and `JsonTag` via `@Valid`.

### 11.3. Invalid Path Variable

~~~bash
curl -i -G "http://localhost:8080/api/categories/0/items" \
  --data-urlencode "range.min=10" \
  --data-urlencode "range.max=100"
~~~

Expected code **400**, because `categoryId=0` violates `@Positive`. The error occurs on a method parameter, so it typically goes through `HandlerMethodValidationException` in Spring MVC 6.2.

~~~bash
curl -i -G "http://localhost:8080/api/categories/abc/items" \
  --data-urlencode "range.min=10" \
  --data-urlencode "range.max=100"
~~~

The status is also typically **400**, but this time `abc` cannot be converted to `long`. Do not call this a `@Positive` error.

### 11.4. Invalid Query Parameters

~~~bash
# page exceeds limit
curl -i -G "http://localhost:8080/api/categories/7/items" \
  --data-urlencode "page=80" \
  --data-urlencode "range.min=10" \
  --data-urlencode "range.max=100"

# sort not among allowed values
curl -i -G "http://localhost:8080/api/categories/7/items" \
  --data-urlencode "sort=unknown" \
  --data-urlencode "range.min=10" \
  --data-urlencode "range.max=100"
~~~

Both are expected to return **400** if no custom error mapping overrides them.

### 11.5. Invalid Nested Object

~~~bash
# Cross-field constraint: min > max
curl -i -G "http://localhost:8080/api/categories/7/items" \
  --data-urlencode "range.min=100" \
  --data-urlencode "range.max=10"

# Tag with blank name
curl -i -G "http://localhost:8080/api/categories/7/items" \
  --data-urlencode "range.min=10" \
  --data-urlencode "range.max=100" \
  --data-urlencode "tags[0].name="
~~~

Expected result **400** when nested validation is properly enabled. With `range.min=100` and `range.max=10`, both individual fields pass `@DecimalMin("0")`, but `@AssertTrue` on `isOrderValid()` fails.

### 11.6. Data Exceeding Binder Scale

If a client sends index `tags[999999].name`, the binder will not grow the collection to that size due to `setAutoGrowCollectionLimit(8)`. This case may raise a binding/invalid-property exception before `@Size(max=3)`. Exact output depends on how the binder and exception handler handle it; this warrants integration testing if the API accepts untrusted input.

Do not send requests with millions of elements in production to test. Use a dedicated test environment and enforce rate limits, request-size limits, and resource protections at the edge/server.

## 12. Automated Testing with MockMvc

Create `src/test/java/example/validation/NestedValidationApplicationTests.java`:

~~~java
package example.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class NestedValidationApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsValidPathQueryAndNestedModel() throws Exception {
        mvc.perform(get("/api/categories/7/items")
                .param("page", "2")
                .param("sort", "price")
                .param("range.min", "10")
                .param("range.max", "100")
                .param("tags[0].name", "eco"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.categoryId").value(7))
                .andExpect(jsonPath("$.page").value(2))
                .andExpect(jsonPath("$.tags[0]").value("eco"));
    }

    @Test
    void rejectsInvalidPathConstraint() throws Exception {
        mvc.perform(get("/api/categories/0/items")
                .param("range.min", "10")
                .param("range.max", "100"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsPageOutsideRange() throws Exception {
        mvc.perform(get("/api/categories/7/items")
                .param("page", "99")
                .param("range.min", "10")
                .param("range.max", "100"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsNestedCrossFieldRule() throws Exception {
        mvc.perform(get("/api/categories/7/items")
                .param("range.min", "100")
                .param("range.max", "10"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsBlankNestedTagName() throws Exception {
        mvc.perform(get("/api/categories/7/items")
                .param("range.min", "10")
                .param("range.max", "100")
                .param("tags[0].name", ""))
                .andExpect(status().isBadRequest());
    }

    @Test
    void acceptsNestedJson() throws Exception {
        mvc.perform(post("/api/categories/7/items/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"range":{"min":10,"max":100},
                     "tags":[{"name":"eco"}]}
                    """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tags[0]").value("eco"));
    }

    @Test
    void rejectsInvalidNestedJson() throws Exception {
        mvc.perform(post("/api/categories/7/items/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"range":{"min":100,"max":10},
                     "tags":[{"name":"eco"}]}
                    """))
                .andExpect(status().isBadRequest());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

These tests verify the **HTTP contract** and real validation in the Spring MVC test context. Do not assert exact element ordering in `details` JSON because error order can differ by validator and handler signature. When a controller has direct parameter constraints, `HandlerMethodValidationException` is the branch to check; when there is only an `@Valid` object, `MethodArgumentNotValidException` may be invoked.

MockMvc does not replace every integration test with embedded Tomcat. If you need to test URI size limits, proxies, query encoding, or security filters outside a test slice, run the full application on a random port and send requests over real HTTP.

## 13. Validation Groups: Create and Update Can Have Different Rules

A single DTO reused for two operations may require different constraint sets:

- Create: `name` required, ID absent.
- Update: ID required, some fields allowed to be empty.
- Search: price range optional, tag limit differs from create requests.

Jakarta Bean Validation supports **validation groups** and Spring `@Validated(SomeGroup.class)`. Illustrative example:

~~~java
interface CreateGroup {}
interface UpdateGroup {}

record ProductInput(
        @NotBlank(groups = CreateGroup.class)
        String name,

        @NotNull(groups = UpdateGroup.class)
        Long id) {}
~~~

This is a DTO fragment and marker interfaces. When declaring `@Validated(CreateGroup.class) @RequestBody ProductInput input`, the validator checks constraints in that group. Unlike `@Valid`, `@Validated` also supports Spring validation hints/groups. However:
- Constraints in the `Default` group do not automatically run when selecting another group, unless defined or sequenced accordingly.
- Cascading validation into nested objects may also require configuring groups/`@ConvertGroup` when group policies are complex.
- Do not use an overly broad DTO expecting groups alone to prevent over-posting; separate request DTOs are usually clearer and safer.

When combining method validation and group validation, test behavior against your actual Spring Framework version and exception handlers; do not infer it solely from an annotation on a single field.

## 14. How Do Nested Objects in JSON Differ from Nested Query Parameters?

There are two different processing paths:

| Characteristic | Nested `@ModelAttribute` | Nested `@RequestBody` |
|---|---|---|
| Input source | Query/form and supported binder sources | JSON/XML body when supported by converter |
| Path to nested field | `range.min=10`, `tags[0].name=eco` | `{"range":{"min":10},"tags":[{"name":"eco"}]}` |
| Object creation component | `WebDataBinder`, constructor/property binding | Jackson or corresponding `HttpMessageConverter` |
| Limiting writable fields | DTO and `@InitBinder.setAllowedFields` for property binding | JSON DTO, Jackson config, deserializer policies |
| Type conversion error | Binder/type mismatch | Parser/deserializer exception |
| Cascade validation | `@Valid` on nested fields/elements | `@Valid` on nested fields/elements |
| Collection index | Binder has auto-grow limit | JSON parser creates list from array; separate request/body size limits apply |
| Empty body error | Independent of JSON body | `@RequestBody` defaults to required=true |
| Media type | Suited to form/query semantics | `Content-Type: application/json` for JSON |

JSON payloads will not automatically bind with `@ModelAttribute` if the client sends `application/json`; and `@RequestBody` does not automatically merge query parameters into a JSON DTO. The nested validation DTO concept is the same, but object construction and conversion errors differ.

## 15. Input Data Security and Resource Limits

### 15.1. Mass Assignment and Nested Paths

If you bind a domain entity directly with `@ModelAttribute`, a client can send `user.role=ADMIN`, `order.ownerId=...`, `account.balance=999999` whenever corresponding setters exist. This is **mass assignment/over-posting**, not a Bean Validation bug.

Mitigations:
1. Request DTOs contain only fields allowed to be modified.
2. With mutable property binding, `@InitBinder` and `setAllowedFields` restrict bindable property paths.
3. Never bind database JPA entities directly from request parameters.
4. Verify update permissions for fields at the service/domain layer; validation does not replace authorization.
5. With JSON `@RequestBody`, also enforce DTOs/deserialization policies and safe entity mapping. JSON is not immune to mass assignment.
6. Limit nested collection depth/index, request size, and parameter count to mitigate resource exhaustion.

In the example, the binder only allows:
- `range.min`;
- `range.max`;
- `tags[*].name`.

There is no `ownerId` or `admin` path in the DTO. However, `allowedFields` on property binding is **not** a Jackson JSON filter; do not use it in place of a request-body DTO.

### 15.2. Validation Does Not Replace Database/Business Rules

`@Positive` checks that an ID is greater than 0, but does not prove the record exists or the caller has permission to view it. `@Pattern` checks code format, not whether the code exists. `@DecimalMin` checks non-negativity, not quotas, balances, or current prices.

Proper flow:
1. Authenticate and authorize (per security contract).
2. Bind/convert input.
3. Validate syntax, structure, length, and field relationships.
4. Business service checks state, ownership, resource existence, and transaction rules.
5. Choose HTTP codes per API contract: 400 for invalid input, 404 if resource is missing, 403 if unauthorized, 409 on state conflict, etc.

Do not assume `@Valid` guarantees data safety.

## 16. Spring WebFlux: Same Concepts, Different Runtime and Exceptions

Spring WebFlux also supports `@PathVariable`, `@RequestParam`, `@ModelAttribute`, `@RequestBody`, `@Valid`, and method validation. However:
- `@RequestBody` reads via reactive `HttpMessageReader`/codecs and can accept `Mono<T>`.
- `@ModelAttribute` uses a reactive-aware binder for form/query and nested object paths.
- When standalone argument object validation fails, WebFlux usually throws `WebExchangeBindException`.
- Method-level constraints such as `@Positive` on path or `@Min` on query can lead to `HandlerMethodValidationException`.
- `@Valid` alone is still not a direct constraint; method validation selection works similarly in concept.
- Never call `block()` on the event loop just to “read the DTO” before validating.

Illustrative WebFlux fragment (not part of the section 10 MVC project):

~~~java
@PostMapping(path = "/reactive/search",
        consumes = MediaType.APPLICATION_JSON_VALUE)
Mono<ResponseEntity<String>> reactiveSearch(
        @Valid @RequestBody Mono<JsonSearch> input) {
    return input.map(value ->
            ResponseEntity.ok("tags=" + value.tags().size()));
}
~~~

This fragment requires appropriate WebFlux imports and the `JsonSearch` DTO. Validating a reactive body wrapper and returning errors via a publisher differs from receiving a synchronous DTO in MVC. If custom invalid-body handling is needed, use WebFlux `@ExceptionHandler` or appropriate operators rather than reusing Servlet `BindingResult` assumptions on `Mono<DTO>`.

Do not conclude an app runs WebFlux just because `WebClient` is on the classpath. When both starter-web and starter-webflux are present, Spring Boot typically prefers the MVC server; determine the actual web application type first.

## 17. Common Pitfalls

1. **Missing `spring-boot-starter-validation` while expecting `@Min` to run.** Check provider dependencies.
2. **Adding `@Valid` only on the top-level DTO, forgetting nested `@Valid`.** Child constraints may go unchecked.
3. **Using `@NotBlank` on numeric types.** Incompatible constraint; use `@Positive`, `@Min`.
4. **Treating `page=abc` as a `@Min` violation.** That is a conversion error.
5. **Using route regex to replace all validation without considering 404/400.** Those two layers return different results.
6. **Catching only `MethodArgumentNotValidException`.** Can miss `HandlerMethodValidationException` when a method has direct constraints.
7. **Placing `@Validated` on controllers per older guides without checking Spring 6.1+.** May invoke AOP validation with different exceptions.
8. **Placing `BindingResult` not immediately after the object.** Fails to capture local errors for the parameter.
9. **Assuming `@Size(max=3)` stops the binder from allocating huge collections.** These are two separate limit layers.
10. **Sending nested JSON while using `@ModelAttribute`.** Wrong data-reading path; use `@RequestBody`.
11. **Using `@RequestBody` while expecting `range.min` from query params.** Sources are not automatically merged.
12. **Checking only `@NotNull` on range without cascading into PriceBounds.** Fails to check min/max.
13. **Not checking the relationship between min and max.** Individual valid fields can still form an invalid range.
14. **Binding domain entities directly into nested objects.** Risks mass assignment and authorization bypass.
15. **Assuming 400 always has the same exception/error body.** Conversion, missing params, method validation, and JSON parsing follow different paths.
16. **Using test slices that omit real validation config or advice and assuming production matches.** Test the real context.
17. **Not testing path/query URL encoding.** `curl --data-urlencode` prevents bracket/space issues in parameters.
18. **Ignoring null inside container elements.** `List<@Valid TagChoice>` does not automatically forbid null elements; combine with `List<@NotNull @Valid TagChoice>` if needed.
19. **Using `@Min` with BigDecimal for non-negative prices while ignoring precision.** Consider `@Digits`, `@DecimalMin`, and scale/rounding business constraints.
20. **Validating data in controllers while letting other services skip business checks.** HTTP validation and domain invariants complement rather than replace each other.

## 18. Pre-Merge Checklist

- [ ] Endpoint clearly defines path variables, query parameters, model attributes, and JSON body.
- [ ] IDs have type-appropriate constraints (`@Positive`/`@Min`/`@Pattern`) and handling for missing resources.
- [ ] Query keys have clear `required`/`defaultValue`/nullability semantics.
- [ ] Numbers, enums, and dates have appropriate conversion/formatting and tests for wrong types.
- [ ] Nested DTOs have `@Valid` on the right parent/field/element.
- [ ] Required fields use `@NotNull`/`@NotBlank` appropriately; not confused with `@Valid`.
- [ ] Collections have `@Size` and the binder has an auto-grow limit when using indexed model attributes.
- [ ] Cross-field relationships are checked via `@AssertTrue` or a custom class-level constraint.
- [ ] Bean Validation provider is included in dependencies.
- [ ] Class-level `@Validated` is not placed on MVC controllers if using built-in method validation without an AOP reason.
- [ ] Error handlers cover `HandlerMethodValidationException` and `MethodArgumentNotValidException` as needed, plus type conversion/JSON parse errors per contract.
- [ ] Request DTOs restrict exposed fields; nested property binding uses allowedFields on mutable form objects.
- [ ] Error responses do not leak stack traces, tokens, or sensitive data.
- [ ] Tests cover 200, 400 (constraints, nested, conversion), 404, and 415 where relevant.
- [ ] Tested against the real MVC/WebFlux runtime rather than mixing exception paths.
- [ ] Business layer still checks permissions and invariants that cannot be derived from Bean Validation.

## 19. Conclusion

Data validation in Spring Boot requires viewing **the entire request lifecycle**. `@PathVariable` and `@RequestParam` bind individual values and can enforce constraints directly at the handler method level; `@ModelAttribute` and `@RequestBody` construct DTOs via binders or message converters and recursively validate nested branches with `@Valid`. Since Spring MVC 6.1+, constraints directly on method parameters can trigger `HandlerMethodValidationException`, distinct from the `MethodArgumentNotValidException` of single-object validation. Protect APIs using narrow DTOs, type-appropriate constraints, binder limits, consistent error contracts, real request tests, and complementary domain/service validation.

## Official Documentation

- Spring Framework 6.2 — MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — MVC @ModelAttribute: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — MVC @RequestParam: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestparam.html
- Spring Framework 6.2 — MVC @PathVariable: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/pathvariable.html
- Spring Framework 6.2 — MVC @InitBinder: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2 — Spring Data Binding: https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html
- Spring Framework 6.2 — WebFlux Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html
- Spring Boot 3.5 — Bean Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
