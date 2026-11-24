# Spring's @Validated and Validation Group Selection

> **Module:** Spring Framework – validation-data-binding  
> **Parent Topic:** Bean Validation  
> **Focus:** Selecting the right set of Jakarta Validation constraints at each input boundary with `org.springframework.validation.annotation.Validated`, especially when CREATE/UPDATE have different rules.

## 1. Learning Objectives

After this lesson, you will:

1. Distinguish Spring's `@Validated` from Jakarta Validation's `@Valid`.
2. Declare marker interfaces for groups and attach `groups = ...` to constraints.
3. Understand the `Default` group accurately and how to combine `Default.class` with `Create.class` or `Update.class`.
4. Use `@Validated(...)` on `@RequestBody`, `@ModelAttribute` parameters and use Jakarta's `Validator.validate(bean, groups...)` for self-testing.
5. Distinguish `@Validated` on **controller parameters** from `@Validated` on **service classes** for AOP method validation.
6. Distinguish Bean Validation errors on individual parameter validation from Spring MVC 6.1+ built-in method validation.
7. Use group inheritance, `@GroupSequence`, and `@ConvertGroup` when genuinely needed, while avoiding overly complex group designs.

## 2. When Are Validation Groups Needed?

One DTO can be used across multiple operations:

- **Creating an account:** `id` must be absent because the server generates the id; `username` is required.
- **Updating an account:** `id` must be present; `username` is still required.
- **Common rules:** `email` must be non-blank and properly formatted in both cases.

If every constraint sits in the default group, you cannot fully express both contexts with the same DTO without changing rules. **Validation groups** are Jakarta Validation's mechanism for assigning each constraint to one or more groups and evaluating only the requested groups.

Spring adds `@Validated` to declare **which groups to run** at Spring validation trigger points. The annotation does not define new constraints. It forwards groups or validation hints to the appropriate validator.

```text
                 DEFINED ON THE DTO
       @Null(groups = Create.class) Long id
       @NotNull(groups = Update.class) Long id
       @NotBlank(groups = {Create.class, Update.class}) String name
       @Email String email                  [Default]
                           |
                           v
                    VALIDATION TRIGGER
          @Validated(Create.class)      -> Create only
          @Validated(Update.class)      -> Update only
          @Validated({Default.class, Create.class})
                                        -> Default and Create
                           |
                           v
             ConstraintViolation set / BindingResult
```

Declare groups on **constraints**, select groups at **execution**; the two steps must match for constraints to apply.

## 3. `@Valid` vs `@Validated`: Similarities and Differences

| Criterion | `jakarta.validation.Valid` | `org.springframework.validation.annotation.Validated` |
| --- | --- | --- |
| Origin | Jakarta Validation standard | Spring-specific |
| Core role | Marks cascaded validation; Spring also recognizes it to trigger validation on supported arguments | Marks validation and selects groups/hints in Spring integrations |
| Select groups directly? | Has no group selection attribute | Has `value()` taking `Class<?>[]` |
| Controller example | `@Valid @RequestBody Input input` | `@Validated(Create.class) @RequestBody Input input` |
| Nested objects | Typically uses `@Valid` on fields/properties to descend | Use `@Valid` for cascading; `@Validated` on fields is not the standard group conversion mechanism |
| Method validation in services | `@Valid` can contribute to parameter/return checks under enabled mechanisms | `@Validated` on the class is the marker for Spring AOP method validation |
| Use outside Spring | Yes, via Jakarta Validator | Not a standard Jakarta annotation |

Imports must be explicit:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.Default;
import org.springframework.validation.annotation.Validated;
```

`@Validated` accepts one or more group classes:

```java
@Validated(Create.class)
@Validated({Default.class, Create.class})
```

These two lines are **two separate usage examples**, not placed simultaneously on the same element. Spring treats `Class<?>[] value()` as validation hints, which are typically Jakarta Validation group interfaces. Do not confuse `@Validated` with `@Valid` merely because both appear before a DTO.

**Subtle point:** `@Valid` on a nested field is a cascade directive under the active validation group context; it does not mean "always validate all groups of the child bean". To switch groups when cascading, use `@ConvertGroup` per the specification.

## 4. Declaring Groups and Constraints

### 4.1. Marker interfaces

Groups are usually empty interfaces used as identifiers:

```java
public interface Create {}
public interface Update {}
```

DTOs do not need to implement these interfaces; group classes appear only in `groups` attributes and in validation calls. You can organize them inside a class containing nested interfaces (`Checks.Create`, `Checks.Update`) to avoid naming collisions.

### 4.2. DTO for Create and Update

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;

public class AccountCommand {
    @Null(groups = Create.class)
    @NotNull(groups = Update.class)
    private Long id;

    @NotBlank(groups = {Create.class, Update.class})
    private String username;

    @NotBlank
    @Email
    private String email;

    // constructors, getters, and setters omitted in this declaration example
}
```

This snippet illustrates metadata and is not a standalone runnable file.

- When validating **Create**: `id` must be null and `username` must not be blank.
- When validating **Update**: `id` must be non-null and `username` must not be blank.
- `email` has `@NotBlank` and `@Email` **without specifying `groups`**, so both constraints belong to `jakarta.validation.groups.Default`.
- A single constraint can belong to multiple groups via `groups = {A.class, B.class}`; there is no need to duplicate the same annotation across two fields.

### 4.3. Critical trap: `Default` is not automatically included with your chosen group

For `AccountCommand` above:

```java
validator.validate(command);                   // Default
validator.validate(command, Create.class);     // Create
validator.validate(command, Update.class);     // Update
validator.validate(command, Default.class, Create.class);
```

Each call has a **different** meaning. When you explicitly request `Create.class`, constraints belonging only to `Default` **do not run automatically** (unless group inheritance or an appropriate sequence is defined). Thus, to also validate email on creation, use:

```java
@Validated({Default.class, Create.class})
```

Similarly for update:

```java
@Validated({Default.class, Update.class})
```

You do not have to add `Default.class` to `groups` on every constraint. Another option is designing `Create` to extend `Default` or using a group sequence, though explicitly listing both groups at endpoints is often easier to read and test.

### 4.4. Prediction table

Suppose the DTO has:
- `id == null`
- `username == ""`
- `email == "invalid-email"`

| Validated Groups | Failing Constraints | Reason |
| --- | --- | --- |
| `Default` | `email` | `@Email` fails; `@NotBlank` on email still passes |
| `Create` | `username` | `id == null` satisfies `@Null`; Default email does not run |
| `Update` | `id`, `username` | `@NotNull` on id fails; blank username |
| `Default, Create` | `email`, `username` | Combines both constraint sets |
| `Default, Update` | `email`, `id`, `username` | Combines both constraint sets |

Remember `Validator.validate(...)` returns **`Set<ConstraintViolation<T>>`**; iteration order of a `Set` is not guaranteed. If presenting multiple errors in a fixed order, sort them when displaying or testing.

## 5. Standalone Java 17+ Example: Verifying Group Selection

To verify the group mechanism directly at the Jakarta Validation level without a web server, create the following Maven project. The example compiles on Java 17+ with Hibernate Validator 8 (an implementation of Jakarta Validation 3.0).

```text
group-check/
├── pom.xml
└── src/main/java/example/groups/GroupValidationCheck.java
```

`pom.xml` file:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>group-check</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.1.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/groups/GroupValidationCheck.java` file:

```java
package example.groups;

import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.groups.Default;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;

public final class GroupValidationCheck {

    public interface Create {}
    public interface Update {}

    public record Account(
            @Null(groups = Create.class)
            @NotNull(groups = Update.class)
            Long id,

            @NotBlank(groups = {Create.class, Update.class})
            String username,

            @NotBlank
            @Email
            String email) {}

    private static String failingFields(
            Validator validator, Account account, Class<?>... groups) {
        return validator.validate(account, groups).stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Account bad = new Account(null, "", "invalid-email");

            System.out.println("default="
                    + failingFields(validator, bad));
            System.out.println("create="
                    + failingFields(validator, bad, Create.class));
            System.out.println("update="
                    + failingFields(validator, bad, Update.class));
            System.out.println("create+default="
                    + failingFields(validator, bad,
                                    Create.class, Default.class));
            System.out.println("update+default="
                    + failingFields(validator, bad,
                                    Update.class, Default.class));

            Account validUpdate =
                    new Account(12L, "Lan", "lan@example.com");
            System.out.println("valid-update-count="
                    + validator.validate(
                            validUpdate, Update.class, Default.class).size());
        }
    }
}
```

Run:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.groups.GroupValidationCheck
```

**Stdout lines produced by the program** (excluding Maven/provider logs):

```text
default=email
create=username
update=id,username
create+default=email,username
update+default=email,id,username
valid-update-count=0
```

**Why are these results exact?**

- With `Default`, only the two email annotations are evaluated; email is non-blank yet fails `@Email`.
- With `Create`, `id == null` satisfies `@Null`; `username == ""` fails `@NotBlank`.
- With `Update`, null id fails `@NotNull` and blank username fails `@NotBlank`.
- When requesting multiple groups, the violation set corresponds to those constraint sets; sorting field names gives deterministic output order.
- A valid `Account` for update has a positive/non-null id, valid username, and valid email; no constraints fail.
- `try (ValidatorFactory ...)` closes the factory after use; in a Spring application, the factory is typically a framework-managed bean.

This is a **pure Jakarta Validation** program, not yet using Spring's `@Validated`. It shows why Spring must forward the exact group classes to the provider.

## 6. `@Validated` in Spring MVC: Selecting Groups for HTTP Requests

Spring MVC normally triggers Jakarta Validation after constructing the DTO from the request. One endpoint method can use a DTO with the Create group, while another uses the same DTO with the Update group.

### 6.1. Runnable Spring Boot 3 / Java 17 Example

The example requires a Spring Boot 3.x project with `spring-boot-starter-web` and `spring-boot-starter-validation`, plus Java 17+. The code below is a single-file complete application. You can use an existing Boot Maven project or use the following dependency configuration:

```xml
<!-- Dependencies in the Spring Boot project's pom.xml,
     with versions managed by the Spring Boot parent/BOM -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

The XML snippet is only a **dependency fragment** (not a standalone pom). Place the Java code in `src/main/java/example/groupweb/GroupWebApplication.java`:

```java
package example.groupweb;

import java.util.Map;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.groups.Default;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class GroupWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(GroupWebApplication.class, args);
    }

    public interface Create {}
    public interface Update {}

    public record AccountRequest(
            @Null(groups = Create.class)
            @NotNull(groups = Update.class)
            Long id,

            @NotBlank(groups = {Create.class, Update.class})
            String username,

            @NotBlank
            @Email
            String email) {}

    @RestController
    @RequestMapping("/accounts")
    public static class AccountController {

        @PostMapping
        public Map<String, String> create(
                @Validated({Default.class, Create.class})
                @RequestBody AccountRequest request) {
            return Map.of("action", "created",
                          "username", request.username());
        }

        @PutMapping
        public Map<String, String> update(
                @Validated({Default.class, Update.class})
                @RequestBody AccountRequest request) {
            return Map.of("action", "updated",
                          "username", request.username());
        }
    }
}
```

Run the application using your build tool, e.g.:

```bash
./mvnw spring-boot:run
```

or:

```bash
./gradlew bootRun
```

These commands apply when the project has the corresponding Maven/Gradle wrapper; they cannot run from a directory containing only the Java file and dependency fragment.

Once the server is running on `localhost:8080`:

```bash
curl -i -X POST http://localhost:8080/accounts -H "Content-Type: application/json" -d '{"id":null,"username":"Lan","email":"lan@example.com"}'
curl -i -X PUT http://localhost:8080/accounts -H "Content-Type: application/json" -d '{"id":12,"username":"Lan","email":"lan@example.com"}'
```

Without security filters or special HTTP configuration, both valid requests return **HTTP 200**. The JSON body contains `action`/`username` keys; key ordering is not guaranteed.

Try invalid requests:

```bash
curl -i -X POST http://localhost:8080/accounts -H "Content-Type: application/json" -d '{"id":9,"username":"Lan","email":"lan@example.com"}'
curl -i -X PUT http://localhost:8080/accounts -H "Content-Type: application/json" -d '{"id":null,"username":"Lan","email":"lan@example.com"}'
curl -i -X POST http://localhost:8080/accounts -H "Content-Type: application/json" -d '{"id":null,"username":"Lan","email":"bad-email"}'
```

With standard Spring MVC configuration, they are rejected with **HTTP 400**: violating `@Null` Create, `@NotNull` Update, and `@Email` Default respectively. Requests are rejected before controller logic executes. The error payload depends on Spring Boot, exception handlers, and Problem Details configuration, so **do not assume one fixed error JSON**.

**Notable point:** This example places `@Validated` directly on **each endpoint's DTO parameter**, because the two endpoints select different groups. Do not put `@Validated(Create.class)` on the entire controller and expect the Update endpoint to switch automatically to Update.

### 6.2. Why does `@RequestBody` still need a provider?

`@RequestBody` is deserialized from JSON into a DTO by `HttpMessageConverter` (usually Jackson). Spring then invokes the validator to evaluate constraints of the selected groups. Without `spring-boot-starter-validation` or a compatible Bean Validation provider, annotations may not execute as expected.

In Spring Framework 6+ / Boot 3+, use the `jakarta.validation` package. `javax.validation` is the namespace of previous generations; verify dependencies and imports when upgrading.

### 6.3. `@ModelAttribute` and `BindingResult`

For form requests, consider this **illustrative controller method snippet**:

```java
@PostMapping("/account-form")
public String submit(
        @Validated({Default.class, Create.class})
        @ModelAttribute AccountForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "invalid-form";
    }
    return "accepted";
}
```

This snippet requires `AccountForm` and imports defined in the application; it is not a standalone Java program. `BindingResult` must appear **immediately after the associated model parameter** so the controller can handle both data binding errors and validation errors for that object. Without `BindingResult`, validation failure normally causes Spring MVC to throw `MethodArgumentNotValidException`.

When form data conversion fails prior to validation (e.g., a string cannot be parsed into a number), that is a **binding error**, which can still appear in `BindingResult`. Do not assume every form error comes from a constraint group.

## 7. Placing `@Validated` on Services: Method Validation via Spring AOP

Beyond validating a DTO at a controller boundary, Spring also supports validating **method parameters and return values** on Spring beans.

Service example, assuming `Update` and validation dependencies already exist:

```java
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated(Update.class)
public class AccountService {

    public void changeStatus(
            @NotNull(groups = Update.class)
            @Positive(groups = Update.class)
            Long accountId) {
        // Business logic with valid accountId.
    }
}
```

This is an **illustrative code fragment**; it requires declaring the `Update` interface and wiring it into a Spring project. `@Validated(Update.class)` at the **class** level acts both as a marker for Spring's method validation infrastructure and selects Update as the default group for methods in that bean. When `MethodValidationPostProcessor` and a provider are configured, calling `accountService.changeStatus(null)` **through the Spring proxy** can be rejected due to `@NotNull`.

Mechanism:

```text
Caller -> Spring proxy / MethodValidationInterceptor
       -> determine method + groups
       -> Jakarta Validator / ExecutableValidator
       -> violations? report error
       -> no errors? invoke implementation
```

Limits to keep in mind:

- Must be invoked **through the Spring-managed proxy**. Calling `this.changeStatus(...)` inside the same bean normally goes directly to the target object and can bypass AOP validation; calling `new AccountService()` also bypasses the Spring proxy.
- Requires a Bean Validation provider and `MethodValidationPostProcessor`/matching auto-configuration. In Spring Boot with the validation starter, auto-configuration normally enables method validation for eligible beans; in plain Spring Framework you must check configuration.
- By default, Spring AOP method validation can throw `jakarta.validation.ConstraintViolationException`. Enabling `MethodValidationPostProcessor#setAdaptConstraintViolations(true)` allows Spring to switch to `org.springframework.validation.method.MethodValidationException`.
- A class-level annotation alone does not cause every plain method to be validated automatically: appropriate constraints or cascades must be on parameters/return values.
- `@Validated` can declare groups at method and class levels; in complex designs, verify how the interceptor selects groups and proxies via real tests rather than assuming annotations are automatically "merged".

If one method needs to run a different group from the class-level default, place the appropriate group where the framework supports it, or split service contracts by context to avoid confusing conflicts.

## 8. Spring MVC 6.1+: Distinguishing Argument Validation and Method Validation

Spring MVC currently has **two validation execution paths** that are easy to confuse:

| Scenario | Typical Execution Path | Common Error Type |
| --- | --- | --- |
| `@Validated(Create.class) @RequestBody Dto` with no direct method constraints | Validate DTO as a **method argument** | `MethodArgumentNotValidException` |
| `@Valid/@Validated @ModelAttribute Dto, BindingResult` | Validate/bind DTO, pass errors to `BindingResult` for controller inspection | Controller can respond directly |
| `@RequestParam @Min(1) int page` (constraint directly on method parameter, Spring MVC 6.1+) | MVC **built-in method validation** | `HandlerMethodValidationException` |
| `@Validated` service bean with AOP proxy | **Spring AOP method validation** | `ConstraintViolationException` (default), or `MethodValidationException` when configured |

**Spring MVC 6.1+ rule to remember:** A Jakarta constraint directly on a handler parameter or return value can route the entire handler through **method validation**; this path includes nested constraints marked with `@Valid` and normally replaces separate per-argument validation for `@RequestBody`/model attributes. Consequently, the exception may change from `MethodArgumentNotValidException` to `HandlerMethodValidationException`.

**For controllers that already have class-level `@Validated`:** Spring may apply **AOP proxy method validation**. Spring documentation recommends removing class-level `@Validated` from controllers when you want to leverage built-in MVC method validation (introduced in Spring Framework 6.1). You can still use `@Validated(Group.class)` **on DTO parameters** to select groups.

For instance:

```java
@GetMapping("/page")
public String page(@RequestParam @Min(1) int page) {
    return "page=" + page;
}
```

This is a **method fragment**. Because `@Min` sits directly on the parameter, Spring MVC 6.1+ built-in method validation can handle it. Do not infer that `@Validated` must be placed on every controller; it depends on constraint types and integration points.

## 9. Group Inheritance and Modeling Groups

One group can extend another group:

```java
import jakarta.validation.groups.Default;

public interface Create extends Default {}
public interface Update extends Default {}
```

With this model, requesting `Create.class` or `Update.class` also evaluates constraints belonging to `Default` through **group inheritance**. This is an alternative to writing `@Validated({Default.class, Create.class})` on every endpoint.

Before changing your design, understand the impact: inheritance causes the default group to always accompany the child group everywhere that group is used, including when validating services or nested objects. If each endpoint needs explicit control over shared groups, explicit declarations are often easier to trace.

Groups can also represent `Draft`, `Publish`, `Payment`, etc.; name them to describe **validation contexts**, not as security permissions. Groups do not replace authentication/authorization; a DTO passing an Admin group does not prove the caller has Admin privileges.

## 10. `@GroupSequence`: When Evaluation Order Matters

By default, when multiple groups are requested together, Jakarta Validation **does not guarantee evaluation order**. If expensive or complex constraints should run only after basic constraints pass, define a group sequence:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

interface AdvancedChecks {}

@GroupSequence({Default.class, AdvancedChecks.class})
interface CompleteChecks {}
```

Usage:

```java
validator.validate(command, CompleteChecks.class);
```

Or in Spring:

```java
@Validated(CompleteChecks.class)
```

When validating a sequence, the provider runs `Default` first. If there are violations in that group, **`AdvancedChecks` is skipped**; only if it passes does the next group run. This differs from requesting `@Validated({Default.class, AdvancedChecks.class})`: a list of multiple groups **has no guaranteed order**.

Notes:
- A group sequence must be defined consistently with no cycles.
- Avoid putting `@GroupSequence` on a class to **redefine Default** while also using sequence interfaces without understanding the difference. When redefining Default on a class, the sequence must include the class itself per specification; the example above defines only a **sequence interface**.
- Do not turn every business workflow into layered groups; data-dependent checks can be clearer in the service layer.

## 11. Cascading Groups into Nested Beans: `@Valid` and `@ConvertGroup`

Suppose an order DTO must validate the shipping address under a separate group. `@Valid` instructs **descending into the object**, while `@ConvertGroup` changes the group passed into that association:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.constraints.NotBlank;

interface OrderCreate {}
interface ShippingChecks {}

class ShippingAddress {
    @NotBlank(groups = ShippingChecks.class)
    private String city;
}

class Checkout {
    @Valid
    @ConvertGroup(from = OrderCreate.class, to = ShippingChecks.class)
    private ShippingAddress shippingAddress;
}
```

The classes above are an **illustrative model**, not a standalone runnable program. When validating `Checkout` under `OrderCreate.class`, the provider cascades to `ShippingAddress` using the `ShippingChecks.class` group because the association declares that group conversion. Without group conversion and with `ShippingAddress.city` belonging only to `ShippingChecks`, the `OrderCreate` group would not trigger it automatically.

`@ConvertGroup` is a **Jakarta Validation** mechanism, distinct from `@Validated` on controllers. Use it only when group differences between parent and child are intentional; otherwise plain `@Valid` usually suffices.

## 12. Choosing Groups by Business Needs: Two Design Approaches

### Approach A: One DTO with explicit groups

```java
public record UserInput(
    @Null(groups = Create.class)
    @NotNull(groups = Update.class) Long id,
    @NotBlank(groups = {Create.class, Update.class}) String name
) {}
```

Suitable when properties are truly identical and only a few constraints differ by operation. When using this approach, test all group combinations thoroughly and agree on a shared convention for `Default`.

### Approach B: Separate DTOs per endpoint

```java
public record CreateUserRequest(@NotBlank String name) {}
public record UpdateUserRequest(@NotNull Long id, @NotBlank String name) {}
```

Suitable when the data shapes of Create and Update differ substantially, such as Update supporting PATCH with many optional fields or Create having no id at all. Keeping constraints in `Default` on separate DTOs is usually simpler.

**How to choose:** Use groups when reusing **one nearly identical input model**. If differences in data, field editability, optionality, or API semantics are significant, splitting DTOs is usually clearer. Either way, never use validation groups as protection against mass assignment; control bindable fields and edit permissions at the proper layer.

## 13. Common Mistakes and How to Self-Check

1. **Writing only `@Validated(Create.class)` and assuming constraints without `groups` also run.** They belong to `Default`. Add `Default.class` to the requested set or design explicit inheritance/sequences.
2. **Adding `groups=...` in a DTO without triggering validation.** Constraint annotations do not run on constructor/setter calls; you need `Validator`, Spring MVC, method validation, or matching integration.
3. **Thinking `@Valid` selects a specific group.** `@Valid` has no group attribute. Use `@Validated` at the Spring validation trigger point.
4. **Forgetting `@Valid` when a model has child objects.** Constraints on child beans normally do not run without cascading.
5. **Using `@Validated` on a nested field to switch groups.** Use `@Valid` paired with `@ConvertGroup` per Jakarta standard when switching groups during cascade.
6. **Expecting the group list in `@Validated({A.class, B.class})` to dictate execution order.** If ordering is needed, use `@GroupSequence`.
7. **Putting `@Validated` on a controller class without understanding MVC 6.1+ method validation.** This can trigger AOP instead of built-in handling; check annotations and exception types.
8. **Adding `@Validated` to a service class and calling via `this.method()`.** Self-invocation usually bypasses the proxy, so validation may not occur.
9. **Having only `spring-boot-starter-web` and assuming a Bean Validation provider is present.** Check for `spring-boot-starter-validation` or equivalent configuration.
10. **Catching only `MethodArgumentNotValidException` and ignoring `HandlerMethodValidationException`.** Handle errors appropriately for both mechanisms if handlers have direct constraints.
11. **Assuming `@NotBlank` in Default does not matter on Update.** If Update requests omit Default, shared requiredness rules may be skipped.
12. **Using groups as role-based access control.** Passing constraints does not prove authorization to perform an operation.
13. **Testing by comparing `Set<ConstraintViolation>` order.** Sort fields/codes before asserting content; do not assume iteration order.
14. **Confusing string-to-number conversion errors with `@Min`/`@NotNull` errors.** Data binding/JSON deserialization can fail before validation runs.
15. **Putting `groups` on annotations that do not support `groups`.** Verify it is a Jakarta Constraint with a `groups` attribute, not just any annotation.

## 14. Project Adoption Checklist

Before writing an endpoint that uses `@Validated`, answer:

- Which groups are constraints declared with? Which ones belong to `Default`?
- Which groups does this endpoint need to check? Are shared required constraints omitted?
- Are there child objects needing `@Valid` and group conversion?
- Is the trigger point a request body, form, service method, or direct `Validator` call?
- Is a real validation provider on the classpath and configured by the framework?
- Does the controller have direct constraints on method parameters that change the method validation path?
- Are `MethodArgumentNotValidException`, `HandlerMethodValidationException`, `BindingResult`, or AOP `ConstraintViolationException` handled properly?
- Are Create/Update, null/blank data, valid data, Default-only, group inheritance, and a nested scenario tested as appropriate?

## 15. Self-Practice Questions

**Question 1.** `@NotBlank String name` has no `groups`. The controller uses `@Validated(Update.class)`. Is `name=""` guaranteed to produce an error?

**Answer:** No, if `Update` is an independent group without inheritance/sequence; `@NotBlank` belongs to Default. Include `Default.class` too if the goal is to validate name.

**Question 2.** `@NotNull(groups = Update.class) Long id` with `id=null`—does it fail when calling `@Validated(Create.class)`?

**Answer:** No, because the constraint belongs only to Update. That does not prove id is valid for Create; if id must be null on Create, declare `@Null(groups=Create.class)`.

**Question 3.** To validate Default first and then Advanced, is writing `@Validated({Default.class, Advanced.class})` enough?

**Answer:** No; use `@GroupSequence({Default.class, Advanced.class})` on a sequence interface and select that interface.

**Question 4.** Why does a service with `@Validated` still skip validation on an internal call `this.changeStatus(null)`?

**Answer:** Because self-invocation does not pass through the Spring AOP proxy, so the interceptor cannot intercept it.

**Question 5.** Spring MVC has `@RequestParam @Min(1) int page` and the same method has `@Valid @RequestBody`. When validation fails, is it always `MethodArgumentNotValidException`?

**Answer:** No. With built-in method validation from Spring MVC 6.1, a constraint directly on a method parameter can trigger `HandlerMethodValidationException` to handle both method constraints and nested constraints.

**Question 6.** A parent object validates under `Create`, while the child object has constraints only in `Shipping`. What needs to be done?

**Answer:** Put `@Valid` on the association and consider `@ConvertGroup(from=Create.class,to=Shipping.class)`; `@Valid` alone does not automatically switch to the Shipping group.

## 16. Summary

- **Constraint `groups`** assign rules to groups; Spring's **`@Validated`** selects groups when validation is triggered.
- `@Valid` belongs to Jakarta; `@Validated` belongs to Spring. `@Valid` is especially important for cascading; `@Validated` is for group selection in Spring integrations.
- When both common and operation-specific rules are needed, use `@Validated({Default.class, Create.class})` or explicitly designed inheritance/sequences.
- `@Validated` on a **controller DTO parameter** differs from `@Validated` on a **service class** enabling AOP method validation.
- Spring MVC 6.1+ has built-in method validation with distinct exception behavior; pay attention to class-level `@Validated` on controllers.
- Use group sequences for **ordering**, group conversions for **switching groups on cascade**, and test every context to avoid missing constraints.

### Technical References

- Spring Framework — `@Validated` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/annotation/Validated.html
- Spring Framework — Java Bean Validation and method validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework — Validation in Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring MVC — `@ModelAttribute` and `BindingResult`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Jakarta Validation 3.1 — Specification on groups, group sequences, and group conversion: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation 3.1 — `Default` group: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/groups/default
