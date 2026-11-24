# WebDataBinder and Converting String Data into Objects in Spring MVC

## 1. What Will You Learn After This Lesson?

When a browser submits a form `quantity=3&deliveryDate=2026-12-24&code=sku-007`, every input value can arrive as a string, yet the controller needs an `Integer`, a `LocalDate`, and a domain type such as `ProductCode`. **Data binding** is the process of connecting parameter names to properties or constructor parameters of a Java object while performing the necessary **type conversion**. `WebDataBinder` is Spring MVC's specialized component for web scenarios.

After this lesson, you will know:

- How `WebDataBinder` participates in `@ModelAttribute` processing; what the responsibilities of `DataBinder`, `ConversionService`, `Formatter`, and `PropertyEditor` are.
- From input `String` to Java object: name mapping, object creation, property assignment or constructor invocation, type conversion, and error recording.
- How to distinguish **global** conversion configuration from **per-controller/model-attribute** binder configuration using `WebMvcConfigurer` and `@InitBinder`.
- How to read errors via `BindingResult`; distinguishing type conversion errors, unbindable/suppressed fields, and business validation checks.
- How to protect objects from clients assigning unauthorized properties (`mass assignment`) using DTOs and `allowedFields`.
- How to run and test a Spring Boot 3.x / Spring MVC application with Java 17+.

**Scope:** Spring MVC running on the Servlet stack (Spring Framework 6.x). `WebFlux` has a different HTTP flow; `@RequestBody` reads JSON via `HttpMessageConverter`, which is not equivalent to binding form parameters with `WebDataBinder`.

## 2. Where Does WebDataBinder Fit in the Processing Chain?

To understand the mechanism accurately, three concepts must be distinguished:

1. **Binding:** locating source values by name such as `customer`, `quantity`, or path `address.city`, and placing them into the corresponding target.
2. **Conversion/formatting:** turning `"3"` into `Integer(3)`, `"2026-12-24"` into `LocalDate`, and `"sku-007"` into `ProductCode`; when rendering a form, objects can be formatted back into text.
3. **Validation:** after binding, evaluating rules such as `quantity > 0` or `customer` being non-empty. A value that converts successfully is not necessarily valid under business rules.

High-level diagram for `@ModelAttribute`:

```text
POST /orders/form
Content-Type: application/x-www-form-urlencoded

customer=Ada&quantity=3&deliveryDate=2026-12-24&code=sku-007
       │
       ▼
DispatcherServlet → RequestMappingHandlerAdapter
       │
       ▼
@ModelAttribute argument resolver
       │
       ├─ Find or create target object (OrderForm)
       ├─ Create and initialize WebDataBinder
       │    ├─ Configure ConversionService/Formatter/PropertyEditor
       │    ├─ Run matching @InitBinder methods
       │    └─ Apply allowedFields and binding rules
       ├─ Bind data into object
       │    └─ Convert String → Java type, record errors on failure
       ├─ Run validation if requested, e.g., @Valid
       └─ Provide OrderForm + BindingResult to controller
       │
       ▼
Controller processes bound object / errors
```

`org.springframework.validation.DataBinder` handles general-purpose binding and validation. `org.springframework.web.bind.WebDataBinder` extends it for the web context, including rules for working with request parameters. Spring MVC typically creates a binder **per object to bind per request**, through the `WebDataBinderFactory` infrastructure; do not store an active `WebDataBinder` in a singleton service for reuse across requests.

`BeanWrapper` or Spring's property-access mechanism assists in locating JavaBean properties; `ConversionService`/formatters/editors handle the type transformation step. `BindingResult` holds both binding and validation errors. Do not treat `WebDataBinder` as a JSON parser or a URL routing mechanism.

### Which Data Sources Are Bound?

With `@ModelAttribute` in Spring MVC, field names can come from request parameters (query string and form-urlencoded data), URI variables, and request headers where appropriate. Request parameters take precedence over URI variables/headers when names collide. An object may come from the model/session, be created via a constructor, or be resolved via a converter in certain cases.

| Controller argument | Typical input | Primary mechanism |
| --- | --- | --- |
| `@RequestParam Integer page` | `?page=3` | Converts parameter value to method argument type |
| `@PathVariable UUID id` | `/orders/{id}` | Converts path variable value |
| `@RequestHeader LocalDate date` | Corresponding HTTP header, if a suitable converter exists | Converts header value |
| `@ModelAttribute OrderForm form` | `customer=Ada&quantity=3` | Creates/finds object, binds multiple properties, can validate |
| `@RequestBody OrderJson body` | JSON such as `{"quantity":3}` | `HttpMessageConverter` (typically Jackson), then can validate |

`@RequestParam` and `@PathVariable` also leverage the type conversion system and can be customized through appropriate conversion or binder configuration; however, they do **not** create a multi-property form object like `@ModelAttribute`.

## 3. From String to Object: What Actually Happens?

Consider the form:

```text
customer=Ada
quantity=3
deliveryDate=2026-12-24
code=sku-007
```

And the Java bean:

```java
public class OrderForm {
    private String customer;
    private Integer quantity;
    private LocalDate deliveryDate;
    private ProductCode code;

    public OrderForm() { }

    public void setCustomer(String customer) { this.customer = customer; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }
    public void setDeliveryDate(LocalDate deliveryDate) { this.deliveryDate = deliveryDate; }
    public void setCode(ProductCode code) { this.code = code; }

    // Getters are omitted in this illustrative snippet.
}
```

*This is an isolated model illustration; Chapter 7 includes a complete project example with imports, getters, setters, and tests.*

General sequence:

1. Spring determines the model attribute name (`orderForm`), locates an existing object, or creates an `OrderForm`.
2. `WebDataBinder` matches source fields against target properties of the same name. For JavaBean-style binding, setters/property paths must be appropriate.
3. `customer` is already a `String`, so it is assigned directly; `quantity` needs a converter to `Integer`; `deliveryDate` needs a date-parsing rule; `code` needs a custom rule to `ProductCode`.
4. If conversion fails, the binder records a `FieldError`, such as field `quantity` with error `typeMismatch`. Do not assume Spring will silently turn `"abc"` into `0`.
5. If the method has appropriate `@Valid`/`@Validated` annotations, validation runs after the bound object is obtained and errors can be added to `BindingResult`.
6. The controller should execute business logic only when binding and validation status are satisfactory.

Property names can be nested, such as `address.city` or `items[0].sku`. Nested binding depends on object structure, setters/constructors, auto-grow capabilities, and binder restriction policies. Do not expose arbitrary properties sent by the client: a sensitive field such as `role` or `isAdmin` can be assigned without authorization if the object design lacks safety.

### Constructor Binding and Property Binding

`@ModelAttribute` can instantiate an object through a parameterized constructor; Spring can also bind writable properties afterward. With a Java record:

```java
public record SearchFilter(String keyword, Integer page) { }
```

Input `keyword=spring&page=2` can be used to create `SearchFilter("spring", 2)` via constructor binding. For immutable types, parameter names must be properly recognized by the framework (appropriate compiler/metadata configuration), and input names must match the parameters; `@BindParam` supports renaming web parameters in Spring 6.1+.

For a JavaBean with a no-args constructor and setters, property binding is the natural path. That is what the main example below demonstrates. For untrusted input, dedicated request objects and constructor binding that limit assignable entry points are usually safer than exposing persistence entities directly to the binder.

## 4. ConversionService, Converter, Formatter, and PropertyEditor

`WebDataBinder` does not inherently understand every Java type you define. It relies on the configured conversion system.

| Component | Responsibility | When to use |
| --- | --- | --- |
| `ConversionService` | Central `canConvert`/`convert` API; coordinates converters | Shared wherever type conversion is needed |
| `Converter<S,T>` | Converts one source type to one target type | E.g., `String → ProductCode`, `String → UUID` (if customization is needed) |
| `ConverterFactory<S,R>` | Creates converters for a family of target types | Multiple enums/subtypes sharing the same rule |
| `GenericConverter` | Rules based on `TypeDescriptor`/generics/annotations | Conversions that need element types or metadata |
| `Formatter<T>` | Parses text into `T` and prints `T` as text, with `Locale` | Numbers/currencies/dates by language/region |
| `PropertyEditor` | Legacy JavaBeans API, stateful with `setAsText` operations | Integrating legacy libraries or local custom editors |

### Converter: When Rules Do Not Depend on Locale

For example, a product code with format `SKU-007`:

```java
record ProductCode(String value) {}

final class ProductCodeConverter
        implements org.springframework.core.convert.converter.Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(java.util.Locale.ROOT);
        if (!normalized.matches("SKU-[0-9]{3}")) {
            throw new IllegalArgumentException("Product code must have the form SKU-000");
        }
        return new ProductCode(normalized);
    }
}
```

`Converter` takes a `String` and returns a **domain value object**, not merely a string check. It turns `"sku-007"` into `ProductCode("SKU-007")`; `"abc"` causes conversion to fail. Throwing `IllegalArgumentException` inside a converter is one way to signal invalid input. Shared converters must be thread-safe; avoid storing request data in mutable converter fields.

### Formatter: When Dates/Numbers Depend on Input/Output Format

`@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` can be placed on a `LocalDate` property to represent ISO dates like `2026-12-24`. `@NumberFormat` supports a range of number formatting cases. When you need complex rules that depend on `Locale`, write a `Formatter<T>` with `parse(String, Locale)` and `print(T, Locale)`.

Do not call `LocalDate.parse(...)` in every controller to replace the shared binding mechanism manually. When writing a converter/formatter, check empty strings, whitespace, invalid formats, time zones (when converting types carrying point-in-time info), and whether parse/print are symmetric.

### PropertyEditor: Understanding It to Maintain Legacy Code

`PropertyEditor` is typically registered on a binder using `registerCustomEditor` inside `@InitBinder`. An editor can hold internal state, so do not arbitrarily share the same mutable instance across requests. For modern Spring MVC applications, prefer `Converter`/`Formatter` for new requirements.

## 5. Global Conversion Configuration and Scoped @InitBinder

### Global via WebMvcConfigurer

`WebMvcConfigurer#addFormatters(FormatterRegistry)` registers converters or formatters that MVC's type conversion mechanism uses across controllers:

```java
@Configuration
class WebBindingConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new ProductCodeConverter());
    }
}
```

*This snippet is excerpted from the full application in Section 7; include the exact `@Configuration`, `WebMvcConfigurer`, and `FormatterRegistry` imports as shown in that example.*

The advantage is that one `String → ProductCode` definition works for `@RequestParam ProductCode`, `@PathVariable ProductCode`, or a `ProductCode` property inside `@ModelAttribute`. Do not instantiate a new `ConversionService` in individual controllers if you intend to use the existing MVC configuration.

### Per-Controller/Model-Attribute via @InitBinder

`@InitBinder` is invoked to customize `WebDataBinder` before binding runs. It can be placed in a `@Controller`/`@RestController` for controller scope, or in a `@ControllerAdvice` when applying across multiple controllers. `@InitBinder("orderForm")` targets only the model attribute named `orderForm`.

```java
@InitBinder("orderForm")
void configureOrderForm(WebDataBinder binder) {
    binder.setAllowedFields("customer", "quantity", "deliveryDate", "code");
}
```

`allowedFields` ensures only the specified properties can be set via property binding. If a client also sends `admin=true`, Spring puts `admin` into `getSuppressedFields()` instead of setting that property (since it is not on the allowed list). `BindingResult#getSuppressedFields()` lets you detect this and decide whether to return an error. `setDisallowedFields` also exists, but an explicit **allowlist** is usually easier to control than a list of banned names.

Useful binder configuration options to know:

- `setRequiredFields("customer")` requires the field to be present during binding; this is a presence rule at the binding layer, **different** from `@NotBlank` or semantic value checks.
- `setAllowedFields(...)` and `setDisallowedFields(...)` apply to bound field names and can accept patterns; do not treat them as a firewall replacing a well-designed DTO.
- `setDeclarativeBinding(true)` (Spring 6.1+) favors constructor binding; property binding is restricted unless allowed fields are configured. Useful for immutable DTOs or when blocking undeclared property writes.
- You can register `Formatter`/`PropertyEditor` and validators per binder, though shared type conversions belong in MVC configuration.
- If you want to retrieve an existing object from the model without allowing request data binding into it, consider `@ModelAttribute(binding = false)`.

**Security note:** do not use a persistence entity containing `role`, `isAdmin`, or `creditLimit` as a free-form input model if the client is not authorized to modify those fields. Authorization and entity updates should happen in the service layer after the DTO has been validated; `allowedFields` is an additional safeguard for property binding.

## 6. BindingResult: Tracking Conversion and Validation Errors

`BindingResult` holds **object** and **field** errors. When a controller declares it, place it **immediately after** the corresponding `@ModelAttribute` parameter:

```java
@PostMapping("/example")
String submit(@ModelAttribute("orderForm") OrderForm form,
              BindingResult result) {
    if (result.hasErrors()) {
        return "invalid";
    }
    return "ok";
}
```

*This illustrates the method signature; Section 7 contains the full runnable program.*

A `FieldError` can contain `field`, `rejectedValue`, `codes`, and an error message. For example, `quantity=abc` when the target is `Integer` typically records a `typeMismatch` error for `quantity`. If `@Valid` is present and Jakarta Bean Validation is configured, errors such as `NotNull`, `Min`, and `NotBlank` are also included in the result. `@Valid` is not a prerequisite for Spring to perform **type conversion**; binding and conversion still occur without `@Valid`.

Classification:

| Request | Failure point | How to inspect |
| --- | --- | --- |
| `quantity=abc` → `Integer` | Type conversion | `hasFieldErrors("quantity")`, code `typeMismatch` |
| `deliveryDate=tomorrow` → ISO `LocalDate` | Type conversion | `FieldError` on `deliveryDate` |
| `quantity=-2` with `@Min(1)` | Validation, **not** a type conversion error | `FieldError` from Bean Validation |
| `admin=true` when only 4 other fields are allowed | Blocked by allowed fields | `getSuppressedFields()` contains `admin` |
| `customer` omitted | May remain `null` if no required/validation rule is set | Requires corresponding `setRequiredFields` or `@NotBlank` policy |

When no accompanying `BindingResult` is present for the controller to handle, binding/validation errors on `@ModelAttribute` can be turned into an exception by Spring MVC, typically mapped to the default error response. When binding in a method that has `BindingResult`, the controller is responsible for checking it; **do not proceed with business logic when `result.hasErrors()` is true**.

Note: `@Valid` checks declared constraints on the object; it does not automatically enforce business logic or access permissions. JSON parser errors for `@RequestBody` can throw exceptions such as `HttpMessageNotReadableException` before reaching the controller; diagnosis differs from form binding `FieldError`s.

## 7. Runnable Spring Boot 3 + Java 17 Example

This is a complete application demonstrating `WebDataBinder`, `@InitBinder`, `Converter<String, ProductCode>`, `@DateTimeFormat`, and `BindingResult`. We use Spring Boot **3.3.13**, Java **17+**, Maven, with no database required.

Project structure:

```text
web-data-binder-demo/
├── pom.xml
└── src/
    ├── main/java/example/BindingDemoApplication.java
    └── test/java/example/OrderControllerTest.java
```

### 7.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>web-data-binder-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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

### 7.2. BindingDemoApplication.java

All of the following classes reside in `src/main/java/example/BindingDemoApplication.java`; only `BindingDemoApplication` is a public top-level class, complying with Java compilation rules.

```java
package example;

import java.time.LocalDate;
import java.util.Arrays;
import java.util.Locale;
import java.util.stream.Collectors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class BindingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingDemoApplication.class, args);
    }
}

// Domain value type.
record ProductCode(String value) {}

// Shared converter registered in MVC configuration.
final class ProductCodeConverter implements Converter<String, ProductCode> {
    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("SKU-[0-9]{3}")) {
            throw new IllegalArgumentException(
                    "ProductCode must have the form SKU-000");
        }
        return new ProductCode(normalized);
    }
}

@Configuration
class WebBindingConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new ProductCodeConverter());
    }
}

// Input DTO for the form; do not use a persistence entity directly.
class OrderForm {
    private String customer;
    private Integer quantity;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate deliveryDate;

    private ProductCode code;

    // Property simulating a field the client is not allowed to modify.
    private boolean admin;

    public OrderForm() {}

    public String getCustomer() { return customer; }
    public void setCustomer(String customer) { this.customer = customer; }

    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }

    public LocalDate getDeliveryDate() { return deliveryDate; }
    public void setDeliveryDate(LocalDate deliveryDate) {
        this.deliveryDate = deliveryDate;
    }

    public ProductCode getCode() { return code; }
    public void setCode(ProductCode code) { this.code = code; }

    public boolean isAdmin() { return admin; }
    public void setAdmin(boolean admin) { this.admin = admin; }
}

@RestController
@RequestMapping("/orders")
class OrderController {

    // Applies only to @ModelAttribute("orderForm").
    @InitBinder("orderForm")
    void initOrderBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "customer", "quantity", "deliveryDate", "code");
    }

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    ResponseEntity<String> submit(
            @ModelAttribute("orderForm") OrderForm form,
            BindingResult result) {

        // Input blocked by allowedFields is an event that must be handled.
        if (result.getSuppressedFields().length > 0) {
            String names = Arrays.stream(result.getSuppressedFields())
                    .sorted()
                    .collect(Collectors.joining(","));
            return ResponseEntity.badRequest().body("blocked:" + names);
        }

        if (result.hasErrors()) {
            String fields = result.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .collect(Collectors.joining(","));
            return ResponseEntity.badRequest().body("invalid:" + fields);
        }

        return ResponseEntity.ok(
                "order:" + form.getCustomer()
                + "|" + form.getQuantity()
                + "|" + form.getDeliveryDate()
                + "|" + form.getCode().value());
    }

    // Demonstrates that Converter also works for a single parameter.
    @GetMapping("/by-code")
    String byCode(@RequestParam ProductCode code) {
        return "found:" + code.value();
    }
}
```

Because the demo deliberately focuses on **type conversion**, it does not declare `@NotBlank`/`@NotNull` or `@Min`. Therefore, provide all four values when calling the success endpoint; a real application needs validation for required fields before dereferencing `deliveryDate` or `code`.

### 7.3. Running and Observing the Results

In the `web-data-binder-demo` directory:

```bash
mvn test
mvn spring-boot:run
```

In another terminal, invoke sequentially:

```bash
curl -s -X POST "http://localhost:8080/orders/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "customer=Ada" \
  --data-urlencode "quantity=3" \
  --data-urlencode "deliveryDate=2026-12-24" \
  --data-urlencode "code=sku-007"

curl -s "http://localhost:8080/orders/by-code?code=sku-007"

curl -s -X POST "http://localhost:8080/orders/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "customer=Ada&quantity=abc&deliveryDate=2026-12-24&code=sku-007"

curl -s -X POST "http://localhost:8080/orders/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "customer=Ada&quantity=3&deliveryDate=2026-12-24&code=sku-007&admin=true"
```

Expected **body** output, in the exact order of the four commands (each command does not append a newline):

```text
order:Ada|3|2026-12-24|SKU-007
found:SKU-007
invalid:quantity
blocked:admin
```

Exact explanation for each case:

- Valid form: `quantity` goes from `"3"` to `Integer`; ISO date becomes `LocalDate`; code `"sku-007"` becomes `ProductCode("SKU-007")`. `OrderForm` contains the converted objects.
- Query `code=sku-007` on `@RequestParam ProductCode` uses the globally registered converter.
- `quantity=abc` cannot be converted to `Integer`: `BindingResult` contains a `FieldError` for `quantity` and the controller returns HTTP 400 `invalid:quantity`.
- The client sends `admin=true` while `@InitBinder` allows only the other four properties; the `admin` field is suppressed and the controller returns HTTP 400 `blocked:admin`. That is not a type conversion error.

With `curl -i`, the corresponding HTTP statuses are 200, 200, 400, and 400. On Windows PowerShell, if `curl` points to the `Invoke-WebRequest` alias, use `curl.exe` or an equivalent HTTP tool.

### 7.4. MockMvc Tests Verifying Each Binding Step

File `src/test/java/example/OrderControllerTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void bindsFormFieldsWithDateAndCustomProductCode() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("customer", "Ada")
                    .param("quantity", "3")
                    .param("deliveryDate", "2026-12-24")
                    .param("code", "sku-007"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                    "order:Ada|3|2026-12-24|SKU-007"));
    }

    @Test
    void usesGlobalConverterForRequestParam() throws Exception {
        mvc.perform(get("/orders/by-code")
                    .param("code", "sku-007"))
            .andExpect(status().isOk())
            .andExpect(content().string("found:SKU-007"));
    }

    @Test
    void reportsTypeMismatchOnQuantity() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("customer", "Ada")
                    .param("quantity", "abc")
                    .param("deliveryDate", "2026-12-24")
                    .param("code", "sku-007"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string("invalid:quantity"));
    }

    @Test
    void blocksUnexpectedAdminProperty() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("customer", "Ada")
                    .param("quantity", "3")
                    .param("deliveryDate", "2026-12-24")
                    .param("code", "sku-007")
                    .param("admin", "true"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string("blocked:admin"));
    }
}
```

Run `mvn test`. The four tests verify end-to-end results through MVC: successful binding, using the converter outside a form, type conversion error, and detecting a disallowed field. The demo does not need to start a Servlet server during tests; `MockMvc` processes simulated requests within the Spring Boot test context.

## 8. Common Mistakes When Applying This in Real Projects

| Symptom | Possible cause | Appropriate fix |
| --- | --- | --- |
| `quantity=abc` causes an error | String cannot be parsed as a number | Return a friendly error from `BindingResult`; display the field and reason to the user |
| Date `24/12/2026` fails ISO parsing | Expected format is `yyyy-MM-dd` | Standardize the format or use an appropriate `@DateTimeFormat`/`Formatter` |
| Object field remains `null` | Wrong field name, missing setter/constructor, conversion error, blocked field | Check input, property name, `BindingResult`, and `getSuppressedFields` |
| Custom converter is not called | Not registered in MVC `ConversionService`, wrong source/target types | Register via `WebMvcConfigurer#addFormatters`; test `@RequestParam` and form |
| `@InitBinder("orderForm")` does not apply | `@ModelAttribute` has a different name | Use the exact same attribute name |
| Two `BindingResult` parameters get mixed up | Wrong method argument order | Place immediately after the model attribute parameter it describes |
| Form returns 415 | `Content-Type` does not match `consumes` | Send form-urlencoded if the endpoint declares form-urlencoded; use the right endpoint for JSON |
| JSON binding ignores custom formatter | `@RequestBody` goes through `HttpMessageConverter`/Jackson | Configure Jackson for JSON or convert at a separate layer |
| Client can send `role=ADMIN` | Binding directly to an entity with many writable properties | Field-restricted DTO, `allowedFields`, or constructor binding; authorize in the service layer |
| Converter stores request data in a field | Converters are usually shared, leading to concurrency issues | Write stateless converters that hold no request state |

To debug, you can set breakpoints in `@InitBinder`, the converter's `convert()`, and the controller, and inspect `BindingResult`. For nested data, test inputs like `address.city`/`items[0].sku` and check the DTO structure. Enable detailed logging only as needed in development; avoid printing sensitive request information in production.

### Practical Error-Handling Workflow

1. **Define the input contract:** which fields are accepted, data types, formats, required fields, business rules.
2. **Convert types:** rely on consistent converters/formatters, handling invalid values with errors rather than silent defaults.
3. **Block unauthorized fields:** DTO + `allowedFields` or constructor binding; inspect suppressed fields when needed.
4. **Validate:** use Jakarta Bean Validation/validators for rules beyond type conversion.
5. **Handle errors:** respond with HTTP 400 clearly identifying invalid fields, while avoiding exposure of internal details or sensitive values.
6. **Call the service:** only after the DTO is valid; the service is responsible for business logic, authorization, and mutating entities.

## 9. Self-Check Questions

1. When sending `quantity=7`, does converting `"7"` to `Integer` belong to binding or validation? **Answer:** type conversion inside the binding process; validation checks validity afterward.
2. When sending `quantity=abc` to an `Integer`, where is the error located if the controller has a `BindingResult`? **Answer:** a field error on `quantity`, typically with code `typeMismatch`.
3. Which component does `@RequestBody ProductInput` use to read JSON? **Answer:** `HttpMessageConverter` (typically Jackson for JSON); do not confuse it with form property binding.
4. Does `@InitBinder("orderForm")` automatically apply to every DTO? **No.** It targets the `orderForm` attribute within the appropriate controller or advice scope.
5. Where should you place a `String → ProductCode` converter needed across multiple controllers? **Answer:** shared MVC configuration, such as `WebMvcConfigurer#addFormatters`.
6. Is `@Valid` required for a `String` to become a `LocalDate`? **No.** Formatting/conversion and validation are two distinct steps.
7. Why is `setAllowedFields` useful even if a DTO has an `admin` field? **Because it restricts property binding via a whitelist**; the client cannot arbitrarily assign fields outside the list.
8. When using `@ModelAttribute("orderForm")` and `BindingResult`, how must they be positioned? **Adjacent to each other** in the controller method signature.

## 10. Official Documentation

- [Spring Framework 6.2 — @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html): purpose of `WebDataBinder`, `@InitBinder` scope, `allowedFields`, and `declarativeBinding`.
- [Spring Framework 6.2 — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): creating/binding model attributes, constructor/property binding, `BindingResult`.
- [Spring Framework 6.2 — MVC Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html): registering formatters/converters via `WebMvcConfigurer`.
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `Converter`, `ConverterFactory`, `ConversionService`, `TypeDescriptor`.
- [Spring Framework — Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): `Formatter`, locale-aware parsing/printing.
- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html): distinguishing HTTP body conversion from `WebDataBinder`.
