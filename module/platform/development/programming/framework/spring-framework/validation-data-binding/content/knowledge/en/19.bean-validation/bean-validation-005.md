# `validate`, `validateProperty`, and `validateValue` in Bean Validation

## 1. The Problem: Validate the Whole Object, One Property, or an Incoming Candidate Value?

Suppose a registration form in a Spring application has three inputs: username, password, age, along with a contact address. When the user clicks **Submit**, the backend needs to validate the entire object; when the user leaves the **password** box, the UI only wants to validate that property; when the user has just typed a value without assigning it to a bean yet, the backend wants to test a **hypothetical value**.

Jakarta Bean Validation cleanly separates these three scenarios via the **`jakarta.validation.Validator`** interface:

- **`validate(object, groups...)`**: validates **an existing object**, class-level constraints, properties, and nested objects marked for cascading with `@Valid`.
- **`validateProperty(object, propertyName, groups...)`**: validates **a property of an existing object** using constraints attached to that property, reading the actual value currently inside the bean.
- **`validateValue(beanType, propertyName, candidate, groups...)`**: validates **a candidate value** against constraints declared on a class property, without requiring a bean instance and without assigning that value to any bean.

This is **Jakarta Bean Validation** (API 3.x typically paired with Spring Framework 6 / Spring Boot 3), distinct from `validate(Object, Errors)` in Spring's `org.springframework.validation.Validator` interface. An older Spring project may use the `javax.validation.*` package; do not mix `javax` and `jakarta` when selecting dependencies.

Quick invocation example:

```java
Set<ConstraintViolation<RegistrationForm>> all = validator.validate(form);
Set<ConstraintViolation<RegistrationForm>> current =
        validator.validateProperty(form, "password");
Set<ConstraintViolation<RegistrationForm>> candidate =
        validator.validateValue(RegistrationForm.class, "password", "123");
```

The snippet above only illustrates the API; the `RegistrationForm` class, `validator`, and imports are fully defined in the runnable section.

## 2. General Mechanism of `jakarta.validation.Validator`

A bean carries constraints via annotations such as `@NotNull`, `@NotBlank`, `@Size`, `@Min`, `@Email`, `@Pattern`, or custom project-defined constraints. Constraints may sit on fields, getters, types, container elements, or at the class level, depending on the annotation's `@Target`.

`Validator` does not create or mutate data. It inspects **constraint metadata**, selects validation groups, executes the `ConstraintValidator`s of relevant constraints, and returns a `Set<ConstraintViolation<T>>`. An empty set means all constraints executed within the requested scope passed; **it does not mean every business rule of the application has been checked**.

A `ConstraintViolation` can provide:

| Component | Meaning |
| --- | --- |
| `getPropertyPath()` | Path to the violated constraint, e.g., `password` or `address.street` |
| `getMessage()` | Interpolated message, potentially locale-dependent |
| `getMessageTemplate()` | Message template before interpolation |
| `getInvalidValue()` | Violating value; handle carefully with sensitive data |
| `getConstraintDescriptor()` | Constraint metadata and attributes such as `min`, `max` |
| `getRootBeanClass()` | Root bean class used as the validation context |
| `getRootBean()` | Root bean instance when available; may be `null` with `validateValue` |

**`Set` element order is not guaranteed.** Do not rely on violation iteration order to define display order. If deterministic stdout/tests are needed, explicitly sort by path or an appropriate key.

### 2.1. Null, empty strings, and validating multiple constraints

Many annotations **allow `null`**, because they only inspect a value when present: for instance, `@Size(min=8)` does not replace `@NotNull`; `@Min(18)` on an `Integer` does not automatically reject `null`. Conversely, `@NotNull` rejects `null` while allowing `""` and `"  "`; `@NotBlank` applies only to `CharSequence` and rejects `null`, empty, or whitespace-only strings.

Example:

```java
@NotBlank
@Size(min = 3, max = 30)
private String username;
```

The username must contain a non-whitespace character and have length within bounds. If the value is `"a"`, `@NotBlank` passes while `@Size(min=3)` fails. If the value is `null`, both validity and the number of violations depend on the selected constraints and check configuration; do not infer that only one violation is always produced.

### 2.2. Constraint violations vs binding errors

`Validator` receives Java values already in the proper types. It **does not convert** `"twenty"` into `int`, does not perform HTTP request binding, and does not repair user input. In Spring MVC, `DataBinder`/`ConversionService` converts data first, then Bean Validation checks constraints; `BindingResult` can hold both binding and validation errors.

When using `validateValue`, supply a value whose type is compatible with the constraint. Passing an incompatible type can cause a configuration/type exception rather than a clean violation. Validating raw input usually requires a separate parse/conversion step.

## 3. `validate(object, groups...)`: Validating the Whole Bean and Cascaded Objects

Condensed signature:

```java
<T> Set<ConstraintViolation<T>> validate(
        T object, Class<?>... groups);
```

The framework selects constraints applicable to the runtime type and requested groups; by default, when no group is passed, `jakarta.validation.groups.Default` is used.

In scope, `validate(form)` can evaluate:

1. Property constraints on the form (annotated fields or getters).
2. Constraints on the form type itself at the **class level**, e.g., checking `startDate <= endDate`.
3. Constraints on **child objects** when the association is marked with `@Valid`; the error path can be `address.street`.
4. Container element constraints, e.g., `List<@NotBlank String> tags`, and element cascading such as `List<@Valid Address>` when supported.
5. Declared validation groups and group conversion/sequence rules.

Example distinguishing cascade:

```java
class Customer {
    @NotBlank String name;
    @Valid Address address;
}
class Address {
    @NotBlank String street;
}
```

If `address.street` is blank and `address` is non-null, `validate(customer)` can report an `address.street` violation; a `@Valid` annotation on a field only enables traversal into the child object, **it is not itself a non-`null` constraint**. If `address == null`, a separate `@NotNull` is needed to forbid null; `@Valid` does not reject null.

**When to use:** validating a full DTO/command object before processing a request, validating configuration loaded from external sources, validating a bean before persisting critical state, or running tests on overall constraints.

**Note:** it does not replace access control, user authentication, database uniqueness checks, transactions, or domain business rules. Do not call `validate` and assume state cannot change before use.

## 4. `validateProperty(object, propertyName, groups...)`: Validating an Existing Property

Condensed signature:

```java
<T> Set<ConstraintViolation<T>> validateProperty(
        T object, String propertyName, Class<?>... groups);
```

If `form.getPassword()` is currently `"123"` and the `password` field has `@Size(min=8)`, `validator.validateProperty(form, "password")` checks the **current value** of that field. There is no need to validate the entire form.

The narrow scope has an easily missed difference:

- Only constraints attached to the **selected property** are applied.
- **Does not perform cascaded validation via `@Valid`**, even if the selected property is a child object.
- Does not evaluate class-level/cross-field constraints on the parent bean merely because they may involve the selected field.
- Does not traverse nested paths like a full `validate` traversal; do not assume `"address.street"` is supported as a property name. If you need to validate a single nested property, extract the child bean and call `validateProperty(address, "street")`, or validate the full root bean.
- `propertyName` must identify a valid property of the validated type. A wrong name or `null` object can lead to `IllegalArgumentException` rather than an empty `Set`.

For example, if `RegistrationForm.address` is marked only with `@Valid`, while `@NotBlank` sits on `Address.street`, then:

```java
validator.validate(form);                       // can see address.street
validator.validateProperty(form, "address");    // no cascade -> empty set
validator.validateProperty(form, "password");   // checks current password
```

**When to use:** a UI wants quick validation of a single field already bound to a model, a wizard step only needs to report errors for one property, or business logic only wants local constraints for a specific property.

**Should not be used alone** to conclude the entire form is valid, especially when multi-property constraints, class-level constraints, and nested beans exist. Before processing/persisting critical data, validation with an appropriate scope is still required.

## 5. `validateValue(beanType, propertyName, candidate, groups...)`: Validating a Hypothetical Value

Condensed signature:

```java
<T> Set<ConstraintViolation<T>> validateValue(
        Class<T> beanType, String propertyName, Object value,
        Class<?>... groups);
```

`validateValue` relies on constraint metadata declared on a property of the `beanType` **class**. It tests `candidate` **as if** that value were to be placed in the property, without a bean instance and without mutating state.

```java
validator.validateValue(
        RegistrationForm.class, "password", "123");

validator.validateValue(
        RegistrationForm.class, "password", "strong-password");
```

The first case violates `@Size(min=8)`; the second satisfies this constraint. Other properties on any bean are neither observed nor modified.

Consequences:

- **No need to instantiate `RegistrationForm`** and no touching the password currently held on any specific instance.
- **Does not cascade `@Valid`** into nested objects passed as candidates. For example, `validateValue(RegistrationForm.class, "address", new Address(""))` returns empty if `address` has no direct constraints, even though `Address.street` has `@NotBlank`.
- **Does not evaluate class-level/cross-field constraints**, because there is no state from other properties to compare against. A rule like "end date must be after start date" cannot be guaranteed by `validateValue` for one field.
- The input value should already have the target type (or null when testing nullability). `validateValue` does not replace `ConversionService` or a JSON deserializer.
- For custom constraints needing access to other properties, `validateValue` for a single field does not provide a real bean; if logic requires full context, design a cross-field class-level validator and call `validate(object)`.

**When to use:** validating a trial input before object construction, checking a candidate during property-by-property entry, supporting form metadata, or testing a field's rules without instantiating a bean.

### 5.1. Direct Comparison of the Three Methods

| Feature | `validate` | `validateProperty` | `validateValue` |
| --- | --- | --- | --- |
| Primary arguments | Bean instance | Bean instance + field name | Bean class + field name + candidate |
| Reads value from bean | Yes | Yes, at selected field | No |
| Requires instance | Yes | Yes | No |
| Checks multiple properties | Yes | No | No |
| Class-level constraints | Yes | No | No |
| `@Valid` cascading | Yes | No | No |
| Checks field constraints | Yes | Yes | Yes |
| Uses custom groups | Yes | Yes | Yes |
| Mutates/converts value | No | No | No |
| Returns `Set<ConstraintViolation<T>>` | Yes | Yes | Yes |
| Typical use case | Form submission, object graph check | Check a field already stored in a bean | Check a candidate before assignment |

A helpful mnemonic: with `form.password = "123"`:

- `validate(form)` may report password, username, and address.
- `validateProperty(form, "password")` inspects only the current password `"123"`.
- `validateValue(RegistrationForm.class, "password", "long-enough")` inspects only the new value `"long-enough"`; `form.password` remains `"123"`.

## 6. Complete Java 17+ Example: Checking Results and Distinguishing Groups/Cascading

The example uses **Jakarta Bean Validation** with **Hibernate Validator 8.x** as the provider. Spring Framework is not required in the standalone program; a later section shows how to use the same `Validator` in Spring MVC.

### 6.1. Create the Maven Project

Create `pom.xml` in the working directory:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>validator-methods-demo</artifactId>
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
    </dependencies>
</project>
```

The `hibernate-validator` dependency pulls in the Jakarta Validation API and required dependencies. To run this small CLI without the Jakarta Expression Language (EL) library, the example explicitly uses Hibernate Validator's `ParameterMessageInterpolator`; for applications using EL expressions in message templates, configure EL accordingly. `ParameterMessageInterpolator` is a provider detail, not part of the standard Bean Validation interface.

### 6.2. Create `ValidatorMethodsDemo.java`

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import jakarta.validation.groups.Default;

import org.hibernate.validator.HibernateValidator;
import org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator;

import java.util.List;
import java.util.Set;

public class ValidatorMethodsDemo {

    // Additional business group: only check age when this group is requested.
    public interface AgePolicy {}

    public static final class Address {
        @NotBlank
        private final String street;

        public Address(String street) {
            this.street = street;
        }
    }

    public static final class RegistrationForm {
        @NotBlank
        private final String username;

        @Size(min = 8)
        private final String password;

        @Min(value = 18, groups = AgePolicy.class)
        private final int age;

        @Valid
        private final Address address;

        public RegistrationForm(
                String username, String password, int age, Address address) {
            this.username = username;
            this.password = password;
            this.age = age;
            this.address = address;
        }

        public String getPassword() {
            return password;
        }
    }

    private static void show(
            String name, Set<? extends ConstraintViolation<?>> violations) {
        List<String> paths = violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .toList();
        System.out.println(name + " -> " + violations.size() + " " + paths);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory = Validation
                .byProvider(HibernateValidator.class)
                .configure()
                .messageInterpolator(new ParameterMessageInterpolator())
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            RegistrationForm form = new RegistrationForm(
                    "", "123", 16, new Address(""));

            show("validate(Default)", validator.validate(form));
            show("validate(AgePolicy)",
                    validator.validate(form, AgePolicy.class));
            show("validate(Default, AgePolicy)",
                    validator.validate(form, Default.class, AgePolicy.class));

            show("validateProperty(password)",
                    validator.validateProperty(form, "password"));
            show("validateProperty(address)",
                    validator.validateProperty(form, "address"));

            show("validateValue(password=123)",
                    validator.validateValue(
                            RegistrationForm.class, "password", "123"));
            show("validateValue(password=long-enough)",
                    validator.validateValue(
                            RegistrationForm.class, "password", "long-enough"));
            show("validateValue(age=16, AgePolicy)",
                    validator.validateValue(
                            RegistrationForm.class, "age", 16, AgePolicy.class));
            show("validateValue(address)",
                    validator.validateValue(
                            RegistrationForm.class, "address", new Address("")));

            System.out.println("originalPassword=" + form.getPassword());
        }
    }
}
```

**How to run** with JDK 17+ and Maven installed:

Bash (Linux/macOS):

```bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
CP="$(cat classpath.txt)"
javac -encoding UTF-8 -cp "$CP" ValidatorMethodsDemo.java
java -cp ".:$CP" ValidatorMethodsDemo
```

PowerShell (Windows):

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$cp = (Get-Content -Raw classpath.txt).Trim()
javac -encoding UTF-8 -cp $cp ValidatorMethodsDemo.java
java -cp ".;$cp" ValidatorMethodsDemo
```

**Expected stdout** (excluding provider startup or dependency download warnings/logs):

```text
validate(Default) -> 3 [address.street, password, username]
validate(AgePolicy) -> 1 [age]
validate(Default, AgePolicy) -> 4 [address.street, age, password, username]
validateProperty(password) -> 1 [password]
validateProperty(address) -> 0 []
validateValue(password=123) -> 1 [password]
validateValue(password=long-enough) -> 0 []
validateValue(age=16, AgePolicy) -> 1 [age]
validateValue(address) -> 0 []
originalPassword=123
```

### 6.3. Analyzing Each Result

- `validate(Default)` returns three properties: `username`, `password`, and `address.street`. The nested path appears because `address` is annotated with `@Valid`; `@Min` on `age` belongs only to the `AgePolicy` group, so it did not run yet.
- `validate(AgePolicy)` returns one violation for `age`; constraints belonging to `Default` do not automatically run when only this custom group is requested.
- `validate(Default, AgePolicy)` runs both group sets, returning four paths.
- `validateProperty(password)` checks `@Size(min=8)` on the existing value `"123"`.
- `validateProperty(address)` returns empty because the `address` property has no direct constraint, only `@Valid` for cascading in `validate`.
- `validateValue(password=123)` fails, whereas candidate `"long-enough"` passes `@Size(min=8)`, even though the form's actual field has not changed.
- `validateValue(age=16, AgePolicy)` fails because the right group was passed.
- `validateValue(address)` does not cascade to `Address.street`, so it returns empty.
- `originalPassword=123` proves the validation calls do not mutate the instance.

To keep stdout consistent across environments, the program prints only the violation count and **sorted** property paths, rather than printing `Set` in arbitrary order or messages that may vary by locale. Remember that a single field can produce multiple violations if multiple constraints on it fail; violation count does not default to the number of invalid fields.

## 7. Validation Groups: Different Groups Can Yield Different Results

All three methods accept `Class<?>... groups`. When **no** group is specified, the `Default` group is applied. When **specifying** a custom group, do not assume `Default` still runs alongside it: e.g., `validator.validate(form, AgePolicy.class)` only runs constraints belonging to `AgePolicy` (or related constraints via group inheritance/conversion/sequence metadata).

```java
public interface Create {}
public interface Update {}

@NotBlank(groups = Create.class)
private String initialPassword;

@NotNull(groups = {Create.class, Update.class})
private Long accountId;
```

This is an illustrative snippet inside a bean, not a standalone compilable file. If a constraint must always be checked across both operations, specify the right groups or design an appropriate group sequence. Groups can inherit, and `@GroupSequence` defines ordering/short-circuiting rules by group. A group sequence is quite different from passing multiple plain groups, and passing multiple groups without a sequence does not guarantee execution order.

**Cascading and group conversion:** in `validate(root)`, `@Valid` can convert groups when descending into nested objects using `@ConvertGroup`; that is a cascade feature. For `validateProperty` and `validateValue`, there is no cascading, so neither method can validate the full `@ConvertGroup` effect across an object tree.

**Staged validation:** multi-step forms can call `validateProperty` or `validateValue` for quick feedback, but before saving you should call `validate(form, relevantGroups...)` to execute class-level and nested constraints as well. If a rule says "only on update may a field be left blank", define group and constraint policies explicitly rather than picking an arbitrary group and assuming the whole bean is valid.

## 8. Integration in Spring Framework / Spring MVC

### 8.1. Two Interfaces Named `Validator` That Are Easy to Confuse

- `jakarta.validation.Validator`: Jakarta API, with `validate`, `validateProperty`, `validateValue`, returning `Set<ConstraintViolation<T>>`.
- `org.springframework.validation.Validator`: Spring API, with `supports(Class<?>)` and `validate(Object, Errors)`, recording errors into `Errors`/`BindingResult`.

`org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` is the key bridge: it integrates a Bean Validation provider into Spring's validation mechanism and can be used via the Jakarta interface. In Spring Boot 3.x projects, the `spring-boot-starter-validation` starter normally provides Jakarta Validation API + provider; verify your project's actual dependencies. Importing the wrong interface is a common reason the IDE reports it cannot find `validateValue`.

To write a service calling all three APIs, explicitly inject the Jakarta interface:

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import org.springframework.stereotype.Service;
import java.util.Set;

@Service
public class RegistrationValidationService {
    private final Validator validator;

    public RegistrationValidationService(Validator validator) {
        this.validator = validator;
    }

    public Set<ConstraintViolation<RegistrationForm>> checkAll(
            RegistrationForm form) {
        return validator.validate(form);
    }

    public Set<ConstraintViolation<RegistrationForm>> checkField(
            RegistrationForm form, String propertyName) {
        return validator.validateProperty(form, propertyName);
    }

    public Set<ConstraintViolation<RegistrationForm>> checkCandidate(
            String candidatePassword) {
        return validator.validateValue(
                RegistrationForm.class, "password", candidatePassword);
    }
}
```

This is an **integration snippet**: the Spring project needs to provide a Jakarta `Validator` bean, `RegistrationForm`, and Bean Validation dependencies. In production, do not allow clients to pick arbitrary `propertyName` strings without restriction; define an allowlist of valid fields to avoid unintentionally expanding the validation surface or leaking metadata.

### 8.2. Automatic Validation in Controllers

With a form bound into a bean:

```java
@PostMapping("/registrations")
public ResponseEntity<?> create(
        @Valid @ModelAttribute RegistrationForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(bindingResult.getFieldErrors().stream()
                        .map(e -> e.getField() + ": " + e.getCode())
                        .toList());
    }

    return ResponseEntity.ok().build();
}
```

This is an illustrative snippet inside `@Controller`/`@RestController`, not a standalone Java program; it requires the right Spring MVC imports, Jakarta `@Valid`, and a model that Spring can bind (constructor/getters/setters or appropriate binder). For immutable bean forms, configure a suitable binding constructor; do not assume the immutable code in section 6 is automatically bound by MVC from every request type.

- `@Valid` triggers Bean Validation on the bound object, using the `Default` group by default; this is the **whole-object** validation path per Spring's configuration.
- Spring's `@Validated(SomeGroup.class)` lets you choose groups when validating an object; specify the desired groups explicitly.
- Place `BindingResult` **immediately after** the corresponding model parameter so the controller can read its errors; conversion, binding, and constraint errors may appear together.
- Spring MVC can throw different exceptions depending on `@ModelAttribute`, `@RequestBody`, method validation, and controller signature. Do not assume every validation failure automatically produces the same JSON/body/status unless an exception handler is defined.

`@RequestBody` JSON is converted into an object by a deserializer (typically Jackson) before validation runs. That `@Valid` checks a successfully read DTO does not mean Bean Validation handles JSON syntax or type conversion. For method parameter/return value constraints there is also **executable validation** (typically using `ExecutableValidator` or Spring integration), whose scope differs from the three bean-property methods in this lesson.

### 8.3. Translating Violations to UI Messages

Each violation has `propertyPath`, `message`, and constraint info. Applications should map these to appropriate error codes/UI semantics, avoiding exposing classes, passwords, sensitive raw values, or internal messages. In Spring MVC, `BindingResult.getFieldErrors()` and `getGlobalErrors()` distinguish field-bound errors from object-level errors.

Checking candidates with `validateValue` only serves early feedback. When accepting a request, you still must validate the final object state after binding, apply the necessary groups, and check business rules that cannot be expressed with annotations.

## 9. Commonly Misunderstood Cases

| Symptom | Cause | Solution |
| --- | --- | --- |
| `validateProperty(form, "address")` returns empty even though `address.street` is blank | `@Valid` does not cascade in `validateProperty` | Use `validate(form)` or validate the `address` bean separately |
| `validateValue` returns empty, yet submitting the whole form is rejected | Class-level or nested rules are not evaluated when checking a single candidate | Validate the full bean in the final step |
| Calling `validate(form, Create.class)` skips `@NotBlank` without `groups` | The constraint is in `Default` | Select the right groups or assign the constraint to the appropriate group |
| `@Size(min=8)` reports no error when password is `null` | `@Size` allows null | Add `@NotNull` or `@NotBlank` |
| `@NotNull` does not reject whitespace-only strings | `@NotNull` only forbids null | Use `@NotBlank` for strings |
| `getPropertyPath()` has no clear field | Class-level constraints may attach to the object node | Handle global errors too, not only field errors |
| Error count/test order fluctuates | `Set<ConstraintViolation<?>>` does not guarantee order | Sort by path and constraint code |
| Calling `validateValue` with a String for a non-String property throws an exception | Bean Validation does not handle conversion | Parse/bind to the right Java type first |
| `Validator` does not have `validateProperty` | Imported `org.springframework.validation.Validator` | Import `jakarta.validation.Validator` when using the Jakarta API |
| Using `javax.validation.*` with Spring 6/Jakarta provider | Incompatible namespace/dependencies | Align Jakarta API, provider, and Spring version |
| Validating one property while expecting cross-property rules to run | `validateProperty` excludes class-level/cross-field rules | Use `validate` to evaluate the whole bean |
| Displaying raw `getInvalidValue()` to the client | Can leak passwords, tokens, or sensitive data | Return safe codes/messages, never log secret values |
| Continuously creating a new provider factory per input | Bootstrapping metadata/provider is resource-intensive | Reuse `ValidatorFactory`/`Validator` or a container-managed bean |
| Expecting Bean Validation to sanitize data | Validation does not mutate beans | Fix data via normalization/conversion first, then validate |

### Required Tests for All Three APIs

1. Bean with multiple errors across different properties: `validate` returns a comprehensive violation set for the selected groups.
2. Child bean with `@Valid` and constraints: `validate(root)` sees the nested path, `validateProperty(root, "child")` does not cascade.
3. Valid/invalid candidate values: `validateValue` changes outcome per candidate, **the original bean stays unchanged**.
4. Test `Default` and a custom group: prove actual group selection behavior.
5. Test null, empty, whitespace, wrong-typed values, nonexistent property names, and invalid constraint metadata.
6. Class-level constraint depending on two fields: only full-bean `validate` has enough context.
7. HTTP cases: binding errors, Bean Validation errors, and `BindingResult` outcome; verify errors match the API contract.
8. Constraints added to beans over time: final tests must still cover whole-object validation so new rules are not missed.

## 10. How to Decide Which Method to Use

When writing code, ask yourself:

1. **Do I already have a complete bean instance and need to determine if it is valid?** → `validator.validate(bean, groups...)`.
2. **Do I only want to check the value of a property currently inside a bean?** → `validator.validateProperty(bean, "property", groups...)`.
3. **Have I not created / do I not want to modify the bean, and only need to test a new value against the field's annotations?** → `validator.validateValue(Bean.class, "property", candidate, groups...)`.
4. **Does the rule involve multiple fields or child beans?** → use whole-object `validate` (or an appropriate business validator); the two field-level APIs cannot verify linked rules.
5. **Is the context Spring MVC?** → prefer integrated validation via `@Valid`/`@Validated` and `BindingResult` handling on submit; use the three Jakarta methods directly when manual whole-object, per-field, or candidate checking is genuinely needed.

Core point: **`validate` sees the entire object and cascaded graph; `validateProperty` reads one current field; `validateValue` tests a hypothetical value from field metadata.** They share the constraint and group system, yet **differ in data scope and especially in cascading capability**. Picking the wrong scope can lead to concluding "valid" when only a single input box was checked.

### References

- Jakarta Validation 3.0, `Validator` interface: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/validator
- Jakarta Validation 3.0 Specification — object graph, property, value validation: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Hibernate Validator 8.x Reference Guide: https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/
- Spring Framework — Bean Validation integration: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC — Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
