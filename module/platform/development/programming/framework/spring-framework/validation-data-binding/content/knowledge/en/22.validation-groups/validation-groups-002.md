# Applying Constraints to One or Multiple Groups in Jakarta Bean Validation and Spring

## 1. Why Do We Need Validation Groups?

A Java object may be used in multiple contexts: creating, updating, publishing, paying, or approving. Fields required in one context are not necessarily required in another. For example:

- **Creating an account**: the identifier is assigned by the system, so the client must not send `id`; email must be valid.
- **Updating an account**: `id` must be present; email must continue to be valid.
- **Publishing a profile**: the bio section must meet a minimum length.
- **In all cases**: the display name must not be blank.

Separating one DTO per operation is sometimes the easiest approach to control. However, when a shared bean genuinely has multiple rule sets, **validation groups** let you select a **subset of constraints** depending on the context, rather than running all constraints unconditionally.

Two things must be distinguished:

1. **Which group(s) is a constraint assigned to?** — use the `groups` attribute on the annotation, such as `@NotBlank(groups = Create.class)`.
2. **Which group(s) should be validated?** — call `Validator.validate(bean, Create.class)`, or use `@Validated(Create.class)` at a Spring integration point.

Simply declaring groups **does not automatically run validation**. You need a Jakarta Bean Validation provider (such as Hibernate Validator) and an actual validation invocation point.

This article focuses on how a constraint belongs to **one or multiple groups**, its relationship with the `Default` group, how to specify multiple groups during validation, Spring MVC, groups on child objects, ordering with `@GroupSequence`, and testing.

> Examples are based on `jakarta.validation.*` (Jakarta Bean Validation 3.x), Java 17+, and Spring Framework 6+/Spring Boot 3.x. Spring Boot 2.x projects typically use `javax.validation.*`; do not mix the old and new namespaces in the same application.

## 2. What Is a Group? How to Define Marker Interfaces

In Jakarta Bean Validation, a group is typically represented by a **Java interface** with no methods:

```java
package example;

public final class Groups {
    private Groups() {}

    public interface Create {}
    public interface Update {}
    public interface Publish {}
}
```

These interfaces are **markers**: they do not execute any validation algorithm. They are context names used by the provider to decide which constraints apply.

You can define groups at top level or nested inside a class holding constants/groups, like `Groups.Create.class`. Use clear business names (`Create`, `Update`, `Publish`) rather than names tied to UI details or unstable endpoints.

Do not use strings like `"Create"` to define groups. The input type of `groups` is a class array, specifically `Class<?>[]`, so the syntax is:

```java
@NotNull(groups = Groups.Create.class)
@NotBlank(groups = {Groups.Create.class, Groups.Update.class})
```

On the second line, a single **constraint declaration** is attached to **two groups**. There is no "single group only" rule and no requirement to write the same annotation twice. The group only determines whether the constraint is **selected** during validation; the validation logic of `@NotBlank` itself does not change.

### 2.1. The Default Group Does Not Mean "All"

Jakarta provides `jakarta.validation.groups.Default`.

- When declaring a constraint **without the `groups` attribute**, the constraint belongs to `Default`.
- `@NotBlank String name;` is equivalent in group membership to `@NotBlank(groups = Default.class) String name;`.
- When calling `validator.validate(bean)` **without passing any groups**, `Default` is validated by default.
- When calling `validator.validate(bean, Create.class)`, constraints belonging **only to `Default`** generally **do not run automatically**.
- When calling `validator.validate(bean, Default.class, Create.class)`, the set of constraints belonging to both groups runs (subject to relevant group inheritance/sequence rules).

The most important point: `Default` **does not mean "applies in every context"**. If Create/Update logic must always apply a common rule, you must also pass `Default` at validation time, or place that rule into a shared group or the corresponding business groups.

## 3. Applying a Constraint to One Group or Multiple Groups

Consider a DTO with four distinct rules:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.Size;

record AccountRequest(
    // Belongs only to Default because groups is omitted:
    @NotBlank String displayName,

    // Must not send id on create; must provide id on update:
    @Null(groups = Groups.Create.class)
    @NotNull(groups = Groups.Update.class)
    Long id,

    // Two constraints, each belonging to both groups:
    @NotBlank(groups = {
        Groups.Create.class, Groups.Update.class
    })
    @Email(groups = {
        Groups.Create.class, Groups.Update.class
    })
    String email,

    // Only used when publishing:
    @Size(min = 10, groups = Groups.Publish.class)
    String about
) {}
```

This is an illustrative Java 17+ fragment assuming `Groups` is already defined. Reading each part:

- `displayName`: `@NotBlank` belongs to **`Default`**; a validation pass for only `Create` will not check this constraint.
- `id`: in the `Create` group it must be **null** via `@Null`; in the `Update` group it must be **non-null** via `@NotNull`. These are two independent constraints on the same field with different groups.
- `email`: both `@NotBlank` and `@Email` belong to `Create` **and** `Update`. Each constraint can be applied when either group is requested.
- `about`: `@Size(min = 10)` belongs only to `Publish`. When validating creation, a short description does not trigger an error from this constraint.

Do not misunderstand `groups = {Create.class, Update.class}` as meaning "only check when both groups are requested together". It means the constraint is in **each listed group**.

### 3.1. Constraint Selection Table by Group

| Constraint | Default | Create | Update | Publish |
| --- | :---: | :---: | :---: | :---: |
| `displayName: @NotBlank` | ✓ | — | — | — |
| `id: @Null` | — | ✓ | — | — |
| `id: @NotNull` | — | — | ✓ | — |
| `email: @NotBlank` | — | ✓ | ✓ | — |
| `email: @Email` | — | ✓ | ✓ | — |
| `about: @Size(min=10)` | — | — | — | ✓ |

This table assumes the marker interfaces have no inheritance relationships, and no `@GroupSequence` or group conversion (`@ConvertGroup`) is involved. Those mechanisms can affect the actual set of constraints executed and are explained below.

### 3.2. One Value, Multiple Validation Passes

Given an object with data:

```java
var account = new AccountRequest(
    " ",            // displayName fails Default
    -5L,            // id fails Create, passes Update
    "not-an-email", // email fails Create and Update
    "short"         // about fails Publish
);
```

Expected results per pass:

| Requested group(s) | Failing property paths |
| --- | --- |
| No group passed / `Default.class` | `displayName` |
| `Create.class` | `id`, `email` |
| `Update.class` | `email` |
| `Publish.class` | `about` |
| `Create.class, Publish.class` | `id`, `email`, `about` |
| `Default.class, Create.class` | `displayName`, `id`, `email` |

A constraint can be marked as belonging to multiple groups, but within a single validation pass along the same path, the provider must not return duplicate violations for the same constraint just because it was reached via multiple requested groups. Do not build UI logic that depends on the iteration order of `Set<ConstraintViolation<?>>`.

## 4. Difference Between Assigning `groups` and Calling `validate()`

Every standard constraint has a `groups` attribute. Syntax for passing groups when using Jakarta `Validator`:

```java
import jakarta.validation.Validator;
import jakarta.validation.groups.Default;

void check(Validator validator, AccountRequest account) {
    validator.validate(account); // equivalent to Default

    validator.validate(account, Groups.Create.class);

    validator.validate(
            account,
            Groups.Create.class,
            Groups.Update.class);

    validator.validate(
            account,
            Default.class,
            Groups.Create.class);
}
```

This is an illustrative **fragment** of API calls. The `validate(...)` methods return `Set<ConstraintViolation<AccountRequest>>` and do not throw exceptions on invalid data by default.

Three things to remember:

1. `validate(object, A.class, B.class)` selects the union of constraints applicable to the requested groups; it does not require each constraint to belong to **both A and B simultaneously**.
2. `validate(object, A.class, B.class)` **does not guarantee validating A before B**. If you need ordering and want to proceed to B only when A passes, use `@GroupSequence`.
3. If only `A.class` is requested, `Default` is not automatically included unless `A` extends `Default`, a relevant group sequence applies, or another explicit rule is defined.

You can call `validator.validateProperty(bean, "email", Groups.Create.class)` to validate a single property, or `validateValue(AccountRequest.class, "email", value, Groups.Create.class)` to check a candidate value without instantiating the bean. These APIs do not replace validating the whole object graph when rules involve multiple fields or cascades.

## 5. Runnable Java 17+ Example with Maven and Hibernate Validator

This standalone example uses the exact groups above and prints **sorted violation paths** so the output does not depend on the `Set` order returned by the provider.

Directory layout:

```text
groups-demo/
├── pom.xml
└── src/
    ├── main/java/example/GroupValidationDemo.java
    └── test/java/example/GroupValidationDemoTest.java
```

### 5.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>groups-demo</artifactId>
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

`hibernate-validator` is the provider, while `expressly` supplies the Jakarta EL implementation commonly used for message interpolation. In a Spring Boot application, use `spring-boot-starter-validation` and Boot's BOM rather than manually pinning library versions as in this standalone example.

### 5.2. File src/main/java/example/GroupValidationDemo.java

```java
package example;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.Size;
import jakarta.validation.groups.Default;
import jakarta.validation.GroupSequence;

public final class GroupValidationDemo {
    private GroupValidationDemo() {}

    public interface Create {}
    public interface Update {}
    public interface Publish {}

    // Default is validated before Publish when OrderedPublish is requested.
    @GroupSequence({Default.class, Publish.class})
    public interface OrderedPublish {}

    public record Account(
            @NotBlank String displayName,

            @Null(groups = Create.class)
            @NotNull(groups = Update.class)
            Long id,

            @Email(groups = {Create.class, Update.class})
            String email,

            @Size(min = 10, groups = Publish.class)
            String about) {
    }

    public static Account invalidExample() {
        return new Account(
                " ", -5L, "not-an-email", "short");
    }

    public static Set<String> invalidFields(
            Validator validator,
            Account account,
            Class<?>... groups) {

        Set<ConstraintViolation<Account>> violations =
                validator.validate(account, groups);

        return violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(Collectors.toSet());
    }

    private static void print(
            String label,
            Validator validator,
            Account account,
            Class<?>... groups) {

        String names = invalidFields(validator, account, groups)
                .stream()
                .sorted()
                .collect(Collectors.joining(","));

        System.out.println(label + "=" + names);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();
            Account account = invalidExample();

            print("default", validator, account);
            print("create", validator, account, Create.class);
            print("update", validator, account, Update.class);
            print("publish", validator, account, Publish.class);
            print("create+publish", validator, account,
                    Create.class, Publish.class);
            print("default+create", validator, account,
                    Default.class, Create.class);
            print("ordered-publish", validator, account,
                    OrderedPublish.class);
        }
    }
}
```

Run in the `groups-demo` directory (Java 17+, with Maven able to download or use cached dependencies):

```bash
mvn -q test
mvn -q exec:java -Dexec.mainClass=example.GroupValidationDemo
```

Output **from the `println` calls**, excluding Maven/provider logs:

```text
default=displayName
create=email,id
update=email
publish=about
create+publish=about,email,id
default+create=displayName,email,id
ordered-publish=displayName
```

The last line reflects `@GroupSequence`: `Default` has a `displayName` violation, so `Publish` is not evaluated when validating `OrderedPublish`. If you instead validate the two groups separately via `Default.class, Publish.class`, both constraints are evaluated **without guaranteed order**.

In the demo, `email` only has `@Email`. In real applications, `@Email` does not by itself forbid `null` or empty strings: if email is required, add `@NotBlank(groups={Create.class,Update.class})`.

## 6. JUnit 5 Unit Tests Proving Which Groups Run

**File `src/test/java/example/GroupValidationDemoTest.java`:**

```java
package example;

import java.util.Set;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.groups.Default;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GroupValidationDemoTest {

    private static Set<String> fields(
            Validator validator, Class<?>... groups) {
        return GroupValidationDemo.invalidFields(
                validator, GroupValidationDemo.invalidExample(), groups);
    }

    @Test
    void picksOneGroupAtATime() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            assertEquals(Set.of("displayName"),
                    fields(validator));
            assertEquals(Set.of("email", "id"),
                    fields(validator, GroupValidationDemo.Create.class));
            assertEquals(Set.of("email"),
                    fields(validator, GroupValidationDemo.Update.class));
            assertEquals(Set.of("about"),
                    fields(validator, GroupValidationDemo.Publish.class));
        }
    }

    @Test
    void includesAllRequestedGroupsWithoutOrdering() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            assertEquals(Set.of("email", "id", "about"),
                    fields(validator,
                            GroupValidationDemo.Create.class,
                            GroupValidationDemo.Publish.class));

            assertEquals(Set.of("displayName", "email", "id"),
                    fields(validator,
                            Default.class,
                            GroupValidationDemo.Create.class));
        }
    }

    @Test
    void orderedGroupSkipsNextGroupOnFailure() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            assertEquals(Set.of("displayName"),
                    fields(validator,
                            GroupValidationDemo.OrderedPublish.class));
        }
    }
}
```

These tests use the same `pom.xml` in section 5, including JUnit Jupiter and Maven Surefire. Assertions compare **sets of property names**, rather than `ConstraintViolation` iteration order or English message strings that can vary by locale.

In practice, add tests for valid creation payloads, valid update payloads, and missing data. A test that only proves a group was **selected** does not replace business testing of individual constraints.

## 7. When a Constraint Belongs to Two Groups, Does It Run Twice?

Group **membership** is different from **execution count**. With:

```java
@NotBlank(groups = {Create.class, Update.class})
String email;
```

When calling `validate(bean, Create.class)`, the constraint belongs to the requested group so it is evaluated. When calling `validate(bean, Update.class)` in a **separate** call, it is evaluated as well.

However, within **a single call** `validate(bean, Create.class, Update.class)`, the Bean Validation provider must not return two copies of the same violation on the same property path. The specification defines rules to avoid repeatedly validating the same constraint within one validation routine for a given path. Having multiple **distinct constraint declarations** on a field (such as `@NotBlank` and `@Email`) represents two separate conditions and can produce two distinct violations if both fail.

Do not use `groups = {Create.class, Update.class}` to express "only when both Create and Update are selected". If you need a combined condition, that is a **new business rule**, not default `groups` syntax.

## 8. Spring MVC: Selecting One or Multiple Groups with `@Validated`

In Spring, `@Valid` comes from Jakarta Validation while `@Validated` comes from `org.springframework.validation.annotation`. `@Validated` supports selecting **validation hints**, commonly group classes.

First, define the shared interfaces.

**File `src/main/java/com/example/accounts/Checks.java`:**

```java
package com.example.accounts;

public final class Checks {
    private Checks() {}

    public interface Create {}
    public interface Update {}
    public interface Publish {}
}
```

**File `src/main/java/com/example/accounts/AccountPayload.java`:**

```java
package com.example.accounts;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.Size;

public record AccountPayload(
        @NotBlank String displayName,

        @Null(groups = Checks.Create.class)
        @NotNull(groups = Checks.Update.class)
        Long id,

        @NotBlank(groups = {
                Checks.Create.class, Checks.Update.class
        })
        @Email(groups = {
                Checks.Create.class, Checks.Update.class
        })
        String email,

        @Size(min = 10, groups = Checks.Publish.class)
        String about) {
}
```

In this DTO, `displayName` belongs to `Default`; `email` belongs to **both Create and Update**; `id` has opposite conditions between the two operations; and `about` belongs to `Publish`.

**File `src/main/java/com/example/accounts/AccountController.java`:**

```java
package com.example.accounts;

import jakarta.validation.groups.Default;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @PostMapping("/accounts")
    public ResponseEntity<Void> create(
            @Validated({Default.class, Checks.Create.class})
            @RequestBody AccountPayload payload) {

        // Simulate success after validation has passed.
        return ResponseEntity.status(201).build();
    }

    @PutMapping("/accounts")
    public ResponseEntity<Void> update(
            @Validated({Default.class, Checks.Update.class})
            @RequestBody AccountPayload payload) {

        return ResponseEntity.noContent().build();
    }
}
```

These are **files inside a Spring MVC or Spring Boot 3.x application with Web and Validation dependencies**, not a standalone program. The two endpoints use `@Validated` to pass **two groups each** to Spring's Bean Validation integration:

- `POST /accounts` validates `Default` and `Create`.
- `PUT /accounts` validates `Default` and `Update`.
- Because `Default.class` is explicitly passed, `@NotBlank displayName` is still checked for both requests.
- `Publish` is not among those groups, so a short `about` does not fail requests at either endpoint.
- A provider (usually via `spring-boot-starter-validation`) is required for annotations to actually be processed.

**Using `@Validated(Create.class)` alone can skip constraints belonging only to `Default`.** This is a fairly common bug when migrating from `@Valid` to `@Validated` without adjusting groups.

### 8.1. Which Requests Are Valid?

Valid creation:

```http
POST /accounts
Content-Type: application/json

{
  "displayName": "An",
  "id": null,
  "email": "an@example.com",
  "about": "short"
}
```

The controller above returns **201 Created**; `about` is under 10 characters, but the `Publish` constraint **was not selected**, so it does not cause the Create request to fail.

Invalid creation:

```http
POST /accounts
Content-Type: application/json

{
  "displayName": " ",
  "id": 7,
  "email": "invalid-email",
  "about": "short"
}
```

With a standard validation provider/configuration, this typically returns **400 Bad Request** because:
- `displayName` violates `@NotBlank` in `Default`.
- `id` violates `@Null` in `Create`.
- `email` violates `@Email` in `Create`.
- `about` is not checked because it belongs only to `Publish`.

Valid update:

```http
PUT /accounts
Content-Type: application/json

{
  "displayName": "An",
  "id": 7,
  "email": "an@example.com",
  "about": "short"
}
```

The endpoint returns **204 No Content**. For Update, `id` must be non-null; this example illustrates **data validation** and does not yet verify whether the ID exists or belongs to the user.

Note: `@Validated` only enforces data constraints. It does **not** automatically provide authorization, verify record ownership, validate state transitions, or prevent clients from overwriting fields disallowed by the API. For production endpoints, still consider separate DTOs for Create and Update if their contracts and write permissions differ substantially.

### 8.2. How Does Spring Handle Group Errors?

With `@Validated @RequestBody` on a command object in MVC:
- Jackson or an `HttpMessageConverter` converts JSON into `AccountPayload`.
- Spring triggers validation with the selected groups/hints.
- The Bean Validation provider evaluates constraints belonging to the requested groups.
- If errors occur and there is no `BindingResult`/`Errors` handling them inline, Spring MVC typically throws `MethodArgumentNotValidException` and returns **HTTP 400**.
- If a handler method requires **method validation** due to constraints directly on parameters or the return value, Spring MVC 6.1+ may use `HandlerMethodValidationException`.

JSON that cannot be deserialized into the object (for example, a numeric string that cannot be parsed into `Long`) can fail **before** Bean Validation runs. Do not conflate type conversion/binding errors with constraint violations.

### 8.3. MockMvc Tests Verifying the Right Groups

**File `src/test/java/com/example/accounts/AccountControllerTest.java`** in a Spring Boot application with `spring-boot-starter-test`:

```java
package com.example.accounts;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(AccountController.class)
class AccountControllerTest {
    @Autowired MockMvc mvc;

    @Test
    void createRunsDefaultAndCreateGroups() throws Exception {
        mvc.perform(post("/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "displayName": " ",
                      "id": 7,
                      "email": "invalid-email",
                      "about": "short"
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                assertTrue(result.getResolvedException()
                        instanceof MethodArgumentNotValidException);
                var ex = (MethodArgumentNotValidException)
                        result.getResolvedException();
                assertTrue(ex.getBindingResult()
                        .hasFieldErrors("displayName"));
                assertTrue(ex.getBindingResult()
                        .hasFieldErrors("id"));
                assertTrue(ex.getBindingResult()
                        .hasFieldErrors("email"));
                // The Publish group was not selected; no error on about.
                assertTrue(!ex.getBindingResult()
                        .hasFieldErrors("about"));
            });
    }

    @Test
    void createAllowsShortAboutWhenPublishNotSelected()
            throws Exception {
        mvc.perform(post("/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "displayName": "An",
                      "id": null,
                      "email": "an@example.com",
                      "about": "short"
                    }
                    """))
            .andExpect(status().isCreated());
    }

    @Test
    void updateRequiresId() throws Exception {
        mvc.perform(put("/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "displayName": "An",
                      "id": null,
                      "email": "an@example.com",
                      "about": "short"
                    }
                    """))
            .andExpect(status().isBadRequest());
    }
}
```

These tests illustrate Spring Boot 3.x APIs with `@WebMvcTest`, a Bean Validation provider, and appropriate application scanning. If your setup has a custom `@ControllerAdvice`, the exception handling and response format may differ; what matters is proving which group actually validates which fields.

## 9. `@Valid`, `@Validated`, and Group Conversion in Nested Validation

`@Valid` is Jakarta's **cascaded validation** metadata. When a parent object is validated for a group, the provider normally propagates the currently validated group down to child objects via properties annotated with `@Valid`.

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

interface Create {}

class Address {
    @NotBlank(groups = Create.class)
    String city;
}

class Customer {
    @Valid
    Address address;
}
```

When calling `validator.validate(customer, Create.class)`, the `Address.city` constraint belonging to `Create` can be evaluated **if `address` is non-null**. When calling only `validator.validate(customer)` (`Default`), constraints on `Address` belonging solely to `Create` do not run.

If you need to translate group names between two business domains, Jakarta provides `@ConvertGroup`, which only has effect on a `@Valid` cascade path:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;
import jakarta.validation.constraints.NotBlank;

interface ChildChecks {}

class ShippingAddress {
    @NotBlank(groups = ChildChecks.class)
    String street;
}

class Order {
    @Valid
    @ConvertGroup(from = Default.class, to = ChildChecks.class)
    ShippingAddress shippingAddress;
}
```

When validating `Order` with the `Default` group, along the **`shippingAddress` path**, the group is converted to `ChildChecks` before validating the child bean; the `ChildChecks` constraint on `ShippingAddress.street` is evaluated if the bean is present. This **does not change** the groups of other constraints on `Order` itself.

Use `@ConvertGroup` when you genuinely need context mapping between models; do not replace it by putting every constraint into every group. With a container like `List<@Valid Address>`, group conversion can also be applied at the appropriate cascade point per the specification.

**What groups do not do:** they do not turn on `@Valid` when a cascade path is missing, they do not add `@NotNull` when a child bean is null, and they do not turn a Java DTO into a validation call on their own. All three still have their own requirements.

## 10. Group Inheritance and Shared Constraint Sets

One group can extend another via Java interface inheritance.

```java
interface BasicChecks {}
interface FullChecks extends BasicChecks {}
```

If a constraint is assigned to `BasicChecks`, requesting validation for `FullChecks.class` also includes constraints from `BasicChecks` according to group inheritance rules. For example:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

class Profile {
    @NotBlank(groups = BasicChecks.class)
    String name;

    @Size(min = 50, groups = FullChecks.class)
    String biography;
}
```

- `validate(profile, BasicChecks.class)` checks `name`.
- `validate(profile, FullChecks.class)` checks `name` **and** `biography`.
- `validate(profile)` using `Default` does not automatically pick either of these groups unless there are constraints in `Default` or explicit inheritance.

Group inheritance is a **set relationship**, not "Basic runs before Full". If you need an order with stop-on-failure semantics, use a group sequence.

**Another design option:** place shared constraints into a dedicated `Common.class` group, then pass `@Validated({Common.class, Create.class})`. This is often easier to read and avoids the misconception that `Default` runs on every endpoint.

## 11. Does Applying Multiple Groups Guarantee Evaluation Order?

**No.** With:

```java
validator.validate(bean, Default.class, Publish.class);
```

Jakarta Bean Validation allows processing constraints from the two groups in any order, as long as specification-compliant validation semantics are preserved. You must not assume the first group argument is always processed first or that the second group will be skipped if the first fails.

To validate sequentially, declare a **group sequence** on an interface:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

interface PublishChecks {}

@GroupSequence({Default.class, PublishChecks.class})
interface PublishFlow {}
```

Then:

```java
validator.validate(bean, PublishFlow.class);
```

Following the sequence, `Default` is checked first. If `Default` has violations, `PublishChecks` **is not executed in this pass**. If `Default` passes, the `PublishChecks` step runs. A constraint belonging to multiple groups in a sequence is not evaluated repeatedly for the same path.

This is an **inter-group ordering and short-circuiting mechanism**, not a simple way to assign one constraint to multiple groups. Do not use `@GroupSequence` when you just want the union of two groups without caring about order.

Groups in a sequence must not form cyclic dependencies. Attaching constraints directly to the interface that defines the sequence is also not a recommended pattern. When redefining the `Default` group on a **class** with `@GroupSequence`, the specification imposes specific rules (you must include the class itself in the sequence, not just `Default.class`); consult the official documentation before using that advanced configuration.

## 12. Using Validation Groups for Services and Method Validation

Groups also apply to validating method parameters and return values when **method validation** is enabled. However:

- `@Valid` on an ordinary Java method parameter **does not automatically trigger** validation.
- In a Spring service bean, traditional method validation works through infrastructure/proxies (typically with `@Validated` on the bean), so calls must go **through the Spring bean proxy** with a provider present.
- Calling `new MyService()` or self-invoking `this.someMethod()` within the same bean can bypass Spring AOP interception.
- Spring MVC 6.1+ includes built-in method validation for handler methods, distinct from service proxy interception; controller-level `@Validated` can affect which mechanism is chosen.

An illustrative fragment:

```java
import jakarta.validation.Valid;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated(Groups.Update.class)
class AccountService {

    public void save(@Valid AccountPayload payload) {
        // Logic after passing method validation if infrastructure is enabled.
    }
}
```

In this fragment, `Groups.Update` is the default group for method validation on the bean per Spring configuration, while `@Valid` requests cascading into `AccountPayload`. If you use `Groups.Update` and also want `Default` constraints, design or select the appropriate group(s); never assume `Default` is automatically added.

**Important boundary:** group validation does not replace authorization or transaction invariants. A user permitted to call Update must still be authorized to act on that specific object, even when the DTO is valid.

## 13. Container Element Constraints and Groups

Group metadata is declared directly on constraints at type argument positions:

```java
import java.util.List;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

record Labels(
        @NotEmpty
        List<@NotBlank(groups = Groups.Create.class) String> values) {
}
```

- `@NotEmpty` on the list belongs to `Default`.
- `@NotBlank` on each `String` belongs to `Create`.
- `validate(labels)` only checks `@NotEmpty`; if the list is non-empty but contains `" "`, this `Default` pass does not automatically run `@NotBlank`.
- `validate(labels, Create.class)` checks the `String` elements under `Create` but does not automatically run `Default`'s `@NotEmpty`.
- `validate(labels, Default.class, Create.class)` requires both.

With child beans:

```java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

record Line(@NotBlank(groups = Groups.Update.class) String sku) {}

record Batch(List<@Valid Line> lines) {}
```

When Bean Validation validates `Batch` under `Update`, it cascades into each `Line` and validates `sku` under `Update`; when validating only `Default`, the `Update`-only constraint is not selected. `@Valid` does not re-select `Default`, and null `Line` elements are skipped during cascade unless `@NotNull` is placed on the element.

## 14. When to Use Groups vs. Separate DTOs?

**Groups are a good fit** when:
- The DTO structure is genuinely the same, with simple rules varying by Create/Update operations.
- A constraint needs to appear in multiple contexts and shared declaration reduces duplication.
- The system needs clear validation tiers, such as basic checks before expensive checks via a group sequence.
- You want to propagate the same group logic across cascades into child objects.

**Separate DTOs are usually clearer** when:
- Create and Update JSON schemas differ in many fields or data types.
- Field write permissions differ; for instance, admins can edit fields users cannot.
- Cross-field constraints and business invariants are too complex.
- One shared DTO accumulates many groups, group conversions, and sequences that hurt readability and testability.
- Public API contracts require independent documentation, OpenAPI schemas, and backward compatibility.

Whether you choose groups or separate DTOs, test at the **actual entry points** (MVC, service, message consumer) and never assume an annotation executes in every flow.

## 15. Test Matrix for Easily Missed Cases

| Scenario | Recommended assertion |
| --- | --- |
| Constraint without `groups` | Confirm it belongs to `Default` in a minimal test |
| Constraint only in `Create` | `validate(bean, Create.class)` runs; `validate(bean)` does not |
| Constraint in `Create` and `Update` | Both separate group calls validate it |
| `validate(bean, Create.class, Update.class)` | Union of both groups' constraints, no ordering assumed |
| `Default` + `Create` | Shared `Default` and `Create`-specific constraints both run |
| Group inheritance | Child group picks up parent group constraints |
| Group sequence | Later group is skipped when an earlier group has violations |
| Child bean with `@Valid` | Active group propagates down per cascade rules |
| Child bean with `@ConvertGroup` | Child branch is validated under converted group |
| Null child bean | Cascade is skipped; add `@NotNull` if required |
| List type argument with `groups` | Only constraints in the selected group run on elements |
| `@Validated` with only `Create` in MVC | Does not implicitly run `Default`; test shared fields |
| `@Validated({Default, Create})` | Both `Default` and `Create` are applied |
| Wrong JSON type | Deserialization/binding error can happen before validation |
| Project missing provider | Never assume Bean Validation is active |
| Service self-invocation | Do not assume AOP method validation executes |
| Valid DTO but unauthorized | Authorization and business checks still must run separately |

When asserting error paths, do not depend on violation order or English messages; use `ConstraintViolation.getPropertyPath()` and normalized field errors.

## 16. Common Mistakes When Declaring Groups

1. **Assuming `Default` always runs:** selecting `Create.class` alone does not automatically add `Default`. Pass `Default.class` explicitly if needed.
2. **Confusing `groups={A,B}` with intersection:** the constraint belongs to **both sets**, and runs if either `A` or `B` is requested.
3. **Assigning groups without triggering validation:** you still need `Validator.validate` or a Spring integration point.
4. **Assuming the argument order in `validate(bean, A.class, B.class)` dictates execution order:** not guaranteed; use `@GroupSequence` if needed.
5. **Adding every constraint to every group:** leads to poor maintainability; use a `Common` group, inheritance, or separate DTOs.
6. **Forgetting `@Valid` on associations:** a selected group still will not reach child beans without a cascade path.
7. **Misusing `@ConvertGroup`:** it only makes sense alongside cascaded validation; do not use it to arbitrarily switch groups on scalar fields.
8. **Forgetting to select a group in Spring MVC:** `@Valid @RequestBody` normally requests `Default` only, not `Create`/`Update`.
9. **Assuming `@Validated` and `@Valid` are identical:** Spring's `@Validated` can select groups, whereas Jakarta's `@Valid` marks cascade and validation roots in integrations.
10. **Using a shared DTO to solve authorization:** groups validate data shape/rules, not permissions.
11. **Testing only HTTP 400 status:** without field/path assertions, you do not know which group's constraints actually ran.
12. **Misconfigured provider or namespace:** Spring Boot 3.x uses Jakarta and requires a compatible Bean Validation library.
13. **Treating a group sequence as an OR condition:** a sequence is **ordered evaluation with short-circuiting**, not an arbitrary choice.
14. **Failing to distinguish group validation from business workflow steps:** a request passing `Create` does not mean it is permitted to save or publish.
15. **Ignoring null when group constraints only check non-null values:** many constraints accept `null`; add `@NotNull` to the appropriate group if required.
16. **Assuming a group is runtime state on the object:** groups are **passed at validation time**, not stored as "Create state" on the bean.

## 17. Project Adoption Checklist

1. Write a rules matrix by **action** (`Create`, `Update`, `Publish`) and **property** before choosing annotations.
2. Define groups with marker interfaces; use `groups = A.class` for one group and `groups = {A.class, B.class}` for multiple groups.
3. Remember that constraints without `groups` belong to `Default`; decide whether that group should always be validated.
4. At validation boundaries, select the right groups via `Validator.validate(bean, ...)` or `@Validated(...)` in Spring.
5. When **both** common and operation-specific constraints must run, pass `Default.class` alongside the business group or design explicit group inheritance.
6. Use `@GroupSequence` **only when** ordering/short-circuiting is required; do not rely on ordinary group parameter order.
7. For child beans and collections, check `@Valid`, group propagation, `@ConvertGroup` where applicable, and null behavior.
8. Verify the provider, classpath, method validation mechanism, and distinguish binding errors from constraint violations.
9. Write provider-level tests (JUnit) and integration tests (MockMvc) per action; assert which fields are validated or skipped.
10. Keep authorization, transaction control, and business invariants **outside** validation groups.

### Official References

- [Jakarta Bean Validation 3.0 — Group and group sequence, group inheritance, group conversion](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html).
- [Jakarta Bean Validation API — Default group](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/groups/Default.html).
- [Spring Framework Javadoc — @Validated](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/validation/annotation/Validated.html).
- [Spring Framework — @RequestBody and validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html).
- [Spring Framework — Validation for @RequestMapping methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html).
- [Hibernate Validator 8 Reference Guide — Grouping constraints](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/).
