# `@Named`, `@Qualifier`, and the Support Scope of the Jakarta Standard

## 1. Three Annotation Names to Distinguish

Spring Framework 6 supports a set of **Jakarta Dependency Injection (JSR-330)** annotations in the `jakarta.inject` package alongside Spring's own annotations. Using standard annotations can make consumer classes less coupled to Spring APIs, yet that does not mean every capability of the Core Container belongs to Jakarta DI.

- **`jakarta.inject.Named`**: names a component or specifies the candidate to inject by name, such as `@Named("upperPort")`.
- **`jakarta.inject.Qualifier`**: a **meta-annotation** for defining custom qualifiers (`@Fast`, `@Offline`). It does not accept a String value with `@Qualifier("upperPort")` syntax.
- **`org.springframework.beans.factory.annotation.Qualifier`**: **Spring's own** annotation used directly at an injection point, which can accept a string such as `@Qualifier("upperPort")`.

To understand how objects are selected, you also need to know that `jakarta.inject.Inject` is the annotation marking injection points and `jakarta.inject.Provider<T>` handles on-demand lookup.

~~~text
                    Spring ApplicationContext
                        |
    +-------------------+------------------+
    |                   |                  |
@Named("upperPort") @Named("lowerPort") @Named("textService")
  UpperPort           LowerPort             TextService
    |                   |                        |
    +------ TextPort ----+              @Inject constructor
                                             |
                             @Named("upperPort") TextPort
                             Provider<RequestToken>
                                             |
                                   call process(text)
                                             |
                               Provider.get() fetches token
                               UpperPort.format(text)
~~~

Without an explicit selection rule, two beans both implementing `TextPort` can make a `TextPort` injection point ambiguous. `@Named("upperPort")` on the parameter resolves the selection **right at the consumer point**.

## 2. `@Named` on a Bean and on an Injection Point

### On a Class: Assigning a Bean Name

~~~java
import jakarta.inject.Named;

@Named("upperPort")
public class UpperPort implements TextPort {
    // Must implement all methods of TextPort.
}
~~~

This is an **illustrative snippet**, not runnable yet because the `TextPort` definition and methods are omitted. In Spring, a class carrying `@Named` can be detected by component scanning much like `@Component`. If no name is specified inside `@Named`, Spring can apply its bean name generation mechanism.

**Important:** simply placing an annotation on a class **does not automatically make the class appear in every container**. Spring must be configured to component-scan the right package, or register the class explicitly via `context.register(...)`, or have a corresponding bean definition.

### On a Parameter: Narrowing Candidates

~~~java
import jakarta.inject.Inject;
import jakarta.inject.Named;

@Inject
public TextService(@Named("upperPort") TextPort port) {
    this.port = port;
}
~~~

This is also an illustrative snippet. `@Named("upperPort")` here states that the parameter requires a bean compatible with `TextPort` and matching the `upperPort` name/qualifier. It neither creates an extra instance nor modifies the other bean named `lowerPort`.

If the actual candidate's name is `primaryUpperPort` yet the injection writes `upperPort`, Spring may report a missing dependency. When changing a bean name, update places requesting that name or design a more abstract qualifier.

### `@Named` Differs from Java Class Name

`UpperPort` is the class name; `upperPort` is the bean name in the container. One class can be registered under multiple distinct bean definitions; conversely, a bean definition with an explicit name need not match the class name. `@Named` relies on name/qualifier configuration, rather than picking the "first" implementation by declaration order.

## 3. Jakarta `@Qualifier` Is a Meta-Annotation

A custom qualifier with business meaning is `@Fast`. Create `Fast.java`:

~~~java
package demo;

import jakarta.inject.Qualifier;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Qualifier
@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.TYPE,
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.METHOD
})
public @interface Fast {}
~~~

This is an **illustrative annotation definition file**, not a required part of the runnable application in section 7. `@Qualifier` in the import is `jakarta.inject.Qualifier` and sits on the **`Fast` declaration**. Runtime retention allows the container to read the annotation when resolving dependencies.

It can be used as:

~~~java
@Fast
@Named("fastPort")
class FastPort implements TextPort {
    // ...
}

@Inject
public SomeService(@Fast TextPort port) {
    this.port = port;
}
~~~

These two blocks **do not compile standalone** because types, methods, and bean registrations must be declared. When the container supports custom qualifiers, a candidate marked `@Fast` can be selected for a parameter with the same qualifier.

**Wrong:**

~~~java
// Invalid with jakarta.inject.Qualifier:
// @jakarta.inject.Qualifier("fastPort")
~~~

Jakarta's `Qualifier` annotation has no String `value()` attribute. To select by a String name, use `@Named("fastPort")`. To create a custom qualifier, define your own annotation with `@Qualifier` as a meta-annotation.

## 4. Spring `@Qualifier` Differs from Jakarta `@Qualifier`

Example using Spring's own annotation:

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;

@Autowired
public SomeService(@Qualifier("upperPort") TextPort port) {
    this.port = port;
}
~~~

This is an illustrative snippet. In this file, `@Qualifier("upperPort")` is **Spring Qualifier**, not Jakarta's. Both annotations share the same simple name, so if both are needed in the same Java source file, you must use the **fully qualified name** for at least one of them to avoid an import collision.

| Intent | Jakarta DI | Spring |
| --- | --- | --- |
| Select candidate named `upperPort` | `@Named("upperPort")` | `@Qualifier("upperPort")` |
| Define marker `@Fast` | Meta `@jakarta.inject.Qualifier` | Meta `@org.springframework.beans.factory.annotation.Qualifier` |
| Supply dependency | `@Inject` | `@Autowired` |
| Bean name / stereotype | `@Named` | `@Component` and related stereotypes |

**Qualifier correctness depends on how beans are registered.** Do not assume `@Primary` will override a specific qualifier requirement or that a mismatched `@Named` will be fixed automatically. Selecting among multiple candidates requires consistent configuration and tests.

## 5. How Far Does `@Inject` Replace `@Autowired`?

`@Inject` can be processed by Spring on constructor, field, and method injection points:

~~~java
import jakarta.inject.Inject;

@Inject
public void setInventory(InventoryPort inventory) {
    this.inventory = inventory;
}
~~~

The snippet requires `InventoryPort` and the field if compiled. When the bean is managed by Spring, the container finds a matching bean and applies injection at configuration time.

| Feature | Spring's `@Autowired` | Jakarta `@Inject` |
| --- | --- | --- |
| Constructor injection | Yes | Yes |
| Field injection | Yes | Yes |
| Method injection | Yes | Yes |
| `required=false` on annotation | Yes | **No** |
| `Optional<T>` at injection point in Spring | Yes | Yes thanks to Spring integration |
| Is `new` outside container autowired automatically? | No | No |

Syntax error:

~~~java
// Not supported:
// @Inject(required = false)
~~~

`jakarta.inject.Inject` defines no `required` attribute. If a dependency is optional in Spring, one solution is:

~~~java
@Inject
public void setMetrics(java.util.Optional<MetricsPort> metrics) {
    this.metrics = metrics;
}
~~~

This is illustrative only. Spring can pass `Optional.empty()` if no matching candidate exists. Spring's ability to handle `Optional<T>` **does not mean all DI containers must have identical semantics**.

When a bean class has only one constructor, modern Spring Framework can typically use that constructor even without writing `@Autowired` or `@Inject`, provided the bean is registered and dependencies resolve properly. Still, `@Inject` can make DI intent more explicit.

## 6. `Provider<T>` and the Target Bean's Scope

`jakarta.inject.Provider<T>` is a standard API for deferring **requesting a target bean** until `get()` is called.

~~~java
private final Provider<RequestToken> tokens;

@Inject
public TextService(Provider<RequestToken> tokens) {
    this.tokens = tokens;
}

public RequestToken nextToken() {
    return tokens.get();
}
~~~

Illustrative example only, missing fields/imports/classes if taken standalone. In Spring:

- A Provider for a **singleton** typically returns the same instance across multiple `get()` calls.
- A Provider for a **prototype** can return a new instance on each `get()` call.
- A target missing a bean, having multiple ambiguous beans, or failing bean creation can throw an exception **when `get()` is called**.
- Spring's `ObjectProvider<T>` provides additional APIs like `getIfAvailable()` and `stream()`, which are not fully present in Jakarta's `Provider<T>`.

**Provider does not change scope.** It only changes how/when a dependency is requested. Therefore, the runnable example deliberately attaches Spring's `@Scope("prototype")` to the `RequestToken` bean.

### `@Singleton` and Default Scope

Jakarta `@Singleton` describes a standard scope, yet **in Spring** beans registered via `@Named` still default to **singleton per bean definition within each container** unless configured otherwise. This is not a single global singleton across the whole JVM. Do not infer from another DI runtime's defaults that Spring `@Named` defaults to prototype.

In Spring, to get prototype scope use `@Scope("prototype")` or bean definition metadata. `jakarta.inject.Scope` is a **meta-annotation** used to create custom scope annotations; it does not automatically put a bean into request/prototype scope.

## 7. Complete Runnable Java 17 / Spring Framework 6.2 Program

The example has two implementations of a `TextPort` interface, using `@Named` to identify and inject exactly one implementation. `TextService` also receives `Provider<RequestToken>` to verify a fresh prototype object on each processing call. No Spring Boot, server, or database.

### 7.1. Structure and `pom.xml`

Requires JDK 17+, Maven:

~~~text
jakarta-named-demo/
├── pom.xml
└── src/main/java/demo/JakartaNamedDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>jakarta-named-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>jakarta.inject</groupId>
            <artifactId>jakarta.inject-api</artifactId>
            <version>2.0.0</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.JakartaNamedDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.2. Source `JakartaNamedDemo.java`

~~~java
package demo;

import jakarta.inject.Inject;
import jakarta.inject.Named;
import jakarta.inject.Provider;

import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public final class JakartaNamedDemo {
    private JakartaNamedDemo() {}

    public interface TextPort {
        String format(String input);
    }

    @Named("upperPort")
    public static final class UpperPort implements TextPort {
        @Override
        public String format(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }

    @Named("lowerPort")
    public static final class LowerPort implements TextPort {
        @Override
        public String format(String input) {
            return input.toLowerCase(Locale.ROOT);
        }
    }

    public record RequestToken(int number) {}

    @Named("textService")
    public static final class TextService {
        private final TextPort port;
        private final Provider<RequestToken> tokens;

        @Inject
        public TextService(@Named("upperPort") TextPort port,
                           Provider<RequestToken> tokens) {
            this.port = Objects.requireNonNull(port);
            this.tokens = Objects.requireNonNull(tokens);
        }

        public String process(String input) {
            RequestToken token = tokens.get();
            return token.number() + ":" + port.format(input);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        private final AtomicInteger counter = new AtomicInteger();

        @Bean
        @Scope("prototype")
        public RequestToken requestToken() {
            return new RequestToken(counter.incrementAndGet());
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // Explicit registration: @ComponentScan is not needed.
            context.register(AppConfig.class,
                    UpperPort.class, LowerPort.class, TextService.class);
            context.refresh();

            TextService service = context.getBean(TextService.class);
            System.out.println("PORT_COUNT "
                    + context.getBeanNamesForType(TextPort.class).length);
            System.out.println("FIRST " + service.process("Hello"));
            System.out.println("SECOND " + service.process("Java"));
            System.out.println("LOWER "
                    + context.getBean("lowerPort", TextPort.class)
                             .format("SpRiNg"));
            System.out.println("SAME "
                    + (service == context.getBean(TextService.class)));
        }
    }
}
~~~

The nested classes here are `public static`, so they can be registered explicitly via `register(...)`. `@Named("upperPort")` and `@Named("lowerPort")` let Spring name the two beans; `@Inject` on the constructor requests the `upperPort` candidate. `AppConfig` creates a prototype token using Spring's own scope annotation.

### 7.3. Run and Stdout

In the `jakarta-named-demo` directory:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

Direct `javac/java` would need a classpath containing the Spring and Jakarta dependency JARs. Thus using Maven to resolve dependencies and run the application is the cleaner, more direct approach in this example; `maven.compiler.release=17` requests Java 17-compatible compilation.

**Stdout lines printed by the program:**

~~~text
PORT_COUNT 2
FIRST 1:HELLO
SECOND 2:JAVA
LOWER spring
SAME true
~~~

Maven and the JVM may print other info/logs; the block above contains only the lines intentionally emitted by `System.out.println`.

### 7.4. Why Does That Output Occur?

1. `context.register` registers `AppConfig` and the three classes, then `refresh` processes the bean definitions.
2. `getBeanNamesForType(TextPort.class).length` equals **2** because two distinct beans implement the same interface.
3. `TextService` receives `upperPort` thanks to the `@Named("upperPort")` qualifier on the parameter, avoiding ambiguity with `lowerPort`.
4. `process("Hello")` requests a token via `Provider.get()`. The `RequestToken` bean is prototype; the first call gets ID 1, and `UpperPort` returns `HELLO`.
5. On the second call, the provider requests a new token ID 2, and `UpperPort` returns `JAVA`.
6. `getBean("lowerPort", TextPort.class)` selects the remaining implementation, converting `SpRiNg` to `spring`.
7. `TextService` follows Spring's default singleton scope, so two lookups return the same reference and print `SAME true`.

**Provider does not automatically force creating a new instance every time**; it is `@Scope("prototype")` that causes the factory to create a fresh `RequestToken` each time it is requested.

## 8. How Far Does the Jakarta Standard Support Go and What Is Missing?

| Spring Feature | Jakarta DI Equivalent | Notes |
| --- | --- | --- |
| `@Autowired` | `@Inject` | No `required` attribute |
| `@Component` | `@Named` | Lacks Spring's full composed stereotype model |
| `@Qualifier("beanName")` | `@Named("beanName")` | `jakarta.inject.Qualifier` is only a meta-annotation |
| Custom qualifier annotation | `@jakarta.inject.Qualifier` | Requires a custom annotation with suitable retention and targets |
| `@Scope("singleton")` | `@Singleton` | Spring keeps default singleton when using `@Named` |
| `@Scope("prototype")` | No direct equivalent for Spring prototype | Typically use Spring's `@Scope` |
| `@Lazy` | No direct annotation equivalent | Spring's `@Lazy` or provider |
| `@Value` | No direct annotation equivalent | Spring property configuration |
| `ObjectFactory<T>` | `Provider<T>` | Jakarta provides `get()`; Spring adds extensions |
| `@Profile`/`@Conditional` | Not part of `jakarta.inject` | Requires Spring configuration |

`@Named` does not turn a service into HTTP-scoped or activate AOP, transactions, or retries. Those are features not guaranteed by the Jakarta DI API.

### `jakarta.inject` Differs from `jakarta.annotation`

`@Inject`, `@Named`, `@Qualifier`, `@Singleton`, and `Provider<T>` belong to Jakarta DI/JSR-330. `@PostConstruct`, `@PreDestroy`, and `@Resource` belong to Jakarta Annotations/JSR-250; they are **not** included in `jakarta.inject-api`. When needed, the corresponding dependency, such as `jakarta.annotation-api`, must be added.

### Spring 6 and Legacy `javax.inject`

Older Spring tutorials may import `javax.inject.*`. Examples for Spring Framework 6 should use `jakarta.inject.*` with the matching artifact. Do not swap imports mechanically without checking your Spring version and current dependencies.

### `@Value` or `@Lazy` Do Not Exist in `jakarta.inject`

Spring-specific example:

~~~java
// Spring-only illustration, not Jakarta DI API.
@org.springframework.beans.factory.annotation.Value("${app.title:Demo}")
private String title;
~~~

To keep the domain less coupled to Spring, configuration can be read at the composition root and values passed via constructor, or a validated config object injected. `Provider<T>` is a lazy-lookup tool, **not a replacement** for property placeholder mechanisms.

## 9. Using Custom Qualifiers with Business Meaning

If a system has multiple adapters by role and bean names can easily change, custom qualifiers express meanings like `@Offline` or `@Preferred`. For example:

~~~java
package demo;

import jakarta.inject.Qualifier;
import java.lang.annotation.*;

@Qualifier
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.PARAMETER})
public @interface Offline {}
~~~

This is an illustrative `Offline.java` file, not a runnable file from section 7. Place `@Offline` on the candidate bean and at the injection point, while ensuring matching bean registration and types. Spring supports qualifier metadata marked by Jakarta's meta-annotation.

Do not define dozens of marker qualifiers if they only differ by a simple bean name. Conversely, scattering string names like `@Named("adapter23")` across the domain can hard-couple business code to registry names; consider qualifiers expressing roles or choosing implementations in configuration.

## 10. Typical Errors and Diagnostic Steps

| Problem | How to Fix |
| --- | --- |
| Compiler error importing `jakarta.inject.Inject` | Add the proper `jakarta.inject-api` dependency/classpath |
| `@Named` bean does not exist | Verify package scanning or register the class |
| `@Named("upperPort")` fails to select a bean | Check the actual bean name and type/qualifier |
| Two beans of the same interface cause ambiguity | Specify a clear qualifier or strategy |
| `@jakarta.inject.Qualifier("upperPort")` fails to compile | Jakarta `Qualifier` takes no String; use `@Named` |
| Importing both `Qualifier`s with the same simple name | Use a fully qualified annotation for one of them |
| `@Inject(required=false)` fails to compile | Jakarta Inject has no `required` attribute |
| `Provider.get()` returns the same instance | Target scope is singleton |
| `Provider.get()` throws an exception | Candidate absent, ambiguous, or bean creation failed |
| `@Named` assumed to be prototype | Spring defaults to singleton; use `@Scope` if needed |
| Looking for `@Value` in `jakarta.inject` | Does not exist; use Spring property injection/config |
| Old `javax.inject` does not behave as expected | Check Jakarta migration on Spring 6 |
| Calling `new` and expecting annotations to auto-inject | Let Spring manage/configure the instance |
| Using a custom qualifier yet still picking the wrong bean | Check meta-annotation, runtime retention, target, candidate registration |
| Assuming singleton beans are thread-safe by default | Scope does not provide automatic synchronization |

Diagnostic sequence: check Jakarta dependency → bean registration → candidate name/type → injection qualifier → scope/provider → root cause inside bean creation exception. Do not fix errors by marking every bean `@Primary`.

## 11. Exercises with Answers

**1.** Is `@jakarta.inject.Qualifier("upperPort")` valid?

**Answer:** No. `jakarta.inject.Qualifier` is a meta-annotation; use `@Named("upperPort")` or a custom qualifier like `@Fast`.

**2.** Do `@Named("upperPort")` on a class and on a parameter differ?

**Answer:** On a class it identifies the candidate component; on a parameter it restricts the bean to receive by name/qualifier.

**3.** If `upperPort` and `lowerPort` both implement `TextPort`, does Spring automatically pick the one declared first?

**Answer:** Do not rely on declaration order; if unresolvable, an ambiguity error can occur. Use a qualifier.

**4.** Is `@Inject(required=false)` valid?

**Answer:** No. Jakarta `@Inject` has no `required` attribute. In Spring you can use `Optional<T>` or other optional DI approaches.

**5.** What is the default scope of a `@Named` bean in Spring?

**Answer:** Singleton per bean definition/context, not a JVM-wide global singleton.

**6.** Why do two `Provider.get()` calls in the demo produce numbers 1 and 2?

**Answer:** The target `RequestToken` bean is marked `@Scope("prototype")`; on each request Spring runs the factory method and increments the counter.

**7.** If `RequestToken` is changed to singleton, will the provider still create a new token every time?

**Answer:** No. Provider performs the lookup, while scope determines the instance supplied.

**8.** Is `jakarta.annotation.PostConstruct` inside `jakarta.inject-api`?

**Answer:** No. That belongs to the separate Jakarta Annotations API (JSR-250), distinct from `jakarta.inject`.

**9.** Why does custom `@Offline` need `@Retention(RUNTIME)`?

**Answer:** Qualifier metadata must be present when the container performs resolution. Without retaining the annotation at runtime, metadata readers cannot detect it.

**10.** Does `@Named` completely replace `@Value`, `@Lazy`, and `@Scope`?

**Answer:** No. It only supports simple naming/qualifying/stereotyping, and does not define those Spring features.

**11.** A class carries `@Named` without scanning/registration; will `getBean(Class)` succeed?

**Answer:** You cannot expect it to. The context must have a corresponding registered bean definition.

## 12. Application Checklist

- [ ] Spring Framework 6.x, Java 17+, and `jakarta.inject-api` are declared when using Jakarta DI annotations.
- [ ] Distinguish `jakarta.inject.Named`, `jakarta.inject.Qualifier`, and Spring's `Qualifier`.
- [ ] Named/qualified beans are registered in the right context.
- [ ] Injection point type and name/qualifier match the candidate.
- [ ] Do not write `@jakarta.inject.Qualifier("...")` or `@Inject(required=false)`.
- [ ] When a custom qualifier is needed, define the annotation with the meta qualifier, runtime retention, and proper targets.
- [ ] Use `Provider.get()` when on-demand lookup is truly needed, understanding the target bean's scope.
- [ ] Do not equate provider with prototype.
- [ ] Do not assume every Jakarta implementation shares Spring's exact singleton default.
- [ ] Do not assume Jakarta DI includes `@Value`, `@Lazy`, or Spring profiles/conditions.
- [ ] Distinguish JSR-330 `jakarta.inject` from JSR-250 `jakarta.annotation`.
- [ ] When migrating, verify `javax.inject` vs `jakarta.inject` and actual dependencies.
- [ ] Test multiple candidates of the same type, missing-bean cases, and by-name resolution.
- [ ] Do not rely on scan/definition order to choose dependencies.
- [ ] Separate business logic from arbitrary bean lookups, and do not turn annotations into a place to hide business rules.

### Spring References

- [Using JSR 330 Standard Annotations — Spring 6.2](https://docs.spring.io/spring-framework/reference/6.2/core/beans/standard-annotations.html)
- [Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)

**Conclusion:** Jakarta's `@Named` is used to **identify candidates or select by name**. `jakarta.inject.Qualifier` is solely a meta-annotation for creating custom qualifiers, not Spring's `@Qualifier("...")` string syntax. `@Inject` and `Provider<T>` integrate well with the Spring Core Container yet do not replace all of `@Autowired(required=false)`, `@Value`, `@Lazy`, or `@Scope`. Understanding the exact APIs, scopes, and where beans are registered keeps dependency injection clear, avoids import mix-ups, and makes testing straightforward.