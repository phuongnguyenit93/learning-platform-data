# ParameterNameProvider and Parameter Names in Jakarta Bean Validation Results

## Objectives

When a constraint placed on a method or constructor parameter is violated, the reader of the result needs to know **which parameter failed**. This article explains the `jakarta.validation.ParameterNameProvider` infrastructure, where parameter names appear in `ConstraintViolation.getPropertyPath()`, the difference between real names and `arg0`/`arg1`, how to configure a custom provider, and its relationship with Spring Framework.

After this lesson, you will be able to:

- Describe accurately the two methods of `ParameterNameProvider` and its thread-safety requirements.
- Explain why compiling Java with `-parameters` affects names in violations.
- Read `Path.ParameterNode.getName()` and `getParameterIndex()` without manually parsing path strings.
- Write a custom provider with a safe fallback, configure it when building a `ValidatorFactory`, and observe results on both methods and constructors.
- Distinguish Jakarta Validation parameter names from HTTP parameter names, DTO property names, and Spring's parameter name discovery mechanism.

## 1. The problem: which parameter failed?

Suppose we have a method:

~~~java
public void reserve(@NotBlank String customerId, @Min(1) int seats) {
    // Business logic
}
~~~

If an intended call has `customerId = ""` and `seats = 0`, both parameters violate their constraints. Bean Validation can produce two `ConstraintViolation`s, each containing a `Path` leading to the error location.

Two ways this may be displayed:

~~~text
reserve.customerId
reserve.seats
~~~

or, if real name metadata is absent from bytecode:

~~~text
reserve.arg0
reserve.arg1
~~~

Here `arg0` and `arg1` are synthetic names by **parameter position, starting at 0**. The name in the path is supplied by `ParameterNameProvider`. The `@NotBlank`/`@Min` constraints and the validated values remain the same; only the name identification in the result changes.

**Prerequisite:** method/constructor validation must already be active. Simply placing `@NotBlank` on a parameter and calling a Java method directly **does not automatically invoke** Bean Validation. In Java SE we use `ExecutableValidator`; in Spring, use the appropriate method validation integration.

## 2. The ParameterNameProvider API

Jakarta Validation interface:

~~~java
package jakarta.validation;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.List;

public interface ParameterNameProvider {
    List<String> getParameterNames(Constructor<?> constructor);
    List<String> getParameterNames(Method method);
}
~~~

Both overloads take a reflection object describing an executable and return a list of names in **exact declaration order**:

| Method | Input object | Result for two parameters |
| --- | --- | --- |
| `getParameterNames(Method)` | Method processed by the validation engine | `["customerId", "seats"]` |
| `getParameterNames(Constructor<?>)` | Constructor processed by the validation engine | `["customerId", "seats"]` |

Contract to follow:

1. The name list must match the **count and order** of the executable's parameters. For a zero-argument executable, return an empty list. Never return `null`.
2. Every position must have a valid name; do not reorder or omit a parameter just because it has no annotations.
3. Implementations must be **thread-safe**: the provider/validator may call it repeatedly or concurrently from multiple threads.
4. Results should stay stable for the same `Method`/`Constructor`, independent of requests or user data.
5. When no custom naming rule applies, **delegate to the default provider** instead of guessing names for every executable.

The returned names are for violation reporting. `ParameterNameProvider` **does not** rename parameters in bytecode, names in Java signatures, DTO field names, or values passed into the method.

### Scope of impact

- **Affected:** `ElementKind.PARAMETER` in `ConstraintViolation.getPropertyPath()` when validating constraints on method/constructor parameters.
- **Unchanged:** method names, constructor names, parameter indices, bean properties in field/property validation, or the `<return value>` node of return-value constraints.
- **Separate concern:** parameter metadata in Spring MVC request binding and key names in JSON requests.

For example, `@NotBlank` on `reserve(String customerId, ...)` creates a parameter node; `@NotBlank` on field `OrderRequest.customerId` creates a property node. This article's provider addresses the **parameter node** case.

## 3. Where does the default provider get names?

According to Jakarta Validation, the default implementation must match Java reflection behavior: reading `Executable.getParameters()` and `Parameter.getName()`. When class files carry parameter name information, the result is the declared name; when that information is missing, Java reflection returns synthetic names `arg0`, `arg1`, and so on.

Java compiler flag:

~~~bash
javac -parameters -d out Example.java
~~~

The `-parameters` flag embeds parameter name metadata into the class file so Java reflection can read it. The `-g` flag for debug information **is not** equivalent to `-parameters` for Java reflection. In Maven/Gradle, ensure the compiler configuration is applied to the **module declaring the method/constructor being validated**, not only to the module calling it.

You can inspect metadata yourself with Java reflection:

~~~java
for (java.lang.reflect.Parameter p : method.getParameters()) {
    System.out.println(p.getName() + " | present=" + p.isNamePresent());
}
~~~

With `-parameters` and a method having `customerId`, `seats`, the output is:

~~~text
customerId | present=true
seats | present=true
~~~

If the class is recompiled **without** this metadata, Java reflection typically returns:

~~~text
arg0 | present=false
arg1 | present=false
~~~

`isNamePresent()` distinguishes real names stored by the compiler from synthetic names. Java names in source code do not automatically exist in bytecode; you must inspect the **actual compiled artifact**, especially when using external dependencies.

Some frameworks/providers have alternative name sources (such as metadata/annotations or specialized bytecode readers), but the **portable default behavior** is reflection. If you want names different from reflection, configure a custom `ParameterNameProvider`.

## 4. How are names recorded in ConstraintViolation?

When method parameter validation fails, the path contains nodes of the corresponding kind (`ElementKind`). For the `reserve` example, a typical path is:

~~~text
MethodNode(name="reserve")
    -> ParameterNode(name="customerId", index=0)
~~~

When real names are missing, `ParameterNode.name` may become `arg0` while `index=0` **remains unchanged**.

Key APIs:

~~~java
ConstraintViolation<?> violation = /* violation returned by validation */;
Path path = violation.getPropertyPath();

for (Path.Node node : path) {
    if (node.getKind() == ElementKind.PARAMETER) {
        Path.ParameterNode parameter =
                node.as(Path.ParameterNode.class);
        String name = parameter.getName();
        int index = parameter.getParameterIndex();
        // name: "customerId" (or "arg0")
        // index: 0
    }
}
~~~

This is an **illustrative snippet**, not a standalone program. When writing machine-consumable code, rely on `ElementKind.PARAMETER` and `getParameterIndex()`. `Path.toString()` is useful for logging/debugging, but Jakarta Validation defines it as a human-readable representation; applications should not depend on its exact string format to extract names via `split(".")`.

Besides name/index, a violation also provides `getMessage()`, `getMessageTemplate()`, `getInvalidValue()`, and `getConstraintDescriptor()`. The provider changes the name **on the path**; it does not automatically change `message` content or message language unless a presentation layer explicitly combines the path with the message.

## 5. Java 17+ example: default provider and custom provider

The example below demonstrates both overloads of `ParameterNameProvider`, contrasts default names with custom names, and checks method/constructor errors via the Jakarta Validation API. No Spring container is needed to verify it.

We have one Java file: `src/main/java/com/example/validation/Demo.java`.

~~~java
package com.example.validation;

import jakarta.validation.Configuration;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ElementKind;
import jakarta.validation.ParameterNameProvider;
import jakarta.validation.Path;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.stream.Collectors;

public final class Demo {

    public static final class BookingService {
        public void reserve(
                @NotBlank String customerId,
                @Min(1) int seats) {
            // No invocation is needed for this validation demo.
        }
    }

    public static final class BookingRequest {
        public BookingRequest(
                @NotBlank String customerId,
                @Min(1) int seats) {
            // Constructor parameters carry the constraints.
        }
    }

    // An immutable, thread-safe wrapper around the standard provider.
    public static final class FriendlyParameterNames
            implements ParameterNameProvider {

        private final ParameterNameProvider delegate;

        public FriendlyParameterNames(ParameterNameProvider delegate) {
            this.delegate = delegate;
        }

        @Override
        public List<String> getParameterNames(Method method) {
            if (method.getDeclaringClass() == BookingService.class
                    && method.getName().equals("reserve")
                    && method.getParameterCount() == 2) {
                return List.of("clientCode", "seatCount");
            }
            return delegate.getParameterNames(method);
        }

        @Override
        public List<String> getParameterNames(
                Constructor<?> constructor) {
            if (constructor.getDeclaringClass()
                    == BookingRequest.class
                    && constructor.getParameterCount() == 2) {
                return List.of("clientCode", "seatCount");
            }
            return delegate.getParameterNames(constructor);
        }
    }

    private static void printParameterErrors(
            String label,
            Set<? extends ConstraintViolation<?>> violations) {

        Map<Integer, String> byIndex = new TreeMap<>();

        for (ConstraintViolation<?> violation : violations) {
            for (Path.Node node : violation.getPropertyPath()) {
                if (node.getKind() == ElementKind.PARAMETER) {
                    Path.ParameterNode parameter =
                            node.as(Path.ParameterNode.class);
                    byIndex.put(
                            parameter.getParameterIndex(),
                            parameter.getName());
                }
            }
        }

        String summary = byIndex.entrySet().stream()
                .map(entry -> entry.getKey() + ":"
                        + entry.getValue())
                .collect(Collectors.joining(", "));

        System.out.println(label + " -> " + summary);
    }

    private static void runChecks(
            String label,
            Validator validator,
            Method method,
            Constructor<BookingRequest> constructor) {

        BookingService service = new BookingService();
        Object[] invalidArguments = {"", 0};

        var executableValidator = validator.forExecutables();

        Set<ConstraintViolation<BookingService>> methodErrors =
                executableValidator.validateParameters(
                        service, method, invalidArguments);

        Set<ConstraintViolation<BookingRequest>> constructorErrors =
                executableValidator.validateConstructorParameters(
                        constructor, invalidArguments);

        printParameterErrors(label + " method", methodErrors);
        printParameterErrors(label + " constructor", constructorErrors);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Method method = BookingService.class.getMethod(
                "reserve", String.class, int.class);

        Constructor<BookingRequest> constructor =
                BookingRequest.class.getConstructor(
                        String.class, int.class);

        try (ValidatorFactory defaultFactory =
                     Validation.buildDefaultValidatorFactory()) {
            runChecks(
                    "default",
                    defaultFactory.getValidator(),
                    method,
                    constructor);
        }

        Configuration<?> configuration =
                Validation.byDefaultProvider().configure();

        ParameterNameProvider fallback =
                configuration.getDefaultParameterNameProvider();

        try (ValidatorFactory customFactory = configuration
                .parameterNameProvider(
                        new FriendlyParameterNames(fallback))
                .buildValidatorFactory()) {
            runChecks(
                    "custom",
                    customFactory.getValidator(),
                    method,
                    constructor);
        }
    }
}
~~~

### 5.1. Analyzing the key points

1. `@NotBlank` and `@Min(1)` are placed on **method parameters** and **constructor parameters**. Both validation calls receive `Object[]{"", 0}`, so both positions produce errors.
2. `validateParameters(service, method, args)` validates method parameters. `validateConstructorParameters(constructor, args)` validates constructor parameters. Both belong to `Validator.forExecutables()`; they **do not require** invoking the method or instantiating the object.
3. `FriendlyParameterNames` uses exact reflection types and accepts the default `ParameterNameProvider` as a delegate. For the targeted executables, it returns `clientCode`/`seatCount`; for all other executables, it falls back.
4. `List.of(...)` is an immutable list; `delegate` is a `final` field. There are no mutable maps or request state in the provider. This satisfies thread-safety requirements, assuming the delegate also honors the contract.
5. `TreeMap<Integer,String>` sorts **by parameter position**, avoiding dependence on the unguaranteed iteration order of `Set<ConstraintViolation<?>>`.
6. The printing logic reads names directly from `Path.ParameterNode`; it does not rely on dots or the full string syntax of `getPropertyPath().toString()`.

### 5.2. Maven configuration for -parameters and running the demo

Create `pom.xml` at the project root:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>parameter-names-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.3.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Run with JDK 17+ and Maven:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=com.example.validation.Demo
~~~

Lines **printed by `Demo`**, excluding logs that Maven or the validation provider may emit:

~~~text
default method -> 0:customerId, 1:seats
default constructor -> 0:customerId, 1:seats
custom method -> 0:clientCode, 1:seatCount
custom constructor -> 0:clientCode, 1:seatCount
~~~

If you remove `<parameters>true</parameters>` and **clean and recompile** without another name metadata source, the `default` lines typically become `0:arg0, 1:arg1`. The two `custom` lines still use the names we provided.

Version note: Hibernate Validator **8.x** uses Jakarta Validation **3.0**, compatible with Java 17 and Spring Boot 3.x. The `ParameterNameProvider` contract used in the example is present in both Jakarta Validation 3.0 and 3.1. When switching to another provider/version, check the project's compatibility matrix and dependency management.

### 5.3. Why provide a fallback?

A real application has many methods/constructors, including ones declared by external libraries. If a custom provider always returns the same two names for **every** method, executables with 0, 1, or 3 parameters will receive mismatched metadata; the engine may raise configuration errors instead of useful violations.

Safe structure:

~~~java
@Override
public List<String> getParameterNames(Method method) {
    if (/* exact class/method/signature with custom convention */) {
        return List.of(/* one name per parameter */);
    }
    return delegate.getParameterNames(method);
}
~~~

This is an **illustrative snippet** extracted from the class above, not standalone compilable code. In projects with overloads, inherited methods, interfaces, and proxies, check the signature precisely enough; matching only `"reserve"` can collide with overloads. Any lookup based on declared names/annotations must have deterministic, testable rules.

## 6. Where is ParameterNameProvider configured?

### 6.1. Jakarta Validation bootstrap

The portable approach is customizing `Configuration` before building `ValidatorFactory`:

~~~java
Configuration<?> config =
        Validation.byDefaultProvider().configure();

ParameterNameProvider defaultProvider =
        config.getDefaultParameterNameProvider();

ValidatorFactory factory = config
        .parameterNameProvider(
                new FriendlyParameterNames(defaultProvider))
        .buildValidatorFactory();

try {
    Validator validator = factory.getValidator();
    // Use validator.forExecutables() here.
} finally {
    factory.close();
}
~~~

This is an **excerpt** based on `Demo.FriendlyParameterNames` declared above, not runnable standalone. Choose the provider before creating the factory, because `Validator` instances produced by the factory inherit the factory's configuration. Beyond the Java API, Jakarta Validation can configure a provider via `META-INF/validation.xml`; use the exact namespace/schema matching your runtime version and ensure there are no duplicate config files.

Depending on the use case, Jakarta Validation also offers `ValidatorContext.parameterNameProvider(...)` to customize a `Validator` obtained from a factory. If consistent application-wide behavior is needed, factory-level configuration is usually easier to manage.

### 6.2. Spring Framework and LocalValidatorFactoryBean

Spring Framework 6.x integrates Jakarta Validation via `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean`, bridging Spring's `Validator` API and Jakarta's `ValidatorFactory`. A Spring MVC application with a Bean Validation provider on the classpath typically registers a validator bean used for `@Valid` / `@Validated`.

`LocalValidatorFactoryBean` provides the method:

~~~java
void setParameterNameDiscoverer(
        org.springframework.core.ParameterNameDiscoverer discoverer)
~~~

This method lets Spring configure how parameter names are discovered when needed. `org.springframework.core.DefaultParameterNameDiscoverer` can be used. Example configuration bean when the application **explicitly owns** validation configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.DefaultParameterNameDiscoverer;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
class ValidationConfig {

    @Bean
    LocalValidatorFactoryBean validator() {
        LocalValidatorFactoryBean bean =
                new LocalValidatorFactoryBean();

        bean.setParameterNameDiscoverer(
                new DefaultParameterNameDiscoverer());

        return bean;
    }
}
~~~

This is a Spring integration snippet, not combined into the standalone `Demo` program. In Spring Boot, inspect existing beans/auto-configuration before redefining the validator: declaring an extra `LocalValidatorFactoryBean` can change how the application selects its validator, message source, or other customizations. On Spring Framework 6, `DefaultParameterNameDiscoverer` primarily leverages Java reflection for Java (and may support Kotlin where applicable); it cannot guarantee recovering real Java names if class files lack `-parameters` metadata.

**Do not confuse the two SPIs:**

| API | Ecosystem | Role |
| --- | --- | --- |
| `jakarta.validation.ParameterNameProvider` | Jakarta Validation | Provides names for method/constructor parameters in violation paths |
| `org.springframework.core.ParameterNameDiscoverer` | Spring Core | Discovers parameter names for Spring infrastructure; can be used by Spring's adapter for Jakarta Validation |
| `org.springframework.validation.Validator` | Spring | Validates target objects and records errors in `Errors` |
| `jakarta.validation.Validator` | Jakarta Validation | Validates beans/executables and returns `ConstraintViolation` |

If you specifically need a **custom `ParameterNameProvider`** inside Spring, verify that the final `ValidatorFactory` configuration actually uses that provider. Do not assume that Java SE `Validation.buildDefaultValidatorFactory()` and Spring-managed `LocalValidatorFactoryBean` use the same factory or the same naming strategy.

### 6.3. Names in HTTP responses are not necessarily Jakarta violation names

Consider a Spring MVC controller:

~~~java
@GetMapping("/bookings")
public String find(@RequestParam("customer") String id) {
    return id;
}
~~~

`"customer"` is the **HTTP query parameter name** specified by `@RequestParam`; `id` is the Java parameter name. These are two different name sources. Binding errors, `MethodArgumentNotValidException`, and `HandlerMethodValidationException` each have their own Spring MVC handling structures. Do not promise that changing `ParameterNameProvider` will automatically change every key in Spring's HTTP error JSON.

In method validation mechanisms, Spring or a proxy/interceptor may invoke Jakarta's `ExecutableValidator` and produce `ConstraintViolation`s. In that case `ParameterNameProvider` affects the `PARAMETER` node name. However, the application still decides how to map errors to the API response. If clients rely on stable `field` or `parameter` fields, design an explicit error contract instead of exposing raw `Path.toString()` as a public identifier.

## 7. Constructors, return values, cascading, and container elements

`ParameterNameProvider` has an overload for **constructors** because constraints can be placed directly on constructor parameters:

~~~java
public BookingRequest(
        @NotBlank String customerId,
        @Min(1) int seats) {
    // ...
}
~~~

`ExecutableValidator.validateConstructorParameters(...)` creates violations whose path traverses a constructor node and a parameter node. For return-value constraints such as `@NotNull` on a return value, the path has an `ElementKind.RETURN_VALUE` node with the conventional name `<return value>`; the parameter name provider is not used to rename that node.

For an object parameter annotated with `@Valid` that has an invalid nested field, the path can continue from the parameter node to a property node, such as:

~~~text
reserve.request.customerId
~~~

`request` (parameter node) comes from `ParameterNameProvider`, while `customerId` (property node) is the bean property name. With container element constraints, the path can contain additional nodes and element indices/keys. Therefore, the entire path cannot be treated as simply a single parameter name.

For **cross-parameter constraints** (rules evaluating multiple parameters together), the standard defines a `CROSS_PARAMETER` node named `<cross-parameter>`. This node is distinct from individual `ParameterNode`s; to attach an error to a specific parameter, the constraint validator must construct the corresponding error path. `ParameterNameProvider` does not automatically split one cross-parameter violation into multiple separate errors.

## 8. Common errors and diagnostics

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Path displays `arg0`, `arg1` | Bytecode lacks Java parameter names | Enable `-parameters` in the module declaring the method, clean rebuild, verify via reflection |
| Java names correct locally but different on CI | Different compiler configuration or artifacts | Check compiler flags and `isNamePresent()` on the actual artifact |
| No violations despite invalid parameters | Method validation not enabled | Use `ExecutableValidator` or Spring's validation interception mechanism |
| Custom provider has no effect | Factory/validator created before configuration, or Spring uses another factory | Identify the active `ValidatorFactory` instance and attach the provider at bootstrap |
| Returned names are shifted | Name list has wrong order/length | Return names aligned with executable's parameter indices; fall back for other executables |
| Flaky tests with multiple errors | Relying on `Set<ConstraintViolation>` order | Read `ParameterNode.getParameterIndex()` and sort by index |
| Exception when provider fetches names | Runtime error in custom provider or invalid metadata | Inspect the `ValidationException` stack trace and check naming rules |
| HTTP API errors still show old names | Spring MVC builds error responses per binding/method validation rules | Inspect the application's error converter and separate HTTP names from parameter names |
| Wrong results under multithreading | Mutable cache or provider field mutated | Use an immutable/thread-safe implementation; avoid per-request state |

### Quick debugging workflow

1. Confirm the trigger point: `Validator.forExecutables().validateParameters(...)` or method-validation integration actually ran.
2. Check the exact reflection method/constructor and signature being used, especially with proxies/interfaces/overloads.
3. Use `Executable.getParameters()`, `Parameter.getName()`, and `isNamePresent()` to inspect real names in bytecode.
4. Confirm which provider `ValidatorFactory.getParameterNameProvider()` or the Spring configuration path is using.
5. Print each `Path.Node` including `getKind()`/`getName()`; for `PARAMETER`, also read `getParameterIndex()` to confirm accurate mapping.
6. In tests, compare names and positions explicitly, and check constraint message content separately. Do not rely on iteration order or full path string formatting.

## 9. Exercises and self-check criteria

**Exercise 1 — Predict the output:** For `reserve(@NotBlank String customerId, @Min(1) int seats)` with arguments `["", 0]`, when the compiler does not enable `-parameters`, what names will the default provider yield? Per default rules: `arg0` and `arg1`. Their respective indices remain `0` and `1`. If only `seats=2`, only the error at index `0` remains.

**Exercise 2 — Add an overload:** Add `reserve(String customerId)`. Modify the custom provider so that only the two-parameter method uses `clientCode`/`seatCount`, while the one-parameter overload uses the fallback. Explain why matching `"reserve"` by name alone is insufficient.

**Exercise 3 — Constructor:** Add a zero-argument constructor to `BookingRequest`. Why must the provider return an empty list for that constructor? Check `getParameterCount()` to ensure the name list cannot get out of alignment.

**Exercise 4 — Separate concepts:** In controller `find(@RequestParam("customer") String id)`, which is the HTTP query parameter name, and which is the Java method parameter name? Why does changing `ParameterNameProvider` not rename `"customer"` to `"id"` in the URL?

**Exercise 5 — Automated test:** Write a test that builds `ValidatorFactory` under both default and custom configurations, calls `validateParameters()`, and verifies a violation with `ParameterNode.getParameterIndex()==0` has names `customerId` and `clientCode` respectively. Do not compare the entire `Set` by iteration order.

**Key takeaway:** `ParameterNameProvider` is the naming infrastructure for **method/constructor parameters in Jakarta Validation error paths**. By default, names come from Java reflection metadata (`-parameters` preserves source names); a custom provider can alter how they are displayed, provided it preserves order, is thread-safe, and falls back safely. When consuming results, indices from `Path.ParameterNode` are more reliable than manually parsing path strings.

## References

- [Jakarta Validation 3.1 — Naming parameters and ConstraintViolation paths](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html)
- [Jakarta Validation 3.1 — ParameterNameProvider API](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/ParameterNameProvider.html)
- [Hibernate Validator 8 — Reference Guide, Configuration / ParameterNameProvider](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/)
- [Spring Framework 6.2 — LocalValidatorFactoryBean API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring Framework — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
