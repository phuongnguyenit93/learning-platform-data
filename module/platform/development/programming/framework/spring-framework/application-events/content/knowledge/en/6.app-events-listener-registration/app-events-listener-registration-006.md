# ApplicationListenerDetector

`ApplicationListenerDetector` is an internal infrastructure component of Spring Framework. It is a `BeanPostProcessor` installed directly into the BeanFactory by `AbstractApplicationContext` to detect bean instances implementing `ApplicationListener` and register those instances with the ApplicationContext.

It is not an application listener, does not receive business events, and is not the processor that handles the `@EventListener` annotation. Its job lies in the bean creation and destruction lifecycle: observing beans after initialization, identifying eligible listener instances, adding instances to the event multicaster, and removing instances when beans are destroyed.

This article follows Spring Framework source tag **6.2.0**. `ApplicationListenerDetector` is an internal implementation, not a public extension API. You can read its source to understand startup and debugging, but you should not import, instantiate, or depend on this class in application code.

## 1. Three concepts to keep separate

| Component | Nature | Role |
|---|---|---|
| `ApplicationListenerDetector` | Internal `BeanPostProcessor` | Detects bean instances implementing `ApplicationListener` during the BeanFactory lifecycle |
| ApplicationListener bean | Application bean implementing `ApplicationListener<E>` | Handles events via `onApplicationEvent(E)` |
| `EventListenerMethodProcessor` | Internal `BeanFactoryPostProcessor` and `SmartInitializingSingleton` | Finds methods annotated with `@EventListener`, creates adapters, and registers those adapters |

Example of an application bean:

~~~java
@Component
public class OrderCreatedListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        System.out.println("New order: " + event.getOrderId());
    }
}
~~~

`OrderCreatedListener` is the actual listener. It receives events and runs business logic. `ApplicationListenerDetector` only observes Spring creating this bean and then registers it. The detector does not call `onApplicationEvent` directly; the event multicaster is the component that distributes events to matching listeners.

## 2. Where the detector sits in Spring 6.2.0

In the `AbstractApplicationContext.prepareBeanFactory(...)` source, Spring installs the detector directly with the call:

~~~java
beanFactory.addBeanPostProcessor(new ApplicationListenerDetector(this));
~~~

The call resides in `prepareBeanFactory`, after the context registers resolvable dependencies such as `ApplicationEventPublisher` and `ApplicationContext`. It runs before `invokeBeanFactoryPostProcessors(...)`, before `registerBeanPostProcessors(...)`, and before regular application singletons are instantiated.

This means:

- The detector does not need to be declared with `@Component`, `@Bean`, or XML.
- The detector is not a user-configured listener bean.
- It is already in the post-processor list before Spring begins instantiating application beans.
- It can observe beans created in subsequent refresh phases, including bean post-processors and listener beans.

The name "early post-processor" in the source refers to when it is attached to the BeanFactory. It does not mean the detector registers a listener before the listener instance finishes initializing.

## 3. Which interfaces does the detector implement?

In Spring 6.2.0, the detector combines two roles:

- `MergedBeanDefinitionPostProcessor`: receives merged bean definition information to know whether the bean has singleton scope.
- `DestructionAwareBeanPostProcessor`: observes beans after initialization and performs cleanup before a bean is destroyed.

The two roles solve different problems. The merged definition tells the bean's scope; the post-initialization callback provides the actual instance to check `instanceof ApplicationListener`.

### 3.1. Recording the bean's scope

In the `postProcessMergedBeanDefinition(...)` callback, the detector stores the singleton status by bean name. The idea of the processing block is:

~~~java
@Override
public void postProcessMergedBeanDefinition(
        RootBeanDefinition beanDefinition,
        Class<?> beanType,
        String beanName) {

    singletonNames.put(beanName, beanDefinition.isSingleton());
}
~~~

This map does not hold listener objects. It only stores a Boolean for the bean name so that the post-initialization callback knows whether the newly created instance is a singleton according to the merged definition.

Checking scope is important because the way the event multicaster holds a listener instance differs from how it holds a listener bean name. Singleton instances can be registered directly. Top-level non-singleton beans are registered by bean name so the BeanFactory provides instances according to scope when needed.

### 3.2. Inspecting the instance after initialization

In `postProcessAfterInitialization(bean, beanName)`, the detector only cares about objects implementing `ApplicationListener`.

High-level processing flow in Spring 6.2.0:

~~~java
if (bean instanceof ApplicationListener<?> listener) {
    Boolean singleton = singletonNames.get(beanName);

    if (Boolean.TRUE.equals(singleton)) {
        applicationContext.addApplicationListener(listener);
    }
    else if (Boolean.FALSE.equals(singleton)) {
        if (!applicationContext.containsBean(beanName)) {
            // Warn on non-singleton inner listener bean.
        }
        singletonNames.remove(beanName);
    }
}

return bean;
~~~

This is a simplified logic outline for explanation, not a complete copy of the source. The real code includes a logger, log-level checks, and generic type handling.

If the bean is a singleton, the detector calls `applicationContext.addApplicationListener(listener)`. In `AbstractApplicationContext`, this call adds the instance to the context's listener set and, if the event multicaster has already been initialized, adds the instance to the current multicaster.

If the bean is non-singleton, the detector does not register that instance as a fixed listener instance. For top-level beans, registration by bean name is already handled by `registerListeners()`. For non-singleton inner beans, Spring has no stable top-level bean name for the event multicaster to look up; the detector logs a warning that non-singleton inner listeners cannot be reliably auto-detected.

### 3.3. Why does the callback run after initialization?

`postProcessAfterInitialization` is called after initialization callbacks such as `InitializingBean.afterPropertiesSet()` or custom init methods. Therefore, the detector registers the listener after bean initialization has run through those callbacks.

This differs from `postProcessMergedBeanDefinition`, which takes place during merged definition processing to record scope information.

The detector does not replace dependency injection, does not create listener objects, and does not transform an object into a listener. It only inspects instances already created by the BeanFactory.

## 4. Registration timing: two complementary registration paths

A common point of confusion is that Spring has both `registerListeners()` and `ApplicationListenerDetector`. These two mechanisms are not two names for the same step.

### Path 1 — Registering top-level listener beans by bean name

In `AbstractApplicationContext.registerListeners()`, Spring performs two groups of tasks:

1. Adds statically pre-registered listener instances to the event multicaster.
2. Finds bean names of type `ApplicationListener` using:

~~~java
getBeanNamesForType(ApplicationListener.class, true, false)
~~~

Then, Spring calls `addApplicationListenerBean(listenerBeanName)` for each bean name.

The two Boolean parameters have important meanings:

- `includeNonSingletons = true`: allows finding non-singleton top-level listener beans as well.
- `allowEagerInit = false`: avoids eagerly initializing FactoryBeans solely to complete type probing.

At this step Spring registers bean names without needing to instantiate all listener beans. The event multicaster holds bean names and uses the BeanFactory to obtain listener instances when events need to be distributed.

### Path 2 — Registering actual singleton instances via the detector

When a listener bean is instantiated, the detector inspects the instance in `postProcessAfterInitialization`. If the bean is a singleton, it calls `addApplicationListener(instance)`.

This path is especially important for singleton inner beans. An inner bean has no top-level bean name for `getBeanNamesForType(ApplicationListener.class, ...)` to find, yet the instance still goes through the BeanFactory lifecycle and the detector can see it.

For top-level singleton listener beans, both paths can appear: `registerListeners()` added the bean name, and then the detector adds the actual instance after initialization. The event multicaster manages both listener instances and listener bean names, and avoids invoking the same singleton listener object twice when merging candidates.

## 5. Detection scope: what does the detector see?

Detection scope must be understood through two questions: does the object go through the BeanFactory lifecycle, and does the bean definition have singleton scope?

| Case | Registration path in Spring 6.2.0 | Result |
|---|---|---|
| Top-level singleton bean implements `ApplicationListener` | `registerListeners()` adds bean name; detector adds instance after initialization | Registered |
| Top-level prototype listener bean | `registerListeners()` adds bean name; detector does not retain a fixed prototype instance | Supported via bean name and scope |
| Singleton inner listener bean | No top-level bean name; detector sees the instance after initialization | Detector registers actual instance |
| Non-singleton inner listener bean | No stable top-level bean name; detector cannot register a long-lived instance | Warning, not reliably auto-detected |
| Object created with `new` inside a bean, not a separate bean | Does not go through BeanFactory post-processing as an independent bean | Detector does not see it |
| Listener registered directly with `context.addApplicationListener(...)` | Context registers the instance via public API | No detector discovery needed |

### 5.1. Top-level prototype does not mean ignored

Do not read the non-singleton branch of the detector and conclude that Spring does not support prototype listener beans.

Top-level listener beans are found by `registerListeners()` with `includeNonSingletons = true` and registered by bean name. The multicaster can retrieve the listener via the BeanFactory by bean name; instance lifecycle still follows the declared scope.

The detector simply does not add prototype instances to the fixed listener instance set. That is the difference between registration by bean name and registration by object instance.

### 5.2. Why do inner listener beans need the detector?

`getBeanNamesForType(...)` finds bean names at the BeanFactory level; it does not traverse every nested object inside the dependency graph. An inner bean declared directly inside a property or constructor argument has no standalone bean name to register with the multicaster.

XML example of an inner bean:

~~~xml
<bean id="orderCoordinator" class="demo.OrderCoordinator">
    <property name="listener">
        <bean class="demo.OrderCreatedListener"/>
    </property>
</bean>
~~~

The inner listener is created while creating its enclosing bean. It still goes through bean post-processing, so the detector can recognize the instance implementing `ApplicationListener` and register it if that instance is a singleton according to the merged definition.

If you create an object with `new OrderCreatedListener()` inside a Java method body and pass it into another bean, that object does not automatically become a separate bean. The detector does not scan arbitrary fields or object graphs to find listeners.

## 6. Refresh order in Spring 6.2.0

The refresh order explains why Spring needs both registration by bean name and post-processing by instance.

<text color="secondary" size="sm">Abbreviated sequence based on AbstractApplicationContext.refresh()</text>

1. **`prepareRefresh()`** — Marks the context as active, stores listeners registered prior to refresh, and creates a buffer for early application events.
2. **`obtainFreshBeanFactory()`** — Creates or obtains the context's BeanFactory.
3. **`prepareBeanFactory()`** — Configures the BeanFactory, registers resolvable dependencies, and attaches `ApplicationListenerDetector` as an early BeanPostProcessor.
4. **`postProcessBeanFactory()`** — Allows context subclasses to customize the BeanFactory.
5. **`invokeBeanFactoryPostProcessors()`** — Runs BeanFactoryPostProcessors, including `EventListenerMethodProcessor.postProcessBeanFactory(...)` if the annotation infrastructure registered that processor.
6. **`registerBeanPostProcessors()`** — Registers BeanPostProcessors declared as beans.
7. **`initMessageSource()`** — Initializes the MessageSource.
8. **`initApplicationEventMulticaster()`** — Initializes the event multicaster, defaulting to `SimpleApplicationEventMulticaster` if there is no custom bean.
9. **`onRefresh()`** — Executes subclass-specific refresh logic.
10. **`registerListeners()`** — Adds statically registered listener instances, adds top-level listener bean names, and then replays buffered early events.
11. **`finishBeanFactoryInitialization()`** — Instantiates remaining non-lazy singletons. The detector runs after each bean's initialization and registers singleton `ApplicationListener` instances.
12. **`finishRefresh()`** — Initializes the LifecycleProcessor, calls `onRefresh()` on the lifecycle processor, and emits `ContextRefreshedEvent`.

Point to remember: the detector is installed at step 3, but listener instances are typically only registered at step 11 when beans complete initialization. Meanwhile, top-level listener bean names are already known to the multicaster from step 10.

Early events published before the multicaster is ready are buffered. After `registerListeners()` sets up listener instances and listener bean names, Spring replays those events. Thus, early events are not lost solely because the multicaster was not yet initialized at publish time.

### 6.1. Why does ContextRefreshedEvent usually arrive after singleton listeners are ready?

`finishRefresh()` comes after `finishBeanFactoryInitialization()`. Regular non-lazy singletons have already been created and the detector has processed listener instances before the context emits `ContextRefreshedEvent`.

This does not mean every lazy listener has been instantiated. Top-level lazy listener beans may already be registered by bean name; instantiation can occur when the BeanFactory needs to supply the listener for a matching event.

## 7. Do not confuse with EventListenerMethodProcessor

`EventListenerMethodProcessor` solves a different problem: detecting methods annotated with `@EventListener` and turning each method into a listener adapter.

In Spring Framework 6.2.0, this class implements:

~~~java
public class EventListenerMethodProcessor
        implements SmartInitializingSingleton,
                   ApplicationContextAware,
                   BeanFactoryPostProcessor {
}
~~~

It does not implement `BeanPostProcessor`.

Main workflow:

1. In `postProcessBeanFactory(...)`, the processor retains the BeanFactory and finds matching `EventListenerFactory` beans.
2. In the `afterSingletonsInstantiated()` callback, it scans beans and methods annotated with `@EventListener`.
3. For each matching method, the factory creates an `ApplicationListener` adapter, typically `ApplicationListenerMethodAdapter`.
4. The processor calls `applicationContext.addApplicationListener(adapter)` to register the adapter with the context.

Spring 6.2.0 Javadoc explicitly describes this class as registering `@EventListener` methods as individual `ApplicationListener` instances. The `afterSingletonsInstantiated()` callback runs at the end of the singleton pre-instantiation phase, once regular singleton beans have been created.

### 7.1. Comparison by detection mechanism

| Criterion | ApplicationListenerDetector | EventListenerMethodProcessor |
|---|---|---|
| Processor type | BeanPostProcessor + DestructionAwareBeanPostProcessor + MergedBeanDefinitionPostProcessor | BeanFactoryPostProcessor + SmartInitializingSingleton |
| Input | Bean instance | Bean classes and method metadata |
| Detection condition | `bean instanceof ApplicationListener` | Method with `@EventListener` |
| Primary timing | After each bean's initialization | Scans and registers adapters after singleton pre-instantiation |
| Outcome | Registers listener bean instance | Creates and registers a listener adapter for the method |
| Listener bean destruction handling | Has callback to remove listener | Adapter is registered by the processor as a listener instance; not a listener bean detected by the detector |

Example of a bean that does not implement `ApplicationListener` but has an annotated method:

~~~java
@Component
public class OrderAuditHandler {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Audit: " + event.getOrderId());
    }
}
~~~

`ApplicationListenerDetector` does not find this method because the bean is not an `ApplicationListener`. `EventListenerMethodProcessor` is the component that reads the annotation, creates the adapter, and registers the adapter.

Conversely, a bean that only implements `ApplicationListener` does not need `@EventListener`; it is detected by type and registered via the listener bean name/instance paths.

Do not merge the two mechanisms into a single "annotation BeanPostProcessor". They have different interfaces, lifecycles, and inputs. If the same bean both implements `ApplicationListener` and has an `@EventListener` method for the same event, the two mechanisms can register two separate listener routes and lead to duplicate handling; combine them only when intentional.

## 8. Spring Framework 6.2: version-specific details to remember

### 8.1. The detector remains an internal implementation

In source tag `v6.2.0`, `AbstractApplicationContext.prepareBeanFactory()` directly instantiates `ApplicationListenerDetector`. This is an implementation detail of ApplicationContext, not an application API guaranteed compatible across all versions.

When upgrading Spring, check the corresponding source tag if debugging internals. Do not write application code that calls the detector constructor or depends on the `singletonNames` map.

### 8.2. ApplicationListener has supportsAsyncExecution()

`ApplicationListener.supportsAsyncExecution()` was added in Spring 6.1 and is present in Spring 6.2. Its default value is `true`; it tells the multicaster whether the listener can be executed asynchronously if the multicaster is configured with an executor.

The detector does not decide whether a listener runs synchronously or asynchronously. It only registers the listener instance. Dispatching depends on `ApplicationEventMulticaster`, executor configuration, and the listener's async capability.

With the default `SimpleApplicationEventMulticaster` without an executor configured, listeners are invoked on the event-publishing thread. If an executor is configured, a listener that does not support async execution must still run on the thread calling the multicaster.

### 8.3. @EventListener.defaultExecution() is an annotation attribute

Spring 6.2 adds the `defaultExecution` attribute to `@EventListener`. The Javadoc states this attribute exists since 6.2 and serves composed annotations such as `@TransactionalEventListener`.

This is behavior belonging to the annotation listener pipeline, handled by adapters created through `EventListenerMethodProcessor`. It does not change the role of `ApplicationListenerDetector` and does not cause the detector to start scanning annotations.

### 8.4. ApplicationListener and @EventListener differ in event types

`ApplicationListener<E>` constrains `E extends ApplicationEvent`. Meanwhile, `@EventListener` can accept `ApplicationEvent` or plain Java objects. Spring wraps payload objects into `PayloadApplicationEvent` in the publishing infrastructure.

This point matters when reading the detector: it checks whether a bean implements the `ApplicationListener` interface. It does not automatically turn a bean with a POJO-accepting method into an ApplicationListener; that adapter is created by `EventListenerMethodProcessor`.

## 9. Complete example: ApplicationListener bean in Spring 6.2.0

The following example uses Java 17 and Spring Context 6.2.0. It registers a listener bean for a business event and a listener for `ContextRefreshedEvent`. There is no need to manually create or register `ApplicationListenerDetector`; ApplicationContext installs the internal processor automatically.

**Project structure**

~~~text
application-listener-detector-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationListenerDetectorDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>application-listener-detector-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ApplicationListenerDetectorDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/ApplicationListenerDetectorDemo.java**

~~~java
package demo;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ApplicationListenerDetectorDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            System.out.println("Publishing ORD-70");
            context.publishEvent(new OrderCreatedEvent(context, "ORD-70"));
        }
    }

    @Configuration
    public static class AppConfig {

        @Bean
        public OrderCreatedListener orderCreatedListener() {
            return new OrderCreatedListener();
        }

        @Bean
        public ApplicationListener<ContextRefreshedEvent> refreshListener() {
            return event ->
                    System.out.println("ContextRefreshedEvent received");
        }
    }

    public static class OrderCreatedEvent extends ApplicationEvent {

        private static final long serialVersionUID = 1L;

        private final String orderId;

        public OrderCreatedEvent(Object source, String orderId) {
            super(source);
            this.orderId = orderId;
        }

        public String getOrderId() {
            return orderId;
        }
    }

    public static class OrderCreatedListener
            implements ApplicationListener<OrderCreatedEvent> {

        @Override
        public void onApplicationEvent(OrderCreatedEvent event) {
            System.out.println(
                    "OrderCreatedEvent received: " + event.getOrderId());
        }
    }
}
~~~

**Running the program**

From the directory containing `pom.xml`, run:

~~~bash
mvn -q compile exec:java
~~~

Output:

~~~text
ContextRefreshedEvent received
Publishing ORD-70
OrderCreatedEvent received: ORD-70
~~~

**Interpreting the output**

1. `AnnotationConfigApplicationContext(AppConfig.class)` registers the configuration and refreshes the context automatically.
2. During refresh, `registerListeners()` discovers the two listener bean names and registers the bean names with the multicaster.
3. When singletons are instantiated, `ApplicationListenerDetector` receives the actual instances of `OrderCreatedListener` and `refreshListener` after initialization, and registers the singleton instances.
4. `finishRefresh()` emits `ContextRefreshedEvent`, so `refreshListener` prints the first line.
5. After the context constructor returns, `main` publishes `OrderCreatedEvent`; the business listener receives the event and prints the order ID.

This example demonstrates registration of ApplicationListener beans in an ApplicationContext. The detector is an internal component installed automatically during refresh; application code only declares listener beans and publishes events.

## 10. Common source-reading mistakes and diagnostics

- **Saying the detector is a listener:** Wrong role. The detector is a BPP; it is the listener bean that implements `ApplicationListener` and receives events.
- **Assuming the detector is a bean found by component scan:** In Spring 6.2.0, `AbstractApplicationContext.prepareBeanFactory()` directly adds the detector to the BeanFactory.
- **Assuming the detector scans all objects on the heap:** It only processes instances going through the BeanFactory bean lifecycle.
- **Assuming all prototype listeners are ignored:** Top-level prototype listeners are registered by `registerListeners()` by bean name; the detector simply does not retain fixed prototype instances.
- **Assuming the detector detects all inner beans:** The detector can only register eligible singleton inner bean instances. Non-singleton inner beans lack a stable top-level bean name and trigger a warning.
- **Assuming the detector handles @EventListener:** Annotated methods are processed by `EventListenerMethodProcessor`, which creates `ApplicationListenerMethodAdapter`.
- **Assuming listeners are added before init callbacks:** The detector uses `postProcessAfterInitialization`, meaning after bean initialization callbacks.
- **Assuming the detector decides async execution:** The detector only registers listeners. The multicaster and `supportsAsyncExecution()` determine whether a listener can run asynchronously.
- **Assuming registerListeners() instantiates all listener beans:** Spring registers bean names with `allowEagerInit=false`; regular bean initialization occurs in the next step.
- **Forgetting cleanup:** The detector has a destruction-aware callback to remove singleton listener instances from the context when beans are destroyed.

## 11. Checklist when debugging ApplicationListenerDetector

When a listener does not receive events or receives them multiple times, check in order:

1. Does the bean actually implement `ApplicationListener`, or does it only have an `@EventListener` method?
2. Is the listener a top-level bean, an inner bean, or an object created manually with `new`?
3. Is the bean scope singleton or non-singleton?
4. Was the top-level bean name discovered by `registerListeners()` via `getBeanNamesForType(ApplicationListener.class, true, false)`?
5. Has the bean been instantiated so the detector ran `postProcessAfterInitialization`?
6. Was the listener registered by instance, bean name, or `@EventListener` adapter?
7. Are two separate listener paths handling the same event and causing duplicate handling?
8. Has the context finished refreshing and was the event published to the right ApplicationContext?
9. If an executor exists, does the listener support async execution and is the multicaster configured with an executor?

## 12. Key takeaways

`ApplicationListenerDetector` is an internal BeanPostProcessor installed early by `AbstractApplicationContext` in `prepareBeanFactory()`. It observes bean instances after initialization, registers actual singleton `ApplicationListener` instances, and removes instances when beans are destroyed.

`registerListeners()` handles registering top-level listener bean names before singletons are instantiated; the detector complements it by detecting singleton inner listener beans that bean name queries cannot find. Top-level non-singleton listeners can still be registered by bean name.

`EventListenerMethodProcessor` is an independent pipeline: it scans `@EventListener` methods and creates ApplicationListener adapters. In Spring 6.2, clearly distinguishing these three roles is essential when reading the refresh lifecycle, debugging registration timing, and resolving duplicate listeners.

## References — Spring Framework 6.2.0

- [ApplicationListenerDetector.java — source tag v6.2.0](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-context/src/main/java/org/springframework/context/support/ApplicationListenerDetector.java)
- [AbstractApplicationContext.java — source tag v6.2.0](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-context/src/main/java/org/springframework/context/support/AbstractApplicationContext.java)
- [AbstractApplicationEventMulticaster.java — source tag v6.2.0](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-context/src/main/java/org/springframework/context/event/AbstractApplicationEventMulticaster.java)
- [EventListenerMethodProcessor.java — source tag v6.2.0](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-context/src/main/java/org/springframework/context/event/EventListenerMethodProcessor.java)
- [EventListenerMethodProcessor Javadoc — 6.2.0](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListenerMethodProcessor.html)
- [EventListener Javadoc — 6.2.0](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListener.html)
- [ApplicationListener Javadoc — 6.2.0](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationListener.html)
- [ApplicationEventMulticaster Javadoc — 6.2.0](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
