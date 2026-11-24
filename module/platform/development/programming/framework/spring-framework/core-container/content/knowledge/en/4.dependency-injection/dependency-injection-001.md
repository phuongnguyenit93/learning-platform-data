# Required Dependencies, Optional Dependencies, and Object Immutability in Spring

## 1. Classifying Dependencies by Object Contract

A Java class may need one or more collaborator objects (*dependencies*) to carry out its task. In Spring Core Container, **Dependency Injection (DI)** is the process by which the container supplies those defined dependencies to a bean, rather than letting the bean look up or create all of its collaborators itself.

The important question when designing a service is not “which annotation should I place?”, but **is this dependency required for the object to be valid?**

| Dependency Type | Meaning | When the Dependency Is Missing | Preferred Design Approach |
| --- | --- | --- | --- |
| **Required** | Cannot fulfill the object's primary contract if missing | Should fail fast with a clear cause | **Constructor injection**, non-`null` parameters, `final` fields |
| **Optional** | Still has a well-defined valid behavior when missing | Use a default, skip a feature, or use a fallback mechanism | `Optional<T>`, `ObjectProvider<T>`, default strategy; setter if reconfiguration is needed |
| **Configuration value** | Parameters such as timeout, base URL, business limits | Requires clear validation and default policies | Constructor/configuration factory method, immutable value object |

For example, a `BillingService` **must have** a `PaymentGateway` to record payments, but **may omit** an `AuditSink` in a demo/offline mode. When `PaymentGateway` is missing, creating the service fails; when `AuditSink` is missing, the service still processes payments without emitting audit records.

**Optional does not mean “security-unimportant”.** If auditing is legally or compliance-mandated, it must be designed as **required**; never silently skip an essential capability merely because the `Optional` API allows it.

Learning objective: define the contract accurately, distinguish **the container lacking a bean** from **a `null` value passed directly by code**, master Spring's optional choices, and understand the true scope of `final`/immutability.

## 2. Constructor Injection and Configuration State Immutability

For required dependencies, an object should refuse to be created if a needed value does not exist:

~~~java
// Plain Java snippet: PaymentGateway/AuditSink types are defined in the full demo.
public final class BillingService {
    private final PaymentGateway gateway;
    private final Optional<AuditSink> audit;

    public BillingService(
            PaymentGateway gateway, Optional<AuditSink> audit) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
        this.audit = Objects.requireNonNull(audit, "audit");
    }
}
~~~

This is an **illustrative sample**, not standalone compilable source: it needs imports for `java.util.Objects`, `java.util.Optional`, and declarations for the interfaces. The complete program is in section 5.

**Constructor injection** provides three direct benefits:

1. **Missing required dependencies are detected early.** A Java caller attempting to pass `null` receives an exception at the constructor rather than a `NullPointerException` halfway through business processing.
2. **The object leaves the constructor in a valid state.** There is no temporary existence of a `BillingService` lacking a gateway while hoping a setter gets called before use.
3. **Dependency references can be `final`.** Once the constructor completes, the class cannot reassign the `gateway` or `audit` fields in normal Java code.

Spring also recommends constructor injection for required components because it enables immutable design and avoids returning partially initialized objects. For a Spring-managed component with only **one constructor**, Spring can typically select that constructor without writing `@Autowired`; with a `@Bean` factory method, you can inject via **factory method parameters**. Rules for multiple constructors are more complex—do not assume Spring will guess every constructor overload.

### `final` Does Not Mean Deep Immutability

~~~java
private final List<String> events = new ArrayList<>();
~~~

The `events` reference cannot be reassigned to another list after initialization, yet **the list's contents can still change**. Likewise, `private final PaymentGateway gateway` only keeps the *reference* fixed; if the `PaymentGateway` implementation holds mutable state, the entire object graph does not automatically become immutable or thread-safe.

**Object immutability has multiple levels:**
- **Stable dependency wiring:** references to dependencies do not change after construction (`final`).
- **Immutable state:** values held by the object do not change after construction; when accepting mutable inputs, create defensive copies.
- **Deep immutability:** all child objects reachable from the object must also uphold an appropriate contract.
- **Thread safety:** requires considering concurrency and actual state; a Spring singleton **does not automatically guarantee thread safety**.

A service can have final dependencies and still interact with a database, write logs, or call a mutable client. **Configuration immutability and method side effects are two distinct concepts.**

## 3. How Spring Interprets “Required” at an Injection Point

In Spring, a regular dependency is treated as **required** when resolving a constructor or factory method parameter by type. If the container has no matching bean and no special rule applies to the injection point, bean creation fails.

~~~java
// Configuration snippet; full types/imports are in the section 5 demo.
@Bean
BillingService billingService(
        PaymentGateway gateway, Optional<AuditSink> audit) {
    return new BillingService(gateway, audit);
}
~~~

`PaymentGateway gateway` is **required**. Spring must find a compatible bean to invoke the factory method. `Optional<AuditSink>` is an **optional** injection point under Spring's resolution rules: if no suitable `AuditSink` bean exists, it can pass `Optional.empty()`; when there is exactly one matching candidate, it passes `Optional.of(bean)`.

If **two beans share the same type** without a qualifier, primary designation, or explicit disambiguation mechanism, Spring may report ambiguity. `Optional<T>` does not mean “arbitrarily pick the first bean” when multiple candidates exist.

### When Spring Resolves a Missing Required Bean

~~~text
@Bean billingService(PaymentGateway gateway, Optional<AuditSink> audit)
                         |
                         v
           Look up PaymentGateway in context
                     /                 \
             1 match found          None found
                  |                     |
                  v                     v
         Inject reference       Bean creation fails
                  |
                  v
         Resolve optional AuditSink
                  |
            Present / absent
                  |
                  v
       Create valid BillingService
~~~

When a non-lazy singleton is pre-instantiated during `ApplicationContext.refresh()`, a missing required bean can cause **the entire context startup to fail** before the application ever calls `getBean`. With lazy or prototype beans, the error may surface later at bean creation time. Do not confuse a bean creation error with Maven failing to download JARs.

**Difference between two validation layers:**

- **Container validation:** Is there a bean whose type/qualifier satisfies the injection point?
- **Object invariant validation:** Are the arguments valid regarding nullness, domain rules, value ranges, or business relationships?

Spring may have resolved the right bean by type while that bean still carries an invalid business configuration. Use validation inside the constructor or factory to enforce invariants, rather than expecting DI to verify every domain rule.

## 4. Ways to Express Optional Dependencies

Spring supports several approaches, whose semantics and lifecycles are not identical.

| Expression | When No Bean Exists | When to Consider |
| --- | --- | --- |
| **`Optional<T>`** at injection point | Typically receives `Optional.empty()` | Know right at construction whether the feature is available; genuinely optional dependency |
| **`ObjectProvider<T>`** | Receives a provider; can check `getIfAvailable()` later | Want **on-demand lookup**, deferred bean retrieval, or scope coordination |
| **`@Nullable T`** on parameter | Allows receiving `null` per injection rules | Integrating APIs that naturally use null; must code null-safely and pick the right annotation |
| **`@Autowired(required = false)`** on setter/field | Setter is not invoked or field is not set if candidate is missing | Legacy mutable/configuration optionality; requires a valid default |
| **No-op/default implementation** | Always injects an implementation fulfilling the contract | When the feature always needs a strategy, with a default implementation performing no side effects |

**Recommendation for new code:** `Optional<T>` clearly expresses a dependency that may be absent right at object creation; `ObjectProvider<T>` is useful when a dependency needs to be fetched dynamically at method invocation time. Do not mark a dependency optional if the service cannot operate without it.

### `Optional<T>` Directly in the Constructor

~~~java
public BillingService(
        PaymentGateway gateway, Optional<AuditSink> audit) {
    this.gateway = Objects.requireNonNull(gateway);
    this.audit = Objects.requireNonNull(audit);
}
~~~

`audit` **must not be null**; absence of auditing is represented by `Optional.empty()`. This avoids mixing two absence mechanisms: both `null` and empty. In plain Java callers, you must construct `Optional.empty()` or `Optional.of(sink)` yourself; Spring only resolves `Optional` when creating/injecting the bean.

### `ObjectProvider<T>`: Fetching on Demand

~~~java
// Snippet inside a Spring bean, assuming the provider has already been injected.
private final ObjectProvider<AuditSink> sinkProvider;

public void maybeRecord(String message) {
    AuditSink sink = sinkProvider.getIfAvailable();
    if (sink != null) {
        sink.record(message);
    }
}
~~~

The snippet above requires importing `org.springframework.beans.factory.ObjectProvider` and the corresponding types. **A provider does not turn a missing bean into an implementation**; it only lets you query and handle its absence. Regular `getObject()` **requires a bean to exist**, unlike `getIfAvailable()`; when multiple candidates exist, ambiguity/qualifiers must be handled.

A provider can also be useful when a singleton needs to create or retrieve a prototype bean per call. Injecting a prototype directly into a singleton's constructor does **not** refresh the dependency on each method call.

### `@Autowired(required=false)` and `@Nullable`

~~~java
// Illustrative snippet (not a standalone Java file):
private AuditSink audit = message -> { }; // Default no-op.

@Autowired(required = false)
public void setAudit(AuditSink sink) {
    this.audit = sink;
}
~~~

If Spring finds no matching dependency, a non-required setter may **not be called**, so the field retains its initial no-op value. This fits when an object **permits swapping strategies after construction**; however, state is now mutable, requiring attention to concurrency and when the object is used.

`@Nullable` is supported by Spring at injection points (such as `org.jspecify.annotations.Nullable` in modern Spring) to represent an absent dependency as `null`. This API requires the right dependency/import and must be handled null-safely. **Do not equate `@Nullable` with `@Autowired(required=false)` in every position**; they have different semantics, especially on multi-parameter methods.

## 5. Spring Framework 7 + Java 17 Project: Three Required/Optional Scenarios

The example uses **one business service** and three container configurations:

1. `PaymentGateway` present, **no `AuditSink`** → service is created, `Optional.empty()`.
2. `PaymentGateway` present and **one `AuditSink` present** → service is created, audit receives the message.
3. **No `PaymentGateway`** → container refuses to create the required `BillingService`, rather than silently supplying null.

Three independent context initializations, without Spring Boot or a web server.

### 5.1. Maven Structure

~~~text
required-optional-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── RequiredOptionalDemo.java
~~~

Requirements: **JDK 17+**, Maven **3.9+**, downloading libraries from the repository on the first run.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>required-optional-demo</artifactId>
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
                    <mainClass>demo.RequiredOptionalDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides the container APIs and pulls in the foundational Spring artifacts via Maven transitive dependencies; no Spring Boot starter is needed. Spring Framework 7.0 has a Java 17 baseline; use an appropriate BOM/version management setup when adding other Spring modules in a real application.

### 5.2. Code in `src/main/java/demo/RequiredOptionalDemo.java`

~~~java
package demo;

import java.util.Objects;
import java.util.Optional;

import org.springframework.beans.BeansException;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class RequiredOptionalDemo {

    private RequiredOptionalDemo() {
    }

    interface PaymentGateway {
        String charge(String invoice, long amount);
    }

    interface AuditSink {
        void record(String message);
    }

    static final class FixedGateway implements PaymentGateway {
        @Override
        public String charge(String invoice, long amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("amount must be >= 0");
            }
            return "OK:" + invoice + ":" + amount;
        }
    }

    static final class ConsoleAuditSink implements AuditSink {
        @Override
        public void record(String message) {
            System.out.println("AUDIT:" + message);
        }
    }

    // Business service: does not depend on Spring APIs.
    public static final class BillingService {
        private final PaymentGateway gateway;
        private final Optional<AuditSink> audit;

        public BillingService(
                PaymentGateway gateway, Optional<AuditSink> audit) {
            this.gateway = Objects.requireNonNull(gateway, "gateway");
            this.audit = Objects.requireNonNull(audit, "audit");
        }

        public boolean hasAudit() {
            return audit.isPresent();
        }

        public String bill(String invoice, long amount) {
            String receipt = gateway.charge(invoice, amount);
            audit.ifPresent(sink -> sink.record(receipt));
            return receipt;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class BaseConfig {
        @Bean
        public PaymentGateway paymentGateway() {
            return new FixedGateway();
        }

        @Bean
        public BillingService billingService(
                PaymentGateway gateway, Optional<AuditSink> audit) {
            return new BillingService(gateway, audit);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AuditConfig {
        @Bean
        public AuditSink auditSink() {
            return new ConsoleAuditSink();
        }
    }

    // Intentionally do NOT declare PaymentGateway.
    @Configuration(proxyBeanMethods = false)
    public static class MissingGatewayConfig {
        @Bean
        public BillingService billingService(
                PaymentGateway gateway, Optional<AuditSink> audit) {
            return new BillingService(gateway, audit);
        }
    }

    public static void main(String[] args) {
        // Required PaymentGateway present, optional AuditSink absent.
        try (var context =
                new AnnotationConfigApplicationContext(BaseConfig.class)) {
            BillingService service = context.getBean(BillingService.class);
            System.out.println("without.audit=" + service.hasAudit());
            System.out.println("without.result="
                    + service.bill("INV-1", 120));
            System.out.println("without.singleton="
                    + (service == context.getBean(BillingService.class)));
        }

        // Register an additional AuditSink bean.
        try (var context = new AnnotationConfigApplicationContext(
                BaseConfig.class, AuditConfig.class)) {
            BillingService service = context.getBean(BillingService.class);
            System.out.println("with.audit=" + service.hasAudit());
            // The call below invokes AuditSink.record(), printing the AUDIT line first.
            String receipt = service.bill("INV-2", 200);
            System.out.println("with.result=" + receipt);
        }

        // Missing required bean: failure during context startup.
        try (var context = new AnnotationConfigApplicationContext(
                MissingGatewayConfig.class)) {
            System.out.println("unreachable");
        } catch (BeansException expected) {
            System.out.println("missingRequired.rejected=true");
        }
    }
}
~~~

**Why this compiles and runs standalone:** All classes/interfaces of the demo live in the same source file, needing only the `spring-context` dependency. `BaseConfig` declares the gateway and service; `AuditConfig` independently declares only the audit sink. Spring resolves the required `PaymentGateway` parameter and the optional `Optional<AuditSink>` parameter for the factory method.

`BillingService` keeps two `final` fields, has no setters, and rejects `null` arguments via `Objects.requireNonNull`. This is a **reference-immutable design**; do not infer that every `PaymentGateway`/`AuditSink` implementation is immutable or thread-safe.

`MissingGatewayConfig` only has `BillingService`, which requires a gateway. Under default settings (non-lazy singleton), the context cannot finish refreshing; the exception belongs to the `BeansException` hierarchy. The program prints only a single boolean line confirming failure, **without relying on exact class names, messages, or stack traces** that vary across versions and loggers.

**Note on `@Bean` factory-method injection:** With `proxyBeanMethods=false`, factory methods in this example **do not call each other directly**. Spring supplies dependencies to `billingService(...)` via parameters; do not manually call `paymentGateway()` inside it and assume singleton semantics.

## 6. Running Maven and Comparing stdout

From the `required-optional-demo` directory containing `pom.xml`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

The Java/Maven check commands print environment-specific details. The final command uses the compiler via Maven to target Java 17 and run `demo.RequiredOptionalDemo`.

**7 deterministic stdout lines from the program** (excluding diagnostic logs/exceptions emitted by Maven or Spring backends outside `System.out.println`):

~~~text
without.audit=false
without.result=OK:INV-1:120
without.singleton=true
with.audit=true
AUDIT:OK:INV-2:200
with.result=OK:INV-2:200
missingRequired.rejected=true
~~~

| Output Line | Evidence | Inference Limit |
| --- | --- | --- |
| `without.audit=false` | `Optional.empty()` is used when no AuditSink bean exists | Does not mean the `AuditSink` API failed |
| `without.result=...` | Required gateway exists, so business logic still runs | Does not prove every optional configuration is safe |
| `without.singleton=true` | BillingService bean defaults to singleton within a context | Not a single instance across the entire JVM |
| `with.audit=true` | Exactly one matching AuditSink exists in the second context | Does not mean audit was required in the first context |
| `AUDIT:...` | Optional dependency is invoked when present | A side effect can occur while the bill result still returns properly |
| `with.result=...` | Business receipt is unchanged when adding audit | Does not by itself guarantee durable audit delivery |
| `missingRequired.rejected=true` | Creating a singleton missing a required dependency is rejected | Does not mean missing any optional dependency will also fail |

When a context fails to start, Spring may log warnings or exceptions before the program catches the exception. Expected output here refers to **the lines from the source itself**, not the entire terminal output.

If an application uses a real `PaymentGateway` with I/O, expected output should not be hardcoded to network calls; the demo uses `FixedGateway` for deterministic results without external side effects.

## 7. Plain Java 17: Required/Optional Without Spring

**Required vs. optional** is an object contract concern, not solely a Spring feature. To verify this yourself, create a separate **`RequiredOptionalPureJava.java`** file:

~~~java
import java.util.Objects;
import java.util.Optional;

public class RequiredOptionalPureJava {
    interface Store {
        String id();
    }

    static final class Reader {
        private final Store store;
        private final Optional<String> label;

        Reader(Store store, Optional<String> label) {
            this.store = Objects.requireNonNull(store, "store");
            this.label = Objects.requireNonNull(label, "label");
        }

        String describe() {
            return store.id() + ":" + label.orElse("default");
        }
    }

    public static void main(String[] args) {
        Store store = () -> "store";
        System.out.println("noLabel="
                + new Reader(store, Optional.empty()).describe());
        System.out.println("withLabel="
                + new Reader(store, Optional.of("vip")).describe());

        try {
            new Reader(null, Optional.empty());
        } catch (NullPointerException expected) {
            System.out.println("requiredRejected=true");
        }
    }
}
~~~

Run from the directory containing the file, **without Maven or Spring JARs**:

~~~bash
javac RequiredOptionalPureJava.java
java RequiredOptionalPureJava
~~~

Expected stdout:

~~~text
noLabel=store:default
withLabel=store:vip
requiredRejected=true
~~~

Both examples apply the same principle: **required is non-null**, **optional explicitly represents absence**, and **references are kept final**. Spring only orchestrates resolution and dependency wiring; plain Java must still protect invariants when callers explicitly use `new`.

A design note: `Optional` generally fits return values and certain dependency injection points; avoid forcing `Optional` into every field or every DTO as a substitute for defining a clear contract and serialization format. In the example, the `Optional<AuditSink>` field is intentional to highlight an optional dependency.

## 8. Setter Injection When Non-Essential Configuration Has a Default Value

In the `BillingService` example, `PaymentGateway` is a required dependency while `AuditSink` is expressed as `Optional<AuditSink>` right in the constructor. For a **setting with a valid default** that permits adjustment, a setter is another option:

~~~java
// Plain Java sample to illustrate a setter, without main().
public final class ReportService {
    private boolean verbose; // Defaults to false; the object remains valid.

    public void setVerbose(boolean verbose) {
        this.verbose = verbose;
    }

    public void report() {
        if (verbose) {
            System.out.println("report:verbose");
        }
    }
}
~~~

Omitting `setVerbose(...)` still leaves `ReportService` with deterministic behavior. With an `@Autowired(required = false)` setter accepting an **optional bean**, Spring may skip calling the setter if no suitable dependency is found; therefore, the default state must be safe. Never turn a genuinely required dependency like `PaymentGateway` into an optional setter just to get the context to start.

**Limitation:** setters keep mutable state, so modifying configuration while a singleton serves multiple threads requires clear synchronization and consistency policies. Multiple-constructor selection rules and diagnosing constructors with too many dependencies are two separate topics; they do not alter the required/optional definitions in this lesson.

## 9. Practical Immutability: Data, Defensive Copies, and Concurrency

A class with `final` fields can still be mutated indirectly if a field points to a collection managed by the caller. For example:

~~~java
// Java 17 snippet: retain an immutable copy of the tags.
public final class BillingPolicy {
    private final List<String> allowedTags;

    public BillingPolicy(List<String> tags) {
        this.allowedTags = List.copyOf(
                Objects.requireNonNull(tags, "tags"));
    }

    public List<String> allowedTags() {
        return allowedTags;
    }
}
~~~

`List.copyOf` creates or reuses an **unmodifiable list** under the right contract and rejects `null` elements; callers cannot modify the list elements through the returned reference. However, if the elements themselves are mutable objects, **the child objects themselves** can still be mutated. The snippet above requires importing `java.util.List`, `java.util.Objects` and placing it in a file with a matching public class name.

Principles to raise the level of immutability:

1. Declare `private final` fields for state that should stay fixed; let the constructor enforce validation.
2. Avoid exposing setters that alter essential state after construction.
3. Use immutable value objects (e.g., Java 17 `record` where appropriate), defensive copies for collections/arrays, and avoid leaking mutable references.
4. Clearly define resource ownership and side effects. A `final` `PaymentGateway` can still execute external transactions.
5. When Spring creates a singleton, **ensure bean code is thread-safe as needed**: a Spring scope does not automatically protect mutable caches or counters.
6. Avoid circular constructor dependencies. If A needs B to finish construction and B simultaneously needs A, the container may fail when building the graph; revisit the design rather than converting every dependency to setters to mask the cycle.

**Do not make every dependency Optional to dodge startup errors.** If an application strictly requires payments, missing `PaymentGateway` should be an explicit failure — “succeeding” at startup with a null or no-op payment gateway can be far more dangerous than failing fast.

## 10. Common Errors and Self-Diagnosis

| Symptom / Observation | Possible Cause | Resolution |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` for PaymentGateway | No matching bean in the context | Register a proper `@Bean`/component scan, check active configuration |
| `UnsatisfiedDependencyException` during refresh | Bean needs an unresolved required dependency | Read the `Caused by` exception; verify type, bean name, qualifier |
| `NoUniqueBeanDefinitionException` | Multiple candidates share the type with no selection rule | Use `@Qualifier`, `@Primary`, or split interfaces |
| `Optional<AuditSink>` is always empty | AuditSink bean is not registered in the current context | Check config classes/scans; do not blindly force `get()` |
| Calling `audit.get()` when Optional.empty | `NoSuchElementException` in business code | Use `ifPresent`, `orElse`, `orElseGet` according to policy |
| `@Autowired(required=false)` setter never runs | No valid candidate for the injection point | Ensure the object's default state is valid before the setter |
| `ObjectProvider.getObject()` fails | This API requires a bean and provides no automatic fallback | Choose `getIfAvailable()` or handle the exception |
| `Objects.requireNonNull` still throws NPE | Code manually calls `new Service(null,...)` or a factory passes null | Fix the caller/factory; container injection does not replace validation |
| Has `final` fields yet state still changes | Referenced dependency or collection is still mutable | Defensive copies, immutable implementations, proper state synchronization |
| Singleton suffers race conditions under concurrent requests | Shared mutable state without thread safety | Design stateless/immutable beans or apply proper concurrency controls |
| Context starts fine but business logic is wrong | DI only handles wiring, not domain rule correctness | Unit/integration tests, input validation, and contract checks |
| Java code importing Spring fails to compile | Missing `spring-context` on the compile classpath | Use the right Maven dependency version and reload the project |

### Distinguishing Infrastructure Errors from Contract Errors

- If Maven cannot find an artifact, that is a **dependency resolution/repository** issue.
- If Java code cannot import `org.springframework.context.annotation`, that is a **compile classpath** issue.
- If the context cannot find a bean, that is a **DI configuration** issue.
- If a constructor throws `IllegalArgumentException`/`NullPointerException`, that is an **invariant/argument validation** issue or a factory passing invalid values.
- If `bill()` computes `amount` incorrectly, that is a **business logic** issue, which Spring will not detect automatically.

Read the **root cause in the exception chain**, rather than copying an exact Spring message from a single patch version; nested types and messages can vary depending on how the context is constructed.

## 11. Verifiable Experiments

Make each change independently on a copy, then restore the original code to compare against stdout in section 6:

1. **Without optional:** run BaseConfig, explain why `without.audit=false` yet `without.result` is still produced.
2. **With optional:** add AuditConfig, pinpoint when `ConsoleAuditSink.record()` runs and why the `AUDIT` line appears before `with.result`.
3. **Without required:** run MissingGatewayConfig by itself and identify the startup error type. Why must a missing gateway fail instead of becoming `Optional.empty()`?
4. **Induce ambiguity:** declare two different `PaymentGateway` beans, then add `@Qualifier`/`@Primary` to resolve it. Do not use Optional to hide the error.
5. **Constructor guard:** manually instantiate `new BillingService(null, Optional.empty())` outside Spring, confirming the exception comes from Java constructor validation, not the container.
6. **Change optional to required:** replace the `Optional<AuditSink>` parameter with `AuditSink`; predict why BaseConfig will no longer start normally.
7. **Use Provider:** inject `ObjectProvider<AuditSink>`, compare `getIfAvailable()` with `getObject()` when the bean is missing.
8. **Add no-op fallback:** create `NoOpAuditSink` and inject it as a conditional/explicitly contracted default bean; compare with omitting audit altogether.
9. **Optional setter:** move audit to a setter with `@Autowired(required=false)` and a no-op default, compare why wiring is now more mutable.
10. **Analyze concurrency:** explain why a `final PaymentGateway` does not guarantee the gateway implementation is thread-safe under concurrent calls.
11. **Defensive copy:** try mutating the list returned from `BillingPolicy.allowedTags()`, predict the exception, and distinguish shallow vs. deep immutability.
12. **Plain Java unit test:** pass a fake gateway and `Optional.empty()` to test `BillingService` without starting a context; distinguish testing business logic from testing wiring.

### Lesson Completion Checklist

- [ ] Distinguish required, optional, and default dependencies by **business contract**.
- [ ] Use constructor injection and `Objects.requireNonNull` for required dependencies.
- [ ] Accurately predict `Optional<AuditSink>` behavior without and with a bean.
- [ ] Do not confuse `ObjectProvider.getObject()` with `getIfAvailable()`.
- [ ] Explain `@Autowired(required=false)` on a setter and how it differs from constructor injection.
- [ ] Distinguish `final` reference, immutable state, deep immutability, and thread safety.
- [ ] Know why a missing PaymentGateway makes the context fail fast.
- [ ] Run the Java 17 Maven demo to get the exact 7 primary stdout lines and plain Java for the exact 3 lines.
- [ ] Know how to check for dependency ambiguity and avoid using optionality to mask configuration errors.

## 12. Summary and Official Documentation

**Key takeaways:**

- **Required dependency:** the object cannot be valid when it is missing; protect it with constructor injection, a non-null contract, and validation. Spring requires resolving it by default.
- **Optional dependency:** valid behavior still exists when absent; express it via `Optional<T>`, `ObjectProvider<T>`, or an appropriate default strategy. Do not mark genuinely required business logic as optional.
- **Immutability:** `final` fixes the reference but **does not automatically freeze the dependency's state**; use defensive copies and value objects when needed.
- **Good DI design:** business logic receives explicit dependencies and is testable in plain Java; Spring is the wiring/lifecycle tool, not the source of immutability rules.

Reference documentation:
- [Spring Framework – Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework – Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework – Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring Framework – Using @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring Framework – Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework – Dependency Resolution with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Java 17 – `java.util.Optional`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html)
- [Java 17 – `Objects.requireNonNull`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html)

**Conclusion:** In Spring Core Container, “required dependency” and “optional dependency” are **object design decisions**, while `Optional`, providers, and autowiring are the tools to implement those decisions. A service with an explicit constructor, validated required dependencies, and `final` references is easier to reason about, test, and operate without mistakenly assuming Spring makes every object immutable.