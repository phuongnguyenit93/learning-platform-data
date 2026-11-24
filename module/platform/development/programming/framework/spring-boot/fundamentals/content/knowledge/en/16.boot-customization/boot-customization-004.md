# Distinguishing beans of the same type from beans with the same name

In Spring Boot, an application can have multiple beans implementing the same interface, such as multiple implementations of `NotificationSender`, `PaymentGateway`, or `DataSource`. This is completely valid as long as each bean has its own identifier and the application knows how to pick the appropriate bean when needed.

Another situation that easily causes confusion is when two configurations register beans with the same name. In that case, the problem is no longer having multiple beans of the same type, but an **identifier conflict within the same Spring container**. Spring manages bean definitions in a registry; one bean name can represent only one definition at a time.

To organize dependencies properly, you must distinguish:

- **Type** indicates which Java types a bean can be used as.
- **Bean name** is the bean's identifier in the container.
- **Alias** is an additional name pointing to the same bean.
- **Qualifier** is metadata used to filter candidates during injection.
- **Primary** marks the preferred candidate in certain single-bean selection scenarios.

This lesson explains those concepts, how Spring selects beans by type or name, common errors when there are multiple candidates or duplicate names, and how to handle them in Spring Boot Java configuration.

## 1. Bean type and bean name are two different attributes

A bean in Spring is managed by the container through a bean definition and an instance. When using a bean, you can usually look it up by **type** or by **name**.

For example:

```java
@Component("emailSender")
public class EmailNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        // Send email.
    }
}
```

In this example:

- The concrete type is `EmailNotificationSender`.
- The bean can also be looked up via the `NotificationSender` interface because the class implements that interface.
- The bean name is explicitly declared as `emailSender`.

You can request the bean in two ways:

```java
NotificationSender sender =
        applicationContext.getBean("emailSender", NotificationSender.class);

EmailNotificationSender implementation =
        applicationContext.getBean(EmailNotificationSender.class);
```

The first way looks up by name and checks type compatibility. The second looks up the bean by type. The two access methods do not share the same resolution rules.

### 1.1. Type answers "what kind of bean is this?"

Type is a Java type that the bean satisfies. When a class implements an interface, its instance can be looked up through the interface or compatible supertypes.

For example:

```java
public interface NotificationSender {
    void send(String recipient, String message);
}

@Component
class EmailNotificationSender implements NotificationSender {
    // ...
}

@Component
class SmsNotificationSender implements NotificationSender {
    // ...
}
```

Both beans are compatible with the `NotificationSender` type. A query by the interface type can find both.

### 1.2. Name answers "how is this bean identified?"

A bean name is the name used in the container to register and look up a bean. If using component scanning without an explicit name, Spring usually generates a default name from the class name with a lowercase first letter:

| Class | Common default bean name |
| --- | --- |
| `EmailNotificationSender` | `emailNotificationSender` |
| `SmsNotificationSender` | `smsNotificationSender` |
| `URLFormatter` | `URLFormatter` per JavaBeans decapitalize rules when both the first and second characters are uppercase |

Default names are a convenient convention. When a bean name is part of a configuration contract, give it an explicit name so readers do not have to guess.

### 1.3. Multiple beans of the same type is normal

An interface can have multiple implementations. Each implementation can be registered as a separate bean with its own name:

```text
Bean name                  Bean type
------------------------------------------------
emailSender                NotificationSender
smsSender                  NotificationSender
consoleSender              NotificationSender
```

This is not an error. It only becomes an issue when an injection point requests **a single** `NotificationSender` and Spring finds multiple candidates without a sufficiently clear selection rule.

### 1.4. One bean can have multiple types

An instance of `EmailNotificationSender` can be looked up by its concrete type, the `NotificationSender` interface, or another parent interface the class implements. Therefore, "one bean" does not mean "one type."

In other words:

- One type can match multiple beans.
- One bean can match multiple types.
- Bean name identifies the bean in the container; type defines the type views the bean satisfies.

## 2. One class can create multiple beans of the same type with different names

You do not necessarily need multiple implementation classes to have multiple beans of the same type. One class can be used to create multiple beans with different configurations.

Example of an HTTP client with a timeout configuration:

```java
public class PartnerClient {

    private final Duration timeout;

    public PartnerClient(Duration timeout) {
        this.timeout = timeout;
    }

    public Duration timeout() {
        return timeout;
    }
}
```

Java configuration:

```java
@Configuration(proxyBeanMethods = false)
public class PartnerClientConfiguration {

    @Bean("fastPartnerClient")
    PartnerClient fastPartnerClient() {
        return new PartnerClient(Duration.ofSeconds(2));
    }

    @Bean("slowPartnerClient")
    PartnerClient slowPartnerClient() {
        return new PartnerClient(Duration.ofSeconds(15));
    }
}
```

The context has two beans:

| Bean name | Type | Configuration value |
| --- | --- | --- |
| `fastPartnerClient` | `PartnerClient` | 2 seconds |
| `slowPartnerClient` | `PartnerClient` | 15 seconds |

Two beans share the same type but have different names. When selecting a specific client, you can use a qualifier or look it up by name.

This is useful when the same implementation serves two different roles, such as:

- A client calling internal APIs and a client calling partner APIs.
- A read data source and a write data source.
- A serializer for JSON format and a serializer for CSV format.
- A short-lived cache and a cache with a longer retention time.

However, if two beans only differ by a configuration value with no separate usage reason, consider whether you need two beans or just one bean receiving the appropriate configuration.

## 3. Looking up by type

Spring can look up a bean by type:

```java
NotificationSender sender =
        applicationContext.getBean(NotificationSender.class);
```

Or retrieve all matching beans:

```java
Map<String, NotificationSender> senders =
        applicationContext.getBeansOfType(NotificationSender.class);
```

The two operations have different meanings:

- `getBean(NotificationSender.class)` requires a single resolvable candidate according to container rules.
- `getBeansOfType(NotificationSender.class)` returns matching beans as a map keyed by bean name.

### 3.1. No matching bean

If no bean is compatible with the requested type, Spring may throw `NoSuchBeanDefinitionException`.

For example:

```java
PaymentGateway gateway =
        applicationContext.getBean(PaymentGateway.class);
```

If the context has no bean implementing `PaymentGateway`, this request fails.

Possible causes:

- The implementation has not been registered.
- The class is outside the component scan scope.
- The configuration creating the bean has not been imported.
- The bean was excluded by `@Profile` or `@Conditional...`.
- The module providing the implementation is not on the runtime classpath.

### 3.2. Multiple beans of the same type

If two beans both match `NotificationSender` and there is no selection criterion, requesting a single bean can fail with `NoUniqueBeanDefinitionException`.

For example:

```java
@Service
class RegistrationService {

    private final NotificationSender sender;

    RegistrationService(NotificationSender sender) {
        this.sender = sender;
    }
}
```

If the context has both `emailSender` and `smsSender`, the constructor above does not specify which implementation the service wants to use.

This is a **type ambiguity** error, not a duplicate bean name error.

### 3.3. Retrieving all beans by type

If the application needs all implementations, do not ask for a single bean. Inject a collection:

```java
@Service
class NotificationBroadcastService {

    private final List<NotificationSender> senders;

    NotificationBroadcastService(List<NotificationSender> senders) {
        this.senders = senders;
    }

    void broadcast(String recipient, String message) {
        senders.forEach(sender -> sender.send(recipient, message));
    }
}
```

Spring supplies the beans compatible with `NotificationSender` into the collection. This expresses the exact intent: "use all senders."

With `Map<String, NotificationSender>`, keys are typically bean names and values are instances. This is useful when you need to iterate or look up multiple implementations by identifier.

## 4. Looking up by bean name

When you know the bean name, you can ask the container for the bean by name:

```java
NotificationSender email =
        applicationContext.getBean("emailSender", NotificationSender.class);
```

The method taking both name and type verifies that the bean with that name has a compatible type. If you only use:

```java
Object bean = applicationContext.getBean("emailSender");
```

the result has declared type `Object`, so the code usually needs a cast or type check.

### 4.1. Name lookup does not mean type is unimportant

Spring still creates and manages beans with type, dependencies, and metadata. Looking up by name only identifies **which identifier** to retrieve. When using the overload with a type, the container checks whether the found bean is compatible with the requested type.

If the name does not exist, `NoSuchBeanDefinitionException` can occur. If the name exists but the type is incompatible with the requested type, retrieving the bean can fail due to a type mismatch.

### 4.2. Bean names are scoped to a container

Bean names are managed inside a registry/application context. Two independent application contexts can both have a bean named `dataSource` without colliding in each other's registries. In a parent-child context hierarchy, a child context can have a bean with the same name, and lookups in the child context can shadow the bean of the same name from the parent context.

Within a single context, treat bean names as unique identifiers. Do not rely on having multiple definitions with the same name to represent multiple implementations.

## 5. Beans with the same name are a different situation

In a bean registry, one bean name represents only one bean definition at a time. If two configurations both register a definition named `paymentGateway`, they are competing for the same identifier.

For example:

```java
@Configuration
class DefaultPaymentConfiguration {

    @Bean("paymentGateway")
    PaymentGateway paymentGateway() {
        return new DemoPaymentGateway();
    }
}
```

Another configuration:

```java
@Configuration
class PartnerPaymentConfiguration {

    @Bean("paymentGateway")
    PaymentGateway paymentGateway() {
        return new PartnerPaymentGateway();
    }
}
```

Both methods declare the bean name `paymentGateway`. Within the same context, this is a bean name collision.

### 5.1. Default behavior in modern Spring Boot

In modern Spring Boot versions, bean definition overriding is typically disabled by default. If two configurations register the same bean name, context initialization may fail with `BeanDefinitionOverrideException`.

This helps detect duplicate-name configurations early rather than silently replacing one definition with another.

Spring Framework provides a mechanism to allow bean definition overriding depending on registry configuration. Spring Boot provides the property:

```properties
spring.main.allow-bean-definition-overriding=true
```

to re-enable bean definition overriding behavior when necessary.

Do not enable this property just to make the error disappear. If two configurations accidentally use the same name, overriding can hide wiring bugs and make the selected implementation depend on registration order.

### 5.2. When overriding is enabled

If the registry allows overriding, a later-registered definition can replace an existing definition of the same name. The result is that the container holds only one definition under that name; two beans do not coexist side by side under the same name.

This differs from having two beans of the same type with different names:

```text
Two beans of the same type, different names:
  emailSender -> EmailNotificationSender
  smsSender   -> SmsNotificationSender
  => Both can exist.

Two definitions with the same name:
  paymentGateway -> DemoPaymentGateway
  paymentGateway -> PartnerPaymentGateway
  => Conflict, or one definition overrides the other,
     depending on registry configuration.
```

### 5.3. Duplicate names are not solved by @Primary

`@Primary` only affects selection among candidate beans of the same type where a single bean is needed. It does not allow two independent bean definitions to occupy the same name in the registry.

If two `@Bean` methods have the same name, adding `@Primary` to one method does not resolve the bean name conflict. You need to rename one bean, remove one configuration, use appropriate conditions, or intentionally design a replacement mechanism.

## 6. Alias: multiple names pointing to the same bean

Spring supports aliases so one bean can be looked up by multiple names. An alias does not create an extra bean instance and does not create an independent bean definition.

Example with `@Bean`:

```java
@Configuration(proxyBeanMethods = false)
class DataSourceConfiguration {

    @Bean(name = {"primaryDataSource", "dataSource"})
    DataSource primaryDataSource() {
        return createDataSource();
    }
}
```

In this example, `primaryDataSource` is the bean name and `dataSource` is an alias. Both names point to the same bean.

You can picture it as:

```text
primaryDataSource ─┐
                   ├──> the same DataSource instance
dataSource ────────┘
```

Aliases are useful when you need to keep an old name for compatibility with existing configuration or code while renaming a bean. However, too many aliases can make configuration harder to read; keep one primary name and only add aliases when genuinely needed.

### 6.1. Declaring aliases with @Bean

The `name` attribute of `@Bean` can accept multiple names:

```java
@Bean(name = {"mainClock", "systemClock"})
Clock clock() {
    return Clock.systemUTC();
}
```

Both names can be used to look up the same bean:

```java
Clock first = context.getBean("mainClock", Clock.class);
Clock second = context.getBean("systemClock", Clock.class);
```

For a singleton bean, lookups via the primary name and the alias return the same instance. For other bean scopes, the scope's instance creation rules still apply; aliases do not change scope.

### 6.2. Alias vs. two beans of the same type

If you have:

```java
@Bean("mainClock")
Clock mainClock() {
    return Clock.systemUTC();
}

@Bean("testClock")
Clock testClock() {
    return Clock.fixed(
            Instant.parse("2025-01-01T00:00:00Z"),
            ZoneOffset.UTC
    );
}
```

then there are two distinct bean definitions of the same `Clock` type and two separate singleton instances. Only if `testClock` is an alias of `mainClock` do they point to one bean definition and one instance.

## 7. Selection rules when injecting by type

With constructor injection:

```java
@Service
class ReportService {

    private final ReportExporter exporter;

    ReportService(ReportExporter exporter) {
        this.exporter = exporter;
    }
}
```

Spring resolves the dependency based on type and selection metadata. At a high level:

1. Find beans whose type is compatible with `ReportExporter`.
2. Apply qualifiers requested at the injection point.
3. If multiple candidates remain, consider priority criteria such as `@Primary` and related selection rules.
4. In some situations, the parameter/field name can help resolve a candidate when the name matches a bean name and no stronger criterion applies.
5. If a unique bean still cannot be determined for a single dependency, Spring reports an ambiguity error.

This description explains how beans are selected; exact ordering depends on injection point type and Spring version. When you need a stable selection, declare an explicit qualifier rather than relying on parameter names.

### 7.1. @Primary: selecting a default bean

`@Primary` marks a bean as the preferred candidate when multiple beans share a type and an injection point needs a single bean.

```java
@Component
@Primary
class CsvReportExporter implements ReportExporter {
    // ...
}

@Component
class PdfReportExporter implements ReportExporter {
    // ...
}
```

A service accepting `ReportExporter` without a qualifier can receive the primary bean if other criteria do not change the outcome.

`@Primary` does not remove the remaining beans from the context. They can still be looked up by name, injected via qualifiers, or received in collections.

### 7.2. @Qualifier: filtering specific candidates

`@Qualifier` lets you state explicitly that the injection point needs a bean carrying the corresponding qualifier:

```java
@Service
class PdfReportService {

    private final ReportExporter exporter;

    PdfReportService(
            @Qualifier("pdfReportExporter")
            ReportExporter exporter
    ) {
        this.exporter = exporter;
    }
}
```

A qualifier can use a bean name as a fallback criterion, but its essence is candidate-filtering metadata. You can create custom qualifier annotations to express traits like `@Regional("asia")` or `@StorageType("durable")`.

### 7.3. @Primary and @Qualifier have different roles

| Mechanism | Purpose |
| --- | --- |
| `@Primary` | Mark the preferred default bean |
| `@Qualifier` | Specify the required trait/label at the injection point |
| Bean name | Identify the bean in the container |
| Alias | Additional name for the same bean |

If a service always needs PDF, the `pdf` qualifier expresses intent more clearly than relying on an application-wide primary bean. If most services need CSV and only one special service needs PDF, you can use primary for CSV and a qualifier for PDF.

## 8. Injecting by name vs. injecting by type

Spring has several ways to declare dependencies. They have different resolution rules.

### 8.1. @Autowired typically resolves by type

For example:

```java
@Autowired
private NotificationSender sender;
```

Spring searches for beans matching the `NotificationSender` type. If there is only one candidate, it can inject directly. If there are multiple, a qualifier, primary, or another resolution criterion is needed.

With constructor injection:

```java
RegistrationService(NotificationSender sender) {
    this.sender = sender;
}
```

Spring also resolves dependencies by type. If there are multiple beans of the same type, the parameter name may participate in resolution under appropriate conditions, but you should not rely on this behavior instead of an explicit qualifier.

### 8.2. @Resource leans toward name-based injection

`@Resource` comes from Jakarta Annotations and is commonly used to request a dependency by name:

```java
@Resource(name = "emailSender")
private NotificationSender sender;
```

In this example, the name `emailSender` is explicitly specified. The resource injection mechanism looks up the resource by that name; if it cannot be resolved according to the corresponding rules, injection fails.

If `@Resource` is used without specifying `name` on a field or property, the default name is usually inferred from the field/property name. The mechanism may fall back to type according to Spring/Jakarta rules. Therefore, when exact selection by name is needed, explicitly set the `name` attribute.

### 8.3. Comparison

| Declaration | Common selection meaning |
| --- | --- |
| `@Autowired NotificationSender sender` | Type-based; may use qualifier/primary and additional resolution rules |
| `@Autowired @Qualifier("sms") NotificationSender sender` | Type-based then filtered by qualifier |
| `@Resource(name = "emailSender")` | Requests resource by name |
| `context.getBean("emailSender")` | Explicit lookup by bean name |
| `context.getBean(NotificationSender.class)` | Lookup by type; must resolve to one candidate |
| `context.getBeansOfType(NotificationSender.class)` | Retrieves all matching beans by type |

For new Spring applications, constructor injection is generally easier to test and expresses dependencies clearly. Choose type or name based on the meaning of the dependency, not just on which annotation has fewer characters.

## 9. How are default names generated?

### 9.1. Component scanning

When using:

```java
@Component
public class EmailNotificationSender {
}
```

Spring usually assigns the default bean name `emailNotificationSender`.

You can specify an explicit name:

```java
@Component("emailSender")
public class EmailNotificationSender {
}
```

Explicit names are useful when the bean name is used in configuration or at injection points. For classes used across multiple contexts or modules, choose a stable, meaningful name.

### 9.2. @Bean method

With:

```java
@Configuration
class ClockConfiguration {

    @Bean
    Clock systemClock() {
        return Clock.systemUTC();
    }
}
```

The method name `systemClock` is the default bean name. You can set a different name:

```java
@Bean("utcClock")
Clock systemClock() {
    return Clock.systemUTC();
}
```

With multiple names:

```java
@Bean(name = {"utcClock", "systemClock"})
Clock clock() {
    return Clock.systemUTC();
}
```

The first name is the primary bean name; the remaining names are aliases.

### 9.3. Bean names are case-sensitive

Use bean names consistently and treat names as exact identifier strings. `emailSender` and `EmailSender` should not be treated as interchangeable spellings. Avoid arbitrarily changing capitalization once a bean name is referenced in qualifiers, resource injection, or lookup code.

## 10. Bean name collisions across configurations

An application can import multiple configuration classes:

```java
@Configuration
class LocalCacheConfiguration {

    @Bean("cacheManager")
    CacheManager cacheManager() {
        return new LocalCacheManager();
    }
}

@Configuration
class RedisCacheConfiguration {

    @Bean("cacheManager")
    CacheManager cacheManager() {
        return new RedisCacheManager();
    }
}
```

If both configurations are processed in the same context, they both register the name `cacheManager`. This is a bean name collision.

### 10.1. Solution 1: use different names if both are truly needed

```java
@Bean("localCacheManager")
CacheManager localCacheManager() {
    return new LocalCacheManager();
}

@Bean("redisCacheManager")
CacheManager redisCacheManager() {
    return new RedisCacheManager();
}
```

Then select the bean via qualifier:

```java
CacheService(
        @Qualifier("redisCacheManager") CacheManager cacheManager
) {
    this.cacheManager = cacheManager;
}
```

### 10.2. Solution 2: activate only one configuration

If local cache is only for dev environments and Redis is used in production, you can use profiles:

```java
@Configuration
@Profile("dev")
class LocalCacheConfiguration {
    // ...
}

@Configuration
@Profile("prod")
class RedisCacheConfiguration {
    // ...
}
```

The two configurations should not be activated together if the goal is to have only one default bean named `cacheManager`. Profiles describe activation environments; they are not a way to name beans.

### 10.3. Solution 3: default configuration and custom bean

With auto-configuration, you can provide a default bean when the application does not yet have a corresponding bean:

```java
@AutoConfiguration
class CacheAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CacheManager.class)
    CacheManager cacheManager() {
        return new LocalCacheManager();
    }
}
```

When the application declares a matching bean itself, the auto-configuration can back off instead of registering a duplicate-named definition. This is a common pattern for libraries to provide defaults while allowing applications to customize.

## 11. Do not confuse bean name collisions with multiple beans of the same type

These two errors have different symptoms and fixes:

| Situation | Example | Possible error | How to handle |
| --- | --- | --- | --- |
| Multiple beans of the same type, different names | `emailSender`, `smsSender` both implement `NotificationSender` | `NoUniqueBeanDefinitionException` when a single bean is needed | `@Qualifier`, `@Primary`, inject collection |
| Two definitions with the same name in one registry | Two configurations both declare `paymentGateway` | `BeanDefinitionOverrideException` if overriding is disabled | Rename, drop redundant config, use condition/profile |
| No bean matching type | `PaymentGateway` not registered | `NoSuchBeanDefinitionException` or `UnsatisfiedDependencyException` | Check scan/import/dependency/condition |
| Invalid duplicate alias name | Alias name already used by another bean | Alias/definition registration error | Choose a non-conflicting alias |
| One bean with multiple aliases | `utcClock`, `systemClock` both point to one bean | Not a conflict if aliases are validly registered | Keep primary name and needed aliases |

When reading an exception, identify whether it refers to **the number of candidates by type** or **a bean identifier in the registry**. Adding `@Primary` does not fix a name collision; renaming beans does not automatically resolve every type ambiguity if multiple candidates still remain.

## 12. Type matching and @Bean return types

Spring predicts bean types from the class or factory method metadata. Therefore, the return type of a `@Bean` method affects which types the container can recognize before creating an instance.

For example:

```java
@Bean
NotificationSender notificationSender() {
    return new EmailNotificationSender();
}
```

The definition indicates the declared type is `NotificationSender`. This is the appropriate contract type if consumers only need the interface.

If a consumer requests `EmailNotificationSender` specifically, Spring may not determine the concrete type from the factory method metadata in certain early processing stages, especially when the method only declares an interface return type. Therefore, declare a sufficiently specific return type when the application truly needs to query by implementation class:

```java
@Bean
EmailNotificationSender emailNotificationSender() {
    return new EmailNotificationSender();
}
```

However, **do not declare a concrete type just to make consumers depend on an implementation** if an interface already expresses the contract sufficiently. Prefer injecting interfaces and use concrete types only when genuinely required.

With factory beans, proxies, or beans created by special mechanisms, type prediction can be more complex. When querying by type does not yield expected results, inspect the bean definition, factory method return type, and appropriate type introspection APIs.

## 13. Bean names and bean types with proxies

Spring AOP can wrap a bean in a proxy. A proxy may implement interfaces or subclass the target class depending on the proxy strategy.

For example:

```java
@Service
public class BillingService implements BillingOperations {

    @Transactional
    public void charge() {
        // ...
    }
}
```

When a proxy is present, the bean name remains the bean's identifier in the context, but the object received by consumers may be a proxy. The types exposed by the proxy depend on the proxy creation strategy.

Therefore:

- Looking up by bean name still finds the bean registered under that name.
- Looking up by an interface implemented by the proxy is generally appropriate.
- Looking up by concrete class can fail if the proxy is a JDK dynamic proxy.
- Do not assume the received object always has the exact runtime class of the original implementation.

This is another reason to design dependencies around interfaces when appropriate.

## 14. Parent-child contexts and beans with the same name

Spring can organize multiple application contexts in a parent-child relationship. Each context has its own registry.

Conceptual example:

```text
Parent ApplicationContext
  bean: dataSource -> SharedDataSource
        |
        v
Child WebApplicationContext
  bean: dataSource -> TenantDataSource
```

Both contexts can have a bean named `dataSource` without being two duplicate definitions in the same registry. When looking up from the child context, the same-named bean in the child can take precedence and shadow the bean from the parent context.

This is a different case from two configurations registering `dataSource` into a single registry.

In typical Spring Boot applications, most learners work with a single application context. However, when integrating multiple web contexts, management contexts, or modules with separate contexts, remember that bean name scope is **per container/registry**, not a global name across the entire JVM.

## 15. Practice: building an application with multiple senders

We will create three senders with three different names:

```java
public interface NotificationSender {
    void send(String recipient, String message);
}

@Component("emailSender")
class EmailSender implements NotificationSender {
    public void send(String recipient, String message) {
        System.out.println("EMAIL: " + recipient + " - " + message);
    }
}

@Component("smsSender")
class SmsSender implements NotificationSender {
    public void send(String recipient, String message) {
        System.out.println("SMS: " + recipient + " - " + message);
    }
}

@Component("consoleSender")
class ConsoleSender implements NotificationSender {
    public void send(String recipient, String message) {
        System.out.println("CONSOLE: " + recipient + " - " + message);
    }
}
```

### 15.1. Service needing email

```java
@Service
class WelcomeService {

    private final NotificationSender sender;

    WelcomeService(@Qualifier("emailSender") NotificationSender sender) {
        this.sender = sender;
    }

    void welcome(String email) {
        sender.send(email, "Welcome!");
    }
}
```

### 15.2. Service needing SMS

```java
@Service
class SecurityAlertService {

    private final NotificationSender sender;

    SecurityAlertService(@Qualifier("smsSender") NotificationSender sender) {
        this.sender = sender;
    }

    void alert(String phoneNumber) {
        sender.send(phoneNumber, "Security alert");
    }
}
```

Both services depend on `NotificationSender` yet receive different implementations thanks to qualifiers.

### 15.3. Service needing all senders

```java
@Service
class BroadcastService {

    private final Map<String, NotificationSender> senders;

    BroadcastService(Map<String, NotificationSender> senders) {
        this.senders = senders;
    }

    void broadcast(String recipient, String message) {
        senders.values().forEach(
                sender -> sender.send(recipient, message)
        );
    }
}
```

The injected map has bean names as keys and corresponding instances as values. The service can iterate over all senders without asking Spring to pick a single bean.

If you want only senders belonging to a group, you can attach a custom qualifier to those beans and inject a collection with that qualifier at the injection point.

### 15.4. Inspecting results with ApplicationContext

In an illustrative runner:

```java
@Bean
CommandLineRunner inspectSenders(ApplicationContext context) {
    return args -> {
        Map<String, NotificationSender> senders =
                context.getBeansOfType(NotificationSender.class);

        senders.forEach((name, sender) ->
                System.out.println(name + " -> " + sender.getClass().getName())
        );
    };
}
```

The output can show the three bean names sharing the interface type. If an AOP proxy or decorator is present, the runtime class displayed may be a proxy instead of the original implementation class.

## 16. How to troubleshoot when Spring reports an error

### 16.1. NoUniqueBeanDefinitionException

The message indicates that multiple beans of the same type match a single dependency.

Steps:

1. Read the requested type.
2. List the bean names of that type using the report or `getBeansOfType`.
3. Determine whether the service needs one specific implementation, a default bean, or the whole group.
4. Use `@Qualifier`, `@Primary`, or collection injection accordingly.

Do not delete an implementation just to make the error go away if the application genuinely needs multiple beans.

### 16.2. BeanDefinitionOverrideException

The message indicates that a bean definition is being registered under a name that already exists in the registry and overriding is not permitted.

Steps:

1. Identify the colliding bean name.
2. Find the configuration classes or components registering that name.
3. Determine whether both beans are needed or only one implementation.
4. If both are needed, rename them and inject explicitly.
5. If only one is needed, remove the redundant configuration via profiles/conditions or fix the registration source.

Do not enable global overriding as your first solution.

### 16.3. NoSuchBeanDefinitionException

No bean matches the requested name or type. Check:

- Has the bean been registered?
- Are the requested name and type correct?
- Is the configuration scanned/imported?
- Do profiles and conditions allow the bean to exist?
- Is the dependency containing the implementation on the classpath?

### 16.4. Bean found by name, but wrong type

If you use:

```java
context.getBean("emailSender", PaymentGateway.class);
```

while the `emailSender` bean only implements `NotificationSender`, the type request is incompatible. Check both name and type instead of assuming a bean name suffices to guarantee the type.

## 17. Checklist for choosing by type or name

When declaring a dependency, ask yourself:

1. **Does the service need a role or a concrete implementation?** If it only needs a role, inject the interface by type.
2. **Are there multiple beans of the same type?** If so, determine whether the service needs one bean or the entire group.
3. **Which bean is the default?** You can use `@Primary` if one implementation fits most injection points.
4. **Does the service require a specific trait?** Use `@Qualifier` or a custom qualifier.
5. **Does code need to look up a bean by identifier?** Use name lookup in infrastructure/registry code with a clear reason.
6. **Do two configurations register the same name?** Check bean definition collisions, aliases, and overriding settings.
7. **Are multiple names actually just aliases of the same bean?** Distinguish aliases from two separate definitions.
8. **Are multiple contexts in use?** Identify which registry owns the bean name.

A good design usually has services depend on types/contracts, while bean names and selection configurations live at the composition root or wiring layer. When a name is part of an integration API, give it an explicit, stable name.

## 18. Practice exercises

### Exercise 1 – Distinguish same type and same name

Create two classes `EmailSender` and `SmsSender` both implementing `NotificationSender`. Register them with bean names `emailSender` and `smsSender`.

Answer:

- How many bean definitions exist?
- How many implementation types exist?
- How many entries does `getBeansOfType(NotificationSender.class)` return?
- Why is this not a bean name collision error?

### Exercise 2 – One class, two beans

Create a `PartnerClient` class with a timeout property. Register two beans `fastClient` and `slowClient` using two `@Bean` methods returning the same class.

Verify that both beans share the same type but have different instances and different bean names.

### Exercise 3 – Trigger a bean name collision

Create two configurations both declaring `@Bean("paymentGateway")`. Observe the error under default Spring Boot settings. Then rename them to `demoPaymentGateway` and `partnerPaymentGateway`, and inject each bean via qualifier.

### Exercise 4 – Alias or second bean?

Declare:

```java
@Bean(name = {"mainClock", "systemClock"})
Clock clock() {
    return Clock.systemUTC();
}
```

Look up using both names and compare object identity. Then declare two separate `@Bean` methods to create two different `Clock` instances, and explain the difference.

### Exercise 5 – Choose one bean or the whole group

Create three `ReportExporter` implementations: CSV, PDF, and JSON.

- Use `@Primary` to select CSV as the default.
- Use `@Qualifier("pdf")` for a service that exports PDFs.
- Inject `List<ReportExporter>` into a service that exports in multiple formats.

Explain why `@Primary` does not exclude PDF and JSON from the collection.

### Exercise 6 – Distinguish @Autowired and @Resource

Create two beans of the same type named `emailSender` and `smsSender`. Try injecting with `@Autowired` without a qualifier, `@Autowired @Qualifier("smsSender")`, and `@Resource(name = "emailSender")`. Record how selection behaves and the error if a bean name does not exist.

## 19. Key takeaways

**Beans of the same type and beans with the same name are two different issues.**

- Multiple beans of the same type with different names can coexist. Spring only needs extra criteria when an injection point requires a single bean.
- One bean can match multiple types through its class, interfaces, and supertypes.
- One class can create multiple bean instances with different names via multiple `@Bean` methods.
- A bean name identifies a bean within a registry; an alias is another name pointing to the same bean and does not create a new instance.
- Two distinct bean definitions with the same name in one registry cause a conflict or override depending on policy; modern Spring Boot discourages overriding by default.
- `@Primary` chooses the default candidate; `@Qualifier` filters candidates by label/metadata; collection injection receives multiple beans of the same type.
- `@Autowired` generally resolves by type, whereas `@Resource(name = "...")` expresses selection by name.
- Bean name collisions are not solved by `@Primary`; type ambiguity is not solved merely by enabling bean overriding.
- When proxies are involved, the runtime object injected may differ from the original implementation class; interface-based dependencies are generally more resilient.

When organizing Java configuration, use **type to express the contract a service needs**, use **name to identify a bean**, and use **qualifier/primary to resolve selection**. Only when these three responsibilities are cleanly separated can an application hold multiple implementations of the same type while avoiding name collisions and keeping wiring easy to understand.
