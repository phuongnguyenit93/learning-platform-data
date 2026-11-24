# Filtering Candidate Sets with `@Qualifier` in Spring Core Container

## 1. Essence: Selecting from the Set of Type-Matching Beans

When Spring needs to supply a dependency to a constructor, field, method, or `@Bean` factory method, the container first evaluates **which beans match the type** of the injection point. If multiple candidates share the same interface, Spring's `@Qualifier` lets you **narrow the candidate set** by an appropriate trait, label, or name.

~~~text
                  Bean definitions
        fastA: Channel + qualifier "fast"
        fastB: Channel + qualifier "fast"
        slowC: Channel + qualifier "slow"
        formatter: Formatter + qualifier "fast"
                           |
                require type Channel
                           |
                {fastA, fastB, slowC}
                           |
                @Qualifier("fast")
                           |
                    {fastA, fastB}
                      /        \
                List<Channel>  Channel
                  2 elements   2 candidates:
                               can be ambiguous
~~~

The most important point of this lesson: **`@Qualifier` is a filter over type-compatible beans, not implicitly a unique key referencing a single bean ID**. Two beans with the same `"fast"` qualifier are both eligible when injecting a `List<Channel>`. Conversely, an injection point requesting **a single `Channel`** remains ambiguous if two candidates remain after filtering with no additional selection rule. These are the exact semantics stated directly in the Spring reference documentation.

Therefore, for `@Autowired` or injection into a `@Bean` parameter, think in three steps:

1. Determine the **required type** at the injection point, accounting for generic types and assignability.
2. Apply constraints/metadata such as `@Qualifier` to **filter which beans are allowed as candidates**.
3. If a single object is requested, the container must pick **one** final candidate; if a collection is requested, the container can supply **all** remaining candidates under the applicable rules.

**Learning goals:** apply qualifiers directly on parameters, annotate candidates, filter `List`/`Set`, distinguish from `@Primary` and by-name lookup, build custom qualifiers, inspect missing/ambiguous errors, and run a Java 17 Maven example.

## 2. Minimal Syntax of Spring `@Qualifier`

The annotation used here is:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
~~~

Do not confuse it with `jakarta.inject.Qualifier`: the latter is a **meta-annotation** for defining custom qualifiers and does not take a String argument directly with the same syntax.

### On a Bean Definition: Describing a Candidate

With Java configuration:

~~~java
@Bean
@Qualifier("fast")
DeliveryPort fastGateway() {
    return new FastGateway();
}
~~~

This is an **illustrative snippet**; `DeliveryPort` and `FastGateway` must be defined if compiling standalone. It declares a bean with default name `fastGateway`, type `DeliveryPort`, and qualifier metadata `"fast"`.

The same annotation can also be placed on a Spring component class:

~~~java
@Component
@Qualifier("fast")
final class FastGateway implements DeliveryPort {
    // Needs interface implementation in a real project.
}
~~~

This is an **illustrative alternative configuration**, not a class added to the main program. It is registered only when Spring scans the appropriate package or the bean is registered through a supported mechanism.

### On an Injection Point: Accepting Only the Filtered Group

~~~java
@Autowired
public Sender(@Qualifier("fast") DeliveryPort gateway) {
    this.gateway = gateway;
}
~~~

This is an illustrative constructor injection snippet. Spring finds beans compatible with type `DeliveryPort` **and** qualifier `"fast"`, then needs a final selection for the single parameter `gateway`. If multiple `"fast"` beans of the same type remain, adding this qualifier alone does not guarantee a unique result.

If a managed bean class has only a single constructor, Spring Framework 4.3+ usually does not require `@Autowired` on that constructor. However, **`@Qualifier` on the parameter still takes effect**:

~~~java
public Sender(@Qualifier("fast") DeliveryPort gateway) {
    this.gateway = gateway;
}
~~~

Again, the code above only applies when `Sender` and its collaborator are properly registered.

### Applying Per Parameter

~~~java
@Autowired
public void configure(
        @Qualifier("fast") DeliveryPort foreground,
        @Qualifier("slow") DeliveryPort background) {
    this.foreground = foreground;
    this.background = background;
}
~~~

Each parameter is resolved independently. The annotation on `foreground` does not affect `background`. The method can be named `configure`; it does not have to be `set...`. The requirement is that the bean is actually Spring-managed and types/qualifiers match without ambiguity. This snippet is not standalone because fields/interfaces are not defined.

## 3. Qualifier Is a Filter, **Not Required to Be Unique**

Suppose three beans share the `DeliveryPort` type:

| Bean name | Type | Declared qualifier |
| --- | --- | --- |
| `fastA` | `DeliveryPort` | `fast` |
| `fastB` | `DeliveryPort` | `fast` |
| `slowC` | `DeliveryPort` | `slow` |

Requests:

| Injection point | Candidates after filtering | Typical outcome |
| --- | --- | --- |
| Unqualified `DeliveryPort` | `fastA, fastB, slowC` | Ambiguous without an additional selection rule |
| `@Qualifier("fast") DeliveryPort` | `fastA, fastB` | Can still be ambiguous |
| `@Qualifier("slow") DeliveryPort` | `slowC` | Selects `slowC` |
| `@Qualifier("fast") List<DeliveryPort>` | `fastA, fastB` | Injects both |
| `@Qualifier("slow") Set<DeliveryPort>` | `slowC` | Injects a set with one bean |
| `@Qualifier("missing") DeliveryPort` | No matching bean | Required injection typically fails |

The table above assumes the beans carry no extra selection metadata such as `@Primary`, special parameter-name meaning, or other conditions; it illustrates the core rule of **narrowing by type and qualifier**.

### Why Does List Still Receive Two Beans?

Because `@Qualifier("fast")` carries no clause saying “at most one bean may carry the fast label”. It means “consider only beans carrying the fast trait”. When the injection target is `List<DeliveryPort>` or `Set<DeliveryPort>`, Spring can provide all beans matching both the type and the qualifier. This is completely natural when you want multiple handlers, rule engines, notifiers, or adapters belonging to the same group.

### A Bean ID Is Not the Definition of a Qualifier

Spring allows a **bean name to act as a fallback qualifier value** within the set of beans already matching the type. As a result, in many cases you can write:

~~~java
@Autowired
public Sender(@Qualifier("fastA") DeliveryPort gateway) {
    this.gateway = gateway;
}
~~~

even when bean `fastA` was not explicitly annotated with `@Qualifier("fastA")`, because Spring can inspect the bean name `fastA`. Still, this remains **type-driven autowiring**; a bean of the wrong type does not become a `DeliveryPort` merely because its name matches.

**Recommendation:** a qualifier label describing a stable trait like `"fast"`, `"eu"`, or `"persistent"` is usually more resilient than a bean name string like `"fastGatewayV2"`. If the real goal is a **unique reference by name**, `jakarta.annotation.Resource(name="...")` from Jakarta Annotations/JSR-250 has by-name lookup semantics distinct from `@Autowired` + qualifier, requiring the corresponding classpath/annotation support.

## 4. Runnable Spring Framework 6.2 / Java 17 Example

This console program has **two beans with qualifier `fast`** and one bean with qualifier `slow`. Spring injects the entire fast group into a `List<DeliveryPort>` while injecting the single slow bean into a single dependency.

### 4.1. Project Structure

Requires JDK 17+ and Maven:

~~~text
qualifier-filter-demo/
├── pom.xml
└── src/main/java/demo/QualifierFilterDemo.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>qualifier-filter-demo</artifactId>
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
                    <mainClass>demo.QualifierFilterDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. Complete Source Code

Create `src/main/java/demo/QualifierFilterDemo.java`:

~~~java
package demo;

import java.util.List;
import java.util.Objects;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;

public final class QualifierFilterDemo {
    private QualifierFilterDemo() {}

    public interface DeliveryPort {
        String code();
        String send(String text);
    }

    public record DemoDelivery(String code) implements DeliveryPort {
        @Override
        public String send(String text) {
            return code + ":" + text;
        }
    }

    public static final class Router {
        private final List<DeliveryPort> fast;
        private final DeliveryPort slow;

        public Router(List<DeliveryPort> fast, DeliveryPort slow) {
            this.fast = List.copyOf(Objects.requireNonNull(fast));
            this.slow = Objects.requireNonNull(slow);
        }

        public String fastNames() {
            return fast.stream()
                    .map(DeliveryPort::code)
                    .sorted()
                    .toList()
                    .toString();
        }

        public int fastCount() {
            return fast.size();
        }

        public String slowName() {
            return slow.code();
        }

        public String deliverSlow(String text) {
            return slow.send(text);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        @Qualifier("fast")
        public DeliveryPort fastA() {
            return new DemoDelivery("fast-a");
        }

        @Bean
        @Qualifier("fast")
        public DeliveryPort fastB() {
            return new DemoDelivery("fast-b");
        }

        @Bean
        @Qualifier("slow")
        public DeliveryPort slowC() {
            return new DemoDelivery("slow-c");
        }

        @Bean
        public Router router(
                @Qualifier("fast") List<DeliveryPort> fast,
                @Qualifier("slow") DeliveryPort slow) {
            return new Router(fast, slow);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            Router router = context.getBean(Router.class);

            System.out.println("TYPE_COUNT "
                    + context.getBeanNamesForType(DeliveryPort.class).length);
            System.out.println("FAST_NAMES " + router.fastNames());
            System.out.println("FAST_COUNT " + router.fastCount());
            System.out.println("SLOW_NAME " + router.slowName());
            System.out.println("SLOW_RESULT "
                    + router.deliverSlow("PING"));
            System.out.println("SAME_ROUTER "
                    + (router == context.getBean(Router.class)));
        }
    }
}
~~~

Key point: `@Qualifier("fast")` on **two `@Bean` methods** attaches metadata for two beans in the same group. `@Qualifier("fast")` on the `List<DeliveryPort>` parameter of the `router` factory method filters down to exactly those two beans. `Router` is a plain Java class with no Spring imports, while the wiring decisions live in the configuration.

### 4.3. Run Commands

From the `qualifier-filter-demo` directory:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

In this example, `maven.compiler.release=17` targets Java release 17 compilation. Running `javac/java` directly requires the full classpath with Spring and its dependencies; Maven handles the classpath and runs main.

**Stdout from `System.out.println` in exact order:**

~~~text
TYPE_COUNT 3
FAST_NAMES [fast-a, fast-b]
FAST_COUNT 2
SLOW_NAME slow-c
SLOW_RESULT slow-c:PING
SAME_ROUTER true
~~~

`mvn -version` also prints Maven/JDK versions; Maven may emit logs and download dependencies. The block above **describes only the output intentionally printed by the application**, without claiming no other terminal logs exist.

### 4.4. Explaining the Results

1. When `AnnotationConfigApplicationContext(AppConfig.class)` refreshes, Spring registers three `DeliveryPort` beans—`fastA`, `fastB`, `slowC`—along with the `Router` bean.
2. `getBeanNamesForType(DeliveryPort.class)` has length 3. This counts **by type**, before any qualifier is applied.
3. The `router(...)` factory method takes `List<DeliveryPort> fast` with qualifier `"fast"`. Spring supplies both `fastA` and `fastB`; hence `FAST_COUNT 2`.
4. `Router.fastNames()` sorts the codes before printing so stdout does not depend on container iteration order within the group: `[fast-a, fast-b]`.
5. The single parameter `@Qualifier("slow") DeliveryPort slow` leaves only `slowC` after filtering, so `SLOW_NAME slow-c`.
6. `deliverSlow("PING")` uses the received reference to return `slow-c:PING`, without asking the container to pick a candidate again on each call.
7. `Router` is a singleton by default within a context; looking it up twice returns the same object, so `SAME_ROUTER true`.

The output avoids `println` inside factory methods or constructors, avoiding irrelevant singleton creation-order dependencies. `List.copyOf` protects the list field from external mutation, though it does not itself make each `DeliveryPort` immutable or thread-safe.

## 5. Plain Java 17 Example: Filtering and Injection Are Separate Steps

To see the filtering idea clearly, try an example **without Spring**. This is **not** Spring qualifier resolution; the Java code explicitly filters by tag to model the selection idea.

Create `CandidateFilter.java`:

~~~java
import java.util.List;

public final class CandidateFilter {
    public record Candidate(String beanName, String type, String tag) {}

    public static void main(String[] args) {
        List<Candidate> beans = List.of(
            new Candidate("fastA", "Channel", "fast"),
            new Candidate("fastB", "Channel", "fast"),
            new Candidate("slowC", "Channel", "slow"),
            new Candidate("formatA", "Formatter", "fast")
        );

        List<String> matches = beans.stream()
            .filter(b -> b.type().equals("Channel"))
            .filter(b -> b.tag().equals("fast"))
            .map(Candidate::beanName)
            .sorted()
            .toList();

        System.out.println("MATCHES " + matches);
        System.out.println("COUNT " + matches.size());
        System.out.println("UNIQUE " + (matches.size() == 1));
    }
}
~~~

Inside the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 CandidateFilter.java
java CandidateFilter
~~~

**Exact stdout:**

~~~text
MATCHES [fastA, fastB]
COUNT 2
UNIQUE false
~~~

The two filter steps model that `formatA` shares the `fast` label yet has a **different type** and is excluded, while both `Channel` items carrying `fast` remain after filtering. In real Spring, types also involve inheritance, generic metadata, qualifiers, and many other candidate resolution rules; this code simply reinforces **type first, qualifier narrowing**.

## 6. How Do `@Primary` and `@Qualifier` Work Together?

`@Primary` is a precedence rule when Spring must pick **one bean** among multiple candidates. `@Qualifier` restricts which beans are considered. Do not treat `@Primary` as a mechanism that bypasses all qualifiers.

Hypothetical example:

- `fastA` and `fastB` carry qualifier `fast`.
- `slowC` carries qualifier `slow` and is marked `@Primary`.

If an injection point requests `@Qualifier("fast") DeliveryPort`, Spring **does not pick `slowC` merely because `slowC` is primary**, because `slowC` fails the requested qualifier.

On the other hand, if `fastA` is marked as the sole primary in the `fast` group, Spring can select `fastA` for a single dependency qualified with `fast` (when no other constraint interferes). Yet for `@Qualifier("fast") List<DeliveryPort>`, **both `fastA` and `fastB` remain eligible to appear in the collection**; primary does not automatically turn a filter into a single-element selector.

~~~java
// Illustrative variant; do not add simultaneously to the runnable file:
// @Bean
// @Primary
// @Qualifier("fast")
// DeliveryPort fastA() { return new DemoDelivery("fast-a"); }
~~~

Import `org.springframework.context.annotation.Primary` if applying this for real. Do not use `@Primary` to handle routing logic that picks an adapter **based on per-transaction runtime data**; that is business strategy/router design, not bean candidate resolution.

### When the Entire Group Has No Candidates

`@Qualifier("missing") DeliveryPort` does not invent a bean. For a standard required injection point, Spring reports a missing matching bean. For a required `List<DeliveryPort>` on a field/method, lacking matching elements can also cause an error; in some constructor/factory-method injection paths, Spring has special rules for multi-element arguments. Therefore, if a group can legitimately be empty, design and test against your actual Spring version and signature rather than assuming Spring always injects an empty list.

## 7. Filtering `List`, `Set`, `Map`, and Arrays

Spring supports type-based injection for typed collections and arrays. Qualifiers can restrict which beans enter the group.

~~~java
@Autowired
public void configure(
        @Qualifier("fast") List<DeliveryPort> fastPorts,
        @Qualifier("slow") DeliveryPort slowPort) {
    this.fastPorts = fastPorts;
    this.slowPort = slowPort;
}
~~~

This is an illustrative non-standalone snippet; fields and interfaces must be defined. Similar forms include:

- `Set<DeliveryPort>`: set of matching beans, without relying on incidental iteration order when used.
- `DeliveryPort[]`: array of matching candidates.
- `Map<String, DeliveryPort>`: keys are typically bean names, values are matching bean instances; qualifiers can also narrow candidates under the corresponding resolution rules.
- `List<DeliveryPort>`: can preserve order via `@Order`/`Ordered` for group injection if an ordering rule is declared. Do not rely on incidental component-scan order as business logic.

A qualifier **can match multiple beans**, making it a natural fit for handler chains, batch processors, multi-channel notifications, or strategies sharing a role.

### Distinguishing Group Filtering from Runtime Strategy

Injecting a list of “all fast channels” is **component wiring** at the time Spring assembles the bean graph. If a use case needs to choose “fast or slow” based on user input per invocation, that logic belongs to a runtime service/router. `@Qualifier` does not inspect request payloads to switch beans dynamically.

## 8. Custom Qualifiers with Domain Meaning

A string like `@Qualifier("fast")` is easy to start with, yet strings scattered in many places can be hard to rename. When a label represents an important convention, you can create a dedicated annotation.

Example `Fast.java` file:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.beans.factory.annotation.Qualifier;

@Target({ElementType.TYPE, ElementType.METHOD,
         ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface Fast {}
~~~

This is an **illustrative annotation file**, not added to the runnable project in section 4. You can place `@Fast` on candidate beans/classes and on injection points. Spring treats that annotation as qualifier metadata, not as a method to invoke automatically.

You can also define an annotation with attributes, such as `@Region("EMEA")`:

~~~java
@Target({ElementType.TYPE, ElementType.METHOD,
         ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface Region {
    String value();
}
~~~

This is an illustration requiring the same imports as `Fast.java`. When `@Region("EMEA")` and `@Region("APAC")` are placed on appropriate beans, an injection point annotated with `@Region("EMEA")` filters by that specific value.

**Note:** do not confuse Spring's meta-`@Qualifier` with `jakarta.inject.Qualifier`; both can participate in custom qualifiers in certain setups, but you must be aware of the package and framework mechanics. This lesson focuses on **Spring `@Qualifier`**.

### Using XML Bean Definitions

With XML, qualifier metadata can be attached directly:

~~~xml
<bean id="fastGateway" class="demo.FastGateway">
    <qualifier value="fast"/>
</bean>
~~~

This is an **illustrative XML snippet**, not standalone runnable; it requires the class and a valid XML root/schema. Spring evaluates qualifier metadata when resolving annotation-driven dependencies. Do not confuse XML `<qualifier>` with a Java `setQualifier` method on a bean; it is bean definition metadata.

## 9. Name-Based Injection and Differences from `@Resource`

Spring provides fallback matching by bean name or alias during type-driven resolution when no stronger guidance such as qualifier, primary, or fallback is present. On Spring 6.1+, matching based on **Java parameter names** requires parameter name info to be retained at compile time, typically via `-parameters`; Spring 6.2 also optimizes shortcuts for name matching in certain cases.

Consequently, code like:

~~~java
public Sender(DeliveryPort fastA) {
    this.gateway = fastA;
}
~~~

can pick the bean named `fastA` when multiple compatible `DeliveryPort` beans exist and no other precedence metadata applies, **provided** parameter name metadata was retained and resolution rules are satisfied. Do not rely on this when actual business requirements demand a specific role: `@Qualifier("fast")` or a custom qualifier is clearer and less tied to Java variable names.

`@Resource(name="fastA")` comes from Jakarta Annotations (JSR-250, package `jakarta.annotation`), is a name-oriented lookup mechanism, and follows its own rules. It fits better when the explicit goal is fetching an object by name, yet `@Resource` does not have the same applicability as `@Autowired` on constructors or multi-parameter methods; distinguish the two.

## 10. Common Pitfalls

| Misconception / Error | Explanation / Fix |
| --- | --- |
| “`@Qualifier("fast")` always picks exactly one bean.” | It filters beans by type; two `fast` beans may still remain. |
| “A qualifier is an absolute ID, regardless of type.” | Type-driven selection still applies; a qualifier does not make a wrong-typed bean valid. |
| “A qualifier may be used on at most one bean.” | Multiple beans can share a qualifier, especially for collection injection. |
| “Putting `@Qualifier` on a parameter is enough even if the bean isn't registered.” | The bean must exist and carry matching type/metadata. |
| “`@Primary` always beats every qualifier.” | Primary cannot select a bean that fails the qualifier. |
| “`@Primary` on one `fast` bean reduces the `fast` List to only that bean.” | Collections can receive all candidates satisfying the qualifier. |
| “Putting `@Qualifier` on a business method makes it run automatically.” | The annotation applies to bean definitions/injection points, not invoking business logic. |
| “`@Qualifier` and `jakarta.inject.Qualifier` are the same.” | Spring's annotation takes a String; Jakarta's annotation is typically a meta-annotation. |
| “Parameter name matching a bean name always suffices for autowiring.” | It depends on metadata and requires `-parameters` on Spring 6.1+ for parameter name matching. |
| “With no `fast` beans, list injection always gets `[]` without error.” | Depends on injection path and required semantics; test the exact signature. |
| “Injecting all beans executes all of them on every request.” | Injection is wiring; invoking business methods requires explicit code. |
| “Qualifiers handle transactions, HTTP routing, or concurrency.” | They only affect candidate selection, without adding other infrastructure. |
| “Bean name fallback turns `@Autowired` into `@Resource`.” | Semantics differ; `@Autowired` still filters by type first. |
| “Package scan order decides which implementation gets chosen.” | Never rely on scan order; use explicit rules. |

### Diagnosing When the Context Fails to Start

- `NoSuchBeanDefinitionException` or `UnsatisfiedDependencyException`: possible missing type/qualifier match. Inspect bean definitions, component scanning, and `@Bean` names.
- `NoUniqueBeanDefinitionException`: multiple candidates remain after filtering for a **single-valued injection point**; needs a more specific qualifier, an appropriate primary, or a different injection design.
- `BeanCreationException`: a matching bean candidate failed during construction, factory invocation, or initialization; `@Qualifier` does not swallow errors.
- Wrong `Qualifier` import: verify package `org.springframework.beans.factory.annotation.Qualifier`; do not copy String syntax to `jakarta.inject.Qualifier`.
- Entire group missing after configuring `@Qualifier("fast") List<Port>`: check that the beans actually carry `fast` metadata, names/aliases, and the proper injection mechanism.

**Effective debugging approach:** first list all candidates sharing the interface; next inspect each candidate's qualifier metadata and the injection point; finally check whether the target needs one bean or a group. Do not fix ambiguity by marking every implementation as primary.

## 11. Exercises with Answers

**1.** Spring has two `DeliveryPort` beans carrying the `fast` qualifier. Does injecting `@Qualifier("fast") DeliveryPort` guarantee picking one?

**Answer:** No. If two candidates remain after filtering with no further selection rule, single-valued injection can be ambiguous.

**2.** With the same configuration, what does injecting `@Qualifier("fast") List<DeliveryPort>` receive?

**Answer:** Both `fast` beans, provided they match the type and metadata.

**3.** Does a `Formatter` bean carrying the `fast` qualifier enter a `List<DeliveryPort>` qualified with `fast`?

**Answer:** No, if `Formatter` is not a `DeliveryPort`. Qualifiers filter **after type matching**, without changing types.

**4.** If `slowC` is `@Primary` yet the injection point requests qualifier `fast`, is `slowC` selected?

**Answer:** Not merely because it is primary; it does not satisfy the `fast` qualifier.

**5.** If `@Primary` is placed on `fastA` while keeping both `fast` beans, does a `fast`-qualified `List<DeliveryPort>` still contain `fastB`?

**Answer:** Yes, primary prioritizes a candidate for single-valued injection without removing other beans from the group.

**6.** Can `@Qualifier("fastA")` match a bean named `fastA` that does not have an explicit qualifier of the same name?

**Answer:** In Spring, bean name fallback applies within the set of type-compatible beans; however, that is still type-narrowed matching, not an absolute bean ID lookup.

**7.** Why does the runnable example sort names before printing?

**Answer:** So output does not depend on the order Spring returns candidates; sorting guarantees `[fast-a, fast-b]`.

**8.** In the example, why is `FAST_COUNT 2` while `TYPE_COUNT 3`?

**Answer:** `TYPE_COUNT` counts all three type-matching beans; `FAST_COUNT` counts the beans remaining after the `fast` qualifier.

**9.** Why not use `@Resource` as a complete replacement for `@Qualifier`?

**Answer:** `@Resource` has different semantics and injection targets, typically emphasizing name lookup, and is not a drop-in replacement for filtering groups in constructors or multi-argument methods.

**10.** A qualifier string changes frequently; how can typo risk be reduced?

**Answer:** Define a custom meta-annotated qualifier such as `@Fast` or `@Region`, and apply it consistently to candidates and injection points.

## 12. Application Checklist

- [ ] Understand `@Qualifier` as a condition that **filters within the type-matching bean set**.
- [ ] Know clearly whether the injection point needs **one bean** or a **collection**.
- [ ] Bean candidates are registered via `@Bean`, component scanning, or registry APIs.
- [ ] Attach qualifier metadata to the appropriate candidate beans.
- [ ] Use the Spring `@Qualifier` package when passing a String value.
- [ ] Give every injection parameter a clear type/qualifier when multiple beans exist.
- [ ] Do not assume a qualifier can be used at most once.
- [ ] Do not rely on declaration order to pick a single candidate.
- [ ] Understand the difference between `@Primary` and qualifier filtering.
- [ ] Rely on bean name fallback only when you understand its matching conditions.
- [ ] Do not equate Spring `@Qualifier` with Jakarta `@Qualifier`.
- [ ] When creating a custom qualifier, use runtime retention and appropriate targets.
- [ ] Test one candidate, multiple candidates with the same qualifier, and missing-candidate cases.
- [ ] When injecting a list/map, control ordering or sort if deterministic output is required.
- [ ] Keep runtime selection based on business data in services/routers, not hidden in annotations.
- [ ] Do not treat `@Qualifier` as a fix for transaction, lifecycle, or concurrency bugs.

### Official References

- [Spring — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring — Using Generics as Autowiring Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/generics-as-qualifiers.html)

**Conclusion:** Spring's `@Qualifier` narrows **beans that already match the target type** based on labels or required metadata. If a single bean is needed, a unique candidate must still remain after filtering (or another rule must pick one); if a `List`/`Set` is needed, multiple beans carrying the same qualifier can all be injected together. This is the difference between **filtering a candidate set** and **looking up a single exact bean name**, and it provides a foundation for extensible DI design without choosing implementations by incidental order.