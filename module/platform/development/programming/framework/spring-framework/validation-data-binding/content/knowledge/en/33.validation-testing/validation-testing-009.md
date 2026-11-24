# Testing Custom Constraints, Groups, and Cascaded Validation in Jakarta Bean Validation

## 1. Three mechanisms that must be tested independently

In Spring Framework, Bean Validation is commonly integrated via `LocalValidatorFactoryBean`, with Hibernate Validator as a popular Jakarta Validation provider. When an object is validated, three questions should be separated:

1. **Custom constraint:** Does an application-defined rule return the right result for valid values, malformed values, blank strings, and `null`?
2. **Validation groups:** When validating with group `Draft` or `Publish`, do only constraints belonging to that group run? How does the default `Default` group behave?
3. **Cascaded validation:** Are constraints on nested objects or collection elements evaluated via `@Valid`? When transitioning from a parent object to a child object requires switching groups, does `@ConvertGroup` work properly?

These are three **distinct** layers of responsibility. A correctly written custom validator may still fail to run if its group does not match. Valid annotations on a child object may be skipped if `@Valid` is missing. Conversely, a `@GroupSequence` can intentionally skip later groups when an earlier group fails.

This lesson uses **Java 17, Jakarta Validation 3.0, Hibernate Validator 8, and JUnit 5**, with a standalone runnable Maven program. No Spring Boot, HTTP server, or database is needed to exercise Bean Validation logic. The final sections explain integration with Spring MVC `@Valid` and `@Validated`.

## 2. Key APIs and annotations

| Component | Role | What to observe in tests |
| --- | --- | --- |
| `jakarta.validation.Constraint` | Marks an annotation as a Bean Validation constraint | `validatedBy` points to the right validator |
| `ConstraintValidator<A,T>` | Implements custom constraint logic | `initialize(...)`, `isValid(value, context)` |
| `Validator#validate(bean, groups...)` | Validates an object and graph against selected groups | Set of `ConstraintViolation` |
| `Validator#validateProperty(...)` | Validates a single property on an object directly | **Does not cascade** into nested objects |
| `Validator#validateValue(...)` | Validates a hypothetical property value without an instance | Used to unit-test a constraint |
| `ConstraintViolation#getPropertyPath()` | Path to the failing field | `sku`, `recipient.email` |
| `ConstraintViolation#getConstraintDescriptor()` | Metadata of the violated constraint | Identifies exact annotation e.g., `ValidSku.class` |
| `@Valid` | Enables cascaded validation | Violations inside child objects/collection elements |
| `groups = ...` | Assigns a constraint to one or more groups | Default, Draft, Publish, Contact |
| `@GroupSequence` | Enforces group evaluation order | Later groups do not run if an earlier group fails |
| `@ConvertGroup` | Converts groups across a **cascade edge** | Publish on parent → Contact on child |
| `ValidationMessages.properties` | Resolves constraint message templates | `getMessageTemplate()` and `getMessage()` |

By default, `validator.validate(bean)` uses `jakarta.validation.groups.Default`. Calling `validator.validate(bean, Publish.class)` **does not automatically run all default constraints**; that only happens if group inheritance or a group sequence requires it.

## 3. Designing the illustrative problem

An `Item` record/class has the following rules:

- `id` is always required in the **Default** group.
- `title` is required in the **Draft** group when drafting.
- `sku` is required and must match a pattern like `AB-123` in the **Publish** group.
- `stock` must be positive in the **Publish** group.
- `recipient` must be non-null in the **Publish** group.
- Inside `recipient`, `name` must be present and `email` well-formed, but those constraints belong to a separate **Contact** group.
- The cascade edge from `Item.recipient` is configured with `@ConvertGroup(from=Publish.class,to=Contact.class)` so that publishing an item also checks contact rules.
- Sequence group `Ready` runs **Draft then Publish**, stopping after Draft if errors exist.

We use an intentionally invalid input:

```text
id        = ""
title     = ""
sku       = "bad-9"
stock     = 0
recipient = { name: "", email: "not-email" }
```

When validating each group independently, results must differ:

| Group passed to validate | Failing fields |
| --- | --- |
| No group passed (Default) | `id` |
| `Draft` | `title` |
| `Publish` | `sku`, `stock`, `recipient.name`, `recipient.email` |
| `Ready` (Draft → Publish) | Only `title` because Draft fails |
| `Ready` after fixing title | Remaining Publish errors if still invalid |

Tests must compare the **set of paths** or structured constraint metadata rather than relying on arbitrary iteration order of `Set<ConstraintViolation<?>>`.

## 4. Creating a custom constraint by convention

To validate SKUs, we define the `@ValidSku` annotation.

Required elements of a standard Bean Validation constraint annotation:

```java
@Documented
@Constraint(validatedBy = SkuValidator.class)
@Target({
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidSku {

    String message() default "{demo.sku.invalid}";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

This is an **excerpt from the full program in section 9**. When declared as a top-level public annotation, the file must be named `ValidSku.java`; in the sample program, it is nested inside `ValidationLab.java` to keep the file count small.

Explanation:

- `@Constraint(validatedBy=SkuValidator.class)` links the annotation to its implementation.
- `@Retention(RUNTIME)` allows the provider to read the annotation via reflection during validation.
- `@Target(...)` restricts where the annotation can be placed.
- `message()` is the message template; use a key that is easy to localize.
- `groups()` is the group list. **The default must be an empty array**; omitting `groups` places the constraint in `Default`.
- `payload()` carries extension metadata; never use it to make authentication/authorization decisions.

### 4.1. ConstraintValidator: null is normally considered valid

Implementation:

```java
public static final class SkuValidator
        implements ConstraintValidator<ValidSku, String> {

    private static final Pattern PATTERN =
        Pattern.compile("[A-Z]{2}-[0-9]{3}");

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {

        return value == null || PATTERN.matcher(value).matches();
    }
}
```

**Why is `null` treated as valid?** A format-checking custom constraint should generally only answer "if a SKU is present, does it match the pattern?". Whether the SKU is required should be checked independently with `@NotNull` or `@NotBlank`. This keeps the constraint reusable for optional fields.

When `@NotBlank` and `@ValidSku` are placed on the same field:

- `sku=null`: `@NotBlank` fails, `@ValidSku` accepts `null`.
- `sku=""`: `@NotBlank` fails; `@ValidSku` may also fail because an empty string does not match the regex. **Two violations** may be produced, and tests should decide whether that is intended.
- `sku="bad-9"`: not blank, but wrong pattern → only `@ValidSku` fails.
- `sku="AB-123"`: both pass.

If you want strictly one error for an empty string, the custom constraint can ignore blank values and leave them to `@NotBlank`, though that alters the constraint's contract and must be documented in tests. The main example keeps the regex simple and uses non-empty invalid input to test `ValidSku` in isolation.

### 4.2. initialize() and state/thread safety

`ConstraintValidator#initialize(annotation)` is an optional hook to read annotation attributes, such as `@ValidSku(prefix="AB")` in another design. With the fixed regex here, overriding `initialize()` is unnecessary.

Providers may cache and reuse validator instances. Never store request-specific values, principals, or `ConstraintValidatorContext` in instance fields across calls. A shared immutable `Pattern` is safe; `Matcher` is created per call and never shared across threads.

### 4.3. Writing custom violations on child fields

For a class-level constraint checking multiple fields, you can build a custom field path:

```java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        "{demo.range.invalid}")
    .addPropertyNode("endDate")
    .addConstraintViolation();
```

This is an **illustrative fragment** inside `ConstraintValidator#isValid` for a class-level constraint, not part of the runnable program. Once disabling the default violation, you must add a new violation when validation fails. Never interpolate untrusted user data directly into EL/message templates.

## 5. Validation groups: selecting the right subset of constraints

Jakarta Bean Validation groups are represented by interfaces:

```java
public interface Draft {}
public interface Publish {}
public interface Contact {}
```

This is an illustrative fragment; in the runnable example, the interfaces live inside `ValidationLab.Groups`.

When declared as:

```java
@NotBlank
private String id;

@NotBlank(groups = Draft.class)
private String title;

@ValidSku(groups = Publish.class)
private String sku;
```

We have:

- `@NotBlank` on `id` belongs to `Default` since no `groups` are specified.
- `@NotBlank(groups=Draft.class)` on `title` belongs to Draft.
- `@ValidSku(groups=Publish.class)` on `sku` belongs to Publish.

Calling:

```java
validator.validate(item);
validator.validate(item, Draft.class);
validator.validate(item, Publish.class);
validator.validate(
    item, Default.class, Draft.class, Publish.class);
```

These four calls have distinct semantics. When passing multiple groups in a single validate call, there is **no guaranteed evaluation order** among those groups. Do not rely on varargs argument order to build a "before–after" workflow; use `@GroupSequence`.

### 5.1. Group inheritance

If you write:

```java
public interface Publish extends Draft {}
```

then Publish inherits Draft's constraints per group-inheritance rules. In the demo project, the three groups are independent so tests can separate them clearly. **Do not** assume Publish automatically includes Draft unless you explicitly declare that inheritance.

### 5.2. Default does not run automatically when another group is selected

A common design mistake:

```java
validator.validate(item, Publish.class);
```

while expecting every ungrouped `@NotBlank` to be checked. By default they belong to `Default`, not automatically to Publish. If a rule must run in both, declare:

```java
@NotBlank(groups = {Default.class, Publish.class})
private String id;
```

or use a sequence/group inheritance as designed. Test both paths to avoid skipping "always required" constraints.

### 5.3. Validation groups are not roles or access permissions

Naming a group `AdminChecks` does not verify the caller is an admin. Groups only select **which constraint subset runs**; resource and field authorization belong at the Spring Security/service/domain boundary. Even if validation under `AdminChecks` passes, a user is not authorized to change roles merely because the DTO is valid.

## 6. Group sequence: ordered and short-circuiting

A sequence:

```java
@GroupSequence({Draft.class, Publish.class})
public interface Ready {}
```

When calling:

```java
validator.validate(item, Ready.class);
```

the provider must:

1. Run all constraints belonging to Draft.
2. If Draft has **any** violation, **skip Publish** for that sequence pass.
3. If Draft passes, run Publish.

**There is no guaranteed order among constraints within the same group.** A sequence only enforces order **between groups**, not among fields/validators inside a group.

For an item with an empty title and invalid SKU, `Ready` reports only `title`; that does not mean SKU has been confirmed valid. Once title is fixed, re-validating surfaces the remaining Publish errors.

### 6.1. Group sequence pitfalls

- Never declare cyclic group sequences. Circular dependencies can trigger `GroupDefinitionException`.
- An interface defining a sequence should not simultaneously extend another group interface.
- Do not attach constraints directly to a marker interface acting as a sequence and assume they behave like a regular group.
- When redefining the default sequence directly on a class, Jakarta rules generally require including **the class itself** in the sequence; a redefined `Default` sequence is scoped locally to that class and does not propagate the full sequence down to child objects.
- If you want all errors reported simultaneously, do not use a sequence since short-circuiting is intentional.

### 6.2. Testing true short-circuit behavior

Tests should not just count errors; they must prove **Publish violations do not appear** when Draft fails:

```java
Set<ConstraintViolation<Item>> violations =
    validator.validate(item, Ready.class);

assertEquals(Set.of("title"), paths(violations));
```

This is a JUnit fragment requiring the `paths(...)` helper and model from section 9. With a valid `title`, test again and confirm Publish errors then appear.

## 7. Cascaded validation: @Valid is not a constraint

A parent object holding a child object:

```java
public class Item {
    @Valid
    private Recipient recipient;
}

public class Recipient {
    @NotBlank
    private String name;
}
```

This is an illustrative fragment, not a standalone file. When validating `Item` with the appropriate group, `@Valid` lets the provider **descend into `Recipient`** and check constraints there.

Key points:

- Without `@Valid`: validating Item **does not automatically traverse the entire object graph**.
- `@Valid` itself **is not a constraint** and never creates its own "cascaded" violation.
- If `recipient` is `null`, cascading **skips it**; place `@NotNull` on the reference if the child object is mandatory.
- If `recipient` is present, its constraints must belong to the **active group** or a converted group.
- Object graphs with cyclic references have infinite-loop protection per the Bean Validation spec; do not write custom validators that recursively walk object graphs unchecked.
- On collections, you can use `List<@Valid Recipient>` to validate each element (container element cascading); avoid placing `@Valid` on both the container and type argument "just in case", as that risks redundant processing.

### 7.1. Without @Valid, tests must prove cascading does not happen

A wrapper:

```java
public static final class WithoutCascade {
    private final Recipient recipient;

    public WithoutCascade(Recipient recipient) {
        this.recipient = recipient;
    }
}
```

If an invalid `Recipient` is placed inside, `validator.validate(wrapper, Contact.class)` detects no errors on Recipient's fields because the field lacks `@Valid`.

This is not a provider bug; it is the contract of cascaded validation. Test both **with** and **without** `@Valid` so a missing `@Valid` is never mistaken for a broken validator.

### 7.2. @Valid and missing child object

A field:

```java
@NotNull(groups = Publish.class)
@Valid
private Recipient recipient;
```

when `recipient == null` and validated under Publish produces only a violation from `@NotNull`. There are no `recipient.name` or `recipient.email` errors because no child instance exists to inspect.

If a property is optional by business rules, `@Valid` alone makes sense; if mandatory, add `@NotNull` with the right group.

### 7.3. Cascaded validation across collections

Example:

```java
public class ContactBatch {
    private List<@Valid Recipient> contacts;
}
```

With Hibernate Validator 8/Jakarta Validation 3, a `List` uses standard value extractors to validate each `Recipient` element. Property paths include indexes like `contacts[0].email`.

When testing collections, **do not rely on Set iteration order**. Assert structured field paths or container element nodes, and deliberately introduce an invalid element to verify.

## 8. Converting groups during cascade with @ConvertGroup

Suppose `Item` is validated under group `Publish`, while `Recipient` defines its constraints under group `Contact`. With `@Valid` alone, Publish propagates down to Recipient, so `@NotBlank(groups=Contact.class)` would not run.

Declaration:

```java
@NotNull(groups = Publish.class)
@Valid
@ConvertGroup(from = Publish.class, to = Contact.class)
private Recipient recipient;
```

When validating `Item` with Publish, the provider crosses the `recipient` edge, converts **Publish → Contact**, and validates `Recipient` under `Contact`. Other properties of `Item` do not switch groups: `sku` and `stock` are still validated under `Publish`.

Rules to remember:

- `@ConvertGroup` is valid only alongside `@Valid`; otherwise the provider may throw `ConstraintDeclarationException`.
- `from` must be a regular group, **not a group sequence**.
- You cannot declare two conversion rules with the same `from` on one element.
- Conversions **do not chain transitively**: A→B and B→C on the same edge will not automatically turn A into C.
- A group sequence is **expanded** before applying cascade-edge conversion; thus sequence `Ready` containing `Publish` still triggers `Publish→Contact` when evaluating the `Publish` step.
- On a `null` reference, no nested validation runs; conversion never creates a child object.

### 8.1. Test proving group conversion occurred

When validating Publish produces violations for `recipient.email` and `recipient.name`, that indicates the Contact group ran on Recipient. To prove causality, Recipient's constraints must belong exclusively to Contact, not Publish/Default.

A stronger test than counting total errors is comparing the **set of property paths**:

```text
recipient.email
recipient.name
sku
stock
```

Without `@ConvertGroup` or when passing the wrong group, the violation set differs. Never use overly broad assertions like `hasErrors() == true`, because a `sku` error can hide the fact that Recipient was never validated at all.

## 9. Standalone runnable Java 17 project

The complete example uses one model/constraint file, one JUnit test file, one message bundle, and Maven. Classes inside `ValidationLab.java` are nested so learners can run it without creating many separate Java files.

### 9.1. Project structure

```text
constraint-groups-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/ValidationLab.java
    │   └── resources/ValidationMessages.properties
    └── test/
        └── java/demo/ValidationLabTest.java
```

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>demo</groupId>
  <artifactId>constraint-groups-lab</artifactId>
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
      <groupId>org.glassfish</groupId>
      <artifactId>jakarta.el</artifactId>
      <version>4.0.2</version>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.12.2</version>
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
    </plugins>
  </build>
</project>
```

Hibernate Validator 8 is the provider for Jakarta Bean Validation 3.0; Jakarta EL support is required for certain message-interpolation scenarios. Tests do not need a Spring Boot starter because they exercise **Jakarta Validator** directly.

### 9.3. ValidationMessages.properties

```properties
demo.sku.invalid=SKU code must match AB-123 (two uppercase letters and three digits)
```

The provider interpolates `{demo.sku.invalid}` into the message. To keep tests stable across locales, the JUnit suite primarily asserts annotation types and field paths rather than built-in constraint translations.

### 9.4. ValidationLab.java

```java
package demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Payload;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.GroupSequence;

public class ValidationLab {

    private ValidationLab() {
    }

    public static final class Groups {
        private Groups() {
        }

        public interface Draft {}
        public interface Publish {}
        public interface Contact {}

        @GroupSequence({Draft.class, Publish.class})
        public interface Ready {}
    }

    @Documented
    @Constraint(validatedBy = SkuValidator.class)
    @Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.ANNOTATION_TYPE,
        ElementType.TYPE_USE
    })
    @Retention(RetentionPolicy.RUNTIME)
    public @interface ValidSku {
        String message() default "{demo.sku.invalid}";
        Class<?>[] groups() default {};
        Class<? extends Payload>[] payload() default {};
    }

    public static final class SkuValidator
            implements ConstraintValidator<ValidSku, String> {

        private static final Pattern SKU =
            Pattern.compile("[A-Z]{2}-[0-9]{3}");

        @Override
        public boolean isValid(
                String value,
                ConstraintValidatorContext context) {

            // Null is delegated to @NotNull/@NotBlank.
            return value == null || SKU.matcher(value).matches();
        }
    }

    public static final class Recipient {

        @NotBlank(groups = Groups.Contact.class)
        private final String name;

        @NotBlank(groups = Groups.Contact.class)
        @Email(groups = Groups.Contact.class)
        private final String email;

        public Recipient(String name, String email) {
            this.name = name;
            this.email = email;
        }

        public String getName() {
            return name;
        }

        public String getEmail() {
            return email;
        }
    }

    public static final class Item {

        // No groups specified => Default group.
        @NotBlank
        private final String id;

        @NotBlank(groups = Groups.Draft.class)
        private final String title;

        @NotBlank(groups = Groups.Publish.class)
        @ValidSku(groups = Groups.Publish.class)
        private final String sku;

        @Positive(groups = Groups.Publish.class)
        private final int stock;

        @NotNull(groups = Groups.Publish.class)
        @Valid
        @ConvertGroup(
            from = Groups.Publish.class,
            to = Groups.Contact.class
        )
        private final Recipient recipient;

        public Item(
                String id,
                String title,
                String sku,
                int stock,
                Recipient recipient) {

            this.id = id;
            this.title = title;
            this.sku = sku;
            this.stock = stock;
            this.recipient = recipient;
        }

        public String getId() {
            return id;
        }

        public String getTitle() {
            return title;
        }

        public String getSku() {
            return sku;
        }

        public int getStock() {
            return stock;
        }

        public Recipient getRecipient() {
            return recipient;
        }
    }

    // NO @Valid: Bean Validation does not descend into recipient.
    public static final class WithoutCascade {
        private final Recipient recipient;

        public WithoutCascade(Recipient recipient) {
            this.recipient = recipient;
        }

        public Recipient getRecipient() {
            return recipient;
        }
    }

    // TYPE_USE @Valid: provider descends into each List element.
    public static final class ContactBatch {
        private final List<@Valid Recipient> contacts;

        public ContactBatch(List<Recipient> contacts) {
            this.contacts = contacts;
        }

        public List<Recipient> getContacts() {
            return contacts;
        }
    }

    public static Item invalidItem() {
        return new Item(
            "", "", "bad-9", 0,
            new Recipient("", "not-email"));
    }

    public static Item validItem() {
        return new Item(
            "ITEM-1", "Laptop", "AB-123", 5,
            new Recipient("Lan", "lan@example.test"));
    }

    private static String describe(
            Set<? extends ConstraintViolation<?>> violations) {

        return violations.stream()
            .map(v -> v.getPropertyPath()
                + ":"
                + v.getConstraintDescriptor()
                    .getAnnotation()
                    .annotationType()
                    .getSimpleName())
            .sorted()
            .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                 Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            Item bad = invalidItem();

            System.out.println("DEFAULT="
                + describe(validator.validate(bad)));
            System.out.println("DRAFT="
                + describe(validator.validate(
                    bad, Groups.Draft.class)));
            System.out.println("PUBLISH="
                + describe(validator.validate(
                    bad, Groups.Publish.class)));
            System.out.println("READY="
                + describe(validator.validate(
                    bad, Groups.Ready.class)));

            Item titleFixed = new Item(
                "", "Laptop", "bad-9", 0,
                new Recipient("", "not-email"));

            System.out.println("READY_AFTER_TITLE="
                + describe(validator.validate(
                    titleFixed, Groups.Ready.class)));
            System.out.println("ALL_VALID="
                + validator.validate(
                    validItem(), Groups.Ready.class).isEmpty());
        }
    }
}
```

### 9.5. Why is this model easy to test?

- Fields are `final`, so no binding side effects occur during validation.
- `@ValidSku` belongs only to `Publish`; `id`'s `@NotBlank` belongs to `Default`; the two roles stay cleanly separated.
- Recipient's constraints belong only to `Contact`, so their appearance during `Publish` proves `@ConvertGroup`.
- `@NotNull(groups=Publish.class)` on the reference and `@Valid` solve **two different cases**: whether the child exists and whether it is valid.
- `Groups.Ready` is a sequence from Draft to Publish, not an unordered group set.
- `describe(...)` uses annotation type and property path, sorted before printing. It never depends on localized messages or Set iteration order.
- `ValidatorFactory` is created once for the CLI and closed on exit. Long-lived applications typically reuse a single `ValidatorFactory`/Spring-managed validator instead of recreating it per HTTP request.

### 9.6. Run commands

Requires Java 17+, Maven 3.x. In the directory containing `pom.xml`:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java \
  -Dexec.mainClass=demo.ValidationLab
```

Expected program output, ignoring Maven or Hibernate Validator logging:

```text
DEFAULT=id:NotBlank
DRAFT=title:NotBlank
PUBLISH=recipient.email:Email,recipient.name:NotBlank,sku:ValidSku,stock:Positive
READY=title:NotBlank
READY_AFTER_TITLE=recipient.email:Email,recipient.name:NotBlank,sku:ValidSku,stock:Positive
ALL_VALID=true
```

Line-by-line explanation:

1. **DEFAULT:** checks only `@NotBlank` on `id`; constraints marked Draft/Publish/Contact do not run automatically.
2. **DRAFT:** only the blank title produces a `NotBlank` violation.
3. **PUBLISH:** invalid SKU pattern, stock is 0, Recipient has blank name and invalid email; Contact group ran **via the Publish→Contact conversion**.
4. **READY:** because Draft failed, the Publish step was skipped; no SKU error appears in this pass.
5. **READY_AFTER_TITLE:** Draft passed, so Publish runs and produces the remaining four violations.
6. **ALL_VALID:** valid item satisfies both Draft and Publish (including the Contact cascade), yielding zero violations.

Output is derived from the rules in code and the bundle; run locally to verify on your exact dependency versions, especially if you edit models/groups/constraints.

## 10. JUnit 5: testing each property separately

Save to `src/test/java/demo/ValidationLabTest.java`. Tests share one `ValidatorFactory` for the test class while creating fresh objects per case. Helpers never rely on `Set` iteration order.

### 10.1. ValidationLabTest.java

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.groups.Default;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class ValidationLabTest {

    private static ValidatorFactory factory;
    private static Validator validator;

    @BeforeAll
    static void openFactory() {
        factory = Validation.buildDefaultValidatorFactory();
        validator = factory.getValidator();
    }

    @AfterAll
    static void closeFactory() {
        factory.close();
    }

    private static Set<String> paths(
            Set<? extends ConstraintViolation<?>> errors) {

        return errors.stream()
            .map(v -> v.getPropertyPath().toString())
            .collect(Collectors.toSet());
    }

    @Test
    void customConstraintAcceptsProperSkuAndRejectsBadSku() {
        var good = validator.validateValue(
            ValidationLab.Item.class,
            "sku", "AB-123",
            ValidationLab.Groups.Publish.class);

        assertTrue(good.isEmpty());

        var bad = validator.validateValue(
            ValidationLab.Item.class,
            "sku", "bad-9",
            ValidationLab.Groups.Publish.class);

        assertEquals(1, bad.size());
        var violation = bad.iterator().next();

        assertEquals("sku", violation.getPropertyPath().toString());
        assertEquals(
            ValidationLab.ValidSku.class,
            violation.getConstraintDescriptor()
                .getAnnotation().annotationType());
        assertEquals(
            "{demo.sku.invalid}",
            violation.getMessageTemplate());
    }

    @Test
    void nullSkuIsRejectedByNotBlankNotFormatRule() {
        var errors = validator.validateValue(
            ValidationLab.Item.class,
            "sku", null,
            ValidationLab.Groups.Publish.class);

        assertEquals(1, errors.size());
        assertEquals(
            "NotBlank",
            errors.iterator().next()
                .getConstraintDescriptor()
                .getAnnotation().annotationType().getSimpleName());
    }

    @Test
    void defaultGroupRunsOnlyDefaultRules() {
        var errors = validator.validate(
            ValidationLab.invalidItem());

        assertEquals(Set.of("id"), paths(errors));
    }

    @Test
    void draftGroupDoesNotSilentlyRunDefaultOrPublish() {
        var errors = validator.validate(
            ValidationLab.invalidItem(),
            ValidationLab.Groups.Draft.class);

        assertEquals(Set.of("title"), paths(errors));
    }

    @Test
    void publishGroupAlsoCascadesIntoContactGroup() {
        var errors = validator.validate(
            ValidationLab.invalidItem(),
            ValidationLab.Groups.Publish.class);

        assertEquals(
            Set.of(
                "sku", "stock",
                "recipient.name", "recipient.email"
            ),
            paths(errors));
    }

    @Test
    void sequenceStopsWhenDraftFails() {
        var errors = validator.validate(
            ValidationLab.invalidItem(),
            ValidationLab.Groups.Ready.class);

        assertEquals(Set.of("title"), paths(errors));
    }

    @Test
    void sequenceRunsPublishAfterDraftPasses() {
        var item = new ValidationLab.Item(
            "", "Laptop", "bad-9", 0,
            new ValidationLab.Recipient("", "not-email"));

        var errors = validator.validate(
            item, ValidationLab.Groups.Ready.class);

        assertEquals(
            Set.of(
                "sku", "stock",
                "recipient.name", "recipient.email"
            ),
            paths(errors));
    }

    @Test
    void withoutValidNestedErrorsDoNotPropagate() {
        var contact = new ValidationLab.Recipient(
            "", "not-email");
        var holder = new ValidationLab.WithoutCascade(contact);

        assertTrue(validator.validate(
            holder, ValidationLab.Groups.Contact.class).isEmpty());

        // Validating Contact directly surfaces its errors.
        assertEquals(
            Set.of("name", "email"),
            paths(validator.validate(
                contact, ValidationLab.Groups.Contact.class)));
    }

    @Test
    void nullRecipientNeedsExplicitNotNullRule() {
        var item = new ValidationLab.Item(
            "ITEM-2", "Valid", "AB-123", 1, null);

        var errors = validator.validate(
            item, ValidationLab.Groups.Publish.class);

        assertEquals(Set.of("recipient"), paths(errors));
        assertEquals(
            "NotNull",
            errors.iterator().next()
                .getConstraintDescriptor()
                .getAnnotation().annotationType().getSimpleName());
    }

    @Test
    void validatePropertyDoesNotCascadeToChild() {
        var item = ValidationLab.invalidItem();

        assertTrue(validator.validateProperty(
            item, "recipient",
            ValidationLab.Groups.Publish.class).isEmpty());

        // Whole-graph validate applies @Valid + @ConvertGroup.
        assertFalse(validator.validate(
            item, ValidationLab.Groups.Publish.class).isEmpty());
    }

    @Test
    void containerElementValidCascadesIntoListElements() {
        var batch = new ValidationLab.ContactBatch(
            List.of(new ValidationLab.Recipient(
                "", "not-email")));

        var errors = validator.validate(
            batch, ValidationLab.Groups.Contact.class);

        assertEquals(2, errors.size());
        assertTrue(errors.stream().allMatch(v ->
            v.getPropertyPath().toString()
                .contains("contacts[0]")));
    }

    @Test
    void validItemCanPassAllRequestedGroups() {
        var errors = validator.validate(
            ValidationLab.validItem(),
            Default.class,
            ValidationLab.Groups.Draft.class,
            ValidationLab.Groups.Publish.class);

        assertTrue(errors.isEmpty());
    }
}
```

The test suite contains **12 JUnit methods**, focusing on concrete behavior instead of broad boolean checks.

### 10.2. Running tests

```bash
mvn -q test
```

If all assertions succeed, Maven returns **exit code 0**. With `-q`, do not expect fixed stdout. Detailed reports appear in `target/surefire-reports/`, such as the XML report for `demo.ValidationLabTest`.

**Assertions and expected outputs are derived from the program logic, and the compiler/JUnit were not executed in this document.** When applying in a real project, run Maven tests against your exact Java/dependency versions; if changing groups or messages, update tests to match the new contract.

### 10.3. Reading results by responsibility layer

| Test | What it proves |
| --- | --- |
| `customConstraintAcceptsProperSkuAndRejectsBadSku` | Custom validator executes, metadata identifies exact annotation |
| `nullSkuIsRejectedByNotBlankNotFormatRule` | Null handling is separate from format validation |
| `defaultGroupRunsOnlyDefaultRules` | Omitting groups uses Default |
| `draftGroupDoesNotSilentlyRunDefaultOrPublish` | Draft does not implicitly include Default/Publish |
| `publishGroupAlsoCascadesIntoContactGroup` | Publish checks parent group and converts to Contact |
| `sequenceStopsWhenDraftFails` | Group sequence short-circuits |
| `sequenceRunsPublishAfterDraftPasses` | Later group runs once earlier group passes |
| `withoutValidNestedErrorsDoNotPropagate` | Missing `@Valid` does not cascade automatically |
| `nullRecipientNeedsExplicitNotNullRule` | Null is caught by `@NotNull`, not `@Valid` |
| `validatePropertyDoesNotCascadeToChild` | `validateProperty` does not descend into child objects |
| `containerElementValidCascadesIntoListElements` | `@Valid` on List type argument produces nested violations |
| `validItemCanPassAllRequestedGroups` | Valid case passes across multiple requested groups |

## 11. Improving test quality: assert the cause, not just the error count

Writing only:

```java
assertFalse(validator.validate(item).isEmpty());
```

is usually too weak. It does not tell you whether `@ValidSku` actually ran; the item might have failed due to `@NotBlank` on another field.

A strong test verifies:

- **Property path**: `sku`, `recipient.email`, `contacts[0].email`.
- **Constraint type**: `getConstraintDescriptor().getAnnotation().annotationType()`.
- **Message template**: e.g., `{demo.sku.invalid}` when verifying a custom annotation points to the right bundle key.
- **Requested group**: Default, Draft, Publish, Ready, Contact.
- **Presence or absence of `@Valid`** on references/container elements.
- **Difference** between early-group and late-group errors in a sequence.
- **No side effects**: the validator never mutates objects or writes to the DB just by validating.

When multiple violations hit the same field, `Set<String> paths` can hide the count or annotation types. In tests distinguishing two constraints on one field, compare pairs of `field + annotation type` or `ConstraintDescriptor` entries and assert counts explicitly.

### 11.1. Testing @NotBlank combined with @ValidSku

A `sku` of `""` can violate both `@NotBlank` and `@ValidSku`. If the API wants only one error per field, that is either a presentation-layer **error aggregation strategy** or a constraint-design change; Bean Validation does not guarantee one violation per property by default.

Tests can assert both or use a custom constraint that accepts blank/null and delegates "required" to `@NotBlank`. Do not assert `assertEquals(1, errors.size())` for an empty string when the model has two constraints failing simultaneously without mutual exclusion.

### 11.2. Testing custom constraint metadata

Use:

```java
ConstraintDescriptor<?> descriptor =
    violation.getConstraintDescriptor();

Class<?> annotationType =
    descriptor.getAnnotation().annotationType();

Set<Class<?>> groups = descriptor.getGroups();
```

This is a fragment assuming `violation` exists. You can assert `annotationType == ValidSku.class` and `groups` contains `Publish.class`. Testing the descriptor catches annotations placed on the wrong property or assigned to the wrong groups even when the displayed message looks identical.

### 11.3. Keep localization tests separate

`ConstraintViolation#getMessageTemplate()` is the raw descriptor string, whereas `getMessage()` is interpolated per locale/provider. If the goal is testing constraint logic, compare templates/annotation types rather than a fixed localized sentence.

If the goal is i18n, create separate resource bundles `ValidationMessages_vi.properties` and `ValidationMessages_en.properties`, configure the provider's locale appropriately, and test messages under the exact locale. **Do not mutate JVM-wide `Locale.setDefault(...)` across parallel tests**, as that introduces races.

## 12. Connection to Spring MVC: @Valid, @Validated, and groups

In Spring MVC 6.2, when Jakarta Bean Validation is on the classpath, `LocalValidatorFactoryBean` is normally registered as the default validator.

### 12.1. @Valid uses the Default group in common cases

Controller fragment:

```java
@PostMapping("/inventory/drafts")
public ResponseEntity<?> draft(
        @Valid @RequestBody ItemInput input) {
    return ResponseEntity.ok().build();
}
```

This is an integration snippet requiring `ItemInput` DTO and imports. Usually `@Valid` on an argument object invokes Bean Validation with the default group. If the DTO only declares constraints in Draft/Publish and none in Default, `@Valid` alone may **not execute** those rules.

### 12.2. @Validated selects specific groups

```java
@PostMapping("/inventory/publish")
public ResponseEntity<?> publish(
        @Validated(Groups.Publish.class)
        @RequestBody ItemInput input) {
    return ResponseEntity.ok().build();
}
```

This fragment uses `Groups.Publish` and an application `ItemInput`. `@Validated(...)` is Spring's group-supporting annotation; on a controller argument, it selects the requested groups for object-level validation. To run Draft then Publish sequentially, pass `@Validated(Groups.Ready.class)` when the group model supports it.

**Note:** `@Validated` at the **controller class level** can activate Spring AOP method validation rather than Spring MVC 6.1+ built-in method validation, leading to a different exception path. Do not equate parameter-level group selection with annotating the whole controller class with `@Validated`.

### 12.3. MVC errors differ from plain Jakarta Validator errors

| Context | Typical failure mode |
| --- | --- |
| Plain `Validator#validate(bean)` | Returns `Set<ConstraintViolation<T>>`, does not throw on violations |
| `@Valid @RequestBody DTO` in MVC without adjacent BindingResult | `MethodArgumentNotValidException` on the object-argument validation path |
| Direct method constraints in MVC 6.1+ | `HandlerMethodValidationException` on the method-validation path |
| `@Valid @ModelAttribute` with adjacent `BindingResult` | Controller receives errors to handle itself |
| `@Validated` service method via Spring AOP | May throw `ConstraintViolationException` or `MethodValidationException` depending on config |

Method validation can **encompass** nested `@Valid` arguments when the method also declares direct constraints. Never write a test catching a single exception type and claim every controller validation path uses it.

### 12.4. Cascading is the model's responsibility

If an input has a nested object:

```java
public class ItemInput {
    @Valid
    @ConvertGroup(
        from = Groups.Publish.class,
        to = Groups.Contact.class)
    private RecipientInput recipient;
}
```

where `RecipientInput` has constraints in `Contact`, validation from `Publish` can cascade into `recipient`. Declaring `RecipientInput` without `@Valid` will not trigger child traversal.

This is a fragment for a Spring MVC DTO, not a class from section 9's standalone program. For nested lists, use `List<@Valid RecipientInput>` and place group conversion at the cascade edge.

## 13. Testing across three layers and when to use each

| Test layer | Tool | Focus | Does not prove on its own |
| --- | --- | --- | --- |
| Unit custom constraint logic | `SkuValidator#isValid(...)` or `Validator#validateValue(...)` | Regex, null, boundary values | Full groups/cascade/MVC if calling `isValid` directly |
| Jakarta Bean Validation integration | `Validator#validate(...)` + JUnit 5 | Groups, sequences, cascade, conversion, metadata | Spring MVC argument resolvers, HTTP status, `@InitBinder`, serialization |
| Spring MVC integration | `MockMvc` / Spring Boot Test | `@Validated(groups)`, error mapping, HTTP 400, binding/JSON, controller behavior | Full security/business side effects unless included in test setup |

A unit test calling directly:

```java
new ValidationLab.SkuValidator()
    .isValid("bad-9", null);
```

can test the regex because the current implementation ignores context, yet it **skips** annotation metadata, message interpolation, group selection, and provider bootstrapping. Provider-level tests via `validator.validateValue(...)` or `validate(...)` are what prove the constraint is properly registered and enforced in Jakarta.

If the controller binds JSON via Jackson, test JSON deserialization separately; `@Valid` does not replace HTTP payload shape validation or converter error handling. If a form uses `@ModelAttribute`, also test `WebDataBinder`/`@InitBinder` and `BindingResult`.

## 14. Edge cases to add to the test suite

### 14.1. Null, blank, and malformed patterns

| SKU input | `@NotBlank` | `@ValidSku` in example | Outcome when both are in Publish |
| --- | --- | --- | --- |
| `null` | Violated | Valid | 1 violation |
| `""` | Violated | Violated | Can produce 2 violations |
| `"  "` | Violated | Violated | Can produce 2 violations |
| `"AB-12"` | Valid | Violated | 1 violation |
| `"ab-123"` | Valid | Violated | 1 violation |
| `"AB-123"` | Valid | Valid | 0 violations |

The regex is a representation rule specific to this lab. In real systems, decide whether to allow case-insensitivity or normalize prior to validation, rather than blindly calling `toUpperCase()` on strings when the domain forbids it.

### 14.2. Group inheritance and duplicate validations

If a constraint belongs to multiple groups, the provider does not necessarily execute it multiple times during a single validation pass requesting multiple overlapping groups. Do not treat `isValid()` call counts as a business contract without special reason. Groups select rule subsets; never use them to trigger side effects or send emails.

When a group inherits multiple groups, evaluation order across unsequenced constraints remains undefined. Use `@GroupSequence` whenever order is a genuine business requirement.

### 14.3. Null nested references and empty collections

- Null reference: `@Valid` produces no nested violations; use `@NotNull` if required.
- Null collection: `@Valid` does not require the collection to be non-null; use `@NotNull`.
- Empty collection: no elements to cascade into; use `@NotEmpty` or `@Size(min=1)` on the collection with the right group if at least one element is required.
- Collection with a null element: cascading skips null elements; if null elements are invalid, use `List<@NotNull @Valid Recipient>` with constraints in the right groups.
- Map: may need separate key/value checks; Jakarta Validation supports container element constraints for generic type arguments and value extractors.
- Graph cycles: providers have cycle-avoidance rules to prevent endless recursion, yet you should still test complex structures and execution times.

### 14.4. @ConvertGroup across different graph edges

Group conversion applies to the **declared cascade edge**, not globally at the root or for every object of that type across the graph. Two fields pointing to `Recipient` can have different group conversions on each association per policy.

If `@ConvertGroup(from=Publish.class,to=Contact.class)` is declared while validating `Draft.class`, this conversion rule **does not match**; `Draft` propagates by default if `@Valid` applies. Since `Recipient` only has `Contact` constraints, zero violations occur—which is expected, not a provider bug.

### 14.5. Class-level constraints and cross-field rules

If a custom constraint must compare two fields, place it on `TYPE` and implement `ConstraintValidator<CustomAnnotation, Item>`. On failure, you can add a property node pointing to the relevant attribute. For a validator checking only SKU, a `FIELD` constraint as in the demo is simpler.

Never let a custom validator hit the database arbitrarily inside every `isValid()` call, as that increases latency, complicates transaction/caching guarantees, and turns validation into a source of side effects. Inventory checks, ownership, and state-transition permissions belong in the appropriate domain/service/authorization layer.

## 15. Common errors and fixes

| Symptom | Typical cause | Fix |
| --- | --- | --- |
| `@ValidSku` never runs | Annotation lacks `@Constraint`, wrong retention, provider not bootstrapped, or group unselected | Check annotation metadata, `validateValue`, and groups |
| `UnexpectedTypeException` | No `ConstraintValidator` matches the annotation's target type | Declare an implementation matching the field type |
| `ConstraintDefinitionException` | Constraint annotation missing `message/groups/payload` or malformed | Follow the Jakarta Bean Validation contract |
| Custom error message not found | Missing `ValidationMessages.properties` or wrong key | Check resource root/classpath and `getMessageTemplate()` |
| `validator.validate(bean)` skips Publish | Publish is not the Default group | Call `validate(bean, Publish.class)` or use an appropriate sequence |
| `@Valid` on Recipient produces no errors | Nested constraints belong to Contact while Publish was passed | Add `@ConvertGroup` if required by policy |
| `@ConvertGroup` has no effect | Not paired with `@Valid`, wrong `from` group, or placed on a different edge | Verify annotation placement and group conversion rules |
| `ConstraintDeclarationException` | `@ConvertGroup` missing `@Valid`, duplicate `from`, or `from` is a sequence | Fix declaration per spec |
| `Ready` reports only title, not SKU | Group sequence stops at Draft when Draft fails | Fix title and re-validate, or pass non-sequenced groups when all errors are needed |
| Tests relying on Set order flake | `Set<ConstraintViolation>` has no guaranteed order | Compare path sets or sort first |
| Duplicate field masks a violation | Compared only `Set<String> paths` | Also compare annotation types and counts |
| `@Valid` does not report null Recipient | Cascade skips null | Add `@NotNull` on the reference |
| Standalone custom validator test passes, Jakarta provider fails | Direct `isValid` skips metadata/bootstrapping | Add provider-level tests |
| Spring MVC runs only Default | Used `@Valid` instead of `@Validated(Publish.class)` | Select the group on the appropriate argument |
| Controller throws unexpected exception | Whole-method validation or class-level AOP `@Validated` | Inspect Spring MVC 6.1+ validation path |
| Validation passes yet user lacks permission to edit | Groups are not authorization | Check principal/resource/tenant in the service |
| Validator mutates state inside `isValid` | Custom constraint has side effects | Keep validation pure; perform updates in business logic |

## 16. Testing and review checklist

1. Does the custom constraint have `@Constraint`, runtime retention, proper targets, and `message/groups/payload`?
2. Does `ConstraintValidator` support the right property type with an explicit contract for null/blank?
3. Are valid values, malformed formats, null, blank, and boundary cases tested?
4. Do tests assert annotation types or message templates rather than just `hasViolations()`?
5. Are `Default`, each custom group, and multi-group behaviors tested?
6. When ordering is required, is `@GroupSequence` used and stop-on-failure tested?
7. Is the group sequence tested again after fixing the first group's errors?
8. Do nested objects have `@Valid` on the right field/getter/type argument?
9. Is an invalid nested object tested **without `@Valid`** to prove cascading is opt-in?
10. For group conversion, is parent-to-child conversion tested via concrete paths?
11. Are `null` references and `@NotNull` tested separately?
12. For collections, are invalid, null, and empty elements tested when the business contract requires it?
13. Is `validate` distinguished from `validateProperty` and `validateValue`?
14. Do assertions avoid Set iteration order and volatile localized messages?
15. Is `ValidatorFactory` managed and closed properly in tests, with mutable state isolated?
16. For MVC, are `@Valid` vs `@Validated(groups)` and HTTP status/exception paths tested?
17. Are groups kept completely separate from Admin/User permissions, with independent authorization?
18. Are regression tests present when adding fields, renaming groups, or refactoring nested DTOs?

## 17. Summary

A **custom constraint** consists of a properly declared annotation and a `ConstraintValidator` implementing the rule. Test valid/invalid/null values along with metadata to prove the provider enforces the constraint.

**Validation groups** select constraint subsets: omitting groups selects `Default`; `@GroupSequence` enforces ordering and stops subsequent groups when an earlier group fails. Never confuse groups with roles or an authorization mechanism.

**Cascaded validation** descends into child objects/collection elements only when `@Valid` is present; null references are skipped unless constrained by `@NotNull`. When a child object uses a different group, `@ConvertGroup` converts the group at that cascade edge. A strong JUnit 5 suite verifies each mechanism independently and then in combination—especially through **property paths, constraint annotation types, and group-sequence short-circuiting**.

## Official references

- Jakarta Bean Validation 3.0 specification — Constraint definitions: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Bean Validation 3.0 — Validation groups, sequences, and group conversion (same specification, sections 5.4–5.5): https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Hibernate Validator 8 Reference Guide — Custom constraints, section 6; Grouping constraints, section 5: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Jakarta Validation API — `ConstraintValidator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraintvalidator
- Jakarta Validation API — `Validator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/validator
- Jakarta Validation API — `GroupSequence`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/groupsequence
- Jakarta Validation API — `ConvertGroup`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/groups/convertgroup
- Spring Framework 6.2 — Bean Validation integration: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — MVC validation rules for `@Valid` and `@Validated`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — Web MVC validator configuration: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html
- JUnit 5 User Guide — Lifecycle and assertions: https://junit.org/junit5/docs/current/user-guide/