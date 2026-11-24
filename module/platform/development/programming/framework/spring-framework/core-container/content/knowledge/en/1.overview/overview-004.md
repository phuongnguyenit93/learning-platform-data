# Beans, Bean Definitions, and Object Instances in Spring Core Container

## 1. Three Concepts to Separate Clearly

In Spring Framework, a **bean** is an object managed by the Spring IoC container. To do that, the container needs to know **under what configuration the bean is registered** and **when to create or provide an actual object**. Three related terms that are not synonymous:

| Concept | Essence | Question it answers |
| --- | --- | --- |
| **Bean definition** (`BeanDefinition`) | Metadata/recipe declaring a bean to the container | What name, how created, what type, what scope, what dependencies, lazy or not? |
| **Bean instance** | An actual Java object that has been created/configured, living inside or supplied through Spring's managed lifecycle | Which concrete object was created? Is it the same reference as the previous lookup? |
| **Bean** | An object managed by the Spring container in the context of a bean definition/registration | By what rules can Spring supply and manage this object? |

Remember:

- `class UserService` is a **Java type**, not automatically a bean.
- `new UserService(...)` creates a **Java object**; if it is not passed through an appropriate registration/management mechanism, it does not automatically become a Spring-managed bean.
- A `@Bean UserService userService() {...}` method is a **declaration source** for the container to register a bean definition. When the container executes that factory method according to its scope, the returned object is managed as a bean.
- A **bean definition** may not yet have an instance at a given point in time, may have a single shared instance, or may produce multiple instances depending on **scope** and instantiation policy.
- Bean name, class name, and object are **three distinct layers of identity**. You should not say "one Java class = one bean = one instance."

**Mental model:** the blueprint/ingredients (definition) instruct how to build a product; the concrete product (instance) is the actual result. This is only an analogy: the container can also process dependencies, post-processors, proxies, and lifecycle callbacks before supplying the instance.

## 2. What Information Does a Bean Definition Contain?

Spring represents bean metadata with APIs such as `org.springframework.beans.factory.config.BeanDefinition`. Typical information:

| Information group | Purpose | Example |
| --- | --- | --- |
| Bean identity | Lookup by name and alias, identifying which registration | `userService`, `mainService` |
| Type/creation method | Class, constructor/factory method, factory object, supplier | `UserService.class`, `@Bean` method |
| Dependencies | Other beans the object needs to be created/configured | `UserRepository` passed via constructor |
| Scope | Controls the count/frequency of instance provisioning | `singleton`, `prototype` |
| Lazy/eager | When the bean may be instantiated | `@Lazy` or singleton instantiation at refresh |
| Values/configuration | Properties, constructor arguments, autowiring metadata | URL, timeout, dependency reference |
| Lifecycle | Configured initialization/destruction callbacks | `initMethod`, `destroyMethod` |
| Auxiliary metadata | Configuration source, role, primary/candidate, etc. | Supports resolution and bean management |

**Not every definition stores every field identically.** Depending on the registration kind, part of the metadata lives in the bean definition and part is inferred from annotations or factory methods during container processing phases. Nor is it an ordinary business DTO object.

### How Do Names, Aliases, and Types Differ?

- With `@Bean`, the default name is **typically** the factory method name; for example, `userService()` creates a bean named `userService` (customizable via a bean-name generator or specifying `name`).
- `@Bean(name = {"userService", "mainService"})` registers one bean under a primary name and an alias. **An alias does not create a second definition or instance.**
- Two **different definitions** can produce two beans of the same class. Therefore a Spring singleton is **one instance per bean definition within one container** according to scope rules, not a single object of that class across the whole JVM.
- When retrieving a bean by type, if multiple compatible candidates exist without an appropriate selection rule, resolution can report ambiguity. `@Primary` or `@Qualifier` solves dependency selection, not creating a second object.

A registered `BeanDefinition` can be inspected via `ConfigurableListableBeanFactory.getBeanDefinition(name)` in an appropriate context; that retrieves **metadata**, not an object lookup call like `getBean(name)`.

## 3. From Definition to Instance: How Does the Process Unfold?

Conceptual diagram (specific implementations/extension points may add extra steps):

~~~text
Configuration source
@Configuration / @Bean / @Component scan / XML / programmatic registration
                 |
                 v
  Parse and register BeanDefinition
                 |
                 v
  BeanFactoryPostProcessor may process metadata
                 |
                 v
  Determine scope, lazy, dependencies, and creation conditions
                 |
                 v
  Factory/constructor creates the actual Java object
                 |
                 v
  Inject/configure, BeanPostProcessor, init callbacks
                 |
                 v
  Container supplies bean reference to callers
                 |
                 v
  Context closes or scope ends: appropriate callbacks
~~~

A few key points:

1. The container **reads configuration** and registers bean definitions; a definition is a creation recipe, **not identical** to a created object.
2. Spring **resolves dependencies** before or during bean creation and configuration. Constructor injection, `@Bean` factory method parameters, and property injection are common mechanisms.
3. The container invokes the constructor or factory method, may apply `BeanPostProcessor`s, creates proxies when configuration requires, and then runs appropriate initialization callbacks before the application uses the bean.
4. When calling `getBean`, what is returned is the **bean object/reference** supplied by the container. When proxying is involved, the returned object may be a **proxy** whose runtime class differs from the target class; do not assume `getClass()` always equals the original class.
5. Having a definition **does not guarantee** bean creation will succeed: missing dependencies, ambiguity, constructors throwing exceptions, or unresolvable circular dependencies can all cause bootstrap/lookup to fail.

### Two Extension Points Often Confused

- `BeanFactoryPostProcessor` primarily operates on **bean-definition metadata** before regular beans are instantiated.
- `BeanPostProcessor` processes **bean instances** during initialization phases. It may return a replacement object or a proxy according to the applicable contract.

Avoid calling `getBean()` indiscriminately inside a metadata post-processor: doing so can force premature instantiation and cause certain post-processing steps not to run as expected.

## 4. How Many Instances Can One Definition Correspond To?

**Scope** determines a critical part of the relationship between a bean definition and its instances.

| Scope | Typical rule | Calling `getBean()` twice |
| --- | --- | --- |
| `singleton` (default) | One shared instance per bean definition within one IoC container | Returns the same bean reference (barring special lookup mechanisms) |
| `prototype` | Container creates/configures a new instance each time the bean is requested | Typically returns two distinct instances |
| `request` | One bean instance scoped to a single HTTP request | Depends on current request; requires a web-aware context |
| `session` | Bound to an HTTP session | Depends on current session; requires a web-aware context |
| Custom scope | Follows rules declared by the application | Cannot be inferred without knowing the custom scope |

A **prototype bean definition** is *one recipe capable of creating many objects*; it does not mean multiple definitions are automatically generated.

**Spring's singleton differs from GoF Singleton:** the same class can have multiple singleton beans if multiple definitions or multiple contexts are registered. In particular, Spring does not ensure objects created via `new` outside the container share anything with a singleton bean.

**Lifecycle:** the container typically manages destroying eligible singletons when closing the context; for prototypes, Spring normally **does not automatically invoke full destruction callbacks** after handing the instance to the caller. For prototypes holding closeable resources, the consumer must have an appropriate cleanup strategy.

### Lazy Does Not Mean Prototype

- **Non-lazy** singletons in an `ApplicationContext` are typically pre-instantiated when the context refreshes.
- A singleton bean annotated with `@Lazy` is typically created when first actually needed; **the definition can exist before the instance**.
- If a `@Lazy` singleton is a required dependency of an eager singleton, it may still be created during startup to satisfy that dependency.
- `@Lazy` does not change scope to prototype. Lazy decides **timing**; scope decides **sharing/instance count**.

## 5. Where Are Definitions Registered From?

Spring offers several ways to declare beans. The short examples in this section illustrate **syntax**, not standalone runnable Java files.

### Approach A — Java Configuration with `@Bean`

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    PaymentService paymentService(PaymentRepository repository) {
        return new PaymentService(repository);
    }
}
~~~

The snippet above assumes `PaymentService`, `PaymentRepository`, a `PaymentRepository` bean, and the relevant Spring imports already exist. When the context reads `AppConfig`, it registers a definition for `paymentService`; at instantiation time, Spring resolves `repository` according to injection rules.

`@Configuration(proxyBeanMethods=false)` fits when **not calling `@Bean` methods directly to obtain beans via interception**; in this mode a plain Java call to a factory method may create a new object outside the container's singleton lookup. Use `@Bean` parameters or constructors to express dependencies clearly.

### Approach B — Component Scanning

~~~java
@Component
class EmailSender {
    void send(String message) {
        System.out.println(message);
    }
}
~~~

The class only becomes a bean if the context has **registered/scanned the package** containing it via `@ComponentScan`, `context.scan(...)`, or an equivalent configuration mechanism. The annotation alone does not make the whole JVM aware of the bean.

### Approach C — XML or Programmatic Registration

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">
    <bean id="emailSender" class="demo.EmailSender" scope="singleton"/>
</beans>
~~~

This is a **syntactically standalone XML configuration** example, not used to run the Java program in section 6. Programmatic registration can also use `GenericApplicationContext` / `BeanDefinitionRegistry` and appropriate bean definition APIs. All of these approaches provide **metadata/registration to the container**; there is no need to turn every object into a component-scanned class.

## 6. Standalone Example: Observing Definitions, Singletons, Prototypes, and Aliases

This is a **plain Spring Framework** program requiring no Spring Boot, database, or HTTP server. It clearly demonstrates: metadata exists **before querying a lazy instance**, an alias does not create a second definition, singletons are reused, and prototypes create new instances.

### 6.1. Requirements and Project Structure

Requires **JDK 17+**, **Maven 3.9+**, and internet on the first run to download dependencies. Spring Framework **7.0.9** keeps a Java 17 baseline; the example pins the version to minimize differences when re-running.

~~~text
bean-definition-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanDefinitionDemo.java
~~~

### 6.2. File `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-definition-demo</artifactId>
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
                    <mainClass>demo.BeanDefinitionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` pulls in the required Spring modules through the Maven dependency graph; you do not need to download individual `spring-beans` JARs manually. Maven Compiler Plugin invokes the Java compiler targeting release 17, and Exec Plugin runs the `main` class with the dependency classpath.

### 6.3. File `src/main/java/demo/BeanDefinitionDemo.java`

~~~java
package demo;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Scope;

public final class BeanDefinitionDemo {
    private BeanDefinitionDemo() {
    }

    public static final class CatalogRepository {
        static int created;
        private final int id;

        CatalogRepository() {
            id = ++created;
        }

        int id() {
            return id;
        }
    }

    public static final class ReportJob {
        static int created;
        private final int id;
        private final CatalogRepository repository;

        ReportJob(CatalogRepository repository) {
            this.repository = repository;
            id = ++created;
        }

        int id() {
            return id;
        }

        CatalogRepository repository() {
            return repository;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean(name = {"catalogRepository", "catalogAlias"})
        @Lazy
        public CatalogRepository catalogRepository() {
            return new CatalogRepository();
        }

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public ReportJob reportJob(CatalogRepository repository) {
            return new ReportJob(repository);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            BeanDefinition definition =
                    context.getBeanFactory()
                            .getBeanDefinition("catalogRepository");

            System.out.println("definitionExists="
                    + context.containsBeanDefinition("catalogRepository"));
            System.out.println("aliasIsBean="
                    + context.containsBean("catalogAlias"));
            System.out.println("aliasIsDefinition="
                    + context.containsBeanDefinition("catalogAlias"));
            System.out.println("definitionLazy="
                    + definition.isLazyInit());
            System.out.println("repositoryCountBeforeGet="
                    + CatalogRepository.created);

            CatalogRepository first =
                    context.getBean(CatalogRepository.class);
            CatalogRepository second =
                    context.getBean("catalogAlias", CatalogRepository.class);

            System.out.println("repositoryCountAfterGet="
                    + CatalogRepository.created);
            System.out.println("sameSingleton=" + (first == second));

            BeanDefinition reportDefinition =
                    context.getBeanFactory().getBeanDefinition("reportJob");
            System.out.println("reportScope="
                    + reportDefinition.getScope());

            ReportJob reportA = context.getBean(ReportJob.class);
            ReportJob reportB = context.getBean(ReportJob.class);

            System.out.println("samePrototype=" + (reportA == reportB));
            System.out.println("reportIds="
                    + reportA.id() + "," + reportB.id());
            System.out.println("bothUseSameRepository="
                    + (reportA.repository() == first
                    && reportB.repository() == first));
        }
    }
}
~~~

**Run inside the `bean-definition-demo` directory containing `pom.xml`:**

~~~bash
java -version
mvn -version
mvn -q compile exec:java
~~~

The command `mvn -q compile exec:java` runs the compiler per Maven configuration and then executes the program. Do not run `java demo.BeanDefinitionDemo` directly from the project directory without configuring the full library classpath.

**Exact stdout of the 11 `System.out.println` statements in the application** (excluding output from `java -version`, `mvn -version`, and logs/diagnostics that Maven or a logging backend may emit):

~~~text
definitionExists=true
aliasIsBean=true
aliasIsDefinition=false
definitionLazy=true
repositoryCountBeforeGet=0
repositoryCountAfterGet=1
sameSingleton=true
reportScope=prototype
samePrototype=false
reportIds=1,2
bothUseSameRepository=true
~~~

Each time the program runs in a fresh JVM, the `static created` fields start at 0. These counters are an illustrative tool for the example, not a default Spring property.

### 6.4. Explaining Each Result

1. `containsBeanDefinition("catalogRepository")` returns `true`: the context has registered the bean's metadata.
2. `containsBean("catalogAlias")` is `true` because the alias points to a known registration; `containsBeanDefinition("catalogAlias")` is `false` because an alias **is not a separate definition**.
3. `definition.isLazyInit()` is `true`: the `@Lazy` annotation specifies deferred singleton creation. Before lookup, `CatalogRepository.created=0` because no eager bean needed this instance yet.
4. Looking up twice—by type and by alias—yields the **same object** for the singleton; the constructor ran only once, so the counter is 1.
5. The `reportJob` bean has `prototype` scope; two calls to `getBean(ReportJob.class)` create two `ReportJob` objects with ids 1 and 2, so `==` returns `false`.
6. Both prototypes are injected with the **same `CatalogRepository` singleton** via the `reportJob` factory method parameter. Therefore `bothUseSameRepository=true`.

A few details to read the results accurately: `getBeanDefinition(...)` returns **metadata**, while `getBean(...)` returns the **object**; `getScope()` on a bean without an explicit `scope` declaration may return an empty string (meaning default singleton), not necessarily the literal string `singleton`. That is why the example deliberately prints the scope of the prototype bean, which has an explicit value.

## 7. How Do Bean Instances Differ from Manually Created Objects?

Consider three cases:

| How the object is created/obtained | Corresponding bean definition in context? | Who manages its lifecycle? |
| --- | --- | --- |
| `context.getBean(CatalogRepository.class)` | Yes, in the example's context | Spring manages the bean per scope/callbacks |
| `new CatalogRepository()` in app code outside Spring | No, not from a standalone `new` | The creating code is responsible |
| `new CatalogRepository()` inside a `@Bean` factory method | Definition provided by `@Bean`; returned object is managed | Spring takes ownership of the **returned object** as a bean |

Not every object created inside a factory method becomes a bean. If a factory creates a temporary `helper` object and returns a different object, `helper` does not automatically become a bean unless registered.

**Object references and bean names are not one-to-one either:**

- The same bean can have **multiple aliases**, yet only one singleton instance is provided for that registration.
- The same class can have **multiple bean definitions**, with each singleton definition having its own instance.
- The same prototype bean definition can produce **multiple instances**.
- Proxies/AOP can cause the reference returned by Spring to point to a proxy; do not use `getClass()` or `new` as the sole test for whether an object is managed by Spring.

**Spring does not alter Java's `new` rules.** Spring only defines how objects within the container's scope are registered, created/configured, and managed.

## 8. Creation Timing, Lifecycle, and Boundaries to Remember

At an introductory level, a bean's lifecycle is typically learned via this model:

~~~text
BeanDefinition becomes active
          |
          v
  Resolve dependencies
          |
          v
  Constructor/factory method
          |
          v
  Inject/configure + appropriate post-processing
          |
          v
    Init callbacks
          |
          v
  Bean is placed into use
          |
          v
  End of scope / context close
          |
          v
  Destroy callbacks if supported by scope
~~~

You can use `@Bean(initMethod = "start", destroyMethod = "stop")` when a class has appropriate methods for the container to invoke during its lifecycle; for annotation-based components, callbacks like `@PostConstruct`/`@PreDestroy` belong to the **`jakarta.annotation`** namespace in modern Spring generations.

**Especially common pitfalls:**

- An `ApplicationContext` normally creates **non-lazy** singletons during refresh; do not assume calling `getBean` is always the first time the constructor runs.
- `@Lazy` may not defer a bean if an eager singleton requires that dependency right at bootstrap.
- Prototype beans are created on each request; Spring does not automatically execute full destruction callbacks after handing a prototype to the caller. If the bean holds connections/files/sockets, the caller needs a cleanup strategy.
- Injecting a prototype into a **singleton's constructor** does not automatically supply a new dependency on every method call on the singleton; injection typically happens once when the singleton is created. If you want a fresh prototype per use, an appropriate lookup/provider mechanism is needed.
- `context.close()` is not synonymous with immediate Java garbage collection. It triggers appropriate lifecycle/shutdown callbacks; if references remain alive, Java objects can still stay in memory.
- Bean registration fails when metadata/dependencies are missing or invalid, on ambiguity, when constructors throw exceptions, or on unresolvable constructor cycles. Do not treat a `BeanDefinition` as proof that an instance was successfully created.

### When to Inspect Definitions vs. Retrieve Instances?

- Inspect `BeanDefinition`, scope, lazy, and source metadata when **debugging container configuration** or building extension tools. Typically work through `ConfigurableListableBeanFactory`/registry during the proper phase.
- Use dependency injection and receive real objects via constructors/`@Bean` parameters when **writing business logic**. Avoid scattering `context.getBean` in every service, which turns services into service locators and makes testing harder.
- Use `getBean` deliberately at bootstrap, in test harnesses, plugin lookups, or for dynamic lookup needs; keep scope and object creation cost in mind.
- Do not arbitrarily mutate bean definitions **after the context has created singletons**: changing metadata at that point does not automatically recreate existing beans or update already-injected references.

## 9. Common Errors When Confusing Definitions with Instances

| Misconception | Accurate explanation |
| --- | --- |
| "One `@Bean` method equals one object created immediately" | It is a bean definition source; instantiation timing depends on scope/lazy/dependencies/refresh |
| "`BeanDefinition` is the bean object itself" | A definition is metadata; an instance is the actual object |
| "A Java class always has only one Spring bean" | You can register multiple definitions of the same class, or none at all |
| "Two bean names always mean two objects" | One could be an alias for the same bean, creating no new object |
| "Prototype means multiple definitions automatically" | One definition can produce multiple instances |
| "Singleton means one object across all Spring contexts/JVM" | Default scope is per **container + bean definition** |
| "Adding `@Component` always makes Spring see that class" | Requires proper scanning/registration in the context |
| "Calling a `@Bean` method directly always returns the singleton bean" | With `proxyBeanMethods=false`, a direct Java call is still a plain method call |
| "Having a `BeanDefinition` guarantees the bean can be instantiated" | Bean creation can fail due to dependencies/config/constructors |
| "Closing the context destroys all Java objects" | Spring only runs appropriate lifecycle callbacks; objects/references and GC follow Java rules |

**Common troubleshooting case:** two different `EmailSender` definitions exist, yet a consumer injects a single `EmailSender` without specifying a candidate. Determining the right bean can become ambiguous and fail when creating the dependent bean. Do not try to fix this by randomly renaming Java classes; check bean names, types, `@Qualifier`, `@Primary`, factory methods, and scan configuration.

## 10. Self-Check Exercises

Perform each change **on a copy** and restore the original code between exercises to compare stdout accurately.

1. **Remove `@Lazy`** from `catalogRepository()`: predict `repositoryCountBeforeGet` and why. With default eager singletons in the current context, it usually becomes `1` right after context creation finishes.
2. **Change `reportJob` scope back to singleton** by removing `@Scope`: predict `samePrototype` (it will be `true`) and `reportIds` (typically `1,1`). Since the name `samePrototype` no longer fits, rename the label meaningfully.
3. **Remove the `catalogAlias` alias** from `@Bean(name=...)`: predict what `containsBean("catalogAlias")` and `getBean("catalogAlias", ...)` will do. You can verify via `NoSuchBeanDefinitionException`.
4. **Add another `@Bean` of type `CatalogRepository` with a different name**: observe why `getBean(CatalogRepository.class)` becomes ambiguous. Try `@Qualifier` or looking up by bean name.
5. **Create `new CatalogRepository()` directly outside the context**: does the static counter increase? Do Spring definitions/aliases change? Why doesn't that object automatically belong to the container?
6. **Try placing stateful mutable fields in a singleton instance**: describe the risks when multiple threads share it, and why scope **does not** automatically guarantee thread safety.
7. **Close the context while keeping a reference**: distinguish lifecycle callbacks from object GC, avoiding the claim that objects are deleted immediately on `close()`.

### Self-Assessment

You have mastered the lesson if you can explain without guessing:

- [ ] What is a bean definition, and how does it differ from a class, a bean name, and a bean instance?
- [ ] What different questions do `containsBeanDefinition`, `getBeanDefinition`, `containsBean`, and `getBean` answer?
- [ ] How many instances does a singleton definition vs. a prototype definition create/supply?
- [ ] Why does an alias not create an additional bean instance?
- [ ] Why do `@Lazy` and scope answer **two different questions**?
- [ ] What concrete evidence in stdout proves the definition exists before the singleton instance?
- [ ] How can changing a `@Bean` factory method affect the dependency graph and lifecycle?

## 11. Summary and Official Documentation

**Core takeaways:**

- **Bean definition = metadata/recipe.**
- **Bean instance = actual object created and supplied according to scope.**
- **Spring bean = object managed by the IoC container** within an appropriate registration/context.
- Definitions can exist before instances; singletons typically share one instance, while prototypes provide a new instance per request.
- Bean names and aliases are lookup identifiers, not object counts.
- `BeanFactory`/registries manage metadata, while `ApplicationContext` bootstraps and runs the application; prefer DI over calling `getBean` everywhere.

Official documentation for further verification:

- [Spring – Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
- [Spring – Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring – Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html)
- [Spring – Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring – Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)

**Conclusion:** Do not confuse "Spring **knows how to create** a bean" with "Spring **has already created** an object," nor confuse bean names with instances. Clearly distinguishing `BeanDefinition` from bean instances is the foundation for understanding dependency injection, scopes, lazy loading, proxies, lifecycles, and Core Container debugging.