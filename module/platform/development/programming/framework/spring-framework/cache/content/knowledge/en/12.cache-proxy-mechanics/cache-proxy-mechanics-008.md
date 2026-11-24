# Spring Cache: AspectJ Mode and Weaving Requirements

## Lesson Objectives

In Spring Framework, annotations such as `@Cacheable`, `@CachePut`, and `@CacheEvict` do not execute caching merely by appearing on a method. Spring needs a way to **intercept method calls** to decide when to read, write, or evict cache entries. The default mode uses **Spring AOP proxies**; the alternative mode uses **AspectJ weaving** to transform the bytecode of eligible classes.

This lesson focuses on **AspectJ mode and the mandatory conditions for weaving to actually take effect**, particularly for solving self-invocation in Spring Cache. After this lesson, you will be able to:

- Explain the difference between calls passing through a **proxy** and calls that are **AspectJ woven**.
- Know when `@EnableCaching(mode = AdviceMode.ASPECTJ)` is appropriate.
- Distinguish **compile-time weaving (CTW)**, **post-compile weaving**, and **load-time weaving (LTW)**.
- Properly prepare `spring-aspects`, **AspectJ weaver/agent**, Spring configuration, and the scope of classes to weave.
- Understand why `@EnableAspectJAutoProxy` or merely adding `aspectjweaver.jar` without activating weaving **is not enough**.
- Run a Java 17 example showing **self-invocation still caches when weaving is active**.
- Diagnose failures: method re-runs despite `@Cacheable`, annotations placed only on interfaces, inactive agent, classes loaded before weaving, and unready cache configuration.

> **Key idea:** `AdviceMode.ASPECTJ` selects **how Spring Cache applies advice**; it **does not modify bytecode by itself**. To work, the application needs the Spring caching aspect in `spring-aspects.jar` **and** an actual AspectJ weaving step (at compile time or when classes are loaded by the JVM).

## 1. Why Does Spring Cache Often Hit Self-Invocation Limits?

Imagine a bean with two methods:

~~~java
public class PriceService {
    public String checkoutPrice(String sku) {
        return findPrice(sku); // internal call on the same object
    }

    @Cacheable(cacheNames = "prices", key = "#p0")
    public String findPrice(String sku) {
        return repository.findPrice(sku);
    }
}
~~~

This is an **illustrative snippet**; `repository` and cache configuration are not defined here.

In the default **proxy mode**, the object other beans receive may be a Spring proxy. External calls to `proxy.findPrice("A")` pass through the caching interceptor. However, once inside `PriceService`, calling `this.findPrice("A")` or `findPrice("A")` invokes the method directly on the target object **without going back through the proxy**. Consequently, the cache annotation on `findPrice` is not applied for that internal call.

### Comparison Diagram

~~~text
PROXY MODE:

Caller -> Spring proxy -> cache advice -> target.findPrice()
                                      |
                         cache hit may skip target

Caller -> Spring proxy -> target.checkoutPrice()
                                |
                                +-- this.findPrice()
                                    (bypasses cache advice)


ASPECTJ MODE (woven class):

Caller -> PriceService.checkoutPrice()
                       |
                       +-- this.findPrice()
                                  |
                       advice woven into bytecode
                                  |
                            cache hit/miss
~~~

With AspectJ, advice is applied at the **join point of the woven method**, regardless of whether the call goes through a Spring proxy. Thus self-invocation on a method matched by the AspectJ caching aspect **can trigger caching**.

Do not switch an entire application to AspectJ just for one internal call. First consider splitting responsibilities into separate Spring beans so calls go through proxies, or redesigning caching boundaries. AspectJ requires more complex build/deployment pipelines and carries its own testing and operational costs.

## 2. Two Modes for Processing Caching Annotations

Enabling caching by default:

~~~java
@Configuration
@EnableCaching
public class CacheConfig {
    // Register CacheManager ...
}
~~~

Equivalent in intent to:

~~~java
@EnableCaching(mode = AdviceMode.PROXY)
~~~

To request AspectJ mode:

~~~java
import org.springframework.context.annotation.AdviceMode;
import org.springframework.cache.annotation.EnableCaching;

@EnableCaching(mode = AdviceMode.ASPECTJ)
~~~

The snippets above are **illustrative configuration syntax**, not complete Java files.

| Feature | `AdviceMode.PROXY` | `AdviceMode.ASPECTJ` |
| --- | --- | --- |
| Mechanism | Spring AOP creates a proxy around the bean | AspectJ transforms target class bytecode |
| External call via bean proxy | Intercepted if eligible | Intercepted if class/method is woven and matches aspect |
| Self-invocation within same object | Does not go through proxy, so typically not cached | Can be intercepted because advice lives at method execution |
| Requires `spring-aspects`? | Not specifically for Spring Cache proxies | Yes |
| Requires bytecode weaving step? | No | Yes: CTW, post-compile weaving, or LTW |
| Does `proxyTargetClass` control weaving? | Affects proxy selection per configuration | **No**; ignored in AspectJ mode |
| Annotations on interfaces | Recognized by proxy in some cases | **Do not use**; AspectJ caching aspect does not recognize interface-only annotations |
| Non-public methods | Proxy caching typically does not support as expected | AspectJ can weave matching calls depending on pointcut and environment |
| Build/run complexity | Lower | Higher; requires verifying agent, class loader, runtime weaving |
| Applies to objects not accessed via proxy | Not under proxy semantics | Possible if the class is woven and the aspect is properly configured |

**Do not confuse:** `@EnableAspectJAutoProxy` only enables **Spring AOP using `@AspectJ` annotation syntax**, which still creates **proxies**. The annotation name contains "AspectJ," yet it **does not enable AspectJ bytecode weaving**. It is not a substitute for the AspectJ agent or compiler.

Similarly, `@EnableCaching(proxyTargetClass = true)` only changes how proxies are created in proxy mode. Using class-based proxies (CGLIB) **does not solve self-invocation** either; `this.method()` calls still bypass the proxy.

## 3. Three Forms of Weaving and Their Differences

*Weaving* is the process of combining advice/aspects with matching execution points of a class. With the same `@Cacheable`, AspectJ can take effect at different weaving times.

### 3.1. Compile-Time Weaving (CTW)

The AspectJ compiler (`ajc`) compiles and weaves aspects into **bytecode during the build**. The output `.class` files or JARs are already transformed. At runtime, a separate `-javaagent` is usually not needed for classes that have already been fully woven.

Requirements:

- An AspectJ compiler/plugin compatible with your JDK and bytecode version.
- `spring-aspects` present on the **aspect path** so the compiler knows which aspects to apply.
- Application classes properly processed by the compiler, rather than compiled with `javac` while skipping weaving.
- Packaging the proper Spring/AspectJ runtime dependencies with the application.

Pros: weaving can be verified during the build, avoiding class transformation at startup. Cons: more complex pipeline configuration, and you must ensure **every class needing interception was actually woven**. If the build has modules publishing separate JARs, classes in those modules must also be accounted for.

### 3.2. Post-Compile Weaving

Java code is compiled to bytecode first, and then an AspectJ weaving step processes the **compiled classes/JARs**. This is useful when you want to keep standard compilation while still weaving inside the build pipeline.

Do not merely add a Maven plugin named AspectJ and assume every module is woven: inspect **inpath/aspectpath, output classes, plugin execution order, and the actual deployed artifact**. If an unwoven JAR is accidentally packaged, the application may start while self-invocation fails to cache.

### 3.3. Load-Time Weaving (LTW)

The AspectJ weaver transforms bytecode **when the JVM loads classes**, before each class is defined for execution. For a standalone Java application, the common approach is launching the JVM with a Java agent:

~~~bash
java -javaagent:/path/to/aspectjweaver.jar -cp "..." demo.Main
~~~

This command is only a **syntax template**; a concrete runnable example is in Section 6.

For LTW, you need:

1. `aspectjweaver.jar` at a version supporting your running bytecode/JDK.
2. The JVM **actually** started with the agent or a load-time weaving mechanism providing an appropriate `ClassFileTransformer`.
3. The aspects to weave (Spring's caching aspect from `spring-aspects.jar`) on the classpath and declared so AspectJ recognizes them.
4. Target classes loaded **through a class loader controlled by the weaver**; classes already defined before the agent/weaver attaches are not retroactively woven by standard LTW configurations.
5. Spring's caching infrastructure configured (e.g., `@EnableCaching(mode = AdviceMode.ASPECTJ)` and `CacheManager`) before cache-advised methods are called.

LTW is convenient when you do not want to alter the compilation pipeline, yet it depends on **how the JVM is launched**. In containers, test runners, IDEs, servers, or actual `java` commands, verify that the running JVM receives the right `-javaagent`.

### Lifecycle Comparison

~~~text
Java source
    |
    +--> ajc / compile-time weaving --------> woven .class --> JVM
    |
    +--> javac --> ordinary .class
                      |
                      +--> post-compile weave --> woven .class --> JVM
                      |
                      +--> JVM + AspectJ agent
                                      |
                                load-time weave
                                      |
                                woven loaded class
~~~

The three deployment paths **do not need to be used simultaneously**. Pick one clear path for the classes requiring interception and verify the output. Weaving the same class across multiple stages can produce warnings or hard-to-diagnose behavior.

## 4. Prerequisites for Spring Cache AspectJ to Actually Work

### Requirement A — Select the Proper Caching Advice Mode

A Spring `@Configuration` class must declare:

~~~java
@EnableCaching(mode = AdviceMode.ASPECTJ)
~~~

Spring configures AspectJ caching infrastructure instead of standard proxy caching. If left at default `PROXY`, adding `spring-aspects` or running an agent will not switch **the caching mechanism configured by Spring** to AspectJ mode.

### Requirement B — Include the Spring Caching Aspect

The `org.springframework:spring-aspects` module contains Spring's AspectJ aspects, including:

~~~text
org.springframework.cache.aspectj.AnnotationCacheAspect
~~~

It is distinct from `org.springframework:spring-aop` (which supports Spring's proxy AOP).

For the standalone Java program in this lesson, `spring-aspects` **must match the Spring Framework version** to avoid API mismatches. For example, `spring-context:6.2.10` pairs with `spring-aspects:6.2.10`.

`spring-aspects.jar` also bundles an AspectJ configuration `META-INF/aop.xml` identifying its aspects. In basic LTW setups using Spring aspects, **you do not need to create a separate `aop.xml`** solely to activate `AnnotationCacheAspect`; verify the file inside the JAR is on the runtime classpath.

### Requirement C — Have an Actual Weaving Mechanism

Simply adding the dependency:

~~~xml
<dependency>
  <groupId>org.aspectj</groupId>
  <artifactId>aspectjweaver</artifactId>
  <version>1.9.22.1</version>
</dependency>
~~~

is **not enough** for weaving to occur. The dependency puts the library on the classpath, yet classes will not transform by themselves without an agent/transformer or a build step using `ajc`. In the LTW example, `-javaagent:...` is mandatory.

`spring-boot-starter-aop` or `@EnableAspectJAutoProxy` are not aliases for AspectJ LTW either. They generally serve Spring proxy AOP.

### Requirement D — Place Annotations on Concrete Classes/Methods

Spring recommends placing `@Cacheable`, `@CachePut`, and `@CacheEvict` on **methods of the concrete class**, not solely on interfaces:

~~~java
public interface Catalog {
    String lookup(String sku);
}

public class CatalogService implements Catalog {
    @Cacheable(cacheNames = "items", key = "#p0")
    public String lookup(String sku) {
        return "item-" + sku;
    }
}
~~~

In the illustrative example above, the annotation is placed **directly on the implementation**, suitable for AspectJ weaving. If you put `@Cacheable` only on `Catalog.lookup` without annotating the implementation, **the weaving-based caching aspect will not detect it as expected**, because Java does not inherit annotations from interface methods onto implementation methods.

### Requirement E — Objects and Spring Infrastructure Must Be Ready

When a cache-advised method runs, the aspect must already be configured by Spring with `CacheManager`/`CacheResolver` and components such as key generators and error handlers. In the example running from `ApplicationContext`, we retrieve the bean **after context initialization finishes**.

Do not call cache-annotated methods inside constructors/`@PostConstruct` expecting normal business-call behavior. In proxy mode, the bean is not yet ready via proxy; in AspectJ mode, bytecode may already be woven while the caching aspect is not fully configured yet. Initialization and operation are two distinct phases.

## 5. When Should You Consider AspectJ Instead of Proxies?

`AdviceMode.ASPECTJ` is typically valuable when:

- There are **genuinely unavoidable self-invocations** that must pass through cache advice and splitting beans is unreasonable.
- You need interception on methods that Spring proxies cannot easily wrap, after verifying the actual pointcuts of `AnnotationCacheAspect`.
- The application already has a tested, stable **AspectJ CTW/LTW pipeline**.
- The team can manage weaving agent versions, JPMS/class loaders, logging, CI, and build/deployment complexity.

Do not choose AspectJ merely because:

- You want `@Cacheable` on a `public` method called from another bean: proxy mode already handles this.
- You think `proxyTargetClass = true` or `@EnableAspectJAutoProxy` automatically means weaving.
- You want to cache every method, including ones with side effects or unstable return values.
- You want caching to work "automatically" before the Spring Context is initialized or at an inappropriate object lifecycle stage.

**Prefer simplicity:** if you only need to resolve self-invocation in one service, extracting the cached method into another bean is usually far less complex than altering the entire JVM/build setup.

## 6. Runnable Java 17 Example: Self-Invocation Cached via LTW

The project below uses **Java 17, Maven, Spring Framework 6.2.10**, and **AspectJ Weaver 1.9.22.1**. It registers `@EnableCaching(mode = AdviceMode.ASPECTJ)` and uses the JVM `-javaagent` flag to weave bytecode at class-load time.

The example uses `ConcurrentMapCacheManager` to keep the cache in RAM for easy observation. No Spring Boot, Redis, or database is required.

### 6.1. Directory Structure

~~~text
spring-cache-aspectj/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AspectjCachingDemo.java
~~~

You do not need to create a custom `META-INF/aop.xml` for this example because the `spring-aspects` JAR already includes the corresponding aspect configuration.

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-cache-aspectj</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.10</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-aspects</artifactId>
      <version>6.2.10</version>
    </dependency>
    <dependency>
      <groupId>org.aspectj</groupId>
      <artifactId>aspectjweaver</artifactId>
      <version>1.9.22.1</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-dependency-plugin</artifactId>
        <version>3.8.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Maven compiles the Java code with the compiler plugin; then the dependency plugin copies runtime JARs into `target/dependency`. **Weaving happens when the JVM runs with the agent**, not because Maven compiler inherently knows about AspectJ.

### 6.3. src/main/java/demo/AspectjCachingDemo.java

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AdviceMode;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class AspectjCachingDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching(mode = AdviceMode.ASPECTJ)
    public static class Config {

        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("items");
        }

        @Bean
        public CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static class CatalogService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "items", key = "#p0")
        public String load(String sku) {
            int n = loads.incrementAndGet();
            return "Item-" + sku + " (load=" + n + ")";
        }

        // INTERNAL call: does not pass through a Spring proxy.
        public String loadInternally(String sku) {
            return this.load(sku);
        }

        public int sourceLoads() {
            return loads.get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            CatalogService service =
                context.getBean(CatalogService.class);

            System.out.println("First self: " +
                service.loadInternally("A"));
            System.out.println("Second self: " +
                service.loadInternally("A"));
            System.out.println("Direct: " + service.load("A"));
            System.out.println(
                "Source loads: " + service.sourceLoads());

            System.out.println("Other key: " +
                service.loadInternally("B"));
            System.out.println(
                "Source loads: " + service.sourceLoads());
        }
    }
}
~~~

Key points:

1. `Config` uses `@EnableCaching(mode = AdviceMode.ASPECTJ)`: selects the caching aspect instead of proxy advice.
2. `spring-aspects` provides `AnnotationCacheAspect`.
3. The JVM launch command must include the **AspectJ agent** so `CatalogService.load` is actually woven.
4. `loadInternally` calls `this.load(sku)`. This is where **proxy mode** normally bypasses the annotation. When weaving is active, AspectJ advice intercepts `load` execution even when called within the same object.
5. `loads` tracks how many times the method body actually runs. Cache hits return the initial value without incrementing the counter.
6. The service is managed by Spring and retrieved from the context before calling business methods.

### 6.4. Running on Linux/macOS with Java 17

In the directory containing `pom.xml`:

~~~bash
mvn -q -DskipTests package dependency:copy-dependencies
java -javaagent:target/dependency/aspectjweaver-1.9.22.1.jar \
     -cp "target/classes:target/dependency/*" \
     demo.AspectjCachingDemo
~~~

`-javaagent` is a **JVM argument** and must appear before the main class name. `:` in the classpath is the separator on Linux/macOS.

On **Windows PowerShell**, use `;` for the classpath:

~~~powershell
mvn -q -DskipTests package dependency:copy-dependencies
java -javaagent:target/dependency/aspectjweaver-1.9.22.1.jar -cp "target/classes;target/dependency/*" demo.AspectjCachingDemo
~~~

Use the `target/dependency` path instead of guessing Maven's local repository path: `dependency:copy-dependencies` places the runtime JARs in that directory. With IDEs, Gradle, or Fat JARs, the JVM startup mechanism and weaver JAR path differ, though the agent and runtime classpath principles stay the same.

### 6.5. Expected Output

The lines **printed by the program itself** (excluding JVM/weaver and Maven messages) are:

~~~text
First self: Item-A (load=1)
Second self: Item-A (load=1)
Direct: Item-A (load=1)
Source loads: 1
Other key: Item-B (load=2)
Source loads: 2
~~~

Explanation:

- The first `loadInternally("A")` calls `load("A")`; key `"A"` is absent so `loads` increments to 1, and the result is stored in cache `items`.
- The second call is **within the same object**, yet because `load` is woven, the advice handles the cache hit; the method body does not re-run.
- The direct call `service.load("A")` also hits the same `"A"` entry, so the result still shows `load=1`.
- `loadInternally("B")` produces a different key and misses, incrementing `loads` to 2.

If you only switch to `@EnableCaching(mode = AdviceMode.ASPECTJ)` and **forget the agent or weaving step**, do not assume the output above is guaranteed. The app may start without intercepting the method properly, or fail with other configuration errors. Use integration tests observing source-method execution counts and confirming weaving in logs/bytecode.

### 6.6. Conditions for the Example to Hold

- Both `spring-context` and `spring-aspects` use the same Spring Framework version.
- Runtime JDK is 17 or a version supported by the chosen AspectJ weaver.
- The Java agent is **loaded into the JVM executing the application**, not merely the JVM running another build command.
- `spring-aspects` is on the runtime classpath so the weaver finds the caching aspect.
- `CatalogService` is loaded after the weaver is active and the method is successfully woven.
- `@Cacheable` is on the **concrete method** `CatalogService.load`, not only on an interface.
- `CacheManager` has the `items` cache, and `ApplicationContext` completes initialization before calls.
- The example is single-threaded; in concurrent environments, cache stampede and transactions are separate concerns.

## 7. What Is `META-INF/aop.xml` Used For?

AspectJ LTW can read one or more `META-INF/aop.xml` files on the classpath. This file declares aspects and weaving options, such as restricting which classes are woven.

In standard **Spring Cache AspectJ**, `spring-aspects.jar` contains `META-INF/aop.xml` declaring `org.springframework.cache.aspectj.AnnotationCacheAspect` alongside several other Spring aspects. That is why the Section 6 demo does not require adding your own configuration file.

An **illustrative** LTW configuration structure for a custom aspect:

~~~xml
<!DOCTYPE aspectj PUBLIC "-//AspectJ//DTD//EN"
  "https://www.eclipse.org/aspectj/dtd/aspectj.dtd">
<aspectj>
  <weaver options="-showWeaveInfo">
    <include within="demo..*"/>
  </weaver>
  <aspects>
    <aspect name="demo.PerformanceAspect"/>
  </aspects>
</aspectj>
~~~

This is **not a file to create for the caching demo**; `demo.PerformanceAspect` is just an example name and does not exist in the runnable project. When managing `aop.xml` in another project, use real aspect names, account for `aop.xml` files already bundled in dependency JARs, and avoid duplicate declarations or conflicting weave scopes.

Narrowing weave scope can reduce startup overhead, warnings, and unintended impact on unrelated libraries. However, overly narrow filters can also leave `@Cacheable` classes **unwoven**, causing caching behavior not to appear.

### Inspecting the JAR Configuration

On a system with a JDK, you can inspect the file listing:

~~~bash
jar tf target/dependency/spring-aspects-6.2.10.jar
~~~

Look for `META-INF/aop.xml` in the output. This is a **classpath diagnostic step**, not proof that the agent performed weaving.

## 8. Do You Need `@EnableLoadTimeWeaving` or `spring-instrument`?

Spring also provides **Spring-managed load-time weaving** via `@EnableLoadTimeWeaving`, `LoadTimeWeaver`, `InstrumentationLoadTimeWeaver`, and container integration classes. This mechanism differs from launching the JVM directly with the **AspectJ agent**.

Two common paths:

1. **Direct AspectJ agent** (`-javaagent:aspectjweaver.jar`): the agent itself registers AspectJ's class transformer. This is the path shown in the demo. You do not need to add `@EnableLoadTimeWeaving` just to demonstrate this flow.
2. **Spring-managed LTW**: Spring configures a `LoadTimeWeaver` on the appropriate class loader. Some application environments support instrumentation natively; in standalone Java environments, `-javaagent:spring-instrument.jar` may be needed to supply JVM instrumentation for this mechanism. AspectJ weaving infrastructure and the matching caching aspect are still required.

**Do not treat the two agents as identical:** `spring-instrument.jar` supports Spring-managed instrumentation; `aspectjweaver.jar` contains the AspectJ bytecode weaver. Depending on the LTW setup, agent and transformer requirements differ. Do not attach multiple agents blindly "just to be sure"; choose one model and verify the actual class loader.

### Notes for Spring Boot Applications

Spring Boot builds and packages the classpath using its own layout (fat JAR/nested JAR). When deploying via `java -jar`, verify the **agent is passed to the right JVM** and can see the metadata, aspects, and classes to weave. In containers, startup scripts, Kubernetes, or IDEs, check the actual JVM arguments list; merely putting a dependency in `pom.xml` does not enable the agent.

## 9. AspectJ and Special Method Kinds

### 9.1. Annotations Placed Only on an Interface

~~~java
public interface ItemReader {
    @Cacheable(cacheNames = "items")
    String load(String code);
}

public class ItemReaderImpl implements ItemReader {
    @Override
    public String load(String code) {
        return "item-" + code;
    }
}
~~~

This is an **anti-pattern for AspectJ mode**. Java does not inherit annotations from interface methods onto implementation methods. The weaving-based caching aspect does not recognize configurations declared only on an interface as you might expect. Move the annotation down to the method in the concrete class.

### 9.2. Non-Public Methods

Proxy caching typically supports only `public` methods per Spring's guidance. AspectJ bytecode weaving can handle join points that proxies have no way to intercept, including certain non-public methods, **when the aspect pointcut matches**. Still, do not assume every private/static/constructor method is handled by Spring Cache.

`@Cacheable` is a **method** annotation and Spring's caching aspect has a specific pointcut scope. For non-public methods or framework-generated bytecode, check weave logs and integration tests instead of just looking at the annotation.

### 9.3. `final` Classes and Methods

Subclass-based proxies cannot override `final` methods. AspectJ weaving modifies the target class bytecode directly and therefore does not depend on subclass overriding that way. Even so, test actual classes with Kotlin/record/final bytecode, module boundaries, and code generators.

### 9.4. Objects Not Instantiated by Spring

Because AspectJ weaving transforms classes, it does not rely solely on whether an object is wrapped by a Spring proxy. Nevertheless, Spring Cache advice still requires configured caching infrastructure and valid cache names/keys. Do not treat class weaving as a guarantee that any arbitrary object, at any moment, will cache properly with business or transaction context.

### 9.5. Custom / Meta-Annotations

Spring Cache can support custom/meta-annotations in proxy-based infrastructure, whereas the standard caching aspect from `spring-aspects` is primarily designed for **the standard cache annotations**. If you use custom annotations and expect AspectJ to recognize them, you may need to build/customize an aspect or matching pointcut. Do not assume AspectJ applies identically just because proxy mode recognizes a meta-annotation.

## 10. Diagnosing When AspectJ Is Enabled Yet Caching Has No Effect

Check sequentially in order:

1. **Is the right mode active?** Confirm the running config has `@EnableCaching(mode = AdviceMode.ASPECTJ)` and not another `PROXY` config overriding unexpectedly.
2. **Is the matching version of `spring-aspects` present?** Verify the JAR is on the runtime classpath and contains `AnnotationCacheAspect` and `META-INF/aop.xml`.
3. **Does the running JVM have the agent?** Inspect the startup command/process arguments of the application JVM. A Maven build command or a different IDE runner cannot substitute for the agent on the JVM serving requests.
4. **Is the agent compatible with bytecode/JDK?** Check AspectJ version, JVM version, and class file format warnings.
5. **Was the class loaded too early?** LTW normally weaves when a class is loaded; if a class was already loaded before the transformer activated, later configuration will not alter that class.
6. **Does the pointcut match?** Check whether the annotation is on the concrete method rather than only an interface, method signatures, weave scope, and include/exclude filters.
7. **Is the Spring caching aspect configured?** Verify the context is ready, `CacheManager`/`CacheResolver` is registered, and the cache name exists.
8. **Does execution actually reach the annotated method?** Test through the real business path; do not rely on reflection or unit tests that only inspect annotations.
9. **Is another caching layer interfering?** When proxy caching and AspectJ advice coexist due to overlapping configurations, unpredictable behavior can occur. Separate responsibilities clearly.
10. **Are cache provider exceptions occurring?** Missing cache names, wrong keys, backend timeouts, or error handlers can produce symptoms looking like "cache is not working."

### How to Prove Weaving Actually Occurred

Do not rely solely on measuring response time. Use a **counter inside the method body** as in the demo: calling twice with the same key increments the counter only once when caching works.

You can enable AspectJ weaver logging/information via the appropriate configuration to observe woven join points. For production applications, turn off overly verbose weave logging after diagnosis.

### Distinguishing 3 Failure Patterns

| Symptom | Likely cause | Check |
| --- | --- | --- |
| Self-invocation runs method body every time, no exception | Method was not woven or advice not active | JVM agent, aop.xml, pointcut, config mode |
| Cache advice runs but throws "Cannot find cache..." | Cache name cannot be resolved by manager | CacheManager, cacheNames, profiles |
| Method hits cache but returns stale/wrong data | Wrong key, invalidation, or business data | Key generator, TTL, `@CacheEvict`, transactions |
| JVM crashes/fails to start with agent enabled | Incompatible agent/JDK/class loader/modules | Weaver version, JVM flags, logs |
| Interface annotation worked in proxy mode but not in AspectJ | Annotation missing on concrete implementation | Move annotation |
| `@EnableAspectJAutoProxy` enabled yet self-invocation does not cache | Using proxies, no bytecode weaving | `AdviceMode.ASPECTJ` + actual weaving |

## 11. Impact on Transactions, Concurrency, and Performance

AspectJ solves **how interception happens**; it **does not solve every cache property**:

- **Stale data:** `@Cacheable` only reuses data; when the database changes, you still need appropriate `@CacheEvict`, `@CachePut`, TTL, or invalidation policies.
- **Transactions:** woven bytecode does not make a database update and a cache put/evict an atomic transaction. You still must consider commit ordering, rollbacks, and transaction-aware caches.
- **Concurrency:** multiple requests missing the same key concurrently can cause duplicate loads or cache stampedes; handle via cache/provider features or `sync` where supported, not merely by enabling AspectJ.
- **Performance:** LTW can add startup time/transformer overhead; CTW adds build time. Method interception and cache operations still have runtime overhead. Measure with benchmarks matching your workload.
- **Tracing/debugging:** stack traces, bytecode, and advice order can differ from proxy mode. If using security/transaction/retry aspects, test interaction order and failure behavior.
- **Native image/AOT/JPMS:** environments that do not support dynamic bytecode modification like a standard JVM may require different designs; do not assume LTW is compatible with every deployment target by default.
- **Scope:** overly broad weaving causes unnecessary overhead or warnings; overly narrow weaving misses classes that need caching.

Do not use cache annotations to "skip" methods with mandatory side effects. AspectJ causes interception across more call paths, meaning side effects skipped by cache hits can also be skipped in **more places that previously were never cached**. Review method purity when switching modes.

## 12. Checklist for Migrating from PROXY to ASPECTJ

### Pre-Change Checks

- [ ] There is a real problem proxy mode cannot reasonably solve (such as unavoidable self-invocation).
- [ ] Extracting a bean was considered before changing the application-wide weaving infrastructure.
- [ ] Cache-annotated methods do not depend on side effects running on every call.
- [ ] `@Cacheable`/`@CachePut`/`@CacheEvict` sit on the concrete methods to be woven.
- [ ] Target Spring Framework version, JDK version, and AspectJ version are known.
- [ ] A single verifiable path—either **CTW/post-compile weaving** or **LTW**—has been chosen.

### Configuration Checks

- [ ] `@EnableCaching(mode = AdviceMode.ASPECTJ)` is in the proper Spring context.
- [ ] `spring-aspects` is on the runtime/aspect path with the same version as Spring Framework.
- [ ] If using LTW, the executing JVM receives the right agent/transformer.
- [ ] `META-INF/aop.xml` declares the caching aspect, or equivalent configuration is verified.
- [ ] Classes to weave are loaded within the active scope of the weaver.
- [ ] `CacheManager`/`CacheResolver`, `cacheNames`, and key generator are validly configured.
- [ ] Not expecting `@EnableAspectJAutoProxy` or `proxyTargetClass` to replace weaving.

### Post-Deployment Checks

- [ ] Directly test **self-invocation**: same key twice, method body runs only once.
- [ ] Test calls from other beans and multiple distinct keys.
- [ ] Test cache put/evict, null results, and exceptions per business contract.
- [ ] Test transaction rollbacks, cache backend failures, and concurrent calls.
- [ ] Test startup in real runtime environments: IDE, JAR/container, server/test runner.
- [ ] Inspect logs/metrics for cache hits/misses and appropriate weave information.
- [ ] Have a rollback plan back to proxy mode if weaving proves incompatible with the environment.

## 13. Self-Check Questions

**1.** Does `@EnableCaching(mode = AdviceMode.ASPECTJ)` modify class bytecode by itself?  
**Answer:** No. It selects AspectJ caching configuration; `spring-aspects` and an actual weaving process are still required.

**2.** Why does `this.load(id)` usually skip `@Cacheable` in proxy mode?  
**Answer:** Internal calls do not go through the Spring proxy. With AspectJ, advice can live inside the woven method bytecode.

**3.** Is adding the `aspectjweaver` dependency to Maven enough for LTW to work?  
**Answer:** No. You must enable the agent or an LTW mechanism with a suitable transformer when the JVM loads classes.

**4.** Is `@EnableAspectJAutoProxy` equivalent to native AspectJ weaving?  
**Answer:** No. It configures Spring AOP proxies, even though it uses `@AspectJ` syntax.

**5.** In CTW, is a runtime Java agent always mandatory?  
**Answer:** No, provided all classes needing advice were fully woven during the build and the required libraries are on the runtime classpath.

**6.** Should `@Cacheable` be placed only on an interface when using AspectJ mode?  
**Answer:** No. Place annotations on implementation methods / concrete classes.

**7.** Why doesn't `proxyTargetClass=true` fix self-invocation?  
**Answer:** It only controls proxy type; it does not route `this.method()` calls through the proxy.

**8.** What does `spring-aspects.jar` provide for AspectJ caching?  
**Answer:** Spring's caching aspect, including `AnnotationCacheAspect`, along with AspectJ configuration to recognize the aspect.

**9.** Will a class already defined by the JVM before LTW is enabled be re-woven automatically?  
**Answer:** Not under standard LTW mechanisms. The agent/weaver must be active before classes needing interception are loaded.

**10.** Why should demo output rely on a counter instead of only looking at execution time?  
**Answer:** A counter directly shows how many times the method body ran, proving a cache hit during self-invocation.

**11.** If a class is woven but the cache does not exist, will AspectJ create the right cache region automatically?  
**Answer:** No. Resolving/creating cache regions is still governed by `CacheManager`/`CacheResolver` and provider policies.

**12.** Does switching to AspectJ make cache put/evict and a DB transaction atomic?  
**Answer:** No. AspectJ changes the interception mechanism, not data consistency or transaction design.

## References

- Spring Framework Reference — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Reference — Using AspectJ with Spring Applications: https://docs.spring.io/spring-framework/reference/core/aop/using-aspectj.html
- Spring Framework Reference — Enabling @AspectJ Support (distinguishing proxies from weaving): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework API — EnableCaching: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/annotation/EnableCaching.html
- Spring Framework spring-aspects META-INF/aop.xml: https://github.com/spring-projects/spring-framework/blob/main/spring-aspects/src/main/resources/META-INF/aop.xml
- AspectJ project — Java bytecode/JDK compatibility: https://github.com/eclipse-aspectj/aspectj/blob/master/docs/release/JavaVersionCompatibility.adoc
