# Ordering and Scope of Local and Global `WebDataBinder` Configuration

## 1. The Problem to Solve

In Spring MVC, when an HTTP request is mapped onto an `@ModelAttribute` parameter, the framework can create a `WebDataBinder` to assign values, convert types, format data, and run validation. An application often needs multiple levels of configuration:

- Shared policies: allowing only valid fields, using a common `ConversionService`, registering global validators.
- Policies shared across multiple controllers: adding binding/validation rules to a group of form screens.
- Policies specific to a single controller or model attribute: adding a validator or formatter suitable only for that form.

**Main question:** When the same binder receives configuration from both global and local sources, in **what order** and at **what scope** does Spring apply them, and do they **accumulate or overwrite** one another?

For Spring MVC (Servlet stack), the mental model to remember is:

1. Baseline MVC configuration (for example, converters/formatters/validators declared via MVC configuration) is applied to the binder when it is created.
2. Applicable `@InitBinder` methods from `@ControllerAdvice` are applied **before** the target controller's own `@InitBinder` methods.
3. When multiple `@ControllerAdvice` beans exist, ordering among matching advices is controlled via `Ordered` / `@Order`.
4. **The final behavior depends on each configuration operation:** `addValidators(...)` is additive, whereas `setValidator(...)` or `setAllowedFields(...)` sets/replaces the existing configuration.

Do not mistakenly assume "local always beats global" or "global always enforces an immutable rule." **Application order** is one half; **setter vs. adder semantics** is the other half.

## 2. What Is `WebDataBinder` and When Is It Created?

`org.springframework.web.bind.WebDataBinder` extends Spring's `DataBinder`, used in web environments to manage binding request properties onto Java objects and reporting errors.

For example, a request:

```text
POST /orders
Content-Type: application/x-www-form-urlencoded

code=ORD-17&quantity=3
```

can be mapped onto `OrderForm`:

```java
public class OrderForm {
    private String code;
    private Integer quantity;

    // Public constructor, getters, setters...
}
```

Spring MVC performs the following high-level steps:

```text
HTTP request
    │
    ▼
HandlerMapping / HandlerAdapter selects controller method
    │
    ▼
Create / locate model attribute and WebDataBinder
    │
    ├── Shared MVC binder configuration
    ├── Matching @InitBinder methods from @ControllerAdvice
    └── @InitBinder methods from target controller
    │
    ▼
Bind HTTP values → property conversion/formatting
    │
    ▼
@Valid / @Validated (if requested)
    │
    ▼
BindingResult / Errors or appropriate exception branch
    │
    ▼
Controller method and business logic
```

This diagram illustrates the **configuration flow for a single binder**; details such as object instantiation order, constructor binding, and argument resolution vary by parameter type. Do not use this diagram to claim that all `@RequestParam`, `@RequestBody`, or all methods share one `WebDataBinder`.

**Each request/model-attribute binding uses its own binder instance**, not a singleton `WebDataBinder` that you mutate and reuse across all users. Conversely, `@ControllerAdvice` classes, validators, or formatters registered as Spring beans may be singletons and must be thread-safe if they hold state.

## 3. Three Configuration Levels to Distinguish

| Level | Configuration Point | Primary Scope |
| --- | --- | --- |
| MVC infrastructure | `WebMvcConfigurer#addFormatters`, `getValidator`, and MVC config hooks | Shared across MVC conversion/validation mechanisms |
| Shared across controllers | `@ControllerAdvice` / `@RestControllerAdvice` containing `@InitBinder` | All controllers or a subset matched by advice selectors |
| Local to one controller | `@InitBinder` inside `@Controller` or `@RestController` | That controller; can be further narrowed by model attribute name |

### 3.1. MVC Infrastructure Configuration

Example providing a shared converter for bound parameters:

```java
@Configuration
public class ConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToOrderCodeConverter());
    }
}
```

This is an **illustrative integration snippet**, requiring imports for `@Configuration`, `WebMvcConfigurer`, `FormatterRegistry`, and `StringToOrderCodeConverter`. `WebMvcConfigurer` is for Spring MVC; for reactive WebFlux, use `WebFluxConfigurer`.

When a Jakarta Bean Validation provider is present (for example from `spring-boot-starter-validation`), MVC's default configuration typically uses `LocalValidatorFactoryBean` as the shared validator. To add a validation rule for a single form, you usually **do not need to override `WebMvcConfigurer#getValidator()`**: adding a local validator to the binder preserves the Jakarta validation baseline.

This level does not mean an HTTP JSON field will automatically use a converter added to `FormatterRegistry`. `@RequestBody` uses an HTTP message converter/Jackson to decode JSON and may then validate the object.

### 3.2. Shared Configuration with `@ControllerAdvice`

```java
@ControllerAdvice
public class CommonBindingAdvice {

    @InitBinder("order")
    public void initOrderBinder(WebDataBinder binder) {
        binder.setAllowedFields("code", "quantity");
    }
}
```

This is an illustrative snippet. `@ControllerAdvice` applies to controllers within the advice's scope, while `@InitBinder("order")` selects only binders for model attributes named `order`. In another controller with `@ModelAttribute("profile")`, this method **does not apply** to the binder named `profile`.

### 3.3. Local Configuration in a Controller

```java
@RestController
public class OrdersController {

    private final OrderCodeValidator orderCodeValidator;

    public OrdersController(OrderCodeValidator orderCodeValidator) {
        this.orderCodeValidator = orderCodeValidator;
    }

    @InitBinder("order")
    void initOrder(WebDataBinder binder) {
        binder.addValidators(orderCodeValidator);
    }

    @PostMapping("/orders")
    public String submit(
            @Valid @ModelAttribute("order") OrderForm form,
            BindingResult errors) {
        return errors.hasErrors() ? "INVALID" : "ACCEPT";
    }
}
```

This is an illustrative integration snippet requiring the corresponding classes, imports, and annotations. The `@InitBinder` method affects only binders in `OrdersController` with the matching attribute name. Another controller will not run this method merely because it has a bean of the same type `OrderForm`.

Note that `BindingResult` must stand immediately after `@ModelAttribute` to capture binding/validation errors for that exact object.

## 4. Exact Application Order: Global Before Local

The Spring MVC documentation highlights a key distinction:

- For **`@InitBinder`** and **`@ModelAttribute`**: methods from `@ControllerAdvice` are applied **before** local methods on the controller.
- For **`@ExceptionHandler`**: local methods on the controller are evaluated **before** global exception handlers.

Do not carry `@ExceptionHandler` precedence rules over to `@InitBinder`—the two mechanisms do not share the same priority order.

Example:

```java
@ControllerAdvice
@Order(100)
public class GlobalBinderAdvice {

    @InitBinder("order")
    void applyGlobal(WebDataBinder binder) {
        binder.setAllowedFields("code", "quantity");
    }
}

@RestController
public class OrdersController {

    @InitBinder("order")
    void applyLocal(WebDataBinder binder) {
        binder.addValidators(orderCodeValidator);
    }
}
```

This is a structural illustration without full constructors/fields/imports. When an `order` binder is created for `OrdersController`, the eligible global method runs **before** the local method.

**Important:** `@Order(100)` on a global advice does **not** move the advice after a controller-local `@InitBinder`. It orders **advice beans** relative to each other when multiple advices apply; local methods still run in the controller phase.

### 4.1. With Multiple `@ControllerAdvice` Beans, How Does `@Order` Work?

Example:

```java
@ControllerAdvice
@Order(10)
class BaseBindingAdvice {
    @InitBinder("order")
    void base(WebDataBinder binder) {
        // Shared configuration with earlier priority
    }
}

@ControllerAdvice
@Order(20)
class FeatureBindingAdvice {
    @InitBinder("order")
    void feature(WebDataBinder binder) {
        // Shared configuration applied after BaseBindingAdvice
    }
}
```

These are **standalone illustrative snippets**, not meant to be pasted simultaneously into the example program in section 7. Between two standard singleton advices with matching selectors, a lower `@Order` value takes earlier precedence. A class implementing `Ordered` can also supply an order. Exact behavior for request/session-scoped advices has edge cases, so keep advice configuration simple and avoid relying on implicit ordering.

**Do not rely on the execution order of multiple `@InitBinder` methods within the same advice or controller when they modify the same property.** A single clearly designed method, or separate advices with explicit `@Order`, is much easier to reason about and test.

### 4.2. Order Between MVC Baseline and `@InitBinder`

In essence, `WebBindingInitializer`/infrastructure applies shared settings such as `ConversionService`, validators, and default binder options during binder initialization; afterwards, `@InitBinder` methods customize the binder for the target handler. Thus, a local `@InitBinder` sees the default validator already configured and can append additional validators with `addValidators(...)`.

Do not think Spring runs one validation pass before global advice and then runs local afterward. The configuration hooks prepare the binder; the binder **then** performs binding and validation during argument processing.

## 5. Scope of `@ControllerAdvice` and `@InitBinder("name")`

There are two independent filters.

### 5.1. Filtering by Controller with `@ControllerAdvice`

By default, an advice applies to all framework-recognized controllers. You can narrow it with:

```java
@ControllerAdvice(annotations = RestController.class)
class RestOnlyBindingAdvice {
    // Only controllers carrying the RestController marker match.
}

@ControllerAdvice(basePackages = "demo.web.admin")
class AdminBindingAdvice {
    // Only controllers in the specified package.
}

@ControllerAdvice(assignableTypes = OrdersController.class)
class OrdersOnlyBindingAdvice {
    // Only matching controller classes/types.
}
```

These are **separate selector examples**. You can also use `basePackageClasses` to avoid hard-coded package strings. You do not need all these advices for a simple form.

Selectors are evaluated at the controller level, not by HTTP URL path or parameter count. In multi-module applications, keep advice selectors narrow enough so you do not accidentally attach a validator that does not support another module's forms.

### 5.2. Filtering by Object Name with `@InitBinder`

`@InitBinder("order")` applies to binders whose object name is `order`. For instance:

```java
public String create(
        @Valid @ModelAttribute("order") OrderForm form,
        BindingResult errors) {
    // ...
}
```

matches `"order"`.

However:

```java
public String edit(
        @Valid @ModelAttribute("profile") ProfileForm form,
        BindingResult errors) {
    // ...
}
```

does not match `"order"`.

An `@InitBinder` without attribute names applies to all matching binders **within its controller/advice scope**. An `@InitBinder({"order","quote"})` can list multiple names. Distinguish the model attribute name from the Java class name, Java variable name, or URL path: they do not have to match.

### 5.3. Quick Scope Matrix

| Method Location | Attribute Name | Effect |
| --- | --- | --- |
| Inside `OrdersController` | `@InitBinder("order")` | Only the `order` binder in `OrdersController` |
| Inside `OrdersController` | `@InitBinder` | Matching binders in `OrdersController` |
| Inside `@ControllerAdvice` with no selector | `@InitBinder("order")` | `order` binders across all controllers |
| Inside `@ControllerAdvice(assignableTypes=...)` | `@InitBinder("order")` | `order` binders only in the selected controllers |
| MVC `WebMvcConfigurer#addFormatters` | No per-binder name | Shared converters/formatters across MVC |

If a controller has no `@ModelAttribute("order")`, `@InitBinder("order")` may not be invoked for that request. To test scope properly, test requests handled through MVC, not plain Java calls like `new Controller()`.

## 6. When Multiple Configurations Touch One Binder: Additive or Overwriting?

This is the most error-prone area because **execution order alone does not determine merge semantics**.

| API | Effect on Binder | Consequence |
| --- | --- | --- |
| `binder.addValidators(v1,v2)` | Appends validators to the existing list | Preserves global Bean Validation when configured properly |
| `binder.setValidator(v)` | Replaces the current validator list with `v` | Can drop the default Jakarta validator |
| `binder.replaceValidators(v1,v2)` | Replaces the entire list with the new validators | Use when intentionally specifying the exact list to run |
| `binder.setAllowedFields("a","b")` | Sets the list of allowed fields | A later call can replace an earlier setting; does not auto-intersect |
| `binder.setDisallowedFields(...)` | Sets disallowed field patterns | Easy to miss fields as DTOs grow; prefer allowlists where appropriate |
| `binder.setDeclarativeBinding(true)` | Enables configuration allowing only constructor binding and explicitly allowed property binding | Reduces unintended property binding |
| `binder.addCustomFormatter(...)` | Registers a local formatter for a type/field | Can override behavior compared to shared formatters |
| `binder.registerCustomEditor(...)` | Registers a property editor by type or field | Can affect conversion for fields in the same scope |

### 6.1. Additive: Adding Validators

Suppose MVC already registered `LocalValidatorFactoryBean` to handle `@NotBlank` and `@Min`.

```java
@InitBinder("order")
void configure(WebDataBinder binder) {
    binder.addValidators(globalPolicyValidator, localPolicyValidator);
}
```

Additional validators record errors into the **same** `BindingResult`. If you call `setValidator(localPolicyValidator)` instead of `addValidators`, the default validator list may be replaced. In that case, Jakarta annotations on the DTO risk no longer running during this binder validation pass.

**Rule:** to append rules, use `addValidators`; use `setValidator`/`replaceValidators` only when you truly want to replace the list.

### 6.2. Replacing: `allowedFields`

Suppose global advice sets:

```java
binder.setAllowedFields("code", "quantity");
```

Then local code calls:

```java
binder.setAllowedFields("code", "quantity", "internalNote");
```

Because this is a configuration setter, the later call is **not an automatic intersection** with the earlier list. In a global-before-local model, a local controller can inadvertently widen the set of bindable properties and **weaken the global security policy**.

If global advice enforces a strict allowlist, local policies must avoid replacing it with a broader list. If a different set is genuinely needed, design a clear shared policy, combine/intersect at an authorized layer, and write request tests with disallowed fields.

### 6.3. Overlapping `Formatter` and `PropertyEditor`

A shared formatter may be registered via:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addFormatter(new DateFormatter("yyyy-MM-dd"));
}
```

In a controller, a field can be customized specifically:

```java
@InitBinder("event")
void initEvent(WebDataBinder binder) {
    binder.addCustomFormatter(new DateFormatter("dd/MM/yyyy"), "startDate");
}
```

These are **two separate illustrative snippets**, assuming `startDate` is of type `java.util.Date` with the necessary imports. Local configuration can change how the binder handles that specific field compared to the shared formatter. Do not define two conflicting formatters for the same field without tests confirming the accepted syntax.

### 6.4. Duplicate Validators or `@InitBinder` Methods

If the same validator is added by both global advice and a local controller, double registration can cause duplicate validation/errors; do not assume every list API automatically deduplicates by business logic. Assign clear ownership for each rule and use integration tests to verify per-field error counts.

## 7. Runnable Java 17 + Spring Boot 3.5.6 Example

This example designs two endpoints with the **same form class and same model attribute name** but different local scopes:

- `POST /orders`: has both global validation **and** local validation.
- `POST /quotes`: has only global validation; does not inherit `OrdersController`'s local policy.
- Global `@ControllerAdvice @InitBinder("order")` sets the allowlist `code, quantity` and adds a rule capping quantity at 5.
- Local `OrdersController @InitBinder("order")` adds a rule rejecting the code `BLOCKED`.
- Global Bean Validation from `spring-boot-starter-validation` still checks `@NotBlank` and `@Min(1)`.
- Field `internalNote` exists on the form but is not allowlisted for binding; if a request tries sending it, the controller explicitly returns `REJECTED_FIELDS`.

This is a Spring MVC Servlet-stack application. No database or template engine is needed.

### 7.1. Directory Structure

```text
binder-order-scope/
├── pom.xml
└── src/main/java/demo/binding/
    ├── BinderScopeApplication.java
    ├── OrderForm.java
    ├── QuantityPolicyValidator.java
    ├── BlockedCodeValidator.java
    ├── GlobalOrderBindingAdvice.java
    ├── FormResponses.java
    ├── OrdersController.java
    └── QuotesController.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>binder-order-scope</artifactId>
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

### 7.3. BinderScopeApplication.java

```java
package demo.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BinderScopeApplication {

    public static void main(String[] args) {
        SpringApplication.run(BinderScopeApplication.class, args);
    }
}
```

### 7.4. OrderForm.java

```java
package demo.binding;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class OrderForm {

    @NotBlank
    private String code;

    @NotNull
    @Min(1)
    private Integer quantity;

    // Has a setter, but intentionally NOT allowed to bind from HTTP requests.
    private String internalNote;

    public OrderForm() {
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public String getInternalNote() {
        return internalNote;
    }

    public void setInternalNote(String internalNote) {
        this.internalNote = internalNote;
    }
}
```

`internalNote` demonstrates the **mass assignment** risk. Even with a public setter, the global binder allows binding only `code` and `quantity`. In practice, it is even better to omit sensitive fields from the request DTO altogether.

### 7.5. QuantityPolicyValidator.java

```java
package demo.binding;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class QuantityPolicyValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return OrderForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        OrderForm form = (OrderForm) target;

        if (form.getQuantity() != null && form.getQuantity() > 5) {
            errors.rejectValue(
                "quantity", "quantityLimit",
                "Maximum 5 units per request");
        }
    }
}
```

This validator applies to both `OrdersController` and `QuotesController` because the **global advice** attaches it to the `order` binder for both.

### 7.6. BlockedCodeValidator.java

```java
package demo.binding;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class BlockedCodeValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return OrderForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        OrderForm form = (OrderForm) target;

        if ("BLOCKED".equalsIgnoreCase(form.getCode())) {
            errors.rejectValue(
                "code", "blockedCode",
                "This code cannot be used to place an order");
        }
    }
}
```

This is a **local rule** added by `OrdersController`. It uses `"BLOCKED".equalsIgnoreCase(...)` to avoid `NullPointerException` when `code` has no value.

### 7.7. GlobalOrderBindingAdvice.java

```java
package demo.binding;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.InitBinder;

@ControllerAdvice
@Order(100)
public class GlobalOrderBindingAdvice {

    private final QuantityPolicyValidator quantityPolicy;

    public GlobalOrderBindingAdvice(QuantityPolicyValidator quantityPolicy) {
        this.quantityPolicy = quantityPolicy;
    }

    @InitBinder("order")
    public void configure(WebDataBinder binder) {
        binder.setAllowedFields("code", "quantity");
        binder.addValidators(quantityPolicy);
    }
}
```

Explanation:

- `@ControllerAdvice` applies to both controllers because the example sets no narrower selector.
- `@InitBinder("order")` selects only binders for the attribute named `order`.
- `setAllowedFields("code","quantity")` sets the shared allowlist.
- `addValidators(quantityPolicy)` appends the quantity rule while keeping MVC's default validator.
- `@Order(100)` matters for ordering **relative to other advice beans**; it does not push the global method after a local method.

The `org.springframework.stereotype.Controller` import in this file is unnecessary and can be removed; it does **not** create an extra controller because the class only carries `@ControllerAdvice`. The Java code above still compiles with the unused import, though keeping imports clean is better in real projects.

### 7.8. FormResponses.java

```java
package demo.binding;

import java.util.stream.Collectors;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;

final class FormResponses {

    private FormResponses() {
    }

    static ResponseEntity<String> build(
            String type, OrderForm form, BindingResult errors) {

        // Do not treat requests with suppressed fields as valid.
        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest().body("REJECTED_FIELDS");
        }

        if (errors.hasErrors()) {
            String details = errors.getFieldErrors().stream()
                .map(error -> error.getField() + ":" + shortCode(error))
                .sorted()
                .collect(Collectors.joining(","));

            return ResponseEntity.badRequest()
                    .body("INVALID|" + details);
        }

        return ResponseEntity.ok(
            "ACCEPT|" + type
            + "|" + form.getCode()
            + "|" + form.getQuantity()
            + "|note=" + form.getInternalNote());
    }

    private static String shortCode(FieldError error) {
        String[] codes = error.getCodes();
        return codes == null || codes.length == 0
                ? "unknown"
                : codes[codes.length - 1];
    }
}
```

This helper is shared by both controllers for a uniform response format. Tests can compare generic error codes without depending on English/Vietnamese provider messages. The program explicitly rejects any request with suppressed fields; this does **not happen automatically** just from calling `setAllowedFields`. In production applications, use an error DTO and stable error codes instead of concatenating a string.

### 7.9. OrdersController.java

```java
package demo.binding;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    private final BlockedCodeValidator blockedCode;

    public OrdersController(BlockedCodeValidator blockedCode) {
        this.blockedCode = blockedCode;
    }

    @InitBinder("order")
    void localRules(WebDataBinder binder) {
        // Global advice has already been applied. Append only, do not replace.
        binder.addValidators(blockedCode);
    }

    @PostMapping(
        path = "/orders",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<String> create(
            @Valid @ModelAttribute("order") OrderForm form,
            BindingResult errors) {

        return FormResponses.build("order", form, errors);
    }
}
```

When `OrdersController` processes the `order` binder, global advice configuration runs **first**, followed by local `addValidators(blockedCode)`. Global Jakarta Bean Validation, the global custom rule, and the local custom rule can all contribute errors.

### 7.10. QuotesController.java

```java
package demo.binding;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class QuotesController {

    @PostMapping(
        path = "/quotes",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<String> quote(
            @Valid @ModelAttribute("order") OrderForm form,
            BindingResult errors) {

        // OrdersController's local @InitBinder is not present here.
        return FormResponses.build("quote", form, errors);
    }
}
```

Both controllers accept `@ModelAttribute("order")`, so the global advice applies to both. However, only `OrdersController` has the local `@InitBinder`, so `QuotesController` does **not** inherit the `blockedCode` rule.

## 8. Running the Example and Verifying Ordering/Scope

In the directory containing `pom.xml`, with Java 17+ and Maven 3.x:

```bash
mvn -q spring-boot:run
```

The server typically listens on `http://localhost:8080` if the port is free. Send commands from another bash/zsh/WSL terminal. The `text` blocks below show the **response body**, excluding HTTP headers or Spring/Maven logs.

### 8.1. Case A — Valid Form

```bash
curl -s -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ORD-17' \
  --data-urlencode 'quantity=3'
```

HTTP 200, body:

```text
ACCEPT|order|ORD-17|3|note=null
```

`internalNote` remains `null` because no input was given for it. Neither global nor local validators reported errors.

### 8.2. Case B — Error from Local Validator Only

```bash
curl -s -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=BLOCKED' \
  --data-urlencode 'quantity=2'
```

HTTP 400, body:

```text
INVALID|code:blockedCode
```

`BlockedCodeValidator` is registered on `OrdersController`, so it rejects the code `BLOCKED`.

Send **the same payload** to `QuotesController`:

```bash
curl -s -X POST 'http://localhost:8080/quotes' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=BLOCKED' \
  --data-urlencode 'quantity=2'
```

HTTP 200, body:

```text
ACCEPT|quote|BLOCKED|2|note=null
```

This shows that a local validator **does not leak** to another controller, even though both share the model attribute name `order`. Controller scope and attribute name must be evaluated **together**.

### 8.3. Case C — Global Error Across Both Controllers

```bash
curl -s -X POST 'http://localhost:8080/quotes' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ORD-17' \
  --data-urlencode 'quantity=6'
```

HTTP 400, body:

```text
INVALID|quantity:quantityLimit
```

Sending the same request to `/orders` also produces `quantityLimit`. This validator lives in the global advice applying to both controllers.

### 8.4. Case D — Default Jakarta Bean Validation Error

```bash
curl -s -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=' \
  --data-urlencode 'quantity=0'
```

HTTP 400, body:

```text
INVALID|code:NotBlank,quantity:Min
```

`@NotBlank` and `@Min` prove the Jakarta validator is still preserved because the code used `addValidators(...)` instead of `setValidator(...)`.

### 8.5. Case E — Both Global and Local Custom Validators Fail

```bash
curl -s -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=BLOCKED' \
  --data-urlencode 'quantity=6'
```

HTTP 400, body:

```text
INVALID|code:blockedCode,quantity:quantityLimit
```

Errors from both sources appear together in `BindingResult`. Output is sorted by `field:code` so it does not depend on the order in which Spring or the provider emits errors.

### 8.6. Case F — Blocking a Field Not Allowed for Binding

```bash
curl -s -X POST 'http://localhost:8080/quotes' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ORD-17' \
  --data-urlencode 'quantity=3' \
  --data-urlencode 'internalNote=FORGED'
```

HTTP 400, body:

```text
REJECTED_FIELDS
```

Global `setAllowedFields("code","quantity")` causes the binder to reject `internalNote`. The helper sees a non-empty `getSuppressedFields()` array and explicitly returns 400. This demonstrates checking field suppression: **`setAllowedFields` does not mean the framework automatically raises a `FieldError` so the controller returns 400.**

### 8.7. Case G — Type-Conversion Error Still Goes to `BindingResult`

```bash
curl -s -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ORD-17' \
  --data-urlencode 'quantity=abc'
```

The value `"abc"` cannot be converted to `Integer`; standard form binding records error code `typeMismatch` for `quantity`. The controller returns HTTP 400 with the expected body:

```text
INVALID|quantity:typeMismatch
```

This is a **binding/type-conversion** error, not `@Min` detecting a small number. If an application customizes `BindingErrorProcessor` or `MessageCodesResolver`, the exact code details may differ; align tests with actual configuration.

The commands above do not print status codes because `curl -s` outputs only the body. To view status/headers, use `curl -i` or `curl -w '%{http_code}'`. Boot logs and terminal prompts are not part of the response.

## 9. Small Changes with Big Consequences

### 9.1. Local `setValidator` Instead of `addValidators`

Suppose `OrdersController.localRules` is changed to:

```java
@InitBinder("order")
void localRules(WebDataBinder binder) {
    binder.setValidator(blockedCode);
}
```

Now the local setter can **replace the validator list configured by infrastructure and global advice**. During binder validation, `@NotBlank`, `@Min`, and `quantityLimit` may stop running, even though the annotations and global advice are still present.

This is a **replacement snippet for analysis**, not present in the main source. Never overwrite the validator list unintentionally; to keep all validators, use `addValidators`.

### 9.2. Local `setAllowedFields` Widening the List

Suppose local code adds:

```java
@InitBinder("order")
void configure(WebDataBinder binder) {
    binder.setAllowedFields("code", "quantity", "internalNote");
}
```

If an earlier advice restricted fields to `code,quantity`, the local setter widens the allowlist. Then `internalNote` from HTTP can be populated, defeating the global restriction.

**Security lesson:** Do not assume every "global rule" is immutable merely because it ran first. For setter-style binder options, downstream code must be reviewed and tested to guarantee sensitive fields cannot bind.

### 9.3. One Advice for Many Form Types

If you write:

```java
@ControllerAdvice
class BroadAdvice {

    @InitBinder
    void configure(WebDataBinder binder) {
        binder.addValidators(new OrderOnlyValidator());
    }
}
```

then the method applies to many binders and can fail when `OrderOnlyValidator.supports(targetClass)` returns `false` for another DTO. The fix is to narrow with `@InitBinder("order")`, `@ControllerAdvice` selectors, or add the validator only when the target type matches.

### 9.4. Adding Multiple `@InitBinder` Methods and Relying on Accidental Order

Do not write two `@InitBinder("order")` methods in the same class, each calling `setAllowedFields(...)` differently, and expect method names or Java source order to govern precedence. When an explicit sequence is needed, consolidate interdependent logic into one method or split into advices with explicit `@Order` and integration tests.

## 10. Important Differences with WebFlux, `@RequestBody`, and Method Validation

### 10.1. Spring MVC Differs from Spring WebFlux

This article uses the **Spring MVC Servlet stack** as its primary example. Spring WebFlux has `WebFluxConfigurer` and its own reactive controller binder, so do not copy `WebMvcConfigurer` settings to WebFlux assuming identical behavior.

Global advice before local binder ordering has a similar meaning in WebFlux annotated controllers, but reactive argument resolution, binding errors, and reactive wrapper handling can differ. Always test on your application's actual stack.

### 10.2. `@RequestBody` JSON Does Not Go Through `@ModelAttribute` Property Binding

`@Valid @RequestBody JsonRequest request` uses an HTTP message converter/Jackson for deserialization prior to validation. Therefore:

- `WebDataBinder#setAllowedFields(...)` is **not** a mass-assignment defense for JSON fields that Jackson can deserialize.
- Malformed JSON syntax fails before validation, e.g., with `HttpMessageNotReadableException`.
- To restrict JSON fields, design clear request DTOs/Jackson visibility and boundary mapping.
- Appropriate local binder validation settings may still apply in matching contexts, but do not treat `@ModelAttribute` property binding and JSON deserialization as the same pipeline.

### 10.3. `@Valid` and Controller-Level Errors

`@Valid` or `@Validated` can trigger validators on command objects; `BindingResult` must immediately follow the model attribute if the controller handles errors inline.

As of Framework 6.1, Spring MVC also has **built-in method validation** for constraints directly on parameters/return values, such as `@Min(1)` on `@RequestParam`. Method validation failures may throw `HandlerMethodValidationException`, which is not handled by a separate form's `BindingResult`.

`@InitBinder` does not replace converter binding exceptions, method-argument validation, or AOP-based service-bean constraints.

## 11. How to Test Ordering and Scope Accurately

### Test Observable Behavior Rather Than Execution-Order Logs

To prove global and local scopes do not bleed into each other, test observable contracts:

| Request | Context | Expected Outcome |
| --- | --- | --- |
| `POST /orders code=ORD-17 quantity=3` | Global + local | HTTP 200 |
| `POST /quotes code=ORD-17 quantity=3` | Global only | HTTP 200 |
| `POST /orders code=BLOCKED quantity=2` | Local code rule | HTTP 400, `blockedCode` |
| `POST /quotes code=BLOCKED quantity=2` | No local code rule | HTTP 200 |
| `POST /orders code=ORD-17 quantity=6` | Global quantity rule | HTTP 400, `quantityLimit` |
| `POST /quotes code=ORD-17 quantity=6` | Global quantity rule | HTTP 400, `quantityLimit` |
| `POST /orders code= quantity=0` | Jakarta Bean Validation | HTTP 400, `NotBlank` and `Min` |
| `POST /quotes ... internalNote=FORGED` | Global allowlist | HTTP 400, `REJECTED_FIELDS` |
| `POST /orders quantity=abc` | Binding conversion | HTTP 400, `typeMismatch` |

Use `MockMvc` or HTTP integration tests to exercise the real pipeline. Calling `new OrdersController(...).create(form, result)` directly bypasses `@InitBinder` and framework binders.

### Verifying Advice Order When It Truly Matters

If you have multiple global advices with different `@Order` values, test through the binder's final behavior rather than relying solely on logs. For example, one advice calling `setAllowedFields(...)` and another also calling `setAllowedFields(...)` will leave the later list active; however, that setup is hard to maintain and should be avoided unless clearly required.

For diagnostics, you can temporarily log inside `@InitBinder` and remove the logging after testing, but never let a global singleton advice write request-specific data into shared fields. For security rules, add regression tests asserting that sensitive fields are always rejected.

## 12. Best Practices: One Clear Policy Without Implicit Overrides

- **Keep useful defaults:** Replace global validators or conversion services only when truly needed; for form-specific rules, append local validators.
- **Use the narrowest sufficient scope:** Advice for shared policies, controller-local for controller-specific rules, `@InitBinder("name")` for the exact object.
- **Set `@Order` when multiple advices genuinely require ordering:** Never rely on classpath scan order or class names.
- **Do not assume every setting merges:** Distinguish setters from adders, especially `setAllowedFields` and `setValidator`.
- **Define dedicated request DTOs:** Never property-bind directly onto entities with server-only fields.
- **Protect central `allowedFields`:** A local setter must not inadvertently unlock fields blocked by global policy. Test requests with extra fields.
- **Keep validators stateless and thread-safe:** Avoid mutable state because they serve concurrent requests.
- **Avoid blocking I/O in converters/validators whenever possible:** Keep conversion and validation fast and predictable.
- **Do not leak rejected values:** `FieldError#getRejectedValue()` and internal field names may contain data that should not appear in public API responses.
- **Decide HTTP status explicitly:** When `BindingResult` is present inline, the controller owns returning the error view or response.
- **Distinguish controller selection from attribute selection:** `@ControllerAdvice` selectors and `@InitBinder("name")` are two separate filters.

## 13. Summary

**The configuration order for binders in Spring MVC is baseline configuration → global `@ControllerAdvice @InitBinder` → local `@Controller @InitBinder`** (within the binder initialization flow for a handler). Among global advices, use `Ordered`/`@Order` to establish explicit priority. Scope is governed by method placement, advice selectors, and the attribute name in `@InitBinder`.

The key when combining configurations is **whether an API is additive or overwriting**. `addValidators` appends rules while preserving global Bean Validation; `setValidator` and `setAllowedFields` can replace earlier settings. Testing against real requests and guarding disallowed fields is therefore just as critical as knowing execution order.

## References

- Spring Framework 6.2 — *Controller Advice*, global and local ordering: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html
- Spring Framework 6.2 — `@InitBinder` and binding configuration: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2 — *Data Binding*, allowlists, and declarative binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html
- Spring Framework 6.2 — *MVC Validation*: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 Javadoc — `DataBinder`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2 Javadoc — `@ControllerAdvice`, `@Order`, and selectors: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/web/bind/annotation/ControllerAdvice.html
- Spring Framework 6.2 Javadoc — `@InitBinder`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/web/bind/annotation/InitBinder.html
- Spring Framework 6.2 Javadoc — `ConfigurableWebBindingInitializer`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/web/bind/support/ConfigurableWebBindingInitializer.html