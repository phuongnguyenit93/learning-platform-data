# Redefining the `Default` Group for a Class in Jakarta Bean Validation

## 1. Why Redefine the `Default` Group?

In Java/Spring applications, a bean often has several categories of rules:

- **Basic:** non-empty name, positive quantity, required fields present.
- **Consistency:** fields must be mutually compatible or an internal state must be confirmed.
- **Approval:** only accepted once a final condition is met.

If all constraints run simultaneously, users can receive approval-step errors even when the input code or quantity is not yet valid. Jakarta Bean Validation lets you order **validation groups** and stop before later groups when an earlier group fails.

There are two ways to use `@GroupSequence`:

1. Place it on an **interface** to create a composite group of ordered sub-groups; callers request it explicitly with `validator.validate(bean, MySequence.class)`.
2. Place it on the **validated class itself** to **redefine the `Default` group for that class only**. When callers invoke `validator.validate(bean)` as usual, the new sequence applies automatically.

This article focuses on the second approach: **class-level default group sequence redefinition**.

Example requirement: when validating an `Invoice`, the system always wants to run *Basic → Consistency → Approval*, even when the caller only requests the default group. You do not want every service or controller to have to remember the name `CompleteInvoiceChecks`.

**Learning objectives:** know how to declare `@GroupSequence` on a class; understand why it must contain **the class itself**, not `Default.class`; master group stopping rules; understand local scope and `@Valid` cascade behavior; verify with Java 17 and Spring MVC integration.

## 2. Reviewing the `Default` Group and Custom Groups

### 2.1. What Is `Default`?

`jakarta.validation.groups.Default` is the marker interface for the default group. A constraint without `groups` specified belongs to `Default`:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

@NotBlank
private String code;

@Min(1)
private int quantity;
```

These are two illustrative field declarations, not a runnable class. By default:

```java
validator.validate(invoice);
validator.validate(invoice, jakarta.validation.groups.Default.class);
```

both calls request the `Default` group. If the `Invoice` class redefines `Default`, **both invocation styles** are governed by the declared sequence.

### 2.2. Custom Groups

Groups are typically marker interfaces:

```java
interface ConsistencyChecks {}
interface ApprovalChecks {}
```

Constraints assigned to custom groups:

```java
import jakarta.validation.constraints.AssertTrue;

@AssertTrue(groups = ConsistencyChecks.class)
private boolean consistent;
```

When a class has not redefined `Default`, calling `validate(bean)` normally does **not** run constraints belonging solely to `ConsistencyChecks`.

### 2.3. Passing Multiple Groups Does Not Create Ordering

```java
validator.validate(invoice,
        ConsistencyChecks.class,
        ApprovalChecks.class);
```

This requests two groups, yet **does not guarantee** `ConsistencyChecks` will finish before `ApprovalChecks` simply because it appears earlier in the argument list. When order is a business requirement, use `@GroupSequence`.

| Mechanism | Evaluation order | Stops before later group? |
| --- | --- | --- |
| `validate(bean)` without sequence | `Default` group only | No subsequent tier |
| `validate(bean, A.class, B.class)` | No order guaranteed from parameter list alone | Not based on parameter order |
| `@GroupSequence({A.class, B.class})` on interface and requesting that interface | Yes: `A` then `B` | Yes, if `A` has violations |
| `@GroupSequence({Bean.class, A.class})` on class and requesting `Default` | Yes: class group then `A` | Yes, if class group has violations |

**Note:** there is no guaranteed ordering **among constraints within the same group**. Only the ordering across tiers established by the sequence is guaranteed.

## 3. Declaring `@GroupSequence` on a Class

### 3.1. Standard Syntax

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

interface ConsistencyChecks {}
interface ApprovalChecks {}

@GroupSequence({
    Invoice.class,
    ConsistencyChecks.class,
    ApprovalChecks.class
})
class Invoice {

    @NotBlank
    String code;

    @Min(1)
    int quantity;

    @AssertTrue(groups = ConsistencyChecks.class)
    boolean consistent;

    @AssertTrue(groups = ApprovalChecks.class)
    boolean reviewed;
}
```

This is an illustrative class without constructors or a runner. A standalone runnable Java 17 example is provided in section 6.

`@GroupSequence` on the `Invoice` class itself means: **when validating the `Default` group for `Invoice`, replace that `Default` group with the declared group sequence**.

```text
validator.validate(invoice)
            |
            v
    Requests Default group
            |
            v
@GroupSequence on Invoice
            |
            v
[1] Invoice.class
    @NotBlank code
    @Min quantity
            |
        Has errors?
        /    \
      Yes     No
      |        |
    Stop       v
       [2] ConsistencyChecks
           @AssertTrue consistent
                   |
               Has errors?
               /    \
             Yes     No
             |        |
           Stop       v
              [3] ApprovalChecks
                  @AssertTrue reviewed
                      |
                      v
                   Finish
```

The goal is not "run every constraint at most once", but rather **progressively deepen validation once foundational state is valid**.

### 3.2. Why Must `Invoice.class` Be Placed in the Sequence?

The Jakarta Validation specification defines an *implicit grouping* rule: constraints belonging to `Default` and declared on class `A` also **implicitly belong to group `A`**.

Therefore, in the example above, `Invoice.class` represents the `Default` constraints declared on the class: `@NotBlank code` and `@Min quantity`. This is how basic constraints are preserved when redefining `Default`.

If the redefinition is placed on a class `A`, the sequence **must contain `A.class`**. Otherwise, the provider may throw `jakarta.validation.GroupDefinitionException` during validation or metadata inspection. This requirement holds even if the class has very few constraints.

**CORRECT:**

```java
@GroupSequence({Invoice.class, ConsistencyChecks.class})
class Invoice {
    // Field/constraint declarations of Invoice
}
```

**WRONG — missing the class itself:**

```java
@GroupSequence({ConsistencyChecks.class, ApprovalChecks.class})
class Invoice {
    // Sequence does not contain Invoice.class
}
```

### 3.3. Do Not Put `Default.class` in a Class-Level Sequence

A fairly common mistake:

```java
import jakarta.validation.groups.Default;

@GroupSequence({Default.class, ConsistencyChecks.class})
class Invoice {
    // Invalid when placing the sequence on Invoice itself
}
```

You are **redefining `Default`** while putting `Default` itself inside its replacement definition, creating a cyclic dependency. This is not how you retain default constraints. Use `Invoice.class`, not `Default.class`.

Comparison: `@GroupSequence({Default.class, OtherChecks.class})` can be **valid on a standalone sequence interface**, but must not be used to redefine `Default` on a class in that way. Distinguishing these two contexts is the most important takeaway of this topic.

### 3.4. What Happens When a Sequence Fails?

If an earlier tier has **one or more violations**, subsequent groups in the sequence **are not evaluated**. However, every constraint within the currently executing tier can still produce violations.

For example, `code=""`, `quantity=0`, `consistent=false`, `reviewed=false`:

- The `Invoice.class` tier produces **two** violations: `@NotBlank` and `@Min`.
- `ConsistencyChecks` and `ApprovalChecks` do not run.
- You cannot say "the sequence stops at the very first constraint" unless a provider-specific mode is enabled.

With `code="INV-1"`, `quantity=1`, `consistent=false`: the basic tier passes, consistency fails, so approval is skipped.

## 4. How Does This Differ from `@GroupSequence` on an Interface?

An interface sequence creates **a composite group invoked on demand**:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

interface DetailedChecks {}

@GroupSequence({
    Default.class,
    DetailedChecks.class
})
interface FullValidation {}
```

When calling:

```java
validator.validate(bean, FullValidation.class);
```

the provider executes `Default` and then `DetailedChecks` if `Default` passes. However, if you only call `validator.validate(bean)` and the class has **no** redefinition, `FullValidation` is not automatically selected.

With class-level redefinition:

```java
@GroupSequence({Invoice.class, ConsistencyChecks.class})
class Invoice {
    // Class fields/constraints
}
```

the call `validator.validate(invoice)` itself triggers the sequence.

| Aspect | Interface-level | Class-level |
| --- | --- | --- |
| Annotation placed on | Interface | Bean class |
| When sequence runs | Caller requests the sequence interface | Whenever `Default` is validated on the class |
| Can declare `Default.class` | Yes, if it does not cause a group cycle | Cannot be used in the sequence replacing the class's own `Default` |
| Must contain the bean class itself | No (not a class redefinition) | Yes |
| Blast radius | Per use case invoking the sequence | Every flow requesting `Default` on that class |
| Best suited for | Multiple validation levels chosen by caller | Class's `Default` always needs its own ordering |

When an application shares a DTO across many use cases, think carefully: redefining `Default` changes behavior for **every** caller validating `Default` on that class. If some flows only want basic fields checked, an interface sequence with separate groups may be easier to manage.

## 5. Sequences Run by Group, Not by Individual Error

### 5.1. One Group Can Produce Multiple Errors

Even though `Invoice.class` comes first, it still contains multiple constraints. With an empty code and quantity zero, you can receive two violations simultaneously in the first tier. Only **subsequent tiers** are skipped.

Do not assume any order in the `Set<ConstraintViolation<?>>` returned by Jakarta `Validator`. When mapping errors to a response or unit test, sort by field/code/message when deterministic output is needed.

### 5.2. Avoid Side Effects in `ConstraintValidator`

Multiple groups mean multiple evaluation steps, and providers are free to optimize execution. A constraint present in multiple groups of a sequence must not be used as a mechanism to trigger side effects multiple times.

Write `ConstraintValidator`s so they do not mutate data, send emails, or write to a DB automatically. Validation may run multiple times from controllers, services, or batch jobs.

### 5.3. Do Not Confuse with Hibernate Validator Fail-Fast

Hibernate Validator has its own **fail-fast** mode to stop after detecting a single constraint violation, yet it does not guarantee which error within the same group is detected first. `@GroupSequence` is the **Jakarta standard** mechanism ensuring group ordering, whereas fail-fast is a **provider-specific** feature. They solve two different problems.

## 6. Standalone Java 17: Three-Tier `Default` Redefinition

This program uses Hibernate Validator 8 as the Jakarta provider, with four input cases. Each group has fixed messages for easy inspection. Messages are **sorted** before printing to avoid depending on `Set` order.

### 6.1. Structure and Dependencies

```text
default-sequence-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/DefaultSequenceDemo.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'default-sequence-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.hibernate.validator:hibernate-validator:8.0.6.Final'
    implementation 'org.glassfish.expressly:expressly:5.0.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'DefaultSequenceDemo'
}
```

`hibernate-validator` is the Jakarta Bean Validation 3.0 provider; `expressly` provides the Jakarta EL implementation for message interpolation. With Spring Boot, use `spring-boot-starter-validation` and Boot's BOM to manage versions instead of manually aligning library versions.

### 6.2. `DefaultSequenceDemo.java`

```java
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.GroupSequence;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public class DefaultSequenceDemo {

    interface ConsistencyChecks {}
    interface ApprovalChecks {}

    @GroupSequence({
        Invoice.class,
        ConsistencyChecks.class,
        ApprovalChecks.class
    })
    public static final class Invoice {

        @NotBlank(message = "code.required")
        private final String code;

        @Min(value = 1, message = "quantity.min")
        private final int quantity;

        @AssertTrue(
            groups = ConsistencyChecks.class,
            message = "consistency.failed"
        )
        private final boolean consistent;

        @AssertTrue(
            groups = ApprovalChecks.class,
            message = "approval.failed"
        )
        private final boolean approved;

        public Invoice(
                String code, int quantity,
                boolean consistent, boolean approved) {
            this.code = code;
            this.quantity = quantity;
            this.consistent = consistent;
            this.approved = approved;
        }
    }

    private static String messages(
            Set<ConstraintViolation<Invoice>> violations) {
        if (violations.isEmpty()) {
            return "PASS";
        }

        return violations.stream()
                .map(ConstraintViolation::getMessage)
                .sorted()
                .collect(Collectors.joining(","));
    }

    private static void check(
            String label, Invoice bean, Validator validator) {
        Set<ConstraintViolation<Invoice>> violations =
                validator.validate(bean);

        System.out.println(label + ": " + messages(violations));
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            check("basic",
                    new Invoice("", 0, false, false),
                    validator);

            check("consistency",
                    new Invoice("INV-1", 1, false, false),
                    validator);

            check("approval",
                    new Invoice("INV-1", 1, true, false),
                    validator);

            check("valid",
                    new Invoice("INV-1", 1, true, true),
                    validator);
        }
    }
}
```

Save the file matching the class name, then run with JDK 17 and Gradle:

```bash
gradle run --quiet
```

If the project has the Gradle Wrapper, run `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows.

**Expected standard output:**

```text
basic: code.required,quantity.min
consistency: consistency.failed
approval: approval.failed
valid: PASS
```

Interpretation:

- **basic:** Both default constraints `@NotBlank` and `@Min` fail together. No consistency/approval errors appear because the sequence stops after the `Invoice` group.
- **consistency:** Code and quantity are valid; `consistent=false` causes `ConsistencyChecks` to fail, skipping `ApprovalChecks`.
- **approval:** First two tiers pass; `approved=false` violates the final group.
- **valid:** All groups pass; `Set<ConstraintViolation<Invoice>>` is empty.

The example annotates **fields**, so Hibernate Validator can inspect private fields directly. Groups are declared as nested interfaces inside the program class; `Invoice` is a nested static class. The code requires no Spring context or HTTP server.

### 6.3. Validating a Specific Group Does Not Mean Running the `Default` Sequence

Calling:

```java
validator.validate(invoice, ConsistencyChecks.class);
```

requests only `ConsistencyChecks`. It **does not automatically prepend** the `Default` tier. To run `Invoice`'s `Default` sequence, call `validator.validate(invoice)` or request `Default.class`.

When testing a specific group, explicitly state the passed group. Do not assume every `validate` call on a class with a redefinition runs the same sequence.

## 7. **Local** Scope: Parent Sequences Do Not Propagate Whole to Children

This is a common pitfall when Spring MVC validates forms with nested beans.

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;

interface ExtraChecks {}

@GroupSequence({Order.class, ExtraChecks.class})
class Order {

    @NotBlank
    String orderCode;

    @Valid
    Customer customer;

    @AssertTrue(groups = ExtraChecks.class)
    boolean ready;
}

class Customer {

    @NotBlank
    String displayName;
}
```

This snippet illustrates the model without constructors or helper methods.

When calling `validator.validate(order)`:

1. `Order`'s `Default` is replaced by `Order.class`, then `ExtraChecks.class` if needed.
2. Cascading via `@Valid` to `Customer` **does not pass intact** `Order`'s sequence (`Order.class`, `ExtraChecks.class`).
3. `Customer` receives the **`Default` group**, or uses **`Customer`'s own** default redefinition if `Customer` has its own class-level `@GroupSequence`.
4. If `Order.orderCode` is invalid, `Order`'s `ExtraChecks` is skipped; this **does not necessarily prevent `Customer`'s `Default` errors**, because `Default` validation propagated across the `@Valid` relationship.

The specification calls this **default group sequence overriding is local to the class**. Understanding this rule explains why you sometimes see errors on a child even when an advanced group on the parent was blocked.

### If You Want to Switch Groups on Cascade: `@ConvertGroup`

Jakarta provides group conversion on a `@Valid` relationship:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

class Checkout {

    @Valid
    @ConvertGroup(
        from = Default.class,
        to = ShippingChecks.class
    )
    Address shippingAddress;
}
```

This is an illustrative snippet; `Address` and the `ShippingChecks` interface must also be defined. When a cascade call passes `Default` across this relationship, the group is converted to `ShippingChecks`.

Remember:

- `@ConvertGroup` is only valid at a position **with a `@Valid` cascade**.
- Group conversion changes the group passed to the child, not `Default` on the root.
- Do not chain conversions multiple times on the same edge.
- Do not declare two conversions with the same `from` value at one cascade point.
- `from` must not point to a group sequence; group sequences are expanded before conversion rules are checked.
- If the child only needs to receive its own `Default` and has its own class redefinition, **group conversion is not necessarily needed**.

## 8. Applying in Spring MVC and Spring Boot

Spring Framework 6+/Spring Boot 3+ uses the Jakarta namespace, typically wiring the Bean Validation provider through `LocalValidatorFactoryBean`.

Illustrative DTO:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;

interface InvoiceRules {}

@GroupSequence({CreateInvoiceRequest.class, InvoiceRules.class})
public class CreateInvoiceRequest {

    @NotBlank
    public String code;

    @AssertTrue(groups = InvoiceRules.class)
    public boolean policyAccepted;

    public CreateInvoiceRequest() {}
}
```

Place the DTO in `CreateInvoiceRequest.java` with binding compatible with Jackson/Spring. In real API applications, design immutable or setter-based DTOs consistently—do not expose sensitive fields publicly just because of this short example.

Illustrative controller:

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InvoiceController {

    @PostMapping("/invoices")
    public ResponseEntity<String> create(
            @Valid @RequestBody CreateInvoiceRequest request) {
        return ResponseEntity.ok("accepted");
    }
}
```

Once JSON is successfully deserialized into the object and a Jakarta validator is configured:

- `@Valid` triggers validation of the request object.
- Because `CreateInvoiceRequest` redefined `Default`, `code` is validated first.
- If `code` is blank, `InvoiceRules` does not run.
- If `code` is valid while `policyAccepted=false`, `InvoiceRules` produces a violation.
- Spring MVC typically turns object validation errors into HTTP 400 if the controller has no `BindingResult` or custom exception handler.

One way to receive errors directly in the controller is to place `BindingResult` **immediately after** the corresponding `@Valid` parameter in the method signature. Do not confuse unparseable JSON errors with Jakarta constraint errors: Jackson can fail before Bean Validation executes.

### `@Valid` and `@Validated`

In eligible MVC contexts, `@Valid` normally requests the `Default` group. Spring's `@Validated(OtherChecks.class)` can explicitly request a different group. If only a group other than `Default` is requested, **the class's redefined `Default` sequence is not used automatically**.

Test controller group configurations, especially when the same DTO is shared across endpoints. Class-level redefinition alters **default behavior everywhere `Default` is requested**, not just in the controller that inspired the class.

## 9. Hibernate Validator Dynamic Sequence Extension

`@GroupSequence` on a class defines a **static sequence**. If business rules require the sequence to vary based on **instance state**, Hibernate Validator provides an extension:

- `org.hibernate.validator.group.GroupSequenceProvider`.
- `org.hibernate.validator.spi.group.DefaultGroupSequenceProvider<T>`.

Conceptual example: for `Submission`, if `submitted == false`, the sequence is `{Submission.class}`; if `submitted == true`, the sequence is `{Submission.class, SubmittedChecks.class}`.

A dynamic provider implements:

```java
@Override
public List<Class<?>> getValidationGroups(Submission value) {
    List<Class<?>> groups = new ArrayList<>();
    groups.add(Submission.class);

    if (value != null && value.isSubmitted()) {
        groups.add(SubmittedChecks.class);
    }

    return groups;
}
```

This snippet belongs **inside** an already-declared `DefaultGroupSequenceProvider<Submission>` implementation; you need imports for `java.util.List` and `java.util.ArrayList`, along with `Submission` and `SubmittedChecks`. Register the provider with `@GroupSequenceProvider(MySequenceProvider.class)` on the class—this is not a standard Jakarta annotation.

Caveats:

1. The returned sequence **must still contain the bean class itself**.
2. The provider may be called when the instance is null (such as certain metadata/`validateValue` scenarios), so handle `null` safely.
3. The implementation needs a public no-arg constructor and must be thread-safe.
4. Do not combine static class-level `@GroupSequence` with dynamic `@GroupSequenceProvider` on the same class.
5. This is a **Hibernate Validator dependency**, not portable across all Jakarta providers.

Only use dynamic sequences when there is a clear need; sometimes a separate DTO or caller-selected groups are simpler.

## 10. Common Mistakes and How to Test

### Common Mistakes

1. **Using `Default.class` inside `@GroupSequence` on the class itself.** This is a self-reference; use `YourBean.class`.
2. **Omitting `YourBean.class` from the sequence.** Class redefinition must contain that class; otherwise `GroupDefinitionException` occurs.
3. **Thinking `validate(bean, A.class, B.class)` guarantees `A` before `B`.** You must use a sequence for ordering.
4. **Thinking a sequence returns only one violation.** The active group can have multiple errors; stopping happens between groups.
5. **Thinking a parent sequence automatically propagates into `@Valid` children.** Redefinition has local scope.
6. **Confusing an interface sequence with a class sequence.** An interface sequence runs only when requested; a class sequence alters `Default`.
7. **Forgetting `groups` on advanced constraints.** Without `groups = BusinessChecks.class`, the constraint sits in `Default` and runs too early.
8. **Adding groups without testing the short-circuit branch.** Can return unexpected errors or skip intended groups.
9. **Creating circular dependencies in group sequences or inheritance.** Evaluating the group can throw `GroupDefinitionException`.
10. **Thinking `@GroupSequence` handles JSON/type conversion.** It only handles validation order, not request parsing.
11. **Enabling Hibernate fail-fast expecting the first error to always be a specific field.** Constraint order within a group is not guaranteed.
12. **Writing a non-thread-safe dynamic provider.** `DefaultGroupSequenceProvider` can be invoked concurrently.
13. **Using `@ConvertGroup` without `@Valid`.** No valid cascade edge exists; can throw a configuration error.
14. **Putting an entire entity graph into a complex sequence.** Prefer validating bounded DTOs/use cases to avoid overly broad checks and unintended JPA lazy loading.

### Test Matrix

| Case | Expectation |
| --- | --- |
| `Default` constraints fail, advanced groups also fail | Only errors from the class-hosted `Default` group |
| `Default` passes, `ConsistencyChecks` fails | Only `Consistency` errors |
| `Default` and `Consistency` pass, `Approval` fails | Only `Approval` errors |
| All three tiers pass | Empty violation set |
| Requesting `ConsistencyChecks.class` alone | Does not automatically run the `Default` sequence |
| Class sequence omits the class itself | `GroupDefinitionException` |
| Class sequence contains `Default.class` | Invalid configuration |
| Redefined-`Default` parent has `@Valid` child | Child uses its own `Default`, does not copy parent's sequence verbatim |
| Child has its own default redefinition | Child applies its own sequence when `Default` is requested |
| Interface-level sequence invoked explicitly | Groups execute in interface sequence order |
| Malformed JSON | Deserialization error, not constraint ordering |

### Self-Check

1. **Why is `@GroupSequence({Invoice.class, Checks.class})` valid?** Because `Invoice.class` represents the `Default` constraints hosted on `Invoice`, and the class itself must be present in the sequence.
2. **Why can't you replace it with `Default.class`?** Because you are redefining `Default`, which creates a definition cycle.
3. **Can blank code and invalid quantity report two errors?** Yes, because both belong to the first tier; stopping happens before the next group, not at the first error.
4. **When a caller only calls `validate(invoice, ApprovalChecks.class)`, does the basic tier run?** Not automatically.
5. **Does a child receive all of the parent's groups via `@Valid`?** Not for class-level `Default` redefinition; the child receives `Default` or the appropriate converted group.
6. **When should you choose an interface-level sequence?** When multiple use cases need different validation levels selected by the caller without altering the bean's `Default`.
7. **When should you use Hibernate `@GroupSequenceProvider`?** When the default sequence must change based on instance state and you accept provider coupling.

## 11. References

- [Jakarta Bean Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): sections *Group sequence*, *Redefining the Default group for a class*, *Validation routine*, *Group conversion*.
- [Jakarta Validation 3.0 — `@GroupSequence`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/GroupSequence.html): group ordering contract.
- [Jakarta Validation 3.0 — `Default`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/groups/Default.html): default marker group.
- [Hibernate Validator 8 — Reference Guide](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/): `@GroupSequence`, default group redefinition, group conversion, dynamic sequence.
- [Hibernate Validator 8 — `DefaultGroupSequenceProvider`](https://docs.hibernate.org/validator/8.0/api/org/hibernate/validator/spi/group/DefaultGroupSequenceProvider.html): dynamic sequence SPI.
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Jakarta provider integration via `LocalValidatorFactoryBean`.
- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, `@Validated`, `BindingResult`, error handling.

**Takeaway:** when placing `@GroupSequence` on a class, you redefine **`Default` for that class itself**. The sequence must contain **the class**, not `Default.class` in its place. Later groups run only when earlier groups have no errors, and the parent's sequence **does not automatically propagate intact** to child beans during cascade.
