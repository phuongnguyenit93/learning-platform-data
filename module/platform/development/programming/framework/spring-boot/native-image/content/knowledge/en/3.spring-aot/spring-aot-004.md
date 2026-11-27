# Generating Bean Registration, Instantiation, and Wiring Code with Spring AOT

In a Spring Boot application, a **bean** is an object managed by the Spring IoC container. When running on the JVM, Spring can scan annotations, analyze configuration classes, create `BeanDefinition`s, find constructors, resolve dependencies, and then instantiate beans at startup or on demand. This mechanism is flexible, but part of the work may have to be repeated every time the application starts and can rely on reflection or dynamic structures.

**Spring AOT (Ahead-of-Time)** translates information Spring can determine at **build time** into pre-generated Java code. That code describes how to **register beans**, how to **supply bean objects**, and how to **wire dependencies** for the container to use when the application runs. This is a critical link when compiling Spring Boot into a **GraalVM Native Image**, because reachability analysis needs to see the call paths and types that can appear.

This lesson focuses on three core operations: registering bean definitions, creating instances, and wiring beans together. At the same time, it points out which parts are prepared at build time, which parts still occur at runtime, and how to inspect AOT output.

## 1. Distinguishing the Three Operations

Three concepts are often lumped together as "Spring creating beans," yet they happen at different times and levels of abstraction:

| Operation | Role | Example | When It Happens |
|---|---|---|---|
| **Bean registration** | Provides the container a `BeanDefinition` containing name, type, scope, creation instructions, and required attributes | Registering the `paymentGateway` bean with an instance supplier | Registration code is **generated at build time**, while registering into the container is **executed at runtime** |
| **Bean creation** | Executes a supplier, constructor, or factory method to obtain an actual instance | Calling `new LocalPaymentGateway()` | Usually at runtime when the container initializes singletons or when a bean is requested |
| **Bean wiring** | Identifies and supplies dependent beans to constructors, factory methods, or other injection points | Supplying `PaymentGateway` to `PaymentService` | Dependency resolution paths can be **generated at build time**, while retrieving instances normally still occurs at runtime |

**Build-time generated code does not mean all bean objects are created at build time.** When the native executable starts, Spring still operates the container, creates singletons, applies scopes, runs lifecycle hooks, and resolves required dependencies according to the prepared configuration. Spring AOT primarily reduces structural discovery and inference work at runtime.

## 2. Why Does Spring Need to Generate Bean Code?

In standard mode, startup steps may include scanning `@Component`, `@Service`, `@Configuration`, reading `@Bean` methods, applying conditions, processing metadata, and inferring injection points. Some steps use reflection and can lead to many types or methods that cannot be fully identified from static Java calls.

Spring AOT converts the pre-determinable parts into explicit Java calls and registration data:

- The container can receive a set of `BeanDefinition`s prepared according to the build configuration.
- Generated instance suppliers express constructor or factory method calls more explicitly.
- Dependency wiring paths are described in easier-to-analyze code, rather than relying solely on runtime annotation lookup.
- Runtime hints can supplement reflection, proxy, serialization, or resource capabilities that generated code does not fully express.

For GraalVM Native Image, these explicit calls help **reachability analysis** recognize classes and methods that must be included in the executable. However, AOT does not guarantee all reflection is eliminated; some libraries and injection scenarios still require separate metadata.

## 3. Baseline Example: Application with Two Dependent Beans

Suppose a Spring Boot application has a payment gateway and a payment processing service:

~~~java
package example.payment;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

interface PaymentGateway {
    String authorize(String orderId);
}

final class LocalPaymentGateway implements PaymentGateway {
    @Override
    public String authorize(String orderId) {
        return "APPROVED:" + orderId;
    }
}

final class PaymentService {
    private final PaymentGateway gateway;

    PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    String pay(String orderId) {
        return gateway.authorize(orderId);
    }
}

@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new LocalPaymentGateway();
    }

    @Bean
    PaymentService paymentService(PaymentGateway gateway) {
        return new PaymentService(gateway);
    }
}
~~~

Assume `PaymentConfiguration` lies within component scan scope or is imported via `@Import` from the main application configuration. Spring recognizes two bean definitions:

- `paymentGateway`: declared type `PaymentGateway`, return value from factory method `paymentGateway()`.
- `paymentService`: type `PaymentService`, created by factory method `paymentService(PaymentGateway gateway)`.

The `PaymentGateway` dependency in the factory method parameter forms the edge connecting the two beans. Spring needs to find a bean matching the type before invoking the method that creates `paymentService`. Choosing `@Configuration(proxyBeanMethods = false)` is appropriate here because `@Bean` methods do not call each other directly; they receive dependencies via parameters provided by the container.

### Dependency Diagram

~~~mermaid
flowchart TD
    A["PaymentConfiguration"] --> B["BeanDefinition: paymentGateway"]
    A --> C["BeanDefinition: paymentService"]
    B --> D["LocalPaymentGateway instance"]
    D --> E["PaymentGateway dependency"]
    E --> F["PaymentService instance"]
    C --> F
    F --> G["Business method pay(orderId)"]
~~~

Arrows represent **creation and dependency-supply relationships**, not file generation order or a fixed instantiation schedule for every object. With lazy beans, prototypes, or supported runtime conditions, instance creation timing may vary.

## 4. Processing Flow from Java Source to AOT Registration Code

For Spring Boot configured with AOT, processing can be understood across these stages:

~~~mermaid
flowchart TD
    A["Source: @Configuration, @Bean, @Component, ..."] --> B["Run Spring AOT analysis"]
    B --> C["Determine bean/configuration structure"]
    C --> D["Generate BeanDefinition, instance supplier, container init code"]
    C --> E["Contribute required runtime hints"]
    D --> F["Compile AOT Java code"]
    E --> G["GraalVM reachability analysis"]
    F --> G
    G --> H["Native executable"]
    H --> I["Runtime: register beans and create instances when needed"]
~~~

This pipeline spans two time layers:

**Build time:** Spring initializes an AOT processing environment, applies relevant configuration processors, analyzes the bean system, and generates helper classes and metadata. When building natively, GraalVM then analyzes application code alongside AOT code and runtime hints.

**Runtime:** When the executable runs, AOT initialization code registers the prepared bean definitions into the container. The container instantiates beans according to scope and dependencies, executes supported lifecycle callbacks, and serves application requests.

The key point is that **AOT performs structural discovery early**, while **the IoC container remains responsible for managing object lifecycles**.

## 5. What Does Generated Bean Registration Code Look Like?

AOT code generated by Spring depends on the Spring Framework/Boot version, bean types, configuration, and participating AOT processors. Class names, method names, and APIs in generated files may change across versions. Therefore, the snippet below is **conceptual illustrative code**, not a verbatim copy of output from any specific Spring version:

~~~java
// CONCEPTUAL SIMULATION — not actual AOT source code.
void registerBeans(BeanDefinitionRegistry registry,
                   ConfigurableListableBeanFactory beanFactory,
                   PaymentConfiguration configuration) {

    RootBeanDefinition gatewayDefinition =
        new RootBeanDefinition(PaymentGateway.class);
    gatewayDefinition.setInstanceSupplier(
        () -> configuration.paymentGateway()
    );
    registry.registerBeanDefinition(
        "paymentGateway", gatewayDefinition
    );

    RootBeanDefinition serviceDefinition =
        new RootBeanDefinition(PaymentService.class);
    serviceDefinition.setInstanceSupplier(() -> {
        PaymentGateway gateway =
            beanFactory.getBean(PaymentGateway.class);
        return configuration.paymentService(gateway);
    });
    registry.registerBeanDefinition(
        "paymentService", serviceDefinition
    );
}
~~~

This simulation clarifies three ideas:

1. **Registration:** the container receives information about `paymentGateway` and `paymentService` before needing to create instances.
2. **Creation:** each `BeanDefinition` has an instance-supplying mechanism. Creation code can invoke the constructor or factory method directly.
3. **Wiring:** when creating `paymentService`, the container obtains the `PaymentGateway` dependency and passes it to the factory method.

In real generated files, Spring may use APIs like `BeanInstanceSupplier`, factory-method helpers, `__BeanDefinitions` classes, and aggregated registration code; do not use the simulation to guess exact class names or call ordering. The most reliable way to learn is to **open the generated sources in your own project**.

### How Does BeanDefinition Differ from Instance?

A `BeanDefinition` is like a "recipe" for creating a bean: it describes the bean and tells the container how to produce the object. The actual object appears only when the recipe is executed.

With the default `singleton` scope, Spring typically creates one instance per bean definition in the container and reuses that instance. With `prototype`, the container can invoke the creation mechanism multiple times on new requests. With `@Lazy`, instance creation may be deferred. These rules remain the container's runtime responsibility, even when the creation path was generated ahead of time.

## 6. How Does AOT Handle Dependency Wiring?

Spring AOT can generate code helping the container resolve identified injection points. However, **dependency resolution** still obeys Spring semantics:

| Declaration Style | What Spring Must Preserve |
|---|---|
| Constructor injection | Select the appropriate constructor and supply required objects |
| Parameters of `@Bean` method | Retrieve dependencies before calling the factory method |
| `@Qualifier` | Disambiguate beans when multiple candidates share the same type |
| `@Primary` | Prioritize a candidate when multiple matching beans exist |
| `ObjectProvider<T>` | Allow on-demand bean retrieval without forcing immediate creation of every dependency |
| `@Lazy` and scopes | Maintain bean creation timing and scope semantics |
| `@Autowired` on field/method | Process injection points, potentially introducing reflective access needs |

Consider the case of two payment gateways:

~~~java
@Bean("localGateway")
PaymentGateway localGateway() {
    return new LocalPaymentGateway();
}

@Bean("remoteGateway")
PaymentGateway remoteGateway() {
    return new RemotePaymentGateway();
}

@Bean
PaymentService paymentService(
        @Qualifier("localGateway") PaymentGateway gateway) {
    return new PaymentService(gateway);
}
~~~

This snippet extends the earlier example; `RemotePaymentGateway` is assumed to be defined. What AOT must capture is not just the `PaymentGateway` type, but also the **`localGateway` qualifier**. If generated code simply grabbed any bean matching the type, it would violate application semantics. Spring processes injection metadata to preserve bean selection criteria.

**Do not equate the dependency graph with a rigid initialization order list.** In Spring, dependencies can be lazy, optional, or queried via `ObjectProvider`. Constructor dependency cycles do not become valid because of AOT; the application must still resolve that dependency design issue.

## 7. What Does Spring AOT Process, and How Far Does It Go?

Common bean definition sources include:

- `@Component`, `@Service`, `@Repository`, `@Controller` within scan scope.
- `@Configuration` and `@Bean` methods.
- `@Import`, auto-configuration, and bean definitions created via configuration mechanisms supported by Spring AOT.
- Infrastructure components such as bean post-processors, proxies, transactions, or validation when the framework and libraries provide appropriate AOT integration.

Spring Framework offers extension points dedicated to AOT, notably **`BeanFactoryInitializationAotProcessor`** and **`BeanRegistrationAotProcessor`**. They allow the framework or libraries to contribute container initialization code or customize bean registration code generation. These are infrastructure-level mechanisms; regular applications should prefer standard Spring configuration before writing custom processors.

AOT cannot automatically infer every bean registration operation that happens purely dynamically after the application has been built. For instance, if runtime code reads a list of classes from an external data store and only then creates a `BeanDefinition` for each class, the actual bean set may fall outside what AOT prepared. Such scenarios require redesigning the extensibility mechanism or providing specialized AOT integration.

### Distinguishing AOT Code from Runtime Hints

- **Bean registration code** tells the container which beans exist and how to instantiate and wire them.
- **Runtime hints** additionally describe capabilities that Native Image must retain, such as constructors invoked via reflection, JDK proxies, resources, or serialization.
- **GraalVM reachability analysis** uses application code, AOT code, and metadata to determine what must be packaged into the native executable.

A properly registered bean **does not guarantee** that all reflection used by that bean itself will work. For example, `PaymentService` may be instantiated successfully, yet a library inside the service calling `Class.forName` with a class name from a request can still lack metadata in the native build.

## 8. Configuration, Profiles, and Conditions at Build Time

Spring AOT analyzes the context according to the **AOT processing environment**. This matters for `@Profile`, `@ConditionalOnProperty`, `@ConditionalOnClass`, and auto-configuration conditions.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
class GatewayConfiguration {

    @Bean
    @Profile("dev")
    PaymentGateway devGateway() {
        return new LocalPaymentGateway();
    }

    @Bean
    @Profile("prod")
    PaymentGateway prodGateway() {
        return new RemotePaymentGateway();
    }
}
~~~

If AOT processing runs with profile `prod`, the generated bean structure can differ from running with profile `dev`. **Do not assume changing `spring.profiles.active` when launching the native executable will create beans that were excluded during AOT processing.** Choose build profiles, properties, and conditions matching your deployment strategy, then test on the exact artifact produced.

Distinguish two groups of configuration:

1. **Configuration affecting bean structure**: changes candidates, bean conditions, bean types, or registration mechanisms. This group must be carefully evaluated during the AOT step.
2. **Values read by beans at runtime**: such as service URLs, timeouts, or credentials supplied when running. Depending on how the application uses them, these values can still change without altering bean structure.

There is no rule saying "every Spring Boot property is frozen at build time." What you must check is **whether that value participates in deciding the context structure for which AOT generated code**.

## 9. Observing AOT Code in a Project

With a Spring Boot project and its corresponding build plugin, you can ask Spring to run AOT processing without completing native compilation:

~~~bash
# Maven: Spring Boot Maven Plugin
./mvnw spring-boot:process-aot

# Gradle: Spring Boot Gradle Plugin
./gradlew processAot
~~~

On Windows, use the respective wrappers `mvnw.cmd` or `gradlew.bat`. When using these goals/tasks, ensure the Spring Boot plugin and Java version are configured compatibly. Common directories:

| Build tool | Common generated sources location |
|---|---|
| Maven | `target/spring-aot/main/sources` |
| Gradle | `build/generated/aotSources` |

Exact directory names and output structures may vary by version or build configuration. Inside generated sources, look for helper `BeanDefinitions` classes, `BeanFactoryRegistrations`, `BeanInstanceSupplier` creation, and `ApplicationContext` initialization code.

A helpful workflow for reading generated sources:

1. Confirm the `paymentGateway` and `paymentService` beans appear in the AOT analysis output.
2. Locate the supplier or factory method used to instantiate each bean.
3. Inspect how the `PaymentGateway` dependency is supplied to `PaymentService`.
4. Compare with `@Qualifier`, `@Profile`, scope, and `@Lazy` declarations in your source code.
5. If an expected bean is missing, check scan scope, configuration conditions, and the AOT processing environment before concluding the generator is wrong.

**Do not edit generated source files directly.** They will be regenerated on the next build. If changes are needed, update configuration sources or AOT extension mechanisms and rerun processing.

## 10. From AOT Code to GraalVM Native Image

When the target is native execution, typical build commands (with a configured native build plugin/profile) are:

~~~bash
# Maven
./mvnw -Pnative native:compile

# Gradle
./gradlew nativeCompile
~~~

The native build pipeline feeds AOT output alongside application code into GraalVM reachability analysis. There are three distinct verification levels:

| Verification Level | What does it prove? | What is insufficient to conclude? |
|---|---|---|
| `process-aot` succeeds | Spring generated AOT code for the processing environment | That the native application is guaranteed to compile |
| Native compilation succeeds | GraalVM produced an executable from the code and metadata | That every endpoint and business branch works |
| Native executable testing | Executed flows produced correct observable results | That untested flows are also compatible |

Therefore, for the payment example, verify at least: context startup, `paymentService` bean creation, dependency wired to the right implementation, `pay()` returning expected results, and supported profiles working on their corresponding artifacts.

Integration tests or smoke tests calling endpoints can be added, but the focus is **running the same cases on JVM and native** to catch discrepancies caused by AOT or metadata.

## 11. Common Errors When Wiring Beans Through AOT

| Symptom | Likely cause to check | Remediation direction |
|---|---|---|
| `NoSuchBeanDefinitionException` occurring only in native | Bean excluded from AOT-analyzed structure or filtered by condition/profile | Inspect build environment, conditions, and generated registrations |
| `NoUniqueBeanDefinitionException` | Multiple beans of the same type without disambiguation | Check `@Qualifier`, `@Primary`, and bean definitions |
| Bean creation fails because constructor/method is inaccessible | Injection or library requires reflective access with insufficient metadata | Inspect exception, bean creation path, and related runtime hints |
| Bean is created but missing resource/template during processing | Resource was not packaged in the image | Check resource hints and classpath paths |
| Dynamic bean registration works on JVM but is absent in native | Registration happens after AOT analysis or lacks AOT support | Shift the bean set to build-determinable config or write appropriate AOT integration |
| Switching profile at runtime fails to create expected bean | Profile or structural condition was decided during AOT processing | Build for the target profile and test each supported configuration |

Do not try to fix every error by "keeping all reflection": bean errors can stem from conditions, dependency relationships, qualifiers, or dynamic registration, not only reflection metadata. Always read the stack trace, compare JVM and native contexts, and isolate step by step.

## 12. Practice: Proactively Predicting the Bean Graph

Extend the example with a `RemotePaymentGateway` implementation and two beans named `localGateway` and `remoteGateway`. `PaymentService` uses `@Qualifier("localGateway")`. Then:

1. Draw the expected bean and dependency diagram when profile `dev` is active.
2. Run `process-aot`, and verify that generated registration code includes the required beans and appropriate dependency wiring points.
3. Try removing `@Qualifier` while two beans of the same type exist, and observe the error or candidate selection under Spring's actual precedence mechanisms.
4. Add `@Lazy` to `PaymentService` and distinguish **definition registration time** from **instance creation time** using a log in the constructor.
5. Build natively and rerun valid cases; if behavior differs from JVM, inspect AOT-generated bean structure, required metadata, and build environment in order.

The expected outcome is being able to answer accurately: "Spring already **knew how to create the bean** at build time, but **when the bean is created** still depends on the container, scope, and runtime demand."

## 13. Takeaways

In Spring Boot Native Image, bean code generation via Spring AOT serves three related purposes: **explicitly registering bean structure**, **providing analyzable instance creation paths**, and **expressing how dependencies are resolved**. This process reduces dynamic discovery at startup and helps GraalVM see necessary Java call paths.

However, Spring AOT does not replace the IoC container, does not force every singleton to be created at build time, and does not automatically resolve all application reflection. A reliable native build requires a bean structure prepared appropriately for the deployment environment, properly scoped runtime hints, and testing on the built executable.
