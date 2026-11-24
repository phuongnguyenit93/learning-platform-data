# Roadmap from Conceptual Model to Configuration Verification — Spring Core Container

## 1. Goal: From Understanding Principles to Verifiable Proof of a Working App

Learning **Spring Framework Core Container** should not stop at memorizing terms like `IoC`, `DI`, `bean`, or `ApplicationContext`. A configuration is truly useful only when you can point out **who needs whom**, **which bean satisfies that need**, **whether the container created and injected the right objects**, and **whether operational assumptions have been verified by real runtime behavior**.

This lesson walks through a **repeatable roadmap** for a small application using Java 17+ and Spring Framework: from conceptual sketch, contract design, configuration declarations, running the program, and checking the bean graph to diagnosing a broken configuration. It is a lesson **connecting design thinking with verification**; it is not an exhaustive catalog of every Spring annotation.

### After This Lesson, You Should Be Able To

1. Turn a short business requirement into **components, boundaries, and directed dependencies**.
2. Choose Java configuration with `@Configuration`/`@Bean` and **constructor injection** to assemble the model accurately.
3. Know how **bean definitions**, **bean instances**, **Java type contracts**, and **non-Spring-managed objects** differ.
4. Run a standalone `AnnotationConfigApplicationContext` without Spring Boot or a web server.
5. Verify **bean registration**, **collaborator identity**, **singleton scope**, **business behavior**, **program output**, and **context closing**.
6. Formulate negative tests for **missing beans**, **multiple candidate beans**, **constructor cycles**, and **unloaded configurations**.
7. Know when plain Java unit tests suffice and when spinning up a Spring context is needed to test wiring.

> **Learning rule:** Every step must have **verifiable output**. "The context started without errors" is just one signal; it does not prove all business logic or every dependency edge is right.

## 2. Full Roadmap Overview

~~~mermaid
flowchart TD
    A["Business requirements"] --> B["Object model and dependency graph"]
    B --> C["Java contracts: interface / constructor"]
    C --> D["Bean definitions: @Configuration / @Bean"]
    D --> E["ApplicationContext: register and refresh"]
    E --> F{"Context initializes?"}
    F -->|No| G["Read exception: missing / duplicate / cycle"]
    G --> C
    F -->|Yes| H["Get beans, check identity and scope"]
    H --> I["Run behavior and compare stdout"]
    I --> J["Run negative tests, close context, refine config"]
~~~

It can be broken into **6 acceptance milestones**:

| Milestone | Required deliverable | Verification evidence |
| --- | --- | --- |
| 1 — Concept | A dependency graph with clear edge directions | Able to state "which collaborator each consumer needs" |
| 2 — Design | Interfaces, constructors, method contracts | Can instantiate and test in plain Java |
| 3 — Configuration | Corresponding set of bean definitions | Bean names/types and injection points defined |
| 4 — Bootstrap | Runnable `ApplicationContext` | `refresh()`/initialization completes |
| 5 — Verification | Checks for registration, wiring, and behavior | PASS result / expected output |
| 6 — Failure & lifecycle | Missing/duplicate/cycle cases, cleanup | Able to reproduce and diagnose failures |

**Do not swap steps around:** if you do not yet know what the right dependency graph is, you might register enough beans for the context to start while still wiring the wrong implementation. Conversely, a correct diagram on paper does not guarantee the container has the right bean definitions.

## 3. Milestone 1 — Modeling Before Configuring

Suppose the application needs to generate a greeting for a user while recording the ID of the served user. The requirement has only three responsibilities:

- **Display-name lookup:** `UserDirectory` knows how to look up a user ID to obtain a name.
- **Greeting creation:** `GreetingService` uses `UserDirectory` without deciding how data is stored.
- **Coordination and auditing:** `GreetingFacade` uses `GreetingService` together with `AuditTrail`.

A reasonable diagram:

~~~mermaid
flowchart LR
    Facade["greetingFacade : GreetingFacade"]
    Service["greetingService : GreetingService"]
    Directory["userDirectory : UserDirectory"]
    Audit["auditTrail : AuditTrail"]
    Facade -->|"needs"| Service
    Facade -->|"needs"| Audit
    Service -->|"needs"| Directory
~~~

Arrow direction is **consumer → dependency**. `GreetingFacade` does not need to know the directory's implementation class, only a service that satisfies the contract.

This model contains four application beans. Spring may also register **infrastructure bean definitions** for its own annotation-processing machinery; therefore you should **not** assert that the context's entire `getBeanDefinitionCount()` equals 4. Instead, check **the four bean names explicitly registered by the application**.

### Distinguishing Three Modeling Layers

| Layer | Example | What to verify |
| --- | --- | --- |
| Java contract | `interface UserDirectory` | Methods, types, input/output constraints |
| Logical dependency | `GreetingService → UserDirectory` | Consumer class actually receives the right collaborator |
| Spring configuration | `@Bean UserDirectory userDirectory()` | Container has a compatible bean at runtime |

**Not every `new` is an IoC violation.** `new` inside a factory method or composition root is normal; the problem is when a business class locates/creates dependencies it should not be responsible for configuring.

### Turning Contracts into Testable Questions

- `UserDirectory.displayName("lan")` must return `"Lan"` in the demo implementation.
- `GreetingService.greet("lan")` must return `"Xin chao, Lan!"`.
- `GreetingFacade.send("lan")` must record one audit event **after** creating the greeting succeeds.
- Service and facade must receive **the same singleton beans** returned by the context (in the demo configuration).
- If the required `UserDirectory` is missing, configuration must not silently substitute `null`.

These are **acceptance criteria**, not vague statements like "Spring works well."

## 4. Milestone 2 — From Dependencies to Java Design

Prefer **constructor injection** for required dependencies:

~~~java
interface UserDirectory {
    String displayName(String userId);
}

final class GreetingService {
    private final UserDirectory directory;

    GreetingService(UserDirectory directory) {
        this.directory = java.util.Objects.requireNonNull(directory);
    }

    String greet(String id) {
        return "Xin chao, " + directory.displayName(id) + "!";
    }
}
~~~

**This is an illustrative snippet, not a standalone program.** It shows:

1. The service depends only on an **interface**, not on a specific storage mechanism.
2. The constructor accepts only one collaborator; the service class **does not call `ApplicationContext.getBean(...)`** inside domain logic.
3. The dependency is stored in a `final` field, preventing reference reassignment after construction.
4. It can be unit-tested with a fake implementation **without Spring**:

~~~java
UserDirectory fake = id -> "Test";
GreetingService service = new GreetingService(fake);
System.out.println(service.greet("anything")); // Xin chao, Test!
~~~

Here we already have **DI in design**, even before creating a Spring container. Spring only automates **registration, candidate lookup, instantiation, injection, and lifecycle**.

### When Is an Abstraction Unnecessary?

Do not create an interface just because "learning Spring means having interfaces." It adds value when representing a clear contract, supporting multiple implementations, enabling test fakes, or separating domain from infrastructure. For a pure stateless computation utility, a simple Java class remains appropriate.

## 5. Milestone 3 — Registering Bean Definitions

In Spring Java configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    UserDirectory userDirectory() {
        return new InMemoryDirectory();
    }

    @Bean
    GreetingService greetingService(UserDirectory directory) {
        return new GreetingService(directory);
    }
}
~~~

**Non-standalone illustration** because `InMemoryDirectory` does not appear in this isolated snippet. Each `@Bean` declares a **bean definition** from a factory method; **the default bean name is usually the method name**. The `UserDirectory directory` parameter is what Spring must resolve from available beans.

Be sure to distinguish:

- **Registering a bean definition:** the context knows *how* to create the bean.
- **Creating a bean instance:** the context actually runs the factory/constructor at the appropriate time.
- **Injection:** the matching object is passed into the dependency point.
- **Usage:** business code explicitly calls methods as normal; Spring does not automatically call `greet` just because a bean is registered.

With `@Configuration(proxyBeanMethods = false)`, do not directly call another `@Bean` method to "get the singleton bean." That may just be a plain Java call. Declare dependencies using **factory method parameters**, like `greetingService(UserDirectory directory)`, so the container resolves them.

### BeanFactory and ApplicationContext

`BeanFactory` provides the core bean lookup mechanism; `ApplicationContext` extends it with lifecycle management, events, message resources, and convenient bootstrapping. This lesson uses `AnnotationConfigApplicationContext` for plain Java startup.

By default, regular singletons are instantiated when `ApplicationContext` refreshes; `@Lazy` or other scopes can defer this. **A bean definition existing does not mean an instance has been created**. Do not rely on the order in which methods are listed as an initialization-order contract.

## 6. Milestones 4–5 — Complete Project with Live Runtime Checks

The following project uses **Java 17**, **Maven**, and **Spring Framework 6.2.19** via `spring-context`. This is a pinned version to keep the example reproducible, **not a claim that it is the latest Spring version**. The program needs no Spring Boot, database, or HTTP server.

~~~text
config-verification-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ConfigurationVerificationDemo.java
~~~

### 6.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>config-verification-demo</artifactId>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ConfigurationVerificationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven automatically downloads `spring-context` along with required transitive dependencies. If you try placing only a single Spring JAR on the classpath, the compiler or runtime may report missing classes from other modules.

### 6.2. `src/main/java/demo/ConfigurationVerificationDemo.java`

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class ConfigurationVerificationDemo {
    private ConfigurationVerificationDemo() {}

    public interface UserDirectory {
        String displayName(String userId);
    }

    public static final class InMemoryDirectory
            implements UserDirectory {
        @Override
        public String displayName(String userId) {
            if ("lan".equals(userId)) {
                return "Lan";
            }
            throw new IllegalArgumentException("unknown user");
        }
    }

    public static final class GreetingService {
        private final UserDirectory directory;

        public GreetingService(UserDirectory directory) {
            this.directory = Objects.requireNonNull(directory);
        }

        public String greet(String userId) {
            return "Xin chao, " + directory.displayName(userId) + "!";
        }

        public UserDirectory directory() {
            return directory;
        }
    }

    public static final class AuditTrail {
        private final List<String> events = new ArrayList<>();

        public void record(String userId) {
            events.add(userId);
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    public static final class GreetingFacade {
        private final GreetingService service;
        private final AuditTrail audit;

        public GreetingFacade(GreetingService service, AuditTrail audit) {
            this.service = Objects.requireNonNull(service);
            this.audit = Objects.requireNonNull(audit);
        }

        public String send(String userId) {
            String message = service.greet(userId);
            audit.record(userId);
            return message;
        }

        public GreetingService service() {
            return service;
        }

        public AuditTrail audit() {
            return audit;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public UserDirectory userDirectory() {
            return new InMemoryDirectory();
        }

        @Bean
        public AuditTrail auditTrail() {
            return new AuditTrail();
        }

        @Bean
        public GreetingService greetingService(UserDirectory directory) {
            return new GreetingService(directory);
        }

        @Bean
        public GreetingFacade greetingFacade(
                GreetingService service, AuditTrail audit) {
            return new GreetingFacade(service, audit);
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            String[] appBeanNames = {
                "userDirectory", "auditTrail",
                "greetingService", "greetingFacade"
            };
            for (String beanName : appBeanNames) {
                require(context.containsBeanDefinition(beanName),
                        "missing bean definition: " + beanName);
            }
            System.out.println("definitions=4/4");

            UserDirectory directory = context.getBean(UserDirectory.class);
            GreetingService service =
                    context.getBean(GreetingService.class);
            AuditTrail audit = context.getBean(AuditTrail.class);
            GreetingFacade facade = context.getBean(GreetingFacade.class);

            require(service.directory() == directory,
                    "service is wired to wrong directory");
            require(facade.service() == service,
                    "facade is wired to wrong service");
            require(facade.audit() == audit,
                    "facade is wired to wrong audit");
            System.out.println("wiring=PASS");

            require(context.getBean(GreetingService.class) == service,
                    "greetingService is not singleton");
            System.out.println("singleton=PASS");

            System.out.println("message=" + facade.send("lan"));
            System.out.println("audit=" + audit.snapshot());
        }
    }
}
~~~

The program has one `public` top-level class matching the filename, with supporting types nested inside. `@Bean` factory methods pass dependencies through **parameters** without calling one another. `@Autowired` is not needed on factory methods: Spring resolves `@Bean` method arguments automatically.

The `require(...)` checks **always execute**. Unlike Java `assert`, they **are not skipped** when running by default without `-ea`.

### 6.3. Running with Maven

Inside the `config-verification-demo` directory:

~~~bash
java -version
mvn -version
mvn -q clean compile exec:java
~~~

**Exact stdout printed by the application when all checks PASS:**

~~~text
definitions=4/4
wiring=PASS
singleton=PASS
message=Xin chao, Lan!
audit=[lan]
~~~

`java -version`, `mvn -version`, and Maven/Spring log lines (if shown by logging config) do not belong to these **five application stdout lines**. If any `require` check fails, the program **must not** continue printing subsequent PASS lines; the exception pinpoints which assumption failed.

### 6.4. Compiling and Running Directly with `javac`/`java`

For Spring code, the classpath must include Spring JARs and required transitive dependencies. You can ask Maven to generate a classpath file:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/ConfigurationVerificationDemo.java
java -cp "out:$(cat classpath.txt)" demo.ConfigurationVerificationDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/ConfigurationVerificationDemo.java
java -cp "out;$deps" demo.ConfigurationVerificationDemo
~~~

Unix uses `:` as the classpath separator; Windows uses `;`. Running the same class produces the exact same **five stdout lines** from section 6.3. `package org.springframework... does not exist` usually indicates Spring is missing from the classpath, **not that IoC logic itself is wrong**.

## 7. Reading the Checks: Layer-by-Layer Verification

| Check performed | Proof | What it does **not** prove |
| --- | --- | --- |
| `containsBeanDefinition(name)` for four names | Four application bean definitions are registered | That any bean necessarily initializes all behavior properly |
| `getBean(Type.class)` | Container can supply a candidate of the requested type | That every business use case is right |
| Comparing `service.directory() == directory` | The exact directory bean was injected into service | That the directory implementation has no business bugs |
| Comparing `facade.service() == service` and `facade.audit() == audit` | Wiring edges are connected to the right objects | That every runtime path invokes collaborators |
| Calling `getBean(GreetingService.class) == service` again | Same singleton instance within this context | That every bean is singleton or JVM-wide singleton |
| `facade.send("lan")` and `audit.snapshot()` | Greeting logic and audit recording work for the sample case | That other environment configurations are also right |
| `try-with-resources` closes context | Code closes context on block exit | That every manually created resource outside container was cleaned up |

**Do not confuse counts:** `definitions=4/4` means *the four target application bean names are present*, **not** `context.getBeanDefinitionCount() == 4`. Spring registers additional infrastructure definitions to support annotations/configuration.

**Do not use `==` blindly:** reference comparison here is an identity check within a specific singleton configuration. It does not mean every bean of the same type across different contexts is the same object, nor that prototypes/scoped proxies follow those assumptions.

### Why Identity-Based Wiring Checks Are Useful

A context can start successfully while selecting the wrong implementation of an interface when multiple beans are compatible. When you know the **intended target** is a specific bean, you can check in a wiring test that the injected reference matches that bean. For proxies/scoped beans, adapt checks to the appropriate contract rather than forcing raw implementation identity checks.

## 8. Milestone 6 — Controlled Fault-Injection Testing

After the happy path works, try **negative tests** on isolated configurations. Do not break the `AppConfig` used for the happy path and then guess ambiguously.

### Case A: Missing Required Dependency

Illustrative snippet, to be placed in an appropriate class/config:

~~~java
@Configuration(proxyBeanMethods = false)
class MissingDirectoryConfig {
    @Bean
    GreetingService greetingService(UserDirectory directory) {
        return new GreetingService(directory);
    }
}
~~~

When loading **only** `MissingDirectoryConfig` with no other `UserDirectory` bean, the container cannot resolve the `directory` parameter for the factory method. The context typically fails to refresh; the exception chain may include `UnsatisfiedDependencyException` or `NoSuchBeanDefinitionException`.

**Reliable observation:** *the context fails due to a missing required bean*, independent of exact stack trace wording — message text, line numbers, and wrappers can vary across versions/configs.

### Case B: Multiple Competing Beans

~~~java
@Bean
UserDirectory directoryOne() { return new InMemoryDirectory(); }

@Bean
UserDirectory directoryTwo() { return new InMemoryDirectory(); }
~~~

This is an **illustrative snippet** in another configuration. If an injection point requests **a single `UserDirectory`** while two equivalent candidates exist, Spring may report `NoUniqueBeanDefinitionException`. Consider:

- Selecting a bean with `@Qualifier` at the injection point.
- Placing `@Primary` on the preferred candidate when clearly justified.
- Removing unnecessary registration or adjusting design so the contract is clear.
- If the application needs multiple implementations, injecting a collection or `ObjectProvider<UserDirectory>` as needed.

Note: Spring has multiple candidate-selection rules (qualifiers, primary, fallback, parameter names, etc.). **Having two beans of the same type does not mean every injection is guaranteed to fail**, though it is a case worth testing intentionally.

### Case C: Constructor Cycle

~~~java
final class A {
    A(B b) {}
}

final class B {
    B(A a) {}
}
~~~

If A and B are registered and each requires the other right in its constructor, the dependency graph contains a cycle A→B→A. It cannot be resolved normally by "creating one bean first"; you must **change the design or responsibility boundaries**, not use field injection as a default bandage.

### Case D: Configuration Class Not Registered

A `@Configuration` or `@Component` existing in source code **does not automatically appear in the context**. If you load only `OtherConfig.class`, beans in `AppConfig.class` are not registered unless imported/scanned/registered through the appropriate mechanism. Always check **which configuration objects were supplied to the context**, rather than just looking for annotations in source files.

### Case E: Using `new` Outside the Container

~~~java
GreetingService manual = new GreetingService(
        userId -> "Manual");
System.out.println(manual.greet("x")); // Xin chao, Manual!
~~~

This is an illustrative snippet inside a method with access to the nested classes. `manual` is an ordinary Java object, **not a Spring bean**. It can run cleanly because the caller passed the dependency manually; do not expect it to receive context callbacks or bean scoping automatically.

## 9. Stage-by-Stage Failure Triage Roadmap

| Stage | Symptom | First place to check |
| --- | --- | --- |
| Java compilation | `cannot find symbol` / `package org.springframework... does not exist` | Class names, packages, Maven dependencies, classpath, JDK |
| Context refresh | `UnsatisfiedDependencyException` | Which bean needs which dependency type; missing registration or scan |
| Candidate selection | `NoUniqueBeanDefinitionException` | How many matching beans exist, qualifiers/primary, injection contract |
| Circular wiring | `BeanCurrentlyInCreationException` | Draw the constructor/factory dependency cycle |
| Runtime behavior | Wrong greeting printed | Check directory implementation, inputs, service logic; don't blame Spring for everything |
| Scope | Two bean lookups give unexpected identities | Check scope, provider, lazy, proxy, and whether it's the same context |
| Lifecycle | Resource unclosed or callback not called | Is bean container-managed, with matching scope/lifecycle hook? |
| Startup vs. tests | Unit tests PASS, context FAILS | Unit tests didn't verify bean registration/wiring; add a wiring smoke test |

**Read exceptions from the root cause:** a `BeanCreationException` on a higher-level bean is often just a symptom of a failing dependency bean. Follow the `Caused by` chain to locate the first injection point, bean definition, or constructor/factory that failed.

**Do not** catch every `BeansException` and continue with null dependencies: a configuration missing a required dependency should **fail fast** instead of silently leaving the app in an invalid state.

## 10. Two-Layer Testing Without Blind Reliance on Annotations

### Plain Java Design Unit Tests

A fake without Spring:

~~~java
UserDirectory fake = id -> "Tester";
GreetingService service = new GreetingService(fake);
System.out.println(service.greet("x")); // Xin chao, Tester!
~~~

This is an illustrative snippet, **not a standalone Java file**; it can live inside a test method or example class. Unit tests focus on outputs when swapping implementations, input handling, and logic side effects.

### Integration/Smoke Tests for Spring Configuration

Spin up a context with the real configuration:

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {
    GreetingFacade facade = context.getBean(GreetingFacade.class);
    // Verify bean graph, collaborator identity, and behavior.
}
~~~

This is also a snippet inside a program/test with access to the nested classes. Verify the real configuration: right bean names, unambiguous dependencies, no missing/duplicate beans, scopes, and sample behavior. If the system has multiple profiles/conditional beans, test the **environment combinations actually supported**, not just a single default context.

You do not need the full Spring Test infrastructure for a small example; once you have JUnit/Spring Test, similar checks can go into automated tests. Remember: **passing unit tests do not prove wiring is right; correct wiring does not prove business logic is right**.

## 11. How to Ramp Up Complexity After This Example

Once you observe the five expected stdout lines, progress in order:

1. **Swap implementation:** create another `UserDirectory` (e.g., returning a name from config), explicitly select a bean with `@Qualifier` when multiple candidates exist. Verify the output changes as expected without editing `GreetingService`.
2. **Split configurations:** divide factory methods into infrastructure and service configs; use `@Import` or register them explicitly on the context. Verify no beans are accidentally lost.
3. **Try optional dependencies:** if auditing is optional by contract, explore `ObjectProvider<AuditTrail>` or appropriate nullable handling; do not turn required dependencies into optional ones to hide bugs.
4. **Explore scopes/lazy:** compare singleton vs. prototype, without relying on `==` for other scopes; observe when instances are created.
5. **Observe lifecycles:** add a bean holding a simulated resource with a destroy callback and close the context. Distinguish container-managed beans from manually instantiated objects.
6. **Separate unit and integration tests:** one suite using plain Java only, the other actually booting a context. Run them in your build pipeline as the system grows.

### When Is a Configuration Task Complete?

A configuration has minimal acceptable proof when:

- There is a clear dependency/contract model, not just annotations.
- Sufficient bean definitions are registered for required dependencies.
- The context bootstraps in the intended environment.
- Critical wiring edges are verified, not just calling `getBean` on an arbitrary class.
- Sample behavioral cases produce concrete expected results.
- At least one configuration failure case is understood and diagnosed accurately.
- The context is closed when the application owns its lifecycle.
- It does not rely on accidental init order, unchecked bean names/counts, or machine-specific environments.

## 12. Misconceptions to Avoid

- **"Reading annotations tells you the app is right."** Annotations only declare metadata; runtime verification is still required.
- **"The Spring container runs all business logic automatically."** The container handles wiring/lifecycle; method behavior comes from your Java code.
- **"The context starting finishes all testing."** Wiring could succeed while picking the wrong implementation or having logic bugs.
- **"Bean count must equal the number of `@Bean` methods I wrote."** Infrastructure definitions and other registration mechanisms may exist; check target bean names instead of unverified total counts.
- **"Singleton means one object across every JVM."** Default singleton is per bean definition within one container.
- **"Having an interface makes Spring automatically pick the right implementation."** A matching bean must exist; multiple candidates need explicit resolution.
- **"`@Lazy` removes a dependency."** No; it only changes resolution/creation timing in applicable configurations.
- **"You must pass `-ea` to validate configuration."** No; use regular runtime checks/test assertions that execute regardless of JVM assertion flags.
- **"You need Spring Boot to use IoC."** No; this example runs with plain Spring Framework and Maven.

## 13. Self-Check Exercises and Answers

**Exercise 1.** `GreetingFacade` depends on `GreetingService` and `AuditTrail`; `GreetingService` depends on `UserDirectory`. Draw the edges, direction, and count of application bean definitions.

**Answer:** Three edges: facade→service, facade→audit, service→directory. Four application bean definitions are registered. Do not infer `getBeanDefinitionCount() == 4` for the whole context.

**Exercise 2.** Keep the config unchanged but edit `InMemoryDirectory` to return `"Mai"` for id `"lan"`. Which classes need editing, and which stdout line changes?

**Answer:** Edit only the directory implementation or how the factory creates it; `GreetingService` needs no edits. The `message=...` line changes with the data, while wiring/singleton checks can keep passing.

**Exercise 3.** Why is `facade.service() == context.getBean(GreetingService.class)` meaningful in the demo, yet not a universal rule for all scopes?

**Answer:** In the demo both retrieve the same singleton from the same context. Prototypes, scoped proxies, and providers have different semantics, so do not blindly apply the same identity check across all designs.

**Exercise 4.** Register two different `UserDirectory` beans while keeping a single unqualified `UserDirectory directory` parameter. What must you check?

**Answer:** Review the full candidate selection rules and verify which bean is actually injected. Without a unique choice, the context fails due to ambiguity; use qualifiers/primary or adjust registration.

**Exercise 5.** Unit tests with a fake PASS, yet `new AnnotationConfigApplicationContext(AppConfig.class)` fails. Is that a contradiction?

**Answer:** No. Unit tests only prove the service works when the caller supplies a dependency; integration tests are needed to confirm Spring can **register and resolve** the real dependency.

## 14. Application Checklist

- [ ] Write down clear business requirements and responsible classes.
- [ ] Draw the bean graph in **consumer → dependency** direction, avoiding circular dependencies.
- [ ] Design contracts and constructor injection before placing annotations.
- [ ] List each bean definition: name, type, factory, scope, and dependencies.
- [ ] Bootstrap `ApplicationContext` with the exact configuration being tested.
- [ ] Verify existence of **target bean names**, without assuming total definition count.
- [ ] Verify actual wiring (by reference or behavior) along critical edges.
- [ ] Verify singleton/lifecycle semantics matching the configured scope.
- [ ] Run sample behavior and compare against expected stdout.
- [ ] Prepare failure cases for missing/duplicate beans, constructor cycles, and unloaded config.
- [ ] Close the context and track application-owned resources.
- [ ] Separate plain Java tests from Spring wiring tests; do not substitute one for the other.

**Conclusion:** An effective workflow is **sound model → clear contracts → accurate bean definitions → container bootstrap → verify wiring and behavior → test failure cases**. Runtime evidence turns conceptual knowledge of IoC/DI and the Core Container into practical engineering capability.

### Official Documentation

- [Spring IoC Container — Introduction](https://docs.spring.io/spring-framework/reference/6.2/core/beans/introduction.html)
- [Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html)
- [Using @Bean](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html)
- [BeanFactory and ApplicationContext](https://docs.spring.io/spring-framework/reference/6.2/core/beans/beanfactory.html)
