# Listener List Caching in Spring Event Multicaster

When a Spring application publishes many events of the same type, searching through all listeners and checking each listener on every publication would be repetitive work. Spring includes a mechanism to **cache the list of matching listeners** directly inside the event multicaster. This lesson explains where the cache is built, what the lookup key contains, when the cache is used or refreshed, and what is **not** cached.

## 1. Where Does the Cache Sit in the Event-Publishing Flow?

Typical flow in an `ApplicationContext`:

~~~text
ApplicationEventPublisher.publishEvent(event)
    -> ApplicationContext forwards event to ApplicationEventMulticaster
        -> selects ApplicationListeners matching the event
            -> invokes each listener
~~~

`ApplicationEventMulticaster` is the coordination interface. In Spring Framework, `SimpleApplicationEventMulticaster` extends `AbstractApplicationEventMulticaster`. The abstract class manages listener registration, filtering, and caching; `SimpleApplicationEventMulticaster` is responsible for dispatching events to the selected listeners. By default, listeners are invoked synchronously on the event-publishing thread; configuring an executor is a separate concern, not a function of the cache.

**Three things to distinguish:**

- **Registry**: the set of listeners registered with the multicaster, consisting of instances and bean names.
- **Listener cache**: the filtering result from the registry for a combination of event type and source type. The cache avoids repeating the selection step when similar events arrive.
- **Listener execution**: the handler method still runs for **every event** published. Spring does not cache execution results or skip an event simply because of a cache hit.

For example: 200 listeners are registered, but only 5 care about `OrderCreatedEvent`. The first lookup must identify those 5 listeners; subsequent lookups with the same cache key can reuse the matching set. **The numbers 200/5 are purely illustrative**, not Spring constants.

## 2. Cache Key: Event Type and Source Type

In the `AbstractApplicationEventMulticaster` implementation, the core logic can be expressed as:

~~~text
cacheKey = (
    eventType  : ResolvableType,
    sourceType : Class<?> obtained from event.getSource() or null
)

cachedListeners = retrieverCache.get(cacheKey)
~~~

- **`eventType`** uses `ResolvableType`, so it can represent generic type information rather than just a class name. For example, with `PayloadApplicationEvent<T>`, the payload type can affect which listeners match.
- **`sourceType`** is the runtime type of the `event.getSource()` object. This is the **class of the source**, not the source object's identity, transaction ID, or payload content.
- Two events with the same `eventType` whose sources belong to two different classes can have **two different cache keys**. This is necessary because `GenericApplicationListener` or `SmartApplicationListener` can filter by source type.

Simplified key examples:

| Event type | Source type | Cache key |
| --- | --- | --- |
| `OrderCreatedEvent` | `CheckoutService.class` | `(OrderCreatedEvent, CheckoutService)` |
| `OrderCreatedEvent` | `CheckoutService.class` (different source object) | **Same key** as row above |
| `OrderCreatedEvent` | `AdminService.class` | **Different key** |
| `OrderCancelledEvent` | `CheckoutService.class` | **Different key** |

The cache belongs to **a single multicaster instance**, not application-wide shared memory or a distributed cache. Two separate `ApplicationContext` instances can own different multicasters and registries.

## 3. Cache Miss, Cache Hit, and the Filtering Step

Abbreviated progression of `getApplicationListeners(event, eventType)`:

1. Build a `ListenerCacheKey` from the event type and source type.
2. Look up the corresponding `CachedListenerRetriever` in `retrieverCache` (the implementation uses a concurrent structure to support concurrent access).
3. **Cache hit and entry ready**: retrieve the listener list from the retriever; no need to re-filter the entire registry by event/source type.
4. **Cache miss**: evaluate whether caching is eligible; if eligible, create a new retriever, filter listeners, and store the result. If not eligible, still filter and dispatch the event normally without retaining a cache entry.
5. Return the matching list for the multicaster to execute.

Filtering considers mechanisms supported by Spring, such as:

- `ApplicationListener<E>`: declares the event type of interest via generics.
- `GenericApplicationListener` and `SmartApplicationListener`: can decide based on `supportsEventType(...)` and `supportsSourceType(...)`.
- Listeners registered by **bean name**: Spring can inspect the bean type beforehand to eliminate non-matching candidates before retrieving instances when needed. The cache can hold **bean names** alongside matching listener instances, because not every bean has to be pinned to a single instance.
- `@EventListener` methods adapted by Spring into listeners; candidate selection also goes through the multicaster infrastructure.

This is a **cache of type-based filtering results**. If an `@EventListener(condition = "...")` has a condition depending on event content, the handling condition still needs to be evaluated when the event runs. You must not infer that a cache hit means the previous condition automatically holds for all subsequent payloads.

## 4. Runnable Java Example: Caching and Updating Listeners

The following example uses **Java 17+** and `spring-context`. We publish two events of the same type/source, add a new listener, and publish again. Adding the listener must cause the multicaster to recognize that the listener set has changed.

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'demo.ListenerCacheDemo'
}
~~~

Create `src/main/java/demo/ListenerCacheDemo.java`:

~~~java
package demo;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

public final class ListenerCacheDemo {

    static final class OrderCreatedEvent extends ApplicationEvent {
        private final int orderId;

        OrderCreatedEvent(Object source, int orderId) {
            super(source);
            this.orderId = orderId;
        }

        int orderId() {
            return orderId;
        }
    }

    static final class OrderListener implements ApplicationListener<OrderCreatedEvent> {
        private final String name;

        OrderListener(String name) {
            this.name = name;
        }

        @Override
        public void onApplicationEvent(OrderCreatedEvent event) {
            System.out.println(name + " -> order " + event.orderId());
        }
    }

    public static void main(String[] args) {
        var multicaster = new SimpleApplicationEventMulticaster();
        multicaster.addApplicationListener(new OrderListener("A"));

        Object source = new Object();
        multicaster.multicastEvent(new OrderCreatedEvent(source, 1));
        multicaster.multicastEvent(new OrderCreatedEvent(source, 2));

        // Modifying registry: Spring must clear the old listener cache.
        multicaster.addApplicationListener(new OrderListener("B"));
        multicaster.multicastEvent(new OrderCreatedEvent(source, 3));
    }
}
~~~

Run inside the Gradle project with Java 17+ (if Gradle Wrapper is present, use `./gradlew run --quiet`; on Windows use `gradlew.bat run --quiet`):

~~~text
A -> order 1
A -> order 2
A -> order 3
B -> order 3
~~~

**Explanation of each publication:**

| Point in time | Registry | Expected result |
| --- | --- | --- |
| Publish order 1 | A | A receives event; multicaster can build cache for the matching key |
| Publish order 2 | A | A is still invoked; eligible cache can be reused |
| Register B | A, B | Existing cache is invalidated/cleared due to registry change |
| Publish order 3 | A, B | Both A and B receive the event according to the current registry |

The stdout output **proves the new listener is recognized**; stdout alone **does not prove the number of cache hits**. To confirm specific hits/misses, you need to observe the Spring implementation with a debugger/profiler or dedicated instrumentation. There is no standard public API like `getListenerCacheHitCount()` on the multicaster.

**Why use the concrete class `OrderListener`?** The type `ApplicationListener<OrderCreatedEvent>` is explicitly preserved for the generic-checking mechanism. The example does not rely on Spring having to infer the event type from a lambda whose generics are erased at runtime.

## 5. When Is the Cache Refreshed or Not Used?

Registration/unregistration methods on `AbstractApplicationEventMulticaster`, such as `addApplicationListener(...)`, `addApplicationListenerBean(...)`, `removeApplicationListener(...)`, and `removeAllListeners()`, modify the registry and make old filtering results unreliable. The Spring implementation clears `retrieverCache` when performing these changes; the next publication recomputes against the current registry.

This differs from changing the **internal state** of a listener. For example, a registered listener checks an `enabled` flag when handling an event: changing that flag does not necessarily change the registry and is not a reason to automatically rebuild the listener cache. The flag must be checked inside the handler on every invocation.

Cases to keep in mind:

- **Class loader constraints**: Spring checks whether caching the event/source types is safe relative to the bean class loader (via `ClassUtils.isCacheSafe(...)`). If unsafe, Spring still selects listeners to dispatch but may skip caching that entry to avoid retaining inappropriate class loader references.
- **Concurrent access**: one thread may see a cache entry currently being populated by another thread. The implementation handles an unready entry by resolving the matching list itself for the current invocation; it does not return an empty list by default.
- **Multiple event/source types**: each distinct combination can create its own entry. Entry count depends on types used, so do not assume there is only one cached list for the entire application.
- **Bean scope**: caching a selected bean name does not mean every dispatch uses the exact same bean object across all scopes. Bean lifecycle is still managed by the BeanFactory.

Descriptions of `retrieverCache`, `ListenerCacheKey`, and `CachedListenerRetriever` are **implementation details**, useful for understanding and debugging; you should not write application code that depends on private structures or internal field names.

## 6. What Problems Does the Listener Cache Not Solve?

| Common misconception | Correct understanding |
| --- | --- |
| "The first event ran, so the next event of the same type is skipped." | Every event is still delivered to matching listeners. |
| "The cache stores the result of `onApplicationEvent`." | The cache stores listener selection; processing logic and side effects still run each time. |
| "A cache hit bypasses payload-based conditions." | Dynamic business conditions/checks must still be evaluated per event. |
| "Changing the source object definitely creates a new key." | Only the **source type** participates in the key; two objects of the same class usually use the same key. |
| "I must call cache.clear() manually whenever adding a listener." | Use the multicaster's register/unregister APIs; Spring handles invalidation. |
| "Listener caching makes event processing automatically asynchronous." | Synchronous/asynchronous behavior depends on dispatch/executor configuration and listener execution capability. |

In particular, do not confuse this cache with the **Spring Cache Abstraction** (`@Cacheable`, `CacheManager`): Spring Cache Abstraction caches method results by data key; listener caching is an internal optimization of the step that identifies event receivers.

## 7. How to Apply and Test in Real Applications

1. **Prefer explicit listener type declarations**, such as `ApplicationListener<OrderCreatedEvent>` or `@EventListener` for a concrete event type. Avoid registering overly broad listeners and manually checking `instanceof` for every event unnecessarily.
2. **Register listeners through Spring/Multicaster APIs**. If the application genuinely adds/removes listeners at runtime, use `addApplicationListener` or the corresponding remove APIs. Do not directly mutate internal cache structures via reflection.
3. **Keep business conditions in the handler**. Order state, user, feature flags, and payload data can change between events even when the cache key is identical.
4. **Evaluate performance in the right place**. Caching reduces candidate selection overhead; processing time may still be dominated by I/O, database, network, or blocking listeners. Measure actual latency and profile before optimizing.
5. **Test when the registry changes**. A minimal test should publish an event when only A exists, add B, publish again, and verify both A and B receive it; also test removal if the application uses that feature. Do not write tests depending on Spring's private fields.

**Remember:** For the same `ResolvableType` and source class, Spring can reuse the listener lookup result. When the registry changes, the cache is refreshed; events and listener logic are still processed normally on each publication.

### References

- [AbstractApplicationEventMulticaster — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/AbstractApplicationEventMulticaster.html)
- [SimpleApplicationEventMulticaster — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [AbstractApplicationEventMulticaster Source Code (Spring Framework)](https://github.com/spring-projects/spring-framework/blob/main/spring-context/src/main/java/org/springframework/context/event/AbstractApplicationEventMulticaster.java)
