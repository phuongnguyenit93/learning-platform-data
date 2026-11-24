# Selection Rules When Multiple Constructors Exist — `@Autowired` in Spring Framework

## 1. The Problem to Understand

A Java class can **overload constructors**: declare constructors with the same class name but different parameter lists. When calling `new` yourself, the **Java compiler** picks the overload based on the arguments you pass. When **Spring creates a bean from that class**, the container must decide **which constructor to use** and which dependencies it can resolve to pass in.

Two different mechanisms:

- **Java overload resolution:** for example, `new ReportService(tracer)` invokes the constructor accepting `Tracer`, because the Java expression explicitly specifies the argument.
- **Spring constructor resolution:** for example, `context.getBean(ReportService.class)` (when the bean is registered) can trigger Spring to choose a constructor based on `@Autowired`, matching candidates, a default constructor, and bean definition metadata.

**There is no rule that "the longest constructor always wins".** Only in the situation where **multiple constructors are marked `@Autowired(required=false)`** does Spring inspect candidate constructors and pick the constructor **with the most dependencies that the container can resolve**, according to autowiring policy. If no candidate fits and a suitable default/primary constructor exists, Spring can use it. That rule does not mean picking any longest constructor in the class arbitrarily.

After this article, you will be able to:

1. Distinguish Java constructor overloading from Spring's constructor selection mechanism for beans.
2. Explain the case where **a single constructor does not need `@Autowired`**.
3. Understand the default meaning of `@Autowired(required=true)`: only **one** constructor in the same class can be marked required.
4. Understand multiple constructors with `@Autowired(required=false)`, **greedy satisfiable candidate**, and falling back to a default constructor.
5. Know what happens when a class has multiple constructors **without marking `@Autowired`**.
6. Distinguish **constructor selection** from **bean candidate selection** for each parameter (`@Primary`, `@Qualifier`, ambiguity).
7. Verify using a **pure Java 17+ / Spring Framework Core Container** project, Maven, and `javac`/`java` commands with deterministic stdout.
8. Recognize errors and design constructor injection that is readable, testable, and avoids overusing many overloads.

**Scope:** Only explores **constructor selection rules when Spring instantiates a bean**, without needing Spring Boot, JPA, Lombok, Kotlin, or XML. Special Java/Spring cases are noted to avoid misapplying a single rule to every form of bean registration.

## 2. Scenarios in One Table

| Constructors of a Class | How Spring Typically Handles It |
| --- | --- |
| Only **one constructor** | Uses that constructor, even without `@Autowired`; dependencies must be resolvable |
| Multiple constructors, **one** annotated with default `@Autowired` (`required=true`) | Uses the marked constructor; missing required dependency causes failure, does not arbitrarily switch to another constructor |
| Multiple constructors all annotated with `@Autowired(required=false)` | Evaluates candidates; picks the constructor with **the most resolvable dependencies** |
| All `required=false` annotated candidates fail to resolve | Falls back to default/primary constructor **if present** |
| Multiple constructors, **none annotated with `@Autowired`**, has default no-arg | Uses the no-arg constructor by default; does not greedily pick the longest overload |
| Multiple constructors, no annotations, no suitable default/primary constructor | Should not expect Spring to guess; clarify which constructor to inject or provide bean creation metadata |
| Multiple constructors with **two `@Autowired(required=true)` annotations** | Invalid configuration; cannot have two required annotated constructors |
| One required annotated constructor **and** an optional annotated constructor | Invalid per annotation rules: a required constructor must be the sole annotated constructor |

> In the table, *primary constructor* means a main constructor recognized by Spring according to appropriate rules/language/metadata; do **not** confuse it with `@Primary`, which selects a **bean** among multiple candidates.

Spring's constructor rules are documented in the JavaDoc for `org.springframework.beans.factory.annotation.Autowired` and `AutowiredAnnotationBeanPostProcessor`. They do not require every overload to be public; however, this article uses public constructors to keep code easy to follow and independent of module accessibility issues.

## 3. Simple Case: One Constructor, No `@Autowired` Needed

~~~java
@Component
final class SingleConstructorService {
    private final Tracer tracer;

    public SingleConstructorService(Tracer tracer) {
        this.tracer = java.util.Objects.requireNonNull(tracer);
    }
}
~~~

This is an **illustrative snippet**: `Tracer` must be declared and `@Component` imported. In Spring 4.3+ (including Spring Framework 6.2), if a bean class **has only one constructor**, Spring can use that constructor **without requiring `@Autowired`**.

Notes:

- Spring only auto-creates/injects dependencies into **beans it manages**. If `SingleConstructorService` is not registered via component scan, `context.register(...)`, or an appropriate bean definition, annotations in source code do not spawn instances by themselves.
- Without a matching `Tracer` bean, Spring **does not pass null automatically** to create a valid service; bean creation typically fails.
- Java still allows `new SingleConstructorService(tracer)` without Spring: constructor injection is fundamentally a plain Java technique.
- If there is only one constructor and you add `@Autowired`, it is valid, though usually redundant syntax.
- With a single constructor that has multiple parameters, Spring will attempt to resolve the needed dependencies. The "one constructor" rule **does not make every parameter optional**.

### `@Autowired` Is Not the Sole Sign of Bean Registration

A class with a constructor that is not a bean will not participate in dependency injection automatically. This example:

~~~java
SingleConstructorService local =
        new SingleConstructorService(new ConsoleTracer());
~~~

is **manual wiring in Java**, not Spring DI. If `ConsoleTracer` is a regular Java object and you do not register it, it does not turn into a managed Spring bean merely because it was passed into a constructor.

## 4. Multiple Constructors: One `@Autowired(required=true)` Constructor

The default of `@Autowired` is `required=true`. Writing:

~~~java
@Component
final class StrictService {
    private final Tracer tracer;

    public StrictService() {
        this.tracer = null;
    }

    @Autowired
    public StrictService(Tracer tracer) {
        this.tracer = java.util.Objects.requireNonNull(tracer);
    }
}
~~~

This is an **illustrative snippet of selection rules**, not a recommended structure for a business service because the default constructor leaves a null state. In the context of Spring bean creation:

- The `StrictService(Tracer)` constructor is marked **required**, so Spring selects it for constructor injection.
- If the context has no suitable `Tracer`, bean creation **fails**; Spring does not fall back to `StrictService()` just to avoid an error.
- If the context has exactly one matching `Tracer`, Spring passes it into the annotated constructor.
- Having a Java no-arg constructor **does not turn a required dependency into an optional one**.

In real-world design, if `Tracer` is required for the service to operate, one usually **keeps only the constructor accepting Tracer**; that way plain Java also prevents creating an invalid instance. The snippet here intentionally keeps both constructors to observe Spring's choice.

**Do not** attach `@Autowired(required=true)` to two constructors in the same class. That is a conflicting configuration; Spring does not use source code order to "pick one arbitrarily" between the two.

## 5. Multiple `@Autowired(required=false)` Constructors: Picking a Suitable Candidate

Pattern:

~~~java
@Component
final class FlexibleService {
    private final String selection;

    public FlexibleService() {
        this.selection = "default";
    }

    @Autowired(required = false)
    public FlexibleService(Tracer tracer) {
        this.selection = "tracer";
    }

    @Autowired(required = false)
    public FlexibleService(Tracer tracer, Formatter formatter) {
        this.selection = "tracer+formatter";
    }

    String selection() {
        return selection;
    }
}
~~~

This is a **snippet**; two types `Tracer` and `Formatter` must be properly registered. Spring evaluates constructors annotated `required=false` as **alternatives**, rather than applying "nullable parameter" semantics to each constructor.

| Available Collaborator Beans | Constructor Selected in Example | Value of `selection` |
| --- | --- | --- |
| Both a `Tracer` and a `Formatter` present | `FlexibleService(Tracer, Formatter)` | `tracer+formatter` |
| `Tracer` present, no `Formatter` | `FlexibleService(Tracer)` | `tracer` |
| Neither `Tracer` nor `Formatter` present | `FlexibleService()` | `default` |

This is the common case of the **"constructor satisfying the most dependencies"** rule, subject to these conditions:

- The longer constructor must be **satisfiable**: its required parameters must be compatibly resolvable by the container.
- There are multiple `@Autowired(required=false)` constructors; they are all **candidates**. If multiple candidates tie in priority/resolvability, do not design around a "random pick" rule; clarify via a single constructor or proper annotation/metadata.
- A no-arg constructor acts as a **fallback** if no annotated candidate can be resolved.
- `@Autowired(required=false)` on a constructor **does not mean Spring will pass null for any parameter lacking a bean**, nor does it mean Spring always instantiates the service via the longest constructor.
- Spring can hit errors other than "no candidate", for example a parameter having **multiple beans that cannot be uniquely disambiguated** or a dependency bean failing during initialization. Do not treat every failure as a guaranteed reason to fall back.
- If the "no Tracer" situation renders the service meaningless, designing a `FlexibleService()` fallback will mask missing configuration. When a collaborator is genuinely required, it is better to keep only one required constructor.

### Do Not Confuse `required=false` on a Constructor with an Optional Field/Method

With a setter or field:

~~~java
@Autowired(required = false)
public void setMetrics(MetricsClient metrics) {
    this.metrics = metrics;
}
~~~

Spring can **skip the injection point** if the dependency is absent (per appropriate rules). With **constructor alternatives**, Spring is choosing **one out of multiple constructors** to create the object; there is no such thing as running all constructors or "skipping" unavailable parameters.

If a dependency is genuinely optional **within a single constructor**, consider `Optional<T>`, `@Nullable`, or `ObjectProvider<T>` when semantics fit; that is a **parameter/injection-point** concern, not defaulting to multiple constructors.

## 6. No `@Autowired` When Multiple Constructors Exist

Consider this example:

~~~java
@Component
final class UnannotatedService {
    private final String selected;

    public UnannotatedService() {
        this.selected = "default";
    }

    public UnannotatedService(Tracer tracer) {
        this.selected = "tracer";
    }
}
~~~

This is a class with **two constructors and neither constructor annotated with `@Autowired`**. When Spring is asked to instantiate this bean via normal constructor injection in the demo, it uses the **no-arg default constructor**, even if the context already has a `Tracer` bean. Reason: Spring does not automatically apply the "greediest satisfiable" rule meant for **multiple optional annotated constructors** to arbitrary unannotated constructors.

If a class has **multiple constructors, no no-arg constructor, and no suitable default/primary constructor metadata**, the choice can be ambiguous and lead to bean creation failure. Do not guess that Spring picks "the first one" or "the one with the fewest parameters". Instead:

1. Pick **one** meaningful constructor and annotate it with `@Autowired` when multiple overloads exist.
2. Or remove unnecessary overloads so only one constructor remains.
3. Or use a `@Bean` factory method with explicit logic and arguments.
4. Only if there are **genuinely** multiple valid initialization configurations, consider multiple `@Autowired(required=false)` alternatives.

**Unlike the single-constructor case:** one constructor needs no annotation, but once you **add an overload**, constructor selection semantics can change. This is why a seemingly harmless refactor like adding a no-arg constructor for another framework can cause Spring to stop injecting dependencies as intended.

## 7. Selecting a Constructor Differs from Selecting a Bean for a Parameter

Spring goes through two separate questions:

1. **Which constructor is considered suitable to invoke?**
2. **Which bean instance does each parameter of that constructor receive?**

Suppose a constructor requires `Tracer`, but the context has:

~~~java
@Bean("fileTracer")
Tracer fileTracer() { return new FileTracer(); }

@Bean("consoleTracer")
Tracer consoleTracer() { return new ConsoleTracer(); }
~~~

This is a **non-standalone snippet**, missing type and class definitions. It illustrates two beans of the same type. Spring must resolve a single-valued `Tracer` from multiple candidates using appropriate rules, which may require:

- `@Qualifier("consoleTracer")` on the constructor parameter needing that specific bean.
- `@Primary` on the bean intended as the default choice.
- Clarifying bean names/types and registration conditions to avoid creating redundant candidates.
- Using `List<Tracer>`/`Map<String, Tracer>` or `ObjectProvider<Tracer>` if the contract genuinely wants multiple beans.

**Note:** `@Primary` selects a **bean candidate**, not a "primary constructor" among overloads. Conversely, `@Autowired` on a constructor helps Spring identify the allowed constructor, but **does not resolve ambiguity among beans of the same type**.

Explicit constructor example:

~~~java
@Autowired
public DeliveryService(
        @Qualifier("consoleTracer") Tracer tracer) {
    this.tracer = java.util.Objects.requireNonNull(tracer);
}
~~~

This snippet needs a full `DeliveryService` declaration and proper imports. In the main demo program we deliberately have **at most one bean per type** so constructor selection results do not depend on qualifiers, `@Primary`, or ambiguity.

### A Bean Failing During Creation Is Also a Separate Issue

If the container knows of a `Tracer` yet the factory method creating `Tracer` throws an exception, that is not simply "no Tracer bean". Spring may throw `BeanCreationException` and other wrapper exceptions. Do not casually rely on a fallback constructor to hide real initialization failures of a dependency.

## 8. Complete Java 17+ Example: Six Constructor Selection Cases

The demo uses **Spring Framework 6.2.19** from Maven and **JDK 17+**. The version is pinned for reproducibility, not claimed to be the latest. The program opens **independent** Spring contexts to demonstrate three choices of a flexible class, a single unannotated constructor, two unannotated constructors, and a required constructor.

### 8.1. Structure

~~~text
autowired-constructor-selection/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ConstructorSelectionDemo.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>autowired-constructor-selection</artifactId>
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
                    <mainClass>demo.ConstructorSelectionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The `spring-context` module pulls in Spring Core Container dependencies. Maven requires repository access if the artifacts are not yet cached. Do not just copy `spring-context.jar` and expect enough classpath for `javac` and `java` to run.

### 8.3. File src/main/java/demo/ConstructorSelectionDemo.java

~~~java
package demo;

import java.util.Objects;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.stereotype.Component;

public final class ConstructorSelectionDemo {
    private ConstructorSelectionDemo() {}

    public interface Tracer {}
    public interface Formatter {}

    public static final class ConsoleTracer implements Tracer {
        public ConsoleTracer() {}
    }

    public static final class PlainFormatter implements Formatter {
        public PlainFormatter() {}
    }

    public interface Choice {
        String selected();
    }

    // Multiple candidates: both overloads are required=false.
    @Component
    public static final class FlexibleClient implements Choice {
        private final String selection;

        public FlexibleClient() {
            this.selection = "default";
        }

        @Autowired(required = false)
        public FlexibleClient(Tracer tracer) {
            Objects.requireNonNull(tracer);
            this.selection = "tracer";
        }

        @Autowired(required = false)
        public FlexibleClient(Tracer tracer, Formatter formatter) {
            Objects.requireNonNull(tracer);
            Objects.requireNonNull(formatter);
            this.selection = "tracer+formatter";
        }

        @Override
        public String selected() {
            return selection;
        }
    }

    // Single constructor: @Autowired is not needed.
    @Component
    public static final class SingleClient implements Choice {
        private final Tracer tracer;

        public SingleClient(Tracer tracer) {
            this.tracer = Objects.requireNonNull(tracer);
        }

        @Override
        public String selected() {
            return tracer == null ? "UNEXPECTED" : "tracer";
        }
    }

    // Two unannotated constructors: default is used.
    @Component
    public static final class UnannotatedClient implements Choice {
        private final String selection;

        public UnannotatedClient() {
            this.selection = "default";
        }

        public UnannotatedClient(Tracer tracer) {
            Objects.requireNonNull(tracer);
            this.selection = "tracer";
        }

        @Override
        public String selected() {
            return selection;
        }
    }

    // One constructor annotated with default required=true.
    @Component
    public static final class RequiredClient implements Choice {
        private final String selection;

        public RequiredClient() {
            this.selection = "default";
        }

        @Autowired
        public RequiredClient(Tracer tracer) {
            Objects.requireNonNull(tracer);
            this.selection = "required-tracer";
        }

        @Override
        public String selected() {
            return selection;
        }
    }

    private static String choose(
            Class<? extends Choice> beanClass,
            boolean hasTracer, boolean hasFormatter) {

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {

            if (hasTracer) {
                context.registerBean(Tracer.class, ConsoleTracer::new);
            }
            if (hasFormatter) {
                context.registerBean(Formatter.class, PlainFormatter::new);
            }

            context.register(beanClass);
            context.refresh();
            return context.getBean(beanClass).selected();
        }
    }

    public static void main(String[] args) {
        System.out.println("flexibleBoth=" +
                choose(FlexibleClient.class, true, true));
        System.out.println("flexibleTracerOnly=" +
                choose(FlexibleClient.class, true, false));
        System.out.println("flexibleNone=" +
                choose(FlexibleClient.class, false, false));

        System.out.println("singleNoAnnotation=" +
                choose(SingleClient.class, true, false));

        System.out.println("multipleNoAnnotation=" +
                choose(UnannotatedClient.class, true, false));

        System.out.println("requiredPresent=" +
                choose(RequiredClient.class, true, false));

        try {
            choose(RequiredClient.class, false, false);
            System.out.println("requiredMissing=UNEXPECTED");
        } catch (BeansException expected) {
            System.out.println("requiredMissing=REJECTED");
        }
    }
}
~~~

**Why the example is clear and does not need component scanning:**

- There is only **one public top-level class** `ConstructorSelectionDemo`; helper classes are `public static` nested classes. File/package names match the path.
- `AnnotationConfigApplicationContext()` creates an empty/unrefreshed context, then `registerBean(Tracer.class, ...)` and `registerBean(Formatter.class, ...)` are intentionally called before `refresh()`.
- `context.register(beanClass)` directly registers the exact class for Spring to create. Each call to `choose(...)` uses **a fresh context** so bean definitions/candidates do not leak across experiments.
- `ConsoleTracer` and `PlainFormatter` have public no-arg constructors; method references `ConsoleTracer::new` and `PlainFormatter::new` are valid `Supplier`s for bean registration.
- `FlexibleClient` has two overloads annotated `required=false` and a default constructor. When both dependencies are present, the two-parameter constructor is chosen; with only Tracer, the one-parameter one; missing both, it falls back to no-arg.
- `SingleClient` has one unannotated constructor and a registered `Tracer`; Spring still injects it.
- `UnannotatedClient` has two unannotated constructors; with no-arg available, Spring picks no-arg rather than greedily picking Tracer.
- `RequiredClient` has one constructor annotated with default `required=true`. When Tracer is missing, Spring does not use no-arg as a fallback and fails; the demo catches `BeansException` to print the verification result.
- No randomness, system time, reflection output, iteration order, or identity hash logic is used in stdout.
- `try-with-resources` closes each context created by the application. In the deliberately failing refresh case, the framework may write warnings/exception details to **stderr/logs**; the example only specifies the exact **lines emitted by `main`'s `System.out.println`**.

### 8.4. Running with Maven

Inside the `autowired-constructor-selection` directory:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Exact 7 stdout lines printed by the application code (excluding tool/framework info):**

~~~text
flexibleBoth=tracer+formatter
flexibleTracerOnly=tracer
flexibleNone=default
singleNoAnnotation=tracer
multipleNoAnnotation=default
requiredPresent=required-tracer
requiredMissing=REJECTED
~~~

Output of `java -version`, `mvn -version`, and Spring logs may vary by machine; they are not the seven `System.out.println(...)` lines checked above.

### 8.5. Running with javac/java

Because the code imports Spring, the Spring API and transitive dependencies must be on the classpath. First use Maven to generate the file:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

Linux/macOS (bash/zsh):

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/ConstructorSelectionDemo.java
java -cp "out:$(cat classpath.txt)" demo.ConstructorSelectionDemo
~~~

Windows PowerShell:

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/ConstructorSelectionDemo.java
java -cp "out;$deps" demo.ConstructorSelectionDemo
~~~

On Unix, classpath entries are separated by `:`; Windows uses `;`. Both commands run the exact same `main` and test cases. If `javac` reports `package org.springframework... does not exist`, check dependencies/classpath before concluding the constructor resolution rules have a bug.

## 9. Interpreting Each Stdout Line

| Line | What It Proves |
| --- | --- |
| `flexibleBoth=tracer+formatter` | Both optional annotated candidates are resolvable; Spring uses the overload accepting two dependencies |
| `flexibleTracerOnly=tracer` | Two-parameter overload lacks Formatter; Spring picks the resolvable one-parameter overload |
| `flexibleNone=default` | No annotated overload is satisfied; Spring uses the default constructor |
| `singleNoAnnotation=tracer` | Only one constructor exists so `@Autowired` is not required |
| `multipleNoAnnotation=default` | Multiple unannotated overloads with no-arg: does not greedily pick the overload taking Tracer |
| `requiredPresent=required-tracer` | Required `@Autowired` designated the constructor and the dependency is present |
| `requiredMissing=REJECTED` | Required constructor lacks dependency; Spring does not silently fall back to no-arg |

**Do not infer from these results that Spring always prefers more parameters**. The experiment intentionally registered at most one bean per type, isolated contexts, and avoided unusual bean factory setups. Cases with tied constructor overloads, parameter names, qualifiers, primary beans, inheritance, or ambiguous argument types must be evaluated against the actual configuration.

## 10. Subtle Pitfalls Outside the Core Rules

### 10.1. `@Autowired` on a Constructor vs `@Bean` Factory Method

A JavaConfig snippet:

~~~java
@Bean
ReportService reportService(Tracer tracer) {
    return new ReportService(tracer);
}
~~~

This is an **illustrative snippet**, needing `ReportService`/`Tracer` and a corresponding config class. Spring resolves the **factory method parameter** `Tracer`; the `new ReportService(tracer)` call inside the method is a **direct Java call** to the written overload. When a BeanDefinition specifies a factory method, one cannot assume constructor selection rules apply to the resulting class the same way as when directly registering the class for Spring to instantiate.

This matters when debugging: sometimes developers look at annotations on `ReportService`'s constructor while the bean is actually created via a `@Bean` factory method directly calling a different constructor. Check the **actual registration path and factory**, not just the class.

### 10.2. `required=false` Is Not Null Injection

With two constructors `(Tracer)` and `(Tracer, Formatter)` having `@Autowired(required=false)`, when `Formatter` is missing Spring tries the matching constructor with **fewer parameters**. That differs from `new FlexibleClient(tracer, null)`. You should still validate constructor arguments per the class's own Java invariants.

If you do not want the service to run when `Formatter` is missing, marking it optional just to suppress errors is the wrong design decision; keep the dependency required and fail fast.

### 10.3. `@Autowired` on Constructor Parameters

Although the annotation includes `ElementType.PARAMETER`, Spring Core documentation notes that placing `@Autowired` solely on a **parameter** is not the standard mechanism for selecting a constructor. The clear way is placing `@Autowired` on the **constructor**, and placing `@Qualifier` or `@Value` on the **parameter** when needing to specify a bean/value.

This is an important distinction when a class has multiple overloads: do not put an annotation on one parameter and expect Spring to figure out which constructor is required.

### 10.4. `Optional`, `@Nullable`, and Provider Parameters

A single constructor sometimes has a genuinely optional dependency:

~~~java
public ReportService(
        Tracer tracer,
        java.util.Optional<MetricsClient> metrics) {
    this.tracer = java.util.Objects.requireNonNull(tracer);
    this.metrics = java.util.Objects.requireNonNull(metrics);
}
~~~

**Illustrative snippet**, not standalone source. `Optional<MetricsClient>` lets absence be expressed explicitly when Spring resolves that injection point; `@Nullable`/providers can also be used as needed. That does not mean every dependency should be optional — for required collaborators, explicit fail-fast constructor injection is easier to control.

When choosing between one constructor with `Optional<T>` and multiple `@Autowired(required=false)` constructors, prefer a simple API design that states valid states clearly and can be tested directly in plain Java.

### 10.5. Do Not Treat Every Error as a "Fallback"

If a dependency has two ambiguous candidates, the selected constructor itself can fail while resolving parameters. If a dependency bean is instantiated yet its constructor/initializer throws an exception, that is a genuine bean creation failure. Spring **does not guarantee** that "if the long overload errors, the short overload will definitely be used and the app stays valid". Classify errors via `Caused by`, candidate set, and considered constructors.

### 10.6. Versions and Constructor-Generating Tools

Lombok can generate additional constructors that pre-compile Java source does not show as you might expect; Java records have their own canonical constructor. When using Lombok, records, Kotlin, or code generation, inspect the **constructors actually present in bytecode** and their corresponding rules. The pure Java 17 example in this article avoids those factors to isolate Spring `@Autowired` observation.

## 11. Real-World Errors and Troubleshooting

| Symptom | Common Cause | How to Diagnose / Fix |
| --- | --- | --- |
| Spring uses no-arg even though an overload taking collaborators exists | Multiple constructors without `@Autowired`, default is available | Keep one constructor or annotate the intended constructor |
| `UnsatisfiedDependencyException` on startup | Required constructor needs an unregistered bean | Check type, candidates, registration, and qualifiers |
| `NoSuchBeanDefinitionException` in cause | No compatible bean exists | Add bean config or adjust dependency contract |
| `NoUniqueBeanDefinitionException` | Multiple beans of same type, cannot select candidate | `@Qualifier`/`@Primary` or fix configuration |
| `BeanCreationException` | Collaborator's factory/constructor/initializer threw an error | Read `Caused by`; fix logic/config values |
| Exception about multiple required constructors | Multiple constructors annotated with default `@Autowired` (true) | Only one required, or all optional candidates per design |
| Optional overload "skipped" | That constructor could not resolve all parameters | Verify each bean type; inspect which overload Spring picked |
| No default constructor and no annotation | Spring has no clear valid choice | Annotate a constructor or refactor to a single constructor |
| Adding no-arg breaks wiring | Class previously had one constructor, now has multiple overloads | Write startup tests, explicitly decide which constructor to use |
| Service gets an object yet lacks a collaborator | Fallback constructor permitted an invalid state | Do not provide an unsafe fallback; require necessary dependencies |
| Using `@Primary` to "pick a constructor" | Confusing bean candidate with overload choice | `@Primary` picks bean by type; constructors need appropriate `@Autowired` |
| Unit test calling `new` picks a different overload than Spring | Java caller explicitly chooses constructor, Spring picks via metadata | Maintain both unit tests and Spring wiring tests |
| `javac` reports missing Spring | Missing classpath/build dependencies | Check Maven pom and `-cp` |
| Error hidden when bean is `@Lazy` | Instantiation may be deferred | Test `getBean`/actual flow and creation timing |

### Ordered Debugging Checklist

1. **By which path is the bean actually created?** Class registration/component scanning or a `@Bean` method returning an already `new`'d object?
2. **How many constructors does the class have?** Are there default, synthetic/generated, or newly added overloads?
3. **Where are the annotations?** Which constructor has `@Autowired`, and is `required` true or false?
4. **What beans are in the container?** Does each parameter have a matching candidate? Does having more than one require a qualifier?
5. **Which candidate constructor was selected?** Rely on rules and startup logs/exception chains; do not just count parameters.
6. **Is the object in a valid state?** Did a fallback constructor omit a dependency that is actually needed?
7. **Are there regression tests?** A constructor signature change should not silently alter service wiring.
8. **Conclude and simplify:** if complex overloads exist solely to accommodate DI, consider one clear required constructor and use factories for other cases.

## 12. Testing the Rules with Minimal Assumptions

The demo checks via stdout, yet a serious project should have:

- **Java unit tests:** call each intended overload directly, checking `Objects.requireNonNull` and invariants; no Spring needed.
- **Spring context tests:** create a context registering only needed beans, fetch the service, verify which constructor path ran (e.g., a test-only enum/string property).
- **Negative tests:** when a required collaborator is missing, the context fails **without falling back to default**.
- **Ambiguity tests:** intentionally add two Tracer candidates to verify qualifier/primary, without concluding from verbatim exception messages.
- **Factory method tests:** verify whether a `@Bean` path calls a specific constructor itself or the container instantiates directly.
- **Regression tests when adding overloads:** a test checking only Java compilation is insufficient to catch altered wiring.

Do not rely on Java's default `assert` as a mandatory check unless `-ea` is enabled. Use test framework assertions or validate and throw exceptions. Also avoid locking tests to entire stack traces since messages, log order, and wrappers can vary across versions.

## 13. Exercises and Answers

**Exercise 1.** A class has only constructor `Service(Tracer tracer)` without `@Autowired`. Will Spring Framework 6 use that constructor?

**Answer:** Yes, if the class is registered as a Spring bean and a matching dependency resolves. A single constructor needs no annotation.

**Exercise 2.** There is a default constructor and a constructor `Service(Tracer)` with default `@Autowired`. The context has no Tracer. Does Spring use the default?

**Answer:** No, per required constructor rules. Spring does not skip a required annotated constructor just to use no-arg; bean creation fails.

**Exercise 3.** There are three constructors: default, `Service(Tracer)` `required=false`, and `Service(Tracer, Formatter)` `required=false`. The context only has Tracer. Which is chosen?

**Answer:** `Service(Tracer)` is chosen because it is resolvable, whereas the longer overload lacks Formatter.

**Exercise 4.** What if the context has both Tracer and Formatter?

**Answer:** The two-parameter overload in the example is chosen, because it is the annotated candidate satisfying the most dependencies.

**Exercise 5.** What if the context lacks both dependencies and has a default constructor?

**Answer:** When no `required=false` annotated candidates can be resolved, it falls back to the default constructor if present.

**Exercise 6.** Two unannotated constructors, one no-arg and one `Service(Tracer)`, context has Tracer. Does it always use the overload accepting Tracer?

**Answer:** No. Under standard constructor selection, the default is used; do not misapply the rule for multiple `required=false` annotated candidates.

**Exercise 7.** There are two Tracer beans and one constructor requiring Tracer. What does `@Primary` handle?

**Answer:** It selects the default **Tracer bean** for the injection point when appropriate, rather than directly choosing a constructor overload. `@Qualifier` can be used for greater clarity.

**Exercise 8.** Does `@Autowired(required=false)` on a constructor mean any parameter can be null?

**Answer:** No. With multiple annotated constructors, it allows the constructor to act as a conditional candidate, not a command to inject null into any parameter lacking a bean.

**Exercise 9.** A bean is created inside `@Bean service() { return new Service(...); }`. Who picks the overload?

**Answer:** The Java call `new Service(...)` inside the factory method explicitly selects the overload based on arguments; Spring does not necessarily auto-select a different constructor of the returned object per class registration rules.

## 14. Application Checklist

- [ ] Know that a single constructor can work without `@Autowired`.
- [ ] With multiple constructors, decide explicitly which one is used for the managed bean.
- [ ] Do not put `@Autowired(required=true)` on multiple constructors.
- [ ] If there are multiple `@Autowired(required=false)`, understand **greediest satisfiable candidate**.
- [ ] When optional candidates are missing, only use default fallback if the class state remains valid.
- [ ] Do not treat `required=false` as permission to inject null arbitrarily.
- [ ] Do not apply the greedy rule to multiple **unannotated** constructors.
- [ ] Distinguish constructor choice from bean candidate resolution/`@Qualifier`/`@Primary`.
- [ ] Know how to check the actual registration path: bean class vs `@Bean` factory method.
- [ ] Do not turn required business dependencies into optional ones just so startup succeeds.
- [ ] Have tests covering full dependencies, one missing dependency, all missing dependencies, and required failure.
- [ ] Check constructors produced by code generation/records/other frameworks when needed.
- [ ] Run Java 17+ with Maven or `javac`/`java` with the Spring classpath and verify the **7 stdout lines**.
- [ ] On error, read the bean name, constructor candidates, and `Caused by` before fixing.
- [ ] Prefer **one clear constructor** for mandatory dependencies in most business services.

**Conclusion:** `@Autowired` is not a signal for "Spring just picks the longest constructor". Spring **prioritizes a required constructor if designated**, **chooses the overload with the most satisfiable dependencies** among `required=false` candidates, **falls back** to default when no candidate fits and conditions allow, and **uses a single constructor** even without the annotation. Understanding the registration path and bean candidate resolution lets you design DI that is **predictable and fails fast in the right place**.

### Official Spring Documentation

- [Spring Framework 6.2 — @Autowired JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/annotation/Autowired.html)
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [AutowiredAnnotationBeanPostProcessor API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/annotation/AutowiredAnnotationBeanPostProcessor.html)
- [Spring Java Configuration / @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
