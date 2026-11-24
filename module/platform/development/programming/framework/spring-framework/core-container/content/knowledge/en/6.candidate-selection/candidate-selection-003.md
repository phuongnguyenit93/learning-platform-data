# Prioritizing a Candidate with `@Primary` in Spring Core Container

## 1. The Problem: Multiple Beans of the Same Type, Yet Only One Dependency Is Needed

Spring IoC Container allows **multiple bean definitions compatible with the same Java type**. For example, `FastTransport`, `SafeTransport`, and `BackupTransport` all implement the `Transport` interface. A service with a constructor taking `Transport` requires **a single reference**, even though all three are assignable to that parameter.

Without an appropriate resolution rule, injecting a single dependency by type can fail because **it is impossible to determine which bean to pick** (`NoUniqueBeanDefinitionException`, sometimes wrapped in `UnsatisfiedDependencyException`).

`@Primary`, in package `org.springframework.context.annotation`, marks **a preferred bean** among autowire candidates that satisfy the same injection point. When after filtering there is **exactly one valid primary bean**, Spring uses that bean for a single-valued dependency.

~~~java
// Illustrative snippet inside a @Configuration class:
@Bean("fastTransport")
@Primary
Transport fastTransport() {
    return new FastTransport();
}

@Bean("safeTransport")
Transport safeTransport() {
    return new SafeTransport();
}
~~~

In normal cases, an injection point requesting `Transport` receives the `fastTransport` bean, provided both beans are registered and no other filtering condition disqualifies the primary.

**What `@Primary` does not do:** it does not create beans, change Java types, change bean names, change scopes, guarantee thread safety, remove other beans, make every injection point receive the primary, or override a qualifier that explicitly specifies another bean.

The learning goal is to understand **when Spring needs a primary, how primary participates in candidate selection, its limitations, and control cases**. The lesson uses Java 17+, Spring Framework 7.0.9, and Maven, with complete code, run commands, and expected stdout.

## 2. Where to Declare `@Primary` and Its Scope of Effect

### On a `@Bean` Method

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    @Primary
    Transport fastTransport() {
        return new FastTransport();
    }
}
~~~

When using **Java configuration** with `@Bean`, place `@Primary` on the **factory method registering the bean** you want to prioritize. Primary metadata belongs to the **bean definition**, not a state that the JVM attaches to every instance of the same class.

### On a Component-Scanned Class

~~~java
@Component
@Primary
class FastTransport implements Transport {
    @Override
    public String id() {
        return "FAST";
    }
}
~~~

The class must be within **component scan** scope or registered via a Spring-supported mechanism. Merely having a `@Component @Primary` class on the classpath does not mean every context contains that bean.

### Equivalent XML Configuration

~~~xml
<bean id="fastTransport" class="demo.FastTransport" primary="true"/>
<bean id="safeTransport" class="demo.SafeTransport"/>
~~~

This XML is an **illustrative snippet**, not a file used in the Maven project in section 7; in that project, the classes are declared inside another Java source file, so `demo.FastTransport` is merely an example of a corresponding top-level public class. The XML `primary="true"` attribute expresses the same Spring bean-definition priority metadata.

**Important note on annotation placement:** If a Java class carries `@Primary` yet that bean is registered via a specific `@Bean` method, do not assume the class-level annotation will always be the metadata Spring uses for the method-registered definition. Declare `@Primary` on the **`@Bean` method** so the contract is unambiguous.

**Scope of precedence:** primary applies to bean definitions eligible to be considered as a **candidate for a dependency currently being resolved**, not as a “global preferred bean” that overrides every requirement. Another interface or a different qualifier can produce a different candidate set.

## 3. How Spring Selects a Candidate

When Spring needs to supply `Transport` to a constructor, method, or field, the conceptual flow is:

~~~text
Injection point requests Transport
                |
                v
   Find type-compatible beans
                |
                v
  Filter autowire candidates & metadata
    (qualifier, generic, other conditions)
                |
                v
    One candidate or multiple candidates?
          /                 \
    One eligible        Multiple eligible
          |                    |
          v                    v
      Select it        Exactly one @Primary?
                            /        \
                          Yes         No
                           |           |
                           v           v
                     Select primary  Check other
                                    precedence rules
                                    or report ambiguity
~~~

This is a **diagram for learning the mechanism**, not the exact branch-by-branch order of `DefaultListableBeanFactory`. Spring also considers `@Fallback`, default-candidate, name matching, self-references, priority, and special rules per injection point.

Practical conclusions:
- **A single candidate:** the dependency is supplied **without** needing `@Primary`.
- **Multiple candidates, one primary:** primary can resolve a single-bean request.
- **Multiple candidates, no primary:** other resolution rules may still apply; otherwise, a non-unique bean error occurs.
- **Multiple candidates, two or more primaries:** primary can no longer select **one** bean; ambiguity can still be reported.
- **Primary does not match type/qualifier:** it is excluded from the final candidate set; it cannot win on its own.
- **No candidate:** `@Primary` on an unrelated type does not solve a missing bean problem.

A primary bean is typically **pre-instantiated** when it is an eager singleton in an application context, yet `@Primary` **does not by itself dictate when a bean is created**. Scope, lazy, and factory rules still apply as usual.

## 4. Key Distinction: Single-Bean Injection vs. Multi-Bean Injection

`@Primary` primarily affects **single-valued dependencies**, for example:

~~~java
@Autowired
private Transport defaultTransport;
~~~

Or constructor:

~~~java
// Java 17 snippet: constructor injection.
final class Dispatcher {
    private final Transport transport;

    Dispatcher(Transport transport) {
        this.transport = transport;
    }
}
~~~

Conversely, Spring can inject **all eligible candidates** into:

~~~java
@Autowired
private List<Transport> transports;

@Autowired
private Map<String, Transport> transportByName;
~~~

With three autowire-eligible beans:
- An unqualified `Transport` typically receives the **primary**.
- A `List<Transport>` can contain **all three** (including eligible primary and fallback beans).
- A `Map<String,Transport>` can contain all three; **keys are bean names**, not Java class names.
- `@Primary` **does not** exclude `safeTransport` or `backupTransport` from the collection or map.
- `@Order` or `Ordered` (when present) affects **list ordering**, without turning a bean into a primary.

Therefore, do not use the element count of `List<Transport>` to conclude that primary “isn’t working”. Primary is a signal when the container must **choose a single reference** among multiple candidates; collections have a different contract.

In the complete example, list results are **sorted** before printing so they do not depend on bean registration order or ordering metadata. This verifies membership without imposing an order that is not guaranteed across all configurations.

## 5. `@Qualifier` Can Select a Different Bean Than the Primary

Suppose:
- `fastTransport` is marked `@Primary`;
- `safeTransport` also has type `Transport`, but is **not** primary;
- an injection point carries `@Qualifier("safeTransport")`.

~~~java
// Snippet inside a @Bean factory method:
@Bean
Dispatcher safeDispatcher(
        @Qualifier("safeTransport") Transport transport) {
    return new Dispatcher(transport);
}
~~~

Here, the qualifier narrows the **candidate set** by metadata/name compatible with the requested type. Only `safeTransport` satisfies the condition, so Spring selects it **even though `fastTransport` is primary**.

**Do not say “primary always overrides qualifier”.** If the primary bean does not satisfy the qualifier, it is not an eligible candidate for that injection point. Type and qualifier rules must be evaluated before concluding who wins.

Comparison:

| Injection point | Matching candidates | Typical outcome |
| --- | --- | --- |
| Unqualified `Transport t` | FAST, SAFE, BACKUP | FAST when FAST is primary |
| `@Qualifier("safeTransport") Transport t` | SAFE | SAFE |
| `@Qualifier("missingTransport") Transport t` | No matching bean | Required dependency error |
| `SmsTransport t` | Only beans of type `SmsTransport` | Does not pick FAST if FAST is not assignable |
| `List<Transport> list` | Eligible `Transport` beans | Multiple beans, not just FAST |

`@Qualifier` is fundamentally a **filter within the set of type matches**, not an instruction to arbitrarily grab a bean of another type. For requesting an **exact bean name** on a field/setter, `jakarta.annotation.Resource(name="...")` is a separate by-name mechanism, though it is not needed to explain `@Primary`.

**Do not rely on parameter names in place of explicit qualifiers** when code has multiple implementations. Spring may consider field/parameter names alongside other criteria; renaming a field or changing compiler metadata can alter behavior unexpectedly.

## 6. `@Fallback` Is a Different Strategy, Not Inverted `@Primary`

Spring Framework 6.2+ provides `@Fallback`:

~~~java
@Bean
Transport fastTransport() {
    return new FastTransport();
}

@Bean
@Fallback
Transport backupTransport() {
    return new BackupTransport();
}
~~~

When there is **one regular bean** (non-fallback) and all remaining beans are fallbacks, that regular bean can be chosen as the default for a single dependency. In the example with only regular FAST and fallback BACKUP, requesting a single `Transport` selects **FAST even without `@Primary`**.

Brief comparison:

| Concept | Meaning |
| --- | --- |
| `@Primary` | Prioritizes the marked bean when multiple qualified candidates exist for a **single dependency** |
| `@Fallback` | Marks a bean as a fallback, allowing remaining regular candidates to be preferred |
| `@Qualifier` | Filters candidates according to the injection point's condition |
| `@Bean(autowireCandidate=false)` | Excludes a bean from standard autowiring |
| `@Order` | Orders elements when collecting multiple beans under applicable rules |
| `@Lazy` | Concerns initialization timing; not candidate selection precedence |
| `@Scope` | Defines instance scope; does not select alternative beans on its own |

A fallback bean **remains a real bean** and can be looked up by name. `@Fallback` does not necessarily exclude a bean from `List<Transport>`. Under Spring's mechanism, type-matching beans can still participate in collection/map injection depending on autowire eligibility.

Combining primary, fallback, qualifiers, and default-candidate flags across many beans can become hard to read: inspect the **actual candidate set at each injection point**, rather than guessing from a single annotation in isolation. In the project, simple configurations are intentionally used to prove each distinction.

## 7. Demo with Spring Framework 7.0.9 + Maven + Java 17

The demo sets up five independent scenarios:

1. **PrimaryConfig:** three beans of the same type; FAST is `@Primary`, BACKUP is `@Fallback`. A single dependency selects FAST, `@Qualifier("safeTransport")` selects SAFE, and collection/map contain all three.
2. **NoPrimaryConfig:** FAST and SAFE are both regular; a single type lookup without a resolution criterion → **non-unique** error.
3. **TwoPrimaryConfig:** FAST and SAFE are **both `@Primary`** → cannot pick a single unique primary.
4. **FallbackOnlyConfig:** FAST is regular and SAFE is `@Fallback`, with no primary → FAST is still chosen.
5. **OnlyOneConfig:** only FAST → Spring selects FAST without requiring `@Primary`.

Each scenario uses a **separate** `AnnotationConfigApplicationContext`, avoiding accidental bean registrations from prior configurations. Failure scenarios are caught intentionally; expected stdout is not pinned to Spring exception messages or stack traces.

### 7.1. Project Structure

~~~text
primary-selection-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── PrimarySelectionDemo.java
~~~

Requires **JDK 17+**, **Maven 3.9+**, and access to download Spring dependencies from Maven Central/a mirror on the first run. This is **pure Spring Framework**, requiring no Spring Boot, servlet container, or database.

### 7.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>primary-selection-demo</artifactId>
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
                    <mainClass>demo.PrimarySelectionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The Maven compiler plugin runs `javac` targeting Java 17; Exec Maven Plugin puts Spring dependencies on the runtime classpath. `spring-context` pulls in the required Spring modules via Maven dependency resolution; do not manually pass individual JARs on the CLI.

### 7.3. File `src/main/java/demo/PrimarySelectionDemo.java`

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Fallback;
import org.springframework.context.annotation.Primary;

public final class PrimarySelectionDemo {
    private PrimarySelectionDemo() {
    }

    @FunctionalInterface
    interface Transport {
        String id();
    }

    static final class FastTransport implements Transport {
        @Override
        public String id() {
            return "FAST";
        }
    }

    static final class SafeTransport implements Transport {
        @Override
        public String id() {
            return "SAFE";
        }
    }

    static final class BackupTransport implements Transport {
        @Override
        public String id() {
            return "BACKUP";
        }
    }

    static final class Dashboard {
        private final Transport selected;
        private final Transport qualified;
        private final List<Transport> all;
        private final Map<String, Transport> byName;

        Dashboard(Transport selected, Transport qualified,
                List<Transport> all, Map<String, Transport> byName) {
            this.selected = selected;
            this.qualified = qualified;
            this.all = all;
            this.byName = byName;
        }

        String selectedId() {
            return selected.id();
        }

        String qualifiedId() {
            return qualified.id();
        }

        boolean sameAs(Transport expected) {
            return selected == expected;
        }

        boolean qualifiedSameAs(Transport expected) {
            return qualified == expected;
        }

        String allIds() {
            return all.stream().map(Transport::id)
                    .sorted().collect(Collectors.joining(","));
        }

        String beanNames() {
            return byName.keySet().stream()
                    .sorted().collect(Collectors.joining(","));
        }

        boolean hasBackup() {
            return byName.containsKey("backupTransport");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class PrimaryConfig {
        @Bean("fastTransport")
        @Primary
        public Transport fastTransport() {
            return new FastTransport();
        }

        @Bean("safeTransport")
        public Transport safeTransport() {
            return new SafeTransport();
        }

        @Bean("backupTransport")
        @Fallback
        public Transport backupTransport() {
            return new BackupTransport();
        }

        @Bean
        public Dashboard dashboard(Transport transport,
                @Qualifier("safeTransport") Transport safeTransport,
                List<Transport> transports,
                Map<String, Transport> transportByName) {
            return new Dashboard(transport, safeTransport,
                    transports, transportByName);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class NoPrimaryConfig {
        @Bean
        public Transport fastTransport() {
            return new FastTransport();
        }

        @Bean
        public Transport safeTransport() {
            return new SafeTransport();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class TwoPrimaryConfig {
        @Bean
        @Primary
        public Transport fastTransport() {
            return new FastTransport();
        }

        @Bean
        @Primary
        public Transport safeTransport() {
            return new SafeTransport();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class FallbackOnlyConfig {
        @Bean
        public Transport fastTransport() {
            return new FastTransport();
        }

        @Bean
        @Fallback
        public Transport safeTransport() {
            return new SafeTransport();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class OnlyOneConfig {
        @Bean
        public Transport fastTransport() {
            return new FastTransport();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(PrimaryConfig.class)) {
            Dashboard dashboard = context.getBean(Dashboard.class);
            Transport fast = context.getBean("fastTransport", Transport.class);
            Transport safe = context.getBean("safeTransport", Transport.class);

            System.out.println("main.selected=" + dashboard.selectedId());
            System.out.println("main.qualified=" + dashboard.qualifiedId());
            System.out.println("main.samePrimary="
                    + dashboard.sameAs(fast));
            System.out.println("main.sameQualified="
                    + dashboard.qualifiedSameAs(safe));
            System.out.println("main.allIds=" + dashboard.allIds());
            System.out.println("main.mapNames=" + dashboard.beanNames());
            System.out.println("main.mapHasFallback="
                    + dashboard.hasBackup());
            System.out.println("main.byType="
                    + context.getBean(Transport.class).id());
            System.out.println("main.fast.primary="
                    + context.getBeanFactory()
                            .getBeanDefinition("fastTransport").isPrimary());
            System.out.println("main.safe.primary="
                    + context.getBeanFactory()
                            .getBeanDefinition("safeTransport").isPrimary());
            System.out.println("main.backup.fallback="
                    + context.getBeanFactory()
                            .getBeanDefinition("backupTransport").isFallback());
            System.out.println("main.backup.byName="
                    + context.getBean("backupTransport", Transport.class).id());
        }

        try (var context =
                new AnnotationConfigApplicationContext(NoPrimaryConfig.class)) {
            context.getBean(Transport.class);
            System.out.println("noPrimary.unexpected");
        } catch (NoUniqueBeanDefinitionException expected) {
            System.out.println("noPrimary.ambiguous=true");
        }

        try (var context =
                new AnnotationConfigApplicationContext(TwoPrimaryConfig.class)) {
            context.getBean(Transport.class);
            System.out.println("twoPrimary.unexpected");
        } catch (NoUniqueBeanDefinitionException expected) {
            System.out.println("twoPrimary.ambiguous=true");
        }

        try (var context =
                new AnnotationConfigApplicationContext(FallbackOnlyConfig.class)) {
            System.out.println("fallbackOnly.selected="
                    + context.getBean(Transport.class).id());
            System.out.println("fallbackOnly.backup="
                    + context.getBean("safeTransport", Transport.class).id());
        }

        try (var context =
                new AnnotationConfigApplicationContext(OnlyOneConfig.class)) {
            System.out.println("onlyOne.selected="
                    + context.getBean(Transport.class).id());
            System.out.println("onlyOne.isPrimary="
                    + context.getBeanFactory()
                            .getBeanDefinition("fastTransport").isPrimary());
        }
    }
}
~~~

### 7.4. How to Read the Code

- **PrimaryConfig:** FAST, SAFE, and BACKUP are all of type `Transport`. FAST is marked `@Primary`, and BACKUP has `@Fallback`.
- **Parameter `Transport transport` of `dashboard(...)`:** without a qualifier, Spring picks FAST because it is the valid primary; `selectedId()="FAST"`.
- **Parameter `@Qualifier("safeTransport") Transport safeTransport`:** only SAFE satisfies the qualifier and is passed to `Dashboard.qualified`, not FAST.
- **`List<Transport>` / `Map<String,Transport>`:** all three beans still enter the collection/map in the example; `@Primary` and `@Fallback` do not remove them from type matches. Output is sorted for stability.
- **BeanDefinition metadata:** `isPrimary()` is true only for FAST; `isFallback()` is true for BACKUP. These are bean definition metadata, not static flags on the Java classes.
- **NoPrimaryConfig:** only FAST and SAFE, with no qualifier and no primary; `getBean(Transport.class)` cannot pick a unique candidate.
- **TwoPrimaryConfig:** two beans are both primary, likewise lacking a rule to pick a single one. The annotation does not mean “pick the first registered bean”.
- **FallbackOnlyConfig:** FAST is regular and SAFE is fallback; with exactly one regular candidate, Spring selects FAST. Yet SAFE can still be retrieved by name.
- **OnlyOneConfig:** only FAST exists; `getBean(Transport.class)` works even though `isPrimary=false`. Do not put `@Primary` on every bean when only one implementation exists.

**Compilability:** the file uses Java 17 and `@Configuration`, `@Bean`, `@Primary`, `@Fallback`, and `@Qualifier` from Spring 7.0.9; no JUnit/Mockito or XML is needed. `@FunctionalInterface` on `Transport` is valid because it declares only one abstract method `id()` besides methods from `Object`.

## 8. Running the CLI and Verifying Stdout

Inside the `primary-selection-demo` directory containing `pom.xml`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

The first three commands check JDK/Maven versions and produce machine-dependent output. The last command compiles via Maven Compiler Plugin (`--release 17`) and then runs `demo.PrimarySelectionDemo`.

**18 stdout lines printed by the program itself** (excluding Maven/Spring logs and environment-dependent reports/stack traces):

~~~text
main.selected=FAST
main.qualified=SAFE
main.samePrimary=true
main.sameQualified=true
main.allIds=BACKUP,FAST,SAFE
main.mapNames=backupTransport,fastTransport,safeTransport
main.mapHasFallback=true
main.byType=FAST
main.fast.primary=true
main.safe.primary=false
main.backup.fallback=true
main.backup.byName=BACKUP
noPrimary.ambiguous=true
twoPrimary.ambiguous=true
fallbackOnly.selected=FAST
fallbackOnly.backup=SAFE
onlyOne.selected=FAST
onlyOne.isPrimary=false
~~~

These results do not rely on randomness, time, or network. `Map.keySet()` and `List` are sorted before printing. The two intentionally ambiguous contexts may emit diagnostics outside application stdout; the program catches the exact `NoUniqueBeanDefinitionException` type and prints deterministic booleans.

**Key takeaways:**

| Output | What it proves |
| --- | --- |
| `main.selected=FAST` | FAST is chosen for an unqualified `Transport` dependency |
| `main.qualified=SAFE` | Qualifier selects SAFE even though FAST is primary |
| `main.samePrimary=true` | Dependency and by-name lookup for FAST share the same singleton reference in the context |
| `main.allIds=BACKUP,FAST,SAFE` | Primary/fallback do not exclude beans from an injected list |
| `main.mapNames=...` | All eligible beans still appear in the injected map keyed by bean names |
| `main.fast.primary=true` | Metadata on the FAST bean definition recorded `@Primary` |
| `noPrimary.ambiguous=true` | Two equal candidates are not automatically disambiguated |
| `twoPrimary.ambiguous=true` | Marking two primaries does not create a single-choice criterion |
| `fallbackOnly.selected=FAST` | `@Fallback` can let a regular candidate win without using primary |
| `onlyOne.isPrimary=false` | A single candidate does not need to be marked primary |

If you intentionally modify the configuration, output will change; compare against the original source before judging pass/fail. Do not pin exception messages because different Spring versions or logging setups may phrase errors differently.

## 9. Plain Java 17 Example: Thinking About Choosing a Default

`@Primary` is a Spring rule, yet the logic can be understood in plain Java: a registry with multiple implementations and a **default selection name**. Create a separate `ManualPrimaryChoice.java` file (no Maven/Spring dependency):

~~~java
import java.util.Map;

public class ManualPrimaryChoice {
    interface Transport {
        String id();
    }

    public static void main(String[] args) {
        Map<String, Transport> registry = Map.of(
                "fast", () -> "FAST",
                "safe", () -> "SAFE");

        String defaultName = "fast";
        Transport selected = registry.get(defaultName);
        Transport explicitlyChosen = registry.get("safe");

        System.out.println("default=" + selected.id());
        System.out.println("explicit=" + explicitlyChosen.id());
        System.out.println("available=" + registry.size());
        System.out.println("same=" + (selected == explicitlyChosen));
    }
}
~~~

Run with JDK 17+ in the directory containing the file:

~~~bash
javac ManualPrimaryChoice.java
java ManualPrimaryChoice
~~~

Stdout:

~~~text
default=FAST
explicit=SAFE
available=2
same=false
~~~

This is **not** how Spring internally stores primary: we constructed `Map` and `defaultName` manually, without a BeanFactory, type filtering, or lifecycle. It merely illustrates the idea of **“having multiple valid options, while designating one default choice when no further specification is given”**.

Spring layers on other factors: bean metadata, `@Qualifier`, fallback, generic types, scopes, conditional registrations, and exceptions when resolution fails. Do not replace Spring's BeanFactory with a global map in business code without a specific architectural reason.

## 10. Situations Requiring Extra Care

### 10.1. Primary Only Applies Within the Eligible Candidate Set

If bean FAST is given `autowireCandidate=false` or does not satisfy the injection point's qualifier/generics, `@Primary` does not force Spring to inject it. A bean excluded from autowiring can still be looked up by name in appropriate cases, yet **it is no longer a candidate to choose from at that injection point**.

If bean FAST does not have a type compatible with `Transport`, do not expect `@Primary` to make the JVM cast an object of the wrong interface.

### 10.2. Primary and Generic Types

Suppose there are beans `Store<String>` and `Store<Integer>`. Spring can use **generic type arguments as implicit qualifiers**. A `Store<Integer>` marked primary is not necessarily a candidate for an injection point requesting `Store<String>`. Declare concrete factory method return types so Spring has reliable generic metadata.

### 10.3. Primary and Parent/Child Contexts

A system can have multiple `ApplicationContext` instances (parent/child). Bean visibility and local overrides can affect the candidate set; primary metadata in a parent context does not automatically turn every lookup in a child context into a JVM-wide rule.

Some type-discovery APIs such as `getBeanNamesForType` also have local scope distinct from ancestor-aware utilities. When debugging, state explicitly **which context is resolving the dependency**.

### 10.4. Primary and AOP Proxies

A proxy can alter the runtime class visible via `getClass()` or expose only interfaces, depending on JDK dynamic proxy vs. class-based proxy. `@Primary` does not fix type assignability or synthesize a missing interface. If an injection point demands a concrete class that the proxy is incompatible with, that must be solved at the type/proxy design level, not by raising precedence.

### 10.5. Primary on a Class vs. XML Registration

The Javadoc for `@Primary` notes limitations regarding metadata sources. With XML `<bean>`, explicitly declare **`primary="true"`** in the bean definition rather than assuming class annotations will be read just like component scanning. With Java `@Bean`, place `@Primary` on the `@Bean` method.

### 10.6. Singleton Scope Does Not Mean a Primary Bean Has One Instance Across the Whole JVM

Default singleton scope belongs to a **bean definition within a single Spring container**. Two independent contexts can create two separate instances of the same `@Bean @Primary`. `@Primary` governs dependency candidate precedence, not scope or lifecycle.

### 10.7. Primary Does Not Replace Fail-Fast When a Required Bean Is Missing

If no implementation satisfies the type, `@Primary` on an unregistered definition does not help. For a required dependency, the container should fail early and report the missing bean rather than silently supplying `null`. If truly optional, express that via `Optional<T>`, a provider, or a contract default strategy; do not use `@Primary` to mask errors.

## 11. Common Errors and How to Diagnose Them

| Symptom | Correct interpretation | Resolution |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` when injecting type `T` | Multiple candidates exist without a single deterministic winner | Inspect type matches; apply one primary or qualifier according to intent |
| Two `@Primary` beans of the same type | No unique primary exists | Pick one default bean, or add qualifiers at individual injection points |
| `@Qualifier("safeTransport")` does not receive primary FAST | Expected behavior: FAST does not match the SAFE qualifier | Check the injection point contract rather than changing primary to fix it |
| `@Primary` is set, yet `getBean("safeTransport")` still returns SAFE | **Explicit by-name** lookup, not by-type selection | Distinguish `getBean(name)` from `getBean(type)` |
| `List<Transport>` contains both FAST and SAFE | Primary only resolves a **single** dependency | Use collections for their intended purpose; filter/sort if needed |
| Primary bean is missing from collection injection | Possibly excluded by type/qualifier/`autowireCandidate` | Check bean registration and candidate filtering |
| Removing `@Primary` still lets injection succeed | Perhaps only one candidate remains, or another qualifier/name/fallback applies | Observe the actual injection point and candidate set |
| Class has `@Primary`, yet the bean is not prioritized | Registration metadata did not come from component scan, or annotation is in the wrong place | For `@Bean`, place `@Primary` on the method; XML uses the `primary` attribute |
| Same-typed beans in 2 contexts behave differently | Candidate sets/hierarchies differ | Inspect the specific context, profiles, registrations, and parent hierarchy |
| Primary bean has a different implementation type | Only type-compatible beans are candidates | Align the contract interface or registered type |
| App runs, yet picks the wrong implementation | `@Primary` was applied too broadly across multiple use cases | Use `@Qualifier` at specific injection points and test the composition root |
| Circular dependencies do not disappear | Primary picks a candidate; it does not fix dependency cycles | Refactor dependency relationships |
| Bean marked `@Primary` fails during initialization | Primary does not bypass constructor/lifecycle failures | Read the root cause of bean creation |
| `@Primary` is not visible in type discovery | Type-discovery APIs usually do not surface priority directly | Inspect bean definition `isPrimary()` or perform the actual lookup |
| Mistaking `@Order` for `@Primary` | Ordering differs from candidate preference | Use the annotation appropriate for the requirement |

**Debugging checklist:** determine whether the injection point needs **one bean or a collection**; verify bean registrations and type compatibility; inspect qualifiers, generics, primary/fallback, and `autowireCandidate`; verify primary metadata on the **bean definition**; then observe `getBean(Type.class)` or a wiring integration test in the **right context**.

## 12. Prediction Exercises Before Running

Apply each change on a copy of the code, restoring the original source between exercises to compare against expected stdout.

1. **Switch primary:** move `@Primary` from FAST to SAFE in `PrimaryConfig`. Predict `main.selected=SAFE`, while `main.qualified=SAFE` stays unchanged.
2. **Remove primary:** delete `@Primary` in `PrimaryConfig` while keeping FAST/SAFE regular. Predict `dashboard(Transport transport,...)` can cause ambiguity during context refresh.
3. **Add a second primary:** add `@Primary` to SAFE while FAST remains primary. Explain why two primaries do not form a “priority order” and why the context can fail because `Dashboard` needs one `Transport`.
4. **Change qualifier:** change `@Qualifier("safeTransport")` to `@Qualifier("fastTransport")`; predict `main.qualified=FAST` and update `main.sameQualified` to compare against the matching reference.
5. **Remove qualifier:** remove `@Qualifier` from the `safeTransport` parameter. Predict both `Transport` parameters will pick primary FAST if no other constraint applies.
6. **Add fallback:** mark SAFE with `@Fallback` (with no primary). Predict which beans still appear in the list/map.
7. **Add an implementation:** create `ExperimentalTransport` and register a new `@Bean`. If FAST stays the sole primary, single injection can still pick FAST while the collection expands.
8. **Switch to collection:** use `List<Transport>` and print `size()`. Why does the count not become 1 just because a primary exists?
9. **Change scope:** put `@Scope("prototype")` on FAST and look it up twice by name to observe identity. Distinguish candidate priority from instance count.
10. **Change declared return type:** declare a `@Bean` with an interface type vs. a concrete class type; observe how metadata affects lookup by implementation type.
11. **Use `@Qualifier` with non-primary SAFE:** confirm the qualifier still selects SAFE; why is primary not the “strongest filter”?
12. **Use XML:** create a standalone definition with `primary="true"` and compare the mechanism with annotating a `@Bean` method.
13. **No bean:** remove all `Transport` beans from a config and call `getBean(Transport.class)`; distinguish `NoSuchBeanDefinitionException` from `NoUniqueBeanDefinitionException`.
14. **Run plain Java:** add a `backup` entry to the map in `ManualPrimaryChoice`; observe that setting a default does not prevent a caller from requesting another key.
15. **Separate tests:** write a `Dashboard` unit test passing fake transports directly, and an integration test using `AnnotationConfigApplicationContext` to verify `@Primary`.

### Completion Checklist

- [ ] Understand `@Primary` as a **preference for a single-valued dependency**, not bean creation or exclusion of other beans.
- [ ] Declare `@Primary` in the right place on a `@Bean` method or component class.
- [ ] Know that a single candidate needs no primary.
- [ ] Know that two primaries can cause ambiguity.
- [ ] Distinguish `@Primary`, `@Qualifier`, `@Fallback`, `@Order`, and `autowireCandidate=false`.
- [ ] Do not confuse `getBean(name)` with `getBean(Type.class)`.
- [ ] Explain why list/map injection still receives multiple beans.
- [ ] Identify scope/context, qualifier, and generic type issues when a primary is not chosen.
- [ ] Run Maven Java 17 to get the exact 18 application stdout lines and plain Java to get the exact 4 lines.
- [ ] Know how to investigate root causes when bean selection is missing or ambiguous.

## 13. Summary and References

**Takeaway:** When multiple bean definitions can satisfy a dependency, `@Primary` marks the bean that should be **preferred** if **one** must be chosen and that bean **remains an eligible candidate** after evaluating type, qualifiers, and related constraints. It does not delete other beans, alter lifecycle/scope, or force an override of an explicit name requirement.

Official documentation:
- [Spring Framework — Primary and Fallback](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring Framework — Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework — Autowiring Collaborators](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-autowire.html)
- [Spring Framework — Java Configuration and @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring API — Primary](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Primary.html)
- [Spring API — Fallback](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Fallback.html)
- [Spring API — BeanDefinition](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/BeanDefinition.html)

**Practical conclusion:** Treat `@Primary` as a **default policy when Spring must pick one candidate**, not a way to paper over every DI error. If a use case needs a specific implementation, use an explicit qualifier; if it needs all implementations, use a collection; if it needs a backup option, consider fallback. Verify each policy with a small context and observable output.