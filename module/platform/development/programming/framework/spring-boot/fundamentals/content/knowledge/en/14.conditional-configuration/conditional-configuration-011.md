# Configuration Processing Order and Why Bean Conditions Behave Unexpectedly

Spring Boot can automatically register many beans based on the classpath, properties, profiles, application type, and already-declared beans. This mechanism gives applications sensible defaults without having to write every factory method by hand. However, when a bean appears even though you thought a condition should be false, or fails to appear even though you set the property and added the dependency, the root cause usually lies in **when Spring processes configurations and when conditions are evaluated**.

To understand the outcome, distinguish three stages:

1. Spring reads and parses configuration classes, annotations, and imports.
2. Spring registers bean definitions while evaluating bean-related conditions.
3. The container instantiates objects, injects dependencies, and applies lifecycles.

Not all conditions are checked at the same time. A classpath condition may be evaluated while Spring is parsing configuration; a condition such as `@ConditionalOnMissingBean` needs to know which bean definitions have already been registered and therefore belongs to the bean registration phase. Ordering between configurations—especially Spring Boot auto-configurations—can change the set of beans a condition sees.

This lesson explains processing order at the level needed to interpret condition outcomes, understand why beans are created or skipped, and investigate systematically instead of changing order randomly.

## 1. A Bean Condition Is Not an Expression Checked at Every Moment

A configuration may declare:

~~~java
@Configuration
@ConditionalOnProperty(
        prefix = "app.mail",
        name = "enabled",
        havingValue = "true"
)
public class MailConfiguration {

    @Bean
    public MailSender mailSender() {
        return new SmtpMailSender();
    }
}
~~~

If the property matches, the configuration can be applied and `mailSender()` supplies a bean definition. If the property does not match, the configuration is skipped and that bean is not registered from this source.

However, "conditional" does not mean Spring waits until `mailSender()` is called to check. Spring can evaluate conditions while processing the configuration class or while processing the bean method, depending on the condition type and the phase required by the condition.

For example:

- `@ConditionalOnClass` cares whether a class is on the classpath, so it can be evaluated during the configuration parsing phase.
- `@ConditionalOnProperty` checks properties in `Environment` and can be evaluated during configuration processing.
- `@ConditionalOnBean` and `@ConditionalOnMissingBean` need to inspect already-registered bean definitions, so they are tied to the bean registration phase.

If a condition is evaluated before the required information appears, the outcome can differ from reasoning based on the final state of the `ApplicationContext`.

## 2. General Configuration Processing Order

A Spring Boot application starts via:

~~~java
@SpringBootApplication
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

`SpringApplication.run(...)` prepares the environment, creates an appropriate `ApplicationContext`, loads configuration sources, and triggers bean definition processing.

The high-level flow can be described as:

~~~text
SpringApplication.run(...)
          |
          v
Prepare Environment, profiles,
property sources, and ApplicationContext
          |
          v
Register startup configuration
(@SpringBootApplication, @Import, ...)
          |
          v
ConfigurationClassPostProcessor
parses configuration classes
          |
          +--> component scan
          |
          +--> @Import and imported configurations
          |
          +--> deferred imports / auto-configuration
          |
          v
Register bean definitions
and evaluate corresponding conditions
          |
          v
BeanFactoryPostProcessor /
BeanPostProcessor and container steps
          |
          v
Instantiate singletons, resolve dependencies,
proxies, and lifecycle callbacks
          |
          v
ApplicationContext ready
~~~

This is a simplified orientation diagram. Internal steps may interleave, and certain extension points participate at different times. Yet one distinction is crucial: **bean definition registration happens before most singleton beans are instantiated**.

### Configuration Classes Are Parsed Before All Bean Instances Exist

`@Configuration` is not simply a class called like a service. Spring inspects its metadata to find:

- `@Bean` methods.
- `@ComponentScan` and discovered components.
- `@Import`, `ImportSelector`, and `ImportBeanDefinitionRegistrar`.
- `@PropertySource` and related configuration directives.
- Conditions deciding whether the configuration or bean method should be applied.

This process works primarily with metadata and bean definitions. It does not need to create every service/repository first before deciding configuration.

### Deferred Imports and Auto-Configuration

`@EnableAutoConfiguration` (included in `@SpringBootApplication`) uses a selective import mechanism for auto-configurations. Auto-configurations are normally handled as deferred imports: Spring first parses regular configurations and related imports, then processes the deferred import group according to the corresponding mechanism.

This gives auto-configurations a chance to observe bean definitions declared earlier by the application. Consequently, conditions such as `@ConditionalOnMissingBean` can usually "step aside" for user-configured beans.

Do not treat this as an absolute rule that every user bean is always registered before every auto-configuration in all complex setups. `@Import`, nested configurations, multiple contexts, or custom registrars can change actual ordering. When a condition depends on beans, check the actual registration order and the condition report.

## 3. Two Phases of `ConfigurationCondition`

Spring Framework defines `ConfigurationCondition` so a condition can specify when it needs to be evaluated.

Two main phases:

| Phase | Meaning | Typically suitable information |
|---|---|---|
| `PARSE_CONFIGURATION` | While Spring is parsing configuration classes | Annotation metadata, classpath, class configuration |
| `REGISTER_BEAN` | While Spring is processing and registering bean definitions | Bean definitions already registered up to that point |

A regular condition implementing only `Condition` can be evaluated during configuration checking. If it implements `ConfigurationCondition`, it can specify the right phase through `getConfigurationPhase()`.

Conceptual example:

~~~java
public class FeatureCondition implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        return context.getBeanFactory()
                .containsBeanDefinition("featureRepository");
    }
}
~~~

This example only illustrates the API and concept. In real code, handle cases where `getBeanFactory()` is unavailable or use appropriate registry/metadata APIs; do not assume every context type supports the same query capabilities.

Key point: a condition that needs to observe bean definitions should not be designed to run too early in the parse phase. Conversely, classpath-dependent conditions can be checked early so Spring does not have to process inapplicable configurations.

## 4. Why Are `@ConditionalOnBean` and `@ConditionalOnMissingBean` Order-Sensitive?

These two annotations are very common in auto-configuration:

~~~java
@Bean
@ConditionalOnBean(DataSource.class)
public JdbcHealthReporter jdbcHealthReporter(DataSource dataSource) {
    return new JdbcHealthReporter(dataSource);
}
~~~

~~~java
@Bean
@ConditionalOnMissingBean(DataSource.class)
public DataSource fallbackDataSource() {
    return createFallbackDataSource();
}
~~~

They do not merely ask "is the `DataSource` class on the classpath?". They ask about bean definitions/beans satisfying the specified type or criteria **at the time the condition is evaluated**.

### Registration Order Example

Suppose there are two configurations:

~~~java
@Configuration
public class PrimaryConfiguration {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

~~~java
@Configuration
public class ConditionalConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    public Clock fallbackClock() {
        return Clock.systemUTC();
    }
}
~~~

If `applicationClock` is already registered before Spring evaluates the condition on `fallbackClock`, the fallback bean will not be registered. If a complex configuration causes the condition to evaluate before the matching bean definition appears, the result can differ.

Therefore, Spring Boot recommends using `@ConditionalOnMissingBean` primarily in **auto-configuration**, where import order and ordering mechanisms are designed so default configurations can yield to application configurations.

### Conditions See Definitions, Not Necessarily Running Instances

Bean conditions normally operate at the registry stage, before instances are created. Thus, do not interpret `@ConditionalOnBean` as "wait until the bean runs successfully and then check." A bean definition may exist while its instance later fails during initialization due to missing dependencies or constructor errors.

Conversely, an object instantiated manually outside the container does not automatically become a bean definition visible to conditions.

### Specifying Type, Name, and Annotation

Condition annotations support several ways to identify beans, such as by:

- Bean type (`value` or `type`).
- Bean name (`name`).
- Annotation (`annotation`).
- Search strategy across context hierarchy.

Use the right attributes for your Spring Boot version. If a bean is created via a factory method, Spring can rely on return-type metadata; declaring an overly generic return type can make type inference less accurate.

Example:

~~~java
@Bean
@ConditionalOnMissingBean(Clock.class)
public Clock applicationClock() {
    return Clock.systemUTC();
}
~~~

Declaring return type `Clock` gives Spring clear information about the kind of bean the method provides.

## 5. Auto-Configuration Ordering: `@AutoConfigureBefore`, `@AutoConfigureAfter`, and `@AutoConfigureOrder`

Spring Boot provides annotations to order auto-configuration classes relative to one another:

- `@AutoConfigureBefore`: specifies this auto-configuration is processed before the named class.
- `@AutoConfigureAfter`: specifies it is processed after the named class.
- `@AutoConfigureOrder`: specifies relative order using an order value.

Example:

~~~java
@AutoConfiguration
@AutoConfigureAfter(DataSourceAutoConfiguration.class)
public class ReportingAutoConfiguration {

    @Bean
    @ConditionalOnBean(DataSource.class)
    public ReportingRepository reportingRepository(DataSource dataSource) {
        return new JdbcReportingRepository(dataSource);
    }
}
~~~

The intent is for the reporting auto-configuration to be processed after `DataSource` configuration so it can inspect the relevant bean. This configuration is an illustrative example; annotation names and APIs should match your project's Spring Boot version.

Another example:

~~~java
@AutoConfiguration
@AutoConfigureBefore(CacheAutoConfiguration.class)
public class CustomCacheDefaultsAutoConfiguration {
    // Default cache beans or configurations.
}
~~~

These ordering annotations are meant for **auto-configuration**, not as a general tool to order arbitrary Java classes or component scans.

### Ordering Does Not Create Dependencies

`@AutoConfigureAfter` does not mean beans in that class can automatically inject any bean from the preceding class. It only controls auto-configuration processing order. Beans must still be registered and dependencies must be compatible.

If bean A genuinely needs bean B, declare the dependency via constructor or `@Bean` method parameters. Do not use ordering as a substitute for dependency relationships.

### Do Not Confuse with `@Order`

`@Order` is typically used to sort certain components such as ordered collections, handlers, filters, or order-aware objects. It is **not** a general way to control the registration order of all bean definitions or the evaluation order of all configuration classes.

Example:

~~~java
@Component
@Order(1)
public class FirstHandler implements Handler {
    // ...
}
~~~

`@Order(1)` can affect order when Spring injects a collection of `Handler`s via an ordering-aware mechanism. It does not guarantee `FirstHandler` is registered before every other bean, nor does it replace `@AutoConfigureBefore` in auto-configuration.

### Do Not Confuse with `@DependsOn`

`@DependsOn("someBean")` indicates that one bean requires another bean to be instantiated first. It pertains to instance initialization/destruction order, not configuration parsing order or auto-configuration condition evaluation order.

If a condition does not see a bean definition because it was registered too late, adding `@DependsOn` usually does not solve the real issue: `@DependsOn` does not make a bean definition appear earlier in the registry.

## 6. Component Scan, `@Import`, and `@Bean` Also Affect the Set of Definitions

Bean conditions determine their results based on definitions already registered. Therefore, know where definitions come from.

### Component Scan

~~~java
@Service
public class CustomerService {
    // ...
}
~~~

If the package lies within the scan scope, the class can be registered as a bean definition. If outside the scan scope, the bean does not appear automatically just because it has `@Service`.

### `@Import`

~~~java
@Configuration
@Import(CustomerConfiguration.class)
public class StoreConfiguration {
}
~~~

`@Import` brings another configuration into processing. The imported configuration can register additional bean definitions and affect conditions evaluated afterward.

### `@Bean`

~~~java
@Configuration
public class CustomerConfiguration {

    @Bean
    public CustomerRepository customerRepository() {
        return new InMemoryCustomerRepository();
    }
}
~~~

A `@Bean` method creates a bean definition. If an auto-configuration checks `@ConditionalOnMissingBean(CustomerRepository.class)` after this definition is registered, the auto-configuration can skip the default repository.

### `ImportBeanDefinitionRegistrar`

A registrar can register multiple bean definitions directly. These definitions can also affect conditions evaluated in later steps. If a registrar and an auto-configuration have an ordering relationship, check the actual import and registration flow; do not rely on assuming every registrar always runs before every auto-configuration.

## 7. Classpath Conditions: Library Present Does Not Guarantee Bean Created

`@ConditionalOnClass` checks whether a class exists on the classpath:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.search.SearchClient")
public class SearchAutoConfiguration {

    @Bean
    public SearchService searchService() {
        return new SearchService();
    }
}
~~~

If `SearchClient` is not on the classpath, the auto-configuration can be skipped. If the class exists, that satisfies only one condition; other conditions may still fail.

A dependency may be declared in a build file yet be absent from the runtime classpath due to scope/configuration, exclusions, or packaging. In that case, `@ConditionalOnClass` may fail to match in the running application.

### Using `name` to Avoid Resolving Classes Too Early

In some optional-library configurations, directly referencing a class absent from the classpath can cause problems when the JVM resolves annotation/configuration metadata. The `name` form lets you describe the class by string name:

~~~java
@ConditionalOnClass(
        name = "com.example.search.SearchClient"
)
~~~

For auto-configurations, be careful about placing method signatures referencing types from optional libraries inside a configuration class that may be loaded when the library is absent. You can separate nested configurations or standalone classes guarded by classpath conditions to avoid unintended class loading.

### `@ConditionalOnMissingClass`

The opposite condition:

~~~java
@ConditionalOnMissingClass(
        "com.example.search.SearchClient"
)
@Configuration
public class SearchFallbackConfiguration {
    // Fallback configuration when library is missing.
}
~~~

This condition is useful for fallbacks when a capability is absent. However, if the class is present yet the bean is not created because of a property or another bean condition, `@ConditionalOnMissingClass` will not detect that.

## 8. Property Conditions and Configuration Source Precedence

`@ConditionalOnProperty` checks values in Spring's `Environment`. Example:

~~~java
@Configuration
@ConditionalOnProperty(
        prefix = "app.search",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class SearchConfiguration {

    @Bean
    public SearchService searchService() {
        return new SearchService();
    }
}
~~~

With this configuration:

| Effective value of `app.search.enabled` | Result |
|---|---|
| `true` | Condition matches |
| `false` | Does not match |
| Property missing | Does not match because `matchIfMissing = false` |
| `TRUE` | Case-insensitive string comparison according to how the condition handles typical boolean values; still keep casing consistent |

If `havingValue` is omitted, the condition has a default rule checking whether the property exists and does not have the string value `false`. Hence, if a property is set to `no` or some string other than `false`, the result might surprise the author. When you need an explicit boolean, set `havingValue = "true"`.

### Which Property Takes Effect?

Spring Boot has multiple configuration sources: application files, profile-specific files, environment variables, system properties, command-line arguments, config data imports, and programmatic sources. Higher-precedence sources override lower-precedence ones.

Example:

`application.yml`:

~~~yaml
app:
  search:
    enabled: false
~~~

Running the application with an argument:

~~~bash
java -jar app.jar --app.search.enabled=true
~~~

Command-line values normally override file values, so the condition can match even though YAML says false.

If a condition yields a surprising result, find the **effective property value** instead of reading only one YAML file. Consider active profiles, environment variables, launch arguments, config imports, and custom property sources.

### Placeholders and Property Names

Spring Boot supports relaxed binding for many property naming styles, especially in environment variables. However, for conditions and keys written in annotations, use canonical kebab-case such as `app.search.enabled`. Avoid guessing mappings when property names contain hyphens, abbreviations, or complex structures.

### Do Not Rely on Properties Not Yet Loaded When Conditions Run

If a property source is registered too late in the lifecycle, conditions evaluated earlier will not automatically re-run just because the property appears later. Plug configuration sources into Spring Boot's proper loading mechanism and timing, rather than adding a property source inside a business bean after the context has started initializing.

## 9. Bean Conditions: `OnBeanCondition` and Confusing Cases

Common annotations:

- `@ConditionalOnBean`: requires a matching bean to already exist in the registry/context at condition time.
- `@ConditionalOnMissingBean`: matches when no matching bean is found.
- `@ConditionalOnSingleCandidate`: matches when there is a single injectable candidate (or one marked primary in the corresponding scenario).

Example:

~~~java
@Bean
@ConditionalOnSingleCandidate(DataSource.class)
public JdbcTemplate jdbcTemplate(DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}
~~~

If there is a single `DataSource` candidate or one primary candidate under resolution rules, the configuration can create `JdbcTemplate`. If there are multiple `DataSource`s without a clear primary choice, the condition may not match.

### Why Does `@ConditionalOnMissingBean` Sometimes Fail to Back Off?

Common causes:

1. **The application bean was not registered yet when the condition ran.** The condition evaluated before the expected bean definition appeared.
2. **The `@Bean` return type is too generic.** Metadata does not reveal the exact bean type the factory method will supply.
3. **The bean is outside the component scan scope.** A class has `@Service` or `@Repository`, yet was never discovered.
4. **The bean exists only in another profile.** The current profile does not register that definition.
5. **The checked name/type is wrong.** The bean might be registered under a different interface or name than the condition expects.
6. **The condition has a different search strategy or attributes.** A parent/child context hierarchy can change search results from expectations.
7. **Another configuration registers the bean afterward.** A condition that already matched at evaluation time does not retroactively reverse itself.

The last point is crucial: conditions are not a continuous reactive mechanism. When a bean definition is registered later, Spring does not automatically go back and cancel definitions already approved by an earlier condition.

### Declare Specific Return Types

Example that limits metadata:

~~~java
@Bean
public Object customClock() {
    return Clock.systemUTC();
}
~~~

Spring only sees the declared return type `Object` at the method metadata level, so conditions based on type `Clock` may not recognize the definition as expected before the instance is created.

Instead declare:

~~~java
@Bean
public Clock customClock() {
    return Clock.systemUTC();
}
~~~

Specific return types help the container and conditions better understand what kind of bean is provided. If returning a concrete implementation, declare the appropriate interface/contract type that consumers will use.

## 10. Auto-Configuration Ordering Can Change Condition Results

Suppose there are two auto-configurations:

~~~java
@AutoConfiguration
public class DefaultStorageAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(StorageClient.class)
    public StorageClient defaultStorageClient() {
        return new DefaultStorageClient();
    }
}
~~~

~~~java
@AutoConfiguration
public class CloudStorageAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.storage.cloud",
            name = "enabled",
            havingValue = "true"
    )
    public StorageClient cloudStorageClient() {
        return new CloudStorageClient();
    }
}
~~~

If `DefaultStorageAutoConfiguration` is processed first, there is no `StorageClient` from the cloud config yet at that moment. The default bean may be registered. When the cloud config is processed afterward, it may add a second bean if the property condition matches. The result is two candidates of the same type rather than cloud automatically replacing the default.

If the cloud config is processed first, the default config can see the cloud bean and skip the default bean.

When auto-configurations have an ordering dependency, declare it explicitly:

~~~java
@AutoConfiguration
@AutoConfigureBefore(DefaultStorageAutoConfiguration.class)
public class CloudStorageAutoConfiguration {
    // ...
}
~~~

Or order in the reverse direction depending on the goal. In the example, to have the cloud bean present before the default condition evaluates, the cloud auto-configuration must be processed before the default auto-configuration.

### Do Not Use Ordering to Mask an Unclear Condition Design

If an auto-configuration needs to provide a fallback when the user has not configured storage, design conditions and ordering clearly. If two implementations can both be valid, you might need `@ConditionalOnMissingBean` for the default and an intentional property/profile for cloud. Do not rely on "whichever bean is registered last wins"; Spring Boot disables bean definition overriding by default in many setups, and even when enabled, results depend on order and bean names, making maintenance very difficult.

### Auto-Configuration Ordering Is Not Bean Instance Order

`@AutoConfigureBefore` and `@AutoConfigureAfter` control the processing order of auto-configuration classes. They do not directly dictate which singleton must instantiate before which singleton. When initialization order is needed, use dependency relationships or `@DependsOn` where truly necessary.

## 11. Conditions at Class Level vs. `@Bean` Method Level

Conditions can be placed on a configuration class:

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

    @Bean
    public AuditRepository auditRepository() {
        return new AuditRepository();
    }
}
~~~

If the class-level condition does not match, the whole configuration can be skipped, so the bean methods inside are not registered from this configuration.

Or place conditions on individual bean methods:

~~~java
@Configuration
public class AuditConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.audit",
            name = "publisher-enabled",
            havingValue = "true"
    )
    public AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "app.audit",
            name = "repository-enabled",
            havingValue = "true"
    )
    public AuditRepository auditRepository() {
        return new AuditRepository();
    }
}
~~~

Now each bean method has its own condition. One bean can be registered while the other is skipped.

Check dependencies between them: if `AuditPublisher` strictly requires `AuditRepository` yet the repository is disabled, the context can fail when creating the publisher. Independent conditions do not automatically know that beans are logically coupled and must toggle together.

## 12. Conditions on Components and Imported Configurations

Conditions can also appear on component classes or imported classes. However, you must understand their corresponding registration mechanisms.

Example:

~~~java
@Component
@Profile("dev")
public class LocalPaymentGateway implements PaymentGateway {
    // ...
}
~~~

When the `dev` profile is active, component scanning can register the bean. Under other profiles, the bean is not registered from this class.

For imported configurations:

~~~java
@Configuration
@Profile("prod")
public class ProductionPaymentConfiguration {
    // ...
}
~~~

If the profile does not match, the configuration can be skipped, and the bean definitions inside are not created either.

A bean can be excluded due to conditions at multiple layers: the configuration class was not processed, the bean method did not match, component scanning did not find it, or an auto-configuration was excluded. When investigating, identify **which condition was actually evaluated and on which metadata**.

## 13. Custom `Condition` and Choosing the Right Phase

You can create your own condition by implementing `Condition`:

~~~java
public class ExternalFeatureCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        Environment environment = context.getEnvironment();

        return environment.getProperty(
                "app.external.enabled",
                Boolean.class,
                false
        );
    }
}
~~~

Usage:

~~~java
@Configuration
@Conditional(ExternalFeatureCondition.class)
public class ExternalFeatureConfiguration {
    // ...
}
~~~

If a condition only reads properties, `@ConditionalOnProperty` can keep the code shorter. Custom conditions are useful when checking logic is more complex or combines multiple factors.

If a condition depends on already-registered bean definitions, consider `ConfigurationCondition` and the `REGISTER_BEAN` phase:

~~~java
public class RepositoryPresentCondition
        implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        BeanFactory factory = context.getBeanFactory();

        return factory instanceof ListableBeanFactory listable
                && listable.getBeanNamesForType(
                        CustomerRepository.class,
                        false,
                        false
                ).length > 0;
    }
}
~~~

This code illustrates the idea of choosing a phase; in a library condition needing compatibility across multiple registry/bean factory types, handle cases where `ListableBeanFactory` is unavailable or types cannot be queried as desired.

A custom condition should:

- Produce deterministic results from the metadata/environment/registry it is allowed to observe.
- Not create bean instances or perform side effects.
- Not call external services or access databases to decide configuration.
- Avoid depending on beans created after its phase.
- Provide clear messages to help investigate when a condition does not match.

Conditions are invoked during context construction; performing I/O or mutating state inside `matches` makes startup unpredictable and may execute multiple times.

## 14. `@ConditionalOnExpression` Can Cause Surprises

Spring Boot provides `@ConditionalOnExpression` for using SpEL:

~~~java
@Configuration
@ConditionalOnExpression(
        "${app.feature.enabled:false} and '${app.region:local}' == 'local'"
)
public class LocalFeatureConfiguration {
    // ...
}
~~~

This is flexible, yet expressions easily become long, hard to read, and hard to diagnose. For simple property conditions, `@ConditionalOnProperty` is usually clearer.

Additionally, using SpEL to reference beans inside an expression can cause those beans to be instantiated very early to evaluate the condition, before other post-processors finish processing them. That can cause side effects or leave beans incompletely processed. Avoid using bean references in conditional expressions to decide configuration; rely on properties or available metadata.

## 15. Why Is a Bean Present Even Though You Thought the Condition Was False?

A few common situations:

### Another Registration Source Supplies the Same Bean Type

You excluded a bean from an auto-configuration or its condition failed, yet another component scan or `@Bean` still registers an implementation of the same type. A condition only stops one registration source; it does not delete beans from the entire context.

### Condition Is Placed on a Different Configuration from the Observed Bean

The condition may be on one class while the bean is registered by another configuration, or from another auto-configuration. Determine the actual bean name, resource/source, and bean definition.

### Effective Property Differs from the File You Are Viewing

Environment variables, command-line arguments, profile-specific configs, or config imports override YAML. Check the effective property value and its source.

### Condition Checks a Different Type from the Injected Type

The bean is registered under a different implementation or interface; the condition may check a specific type that does not match the declared/metadata type Spring recognizes.

### Another Component Scan Still Discovers the Class

An exclude filter on one scan is not a context-wide ban on the bean. If the class lies within the scan scope of another configuration, it can still be registered by that scan.

## 16. Why Is a Bean Absent Even Though You Thought the Condition Was True?

### Class Exists Only on the Compile Classpath

The dependency may be in a scope not included at runtime. Check the runtime classpath and deployment artifact, not just the build file.

### Profile Is Not Active

`@Profile("prod")` does not match if the `prod` profile is not activated. Check `spring.profiles.active` and related profile groups/configurations.

### Property Is Missing or Has a Different Value

If `matchIfMissing` is false, a missing property causes the condition not to match. If `havingValue` is declared, the value must match. Check effective property sources.

### Required Bean Was Not Registered Yet When Condition Evaluated

Especially with `@ConditionalOnBean`, the configuration providing the bean might be processed later. Check auto-configuration ordering, imports, and condition phases.

### Multiple Bean Candidates Exist

`@ConditionalOnSingleCandidate` can fail to match if multiple candidates exist without a single primary candidate.

### Configuration Class Was Not Imported or Scanned

Having a configuration class in source code does not mean Spring automatically processes it. It must be component-scanned, imported, or registered via the appropriate mechanism.

### Another Condition on the Class or Method Excluded the Bean

Multiple conditions can apply at once. Only one non-matching condition is needed for the bean/configuration to be skipped.

## 17. Reading the Condition Evaluation Report

Spring Boot can provide a report explaining which auto-configurations matched or did not match. This is one of the most useful tools when beans appear or disappear unexpectedly.

### Enabling Debug at Startup

You can run the application with:

~~~bash
java -jar app.jar --debug
~~~

Or configure appropriate logging/debug in development. Spring Boot prints the condition evaluation report with groups:

- Positive matches: configurations/conditions that matched.
- Negative matches: configurations that did not match.
- Exclusions: auto-configurations excluded from importing.
- Unconditional classes: configurations that do not depend on conditions in the same way.

The report can show that an auto-configuration was skipped due to a missing class, mismatched property, or an already-existing bean. Read the **negative match message** to find the specific reason instead of just scanning class names.

### Actuator `conditions` Endpoint

If the application integrates Spring Boot Actuator and the `conditions` endpoint is exposed/configured appropriately, condition details can be observed via the corresponding management endpoint. Endpoint exposure must be security-controlled; do not publicly expose internal configuration details in production.

### Distinguishing the Condition Report from the Bean List

The condition report explains condition evaluation outcomes, yet it does not replace checking actual bean definitions. A bean may be registered from another source even when the related auto-configuration did not match. When needed, query `ApplicationContext` or inspect bean definition metadata to locate the registration source.

## 18. Testing Conditions with `ApplicationContextRunner`

When developing auto-configurations or conditions, `ApplicationContextRunner` helps test configuration variants in a small context without booting the entire application.

Conceptual example:

~~~java
class MailAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    MailAutoConfiguration.class
                            )
                    );

    @Test
    void createsMailSenderWhenEnabled() {
        contextRunner
                .withPropertyValues("app.mail.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(MailSender.class);
                });
    }

    @Test
    void doesNotCreateMailSenderWhenDisabled() {
        contextRunner
                .withPropertyValues("app.mail.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(MailSender.class);
                });
    }
}
~~~

This is a test skeleton; the `MailAutoConfiguration`, `MailSender`, and assertion library classes must exist in the project. `ApplicationContextRunner` belongs to Spring Boot test support and is especially useful for testing auto-configuration.

Additional scenarios can be added:

- Property missing.
- Property overridden with another value.
- Custom bean registered beforehand to test `@ConditionalOnMissingBean`.
- Two bean candidates to test `@ConditionalOnSingleCandidate`.
- Optional class present or absent on the classpath.
- Different profiles.
- Two auto-configurations ordered before/after each other.

### Testing User Bean Replacing the Default

~~~java
contextRunner
        .withBean(MailSender.class, CustomMailSender::new)
        .run(context -> {
            assertThat(context)
                    .hasSingleBean(MailSender.class);
            assertThat(context.getBean(MailSender.class))
                    .isInstanceOf(CustomMailSender.class);
        });
~~~

This snippet illustrates adding a custom bean to the test context to verify whether default auto-configuration backs off. Exact syntax depends on the Spring Boot Test version in use.

## 19. A Systematic Diagnostic Workflow

When a bean does not appear or appears unexpectedly, follow this sequence:

~~~text
Actual bean differs from expectation
          |
          v
Identify bean name and type
          |
          v
Find all registration sources:
component scan, @Bean, @Import,
registrar, auto-configuration
          |
          v
Identify which conditions apply
at class and method levels
          |
          v
Check phase and processing order
(PARSE_CONFIGURATION / REGISTER_BEAN)
          |
          v
Check classpath, properties,
profiles, and bean definitions
present when the condition ran
          |
          v
Read the Condition Evaluation Report
          |
          v
Create a test context reproducing the condition
          |
          v
Fix the right registration source or ordering
~~~

A quick checklist:

| Symptom | Check first |
|---|---|
| Default bean still appears despite custom bean declaration | Was the custom bean registered before the condition? Is the return type specific enough? |
| Conditional bean does not appear | Which condition failed? Which property/class/bean/profile is missing? |
| Two implementations appear together | Which two registration sources supply beans? Did the default condition see the custom bean? |
| Fails only in production | How do runtime classpath, profiles, property sources, environment, and infrastructure differ? |
| `@ConditionalOnBean` does not see bean | Did the bean definition exist before the condition ran? |
| Auto-configuration runs in unexpected order | Are `@AutoConfigureBefore`/`After`/`Order` needed? |
| `@Order` does not change condition | Using `@Order` for the wrong purpose; use auto-configuration ordering or proper dependencies |
| Bean is created, yet initialization fails | Distinguish condition match from constructor/dependency/lifecycle failures |

## 20. Principles for Designing Predictable Conditions

1. **Use the condition suited to the type of information.** Classpath uses `@ConditionalOnClass`; properties use `@ConditionalOnProperty`; profiles use `@Profile`; existing beans use `@ConditionalOnBean` or `@ConditionalOnMissingBean`.
2. **Use `@ConditionalOnMissingBean` primarily for auto-configuration.** This provides defaults while giving applications the ability to override.
3. **Do not rely on beans to be registered in the future.** Conditions see the registry at evaluation time; they do not automatically re-run afterward.
4. **Declare sufficiently specific `@Bean` return types.** Accurate type metadata helps conditions and autowiring identify beans properly.
5. **Use dedicated ordering for auto-configuration.** `@AutoConfigureBefore`, `@AutoConfigureAfter`, and `@AutoConfigureOrder` serve a different purpose from `@Order` and `@DependsOn`.
6. **Do not use conditions to perform I/O.** Do not call databases, HTTP endpoints, or mutate state in `matches`.
7. **Keep conditions at the right level.** If an entire configuration toggles together, place the condition on the class; if individual beans are independent, place it on the bean method.
8. **Control multiple registration sources.** Excluding an auto-configuration does not remove beans of the same type from component scanning or other `@Bean` methods.
9. **Test both matching and non-matching cases.** Missing properties, different profiles, custom beans, multiple candidates, and optional classpaths can all change results.
10. **Use the condition report to explain outcomes.** Do not deduce behavior from a single YAML file or annotation alone.

## Conclusion

Bean conditions in Spring Boot are evaluated during configuration parsing and bean definition registration, before most instances are created. Therefore, the result depends on **the condition's phase, configuration/auto-configuration processing order, classpath metadata, effective properties, profiles, and bean definitions already present at evaluation time**.

`@ConditionalOnBean` and `@ConditionalOnMissingBean` are especially sensitive to registry ordering; classpath and property conditions rely on different information sources. `@AutoConfigureBefore`, `@AutoConfigureAfter`, and `@AutoConfigureOrder` help order auto-configurations when needed, while `@Order` and `@DependsOn` solve different problems.

When outcomes differ from expectations, identify which source the bean comes from, which condition applies, which phase the condition is evaluated in, and which values/definitions existed at that moment. Combining the Condition Evaluation Report with a small context test will explain accurately why Spring Boot chose or skipped a configuration.
