# SearchStrategy.CURRENT, ANCESTORS, and ALL in the ApplicationContext Hierarchy

## 1. Why Is SearchStrategy Needed?

Spring can run multiple `ApplicationContext` instances in a **parent–child** relationship. Each context holds its own bean definitions. When looking up beans, a child context can see beans from its parent according to Spring's rules, whereas the parent does not automatically see beans declared only in the child.

When Spring Boot evaluates a condition like "does bean `X` exist?", the key question is: **search for the bean only in the current context, or in parent contexts as well?** The `org.springframework.boot.autoconfigure.condition.SearchStrategy` enum lets you select the search region via the `search` attribute on bean conditions.

After this lesson, you will be able to read a context hierarchy, predict `@ConditionalOnBean` / `@ConditionalOnMissingBean` outcomes, and choose the right scope when writing auto-configurations.

## 2. The Three Values: CURRENT, ANCESTORS, and ALL

Consider the following context chain, with the condition being evaluated **in WebContext**:

```text
RootContext
    |
    v
ServiceContext
    |
    v
WebContext  <-- current context
```

| Strategy | Where It Searches | Where It Does Not Search |
|---|---|---|
| `SearchStrategy.CURRENT` | Only `WebContext` | `ServiceContext`, `RootContext` |
| `SearchStrategy.ANCESTORS` | `ServiceContext` and `RootContext` | `WebContext` |
| `SearchStrategy.ALL` | `WebContext` and all ancestors | No context along the upward path is excluded |

**`ANCESTORS` includes all ancestors, not just the immediate parent**, and always excludes the context currently being evaluated. **`ALL` includes the current context and all ancestors**, which does not mean searching sibling contexts or other child contexts. If there is only a single root context, `ANCESTORS` has nowhere to search; `CURRENT` and `ALL` inspect the same context.

The parent–child relationship between `ApplicationContext` instances is the deciding factor. Two Java packages, two `@Configuration` classes, or two `singleton`/`prototype` bean scopes do not by themselves create two contexts.

## 3. Where Is SearchStrategy Used?

All three major bean conditions in Spring Boot 3.3 support the `search` attribute and default to **`SearchStrategy.ALL`**:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnSingleCandidate;
import org.springframework.boot.autoconfigure.condition.SearchStrategy;

// Illustrative annotation snippets, placed on @Bean or an appropriate configuration:
// @ConditionalOnBean(value = Client.class, search = SearchStrategy.ALL)
// @ConditionalOnMissingBean(value = Client.class, search = SearchStrategy.CURRENT)
// @ConditionalOnSingleCandidate(value = Client.class, search = SearchStrategy.ANCESTORS)
```

In the last three example lines, `Client` is a hypothetical application type:

- `@ConditionalOnBean` matches when beans satisfying the declared requirements exist in the inspected scope. If there are multiple requirements, all must be met; the same bean does not necessarily have to satisfy every requirement.
- `@ConditionalOnMissingBean` matches when **no** bean satisfies the requirements in the inspected scope. It is commonly used to provide a default bean when the user has not declared a corresponding bean yet.
- `@ConditionalOnSingleCandidate` requires an identifiable single matching candidate for the bean type; multiple beans of the same type can still qualify if a single `@Primary` candidate is designated.

`search` only determines **the condition evaluation scope**. It does not create a parent context, does not register beans itself, does not change component-scan scope, and does not replace `@Qualifier` or injection mechanisms.

## 4. Decision Tables by Bean Location

Suppose the condition is being evaluated in **Child**, looking for a bean of type `Marker`. The beans in the example qualify as candidates, have distinct names, and have already been processed by Spring before the condition runs.

### `@ConditionalOnBean(Marker.class)`

| Location of `Marker` | CURRENT | ANCESTORS | ALL |
|---|---|---|---|
| Only in Parent | Does not match | Matches | Matches |
| Only in Child | Matches | Does not match | Matches |
| In both Parent and Child | Matches | Matches | Matches |
| Nowhere | Does not match | Does not match | Does not match |

### `@ConditionalOnMissingBean(Marker.class)`

With a single type requirement as above, the outcome is the inverse:

| Location of `Marker` | CURRENT | ANCESTORS | ALL |
|---|---|---|---|
| Only in Parent | Matches | Does not match | Does not match |
| Only in Child | Does not match | Matches | Does not match |
| In both Parent and Child | Does not match | Does not match | Does not match |
| Nowhere | Matches | Matches | Matches |

Common consequence: Child has no `Marker`, while Parent does. `@ConditionalOnMissingBean(Marker.class)` uses the default `ALL`, so it **does not create a fallback bean** in Child. Changing to `search = CURRENT` allows the condition **to match**, because only Child is checked then.

These tables represent the basic model by bean type. Beans with the same name between parent and child can be shadowed during lookup; special candidates can also produce results different from mechanically counting every bean definition. When those cases occur, inspect the actual condition report.

## 5. Java 17+ Example: Parent Has Marker, Child Does Not

The following example has a standalone `main` method. Place `SearchStrategyDemo.java` in a project with Spring Framework 6.x and Spring Boot 3.3.x (including `spring-context`, `spring-boot-autoconfigure`), then run `SearchStrategyDemo.main` from your IDE with the project classpath. No web server needs to be started.

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.SearchStrategy;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SearchStrategyDemo {

    public static class Marker {}

    @Configuration(proxyBeanMethods = false)
    public static class ParentConfiguration {
        @Bean
        public Marker parentMarker() {
            return new Marker();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ChildConfiguration {
        @Bean("checkCurrent")
        @ConditionalOnBean(value = Marker.class, search = SearchStrategy.CURRENT)
        public String checkCurrent() {
            return "found current";
        }

        @Bean("checkAncestors")
        @ConditionalOnBean(value = Marker.class, search = SearchStrategy.ANCESTORS)
        public String checkAncestors() {
            return "found ancestors";
        }

        @Bean("checkAll")
        @ConditionalOnBean(value = Marker.class, search = SearchStrategy.ALL)
        public String checkAll() {
            return "found all";
        }

        @Bean("missingCurrent")
        @ConditionalOnMissingBean(
                value = Marker.class, search = SearchStrategy.CURRENT)
        public String missingCurrent() {
            return "missing current";
        }

        @Bean("missingAll")
        @ConditionalOnMissingBean(
                value = Marker.class, search = SearchStrategy.ALL)
        public String missingAll() {
            return "missing all";
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext parent =
                     new AnnotationConfigApplicationContext(
                             ParentConfiguration.class)) {
            try (AnnotationConfigApplicationContext child =
                         new AnnotationConfigApplicationContext()) {
                child.setParent(parent);
                child.register(ChildConfiguration.class);
                child.refresh();

                System.out.println("OnBean CURRENT   : "
                        + child.containsLocalBean("checkCurrent"));
                System.out.println("OnBean ANCESTORS : "
                        + child.containsLocalBean("checkAncestors"));
                System.out.println("OnBean ALL       : "
                        + child.containsLocalBean("checkAll"));
                System.out.println("Missing CURRENT  : "
                        + child.containsLocalBean("missingCurrent"));
                System.out.println("Missing ALL      : "
                        + child.containsLocalBean("missingAll"));
            }
        }
    }
}
```

Expected `System.out` output (any extra log lines printed by libraries, if present, are not part of the output below):

```text
OnBean CURRENT   : false
OnBean ANCESTORS : true
OnBean ALL       : true
Missing CURRENT  : true
Missing ALL      : false
```

How to trace the reasoning:

1. Parent is created and refreshed first, so the `parentMarker` bean of type `Marker` is already present.
2. Child is attached to Parent via `setParent(parent)` before registering configurations and calling `refresh()`.
3. Child does not define `Marker`. Therefore `@ConditionalOnBean(search = CURRENT)` does not match, whereas `ANCESTORS` and `ALL` find `parentMarker`.
4. With `@ConditionalOnMissingBean`, `CURRENT` matches because Child lacks `Marker`, while `ALL` does not match because Parent already has one.
5. `containsLocalBean(...)` checks beans **registered in Child**, making it easy to observe the exact result. `containsBean(...)` can traverse up to the parent and is less suitable for this local check.

In the code above, the conditional methods return `String` for easy printing; a real application would return a service, client, or adapter. The example intentionally uses `@Configuration` because all beans in Parent are already processed before Child evaluates its conditions; in production, bean conditions are typically placed in auto-configuration to control ordering.

## 6. Choosing a Strategy by Scenario

### CURRENT: Allow a Separate Bean in Each Context

```java
@Bean
@ConditionalOnMissingBean(
        value = RequestHandler.class,
        search = SearchStrategy.CURRENT)
RequestHandler localHandler() {
    return new DefaultRequestHandler();
}
```

Illustrative snippet with two application-defined types `RequestHandler` and `DefaultRequestHandler`. Child can create its own handler even when Parent already has a handler of the same type. Use when each context is designed to have its own configuration, while accepting that beans of the same type may exist at multiple levels.

### ANCESTORS: Match Only If an Ancestor Provides the Service

```java
@Bean
@ConditionalOnBean(
        value = SharedRegistry.class,
        search = SearchStrategy.ANCESTORS)
RegistryBridge registryBridge(SharedRegistry registry) {
    return new RegistryBridge(registry);
}
```

Illustrative snippet with custom types `SharedRegistry` / `RegistryBridge`. A bean present only in Child is not enough; the condition requires `SharedRegistry` in an ancestor. Note that **the condition matching does not guarantee the `registry` parameter will definitely be injected from Parent** if Child also has a candidate of the same type. Bean selection rules during injection must be considered separately.

### ALL: Yield to an Existing Bean Anywhere in the Context Tree

```java
@Bean
@ConditionalOnMissingBean(
        value = MetricsReporter.class,
        search = SearchStrategy.ALL)
MetricsReporter metricsReporter() {
    return new DefaultMetricsReporter();
}
```

Illustrative snippet with two application-defined types. Auto-configuration provides the default `MetricsReporter` only when neither Child nor any ancestor context already has a matching bean. This is a common choice to avoid creating a default bean that duplicates the role of a shared bean from Parent.

## 7. Important Limitations

**Bean definition processing order:** `@ConditionalOnBean` and `@ConditionalOnMissingBean` only evaluate bean definitions that the context has processed **up to evaluation time**. A bean appearing later can make the intuition "eventually bean X exists" wrong. Spring Boot recommends using these conditions in auto-configurations, since user-declared beans are normally processed first. When depending on a bean created by another auto-configuration, use ordering mechanisms like `@AutoConfiguration(after = ...)`.

**Single candidate vs. bean exists:** `@ConditionalOnSingleCandidate(value = TaskExecutor.class, search = ALL)` needs to pick a single suitable candidate. Having two `TaskExecutor` beans without a unique selectable candidate means `@ConditionalOnBean(TaskExecutor.class)` can match while `@ConditionalOnSingleCandidate` does not. A suitable `@Primary` candidate can let the single-candidate condition match. `search` determines which contexts are included when considering candidates.

**Lookup by type vs. lookup by name:** `@ConditionalOnBean(value = Client.class)` checks by type, whereas `@ConditionalOnBean(name = "client")` checks by name. In parent–child systems, duplicate bean names and shadowing rules can affect lookup results. Do not deduce behavior solely from the total count of beans of that type visible in a debugger.

**Not every bean is a valid candidate:** Bean conditions can ignore beans that are not autowire candidates or candidates excluded under the rules of the Spring Boot version in use. If the outcome differs from the simple tables above, examine type, name, candidate flags, and processing timing.

**Bean lookup is not equivalent to the condition:** `child.getBean(Service.class)` may resolve a bean in Parent, yet `@ConditionalOnBean(value = Service.class, search = CURRENT)` still does not match when Child has no local matching bean. Furthermore, `@Primary`, `@Qualifier`, and generic types can affect injection; `search` does not control all of those rules by itself.

**Do not use ANCESTORS out of habit:** Many typical Spring Boot applications have only a single context. `ANCESTORS` is only useful when a real parent context exists. A `@Configuration` nested inside another class can still belong to the same context.

## 8. Step-by-Step Debugging

1. Identify the exact **context evaluating the condition**, then walk `applicationContext.getParent()` to see which ancestors exist.
2. Determine whether the requirement is by **type** or **name** and see at which level the bean is registered. Also check cases where parent and child share the same bean name.
3. Check the `search` attribute; if omitted, it defaults to `ALL`.
4. Use the **Condition Evaluation Report**: run the Spring Boot application with `--debug` to view positive/negative condition matches. If Actuator is used and the corresponding endpoint is enabled, you can inspect `/actuator/conditions`.
5. When a condition depends on another auto-configuration, verify **bean definition registration order**, not just the list of beans after the application finishes starting.
6. When writing tests yourself, distinguish `containsLocalBean` from operations that can search through the parent. Read the bean type, bean name, and candidate criteria before concluding the bug lies in `SearchStrategy`.

## 9. Self-Check Exercises

**Question 1.** Child does not have `CacheClient`; Parent does. Does `@ConditionalOnMissingBean(value = CacheClient.class, search = CURRENT)` match?

**Answer:** Yes. CURRENT only inspects Child, so the "missing bean" condition matches.

**Question 2.** Child has `CacheClient`; Parent does not. Does `@ConditionalOnBean(value = CacheClient.class, search = ANCESTORS)` match?

**Answer:** No. ANCESTORS excludes Child from the search scope.

**Question 3.** Root has `CacheClient`; Middle and Leaf do not. In Leaf, does `@ConditionalOnBean(value = CacheClient.class, search = ANCESTORS)` match?

**Answer:** Yes. Root is also an ancestor of Leaf, even though it is not the immediate parent.

**Question 4.** Neither Child nor Parent has `CacheClient`. Does `@ConditionalOnMissingBean(CacheClient.class)` match?

**Answer:** Yes. The default ALL finds no matching bean anywhere along the parent–child chain.

## 10. Key Takeaways

- **CURRENT:** only the current context.
- **ANCESTORS:** all ancestor contexts, excluding the current one.
- **ALL:** the current context and all ancestor contexts; also the default `search` value for the three bean conditions covered.

Choose `search` based on architectural requirements: whether a bean must be local to Child, must come from Parent, or may be shared across the context hierarchy. With `@ConditionalOnMissingBean`, remember that the default `ALL` can prevent Child from **creating a new bean** when Parent already has a bean of the same type.

### Official Documentation

- [Spring Boot SearchStrategy API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/autoconfigure/condition/SearchStrategy.html)
- [Spring Boot 3.3 ConditionalOnBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html)
- [Spring Boot 3.3 ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Boot 3.3 ConditionalOnSingleCandidate API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
