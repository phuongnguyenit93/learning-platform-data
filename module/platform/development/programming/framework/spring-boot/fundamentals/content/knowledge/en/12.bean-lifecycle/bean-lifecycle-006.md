# Callback Order When Combining Multiple Initialization and Destruction Mechanisms

Spring manages a bean's lifecycle from object creation, dependency injection, and completing initialization until the ApplicationContext closes. The framework provides multiple ways for an application to participate in that lifecycle: **@PostConstruct**, **InitializingBean**, custom init methods, **@PreDestroy**, **DisposableBean**, and custom destroy methods.

A single bean can use multiple mechanisms at the same time. When that happens, callback order matters greatly: which callback runs first, which runs next, and which is invoked when the context closes? Without knowing the order, you might initialize a resource too early, close a resource before work finishes, or accidentally perform the same operation multiple times.

This lesson focuses on **callback order when combining multiple initialization and destruction mechanisms**. We also distinguish bean lifecycle callbacks from BeanPostProcessor, Aware, SmartInitializingSingleton, ApplicationContext events, and dependency ordering among multiple beans.

## 1. Two Phases to Distinguish: Initialization and Destruction

A singleton bean's lifecycle can be pictured as:

~~~text
Spring creates the object
       │
       ▼
Inject dependencies and configuration
       │
       ▼
Initialization callbacks
       │
       ▼
Bean is ready to use
       │
       ▼
Application continues running
       │
       ▼
ApplicationContext closes
       │
       ▼
Destruction callbacks
       │
       ▼
Resources are released
~~~

**Initialization callbacks** run while Spring finalizes a bean. They are typically used to validate configuration, prepare internal state, initialize local caches, or open resources owned by the bean.

**Destruction callbacks** run when the container executes the destruction process for the bean. They are typically used to stop accepting new work, flush pending data, close connections, or release resources.

These two phases are not arbitrary application calls. They are tied to the Spring-managed lifecycle. An object created with **new** outside the container will not automatically receive Spring's callbacks.

## 2. Order of Initialization Callbacks

Spring supports three common initialization mechanisms:

1. **@PostConstruct**
2. **InitializingBean.afterPropertiesSet()**
3. **Custom init method** declared through bean configuration, such as the **initMethod** attribute of **@Bean**

If one bean uses all three mechanisms and each mechanism is a separate method, the execution order is:

1. **@PostConstruct**
2. **InitializingBean.afterPropertiesSet()**
3. **Custom init-method**

For example, a bean can validate configuration in **@PostConstruct**, prepare state after properties have been assigned in **afterPropertiesSet()**, and then run a warm-up step declared as a custom init method.

### 2.1. @PostConstruct

**@PostConstruct** is a standard Jakarta annotation used to mark a method that should run after dependency injection completes and before the bean is put into normal use.

With Spring Boot 3.x, this annotation belongs to package **jakarta.annotation.PostConstruct**:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class SearchIndexClient {

    @PostConstruct
    public void validateConfiguration() {
        // Validate values that have been injected.
    }
}
~~~

The method normally takes no parameters and returns void. It is an appropriate place for validating local configuration or preparing initial state based on injected dependencies.

**@PostConstruct does not run immediately inside the constructor.** The constructor runs first, then Spring performs property population/dependency injection and bean processing before invoking this callback.

### 2.2. InitializingBean.afterPropertiesSet()

**InitializingBean** is a Spring interface. A bean implementing this interface must define the **afterPropertiesSet()** method:

~~~java
import org.springframework.beans.factory.InitializingBean;
import org.springframework.stereotype.Component;

@Component
public class SearchIndexClient implements InitializingBean {

    @Override
    public void afterPropertiesSet() {
        // Prepare state after properties have been set.
    }
}
~~~

Spring calls this method after **@PostConstruct** callbacks and before any custom init method.

The advantage is that the method is declared through an interface so Spring recognizes it directly. The limitation is that the class must depend on the Spring API, coupling the code more tightly to the framework.

In new applications, **@PostConstruct** is usually preferred if only one standard callback is needed. **InitializingBean** remains useful when working with existing code or when a class intentionally chooses to integrate Spring's lifecycle interface.

### 2.3. Custom init method

You can declare an initialization method name on **@Bean**:

~~~java
@Configuration
public class SearchConfiguration {

    @Bean(initMethod = "warmUp")
    SearchIndexClient searchIndexClient() {
        return new SearchIndexClient();
    }
}
~~~

The class has the **warmUp()** method:

~~~java
public class SearchIndexClient {

    public void warmUp() {
        // Load data or prepare required resources.
    }
}
~~~

A custom init method lets you configure lifecycle behavior without requiring the class to implement **InitializingBean** or carry **@PostConstruct**. This is especially useful when the object comes from an external library and you cannot modify its source code.

Spring also supports declaring an init method via XML bean definitions or equivalent configuration mechanisms.

## 3. Order of Destruction Callbacks

In the destruction phase, Spring supports three common mechanisms:

1. **@PreDestroy**
2. **DisposableBean.destroy()**
3. **Custom destroy method** declared through bean configuration, such as the **destroyMethod** attribute of **@Bean**

If all three mechanisms are configured with different methods, the order is:

1. **@PreDestroy**
2. **DisposableBean.destroy()**
3. **Custom destroy-method**

This order lets a bean stop operating in the first callback, perform lifecycle-interface cleanup in the next step, and complete release operations per custom configuration.

### 3.1. @PreDestroy

**@PreDestroy** is a standard Jakarta annotation marking a method that runs before the bean is destroyed:

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class MessageConsumer {

    @PreDestroy
    public void stopAcceptingMessages() {
        // Stop accepting new work and prepare to stop.
    }
}
~~~

This method is suited for instructing a component to stop accepting new work, signaling shutdown state, or releasing resources directly owned by the bean.

### 3.2. DisposableBean.destroy()

A bean can implement **DisposableBean**:

~~~java
import org.springframework.beans.factory.DisposableBean;

public class MessageConsumer implements DisposableBean {

    @Override
    public void destroy() {
        // Complete cleanup per Spring's lifecycle.
    }
}
~~~

Spring calls **destroy()** after the **@PreDestroy** callback and before any custom destroy method.

Like **InitializingBean**, this interface makes the class depend directly on Spring. If you want less framework coupling in the class, choose the annotation or a custom destroy method.

### 3.3. Custom destroy method

For beans created via **@Bean**, you can declare:

~~~java
@Configuration
public class ConsumerConfiguration {

    @Bean(destroyMethod = "release")
    MessageConsumer messageConsumer() {
        return new MessageConsumer();
    }
}
~~~

The class defines:

~~~java
public class MessageConsumer {

    public void release() {
        // Release final resources.
    }
}
~~~

Spring invokes **release()** as the custom destroy method when performing destruction for the bean. This is also useful when configuring the lifecycle for external library objects.

## 4. Example Combining All Three Init Mechanisms and All Three Destroy Mechanisms

We create a bean with three distinct initialization steps:

1. Validate configuration via **@PostConstruct**.
2. Prepare internal state via **afterPropertiesSet()**.
3. Warm up data via custom init method **warmUp()**.

When the context closes:

1. Stop accepting work via **@PreDestroy**.
2. Flush pending data via **DisposableBean.destroy()**.
3. Close final resources via custom destroy method **release()**.

Complete example:

~~~java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;

public class SearchIndexClient
        implements InitializingBean, DisposableBean {

    @PostConstruct
    public void validateConfiguration() {
        System.out.println("1. @PostConstruct: validate configuration");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("2. afterPropertiesSet: initialize state");
    }

    public void warmUp() {
        System.out.println("3. custom init: warm up index");
    }

    @PreDestroy
    public void stopAcceptingWork() {
        System.out.println("1. @PreDestroy: stop accepting work");
    }

    @Override
    public void destroy() {
        System.out.println("2. destroy: flush pending state");
    }

    public void release() {
        System.out.println("3. custom destroy: release resources");
    }
}
~~~

Bean configuration:

~~~java
package com.example.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LifecycleConfiguration {

    @Bean(
        initMethod = "warmUp",
        destroyMethod = "release"
    )
    SearchIndexClient searchIndexClient() {
        return new SearchIndexClient();
    }
}
~~~

When the context initializes the bean, the illustrative log order is:

~~~text
1. @PostConstruct: validate configuration
2. afterPropertiesSet: initialize state
3. custom init: warm up index
~~~

When the context closes gracefully:

~~~text
1. @PreDestroy: stop accepting work
2. destroy: flush pending state
3. custom destroy: release resources
~~~

The methods in the example deliberately perform distinct actions to illustrate the order. In real code, design cleanup so you do not close the same resource twice or perform an action in both **@PreDestroy** and **destroy()**.

## 5. Full Order Placing Callbacks Within the Bean Lifecycle

The three init callbacks are not Spring's first activities. Prior to them are object creation, dependency injection, and container-related callbacks.

For a regular singleton bean, you can picture the conceptual sequence:

~~~text
1. Instantiate
   Call constructor or factory method
          │
          ▼
2. Populate properties
   Inject fields/setters and configure dependencies
          │
          ▼
3. Aware callbacks
   BeanNameAware, BeanFactoryAware, ...
          │
          ▼
4. BeanPostProcessor before initialization
   Includes @PostConstruct processing
          │
          ▼
5. InitializingBean.afterPropertiesSet()
          │
          ▼
6. Custom init-method
          │
          ▼
7. BeanPostProcessor after initialization
   May create a proxy
          │
          ▼
8. Bean ready for use
~~~

### 5.1. Constructor

The constructor creates the object. Dependencies declared through the constructor are resolved by Spring before calling the constructor. Dependencies through fields/setters are typically injected in the property population step afterward.

Do not use a setter-injected field inside a constructor because the setter has not yet been called:

~~~java
@Component
public class ReportService {

    private ReportExporter exporter;

    public ReportService() {
        // exporter has not been assigned by setter injection here.
    }

    @Autowired
    public void setExporter(ReportExporter exporter) {
        this.exporter = exporter;
    }
}
~~~

If a dependency is required for the object to have a valid state immediately upon creation, constructor injection expresses that requirement more clearly.

### 5.2. Property population and dependency injection

Spring assigns dependencies per field injection, setter injection, or other configured injection points. After this phase, init callbacks can use injected dependencies.

For example, **@PostConstruct** can read **Environment**, a service, or an assigned property. However, do not treat **@PostConstruct** as a replacement for constructor validation of every invariant; if a class cannot validly exist without a dependency, declare the required dependency in the constructor.

### 5.3. Aware callbacks

**Aware** interfaces let a bean receive certain container-provided objects/infrastructure, for example:

- **BeanNameAware** receives the bean name.
- **BeanClassLoaderAware** receives the class loader.
- **BeanFactoryAware** receives the BeanFactory.
- **EnvironmentAware** receives the Environment.
- **ApplicationContextAware** receives the ApplicationContext.

Some callbacks such as **ApplicationContextAware** are processed by an internal Spring BeanPostProcessor prior to initialization callbacks. Thus, they belong to the bean preparation phase, not custom init methods.

In ordinary applications, constructor injection is usually easier to test and more transparent than implementing multiple Aware interfaces. Use Aware when direct integration with the container is genuinely needed.

### 5.4. BeanPostProcessor before and after initialization

**BeanPostProcessor** is an extension point allowing Spring or the application to intervene on a bean before/after init callbacks.

- **postProcessBeforeInitialization(...)** runs before initialization callbacks such as **@PostConstruct**.
- **postProcessAfterInitialization(...)** runs after **afterPropertiesSet()** and custom init methods.

Some Spring features use post-processors to process annotations or create proxies. For example, AOP mechanisms can wrap a bean in a proxy after initialization. Therefore, the object injected elsewhere may be a proxy representing the bean.

This explains why you should not manually invoke **@PostConstruct** yourself or assume a proxy has already been created before initialization finishes.

## 6. Full Destruction Order

When Spring performs destruction on a singleton bean, it can be pictured as:

~~~text
ApplicationContext begins closing
          │
          ▼
DestructionAwareBeanPostProcessor
          │
          ▼
@PreDestroy
          │
          ▼
DisposableBean.destroy()
          │
          ▼
Custom destroy-method
          │
          ▼
Bean completed destruction
~~~

**@PreDestroy** is processed via the destruction-aware post-processing mechanism. Afterward, Spring calls **DisposableBean.destroy()**, and then calls the custom destroy method if declared.

A bean can use these callbacks to break cleanup into ordered steps, but avoid depending on callback ordering of another bean unless an explicit relationship is declared.

### When is destruction triggered?

For managed singleton beans, destruction typically occurs when:

- The application calls **ApplicationContext.close()**.
- The context is closed via **try-with-resources** or an appropriate shutdown workflow.
- The JVM exits and the application/container shutdown hook executes context closure (if registered and given enough time to run).

In Spring Boot, applications usually close the context on normal process shutdown. If the process is force-killed, the machine loses power, or the container runtime stops too abruptly, callbacks may not get a chance to finish. Therefore, **@PreDestroy does not replace durable state persistence or crash recovery mechanisms**.

## 7. When the Same Method Is Declared for Multiple Mechanisms

Spring has rules to avoid duplicate invocation when **the same method name** is declared for multiple lifecycle mechanisms.

For example, if a method is used as a custom init method and is also the method implementing **afterPropertiesSet()** under the corresponding configuration, Spring avoids executing the same method twice when the duplicate name is detected.

However, the easiest-to-understand and least error-prone approach is **one dedicated method per lifecycle responsibility**:

~~~java
@PostConstruct
void validate() { }

@Override
public void afterPropertiesSet() { }

void warmUp() { }
~~~

When each mechanism uses a distinct method name, the order is unambiguous:

~~~text
validate()
   → afterPropertiesSet()
       → warmUp()
~~~

The same applies to destruction:

~~~java
@PreDestroy
void stop() { }

@Override
public void destroy() { }

void release() { }
~~~

If configuring a custom init/destroy method that matches another lifecycle method, check the rules of your Spring version and avoid relying on side effects of repeated calls. In particular, cleanup such as closing connections or stopping executors should be designed idempotently whenever possible.

## 8. Using @Bean(initMethod, destroyMethod) for External Objects

A major benefit of custom lifecycle methods is being able to manage the lifecycle of objects whose source code you do not control.

Suppose an external library provides:

~~~java
public class ExternalClient {

    public void connect() {
        // Open connection.
    }

    public void close() {
        // Close connection.
    }
}
~~~

We can configure:

~~~java
@Configuration
public class ExternalClientConfiguration {

    @Bean(
        initMethod = "connect",
        destroyMethod = "close"
    )
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
~~~

The container creates **ExternalClient**, calls **connect()** during the init phase, and calls **close()** during the destroy phase when the bean is managed and the context closes.

You do not need to modify the library class to add **@PostConstruct**, **@PreDestroy**, **InitializingBean**, or **DisposableBean**. The bean configuration owns the responsibility of wiring the library's lifecycle into Spring.

### Inferred destroy method

With **@Bean**, Spring can infer certain default destroy methods such as **close** or **shutdown** if the bean has a corresponding method and configuration has not disabled inference. Therefore, before manually declaring a destroy method, understand your framework/version's inference behavior to avoid closing resources redundantly.

If you want to disable destroy method inference, Spring supports configuring **destroyMethod = ""** where appropriate. Use this option when you actively manage cleanup by another mechanism and clearly understand the bean's lifecycle.

## 9. Order Among Multiple Beans: Dependencies Matter More Than Declaration Order

Callback order **within a single bean** is deterministic. However, init/destroy order **across different beans** is a separate matter.

Suppose:

~~~text
OrderService
    └── needs OrderRepository
             └── needs DataSource
~~~

Spring must create dependencies before creating a bean that depends on them. According to this dependency relationship, **DataSource** needs to be ready before **OrderRepository**, and only then is **OrderService** created and fully injected.

During destruction, the dependency relationship is reversed: the dependent bean is typically destroyed before the dependency it uses. For instance, services/repositories stop using the datasource before the datasource is closed.

~~~text
Initialization:
DataSource → OrderRepository → OrderService

Destruction:
OrderService → OrderRepository → DataSource
~~~

This is dependency-graph order, not a simple rule like "whichever bean is written earlier in the config file initializes first."

### @DependsOn for relationships not expressed via injection

If bean B needs an initialization side effect of bean A without having a direct dependency in its constructor/properties, you can declare **@DependsOn**:

~~~java
@Component
public class DatabaseWarmup {
    // Prepare required schema/cache.
}

@Component
@DependsOn("databaseWarmup")
public class SearchService {
    // Needs DatabaseWarmup to finish before initializing.
}
~~~

**@DependsOn** requires the specified bean to initialize before the annotated bean. When a singleton context closes, destruction order between beans with a depends-on relationship is reversed so the dependent bean is destroyed before the bean it depends on.

Only use **@DependsOn** when there is a real initialization relationship that is not expressed via dependency injection. If SearchService needs DatabaseWarmup as a regularly used dependency, constructor injection describes the relationship more clearly.

### @Order is not a tool for sorting singleton lifecycle order

**@Order** typically affects the order of beans in collection injection or certain order-aware processing mechanisms. It is not a general rule to force all singleton beans to initialize/destroy in an arbitrary numeric order.

If a dependency relationship is needed between two beans, express the dependency via constructors or use **@DependsOn** when appropriate. Do not use **@Order** in place of a dependency graph.

## 10. SmartInitializingSingleton and When All Singletons Have Been Created

Beyond callbacks on individual beans, Spring has **SmartInitializingSingleton**. This interface provides the method:

~~~java
void afterSingletonsInstantiated();
~~~

The method is called once normal eager singleton initialization in the BeanFactory has completed. This is useful if a bean needs to observe or aggregate information from other singletons after they have been created.

~~~java
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.stereotype.Component;

@Component
public class PluginRegistry implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        // Can aggregate registered singleton plugins.
    }
}
~~~

This is **not a callback replacing @PostConstruct**:

- **@PostConstruct** is tied to the initialization of one specific bean.
- **afterPropertiesSet()** and custom init methods are also tied to a specific bean.
- **afterSingletonsInstantiated()** runs after regular eager singletons have been created.

Lazy beans that have not yet been initialized may not be present at this time. Therefore, do not treat this callback as a guarantee that every possible bean in the context, including lazy beans, has been created.

## 11. ApplicationContext Events and SmartLifecycle Are Not Single-Bean Callbacks

Spring has multiple lifecycle milestones at the ApplicationContext level. They are often confused with init/destroy callbacks of individual beans.

### ContextRefreshedEvent

When the ApplicationContext finishes refreshing, Spring publishes **ContextRefreshedEvent**. A listener can receive the event:

~~~java
@Component
public class ContextReadyListener {

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        // Handle once the context has refreshed.
    }
}
~~~

This is a context-level event. It can be published again if the context is refreshed under a supported mechanism; therefore, listeners should consider avoiding unintended repeated side effects.

### ApplicationRunner and CommandLineRunner

Spring Boot invokes **ApplicationRunner** and **CommandLineRunner** after the ApplicationContext has refreshed during the application startup sequence:

~~~java
@Component
public class StartupReport implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // Perform work after the context has refreshed.
    }
}
~~~

Runners are suitable for work that needs to execute after context initialization. However, they are not per-bean init callbacks. If a runner executes a long task, consider its impact on startup time and how background work is coordinated.

### SmartLifecycle

**SmartLifecycle** is a lifecycle management mechanism for components that need phased start/stop. It fits components like listener containers or background services that need to start and stop in coordination with the ApplicationContext.

SmartLifecycle has its own rules for phases and auto-startup; it does not replace a bean's **@PostConstruct → afterPropertiesSet() → custom init method** sequence.

## 12. Are Destroy Callbacks Called for Prototype Beans?

This is a crucial limitation of lifecycle management:

- For **singleton beans**, Spring fully manages destruction when the context closes.
- For **prototype beans**, Spring creates and configures the instance, but after handing the instance off to the client, the container does not manage its full destruction lifecycle like singletons. Destruction callbacks such as **@PreDestroy** are not automatically invoked for prototype beans in the usual way.

Example:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class TemporaryReport {

    @PreDestroy
    public void cleanup() {
        // Do not assume Spring automatically calls this for each prototype instance.
    }
}
~~~

If a prototype object owns file handles, connections, or resources needing closure, whichever side retrieves the object must take responsibility for cleanup, or use a factory/try-with-resources/explicit close API.

**Scope changes instance lifecycle**, so when designing destroy callbacks, you must know which scope the bean uses.

## 13. What Happens When a Callback Fails?

If an initialization callback throws an exception, bean creation fails. The ApplicationContext may fail to start up if that bean is a required dependency or an eagerly initialized singleton.

Example:

~~~java
@PostConstruct
public void validateConfiguration() {
    if (endpoint == null || endpoint.isBlank()) {
        throw new IllegalStateException("Endpoint is not configured");
    }
}
~~~

Failing fast during initialization can be useful when missing configuration prevents a component from operating properly. However, init callbacks should not run a long business sequence with hard-to-roll-back side effects.

During destruction, if a callback throws an exception, Spring still has mechanisms to handle destroying other beans during context closure and logs the error. Nonetheless, do not rely on subsequent callbacks to fix every consequence of an earlier callback. Cleanup should be designed independently, with state checks, and as idempotent as possible.

### Idempotent cleanup

An idempotent cleanup operation can be called multiple times without corrupting state:

~~~java
public class ResourceHolder {

    private boolean closed;

    public synchronized void close() {
        if (closed) {
            return;
        }

        // Close resource if still open.
        closed = true;
    }
}
~~~

The example above only illustrates the idea; real resources require proper exception handling and accurate closed-state management. Idempotency is useful when a library has both lifecycle callbacks and a manual close API, or when shutdown can be triggered from multiple paths.

## 14. Avoid Putting Heavy Business Work in Init/Destroy Callbacks

Lifecycle callbacks aim to manage a bean's technical resources and state. By default, do not use them to:

- Import millions of records right as the context starts up.
- Send bulk emails every time a bean is created.
- Capture payments or mutate order states when the context closes.
- Run a long business workflow without progress tracking.
- Make external calls without timeouts/retries while blocking startup or shutdown.

If work needs to run after startup, define it as a runner, job, message consumer, or an explicitly coordinated use case. If handling shutdown, distinguish **stopping acceptance of new work**, **waiting for in-flight work to finish**, **flushing data**, and **closing resources**.

For example, a worker can use **SmartLifecycle** to manage start/stop and a dedicated service to perform business logic. Lifecycle callbacks only control the technical lifecycle; message-processing logic lives in the application service.

## 15. Summary Table of Mechanisms and Order

| Phase | Mechanism | Timing |
|---|---|---|
| Before init callbacks | Constructor | Create object |
| Before init callbacks | Populate properties / dependency injection | Assign dependencies |
| Before init callbacks | Aware callbacks | Provide certain information from the container |
| Init | **@PostConstruct** | First init callback among the three common mechanisms |
| Init | **InitializingBean.afterPropertiesSet()** | After @PostConstruct |
| Init | **Custom init method** | After afterPropertiesSet() |
| After init | BeanPostProcessor after initialization | May wrap bean / create proxy |
| After eager singleton creation | **SmartInitializingSingleton** | After regular eager singletons have been initialized |
| Context refreshed | **ContextRefreshedEvent**, Boot runners per startup flow | Context/application-level milestone |
| Destroy | **@PreDestroy** | First destroy callback among the three common mechanisms |
| Destroy | **DisposableBean.destroy()** | After @PreDestroy |
| Destroy | **Custom destroy method** | After destroy() |

Two sequences to remember:

~~~text
INITIALIZATION
@PostConstruct
      ↓
afterPropertiesSet()
      ↓
custom init-method

DESTRUCTION
@PreDestroy
      ↓
DisposableBean.destroy()
      ↓
custom destroy-method
~~~

The order above describes **callbacks of a single bean**. Order across multiple beans also depends on the dependency graph, @DependsOn, scope, and context-closing workflow.

## 16. Which Mechanism to Choose in a Spring Boot Project?

| Need | Usually preferred choice | Reason |
|---|---|---|
| Validate configuration after injection | **@PostConstruct** | Standard annotation, easy to read |
| Integrate with an existing lifecycle interface | **InitializingBean** | Useful when the class intentionally depends on Spring |
| Configure init for an external library object | **@Bean(initMethod = "...")** | No need to modify the library class |
| Clean up resources before bean destruction | **@PreDestroy** | Standard annotation, no need to implement a Spring interface |
| Use Spring's destroy lifecycle interface | **DisposableBean** | Direct integration with the container |
| Configure destroy for an external object | **@Bean(destroyMethod = "...")** | Declare cleanup where the bean is created |
| Know when eager singletons have been created | **SmartInitializingSingleton** | Callback at the milestone after singleton instantiation |
| Start/stop components by phase | **SmartLifecycle** | Coordinated operational lifecycle management |
| Run work after context refresh | **ApplicationRunner / CommandLineRunner** | Entry point at the Spring Boot application level |

There is no need to use every mechanism in every bean. Pick one simple mechanism fitting the responsibility; only combine multiple mechanisms when steps have distinct meaning and the order is clearly understood.

## 17. Practice Observing Callback Order

Create a small Spring Boot project, add a **LifecycleProbe** class implementing **InitializingBean** and **DisposableBean**, along with **@PostConstruct**, **@PreDestroy**, and two custom methods declared via **@Bean**.

Example configuration:

~~~java
@Configuration
public class ProbeConfiguration {

    @Bean(initMethod = "customStart", destroyMethod = "customStop")
    LifecycleProbe lifecycleProbe() {
        return new LifecycleProbe();
    }
}
~~~

In each callback, print a different log line. Start the application and observe the order of the three init lines. Then close the ApplicationContext gracefully and observe the three destroy lines.

Next, try:

1. Removing **InitializingBean** and observing the remaining order.
2. Removing **@PostConstruct** and observing that custom init is still called.
3. Removing the custom destroy method and observing the remaining two destroy callbacks.
4. Switching the bean to **prototype** and observing that Spring does not automatically call destruction callbacks for individual instances.
5. Creating bean B depending on bean A and observing A created before B, and B destroyed before A.
6. Adding **@DependsOn** when there is no direct dependency injection and observing the impact on order.

When testing, close the context explicitly, for instance:

~~~java
try (var context =
        new AnnotationConfigApplicationContext(ProbeConfiguration.class)) {
    // Bean is created and used here.
}
// Context closes when exiting try; destruction callbacks are invoked.
~~~

This snippet uses **AnnotationConfigApplicationContext** to demonstrate the Spring Framework mechanism. In Spring Boot, similar behavior can be observed when closing the context or terminating the application normally.

## 18. Common Mistakes When Combining Callbacks

**Assuming @PostConstruct runs before dependency injection.** In fact, it runs after Spring-managed dependency injection steps. Do not use setter-injected fields in the constructor.

**Assuming custom init method runs before afterPropertiesSet().** The standard order is @PostConstruct, afterPropertiesSet(), then custom init method.

**Assuming @PreDestroy runs after destroy().** The standard order is @PreDestroy, DisposableBean.destroy(), then custom destroy method.

**Performing the same cleanup in multiple callbacks.** This can close resources twice. Split responsibilities clearly or make cleanup idempotent.

**Relying on @Bean declaration order in a file to infer lifecycle order.** Order across beans primarily depends on the dependency graph and specific lifecycle rules; use dependency injection or @DependsOn when expressing relationships.

**Using @Order to control singleton init/destroy order.** @Order is not a general-purpose tool for this.

**Assuming every bean is destroyed when the context closes.** Prototype beans do not have full container-managed destruction like singletons.

**Assuming @PreDestroy always runs when the process exits.** Forced shutdowns or machine failures can prevent callbacks from having a chance to run.

**Putting long business tasks inside @PostConstruct.** Startup can slow down or fail; extract work into a runner/job/worker with proper state and error handling.

**Confusing bean callbacks with context events.** SmartInitializingSingleton, ContextRefreshedEvent, and ApplicationRunner operate at broader milestones than a single bean's init lifecycle.

## Conclusion

When combining multiple Spring lifecycle mechanisms, the callback order within a bean is:

- **Initialization:** **@PostConstruct → InitializingBean.afterPropertiesSet() → custom init method**.
- **Destruction:** **@PreDestroy → DisposableBean.destroy() → custom destroy method**.

Before init callbacks come the constructor, dependency injection, Aware callbacks, and before-initialization BeanPostProcessors; after init come after-initialization BeanPostProcessors. At the context level, **SmartInitializingSingleton**, refresh events, and Spring Boot runners are separate milestones and do not replace per-bean callbacks.

Assign each callback a distinct responsibility, avoid performing the same operation multiple times, and remember that ordering across beans is governed by dependency relationships and context management mechanisms. Mastering this sequence helps you initialize resources at the right time, stop components cleanly, and avoid errors when a Spring Boot application shuts down.
