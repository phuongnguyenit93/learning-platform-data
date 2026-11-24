# When Does a Bean Need Information from the Container? — Aware Callbacks in Spring

## 1. The Problem to Solve

A typical Spring bean only needs business collaborators such as a repository, HTTP client, or another service. The Spring IoC Container passes those dependencies through constructor, setter, or field injection. The bean does not need to know that the container exists, where it was instantiated, or what name it has.

Occasionally, an **infrastructure bean** needs information held only by the container: its actual bean name, the `BeanFactory` that created it, the `ApplicationContext` that owns it, the `Resource` loader, the `Environment`, the application event publisher, or the `MessageSource`. Spring supports a family of interfaces with the **`Aware`** suffix to pass this information into the bean via callbacks.

The question "When does a bean need information from the container?" should be answered based on **the responsibility of the bean itself**:

- **Use Aware** when the bean implements a framework extension, infrastructure adapter, or diagnostic tool, or needs metadata/capabilities directly tied to the Spring container.
- **Prefer constructor injection** when the bean only needs a business dependency or a specific infrastructure interface that Spring can inject directly.
- **Prefer `ObjectProvider<T>`** when you need to obtain a bean on demand, such as a new prototype for each task, without holding the entire `BeanFactory`.
- **Avoid using `ApplicationContext` as a service locator** in every business method; this hides dependencies, increases coupling to Spring, and makes unit testing harder.

After this lesson, you will understand each Aware callback accurately, know when it runs in the bean lifecycle, choose a minimal interface, and be able to run a Java 17 example on Spring Framework 6.1.x.

## 2. The Nature of the `Aware` Interface

`org.springframework.beans.factory.Aware` is a **marker interface**. It does not define any callback methods itself. Sub-interfaces define their own methods; Spring or an appropriate `BeanPostProcessor` must recognize and invoke those methods.

Three common examples:

~~~java
// Abbreviated API signatures for illustration; do not redefine them yourself.
public interface BeanNameAware extends Aware {
    void setBeanName(String name);
}

public interface BeanFactoryAware extends Aware {
    void setBeanFactory(BeanFactory beanFactory) throws BeansException;
}

public interface ApplicationContextAware extends Aware {
    void setApplicationContext(ApplicationContext context)
        throws BeansException;
}
~~~

Actual packages:

- `BeanNameAware` and `BeanFactoryAware` are in `org.springframework.beans.factory`.
- `ApplicationContextAware` is in `org.springframework.context`.
- `Aware` is in `org.springframework.beans.factory`.

**Simply naming an interface ending with `Aware` does not make Spring invoke the callback automatically.** For a custom application-defined interface, an explicit processor or infrastructure must handle it.

### Two Ways to Express Dependencies

The right approach for most services:

~~~java
@Service
public class CheckoutService {
    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public void checkout() {
        gateway.charge();
    }
}
~~~

This is an illustrative snippet that requires defining `PaymentGateway` and Spring imports. The `PaymentGateway` dependency is explicitly visible in the constructor.

The approach that is easily overused:

~~~java
@Service
public class CheckoutService implements ApplicationContextAware {
    private ApplicationContext context;

    @Override
    public void setApplicationContext(ApplicationContext context) {
        this.context = context;
    }

    public void checkout() {
        context.getBean(PaymentGateway.class).charge();
    }
}
~~~

This is an **alternative** version; do not combine classes with the same name in one project. Both can work when configured properly, but the second version hides the core dependency inside a method, couples the class to the container, and makes testing no longer as simple as passing a fake gateway.

For a business service, constructor injection is usually easier to understand and safer. Aware callbacks exist for cases that genuinely need **container information**.

## 3. Quick Decision Table by Information Needed

| Interface | What does the container provide? | Appropriate use cases |
| --- | --- | --- |
| `BeanNameAware` | Actual bean name in the bean factory | Registry, metric tags, diagnostic logs by bean name |
| `BeanFactoryAware` | `BeanFactory` owning the bean | Infrastructure adapter needing on-demand bean or metadata lookup |
| `ApplicationContextAware` | `ApplicationContext` containing the bean | Framework integration needing broad context capabilities, hierarchy inspection |
| `EnvironmentAware` | `Environment` | Infrastructure analyzing profiles, property sources, or runtime configuration |
| `ResourceLoaderAware` | `ResourceLoader` | Adapter reading resources from classpath/file/URL |
| `ApplicationEventPublisherAware` | `ApplicationEventPublisher` | Infrastructure publishing application events |
| `MessageSourceAware` | `MessageSource` | Internationalization components resolving messages by locale |
| `BeanClassLoaderAware` | `ClassLoader` used by the bean factory | Plugins/class scanning, bytecode/tooling |
| `EmbeddedValueResolverAware` | `StringValueResolver` | Framework handling placeholders and embedded values |
| `ServletContextAware` | `ServletContext` of the web application | Servlet container integration |
| `ServletConfigAware` | `ServletConfig` in an appropriate web environment | Servlet-bound extensions |
| `LoadTimeWeaverAware` | `LoadTimeWeaver` when configured | Load-time weaving integration, specialized infrastructure |

Other interfaces such as `ApplicationStartupAware` and `ImportAware` are only useful in specialized framework/instrumentation scenarios. There is no need to implement every interface just because Spring supports it.

Distinguish between **what a bean can receive** and **what a bean should receive**. A class that only needs to publish events usually only needs `ApplicationEventPublisher`; holding the entire `ApplicationContext` grants excessive privileges.

## 4. When Do Aware Callbacks Run?

A bean **must be created before** Spring can invoke Aware setters. In the normal `ApplicationContext` creation path:

```text
Bean definition → constructor / @Bean factory method
               → dependency injection / property population
               → BeanNameAware / BeanClassLoaderAware / BeanFactoryAware
               → BeanPostProcessor before initialization:
                   ApplicationContext-level Aware interfaces; @PostConstruct
               → InitializingBean.afterPropertiesSet()
               → custom init method
               → BeanPostProcessor after initialization (may proxy)
               → bean has completed initialization
```

The three `BeanFactory`-related callbacks are handled directly; `ApplicationContextAware`, `ResourceLoaderAware`, and context-level interfaces are handled by `ApplicationContextAwareProcessor` before initialization. The order among **different `BeanPostProcessor` implementations** may depend on configuration/ordering. Lesson 185 proves each milestone with logs and explains the internal processor order.

**Note on readiness:** receiving `ApplicationContext` while the container **is refreshing** does not guarantee that all singletons or listeners are ready. Inside the callback, you should only store the reference or perform lightweight validation; do not trigger bulk `getBean()` calls to run long-running work. A constructor cannot read fields assigned by an Aware setter; if a collaborator is needed immediately at bean creation, use constructor injection.

## 5. `BeanNameAware`: Knowing the Name Assigned by the Container

`BeanNameAware.setBeanName(String)` receives the **actual bean name** that Spring uses for the definition being created:

```java
class NamedAdapter implements BeanNameAware {
    private String beanName;

    @Override public void setBeanName(String name) {
        this.beanName = name;
    }

    String label() { return "adapter=" + beanName; }
}
```

When `@Bean("paymentAdapter")` returns a `NamedAdapter`, the callback receives `paymentAdapter` and `label()` produces the string `adapter=paymentAdapter`. This snippet requires importing `BeanNameAware` and registering the bean through configuration. This name is suitable for diagnostics/metrics in infrastructure components, **not as a business ID or unique instance ID**: multiple prototype instances can share the same bean name, and names can change during refactoring. Lesson 182 further explains aliases and auto-generated names.

## 6. `BeanFactoryAware`: Factory-Level Lookup Access

`BeanFactoryAware.setBeanFactory(BeanFactory)` supplies the factory managing the bean. An infrastructure adapter can look up a plugin by a validated name:

```java
class PluginBridge implements BeanFactoryAware {
    private BeanFactory beanFactory;

    @Override public void setBeanFactory(BeanFactory supplied) {
        beanFactory = supplied;
    }

    Plugin getPlugin(String beanName) {
        return beanFactory.getBean(beanName, Plugin.class);
    }
}
```

This snippet requires imports and an application-defined `Plugin` type. Bean names coming from external input must be mapped or allowlisted before lookup. Factory lookup returns a singleton or creates a prototype according to the **actual scope**, not a new object by default. If you know the dependency type and only need lazy retrieval, inject `ObjectProvider<Plugin>` via constructor and call `getObject()` when needed: a narrower contract that reduces coupling to the entire factory. Do not perform bulk lookups inside an Aware setter while the bean is initializing.

## 7. `ApplicationContextAware`: When Broad Context Capabilities Are Needed

`ApplicationContextAware.setApplicationContext(ApplicationContext)` provides the context containing the bean. This API includes bean lookup, resource loading, events, messages, and parent/child context metadata:

```java
class ContextInspector implements ApplicationContextAware {
    private ApplicationContext context;

    @Override public void setApplicationContext(ApplicationContext supplied) {
        context = supplied;
    }

    boolean hasBean(String name) { return context.containsBean(name); }
}
```

This snippet requires Spring imports. Use it when the bean's core responsibility is **framework integration, diagnostics, or context-level infrastructure management**. For services that only need events, resources, or messages, inject the corresponding `ApplicationEventPublisher`, `ResourceLoader`, or `MessageSource` interface. A bean belonging to a parent context does not become a child bean when the child looks it up; avoid a static `ApplicationContextHolder` because it can retain stale references across multiple contexts or tests.

## 8. `EnvironmentAware`: Runtime Configuration Information

`EnvironmentAware.setEnvironment(Environment)` supplies the abstraction for reading property sources, active/default profiles, and property precedence:

```java
class RegionResolver implements EnvironmentAware {
    private Environment environment;

    @Override public void setEnvironment(Environment env) {
        environment = env;
    }

    String region() {
        return environment.getProperty("app.region", "default");
    }
}
```

The snippet requires importing `org.springframework.context.EnvironmentAware` and `org.springframework.core.env.Environment`. If only a few business values are needed, inject bound/validated configuration via constructor; avoid logging secrets from `Environment`. Lesson 183 explains profiles, property conversion, and configuration changes after refresh.

## 9. `ResourceLoaderAware`: Using Spring's Resource Mechanism

`ResourceLoaderAware.setResourceLoader(ResourceLoader)` helps an adapter resolve resource locations dynamically, such as `classpath:templates/info.txt` or `file:/opt/app/data.txt`.

```java
Resource resource = loader.getResource("classpath:templates/info.txt");
try (var input = resource.getInputStream()) {
    String content = new String(input.readAllBytes(),
            java.nio.charset.StandardCharsets.UTF_8);
}
```

This is a fragment inside a method that has a `ResourceLoader loader` field and declares/handles `IOException`. `Resource.getFile()` does not work for all resources inside a JAR; prefer streams. If reading only a single fixed resource, you can inject `Resource` directly. Lesson 183 covers resource patterns with `ResourcePatternResolver`, I/O error handling, and i18n.

## 10. Other Specialized Aware Interfaces

Beyond name/factory/context, Spring provides contracts **narrow enough for a single capability**:

| Interface | Callback/capability | Important limitation |
| --- | --- | --- |
| `ApplicationEventPublisherAware` | Receives `ApplicationEventPublisher` to call `publishEvent` | Does not create listeners or turn events into a durable queue; see Lesson 184 |
| `MessageSourceAware` | Receives `MessageSource` to look up keys by locale | Requires proper message codes/bundles/fallbacks; not Kafka/JMS |
| `BeanClassLoaderAware` | Class loader used by BeanFactory | Intended for plugins, class loading, or instrumentation |
| `EmbeddedValueResolverAware` | Resolver for placeholders/expressions | Part of embedded value processing infrastructure |
| `ServletContextAware` / `ServletConfigAware` | Servlet container information | Requires an appropriate web context/processor; unavailable in pure CLI contexts |
| `LoadTimeWeaverAware` | Load-time weaver if configured | Does not enable weaving merely by implementing the interface |
| `ImportAware` | Metadata from `@Import` | Part of configuration processing infrastructure |

Example of publishing events needing only the publisher:

```java
class JobEvents implements ApplicationEventPublisherAware {
    private ApplicationEventPublisher publisher;

    @Override public void setApplicationEventPublisher(
            ApplicationEventPublisher supplied) {
        publisher = supplied;
    }

    void finished(String jobId) {
        publisher.publishEvent(new JobFinished(jobId));
    }

    record JobFinished(String id) {}
}
```

This is an illustrative class requiring imports; the bean must be managed by Spring to receive the setter callback. Listeners and synchronous/async dispatch are separate mechanisms; if only a publisher is needed for business logic, constructor injection is usually cleaner. For i18n, `MessageSource.getMessage` resolves text by `Locale`; it does not send messages over the network. Do not define an interface whose name merely ends in `Aware` and expect Spring to recognize it without a processor.

## 11. Complete Java 17 + Spring 6.1 Example: BeanNameAware, BeanFactoryAware, EnvironmentAware, and ApplicationContextAware

This application needs no Spring Boot, HTTP server, or database. It demonstrates that Aware callbacks run before `InitializingBean.afterPropertiesSet()`, while comparing constructor DI with factory lookup.

### 11.1. Project Structure

~~~text
aware-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── aware/
                        └── AwareDemo.java
~~~

### 11.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>aware-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.13</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>com.example.aware.AwareDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 11.3. `src/main/java/com/example/aware/AwareDemo.java`

~~~java
package com.example.aware;

import java.util.Map;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.BeanFactoryAware;
import org.springframework.beans.factory.BeanNameAware;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.context.EnvironmentAware;
import org.springframework.context.ResourceLoaderAware;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.io.ResourceLoader;

public class AwareDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource(
                    "demo-properties", Map.of("demo.region", "VN")));

            context.register(Config.class);
            context.refresh();

            Inspector bean = context.getBean(Inspector.class);

            System.out.println("beanName=" + bean.beanName());
            System.out.println("greeting=" + bean.greeting());
            System.out.println(
                "factoryLookupSame=" + bean.factorySeesSameGreeting());
            System.out.println("sameContext=" + bean.hasContext(context));
            System.out.println("region=" + bean.region());
            System.out.println(
                "classResourceExists=" + bean.classResourceExists());
            System.out.println("initialized=" + bean.initialized());
        }
    }

    public interface Greeting {
        String sayHello();
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        Greeting greeting() {
            return () -> "Hello";
        }

        @Bean(name = "inspector")
        Inspector inspector(Greeting greeting) {
            return new Inspector(greeting);
        }
    }

    public static class Inspector
            implements BeanNameAware, BeanFactoryAware,
                       EnvironmentAware, ResourceLoaderAware,
                       ApplicationContextAware, InitializingBean {

        private final Greeting greeting;
        private String beanName;
        private BeanFactory beanFactory;
        private ApplicationContext context;
        private Environment environment;
        private ResourceLoader resourceLoader;
        private boolean initialized;

        public Inspector(Greeting greeting) {
            this.greeting = greeting;
        }

        @Override
        public void setBeanName(String name) {
            beanName = name;
        }

        @Override
        public void setBeanFactory(BeanFactory factory)
                throws BeansException {
            beanFactory = factory;
        }

        @Override
        public void setEnvironment(Environment suppliedEnvironment) {
            environment = suppliedEnvironment;
        }

        @Override
        public void setResourceLoader(ResourceLoader suppliedLoader) {
            resourceLoader = suppliedLoader;
        }

        @Override
        public void setApplicationContext(ApplicationContext suppliedContext)
                throws BeansException {
            context = suppliedContext;
        }

        @Override
        public void afterPropertiesSet() {
            if (beanName == null || beanFactory == null ||
                environment == null || resourceLoader == null ||
                context == null || greeting == null) {
                throw new IllegalStateException("Aware callbacks incomplete");
            }
            initialized = true;
        }

        public String beanName() {
            return beanName;
        }

        public String greeting() {
            return greeting.sayHello();
        }

        public boolean factorySeesSameGreeting() {
            return beanFactory.getBean(Greeting.class) == greeting;
        }

        public boolean hasContext(ApplicationContext expected) {
            return context == expected;
        }

        public String region() {
            return environment.getProperty("demo.region", "missing");
        }

        public boolean classResourceExists() {
            return resourceLoader.getResource(
                "classpath:com/example/aware/AwareDemo.class").exists();
        }

        public boolean initialized() {
            return initialized;
        }
    }
}
~~~

### 11.4. Running and Observing Output

Requires JDK 17+ and Maven 3.9.x. From the `aware-demo` directory:

~~~bash
mvn -q compile exec:java
~~~

The program's `System.out.println` lines:

~~~text
beanName=inspector
greeting=Hello
factoryLookupSame=true
sameContext=true
region=VN
classResourceExists=true
initialized=true
~~~

Maven or logging frameworks may print additional information depending on configuration; the lines above are the stdout intentionally produced by the code.

**Why is the output like this?**

1. `@Bean(name = "inspector")` supplies the bean name, so `BeanNameAware` receives `inspector`.
2. `Greeting` is injected by Spring via the **factory method parameter and constructor**, so `greeting=Hello`.
3. `Greeting` is a singleton by default. `BeanFactory.getBean(Greeting.class)` returns the same injected object, so `factoryLookupSame=true`.
4. `ApplicationContextAware` receives the exact context that created the bean, so `sameContext=true`.
5. `MapPropertySource` adds `demo.region=VN` before the context refreshes, so `EnvironmentAware` reads `region=VN`.
6. The `AwareDemo.class` class file is compiled onto the classpath by Maven, so `ResourceLoader` locates the resource and returns `classResourceExists=true`.
7. `afterPropertiesSet()` runs after the required callbacks and confirms all fields are populated, so `initialized=true`.

This example intentionally combines multiple Aware interfaces on one class for learning and verification. In real projects, choose only the interfaces genuinely needed and avoid creating a service that holds every Spring container privilege.

## 12. Constructor Injection Can Replace Many Aware Callbacks

Spring can inject certain infrastructure dependencies directly when appropriate. For example, with a constructor:

~~~java
@Component
public class TemplateService {
    private final ResourceLoader loader;
    private final ApplicationEventPublisher publisher;

    public TemplateService(
            ResourceLoader loader,
            ApplicationEventPublisher publisher) {
        this.loader = loader;
        this.publisher = publisher;
    }
}
~~~

This is an illustrative class with `Component`, `ResourceLoader`, and `ApplicationEventPublisher` imports. If the service needs those two collaborators, the constructor makes dependencies explicit and simplifies unit testing.

Comparison:

| Goal | Aware Callback | Constructor Injection |
| --- | --- | --- |
| Spring callback-style code | Implement interface yourself; Spring calls setter | Spring resolves dependencies via constructor |
| Dependencies visible immediately on object creation | Not necessarily | Yes |
| Class can be instantiated independently with `new` | Must manually invoke callbacks if relying on Aware fields | Just pass fake/mock dependencies |
| Used with framework extensions requiring Aware interfaces | Appropriate | Depends on integration API |
| Only a single specific collaborator needed | Often too much ceremony | Usually better |

As for `ApplicationContextAware`, you can also inject `ApplicationContext` directly into a Spring bean constructor. Supporting injection does not mean putting the container into every class. Narrow the dependencies before deciding.

## 13. Pitfalls When Using Aware

### 13.1. Using an Aware Field Directly Inside the Constructor

~~~java
public BadAdapter() {
    // beanFactory may still be null here.
    beanFactory.getBean("helper");
}
~~~

This illustrative constructor belongs to a class whose `beanFactory` field is set by `BeanFactoryAware`. The constructor runs before the callback, so accessing the field can throw `NullPointerException`. If a collaborator is needed immediately during object creation, inject it through the constructor.

### 13.2. Calling `getBean()` Too Early in a Callback

~~~java
@Override
public void setApplicationContext(ApplicationContext context) {
    this.context = context;
    context.getBeansOfType(Plugin.class); // May instantiate beans prematurely.
}
~~~

This snippet illustrates a class implementing `ApplicationContextAware` with a `Plugin` interface. Bulk bean lookups while the context is still refreshing can cause early instantiation, circular dependencies, or disrupted initialization ordering. If runtime lookup is needed, defer it until an appropriate operational phase or design an appropriate registry/injection.

### 13.3. Turning ApplicationContext into a Global Static

~~~java
public static ApplicationContext GLOBAL_CONTEXT;
~~~

Keeping the context in a static field creates implicit global state, which easily breaks with multiple application contexts, test context reloads, and shutdowns. Creating a "helper to fetch any bean by name" hides dependencies and keeps framework references alive too long. Use DI or a narrow abstraction.

### 13.4. Confusing Bean Name with Class Name or Instance Identifier

`BeanNameAware` receives the actual bean definition name, which may be determined by `@Bean(name=...)`, `@Component`, aliases, or another registration mechanism. Inner beans may receive generated names. Do not use a bean name as a unique ID for transactions or requests.

### 13.5. Using Aware to Access Inactive Scope Data

A request-scoped bean implementing `ApplicationContextAware` does not mean an HTTP request exists on every thread. If a singleton, scheduler, or executor invokes a request-scoped proxy outside a request, it can still encounter `ScopeNotActiveException`. Aware does not alter scope rules.

### 13.6. Assuming a Marker Interface Alone Triggers a Callback

~~~java
public interface MyRegistryAware extends Aware {
    void setRegistry(MyRegistry registry);
}
~~~

This is an illustrative custom interface. Spring does not automatically know how to call `setRegistry`. You must provide corresponding infrastructure/`BeanPostProcessor` support or use regular constructor injection.

## 14. Aware and Bean Lifecycle Order: How to Verify Accurately

You can verify callback ordering with a bean implementing `BeanNameAware`, `ApplicationContextAware`, and `InitializingBean`:

```java
class CallbackProbe implements BeanNameAware,
        ApplicationContextAware, InitializingBean {
    private final List<String> events = new ArrayList<>();

    @Override public void setBeanName(String name) {
        events.add("BeanNameAware");
    }
    @Override public void setApplicationContext(ApplicationContext context) {
        events.add("ApplicationContextAware");
    }
    @Override public void afterPropertiesSet() {
        events.add("InitializingBean");
    }
    List<String> events() { return List.copyOf(events); }
}
```

The snippet requires importing `List`, `ArrayList`, and the three Spring interfaces; register it as a bean in `AnnotationConfigApplicationContext` and compare the order of the three labels. On the default path, the result is `BeanNameAware → ApplicationContextAware → InitializingBean`. This is evidence for **one specific bean**, not a guarantee of creation order across every bean in the application. Lesson 185 includes a complete demo logging BeanFactory callbacks, all six context-aware interfaces, `BeanPostProcessor`, and destruction.

## 15. Does Aware Work with Prototype, Singleton, and Scoped Proxies?

**Singleton:** callbacks run when Spring creates/initializes the singleton instance (typically during refresh for non-lazy singletons). Subsequent `context.getBean()` calls do not re-run callbacks on that same singleton.

**Prototype:** each time the container creates a new prototype target, initialization and the applicable Aware callbacks are executed for the new instance. Two instances may receive the same bean name/context reference because they are created from the same definition in the same context.

**Request/session scope:** callbacks run on the target when the scope actually creates the target; a scoped proxy lets long-lived beans reference the per-request/session target. Successfully injecting the proxy does not mean the target already exists or the scope is active in a scheduler thread.

**Objects created with `new`:** not managed by Spring, so they do not receive Aware callbacks automatically. If a class needs to work independently of the container, passing dependencies through the constructor is a better design.

**Note on destroy callbacks:** Aware callbacks provide information at initialization time. They do not turn a prototype into a bean automatically destroyed by Spring after handoff; resource cleanup remains the caller's responsibility.

## 16. Custom Aware Interfaces and BeanPostProcessor

If you are building your own **framework extension**, you can define a custom contract:

~~~java
public interface RegistryAware {
    void setRegistry(PluginRegistry registry);
}
~~~

This is a custom example requiring a `PluginRegistry` interface/class. For Spring to invoke the callback, you can write a processor:

~~~java
import org.springframework.beans.factory.config.BeanPostProcessor;

public final class RegistryAwareProcessor implements BeanPostProcessor {
    private final PluginRegistry registry;

    public RegistryAwareProcessor(PluginRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Object postProcessBeforeInitialization(
            Object bean, String beanName) {
        if (bean instanceof RegistryAware aware) {
            aware.setRegistry(registry);
        }
        return bean;
    }
}
~~~

This is an illustrative Java class; you need to declare the `RegistryAware` interface, the `PluginRegistry` type, and register `RegistryAwareProcessor` as a bean post-processor early enough in the context. Without registering the processor, Spring will not call the custom method.

Use this pattern when a framework library must supply a registry to many components under its own callback contract. For business code, constructor injection of `PluginRegistry` is far simpler.

**BeanPostProcessor risks:** processors are typically instantiated early; complex eager dependencies inside a processor can cause certain beans to be created before all processors/proxies are ready. Avoid turning a processor into a large business service.

## 17. Real-World Usage Scenarios

Different needs lead to different interfaces. An adapter instantiated under multiple configurations that wants to tag metrics by **bean definition name** can use `BeanNameAware`; if the metric label is a long-lived business contract, inject a dedicated configuration label instead. A plugin resolver that must select beans by runtime ID can use `BeanFactoryAware` inside a **name-validated adapter**, whereas a fixed set of plugins can simply inject `Map<String, Plugin>`.

A library supporting `classpath:`/`file:` templates can use `ResourceLoaderAware`; an adapter reading profiles/property sources uses `EnvironmentAware`; a multi-context diagnostic tool may need `ApplicationContextAware`. A business service that only needs to publish domain events only needs to constructor-inject `ApplicationEventPublisher`; if the event depends on transaction commit, you must also choose an appropriate listener/transaction strategy. The decision depends on bean responsibility, not on how many Aware interfaces exist.

## 18. Decision Process Before Implementing Aware

1. **Does the bean need Spring infrastructure?** If it only needs business collaborators, use constructor DI.
2. **Do you need a narrow interface or the whole context?** If a narrow interface exists such as `ResourceLoader`, `Environment`, or `ApplicationEventPublisher`, inject it.
3. **Do you need the bean's own metadata?** `BeanNameAware` is appropriate when the bean name is genuinely useful.
4. **Do you need runtime lookup?** Try `ObjectProvider<T>`, `List<T>`, or `Map<String,T>` before injecting `BeanFactory`.
5. **Does receiving the information happen at the right time?** Aware callbacks run after the constructor and before initialization; avoid triggering other beans prematurely.
6. **Is there a supporting environment?** `ServletContextAware` only works in an appropriate web-aware context.
7. **Is there a risk of global references or hierarchy issues?** Avoid static holders; verify which context actually owns the bean.
8. **How will it be tested?** Use unit tests for pure logic and integration tests creating a Spring context to verify callbacks.

If you cannot clearly articulate **why container metadata is a genuine dependency**, that is a sign to go back to constructor injection.

## 19. Common Errors and Fixes

| Error | Cause | Fix |
| --- | --- | --- |
| `ApplicationContext` is null in constructor | Callback has not run yet | Use constructor injection for immediately needed dependencies |
| Aware callback does not run | Bean created with `new` or missing required processor | Register bean in the right context; run a real test |
| `BeanNameAware` returns an unexpected name | Bean name has alias, factory method, or generated name | Inspect actual bean definition; avoid relying on it as a business ID |
| Service has too many `getBean()` calls | Service Locator overuse | Use constructor DI, provider, or collection injection |
| Circular dependency when callback runs | Calling lookup too early during context refresh | Defer lookup or redesign the dependency graph |
| Resource cannot be read inside a JAR | Treating classpath resource as a physical file | Use `getInputStream()`, handle IOException |
| Property differs across environments | PropertySources precedence | Inspect profiles/sources, use typed configuration |
| Web bean does not receive `ServletContext` | Using a non-web context | Choose an appropriate web-aware context |
| Prototype receives the same bean name | Name belongs to the definition, not the instance | Generate a separate instance ID |
| Custom interface callback does not run | No processor registered | Register a BeanPostProcessor or use DI |
| Bean in child sees a different context than expected | Parent/child hierarchy and ownership | Confirm which context registers the bean |
| Scoped bean fails outside a request | No active scope | Call target within a real request or pass a data snapshot |
| Unit test using `new` fails | No Spring callbacks invoked | Inject dependencies directly or build an integration context |
| Bean created prematurely | Looking up the whole registry inside an Aware callback | Store the reference and use it at the right time |

## 20. Self-Check Questions

**Question 1.** An `OrderService` needs `OrderRepository`. Why is constructor injection usually better than `ApplicationContextAware`?

**Answer:** The dependency is declared explicitly; Spring resolves it when creating the bean; it is easy to unit test with a fake repository and avoids container-wide runtime lookup.

**Question 2.** A bean implementing `BeanNameAware` receives the same name across two prototype instances; did Spring mistakenly create a singleton?

**Answer:** No. The bean name identifies the bean definition; prototype scope can still create multiple distinct instances from the same definition.

**Question 3.** Can you call `beanFactory.getBean(...)` in a constructor when the `beanFactory` field is only set via `BeanFactoryAware`?

**Answer:** No: the constructor runs before the callback, so the field has not been assigned yet. If a dependency is needed in the constructor, inject it directly.

**Question 4.** When you need to publish an application event, what should you inject?

**Answer:** `ApplicationEventPublisher` is the right narrow dependency; `ApplicationEventPublisherAware` can also be used for framework callback style, whereas `ApplicationContextAware` is usually overly broad.

**Question 5.** A bean implements a custom `MyContextAware` interface without a processor; will Spring call the method automatically?

**Answer:** No. `Aware` is a marker; custom callbacks require explicit infrastructure or switching to constructor DI.

**Question 6.** Can a `@RequestScope` bean that receives `ApplicationContext` via callback run inside a `@Scheduled` task?

**Answer:** The callback does not create an HTTP request. A request-scoped target still requires an active request scope; background tasks should use snapshot data or a non-request-bound dependency.

**Question 7.** Which interface should a singleton use when it needs a new prototype for each processing run?

**Answer:** Typically `ObjectProvider<PrototypeType>`, fetching the bean at the start of each unit of work and managing cleanup if it holds resources. There is no need to receive the entire `BeanFactory` just for that.

## 21. Official Spring Documentation

- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `ApplicationContextAware`, `BeanNameAware`, and other Aware interfaces.
- [`Aware` Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/Aware.html): marker interface and callback contract.
- [`BeanNameAware` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/BeanNameAware.html): bean name and callback timing.
- [`BeanFactoryAware` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/BeanFactoryAware.html): factory ownership and dependency lookup.
- [`ApplicationContextAware` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ApplicationContextAware.html): context reference and initialization timing.
- [`ApplicationContext` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ApplicationContext.html): bean lookup, events, resources, messages, and context hierarchy.
- [Spring Framework — Annotation-based Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html): choosing constructor/field/method injection.
