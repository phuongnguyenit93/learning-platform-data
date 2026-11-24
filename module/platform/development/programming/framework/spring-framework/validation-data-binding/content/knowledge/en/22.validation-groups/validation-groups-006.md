# `@GroupSequence` and Stage Ordering in Bean Validation

## 1. Why Do We Need Validation Ordering?

In Spring Framework, Jakarta Bean Validation can check an object against many constraints: required fields, formatting, cross-field relationships, and complex business rules. Not all checks should always run at the same time.

For example, a registration form has three stages:

1. **Required:** name and email must not be blank.
2. **Syntax:** email must be properly formatted.
3. **Business:** registration code must follow business rules.

If the name is still blank, you may want to **stop after the Required stage** instead of showing additional errors from later steps. If the email is present but syntactically invalid, you may want to return the format error and **skip** business constraints that depend on valid input.

Jakarta Bean Validation supports this via **validation groups** and the **`@GroupSequence`** annotation:

```text
Request validation for OrderedChecks
                  |
                  v
           [Required]
          error? -- yes --> finish; return Required violations
                  |
                  no
                  v
            [Syntax]
          error? -- yes --> finish; return Syntax violations
                  |
                  no
                  v
           [Business]
                  |
                  v
            return result
```

**Core idea:** `@GroupSequence` establishes **ordering between groups (stages)**. If a stage produces at least one `ConstraintViolation`, **subsequent** stages are skipped in that validation pass. It **does not guarantee** execution order among individual annotations within the same group, nor is it a "stop on the very first error globally" mechanism.

After this lesson, you will understand and be able to use:

- `groups` on annotations such as `@NotBlank`, `@Pattern`, `@Min`, and `@AssertTrue`.
- `@GroupSequence` placed on an **interface representing a sequence of groups**.
- `@GroupSequence` placed directly on a **bean class to redefine that class's `Default` group**.
- Differences between `validator.validate(bean, Ordered.class)`, `validator.validate(bean, A.class, B.class)`, and the default `validator.validate(bean)`.
- Inter-stage short-circuiting rules, cascaded validation (`@Valid`), group conversion, and common configuration mistakes.
- Integrating with Spring MVC using `@Validated(Ordered.class)` and checking `BindingResult`.

## 2. Reviewing Validation Groups

A **group** represents a set of constraints evaluated together. In Jakarta Validation, a group is typically represented by an empty interface:

```java
public interface Required {}
public interface Syntax {}
public interface Business {}
```

When declaring a constraint, you attach it to one or more groups:

```java
@NotBlank(groups = Required.class)
private String name;

@Pattern(regexp = ".+@.+\\..+", groups = Syntax.class)
private String email;

@Pattern(regexp = "REG-[0-9]{3}", groups = Business.class)
private String registrationCode;
```

This is an **illustrative code snippet**; you must import the annotations from `jakarta.validation.constraints` and declare the group interfaces in the appropriate class/package.

A constraint can belong to **multiple groups**:

```java
@NotBlank(groups = {Required.class, Business.class})
private String displayName;
```

However, belonging to multiple groups does not create a processing order. If you want `Required` to run before `Business`, you need a group sequence.

### 2.1. The `Default` Group

If you omit the `groups` attribute:

```java
@NotBlank
private String name;
```

the constraint belongs to **`jakarta.validation.groups.Default`**. When calling:

```java
validator.validate(object);
```

Jakarta Validation requests the `Default` group by default (aside from standard-compliant overrides such as redefining `Default` on a class). That is **different** from "running every group".

If a DTO's constraints only carry `groups = Required.class`, `groups = Syntax.class`, and `groups = Business.class`, calling `validate(dto)` without specifying groups will **not automatically run those three groups**. You must explicitly request the appropriate groups or sequence.

### 2.2. Calling Multiple Groups Does Not Mean Ordered Execution

These two approaches have different semantics:

```java
// Requests multiple groups; DOES NOT guarantee order A -> B -> C.
validator.validate(form, Required.class, Syntax.class, Business.class);

// Requests a group sequence that explicitly defines order.
validator.validate(form, OrderedChecks.class);
```

When passing multiple groups directly to `validate(...)`, the specification does not mandate execution order among them. Do not rely on varargs argument order to infer "Required failed so Syntax did not run".

**A group only selects a set of constraints. Only a group sequence carries ordering rules between those sets.**

## 3. Declaring `@GroupSequence` on an Interface

Suppose we have three groups:

```java
public interface Required {}
public interface Syntax {}
public interface Business {}
```

We declare an interface **representing the sequence**:

```java
import jakarta.validation.GroupSequence;

@GroupSequence({
    Required.class,
    Syntax.class,
    Business.class
})
public interface OrderedChecks {}
```

`OrderedChecks` is a **group sequence**. When calling:

```java
Set<ConstraintViolation<Registration>> violations =
        validator.validate(registration, OrderedChecks.class);
```

validation is requested in the order:

```text
Required -> Syntax -> Business
```

Mechanism:

1. Evaluate constraints belonging to `Required` across the applicable object graph.
2. If `Required` has violations, return those violations and **do not proceed to `Syntax` and `Business`**.
3. If `Required` passes, proceed to `Syntax`.
4. If `Syntax` has violations, **skip `Business`**.
5. If `Syntax` passes, validate `Business`.
6. The returned violation set reflects the constraints that were executed; it does not necessarily contain latent errors from stages that did not run.

Do not attach constraints directly using `groups = OrderedChecks.class`. Attach constraints to the **component groups** such as `Required`, `Syntax`, and `Business`, then request `OrderedChecks` at the validation entry point.

An interface carrying `@GroupSequence` should also not `extends` other groups. Per the specification, it is a **sequence declaration** interface, not an inherited group to attach constraints to.

### 3.1. What If One Stage Has Multiple Violations?

Suppose `Required` has:

```java
@NotBlank(groups = Required.class)
private String name;

@NotBlank(groups = Required.class)
private String email;
```

If both fields are blank, the validator **can return two violations in the `Required` stage**. `@GroupSequence` only guarantees that **later** stages do not run; it does not guarantee receiving only **one** error.

Nor can you rely on `name` executing before `email`, or on element order inside `Set<ConstraintViolation<?>>`. For deterministic tests or logs, compare **violation sets by path/constraint** or sort before displaying.

### 3.2. Three-Attempt Example

| Input | `Required` | `Syntax` | `Business` | Result |
| --- | --- | --- | --- | --- |
| Blank name, invalid email, invalid code | **Fail** | Skipped | Skipped | Only `Required` stage errors |
| Valid name, invalid email, invalid code | Pass | **Fail** | Skipped | `Syntax` stage errors |
| Valid name/email, invalid code | Pass | Pass | **Fail** | `Business` stage errors |
| All data valid | Pass | Pass | Pass | No violations |

This sequence fits a pipeline that **checks foundational conditions before complex conditions**. It does not make syntax or business constraints disappear; they still run once data clears the earlier stage.

## 4. `@GroupSequence` Does Not Activate Itself

Simply defining the interface:

```java
@GroupSequence({Required.class, Syntax.class})
interface OrderedChecks {}
```

does not mean every validation call automatically uses this sequence.

You must specify `OrderedChecks.class` at the **validation request point**:

```java
validator.validate(form, OrderedChecks.class);
```

or in Spring MVC, on the argument being validated by group:

```java
@Validated(OrderedChecks.class) @ModelAttribute("form") Registration form
```

Spring's `@Validated` lets you specify validation hints/groups. Conversely, `@Valid` on an ordinary controller parameter triggers validation but **carries no `groups` attribute to select a sequence interface**; absent other configuration, the group used is `Default`.

Other design situations:
- Need different endpoints to validate differently: use dedicated groups/sequences per endpoint.
- Need every `Default` validation of **one specific class** to follow a sequence: place `@GroupSequence` on the **class** (see section 6).
- Need both foundational checks and expensive rules: put `Default` in the sequence interface followed by the advanced-step group.

## 5. Using `Default` as the First Stage of a Sequence Interface

In existing code, constraints often omit `groups` and therefore belong to `Default`:

```java
public class ProductForm {
    @NotBlank
    private String name;

    @Min(1)
    private Integer quantity;

    @SomeComplexRule(groups = Advanced.class)
    private String extra;
}
```

`@SomeComplexRule` here is an **illustrative name**, not a standard annotation and not a standalone runnable Java program. Standard annotations like `@NotBlank` and `@Min` belong to Jakarta Validation.

You can define:

```java
public interface Advanced {}

@GroupSequence({Default.class, Advanced.class})
public interface FullCheck {}
```

Import `jakarta.validation.GroupSequence` and `jakarta.validation.groups.Default`.

When calling `validator.validate(product, FullCheck.class)`:

1. Constraints in `Default` run first.
2. If `name` or `quantity` fails, `Advanced` is **not checked**.
3. Only if `Default` passes is `Advanced` evaluated.

This is a useful way to add an expensive stage to a DTO that already uses many default constraints **without editing all the existing annotations**.

**Note:** this section covers `@GroupSequence` on an **interface**. When placing the annotation on a **bean class to redefine `Default`**, the syntax differs and has a mandatory rule: you must include the class itself in the sequence, not `Default.class` in its place. See the next section.

## 6. Redefining the `Default` Group on the Bean Class Itself

Jakarta Validation also allows placing `@GroupSequence` **directly on a class**. In that case, it does not define a named sequence interface to pass explicitly; instead, it changes **the meaning of `Default` for that class**.

Example:

```java
public interface ComplexChecks {}

@GroupSequence({Invoice.class, ComplexChecks.class})
public class Invoice {

    @NotBlank
    private String invoiceNumber;

    @AssertTrue(groups = ComplexChecks.class)
    private boolean totalIsConsistent;

    // Constructor/getters/setters.
}
```

This is an **illustrative snippet**, requiring imports for `jakarta.validation.GroupSequence`, `jakarta.validation.constraints.NotBlank`, and `AssertTrue`.

When calling:

```java
validator.validate(invoice); // No need to specify a sequence interface.
```

for an `Invoice` instance, `Default` validation is replaced by:

```text
Invoice.class -> ComplexChecks.class
```

Meaning:
- `Default` constraints declared on `Invoice` are included via the **`Invoice.class`** group in the first stage.
- If `invoiceNumber` is blank, `ComplexChecks` is not reached.
- If `invoiceNumber` is valid while `totalIsConsistent` is `false`, the `@AssertTrue` constraint in `ComplexChecks` runs and can report a violation.
- If both are valid, there are no violations.

### 6.1. Why Must `Invoice.class` Be Included?

For redefining `Default` on the `Invoice` class, the standard **requires** the sequence to contain **`Invoice.class` itself**:

```java
// CORRECT: placed on the Invoice class.
@GroupSequence({Invoice.class, ComplexChecks.class})
public class Invoice { ... }
```

Do not replace it with:

```java
// WRONG when placed on the Invoice class.
@GroupSequence({Default.class, ComplexChecks.class})
public class Invoice { ... }
```

The second case uses `Default.class` to redefine `Default` itself and causes a configuration error. If a class-level sequence does not include **that class**, the provider must throw **`GroupDefinitionException`** when validating or reading metadata.

**Remember these two formulas:**

| Annotation placement | Correct configuration | How to invoke |
| --- | --- | --- |
| On **sequence interface** `FullCheck` | `@GroupSequence({Default.class, ComplexChecks.class})` | `validator.validate(bean, FullCheck.class)` |
| On **bean class** `Invoice` | `@GroupSequence({Invoice.class, ComplexChecks.class})` | `validator.validate(invoice)` uses redefined `Default` |

This is one of the most important distinctions of `@GroupSequence`.

### 6.2. Scope of `Default` Redefinition

Redefining `Default` on a class is **local to that class**. It **does not automatically propagate the new sequence intact to every child object** annotated with `@Valid`.

If `Invoice` contains `@Valid Customer customer`:
- When `Default` propagates across the cascade relationship, `Customer` normally uses **`Customer`'s own `Default`** semantics.
- A `Default` sequence defined specifically on `Invoice` is not treated as a global group sequence applied identically to `Customer`.
- If `Customer` also has its own `Default` sequence, it can apply its own rules when validated in `Default`.
- If you need to switch groups across a `@Valid` edge, consider `@ConvertGroup` deliberately.

Therefore, do not treat redefining `Default` on a root DTO as an "application-wide group sequence switch". Test both root and child when nested validation is involved.

## 7. Complete Java 17+ Maven Example: Three Stages and `Default` Redefinition

The following example uses **Jakarta Bean Validation 3.0, Hibernate Validator 8.0.2.Final**, and **Spring Framework 6.2.14**. The program runs standalone without Spring Boot or a web server and verifies:
- Three stages: `Required` → `Syntax` → `Business`.
- Skipping later stages when an earlier stage has errors.
- `Default` **does not automatically run** custom groups when constraints only belong to custom groups.
- Spring `SpringValidatorAdapter` accepting a sequence as a validation hint.
- `@GroupSequence` on a **class** changing its `Default` sequence properly.

### 7.1. Create `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>validation-group-sequence</artifactId>
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
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.14</version>
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

`hibernate-validator` is the Jakarta Bean Validation provider; `jakarta.el` supports message interpolation; `spring-context` supplies `SpringValidatorAdapter` and `BeanPropertyBindingResult`. In Spring Boot, typically use Boot's dependency management and validation starter rather than pinning individual versions as in this learning example.

### 7.2. Create `src/main/java/demo/GroupSequenceDemo.java`

```java
package demo;

import java.util.List;

import jakarta.validation.GroupSequence;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.beanvalidation.SpringValidatorAdapter;

public final class GroupSequenceDemo {

    public interface Required {}
    public interface Syntax {}
    public interface Business {}

    // Sequence interface requested explicitly.
    @GroupSequence({Required.class, Syntax.class, Business.class})
    public interface OrderedChecks {}

    public static final class Registration {
        @NotBlank(groups = Required.class, message = "name required")
        private String name;

        @NotBlank(groups = Required.class, message = "email required")
        @Pattern(
            regexp = "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$",
            groups = Syntax.class,
            message = "email syntax invalid"
        )
        private String email;

        @Pattern(
            regexp = "REG-[0-9]{3}",
            groups = Business.class,
            message = "registration code invalid"
        )
        private String registrationCode;

        public Registration(String name, String email, String code) {
            this.name = name;
            this.email = email;
            this.registrationCode = code;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public String getRegistrationCode() {
            return registrationCode;
        }

        public void setRegistrationCode(String code) {
            this.registrationCode = code;
        }
    }

    public interface DeepCheck {}

    // When on a CLASS, @GroupSequence redefines Default for that class.
    @GroupSequence({Profile.class, DeepCheck.class})
    public static final class Profile {
        @NotBlank(message = "title required")
        private String title;

        @AssertTrue(
            groups = DeepCheck.class,
            message = "approval required"
        )
        private boolean approved;

        public Profile(String title, boolean approved) {
            this.title = title;
            this.approved = approved;
        }

        public String getTitle() {
            return title;
        }

        public void setTitle(String title) {
            this.title = title;
        }

        public boolean isApproved() {
            return approved;
        }

        public void setApproved(boolean approved) {
            this.approved = approved;
        }
    }

    private static <T> List<String> paths(
            Validator validator, T bean, Class<?>... groups) {
        return validator.validate(bean, groups).stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .toList();
    }

    private static void check(
            List<String> actual,
            List<String> expected,
            String caseName) {
        if (!actual.equals(expected)) {
            throw new AssertionError(
                    caseName + ": expected " + expected
                    + ", got " + actual);
        }
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            Registration first = new Registration(
                    " ", "not-an-email", "BAD");

            Registration second = new Registration(
                    "Ada", "not-an-email", "BAD");

            Registration third = new Registration(
                    "Ada", "ada@example.com", "BAD");

            Registration valid = new Registration(
                    "Ada", "ada@example.com", "REG-123");

            // Each run executes stages only up to the failing stage.
            List<String> required =
                    paths(validator, first, OrderedChecks.class);
            List<String> syntax =
                    paths(validator, second, OrderedChecks.class);
            List<String> business =
                    paths(validator, third, OrderedChecks.class);
            List<String> success =
                    paths(validator, valid, OrderedChecks.class);

            check(required, List.of("name"), "required");
            check(syntax, List.of("email"), "syntax");
            check(business, List.of("registrationCode"), "business");
            check(success, List.of(), "success");

            System.out.println("required=" + required);
            System.out.println("syntax=" + syntax);
            System.out.println("business=" + business);
            System.out.println("success=" + success);

            // Registration only uses custom groups, with no Default constraints.
            List<String> defaultOnly = paths(validator, first);
            check(defaultOnly, List.of(), "default");
            System.out.println("defaultOnly=" + defaultOnly);

            // Spring SmartValidator accepts a group sequence as a hint.
            SpringValidatorAdapter adapter =
                    new SpringValidatorAdapter(validator);
            BeanPropertyBindingResult springErrors =
                    new BeanPropertyBindingResult(second, "registration");

            adapter.validate(second, springErrors, OrderedChecks.class);
            List<String> springFields =
                    springErrors.getFieldErrors().stream()
                            .map(FieldError::getField)
                            .sorted()
                            .toList();

            check(springFields, List.of("email"), "spring");
            System.out.println("springFields=" + springFields);

            // @GroupSequence placed on Profile class:
            // validator.validate(profile) automatically uses the redefined Default.
            List<String> profile1 =
                    paths(validator, new Profile("", false));
            List<String> profile2 =
                    paths(validator, new Profile("Ready", false));
            List<String> profile3 =
                    paths(validator, new Profile("Ready", true));

            check(profile1, List.of("title"), "profile1");
            check(profile2, List.of("approved"), "profile2");
            check(profile3, List.of(), "profile3");

            System.out.println("classDefault1=" + profile1);
            System.out.println("classDefault2=" + profile2);
            System.out.println("classDefault3=" + profile3);

            System.out.println("CHECKS: PASS");
        }
    }
}
```

### 7.3. Run with Maven

From the directory containing `pom.xml`, using **JDK 17+ and Maven 3.9+**:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=demo.GroupSequenceDemo
```

Lines printed by the program itself, excluding Hibernate Validator or Maven startup logs that may appear on the console:

```text
required=[name]
syntax=[email]
business=[registrationCode]
success=[]
defaultOnly=[]
springFields=[email]
classDefault1=[title]
classDefault2=[approved]
classDefault3=[]
CHECKS: PASS
```

Explanation:
- `required=[name]`: blank name triggers a violation in `Required`. Even though email and code are also invalid, the two later stages **have not run**.
- `syntax=[email]`: `Required` passes; the email regex in `Syntax` fails. `registrationCode` in `Business` has not run yet.
- `business=[registrationCode]`: data clears the first two stages and fails in `Business`.
- `success=[]`: all stages pass.
- `defaultOnly=[]`: without requesting the sequence, `Registration` only has constraints on custom groups, so `Default` does not evaluate them.
- `springFields=[email]`: Spring's adapter accepts `OrderedChecks.class` as a validation hint and creates the corresponding `FieldError`.
- `classDefault1=[title]`: on `Profile`, `Default` evaluates `title` first, fails, and stops.
- `classDefault2=[approved]`: `title` passes, so it advances to `DeepCheck`.
- `classDefault3=[]`: both stages of the class's `Default` sequence pass.

**Note on syntax:** the email regex in the example only illustrates the syntax stage and is **not a production-grade email validation solution**. You can replace it with `@Email(groups=Syntax.class)` from Jakarta Validation, along with appropriate application rules and provider tests.

**Note on runnability:** `GroupSequenceDemo.java` has complete classes, imports, POM, Maven commands, and result assertions. When adapting to an existing project, run with that project's JDK and dependencies, especially if Spring/Jakarta namespaces differ from the illustrative versions.

## 8. Using a Group Sequence in Spring MVC

In a Spring MVC controller, a `@ModelAttribute` parameter can trigger an ordered group sequence via `@Validated`:

```java
@PostMapping("/registrations")
public String submit(
        @Validated(GroupSequenceDemo.OrderedChecks.class)
        @ModelAttribute("registration")
        GroupSequenceDemo.Registration form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "registration/form";
    }
    return "registration/success";
}
```

**This is an illustrative snippet placed inside a controller**, not a standalone program. It assumes DTO `GroupSequenceDemo.Registration` is used as a form model with appropriate instantiation/binding support; in real MVC apps, DTOs typically have a no-arg constructor or suitable constructor binding. Required imports:

```java
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.validation.BindingResult;
```

When a user submits data:

1. Spring MVC binds the request into `Registration` (type conversion and property population).
2. `@Validated(OrderedChecks.class)` invokes Bean Validation with the **sequence**.
3. If `Required` fails, `BindingResult` contains `Required` errors; `Syntax` and `Business` do not run during this sequence pass.
4. If `Required` passes while `Syntax` fails, only errors from `Syntax` are recorded.
5. If all three groups pass, processing continues.

**`BindingResult` must immediately follow the argument being validated** when handling its errors in a standard MVC flow. Replacing it with plain `@Valid` normally requests `Default`, and does not implicitly activate `OrderedChecks`.

### 8.1. Where to Put `@Validated`?

`@Validated` is a **Spring** annotation (`org.springframework.validation.annotation.Validated`) that can carry group classes as validation hints:

```java
@Validated(OrderedChecks.class)
```

`@GroupSequence` and `groups=...` are **Jakarta Bean Validation** mechanisms. Spring forwards hints to the appropriate provider through an adapter. When other annotations or infrastructure trigger **method validation** (such as constraints placed directly on method parameters), exception behavior and execution paths can differ from normal command-object validation; test the actual endpoint.

Do not assume putting `@Validated` on the entire controller class makes every `@ModelAttribute` automatically run a specific sequence as intended. For readability and control, place the right group on the parameter receiving the DTO and verify with integration tests.

### 8.2. `@RequestBody` JSON Can Also Be Validated by Group

You can declare:

```java
@PostMapping("/api/registrations")
public ResponseEntity<Void> submitJson(
        @RequestBody
        @Validated(OrderedChecks.class)
        RegistrationDto request) {
    // Process when DTO is valid.
    return ResponseEntity.noContent().build();
}
```

This is an **illustrative controller snippet** requiring Spring Web MVC, actual imports for `PostMapping`, `RequestBody`, `ResponseEntity`, `Validated`, and `RegistrationDto`. JSON is deserialized before Bean Validation runs; an unreadable JSON error **does not** become a `Required`/`Syntax`/`Business` stage violation. When no matching `BindingResult` is declared, argument validation failures can be thrown as exceptions handled by exception handlers depending on the MVC version and configuration.

Distinguish:
- **Binding/deserialization error**: failed to convert input into the target Java type.
- **Validation error**: Java object exists, but violates a constraint in a requested group.
- **Business processing error**: business rules or database reject the operation even with a valid DTO.

`@GroupSequence` controls **validation constraints**; it does not fix JSON parse errors and does not replace transactions or data consistency checks in the service/database layers.

## 9. `@Valid`, Child Objects, and Inter-Stage Ordering

A form may have the structure:

```java
public class OrderForm {
    @Valid
    private Customer customer;

    @Valid
    private List<LineItem> items;
}
```

This is illustrative code; you need imports for `jakarta.validation.Valid`, `java.util.List`, and the child classes. With `@Valid`, Bean Validation can check constraints on child objects. When calling `validator.validate(order, OrderedChecks.class)`, the sequence can apply **across the validated object graph**, not only the root object.

**Key point:** for an ordered group in a sequence, the validator must evaluate **constraints belonging to that stage on cascadable child objects** before deciding whether to move to the next stage. If a `Required` constraint on a child fails, the subsequent `Syntax` stage can be skipped for the entire sequence pass.

This fits requirements like:
- Check required fields on `OrderForm`, `Customer`, and `LineItem` first.
- Only if all required fields pass, validate formatting.
- Only if data is structurally valid, run expensive business constraints.

However, there is one important semantic exception: **a `Default` group sequence redefined on a class is local to that class and is not propagated intact across `@Valid` references**. For instance, `@GroupSequence({OrderForm.class, Advanced.class})` on `OrderForm` does not mean `Customer` automatically receives `OrderForm.class` then `Advanced.class` in place of its own `Default`.

To switch groups when cascading from parent to child, use `@ConvertGroup` on the `@Valid` edge:

```java
@Valid
@ConvertGroup(from = Default.class, to = ChildChecks.class)
private ChildDto child;
```

Imports are `jakarta.validation.Valid`, `jakarta.validation.groups.ConvertGroup`, and `jakarta.validation.groups.Default`. `ChildChecks` is a declared group interface; this snippet is **illustrative structural code**, not a full class.

`@ConvertGroup` does not arbitrarily alter ordering and does not define a new group sequence on its own: it **converts the group propagated across one cascade edge**. When combining it with `@GroupSequence`, test both root and child with invalid input scenarios to avoid thinking group conversion is a way to "apply `@GroupSequence` to every object".

### 9.1. `@Valid` Does Not Have `groups=...`

The following syntax is **invalid**:

```java
@Valid(groups = Required.class)  // Wrong: @Valid has no groups attribute.
private Customer customer;
```

The correct form is:

```java
@Valid
private Customer customer;
```

Then use `Validator.validate(root, Required.class)`, `@Validated(Required.class)` at the entry point, or `@ConvertGroup` when switching groups during cascade. Do not mistakenly put constraint parameters on `@Valid`.

## 10. Group Inheritance, Nested Groups, and Constraints in Multiple Groups

One group can extend another via interface inheritance:

```java
public interface Required {}
public interface Premium extends Required {}
```

When validating `Premium`, constraints belonging to `Required` can also be included via group inheritance. However, **interface inheritance does not create execution order**:

```text
Premium extends Required
    = group that includes inherited constraints
    ≠ run Required before Premium and stop if Required fails
```

To get ordering, create a **separate sequence interface** that does not `extends` other groups:

```java
@GroupSequence({Required.class, PremiumChecks.class})
public interface PremiumPipeline {}
```

Similarly, a group inside a sequence can be another composite group/sequence. The standard requires that ordering relationships of component groups be respected; definitions creating **invalid ordering cycles** can cause `GroupDefinitionException`.

If a constraint belonging to **multiple groups** appears in the same sequence, Jakarta Validation does not require repeatedly executing the same constraint on the same navigation path each time a group is encountered; a constraint already evaluated in an earlier matching group is not re-executed merely because it also belongs to a later group.

Therefore, do not rely on a `ConstraintValidator` with side effects or count `isValid()` invocations as a business mechanism. Constraint validators should focus purely on checking validity, not updating data or sending external notifications.

## 11. Is `@GroupSequence` the Same as "Fail Fast"?

**No.** These two mechanisms are different:

| Mechanism | Stopping rule | Jakarta standard? |
| --- | --- | --- |
| `@GroupSequence` | When **a group/stage** has violations, skip subsequent groups | Yes, part of Jakarta Validation |
| Provider-specific fail-fast | May stop immediately after the **first violation** detected by the provider | Provider-defined behavior/configuration, not `@GroupSequence` semantics |
| `if (errors.hasErrors()) return ...` in controller | Application stops further processing once errors exist | Application logic; does not alter constraint order inside validator |

For example, `Required` has 5 invalid fields. `@GroupSequence` does not guarantee returning only one error; you may receive multiple violations from that same stage. If Hibernate Validator's provider-specific fail-fast mode is enabled, the violation count and detection order may differ, but that is a **provider policy** and must be tested separately.

Do not depend on the order of individual constraints within one stage, and do not assume a group sequence orchestrates **real service tasks** such as transactional inventory checks or external API calls. Bean Validation should handle consistent, side-effect-free rules; services still must enforce business invariants when writing data.

## 12. Common Design and Configuration Mistakes

### 12.1. Confusing `@GroupSequence` with `@Validated`

`@GroupSequence` is a Jakarta annotation for **describing ordering among groups**. `@Validated` is a Spring annotation for **requesting validation of one or more groups** at an appropriate call site. Simply writing `@GroupSequence` on an interface without requesting that group has no effect on `validator.validate(bean)`.

### 12.2. Calling Multiple Groups Expecting Short-Circuiting

```java
validator.validate(form, Required.class, Business.class);
```

This is **not** a sequence. Two groups are requested with no standard ordering. Fix by calling:

```java
validator.validate(form, OrderedChecks.class);
```

where `@GroupSequence` declares the required order.

### 12.3. Placing `@GroupSequence` on a Class Without the Class Itself

```java
@GroupSequence({Default.class, Business.class})
public class Order { ... } // Invalid redefinition of Order's Default.
```

On a class, you must include `Order.class`:

```java
@GroupSequence({Order.class, Business.class})
public class Order { ... }
```

By contrast, on a **sequence interface**, `Default.class` is completely valid.

### 12.4. Using a Sequence Interface as `groups` on a Constraint

```java
@NotBlank(groups = OrderedChecks.class)
private String name;
```

This is not the standard way to assign per-stage constraints. Put `groups = Required.class` and include `Required.class` in the sequence. Per specification guidance, a sequence interface should not be used directly in constraint declarations.

### 12.5. Defining Cycles Between Sequences

```java
@GroupSequence({Second.class})
interface First {}

@GroupSequence({First.class})
interface Second {}
```

This illustrative structure creates a circular sequence dependency. The provider may throw `GroupDefinitionException` when processing that group. Do not rely on the provider to "fix" ordering automatically; design stages unidirectionally.

### 12.6. Assuming `Default` Is the Union of All Groups

A constraint with only `groups = Business.class` does **not** automatically belong to `Default`. If `@Valid` is used without group selection, it may not run. Add the appropriate group to the sequence or specify `@Validated` properly at the entry point.

### 12.7. Running Validation Without a Provider

Annotations do not execute themselves. Jakarta Bean Validation needs an implementation such as Hibernate Validator and Spring integration. If only the API is on the classpath without a provider, creating a `ValidatorFactory` or running validation can fail; in Spring Boot, include the matching validation starter dependency.

### 12.8. Ignoring Binding Errors

An `Integer` field receiving `"abc"` can fail conversion before reaching `@Min`. Do not expect a `Syntax`/`Business` sequence to handle parse errors: that is **data binding**, requiring `typeMismatch` handling and dedicated error messages.

### 12.9. Expecting a Single Error

Within the same `Required` stage, multiple fields can fail together. `Set<ConstraintViolation<?>>` does not guarantee order, so tests should assert **sets of failing fields and groups**, not "the first error is field X", unless the application explicitly sorts or prioritizes errors.

### 12.10. Using Sequences to Hide Important Business Errors

Sequences optimize error presentation and avoid running expensive constraints when foundational data is invalid. That does not prove errors in skipped stages do not exist. After the user fixes an earlier stage, errors from the next stage may surface; UX should account for that.

### 12.11. Redefining `Default` on Root and Expecting Child to Match Identically

Class-level `Default` redefinition has local scope. In an object graph with `@Valid`, groups traverse relationships per cascade rules; if a child needs a different policy, use explicit group conversion or child sequences and test actual behavior.

### 12.12. Mixing Java Validation Namespaces

Spring Framework 6+ uses `jakarta.validation.*` in the Jakarta ecosystem; older Spring 5.x projects typically use `javax.validation.*`. APIs, providers, and imports must align—do not just change package names on a few annotations and expect the build to work.

## 13. Essential Test Matrix

| Case | Input/configuration | Expectation |
| --- | --- | --- |
| `Required` fails | blank name, bad email, bad code | Only `Required` stage violations in sequence |
| `Required` passes, `Syntax` fails | valid name, bad email, bad code | `Syntax` fails; `Business` does not run |
| `Required`/`Syntax` pass, `Business` fails | valid email pattern, bad code | `Business` fails |
| All stages pass | Valid data | No violations |
| Multiple errors in one stage | Both name and email blank | Multiple `Required` violations possible |
| Calling groups directly | `validate(bean, Required.class, Business.class)` | No ordering or short-circuiting guaranteed |
| No group specified | `validate(bean)` with constraints only in custom groups | Only `Default` requested; custom groups do not run |
| Sequence interface with `Default` | `@GroupSequence({Default.class, Advanced.class})` | `Default` runs before `Advanced` when interface is requested |
| Class-level `Default` redefinition | `@GroupSequence({Bean.class, Advanced.class})` on `Bean` | Validates `Bean`'s `Default` following the sequence |
| Class-level missing bean class | Class annotation omits `Bean.class` | `GroupDefinitionException` |
| Cyclic sequence | Invalid `A → B → A` | `GroupDefinitionException` |
| Constraint in multiple groups | Same constraint declared in both groups | Not unconditionally re-run on the same validation path |
| Group inheritance | `Premium extends Required` | Inherits constraint set, does **not** create ordering |
| Child with `@Valid` | `Required` fails on child object | Subsequent groups do not run per the active ordered sequence |
| Root class default | Root redefines `Default`, has child | Local sequence does not propagate verbatim to child |
| Group conversion | `@ConvertGroup(from=Default.class,to=ChildChecks.class)` | Uses target group when cascading across that edge |
| Form conversion error | String cannot convert to `Integer` | Spring reports binding error; does not prove `@Min` group ran |
| Malformed JSON body | JSON deserialization fails | Fails reading request before object is validated |
| Spring MVC `@Validated` | `@Validated(OrderedChecks.class)` with `BindingResult` right after | Uses DTO sequence, collects field errors |
| Provider fail-fast | Hibernate Validator custom setting | May return fewer errors; not equivalent to `@GroupSequence` |
| Order testing | Multiple violations in one group | Do not rely on `Set` order; sort or compare sets |

### 13.1. Testing Without Depending on Message Text

With an available validator, you can verify the path set:

```java
Set<String> paths = validator.validate(form, OrderedChecks.class)
        .stream()
        .map(v -> v.getPropertyPath().toString())
        .collect(Collectors.toSet());

if (!paths.equals(Set.of("email"))) {
    throw new AssertionError("Unexpected validation phase: " + paths);
}
```

This is an **excerpt** inside a method/test where `validator` and `form` exist and `java.util.Set` and `java.util.stream.Collectors` are imported. This approach neither depends on the locale of `message` nor on the `Set` order returned by the provider.

For critical logic, also test:
- **Presence/absence** of violations from expected groups.
- **An expensive constraint** executing only after prerequisite stages pass, using an instrumented test validator without introducing side effects into production code.
- `BindingResult` on the actual Spring MVC endpoint, not just standalone Jakarta `Validator` calls.
- The interaction between root `Default` redefinition and nested children, especially when `@ConvertGroup` is present.

## 14. Design and Implementation Checklist

- [ ] Split constraints into groups **by data dependency**, not just memorable names.
- [ ] Declare `@GroupSequence` on an interface ordered from foundational to advanced conditions.
- [ ] Request the **sequence interface** at the validation site: `validator.validate(bean, Sequence.class)` or Spring `@Validated(Sequence.class)`.
- [ ] If placing `@GroupSequence` on a **class**, include **that class itself** in the list to redefine `Default`; do not substitute `Default.class`.
- [ ] Do not attach constraints to the sequence interface itself; attach them to component groups.
- [ ] Do not expect ordering among constraints in the same group or among multiple groups passed directly without a sequence.
- [ ] Test stage 1 failing, middle stage failing, final stage failing, and all stages passing.
- [ ] Clearly define group propagation through `@Valid`, group conversions, and the scope of each bean's `Default` redefinition.
- [ ] Do not use sequences to replace binding/JSON error handling, transactions, authorization, or service-layer business invariants.
- [ ] Verify execution with your project's actual Jakarta Validation provider and Spring dependencies.
- [ ] Avoid side effects in `ConstraintValidator`; do not assume a constraint is invoked exactly once across the entire object graph.
- [ ] In Spring MVC, ensure `BindingResult` immediately follows the validated parameter, or an exception handler is configured when `BindingResult` is omitted.

## Official Documents

- Jakarta Bean Validation 3.0 Specification, Sections 5.4 **Group and group sequence**, 5.4.2 **Group sequence**, 5.4.3 **Redefining the Default group for a class**: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation 3.0 — `@GroupSequence`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/GroupSequence.html
- Jakarta Validation 3.0 — `Validator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Validator.html
- Jakarta Validation 3.0 — `@ConvertGroup`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/groups/ConvertGroup.html
- Spring Framework 6.2 — Bean Validation: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — `@Validated`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/annotation/Validated.html
- Spring Framework 6.2 — `SpringValidatorAdapter`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/beanvalidation/SpringValidatorAdapter.html
- Hibernate Validator 8 — Reference Guide, Group sequences: https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/
