# Why Objects Created Outside the Container Are Not Automatically Injected — `@Autowired` in the Spring Core Container

## 1. The Phenomenon: Same Class, Different Creation Path, Different Injection Result

Consider a Java class with a field:

~~~java
@Component
public class GreetingClient {
    @Autowired
    private Formatter formatter;
}
~~~

Many people think that simply adding `@Component` or `@Autowired` ensures any object of this class will automatically get a `formatter` value. **That is a misconception.** Annotations are **metadata**, not a command that executes automatically whenever Java allocates an object with `new`.

Compare:

~~~java
GreetingClient a = new GreetingClient();
GreetingClient b = context.getBean(GreetingClient.class);
~~~

This is an **explanatory snippet**, not a complete Java file. Given a Spring context with the bean registered and exactly one compatible `Formatter` bean:

- Object `a` was created directly via Java `new`. It **does not automatically go through Spring's autowiring process**, so the `formatter` field retains its default `null` value unless another constructor/code assigns it.
- Object `b` was returned from Spring's `ApplicationContext`. It passed through the **injection processing step** in a Spring-managed bean's lifecycle; `formatter` is assigned by Spring with the resolved collaborator.
- The two objects belong to the same Java class yet **do not share the same ownership**. The fact that an object's class has a bean definition **does not turn every other object of that class into a managed bean**.
- The `@Component` annotation makes the class **eligible for registration via scanning**; an object created via Java `new` outside the container is not automatically "adopted" by Spring.

**Lesson objective:** understand *why* Spring does not auto-inject objects created outside the container, *consequences*, *architecturally sound fixes*, and *limitations of APIs that can support objects created by other frameworks*.

After this article, you will be able to:

1. Explain the roles of `ApplicationContext`, `BeanFactory`, `BeanDefinition`, and `BeanPostProcessor` when creating and injecting beans.
2. Distinguish a `new` object, a Spring-managed bean retrieved via `getBean(...)`, manual constructor injection, and an external object passed to `autowireBean(...)`.
3. Understand why `@Autowired` on a field/method of an ordinary object is not processed by the JVM itself.
4. Prefer **constructor injection**, keep required collaborators in `private final` fields, and separate object creation responsibilities.
5. Know integration cases requiring `AutowireCapableBeanFactory.autowireBean(existingObject)`, along with **limitations regarding the registry and lifecycle**.
6. Analyze `NullPointerException` caused by uninjected objects, missing-bean errors, duplicate candidates, constructing objects in the wrong place, and carelessness in unit tests.
7. Run a pure **Spring Framework + Java 17+** example, without Spring Boot, using Maven, `javac`/`java`, and exact stdout.

**Scope:** this article focuses on **objects created outside the container not automatically receiving `@Autowired`**. AspectJ, JPA, Servlet, and third-party framework factories are mentioned at a recognition level without making them mandatory prerequisites for the demo.

## 2. Mechanism: Annotations Alone Do Not Inject Dependencies

Annotations in Java are stored in class/method/field metadata (according to the annotation's retention), yet **the JVM has no general rule saying "whenever you see `@Autowired`, look up a bean and assign it to the field"**.

Spring must actively perform the necessary steps:

1. **Register the class or factory method:** from `@ComponentScan`, `@Bean`, XML, programmatic bean definitions, or an appropriate `context.register(SomeClass.class)`.
2. **Identify a bean to create:** Spring uses the definition, bean name, scope, and constructor/factory information.
3. **Instantiate the object:** either via a constructor resolved by Spring or a factory method supplying the object.
4. **Resolve collaborators:** Spring finds candidates by type, qualifier, primary, name, and autowiring rules.
5. **Apply injection annotations:** post-processors such as `AutowiredAnnotationBeanPostProcessor` handle `@Autowired` on appropriate fields/methods, after the object is instantiated and before using it as an initialized bean.
6. **Complete the lifecycle:** callbacks, other `BeanPostProcessor`s, and possibly proxy creation; the container publishes the bean according to its scope and manages the lifecycle steps it is responsible for.

A simplified diagram:

~~~mermaid
flowchart TD
    A["BeanDefinition / class registration"] --> B["Spring creates or receives bean instance"]
    B --> C["Bean post-processing"]
    C --> D["Resolve @Autowired fields / methods"]
    D --> E["Initialization, proxies (if any)"]
    E --> F["Bean returned by getBean(...)"]
    N["new SomeClass() outside Spring"] --> X["Plain Java object"]
    X -.->|"Does NOT go through"| C
~~~

The diagram is intentionally simplified: constructor injection must be resolved **when creating the object**, not waiting until field/method post-processing; additionally, the initialization cycle has further extension points and dependency handling. Even so, the key boundary remains **whether it goes through Spring's pipeline or not**.

Spring can read annotations when processing **a managed bean**. An object instantiated with `new` inside a business method **does not automatically register itself** in the BeanFactory and does not automatically invoke bean post-processors.

### Distinguish Three Often-Confused Actions

| Action | Example | Meaning |
| --- | --- | --- |
| Registering a **bean definition** | `context.register(GreetingClient.class)` | Spring knows **how to create** a bean when the context processes registrations |
| Retrieving a managed **bean instance** | `context.getBean(GreetingClient.class)` | Spring supplies a bean according to scope, with matching injection/lifecycle |
| Creating an ordinary Java object | `new GreetingClient()` | The JVM allocates the object; Spring is not notified and applies no injection |

Do not interpret `@Component` as "wherever this class appears, it turns into a Spring bean". A component stereotype makes the class eligible for discovery **when the right package is scanned**, or the class can be registered by other means. It is not a mechanism intercepting every `new` call.

## 3. Most Common Case: `@Autowired` Field Is Null After `new`

~~~java
@Component
final class ReportService {
    @Autowired
    private Formatter formatter;

    String render(String input) {
        return formatter.format(input);
    }
}
~~~

This is a **snippet**, missing the `Formatter` definition and not standalone code. The call:

~~~java
ReportService report = new ReportService();
report.render("book"); // Possible NPE because formatter was not injected.
~~~

If no other code assigns the field, Java initializes reference fields to `null` by default. The `@Autowired` annotation on the field does not execute on its own; calling `render(...)` can throw a `NullPointerException`.

With a container-managed bean:

~~~java
ReportService report = context.getBean(ReportService.class);
String result = report.render("book");
~~~

when `ReportService` is actually registered, has the right dependency, and injection succeeds, `formatter` has already been supplied by the container before normal use. However, **do not infer that every `getBean` always succeeds**: missing `Formatter`, multiple ambiguous candidates, or a dependency failing initialization can still cause bean creation to fail.

**The error is not that the field is private.** Spring has mechanisms to process/inject properly annotated fields. The problem is that **whoever created the object bypassed Spring's lifecycle**.

### Why Adding `@Autowired` to a Constructor Also Fails to Rescue an Arbitrary `new` Call

With:

~~~java
final class ReportService {
    private final Formatter formatter;

    @Autowired
    ReportService(Formatter formatter) {
        this.formatter = java.util.Objects.requireNonNull(formatter);
    }
}
~~~

If code calls `new ReportService(formatter)`, the **Java caller** supplied the dependency itself. The annotation is not "activated" by the JVM via DI; the constructor just runs normally. If code tries calling `new ReportService()`, Java **fails to compile** if the class has no no-arg constructor. That is an advantage: required dependencies are explicit in the API.

Do not add a default constructor creating a missing-`formatter` state just so some caller can easily write `new`. Fix the object creation site to pass the dependency or obtain the managed bean at the proper boundary.

## 4. Who Creates the Object Determines Who Is Responsible for Injection

### When Spring Creates/Manages the Bean

- `@Component` discovered via scanning/registration or a `@Bean` factory puts the object into Spring.
- Spring resolves declared dependencies and runs appropriate injection callbacks.
- Beans usually have default singleton scope, so two `getBean("...")` calls in the same context return the same instance per singleton semantics.
- Initialization, AOP proxies, scoped semantics, and destruction callbacks can be applied per configuration/lifecycle.
- Consumers should not manually instantiate a parallel copy and assume it is configured like the bean.

### When Business Code Manually Calls `new`

- A Java-created object can work properly **if all dependencies were passed directly** via constructor/setter.
- An `@Autowired` field left unprocessed remains at its default, typically `null`.
- Spring **does not automatically register** this object in the bean registry, nor automatically apply `@Value`, `@PostConstruct`, `@Transactional` proxies, `@Async`, or `@PreDestroy` as on a managed bean.
- Creating an object **inside a method of a Spring-managed bean** does not naturally make the child object managed. The container knows about the parent bean, not every `new` instruction in the JVM.
- If the object holds resources or open connections, the caller is usually responsible for cleanup if the object does not belong to a Spring-managed lifecycle.

**One exception to distinguish:** an object instantiated with `new` inside a `@Bean` factory method to **return to Spring** can become a managed bean specifically because the factory method is **a bean creation path used by the container**. In other words, the `new` keyword itself is not forbidden; what matters is **whether the object enters the container's management pipeline**.

## 5. Preferred Fix: Constructor Injection and Separating Object Creation

Favor classes where required dependencies are passed explicitly:

~~~java
public final class GreetingService {
    private final Formatter formatter;

    public GreetingService(Formatter formatter) {
        this.formatter = java.util.Objects.requireNonNull(
                formatter, "formatter is required");
    }

    public String greet(String raw) {
        return formatter.format(raw);
    }
}
~~~

**A snippet that can go into a suitable file after declaring `Formatter`**, not a complete program. Two valid ways to instantiate it:

~~~java
// Plain Java, no Spring needed:
Formatter fake = raw -> "TEST:" + raw;
GreetingService unit = new GreetingService(fake);

// Spring at the composition root:
Formatter managedFormatter = context.getBean(Formatter.class);
GreetingService manuallyComposed =
        new GreetingService(managedFormatter);
~~~

In both cases, the manually created object **has its full collaborator** thanks to the Java constructor; it **does not automatically become a Spring bean** merely because the collaborator came from the context.

Usually a better design in a Spring application: **also register `GreetingService` as a bean** and inject it into the controller/job/service beans that need it. Do not scatter `getBean(...)` calls across business methods.

### When Is Using `new` Normally Appropriate?

Use `new` naturally for objects **not needing container management**: DTOs, value objects, immutable domain data, collections, plain Java classes with explicit parameters, or local helpers needing no injection/AOP/lifecycle. **Do not force every Java object to become a Spring bean.**

A practical rule of thumb:

- **Has framework-managed dependencies or lifecycle?** Let Spring manage it or explicitly define a factory.
- **Has collaborators that are easy to pass via constructor?** Manual DI is completely valid.
- **Is a value object without service dependencies?** Ordinary `new` is right.
- **Object created by an external library where you don't control the constructor?** Consider an adapter or an API deliberately supporting autowiring existing instances.

**Constructor injection makes bugs easier to spot:** `Objects.requireNonNull` rejects missing references at construction time; `private final` prevents references from being overwritten. However, a `final` field does not automatically make a mutable collaborator thread-safe and does not automatically apply Spring AOP.

## 6. An Integration Exception: `AutowireCapableBeanFactory.autowireBean(...)`

Spring provides a low-level API to **inject dependencies into an existing object**:

~~~java
LegacyClient external = new LegacyClient();
context.getAutowireCapableBeanFactory().autowireBean(external);
~~~

**This is a snippet**; the full class/context appears in section 7. `AutowireCapableBeanFactory.autowireBean(existingObject)` applies **after-instantiation callbacks/property post-processing**, including annotation-driven injection such as `@Autowired` on the instance's fields/setters.

This API serves scenarios **integrating with another system that owns object creation**, not as a default technique across all business code.

### What It Does and Does Not Do

| Aspect | Outcome When Calling `autowireBean(external)` |
| --- | --- |
| Existing instance already created by Java | Keeps the same instance supplied by the caller |
| Matching `@Autowired` fields/methods | Can be processed/populated if dependencies resolve |
| `@Autowired` constructor of an already-`new`'d class | **Does not re-run the constructor** and does not change how the object was created |
| Automatically adds a bean definition to the registry | **No** |
| `context.getBean(LegacyClient.class)` finds the external object | **No**, unless registered separately |
| Guarantees full init/post-processors/AOP proxies like a managed bean | **Cannot be concluded solely from `autowireBean`** |
| Guarantees full destruction callbacks on context close | **No**; the caller must still manage lifecycle properly |
| Missing or ambiguous dependency | Can still fail with injection errors, not "forgiven" for being an external object |

This is a detail easily misinterpreted: **being injected does not mean being registered as a Spring bean**. You can observe `external.formatter != null` after `autowireBean` while `getBeanNamesForType(LegacyClient.class)` remains empty. On that object, mechanisms related to bean name, singleton registry, proxies, and teardown may not behave like a normal managed bean.

### Related APIs Are Not Identical

- `autowireBean(Object)`: processes dependency annotations/property post-processing on an **existing instance**, without generating a bean registry entry.
- `createBean(Class<T>)`: asks the bean factory to **create a new instance and run creation/initialization through appropriate post-processors**, yet does not by default register it under a singleton name in the application context.
- `initializeBean(Object, name)`: applies initialization callbacks and bean post-processing to an existing object; **not a simple drop-in replacement for `autowireBean` for field injection**.
- `configureBean(Object, name)`: configures an existing object according to **an existing bean definition for `name`** and performs additional callbacks; requires a corresponding definition, so quite different from "just pass any object in".
- `registerSingleton(name, instance)` is an intentional instance registration operation on an appropriate BeanFactory, yet **does not automatically run full callbacks of normal bean creation**; do not misuse it to replace `@Bean`.

**Do not chain these APIs by guesswork** hoping to achieve identical semantics to a container-managed bean. Choose the exact capability documented and verify lifecycle/proxy/ownership impacts. For business code you control, prefer explicit bean/factory declarations or constructor injection.

## 7. Self-Contained Java 17+ Example, Pure Spring Framework

The following example runs a Spring Context and observes four cases:

1. `new FieldClient()`: the `@Autowired` field is not assigned automatically.
2. `context.getBean(FieldClient.class)`: same class yet managed by Spring and injected successfully.
3. `new ConstructorClient(formatter)`: unregistered object that works properly because of **manual constructor injection**.
4. `new LegacyClient()` followed by `autowireBean(external)`: the field is intentionally injected, **yet the object is not registered in the registry**.

**Requirements:** JDK 17+, Maven, Spring Framework **6.2.19** pinned for reproducibility. No Spring Boot, Servlet container, or DB needed. The pinned version is not a claim that it is the latest Spring release.

~~~text
external-object-autowiring/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ExternalObjectDemo.java
~~~

### 7.1. File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>external-object-autowiring</artifactId>
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
                    <mainClass>demo.ExternalObjectDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Framework dependencies are also resolved transitively by Maven. If using `javac` directly, the classpath must include all libraries resolved by Maven.

### 7.2. File src/main/java/demo/ExternalObjectDemo.java

~~~java
package demo;

import java.util.Locale;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

public final class ExternalObjectDemo {
    private ExternalObjectDemo() {}

    public interface Formatter {
        String format(String raw);
    }

    public static final class UppercaseFormatter implements Formatter {
        @Override
        public String format(String raw) {
            if (raw == null || raw.isBlank()) {
                throw new IllegalArgumentException("name is required");
            }
            return "Xin chao, " + raw.strip().toUpperCase(Locale.ROOT);
        }
    }

    @Component("fieldClient")
    public static final class FieldClient {
        @Autowired
        private Formatter formatter;

        public FieldClient() {}

        public boolean injected() {
            return formatter != null;
        }

        public String reply(String name) {
            if (formatter == null) {
                throw new IllegalStateException("formatter not injected");
            }
            return formatter.format(name);
        }
    }

    public static final class ConstructorClient {
        private final Formatter formatter;

        public ConstructorClient(Formatter formatter) {
            this.formatter = Objects.requireNonNull(
                    formatter, "formatter required");
        }

        public String reply(String name) {
            return formatter.format(name);
        }
    }

    public static final class LegacyClient {
        @Autowired
        private Formatter formatter;

        public LegacyClient() {}

        public boolean injected() {
            return formatter != null;
        }

        public String reply(String name) {
            if (formatter == null) {
                throw new IllegalStateException("formatter not injected");
            }
            return formatter.format(name);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public Formatter formatter() {
            return new UppercaseFormatter();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        AppConfig.class, FieldClient.class)) {

            // Case 1: Java new, autowiring does not run.
            FieldClient plain = new FieldClient();
            System.out.println("newInjected=" + plain.injected());
            try {
                plain.reply("Lan");
                System.out.println("newCall=UNEXPECTED");
            } catch (IllegalStateException ex) {
                System.out.println("newCall=BLOCKED");
            }

            // Case 2: Spring bean of the same class, field was injected.
            FieldClient managed = context.getBean(FieldClient.class);
            System.out.println("managedInjected=" + managed.injected());
            System.out.println("managedReply=" + managed.reply(" Lan "));

            // Case 3: manual constructor injection, unregistered.
            Formatter formatter = context.getBean(Formatter.class);
            ConstructorClient manual = new ConstructorClient(formatter);
            System.out.println("manualReply=" + manual.reply(" Minh "));
            System.out.println("manualRegistered=" +
                    (context.getBeanNamesForType(ConstructorClient.class)
                            .length > 0));

            // Case 4: autowireBean on existing external instance.
            LegacyClient external = new LegacyClient();
            System.out.println("externalBefore=" + external.injected());
            context.getAutowireCapableBeanFactory()
                    .autowireBean(external);
            System.out.println("externalAfter=" + external.injected());
            System.out.println("externalRegistered=" +
                    (context.getBeanNamesForType(LegacyClient.class)
                            .length > 0));
            System.out.println("externalReply=" + external.reply(" An "));

            System.out.println("managedSingleton=" +
                    (managed == context.getBean(FieldClient.class)));
        }
    }
}
~~~

### 7.3. Exact Expected Output

Inside the `external-object-autowiring` directory:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Exact 11 stdout lines printed by `main` on a successful run:**

~~~text
newInjected=false
newCall=BLOCKED
managedInjected=true
managedReply=Xin chao, LAN
manualReply=Xin chao, MINH
manualRegistered=false
externalBefore=false
externalAfter=true
externalRegistered=false
externalReply=Xin chao, AN
managedSingleton=true
~~~

Version lines, dependency downloads, or Maven/Spring logs if present are outside the 11 lines printed directly by the example code.

**Technical explanation of each line:**

| Output | Proof |
| --- | --- |
| `newInjected=false` | Java `new` does not automatically trigger Spring annotation injection |
| `newCall=BLOCKED` | Code has a guard; fails early without accessing a null collaborator |
| `managedInjected=true` | Bean created through the Spring context has its `@Autowired` field processed |
| `managedReply=Xin chao, LAN` | Managed bean uses the real collaborator |
| `manualReply=Xin chao, MINH` | Manual constructor injection lets a plain Java object work |
| `manualRegistered=false` | `ConstructorClient` is not auto-registered merely by being created with `new` |
| `externalBefore=false` | `LegacyClient` has not undergone injection yet |
| `externalAfter=true` | `autowireBean(external)` processed the `@Autowired` field |
| `externalRegistered=false` | Having been injected does not mean having a bean registry entry |
| `externalReply=Xin chao, AN` | External object received the formatter object from the container |
| `managedSingleton=true` | Spring-managed `FieldClient` is singleton by default in this context |

The example code avoids timestamps, random numbers, identity hashes, and collection order; expected stdout does not depend on such factors. The code and output here are presented for learners to run and verify themselves.

### 7.4. Running Directly with `javac`/`java`

Because the program imports Spring, Maven can generate the classpath for all transitive dependencies:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/ExternalObjectDemo.java
java -cp "out:$(cat classpath.txt)" demo.ExternalObjectDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/ExternalObjectDemo.java
java -cp "out;$deps" demo.ExternalObjectDemo
~~~

On Unix classpath entries are separated by `:`, on Windows by `;`. Both runs invoke `demo.ExternalObjectDemo`, hence producing the exact same 11 stdout lines. If `javac` reports `org.springframework...` not found, fix dependencies/classpath before diagnosing autowiring behavior.

## 8. Real-World Cases: Controller, Listener, Task, Helper

**A common anti-pattern in Spring MVC:**

~~~java
// Wrong if wanting this ReportService injected by Spring:
ReportService service = new ReportService();
return service.render("book");
~~~

Even if `ReportService` has `@Service`, manually calling `new` inside a controller means that instance is not managed. Use constructor injection into the controller:

~~~java
@RestController
public class ReportController {
    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }
}
~~~

**These two blocks are Spring MVC snippets, not part of the runnable Core Container project**; they also require Spring Web libraries, service declarations, imports, and real methods. Main point: a Spring-managed controller **receives the service bean**, rather than creating an unmanaged copy of the service itself.

**A similar bug in background tasks:**

~~~java
new Thread(new EmailJob()).start();
~~~

If `EmailJob` contains an `@Autowired` field without being created/processed by the container, code running in the thread will not be auto-injected either. Use a properly configured scheduler/executor and construct tasks with dependencies via constructor, or let Spring manage the service parts needing DI. **This does not mean every Runnable should be a singleton**: per-task data should still be separate objects, while managed dependencies can be passed into the constructor.

**In plain Java unit tests:** if you write `new SomeService()` and expect an `@Autowired` field to be populated, the test makes a false assumption. Use constructor injection with fakes/mocks, or use a real Spring Test context when actually testing Spring wiring; **do not boot an entire context just to unit test a simple calculation**.

**In JPA entities, deserialized objects, objects created by other libraries:** another framework may own object creation. Do not expect `@Autowired` on an entity/DTO to work automatically. It is better to pass data into a managed service handling the entity, or use a controlled integration API at the boundary. Ecosystems with their own injection mechanisms only work when configured for those mechanisms, not simply because an annotation sits somewhere.

## 9. Why `@Configurable` Does Not Automatically Fix `new`

Spring has AspectJ integration for certain objects created **outside** the IoC container, for example using `@Configurable` paired with `@EnableSpringConfigured`/`spring-aspects` and suitable **AspectJ weaving**. However:

- Simply adding `@Configurable` to a class is **not enough** for Spring to inject every `new` call.
- Supporting configuration and corresponding load-time/compile-time weaving are required; this is an advanced technique with runtime/classloader constraints and operational cost.
- It is not a reason to abandon constructor injection and turn every value/domain object into a dependency lookup point.
- Do not rely on ordinary Spring AOP proxies assuming the JVM intercepts every `new` in any Java file.

**Practical rule:** only use weaving when a specific integration requirement has been evaluated and tested; explicit constructor injection and bean registration are usually easier to understand, test, and carry fewer surprises.

## 10. Consequences of Trying to Use an Unmanaged Object Like a Managed Bean

### 10.1. No Injection Annotations Processed

`@Autowired` fields/methods are not processed, so collaborators may be null. `@Value` properties are not resolved either; `@Inject`/`@Resource` have similar limits without the appropriate container processor.

### 10.2. No Bean Lifecycle Guarantees

`@PostConstruct`, `InitializingBean`, `@PreDestroy`, destroy methods, and normal lifecycle management belong to steps the framework must actively invoke. An object `new`'d outside the container does not run Spring callbacks merely because the class carries annotations.

### 10.3. No Spring Proxies

For proxy-based features such as `@Transactional`, `@Async`, caching, or security interceptors, an object `new`'d outside the context is normally **not proxy-managed**. Method calls on that instance can bypass needed interceptors. Moreover, **self-invocation** on a managed bean has its own proxy limitations; do not use self-invocation to verify bean ownership.

### 10.4. Does Not Follow Bean Scope

A Spring singleton is scoped per bean name/container. `new SomeService()` creates a distinct Java instance from the singleton returned by `getBean(...)`. Having the same class name does not mean singleton identity.

### 10.5. No Automatic Qualifier/Primary Resolution

If a field wants a `Formatter` bean, an annotation on an unmanaged object does not cause Spring to run candidate resolution. `@Qualifier`/`@Primary` rules only take effect when an actual injection mechanism is resolving the dependency.

### 10.6. No Container Monitoring of Cleanup

If an external object opens streams/sockets/thread pools, the code that creates/owns it must close them properly. Calling `autowireBean(external)` just to inject a field **does not make Spring the default owner of all external resources**.

## 11. Distinguishing DI Errors from Java and Configuration Errors

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `@Autowired` field stays null, object created via `new` | Instance never went through Spring's pipeline | Obtain the managed bean or pass dependencies via constructor |
| `@Component` class still missing from context | Package not scanned or class not registered | Configure `@ComponentScan` or `context.register(...)` properly |
| `NoSuchBeanDefinitionException` | Injection ran yet no matching bean candidate exists | Register the dependency, check type/name/qualifier |
| `NoUniqueBeanDefinitionException` | Multiple beans of the same type without picking one | Use `@Qualifier`/`@Primary` or fix configuration |
| `UnsatisfiedDependencyException` | Constructor/field/method dependency cannot be resolved | Read `Caused by`; fix bean registration/injection point |
| `NullPointerException` when calling a `new`'d service | Collaborator field defaults to null, no guard | Do not `new` a service needing DI; use constructor non-null guards |
| Unit test using `new` fails with null | Spring not started and dependencies not supplied | Constructor-inject fakes in unit tests; context tests for wiring |
| `getBean(LegacyClient.class)` still fails after `autowireBean` | Autowiring an existing instance **does not register** it | If a managed bean is needed, declare its definition/factory upfront |
| `@Transactional` is bypassed | Calling an object outside the proxy/container | Obtain the actual proxied bean, check proxy mode/scope |
| `@PostConstruct` does not run on external instance | Only `new` or only `autowireBean`, not full lifecycle | Assign clear ownership; use lifecycle APIs properly |
| `@Configurable` has no effect | Required AspectJ weaving/infrastructure not configured | Avoid guessing; set up weaving intentionally or change architecture |
| `ObjectProvider.getObject()` missing bean | Provider lookup genuinely found no candidate | Register bean or handle optionality per contract |
| `@Autowired(required=false)` lets service run with null | Hiding a genuinely mandatory dependency | Design a required constructor and fail fast |
| `javac` reports missing Spring packages | Compile classpath lacks Spring JARs | Check POM and Maven dependency classpath |
| `ApplicationContext` already closed | External object still holds collaborators using shut-down resources | Clarify owner/caller lifecycle; do not use a closed context |

**Diagnostic tip:** when an `@Autowired` field is unexpectedly null, immediately ask **"Who created this instance?"**. Pinpoint whether it was created via `new`, a constructor/factory method, component scan, plugin loader, framework deserializer, or test runner. Only then inspect qualifiers/types/scopes. If the instance was never processed by Spring, the bug is not in `@Qualifier`.

## 12. Proper Patterns in Application Architecture

### Pattern A — Inject Managed Services into Managed Consumers (Preferred)

~~~java
@Component
public class OrderHandler {
    private final OrderService orders;

    public OrderHandler(OrderService orders) {
        this.orders = java.util.Objects.requireNonNull(orders);
    }
}
~~~

**Snippet**, requires `OrderService` registered as a bean and importing `@Component`. Spring will create/resolve dependencies when instantiating `OrderHandler`. If `OrderService` is missing a bean, startup can fail early, preventing silent nulls.

### Pattern B — Create Value Objects with `new` and Pass Data

~~~java
public record OrderRequest(String sku, int count) {
    public OrderRequest {
        if (sku == null || sku.isBlank() || count <= 0) {
            throw new IllegalArgumentException("invalid request");
        }
    }
}
~~~

A valid Java 17 record snippet inside an appropriate file. This domain record does not need `@Autowired`; creating it with `new OrderRequest("BOOK", 2)` is natural and has no missing DI.

### Pattern C — A Factory Has Managed Dependencies Yet Creates New Objects with Valid Constructors

~~~java
@Component
public class ReportFactory {
    private final Formatter formatter;

    public ReportFactory(Formatter formatter) {
        this.formatter = java.util.Objects.requireNonNull(formatter);
    }

    public ReportJob newJob(String title) {
        return new ReportJob(formatter, title);
    }
}
~~~

**Snippet**, requires the `ReportJob` class and matching imports. `ReportFactory` is a bean so it receives `Formatter` via constructor; each `ReportJob` created by the factory is a separate Java object yet **already has its dependency**, without needing field injection itself. Those `ReportJob`s do not automatically become managed beans; keep lifecycle/resources under appropriate ownership.

### Pattern D — Autowire External Objects When Integration Mandates It

If a third-party library insists on calling a no-arg constructor and only provides the object afterward, the integration boundary can call `autowireBean(existingObject)`. Document clearly:

- Who creates and who destroys the object?
- Are `@PostConstruct`/proxies/transactions needed?
- Are a bean name/scope needed in the registry?
- If a full managed bean is truly needed, can registration/factories or an adapter be used instead?

The external-object autowire API is an **integration escape hatch**, not the default way to patch services randomly created with `new`.

## 13. Testing and Exercises with Answers

### Unit Testing Without Spring

Create a fake `Formatter` and constructor-inject it into a plain Java class. No context required:

~~~java
Formatter fake = raw -> "FAKE:" + raw;
ConstructorClient client = new ConstructorClient(fake);
System.out.println(client.reply("Lan")); // FAKE:Lan
~~~

**This snippet needs to sit in a scope with access to the demo's nested types.** It proves constructor injection can be tested in plain Java without field reflection or starting the container.

### Spring Integration Testing

Create a context with `AppConfig.class` and `FieldClient.class`, retrieve `FieldClient` via `getBean(...)`; verify the collaborator is non-null and behavior is correct. Separately test `new FieldClient()` for `injected()==false`. If integration requires `autowireBean`, verify the external object after wiring, yet **do not** blindly expect `containsBean(...)` or automatic destruction.

Do not rely on Java `assert` as a mandatory runtime check in examples unless `-ea` is enabled; use test framework assertions or `if (...) throw ...`.

**Exercise 1.** A class has `@Component` and an `@Autowired` field, and you call `new MyService()` inside a controller. Why is the field null?

**Answer:** A new Java-created object does not pass through Spring injection post-processors; `@Component` does not intercept `new` calls. Inject the managed service into the controller or supply dependencies via constructor.

**Exercise 2.** Does `@Bean MyService service() { return new MyService(); }` always remain uninjected because it contains `new`?

**Answer:** No. The object returned as **the bean of a Spring-invoked factory method** goes through the corresponding processing steps. The issue is not the `new` keyword itself, but **whether the container receives/manages it as a bean**.

**Exercise 3.** Does `autowireBean(external)` make `external` a default singleton with a bean name?

**Answer:** No. The API can process annotation-driven injection on an existing object, yet does not automatically add a registry entry/singleton definition.

**Exercise 4.** If `LegacyClient` has a constructor requiring `Formatter` and you already called `new LegacyClient(null)`, will `autowireBean(...)` re-run the constructor to fix the null?

**Answer:** No. The constructor already finished when Java created the object. The API only processes injection on the existing instance per its support; fix the caller/constructor to protect invariants.

**Exercise 5.** Is an object `new`'d inside a method of a Spring bean automatically managed?

**Answer:** No. The parent object's bean scope does not make every object it creates managed. However, the creator can pass valid dependencies via constructor.

**Exercise 6.** A request DTO has no Spring collaborators. Should the DTO be registered as a singleton bean and retrieved with `getBean` on every request?

**Answer:** Usually no. DTOs/value objects carrying request data are instantiated per demand; creating them with `new` is completely appropriate and has no DI flaw.

**Exercise 7.** Why is `manualReply=Xin chao, MINH` printed while `manualRegistered=false` in the demo?

**Answer:** `ConstructorClient` received a valid `Formatter` via its Java constructor so it works properly, yet it was never registered with Spring as a bean.

**Exercise 8.** Can you put `@Configurable` on a class so every `new` is injected immediately?

**Answer:** Not by the annotation alone. AspectJ integration also requires weaving and supporting infrastructure; normal code should favor explicit constructor injection/factory beans.

**Exercise 9.** Why can a test running without Spring fail with field injection while passing with constructor injection?

**Answer:** Field injection requires a Spring processor to perform the assignment; a Java constructor only needs the caller to provide a valid fake/real collaborator, making isolated unit testing straightforward.

### Completion Checklist

- [ ] Know `@Autowired` is metadata processed by Spring, not auto-injected by the JVM after every `new`.
- [ ] Distinguish registering a class/definition from instantiating a Java object.
- [ ] Understand how `BeanPostProcessor`/`AutowiredAnnotationBeanPostProcessor` operate in the bean pipeline.
- [ ] Do not assume `@Component` makes every instance of that class managed.
- [ ] Know a `@Bean` factory can call `new` while the result becomes a managed bean when returned to the container.
- [ ] For services with required dependencies, prefer constructor injection and `Objects.requireNonNull`.
- [ ] Do not call `ApplicationContext.getBean(...)` throughout business methods just to fix ownership bugs.
- [ ] Know `autowireBean(existing)` can inject without registering or running full lifecycle.
- [ ] Distinguish `autowireBean`/`createBean`/`initializeBean`/`configureBean`/`registerSingleton` by their actual capabilities.
- [ ] Do not expect managed-bean proxies/AOP/lifecycle/scope on unmanaged objects.
- [ ] Identify ownership when objects are created by controllers, task frameworks, mappers, ORMs, or tests.
- [ ] Use normal `new` for value objects/DTOs that do not need DI.
- [ ] Run Java 17+ and verify the **exact 11 stdout lines**.
- [ ] When using `javac`/`java`, provide the complete Spring compile/runtime classpath.
- [ ] Have plain Java unit tests and wiring smoke tests; keep negative tests in separate setups.

**Conclusion:** `@Autowired` does not automatically supply dependencies to every Java object. Spring injects collaborators **when the container itself manages the bean or is explicitly asked to process an instance via a specific API**. Objects created with `new` outside the container do not go through that pipeline by default, so annotated fields can remain null. The best fix is to **let Spring own services needing DI or pass dependencies via constructor**; only use the existing-instance autowire API when genuinely integrating objects managed by another system.

### Official Spring Documentation

- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html)
- [Spring Framework — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config.html)
- [AutowireCapableBeanFactory API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/config/AutowireCapableBeanFactory.html)
- [Spring Framework — Using AspectJ with Spring Applications](https://docs.spring.io/spring-framework/reference/core/aop/using-aspectj.html)
