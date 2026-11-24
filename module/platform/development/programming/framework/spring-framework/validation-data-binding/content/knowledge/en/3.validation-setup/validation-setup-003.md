# Distinguishing Jakarta Validation API and Validation Provider

## 1. Why Must You Distinguish Them Right During Setup?

Suppose a Java application has a DTO with `@NotBlank` and `@Min`. The IDE recognizes the annotations and `mvn compile` succeeds, yet at runtime no errors are detected, or the application reports that no validation provider was found. These two situations can only be resolved properly by separating the **API**, the **provider**, and the **validation trigger**.

- **Jakarta Validation API** is the *standard contract* (specification/API): it defines constraint annotations, interfaces, result objects, and the bootstrap mechanism. The commonly used artifact is `jakarta.validation:jakarta.validation-api`; the package is `jakarta.validation.*`.
- **Validation provider** is the *implementation library* fulfilling that contract: it discovers constraints, instantiates `ConstraintValidator`, checks values, interpolates messages, and creates `ConstraintViolation` objects. A popular provider is **Hibernate Validator**, artifact `org.hibernate.validator:hibernate-validator`. Apache BVal is another example of a provider.
- **Caller/trigger** is the part that actually requests validation: code calling `jakarta.validation.Validator#validate(...)`, or Spring MVC/Method Validation configured to invoke the validator at the right execution point.

Having the API lets code **compile**. Having the provider gives the API **an execution engine**. Having the trigger makes validation **actually run**. These three conditions cannot substitute for one another.

```text
Application / Spring code
  |  uses @NotBlank, @Min, @Valid, and Validator
  v
Jakarta Validation API (jakarta.validation.*)
  |  Bootstrap / SPI / execution contract
  v
Validation provider (e.g., Hibernate Validator)
  |  Resolves metadata, runs ConstraintValidator, interpolates messages
  v
Set<ConstraintViolation<T>> -> handled by the application or Spring adapter
```

**Common pitfall:** `@Valid` is an API annotation; simply placing `@Valid` on an object instantiated via `new` does not cause validation to run automatically. A supporting entry point is required, such as `validator.validate(obj)` or a controller argument for which Spring MVC runs validation.

## 2. What Does the API Contain, and What Does the Provider Add?

| Aspect | Jakarta Validation API | Validation provider |
| --- | --- | --- |
| Role | Describes the standard contract, data types, and interaction rules | Provides the runtime that executes the contract |
| Maven coordinate | `jakarta.validation:jakarta.validation-api` | e.g., `org.hibernate.validator:hibernate-validator` |
| Representative types | `Validation`, `Validator`, `ValidatorFactory`, `ConstraintViolation`, `ConstraintValidator` | Bootstrap classes, metadata engine, validator implementations, message interpolation |
| Standard constraints | Declares `@NotNull`, `@NotBlank`, `@Size`, `@Min`, `@Valid`… | Provides runtime logic to validate constraints |
| Can compile annotations? | Yes, if the API is on the compile classpath | Provider is usually not needed directly in source code |
| Can actually validate via `validate`? | No, if only the API is present | Yes, if a compatible provider is discovered and initialized |
| Tied to Spring? | No | Not required; Spring is a consumer/integrator |
| Swapping implementations? | Code using standard APIs usually stays intact | Another provider can be chosen if spec-compliant and not relying on vendor extensions |

Core APIs:

- `jakarta.validation.Validation`: entry point to bootstrap a `ValidatorFactory`.
- `jakarta.validation.ValidatorFactory`: configurable factory initialized once and closed when the application shuts down; supplies `Validator`.
- `jakarta.validation.Validator`: API for calling `validate`, `validateProperty`, `validateValue`, and accessing metadata.
- `jakarta.validation.ConstraintViolation<T>`: describes a single constraint failure, including property path, message, invalid value, and descriptor.
- `jakarta.validation.ConstraintValidator<A, T>`: contract for the validation logic of a custom annotation.
- `jakarta.validation.spi.ValidationProvider`: SPI allowing implementation libraries to participate in bootstrapping.

**Additional distinction:** `jakarta.validation.Validator` and `org.springframework.validation.Validator` are two distinct interfaces. `Hibernate Validator` is also a different project from `Hibernate ORM` used for JPA; you cannot assume Bean Validation is ready simply because Hibernate ORM is present.

## 3. Trying an API-Only Setup: Compiles but Lacks an Engine

In a Java SE Maven project, the standalone API dependency can be declared as:

```xml
<dependency>
    <groupId>jakarta.validation</groupId>
    <artifactId>jakarta.validation-api</artifactId>
    <version>3.0.2</version>
</dependency>
```

The following imports will then compile:

```java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Min;
```

A data class can also declare constraints:

```java
record Account(@NotBlank String username, @Min(18) int age) {}
```

However, if the runtime classpath **has only the Jakarta Validation API and no provider**, the bootstrap call:

```java
var factory = Validation.buildDefaultValidatorFactory();
```

cannot create a working factory. In a missing-provider scenario, the API throws `jakarta.validation.NoProviderFoundException` (a subtype of `ValidationException`), rather than evaluating `@NotBlank` or `@Min` itself. Do not catch the exception and treat it as "validation succeeded": that is a **setup error**.

In addition, **having both API and provider without a trigger** also prevents annotations from being enforced. For instance, simply calling `new Account(" ", 16)` and storing the object without any `validate` call or corresponding framework mechanism gives no reason to expect a validation exception.

## 4. Setting Up a Provider for Java SE with Maven

The example below uses Jakarta Validation API 3.0.2, a compatible Hibernate Validator 8.0.x release, and a Jakarta Expression Language implementation for message interpolation. The versions are **pinned so the example is reproducible**; in a real project, use a compatible version set aligned with the project's dependency management.

Directory structure:

```text
validation-setup/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApiProviderDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>validation-setup</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <!-- Standard contract; the provider may also pull in the API transitively. -->
        <dependency>
            <groupId>jakarta.validation</groupId>
            <artifactId>jakarta.validation-api</artifactId>
            <version>3.0.2</version>
        </dependency>

        <!-- Implementation that executes constraints. -->
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.6.Final</version>
        </dependency>

        <!-- Jakarta EL used for default message interpolation in Java SE. -->
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Why is there an EL dependency? According to Hibernate Validator documentation, the default message interpolation mechanism supports Jakarta Expression Language expressions. In a Jakarta EE container environment, an EL implementation may already be supplied by the container; in standalone Java SE, an appropriate library usually needs to be added. Do not confuse an **EL implementation** with a **validation provider**: EL only supports message interpolation; adding EL cannot replace Hibernate Validator.

File `src/main/java/demo/ApiProviderDemo.java`:

```java
package demo;

import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import java.util.List;

public final class ApiProviderDemo {

    record Account(@NotBlank String username, @Min(18) int age) {}

    public static void main(String[] args) {
        Account account = new Account("   ", 16);

        try (ValidatorFactory factory =
                 Validation.buildDefaultValidatorFactory()) {

            // The variable type is the Jakarta API; the implementation comes from the provider.
            jakarta.validation.Validator validator = factory.getValidator();

            List<String> errors = validator.validate(account).stream()
                .map(v -> v.getPropertyPath() + ":"
                    + v.getConstraintDescriptor()
                       .getAnnotation()
                       .annotationType()
                       .getSimpleName())
                .sorted()
                .toList();

            System.out.println("Errors: " + errors);
        }
    }
}
```

From the `validation-setup` directory, with JDK 17+ and Maven installed:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ApiProviderDemo
```

The line printed by the program itself (there may also be logging messages from the provider depending on configuration):

```text
Errors: [age:Min, username:NotBlank]
```

Step-by-step explanation:

1. `@NotBlank` and `@Min` are recognized by the compiler via the API.
2. `Validation.buildDefaultValidatorFactory()` uses the bootstrap mechanism to locate an implementation.
3. Hibernate Validator is initialized as the provider; `factory.getValidator()` returns a validator implementing the standard Jakarta interface.
4. `validator.validate(account)` checks the data and returns `Set<ConstraintViolation<Account>>`.
5. The program converts the violations into property name + annotation name and sorts them for stable output; the result contains two errors because username contains only whitespace and age is less than 18.

If you remove the `hibernate-validator` dependency from `pom.xml` while keeping the API and EL, the program still compiles, but at the bootstrap step it fails with a missing provider error. If you remove the `validator.validate(account)` step, no validation is requested at all. These two experiments clearly separate the three stages: **compile contract → runtime implementation → invocation**.

## 5. How Does Bootstrap Discover the Validation Provider?

Jakarta Validation specifies an implementation discovery mechanism via SPI. With default bootstrapping:

```java
try (var factory = Validation.buildDefaultValidatorFactory()) {
    var validator = factory.getValidator();
    // Use validator.
}
```

Overview of the process:

1. The API uses provider resolution to locate available implementations on the runtime classpath/module path.
2. Following the Java Service Provider mechanism, an implementation can advertise its service via the resource `META-INF/services/jakarta.validation.spi.ValidationProvider`. Hibernate Validator uses the provider class `org.hibernate.validator.HibernateValidator`.
3. Bootstrap selects and configures the provider according to Jakarta Validation rules, creating a `ValidatorFactory`.
4. `ValidatorFactory` returns a `Validator` to execute validation on objects.

The file `META-INF/services/jakarta.validation.spi.ValidationProvider` is the **provider's service descriptor**, not a place where the application puts DTO annotations. Normally Maven/Gradle pulls this resource from the provider JAR; the application does not need to create it manually.

### If Multiple Providers Are Present

Do not rely on JAR ordering on the classpath to guess which provider is used. You can explicitly specify an implementation when truly needed:

```java
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import org.hibernate.validator.HibernateValidator;

try (ValidatorFactory factory =
         Validation.byProvider(HibernateValidator.class)
             .configure()
             .buildValidatorFactory()) {
    var validator = factory.getValidator();
    // Validate objects via the Jakarta API.
}
```

This is an illustrative snippet placed inside a Java method with appropriate exception handling or declaration. Using `HibernateValidator.class` makes the code **directly dependent** on a specific provider: compilation requires the Hibernate Validator artifact on the compile classpath, and changing providers will require code edits. When portability is desired, prefer `buildDefaultValidatorFactory()`; when a specific provider is needed, you can use `Validation.byProvider(...)` or configure the default provider via `META-INF/validation.xml` per the specification.

In special classloader environments such as OSGi or certain custom-packaged applications, service-based discovery may require a custom `ValidationProviderResolver`. With fat JARs built by manually merging JARs, do not drop `META-INF/services/*` files; losing the service descriptor can cause `NoProviderFoundException` even when the provider classes are still present.

## 6. Spring Boot: Which Dependencies Should You Declare?

With **Spring Boot 3.x** (using the `jakarta.validation.*` namespace), the standard setup is using the validation starter; Boot's dependency management selects compatible dependency versions. You do not need to manually pin Jakarta API and provider versions when using Boot's BOM/parent properly.

Maven, in a project already using the Spring Boot parent/BOM:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Gradle Groovy DSL, in a project already configured with the Spring Boot plugin/dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

The starter supplies the components needed for Jakarta Bean Validation, including the Hibernate Validator provider in a typical Spring Boot setup. If the application also exposes REST endpoints, you normally add the Web dependency separately; the validation starter by itself **does not** create controllers or an HTTP server.

Example DTO using the standard API:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateAccountRequest(
    @NotBlank String username,
    @Min(18) int age
) {}
```

**Illustrative** example in a Spring MVC controller within a project that already has Spring Web and Bean Validation:

```java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @PostMapping("/accounts")
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreateAccountRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

This is **not** the standalone program from section 4; it requires a Spring Boot Web project and a separate `CreateAccountRequest.java` file. `@Valid` on the parameter instructs Spring MVC to trigger Bean Validation after JSON has been deserialized into an object. For constraint violations on a request argument validated this way, Spring MVC typically raises `MethodArgumentNotValidException`; without a custom handler, the default mechanism may return HTTP 400. Appropriate error responses should be configured for the application.

### What Does LocalValidatorFactoryBean Do?

Spring provides `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean`, which initializes the Jakarta Validation provider via the bootstrap mechanism and simultaneously adapts it to:

- `jakarta.validation.Validator` / `jakarta.validation.ValidatorFactory`: the standard API side.
- `org.springframework.validation.Validator`: Spring's `Errors`/`BindingResult` side.

In a Spring Framework project without Boot, once the Jakarta API and provider are present, you can declare the bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class ValidationConfig {
    @Bean
    public LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }
}
```

This snippet is a Spring configuration that needs to be scanned/registered in the ApplicationContext. `LocalValidatorFactoryBean` **is not** a second provider: it bootstraps and uses the actual provider, then integrates errors into Spring's model. When using Boot, usually let auto-configuration perform this setup, and only register the bean manually if specific customization is required.

**Distinguishing runtime errors:** Jackson/HTTP converter failing to read JSON is a deserialization/binding error; an object being created but failing `@NotBlank`/`@Min` is a constraint validation error. Do not lump both together as "missing validation provider".

## 7. Version Compatibility and Namespaces

During setup, three dependency layers must belong to the same generation:

1. **API/spec**: the Jakarta Validation namespace and version expected by the project/framework.
2. **Provider**: an implementation supporting that API version.
3. **Framework integration**: Spring Framework/Spring Boot, error translation libraries, and related components.

A compatible example pair is Jakarta Validation API 3.0.x and Hibernate Validator 8.0.x with JDK 17. In a Spring Boot project, use the version set managed by the corresponding BOM rather than hardcoding versions copied from a standalone example.

| Environment | Typical validation imports | Dependency selection guidance |
| --- | --- | --- |
| Spring Framework 5 / Boot 2 (legacy) | `javax.validation.*` | API/provider compatible with the `javax` generation |
| Spring Framework 6 / Boot 3 | `jakarta.validation.*` | Validation starter or Jakarta-compatible API/provider |
| Java SE using Jakarta Validation | `jakarta.validation.*` | API + provider + required runtime dependencies |
| Jakarta EE container | `jakarta.validation.*` | Check provider and EL supplied by the container before adding JARs |

**Do not fix things by only changing imports** from `javax.validation` to `jakarta.validation` while keeping an incompatible old provider. Nor does every artifact named `hibernate-*` supply a `ValidationProvider`. To verify the exact JARs resolved, use the dependency tree rather than guessing from starter names.

For example:

```bash
mvn dependency:tree
```

Or with Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

When reading the dependency tree, verify that the **runtime classpath** includes both the Jakarta Validation API and a compatible provider. Misusing `compileOnly` or `provided` can allow the IDE to compile while leaving the provider absent at runtime. In actual deployment artifacts (Docker image, executable JAR), also confirm the provider is packaged properly.

## 8. EL, Message Interpolation, and Initialization Failures

Beyond the API and provider, Hibernate Validator typically needs a Jakarta Expression Language implementation to fully handle default message interpolation. For example:

```java
@Min(value = 18, message = "Age must be at least {value}")
int age;
```

`{value}` is a constraint message parameter; in addition, message templates may contain EL expressions. The provider is responsible for processing messages according to the specification. When no EL implementation is present in Java SE, the provider may throw an error while initializing the message interpolator even though Hibernate Validator itself is present.

Hibernate Validator provides `org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator` for environments without EL:

```java
import jakarta.validation.Validation;
import org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator;

try (var factory = Validation.byDefaultProvider()
        .configure()
        .messageInterpolator(new ParameterMessageInterpolator())
        .buildValidatorFactory()) {
    var validator = factory.getValidator();
    // Use validator.
}
```

This is a **Hibernate Validator-specific option**, not a full equivalent to the spec-defined interpolation algorithm with EL: templates containing EL expressions will not be fully evaluated. For standard applications, prefer supplying a compatible EL implementation and keeping standard message interpolation.

If localized messages are needed, Jakarta Validation supports `ValidationMessages.properties` and corresponding locale bundles on the classpath. In Spring, `LocalValidatorFactoryBean` also allows integrating an appropriate message source. Incorrectly interpolated error messages may be a resource bundle/EL issue, independent of whether constraints are being evaluated.

## 9. Diagnosing Setup Failures

| Symptom | Causes to check | Resolution |
| --- | --- | --- |
| Compiler reports missing `jakarta.validation` package | API missing from compile classpath, or mixing `javax`/`jakarta` | Add the appropriate dependency/BOM, align imports with framework version |
| `NoProviderFoundException` on bootstrap | API is present but provider is missing on runtime classpath, or service discovery is broken | Add a compatible provider; inspect dependency tree and `META-INF/services` |
| Provider is present but message interpolator initialization fails | Missing Jakarta EL implementation or version mismatch | Add a compatible EL library; consider alternative interpolator with noted limitations |
| Annotations are present but invalid data slips through | No `validate` call, missing `@Valid` at entry point, or framework validation not enabled | Pinpoint the exact trigger point and verify configuration |
| `NoSuchMethodError`, `ClassNotFoundException`, `LinkageError` | Incompatible API/provider/framework versions or duplicate versions on classpath | Check dependency resolution, BOM, packaging, and namespace |
| Multiple providers present and behavior is unexpected | Default provider not selected as anticipated | Explicitly configure the provider rather than relying on JAR order |
| `@NotBlank` does not apply to the field type used | Constraint does not support target type or data type differs from expectations | Check constraint targets; `@NotBlank` is for `CharSequence` strings |
| Validation errors occur but REST response has wrong format | Spring translates errors into exception/`BindingResult` but app lacks response handling | Build an appropriate handler once the provider is working |
| Provider not found inside executable/fat JAR | Packaging dropped the library or service descriptor | Inspect final artifact contents and how service metadata is merged |

Minimal diagnostic steps, in order to minimize debugging time:

1. Inspect the dependency tree of the **running application**; confirm both API and provider are present at runtime.
2. Check whether annotation and API packages are `jakarta.validation` or `javax.validation`; verify provider/framework compatibility.
3. Try calling `Validation.buildDefaultValidatorFactory()` in a standalone program to separate bootstrap failures from Spring/controller issues.
4. Call `validator.validate(new Account("   ", 16))` to confirm the provider actually returns violations.
5. If bootstrap succeeds but messages are wrong, check EL, bundles, and locale; if Spring does not trigger validation, check the placement of `@Valid`, `@Validated`, and entry points.
6. If the error only appears after packaging, inspect the classpath/service descriptors inside the deployment artifact.

## 10. Long-Term Design Considerations

- **Program against the standard API:** DTO classes, services, and shared libraries should prefer importing `jakarta.validation.*`. Use provider extensions only when solving a concrete requirement.
- **Let dependency management control versions:** with Spring Boot, prefer starters/BOMs. With Java SE, lock compatible API/provider/EL versions and inspect the dependency tree.
- **Reuse `ValidatorFactory`:** creating the factory is not an operation to perform per request; build it once for the application lifecycle, obtain `Validator` from it, and close the factory on shutdown. In Spring, let the container manage this bean.
- **Do not instantiate providers manually:** go through `Validation`/`ValidatorFactory` or Spring's integration configuration to respect the SPI and object lifecycle.
- **Distinguish errors from exceptions:** a violation is the result of data failing checks; a bootstrap exception is a misconfigured application. Do not treat a missing-provider exception as a business validation violation.
- **Trust only triggered behavior:** having annotations on the model, having dependencies on the classpath, and passing requests through a validator are three separate conditions; verify all three during QA.

## 11. Self-Check Questions

1. Why does declaring only `jakarta.validation-api` allow `@NotBlank` to compile while `Validation.buildDefaultValidatorFactory()` fails?
2. How do Hibernate Validator and `jakarta.validation.Validator` differ in role? When swapping providers, which code usually remains unchanged?
3. Why does adding an EL implementation without adding a provider still fail to resolve `NoProviderFoundException`?
4. When Spring Boot 3 already uses `spring-boot-starter-validation`, should you manually add multiple different API/provider versions? Why or why not?
5. If both API and provider are present but objects are only instantiated with `new`, what else is needed to catch invalid data?
6. When packaging a fat JAR, why can losing `META-INF/services/jakarta.validation.spi.ValidationProvider` cause an error?

**Remember:** the Jakarta Validation API defines the *contract*; the validation provider executes the contract; application/Spring code creates *the invocation point*. A proper setup must satisfy compile dependencies, runtime dependencies, and trigger placement.

## References

- Jakarta Validation specification: https://jakarta.ee/specifications/bean-validation/
- Hibernate Validator 8.0 Reference Guide — Getting started, Provider discovery, and Message interpolation: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework — Java Bean Validation and `LocalValidatorFactoryBean`: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Boot — Validation: https://docs.spring.io/spring-boot/reference/io/validation.html
