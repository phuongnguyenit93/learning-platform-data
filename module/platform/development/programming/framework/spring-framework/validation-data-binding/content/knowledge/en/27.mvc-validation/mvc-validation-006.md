# Distinguishing Built-in MVC Integration from @Validated via AOP in Spring Framework

## 1. The problem: one constraint, multiple execution paths

In Spring Framework, both controllers and services can use Jakarta Validation constraints such as `@NotBlank`, `@Min`, `@NotNull`, or `@Valid`. However, **annotations are only metadata**: there must be a mechanism reading that metadata and actively checking it for constraints to take effect.

For example:

```java
@GetMapping("/orders")
public String find(@RequestParam @Min(1) long id) {
    return "order-" + id;
}
```

A request `GET /orders?id=0` will be processed by the Spring MVC machinery. Meanwhile, in a Spring service:

```java
@Service
@Validated
public class OrderService {

    public String find(@Min(1) long id) {
        return "order-" + id;
    }
}
```

A call `orderService.find(0)` can be validated by a **Spring AOP method-validation proxy**, but only when the bean/proxy and validation infrastructure are configured appropriately. The two paths differ in trigger timing, error types, HTTP handling, and technical limitations.

Even within controllers, Spring MVC further distinguishes **validating individual DTO arguments** from **method validation of the whole handler**.

In this lesson we clearly separate three branches:

1. **MVC argument validation:** `@Valid @RequestBody`, `@Valid @ModelAttribute`, or `@Valid @RequestPart` on a command object.
2. **MVC built-in method validation:** Spring Framework **6.1+** directly validates constraints on `@RequestMapping` handler method parameters/return values, **without an AOP proxy**.
3. **AOP method validation:** class-level `@Validated` (typically on a service) plus `MethodValidationPostProcessor`, validating calls **going through a proxy**.

**Objectives:** know which branch actually runs, when to include or omit `@Validated` on a controller, distinguish `MethodArgumentNotValidException` from `HandlerMethodValidationException` and `ConstraintViolationException`, run a Java 17+ example with Spring MVC, and write tests to prove it.

> **Version scope:** This content uses Spring Framework 6.1+/6.2.x and Spring Boot 3.x with Jakarta Validation (`jakarta.validation.*`). In particular, built-in MVC method validation was added in **Spring Framework 6.1**, so do not extrapolate this behavior back to Spring MVC 6.0. WebFlux has its own handler system; consult reactive-stack documentation for it.

## 2. Architecture map: where does validation happen?

### 2.1. HTTP request flowing through Spring MVC

```text
HTTP request
    |
    v
DispatcherServlet
    |
    v
HandlerMapping selects controller method
    |
    v
Argument resolvers / WebDataBinder / HttpMessageConverter
    |
    +--> Bind JSON/form/query/path to method arguments
    |
    +--> If DTO @Valid/@Validated is eligible:
    |       argument validation
    |       -> MethodArgumentNotValidException on error
    |
    +--> If handler requires method validation due to direct @Constraint:
            MVC built-in method validation (Framework 6.1+)
            -> HandlerMethodValidationException on error
    |
    v
Invoke handler, obtain return value
    |
    +--> If return constraints exist, MVC can also
          validate the return value after the handler runs
    |
    v
Handle response / exception resolvers
```

This is a conceptual flow, not the internal order of every component in every configuration. The essential point is that **MVC already has integration hooks inside argument binding and handler invocation**. It does not require a proxy to validate method constraints on controllers from Spring 6.1 onward.

### 2.2. Method call on a Spring bean via AOP

```text
A Spring bean calls serviceProxy.someMethod(args)
    |
    v
Spring AOP proxy / MethodValidationInterceptor
    |
    +--> validate method parameters
    |       if violations exist: typically throws
    |       ConstraintViolationException
    |
    v
Target service method executes
    |
    v
Method return value
    |
    +--> validate method return
    |       if violations exist: throws exception
    |
    v
Caller receives result
```

This is a different mechanism: a proxy wraps **method calls on a Spring bean**. It knows nothing about how an HTTP request was parsed, does not directly manage `BindingResult`, and does not map errors to HTTP 400.

### 2.3. Sharing Jakarta Validation, not the same integration

Underneath, both MVC and AOP can rely on a Jakarta Validation provider (usually Hibernate Validator) to check constraints. The difference lies in **who invokes the validator, when it is invoked, and who turns violations into responses/exceptions**. It is not because `@Min` in MVC is "stronger" than `@Min` in a service.

## 3. Core comparison table

| Criterion | MVC argument validation | MVC built-in method validation (6.1+) | AOP `@Validated` method validation |
| --- | --- | --- | --- |
| Target | A single DTO/command object bound from the request | The entire controller method contract | A bean method contract called through a proxy |
| Trigger | `@Valid` or `@Validated` on an eligible `@RequestBody`/`@ModelAttribute`/`@RequestPart` | Constraints like `@Min`/`@NotBlank` **directly** on parameters or return value | Class-level `@Validated` and `MethodValidationPostProcessor` |
| Requires AOP? | No | **No** | **Yes** |
| Tied to HTTP? | Yes, part of MVC argument resolution | Yes, part of MVC handler method execution | Not required; works in non-HTTP services |
| Constraints on DTO properties? | Yes, via cascading | Can be included via `@Valid` when method validation is triggered | Can cascade when method parameter/return uses `@Valid` |
| Typical error | `MethodArgumentNotValidException` | `HandlerMethodValidationException` | `ConstraintViolationException` by default |
| Framework HTTP status | Usually 400 for invalid input | Usually 400 for input; **return-value** errors are 500 | Not HTTP 400 by default; depends on exception handling |
| `BindingResult` | Can be placed right after the DTO for local handling | Can handle errors locally per method-validation rules | Not part of the AOP proxy contract |
| Direct Java call bypassing MVC | Does not run MVC binding/validation | Does not run MVC validation | Runs only if called through an eligible proxy |
| Self-invocation `this.method()` | Unrelated to request binding | Not MVC's request validation point | Usually **bypasses** proxy advice |

**Do not collapse these three columns into one mechanism.** For instance, `@Valid` on a DTO does not necessarily trigger method validation, while class-level `@Validated` on a controller can route you to the older AOP branch instead of the built-in MVC branch you intended to use.

## 4. `@Valid`, `@Validated`, and `@Constraint`: their real roles

### 4.1. Jakarta Validation's `@Valid`

```java
@PostMapping("/people")
public ResponseEntity<?> create(
        @Valid @RequestBody PersonRequest request) {
    // ...
}
```

`@Valid` denotes **cascaded validation**: checking constraints inside `PersonRequest` after the data is parsed/bound. It is not a direct constraint with `message`, `groups`, and `payload` like `@NotBlank`.

If a handler **does not need method validation** because it has no direct constraints on parameters/return values, a `@Valid @RequestBody` case like the one above is usually handled by the argument resolver and can throw `MethodArgumentNotValidException` when there is no immediately following `BindingResult`.

### 4.2. Spring's `@Validated`

`org.springframework.validation.annotation.Validated` plays two different roles depending on **placement**:

- **On a DTO argument** (e.g., `@Validated(Create.class) @RequestBody Request request`): acts as a validation hint/group selector, similar to `@Valid` in triggering validation while allowing explicit groups.
- **On a Spring bean class** (e.g., `@Service @Validated`): signals `MethodValidationPostProcessor` to apply a method-validation **AOP proxy** to the bean.

`@Validated` **is not** a Jakarta `@Constraint`; it does not validate a `String` or `int` by itself. You still need `@NotBlank`, `@Min`, a custom constraint, `@Valid`, etc. on the proper target.

**Common confusion:** Using `@Validated` on a DTO argument to pick groups does not mean you must also put `@Validated` on the controller class. The effects and execution paths differ.

### 4.3. Direct constraints on handler parameters

```java
@GetMapping("/page")
public String page(@RequestParam("size") @Min(1) int size) {
    return "size=" + size;
}
```

`@Min` is a **direct constraint** on a method parameter. In Spring MVC 6.1+ with a Jakarta Validation provider, it activates the **MVC built-in method validation** branch. When `size=0`, errors normally go through `HandlerMethodValidationException`, not `MethodArgumentNotValidException`.

Similarly, a constraint placed **directly on the method** such as:

```java
@NotBlank
@GetMapping("/token")
public String token() {
    return "";
}
```

marks a **return-value constraint**. After the handler executes, MVC can validate the return value and report violations via `HandlerMethodValidationException`, with HTTP status **500** for server-side postcondition violations per the exception's contract.

### 4.4. Methods with both direct constraints and a `@Valid` DTO

```java
@PostMapping("/items")
public ResponseEntity<?> create(
        @RequestParam("count") @Min(1) int count,
        @Valid @RequestBody ItemRequest request) {
    // ...
}
```

Because `@Min` is directly on the `count` parameter, this handler **requires method validation**. Spring MVC 6.1+ lets method validation check both `count` and the constraints inside `ItemRequest` via `@Valid`; in this case it **replaces** the argument resolver's standalone DTO validation, avoiding duplicate checks.

Consequently, the exact same `ItemRequest` DTO with `name=""` can produce **different exception types** depending on the controller signature:
- Handler with only `@Valid @RequestBody ItemRequest`: typically `MethodArgumentNotValidException`.
- Handler that also has a direct `@Min` on another parameter: typically `HandlerMethodValidationException`.

This is a notable behavioral shift when upgrading to Framework 6.1+ or adding direct constraints to controllers.

## 5. Why remove `@Validated` from controller classes if using MVC 6.1+?

Spring Framework documentation states clearly: **if a controller has class-level `@Validated`, method validation is applied via an AOP proxy**. To use **built-in MVC method validation** introduced in Spring 6.1, **remove `@Validated` from the controller class**.

### 5.1. Pattern to avoid when wanting built-in MVC validation

```java
@RestController
@Validated // Selects method validation via AOP proxy.
@RequestMapping("/api")
public class SampleController {

    @GetMapping("/quantity")
    public String quantity(
            @RequestParam("count") @Min(1) int count) {
        return "count=" + count;
    }
}
```

This code is not invalid in every version; prior to Spring 6.1, AOP was the standard way to enforce direct constraints on controllers. In MVC 6.1+, however, it is **not** the recommended setup if you want the built-in mechanism and standard MVC exception/handling behavior.

### 5.2. Recommended pattern in MVC 6.1+

```java
@RestController
@RequestMapping("/api")
public class SampleController { // No @Validated on the class.

    @GetMapping("/quantity")
    public String quantity(
            @RequestParam("count") @Min(1) int count) {
        return "count=" + count;
    }
}
```

With a Jakarta Validation provider present and MVC configured properly, the direct `@Min` is verified **inside MVC's handler invocation flow**.

**Do not misinfer:** "Removing `@Validated` from the controller" does **not** mean disabling validation. It simply selects the built-in MVC mechanism for method validation. `@Valid`/`@Validated` placed **on a DTO argument** to trigger validation/groups may still be needed.

### 5.3. Services can still use `@Validated`

```java
@Service
@Validated
public class PricingService {

    public BigDecimal price(
            @NotBlank String sku,
            @Min(1) int quantity) {
        return BigDecimal.TEN;
    }
}
```

In a service, no Spring MVC argument resolver wraps calls from other code. When you want to enforce method contracts, class-level `@Validated` and AOP method validation remain normal practice, provided the bean is Spring-managed and calls go through its proxy.

Do not "remove all `@Validated` from the entire project" just because you read guidance meant specifically for **MVC controller classes**.

## 6. Exceptions: you cannot handle all three branches with one assumption

### 6.1. `MethodArgumentNotValidException`

Typically occurs when Spring MVC binds and validates a **standalone DTO argument**, for example:

```java
public record NewUser(
        @NotBlank(message = "name.required") String name) {}

@PostMapping("/users")
public void create(@Valid @RequestBody NewUser user) {
    // ...
}
```

If the body has `{"name":""}` and the handler does not need method validation, Spring MVC typically returns HTTP 400 and raises `MethodArgumentNotValidException`. This exception carries binding/validation data such as `BindingResult` and `FieldError`, making per-field error responses straightforward.

### 6.2. `HandlerMethodValidationException`

This is the Spring MVC exception for **handler method validation**. Scenarios include:
- Direct parameter `@Min(1)` fails.
- Direct parameter `@NotBlank` fails.
- A `@Valid` DTO fails **inside a handler that already activated method validation**.
- A return-value constraint fails, e.g., `@NotNull` on a method that returns `null`.

By default, Spring MVC treats input validation failures as **400 Bad Request**. For return-value validation failures, the exception signals a server-side postcondition bug and uses **500 Internal Server Error**. Return errors are not client request errors, so never blindly convert them to 400.

### 6.3. `ConstraintViolationException` via AOP

By default, `MethodValidationPostProcessor` can use `MethodValidationInterceptor` to throw `jakarta.validation.ConstraintViolationException` when a proxied method's parameter or return value is invalid. This exception contains a `Set<ConstraintViolation<?>>` and is **not automatically** bound to HTTP status 400.

If a controller calls a service and the service throws this exception, you need an explicit handling policy: input errors attributable to the client might be 400/422 depending on the API; violations of service invariants or return contracts might be 500. Do not create a blanket handler saying "every `ConstraintViolationException` is 400", as it can mask programming bugs.

Since Spring 6.1, `MethodValidationPostProcessor#setAdaptConstraintViolations(true)` can adapt violations into Spring's validation result and throw `org.springframework.validation.method.MethodValidationException` instead of `ConstraintViolationException`. Know your actual configuration before writing exception handlers.

### 6.4. Exception routing table

| Scenario | Primary handling branch | Typical error type |
| --- | --- | --- |
| `@Valid @RequestBody Dto`, no method validation needed | MVC argument resolver | `MethodArgumentNotValidException` |
| `@Valid @ModelAttribute Dto`, no method validation needed | MVC binder | `MethodArgumentNotValidException` |
| `@Valid @RequestPart Dto`, no method validation needed | MVC part + converter | `MethodArgumentNotValidException` |
| `@Min(1) @RequestParam int` on 6.1+ controller without class `@Validated` | MVC built-in method | `HandlerMethodValidationException` |
| Handler with direct `@Min` and invalid `@Valid` DTO | MVC built-in method | `HandlerMethodValidationException` |
| Controller return `@NotNull` fails | MVC built-in method return | `HandlerMethodValidationException` (typically 500) |
| `@Validated` Spring service receives invalid arguments via proxy | Spring AOP | `ConstraintViolationException` (default) |
| AOP with adaptation enabled | Spring AOP | `MethodValidationException` |
| Missing `@RequestParam(required=true)` | MVC argument resolver/binding | `MissingServletRequestParameterException`, not Bean Validation |
| Query string `"abc"` fails conversion to `int` | MVC type conversion | Type error like `MethodArgumentTypeMismatchException`, not `@Min` |

The table describes default/common mechanisms; `@ControllerAdvice`, `BindingResult`, and Framework versions can change actual responses. When debugging, look at the actual exception type and stack trace first.

## 7. Standalone Spring Boot 3.5.6 + Java 17 example

The goal of this example is to **observe all three paths in one application**:

1. Endpoint `GET /api/quantity?count=0`: direct `@Min` on the controller ⇒ built-in MVC method validation.
2. Endpoint `POST /api/profiles`: `@Valid @RequestBody` only ⇒ MVC argument validation.
3. Endpoint `POST /api/mixed`: combines direct `@Min` and `@Valid` DTO ⇒ built-in MVC method validation covering the DTO as well.
4. A `ReservationService` with class-level `@Validated` ⇒ method validation via AOP proxy.
5. Automated tests distinguishing exact **exception classes**, not just HTTP status.

The example uses Spring Boot **3.5.6** (an actual release in the Boot 3.5 line using Spring Framework 6.2.x). This is a consistent illustrative version and does not imply it is the latest Boot release. Do not copy dependency versions blindly across different major Boot lines without verifying compatibility.

### 7.1. Directory layout

```text
mvc-vs-aop-validation/
├── pom.xml
└── src/
    ├── main/java/demo/validation/
    │   ├── ValidationModesApplication.java
    │   ├── ProfileRequest.java
    │   ├── ReservationService.java
    │   └── DemoController.java
    └── test/java/demo/validation/
        └── ValidationModesTest.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>mvc-vs-aop-validation</artifactId>
    <version>1.0-SNAPSHOT</version>

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

- `spring-boot-starter-web` provides Spring MVC and the embedded Servlet container.
- `spring-boot-starter-validation` provides Jakarta Validation integration/provider.
- `spring-boot-starter-aop` makes the proxy infrastructure for the service explicit; in another project, this dependency might already come transitively from another starter.
- `spring-boot-starter-test` provides JUnit Jupiter, Spring Test, and `MockMvc`.
- Dependency versions are managed by the Boot parent.

### 7.3. `ValidationModesApplication.java`

```java
package demo.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationModesApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationModesApplication.class, args);
    }
}
```

There is no need to manually declare an extra `MethodValidationPostProcessor` if Boot's auto-configuration infrastructure already configures it. Registering a duplicate bean post-processor unnecessarily can create unintended proxy behavior.

### 7.4. `ProfileRequest.java`

```java
package demo.validation;

import jakarta.validation.constraints.NotBlank;

public record ProfileRequest(
        @NotBlank(message = "profile.name.blank") String name) {
}
```

This constraint belongs to a **DTO property**. What determines the exception type is not this annotation changing, but whether the **controller method** receiving the DTO has direct method constraints or not.

### 7.5. `ReservationService.java` — AOP method validation

```java
package demo.validation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

import java.util.concurrent.atomic.AtomicInteger;

@Service
@Validated
public class ReservationService {

    private final AtomicInteger calls = new AtomicInteger();

    @NotBlank(message = "reservation.result.blank")
    public String reserve(
            @NotBlank(message = "reservation.code.blank") String code,
            @Min(value = 1, message = "reservation.count.small")
            int count) {

        calls.incrementAndGet();
        return code.repeat(count);
    }

    public int calls() {
        return calls.get();
    }
}
```

**Why is `@Validated` needed here?** This is a Spring service bean, not an MVC handler. `MethodValidationPostProcessor` finds classes annotated with `@Validated` and puts method-validation advice on the proxy. When another bean injects `ReservationService` and calls `reserve("", 2)` **through the proxy**, the method parameter constraints are checked before the body executes; the `calls` counter does not increment.

`@NotBlank` placed on the method is a **return-value** constraint checked after the method returns. The example always produces a valid return when inputs are valid, yet the postcondition is still shown to learn how the two phases differ.

Also note: `@Validated` on the class does not require every method to have constraints. `calls()` has no constraints; it simply reports how many times the business method executed so tests stay transparent.

### 7.6. `DemoController.java` — built-in MVC, no controller AOP

```java
package demo.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class DemoController {

    // Intentionally do NOT place @Validated on the controller class.

    @GetMapping("/quantity")
    public Map<String, Integer> quantity(
            @RequestParam("count") @Min(1) int count) {
        return Map.of("count", count);
    }

    @PostMapping("/profiles")
    public Map<String, String> profile(
            @Valid @RequestBody ProfileRequest request) {
        return Map.of("name", request.name());
    }

    @PostMapping("/mixed")
    public Map<String, Object> mixed(
            @RequestParam("count") @Min(1) int count,
            @Valid @RequestBody ProfileRequest request) {
        return Map.of(
                "count", count,
                "name", request.name());
    }
}
```

Three points to observe:

- `quantity()` has `@Min` **directly** on a parameter ⇒ Spring MVC 6.1+ uses built-in method validation.
- `profile()` only has `@Valid` on a DTO argument ⇒ Spring MVC uses regular argument validation; no AOP needed.
- `mixed()` has a direct `@Min` ⇒ Spring MVC uses method validation, **encompassing** nested validation of `ProfileRequest` via `@Valid`.

This lets us compare the exact same `ProfileRequest` DTO along two different paths without adding `@Validated` to the controller class.

### 7.7. `ValidationModesTest.java` — testing all three paths

```java
package demo.validation;

import jakarta.validation.ConstraintViolationException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ValidationModesTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ReservationService service;

    @Test
    void mvcDirectConstraintUsesHandlerMethodValidation() throws Exception {
        mvc.perform(get("/api/quantity")
                        .param("count", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(result ->
                        assertInstanceOf(
                                HandlerMethodValidationException.class,
                                result.getResolvedException()));
    }

    @Test
    void mvcDtoOnlyUsesArgumentValidation() throws Exception {
        mvc.perform(post("/api/profiles")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(result ->
                        assertInstanceOf(
                                MethodArgumentNotValidException.class,
                                result.getResolvedException()));
    }

    @Test
    void mixedHandlerValidatesNestedDtoAtMethodLevel() throws Exception {
        mvc.perform(post("/api/mixed")
                        .param("count", "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(result ->
                        assertInstanceOf(
                                HandlerMethodValidationException.class,
                                result.getResolvedException()));
    }

    @Test
    void mvcAcceptsValidInput() throws Exception {
        mvc.perform(get("/api/quantity")
                        .param("count", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(2));
    }

    @Test
    void serviceProxyRejectsInvalidInputBeforeMethodBody() {
        int before = service.calls();

        ConstraintViolationException error =
                assertThrows(
                        ConstraintViolationException.class,
                        () -> service.reserve("", 2));

        assertEquals(before, service.calls());
        assertEquals(1, error.getConstraintViolations().size());
    }

    @Test
    void serviceProxyAcceptsValidInput() {
        assertEquals("ABAB", service.reserve("AB", 2));
    }
}
```

Run tests from the project directory:

```bash
mvn test
```

**All 6 tests are expected to pass in a valid Maven/JDK 17 environment.** These assertions carry the following meanings:

| Test | Meaning of the outcome |
| --- | --- |
| `mvcDirectConstraintUsesHandlerMethodValidation` | MVC returns 400 and the resolved exception is `HandlerMethodValidationException` |
| `mvcDtoOnlyUsesArgumentValidation` | Standalone `@Valid` DTO returns 400 with `MethodArgumentNotValidException` |
| `mixedHandlerValidatesNestedDtoAtMethodLevel` | Same invalid DTO, but the handler has direct `@Min` so the exception comes from the method branch |
| `mvcAcceptsValidInput` | Value `count=2` through MVC is accepted |
| `serviceProxyRejectsInvalidInputBeforeMethodBody` | Calling the service through its proxy throws `ConstraintViolationException`; the counter does not increment |
| `serviceProxyAcceptsValidInput` | Service with valid input returns `"ABAB"` |

Use `MockMvc` in the first three tests to observe the exception **after the MVC exception resolver has processed it**. Use `assertThrows` when calling the injected Spring service bean directly to prove the **AOP proxy**. These are two different testing levels.

Test execution order is not guaranteed. That is why the call-count test records `before = service.calls()` right before the invalid call, rather than asserting that total calls across the suite are always 0.

If the MVC direct-constraint test does **not** produce `HandlerMethodValidationException`, first verify Spring Framework is at least 6.1 and the controller class does not have `@Validated`. If the service test does **not** throw an exception, check `@Validated` on the service, the bean post-processor, validation/AOP dependencies, and whether the injected object is actually a proxy.

### 7.8. Running the app and checking with HTTP

Start:

```bash
mvn spring-boot:run
```

Send a valid request:

```bash
curl -i 'http://localhost:8080/api/quantity?count=2'
```

Expected HTTP **200** with JSON:

```json
{"count":2}
```

Input violating the direct constraint:

```bash
curl -i 'http://localhost:8080/api/quantity?count=0'
```

Expected HTTP **400**. The error body shape depends on Spring Boot error handling and Problem Details configuration; do not assume the JSON body always contains a specific field unless you wrote a `@ControllerAdvice`.

An invalid DTO:

```bash
curl -i -X POST \
  'http://localhost:8080/api/profiles' \
  -H 'Content-Type: application/json' \
  -d '{"name":""}'
```

Also normally returns HTTP **400**, yet it follows the **argument validation** branch. Looking only at status 400 will not tell you which mechanism the provider/framework went through; that is why tests must assert the exception type as in `ValidationModesTest`.

The exact same DTO on the combined handler:

```bash
curl -i -X POST \
  'http://localhost:8080/api/mixed?count=1' \
  -H 'Content-Type: application/json' \
  -d '{"name":""}'
```

Expected HTTP **400**, but the **MVC method validation** branch is activated by `@Min` on the `count` parameter.

## 8. How do `BindingResult` and `Errors` interact?

This is an important MVC boundary that AOP services do not have.

### 8.1. Handling DTO errors locally

```java
@PostMapping("/profiles")
public ResponseEntity<?> create(
        @Valid @RequestBody ProfileRequest request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "profile.invalid"));
    }

    return ResponseEntity.ok(Map.of("name", request.name()));
}
```

This is an **illustrative** snippet replacing `profile()` in the main example, not something to copy verbatim alongside it into `DemoController.java`. You need to import `BindingResult` and `ResponseEntity`. `BindingResult` must appear **immediately after** the bound/validated argument. When validation errors are handled locally, the controller can return a custom error payload without letting `MethodArgumentNotValidException` bubble up to a global handler.

### 8.2. When the handler also has method validation

```java
@PostMapping("/mixed")
public ResponseEntity<?> mixed(
        @Valid @RequestBody ProfileRequest request,
        BindingResult errors,
        @RequestParam("count") @Min(1) int count) {
    // ...
}
```

With MVC 6.1+ method validation, Spring still respects `Errors`/`BindingResult` for supported parameters. The handler is invoked only when **all validation errors belong to parameters that have an `Errors` or `BindingResult` immediately following them** to handle those errors. If another parameter also has errors, such as `count=0` without a corresponding `BindingResult`, `HandlerMethodValidationException` can still be thrown.

Therefore, do not conclude that "having one `BindingResult` in a method swallows every method validation error". `BindingResult` binds strictly to the **immediately preceding argument** and only covers errors within MVC's supported scope.

### 8.3. AOP does not consume `BindingResult` like MVC

`MethodValidationInterceptor` in a service does not participate in MVC argument binding. If you pass an arbitrary `BindingResult` object into a service, the interceptor does not automatically treat it as an error channel for the preceding method parameter. It still handles Jakarta constraint violations according to AOP policy (typically throwing `ConstraintViolationException`).

## 9. Validation groups: do not put `@Validated` in the wrong place

Example of a DTO with extra rules in the `Publish` group:

```java
public interface Publish {}

public record ArticleRequest(
        @NotBlank String title,
        @Size(min = 20, groups = Publish.class) String body) {}
```

This is an illustrative snippet requiring imports for `jakarta.validation.constraints.NotBlank` and `Size`.

### 9.1. Selecting groups for an MVC DTO argument

```java
@PostMapping("/articles")
public void publish(
        @Validated(Publish.class)
        @RequestBody ArticleRequest request) {
    // ...
}
```

`@Validated(Publish.class)` sits **on the argument** and passes the appropriate validation hint/group for DTO validation. Requesting only `Publish` does not automatically check `Default` constraints such as `@NotBlank`, unless group inheritance/sequences or other configurations apply. To apply both groups, you can declare `@Validated({Default.class, Publish.class})` when appropriate.

### 9.2. Selecting groups in an AOP service

```java
@Service
@Validated(Publish.class)
public class PublishingService {

    public void publish(
            @NotBlank(groups = Publish.class) String title) {
        // ...
    }
}
```

In a service, class-level `@Validated(Publish.class)` **is the annotation used by AOP to select the bean and groups**. Do not apply the "remove `@Validated` from controllers" rule to this service; the two places have different roles.

### 9.3. Do not arbitrarily mix class-level controller AOP and DTO groups

If a controller needs group-based DTO validation, prefer `@Validated(Publish.class)` **on the argument needing the group** rather than switching the whole controller to class-level `@Validated` just to get groups. A class-level controller annotation has broader architectural consequences: it routes method validation to an AOP proxy, changing exception types and MVC integration behavior.

For method-level groups and direct validation on handlers, consult your framework version's documentation and current limitations rather than assuming every AOP service group option automatically means the same thing in built-in MVC validation.

## 10. Why does Spring AOP sometimes skip validation despite `@Validated`?

An AOP proxy is not a VM instrumenting every method call. It only intercepts calls **passing through the proxy** that satisfy advisor/interceptor conditions.

### 10.1. Self-invocation

```java
@Service
@Validated
public class PaymentService {

    public void process() {
        charge(-1); // Call from the target itself: typically bypasses proxy.
    }

    public void charge(@Min(1) int amount) {
        // ...
    }
}
```

This illustrative snippet requires Spring/Jakarta Validation imports. When `process()` executes inside the same target, calling `this.charge(-1)` does not pass through the outer proxy. Thus, method-validation advice normally does not run for `charge` on that path.

The usual fix is splitting it into another bean and calling that bean via dependency injection, or restructuring so the call goes through the proxy. If an internal flow must be enforced independently of Spring AOP, consider calling the Jakarta Validation API directly at the control point or expressing the invariant with plain Java checks.

### 10.2. Objects instantiated directly with `new`

```java
PaymentService service = new PaymentService();
service.charge(-1);
```

This is **not** a Spring-managed proxy; merely having `@Validated` in source code does not make an object created with `new` validated by Spring AOP.

### 10.3. JDK/CGLIB proxy limitations

- JDK dynamic proxies operate through interfaces; class-based proxies rely on subclassing/CGLIB.
- Private methods are not join points that standard proxy-based advice can intercept.
- Final methods cannot be overridden for standard class-based proxy advice.
- Interface/implementation layout, method visibility, bean lifecycle, and how calls are resolved can affect whether the advisor sees method metadata.

When debugging, do not just look for the annotation—verify the **actual call path** and confirm the bean came from the Spring container.

### 10.4. Built-in MVC also has its own boundaries

Spring MVC's built-in method validation only participates in **handler invocations through `DispatcherServlet` and the MVC machinery**. If you call a controller method directly from a test like a plain Java method, that is not an HTTP handler invocation; you cannot conclude MVC validation is broken from seeing "no exception" on a direct call.

Use `MockMvc` or an HTTP test going through MVC to prove this branch.

## 11. Reading and normalizing errors at the right layer

### 11.1. When choosing `ResponseEntityExceptionHandler`

Spring Framework provides `ResponseEntityExceptionHandler` for MVC. Inside a `@ControllerAdvice` extending it, you can override the corresponding handler hooks for:

- `handleMethodArgumentNotValid(...)`: DTO argument validation.
- `handleHandlerMethodValidationException(...)`: MVC method validation.

These methods let you translate errors into consistent `ProblemDetail`/`ResponseEntity` payloads. Exact method signatures depend on the Spring Framework version; when implementing for real, check the JavaDoc of the version in use instead of copying signatures from another release. You can also use `@ExceptionHandler`, avoiding duplicate definitions for exceptions already handled by the superclass.

### 11.2. Handling `HandlerMethodValidationException`

The exception has structured method validation results, allowing access per method parameter. Besides `getAllValidationResults()`, Spring provides iteration over results and visitor APIs. If you need to return field/parameter names to clients, rely on metadata and result structures rather than arbitrarily splitting message strings.

For return-value errors, log enough context for operations and return a **server error** instead of blaming the request. Never send arbitrary invalid return values straight to clients, as they may contain sensitive data.

### 11.3. Handling `ConstraintViolationException` from AOP services

You can iterate over it:

```java
for (ConstraintViolation<?> violation
        : exception.getConstraintViolations()) {

    String path = violation.getPropertyPath().toString();
    String message = violation.getMessage();
    // Convert into error code / structured response per API contract.
}
```

This is an illustrative fragment assuming `exception` is a `ConstraintViolationException` with corresponding Jakarta Validation imports. `ConstraintViolation` is not the same as MVC's `FieldError`. A method parameter can have a path like `reserve.code` or `reserve.arg0` depending on `ParameterNameProvider` and compiler flags.

If a controller calls a service and the service throws `ConstraintViolationException`, handle it at the **application boundary** according to error classification and API policy. Do not let every unchecked exception silently become a vague 500 error, nor assume every violation is an HTTP client input error.

### 11.4. Parsing/binding errors are not Bean Validation errors

Examples:
- Missing required query parameter `count`: `MissingServletRequestParameterException`.
- Passing `count=abc` to bind into `int`: type conversion error.
- Unreadable JSON: `HttpMessageNotReadableException`.

These errors can occur **before** `@Min(1)` ever has a valid `int` value to inspect. That is why returning 400 does not prove an error came from Jakarta Validation.

## 12. Comparison exercise: changing just one annotation

This is a practical exercise when upgrading projects.

### Experiment A: controller without class-level `@Validated`

```java
@RestController
public class ExampleController {

    @GetMapping("/example")
    public String get(@RequestParam("n") @Min(1) int n) {
        return Integer.toString(n);
    }
}
```

In Spring MVC 6.1+ with a configured provider, send `?n=0`. Observe `HandlerMethodValidationException`. This is the built-in branch.

### Experiment B: add `@Validated` onto the controller class

```java
@RestController
@Validated
public class ExampleController {
    // Same handler as above.
}
```

Now you have requested method validation via **AOP** for the controller. When method validation runs through a proxy, the exception type may change to `ConstraintViolationException` or an adapted exception; HTTP handling may also differ. Do not compare only HTTP statuses—inspect the actual exception, proxy, and post-processor configuration.

This is a separate experiment; **do not modify `DemoController.java` from the main runnable example** if you want the earlier six tests to keep passing as written.

### Experiment C: keep built-in MVC controller, add `@Validated` to the service

Place `@Validated` on `ReservationService` as in section 7. Use `MockMvc` to test the controller and `assertThrows` to test the service. You will see both paths coexist without conflict:
- Controller validation by MVC.
- Service validation by AOP.

That is usually the desired separation of responsibilities.

### Experiment D: remove `@Min` from `mixed()`

If `mixed()` is left with only `@Valid @RequestBody ProfileRequest` (and no other direct method constraints), predict the exception for `{"name":""}`. In a standard configuration, validation reverts to the argument resolver branch and `MethodArgumentNotValidException`. No annotation on the `ProfileRequest` record needs to change.

## 13. Checklist when upgrading from Spring 6.0 to 6.1+

1. **Verify versions:** does the app use Framework 6.1+ and a Jakarta Validation provider?
2. **Inventory controllers with class-level `@Validated`:** this is usually a sign of AOP method validation on older controllers.
3. **Decide to adopt built-in MVC validation:** for controllers wanting built-in validation, remove class-level `@Validated` per Spring guidance. Do not blindly delete argument-level `@Valid`/`@Validated`.
4. **Inventory direct method constraints:** `@Min`, `@NotBlank`, `@NotNull` on parameters and return values.
5. **Update exception handling:** add handling for `HandlerMethodValidationException` alongside `MethodArgumentNotValidException`; avoid handlers supporting only one type.
6. **Retest handlers combining `@Valid` DTOs and direct constraints:** the exception may shift from argument-level to method-level, not because DTO rules disappeared.
7. **Check `BindingResult` placement:** immediately after the target argument; never assume one `BindingResult` catches every error in the handler.
8. **Keep `@Validated` on services where needed:** AOP method validation on services is not replaced by built-in MVC validation.
9. **Check self-invocation and proxies:** calls originating inside the same bean can bypass AOP method validation.
10. **Distinguish input errors from return errors:** invalid input is a bad request; return-invariant failure is usually a server error.
11. **Write tests asserting exception types, not just HTTP status:** 400 could be a missing parameter, JSON parse error, DTO validation, or handler method validation.
12. **Avoid duplicate infrastructure registration:** avoid manually creating extra post-processors/advisors if Spring Boot already configures them.

## 14. Common misconceptions

| Misconception | Reality | How to fix |
| --- | --- | --- |
| "Having `@Valid` means method validation runs" | `@Valid` is a cascade marker; DTO argument validation can run separately | Check whether a direct `@Constraint` exists on the handler |
| "Spring MVC method validation always requires `@Validated` on the controller" | Since Framework 6.1, MVC supports built-in validation without class-level `@Validated` | Remove the class-level annotation when built-in MVC is intended |
| "A controller with `@Validated` definitely still goes through the new built-in MVC path" | Class-level `@Validated` selects the AOP proxy path per Spring docs | Assign controller/service annotations to their proper roles |
| "Service `@Validated` needs no proxy" | AOP method validation relies on calls passing through a Spring proxy | Check the actual bean and self-invocation |
| "Invalid `@Valid @RequestBody` always throws `MethodArgumentNotValidException`" | When the handler has direct constraints, MVC method validation can cover the DTO too | Test combined handlers and handle `HandlerMethodValidationException` |
| "All 3 exceptions automatically produce HTTP 400" | AOP exceptions have no default HTTP status; MVC return failures are typically 500 | Classify error source and phase |
| "`BindingResult` anywhere catches all errors" | It binds strictly to the immediately preceding argument and corresponding validation path | Place it properly and account for errors on other parameters |
| "Calling a controller method directly tests MVC validation" | Direct Java calls bypass `DispatcherServlet` | Use `MockMvc`/HTTP integration tests |
| "`@Validated` on a DTO argument is identical to `@Validated` on a controller class" | On an argument it selects validation hints/groups; on a class it can activate a proxy | Interpret based on annotation placement |
| "`@NotBlank` runs as soon as a JSON string is parsed" | Requires the validation step after binding/argument resolution | Ensure a provider and trigger annotation are at the right layer |
| "Seeing no error means validation passed" | Validation may not have been triggered, proxy may be absent, or annotation misplaced | Test invalid inputs and assert the exception type |
| "Throwing `ConstraintViolationException` is the default behavior of `Validator.validate()`" | Jakarta Validation API directly returns `Set<ConstraintViolation>` | The caller decides to throw, unlike the AOP interceptor |

## 15. Practical design scenarios

### 15.1. Controller receives DTO, service executes business logic

A clean typical design:

```text
HTTP client
   |
   v
Spring MVC controller
 - bind JSON/form/query
 - @Valid DTO + direct parameter constraints
 - translate input errors into a consistent response
   |
   v
Spring service bean
 - @Validated method contracts via AOP (if needed)
 - enforce business invariants and authorization
 - handle transactional logic
   |
   v
Repository / external services
```

**Do not put `@Validated` on the controller class just because the service has `@Validated`.** Each layer has its own responsibility.

DTO validation at the boundary provides fast client feedback; method validation on services preserves contracts when a service is called from multiple entry points (HTTP, scheduler, message consumer, CLI), **provided** calls pass through a properly configured proxy. Critical invariants still need protection in domain/service logic rather than delegating everything to HTTP annotations.

### 15.2. Can validation happen twice?

Yes. For instance, the controller puts `@Valid` on a DTO, and then a `@Validated` service also puts `@Valid` on the same DTO. Two layers validate at two different boundaries; this is not always redundant, because the service may also be invoked from other callers. However, for a single HTTP request, the system may perform validation twice.

In contrast, when **a single MVC handler** needs method validation due to direct constraints, Spring 6.1+ designs method validation to **replace** the corresponding standalone argument validation, avoiding double validation within the same handler. Do not confuse these two scenarios.

### 15.3. When to invoke `ExecutableValidator` manually?

If a library or integration does not go through Spring MVC or an AOP proxy, you can still obtain:

```java
jakarta.validation.Validator validator = /* injected validator */;
var executables = validator.forExecutables();

var problems = executables.validateParameters(
        targetObject, reflectedMethod, argumentArray);
```

This is an illustrative snippet because `targetObject`, `reflectedMethod`, and `argumentArray` depend on context. The API returns `Set<ConstraintViolation<T>>`. This demonstrates that both MVC and AOP are simply **integration mechanisms calling the validation engine**, not the only way Jakarta Validation can run.

### 15.4. When should constraint annotations not be used?

Some invariants must be checked inside domain logic (such as inventory stock at transaction time, authorization permissions, or database entity existence). `@Min`/`@NotBlank` do not replace transactions, authorization, or race-condition checks. MVC validation and service method validation enforce **data contracts**, not every complex business invariant.

## 16. Knowledge self-check

1. A controller has no class-level `@Validated` yet has `@Min(1)` on `@RequestParam`, running Spring MVC 6.2. When `0` is sent, which mechanism validates it and what is the typical exception?
2. On that same controller, add `@Validated` at the **class level**. Why might the exception type and handling change?
3. Two handlers both accept `@Valid @RequestBody ProfileRequest`. Handler A has only the DTO; handler B also has `@Min` on a query parameter. Why can an empty DTO yield two different exception types?
4. You place `@Validated` on `ReservationService` and call `this.reserve("", 1)` from inside the service itself. Why might validation be skipped?
5. An AOP service throws `ConstraintViolationException` where the violation is on the **return value**. Should you automatically return HTTP 400 to the client? Explain.
6. When an MVC handler has `BindingResult` right after a DTO, yet `@Min` on another parameter fails, is the handler invoked? Why?
7. A request missing `@RequestParam(required=true)` receives 400; can you conclude `@Min` ran? What should you check?
8. If you want to validate a service method in a unit test without starting Spring, which Jakarta Validation API can you use?
9. When upgrading from Spring 6.0 to 6.1+, what tests should you add to prove the switch from controller AOP to built-in MVC worked properly?
10. Why do `@Validated(Group.class)` on a DTO argument and `@Validated(Group.class)` on a service class not share the same architectural role?

**Short conclusion:** MVC validation is **part of the HTTP processing lifecycle**; Spring MVC 6.1+ provides built-in method validation on handlers; Spring's class-level `@Validated` is **how AOP method validation is enabled** for beans such as services. Choose the right mechanism based on where the call passes through—never assume seeing the same `@Min` annotation implies identical exceptions and behavior everywhere.

## 17. References

- [Spring Framework 6.2 — Validation of Spring MVC controller methods](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Java Bean Validation and method validation via AOP](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — Understanding AOP proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — `@RequestBody`, Bean Validation, and `BindingResult`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — `ResponseEntityExceptionHandler`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Framework — `HandlerMethodValidationException`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [Spring Framework — `MethodValidationPostProcessor`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html)
- [Jakarta Validation specification — method and parameter validation](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html#constraintdeclarationvalidationprocess-methodlevelconstraints)
- [Spring Boot — Dependency validation and application configuration](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
- [Spring Boot 3.5.6 release announcement](https://spring.io/blog/2025/09/18/spring-boot-3-5-6-available-now/)