# Looking Up APIs and Behavior Changes Across Spring Framework Versions

## 1. Objectives and Scope

When working with **Spring Framework – Validation & Data Binding**, an example that works in documentation for a newer version may not compile or behave identically in a project using an older version. The issue is not merely whether a method exists: the Framework version, Spring Boot, Bean Validation libraries, type converters, MVC parameter handling, and application configuration can all affect the outcome.

After this lesson, you will be able to:

1. Identify the **actual Spring Framework version resolved and running**, rather than confusing it with the Spring Boot version or the documentation version currently open in a browser.
2. Locate the right **Reference Documentation**, **Javadoc**, **release notes**, **upgrade guides**, source code, and tests for a specific version.
3. Distinguish **API signature changes** from **runtime behavior changes** across `DataBinder`, `WebDataBinder`, `ConversionService`, `Validator`, `@ModelAttribute`, and method validation.
4. Build a small reproducer with verifiable inputs and outputs before applying conclusions to a real application.
5. Compile an impact checklist when upgrading from Spring Framework 5.3 to 6.x, between 6.x branches, or from 6.x to 7.x.

The scope focuses on **validation and data binding** in Spring Core/Spring MVC; where necessary, the lesson notes boundaries with Spring WebFlux and JSON deserialization. Spring Framework 7's addition of **API versioning for HTTP endpoints** is a separate feature and not the main topic here. "API version" in this lesson refers to library versions and Java programming contracts.

## 2. Distinguishing API, Behavior, and Runtime Environment

**API** is the surface your code calls or implements: packages, classes, interfaces, methods, constructors, annotations, parameters, return types, and public exceptions. For example, `DataBinder.setDeclarativeBinding(boolean)` is a Spring method.

**Behavior** is the outcome after calling an API or sending a request: whether a form field is bound, whether errors go into `BindingResult` or throw an exception, whether the controller method is invoked, which HTTP status is returned, or which formatter applies to dates.

**Environment** includes the JDK, Spring Framework, Spring Boot (if used), Jakarta Validation API/provider, servlet container, dependency graph, and MVC configuration. Two projects with identical controller code but differences in these components can produce different results.

Typical examples:

- Code calling `DataBinder.setDeclarativeBinding(true)` will **not compile** if the compile classpath has a `DataBinder` version prior to Spring Framework **6.1**, when this API was introduced.
- The same controller with `@RequestParam @Min(1)` can go through different validation mechanisms depending on whether MVC runs before or from Spring **6.1**, because Spring MVC 6.1 added **built-in method validation**.
- `@Valid` in a Spring 5.x application typically imports `javax.validation.Valid`; when upgrading to Spring Framework 6 (Jakarta EE ecosystem), you must use `jakarta.validation.Valid` and compatible validation libraries.
- A JSON parsing error in `@RequestBody` may come from Jackson/message converters, whereas a property assignment error in `@ModelAttribute` goes through data binding. Changing `ConversionService` is not guaranteed to fix a Jackson error.

Therefore, every technical conclusion should follow the structure: **"On Spring Framework version X, with dependencies/configuration Y and input Z, outcome K is observed."** Avoid drawing sweeping conclusions from an article that omits version numbers.

## 3. Identifying the Exact Version Before Looking Up Docs

### 3.1. Spring Boot Is Not Spring Framework

Spring Boot provides auto-configuration and a BOM-managed set of dependencies. The `spring-boot` version number and the `spring-framework` version number **are not the same**. For instance, changing the Boot version can pull in new versions of `spring-core`, `spring-context`, `spring-web`, and `spring-webmvc`. Do not guess a Framework version solely from configuration file names.

For **Gradle** projects, inspect the resolved configuration:

~~~bash
./gradlew dependencyInsight --dependency spring-context --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

On Windows, use `gradlew.bat` instead of `./gradlew`. For multi-project Gradle builds, include the subproject path, e.g., `./gradlew :web-app:dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath`; `web-app` here only illustrates command structure. If the project has no `runtimeClasspath` configuration, check the module's actual configurations.

For **Maven**:

~~~bash
mvn dependency:tree -Dincludes=org.springframework
mvn help:effective-pom
~~~

The goal is recording **the version selected after dependency management and conflict resolution**. A direct declaration or a transitive dependency pulling another version does not by itself prove which version is active. Check consistency across Spring artifacts; mixing incompatible major/minor versions can cause `NoSuchMethodError`, `ClassNotFoundException`, or unpredictable behavior.

In a running application with Spring Core, you can check:

~~~java
import org.springframework.core.SpringVersion;

System.out.println("Framework=" + SpringVersion.getVersion());
System.out.println("Java=" + Runtime.version());
~~~

This is a **snippet** to place inside an executing application method. `SpringVersion.getVersion()` normally returns the version of the loaded Spring Core; under certain special packaging setups it may return `null`. In that case, inspect the JARs/classpath rather than guessing a version number. Do not treat a startup banner as the sole proof for every Spring module.

### 3.2. Locking Down a "Version Profile" for the Issue

Before researching, record the following fields:

| Field | Example details to record |
| --- | --- |
| Framework | Exact versions of `spring-core`, `spring-context`, `spring-web`, `spring-webmvc` |
| Boot | Present or not; Boot version and actual BOM |
| JDK | Java 17, 21, or active runtime version; note difference from source compatibility if any |
| Validation | `jakarta.validation` or `javax.validation`; which provider and version |
| Web stack | Spring MVC/Servlet or WebFlux; using `@ModelAttribute`, `@RequestParam`, or `@RequestBody` |
| Failure path | Compile error, startup failure, binding error, validation error, exception, or HTTP response |
| Configuration | `WebMvcConfigurer`, `@InitBinder`, `@Validated`, custom `Converter`/`Formatter`, `@ControllerAdvice` |

For example, the error "`HandlerMethodValidationException` does not exist" first requires checking the `spring-web` version and active validation mechanism before reading Javadoc. The symptom "`@Valid` does not run" requires verifying the provider, annotations, parameter types, and how Spring invokes validation.

## 4. Authoritative Sources and How to Read Them Properly

### 4.1. Reliable Lookup Order

| Source | Purpose | What to record |
| --- | --- | --- |
| **Exact-version Javadoc** | Signatures, inheritance, `@since`, `@Deprecated`, method contracts | Package, module/JAR, parameters, return type, exceptions, since |
| **Reference Documentation of the same branch** | Processing flows, applicability conditions, configuration patterns | Endpoints, binding types, validation order, configuration scope |
| **Release Notes / Upgrade Guide** | Breaking changes, new features, changed defaults | Starting version, migration requirements, recommended replacements |
| **Source code at release tag** | Exact behavior when Javadoc is not explicit enough | Conditional branches and actual execution paths |
| **Tests in source at tag** | Behavioral evidence, edge cases | Test names, inputs, asserted exceptions/results |
| **Reproducer running exact dependencies** | Confirmation in the application's environment | Commands, Java/Framework/provider, stdout/HTTP response |

Official starting links:

- [Spring Framework Reference – Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring MVC – Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring MVC – `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC – `@InitBinder`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework Javadoc – navigation portal](https://docs.spring.io/spring-framework/docs/current/javadoc-api/)
- [Spring Framework 6.x Upgrade Guide](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)
- [Spring Framework release tags](https://github.com/spring-projects/spring-framework/tags)
- [Spring Framework support branches](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions)

Unversioned `reference` pages typically display the currently published branch. When working on older systems, **also check archived documentation for that exact version** if available, and use the Javadoc of the exact resolved artifact. Do not assume an example on the "current" page runs verbatim on 5.3 or 6.0.

### 4.2. Reading Javadoc with a Consistent Process

Suppose you need to look up `org.springframework.validation.DataBinder.setDeclarativeBinding`:

1. Confirm the full name: `org.springframework.validation.DataBinder`, in `spring-context`. Do not confuse `DataBinder` with `WebDataBinder`, which is a subclass for web environments.
2. Open [Spring 6.1.0 DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.html) and find `setDeclarativeBinding`.
3. Read the signature `void setDeclarativeBinding(boolean declarativeBinding)`, its description, and **Since: 6.1**. This is direct evidence of when the API appeared.
4. Check **See Also** and related methods such as `setAllowedFields`, `construct`, `bind`, and `getBindingResult`. Ask whether the method affects *constructor binding*, *property binding*, or both.
5. Compare against the Javadoc of the older/exact version in use. If an API does not show up, verify the exact class name, package, version, and whether the method is inherited before concluding it "does not exist".
6. If the change affects runtime errors or security, also check the Reference, release notes, and a small test.

Key markers in Javadoc:

- `@since`: when the API was introduced; **does not by itself prove** behavioral details across every patch release.
- `@Deprecated` or "Deprecated": recommendation to stop using, possibly accompanied by `forRemoval` and a replacement. Deprecated **does not mean** immediately removed.
- Parameters / Returns / Throws: the contract callers can rely on.
- Implemented Interfaces / Superclasses: a method may be declared on an interface or inherited from a superclass.
- Nullability, generic types, and annotations: can change static checks/Kotlin interoperability even when method names stay unchanged.

### 4.3. From Docs to Tagged Source Code and Tests

In the GitHub repository `spring-projects/spring-framework`, select **the specific release tag** rather than looking at `main` by default. For each API, check in turn:

1. Locate the Java file declaring the method/annotation by full package.
2. Find call sites and related unit/integration tests.
3. Compare the **two tags of interest**, noting what changed: signatures, defaults, conditions, exceptions, processing order.
4. Check issue/PR history when release notes do not fully explain why a change was made.
5. Use application tests to confirm within your stack, since custom configuration can produce behavior different from Spring's own tests.

A single line of diff is rarely enough. For example, adding a public method does not guarantee MVC calls it by default; you must check whether the framework/Boot registers or enables that feature.

## 5. Essential API Map for Validation & Data Binding

| API / annotation | Group / library | What to look up |
| --- | --- | --- |
| `org.springframework.validation.DataBinder` | Spring validation (`spring-context`) | Constructor/property binding, allowed fields, errors, validators, declarative mode |
| `org.springframework.web.bind.WebDataBinder` | Spring web | Web request binder subclass; scoped formatters/converters/editors |
| `org.springframework.validation.BindingResult` | Spring validation | `FieldError`, `ObjectError`, rejected values, suppressed fields |
| `org.springframework.validation.Validator` | Spring validation | `supports`, `validate`; usable without Jakarta Validation |
| `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` | Spring validation + Jakarta | Adapter integrating a Bean Validation provider into Spring |
| `jakarta.validation.Valid` / `jakarta.validation.constraints.*` | Jakarta Validation API | Cascaded validation and constraints; requires a compatible provider |
| `org.springframework.validation.annotation.Validated` | Spring validation | Validation groups and AOP-based method validation scenarios |
| `org.springframework.core.convert.ConversionService` | Spring Core | Type conversion, `canConvert`/`convert` |
| `org.springframework.core.convert.converter.Converter` | Spring Core | Custom type conversion rules |
| `org.springframework.format.Formatter` | Spring formatting | Locale-aware parse/print |
| `org.springframework.web.bind.annotation.ModelAttribute` | Spring Web | Retrieve or create model objects and bind request values |
| `org.springframework.web.bind.annotation.InitBinder` | Spring Web | Configure `WebDataBinder` per controller/advice |
| `org.springframework.web.servlet.config.annotation.WebMvcConfigurer` | Spring MVC | Register converters/formatters/validators at MVC scope |
| `org.springframework.web.bind.MethodArgumentNotValidException` | Spring Web | Validation/binding error for arguments handled by resolvers |
| `org.springframework.web.method.annotation.HandlerMethodValidationException` | Spring Web, since 6.1 | Error result from MVC's built-in method validation |

Exact class names are critical when searching: Spring's `Validator` and Jakarta's `Validator` share the same short name but differ in package, contract, and methods. `LocalValidatorFactoryBean` is typically the bridge. Likewise, MVC form formatters are not the same component as JSON deserializers.

## 6. Version Milestones to Verify During Upgrades

| Spring Framework line | Relevant change milestones | What to verify |
| --- | --- | --- |
| **5.3.x** | Pre-Jakarta migration generation; Bean Validation ecosystem typically uses `javax.validation` | `javax.*` imports, provider, Java/runtime, how method validation is enabled |
| **6.0.x** | Java 17 baseline; migrated to Jakarta EE 9, including `jakarta.validation` and `jakarta.servlet` | Updated imports + dependencies, container, Hibernate Validator compatibility |
| **6.1.x** | Spring MVC adds **built-in method validation**; `DataBinder.setDeclarativeBinding` introduced in 6.1 | Exception types, class-level `@Validated`, constructor/property binding, Javadoc `@since` |
| **6.2.x** | Final feature branch of the 6.x generation; patches may refine processing details and fix bugs | Check release notes/changelogs of the actual patch; do not treat all 6.x releases as identical |
| **7.0.x** | Jakarta EE 11 / Bean Validation 3.1 baseline, still supporting Java 17; favors Jackson 3 and JSpecify nullness | Matching-generation provider/container, JSON integration, nullability, deprecated/removed APIs |

This table is a **lookup starting point**, not a complete compatibility matrix or a guarantee that every app shares identical behavior. For every upgrade, read the notes of the **exact source and target releases**. For instance, the milestone "6.1 has built-in method validation" does not mean all validation runs automatically without a Bean Validation provider or required configuration.

### 6.1. Spring 5.3 → 6.0: Validation Namespace Changes

Example imports in a legacy-generation application:

~~~java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
~~~

When migrating to Spring Framework 6 and compatible Jakarta Validation:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
~~~

Changing imports **is only part** of the migration: the build must include matching-generation Jakarta Validation API/provider artifacts; the servlet stack also moves from `javax.servlet` to `jakarta.servlet`. Spring's own classes such as `org.springframework.validation.BindingResult` **do not** change packages to `jakarta.*`.

Common errors:

- `package javax.validation does not exist`: the compile classpath moved to Jakarta while source files still import the old package.
- `NoClassDefFoundError` or Bean Validation not running: missing API/provider, or incompatible provider version.
- `@Valid` is present but constraints are not checked: verify annotation placement, constraints on target object, provider discovery, and whether MVC/bean validation is actually invoked.

Do not mix `javax.validation.*` and `jakarta.validation.*` in the same pipeline expecting binary equivalence.

### 6.2. Spring 6.1: Watch Both New APIs and New MVC Mechanisms

Two cases have high instructional value:

**Case A: `DataBinder.setDeclarativeBinding(boolean)`.** Javadoc marks **Since: 6.1**. When set to `true`, the binder applies only explicitly declared binding paths: constructor binding and property binding restricted by `allowedFields`. The goal is curbing clients from arbitrarily populating properties outside valid input data. This API differs from `setAllowedFields`, which could already configure a property whitelist in earlier versions.

**Case B: built-in method validation in Spring MVC.** Before 6.1, validating constraints placed directly on method parameters typically required other setups, such as AOP method validation. From 6.1 onward, Spring MVC has a built-in mechanism for method argument/return constraints and may throw `HandlerMethodValidationException`. For `@Valid` on an ordinary command object under matching conditions, individual parameter-level validation may throw `MethodArgumentNotValidException`. Inspect method signatures because adding `@Min` or `@NotBlank` directly on a parameter can route the entire call through **method validation**.

### 6.3. Spring 7.0: Raising the Baseline Does Not Change Every Binding API

Spring Framework 7.0 keeps the **Java 17** baseline while raising underlying requirements to Jakarta EE 11 and Bean Validation 3.1. For web applications, verify compatible servlet containers and providers; for example, running an older-generation Jakarta Validation library can cause integration errors.

Framework 7.0 supports Jackson 3 under the `tools.jackson` package hierarchy and deprecates the Jackson 2 path. That matters if endpoints use JSON `@RequestBody`/`@ResponseBody`, but should not be conflated with changes to `DataBinder` for forms or query parameters. The framework also adopts JSpecify nullness annotations; nullable markers in Javadoc/tooling may differ from before even when methods remain intact.

Do not label any API "removed in Spring 7" merely because it was deprecated in 6.x: cross-check the 7.0 release notes and Javadoc. Exact patch-level changes must also be checked individually.

## 7. Scenario 1: Checking DataBinder APIs Across Versions

### 7.1. Asking the Technical Question Properly

"Can an application running Spring 6.0 call `setDeclarativeBinding(true)`? If upgrading to 6.1, how does binding allowed vs. disallowed form fields behave?"

Verification sequence:

1. Open `DataBinder` Javadoc at the resolved version and check the exact signature.
2. In 6.1.0, `setDeclarativeBinding(boolean)` shows **Since: 6.1**; do not copy that call into source code compiled against 6.0.
3. Read the description: `setDeclarativeBinding(true)` restricts property binding via `allowedFields`; constructor binding remains a separate path.
4. Check the input DTO, desired allowed field list, and how the binder is configured (`@InitBinder` or directly).
5. Send both allowed and disallowed fields, then inspect `BindingResult.getSuppressedFields()`. A suppressed field does not automatically throw an exception.
6. Re-run the test across both versions and record results; if differences appear, use the tag's code and tests to explain them.

Example inside a Spring MVC controller on **Spring 6.1+**:

~~~java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("registrationForm")
public void restrictInput(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("displayName", "email");
}
~~~

This is a **controller snippet**, not a standalone Java file. When using `@ModelAttribute("registrationForm")`, it configures the binder for that named model attribute. `setAllowedFields` enforces a property binding whitelist; constructor parameter selection still requires careful DTO design. Do not bind directly onto an entity containing `role`, `isAdmin`, or `balance` assuming validation annotations alone prevent all mass assignment.

### 7.2. Runnable Experiment on Java 17+

The experiment below uses **Spring Context** directly, without Spring Boot or a web server. It verifies two aspects:

- Whether the `setDeclarativeBinding(boolean)` API exists in the running JAR (using reflection so the source itself compiles on 6.0 as well).
- How `DataBinder` handles type-mismatched values and fields blocked by `allowedFields`.

Create `settings.gradle`:

~~~groovy
rootProject.name = 'spring-binding-api-probe'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

def frameworkVersion = providers.gradleProperty('frameworkVersion')
        .orElse('6.2.0')
        .get()

dependencies {
    implementation "org.springframework:spring-context:$frameworkVersion"
}

application {
    mainClass = 'FrameworkApiProbe'
}
~~~

Create `src/main/java/FrameworkApiProbe.java`:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class FrameworkApiProbe {

    public static class RegistrationForm {
        private Integer quantity;
        private String role;

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }
    }

    public static void main(String[] args) {
        boolean hasDeclarativeBinding = Arrays.stream(DataBinder.class.getMethods())
                .anyMatch(FrameworkApiProbe::isDeclarativeBindingSetter);

        RegistrationForm form = new RegistrationForm();
        DataBinder binder = new DataBinder(form);
        binder.setAllowedFields("quantity");

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("quantity", "abc");
        input.add("role", "ADMIN");
        binder.bind(input);

        BindingResult result = binder.getBindingResult();
        System.out.println("hasDeclarativeBinding=" + hasDeclarativeBinding);
        System.out.println("quantity=" + form.getQuantity());
        System.out.println("role=" + form.getRole());
        System.out.println("typeMismatch=" + result.hasFieldErrors("quantity"));
        System.out.println("suppressed=" +
                Arrays.toString(result.getSuppressedFields()));
    }

    private static boolean isDeclarativeBindingSetter(Method method) {
        return method.getName().equals("setDeclarativeBinding")
                && method.getParameterCount() == 1
                && method.getParameterTypes()[0] == boolean.class;
    }
}
~~~

Run with JDK 17+ and Gradle installed:

~~~bash
gradle -q run
~~~

With the default `frameworkVersion=6.2.0`, the program output is:

~~~text
hasDeclarativeBinding=true
quantity=null
role=null
typeMismatch=true
suppressed=[role]
~~~

Explanation: `quantity=abc` cannot convert to `Integer`, producing a `typeMismatch` field error; `role` is not in `allowedFields`, so it is suppressed and left unassigned. These are two distinct causes. Inspecting `BindingResult` reveals both conversion errors and blocked fields.

To check the API at two other milestones:

~~~bash
gradle -q run -PframeworkVersion=6.0.0
gradle -q run -PframeworkVersion=6.1.0
~~~

Expected first lines respectively:

~~~text
6.0.0 -> hasDeclarativeBinding=false
6.1.0 -> hasDeclarativeBinding=true
~~~

That is a **comparison table across two runs**, not combined stdout from a single run. The remaining four lines continue to report the example's binding checks. If using Gradle Wrapper, replace `gradle` with `./gradlew` on Linux/macOS or `gradlew.bat` on Windows.

The reflection check only tells you the public signature is present. It does not prove web configuration has enabled the feature. To test `setDeclarativeBinding(true)` behavior, add a test on Spring 6.1+ invoking the method directly and testing matching property binding/constructor binding.

## 8. Scenario 2: Validation Errors Change When Using Spring MVC 6.1+

### 8.1. Two Types of Validation in a Controller

Illustrative example in a Spring MVC application with a Jakarta Bean Validation provider:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ValidationExampleController {

    public record CreateRequest(@NotBlank String name) {
    }

    @PostMapping("/people")
    public String create(@Valid @RequestBody CreateRequest request) {
        return request.name();
    }

    @GetMapping("/people/page")
    public String page(@RequestParam @Min(1) int page) {
        return "page=" + page;
    }
}
~~~

This is an **integration example**, requiring a host application with Spring MVC and a Jakarta Bean Validation provider. The two paths differ:

- `POST /people` with JSON body `{"name":""}`: after JSON is deserialized into `CreateRequest`, `@Valid` triggers object validation. If the method has no other direct constraint triggering method validation, Spring MVC may throw `MethodArgumentNotValidException`.
- `GET /people/page?page=0`: `@Min(1)` is placed directly on the controller parameter. On Spring MVC **6.1+**, built-in method validation may produce `HandlerMethodValidationException`; handling is per parameter rather than a single DTO.

If the controller carries `@Validated` **at the class level**, method validation may route through an **AOP proxy**. Spring documentation advises removing class-level `@Validated` when you want to use MVC's built-in method validation introduced in 6.1. However, do not blindly delete the annotation from services: `MethodValidationPostProcessor` for non-controller service beans is a separate mechanism with its own purpose.

### 8.2. Why You Cannot Infer the Exception from `@Valid` Alone

`@Valid` cascades/evaluates constraints on an object, yet **is not itself a direct constraint annotation on a method parameter**. Adding `@NotNull`, `@Min`, or another constraint on a parameter/method can switch execution to method validation; in that case, even nested validation from `@Valid` may be covered by method validation.

For `@ModelAttribute` or `@RequestBody`, placing an `Errors`/`BindingResult` parameter **immediately after** the bound object allows the controller to handle applicable errors directly. Yet if a method validation error occurs on another parameter lacking a corresponding `Errors` parameter, the framework may still throw `HandlerMethodValidationException`. Do not write a single `@ExceptionHandler` catching only `MethodArgumentNotValidException` assuming it covers all validation forms.

Checklist before editing:

| Observation | What to check first |
| --- | --- |
| `@Valid` reports no errors | Provider, constraints, data source, annotations on arguments, validation groups |
| Errors newly become `HandlerMethodValidationException` | Are there direct constraints on parameters/return values? Is Spring MVC 6.1+? |
| Exception comes from AOP instead of MVC | Does the controller have class-level `@Validated`? Is `MethodValidationPostProcessor` active? |
| `BindingResult` is present yet controller is not invoked | Is the parameter immediately after the model attribute? Are there errors on other parameters? |
| Response differs from before upgrade | Catch the exact exception; inspect `@ControllerAdvice`, `ResponseEntityExceptionHandler`, and error response config |
| `quantity=abc` never reaches business validation | Did a `typeMismatch` conversion/binding error happen before validation? |

The exception class itself is only one piece of the observation. HTTP status and JSON body also depend on exception resolvers / Spring Boot error handling / `@ControllerAdvice`; do not treat a sample response in a tutorial as the universal default contract for every application.

## 9. Scenario 3: Distinguishing DataBinder, Converter, and JSON

Trace the data path before deciding which API to change:

~~~text
Query/Form/Path value
        |
        +-- MVC argument resolver / WebDataBinder
        |          |
        |          +-- ConversionService / Formatter
        |          +-- BindingResult: typeMismatch, rejectedValue, ...
        |          +-- Validator / Jakarta Validation provider
        |
        +-- Controller parameter or @ModelAttribute object

JSON request body
        |
        +-- HttpMessageConverter / JSON mapper
        |          |
        |          +-- Deserialize object (Jackson depending on version/config)
        |          +-- Then validation may run if @Valid/@Validated
        |
        +-- @RequestBody object
~~~

For example, with the same `LocalDate orderedOn` field:

- With `@ModelAttribute`, `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` can guide Spring formatting to parse date strings in the request.
- With `@RequestBody` JSON, the date is read by Jackson/the deserializer. Spring MVC's `FormatterRegistry` does not automatically alter the JSON mapper's rules.
- With `@RequestParam LocalDate`, MVC conversion/formatting applies based on the corresponding annotations/configuration.

When upgrading Framework 6.x to 7.0 where the Jackson ecosystem also changes, write separate tests for **JSON bodies** and **form/query binding**. Do not conflate two failures just because the error message mentions the same field name.

## 10. Scenario 4: Diagnosing a Missing or Deprecated API

### 10.1. "cannot find symbol" Error During Upgrade

For example, old code or code copied from newer documentation calls a method absent in the current version:

~~~text
error: cannot find symbol
  symbol:   method setDeclarativeBinding(boolean)
  location: variable binder of type DataBinder
~~~

Analyze in order:

1. Is it genuinely `org.springframework.validation.DataBinder` or another type with the same short name?
2. Which exact version of `spring-context` is on the **compileClasspath**?
3. Does that version's Javadoc contain the method with the expected signature and visibility?
4. Are you accidentally reading the "current" Javadoc of a newer release?
5. If a capability introduced in 6.1 is needed, decide between upgrading Framework/Boot **in lockstep** or using an older-compatible API (such as `setAllowedFields` for property whitelisting) per business requirements.

The runtime error `NoSuchMethodError` has a different nuance: **bytecode was compiled against an API that had the method, while the class loaded at runtime lacks that method**. Inspect both compile classpath and runtime classpath; do not just tweak imports.

### 10.2. When Encountering `@Deprecated`

Read the annotation and deprecation rationale in Javadoc, then check release notes/upgrade guides. Classify it:

- The API still runs, though migrating to another approach is recommended.
- One overload is discouraged, with a newer overload replacing it.
- The API was removed in a new major release and source code must be updated.
- Nullability or default contracts changed while the method remains present.

To compare clearly, build a concrete table:

| Item | Source version | Target version | Evidence |
| --- | --- | --- | --- |
| Class/method | Present/absent, signature | Present/absent, signature | Javadoc of both artifacts |
| Annotations & provider | Package, dependencies | Package, dependencies | BOM + Javadoc + build |
| Behavior | Input → expected result | Input → actual result | Tests on both versions |
| Errors | Exception and error fields | Exception and error fields | Stack traces + tests |
| Resolution | Current config | Targeted config/code change | Release notes/upgrade guide |

If tests have not been run yet, state clearly that the conclusion is **from documentation inspection**, not runtime evidence.

## 11. Regression Test Suite for Validation/Data Binding

A Framework change may let controllers compile while altering error types or binding behavior. For every migration, create tests with identical inputs and assertions on both versions.

### 11.1. Minimum Test Cases

| Case | Typical input | Required assertion |
| --- | --- | --- |
| Type conversion succeeds | `quantity=12` | Java field is `Integer 12`, no field errors |
| Type conversion fails | `quantity=abc` | `typeMismatch`/binding error present; do not assume business validators ran |
| Business validation | `quantity=0` with `@Min(1)` | Constraint error, distinct from parse error |
| Blocked field | `role=ADMIN` when only `quantity` is allowed | `role` remains unchanged; check suppressed fields |
| Missing required param | Missing `@RequestParam` | Appropriate missing value/argument error |
| Empty/invalid DTO fields | JSON `{"name":""}` with `@NotBlank` | Validation occurs when provider and annotations align |
| Direct constraint | `@RequestParam @Min(1) int page`, `page=0` | Validation path matches the Framework version |
| Locale/format | `01/02/2026` per chosen rule | Parsed/printed accurately per configured format/locale |
| JSON vs. form | Same date field received via both request types | Appropriate deserializer/binder for each path |
| Exception handler | Invalid request | Status and error body follow application API contract |

Note that `@Min` tests are only meaningful when a Bean Validation provider and appropriate trigger are configured; "no error" in an app missing a provider does not prove the Framework intentionally ignored the constraint.

### 11.2. Auditing Source Code and Build After Upgrade

- Recompile on a **JDK supported** by the target release.
- Read the dependency tree so no incompatible `spring-*` lines mix.
- Check `javax.validation`/`jakarta.validation` packages and the provider.
- Run unit tests at the `DataBinder`/`Validator` layer first; then test MVC with MockMvc or a real server to confirm HTTP statuses and exception handling.
- Check controllers carrying class-level `@Validated`; if adopting MVC's built-in validation from 6.1, re-read the migration guide.
- Audit DTO sources and bound field restrictions; in particular, never allow clients to arbitrarily update privilege fields.
- Separate JSON `@RequestBody` tests from form/query `@ModelAttribute` tests.
- Read release notes for the target minor/patch and related issue logs before assuming a bug is fixed.
- Record commands, versions, inputs, and actual outputs so future upgrades remain reproducible.

## 12. Sample Lookup Workflow from a Real Error

Scenario: after updating dependencies, `POST /people` returns a different error response than before. Do not rush to edit the exception handler; proceed as follows:

**Step 1 – Capture environment info.** Record versions of `spring-webmvc`, `spring-web`, Jakarta Validator provider, Java, and Spring Boot BOM. Run dependency inspection commands and preserve verifiable output.

**Step 2 – Capture input + controller signature.** Record HTTP method, content type, body/query, annotations on arguments and classes; check `@Valid`, direct constraints like `@NotBlank`, and `BindingResult` placement. Determine whether this is a JSON deserialization failure, binding failure, or validation failure.

**Step 3 – Open exact-version Javadoc.** Look up `MethodArgumentNotValidException`, `HandlerMethodValidationException`, `BindingResult`, and relevant methods. If a class appeared in 6.1, do not put a handler for that class into source compiled against 6.0.

**Step 4 – Read Reference + release notes.** Spring MVC docs explain when validation runs at the argument level versus method level; note conditions around class-level `@Validated`. If servlet/container or Jakarta providers are affected, also read the upgrade guide.

**Step 5 – Write fixed-input tests.** Send the same invalid request against source and target versions, recording exception class, field/parameter errors, HTTP status, and response body. Separate JSON parse error tests from Bean Validation tests.

**Step 6 – Fix at the right layer.** If the change is the validation exception, update `@ControllerAdvice`/`ResponseEntityExceptionHandler` or the error response contract. If it is input conversion, fix the formatter/converter or request format. If JSON, check JSON mapper configuration. If mass assignment, fix DTOs/allowed fields.

**Step 7 – Conclude with evidence.** Attach versions, Javadoc, release notes, tests, and post-fix results; never write "Spring changed behavior on its own" without pinpointing the specific change.

## 13. Common Misconceptions

**"I read the latest docs, so my code must be right."** "Current" documentation may belong to a newer branch than your dependencies. Always open docs/Javadoc for the exact version and check when an API appeared.

**"Spring Boot 4 and Spring Framework 4 are the same."** No. The two projects have independent versioning; Spring Boot manages an underlying set of libraries. Use the dependency tree/BOM to identify the Framework version.

**"Adding `@Valid` is enough for all validation to work."** Not necessarily. Check the provider, constraints, argument resolvers, method-level constraints, and corresponding AOP/MVC mechanisms.

**"All input errors are `MethodArgumentNotValidException`."** No. Spring MVC 6.1+ has method validation with `HandlerMethodValidationException`; conversion failures, JSON parse failures, and missing arguments each follow separate paths.

**"`BindingResult` can be placed anywhere."** No. In an MVC method signature, when used to handle errors of a model attribute/argument, it typically must sit immediately after that argument; errors on other parameters must still be accounted for.

**"`setAllowedFields` and `setDeclarativeBinding` are identical."** No. `setAllowedFields` defines a whitelist for property binding; `setDeclarativeBinding(true)` (6.1+) enforces that only declared binding paths—constructor binding and allowed property binding—are applied.

**"A custom Converter handles all JSON."** No. JSON `@RequestBody` goes through HTTP message converters and the JSON mapper; the conversion service serves other applicable binding paths.

**"Deprecated means the method is already deleted."** No. Check the deprecation message, removal schedule, and target version Javadoc.

**"Within the same minor version, patches never change behavior."** Not guaranteed. A patch can fix bugs or adjust behavior. When reproducing issues, record the full X.Y.Z version.

**"Changing `javax` imports to `jakarta` completes the upgrade."** False. Runtime, provider, servlet stack, dependency graph, and integration tests must all be compatible.

## 14. Final Checklist and Reference Links

For every question asking "Does this API/behavior change across versions?", be able to answer:

1. **Which exact library?** Full package/class/method and the artifact containing it.
2. **What is the real version?** Dependencies resolved at compile time and runtime; accompanying Boot/JDK/provider.
3. **Are the docs for the right version?** Javadoc `@since`, deprecation, Reference, release notes, upgrade guide.
4. **What kind of change is it?** Signature, annotation, default, exception, binding/validation order, behavior, or dependency.
5. **What is the runtime evidence?** Input, command, test, and actual output on each version.
6. **Which code paths are affected?** `DataBinder`/`@ModelAttribute`, MVC method validation, JSON deserializer, or service-layer validation.
7. **Have regression tests run?** Success, mismatch, constraint, field whitelist, HTTP response, locale, and JSON/form separation.
8. **Are the limits of the conclusion noted?** Aspects depending on custom configuration and patch versions.

Authoritative sources to consult for this lesson:

- [Spring Framework – Validation, Data Binding and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring Framework – Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC – Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring MVC – Model Attribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC – InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.1.0 DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.x Upgrade Guide](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)
- [Spring Boot – Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Framework GitHub tags](https://github.com/spring-projects/spring-framework/tags)

Mastering this lookup workflow lets you investigate errors and upgrade the Framework with solid evidence: **pin versions, check API contracts, cross-check changes, verify with fixed inputs, and only then modify code or configuration**.