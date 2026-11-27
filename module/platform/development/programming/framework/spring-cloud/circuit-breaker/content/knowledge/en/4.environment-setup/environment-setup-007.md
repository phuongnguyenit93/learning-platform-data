# Verifying the Classpath, Auto-Configuration, and Implementing CircuitBreakerFactory

## Environment Setup Objectives

Spring Cloud Circuit Breaker provides an abstraction layer so applications can call dependent services through a circuit breaker without tightly coupling business code to a specific library. With Resilience4j, the Spring Cloud starter brings the implementation, auto-configuration, and integration components into the Spring ApplicationContext.

To integrate properly, you must verify three things: the appropriate dependencies are on the classpath; auto-configuration created the right factory and related beans; and the application is injecting and using the right `CircuitBreakerFactory`. When a custom mechanism is needed, you can implement a factory compatible with Spring Cloud's abstraction.

## Choosing Dependencies and Verifying the Classpath

For a standard Spring MVC or Spring Web application, add the Resilience4j starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
```

If the application uses Reactor and needs a reactive circuit breaker, use the corresponding starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
```

With Gradle, declare the equivalent dependencies:

```groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j'
    // Only add the reactive starter if the application uses Reactor:
    // implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j'
}
```

Manage Spring Boot and Spring Cloud versions using mutually compatible BOMs. Do not pick an individual Spring Cloud Circuit Breaker version and pair it with an arbitrary release train: Spring Cloud libraries share many APIs and evolve across version lines.

After declaring dependencies, inspect the dependency graph to confirm the starter and required libraries are actually in the runtime configuration:

```bash
# Maven
mvn dependency:tree

# Gradle
./gradlew dependencies --configuration runtimeClasspath
```

Read the output against these checkpoints:

- The starter matching the application model (imperative or reactive) is present.
- Spring Cloud Circuit Breaker core and the corresponding Resilience4j implementation are present.
- There are no two conflicting versions of the same library caused by transitive dependencies.
- The Spring Boot, Spring Cloud, and Resilience4j versions belong to a supported combination.

A dependency appearing on the compile classpath is not guaranteed to be on the runtime classpath. If the application throws `ClassNotFoundException` or `NoClassDefFoundError`, inspect the actual packaged artifact and runtime configuration. If you encounter `NoSuchMethodError`, check for version conflicts because the class was found, yet its runtime API does not match the compiled code.

## Distinguishing Classpath, Component Scan, and Auto-Configuration

The classpath tells the JVM which classes can be loaded. Component scan finds classes declared by the application, typically classes annotated with `@Component`, `@Service`, or `@Configuration`. Spring Boot auto-configuration uses conditions to decide whether to create pre-configured beans.

Therefore, having a library on the classpath does not guarantee the factory has been created. Auto-configuration may also depend on:

- The presence of a specific class, usually checked with `@ConditionalOnClass`.
- The absence of an application-declared bean, checked with `@ConditionalOnMissingBean`.
- A property enabling or disabling the feature, checked with `@ConditionalOnProperty`.
- Other dependent beans having been registered successfully.

Illustrative example of an application-authored auto-configuration:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(CircuitBreakerFactory.class)
@ConditionalOnProperty(
    prefix = "app.circuit-breaker",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class ApplicationCircuitBreakerConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ApplicationCircuitBreakerPolicy applicationCircuitBreakerPolicy() {
        return new ApplicationCircuitBreakerPolicy();
    }
}
```

This is only an example of bean creation conditions in an application; the Resilience4j starter already provides its own auto-configuration. Do not create an extra Resilience4j `CircuitBreakerFactory` if the starter has already registered an appropriate factory. A duplicate factory bean of the same type can alter bean selection or cause injection errors.

## Confirming the Factory Created by Spring

The application can inject the `CircuitBreakerFactory` abstraction instead of instantiating the implementation manually:

```java
@Service
public class CatalogService {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;

    public CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
    }

    public CatalogItem find(String id) {
        return circuitBreakerFactory.create("catalog").run(
            () -> catalogClient.find(id),
            error -> CatalogItem.unavailable(id)
        );
    }
}
```

The factory creates a circuit breaker named `catalog`. This name is the configuration identifier; use a stable name per dependent service rather than generating a new name per request. The fallback receives the failure cause so the application can log it or choose an appropriate response. For example, `CatalogItem.unavailable(id)` should clearly represent undetermined data rather than masquerading as a valid found result.

To inspect auto-configuration, you can enable Spring Boot's conditions report at startup:

```bash
java -jar app.jar --debug
```

In the report, look for configurations related to Circuit Breaker and Resilience4j. Check which configurations matched, which were skipped, and why. You can inspect beans at runtime by checking the ApplicationContext or using Spring Boot Actuator's `conditions` endpoint in an appropriately secured environment.

If the factory is not created, check dependencies, classpath conditions, configuration properties, application-declared replacement beans, and the conditions report in order. If there are multiple beans of the same type, determine which bean is selected and why; do not resolve it by arbitrarily adding `@Primary` before understanding where the duplicate bean came from.

## Customizing the Resilience4j Factory

Normally, you should customize the factory provided by the starter using a `Customizer`. Example setting a default configuration for instances:

```java
@Configuration(proxyBeanMethods = false)
public class Resilience4jCircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> defaultCircuitBreakerConfig() {
        return factory -> factory.configureDefault(id ->
            new Resilience4JConfigBuilder(id)
                .circuitBreakerConfig(
                    CircuitBreakerConfig.custom()
                        .failureRateThreshold(50)
                        .slidingWindowSize(10)
                        .minimumNumberOfCalls(5)
                        .build()
                )
                .timeLimiterConfig(
                    TimeLimiterConfig.custom()
                        .timeoutDuration(Duration.ofSeconds(3))
                        .build()
                )
                .build()
        );
    }
}
```

The corresponding imports belong to Spring Cloud Circuit Breaker, Resilience4j, and Java time. Builder class names or import paths may vary by the release train in use; keep dependencies on the same version line. In this configuration, `failureRateThreshold`, `slidingWindowSize`, and `minimumNumberOfCalls` control failure evaluation; `TimeLimiterConfig` controls the wait duration for calls integrated with TimeLimiter. The two mechanisms work together, yet serve different purposes.

If you need per-name customization, use the factory's per-instance configuration API rather than duplicating factory beans. For example, a payment service may need a shorter timeout and a different failure threshold than a product catalog service. Separating configuration by name helps tailor policies to the characteristics of each dependent service.

## When Should You Implement Your Own CircuitBreakerFactory?

You should only implement your own factory when the application needs a custom provider, wants to wrap an internal library, or needs to bring a circuit breaker mechanism without an existing starter into the Spring Cloud abstraction. If Resilience4j meets your requirements, customizing the starter-provided factory is usually simpler and less risky.

`CircuitBreakerFactory` is the entry point for creating `CircuitBreaker` objects by identifier. An implementation needs to handle at least the following:

1. Accept a stable identifier for the dependent service.
2. Look up the corresponding policy or configuration, optionally falling back to a default configuration when no specific configuration exists.
3. Create a `CircuitBreaker` object capable of executing the supplier and handling fallbacks according to Spring Cloud's contract.
4. Scope state and metrics properly per breaker; do not create an unintended shared state across all services.
5. Allow Spring to register the factory as a bean so the application can inject the abstraction.

Skeleton example of a custom factory structure:

```java
public final class CustomCircuitBreakerFactory
        extends CircuitBreakerFactory<CustomBreakerConfig, CustomBreakerConfigBuilder> {

    private final CustomBreakerRegistry registry;

    public CustomCircuitBreakerFactory(CustomBreakerRegistry registry) {
        this.registry = registry;
    }

    @Override
    public CircuitBreaker create(String id) {
        CustomBreakerConfig config = registry.configurationFor(id);
        return new CustomCircuitBreaker(id, config, registry);
    }

    @Override
    protected CustomBreakerConfigBuilder configBuilder(String id) {
        return new CustomBreakerConfigBuilder();
    }
}
```

`CustomBreakerConfig`, `CustomBreakerConfigBuilder`, `CustomBreakerRegistry`, and `CustomCircuitBreaker` are application-defined types illustrating the implementation's responsibilities. The builder must adhere to the `ConfigBuilder` contract of the Spring Cloud Circuit Breaker version in use; the factory needs to connect per-ID configuration results with the provider's registry. Specific builder and registry implementations depend on how the provider stores policies, so do not copy these illustrative types as if they were built-in Spring APIs.

A custom breaker must properly handle two main branches: letting the supplier run when state permits, and returning the fallback when the call fails according to contract. Do not treat every business error as an infrastructure failure by default. Classify exceptions, record outcomes, and transition states according to the chosen policy. At the same time, the fallback should not hide cause information; log or emit metrics before returning the replacement response.

Register the implementation with a conditional bean to avoid conflicting with a starter:

```java
@Configuration(proxyBeanMethods = false)
public class CustomCircuitBreakerConfiguration {

    @Bean
    @ConditionalOnMissingBean(CircuitBreakerFactory.class)
    CustomCircuitBreakerFactory customCircuitBreakerFactory(
            CustomBreakerRegistry registry) {
        return new CustomCircuitBreakerFactory(registry);
    }
}
```

If packaging this configuration as an auto-configuration library, register it using the mechanism for your Spring Boot version. Spring Boot 3 uses `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; Spring Boot 2 applications commonly use `spring.factories`. Do not register the same configuration both ways in a single library unless intentionally supporting both corresponding versions.

## Reactive Factory and Reactive Classpath

Applications using `Mono` or `Flux` should select the corresponding reactive starter and use `ReactiveCircuitBreakerFactory`. Do not wrap a reactive call with the imperative factory and call `block()` to force synchronization, as doing so can occupy threads and negate the benefits of the non-blocking model.

Example using the reactive factory:

```java
@Service
public class ReactiveCatalogService {
    private final ReactiveCircuitBreakerFactory<?, ?> factory;
    private final WebClient webClient;

    public ReactiveCatalogService(
            ReactiveCircuitBreakerFactory<?, ?> factory,
            WebClient webClient) {
        this.factory = factory;
        this.webClient = webClient;
    }

    public Mono<String> find(String id) {
        return factory.create("catalog")
            .run(
                webClient.get()
                    .uri("/catalog/{id}", id)
                    .retrieve()
                    .bodyToMono(String.class),
                error -> Mono.just("CATALOG_UNAVAILABLE")
            );
    }
}
```

Inspect the reactive classpath separately if Spring cannot find `ReactiveCircuitBreakerFactory` or fails to create the reactive implementation. Only add the reactive starter when the application actually uses Reactor; an MVC application does not need to bring in reactive components just to use an imperative circuit breaker.

## Startup Diagnostic Procedure

When the application cannot create or inject the factory, check in the following sequence:

| Symptom | Where to Check |
| --- | --- |
| `ClassNotFoundException` or `NoClassDefFoundError` | Runtime dependencies, packaged artifact, chosen imperative/reactive starter. |
| `NoSuchMethodError` | Whether Spring Boot, Spring Cloud, and transitive dependency versions are compatible. |
| No `CircuitBreakerFactory` bean | Auto-configuration report, classpath conditions, enable/disable properties, and excluded configurations. |
| Multiple beans of the same type | Custom configurations, component scan, other starters, and `@ConditionalOnMissingBean` conditions. |
| Circuit breaker always uses default configuration | ID name passed to `create`, instance name in configuration, and customizer application order. |
| Reactive factory not created | Reactor starter, Reactor classes on runtime classpath, and reactive auto-configuration. |

After fixing, restart the application and verify that the factory is injected, the breaker is created with the right ID, the fallback runs on errors, and metrics reflect outcomes. In a development environment, you can test against a mock service returning errors or delaying responses to observe behavior. Do not leave diagnostic or actuator endpoints public without restricting access.

## Key Principles to Remember

- Dependencies determine which classes are on the classpath; auto-configuration determines which beans are created.
- Use the right starter type and manage versions with a compatible BOM.
- Prefer customizing the starter-provided Resilience4j factory before implementing your own `CircuitBreakerFactory`.
- Use stable breaker names to accurately map configuration and metrics.
- Keep fallbacks meaningful and distinguish business errors from dependency failures.
- With Reactor, use the reactive starter and `ReactiveCircuitBreakerFactory` throughout the pipeline.

Once the classpath and auto-configuration are verified, the application can use the `CircuitBreakerFactory` abstraction consistently. This enables controlled policy changes for protecting dependent services and supports deploying circuit breakers in Spring Cloud without cluttering business code.
