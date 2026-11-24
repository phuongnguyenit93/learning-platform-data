# Diagnosing Incorrect `@GroupSequence` or Desired Validation Groups Not Triggering in Spring Framework

## Learning Objectives

A particularly subtle bug when using Jakarta Bean Validation with Spring MVC is: **constraints are declared properly, the object has `@Valid`, yet tests or real requests fail to run the expected group**. Conversely, sometimes a group was requested yet **intentionally skipped** because an earlier group in `@GroupSequence` already produced violations. Looking only at HTTP 400 or violation counts makes it easy to misdiagnose this as "Hibernate Validator ignored my annotation."

This article belongs to the **Diagnostics** section of the **Spring Framework — validation-data-binding** module, diving into:

- The `jakarta.validation.groups.Default` group and custom groups such as `BusinessChecks` and `FinalChecks`.
- Jakarta `@Valid` vs. Spring `@Validated`: when a group is selected and what actually invokes validation.
- `@GroupSequence` on an **interface** to define an ordered chain, distinguished from `@GroupSequence` on a **class** to **redefine `Default`** for that class.
- The rule of **stopping at the first group with at least one violation**, compared to passing multiple groups together **without ordering**.
- Group inheritance; cyclic sequence errors; `GroupDefinitionException`.
- Cascading `@Valid` into nested objects/Lists; `@ConvertGroup`; why a parent object's customized Default group **does not automatically propagate** to child objects.
- Hibernate Validator's `@GroupSequenceProvider` for dynamic default sequences (a non-standard Jakarta extension).
- Inspecting `ConstraintViolation.getConstraintDescriptor().getGroups()`, property paths, metadata, and `BindingResult` in tests.
- Building a Java 17+, Spring Boot 3.5.7, MockMvc + JUnit example to see which group runs, which is skipped, and why.

**Guiding conclusion:** Before editing annotations, verify **which group was actually requested** and **which group caused the sequence to stop**. An annotation existing on a model **does not mean** it is evaluated on every validator call.

## 1. Foundational Concepts

### 1.1. Every Constraint Belongs to One or More Groups

Example:

~~~java
public interface BusinessChecks {}
public interface FinalChecks {}

public class Registration {
    @NotBlank
    private String email;

    @NotBlank(groups = BusinessChecks.class)
    private String companyCode;

    @AssertTrue(groups = FinalChecks.class)
    private boolean acceptedTerms;
}
~~~

The snippet above is an **explanatory fragment**, not a standalone runnable file. Relevant imports belong to `jakarta.validation.constraints`.

The three rules do not share the same group:

| Constraint | Declared group | When is it checked? |
| --- | --- | --- |
| `@NotBlank email` | `Default` (implicit) | When validating with Default |
| `@NotBlank(groups=BusinessChecks.class) companyCode` | `BusinessChecks` | When requesting BusinessChecks or a group/sequence including it |
| `@AssertTrue(groups=FinalChecks.class) acceptedTerms` | `FinalChecks` | When requesting FinalChecks or a sequence including it |

With Jakarta `Validator`:

~~~java
validator.validate(registration);
validator.validate(registration, Default.class);
~~~

Both calls are generally equivalent in requesting **the Default group**. Neither automatically triggers `BusinessChecks` or `FinalChecks`, unless there is a **default group sequence redefinition** on the class, or an appropriate group-sequence / group-inheritance relationship.

### 1.2. `@Valid` Is Not a "Run All Groups" Command

`jakarta.validation.Valid` is commonly placed on controller arguments or nested properties:

~~~java
@PostMapping("/register")
ResponseEntity<?> register(
        @Valid @RequestBody Registration input) {
    // ...
}
~~~

`@Valid` tells Spring the object must be validated; without a group hint, `Default` normally applies. It has **no** `groups` parameter and does not mean "evaluate every constraint across all groups."

To request a group in Spring MVC, use Spring's `@Validated`:

~~~java
@PostMapping("/register/final")
ResponseEntity<?> finalSubmit(
        @Validated(FinalChecks.class)
        @RequestBody Registration input) {
    // ...
}
~~~

`@Validated` belongs to `org.springframework.validation.annotation.Validated`, a different package from Jakarta `@Valid`. `@Validated(FinalChecks.class)` typically triggers only `FinalChecks` (plus inherited/sequenced groups if any), **without automatically adding `Default`**.

### 1.3. A Set of Multiple Groups Is Not Equivalent to a Sequence

Example:

~~~java
validator.validate(
        registration,
        Default.class,
        BusinessChecks.class,
        FinalChecks.class);
~~~

This call requests **all three groups**, yet Jakarta Bean Validation **guarantees no ordering** among independently requested groups. A failing `Default` constraint is not a standard reason to skip `BusinessChecks`/`FinalChecks` constraints in an unsequenced call.

If **ordering and short-circuiting** are required, you must use `@GroupSequence` properly.

## 2. `@GroupSequence` on an Interface: Ordering and Short-Circuiting

Create a group meaning "validate sequentially according to the workflow":

~~~java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

@GroupSequence({
        Default.class,
        BusinessChecks.class,
        FinalChecks.class
})
public interface OrderedChecks {
}
~~~

This is a **group sequence interface**. It takes effect when callers request **`OrderedChecks`**:

~~~java
Set<ConstraintViolation<Registration>> violations =
        validator.validate(
                registration,
                OrderedChecks.class);
~~~

In Spring MVC:

~~~java
@PostMapping("/register/ordered")
ResponseEntity<?> registerOrdered(
        @Validated(OrderedChecks.class)
        @RequestBody Registration input) {
    // ...
}
~~~

**Important:** Merely having `@GroupSequence` on `OrderedChecks` **does not make every `validator.validate(registration)` call switch to `OrderedChecks`**. Callers must request this group sequence, unless used through another valid definition.

### 2.1. The Short-Circuit Rule

Groups are evaluated in order:

~~~text
Default
   |
   +-- violation? ---- YES ---> STOP
   |
   +-- NO
         |
         v
    BusinessChecks
         |
         +-- violation? --- YES ---> STOP
         |
         +-- NO
               |
               v
          FinalChecks
               |
               v
           Result
~~~

Suppose `email`, `companyCode`, and `acceptedTerms` are all invalid:

- `Default` catches the `email` error.
- `BusinessChecks` **does not run** because `Default` failed.
- `FinalChecks` **does not run** because the sequence stopped.
- The violation set contains only errors collected in `Default`.

That is **the intended behavior of `@GroupSequence`**. It does not mean constraints in the later two groups were misdeclared.

When `Default` passes yet `BusinessChecks` fails, only `Default` and `BusinessChecks` are processed; `FinalChecks` is skipped. Only when both earlier stages pass is `FinalChecks` evaluated.

### 2.2. Do Not Confuse Short-Circuiting with "Only One Error"

Within a single group, the provider may record **multiple violations**: empty email, age too low, blank city... Once a group produces at least one violation, the sequence stops **after that group**. By default this is not a "stop at the first failing field" mechanism; the count and order of violations within the same group should not be assumed to match field declaration order.

Hibernate Validator offers a **fail-fast** extension mode, which is a separate setting and can alter violation counts in tests. Do not confuse provider-specific fail-fast with standard group-level short-circuiting.

### 2.3. Do Not Assign Constraints Directly to a Sequence Interface

Do not write:

~~~java
@NotBlank(groups = OrderedChecks.class)
private String companyCode;
~~~

when `OrderedChecks` is an interface annotated with `@GroupSequence`. Per Bean Validation rules, a group sequence interface must not have superinterfaces and must not be used directly in a constraint's `groups`. Assign constraints to **`BusinessChecks`** or **`FinalChecks`**, and use `OrderedChecks` solely to **request the sequence**.

### 2.4. Group Inheritance Does Not Automatically Run `Default`

Example:

~~~java
public interface AdvancedBusinessChecks
        extends BusinessChecks {
}
~~~

When validating `AdvancedBusinessChecks.class`, constraints belonging to `BusinessChecks` are included via group inheritance. However, that **does not implicitly include `Default`** unless the group/sequence hierarchy actually includes `Default`.

Group inheritance supports policy reuse. Avoid deep inheritance chains that obscure which groups a constraint belongs to; name groups after use cases.

## 3. `@GroupSequence` on a Class: Redefining `Default`

Distinct from `@GroupSequence` on an interface is placing the annotation **directly on a bean class**:

~~~java
import jakarta.validation.GroupSequence;
import jakarta.validation.constraints.NotBlank;

@GroupSequence({
        StrictProfile.class,
        ComplianceChecks.class
})
public record StrictProfile(
        @NotBlank String displayName,
        @NotBlank(groups = ComplianceChecks.class)
        String identityNumber) {
}
~~~

When `validator.validate(new StrictProfile(...))` requests `Default`, the sequence is redefined for **`StrictProfile` itself**:

1. Validate `Default` constraints declared on `StrictProfile` (represented in the sequence by `StrictProfile.class`).
2. Only if that first group passes, validate `ComplianceChecks`.
3. If the first group fails, `ComplianceChecks` is skipped.

### 3.1. Why Must It Contain the Class Instead of `Default.class`?

Here is a common diagnostic mistake:

~~~java
@GroupSequence({
        Default.class,
        ComplianceChecks.class
})
public class BrokenProfile {
    @NotBlank
    private String displayName;
}
~~~

When `@GroupSequence` **redefines `Default` on a class**, the sequence **must include the class itself** (here `BrokenProfile.class`), never `Default.class` in its place. An invalid sequence throws `jakarta.validation.GroupDefinitionException` during metadata inspection or validation.

Fix:

~~~java
@GroupSequence({
        BrokenProfile.class,
        ComplianceChecks.class
})
public class BrokenProfile {
    @NotBlank
    private String displayName;
}
~~~

Notice: on the **interface** `OrderedChecks` in Section 2, `Default.class` in the sequence is **correct**; on **class-level Default redefinition** on `BrokenProfile`, it is **wrong**. You cannot read a `@GroupSequence` line without checking **whether the annotation sits on an interface or a class**.

### 3.2. Redefined `Default` Applies Only Locally to the Class

When `StrictProfile` redefines `Default`, that **does not automatically turn the group passed down to linked objects** via `@Valid` into `StrictProfile`'s full sequence. Default redefinition is **local to that class**. Child objects receive groups according to Jakarta Validation's group propagation rules; if you need to translate groups across a cascade edge, use `@ConvertGroup` on the association.

Thus, "the parent's `@GroupSequence` includes `ComplianceChecks` yet the child's `ComplianceChecks` errors did not appear" may be **correct behavior**, not the provider skipping nested validation.

### 3.3. Avoid Cyclic Group Dependencies

Sequences must not contain cyclic dependencies violating spec rules, including indirect cycles through group inheritance. Conceptual broken model:

~~~text
SequenceA → SequenceB → SequenceA
~~~

When metadata is inspected or the group is requested, the provider throws `GroupDefinitionException`. Never try to work around this by calling the validator multiple times arbitrarily; fix the group graph into a valid DAG/order and add metadata tests.

## 4. `@ConvertGroup` and Nested Objects

### 4.1. `@Valid` Cascades Only the Active Group

Suppose:

~~~java
public record Address(
        @NotBlank String city,
        @NotBlank(groups = BusinessChecks.class)
        String zipCode,
        @NotBlank(groups = AddressReview.class)
        String districtCode) {
}
~~~

Root:

~~~java
public record RegistrationRequest(
        @NotBlank String email,
        @Valid Address address) {
}
~~~

If you only call:

~~~java
validator.validate(registrationRequest);
~~~

then `Default` applies to the root and, by cascade, `Default` propagates into `Address`. The `city` constraint is checked, while `zipCode` (`BusinessChecks`) and `districtCode` (`AddressReview`) **do not run**. If the caller requests `OrderedChecks`, the provider evaluates each group in turn, including nested constraints in that group, per propagation and sequence rules.

### 4.2. `@ConvertGroup` When Translating Groups Across a Cascade Edge

~~~java
public record ConvertedRequest(
        @NotBlank String label,
        @NotNull
        @Valid
        @ConvertGroup(
                from = Default.class,
                to = AddressReview.class)
        Address address) {
}
~~~

`@ConvertGroup` belongs to `jakarta.validation.groups.ConvertGroup` and only takes effect on an edge cascaded via `@Valid`. When callers validate **Default** on `ConvertedRequest`, `address` is validated under **`AddressReview`** instead of `Default` due to the conversion rule.

If `address` has:

~~~text
city=""         → belongs to Default
zipCode=""      → belongs to BusinessChecks
districtCode="" → belongs to AddressReview
~~~

then under the conversion above, **`districtCode` errors appear**, while `city` and `zipCode` are not checked from `Default` propagating across this edge. This cleanly explains why "a desired nested group field did not trigger" or "a nested default field unexpectedly produced no error."

### 4.3. Important Limitations of `@ConvertGroup`

- `@ConvertGroup` requires `@Valid` on the corresponding cascade point/container element.
- `from` is the incoming group **after sequences have been expanded**; never place a group sequence in `from`.
- `to` may point to a valid group sequence.
- Conversions on one edge do not chain recursively on that same edge: `A→B` and `B→C` does not mean `A` automatically converts to `C` across that single edge.
- Never declare two mappings with the same `from` on the same conversion point; the provider may throw `ConstraintDeclarationException`.
- Conversion grants no permissions and does not replace authentication; it only selects Bean Validation constraint groups.

When diagnosing a silent nested field, check: **is `@Valid` present, is the object non-null, which group is propagated, is `@ConvertGroup` present, and which group owns the constraint**.

## 5. `@GroupSequenceProvider`: Hibernate Validator Extension

`@GroupSequenceProvider` belongs to `org.hibernate.validator.group.GroupSequenceProvider`. It is **not a standard Jakarta annotation**. Hibernate Validator provides it to redefine the `Default` sequence **dynamically based on object state**.

Conceptual example:

~~~text
Registration isDraft=true
  → validate only the bean's default group

Registration isDraft=false
  → validate default group then FinalChecks
~~~

A default group sequence provider receives the current object to determine groups and must include **the validated class itself** in the returned sequence per provider rules.

Before using it, verify:

1. Does the project use Hibernate Validator or another Jakarta provider?
2. Is validation invoked on an object holding the state needed to select the sequence?
3. When the object is null or the provider initializes metadata, is the provider logic null-safe?
4. Are there tests covering state transitions Draft→Final verifying the group actually activates?
5. Does it conflict with a static `@GroupSequence` on the same bean?

**Never use a client-submitted input flag as an authorization mechanism.** A client must never be trusted to pass `isAdmin=true` or `isApproved=true` just to switch validation groups; groups only validate data shape/rules, while execution authority belongs in service/security layers.

If portability matters, prefer `@Validated(SomeSequence.class)` or explicit `Validator.validate(object, group)` calls from the use case rather than relying on a provider-specific feature.

## 6. Spring MVC: `@Valid` and `@Validated` in the Pipeline

### 6.1. For `@RequestBody`

~~~java
@PostMapping("/default")
ResponseEntity<?> createDefault(
        @Valid @RequestBody RegistrationRequest input) {
    // ...
}
~~~

Normally Spring MVC validates `Default`. If a constraint only declares `groups=FinalChecks.class`, it **does not run**.

~~~java
@PostMapping("/ordered")
ResponseEntity<?> createOrdered(
        @Validated(OrderedChecks.class)
        @RequestBody RegistrationRequest input) {
    // ...
}
~~~

Spring passes the `OrderedChecks.class` group hint to the validator. The sequence is expanded by the Jakarta provider; if `Default` fails, `BusinessChecks` and `FinalChecks` are skipped. When no `BindingResult` immediately follows the parameter, Spring MVC normally throws `MethodArgumentNotValidException`.

### 6.2. With `@ModelAttribute` and `BindingResult`

~~~java
@PostMapping("/submit-form")
String submit(
        @Validated(OrderedChecks.class)
        @ModelAttribute("registrationForm")
        RegistrationForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "registration-form";
    }
    return "redirect:/success";
}
~~~

This is a **snippet** for traditional MVC forms; it requires `RegistrationForm` and corresponding views, and is not part of the JSON demo project. When `BindingResult` sits **immediately after** the form argument, Spring hands errors to the controller instead of throwing an exception. That **does not mean validation did not run**. Inspect:

~~~java
errors.getFieldErrors();
errors.getGlobalErrors();
errors.getAllErrors();
errors.getErrorCount();
~~~

If `BindingResult` is misplaced, or if method validation applies to other parameters, the exception path can differ. Do not diagnose solely by whether an `@ExceptionHandler` was called.

### 6.3. Method Validation in Spring 6.1+

Since Spring Framework 6.1, MVC includes native controller method validation for direct constraints:

~~~java
@GetMapping("/limits")
String limits(@RequestParam @Min(1) int count) {
    return "ok";
}
~~~

When direct method constraints like `@Min` exist, method-level validation can **cover** `@Valid` arguments as well and throw `HandlerMethodValidationException` instead of a single-object `MethodArgumentNotValidException`.

If a controller has **class-level `@Validated`**, method validation may route through an AOP proxy instead of native MVC. Spring documentation recommends removing the class-level annotation when using Spring 6.1+ native controller method validation. Consequently, controller advice handling only `MethodArgumentNotValidException` may miss errors; that does not mean "the group was not triggered."

### 6.4. `@Validated` on Services and Self-Invocation

A service:

~~~java
@Service
@Validated
public class RegistrationService {

    public void approve(
            @Validated(FinalChecks.class)
            RegistrationRequest request) {
        // ...
    }
}
~~~

This snippet depends on actual method validation/AOP configuration. With proxy-based Spring method validation, **calling the method through the proxy** triggers the interceptor; self-invocation like `this.approve(...)` inside the same instance normally bypasses proxy advice. That is a **validation entry-point** issue, distinct from `@GroupSequence` short-circuiting.

Do not conclude "wrong constraint group" before proving a `Validator.validate(...)` call or interceptor actually executed.

## 7. Outside-In Diagnostic Workflow

When a test expects `FinalChecks` errors yet sees only a `Default` error, follow these steps in order.

### Step 1 — Verify the Constraint and Its Owning Group

Read the full annotation:

~~~java
@NotBlank(groups = BusinessChecks.class)
String companyCode;
~~~

Without `groups`, the annotation belongs to `Default`. With `groups={BusinessChecks.class,FinalChecks.class}`, the constraint belongs to both groups with no internal priority order.

You can inspect metadata:

~~~java
BeanDescriptor bean = validator
        .getConstraintsForClass(RegistrationRequest.class);

PropertyDescriptor property =
        bean.getConstraintsForProperty("companyCode");

Set<ConstraintDescriptor<?>> definitions =
        property.getConstraintDescriptors();
~~~

This is a snippet; imports come from `jakarta.validation.metadata`. Inspect `descriptor.getGroups()` to see **which groups the constraint actually declares**, rather than guessing from the field name.

### Step 2 — Confirm Which Group the Caller Requested

Compare:

~~~java
validator.validate(input);
validator.validate(input, BusinessChecks.class);
validator.validate(input, OrderedChecks.class);
validator.validate(input,
        Default.class,
        BusinessChecks.class,
        FinalChecks.class);
~~~

These four calls can yield different violation sets. In MVC, check whether `@Valid` or `@Validated(...)` sits on **the right parameter**. In services, check whether the call site goes through the method-validation proxy.

### Step 3 — When Using `@GroupSequence`, Find the First Failing Group

Do not just ask "why didn't `FinalChecks` run?" Verify:

~~~text
Default has errors?         → STOP, later groups skipped
Default passes, Business fails? → STOP, Final skipped
Both prior groups pass?     → Only then does Final run
~~~

Write a test for each gate. To test `FinalChecks` rules in isolation, call `validator.validate(input,FinalChecks.class)` to confirm the rule works, then run `OrderedChecks` to verify the sequence.

### Step 4 — Distinguish Interface Sequences from Class Default Redefinitions

- `@GroupSequence` on an interface: callers must request that interface, e.g., `OrderedChecks.class`.
- `@GroupSequence` on a class: redefines `Default` locally for the class, and **must include the class itself in the sequence**, never `Default.class` instead.

If you get `GroupDefinitionException`, inspect cycles/inheritance and the `@GroupSequence` list before changing constraints.

### Step 5 — Inspect Nested / Cascade / `@ConvertGroup`

Does the nested object have `@Valid`? Is it non-null? Is the root group propagated? Is `@ConvertGroup` translating `Default` to another group? Are list/map elements annotated with `@Valid`/type-use constraints?

### Step 6 — Distinguish Binding Errors from Validation Errors

`age="abc"` in a form can become `typeMismatch` before `@Min` runs. Unparseable JSON throws `HttpMessageNotReadableException` with no Bean Validation on the DTO. Fix input so deserialization succeeds first, then verify the group sequence.

### Step 7 — Check Provider, Groups, and Test Environment

- Are `spring-boot-starter-validation`/Hibernate Validator on the classpath?
- Is a valid `LocalValidatorFactoryBean` active for Spring MVC?
- Did a custom `Validator`/`WebMvcConfigurer.getValidator()`/`@InitBinder` accidentally replace the adapter?
- Are legacy `javax.validation.*` imports mixed into a Boot 3 Jakarta project?
- Is provider fail-fast enabled?
- Is a unit test instantiating the controller with `new` without MVC validation infrastructure?
- Is method-level validation changing the exception class?

### Step 8 — Read Paths and Descriptors, Do Not Guess from `defaultMessage`

Write tests checking `ConstraintViolation.getPropertyPath().toString()` and `getConstraintDescriptor().getGroups()`. Avoid asserting English Hibernate Validator strings, because localization can change even while the rule and group remain right.

## 8. Runnable Java 17+ / Spring Boot 3.5.7 Project

The project demonstrates four scenarios:

1. **Default vs. Business vs. Final:** a form with `Default`, `BusinessChecks`, and `FinalChecks` constraints.
2. **`OrderedChecks`:** sequence `Default → BusinessChecks → FinalChecks`, stopping at the first failing group.
3. **`ConvertedRequest`:** `@ConvertGroup(Default→AddressReview)` translating the group when cascading into nested `Address`.
4. **`StrictProfile`:** class-level `@GroupSequence` redefining `Default`.

Includes a JSON controller with four endpoints—`/default`, `/ordered`, `/business`, `/unordered`—demonstrating group selection in Spring MVC. Includes unit tests using `jakarta.validation.Validator` and MockMvc tests for status/path/group selection.

### 8.1. File Structure

~~~text
validation-group-diagnostics/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/groups/
    │   │   ├── Application.java
    │   │   ├── BusinessChecks.java
    │   │   ├── FinalChecks.java
    │   │   ├── AddressReview.java
    │   │   ├── ComplianceChecks.java
    │   │   ├── OrderedChecks.java
    │   │   ├── Address.java
    │   │   ├── RegistrationRequest.java
    │   │   ├── ConvertedRequest.java
    │   │   ├── StrictProfile.java
    │   │   ├── RegistrationController.java
    │   │   └── ValidationAdvice.java
    │   └── resources/application.properties
    └── test/java/com/example/groups/
        ├── GroupValidationTest.java
        └── GroupMvcTest.java
~~~

### 8.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>validation-group-diagnostics</artifactId>
    <version>1.0.0</version>

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
~~~

The project uses `jakarta.validation`, not Spring Boot 2's `javax.validation`. `spring-boot-starter-validation` is required for Spring Boot to register a provider such as Hibernate Validator. No extra `Validator` bean declaration is needed when Boot auto-configuration provides it.

### 8.3. `Application.java`

~~~java
package com.example.groups;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 8.4. `BusinessChecks.java`

~~~java
package com.example.groups;

public interface BusinessChecks {
}
~~~

### 8.5. `FinalChecks.java`

~~~java
package com.example.groups;

public interface FinalChecks {
}
~~~

### 8.6. `AddressReview.java`

~~~java
package com.example.groups;

public interface AddressReview {
}
~~~

### 8.7. `ComplianceChecks.java`

~~~java
package com.example.groups;

public interface ComplianceChecks {
}
~~~

These marker interfaces contain no methods. They represent **validation groups**, not security roles/authorities and not Spring `@Component`s.

### 8.8. `OrderedChecks.java` — Proper Sequence Interface

~~~java
package com.example.groups;

import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

@GroupSequence({
        Default.class,
        BusinessChecks.class,
        FinalChecks.class
})
public interface OrderedChecks {
}
~~~

Do not write `extends BusinessChecks` on `OrderedChecks`; do not assign constraints directly to `groups=OrderedChecks.class`. This is the sequence group explicitly requested by the controller and tests.

### 8.9. `Address.java`

~~~java
package com.example.groups;

import jakarta.validation.constraints.NotBlank;

public record Address(
        @NotBlank String city,

        @NotBlank(groups = BusinessChecks.class)
        String zipCode,

        @NotBlank(groups = AddressReview.class)
        String districtCode) {
}
~~~

Three properties belong to three distinct groups. Validating only `Default` on `Address` checks only `city`; validating `BusinessChecks` checks only `zipCode`; validating `AddressReview` checks only `districtCode`.

### 8.10. `RegistrationRequest.java`

~~~java
package com.example.groups;

import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record RegistrationRequest(
        @NotBlank @Email String email,

        @NotNull @Min(18) Integer age,

        @NotBlank(groups = BusinessChecks.class)
        String companyCode,

        @AssertTrue(groups = FinalChecks.class)
        boolean acceptedTerms,

        @NotNull @Valid Address address) {
}
~~~

Primitive boolean `acceptedTerms` is used in the demo; its default is false. When validating `Default`, `@AssertTrue(groups=FinalChecks.class)` does **not** run. When validating `FinalChecks`, false produces a violation on `acceptedTerms`. In real products, if an absent field must be distinguished from false, use `Boolean` with `@NotNull(groups=FinalChecks.class)`.

Because of `@Valid Address`, when `BusinessChecks` is requested, nested `address.zipCode` is also checked. There is no `@ConvertGroup` on this edge, so normal group propagation is preserved.

### 8.11. `ConvertedRequest.java`

~~~java
package com.example.groups;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

public record ConvertedRequest(
        @NotBlank String label,

        @NotNull
        @Valid
        @ConvertGroup(
                from = Default.class,
                to = AddressReview.class)
        Address address) {
}
~~~

This is a dedicated diagnostic case: callers request only `Default` on `ConvertedRequest`, yet nested `Address` is validated under `AddressReview`. Never introduce group-conversion request types into production merely to "run extra nested checks"; design explicit use cases.

### 8.12. `StrictProfile.java`

~~~java
package com.example.groups;

import jakarta.validation.GroupSequence;
import jakarta.validation.constraints.NotBlank;

@GroupSequence({
        StrictProfile.class,
        ComplianceChecks.class
})
public record StrictProfile(
        @NotBlank String displayName,

        @NotBlank(groups = ComplianceChecks.class)
        String identityNumber) {
}
~~~

Unlike `OrderedChecks` (an interface), the annotation on this record/class **redefines `Default`**. The first member is `StrictProfile.class`, not `Default.class`. `validator.validate(profile)` checks `displayName` first, then `identityNumber` if `displayName` is valid.

### 8.13. `RegistrationController.java`

~~~java
package com.example.groups;

import jakarta.validation.Valid;
import jakarta.validation.groups.Default;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/registrations")
public class RegistrationController {

    public record Accepted(
            String result,
            String email) {
    }

    private ResponseEntity<Accepted> accept(
            RegistrationRequest input) {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new Accepted("accepted", input.email()));
    }

    @PostMapping(
            path = "/default",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Accepted> defaultSubmit(
            @Valid @RequestBody RegistrationRequest input) {
        return accept(input);
    }

    @PostMapping(
            path = "/ordered",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Accepted> orderedSubmit(
            @Validated(OrderedChecks.class)
            @RequestBody RegistrationRequest input) {
        return accept(input);
    }

    @PostMapping(
            path = "/business",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Accepted> businessOnly(
            @Validated(BusinessChecks.class)
            @RequestBody RegistrationRequest input) {
        return accept(input);
    }

    @PostMapping(
            path = "/unordered",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Accepted> unorderedAll(
            @Validated({
                    Default.class,
                    BusinessChecks.class,
                    FinalChecks.class
            })
            @RequestBody RegistrationRequest input) {
        return accept(input);
    }
}
~~~

**Four endpoints for learning and comparison**, not recommended verbatim as a production design:

- `/default`: requests only `Default`.
- `/ordered`: requests sequence `Default→Business→Final`, stopping when an earlier group fails.
- `/business`: requests only `BusinessChecks`; can let invalid `Default` data pass because `Default` is not requested. This helps expose bugs, **not** a license to deploy business endpoints missing basic checks.
- `/unordered`: requests three independent groups; no fixed-order short-circuiting like `OrderedChecks`.

The controller **has no class-level `@Validated`**, avoiding mixing Spring MVC 6.1+ native method validation with unnecessary AOP proxies. Methods have no direct constraints like `@Min` on other parameters, so normal bean input errors route through `MethodArgumentNotValidException`.

### 8.14. `ValidationAdvice.java`

~~~java
package com.example.groups;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;

@RestControllerAdvice
public class ValidationAdvice
        extends ResponseEntityExceptionHandler {

    public record FieldIssue(
            String field,
            String code) {
    }

    public record ErrorReport(
            String code,
            List<FieldIssue> fieldErrors,
            List<String> globalErrors) {
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        BindingResult errors = ex.getBindingResult();

        List<FieldIssue> fields = errors.getFieldErrors()
                .stream()
                .map(error -> new FieldIssue(
                        error.getField(),
                        Objects.toString(
                                error.getCode(), "invalid")))
                .sorted(Comparator
                        .comparing(FieldIssue::field)
                        .thenComparing(FieldIssue::code))
                .toList();

        List<String> globals = errors.getGlobalErrors()
                .stream()
                .map(error -> Objects.toString(
                        error.getCode(), "invalid"))
                .sorted()
                .toList();

        return handleExceptionInternal(
                ex,
                new ErrorReport(
                        "VALIDATION_FAILED",
                        fields,
                        globals),
                headers,
                status,
                request);
    }
}
~~~

`ResponseEntityExceptionHandler` already handles many Spring MVC exceptions. Here we override only the `MethodArgumentNotValidException` hook, avoiding adding a duplicate `@ExceptionHandler(MethodArgumentNotValidException.class)` on the same advice.

The body contains only **field path** and **constraint code**, omitting `FieldError.getRejectedValue()` from JSON; rejected values could be passwords, tokens, or sensitive data. The `address.zipCode` error path helps test cascade and group propagation.

**You cannot reliably infer which group ran solely from `FieldError.getCode()`:** an annotation like `@NotBlank` may belong to multiple groups. To diagnose accurately, use `ConstraintDescriptor.getGroups()` metadata and compare `Validator.validate(...groups)` calls in unit tests.

### 8.15. `application.properties`

~~~properties
server.port=8080
spring.mvc.problemdetails.enabled=false
server.error.include-message=never
~~~

The demo uses custom advice for a clean testable error shape rather than relying on Spring Boot's default response. If a product uses RFC 9457 `ProblemDetail`, you still verify groups and binding/validation the same way; error body format does not alter sequence behavior.

## 9. Unit Tests: Pinpointing Which Group Is Active

Create `src/test/java/com/example/groups/GroupValidationTest.java`:

~~~java
package com.example.groups;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.GroupDefinitionException;
import jakarta.validation.GroupSequence;
import jakarta.validation.Validator;
import jakarta.validation.groups.Default;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class GroupValidationTest {

    @Autowired
    Validator validator;

    private static RegistrationRequest input(
            String email,
            int age,
            String companyCode,
            boolean acceptedTerms,
            String city,
            String zipCode) {

        return new RegistrationRequest(
                email,
                age,
                companyCode,
                acceptedTerms,
                new Address(city, zipCode, "D1"));
    }

    private static RegistrationRequest valid() {
        return input(
                "lan@example.com",
                25,
                "COMPANY-1",
                true,
                "Ha Noi",
                "12345");
    }

    private static <T> Set<String> paths(
            Set<ConstraintViolation<T>> violations) {

        return violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(Collectors.toSet());
    }

    @Test
    void defaultDoesNotActivateCustomGroups() {
        RegistrationRequest request = input(
                "", 16, "", false,
                "", "");

        var result = validator.validate(request);

        assertEquals(
                Set.of("email", "age", "address.city"),
                paths(result));

        assertFalse(paths(result).contains("companyCode"));
        assertFalse(paths(result).contains("acceptedTerms"));
        assertFalse(paths(result).contains(
                "address.zipCode"));
    }

    @Test
    void businessOnlyDoesNotImplicitlyIncludeDefault() {
        RegistrationRequest request = input(
                "", 16, "", false,
                "", "");

        var result = validator.validate(
                request,
                BusinessChecks.class);

        assertEquals(
                Set.of("companyCode", "address.zipCode"),
                paths(result));
    }

    @Test
    void orderedStopsAfterDefaultFailures() {
        RegistrationRequest request = input(
                "", 16, "", false,
                "", "");

        var result = validator.validate(
                request,
                OrderedChecks.class);

        assertEquals(
                Set.of("email", "age", "address.city"),
                paths(result));
    }

    @Test
    void orderedStopsAfterBusinessFailures() {
        RegistrationRequest request = input(
                "lan@example.com", 25, "", false,
                "Ha Noi", "");

        var result = validator.validate(
                request,
                OrderedChecks.class);

        assertEquals(
                Set.of("companyCode", "address.zipCode"),
                paths(result));

        assertFalse(paths(result).contains("acceptedTerms"));
    }

    @Test
    void orderedReachesFinalOnlyAfterPreviousPass() {
        RegistrationRequest request = input(
                "lan@example.com", 25,
                "COMPANY-1", false,
                "Ha Noi", "12345");

        var result = validator.validate(
                request,
                OrderedChecks.class);

        assertEquals(Set.of("acceptedTerms"), paths(result));
    }

    @Test
    void allValidPassesOrderedChecks() {
        assertTrue(validator.validate(
                valid(),
                OrderedChecks.class).isEmpty());
    }

    @Test
    void independentGroupsDoNotShortCircuit() {
        RegistrationRequest request = input(
                "", 16, "", false, "", "");

        var result = validator.validate(
                request,
                Default.class,
                BusinessChecks.class,
                FinalChecks.class);

        assertEquals(
                Set.of(
                    "email",
                    "age",
                    "address.city",
                    "companyCode",
                    "address.zipCode",
                    "acceptedTerms"),
                paths(result));
    }

    public interface AdvancedBusinessChecks
            extends BusinessChecks {
    }

    @Test
    void inheritedGroupIncludesParentConstraints() {
        RegistrationRequest request = input(
                "", 16, "", false,
                "", "");

        var result = validator.validate(
                request,
                AdvancedBusinessChecks.class);

        assertEquals(
                Set.of("companyCode", "address.zipCode"),
                paths(result));
    }

    @Test
    void convertGroupChangesNestedGroupOnly() {
        ConvertedRequest request =
                new ConvertedRequest(
                        "ok",
                        new Address("", "", ""));

        var result = validator.validate(request);

        assertEquals(
                Set.of("address.districtCode"),
                paths(result));

        assertEquals(
                Set.of("city"),
                paths(validator.validate(request.address())));
    }

    @Test
    void classLevelDefaultSequenceStopsOnFirstStage() {
        StrictProfile p = new StrictProfile("", "");

        assertEquals(
                Set.of("displayName"),
                paths(validator.validate(p)));

        StrictProfile later = new StrictProfile(
                "Lan", "");

        assertEquals(
                Set.of("identityNumber"),
                paths(validator.validate(later)));
    }

    @GroupSequence({
            Default.class,
            ComplianceChecks.class
    })
    static class BrokenProfile {

        @jakarta.validation.constraints.NotBlank
        private String displayName = "";
    }

    @Test
    void invalidDefaultRedefinitionThrows() {
        assertThrows(
                GroupDefinitionException.class,
                () -> validator.validate(
                        new BrokenProfile()));
    }

    @Test
    void metadataShowsDeclaredGroup() {
        var descriptor = validator
                .getConstraintsForClass(
                        RegistrationRequest.class)
                .getConstraintsForProperty("companyCode");

        assertNotNull(descriptor);

        assertTrue(descriptor
                .getConstraintDescriptors()
                .stream()
                .anyMatch(constraint ->
                    constraint.getGroups()
                            .contains(BusinessChecks.class)));

        assertFalse(descriptor
                .getConstraintDescriptors()
                .stream()
                .anyMatch(constraint ->
                    constraint.getGroups()
                            .contains(Default.class)));
    }
}
~~~

### 9.1. Interpreting the 12 Tests

| Test | What it proves |
| --- | --- |
| `defaultDoesNotActivateCustomGroups` | Does not run Business/Final by default |
| `businessOnlyDoesNotImplicitlyIncludeDefault` | Selecting Business alone does not add Default |
| `orderedStopsAfterDefaultFailures` | Sequence halts at the Default stage |
| `orderedStopsAfterBusinessFailures` | Default passes, Business fails, so Final is skipped |
| `orderedReachesFinalOnlyAfterPreviousPass` | Final runs only once both prior groups pass |
| `allValidPassesOrderedChecks` | Proper sequence passes for valid data |
| `independentGroupsDoNotShortCircuit` | Passing multiple groups does not form a sequence |
| `inheritedGroupIncludesParentConstraints` | Group inheritance works |
| `convertGroupChangesNestedGroupOnly` | Nested Address switches from Default to AddressReview |
| `classLevelDefaultSequenceStopsOnFirstStage` | Default redefinition on a class |
| `invalidDefaultRedefinitionThrows` | Fails when using Default.class instead of owning class |
| `metadataShowsDeclaredGroup` | Inspecting metadata confirms declared groups |

**Why do tests compare sets of paths?** `Validator.validate(...)` returns a `Set<ConstraintViolation<?>>`, which does not guarantee violation order matches field declaration order. Using `Set.of(...)` and comparing paths keeps tests independent of arbitrary provider ordering.

In this project, fixtures deliberately cause one failing rule per field at a time (e.g., empty email fails `@NotBlank` while `@Email` accepts empty strings). If more constraints are added, update tests to match the actual code/path sets.

## 10. MockMvc Tests: `@Valid`, `@Validated`, and Group Hints Over HTTP

Create `src/test/java/com/example/groups/GroupMvcTest.java`:

~~~java
package com.example.groups;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class GroupMvcTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    private ObjectNode validJson() {
        ObjectNode root = mapper.createObjectNode();
        root.put("email", "lan@example.com");
        root.put("age", 25);
        root.put("companyCode", "COMPANY-1");
        root.put("acceptedTerms", true);

        root.putObject("address")
                .put("city", "Ha Noi")
                .put("zipCode", "12345")
                .put("districtCode", "D1");

        return root;
    }

    private ResultActions send(
            String endpoint,
            ObjectNode json) throws Exception {

        return mvc.perform(post(
                        "/api/registrations/" + endpoint)
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(json)));
    }

    @Test
    void defaultEndpointIgnoresNonDefaultGroups()
            throws Exception {

        ObjectNode request = validJson();

        request.put("companyCode", "");
        request.put("acceptedTerms", false);
        ((ObjectNode) request.get("address"))
                .put("zipCode", "");

        send("default", request)
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.result")
                        .value("accepted"));
    }

    @Test
    void defaultEndpointRejectsDefaultViolation()
            throws Exception {

        ObjectNode request = validJson();
        request.put("email", "");

        send("default", request)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].field")
                        .value("email"))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].code")
                        .value("NotBlank"));
    }

    @Test
    void orderedStopsAtDefault() throws Exception {
        ObjectNode request = validJson();

        request.put("email", "");
        request.put("age", 16);
        request.put("companyCode", "");
        request.put("acceptedTerms", false);

        ((ObjectNode) request.get("address"))
                .put("city", "")
                .put("zipCode", "");

        send("ordered", request)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors.length()")
                        .value(3))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].field")
                        .value("address.city"))
                .andExpect(jsonPath(
                        "$.fieldErrors[1].field")
                        .value("age"))
                .andExpect(jsonPath(
                        "$.fieldErrors[2].field")
                        .value("email"));
    }

    @Test
    void orderedStopsAtBusiness() throws Exception {
        ObjectNode request = validJson();

        request.put("companyCode", "");
        request.put("acceptedTerms", false);

        ((ObjectNode) request.get("address"))
                .put("zipCode", "");

        send("ordered", request)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors.length()")
                        .value(2))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].field")
                        .value("address.zipCode"))
                .andExpect(jsonPath(
                        "$.fieldErrors[1].field")
                        .value("companyCode"));
    }

    @Test
    void orderedReachesFinalAfterEarlierStagesPass()
            throws Exception {

        ObjectNode request = validJson();
        request.put("acceptedTerms", false);

        send("ordered", request)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors.length()")
                        .value(1))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].field")
                        .value("acceptedTerms"))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].code")
                        .value("AssertTrue"));
    }

    @Test
    void orderedAcceptsValidBody() throws Exception {
        send("ordered", validJson())
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.result")
                        .value("accepted"));
    }

    @Test
    void businessOnlyCanMissDefaultViolations()
            throws Exception {

        ObjectNode request = validJson();
        request.put("email", "");
        request.put("age", 16);
        request.put("acceptedTerms", false);
        ((ObjectNode) request.get("address"))
                .put("city", "");

        // Intentional warning: this endpoint illustrates
        // how choosing the wrong group can let Default slip through.
        send("business", request)
                .andExpect(status().isCreated());
    }

    @Test
    void unorderedChecksAllRequestedGroups()
            throws Exception {

        ObjectNode request = validJson();

        request.put("email", "");
        request.put("age", 16);
        request.put("companyCode", "");
        request.put("acceptedTerms", false);

        ((ObjectNode) request.get("address"))
                .put("city", "")
                .put("zipCode", "");

        send("unordered", request)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors.length()")
                        .value(6));
    }

    @Test
    void malformedJsonFailsBeforeBeanValidation()
            throws Exception {

        mvc.perform(post("/api/registrations/ordered")
                        .contentType(
                                MediaType.APPLICATION_JSON)
                        .content("{"))
                .andExpect(status().isBadRequest());
    }
}
~~~

### 10.1. Why Test at Both Layers?

`GroupValidationTest` invokes Jakarta `Validator` directly to verify rules and group sequences **independently of HTTP**. `GroupMvcTest` verifies Spring argument resolution, `@Valid`/`@Validated` hints, Jackson, exception handling, and response contracts.

If unit tests PASS yet MockMvc fails to run the desired group, focus on controller annotations, validation provider integration, method signatures, and MVC configuration. If unit tests also produce no violations, focus on annotation `groups`, test fixtures, cascade/`@ConvertGroup`, and sequence definitions.

**Total 21 tests:** 12 unit and 9 MockMvc tests per the source above. They verify even cases where the system *intentionally* skips later groups, rather than testing only completely valid inputs.

## 11. Running and Expected HTTP Responses

### 11.1. Run Commands

In the directory containing `pom.xml`, requiring JDK 17+ and Maven:

~~~bash
mvn test
mvn spring-boot:run
~~~

Run individually:

~~~bash
mvn -Dtest=GroupValidationTest test
mvn -Dtest=GroupMvcTest test
~~~

### 11.2. Valid JSON Sample

~~~json
{
  "email": "lan@example.com",
  "age": 25,
  "companyCode": "COMPANY-1",
  "acceptedTerms": true,
  "address": {
    "city": "Ha Noi",
    "zipCode": "12345",
    "districtCode": "D1"
  }
}
~~~

Send:

~~~bash
curl -i -X POST \
  http://localhost:8080/api/registrations/ordered \
  -H "Content-Type: application/json" \
  -d '{
    "email":"lan@example.com",
    "age":25,
    "companyCode":"COMPANY-1",
    "acceptedTerms":true,
    "address":{
      "city":"Ha Noi",
      "zipCode":"12345",
      "districtCode":"D1"
    }
  }'
~~~

Expected HTTP **201 Created** response:

~~~json
{
  "result": "accepted",
  "email": "lan@example.com"
}
~~~

### 11.3. `Default` Fails So `Business`/`Final` Are Not Reached

~~~bash
curl -i -X POST \
  http://localhost:8080/api/registrations/ordered \
  -H "Content-Type: application/json" \
  -d '{
    "email":"",
    "age":16,
    "companyCode":"",
    "acceptedTerms":false,
    "address":{
      "city":"",
      "zipCode":"",
      "districtCode":""
    }
  }'
~~~

Even though many fields are invalid across all groups, **`OrderedChecks` stops after `Default`**. Expected 400 response:

~~~json
{
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {"field": "address.city", "code": "NotBlank"},
    {"field": "age", "code": "Min"},
    {"field": "email", "code": "NotBlank"}
  ],
  "globalErrors": []
}
~~~

The absence of `companyCode`, `address.zipCode`, or `acceptedTerms` here **is not a bug**; they belong to groups that have not run yet. `districtCode` belongs to `AddressReview`, which is neither in `OrderedChecks` nor converted on `RegistrationRequest`, so it is not evaluated on this endpoint.

### 11.4. `Business` Fails So `Final` Is Skipped

A request where `Default` passes yet `companyCode=""`, `address.zipCode=""`, and `acceptedTerms=false` returns 400 with:

~~~json
{
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {"field": "address.zipCode", "code": "NotBlank"},
    {"field": "companyCode", "code": "NotBlank"}
  ],
  "globalErrors": []
}
~~~

`acceptedTerms` does not appear because `FinalChecks` was not reached.

### 11.5. Cases Highlighting Failure Differences

| Endpoint | Input | Result |
| --- | --- | --- |
| `/default` | Default valid, Business/Final invalid | **201**, because custom groups were not requested |
| `/ordered` | Default invalid | **400**, only Default errors |
| `/ordered` | Default passes, Business invalid | **400**, only Business errors |
| `/ordered` | Default/Business pass, Final invalid | **400**, only Final errors |
| `/ordered` | All pass | **201** |
| `/business` | Business passes, Default invalid | **201**, illustrating incomplete group selection bug |
| `/unordered` | All groups have errors | **400**, errors across all requested groups |
| `/ordered` | Unparseable JSON | **400** from decoding, group sequence never runs |

The 201 status on `/business` is an **intentional architectural warning**, not a recommended production design.

## 12. Common Diagnostic Mistakes

| Symptom | Possible Cause | Check and Fix |
| --- | --- | --- |
| Constraint with `groups=FinalChecks.class` does not fail with `@Valid` | `@Valid` requests only Default by default | Use `@Validated(FinalChecks.class)` or a suitable sequence |
| Created `OrderedChecks` yet `validator.validate(bean)` unchanged | Sequence was not requested | Call `validate(bean,OrderedChecks.class)` |
| Final does not run even when Final field is invalid | Prior Default or Business has violations | Test each stage of the sequence |
| Passing three groups reports errors across all three | Multiple groups do not guarantee order/short-circuiting | Use a `@GroupSequence` interface |
| `@GroupSequence({Default.class,...})` on class throws `GroupDefinitionException` | Broken Default redefinition | Replace `Default.class` with the class itself |
| Sequence interface extends another group | Invalid sequence/inheritance relationship | Sequence interfaces should not extend other groups |
| Sequence A includes B and B includes A | Group cycle | Break cycle, test metadata |
| Constraint declares `groups=OrderedChecks.class` | Sequence interface used directly as constraint group | Assign to component groups |
| Business group requested yet nested zip unchecked | Missing `@Valid` on cascade edge or null object | Check `@NotNull @Valid` and path |
| Parent has Default sequence yet child skips parent's extra group | Default redefinition is local | Use `@ConvertGroup` on association if needed |
| After `@ConvertGroup`, Address's Default `city` is not reported | Default on that edge converted to `AddressReview` | Adjust conversion/rules per use case |
| `@ConvertGroup` has no effect | Missing `@Valid` or `from` misses expanded group | Check cascade and actual group |
| Final group does not run despite `@Validated` on DTO | Annotation placed at wrong boundary or different method validation | Check method signature and exception type |
| `@Validated` service self-invocation skips validation | Bypasses Spring AOP proxy | Call across proxy/service boundary or Validator directly |
| Tests lack Hibernate Validator | Missing validation provider/starter | Add `spring-boot-starter-validation` |
| Seeing `MethodArgumentNotValidException` instead of expected exception | Argument-level MVC validation | Inspect `BindingResult` and advice |
| Seeing `HandlerMethodValidationException` | Direct method constraints in MVC 6.1+ | Test native method validation/different handler |
| Field `age="abc"` produces no `@Min` violation | Type conversion/deserialization failed before Bean Validation | Test decoding separately |
| Group test count changes when fail-fast enabled | Provider stops early within the same group | Do not rely on exact count under fail-fast |
| Violation order varies across machines | `Set` has no guaranteed order | Compare sets of paths/codes, never `iterator().next()` |
| Bean's `Default` redefined yet child behaves differently | Local rule does not propagate full sequence | Test parent and nested separately |
| Adding class-level `@Validated` on a new controller | AOP method validation may alter native behavior | Confirm controller architecture and Spring version |
| Using `@Valid` on `Mono<T>` in MVC expecting immediate run | Reactive arguments differ from Servlet binding | Choose the right MVC/WebFlux pipeline |

## 13. When to Use `@Validated({Default, Business, Final})` vs. a Sequence?

There are two different business intentions:

### 13.1. Collecting All Relevant Errors in One Pass

~~~java
validator.validate(
        request,
        Default.class,
        BusinessChecks.class,
        FinalChecks.class);
~~~

This fits when the frontend wants to display **all errors across multiple groups** and checking later groups does not depend on earlier groups being valid. **Never** rely on evaluation order among independent groups.

### 13.2. Performing Staged Validation

~~~java
validator.validate(
        request,
        OrderedChecks.class);
~~~

This fits when business checks only make sense once foundational data is valid, or final checks are expensive and unnecessary if basic validation failed. If one stage fails, subsequent stages are skipped by sequence definition.

**Do not choose a sequence merely to "make tests easier to write"**: it changes the error set returned to users. Decide whether UX/API contracts want all errors at once or staged errors.

## 14. Defining Groups by Business Function Rather Than Tech Layer

A clean model:

~~~text
Default         → syntax, null/blank, types, and basic bounds
BusinessChecks  → screen-specific business rules
FinalChecks     → rules applying only upon final submission
AddressReview   → address data in a dedicated step
~~~

Not every basic constraint must sit in `Default`. However, when splitting groups, a new developer might mistakenly assume `@Valid` "checks everything." Therefore:

- Document which group each endpoint/use case uses.
- Name groups after business intent (`FinalSubmit`, `DraftChecks`, `PaymentChecks`) rather than `Group1`.
- Avoid complex group-dependency nesting when explicit manual validation is clearer.
- Never use validation groups to enforce access control (`role`, `owner`, `approval` belong to authorization/services).
- When moving a constraint from `Default` to another group, update integration tests because `@Valid` endpoints may stop catching it.

## 15. Group Conversion in `List`, `Map`, and Nested Graphs

With collections:

~~~java
public record BatchRequest(
        @Valid
        List<@Valid Address> addresses) {
}
~~~

This is a snippet. Cascading into each element checks constraints in **the currently propagated group**. If `Address` has `zipCode` in `BusinessChecks`, a Default-only call will not activate `zipCode` merely because it sits in a list.

You can place `@ConvertGroup` on the appropriate Jakarta Bean Validation type-use/cascade position to translate groups when traversing collection elements, e.g.:

~~~java
public record BatchReview(
        List<
            @Valid
            @ConvertGroup(
                from = Default.class,
                to = AddressReview.class)
            Address> addresses) {
}
~~~

This is a type-use snippet supported by Jakarta Validation 3.0 compatible providers; it requires `List`, `Valid`, `ConvertGroup`, and `Default` imports. Test the property path, such as `addresses[0].districtCode`, against your real provider/version. Declaring `@ConvertGroup` on the collection without cascading at the right position will not trigger the desired group conversion.

Specifically, when a parent class redefines its `Default` sequence, do not assume the full sequence propagates intact to every element; rely on **expanded groups and per-edge conversion rules**. Debug level by level through the graph.

## 16. Checking Custom Constraints and Meta-Annotations

When writing a custom constraint:

~~~java
@Target({ FIELD, PARAMETER })
@Retention(RUNTIME)
@Constraint(validatedBy = UniqueCodeValidator.class)
public @interface UniqueCode {
    String message() default "Code already in use";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

This is an annotation-design snippet, not a runnable file in the demo (it needs the validator and imports). In Jakarta Bean Validation, a custom constraint annotation must declare compatible `groups()` and `payload()`; callers pick groups when applying it:

~~~java
@UniqueCode(groups = BusinessChecks.class)
private String companyCode;
~~~

If a custom annotation has invalid target/retention/validator type, `ConstraintDefinitionException` or `UnexpectedTypeException` may occur. That is a **metadata/validator configuration error**, distinct from a group being skipped by a sequence. Never catch every exception as "group did not run" and ignore internal stack traces.

When a composed constraint combines multiple inner annotations, testing violation counts may require understanding `@ReportAsSingleViolation`; inspect **codes, paths, and descriptors** instead of counts alone.

## 17. Regression Testing Checklist When Upgrading

1. Verify Java 17+, Boot/Spring Framework/Hibernate Validator versions, and Jakarta namespace.
2. Check `@Valid`, `@Validated(...)`, `@ModelAttribute`, or `@RequestBody` on the exact controller argument.
3. List actual group declarations for each constraint via metadata.
4. Write `validator.validate(bean)` tests for `Default`.
5. Write `validator.validate(bean,Custom.class)` tests for each group.
6. Write `validator.validate(bean,Sequence.class)` tests for each stage.
7. Write a "multiple independent groups" test to avoid confusing it with a sequence.
8. For class-level Default redefinitions, verify the class itself is inside `@GroupSequence`.
9. If nested validation does not run, check `@Valid`, null state, and group conversion.
10. If using Hibernate `@GroupSequenceProvider`, test all state branches and null-safe logic.
11. If Spring MVC exception types changed, inspect direct method constraints and class-level `@Validated`.
12. If a custom validator depends on services/data access, test actual invocation, not just Spring Bean metadata.
13. If messages are missing, separate i18n/`MessageSource` tests from group activation tests.
14. Never depend on iteration order of `Set<ConstraintViolation<?>>`.
15. If fail-fast is enabled, do not assume every group collects all violations.
16. For forms/JSON with conversion errors, test parsing/binding separately.
17. When validation groups exist for draft/final, test each endpoint under its matching business group.
18. Ensure validation failures cause no side effects (DB writes, events, workflow triggers).
19. Never treat validation groups as authorization groups; test permissions in security/service layers.
20. Keep one unit test intentionally exercising a broken Default redefinition so the team recognizes `GroupDefinitionException`.

## 18. Practice Exercises

**Exercise 1 — Default and Final.** Put `@NotBlank(groups=FinalChecks.class)` on `approvalCode`. Call `validator.validate(bean)` with an empty `approvalCode`; explain why no violation appears. Write a test calling `validator.validate(bean,FinalChecks.class)`.

**Exercise 2 — Short-circuiting.** Use `@GroupSequence({Default,BusinessChecks,FinalChecks})` on an interface. Create a bean failing all three groups; verify only the first group is reported. After fixing `Default`, which group is reported next?

**Exercise 3 — Wrong `GroupSequence` style.** Place `@GroupSequence({Default.class, BusinessChecks.class})` on a bean class. Predict the exception and fix it by replacing `Default.class` with the bean class.

**Exercise 4 — Group inheritance.** Create `PremiumBusinessChecks extends BusinessChecks`. Do `BusinessChecks` constraints run when requesting only `PremiumBusinessChecks`? Is `Default` added automatically?

**Exercise 5 — Nested cascade.** Remove `@Valid` from `Address` in `RegistrationRequest`. Why does `address.zipCode` disappear from `BusinessChecks` errors? Write a test proving it.

**Exercise 6 — `@ConvertGroup`.** Attach `@ConvertGroup(from=Default.class,to=AddressReview.class)` to nested `Address`. Submit `city=""`, `districtCode=""` and validate `Default`; which error path still appears?

**Exercise 7 — Spring MVC.** Change an endpoint from `@Validated(OrderedChecks.class)` back to `@Valid`. With an empty `companyCode` yet valid `Default`, how does HTTP status change? Why?

**Exercise 8 — Unordered.** Replace the sequence with `@Validated({Default.class,BusinessChecks.class,FinalChecks.class})`. Write a test asserting the set of paths rather than order.

**Exercise 9 — Native method validation.** Add `@Min(1)` on a `@RequestParam` in Spring MVC 6.1+. Predict when `HandlerMethodValidationException` replaces `MethodArgumentNotValidException`.

**Exercise 10 — Service AOP.** A `@Validated` service calls `this.submit(...)` on itself. Write tests comparing proxy calls vs. internal calls, explaining self-invocation and proper boundary design.

**Exercise 11 — Hibernate extension.** Use `@GroupSequenceProvider` for Draft and Final states. Ensure the provider is null-safe and avoid relying on client-controlled flags for authorization.

**Exercise 12 — API contract.** Design a JSON response with `field`, `code`, and group diagnostics for logs/tests only without leaking `rejectedValue`. Write tests for `Default`/`Business`/`Final` errors at each stage.

## Conclusion

When encountering "a group did not run," trace **requested group → sequence → cascade/conversion → Spring validation entry point**:

~~~text
@Valid or Validator.validate(bean)
        |
        v
Default (unless class redefines Default)
        |
        +-- @GroupSequence on an interface?
        |      Must request that sequence interface itself.
        |
        +-- Class-level @GroupSequence?
        |      Must include the class itself, not Default.class.
        |
        +-- Error in an earlier group?
        |      Sequence STOPS; skipping later groups is expected.
        |
        +-- Nested @Valid?
        |      Group propagates, optionally translated by @ConvertGroup.
        |
        +-- @Validated at Spring boundary?
               Check hints / method validation / AOP proxy.
~~~

**Three things to remember:** `@Valid` does not run every group by default; `@GroupSequence` enforces ordering **and stops when a group fails**; `@GroupSequence` on a **class** must include the class itself to redefine `Default`. Direct `jakarta.validation.Validator` tests combined with MockMvc and metadata descriptors let you distinguish a group that was never requested, legitimately short-circuited, translated across a cascade, or never triggered at the Spring boundary.

## References

- [Jakarta Bean Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/)
- [Hibernate Validator 8 — Reference Guide, Chapter 5 Validation groups](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#chapter-groups)
- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — MVC Validation Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html)
- [Spring Framework 6.2 — @Validated Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/annotation/Validated.html)
- [Spring Framework 6.2 — Java Bean Validation Integration](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — MethodArgumentNotValidException API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/bind/MethodArgumentNotValidException.html)
- [Jakarta Validation — ConstraintDescriptor API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/metadata/ConstraintDescriptor.html)
