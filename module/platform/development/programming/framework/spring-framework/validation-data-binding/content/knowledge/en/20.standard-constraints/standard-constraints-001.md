# @Null and @NotNull in Jakarta Bean Validation and Spring Framework

## 1. The Problem: "No Value" Is Different from "Empty Value"

In Spring applications, the two annotations `@Null` and `@NotNull` belong to the **built-in constraints** group of Jakarta Bean Validation. They are used when a data contract needs to specify that a field **must be absent at the Java `null` level**, or **must have a non-`null` reference**.

For example, with an order management API:

- When **creating** an order, the client must not decide the system-generated ID itself: `id` needs to be `null` before the server assigns an ID.
- When **updating** an order, the ID must be present to identify the resource: `id` needs to be non-`null`.
- The `name` field must have a value; if the requirement is "must contain actual content", `@NotNull` alone is not enough.

These two rules look simple, yet they directly affect DTO design, validation groups, conversion/binding, handling of empty strings, missing fields in JSON, and when data validation occurs.

## 2. Exact Definition

Jakarta Validation declares:

```java
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.NotNull;

public class Example {
    @Null
    private Long id;

    @NotNull
    private String name;
}
```

- **`@Null`:** the annotated element **must be `null`**.
- **`@NotNull`:** the annotated element **must not be `null`**.
- Both **accept any reference type that can be `null`**, such as `String`, `Long`, `LocalDate`, enum, object, `List`, and container element values.
- Neither checks content, length, positive numbers, format validity, or existence in a database.
- These annotations belong to **`jakarta.validation.constraints`**; in Spring Framework 6 / Spring Boot 3 projects, do not mistakenly use `javax.validation.constraints` from the previous generation.

Truth table for each annotation:

| Java Value | `@Null` | `@NotNull` | Remarks |
| --- | --- | --- | --- |
| `null` | Pass | Violation | The case that directly distinguishes them |
| `""` (empty string) | Violation | Pass | An empty string is a non-null object |
| `"   "` | Violation | Pass | Whitespace is not forbidden by `@NotNull` |
| `"hello"` | Violation | Pass | Content does not matter for these two constraints |
| `0`, `false` | Violation if boxed into an object | Pass | Number 0 / boolean false is still a value |
| `List.of()` (empty collection) | Violation | Pass | An empty collection is not `null` |
| `new Object()` | Violation | Pass | The object exists |

**Common pitfall:** at validation time, `@NotNull` does not care whether the user typed "reasonable" data; it only cares whether the value being validated equals `null`. Therefore, `@NotNull String name` still accepts `name=""` and `name="  "`.

### 2.1. Where Are the Annotations Placed?

In Jakarta Validation 3.x, `@Null` and `@NotNull` can be applied to fields, methods/getters, parameters, constructors, annotation types, and `TYPE_USE`. Typically:

```java
class CustomerForm {
    @NotNull
    private String email;                    // Field-level

    @NotNull
    public String getPhone() { return phone; } // Getter-level

    private String phone;
}
```

The example above only illustrates placement, not a complete class for MVC binding. In a real bean, choose **one consistent declaration placement** for each constraint; placing the exact same annotation on both the field and the getter can cause the same intent to be checked via two different constraint metadata entries.

With `TYPE_USE`, individual elements can be validated:

```java
class Shipment {
    @NotNull
    private List<@NotNull String> trackingCodes;
}
```

Here, `@NotNull` on `trackingCodes` requires the list itself not to be null; `List<@NotNull String>` requires every element in the list to be non-null when Bean Validation traverses elements of a supported container. The list is still allowed to be **empty**; to require at least one element, additionally use `@NotEmpty` or `@Size(min=1)`.

### 2.2. Do Not Place `@Null` on Primitives if Checking for Null

Primitive types `int`, `long`, and `boolean` cannot hold `null`. Therefore:

```java
@NotNull
private int age;
```

This annotation does not help detect when a user **did not pass an age** after binding has completed: `age` may be initialized by default to `0`, and `0` is not null. If you want to represent "not provided", use a wrapper type:

```java
@NotNull
private Integer age;
```

If `@Null` is placed on a primitive, an actual primitive value is always non-null; the constraint will fail when checked. Meanwhile, Bean Validation **does not replace the binding step**: missing fields, wrong-type values, and primitive defaults still depend on the object creation/binding mechanism.

## 3. Comparison with @NotEmpty, @NotBlank, and Content Checks

To determine the right constraint, distinguish between **null**, **empty**, **blank**, and **invalid format**.

| Constraint | `null` | `""` | `"  "` | `"abc"` | Used for |
| --- | --- | --- | --- | --- | --- |
| `@Null` | Pass | Fail | Fail | Fail | Requiring absence of a value |
| `@NotNull` | Fail | Pass | Pass | Pass | Requiring non-null |
| `@NotEmpty` | Fail | Fail | Pass | Pass | Non-empty string, collection, map, or array |
| `@NotBlank` | Fail | Fail | Fail | Pass | `CharSequence` must have at least one non-whitespace character |

In the table, `@NotEmpty` and `@NotBlank` are evaluated on `String` values; do not arbitrarily apply `@NotBlank` to `Integer` or `List`.

Example:

```java
class RegisterRequest {
    @NotNull
    private Long departmentId; // Has an ID; whether that ID exists in the DB is not yet known.

    @NotBlank
    private String username;   // Not null, empty, or whitespace-only.

    @NotEmpty
    private List<String> roles; // Has at least one element; element contents are checked separately.
}
```

`@NotBlank` is a better choice than `@NotNull` for a required name with content. For a collection whose elements must be non-null, combine `@NotEmpty List<@NotNull String>`. For a number that must be greater than 0, combine `@NotNull` with `@Positive` or `@Min(1)`. For an email, explicitly require non-emptiness in addition to `@Email` according to the application contract; do not assume `@Email` forbids `null` by itself.

**Do not write `@Null @NotNull` on the same field in the same validation group**: no value can simultaneously be null and non-null. Only use both when they serve **different groups** or clearly modeled business conditions.

## 4. Validation Groups: Same Field, Different Requirements on Create and Update

A very common case is a server-assigned ID:

```java
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.NotNull;

interface Create {}
interface Update {}

class OrderCommand {
    @Null(groups = Create.class)
    @NotNull(groups = Update.class)
    private Long id;

    // Getter/setter or constructor binding is defined in real code.
}
```

- On create: `validator.validate(command, Create.class)` requires `id == null`.
- On update: `validator.validate(command, Update.class)` requires `id != null`.
- If `validator.validate(command)` is called without passing a group, the `Default` group runs by default. **The two constraints above do not run in `Default`** because they are only declared for `Create` or `Update`.
- Jakarta's `@Valid` has no group attribute; to select groups in Spring MVC, use Spring's `@Validated(Create.class)` or `@Validated(Update.class)` in supported positions.

MVC controller example (integration snippet, not a standalone Java program):

```java
@PostMapping("/orders")
ResponseEntity<?> create(
        @Validated(Create.class) @RequestBody OrderCommand command,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("Invalid order");
    }
    // Authorize, apply business rules, then assign ID in the service.
    return ResponseEntity.ok().build();
}

@PutMapping("/orders/{id}")
ResponseEntity<?> update(
        @PathVariable Long id,
        @Validated(Update.class) @RequestBody OrderCommand command,
        BindingResult errors) {
    if (errors.hasErrors() || !id.equals(command.getId())) {
        return ResponseEntity.badRequest().body("Invalid order");
    }
    return ResponseEntity.ok().build();
}
```

You need to import the Spring MVC types, `@Validated`, `BindingResult`, `OrderCommand`, and `ResponseEntity`, as well as define the corresponding getters/binding for the DTO. The paths and ID checks here illustrate business rules; production code also needs to address authorization, missing resources, race conditions, and database state.

**Reliability note:** `@Null(groups=Create.class)` ensures the ID *after binding* is null; it **does not by itself prove the client did not send the field**. In JSON, a "missing field" and `"id": null` usually both produce a Java `null` value; both pass `@Null`. When strict policy forbids the client from sending a field, use a separate DTO without that property, control JSON mapping, or check input structure at the appropriate layer.

**Protect IDs from mass assignment:** do not rely on `@Null` in place of configuring which fields clients are allowed to write; use per-action DTOs, control property binder/mapper settings, and assign IDs on the server. Data that is valid regarding nullability is not necessarily valid regarding authorization.

## 5. Standalone Java 17+ Example: @Null, @NotNull, and Groups

The example uses **Jakarta Validation 3.x** and Hibernate Validator 8 as the provider. The program demonstrates: ID must be null on create and non-null on update; name and list must be non-null in the default group; the nested address is only validated when `@Valid` cascades.

### 5.1. Maven Configuration

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>null-constraints-demo</artifactId>
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

`hibernate-validator` brings in the Jakarta Validation API and required transitive dependencies. To run the example from the command line without requiring a Jakarta Expression Language library, the program uses Hibernate Validator's `ParameterMessageInterpolator`. This component is a provider detail, not a standard interface; applications using message templates with EL expressions should configure appropriate EL support.

### 5.2. Source Code `NullConstraintsDemo.java`

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.NotNull;

import org.hibernate.validator.HibernateValidator;
import org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator;

import java.util.List;
import java.util.Set;

public class NullConstraintsDemo {

    public interface Create {}
    public interface Update {}

    public static final class Address {
        @NotNull
        private final String city;

        public Address(String city) {
            this.city = city;
        }
    }

    public static final class OrderCommand {
        @Null(groups = Create.class)
        @NotNull(groups = Update.class)
        private final Long id;

        @NotNull
        private final String name;

        @NotNull
        private final List<String> tags;

        @Valid
        private final Address address;

        public OrderCommand(Long id, String name, List<String> tags, Address address) {
            this.id = id;
            this.name = name;
            this.tags = tags;
            this.address = address;
        }

        public Long getId() {
            return id;
        }
    }

    private static void print(
            String label, Set<? extends ConstraintViolation<?>> violations) {
        List<String> paths = violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .toList();
        System.out.println(label + " -> " + paths.size() + " " + paths);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory = Validation
                .byProvider(HibernateValidator.class)
                .configure()
                .messageInterpolator(new ParameterMessageInterpolator())
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            // id=null satisfies Create; name="" and tags=[] are both non-null.
            OrderCommand draft = new OrderCommand(
                    null, "", List.of(), new Address(null));

            // Object has an id, but three constraints in Default are violated.
            OrderCommand saved = new OrderCommand(
                    7L, null, null, new Address(null));

            print("draft Default", validator.validate(draft));
            print("draft Create", validator.validate(draft, Create.class));
            print("draft Update", validator.validate(draft, Update.class));

            print("saved Default", validator.validate(saved));
            print("saved Create", validator.validate(saved, Create.class));
            print("saved Update", validator.validate(saved, Update.class));

            print("draft.name", validator.validateProperty(draft, "name"));
            print("draft.address", validator.validateProperty(draft, "address"));

            print("candidate.name=null", validator.validateValue(
                    OrderCommand.class, "name", null));
            print("candidate.id=7 Create", validator.validateValue(
                    OrderCommand.class, "id", 7L, Create.class));
            print("candidate.id=null Update", validator.validateValue(
                    OrderCommand.class, "id", null, Update.class));

            System.out.println("savedId=" + saved.getId());
        }
    }
}
```

### 5.3. Compile and Run

JDK 17+ and Maven, executed from the directory containing the two files above.

Bash (Linux/macOS):

```bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
CP="$(cat classpath.txt)"
javac -encoding UTF-8 -cp "$CP" NullConstraintsDemo.java
java -cp ".:$CP" NullConstraintsDemo
```

PowerShell (Windows):

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$cp = (Get-Content -Raw classpath.txt).Trim()
javac -encoding UTF-8 -cp $cp NullConstraintsDemo.java
java -cp ".;$cp" NullConstraintsDemo
```

Expected stdout (ignoring provider or Maven logs/warnings if printed by the environment):

```text
draft Default -> 1 [address.city]
draft Create -> 0 []
draft Update -> 1 [id]
saved Default -> 3 [address.city, name, tags]
saved Create -> 1 [id]
saved Update -> 0 []
draft.name -> 0 []
draft.address -> 0 []
candidate.name=null -> 1 [name]
candidate.id=7 Create -> 1 [id]
candidate.id=null Update -> 1 [id]
savedId=7
```

Explanation:

- `draft Default` only violates `address.city`: `name=""` and `tags=[]` still satisfy `@NotNull`. `@Valid` on `address` enables cascading into `city`'s `@NotNull` check.
- `draft Create` passes because ID is null and only the `@Null(groups=Create.class)` constraint is selected; the `Default` group does not run automatically alongside it.
- `draft Update` fails because ID is null; `@NotNull(groups=Update.class)` is required.
- `saved Default` fails on `name`, `tags`, and `address.city`, but does not check the two ID constraints because they do not belong to the `Default` group.
- `saved Create` fails because ID already has a value; `saved Update` passes because ID is non-null.
- `validateProperty(draft, "address")` does not follow `@Valid` cascades, so it returns 0 when the `address` property has no direct constraint.
- `validateValue` tests a candidate value without mutating the instance; the three calls demonstrate null/non-null in the respective groups.
- `getPropertyPath()` is sorted before printing so stdout does not depend on the iteration order of `Set<ConstraintViolation<?>>`.

**Example scope:** this is plain Java Bean Validation. `OrderCommand` here is immutable to illustrate validating an already constructed object; it is not automatically a bindable DTO for every MVC request. When used in Spring MVC, configure constructor binding/deserialization appropriately or build a DTO with setters/builders as required.

## 6. Integrating with Spring Framework: When Are Constraints Enforced?

Placing annotations on fields **is not enough for every value assignment to automatically throw errors**. Spring must have a mechanism to trigger validation.

### 6.1. Spring MVC with Forms and JSON

For `@ModelAttribute` forms or `@RequestBody` payloads:

```java
@PostMapping("/customers")
public ResponseEntity<?> create(
        @Valid @RequestBody CustomerRequest request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(errors.getFieldErrors().stream()
                        .map(e -> e.getField() + ": " + e.getCode())
                        .toList());
    }

    return ResponseEntity.ok().build();
}
```

The snippet above is code inside a controller, using the appropriate `jakarta.validation.Valid` and Spring MVC imports. `CustomerRequest` is a DTO that must have the desired properties/annotations; the object must be successfully created by the JSON deserializer before Bean Validation can evaluate constraints.

- `@Valid` triggers object validation with the default group.
- `@Validated(Create.class)` from Spring selects a group when checking constraints specific to the Create operation.
- `BindingResult` is placed immediately after the corresponding parameter so the controller receives errors in cases supported by Spring; depending on the signature and validation type, errors may be raised as `MethodArgumentNotValidException` or `HandlerMethodValidationException`. Do not assume a single exception for every case.
- With `@RequestBody`, malformed JSON or invalid type conversion can be rejected **before Bean Validation**, and does not necessarily go through the same `BindingResult` as a `@NotNull` violation.

In a typical Spring Boot application, use the validation starter to include the API + provider (e.g., Hibernate Validator). If the classpath lacks a provider or no validator is registered for MVC, annotations may not be evaluated as expected.

### 6.2. Distinguishing "Property Required in Request" vs. "Non-Null After Binding"

These two requirements are **not equivalent**:

1. **`@NotNull` on a Java property:** checks that the final value is non-null when Bean Validation runs.
2. **Requiring the client to send a field in the wire format:** checks for the presence of the key/parameter in the HTTP request.

JSON examples:

```json
{}
```

and:

```json
{"name": null}
```

With a DTO having `String name` and the default deserializer without extra presence conditions, both cases typically produce `name == null`; `@NotNull` will reject both. If you need to **distinguish** a missing field from an explicit null (e.g., JSON Merge Patch), use an input model that supports presence state or a dedicated mapping mechanism.

Conversely, JSON:

```json
{"name": ""}
```

usually produces the Java value `""`; `@NotNull` allows it, whereas `@NotBlank` rejects it. In form binding, `StringTrimmerEditor`, a custom converter, or binder configuration can turn empty/blank strings into null; the `@NotNull` result afterward will then differ from when trimming was not applied. That is the effect of the **conversion/normalization** step preceding validation, not of the annotation itself.

### 6.3. Method Parameters and Response Validation

Bean Validation also supports parameter/return value constraints:

```java
// Method illustrating a contract; must go through a validation interceptor
// or the framework's method validation mechanism.
public String find(@NotNull Long id) {
    return "order-" + id;
}
```

Annotating a parameter with `@NotNull` **does not automatically guarantee** every internal Java call will be checked; it requires `ExecutableValidator` or appropriate method validation integration. Recent versions of Spring MVC support method validation on controller parameters; Spring services may require `@Validated`/proxying or other configuration depending on the stack and how methods are called.

For HTTP requests, `@RequestParam(required=true)` is a **parameter presence constraint** rule at the MVC layer; it is not a general replacement for `@NotNull` on a bean field. Do not use `@Null` to forbid users from sending a parameter; if the policy is "field absent from payload", use a DTO, field filtering, or payload presence checks.

### 6.4. In Services and Manual Validation

You can inject `jakarta.validation.Validator` directly:

```java
@Service
public class CustomerValidationService {
    private final jakarta.validation.Validator validator;

    public CustomerValidationService(
            jakarta.validation.Validator validator) {
        this.validator = validator;
    }

    public void check(CustomerRequest request) {
        var violations = validator.validate(request);
        if (!violations.isEmpty()) {
            throw new IllegalArgumentException("Invalid customer");
        }
    }
}
```

This is an integration snippet; `CustomerRequest` and `@Service` must be properly defined/imported. For production applications, translate `ConstraintViolation` into unified error messages/codes, and do not return raw invalid values if they contain sensitive data.

Two easily confused interfaces: `jakarta.validation.Validator` has `validate(object)` returning `Set<ConstraintViolation<T>>`; `org.springframework.validation.Validator` has `supports(...)` and `validate(object, Errors)`. Spring's `LocalValidatorFactoryBean` bridges Bean Validation integration.

## 7. Nested Objects and Collections: Nullability at Each Level

Consider:

```java
class Invoice {
    @NotNull
    @Valid
    private BillingAddress address;

    @NotNull
    private List<@NotNull String> tags;
}

class BillingAddress {
    @NotNull
    private String city;
}
```

There are three distinct conditions:

1. `address != null` thanks to `@NotNull`; `@Valid` enables checking `address.city` when `address` exists.
2. `tags != null` thanks to `@NotNull` placed on the collection.
3. Each element of `tags` must be non-null thanks to `List<@NotNull String>`, yet `tags=[]` **is still valid**.

Do not confuse `@NotNull` with `@Valid`: `@Valid` only triggers cascading and does not itself require the property to be non-null. If an optional relationship is left `null`, having cascade skip a nonexistent object makes sense; if the relationship is required, use `@NotNull @Valid` together.

When validating individual fields:

```java
validator.validate(invoice);                     // Evaluates the graph if @Valid.
validator.validateProperty(invoice, "address");  // Does not cascade into address.city.
```

`validateValue(Invoice.class, "address", ...)` also does not cascade. To conclude that the whole object is valid, use `validate` with the appropriate groups.

## 8. Groups, Error Messages, and Testing Expectations Properly

### 8.1. Constraint Attributes

Both `@Null` and `@NotNull` have three standard attributes:

- `message`: message template (default message keys are resolved by the provider via `ValidationMessages.properties`/supported bundles).
- `groups`: applicable groups; leaving it empty means belonging to the `Default` group.
- `payload`: extension metadata; the payload itself does not alter the null/non-null condition.

```java
@NotNull(
    message = "{order.customer.required}",
    groups = Create.class
)
private Long customerId;
```

This is an illustrative field in a bean with the `Create` group. When using a message key, a bundle containing the corresponding content is required. `ConstraintViolation#getMessage()` can depend on locale and provider; stable tests should assert against property path, template, or constraint metadata when needed.

### 8.2. What Should Tests Cover?

| Input / Action | Expectation |
| --- | --- |
| `@Null Long id` with `id=null` | Pass |
| `@Null Long id` with `id=0L` | Violation |
| `@NotNull String name` with `name=null` | Violation |
| `@NotNull String name` with `name=""` | Pass |
| `@NotNull String name` with `name="   "` | Pass |
| `@NotEmpty String name` with `name=""` | Violation |
| `@NotBlank String name` with `name="   "` | Violation |
| `@NotNull List<String> tags` with `tags=[]` | Pass |
| `List<@NotNull String>` with a null element | Violation on that element |
| `@Null(groups=Create.class)` invoked with Update group | Create constraint not applied |
| `@NotNull(groups=Update.class)` invoked with Create group | Update constraint not applied |
| `@NotNull @Valid Address address` with `address=null` | `@NotNull` violation |
| `@Valid Address address` with `address=null` | Cascade skipped; no violation just for being null |

Write tests for **valid beans**, **constraint-violating beans**, **correct groups**, and the **HTTP level**. In Spring MVC, verify how JSON/forms are constructed into objects by the deserializer and binder before asserting `@NotNull` messages.

### 8.3. When More Than @Null/@NotNull Is Needed

If business rules require:

- Name must have non-whitespace characters: `@NotBlank`.
- List must have at least one element: `@NotEmpty` or `@Size(min=1)`.
- Numeric value within a range: `@Min`, `@Max`, `@Positive`/`@Negative` combined with nullability when needed.
- String matching a regex: `@Pattern` and other constraints checking empty/null as appropriate.
- Future date: `@Future` or `@FutureOrPresent` along with `@NotNull` if input is required.
- ID must exist in the database: check in the service/repository or a custom validator with an appropriate policy; `@NotNull` only knows whether the ID is non-null.

Do not use `@NotNull` in place of a complex business rule and expect the provider to infer your intent.

## 9. Common Mistakes and Fixes

| Mistake | Actual Cause | Fix |
| --- | --- | --- |
| `@NotNull` does not catch empty strings | `"" != null` | Use `@NotBlank` or `@NotEmpty` as appropriate |
| `@NotNull` on `int` does not detect missing input | Primitives cannot be null; default value can be 0 | Use `Integer`; distinguish binding errors from constraints |
| `@Null` used to forbid clients from sending a field, yet `"id":null` still passes | The annotation checks the post-bind value, not key presence | Use a separate DTO / inspect payload structure |
| `@Null` and `@NotNull` in the same group on one field | Two contradictory conditions | Use separate Create/Update groups or separate DTOs |
| `@NotNull List<String>` still accepts an empty list | Nullability differs from collection size | Use `@NotEmpty` if the list needs elements |
| `@NotNull` placed on `Optional<T>`, yet `Optional.empty()` passes | The `Optional` object is non-null | Validate content using an appropriate representation; avoid Optional fields when unnecessary |
| Annotations exist, yet the API still accepts invalid data | Bean Validation is not triggered or provider is missing | Configure a provider and `@Valid`/`@Validated` at the right place |
| Wrong-type JSON error mistaken for a `@NotNull` error | Deserialization runs before validation | Handle `HttpMessageConverter`/Jackson errors and validation errors separately |
| Only placing `@Valid` on a nested field and expecting null to be forbidden | Cascading does not imply `@NotNull` | Combine `@NotNull @Valid` if required |
| Calling validator with Create group, yet Default fields do not run | Only the selected group (and related rules) are evaluated | Select groups accurately; use sequences/inheritance if needed |
| Using `getMessage()` as a long-term logic key | Messages can be translated by locale | Use constraint code / message template / field to classify |
| Using `@NotNull` to check permission to update an ID | Nullability cannot verify access rights | Check permissions and ownership in the service |
| Placing annotations on both field and getter and seeing duplicate errors | Constraint metadata is declared twice | Choose one consistent constraint placement strategy |
| Using `javax.validation` package on Spring 6 | Different Jakarta namespace | Use `jakarta.validation` and compatible providers |

## 10. Checklist for Choosing Annotations When Designing DTOs

When defining a field, determine in order:

1. **Must the value be absent in this operation?** Use `@Null` if you need to check null after binding; to **forbid sending the property**, design an appropriate input contract/DTO.
2. **Must the value be present?** Use `@NotNull` with a reference type; if it is a string requiring content, consider `@NotBlank`.
3. **Can a collection be empty?** If not, use `@NotEmpty` or `@Size(min=1)`.
4. **Is a nested relationship required and in need of deep validation?** Use `@NotNull @Valid` if both are required.
5. **Do Create and Update have opposite nullability?** Choose per-action DTOs or validation groups with a clear policy; do not attach contradictory constraints to the same group.
6. **Does data come from HTTP/JSON?** Check mapping, missing fields, explicit null, empty values, and post-normalization state before concluding whether a constraint works properly.
7. **Are there security or business rules?** Enforce them independently at the appropriate layer; Bean Validation is part of validity checking, not an authorization mechanism.

**Remember:** `@Null` requires the Java value to be `null`; `@NotNull` requires the Java value to be non-`null`. They do not check string content, do not reliably detect whether a client sent a key, do not replace conversion/binding, and do not replace business rules. Choose annotations based on the actual data contract, and combine other constraints and appropriate groups before wiring into Spring controllers.

### References

- Jakarta Validation API 3.1 — `@Null`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/Null.html
- Jakarta Validation API 3.1 — `@NotNull`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/NotNull.html
- Jakarta Bean Validation 3.0 specification — built-in constraints and groups: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Hibernate Validator 8 Reference Guide: https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/
- Spring Framework — Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC — Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring MVC — Validation configuration: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html
