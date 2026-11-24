# `@Fallback` and Version Requirements Starting in Spring Framework 6.2

## 1. What Problem Does `@Fallback` Solve?

A library or module may provide a **default implementation** so an application runs out of the box. When the application registers its own implementation, we want Spring to **prefer the custom implementation without forcing the user to add `@Primary`**.

Starting in **Spring Framework 6.2**, the `org.springframework.context.annotation.Fallback` annotation addresses this exact scenario: it marks a bean as a **fallback candidate** when Spring autowires a **single-valued dependency** (*single-valued autowiring*).

~~~java
@Bean
@Fallback
MessageCodec defaultCodec() {
    return new DefaultCodec();
}
~~~

This block is **illustrative only**; classes/interfaces, imports, and Spring configuration are required. A complete runnable example is in section 5.

If the context contains only the matching `defaultCodec` bean, Spring still injects that bean normally. If the application registers another **regular (non-fallback)** `MessageCodec` bean and it is the sole regular candidate, Spring selects the regular bean.

~~~text
Injection point: MessageCodec codec
                  |
       candidates matching MessageCodec type
                  |
        +---------+---------+
        |                   |
    defaultCodec         customCodec
    @Fallback            regular
        |                   |
        +---------+---------+
                  |
      exactly 1 regular candidate?
                  |
            Yes -> customCodec
            No  -> evaluate additional rules
                    / missing / ambiguous
~~~

**Three things that must not be misunderstood:**

- `@Fallback` **does not delete or disable** the bean. The bean can still be retrieved by name, injected via an appropriate qualifier, and included in `List<MessageCodec>`, `Map<String, MessageCodec>`, or a provider stream.
- `@Fallback` **is not equivalent to `@Lazy`, `@Conditional`, or `@Profile`**. It does not wait for another implementation to fail and swap out the bean currently used by a service.
- `@Fallback` **did not exist before Spring Framework 6.2**. Source importing this annotation will not compile on Spring 6.1.x or earlier because the API does not exist there.

In this model, “fallback” describes **candidate precedence when autowiring a single object**, not fault tolerance, circuit breaking, or application-level retries.

## 2. Applicability Conditions and Bean Selection Rules

`@Fallback` is a marker annotation (no parameters needed):

~~~java
import org.springframework.context.annotation.Fallback;
~~~

According to the Spring 6.2 API, it can be placed on a **class** (`TYPE`) or **method** (`METHOD`), with runtime retention. Two common placements:

~~~java
// Illustrative bean factory method:
@Bean
@Fallback
MessageCodec fallbackCodec() {
    return new DefaultCodec();
}
~~~

~~~java
// Illustrative component class:
@Component
@Fallback
class DefaultCodec implements MessageCodec {
    // Implement MessageCodec methods
}
~~~

Both blocks above are illustrative; neither is a standalone runnable file. For components, component scanning must cover the package or the class must be registered in the context. For `@Bean`, the `@Configuration` class containing the factory method must be registered with Spring.

### 2.1. Decision Table for a Single-Valued Dependency

Assume `MessageCodec` is an interface, bean candidates match the type, and no other qualifiers or special conditions apply.

| Matching beans | Expected outcome when injecting a single `MessageCodec` |
| --- | --- |
| One fallback bean, no other beans | Selects the fallback bean |
| One regular bean + one fallback bean | Selects the regular bean |
| One regular bean + multiple fallback beans | Selects the regular bean |
| Two regular beans + one fallback bean | Still ambiguous without an extra selection rule |
| Two fallback beans, no regular beans | Can be ambiguous because marking both fallback does not pick one uniquely |
| One matching `@Primary` bean + non-primary candidates | The primary bean is typically preferred for single injection |
| No matching beans | Required dependency cannot be resolved |

The rule stated clearly in Spring documentation: **if among multiple candidates there is only one bean not marked fallback, that bean is preferred**, acting much like a primary in this situation.

**Do not overgeneralize** that “having `@Fallback` guarantees Spring always picks a bean”. When two regular beans remain, `@Fallback` on a third bean cannot disambiguate the two main beans. When two fallbacks exist with no regular bean, an explicit selection rule or configuration adjustment is still needed.

### 2.2. A Sole Fallback Bean Still Works

This is what enables a library to ship a default implementation:

- The library provides `@Fallback MessageCodec defaultCodec()`.
- The application does not override it: the service receives `defaultCodec` and runs immediately.
- The application adds `@Bean MessageCodec customCodec()`: the service receives `customCodec` without needing to put `@Primary` on the new bean.

This is convenient for **library starters, extension modules, or integrations with default implementations**. However, the annotation does not itself decide how many beans are registered; registration still happens through `@Bean`, component scanning, imports, bean definitions, or configurations.

### 2.3. The Fallback Bean Remains Present in the Container

`@Fallback` does not delete the old bean or stop Spring from instantiating a non-lazy singleton. If `defaultCodec` has singleton scope, it can still be created during context refresh under the normal lifecycle.

When calling:

~~~java
MessageCodec selected = context.getBean(MessageCodec.class);
MessageCodec backup = context.getBean(
        "defaultCodec", MessageCodec.class);
~~~

in a context containing one regular bean and one fallback, by-type lookup can pick the regular bean, while **explicit lookup by name `defaultCodec` still retrieves the fallback**. These are two different kinds of bean requests; do not treat them as measuring the same thing.

## 3. Comparing `@Fallback`, `@Primary`, and `@Qualifier`

| Annotation | Main role | When to use? |
| --- | --- | --- |
| `@Fallback` | Lowers precedence of a backup bean during single-dependency selection | A module supplies a default implementation and wants application-specific beans preferred automatically |
| `@Primary` | Raises precedence of one bean when multiple single-injection candidates exist | There is one clear default choice among implementations |
| `@Qualifier("name")` | **Filters** candidates by criterion/metadata | An injection point needs an implementation with a specific role |
| No special annotation | Resolves by type and other metadata | Only one type-compatible candidate exists or another Spring rule applies |

### 3.1. Difference in Precedence Direction

With `@Primary`:

~~~java
@Bean
@Primary
MessageCodec preferredCodec() {
    return new PreferredCodec();
}
~~~

Bean `preferredCodec` is marked as the preferred choice when multiple candidates exist. With `@Fallback`:

~~~java
@Bean
@Fallback
MessageCodec defaultCodec() {
    return new DefaultCodec();
}
~~~

Bean `defaultCodec` remains eligible to provide `MessageCodec`, yet **yields to a non-fallback bean** whenever exactly one regular bean remains among the candidates.

Both snippets need the corresponding classes and Spring imports to compile standalone. They illustrate two design directions: **marking which bean is preferred** versus **marking which bean is a fallback**.

### 3.2. Qualifiers Still Matter

If both `customA` and `customB` are regular beans of type `MessageCodec`, `@Fallback` on a third bean cannot distinguish those two candidates. You can place:

~~~java
public Renderer(
        @Qualifier("customA") MessageCodec codec) {
    this.codec = codec;
}
~~~

This is an illustrative snippet. Spring's `@Qualifier` on the parameter requests a candidate matching that name/metadata. Spring resolves qualifiers within **the type-compatible set**, so do not assume a qualifier can turn an incompatible bean into a `MessageCodec`.

You can also explicitly request the fallback bean via a clear qualifier (such as `@Qualifier("defaultCodec")` if the actual metadata/bean name matches). In that case, the fallback annotation does not “forbid using” the bean; it only affects by-type selection precedence.

### 3.3. `@Primary` Does Not Shrink Collections

Both `@Primary` and `@Fallback` primarily affect **picking a single object** when multiple candidates exist. When injecting `List<MessageCodec>`, Spring can still supply regular, primary, and fallback beans matching the type. To narrow a collection intentionally, use qualifiers or an appropriate strategy/filter in code.

## 4. Collections, Maps, and `ObjectProvider` Still Include Fallbacks

Example:

~~~java
@Autowired
public void configure(List<MessageCodec> codecs,
                      Map<String, MessageCodec> codecsByName) {
    this.codecs = codecs;
    this.codecsByName = codecsByName;
}
~~~

This is illustrative code with fields/interfaces omitted. Spring can inject every type-matching bean into `List`, and `Map<String, MessageCodec>` has **bean names** as keys and bean instances as values.

`@Fallback` does not exclude members from this set. The API documentation explicitly notes that arrays, collections, maps, and streams from `ObjectProvider` include all type-matching candidates.

If a service needs **only one implementation at runtime**, inject a single `MessageCodec`. If you want to **discover all providers/strategies**, inject a collection or provider stream intentionally; then decide in your own logic whether to skip fallbacks, rather than assuming the container excluded them.

**Ordering note:** collection injection should not rely on source order or package-scan order. If order matters, use Spring `@Order`/`Ordered` appropriately or sort data before printing or processing.

### 4.1. `ObjectProvider` Does Not Mean Returning Only Regular Beans

If code calls:

~~~java
ObjectProvider<MessageCodec> provider =
        context.getBeanProvider(MessageCodec.class);
var names = provider.stream().map(MessageCodec::name).toList();
~~~

that is an **illustrative example** needing interface, context, and import declarations. The stream can include fallback beans as well. Conversely, `getObject()` or single-object resolution methods on the provider follow single-candidate selection rules and can be ambiguous if no unique final candidate exists.

Do not confuse having a fallback bean with `getIfAvailable()` returning `null` when **no bean exists at all**; a fallback is still a registered bean.

## 5. Complete Runnable Example: Spring Framework 6.2 and Java 17

This program creates two independent `ApplicationContext` instances:

- **First context:** registers only one fallback `MessageCodec`. The consumer bean receives the default.
- **Second context:** also registers a regular `MessageCodec`. The consumer bean automatically picks the regular implementation, while the collection still includes the fallback; the fallback can also still be retrieved directly by name.

### 5.1. Structure and Maven

Requires JDK 17+ and Apache Maven. Uses **Spring Framework 6.2.0** and `spring-context`; no Spring Boot, web server, or database.

~~~text
spring-fallback-demo/
├── pom.xml
└── src/main/java/demo/FallbackDemo.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>spring-fallback-demo</artifactId>
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
                    <mainClass>demo.FallbackDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. Complete Java Source

Create `src/main/java/demo/FallbackDemo.java`:

~~~java
package demo;

import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Fallback;
import org.springframework.context.annotation.Import;

public final class FallbackDemo {
    private FallbackDemo() {}

    public interface MessageCodec {
        String name();
        String render(String message);
    }

    public record PrefixCodec(String name, String prefix)
            implements MessageCodec {
        @Override
        public String render(String message) {
            return prefix + message;
        }
    }

    public static final class Processor {
        private final MessageCodec selected;
        private final List<MessageCodec> all;

        public Processor(MessageCodec selected, List<MessageCodec> all) {
            this.selected = Objects.requireNonNull(selected);
            this.all = List.copyOf(all);
        }

        public String selectedName() {
            return selected.name();
        }

        public String allNames() {
            return all.stream()
                    .map(MessageCodec::name)
                    .sorted()
                    .toList()
                    .toString();
        }

        public String process(String message) {
            return selected.render(message);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DefaultsConfig {
        @Bean
        @Fallback
        public MessageCodec defaultCodec() {
            return new PrefixCodec("fallback", "DEFAULT:");
        }

        @Bean
        public Processor processor(MessageCodec codec,
                                   List<MessageCodec> allCodecs) {
            return new Processor(codec, allCodecs);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(DefaultsConfig.class)
    public static class ExtensionConfig {
        @Bean
        public MessageCodec customCodec() {
            return new PrefixCodec("custom", "CUSTOM:");
        }
    }

    public static void main(String[] args) {
        inspect("-- fallback only --", DefaultsConfig.class);
        inspect("-- with regular bean --", ExtensionConfig.class);
    }

    private static void inspect(String heading, Class<?> configuration) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(configuration)) {
            Processor processor = context.getBean(Processor.class);
            System.out.println(heading);
            System.out.println("SELECTED " + processor.selectedName());
            System.out.println("ALL " + processor.allNames());
            System.out.println("RESULT " + processor.process("HELLO"));
            System.out.println("DEFAULT_DIRECT "
                    + context.getBean("defaultCodec", MessageCodec.class)
                             .render("HELLO"));
        }
    }
}
~~~

In `DefaultsConfig`, `defaultCodec` is a fallback. Because it is the only `MessageCodec` bean in the first context, Spring still picks it for the `MessageCodec codec` parameter.

In `ExtensionConfig`, `@Import(DefaultsConfig.class)` brings in both `defaultCodec` and `customCodec`. Because there is exactly one **non-fallback** candidate—`customCodec`—the container picks it for the single `codec` parameter. Meanwhile, `List<MessageCodec> allCodecs` contains both beans.

**Decisions ensuring deterministic stdout:**

- `PrefixCodec` prints nothing in constructors or factory methods.
- `Processor.allNames()` sorts names via `sorted()` instead of relying on bean listing order.
- The two contexts are isolated and each closes via try-with-resources.
- Looking up `defaultCodec` uses an explicit name and exact bean type.

### 5.3. Run Commands and Expected Stdout

In the `spring-fallback-demo` directory:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

Because the program depends on Spring JARs, running `javac/java` directly requires the full classpath; Maven manages dependencies and the main class for the run above. `maven.compiler.release=17` ensures Java 17 compilation.

**Stdout printed intentionally by the code in exact order:**

~~~text
-- fallback only --
SELECTED fallback
ALL [fallback]
RESULT DEFAULT:HELLO
DEFAULT_DIRECT DEFAULT:HELLO
-- with regular bean --
SELECTED custom
ALL [custom, fallback]
RESULT CUSTOM:HELLO
DEFAULT_DIRECT DEFAULT:HELLO
~~~

`mvn -version` prints version details; Maven may also log dependency downloads or plugin messages. The block above represents only the `System.out.println` lines in `FallbackDemo`.

### 5.4. Result Analysis

1. `AnnotationConfigApplicationContext(DefaultsConfig.class)` refreshes the first context and registers `defaultCodec` along with `processor`.
2. `@Fallback` does not make `defaultCodec` disappear. `processor(MessageCodec codec, ...)` receives the fallback because no other candidate of that type exists.
3. `Processor` prints name `fallback`; the list contains one bean, so `ALL [fallback]`.
4. `process("HELLO")` returns `DEFAULT:HELLO`. Looking up `defaultCodec` by name also returns the default implementation.
5. The second context imports the defaults config and adds `customCodec` as a **regular bean**, without `@Primary`.
6. When Spring creates `processor`, type `MessageCodec` has two candidates, one of which is fallback. Spring prefers `customCodec` for single injection, so `SELECTED custom`.
7. `List<MessageCodec>` still receives both candidates, yielding `ALL [custom, fallback]` after sorting.
8. `process("HELLO")` uses the custom codec to return `CUSTOM:HELLO`; direct lookup of `defaultCodec` still returns `DEFAULT:HELLO`.
9. `@Fallback` applies only during autowiring; it **does not swap the dependency of an already-created `Processor`** if you add bean definitions or alter the environment later.

The example does not use `@ComponentScan`; all beans are declared via `@Configuration`/`@Bean`. No Spring Boot auto-configuration or special condition affects bean selection.

## 6. Plain Java 17: Simulating the Fallback Rule for Clarity

Java 17 does not have Spring's `@Fallback` or create containers on its own. To illustrate the selection criterion, write a standalone program implementing a **simplified version** of the rule:

- If there is exactly **one regular bean**, select it.
- If there are **no regular beans** and only one candidate exists, select that candidate.
- If multiple unresolved candidates remain, report ambiguity.

This is a **teaching model**, not a replacement for Spring's real algorithm (which also involves qualifiers, primary, scopes, type matching, and other resolution rules).

Create `FallbackSelection.java`:

~~~java
import java.util.List;

public final class FallbackSelection {
    public record Candidate(String name, boolean fallback) {}

    static Candidate select(List<Candidate> candidates) {
        List<Candidate> regular = candidates.stream()
                .filter(candidate -> !candidate.fallback())
                .toList();
        List<Candidate> considered =
                regular.isEmpty() ? candidates : regular;

        if (considered.size() != 1) {
            throw new IllegalStateException(
                    "ambiguous: " + considered.size());
        }
        return considered.get(0);
    }

    public static void main(String[] args) {
        Candidate base = new Candidate("default", true);
        Candidate custom = new Candidate("custom", false);
        Candidate another = new Candidate("another", false);

        System.out.println("BASE "
                + select(List.of(base)).name());
        System.out.println("CUSTOM "
                + select(List.of(base, custom)).name());

        try {
            select(List.of(base, custom, another));
        } catch (IllegalStateException ex) {
            System.out.println("MULTIPLE " + ex.getMessage());
        }
    }
}
~~~

In the directory containing this file, run on JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 FallbackSelection.java
java FallbackSelection
~~~

**Exact stdout:**

~~~text
BASE default
CUSTOM custom
MULTIPLE ambiguous: 2
~~~

The final line demonstrates the case where **two regular beans** remain after filtering out the fallback bean for a single-valued dependency. Because no `@Primary` or qualifier rule is modeled, the code reports ambiguity. That is precisely why `@Fallback` **cannot replace** the rest of bean candidate resolution.

## 7. Version Requirements and Compatibility

### 7.1. Minimum Version

- `@Fallback` was introduced **in Spring Framework 6.2.0**.
- Exact package and import: `org.springframework.context.annotation.Fallback`.
- With `spring-context:6.2.0`, the demo uses real APIs and Java 17 without preview syntax.
- **Spring Framework 6.1.x and earlier lack `@Fallback`**; importing it on those versions causes compilation errors like `cannot find symbol`/`Fallback cannot be resolved to a type`.
- Do not confuse `@Fallback` with `@Primary`, which already existed in earlier Spring versions.

### 7.2. Spring Boot and Dependency Version Management

If a project uses Spring Boot, the Spring Framework version is normally governed by Boot's **BOM/dependency management**. Never assume the version written in one sub-module's `pom.xml` will remain the actual framework version when running another application.

When suspecting a version mismatch:

~~~bash
mvn -version
mvn dependency:tree -Dincludes=org.springframework:spring-context
~~~

If the project uses Gradle, inspect dependency resolution with the corresponding task such as `./gradlew dependencies --configuration runtimeClasspath` (configuration name depends on the project). The Maven command above does not require running the application; it shows which version `spring-context` resolves to.

**Keep Spring Framework modules aligned** through a compatible BOM or dependency management. Forcing a single Spring JAR to 6.2 inside an app whose core Spring JARs remain 6.1 can cause classloading and compatibility issues. To use `@Fallback`, ensure the entire Spring dependency graph aligns, not merely compiling one source file.

### 7.3. If You Cannot Upgrade to 6.2 Yet

In older Spring versions, relatively straightforward options include:

- Mark the preferred implementation with `@Primary` if you control the application configuration.
- Or use `@Qualifier` to pick the exact implementation at the injection point.
- Or design conditional bean registration using an appropriate mechanism/framework if you genuinely want to **skip registering** the default bean when a custom bean exists.

These are **alternatives tailored to specific needs**, not a claim that putting `@Primary` on a default bean behaves the same as `@Fallback`. Marking the **default** as primary prioritizes it instead of letting custom beans take over—the exact opposite of the goal.

### 7.4. Java 17 and Imports

Spring Framework 6.2 requires the Java baseline of the Spring 6 generation; **Java 17+** is the baseline used for these examples. Section 5's code uses records, `toList()`, and try-with-resources—all supported in Java 17.

The annotation can be applied to a class or a method:

~~~java
@Fallback
class DefaultCodec implements MessageCodec {
    // ...
}

@Bean
@Fallback
MessageCodec defaultCodec() {
    return new DefaultCodec();
}
~~~

These are two **alternative illustrative declarations**. Do not copy both into the same bean graph expecting a single fallback bean: Spring evaluates each bean definition separately.

## 8. What `@Fallback` Does NOT Do

| Misconception | Reality |
| --- | --- |
| “A fallback bean is created only if no regular bean exists.” | No; the annotation is not a bean registration or instantiation condition. |
| “Fallback automatically deletes the default bean when a custom bean appears.” | No; the default bean stays in the context. |
| “Fallback means failover when the main bean throws an exception.” | No; it is candidate selection metadata, not a runtime fault-tolerance mechanism. |
| “With `@Fallback`, two regular beans stop being ambiguous.” | No; two regular beans still need a selection rule. |
| “Fallbacks are always excluded from `List<T>` or `Map<String,T>`.” | No; collections, maps, and provider streams still include matching beans. |
| “Put `@Fallback` on an injection parameter.” | Wrong target; the annotation belongs on a bean class or factory method. |
| “Fallback is the same as `@Primary`.” | Opposite precedence: primary raises priority, fallback yields to regular beans. |
| “Fallback is the same as `@Qualifier`.” | Qualifiers filter by criteria; fallback marks precedence in single-dependency resolution. |
| “Fallback works on Spring 6.1.” | No; requires Spring 6.2+. |
| “Fallback always makes a bean `@Lazy`.” | No; lazy initialization is a separate configuration. |
| “A fallback bean gets injected even if its type doesn't match.” | No; it must still match the dependency's type and metadata. |
| “The annotation automatically picks beans based on each request's content.” | No; autowiring is not runtime business routing. |

### When Multiple Fallback Beans Exist

If only two fallback beans of the same type exist, single injection still cannot pick a unique winner. Do not assume “both are backups” means Spring automatically uses whichever was declared first. If you want a fixed default within the group, add another selection rule or simplify the bean graph; if you want both, inject a collection.

### `@Fallback` and `@Qualifier` Coexisting

Qualifiers typically narrow down **an eligible candidate set for an injection point**. Fallback still expresses precedence when Spring must decide on a single candidate. Thus, selecting by name/qualifier can intentionally pull in a fallback bean where needed; however, do not rely on an imagined global precedence order across every configuration. When combining qualifiers, primary, and fallback, testing the bean graph with an integration test is best practice.

## 9. Testing Selection Behavior

The demo verifies two key scenarios without a network or database:

- Fallback only: processor receives `defaultCodec`.
- Fallback + one regular bean: processor receives `customCodec`, while `List<MessageCodec>` still contains both.

In a real project, add integration tests for:

1. Context with only the fallback bean → injection succeeds.
2. Context with fallback + one regular bean → regular bean is selected.
3. Context with fallback + **two regular beans** → verify actual behavior under qualifiers/primary/name matching; if no rule resolves them, detect ambiguity.
4. Inject `List<T>` or typed `Map<String,T>` → verify the fallback bean is still present.
5. Look up the fallback bean by name → the bean remains accessible.
6. Dependency tree output confirms aligned Spring Framework 6.2+ versions.

Avoid writing a unit test that merely asserts `@Fallback` exists in source without starting a context: annotations on beans are metadata that require a real Spring container to validate injection resolution.

### Error Symptoms and Debugging

- `cannot find symbol: Fallback`: older Spring version or wrong package import.
- `NoSuchBeanDefinitionException`: no candidate matches type/qualifier, or configuration was not registered.
- `NoUniqueBeanDefinitionException`: multiple final candidates remain, usually multiple regular beans of the same type.
- `BeanCreationException`: a candidate or factory method failed during initialization; `@Fallback` does not handle this exception.
- Spring was upgraded yet still picks an unexpected bean: check qualifiers, `@Primary`, bean names, `@Fallback` on the right bean definition, and configuration order/sources.
- Collection lacks the fallback bean as expected: check whether the fallback bean is actually registered and type-compatible rather than blaming the annotation.

## 10. Exercises with Answers

**1.** Only one `@Fallback MessageCodec` exists; does single-valued `MessageCodec` injection work?

**Answer:** Yes. When it is the sole candidate, Spring can inject the fallback bean.

**2.** Add one regular `MessageCodec` bean without `@Primary`; which one does Spring pick?

**Answer:** With a single matching regular bean, Spring selects the regular bean, not the fallback.

**3.** Given two regular beans and one fallback, does single injection definitely pick the first-declared regular bean?

**Answer:** No. When two regular candidates remain, an explicit rule is needed for the final choice; otherwise ambiguity can fail.

**4.** Does `List<MessageCodec>` contain two elements when the context has one fallback and one regular bean?

**Answer:** Yes, provided both match the type and are eligible autowire candidates. The fallback annotation does not remove a bean from collections.

**5.** Does `@Fallback` cause `getBean("defaultCodec")` to fail?

**Answer:** No. The bean remains registered; explicit lookup by name can retrieve it.

**6.** Can `@Fallback` replace a circuit breaker if the main implementation loses network connectivity?

**Answer:** No. The fallback annotation handles candidate selection at wiring time, not automatic retries or failover across business calls.

**7.** Why does Spring 6.1 report that the `Fallback` class cannot be found?

**Answer:** Because the annotation was added in Spring Framework 6.2. To use it, upgrade the framework accordingly or choose a configuration approach compatible with older versions.

**8.** Is `@Primary` the same as `@Fallback`?

**Answer:** No. Primary marks a preferred bean; fallback marks a bean that yields when a suitable regular option exists.

**9.** Can a `@Fallback` bean appear in `ObjectProvider<T>.stream()`?

**Answer:** Yes, if type and autowiring conditions match; fallback does not remove it from the provider stream.

**10.** If a framework starter supplies a default implementation, should it put `@Primary` or `@Fallback` on the default?

**Answer:** In Spring 6.2+, `@Fallback` is usually preferable when you want an application-registered bean **preferred naturally** without forcing users to add `@Primary`. If the starter wants to create the bean only when no bean of that type exists at all, use **conditional registration** separately rather than conflating it with fallback metadata.

**11.** Why does the demo sort names inside `allNames()`?

**Answer:** So stdout does not depend on the order Spring places beans into the collection; `[custom, fallback]` stays deterministic.

## 11. Project Adoption Checklist

- [ ] Verified Java 17+ and Spring Framework **6.2+** requirement when using `@Fallback`.
- [ ] Imported `org.springframework.context.annotation.Fallback` accurately.
- [ ] Placed the annotation on a bean class or `@Bean` factory method, not on an injection parameter.
- [ ] Registered a valid default bean; do not assume the annotation creates beans itself.
- [ ] Ensured only one regular bean remains for a single dependency if you want it to naturally beat the fallback.
- [ ] Did not assume `@Fallback` excludes beans from collections/Maps/provider streams.
- [ ] When multiple regular beans exist, defined an explicit selection rule with qualifiers or primary where appropriate.
- [ ] Did not put `@Primary` on the default if custom beans are meant to take precedence.
- [ ] Did not treat a fallback bean as `@ConditionalOnMissingBean` or runtime failover.
- [ ] Checked the Spring dependency tree/BOM to avoid version mismatches.
- [ ] Separated processing-logic unit tests from candidate-resolution integration tests.
- [ ] Tested contexts both with and without overriding beans.
- [ ] Did not rely on package scan order as a bean selection rule.
- [ ] Considered singleton lifecycle and thread safety separately; fallback annotation does not alter those requirements.
- [ ] When maintaining backward compatibility with Spring pre-6.2, avoided importing APIs that do not exist yet.
- [ ] Verified application stdout separately from Maven logs.

### Official Documentation

- [Fine-tuning Annotation-based Autowiring with @Primary or @Fallback](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [@Fallback API — Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/annotation/Fallback.html)
- [Spring Framework 6.2 Release Notes — Support for fallback beans](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.2-Release-Notes)
- [Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)

**Conclusion:** `@Fallback` is a **bean candidate precedence** tool introduced in **Spring Framework 6.2**. It lets a module register a default implementation that automatically yields to a regular implementation added by the application. Fallback beans remain in the container and in collection injections. Understanding these boundaries, the version requirement, and how it differs from `@Primary`/`@Qualifier` helps you supply defaults cleanly without mistaking the annotation for bean replacement or runtime error handling.