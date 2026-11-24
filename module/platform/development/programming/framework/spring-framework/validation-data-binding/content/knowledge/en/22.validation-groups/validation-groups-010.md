# Distinguishing `GroupSequence` from Error Ordering in Bean Validation Results

## 1. Two Completely Different Kinds of "Order"

In Spring Framework using **Jakarta Bean Validation**, validation groups let you organize constraints into purposeful sets: required fields, format checks, and deep business rules. Using `@GroupSequence`, developers can require an earlier group to **fully pass** before moving on to the next group.

However, the **execution order of constraint groups** is not the same as the **order of error elements returned**.

**Rules to remember:**

1. **`@GroupSequence`**: defines the **evaluation order across validation groups** and the mechanism to **stop before subsequent groups if the current group has at least one violation**.
2. **`Validator.validate(...)`**: returns **`Set<ConstraintViolation<T>>`**, a set of violations; **there is no guarantee on iteration order of errors**.
3. Within a **single group**, constraints likewise have no specification-guaranteed execution order, unless another rule in the spec applies. A group sequence does not turn constraints in the same group into an `A → B → C` queue.
4. If you need a **deterministic display order of errors** (for REST APIs, forms, or tests), the application must **sort** the results or define priority rules in the presentation layer. `@GroupSequence` does not do this.
5. When a group in a sequence fails, **that does not mean only one error remains**. In standard validation configuration, the set can still contain **multiple violations belonging to that first failing group**.

Conceptual model:

~~~text
@GroupSequence({Presence, Shape, Business})
          |
          v
  Presence: required input?
          |
     +----+----+
     |         |
  errors     no errors
     |         |
   STOP        v
         Shape: valid length/range?
               |
          +----+----+
          |         |
       errors     no errors
          |         |
         STOP       v
              Business: deep rules?
                        |
                  return result

Result of each validation run:
      Set<ConstraintViolation<T>>
                |
                | no ordering guaranteed
                v
   sort / map / present to client
~~~

An application can have a **correct** sequence and still return error JSON in a **different** order across two runs. That is not a bug in `@GroupSequence`, but a confusion between evaluation schedule and result-set representation.

## 2. Background: What Is a Group?

Every Jakarta Bean Validation constraint has a `groups` attribute specifying which groups it belongs to.

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

interface PresenceChecks {}
interface ShapeChecks {}

class UserRequest {

    @NotBlank(groups = PresenceChecks.class)
    @Size(min = 3, max = 12, groups = ShapeChecks.class)
    String username;
}
~~~

This is an **illustrative snippet**, not a standalone program. `@NotBlank` belongs to `PresenceChecks`, while `@Size` belongs to `ShapeChecks`. Both groups can be requested independently.

~~~java
validator.validate(request, PresenceChecks.class);
validator.validate(request, ShapeChecks.class);
~~~

With `request.username = ""`:

- `PresenceChecks`: `@NotBlank` fails.
- `ShapeChecks`: `@Size(min=3)` fails.
- If only `PresenceChecks` is validated, `ShapeChecks` **does not automatically run**.
- If calling `validator.validate(request)` without passing groups, the default group is `jakarta.validation.groups.Default`. In this example the constraints **all carry custom groups**, so no constraint on `UserRequest.username` belongs to `Default` from those annotations alone.

### Syntax and Group Scope

A group is typically a **marker interface** with no methods:

~~~java
public interface PresenceChecks {}
public interface ShapeChecks {}
public interface BusinessChecks {}
~~~

An annotation can belong to multiple groups:

~~~java
@NotNull(groups = {PresenceChecks.class, BusinessChecks.class})
private String reference;
~~~

A constraint can appear in multiple groups; when those groups are included in a sequence, the specification avoids re-evaluating a constraint already processed in an earlier group. Do not design business logic assuming the same validator is guaranteed to be called multiple times merely because multiple groups are listed.

**Distinguish group inheritance** from group sequences: `interface AdvancedChecks extends PresenceChecks {}` establishes group inheritance, yet does not define "Presence first, Advanced second". For ordering and per-stage stopping, use `@GroupSequence` per contract.

## 3. Without `GroupSequence`: Multiple Groups Have No Guaranteed Evaluation Order

Consider the call:

~~~java
validator.validate(request,
    PresenceChecks.class,
    ShapeChecks.class,
    BusinessChecks.class);
~~~

Many people assume Java varargs preserve order so the provider will run `Presence → Shape → Business` sequentially and stop if `Presence` fails. **This is false.**

Varargs arguments specify **which groups to validate**, not a stopping sequence. Per Jakarta Bean Validation, without `@GroupSequence`, the evaluation order of constraints/groups **is unconstrained**. Errors from multiple groups can appear together in the result set.

This holds even when:

~~~java
validator.validate(request,
    BusinessChecks.class,
    PresenceChecks.class);
~~~

reverses the argument order. Changing argument order **is not** a validation prioritization mechanism.

Comparison:

| Call | Requested groups | Ordered and stops later groups? |
| --- | --- | --- |
| `validate(bean)` | `Default` | No, unless the class's `Default` group redefines a sequence. |
| `validate(bean, PresenceChecks.class)` | Only `Presence` and matching inherited groups | No subsequent stage to stop. |
| `validate(bean, PresenceChecks.class, ShapeChecks.class)` | Both | **No guarantee** of ordering/stopping. |
| `validate(bean, OrderedChecks.class)` | Groups in the declared sequence | **Yes**, per sequence order and stopping rule. |
| `validate(bean, Default.class, BusinessChecks.class)` | `Default` and `Business` | Varargs position alone creates no sequence. |

**To get ordering**, define a sequence group annotated with `@GroupSequence` and request that exact group; do not reorder field annotations or varargs parameters.

## 4. What Does `GroupSequence` Actually Do?

The annotation is `jakarta.validation.GroupSequence`:

~~~java
import jakarta.validation.GroupSequence;

interface PresenceChecks {}
interface ShapeChecks {}
interface BusinessChecks {}

@GroupSequence({
    PresenceChecks.class,
    ShapeChecks.class,
    BusinessChecks.class
})
interface OrderedChecks {}
~~~

Here `OrderedChecks` is an **interface representing a group sequence**, not a field constraint. The call:

~~~java
validator.validate(request, OrderedChecks.class);
~~~

means:

1. Evaluate constraints in `PresenceChecks`.
2. If `Presence` produces **one or more violations**, return the corresponding validation results and **do not run `ShapeChecks` or `BusinessChecks`** in the sequence.
3. If `Presence` passes, evaluate `ShapeChecks`.
4. If `Shape` produces violations, **do not run `BusinessChecks`**.
5. If both prior groups pass, evaluate `BusinessChecks`.
6. If all three pass, the sequence's violation set is empty.

**It does not stop immediately upon finding the first failing constraint inside a group.** With a provider in standard mode, if `Presence` has two failing constraints, you can receive both `Presence` errors. What `@GroupSequence` guarantees is **skipping groups after a failing group**, not "returning only one error at a time".

When a provider enables **fail-fast** (a Hibernate Validator-specific mode), it can stop after the first detected error. Fail-fast and `GroupSequence` are two different features; section 14 contrasts them specifically.

### Conditions for a Valid Sequence Definition

- An interface annotated with `@GroupSequence` should be a marker interface **that does not extend other groups**.
- Do not attach constraints with `groups = OrderedChecks.class` on fields; attach constraints to **component groups**. The sequence only **combines groups and defines order**.
- Do not create direct or indirect cyclic sequences, including through group inheritance. When the provider detects a cycle, `GroupDefinitionException` is thrown.
- A component group can be formed from inheritance or another sequence, yet the ordering of the entire structure must remain consistent.
- `@GroupSequence` is neither JPA's `@SequenceGenerator` nor a sorting hint for Java collections.

## 5. Why Is `Set<ConstraintViolation<T>>` Unordered?

Jakarta `Validator` defines the signature:

~~~java
<T> Set<ConstraintViolation<T>> validate(
    T object, Class<?>... groups);
~~~

`Set` represents a collection of violating items and **promises no stable ordering** like `List`. Providers may use `Set.of(...)`, `HashSet`, or another implementation with different iteration order; the API does not require returning a `LinkedHashSet` in detection order. Therefore:

~~~java
for (ConstraintViolation<UserRequest> error : errors) {
    System.out.println(error.getMessage());
}
~~~

does not guarantee a rule like "required errors appear before length errors", even when one group ran before another. While errors from a sequence belong only to the first failing group, **errors within that group itself still have no specification-mandated order**.

Do not write tests like:

~~~java
// NOT RECOMMENDED: expecting the first element to be the priority error.
String first = errors.iterator().next().getMessage();
assertEquals("username is required", first);
~~~

especially when the set has more than one element. Do not try to "fix" it by wrapping into `ArrayList<>(errors)` and reading index 0: that list still inherits arbitrary order from the `Set`.

### Proper Way to Print Deterministically

~~~java
errors.stream()
    .map(v -> v.getPropertyPath() + " -> " + v.getMessage())
    .sorted()
    .forEach(System.out::println);
~~~

This illustrative snippet sorts by the **resulting string**, suitable for short demos. In production APIs, it is better to sort by **field/path, error code, and defined priority**, rather than relying on localized message text.

**The display order of errors** is a presentation decision; it does not tell you which constraint was evaluated first inside the validator.

## 6. Four Scenarios to Predict the Violation Set Accurately

Suppose there are three groups:

- **Presence:** `username` non-null/non-empty/non-blank, `age` non-null, `code` non-blank.
- **Shape:** `username` length 3–8 UTF-16 units, `age` at least 18.
- **Business:** `code` matches `[A-Z][A-Z0-9]{3,7}`, i.e., 4–8 ASCII characters starting with an uppercase letter.

Sequence: `Presence → Shape → Business`.

| Data | `Presence` | `Shape` | `Business` | Errors returned when validating sequence |
| --- | --- | --- | --- | --- |
| `username="", age=null, code="A123"` | **2 errors** | Skipped | Skipped | 2 `Presence` errors. |
| `username="Al", age=16, code="A123"` | Pass | **2 errors** | Skipped | 2 `Shape` errors. |
| `username="Alice", age=20, code="bad"` | Pass | Pass | **1 error** | 1 `Business` error. |
| `username="Alice", age=20, code="A123"` | Pass | Pass | Pass | Empty set. |

If `username="Al", age=16, code="bad"` is validated with **all three groups via varargs**, you can get **3 errors**: two from `Shape` and one from `Business`. Yet when validating **`OrderedChecks.class`**, you get **2 `Shape` errors**, because `Business` is skipped.

**Accurate statement:** `GroupSequence` affects **which errors are produced** by controlling which stages execute; it **does not impose a sort order** on the produced errors.

## 7. Runnable Example: Java 17 + Hibernate Validator 8

The example below tests the exact distinction between group sequencing and returned error ordering. Runs with **Java 17**, **Maven**, **Jakarta Bean Validation 3.0 API**, and **Hibernate Validator 8.0.6.Final** (provider). No Spring MVC or web server is required to observe the core contract.

Directory structure:

~~~text
group-sequence-demo/
├── pom.xml
└── src/
    ├── main/java/demo/GroupSequenceDemo.java
    └── test/java/demo/GroupSequenceDemoTest.java
~~~

### 7.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>group-sequence-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.6.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
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
~~~

`hibernate-validator` provides the implementation to run Jakarta Validation, while `expressly` provides EL for message interpolation in standalone Java SE apps. In Spring Boot projects using dependency management, prefer `spring-boot-starter-validation` and let the BOM manage versions rather than pinning dependencies as in this Maven demo.

### 7.2. `src/main/java/demo/GroupSequenceDemo.java`

~~~java
package demo;

import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.GroupSequence;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public class GroupSequenceDemo {

    public interface PresenceChecks {}
    public interface ShapeChecks {}
    public interface BusinessChecks {}

    @GroupSequence({
        PresenceChecks.class,
        ShapeChecks.class,
        BusinessChecks.class
    })
    public interface OrderedChecks {}

    public static final class Registration {
        @NotBlank(
            groups = PresenceChecks.class,
            message = "username required")
        @Size(
            min = 3, max = 8,
            groups = ShapeChecks.class,
            message = "username length 3..8")
        private final String username;

        @NotNull(
            groups = PresenceChecks.class,
            message = "age required")
        @Min(
            value = 18,
            groups = ShapeChecks.class,
            message = "age must be at least 18")
        private final Integer age;

        @NotBlank(
            groups = PresenceChecks.class,
            message = "code required")
        @Pattern(
            regexp = "[A-Z][A-Z0-9]{3,7}",
            groups = BusinessChecks.class,
            message = "code format invalid")
        private final String code;

        public Registration(
                String username, Integer age, String code) {
            this.username = username;
            this.age = age;
            this.code = code;
        }
    }

    static void show(
            String label,
            Set<? extends ConstraintViolation<?>> errors) {

        System.out.println(label + "=" + errors.size());

        // Strings are sorted so stdout does not depend on Set order.
        errors.stream()
            .map(v -> v.getPropertyPath() + " -> " + v.getMessage())
            .sorted()
            .forEach(System.out::println);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            show("presence-stop", validator.validate(
                new Registration("", null, "A123"),
                OrderedChecks.class));

            show("shape-stop", validator.validate(
                new Registration("Al", 16, "A123"),
                OrderedChecks.class));

            show("business-stop", validator.validate(
                new Registration("Alice", 20, "bad"),
                OrderedChecks.class));

            show("valid", validator.validate(
                new Registration("Alice", 20, "A123"),
                OrderedChecks.class));

            Registration mixed =
                new Registration("Al", 16, "bad");

            // Three groups requested, NOT a sequence.
            show("plain-groups", validator.validate(
                mixed,
                PresenceChecks.class,
                ShapeChecks.class,
                BusinessChecks.class));

            // Same object, explicitly requesting the sequence.
            show("ordered-groups", validator.validate(
                mixed, OrderedChecks.class));

            // No annotation in the example belongs to Default.
            show("default-only", validator.validate(
                new Registration("", null, "bad")));
        }
    }
}
~~~

### 7.3. Run and Output

Run in the directory containing `pom.xml` (requires JDK 17+, Maven, and permission to download dependencies on first run):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.GroupSequenceDemo
~~~

Stdout **produced by the program**, excluding any Maven/Hibernate Validator runtime logs:

~~~text
presence-stop=2
age -> age required
username -> username required
shape-stop=2
age -> age must be at least 18
username -> username length 3..8
business-stop=1
code -> code format invalid
valid=0
plain-groups=3
age -> age must be at least 18
code -> code format invalid
username -> username length 3..8
ordered-groups=2
age -> age must be at least 18
username -> username length 3..8
default-only=0
~~~

Explanation:

1. `presence-stop`: `username` is `""` and `age` is `null`, so two `Presence` constraints fail. `Shape` and `Business` **do not run** in the sequence.
2. `shape-stop`: `Presence` passes; `username` `"Al"` (length 2) and `age` `16` fail `Shape`; `Business` does not run. There are **two errors in the same group**, yet the order of those two lines comes from our `sorted()`, not from `GroupSequence`.
3. `business-stop`: `Presence` and `Shape` pass, `code` `"bad"` does not match the pattern; produces one `Business` error.
4. `valid`: all stages pass → 0.
5. `plain-groups`: three groups requested together without a sequence; yields two `Shape` errors and one `Business` error → 3.
6. `ordered-groups`: same `mixed` object using the sequence; `Shape` fails so `Business` does not run → 2.
7. `default-only`: every constraint in the example has explicit groups and none belong to `Default`. Calling `validate(bean)` does not include `OrderedChecks`, returning 0 even though multiple fields fail the custom groups. This is an **important design trap**, not proof that the object is valid under all rules.

**Do not remove `.sorted()`** and still claim the line order above is fixed: the content and error counts remain valid, while iteration order over individual violations is not guaranteed. In real tests, compare counts and path/message sets or sorted lists rather than guessing provider order.

## 8. Testing with JUnit 5

File `src/test/java/demo/GroupSequenceDemoTest.java`:

~~~java
package demo;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class GroupSequenceDemoTest {

    @Test
    void stopsAfterPresenceAndCanReturnMoreThanOneError() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var value = new GroupSequenceDemo.Registration(
                "", null, "A123");

            var errors = validator.validate(
                value, GroupSequenceDemo.OrderedChecks.class);

            assertEquals(2, errors.size());
            assertEquals(
                Set.of("username", "age"),
                errors.stream()
                    .map(v -> v.getPropertyPath().toString())
                    .collect(Collectors.toSet()));
        }
    }

    @Test
    void laterGroupIsSkippedWhenShapeFails() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var value = new GroupSequenceDemo.Registration(
                "Al", 16, "bad");

            var errors = validator.validate(
                value, GroupSequenceDemo.OrderedChecks.class);

            assertEquals(2, errors.size());
            assertEquals(
                Set.of("username", "age"),
                errors.stream()
                    .map(v -> v.getPropertyPath().toString())
                    .collect(Collectors.toSet()));
        }
    }

    @Test
    void passingEarlierGroupsAllowsBusiness() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var value = new GroupSequenceDemo.Registration(
                "Alice", 20, "bad");

            var errors = validator.validate(
                value, GroupSequenceDemo.OrderedChecks.class);

            assertEquals(1, errors.size());
            assertEquals("code",
                errors.iterator().next()
                    .getPropertyPath().toString());
        }
    }

    @Test
    void unorderedVarargsAndSequenceYieldDifferentSets() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var value = new GroupSequenceDemo.Registration(
                "Al", 16, "bad");

            var unordered = validator.validate(
                value,
                GroupSequenceDemo.PresenceChecks.class,
                GroupSequenceDemo.ShapeChecks.class,
                GroupSequenceDemo.BusinessChecks.class);

            var sequenced = validator.validate(
                value,
                GroupSequenceDemo.OrderedChecks.class);

            assertEquals(3, unordered.size());
            assertEquals(2, sequenced.size());
            assertTrue(unordered.stream()
                .anyMatch(e -> e.getPropertyPath().toString()
                    .equals("code")));
            assertTrue(sequenced.stream()
                .noneMatch(e -> e.getPropertyPath().toString()
                    .equals("code")));
        }
    }

    @Test
    void defaultIsNotTheCustomSequence() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var value = new GroupSequenceDemo.Registration(
                "", null, "bad");

            assertTrue(validator.validate(value).isEmpty());
            assertFalse(validator.validate(
                value,
                GroupSequenceDemo.OrderedChecks.class).isEmpty());
        }
    }

    @Test
    void validValuesPassAllStages() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var value = new GroupSequenceDemo.Registration(
                "Alice", 20, "A123");

            assertTrue(validator.validate(
                value,
                GroupSequenceDemo.OrderedChecks.class).isEmpty());
        }
    }

    @Test
    void normalizeErrorOrderExplicitlyForPresentation() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var value = new GroupSequenceDemo.Registration(
                "", null, "A123");

            var errors = validator.validate(
                value, GroupSequenceDemo.OrderedChecks.class);

            var sortedMessages = errors.stream()
                .map(ConstraintViolation::getMessage)
                .sorted()
                .toList();

            assertEquals(
                java.util.List.of("age required", "username required"),
                sortedMessages);
        }
    }
}
~~~

Run:

~~~bash
mvn test
~~~

With the sample configuration, the expected result is: **7 tests passed, 0 failed**. Key tests:

- Do not verify "Presence ran first" by `Set` element order; verify that **Shape/Business errors are absent when Presence fails**.
- Do not assert "there is only one error" when a stage fails; test **two errors in the same group**.
- For a given object, compare **varargs of ordinary groups** against the **group sequence**.
- When output ordering is needed, **explicitly sort** before comparing `List`s.

The example uses default Hibernate Validator without fail-fast enabled. In a custom provider configuration with fail-fast or other constraints, error counts can differ; lock down test conditions in setup and do not expect error counts beyond declared constraints.

## 9. `@GroupSequence` on an Interface vs. `@GroupSequence` on a Class

There are two uses of the **same annotation name** with different meanings.

### 9.1. Interface Sequence: Caller Explicitly Requests the Group

~~~java
@GroupSequence({
    jakarta.validation.groups.Default.class,
    ShapeChecks.class,
    BusinessChecks.class
})
public interface CompleteChecks {}
~~~

When declared on an interface, `CompleteChecks` represents an ordered combination. For it to take effect, call:

~~~java
validator.validate(bean, CompleteChecks.class);
~~~

If you only call `validator.validate(bean)`, Jakarta validates `Default` by default and **does not automatically know** you wanted `CompleteChecks`, unless a relevant class redefined its default group sequence.

Including `Default.class` in an **interface sequence** is valid. This is how you combine ordinary `Default` constraints with deeper groups while still stopping at the first failing group.

### 9.2. Class Sequence: Redefining `Default` for That Class

When you want every `validator.validate(invoice)` call to follow a specific order automatically:

~~~java
import jakarta.validation.GroupSequence;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

interface InvoiceDeepChecks {}

@GroupSequence({Invoice.class, InvoiceDeepChecks.class})
class Invoice {

    @NotBlank(message = "invoice number required")
    String number;

    @Min(value = 1, groups = InvoiceDeepChecks.class,
         message = "items must be positive")
    int itemCount;
}
~~~

Here **`@GroupSequence` is placed on `class Invoice`**. When validating `Invoice`'s `Default`:

1. The `Invoice.class` group, representing default constraints declared on the class, is checked first. Blank `number` → stops.
2. Only if the default part passes is `InvoiceDeepChecks` evaluated for `itemCount`.

**Very important rule:** when redefining `Default` for class `Invoice`, the sequence **must contain `Invoice.class`**, and must not replace it with `Default.class`:

~~~java
// INVALID when placed directly on class Invoice:
@GroupSequence({
    jakarta.validation.groups.Default.class,
    InvoiceDeepChecks.class
})
class Invoice { }
~~~

This example is **intentionally invalid and must not be copied into runnable projects**. It creates a cyclic dependency or omits the class itself from its default sequence per Jakarta rules, which can cause `GroupDefinitionException` when the provider processes metadata or validates.

**Remember the contrast:**

| Annotation placed on | Can write `Default` in sequence? | Group used during validation |
| --- | --- | --- |
| Interface `CompleteChecks` | Yes | Call `validate(bean, CompleteChecks.class)`. |
| Class `Invoice` to redefine `Default` | Must use **`Invoice.class`** instead of `Default.class` | `validate(invoice)` uses the new default sequence for that class. |

### 9.3. `Default` Override Is Local and Does Not Propagate Whole to Child Beans

A class redefining its own `Default` **does not cause `@Valid`-cascaded objects to automatically inherit an identical new sequence group**. Group propagation rules govern which group crosses each relationship; in standard scenarios, the parent's `Default` propagates as `Default` to child beans. Each child bean applies its own default-group semantics if configured.

If you need to switch groups on cascade, Bean Validation provides `@ConvertGroup`, which is a different concept from sorting errors. Test actual behavior across the object graph, especially when combining group conversion, sequences, and `Default` overrides.

## 10. Multiple Constraints in One Group Are Not Ordered by `@GroupSequence`

Example:

~~~java
interface PresenceChecks {}

class AccountForm {
    @NotBlank(groups = PresenceChecks.class)
    String username;

    @NotBlank(groups = PresenceChecks.class)
    String email;

    @NotNull(groups = PresenceChecks.class)
    Integer age;
}
~~~

If all three fields are missing, one `Presence` validation pass can produce three violations. `@GroupSequence({PresenceChecks.class, ...})` **does not** give you an ordering of "username before email before age".

Similarly, writing annotations on one field in order:

~~~java
@NotBlank(groups = PresenceChecks.class)
@Size(min = 3, groups = PresenceChecks.class)
String name;
~~~

does **not** mean `@NotBlank` is guaranteed to run before `@Size`. Both belong to the same group and both can fail when `name=""`. To split them into two stages, separate them into two distinct groups and define a sequence—but do that only when business rules **genuinely need conditional validation**, not merely to put one message "at the top" in the UI.

### `GroupSequence` Also Does Not Define `@Valid` Traversal Order

If an object contains multiple `@Valid` nested beans, the order in which a provider traverses properties or collections is also not a UI error-priority mechanism. A sequence defines **group order** across the spec-defined object graph processing, without turning every nested field and element into a fixed-order evaluation list.

Do not use side effects inside `ConstraintValidator.isValid(...)` to track order or write state that another validator depends on. Validators should be free of meaningful side effects; execution order is not a business serialization contract.

## 11. If You Only Want Errors Displayed in Priority Order, Do Not Use `GroupSequence`

Suppose a form has three errors: invalid username, invalid email, and invalid age. The requirement is simply to display:

1. Username.
2. Email.
3. Age.

If the business still wants **all three errors returned in the same response**, splitting them into three groups with `GroupSequence` would **drop the latter two errors** when the first group fails. That is usually choosing the **wrong tool for the goal**.

Instead:

~~~java
record ApiError(
    String field,
    String code,
    String message
) {}
~~~

After validating all relevant groups, map `ConstraintViolation`s into a list, then sort by the **UI's priority table**. For example:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import jakarta.validation.ConstraintViolation;

static <T> List<ApiError> toApiErrors(
        Set<ConstraintViolation<T>> errors) {

    Map<String, Integer> fieldRank = Map.of(
        "username", 0,
        "email", 1,
        "age", 2
    );

    return errors.stream()
        .map(v -> new ApiError(
            v.getPropertyPath().toString(),
            v.getConstraintDescriptor().getAnnotation()
                .annotationType().getSimpleName(),
            v.getMessage()))
        .sorted(Comparator
            .comparingInt(
                (ApiError e) ->
                    fieldRank.getOrDefault(e.field(), 999))
            .thenComparing(ApiError::field)
            .thenComparing(ApiError::code)
            .thenComparing(ApiError::message))
        .toList();
}
~~~

This is an **illustrative mapping snippet** that belongs inside a class with `ApiError` and the relevant imports, not a standalone runnable file. It sorts by the defined rank, then uses field/code/message as tie-breakers for deterministic ordering. If an API has multiple violations on the same field, all items are preserved.

**Do not rely on `getMessage()` as a stable error code.** Messages can change with locale and interpolation. For a durable public error contract, define dedicated business error codes and map from the corresponding constraint metadata.

If you only want **one message per field**, you can add a priority selection strategy—for example `REQUIRED` before `SIZE` before `PATTERN`. That is still presentation/response handling, not a reason to introduce `@GroupSequence`. Expensive checks or rules that depend on already-valid data are the right reasons to split validation stages.

## 12. When Should You Actually Use `GroupSequence`?

`GroupSequence` is valuable when **an earlier stage must pass before a later stage makes sense**:

- **Basic checks before deep checks:** run consistency/business constraints only after required fields and basic data formats pass.
- **Avoiding costly computation:** a later group's validation may be heavier; evaluate it only when input is good enough. Even so, validators generally should not perform heavy I/O or side effects.
- **Implementing staged policies:** data must satisfy `PresenceChecks`, then `ShapeChecks`, and finally `BusinessChecks`.
- **Redefining `Default` for a specific bean:** you want `validate(bean)` by default to progress through that bean's appropriate stages.

`GroupSequence` is **not appropriate** when the goal is merely:

- Sorting error messages by field name.
- Forcing a single error to be displayed.
- Making JSON error lines appear in a fixed order across runs.
- Predicting which constraint within the same group runs first.
- Catching every error across all groups even when an earlier group already failed.

To display **all errors in one pass**, review a policy of running groups together (without sequence short-circuiting) and then sort the results. To report errors **in logical stages**, use a sequence and clearly explain to users why deeper-stage errors have not appeared yet.

## 13. Interaction with `@Valid`, Collections, and Nested Groups

When `@Valid` is present, Bean Validation can descend into non-null child objects. Requested groups and group sequences govern how constraints across the object graph are evaluated.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

class Order {
    @NotNull(groups = PresenceChecks.class)
    @Valid
    Customer customer;
}
~~~

If `customer == null`, `@Valid` does not fabricate a child bean; `@NotNull` in `PresenceChecks` produces a violation. If `Presence` fails in the sequence, subsequent stages are skipped.

If `customer != null`, `Customer`'s constraints can be cascaded per the active group semantics. The nested bean itself may also declare `@GroupSequence` or `@ConvertGroup`. Never assume every constraint on a nested bean always runs simply because the parent has `@Valid`.

### Key Boundaries

- `@Valid` is **cascading**, not a constraint like `@NotNull`.
- A group sequence on the parent is not simply a traversal order over child list elements.
- `@ConvertGroup(from=..., to=...)` can switch groups when entering a cascade edge; `from` applies to the group already expanded from the sequence. Do not put a sequence name in `from` expecting it to match as an unexpanded group.
- When two child objects fail in the same stage, the combined `Set` still has no guaranteed display order.
- If a class redefines `Default`, that redefinition is local; it does not carry the whole sequence automatically to related objects.

**Practice:** with multi-level object graphs, write dedicated tests verifying **which groups ran or did not run**, **violation counts**, and **paths**. Never write tests that inspect `Set` order to infer traversal order.

## 14. `GroupSequence` vs. Fail-Fast and `@ReportAsSingleViolation`

Three features can all result in **fewer errors**, yet they are fundamentally different:

| Feature | What does it control? | Guarantees `Set` error order? |
| --- | --- | --- |
| `@GroupSequence` (Jakarta standard) | **Group** evaluation order and skipping **subsequent groups** when an earlier group fails. | **No**. |
| Hibernate Validator **fail-fast** (provider-specific) | Can stop entire validation after one detected violation, without specifying which violation comes first. | **No**. |
| `@ReportAsSingleViolation` (Jakarta standard) | For a **composed constraint**, replaces constituent constraint errors with one composite violation. | **No**. |
| Application `Comparator`/sort | **Presentation** order of the list, without changing which constraints were evaluated. | **Ordered after sorting**, though the original `Set` remains unordered. |

### Illustrative Example

Suppose `Presence` has three failing constraints:

- Using `@GroupSequence` alone: you can get all three `Presence` errors; `Shape` and `Business` do not run.
- Enabling Hibernate Validator fail-fast: you may get only **one error** as the provider stops on the first violation it hits (with no guarantee which constraint that is).
- Using a composed constraint with `@ReportAsSingleViolation`: multiple failing sub-constraints inside that composite produce **one combined violation** for that constraint, while other independent constraints can still produce errors.
- Calling `.sorted()`: same error count and same executed groups; only the presentation order changes.

Do not use fail-fast to "pick the highest-priority error" without an explicit priority rule, since providers do not guarantee constraint order unless another specific mechanism defines it and is properly used. To prioritize errors, define a handling strategy in application code.

## 15. Misconfiguration: `GroupDefinitionException` and Wrong-Group Constraints

### 15.1. Creating a Sequence Cycle

Intentionally flawed example:

~~~java
interface Alpha {}
interface Beta {}

@GroupSequence({Alpha.class, Beta.class})
interface AThenB {}

@GroupSequence({AThenB.class, Alpha.class})
interface CyclicChecks {} // This alone does not create a cycle yet.
~~~

**Note:** the snippet above might not actually create a cycle; it only illustrates nested sequences and repeated groups. A **real cycle** occurs when `A` requires a sequence containing `B`, while `B` directly or indirectly requires `A`. Rather than distorting the contract with a long, fragile Java example, remember the criterion instead of treating the snippet above as an exception-throwing demo.

When the provider detects a genuine cycle in group sequences or group inheritance, `GroupDefinitionException` is an application declaration/configuration bug, **not a user request data error**. Never automatically return it as an HTTP 400 "invalid field" error.

### 15.2. Confusing Interfaces and Classes

~~~java
// CORRECT when declared on an interface:
@GroupSequence({
    jakarta.validation.groups.Default.class,
    ShapeChecks.class
})
interface CompleteChecks {}
~~~

~~~java
// CORRECT when redefining Default directly on a class:
@GroupSequence({
    RequestForm.class,
    ShapeChecks.class
})
class RequestForm {}
~~~

The second snippet is a minimal **illustration** of the class; real projects need constraints and target objects to validate. Replacing `RequestForm.class` with `Default.class` inside the class's own annotation breaks the rule and can throw `GroupDefinitionException`.

### 15.3. Assigning Constraints to the Sequence Instead of Component Groups

~~~java
// NOT RECOMMENDED:
@NotBlank(groups = OrderedChecks.class)
String title;
~~~

An interface representing a sequence should not be used directly in constraint declarations. Assign constraints to `PresenceChecks.class` or `ShapeChecks.class`. This keeps the contract "which stage checks this condition?" transparent.

### 15.4. Confusing `Default` with All Groups

~~~java
validator.validate(bean);
~~~

**Does not automatically invoke** every user-defined group. If a constraint belongs solely to `BusinessChecks`, it does not run implicitly in `Default`. To include business groups, pass the specific group/sequence or redefine `Default` on the class appropriately.

## 16. Integrating with Spring Framework / Spring Boot

Spring supports Bean Validation via Jakarta `Validator` and validation trigger points. **`@GroupSequence` is a Jakarta annotation**, whereas **`@Validated` is a Spring annotation** that selects groups when applying validation at supported boundaries.

For a Spring Boot 3 project that already has a parent/BOM managing versions:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

This is a dependency snippet for a **Spring Boot project**, not a complete standalone `pom.xml`.

### 16.1. Selecting a Group Sequence for a Controller DTO

~~~java
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.ResponseEntity;

@RestController
class RegistrationController {

    @PostMapping("/registrations")
    ResponseEntity<Void> register(
            @Validated(GroupSequenceDemo.OrderedChecks.class)
            @RequestBody
            GroupSequenceDemo.Registration request) {

        // Business processing after validation passes.
        return ResponseEntity.noContent().build();
    }
}
~~~

This is a **Spring MVC integration snippet**, not a standalone runnable app. In a real app, make `Registration` a DTO compatible with JSON deserialization (constructor/record/properties supported by Jackson), ensure a Bean Validation provider is present, and ensure classes are discovered by Spring. The core exercise in section 7 used an immutable `Registration` for direct `Validator` testing rather than designing it as a production Jackson DTO.

`@Validated(OrderedChecks.class)` explicitly requests the sequence. If you only use:

~~~java
@Valid @RequestBody RegistrationRequest request
~~~

then `Default` applies, unless the class redefined `Default`. `@Valid` **does not** automatically pick `OrderedChecks.class` merely because that interface exists.

### 16.2. Distinguishing Validation Errors from Response Ordering

In Spring MVC, when validating a `@RequestBody` object via `@Validated`/`@Valid` fails, the app typically receives `MethodArgumentNotValidException` and `BindingResult`/`FieldError` in standard controller setups. With Spring MVC 6.1+ method validation where constraints sit directly on method parameters, you may receive `HandlerMethodValidationException`. Proxy-based service method validation may throw `ConstraintViolationException` or an adapted exception if configured.

**Do not cast** `FieldError` to `ConstraintViolation<?>`. They are different error models. Similarly, even though group execution order is fixed, the element order in `BindingResult.getFieldErrors()` **should not be treated as a cross-version display priority contract** when an API needs stable ordering. Map and sort explicitly by field + code/priority.

Illustrative handler:

~~~java
@ExceptionHandler(MethodArgumentNotValidException.class)
ResponseEntity<List<ApiError>> handle(
        MethodArgumentNotValidException ex) {

    List<ApiError> errors = ex.getBindingResult()
        .getFieldErrors().stream()
        .map(e -> new ApiError(
            e.getField(),
            e.getCode() == null ? "INVALID" : e.getCode(),
            e.getDefaultMessage()))
        .sorted(Comparator
            .comparing(ApiError::field)
            .thenComparing(ApiError::code))
        .toList();

    return ResponseEntity.badRequest().body(errors);
}
~~~

This is an **illustrative snippet inside `@RestControllerAdvice`**, requiring the imports and `ApiError` record from section 11; it is not a standalone class. Sorting with `Comparator` gives responses deterministic order even though the error source defines none. In real applications, handle nullability of messages/codes, define stable business error codes, and avoid exposing sensitive values (`rejectedValue`/`invalidValue`) to clients.

### 16.3. `@Validated` on Services

With Spring method validation via `@Validated`/`MethodValidationPostProcessor`, a method with parameter or return-value constraints invoked through a Spring proxy can use the selected group. However, this is the **method validation path**, distinct from calling `Validator.validate(bean, OrderedChecks.class)`. Do not expect calling `new Service().method()` directly to run AOP validation or the sequence.

Group sequences matter on both paths when **properly requested**, yet exception types and violation-to-response mapping can differ. Write integration tests following the real pipeline.

## 17. Designing Tests That Avoid False Ordering Assumptions

Good tests focus on **the contents of the error set** and **skipped groups**, rather than incidental provider iteration order.

### Good Test

~~~java
var errors = validator.validate(
    request, OrderedChecks.class);

assertEquals(2, errors.size());
assertEquals(
    Set.of("username", "age"),
    errors.stream()
        .map(v -> v.getPropertyPath().toString())
        .collect(java.util.stream.Collectors.toSet()));
~~~

This is an **illustrative snippet** with `request` holding invalid `Presence` data and appropriate JUnit imports. It verifies two failing fields without depending on order.

### Fragile Test

~~~java
var errors = validator.validate(
    request, OrderedChecks.class);

// FRAGILE if errors has multiple elements:
assertEquals(
    "username",
    errors.iterator().next().getPropertyPath().toString());
~~~

This test may pass on one provider/JDK and fail on another without any change to the group sequence policy.

### Testing Output Order at the Right Layer

~~~java
List<String> sortedPaths = errors.stream()
    .map(v -> v.getPropertyPath().toString())
    .sorted()
    .toList();

assertEquals(List.of("age", "username"), sortedPaths);
~~~

This tests **order after sorting**, not the order in which Bean Validation ran constraints.

### Tests Should Not Rely on Custom Validator Logs

You can create a custom `isValid` logging "group A" or "group B" while investigating, yet never turn those internal logs into **an ordering contract for constraints within the same group**. Validators can be cached, reused, or invoked through different object-graph traversals; provider-specific fail-fast makes "first error" ordering even less predictable.

Keep three separate test suites:

1. **Validation scope:** which groups were requested and what kinds of errors exist.
2. **Short circuit:** later groups are genuinely skipped when an earlier group fails.
3. **Presentation:** error lists are sorted per client-required criteria.

## 18. Common Mistakes and Fixes

| Misconception | Consequence | Correct approach |
| --- | --- | --- |
| Thinking `@GroupSequence` sorts `Set<ConstraintViolation>` | API returns errors in unexpected order. | Explicitly sort when mapping to `List`/JSON. |
| Thinking a sequence returns only **one** violation | Misses errors in the same stage. | `GroupSequence` stops **later groups**, not individual constraints by default. |
| Passing `validate(bean, A.class, B.class)` thinking it means `A → B` | Both groups may run with no short-circuiting. | Define `@GroupSequence({A.class,B.class})` and invoke the sequence interface. |
| Reordering field annotations to control the first error | Providers make no guarantee. | Group by real business dependency or sort UI errors. |
| Putting `groups=Ordered.class` directly on a constraint | Confuses sequence interface with component group. | Assign constraints to `Presence`/`Shape`/`Business`. |
| Defining a sequence interface then calling `validate(bean)` | Only `Default` runs; sequence does not activate itself. | Pass the sequence or intentionally redefine `Default`. |
| Putting `@GroupSequence({Default.class, Deep.class})` on a class | Violates `Default` redefinition rule. | Use `@GroupSequence({MyClass.class, Deep.class})`. |
| Using a sequence to order form errors while still wanting all errors | Later groups are skipped when an earlier group fails. | Validate all needed groups and sort results. |
| Using `iterator().next()` as the priority error | `Set` order is not guaranteed. | Process all errors, then sort/rank explicitly. |
| Enabling fail-fast thinking it follows field priority | "First error" has no standard priority. | Define priority policy in application code. |
| Assuming child beans inherit parent's default sequence verbatim | `Default` redefinition is local; propagation follows group semantics. | Test `@Valid`/`@ConvertGroup` and configure `Default` on the right class. |
| Thinking `@Validated({A.class,B.class})` is a sequence | An array of groups is not `@GroupSequence`. | Use `@Validated(Ordered.class)` when ordering is required. |
| Treating every validation exception as a 400 input error | `GroupDefinitionException` can be a server metadata bug. | Separate configuration errors from user data errors. |
| Returning raw `ConstraintViolation` with `invalidValue` in JSON | Can leak passwords, PII, and internal structure. | Map safely to field/code/message. |
| Checking only error count without checking blocked later groups | Misconfigured groups can still yield the same count. | Check property paths/messages to confirm the stage. |
| Using message text as the primary error code and sort key | Messages depend on locale. | Use business error codes and explicit comparators. |
| Writing custom validators with side effects relying on call order | Logic breaks across providers/versions. | Keep validators independent and read-only. |

## 19. Practical Project Adoption Checklist

1. List constraints belonging to `Default`, `PresenceChecks`, `ShapeChecks`, and `BusinessChecks`.
2. Identify **which constraints must pass first** before deeper constraints can be evaluated.
3. Choose a **sequence interface** if callers select it explicitly, or a **class-level `Default` override** if it is the bean's default contract.
4. When using an interface sequence, avoid extending other groups and do not attach constraints directly to the sequence group.
5. When redefining `Default` on a class, remember `@GroupSequence({MyClass.class, ...})`.
6. Never create cyclic sequences, even through inheritance or nested sequences.
7. Do not confuse multi-group varargs with a sequence group.
8. Test when **`Presence` fails multiple constraints**: receive errors from that group while later groups are skipped.
9. Test when `Presence` passes yet `Shape` fails: `Business` is skipped.
10. Test when all earlier groups pass: `Business` actually runs.
11. Test the difference between `validate(bean, A.class,B.class)` and `validate(bean, Ordered.class)`.
12. Keep direct Bean Validation tests separate from Spring MVC/`@Validated`/AOP tests where applicable.
13. Never trust `Set` order; sort by field, code, and UI priority when converting to a list.
14. If fail-fast or composed constraints are enabled, re-test **error counts and scope** under that configuration.
15. Verify `@Valid` cascading, group conversion, and `Default` redefinition across nested object graphs.
16. Never expose `getInvalidValue()`, stack traces, or sensitive metadata in responses.
17. Document for clients whether returned errors represent **all errors** or **errors of the first failing stage**. That API behavior difference can matter greatly.

### Review Questions

1. Does `@GroupSequence({Basic.class, Deep.class})` force `Set<ConstraintViolation<?>>` to return `Basic` errors before `Deep` errors?
2. `Basic` has two failing constraints and `Deep` has three failing constraints. When running the sequence (without fail-fast), how many errors can be returned and is `Deep` checked?
3. Is calling `validator.validate(bean, Basic.class, Deep.class)` equivalent to invoking the sequence?
4. How does `@GroupSequence` on an interface differ from `@GroupSequence` on a class?
5. For class `Invoice` redefining `Default`, should the sequence contain `Default.class` or `Invoice.class`?
6. An API wants to return **all errors** and list `name` before `age`: should you use `GroupSequence` to sort or sort after validation?
7. Can you rely on `violations.iterator().next()` as the highest-priority error?
8. Why does `@Validated({Basic.class,Deep.class})` not mean `Basic → Deep`?
9. How are Hibernate Validator fail-fast and `GroupSequence` similar, and how do they differ?
10. If a parent class has a `@Valid` nested bean and redefines `Default`, can you assume the parent's entire sequence propagates intact to the child bean?

**Answers:** (1) No, a sequence governs **evaluation** order and stopping later groups, not `Set` order; (2) 2 `Basic` errors can be returned and `Deep` is skipped; (3) No, varargs do not create a sequence; (4) an interface sequence must be requested explicitly, whereas a class sequence redefines `Default` locally; (5) `Invoice.class`; (6) validate the required scope and then sort the response; (7) No; (8) an array of groups carries no ordering contract; (9) both can reduce error counts, but `GroupSequence` stops between groups while fail-fast stops on detection per provider behavior; (10) No, default override has local scope and distinct propagation rules.

## 20. Official References

- Jakarta Bean Validation 3.0 Specification — *Group sequence*, *Redefining the Default group for a class*, *Validation routine*: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Bean Validation 3.0 API — `GroupSequence`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/GroupSequence.html
- Jakarta Bean Validation 3.0 API — `Validator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Validator.html
- Jakarta Bean Validation 3.0 API — `ConstraintViolation`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintViolation.html
- Jakarta Bean Validation 3.0 API — `GroupDefinitionException`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/GroupDefinitionException.html
- Hibernate Validator 8.0 — Reference Guide, *Defining group sequences*, *Redefining default group sequence*, and *Fail fast*: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Hibernate Validator 8.0 releases, Maven coordinates: https://hibernate.org/validator/releases/8.0/
- Spring Framework — Validation, Data Binding, Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation.html
- Spring Framework — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
