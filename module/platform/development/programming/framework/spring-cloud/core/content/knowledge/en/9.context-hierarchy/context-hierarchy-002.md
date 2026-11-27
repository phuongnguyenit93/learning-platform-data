# Building Parent, Child, and Sibling Contexts with `SpringApplicationBuilder`

Spring can run multiple `ApplicationContext` instances within the same process and organize them into a **context hierarchy tree**. A *parent* context holds shared beans; a *child* context holds specialized components and can access the parent's beans. Two contexts that share the same parent are called **siblings**: they can share infrastructure in the parent, but cannot directly access each other's private beans.

Spring Boot provides `SpringApplicationBuilder` to build this structure with a fluent API. In the **SPRING_CLOUD_CORE** module, this model is useful for understanding Spring's context hierarchy, how Spring Cloud bootstraps and shares configuration, and the boundary between sharing beans within one JVM versus communicating across distributed services.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain parent, child, and sibling relationships between `ApplicationContext` instances.
2. Use `SpringApplicationBuilder` to create parent–child and sibling contexts.
3. Predict which beans can be looked up from each context and handle same-named beans.
4. Design a shared context for infrastructure and dedicated contexts for individual sub-applications.
5. Configure web application types, profiles, properties, and lifecycles appropriately for each context.
6. Distinguish a context hierarchy from the Spring Cloud bootstrap context and from microservice boundaries.
7. Test context creation, bean visibility, Environment, and proper context shutdown.

## 2. Why Do We Need a Context Hierarchy?

An `ApplicationContext` is a container holding bean definitions, bean instances, event listeners, resource loading, and Spring services. In simple applications, one context is usually sufficient. When a single process needs multiple configuration regions or multiple sub-applications, splitting into parent and child contexts can help organize beans by scope.

For example, an internal process has two web applications:

- An API context exposing endpoints for clients.
- An Admin context providing an operations UI or API.
- A parent context holding genuinely shared infrastructure beans, such as `Clock`, base configuration, or a non-web service.

~~~mermaid
flowchart TD
    P[Parent ApplicationContext<br/>Shared infrastructure]
    P --> A[API child context]
    P --> B[Admin child context]
    A --> A1[REST controllers]
    A --> A2[API services]
    B --> B1[Admin controllers]
    B --> B2[Admin services]
~~~

Both child contexts reference the same parent. Beans in the parent can be looked up from either child; private beans in the API context do not automatically appear in the Admin context.

**Architectural note:** parent/child/sibling are container structures within the **same JVM**. They do not provide network boundaries, process isolation, independent scaling, or fault isolation like microservices deployed in separate processes.

## 3. Three Relationships to Distinguish

### 3.1. Parent and Child

A context can have one parent. The child inherits bean lookup capability from the parent through the hierarchy.

- The parent holds shared beans or foundational configuration.
- The child holds beans specific to that sub-application.
- The child can access its own beans and beans in the parent.
- The parent cannot look up beans that exist only in the child.
- The parent cannot inject dependencies declared only in the child.

~~~mermaid
flowchart TD
    P[Parent context]
    C[Child context]
    P --> C
    C --> C1[Look up child beans]
    C --> C2[Look up parent beans if needed]
    P --> P1[Only look up parent beans]
~~~

For example: `InventoryDirectory` is declared in the parent. A controller in the child can inject `InventoryDirectory`. However, if a parent bean tries to inject `ApiController` declared only in the child, parent initialization will fail to find that bean.

### 3.2. Sibling

Two contexts are siblings if they share the **same parent**:

~~~mermaid
flowchart TD
    P[Shared parent]
    P --> A[API context]
    P --> B[Admin context]
~~~

Siblings are neither parents nor children of each other. Therefore:

- The API child sees beans in API and parent.
- The Admin child sees beans in Admin and parent.
- The API child does not see beans that exist only in Admin.
- The Admin child does not see beans that exist only in API.

If API and Admin need to share a service, place that service in the parent or in an appropriate shared configuration module. Do not rely on two siblings running in the same JVM to assume they share beans.

### 3.3. Root Context

A context without a parent is a root context. The root can hold foundational beans shared by its children. An application with only a single context is also a case with no hierarchy.

| Relationship | Has a parent? | Where are beans looked up from? |
| --- | --- | --- |
| Root | No | Beans belonging to the context itself |
| Child | Has one parent | Child beans first, then up the hierarchy to the parent |
| Sibling A | Same parent as sibling B | Beans of A and parent; does not see B's private beans |
| Sibling B | Same parent as sibling A | Beans of B and parent; does not see A's private beans |

## 4. Creating Parent and Child Contexts with SpringApplicationBuilder

### 4.1. Minimal Example

Suppose there are two configuration classes:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Clock;

@Configuration(proxyBeanMethods = false)
public class SharedParentConfiguration {

    @Bean
    Clock systemClock() {
        return Clock.systemUTC();
    }
}
~~~

Child:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApiApplication {
}
~~~

Creating the hierarchy:

~~~java
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;

public class OrdersLauncher {

    public static void main(String[] args) {
        new SpringApplicationBuilder(SharedParentConfiguration.class)
                .web(WebApplicationType.NONE)
                .child(OrdersApiApplication.class)
                .web(WebApplicationType.SERVLET)
                .run(args);
    }
}
~~~

Steps:

1. The constructor receives the parent context's sources.
2. `.web(WebApplicationType.NONE)` sets the parent as a non-web context without a web server.
3. `.child(OrdersApiApplication.class)` creates a builder for the child.
4. `.web(WebApplicationType.SERVLET)` sets the child as a Servlet application.
5. `.run(args)` starts the parent first if the parent is not already running, then starts the child and returns the current application's context.

This is an illustrative example. In a real project, you need to restrict the child's component scan so it does not accidentally rescan shared configuration or components belonging to another child.

### 4.2. Parent Can Be Declared Using `parent(...)`

Another way to write it:

~~~java
new SpringApplicationBuilder()
        .parent(SharedParentConfiguration.class)
        .child(OrdersApiApplication.class)
        .run(args);
~~~

`parent(...)` adds a parent application; `child(...)` creates a child application. Both return the builder for further configuration.

If there is only a single standalone Boot application, do not create a hierarchy just to use the fluent API. `SpringApplication.run(...)` or a simple `SpringApplicationBuilder` is usually easier to understand.

### 4.3. `run(...)` Starts the Parent First

According to the `SpringApplicationBuilder` API, `run(args)` creates the current context and its parent context if configured. The parent is run first with the same command-line arguments if it has not already been started.

This matters when the child depends on parent beans. If the parent fails to initialize, the child cannot complete startup under that hierarchy either.

You can retain the builders to access contexts after running:

~~~java
SpringApplicationBuilder parentBuilder =
        new SpringApplicationBuilder(SharedParentConfiguration.class)
                .web(WebApplicationType.NONE);

SpringApplicationBuilder childBuilder =
        parentBuilder.child(OrdersApiApplication.class)
                .web(WebApplicationType.SERVLET);

ConfigurableApplicationContext childContext = childBuilder.run(args);
ConfigurableApplicationContext parentContext = parentBuilder.context();
~~~

`context()` returns the builder's current context if it has been created. When managing lifecycles or testing, keep references to the builders/contexts rather than assuming `run()` returns every context in the hierarchy.

## 5. Creating Sibling Contexts

### 5.1. Using `sibling(...)`

Suppose one process needs API and Admin to share `SharedParentConfiguration`:

~~~java
SpringApplicationBuilder apiBuilder =
        new SpringApplicationBuilder(SharedParentConfiguration.class)
                .web(WebApplicationType.NONE)
                .child(OrdersApiApplication.class)
                .web(WebApplicationType.SERVLET);

SpringApplicationBuilder adminBuilder =
        apiBuilder.sibling(
                new Class<?>[]{AdminApplication.class},
                args
        ).web(WebApplicationType.SERVLET);

ConfigurableApplicationContext adminContext = adminBuilder.run(args);
ConfigurableApplicationContext apiContext = apiBuilder.context();
~~~

`AdminApplication` is the second application's configuration. `sibling(...)` creates a new application that shares the same parent as the current application.

**API lifecycle detail:** calling `sibling(...)` has the side effect of starting the current application and its parent if they are not already running. The overload taking `Class<?>[]` and `String... args` allows passing arguments when starting the current application and parent. Then call `run(args)` on the sibling builder to run the sibling application.

This differs from calling `.child(AdminApplication.class)` on the API builder: that would make Admin a child of API, not a sibling of API.

### 5.2. Siblings Can Have Separate Configurations

API and Admin can use separate sources:

~~~java
@Configuration(proxyBeanMethods = false)
class ApiConfiguration {
    // Beans for API only.
}

@Configuration(proxyBeanMethods = false)
class AdminConfiguration {
    // Beans for Admin only.
}
~~~

When both are siblings, beans in `ApiConfiguration` are not automatically visible from `AdminConfiguration`, and vice versa. Beans that are genuinely shared should be placed in the parent.

### 5.3. When to Use Siblings?

| Need | How to organize |
| --- | --- |
| One web application using shared infrastructure | Root + one child |
| API and Admin needing to share infrastructure beans | One parent + two siblings |
| A child needing additional specialized sub-configuration | Parent → Child → Grandchild |
| Two applications needing no shared beans | Two independent contexts or two processes, depending on the goal |
| Independent scaling or deployment | Separate processes/services; a context hierarchy does not provide this capability |

## 6. Bean Lookup Rules in a Hierarchy

### 6.1. Child Can Use Parent Beans

For example, the parent declares a service:

~~~java
public class SharedCatalog {
    public String source() {
        return "shared-parent";
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
class SharedParentConfiguration {
    @Bean
    SharedCatalog sharedCatalog() {
        return new SharedCatalog();
    }
}
~~~

The child can inject it:

~~~java
@Component
class ApiCatalogService {
    private final SharedCatalog catalog;

    ApiCatalogService(SharedCatalog catalog) {
        this.catalog = catalog;
    }

    String source() {
        return catalog.source();
    }
}
~~~

When Spring creates `ApiCatalogService` in the child, dependency lookup can walk up to the parent if the child does not have a matching local bean.

### 6.2. Parent Cannot Depend on Child Beans

Architecturally invalid example:

~~~java
@Configuration(proxyBeanMethods = false)
class SharedParentConfiguration {
    @Bean
    SharedCoordinator coordinator(ApiController controller) {
        return new SharedCoordinator(controller);
    }
}
~~~

If `ApiController` is declared only in the child, the parent cannot find it. The parent is initialized before the child and cannot depend on a bean that only exists in the child.

The fix is to invert responsibilities: the parent provides a shared abstraction; the child injects that abstraction and coordinates its own specific behavior.

### 6.3. Same-Named Beans in Child and Parent

If both parent and child have a bean named `clock`, a lookup through the child prefers the child's bean. The parent's bean still exists in the parent context, but can be shadowed by the child's bean when looked up by name from the child.

This can cause confusion when injecting by type, especially when both beans have the same type:

- Use `@Qualifier` to select the bean explicitly.
- Use `@Primary` in the appropriate scope if there is a default candidate.
- Avoid creating beans with the same name/type at multiple levels unless overriding is intended.
- Check which context owns the bean rather than looking only at the bean name.

A `BeanFactory` hierarchy does not merge all beans into a single registry. Each context has its own bean factory, and lookups traverse the parent relationship.

## 7. Singleton Scope and Shared State

A singleton bean in the parent is a single instance managed by the parent. Multiple children can look up and share that exact instance.

This is useful for shared services, but also introduces constraints:

- Shared beans must be safe when accessed concurrently by multiple children.
- Mutable state in the parent can be modified by multiple children simultaneously.
- Do not place request-scoped or servlet-specific beans in a parent shared across multiple web children.
- Consider bean lifecycle and resource opening/closing when the parent context shuts down.
- A singleton in another child is a different instance, even when both beans have the same class.

For example, `Clock` or a stateless client may be suitable as a shared bean if configuration and lifecycle allow. A component holding user session data or request state is generally unsuitable for a shared parent.

**Sharing a bean does not mean sharing data safely.** If multiple children invoke a mutable bean, design thread safety and ownership just like any concurrently shared object in the JVM.

## 8. Environment, Profiles, and Configuration Across Contexts

### 8.1. Environment in a Hierarchy

Spring Boot's `SpringApplicationBuilder` propagates/copies default settings and the Environment from parent to child according to builder rules. Spring Boot documentation also notes that a hierarchy built in the default manner uses the same Environment for parent and child in the documented cases. Therefore, do not treat parent and child as two completely independent configuration environments.

If an application needs separate configuration for each child, explicitly define how `ConfigurableEnvironment` is created/supplied and test the behavior on the Spring Boot version in use. Do not assume that merely having two separate bean factories makes profiles or property sources independent automatically.

### 8.2. Setting Profiles with the Builder

You can use `.profiles(...)`:

~~~java
new SpringApplicationBuilder(SharedParentConfiguration.class)
        .profiles("cloud", "prod")
        .child(OrdersApiApplication.class)
        .run(args);
~~~

Per the builder API, profiles are added to the current application and related parent/child contexts. When using a hierarchy, verify the active profiles in each context via `Environment.getActiveProfiles()`.

Do not use profiles to simulate sibling isolation. Profiles determine which configurations/beans are activated; they do not create bean boundaries between two contexts.

### 8.3. Default Properties

`SpringApplicationBuilder.properties(...)` sets default properties for the Environment:

~~~java
new SpringApplicationBuilder(OrdersApiApplication.class)
        .properties(
                "clients.inventory.read-timeout=700ms",
                "feature.catalog.enabled=true"
        )
        .run(args);
~~~

Default properties typically have lower precedence than external configuration sources such as command-line arguments, system properties, and Config Data. Use them as application defaults; do not treat them as the highest-precedence override mechanism.

### 8.4. Separate Configuration per Child

When multiple children need different profiles/properties, explicitly design how the Environment is provided to each builder. The `environment(ConfigurableEnvironment)` API lets you supply an Environment for the application being built. Note that if the same Environment object is passed to multiple contexts, changes to a PropertySource can affect all contexts sharing that object.

Example of initializing a separate Environment:

~~~java
StandardEnvironment apiEnvironment = new StandardEnvironment();
apiEnvironment.setActiveProfiles("api");

SpringApplicationBuilder apiBuilder =
        new SpringApplicationBuilder(ApiApplication.class)
                .environment(apiEnvironment);
~~~

This example illustrates supplying an Environment to a standalone application. When combined with a parent, verify how your version of the builder merges/propagates the Environment; do not use this snippet as a guarantee that simply creating a new object automatically isolates all configuration in a hierarchy.

## 9. Web Application Type and Placement of Web Components

Spring Boot supports the following application types:

- `WebApplicationType.NONE`: does not create a web server.
- `WebApplicationType.SERVLET`: Servlet-based web application.
- `WebApplicationType.REACTIVE`: reactive application based on the reactive web stack.

An important constraint when building a context hierarchy is that **web components should reside in child contexts**. The parent should typically be a non-web context containing shared configuration and beans.

~~~java
new SpringApplicationBuilder(SharedParentConfiguration.class)
        .web(WebApplicationType.NONE)
        .child(OrdersApiApplication.class)
        .web(WebApplicationType.SERVLET)
        .run(args);
~~~

If you place a web server or controllers in the parent, conflicts can arise when a child also creates web infrastructure. Separating web-specific beans into children gives each sub-application a clear scope.

### 9.1. Do Not Arbitrarily Mix Servlet and Reactive

If a process has a Servlet API and a separate reactive application, each child can be configured with its appropriate web type. However, you must verify the classpath, auto-configuration, ports, lifecycle, and compatibility of each integration. Not every starter is compatible with every kind of web context.

## 10. Component Scan and Auto-Configuration in a Hierarchy

### 10.1. Avoid Overly Broad Scans

`@SpringBootApplication` includes component scanning. If both parent and child scan a broad root package, the same configuration or components can be registered in multiple contexts.

For example, a parent scanning `com.example` while a child also scans `com.example.api` can cause API beans to appear in the parent if scan filters are not properly restricted. That defeats the intent of keeping web beans in the child.

One way to organize packages:

~~~text
com.example
  shared
    SharedParentConfiguration.java
    SharedCatalog.java
  api
    OrdersApiApplication.java
    ApiController.java
  admin
    AdminApplication.java
    AdminController.java
~~~

The parent imports only the `shared` package; the API child scans only `api`; the Admin child scans only `admin`. You can use `@ComponentScan(basePackageClasses = ...)` or `@Import` to define the configuration explicitly.

### 10.2. Auto-Configuration Can Run in Multiple Contexts

If each context is initialized by a `SpringApplication` with auto-configuration enabled, matching auto-configurations can be evaluated in each context. This can create separate infrastructure beans in both parent and child.

For example, if two children both have web auto-configuration, each child can initialize its own web infrastructure. That may be intentional if they are two independent web applications, but ports and resources must be checked.

Do not assume an auto-configuration runs only once across the entire JVM. It is applied within the scope of each context being initialized.

### 10.3. Avoid Duplicating Shared Beans

If `Clock`, `ObjectMapper`, or a shared client is already in the parent, do not redeclare it in every child unless a child genuinely needs a different configuration. If a child redeclares it, decide explicitly whether the child bean shadows the parent bean or adds another candidate.

## 11. Application Events and Lifecycle

### 11.1. Events in a Context Hierarchy

An event published in a child can be forwarded up to the parent via Spring context's event propagation mechanism. An event published in the parent is not automatically broadcast down to all children.

Therefore, if a child publishes a domain event, a listener in the parent can receive it if registered properly. However, do not rely on parent events to automatically notify other sibling contexts. For siblings to communicate, use a shared abstraction, an explicitly designed internal event bus, or appropriate messaging.

### 11.2. Context Initialization and Shutdown Order

`SpringApplicationBuilder.run(...)` starts the parent before starting the child. If the parent is not ready, the child cannot rely on parent beans.

When the application shuts down, ensure children are no longer using resources in the parent before the parent is closed. For contexts managed manually by test code or a launcher, retain references and close them in the proper order:

1. Stop accepting work in the children.
2. Close the child contexts.
3. Close the parent last.

If using the builder's shutdown hook, understand which contexts have hooks registered and who owns the lifecycle. Do not close the parent while a child is still processing requests or using shared resources.

## 12. Integration with Spring Cloud

### 12.1. A Context Hierarchy Is Not the Bootstrap Context

The Spring Cloud bootstrap context is a specific legacy Spring Cloud mechanism for loading configuration before the main application context. That context can serve as the parent of the main context in the legacy bootstrap model.

`SpringApplicationBuilder` can also create a parent/child hierarchy, but for a more general purpose: organizing multiple applications/contexts in the same process. The two concepts may be related, but they are not identical.

With modern Config Data imports, the Config Client loads remote sources during Environment preparation; there is no need to manually create a hierarchy just to fetch configuration.

### 12.2. Sharing Discovery or Client Beans

If the parent contains a `DiscoveryClient` bean or a shared stateless client, children can look up that bean through the hierarchy if dependencies and auto-configuration are placed properly. However, do not assume every discovery provider supports or should be initialized in the parent.

Consider:

- Whether the provider requires per-application configuration.
- Whether the registry client depends on the child's profile/application name.
- Whether the bean holds state or metadata tied to a specific service identity.
- Whether the parent Environment is suitable for all children.
- Whether closing the parent context affects clients still used by children.

A service registry entry typically represents a specific application/instance. If two children need to register with different service names or metadata, giving each child its own integration may be more appropriate than sharing a single registration bean in the parent.

### 12.3. Does Not Replace Inter-Microservice Communication

A context hierarchy only shares objects within one JVM. If Orders and Inventory are two services running in separate processes/containers, they must communicate over HTTP, messaging, or another distributed protocol. You cannot use a parent/child context to look up beans in another process.

## 13. Testing a Context Hierarchy

### 13.1. Checking Bean Visibility

You can start a small parent and child using the builder, then verify that the child sees the parent's bean:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

class ContextHierarchyTest {

    @Test
    void childCanResolveParentBean() {
        try (ConfigurableApplicationContext parent =
                     new SpringApplicationBuilder(SharedParentConfiguration.class)
                             .web(WebApplicationType.NONE)
                             .run();
             ConfigurableApplicationContext child =
                     new SpringApplicationBuilder(OrdersApiApplication.class)
                             .parent(parent)
                             .web(WebApplicationType.NONE)
                             .run()) {
            assertThat(child.getBean(SharedCatalog.class)).isNotNull();
            assertThat(child.getParent()).isSameAs(parent);
        }
    }
}
~~~

The example requires `SharedCatalog` in `SharedParentConfiguration` and uses `OrdersApiApplication` declared earlier as the child's source. Using `WebApplicationType.NONE` keeps the test from starting a web server.

In real tests, check both child and parent beans rather than only verifying that a child lookup succeeds and concluding the entire hierarchy is correct.

### 13.2. Verifying Parent Cannot See Child Beans

~~~java
assertThat(parent.context().containsBean("apiController")).isFalse();
assertThat(child.containsBean("apiController")).isTrue();
~~~

`containsBean` is called on the appropriate context. When looking up through the hierarchy, the child can see the parent; the parent does not look downward into the child.

### 13.3. Verifying Sibling Isolation

Create two siblings with their own beans sharing a parent bean. Verify:

- The API child sees the shared bean.
- The Admin child sees the shared bean.
- The API child does not see beans existing only in Admin.
- The Admin child does not see beans existing only in API.

You can use `SpringApplicationBuilder.sibling(...)` or create each child with the same running parent context using the `parent(ConfigurableApplicationContext)` overload.

### 13.4. Testing Profiles and Environment

Check `Environment.getActiveProfiles()` in both parent and child. If the Environment is shared or inherited per builder configuration, confirm profiles are propagated as expected. If separate Environments are used, verify both property sources and precedence order.

Do not check only `builder.profiles(...)`; verify the actual active profiles in the context after startup.

## 14. Common Mistakes

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| Child cannot inject parent bean | Bean is not in parent or parent startup failed | Check parent context, bean definitions, and lifecycle |
| Parent fails to inject child bean | Dependency designed against hierarchy direction | Move shared abstraction up to parent or move consumer down to child |
| Siblings do not see each other's beans | Siblings do not inherit from each other | Place shared bean in parent or use explicit communication |
| Bean appears twice | Component scan/auto-configuration runs in multiple contexts | Narrow scans and verify which context owns each bean |
| Child has a bean with same name as parent | Child bean shadows parent bean when looked up through child | Use qualifiers, rename, or remove duplicate declaration |
| Web server initializes in wrong context | Web components placed in parent or web type misconfigured | Put web infrastructure in child; parent is typically `NONE` |
| Calling `sibling()` starts current context early | This is a documented side effect in the API | Use the overload taking args and understand startup order |
| Closing parent breaks child | Parent closed while child still uses shared bean | Stop/close child before parent |
| Two children receive unexpected configuration | Environment/profiles propagated or shared by the builder | Inspect the actual Environment of each context |
| Assuming hierarchy creates two microservices | Confusing container boundaries with process boundaries | Use separate processes/services when scaling/deployment/fault isolation is needed |

## 15. Design Principles and When Not to Use a Hierarchy

A context hierarchy is helpful when a single process genuinely needs to share infrastructure and separate bean scopes. It also increases complexity in debugging, configuration, events, and lifecycle.

Use it when:

- Multiple sub-applications in the same JVM need to share certain foundational beans.
- There is a clear reason for the parent to manage the lifecycle of shared infrastructure.
- Web beans or per-application beans need to be separated into distinct contexts.
- The team can control component scanning, profiles, and property sources for each context.

Do not use it merely because:

- You want to split Java packages or modules.
- You want to avoid creating multiple service processes.
- You want to share data between microservices.
- You want independent configuration environments without designing separate Environments.
- You want to reduce bean counts without defining ownership.

A Java modular codebase can separate packages and configurations within the same context without needing a hierarchy. Create multiple contexts only when container boundaries provide tangible value.

## 16. Practice Exercises

**Exercise 1 — Parent/child.** Create `SharedParentConfiguration` providing a `Clock` bean, then create `OrdersApiConfiguration` as a child. Verify the child can inject `Clock`. Try moving the `Clock` bean down into the child and observe whether the parent can inject it.

**Exercise 2 — Sibling.** Create `ApiApplication` and `AdminApplication` sharing a parent. Have each child provide its own differently named bean. Verify both see the parent bean but neither sees the sibling's private bean.

**Exercise 3 — Bean override.** Place a bean with the same name in both parent and child. Test `getBean()` from the child and from the parent, then use `@Qualifier` to select the candidate explicitly.

**Exercise 4 — Component scan.** Have the parent scan a root package containing both API and Admin. Observe beans being registered in unintended contexts. Narrow `@ComponentScan` and re-verify the hierarchy.

**Exercise 5 — Web type.** Set the parent to `WebApplicationType.NONE` and the child to `SERVLET`. Verify only the child opens a web server. Try configuring web infrastructure in the parent and analyze the error or conflict.

**Exercise 6 — Lifecycle.** Create two children sharing a parent bean that holds a resource needing to be closed. Build a shutdown sequence so no child continues using the resource after the parent is closed.

**Exercise 7 — Spring Cloud.** Compare a hierarchy created with `SpringApplicationBuilder` against Spring Cloud's legacy bootstrap context. Identify which context serves application organization and which serves bootstrap configuration loading.

## 17. Key Takeaways and Reference Sources

- **Parent** holds shared beans; **child** can look up parent beans, but parent does not look down into child.
- **Siblings** share a parent and do not see each other's private beans.
- `SpringApplicationBuilder.child(...)` creates a child; `sibling(...)` creates a peer application alongside the current application.
- `run(...)` starts the parent first if the parent is not running. `sibling(...)` has the side effect of starting the current application and parent per the API.
- Each context has its own bean factory and lifecycle; singletons in the parent can be shared across multiple children.
- Place web-specific components in children; the parent is typically a non-web context.
- Check component scanning and auto-configuration in each context to avoid duplicate beans.
- A context hierarchy is an in-JVM structure, not a replacement for microservice boundaries.
- Spring Cloud's legacy bootstrap context is a specific integration case; do not equate it with every hierarchy built manually with the builder.

Official sources for cross-checking against your project's Spring Boot/Spring Framework version:

1. [Spring Boot Reference – Fluent Builder API and Context Hierarchy](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
2. [Spring Boot Javadoc – `SpringApplicationBuilder`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/builder/SpringApplicationBuilder.html)
3. [Spring Framework Reference – BeanFactory Hierarchy](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
4. [Spring Framework Reference – ApplicationContext](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
5. [Spring Cloud Context – Bootstrap Application Context](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
