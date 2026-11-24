# Proxies at `@Lazy` Injection Points and Error Timing in Spring Framework

## 1. The Problem: When Is a Bean Created, and When Do Errors Surface?

The Spring IoC Container manages bean definition registration, dependency resolution, and bean initialization. By default, many singletons in an `ApplicationContext` are created right when the context starts up. This is helpful because the application catches configuration, dependency, and initialization errors early.

However, sometimes a collaborator is only genuinely needed on a rare branch, takes time to initialize, or incurs connection overhead to an external system. Spring provides `@Lazy` to control bean creation timing and **lazy-resolution proxies** to defer dependency resolution at the **injection point**.

Two snippets that look nearly identical have different meanings:

```java
// 1. @Lazy on the bean definition.
@Bean
@Lazy
PaymentClient paymentClient() {
    return new RemotePaymentClient();
}
```

```java
// 2. @Lazy at the injection point.
@Bean
CheckoutService checkoutService(@Lazy PaymentClient client) {
    return new CheckoutService(client);
}
```

These are **illustrative excerpts**, requiring full imports and domain classes to compile. Case (1) controls **whether the `paymentClient` bean is pre-instantiated**. Case (2) asks Spring to supply **a proxy** at the `client` parameter, so the real bean is resolved when the proxy is used.

These are not two synonyms:

- If a bean definition has `@Lazy` yet is **injected directly** into an eager singleton, Spring may still have to create the bean right when the context starts.
- If an injection point has `@Lazy` yet the target bean is a **regular eager singleton**, the target may still already have been created before the first proxy call.
- When both the target definition **and** the injection point are lazy, provided no other dependency/eager lookup path pulls the target in, the target can be created when the proxy is actually invoked.
- If the target bean **does not exist**, a lazy proxy at the injection point can still be injected; the error only surfaces when the proxy is invoked.
- If the target bean is selected yet fails to construct, the bean creation error can appear on the first proxy call — instead of when creating the consumer.

Lesson objectives:

1. Distinguish `@Lazy` on `@Bean`/`@Component`/`@Configuration` from `@Lazy` on field, constructor parameter, and method parameter injection.
2. Understand what a lazy-resolution proxy does and does not do.
3. Know how to reason about `register`, `refresh`, constructor, init callback, proxy invocation, and destroy timing.
4. Recognize startup, injection, first-invocation, and later-invocation failures.
5. Understand the rule that a singleton target is cached once resolved while non-singletons may be re-resolved on every access.
6. Distinguish a lazy dependency from an optional dependency; use `ObjectProvider` properly when no bean exists.
7. Run a Java 17+ / Spring Framework 6.2 example with multiple contexts verifying the variants.
8. Have a methodology to test, debug, and safely apply this in production.

## 2. Choosing the Right `@Lazy` Placement to Control Error Timing

`@Lazy` on a **bean definition** (`@Bean`, component, configuration) determines whether the singleton target undergoes normal eager pre-instantiation. `@Lazy` at an **injection point** (constructor/`@Bean` parameter, field, or setter handled by Spring) requests a lazy-resolution **proxy** so the consumer can be created before the target is needed.

| Target bean | Injection edge into eager consumer | Observed outcome |
| --- | --- | --- |
| Eager singleton | `@Lazy Gateway` proxy | Proxy is injected, yet target may still be created right during refresh |
| `@Lazy` singleton | Direct `Gateway` | Target is created early to complete the consumer |
| `@Lazy` singleton | `@Lazy Gateway` proxy | Target can wait until the first proxy invocation |
| No valid target | `@Lazy Gateway` proxy | Proxy can still be injected; missing-dependency error moves to invocation time |
| Prototype | Lazy proxy | Target may be re-resolved for each method invocation; avoid for multiple calls needing shared mutable state |

For example, `@Bean @Lazy Gateway gateway()` combined with `consumer(@Lazy Gateway gateway)` truly defers the target only when **no other eager path** fetches the bean first. You must use an interface or proxiable type; final classes/methods and proxy limitations can cause errors **right at injection**, without waiting for first use.

This lesson closely analyzes **error location and kind**: proxy creation error, bean lookup error, bean creation error, and business invocation error are distinct situations. Check the refresh milestone vs first call using markers or `containsSingleton` before dereferencing the proxy.

## 3. How Lazy-Resolution Proxies Work at the Injection Point

Spring creates an intermediary object between consumer and target. The consumer holds a reference to the proxy; the proxy holds the mechanism to look up the target via the bean factory/dependency descriptor.

```text
                     ApplicationContext.refresh()
                                |
                                v
                   EagerConsumer is created
                                |
                                v
            @Lazy dependency at injection point
                                |
                                v
            Spring creates lazy-resolution proxy
                                |
                                v
              Consumer holds proxy reference
                                |
                    [target not needed yet]
                                |
               User calls consumer.execute()
                                |
                                v
                   Proxy intercepts call
                                |
                                v
          BeanFactory resolves target dependency
                 /             |             \
           exists          missing        creation fails
             |                 |               |
             v                 v               v
     Create/get target   missing bean error  BeanCreationException
             |
             v
       Call target method
             |
             v
        Return result to consumer
```

### 3.1. The Proxy Is a Real Injected Object

`@Lazy` at an injection point does not pass Java `null` and swap it for a bean later. It passes **a proxy object** that the consumer can store in a field, return from a getter, or pass onward.

```java
class ClientConsumer {
    private final Client client;

    ClientConsumer(@Lazy Client client) {
        this.client = client;
    }

    Client getClient() {
        return client;
    }
}
```

This is an illustrative snippet; imports, bean registration, and a `Client` interface are needed. When the container supports proxying, `getClient() != null` does not prove a target bean exists. It only proves the field holds a proxy reference.

### 3.2. A Proxy Is Not a Copy of the Target

A lazy-resolution proxy is not a second domain object `new ExpensiveClient()`. It is a **bridge** to the container to fetch the target. When the target is a singleton, the proxy can cache the singleton target after the first resolution; subsequent calls use that target. When the target is not a singleton, the proxy can re-resolve the target on each access, per `@Lazy`'s Javadoc.

Distinguish:
- **Proxy identity:** the consumer holds the same proxy reference.
- **Target identity:** the object behind the proxy can be a singleton, prototype, or scoped proxy target.
- **Bean definition name:** the name used by the container to register the target, not necessarily the Java class name.

### 3.3. Interface Proxies and Class-Based Proxies

When the injection type is an interface, Spring can create a JDK dynamic proxy implementing that interface. With concrete class injection, Spring may need a class-based proxy mechanism; final classes, final methods, visibility, and AOP settings can impose limitations on proxy creation/interception.

For the demo lesson, we deliberately inject the **`Gateway` interface** so JDK proxy semantics are straightforward and easy to verify. Do not assume every `@Lazy` proxy will have a fixed class name or always use CGLIB.

### 3.4. Why `getClass()` and `instanceof` Are Not Proof the Target Was Created

`proxy.getClass()` gets the Java runtime class of the **proxy**, which does not constitute evidence that the inner target has been initialized. `proxy instanceof Gateway` only shows that the proxy implements the `Gateway` interface/type. More reliable ways to check target creation are:
- a counter inside the factory method/constructor;
- `beanFactory.containsSingleton("gateway")` when the target is a singleton;
- intentionally recorded side effects;
- behavior assertions after the call.

Do not call `proxy.toString()`, `equals()`, or a business method just to "check if it's a proxy" if you do not want to accidentally make Spring resolve the target. Depending on the proxy implementation, those calls may pass through the interceptor/target source.

## 4. Three Distinct Moments: Inject Proxy, Resolve Target, Initialize Bean

An application can go through:

1. **Bean definition registration:** Spring knows metadata for `gateway` and `consumer`, not necessarily having instances yet.
2. **Consumer bean instantiation:** Spring creates the consumer and supplies the proxy to the `@Lazy Gateway` parameter.
3. **Target dependency resolution:** the proxy is invoked, and Spring identifies the target bean by type/qualifier/name and candidate rules.
4. **Target bean instantiation/initialization:** if the target does not yet exist, the BeanFactory constructs the object, injects dependencies, and runs lifecycle callbacks/post-processors.
5. **Target method invocation:** the business method runs on the target/proxy chain.
6. **Context closing:** the container invokes destroy callbacks on managed singletons per scope/lifecycle semantics.

Stages 3 and 4 can happen together on the first call, though not necessarily. If an eager singleton target was already created by the context, the proxy simply fetches the existing bean. If the target is a prototype, multiple calls can lead to multiple target instances.

### 4.1. Distinguish Deferring Resolution from Deferring Instantiation

`@Lazy` at the injection point defers **resolving the target for that consumer**. It is not a switch guaranteeing the target bean is **never** created beforehand. Another bean may inject the target directly, `@DependsOn` may pull it into startup, or application code may call `context.getBean(Target.class)` early.

Therefore, when measuring "true laziness", you must inspect **every path creating the target** in the context and the target bean definition's lazy policy.

### 4.2. Do Not Assume Lazy Means Async

The lazy proxy performs lookup when invoked; by default the business method still executes **synchronously on the calling thread**, unless there is an independent async mechanism such as `@Async` or a reactive pipeline.

If the target constructor blocks on the network, the first proxy call can also block on the network. Lazy only shifts latency to another moment; it does not make latency free.

### 4.3. Lazy Is Not Hot Swap

Once created, a singleton target is not automatically replaced with another implementation when properties change. `@Lazy` does not replace `@RefreshScope`, a routing layer, or runtime reconfiguration mechanisms. For prototype/scoped beans, resolution behavior follows the scope, yet do not infer that changing a config file after `refresh()` will alter bean definitions.

## 5. Initialization Timing Matrix

Suppose there is an eagerly created singleton `Consumer` and a `Gateway`:

| Target definition | Consumer's injection point | Other path creating Gateway? | Typical outcome at startup |
| --- | --- | --- | --- |
| Eager singleton | Direct injection | No | Gateway is created at startup |
| `@Lazy` singleton | Direct injection | No | Gateway is still created because consumer needs target |
| Eager singleton | `@Lazy` proxy | No | Gateway is pre-instantiated due to its own eager definition |
| `@Lazy` singleton | `@Lazy` proxy | No | Consumer can be created; Gateway does not need initialization yet |
| `@Lazy` singleton | `@Lazy` proxy | Another eager bean needs target | Gateway may still be created at startup |
| Prototype | Direct injection into singleton | No | One prototype is supplied when consumer is created |
| Prototype | `@Lazy` proxy | No | Target may be freshly resolved for each method invocation |
| No bean | Direct required injection | No | Usually fails during startup/injection |
| No bean | `@Lazy` proxy | No | Consumer may be created; fails when proxy is called |

The table assumes Spring's injection-point proxy infrastructure is active and the dependency types are proxiable. It is not a commitment for every lifecycle/FactoryBean/custom BeanPostProcessor outside the example.

### 5.1. `@Lazy` on Target Alone Is **Not Enough** If Consumer Is Eager

```java
@Bean
@Lazy
Gateway gateway() {
    return new RealGateway();
}

@Bean
Consumer consumer(Gateway gateway) {
    return new Consumer(gateway);
}
```

Spring needs `Gateway` to create `Consumer`; the target is pulled in despite being marked lazy. This is an important principle from the Spring reference.

### 5.2. `@Lazy` at Injection Point Alone Is **Not Enough** If Target Is Eager

```java
@Bean
Gateway gateway() {
    return new RealGateway();
}

@Bean
Consumer consumer(@Lazy Gateway gateway) {
    return new Consumer(gateway);
}
```

The consumer receives a proxy, yet if `gateway` is a non-lazy singleton eagerly pre-instantiated by the context, the target may already have been created during startup. Do not see an injection proxy and claim you reduced total singleton creation time.

### 5.3. Proper Combination When Deferral Is Truly Needed

```java
@Bean
@Lazy
Gateway gateway() {
    return new RealGateway();
}

@Bean
Consumer consumer(@Lazy Gateway gateway) {
    return new Consumer(gateway);
}
```

In a context where no other path resolves `gateway`, the consumer can start up without initializing `gateway`. The first business method touching the proxy triggers target resolution.

## 6. When Do Errors Surface?

The most important point of this lesson is that **when an error is reported changes according to the dependency route**, even though the nature of the error is the same.

### 6.1. Target Bean Does Not Exist

No `Gateway` in the registry:

```java
@Component
class Consumer {
    private final Gateway gateway;

    Consumer(@Lazy Gateway gateway) {
        this.gateway = gateway;
    }

    String charge() {
        return gateway.pay();
    }
}
```

This is an illustration; imports/interface and bean registration are required. Per `@Lazy` Javadoc, a lazy-resolution proxy **is still injected** even when the target does not exist. `ApplicationContext` can refresh successfully, yet when `charge()` calls `gateway.pay()`, the proxy resolves the dependency and Spring throws an exception such as `NoSuchBeanDefinitionException` on certain lookup paths.

If `@Lazy` is removed from the injection point and it remains a required dependency, Spring usually detects the missing bean when creating `Consumer`. This is the meaning of **fail-fast** versus **fail-late**.

### 6.2. Target Bean Definition Exists, Yet Factory Method/Constructor Fails

```java
@Bean
@Lazy
Gateway gateway() {
    throw new IllegalStateException("Remote configuration invalid");
}
```

If `Consumer` receives the target via an `@Lazy Gateway` proxy and nobody creates the target at startup, the context can refresh. The first call going through the proxy makes the BeanFactory execute the factory method, resulting in a `BeanCreationException` (usually wrapping `IllegalStateException`).

Do not say "`@Lazy` catches the error for Spring" — the error still happens, it is merely **shifted to the target-usage milestone**. In production, this could be the first request/queue message, which is harder to observe than a startup failure without proper logs/metrics.

### 6.3. Target Is an Eager Singleton Yet Fails Creation

If the target bean does not have `@Lazy`:

```java
@Bean
Gateway gateway() {
    throw new IllegalStateException("Configuration invalid");
}
```

even if a consumer has an `@Lazy Gateway` injection point, the context can still eagerly instantiate the target singleton and fail **right during refresh**. An injection proxy does not prevent the eager initialization mechanism of the target definition.

### 6.4. Target Succeeds Yet Business Method Fails

A target being created and initialized successfully does not mean business methods will never throw. Business errors such as validation, network timeouts, or database conflicts can occur on **any method call**, not solely the first call through the proxy.

Separate:
- **Dependency resolution failure:** no candidate exists or can be selected.
- **Bean creation failure:** constructor/factory/init callback throws.
- **Business invocation failure:** method runs yet raises a business error.
- **Proxy creation failure:** unable to create a suitable proxy for the injection type (e.g., proxying constraints on a concrete/final class).

### 6.5. Proxy Type Errors Can Surface Early

If an injection point requests a concrete final class that cannot be subclassed/proxied by the active strategy, Spring can fail **when creating the proxy/injecting the consumer**, before any business method runs.

Therefore the statement "every error with `@Lazy` is deferred" is false. The Javadoc guarantees lazy target resolution semantics assuming the proxy is created successfully; AOP/proxy configuration errors and certain metadata errors can still occur at context startup.

## 7. Optional Dependencies: Do Not Use a Proxy as a Bean Existence Check

An easily confused pattern:

```java
@Autowired(required = false)
@Lazy
private OptionalGateway optionalGateway;
```

Even when the target does not exist, a lazy-resolution proxy can still be injected. Therefore:

```java
if (optionalGateway != null) {
    optionalGateway.execute();
}
```

does not prove the target is present. The `execute()` call itself may throw an exception. Spring's Javadoc warns that injection-point lazy proxies have unintuitive behavior for optional dependencies.

### 7.1. Use `ObjectProvider<T>` When You Need Optional, Lazy, and Lookup Timing Control

```java
@Component
class NotificationService {
    private final ObjectProvider<OptionalGateway> gateways;

    NotificationService(
            ObjectProvider<OptionalGateway> gateways) {
        this.gateways = gateways;
    }

    void notifyIfConfigured() {
        OptionalGateway gateway = gateways.getIfAvailable();
        if (gateway != null) {
            gateway.execute();
        }
    }
}
```

This is illustrative code; imports and the `OptionalGateway` type are required. `ObjectProvider` belongs to `org.springframework.beans.factory`. It holds a **lookup handle**, not an already-resolved dependency target.

- `getObject()`: requests a matching object, and can throw when absent or ambiguous.
- `getIfAvailable()`: returns `null` when absent, yet can still fail if multiple unresolved candidates exist or bean creation is broken.
- `ifAvailable(Consumer<T>)`: runs a callback if an object exists; avoid confusing "absent" with a business method throwing.
- `getIfUnique()`: useful when only a single unique candidate is accepted; check qualifier/primary semantics in your Spring version.

Using `ObjectProvider` does not guarantee avoiding exceptions if the target **has a definition yet fails creation**. It expresses optional/late lookup more clearly than an injection proxy mistaken for a nullable field.

### 7.2. `Optional<T>` and `@Nullable` Solve a Different Problem

Spring supports optional dependency injection with `Optional<Gateway>` or `@Nullable Gateway` at appropriate injection points. However, if the consumer needs to look up again at **usage time**, a provider is more suitable: `Optional` is resolved at injection time, whereas `ObjectProvider` allows actively querying the container when needed.

Do not combine `@Lazy` and `Optional<T>` assuming they always share the same lifecycle semantics. Test the specific configuration.

### 7.3. Do Not Use `@Lazy` to Hide Missing Config

If `Gateway` is a required business dependency, pushing errors from startup to the first request usually makes the system **less reliable**, not better. Lazy can be used to reduce initialization cost when a feature is not yet called, yet readiness checks/integration tests are still needed to ensure required paths have sufficient resources.

## 8. Singleton and Prototype Under a Lazy-Resolution Proxy

Spring's `@Lazy` Javadoc describes caching when a singleton target is first resolved, and **re-resolution on each access** when the target is not a singleton.

### 8.1. Singleton Target

```java
@Bean
@Lazy
Gateway gateway() {
    return new DefaultGateway();
}

@Bean
Consumer consumer(@Lazy Gateway gateway) {
    return new Consumer(gateway);
}
```

The first time `consumer` calls `gateway.call()`, Spring locates and initializes the singleton. Subsequent calls normally reuse the same singleton target. The proxy does not create a new bean per method invocation merely because the injection point has `@Lazy`.

### 8.2. Prototype Target

```java
@Bean
@Scope("prototype")
RequestToken requestToken() {
    return new DefaultRequestToken();
}

@Bean
TokenService tokenService(@Lazy RequestToken token) {
    return new TokenService(token);
}
```

A lazy-resolution proxy to a prototype dependency can ask the BeanFactory to resolve the target **each time a method is invoked through the proxy**. This differs from injecting a prototype directly into a singleton, where the prototype is normally created only once when the singleton is initialized.

However, do not equate proxy-per-invocation with **request scope** or thread-local isolation. If you need one object spanning an entire HTTP request, use proper web request scope/scoped proxies rather than creating a new prototype per method invocation and expecting shared state.

### 8.3. Note on Stateful Prototypes

Suppose `RequestToken` is mutable:

```java
token.setId("one");
return token.getId();
```

With a lazy prototype proxy re-resolving the target on every method call, `setId(...)` and `getId()` **may operate on two different prototype instances**. This is a serious trap.

If a stateful object is needed within a single use case:
- use `ObjectProvider<RequestToken>.getObject()` **once**, store the target in a local variable, and then invoke consecutive methods on it;
- or use a scoped bean matching the use-case lifecycle;
- do not expect a prototype proxy to preserve state across calls.

### 8.4. Singleton Consumer Holds One Proxy Reference

`TokenService` is a singleton and its `token` field holds only **one proxy object**. Yet the proxy can re-resolve prototype targets as needed. Thus stable field reference identity does not mean fixed target identity.

## 9. Complete Java 17+ Demo: 6 Verification Scenarios

This project uses **Spring Framework 6.2.19** and Gradle, without Spring Boot, a database, or network. It creates independent `AnnotationConfigApplicationContext`s to demonstrate:

1. `@Lazy` target + `@Lazy` injection point: consumer starts before target; the first call creates the singleton target.
2. Prototype injected via lazy proxy: each method invocation resolves a new target.
3. Missing target: proxy is still injected and error surfaces on invocation.
4. `ObjectProvider`: optional dependency with no target is handled explicitly.
5. `@Lazy` target yet consumer injects **directly**: target is created during refresh to satisfy dependency.
6. Eager target or failing factory: injection proxy does not turn an eager bean lazy, and bean creation failure can appear at startup or first invocation depending on configuration.

### 9.1. Structure

```text
lazy-injection-point-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── LazyInjectionDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'lazy-injection-point-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'LazyInjectionDemo'
}
```

Requires JDK 17+ and a compatible Gradle version. `spring-context` provides `AnnotationConfigApplicationContext`, `@Bean`, `@Lazy`, bean factory injection, and pulls in the Spring modules needed for proxy infrastructure.

### 9.2. Complete Java Source

Save `src/main/java/LazyInjectionDemo.java`:

```java
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Scope;

public class LazyInjectionDemo {

    static final AtomicInteger lazyCreated = new AtomicInteger();
    static final AtomicInteger prototypeCreated = new AtomicInteger();
    static final AtomicInteger directCreated = new AtomicInteger();
    static final AtomicInteger eagerCreated = new AtomicInteger();

    public interface Gateway {
        String call();
    }

    public record DefaultGateway() implements Gateway {
        @Override
        public String call() {
            return "ok";
        }
    }

    public record GatewayConsumer(Gateway gateway) {
        public String use() {
            return gateway.call();
        }

        public boolean holdsJdkProxy() {
            return Proxy.isProxyClass(gateway.getClass());
        }
    }

    public interface SessionToken {
        String id();
    }

    public record DefaultToken(String value) implements SessionToken {
        @Override
        public String id() {
            return value;
        }
    }

    public record TokenConsumer(SessionToken token) {
        public String id() {
            return token.id();
        }
    }

    public interface MissingPort {
        String ping();
    }

    public record MissingConsumer(MissingPort port) {
        public boolean holdsJdkProxy() {
            return Proxy.isProxyClass(port.getClass());
        }

        public String invoke() {
            return port.ping();
        }
    }

    public record OptionalConsumer(
            ObjectProvider<MissingPort> provider) {
        public boolean exists() {
            return provider.getIfAvailable() != null;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class LazyConfig {

        @Bean
        @Lazy
        Gateway gateway() {
            lazyCreated.incrementAndGet();
            return new DefaultGateway();
        }

        @Bean
        GatewayConsumer gatewayConsumer(@Lazy Gateway gateway) {
            return new GatewayConsumer(gateway);
        }

        @Bean
        @Scope("prototype")
        SessionToken sessionToken() {
            int number = prototypeCreated.incrementAndGet();
            return new DefaultToken("token-" + number);
        }

        @Bean
        TokenConsumer tokenConsumer(@Lazy SessionToken sessionToken) {
            return new TokenConsumer(sessionToken);
        }

        @Bean
        MissingConsumer missingConsumer(@Lazy MissingPort missing) {
            return new MissingConsumer(missing);
        }

        @Bean
        OptionalConsumer optionalConsumer(
                ObjectProvider<MissingPort> provider) {
            return new OptionalConsumer(provider);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DirectConfig {

        @Bean
        @Lazy
        Gateway gateway() {
            directCreated.incrementAndGet();
            return new DefaultGateway();
        }

        @Bean
        GatewayConsumer gatewayConsumer(Gateway gateway) {
            return new GatewayConsumer(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class EagerConfig {

        @Bean
        Gateway gateway() {
            eagerCreated.incrementAndGet();
            return new DefaultGateway();
        }

        @Bean
        GatewayConsumer gatewayConsumer(@Lazy Gateway gateway) {
            return new GatewayConsumer(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DeferredFailureConfig {

        @Bean
        @Lazy
        Gateway gateway() {
            throw new IllegalStateException("late factory failure");
        }

        @Bean
        GatewayConsumer gatewayConsumer(@Lazy Gateway gateway) {
            return new GatewayConsumer(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class EagerFailureConfig {

        @Bean
        Gateway gateway() {
            throw new IllegalStateException("startup factory failure");
        }

        @Bean
        GatewayConsumer gatewayConsumer(@Lazy Gateway gateway) {
            return new GatewayConsumer(gateway);
        }
    }

    private static void check(boolean condition, String reason) {
        if (!condition) {
            throw new AssertionError(reason);
        }
    }

    private static void lazyAndOptionalCases() {
        try (var context = new AnnotationConfigApplicationContext(
                LazyConfig.class)) {

            GatewayConsumer gateway =
                    context.getBean(GatewayConsumer.class);
            TokenConsumer tokens =
                    context.getBean(TokenConsumer.class);
            MissingConsumer missing =
                    context.getBean(MissingConsumer.class);
            OptionalConsumer optional =
                    context.getBean(OptionalConsumer.class);

            boolean before = context.getBeanFactory()
                    .containsSingleton("gateway");
            check(!before, "gateway must not be created yet");

            boolean proxy = gateway.holdsJdkProxy();
            check(proxy, "expected interface lazy proxy");

            System.out.println("lazy.before=" + before);
            System.out.println("lazy.proxy=" + proxy);

            String first = gateway.use();
            boolean after = context.getBeanFactory()
                    .containsSingleton("gateway");
            String second = gateway.use();

            check("ok".equals(first) && "ok".equals(second),
                    "unexpected gateway result");
            check(after && lazyCreated.get() == 1,
                    "singleton target should be created once");

            System.out.println("lazy.call1=" + first);
            System.out.println("lazy.after=" + after);
            System.out.println("lazy.call2=" + second);
            System.out.println("lazy.created=" +
                    lazyCreated.get());

            String tokenOne = tokens.id();
            String tokenTwo = tokens.id();
            check(!tokenOne.equals(tokenTwo),
                    "prototype target should change");
            check(prototypeCreated.get() == 2,
                    "expected two prototype instances");

            System.out.println("prototype.first=" + tokenOne);
            System.out.println("prototype.second=" + tokenTwo);
            System.out.println("prototype.created=" +
                    prototypeCreated.get());

            boolean missingProxy = missing.holdsJdkProxy();
            check(missingProxy, "expected missing-port proxy");
            boolean missingFailure = false;
            try {
                missing.invoke();
            } catch (BeansException expected) {
                missingFailure = true;
            }
            check(missingFailure,
                    "missing target must fail on invocation");

            boolean optionalExists = optional.exists();
            check(!optionalExists, "missing port must be absent");

            System.out.println("missing.proxy=" + missingProxy);
            System.out.println("missing.failsOnCall=" +
                    missingFailure);
            System.out.println("optional.exists=" +
                    optionalExists);
        }
    }

    private static void directCase() {
        try (var context = new AnnotationConfigApplicationContext(
                DirectConfig.class)) {

            GatewayConsumer consumer =
                    context.getBean(GatewayConsumer.class);
            check(directCreated.get() == 1,
                    "direct injection should create lazy target");
            check(!consumer.holdsJdkProxy(),
                    "direct injection should hold target");

            System.out.println("direct.createdAtRefresh=" +
                    directCreated.get());
            System.out.println("direct.proxy=" +
                    consumer.holdsJdkProxy());
        }
    }

    private static void eagerCase() {
        try (var context = new AnnotationConfigApplicationContext(
                EagerConfig.class)) {

            GatewayConsumer consumer =
                    context.getBean(GatewayConsumer.class);
            check(eagerCreated.get() == 1,
                    "eager singleton should exist at refresh");

            System.out.println("eager.createdAtRefresh=" +
                    eagerCreated.get());
            System.out.println("eager.proxy=" +
                    consumer.holdsJdkProxy());
        }
    }

    private static void deferredFailureCase() {
        try (var context = new AnnotationConfigApplicationContext(
                DeferredFailureConfig.class)) {

            GatewayConsumer consumer =
                    context.getBean(GatewayConsumer.class);
            boolean failed = false;
            try {
                consumer.use();
            } catch (BeansException expected) {
                failed = true;
            }
            check(failed, "expected deferred bean creation failure");

            System.out.println("deferred.failureOnCall=" +
                    failed);
        }
    }

    private static void eagerFailureCase() {
        boolean failedAtRefresh = false;
        try (var context = new AnnotationConfigApplicationContext(
                EagerFailureConfig.class)) {
            throw new AssertionError("expected refresh to fail");
        } catch (BeansException expected) {
            failedAtRefresh = true;
        }
        check(failedAtRefresh, "expected startup failure");
        System.out.println("eager.failureAtRefresh=" +
                failedAtRefresh);
    }

    public static void main(String[] args) {
        lazyAndOptionalCases();
        directCase();
        eagerCase();
        deferredFailureCase();
        eagerFailureCase();
    }
}
```

### 9.3. Run Command

In the `lazy-injection-point-demo` directory:

```bash
gradle run --quiet
```

If using the Gradle Wrapper on Linux/macOS:

```bash
./gradlew run --quiet
```

On Windows PowerShell:

```powershell
.\gradlew.bat run --quiet
```

Output from `System.out.println`:

```text
lazy.before=false
lazy.proxy=true
lazy.call1=ok
lazy.after=true
lazy.call2=ok
lazy.created=1
prototype.first=token-1
prototype.second=token-2
prototype.created=2
missing.proxy=true
missing.failsOnCall=true
optional.exists=false
direct.createdAtRefresh=1
direct.proxy=false
eager.createdAtRefresh=1
eager.proxy=true
deferred.failureOnCall=true
eager.failureAtRefresh=true
```

Additional Spring/Gradle logging messages may appear, especially in contexts that **intentionally throw** exceptions. The lines above are the business output deliberately printed; the demo uses `check(...)` to throw `AssertionError` if assumptions do not hold.

### 9.4. Why Does Case 1 Truly Defer the Target?

`gateway()` is declared `@Bean @Lazy`, so its singleton definition is not automatically pre-instantiated. `gatewayConsumer(@Lazy Gateway gateway)` receives a lazy proxy without forcing the BeanFactory to create `Gateway` immediately. When `gateway.use()` is called the first time, the proxy resolves the target and `gateway()` runs. The counter increases from 0 to 1; the second call reuses the singleton, keeping the counter at 1.

`containsSingleton("gateway")` checks the singleton cache in the BeanFactory; it does not check **whether or not a bean definition exists**. Even when `containsSingleton` returns false, a valid bean definition may already exist.

### 9.5. Why Does Prototype Create Two Instances?

`sessionToken()` has `@Scope("prototype")`; a lazy proxy is injected into `TokenConsumer`. When the consumer calls `tokens.id()` twice, target resolution can create two `DefaultToken`s, from `token-1` to `token-2`. This demonstrates Spring `@Lazy` non-singleton re-resolution, not one token mutating its value on the same instance.

### 9.6. Why Does a Missing Target Not Break Startup?

`MissingConsumer` receives `@Lazy MissingPort missing`. Spring can create a proxy for the `MissingPort` interface without resolving the target yet. Calling `getClass()` on the proxy does not materialize the bean. Only when `missing.invoke()` calls `port.ping()` does the BeanFactory attempt to resolve `MissingPort` and report an error. The demo catches `BeansException` to pinpoint where the error occurred; production code should log the root cause and distinguish missing beans from other logic errors.

### 9.7. Why Does `ObjectProvider` Return False?

`OptionalConsumer` receives `ObjectProvider<MissingPort>`. When `exists()` calls `getIfAvailable()`, no `MissingPort` bean exists so it returns null; the test prints `optional.exists=false`. This is a more sensible API when checking the existence of an optional dependency.

### 9.8. Why Does Direct Injection Pull the Lazy Target into Startup?

In `DirectConfig`, the `Gateway` target is marked `@Lazy`, yet `gatewayConsumer(Gateway gateway)` has no `@Lazy` on the parameter. The eager consumer needs the real target to run its factory method, so `gateway()` is invoked during `refresh()`; `direct.createdAtRefresh=1` and `direct.proxy=false`.

### 9.9. Why Is the Eager Target Still Created Even Though the Consumer Has a Proxy?

`EagerConfig.gateway()` does not carry `@Lazy`. `AnnotationConfigApplicationContext` normally pre-instantiates non-lazy singletons, so after `refresh()` the counter is already 1. The consumer has an injection-point `@Lazy` so the field still holds a proxy, yet the target has already been created; thus `eager.proxy=true` does **not** mean `eager.createdAtRefresh` equals 0.

### 9.10. Two Factory Failures with the Same Cause Yet Different Timing

`DeferredFailureConfig` marks the target bean `@Lazy`, and the consumer receives a proxy. `refresh()` completes; only on the first call is `Gateway` constructed, throwing `IllegalStateException` wrapped by Spring as a bean creation error. Output `deferred.failureOnCall=true`.

`EagerFailureConfig` declares the target eager, so the BeanFactory executes the failing factory method at startup, before the application even retrieves the consumer. Output `eager.failureAtRefresh=true`.

**Demo conclusion:** choosing lazy/eager affects when the error surfaces, not whether the error disappears.

## 10. Common Mistakes When Using Proxies at Injection Points

| Symptom / misconception | Cause | How to fix |
| --- | --- | --- |
| "Used `@Lazy` yet startup is still slow" | Target definition is still eager or another consumer needs target | Mark target lazy and check all dependency edges |
| "Consumer created means target exists" | Proxy was injected even before target resolution | Check target via provider/readiness test or invoke use case |
| `@Autowired(required=false) @Lazy` is still non-null | Lazy proxy is always created when supported | Use `ObjectProvider`/`Optional` appropriately |
| Missing bean only fails on first request | Injection-point proxy causes fail-late | Test startup contract, readiness, and critical paths |
| Target constructor throws yet context still refreshes | Target is lazy and proxy defers bean creation | Distinguish startup and first-invocation failures |
| Context fails despite lazy injection point | Target is eager or proxy creation/config errors | Check target definition/proxyability |
| `proxy.getClass()` is not the implementation class | That is the proxy's class | Check interface/behavior, do not rely on exact proxy class |
| `proxy == target` is false | Proxy is an intermediary object | Use contract methods and proper bean identity |
| Prototype method calls do not share state | Proxy re-resolves on each access | Fetch target once via provider if stateful use case is needed |
| Self-invocation bypasses proxy | Internal method call on target skips wrapper | Redesign call boundary; do not treat lazy as an AOP business feature |
| Final class/method proxying error | Proxy strategy cannot subclass/intercept | Prefer interfaces; review proxy constraints |
| First call has a latency spike | Target initialization was shifted into the request | Use warm-up/readiness or deliberate pre-initialization |
| Thinking `@Lazy` runs async | It only shifts lookup/init timing | Use separate async infrastructure if needed |
| Target bean has credential error only discovered when user calls it | Missing config is detected late | Validate configuration at startup or health checks |
| Forgetting to close context | Target resource initialized without cleanup | Close ApplicationContext when appropriate |
| `@Lazy` removed during refactoring | Dependency becomes eager and shifts error timing | Write integration tests for creation timing |
| Changing property after refresh does not change target | Lazy is not hot reload | Use appropriate refresh/routing policies |
| Using `@Lazy` to fix circular dependencies | Only defers one resolution path | Refactor graph; test cycles/proxies/early references |
| Prototype injected directly into singleton | Target is resolved only when singleton is created | Use provider or lazy proxy if per-use lookup is wanted |

### 10.1. Do Not Diagnose from Short Exception Messages

An error like `BeanCreationException` can wrap many root causes:
- a constructor throwing `IllegalArgumentException`;
- a bean definition missing a property;
- a condition/profile preventing a dependency from being registered;
- network client initialization failure;
- a circular dependency;
- a proxy unable to be created for the target type.

Read the full exception chain, bean name, injection point, thread, and failure milestone (during refresh vs first business call).

### 10.2. Note on Stacked AOP Proxies

A target bean may already be proxied by Spring AOP (transactions, caching, security). A lazy-resolution proxy is an intermediary layer for **dependency resolution**, and does not itself provide transactions/authorization. Calling a method may go through the lazy proxy and then reach a target bean that is an AOP proxy.

Do not unwrap/proxy-cast to the implementation class in business code. Inject an interface or a clear public contract. Test transaction/caching behavior through managed references, not objects created with `new`.

### 10.3. Limit Lazy Usage for Mandatory Infrastructure

Transaction managers, security policies, database schema validation, or a client always used right after startup may need to fail fast. Hiding errors until traffic arrives makes the failure blast radius harder to manage. If choosing lazy for a good reason (high startup cost/optional feature), add readiness contracts and test initialization on required paths.

## 11. Comparing Lazy Proxy with `ObjectProvider`, `Supplier`, and Explicit Factory

| Characteristic | Injection-point `@Lazy` | `ObjectProvider<T>` | Direct injection of `T` |
| --- | --- | --- | --- |
| What consumer receives | Proxy typed as T | Provider handle | Target bean/proxy returned by container |
| When target is resolved | When called through proxy | When code calls `getObject/getIfAvailable` | During DI, before consumer is ready |
| Missing target | May fail when invoking proxy | `getIfAvailable` indicates absence; `getObject` errors | Required injection usually fails early |
| Singleton caching | Per target scope/proxy semantics | BeanFactory singleton semantics | Same singleton reference |
| Per-use prototype | May re-resolve on each proxy invocation | Each `getObject()` can get a new prototype | Singleton consumer holds one injected prototype |
| Lookup control | Implicit via method calls | Explicit at usage site | None |
| Ease of reviewing dependencies | Moderate, proxy hides resolution | Clear if provider is named well | Clear |
| Use case | Defer calling target while using interface directly | Optional/multi-candidate/runtime lookup | Required DI, fail-fast |

### 11.1. When to Choose `ObjectProvider`?

Use a provider when you need to:
- check whether a dependency exists;
- obtain a fresh prototype **once per unit of work**;
- proactively handle missing/multiple candidates;
- choose a transparent lookup point for caching/retry calculations;
- implement a fallback service when a feature is not installed.

Example:

```java
void process(ObjectProvider<SessionToken> provider) {
    SessionToken token = provider.getObject();
    token.assign("order-1");
    token.consume();
}
```

The snippet above assumes a `SessionToken` API with two illustrative methods. Both calls operate on the same **local target instance**. If replaced with a lazy prototype proxy and two methods are called on the proxy, the target could differ between the two calls.

### 11.2. When to Choose Injection-Point `@Lazy`?

When a required dependency **will exist**, yet the consumer does not need to call it at creation time; the interface API is stable; you want to avoid lookup boilerplate and accept late error detection risk along with proxy overhead.

For example, a reporting module that runs infrequently while the main business path does not depend on it on every request. Even so, still validate critical modules before receiving traffic that needs them.

### 11.3. When to Avoid Both?

If the consumer always uses the dependency right inside its constructor/init method, or the resource is mandatory for the application to function, direct constructor DI can be clearer and more fail-fast. If async/background creation is needed, use the corresponding startup scheduling/background initialization features; `@Lazy` alone does not schedule threads.

## 12. Testing at the Right Time and Boundaries

### 12.1. Test 1 — Target Singleton Not Created After Refresh

```java
try (var context = new AnnotationConfigApplicationContext(
        LazyInjectionDemo.LazyConfig.class)) {
    boolean created = context.getBeanFactory()
            .containsSingleton("gateway");
    if (created) {
        throw new AssertionError("Gateway created too early");
    }
}
```

This is a **test fragment** based on the Section 9 demo, requiring appropriate imports/package names. It verifies a bean creation milestone that simply inspecting startup logs could miss.

### 12.2. Test 2 — Target Created Exactly Once

```java
GatewayConsumer consumer = context.getBean(
        GatewayConsumer.class);
consumer.use();
consumer.use();
if (createdCounter.get() != 1) {
    throw new AssertionError("Expected singleton init once");
}
```

This is a **pseudo-test fragment**: `createdCounter` is a counter provided by the test setup. It demonstrates verifying singleton caching/creation instead of merely observing identical outputs from two calls.

### 12.3. Test 3 — Missing Dependency Throws at Invocation

- Create a context with a `@Lazy MissingPort` consumer without declaring a `MissingPort` bean.
- Verify context refresh succeeds.
- Verify the proxy reference exists.
- Call `port.ping()` and inspect the exception family/root cause.
- State clearly "first method invocation failed" in the assertion message.

This prevents regressions: a refactoring that removes `@Lazy` can shift the failure from invocation to refresh; the test will surface that change.

### 12.4. Test 4 — Same Failure on Eager Bean Fails Fast

Define an eager target bean with a throwing factory method. Ensure `new AnnotationConfigApplicationContext(Config.class)` fails. If you merely catch any `Exception` and consider the test passed, you might mask unrelated XML/annotation/constructor errors; inspect the root cause and bean name.

### 12.5. Test 5 — Prototype Re-Resolution

```java
String first = tokenConsumer.id();
String second = tokenConsumer.id();
if (first.equals(second)) {
    throw new AssertionError("Expected distinct targets");
}
```

This demo excerpt assumes the target generates distinct IDs. It is a test of target scope, not a test of `proxy != target`.

### 12.6. Test 6 — Do Not Create Target When Only Inspecting Proxy Class

To ensure a getter/proxy check does not trigger the target, compare counters before/after `Proxy.isProxyClass(proxy.getClass())`. Avoid accidentally invoking `toString` in loggers or debugger watches when testing "target not yet resolved".

### 12.7. Test 7 — Replace Optional Dependency with Provider

Declare `ObjectProvider<MissingPort>` and assert `getIfAvailable() == null` when no provider candidate exists. Then register a matching bean in **another context** to test the present branch. Avoid registering at runtime into an already-refreshed context while serving traffic, because concurrent mutation of the bean registry is not a default-safe workflow.

## 13. Frequently Asked Questions

### 13.1. Does `@Lazy` on a Constructor Make the Constructor Run Late?

If the annotation is placed on a **constructor parameter** `Consumer(@Lazy Gateway gateway)`, Consumer's constructor **still runs** when the Consumer bean is created. It receives a proxy. That annotation does not make the Consumer bean itself lazy. To make Consumer lazy, annotate Consumer's **definition** with `@Lazy` or configure accordingly.

### 13.2. Is the Target Bean Always Created on the First Business Method?

No. If the target is an eager singleton, it may be created at refresh; if another dependency needs it, it may also be pulled in early; if the target already exists, the proxy just looks it up. A more accurate statement: an injection-point proxy **resolves the target when called**, while **target creation** only happens if the bean does not yet exist and scope/lifecycle require creation.

### 13.3. Must Injection-Point `@Lazy` Be Used with `@Autowired`?

The Javadoc describes it on injection points annotated with `@Autowired` or `@Inject`, and Spring bean factory method parameters also have corresponding dependency resolution mechanics. In JavaConfig, `@Bean Consumer consumer(@Lazy Gateway gateway)` is designed to work. If you create Consumer manually via `new Consumer(...)` outside Spring, the parameter annotation is not automatically interpreted by the JVM as a proxy.

### 13.4. Does an `@Lazy` Annotation on an Interface Automatically Make Every Implementation Lazy?

Not by default. Bean definitions and injection points are where Spring applies the relevant metadata. Inspect the actual target implementation beans and injection points; do not rely on an arbitrary annotation on an interface to infer that all candidate beans are lazy.

### 13.5. Why Is Interface Injection Usually Easier with Proxies?

A JDK dynamic proxy only needs to implement the interface. Concrete class proxies may rely on subclassing and hit final class/method constraints. Interface contracts reduce coupling between consumer and implementation and make proxy creation easier. This is a recommendation, not a requirement that every dependency in Spring be an interface.

### 13.6. Does the Proxy Cache Method Results?

No. Singleton target caching and **method result caching** are two different things. A lazy-resolution proxy can retain the singleton target reference, yet does not automatically memoize the output of `gateway.call()`. If a method queries a database twice, two calls can still execute the operation twice unless separate caching exists.

### 13.7. Is the Created Proxy a `@Transactional` Proxy?

Not merely because of `@Lazy`. A lazy-resolution proxy serves deferred dependency resolution. A target bean may additionally be proxied by AOP post-processors for transactions/caching/security, yet that is an independent mechanism requiring appropriate configuration.

### 13.8. What If Multiple Threads Call the Proxy Concurrently?

For a singleton bean, the BeanFactory normally guarantees singleton creation semantics, yet contention/latency when multiple threads touch the lazy target for the first time must be measured under realistic workloads. For prototypes, multiple invocations can obtain multiple instances. Avoid relying on factory call counts/ordering in concurrency tests without checking bean scope and application synchronization.

### 13.9. Does Lazy Help Resolve Circular Dependencies?

It can defer an edge in the dependency graph and allow some cases to initialize via a proxy, yet does not turn a cyclic graph into good design; errors may shift from startup to runtime. Redesign module boundaries, events/callbacks, or factory abstractions to eliminate cycles whenever possible.

### 13.10. Should Every Bean Be Made Lazy for Fast Startup?

Not by default. Eager singleton creation enables fail-fast behavior, warm caches, and verifying infrastructure before accepting traffic. Overly broad laziness shifts errors and memory/CPU spikes onto the first critical path; optimize using profiling, startup metrics, and feature-specific policies.

## 14. Exercises with Answers

### Exercise 1 — Where Is the Annotation Placed?

`@Bean @Lazy Gateway gateway()` and `@Bean Consumer consumer(Gateway gateway)`. When `Consumer` is eager, is `Gateway` guaranteed not to be created at startup?

**Answer:** No. Eager `Consumer`'s dependency pulls the lazy target into bean creation.

### Exercise 2 — Only the Injection Point Is Lazy

`@Bean Gateway gateway()` (eager) and `consumer(@Lazy Gateway gateway)`. Does the presence of a `proxy` prove the target has not been created?

**Answer:** No. An eager singleton target can be pre-instantiated during refresh.

### Exercise 3 — Both Definition and Injection Point Are Lazy

`@Bean @Lazy Gateway gateway()` and consumer receives `@Lazy Gateway`, with no other reference to `Gateway`. What is the expected target creation milestone?

**Answer:** The first method call through the lazy proxy (unless another lookup/usage path creates the bean earlier).

### Exercise 4 — Missing Target

There is no `MissingPort` bean, yet a consumer has `@Lazy MissingPort`. Can the context refresh successfully?

**Answer:** Yes, if the proxy is created validly. When a method is called on the proxy, the BeanFactory can report the missing bean.

### Exercise 5 — Nullable Field

`@Autowired(required=false) @Lazy Gateway gateway`. Does `gateway != null` confirm the `Gateway` bean actually exists?

**Answer:** No. The proxy reference can be non-null even when the target is missing. Use `ObjectProvider.getIfAvailable()` or an explicit optional policy.

### Exercise 6 — Is the Proxy a Real Bean?

A consumer holds a `Gateway` proxy and one method call triggers the singleton target. Are two `Gateway` domain instances created?

**Answer:** No. The proxy is an intermediary object; the singleton target is the managed domain bean. Proxy identity and target identity differ.

### Exercise 7 — Singleton Target

A consumer calls the same method through a lazy proxy five times. Must the `@Bean Gateway` factory run five times?

**Answer:** No; with a singleton target and no reset, the factory normally runs once when the target is created.

### Exercise 8 — Prototype Target

A consumer has `@Lazy Token token`, and the `Token` target is a prototype. Can two `token.id()` calls retrieve two target objects?

**Answer:** Yes. A lazy-resolution proxy can re-resolve a non-singleton on each access.

### Exercise 9 — Stateful Prototype

`token.setValue("A")` followed immediately by `token.getValue()` on a lazy prototype proxy. Is `get` guaranteed to return `A`?

**Answer:** No. Two calls may resolve two different instances. Use a provider to obtain a single prototype target for the unit of work.

### Exercise 10 — When Does the Error Happen?

Target `@Bean @Lazy Gateway gateway()` throws an exception in the factory method, and consumer receives `@Lazy Gateway`. No other lookups exist. Where will the error most likely surface?

**Answer:** When the first method call through the proxy causes the BeanFactory to create the target.

### Exercise 11 — Failing Eager Factory

Remove `@Lazy` from the target definition, keeping `@Lazy` at the consumer injection point. The factory throws an exception. Is the context guaranteed to still refresh?

**Answer:** No. Eager singleton creation can fail during refresh.

### Exercise 12 — Is Lazy Async?

A `Gateway` constructor takes 5 seconds. Does using a lazy proxy prevent the first call from waiting 5 seconds?

**Answer:** No. The first call can block on synchronous creation. Async requires a separate mechanism.

### Exercise 13 — Missing Candidate and Provider

What does `ObjectProvider<Gateway>.getIfAvailable()` normally return when no target exists?

**Answer:** `null` per contract when no candidate exists. If a candidate exists yet fails initialization or causes ambiguity, an exception can still occur.

### Exercise 14 — Proxy getClass

`Proxy.isProxyClass(client.getClass())` is true. Does this prove the lazy target has already been created?

**Answer:** No. It identifies a proxy class, without confirming target instantiation.

### Exercise 15 — Annotation on Bean Definition

`@Lazy` is placed only on `@Component HeavyJob`, and another singleton injects `HeavyJob` directly. Can the container create `HeavyJob` at startup?

**Answer:** Yes, because it must satisfy the eager dependency.

### Exercise 16 — Proxy and Transactions

An `@Lazy` proxy holds a target annotated with `@Transactional`. Can transaction infrastructure be removed since a lazy proxy already exists?

**Answer:** No. Lazy resolution does not replace transaction interception/advisors/managers.

### Exercise 17 — Consumer Initialization Timing

`Consumer` has constructor parameter `@Lazy Gateway` and `Consumer` itself is an eager singleton. When does `Consumer`'s constructor run?

**Answer:** When Spring initializes `Consumer` during startup. Only target dependency resolution is deferred behind the proxy.

### Exercise 18 — Delayed Exception

Production runs fine for 2 hours, until a rare request fails to create a lazy target. Why is this a trade-off?

**Answer:** Fast startup/fail-late trades off early detection of config/dependency errors. You need readiness/integration tests/warm-up policies proportional to criticality.

## 15. Checklist for Applying `@Lazy` at Injection Points

- Have you distinguished `@Lazy` on **target definition** from `@Lazy` at **injection point**?
- Should the target really be lazy, or is it already created eagerly through another dependency?
- Does the consumer inject a **proxy** of an appropriate type (usually an interface)?
- Are there concrete final types/methods or class-based proxy constraints?
- Is the dependency genuinely optional? If so, would `ObjectProvider` express it better?
- Are you mistakenly using `proxy != null` to confirm bean existence?
- Would shifting target creation failures from startup to the first request cause downtime?
- Have you tested no-target, broken-factory, eager-factory, and healthy-target cases?
- Is the target scope singleton or prototype? Does each proxy invocation resolve the same or different target?
- With a stateful prototype, could code accidentally call multiple methods via the proxy on different instances?
- Does the lazy proxy slow down the first critical path? Is there a readiness/warm-up strategy?
- Are business methods invoked through Spring-managed proxy chains when transactions/caching are needed?
- Are you confusing lazy with async/background execution or runtime refresh?
- Do tests use creation counters/`containsSingleton` and assert timing instead of only inspecting the proxy class?
- Are context cleanup and errors/logs/metrics handled properly?

## 16. Summary

In Spring Core Container, **`@Lazy` on a bean definition** controls whether a bean is eagerly pre-instantiated; **`@Lazy` at an injection point** creates a **lazy-resolution proxy** to defer target dependency resolution until the proxy is used. You must inspect both sides and all dependency edges to conclude that a target is actually created late.

A proxy is always injected successfully when proxy creation is valid; **a missing target may only be detected when the proxy is invoked**. That makes optional dependencies unintuitive. `ObjectProvider` expresses optional/proactive lookup better. For a singleton target, a lazy proxy can cache the target after the first resolution; for a non-singleton, it can re-resolve on each access. Therefore be careful with stateful prototype beans.

Choose lazy for **specific startup/cost/lifecycle reasons**, not as a way to patch broken dependency graphs or make exceptions vanish. What matters is not just "the bean is created later", but **where errors are detected later**, which consumer bears the latency, and whether critical usage paths are verified before production traffic.

### Official References

- [Spring Framework 6.2 — `@Lazy` Javadoc (definition vs injection-point proxy, missing target, and singleton/prototype)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Lazy.html).
- [Spring Framework 6.2 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html).
- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html).
- [Spring Framework 6.2 — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html).
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html).
- [Spring Framework 6.2 — `ContextAnnotationAutowireCandidateResolver` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/ContextAnnotationAutowireCandidateResolver.html).
- [Spring Framework 6.2 — `ObjectProvider` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/ObjectProvider.html).
