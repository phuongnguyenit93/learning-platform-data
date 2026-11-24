# Early Type Prediction and Its Impact on FactoryBean Autowiring in Spring Framework

## 1. The problem: Spring must know the bean type before having the actual object

In the Spring Core Container, a dependency is typically declared by **type**—for instance, `ReportService`'s constructor requires an `Encoder`. To pick the right bean, Spring must identify **which bean definitions can supply an object assignable to type `Encoder`**, even before the object has been created.

For ordinary beans, Spring can rely on the class/return type of a `@Bean` method or bean definition. However, a **`FactoryBean<T>`** is a special case: the bean itself is a factory; the object the application receives when calling `getBean("beanName")` is **the product of `FactoryBean.getObject()`**, not the factory instance.

Example:

```text
bean name: "textEncoder"
         |
         v
    EncoderFactory  implements FactoryBean<Encoder>
         |
         +-- getObjectType() -> Encoder.class
         |                      ^
         |                      |
         |         Spring knows product type
         |         without needing to create Encoder
         |
         +-- getObject() -> real Encoder
                                |
                                v
                         ReportService
                        (inject Encoder)
```

**Early type prediction** means the container can **infer the product type** from metadata or query `FactoryBean.getObjectType()` to match dependencies **without necessarily calling `getObject()`**. This is an important part of making constructor autowiring, `getType()`, `getBeanNamesForType()`, and type-based lookups work properly.

The key point: **do not equate type identification, factory initialization, and product creation**. Those three steps can happen at different times.

## 2. FactoryBean<T> has two type identities

The `org.springframework.beans.factory.FactoryBean<T>` interface provides three main methods:

```java
// Abbreviated API signature for learning; do not redefine in your application.
public interface FactoryBean<T> {
    T getObject() throws Exception;
    Class<?> getObjectType();
    default boolean isSingleton() { return true; }
}
```

In Spring Framework 6.x, `getObjectType()` is permitted to return `null` when the type is unknown. However, the API Javadoc explicitly notes: autowiring may **skip a FactoryBean if it returns null at the time type discovery is needed**. Therefore, return a reliable type as early as possible.

Suppose a bean definition is named `"textEncoder"`, the factory instance is `EncoderFactory`, and the product is `Encoder`:

| Query | What does Spring want to know/retrieve? | Expected result |
| --- | --- | --- |
| `getBean("textEncoder")` | Product | An `Encoder` |
| `getBean("&textEncoder")` | The factory itself | An `EncoderFactory` |
| `getType("textEncoder")` | Product type | `Encoder.class` if predictable |
| `getType("&textEncoder")` | Factory type | `EncoderFactory.class` |
| `getBeanNamesForType(Encoder.class)` | Bean names with matching products | May include `textEncoder` |
| `getBeanNamesForType(EncoderFactory.class)` | Beans of matching type | Do not use as a substitute for retrieving the factory with `&` |
| `getBean("textEncoder", Encoder.class)` | Type-checked product | `Encoder` or a type error on mismatch |

The `&` character is the `BeanFactory.FACTORY_BEAN_PREFIX` constant, used to **dereference the factory** when querying by name. Do not attach `&` when you want the product injected into the application.

### Difference between the factory's type and the product's type

```java
public final class EncoderFactory implements FactoryBean<Encoder> {
    @Override
    public Encoder getObject() {
        // Produces product when container needs it.
        return new PrefixEncoder("v1:");
    }

    @Override
    public Class<?> getObjectType() {
        return Encoder.class;
    }
}
```

This is a fragment requiring the `Encoder` interface, `PrefixEncoder` class, and `FactoryBean` import; it is not a standalone runnable program. The Java type of the factory instance is `EncoderFactory`, yet **the type published for the normal bean name is `Encoder`**. When resolving an `Encoder` dependency, Spring needs to know the **product**, not just the class implementing the factory.

## 3. getObjectType() must be accurate, lightweight, and safe to run early

The Spring Javadoc emphasizes that `getObjectType()` **may be called before the FactoryBean is fully initialized**. During type matching, Spring does not want to initialize the product just to find out what class the product is.

A good implementation:

```java
@Override
public Class<?> getObjectType() {
    return Encoder.class;
}
```

A risky implementation:

```java
@Override
public Class<?> getObjectType() {
    return product.getClass(); // product may be null before getObject().
}
```

The risky snippet is an illustrative fragment; the `product` field is not defined here. If `product` is only created in `getObject()`, `@PostConstruct`, or a later step, `getObjectType()` can throw `NullPointerException` or return null, causing type discovery to fail.

Another error:

```java
@Override
public Class<?> getObjectType() {
    return getObject().getClass(); // Wrong: creates product to guess type.
}
```

The fragment above only compiles if `getObject()` declares no checked exception or handles exceptions appropriately; it is an **anti-pattern**, not production code. It can open connections, spawn threads, hit a DB, or pull in a dependency chain while Spring is only asking "what type is this?". This increases startup latency, circular dependency risks, and unwanted side effects.

**Good rules:**
1. If the product always implements `Encoder`, usually return `Encoder.class` even when the concrete implementation is chosen by configuration.
2. If consumers need a concrete class, the returned type must be compatible with that concrete class; declaring too broad an interface can prevent lookups by concrete type from finding it.
3. Do not throw an exception merely because the type is not yet known. The API allows returning `null`, though you must accept the autowiring limitations.
4. Do not depend on late-injected fields or unready files/networks.
5. Keep it side-effect-free; the method may be called multiple times by Spring during metadata processing.
6. Do not use `getObjectType()` as an initialization method for the product.
7. Keep the published type **stable**, compatible with every product the factory may return over its lifetime.

If `getObjectType()` advertises `CsvEncoder.class` while `getObject()` returns `JsonEncoder` which does not inherit that type, the container may pick the wrong bean during autowiring and then fail with a type mismatch error at creation time. Type metadata must be truthful.

## 4. Type resolution happens across multiple stages

There are at least three layers of information:

**(A) Bean definition metadata:** Spring may know the FactoryBean's class, generic signature `FactoryBean<Encoder>`, factory method return type, or metadata registered by a registrar before the factory instance exists.

**(B) FactoryBean instance:** When more information is needed and policy permits, Spring may instantiate the factory and call `getObjectType()`. This **does not necessarily** create the product.

**(C) Actual product:** `getObject()` creates or returns the product, and only then is the exact concrete instance of the final object known for sure.

```text
BeanDefinition / generic / factory-method return type
                  |
                  v
        enough type metadata?
           |              |
          Yes             No
           |              |
           |              v
           |       policy allow eager init?
           |             |            |
           |            Yes           No
           |             |            |
           |        instantiate      type may be
           |        FactoryBean       unknown
           |             |
           |        getObjectType()
           |             |
           +-------------+
                  |
             select candidate
                  |
       when dependency is actually needed
                  |
            FactoryBean.getObject()
                  |
             product is used
```

This is a conceptual model of type prediction, not a trace of all internal methods of a specific Spring version. Some paths may prefer metadata/generics, some paths invoke the factory, and some paths skip uninitialized factories to avoid side effects.

### Distinguishing two levels of "eager"

- **Eagerly initializing the FactoryBean to inspect the type**: may create the **factory instance** and call `getObjectType()`. It does not imply `getObject()` has been called.
- **Eagerly initializing the FactoryBean product**: creates the **product** itself at startup, for example because another eager singleton depends on the product, or `SmartFactoryBean.isEagerInit()` is configured appropriately.

Do not look at the factory constructor log and conclude the product was also created. To be sure, separately measure calls to `FactoryBean.getObject()` or product initialization events.

## 5. Direct impact on constructor autowiring

Suppose a business bean needs an `Encoder`:

```java
public final class ReportService {
    private final Encoder encoder;

    public ReportService(Encoder encoder) {
        this.encoder = encoder;
    }

    public String render(String text) {
        return encoder.encode(text);
    }
}
```

This is a fragment requiring the `Encoder` interface, not standalone source. When Spring creates `ReportService`, it must find a bean whose object type is compatible with `Encoder`. If the only such bean is produced by `EncoderFactory`, Spring can:

1. Look up the type from bean definition/generic signature.
2. When needed, call `EncoderFactory.getObjectType()`.
3. Identify bean name `textEncoder` as a candidate of type `Encoder`.
4. Retrieve the product through the container (which may lead to `getObject()`) to inject it.

Notably, step (2) **does not need to create the product** if the factory declares the type properly. Step (4), however, will normally create the product **when `ReportService` is actually instantiated**; constructor injection does not make a dependency lazy unless a separate lazy proxy/provider is used.

### What if getObjectType() returns null?

A factory with an unknown type can cause Spring to **omit that product from the candidate list** for `Encoder` type injection. The result may be `NoSuchBeanDefinitionException`/`UnsatisfiedDependencyException` when creating `ReportService` (depending on initialization site and error wrapping). If another candidate exists, Spring might inject that other candidate or report ambiguity, rather than picking the "hidden" factory.

```java
@Override
public Class<?> getObjectType() {
    return null; // Only use when type truly cannot be inferred yet.
}
```

Do not claim that **every** lookup path fails on null. For example, retrieving by **bean name** `getBean("textEncoder")` can still invoke `getObject()` to get the product. There are also cases where other metadata allows the type to be recognized. The accurate conclusion is that **returning null poses a major risk to type-based discovery/autowiring**, not that it forbids Spring from retrieving the product by name.

### Do not confuse injection errors with product creation errors

| Symptom | Detected at which step? | Likely cause |
| --- | --- | --- |
| No `Encoder` candidate found | Type discovery | `getObjectType()` null/wrong, factory not yet considered, wrong package/profile |
| Two candidates found | Candidate selection | Two products have matching types; need `@Qualifier`/`@Primary` |
| Candidate selected yet constructor init fails | Product creation | `getObject()` throws exception, missing config, network failure |
| `BeanNotOfRequiredTypeException` | Type contract | Product is incompatible with the requested type |
| Retrieved `&textEncoder` yet cast to `Encoder` | Wrong identity retrieved | `&` returns the factory, not the product |
| Injection happens before expected startup point | Eager dependent singleton | Constructor injection needs the real product when the consumer is created |

## 6. Complete Spring Core example — predicting type before creating product

The sample below uses **Java 17+, Maven 3.9+, Spring Framework 6.2.18**. We intentionally make `ReportService` a **lazy singleton**, so at context refresh `EncoderFactory` exists without needing to create the product yet. Next we perform type queries, inspect the counter, and finally request `ReportService` to observe when the product gets created.

### 6.1. Project structure

```text
factorybean-type-demo/
├── pom.xml
└── src/main/java/edu/example/type/
    ├── Encoder.java
    ├── PrefixEncoder.java
    ├── EncoderFactory.java
    ├── ReportService.java
    ├── AppConfig.java
    └── Main.java
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>factorybean-type-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
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
                    <mainClass>edu.example.type.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/edu/example/type/Encoder.java**

```java
package edu.example.type;

public interface Encoder {
    String encode(String text);
}
```

**src/main/java/edu/example/type/PrefixEncoder.java**

```java
package edu.example.type;

public record PrefixEncoder(String prefix) implements Encoder {
    @Override
    public String encode(String text) {
        return prefix + text;
    }
}
```

**src/main/java/edu/example/type/EncoderFactory.java**

```java
package edu.example.type;

import org.springframework.beans.factory.FactoryBean;

public final class EncoderFactory implements FactoryBean<Encoder> {
    private Encoder shared;
    private int count;

    @Override
    public synchronized Encoder getObject() {
        // Create product exactly once when someone actually needs it.
        if (shared == null) {
            shared = new PrefixEncoder("v1:");
            count++;
        }
        return shared;
    }

    @Override
    public Class<?> getObjectType() {
        // Important: do not call getObject() and do not rely on late-init state.
        return Encoder.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }

    public synchronized int productCreationCount() {
        return count;
    }
}
```

**src/main/java/edu/example/type/ReportService.java**

```java
package edu.example.type;

public final class ReportService {
    private final Encoder encoder;

    public ReportService(Encoder encoder) {
        this.encoder = encoder;
    }

    public String render(String text) {
        return encoder.encode(text);
    }

    public Encoder encoderReference() {
        return encoder;
    }
}
```

**src/main/java/edu/example/type/AppConfig.java**

```java
package edu.example.type;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;

@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean("textEncoder")
    public EncoderFactory encoderFactory() {
        return new EncoderFactory();
    }

    @Bean
    @Lazy
    public ReportService reportService(Encoder encoder) {
        return new ReportService(encoder);
    }
}
```

**src/main/java/edu/example/type/Main.java**

```java
package edu.example.type;

import java.util.Arrays;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class Main {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            EncoderFactory factory =
                    context.getBean("&textEncoder", EncoderFactory.class);

            System.out.println("type: "
                    + context.getType("textEncoder").getSimpleName());
            System.out.println("created before request: "
                    + factory.productCreationCount());

            String[] names = context.getBeanNamesForType(Encoder.class);
            Arrays.sort(names);
            System.out.println("candidates: " + Arrays.toString(names));
            System.out.println("created after type query: "
                    + factory.productCreationCount());

            ReportService report = context.getBean(ReportService.class);
            System.out.println("result: " + report.render("abc"));
            System.out.println("created after autowire: "
                    + factory.productCreationCount());

            Encoder byName = context.getBean("textEncoder", Encoder.class);
            System.out.println("same product: "
                    + (byName == report.encoderReference()));
            System.out.println("factory type: "
                    + context.getType("&textEncoder").getSimpleName());
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

**Program `System.out.println` lines:**

```text
type: Encoder
created before request: 0
candidates: [textEncoder]
created after type query: 0
result: v1:abc
created after autowire: 1
same product: true
factory type: EncoderFactory
```

**Explanation:**
- The `AnnotationConfigApplicationContext(AppConfig.class)` constructor calls `refresh()` automatically; the singleton factory bean can be created to serve metadata, while the product does not have to be created yet.
- `@Lazy` on the `ReportService` bean prevents the consumer from being eagerly created during refresh. In this sample no other bean requests `Encoder` early.
- `getType("textEncoder")` and `getBeanNamesForType(Encoder.class)` use type metadata/`getObjectType()`; `getObject()` is unnecessary, so the product counter stays 0.
- `context.getBean(ReportService.class)` creates the lazy consumer; the `Encoder` constructor dependency is resolved via the factory's product, causing `getObject()` to create the `PrefixEncoder` record once.
- Because `isSingleton()==true` and the factory itself holds the `shared` reference, the subsequent `getBean("textEncoder")` lookup returns the existing product.
- `getType("&textEncoder")` queries the factory's type, not the product's type.

The example has deterministic output based on explicit relationships and values, independent of classpath scanning or creation order of unrelated beans. Other Maven/Spring logs may appear depending on the environment; the eight lines above are the logs printed by `Main` itself.

**Experiment:** Replace `getObjectType()` with `return null;` and rerun. Some type query paths may return null or fail to find `textEncoder`; autowiring `Encoder` may fail. Do not treat this as a fixed "new stdout result" across all Spring introspection paths; inspect the actual exception chain, because Spring might infer from generic signatures/metadata or have already instantiated the factory.

## 7. getBeanNamesForType(), getBeansOfType(), and allowEagerInit

Three concepts often conflated:

1. **`getType("beanName")`**: queries the type of a bean name. If the product type is undetermined, it may return null or have to consider factory initialization depending on the overload/path.
2. **`getBeanNamesForType(...)`**: finds the **names** of candidates by type. It has overloads allowing control over bean search scope and initialization policy.
3. **`getBeansOfType(...)`**: returns a **map of name → instance**, so it must resolve real objects for matching results; returning the map normally causes bean creation to happen.

Example with `ConfigurableListableBeanFactory` (in a Spring context with `ListableBeanFactory`), the APIs:

```java
String[] candidates =
        context.getBeanNamesForType(Encoder.class);

String[] conservative =
        context.getBeanNamesForType(Encoder.class, true, false);

java.util.Map<String, Encoder> instances =
        context.getBeansOfType(Encoder.class);
```

This is a fragment depending on defined `context` and `Encoder`. All three methods belong to `ListableBeanFactory` supported by `ApplicationContext`. **`getBeansOfType()` does not merely list metadata**: it can create the product and its related dependencies to supply the instance map.

### Meaning of includeNonSingletons and allowEagerInit

| Parameter | Value | Consequence |
| --- | --- | --- |
| `includeNonSingletons=true` | Permits prototype/scoped/non-singleton candidates | Covers a broader scope |
| `includeNonSingletons=false` | Considers only matching singletons | Considers singleton products of FactoryBeans as determinable |
| `allowEagerInit=true` | Allows initializing factories/lazy infrastructure **when needed for type matching** | May produce side effects from factory initialization |
| `allowEagerInit=false` | Restricts eager initialization for type finding | May **omit** FactoryBean products lacking an existing factory instance or sufficient metadata |

Notably, the `ListableBeanFactory.getBeanNamesForType(type, includeNonSingletons, allowEagerInit)` documentation explains that when `allowEagerInit=false`, inspecting FactoryBeans may only check the raw factory rather than the product if creating the factory would be required to call `getObjectType()`. Therefore **an empty name search result does not prove with certainty that no bean can produce that type**.

`allowEagerInit=true` **does not mean** Spring always calls `FactoryBean.getObject()` immediately. It usually allows the **factory itself** to be created for type detection, while creating the product itself can still wait until the dependency is actually resolved.

Analysis example:

```text
A. Product type known from BeanDefinition / generic metadata
   -> candidate name can be identified without creating FactoryBean.

B. Product type only determined in factory.getObjectType()
   -> may need to instantiate factory before finding candidate.

C. Product type only known after a heavy call to getObject()
   -> FactoryBean API design discourages this approach;
      Spring may skip candidate or cause unwanted side effects.
```

When building frameworks, plugin registries, or startup health checks, consider **looking up names first and resolving selectively**. Using `getBeansOfType` to load every service plugin can inadvertently trigger expensive FactoryBeans.

### Results by order and context hierarchy

An ordinary `ListableBeanFactory` searches **beans of the current factory**, without automatically scanning beans across every parent/child context. For hierarchies, use `BeanFactoryUtils.beanNamesForTypeIncludingAncestors(...)` when needed. Do not assume a product name has the same meaning across the whole JVM/pod.

## 8. Why does getObjectType() returning null make autowiring unpredictable?

Suppose the following configuration:

```java
public final class UnknownEncoderFactory implements FactoryBean<Encoder> {
    private Encoder product;

    @Override
    public Encoder getObject() {
        if (product == null) {
            product = new PrefixEncoder("unknown:");
        }
        return product;
    }

    @Override
    public Class<?> getObjectType() {
        return product == null ? null : product.getClass();
    }
}
```

This is an anti-pattern fragment needing `FactoryBean` imports and `Encoder`/`PrefixEncoder` types. When the container merely asks the type of a bean whose product has not been created yet, the factory returns `null`. Spring may fail to recognize this candidate when resolving an `Encoder` dependency by type. If the application retrieves the product by name first, type discovery afterward yields a different result. This leads to **usage-order-dependent bugs** that are very hard to debug.

**Fix:** if it always creates `PrefixEncoder`, return `PrefixEncoder.class` or at least `Encoder.class` from the start, without depending on `product` state.

If the product class is only determined from a config key yet all implement the `Encoder` interface, returning `Encoder.class` is usually enough for consumers injecting `Encoder`. Consumers directly injecting `PrefixEncoder` might not discover the bean if type metadata only declares the interface; that is a limitation of the predicted type choice, not that the product fails to implement `PrefixEncoder` at runtime.

### Consequences with @ConditionalOnBean in Spring Boot

Although the main topic is Spring Core, real-world systems also use `@ConditionalOnBean(Encoder.class)` in Spring Boot auto-configuration. Conditions like this typically rely on type metadata and the registration timing of bean definitions. A FactoryBean hiding its product type can prevent the condition from recognizing the bean as expected. When writing starters/auto-configuration, it is especially important to provide an accurate `getObjectType()`, clear return signatures, and early metadata. Do not confuse Spring Boot condition behavior with a `FactoryBean` contract claiming it automatically fixes all type matching.

## 9. When there are multiple candidates: @Qualifier and @Primary

Suppose two factory beans both declare `Encoder.class`:

```java
@Configuration(proxyBeanMethods = false)
class MultiConfig {
    @Bean("fastEncoder")
    FactoryBean<Encoder> fastEncoder() {
        return new FastEncoderFactory();
    }

    @Bean("safeEncoder")
    FactoryBean<Encoder> safeEncoder() {
        return new SafeEncoderFactory();
    }
}
```

The snippet only illustrates architecture and does not compile because `FastEncoderFactory`/`SafeEncoderFactory` are undefined. When both products are `Encoder` candidates, constructor injection `ReportService(Encoder encoder)` can report `NoUniqueBeanDefinitionException` (usually wrapped when creating the consumer).

Fix with a qualifier on the injection point:

```java
@Service
class ReportService {
    private final Encoder encoder;

    ReportService(@Qualifier("safeEncoder") Encoder encoder) {
        this.encoder = encoder;
    }
}
```

The snippet needs imports for `@Service`/`@Qualifier` and `Encoder`. `@Qualifier` selects the product bean with the matching name/qualifier; it does not require the consumer to hold a `FactoryBean` instance.

Or mark one product definition as primary:

```java
@Bean("safeEncoder")
@Primary
FactoryBean<Encoder> safeEncoder() {
    return new SafeEncoderFactory();
}
```

The snippet needs `@Bean`, `@Primary`, and the factory type. `@Primary` prioritizes a candidate during autowiring when multiple beans share the same type; it **does not fix** an undiscovered type. For a FactoryBean returning null in `getObjectType()`, adding `@Primary` does not guarantee the candidate will automatically appear in every query.

**Summary:**

| Problem | Right tool | What is needed from FactoryBean |
| --- | --- | --- |
| Spring does not know what product type exists | `getObjectType()`, clear return type/metadata | Type must be right and known early |
| Exactly one candidate exists | Type-based autowiring | FactoryBean must be discovered |
| Multiple candidates share the type | `@Qualifier`, `@Primary` | Candidates must be discovered |
| Optional dependency | `ObjectProvider<Encoder>`, `Optional<Encoder>` | Does not create object unless needed, yet type discovery still matters |
| Want multiple implementations | `List<Encoder>`, `Map<String, Encoder>` | Product type must be accurate to join collections |
| Want to inject the factory itself | `getBean("&name")` or proper injection config | Do not confuse factory with product |

## 10. Generic types: Class<?> does not fully express Repository<User>

`getObjectType()` returns a `Class<?>`. It only represents a **raw class/interface type**, and does not directly represent concrete generic arguments like `Repository<User>`. Spring uses `ResolvableType` and metadata from bean definitions/factory methods/target declarations when generic type inference is needed.

Target example:

```java
interface Repository<T> {
    T findById(String id);
}

record User(String id) {}

final class UserRepository implements Repository<User> {
    @Override
    public User findById(String id) {
        return new User(id);
    }
}
```

This is a type-complete Java snippet, not attached to section 6's `Encoder` project. If a factory creates `Repository<User>` and `getObjectType()` returns `Repository.class`, the `<User>` info is not present inside that `Class<?>` object. Spring can infer generics from `FactoryBean<Repository<User>>` or bean definition metadata in some cases, yet you should not assume every raw-type definition suffices to autowire `Repository<User>` accurately and distinguish it from `Repository<Order>`.

**What to do:**
- Declare concrete generic signatures on classes/factory methods, e.g., `FactoryBean<Repository<User>>` instead of raw `FactoryBean`.
- Provide an accurate `getObjectType()` at the class or interface level.
- If writing infrastructure that registers bean definitions programmatically, consider supplying `ResolvableType` in metadata where the framework supports it.
- Write integration tests with two products having different generic arguments to confirm Spring picks the right bean, avoiding reliance on type erasure or superficial assumptions.
- If products differ wildly by runtime config, it is usually better to register explicit separate bean definitions rather than one ambiguous factory whose type cannot be predicted.

### FACTORY_BEAN_OBJECT_TYPE_ATTRIBUTE metadata

Spring provides the constant `FactoryBean.OBJECT_TYPE_ATTRIBUTE` with key value `"factoryBeanObjectType"`. Infrastructure creating `BeanDefinition`s programmatically can set this metadata to declare the product type early when it cannot be inferred from the factory class.

Conceptual example with the Spring BeanDefinition API:

```java
BeanDefinition definition =
        BeanDefinitionBuilder.genericBeanDefinition(EncoderFactory.class)
                .getBeanDefinition();

definition.setAttribute(FactoryBean.OBJECT_TYPE_ATTRIBUTE, Encoder.class);
```

The snippet needs imports for `BeanDefinition`, `BeanDefinitionBuilder`, `FactoryBean`, and `EncoderFactory`; the code must be used inside a matching registrar/`BeanDefinitionRegistry`, **not** section 6's runnable project. In Spring 6.1+/6.2, the attribute must be a `Class<?>` or `ResolvableType` (or absent)—**do not put a String `"com.example.Encoder"`**: Spring may throw an error due to an invalid metadata type. This is an API for infrastructure authors; applications normally only need a proper `getObjectType()`.

**Do not abuse:** the attribute does not replace `getObject()` returning a product of the actual right type and does not replace normal injection handling. Wrong metadata can cause Spring to discover a candidate yet fail when resolving the instance.

## 11. FactoryBean and lifecycle: one reason early type prediction is needed

A factory is a real bean, whereas the product is an object supplied by the factory.

```text
Container refresh / dependency discovery
  |
  +-- may inspect BeanDefinition, generic signature
  +-- may create FactoryBean to call getObjectType()
  |
  +-- FactoryBean instance is initialized:
        constructor, injection, @PostConstruct, InitializingBean...
  |
  +-- product is requested:
        FactoryBean.getObject()
        cache if singleton factory and singleton product apply
  |
  +-- inject product into consumer
```

Spring may have logic to post-process objects returned by FactoryBean, yet **do not infer that the product automatically receives a full lifecycle like an ordinary bean definition**. If the product manages sockets/SDK thread pools, clarify who is responsible for initializing/closing resources. A singleton factory can implement `DisposableBean` to clean up products it owns, or use a separate managed lifecycle component.

### When is the factory created yet the product is not?

- Context refresh constructs an eager singleton factory, while no consumer has requested the product yet.
- A type lookup permits eager initialization of the **factory** to inspect `getObjectType()`, without needing `getObject()` yet.
- The app calls `getBean("&textEncoder")` to inspect the factory, without requesting the product yet.
- A lazy consumer bean has not been resolved yet.

### When can the product be created early?

- An eager singleton consumer injects the product in its constructor.
- `getBeansOfType(Encoder.class)` needs to return an instance map.
- Code calls `getBean("textEncoder")`, even before the application is fully ready if permitted.
- `SmartFactoryBean.isEagerInit()` advertises that the product needs eager initialization during the appropriate pre-instantiation pass.

`isSingleton()==true` does not equate to the product being created immediately at context refresh. It refers to **the identity of the shared/cached object**. Conversely, `@Lazy` on a consumer only defers resolving that consumer's dependency if nothing else creates the product early.

## 12. Hands-on error diagnosis using Spring APIs

When encountering an injection failure involving a FactoryBean, do not immediately patch with `@Primary` or `@Lazy`. Separate the questions by stage:

```java
// In an already-refreshed ApplicationContext ctx:
System.out.println(ctx.getType("textEncoder"));
System.out.println(ctx.getType("&textEncoder"));

System.out.println(
        java.util.Arrays.toString(
                ctx.getBeanNamesForType(Encoder.class, true, false)));

System.out.println(
        java.util.Arrays.toString(
                ctx.getBeanNamesForType(Encoder.class, true, true)));

Encoder product = ctx.getBean("textEncoder", Encoder.class);
```

This debug snippet is not a standalone runnable program; `ctx`/`Encoder` must be defined. **Note:** calling `getBean` on the last line will create the product if it does not exist yet; only run when side effects are acceptable. Comparing the two `allowEagerInit` overloads helps distinguish candidates recognized from metadata versus candidates requiring factory initialization to discover.

Checklist:

1. Is the `textEncoder` bean definition actually registered in the right `ApplicationContext`? Did `@Profile` or `@Conditional` exclude it?
2. Is the bean retrieved as `"textEncoder"` (product) or `"&textEncoder"` (factory)?
3. What does `getType("textEncoder")` return **before** creating the product?
4. Can `FactoryBean.getObjectType()` return null in an early phase? Does it depend on `@PostConstruct` or late-injected fields?
5. Is the advertised type compatible with `getObject()`'s output under all configurations?
6. Is the factory initialized early when `allowEagerInit=true`? Does that initialization have unreasonable side effects?
7. Are there multiple product beans of the same type? Are `@Qualifier`/`@Primary` in the right place?
8. Is the type generic `Repository<User>` or raw `Repository`? Is metadata sufficient to distinguish?
9. Does `getObject()` throw exceptions, return null, or build a proxy not assignable as declared?
10. Is the consumer bean eager or lazy? Has another user resolved the product earlier?
11. If using a programmatic registry, is the `factoryBeanObjectType` attribute of the right `Class`/`ResolvableType` type?
12. Did a test inadvertently call `getBeansOfType`, causing all products to be instantiated before assertions?

### Common error table

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Autowiring `Encoder` reports no bean despite FactoryBean existing | `getObjectType()` null, bean profile inactive, missing type metadata | Publish a stable type, test type lookup early |
| `getBean("textEncoder")` works, yet injection by type fails | Name lookup does not require the same metadata as type matching | Fix `getObjectType`/generic/definition metadata |
| `getType("textEncoder")` returns null before startup use | Factory cannot predict product type yet | Return a common interface or early metadata |
| Two FactoryBeans have product type `Encoder` | Ambiguity | `@Qualifier`, `@Primary`, or inject collection |
| `getType("&textEncoder")` differs from desired type | Querying the factory's type | Drop `&` when querying the product |
| `getBeanNamesForType(..., false)` misses candidate | Eager type introspection is disallowed | Understand trade-off, use metadata or appropriate query |
| `getBeansOfType` makes SDK client connect early | Must materialize instances to return the map | List names first, then resolve selectively |
| `getObjectType()` queries the network | Side effect in type discovery | Remove I/O from type prediction |
| `factoryBeanObjectType` attribute is `String` | Invalid metadata in Spring 6.1+ | Use `Class<?>` or `ResolvableType` |
| Product type is JDK proxy interface, concrete class declared | Predicted class too specific, not assignable | Declare the exact interface the proxy implements |
| `FactoryBean<Repository>` fails to distinguish generic User/Order | Lost parameterized metadata | Declare concrete generic and test autowiring |
| Consumer `@Lazy` yet product still created on refresh | Eager dependency or `SmartFactoryBean` present | Check graph, factory lifecycle, and startup logic |
| Singleton factory, non-singleton product | `isSingleton() == false` | Distinguish factory lifecycle from product lifecycle |
| Singleton product is not thread-safe | Same reference used by multiple threads | Design immutability/synchronization separately |

## 13. Self-assessment exercises

1. Why does Spring need to know `FactoryBean.getObjectType()` before calling `getObject()`?
2. How do `getBean("textEncoder")` and `getBean("&textEncoder")` differ?
3. If `getObjectType()` depends on a `product` field only assigned in `getObject()`, what can happen when Spring autowires?
4. `FactoryBean<Encoder>` returns a `PrefixEncoder` product; is a consumer injecting `Encoder` valid if `getObjectType()` returns `Encoder.class`?
5. Is a consumer directly injecting `PrefixEncoder` guaranteed to match if the factory only declares `Encoder.class`?
6. Does `isSingleton()==true` force the product to be created at `refresh()`?
7. What is the difference between `getBeanNamesForType` and `getBeansOfType`?
8. What kind of candidate can `getBeanNamesForType(Encoder.class, true, false)` miss?
9. Why should `getObjectType()` not call a remote API to obtain the product class?
10. Two FactoryBeans both declare `Encoder.class`; how do you pick one for injection?
11. What data type does `FactoryBean.OBJECT_TYPE_ATTRIBUTE` require in Spring 6.2?
12. Why is a `Class<?>` insufficient to represent `Repository<User>`?
13. Can a `FactoryBean` be created while its product has not been created yet?
14. Does `@Lazy` on `ReportService` defer the product if another singleton eagerly injects it?
15. In the runnable example, what does the line `created after type query: 0` demonstrate?

**Suggested answers:** (1) To identify candidates/autowire without creating the product. (2) Without prefix returns the product, with `&` returns the factory. (3) Null or exception during type lookup; candidate may be skipped. (4) Yes. (5) Not guaranteed; the published type is too broad. (6) No. (7) One returns names, the other returns instances. (8) FactoryBeans/lazy beans needing eager init to predict type. (9) Causes side effects/latency/circular references. (10) `@Qualifier`/`@Primary`. (11) `Class<?>` or `ResolvableType`, not String. (12) Java `Class` does not carry type arguments; use generic signatures/metadata. (13) Yes. (14) No, another place can still request the product. (15) Type prediction did not require calling `getObject()` in that project.

## 14. Practical implementation principles

- Always distinguish **factory type**, **product type**, and **product instance**.
- `getObjectType()` is a critical contract for **autowiring by type**, not an optional secondary method.
- Return an accurate and stable type from known metadata/types **without creating the product**.
- Accept `null` only when genuinely indeterminable, and understand type-based lookup may skip the factory.
- Keep factory initialization lightweight; type discovery can cause the factory to be created before business logic uses the product.
- Be cautious with `allowEagerInit` when writing plugin registries/startup scanners.
- Do not use `getBeansOfType` if you only want to list names and cannot accept product creation.
- Use `@Qualifier`/`@Primary` when **multiple candidates match the type**, not to hide wrong metadata.
- For generic dependencies, verify actual `ResolvableType`/declarations in integration tests.
- Avoid side effects in `getObjectType()`; create real resources in `getObject()` with timeouts/error policies.
- If the product is shared, ensure thread safety and appropriate resource cleanup; `isSingleton()` does not substitute for this.
- Write tests verifying **type queries do not create the product**, then test autowiring and identity separately.

## 15. Official documentation

- Spring Framework — Customizing Instantiation Logic with FactoryBean: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework 6.2 — FactoryBean Javadoc (getObjectType, isSingleton, OBJECT_TYPE_ATTRIBUTE): https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/FactoryBean.html
- Spring Framework 6.2 — ListableBeanFactory Javadoc (getBeanNamesForType, allowEagerInit): https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/ListableBeanFactory.html
- Spring Framework 6.2 — BeanFactory Javadoc (FACTORY_BEAN_PREFIX, getType): https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/BeanFactory.html
- Spring Framework 6.2 — AbstractBeanFactory getTypeForFactoryBean metadata: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/support/AbstractBeanFactory.html
- Spring Framework 6.2 — ResolvableType Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/ResolvableType.html
- Spring Framework 6.2 — SmartFactoryBean Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/SmartFactoryBean.html
