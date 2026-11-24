# Choosing Between FactoryBean, @Bean, and Factory Methods in the Spring Core Container

## 1. Objective and design question

When a Java system needs to create an HTTP client, a cryptographic object, a dynamic proxy, an SDK client, or a service assembled from multiple dependencies, there are at least three ways to write code that all look like a "factory":

1. **Plain Java factory method**: a `static` or instance method returning an object, capable of existing entirely without Spring.
2. **`@Bean` configuration method**: Spring reads a method annotated with `@Bean` as a **bean definition**, calls the method when needed to create the bean, and manages the **returned object** according to scope/lifecycle.
3. **`FactoryBean<T>`**: a **special bean** implementing Spring's contract. When looking up that bean name, the container normally exposes the **product `T`** supplied by `getObject()`, while the factory instance itself is accessed with the `&` prefix.

Choosing poorly often leads to verbose code, beans created outside the container, duplicate instances, unclosed products, or autowiring failing to discover the right type. Choosing well does not mean picking the "most powerful" solution, but picking the **simplest solution that adequately expresses ownership, creation timing, identity, and container integration**.

This lesson analyzes those criteria, provides a Java 17/Spring Framework 6.2 example, and explains when each option makes sense.

> The term **"factory method"** refers to an object-creation technique and does not by itself prove an object is Spring-managed. Meanwhile **`FactoryBean`** (capitalized like the interface name) has special semantics recognized by Spring. In Spring XML, the `factory-bean` attribute means **the bean name holding an instance factory method**, and does not have to be a `FactoryBean<T>`.

## 2. Quick decision table

| Question | Java factory method | `@Bean` method | `FactoryBean<T>` |
| --- | --- | --- | --- |
| Does it have to depend on Spring? | No | Yes, on the configuration class | Yes, the class implements a Spring interface |
| Does it automatically register the object into the container? | **No** | **Yes**, when configuration is processed | **Yes**, if the FactoryBean itself is registered as a bean |
| Who calls the object-creation code? | Java caller | Spring calls it per bean definition | Spring requests `getObject()` when the product is needed |
| Does Spring DI apply to the product? | Not automatically when caller invokes it directly | Yes, like an ordinary bean | Has FactoryBean product integration level; **not identical to the full init/destroy lifecycle** of an ordinary bean |
| Singleton/prototype product | Decided by your code | Uses `@Scope` on the bean definition | `FactoryBean.isSingleton()` + factory scope; must consider **two layers** |
| Retrieving the factory object and product separately? | Caller holds the factory reference | Depends on which beans you register | `getBean("&name")` gets the factory, `getBean("name")` gets the product |
| Spring's ability to know the type before creation | If unregistered, Spring does not know | Has info from the `@Bean` return type | `getObjectType()` and related metadata |
| Resource closing | Caller/owner bears responsibility | Spring provides destroy callbacks for managed beans | Container manages the FactoryBean; factory/caller must define cleanup for the product |
| Design complexity | Low | Low–medium | Higher, used for genuinely needed extension points |
| Default choice for typical SDK integration | Called **inside `@Bean`** | **Usually preferred** | Only when product creation semantics need special Spring handling |

**Priority rule:** start with **constructor injection + `@Bean`** (or `@Component` for classes you author). If a library only provides `ExternalSdk.createClient(config)`, simply call that static factory **inside `@Bean`**. Only implement `FactoryBean<T>` yourself when you genuinely need a container-recognized factory bean via `getObject()/getObjectType()/isSingleton()` and the product-vs-factory syntax.

## 3. Plain Java factory method: creating objects is the caller's responsibility

A factory method is a way to encapsulate `new` logic or implementation selection:

```java
public final class FormatterFactory {
    private FormatterFactory() {}

    public static Formatter forLocale(String locale) {
        return new Formatter(locale);
    }
}
```

This is an **illustrative snippet**, assuming a `Formatter` class with a `String` constructor is defined. `forLocale` is a plain Java static factory method. It can be called in any program:

```java
Formatter formatter = FormatterFactory.forLocale("vi-VN");
```

This is a usage snippet requiring no Spring. Pros: zero container dependency, easy to reuse as a library, object-creation logic lives in one place, and completely independent unit testing.

However, if you call a factory method **directly inside business code**:

```java
class ReportService {
    void generate() {
        Formatter formatter =
                FormatterFactory.forLocale("vi-VN");
        // Use formatter...
    }
}
```

then `ReportService` decides **when and how** to create the formatter. Spring does not automatically track those objects, inject fields, invoke `@PostConstruct`/`@PreDestroy`, or apply AOP merely because the application uses Spring.

### Static factory method and instance factory method

Static:

```java
Client client = ClientSdk.create("https://api.example");
```

Instance:

```java
ClientBuilder builder = new ClientBuilder(credentials);
Client client = builder.build("https://api.example");
```

These are illustrative snippets requiring `ClientSdk`/`Client`/`ClientBuilder`/`credentials` from a specific SDK. Methods can cache internally, create anew, return existing objects, or implement pooling. **Java does not automatically attach singleton/prototype scopes to factory methods**.

A Spring-injected Java factory class **also does not automatically turn every product it creates into a Spring bean**. `@Component ClientBuilder` makes the **builder** a bean, not each product returned from calling `builder.build()` registered into BeanFactory.

## 4. @Bean: wrapping factory logic into a bean definition

`@Bean` is an annotation marking a method so Spring registers a **bean definition**. Spring calls the method as a factory method when an object is needed, then applies scope/lifecycle to the returned bean.

```java
@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    ApiClient apiClient(ApiCredentials credentials) {
        return VendorSdk.createClient(credentials);
    }
}
```

This is an illustrative snippet; `ApiClient`, `ApiCredentials`, and `VendorSdk` are hypothetical classes in a real system. There is no need to implement `FactoryBean<ApiClient>` if the requirement is only creating a client through an SDK. Spring can resolve `ApiCredentials` from the container to pass into the method; the default bean name comes from the `apiClient` method, and the default scope is singleton.

**Two clear layers of responsibility:**

- **`VendorSdk.createClient(...)`** decides how to construct the object.
- **Spring `@Bean`** decides when to create it, dependency wiring, scope, and lifecycle of the result.

That is a very common combination and is the answer for many cases of "the SDK forces a static factory" or "the constructor is private".

### @Bean does not force domain code to use Spring

Classes like `ApiClient`, `VendorSdk`, or business services may import no Spring at all. Spring only appears in the configuration class:

```java
@Bean
ConnectionSettings connectionSettings(
        Environment environment) {
    return new ConnectionSettings(
            environment.getRequiredProperty("client.url"));
}
```

This is an illustrative snippet requiring `ConnectionSettings` with a matching constructor and importing `Environment`. Domain code does not need to know dependencies come from Spring.

### @Bean supports scopes

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
RequestEncoder requestEncoder() {
    return new RequestEncoder();
}
```

This is an illustrative snippet importing `Scope`/`ConfigurableBeanFactory`, assuming `RequestEncoder` exists. Each time BeanFactory directly resolves this prototype, it creates a new object. However, if the prototype is injected into a singleton via constructor **once**, the singleton keeps the instance it received; it does not automatically swap the prototype on every method call.

### @Bean supports init/destroy callbacks

```java
@Bean(initMethod = "connect", destroyMethod = "close")
RemoteChannel remoteChannel(Config config) {
    return RemoteChannel.open(config);
}
```

This is an illustrative snippet assuming `RemoteChannel` has matching methods. The returned bean receives lifecycle callbacks like a container-managed bean, including what Spring supports per configuration.

In particular, `@Bean` defaults to `destroyMethod = "(inferred)"` in Spring 6.2, which can infer `close()`/`shutdown()` when eligible. For resources borrowed from JNDI or external systems with their own owner, consider `@Bean(destroyMethod = "")` to disable inferred cleanup; do not confuse this setting with automatically disabling other `@PreDestroy`/`DisposableBean` callbacks.

## 5. FactoryBean<T>: extending BeanFactory's instantiation mechanism

`org.springframework.beans.factory.FactoryBean<T>` is the contract of **a bean acting as a factory**. Spring recognizes three methods specially:

```java
public interface FactoryBean<T> {
    T getObject() throws Exception;
    Class<?> getObjectType();
    default boolean isSingleton() {
        return true;
    }
}
```

This is an **abbreviated signature to explain the API** of Spring 6.2; annotation/Javadoc details are omitted.

- `getObject()`: produces or supplies the product.
- `getObjectType()`: tells the container the product type, useful for autowiring/type lookups **without creating the product**.
- `isSingleton()`: indicates whether the product is a shared singleton; defaults to `true`.

Registering a `FactoryBean` named `remoteClient` means:

```java
Object client  = context.getBean("remoteClient");
Object factory = context.getBean("&remoteClient");
```

This is an illustrative snippet assuming the `remoteClient` bean implements `FactoryBean`.

- `"remoteClient"` → the **product** supplied by `FactoryBean.getObject()`.
- `"&remoteClient"` → the **FactoryBean instance itself**.
- The prefix is `BeanFactory.FACTORY_BEAN_PREFIX`; not special Java syntax or a bean definition named `&remoteClient`.

These semantics make `FactoryBean` completely different from a class you simply name `RemoteClientFactory` without implementing the interface.

### getObjectType() is an architectural decision

Spring may need to infer the type when selecting candidates for constructor injection:

```java
@Override
public Class<?> getObjectType() {
    return ApiClient.class;
}
```

This is an illustrative method snippet. Return a stable type (usually the product interface or class) **without causing side effects**. Returning `null` if the type is genuinely undetermined can cause type-based autowiring to skip that FactoryBean.

Do not write:

```java
@Override
public Class<?> getObjectType() {
    return getObject().getClass(); // Anti-pattern.
}
```

because metadata queries might inadvertently connect over the network, spawn threads, or construct the product too early—even before the factory finishes initializing.

### FactoryBean is not BeanFactory

`BeanFactory` is a container-level API, whereas `FactoryBean` is just a **container-managed extension point**. `FactoryBean` does not replace BeanFactory, does not hold all bean definitions, and does not provide `getBean(...)` for the whole application.

Similar names do not imply the two interfaces are related by inheritance.

## 6. A Java 17+ program to compare all three options

This example aims to verify an **architectural decision**, not merely read definitions. An `Endpoint` type is created along four paths:

1. `@Bean` calling a **static factory method** of a hypothetical library.
2. `@Bean` calling an **instance factory method** of a collaborator.
3. A `@Bean` registering a **`FactoryBean<Endpoint>`**; the container exposes the product on lookup.
4. A prototype `@Bean` using an instance factory method to create a different instance per lookup.

The program uses Spring Framework 6.2.18, Java 17, and Gradle. No Spring Boot required.

Structure:

```text
factory-choice-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/FactoryChoiceDemo.java
```

### settings.gradle

```groovy
rootProject.name = 'factory-choice-demo'
```

### build.gradle

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'FactoryChoiceDemo'
}
```

### src/main/java/FactoryChoiceDemo.java

```java
import org.springframework.beans.factory.FactoryBean;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public class FactoryChoiceDemo {

    // Product type. A Java 17 record unaware of Spring.
    public record Endpoint(String origin) {
    }

    public record Prefix(String value) {
    }

    // Plain Java static factory method.
    public static final class ExternalSdk {
        private ExternalSdk() {
        }

        public static Endpoint create(String prefix) {
            return new Endpoint("static:" + prefix);
        }
    }

    // Plain Java instance factory method.
    public static class EndpointMaker {
        public Endpoint create(String prefix) {
            return new Endpoint("instance:" + prefix);
        }
    }

    // A special bean: Spring exposes Endpoint as the product.
    public static class EndpointFactory
            implements FactoryBean<Endpoint> {

        private final Prefix prefix;
        private Endpoint shared;
        private int calls;

        public EndpointFactory(Prefix prefix) {
            this.prefix = prefix;
        }

        @Override
        public synchronized Endpoint getObject() {
            calls++;
            if (shared == null) {
                shared = new Endpoint("factoryBean:" + prefix.value());
            }
            return shared;
        }

        @Override
        public Class<?> getObjectType() {
            return Endpoint.class;
        }

        @Override
        public boolean isSingleton() {
            return true;
        }

        public synchronized int calls() {
            return calls;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public Prefix prefix() {
            return new Prefix("blue");
        }

        @Bean
        public EndpointMaker endpointMaker() {
            return new EndpointMaker();
        }

        // @Bean retrieves the product of the static factory method.
        @Bean("staticEndpoint")
        public Endpoint staticEndpoint(Prefix prefix) {
            return ExternalSdk.create(prefix.value());
        }

        // @Bean retrieves the product of the instance factory method.
        @Bean("instanceEndpoint")
        public Endpoint instanceEndpoint(
                EndpointMaker maker, Prefix prefix) {
            return maker.create(prefix.value());
        }

        // This @Bean returns FactoryBean, not Endpoint.
        @Bean("factoryEndpoint")
        public EndpointFactory factoryEndpoint(Prefix prefix) {
            return new EndpointFactory(prefix);
        }

        // Same Java instance factory, but the product bean is prototype.
        @Bean("prototypeEndpoint")
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public Endpoint prototypeEndpoint(
                EndpointMaker maker, Prefix prefix) {
            return maker.create("prototype-" + prefix.value());
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            Endpoint fromStatic =
                    context.getBean("staticEndpoint", Endpoint.class);

            Endpoint fromInstance =
                    context.getBean("instanceEndpoint", Endpoint.class);

            Endpoint fromFactory =
                    context.getBean("factoryEndpoint", Endpoint.class);

            Endpoint factoryAgain =
                    context.getBean("factoryEndpoint", Endpoint.class);

            EndpointFactory realFactory =
                    context.getBean("&factoryEndpoint",
                                    EndpointFactory.class);

            EndpointFactory sameFactory =
                    context.getBean("&factoryEndpoint",
                                    EndpointFactory.class);

            Endpoint firstPrototype =
                    context.getBean("prototypeEndpoint", Endpoint.class);

            Endpoint secondPrototype =
                    context.getBean("prototypeEndpoint", Endpoint.class);

            // Calling the factory method using ordinary Java:
            Endpoint manual = context.getBean(EndpointMaker.class)
                    .create("manual");

            System.out.println("static=" + fromStatic.origin());
            System.out.println("instance=" + fromInstance.origin());
            System.out.println("factoryBean=" + fromFactory.origin());
            System.out.println("staticSingleton=" +
                    (fromStatic == context.getBean("staticEndpoint")));
            System.out.println("factoryProductSingleton=" +
                    (fromFactory == factoryAgain));
            System.out.println("sameFactoryInstance=" +
                    (realFactory == sameFactory));
            System.out.println("productVsFactoryDifferentTypes=" +
                    (!((Object) fromFactory instanceof FactoryBean<?>)));
            System.out.println("factoryGetObjectCalls=" +
                    realFactory.calls());
            System.out.println("prototypeDifferent=" +
                    (firstPrototype != secondPrototype));
            System.out.println("prototypeOrigin=" +
                    firstPrototype.origin());
            System.out.println("manualOrigin=" + manual.origin());
        }
    }
}
```

**Note about Java:** `Endpoint` is a `record` that does not implement `FactoryBean`. The expression `fromFactory instanceof FactoryBean<?>` directly fails to compile because the two types are incompatible. The full code above **casts to `Object` before using `instanceof`**, so it can be copy-pasted and run without changing any line.

### Run

```bash
gradle run --quiet
# If the project already has a Gradle Wrapper:
# ./gradlew run --quiet
```

Output printed by the program's `System.out`:

```text
static=static:blue
instance=instance:blue
factoryBean=factoryBean:blue
staticSingleton=true
factoryProductSingleton=true
sameFactoryInstance=true
productVsFactoryDifferentTypes=true
factoryGetObjectCalls=1
prototypeDifferent=true
prototypeOrigin=instance:prototype-blue
manualOrigin=instance:manual
```

In practice there may be runtime/framework logs, not part of the `System.out` lines listed above.

### Explanation

- `staticEndpoint`: Spring calls the `@Bean` method, which calls the static Java factory `ExternalSdk.create`. The `Endpoint` product is a singleton bean, even though `ExternalSdk` is not a Spring bean at all.
- `instanceEndpoint`: Spring resolves the `EndpointMaker` collaborator from the container, then calls the instance method `maker.create(...)` inside `@Bean`. The product is also a singleton bean.
- `factoryEndpoint`: the bean definition holds **`EndpointFactory`**, which implements `FactoryBean<Endpoint>`. `getBean("factoryEndpoint")` returns the `Endpoint` product; `getBean("&factoryEndpoint")` returns `EndpointFactory`. Because `isSingleton()==true`, the product is cached; `getObject()` only needs to be called once for the observed lookups.
- `prototypeEndpoint`: still just a `@Bean` method calling a normal Java factory, but with `@Scope("prototype")`. Two lookups create two independent instances.
- `manual`: calling `EndpointMaker.create` directly is a Java call; the created product does not automatically register a new bean definition in the context. `EndpointMaker` remains a singleton bean, while `manual` is **not** a new Spring-managed bean.

This demonstrates all three choices **inside the same container**. The difference lies in who manages the product and the contract Spring recognizes, not whether the object-creation syntax is `new`, static, or instance.

## 7. Comparing product and factory types in the example

The line `!((Object) fromFactory instanceof FactoryBean<?>)` in section 6 casts to `Object` to perform a valid runtime type check in Java 17. The result `true` confirms the `Endpoint` product is not a `FactoryBean`. This is only an illustrative check, not how an application should probe for factories using `instanceof`.

When code needs the factory itself, the clearer way is `getBean("&factoryEndpoint", EndpointFactory.class)`; when it needs the product, `getBean("factoryEndpoint", Endpoint.class)`. These two lookups show the difference in `FactoryBean`'s contract without casting or guessing from Java class names.

## 8. When to choose @Bean calling a static factory method?

Choose when a library only provides:

```java
ThirdPartyClient client =
        ThirdPartyClient.create(apiKey, timeout);
```

This is an illustrative snippet with a hypothetical API. You can register it cleanly with:

```java
@Configuration(proxyBeanMethods = false)
class ThirdPartyConfig {

    @Bean(destroyMethod = "close")
    ThirdPartyClient thirdPartyClient(
            ClientSettings settings) {
        return ThirdPartyClient.create(
                settings.apiKey(), settings.timeout());
    }
}
```

This is an illustrative configuration snippet requiring corresponding `ThirdPartyClient`/`ClientSettings`. Benefits:

- Spring resolves `ClientSettings`;
- the `ThirdPartyClient` product has a name and scope;
- the client has lifecycle callbacks if the bean definition is configured properly;
- the client is constructor-injected into services;
- SDK code stays plain Java, without being forced to implement Spring APIs.

**Do not wrap an extra custom FactoryBean** just to call a single static factory method. That adds boilerplate and increases the number of concepts and lifecycles to manage without improving behavior.

### Factories with private constructors

Java libraries often lock constructors to enforce invariants:

```java
public final class TokenCodec {
    private TokenCodec(String secret) { /* ... */ }

    public static TokenCodec fromSecret(String secret) {
        // ... validate ...
        return new TokenCodec(secret);
    }
}
```

This is an illustrative class. `@Bean TokenCodec tokenCodec(...)` calling `TokenCodec.fromSecret(...)` is the natural solution. Spring **does not require** a product to have a public constructor when you supply the object via a factory method.

## 9. When to choose @Bean calling an instance factory method?

Choose when creation requires a factory collaborator with state/dependencies:

```java
@Configuration(proxyBeanMethods = false)
class CryptoConfig {

    @Bean
    KeyProvider keyProvider(Environment env) {
        return new KeyProvider(
                env.getRequiredProperty("security.key-path"));
    }

    @Bean
    TokenSigner tokenSigner(KeyProvider provider) {
        return provider.createSigner();
    }
}
```

This is an illustrative snippet. `KeyProvider` and `TokenSigner` are application-defined types. `createSigner()` is a **Java instance factory method**; the factory collaborator `KeyProvider` is also a bean; the product `TokenSigner` is **registered separately** via the second `@Bean`.

Advantages:

- Reuses factory state/dependencies of `KeyProvider`.
- Still explicitly declares each container-managed product.
- The scope of `tokenSigner` is independent of `keyProvider`'s scope.
- Consumer code only injects `TokenSigner`, unaware of the factory implementation.

If a factory has multiple methods (create signer, verifier, decoder), you can declare multiple `@Bean` methods to register each product separately rather than forcing all products through one `FactoryBean`.

### XML: static and instance factory methods

Spring XML has explicit factory method syntax:

```xml
<bean id="staticProduct"
      class="example.LegacyFactory"
      factory-method="createStatic"/>

<bean id="legacyFactory"
      class="example.LegacyFactory"/>

<bean id="instanceProduct"
      factory-bean="legacyFactory"
      factory-method="createInstance"/>
```

This is **illustrative XML**, assuming `example.LegacyFactory` has a static `createStatic()` method, a no-arg constructor, and an instance `createInstance()` method. The attribute `factory-bean="legacyFactory"` denotes **the bean serving as the object holding the instance factory method**; it **does not require** that class to implement `org.springframework.beans.factory.FactoryBean`.

This is the source of a famous confusion in Spring docs: lowercase *factory bean* can mean "a bean holding an object-creating method", whereas capitalized `FactoryBean` is the interface with three methods and product-dereferencing semantics.

## 10. When does FactoryBean<T> truly bring value?

Choose `FactoryBean<T>` if you are writing **container integration** rather than merely registering a static product. Common characteristics:

1. **The product is a dynamic proxy** built from metadata, interfaces, or descriptors.
2. **One bean name needs to expose the product** while the factory itself has its own state/lifecycle and also needs `&name` lookup.
3. The container or framework needs to **predict the product type** via `getObjectType()` before the product is created.
4. The product has a **singleton-vs-non-singleton** contract that must be expressed on the factory, not just a simple `@Scope`.
5. Product creation can be deferred to integrate with infrastructure frameworks.
6. You are building a reusable library/infrastructure registered via bean definitions from XML, Java config, or registry APIs.

Conceptual example:

```java
public final class RemoteProxyFactory
        implements FactoryBean<RemoteService> {

    private final RemoteProxyBuilder builder;

    public RemoteProxyFactory(RemoteProxyBuilder builder) {
        this.builder = builder;
    }

    @Override
    public RemoteService getObject() throws Exception {
        return builder.createProxy(RemoteService.class);
    }

    @Override
    public Class<?> getObjectType() {
        return RemoteService.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }
}
```

This is an **illustrative class**, assuming `RemoteService` and `RemoteProxyBuilder` exist and importing `FactoryBean`. `getObject()` returns a proxy; a bean name can be injected by the `RemoteService` interface without forcing consumers to depend on a concrete proxy type.

**However, one thing needs fixing for production:** the `getObject()` method above **creates a new proxy when called directly** despite declaring `isSingleton()==true`. The container can cache the product, yet a good FactoryBean contract requires a singleton product to have a stable identity. Cache the proxy in the factory or ensure `builder.createProxy(...)` returns a shared product. This snippet only expresses the integration idea, not a complete singleton implementation.

### getObjectType() and predictability

FactoryBean needs to declare a type stable enough for Spring autowiring. Avoid calling `getObject()` from `getObjectType()`. That might execute external I/O or build an unready proxy while the container is asking for metadata.

If the type is unknown upfront, `getObjectType()` may return `null`, though type-based lookup/autowiring will be restricted. A stable public interface is a better choice if the runtime product has a dynamic class.

## 11. Scope and identity: do not confuse factory with product

### Plain Java factory method

A Java method can return:

```java
public Endpoint create() {
    return new Endpoint("new-every-time");
}
```

If a caller invokes it twice, there are two instances, unless the factory caches internally. No implicit `@Scope` is attached.

### @Bean

`@Bean Endpoint endpoint()` creates a singleton bean in the container by default. Even if the method always does `return new Endpoint(...)`, Spring does not automatically re-invoke the method on each singleton lookup. With `@Scope("prototype")`, each time BeanFactory directly creates a prototype bean it invokes the factory method again.

### FactoryBean

`FactoryBean.isSingleton()` controls the product caching contract. The FactoryBean itself has a bean definition with its own scope. For example, a singleton FactoryBean can supply:

- a singleton product if `isSingleton()==true`;
- an uncached product if `isSingleton()==false`.

Do not conclude "singleton FactoryBean means the product is always singleton" or "`isSingleton=false` is definitely prototype". A `SmartFactoryBean` provides `isPrototype()` to add independent-product semantics.

### Case of a singleton injecting a prototype

A `@Bean` method returns a prototype of the right scope, yet when a prototype is injected into a singleton via constructor, Spring resolves it **once while constructing the singleton**. If each operation needs a new object, use `ObjectProvider<Endpoint>`, lookup method injection, or a Java factory collaborator with an explicitly designed lifetime.

`FactoryBean` is not the default tool to solve every "singleton needing a prototype" problem. If the task is just requesting a fresh prototype each time, `ObjectProvider` is usually more direct.

## 12. Lifecycle and resource ownership

This criterion matters more than line count. If the product opens sockets/files/threads, who is responsible for closing them?

| Creation approach | Default ownership to consider | Cleanup direction |
| --- | --- | --- |
| Java factory method called directly outside Spring | Caller or factory per Java contract | `try-with-resources`/`finally`/explicit close |
| `@Bean` returning a singleton resource | Spring if configuration grants ownership to context | `@PreDestroy`, `DisposableBean`, `destroyMethod`, or inferred `close`/`shutdown` |
| `@Bean` returning a prototype | Caller after receiving the prototype | Close each instance yourself |
| `FactoryBean` itself as singleton | Spring manages the **factory bean instance** | Factory destroy callback on context close |
| Product created by `FactoryBean.getObject()` | Does not automatically get full destruction lifecycle of an ordinary bean | Factory tracks/closes product, or caller manages per contract |
| Resource borrowed from shared registry/JNDI | External owner | Do not auto-close; disable inferred destroy on borrowed beans when appropriate |

According to the `FactoryBean` Javadoc, the container manages the lifecycle of the **FactoryBean instance**, yet **does not automatically manage the full destruction lifecycle of the product** in the same way. Therefore if a proxy or client product holds resources, the factory must coordinate cleanup or delegate ownership to the caller.

### Singleton product holding resources

```java
final class ClientFactory
        implements FactoryBean<ManagedClient>, DisposableBean {

    private ManagedClient singleton;

    @Override
    public synchronized ManagedClient getObject() {
        if (singleton == null) {
            singleton = new ManagedClient();
        }
        return singleton;
    }

    @Override
    public Class<?> getObjectType() {
        return ManagedClient.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }

    @Override
    public synchronized void destroy() throws Exception {
        if (singleton != null) {
            singleton.close();
        }
    }
}
```

This is an illustrative snippet; it requires imports for Spring `FactoryBean`/`DisposableBean` and a `ManagedClient implements AutoCloseable` class. In real code, make `destroy()` idempotent, handle partial initialization, and prevent a closed product from being served again.

If the factory creates non-singleton products, design a tracking approach or require callers to close each product—you cannot just close a single `singleton` field.

### FactoryBean creating product in getObject and encountering an error

`getObject()` can `throws Exception`. If a socket is opened and a later step throws, the bean factory has not necessarily received a valid product to destroy. Clean up intermediate resources right inside `getObject()` with `try/finally`. This is the same rule as a `@Bean` factory method throwing before `return`.

## 13. @Configuration(proxyBeanMethods) and cross-calling @Bean methods

An important distinction when choosing `@Bean`:

```java
@Configuration(proxyBeanMethods = false)
class LiteConfig {

    @Bean
    Dependency dependency() {
        return new Dependency();
    }

    @Bean
    Consumer consumer() {
        // This is a plain Java call, NOT intercepted by Spring.
        return new Consumer(dependency());
    }
}
```

This is an illustrative snippet with hypothetical `Dependency`/`Consumer`. When `proxyBeanMethods = false`, `consumer()` calling `dependency()` directly can create **another Dependency**, not the singleton registered by the container.

What to do instead:

```java
@Configuration(proxyBeanMethods = false)
class SafeConfig {

    @Bean
    Dependency dependency() {
        return new Dependency();
    }

    @Bean
    Consumer consumer(Dependency dependency) {
        return new Consumer(dependency);
    }
}
```

Spring resolves the dependency through the container, avoiding bypassing `dependency`'s lifecycle/scope. This is an illustrative snippet, not a standalone program.

With full `@Configuration` mode and the default `proxyBeanMethods = true`, Spring can generate a CGLIB-enhanced subclass to **intercept cross-calls between `@Bean` methods**, returning the corresponding scoped bean. However, that has limitations with final classes/methods and should not be overused as a blanket solution. Parameter injection is clearer when interception is unnecessary.

**Do not confuse** `@Configuration`'s `@Bean`-method interception behavior with `FactoryBean<T>`: they are two completely different mechanisms.

## 14. XML static/instance factory methods vs. FactoryBean

Consider this XML configuration:

```xml
<bean id="encoder"
      class="example.EncodingSdk"
      factory-method="staticEncoder"/>

<bean id="codecBuilder"
      class="example.CodecBuilder"/>

<bean id="decoder"
      factory-bean="codecBuilder"
      factory-method="createDecoder"/>
```

This is illustrative XML, assuming the corresponding classes and methods exist. `encoder` and `decoder` are **ordinary bean products**, built by Spring using static/instance factory methods.

If you replace `codecBuilder` with a class implementing `FactoryBean<Decoder>` and look up `getBean("codecBuilder")`, Spring applies `FactoryBean` product semantics. However, XML `factory-bean="codecBuilder"` does not mean the same thing: it merely tells Spring to invoke an instance method on the bean named `codecBuilder` to create the `decoder` bean.

These concepts can be combined, yet they are not the same:
- Java factory method creates an object.
- XML/`@Bean` registers the product as a bean.
- `FactoryBean<T>` creates its own abstraction with product-dereferencing semantics.

Old documentation using lowercase "factory bean" makes it easy for developers to confuse it with the capitalized interface. When reading code, check the **actual type of the registered object** rather than guessing from the name.

## 15. Clarity in autowiring and testing

### Constructor injection for the product

If there is only one candidate bean of type `PricingClient`:

```java
@Service
class PriceService {
    private final PricingClient client;

    PriceService(PricingClient client) {
        this.client = client;
    }
}
```

This is an illustrative snippet needing corresponding imports/definitions. `PriceService` does not care whether `PricingClient` came from a constructor, a static factory via `@Bean`, or a `FactoryBean`. That is the goal of DI: keeping business code independent of object creation.

If there are multiple candidates of the same type, use `@Qualifier` or explicit name-based injection. The section 6 example has multiple `Endpoint` beans, so it looks up by bean name; attempting `getBean(Endpoint.class)` without a qualifier could lead to `NoUniqueBeanDefinitionException`.

### Unit testing plain factories

`EndpointMaker.create("test")` can be tested without Spring. The same applies to `ExternalSdk.create(...)` if that code is plain Java and requires no external I/O.

### Integration testing @Bean

Build `AnnotationConfigApplicationContext(Config.class)` to verify:
- The product is registered.
- `@Scope` is right.
- Dependencies flow through the container.
- Init/destroy callbacks happen at expected milestones.
- Bean names/qualifiers do not conflict.

### Integration testing FactoryBean

In addition to `getObject()` behavior when called directly, verify:
- `context.getBean("x")` returns the product.
- `context.getBean("&x")` returns the factory.
- `getObjectType()` enables type lookup.
- `isSingleton()` matches product identity.
- The product has cleanup aligned with ownership.
- `getObject()` errors propagate properly.

A passing `FactoryBean` unit test **does not prove** container dereferencing and caching work properly without an integration test.

## 16. Practical scenario table

| Need | Preferred choice | Why |
| --- | --- | --- |
| Registering an SDK client from static `create(config)` | `@Bean` calling static factory | Concise, type-safe, full scope/lifecycle |
| Client builder has constructor dependencies and creates one product | `@Bean` receiving builder then calling instance method | Keeps factory and product dependencies clear |
| Business method needs a short-lived non-bean object | Plain Java factory method | Avoids needlessly putting temporary business objects in the container |
| Singleton wants a fresh prototype repeatedly | `@Bean @Scope("prototype")` + `ObjectProvider<T>` | Product is a properly scoped bean with explicit lookup |
| Creating a client from config with one-time init/cleanup | `@Bean(initMethod/destroyMethod)` | One ordinary bean suffices |
| Product is a dynamic proxy needing to publish interface/type before creation | `FactoryBean<T>` | Spring understands product type and product dereferencing |
| Writing reusable framework integration with many product definitions | `FactoryBean<T>` or bean definition registration | Container-understood extension point |
| Product must be singleton yet factory has custom per-instance config | `FactoryBean<T>` with `isSingleton=true` or `@Bean` methods | Assess necessity of factory/product abstraction |
| External JNDI resource owned by app server | `@Bean(destroyMethod = "")` | Avoids accidentally closing borrowed resources |
| Need a Spring-independent object in a portable library | Static/instance Java factory | Avoids pulling the framework into library APIs |
| Multiple products from one factory object | Multiple `@Bean` methods calling the same factory or direct Java factory | Clear per-product scope; avoids forcing one `FactoryBean<T>` to handle multiple types |
| Product type unknown upfront and specialized framework needs delegation | `FactoryBean` with a stable product interface if available | Leverages `getObjectType()`, while avoiding null/type ambiguity |

## 17. Anti-patterns and how to fix them

### Anti-pattern A: writing a custom FactoryBean just to wrap a constructor

```java
public final class UserServiceFactoryBean
        implements FactoryBean<UserService> {
    @Override
    public UserService getObject() {
        return new UserService();
    }

    @Override
    public Class<?> getObjectType() {
        return UserService.class;
    }
}
```

This is an illustrative class (requiring imports and `UserService`). If `getObject()` always creates anew yet `isSingleton()` uses the default true, the factory also **risks violating identity expectations** when called directly. Replace with:

```java
@Bean
UserService userService() {
    return new UserService();
}
```

which suffices in most cases.

### Anti-pattern B: treating every Java factory method return value as a bean

```java
Endpoint e = context.getBean(EndpointMaker.class)
                    .create("test");
```

Instance `e` is the result of a Java call; it does **not** become a new Spring bean merely because `EndpointMaker` is a Spring bean. If Spring needs to manage the product separately, declare `@Bean`/scope accordingly.

### Anti-pattern C: calling context.getBean everywhere

```java
class BusinessUseCase {
    private final BeanFactory beanFactory;

    BusinessUseCase(BeanFactory beanFactory) {
        this.beanFactory = beanFactory;
    }

    void run() {
        Endpoint e = beanFactory.getBean("staticEndpoint", Endpoint.class);
    }
}
```

This is an illustrative snippet. It couples business code to the container and string bean names. For fixed dependencies, use constructor injection of `Endpoint` with qualifiers if needed; for dependencies created anew per scope, consider `ObjectProvider<Endpoint>`.

### Anti-pattern D: FactoryBean.getObjectType() triggering network calls

`getObjectType()` serves metadata; avoid opening connections, calling remote APIs, or constructing the product just to know its class. Give Spring a stable type via an interface/class whenever possible.

### Anti-pattern E: FactoryBean.isSingleton() differing from behavior

`isSingleton=true` while `getObject()` always creates a new object may stay hidden when retrieved through BeanFactory due to container caching, yet anyone calling the factory directly sees different behavior. Design a real shared singleton identity or return `false` if the product is truly non-singleton.

### Anti-pattern F: forgetting cleanup of FactoryBean products

Spring manages the lifetime of the factory bean instance; do not assume an `AutoCloseable` product will always have `@PreDestroy`/`destroyMethod` applied automatically like a normally registered object. The factory or caller must have explicit ownership.

### Anti-pattern G: cross-calling @Bean methods when proxyBeanMethods=false

`consumer(dependency())` is a direct Java call that can create an instance outside the singleton cache. Pass `Dependency` as an argument to `@Bean consumer(Dependency dependency)`.

### Anti-pattern H: splitting every construction step into many abstractions

If object construction is just three lines inside `@Bean`, adding `AbstractFactory` + `FactoryBean` + `Builder` + `ServiceLocator` can make the architecture hard to test and increase coupling. Add abstractions only when there are **real variations** or a clear integration contract.

## 18. Design checklist before deciding

1. Does the product need Spring to manage it as a bean? If not, a plain Java factory method may suffice.
2. Does the product only need to be created once from a constructor/static/instance factory? If yes, `@Bean` is usually the simpler choice.
3. Does the product have request/prototype scope or will it be shared as a singleton? Do bean scope and factory caching align?
4. Does the product hold external resources needing closing? Who is the owner: Spring, caller, factory, or external registry?
5. Can the product class receive DI in `@Bean` method arguments without needing a Spring-specific interface?
6. Do you genuinely need Spring to know the product type via `getObjectType()` **when only a FactoryBean definition exists**?
7. Do you need to expose both the **factory instance** and the **product** under the same bean name with `&name`?
8. Is `FactoryBean.getObject()` thread-safe, predictable, and accurate about singleton status?
9. Can `ObjectProvider` be used to retrieve fresh prototypes instead of implementing FactoryBean yourself?
10. In `@Configuration(proxyBeanMethods=false)`, have direct cross-method calls been replaced with parameter injection?
11. If there are multiple products of the same type, are bean names/`@Qualifier` set properly?
12. Are there tests proving real behavior and lifecycle through the Spring container?

## 19. Short rule to remember

A natural-language way to distinguish them:

- **"I just want to encapsulate how an object is created"** → **Java factory method**.
- **"I want Spring to manage the object that the method creates"** → **`@Bean` calling a factory method**.
- **"I am building a factory bean where Spring must understand its product and how it is exposed as an extension point"** → **`FactoryBean<T>`**.

In real code, **`@Bean` and Java factory methods are not opposites**: the most common pattern is **using both together**. `FactoryBean` is the specialized choice when you need product/factory semantics and special type/caching metadata.

**Never decide solely from a class name `XxxFactory`.** Check whether it implements `FactoryBean` or is just a Java factory class, then determine which bean is actually registered by Spring, who owns the product, and which scope it lives in.

## 20. Official sources to read and verify

- [Spring Framework Reference — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): configuring bean definitions from methods, dependency arguments, scope, and lifecycle.
- [Spring Framework Reference — Customizing Instantiation Logic with a FactoryBean](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-extension.html): FactoryBean contract and how `getBean("x")`/`getBean("&x")` work.
- [Spring Framework Reference — Bean Overview / Static and Instance Factory Methods](https://docs.spring.io/spring-framework/reference/6.2/core/beans/definition.html): constructors, static `factory-method`, XML instance `factory-bean`, and distinction from `FactoryBean`.
- [Spring Framework Reference — Using the @Configuration annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html): inter-bean references and `proxyBeanMethods` effects.
- [Spring Framework 6.2.18 API — FactoryBean](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/FactoryBean.html): `getObject()`, `getObjectType()`, `isSingleton()`, and factory/product lifecycle semantics.
- [Spring Framework 6.2.18 API — @Bean](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/Bean.html): bean definition metadata, init/destroy methods, and annotation behavior.

**Conclusion:** There is no need to implement `FactoryBean<T>` just to invoke a factory method. Put the Java factory method inside `@Bean` if you want the product to be a Spring-managed bean. When you need a container-level extension with product-vs-factory lookup, product type prediction, and factory-specific caching semantics, `FactoryBean<T>` is the right tool.
