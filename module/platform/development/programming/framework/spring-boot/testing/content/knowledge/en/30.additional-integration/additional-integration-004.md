# Testing Method Validation and How It Differs from Direct Java Object Calls

**Method validation** is the mechanism for enforcing Bean Validation constraints on **parameters and return values of a method**, such as `@NotBlank String sku`, `@Min(1) int quantity`, or `@NotNull` on a return value. In a Spring Boot application, annotations appear directly on the service, yet that does not mean every Java call automatically checks the data. Test outcomes can differ completely between:

- `new InventoryService().reserve(" ", 0)`: a **plain Java object** call that does not pass through an AOP proxy; annotations are not automatically enforced.
- `@Autowired InventoryService service; service.reserve(" ", 0)`: a call through a **Spring-managed bean proxy**, which `MethodValidationPostProcessor` can intercept and validate when configured properly, such as annotating the class with `@Validated`.
- `this.reserve(" ", 0)` inside `InventoryService` itself: **self-invocation**, which normally invokes the target object directly and bypasses Spring AOP advice.
- `MockMvc.perform(post(...))`: an HTTP request deserialized by Spring MVC, validated via `@Valid @RequestBody` or **MVC built-in method validation** on the controller signature; this is **not** a plain Java call.
- `validator.validate(object)` or `validator.forExecutables().validateParameters(...)`: **explicitly runs validation**, even when the object is not managed by Spring.

This knowledge lesson belongs to the **Additional integration** group in **Spring Boot - testing**, focusing directly on **"Testing method validation and how it differs from direct Java object calls."** The complete examples use **Java 17, Spring Boot 3.5, Spring Framework 6.2, Jakarta Validation, and JUnit Jupiter**. The test suite compares direct-new calls against Spring AOP proxies, verifies input/output/nested constraints and internal self-calls, and distinguishes **service method validation** exceptions from **Spring MVC validation** exceptions. No database, Docker, or external API is required.

> **Foundational takeaway:** an annotation is not like an `if` statement automatically executed by Java. You need the **validation trigger matching the entry point**; a test that bypasses that entry point can pass while production fails, or vice versa.

## 1. Method validation concepts in Jakarta Bean Validation

Jakarta Bean Validation defines several constraint kinds:

- **Bean/property constraints:** on fields, getters, record components, or type-use targets, e.g., `record ReservationRequest(@NotBlank String sku, @Min(1) int quantity)`. Checked when `Validator.validate(request)` is invoked or a framework triggers object validation.
- **Executable parameter constraints:** on method/constructor parameters, e.g., `reserve(@NotBlank String sku, @Min(1) int quantity)`. Requires `ExecutableValidator.validateParameters(...)` or an equivalent interceptor/framework.
- **Return-value constraints:** on method return types, e.g., `@NotBlank public String reference(...)`. Requires checking the return value after the method runs; through a service proxy, it can throw after the method has executed.
- **Cascaded validation:** `@Valid ReservationRequest request` instructs validation of constraints **inside the request object** at the boundary where validation runs; placing `@Valid` alone does not cause an ordinary Java call to validate the object.
- **Groups:** Bean Validation supports the `Default` group and marker interfaces; Spring's `@Validated(Group.class)` selects groups for method validation, whereas `@Valid` alone is not a group selector.
- **Cross-parameter constraints:** custom constraints across combinations of multiple parameters require a dedicated validator; do not pretend `@Min` on one parameter validates relationships between two parameters.
- **Composed constraints:** custom annotations combining multiple constraints still require a validation engine and appropriate metadata.

Example signature:

```java
@Validated
@Service
public class InventoryService {
    public String reserve(
            @NotBlank String sku,
            @Min(1) int quantity) {
        return "R:" + sku + ":" + quantity;
    }

    @NotBlank
    public String reference(@NotBlank String sku) {
        return sku.equals("unavailable") ? "" : "ref:" + sku;
    }
}
```

This is only a **snippet** without full imports/dependencies; the runnable example is in section 6. When invoked through a Spring proxy, invalid inputs are rejected **before the method body**, while invalid return values are detected **after the method body**. If the method produces side effects before a return-value violation is caught, do not assume the exception rolls back every resource; explicit transaction boundaries or cleanup are needed.

### Bean validation vs. executable validation

```text
Bean object:
  ReservationRequest(sku="", quantity=0)
          |
          +-- validator.validate(request)
                      -> violations on bean properties

Method call:
  inventory.reserve("", 0)
          |
          +-- Java direct invocation -> method runs, NO auto check
          |
          +-- Spring proxy -> MethodValidationInterceptor
                                -> validateParameters(...)
                                -> target method
                                -> validateReturnValue(...)
                                -> caller receives result or exception
```

A `validator.validate(dto)` test proves **DTO constraints are valid**, but **does not prove** a `@Validated` proxy is applied to the service. A test calling the Spring proxy proves service interception, but **does not prove** HTTP requests are deserialized by Spring MVC and return 400 properly. Each test answers a different question.

## 2. Why does `new Service()` differ from `@Autowired Service`?

Spring method validation for beans typically relies on a **Spring AOP proxy**: Spring manages the object and `MethodValidationPostProcessor` attaches an interceptor to eligible beans. In Spring Boot 3.5 with a Bean Validation implementation such as Hibernate Validator on the classpath (commonly via `spring-boot-starter-validation`), Boot auto-configures method validation; the target class must be annotated with `@Validated` to receive AOP-based method validation.

```text
Plain Java call                            Call through Spring
---------------------------------          ----------------------------------
new InventoryService()                     ApplicationContext
         |                                       |
         v                                       v
      target object                          inventoryService proxy
         |                                       |
         +-- reserve("", 0)                     +-- invoke reserve("", 0)
                 |                                   |
                 +-- no interceptor                  +-- pre-validate parameters
                 |                                   |
                 +-- "R::0"                          +-- ConstraintViolationException
```

**When Bean Validation is not configured** (missing provider, missing starter, or missing `@Validated` on the target type), even a Spring-managed object will not be method-validated. Never assume `@Autowired` alone suffices: tests must verify both bean advice/proxying and observed behavior.

### 2.1. Spring's `@Validated` vs. Jakarta's `@Valid`

| Annotation | Typical meaning | Example |
|---|---|---|
| `@Validated` on service class | Marks target bean for AOP method validation; can specify groups | `@Service @Validated class InventoryService` |
| `@NotBlank` directly on method parameter | Constraint on the actual argument | `reserve(@NotBlank String sku)` |
| `@Min(1)` on primitive/boxed number | Value must be at least 1 | `reserve(@Min(1) int quantity)` |
| `@NotBlank` on method return value | Constraint on the returned value | `@NotBlank String reference(...)` |
| `@Valid` on method parameter | Cascades constraints into the nested object | `reserveRequest(@Valid ReservationRequest request)` |
| `@Valid` on MVC `@RequestBody` | Triggers argument validation at MVC binding boundary | `create(@Valid @RequestBody ReservationRequest r)` |
| `@Validated(Group.class)` | Selects validation groups at a Spring boundary | `@Validated(Create.class)` or type-level |
| `@NotNull` | Value cannot be null; unlike `@NotBlank` for Strings | `@NotNull ReservationRequest request` |

**`@Valid` is not a standalone constraint annotation.** For a `@Valid ReservationRequest request` parameter **without `@NotNull`**, `null` is not treated as a violation by `@Valid` alone; if business logic requires non-null, add `@NotNull`. The method body may still throw `NullPointerException` when dereferencing null; that is a Java error, not a `@Valid` violation.

### 2.2. AOP proxies and limitations

- **Callers must go through the proxy.** `this.reserve(...)` from another method on the same target typically bypasses the proxy.
- **CGLIB class proxies** have limitations with `final` or `private` classes/methods because they cannot be overridden normally. JDK dynamic proxies apply to interface methods; choose appropriate configuration and do not rely on private methods.
- **Beans created with `new` or Mockito mocks** are not wrapped by Spring; a mock can throw an exception when stubbed to do so, but that does not prove real method validation is active.
- **Parameter annotations** must be visible through the provider/metadata. With interfaces and implementations, follow Jakarta Validation method-constraint inheritance rules; do not arbitrarily strengthen preconditions on overrides where the provider treats that as a violation.
- **Self-invocation** normally bypasses method validation, `@Transactional`, and `@Async` advice under proxy-based Spring AOP.
- **AspectJ weaving** differs from proxy-based AOP and has different self-invocation semantics; examples in this lesson use standard Boot AOP proxies.

If a test creates `new InventoryService()` and sees `quantity=0` succeed without error, that is **not evidence that validation is broken**. It simply proves you invoked the target through a path without an interceptor.

## 3. Which exceptions can appear?

### `@Validated` service via proxy

Spring Framework's `MethodValidationInterceptor` has two key modes:

1. **Traditional default:** constraint violations throw `jakarta.validation.ConstraintViolationException`, containing `Set<ConstraintViolation<?>>`.
2. **Adapted violations:** when `MethodValidationPostProcessor.setAdaptConstraintViolations(true)` is configured, it can throw `org.springframework.validation.method.MethodValidationException` carrying a `MethodValidationResult`.

In a default Boot 3.5 setup, service tests expect **`ConstraintViolationException`**. Do not claim this is an immutable exception class across every application: custom post-processors, AOP interceptors, REST exception translation, or other validation libraries may change it.

### Spring MVC has its own validation path

Since Spring Framework **6.1**, Spring MVC supports **built-in method validation** for `@RequestMapping` handler methods (requiring no AOP to check direct constraints on handler signatures). Per Spring Framework 6.2 documentation:

- `@Valid @RequestBody ReservationRequest request` with constraints on the DTO and **no other direct method-level constraints**: the typical exception is **`MethodArgumentNotValidException`**, HTTP **400 Bad Request**.
- `@RequestParam @Min(1) int quantity` or constraints directly on handler method parameters/return values: uses **MVC method validation**, typically throwing **`HandlerMethodValidationException`**, HTTP 400 for input violations; return violations generally reflect a server error.
- If a handler has **both** `@RequestParam @Min(...)` and `@Valid @RequestBody`, method validation typically **supersedes** per-argument body validation; the exception can be `HandlerMethodValidationException` even when the error is inside the nested DTO.
- Placing `@Validated` **at the controller class level** can route validation through the **older AOP method validation** path instead of built-in MVC validation; Framework 6.2 docs recommend **removing class-level `@Validated` from controllers** to use the newer mechanism.
- Placing `BindingResult`/`Errors` right after `@RequestBody` changes exception behavior in some cases; do not assume every `@Valid` failure throws into controller advice.
- MVC exception mapping and HTTP statuses can be customized via `@ControllerAdvice` or custom handlers; assert according to actual configuration.

| Call path | Trigger point | Typical default exception | Control case |
|---|---|---|---|
| `new InventoryService().reserve(" ", 0)` | No validation interceptor | No automatic `ConstraintViolationException` | Raw Java object unit test |
| `@Autowired InventoryService.reserve(" ", 0)` | Spring method validation proxy | `ConstraintViolationException` | `@SpringBootTest` + injected bean |
| `service.reserveRequest(@Valid dto)` | Cascaded executable validation via proxy | `ConstraintViolationException` | Invalid DTO passed to method |
| `validator.validate(dto)` | Explicit Jakarta `Validator` | Returns `Set<ConstraintViolation<T>>` | Does not auto-throw |
| `validator.forExecutables().validateParameters(...)` | Explicit `ExecutableValidator` | Returns violations | Works on raw `new` instance |
| `MockMvc POST @Valid @RequestBody dto` | MVC argument validation | `MethodArgumentNotValidException` | 400, controller body not executed |
| `MockMvc GET @RequestParam @Min int` | MVC built-in method validation | `HandlerMethodValidationException` | 400, controller body not executed |
| `MockMvc POST with @Min + @Valid body` | MVC method validation | `HandlerMethodValidationException` | 400 with per-parameter errors |

**Never hardcode "service method validation = HTTP 400."** The service layer throws a Java exception; if invoked during an HTTP request, the status code depends on the app's exception handling. In the sample code, MVC validates inputs **before calling the service**, so 400 responses follow MVC's mechanism; production systems need a consistent error contract that hides internal details.

## 4. Define the test objective before picking a tool

| Objective | Recommended test style | Tests real proxy? |
|---|---|---|
| Verify method algorithm with known inputs | Unit test with `new Service()` | **No** |
| Verify constraint metadata on DTO | Inject `jakarta.validation.Validator` or build validator factory | Only tests Bean Validation directly |
| Verify `@Validated` service parameter/return constraints | `@SpringBootTest` injecting bean, calling public method via proxy | **Yes** |
| Verify self-invocation limitation | Call non-constrained outer method A on bean proxy, A calls `this.B(...)` | Yes, to prove bypass |
| Verify bean validation groups | Bean validation + Spring context group tests | Yes, when using `@Validated` |
| Verify JSON binding + DTO validation + 400 response | `MockMvc` or HTTP integration test | MVC mechanism |
| Verify MVC direct method constraints | Spring MVC 6.1+ with `@RequestParam @Min` and `MockMvc` | MVC built-in, **no controller AOP needed** |
| Verify controller advice / external API status | `@SpringBootTest`/`@WebMvcTest` with appropriate security/filter config | Depends on bean graph/slice |
| Verify JPA/transaction rollback after validation | DB integration test + proper transaction boundary | Different goal than pure validation |

A **unit test making direct Java calls** is great for business algorithms; do not force it to prove AOP. Likewise, a `MockMvc` test returning 400 proves **MVC binding**, not proxy validation on a service invoked from non-HTTP entry points.

## 5. Demo design and directory tree

Sample application:

- `ReservationRequest` is a Java record with `@NotBlank sku` and `@Min(1) quantity`.
- `InventoryService` is a Spring `@Service @Validated` with `reserve` (direct parameter constraints), `reserveRequest(@Valid ReservationRequest)` (cascaded validation), `reference` (return-value constraint), and `reserveViaSelfCall` intentionally calling `this.reserve(...)`.
- `OrderController` **does not have class-level `@Validated`**. `POST /api/orders` uses `@Valid @RequestBody`; `GET /api/orders/preview` uses `@RequestParam @Min(1)`; `POST /api/orders/combined` uses **both** `@RequestParam @Min(1)` and `@Valid @RequestBody`.
- `InventoryMethodValidationTest` demonstrates direct-object bypass vs. Spring proxy enforcement.
- `OrderControllerValidationTest` uses `MockMvc` to verify 400/201, the two distinct exception types, and how direct controller invocation bypasses MVC.

```text
method-validation-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/methodvalidation/
    │   ├── MethodValidationDemoApplication.java
    │   ├── ReservationRequest.java
    │   ├── InventoryService.java
    │   └── OrderController.java
    └── test/java/com/example/methodvalidation/
        ├── InventoryMethodValidationTest.java
        └── OrderControllerValidationTest.java
```

**Scope:** the example uses no DB, no user authentication, and no external APIs, isolating the boundaries between plain Java calls, method proxies, and MVC. No Java agent or weaving is used to auto-validate raw `new` calls.

## 6. Runnable Java 17 + Spring Boot 3.5 source code

### 6.1. Maven `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>com.example</groupId>
    <artifactId>method-validation-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-aop</artifactId>
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

**Why both validation and AOP?** `spring-boot-starter-validation` supplies the Jakarta Bean Validation implementation (Hibernate Validator); `spring-boot-starter-aop` ensures AOP infrastructure for Spring method validation proxies; `spring-boot-starter-web` provides MVC/`MockMvc` integration. `spring-boot-starter-test` brings in JUnit Jupiter, AssertJ, and Spring test utilities.

With Spring Boot 3.x you must use **`jakarta.validation.*`**, not the legacy Boot 2 `javax.validation.*` imports. Java 17 meets the baseline; Boot parent manages compatible Spring Framework/Security/Test versions. If targeting Boot 4, verify module and artifact changes instead of blindly copying imports/dependencies from this lesson.

### 6.2. Main application

File **`src/main/java/com/example/methodvalidation/MethodValidationDemoApplication.java`**:

```java
package com.example.methodvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodValidationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodValidationDemoApplication.class, args);
    }
}
```

Placing classes under this package lets Spring component scanning find `InventoryService` and `OrderController`. Tests sit in the same package so Spring Boot locates `@SpringBootConfiguration` automatically without manually specifying `classes`.

### 6.3. DTO with bean constraints

File **`src/main/java/com/example/methodvalidation/ReservationRequest.java`**:

```java
package com.example.methodvalidation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record ReservationRequest(
        @NotBlank String sku,
        @Min(1) int quantity) {
}
```

On a Java 17 record, constraints on record components work with Bean Validation; Hibernate Validator validates the properties. `@NotBlank` rejects null, empty strings, and whitespace-only strings; `@Min(1)` rejects 0 and negative quantities. Note that `@Min` does not cap maximum values, and `@NotBlank` does not validate SKU format; real-world rules can add `@Size`/`@Pattern`/business constraints.

### 6.4. Service with method constraints and a self-invocation case

File **`src/main/java/com/example/methodvalidation/InventoryService.java`**:

```java
package com.example.methodvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class InventoryService {

    public String reserve(
            @NotBlank String sku,
            @Min(1) int quantity) {

        return "R:" + sku + ":" + quantity;
    }

    @NotBlank
    public String reference(@NotBlank String sku) {
        if ("unavailable".equals(sku)) {
            return "";
        }
        return "ref:" + sku;
    }

    public String reserveRequest(
            @Valid ReservationRequest request) {

        return reserve(request.sku(), request.quantity());
    }

    // Intentional example illustrating self-invocation bypassing proxy.
    public String reserveViaSelfCall(
            String sku, int quantity) {

        return this.reserve(sku, quantity);
    }
}
```

`@Validated` marks the target bean for AOP method validation. In `reserveViaSelfCall`, the public outer method **has no direct constraints**, so when a caller invokes it via the proxy, the interceptor detects no errors on the outer parameters. Then `this.reserve(...)` executes **on the target directly**, bypassing the proxy, so the inner constraints are not automatically checked. This illustrates a proxy limitation and is **not production business code to keep**.

`reserveRequest(@Valid ReservationRequest request)` enables nested constraint validation via executable validation when called **through the proxy**. Since `@Valid` does not enforce non-null, real apps should add `@NotNull` if the contract forbids null. Calling `new InventoryService().reserveRequest(...)` directly skips nested bean constraints as well, because only annotations are present without framework invocation.

`reference("unavailable")` intentionally returns `""` to illustrate a **return-value constraint**. The service method body completes first and then the proxy detects that `@NotBlank` failed; if the method wrote to a DB or called an external system, separate transaction/compensation logic is required—do not rely on method validation to undo work.

### 6.5. MVC controller with two validation paths

File **`src/main/java/com/example/methodvalidation/OrderController.java`**:

```java
package com.example.methodvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final InventoryService inventory;

    public OrderController(InventoryService inventory) {
        this.inventory = inventory;
    }

    @PostMapping
    public ResponseEntity<String> create(
            @Valid @RequestBody ReservationRequest request) {

        String id = inventory.reserve(
                request.sku(), request.quantity());
        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(id);
    }

    @GetMapping("/preview")
    public String preview(
            @RequestParam @Min(1) int quantity) {

        return "preview:" + quantity;
    }

    @PostMapping("/combined")
    public ResponseEntity<String> createCombined(
            @RequestParam @Min(1) int priority,
            @Valid @RequestBody ReservationRequest request) {

        String id = inventory.reserve(
                request.sku(), request.quantity());
        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body("P:" + priority + ":" + id);
    }
}
```

**Do not put class-level `@Validated` on this controller.** Spring Framework 6.2's MVC built-in method validation detects the direct `@Min(1)` constraint on the request parameter in `preview` and `createCombined`. Meanwhile, `create` only has `@Valid @RequestBody` on the DTO (with no direct method constraint on the handler), so `MethodArgumentNotValidException` is the standard exception path when the body is invalid.

The controller is a Spring bean, yet a **direct Java call** like `new OrderController(new InventoryService()).create(new ReservationRequest("", 0))` bypasses both MVC argument resolution/validation and the Spring service proxy, returning a 201 response despite invalid input. Never include such a direct-invocation test in an acceptance suite as evidence that the HTTP endpoint accepts invalid payloads.

### 6.6. Service integration tests: comparing raw Java and Spring proxies

File **`src/test/java/com/example/methodvalidation/InventoryMethodValidationTest.java`**:

```java
package com.example.methodvalidation;

import java.lang.reflect.Method;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validator;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class InventoryMethodValidationTest {

    @Autowired
    private InventoryService springService;

    @Autowired
    private Validator validator;

    @Test
    void directNewDoesNotRunMethodValidation() {
        InventoryService raw = new InventoryService();

        assertThat(raw.reserve(" ", 0))
                .isEqualTo("R: :0");
    }

    @Test
    void springManagedServiceIsAopProxy() {
        assertThat(AopUtils.isAopProxy(springService))
                .isTrue();
    }

    @Test
    void springProxyRejectsBlankSku() {
        assertThatThrownBy(() ->
                springService.reserve(" ", 2))
                .isInstanceOf(ConstraintViolationException.class)
                .satisfies(error -> {
                    var violations =
                            ((ConstraintViolationException) error)
                                    .getConstraintViolations();
                    assertThat(violations).hasSize(1);
                });
    }

    @Test
    void springProxyRejectsQuantityZero() {
        assertThatThrownBy(() ->
                springService.reserve("BOOK-1", 0))
                .isInstanceOf(ConstraintViolationException.class);
    }

    @Test
    void springProxyReportsBothParameterViolations() {
        assertThatThrownBy(() ->
                springService.reserve(" ", 0))
                .isInstanceOf(ConstraintViolationException.class)
                .satisfies(error -> {
                    var violations =
                            ((ConstraintViolationException) error)
                                    .getConstraintViolations();
                    assertThat(violations).hasSize(2);
                });
    }

    @Test
    void validArgumentsPassSpringMethodValidation() {
        assertThat(springService.reserve("BOOK-1", 3))
                .isEqualTo("R:BOOK-1:3");
    }

    @Test
    void selfInvocationDoesNotCrossValidationProxy() {
        assertThat(
                springService.reserveViaSelfCall(" ", 0))
                .isEqualTo("R: :0");
    }

    @Test
    void proxyValidatesReturnValueAfterMethodCall() {
        assertThatThrownBy(() ->
                springService.reference("unavailable"))
                .isInstanceOf(ConstraintViolationException.class);
    }

    @Test
    void directNewDoesNotValidateReturnValue() {
        InventoryService raw = new InventoryService();

        assertThat(raw.reference("unavailable"))
                .isEqualTo("");
    }

    @Test
    void proxyCascadesValidNestedRequest() {
        ReservationRequest invalid =
                new ReservationRequest("", 0);

        assertThatThrownBy(() ->
                springService.reserveRequest(invalid))
                .isInstanceOf(ConstraintViolationException.class)
                .satisfies(error -> {
                    var violations =
                            ((ConstraintViolationException) error)
                                    .getConstraintViolations();
                    assertThat(violations).hasSize(2);
                });
    }

    @Test
    void directObjectCallBypassesCascadedValidation() {
        InventoryService raw = new InventoryService();

        assertThat(raw.reserveRequest(
                new ReservationRequest("", 0)))
                .isEqualTo("R::0");
    }

    @Test
    void explicitBeanValidatorWorksOnRawRecord() {
        ReservationRequest invalid =
                new ReservationRequest("", 0);

        Set<ConstraintViolation<ReservationRequest>> errors =
                validator.validate(invalid);

        assertThat(errors).hasSize(2);
    }

    @Test
    void executableValidatorChecksRawMethodManually()
            throws Exception {

        InventoryService raw = new InventoryService();
        Method method = InventoryService.class.getMethod(
                "reserve", String.class, int.class);

        var violations = validator.forExecutables()
                .validateParameters(
                        raw, method, new Object[] {" ", 0});

        assertThat(violations).hasSize(2);
    }

    @Test
    void executableValidatorCanCheckRawReturnValue()
            throws Exception {

        InventoryService raw = new InventoryService();
        Method method = InventoryService.class.getMethod(
                "reference", String.class);

        var violations = validator.forExecutables()
                .validateReturnValue(
                        raw, method, "");

        assertThat(violations).hasSize(1);
    }

    @Test
    void validReturnValueFromProxyPasses() {
        assertThat(springService.reference("BOOK-1"))
                .isEqualTo("ref:BOOK-1");
    }
}
```

**15 `@Test` methods in this class**: 3 tests showing raw objects/raw returns/cascades are not intercepted, tests for Spring proxy and input violations, return-value violation test, self-invocation test, 3 tests for explicit Jakarta Validator/executable validator, and valid paths. Negative cases expecting an exception PASS when the right exception is thrown, not as JUnit failures.

#### Why don't the tests depend on exception messages?

Parameter names inside `ConstraintViolation.getPropertyPath()` can vary if the Java compiler was not invoked with `-parameters` or if the provider uses different metadata. The example uses `hasSize(1/2)` and the exception type rather than asserting exact text like `"reserve.sku must not be blank"`. In real projects, you can inspect constraint descriptor annotation types or property paths per known rules, avoiding localized Hibernate Validator text.

#### Why use `@SpringBootTest(webEnvironment=NONE)`?

The context loads the Spring-managed `InventoryService`, `MethodValidationPostProcessor`/Bean Validation provider, and AOP infrastructure without starting an HTTP servlet server. This is the right boundary to prove **service proxying** without paying MockMvc/HTTP overhead unnecessarily. In a project with many auto-configurations wanting a lighter setup, you can use `ApplicationContextRunner` with exact Validation/AOP configurations; do not trim the context so much that you drop the post-processor under test.

### 6.7. MockMvc integration tests: object validation and MVC method validation

File **`src/test/java/com/example/methodvalidation/OrderControllerValidationTest.java`**:

```java
package com.example.methodvalidation;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class OrderControllerValidationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validRequestBodyProduces201() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"BOOK-1","quantity":3}
                        """))
                .andExpect(status().isCreated())
                .andExpect(content().string("R:BOOK-1:3"));
    }

    @Test
    void invalidRequestBodyProducesMethodArgumentNotValid()
            throws Exception {

        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"","quantity":0}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(result -> assertThat(
                        result.getResolvedException())
                        .isInstanceOf(
                                MethodArgumentNotValidException.class));
    }

    @Test
    void onlyQuantityInvalidStillGetsBodyValidation400()
            throws Exception {

        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"BOOK-1","quantity":0}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(result -> assertThat(
                        result.getResolvedException())
                        .isInstanceOf(
                                MethodArgumentNotValidException.class));
    }

    @Test
    void directRequestParamConstraintUsesMvcMethodValidation()
            throws Exception {

        mvc.perform(get("/api/orders/preview")
                .param("quantity", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(result -> assertThat(
                        result.getResolvedException())
                        .isInstanceOf(
                                HandlerMethodValidationException.class));
    }

    @Test
    void validRequestParamProduces200() throws Exception {
        mvc.perform(get("/api/orders/preview")
                .param("quantity", "2"))
                .andExpect(status().isOk())
                .andExpect(content().string("preview:2"));
    }

    @Test
    void directConstraintOnHandlerSupersedesBodyValidation()
            throws Exception {

        mvc.perform(post("/api/orders/combined")
                .param("priority", "0")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"","quantity":0}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(result -> assertThat(
                        result.getResolvedException())
                        .isInstanceOf(
                                HandlerMethodValidationException.class));
    }

    @Test
    void combinedHandlerValidArgumentsProduce201() throws Exception {
        mvc.perform(post("/api/orders/combined")
                .param("priority", "2")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"BOOK-1","quantity":3}
                        """))
                .andExpect(status().isCreated())
                .andExpect(content().string("P:2:R:BOOK-1:3"));
    }

    @Test
    void directJavaControllerCallDoesNotRunMvcValidation() {
        OrderController rawController =
                new OrderController(new InventoryService());

        ResponseEntity<String> response =
                rawController.create(
                        new ReservationRequest("", 0));

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody())
                .isEqualTo("R::0");
    }
}
```

**8 `@Test` methods in the MVC class**. The suite compares:

- Invalid POST body with `@Valid @RequestBody` → 400, `MethodArgumentNotValidException` (no other direct constraints on the handler method).
- GET direct method constraint `@RequestParam @Min(1)` → 400, `HandlerMethodValidationException`.
- Combined POST with `@Min` on query parameter and `@Valid` on body → method-level validation, `HandlerMethodValidationException`.
- Valid paths → 200/201.
- Direct invocation instantiating the controller and service with `new` → no MVC binder, validation, or Spring method proxy, resulting in a 201 response despite an invalid DTO. This outcome is **true only for the direct Java call in the demo**, not for an actual HTTP endpoint.

**Total 23 JUnit tests** across the two classes: 15 service + 8 MVC. Intentionally not mocking `InventoryService` with Mockito ensures tests actually exercise AOP behavior.

### 6.8. Run commands and reading results

Requires **JDK 17+**, Maven, and no Docker:

```bash
mvn test
```

Or run each group individually:

```bash
mvn -Dtest=InventoryMethodValidationTest test
mvn -Dtest=OrderControllerValidationTest test
```

If Maven Wrapper is configured: `./mvnw test` on Linux/macOS or `mvnw.cmd test` on Windows. With the project structured and dependencies set as shown, the expected outcome is **23 tests, 0 failures, 0 errors**. This is an expected result based on the assertions, **not an execution log produced in this article**. The code was reviewed for APIs and semantics based on Spring Boot 3.5/Spring Framework 6.2, without running Maven in the authoring environment.

When results differ from expectations, **do not hastily change exception assertions to `Exception.class` just to turn tests green**. Inspect the Spring Boot version, Jakarta Validator provider, bean proxy, controller-level `@Validated`, test slice, `ValidationPostProcessor`, and custom exception mappings.

## 7. Scenarios that should not be equated

### 7.1. Direct calls from a unit test

```java
InventoryService service = new InventoryService();
String result = service.reserve(" ", 0);
```

This is valid Java code and returns `"R: :0"` in the demo. It tests the method logic **without going through the Spring context**, so it **does not prove `@NotBlank`/`@Min` are enforced**.

To unit-test constraints without booting all of Spring:

```java
try (ValidatorFactory factory =
        Validation.buildDefaultValidatorFactory()) {
    Validator validator = factory.getValidator();
    var errors = validator.validate(
            new ReservationRequest("", 0));
    assertThat(errors).hasSize(2);
}
```

This is a **snippet** requiring Jakarta Validation `Validation`, `Validator`, `ValidatorFactory`, and AssertJ imports; it only validates DTO constraints. For executable validation on a raw service, use `validator.forExecutables().validateParameters(target, method, args)` and `validateReturnValue(...)` as shown in the tests. Never call `Validator.validate(service)` assuming it checks method signatures: `validate(bean)` checks bean property constraints, not executable validation.

### 7.2. Self-invocation: the service is proxied, yet internal calls still skip validation

```java
public String reserveViaSelfCall(String sku, int quantity) {
    return this.reserve(sku, quantity);
}
```

When a caller enters through `springService.reserveViaSelfCall`, the interceptor sees the outer method; since the outer method has no constraints, it lets it pass. Then `this.reserve` calls the target directly, bypassing the proxy, so the inner `@NotBlank`/`@Min` are skipped.

**Preferred fix:** extract the validated method into another bean and call it through an injected Spring bean; or move validation to the appropriate outer boundary, or invoke an explicit validator when framework proxying does not fit. **Avoid** coupling business code to `AopContext.currentProxy()` without strong justification, as it increases coupling and requires exposing proxies.

### 7.3. `@Valid` on a DTO does not replace method constraints

A DTO record with `@NotBlank`/`@Min` is checked when Spring MVC processes `@Valid @RequestBody`. However, if a service accepts **two scalar parameters**, it may need direct constraints on `reserve(@NotBlank sku, @Min qty)` to protect callers **outside HTTP** (scheduled jobs, Kafka consumers, CLI adapters, or integration tests).

Conversely, if a service accepts `@Valid ReservationRequest`, the proxy can cascade into the object. For `null`, `@Valid` is not enough: add `@NotNull` when input is required.

### 7.4. Parameter validation and return validation occur at different times

- **Input constraints** fail in the proxy **before** the method body runs: normally there are no side effects inside the method (aside from interceptor/argument construction behavior).
- **Return-value constraints** fail **after** the target method has executed. If the method already wrote to a DB and committed an independent transaction or sent a message before the error was caught, an exception is not enough to guarantee all side effects rolled back.
- **Method groups** can restrict certain constraints to specific groups. Tests using `@Validated(Group.class)` must know which group is active and test both positive and negative cases.
- **Cross-parameter validation** requires a custom Bean Validation constraint; testing two scalar parameters separately does not prove relational rules like `startDate <= endDate`.

### 7.5. Final classes/methods, interface proxies, and qualifiers

- With JDK proxies, callers normally inject beans by interface; understand constraint placement across interfaces and implementations per Jakarta Validation's method inheritance rules.
- With CGLIB, `final` classes or methods cannot be overridden by standard proxy interceptors; keep advised classes/methods non-final with public signatures.
- Instantiating `new SomeService()` produces no Spring bean proxy, even if the class has `@Component`/`@Validated`.
- Adding `@Primary` or another bean name does not solve method validation by itself; what matters is **the bean instance the caller actually receives** and whether it has the right interceptor.

## 8. Differences in HTTP statuses and exception mapping

| Where the error is caught | Typical exception | Default/common status | Notes |
|---|---|---|---|
| MVC `@Valid @RequestBody` | `MethodArgumentNotValidException` | **400** | Validates DTO during argument binding |
| MVC direct `@Min`/`@NotBlank` on handler | `HandlerMethodValidationException` | **400** for input | Return-value violations may be handled as server errors |
| Spring service `@Validated` proxy | `ConstraintViolationException` | **Not automatically 400 in all contexts** | Exception from service; requires proper error handler |
| `MethodValidationPostProcessor` adapted mode | `MethodValidationException` | Depends on exception handling | Not always identical to `ConstraintViolationException` |
| Malformed JSON input | `HttpMessageNotReadableException` | **400** | Parse/deserialization error, not a constraint |
| Query string `"abc"` for `int` | `MethodArgumentTypeMismatchException` | Typically **400** | Conversion error occurs before/separately from validation |
| Missing authentication/authorization | Security exceptions/handlers | 401/403 per config | Distinct from method validation |
| Null dereference in direct method | `NullPointerException` | 500 if unhandled | Not automatically `@NotNull` validation |

### `@ControllerAdvice` should handle actual failure types

In production APIs, you can write a `@RestControllerAdvice` with dedicated handlers for `MethodArgumentNotValidException`, `HandlerMethodValidationException`, `ConstraintViolationException`, and unparseable payloads. Never lump every `RuntimeException` into 400: programming, DB, and service bugs still need proper classification.

The same business input violation can surface at the DTO layer, service layer, or provider layer. Design a consistent error response contract (problem details, code, field/path, correlation ID) without exposing class names, stack traces, or sensitive values in HTTP responses. When testing controllers, verify both **status + error schema**, not just Hibernate Validator messages that may change with localization.

## 9. Spring MVC 6.1+: check before carrying over class-level `@Validated`

In Spring Framework 6.1+, MVC built-in method validation handles direct method constraints on handler signatures. Spring Framework 6.2 docs state clearly: to use the built-in mechanism, **remove class-level `@Validated` from controllers**; leaving it in place can route validation through an AOP proxy instead of the MVC path.

Key details:

1. **`@Valid` alone is not a direct constraint.** On a body DTO, it normally triggers argument validation and `MethodArgumentNotValidException`.
2. Adding **`@NotNull`** directly on a handler parameter can activate **method validation**, changing the exception type.
3. A handler with `@Min` on a query param and `@Valid` on a body can throw `HandlerMethodValidationException` when the nested body is invalid, because method validation **covers nested constraints too**.
4. Tests/apps with a `@ControllerAdvice` catching `MethodArgumentNotValidException` but not `HandlerMethodValidationException` can produce inconsistent error responses after framework upgrades.
5. Adding `BindingResult` right after a parameter may allow the method to be called in cases where errors belong only to the parameter with a binding result; do not assume every `@Valid` always throws.
6. In WebFlux, validation and exceptions follow similar concepts with different web stack and exception classes; do not copy MockMvc tests directly to `WebTestClient`.

**QA goal during upgrades:** audit handler signatures, class-level `@Validated`, MVC exception handlers, and tests. Do not just look for annotations in code and assume which Bean Validation path runs.

## 10. How test slices and Mockito can strip out validation

### `@WebMvcTest`

`@WebMvcTest(OrderController.class)` loads the MVC slice, which can test request binding and built-in MVC validation. However, if the controller injects `InventoryService` and the slice does not instantiate the real bean, tests typically provide a mock (`@MockitoBean` or equivalent). In that setup, the **service method validation proxy** may **not exist** or reflect production. A slice test passing with 400 on the DTO **does not prove** the service proxy validates calls. A `@SpringBootTest` or dedicated context with the post-processor is needed for the service boundary.

### Mockito `mock(InventoryService.class)`

Mocks do not automatically run Spring's `MethodValidationPostProcessor`; they return default values or test-stubbed behavior. For instance:

```java
InventoryService mock = Mockito.mock(InventoryService.class);
mock.reserve(" ", 0);
```

This is a snippet (requires Mockito) and **is not a test of real service method validation**. Mockito can be stubbed to throw `ConstraintViolationException`, but that only tests how the caller handles the exception, not the constraint annotations or validation provider.

### `@InjectMocks` or raw constructor calls

`@InjectMocks` instantiates a target object and injects mocks; it **does not guarantee** Spring AOP proxies or Jakarta validation run. It works well for unit-testing algorithms, but not when the criterion is `@Validated` interception. Test with **real Spring beans** via a context whenever expected behavior comes from Spring infrastructure.

## 11. Testing pitfalls and how to catch them

| Mistake | Why it is wrong | What the test should do |
|---|---|---|
| Calling `new Service().method(invalid)` expecting annotations to throw | No proxy/interceptor | Inject the real bean and call through the Spring proxy |
| Asserting `@Validated` presence via reflection only | Metadata does not prove advice runs | `AopUtils.isAopProxy` + invalid invocation |
| Omitting `spring-boot-starter-validation` | Missing Jakarta Validation implementation | Add starter and verify provider/auto-config |
| Omitting AOP infrastructure | No proxy interception | Ensure Spring AOP is properly configured |
| Self-invocation `this.validatedMethod` | Bypasses AOP proxy | Split beans or validate at outer boundary |
| `final` class/method under CGLIB proxy | Cannot advise via subclass override | Adjust design or proxy strategy |
| Treating `@Valid` as `@NotNull` | Null is not a violation by itself | Add `@NotNull` when contract requires it |
| Validating only the DTO and assuming the service is safe | DTO constraints differ from executable constraints | Test `@Validated` bean proxy separately |
| Passing invalid DTO via MockMvc and checking status only | Unclear whether MVC argument or method validation fired | Assert `getResolvedException()` type |
| Calling every HTTP 400 a validation error | Parse/type mismatches differ from constraint violations | Test invalid JSON, missing params, and method constraints separately |
| Leaving class-level `@Validated` on controller in MVC 6.2 blindly | Can alter the validation path | Follow MVC built-in docs; remove to use the new path |
| Asserting exact exception message text | Hibernate Validator localization/parameter names vary | Assert type, constraint metadata, counts/paths where appropriate |
| Mapping `ConstraintViolationException` to 500 outside HTTP | Service exceptions carry no implicit API status | Implement exception handling matching business semantics |
| Return-value constraint throws after creating side effects | Failure detected after method body | Use transactions/compensation and test side effects |
| Checking `isAopProxy` without calling invalid inputs | Bean might be proxied for transactions instead | Assert validation's own error semantics |
| Mocking the real service bean with Mockito | Loses target validation behavior | Run integration tests with the real bean |
| Testing only positive inputs | Service might not validate anything and still pass | Add invalid parameter, return, and nested cases |
| Using `assertThrows(Exception.class)` | Too broad; masks config/proxy failures | Assert exact exception class/cause and violation count |
| Testing only `@Valid` request bodies | Misses `@RequestParam`/return method validation | Add MockMvc direct parameter constraint tests |
| Missing provider after Boot 2→3 upgrade | `javax` vs. `jakarta` namespace mismatch | Align imports and dependency versions consistently |

## 12. Checklist before concluding method validation works

- [ ] I have clearly identified the entry point: raw Java call, Spring service proxy, MVC handler, or explicit `Validator`.
- [ ] A Bean Validation provider and dependencies matching the Spring Boot line are present.
- [ ] Using `jakarta.validation.*` with Boot 3.5.
- [ ] Service target has `@Validated` and public methods have parameter/return constraints.
- [ ] Tests invoke the bean injected from the Spring context, not just raw `new`.
- [ ] Negative tests with invalid arguments show the proxy actually throws violations.
- [ ] Tests verify valid inputs still run the method and return expected outputs.
- [ ] Tests distinguish parameter violations from return-value violations.
- [ ] `@Valid` nested DTO validation is tested via proxy or explicit `Validator`.
- [ ] Does not mistake `@Valid` for rejecting null; `@NotNull` is added when needed.
- [ ] Self-invocation is tested if code makes internal calls to annotated methods.
- [ ] No `final`/private classes or methods silently block proxy advice.
- [ ] When using interface proxies, annotation/method inheritance obeys Jakarta Validation rules.
- [ ] `@SpringBootTest(webEnvironment=NONE)` is used appropriately when testing service method validation alone.
- [ ] For MVC, both `@Valid @RequestBody` and direct `@Min`/`@NotBlank` on handlers are tested.
- [ ] MVC controllers do not carry class-level `@Validated` when intending to use Framework 6.1+ MVC built-in validation.
- [ ] Tests distinguish `MethodArgumentNotValidException` and `HandlerMethodValidationException`.
- [ ] `@ControllerAdvice` handles error schemas and statuses consistently across multiple validation paths.
- [ ] Tests assert the exact error source, not merely HTTP 400.
- [ ] Mockito mocks are never used as evidence of real Spring method validation proxies.
- [ ] Assertions do not depend on localized messages or violation ordering.
- [ ] Return-value violations are analyzed for side effects and transaction boundaries.
- [ ] Tests are executed via Maven/JUnit on JDK 17+ and the target Boot/framework version.
- [ ] All conclusions state their exact scope (raw object, proxy, MVC, or provider) without overgeneralizing.

**Conclusion:** Testing **method validation** is not checking whether `@NotBlank` or `@Min` appears on a method—it is proving **constraints are enforced at the actual entry point**. `new`/`this` calls normally bypass proxies; `@Validated` Spring services throw `ConstraintViolationException` via AOP; Spring MVC 6.1+ validates controllers via its own mechanism with `MethodArgumentNotValidException` or `HandlerMethodValidationException`. Quality tests **contrast direct Java calls with Spring-managed paths**, cover input/return/nested constraints, and never equate every service exception with HTTP 400.

### Official references

- [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
- [Spring Framework 6.2 — Java Bean Validation and Spring-driven Method Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — `@RequestBody` validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — `MethodValidationInterceptor` API](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationInterceptor.html)
- [Spring Framework 6.2 — Spring AOP proxying and self invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Jakarta Bean Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/)