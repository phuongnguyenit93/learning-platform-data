# Restricting Candidates with `autowire-candidate` in Spring Core Container

## 1. A Bean Existing Does Not Mean It Is Allowed to Be Autowired

A Spring `ApplicationContext` can register multiple beans of the same Java type. For example, `activeTransport` serves main business logic, while `internalTransport` is an implementation used for maintenance or testing a special processing path. Both implement `Transport`, yet regular services **should not automatically receive** `internalTransport` simply because its type matches.

Spring Core Container separates the following concepts:

1. **Bean registration:** does the bean have a name, definition, and membership in the container?
2. **Type matching:** is the bean's type assignable to the type requested by the injection point?
3. **Autowire candidate eligibility:** is that type-matching bean **permitted to participate in autowiring**?
4. **Candidate selection:** when multiple candidates are permitted, do `@Primary`, `@Qualifier`, `@Fallback`, and other rules select an appropriate bean?
5. **Explicit reference:** can a caller or configuration explicitly looking up a bean by **explicit name** still use that bean?

The **`autowire-candidate=false`** (XML) or **`@Bean(autowireCandidate=false)`** (Java configuration) mechanism places a restriction at **step 3**. It does not delete the bean and **does not forbid every lookup by name**.

Spring Java configuration example:

~~~java
// Snippet: Transport is an interface included in the complete project in section 7.
@Bean(name = "internalTransport", autowireCandidate = false)
Transport internalTransport() {
    return () -> "INTERNAL";
}
~~~

The `internalTransport` bean remains registered; `context.getBean("internalTransport", Transport.class)` can still return the instance. However, Spring excludes this bean from type-based selection at injection points such as:

~~~java
@Autowired
private Transport transport;

// Or a factory method receiving a Spring-resolved dependency:
@Bean
Report report(Transport selected) {
    return new Report(selected);
}
~~~

Both snippets above are illustrative, **not standalone Java files**. The program has a complete structure in section 7.

**Key message:** You cannot treat the output of `getBeanNamesForType(Transport.class)` as an exact mirror of the bean list `@Autowired Transport` will consider. A type-matching bean can still be marked **not an autowire candidate**.

## 2. Where Is `autowire-candidate` Configured?

### 2.1. On an XML Bean Definition

In XML, the exact attribute name is **`autowire-candidate`**:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="activeTransport"
          class="demo.ActiveTransport"/>

    <bean id="internalTransport"
          class="demo.InternalTransport"
          autowire-candidate="false"/>
</beans>
~~~

This is an **illustrative** XML configuration example using two hypothetical standalone classes `demo.ActiveTransport`/`demo.InternalTransport`; the runnable project in section 7 **does not read XML** and uses `@Bean` with Java 17.

The value `false` means **the `internalTransport` definition is excluded from the autowire candidate set for type-based injection**. If XML configures an explicit dependency:

~~~xml
<bean id="specialReport" class="demo.SpecialReport">
    <constructor-arg ref="internalTransport"/>
</bean>
~~~

then explicit `ref` **can still work**; do not interpret the flag as meaning “the bean does not exist”. The XML snippet above merely illustrates that point; class `demo.SpecialReport` is likewise illustrative and is not part of the standalone Maven source below.

### 2.2. On a `@Bean` Method

Spring provides the `autowireCandidate` attribute directly on `org.springframework.context.annotation.Bean`:

~~~java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean("activeTransport")
    Transport activeTransport() {
        return () -> "ACTIVE";
    }

    @Bean(name = "internalTransport", autowireCandidate = false)
    Transport internalTransport() {
        return () -> "INTERNAL";
    }
}
~~~

This configuration produces two definitions `activeTransport` and `internalTransport`, both of type `Transport`. Only `activeTransport` is a candidate for plain `@Autowired Transport`. **The flag lives on the bean definition**, not inside the `Transport` interface or instance.

### 2.3. Adjusting via the `BeanDefinition` API

If you genuinely need to control metadata in Java when registering definitions (typically in infrastructure code):

~~~java
// Snippet: runs before the bean factory starts resolving dependencies.
BeanDefinition definition =
        registry.getBeanDefinition("internalTransport");
definition.setAutowireCandidate(false);
~~~

This snippet requires `BeanDefinition`, `BeanDefinitionRegistry`, and an appropriate registration phase; it is **not** a recommendation for business services to mutate bean definitions once the application is running. For new code, declaring `@Bean(autowireCandidate=false)` explicitly is usually easier to inspect.

Spring's bean definition also provides `isAutowireCandidate()` to query this metadata, which is very helpful when debugging why “a bean is in the context yet is not injected”.

### 2.4. Default Value

For most ordinary bean definitions, **autowire candidate defaults to `true`**. Having a bean of a matching type usually lets it participate in autowiring, subject to qualifiers, generic signatures, scopes, and other filters.

Do not set `false` casually to dodge a `NoUniqueBeanDefinitionException` without knowing which use cases might need that bean. This is a **policy disabling DI participation**, with consequences across multiple injection points.

## 3. Name or Type Lookup Works, Yet the Injection List Is Filtered

Compare four scenarios:

| Operation | Ordinary `activeTransport` | `internalTransport` with `autowireCandidate=false` |
| --- | --- | --- |
| Bean definition registered | Yes | Yes |
| `context.containsBean("...")` | Yes | Yes |
| `getBean("name", Transport.class)` | Retrievable | **Still retrievable by name** |
| `getBeanNamesForType(Transport.class)` | Usually appears | **Still appears** if type-compatible |
| `getBeansOfType(Transport.class)` | Can appear in the map | **Can still appear** because this is a type discovery/lookup API |
| Plain `@Autowired Transport` | Considered | **Excluded** |
| `@Autowired List<Transport>` | Included in collection | **Excluded from injected candidates** |
| `@Autowired Map<String,Transport>` | Included in map | **Excluded from injected candidates** |
| `@Qualifier("internalTransport") Transport` | Does not select a bean failing the qualifier | **Does not bring an excluded bean back** into type-based autowiring |

### Discovery Differs from Injection

~~~java
String[] names =
        context.getBeanNamesForType(Transport.class);
Map<String, Transport> all =
        context.getBeansOfType(Transport.class);
~~~

Both APIs above perform **type-based bean discovery/lookup** in `ListableBeanFactory`. They do not directly return “the filtered candidate set for a specific autowire point”. A bean can simultaneously match the type and be marked `autowireCandidate=false`.

Conversely, Spring resolves dependencies for fields, constructors, and factory-method parameters through autowiring rules. **The result can be smaller than type discovery**, especially when exclusions, qualifiers, or generic constraints exist.

### Explicit Name-Based References Still Work

~~~java
Transport internal =
        context.getBean("internalTransport", Transport.class);
~~~

This is an **explicit request by bean name**; the autowire candidate flag does not delete `internalTransport`. According to Spring documentation, explicit references by name are still resolved. XML `<ref bean="internalTransport"/>` and explicit by-name mechanisms follow the same principle when used properly.

**Crucial distinction:** `@Qualifier("internalTransport")` on `@Autowired Transport` **is still type-based autowiring with a qualifier filter**. The qualifier **does not** turn that injection into an explicit `getBean(name)` that bypasses exclusion. That is why you cannot use a qualifier as a “skeleton key” to defeat `autowireCandidate=false`.

## 4. `autowireCandidate=false` Does Not Prevent the Bean Itself from Receiving Dependencies

A point often understood backwards:

> “A bean excluded from autowire candidates will no longer have Spring inject its own dependencies.”

False. The flag governs **whether others can autowire this bean into themselves**, not whether Spring instantiates this bean or supplies its own dependencies.

Example:

~~~java
// Illustrative snippet (place inside an appropriate @Configuration class with @Bean).
@Bean(name = "internalTransport", autowireCandidate = false)
Transport internalTransport(Settings settings) {
    return new InternalTransport(settings);
}
~~~

Here `Settings` is an eligible bean and Spring can resolve the `Settings settings` parameter to build `internalTransport`. Once created, `internalTransport` remains excluded **when another consumer requests `Transport` by type**.

**Two different dependency directions:**

~~~text
          Settings (ordinary candidate)
                    |
                    | Inject Settings to CREATE the bean
                    v
    internalTransport (autowireCandidate=false)
                    |
                    X NOT autowired BY TYPE
                    |
                    v
               RegularConsumer

   Explicit getBean("internalTransport") still works
~~~

When building systems with plugins, internal delegates, or supporting adapters, this is an important distinction: you want a bean to function fully inside the context while **not intruding into the default candidate set** of other services.

That bean still obeys scopes, constructor/field/method injection, and initialization/destruction callbacks under standard Spring rules. The flag does not turn a Spring bean into an unmanaged object outside the container.

## 5. `autowireCandidate=false` Differs from `defaultCandidate=false`

Starting in Spring Framework **6.2+**, `@Bean` has two important variants:

| Metadata | No qualifier, plain by-type injection | With matching `@Qualifier` | Explicit name lookup |
| --- | --- | --- | --- |
| `autowireCandidate=true, defaultCandidate=true` (default) | Can be a candidate | Can be a candidate | Yes |
| **`autowireCandidate=false`** | **Not autowired** | **Still not autowired by type** | **Yes** |
| **`defaultCandidate=false`** with `autowireCandidate=true` | Not a default choice by plain type | **Can be selected with a qualifier** | Yes |

### “Hard” Restriction: `autowireCandidate=false`

~~~java
@Bean(name = "internalTransport", autowireCandidate = false)
Transport internalTransport() {
    return () -> "INTERNAL";
}
~~~

Do not use `@Autowired @Qualifier("internalTransport")` to ask for this bean as a standard type-based candidate. If business logic needs that exact named bean, express it as an **explicit reference by name** at the composition root or bean wiring layer where appropriate.

### “Conditional” Restriction: `defaultCandidate=false`

~~~java
@Bean(name = "specialTransport", defaultCandidate = false)
Transport specialTransport() {
    return () -> "SPECIAL";
}
~~~

This bean keeps `isAutowireCandidate=true`, yet is intended to participate only at injection points carrying an **additional indicator** such as `@Qualifier("specialTransport")`.

Example:

~~~java
@Bean
NamedConsumer selectedClient(
        @Qualifier("specialTransport") Transport selected) {
    return new NamedConsumer(selected);
}
~~~

This snippet requires defining `NamedConsumer` and importing the qualifier properly. The complete project in section 7 illustrates the same mechanism using `restrictedTransport`.

**When you need “never automatically pick during type injection”, use `autowireCandidate=false`. When you need “not a default, yet still selectable with a qualifier”, consider `defaultCandidate=false`.** Do not confuse them with `@Primary`/`@Fallback`: those two annotations affect precedence among eligible candidates, whereas candidate flags affect whether a bean is eligible from the outset.

## 6. Can `@Primary`, `@Qualifier`, `@Fallback`, or Field Names Rescue an Excluded Bean?

### `@Primary` Does Not Override Exclusion

If bean `internalTransport` carries both `autowireCandidate=false` and `@Primary`:

~~~java
@Bean(name = "internalTransport", autowireCandidate = false)
@Primary
Transport internalTransport() {
    return () -> "INTERNAL";
}
~~~

When a service asks for a plain `Transport`, Spring still **does not use `internalTransport` as an autowire candidate**. `@Primary` can only prioritize **remaining eligible candidates**; it does not turn an excluded definition into a candidate.

In the demo, we **intentionally** place `@Primary` on the excluded bean to verify this rule. Afterward, both `isPrimary()` and `isAutowireCandidate()` metadata are printed; you will see **`primary=true` yet `autowireCandidate=false`**, and the service still receives the regular bean.

### `@Qualifier` Is a Filter, Not an Explicit Ref

~~~java
@Autowired
@Qualifier("internalTransport")
private Transport transport;
~~~

When bean `internalTransport` has `autowireCandidate=false`, this remains a type-driven injection point and therefore **is not allowed to pick that bean merely via qualifier**. Do not confuse `@Qualifier("beanName")` with `getBean("beanName")`; the two carry different meanings.

### `@Fallback` Does Not Exclude a Bean from Autowire Candidates

In Spring 6.2+, `@Fallback` marks a bean as a backup option; it **can still be an autowire candidate** and join collections, depending on qualifiers and eligibility. `@Primary` prioritizes a candidate, `@Fallback` lowers precedence relative to non-fallback candidates, while **`autowireCandidate=false` removes the bean completely from type-based autowiring**.

### Field/Parameter Names Do Not Bypass Exclusion

A field named `internalTransport` with `@Autowired` cannot automatically “restore” autowiring for an excluded bean merely because the field name matches the bean name. Injection-point names help choose among candidates; they **must not be treated as a backdoor around candidate eligibility**.

**Exception to distinguish:** XML **`byName`** autowiring mode or an explicit bean reference by name has distinct semantics; Spring documentation notes explicitly that `autowire-candidate` does not block explicit references by name. Do not assume every technique involving the word “name” is the same kind of injection.

## 7. Java 17 Maven Project: Observing Discovery, Filtering, and Explicit Lookup Clearly

The goal is to **run three isolated contexts**:

1. **MainConfig:** has an ordinary bean `activeTransport` and a bean `internalTransport` carrying `autowireCandidate=false` **and `@Primary`**. `getBeanNamesForType(Transport.class)` sees both; `@Bean Report report(Transport selected, List<Transport> ..., Map<String,Transport> ...)` receives only **ACTIVE**. `getBean("internalTransport")` still returns **INTERNAL**.
2. **ExcludedOnlyConfig:** has only one bean of the type, yet **not a candidate**, while a `@Bean` requires a mandatory `Transport` → context **startup fails**, proving “matches type yet excluded” is insufficient.
3. **RestrictedConfig:** has a normal `regularTransport` and `restrictedTransport` with `defaultCandidate=false`. Plain `Transport` receives **REGULAR**; the parameter annotated with `@Qualifier("restrictedTransport")` receives **RESTRICTED**.

The code needs no Spring Boot, HTTP server, or database; all application results are printed intentionally by the source.

### 7.1. Directory Structure

~~~text
candidate-restriction-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── CandidateRestrictionDemo.java
~~~

Requires **JDK 17+**, Maven **3.9+**, and access to download Maven artifacts on the first build.

### 7.2. Complete `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>candidate-restriction-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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
                    <mainClass>demo.CandidateRestrictionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` brings in the dependent Spring Core Container modules via Maven; the compiler plugin targets Java 17. Jakarta annotation API is unnecessary because the demo uses Spring `@Bean`, `@Primary`, and `@Qualifier`; `@Resource` is not used in the main program.

### 7.3. `src/main/java/demo/CandidateRestrictionDemo.java`

~~~java
package demo;

import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

public final class CandidateRestrictionDemo {

    private CandidateRestrictionDemo() {
    }

    @FunctionalInterface
    interface Transport {
        String id();
    }

    record FixedTransport(String id) implements Transport {
    }

    static final class Report {
        private final Transport selected;
        private final List<Transport> available;
        private final Map<String, Transport> byName;

        Report(Transport selected, List<Transport> available,
                Map<String, Transport> byName) {
            this.selected = selected;
            this.available = available;
            this.byName = byName;
        }

        String chosen() {
            return selected.id();
        }

        String injectedIds() {
            return available.stream()
                    .map(Transport::id)
                    .sorted()
                    .collect(Collectors.joining(","));
        }

        String injectedNames() {
            return byName.keySet().stream()
                    .sorted()
                    .collect(Collectors.joining(","));
        }

        boolean containsInternal() {
            return byName.containsKey("internalTransport");
        }
    }

    static final class SingleConsumer {
        private final Transport selected;

        SingleConsumer(Transport selected) {
            this.selected = selected;
        }

        String chosen() {
            return selected.id();
        }
    }

    static final class RestrictedReport {
        private final Transport plain;
        private final Transport qualified;

        RestrictedReport(Transport plain, Transport qualified) {
            this.plain = plain;
            this.qualified = qualified;
        }

        String plain() {
            return plain.id();
        }

        String qualified() {
            return qualified.id();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class MainConfig {
        @Bean("activeTransport")
        public Transport activeTransport() {
            return new FixedTransport("ACTIVE");
        }

        @Bean(name = "internalTransport", autowireCandidate = false)
        @Primary
        public Transport internalTransport() {
            return new FixedTransport("INTERNAL");
        }

        @Bean
        public Report report(
                Transport selected,
                List<Transport> transports,
                Map<String, Transport> transportsByName) {
            return new Report(selected, transports, transportsByName);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ExcludedOnlyConfig {
        @Bean(name = "excludedOnly", autowireCandidate = false)
        public Transport excludedOnly() {
            return new FixedTransport("EXCLUDED");
        }

        @Bean
        public SingleConsumer needsTransport(Transport candidate) {
            return new SingleConsumer(candidate);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class RestrictedConfig {
        @Bean("regularTransport")
        public Transport regularTransport() {
            return new FixedTransport("REGULAR");
        }

        @Bean(name = "restrictedTransport", defaultCandidate = false)
        public Transport restrictedTransport() {
            return new FixedTransport("RESTRICTED");
        }

        @Bean
        public RestrictedReport restrictedReport(
                Transport plain,
                @Qualifier("restrictedTransport") Transport explicit) {
            return new RestrictedReport(plain, explicit);
        }
    }

    private static String sortedNames(String[] input) {
        Arrays.sort(input);
        return String.join(",", input);
    }

    private static String sortedKeys(Map<String, ?> input) {
        return input.keySet().stream()
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(MainConfig.class)) {
            var report = context.getBean(Report.class);
            var factory = context.getBeanFactory();
            var internal =
                    context.getBean("internalTransport", Transport.class);

            System.out.println("main.typeNames=" + sortedNames(
                    context.getBeanNamesForType(Transport.class)));
            System.out.println("main.allTypeObjects=" + sortedKeys(
                    context.getBeansOfType(Transport.class)));
            System.out.println("main.internalRegistered="
                    + context.containsBeanDefinition("internalTransport"));
            System.out.println("main.internalCandidate="
                    + factory.getBeanDefinition(
                            "internalTransport").isAutowireCandidate());
            System.out.println("main.internalPrimary="
                    + factory.getBeanDefinition(
                            "internalTransport").isPrimary());
            System.out.println("main.activeCandidate="
                    + factory.getBeanDefinition(
                            "activeTransport").isAutowireCandidate());
            System.out.println("main.selected=" + report.chosen());
            System.out.println("main.injectedList=" + report.injectedIds());
            System.out.println("main.injectedMap=" + report.injectedNames());
            System.out.println("main.mapContainsInternal="
                    + report.containsInternal());
            System.out.println("main.explicitByName=" + internal.id());
            System.out.println("main.explicitSame="
                    + (internal == context.getBean(
                            "internalTransport", Transport.class)));
        }

        // Only an excluded bean of the same type exists: not eligible for autowiring.
        try (var context = new AnnotationConfigApplicationContext(
                ExcludedOnlyConfig.class)) {
            System.out.println("excludedOnly.unexpected");
        } catch (BeansException expected) {
            System.out.println("excludedOnly.failed=true");
        }

        try (var context = new AnnotationConfigApplicationContext(
                RestrictedConfig.class)) {
            var report = context.getBean(RestrictedReport.class);
            var factory = context.getBeanFactory();

            System.out.println("restricted.typeNames=" + sortedNames(
                    context.getBeanNamesForType(Transport.class)));
            System.out.println("restricted.plain=" + report.plain());
            System.out.println("restricted.qualified=" + report.qualified());
            System.out.println("restricted.canAutowire="
                    + factory.getBeanDefinition(
                            "restrictedTransport").isAutowireCandidate());
            System.out.println("restricted.defaultCandidate="
                    + factory.getBeanDefinition(
                            "restrictedTransport").isDefaultCandidate());
            System.out.println("restricted.byName="
                    + context.getBean(
                            "restrictedTransport", Transport.class).id());
        }
    }
}
~~~

### 7.4. Reading the Three Experiments Accurately

**MainConfig — internal does not participate in autowiring:**

- Spring creates definitions for two beans of type `Transport` and the `Report` bean.
- `internalTransport` still has metadata `isPrimary=true`, yet `isAutowireCandidate=false`. Thus `@Primary` on that bean **does not override** the excluded status.
- Parameter `Transport selected` on factory method `report` receives `activeTransport` (the only eligible candidate).
- `List<Transport>` and `Map<String,Transport>` injected into `Report` contain only ACTIVE, **not** INTERNAL.
- `getBeanNamesForType(Transport.class)` and `getBeansOfType(Transport.class)` still observe both type-matching beans.
- `context.getBean("internalTransport", Transport.class)` still works. Looking up twice by name in one context returns the same instance because the default scope is singleton.

**ExcludedOnlyConfig — type matches, yet no candidate exists:**

- The context has exactly one `Transport` type match, yet that bean has `autowireCandidate=false`.
- `needsTransport(Transport candidate)` is a required injection point; with no eligible candidate, Spring cannot create `SingleConsumer` and `refresh()` fails.
- `BeansException` is caught intentionally. **Do not** pin expected stdout to an exact exception subclass or stack trace.

**RestrictedConfig — `defaultCandidate` differs from `autowireCandidate`:**

- `regularTransport` is an autowire candidate and default candidate by default.
- `restrictedTransport` has `defaultCandidate=false` yet `isAutowireCandidate=true`.
- Parameter `Transport plain` selects REGULAR when unqualified, while `@Qualifier("restrictedTransport") Transport explicit` receives RESTRICTED.
- `getBean("restrictedTransport")` also works—not because the setting is `true` or `false`, but because it is an explicit lookup by name.

**Why there is no race or order dependency in the output:** the three contexts are created and closed **sequentially**. No factory method calls another `@Bean` method directly; `proxyBeanMethods=false` is appropriate. Listed names are sorted, and values returned by `FixedTransport` are fixed.

## 8. CLI and Expected Stdout

Inside the `candidate-restriction-demo` directory containing `pom.xml`, run:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

The first three version commands produce environment-dependent output. The last command compiles targeting Java 17 via Maven Compiler Plugin and then runs the main class with Spring dependencies.

**19 stdout lines printed by the Java program itself** (excluding Maven/Spring logging, warnings, or exception diagnostics):

~~~text
main.typeNames=activeTransport,internalTransport
main.allTypeObjects=activeTransport,internalTransport
main.internalRegistered=true
main.internalCandidate=false
main.internalPrimary=true
main.activeCandidate=true
main.selected=ACTIVE
main.injectedList=ACTIVE
main.injectedMap=activeTransport
main.mapContainsInternal=false
main.explicitByName=INTERNAL
main.explicitSame=true
excludedOnly.failed=true
restricted.typeNames=regularTransport,restrictedTransport
restricted.plain=REGULAR
restricted.qualified=RESTRICTED
restricted.canAutowire=true
restricted.defaultCandidate=false
restricted.byName=RESTRICTED
~~~

### Key Output Groups

| Output | What is verified |
| --- | --- |
| `main.typeNames=activeTransport,internalTransport` | Type discovery still sees the excluded bean |
| `main.internalCandidate=false` | Definition metadata actively excludes `internal` from autowiring |
| `main.internalPrimary=true` | Primary exists in metadata yet **does not rescue** the excluded bean |
| `main.injectedList=ACTIVE` | Autowired collection includes only eligible beans |
| `main.injectedMap=activeTransport` | Autowired map omits `internal` |
| `main.explicitByName=INTERNAL` | By-name lookup still retrieves the excluded bean |
| `excludedOnly.failed=true` | Having only an excluded bean cannot satisfy a required injection |
| `restricted.plain=REGULAR` | A `defaultCandidate=false` bean stays out of plain type injection |
| `restricted.qualified=RESTRICTED` | A qualifier allows the restricted default candidate to be injected |
| `restricted.canAutowire=true` | `defaultCandidate=false` does not mean `autowireCandidate=false` |

Running a modified version with altered `defaultCandidate`/qualifier/primary/beans may change the lines above; compare against the original source. Spring may log context startup failure in the excluded-only case, while expected output counts only `System.out.println` from the code.

## 9. Plain Java 17: Separating Registry Membership from Eligible Candidates

To understand the mechanism without Spring, create standalone file **`ManualCandidateFilter.java`**:

~~~java
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public class ManualCandidateFilter {
    interface Transport {
        String id();
    }

    public static void main(String[] args) {
        Map<String, Transport> registered = Map.of(
                "core", () -> "CORE",
                "internal", () -> "INTERNAL");
        Set<String> excluded = Set.of("internal");

        String names = registered.keySet().stream()
                .sorted().collect(Collectors.joining(","));
        String eligible = registered.keySet().stream()
                .filter(name -> !excluded.contains(name))
                .sorted().collect(Collectors.joining(","));

        System.out.println("registered=" + names);
        System.out.println("eligible=" + eligible);
        System.out.println("byType=" + registered.get("core").id());
        System.out.println("explicit=" + registered.get("internal").id());
    }
}
~~~

Plain Java commands, run from the directory containing the file:

~~~bash
javac ManualCandidateFilter.java
java ManualCandidateFilter
~~~

Exact stdout:

~~~text
registered=core,internal
eligible=core
byType=CORE
explicit=INTERNAL
~~~

**This is a mental model using Java collections, not a replica of Spring's algorithm.** `Map` has no `BeanDefinition`, qualifiers, scopes, or lifecycle. The sole takeaway to see is: objects present in the registry (`registered`) **differ** from objects eligible for automatic selection (`eligible`), yet explicit lookup by name can still retrieve an excluded object.

## 10. XML Pattern `default-autowire-candidates` and Precedence

Beyond per-bean configuration, XML lets you restrict **by bean name pattern** using `default-autowire-candidates` on top-level **`<beans>`**:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd"
       default-autowire-candidates="*Repository,*Gateway">

    <bean id="orderRepository" class="demo.OrderRepository"/>
    <bean id="internalHelper" class="demo.InternalHelper"/>

    <bean id="explicitHelper"
          class="demo.InternalHelper"
          autowire-candidate="true"/>

    <bean id="blockedGateway"
          class="demo.InternalHelper"
          autowire-candidate="false"/>
</beans>
~~~

This is an XML snippet **explaining the policy**, assuming demo classes `demo.OrderRepository`/`demo.InternalHelper` exist in a separate XML project.

The `*Repository,*Gateway` patterns indicate which bean names are eligible **by default** as autowire candidates. If `internalHelper` does not match the pattern, it is excluded by default. However, **explicitly declaring** `autowire-candidate="true"` or `"false"` on an individual bean definition **takes precedence** over the pattern.

**Why use names to govern candidate eligibility?** Sometimes a module contains many internal adapters that should not be exposed to global autowiring, and naming conventions are already strict. However, renaming a bean can change how it is filtered, so this approach requires clear conventions and tests.

**Do not confuse** XML `default-autowire-candidates` (a pattern matched against bean names) with Java `@Bean(defaultCandidate=false)` (restricted default selection by type/qualifier). These two mechanisms differ in both declaration site and semantics.

## 11. When to Use and When Not to Use Exclusion

### Appropriate Scenarios

- **Infrastructure helper:** an implementation sharing an interface with business beans yet intended only for internal use by a specific adapter.
- **Diagnostic/probe client:** a simulated client used to test another processing path that must never be picked automatically by production services.
- **Legacy compatibility bean:** a bean that must remain registered to preserve explicit references in older configuration while staying out of new type-based autowiring.
- **Separating public API and internal delegate:** a bean supplied via explicit wiring at the composition root, while other components injecting the interface by type need a clear default implementation.

### Situations Where It Should Not Mask Other Problems

- Multiple implementations share a type and all are valid for different use cases: use **qualifiers** or a `@Primary` policy rather than arbitrarily excluding a bean another module needs.
- A **genuinely optional** dependency: express it via `Optional<T>`, `ObjectProvider<T>`, an optional setter, or a valid no-op strategy; exclusion does not turn a required dependency into an optional one.
- Circular dependencies: changing candidate filtering does not break dependency cycles between objects.
- A bean is missing due to registration/configuration errors: setting `autowireCandidate=false` makes debugging harder.
- Using the flag to avoid designing interfaces with clear responsibilities: if an interface is implemented by 20 unrelated delegates, revisit the abstraction and module boundaries.

Also do not attach `@Primary` to an excluded bean hoping it will be chosen again. **Primary sets precedence among candidates; exclusion removes a bean from that set.**

## 12. Common Errors and How to Debug in Order

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Bean appears in `getBeanNamesForType` yet is not injected | `autowireCandidate=false` or qualifier/generic filtering | Check `BeanDefinition.isAutowireCandidate()` and the injection point |
| `@Autowired Transport` reports missing bean despite one bean of that type existing | That bean is excluded from autowiring | Remove the exclusion if contractually appropriate, or use explicit wiring |
| Adding `@Qualifier("internalTransport")` still fails | Qualifier does not turn an excluded bean into a type candidate | Use an appropriate explicit by-name reference or update metadata intentionally |
| `@Primary` on an excluded bean has no effect | Primary selects only among eligible candidates | Check both `isPrimary` **and** `isAutowireCandidate` |
| `List<Transport>` misses a registered bean | Collection injection also filters candidate eligibility | Distinguish an injected list from `getBeansOfType` |
| `Map<String,Transport>` differs from type discovery map | Autowire points enforce candidate rules | Inspect `getBeanNamesForType` then candidate filtering |
| `getBean("internalTransport")` still succeeds | Exclusion neither deletes the definition nor blocks name lookup | Expected behavior |
| Excluded bean still gets `Settings` injected into itself | The flag restricts the bean as a dependency for others | Expected behavior; note the two dependency directions |
| `defaultCandidate=false` still injects via qualifier | Only excluded from default/plain type selection | Expected behavior; distinct from `autowireCandidate=false` |
| Plain `Transport` picks an unexpected implementation | Bean metadata, primary/fallback/`defaultCandidate`, or injection-point name | Determine actual candidates per context |
| `NoUniqueBeanDefinitionException` even after excluding one bean | Multiple eligible candidates still remain | Use qualifiers/primary or split the interface sensibly |
| XML pattern excludes a bean unexpectedly | Bean name does not match `default-autowire-candidates` | Check patterns and explicit overrides |
| `@Bean` method fails to compile after adding attribute | Spring version/API differs from assumption | Use the matching Spring line and check the actual `@Bean` Javadoc |
| `NoSuchBeanDefinitionException` while type discovery finds beans | Candidate eligibility, qualifiers, or scope/hierarchy | Read the cause chain instead of assuming the class does not exist |
| Java compilation reports missing Spring annotations | Broken Maven dependency/classpath | Inspect `spring-context` and JDK setup |
| Bean is not instantiated even though registered | `@Lazy`, prototype, scope, or other lifecycle settings | Do not equate registration with eager instantiation |

### Minimal Diagnostic Workflow

1. Confirm the **right context**, bean registrations, and interface/implementation type compatibility.
2. Call `getBeanNamesForType(T.class)` to see **which names** are discovered.
3. For any suspect bean, inspect `BeanDefinition.isAutowireCandidate()`, `isDefaultCandidate()`, `isPrimary()`, and `isFallback()` where supported by that API version.
4. Check the **injection point**: `@Autowired T`, `List<T>`, `Map<String,T>`, qualifiers, generic signatures, or explicit name reference?
5. Check remaining factors: Java modules/classloaders, proxies, scopes, primary/fallback, XML patterns, and parent contexts if present.
6. Read the **root cause** of `UnsatisfiedDependencyException`, `NoSuchBeanDefinitionException`, and `NoUniqueBeanDefinitionException`, rather than matching fragile exception wording.
7. Keep dedicated integration tests for the composition root; keep business unit tests Spring-free using fakes via constructors where appropriate.

## 13. Self-Verification Exercises and Checklist

Test each change **on a copy** of the project, restoring the original source before comparing against section 8's stdout:

1. **Remove exclusion:** change `@Bean(name="internalTransport",autowireCandidate=false)` to a normal bean. Predict `main.injectedList` and `main.injectedMap` will include INTERNAL; since INTERNAL also has `@Primary`, `main.selected` switches to INTERNAL.
2. **Remove primary only:** keep `autowireCandidate=false` and remove `@Primary`. Predict `Report` still selects ACTIVE, because `internal` does not participate in autowiring anyway.
3. **Try using a qualifier to fetch the excluded bean:** add `@Qualifier("internalTransport") Transport t` to another bean. Predict failure because type-based autowiring finds no eligible candidate.
4. **Lookup by name:** compare `getBean("internalTransport", Transport.class)` twice; with default singleton scope, object identity must match.
5. **Type-discovery snapshot:** compare `getBeanNamesForType(Transport.class)` with `Report.injectedNames()` and explain the difference.
6. **No eligible bean:** run `ExcludedOnlyConfig` standalone and locate the failure at injection point `needsTransport(Transport candidate)`, not because Java lacks the `Transport` type.
7. **Keep `defaultCandidate=false`:** test with `@Qualifier("restrictedTransport")` and without the qualifier on a copy; explain how it differs from hard exclusion.
8. **Turn restricted into excluded:** replace `defaultCandidate=false` with `autowireCandidate=false` in `RestrictedConfig`. Predict the qualifier is no longer enough to select the bean.
9. **Make excluded bean prototype:** add `@Scope("prototype")` and call `getBean("internalTransport")` twice; compare by-name lookup still working against instance identity.
10. **Add a second eligible bean:** register an additional `backupTransport` without primary. Predict a required `Transport selected` becomes ambiguous, even though excluded `internal` remains filtered out.
11. **XML configuration:** test `autowire-candidate="false"` with explicit XML `ref` and observe the bean remains usable via name reference.
12. **XML pattern:** use `default-autowire-candidates="*Transport"` and observe non-matching bean names are filtered unless explicitly overridden.
13. **Print metadata before injection:** write a helper inspecting definition flags and type names before requesting consumer beans.
14. **Dependencies of an excluded bean:** declare factory method `internalTransport(Settings settings)` and prove the excluded bean **still receives `Settings`** from the container.
15. **Plain Java compilation:** run `ManualCandidateFilter`, add a registry entry and adjust the excluded set, then compare registered vs. eligible lists.

### Mastery Checklist

- [ ] Understand **registered bean**, **type match**, **autowire candidate**, and **chosen bean** as distinct stages.
- [ ] Know XML `autowire-candidate="false"` and Java `@Bean(autowireCandidate=false)`.
- [ ] Know an excluded bean can still be retrieved via `getBean(name)` / explicit ref.
- [ ] Know type-discovery APIs can still display excluded beans.
- [ ] Know both single-bean injection **and** injected `List`/`Map` enforce candidate eligibility.
- [ ] Know `@Primary` and `@Qualifier` do not break hard exclusion.
- [ ] Distinguish **`defaultCandidate=false`** from **`autowireCandidate=false`**.
- [ ] Understand an excluded bean can still **receive its own dependencies**.
- [ ] Know the effects of XML `default-autowire-candidates` patterns and overrides.
- [ ] Run the Spring Maven Java 17 demo for the exact 19 stdout lines and plain Java for the 4 lines.
- [ ] Debug using bean definition metadata + injection point rather than guessing from type names.

## 14. Summary and Official Sources

`autowire-candidate=false` sets a **participation boundary for dependency injection**: the bean stays alive inside the Spring container yet **does not become a type-based autowire candidate** where the same interface/superclass is requested. Explicit references by name still work.

`defaultCandidate=false` is a **softer** restriction introduced in Spring 6.2+: it avoids plain by-type injection while still permitting qualified injection when metadata matches. `@Primary`/`@Fallback` only govern **precedence within the eligible candidate set** without altering exclusion flags.

Documentation sources:
- [Spring Framework — Autowiring Collaborators / Excluding a Bean from Autowiring](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-autowire.html)
- [Spring Framework — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework — Primary and Fallback](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring API — `@Bean`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Bean.html)
- [Spring API — `BeanDefinition`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/BeanDefinition.html)
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)

**Takeaway:** If Spring “sees” a bean by type yet refuses to autowire it, check **`isAutowireCandidate()` before adding `@Primary` or `@Qualifier`**. Choosing the right configuration level among hard exclusion, restricted-default candidate, and primary preference keeps DI clear, maintainable, and free of unexpected dependency ambiguities.