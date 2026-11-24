# Declaring the Product Type with getObjectType in Spring FactoryBean

## Objectives

When Spring encounters a bean implementing `FactoryBean<T>`, that bean acts as **an object-creating factory registered under the bean name**. External code normally receives the factory's **product** via `getObject()`, while the factory itself can be accessed with the `&` prefix.

For the container to discover beans by type, prepare autowiring, and answer type queries such as `getType(...)` or `getBeanNamesForType(...)`, Spring needs to know **what type the expected product has without creating the product immediately**. That is the role of `FactoryBean.getObjectType()`.

This lesson belongs to the **FactoryBean** section of the Spring Framework Core Container. It focuses on the `getObjectType()` contract: what to return, when it may be called, how it affects dependency injection, how to handle products with dynamic types, and how to verify with Java 17.

After this lesson, you will be able to:

1. Distinguish **the FactoryBean type** from **the type of object produced by the FactoryBean**.
2. Implement `Class<?> getObjectType()` properly and understand why returning `null` makes finding the bean by type difficult.
3. Explain why not to call `getObject()` merely to infer the product type.
4. Write and run a `FactoryBean<ApiClient>` example, inject the product into a service, and inspect `&beanName`.
5. Distinguish `getObjectType()`, `getObject()`, and `isSingleton()`, as well as the limits of type information when generics/proxies/dynamic factories appear.
6. Diagnose the error "a named bean exists, yet is not found when autowiring by interface".

## 1. What is FactoryBean?

Spring defines the interface:

~~~java
package org.springframework.beans.factory;

public interface FactoryBean<T> {
    T getObject() throws Exception;
    Class<?> getObjectType();
    default boolean isSingleton() {
        return true;
    }
}
~~~

This is an **abbreviated signature for explanation**, not source code you write yourself inside Spring's package. In modern Spring, `getObject()` may return `null` under the contract, and `getObjectType()` may also return `null` when the type is not yet determined.

The three methods have distinct responsibilities:

| Method | Question it answers | Main effect |
| --- | --- | --- |
| `T getObject()` | What exact object is the product? | Creates or returns the object to supply to bean consumers |
| `Class<?> getObjectType()` | What Java type does the product have? | Tells Spring the expected type for dependency matching, metadata checks, and type-based bean queries |
| `boolean isSingleton()` | Does the factory always supply the same product reference so Spring can cache it? | Controls product caching/semantics |

**Key distinction:** `FactoryBean<T>` is not the `@Bean` annotation and not an arbitrary Java factory class. It is a **special Spring SPI**: when a container-managed bean implements `FactoryBean`, the normal bean name represents the *product*; the name with the `&` prefix represents the *factory*.

For example, Spring has a bean named `apiClient` implemented by `ApiClientFactoryBean`:

~~~text
getBean("apiClient")
      |
      v
Spring retrieves the FactoryBean
      |
      +-- getObjectType() --> describes product type (ApiClient.class)
      |
      +-- getObject() ----> ApiClient product

getBean("&apiClient")
      |
      v
ApiClientFactoryBean (the factory itself)
~~~

This mechanism is used when creating objects with complex logic: proxies, library clients, configurable adapters, resource wrappers, environment-selected products, or objects that cannot be declared via a simple constructor.

If you only need to return a new object from a configuration method, `@Bean` is usually enough; there is no need to write an extra `FactoryBean`. `FactoryBean` is useful when you need **type metadata, singleton semantics, and product-supplying logic** through Spring's SPI.

## 2. The exact contract of getObjectType()

Signature:

~~~java
@Override
public Class<?> getObjectType() {
    return ApiClient.class;
}
~~~

`getObjectType()` returns **the type that the FactoryBean supplies via `getObject()`**, not the type of the factory itself. For example, if `ApiClientFactoryBean implements FactoryBean<ApiClient>`, a sensible target is `ApiClient.class` or a specific appropriate product type.

Contract per the Spring Javadoc:

- May return `null` if the product type cannot be known **at query time**.
- The method may be called by Spring **before the FactoryBean finishes initialization**; do not rely on state that is only created in `afterPropertiesSet()` or `@PostConstruct`.
- For singleton products, **avoid creating the singleton just to know the type**. Ideally, estimate/know the type from metadata, constructor parameters, or pre-existing configuration.
- For prototype/non-singleton products, still return a meaningful type so the container can find the bean.
- The Javadoc warns that a `FactoryBean` returning `null` here will be **skipped during type-based autowiring** when searching for candidates; therefore, provide a stable type whenever possible.

### Return the product class, not the FactoryBean class

**Right:**

~~~java
public final class ClientFactory implements FactoryBean<ApiClient> {
    @Override
    public Class<?> getObjectType() {
        return ApiClient.class;
    }

    @Override
    public ApiClient getObject() {
        return new DefaultApiClient();
    }
}
~~~

This is an **illustrative snippet**; `ApiClient` and `DefaultApiClient` are defined in the complete runnable example in section 6.

**Semantically wrong:**

~~~java
@Override
public Class<?> getObjectType() {
    return ClientFactory.class; // Wrong: this is the factory class, not the product.
}
~~~

Spring is asking about the **product**, whereas above you returned **the factory's class**. This can prevent queries for `ApiClient.class` from recognizing the bean, while also making the type metadata inconsistent with the actual object returned by `getObject()`.

If you want to retrieve `ClientFactory` itself, use the `&` prefix or inject the FactoryBean directly via the appropriate mechanism; do not alter `getObjectType()` to serve that purpose.

## 3. Why does Spring need to know the product type before creating the object?

Suppose there is a factory bean named `apiClient` and a service:

~~~java
@Service
class CheckoutService {
    CheckoutService(ApiClient apiClient) {
        // Wants Spring to automatically determine the bean providing ApiClient.
    }
}
~~~

This illustrates constructor injection in a Spring application with complete types. To resolve the `ApiClient` parameter, BeanFactory must find a candidate assignable to `ApiClient`.

Intuitively, the process consists of:

~~~text
CheckoutService needs dependency ApiClient
              |
              v
BeanFactory lists bean definitions
              |
              v
Encounters bean "apiClient" having a FactoryBean
              |
              v
Queries / infers product type
              |
              +-- getObjectType() = ApiClient.class
              |      |
              |      v
              |   Determines valid candidate
              |      |
              |      v
              |   getObject() supplies product when actually needed
              |
              +-- getObjectType() = null
                     |
                     v
               No useful type information:
               candidate may be skipped during autowiring
~~~

**Do not infer that every autowiring pass calls `getObjectType()` exactly once.** Spring has multiple paths for inferring metadata from bean definitions, generic signatures, `FactoryBean.OBJECT_TYPE_ATTRIBUTE`, caches, and existing factory instances. The exact call count and timing are version/configuration-dependent implementation details. The contract for FactoryBean authors is: **keep the method cheap, safe to call early, and returning a consistent type**.

### Type querying is not equivalent to product retrieval

Relevant APIs:

~~~java
context.getType("apiClient");
context.isTypeMatch("apiClient", ApiClient.class);
context.getBeanNamesForType(ApiClient.class);
context.getBean(ApiClient.class);
~~~

- `getType` / `isTypeMatch` / `getBeanNamesForType` inspect type/candidate information. Depending on flags/configuration, Spring **may** need to initialize the FactoryBean to obtain metadata if early information is insufficient.
- `getBean(ApiClient.class)` retrieves a usable object, so it may create the product when needed.
- A type query call does not mean the product has necessarily been created; that is the design purpose of `getObjectType`.

Use `BeanFactory.getType(String name, boolean allowFactoryBeanInit)` if you want to control whether BeanFactory is permitted to initialize an **uninitialized FactoryBean** solely to determine its type. `allowFactoryBeanInit=false` does not mean Spring is forbidden from reading metadata or excludes all already-created FactoryBeans.

## 4. Do not create the product inside getObjectType()

A problematic way to write it:

~~~java
@Override
public Class<?> getObjectType() {
    return getObject().getClass(); // Avoid: forces product creation just to inspect type.
}
~~~

For a product requiring network connections or heavy resources, merely searching for beans by type could already create the client, open sockets, and run initialization at the wrong time. The product object's lifecycle can also be disrupted if this approach creates an instance and drops the reference.

Common issues:

1. **Side effects** when the container only wants metadata, especially at startup or during component scanning.
2. The factory is not yet fully initialized, so `getObject()` demands unready fields and throws an error.
3. Causes **circular dependencies / circular initialization** when `getObject()` needs a bean currently being resolved by Spring.
4. Increased cost from repeated type queries or factories returning new products.
5. When the product has a runtime proxy, `getClass()` returns a proxy-generated class instead of the stable interface clients need.
6. If `getObject()` can return `null`, calling `getClass()` also causes a `NullPointerException`.

**What to do instead:** return a known type from declarations or configuration without creating the product:

~~~java
@Override
public Class<?> getObjectType() {
    return ApiClient.class;
}
~~~

If the type depends on a parameter:

~~~java
public final class TypedFactory<T> implements FactoryBean<T> {
    private final Class<T> productType;
    private final java.util.function.Supplier<? extends T> supplier;

    public TypedFactory(
            Class<T> productType,
            java.util.function.Supplier<? extends T> supplier) {
        this.productType = java.util.Objects.requireNonNull(productType);
        this.supplier = java.util.Objects.requireNonNull(supplier);
    }

    @Override
    public T getObject() {
        return supplier.get();
    }

    @Override
    public Class<?> getObjectType() {
        return productType; // Metadata available directly from constructor.
    }

    @Override
    public boolean isSingleton() {
        return false; // Each lookup creates a new product per this example's Supplier contract.
    }
}
~~~

This is a Java class that compiles with the appropriate Spring API import (`org.springframework.beans.factory.FactoryBean`). `supplier` might itself return a shared object if the caller intentionally does so; in that case `isSingleton()` must be revisited to match actual behavior. The principle is to pass **`Class<T>` ahead of time**, rather than letting `getObjectType()` force product creation.

## 5. Choosing the right type: interface or implementation?

Suppose the factory creates `DefaultApiClient implements ApiClient`. There are two valid Java type choices if both hold true for all products that might be created:

~~~java
return ApiClient.class;
~~~

or:

~~~java
return DefaultApiClient.class;
~~~

Choose based on **the actual contract the bean exposes**:

- If services are designed to inject `ApiClient` and the factory may swap multiple implementations, returning `ApiClient.class` is sensible.
- If the factory guarantees always returning the exact implementation type, returning `DefaultApiClient.class` can help resolve a dependency requiring that concrete type.
- Do not declare a type **narrower than or not assignable from** the actual object: Spring may make wrong predictions and fail later when retrieving the product.
- Do not return a type that only appears in *one* configuration branch if other creations might return incompatible objects. Pick a stable common contract.

**Important:** `Class<?>` type information does not fully represent Java generic arguments such as `ApiClient<String>` versus `ApiClient<Long>`. Spring provides `ResolvableType` and generic metadata on bean definitions to support complex matching. If the application needs to distinguish generics, do not assume `getObjectType()` alone solves it completely: it only returns the **raw class**.

### Dynamically created proxies

A `FactoryBean` may supply a JDK dynamic proxy that only implements `ApiClient`. In that case, returning `ApiClient.class` is accurate and stable; returning `DefaultApiClient.class` is wrong if the final product **is not an instance** of `DefaultApiClient`.

For class-based proxies, the proxy type may be a subclass of the implementation. Usually there is no need to use `proxy.getClass()` as metadata: returning a clear superclass/interface that the proxy always implements is more resilient.

## 6. Complete Java 17 and Spring Framework 6.2 example

The example uses `FactoryBean<ApiClient>` to create a singleton product and demonstrates:

- `getObjectType()` declares the **ApiClient** interface type.
- The `CheckoutService` bean is autowired by `ApiClient`.
- `getBean("apiClient")` receives the product, `getBean("&apiClient")` receives the factory.
- `getType("apiClient")` checks the product type; `getType("&apiClient")` checks the factory type.
- `isSingleton()` declares that the same product is reused.
- `getObjectType()` has no side effect of creating the product.

### 6.1. Structure

~~~text
factory-object-type-demo/
├── pom.xml
└── src/main/java/demo/
    └── FactoryObjectTypeDemo.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>factory-object-type-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. src/main/java/demo/FactoryObjectTypeDemo.java

~~~java
package demo;

import org.springframework.beans.factory.FactoryBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class FactoryObjectTypeDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            // Bean by normal name: retrieves the product.
            ApiClient client = context.getBean("apiClient", ApiClient.class);

            // & prefix: requests the FactoryBean itself.
            ApiClientFactoryBean factory =
                    context.getBean("&apiClient", ApiClientFactoryBean.class);

            // Another bean injected with ApiClient.
            CheckoutService service = context.getBean(CheckoutService.class);

            System.out.println("productType="
                    + context.getType("apiClient").getSimpleName());
            System.out.println("factoryType="
                    + context.getType("&apiClient").getSimpleName());
            System.out.println("result=" + service.checkout("42"));
            System.out.println("sameProduct="
                    + (client == context.getBean(ApiClient.class)));
            System.out.println("created=" + factory.creationCount());
        }
    }

    public interface ApiClient {
        String request(String id);
    }

    public static final class DefaultApiClient implements ApiClient {
        @Override
        public String request(String id) {
            return "ok:" + id;
        }
    }

    public static class ApiClientFactoryBean implements FactoryBean<ApiClient> {
        private ApiClient cached;
        private int created;

        @Override
        public synchronized ApiClient getObject() {
            if (cached == null) {
                cached = new DefaultApiClient();
                created++;
            }
            return cached;
        }

        @Override
        public Class<?> getObjectType() {
            return ApiClient.class; // Does not call getObject().
        }

        @Override
        public boolean isSingleton() {
            return true;
        }

        public synchronized int creationCount() {
            return created;
        }
    }

    public static class CheckoutService {
        private final ApiClient client;

        public CheckoutService(ApiClient client) {
            this.client = client;
        }

        public String checkout(String id) {
            return client.request(id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean(name = "apiClient")
        public static ApiClientFactoryBean apiClientFactory() {
            return new ApiClientFactoryBean();
        }

        @Bean
        public static CheckoutService checkoutService(ApiClient apiClient) {
            return new CheckoutService(apiClient);
        }
    }
}
~~~

### 6.4. How to run

Requires Java 17+ and Maven. Inside the `factory-object-type-demo` directory:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=demo.FactoryObjectTypeDemo
~~~

**Program stdout** (ignoring Maven/infrastructure logs if the environment prints extra output):

~~~text
productType=ApiClient
factoryType=ApiClientFactoryBean
result=ok:42
sameProduct=true
created=1
~~~

### 6.5. Why is the output like this?

1. `@Bean(name = "apiClient")` registers the **FactoryBean instance** under the name `apiClient`. Because the class implements `FactoryBean<ApiClient>`, the container applies special dereferencing logic.
2. `getObjectType()` returns `ApiClient.class` so Spring knows the product type when looking up beans by interface; it does not create `DefaultApiClient` itself.
3. When Spring creates `CheckoutService(ApiClient apiClient)` or when `getBean("apiClient")` is called, BeanFactory retrieves the product provided by `getObject()`. The factory in the example returns the same cached instance.
4. `getType("apiClient")` returns the product type info `ApiClient`, so it prints `productType=ApiClient`.
5. `getType("&apiClient")` returns the factory's class, so it prints `factoryType=ApiClientFactoryBean`.
6. `CheckoutService.checkout("42")` invokes the client and returns `ok:42`.
7. `context.getBean(ApiClient.class)` and the `client` variable reference the same product (because there is only one `ApiClient` candidate and a singleton factory).
8. The `created` counter increments once when `DefaultApiClient` is created, resulting in `created=1`.

**Note:** The example uses synchronization inside the FactoryBean to ensure `getObject()` does not create duplicate products if called concurrently. With `isSingleton() == true`, Spring can also cache the product inside BeanFactory. These are two separate layers of mechanism; in production code, unify product ownership and lifecycle to avoid double caching or improper destruction.

### 6.6. Try changing one line to observe the error

Change:

~~~java
@Override
public Class<?> getObjectType() {
    return null;
}
~~~

Then Spring is not guaranteed to find `apiClient` as a candidate for `ApiClient` during autowiring, especially when the product does not exist yet or type metadata is insufficient. The `CheckoutService` bean requiring `ApiClient` may report `NoSuchBeanDefinitionException` wrapped in `UnsatisfiedDependencyException`.

**Do not claim every program returning null must necessarily fail on the exact same line.** Spring may infer generics/other metadata or have already created the product earlier. The SPI contract still recommends **returning the expected type early**; relying on fallback inference when the type is clearly known is an unstable design.

Change to:

~~~java
@Override
public Class<?> getObjectType() {
    return ApiClientFactoryBean.class;
}
~~~

This is the wrong product type: the container may predict `apiClient` as a FactoryBean instead of `ApiClient`, affecting type matching. The factory itself can still be accessed via `&apiClient`; that **does not require** changing the product metadata.

If returning `DefaultApiClient.class`, the example may still work because the product is that implementation. However, if later the factory switches to a JDK proxy that only implements `ApiClient`, declaring the concrete class will be wrong. Choosing `ApiClient.class` reflects a more stable API.

## 7. getObjectType() does not determine singleton/prototype

A common misconception: "Returning the same `Class<?>` means Spring will always create the same instance." Incorrect. **Type** and **lifecycle** are two independent pieces of information.

~~~java
@Override
public Class<?> getObjectType() {
    return ApiClient.class;
}

@Override
public boolean isSingleton() {
    return false;
}

@Override
public ApiClient getObject() {
    return new DefaultApiClient();
}
~~~

This is an illustrative snippet inside `ApiClientFactoryBean`, not a complete standalone program.

In this configuration, each time BeanFactory retrieves the product from the factory it can receive **a different instance**; `getObjectType()` is still always `ApiClient.class`. The factory bean itself can be a singleton while its product is not a singleton.

Be careful:

- `isSingleton() == true` must be compatible with a factory supplying a single shared object. If the factory reports true yet returns a new object on every call, Spring may cache one object while calling the factory directly behaves differently, muddying semantics.
- `isSingleton() == false` does not by itself prove every returned object is guaranteed independent in all situations; Spring provides `SmartFactoryBean.isPrototype()` to describe that further.
- BeanFactory caches singleton products with its own mechanism; do not use `getObjectType()` to trigger "warm-up" side effects or prepare caches.
- Cleanup of products created by `FactoryBean` must be designed according to proper ownership and lifecycle; do not infer that simply because the factory closed, every product across every scope is automatically closed.

## 8. Returning null when the type is truly unknown

The contract permits:

~~~java
@Override
public Class<?> getObjectType() {
    return resolvedType; // May be null at a very early stage.
}
~~~

For example, a factory configured with a class name from external metadata only available later during startup cannot yet know the product type at the time Spring queries it. Returning `null` then is **API-valid**, but comes with costs:

1. The container cannot be sure whether the factory satisfies a type-based injection point.
2. `ListableBeanFactory` candidate searches may skip the factory when no matching type is received.
3. `BeanFactory.getType("name")` may return `null`.
4. Type-analysis tools or components registering based on bean types may see a bean as missing.
5. Results may depend on initialization order if the type only appears after initialization.

If you know a **stable common interface** even without knowing the concrete implementation yet, return that interface instead of `null`. For instance, implementations `HttpApiClient` and `MockApiClient` both implement `ApiClient`; `getObjectType()` can still return `ApiClient.class`.

If publishing the type early is completely impossible, consider restructuring the factory to pass the type via constructor/configuration, or having downstream dependencies use an explicit discovery API instead of blind autowiring.

### Do not rely on late initialization state

An anti-pattern:

~~~java
private Class<?> type;

@Override
public void afterPropertiesSet() {
    type = expensiveRegistry.resolveProductClass();
}

@Override
public Class<?> getObjectType() {
    return type;
}
~~~

This is a snippet placed in a `FactoryBean` class that also implements `InitializingBean`, with `expensiveRegistry` as an illustrative dependency only. Spring may call `getObjectType()` **before** `afterPropertiesSet()`; the null result makes the bean absent during some type discovery steps. If the type is required from configuration, pass the information early via constructor or BeanDefinition metadata rather than waiting for an init callback.

## 9. Generic FactoryBean<T> and limits of type inference

The declaration:

~~~java
class ApiClientFactoryBean implements FactoryBean<ApiClient> { ... }
~~~

has the generic parameter `ApiClient`, which **can help Spring infer the product type from class/bean definition metadata**. However:

- `getObjectType()` remains the official API used to return the product type when Spring queries a FactoryBean instance.
- Generic types can be erased or obscured by raw declarations, factory methods returning overly general types, proxies, or programmatic registration.
- `FactoryBean<List<String>>` and `FactoryBean<List<Long>>` both have raw product class `List.class`; a method returning `Class<?>` cannot represent differences in type arguments.
- Complex generic-based autowiring relies additionally on `ResolvableType`, declarations, and metadata. Do not try to force `getObjectType()` to return a non-existent `Class<List<String>>` due to Java type erasure.

Example of a factory method declaring too general a type:

~~~java
@Bean
public FactoryBean<?> someFactory() {
    return new ApiClientFactoryBean();
}
~~~

Spring may have less static information than with:

~~~java
@Bean
public ApiClientFactoryBean apiClientFactory() {
    return new ApiClientFactoryBean();
}
~~~

These are illustrative snippets inside a `@Configuration` class. When early type discovery is needed, keep the return type signature **specific enough for Spring to infer** and implement `getObjectType()` accurately. Do not assume "already wrote generic `<ApiClient>`" suffices across every registration path.

## 10. FactoryBean.OBJECT_TYPE_ATTRIBUTE: advanced metadata

Spring has the constant:

~~~java
FactoryBean.OBJECT_TYPE_ATTRIBUTE
~~~

It is an attribute name on `BeanDefinition`, used when frameworks/registrars need to **declare the product type upfront without instantiating the FactoryBean**. This is an infrastructure API, not something ordinary applications configure manually.

In Spring 6.1+ and 6.2, metadata is handled as a `Class<?>` or appropriate `ResolvableType`; you must not arbitrarily put a **String class name** into this attribute and expect Spring to convert it automatically. A `String` value can cause:

~~~text
IllegalArgumentException:
Invalid value type for attribute 'factoryBeanObjectType': java.lang.String
~~~

This is a symptom of **wrongly typed BeanDefinition metadata**, not a bug of the `getObjectType()` method alone. When doing framework integration/registrar work, use valid metadata types and the official API:

~~~java
// BeanDefinition bd was created by registration code.
bd.setAttribute(
        FactoryBean.OBJECT_TYPE_ATTRIBUTE,
        ApiClient.class);
~~~

This is a **programmatic registration snippet**, requiring variable `bd` of type `org.springframework.beans.factory.config.BeanDefinition` and appropriate `FactoryBean`/`ApiClient` imports; it is not a standalone runnable file. If generic-rich metadata is needed, consider an appropriate `ResolvableType`. Setting the attribute properly does not license the `getObjectType()` implementation to lie about the runtime product type; metadata and the actual object must agree.

Most business applications **do not need** to touch `OBJECT_TYPE_ATTRIBUTE`. If you just want to implement a `FactoryBean`, returning the right class from `getObjectType()` is the first thing to do.

## 11. Distinguishing getType, getObject, and &beanName

A short diagram:

~~~text
BeanDefinition: name = "apiClient"
                    |
                    v
             ApiClientFactoryBean
               /      |       \
              /       |        \
     getObjectType  getObject  isSingleton
          |           |           |
    ApiClient.class  ApiClient   true
          |           |           |
    metadata match    object     cache semantics

getType("apiClient")   --> product type (ApiClient)
getBean("apiClient")   --> ApiClient product
getBean("&apiClient")  --> ApiClientFactoryBean factory
getType("&apiClient")  --> factory type
~~~

Keep in mind:

- `getObjectType()` is how the FactoryBean itself **declares** the product type.
- `BeanFactory.getType(name)` is the container-side API to **query** a bean's type by name.
- `FactoryBean.getObject()` is the factory-side API to **supply** the product.
- `BeanFactory.getBean(name)` is the consumer-side API to **retrieve** a bean; if the name points to a FactoryBean, the consumer receives the product.
- `&name` is the dereference convention to retrieve the factory, not a second ordinary bean definition.
- `isSingleton()` controls product caching semantics, distinct from the scope of the FactoryBean instance.

Do not confuse with `ObjectFactory<T>`:

~~~java
ObjectFactory<ApiClient> provider;
~~~

`ObjectFactory<T>` is an on-demand object retrieval API; `FactoryBean<T>` is a **Spring bean special factory** owning product type metadata and special bean naming. They are two different interfaces.

## 12. Type matching, @Autowired, and real-world incidents

When a service requires:

~~~java
public CheckoutService(ApiClient apiClient) { ... }
~~~

Spring searches for candidates compatible with `ApiClient`. Relevant conditions:

1. A BeanDefinition representing the FactoryBean or other product-type metadata has sufficient information.
2. `getObjectType()` does not return a type unrelated to `ApiClient`.
3. There are not multiple candidates of the same type causing ambiguity, or `@Primary`/`@Qualifier`/parameter name clarifies it.
4. The FactoryBean can be initialized/used when needed without circular dependency errors.
5. `getObject()` ultimately returns a product compatible with the dependency type.

If there are **two** FactoryBeans both declaring `ApiClient.class` and two corresponding products, `@Autowired ApiClient` can report `NoUniqueBeanDefinitionException`. Fix with `@Qualifier("apiClient")` or `@Primary` as intended—do not change `getObjectType()` to a fake type to dodge ambiguity.

Example adding `@Qualifier` when needed:

~~~java
public CheckoutService(
        @org.springframework.beans.factory.annotation.Qualifier("apiClient")
        ApiClient apiClient) {
    this.client = apiClient;
}
~~~

This is a constructor snippet in `CheckoutService`, assuming multiple `ApiClient` beans exist in the same context. With a single candidate as in the section 6 example, a qualifier is unnecessary.

### Diagnosing by type vs. by name

If `getBean("apiClient")` returns the product yet `getBean(ApiClient.class)` reports no bean found, prioritize checking:

- Does `FactoryBean.getObjectType()` return `null` when Spring needs to resolve the type?
- Does it return the **factory class** instead of the **product class**?
- Does the `@Bean` signature return raw `FactoryBean<?>` making early metadata unclear?
- Does the returned product actually implement the declared interface?
- Is the bean registered in the right `ApplicationContext`?
- Is there a scope/conditional registration preventing the definition from existing?

In an isolated test, you can print:

~~~java
System.out.println(context.getType("apiClient"));
System.out.println(context.getType("&apiClient"));
System.out.println(java.util.Arrays.toString(
        context.getBeanNamesForType(ApiClient.class)));
~~~

This is a snippet placed in a method with the application's `context` and `ApiClient`. Querying names by type can trigger FactoryBean initialization depending on flags; if you only want to check metadata while avoiding eager init, look at the `getBeanNamesForType(type, includeNonSingletons, allowEagerInit)` overload and understand its limits.

**Do not fix the issue by manually initializing the product inside `getObjectType()`**. That might accidentally make a test appear to pass while introducing side effects during metadata lookup.

## 13. Testing the getObjectType contract independently

A good `FactoryBean` should be tested at two levels.

### 13.1. Unit testing FactoryBean without a context

Write test logic as follows (snippet inside a test method using the section 6 example classes):

~~~java
var factory = new FactoryObjectTypeDemo.ApiClientFactoryBean();

if (factory.getObjectType() != FactoryObjectTypeDemo.ApiClient.class) {
    throw new AssertionError("Wrong product type");
}
if (factory.creationCount() != 0) {
    throw new AssertionError("getObjectType unexpectedly created product");
}

var first = factory.getObject();
var second = factory.getObject();

if (first != second) {
    throw new AssertionError("Expected shared singleton product");
}
if (!factory.getObjectType().isInstance(first)) {
    throw new AssertionError("Product not assignable to advertised type");
}
~~~

This test directly proves:

- `getObjectType()` returns the exact type and does not create the product.
- `getObject()` returns a product assignable to the declared type.
- For the sample singleton factory, multiple calls return the same reference.

However, a unit test does not prove Spring autowiring or factory dereferencing works; those require an integration test.

### 13.2. Integration testing with the Spring container

Create an `AnnotationConfigApplicationContext` from `Config` in section 6, then verify:

- `context.getType("apiClient")` is compatible with `ApiClient.class`.
- `context.getType("&apiClient")` is `ApiClientFactoryBean.class`.
- `context.getBean("apiClient")` is the `ApiClient` product.
- `context.getBean("&apiClient")` is the FactoryBean.
- `context.getBean(CheckoutService.class)` has had the product injected.
- `context.getBeanNamesForType(ApiClient.class)` includes the name `apiClient`.
- `getObject()` is actually called when the product is needed, without using `getObjectType()` as a place to trigger side effects.
- FactoryBean `isSingleton()` matches semantics; check object identity.
- When returning `null`/wrong type, observe the actual effect per Spring version and metadata rather than guessing a fixed exception.

### 13.3. Additional valuable test cases

| Test case | Objective |
| --- | --- |
| Factory with uncreated product, call `getObjectType` | Does not create resources |
| Factory before `afterPropertiesSet` | No NPE / does not rely on late-initialized fields |
| Product is a JDK dynamic proxy | Advertised type is an interface the proxy implements |
| Product uses multiple implementations | Published type is a stable common contract |
| Non-singleton product | `getObjectType` does not alter creation semantics |
| Generic FactoryBean obscured by raw type | Explicit metadata still suffices for type discovery |
| Multiple products sharing an API | Autowiring reports ambiguity or qualifier picks the right one |
| Circular dependency exists | `getObjectType` does not call `getObject` creating another cycle |
| Programmatic `OBJECT_TYPE_ATTRIBUTE` metadata | Valid Class/ResolvableType; do not use String |
| Context close | Resources are destroyed according to proper ownership and scope |

## 14. Common mistakes and fixes

| Symptom | Typical cause | Remediation |
| --- | --- | --- |
| `@Autowired ApiClient` finds no candidate | `getObjectType()` returns null during type discovery | Return `ApiClient.class` if the interface is known |
| Bean by name exists yet bean by type is not found | Returns the factory type or wrong product type | Return the type of the object supplied by `getObject()` |
| Type query unexpectedly opens a socket | `getObjectType()` calls `getObject()` | Do not create the product inside type queries |
| `NullPointerException` during refresh/autowire | `getObjectType` relies on fields only set after init | Use type metadata available from constructor/config |
| `NoUniqueBeanDefinitionException` | Multiple products assignable to the same interface | `@Qualifier` or `@Primary` |
| `ClassCastException` or type mismatch on `getBean` | Runtime product is not assignable to advertised type | Fix metadata and product contract |
| Choosing runtime proxy class in `getObjectType` | Unstable type or proxy does not exist yet | Return a stable API interface/superclass |
| Factory bean seen via normal name instead of product | Confusion over `&` usage | `getBean("&name")` gets factory, `getBean("name")` gets product |
| `isSingleton()=true` yet factory returns new objects | Wrong factory semantics / surprising caching | Align contract, cache properly, or return false |
| `getObjectType()` tries to express generics | `Class<?>` cannot represent full parameterized types | Use `ResolvableType`/bean metadata when appropriate |
| Error `factoryBeanObjectType: java.lang.String` | Registrar set BeanDefinition attribute to wrong type | Use `Class<?>` or `ResolvableType`, not a String class name |
| FactoryBean creates expensive product right when searching types | Side effects in type metadata or eager type discovery | Declare type early and use overloads avoiding eager init when appropriate |
| Component uses `@Bean` returning overly broad `FactoryBean<?>` | Weak static type metadata | Declare concrete FactoryBean return type if possible |

## 15. FactoryBean product type design checklist

1. Define a **stable type contract** that every product always implements.
2. Implement `getObjectType()` to return the `Class<?>` of the **product**, not the FactoryBean.
3. Never call `getObject()`, open connections, access the network, or create expensive resources inside `getObjectType()`.
4. Allow `getObjectType()` to run before init; use metadata from constructor/config if needed.
5. Return `null` only when the type is genuinely unknowable; understand the consequences for autowiring.
6. Ensure `getObject()` always returns an object assignable to the advertised type.
7. Set `isSingleton()` to match product identity/cache semantics.
8. Register the FactoryBean with a sufficiently specific class/`@Bean` method type, avoiding raw metadata unnecessarily.
9. Use `&beanName` when you want the factory, and the normal name when you want the product.
10. Test type discovery and autowiring in an ApplicationContext in addition to FactoryBean unit tests.
11. With dynamic proxies, prefer a common interface or superclass rather than returning a runtime proxy class.
12. With registrars, use `FactoryBean.OBJECT_TYPE_ATTRIBUTE` with the right metadata type.
13. Distinguish type lookup errors from product creation errors, scope issues, qualifiers, and duplicate candidates.

## 16. Self-check questions

**Question 1.** What type does `FactoryBean.getObjectType()` return?  
**Answer:** The type of the **product object** supplied by `getObject()`, not the class of the FactoryBean itself.

**Question 2.** Why should you not call `getObject()` inside `getObjectType()` to get `getClass()`?  
**Answer:** Because type discovery can happen before the factory is ready, and you should not create resources or cause side effects just to determine the type.

**Question 3.** Is it valid for `getObjectType()` to return `null`?  
**Answer:** Yes if the type is not yet known, though Spring may skip the FactoryBean during type-based autowiring; return a common interface if known.

**Question 4.** How do `getBean("client")` and `getBean("&client")` differ when `client` belongs to a FactoryBean?  
**Answer:** The normal name retrieves the product; the name with the `&` prefix retrieves the FactoryBean instance.

**Question 5.** If the product is a JDK proxy implementing `ApiClient`, should you return `DefaultApiClient.class`?  
**Answer:** No if the proxy is not an instance of `DefaultApiClient`. Return `ApiClient.class`.

**Question 6.** Can a FactoryBean report `isSingleton() == false` and still return `ApiClient.class`?  
**Answer:** Yes. One piece of information describes the type, and the other describes how product identity is managed.

**Question 7.** Does generic `FactoryBean<ApiClient>` make `getObjectType` pointless?  
**Answer:** No. Spring can infer from generics, but metadata still depends on registration style, proxies, and type discovery steps; the method remains the official SPI.

**Question 8.** When two FactoryBeans both declare `ApiClient.class`, how do you resolve ambiguity?  
**Answer:** Use `@Qualifier`, `@Primary`, or design an explicit injection API; do not falsify the product type.

**Question 9.** Can `FactoryBean.OBJECT_TYPE_ATTRIBUTE` take the string `"demo.ApiClient"`?  
**Answer:** You should not; in Spring 6.1+/6.2, valid metadata types are `Class<?>` or `ResolvableType`, while a String can cause `IllegalArgumentException`.

**Question 10.** Do you need to create the product just so `getBeanNamesForType(ApiClient.class)` sees the bean?  
**Answer:** No. Design `getObjectType()` properly so Spring has a basis to identify the candidate before the product exists.

## Official documentation

- Spring Framework Javadoc 6.2: [FactoryBean](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/FactoryBean.html) — contract of `getObject()`, `getObjectType()`, `isSingleton()`, `OBJECT_TYPE_ATTRIBUTE`.
- Spring Framework Reference: [Extension Points — Customizing Instantiation Logic with a FactoryBean](https://docs.spring.io/spring-framework/reference/core/beans/definition.html#beans-factory-extension-factorybean).
- Spring Framework Javadoc: [BeanFactory](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/BeanFactory.html) — `&` dereference, `getType(name)`.
- Spring Framework Javadoc: [ListableBeanFactory](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/ListableBeanFactory.html) — type lookup, `getBeanNamesForType` overload and `allowEagerInit`.
- Spring Framework Javadoc: [FactoryBeanRegistrySupport](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/support/FactoryBeanRegistrySupport.html).
