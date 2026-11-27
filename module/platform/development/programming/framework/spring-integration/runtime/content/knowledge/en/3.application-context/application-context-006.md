# IntegrationObjectSupport Logger and Resource Name

In Spring Integration, many internal components share a set of foundational needs: recognizing the bean name, accessing `BeanFactory` and `ApplicationContext`, obtaining a `TaskScheduler` or `ConversionService`, initializing with the Spring lifecycle, and logging. `IntegrationObjectSupport` groups these capabilities into one base class so channels, endpoints, handlers, and transformers can share them.

Two details frequently encountered when reading source code or diagnosing runtime behavior are the `logger` and the component's identifying name. The logger indicates which Java class produced a log entry; the component name indicates which instance in the integration flow emitted it. Distinguishing these two pieces of information makes log reading accurate, especially when a class has multiple beans or when multiple endpoints are created from the same handler type.

## 1. Role of IntegrationObjectSupport

`IntegrationObjectSupport` resides in the `org.springframework.integration.context` package. It is an abstract base class for framework components. Direct or indirect subclasses include `AbstractEndpoint`, `AbstractMessageChannel`, `AbstractTransformer`, `MessageHandlerSupport`, and `AbstractConnectionFactory`.

This class integrates with the Spring lifecycle through interfaces such as `BeanNameAware`, `BeanFactoryAware`, `ApplicationContextAware`, and `InitializingBean`, while also providing identification through `NamedComponent`. In newer versions, it also implements `ComponentSourceAware` to retain configuration source metadata for the bean. These utilities serve framework components; ordinary business code should prefer constructor injection and standard dependency injection rather than depending directly on `ApplicationContext`.

Commonly used capabilities from this base class:

| Member | Purpose |
|---|---|
| `logger` | Pre-configured logger available to subclasses |
| `getBeanName()` | Retrieves the bean name assigned by the Spring container |
| `getComponentName()` | Retrieves the component's logical name; defaults to bean name if no custom name is set |
| `setComponentName(String)` | Sets a custom logical name for the component |
| `getComponentType()` | Provides the component type; subclasses can override |
| `getBeanFactory()` | Accesses `BeanFactory` from subclasses |
| `getApplicationContext()` | Accesses `ApplicationContext` from subclasses |
| `getTaskScheduler()` | Retrieves the shared scheduler when the component needs scheduling |
| `getConversionService()` | Retrieves the type conversion service |
| `getChannelResolver()` | Resolves a channel name to a `MessageChannel` |
| `onInit()` | Hook for subclasses to execute initialization logic |

Not every subclass uses all of these utilities. `IntegrationObjectSupport` provides the common baseline; actual behavior also depends on the subclass and the bean's configuration.

## 2. The Inherited Logger

In Spring Integration 6.x, `IntegrationObjectSupport` provides the field `protected final LogAccessor logger`. Because the field has `protected` visibility, subclasses can log directly without creating a new logger. `LogAccessor` is a Spring Core utility class offering `trace`, `debug`, `info`, `warn`, and `error` levels along with log-level check methods.

For example, a component can log during initialization and when receiving messages:

~~~java
public class AuditMessageHandler extends IntegrationObjectSupport
        implements MessageHandler {

    @Override
    public String getComponentType() {
        return "audit-handler";
    }

    @Override
    protected void onInit() {
        logger.info(() -> "Initialized component '" + getComponentName()
                + "' with type '" + getComponentType() + "'");
    }

    @Override
    public void handleMessage(Message<?> message) {
        logger.debug(() -> "component='" + getComponentName()
                + "', messageId='" + message.getHeaders().getId() + "'");
    }
}
~~~

Main imports:

~~~java
import org.springframework.integration.context.IntegrationObjectSupport;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
~~~

The base class `logger` is created for the instance's actual runtime class, so the logger category is typically the fully qualified name of the subclass, such as `com.example.integration.AuditMessageHandler`. If there are multiple `AuditMessageHandler` beans, they still share this logger category. To know which instance emitted a log entry, include `getComponentName()` in the log message.

Overloads accepting a `Supplier` enable deferred construction of log messages:

~~~java
logger.debug(() -> "component='" + getComponentName()
        + "', messageId='" + message.getHeaders().getId() + "'");
~~~

This is appropriate for debug messages involving string concatenation or additional computation. When DEBUG level is disabled, the content inside the supplier does not need to be evaluated. When logging errors, preserve the exception so the stack trace is not lost:

~~~java
logger.error(exception,
        () -> "Failed to process message in '" + getComponentName() + "'");
~~~

Do not redeclare a field named `logger` in a subclass if the goal is simply to use the available logger. Shadowing the inherited field makes it harder for readers to tell which logger a statement uses and can create two different logger categories. If a separate logger is needed for a special purpose, give the field a different name and explain why clearly.

### Logger Category Is Not Component Name

A logger category belongs to the logging system and is usually selected by class or package. You can adjust log levels via logging configuration, for example:

~~~yaml
logging:
  level:
    com.example.integration: DEBUG
~~~

A bean name or component name does not automatically become a logging category. If you need to filter logs for a specific instance, write the component name as a field in the log message or put it into MDC according to the application's context propagation rules. For executor-based processing, do not assume MDC on the sending thread is automatically present on worker threads.

## 3. Bean Name and Component Name

`IntegrationObjectSupport` has two related but distinct identification concepts.

**Bean name** is the bean's name in the Spring container. When a bean implements `BeanNameAware`, Spring calls `setBeanName(String)` during bean creation. `IntegrationObjectSupport` provides a `final` implementation of `setBeanName`, so subclasses cannot override this method. You can read the assigned name with `getBeanName()`.

**Component name** is the logical name Spring Integration uses to identify the component in the integration context. You can set this name with `setComponentName(String)`. `getComponentName()` returns the configured component name; if none was set, it uses the bean name as the default.

For example, if a bean is declared with the name `auditMessageHandler` and no separate component name is set, the typical result is:

~~~java
getBeanName();      // "auditMessageHandler"
getComponentName(); // "auditMessageHandler"
~~~

If a custom logical name is set:

~~~java
setComponentName("orders.audit");

getBeanName();      // "auditMessageHandler"
getComponentName(); // "orders.audit"
~~~

A custom name allows the component name to reflect its role in the flow rather than merely reflecting the Java type or bean factory method name. Choose short, stable names that are easy to search in logs, graphs, or monitoring configurations.

| Information | Example | Used for |
|---|---|---|
| Logger category | `com.example.integration.AuditMessageHandler` | Selecting log levels by class/package |
| Bean name | `auditMessageHandler` | Identifying the bean in the Spring container |
| Component name | `orders.audit` | Identifying the component in the integration flow and operational data |
| Component type | `audit-handler` | Describing the kind of component |

In some documentation or discussions, "resource name" may be used in the sense of a name identifying a runtime component. With `IntegrationObjectSupport`, the APIs to inspect first are `getComponentName()` and `getBeanName()`; this class does not have a general `resourceName` property representing a file path. When referring to files, classpath entries, or URLs, that belongs to Spring Core's `Resource`/`ResourceLoader` concept and is a different mechanism.

## 4. Setting Component Name in Java Configuration

When creating a bean manually, you can set the component name before Spring finishes bean initialization:

~~~java
@Configuration
@EnableIntegration
public class AuditIntegrationConfiguration {

    @Bean
    AuditMessageHandler auditMessageHandler() {
        AuditMessageHandler handler = new AuditMessageHandler();
        handler.setComponentName("orders.audit");
        return handler;
    }

    @Bean
    IntegrationFlow auditFlow(AuditMessageHandler auditMessageHandler) {
        return IntegrationFlow.from("orders.audit.input")
                .handle(auditMessageHandler)
                .get();
    }
}
~~~

Spring still assigns the bean name `auditMessageHandler` via `BeanNameAware`. Because the component name was set, `getComponentName()` returns `orders.audit`. In logs, you can output both when correlating container configuration with flow diagrams.

Explicit naming is particularly useful when a flow has multiple endpoints sharing one handler class, when registering flows dynamically, or when comparing names in logs with component names displayed in topology views. Avoid using customer IDs, tokens, or per-message dynamic values as component names; those are runtime data and make component identifiers unstable.

## 5. Component Type, Description, and Source

Beyond the name, `NamedComponent` also provides `getComponentType()`. Subclasses can override it to describe the component type, such as `channel`, `service-activator`, or an application-specific type. Name and type serve different purposes: name identifies the instance, type classifies the instance.

In versions supporting `ComponentSourceAware`, `IntegrationObjectSupport` can also retain:

- `getComponentDescription()`: a human-readable description of the bean, typically taken from the `BeanDefinition` if not set explicitly.
- `getComponentSource()`: the configuration source object, which may be `null` if no source information is available.
- `getBeanDescription()`: bean description metadata provided by the base class.

This metadata is useful for introspection tools and configuration diagnostics. It does not replace the component name and should not be used as a stable identification key. In particular, the component source can be a configuration metadata object, not necessarily a file path string.

## 6. Initialization Lifecycle and the onInit Hook

`IntegrationObjectSupport` implements `InitializingBean`. Spring calls `afterPropertiesSet()` after applying aware callbacks and configuring bean properties. The base class's `afterPropertiesSet()` method is `final`; it prepares required internal utilities and then calls `onInit()` so subclasses can perform initialization work.

General flow:

~~~mermaid
flowchart TD
    A[Spring creates bean] --> B[BeanNameAware.setBeanName]
    B --> C[BeanFactoryAware / ApplicationContextAware]
    C --> D[Apply properties and dependencies]
    D --> E[IntegrationObjectSupport.afterPropertiesSet]
    E --> F[Prepare Integration utilities]
    F --> G[Subclass.onInit]
    G --> H[Component ready for runtime]
~~~

Therefore, subclasses should override `onInit()` for logic that must run after dependencies and context have been provided. Do not override `afterPropertiesSet()`; that method is already managed by the base class. Also avoid using constructors to access `BeanFactory`, `ApplicationContext`, or component name because Spring's callbacks have not completed when the constructor runs.

For instance, `onInit()` can validate internal configuration and log a line containing the component name. Avoid performing long I/O work or launching unmanaged threads here; task lifecycles and shutdown must follow Spring's lifecycle management mechanism.

## 7. Using Component Names for Runtime Diagnostics

When investigating a failing message, combine the component identifier with message identification keys. A useful log entry might contain:

- Component name and component type.
- Message ID to locate a specific message.
- Correlation ID to group messages belonging to the same business workflow.
- Channel or endpoint name if the component processes at a specific point.
- Processing outcome, duration, or exception to investigate.

Example:

~~~java
logger.debug(() -> "component='" + getComponentName()
        + "', type='" + getComponentType()
        + "', messageId='" + message.getHeaders().getId()
        + "', correlationId='" + message.getHeaders().get("correlationId")
        + "'");
~~~

Do not log the entire payload just to identify a message. Payloads may contain personal data, business secrets, or large data volumes. IDs and component names are usually enough to connect logs with Message History, the Integration Graph, and metrics. If additional business data must be logged, restrict allowed fields and apply masking rules.

Another note: `IntegrationObjectSupport` only provides the underlying logger. Enabling/disabling main-path logging via `IntegrationManagement.setLoggingEnabled(...)` belongs to components implementing `IntegrationManagement`, such as many channels and message handlers. You cannot infer that every subclass of `IntegrationObjectSupport` has a `loggingEnabled` property merely because it inherits `logger`.

## 8. Common Misconceptions to Avoid

| Misconception | Correct understanding |
|---|---|
| Logger name is the bean name | Logger category is usually by class; bean name and component name are separate metadata |
| `getBeanName()` always equals `getComponentName()` | They are equal only when no custom component name has been set |
| Component name is the configuration file name | It is the component's logical name; configuration source metadata is represented separately |
| `IntegrationObjectSupport` has `resourceName` for every component | The common identification API is bean name/component name; `Resource` paths belong to a different Spring Core mechanism |
| `afterPropertiesSet()` can be overridden | This method is `final`; use `onInit()` for subclass initialization logic |
| The inherited logger automatically shows which instance logged | Multiple instances of the same class share one logger category; include `getComponentName()` in the log message |
| Every subclass has `setLoggingEnabled()` | Only components implementing `IntegrationManagement` expose that logging management contract |

## 9. Checklist When Building a Component

- [ ] Extend `IntegrationObjectSupport` only when the component genuinely needs Spring Integration utilities and lifecycle hooks.
- [ ] Use the inherited `protected` logger; avoid shadowing the `logger` field without a clear reason.
- [ ] Include `getComponentName()` in logs to distinguish instances of the same class.
- [ ] Set a component name that is short, stable, and meaningful within the flow.
- [ ] Override `getComponentType()` if observability tools need custom component classification.
- [ ] Apply configuration before the `afterPropertiesSet()` phase and use `onInit()` for initialization logic.
- [ ] Log message ID/Correlation ID instead of dumping the entire payload.
- [ ] Only use `setLoggingEnabled()` when the component actually implements `IntegrationManagement`.

By separating logger category, bean name, and component name, logs tell you both which Java class emitted an event and which instance in the integration flow processed it. `IntegrationObjectSupport` provides these hooks alongside lifecycle integration and context utilities; using each concept properly makes components easier to observe and diagnose.

## References

- [Spring Integration 6.4 API: IntegrationObjectSupport](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/context/IntegrationObjectSupport.html)
- [Spring Integration API: NamedComponent](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/support/context/NamedComponent.html)
- [Spring Integration API: IntegrationManagement](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/support/management/IntegrationManagement.html)
- [Spring Framework API: LogAccessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/log/LogAccessor.html)
