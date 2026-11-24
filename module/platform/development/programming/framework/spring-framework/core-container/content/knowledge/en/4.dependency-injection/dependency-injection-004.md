# Field Injection and Its Impact on Testing in Spring

## 1. Field Injection Concept and the Core Problem

**Field injection** is a form of Dependency Injection (DI) in which the Spring IoC Container assigns collaborator beans directly into **fields of an already constructed object**. The familiar style looks like:

~~~java
// Illustrative code; the GreetingRepository interface is in the full example in section 5.
class FieldWiredGreeter {
    @Autowired
    private GreetingRepository repository;

    String greet(String name) {
        return repository.greet(name);
    }
}
~~~

`@Autowired` on a field is a valid Spring mechanism. However, calling `new FieldWiredGreeter()` in plain Java **does not trigger autowiring**, leaving `repository` unassigned. Calling `greet()` can throw a `NullPointerException` even though the code **compiles cleanly**. That is a consequence of **hiding dependencies from the constructor signature**.

Separate three questions:
1. **What dependencies are needed?** For instance, `GreetingRepository` is required for the service to produce a greeting.
2. **Who supplies the dependency?** Does a plain Java caller pass it into a constructor, or does the Spring container resolve a bean?
3. **Can logic be tested without booting a container?** If dependencies are visible in the constructor, passing a fake is straightforward. If they live only in `private` fields with `@Autowired`, test authors often have to start Spring or reach into the fields.

| Characteristic | Field injection | Constructor injection |
| --- | --- | --- |
| Where dependencies are declared | `@Autowired` on field | Constructor parameters |
| `new Service()` without dependencies | Can construct an unwired object | Does not compile if only parameter-requiring constructors exist |
| `final` references | Incompatible with post-construction assignment | Natural, easy to establish immutable wiring |
| Plain Java unit tests | Requires a mechanism to populate private fields | `new Service(fake)`, no Spring needed |
| Signal of too many dependencies | Scattered across fields/annotations | Clearly visible in the constructor |
| Autowiring when Spring manages the bean | Yes | Yes |
| Can fail due to missing bean in Spring | Yes | Yes |

**Do not conclude that field injection is always wrong.** It is supported by Spring, and legacy systems or integration adapters still use it. The goal is to recognize its **concrete impact on testability, initialization state, and API clarity** so you can choose the right DI mechanism.

## 2. When Does Spring Perform Field Injection?

When the container instantiates a **Spring-managed bean**, annotation post-processors such as `AutowiredAnnotationBeanPostProcessor` process `@Autowired` and look up a compatible bean to assign to the field. This happens **after the constructor runs** (before the bean finishes initialization for normal use).

~~~text
Config source: @Bean or @Component + scan
                    |
                    v
          Register BeanDefinition
                    |
                    v
           Spring instantiates Java object
                    |
                    v
       Process @Autowired private field
                    |
           Resolve dependency
              /           \
       Candidate found   Required missing
            |                 |
            v                 v
     Assign reference   Bean creation fails
            |
            v
       Initialization callbacks
            |
            v
      Bean ready for use
~~~

`private` fields can still be injected by Spring via reflection and the appropriate access mechanism. That does not mean Java skips encapsulation for arbitrary callers. Under the **Java module path (JPMS)**, reflection access and module openness may require explicit configuration; this example runs on the **traditional classpath**.

**Important:** placing annotations on a class or field **does not register a bean by itself**. The object must be managed by the container via valid configuration: component scanning, `@Bean`, XML, or explicit registration APIs. `AnnotationConfigApplicationContext` automatically registers the required annotation post-processors when initialized with Java configuration.

With a field-injected bean:

~~~java
@Autowired
private GreetingRepository repository;
~~~

Do not access `repository` inside the constructor if you rely on Spring injecting it: at that point the field still holds its default or Java inline-initialized value. Before handing a bean to clients, the container normally has either completed injection or raised a wiring error.

**`@Autowired` is required by default.** Lacking a matching bean typically causes Spring to fail during bean creation. For non-lazy singletons in an `ApplicationContext`, the failure can appear right at `refresh()`/startup; for lazy or prototype beans, it can appear on first request. This differs from manually calling `new` in Java and ending up with a null field.

## 3. Why Are Unit Tests for Field Injection Often Harder?

### Hidden Dependencies in the Constructed Object

A unit test writing:

~~~java
// Illustrative snippet:
FieldWiredGreeter service = new FieldWiredGreeter();
service.greet("An");
~~~

has instantiated the object without supplying a repository. The test author only discovers the dependency by reading fields/annotations or hitting a runtime failure. Meanwhile:

~~~java
// Illustrative snippet of a class with a constructor dependency:
ConstructorWiredGreeter service =
        new ConstructorWiredGreeter(name -> "Fake:" + name);
System.out.println(service.greet("An"));
~~~

works completely in plain Java; the fake lambda implements a single-abstract-method interface.

### Strategies for Testing Field-Injected Beans

| Strategy | What It Tests | Limitations |
| --- | --- | --- |
| Spin up a small `ApplicationContext` | Whether the container injects properly and the bean works | Tests must prepare Spring config and run container lifecycle |
| Spring Test `ReflectionTestUtils.setField` or raw reflection | Business behavior after forcing the dependency | Tests couple to field names/implementation details; needs `spring-test` for the utility |
| Add a setter or package-level test seam | Allows manual dependency assignment | Can introduce test-only APIs, mutable state, and missing invariants |
| Refactor to constructor injection | Unit test business logic with fakes, no Spring needed | Requires updating the constructor and composition root |
| Mockito `@InjectMocks` (when using Mockito) | Instantiates subject and attempts to inject mocks | Mock tool behavior does not replace Spring wiring tests; adds separate dependency/runner |

In new code that you control, **constructor injection + plain Java unit tests** generally cost less to maintain than reflecting over private fields. For code you cannot modify, a small test context is a transparent option when the goal is genuinely to verify Spring autowiring.

**Behavior unit tests differ from wiring integration tests:** `greet("An")` logic can be right while Spring config is missing a bean; or Spring config can pass while business logic returns the wrong value. Use the right verification tool for each goal.

## 4. Constructor Injection, `final`, and Immutable Design

Recommended declaration for a required dependency:

~~~java
// Snippet; requires importing java.util.Objects and the GreetingRepository interface.
final class ConstructorWiredGreeter {
    private final GreetingRepository repository;

    ConstructorWiredGreeter(GreetingRepository repository) {
        this.repository =
                Objects.requireNonNull(repository, "repository");
    }

    String greet(String name) {
        return repository.greet(name);
    }
}
~~~

**Benefits:**
- The constructor API makes clear that the object requires `GreetingRepository` from the outset.
- Plain Java callers can pass an in-memory or fake repository without Spring.
- `Objects.requireNonNull` fails fast even when invoked from plain Java code.
- `final` fields ensure references are not reassigned after construction.
- When a constructor accumulates too many dependencies, code review easily spots that the class is taking on too many responsibilities.

Note: `final` **does not make the repository itself immutable or thread-safe**. The repository may still hold mutable state or perform I/O; Spring singletons also do not automatically synchronize multi-threaded calls.

Spring Framework supports autowiring a component's **single constructor** normally **without requiring `@Autowired`**. With `@Bean` configuration, you can also let Spring inject via factory method parameters. Multiple constructors must follow constructor selection rules; do not expect Spring to guess the right overload arbitrarily.

**You do not need to avoid every `new` call in Spring.** A `@Bean` factory method can return `new ConstructorWiredGreeter(repository)`; what Spring provides is **resolving `repository` and managing the returned object** as a bean in the container.

## 5. Java 17 Maven Project: One Program Comparing Both Injection Styles

The example uses **plain Spring Framework**, without Spring Boot, an HTTP server, or a database. The program observes:
1. `new FieldWiredGreeter()` in plain Java **has no repository**.
2. The constructor-wired service accepts a plain Java fake and **works immediately**.
3. A Spring context registering both services: **both field and constructor injection work**.
4. The constructor-injected service holds the exact dependency bean retrieved from the context.

Requires JDK **17+**, Maven **3.9+**, and Maven Central/mirror access to fetch dependencies if needed. Lesson versions: **Spring Framework 7.0.9**, **JUnit Jupiter 5.12.2**.

### 5.1. Structure

~~~text
field-injection-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/FieldInjectionDemo.java
    └── test/
        └── java/demo/FieldInjectionDemoTest.java
~~~

### 5.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>field-injection-demo</artifactId>
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
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.2</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.3</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.FieldInjectionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides `AnnotationConfigApplicationContext`, `@Configuration`, `@Bean`, and `@Autowired` processing; Maven resolves the necessary foundational Spring artifacts automatically. `junit-jupiter` is a **test-scope** dependency; Surefire runs tests via the JUnit Platform. The POM does not need `spring-test` because the example test opens the context directly with `AnnotationConfigApplicationContext`.

### 5.3. `src/main/java/demo/FieldInjectionDemo.java`

~~~java
package demo;

import java.util.Objects;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class FieldInjectionDemo {
    private FieldInjectionDemo() {
    }

    @FunctionalInterface
    interface GreetingRepository {
        String greet(String name);
    }

    static final class FieldWiredGreeter {
        @Autowired
        private GreetingRepository repository;

        boolean hasRepository() {
            return repository != null;
        }

        String greet(String name) {
            return repository.greet(name);
        }
    }

    static final class ConstructorWiredGreeter {
        private final GreetingRepository repository;

        ConstructorWiredGreeter(GreetingRepository repository) {
            this.repository =
                    Objects.requireNonNull(repository, "repository");
        }

        GreetingRepository dependency() {
            return repository;
        }

        String greet(String name) {
            return repository.greet(name);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public GreetingRepository greetingRepository() {
            return name -> "Hello, " + name + "!";
        }

        @Bean
        public FieldWiredGreeter fieldWiredGreeter() {
            return new FieldWiredGreeter();
        }

        @Bean
        public ConstructorWiredGreeter constructorWiredGreeter(
                GreetingRepository repository) {
            return new ConstructorWiredGreeter(repository);
        }
    }

    public static void main(String[] args) {
        // Plain Java new does not execute @Autowired.
        var plainField = new FieldWiredGreeter();
        System.out.println("plain.field.ready="
                + plainField.hasRepository());

        try {
            plainField.greet("Lan");
        } catch (NullPointerException expected) {
            System.out.println("plain.field.callFailed=true");
        }

        // Constructor accepts a fake: no context needed.
        var plainConstructor = new ConstructorWiredGreeter(
                name -> "Fake:" + name);
        System.out.println("plain.constructor.greet="
                + plainConstructor.greet("Lan"));

        // Control case with the Spring container.
        try (var context = new AnnotationConfigApplicationContext(
                AppConfig.class)) {
            var field = context.getBean(FieldWiredGreeter.class);
            var constructor = context.getBean(
                    ConstructorWiredGreeter.class);
            var repository = context.getBean(GreetingRepository.class);

            System.out.println("spring.field.ready="
                    + field.hasRepository());
            System.out.println("spring.field.greet="
                    + field.greet("Lan"));
            System.out.println("spring.constructor.greet="
                    + constructor.greet("Lan"));
            System.out.println("spring.constructor.sameDependency="
                    + (constructor.dependency() == repository));
            System.out.println("spring.constructor.singleton="
                    + (constructor == context.getBean(
                            ConstructorWiredGreeter.class)));
        }
    }
}
~~~

**Explanation:**

- `plainField` is constructed outside Spring, so the field annotation **is not processed**. The null failure in the demo is caught deliberately; **do not** catch `NullPointerException` to handle missing dependencies in production.
- `plainConstructor` receives a fake via a single-method lambda, verifying a testable API without a container.
- `AppConfig` supplies the `GreetingRepository` bean and both services. Even though `FieldWiredGreeter` is returned from a `@Bean` factory method (without `@Component`), Spring **still post-processes that bean and injects the `@Autowired` field**.
- `constructorWiredGreeter(GreetingRepository repository)` receives its dependency via a **Spring-resolved `@Bean` method parameter**. `ConstructorWiredGreeter` only depends on Java's `Objects` API and does not import Spring.
- `@Configuration(proxyBeanMethods=false)` is appropriate because factory methods do not call one another directly to obtain beans. Default singleton scope ensures two lookups of `ConstructorWiredGreeter` from **the same context** return the same object.

### 5.4. Compiling/Running and Expected stdout

From the `field-injection-demo` directory containing `pom.xml`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

Maven Compiler Plugin compiles with `javac` targeting `--release 17`; Exec Plugin places Spring dependencies on the runtime classpath. Output of the first three version checks depends on your machine.

**8 stdout lines printed by `main`**, excluding environment-specific Maven/Spring logs:

~~~text
plain.field.ready=false
plain.field.callFailed=true
plain.constructor.greet=Fake:Lan
spring.field.ready=true
spring.field.greet=Hello, Lan!
spring.constructor.greet=Hello, Lan!
spring.constructor.sameDependency=true
spring.constructor.singleton=true
~~~

The output proves **field injection does not always fail**: in a Spring-managed bean, it works. The difference is that when testing with `new`, the field-injected service offers no constructor API to pass required dependencies, whereas the constructor-injected service accepts fakes cleanly.

## 6. JUnit 5: Separating Containerless Unit Tests from Bean Wiring Tests

Complete file **`src/test/java/demo/FieldInjectionDemoTest.java`**:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

final class FieldInjectionDemoTest {

    @Test
    void constructorBehaviorWithoutSpring() {
        FieldInjectionDemo.GreetingRepository fake =
                name -> "Test:" + name;
        var service = new FieldInjectionDemo.ConstructorWiredGreeter(fake);

        assertEquals("Test:Lan", service.greet("Lan"));
        assertSame(fake, service.dependency());
        assertThrows(NullPointerException.class,
                () -> new FieldInjectionDemo.ConstructorWiredGreeter(null));
    }

    @Test
    void plainFieldObjectIsUnwired() {
        var service = new FieldInjectionDemo.FieldWiredGreeter();

        assertFalse(service.hasRepository());
        assertThrows(NullPointerException.class,
                () -> service.greet("Lan"));
    }

    @Test
    void springManagesBothInjectionStyles() {
        try (var context = new AnnotationConfigApplicationContext(
                FieldInjectionDemo.AppConfig.class)) {
            var field = context.getBean(
                    FieldInjectionDemo.FieldWiredGreeter.class);
            var constructor = context.getBean(
                    FieldInjectionDemo.ConstructorWiredGreeter.class);
            var repository = context.getBean(
                    FieldInjectionDemo.GreetingRepository.class);

            assertTrue(field.hasRepository());
            assertEquals("Hello, Lan!", field.greet("Lan"));
            assertEquals("Hello, Lan!", constructor.greet("Lan"));
            assertSame(repository, constructor.dependency());
        }
    }
}
~~~

Run:

~~~bash
mvn -q test
~~~

**Expected test results:** 3 test methods pass, **0 failures, 0 errors, 0 skipped**. The Surefire report can be read at `target/surefire-reports/demo.FieldInjectionDemoTest.txt`, or omit `-q` when running Maven to view the summary. **There is no single fixed stdout for all of Maven/Surefire**, so do not pretend every run prints the exact same terminal block.

**Three distinct purposes:**
1. `constructorBehaviorWithoutSpring`: verifies business logic and null invariants **without** a context.
2. `plainFieldObjectIsUnwired`: negative test for `new` on a field-injected object, not a claim that Spring DI is broken.
3. `springManagesBothInjectionStyles`: small integration test confirming bean registration/post-processing and real wiring.

A unit test for a service without Spring can use a fake/spy/mock to check logic; an integration test with a context is needed when verifying configuration. In larger applications, separating test types shortens feedback loops and avoids depending on unrelated beans.

## 7. Plain Java 17 with `javac`/`java`: Injection Is Not Exclusive to Spring

Create a standalone file **`PlainJavaGreeter.java`** outside the Maven project (or in an independent example directory):

~~~java
import java.util.Objects;

public class PlainJavaGreeter {
    interface Greeter {
        String greet(String name);
    }

    static final class Service {
        private final Greeter greeter;

        Service(Greeter greeter) {
            this.greeter = Objects.requireNonNull(greeter);
        }

        String greet(String name) {
            return greeter.greet(name);
        }
    }

    public static void main(String[] args) {
        Service service = new Service(name -> "Fake:" + name);
        System.out.println("pure.fake=" + service.greet("Lan"));

        try {
            new Service(null);
        } catch (NullPointerException expected) {
            System.out.println("pure.rejectsNull=true");
        }
    }
}
~~~

Compile and run with JDK 17+, **without Maven or Spring**:

~~~bash
javac PlainJavaGreeter.java
java PlainJavaGreeter
~~~

Stdout:

~~~text
pure.fake=Fake:Lan
pure.rejectsNull=true
~~~

Takeaway: designing DI through constructors is a fundamental Java technique. Spring adds **automatic bean resolution and lifecycle management**, rather than replacing the responsibility of designing classes with clear contracts.

## 8. Field Injection with Optional Dependencies, Qualifiers, and Limits

### `@Autowired(required=false)`

~~~java
// Snippet (placed inside a class with the appropriate Repository type):
@Autowired(required = false)
private GreetingRepository repository;
~~~

If no matching bean is found, Spring may **skip assigning the field**, leaving its initial default (`null` if unassigned). That is **only valid** if the dependency is genuinely optional per the class contract and every usage site handles its absence. For a required repository, marking it optional merely to avoid startup failures is risky.

If multiple `GreetingRepository` beans share the same type with no clear selection rule, Spring may still throw `NoUniqueBeanDefinitionException`. `required=false` **is not a switch for “pick any bean arbitrarily”**.

### `@Qualifier`, `@Primary`

Ambiguity across candidates can be resolved on field injection:

~~~java
@Autowired
@Qualifier("primaryGreetingRepository")
private GreetingRepository repository;
~~~

Requires importing `org.springframework.beans.factory.annotation.Qualifier` and having a bean with the matching qualifier or name. With constructor injection, you can place `@Qualifier` on the corresponding **constructor parameter**; switching injection mechanisms does not resolve ambiguity on its own.

### `final` and Thread Safety

Do not try to make field injection `private final Repository repository` and expect Spring to bypass construction invariants cleanly. In normal Java code, `final` fields must be initialized during object construction; constructor injection is the clear path.

Still, keeping references `final` only gives **stable wiring**; it does not make the repository object immutable or thread-safe. A singleton with mutable fields can still suffer race conditions when used from multiple threads. Design stateless beans or synchronize appropriately.

### Circular Dependencies

Field/setter injection can sometimes let certain dependency cycles be resolved via early references, though not in every case. Partially initialized objects can be hard to reason about; **do not use field injection as the default fix for circular dependencies**. Revisit dependency direction, class responsibilities, and how services are split.

## 9. When to Keep Field Injection vs. When to Refactor

**Prefer constructor injection** when:
- A dependency is **required** for the object to function properly.
- You want to unit test the service with fakes/stubs/mocks without starting Spring.
- You want `final` fields and explicit construction invariants.
- A business class must also work in CLI/batch jobs or standalone Java code.
- You want code reviews to spot the dependency graph in the constructor and detect overloaded classes.

**You may temporarily keep field injection** when:
- Maintaining large legacy codebases where changing constructors would require editing many entry points.
- Code is a Spring-managed framework adapter verified primarily through a context with no need for direct `new`.
- Migrating incrementally to constructor injection behind test coverage; do not refactor mechanically without verifying behavioral impact.

When a legacy class cannot be modified, tests can use a small context or a reflection helper. Keep in mind that **tests then couple to implementation details** such as field names and require reflection permissions. Spring Test's `ReflectionTestUtils` requires the `spring-test` artifact in test scope; **this example's POM omits that artifact** because tests do not use reflection.

A practical comparison: field injection saves a few lines of constructor boilerplate, yet can increase setup steps and hidden assumptions in every unit test. Evaluate by **total complexity** rather than class line count alone.

## 10. Common Errors and How to Fix Them

| Symptom | Possible Cause | How to Check / Fix |
| --- | --- | --- |
| `new FieldWiredGreeter()` then `greet()` throws NPE | Java does not run Spring post-processors | Use constructor injection for plain Java tests or test through a context |
| `@Autowired` field on an object created via `new` stays null | Object is not managed by the container | Register the bean properly or design the class without container reliance |
| Spring startup fails for missing repo | Required field has no candidate | Check bean registration, component scan, type, and qualifier |
| Multiple repositories of the same type | Candidate ambiguity | `@Qualifier`, `@Primary`, or explicit configuration |
| Field accessed inside the constructor | Field injection occurs after construction | Pass required dependencies through the constructor |
| Test cannot assign a private field | Dependency has no seam for injection | Refactor to constructor; for legacy code consider context/reflection |
| `final` field still allows mutating child object contents | `final` locks the reference, not the object graph | Immutable value objects/defensive copies/concurrency design |
| `@Autowired(required=false)` still causes NPE | Field is null yet business code does not check | Decide whether the dependency is truly optional or required |
| Tests too slow because Spring starts for every method | Using a context even for simple behavior tests | Separate unit tests using fakes from wiring integration tests |
| Field/circular dependency yields half-initialized objects | Circular dependency graph or unclear lifecycle | Break the cycle and design simpler dependency direction |
| Maven error `package org.springframework...` | Missing Spring on compile classpath | Ensure `spring-context`, sync Maven, verify JDK |
| Stdout differs from original | Source/config modified or background logs mixed in | Run original source and separate app stdout from diagnostics |

**Error layering:** a missing JAR is a classpath/build error; a missing required bean is a container wiring error; calling `new` in Java and hitting a null field is a construction contract error; wrong business results are a business logic error. Do not apply one fix to every layer.

## 11. Practice Exercises and Checklist

Run each experiment on **a copy**, restoring the source between exercises to compare with the original stdout:

1. **Refactor:** change `FieldWiredGreeter` to a constructor taking `GreetingRepository`, update the `fieldWiredGreeter(repo)` factory, and write a plain Java unit test without a context.
2. **Keep field, use Spring:** add a test asserting the repository reference inside the field bean after context startup (via an observation method, no reflection needed).
3. **Remove repo bean:** delete `@Bean greetingRepository()` in the copy; observe the startup failure and cause chain.
4. **Add a second candidate:** register another `GreetingRepository` bean; predict ambiguity in both field and factory-method injection.
5. **Use qualifier:** select the desired bean and confirm both services receive the expected implementation.
6. **Try `@Autowired(required=false)`:** pretend no repo exists; explain why the service must define a valid fallback before marking it optional.
7. **Test another fake:** change the fake lambda in JUnit to `name -> "TEST2:" + name` and update the assertion without modifying the business class.
8. **Check `final`:** try reassigning `repository` after construction in the constructor-wired service; observe the compiler error.
9. **Access dependency in field service constructor:** describe why accessing a field-injected dependency there happens too early.
10. **Drop the context:** use `PlainJavaGreeter` to test the `greet` logic and null validation using only `javac`/`java`.
11. **Multiple contexts:** compare object identity across two contexts and explain why singletons are scoped per container.
12. **Design a test suite:** group pure unit tests for logic and integration tests for bean wiring, deciding which should run more frequently.

**Checklist:**
- [ ] Field injection uses `@Autowired` on fields of a **Spring-managed bean**.
- [ ] Spring populates fields after construction; plain Java `new` does not trigger wiring.
- [ ] Constructor injection lets you instantiate valid objects with fakes in unit tests.
- [ ] `final` constrains the reference, not deep immutability or thread safety.
- [ ] Accurately predict the 8 Maven stdout lines and 2 plain Java stdout lines.
- [ ] Distinguish behavior, negative scenario, and Spring wiring across the 3 JUnit tests.
- [ ] `@Autowired(required=false)` is only appropriate for genuinely optional dependencies.
- [ ] Resolve missing/ambiguous beans via proper configuration rather than hiding errors with annotations.
- [ ] Know when to use a test context, when to use plain Java fakes, and why reflection tests are brittle.

## 12. Summary and References

Field injection **works inside Spring** but obscures required dependencies in the construction API: unit tests calling `new` directly easily create unwired objects. Constructor injection makes the contract explicit, supports `private final`, fails fast with null guards, and allows testing behavior with plain Java fakes. In a Spring app, both styles still rely on accurate bean configuration.

Official references:
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — Annotation-based Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework — Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [JUnit 5.12.2 Guide](https://docs.junit.org/5.12.2/user-guide/)
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)

**Takeaway:** Optimizing testability does not mean abandoning DI or Spring, but **placing dependencies in the object's explicit contract**, using Spring to assemble the graph, and booting a container only in tests that genuinely need to verify Spring wiring.