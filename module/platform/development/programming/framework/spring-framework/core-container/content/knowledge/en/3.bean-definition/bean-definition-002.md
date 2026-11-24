# Bean Class, Constructor, and Factory Method in Spring Bean Definitions

## 1. What Information Is Used to Create a Bean?

In the Spring Core Container, a **bean definition** is metadata telling the container how to create and manage a bean. A bean definition is typically associated with an **implementation class**, an **object creation mechanism**, **dependencies/arguments to supply**, a **scope**, and **lifecycle configuration**. This lesson focuses on three ways to specify the *creation mechanism*:

1. **Bean class + constructor:** Spring directly invokes a class constructor while resolving the constructor parameters that need to be injected.
2. **Static factory method:** Spring invokes a `static` method responsible for returning the object to be registered as a bean.
3. **Instance factory method:** Spring invokes a method on **an existing factory object** to create the object to be registered as a bean.

With Java configuration, `@Bean` is usually the most intuitive way to express a factory method. With XML-style bean definitions, the `class`, `factory-method`, and `factory-bean` attributes express the corresponding creation paths. Choosing the right mechanism helps manage object creation, configuration, and lifecycle without scattering `new` across business classes.

~~~text
                    Bean definition / configuration
                              |
         +--------------------+--------------------+
         |                    |                    |
       class              static factory       instance factory
         |                    |                    |
    constructor()       SomeFactory.create()   factoryBean.create()
         |                    |                    |
         +--------------------+--------------------+
                              |
                        bean instance
                              |
                scope / dependency / lifecycle
~~~

The diagram shows **three paths for creating a bean**; it does not mean every bean must use all three. Spring can still apply post-processors, proxies, and lifecycle callbacks depending on the configured features.

## 2. Distinguishing Bean Class, Java Object, and Bean Definition

Plain Java class example:

~~~java
public final class GreetingService {
    private final Formatter formatter;

    public GreetingService(Formatter formatter) {
        this.formatter = formatter;
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
~~~

This is an **illustrative snippet**, not standalone because the `Formatter` interface is not defined here; the full runnable example is in Section 6.

- **Bean class** is the class type Spring can use to create an object, such as `GreetingService`. It does not automatically become a bean just because the class is on the classpath.
- **Bean definition** is the information registered with the container so Spring knows whether to create that object via constructor or factory and how to wire dependencies.
- **Bean instance** is the actual object returned by `getBean(...)`. The runtime object may be a proxy if certain extension mechanisms are enabled.
- **Bean name** is the registration identifier, such as `greetingService`; **bean type** is the Java type used for checking and autowiring. The bean name and class name do not necessarily match.

`new GreetingService(formatter)` creates a Java object on its own, but that object **does not automatically become a Spring-managed bean** unless you register that instance or a corresponding definition with the container.

Bean metadata can also contain `scope`, `lazy-init`, `init-method`, `destroy-method`, or equivalent configuration sources. Those details **do not replace** the constructor/factory method; rather, they supplement the container context that manages the object.

## 3. Approach 1 — Spring Instantiates Directly via Constructor

### 3.1. Constructor Injection

Suppose a `Formatter` bean and a bean definition for `GreetingService` already exist. With a single constructor:

~~~java
public GreetingService(Formatter formatter) {
    this.formatter = java.util.Objects.requireNonNull(formatter);
}
~~~

Spring can resolve the parameter of type `Formatter` and then create `GreetingService` using that constructor. In a class with **only one constructor**, since Spring Framework 4.3 it is generally unnecessary to place `@Autowired` on the constructor for constructor injection to work.

A bean definition can be created through several paths:

- `@Component` + component scanning: Spring discovers the class and creates the bean from the appropriate constructor.
- `AnnotationConfigApplicationContext.register(GreetingService.class)`: registers the class explicitly before refresh; no package scanning is needed.
- XML `<bean class="...">` with constructor argument configuration.
- Low-level `BeanDefinitionRegistry` and `RootBeanDefinition`/`BeanDefinitionBuilder` APIs.

**Important:** constructor injection is about **supplying dependencies to a constructor**. It can be used even without Spring; Spring simply handles selecting/providing arguments and invoking the constructor in place of a manual composition root.

### 3.2. Default Constructor and Multiple Constructors

A class does not have to have a no-argument constructor. Spring can invoke a parameterized constructor when it has a way to determine the constructor and resolve the appropriate dependencies. However:

- If a class has **multiple constructors**, selection rules may require `@Autowired`, explicit bean definition configuration, or a clearer design.
- If a dependency bean is missing, or multiple candidates exist without disambiguation, Spring may fail immediately when creating the bean.
- If the constructor throws an exception, bean creation fails and is typically wrapped in an error chain related to `BeanCreationException`.
- `private` constructors, `abstract` classes, non-instantiable types, and visibility rules have their own rules/limitations; do not assume every class is instantiated by the container in the same way.
- `@Autowired(required = false)` or overloaded constructors should not become a way to hide required dependencies; a single clear constructor is usually easier to maintain.

**Do not mix responsibilities:** a constructor should establish invariants and receive dependencies; avoid performing complex I/O or long-running side effects during bean instantiation. An eager singleton may be instantiated during context refresh, before any business method is called.

### 3.3. Constructor-Based XML Bean Definition

**Structural illustration** XML snippet, assuming `demo.GreetingService` and `demo.Formatter` are valid types in another project:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://www.springframework.org/schema/beans
                           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="formatter" class="demo.SimpleFormatter"/>

    <bean id="greetingService" class="demo.GreetingService">
        <constructor-arg ref="formatter"/>
    </bean>
</beans>
~~~

Here `class` specifies the class to be instantiated by Spring; `constructor-arg ref` indicates that the dependency is the `formatter` bean. XML is not mandatory: `@Configuration`, `@Bean`, or component registration can express the same intent in Java.

## 4. Approach 2 — Static Factory Method

Sometimes a class needs to be created via a `static` method instead of calling a constructor directly. Common situations:

- The class has a hidden constructor and a public static factory, such as `SomeClient.create(config)`.
- The creation method needs to choose one of several implementations while returning a stable contract.
- You want to use a library's factory API without modifying the library's code.

Plain Java example:

~~~java
public final class Formatter {
    private final String prefix;

    private Formatter(String prefix) {
        this.prefix = prefix;
    }

    public static Formatter of(String prefix) {
        return new Formatter(prefix);
    }

    public String format(String name) {
        return prefix + " " + name;
    }
}
~~~

This is an **illustrative snippet**. With normal Java code creation, you call `Formatter.of("Hello")` instead of `new Formatter("Hello")`. If using the corresponding XML bean definition:

~~~xml
<bean id="formatter"
      class="demo.Formatter"
      factory-method="of">
    <constructor-arg value="Hello"/>
</bean>
~~~

In this configuration, `class` is the **class containing the static factory method**, `factory-method` is the name of the creation method, and `constructor-arg` can be used to pass arguments to the factory method. The returned object is what becomes the managed bean under this bean definition.

### Static `@Bean` in Java Configuration

Spring allows declaring a `static` `@Bean` method:

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    public static Formatter formatter() {
        return Formatter.of("Hello");
    }
}
~~~

This is an **illustrative example** using `Formatter` from above; Section 6 provides a complete runnable program. A `@Bean static` method belongs to the configuration class and does not need an `AppConfig` instance to be invoked as a Java method. Spring still registers the **returned object** as a bean.

**Do not confuse two things:**

1. **Factory method of an XML bean definition:** uses `class + factory-method` pointing to a static method on the creating class.
2. **Static method annotated with `@Bean`:** Spring reads the annotation in `@Configuration` and uses that method as the bean factory method.

They express the factory idea but are **two different configuration declaration styles**. A `@Bean` method can directly call a library's static factory method, such as `return Formatter.of("Hello")`.

## 5. Approach 3 — Instance Factory Method

Instead of a static method, you have an already-created factory object:

~~~java
public final class FormatterFactory {
    private final String prefix;

    public FormatterFactory(String prefix) {
        this.prefix = prefix;
    }

    public Formatter createFormatter() {
        return Formatter.of(prefix);
    }
}
~~~

This snippet is **illustrative**, assuming `Formatter` already exists. Here the creation method depends on the **state/configuration of the factory instance**.

XML example:

~~~xml
<bean id="formatterFactory" class="demo.FormatterFactory">
    <constructor-arg value="Hello"/>
</bean>

<bean id="formatter"
      factory-bean="formatterFactory"
      factory-method="createFormatter"/>
~~~

Meaning:

1. Spring creates `formatterFactory` as a separate bean.
2. When `formatter` is needed, Spring calls `createFormatter()` **on that factory bean**.
3. The object returned by the factory is managed under the bean name `formatter`.

In this instance-factory declaration style, **`factory-bean` points to the *bean name holding the factory instance***, unlike `class` for a static factory. You should not write `factory-bean="demo.FormatterFactory"` unless a bean with that literal string name exists.

### Instance Method Annotated with `@Bean`

In Java configuration, the more common approach is:

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    Formatter formatter() {
        return Formatter.of("Hello");
    }
}
~~~

The `formatter()` method is an **instance factory method of the configuration class**. Spring manages invoking it and registering the returned object. This is not identical to manually specifying a method name in XML, though both serve the role of creating beans.

A `@Bean` method can also accept dependencies as parameters:

~~~java
@Bean
GreetingService greetingService(Formatter formatter) {
    return new GreetingService(formatter);
}
~~~

Spring resolves the `Formatter` bean and passes it into the **factory method parameter**. This is also dependency injection, even though the constructor call occurs inside the `@Bean` method body.

### Comparing the Three Approaches

| Bean creation approach | What does the configuration specify? | Who executes the creation call? |
| --- | --- | --- |
| Direct constructor | Bean class + constructor arguments | Container selects/invokes the constructor |
| Static factory | Class with static method + method/arguments | Container invokes the static factory |
| Instance factory | Existing factory bean + instance method/arguments | Container obtains the factory bean and invokes the method |
| `@Bean` Java method | Method in configuration, either static or instance | Container invokes the `@Bean` method and manages the return value |

No single mechanism is "right" for every bean. **Choose the simplest creation approach that fits the API of the class you need to use.**

## 6. Complete Runnable Spring Framework 6.2 / Java 17 Program

This single example intentionally uses **all three paths** in one context:

- `GreetingService` is created directly by Spring via its **constructor**.
- `Phrase` is provided via a **static `@Bean` factory method**.
- `GreetingFormatter` is provided via an **instance `@Bean` factory method**, which internally calls a plain Java static factory.

There is no Spring Boot, web server, database, or AOP. The run command uses Maven to download `spring-context`.

### 6.1. Directory Structure

~~~text
bean-creation-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanCreationDemo.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>bean-creation-demo</artifactId>
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
                    <mainClass>demo.BeanCreationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. Complete Java File

Create `src/main/java/demo/BeanCreationDemo.java`:

~~~java
package demo;

import java.util.Objects;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class BeanCreationDemo {
    private BeanCreationDemo() {
    }

    public record Phrase(String prefix) {
        public Phrase {
            Objects.requireNonNull(prefix, "prefix");
            if (prefix.isBlank()) {
                throw new IllegalArgumentException("prefix must not be blank");
            }
        }
    }

    public static final class GreetingFormatter {
        private final Phrase phrase;

        private GreetingFormatter(Phrase phrase) {
            this.phrase = Objects.requireNonNull(phrase, "phrase");
        }

        // Java static factory: constructor is hidden from callers.
        public static GreetingFormatter create(Phrase phrase) {
            return new GreetingFormatter(phrase);
        }

        public String format(String name) {
            Objects.requireNonNull(name, "name");
            return phrase.prefix() + " " + name;
        }
    }

    public static final class GreetingService {
        private final GreetingFormatter formatter;

        // Single constructor: Spring can inject this dependency.
        public GreetingService(GreetingFormatter formatter) {
            this.formatter = Objects.requireNonNull(formatter, "formatter");
        }

        public String greet(String name) {
            return formatter.format(name);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        // @Bean static factory method.
        @Bean
        public static Phrase phrase() {
            return new Phrase("Hello");
        }

        // @Bean instance factory method, with parameter injected by Spring.
        @Bean
        public GreetingFormatter greetingFormatter(Phrase phrase) {
            return GreetingFormatter.create(phrase);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // Register regular class so Spring instantiates it via constructor.
            context.register(AppConfig.class, GreetingService.class);
            context.refresh();

            GreetingService service = context.getBean(GreetingService.class);
            System.out.println("MESSAGE " + service.greet("Lan"));
            System.out.println("PHRASE "
                    + context.getBean(Phrase.class).prefix());
            System.out.println("FACTORY "
                    + context.getBean(GreetingFormatter.class).format("Mai"));
            System.out.println("SINGLETON "
                    + (service == context.getBean(GreetingService.class)));
        }
    }
}
~~~

### 6.3. Run Command and Stdout

From the `bean-creation-demo` directory containing `pom.xml`, requiring JDK 17+ and Maven:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

**Exact stdout lines printed by `BeanCreationDemo` in order:**

~~~text
MESSAGE Hello Lan
PHRASE Hello
FACTORY Hello Mai
SINGLETON true
~~~

`mvn -version` and Maven/plugins may print additional environment information or logs. The four lines above are the ones produced by `System.out.println` in the demo code; it is not guaranteed that the entire terminal output will always have only four lines.

### 6.4. Tracing Each Bean's Creation Path

1. `context.register(AppConfig.class, GreetingService.class)` registers both classes before calling `refresh()`. No component scan is needed.
2. Spring reads `@Configuration` and finds two `@Bean` methods.
3. Bean `phrase` is created by the `static Phrase phrase()` method returning a `Phrase("Hello")` record.
4. Bean `greetingFormatter` is created by the **instance** method `AppConfig.greetingFormatter(Phrase)`. Spring passes the registered `Phrase` into the parameter, and the method calls `GreetingFormatter.create(phrase)`.
5. Bean `GreetingService` is created via **constructor injection**, because the class was registered directly and has a single constructor accepting `GreetingFormatter`.
6. `getBean(GreetingService.class)` returns the service. `greet("Lan")` invokes the injected formatter and produces `Hello Lan`.
7. `getBean(Phrase.class)` and `getBean(GreetingFormatter.class)` both look up already-created beans; the third print statement illustrates that the factory returns the expected product type.
8. Since the default scope is `singleton` per context, the second lookup for `GreetingService` returns the same instance, printing `SINGLETON true`.
9. `try-with-resources` closes the context; any applicable destroy callbacks for managed beans are handled by Spring.

This is why the example can distinguish **creation mechanisms** without relying on the order of `println` calls inside constructors. Business output is printed after context refresh, so it does not depend on singleton creation order during startup.

### Why Doesn't `GreetingService` Need `@Component`?

`context.register(GreetingService.class)` registers the class directly with `AnnotationConfigApplicationContext`. The class is already an explicit bean candidate, even without `@Component`. If you remove that registration call and do not use another registration mechanism, Spring will not automatically create a `GreetingService` bean simply because the class exists in the project.

Another option is to annotate it with `@Component` and enable component scanning for the appropriate package, or add a `@Bean GreetingService service(GreetingFormatter formatter)`. You should avoid unintentionally using all three ways to register the same object, as that can create duplicate beans or name confusion.

## 7. Common Confusion: `@Bean` Factory Method vs. `FactoryBean<T>`

The two concepts have similar names but are not the same.

### `@Bean`

This is an annotation marking a factory method in a configuration class. Spring calls the method and manages the object the method returns:

~~~java
@Bean
GreetingFormatter greetingFormatter(Phrase phrase) {
    return GreetingFormatter.create(phrase);
}
~~~

The code is an excerpt from the program in Section 6. `@Bean` itself **does not require** the product class to implement any special Spring interface.

### `FactoryBean<T>`

`org.springframework.beans.factory.FactoryBean<T>` is a **specialized SPI**. A bean implementing `FactoryBean<T>` can provide a *product bean* via `getObject()`, while reporting `getObjectType()` and `isSingleton()`.

**Concept-illustrating example, not a standalone program:**

~~~java
class FormatterFactoryBean
        implements org.springframework.beans.factory.FactoryBean<GreetingFormatter> {

    public GreetingFormatter getObject() {
        return GreetingFormatter.create(new Phrase("Hello"));
    }

    public Class<?> getObjectType() {
        return GreetingFormatter.class;
    }

    public boolean isSingleton() {
        return true;
    }
}
~~~

If a Spring bean is registered as a `FactoryBean` under the name `formatterFactoryBean`, then:

- `getBean("formatterFactoryBean")` normally returns the factory's **product**.
- `getBean("&formatterFactoryBean")` retrieves **the factory bean itself**.

The `&` prefix is Spring's `FactoryBean` dereference convention. It has **no** relation to Java's bitwise operator in this case.

In particular, an **instance factory method** such as `factoryBean.createFormatter()` in XML **does not require** the factory object to implement `FactoryBean<T>`. They are two different APIs/configuration patterns.

**When do you need `FactoryBean`?** When you are writing framework-level integration/factory logic and want Spring to manage an intermediary object that produces products according to the SPI. For ordinary applications, `@Bean` or constructor injection is usually sufficient and easier to understand.

## 8. Return Type, Bean Name, and Dependencies at Creation Time

### Bean Type Is Not Necessarily the Concrete Type

~~~java
@Bean
MessageSender sender() {
    return new ConsoleSender();
}
~~~

This is an **illustrative** example; `MessageSender` and `ConsoleSender` are not defined. The `@Bean` method returns the `MessageSender` interface, though the instance may be `ConsoleSender`. Calling code should look up/inject by the **contract** when appropriate.

When selecting a bean by type, Spring relies on metadata from the bean definition/factory method and may need to instantiate the object to determine its concrete type. Do not assume pre-instantiation lookups always know every implementation subtype by reflecting on a concrete return type.

### Bean Name

By default with `@Bean`, the bean name is the method name: `phrase`, `greetingFormatter`. For directly registered classes, Spring names them according to component registration rules; the demo code does not rely on bean names and instead looks up by type.

### Constructor/Factory Method Arguments

Similar to constructor injection, Spring can supply parameters to a `@Bean` factory method from other beans:

~~~java
@Bean
GreetingFormatter greetingFormatter(Phrase phrase) {
    return GreetingFormatter.create(phrase);
}
~~~

Here `Phrase` must have a matching bean. If none exists, creating the `GreetingFormatter` bean fails. If two different `Phrase` beans exist without a valid disambiguation mechanism, injection may be ambiguous.

You should declare dependencies via parameters rather than calling `ApplicationContext.getBean(...)` indiscriminately inside the factory method body. In `@Configuration(proxyBeanMethods = false)`, **calling another `@Bean` method directly as a plain Java call does not necessarily refer to the managed singleton**, so method parameter injection is the clear choice.

## 9. Scope, Lifecycle, and Initialization Failures

- **`singleton` (default):** one bean instance per bean definition within **one container**, typically initialized during `ApplicationContext.refresh()` if not lazy. The factory method is normally invoked during creation of that instance, not on every lookup.
- **`prototype`:** typically creates a new instance each time the container receives a bean creation request; the factory method or constructor may be invoked multiple times matching the number of requests.
- **`@Lazy`:** can defer bean creation. If a lazy bean becomes a required dependency of another eager singleton, initialization timing still depends on the injection configuration.
- **Lifecycle:** the container can run initialization/destruction callbacks and bean post-processors according to its rules. You cannot infer that every object returned by a factory receives all features if that object is not managed as a bean.
- **Proxy:** when AOP or transactions are enabled, `getBean` may return a proxy, so the runtime type of the bean can differ from the originally created class.

### When a Constructor/Factory Throws an Exception

Example:

~~~java
@Bean
GreetingFormatter greetingFormatter(Phrase phrase) {
    if (phrase.prefix().isBlank()) {
        throw new IllegalArgumentException("Blank prefix");
    }
    return GreetingFormatter.create(phrase);
}
~~~

This is **illustrative**, not code from the runnable example in Section 6. If the factory method throws an exception, Spring cannot create the `greetingFormatter` bean and typically reports a bean creation error along with the root cause. For an eager singleton, the error can cause `refresh()` to fail before `getBean` is ever called.

### Two Common Anti-Patterns

1. **Unintentionally creating beans of the same class in multiple ways:** component-scanning `GreetingService`, also registering `@Bean GreetingService`, and also registering the class directly. This can produce multiple candidates and make type-based injection/lookup ambiguous.
2. **Putting business workflows in a factory method:** the factory body should focus on creating/configuring the object. Business processing flows belong in services, not running during container startup.

## 10. Common Errors and How to Handle Them

| Symptom | What to Check |
| --- | --- |
| `NoSuchBeanDefinitionException` on `getBean` | Is the class/`@Bean` registered in the right context? Is a profile/condition blocking it? |
| `NoUniqueBeanDefinitionException` | Are there multiple candidates of the same type? Specify `@Primary`, `@Qualifier`, or bean name |
| `UnsatisfiedDependencyException` | Which bean type required by the constructor/factory method is missing? |
| `BeanCreationException` | What did the constructor/factory/init method throw? Check the root cause |
| Cannot find a suitable constructor | Are there multiple constructors? Is autowiring/argument configuration right? |
| Factory method not found | Is it static or instance? Are method name/visibility/signature right? |
| XML `factory-bean` used like a class name | This attribute is the **bean name** of the factory instance |
| Confusing `@Bean` with `FactoryBean` | The first is an annotation for a factory method; the second is an SPI that produces products |
| Returning a class with a private constructor | Can be created via a public static factory if the API allows it |
| Manually calling a `@Bean` method in lite mode | A direct call is a plain Java call and may create an object outside the managed singleton |
| Calling `new` on a class and expecting Spring to manage it | Outside-container instances do not automatically get Spring metadata/lifecycle |
| Assuming a singleton bean is thread-safe | Scope does not guarantee safety for concurrent mutable state |
| Assuming Spring eliminates all `new` | Constructors and factory methods still create objects; Spring organizes where creation happens and manages lifecycle |

**Debug in the right order:** check the registered bean definition → creation mechanism (constructor/factory) → dependencies and scope → root exception at initialization → finally lookup. Do not fix a dependency issue by adding a duplicate bean before understanding the cause.

## 11. Exercises with Answers

**Exercise 1.** Class `GreetingService` has a single constructor accepting `GreetingFormatter`. If the class is registered and a `GreetingFormatter` bean exists, must you also write a no-arg constructor?

**Answer:** No. Spring can choose the single constructor and supply the matching dependency. A no-arg constructor is not a mandatory bean requirement.

**Exercise 2.** Why can `Formatter.of("Hello")` create an object even though `Formatter`'s constructor is private?

**Answer:** A static factory is a method inside the class, so it has access to that class's private constructor. The container can call the configured static factory instead of calling the private constructor directly.

**Exercise 3.** Does XML `factory-bean="formatterFactory"` mean calling a method on a class named `formatterFactory`?

**Answer:** No. `factory-bean` is the **name of a registered factory instance bean**; Spring invokes the instance method on that object.

**Exercise 4.** Why should `@Bean` and `FactoryBean` not be treated as synonyms?

**Answer:** `@Bean` marks a method that supplies an object. `FactoryBean<T>` is an SPI interface allowing a factory bean to supply a product via `getObject()` with its own dereferencing rules.

**Exercise 5.** In the example, `GreetingService` has no `@Component`, yet it can still be looked up. Why?

**Answer:** `context.register(GreetingService.class)` registers the class as a bean definition before `refresh()`. Component scanning is not the only registration method.

**Exercise 6.** When renaming `@Bean GreetingFormatter greetingFormatter(...)` to `@Bean GreetingFormatter createFormatter(...)`, what notable impact occurs?

**Answer:** The default bean name may change from `greetingFormatter` to `createFormatter`. Code looking up by type may still work if it is the sole candidate; code using the old bean name may fail.

**Exercise 7.** If the `GreetingFormatter` bean has prototype scope, does every call to `service.greet(...)` automatically receive a new formatter?

**Answer:** No. The singleton `GreetingService` is injected with one dependency at creation time, so it normally retains that reference. Supplying a fresh prototype per call requires an appropriate design/provider.

## 12. Checklist for Choosing and Defining Beans

- [ ] Identify the **product class** accurately and whether constructor/static/instance factory invocation is supported.
- [ ] Choose constructor injection when the class is under your control and dependencies are explicit.
- [ ] Choose a static factory if the class API requires it or offers a clear benefit.
- [ ] Choose an instance factory if creation relies on an already-configured factory object.
- [ ] When using `@Bean`, understand the method can be static or instance, and the return value is what becomes the managed bean.
- [ ] Do not confuse XML `factory-method`/`factory-bean` with the `FactoryBean<T>` interface.
- [ ] Register classes or configurations into the context; annotations/source code alone do not automatically create beans.
- [ ] Clarify bean name, return type, dependency arguments, and when the type is recognized.
- [ ] Verify singleton/prototype scope and its impact on how many times the constructor/factory runs.
- [ ] Avoid running complex business logic while the container is creating beans.
- [ ] Check for missing/ambiguous dependency errors and root exceptions.
- [ ] Use `getBean(Class<T>)` at application boundaries and constructor injection inside services.
- [ ] Write tests for bean configuration when multiple creation paths/implementations coexist.

**Conclusion:** **Bean class** describes the object type, while the **constructor or factory method** determines the object creation path. Spring stores that choice in the bean definition, wires dependencies, manages scope/lifecycle, and returns the bean to callers. Distinguishing constructors, static factories, instance factories, and `FactoryBean` helps configure the Spring Core Container accurately, testably, and without coupling to a specific library's object creation style.