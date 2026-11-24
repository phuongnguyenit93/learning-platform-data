# Default Group and Declaring Groups Using Interfaces

> **Scope:** Jakarta Bean Validation validation groups, especially the `Default` group, marker interfaces to represent create/update rules, how to assign constraints to groups, and selecting groups at runtime. This article also connects to Spring MVC `@Valid`/`@Validated`, group inheritance, nested validation, and common misconceptions. Standalone examples can be run with Java 17+ and Maven.

## 1. Why Does Bean Validation Need Validation Groups?

The same data object can appear in multiple scenarios. For example, with an account:

- **Create:** requires a name and an invitation code; does not yet have a system-assigned ID.
- **Update:** requires an ID but does not require re-entering the invitation code.
- **Common checks:** some properties always have basic rules, regardless of the operation.

If every constraint ran on every validation call, a create request could fail for missing an ID, while an update request could fail for missing an invitation code. A *validation group* lets you select the set of constraints to apply for an operation without rewriting validator logic.

```text
                          CustomerRequest
                (constraints carry group metadata)
                             │
             ┌───────────────┼────────────────┐
             ▼               ▼                ▼
          Default          OnCreate         OnUpdate
        basic rules      create rules     update rules
             │               │                │
             └───────────────┴────────────────┘
                             │
            Validator.validate(bean, groups...)
                             │
                   ConstraintViolation(s)
```

Group names do not automatically bind to HTTP methods, Java classes, or user permissions: the **caller** must choose the appropriate group when invoking Bean Validation. Default does not mean “all groups”.

## 2. What Is the `Default` Group?

Jakarta Validation defines the standard interface:

```java
jakarta.validation.groups.Default
```

If a constraint **does not specify the `groups` attribute**, that constraint belongs to `Default`. For example:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.groups.Default;

public class ProfileInput {
    @NotBlank
    private String name;

    @NotNull(groups = Default.class)
    private Long ownerId;
}
```

Both fields above belong to the `Default` group. Writing `groups = Default.class` explicitly declares what is already the default. This snippet only illustrates annotations; it is not a Java program with a `main` method.

For an ordinary bean without a customized default group sequence, the following two calls validate the same group:

```java
validator.validate(profile);
validator.validate(profile, Default.class);
```

In the `Validator.validate(T object, Class<?>... groups)` API, when **no group is passed**, the default group is used. This does **not** trigger all constraints assigned to `Create`, `Update`, `Admin`, etc.

Conversely, a constraint written as:

```java
@NotBlank(groups = OnCreate.class)
private String invitationCode;
```

belongs only to `OnCreate`, and **does not automatically still belong to `Default`**. The default value of the `groups` attribute in an annotation definition is an empty array; when you declare custom groups, you replace the default selection with the list you declared.

### 2.1. Behavior Table

| Attached constraint | `validate(bean)` | `validate(bean, Default.class)` | `validate(bean, OnCreate.class)` |
| --- | --- | --- | --- |
| `@NotBlank String name` | Yes | Yes | No, if `OnCreate` does not extend `Default` |
| `@NotNull(groups = Default.class) Long ownerId` | Yes | Yes | No, if there is no group relationship |
| `@NotBlank(groups = OnCreate.class) String invitationCode` | No | No | Yes |
| `@Positive(groups = {Default.class, OnCreate.class}) int quota` | Yes | Yes | Yes |

**Scope note:** The table describes ordinary independent groups. Group inheritance, `@GroupSequence`, and `@ConvertGroup` can expand or change the set of constraints actually evaluated; they must be declared intentionally.

## 3. Creating Validation Groups Using Marker Interfaces

Custom groups are typically **marker interfaces**: empty interfaces that require no implementation and contain no business logic.

```java
public interface OnCreate {
}

public interface OnUpdate {
}
```

If they are two top-level `public` interfaces as above, each interface requires its own Java file (`OnCreate.java`, `OnUpdate.java`). To centralize groups, projects often use a class containing nested interfaces:

**`ValidationGroups.java`**

```java
package demo;

public final class ValidationGroups {
    private ValidationGroups() {
    }

    public interface OnCreate {
    }

    public interface OnUpdate {
    }
}
```

Usage in a constraint:

```java
import jakarta.validation.constraints.NotNull;

@NotNull(groups = ValidationGroups.OnUpdate.class)
private Long id;
```

This snippet shows an illustrative field inside a DTO. Use `ValidationGroups.OnUpdate.class` — a **Class literal**; do not pass a string `"OnUpdate"`, do not instantiate the interface with `new`, and do not create a Spring bean for each group.

### 3.1. A Constraint Can Participate in Multiple Groups

```java
import jakarta.validation.constraints.Positive;
import jakarta.validation.groups.Default;

@Positive(groups = {
    Default.class,
    ValidationGroups.OnCreate.class,
    ValidationGroups.OnUpdate.class
})
private Integer quota;
```

A constraint like the one above runs when any of the listed groups is requested. You can also list only `OnCreate.class` and `OnUpdate.class` without `Default.class` if business requirements call for it.

Do not attach the same annotation multiple times just to specify multiple groups if you can put the groups into **a single `groups` attribute**; doing so avoids duplicate constraints and keeps the model clear.

## 4. Selecting Groups When Calling `Validator`

Basic invocation patterns:

```java
validator.validate(bean); // Default
validator.validate(bean, Default.class); // Explicit Default
validator.validate(bean, ValidationGroups.OnCreate.class);
validator.validate(bean, ValidationGroups.OnUpdate.class);
validator.validate(bean,
        Default.class, ValidationGroups.OnCreate.class);
```

**Passing multiple groups** instructs the provider to validate the selected groups; there is no guarantee that a group earlier in the list will always finish before a later group. Intentional ordering is the subject of `@GroupSequence`.

`Validator.validate(...)` returns a `Set<ConstraintViolation<T>>`. A `Set` has no guaranteed ordering by contract; when printing or comparing in tests, sort the necessary attributes. `getMessage()` can be affected by locale; prefer `getPropertyPath()` and the annotation type when making technical assertions.

### 4.1. Runnable Java 17+ Standalone Example

The following example demonstrates that `Default` and `OnCreate`/`OnUpdate` **are not implicitly merged**, that a constraint can belong to two groups, and that one group can inherit from another.

Project structure:

```text
bean-validation-groups/
├── pom.xml
└── src/main/java/demo/ValidationGroupsDemo.java
```

**`pom.xml`**: uses the Spring Boot starter as the source for the Jakarta Validation API and Hibernate Validator; the Java `main` program does not start a Spring application context.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>bean-validation-groups</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/ValidationGroupsDemo.java`**:

```java
package demo;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.groups.Default;

import java.util.List;
import java.util.Set;

public class ValidationGroupsDemo {
    public interface OnCreate {
    }

    public interface OnUpdate {
    }

    // Review extends OnCreate. When validating Review,
    // constraints belonging to OnCreate are also evaluated.
    public interface Review extends OnCreate {
    }

    static final class Customer {
        @NotBlank
        private final String name; // Default group

        @NotNull(groups = OnCreate.class)
        private final String invitationCode;

        @NotNull(groups = OnUpdate.class)
        private final Long id;

        @Positive(groups = {OnCreate.class, OnUpdate.class})
        private final int quota;

        Customer(String name, String invitationCode,
                 Long id, int quota) {
            this.name = name;
            this.invitationCode = invitationCode;
            this.id = id;
            this.quota = quota;
        }
    }

    public static void main(String[] args) {
        Customer invalid = new Customer("", null, null, 0);
        Customer valid = new Customer("Lan", "INV-01", 7L, 2);

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            show(validator, "implicitDefault", invalid);
            show(validator, "explicitDefault", invalid,
                    Default.class);
            show(validator, "create", invalid,
                    OnCreate.class);
            show(validator, "update", invalid,
                    OnUpdate.class);
            show(validator, "defaultPlusCreate", invalid,
                    Default.class, OnCreate.class);
            show(validator, "reviewInherited", invalid,
                    Review.class);
            show(validator, "validAll", valid,
                    Default.class, OnCreate.class, OnUpdate.class);
        }
    }

    private static void show(Validator validator, String label,
                             Customer bean, Class<?>... groups) {
        Set<ConstraintViolation<Customer>> violations =
                validator.validate(bean, groups);

        List<String> fields = violations.stream()
                .map(v -> v.getPropertyPath().toString() + ":"
                        + v.getConstraintDescriptor()
                                .getAnnotation()
                                .annotationType()
                                .getSimpleName())
                .sorted()
                .toList();

        System.out.println(label + " -> " + fields);
    }
}
```

Run in the directory containing `pom.xml`, requiring Maven and JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ValidationGroupsDemo
```

**Lines printed by the program** (excluding auxiliary Maven/provider logs):

```text
implicitDefault -> [name:NotBlank]
explicitDefault -> [name:NotBlank]
create -> [invitationCode:NotNull, quota:Positive]
update -> [id:NotNull, quota:Positive]
defaultPlusCreate -> [invitationCode:NotNull, name:NotBlank, quota:Positive]
reviewInherited -> [invitationCode:NotNull, quota:Positive]
validAll -> []
```

Because `Customer invalid` has `name=""`, `invitationCode=null`, `id=null`, and `quota=0`:

1. Passing no group means validating `Default` → only `name:NotBlank`.
2. Passing `OnCreate.class` → validates `invitationCode` and `quota`; **does not automatically validate `name`**.
3. Passing `OnUpdate.class` → validates `id` and `quota`.
4. Passing both `Default.class` and `OnCreate.class` → produces violations from both groups.
5. `Review extends OnCreate` → inherits constraints from `OnCreate`, does not automatically include `Default`.
6. `Customer valid` is valid across all three groups.

The program does not print message text (which may be localized) and sorts by field/constraint name so it does not depend on `Set` iteration order. The factory created by the program is closed via `try-with-resources`; the `Validator` obtained from the factory is reused within the same lifecycle.

### 4.2. Mini Exercise: Adding `Default` to the Create Group

Try changing the annotation on `name` in `Customer` to:

```java
@NotBlank(groups = {Default.class, OnCreate.class, OnUpdate.class})
private final String name;
```

After the change, validating `OnCreate` or `OnUpdate` also detects an empty `name`. If you replace it with `groups = OnCreate.class` **while omitting `Default.class`**, `name` is no longer validated under `Default`. This is how you verify the relationship between the `groups` list and the default group.

## 5. Validation Group Inheritance Using `extends`

Like other Java interfaces, marker interfaces can inherit from one another:

```java
public interface BasicChecks {
}

public interface DetailedChecks extends BasicChecks {
}
```

When calling `validate(bean, DetailedChecks.class)`, the provider evaluates constraints in `DetailedChecks` **and** `BasicChecks`. Conversely, requesting `BasicChecks.class` does not include constraints belonging only to `DetailedChecks`.

| Group selected during validation | Constraint in `BasicChecks` | Constraint in `DetailedChecks` |
| --- | --- | --- |
| `BasicChecks.class` | Yes | No |
| `DetailedChecks.class` | Yes, via inheritance | Yes |

This also allows a custom group to **extend `Default`** if the application genuinely wants to include default constraints:

```java
import jakarta.validation.groups.Default;

public interface OnCreateIncludingDefault extends Default {
}
```

When `OnCreateIncludingDefault.class` is selected, constraints belonging to `Default` are also included in the same validation pass. However, **not every group interface should automatically extend `Default`**. Choosing the right groups and inheritance model must be determined by the application's contract.

**Inheritance does not imply ordering.** It includes the parent group, but does not guarantee that parent-group constraints always finish before child-group constraints; if you need fail-fast ordering, use `@GroupSequence`.

## 6. Distinguishing `@Valid` and `@Validated` in Spring MVC

Spring Framework integrates Jakarta Bean Validation through adapter classes such as `LocalValidatorFactoryBean`. With Spring Boot 3.x and `spring-boot-starter-validation`, you usually do not have to bootstrap a factory manually in controllers.

Two commonly encountered annotations:

- `jakarta.validation.Valid` (Jakarta standard) indicates cascading validation and is supported by Spring MVC to trigger argument validation; when no other group instruction is given, **the `Default` group** is the normal choice.
- `org.springframework.validation.annotation.Validated` (from Spring) allows **group selection**: `@Validated(ValidationGroups.OnCreate.class)` or `@Validated({A.class, B.class})`.

### 6.1. Illustrative Classes in Spring Boot Web MVC

The following code requires a Spring Boot 3 project with Spring Web MVC, starter-validation, and the corresponding files. This is an integration example, **not** the standalone `main` program in section 4.

**`ValidationGroups.java`**:

```java
package demo;

public final class ValidationGroups {
    private ValidationGroups() {
    }

    public interface OnCreate {}
    public interface OnUpdate {}
}
```

**`CustomerRequest.java`**:

```java
package demo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.groups.Default;

public record CustomerRequest(
    @NotBlank(groups = {
        Default.class,
        ValidationGroups.OnCreate.class,
        ValidationGroups.OnUpdate.class
    })
    String name,

    @NotBlank(groups = ValidationGroups.OnCreate.class)
    String invitationCode,

    @NotNull(groups = ValidationGroups.OnUpdate.class)
    Long id
) {
}
```

**`CustomerController.java`**:

```java
package demo;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CustomerController {
    @PostMapping("/customers")
    public ResponseEntity<Void> create(
            @Validated(ValidationGroups.OnCreate.class)
            @RequestBody CustomerRequest request) {
        return ResponseEntity.noContent().build();
    }

    @PutMapping("/customers")
    public ResponseEntity<Void> update(
            @Validated(ValidationGroups.OnUpdate.class)
            @RequestBody CustomerRequest request) {
        return ResponseEntity.noContent().build();
    }
}
```

| Request after deserializing into DTO | Group executed | Constraint outcome |
| --- | --- | --- |
| Create, `name=""` | `OnCreate` | Violates `@NotBlank` on `name` |
| Create, `invitationCode=""` | `OnCreate` | Violates `@NotBlank` on invitation code |
| Create, `id=null` | `OnCreate` | No violation on `id` (since `id` belongs to `OnUpdate`) |
| Update, `id=null` | `OnUpdate` | Violates `@NotNull` on `id` |
| Update, `invitationCode=null` | `OnUpdate` | No violation on invitation code (since it only belongs to `OnCreate`) |
| Update, `name=""` | `OnUpdate` | Violates `@NotBlank` on `name` |

Place `name` in all three groups so it is validated on create, update, and default. If you only put `@NotBlank` without `groups`, then `@Validated(OnCreate.class)` **will not automatically** validate `name`, unless the group is designed to extend `Default` or is passed alongside `Default.class`.

In typical Spring MVC applications, `@Validated @RequestBody` failures are turned into validation errors / HTTP 400 if there is no corresponding `BindingResult` handling. However, **malformed JSON, missing data in strict deserialization mode, or type conversion failures** may be handled by Jackson/message converters *before* Bean Validation runs. Do not assume every HTTP 400 is a `ConstraintViolation`.

### 6.2. Why Does `@Valid` Sometimes “Miss Errors”?

If a controller uses:

```java
public ResponseEntity<Void> create(
        @Valid @RequestBody CustomerRequest request) {
    // ...
}
```

and has no other way to select groups, Spring validates `Default`. At that point `name` runs, but `invitationCode`—which only belongs to `OnCreate`—**is not validated**. This is a common bug when a DTO has `groups=OnCreate.class` attached, yet the endpoint only uses `@Valid`.

The fix is to select the group explicitly with `@Validated(OnCreate.class)` (or a complete marker group) and write request tests confirming that the required constraints actually run. Do not treat the presence of an annotation as proof that it executed.

### 6.3. Method Validation Differs from Request Body Validation

Spring also uses `@Validated` on beans/services to support method validation via AOP/interceptors for constraints on parameters and return values. That execution path differs from Spring MVC argument validation. For example, *self-invocation* from one method to another on the same object may bypass the proxy. Always test the actual entry point and mechanism instead of assuming `@Validated` in any single place applies to every call.

## 7. Groups in Nested Validation (`@Valid` and `@ConvertGroup`)

A group selected on the root bean can **propagate to child beans** when the provider cascades via `@Valid`:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class OrderRequest {
    @Valid
    private Address address;
}

public class Address {
    @NotBlank
    private String street; // Default

    @NotNull(groups = ValidationGroups.OnCreate.class)
    private String deliveryCode; // OnCreate
}
```

These are two illustrative classes; when creating actual Java files, each `public` class must reside in a file of the same name. If you call `validate(order, OnCreate.class)`:

- If `address` is non-null, validation cascades to `Address` using the `OnCreate` group.
- `deliveryCode` is evaluated; `street` belongs only to `Default` and therefore does not run automatically.
- `@Valid` **does not forbid null on its own**: if `address=null` is disallowed, add `@NotNull` in the required group.

If you want to switch groups **only on a specific cascade edge**, Jakarta Validation provides `@ConvertGroup`:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

public class CheckoutRequest {
    @Valid
    @ConvertGroup(
        from = Default.class,
        to = ValidationGroups.OnCreate.class
    )
    private Address address;
}
```

When validating `Default` and descending into `address` through `@Valid`, the group on that branch is converted to `OnCreate`. Do not use `@ConvertGroup` as a substitute for selecting the right group at the controller or `validate` call; conversion only makes sense on the appropriate cascade point.

Similarly, constraints inside containers also obey groups:

```java
Map<
    @NotBlank(groups = ValidationGroups.OnCreate.class) String,
    @Valid Address> addresses;
```

The `Map` example above requires the corresponding imports and DTO to compile. The constraint on the key only runs when the `OnCreate` group is selected; `@Valid` on the value determines whether constraints inside the `Address` bean are validated, following the active group propagation rules.

## 8. `@GroupSequence` for Ordering, Unlike Plain Marker Interfaces

When calling:

```java
validator.validate(bean, Default.class, OnCreate.class);
```

the provider selects both groups, but **there is no guarantee of evaluation order**. If you want to check the basic group first and only proceed when the earlier group is valid, you can define a **group sequence**:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

@GroupSequence({Default.class, ValidationGroups.OnCreate.class})
public interface CompleteCreate {
}
```

The snippet above is an interface definition in `CompleteCreate.java`, with `ValidationGroups` already existing. When calling:

```java
validator.validate(bean, CompleteCreate.class);
```

the provider evaluates `Default` first; if there are violations, the sequence does not continue to `OnCreate`. Only if there are no errors in the first step will `OnCreate` be validated.

**Do not confuse the two uses of `@GroupSequence`:** When redefining the *default group sequence of a class itself* by annotating that class, the sequence must contain **that class itself**; you cannot arbitrarily write only `Default.class` in place of the class name. Violating this can cause a `GroupDefinitionException`. This is an advanced mechanism; for simple create/update needs, declaring marker interfaces and selecting the right group is usually easier to maintain.

## 9. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Thinking `Default` means all constraints | Constraints belonging only to custom groups do not run | Select the right group or list `Default.class` alongside custom groups |
| Writing `groups=OnCreate.class` and thinking it still belongs to `Default` | The constraint does not automatically participate in `Default` | Explicitly list multiple groups if needed |
| Using only `@Valid` on POST when the DTO uses `OnCreate` | Create-only constraints are skipped | Use `@Validated(OnCreate.class)` |
| Using only `@Validated(OnCreate.class)` when `name` only belongs to `Default` | Common rules are missed | Add `name` to `OnCreate` or design group inheritance/sequence |
| Declaring marker interfaces with unnecessary logic or methods | Group model becomes confusing | Use empty interfaces with clear business names |
| Passing the string `"Create"` instead of `Create.class` | Does not match the group API | Use a `Class<?>` literal |
| Making `Child extends Parent` and thinking `validate(Parent.class)` runs `Child` too | Inheritance direction understood backwards | Select the child group to also evaluate parent-group constraints |
| Passing two groups to force execution order | Order is not guaranteed | Use `@GroupSequence` |
| Defining an invalid group sequence when redefining a class's default | Group definition error | The class itself must appear in its own sequence |
| Forgetting `@Valid` on a child bean | Rules inside the child bean do not cascade | Add `@Valid` on the right property or container element |
| Having `@Valid` and thinking all groups on the child bean run | The current group is propagated, not all groups by default | Check group propagation and `@ConvertGroup` if needed |
| Using `@ConvertGroup` without `@Valid` | Converting groups on a non-cascading point is invalid | Attach conversion to the proper cascade edge |
| Missing a Jakarta Validation provider | Annotations may exist but not execute as expected | Add `spring-boot-starter-validation` or a compatible provider |
| Using `javax.validation.*` with Spring Boot 3 | Wrong Jakarta namespace | Use `jakarta.validation.*` |
| Asserting on violation order or full message text | Tests easily break across locales/providers | Sort or compare constraint/property-path sets |

### When to Use Separate DTOs Instead of Too Many Groups

If create and update APIs differ significantly in structure, separate `CreateCustomerRequest` and `UpdateCustomerRequest` classes can be easier to read and test than a single DTO maintaining dozens of groups. Groups are useful when **model reuse is intentional** and the difference lies only in the set of constraints to validate.

Groups also do not replace authorization, database checks, or service-layer business rules. A request can pass Bean Validation and still not be permitted to update a record, or vice versa.

## 10. Testing Workflow and Checklist

Verify step by step:

1. **Identify metadata:** constraints without `groups` = `Default`; if custom groups are specified, inspect the actual list.
2. **Identify the caller:** direct `Validator.validate(...)`, Spring MVC `@Valid` or `@Validated(...)`, method validation, or a scheduled job.
3. **Check group relationships:** does the marker interface `extends` a parent group, `Default`, or participate in `@GroupSequence`?
4. **Check nested beans:** is `@Valid` placed on the path down to child objects? Is `@ConvertGroup` present?
5. **Separate binding errors:** did data enter the DTO with the right types before validation ran?
6. **Write a test matrix:** one object violating only `Default`, one violating only `OnCreate`, one violating both, and one valid object.

Implementation checklist:

- [ ] Are `Default` and custom groups defined according to the exact business scope?
- [ ] Are marker interfaces free of unnecessary logic?
- [ ] Is there a test verifying that `validate(bean)` is equivalent to `validate(bean, Default.class)` under standard configuration?
- [ ] Is there a test verifying that `validate(bean, OnCreate.class)` **does not automatically include `Default`**?
- [ ] Are constraints shared across multiple operations assigned to all required groups?
- [ ] Is group inheritance used intentionally and tested in the right direction?
- [ ] Is Spring MVC using `@Validated(Groups.X.class)` when group X is needed, rather than just `@Valid`?
- [ ] Do child DTOs have `@Valid` in the right places and tests for group propagation?
- [ ] If ordering is required, is `@GroupSequence` used instead of parameter order?
- [ ] Are assertions independent of `Set<ConstraintViolation>` order and localized message text?

**Conclusion:** `Default` is the standard group for constraints that do not declare `groups`, **not the union of all groups**. Custom groups are represented by **marker interfaces**, attached to constraints via `groups = MyGroup.class`, and selected when calling `validate(bean, MyGroup.class)` or using `@Validated(MyGroup.class)` in Spring. Inheritance, sequences, and cascades must be designed explicitly to avoid assuming groups accumulate automatically.

### Official References

- [Jakarta Bean Validation 3.0 Specification — Groups, Group Inheritance, Group Sequence](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jakarta Validation Default group — Platform 10 API](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/validation/groups/default)
- [Hibernate Validator 8 Reference Guide — Grouping Constraints](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
