# Resolving a Dependency with Multiple Beans of the Same Type — Spring Framework Core Container

## 1. The Problem: Spring Finds Multiple Type-Compatible Beans, Yet the Dependency Accepts Only One

Suppose an application has a `MessageSender` interface and two Spring beans:

~~~java
@Bean("emailSender")
MessageSender emailSender() {
    return new EmailSender();
}

@Bean("smsSender")
MessageSender smsSender() {
    return new SmsSender();
}
~~~

**Illustrative snippet:** the interface, implementations, and full configuration are omitted here; a runnable Java 17 example is in section 7.

A service requires **exactly one** sender:

~~~java
public AlertService(MessageSender sender) {
    this.sender = java.util.Objects.requireNonNull(sender);
}
~~~

Spring finds the beans compatible with `MessageSender`, but there are currently **two** candidates: `emailSender` and `smsSender`. Without additional guidance sufficient to pick one, the container **must not guess arbitrarily**. For a single-valued dependency, Spring typically throws `NoUniqueBeanDefinitionException` (sometimes wrapped inside `UnsatisfiedDependencyException`/`BeanCreationException` when occurring during service creation).

**Question to answer:** “Among multiple registered beans of the same type, which bean gets passed into this injection point?”

After this lesson, you will be able to:

1. Distinguish **bean name**, **Java type/interface**, **bean candidate**, **injection point**, and bean instance.
2. Tell the difference between **missing candidates** and **multiple candidates**.
3. Choose a default implementation via `@Primary`; understand why **two primaries** remain ambiguous.
4. Use `@Qualifier` to request an appropriate implementation for **a specific injection point**; understand that a qualifier is a *filter over matching types*, not a type-ignoring String reference.
5. Use **Spring Framework 6.2** `@Fallback` to lower a bean's precedence; understand when a fallback bean is still selected.
6. Distinguish **single-bean injection** from **List/Map/array multi-bean injection**, including the role of `@Order`.
7. Understand name matching, `-parameters`, `@Resource`, generic types, and `autowireCandidate`/`defaultCandidate` settings where appropriate.
8. Run a standalone Java 17+ demo with Spring Framework 6.2.19, Maven, and `javac`/`java` commands, matching deterministic stdout.
9. Diagnose and fix ambiguity without masking errors via arbitrary selections, `@Autowired(required=false)`, or a service locator.

**Scope:** *candidate bean selection* mechanisms in Spring Core Container. No Spring Boot, web, database, real email/SMS, test framework, or external DI library is required.

## 2. Distinguishing Three Outcomes When Resolving a Dependency

Given an injection point requesting `MessageSender`:

| Eligible candidate count after selection rules | Typical outcome |
| --- | --- |
| No matching bean | Missing dependency; may throw `NoSuchBeanDefinitionException` or a wrapper |
| One matching bean | Spring injects that bean object |
| Multiple matching beans, no unique choice | Ambiguity; typically `NoUniqueBeanDefinitionException` |
| Multiple beans of the same type, with **one valid @Primary** | Spring selects the primary for single-valued injection |
| Multiple beans of the same type, narrowed to one by **@Qualifier** | Spring selects the candidate matching the qualifier |
| Multiple beans, with **one non-fallback** and `@Fallback` beans | The non-fallback bean is preferred under Spring 6.2 rules |
| Injection point is `List<MessageSender>` | Spring can provide **multiple** beans without forcing a single choice |

**Specifically:** having multiple beans of the same type **is not a registry error**. Two distinct bean names are completely valid. An error arises only when **a consumer wants exactly one instance** and the container cannot pick a unique one (or when a lookup by type is not specific enough).

Two bean definitions sharing the **same bean name** is a different matter — that concerns bean definition registration and overriding policy, not resolving multiple candidates by type.

## 3. Which Layers of Information Does Spring Use to Select a Candidate?

A practical mental model of how a collaborator is found:

~~~mermaid
flowchart TD
    I["Injection point: MessageSender"] --> T["Filter type-compatible beans"]
    T --> N{"Candidate count?"}
    N -->|"0"| X["Missing dependency"]
    N -->|"1"| OK["Select the single bean"]
    N -->|"Multiple"| Q["Evaluate qualifier, primary, fallback, and related rules"]
    Q --> U{"Unique best candidate?"}
    U -->|"Yes"| OK
    U -->|"No"| E["Ambiguous dependency"]
~~~

This is a **mental model**, not a literal specification of every internal step or absolute precedence across all Spring algorithm branches. In practice, Spring uses `DependencyDescriptor`, bean definitions, type metadata, and various resolution rules, including `@Qualifier`, `@Primary`, `@Fallback`, parameter/field name matching, `@Priority`, and candidate status flags.

To apply this accurately, ask in order:

1. **What is the type at the injection point?** The `MessageSender` interface or concrete implementation `EmailSender`? Are generic arguments significant?
2. **Which beans are registered?** Are bean names, factory methods, scopes, and return types clear enough?
3. **Which beans are eligible for autowiring?** Are any marked with `autowireCandidate=false` or restricted metadata?
4. **Does the injection point have a qualifier?** Does it explicitly state “EMAIL”, “SMS”, “fast”, “main”, or a specific bean name?
5. **Among the remaining candidates, is there a primary/fallback policy?** Is there a single unique choice?
6. **Is there a name match on the injection point?** Were parameter names preserved at compile time?
7. **Does the consumer need one or many?** If it needs all of them, collection injection is usually more appropriate than picking arbitrarily.

**Do not rely on method declaration order in source code as a contract for selecting a single bean.** Registering later, having an alphabetically earlier name, or being scanned first is not a business mechanism replacing explicit qualifiers or `@Primary`.

## 4. @Primary: Selecting a Default Bean When Multiple Beans Share a Type

`@Primary` marks a preferred candidate for a **single-valued dependency** provided that bean still satisfies the type, qualifier, and autowire eligibility conditions. For instance, with `emailSender` and `smsSender` both of type `MessageSender`, marking EMAIL as primary lets a `MessageSender sender` parameter receive EMAIL without forcing every consumer to specify a qualifier.

A valid `@Qualifier("smsSender")` at the injection point still narrows the choice to SMS. Two primaries satisfying the same dependency do not produce a unique default. Primary also does not remove SMS from `List<MessageSender>` or `Map<String, MessageSender>`. Section 7 verifies these cases; the dedicated lesson on `@Primary` explores bean definitions and edge cases in depth.

## 5. @Qualifier: Narrowing Candidates at a Specific Injection Point

With two `MessageSender` beans, a consumer requiring SMS can declare `@Qualifier("smsSender") MessageSender sender`. A qualifier is a **filter within the set of type-compatible candidates**; a value matching a bean name can be used by Spring to match, but do not think of it as a lookup by name regardless of type. A qualifier can describe a role such as `transactional` or `regional` and can be attached to multiple beans.

Therefore, `@Qualifier("fast") List<MessageSender>` can receive multiple beans carrying that label, while `@Qualifier("fast") MessageSender` remains ambiguous if two equal beans remain. In section 7's demo, the qualifier designates a specific SMS or EMAIL bean; the upcoming lesson on `@Qualifier` and custom qualifiers goes deeper into collections, annotation metadata, and domain semantics.

## 6. @Fallback: Lowering a Bean's Precedence in Spring Framework 6.2

Starting in **Spring Framework 6.2**, `org.springframework.context.annotation.Fallback` marks a bean as a low-precedence option when resolving a **single-valued** dependency. If there is exactly one normal bean and the remaining beans are fallbacks, Spring can select the normal bean. If the context has only a single eligible fallback bean, that bean is still injected.

Fallback **does not** remove the bean from the container, prevent it from appearing in collections, defer its initialization, or perform failover when a business call fails. If multiple normal beans or multiple fallback beans satisfy an injection point, another rule is still needed to disambiguate. `FallbackConfig` and `OnlyFallbackConfig` in section 7 demonstrate both branches; the dedicated `@Fallback` lesson covers version constraints and tricky cases.

## 7. Runnable Java 17+ Project: Demonstrating Five Resolution Approaches

Uses **JDK 17+**, Maven, and **Spring Framework 6.2.19**. The version is pinned for reproducibility, not claimed as the latest. Runs pure Spring Core Container, with no Spring Boot/MVC and no real email/SMS.

The demo uses multiple isolated contexts so each scenario carries only the bean definitions under test:

1. **Plain:** two Senders of the same type with no single-choice rule; lookup by type is rejected.
2. **Qualified + collection:** specifying `@Qualifier("emailSender")` retrieves EMAIL, while `List/Map` receives both EMAIL and SMS. `@Order` sorts the List.
3. **Primary:** EMAIL is `@Primary`, so an unqualified lookup gets EMAIL; however, an SMS qualifier still selects SMS.
4. **Fallback:** SMS is `@Fallback` and EMAIL is a regular bean, so email is preferred.
5. **Only fallback:** when only one fallback SMS exists, it remains the sole valid bean.
6. **Two primaries:** both email and SMS are `@Primary`, so there is no unique primary choice.

### 7.1. Directory Structure

~~~text
candidate-resolution-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── CandidateResolutionDemo.java
~~~

### 7.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>candidate-resolution-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.CandidateResolutionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Required transitive Spring dependencies are resolved by Maven. For direct `javac`/`java` execution, all required Spring JARs must be on the classpath.

### 7.3. `src/main/java/demo/CandidateResolutionDemo.java`

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Fallback;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;

public final class CandidateResolutionDemo {
    private CandidateResolutionDemo() {}

    public interface Sender {
        String id();
    }

    public record NamedSender(String id) implements Sender {
        public NamedSender {
            Objects.requireNonNull(id);
        }
    }

    public static final class QualifiedClient {
        private final Sender sender;

        public QualifiedClient(Sender sender) {
            this.sender = Objects.requireNonNull(sender);
        }

        public String selected() {
            return sender.id();
        }
    }

    public static final class CollectionClient {
        private final List<Sender> all;
        private final Map<String, Sender> byName;

        public CollectionClient(
                List<Sender> all, Map<String, Sender> byName) {
            this.all = List.copyOf(all);
            this.byName = Map.copyOf(byName);
        }

        public String orderedIds() {
            return all.stream().map(Sender::id).toList().toString();
        }

        public String sortedBeanNames() {
            return byName.keySet().stream().sorted()
                    .toList().toString();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class PairConfig {
        @Bean("emailSender")
        @Order(2)
        public Sender emailSender() {
            return new NamedSender("EMAIL");
        }

        @Bean("smsSender")
        @Order(1)
        public Sender smsSender() {
            return new NamedSender("SMS");
        }

        @Bean
        public QualifiedClient qualifiedClient(
                @Qualifier("emailSender") Sender sender) {
            return new QualifiedClient(sender);
        }

        @Bean
        public CollectionClient collectionClient(
                List<Sender> senders, Map<String, Sender> sendersByName) {
            return new CollectionClient(senders, sendersByName);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class PrimaryConfig {
        @Bean("emailSender")
        @Primary
        public Sender emailSender() {
            return new NamedSender("EMAIL");
        }

        @Bean("smsSender")
        public Sender smsSender() {
            return new NamedSender("SMS");
        }

        @Bean
        public QualifiedClient qualifiedClient(
                @Qualifier("smsSender") Sender sender) {
            return new QualifiedClient(sender);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class FallbackConfig {
        @Bean("emailSender")
        public Sender emailSender() {
            return new NamedSender("EMAIL");
        }

        @Bean("smsSender")
        @Fallback
        public Sender smsSender() {
            return new NamedSender("SMS");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class OnlyFallbackConfig {
        @Bean("smsSender")
        @Fallback
        public Sender smsSender() {
            return new NamedSender("SMS");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class TwoPrimaryConfig {
        @Bean("emailSender")
        @Primary
        public Sender emailSender() {
            return new NamedSender("EMAIL");
        }

        @Bean("smsSender")
        @Primary
        public Sender smsSender() {
            return new NamedSender("SMS");
        }
    }

    private static void demonstratePair() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(PairConfig.class)) {
            try {
                context.getBean(Sender.class);
                System.out.println("plain=UNEXPECTED");
            } catch (NoUniqueBeanDefinitionException expected) {
                System.out.println("plain=AMBIGUOUS");
            }

            QualifiedClient qualified =
                    context.getBean(QualifiedClient.class);
            CollectionClient all =
                    context.getBean(CollectionClient.class);

            System.out.println("qualified=" + qualified.selected());
            System.out.println("ordered=" + all.orderedIds());
            System.out.println("beanNames=" + all.sortedBeanNames());
        }
    }

    private static void demonstratePrimary() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(PrimaryConfig.class)) {
            Sender selected = context.getBean(Sender.class);
            QualifiedClient sms = context.getBean(QualifiedClient.class);

            System.out.println("primary=" + selected.id());
            System.out.println("qualifierOverPrimary=" + sms.selected());
        }
    }

    private static void demonstrateFallback() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(FallbackConfig.class)) {
            System.out.println("fallbackPreferred=" +
                    context.getBean(Sender.class).id());
        }

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        OnlyFallbackConfig.class)) {
            System.out.println("onlyFallback=" +
                    context.getBean(Sender.class).id());
        }
    }

    private static void demonstrateTwoPrimaries() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(TwoPrimaryConfig.class)) {
            try {
                context.getBean(Sender.class);
                System.out.println("twoPrimaries=UNEXPECTED");
            } catch (NoUniqueBeanDefinitionException expected) {
                System.out.println("twoPrimaries=AMBIGUOUS");
            }
        }
    }

    public static void main(String[] args) {
        demonstratePair();
        demonstratePrimary();
        demonstrateFallback();
        demonstrateTwoPrimaries();
    }
}
~~~

**Runnability and scope analysis of the demo:**

- Only one public top-level class `CandidateResolutionDemo` matches the path/package; records, configs, and consumers are nested types.
- `Sender` is an interface, and `NamedSender` is a Java 17 record implementing the interface and holding a fixed ID; no real network is used.
- Each `@Configuration` class creates an **isolated context**. This separates the policies rather than placing five identically named groups into one registry where they would override one another.
- The `@Bean` methods have return type `Sender`, which suffices for Spring to see two candidates of the same type; they have distinct names without collisions within any single config.
- `PairConfig` marks `smsSender` `@Order(1)` and `emailSender` `@Order(2)` so List injection has order `[SMS, EMAIL]`. This orders the collection; it **does not** pick a single Sender.
- `Map<String, Sender>` receives beans keyed by name; when printing, we **sort the names** so output does not depend on Map iteration order.
- `QualifiedClient` requests a specific Sender via `@Qualifier` placed on the `@Bean` factory-method parameter; `@Bean` methods do not call each other directly.
- `PrimaryConfig` has one primary EMAIL; an explicit SMS qualifier on another consumer still requests SMS.
- `FallbackConfig` has a regular EMAIL bean and a fallback SMS bean; `OnlyFallbackConfig` has only SMS.
- `TwoPrimaryConfig` has two primaries on the same interface; a type-only lookup lacks a unique primary.
- `AnnotationConfigApplicationContext` closes via `try-with-resources`. Expected exceptions occur on **single-valued type lookups** and are intentionally caught; stack traces or version-dependent exception messages are not printed to stdout.
- No clock, randomness, user input, or network is used; all output strings are deterministic from the demo code.

### 7.4. Running Maven and Verifying Stdout

Inside `candidate-resolution-demo`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Exactly nine stdout lines printed by the Java program on a successful run:**

~~~text
plain=AMBIGUOUS
qualified=EMAIL
ordered=[SMS, EMAIL]
beanNames=[emailSender, smsSender]
primary=EMAIL
qualifierOverPrimary=SMS
fallbackPreferred=EMAIL
onlyFallback=SMS
twoPrimaries=AMBIGUOUS
~~~

JDK/Maven version lines and Maven/Spring logs (if any) are not part of the nine lines printed by `main` in the program. Do not lock tests to full exception messages because exception details can change across Spring versions.

### 7.5. Running `javac`/`java` Directly on Linux/macOS and Windows

First generate the JAR dependency list using Maven:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS — bash/zsh:**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/CandidateResolutionDemo.java
java -cp "out:$(cat classpath.txt)" demo.CandidateResolutionDemo
~~~

**Windows — PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/CandidateResolutionDemo.java
java -cp "out;$deps" demo.CandidateResolutionDemo
~~~

The classpath separator is `:` on Unix and `;` on Windows. Both approaches invoke the same `main` method and produce the exact same application output. If `javac` reports missing `org.springframework.*`, inspect dependencies/classpath before debugging bean resolution.

## 8. Why Does List/Map Injection Not Hit the “Multiple Beans” Error?

There is a difference in the **contract** of the injection point:

~~~java
public NotificationBatch(
        List<MessageSender> allSenders,
        Map<String, MessageSender> byName) {
    // allSenders: beans compatible with the MessageSender type
    // byName: key is the bean name; value is the bean object
}
~~~

**Snippet**, not a full Java file. A single-valued `MessageSender` constructor must pick one, whereas List/Map is meant to gather beans of that type. Therefore, having three strategies of the same type is not inherently an error for collection injection.

Spring supports array, collection, and `Map<String,T>` injection. For maps, **the key type should be String** to represent bean names, and the value type must carry the appropriate type information. For `List<T>`, order can be influenced by `@Order`/`Ordered` and then by registration order when no explicit ordering policy applies.

**Do not assume @Order means “pick the bean with the lowest rank”:**

- `@Order(1)` and `@Order(2)` help sort elements inside an injected collection.
- It is **not equivalent** to `@Primary` when a consumer wants only a single `MessageSender`.
- It also **does not necessarily control singleton initialization order**. Startup order depends on the dependency graph, `@DependsOn`, and bootstrap mechanisms.
- If the business logic needs to “try every sender in order”, an ordered `List<MessageSender>` is useful; if it needs “just one sender”, use qualifier/primary/fallback according to the contract.

If a collection should hold only a subset, a qualifier can **filter the entire collection**. For example, two beans annotated with `@Qualifier("transactional")` can go into `@Qualifier("transactional") List<MessageSender>`; a qualifier does not have to point to a single unique bean.

### Map Is Useful for Strategy Lookup, but Keys Must Be Controlled

Example of a domain registry:

~~~java
private final Map<String, MessageSender> senders;

public StrategySelector(Map<String, MessageSender> senders) {
    this.senders = Map.copyOf(senders);
}

public MessageSender forChannel(String beanName) {
    MessageSender sender = senders.get(beanName);
    if (sender == null) {
        throw new IllegalArgumentException("Unknown channel: " + beanName);
    }
    return sender;
}
~~~

**These are method snippets within a class requiring appropriate imports and interface declarations**, not a second runnable project. This enables *runtime* selection based on an application-validated input. However, avoid letting bean names (Spring wiring details) accidentally become a public API contract; map domain channels to bean strategies or use enums/typed keys when appropriate.

## 9. Parameter Name Matching: Why Can Selection Sometimes Succeed Without @Qualifier?

In some cases, Spring can use the **field/parameter name** to select a bean with a matching name or alias after evaluating other selection rules. For example, `MessageSender emailSender` can match a bean named `emailSender`, but Java parameter names are only reliably preserved if compiled with `-parameters` (especially in Spring Framework 6.1+).

Name matching is a conditional convenience, not a guarantee that Spring always injects by name before type or qualifier. For a business contract needing a stable implementation, an explicit qualifier is easier to verify. The dedicated lesson on `-parameters` explains bytecode metadata, Maven, and how to test with and without that flag.

## 10. Generic Types and Metadata Also Affect Candidates

When `Store<String>` and `Store<Long>` both exist, an injection point of `Store<String>` can use generic metadata to filter candidates before considering `@Primary`, qualifiers, or names. This is differentiation by type contract, distinct from domain labeling. If two beans both have `Store<String>`, ambiguity can still arise; if a method declares raw `Store`, Spring may lack the information to distinguish them. The dedicated section on generic types covers erasure limits and collection injection.

## 11. Other Approaches and Their Limitations

| Mechanism | When appropriate | Limitations |
| --- | --- | --- |
| `@Primary` | There is one default implementation for most consumers | Does not resolve two equal primaries |
| `@Qualifier` | Each consumer needs an implementation for a clear role | Qualifier requires type-compatible candidates; multiple may still remain |
| `@Fallback` | One implementation is a fallback in Spring 6.2+ | Does not replace mandatory policies or remove the bean |
| `List<T>` / `Map<String,T>` | Need all strategies or dynamic lookup | Consumer must handle ordering/selection at point of use |
| Parameter/field name | Meaningful names and reliable metadata | Fragile under refactoring; needs `-parameters` for constructors |
| `@Resource(name=...)` | Need name-oriented field/setter resolution | Semantics differ from type-driven constructor qualifiers |
| Generic type | Interface specialization expresses the contract intent | Requires sufficiently specific generics metadata |
| `ObjectProvider<T>` | Intentional lazy/optional/stream access | Single-valued `getObject()` can still encounter ambiguity |
| `@Bean(defaultCandidate=false)` | Bean should only appear when injection has a qualifier | 6.2 feature; not `@Fallback` |
| `@Bean(autowireCandidate=false)` | Exclude from type-based injection | Does not unregister the bean or forbid explicit lookup |
| `@Profile` / registration condition | Each environment registers only the appropriate implementation | Must test profile/condition setups in real environments |

### Profiles and Conditions Can Solve the Problem at the Source

If the application **never needs both implementations in the same environment**, another approach is to ensure only **one definition is registered** via profile/condition, rather than always registering both and picking via primary.

Conceptual example:

~~~java
@Bean
@Profile("dev")
MessageSender devSender() { return new ConsoleSender(); }

@Bean
@Profile("prod")
MessageSender prodSender() { return new RemoteSender(); }
~~~

**Illustrative snippet**, missing interfaces/implementations and configuration. Make sure the right profile is active, otherwise candidates may be missing; if multiple profiles are active, multiple candidates may reappear. This concerns **which beans are registered**, rather than choosing among already-registered candidates.

Do not use `@Conditional` or `@Profile` to hide business implementations that genuinely need to coexist simultaneously.

## 12. Diagnosing NoUniqueBeanDefinitionException in the Right Place

A stack trace may contain exception layers like:

~~~text
UnsatisfiedDependencyException
  caused by: NoUniqueBeanDefinitionException:
  expected single matching bean but found 2:
  emailSender, smsSender
~~~

**This is an illustrative error structure, not a verbatim stack trace**. Wrapper exception classes and wording depend on the bean creation path and Spring version. Read down to the specific bean name, type, candidate count, and injection point.

A reliable workflow:

1. **Locate the injection point:** constructor parameter, field, `@Bean` factory method, or `context.getBean(Type.class)`?
2. **Verify the type:** `MessageSender` or a subtype; do generic arguments, proxies, or factory declared return types affect it?
3. **List candidate beans:** use `context.getBeanNamesForType(MessageSender.class)` once the context is running; inspect definitions for the relevant names.
4. **Check qualifiers and primary:** are the annotations actually on the injection point / bean definition? Are there two primaries of the same type?
5. **Check fallback, candidate flags, and profiles:** is a bean excluded from autowiring or restricted to qualified injection only?
6. **Check parameter/field names:** does a name accidentally match a bean name? Was `-parameters` used during compilation if relying on it?
7. **Read the root cause:** if a missing bean occurred because registration did not run or a dependency failed, do not conflate it with ambiguity.
8. **Pick the solution matching business intent:** one default → primary; consumer-specific → qualifier; all strategies → List/Map; environment-specific → profile; fallback → @Fallback; truly needs only one definition → fix registration.
9. **Write a smoke test:** test context startup and assert the identity/type/behavior of the injected bean, not just “no exception thrown.”

### API to Inspect Present Beans

~~~java
String[] names = context.getBeanNamesForType(MessageSender.class);
for (String name : names) {
    System.out.println(name);
}
~~~

**Snippet**: must be in a scope with `ApplicationContext context` and the `MessageSender` type. Array order may follow registration order, so sort names before asserting if a deterministic list is required. A bean's presence in the registry **does not automatically prove it is an eligible candidate for every injection point**; qualifier flags and scopes still apply.

## 13. Common Design Mistakes and How to Fix Them

| Symptom | Common misconception | Fix |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` | “Two beans on the same interface are illegal” | Two beans are allowed to coexist; clarify whether the consumer contract wants one or many |
| Marking both beans `@Primary` | “More primaries make selection surer” | Pick one clear default or use qualifiers |
| Adding `@Order(1)` to a bean | Thinking Spring picks the lowest-order bean for single injection | Use primary/qualifier; order is for collections |
| Removing a qualifier during refactoring | Spring starts picking by parameter name or fails with ambiguity | Restore intentional selection requirements |
| `@Qualifier` has a bean name of the wrong type | Expecting a String bean name regardless of type | Fix declared types / bean definitions |
| `@Fallback` still leaves multiple normal beans | Thinking fallback resolves all ambiguity | Use qualifier/primary or narrow the candidate set |
| `@Autowired(required=false)` to “fix” two candidates | Optional does not mean picking a bean arbitrarily | Clarify candidate selection instead of hiding the error |
| Making `@Bean` method return type too generic | Metadata is insufficient to match subtypes/generics | Declare a sufficiently specific return type |
| Fixing only in unit tests with a fake bean | Production config remains ambiguous | Add an integration test using the real configuration |
| Works with one profile active, fails with two | Both implementations get registered together | Verify profile combinations and candidate policy |
| Calling `getBean(Class)` inside a business service | Runtime lookup is brittle and hides dependencies | Use constructor injection into the service |
| Relying on accidental constructor parameter names | Renaming during refactoring breaks binding | Use explicit qualifiers when stability is needed |
| Using `autowireCandidate=false` indiscriminately | Candidates disappear from type-driven injection | Exclude only beans that should not be autowired |
| Using Map then calling `values().iterator().next()` | Relying on order instead of a business policy | Select by domain key or an explicit strategy |
| Race condition on a mutable singleton strategy | Thinking the selected bean is automatically thread-safe | Protect state and design scope/concurrency properly |
| `javac` cannot find Spring APIs | Missing Spring JARs/classpath | Check POM and `-cp` before debugging DI |

**Principle:** an ambiguity error usually carries useful information about **an unclear contract**. Do not fix it by slapping `@Primary` on an arbitrary bean just to make the app start if the business domain has no reason to treat it as the default.

## 14. Testing Candidate Selection Strategies

### Unit Testing Without Spring

A service whose constructor takes an interface can still be tested with a fake:

~~~java
Sender fake = () -> "TEST";
QualifiedClient client = new QualifiedClient(fake);
System.out.println(client.selected()); // TEST
~~~

**Snippet** within the scope accessing the demo's nested types. It tests pure Java logic and that the constructor accepts a collaborator; it **does not** test Spring autowiring policies.

### Wiring Integration Tests

In a context with two Senders, you should verify:

- No qualifier/primary/fallback when requesting a single `Sender.class` → expected ambiguity.
- `@Qualifier("emailSender")` at an injection point → receives the email bean.
- One `@Primary` → bare type resolution selects the default.
- `smsSender` qualifier still selects SMS even when email is primary.
- One normal + one `@Fallback` → normal is preferred.
- Only one fallback candidate → fallback is still selected.
- Two primaries → ambiguity (unless another distinguishing condition applies).
- `List<Sender>` is sorted by `@Order`; `Map<String,Sender>` contains the exact names.
- A bean not registered in a profile → missing candidate, not a multiple-candidate error.

**Do not pin tests to the full exception message text**, because wrappers and wording can change. With a test framework, assert exception type/cause, bean identity, qualifier semantics, and output/behavior.

### Version Note

This lesson uses **Spring Framework 6.2.19** because `@Fallback` and `@Bean(defaultCandidate=...)` are capabilities introduced with 6.2. If a project uses Spring Framework 6.1 or older, **do not copy `@Fallback` code without verifying the version**. On older versions, `@Primary`/`@Qualifier` and existing candidate configuration options are available; upgrading the framework must follow the project's compatibility policy.

## 15. Exercises with Answers

**Exercise 1.** A context has `emailSender` and `smsSender` both implementing `Sender`, with no primary/qualifier. Does `context.getBean(Sender.class)` pick the first registered bean?

**Answer:** Not under single-valued autowiring rules. When multiple indistinguishable candidates exist, `getBean(Sender.class)` typically throws `NoUniqueBeanDefinitionException`.

**Exercise 2.** There is a `@Primary` email bean and a regular SMS bean. What does a factory method taking an unqualified `Sender sender` receive?

**Answer:** EMAIL, because there is exactly one valid primary.

**Exercise 3.** A consumer uses `@Qualifier("smsSender") Sender sender` while EMAIL is primary. Does it receive EMAIL?

**Answer:** Not in this case. The qualifier narrows candidates to the requested SMS; Spring injects SMS.

**Exercise 4.** There is one normal EMAIL bean and one `@Fallback` SMS bean. Which bean does a bare `Sender` injection point receive?

**Answer:** EMAIL, the sole non-fallback candidate.

**Exercise 5.** The context contains only an SMS bean marked `@Fallback`. Is a required `Sender` dependency missing?

**Answer:** No, because SMS is still an eligible candidate; fallback means lower precedence, not excluding the bean.

**Exercise 6.** Marking SMS with `@Order(1)` and EMAIL with `@Order(2)` causes `getBean(Sender.class)` to automatically choose SMS?

**Answer:** No. `@Order` sorts collection injections; it does not replace `@Primary` for standard single-valued lookup.

**Exercise 7.** What does `List<Sender>` receive when there are two differently named beans of the same type?

**Answer:** It typically receives both compatible beans, ordered according to the applicable ordering policy. No single bean needs to be chosen.

**Exercise 8.** Both beans have `@Primary` with no other selection rule. Is a unique default obtained?

**Answer:** No. Two primaries make single-valued selection ambiguous.

**Exercise 9.** Can `@Qualifier` select a bean whose type is incompatible with the injection point?

**Answer:** No. A qualifier narrows **within type-compatible beans**; it does not coerce a String name into an incompatible type.

**Exercise 10.** Why can merely renaming a parameter affect wiring when no qualifier is present?

**Answer:** Spring can use the injection point name as a hint when applicable; in Spring 6.1+, preserving parameter names requires compiling with `-parameters`. Explicit qualifiers are better when selection logic must remain resilient to refactoring.

**Exercise 11.** If only the email sender is needed in every environment, must you create an extra SMS bean and mark email `@Primary`?

**Answer:** No. If SMS does not need to exist, do not register it. Profiles/conditions or a clean configuration can ensure a single bean candidate from the start.

**Exercise 12.** When should you inject `Map<String, Sender>` instead of `Sender`?

**Answer:** When business logic genuinely needs multiple strategies and selects one dynamically by a validated key/condition, not to dodge clarifying a single default.

## 16. Pre-Production Checklist

- [ ] Determine whether the dependency needs **one** or **multiple** beans.
- [ ] Verify bean names, interfaces/types, generics, and qualifier metadata.
- [ ] Interpret `NoUniqueBeanDefinitionException` correctly instead of mistaking it for a missing bean.
- [ ] If there is a legitimate default, mark **exactly one `@Primary`**.
- [ ] If a consumer has specific intent, use `@Qualifier` at the injection point.
- [ ] If there is a fallback bean, understand Spring 6.2 `@Fallback` semantics.
- [ ] Do not treat `@Fallback` as removing or excluding a bean.
- [ ] Do not use `@Order` to replace primary in single-valued injection.
- [ ] For `List/Map`, confirm the elements and ordering match the contract.
- [ ] Avoid selection that depends on accidental parameter names or registration order.
- [ ] Use `@Bean(defaultCandidate=false)`/`autowireCandidate=false` only when you understand the consequences.
- [ ] With `@Bean`, declare return types specific enough for injection points.
- [ ] Separate pure logic unit tests from Spring context wiring tests.
- [ ] Test multiple profile combinations and primary/qualifier/fallback interactions.
- [ ] Run on Java 17+ with Maven and `javac`/`java`, verifying the **9 stdout lines**.
- [ ] Do not hardcode selecting the “first strategy in Map” without a business rule.
- [ ] When changing Spring versions, verify support for `@Fallback` and `@Bean` flags.

**Remember:** Multiple beans of the same type are natural when implementing strategy/interface-based design. Spring simply needs one **clear and unique** selection mechanism when an injection point requests a single object. `@Primary` says **“this is the default”**; `@Qualifier` says **“this specific one is needed here”**; `@Fallback` says **“this is a low-precedence option”**; `List/Map` says **“multiple implementations are needed here”**. Choosing the mechanism that reflects the actual business intent keeps the dependency graph understandable, testable, and free of wiring surprises as the project grows.

### Official Spring Documentation

- [Spring 6.2 — Autowiring Collaborators](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-autowire.html)
- [Spring 6.2 — Fine-tuning @Primary and @Fallback](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-primary.html)
- [Spring 6.2 — Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring 6.2 — Using @Autowired](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html)
- [Spring 6.2 — Using Generics as Autowiring Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/generics-as-qualifiers.html)
