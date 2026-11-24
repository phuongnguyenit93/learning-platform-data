# How `@Autowired` Is Processed in the Spring IoC Container

## 1. `@Autowired` Is an Instruction for the Container, Not Automatic Java Syntax

`@Autowired` is an annotation belonging to the **Spring Framework** (package `org.springframework.beans.factory.annotation`) used to describe the points where Spring should provide a dependency. It can be placed on a **constructor, instance field, setter, or configuration method with parameters**. At supported locations, the Spring IoC Container looks up a suitable bean and passes **that bean's reference** to the object being created.

The key point: **the Java compiler/JVM does not automatically run DI just because it sees `@Autowired`.** An annotation is metadata; Spring must read and process it through the container's infrastructure.

~~~java
// Illustrative snippet, not a standalone file.
@Autowired
private MessageSource source;
~~~

Inside a **Spring-managed bean**, Spring can supply the appropriate `MessageSource` to the field above. However, if you write `new SomeService()` outside the container, Spring does not automatically reach into the newly instantiated object to inject the field; the field may remain `null`. Similarly, simply attaching `@Autowired` does not register a class as a bean.

This article answers five questions:
1. Who reads `@Autowired`, and at **which stage** of the bean lifecycle?
2. How does Spring choose the **constructor**, **bean candidate**, and **injection points**?
3. When does field injection differ from constructor injection and method injection?
4. How do `required`, `Optional<T>`, `ObjectProvider<T>`, and `@Qualifier` affect dependency resolution?
5. Why do some errors occur immediately during context `refresh()`, while others only occur when retrieving a bean?

**Scope:** Plain Spring Framework Core Container, **without** needing Spring Boot, an HTTP server, or a database. The main example uses **Java 17+, Spring Framework 7.0.9, Maven**, without relying on randomness, clocks, or internal logs to build expected stdout.

## 2. Components Involved in Processing the Annotation

| Component | Role | Should Not Be Confused With |
| --- | --- | --- |
| `BeanDefinition` | Metadata registering how to create, scope, factory method, and configuration for a bean | Actual bean instance |
| `BeanFactory` / `ApplicationContext` | Manages definitions, creates and supplies beans, resolves dependencies | Java compiler |
| `BeanPostProcessor` | Extension point intervening in certain processing phases of beans created by Spring | A regular business bean |
| `AutowiredAnnotationBeanPostProcessor` | Processor dedicated to `@Autowired` and related annotations; detects injection points, handles field/method injection, and participates in selecting constructor candidates | Java's `new` operator |
| `ConfigurationClassPostProcessor` | Processes configuration sources such as `@Configuration`, `@Bean`, and `@ComponentScan` to register appropriate metadata | A processor that injects every field itself |
| `DependencyDescriptor` and internal bean factory resolvers | Describes type, qualifier, required/optional, generic, and selects the matching dependency | Plain Java reflection mechanism |
| `InitializingBean` or init callback | Runs once dependencies are supplied and the bean has reached the initialization step | Appropriate place to choose a constructor |

In practice, `AutowiredAnnotationBeanPostProcessor` implements specialized contracts such as **`SmartInstantiationAwareBeanPostProcessor`** and **`InstantiationAwareBeanPostProcessor`**, allowing it to participate in both **determining constructors** and **populating/injecting** the instance.

With `AnnotationConfigApplicationContext` and typical Java configuration, Spring **pre-registers the essential annotation processors**. Therefore, examples using `@Autowired` do not need to manually `new AutowiredAnnotationBeanPostProcessor()`.

In manually configured XML-based contexts, mechanisms like `<context:annotation-config/>` or `<context:component-scan/>` help register the appropriate processors. **XML `<bean>` declarations alone do not guarantee that annotation injection will run automatically if the corresponding infrastructure is not enabled.**

It is important to distinguish: `@Bean` or `@Component` puts a **bean definition** into the container, whereas `@Autowired` requests **resolving/supplying collaborators** for an object already undergoing bean creation. Having a bean definition does not mean all dependencies have been resolved or the instance already exists.

## 3. The Full Pipeline from Metadata to a Ready Bean

This is a **conceptual model** of a typical singleton Spring-managed bean; the internal sequence has many branches for factory methods, scopes, lazy initialization, proxies, and other extension points.

~~~text
Register @Configuration / @Bean / @Component / registerBean(...)
                             |
                             v
                BeanDefinitions in factory
                             |
                        context.refresh()
                             |
                Register BeanPostProcessors
                             |
                 Need to create target bean yet?
                       /             \
                      /               \
            Lazy/prototype        Eager singleton
               can wait                |
                     \                /
                      v              v
         Determine bean class, factory method,
           candidate constructors, metadata
                             |
           Resolve required constructor args
                             |
                    Create Java instance
                             |
         Process @Autowired on instance fields
                             |
         Process @Autowired on config methods
                             |
             Related population steps
                             |
          Aware / before-init / init callbacks
                             |
       Bean ready; may undergo post-process proxying
                             |
                 getBean(...) for client
                             |
          close() -> appropriate destroy callbacks
~~~

### Before Object Instantiation

Spring uses metadata and extension points to determine the **appropriate constructor** or factory method that will create the object. If the constructor has parameters, dependencies for those parameters are resolved **in order to have arguments for the constructor call**. Thus, constructor injection is **not** a field assignment operation after construction.

### After Object Instantiation

If the class has `@Autowired` on a field or method, the processor finds the necessary injection points and uses the bean factory's dependency resolution to supply the references. **Field injection happens after the constructor**, and in the normal processing flow, fields are injected before autowired configuration methods.

### Before Handing Over the Bean

The container completes the corresponding property population and initialization steps, possibly running **`InitializingBean.afterPropertiesSet()`** or an init method. After other BeanPostProcessors, the bean is returned to the client; certain features like AOP may create a proxy, so **the returned object does not necessarily have the same runtime class as the target**.

**Do not claim that Spring creates all beans immediately during `refresh()`:** non-lazy singletons are typically pre-instantiated when the context refreshes, whereas lazy or prototype beans may be created later when requested. A lazy bean can still be created early if another eager dependency requires it.

## 4. Constructor Selection: Before the Instance Exists

`@Autowired` can be placed on a constructor:

~~~java
// Snippet, assuming type MessageSource is already declared.
final class Consumer {
    private final MessageSource source;

    @Autowired
    Consumer(MessageSource source) {
        this.source = source;
    }
}
~~~

Spring needs to find a bean matching `MessageSource` **before** calling the constructor. Therefore, the `source` field can be `final` and the object is constructed with an explicit dependency.

Spring's rules worth remembering:
- If a bean class **declares only one constructor**, Spring typically uses that constructor **without needing** `@Autowired`.
- If a class has **multiple constructors**, Spring must have rules/metadata to choose. One constructor marked `@Autowired(required = true)` (the default) is a mandatory choice; you cannot put required `true` on multiple constructors.
- With multiple constructors marked non-required (`required=false`), Spring can evaluate candidates based on how many dependencies can be resolved, and fall back to a default/primary constructor when rules permit. This is **not** a guarantee that every overload is tried arbitrarily.
- Private/non-`public` constructors can be used by Spring when the environment's reflective access permits.
- **Missing required dependency errors** can appear when the bean is instantiated, and for eager singletons this usually happens during `refresh()`.

If the class is created via a **`@Bean` factory method**:

~~~java
@Bean
Consumer consumer(MessageSource source) {
    return new Consumer(source);
}
~~~

Spring resolves the **factory method** parameters and then invokes the `new Consumer(source)` code you wrote. This is also a form of DI performed by the container, but **do not misdescribe it as Spring choosing `Consumer`'s constructor inside the factory method**: the factory method itself chose the constructor in Java source code.

## 5. Injecting into Fields and Methods: After the Constructor

### Field Injection

~~~java
@Autowired
private Audit audit;
~~~

The processor identifies the field to assign and then resolves a matching `Audit`. If the bean has no candidate and the injection point is required, bean creation may fail. The field does not need to be `public`, but it must belong to a Spring-managed object and the environment must allow appropriate reflection.

Do not design required fields to only be assigned after construction and then accessed immediately inside the constructor. `private final Audit audit` usually suits **constructor injection**, not field injection.

### Setter or Arbitrary Configuration Method

~~~java
@Autowired
void configure(Audit audit) {
    this.audit = audit;
}
~~~

The method name is **not required** to follow the `setX` pattern. Spring can also resolve **multiple parameters** of a config method if the corresponding dependencies exist. With method injection, parameters are resolved before Spring invokes the method; a missing bean error on one parameter can prevent the entire method injection from completing.

Example of the order observed in this article's demo:
1. The constructor prints that the field has not been assigned yet.
2. Field `audit` is injected by Spring.
3. Method `configureAudit(Audit)` is called, seeing that the field already holds a reference.
4. `afterPropertiesSet()` observes the bean state with dependencies already supplied.

This is a model for verifying **lifecycle injection** of a normal bean; there is no need to hardcode a list of all processors or the internal order of bean definitions.

### Places Where It Should Not Be Used

`@Autowired` is not a general DI mechanism **for static fields/methods**. Do not try to use `@Autowired static Repo repo` to get a JVM-wide dependency. Likewise, an instance created via `new` outside the container will not receive automatic field/method injection.

On the Java module path, reflection on non-public fields/methods may require appropriate `opens` declarations. The demo project uses the **classpath**, so JPMS restrictions are not introduced in the basic run steps.

## 6. How Does Spring Find a Matching Bean?

Dependency resolution relies primarily on the **type** and metadata of the injection point. Spring can consider the type (including generic type), qualifiers, the set of candidate beans, primary/fallback, the injection point name, and the corresponding precedence rules.

| Scenario | Outcome or Handling |
| --- | --- |
| One bean has a matching type, required injection | The bean is selected and its reference is supplied |
| No matching bean, required | Typically **bean creation fails** |
| Multiple beans of the same type, no disambiguation | May encounter `NoUniqueBeanDefinitionException` |
| A bean is marked `@Primary` among matching candidates | The primary bean may be preferred when resolving a single-valued dependency |
| Injection point has `@Qualifier("name")` | Narrows candidates by matching qualifier/name, **does not create a new bean** |
| Different generic types | Spring can use generic types as a form of qualifier |
| `List<T>`, `T[]`, `Map<String,T>` | Can inject a collection of matching beans; `Map` uses bean names as keys |
| Multiple parent/child contexts | Resolution may involve hierarchy, visibility, and local overrides per container rules |

**Do not write "Spring always searches by name first, then by type".** Autowiring is designed around type and candidate selection criteria; bean name/parameter name can participate when type/qualifier and precedence rules allow, but it is not a simple universal rule for every case.

Illustrative example (not a standalone project):

~~~java
@Autowired
@Qualifier("fastGateway")
private Gateway gateway;
~~~

Spring needs a `Gateway` bean matching the qualifier. `fastGateway` in the annotation is information for **selecting a dependency**, not an instruction to create a new `Gateway`. When a class has multiple implementations, define clear qualifiers and avoid relying on parameter names that are not retained at compile time.

**Common pitfall:** a bean whose name matches the field is not guaranteed to be selected if the bean type is incompatible or excluded by qualifier/candidate filters. `@Primary` does not alter a Java type or create an alias.

## 7. Required, Optional, and Provider Are Handled Differently

By default, an `@Autowired` field/method is **required**. When a bean is missing, the container usually fails at bean creation time. However, Spring supports ways to express truly **optional** dependencies.

### `@Autowired(required = false)`

~~~java
@Autowired(required = false)
void configureMissing(MissingNotifier missing) {
    // Spring may skip the method call if there is no candidate.
}
~~~

With a **non-required config method**, when an unsatisfiable dependency is missing, Spring may **skip calling the entire method**. For a non-required field, the field can retain its initial value. Do not equate this behavior with Spring automatically passing `null` for every parameter.

### `Optional<T>`

~~~java
@Autowired
private Optional<Metrics> metrics;
~~~

Spring can provide `Optional.empty()` when there is no matching `Metrics` bean, rather than rejecting the enclosing bean. When a candidate exists, `Optional` can hold a reference to the bean. Business code must actually handle the empty branch.

**Do not call `metrics.get()` unconditionally** when the dependency is optional. Do not use optional for business-critical functionality merely to make the context "able to start up".

### `ObjectProvider<T>`

~~~java
@Autowired
private ObjectProvider<MissingNotifier> notifierProvider;
~~~

The container injects a **provider**, without necessarily creating the target bean at injection time. `notifierProvider.getIfAvailable()` can return `null` if no bean exists; `getObject()` demands an actual bean and can throw an exception if missing. A provider is useful when needing to **retrieve a dependency on demand**, especially with prototype scope or lazy behavior.

### `@Nullable`

Spring can recognize **supported nullability annotations** (such as JSpecify's `org.jspecify.annotations.Nullable` in modern Spring lines) on an injection point to indicate absence is permitted. Use the proper annotation and corresponding dependency for the version in use; this is **not** a mechanism where the Java compiler adds a bean automatically.

**For arrays/collections/maps:** Spring documentation describes that default required semantics may require at least one candidate for required injection points. There are exceptions depending on the injection point kind and version (for example, a parameter of a single constructor may receive an empty collection), so do not assume that every required `List<T>` is always empty when missing.

## 8. Runnable Java 17 Maven Project: Observing Each Stage

The example creates a `Consumer` bean with an **`@Autowired` constructor**, **`@Autowired` field**, **`@Autowired` method**, `Optional<Metrics>`, `ObjectProvider<MissingNotifier>`, a skipped optional method, and the `InitializingBean.afterPropertiesSet()` callback.

To eliminate confusion about component scanning, `Consumer` is **explicitly registered using `registerBean(Consumer.class)`**. `AppConfig` declares `MessageSource` and `Audit`. The context automatically activates the appropriate annotation processors.

### 8.1. Structure

~~~text
autowired-pipeline-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AutowiredPipelineDemo.java
~~~

Requires **JDK 17+**, **Maven 3.9+**, and the ability to download Maven dependencies on the first run.

### 8.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>autowired-pipeline-demo</artifactId>
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
                    <mainClass>demo.AutowiredPipelineDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides the Spring APIs in this article and transitively pulls the corresponding foundational Spring artifacts via Maven dependency resolution. Neither Spring Boot, a Java compiler annotation processing plugin, nor a web starter is needed. The Maven Compiler Plugin compiles with `--release 17`.

### 8.3. `src/main/java/demo/AutowiredPipelineDemo.java`

~~~java
package demo;

import java.util.Optional;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class AutowiredPipelineDemo {
    private AutowiredPipelineDemo() {
    }

    @FunctionalInterface
    interface MessageSource {
        String message(String name);
    }

    interface Metrics {
    }

    interface MissingNotifier {
        void notifyEvent(String event);
    }

    record Audit(String label) {
    }

    static final class Consumer implements InitializingBean {
        private final MessageSource source;

        @Autowired
        private Audit audit;

        @Autowired
        private Optional<Metrics> metrics;

        @Autowired
        private ObjectProvider<MissingNotifier> notifierProvider;

        private Audit auditFromMethod;
        private boolean optionalMethodCalled;

        @Autowired
        Consumer(MessageSource source) {
            this.source = source;
            System.out.println("constructor.fieldNull=" + (audit == null));
        }

        @Autowired
        void configureAudit(Audit selectedAudit) {
            this.auditFromMethod = selectedAudit;
            System.out.println("method.fieldReady=" + (audit != null));
        }

        @Autowired(required = false)
        void configureMissing(MissingNotifier notifier) {
            optionalMethodCalled = true;
        }

        @Override
        public void afterPropertiesSet() {
            boolean ready = source != null
                    && audit != null
                    && auditFromMethod != null
                    && metrics != null
                    && notifierProvider != null;
            System.out.println("init.ready=" + ready);
            System.out.println("init.metricsAbsent=" + metrics.isEmpty());
        }

        String message(String name) {
            return source.message(name);
        }

        boolean sameAudit() {
            return audit == auditFromMethod;
        }

        boolean optionalMethodSkipped() {
            return !optionalMethodCalled;
        }

        boolean providerMissing() {
            return notifierProvider.getIfAvailable() == null;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public MessageSource messageSource() {
            return name -> "Hello, " + name + "!";
        }

        @Bean
        public Audit audit() {
            return new Audit("trace");
        }
    }

    public static void main(String[] args) {
        // Empty context: register config and Consumer, then refresh.
        try (var context = new AnnotationConfigApplicationContext()) {
            context.register(AppConfig.class);
            context.registerBean(Consumer.class);
            context.refresh();

            Consumer consumer = context.getBean(Consumer.class);
            System.out.println("lookup.message=" + consumer.message("Lan"));
            System.out.println("lookup.sameAudit=" + consumer.sameAudit());
            System.out.println("optional.setterSkipped="
                    + consumer.optionalMethodSkipped());
            System.out.println("optional.providerMissing="
                    + consumer.providerMissing());
            System.out.println("scope.singleton="
                    + (consumer == context.getBean(Consumer.class)));
        }

        // Missing required dependency: exception on context.refresh().
        try (var missing = new AnnotationConfigApplicationContext()) {
            missing.registerBean(Consumer.class);
            missing.refresh();
        } catch (BeansException expected) {
            System.out.println("missingRequired.failed=true");
        }
    }
}
~~~

**Explanation of verification points:**

1. `register(AppConfig.class)` and `registerBean(Consumer.class)` create the bean definitions. The `Consumer(MessageSource)` constructor is treated as an injection point; Spring must resolve `MessageSource` to instantiate the object.
2. The constructor observes `audit == null` → `true`, because **field injection has not occurred yet** while the constructor is executing.
3. When `configureAudit(Audit)` runs, the `audit` field already holds a reference; this is evidence that field injection happens **before autowired method injection** in this demo.
4. `afterPropertiesSet()` is invoked once injection points have been processed. `init.ready=true` is not a measurement of all initialization/proxy tasks in Spring; it merely confirms that the dependencies observed in the demo are all available.
5. Since there is no `Metrics` bean, Spring injects `Optional.empty()` and `init.metricsAbsent=true`.
6. Since there is no `MissingNotifier` bean: the non-required method `configureMissing` is not called; `ObjectProvider` is still injected, and `getIfAvailable()` finds no bean.
7. `Consumer` is singleton by default. Fetching it twice from the same context yields the same reference.
8. The second context only registers `Consumer`, intentionally omitting the required `MessageSource`. Creating `Consumer` fails; the program catches `BeansException` and prints a single line, without depending on the exact exception class/message/stack trace.

**Important note about lambda:** `MessageSource` is an interface with a single abstract method, so the expression `name -> "Hello, " + name + "!"` is valid in Java 17. `Audit` is a Java `record`, which is also supported syntax in Java 17.

**Do not conclude `@Autowired` processes `Consumer` because the class has `@Component`:** the class here **does not have** `@Component`; it is registered directly via `registerBean`. What is needed is for it to belong to the container with the appropriate annotation processor present.

## 9. Build, Run, and Expected Stdout

From the `autowired-pipeline-demo` directory containing `pom.xml`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

The environment version commands do not have a single fixed stdout. The final command uses Maven to invoke the compiler and run the main class with the appropriate Spring classpath.

**10 stdout lines of the demo code** (excluding framework logs or Maven diagnostics):

~~~text
constructor.fieldNull=true
method.fieldReady=true
init.ready=true
init.metricsAbsent=true
lookup.message=Hello, Lan!
lookup.sameAudit=true
optional.setterSkipped=true
optional.providerMissing=true
scope.singleton=true
missingRequired.failed=true
~~~

**Why does this order make sense?**
- The first three lines together with `init.metricsAbsent` are printed when the first context creates the `Consumer` singleton during `refresh()`, before `getBean` returns the bean to the code in `main`.
- The `lookup.*`, `optional.*`, and `scope.*` group is printed by `main` while the context is active.
- The last line occurs when the second context tries to create `Consumer` without its required dependency, and is caught; that error may produce additional diagnostic Spring logging outside the standard `System.out.println` lines.

You can test a variation with `@Lazy` on `Consumer`: if no other eager bean needs it, the constructor/method/init lines may be deferred until the `getBean(Consumer.class)` call instead of during refresh. **Autowiring remains the exact same mechanism**, only the timing of when bean creation is requested changes.

## 10. Plain Java 17: Why Annotations Do Not Run on Their Own

To separate Java behavior from Spring, create a separate file `PureJavaInjection.java` and run it completely without Maven/Spring JARs:

~~~java
public class PureJavaInjection {
    interface Greeter {
        String greet(String name);
    }

    static final class Service {
        private Greeter field;

        Service() {
            System.out.println("constructor.fieldNull="
                    + (field == null));
        }

        void setGreeter(Greeter value) {
            field = value;
        }

        String greet(String name) {
            return field.greet(name);
        }
    }

    public static void main(String[] args) {
        Service service = new Service();
        System.out.println("beforeManualInjection="
                + (service.field == null));
        service.setGreeter(name -> "Fake:" + name);
        System.out.println("afterManualInjection="
                + service.greet("Lan"));
    }
}
~~~

Run commands from the directory containing the file:

~~~bash
javac PureJavaInjection.java
java PureJavaInjection
~~~

Stdout:

~~~text
constructor.fieldNull=true
beforeManualInjection=true
afterManualInjection=Fake:Lan
~~~

This is **not** a direct `@Autowired` example; it intentionally only illustrates the mechanism where an object is created first and supplied its dependency later. Spring automates the bean lookup/supply part when the bean belongs to the container. Plain Java does not automatically execute a framework's annotation without processing infrastructure.

On the other hand, **constructor injection** can still be done purely in Java: `new Service(greeter)` with a constructor accepting `Greeter` is a valid form of manual DI. The container helps organize resolution and lifecycle, rather than replacing the Java language.

## 11. Common Errors When `@Autowired` Does Not Work

| Symptom | Layer Causing Error | Investigation Direction |
| --- | --- | --- |
| `@Autowired` field stays null in a manually `new`'d object | Object **outside the container** | Register the bean or switch to constructor injection for plain Java testing |
| Class has `@Autowired` but context doesn't know the class | **No bean definition** | Use `@Component` + scanning the right package, `@Bean`, or `registerBean` |
| XML bean has annotations but isn't injected | **Missing annotation post-processors** | Enable `<context:annotation-config/>` / component scan or the corresponding processor |
| No bean of matching type | **Required dependency resolution** | Register the right type/qualifier, inspect the `Caused by` chain |
| Multiple beans of the same type | **Ambiguous candidates** | `@Primary`, `@Qualifier`, or explicit selection configuration |
| Field is used immediately inside constructor | **Wrong lifecycle order** | Move the required dependency to the constructor |
| `@Autowired(required=false)` method does not run | Optional injection point **unsatisfied** | Maintain valid default state; do not treat as an error if the dependency is truly optional |
| `ObjectProvider.getObject()` throws exception | Chose **required lookup** API | Consider `getIfAvailable()` and an intentional fallback |
| `Optional<T>` is empty even though a bean was expected | Bean not registered, wrong type/qualifier, or unexpected config | Verify the exact context/bean registrations; do not call `get()` blindly |
| `@Autowired` on a static field has no effect | **Static members do not support this injection style** | Design an instance service; avoid global mutable state |
| Wrong `@Qualifier` | No candidate matches the qualifier | Cross-check bean name/qualifier metadata and the injection point |
| Java source importing Spring fails to compile | **Classpath/build**, not autowiring | Check `spring-context`, build tool, dependency versions |
| Bean is not fully post-processed | Bean created too early, custom BPP/FactoryPostProcessor, or manual lifecycle | Inspect the registration and bean creation phases |
| Circular constructor dependencies | Graph **has no valid object construction order** | Split responsibilities, invert dependency direction; avoid turning required into optional to mask bugs |

**An important limitation:** `BeanPostProcessor` and `BeanFactoryPostProcessor` instances themselves have a **special** lifecycle and are registered/initialized early. Spring documentation warns against expecting `@Autowired`/`@Inject`/`@Value`/`@Resource` to be fully processed **inside processors you write yourself**; their dependencies should be configured explicitly via factory methods or XML per framework guidelines.

Additionally, if a custom `BeanPostProcessor` is registered too late, some beans already created earlier **will not be re-processed**. Therefore, simply "having seen the annotation" is not enough to ensure proper DI; one must check whether the processor infrastructure participated in the **target bean's lifecycle**.

## 12. Independent Verification, Debugging, and Design Choices

### When Observing the Pipeline

- Set breakpoints at the bean's constructor, `@Autowired` method, and `afterPropertiesSet()` to observe the stages.
- In Spring source/debugger, look at `AutowiredAnnotationBeanPostProcessor` and the `DefaultListableBeanFactory.resolveDependency` mechanism. These are **internal mechanisms for learning**, not APIs to call from business code.
- Use `getBeanDefinitionNames()` and `getBeanNamesForType` to investigate registrations; **do not hardcode the count of bean definitions** because processors and infrastructure beans are also registered.
- Read `UnsatisfiedDependencyException`, `NoSuchBeanDefinitionException`, and `NoUniqueBeanDefinitionException` along the **cause chain**. The exact message string is not a stable contract across every patch.
- Test bean wiring with a small context when needed; use fakes and constructor injection for unit tests that only verify logic.

### When to Use Field, Setter, or Constructor?

- **Required dependency:** prefer **constructor injection** + `final` fields and invariant validation; a single constructor usually does not need `@Autowired`.
- **Truly optional/configurable dependency:** can use `Optional<T>`, `ObjectProvider<T>`, or a setter with a valid default, depending on when resolution is needed.
- **Multi-argument method injection:** useful when configuring an object in one step, but requires understanding required semantics and post-construction invocation.
- **Do not use `@Autowired` to hide an oversized graph:** a constructor with very many dependencies may signal that the class holds too many responsibilities, needing design splitting rather than moving everything to private fields to look shorter.
- **Do not scatter `ApplicationContext.getBean` throughout business logic:** generally receive dependencies via constructor instead of relying on a service locator.
- **Do not assume `@Autowired` automatically creates an unregistered bean class:** the annotation resolves wiring for a bean being created, rather than replacing registration/composition root.

## 13. Exercises and Self-Assessment Checklist

Perform each experiment **on a copy** and restore the original code before comparing with section 9's stdout.

1. **Change `Consumer` to a single constructor without `@Autowired`:** predict Spring's ability to use that constructor automatically.
2. **Remove the `MessageSource` bean:** the first context may fail when `Consumer`'s constructor requires `MessageSource`. Why does `Optional<Metrics>` still not solve this?
3. **Remove the `Audit` bean:** the constructor may still run and print null field, but required field/method injection will fail afterward. Separate constructor resolution errors from property population.
4. **Add a `Metrics` bean:** predict `init.metricsAbsent=false` and explain `Optional.of(bean)`.
5. **Add a `MissingNotifier` bean:** predict that the optional method `configureMissing` is called, the provider retrieves the bean, and the two `optional.*` lines change values.
6. **Add two `MessageSource` implementations:** predict possible ambiguity; resolve with `@Primary` or `@Qualifier`.
7. **Change the declaration order of `@Bean` methods:** does it alter the nature of dependency resolution? Avoid absolute inferences from source ordering.
8. **Place `@Lazy` on `Consumer`:** predict that constructor/method/init logs appear at `getBean` instead of refresh when there is no eager consumer.
9. **Call `new Consumer(fake)` outside Spring:** the constructor still runs, but `@Autowired` fields/methods are not processed; if calling `afterPropertiesSet` manually, why does calling it not inject automatically?
10. **Change `@Autowired(required=false)` to a required method:** does the first context still start normally if `MissingNotifier` is absent?
11. **Compare constructor vs factory method:** switch `Consumer` to `@Bean Consumer consumer(MessageSource source)`, explain why Spring resolves the method parameter while Java code chooses the constructor.
12. **Write a unit test:** pass a fake `MessageSource` to a class using only constructor injection to test behavior without opening a context. Write an integration test only when wanting to verify processor/registration.
13. **Check scope:** change `Consumer` to prototype and fetch it twice; observe that each instance is post-processed and gets its own dependencies per scope rules.

**Checklist:**
- [ ] Distinguish annotation **metadata** from DI executed by the container.
- [ ] Know the role of `AutowiredAnnotationBeanPostProcessor` and related bean factory infrastructure.
- [ ] State the correct order: constructor selection → construction → field/method population → initialization.
- [ ] Distinguish an `@Autowired` constructor from Spring injection of `@Bean` factory method parameters.
- [ ] Know that the bean must be **registered and the processor must exist**.
- [ ] Explain type/qualifier/primary and ambiguity.
- [ ] Know that `Optional<T>`, `ObjectProvider<T>`, and non-required methods behave differently.
- [ ] Successfully run the Java 17 Maven demo producing the exact **10 stdout lines** and plain Java producing **3 lines**.
- [ ] Know why static fields, manually `new`'d objects, and overly early processors are not normal injection paths.
- [ ] Do not treat `@Autowired` as a guarantee of correct business logic or concurrency.

## 14. Summary and Official References

**Mechanism summary:**

1. Register configuration sources → Spring obtains **bean definitions**.
2. When a bean needs to be created, the container inspects metadata and **selects a constructor/factory method**; resolves the corresponding required args.
3. The container creates the object; `AutowiredAnnotationBeanPostProcessor` performs **field/method injection** at supported injection points.
4. The container handles initialization/lifecycle and may apply other processors/proxies before handing the bean to the client.
5. Scope, lazy, optional/required, and bean candidates determine **when** and **which bean** is supplied.

Official documentation:
- [Spring Framework – Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework – Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring API – AutowiredAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/annotation/AutowiredAnnotationBeanPostProcessor.html)
- [Spring Framework – Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework – Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework – Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring Framework – Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)

**Takeaway:** `@Autowired` **does not create beans by itself and does not execute merely because the annotation exists**. It is metadata read by Spring **when creating a container-managed bean**, from which it selects/supplies dependencies by type and candidate rules, required/optional semantics, and completes the bean lifecycle. Mastering that pipeline explains autowiring errors that simply changing an annotation cannot fix.