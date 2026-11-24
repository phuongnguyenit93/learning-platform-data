# SmartInitializingSingleton and When Singletons Are Prepared

In Spring's bean lifecycle, each bean has its own initialization callbacks. However, sometimes a component needs to wait for regular singletons in the container to finish initializing before building a registry, checking consistency, or performing a shared preparation step.

Spring provides the `SmartInitializingSingleton` interface for this moment. The container calls `afterSingletonsInstantiated()` after the pre-instantiation phase of non-lazy singletons. The callback signals that ordinary singletons have been prepared during the bootstrap phase; it does not mean every bean in the application has been created or that the application is ready to accept requests.

## 1. What Is SmartInitializingSingleton?

`SmartInitializingSingleton` belongs to the `org.springframework.beans.factory` package and has one method:

~~~java
public interface SmartInitializingSingleton {

    void afterSingletonsInstantiated();
}
~~~

A bean implementing this interface receives the `afterSingletonsInstantiated()` callback once Spring completes the pre-instantiation phase of regular singletons during ApplicationContext initialization.

The callback can be used to:

- Build a registry from registered singleton components.
- Validate overall configuration after eager singletons have been initialized.
- Wire or index components that need visibility across multiple existing beans.
- Perform internal preparation depending on the initialized state of other singletons.

This callback is designed for the container's bootstrap phase. It is not a callback that runs after every request, not a callback when any arbitrary bean is created, and not a bean destruction callback.

## 2. At What Moment Is the Callback Invoked?

During ApplicationContext refresh, Spring performs multiple phases. The part relevant to this callback can be visualized as follows:

~~~text
ApplicationContext.refresh()
        |
        v
Register BeanPostProcessors and prepare context infrastructure
        |
        v
finishBeanFactoryInitialization()
        |
        v
preInstantiateSingletons()
        |
        +--> Create non-lazy singletons
        |    Inject dependencies and run initialization callbacks
        |
        v
Call afterSingletonsInstantiated()
for singletons implementing SmartInitializingSingleton
        |
        v
finishRefresh()
        |
        +--> Initialize LifecycleProcessor
        +--> Start appropriate SmartLifecycle beans
        +--> Publish ContextRefreshedEvent
        |
        v
Spring Boot runs ApplicationRunner / CommandLineRunner
        |
        v
ApplicationReadyEvent
~~~

Inside each bean, constructors, dependency injection, and initialization callbacks such as `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, or `initMethod` were already processed while that bean was created. Afterward, once Spring finishes creating regular eager singletons, it calls `afterSingletonsInstantiated()` on singletons implementing this interface.

Therefore, the callback can observe other eager singletons after they have been initialized. It runs during refresh, before `ContextRefreshedEvent`; thus, do not interpret this callback as a signal that the ApplicationContext has completed the entire refresh process or that Spring Boot is ready to receive traffic.

## 3. Example: Building a Registry After Handlers Are Initialized

Suppose an application has multiple payment handlers. Each handler provides a provider code and is managed by Spring as a singleton. A registry needs to index handlers by code so other services can look them up quickly.

Define the contract:

~~~java
public interface PaymentHandler {

    String providerCode();

    void validateConfiguration();
}
~~~

Handlers can be implemented separately:

~~~java
import org.springframework.stereotype.Component;

@Component
public class CardPaymentHandler implements PaymentHandler {

    @Override
    public String providerCode() {
        return "card";
    }

    @Override
    public void validateConfiguration() {
        // Check local configuration required for the handler.
    }
}
~~~

The registry implements `SmartInitializingSingleton`:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.stereotype.Component;

@Component
public class PaymentHandlerRegistry
        implements SmartInitializingSingleton {

    private final List<PaymentHandler> handlers;
    private Map<String, PaymentHandler> handlersByCode = Map.of();

    public PaymentHandlerRegistry(List<PaymentHandler> handlers) {
        this.handlers = handlers;
    }

    @Override
    public void afterSingletonsInstantiated() {
        Map<String, PaymentHandler> discovered = new LinkedHashMap<>();

        for (PaymentHandler handler : handlers) {
            handler.validateConfiguration();

            PaymentHandler previous = discovered.putIfAbsent(
                    handler.providerCode(),
                    handler
            );

            if (previous != null) {
                throw new IllegalStateException(
                        "Duplicate payment provider: "
                                + handler.providerCode()
                );
            }
        }

        this.handlersByCode = Map.copyOf(discovered);
    }

    public PaymentHandler getRequired(String providerCode) {
        PaymentHandler handler = handlersByCode.get(providerCode);

        if (handler == null) {
            throw new IllegalArgumentException(
                    "Unsupported payment provider: " + providerCode
            );
        }

        return handler;
    }
}
~~~

When Spring creates `PaymentHandlerRegistry`, the `List<PaymentHandler>` dependency is resolved and required handlers are created. The constructor only stores the list. Validation and indexing happen inside `afterSingletonsInstantiated()`, once the creation phase for regular eager singletons completes.

After the callback, services can call `getRequired("card")` to retrieve the matching handler. If two handlers declare the same code, an exception is thrown during bootstrap and context refresh fails. Configuration errors are caught right at startup instead of appearing on a later request.

In real applications, `validateConfiguration()` should validate local configuration state or bean consistency. If validation needs to call remote services, consider timeouts, retries, and a separate startup policy; this callback runs synchronously during context initialization and can slow down or block startup.

## 4. Which Singletons Count as Initialized?

Understand the exact scope of the phrase "all singleton beans" in this callback.

### Eager singletons

Ordinary singletons not marked lazy are created by Spring during the pre-instantiation phase. When the callback is invoked, these singletons have already gone through their initialization.

This is the group of beans `SmartInitializingSingleton` is designed to coordinate.

### Lazy singletons

Beans with `@Lazy` or defined as lazy are not necessarily created during pre-instantiation. If a bean has not yet been created, you cannot assume a `SmartInitializingSingleton` callback will see an initialized instance of that bean.

If the callback needs a lazy bean, actively accessing the bean may cause it to be created early and alter its original lazy intent. Only do so when that is an intentional design decision.

In addition, a bean implementing `SmartInitializingSingleton` must itself be initialized during pre-instantiation to receive the standard startup callback. If the callback bean itself is lazy and only created after this phase, do not assume the container will retroactively invoke `afterSingletonsInstantiated()` for it.

### Prototype and other scopes

Prototypes are created whenever the container is asked to supply an instance. They do not belong to the pre-instantiated singleton group, so they do not receive `SmartInitializingSingleton` callbacks per instance.

Scopes such as request or session also have their own lifecycles. Do not use this interface to handle initialization or destruction for individual instances in those scopes.

### Beans created after the bootstrap phase

A bean created late due to a lazy lookup or requested by code after the context has refreshed does not cause the global callback to run again. `SmartInitializingSingleton` is a pre-instantiation milestone, not a continuous listener watching every bean created throughout application runtime.

## 5. Comparing with Other Callbacks and Events

Spring's initialization mechanisms differ in timing and scope:

| Mechanism | Timing | Usage scope |
|---|---|---|
| Constructor | During instance creation | Initialize initial state and receive dependencies |
| `@PostConstruct` | During initialization of each bean | Prepare that specific bean after dependencies are injected |
| `InitializingBean.afterPropertiesSet()` | During initialization of each bean | Bean-level initialization callback |
| `@Bean(initMethod = "...")` | During initialization of each bean | Invoke configured init method |
| `SmartInitializingSingleton` | After pre-instantiation of regular singletons | Work that must wait for eager singletons to be initialized |
| `ContextRefreshedEvent` | After ApplicationContext finishes refreshing | Components needing to know the context has refreshed |
| `ApplicationRunner` / `CommandLineRunner` | During Spring Boot startup, after refresh | Application startup tasks |
| `ApplicationReadyEvent` | After runners finish | Components needing to know Spring Boot has signaled readiness |

### Compared to @PostConstruct

`@PostConstruct` runs during initialization of the current bean. It fits validating or preparing the bean's internal state after dependencies have been injected.

It does not mean every other singleton in the application has already been initialized. If logic needs the state of singletons outside the direct dependency graph, do not rely on accidental ordering between beans to run that logic inside `@PostConstruct`.

`SmartInitializingSingleton` fits better when preparation needs to wait until the regular eager singleton creation phase ends.

### Compared to ContextRefreshedEvent

`ContextRefreshedEvent` is published when the ApplicationContext has finished refreshing. It fits when a component needs to react to the event that the context has finished loading.

An application with a context hierarchy or refresh mechanisms can publish this event across multiple contexts or multiple times during the corresponding lifecycle. Listeners need to check the right context and be designed to handle repeated invocations safely when needed.

`SmartInitializingSingleton` is tied to the bean factory's pre-instantiation phase, prior to the refresh-complete event.

### Compared to ApplicationRunner and ApplicationReadyEvent

In Spring Boot, `ApplicationRunner` and `CommandLineRunner` fit application startup work that needs arguments or should run after context refresh, such as loading seed data or checking application-level startup conditions.

`ApplicationReadyEvent` is published after runners finish and Spring Boot signals that the application is ready. If you need to start work tied to the application's ready state, consider this event.

Do not use `SmartInitializingSingleton` as a substitute for a readiness signal. The callback only indicates that the eager singleton creation phase has ended; it does not prove connections to every external system work or that the application has cleared the entire startup workflow.

## 6. Limitations to Keep in Mind

### Do not rely on order among multiple callbacks

An application may have multiple beans implementing `SmartInitializingSingleton`. Do not design callback A to depend on callback B definitely having run beforehand without an explicit coordination mechanism.

If steps require ordering, group them into a single coordinator or express dependencies through an explicit orchestration mechanism. Do not rely on bean creation order or bean names as an execution order contract.

### Callback runs synchronously during refresh

`afterSingletonsInstantiated()` is a synchronous method. If the callback performs slow work, it prolongs context startup time. If the callback throws an unhandled exception, refresh may fail.

Keep callbacks focused on preparing internal structures, validation, and necessary indexing. For long background tasks, use an appropriate task-running mechanism after the application is ready.

### Not a destruction callback

This interface only provides a callback after singletons are initialized. It has no `destroy()` or `stop()` method. If a bean needs to release resources when the context closes, use a proper destruction lifecycle mechanism such as `@PreDestroy`, `DisposableBean`, or `@Bean(destroyMethod = "...")` for beans in scopes whose destruction the container manages.

If the bean is a prototype, remember that Spring does not automatically invoke prototype destruction callbacks. Code owning the instance must still close that instance's resources.

## 7. When Should You Choose SmartInitializingSingleton?

Consider this interface when all of these characteristics apply:

1. The work belongs to the container initialization phase.
2. The work needs to wait until regular eager singletons are created and initialized.
3. The result is internal state or consistency validation serving other components.
4. The work can finish synchronously within a reasonable startup duration.
5. The bean implementing the callback is created during the pre-instantiation phase.

If you only need to initialize a single bean's own state, use its constructor or init callback. If you need to run application-level startup tasks after context refresh, consider `ApplicationRunner` or `CommandLineRunner`. If you need to react once the context refreshes or the application is ready, use the corresponding event.

`SmartInitializingSingleton` marks a specific milestone in the container lifecycle: regular eager singletons have been initialized and the container is wrapping up pre-instantiation. Understanding this milestone accurately helps place registry, validation, and shared preparation logic at the right time while avoiding confusing it with all lazy beans, all scopes, or the entire application being ready.
