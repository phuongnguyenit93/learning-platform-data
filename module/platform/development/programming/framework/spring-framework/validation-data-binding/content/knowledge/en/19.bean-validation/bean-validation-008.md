# @Valid and Triggering Cascaded Validation in Spring

## 1. Learning Objectives and the Real-World Problem

Suppose an API receives an order containing an order code, a shipping address, and multiple line items. The data shape is not flat:

```text
CreateOrderRequest
├── code: String
├── shippingAddress: Address
│   ├── receiverName: String
│   └── city: String
└── lines: List<LineItem>
    ├── [0] sku: String, quantity: int
    └── [1] sku: String, quantity: int
```

If `@NotBlank` is placed only on `Address.city`, validating `CreateOrderRequest` **does not automatically descend into** `shippingAddress`. Similarly, constraints inside each `LineItem` do not run automatically when only the parent object is validated. To make the validator (Bean Validation provider) traverse from the parent object to related objects, mark **the graph edges** with `@Valid`.

By the end of this lesson, you should be able to explain:

1. What `@Valid` means and how it differs from constraints such as `@NotNull`, `@NotBlank`, and `@Positive`.
2. What is required for validation to begin: an explicit call to `Validator.validate(...)` or a Spring integration triggering validation.
3. How `@Valid` cascades into child objects, collections, container elements, and multiple levels, including the `null` case.
4. How `@Valid` on `@RequestBody`/`@ModelAttribute` in Spring MVC affects request data, errors, and HTTP responses.
5. How to distinguish `@Valid`, `@Validated`, validation groups, and method validation, and avoid confusing this with JPA cascade.
6. How to verify behavior with Java 17+, Hibernate Validator, JUnit, and Spring MockMvc.

**Version context:** Examples use `jakarta.validation.*` (Jakarta Bean Validation 3.x), Spring Framework 6+, and Spring Boot 3.x. Spring Boot 2.x projects use the legacy `javax.validation.*` namespace; do not mix both namespaces in the same module.

## 2. What Does @Valid Actually Do?

`jakarta.validation.Valid` marks a reference/path for **cascaded validation** (often described as recursive or propagating validation). When the provider validates a parent bean, it follows the marked element and evaluates constraints on the child bean. If the child bean also has another `@Valid` property, traversal continues across multiple levels.

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

class Address {
    @NotBlank
    String city;
}

class Order {
    @NotNull
    @Valid
    Address shippingAddress;
}
```

This is an **illustrative fragment**, not a standalone Java program. When calling `validator.validate(order)`:

- `@NotNull` on `shippingAddress` asks: is the reference non-`null`?
- `@Valid` on `shippingAddress` requests checking constraints **inside** the `Address` object when it exists.
- `@NotBlank` on `Address.city` is what actually detects an empty or whitespace-only city name.
- If `@Valid` is omitted on `Order.shippingAddress`, `Address.city`'s `@NotBlank` constraint is not reached during a normal `validate(order)` pass.
- If `shippingAddress == null`, the provider **skips the cascade step**. `@Valid` **does not enforce non-null on its own**; `@NotNull` is what still flags the missing address.

There is no standalone `@Valid` constraint meaning "value must be valid". It is a directive to **traverse a reference to another bean**. A child bean with no constraints will produce no errors simply by having `@Valid`.

### 2.1. @Valid does not run automatically on field assignment

For example, `order.setShippingAddress(address)` (or instantiating an object with `new`) only changes Java state; it **does not trigger** Bean Validation immediately. A validation invocation point is required:

- Explicitly calling `jakarta.validation.Validator.validate(order)`.
- Spring MVC binding a parameter such as `@Valid @RequestBody OrderRequest` and using the configured Bean Validation provider.
- Method validation, persistence integration, or another platform mechanism **actually** calling the provider at the right time.

In other words, `@Valid` is **metadata describing traversal paths**; the provider and integration point decide **when to run**. Putting annotations on a DTO and never calling or triggering a validator results in no checks occurring.

### 2.2. @Valid differs from @NotNull

| Annotation | Function | If the Child Object Is `null` |
| --- | --- | --- |
| `@Valid` | Cascades into constraints inside the child bean | Skips cascade, produces no error from `@Valid` alone |
| `@NotNull` | Requires this value itself to be non-`null` | Produces an error |
| `@NotBlank` | String must be non-null and contain a non-whitespace character | Produces an error for `null`/`""`/`"  "` |
| `@NotEmpty` | Supported String, Collection, Map, or Array must be non-null/non-empty | Produces an error if null/empty |
| `@Size(min=1)` | Constrains size of supported types | `null` is normally valid; pair with `@NotNull` if needed |
| `@Positive` | Numeric value must be greater than 0 | 0/negative fails; `null` is normally valid |

An order model often needs `@NotNull @Valid Address shippingAddress` **together**, and `@NotEmpty List<@Valid LineItem> lines` to require elements in the list and then validate each element.

## 3. Object Graphs: Every Level Needs a @Valid Path

Consider three object levels:

```java
class Country {
    @NotBlank String isoCode;
}

class Address {
    @NotBlank String city;
    @Valid Country country;
}

class Customer {
    @Valid Address address;
}

class Order {
    @Valid Customer customer;
}
```

This is condensed code; annotations in the fragment need imports from `jakarta.validation.*`. When the provider executes `validator.validate(order)`, the traversal path is:

```text
Order [validation starts]
  |
  | @Valid on customer
  v
Customer
  |
  | @Valid on address
  v
Address
  |  +-- @NotBlank(city) is checked
  |
  | @Valid on country
  v
Country
     +-- @NotBlank(isoCode) is checked
```

Removing `@Valid` on **any edge** cuts off traversal from the parent across that edge. For instance, removing `@Valid` on `Customer.address` means calling `validate(order)` will not reach `Address.city` or `Country.isoCode` along this path, even though they have constraint annotations.

This is completely different from whether each child class itself contains `@NotBlank`. Constraints on child beans still exist and will run if you **directly** call `validator.validate(address)`; only the traversal starting from `order` is missing.

Bean Validation constructs a `Set<ConstraintViolation>` containing property paths from the root, such as `customer.address.city` and `customer.address.country.isoCode`. Violation traversal/return order should not be treated as a stable display contract; when stable responses are needed, sort explicitly by field/path.

### 3.1. What if there are reference cycles?

Business graphs can have cycles, like `Department.manager.department`. A specification-compliant Bean Validation provider must avoid infinite recursion: an instance already visited on the **current traversal path** is not re-traversed along that same path. An instance referenced from multiple distinct branches may still be validated on those other paths. You do not need to write custom cycle detection just for `@Valid` to work.

## 4. @Valid with List, Map, Optional, and Container Elements

In modern Jakarta Bean Validation, annotations can be placed on **type arguments**:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.util.List;
import java.util.Map;
import java.util.Optional;

class LineItem {
    @NotBlank String sku;
    @Positive int quantity;
}

class Address {
    @NotBlank String city;
}

class Order {
    @NotEmpty
    List<@NotNull @Valid LineItem> lines;

    Map<String, @Valid Address> addressByType;

    Optional<@Valid Address> optionalAddress;
}
```

- `List<@Valid LineItem>`: the provider enters each `LineItem` element to apply its constraints.
- `List<@NotNull @Valid LineItem>`: also requires elements not to be null. `@Valid` alone skips null elements.
- `@NotEmpty` on the list: requires the list itself to have at least one element, but **does not** replace validating fields inside each element.
- `Map<String, @Valid Address>`: requests validating `Address` **values**; does not constrain keys. You can place annotations on the key type argument if needed and the provider has a matching extractor.
- `Optional<@Valid Address>`: validates the bean when `Optional` holds a value; does not turn `Optional.empty()` into a required-field error. If presence is required, design constraints to match the model/contract.

For nested containers like `List<List<@Valid LineItem>>`, put `@Valid` on the type argument containing the values to cascade. No flattening is needed for validation.

**Do not place `@Valid` on both a container and its corresponding type argument just "to be extra sure"**, e.g., avoid `@Valid List<@Valid LineItem>`. The Jakarta Bean Validation specification advises choosing **one cascade location** for the same path to avoid validating elements twice.

A common mistake is writing `@Valid List<LineItem>` directly on a **controller parameter** and expecting the entire HTTP handling to behave identically to a command object. Spring MVC has specific conditions for collection-typed method arguments. For requests with multiple items, using a wrapper DTO `OrderRequest` with `List<@Valid LineItem>` is usually easier to design, test, and report errors for.

## 5. Runnable Java 17+ Example: Observing Cascading in Practice

To see how including or omitting `@Valid` changes results, let's build a program using **Jakarta Bean Validation and Hibernate Validator**. Unlike plain Java examples, annotations/specifications require a provider library at runtime; running `javac` without the classpath is not enough.

Create the directory structure:

```text
cascade-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── CascadeValidationDemo.java
```

### 5.1. pom.xml (Maven, Java 17)

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>cascade-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

This configuration pins library versions so the example is reproducible. In real Spring Boot projects, let Boot's BOM/dependency management select compatible versions instead of adding these mechanically.

### 5.2. CascadeValidationDemo.java

```java
package example;

import java.util.List;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public final class CascadeValidationDemo {

    public record Address(@NotBlank String city) {}

    public record LineItem(
            @NotBlank String sku,
            @Positive int quantity) {}

    public record OrderRequest(
            @NotBlank String code,
            @NotNull @Valid Address address,
            @NotEmpty List<@Valid LineItem> lines) {}

    // Has constraint on address but NO @Valid.
    public record OrderWithoutCascade(@NotNull Address address) {}

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            OrderRequest invalid = new OrderRequest(
                    "ORD-7",
                    new Address(" "),
                    List.of(
                            new LineItem("", 2),
                            new LineItem("BOOK", 1)));

            Set<ConstraintViolation<OrderRequest>> failures =
                    validator.validate(invalid);

            boolean hasAddressError = failures.stream().anyMatch(
                    v -> v.getPropertyPath()
                            .toString().equals("address.city"));

            boolean hasLineError = failures.stream().anyMatch(
                    v -> v.getPropertyPath()
                            .toString().endsWith(".sku"));

            System.out.println("violations=" + failures.size());
            System.out.println("addressError=" + hasAddressError);
            System.out.println("lineError=" + hasLineError);

            OrderWithoutCascade withoutCascade =
                    new OrderWithoutCascade(new Address(" "));

            System.out.println("withoutCascade="
                    + validator.validate(withoutCascade).size());

            OrderRequest missingAddress = new OrderRequest(
                    "ORD-8", null, List.of(new LineItem("BOOK", 1)));

            System.out.println("nullAddress="
                    + validator.validate(missingAddress).size());
        }
    }
}
```

Run in `cascade-demo` with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.CascadeValidationDemo
```

Lines printed by `System.out.println` (provider/build tools may emit their own logs):

```text
violations=2
addressError=true
lineError=true
withoutCascade=0
nullAddress=1
```

Explanation of each result:

- `violations=2`: `address.city` contains only whitespace, `lines[0].sku` is empty; both are rejected by `@NotBlank`. `LineItem.quantity` is valid and `lines` is non-empty.
- `addressError=true` and `lineError=true`: paths from the root show the provider **entered child objects**. With Hibernate Validator, list element paths are typically `lines[0].sku`.
- `withoutCascade=0`: `OrderWithoutCascade`'s `address` is non-null so `@NotNull` passes; because **`@Valid` is missing**, constraints on `Address.city` do not run from this root.
- `nullAddress=1`: `address` is null; `@Valid` skips cascading, while `@NotNull` reports the missing value. All other fields are valid.

`ValidatorFactory` can be shared according to application configuration; `Validator` is normally shared and invoked repeatedly. The CLI example creates the factory once and closes it at the end. In Spring Boot, the framework typically manages the validator bean so you avoid creating factories per request.

## 6. Triggering @Valid at Spring MVC Entry Points

The following practical example uses Spring Boot 3.x, Spring Web MVC, and a Bean Validation provider. With Spring Boot-managed Maven, the needed dependencies are:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

This is a **dependency fragment for a Spring Boot application that already has a `pom.xml`/BOM**, not a standalone `pom.xml`. The DTOs and controller below belong to a Boot project with an appropriate Spring Boot entrypoint and component scan.

### 6.1. DTOs for HTTP requests

**File `src/main/java/com/example/orders/Address.java`:**

```java
package com.example.orders;

import jakarta.validation.constraints.NotBlank;

public record Address(
        @NotBlank String receiverName,
        @NotBlank String city) {}
```

**File `src/main/java/com/example/orders/LineItem.java`:**

```java
package com.example.orders;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record LineItem(
        @NotBlank String sku,
        @Positive int quantity) {}
```

**File `src/main/java/com/example/orders/CreateOrderRequest.java`:**

```java
package com.example.orders;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
        @NotBlank String code,
        @NotNull @Valid Address shippingAddress,
        @NotEmpty List<@NotNull @Valid LineItem> lines) {}
```

Pay attention to two locations:

- `@NotNull @Valid Address shippingAddress`: both requires an address and validates `receiverName`/`city` inside it.
- `@NotEmpty List<@NotNull @Valid LineItem> lines`: requires line items, ensures each item is non-null, and validates `sku`/`quantity` on each item. Do not also put `@Valid` on the `lines` field itself when already cascading on the `LineItem` type argument.

### 6.2. Controller to trigger validation

**File `src/main/java/com/example/orders/OrderController.java`:**

```java
package com.example.orders;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @PostMapping("/orders")
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreateOrderRequest request) {

        // In a real application: delegate to service after validation.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Explaining the two distinct `@Valid` placements:

1. **`@Valid` on the controller parameter**: the point instructing Spring MVC to validate `CreateOrderRequest` after Jackson deserializes the body. Without it (and without another configuration/validation doing the same), MVC does not automatically scan DTO constraints.
2. **`@Valid` on `CreateOrderRequest.shippingAddress` or on the `LineItem` type argument**: defines which branches the provider must descend into **once root validation has begun**.

Thus, many applications need `@Valid` at **both the request entry point** and **nested associations inside DTOs**, because the two annotations serve **two different responsibilities**.

### 6.3. Valid request and invalid request

Valid request:

```http
POST /orders
Content-Type: application/json

{
  "code": "ORD-7",
  "shippingAddress": {
    "receiverName": "An",
    "city": "Ha Noi"
  },
  "lines": [
    { "sku": "BOOK-1", "quantity": 2 }
  ]
}
```

With the controller above, the expected result is **HTTP 201 Created, empty body**. This example only demonstrates behavior when validation succeeds; it does not persist orders.

Multi-level invalid request:

```http
POST /orders
Content-Type: application/json

{
  "code": "ORD-7",
  "shippingAddress": {
    "receiverName": "An",
    "city": " "
  },
  "lines": [
    { "sku": "", "quantity": 0 }
  ]
}
```

Expected result: Spring MVC rejects the request, typically **HTTP 400 Bad Request**. Errors can carry property paths `shippingAddress.city`, `lines[0].sku`, and `lines[0].quantity`.

If the request simply sends `"shippingAddress": null`, the parent field's `@NotNull` error appears, while constraints inside `Address` **are not checked** because the child object does not exist.

If `lines` is `[]` or `null`, `@NotEmpty` flags the error; there are no elements to cascade into. With a `null` element, `@NotNull` on the type argument flags that element.

**The JSON error response shape is not fixed**: it depends on Spring Boot/Spring Framework version, Problem Details configuration, and `@ControllerAdvice`. Only infer status and `BindingResult`/exception content from known configuration, rather than hardcoding one generic error JSON across all applications.

## 7. Where Does Spring MVC Report Errors?

### 7.1. Binding, validation, and handlers

Common flow with `@RequestBody`:

```text
JSON request
    |
    v
Jackson deserializes -> CreateOrderRequest
    |
    v
Spring MVC requests validation due to @Valid on parameter
    |
    v
Bean Validation provider checks constraints on root
    |
    +--> follows @Valid shippingAddress -> Address
    |
    +--> follows @Valid LineItem -> each LineItem
    |
    v
  Violations?
     |                    |
     No                   Yes
     |                    |
invoke controller    typically HTTP 400
```

Type mismatches during deserialization (e.g., `quantity: "nonsense"` when Jackson cannot convert to int) can fail **before reaching** Bean Validation. `@Valid` does not repair invalid JSON types and is not a parser.

### 7.2. Important exceptions

In modern Spring MVC:

- For normal **object parameter** validation via `@Valid @RequestBody` or `@Valid @ModelAttribute`, failures go through `MethodArgumentNotValidException` when no `BindingResult`/`Errors` immediately follows the parameter.
- When a method requires **method validation** because constraints are placed directly on parameters (such as `@Min`, `@NotBlank`) or the return value, Spring MVC 6.1+ can use `HandlerMethodValidationException`. Method validation also covers nested checks declared via `@Valid`.
- `@Valid` **is not a constraint annotation**: adding `@Valid` alone does not force Spring MVC to switch to method validation.
- With `@ModelAttribute` and `BindingResult`, the controller can receive errors and render a view or message itself. Place `BindingResult` **immediately after** the bound/validated object if you want to handle errors inside the method; do not place it after another parameter.

Do not assume every validation error produces the same exception; test the specific controller path, especially when constraints appear on method parameters.

### 7.3. Bean Validation vs Spring Validator

Jakarta Bean Validation uses `jakarta.validation.Validator` and constraint annotations like `@NotBlank`; Spring also has `org.springframework.validation.Validator` and `Errors`. `LocalValidatorFactoryBean` is the crucial bridge allowing Spring to integrate a Bean Validation provider into data binding.

When Spring MVC has a Bean Validation provider on the classpath and standard configuration, MVC can register a global validator. In Spring Boot, `spring-boot-starter-validation` is the common way to supply the provider. Having only the annotation API without a compatible provider/configuration does not mean validations actually run.

## 8. Integration Testing with MockMvc

A test suite should prove **both** activation at the controller and cascading into nested objects. The files below assume the DTOs/controller from section 6 and a properly configured Spring Boot application.

**File `src/test/java/com/example/orders/OrderControllerTest.java`:**

```java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void rejectsInvalidNestedFields() throws Exception {
        String json = """
                {
                  "code": "ORD-7",
                  "shippingAddress": {
                    "receiverName": "An",
                    "city": " "
                  },
                  "lines": [
                    { "sku": "", "quantity": 0 }
                  ]
                }
                """;

        mvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(result -> {
                    assertTrue(
                            result.getResolvedException()
                                instanceof MethodArgumentNotValidException);
                    var ex = (MethodArgumentNotValidException)
                            result.getResolvedException();
                    assertTrue(ex.getBindingResult()
                            .hasFieldErrors("shippingAddress.city"));
                    assertTrue(ex.getBindingResult()
                            .hasFieldErrors("lines[0].sku"));
                    assertTrue(ex.getBindingResult()
                            .hasFieldErrors("lines[0].quantity"));
                });
    }

    @Test
    void acceptsValidNestedFields() throws Exception {
        String json = """
                {
                  "code": "ORD-8",
                  "shippingAddress": {
                    "receiverName": "An",
                    "city": "Ha Noi"
                  },
                  "lines": [
                    { "sku": "BOOK-1", "quantity": 1 }
                  ]
                }
                """;

        mvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isCreated());
    }
}
```

`@WebMvcTest` needs compatible test dependencies (typically `spring-boot-starter-test`), and the test environment must actually have a Bean Validation provider. This test verifies field paths from the HTTP layer rather than merely checking that an annotation exists in source code.

Use another test with `shippingAddress: null` to prove `@NotNull` is applied on the parent field. Add a test with `lines: []` to prove `@NotEmpty` works independently of element cascading. In a practice environment you can temporarily remove `@Valid` on an association to watch the nested field errors disappear, though never ship the unvalidated version.

## 9. Distinguishing @Valid, @Validated, and Method Validation

Both annotations appear in Spring projects, yet they serve different purposes.

| Scenario | @Valid (Jakarta) | @Validated (Spring) |
| --- | --- | --- |
| Request DTO `@RequestBody` | Triggers root validation in MVC, using `Default` group by default | Also supports validating and **selecting groups** when groups are passed |
| Child object field | Used to cascade deeply into child beans | Does not replace `@Valid`'s cascade mechanism |
| Container element `List<@Valid Item>` | Supported in Jakarta Bean Validation | Do not use `@Validated` to mark type arguments instead of `@Valid` |
| Service bean | `@Valid` on method parameters describes cascading **when method validation is enabled** | `@Validated` at bean level is typically used to enable AOP method validation in Spring |
| Selecting validation groups | `@Valid` has no group parameter | `@Validated(Create.class)` selects groups at Spring entry points |

### 9.1. Why might @Valid on a service parameter not run?

```java
import jakarta.validation.Valid;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class OrderService {
    public void submit(@Valid CreateOrderRequest request) {
        // Business logic after method validation passes.
    }
}
```

This is a fragment of a Spring project with method validation infrastructure. On regular Spring beans, Spring AOP must be configured/registered; calling the service **through the Spring proxy** checks constraints on method arguments. Calling `new OrderService()` directly or internal self-invocation via `this.submit(...)` can bypass the proxy. Thus **merely having `@Valid` on a normal Java method does not automatically run method validation**.

Spring MVC 6.1+ has dedicated built-in method validation for controllers, without needing an AOP method-validation proxy in appropriate cases. Do not mix service bean rules with MVC handler method mechanics. When using MVC's built-in method validation, note that class-level `@Validated` on the controller can route method validation through an AOP proxy instead of the built-in MVC mechanism.

### 9.2. How do validation groups propagate?

Constraints have not only types but also **groups**. When no group is selected, the provider checks `jakarta.validation.groups.Default` by default. When crossing `@Valid`, the active group is propagated down to child beans **unless** a group conversion rule applies.

Example:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

interface FullCheck {}

class Detail {
    @NotBlank(groups = FullCheck.class)
    String externalCode;
}

class Request {
    @Valid
    @ConvertGroup(from = Default.class, to = FullCheck.class)
    Detail detail;
}
```

When validating `Request` under the `Default` group, `@ConvertGroup` translates the group for the `detail` branch to `FullCheck`, so `Detail.externalCode` is evaluated. Without `@ConvertGroup` and when validating only `Default`, a constraint declared **solely in `FullCheck`** would not run.

`@Valid` does not automatically convert all groups to `Default` or `FullCheck`; it propagates groups strictly per policy. In Spring MVC, `@Validated(FullCheck.class)` on the parameter is one way to specify groups at the root. For complex rules, test group propagation explicitly across every branch.

## 10. What @Valid Does Not Do

- **Does not determine whether input data is valid JSON syntax.** Jackson/data binder must construct the object first.
- **Does not automatically ensure an object/collection is non-null.** `@NotNull`/`@NotEmpty` or an equivalent constraint is needed.
- **Does not replace constraints on the child bean.** A field with `@Valid` whose child properties have no constraints produces no errors to report.
- **Does not automatically validate a nested object just because its class has annotations.** There must be a `@Valid` path from the object being validated.
- **Does not sanitize or filter data against attacks.** Validation does not replace authorization, business checks, access control, escaping, or prepared SQL.
- **Is not the same as JPA cascade.** `@Valid` propagates constraint checking across the object graph; JPA's `CascadeType.PERSIST`, `MERGE`, `REMOVE` govern entity lifecycle management. One does not automatically enable the other.
- **Is not a guarantee that validation runs everywhere.** Controllers, services, batch jobs, message consumers, and persistence paths can have different trigger points; test actual entry points individually.
- **Does not guarantee error ordering.** Bean Validation returns a violation set; do not rely on `Set<ConstraintViolation<?>>` order for fixed display ordering.

## 11. Recommended Testing Matrix

For `CreateOrderRequest` in section 6, use this matrix to avoid blind spots:

| Case | Input | Expected |
| --- | --- | --- |
| Valid structure | Both Address and LineItem valid | Validation passes |
| Invalid root | `code = ""` | `code` error from `@NotBlank` |
| Null association | `shippingAddress = null` | `shippingAddress` error from `@NotNull` |
| Invalid nested field | `shippingAddress.city = " "` | `shippingAddress.city` error via `@Valid` cascade |
| Null container | `lines = null` | `lines` error from `@NotEmpty` |
| Empty container | `lines = []` | `lines` error from `@NotEmpty` |
| Null item | `lines = [null]` | Element error from `@NotNull` on type argument |
| Invalid nested item | `lines[0].sku = ""` | `lines[0].sku` error |
| Invalid quantity | `lines[0].quantity = 0` | `lines[0].quantity` error |
| Two items, only one invalid | `lines[1].sku = ""` | Error at second element, not applied to valid item |
| Multi-level nesting | Child bean also has a `@Valid` field | Deep-level constraints are validated |
| Missing annotation on association | Remove `@Valid` on a branch in an isolated test | Deep constraints on that branch are not reached |
| Wrong JSON type | `quantity = "abc"` | Deserialization/binding error can occur before validation |
| Unproxied service | Calling `new Service()` | Method validation does not run from annotations alone |

For stable tests, assert **field/property path names, required error counts or categories, and HTTP status**, avoiding asserting entire English messages since validation text can change by locale/message bundle.

## 12. Common Mistakes and Fixes

1. **Putting `@NotBlank` on a child bean but forgetting `@Valid` on the parent bean:** add `@Valid` along the reference path; test the path from root.
2. **Having `@Valid` on the child bean but forgetting `@Valid` on the controller parameter:** add `@Valid @RequestBody` or `@Validated` at the right entry point so MVC triggers validation.
3. **Believing `@Valid` also makes a child field required:** add `@NotNull`, and add `@NotEmpty` if a container cannot be empty.
4. **Validating a list only with `@NotEmpty`:** use `List<@Valid LineItem>` to check every element; add `@NotNull` for individual elements if needed.
5. **Placing `@Valid` on both the container and its type argument:** pick one cascade location to avoid double-checking.
6. **Importing `javax.validation.Valid` in a Spring Boot 3+ project:** switch to `jakarta.validation.Valid` and align Jakarta dependencies.
7. **Adding only the validation API without a runtime provider:** include a provider like Hibernate Validator, or Spring Boot's validation starter.
8. **Assuming controller tests automatically test service methods:** method validation needs its own trigger; test services via Spring proxy or direct `Validator` calls.
9. **Putting `@Valid` on a root collection parameter and expecting DTO-like behavior:** verify Spring MVC's rules, and consider a command object wrapper for clear error reporting.
10. **Believing `@Valid` and `@Validated` are completely identical:** `@Validated` also supports validation groups and Spring method validation.
11. **Confusing validation cascade with persistence cascade:** they are two independent mechanisms.
12. **Asserting only HTTP 400:** also assert field paths like `shippingAddress.city` and `lines[0].sku` to prove validation actually descended into children.

## 13. Summary of Implementation Rules

1. Start at a **validation trigger**: `Validator.validate(root)`, `@Valid @RequestBody`, `@Validated`, or configured method validation.
2. Place constraints on **values to check** (`@NotBlank`, `@Positive`...) and place `@Valid` on **reference edges to child beans**.
3. Pair `@NotNull`/`@NotEmpty` to handle **missing objects** and **empty containers**; `@Valid` only cascades when elements exist.
4. For List/Map/Optional, use container element annotations such as `List<@Valid LineItem>`; do not duplicate `@Valid` on both the container and the same type argument.
5. Use `jakarta.validation.*` for Spring Boot 3+, verify an active provider, and test at both bean and MVC levels.
6. When method constraints/groups are present, understand the differences among `MethodArgumentNotValidException`, `HandlerMethodValidationException`, `@Validated`, and Spring proxy validation.
7. Prove via tests that an error **deep in the object graph** is detected at the right path, even when the root looks valid.

### References

- [Jakarta Bean Validation 3.0 Specification — Object graph validation and container element cascade](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html).
- [Spring Framework — Validation for @RequestMapping methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html).
- [Spring Framework — Configure a Validator for Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html).
- [Spring Framework — Java Bean Validation and Method Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html).
- [Hibernate Validator 8 Reference Guide](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/).
