# Spring AOT Cannot Infer Bean Type or Instantiation Strategy

> **Chapter:** Diagnostics  
> **Module:** `SPRING_BOOT_NATIVE_IMAGE`  
> **Objective:** Diagnose beans whose actual type or instantiation strategy Spring AOT cannot determine; fix `@Bean` declarations, `FactoryBean`, generic types, and `BeanDefinition`; handle dynamic bean registration; distinguish type prediction errors from RuntimeHints and native runtime errors.

## 1. Why Does Spring AOT Need to Know Bean Types Ahead of Time?

In a standard Spring application, the container can defer several decisions until runtime. It reads bean definitions, instantiates beans, runs `BeanFactoryPostProcessor` and `BeanPostProcessor`, and resolves additional type, constructor, field injection, lifecycle callback, or proxy details on demand.

Spring AOT shifts most of that discovery and preparation to build time. AOT creates an `ApplicationContext` to analyze, collects bean definitions, and generates corresponding initialization code. For statically declared beans, the generated code can invoke constructors or factory methods directly instead of relying on reflection at runtime.

To accomplish this, AOT needs to know:

- Which beans will exist in the application context.
- The concrete bean type or the product type provided by the bean.
- Which constructor, factory method, or instantiation mechanism is used.
- Which dependencies must be injected into the bean.
- Which field/method injections and lifecycle callbacks must be processed.
- Which proxy, reflection, resource, or serialization metadata are required.

When a bean is described only by an overly broad interface, a raw generic type, a `FactoryBean` that does not advertise its product type, a dynamic supplier, or a directly registered singleton, AOT may be unable to reproduce the full container behavior.

The Spring Framework documentation states clearly: the classpath and bean definitions are fixed at build time; `@Profile` and `@Conditional` conditions are evaluated during AOT; bean definitions using instance suppliers (lambdas or method references) and singletons registered with `registerSingleton` cannot be transformed ahead of time in the usual way. Because it cannot inspect runtime instances to infer types, bean declarations must be as precise as possible. [Spring Framework — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)

## 2. Distinguish Type Inference Errors from Bean Creation Errors and Native Metadata Errors

These three categories are frequently confused:

| Category | Unresolved question for Spring/GraalVM | Example symptoms |
|---|---|---|
| Bean type prediction | What is the type of the bean or factory product? | Bean exposes only `Object`, raw `FactoryBean`, unresolved generics |
| Bean instantiation | Which constructor/factory method/supplier creates the instance? | Dynamically registered supplier, custom constructor arguments, pre-created singleton |
| Native runtime metadata | At native runtime, which reflection/resource/proxy operations must be retained? | `NoSuchMethodException`, resource not found, proxy cannot be created |

Examples to distinguish them:

- `@Bean` returns `Object` when the actual object is `PaymentGatewayImpl`: type prediction issue.
- `BeanDefinition#setInstanceSupplier(...)` uses a lambda creating a bean from runtime data: issue converting the instantiation strategy to AOT.
- Bean type is clear, but a library invokes its constructor via reflection: RuntimeHints issue.
- Bean is registered via `registerSingleton`: the instance is already created, so AOT lacks a bean definition with enough information to recreate it.
- `@ConditionalOnProperty` changes between build and runtime environments: bean condition is fixed during AOT.

Do not start by adding a `RuntimeHintsRegistrar` for every AOT error. Runtime hints tell Native Image to retain dynamic operations; they do not tell Spring which beans to register or how to create them.

## 3. Declare Concrete Return Types for `@Bean`

This is the most common cause and also the simplest fix.

Suppose an application has an interface and an implementation:

```java
public interface PaymentGateway {
    PaymentResult charge(PaymentCommand command);
}

public class PaymentGatewayImpl implements PaymentGateway {

    @Override
    public PaymentResult charge(PaymentCommand command) {
        // Call the payment provider.
        return PaymentResult.approved();
    }

    public void validateProviderConfiguration() {
        // Validate implementation-specific configuration.
    }
}
```

The following declaration tells AOT only that the bean has type `PaymentGateway`:

```java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new PaymentGatewayImpl();
    }
}
```

At runtime, the code still receives `PaymentGatewayImpl`. However, during AOT processing, Spring uses the declared return type on the factory method to analyze the bean. Annotations, injection points, or lifecycle callbacks present only on `PaymentGatewayImpl` may not be recognized.

Declare the most concrete type that the configuration actually produces:

```java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentGatewayImpl paymentGateway() {
        return new PaymentGatewayImpl();
    }
}
```

Consumers can still inject by interface:

```java
@Service
class CheckoutService {

    private final PaymentGateway paymentGateway;

    CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

This does not force business code to depend on the implementation. It simply allows the bean definition to expose enough information to the container at build time.

### 3.1. When Should You Keep the Interface Type?

If a factory genuinely can return multiple implementations depending on configuration, do not declare a single concrete implementation that contradicts runtime behavior. Split the beans into separate factory methods, use explicit configuration conditions, and ensure the conditions are resolved during the AOT build.

Example:

```java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    @Profile("sandbox")
    SandboxPaymentGateway sandboxPaymentGateway() {
        return new SandboxPaymentGateway();
    }

    @Bean
    @Profile("production")
    ProductionPaymentGateway productionPaymentGateway() {
        return new ProductionPaymentGateway();
    }
}
```

Both methods declare concrete types. Which bean is included in the AOT context depends on the profile active at build time. When running AOT/native, profiles and bean conditions are fixed by the build configuration; changing `SPRING_PROFILES_ACTIVE` at runtime cannot activate a bean that was excluded from AOT output.

If the same binary must support multiple environments, design a bean with a stable concrete type that reads runtime configuration via supported dependencies, or produce separate AOT artifacts per profile/condition set. Do not rely on switching profiles at runtime to alter the generated bean set.

## 4. Inspect Factory Methods and Constructors

Spring AOT needs to determine how to instantiate a bean. For regular classes, keep constructors and dependencies unambiguous:

```java
@Component
class InvoiceService {

    private final InvoiceRepository repository;
    private final TaxCalculator taxCalculator;

    InvoiceService(
            InvoiceRepository repository,
            TaxCalculator taxCalculator) {
        this.repository = repository;
        this.taxCalculator = taxCalculator;
    }
}
```

If a class has multiple constructors, mark the one Spring should use with `@Autowired` when disambiguation is needed. With a single constructor, Spring can use it without any annotation.

Avoid classes with multiple ambiguous instantiation paths, constructors taking ad-hoc arguments available only at runtime, or factory methods taking parameters AOT cannot predict.

For a static factory method example, declare dependencies as parameters:

```java
@Configuration(proxyBeanMethods = false)
class InvoiceConfiguration {

    @Bean
    InvoiceService invoiceService(
            InvoiceRepository repository,
            TaxCalculator taxCalculator) {
        return new InvoiceService(repository, taxCalculator);
    }
}
```

Spring can describe the factory method's dependencies via bean definitions and generate code calling the corresponding method.

### 4.1. Avoid Passing Custom Arguments to `getBean`

Some applications create prototype beans with custom arguments:

```java
InvoiceJob job = beanFactory.getBean(
        InvoiceJob.class, invoiceId, requestedAt);
```

This requires the container to find a constructor or factory method matching dynamic arguments. Spring AOT cannot infer all argument combinations and required reflection from runtime call sites. Furthermore, instantiating beans with custom arguments can bypass generated instance suppliers, preventing field/method injection optimizations from being applied as expected.

Instead, create a dedicated factory bean with explicit dependencies:

```java
@Component
class InvoiceJobFactory {

    private final InvoiceRepository repository;
    private final Clock clock;

    InvoiceJobFactory(InvoiceRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    InvoiceJob create(long invoiceId) {
        return new InvoiceJob(invoiceId, clock.instant(), repository);
    }
}
```

Here the factory bean is managed by Spring with a deterministic type. Per-job data is passed to the `create` method, while long-lived dependencies are injected when the factory is created. This is also easier to test and gives better control over object lifecycles.

## 5. Generic Types Lost Due to Raw Types or Type Erasure

Spring uses `ResolvableType` to preserve and analyze generic metadata. If a bean is declared with a raw type, part of that information can be lost.

Insufficiently typed example:

```java
@Bean
RepositoryAdapter repositoryAdapter() {
    return new RepositoryAdapter();
}
```

If the adapter actually manages `Customer`, declare the type with explicit generics:

```java
@Bean
RepositoryAdapter<Customer, Long> customerRepositoryAdapter() {
    return new RepositoryAdapter<>();
}
```

For programmatic bean definitions, use `RootBeanDefinition` and set the target type with `ResolvableType`:

```java
RootBeanDefinition definition =
        new RootBeanDefinition(RepositoryAdapter.class);

definition.setTargetType(
        ResolvableType.forClassWithGenerics(
                RepositoryAdapter.class,
                Customer.class,
                Long.class));

registry.registerBeanDefinition(
        "customerRepositoryAdapter", definition);
```

`ResolvableType.forClassWithGenerics(...)` preserves type arguments that a raw `Class` cannot represent. This is especially important when a bean factory, `FactoryBean`, collection injection, or framework extension needs the exact product type. [Spring Framework — ResolvableType Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ResolvableType.html)

## 6. Handle `FactoryBean` When AOT Does Not Know the Product Type

A `FactoryBean` produces an object distinct from the factory itself. Spring must know both the factory type and the product type returned by `getObject()`. If the product type cannot be determined, type prediction and post-processing steps may fail to recognize the bean actually injected by consumers.

Example of a generic factory left unparameterized:

```java
public class ClientFactoryBean<T extends AbstractClient>
        implements FactoryBean<T> {

    private final Class<T> productType;
    private final Supplier<T> supplier;

    public ClientFactoryBean(Class<T> productType, Supplier<T> supplier) {
        this.productType = productType;
        this.supplier = supplier;
    }

    @Override
    public T getObject() {
        return supplier.get();
    }

    @Override
    public Class<?> getObjectType() {
        return productType;
    }
}
```

A raw declaration discards generic metadata:

```java
@Bean
ClientFactoryBean paymentClient() {
    return new ClientFactoryBean(
            PaymentClient.class, PaymentClient::new);
}
```

Expose the resolved generic type:

```java
@Bean
ClientFactoryBean<PaymentClient> paymentClient() {
    return new ClientFactoryBean<>(
            PaymentClient.class, PaymentClient::new);
}
```

The type `ClientFactoryBean<PaymentClient>` gives Spring generic information about the product. If the factory is registered programmatically, describe both the factory class and the target type:

```java
RootBeanDefinition definition =
        new RootBeanDefinition(ClientFactoryBean.class);

definition.setTargetType(
        ResolvableType.forClassWithGenerics(
                ClientFactoryBean.class,
                PaymentClient.class));

registry.registerBeanDefinition("paymentClient", definition);
```

When necessary, `FactoryBean#getObjectType()` should also return a stable product class that the factory can report without creating a product instance. Avoid returning `null` or inferring the product type only after calling an external service, reading a runtime file, or creating a client.

### 6.1. When Should You Replace `FactoryBean` with `@Bean`?

Spring Framework recommends considering replacing `FactoryBean` with a standard factory method if the factory does not hold long-lived state and does not need to exist at runtime. Example:

```java
@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    PaymentClient paymentClient(
            PaymentClientProperties properties,
            HttpClient httpClient) {
        return new PaymentClient(properties.endpoint(), httpClient);
    }
}
```

A factory method makes the product type and dependencies explicit. Keep `FactoryBean` only when that abstraction is genuinely required, such as integrating a framework API or needing the factory itself accessible as a standalone bean.

## 7. Register Beans Programmatically with `BeanDefinitionRegistry`

If an application needs to register beans per module/plugin, register the bean definition before AOT analyzes the context. The proper approach is using `ImportBeanDefinitionRegistrar` or `BeanDefinitionRegistryPostProcessor` at the right lifecycle stage.

Example registrar declaring a bean definition with a concrete class:

```java
public class PaymentClientRegistrar
        implements ImportBeanDefinitionRegistrar {

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata importingClassMetadata,
            BeanDefinitionRegistry registry) {

        RootBeanDefinition definition =
                new RootBeanDefinition(PaymentClient.class);

        definition.setTargetType(
                ResolvableType.forClass(PaymentClient.class));

        registry.registerBeanDefinition(
                "paymentClient", definition);
    }
}
```

Import the registrar from a configuration class:

```java
@Configuration(proxyBeanMethods = false)
@Import(PaymentClientRegistrar.class)
class PaymentClientConfiguration {
}
```

The AOT engine processes the configuration model and invokes callbacks while analyzing configuration. Thus, a registrar imported this way can contribute bean definitions before code generation occurs.

If you need to register a bean with generic types, use `RootBeanDefinition#setTargetType(ResolvableType)` as shown in the previous section. If a specific constructor or factory method is needed, declare the bean class and factory method explicitly rather than storing a pre-created instance.

### 7.1. Avoid Registering Pre-Created Instances with `registerSingleton`

The following example creates an object before the container has a bean definition to analyze:

```java
PaymentClient client = createClientFromRuntimeState();

beanFactory.registerSingleton("paymentClient", client);
```

AOT cannot convert a directly registered singleton into a reproducible bean creation sequence. It only sees the pre-existing instance during the build, without a complete description to instantiate an equivalent object when the native executable runs.

Replace it with a bean definition or `@Bean` factory method:

```java
@Bean
PaymentClient paymentClient(
        PaymentClientProperties properties,
        HttpClient httpClient) {
    return createClient(properties, httpClient);
}
```

If client creation logic needs runtime configuration, inject the required properties or abstractions into the factory method. Do not call an external service during the AOT phase to obtain an object and register it as a singleton.

### 7.2. Avoid Custom `BeanDefinition#setInstanceSupplier`

A bean definition using a lambda or method reference as an instance supplier may work on the JVM:

```java
RootBeanDefinition definition =
        new RootBeanDefinition(PaymentClient.class);

definition.setInstanceSupplier(
        () -> createClientFromRuntimeState());

registry.registerBeanDefinition("paymentClient", definition);
```

However, Spring AOT cannot convert this custom instance supplier into static initialization code through the standard mechanism. Prefer `beanClass`, constructor metadata, or a well-typed factory method. If a library must contribute special initialization logic for AOT, look at the AOT contribution APIs instead of expecting AOT to decompile or analyze a lambda body.

Note: AOT code generation emitting its own instance suppliers for analyzed bean definitions is a normal internal implementation detail. The limitation here refers to suppliers attached to bean definitions by the application prior to AOT processing.

## 8. Choose the Right Extension Point for AOT

If a library or integration module registers its own beans, it may need to contribute both bean definitions and code that reproduces runtime behavior. Choose the extension point by responsibility:

| API | Responsibility | When to use |
|---|---|---|
| `ImportBeanDefinitionRegistrar` | Registers bean definitions during configuration processing | Adding beans from annotations/imports or module integrations |
| `BeanDefinitionRegistryPostProcessor` | Modifies the registry before the factory processes bean definitions | Existing infrastructure needing to adjust the registry |
| `BeanFactoryInitializationAotProcessor` | Contributes bean factory initialization code and RuntimeHints | Need to reproduce infrastructure behavior at AOT |
| `BeanRegistrationAotProcessor` | Contributes code/hints for individual bean registrations | Need special handling per bean definition |
| `RuntimeHintsRegistrar` | Registers reflection, resource, serialization, JDK proxy hints | Bean is already recognized, but Native Image lacks metadata |

`BeanFactoryInitializationAotProcessor` can be registered in `META-INF/spring/aot.factories` under the key of the interface's fully qualified name. It can also be declared as a bean; in that case, the processor and its dependencies are instantiated during the AOT phase, and the processor bean is then excluded from the AOT-optimized context since its contribution has already been applied.

`BeanRegistrationAotProcessor` is also an infrastructure extension point. If a bean itself implements this interface, the bean and its dependencies are instantiated during AOT processing. Spring recommends restricting such processors to infrastructure beans with minimal dependencies that are already initialized early. If declared via `@Bean`, the factory method should be `static` so the enclosing configuration class does not need to be instantiated. [Spring Framework — AOT Contributions](https://docs.spring.io/spring-framework/reference/core/aot.html)

Do not write a custom AOT processor just to work around an overly broad `@Bean` return type. Fix the underlying bean definition first. Custom AOT processors are meant for libraries or infrastructure that genuinely need to reproduce specialized behavior.

## 9. `@Profile` and `@Conditional` Conditions Are Decided at Build Time

Spring AOT analyzes the `ApplicationContext` against the classpath and `Environment` available at build time. Conditions determining whether a bean exists are evaluated during that process.

Example:

```java
@Bean
@ConditionalOnProperty(
        prefix = "payment",
        name = "gateway",
        havingValue = "external")
ExternalPaymentGateway externalPaymentGateway() {
    return new ExternalPaymentGateway();
}
```

If the property is absent or has a different value when AOT runs, the bean may be omitted from the generated context. Setting `PAYMENT_GATEWAY=external` after the image is built cannot restore a bean definition already excluded from the output.

Distinguish between:

- **Bean-selecting configuration:** profiles/conditions deciding which beans are created. Values must be supplied to the AOT build.
- **Bean-operating configuration:** endpoints, timeouts, credentials, or feature data read by a bean at runtime. These values can remain externalized as long as they do not alter the set of bean definitions.

Example profile configuration for Maven AOT execution:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>process-aot</id>
            <configuration>
                <profiles>native</profiles>
            </configuration>
            <goals>
                <goal>process-aot</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Actual configuration depends on the project's build plugins and profiles. Inspect the effective POM and `process-aot` logs to confirm which profiles/properties are used.

With Gradle, configure profiles for the AOT task via arguments on the `ProcessAot` task:

```groovy
tasks.withType(org.springframework.boot.gradle.tasks.aot.ProcessAot).configureEach {
    args('--spring.profiles.active=profile-a,profile-b')
}
```

Spring Boot explicitly notes that `@Conditional` annotations are evaluated during AOT and profiles are affected as well. Beans created during the AOT phase will be created when running with AOT; they cannot be toggled back on or off by changing runtime properties. [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/how-to/aot.html)

### 9.1. One Binary for Multiple Environments

If a single binary must run across multiple environments with different implementations, there are three design options:

1. Produce separate AOT artifacts per profile/condition set if the bean structure differs.
2. Register one stable implementation, inject properties/runtime strategies, and select behavior via runtime configuration.
3. Include the implementations in the same bean graph when all must be present, then select via a strategy bean with a deterministic type.

Do not attempt to use runtime profiles to alter a context structure already fixed inside the generated initializer.

## 10. Dynamic Bean Registration and Plugin Discovery

A JVM application can scan the classpath or a plugin directory at startup and create beans for each discovered implementation. In a native image, the classpath and type universe are analyzed at build time. You cannot assume runtime scanning will discover new classes that Native Image did not include in the executable.

If plugins are part of the product:

- Determine the plugin list before running AOT.
- Register bean definitions using configuration/import registrars.
- Keep plugin classes on the build classpath.
- Declare each plugin's concrete type and generic types.
- Produce AOT artifacts matching the supported plugin set.
- If plugins are loaded from external files, consider isolating plugins into separate processes/services rather than expecting a native executable to dynamically load new classes.

`BeanDefinitionRegistryPostProcessor` can participate in AOT if invoked while configuration is processed. However, if the processor itself is registered as a bean, it might also be invoked again at runtime. If runtime behavior must be replaced with generated code, the processor must make an appropriate AOT contribution, such as implementing `BeanFactoryInitializationAotProcessor`. Spring Framework recommends `ImportBeanDefinitionRegistrar` for the standard case of registering beans from configuration. [Spring Framework — Programmatic Bean Registration](https://docs.spring.io/spring-framework/reference/core/aot.html)

## 11. Resolve Circular Dependencies Before AOT Optimization

Some circular dependencies can accidentally work on the JVM via field injection or setter injection. An AOT-optimized context does not support explicit circular dependencies in the way traditional runtime resolution might handle them.

Example cycle:

```text
OrderService -> InventoryService -> ReservationService -> OrderService
```

Refactor the design to separate responsibilities or convert one dependency into controlled lazy access.

Use `ObjectProvider` when a bean is only needed when a specific operation runs:

```java
@Service
class ReservationService {

    private final ObjectProvider<OrderService> orderServiceProvider;

    ReservationService(
            ObjectProvider<OrderService> orderServiceProvider) {
        this.orderServiceProvider = orderServiceProvider;
    }

    void confirm(Reservation reservation) {
        OrderService orderService = orderServiceProvider.getObject();
        orderService.markReserved(reservation.orderId());
    }
}
```

`@Lazy` on an injection point can also defer dependency resolution. However, this should be reserved for dependencies that truly warrant lazy access; if two services call each other constantly, extract shared business logic into a third service to eliminate the cycle.

## 12. RuntimeHints Cannot Fix Bean Type Prediction

Once the bean definition is clear, if the native image fails due to reflection, resources, or proxies, add the corresponding metadata. Example:

```java
public class PaymentRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
                PaymentSerializer.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}
```

Activate the registrar:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentRuntimeHints.class)
class PaymentNativeConfiguration {
}
```

This tells Native Image to retain the constructor and public methods needed for reflection. It does not inform Spring that `PaymentSerializer` is a `FactoryBean` product type, does not recreate directly registered singletons, and does not convert a custom supplier into AOT initialization code.

Choose the right tool:

| Problem | Remedy |
|---|---|
| `@Bean` return type is too broad | Declare a concrete return type |
| Generics are lost | Use full generic signatures and `ResolvableType` |
| `FactoryBean` product type is unclear | Resolve generics and declare `getObjectType()` |
| Bean registered after AOT or as a singleton | Register `BeanDefinition` during the configuration phase |
| Custom supplier | Use an analyzable constructor/factory method or AOT contribution |
| Bean excluded from AOT by condition | Supply profile/property to the build or design a stable graph |
| Constructor/member reflection is missing | Register RuntimeHints for the exact operations |
| Resource is missing from the image | Register resource hints or switch to an appropriate external file |

## 13. Diagnostic Workflow When AOT Fails to Recognize a Bean

Diagnose starting from the original bean definition, and only then inspect generated code and the native runtime.

### Step 1: Identify the Bean Name and Registration Source

Locate where the bean is declared:

- Component annotations such as Component, Service, or Repository.
- Bean factory method.
- Import or ImportBeanDefinitionRegistrar.
- BeanDefinitionRegistryPostProcessor.
- FactoryBean.
- Direct registration via registerSingleton or setInstanceSupplier.

If the bean only appears after a runtime callback executes, AOT may not see that bean definition. Determine whether the callback executes during the AOT configuration phase.

### Step 2: Inspect the Type Predicted by BeanFactory

You can use ConfigurableListableBeanFactory in a test or diagnostic infrastructure check to inspect type prediction:

```java
ConfigurableListableBeanFactory beanFactory =
        applicationContext.getBeanFactory();

Class<?> predictedType =
        beanFactory.getType("paymentClient", false);

ResolvableType productType =
        beanFactory.getBeanDefinition("paymentClient")
                .getResolvableType();

System.out.println("predictedType=" + predictedType);
System.out.println("resolvableType=" + productType);
```

The parameter allowFactoryBeanInit=false avoids triggering FactoryBean initialization just to determine the product type. The result can be null if the container cannot yet predict it. Do not call getBean() during diagnosis just to check the type, because doing so can mask the issue by instantiating the bean early.

If the bean is a FactoryBean, inspect the factory type and product type separately. If the bean has generics, inspect ResolvableType instead of looking only at Class.

### Step 3: Check Profiles and Conditions of the AOT Build

Record:

- Active profiles during the AOT phase.
- Environment properties affecting Conditional evaluations.
- Classpath and dependency versions when running AOT.
- Whether runtime profiles/properties differ from the build.

Enable debug logging or inspect the condition evaluation report when suspecting auto-configuration exclusion. If the bean is missing from AOT bean definitions, identify which condition excluded it.

### Step 4: Run AOT Processing Standalone

With Maven, when the plugin configures the process-aot goal, you can run:

```bash
mvn -Pnative spring-boot:process-aot
```

With the Gradle Spring Boot plugin:

```bash
./gradlew processAot
```

Task/profile names and how profiles are passed may vary by project configuration. Check plugin logs to confirm the AOT task actually ran and used the right Environment.

### Step 5: Inspect Generated Sources

Locate the generated initializer and bean definition classes. Class names typically look like:

- PaymentConfiguration__BeanDefinitions
- PaymentApplication__ApplicationContextInitializer
- Generated bean factory registrations or contribution classes.

Output directories vary by Spring Boot/build plugin version. Maven typically places output under target/spring-aot/; Gradle typically uses build/generated/aotSources, aotClasses, and aotResources. Use the path shown in your current project's build log rather than assuming a fixed path.

Check the generated code:

- Is the bean name registered?
- Does the bean definition have a concrete target type?
- Which factory method is called to create the instance?
- Are constructor arguments and dependencies correct?
- Was any bean excluded due to conditions/profiles?
- Is there generated code for the expected processor/registrar?

If the bean does not appear here, adding reflection hints will not fix the root cause.

### Step 6: Run the AOT-Processed Application on the JVM

After building the artifact containing AOT output, you can run it with AOT mode enabled:

```bash
java -Dspring.aot.enabled=true -jar target/payment-api.jar
```

With Gradle, substitute the actual JAR path in build/libs/. Running AOT mode on the JVM helps catch generated initializer and bean registration errors prior to native compilation. It does not replace native runtime tests, but it narrows down the failure scope.

### Step 7: Run the Native Executable

Once the AOT-processed JVM context starts cleanly, build the native executable and test the affected beans/use cases. If only the native runtime fails, reclassify the issue: reflection, resource, proxy, JNI, serialization, dynamic class loading, or a library lacking reachability metadata.

## 14. Read Errors by Symptom

| Symptom | High probability | What to check first |
|---|---|---|
| Bean missing from generated initializer | Condition/profile not enabled or registration occurs too late | AOT Environment and registration callback |
| Type prediction returns interface/Object | Bean factory method return type is too broad | Concrete factory method return type |
| Type prediction returns null for product | FactoryBean does not resolve product type | Generic parameter and getObjectType() |
| ResolvableType is raw/unresolved | Generic type erased or bean definition lacks target type | Generic signature, setTargetType |
| Supplier lambda not converted by AOT | Custom instance supplier | Replace with constructor/factory method or AOT contribution |
| Bean only exists on standard JVM run | Singleton registration or runtime classpath scanning | Switch to bean definitions analyzable at build time |
| Bean present in generated code but startup reports circular dependency | Explicit circular dependency | Split services, use ObjectProvider/@Lazy deliberately |
| AOT JVM runs but native throws NoSuchMethodException | Missing reflection metadata | RuntimeHints for exact constructor/method |
| Native throws ClassNotFoundException | Type missing from native image or wrong dependency/classpath | Build classpath and reachability |
| Native reports resource not found | Classpath resource not included | Resource hints or external file |
| Runtime profile fails to activate bean | Profile/condition was decided at AOT | Build artifacts per profile or keep bean graph stable |

There is no single error message covering every "AOT cannot infer bean" case. Use the bean definition source, type prediction, and generated code to pinpoint the exact failing stage.

## 15. Fixes That Easily Introduce New Bugs

### 15.1. Mechanically Changing Every Return Type to a Concrete Implementation

Declare a concrete type only when the factory genuinely always creates that implementation. If the factory has multiple outcomes, split factory methods or design a stable strategy bean. Declaring an inaccurate type can cause wrong container type prediction and break autowiring.

### 15.2. Adding Reflection Hints for Entire Packages

Reflection hints do not fix unregistered beans or unclear product types. Register only the constructors/members a library actually invokes via reflection, and verify with RuntimeHintsPredicates.

### 15.3. Forcing Bean Creation During AOT to Inspect Its Type

Calling getBean() inside a BeanFactoryPostProcessor or AOT callback just to check the concrete class can trigger constructors, database connections, or external service calls during the build. Describe the type on the bean definition; there is no need to instantiate the object to infer its type.

### 15.4. Relying on Runtime Classpath Scanning

Native image does not provide a flexible classpath like the JVM. If plugins or implementations must be discovered, scan/register them during AOT processing and ensure those classes are in the build input.

### 15.5. Keeping Circular Dependencies to Preserve Service Structure

AOT may reject dependency cycles that the standard JVM manages to resolve. Use Lazy or ObjectProvider when deferred access is genuinely needed; prefer splitting responsibilities if the cycle reflects flawed service design.

## 16. Pre-Native-Image Build Checklist

- [ ] Every key bean has a deterministic registration source during the AOT phase.
- [ ] Bean factory methods declare the most concrete return type possible.
- [ ] Consumers still inject by interface where appropriate.
- [ ] Beans with multiple constructors have the target constructor clearly designated.
- [ ] Generic signatures do not lose metadata due to raw or unresolved types.
- [ ] FactoryBean exposes a concrete product type via resolved generics and/or getObjectType().
- [ ] Programmatic registration uses BeanDefinitionRegistry and bean definitions with explicit target types.
- [ ] Do not rely on registerSingleton for beans that must be recreated at native runtime.
- [ ] Do not attach custom instanceSupplier expecting AOT to transform lambdas automatically.
- [ ] Do not instantiate prototype beans with custom getBean arguments when a factory bean can be used.
- [ ] Profiles and condition properties are properly supplied during the AOT build.
- [ ] Plugin discovery/bean registration runs before code generation.
- [ ] Infrastructure AOT processors are used only when necessary and keep minimal dependencies.
- [ ] No unresolved explicit circular dependencies remain.
- [ ] Generated bean definitions and initializers have been inspected.
- [ ] The AOT-processed application runs on the JVM.
- [ ] RuntimeHints are added only for reflection/resources/proxies actually required.
- [ ] The native executable has passed integration tests for affected beans and use cases.

## 17. Takeaways

Spring AOT must know which beans exist, what types they have, and how to instantiate them before the native executable is built. Start by clarifying bean definitions: declare concrete return types, preserve generic metadata with ResolvableType, expose FactoryBean product types, and register beans programmatically during the configuration phase.

Custom suppliers, pre-created singletons, runtime-only plugin scanning, and profile/property conditions differing from the AOT build can all cause the generated context not to match the intended application. In those cases, inspect type prediction and generated initializers before adding RuntimeHints. Only after bean registration and instantiation are correct should you address missing reflection, resource, or proxy metadata.

### References

- [Spring Framework — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Spring Framework — ResolvableType Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ResolvableType.html)
- [Spring Framework — BeanFactoryInitializationAotProcessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/aot/BeanFactoryInitializationAotProcessor.html)
- [Spring Framework — BeanRegistrationAotProcessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/aot/BeanRegistrationAotProcessor.html)
- [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/how-to/aot.html)
- [Spring Boot — Ahead-of-Time Processing with the JVM](https://docs.spring.io/spring-boot/reference/packaging/aot.html)
- [Spring Boot — Advanced Native Image Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
