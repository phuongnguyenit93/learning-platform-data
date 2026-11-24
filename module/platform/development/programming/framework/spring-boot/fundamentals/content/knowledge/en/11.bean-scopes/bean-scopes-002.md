# Prototype and When a New Instance Is Created

In Spring, **scope** determines how the container manages instances of a bean. The default scope is `singleton`: within an `ApplicationContext`, a bean definition is typically associated with a single shared instance. With `prototype` scope, Spring creates a new instance every time the container needs to resolve that bean.

What must be understood accurately is: "created anew each time" is counted per **request for the bean from the container**, such as a `getBean()` call or when Spring resolves a dependency while creating another bean. It does not mean every call to a method on the object, every HTTP request, or every thread automatically receives a new instance.

This distinction is especially important when injecting a prototype bean into a singleton service. If injected directly, the singleton typically receives **one prototype instance at the time the singleton itself is created**. To get a new instance on each operation, you must ask the container to look it up again, usually through `ObjectProvider<T>`.

## 1. What Is Prototype Scope?

A prototype bean is a bean whose scope is declared as `prototype`. For example:

~~~java
package com.example.jobs;

import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope("prototype")
public class JobContext {
    private final String id = java.util.UUID.randomUUID().toString();

    public String getId() {
        return id;
    }
}
~~~

When Spring discovers this class via component scanning, the container registers a bean definition with prototype scope. Each time `JobContext` is requested from the container, Spring creates and returns a new object:

~~~java
JobContext first = applicationContext.getBean(JobContext.class);
JobContext second = applicationContext.getBean(JobContext.class);

System.out.println(first == second); // false
System.out.println(first.getId());
System.out.println(second.getId());
~~~

The two variables reference two different instances. Each object holds its own state, such as the `id` value generated in the constructor/field initializer.

You can use the scope constant instead of a string literal:

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Scope;

@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class JobContext {
}
~~~

`ConfigurableBeanFactory.SCOPE_PROTOTYPE` has the value `"prototype"`. Using the constant helps reduce typos in the scope name.

## 2. Comparing Singleton and Prototype

| Characteristic | Singleton | Prototype |
|---|---|---|
| Default scope? | Yes | No |
| Instances created | Typically one instance per bean definition in a container | A new instance created each time the container resolves the bean |
| Typical creation time | When the context initializes (if not lazy), or on first request | When requested |
| Does the container retain the instance for reuse? | Yes | Does not manage a shared instance to return on subsequent requests |
| State across bean lookups | Shared instance | New instance has its own state |
| Suitable for | Stateless services, repositories, shared configuration | Objects holding state for a single task, builders, or short-lived contexts |
| Resource destruction | Container manages destruction callbacks when the context closes | Container does not automatically invoke destruction callbacks for prototypes after handing the object to the client |

Singleton here means singleton **within a bean factory/application context**, not a global object for the entire JVM. Two independent application contexts can have two singleton instances for the same bean definition.

Prototype is also not synonymous with "one object per HTTP request." If you want an instance tied to the HTTP request lifecycle, Spring has a dedicated `request` scope; if you want it tied to a user session, there is `session` scope in an appropriate web application.

## 3. When Does Spring Create a New Prototype Instance?

The practical rule is that Spring creates a prototype whenever there is a **bean resolution** requiring an instance of that bean definition.

### 3.1. On Each Call to getBean()

This is the easiest case to observe:

~~~java
JobContext first = context.getBean(JobContext.class);
JobContext second = context.getBean(JobContext.class);
JobContext third = context.getBean(JobContext.class);
~~~

The result is three distinct instances if all three calls target the same prototype bean definition and no custom wrapper/cache retains the result.

Note that if the code only calls it once:

~~~java
JobContext contextForJob = context.getBean(JobContext.class);
contextForJob.runStepOne();
contextForJob.runStepTwo();
~~~

then both method calls use **the same object**. Prototype scope does not create a new instance for every method call.

### 3.2. When Spring Injects a Prototype into Another Bean

Suppose a bean needs `JobContext`:

~~~java
@Component
public class JobRunner {
    private final JobContext jobContext;

    public JobRunner(JobContext jobContext) {
        this.jobContext = jobContext;
    }

    public void run() {
        jobContext.run();
    }
}
~~~

If `JobRunner` is a singleton (the default), Spring creates `JobRunner` during context initialization or when the bean is requested. While creating `JobRunner`, Spring resolves the `JobContext` dependency and creates one prototype instance to pass into the constructor.

Afterward, `JobRunner` keeps that reference. When `run()` is called multiple times, the code still uses the same `jobContext`. Spring does not automatically go back to the container every time `run()` executes.

~~~text
ApplicationContext initializes JobRunner (singleton)
                |
                v
     Needs dependency JobContext
                |
                v
     Spring creates prototype instance #1
                |
                v
     Injects into JobRunner constructor
                |
                v
       JobRunner holds reference #1
                |
          run() called multiple times
                |
                v
        Still uses instance #1
~~~

This is the most frequently misunderstood point: **prototype scope does not automatically turn an injected dependency into a fresh dependency on each use**.

### 3.3. A Prototype Injected into Another Prototype

If the parent bean is also a prototype, each time Spring creates the parent bean, the container resolves its dependencies again:

~~~java
@Component
@Scope("prototype")
class JobContext {
}

@Component
@Scope("prototype")
class JobRunner {
    private final JobContext context;

    JobRunner(JobContext context) {
        this.context = context;
    }
}
~~~

Each time `context.getBean(JobRunner.class)` is called, Spring creates a new `JobRunner` and resolves a new `JobContext` for that creation. Thus, runner/context pairs from different requests have their own instances.

If a prototype's dependency is a singleton, Spring still injects the shared singleton. The scope of the parent bean does not automatically alter the scope of the dependencies it references.

## 4. Declaring Prototype with @Scope

There are two common ways to register a prototype bean.

### 4.1. Using Component Scanning

~~~java
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope("prototype")
public class ShoppingCart {
    private final java.util.List<String> items =
            new java.util.ArrayList<>();

    public void add(String item) {
        items.add(item);
    }

    public java.util.List<String> items() {
        return java.util.List.copyOf(items);
    }
}
~~~

Spring discovers the class thanks to `@Component` and registers the bean definition with prototype scope thanks to `@Scope`.

### 4.2. Using a @Bean Method

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

@Configuration
public class JobConfiguration {

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    JobContext jobContext() {
        return new JobContext();
    }
}
~~~

The default bean name in the example is `jobContext`, matching the factory method name. Prototype scope is applied to the bean definition declared by that method.

When another `@Bean` method needs `JobContext`, declare the dependency as a parameter:

~~~java
@Bean
JobRunner jobRunner(JobContext jobContext) {
    return new JobRunner(jobContext);
}
~~~

Spring resolves the parameter according to its bean definition and corresponding scope. You should not casually call the factory method directly like an ordinary Java method expecting every configuration style to have the same semantics: with `@Configuration(proxyBeanMethods = false)`, a direct call is a plain Java method call. Using method parameter injection makes the dependency intent clear.

## 5. How to Obtain a Fresh Prototype Inside a Singleton: ObjectProvider

If a singleton needs a new prototype instance for each task execution, inject `ObjectProvider<T>` instead of injecting `T` directly.

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class JobCoordinator {
    private final ObjectProvider<JobContext> contexts;

    public JobCoordinator(ObjectProvider<JobContext> contexts) {
        this.contexts = contexts;
    }

    public void executeJob(String jobName) {
        JobContext context = contexts.getObject();
        context.start(jobName);
        context.run();
    }
}
~~~

Each time `executeJob` is called, the code invokes `getObject()`, asking the container to resolve `JobContext`. Because the target bean has prototype scope, each resolution creates a new instance.

~~~text
JobCoordinator (singleton)
        |
        +--- executeJob("A")
        |          |
        |          +--> contexts.getObject()
        |                    |
        |                    +--> JobContext #1
        |
        +--- executeJob("B")
                   |
                   +--> contexts.getObject()
                             |
                             +--> JobContext #2
~~~

`ObjectProvider` is a bean lookup handle provided by Spring. It does not pre-hold a single prototype instance; each call to a lookup method asks the bean factory to resolve the dependency according to its active scope.

### 5.1. Choosing the Right API

| API | When no matching bean exists | Purpose |
|---|---|---|
| `getObject()` | Throws an error | Bean is required |
| `getIfAvailable()` | Returns `null` | Bean is optional |
| `getIfUnique()` | Returns `null` if there is no unique candidate | Use only when selection must be unambiguous |
| `stream()` | Empty stream if no candidate exists | Iterate over matching beans |
| `orderedStream()` | Empty stream if no candidate exists | Iterate in Spring's defined order |

For a required prototype dependency, `getObject()` is usually the easiest choice to understand. If using `getIfAvailable()`, clearly define what the application should do when the bean does not exist. If multiple implementations of the same type exist, use qualifiers or iterate the stream rather than expecting `getObject()` to pick arbitrarily.

## 6. Another Approach: Method Injection with @Lookup

Spring supports `@Lookup` so the container overrides a method and performs a bean lookup when the method is called. This approach can be used when a singleton wants a new prototype without holding `ObjectProvider` directly.

~~~java
import org.springframework.beans.factory.annotation.Lookup;
import org.springframework.stereotype.Component;

@Component
public class LookupJobCoordinator {

    public void execute(String jobName) {
        JobContext context = newJobContext();
        context.start(jobName);
        context.run();
    }

    @Lookup
    protected JobContext newJobContext() {
        // Spring will override this method when creating the bean.
        return null;
    }
}
~~~

Spring creates a runtime subclass for the bean containing the lookup method and replaces the method implementation to look up the target bean. Each call to `newJobContext()` resolves `JobContext`; if the target is a prototype, each call receives a new instance.

Some conditions and limitations to remember:

- The bean containing the lookup method must be created and managed by the Spring container.
- Spring needs to be able to override the method; the class/method cannot be `final`, and the method cannot be `private` or `static`.
- Subclassing has limitations with classes/factory setups that Spring cannot subclass as required.
- Do not instantiate a bean containing `@Lookup` yourself with `new`, because that object is not created by the container and the method will not be overridden.

`@Lookup` is useful in certain scenarios, but `ObjectProvider` generally makes dependencies easier to spot in constructors and more convenient for testing. When designing services, prefer an approach that clearly expresses dependencies so the team can read and control them.

## 7. Lifecycle of a Prototype Bean

Prototype does not mean Spring skips the entire lifecycle. Each time an instance is created, the container can still run the usual bean management steps:

~~~text
Request prototype bean
        |
        v
Create instance
        |
        v
Inject dependencies / populate properties
        |
        v
Aware callbacks (if any)
        |
        v
BeanPostProcessor before initialization
        |
        v
Initialization callbacks
(@PostConstruct, InitializingBean, initMethod...)
        |
        v
BeanPostProcessor after initialization
        |
        v
Return instance to caller
        |
        v
Client uses it and owns subsequent lifecycle
~~~

The diagram is a high-level outline of the phase order; details depend on the callbacks and processors registered by the application.

Example:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope("prototype")
public class TemporaryWorkspace {

    @PostConstruct
    void initialize() {
        System.out.println("Prepare workspace");
    }

    @PreDestroy
    void cleanup() {
        System.out.println("Release workspace");
    }
}
~~~

Each time Spring creates `TemporaryWorkspace`, initialization callbacks such as `@PostConstruct` still execute. However, there is an important difference:

**Spring does not automatically invoke destruction callbacks for prototype beans after handing the instance to the client.** Because the container does not retain a list of prototype instances to close all of them when the context shuts down, `@PreDestroy` in the example is not automatically called just because the application terminates.

If a prototype owns resources such as file handles, sockets, temporary directories, or executors, the caller requesting the instance must have a plan to release them. You can have the object implement `AutoCloseable` and call `close()` when finished; in cases where Spring needs to run destruction processing, `AutowireCapableBeanFactory` provides `destroyBean(Object)` for instances managed by the application.

Example with try/finally:

~~~java
TemporaryWorkspace workspace = workspaces.getObject();
try {
    workspace.performTask();
} finally {
    workspace.close();
}
~~~

This snippet assumes `TemporaryWorkspace` implements `AutoCloseable`. If Spring-managed destruction callbacks are needed, use the appropriate destruction mechanism instead of assuming `@PreDestroy` runs automatically.

## 8. Are Prototypes Thread-Safe?

Prototypes are often useful for objects holding state specific to a single execution. However, **prototype scope is not a guarantee of thread safety**.

When Spring returns two different instances:

~~~java
JobContext first = contexts.getObject();
JobContext second = contexts.getObject();
~~~

the two objects do not share ordinary instance state. But if:

- code shares the same `first` reference across multiple threads,
- the object contains static mutable state,
- two instances operate on the same external resource,
- or a singleton dependency inside the prototype is not thread-safe,

then race conditions can still occur.

Prototype only defines how the container creates and returns objects. It does not automatically:

- create a new thread,
- lock operations,
- isolate database transactions,
- create a separate instance per HTTP request,
- or manage shared resources.

If you need a separate object per HTTP request, consider `@RequestScope`. If you need a separate object per job execution, using a provider to request a prototype at the start of each job usually expresses intent more clearly.

## 9. Prototype and Other Scopes

| Scope | Instance boundary | When typically created |
|---|---|---|
| `singleton` | One instance per bean definition in a container | On context initialization or first request if lazy |
| `prototype` | One instance per bean request/resolution | When requested |
| `request` | One instance within an HTTP request lifecycle | When request scope is accessed |
| `session` | One instance within an HTTP session lifecycle | When session scope is accessed |
| `application` | One instance within the ServletContext | When application scope is accessed |
| `websocket` | One instance within a WebSocket session lifecycle | When WebSocket scope is accessed |

Web scopes are only available in the corresponding web environment and require an active scope context. Prototype is a core scope that does not depend on HTTP.

### Prototype Is Not Request Scope

An HTTP request can call `getObject()` multiple times and receive multiple prototype instances within the same request. Conversely, if a request-scoped bean is resolved within the same request, valid accesses refer to the instance bound to that request.

Example:

~~~java
@Component
@Scope("prototype")
class RequestWorkBuffer {
}
~~~

Controller calls the provider twice:

~~~java
RequestWorkBuffer a = buffers.getObject();
RequestWorkBuffer b = buffers.getObject();
~~~

`a` and `b` are two distinct prototype instances even within the same HTTP request. Therefore, do not choose prototype just because you want "one object per request."

## 10. Verifying Instance Creation Timing

You can verify via object identity in a Spring test:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotSame;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest
class PrototypeScopeTest {

    @Autowired
    ApplicationContext context;

    @Test
    void eachLookupReturnsANewInstance() {
        JobContext first = context.getBean(JobContext.class);
        JobContext second = context.getBean(JobContext.class);

        assertNotSame(first, second);
    }
}
~~~

The test assumes `JobContext` is registered in the application context with prototype scope.

To test behavior when injected into a singleton, you can create a facade receiving a provider:

~~~java
@Component
class JobFacade {
    private final ObjectProvider<JobContext> contexts;

    JobFacade(ObjectProvider<JobContext> contexts) {
        this.contexts = contexts;
    }

    JobContext newContext() {
        return contexts.getObject();
    }
}
~~~

~~~java
@SpringBootTest
class JobFacadeTest {
    @Autowired
    JobFacade facade;

    @Test
    void providerResolvesAPrototypeForEachCall() {
        JobContext first = facade.newContext();
        JobContext second = facade.newContext();

        assertNotSame(first, second);
    }
}
~~~

You can add a control test with direct constructor injection: fetching the singleton facade twice still yields the same singleton, and the prototype field injected into the facade remains the same reference. This comparison clarifies the difference between **creating anew when the container resolves a dependency** and **re-requesting the bean on each operation**.

## 11. Common Misconceptions

| Misconception | Actual behavior |
|---|---|
| "Prototype means every method call gets a new object." | A new instance only appears when the container resolves the bean again; method calls on an existing reference still use the old object. |
| "Injecting a prototype into a singleton gives a new prototype each time the singleton uses it." | The dependency is resolved when creating the singleton; the singleton keeps the injected instance. |
| "Prototypes destroy themselves when done." | Spring does not automatically run destruction callbacks for prototypes after handing out the instance; the client is responsible for releasing resources. |
| "Prototypes are always thread-safe." | Scope does not provide synchronization; code and dependencies still need thread-safe design. |
| "Prototype is equivalent to request scope." | A single request can request multiple prototype instances; request scope binds an instance to the request lifecycle. |
| "Using ObjectProvider makes Spring create a new object." | The provider simply asks the container to resolve; the target bean's scope decides whether the instance is new. |
| "Every dependency inside a prototype automatically becomes a prototype too." | Each dependency follows its own scope; singleton dependencies remain shared. |

## 12. When Should You Use Prototype?

Prototype makes sense when the application needs an object with separate state per operation, for example:

- `JobContext` holding progress, results, and metadata for a single job.
- `ShoppingCartDraft` used to build an independent calculation session within a task.
- `ReportBuilder` accumulating data to produce a report.
- `CommandContext` holding temporary state for a single command execution.
- `TemporaryWorkspace` managing temporary resources in an operation and explicitly released afterward.

There is no need to switch every service to prototype. Stateless business services, repositories, and configuration components usually fit singleton. Prototype carries the cost of repeated object creation and requires the caller to manage resource lifecycles if applicable.

If the goal is to create a simple Java object that needs no Spring injection, lifecycle, or configuration, using a regular Java constructor/factory may be clearer. Prototype scope is useful when you need **the Spring container to create a new instance while still applying dependency injection and bean initialization** to each instance.

## 13. Decision and Application Process

When designing a stateful bean, determine:

1. **Who owns the state?** If the state is shared application-wide and the bean is safe under concurrent use, singleton may fit. If the state belongs only to one execution, prototype is an option.
2. **When is the instance needed?** If needed once when creating the parent bean, direct injection works. If needed per operation, inject `ObjectProvider<T>` and call `getObject()` at the start of the operation.
3. **Who releases resources?** Prototypes do not get automatic container destruction callbacks; identify where `close()` or an appropriate destruction mechanism is called.
4. **Are there multiple implementations?** Use qualifiers to narrow candidates or streams to select according to business rules.
5. **Does the scope match the actual lifecycle?** Distinguish prototype from request/session scope and do not rely on scope to solve thread safety.
6. **Test creation timing.** Use `assertNotSame` for two lookups and test direct singleton injection versus a singleton using a provider.

Prototype means **one bean resolution from the container creates one new instance**. After the object is returned, the application uses that exact instance until it is no longer needed. If a singleton needs a new instance for each piece of work, it must ask the container to resolve again via `ObjectProvider` or an equivalent lookup mechanism. Understanding this boundary helps choose the right scope and avoid false expectations about object creation timing, state, and bean lifecycle.
