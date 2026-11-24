# ImportBeanDefinitionRegistrar and Advanced Definition Registration

In Spring, most application beans are registered via component scanning or `@Bean` methods. Those approaches suffice for most ordinary applications. However, some libraries or modules need to create **multiple beans from metadata**, from a list of enabled modules, from annotations on a configuration class, or from a set of implementations discovered before the ApplicationContext instantiates business beans.

For example, a library might provide an `@EnableConnectors({"orders", "billing"})` annotation. When a user places that annotation on a configuration class, the library needs to register one connector bean for each declared name. Writing a separate `@Bean` method for each connector is inflexible when the number of connectors is driven by metadata.

Spring provides **`ImportBeanDefinitionRegistrar`** for this advanced scenario. The registrar is hooked into configuration via `@Import`, receives the configuration class metadata and `BeanDefinitionRegistry`, and programmatically registers **bean definitions**. It enables extensible configurations while still letting Spring manage bean instantiation, dependency injection, and lifecycle.

## 1. From Ordinary Bean Registration to Metadata-Driven Registration

A bean in Spring can be registered in several ways:

- Component scanning discovers classes with stereotypes such as `@Component`, `@Service`, `@Repository`, or `@Controller`.
- A `@Bean` method in a `@Configuration` class returns an instance managed by the container.
- `@Import` brings configurations, selectors, or registrars into configuration processing.
- Infrastructure components can register `BeanDefinition`s directly via `BeanDefinitionRegistry`.

For small applications, the following example is usually enough:

~~~java
@Configuration
public class BillingConfiguration {

    @Bean
    public BillingService billingService(
            InvoiceRepository repository
    ) {
        return new BillingService(repository);
    }
}
~~~

Spring knows that the `billingService` method provides a bean. When creating the bean, the container resolves the `InvoiceRepository` parameter and invokes the factory method according to configuration management rules.

Now suppose we need to register one bean for each connector named in an annotation:

~~~java
@EnableConnectors({"orders", "billing", "inventory"})
@Configuration
public class IntegrationConfiguration {
}
~~~

The number of beans and their names are determined from the `@EnableConnectors` metadata. This is a suitable case for a registrar to create bean definitions programmatically.

### Distinguishing Instances from Bean Definitions

A **bean instance** is the actual Java object used at runtime. A **bean definition** is metadata describing to the container how to create and manage that object.

A bean definition can contain information such as:

- Class or factory method used to create the bean.
- Constructor arguments and property values.
- Scope, lazy initialization, primary/autowire candidate flags.
- Required dependencies and initialization relationships.
- Init method and destroy method.
- Role or additional metadata used by the container.

`ImportBeanDefinitionRegistrar` primarily operates in the **definition registration phase**, rather than instantiating objects and managing them manually. That is the single most important point to grasp.

~~~text
Annotation / Java configuration
              |
              v
      @Import(Registrar.class)
              |
              v
ImportBeanDefinitionRegistrar
              |
              | reads AnnotationMetadata
              | writes BeanDefinitionRegistry
              v
       Bean definitions
              |
              v
       BeanFactory / Context
              |
              | resolves dependencies
              | instantiates beans
              | applies lifecycle / proxies
              v
         Bean instances
~~~

## 2. What Is ImportBeanDefinitionRegistrar?

`ImportBeanDefinitionRegistrar` is an interface in the package:

~~~java
org.springframework.context.annotation.ImportBeanDefinitionRegistrar
~~~

This interface lets a class participate in `@Import` processing and register additional bean definitions into the registry.

Core method:

~~~java
void registerBeanDefinitions(
        AnnotationMetadata importingClassMetadata,
        BeanDefinitionRegistry registry
);
~~~

The two parameters serve distinct roles:

| Parameter | Meaning |
|---|---|
| `AnnotationMetadata importingClassMetadata` | Metadata of the configuration class that imported the registrar, including annotation information and annotation attributes |
| `BeanDefinitionRegistry registry` | Registry used to register, inspect, and manage bean definitions |

A registrar is generally not a business bean discovered via component scanning like a service. It is instantiated and invoked by Spring during configuration processing when the class bearing `@Import` is processed.

### What Information Does AnnotationMetadata Provide?

`AnnotationMetadata` lets you read annotations on the configuration class without instantiating that class. Example:

~~~java
Map<String, Object> attributes =
        importingClassMetadata.getAnnotationAttributes(
                EnableConnectors.class.getName()
        );
~~~

The map can contain attributes such as `value`, `basePackages`, `enabled`, or classes declared in the annotation. From that data, the registrar decides which bean definitions to register.

This is a key mechanism for "enable"-style annotations: users declare intent on a configuration class; the registrar reads that intent and creates the required definitions.

### What Does BeanDefinitionRegistry Do?

`BeanDefinitionRegistry` is the abstraction for registering and looking up bean definitions by name. Common operations include:

~~~java
registry.containsBeanDefinition("ordersConnector");
registry.registerBeanDefinition("ordersConnector", beanDefinition);
registry.removeBeanDefinition("ordersConnector");
~~~

In typical registrars, you mainly use `containsBeanDefinition` and `registerBeanDefinition`. Do not remove or replace another bean definition unless there is a clear reason and you understand the impact across the entire application configuration.

## 3. Registrars Are Activated via @Import

A common pattern is creating a composite configuration annotation and using `@Import` to bring the registrar into processing.

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(ConnectorRegistrar.class)
public @interface EnableConnectors {
    String[] value() default {};
}
~~~

The `@EnableConnectors` annotation lets users enable the module and provide connector names. When placed on a configuration class:

~~~java
@Configuration
@EnableConnectors({"orders", "billing"})
public class IntegrationConfiguration {
}
~~~

Spring processes `@Import(ConnectorRegistrar.class)` and invokes the registrar during configuration processing. The registrar can read the `value` attribute from `AnnotationMetadata` and register the corresponding bean definitions.

A class imported with `@Import` can be:

1. A configuration class containing bean definitions.
2. An implementation of `ImportSelector` to choose configuration classes to import.
3. An implementation of `ImportBeanDefinitionRegistrar` to register bean definitions programmatically.

These three mechanisms are related but serve different roles:

| Mechanism | Purpose |
|---|---|
| `@Import(SomeConfiguration.class)` | Brings a configuration class into the context |
| `ImportSelector` | Selects one or more configuration classes to import |
| `ImportBeanDefinitionRegistrar` | Registers custom bean definitions directly into the registry |

If you only need to import a fixed configuration, `@Import` with a configuration class is simplest. If you need to choose configurations based on metadata, `ImportSelector` may fit. If you need to generate bean definitions from data, `ImportBeanDefinitionRegistrar` is the dedicated tool.

## 4. Complete Example: Registering Connectors from an Annotation

Let us build a Spring Boot example that registers one `NamedConnector` bean for each name in `@EnableConnectors`.

### 4.1. Defining the Object to Be Registered

~~~java
package com.example.integration;

public class NamedConnector {
    private final String connectorName;

    public NamedConnector(String connectorName) {
        this.connectorName = connectorName;
    }

    public String connectorName() {
        return connectorName;
    }

    public String send(String payload) {
        return "[" + connectorName + "] " + payload;
    }
}
~~~

`NamedConnector` is a plain Java class. It does not need `@Component` because the registrar registers the bean definition directly for this class.

### 4.2. Creating the Connector-Enabling Annotation

~~~java
package com.example.integration;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.context.annotation.Import;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(ConnectorRegistrar.class)
public @interface EnableConnectors {
    String[] value() default {};
}
~~~

Notable points:

- `@Target(ElementType.TYPE)` allows placing the annotation on classes/interfaces.
- `@Retention(RetentionPolicy.RUNTIME)` retains metadata at runtime so Spring can read it.
- `@Import` connects the annotation to the registrar.
- `value` is the list of connector names the user wants to register.

### 4.3. Implementing the Registrar

~~~java
package com.example.integration;

import java.util.Map;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionStoreException;
import org.springframework.context.annotation.ImportBeanDefinitionRegistrar;
import org.springframework.core.type.AnnotationMetadata;

public class ConnectorRegistrar
        implements ImportBeanDefinitionRegistrar {

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata importingClassMetadata,
            BeanDefinitionRegistry registry
    ) {
        Map<String, Object> attributes =
                importingClassMetadata.getAnnotationAttributes(
                        EnableConnectors.class.getName()
                );

        if (attributes == null) {
            return;
        }

        String[] connectorNames = (String[]) attributes.get("value");

        for (String connectorName : connectorNames) {
            String beanName = connectorName + "Connector";

            if (registry.isBeanNameInUse(beanName)) {
                throw new BeanDefinitionStoreException(
                        "Bean name already in use: " + beanName
                );
            }

            var beanDefinition =
                    BeanDefinitionBuilder
                            .genericBeanDefinition(NamedConnector.class)
                            .addConstructorArgValue(connectorName)
                            .getBeanDefinition();

            registry.registerBeanDefinition(beanName, beanDefinition);
        }
    }
}
~~~

Explanation:

1. `getAnnotationAttributes` reads the attributes of the annotation on the configuration class importing the registrar.
2. If the annotation is absent from metadata, the registrar has no data to process and returns.
3. For each connector name, the code builds a stable bean name.
4. `isBeanNameInUse` checks whether the name is already used by a bean definition or alias.
5. `BeanDefinitionBuilder` constructs metadata for `NamedConnector` and adds the constructor argument.
6. `registerBeanDefinition` registers the metadata in the registry.

The registrar never calls `new NamedConnector(...)`. It describes to Spring how to create the bean; Spring creates instances when the container needs to initialize beans according to scope and lifecycle.

### 4.4. Using the Annotation in an Application

~~~java
package com.example.integration;

import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConnectors({"orders", "billing", "inventory"})
public class IntegrationConfiguration {
}
~~~

Once the ApplicationContext is initialized, the beans can be accessed like this:

~~~java
NamedConnector orders =
        applicationContext.getBean(
                "ordersConnector",
                NamedConnector.class
        );

NamedConnector billing =
        applicationContext.getBean(
                "billingConnector",
                NamedConnector.class
        );
~~~

Result:

~~~java
orders.send("Order created");
// [orders] Order created

billing.send("Invoice generated");
// [billing] Invoice generated
~~~

The lookup snippet here is only for demonstrating verification that the beans were registered. In business services, if connectors are needed, inject a collection of beans or a typed registry instead of scattering `ApplicationContext.getBean` calls.

### 4.5. Working with Multiple Beans of the Same Type

Because the registrar creates multiple `NamedConnector` beans, injecting a single `NamedConnector` without a selection rule will cause ambiguity. You can inject a collection or map:

~~~java
@Service
public class ConnectorDispatcher {
    private final Map<String, NamedConnector> connectors;

    public ConnectorDispatcher(
            Map<String, NamedConnector> connectors
    ) {
        this.connectors = Map.copyOf(connectors);
    }

    public String send(String connectorName, String payload) {
        NamedConnector connector =
                connectors.get(connectorName + "Connector");

        if (connector == null) {
            throw new IllegalArgumentException(
                    "Unknown connector: " + connectorName
            );
        }

        return connector.send(payload);
    }
}
~~~

In this example, Spring supplies beans of type `NamedConnector` as a map keyed by bean name. The dispatcher uses a set of beans assembled by the container; it does not need to hold `ApplicationContext`.

In production applications, consider an interface like `Connector` and a domain-typed resolver instead of concatenating bean names from arbitrary strings. Bean names are a configuration detail; business connector names should have an explicit mapping rule.

## 5. Building BeanDefinitions with BeanDefinitionBuilder

`BeanDefinitionBuilder` helps construct metadata without calling numerous setters directly. It can configure the class, constructor arguments, properties, scope, lazy initialization, and other attributes.

Example:

~~~java
BeanDefinition definition =
        BeanDefinitionBuilder
                .genericBeanDefinition(ReportExporter.class)
                .addConstructorArgValue("csv")
                .setScope(BeanDefinition.SCOPE_SINGLETON)
                .setLazyInit(true)
                .getBeanDefinition();
~~~

Common operations:

| Method | Effect |
|---|---|
| `genericBeanDefinition(Class<?>)` | Starts building a bean definition from a class |
| `addConstructorArgValue(value)` | Adds a constructor argument |
| `addPropertyValue(name, value)` | Sets a property value |
| `setScope(scope)` | Sets the bean scope |
| `setLazyInit(true)` | Marks initialization as lazy |
| `setPrimary(true)` | Prioritizes the bean in certain autowiring scenarios |
| `setAutowireCandidate(false)` | Excludes the bean from being an ordinary autowiring candidate |
| `getBeanDefinition()` | Retrieves the constructed `BeanDefinition` |

Exact method names and capabilities on the builder depend on the Spring Framework version, though the operations above are standard APIs.

### Constructor Arguments and Property Values

You can supply dependencies or configuration values via constructor arguments:

~~~java
BeanDefinition definition =
        BeanDefinitionBuilder
                .genericBeanDefinition(ReportExporter.class)
                .addConstructorArgReference("reportRepository")
                .addConstructorArgValue("csv")
                .getBeanDefinition();
~~~

`addConstructorArgReference` references another bean by name. When the container creates the bean, it resolves that reference against the corresponding bean definition.

Or configure properties:

~~~java
BeanDefinition definition =
        BeanDefinitionBuilder
                .genericBeanDefinition(ReportExporter.class)
                .addPropertyValue("format", "csv")
                .getBeanDefinition();
~~~

Property injection requires a matching setter/property on the class and instantiation that permits Spring to assign the value. For new classes, constructor injection usually expresses mandatory dependencies more clearly.

### Registering Directly with RootBeanDefinition

Using the builder is optional. You can construct a `RootBeanDefinition` directly:

~~~java
RootBeanDefinition definition =
        new RootBeanDefinition(ReportExporter.class);

definition.getConstructorArgumentValues()
        .addIndexedArgumentValue(0, "csv");

definition.setLazyInit(true);
definition.setScope(BeanDefinition.SCOPE_SINGLETON);

registry.registerBeanDefinition("csvReportExporter", definition);
~~~

This allows direct metadata manipulation. The builder is usually shorter and easier to read for simple cases; `RootBeanDefinition` is useful when detailed customization is needed.

## 6. What Advanced Metadata Can a BeanDefinition Contain?

A bean definition does more than record a class name. It can describe how Spring creates, wires, and manages the bean.

### Scope

~~~java
definition.setScope(BeanDefinition.SCOPE_PROTOTYPE);
~~~

A bean definition can use singleton, prototype, or registered web scopes. The scope must fit the context and data lifecycle; a registrar does not automatically create web scope infrastructure if the application lacks it.

### Lazy Initialization

~~~java
definition.setLazyInit(true);
~~~

A lazy bean can be created on demand rather than eagerly initialized alongside regular singletons. Lazy initialization changes when the instance is created; it does not make a dependency optional.

### Primary and Autowire Candidate

~~~java
definition.setPrimary(true);
definition.setAutowireCandidate(true);
~~~

`primary` marks a bean as preferred when multiple candidates of the same type exist for an injection point. `autowireCandidate` determines whether the bean participates in ordinary autowiring candidate selection. Both attributes affect dependency resolution and should be set intentionally.

### Init and Destroy Methods

~~~java
definition.setInitMethodName("initialize");
definition.setDestroyMethodName("close");
~~~

A registrar can declare lifecycle callbacks on a bean definition. The methods must exist with compatible signatures; configuration mistakes may only surface when the container initializes or destroys the bean.

### Depends-on

~~~java
definition.setDependsOn("sharedClient");
~~~

`dependsOn` indicates that a bean requires another bean to be initialized beforehand; during destruction, dependency relationships can also influence cleanup order. Still, if a bean actually needs a dependency to function, declaring a constructor/property reference expresses the relationship better than `dependsOn`.

### Role and Description

~~~java
definition.setRole(BeanDefinition.ROLE_INFRASTRUCTURE);
definition.setDescription("Infrastructure bean registered by connector registrar");
~~~

Role can indicate whether a bean belongs to application code, support, or infrastructure. This is metadata that helps tooling and readers understand the bean's role; it does not replace security or access control mechanisms.

## 7. Reading Annotation Metadata for Conditional Registration

Registrars are often paired with enable-style annotations. The annotation can carry attributes deciding whether to register beans.

Example:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(AuditRegistrar.class)
public @interface EnableAudit {
    boolean enabled() default true;
    String topic() default "audit-events";
}
~~~

The registrar reads the attributes:

~~~java
public class AuditRegistrar
        implements ImportBeanDefinitionRegistrar {

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata metadata,
            BeanDefinitionRegistry registry
    ) {
        Map<String, Object> attributes =
                metadata.getAnnotationAttributes(
                        EnableAudit.class.getName()
                );

        if (attributes == null) {
            return;
        }

        boolean enabled = (boolean) attributes.get("enabled");
        if (!enabled) {
            return;
        }

        String topic = (String) attributes.get("topic");

        BeanDefinition definition =
                BeanDefinitionBuilder
                        .genericBeanDefinition(AuditPublisher.class)
                        .addConstructorArgValue(topic)
                        .getBeanDefinition();

        registry.registerBeanDefinition("auditPublisher", definition);
    }
}
~~~

If `enabled` is false, the registrar does not register `AuditPublisher`. If true, it creates a bean definition with a constructor argument taken from metadata.

However, if the requirement is simply toggling a bean based on an environment property such as `app.audit.enabled`, `@ConditionalOnProperty` on a configuration or bean is often clearer. A registrar is appropriate when registration depends on annotation metadata or needs to generate multiple structured definitions.

### Annotations with Class Attributes

An annotation can accept a class as an attribute:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(AdapterRegistrar.class)
public @interface EnableAdapter {
    Class<?> implementation();
}
~~~

The registrar can read the class attribute from metadata and use it as the bean class if valid:

~~~java
Map<String, Object> attributes =
        metadata.getAnnotationAttributes(
                EnableAdapter.class.getName()
        );

Class<?> implementation =
        (Class<?>) attributes.get("implementation");

BeanDefinition definition =
        BeanDefinitionBuilder
                .genericBeanDefinition(implementation)
                .getBeanDefinition();
~~~

In some metadata-processing contexts, class attributes can be requested as class name strings to avoid eager class resolution. If using a mode that returns class values as strings, handle and load the class using an appropriate classloader. Never cast blindly without knowing the returned value type.

Additionally, verify that the class implements the expected interface, can be instantiated, and has a suitable constructor. Allowing users to specify a class in an annotation does not guarantee every class is a valid implementation.

## 8. Registering Beans from a List of Classes or Modules

An advanced use case is when users pass a list of implementations in an annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(HandlerRegistrar.class)
public @interface EnableHandlers {
    Class<? extends EventHandler>[] value();
}
~~~

Users declare:

~~~java
@Configuration
@EnableHandlers({
        OrderCreatedHandler.class,
        InvoicePaidHandler.class
})
public class EventConfiguration {
}
~~~

The registrar can take the class array and create a bean definition for each type. In practice, choose stable bean names, handle duplicate names, and validate types. Conceptual example:

~~~java
for (Class<?> handlerClass : handlerClasses) {
    if (!EventHandler.class.isAssignableFrom(handlerClass)) {
        throw new IllegalArgumentException(
                "Handler must implement EventHandler"
        );
    }

    BeanDefinition definition =
            BeanDefinitionBuilder
                    .genericBeanDefinition(handlerClass)
                    .getBeanDefinition();

    registry.registerBeanDefinition(
            generateBeanName(handlerClass),
            definition
    );
}
~~~

`generateBeanName` is a helper defined by the registrar. Bean names should be generated by a stable rule that avoids conflicts with existing beans. If multiple modules register the same class or same logical name, explicitly decide whether to reject, skip, or allow aliases.

If the annotation already declares specific classes, there is usually no need to scan the entire classpath to rediscover implementations. Using the provided metadata keeps behavior explicit and predictable.

## 9. Bean Names: Stable Naming and Conflict Handling

Bean names are the keys the registry uses to distinguish bean definitions. When a registrar creates multiple beans, names should be:

- Deterministic across restarts.
- Namespaced/prefixed to reflect the module or feature.
- Independent of collection iteration order.
- Free from accidental collisions with beans registered by component scanning or other configurations.
- Consistent enough to be useful in logs and diagnostics.

For instance, instead of a generic name like `client`, use `ordersConnector` or `billingConnector`.

### Checking Before Registering

~~~java
if (registry.isBeanNameInUse(beanName)) {
    throw new BeanDefinitionStoreException(
            "Bean name already in use: " + beanName
    );
}

registry.registerBeanDefinition(beanName, definition);
~~~

`isBeanNameInUse` checks whether the name is currently used in the registry, including aliases according to the registry contract. When a collision is detected, the registrar should enforce a clear policy.

Do not overwrite another module's bean definitions by default. Bean definition overriding may be disabled or enabled depending on application and version; relying on override behavior makes import order fragile.

### Using BeanNameGenerator When a Shared Convention Is Needed

Spring provides `BeanNameGenerator` to generate bean names by convention. A registrar can construct module-specific names itself or use the bean name generator passed via the corresponding overload in supported Spring versions.

When implementing a registrar that must support multiple Spring versions, verify the exact API of your target version. The `registerBeanDefinitions` overload accepting a `BeanNameGenerator` was introduced in newer Spring Framework versions; do not call newer APIs if your library must run on older Spring versions.

## 10. Registrars Can Use Environment and ResourceLoader

A registrar may need to read environment configuration or access resources. `ImportBeanDefinitionRegistrar` integrates with `Aware` callbacks provided by Spring during configuration processing, such as `EnvironmentAware`, `ResourceLoaderAware`, and `BeanClassLoaderAware`. Check the contract of your Spring version if implementing specific callbacks.

Example reading a property via `EnvironmentAware`:

~~~java
public class FeatureRegistrar
        implements ImportBeanDefinitionRegistrar, EnvironmentAware {

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata metadata,
            BeanDefinitionRegistry registry
    ) {
        boolean enabled = environment.getProperty(
                "app.feature.enabled",
                Boolean.class,
                false
        );

        if (!enabled) {
            return;
        }

        // Register bean definitions when the feature is enabled.
    }
}
~~~

This is an option when the registrar genuinely needs to read the environment. However, if the goal is simply toggling a configuration based on a property, Spring Boot's `@ConditionalOnProperty` is usually more concise.

Similarly, if you need to check the classpath or load resources, use the appropriate abstraction and avoid writing complex custom classloading logic when Spring already provides condition/metadata support.

## 11. When Does a Registrar Run?

A registrar participates during configuration class and `@Import` processing, before regular business beans are fully instantiated. It can add bean definitions for the container to use in subsequent steps.

One way to visualize it:

~~~text
Read configuration classes
          |
          v
Process @Import
          |
          v
Invoke ImportBeanDefinitionRegistrar
          |
          v
Register additional BeanDefinitions
          |
          v
Finish configuration registration
          |
          v
Create beans, resolve dependencies,
apply BeanPostProcessors and lifecycle
~~~

This explains why a registrar receives `BeanDefinitionRegistry` rather than needing an instance of a business bean. It works while the container is still constructing its bean model.

### Do Not Instantiate Business Beans Directly Inside a Registrar

Approach to avoid:

~~~java
registry.registerSingleton(
        "ordersConnector",
        new NamedConnector("orders")
);
~~~

This snippet registers a pre-created singleton instance into the registry/factory via singleton registration, which is not equivalent to registering a full bean definition. It can bypass standard bean management steps such as constructor resolution, bean post-processing, or lifecycle metadata that a bean definition provides.

Normally, you should register:

~~~java
BeanDefinition definition =
        BeanDefinitionBuilder
                .genericBeanDefinition(NamedConnector.class)
                .addConstructorArgValue("orders")
                .getBeanDefinition();

registry.registerBeanDefinition("ordersConnector", definition);
~~~

The container will then be responsible for creating the instance and applying the appropriate management lifecycle.

## 12. Distinguishing ImportBeanDefinitionRegistrar from BeanDefinitionRegistryPostProcessor

Both can register bean definitions, yet they participate at different points in the configuration process.

`BeanDefinitionRegistryPostProcessor` is a specialized `BeanFactoryPostProcessor` with a callback that operates directly on the registry after initial bean definitions have been loaded, before regular beans are created. It fits context-wide registry post-processing tasks.

| Criterion | ImportBeanDefinitionRegistrar | BeanDefinitionRegistryPostProcessor |
|---|---|---|
| Where is it triggered from? | Via `@Import` | Registered as a post-processor bean |
| Scope of intent | Tied to a specific configuration/annotation | Processes the context's registry |
| Input metadata | Receives `AnnotationMetadata` of the importing class | Receives `BeanDefinitionRegistry`; does not receive importing class metadata |
| Typical use case | Enable-style annotations generating bean definitions | Adding/adjusting registry entries after initial registration phase |
| Appropriate place | Configuration libraries, self-enabling modules | Infrastructure requiring context-wide registry manipulation |

Example post-processor interface:

~~~java
public interface BeanDefinitionRegistryPostProcessor
        extends BeanFactoryPostProcessor {

    void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry
    ) throws BeansException;
}
~~~

Do not pick the post-processor just because its name contains "registry." If users enable a feature with an annotation and the registrar needs to read attributes from that annotation, `ImportBeanDefinitionRegistrar` expresses the intent more directly.

### Distinguishing from BeanFactoryPostProcessor

`BeanFactoryPostProcessor` primarily lets you modify bean factory metadata after bean definitions are loaded. `BeanDefinitionRegistryPostProcessor` extends this mechanism with an earlier callback to register additional bean definitions.

Both are infrastructure extension points. Never use them for per-request business logic.

## 13. Distinguishing from FactoryBean

The name `FactoryBean` is easily confused with a registrar, yet the two solve different problems.

- `ImportBeanDefinitionRegistrar` registers **bean definition metadata** into the registry.
- `FactoryBean<T>` is a special bean where, when requested, Spring uses the object produced by the factory as the bean product.

Conceptual example:

~~~java
public class ClientFactoryBean implements FactoryBean<RemoteClient> {

    @Override
    public RemoteClient getObject() {
        return new RemoteClient();
    }

    @Override
    public Class<?> getObjectType() {
        return RemoteClient.class;
    }
}
~~~

A `FactoryBean` can itself be registered via a bean definition. The container then manages the factory and exposes the product according to its contract. A registrar can create bean definitions for factory beans or other components, but does not replace `FactoryBean`'s product-creation role.

Remember:

~~~text
Registrar
   |
   +--> registers BeanDefinition
                  |
                  v
             Spring container
                  |
                  v
          creates bean / FactoryBean
                  |
                  v
             bean instance
~~~

Use a registrar when you need to create definitions from metadata; use `FactoryBean` when you need a dedicated factory abstraction that produces product objects.

## 14. When Should You Use ImportBeanDefinitionRegistrar?

A registrar is useful when there is an infrastructure or framework extension requirement, such as:

- An `@Enable...` annotation needs to register a group of beans based on user-declared attributes.
- A library needs to create a bean definition for each specified interface.
- An integration module needs to register adapters, proxies, or clients from configuration metadata.
- A plugin system needs to register a set of implementations with predetermined names and dependencies.
- An internal framework wants to encapsulate multiple bean definitions behind a single annotation.

For example, a library might provide:

~~~java
@EnableRemoteClients(
        basePackages = "com.example.store.remote"
)
~~~

The registrar can use package metadata to locate client interfaces and register corresponding proxy/client beans. This is the exact capability integration libraries often need: the user declares one annotation; the library handles advanced registration.

However, a registrar is a lower-level extension point than component scanning or `@Bean`. Only use it when programmatic control over bean definitions is required. If a fixed bean can be described with a `@Bean` method, use that simpler approach.

## 15. Advanced Scenario: Registering Clients for Specified Interfaces

A library might want to support an annotation like:

~~~java
@EnableRemoteClients({
        CustomerClient.class,
        InventoryClient.class
})
@Configuration
public class RemoteClientConfiguration {
}
~~~

Each client interface must be registered as a proxy bean. The registrar can read the class list from metadata and create a bean definition for a factory/proxy class with the specified interface as a constructor argument.

General idea:

~~~java
for (Class<?> clientInterface : clientInterfaces) {
    validateClientInterface(clientInterface);

    BeanDefinition definition =
            BeanDefinitionBuilder
                    .genericBeanDefinition(RemoteClientFactoryBean.class)
                    .addConstructorArgValue(clientInterface)
                    .getBeanDefinition();

    registry.registerBeanDefinition(
            beanNameFor(clientInterface),
            definition
    );
}
~~~

Here `RemoteClientFactoryBean` is an infrastructure component defined by the library. It can create a proxy that executes HTTP requests when interface methods are called. The registrar only registers the factory bean definition; proxy and network logic reside inside the factory or adapter.

Keep in mind:

- Accept only valid interfaces, not arbitrary classes.
- Determine non-conflicting bean names.
- Handle annotations configuring endpoints, timeouts, or codecs.
- Do not make network requests while the registrar is running.
- Defer connection/client creation to an appropriate lifecycle phase.
- Fail early on misconfiguration with clear error messages.

This illustrates the value of a registrar: a single annotation can generate multiple bean definitions from metadata instead of forcing users to declare every factory method manually.

## 16. Handling Duplicates and Idempotency

A registrar may participate in complex configuration processing, such as multiple annotations or modules importing the same registrar. Therefore, consider duplication carefully:

- Can the registrar be invoked with the same metadata multiple times?
- Might two configurations request the same bean name?
- Could a bean definition already be registered by another configuration?
- Should duplicates be skipped, fail, or replace?

An explicit policy is usually better than letting the registry silently handle overrides. For example, if bean names must be unique:

~~~java
if (registry.isBeanNameInUse(beanName)) {
    throw new BeanDefinitionStoreException(
            "Duplicate connector name: " + beanName
    );
}
registry.registerBeanDefinition(beanName, definition);
~~~

If the same registrar may be invoked repeatedly with the same configuration and idempotency is desired, inspect the existing bean definition, verify it matches the expected class/metadata, and then skip. Never check only the name and silently ignore everything, because that name might already be used by another configuration for an unrelated bean.

## 17. Conditions, Profiles, and Registrars

A registrar can read annotation metadata to decide registration, but it should not rebuild all of Spring Boot's conditional infrastructure.

If the requirement is simply enabling a bean based on a property:

~~~java
@Configuration
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
)
public class AuditConfiguration {

    @Bean
    public AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }
}
~~~

This is usually far more readable than a registrar manually reading properties and registering definitions.

If the requirement is selecting a bean by profile:

~~~java
@Bean
@Profile("prod")
public PaymentGateway livePaymentGateway() {
    return new LivePaymentGateway();
}
~~~

`@Profile` clearly indicates that the bean is provided only in the corresponding profile.

Choose a registrar when registration logic requires dynamic metadata/definitions—for example, generating N beans from a list in an annotation, registering proxies for multiple interfaces, or wiring a module via an enable annotation. **Do not use a registrar to overcomplicate configuration that can be written using standard `@Bean` or conditions.**

## 18. Testing Registrars

A registrar is infrastructure code, so verify two aspects:

1. Are bean definitions registered properly from metadata?
2. Can the ApplicationContext instantiate and provide beans according to those definitions?

A simple test creates a small context with a configuration using the enable annotation:

~~~java
@Configuration
@EnableConnectors({"orders", "billing"})
static class TestConfiguration {
}
~~~

~~~java
@Test
void registersConnectorBeans() {
    try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                         TestConfiguration.class
                 )) {

        NamedConnector orders =
                context.getBean(
                        "ordersConnector",
                        NamedConnector.class
                );

        NamedConnector billing =
                context.getBean(
                        "billingConnector",
                        NamedConnector.class
                );

        assertEquals("orders", orders.connectorName());
        assertEquals("billing", billing.connectorName());
    }
}
~~~

This test snippet assumes `EnableConnectors`, `ConnectorRegistrar`, and `NamedConnector` are defined as in the earlier example, along with appropriate JUnit/Spring imports.

### Testing the Empty Case

If the annotation supplies no connectors:

~~~java
@EnableConnectors
@Configuration
static class EmptyConfiguration {
}
~~~

The test should confirm the registrar does not register unexpected connector beans. This exercises the annotation's default value and empty-list handling branch.

### Testing Duplicate Names

You can create a bean named `ordersConnector` via another configuration and enable the registrar requesting the same name. The result should be a configuration error with a clear message if the registrar's policy is to reject duplicates.

### Testing Dependencies and Lifecycle

Successfully registering a definition does not prove the instance can be constructed. Let the context instantiate the bean and confirm constructor arguments, dependencies, and lifecycle metadata are applied properly. If the bean has init/destroy methods, close the context in the test and verify cleanup runs according to scope.

## 19. Common Mistakes When Using Registrars

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Registrar does not run | Registrar class was not included via `@Import` or the configuration bearing the annotation was not processed | Verify configuration registration and enable annotation |
| Cannot read annotation attributes | Wrong annotation type/name or annotation absent from importing class metadata | Use the exact fully qualified annotation name and check for null |
| Bean definition registered but instantiation fails | Wrong constructor arguments, missing dependencies, or invalid class | Inspect `BeanCreationException` and definition metadata |
| `NoUniqueBeanDefinitionException` | Registrar registered multiple beans of the same type; consumer injects a single bean | Use qualifiers, primary, collections, or a resolver |
| Bean name conflict | Multiple configurations generate the same name | Add a namespace, check the registry, and enforce a duplicate policy |
| Bean registered twice | Registrar imported through multiple configurations or another registration source exists | Check all registration sources, not just a single import |
| Bean does not receive expected post-processing | Manually registered an instance instead of a definition or wrong lifecycle path | Register a `BeanDefinition` so the container manages it |
| Resources are not closed | Missing destroy metadata or scope does not manage cleanup via container | Configure a destroy method and clarify resource ownership |

### Do Not Confuse Registrars with Component Scanning

A registrar class does not need to be annotated with `@Component` to work if it is already specified via `@Import`. Conversely, placing `@Component` on a registrar without any mechanism treating it as a registrar will not automatically cause Spring to invoke `registerBeanDefinitions`. It is an extension point for configuration imports.

### Do Not Register Bean Definitions Arbitrarily After Context Initialization

`BeanDefinitionRegistry` is intended for the configuration registration phase. Mutating the registry after the application is already running may conflict with already-instantiated beans, resolved dependencies, created proxies, and internal caches. If you need to create objects dynamically at runtime, use a business factory/registry or a plugin management mechanism with an explicit lifecycle instead of arbitrarily modifying bean definitions.

## 20. Safe Registrar Design Workflow

When you need to build a registrar in a library or application:

1. **Confirm why a registrar is needed.** Do you genuinely need to generate multiple bean definitions from metadata, or are simple `@Bean`/`@Import` enough?
2. **Design the enable annotation.** Keep attributes concise, with clear defaults that express user intent.
3. **Identify the metadata source.** Read from `AnnotationMetadata` of the importing class; do not instantiate the configuration class just to read annotations.
4. **Validate inputs.** Check names, classes, interfaces, packages, or configuration attributes before registering.
5. **Choose stable bean names.** Include a namespace and a clear conflict policy.
6. **Build the BeanDefinition.** Configure class, constructor arguments, scope, lazy, primary, and lifecycle as needed.
7. **Register via the registry.** Do not manually instantiate objects if you want Spring to manage the full lifecycle.
8. **Let the container resolve dependencies.** Do not call `ApplicationContext` or manually construct the entire graph with `new` inside the registrar.
9. **Test both metadata and instances.** Verify definitions are registered and beans can be instantiated.
10. **Keep logic at the infrastructure layer.** Registrars should not contain per-request business rules or call external services on startup.

## Conclusion

`ImportBeanDefinitionRegistrar` is an extension point that lets a library or module participate in `@Import` processing and register bean definitions based on metadata. It is especially useful for enable-style annotations, plugin modules, client proxies, or cases requiring multiple beans generated from user-declared classes or names.

A registrar works with `AnnotationMetadata` and `BeanDefinitionRegistry`. It tells Spring how to create beans rather than manually instantiating objects and pushing them into the container. When choosing tools, distinguish clearly: `@Bean` fits explicit factory methods; `ImportSelector` chooses configurations to import; `ImportBeanDefinitionRegistrar` registers dynamic definitions; `BeanDefinitionRegistryPostProcessor` handles context-level registry processing; `FactoryBean` creates bean products.

Use a registrar when the problem truly demands advanced registration. Keep bean names stable, check for conflicts, let the container manage lifecycles, and test both definitions and instances. In doing so, Spring Boot configurations can scale flexibly while keeping the object graph understandable and controllable.
