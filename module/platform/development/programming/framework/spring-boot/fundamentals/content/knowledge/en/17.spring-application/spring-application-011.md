# Context Hierarchies When an Application Has Multiple Contexts

A Spring application does not necessarily have only one `ApplicationContext`. In architectures with multiple configuration zones or multiple web entry points, contexts can be organized in a **parent–child** relationship. The parent context typically holds shared beans; child contexts hold beans belonging only to a specific web application, servlet, or module.

The key rule of a hierarchy is **bean visibility direction**:

- A child context can look up beans registered inside itself.
- If no matching bean is found locally, lookup can continue up to the parent context.
- The parent context does not look down into child contexts.
- Sibling contexts do not automatically see each other's beans.

Each context remains a distinct container with its own bean registry, singleton cache, and lifecycle. A parent–child hierarchy shares dependencies in one direction; it does not merge all beans into a single shared registry.

## 1. What Is an ApplicationContext?

`ApplicationContext` is Spring's high-level container. It manages bean definitions, creates and wires beans, provides resource loading, event publishing, environment access, and other core services.

A typical Spring Boot application creates a single application context during:

~~~java
@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

In most straightforward web applications, one context suffices. However, when separate configuration regions are required, multiple contexts can be created and linked as a tree:

~~~text
                 Parent ApplicationContext
                      (shared beans)
                           |
               +-----------+-----------+
               |                       |
               v                       v
       Child Context A          Child Context B
       (API / servlet A)        (API / servlet B)
~~~

The parent provides foundational beans usable by both children. Child A and Child B cannot directly see each other's private beans.

## 2. Why Would You Need a Context Hierarchy?

Several architectural reasons can make multiple contexts useful:

- **Sharing beans across multiple web applications/servlets:** shared services and repositories live in the parent, while controllers, handlers, or view resolvers live in children.
- **Separating configuration by entry point:** each servlet or web area maintains its own mappings, interceptors, and controllers.
- **Isolating modules with independent lifecycles:** a group of beans can be created/closed with a child context while still consuming shared services from the parent.
- **Separating configuration responsibilities:** the parent manages shared infrastructure while children manage area-specific settings.

For example, an internal application with two web entry points:

~~~text
Parent context
  ├── UserService
  ├── OrderRepository
  ├── DataSource
  └── SharedClock

Child context: /admin/*
  ├── AdminController
  └── AdminWebConfiguration

Child context: /partner/*
  ├── PartnerController
  └── PartnerWebConfiguration
~~~

Both children can use `UserService` and `OrderRepository` from the parent. Yet admin web configuration and controllers do not automatically appear inside the partner child context.

Hierarchies carry extra cost in configuration, bean inspection, and lifecycle management. Do not create multiple contexts just to separate packages or layers in an ordinary application.

## 3. Bean Lookup Rules Between Parent and Child

Bean lookup in a hierarchy follows **local first, parent second**:

1. The current container searches for the bean in its own registry.
2. If no matching bean is found, it can delegate lookup up to its parent.
3. Traversal can continue upward through ancestor levels in multi-level hierarchies.
4. There is no downward lookup from parent to child.

Diagram:

~~~text
Child.getBean("sharedClock")
           |
           v
  Does Child have local bean?
       /          \
     Yes           No
     |               |
     v               v
Return local    Ask Parent
                    |
                    v
             Does Parent have bean?
                /      \
              Yes       No
              |           |
              v           v
         Return bean   Throw not found
~~~

### 3.1. A child can use beans from its parent

Spring Framework example:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ParentConfiguration {

    @Bean
    Clock sharedClock() {
        return Clock.systemUTC();
    }
}
~~~

The child declares a service needing that bean:

~~~java
@Configuration(proxyBeanMethods = false)
class ChildConfiguration {

    @Bean
    ReportService reportService(Clock sharedClock) {
        return new ReportService(sharedClock);
    }
}
~~~

When `ChildConfiguration` is loaded into a child context whose parent contains `Clock`, Spring resolves the `Clock` dependency from the parent context.

### 3.2. The parent cannot use beans that exist only in a child

Suppose the child registers `AdminController`. Calling:

~~~java
parentContext.getBean(AdminController.class);
~~~

will not find that bean if it was registered solely in the child. The parent never searches child contexts.

This rule prevents the parent from depending backward on child implementation details. If a parent needs functionality provided by a child, dependency boundaries may be inverted; move the shared abstraction or bean up to an appropriate module/context.

## 4. Beans with the Same Name in Child and Parent

A child can declare a bean with the same name as one in the parent. When looking up from the child, the local bean takes precedence and shadows the parent's bean within the child's scope:

~~~java
@Configuration(proxyBeanMethods = false)
class ParentConfiguration {
    @Bean
    String greeting() {
        return "Hello from parent";
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
class ChildConfiguration {
    @Bean
    String greeting() {
        return "Hello from child";
    }
}
~~~

Lookup results:

| Lookup Origin | Returned Value |
|---|---|
| Parent context | `Hello from parent` |
| Child context | `Hello from child` |

The child does not alter the bean definition or instance inside the parent. It merely holds a local bean with the same name, causing lookups from the child to prefer the local bean.

In real applications, avoid reusing the same name for beans with different meanings unless intentionally designed. Shadowing makes it harder for readers to tell which level supplies a dependency. If you want to customize a shared bean for all children, configure it in the parent or design a clean abstraction.

### 4.1. Lookup by type and multiple candidates

When resolving by type, a child can use a bean from the parent if no local candidate matches. When multiple candidates of the same type exist across a hierarchy, dependency resolution also depends on qualifiers, `@Primary`, and Spring autowiring rules.

In particular, bean listing APIs differ in local vs. ancestor semantics. For instance, `getBeanNamesForType` on a bean factory focuses on its own registry, whereas `BeanFactoryUtils.beansOfTypeIncludingAncestors(...)` is designed to include ancestors. When aggregating beans across multiple levels, pick an API with the intended semantics and test against a real context.

Do not assume every collection injection in a child automatically receives the exact combined list of beans across the whole hierarchy. If a pipeline needs all handlers from both parent and child, define the aggregation and ordering rules explicitly.

## 5. Each Context Has Its Own Bean Registry and Singletons

Two independent contexts can declare a bean of the same class while creating separate instances:

~~~java
@Configuration(proxyBeanMethods = false)
class SharedConfiguration {
    @Bean
    SharedClock sharedClock() {
        return new SharedClock();
    }
}
~~~

If `SharedConfiguration` is loaded in both parent and child, each context creates its own `SharedClock` singleton. Singleton scope means one instance per bean definition **per container**, not one instance across the entire JVM.

In a hierarchy, if the child does not declare a local bean and resolves from the parent, the child shares the instance managed by the parent. If the child re-declares the bean, it gets its own separate instance.

~~~text
Parent context
  sharedClock bean definition
          |
          v
  SharedClock instance P

Child context
  sharedClock bean definition (if declared locally)
          |
          v
  SharedClock instance C
~~~

The same holds for other scopes. Prototype instances are created per resolution in the context owning the bean definition; web scopes depend on the appropriate context and web scope environment.

## 6. BeanPostProcessors and Configuration Do Not Propagate Automatically Across Contexts

Each application context runs its own bean registration and processing pipeline. A `BeanPostProcessor` registered in a child processes only beans created by that child; it does not retroactively process instances already created in the parent. Conversely, a parent's processor does not automatically become a processor for a child just because the child links to that parent.

This matters for:

- Annotation processing and AOP proxies.
- Processors handling dependency injection.
- Bean validation or other `BeanPostProcessor`-based integrations.
- Custom library processors.

For example, if the parent creates a singleton service before the child is initialized, a `BeanPostProcessor` registered only in the child cannot apply proxies or callbacks to that service.

If a shared bean requires AOP, transactions, or annotation processing, place the necessary configuration and processors in **the context that owns that bean**. Do not assume declaring `@EnableTransactionManagement` or a processor in a child affects beans in the parent.

Likewise, a `@Configuration` loaded in the parent is not automatically re-processed in the child. For a child to have its own configuration, register it in the child or import it through child configuration.

## 7. Lifecycle of Parent and Child

Each context has an independent lifecycle:

- Contexts are created and refreshed separately.
- A context's singletons are instantiated according to that context's dependency/lazy policy.
- Initialization callbacks run while creating beans belonging to the respective context.
- Contexts can be closed independently; singletons managed by that context go through destruction lifecycle callbacks.

A child depending on parent beans should be closed before the parent. If the parent closes while the child is still actively using parent beans, the child's dependencies may stop working properly.

Typical management sequence:

~~~text
1. Create Parent context
2. Refresh Parent context
3. Create Child context, attach Parent
4. Refresh Child context
5. Use the application
6. Close Child context
7. Close Parent context
~~~

When using `SpringApplicationBuilder`, Spring Boot manages constructing the hierarchy. If an application builds contexts manually via Spring Framework APIs, your code is responsible for refreshing and closing each context properly.

### 7.1. Closing a child does not close the parent

The two contexts have separate lifecycles. When a child closes, beans owned by that child are destroyed according to the child's lifecycle. The parent remains alive until closed separately or shut down by a higher-level coordinator.

When stopping the whole application, ensure the entire hierarchy closes in the right order. For contexts managed by `SpringApplicationBuilder`, let the builder/application lifecycle handle shutdown through supported mechanisms instead of arbitrarily closing one context mid-flight.

### 7.2. Prototypes still follow separate destruction rules

Hierarchies do not change scope rules. Spring does not invoke destruction callbacks on prototype instances after handing them to clients, whether requested from a parent or child. Whoever creates/consumes a prototype remains responsible for releasing that instance's resources.

## 8. Building a Context Hierarchy with SpringApplicationBuilder

Spring Boot provides `SpringApplicationBuilder` to assemble parent–child relationships conveniently:

~~~java
import org.springframework.boot.builder.SpringApplicationBuilder;

public class MultiContextApplication {

    public static void main(String[] args) {
        new SpringApplicationBuilder(SharedInfrastructureConfiguration.class)
                .child(ApiConfiguration.class)
                .run(args);
    }
}
~~~

In this example:

- `SharedInfrastructureConfiguration` is the configuration source for the parent context.
- `ApiConfiguration` is the configuration source for the child context.
- `run(args)` launches the hierarchy defined by the builder.

This illustrates combining configuration sources; the classes must carry proper configuration annotations and provide required dependencies.

### 8.1. Explicitly declaring parent and child

You can write:

~~~java
new SpringApplicationBuilder()
        .parent(SharedInfrastructureConfiguration.class)
        .child(AdminConfiguration.class)
        .run(args);
~~~

`parent(...)` adds sources to the parent application; `child(...)` creates a child application with its own sources. The builder also supports siblings for creating multiple child contexts under the same parent.

### 8.2. One parent with multiple children

~~~java
new SpringApplicationBuilder()
        .parent(SharedInfrastructureConfiguration.class)
        .child(AdminConfiguration.class)
        .sibling(PartnerConfiguration.class)
        .run(args);
~~~

Model:

~~~text
SharedInfrastructureConfiguration
              |
        Parent context
          /       \
         /         \
        v           v
  Admin child   Partner child
~~~

Both children can use beans from the parent, yet cannot directly see each other's local beans.

`SpringApplicationBuilder` can configure the web application type for each application in the hierarchy via the corresponding builder API. When using multiple web contexts, clearly specify which context is servlet/reactive/non-web, along with servlet mappings and server lifecycles. Do not copy one context's web configuration into another needlessly.

## 9. Building a Hierarchy Manually with AnnotationConfigApplicationContext

To see the parent–child mechanics clearly without the Boot builder, you can create two contexts using Spring Framework:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

AnnotationConfigApplicationContext parent =
        new AnnotationConfigApplicationContext();
parent.register(ParentConfiguration.class);
parent.refresh();

AnnotationConfigApplicationContext child =
        new AnnotationConfigApplicationContext();
child.setParent(parent);
child.register(ChildConfiguration.class);
child.refresh();

try {
    ReportService service = child.getBean(ReportService.class);
    service.generate();

    Clock clock = child.getBean(Clock.class);
    System.out.println(clock.instant());
} finally {
    child.close();
    parent.close();
}
~~~

In this example:

- Parent registers `Clock`.
- Child registers `ReportService`, which requires `Clock`.
- Child can inject `Clock` from parent.
- Parent cannot retrieve `ReportService` from child.
- Child is closed before parent.

When using the manual API, call `refresh()` after registering configurations and attaching the parent. If you register sources after the context has already refreshed, do not expect bean definitions to be processed like a normal bootstrap.

## 10. Root Context and DispatcherServlet Child Context Pattern

In traditional Spring MVC configurations (prior to widespread Spring Boot auto-configuration), a web application commonly had:

- **Root WebApplicationContext:** holding services, repositories, datasources, and shared beans.
- **DispatcherServlet WebApplicationContext:** holding controllers, handler mappings, view resolvers, and servlet-specific web configuration.

Model:

~~~text
Servlet container
       |
       v
Root WebApplicationContext
  ├── Services
  ├── Repositories
  └── DataSource
       |
       v
DispatcherServlet
       |
       v
Child WebApplicationContext
  ├── Controllers
  ├── HandlerMappings
  └── ViewResolvers
~~~

The DispatcherServlet's child context can consume services in the root context. The root context does not depend on controllers inside the child. This split allows multiple DispatcherServlets to share core infrastructure while keeping separate web configurations.

### 10.1. Does Spring Boot create this hierarchy automatically?

A standard Spring Boot web application normally runs with **a single application context** holding both web infrastructure and application beans. Boot does not automatically split into a root context and a separate DispatcherServlet child context just because the app uses Spring MVC.

A hierarchy appears only when the application or framework configures it explicitly—such as via multiple `SpringApplication` instances, `SpringApplicationBuilder`, or specialized web integrations.

Therefore, do not create parent–child contexts out of traditional Spring MVC habit if your Boot application has only one web server and one set of controllers.

## 11. Component Scanning Within Each Context

Each context has its own scan configuration. If both parent and child scan the same broad package, components can be registered in both contexts, producing two independent instances.

Example to avoid:

~~~java
@Configuration
@ComponentScan("com.example")
class ParentConfiguration {
}
~~~

~~~java
@Configuration
@ComponentScan("com.example")
class ChildConfiguration {
}
~~~

If both scan the entire package, services appear in both parent and child. When the child looks up a local bean, the local bean shadows the parent's bean, making it hard to predict which instance is used.

Narrow the scopes instead:

~~~java
@Configuration(proxyBeanMethods = false)
@ComponentScan("com.example.shared")
class ParentConfiguration {
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@ComponentScan("com.example.admin.web")
class AdminChildConfiguration {
}
~~~

The parent scans shared components; the child scans its own web components. You can also use `@Import` to register a specific configuration instead of scanning for small modules.

## 12. Environment and Properties Across Contexts

`Environment` holds property sources, active profiles, and environment metadata used to configure the application. In a hierarchy, each context can have its own Environment or be configured to share/inherit according to how the builder and application are set up.

Do not assume that:

- every property declared in a child definitely overrides the parent under the same rule in all setups;
- active profiles of parent and child are always independent;
- changing the Environment in one context automatically updates all other contexts.

When using `SpringApplicationBuilder`, check the semantics of your Boot version regarding Environment sharing between parent/child and builder customizations. If constructing contexts manually, attach the desired Environment before refreshing.

Example setting a separate Environment:

~~~java
AnnotationConfigApplicationContext child =
        new AnnotationConfigApplicationContext();

var environment = new org.springframework.core.env.StandardEnvironment();
environment.setActiveProfiles("admin");
child.setEnvironment(environment);
child.setParent(parent);
child.register(AdminConfiguration.class);
child.refresh();
~~~

This snippet illustrates a child with its own configured Environment. If you want to share property sources or profiles with the parent, configure that explicitly and test property resolution order.

## 13. Application Events in a Hierarchy

Contexts have their own event publishers. When an event is published from a child context, Spring can propagate the event up to parent contexts via `ApplicationContext` mechanics. Parents do not automatically propagate events down to children.

Example:

~~~java
child.publishEvent(new CustomApplicationEvent(child, "updated"));
~~~

Listeners in the child receive the event within its context; listeners in the parent can also receive the event propagated from the child. However, events published in the parent are not automatically broadcast down to child contexts.

Keep this in mind when the same listener or event configuration is registered across multiple contexts: the same event could be handled multiple times if listeners sit in both child and parent. Define clearly where listeners belong and prevent duplicate handling.

For lifecycle events like `ContextRefreshedEvent`, each context has its own lifecycle and publishes its own event on refresh. A listener in the parent may observe events propagated from a child, so check the event source context if logic should run only once for the root.

## 14. Hierarchy Is Neither a Security Boundary Nor Process Isolation

Parent and child run inside the same JVM, sharing memory space and usually the same application process. Splitting contexts is not a sandbox:

- A child can look up beans from the parent.
- Parent beans may hold shared credentials or clients.
- A severe JVM failure affects all contexts.
- Hierarchies provide no CPU, memory, or OS permission isolation.

If you need security isolation, independent scaling, deployment separation, or fault isolation, consider process/service boundaries, containers, or proper security mechanisms. Never use a context hierarchy as a data isolation boundary between user groups.

## 15. When to Use and When to Avoid Multiple Contexts

| Scenario | Assessment |
|---|---|
| Multiple DispatcherServlets needing separate web configs while sharing services/repositories | Can suit root/child contexts |
| Multiple web modules with distinct lifecycles and bean registries | Can suit if boundaries are clean |
| Simple Boot app with one server and one API | Usually needs only one context |
| Separating controller/service/repository packages | Component scan and package layout usually suffice |
| Supporting dev/test/prod environments | Use profiles/property sources, not multiple contexts per environment |
| Isolating security or faults across modules | Context hierarchies do not provide strong isolation |
| Running two services that deploy/scale independently | Splitting processes/services is usually better |

Every additional context adds overhead for:

- Bootstrap configuration and component scanning.
- Managing parent/child lifecycles.
- Distinguishing local vs. ancestor beans.
- Investigating logs, events, and conditions.
- Preventing duplicate beans and unintended instantiations.
- Testing configurations at each level.

Create a hierarchy only when a concrete architectural requirement cannot be expressed cleanly in a single context.

## 16. Testing Context Hierarchies

You can verify bean visibility rules using two real contexts:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Clock;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;

class ContextHierarchyTest {

    @Test
    void childCanUseParentBeanButParentCannotUseChildBean() {
        var parent = new AnnotationConfigApplicationContext(
                ParentConfiguration.class);

        var child = new AnnotationConfigApplicationContext();
        child.setParent(parent);
        child.register(ChildConfiguration.class);
        child.refresh();

        try {
            assertThat(child.getBean(Clock.class)).isNotNull();
            assertThat(child.getBean(ReportService.class)).isNotNull();

            assertThrows(
                    NoSuchBeanDefinitionException.class,
                    () -> parent.getBean(ReportService.class)
            );
        } finally {
            child.close();
            parent.close();
        }
    }
}
~~~

This example assumes `ParentConfiguration` registers `Clock` and `ChildConfiguration` registers `ReportService` requiring `Clock`. You can expand the tests to verify:

- Whether a same-named bean in the child shadows the parent's bean during child lookup.
- Whether two contexts create separate singleton instances when declaring the same type.
- That a `BeanPostProcessor` in the child does not process beans already created in the parent.
- Whether events from the child reach parent listeners as expected.
- That closing the child before the parent leaks no resources.
- That component scanning does not register duplicate components at both levels.

### 16.1. Testing Spring Boot builder

For Boot applications, you can test hierarchies built with `SpringApplicationBuilder` and assert:

~~~java
ConfigurableApplicationContext child =
        new SpringApplicationBuilder(ParentConfiguration.class)
                .child(ChildConfiguration.class)
                .run();

try {
    assertThat(child.getParent()).isNotNull();
    assertThat(child.getBean(ReportService.class)).isNotNull();
} finally {
    child.close();
}
~~~

This is an illustrative skeleton; depending on how the builder manages hierarchy and contexts, ensure the parent is also closed cleanly according to lifecycle. In real tests, use `try`/`finally` or an appropriate context management utility to close both parent and child and prevent context leaks across tests.

## 17. Common Errors with Multiple Contexts

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Child cannot inject service | Service not registered in parent, parent not refreshed, or child parent not set | Check bootstrap order and bean definitions |
| Parent cannot find child controller | Mistaken bean visibility direction | Move needed abstraction to parent or invoke from child |
| Bean instantiated twice | Same configuration/component registered in both parent and child | Narrow component scans and clarify bean ownership |
| Child uses an unexpected bean | Local bean shadows same-named bean in parent | Check local bean names and qualifiers |
| AOP/transactions fail on parent service | Processor registered only in child | Register processor/configuration in the context owning the service |
| Child fails after parent closes | Child still depends on destroyed parent beans | Close child before parent |
| Collection injection missing or extra beans | Lookup API considers only local or ancestors differently | Use ancestor-including APIs and test the resolved list |
| Event listener fires twice | Listener registered in multiple contexts or event propagated to parent | Clarify which context owns the listener and check event source |
| Startup complex and hard to diagnose | Multi-layer scans/imports/auto-configurations | Reduce context count and clarify module boundaries |

## 18. Context Hierarchy Design Principles

1. Create multiple contexts only when lifecycle, web entry point, or configuration boundaries truly require separation.
2. Put shared beans in the parent; put specialized beans in children.
3. Keep dependencies unidirectional: children may depend on the parent, never the reverse.
4. Avoid scanning the same package in multiple contexts unless duplicate instances are intended.
5. Remember singletons are scoped per context, not per JVM.
6. Register `BeanPostProcessor` and AOP infrastructure in the context owning the target beans.
7. Close children before the parent and release resources cleanly per lifecycle.
8. Clarify Environment, profiles, event listeners, and collection lookups across levels.
9. Never treat a hierarchy as a security boundary or process isolation.
10. Test bean visibility and lifecycle with real contexts.

Context hierarchies allow Spring to organize an application into parent and child contexts: the parent supplies shared beans, while children hold specialized beans and can resolve upward into the parent. Each context retains its own registry, singleton cache, processors, and lifecycle. Used appropriately, this model works well for multiple web entry points or independently configured modules; for standard Spring Boot applications, a single context is usually easier to understand and operate.
