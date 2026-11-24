# Class-Level and Method-Level Group Selection in Spring Validation

## 1. The Problem: One Bean Has Many Rules, Yet Each Operation Needs Different Groups

In Spring Framework, multiple validation rules can be attached to the same data type or to parameters/return values of the same service. However, the rules needed at **creation** time may differ from those at **update** time; even methods on the same service can require distinct constraint sets.

Jakarta Validation calls each set of constraints a **validation group**. Spring provides the `@Validated` annotation to select groups at Spring-managed invocation points. For **AOP-based method validation**, two positions are critical:

- **`@Validated(Create.class)` at the class level:** marks the bean as eligible for Spring's method-validation proxy and selects the default group for the bean's methods.
- **`@Validated(Update.class)` at the method level:** selects a specific group for that method, **overriding** the class-level selection for that call.

Conceptual example:

```java
@Service
@Validated(Create.class)              // AOP trigger point + default group
public class AccountService {

    public void create(
            @NotBlank(groups = Create.class) String name) {
        // ...
    }

    @Validated(Update.class)          // Overrides class-level group
    public void rename(
            @NotBlank(groups = Update.class) String name) {
        // ...
    }
}
```

The snippet above only illustrates annotation placement; a complete project with source code and tests follows later. Crucial requirement: **placing `@Validated` only on a method of an ordinary Spring service is not enough to create an AOP proxy**. With the default `MethodValidationPostProcessor` configuration, `@Validated` on the type (or an equivalent meta-annotation) is required for the bean to be selected for method validation.

This lesson clearly separates three things that are often mixed up:

1. **Declaring a group on a constraint:** `@NotBlank(groups = Create.class)` specifies which group the constraint belongs to.
2. **Selecting a group when validating:** `@Validated(Create.class)` or `validator.validate(bean, Create.class)` specifies which group(s) the validation pass runs.
3. **Activating the validation point:** a service proxy, an MVC argument resolver, or MVC's built-in method validation; group-selection annotations do not automatically ensure every Java call is validated.

Version scope: Java 17+, Jakarta Validation 3.x, Spring Framework 6.x / Spring Boot 3.x. Pay particular attention to the differences for controllers starting in Spring Framework **6.1**.

## 2. Foundation: Validation Groups Belong to Jakarta, @Validated Belongs to Spring

### 2.1. Declaring Groups with Interfaces

A group in Jakarta Validation is a `Class<?>`, most commonly a **marker interface** with no methods:

```java
public interface Create {}
public interface Update {}
```

These are two independent interfaces. By themselves, they perform no validation, hold no business logic, create no proxies, and do not determine which group Spring will use.

Attaching groups to constraints:

```java
@NotBlank(groups = Create.class)
private String password;

@NotBlank(groups = Update.class)
private String displayName;
```

When `Create.class` is selected, the first constraint is evaluated. When `Update.class` is selected, the second constraint is evaluated. A constraint can belong to multiple groups:

```java
@Size(min = 3, groups = {Create.class, Update.class})
private String username;
```

### 2.2. The Default Group Is an Actual Group, Not "All"

Constraints that do not declare `groups` belong to `jakarta.validation.groups.Default`:

```java
@NotNull                   // groups = Default.class
private String id;

@NotBlank(groups = Create.class)
private String password;
```

Calling `validator.validate(bean)` runs the `Default` group. Calling `validator.validate(bean, Create.class)` **does not automatically also run Default**. Likewise, `@Validated(Create.class)` in Spring does not implicitly evaluate all `Default` constraints.

If both groups are needed, specify both:

```java
@Validated({Default.class, Create.class})
```

where `Default` is imported from `jakarta.validation.groups.Default`. When overriding group selection on a method, list **all** desired groups again; method-level `@Validated` does not merge in groups declared on the class.

Another option when it matches business semantics is group inheritance:

```java
public interface Create extends Default {}
```

Selecting `Create` then includes constraints belonging to `Default` through **Jakarta Validation group inheritance**. Do this only if every `Create` case truly must check all `Default` rules; do not invent inheritance merely to avoid listing groups.

### 2.3. Groups and Group Sequences Are Not the Same

`@Validated({Default.class, Create.class})` selects both groups, yet **does not guarantee** that all `Default` errors are evaluated before `Create` or that the second group is skipped if the first has errors.

When **staged ordering** and stopping before the next stage on failure are mandatory, use Jakarta Validation's `@GroupSequence`. That is a distinct feature from class/method group selection. Do not rely on array element order in `@Validated` as a substitute for a group sequence.

## 3. How Spring Selects Groups at Class Level and Method Level

In **Spring-driven AOP method validation**, the standard rules are:

1. Spring identifies beans eligible for method validation via `@Validated` on the type and an active `MethodValidationPostProcessor`.
2. When a call goes through the proxy, the interceptor looks for `@Validated` on the invoked method.
3. If the method has `@Validated`, it uses the **method** annotation's `value()`, even if it is an empty array.
4. If absent on the method, it looks for `@Validated` on the type or other supported bean metadata.
5. If no group is explicitly selected, the provider uses `Default`.
6. The selected groups apply to constraints on **parameters**, and when the method returns, to constraints on the **return value**.

| Annotation placement | Selected group in AOP service | Meaning |
| --- | --- | --- |
| `@Validated(Create.class)` on class, no `@Validated` on method | `Create` | Uses class-level selection |
| `@Validated(Create.class)` on class, `@Validated(Update.class)` on method | `Update` | Method overrides class |
| `@Validated(Create.class)` on class, `@Validated` on method | `Default` | Method overrides with default selection |
| `@Validated({Default.class, Create.class})` on class, no annotation on method | `Default` and `Create` | Explicitly selects both groups |
| Only `@Validated(Update.class)` on service method, no type-level `@Validated` | Not eligible for AOP | Method annotation alone does not create a pointcut/proxy |
| No `@Validated` on service created manually with `new` | No automatic AOP | Plain Java calls are not intercepted by Spring |

**"Override" here means overriding runtime group selection, not modifying `groups` declared on constraints.** If a constraint belongs to `Create`, it still belongs to `Create` even when the method runs with `Update`; that validation pass simply does not select it.

**Class-level group selection is not the same as a class-level constraint:** `@Validated` on a service selects groups/enables method validation. A custom `@Constraint` on a DTO class validates the state of that DTO. Both phrases say "class-level," yet they are different mechanisms.

## 4. Runnable Spring Boot Example: Class Default, Method Override, and Default

We build a Spring service with three operations:

- `create` uses the class's default `Create` group;
- `rename` uses the `Update` group overridden on the method;
- `check` uses `@Validated` with no value to switch back to `Default`.

Tests invoke the **proxied Spring bean** and observe `ConstraintViolationException`. No HTTP is used in this section to avoid mixing Spring MVC mechanisms with AOP method validation.

### 4.1. Project Structure

```text
validation-groups-demo/
├── build.gradle
├── settings.gradle
└── src/
    ├── main/java/com/example/groups/
    │   ├── GroupDemoApplication.java
    │   ├── Create.java
    │   ├── Update.java
    │   └── AccountService.java
    └── test/java/com/example/groups/
        └── AccountServiceValidationTest.java
```

Install Java 17 or higher and use the project's Gradle wrapper. `settings.gradle`:

```groovy
rootProject.name = 'validation-groups-demo'
```

`build.gradle` (specific illustrative versions from the Spring Boot 3 line):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-validation` provides the Jakarta Validation provider; `spring-boot-starter-aop` makes the proxy dependency explicit. With typical Spring Boot 3 auto-configuration, `MethodValidationPostProcessor` is registered when a valid Bean Validation provider is present. In a plain Spring Framework application without Boot, configure this processor explicitly.

### 4.2. Application Bootstrap

File `src/main/java/com/example/groups/GroupDemoApplication.java`:

```java
package com.example.groups;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GroupDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(GroupDemoApplication.class, args);
    }
}
```

Two marker interfaces:

File `src/main/java/com/example/groups/Create.java`:

```java
package com.example.groups;

public interface Create {}
```

File `src/main/java/com/example/groups/Update.java`:

```java
package com.example.groups;

public interface Update {}
```

Jakarta Validation groups **do not require** any special annotation on the interface. Referencing them in `@NotBlank(groups = ...)` and `@Validated(...)` is enough.

### 4.3. Service with Two-Level Group Selection

File `src/main/java/com/example/groups/AccountService.java`:

```java
package com.example.groups;

import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated(Create.class)
public class AccountService {

    // No @Validated on method => uses Create from class.
    public String create(
            @NotBlank(groups = Create.class) String username) {
        return "created:" + username;
    }

    // Update group replaces Create for this method.
    @Validated(Update.class)
    public String rename(
            @NotBlank(groups = Update.class) String newName) {
        return "renamed:" + newName;
    }

    // Empty group array => selects the Default group.
    @Validated
    public String check(
            @NotBlank String token) {
        return "checked:" + token;
    }

    // @NotBlank constraint on Default does NOT run during a call
    // using the class-level Create group.
    public String defaultOnly(
            @NotBlank String description) {
        return "description:" + description;
    }
}
```

Key observations:

- `create(" ")`: `@NotBlank(groups=Create.class)` fails.
- `rename(" ")`: method selects `Update`, so `@NotBlank(groups=Update.class)` fails.
- `check(" ")`: `@Validated` with no arguments selects `Default`, so `@NotBlank` fails.
- `defaultOnly(" ")`: the method inherits `Create` from the class, whereas `@NotBlank` without `groups` belongs to `Default`; this constraint is **not selected**. The example intentionally highlights a design trap and does not recommend skipping validation in real applications.
- When input is valid, the method completes and returns its normal string. When the interceptor finds violations, the method body does not run.

Do not put `@Validated(Create.class)` on a class and assume all ungrouped `@NotNull` or `@NotBlank` annotations run automatically. Explicitly specify `Default` or use group inheritance if that is what you want.

### 4.4. Unit/Integration Tests Through the Spring Proxy

File `src/test/java/com/example/groups/AccountServiceValidationTest.java`:

```java
package com.example.groups;

import jakarta.validation.ConstraintViolationException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class AccountServiceValidationTest {

    @Autowired
    private AccountService service;

    @Test
    void classLevelCreateGroupAppliesByDefault() {
        ConstraintViolationException ex = assertThrows(
                ConstraintViolationException.class,
                () -> service.create(" ")
        );
        assertEquals(1, ex.getConstraintViolations().size());
        assertEquals("created:alice", service.create("alice"));
    }

    @Test
    void methodLevelUpdateOverridesCreate() {
        ConstraintViolationException ex = assertThrows(
                ConstraintViolationException.class,
                () -> service.rename(" ")
        );
        assertEquals(1, ex.getConstraintViolations().size());
        assertEquals("renamed:anna", service.rename("anna"));
    }

    @Test
    void methodWithEmptyValidatedUsesDefault() {
        ConstraintViolationException ex = assertThrows(
                ConstraintViolationException.class,
                () -> service.check(" ")
        );
        assertEquals(1, ex.getConstraintViolations().size());
        assertEquals("checked:ok", service.check("ok"));
    }

    @Test
    void defaultConstraintIsNotImplicitlyAddedToCreateGroup() {
        assertEquals(
                "description: ",
                service.defaultOnly(" ")
        );
    }
}
```

Run on POSIX shells:

```bash
./gradlew test
```

On Windows:

```powershell
.\gradlew.bat test
```

**Expected:** all four tests pass when standard Boot/AOP configuration is active. The first three tests use `assertThrows` because Spring AOP method validation throws `jakarta.validation.ConstraintViolationException` by default on invalid parameters. The fourth test confirms `Default` is **not implicitly added** to the `Create` group. Do not assert violation ordering inside `Set<ConstraintViolation<?>>`; ordering is not guaranteed.

In projects enabling `MethodValidationPostProcessor#setAdaptConstraintViolations(true)`, AOP errors may be reported as `org.springframework.validation.method.MethodValidationException` instead of `ConstraintViolationException`. Adjust tests and handlers to match the actual application configuration rather than assuming every Spring project throws the same exception.

### 4.5. Why Must Tests Call the Spring-Managed Bean?

If you manually write:

```java
AccountService service = new AccountService();
service.create(" ");
```

then **there is no Spring AOP proxy**: you cannot expect `@Validated` to run on its own. This merely creates a plain Java object; it can return `"created: "` because the body simply concatenates strings.

Similarly, a method inside the service calling `this.rename(...)` normally **bypasses the proxy** in standard Spring AOP, so it does not trigger interception for `rename` via that internal call. For method validation to run, invoke through the Spring bean proxy at the proper boundary; do not rely on self-invocation to guard data.

## 5. When to Use @Validated on a Class, a Method, or a Parameter

The same `@Validated` annotation can appear in three places (TYPE, METHOD, PARAMETER), yet its **semantics depend on the integration point**.

### 5.1. Service: TYPE Selects Default, METHOD Overrides

The `AccountService` example in section 4 illustrates the familiar pattern with `MethodValidationPostProcessor`:

```java
@Validated(Create.class)
@Service
class AccountService {

    public void create(
            @NotBlank(groups = Create.class) String name) {}

    @Validated(Update.class)
    public void update(
            @NotBlank(groups = Update.class) String name) {}
}
```

This is structural illustrative code, not a standalone Java program. Method-level `@Validated(Update.class)` selects the group for the method. It does **not** configure checking only one specific parameter; it affects validating the method's constraints handled by the interceptor, including parameters and return value.

### 5.2. Controller @RequestBody: PARAMETER Selects the Group for the Object

In Spring MVC, `@Validated(Create.class)` directly on `@RequestBody` or `@ModelAttribute` is a **validation hint for the bound object**:

```java
@PostMapping("/accounts")
public ResponseEntity<Void> create(
        @Validated(Create.class) @RequestBody AccountRequest request) {
    return ResponseEntity.noContent().build();
}
```

This is an **illustrative controller method**; `AccountRequest` is assumed to have constraints assigned to group `Create`. With a command object parameter and no direct constraints on other parameters requiring method validation, Spring MVC validates the object under `Create` and can throw `MethodArgumentNotValidException` (unless a `BindingResult` immediately follows).

For an update endpoint:

```java
@PutMapping("/accounts/{id}")
public ResponseEntity<Void> update(
        @PathVariable long id,
        @Validated(Update.class) @RequestBody AccountRequest request) {
    return ResponseEntity.noContent().build();
}
```

This is also a controller method snippet, not a standalone program. Each body parameter can select a different group at binding time. **You do not need `@Validated(Create.class)` on the controller class merely to select a group for `@RequestBody`.**

Comparison:

| Syntax | Location | Primary meaning |
| --- | --- | --- |
| `@Valid @RequestBody Dto dto` | Controller parameter | Validates DTO under Default (in typical context) |
| `@Validated(Create.class) @RequestBody Dto dto` | Controller parameter | Validates DTO under Create when MVC binds it |
| `@Validated(Create.class)` on service class | Type | Enables AOP pointcut and picks default group for method validation |
| `@Validated(Update.class)` on service method | Method | Overrides group when the method is proxy-validated |
| `@Validated(Create.class)` on controller class | Type | Can route controller to AOP method validation; consider Spring MVC 6.1+ |

`@Valid` is a Jakarta annotation for cascaded validation; it takes no group parameter. `@Validated` is a Spring annotation for validation hints and method validation group selection. Using both on the same parameter unnecessarily is redundant and obscures group-selection intent.

### 5.3. Spring MVC 6.1+: Built-In Method Validation Differs from AOP

**Starting in Spring Framework 6.1, Spring MVC supports built-in method validation for handler methods**, without requiring an AOP proxy. It activates when there are direct constraints on parameters or return values, for example:

```java
@GetMapping("/quantities")
public String quantities(
        @RequestParam @Min(1) int quantity) {
    return "quantity=" + quantity;
}
```

This is an illustrative controller method (with matching `@GetMapping`, `@RequestParam`, `@Min` imports). `@Min(1)` is a direct constraint on the parameter: MVC uses built-in method validation and can throw `HandlerMethodValidationException`. If only `@Valid @RequestBody` is on a command object (with no direct constraints requiring method validation), the usual path is argument resolver validation throwing `MethodArgumentNotValidException`.

**Important class-level warning:** When a controller has `@Validated` at TYPE level, Spring MVC may route method validation through an **AOP proxy**. Spring documentation advises **removing class-level `@Validated` on controllers** if you want the built-in MVC 6.1+ mechanism. Therefore, **do not blindly copy the service rule "put `@Validated` on the class to enable AOP" to every controller** without checking the version and desired mechanism.

Spring MVC supports determining groups for built-in method validation (see `MethodValidator#determineValidationGroups` and `MethodValidationAdapter`); annotations on the method can supply groups. However, an annotation on a controller method does not automatically mean it acts as a service AOP pointcut. Test along the **actual validation path**, especially in codebases with legacy class-level `@Validated`.

## 6. How Group Selection Affects Parameters, Return Values, and Nested Objects

### 6.1. Directly on Method Parameters

```java
@Service
@Validated(Create.class)
public class InventoryService {

    public String reserve(
            @NotBlank(groups = Create.class) String sku,
            @Min(value = 1, groups = Create.class) int quantity) {
        return sku + ":" + quantity;
    }
}
```

This snippet illustrates AOP method validation: selecting group `Create` applies to **both** parameter constraints belonging to `Create`. It does not mean "each parameter chooses its own group" within a single normal executable validation pass.

### 6.2. Constraints on Return Values

Jakarta Validation supports constraints on return values:

```java
@Service
@Validated(Create.class)
public class CodeService {

    @NotBlank(groups = Create.class)
    public String generateCode() {
        return "";
    }
}
```

This illustrative snippet intentionally returns an empty string: with a proxy and group `Create`, the error is detected **after the method body runs, before an invalid result is returned to the caller**. Therefore side effects performed inside the method may already have occurred before return validation fails; do not use return validation to replace transaction invariants or business checks at data-write points.

### 6.3. @Valid and Groups of Nested Objects

Example:

```java
public record Profile(
        @NotBlank(groups = Create.class) String displayName
) {}

@Service
@Validated(Create.class)
public class ProfileService {

    public void register(@Valid Profile profile) {
        // ...
    }
}
```

These are two illustrative types requiring `jakarta.validation.Valid` and corresponding Java/Spring annotations. When service method validation selects `Create`, that group normally **propagates down to `Profile`** via `@Valid` (cascading). Thus `displayName` belonging to `Create` is also validated.

If a nested object must use a different group from its parent, Jakarta Validation provides `@ConvertGroup` at the cascade site:

```java
public record Registration(
        @Valid
        @ConvertGroup(from = Create.class, to = Detailed.class)
        Profile profile
) {}
```

`@ConvertGroup` here is a **standard Jakarta feature**, though the short example assumes group `Detailed` and `Profile` constraints in that group are declared. Never place `@ConvertGroup` alone without `@Valid` on the association; providers may throw `ConstraintDeclarationException`.

### 6.4. @Validated Does Not Change Constraint Metadata

If `@NotNull(groups=Update.class)` is attached to a parameter, adding `@Validated(Create.class)` to the method **does not reassign** that constraint to `Create`. Only the requested groups and Jakarta Validation inheritance/group-conversion rules determine whether it runs.

So when debugging "I added `@Validated` yet the constraint does not run," check **both sides**: `groups` on the constraint and `value()` at the group selection point.

## 7. Pitfalls Related to Proxies, Inheritance, and API Design

### 7.1. Marking Only the Method and Forgetting the Type

```java
@Service
public class WronglyConfiguredService {

    @Validated(Update.class)
    public void rename(
            @NotBlank(groups = Update.class) String name) {
        // ...
    }
}
```

This is a counterexample illustrating a configuration gap. Under **default AOP `MethodValidationPostProcessor`**, a method-only annotation **is not a pointcut** selecting the bean. Thus an external call may not undergo method validation. You need `@Validated` at the type level to select the bean, and then method-level annotations to override groups.

### 7.2. Internal Calls Bypass the Proxy

```java
@Service
@Validated(Create.class)
public class SelfCallService {

    public void outer() {
        inner(" ");            // self-invocation
    }

    @Validated(Update.class)
    public void inner(
            @NotBlank(groups = Update.class) String name) {
        // ...
    }
}
```

This is a counterexample: `outer()` calls `inner()` directly on the same object, which under standard Spring proxy AOP performs no separate interception for `inner`. Calling `inner(" ")` from another bean through the proxy is the expected path. Never rely on AOP validation to protect a method that can be invoked internally via `this`.

### 7.3. Private/Final Methods and Objects Created with `new`

Spring AOP proxies must be able to intercept method calls. `private` methods are not intercepted by proxies; CGLIB cannot override `final` methods or classes. With JDK dynamic proxies, callers must invoke through a proxied interface method. Details of proxy type and implementation classes can affect annotation discovery; test with a real Spring context when interface/class hierarchies are complex.

### 7.4. Method Overriding in Java Inheritance

Jakarta Validation defines strict rules for method parameter constraints when overriding or implementing: you may not arbitrarily **strengthen preconditions** (such as adding parameter constraints to an implementation method when the parent contract declares none), to preserve the Liskov substitution principle. Violations can lead to `ConstraintDeclarationException` in the provider.

Group selection with Spring's `@Validated` does not waive Jakarta's method constraint inheritance rules. If code places constraints on an interface while selecting groups on an implementation, verify the annotation combination works with your active Spring/proxy/provider setup and test through the real interface/caller.

### 7.5. Exceptions and Error Handling Vary by Validation Path

| Validation point | Common case | Typical exception |
| --- | --- | --- |
| Direct Jakarta API | `validator.validate(bean, groups...)` | Returns `Set<ConstraintViolation<?>>`; does not throw on violations alone |
| Spring service AOP | Default `MethodValidationPostProcessor` | `ConstraintViolationException` |
| Spring service AOP adapted errors | `setAdaptConstraintViolations(true)` | `MethodValidationException` |
| MVC standalone DTO validation | `@Validated(Group.class) @RequestBody Dto` | `MethodArgumentNotValidException` |
| MVC 6.1+ built-in method validation | Direct constraints on handler params/return | `HandlerMethodValidationException` |
| Binding/deserialization | Invalid JSON or unconvertible type | Separate binding/HTTP message exceptions; can occur before Bean Validation |

Exception types do not depend on which group a constraint belongs to. They reflect the **integration path** (Spring AOP, Spring MVC, or plain Jakarta API). Standardize error responses based on each exception's API rather than assuming all group validation produces a `BindingResult`.

## 8. Choosing One or Multiple Groups in Practice

### 8.1. Create and Update Sharing Rules

Suppose:

```java
public interface Create {}
public interface Update {}

public record AccountRequest(
        @NotBlank(groups = {Create.class, Update.class}) String username,
        @NotNull(groups = Create.class) String initialPassword,
        @NotBlank(groups = Update.class) String updateReason
) {}
```

In the Create flow, `username` and `initialPassword` are validated. In the Update flow, `username` and `updateReason` are validated. Because `username` belongs to both groups, no annotation duplication is needed.

If standard constraints like `@Email` should always run, assign them to both groups or design `Default` appropriately. **Do not assume `Default` is automatically included** just because you expect "basic rules always run."

### 8.2. Multiple Groups on One Method

```java
@Validated({Default.class, Update.class})
public void update(
        @NotBlank String id,
        @NotBlank(groups = Update.class) String reason) {
    // ...
}
```

This is an illustrative method inside a bean with type-level `@Validated`. The check selects **two groups** covering both `id` (in `Default`) and `reason` (in `Update`). Passing an array of multiple elements does not require the provider to evaluate them in array order.

### 8.3. Split by Group or by DTO / Layer?

Groups make sense when the **same data structure** has multiple independent constraint sets, such as Create/Update/Publish or Draft/Submit. However, if two operations differ in semantics, shape, and API contract, **two dedicated DTOs** can be clearer than one DTO packed with dozens of `groups` annotations. Consider:

- Do groups help express a reusable validation policy?
- Does every call path select the right group, including background jobs and message consumers?
- Are `Default` constraints accidentally being skipped?
- Do clients receive consistent error codes per endpoint?
- Will adding a new group cause existing method-level `@Validated` annotations to miss the new constraint?

Do not treat groups as an **authorization** mechanism. Validation groups decide which constraint set runs; they do not authenticate users, enforce permissions, or protect resources.

## 9. Testing Group Selection Thoroughly

A test suite should cover **selected groups, unselected groups, proxies, and exceptions**:

| Test case | What it proves |
| --- | --- |
| Call method without its own `@Validated` on a bean with class `@Validated(Create.class)` | `Create` is selected |
| Call method with `@Validated(Update.class)` | `Update` is selected, without implicitly adding `Create` |
| Call method with empty `@Validated` | `Default` is selected |
| `Default` constraint under a `Create`-only class | Does not run automatically |
| Method with `@Validated({Default.class, Update.class})` | Both groups are evaluated |
| Call bean created with `new`, bypassing Spring proxy | Do not expect AOP to run automatically |
| Service calls its own method via `this` | Do not expect interception of the inner method |
| `@Valid` on nested object parameter | Group cascades properly or converts via `@ConvertGroup` as designed |
| MVC handler with `@RequestBody` and method constraints | Distinguishes `MethodArgumentNotValidException` and `HandlerMethodValidationException` |
| Project enabling `setAdaptConstraintViolations(true)` | Handler/tests adjusted to the right exception type |

To avoid weak tests, do not check only `getConstraintViolations().size()` when multiple constraints exist: verify the **property path**, annotation type, or matching message template. Never rely on `Set<ConstraintViolation<?>>` iteration order or localized message strings. When testing group selection on a service, invoke via an `@Autowired` bean; calling `new AccountService()` does not test Spring AOP.

If no exception occurs on invalid input, check in order:

1. Is the bean actually Spring-created and invoked through the proxy?
2. Is `MethodValidationPostProcessor` registered and is a Bean Validation provider present?
3. Is `@Validated` on the **type** of the service requiring AOP?
4. Does the method override the group at method level? Does the constraint belong to `Default` or another group?
5. Does the constraint's `groups` attribute match the selected group?
6. Is the method `public`, free from proxy/`final`/`private` limits, and free from self-invocation?
7. If in a controller, are you using Spring MVC 6.1+ built-in validation, argument validation, or AOP controller validation?
8. Is the test checking the right exception type, bean instance, and framework version?

## 10. Common Mistakes to Avoid

**Mistake 1: Placing `@Validated(Update.class)` only on a service method and expecting AOP to validate it automatically.** In default Spring-driven AOP method validation, the method annotation only **overrides groups**; type-level `@Validated` is required for bean selection.

**Mistake 2: Thinking method-level groups add onto class-level groups.** `@Validated(Update.class)` on a method is not equivalent to `@Validated({Create.class, Update.class})` when the class selects `Create`. It replaces the type selection for that method.

**Mistake 3: Confusing `Default` with "all groups."** Constraints without a group belong to `Default`. Selecting `Create` does not implicitly evaluate `Default`; select both explicitly or design appropriate inheritance if desired.

**Mistake 4: Using `@Valid` to select groups.** `@Valid` triggers cascading and is used by frameworks to initiate bean validation at boundaries, yet this Jakarta annotation accepts no group arguments. `@Validated(SomeGroup.class)` is Spring's selection/hint mechanism.

**Mistake 5: Putting class-level `@Validated` on every MVC controller just because services do it.** Spring MVC 6.1+ has built-in method validation; class-level `@Validated` can switch to AOP and alter the exception path. Choose the intended mechanism deliberately instead of mixing accidentally.

**Mistake 6: Confusing `@RequestBody` validation with direct method parameter validation.** `@Validated(Group.class) @RequestBody Dto` is used by MVC when binding a command object; `@Min` directly on `@RequestParam int` triggers built-in method validation in MVC 6.1+.

**Mistake 7: Assuming a test with `new Service()` proves method validation works.** Calls must go through the Spring-managed bean/proxy.

**Mistake 8: Arbitrarily adding constraints to parameters of methods overriding an interface.** Jakarta Validation has method inheritance rules; certain declarations cause providers to throw `ConstraintDeclarationException`.

**Mistake 9: Conflating group names with business steps.** `Create`/`Update` are constraint sets, not replacements for transactions, authorization, idempotency, or database uniqueness checks.

**Mistake 10: Assuming all validation errors throw the same exception.** Choose handling based on the boundary (Jakarta API, Spring AOP, MVC argument resolver, MVC built-in); do not guess from the selected group.

## 11. Implementation Checklist

1. Define groups as marker interfaces with names reflecting business meaning.
2. Explicitly declare `groups` on each constraint and decide which constraints belong to `Default`.
3. For Spring service AOP, place `@Validated(...)` on the type to enable validation and set the default group.
4. Place `@Validated(...)` on a method only when you truly want to **override** the type's group; declare all groups that should run.
5. Distinguish annotations on service methods from annotations on **Spring MVC command object parameters**.
6. For Spring MVC 6.1+ controllers, consider built-in method validation and avoid adding type-level `@Validated` out of habit.
7. Invoke services through Spring proxies, without relying on self-invocation or non-interceptable methods.
8. Test at least one violation per group, one `Default` constraint, one method override, and actual exception handling.
9. Use group sequences only when ordering is needed; use group conversion when switching groups during cascading, without conflating them with class-vs.-method override rules.
10. When changing a class's default group, review every method without its own `@Validated` because its active constraint set may change.

**Core takeaway:** In Spring AOP method validation, `@Validated` on the **class** determines whether the bean is proxied and sets its default group; `@Validated` on a **method** overrides the group for that invocation. In Spring MVC, `@Validated` on a **parameter** acts as a hint to validate a command object, while built-in method validation from 6.1+ has its own triggers and exceptions. Reading annotation placement, constraint groups, and framework call paths accurately prevents missed validations.

## References

- [Spring Framework — `@Validated` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/annotation/Validated.html): groups on types/methods and pointcut role.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html): `MethodValidationPostProcessor`, AOP, method validation exceptions.
- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): built-in MVC validation 6.1+, note on controller class-level `@Validated`.
- [Jakarta Validation — Groups](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/validation/groups/package-summary): `Default`, `@ConvertGroup`, and group mechanisms.
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): group inheritance, group sequences, method constraint inheritance.
