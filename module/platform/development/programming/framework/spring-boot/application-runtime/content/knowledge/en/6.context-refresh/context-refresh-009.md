# Parent–Child Contexts in Spring: Bean Visibility and Ownership Scope

## 1. Background and Mental Model

In a typical Spring Boot application, `SpringApplication.run(...)` creates a single primary `ApplicationContext`. However, Spring Framework also supports a **hierarchy of multiple ApplicationContexts**: one context acts as parent to one or more child contexts. Each context has its **own BeanFactory/bean registry**, yet a child context can use beans from the parent context through upward lookup.

This topic has two core questions:

1. **Which bean can see which bean?** Can a bean created by a child context depend on a parent bean? Does the parent automatically see beans registered in a child? If both places use the same bean name, which lookup result wins?
2. **Which context owns the bean?** Which context is responsible for creating it, applying post-processors, managing the singleton cache, and calling callbacks on close? Does a child retrieving a parent bean transfer ownership of that bean?

Key mindset: a context hierarchy is a **hierarchy of lookup visibility and lifecycle management**. It differs from placing classes in parent/child packages, differs from Java class inheritance, and also differs from Spring's `BeanDefinition` inheritance.

~~~mermaid
flowchart TB
    P["Parent ApplicationContext\nParent BeanFactory\nsharedClock, auditClient, policy=parent"]
    C1["Child ApplicationContext A\nChild BeanFactory A\norderService, policy=child-A"]
    C2["Child ApplicationContext B\nChild BeanFactory B\nreportService, policy=child-B"]
    C1 -->|"looks up missing beans in parent"| P
    C2 -->|"looks up missing beans in parent"| P
~~~

In the diagram, A and B **both see** beans registered in the parent, yet A does not automatically see beans registered solely by B and vice versa. The parent also does not automatically look down into each child.

### Overarching Rules

| Query / relationship | Typical outcome | Reason |
| --- | --- | --- |
| Child calls `getBean("sharedClock")`, child lacks it, parent has it | Receives **instance from parent** | Lookup by name delegates up to parent when absent locally |
| Parent calls `getBean("orderService")`, only child A has it | Not found | Parent does not look downward into children |
| Child A calls `getBean("reportService")`, only child B has it | Not found | Siblings do not directly look up each other |
| Child and parent both register `policy` | Child gets its **local** version when looking up `policy`; parent still gets parent's version | Child bean shadows the same-named parent bean for lookups originating in the child |
| Child injects a singleton that exists only in parent | Uses the **same singleton instance from parent** | Beans are not copied when accessed across a hierarchy |
| Closing child A | Child A destroys singletons it manages; parent stays active unless closed separately | Ownership does not transfer to the bean's consumer |

These are the default hierarchy rules for Spring bean factories. Additional mechanisms such as custom bean resolution, proxies, scopes, or special configuration can alter observed details.

## 2. Establishing a Parent–Child Relationship

### 2.1. One Context Has One Parent, Can Have Many Children

`ApplicationContext` has `getParent()`; `HierarchicalBeanFactory` has `getParentBeanFactory()` and `containsLocalBean(...)`. Each child context has at most one direct parent, while multiple children can share one parent. The parent context does not maintain a list of "all beans of all children" for downward lookup.

Distinguish carefully:

- **ApplicationContext hierarchy:** multiple containers, each registering and managing its own beans; allows upward lookup to the parent.
- **Bean definition inheritance:** one bean definition using another bean definition's configuration as a template (such as `ChildBeanDefinition`, XML `parent=...`), which can exist in the same context. This is not a relationship between two containers.
- **Java inheritance:** `class B extends A` inherits Java members/methods; it does not decide which container owns a bean.
- **Package/component scanning:** packages `com.example.parent` and `com.example.child` do not automatically create two ApplicationContexts; one `@ComponentScan` can scan both into **one** context.

A single-context application can still hold thousands of beans across many packages. Only two beans sharing a name **in two different contexts** trigger parent–child shadowing; two colliding definitions in **the same** registry are a separate bean-definition overriding topic.

### 2.2. Creating a Hierarchy with Spring Framework

The `AnnotationConfigApplicationContext` API lets you build a hierarchy programmatically:

~~~java
AnnotationConfigApplicationContext parent =
        new AnnotationConfigApplicationContext(ParentConfig.class);

AnnotationConfigApplicationContext child =
        new AnnotationConfigApplicationContext();

child.setParent(parent);
child.register(ChildConfig.class);
child.refresh();
~~~

Written this way, the parent is already refreshed when the parameterized constructor returns; the child is assigned its parent **before** calling `refresh()`. Beans inside the child are registered and created in the child; when they need a bean missing locally, the bean factory can look in the parent.

**Lifecycle:** close the child and then close the parent in reverse creation order. Closing the child **must not be assumed** to close the parent, and vice versa. The code path creating a hierarchy must take responsibility for closing every context it started.

### 2.3. Creating a Hierarchy with Spring Boot

Spring Boot offers `SpringApplicationBuilder` with `parent(...)` and `child(...)`:

~~~java
ConfigurableApplicationContext child =
    new SpringApplicationBuilder(ParentConfig.class)
        .web(WebApplicationType.NONE)
        .child(ChildConfig.class)
        .web(WebApplicationType.NONE)
        .run(args);
~~~

This snippet is an **alternative startup option** compared to manual Spring Framework construction. It requires importing `org.springframework.boot.WebApplicationType`, `org.springframework.boot.builder.SpringApplicationBuilder`, and `org.springframework.context.ConfigurableApplicationContext`, plus the two config classes defined in the complete example later. `WebApplicationType.NONE` clarifies that the example only tests containers, without opening an HTTP server. `child.getParent()` accesses the parent from the returned context.

Spring Boot imposes its own constraints when building a hierarchy: per the `SpringApplicationBuilder` documentation, web components belong in the child, and parent/child share **the same Environment** in a builder-created hierarchy. Do not arbitrarily create two web-server contexts expecting two completely independent HTTP applications; clearly establish which layer actually owns the web runtime.

## 3. Bean Visibility: Upward Lookup, Not Downward Lookup

Suppose parent registers bean `sharedClock`, and child registers bean `orderService`.

~~~text
Parent:
    sharedClock
Child:
    orderService(sharedClock)
~~~

When creating `orderService`, the child can inject `sharedClock` owned by the parent. However, if a bean in the parent needs `orderService` which exists only in the child, standard autowiring in the parent will not find that bean.

Therefore, typically place shared components that do not depend on child-specific logic into the parent: shared configs, centrally managed infrastructure clients, policies not referencing child business code. Place controllers, handlers, or module-specific features in the child. The parent should not take reverse constructor dependencies onto specific children; that design breaks layering and usually fails with `NoSuchBeanDefinitionException` or `UnsatisfiedDependencyException` when the parent starts.

### 3.1. Lookup by Name

- `child.getBean("sharedClock")`: if no local definition exists, Spring searches the parent; the returned instance is still the parent's bean.
- `child.containsBean("sharedClock")`: can be `true` even though the child does not own the bean.
- `child.containsLocalBean("sharedClock")`: `false` when only the parent declares the bean.
- `parent.containsBean("orderService")`: `false` if the bean exists only in the child.
- `child.getBeanDefinitionNames()`: used to inspect **local** definitions registered in the child; does not automatically list all ancestor definitions.

The two APIs `containsBean` and `containsLocalBean` are designed to answer different questions. Mixing them up easily causes admin dashboards or config-inspection logic to misreport ownership.

### 3.2. Same Bean Name: Child Shadows Parent's Bean

For example, parent has:

~~~java
@Bean("policy")
String parentPolicy() {
    return "parent-policy";
}
~~~

Child has:

~~~java
@Bean("policy")
String childPolicy() {
    return "child-policy";
}
~~~

These are **two bean definitions in two different BeanFactories**:

- `parent.getBean("policy", String.class)` returns `"parent-policy"`;
- `child.getBean("policy", String.class)` returns `"child-policy"`;
- the `policy` bean in the parent is not deleted or altered;
- a child on another branch is not affected by the local policy of the current branch.

The accurate concept is **lookup-level shadowing**, not overriding the same definition inside one registry. Spring Boot's `spring.main.allow-bean-definition-overriding=false` flag controls overriding definitions inside the same bean factory; it does not forbid a parent and child from having the same bean name. If a local definition named `policy` has a different type from what the caller requests, Spring does not necessarily "ignore the wrong-typed local bean to fall back to the parent"; you may get a type error because the local name already shadows the parent's name.

### 3.3. Lookup by Type Is More Nuanced Than by Name

When selecting beans by type across a hierarchy, pay attention to how candidate-listing APIs behave:

- `child.getBeansOfType(Service.class)` from `ListableBeanFactory` mainly lists beans **defined by the current bean factory**, not the full list across all ancestors.
- `BeanFactoryUtils.beansOfTypeIncludingAncestors(child, Service.class)` is the specialized API for retrieving beans from both the child and its ancestors.
- `BeanFactoryUtils.beanNamesForTypeIncludingAncestors(...)` applies deduplication rules: a bean at a lower level shadows a same-named bean at a higher level, **even if their types differ**.
- Injection by type can see eligible candidates from the parent; if multiple matching candidates exist across levels, `@Qualifier`, `@Primary`, or candidate-selection rules still apply. Do not assume "a child bean always wins by type" in every configuration.

Example: parent has a `PaymentGateway` named `globalGateway` and child has a `PaymentGateway` named `tenantGateway`. Two differently named beans can still become two candidates for a `PaymentGateway` injection point; use qualifiers to state intent explicitly. If the child declares **the same name** `globalGateway`, the local bean shadows the parent on that name-based lookup path.

## 4. Ownership Scope: Who Creates, Who Holds the Singleton, Who Destroys?

The **bean owner** is the bean factory/context that registered and manages the bean definition (or the instance registered with that container), not whichever caller first invokes `getBean(...)`.

| Activity | Bean declared in parent | Bean declared in child |
| --- | --- | --- |
| Bean definition | Parent's registry | Child's registry |
| Regular singleton creation | Parent bean factory | Child bean factory |
| Lookup from child | Child can receive bean created by parent | Receives local bean |
| BeanPostProcessor / lifecycle | Processing pipeline of the owning context | Processing pipeline of the owning context |
| Singleton cache | Parent's cache | Child's cache |
| Closing the owning context | Parent manages destroying singletons it created | Child manages destroying singletons it created |
| Does ownership transfer when injected across contexts? | No | No |

### Singleton Means "One Instance Per Container"

`@Scope("singleton")` is the default scope; **a singleton in Spring is scoped per container**, not by default a single unique object across the entire JVM.

- If the parent defines `sharedClient` once and two children both inject it: normally both receive **the exact same instance** from the parent.
- If parent and child both register their own `sharedClient` bean (or two different names of the same class), each container can create its own instance; that is not a bug in singleton scope.
- If a context has `prototype` scope, each retrieval per the rules can create a new instance; Spring does not automatically manage full prototype destruction the way it does for singletons.
- Scopes such as `request`/`session` require a web-aware context and an active request context; merely having a hierarchy does not enable those scopes.

Do not confuse "shared bean" with "thread-safe bean." A singleton placed in the parent can be shared concurrently across multiple requests or child contexts, so clients, caches, and mutable state must be designed safely for their actual level of sharing.

### Lifecycle and Shutdown

When a child calls `getBean("sharedClient")` to get a parent bean, the child **does not** become the owner of that bean. Closing the child should not automatically close a client still used by other children via the parent. When shutting down the entire hierarchy, close the children first, wait for dependent work to finish, and only then close the parent. If you close the parent while a child still uses a bean from the parent, the system can fail attempting to use destroyed resources.

Use `@PreDestroy`, `DisposableBean`, or appropriate destroy methods on resources that the context actually manages. Plain Java references passed into a child do not grant extra shutdown authority over a parent bean.

## 5. Runnable Java 17+ Example: Creating Two Contexts, Looking Up, and Verifying Ownership

This example uses Spring Framework APIs included in the Spring Boot Starter dependency. It creates a parent and child using two real bean factories, needing no HTTP server or database. Choose Java 17+ and a Spring Boot Starter Maven project; assume artifact `context-hierarchy-demo`, package `com.example.hierarchy`.

**File `src/main/java/com/example/hierarchy/ContextHierarchyDemo.java`:**

~~~java
package com.example.hierarchy;

import org.springframework.beans.factory.BeanFactoryUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ContextHierarchyDemo {

    static final class SharedClock {
    }

    static final class ChildHandler {
        final SharedClock clock;

        ChildHandler(SharedClock clock) {
            this.clock = clock;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ParentConfig {

        @Bean("policy")
        public String parentPolicy() {
            return "parent-policy";
        }

        @Bean("sharedClock")
        public SharedClock sharedClock() {
            return new SharedClock();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ChildConfig {

        @Bean("policy")
        public String childPolicy() {
            return "child-policy";
        }

        @Bean("childHandler")
        public ChildHandler childHandler(SharedClock sharedClock) {
            return new ChildHandler(sharedClock);
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext parent =
                new AnnotationConfigApplicationContext(ParentConfig.class);

        AnnotationConfigApplicationContext child =
                new AnnotationConfigApplicationContext();
        child.setParent(parent);
        child.register(ChildConfig.class);
        child.refresh();

        try {
            System.out.println("parent.policy="
                    + parent.getBean("policy", String.class));
            System.out.println("child.policy="
                    + child.getBean("policy", String.class));

            System.out.println("child.seesSharedClock="
                    + child.containsBean("sharedClock"));
            System.out.println("child.ownsSharedClock="
                    + child.containsLocalBean("sharedClock"));
            System.out.println("parent.seesChildHandler="
                    + parent.containsBean("childHandler"));

            Object fromParent = parent.getBean("sharedClock");
            Object fromChild = child.getBean("sharedClock");
            System.out.println("sameSharedClock="
                    + (fromParent == fromChild));

            ChildHandler handler = child.getBean(ChildHandler.class);
            System.out.println("handlerUsesParentClock="
                    + (handler.clock == fromParent));

            System.out.println("child.localClockCount="
                    + child.getBeansOfType(SharedClock.class).size());
            System.out.println("child.hierarchyClockCount="
                    + BeanFactoryUtils.beansOfTypeIncludingAncestors(
                            child, SharedClock.class).size());
        } finally {
            child.close();
            parent.close();
        }
    }
}
~~~

**How to run:** create a Maven Spring Boot project with Spring Initializr and the `Spring Boot Starter` dependency; use package `com.example.hierarchy`, artifact `context-hierarchy-demo`, keep `pom.xml` with the Spring Boot Maven Plugin, and place the class above at the matching path. Run from the project directory:

~~~bash
mvn -q -DskipTests package
java -jar target/context-hierarchy-demo-0.0.1-SNAPSHOT.jar
~~~

The JAR name depends on `artifactId` and `version` in `pom.xml`. The command above assumes the example's default version `0.0.1-SNAPSHOT`. If you choose another version, adjust the artifact name accordingly.

**Lines printed by the program:**

~~~text
parent.policy=parent-policy
child.policy=child-policy
child.seesSharedClock=true
child.ownsSharedClock=false
parent.seesChildHandler=false
sameSharedClock=true
handlerUsesParentClock=true
child.localClockCount=0
child.hierarchyClockCount=1
~~~

Each line demonstrates a rule:

1. `parent.policy` and `child.policy` differ despite having the same bean name: child shadows parent on lookups starting in the child.
2. Child sees `sharedClock`, yet `containsLocalBean` is `false`: visibility does not equal ownership.
3. Parent does not see `childHandler`: visibility direction is asymmetric.
4. `sameSharedClock=true` proves the parent bean is not copied when accessed by the child.
5. `handlerUsesParentClock=true` proves a bean **created by the child** receives a bean **created by the parent**.
6. `getBeansOfType` on the child returns only local Clocks (0), while `BeanFactoryUtils.beansOfTypeIncludingAncestors` includes the parent (1).

Because the application only runs `AnnotationConfigApplicationContext` and does not start a Spring Boot web server, output consists primarily of the lines above; adding loggers or dependencies may produce extra logs, yet the assertion lines stay unchanged when keeping the example source/config intact.

**Why doesn't the example place `@SpringBootApplication` on `ContextHierarchyDemo`?** The lesson intentionally registers `ParentConfig` and `ChildConfig` separately in two contexts. `@SpringBootApplication` enables component scanning; scanning both configurations into **the same context** would turn the example into a bean-name conflict and defeat the parent–child demonstration.

## 6. When Deploying with SpringApplicationBuilder

In Spring Boot, the fluent API lets you configure a context hierarchy without manually calling `register(...)` and `refresh()`. The example below reuses `ParentConfig` and `ChildConfig` from section 5; required imports:

~~~java
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
~~~

Replace the context-creation section inside `main` with:

~~~java
ConfigurableApplicationContext child =
        new SpringApplicationBuilder(ContextHierarchyDemo.ParentConfig.class)
                .web(WebApplicationType.NONE)
                .child(ContextHierarchyDemo.ChildConfig.class)
                .web(WebApplicationType.NONE)
                .run(args);

ConfigurableApplicationContext parent =
        (ConfigurableApplicationContext) child.getParent();

try {
    System.out.println(child.getBean("policy"));
    System.out.println(parent.getBean("policy"));
} finally {
    child.close();
    parent.close();
}
~~~

This is a **replacement snippet** for the context-building block in the example; do not run both hierarchy-creation blocks together. The two `println` calls output `child-policy` and `parent-policy` respectively for the given configuration. Spring MVC or Servlet is not required for this plain container example. For a real Boot application with a web stack, carefully check `SpringApplicationBuilder` constraints regarding web contexts in the child tier and how parent/child share `Environment`.

### Distinguishing Context Configuration from Process Isolation

A hierarchy built inside **the same JVM** does not create isolation equivalent to microservices, OS containers, or a security sandbox. Parent beans can become shared resources across children. Each child has its own registry, yet normally shares the same heap, process, classloader, and certain infrastructure dependencies. Do not place one tenant's secrets in a parent singleton and assume other children cannot reference it.

## 7. Bean Names, Configuration Conditions, and Component Scanning in a Hierarchy

### 7.1. Child Shadowing Differs from Bean Overriding

| Case | Policy / phenomenon | What happens |
| --- | --- | --- |
| Parent has bean `policy` and child also has `policy` | Cross-context shadowing | `child.getBean("policy")` uses local; parent remains untouched |
| Two `@Bean("policy")` registered in **the same** bean factory | Bean definition overriding | With Spring Boot blocking overriding by default, `BeanDefinitionOverrideException` may occur |
| Parent has type `Gateway`, child has type `Gateway` with a different name | Multiple candidates by type | May require qualifiers or a bean-selection policy |
| Child has a bean with the same name but a different type from parent | Shadowing still operates by **name** | No guarantee of falling back to parent when caller requests the parent's type |
| Parent only has `sharedClock`, child does not | Lookup inheritance, not definition inheritance | Child uses the instance owned by parent |

If you want to swap implementations per child, give local beans meaningful names and test lookup paths. Reusing the exact same bean name is supported by Spring, yet easily causes confusion while debugging. When multiple implementations have different names, `@Qualifier` or `@Primary` may fit; they are not tools to make two identically named beans distinct inside one lookup scope.

### 7.2. Scope of Auto-Configuration Conditions

In Spring Boot, `@ConditionalOnMissingBean` has a `search` attribute with `SearchStrategy`:

- `ALL`: checks both the current context and ancestors; this is the default of this condition per Boot's API.
- `CURRENT`: checks only the current context.
- `ANCESTORS`: checks only ancestors, excluding the current context.

**Illustrative** configuration example, placed in an auto-configuration with valid processing order:

~~~java
@ConditionalOnMissingBean(
        value = SharedClock.class,
        search = SearchStrategy.CURRENT)
@Bean
SharedClock localClock() {
    return new SharedClock();
}
~~~

This snippet requires importing `ConditionalOnMissingBean` and `SearchStrategy` from `org.springframework.boot.autoconfigure.condition` plus `@Bean`. If the parent has a `SharedClock` while the child does not yet have a local one, searching **CURRENT** can still match and create an additional clock belonging to the child. Conversely, the **ALL** strategy sees the parent's clock before evaluating missing-bean conditionality.

This is a concrete illustration showing that **a bean visible from an ancestor** and **a bean existing in the current registry** are two different things. `@ConditionalOnMissingBean` depends on bean definitions already processed at evaluation time; per Boot documentation, it is meant for auto-configuration and should not be placed arbitrarily on peer configurations assuming an immutable bean-creation order.

### 7.3. Scanning Components at the Right Layer

A common mistake is configuring an overly broad `@ComponentScan("com.example")` in the parent, causing controllers and services intended for the child to be registered **in the parent**. When that happens:

- The parent instantiates beans that should exist only in the child.
- The child may also scan them and create duplicate instances.
- Beans with supposedly isolated state end up sharing state via the parent, or hit scope conflicts.
- A child-module bean can create unexpected dependency cycles when loaded in the parent context.

Assign **configuration sources** and base packages intentionally for each tier; shared configs are created once in the parent, while module-specific components go into the appropriate child. You can audit `getBeanDefinitionNames()`, `containsLocalBean(...)`, and instance identities to verify.

## 8. Events and Environment: Special Aspects of a Hierarchy

### Application Events Propagate Up to Ancestors

Events published via `ApplicationEventPublisher` from a child normally propagate up to ancestor contexts. Consequently, a listener registered in the parent **can** receive events published by a child. The reverse is not automatically symmetric: publishing an event in the parent does not guarantee listeners registered only in a child will be called.

In particular, Spring Boot may publish startup events for multiple `SpringApplication` instances in a hierarchy; a parent listener can see events from both the parent itself and children. If you only want to handle events from the current context, compare the event's source context with the listener's own context before processing:

~~~java
if (event.getApplicationContext() != myContext) {
    return;
}
~~~

This snippet applies to events with a suitable `getApplicationContext()` API, such as certain `SpringApplicationEvent`/`ApplicationContextEvent` types, not every arbitrary event. `myContext` is the listener's owning context supplied via injection or an appropriate callback.

**Note:** "a listener receives events from a child" does **not** mean the parent can call `getBean(...)` on the child. Event propagation and bean lookup are two independent APIs.

### Configuration and Environment

In a Spring Boot `SpringApplicationBuilder` hierarchy, the documentation specifies that parent and child share the same `Environment`. Thus properties like `server.port` or active profiles do not automatically create isolated namespaces per child. Distinct bean registries do not imply each child receives isolated configuration.

If you need per-child-group configuration, design it explicitly: distinct property prefixes, dedicated config sources, or an appropriate context setup model; verify how properties bind into each bean at context creation time. Do not assume "same key in a child automatically overrides the parent environment" the way bean-name shadowing works.

## 9. When Should You Use Parent–Child Contexts?

A hierarchy is useful when an application has a **shared foundational layer** and **child contexts with distinct lifecycles/functions**:

- One parent provides centrally managed resource pools or clients; multiple children handle separate workloads.
- Plugin/module applications where modules need isolated registries to reduce component-scan collisions and enable/disable modules cleanly.
- Certain traditional web architectures with a root `WebApplicationContext` and a child context per `DispatcherServlet`; handlers/controllers belong to children while shared services/repositories live in root.

However, a hierarchy increases complexity when diagnosing bean lookups, bean lifecycles, event propagation, and configuration. For typical Spring Boot applications, **a single ApplicationContext**, clean dependency injection, sensible packages/modules, and appropriate conditions are usually easier to operate. Choose a hierarchy when you genuinely need lifecycle or registry boundaries, not merely because a project has multiple packages.

### Do Not Use a Hierarchy as Tenant Security

Parent–child contexts do not provide information-access authorization. If children serve different tenants, any shared parent bean holding credentials, caches, or mutable state must have its scope carefully audited. Apply proper authorization, resource isolation, and dedicated data design rather than expecting a BeanFactory to replace data-security policies.

## 10. Failures and Diagnostic Steps

### "Bean exists in parent, yet @Autowired in child cannot find it"

1. Confirm the child **actually had its parent set** before `refresh()`.
2. Confirm the parent has already been refreshed and the expected bean exists in the parent registry.
3. Check name, type, qualifiers, generic types, profiles, registration conditions, and whether the bean is an autowire candidate.
4. Distinguish lookup by name from lookup by type; a same-named local bean can shadow the parent bean.
5. If multiple candidates match by type, check `@Qualifier`/`@Primary` and the injection point.

Do not "fix" it by randomly registering a duplicate bean in the child before verifying ownership; that can accidentally spin up two separate clients or two transaction managers.

### "Parent service needs a child bean, so startup fails"

The parent does not look downward into children. If a shared service must invoke per-child logic, consider inverting the dependency, pushing orchestration down into the child, introducing a child-agnostic abstraction in the parent, or defining an explicit lifecycle-managed registration/dispatch mechanism. Do not try to make the parent inject child beans via sweeping component scans, as that breaks context boundaries.

### "No duplicate-bean error, yet child receives a different implementation than expected"

Check for colliding bean names between parent and child. `child.getBean("policy")` prefers local; if the child registers `policy`, the same-named parent bean is shadowed in that lookup. Inspect `containsLocalBean` and the child's bean definition registry before concluding the parent bean was overwritten.

### "Closing a module causes the shared client to close or leak"

Identify where the bean was created and who invokes lifecycle cleanup. If the shared client belongs to the parent, children must not call `close()` on it themselves. If a resource only serves one child, do not register it in the parent and create mismatched lifecycle ownership. Close children before the parent; audit listeners, schedulers, connection pools, and `@PreDestroy`/destroy callbacks.

### "Child A sees Child B's bean"

If you are seeing the same name/type across children, the bean may actually reside in the parent, both contexts may be scanning the same configuration, or code may be passing direct object references between modules. Two contexts sharing a parent do not automatically look up across siblings. Inspect the actual hierarchy and local bean definitions at each tier.

### "`getBeansOfType()` returns an incomplete list, while `getBean()` succeeds"

`ListableBeanFactory.getBeansOfType` and `getBean(name)` lookup have different visibility scopes in a hierarchy. If you need to inventory all candidates including ancestors, use `BeanFactoryUtils.beansOfTypeIncludingAncestors`. Remember that when parent and child share a name, the local bean shadows the ancestor bean in this utility.

### "Parent listener receives an event twice"

Check that each context publishes its own events, plus child events propagate upward to the parent. For context-aware events, filter using `getApplicationContext()` or an appropriate identifier. Do not assume a bean listener only receives events from its owning context.

## 11. Implementation and Testing Rules

When using a hierarchy, a small, targeted test suite should verify:

1. Child injects parent beans and receives **the exact same instance**.
2. Parent cannot inject/find beans registered solely in a child.
3. Two children can share a parent bean without directly reading each other's local beans.
4. Beans with the same name in parent and child resolve as intended in each context, with no unintended bean collisions.
5. `getBeansOfType` is used only when a local view is wanted; ancestor utilities are used when a hierarchy view is needed.
6. Closing one child leaves parent resources usable by other children; during full shutdown, children close before the parent.
7. Component scans/configuration sources register beans only into their intended tiers.
8. If using Boot auto-configuration, `@ConditionalOnMissingBean(search=...)` checks the intended level.
9. If using web or events, additionally verify web-context hierarchy limits and event propagation.

You do not need to introduce an entire hierarchy into an application just to test logical layering. When separate lifecycles or registries are unnecessary, modular Java code inside a single context is usually enough.

## 12. Self-Check Questions

**Question 1.** Parent has bean `clock`; child does not declare `clock`. What do `child.containsBean("clock")` and `child.containsLocalBean("clock")` return?  
**Answer:** typically `true` and `false`: visible via the parent, yet not owned locally.

**Question 2.** Both parent and child have a bean named `formatter`. When child calls `getBean("formatter")`, is the parent bean destroyed?  
**Answer:** child typically receives its local bean; the parent bean still exists and belongs to the parent.

**Question 3.** Two sibling contexts share a parent. Can Child A automatically inject a bean registered only in Child B?  
**Answer:** no. Both children look up to the parent; there is no default horizontal sibling lookup.

**Question 4.** A parent singleton is injected by two children—are there three distinct singletons?  
**Answer:** no. If both children access the bean via the parent, they normally share **one instance owned by the parent**.

**Question 5.** Why can `child.getBeansOfType(Clock.class)` return an empty map while `child.getBean("sharedClock")` succeeds?  
**Answer:** listing by type on the local bean factory differs from name lookup, which can delegate up to the parent.

**Question 6.** If parent and child register the same bean name, must you enable `spring.main.allow-bean-definition-overriding=true`?  
**Answer:** not merely because of identical names in **two different bean factories**; that is cross-context shadowing, not overriding inside the same registry.

**Question 7.** Does closing a child by default close a shared parent singleton?  
**Answer:** closing a child must not be treated as closing the parent. Shutdown sequence and ownership must be managed separately.

**Question 8.** Does a parent listener receiving an event published by a child prove the parent can see child beans?  
**Answer:** no. Event propagation travels upward; bean lookup does not travel downward.

## Official Documentation

- [Spring Boot — SpringApplication / Fluent Builder API](https://docs.spring.io/spring-boot/reference/features/spring-application.html): `SpringApplicationBuilder`, parent/child, web context limits, shared Environment, and events.
- [Spring Framework — BeanFactoryUtils API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/BeanFactoryUtils.html): ancestor-aware lookups and duplicate-name rules.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): container-scoped `singleton` and other scopes.
- [Spring Framework — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html): post-processor scoping and annotation configuration.
- [Spring Framework — Bean Definition Inheritance](https://docs.spring.io/spring-framework/reference/core/beans/child-bean-definitions.html): distinguishing it from parent/child ApplicationContexts.
- [Spring Boot — ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): the `search` attribute.
- [Spring Boot — SearchStrategy API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/SearchStrategy.html): `ALL`, `CURRENT`, `ANCESTORS`.