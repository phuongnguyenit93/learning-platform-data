# `message`, `groups`, and `payload` of Custom Constraints in Jakarta Bean Validation and Spring

## 1. Objectives and big picture

When writing a custom constraint, you typically create **an annotation** such as `@AllowedRegion` and **a validation class** implementing `ConstraintValidator`. Per Jakarta Validation, **every constraint annotation** must have all three configuration elements with the prescribed types and default values:

```java
String message() default "{demo.AllowedRegion.message}";
Class<?>[] groups() default {};
Class<? extends Payload>[] payload() default {};
```

They answer three distinct questions:

| Attribute | Role | Who uses it? |
| --- | --- | --- |
| `message` | Message template when the constraint is violated | Bean Validation's message interpolator and the presentation layer |
| `groups` | Set of groups the constraint belongs to; decides **when** the constraint is selected | Validation engine when calling `validate(bean, groups...)` or Spring `@Validated` |
| `payload` | Extension metadata attached to the **constraint declaration** | Integration clients, code reading `ConstraintDescriptor`; does not affect pass/fail by default |

Meanwhile, **pass/fail logic** lives in `ConstraintValidator.isValid(...)`, not in these three attributes. A `false` return from `isValid` produces a `ConstraintViolation` with the corresponding message and descriptor; groups determine whether the constraint runs in that validation pass.

Important point: **an annotation is only metadata**. An object carrying annotations is not automatically validated when calling `new`, a constructor, or a setter. There must be a validation pass such as `jakarta.validation.Validator.validate(...)`, Spring MVC `@Valid`/`@Validated` at a supported entry point, or configured service method validation.

## 2. Defining a valid custom constraint annotation

Example annotation validating that a region code starts with a configured prefix:

```java
package demo.validation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = AllowedRegionValidator.class)
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
public @interface AllowedRegion {

    String message() default "{demo.validation.AllowedRegion.message}";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};

    String prefix() default "VN-";
}
```

This is the code for **`src/main/java/demo/validation/AllowedRegion.java`**; it requires the `AllowedRegionValidator` class in the matching package shown next. Notable components:

1. `@Constraint(validatedBy = AllowedRegionValidator.class)` marks the annotation as a Bean Validation constraint and registers the implementation.
2. `@Retention(RUNTIME)` ensures the provider can read the annotation at runtime.
3. `@Target` restricts valid Java placement sites: field, getter/method, parameter, type argument, or another annotation for composition. Declare only the `ElementType` values that are genuinely meaningful for your constraint.
4. `@Documented` includes the annotation in the Javadoc of annotated elements; helpful, though not a replacement for `@Constraint`.
5. `message`, `groups`, and `payload` have **mandatory** signatures per the specification.
6. `prefix` is a constraint-specific parameter; it is not a mandatory element defined by Jakarta. The value of `prefix` can be used in the validator and interpolated into the message using `{prefix}`.

You must not rename `message` to `errorMessage` or `payload` to `severity` and omit the three standard elements. The provider looks for the exact signatures required by the specification.

### Constraint handler class

```java
package demo.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class AllowedRegionValidator
        implements ConstraintValidator<AllowedRegion, CharSequence> {

    private String prefix;

    @Override
    public void initialize(AllowedRegion annotation) {
        prefix = annotation.prefix();
    }

    @Override
    public boolean isValid(
            CharSequence value,
            ConstraintValidatorContext context) {
        return value == null || value.toString().startsWith(prefix);
    }
}
```

Save to **`src/main/java/demo/validation/AllowedRegionValidator.java`**. The provider:

- Finds a suitable validator for the Java type at the constraint site. `String` implements `CharSequence`, so it is supported.
- Calls `initialize(annotation)` to pass immutable parameters of this **constraint declaration**.
- Calls `isValid(value, context)` to evaluate the value. Here `null` is accepted per the format-checking constraint convention; to require a value, combine with `@NotNull` or `@NotBlank`.
- If `isValid` returns `false`, uses the constraint's `message` to build a violation.

**Avoid three mistakes:** do not store per-request data in shared mutable validator fields; do not throw a business exception just to signal "invalid value" when returning `false` suffices; do not assume `payload` is automatically passed as an argument to `isValid`.

## 3. `message`: a message template, not the validation logic itself

### Required type and default value

Standard definition:

```java
String message() default "{demo.validation.AllowedRegion.message}";
```

The value is a **message template**, which can be a literal string or a key enclosed in curly braces for resource bundle lookup.

Example on a model:

```java
@AllowedRegion(prefix = "VN-")
private String code1;

@AllowedRegion(
    prefix = "EU-",
    message = "Code must start with {prefix}"
)
private String code2;
```

`code1` uses the default template on the annotation; `code2` overrides the message at the **constraint usage site**. Both still use the same `AllowedRegionValidator` implementation, differing only in configuration/violation message.

### Resource bundle for messages

Create **`src/main/resources/ValidationMessages.properties`**:

```properties
demo.validation.AllowedRegion.message=Code must start with {prefix}
```

When `code1="US-123"`, the provider typically:

1. Takes the message template `{demo.validation.AllowedRegion.message}`.
2. Looks up the key in `ValidationMessages.properties` on the application classpath.
3. Obtains the string `Code must start with {prefix}`.
4. Replaces `{prefix}` with the annotation attribute value `"VN-"`.
5. Produces the final message: `Code must start with VN-`.

If `code2="US-456"`, the overridden message can interpolate to `Code must start with EU-`.

It is good practice to name keys by convention using the **fully qualified constraint annotation name + `.message`**, for example `demo.validation.AllowedRegion.message`. When moving packages or renaming the annotation, update the corresponding key if following this convention.

### `getMessageTemplate()` differs from `getMessage()`

Given a `ConstraintViolation<?> v`:

```java
String template = v.getMessageTemplate();
String resolved = v.getMessage();
```

- `template` holds the **message template** of the constraint declaration, e.g. `{demo.validation.AllowedRegion.message}`.
- `resolved` is the interpolated string, e.g. `Code must start with VN-`.

This distinction lets you return a user-facing message while keeping the key/template for logging, error categorization, or API responses with a dedicated `code`.

### Messages and internationalization

Jakarta Validation supports locale-based message resolution and `MessageInterpolator`; providers typically load `ValidationMessages.properties`, `ValidationMessages_vi.properties`, `ValidationMessages_en.properties` per bundle rules. When a deterministic locale is needed in a request or test, check how the provider and Spring actually resolve the locale. Do not assume every application setup automatically switches to Vietnamese just because the HTTP header contains `Accept-Language: vi`; the locale/message interpolator configuration flow must be compatible.

With Spring, `LocalValidatorFactoryBean` can use `setValidationMessageSource(MessageSource)` to integrate constraint messages with Spring's message system in supported configurations/providers. Do not call both this setter and `setMessageInterpolator(...)` in conflicting ways. Also distinguish:

- **Provider interpolation:** produces `ConstraintViolation.getMessage()` from `message`.
- **Spring `MessageSource` / `BindingResult` error codes:** allow screens/APIs to determine messages and error codes per field or object.

That is, `message` is part of the Bean Validation contract; HTTP responses or UI mapping belong to a separate layer.

### Parameters in messages and EL

`{prefix}` is a reference to an **annotation attribute**, similar to standard examples with `{min}` and `{max}` on `@Size`. Some providers support Expression Language syntax `\${...}` and dynamic interpolated parameters; whether EL is allowed—especially in **custom violation messages**—depends on the provider and security safeguards. Do not concatenate untrusted user input directly into message templates so the provider evaluates expressions. Prefer fixed keys/attributes and proper escaping when rendering messages in HTML.

## 4. `groups`: selecting constraints for a validation scenario

### Mandatory signature

```java
Class<?>[] groups() default {};
```

An empty array in the **annotation definition** means: when the user **omits `groups`** on a constraint declaration, that constraint belongs to `jakarta.validation.groups.Default`.

However:

```java
@AllowedRegion(prefix = "VN-")
private String generalCode;
```

does not mean "this constraint belongs to all groups". It belongs to **Default**, and will not run automatically when only a custom group with no inheritance relationship to Default is requested.

### Declaring marker groups

```java
public interface OnCreate {}
public interface OnUpdate {}
```

Groups are Java interfaces; they are not Spring beans and do not need `@Component`. At the constraint site:

```java
@AllowedRegion(prefix = "VN-", groups = OnCreate.class)
private String primaryCode;

@AllowedRegion(prefix = "EU-", groups = OnUpdate.class)
private String backupCode;
```

If an object carries these two fields:

```java
validator.validate(object, OnCreate.class); // Selects OnCreate only.
validator.validate(object, OnUpdate.class); // Selects OnUpdate only.
validator.validate(object);                 // Default only, unless configured otherwise.
```

The first two calls are **snippets**, assuming `validator` is a `jakarta.validation.Validator`, `object` has those fields, and the classes/interfaces are properly declared.

A constraint can belong to multiple groups:

```java
@AllowedRegion(
    prefix = "VN-",
    groups = {OnCreate.class, OnUpdate.class}
)
private String serviceCode;
```

When OnCreate or OnUpdate is requested, the constraint on `serviceCode` can be evaluated. This is a mechanism to **select a subset of constraints**; it does not mean the property is mutated or validation runs automatically upon field assignment.

### Selecting multiple groups in one pass

```java
validator.validate(object, Default.class, OnCreate.class);
```

This is an **explicit** call requesting both Default and OnCreate constraints. Do not assume the provider must execute Default before OnCreate; with ordinary groups, check ordering is not guaranteed. If you need **group-level ordering and short-circuiting**, use `@GroupSequence`, not the argument order of `validate(...)`.

### Group inheritance

```java
public interface FullCreate extends OnCreate, Default {}
```

`validator.validate(object, FullCreate.class)` selects constraints of `FullCreate` and its parent groups `OnCreate` and `Default`. The reverse does not hold: calling Default does not automatically select constraints belonging solely to FullCreate or OnCreate.

When designing groups, name them after the **action being validated** (`OnCreate`, `OnUpdate`, `PublishChecks`) rather than creating a separate interface per field. An overly deep group hierarchy is hard to read and makes it easy for rules to be skipped because callers pick the wrong group.

### `@GroupSequence` is not `groups`

```java
@GroupSequence({Default.class, OnCreate.class})
public interface OrderedCreate {}
```

`validator.validate(object, OrderedCreate.class)` runs Default first; if Default has violations, the OnCreate group is not executed in the sequence. Do not use a sequence interface directly as a group inside a constraint's `groups` attribute. A sequence has cycle-avoidance rules and special rules when redefining Default at the class level.

For normal validation, `groups` answers **which rules are selected**; `GroupSequence` answers **in what order they are executed**.

## 5. `payload`: extension metadata, without changing `isValid` results

### Mandatory signature

```java
Class<? extends Payload>[] payload() default {};
```

`Payload` is the marker interface `jakarta.validation.Payload`. Applications define custom metadata types via interfaces/classes implementing `Payload`.

Example classifying severity levels:

```java
public final class Severity {
    private Severity() {}

    public interface Info extends Payload {}
    public interface Warning extends Payload {}
    public interface Error extends Payload {}
}
```

This is an illustrative class, requiring import of `jakarta.validation.Payload`. Attached to a constraint declaration:

```java
@AllowedRegion(
    prefix = "VN-",
    groups = OnCreate.class,
    payload = Severity.Error.class
)
private String primaryCode;
```

**Syntax note:** `payload` takes **classes**, e.g. `Severity.Error.class`, not `new Severity.Error()` and not a string like `"ERROR"`. Multiple payload markers can be passed via `payload = {Severity.Warning.class, Severity.Error.class}`.

### Reading payload via `ConstraintDescriptor`

A violation `v` carries metadata:

```java
Set<Class<? extends Payload>> payloadTypes =
        v.getConstraintDescriptor().getPayload();

boolean isError = payloadTypes.contains(Severity.Error.class);
```

This is a snippet assuming imports, markers, and `v` are already available. Other information from the descriptor:

```java
String annotationName =
        v.getConstraintDescriptor()
         .getAnnotation()
         .annotationType()
         .getSimpleName();

Object configuredPrefix =
        v.getConstraintDescriptor()
         .getAttributes()
         .get("prefix");
```

`ConstraintDescriptor.getAttributes()` provides the annotation element metadata at the declaration; `getPayload()` returns **the set of payload classes**, not a payload object that varies per validation pass.

Purposes for which clients can use payload: deciding UI severity; flagging advisory errors; categorizing for logging/auditing; choosing downstream handling according to a designed policy. However, **standard Bean Validation does not automatically interpret `Severity.Error` as HTTP 400, `Severity.Info` as a warning, or ignore violations**.

### Distinguishing payload metadata from business behavior

| Case | Happens automatically because of `payload`? |
| --- | --- |
| `Severity.Error` causes `isValid()` to run an extra time | No |
| `Severity.Info` turns a `false` into `true` | No |
| `Severity.Warning` removes the error from `Validator.validate()` | No |
| `Severity.Error` produces HTTP 422 in Spring MVC | No |
| Client reads severity via `getPayload()` and applies custom policy | Yes, **if the application writes that code** |
| Provider returns the declaration's payload in the descriptor | Yes, per the metadata API |

Even if an application labels an error a "warning", it is still a `ConstraintViolation` when the validator returns `false`. If you want non-blocking warnings that do not reject a request, you must design a separate mechanism or use different logic; do **not** rely on payload expecting Hibernate Validator to alter results automatically.

### Special standard payloads: `Unwrapping.Unwrap` and `Unwrapping.Skip`

An exception to "metadata handled solely by clients" is the two payloads defined by Jakarta Validation to control **value unwrapping**:

```java
@NotBlank(payload = Unwrapping.Unwrap.class)
private Optional<String> code;
```

This snippet requires importing `java.util.Optional`, `jakarta.validation.constraints.NotBlank`, and `jakarta.validation.valueextraction.Unwrapping`; with a suitable extractor, `Unwrap` requests validating the element inside the container. `Unwrapping.Skip` forces skipping unwrapping in cases where implicit unwrapping applies.

Do not attach this kind of payload as an ordinary severity marker: it has standard semantics understood by the validation engine. Also do not confuse a constraint annotation's `payload()` with Hibernate Validator's proprietary "dynamic payload" features or with Spring `Payload` classes in other libraries. They are not the same contract.

## 6. Distinguishing the three declared values from what the provider executes

Suppose a DTO has:

```java
@NotBlank(message = "name is required")
private String name;

@AllowedRegion(
    prefix = "VN-",
    groups = OnCreate.class,
    payload = Severity.Error.class
)
private String primaryCode;

@AllowedRegion(
    prefix = "EU-",
    message = "backup needs {prefix}",
    groups = OnUpdate.class,
    payload = Severity.Info.class
)
private String backupCode;
```

Suppose all three values are invalid:

| Requested group | Selected constraint | Expected message |
| --- | --- | --- |
| `Default` | `@NotBlank` on `name` | `name is required` |
| `OnCreate` | `@AllowedRegion` on `primaryCode` | From bundle for prefix `VN-` |
| `OnUpdate` | `@AllowedRegion` on `backupCode` | `backup needs EU-` |
| `Default, OnCreate` | Both `name` and `primaryCode` | Two independent violations |
| `FullCreate extends Default, OnCreate` | Same two constraints above | Two independent violations |

Because `payload` is only metadata, attaching `Severity.Info` to a declaration does not exclude it from the violation set when OnUpdate is validated.

## 7. Complete runnable example with Java 17 and Spring Boot

The example uses **a single Java source file** for the annotation, validator, model, and runner for quick copy-and-run experimentation, plus a `ValidationMessages.properties` to test real message interpolation. Outside a learning example, production projects should separate annotation, validator, and DTO into separate classes.

Structure:

```text
custom-constraint-demo/
├── pom.xml
└── src/main/
    ├── java/demo/ConstraintMetadataDemo.java
    └── resources/ValidationMessages.properties
```

### 7.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>custom-constraint-demo</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-validation` provides Jakarta Validation integration and a compatible Hibernate Validator provider via Spring Boot's dependency management. This example does not need Spring MVC; `ApplicationRunner` calls `jakarta.validation.Validator` directly.

### 7.2. `src/main/resources/ValidationMessages.properties`

```properties
demo.AllowedRegion.message=code must start with {prefix}
```

Keep the key and lowercase text as in the example so the output lines are easy to verify. The key here is chosen **explicitly**; if moving the annotation to another package/class, you can switch it to the annotation FQN convention and update the resource accordingly.

### 7.3. `src/main/java/demo/ConstraintMetadataDemo.java`

```java
package demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Payload;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.groups.Default;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ConstraintMetadataDemo {

    public interface OnCreate {}
    public interface OnUpdate {}

    public interface FullCreate extends Default, OnCreate {}

    public static final class Severity {
        private Severity() {}

        public interface Info extends Payload {}
        public interface Error extends Payload {}
    }

    @Documented
    @Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.ANNOTATION_TYPE,
        ElementType.TYPE_USE
    })
    @Retention(RetentionPolicy.RUNTIME)
    @Constraint(validatedBy = AllowedRegionValidator.class)
    public @interface AllowedRegion {
        String message() default "{demo.AllowedRegion.message}";
        Class<?>[] groups() default {};
        Class<? extends Payload>[] payload() default {};
        String prefix() default "VN-";
    }

    public static final class AllowedRegionValidator
            implements ConstraintValidator<AllowedRegion, CharSequence> {

        private String prefix;

        @Override
        public void initialize(AllowedRegion annotation) {
            prefix = annotation.prefix();
        }

        @Override
        public boolean isValid(
                CharSequence value, ConstraintValidatorContext context) {
            return value == null || value.toString().startsWith(prefix);
        }
    }

    public static final class Registration {
        @NotBlank(message = "name required")
        private final String name;

        @AllowedRegion(
            prefix = "VN-",
            groups = OnCreate.class,
            payload = Severity.Error.class
        )
        private final String primaryCode;

        @AllowedRegion(
            prefix = "EU-",
            groups = OnUpdate.class,
            message = "backup needs {prefix}",
            payload = Severity.Info.class
        )
        private final String backupCode;

        public Registration(
                String name, String primaryCode, String backupCode) {
            this.name = name;
            this.primaryCode = primaryCode;
            this.backupCode = backupCode;
        }
    }

    public static void main(String[] args) {
        SpringApplication.run(ConstraintMetadataDemo.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(Validator validator) {
        return args -> {
            Registration invalid =
                    new Registration("", "US-101", "US-202");

            show("Default", validator, invalid, Default.class);
            show("Create", validator, invalid, OnCreate.class);
            show("Update", validator, invalid, OnUpdate.class);
            show("FullCreate", validator, invalid, FullCreate.class);

            ConstraintViolation<Registration> createViolation =
                    validator.validate(invalid, OnCreate.class)
                             .iterator()
                             .next();

            System.out.println("Message template: "
                    + createViolation.getMessageTemplate());

            System.out.println("Prefix attribute: "
                    + createViolation.getConstraintDescriptor()
                                     .getAttributes()
                                     .get("prefix"));

            System.out.println("Severity Error: "
                    + createViolation.getConstraintDescriptor()
                                     .getPayload()
                                     .contains(Severity.Error.class));

            System.out.println("Severity Info: "
                    + createViolation.getConstraintDescriptor()
                                     .getPayload()
                                     .contains(Severity.Info.class));
        };
    }

    static void show(
            String label, Validator validator,
            Registration value, Class<?>... groups) {

        Set<ConstraintViolation<Registration>> violations =
                validator.validate(value, groups);

        String details = violations.stream()
                .map(v -> v.getPropertyPath().toString()
                        + "=" + v.getMessage())
                .sorted()
                .collect(Collectors.joining("; "));

        System.out.println(label + " (" + violations.size() + "): "
                + (details.isEmpty() ? "OK" : details));
    }
}
```

The classes/annotations are declared **`static` inside the public class** and all imports are complete, so the example only needs one Java file. `AllowedRegionValidator` has an implicit public no-arg constructor and can be instantiated by the provider/Spring.

### 7.4. Running and output

With JDK 17+ and Maven installed, run:

```bash
mvn spring-boot:run
```

Alongside standard Spring Boot startup logs, the program prints the following lines:

```text
Default (1): name=name required
Create (1): primaryCode=code must start with VN-
Update (1): backupCode=backup needs EU-
FullCreate (2): name=name required; primaryCode=code must start with VN-
Message template: {demo.AllowedRegion.message}
Prefix attribute: VN-
Severity Error: true
Severity Info: false
```

**Why?**

- `name=""` fails `@NotBlank`, but that constraint belongs only to Default, so the `Default` result has 1 error.
- `primaryCode="US-101"` does not start with `VN-`. It belongs to group OnCreate, so the `Create` result has 1 error. The default message is interpolated via `ValidationMessages.properties`.
- `backupCode="US-202"` does not start with `EU-`. It belongs to group OnUpdate; the annotation overrides `message = "backup needs {prefix}"`, so the `Update` result uses the different message.
- `FullCreate extends Default, OnCreate` selects both Default and OnCreate constraints, producing 2 errors. Results are sorted so display is deterministic even though `Set<ConstraintViolation>` guarantees no ordering.
- `getMessageTemplate()` returns the raw template declared on `primaryCode`'s constraint; `getMessage()` is already interpolated into the actual message.
- `getAttributes().get("prefix")` retrieves the annotation's custom `"VN-"` parameter.
- `getPayload()` contains the `Severity.Error.class` marker recorded by the declaration on `primaryCode`, and does not contain `Severity.Info.class`.

**If `primaryCode` is changed to `"VN-101"`**, Create has no violations. When there are no violations, the code must not call `iterator().next()` on an empty set; in production, always check `violations.isEmpty()` before reading an element. Violation sets also have no stable ordering; using `next()` is safe here only because the OnCreate group produces exactly one violation for the sample input.

### 7.5. Key takeaways from the program

A single `@AllowedRegion` annotation can be reused multiple times with different `prefix`, `message`, `groups`, and `payload` values. The `isValid` implementation does not need to know the current group or severity. The provider selects **the declarations participating in the validation pass**, creates the matching validator, and attaches the declaration's descriptor to the violation on failure.

Note that the demo illustrates behavior compliant with Jakarta Validation/Spring Boot and can be run with the commands above; when adapting to another project, verify actual versions, dependencies, classpath, and application configuration.

## 8. `groups` in Spring MVC: `@Valid` vs `@Validated`

An illustrative REST method:

```java
@PostMapping("/registrations")
public ResponseEntity<?> register(
        @Validated(OnCreate.class)
        @RequestBody RegistrationRequest request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body(
                errors.getFieldErrors().stream()
                      .map(e -> e.getField() + ": "
                              + e.getDefaultMessage())
                      .toList());
    }
    return ResponseEntity.ok().build();
}
```

This is an **illustrative method in Spring MVC**, not a standalone class. It requires `@RestController`, imports for `org.springframework.validation.annotation.Validated`, `org.springframework.validation.BindingResult`, `@PostMapping`, `@RequestBody`, `ResponseEntity`, a constrained DTO, and the `OnCreate` group.

At supported Spring MVC entry points, `@Validated(OnCreate.class)` requests validating the DTO with **OnCreate**. If the DTO has constraints belonging to Default but not OnCreate, they are **not selected automatically**, unless the requested group extends Default or another special rule applies.

If you only write:

```java
public ResponseEntity<?> register(
        @Valid @RequestBody RegistrationRequest request) {
    // ...
}
```

then `@Valid` normally requests validation of the **Default group**, which is not equivalent to `@Validated(OnCreate.class)`. `BindingResult` must appear immediately after the target argument in supported signatures; otherwise, Spring MVC typically turns object argument validation errors into an exception (e.g. `MethodArgumentNotValidException`). Method-level validation with constraints directly on parameters may have a different mechanism/exception depending on the Spring version.

**Do not expect Spring MVC to infer groups from the HTTP method.** POST does not automatically select `OnCreate`, nor does PUT select `OnUpdate`. You must define the contract and appropriate annotation/validator call.

### Returning payload in JSON?

Spring `BindingResult` typically carries `FieldError`, error codes, and messages adapted from Bean Validation. Do not assume Spring automatically converts `payload = Severity.Error.class` into a `severity` field in the response.

If an API needs severity, build an explicit mapping mechanism from `ConstraintViolation.getConstraintDescriptor().getPayload()` or from your application's own error contract. In particular, do not use arbitrary payloads to decide the request-wide HTTP status when a single response can contain multiple violations of different severities without a defined precedence policy.

## 9. `groups` with Spring service method validation

There are two perspectives:

- **Validate objects directly:** inject `jakarta.validation.Validator`, call `validator.validate(bean, OnCreate.class)`. Explicit and easy to test.
- **Validate method parameters:** use Spring's method-validation infrastructure on Spring-managed beans, usually with type-level `@Validated` and `MethodValidationPostProcessor`/auto-configuration. The interceptor asks the provider to check constraints according to the configured group.

Illustrative service example:

```java
@Service
@Validated(OnCreate.class)
public class RegistrationService {
    public void register(@Valid RegistrationRequest request) {
        // ...
    }
}
```

This snippet requires Spring and Jakarta imports along with the related classes. It does not run automatically when calling `new RegistrationService()`, when Spring method validation is not enabled, or when self-invocation `this.register(...)` bypasses the proxy. Do not treat annotations as the sole safeguard protecting business logic across all code paths.

At service boundaries, explicit validation can be preferable to control clearly which groups apply, especially for batch jobs, message consumers, scheduled tasks, or code not routed through MVC.

## 10. `payload` and severity classification in testing workflows

Suppose an application uses two markers:

```java
public interface Warning extends Payload {}
public interface Error extends Payload {}
```

A field with `@AllowedRegion(..., payload=Warning.class)` given invalid data **still** produces a `ConstraintViolation`. Client-side handling code can read:

```java
for (ConstraintViolation<?> v : violations) {
    var p = v.getConstraintDescriptor().getPayload();
    String level = p.contains(Error.class) ? "ERROR"
                 : p.contains(Warning.class) ? "WARNING"
                 : "UNSPECIFIED";
    System.out.println(level + ": " + v.getMessage());
}
```

This is an illustrative snippet based on declared `violations`, `Error`, `Warning`, and proper imports. Severity selection logic resides **in the application**, not performed for you by the Jakarta Validation API.

For auditing/logging, log only necessary data; avoid printing `getInvalidValue()` directly since it may contain tokens, emails, financial info, or secrets. Severity is not a guarantee that an invalid value can be processed safely; acceptance/rejection policies must be defined separately.

To test that payload is not lost, assert on the descriptor:

```java
assertTrue(violation.getConstraintDescriptor()
        .getPayload().contains(Severity.Error.class));
```

This is a JUnit snippet, requiring `assertTrue` and a valid `violation`. If you only want to verify metadata without creating invalid data, use the metadata API `Validator.getConstraintsForClass(...)` to find the `PropertyDescriptor` and its `ConstraintDescriptor`s, then read `getPayload()` and `getAttributes()`.

## 11. Customizing messages directly inside `ConstraintValidatorContext`

`message` on the annotation is the **default template**. When a failure case has details that cannot be expressed using `prefix` alone, the implementation can build a custom violation:

```java
@Override
public boolean isValid(
        String value, ConstraintValidatorContext context) {

    if (value == null || value.startsWith(prefix)) {
        return true;
    }

    context.disableDefaultConstraintViolation();
    context.buildConstraintViolationWithTemplate(
                "Invalid region prefix")
           .addConstraintViolation();

    return false;
}
```

This is an **illustrative method fragment** inside a `ConstraintValidator<AllowedRegion, String>` class with an initialized `prefix` field. It replaces the default message with a custom one. If you call `disableDefaultConstraintViolation()`, you must build at least one custom violation before returning `false`; otherwise, the provider may throw `ValidationException` because no violation is described.

You can add a property node via `addPropertyNode("field")` for a **class-level constraint** to attach the error to a specific field. That is a separate step from changing `message`, and you must ensure the property path is accurate rather than inventing nonexistent fields.

Hibernate Validator offers extra APIs such as `HibernateConstraintValidatorContext.addMessageParameter(...)`; that is a provider extension, not always portable across Jakarta Validation providers. For message templates derived from untrusted input, watch out for EL injection; by default some providers restrict EL in custom violations for safety.

## 12. When should you create a `message` key instead of a literal?

| Context | Suitable approach | Reason |
| --- | --- | --- |
| Multilingual system | `message() default "{app.constraint.SomeRule.message}"` | Routes through locale-specific resource bundles |
| Library reused across projects | Key by annotation FQN + `.message` | Fewer collisions and easy to override |
| Short internal demo | Literal such as `"must start with {prefix}"` | Easy to read without extra resources |
| One use case needing a different message | Override `message = "..." ` at the constraint site | Avoids creating a new annotation |
| Client needing stable error codes | Design a dedicated `errorCode` or constraint mapping | Locale-translated messages should not act as sole error codes |
| Testing messages | Pass/fix locale or use intentional fixed strings | Avoids test failures from locale/bundle changes |

Error messages should describe the **violation** without exposing sensitive data. If a rule takes parameters (min/max/prefix), use controlled interpolated parameters instead of duplicating dozens of similar messages.

## 13. Metadata API: reading `message`, `groups`, and `payload` without validating

`Validator` has a metadata API to inspect constraint declarations. Example with the `Registration` class in the demo:

```java
var beanDescriptor =
        validator.getConstraintsForClass(Registration.class);

var propertyDescriptor =
        beanDescriptor.getConstraintsForProperty("primaryCode");

for (var descriptor : propertyDescriptor.getConstraintDescriptors()) {
    System.out.println(descriptor.getMessageTemplate());
    System.out.println(descriptor.getGroups());
    System.out.println(descriptor.getPayload());
    System.out.println(descriptor.getAttributes().get("prefix"));
}
```

This snippet assumes an initialized `validator`. In production, null-check `propertyDescriptor` if a property might have no constraints. `ConstraintDescriptor` lets you inspect groups, payloads, special attributes, the actual annotation, and constraint metadata.

**A technical distinction:** reading descriptors does not execute `isValid` and does not create `ConstraintViolation`s. The Metadata API is useful for documenting rules, generating UI hints from constraints, or checking conventions, but does not replace actual data validation.

For a custom constraint, `getAttributes()` contains `prefix`, `message`, `groups`, `payload`, and custom annotation elements per API rules. For `ConstraintDescriptor.getGroups()`, membership in `Default` per the contract may be reflected even when `groups()` on the annotation definition defaults to an empty array. Do not infer that `groups() default {}` means the constraint belongs to "no group at all".

## 14. Why must the mandatory signatures not be changed?

According to the Jakarta Validation specification, `message`, `groups`, and `payload` are **reserved names** with standard types/defaults; `validationAppliesTo` is an additional reserved name for constraints that are both generic and cross-parameter. Annotation element names starting with `valid` are also prohibited.

Declaration error table:

| Declaration | Issue |
| --- | --- |
| Missing `message()` | Missing mandatory element |
| `int message() default 0;` | Wrong type; must be `String` |
| `Class<?> groups() default Default.class;` | Wrong type; must be an array `Class<?>[]` |
| `Class<?>[] groups() default {OnCreate.class};` | Wrong group element default; standard requires `{}` |
| `Class<? extends Payload>[] payload() default {Severity.Error.class};` | Wrong default; standard requires `{}` |
| `String payload() default "ERROR";` | Wrong type and meaning |
| `@Retention(CLASS)` | Metadata is not stored with required `RUNTIME` retention |
| Omitting `@Constraint` | No longer recognized as a Bean Validation constraint |
| Using `String validReason()` | Element names starting with `valid` are forbidden in constraint definitions |
| `@Constraint(validatedBy=...) ` pointing to wrong-type validator | May raise validator selection errors, e.g. `UnexpectedTypeException` |

In Java, some mistyped annotation declarations fail to compile immediately (e.g. a default returning an incompatible class); however, several errors are **runtime constraint definition errors**, typically seen as `ConstraintDefinitionException`. Do not rely solely on `javac` succeeding to conclude a constraint is valid. Add integration tests calling `validator.validate(...)` or inspecting custom constraint metadata to detect configuration errors early.

## 15. Do not attach `groups` or `payload` onto `ConstraintValidator`

A common design mistake is assuming the provider uses the validator class to determine groups or severity:

```java
// Not a group selection mechanism per Jakarta Validation:
public class RegionValidator
        implements ConstraintValidator<AllowedRegion, String> {
    // No mandatory groups/payload annotations on this class.
}
```

This is an illustrative snippet; there is no need to apply `@Validated` or severity markers to `ConstraintValidator` for it to work. **Groups and payloads reside on the constraint declaration**, i.e. the annotation attached to a specific field/getter/type/parameter.

If custom logic needs `prefix`, use `initialize(annotation)` to read the declared custom parameter. If logic needs a complex business policy, inject a service or choose a constraint matching that policy. Do not rely on `payload` to automatically alter provider behavior: the standard API does not guarantee `ConstraintValidator.isValid` is passed a severity payload as a parameter.

## 16. Constraint composition: the three attributes on the outer constraint

Jakarta Validation allows creating a **composed constraint** from other constraints. Example:

```java
@NotBlank
@Size(min = 3, max = 16)
@Constraint(validatedBy = {})
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.ANNOTATION_TYPE,
    ElementType.PARAMETER,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
public @interface ShortDisplayName {

    String message() default "invalid display name";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

This is an **illustrative annotation**, requiring imports for `jakarta.validation.Constraint`, `@NotBlank`, `@Size`, `Payload`, `java.lang.annotation.*`, placed in `ShortDisplayName.java`. A composed constraint with `validatedBy={}` is valid because logic comes from the composing constraints.

**Important rule:** when nested constraints are composed via an outer annotation, `groups` and `payload` of composing constraints are inherited from the **main constraint declaration** according to composition rules; you cannot simply put different groups on each inner annotation expecting them to run independently.

If you add `@ReportAsSingleViolation` to the outer annotation, a failure in composing constraints can be reported as **a single violation carrying the main constraint's message**, instead of multiple separate violations; this is an explicit way to alter error reporting, not a feature of `payload`.

For complex composed constraints, `@OverridesAttribute` and `value()` allow forwarding parameters down to component constraints, though they should only be used when reuse yields clear benefits. Do not force a simple constraint into a hard-to-debug composition.

## 17. Combining `message`, `groups`, and `payload` with nested validation

Consider the DTO:

```java
public final class CheckoutRequest {
    @NotNull
    @Valid
    private Address deliveryAddress;

    @AllowedRegion(
        prefix = "VN-",
        groups = OnCreate.class,
        payload = Severity.Error.class
    )
    private String regionCode;
}
```

This is an illustrative model, requiring `Address`, imports, and the groups/markers from earlier sections. If `Address` has a field `@NotBlank String city`, then:

- `@Valid` **is not a constraint**; it tells the provider to cascade into the child object if validation actually runs.
- If `Address` is null, `@NotNull` on `deliveryAddress` catches the missing value in the Default group.
- If only `OnCreate` is requested without an inheritance/sequence relationship to Default, the default `@NotNull` constraint on `deliveryAddress` may not be selected.
- Payload attached to `regionCode` does not "propagate" onto constraints of `Address`. Each constraint declaration owns its own metadata.
- The `OnCreate` group can be propagated across cascades per Jakarta Validation rules; when you need to convert groups along a cascade path, use `@ConvertGroup` properly rather than misusing `payload`.

When nesting collections or `Optional`, type-use annotations and value extractors govern which values are validated. Selected groups still control constraint selection, and payload still describes the declaration. These three axes are independent yet appear together in a single validation pass.

## 18. Testing each axis independently

Writing separate tests helps pinpoint where failures lie:

| Test | Intent | What to verify |
| --- | --- | --- |
| Default message | Do not override `message` | `getMessageTemplate()` is the key; `getMessage()` is the interpolated result |
| Message override | Set `message` on the field | Provider uses the overridden template |
| Attribute interpolation | Change `prefix` | `{prefix}` content changes accurately per declaration |
| Default group | `validate(bean)` | Only default constraints and matching group rules |
| OnCreate group | `validate(bean, OnCreate.class)` | Only constraints in the selected/inherited group |
| Multiple groups | `validate(bean, Default.class, OnCreate.class)` | Violation set is the proper union, without relying on ordering |
| Payload | `getConstraintDescriptor().getPayload()` | `Severity.Error.class` marker is present if declared |
| Payload independence | Switch severity Error to Info | `isValid` still validates the value identically |
| Unsupported type | Place string constraint on `Integer` | Detects configuration / validator resolution error |
| Spring MVC | `@Validated(OnCreate.class)` on DTO parameter | MVC triggers the right group and returns errors per contract |
| Spring service | Call through managed bean/interceptor | Method validation actually runs |
| Locale | Look up `_vi`/`_en` resource bundle | Message matches locale, not confused with error codes |

Example JUnit 5 snippet with the program's model:

```java
@Test
void onCreateKeepsErrorPayload() {
    var input = new Registration("Mai", "US-101", "EU-123");

    var errors = validator.validate(input, OnCreate.class);

    assertEquals(1, errors.size());
    var v = errors.iterator().next();

    assertEquals("primaryCode", v.getPropertyPath().toString());
    assertEquals("code must start with VN-", v.getMessage());
    assertTrue(v.getConstraintDescriptor()
                .getPayload()
                .contains(Severity.Error.class));
}
```

This is an **illustrative test method**, not a standalone test file. It requires JUnit 5, a `validator` instance from the Spring context, static imports for assertions, and `Registration`, `OnCreate`, and `Severity` classes with proper packages/imports. To use the nested classes from the demo, reference `ConstraintMetadataDemo.Registration`, `ConstraintMetadataDemo.OnCreate`, `ConstraintMetadataDemo.Severity`, or use suitable static imports.

`Set<ConstraintViolation>` **guarantees no ordering**. For multiple errors, assert on sets of paths/messages or sort before comparing. Tests must not assert ordering between two groups unless a matching group sequence is configured.

## 19. Troubleshooting workflow

When a custom constraint does not behave properly, check in order:

1. **Is the definition compliant?** Does the annotation have `@Constraint`, `@Retention(RUNTIME)`, and `message`/`groups`/`payload` with proper types and `{}` defaults?
2. **Does the validator match the type?** If `AllowedRegionValidator` supports `CharSequence`, do not place it on `Integer` expecting automatic conversion to a string.
3. **Is a provider present?** Having only the API without an implementation will not execute properly. In Boot, typically use the compatible validation starter.
4. **Is validation actually triggered?** Annotations do not execute automatically on constructor or setter calls.
5. **Is the right group selected?** `@Valid` usually selects Default, `@Validated(OnCreate.class)` selects OnCreate; custom groups do not include Default by default.
6. **Does the message bundle exist?** The key must match, the file must be on the classpath, and the locale must be valid; distinguish `getMessageTemplate()` from `getMessage()`.
7. **Are attribute names right?** `{prefix}` must match the declared `prefix()` element, not an arbitrary Java field name.
8. **Is payload read in the right place?** `getPayload()` on the descriptor; Spring `FieldError` does not expose severity in JSON by default.
9. **Custom message override?** If `isValid` builds a custom violation and disables the default, check the builder, node, and message template of the created violation.
10. **Is Spring DI being used?** With `LocalValidatorFactoryBean`, `SpringConstraintValidatorFactory` usually enables dependency injection into `ConstraintValidator`; a standalone `Validation.buildDefaultValidatorFactory()` may not use the same factory.
11. **Are XML/composition overrides active?** Metadata can be altered/composed per provider rules; inspect `ConstraintDescriptor` to see the effective declaration.
12. **Messages are display content, not a security boundary:** escaping and HTTP error handling remain the application's responsibility.

### Common error table

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ConstraintDefinitionException` | Missing/invalid signatures for `message`, `groups`, `payload` | Follow the standard definition |
| `UnexpectedTypeException` | No validator supports the field's type | Change the type/constraint or write a compatible validator |
| Message shows `{app...message}` | Key missing from bundle or wrong key | Check `ValidationMessages.properties`, classpath, locale |
| `{prefix}` not replaced | Mismatched template/key/attribute or custom interpolator | Check annotation elements and interpolation setup |
| `@Valid` does not check OnCreate | OnCreate is not Default | Use `@Validated(OnCreate.class)` or explicit validator |
| Payload missing from HTTP response | Spring does not serialize marker metadata automatically | Map errors per your own API contract |
| Request still fails with Warning attached | Warning is still a violation when `isValid` returns false | Redefine policy at the application layer |
| Provider never calls validator | Missing trigger or group not selected | Check entry point and group |
| Two similar errors due to custom composition | Duplicate constraints or unintended composition | Audit composing constraints and `@ReportAsSingleViolation` |
| Service method validation does not run | Missing proxy/integration, self-invocation, or `new` | Check Spring-managed bean and post-processor |
| Test messages differ after locale change | Test depends on default locale | Pin locale/message or assert template/code |

## 20. Self-check questions

**1. Which three elements must a custom constraint annotation have?**  
`String message() default ...`, `Class<?>[] groups() default {}`, `Class<? extends Payload>[] payload() default {}`.

**2. Does `groups() default {}` mean the constraint belongs to no group?**  
No. When no group is specified at the declaration, the constraint belongs to `Default`.

**3. Does `@AllowedRegion(groups=OnCreate.class)` run automatically when creating the DTO?**  
No. You must invoke validation with OnCreate or have an integration point that selects the appropriate group.

**4. `message()` defaults to `"{demo.AllowedRegion.message}"`: what is the text inside curly braces?**  
Typically a key looked up in a resource bundle and interpolated according to provider rules.

**5. Are `getMessage()` and `getMessageTemplate()` identical?**  
No. One is the interpolated message, and the other is the violation's original template.

**6. Does `payload=Severity.Warning.class` automatically make a constraint non-blocking?**  
No. It is metadata; `isValid` and groups determine violations, while the application decides how to handle them.

**7. Where should you call to read severity from a violation?**  
`violation.getConstraintDescriptor().getPayload()`.

**8. Is `Severity.Warning` a group interface used with `@Validated`?**  
No. Groups and payloads are two independent contracts; a marker extending `Payload` is not automatically a selected business group.

**9. How can `prefix()` be referenced inside a message?**  
Place `{prefix}` in the template; the provider interpolates it from the corresponding annotation attribute.

**10. Can `@GroupSequence` and `payload` replace each other?**  
No. A group sequence orders group evaluation; payload describes metadata.

**11. Which standard payloads directly affect container unwrapping?**  
`Unwrapping.Unwrap` and `Unwrapping.Skip`, per Jakarta Validation's value extraction contract.

**12. Why should tests for groups, messages, and payloads be separated?**  
Because a constraint can validate correctly while selecting the wrong group, interpolating the wrong message, or missing marker metadata; each axis has distinct failure causes.

## 21. Conclusion

When designing a custom constraint, **`message` specifies how violations are reported**, **`groups` specifies which validation pass selects the constraint**, and **`payload` carries metadata for integration clients**. The three elements have fixed types and defaults per Jakarta Validation, while `ConstraintValidator.isValid` holds responsibility for validating data.

A well-designed constraint needs a clear type contract, interpolatable/internationalizable messages, deliberate group selection, payload interpreted only at the intended layer, and tests verifying **each axis separately**. In Spring, verify integration points using `@Valid`, `@Validated`, `LocalValidatorFactoryBean`, or `jakarta.validation.Validator` calls; do not equate "annotation is present" with "validation was executed".

## Official references

- Jakarta Validation 3.1 — Constraint definition, mandatory `message`/`groups`/`payload`: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation 3.1 API — `@Constraint`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/Constraint.html
- Jakarta Validation 3.1 API — `ConstraintDescriptor`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/metadata/ConstraintDescriptor.html
- Jakarta Validation 3.1 API — `ConstraintViolation`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/ConstraintViolation.html
- Hibernate Validator Reference Guide — Custom constraints and payloads: https://docs.hibernate.org/stable/validator/reference/en-US/html_single/
- Spring Framework Reference — Java Bean Validation and custom constraints: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework Reference — Spring MVC validation configuration: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html
- Spring Framework Reference — Controller validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
