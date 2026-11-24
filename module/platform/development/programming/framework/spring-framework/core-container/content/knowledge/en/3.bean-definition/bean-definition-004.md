# Registering One Class as Multiple Independent Beans — Spring Framework Core Container

## 1. Objectives and Core Question

One **Java class is not equivalent to one Spring bean**. In the Spring Core Container, a bean is registered under an **identifying name** and associated with metadata specifying how it is created, its lifecycle scope, and its dependencies. Therefore, **the same Java class can be used to create multiple independent beans**, each with its own name, its own configuration, and — for two separately instantiated singletons — distinct objects.

For example, suppose an application wants to count requests for two channels, `alpha` and `beta`. Both counters use the `Counter` class, but the requirements are:

- The hit count state of channel alpha does not affect beta's state.
- Retrieving the `alphaCounter` bean again in the same context returns the same instance if it is a singleton.
- Retrieving the `betaCounter` bean is also its own singleton, not an alias of alpha.
- A service that needs a specific counter must **select the right bean**, rather than just saying "I need a `Counter`".

After this lesson, you will understand:

1. The difference between **class**, **bean definition**, **bean name**, **alias**, **bean instance**, and **scope**.
2. How to declare multiple `@Bean` methods returning the same class type.
3. When two beans of the same type are **two independent objects**, and when they are just **two names for one bean**.
4. Why `getBean(Counter.class)` or injecting a `Counter` can be ambiguous when multiple candidates share the same type.
5. How to select explicitly with `@Qualifier`, how to use `@Primary`, bean names, or purposeful collection injection.
6. How to register the same class as multiple definitions using `BeanDefinitionBuilder` and the effect of singleton/prototype.
7. Running a Java 17+ program with Spring Framework, Maven, `javac`/`java` commands, and verifiable stdout.

**Scope:** this lesson focuses on **multiple independent beans originating from the same class**. You do not need Spring Boot, Spring MVC, a database, or component scanning to demonstrate this mechanism.

## 2. Class and Bean Do Not Have a 1-to-1 Relationship

Three concepts:

| Concept | Represents | Meaning |
| --- | --- | --- |
| Java class | `Counter.class` | Defines the type and behavior of all `Counter` objects |
| Bean definition | Metadata named `alphaCounter` or `betaCounter` | Rules for creating/managing a bean inside the container |
| Bean instance | Object provided by a definition | Actual object used by the application |

For the configuration:

~~~java
@Bean("alphaCounter")
Counter alphaCounter() {
    return new Counter("alpha");
}

@Bean("betaCounter")
Counter betaCounter() {
    return new Counter("beta");
}
~~~

**This is a snippet inside a `@Configuration` class**, not a standalone Java file yet. Both factory methods return the **same `Counter` class**, yet Spring holds **two separate bean definitions** and the factory methods perform two distinct `new` calls.

~~~mermaid
flowchart TD
    C["Java class: Counter"] -.-> A["Bean definition: alphaCounter"]
    C -.-> B["Bean definition: betaCounter"]
    A --> IA["Instance A: Counter(alpha)"]
    B --> IB["Instance B: Counter(beta)"]
    IA -.->|same class| IB
~~~

The dashed arrows from class to definitions indicate **the same Java type**, not that the two beans depend on each other. Each definition can have:

- Its own name and aliases.
- Its own factory/constructor and constructor arguments.
- Its own scope/lazy flag/initialization/destruction metadata.
- Different qualifiers or priority.
- A separately created instance, if the factory/constructor actually supplies a separate object.

**Key takeaway:** `singleton` in Spring by default means **one container-managed object per bean definition within one container**, not one object for every bean of the same class, and not a JVM-wide singleton.

### Two Singletons of the Same Class Are Still Two Singletons

Suppose we call:

~~~java
Counter a1 = context.getBean("alphaCounter", Counter.class);
Counter a2 = context.getBean("alphaCounter", Counter.class);
Counter b1 = context.getBean("betaCounter", Counter.class);
~~~

If both definitions are singletons and each factory creates its own object, the result is:

- `a1 == a2` → `true`: two lookups of the **same bean name**.
- `a1 == b1` → `false`: two **different beans**, even though they have the same class.
- `a1.getClass() == b1.getClass()` → `true`: both objects belong to the **same Java class**.

Note: a bean definition with singleton scope does not force **two different definitions** to return different objects if a developer intentionally makes both factories return the same shared reference. The "independent beans" pattern requires that **both factories actually create separate objects**, not merely two names in code.

## 3. Independent Beans Differ from Aliases

Two variants that look similar but produce different results:

**Two independent definitions:**

~~~java
@Bean("alphaCounter")
Counter alphaCounter() {
    return new Counter("alpha");
}

@Bean("betaCounter")
Counter betaCounter() {
    return new Counter("beta");
}
~~~

Two definitions with different names. With the configuration above, each method instantiates a distinct instance.

**One bean with multiple names (alias):**

~~~java
@Bean(name = {"alphaCounter", "alphaAlias"})
Counter alphaCounter() {
    return new Counter("alpha");
}
~~~

In the second snippet, `alphaCounter` is the **primary name**, and `alphaAlias` is an **alias** for the same bean. Looking up by either name leads to the **same bean**, without creating a second singleton definition.

| Scenario | Application bean definitions | Singleton objects from factories (when created separately as coded) |
| --- | ---: | ---: |
| Two `@Bean` methods with different names and two `new Counter(...)` calls | 2 | 2 |
| One `@Bean(name={"alphaCounter","alphaAlias"})` | 1 | 1 |
| Two `@Bean` methods with different names **returning the same existing instance** | 2 | Possibly only 1 shared object |
| One `prototype` definition retrieved twice | 1 | Two objects, if each call creates a new one |

Do not use the total `context.getBeanDefinitionCount()` to count only the application's two counters: Spring may register additional infrastructure definitions. Query **specific bean names**, or retrieve bean names by type and filter/verify.

### Why Can't Two Methods with the Same Name Create Two Beans?

Java does not allow declaring two methods in the same class that differ only by return type. For multiple beans of the same type, give them **different method names/bean names**. The bean name does not need to match the class name.

If component scanning discovers a single `@Component` class, by default you get one definition for that class; wanting multiple definitions requires purposefully registering more, such as distinct `@Bean` methods or programmatic registration. Avoid unintentionally scanning a class while simultaneously registering that same class via `@Bean` if you do not want multiple candidates.

## 4. Using `@Bean` to Create Two Independent Beans

Main configuration:

~~~java
@Configuration(proxyBeanMethods = false)
public static class AppConfig {
    @Bean("alphaCounter")
    public Counter alphaCounter() {
        return new Counter("alpha");
    }

    @Bean("betaCounter")
    public Counter betaCounter() {
        return new Counter("beta");
    }

    @Bean
    public Dashboard dashboard(
            @Qualifier("betaCounter") Counter selected) {
        return new Dashboard(selected);
    }
}
~~~

This is an **excerpt from the runnable example in Section 6**, where `AppConfig` is a static nested configuration class inside a top-level class.

- Both of the first two methods **return `Counter`**, so Spring sees two candidates compatible with type `Counter`.
- The two beans are registered under separate names: `alphaCounter` and `betaCounter`.
- Spring invokes both factory methods when needed, each creating a `Counter` with its own label and state.
- `@Qualifier("betaCounter")` on the parameter of `dashboard(...)` requests the matching candidate with that qualifier/name, rather than any `Counter`.
- `Dashboard` simply receives `Counter` via its constructor; there is no need to call `context.getBean(...)` directly in business logic.

**Why is `proxyBeanMethods = false` valid?** The factory methods **do not directly call each other** to construct dependencies; instead, they use Spring-resolved parameters. If one method directly calls `alphaCounter()` in this mode, that is an ordinary Java method call and may create a new object **that is not the corresponding singleton bean**.

### Independence of State

Suppose:

~~~java
Counter alpha = context.getBean("alphaCounter", Counter.class);
Counter beta = context.getBean("betaCounter", Counter.class);

System.out.println(alpha.hit()); // alpha:1
System.out.println(beta.hit());  // beta:1
System.out.println(alpha.hit()); // alpha:2
~~~

Because `Counter` stores the call count in an **instance** field (not static), alpha has counted 2 while beta has only counted 1. This is stronger evidence than merely having two bean names: **the objects and their state are genuinely separate**.

In the full runnable code, we use `AtomicInteger` to increment the counter in a thread-safe way. That does not mean all logic and all singleton bean state are automatically thread-safe; the class itself must still be designed properly for concurrency requirements.

## 5. Resolving Ambiguity When Multiple Beans Share the Same Type

In a context with two `Counter` beans and no `@Primary`:

~~~java
Counter counter = context.getBean(Counter.class);
~~~

**This snippet illustrates a failure case.** A type-only lookup generally cannot choose a single bean and throws `NoUniqueBeanDefinitionException` when there are two unresolved candidates. In the full program, we catch that exact exception purely to print a deterministic diagnostic line.

### Three Primary Selection Approaches

1. **Specify the name at the injection point with `@Qualifier`**, e.g. `@Qualifier("betaCounter") Counter selected`. This is appropriate when the collaborator must belong to a specific channel.
2. **Place `@Primary` on one bean**, when most single-valued injection points should prefer this candidate and there is a sensible default.
3. **Look up the bean by explicit name at the composition root**, e.g. `context.getBean("alphaCounter", Counter.class)`. Do not turn business services into service locators calling the context everywhere.

An example of `@Primary` **merely illustrating an alternative configuration**:

~~~java
@Bean("alphaCounter")
@Primary
Counter alphaCounter() {
    return new Counter("alpha");
}
~~~

When a suitable primary candidate exists and no other constraint takes precedence, type-based injection can choose alpha by default. However, `@Primary` **does not merge beans**, and `@Qualifier("betaCounter")` can still select beta at a specific injection point.

**Do not say "whenever there are two beans of the same class, Spring will definitely fail".** Spring resolves dependencies using several rules: qualifiers, primary, parameter/field name matching, and other settings. The type-only `getBean(Counter.class)` example in this lesson's configuration **intentionally omits any selection rule**, which is why the ambiguity error occurs.

### If the Problem Genuinely Needs Both

You can inject:

~~~java
@Bean
public CounterReport counterReport(Map<String, Counter> counters) {
    return new CounterReport(counters);
}
~~~

The snippet above is **not standalone** because `CounterReport` is not declared. In Spring, an appropriate collection/map injection can receive multiple `Counter` beans, with the map key typically being the bean name. This is a good choice for a plugin/strategy registry, **and inappropriate if the service needs exactly one specific channel**.

Use `List<Counter>` or `ObjectProvider<Counter>` when the contract genuinely needs multiple candidates or dynamic retrieval; do not use them merely to dodge unclear configuration.

## 6. Complete Java 17+ Program and Output

Uses Spring Framework **6.2.19** and JDK 17+ via Maven. This is a pinned version for the example, not a claim of being the latest release. Spring Boot, a database, and a web server are unnecessary.

Project structure:

~~~text
multiple-beans-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MultipleBeansDemo.java
~~~

### 6.1. `pom.xml` File

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>multiple-beans-demo</artifactId>
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
                    <mainClass>demo.MultipleBeansDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven automatically resolves the transitive dependencies of `spring-context`. When running `javac` separately, you need the Spring JARs on the classpath; Java source files alone are not enough for the compiler to find Spring.

### 6.2. `src/main/java/demo/MultipleBeansDemo.java` File

~~~java
package demo;

import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class MultipleBeansDemo {
    private MultipleBeansDemo() {}

    public static final class Counter {
        private final String channel;
        private final AtomicInteger hits = new AtomicInteger();

        public Counter(String channel) {
            this.channel = channel;
        }

        public String hit() {
            return channel + ":" + hits.incrementAndGet();
        }

        public int count() {
            return hits.get();
        }
    }

    public static final class Dashboard {
        private final Counter selected;

        public Dashboard(Counter selected) {
            this.selected = selected;
        }

        public Counter counter() {
            return selected;
        }

        public String record() {
            return selected.hit();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("alphaCounter")
        public Counter alphaCounter() {
            return new Counter("alpha");
        }

        @Bean("betaCounter")
        public Counter betaCounter() {
            return new Counter("beta");
        }

        @Bean
        public Dashboard dashboard(
                @Qualifier("betaCounter") Counter selected) {
            return new Dashboard(selected);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            String[] counterNames =
                    context.getBeanNamesForType(Counter.class);
            Arrays.sort(counterNames);
            System.out.println("counterBeans=" +
                    String.join(",", counterNames));

            Counter alpha =
                    context.getBean("alphaCounter", Counter.class);
            Counter beta =
                    context.getBean("betaCounter", Counter.class);
            Dashboard dashboard = context.getBean(Dashboard.class);

            System.out.println("definitions=" +
                    (context.containsBeanDefinition("alphaCounter")
                     && context.containsBeanDefinition("betaCounter")));
            System.out.println("sameClass=" +
                    (alpha.getClass() == beta.getClass()));
            System.out.println("differentInstances=" + (alpha != beta));
            System.out.println("alphaSingleton=" +
                    (alpha == context.getBean("alphaCounter", Counter.class)));
            System.out.println("betaSingleton=" +
                    (beta == context.getBean("betaCounter", Counter.class)));

            System.out.println("alphaFirst=" + alpha.hit());
            System.out.println("betaFirst=" + beta.hit());
            System.out.println("alphaSecond=" + alpha.hit());
            System.out.println("alphaCount=" + alpha.count());
            System.out.println("betaCountBeforeDashboard=" + beta.count());

            System.out.println("dashboardUsesBeta=" +
                    (dashboard.counter() == beta));
            System.out.println("dashboardRecord=" + dashboard.record());
            System.out.println("betaCountAfterDashboard=" + beta.count());

            try {
                context.getBean(Counter.class);
                System.out.println("typeLookup=UNEXPECTED");
            } catch (NoUniqueBeanDefinitionException ex) {
                System.out.println("typeLookup=AMBIGUOUS");
            }
        }
    }
}
~~~

**Why the code runs standalone:**

- One `public top-level class` matching the filename `MultipleBeansDemo.java`.
- `Counter`, `Dashboard`, and `AppConfig` are static nested classes, so separate files are unnecessary.
- `@Configuration(proxyBeanMethods=false)` is valid because the two factory methods do not directly invoke each other; the `dashboard(...)` factory method receives its bean via `@Qualifier`.
- The `hits` state is an **instance field**, so each `new Counter(...)` creates its own `AtomicInteger`.
- `Arrays.sort(counterNames)` ensures the printed list of bean names has a deterministic order, independent of container iteration order.
- The context closes upon exiting `try-with-resources`, and the program attaches no destroy callback that prints extra lines, so the exact number of stdout lines from `main` is deterministic as shown below.

### 6.3. Compiling and Running with Maven

In the `multiple-beans-demo` directory:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Exact stdout printed by `main`, consisting of 15 lines:**

~~~text
counterBeans=alphaCounter,betaCounter
definitions=true
sameClass=true
differentInstances=true
alphaSingleton=true
betaSingleton=true
alphaFirst=alpha:1
betaFirst=beta:1
alphaSecond=alpha:2
alphaCount=2
betaCountBeforeDashboard=1
dashboardUsesBeta=true
dashboardRecord=beta:2
betaCountAfterDashboard=2
typeLookup=AMBIGUOUS
~~~

Version check commands and any Maven/Spring logs that appear **do not count** toward the 15 lines directly printed by `main`. Two independent counters from the same class make `alpha:2` clearly visible while `betaCountBeforeDashboard=1`.

### 6.4. Running Directly with `javac` / `java`

Because the Java source imports Spring, the corresponding JARs must be on the compile and runtime classpaths. Have Maven generate the list:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/MultipleBeansDemo.java
java -cp "out:$(cat classpath.txt)" demo.MultipleBeansDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/MultipleBeansDemo.java
java -cp "out;$deps" demo.MultipleBeansDemo
~~~

Unix uses `:` to separate classpath entries; Windows uses `;`. Both run the same `main` and print the 15 lines of output above. It is impossible to compile with `javac` without the dependencies the source imports.

## 7. Reading Stdout: What Has Been Proven

| Output | Exact Conclusion |
| --- | --- |
| `counterBeans=alphaCounter,betaCounter` | Two bean names of type `Counter` exist after sorting; not to be confused with total beans across the whole context |
| `definitions=true` | Both names `alphaCounter` and `betaCounter` are registered as bean definitions |
| `sameClass=true` | Both objects share the same Java class |
| `differentInstances=true` | The two beans return **two different references** |
| `alphaSingleton=true`, `betaSingleton=true` | Each singleton name resolves back to the same reference |
| `alphaFirst=alpha:1`, `betaFirst=beta:1` | Each bean has an independent starting counter state |
| `alphaSecond=alpha:2`, `alphaCount=2` | Only alpha incremented to 2 |
| `betaCountBeforeDashboard=1` | Beta remains at 1 before dashboard records |
| `dashboardUsesBeta=true` | `@Qualifier("betaCounter")` selected the beta bean specifically |
| `dashboardRecord=beta:2` | Dashboard increments beta's state, not alpha's |
| `betaCountAfterDashboard=2` | Beta now has count 2 |
| `typeLookup=AMBIGUOUS` | Lookup by `Counter` class alone cannot identify a single candidate in a configuration without `@Primary` |

One fact is not proven merely by two bean names: that the **objects are independent**. This example explicitly verifies it via `differentInstances=true` and separate counter states; that is the difference between "registering multiple names" and truly having "multiple independent beans".

## 8. Same Class with Multiple Bean Definitions via API

In addition to `@Bean`, you can **register two bean definitions** for the same `Counter.class` using `BeanDefinitionBuilder` or `RootBeanDefinition`. The following is an **illustrative snippet**, not a complete standalone file; it assumes `Counter` from Section 6 has a constructor accepting `String`:

~~~java
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

context.registerBeanDefinition("redCounter",
        BeanDefinitionBuilder.genericBeanDefinition(Counter.class)
                .addConstructorArgValue("red")
                .getBeanDefinition());

context.registerBeanDefinition("blueCounter",
        BeanDefinitionBuilder.genericBeanDefinition(Counter.class)
                .addConstructorArgValue("blue")
                .getBeanDefinition());

try (context) {
    context.refresh();
    Counter red = context.getBean("redCounter", Counter.class);
    Counter blue = context.getBean("blueCounter", Counter.class);
    System.out.println(red == blue); // false.
}
~~~

**Meaning:** the same `Counter.class`, yet two definitions registered under different names with different constructor arguments; under the default singleton scope, Spring creates one object per definition, each configured independently.

Registering definitions **before `refresh()`** is the cleanest timing. Registering additional definitions or mutating metadata once other singletons have already been created can produce complex behavior; do not treat it as a normal way to swap dependencies in a running application.

**Do not drop this snippet straight into the main demo configuration** and still expect the list to contain only two counters: once red/blue are added to the same context, the number of `Counter` candidates increases and lookup/type-selection conditions change accordingly.

## 9. Scope: Independence Between Definitions vs. Creating Fresh Instances per Lookup

### Default Singleton

The two definitions `alphaCounter` and `betaCounter` in the same context share the same class and the same default singleton scope. This means:

- Each definition can manage its own instance created by its own factory.
- Retrieving a bean by the **same name** multiple times returns the same instance.
- Having different **definition names** does not mean sharing one instance.
- Mutable state on each object must still be designed to be thread-safe if concurrent access occurs.

### Prototype

If you replace one definition with:

~~~java
@Bean("alphaCounter")
@Scope("prototype")
Counter alphaCounter() {
    return new Counter("alpha");
}
~~~

This is an **illustrative replacement snippet**, not to be added to the original config when verifying its stdout. When the context requests a prototype bean, Spring creates a new instance on demand; two calls to `getBean("alphaCounter")` can yield two different objects **even for the exact same definition name**. Thus:

| Configuration | Repeated comparison by same name | Comparison between two names |
| --- | --- | --- |
| Two separately created singletons | Same reference | Different references |
| One prototype bean | Each lookup creates a new object | Not a primary criterion for inferring definition count |
| One singleton bean with alias | Same reference under primary name/alias | Both names still refer to the same bean |
| Two definitions returning the same object from a shared factory | Same reference per definition | May share the same reference despite different definitions |

The Spring container does not fully manage destruction of prototypes after handing over the object; if the object holds resources needing cleanup, the owner must implement an appropriate handling strategy.

### Scope Is Not Tied to Class Count

One class can be used across multiple bean definitions with different scopes. You can have one singleton `Counter` bean and one prototype `Counter` bean; **sharing a class** does not dictate each definition's scope.

Conversely, a single bean definition does not necessarily create "one instance per class"; the container applies the configured scope. Always ask: **which definition, which name, which scope, which factory?**

## 10. Registering Multiple Beans of the Same Type and API Design

When it makes sense:

- Two datasource clients of the same class pointing to two different databases.
- Two HTTP API clients of the same class with different configured URLs/credentials.
- Two notification-sending strategies of the same class with separate channel/tenant settings.
- Two worker executors of the same class handling different types of work.
- Two caches of the same implementation with separate namespaces/stored data.

These examples are illustrative patterns; transactions, pooling, lifecycle, and security must be evaluated per real environment. A shared class can represent a **common contract and behavior**, while each bean carries **distinct configuration and state**.

### Give Beans Meaningful Names

Names like `alphaCounter` and `betaCounter` are clearer than `counter1` and `counter2` when they represent specific channels. If multiple parties configure beans in an application, use explicit `@Qualifier` or appropriate custom qualifiers instead of relying accidentally on Java parameter names.

### When You Should Not Create Extra Beans

Do not create multiple beans just because you can: if two consumers genuinely share a **stateless, thread-safe collaborator with identical configuration**, sharing one singleton can be simpler and use fewer resources. Conversely, if the collaborator holds state for two separate channels, splitting beans explicitly provides isolation, though **concurrency, lifecycle, and resource usage** must still be considered.

## 11. Common Errors and How to Handle Them

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| `getBean(Counter.class)` fails | Two candidates of the same type with no unique selection | Use bean name or `@Qualifier`/`@Primary` per design |
| Injecting a `Counter` receives the wrong channel | Relied on unintended name/primary rules | Specify an explicit qualifier and test wiring |
| Mistaking two aliases for two independent beans | Aliases point to the same bean definition | Register two separate definitions |
| Assuming two definitions always produce different objects | Two factory methods might return the same shared object | Create separate objects and verify identity in tests |
| `@Bean` methods calling each other directly with `proxyBeanMethods=false` | Plain Java call can create an object outside the singleton bean | Declare dependencies via factory method parameters |
| Two beans of the same class sharing a `static` variable | Static state belongs to the class, not each instance | Move isolated state into instance fields |
| Mutable singleton unsafe under multithreading | Multiple callers share one bean | Use thread-safe structures/synchronization or redesign state |
| Prototype injected into singleton expected to refresh per call | Dependencies are resolved when the singleton is created | Use `ObjectProvider<T>` or per-call lookup when truly needed |
| Multiple beans registered because `@Component` and `@Bean` coexist | Unintentional duplicate registration | Audit registration sources and keep only the desired candidate |
| `NoSuchBeanDefinitionException` | Wrong bean name or not registered | Check `@Bean`, configuration loading, and package scan |
| `NoUniqueBeanDefinitionException` | Multiple candidates and no disambiguation mechanism | Check qualifiers/primary/type; inspect injection point |
| Context has fewer/more definitions than expected | Counting all infrastructure beans instead of app beans | Filter by expected type/names |
| Java source compilation fails with missing Spring packages | Missing Maven deps or `javac -cp` | Fix build/classpath before diagnosing IoC |
| Flaky tests when using stateful singletons | Tests share a context or mutable bean | Reset data/use proper test isolation and avoid uncontrolled state |

**Read errors at the right level:** `NoUniqueBeanDefinitionException` is a **candidate-selection resolution error**, not an error saying two objects of the same class are illegal in Java. Bean names/qualifiers are the tools for designing explicit selection decisions.

## 12. Self-Check Exercises and Answers

**Exercise 1.** Both `@Bean("one") Counter one()` and `@Bean("two") Counter two()` return `new Counter(...)`. Can the same class have two independent singleton beans?

**Answer:** Yes. Two separate names/definitions and two objects created separately by their factories. Each singleton name stores its own instance.

**Exercise 2.** How many independent beans does `@Bean(name={"one","alias"})` create?

**Answer:** One bean with an additional alias; looking up either name points to the same object for a singleton. It does not create two independent definitions.

**Exercise 3.** `getBean(Counter.class)` encounters two candidates, neither with `@Primary` nor any other selection metadata. Does it automatically pick one at random?

**Answer:** No. A type-only lookup in that case reports no unique selection, such as `NoUniqueBeanDefinitionException`. Specify a name/qualifier or a primary according to your design.

**Exercise 4.** Dashboard needs the beta bean, yet the class field only has type `Counter`. How do you solve this?

**Answer:** Inject `@Qualifier("betaCounter") Counter selected` in the corresponding constructor/factory parameter, or design a custom qualifier. Domain code does not need to query the context by string.

**Exercise 5.** Two beans of the same class have a `static int counter` field. Do the two beans keep independent counts?

**Answer:** Not with that static field; static belongs to the class and is shared. For separate state, use instance fields (in the demo, `AtomicInteger hits`).

**Exercise 6.** Change alpha to `prototype` and call `getBean("alphaCounter")` twice. Do both hold the same reference?

**Answer:** Under normal prototype scope, Spring creates a new instance on each request. Expect identity to differ, no longer matching the singleton condition in the original stdout.

**Exercise 7.** Two beans use the same shared singleton object returned from two factory methods. Since the names and definitions differ, are the references guaranteed to differ?

**Answer:** Not necessarily. Independent names/definitions do not by themselves prove object identity; if the factories return the same reference, both lookups can point to the same object. This is precisely why verifying `alpha != beta` is meaningful.

## 13. Application Checklist

- [ ] Distinguish class, bean definition, bean name, alias, and bean instance.
- [ ] Two beans of the same class require two actual definitions, not merely added aliases.
- [ ] Factory methods create/supply separate instances and separate configuration.
- [ ] Each bean has a name reflecting its role/channel, without meaningless numbering.
- [ ] Understand singleton per bean definition within the same container.
- [ ] Know that prototype creates an instance per bean request under the appropriate scope.
- [ ] When multiple candidates share a type, use qualifiers/primary or names purposefully.
- [ ] Do not rely on Spring "picking randomly" when ambiguous.
- [ ] If all candidates are needed, consider collection/map injection with a clear contract.
- [ ] Do not invoke `@Bean` methods directly under `proxyBeanMethods=false` as a way to obtain singletons.
- [ ] Do not store per-channel state in static fields.
- [ ] Verify object identity and separate state in tests, not just bean name counts.
- [ ] Run Java 17+ with Maven or `javac`/`java` with Spring on the classpath, matching the exact **15 lines of stdout**.
- [ ] Do not overuse multiple beans when a single stateless singleton can be shared safely.

**Conclusion:** **One Java class can back multiple Spring beans.** What makes each bean independent is a **separately registered bean definition/name together with how its factory/scope provides its own instance and state**. A bean alias is only an extra name; type-based dependencies can become ambiguous, so design injection points explicitly using `@Qualifier`/`@Primary` or names when needed.

### Official Documentation

- [Spring Bean Overview and Names](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
- [Spring JavaConfig — @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring Autowiring Collaborators and Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
