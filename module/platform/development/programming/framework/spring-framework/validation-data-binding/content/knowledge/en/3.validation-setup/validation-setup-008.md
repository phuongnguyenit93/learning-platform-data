# Migrating Namespace `javax.validation` to `jakarta.validation` in Spring Framework

## 1. Why Must You Migrate?

When upgrading an application from Spring Framework 5.x / Spring Boot 2.x to Spring Framework 6.x / Spring Boot 3.x, a foundational change is moving from Java EE APIs named `javax.*` to Jakarta EE APIs named `jakarta.*`. For **Bean Validation**, the legacy `javax.validation` namespace is replaced by **`jakarta.validation`**.

Example of the same rule:

```java
// Legacy application (Javax Bean Validation 2.x)
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.Size;
```

```java
// Modern application (Jakarta Validation 3.x)
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
```

The meaning of `@NotBlank` or `@Size` remains validating constraints on data, but **they are Java types in different packages**. `javax.validation.Valid` and `jakarta.validation.Valid` are not the same annotation; the fact that a project still compiles when both libraries happen to sit on the classpath does not prove the newer Spring version will execute validation properly.

The scope of this lesson is **Bean Validation setup** and migrating related code, dependencies, configuration, and tests in Spring. Changing the namespace does not by itself alter business rules, stored data, or API JSON fields.

### Compatibility Milestones to Know

| Platform | Typical Bean Validation namespace | Key notes |
| --- | --- | --- |
| Spring Framework 5.x, Spring Boot 2.x | `javax.validation.*` | Matches legacy Java EE / Bean Validation ecosystem |
| Spring Framework 6.x, Spring Boot 3.x | `jakarta.validation.*` | Spring 6 requires Java 17+; must use Jakarta-compatible API/validator |
| Jakarta Bean Validation 2.0 | `javax.validation.*` | Even though the artifact may be named `jakarta.validation-api:2.0.x`, the package is still `javax` |
| Jakarta Bean Validation 3.0 | `jakarta.validation.*` | Changed package and XML namespace; fits Jakarta EE 9/10 |
| Jakarta Validation 3.1 | `jakarta.validation.*` | Belongs to newer Jakarta EE; coordinate versions per platform |

Easy-to-miss detail: **the artifact `jakarta.validation:jakarta.validation-api` version 2.0.x still contains the `javax.validation` package**. To import `jakarta.validation.*`, you must use Jakarta Validation 3.0+ per the version stack managed by Spring Boot/the framework. Do not infer package names from the artifact name alone.

## 2. Three Components That Must Be Compatible Together

Changing `import` statements is a source-code step, but runtime also depends on two other layers:

1. **Validation API:** defines `@Valid`, `@NotNull`, `@Size`, `Validator`, `ConstraintViolation`, `ConstraintValidator`, etc. In the newer stack, this is `jakarta.validation:jakarta.validation-api` at the appropriate Jakarta version.
2. **Validation provider:** the library that executes rules and resolves metadata. Most commonly Hibernate Validator. Hibernate Validator 6.x uses the `javax` namespace; 7.x and 8.x use `jakarta` (version 8 aligns with Jakarta EE 10); newer lines follow newer Jakarta releases.
3. **Spring integration:** Spring MVC, Spring `LocalValidatorFactoryBean`, `@Validated`, `@ModelAttribute`, and `@RequestBody` wire the binder/validator and surface errors to controllers.

In a **Spring Boot 3.x** application, the standard approach is letting Boot manage versions and adding the validation starter. Do not add only the API artifact while omitting a provider; with only interfaces/annotations, constraint evaluation may not run or `ValidatorFactory` initialization will fail for lack of an implementation.

### Maven: Standard Configuration for Spring Boot 3.x

If `pom.xml` already uses the Spring Boot 3.x parent/BOM, declare:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
</dependencies>
```

`spring-boot-starter-validation` pulls in the validation libraries matching the Boot version managed by the project. **Do not manually pin `jakarta.validation-api` or Hibernate Validator versions different from the BOM** unless there is a specific compatibility requirement. If the project only needs validation at the service/core layer, `spring-boot-starter-validation` can still be used independently of `spring-boot-starter-web`.

### Gradle: Configuration in a Spring Boot Project

With Groovy DSL (`build.gradle`), when the project already uses the Spring Boot plugin and dependency version management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

With Kotlin DSL (`build.gradle.kts`):

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
```

If using **plain Spring Framework** without Boot, you must add both the Jakarta Validation API and a compatible provider, and configure `LocalValidatorFactoryBean`/validators for MVC if needed. Do not copy versionless Boot snippets into a build that has no dependency management.

### Legacy Dependencies to Remove or Upgrade

- `javax.validation:validation-api` is the legacy Bean Validation API namespace.
- `jakarta.validation:jakarta.validation-api:2.0.x` is **not** yet the `jakarta.validation` namespace.
- `org.hibernate.validator:hibernate-validator` 6.x implements `javax.validation`; for Spring Boot 3.x, use the Jakarta-compatible line managed by Boot.
- Internal/third-party libraries compiled against `javax.validation.ConstraintValidator`, `javax.validation.Validator`, or exposing `javax.validation.ConstraintViolation` in public APIs must be upgraded/updated to the new namespace. You cannot merely change imports at the call site and expect old binaries to be compatible.

**Neither changing versions alone nor changing imports alone is enough:** you must verify the entire path from annotations to the validator provider and Spring integration.

## 3. Import Mapping Table: Update Exactly What Belongs to Bean Validation

| Before (Javax) | After (Jakarta) | Role |
| --- | --- | --- |
| `javax.validation.Valid` | `jakarta.validation.Valid` | Triggers cascaded validation / contextual argument validation |
| `javax.validation.constraints.NotNull` | `jakarta.validation.constraints.NotNull` | Disallows `null` |
| `javax.validation.constraints.NotBlank` | `jakarta.validation.constraints.NotBlank` | String must not be `null`, empty, or whitespace-only |
| `javax.validation.constraints.NotEmpty` | `jakarta.validation.constraints.NotEmpty` | String/collection/map/array must not be empty |
| `javax.validation.constraints.Size` | `jakarta.validation.constraints.Size` | Size bounds |
| `javax.validation.constraints.Min`, `Max` | `jakarta.validation.constraints.Min`, `Max` | Numeric bounds |
| `javax.validation.constraints.Email` | `jakarta.validation.constraints.Email` | Email format check per provider |
| `javax.validation.Validator` | `jakarta.validation.Validator` | Direct validation API |
| `javax.validation.Validation` | `jakarta.validation.Validation` | Bootstraps `ValidatorFactory` |
| `javax.validation.ValidatorFactory` | `jakarta.validation.ValidatorFactory` | Factory producing validators |
| `javax.validation.ConstraintViolation` | `jakarta.validation.ConstraintViolation` | Describes a single violation |
| `javax.validation.ConstraintViolationException` | `jakarta.validation.ConstraintViolationException` | Constraint violation exception |
| `javax.validation.Constraint` | `jakarta.validation.Constraint` | Defines custom constraint annotations |
| `javax.validation.Payload` | `jakarta.validation.Payload` | Constraint metadata |
| `javax.validation.ConstraintValidator` | `jakarta.validation.ConstraintValidator` | Custom constraint evaluation logic |
| `javax.validation.ConstraintValidatorContext` | `jakarta.validation.ConstraintValidatorContext` | Context for building violations |
| `javax.validation.groups.Default` | `jakarta.validation.groups.Default` | Default validation group |
| `javax.validation.executable.*` | `jakarta.validation.executable.*` | Method/constructor validation |
| `javax.validation.valueextraction.*` | `jakarta.validation.valueextraction.*` | Container element validation |

Meanwhile, **Spring's own** components remain in the `org.springframework.*` packages, for example:

```java
import org.springframework.validation.annotation.Validated;
import org.springframework.validation.BindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator; // Spring's own Validator
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ModelAttribute;
```

Distinguish **`org.springframework.validation.Validator`** from **`jakarta.validation.Validator`**; they have different interfaces and methods. Spring provides adapters such as `LocalValidatorFactoryBean` to bridge the two worlds. Do not mechanically find-and-replace every occurrence of `Validator` or every `javax.` prefix.

## 4. Controlled Upgrade Process

### Step 1 — Lock Down Platform Versions

Confirm which Spring Framework/Boot and JDK versions the application runs on. Targeting Spring Boot 3.x requires Java 17+ and Spring Framework 6.x. If still on Spring Boot 2.x/Spring 5.x, simply changing `javax.validation` to `jakarta.validation` will usually break compatibility with the older framework. Upgrade the **platform and dependencies** per the upgrade guide first, then migrate source imports.

### Step 2 — Find Every Occurrence of the Old Namespace

At the application source root, you can use `rg`:

```bash
rg -n 'javax\.validation|javax\.el|validation-api|hibernate-validator' .
```

Check not only `src/main/java` but also `src/test/java`, configuration files, shared modules, and generated code. For libraries with public APIs, inspect public method signatures, generic types, and annotations in shared DTOs. `javax.el` is related to Hibernate Validator/message interpolation; if present, review compatibility with Jakarta Expression Language rather than ignoring it.

Read each match in context: namespaces like `javax.crypto`, `javax.net`, and `javax.xml` remain part of Java SE and **must not be mass-replaced**.

### Step 3 — Fix Dependencies Before Editing Imports

With Maven:

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=javax.validation:validation-api,jakarta.validation:jakarta.validation-api,org.hibernate.validator:hibernate-validator
```

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency validation-api
./gradlew dependencyInsight --configuration runtimeClasspath --dependency hibernate-validator
```

Identify which dependency brings the old API/provider onto the classpath. Prefer **upgrading the root library**. Only use `exclude` for transitive dependencies that are genuinely unnecessary once verified; excluding the provider by mistake can silently disable validation.

### Step 4 — Migrate Imports and Dependent Types

Change `javax.validation.*` to `jakarta.validation.*` across controllers, DTOs, entities, services, custom validators, and tests. Inspect custom constraints, validation groups, exception handlers, APIs returning `Set<ConstraintViolation<T>>`, shared library interfaces, and reflection/codegen relying on annotation names.

Example of the same record DTO:

```java
// Before: when the project still used the javax Bean Validation namespace
import javax.validation.constraints.Email;
import javax.validation.constraints.NotBlank;

public record RegisterRequest(
        @NotBlank String username,
        @NotBlank @Email String email) {}
```

```java
// After: with Jakarta Validation 3.x and Spring Boot 3.x
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record RegisterRequest(
        @NotBlank String username,
        @NotBlank @Email String email) {}
```

These two snippets **are alternative versions**, not placed together in one file. `RegisterRequest` must reside in `RegisterRequest.java` with an appropriate package; the examples intentionally omit the `package` line to highlight the changed imports.

### Step 5 — Update XML and Special Integrations If Present

If the project uses `META-INF/validation.xml` or XML constraint mappings, update XML namespaces to Jakarta standards rather than only editing Java imports.

| Component | Old namespace | Jakarta Validation 3.0 namespace |
| --- | --- | --- |
| `validation.xml` | `http://xmlns.jcp.org/xml/ns/validation/configuration` | `https://jakarta.ee/xml/ns/validation/configuration` |
| Constraint mapping XML | `http://xmlns.jcp.org/xml/ns/validation/mapping` | `https://jakarta.ee/xml/ns/validation/mapping` |

For schema 3.0, minimal illustrative configuration:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<validation-config xmlns="https://jakarta.ee/xml/ns/validation/configuration"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="https://jakarta.ee/xml/ns/validation/configuration https://jakarta.ee/xml/ns/validation/validation-configuration-3.0.xsd"
    version="3.0">
</validation-config>
```

Create `validation.xml` only when you genuinely need provider/constraint mapping configuration; simple Boot projects usually **do not need** this file. For other Jakarta Validation versions, check the namespace/schema supported by that specification version. If the project references `javax.validation...` class names in XML, SPI resources `META-INF/services/...`, or bytecode analysis rules, update those as well. `ValidationMessages.properties` can keep existing message keys; only update keys/values that depend on old type names.

### Step 6 — Clean Build and Behavioral Verification

Run compilation, unit tests, and integration tests on the **actual application classpath**, rather than relying on IDE autocomplete. After migration, search the source again for `javax.validation` and inspect the dependency tree to confirm no unintended legacy usage remains. A legacy library may still pull `javax.validation-api` onto the classpath while compilation succeeds; that is a signal to investigate compatibility.

## 5. Runnable Spring MVC Example After Migration

The example below uses Java 17+, Spring Boot 3.x, Spring MVC, and Jakarta Validation. Both starters `spring-boot-starter-web` and `spring-boot-starter-validation` from section 2 are required.

Create `src/main/java/example/validation/ValidationMigrationApplication.java`:

```java
package example.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ValidationMigrationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationMigrationApplication.class, args);
    }

    public record Registration(
            @NotBlank String name,
            @NotBlank @Email String email,
            @NotNull @Min(18) Integer age) {}

    @PostMapping(path = "/registrations",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> register(
            @Valid @RequestBody Registration input) {

        return ResponseEntity.ok("accepted:" + input.email());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<String> handleInvalidInput(
            MethodArgumentNotValidException exception) {

        return ResponseEntity.badRequest().body("VALIDATION_FAILED");
    }
}
```

**Run prerequisites:** Use a Maven/Gradle Spring Boot 3.x application declaring the two dependencies above and JDK 17+. In this example, a single Java file suffices for the application/controller class; the provider is supplied by the validation starter. Launch with:

```bash
mvn spring-boot:run
```

If using Gradle, run `./gradlew bootRun`. By default, the application serves on port 8080 unless configured otherwise.

Valid request:

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":"Lan","email":"lan@example.com","age":24}'
```

Expected HTTP status: `200 OK`. Exact **response body** produced by the controller:

```text
accepted:lan@example.com
```

Request violating constraints:

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":"","email":"not-an-email","age":15}'
```

Expected HTTP status: `400 Bad Request`. **Response body** from our custom handler:

```text
VALIDATION_FAILED
```

Mechanism: Jackson deserializes JSON into `Registration`; `@Valid` instructs Bean Validation to evaluate `@NotBlank`, `@Email`, `@NotNull`, and `@Min`. When the `@RequestBody` argument is invalid in this case, Spring MVC raises `MethodArgumentNotValidException`, handled by `@ExceptionHandler`. Because the result does not depend on the provider's default message wording, the example is easy to verify.

**Do not confuse two error types:** malformed JSON or JSON that cannot convert to the DTO typically causes `HttpMessageNotReadableException`; a syntactically valid request violating Bean Validation follows the `MethodArgumentNotValidException` path above. Specific exceptions also depend on handler design and validation style.

## 6. After Updating Imports, Trigger Validation in the Right Places

### `@RequestBody` / `@ModelAttribute`

- `@Valid` should be imported from `jakarta.validation.Valid`. Place `@Valid` before the DTO in the method parameter to trigger validation after binding/conversion.
- `@ModelAttribute` is used for form/query binding; `@RequestBody` is typically used for JSON/XML bodies. Both can be validated by Spring MVC.
- If the controller needs to handle form errors itself, place `BindingResult` **immediately after** the validated model/request parameter as supported by Spring MVC. `BindingResult` still belongs to `org.springframework.validation`.
- For controllers with constraints placed directly on method parameters, Spring MVC 6.1+ provides **method validation** and may throw `HandlerMethodValidationException` instead of `MethodArgumentNotValidException`. Do not assume a single exception type for every controller signature.

Example form handler inside a controller:

```java
import jakarta.validation.Valid;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

// Method snippet, placed inside an appropriate @Controller class:
@PostMapping("/profile")
public String save(@Valid @ModelAttribute ProfileForm form,
                   BindingResult errors) {
    if (errors.hasErrors()) {
        return "profile-form";
    }
    return "profile-saved";
}
```

`ProfileForm` and views are defined in the real application; the snippet above is a **method illustration**, not a standalone Java file. With Spring MVC, `BindingResult` must immediately follow the object whose errors it collects.

### Spring's `@Validated` Keeps Its Package

`org.springframework.validation.annotation.Validated` is **Spring's** annotation, commonly used for validation groups or enabling method validation on Spring-managed services. Namespace migration does not turn it into `jakarta.validation.Validated`; no such replacement exists.

```java
import jakarta.validation.constraints.Min;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class AccountService {
    public void setAge(@Min(18) int age) {
        // Executes only when the parameter is valid.
    }
}
```

`AccountService` illustrates a class in an application with a Jakarta provider and Spring method validation configured. For Spring to apply proxy/AOP validation on a service, the method must be called **through the Spring bean/proxy**; self-invocation within the same object can bypass the proxy. Do not treat service method validation as proof that MVC request validation works: they are two distinct activation paths.

### Cascaded Validation with Nested Objects

`@Valid` must appear wherever validation should cascade into nested objects. Example:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.util.List;

public record Address(@NotBlank String city) {}

public record CustomerInput(
        @NotBlank String name,
        @Valid Address address,
        List<@Valid Address> previousAddresses) {}
```

These are **two top-level record declarations**, placed in `Address.java` and `CustomerInput.java` (or scoped appropriately per Java rules). Even after a successful namespace migration, forgetting `@Valid` on nested object fields can leave child constraints unevaluated. For lists or maps, container element validation syntax depends on API/provider support.

## 7. Migrating Custom Constraints and Validators

Projects using only `@NotBlank` and `@Size` usually update imports fairly quickly. For custom annotations, you must migrate **the custom validator interface as well**, along with `Payload`, `ConstraintValidatorContext`, and referenced types; migrating only half causes compile errors or prevents the provider from finding the validator.

Annotation example in `src/main/java/example/validation/ValidSku.java`:

```java
package example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Constraint(validatedBy = SkuValidator.class)
@Target({ElementType.FIELD, ElementType.PARAMETER,
         ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidSku {
    String message() default "SKU must start with SKU-";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

Validator in `src/main/java/example/validation/SkuValidator.java`:

```java
package example.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class SkuValidator
        implements ConstraintValidator<ValidSku, String> {

    @Override
    public boolean isValid(String value,
                           ConstraintValidatorContext context) {
        return value == null || value.startsWith("SKU-");
    }
}
```

After compiling against the Jakarta Validation API/provider, `@ValidSku` can be placed on compatible fields or parameters. The logic here **allows `null`** (a common convention for format-checking constraints); to require a value as well, combine with `@NotNull` or `@NotBlank`. For richer custom annotations, also review validation groups, composition (`@ReportAsSingleViolation`), container targets, custom messages, and value extractors.

If custom validation uses Hibernate Validator-specific annotations, check the migration guide for the **exact provider version**. Some extension annotations were deprecated or removed in newer lines; do not assume every annotation under `org.hibernate.validator.constraints` still exists unchanged.

## 8. Common Errors During Namespace Migration

| Symptom | Common cause | How to verify/fix |
| --- | --- | --- |
| `package jakarta.validation does not exist` | Jakarta 3.x+ API missing or classpath still uses API 2.0.x | Check dependency tree and BOM |
| `cannot find symbol: Valid` | Still importing `javax.validation.Valid` or API removed without replacement | Use `jakarta.validation.Valid` |
| Constraints are on DTO yet requests slip through | Missing `@Valid`, provider, MVC config, or annotation still in old namespace | Check annotation imports, starter, and real HTTP tests |
| `NoProviderFoundException` | API is present without a compatible implementation | Add/fix provider; in Boot, use the validation starter |
| `NoClassDefFoundError: javax/validation/...` | A library was compiled against Javax while runtime has only Jakarta | Upgrade/rebuild that library for Jakarta |
| `ClassNotFoundException: jakarta.validation...` | Jakarta API missing at runtime or dependency excluded by mistake | Check `runtimeClasspath`/packaged artifact |
| `UnexpectedTypeException` | Constraint placed on a type unsupported by the validator | Inspect type, constraint, and custom validator implementation |
| Error reading `validation.xml` | Legacy XML namespace/XSD/provider settings | Update XML to the matching Jakarta version |
| `@Validated` import changed wrongly | Confusing Spring's annotation with Jakarta | Keep `org.springframework.validation.annotation.Validated` |
| Unit tests pass yet HTTP does not return 400 | Test validates DTO directly without going through MVC binding | Add MockMvc or HTTP integration tests |
| Validation runs twice or throws a different exception | Controller uses method validation or different proxy configuration | Check method signatures, Spring version, and exception path |

Do not solve migration by keeping **both the Javax API and the Jakarta API** hoping the framework bridges both annotation systems. They may coexist in the dependency graph because of legacy libraries; the goal is to identify the source, upgrade the relevant piece, and ensure production call paths use the unified Jakarta namespace.

## 9. Testing After Migration: Verify Behavior, Not Just Compilation

### Minimum Test Cases

| Test case | Expected result |
| --- | --- |
| DTO with `@NotBlank` receives blank string via `@Valid @RequestBody` | HTTP 400 per handler/exception configuration |
| Valid DTO | Controller processes normally |
| `@Min(18)` receives `age=15` | Rejected by validation |
| `@NotNull` receives `null` or missing field | Produces a violation for the property |
| DTO contains child object annotated with `@Valid` | Constraints on child object are evaluated |
| Custom `@ValidSku` with `"ABC"` | Produces violation when validator is properly configured |
| `@Validated` service with method constraint | Failure caught when invoked through Spring proxy |
| Legacy `javax.validation` dependency references | No direct dependency left, or clear third-party upgrade plan |

### Testing Directly with Jakarta Validator

In a project with a compatible Jakarta provider, you can write validation logic independent of HTTP:

```java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;

// Snippet placed inside an appropriate Java class/method:
record Input(@NotBlank String name) {}

try (ValidatorFactory factory =
         Validation.buildDefaultValidatorFactory()) {
    Validator validator = factory.getValidator();
    int count = validator.validate(new Input("")).size();
    System.out.println(count);
}
```

With a standard provider evaluating `@NotBlank` and a single constraint as above, stdout:

```text
1
```

This is a snippet placing `record Input` in class/method scope and the `try` block inside a **method** (Java 17+), not a standalone Java file; if `ValidatorFactory` fails to initialize, inspect the provider/dependencies. Direct checks prove Jakarta Validator works, whereas proving Spring MVC invokes the right validator requires integration tests.

Run existing tests and a full build, for example:

```bash
mvn clean test
# Or in Gradle:
./gradlew clean test
```

For web applications, also verify actual HTTP statuses, `BindingResult` contents, or exception handlers—never treat a passing `compileJava` as the finish line. After migrating, search again for all occurrences of `javax.validation`: occurrences in comments/migration docs may be valid, whereas production source code, runtime config, and integration libraries must be specifically audited.

## 10. Implementation Checklist and Error-Prevention Principles

1. **Lock Spring Boot/Framework + JDK:** Spring 6.x / Boot 3.x is compatible with Jakarta Validation and Java 17+.
2. **Align dependencies:** use compatible Jakarta Validation API 3.x and an appropriate provider, preferring Boot's starter/BOM; remove or upgrade identified legacy Javax dependencies.
3. **Migrate source code selectively:** `javax.validation.*` → `jakarta.validation.*` in imports, generics, custom constraints, exceptions, shared modules, and tests; do not indiscriminately rename Java SE packages that still use `javax.*`.
4. **Preserve Spring integration:** `@Validated` and `BindingResult` remain under `org.springframework.validation`; ensure `@Valid` is the Jakarta annotation.
5. **Update specialized configs:** XML namespaces, SPI descriptors, manual validator beans, codegen, and extension libraries (if any).
6. **Test both layers:** direct Jakarta validator **and** validation via Spring MVC/services; test binding errors, constraint errors, cascaded validation, and custom validators.
7. **Audit real runtime:** dependency tree, packaged JAR, and startup logs; confirm there are no missing-class/missing-provider errors or silent non-running validation.

A migration is successful when **Jakarta annotations are recognized by a Jakarta provider and applied properly by Spring to requests/services** with verified behavioral tests. The core difference lies in types/packages and the runtime dependency chain, not in how `@NotBlank` or `@Min` conditions are written.

## Authoritative References

- [Jakarta Bean Validation 3.0 specification](https://jakarta.ee/specifications/bean-validation/3.0/)
- [Jakarta Bean Validation 3.0 — namespace change and XML descriptors](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Spring Boot 3.0 Migration Guide — Jakarta EE](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Framework 6.x Upgrade Guide](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Hibernate Validator — Migration Guide](https://hibernate.org/validator/documentation/migration-guide/)
