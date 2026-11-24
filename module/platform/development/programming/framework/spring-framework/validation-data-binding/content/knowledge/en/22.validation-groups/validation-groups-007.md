# Stopping a Group Sequence When a Stage Has Violations: `@GroupSequence` in Bean Validation

## 1. The Problem: Staged Validation and Stopping at the Right Time

Suppose an API receives registration information. There are three logical validation tiers:

1. **Basic input**: name is not blank, email looks valid, password is not empty.
2. **Business rules**: password length meets requirements or properties satisfy logical relationships.
3. **Final confirmation**: the user accepted the terms or another completion condition.

If basic input is already invalid, continuing to business checks can produce noisy error messages, perform unnecessary work, or assume data that the earlier stage did not guarantee.

**Jakarta Bean Validation supports group sequences** via the `@GroupSequence` annotation. When a group in the sequence produces **at least one `ConstraintViolation`**, groups **following that group in the sequence are not evaluated**.

This lesson clearly distinguishes:
- Selecting **multiple validation groups** without requiring an order.
- Selecting **a group sequence** to validate sequentially and stop at the first failing stage.
- **Stopping between groups** vs. provider **fail-fast at the first violation**: two different mechanisms.
- How to verify with Java 17+, Hibernate Validator/JUnit, and Spring MVC `@Validated`.
- Exceptions to understand: the `Default` group, nested validation, group conversion, groups requested outside the sequence, and invalid sequence configurations.

Example context: Java 17+, `jakarta.validation.*` (Jakarta Bean Validation 3.x), Hibernate Validator 8, and Spring Framework 6+/Spring Boot 3.x. Older Spring Boot 2.x projects typically use `javax.validation.*`.

## 2. Core Rules of a Group Sequence

A sequence describes **the order of groups**, not directly the order of individual annotations:

```text
                  @GroupSequence({Basic, Policy, Confirm})
                                  |
                                  v
                        [Basic: validate]
                            /         \
                      Errors?         No errors
                         |                |
                         v                v
                   STOP SEQUENCE     [Policy: validate]
                                       /           \
                                  Errors?           No errors
                                     |                  |
                                     v                  v
                               STOP SEQUENCE       [Confirm: validate]
                                                        |
                                                      Finish
```

Mandatory rules:

- **Earlier stages run before later stages** in the order declared in `@GroupSequence`'s array.
- **If a stage has one or more violations**, all groups positioned after it **in the sequence** are skipped.
- **If the current stage has no violations**, the engine proceeds to the next stage.
- **If all stages pass**, the violation set returned by the validate call is empty.
- **Within a single stage**, the specification sets no fixed order for individual constraints, fields, or property getters; by default it does not stop at the first failing constraint.
- Each constraint can belong to multiple groups. Once a constraint has been evaluated for the same path within the same validation routine, it need not be evaluated again merely because a later group also contains it.

Remember the formula:

**Violation in group k → groups k+1, k+2, ... of the sequence are not evaluated.**

This behavior is guaranteed by Jakarta Bean Validation, not merely a Hibernate Validator optimization.

### 2.1. Three-Stage Example

| Stage | Group | Illustrative rules |
| --- | --- | --- |
| 1 | `InputChecks` | `@NotBlank username`, `@Email email`, `@NotBlank password` |
| 2 | `PolicyChecks` | `@Size(min = 8) password` |
| 3 | `ConsentChecks` | `@AssertTrue accepted` |

In a scenario with an invalid name, too-short password, and unaccepted terms: the sequence reports only errors from **`InputChecks`**. The short password and unaccepted terms still **exist in the data**, yet the provider was never asked to evaluate them in later stages.

That is why you should not describe a group sequence as "validated the whole object and kept only the first error". It genuinely **does not execute** the remaining groups in the sequence path.

## 3. How to Declare `@GroupSequence` on an Interface

Validation groups are represented by Java interfaces. Another interface annotated with `@GroupSequence` serves as **the name of the ordered pipeline**:

```java
import jakarta.validation.GroupSequence;

public final class Checks {
    private Checks() {}

    public interface Input {}
    public interface Policy {}
    public interface Consent {}

    @GroupSequence({
        Input.class,
        Policy.class,
        Consent.class
    })
    public interface Ordered {}
}
```

This is an illustrative fragment. When calling:

```java
validator.validate(request, Checks.Ordered.class);
```

the provider expands `Checks.Ordered` into the three declared stages in order: `Input` → `Policy` → `Consent`. You do **not** attach constraints to the `Ordered` group; you attach them to the component groups.

**Important definition note:** an interface carrying `@GroupSequence` should not directly extend other group interfaces and should not be used directly as a group on constraints. Avoid direct or indirect dependency cycles among sequences or group inheritance; cyclic configurations can throw `GroupDefinitionException` when used.

The array inside `@GroupSequence` is a **processing order**. That differs from the `groups` array on a constraint:

```java
@NotBlank(groups = {Checks.Input.class, Checks.Policy.class})
String field;
```

Here one constraint belongs to **two group sets**, with no rule saying `Input` must run before `Policy`. To enforce ordering and stopping, request validation of `Checks.Ordered.class`.

### 3.1. Do Not Pass Multiple Groups Expecting the Same Effect

These two calls are **not equivalent**:

```java
// No guaranteed order, does not stop after first failing group:
validator.validate(request,
        Checks.Input.class,
        Checks.Policy.class,
        Checks.Consent.class);

// Ordered and stops when the current group has errors:
validator.validate(request, Checks.Ordered.class);
```

In the first call, constraints in all three groups are requested, and evaluation order is not determined by parameter order. The second call establishes a sequential pipeline: if `Input` has errors, `Policy` and `Consent` will not run in the sequence.

Likewise, `@Validated({Input.class, Policy.class})` in Spring only selects multiple groups; it **does not turn** two groups into a sequence.

## 4. Stopping by Stage Is Not Per-Constraint Fail-Fast

These two mechanisms are the easiest to confuse.

| Property | Standard group sequence | Provider-style fail-fast (e.g., Hibernate Validator) |
| --- | --- | --- |
| Stopping scope | When a **group/stage** fails, later groups do not run | May stop after the **first violation** |
| Ordered across stages? | Yes: per `@GroupSequence` | Not guaranteed automatically; depends on configuration |
| Multiple errors in current stage? | Can return multiple errors | Usually returns only one error |
| Part of Jakarta Bean Validation standard? | **Yes** | Provider-specific configuration |
| When to use? | Multi-tier validation depending on foundational prerequisites | Wanting lower overhead / fewer errors returned |
| Proven by tests | Later stages produce no errors when earlier stage fails | Call returns the first error per configured provider |

For example, `Input` has `username=" "` and `email="wrong"`. With a group sequence and standard provider configuration, you can receive **two violations** in `Input`. The provider does not discard remaining errors after the first violation **within the same group**. If Hibernate Validator's fail-fast is enabled, the result may be only **one** violation, and you should not predict whether it is `username` or `email` without another ordering rule.

If an application needs to display **all basic errors**, while hiding advanced errors until basic input is valid, using a group sequence is better suited than enabling global fail-fast.

## 5. Where Does the `Default` Group Fit?

Jakarta has `jakarta.validation.groups.Default`. Constraints that do not declare `groups` belong to `Default`.

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.groups.Default;

class BasicProfile {
    @NotBlank
    String name; // Equivalent to groups = Default.class
}
```

If you call:

```java
validator.validate(profile);
```

the provider requests the `Default` group. However, if you call `validator.validate(profile, Checks.Ordered.class)` and the sequence **does not include `Default`**, constraints belonging only to `Default` may **not run**.

When you want default constraints checked before advanced groups, a sequence on an interface can declare:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

interface BusinessChecks {}
interface ApprovalChecks {}

@GroupSequence({
    Default.class,
    BusinessChecks.class,
    ApprovalChecks.class
})
interface FullCheck {}
```

If `Default` fails, `BusinessChecks` and `ApprovalChecks` do not run. If `Default` passes, the provider moves to `BusinessChecks` and then `ApprovalChecks` if needed.

**Do not confuse interface vs. class usage:**
- `@GroupSequence` on an **interface** defines a group sequence to invoke explicitly (e.g., `FullCheck.class`).
- `@GroupSequence` directly on a **bean class** means **redefining the `Default` group sequence for that class itself**, with different declaration rules; see section 10.

## 6. Input Matrix: Execution Stops Where Errors Occur

Consider a `Signup` object with two constraints in `Input`, one in `Policy`, and one in `Consent`:

| Scenario | `Input` | `Policy` | `Consent` | Result with `Ordered` |
| --- | --- | --- | --- | --- |
| Blank username; bad email; short password; not accepted | **Fail** | Not checked | Not checked | `username`, `email` errors |
| Valid `Input`; short password; not accepted | Pass | **Fail** | Not checked | `password` error |
| Valid `Input` and `password`; not accepted | Pass | Pass | **Fail** | `accepted` error |
| All fields valid | Pass | Pass | Pass | No errors |

Subsequent groups were **not checked**, not deemed "valid". When returning status from an API, prefer wording like "not evaluated" rather than "passed" to prevent misunderstandings.

### 6.1. One Group with Multiple Constraints: Understanding "Stage"

For example, `Input` contains `@NotBlank username`, `@NotBlank password`, and `@Email email`. All three belong to the same group with no defined order. If both `username` and `email` are invalid, the provider can report both; you cannot use `@GroupSequence` to force "`username` must be checked before `email`" while they reside **in the same group**.

To truly separate two steps, use two distinct groups (`RequiredFields` then `SyntaxFields`) and put them in the sequence. However, avoid over-splitting: creating too many tiny groups hurts maintainability and makes it hard to explain why the API only reports one error at a time.

### 6.2. Groups with Dependencies and Inheritance

A group can inherit from another group:

```java
interface SimpleChecks {}
interface ExtendedChecks extends SimpleChecks {}
```

When `ExtendedChecks` is requested, constraints in `SimpleChecks` can also apply per group inheritance rules. Therefore each **step** of a sequence can expand to multiple inherited constraints/groups. Base expectations on actual group definitions, not just counting interfaces listed in the annotation.

If sequence definitions combined with inheritance create an ordering cycle, the provider can throw `GroupDefinitionException`. Never define cyclic sequences or use a sequence interface like an ordinary group.

## 7. Complete Java 17+ Example with Maven and Hibernate Validator

This example runs **without Spring and without an HTTP server**. It proves step-by-step stopping in a group sequence and clearly contrasts it with requesting three independent groups.

Requires Java 17+, Maven, and a Jakarta Validation provider. Structure:

```text
ordered-validation-demo/
├── pom.xml
└── src/
    ├── main/java/example/StagedValidationDemo.java
    └── test/java/example/StagedValidationDemoTest.java
```

### 7.1. File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>ordered-validation-demo</artifactId>
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
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.0</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
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

Versions are pinned for reproducible execution; in a real Spring Boot application, use the BOM and `spring-boot-starter-validation`. A runtime provider is required; having only the API annotations is not enough to execute validation.

### 7.2. File `src/main/java/example/StagedValidationDemo.java`

```java
package example;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.GroupSequence;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public final class StagedValidationDemo {
    private StagedValidationDemo() {}

    public interface Input {}
    public interface Policy {}
    public interface Consent {}

    @GroupSequence({
        Input.class,
        Policy.class,
        Consent.class
    })
    public interface Ordered {}

    public record Signup(
            @NotBlank(groups = Input.class)
            String username,

            @Email(groups = Input.class)
            String email,

            @NotBlank(groups = Input.class)
            @Size(min = 8, groups = Policy.class)
            String password,

            @AssertTrue(groups = Consent.class)
            boolean accepted) {
    }

    public static Set<String> invalidFields(
            Validator validator,
            Signup signup,
            Class<?>... groups) {

        Set<ConstraintViolation<Signup>> violations =
                validator.validate(signup, groups);

        return violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(Collectors.toSet());
    }

    private static void show(
            String label,
            Validator validator,
            Signup signup,
            Class<?>... groups) {

        String fields = invalidFields(validator, signup, groups)
                .stream()
                .sorted()
                .collect(Collectors.joining(","));

        System.out.println(label + "="
                + (fields.isEmpty() ? "OK" : fields));
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Signup badInput = new Signup(
                    " ", "bad-email", "123", false);

            Signup badPolicy = new Signup(
                    "linh", "linh@example.com", "123", false);

            Signup badConsent = new Signup(
                    "linh", "linh@example.com", "strong123", false);

            Signup valid = new Signup(
                    "linh", "linh@example.com", "strong123", true);

            show("input-error", validator, badInput, Ordered.class);
            show("policy-error", validator, badPolicy, Ordered.class);
            show("consent-error", validator, badConsent, Ordered.class);
            show("all-valid", validator, valid, Ordered.class);

            // No sequence: three groups are requested independently.
            show("unordered", validator, badInput,
                    Input.class, Policy.class, Consent.class);

            // No constraint in the demo belongs to Default.
            show("default-only", validator, badInput);
        }
    }
}
```

Compile/test and run in the `ordered-validation-demo` directory:

```bash
mvn -q test
mvn -q exec:java -Dexec.mainClass=example.StagedValidationDemo
```

Stdout from `System.out.println` calls (excluding environment-dependent Maven/provider logs):

```text
input-error=email,username
policy-error=password
consent-error=accepted
all-valid=OK
unordered=accepted,email,password,username
default-only=OK
```

Why are these lines accurate?

- `input-error=email,username`: blank name and bad email fail `Input`. The short password and `accepted=false` in **later** stages are not evaluated in the group sequence.
- `policy-error=password`: `Input` passes; `Policy` catches `"123"` being under length 8. `Consent` continues to be skipped despite `accepted=false`.
- `consent-error=accepted`: `Input` and `Policy` both pass; `Consent` is the first stage with an error.
- `all-valid=OK`: all three groups pass.
- `unordered=accepted,email,password,username`: when passing `Input`, `Policy`, and `Consent` directly **without a sequence**, all four errors can appear.
- `default-only=OK`: the demo declares no constraints in `Default`; requesting `Default` alone does not automatically run constraints belonging to the other three groups.

`invalidFields` extracts property names into a `Set`; `show` sorts the names before printing for deterministic output. Do not infer constraint processing order from the alphabetical order printed on screen.

**Key point:** by making data in later groups invalid as well, yet having `Ordered` return errors only from the first failing group, the example proves sequence-stopping behavior—not merely hiding messages from later groups.

## 8. JUnit 5 Tests: Proving the Three Stopping Points

Create **`src/test/java/example/StagedValidationDemoTest.java`**:

```java
package example;

import java.util.Set;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StagedValidationDemoTest {

    private static Set<String> errors(
            Validator validator,
            StagedValidationDemo.Signup form,
            Class<?>... groups) {

        return StagedValidationDemo.invalidFields(
                validator, form, groups);
    }

    @Test
    void firstStageStopsBusinessAndConsentStages() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            var form = new StagedValidationDemo.Signup(
                    " ", "bad-email", "123", false);

            assertEquals(Set.of("username", "email"),
                    errors(validator, form,
                            StagedValidationDemo.Ordered.class));

            // Calling separate groups: errors from later groups still appear.
            assertEquals(
                    Set.of("username", "email",
                            "password", "accepted"),
                    errors(validator, form,
                            StagedValidationDemo.Input.class,
                            StagedValidationDemo.Policy.class,
                            StagedValidationDemo.Consent.class));
        }
    }

    @Test
    void secondStageStopsConsentStage() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            var form = new StagedValidationDemo.Signup(
                    "linh", "linh@example.com", "123", false);

            assertEquals(Set.of("password"),
                    errors(validator, form,
                            StagedValidationDemo.Ordered.class));
        }
    }

    @Test
    void thirdStageRunsOnlyAfterEarlierStagesPass() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            var needsConsent = new StagedValidationDemo.Signup(
                    "linh", "linh@example.com", "strong123", false);
            assertEquals(Set.of("accepted"),
                    errors(validator, needsConsent,
                            StagedValidationDemo.Ordered.class));

            var complete = new StagedValidationDemo.Signup(
                    "linh", "linh@example.com", "strong123", true);
            assertEquals(Set.of(),
                    errors(validator, complete,
                            StagedValidationDemo.Ordered.class));
        }
    }
}
```

The test suite uses `pom.xml` from section 7; JUnit Jupiter and Surefire are configured. Assertions check **sets of property paths** rather than relying on `Set<ConstraintViolation<?>>` order or English messages that vary by locale.

If you want to prove a later constraint **was literally never invoked**, rather than inferring only from the returned errors, you can add a custom `ConstraintValidator` counting `isValid(...)` invocations inside a test fixture. However, handle state and thread-safety carefully in such tests. For standard behavior, skipping later groups is guaranteed by the specification.

## 9. Spring MVC Integration: Using `@Validated` with a Sequence

In Spring MVC, a request can be validated using `@Validated` on the DTO parameter. To get ordering and stopping, pass the **sequence interface**, not three independent groups.

Assuming Spring Boot 3.x already has these dependencies:

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

This is a **fragment inside a Boot application's `pom.xml` that already has a parent/BOM**, not a standalone Maven file. The following Java files belong to the same application and a component-scanned package.

### 9.1. Groups and Sequence

File **`src/main/java/com/example/signup/SignupChecks.java`**:

```java
package com.example.signup;

import jakarta.validation.GroupSequence;

public final class SignupChecks {
    private SignupChecks() {}

    public interface Input {}
    public interface Policy {}
    public interface Consent {}

    @GroupSequence({
        Input.class,
        Policy.class,
        Consent.class
    })
    public interface Ordered {}
}
```

### 9.2. Request DTO with Constraints per Stage

File **`src/main/java/com/example/signup/SignupRequest.java`**:

```java
package com.example.signup;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record SignupRequest(
        @NotBlank(groups = SignupChecks.Input.class)
        String username,

        @Email(groups = SignupChecks.Input.class)
        String email,

        @NotBlank(groups = SignupChecks.Input.class)
        @Size(min = 8, groups = SignupChecks.Policy.class)
        String password,

        @AssertTrue(groups = SignupChecks.Consent.class)
        boolean accepted) {
}
```

In this example, `@Email` is used in the `Input` stage. `@Email` alone does not replace `@NotBlank` if email is required; in real systems, add `@NotBlank(groups = Input.class)` on `email` when email is mandatory. The sample payloads below always send an email string so the example focuses on sequence stopping.

### 9.3. Controller Selecting the Sequence

File **`src/main/java/com/example/signup/SignupController.java`**:

```java
package com.example.signup;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SignupController {

    @PostMapping("/signup")
    public ResponseEntity<Void> signup(
            @Validated(SignupChecks.Ordered.class)
            @RequestBody SignupRequest request) {

        // Reached only when all requested constraints pass.
        return ResponseEntity.noContent().build();
    }
}
```

The key marker is:

```java
@Validated(SignupChecks.Ordered.class)
@RequestBody SignupRequest request
```

Spring triggers Bean Validation with the `Ordered` group. The provider expands the sequence and stops at the first failing group. Replacing it with:

```java
@Validated({
    SignupChecks.Input.class,
    SignupChecks.Policy.class,
    SignupChecks.Consent.class
})
@RequestBody SignupRequest request
```

selects **three groups without stopping order**. Do not write `@Valid @RequestBody` expecting it to automatically use `SignupChecks.Ordered`: `@Valid` normally requests `Default`, unless `Default` is redefined otherwise.

### 9.4. Expected Responses

With the controller above and a configured Bean Validation provider:

| JSON request | First failing stage | Behavior |
| --- | --- | --- |
| `{"username":" ","email":"bad-email","password":"123","accepted":false}` | `Input` | Usually 400; `username` and `email` errors |
| `{"username":"linh","email":"linh@example.com","password":"123","accepted":false}` | `Policy` | Usually 400; `password` error; `Consent` not checked |
| `{"username":"linh","email":"linh@example.com","password":"strong123","accepted":false}` | `Consent` | Usually 400; `accepted` error |
| `{"username":"linh","email":"linh@example.com","password":"strong123","accepted":true}` | None | 204 No Content |

**Do not assume the error response JSON contains only one error.** If `Input` has two failing constraints, Spring can collect two `FieldError`s. The returned errors represent the **first failing stage**, not necessarily a single error message.

With `@RequestBody`, Jackson deserializes JSON **before** Bean Validation runs. If JSON cannot be parsed or a field has an incompatible type, `HttpMessageNotReadableException` can occur before the sequence is evaluated. When standard request-object validation fails with no `BindingResult`/`Errors` immediately following the argument, Spring MVC typically throws `MethodArgumentNotValidException` and returns 400. If a controller method needs **method validation** due to constraints directly on parameters or return values, Spring MVC 6.1+ may use `HandlerMethodValidationException`. Do not lump all exceptions into one type.

### 9.5. MockMvc Integration Test

File **`src/test/java/com/example/signup/SignupControllerTest.java`** in a Boot app with `spring-boot-starter-test`:

```java
package com.example.signup;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.validation.FieldError;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(SignupController.class)
class SignupControllerTest {

    @Autowired
    MockMvc mvc;

    private static Set<String> fields(
            MethodArgumentNotValidException ex) {
        return ex.getBindingResult().getFieldErrors().stream()
                .map(FieldError::getField)
                .collect(Collectors.toSet());
    }

    @Test
    void stopsAfterInputHasViolations() throws Exception {
        mvc.perform(post("/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "username": " ",
                      "email": "bad-email",
                      "password": "123",
                      "accepted": false
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                assertTrue(result.getResolvedException()
                        instanceof MethodArgumentNotValidException);
                var ex = (MethodArgumentNotValidException)
                        result.getResolvedException();
                assertEquals(Set.of("username", "email"), fields(ex));
            });
    }

    @Test
    void stopsAfterPolicyHasViolation() throws Exception {
        mvc.perform(post("/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "username": "linh",
                      "email": "linh@example.com",
                      "password": "123",
                      "accepted": false
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = (MethodArgumentNotValidException)
                        result.getResolvedException();
                assertEquals(Set.of("password"), fields(ex));
            });
    }

    @Test
    void reachesConsentAfterPriorGroupsPass() throws Exception {
        mvc.perform(post("/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "username": "linh",
                      "email": "linh@example.com",
                      "password": "strong123",
                      "accepted": false
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = (MethodArgumentNotValidException)
                        result.getResolvedException();
                assertEquals(Set.of("accepted"), fields(ex));
            });
    }

    @Test
    void acceptsRequestThatPassesEveryStage() throws Exception {
        mvc.perform(post("/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "username": "linh",
                      "email": "linh@example.com",
                      "password": "strong123",
                      "accepted": true
                    }
                    """))
            .andExpect(status().isNoContent());
    }
}
```

`@WebMvcTest` requires a Boot app with valid test configuration, a validation provider, and appropriate component scanning. When custom `@ControllerAdvice` or additional method validation is present, exception/status mapping may change; adapt tests to the actual contract.

Two key test points:
- In the failing `Input` case, there are **no** field errors for `password`/`accepted`, even though their values also fail later-stage constraints.
- In the failing `Policy` case, the `accepted` field error does not appear yet. If someone accidentally replaces `Ordered.class` with a plain list of groups, the test catches it because errors from later groups appear too.

## 10. Redefining the `Default` Group Sequence on a Bean Class

Sometimes you do not want the controller to know about an `Ordered` interface, and instead want **every `Default` validation of that class** to follow an ordered pipeline. Jakarta lets you attach `@GroupSequence` directly to a class.

Illustrative fragment:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

interface ExtendedChecks {}

@GroupSequence({
    Profile.class,
    ExtendedChecks.class
})
class Profile {

    @NotBlank
    String displayName;

    @Size(min = 20, groups = ExtendedChecks.class)
    String biography;
}
```

When calling `validator.validate(profile)` under `Default`:
1. `Default` constraints declared on `Profile` are evaluated via the `Profile.class` group.
2. If `displayName` fails, `ExtendedChecks` does not run.
3. If `Default` passes, the `biography` length constraint in `ExtendedChecks` is checked.

**Crucial special rule:** on a **class** redefining `Default`, the sequence **must contain that class itself** (e.g., `Profile.class`). Do not write `@GroupSequence({Default.class, ExtendedChecks.class})` directly on `Profile`, because that is invalid syntax for redefinition and can cause `GroupDefinitionException`. Conversely, on an **interface** defining an explicit sequence, `@GroupSequence({Default.class, ExtendedChecks.class})` is valid.

Redefining `Default` on a class takes effect **locally** for that class: it does not automatically apply that `Default` sequence to every child bean via `@Valid`. Test the object graph rather than assuming "the entire tree follows the parent's sequence".

### 10.1. Should Class-Level Redefinition Be Used Everywhere?

Not necessarily. The advantage is that every `Default` validation of the class follows a uniform pipeline. The drawback is that `Default` is no longer straightforward; readers must check class-level annotations to understand why some constraints did not run. For endpoints with clear contexts, defining a sequence on an interface and selecting it via `@Validated(Ordered.class)` is usually easier to understand.

If the sequence depends dynamically on bean state, Hibernate Validator offers the `@GroupSequenceProvider` extension to supply a dynamic default group sequence. This is a **provider-specific** feature, not a portable Jakarta standard API; use it only when genuinely needed and test against your active provider.

## 11. Stopping the Sequence When Validation Cascades to Child Beans

A stage does not consist solely of constraints on the root. When a field is annotated with `@Valid`, the provider can cascade into the child bean using the active requested group.

```java
import jakarta.validation.Valid;
import jakarta.validation.GroupSequence;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

interface Basic {}
interface Advanced {}

@GroupSequence({Basic.class, Advanced.class})
interface RegistrationFlow {}

class Address {
    @NotBlank(groups = Basic.class)
    String city;
}

class Registration {
    @Valid Address address;

    @Size(min = 8, groups = Advanced.class)
    String password;
}
```

If `address.city = " "` and `password = "123"`, calling:

```java
validator.validate(registration, RegistrationFlow.class);
```

hits an error in **`Basic` on `Address`**, so **`Advanced` on `Registration`** does not run in the sequence. In other words, the condition "`Basic` passes" can span the cascaded object graph, not only the root's own fields.

However:
- `@Valid` does not force a child bean to be non-null; `address=null` skips the cascade. Use `@NotNull(groups = Basic.class)` if presence is required.
- If `@Valid` is missing on `Registration.address`, `Address`'s `Basic` constraints are not evaluated along the path from `Registration`, causing the sequence to advance differently than expected.
- Each stage can contain multiple objects and multiple violations; the provider guarantees no evaluation order among properties within the same group.

### 11.1. `@ConvertGroup` and Ordering

Jakarta supports `@ConvertGroup` on a `@Valid` edge to map groups when entering a child bean. Sequences are **expanded into component groups before group conversion**, so do not assume `@ConvertGroup(from = RegistrationFlow.class, ...)` works like converting an entire sequence: `from` must match the expanded group at that step.

Example (fragment):

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

class Container {
    @Valid
    @ConvertGroup(from = Default.class, to = AddressChecks.class)
    Address address;
}

interface AddressChecks {}
```

This converts `Default` to `AddressChecks` when cascading across `address`; it does not change group ordering on the root, nor does it add new constraints to the child bean.

When combining sequences, inheritance, and conversion across multiple levels, write unit tests with deliberately invalid values in different groups to verify exactly which groups execute.

## 12. Important Exception: A Group Requested Both Inside and Outside a Sequence

This is a case that easily produces results different from "stop on first group error".

Suppose `Flow` consists of `Input` then `Policy`:

```java
@GroupSequence({Input.class, Policy.class})
interface Flow {}
```

Normally:

```java
validator.validate(request, Flow.class);
```

If `Input` fails, `Policy` is skipped **within `Flow`**. However, if you call:

```java
validator.validate(
        request,
        Flow.class,
        Policy.class);
```

`Policy` is simultaneously requested as **an independent group outside `Flow`**. In that case `Policy` constraints can still be evaluated even if `Input` fails. The specification does not promise that an independent group request will be suppressed by another sequence's stop rule.

**Practical rule:** if you want an unambiguous stopping pipeline, **pass only the group sequence as the validation input**, instead of requesting both the sequence and one or more component groups independently.

Similarly, when a group is requested multiple times via inheritance or sequences, providers apply rules to avoid checking the same constraint twice on the same path; do not infer execution counts simply from how many times a group name appears.

## 13. Why Should Group Sequences Not Replace Service Workflows?

Group sequences are useful when constraints are **synchronous checks over available data**. They do not replace true multi-step business workflows:

- They do not open transactions, persist data, lock records, or grant permissions.
- They do not turn Bean Validation into an ordered command/side-effect execution engine.
- They do not guarantee database/network failures turn into `ConstraintViolation`s handled as data errors.
- They carry no built-in contract for returning detailed "stage 2 pending" status unless your application builds that response.
- They are not an information-security boundary: even when some constraints are skipped, APIs must still avoid leaking sensitive data and enforce authorization separately.

Custom `ConstraintValidator`s should behave deterministically without side effects. If an "advanced" check queries external data or is resource-intensive, a group sequence reduces calls when basic stages fail, yet timing, data consistency, and retries remain the service/application layer's responsibility.

## 14. Thorough Testing: Preventing False Positives

A good test suite needs these cases:

| Case | Input | Assertion |
| --- | --- | --- |
| First group fails | Invalid `Input`, `Policy`, `Consent` | Only `Input` errors in the group sequence |
| Multiple errors in first group | Invalid `username` and `email` | Errors for both (when fail-fast is off) |
| First group passes, second fails | Short password | Only `Policy` error; `Consent` not evaluated |
| First two pass, third fails | `accepted=false` | Only `Consent` error |
| All groups pass | Valid data | Zero violations |
| Separate groups | Request `Input`, `Policy`, `Consent` individually | Errors from all three groups can appear |
| Validate `Default` only | Constraints only in custom groups | Custom groups do not run automatically |
| Sequence containing `Default` | Invalid `Default`, invalid `Advanced` | `Advanced` is skipped |
| Redefined `Default` on class | `@GroupSequence` includes class itself | `Default` uses the new order |
| Class default sequence missing class | Invalid configuration | Can throw `GroupDefinitionException` |
| Nested `@Valid` fails in stage 1 | Blank `Address.city` | Stops before later stage on root |
| Null nested bean | Missing `@NotNull` | Cascade can skip; test presence explicitly |
| Group requested outside sequence | `Flow` alongside `Policy` | Do not assume `Policy` is always skipped |
| Provider fail-fast | Multiple errors in same stage | May return only one violation; do not guess which field |
| Wrong JSON types | Body fails deserialization | Fails before Bean Validation; sequence never runs |
| Spring missing validation provider | Annotations only | Never conclude validation succeeded |

Assert **property paths, violation counts/groups present, HTTP status**, and acceptance criteria; do not assert full messages tied to a fixed locale. To verify actual internal execution order or custom constraint invocation counts, use instrumented test validators within controlled tests.

## 15. Common Mistakes and Fixes

1. **Confusing `@GroupSequence` with `groups = {A,B}`:** the `groups` array defines membership; `@GroupSequence` defines ordering and stopping.
2. **Passing `validator.validate(bean, A.class, B.class)` thinking A runs before B:** not guaranteed. Invoke the sequence interface.
3. **Thinking it stops at the very first constraint:** a group sequence stops **after a failing stage**, which can still report multiple errors within that stage.
4. **Using `@Valid` expecting the provider to pick `Ordered`:** `@Valid` validates `Default` by default at integration points; use `@Validated(Ordered.class)` or configure `Default` appropriately.
5. **Sequence omits `Default` despite many `Default` constraints:** those constraints may be skipped; add `Default` to the interface sequence when needed.
6. **Putting `@GroupSequence({Default.class, Advanced.class})` on a bean class:** when redefining `Default` on a class, it must contain **the class itself**, not `Default.class`.
7. **Creating cyclic group sequences:** can throw `GroupDefinitionException`. Review inheritance and nested sequences.
8. **Attaching constraints directly to a sequence interface:** attach them to component groups instead of using the sequence interface as a normal group.
9. **Requesting both `Flow` and a component group outside `Flow`:** `Flow`'s stop rule does not cancel the independent group request.
10. **Forgetting `@Valid` on child beans:** errors on nested objects go unchecked, letting the sequence advance despite invalid nested data.
11. **Misusing fail-fast instead of a group sequence:** can drop helpful errors from the same stage and gives no field-order guarantee.
12. **Confusing JSON binding exceptions with constraint violations:** deserialization can fail before the provider is called.
13. **Believing a group sequence performs authorization checks:** validation does not replace authorization.
14. **Putting side effects into stages:** validation should primarily check data, not write records or invoke state-changing workflows.
15. **Not testing group 2 failing:** testing only stage 1 failing does not prove stage progression and stopping at the next stage.
16. **Confusing class-level `Default` redefinition with tree-wide cascading:** a class's `Default` sequence is local; check propagation and conversion rules.
17. **Assuming one violation always equals one field:** custom class-level constraints and container element constraints have different property paths; inspect API metadata.
18. **Missing runtime provider or mismatched Jakarta/`javax` namespaces:** present annotations do not mean the engine executed.

## 16. Project Adoption Checklist

1. Split constraints into stages that genuinely have data dependencies, such as `Input` → `Policy` → `Consent`.
2. Create marker interfaces, then create **one sequence interface** with `@GroupSequence({A.class, B.class, C.class})`.
3. Put `groups = A.class`/`B.class`/`C.class` on the right constraints; avoid assigning wrong-context groups.
4. Decide whether `Default` is needed; if so, place it in the **interface sequence** at the appropriate position.
5. Trigger via `validator.validate(bean, Flow.class)` or `@Validated(Flow.class)` on request DTOs in Spring MVC.
6. Test invalid inputs at stages 1, 2, and 3 alongside invalid data in later stages to prove stopping rules.
7. Also test multiple errors **within the first stage**; do not confuse with provider fail-fast.
8. If using `@Valid` and group conversion, test the object graph, nulls, inheritance, and selected groups.
9. Avoid requesting component groups independently when you want sequence-based stopping.
10. Keep service workflow ordering, authorization, transactions, and side effects in appropriate business layers rather than forcing them into constraint sequences.
11. Assert on property paths and HTTP status; do not rely on `Set` order, message order, or locale.
12. Consult specification/provider docs when redefining `Default` on a class to avoid omitting the class itself from the sequence.

### Official References

- [Jakarta Bean Validation 3.0 Specification — Group sequence and Validation routine](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html).
- [Jakarta Bean Validation API 3.0 — @GroupSequence](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/GroupSequence.html).
- [Hibernate Validator 8 Reference Guide — Defining group sequences, redefining Default, fail fast](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/).
- [Spring Framework — Validation for @RequestMapping methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html).
- [Spring Framework — @RequestBody with @Validated](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html).
- [Spring Framework — Bean Validation integration](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html).
