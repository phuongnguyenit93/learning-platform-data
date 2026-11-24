# BeanDefinitionOverrideException and Bean Name Collisions

When Spring Boot starts, the framework reads configuration, scans components, processes configuration classes, and registers bean definitions into the ApplicationContext's registry. Every bean needs a **bean name** so Spring can look it up, inject dependencies, and manage its lifecycle.

If two configurations register the same bean name in the same registry, the application can halt at startup with the error:

```text
org.springframework.beans.factory.support.BeanDefinitionOverrideException:
Invalid bean definition with name 'paymentGateway' ...
Cannot register bean definition ... since there is already ...
```

This is `BeanDefinitionOverrideException`. It commonly occurs when component scanning finds two classes with the same default bean name, two `@Bean` methods share the same name, or an application bean collides with a bean name from a library/auto-configuration.

Two scenarios must be distinguished:

- **Duplicate bean name:** two bean definitions attempt to register under the same name. This is the direct cause of `BeanDefinitionOverrideException` when overriding is disabled.
- **Duplicate bean type:** multiple beans have different names yet share the same type. Injecting by type can trigger `NoUniqueBeanDefinitionException`.

These two errors require different fixes. This lesson helps you read the error message, find the duplicate registration sources, choose the right fix, and verify the ApplicationContext afterward.

## 1. What Are Bean Names Used For?

A bean definition describes how Spring creates and configures an object, such as:

- Bean class or factory method.
- Scope such as singleton or prototype.
- Constructor arguments and property values.
- Dependencies and qualifiers.
- Init/destroy methods.
- Additional metadata used during bean creation.

The bean name is the identifier key used by the registry to store and look up the definition.

Example:

```java
@Service
public class PaymentService {
}
```

With the default naming strategy, the bean name is usually `paymentService`.

You can retrieve the bean by name:

```java
PaymentService service =
        applicationContext.getBean("paymentService", PaymentService.class);
```

Or inject by type:

```java
@Service
public class CheckoutService {

    private final PaymentService paymentService;

    public CheckoutService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
```

In business code, constructor injection is usually preferred. Bean names still matter when multiple implementations share a type, when using qualifiers, when declaring aliases, or when frameworks register beans.

## 2. How Does Spring Generate Default Bean Names?

Understanding naming rules helps spot collisions before running the application.

### 2.1. @Component, @Service, @Repository, and @Controller

When no explicit name is given, stereotype annotations generally use the short class name with the first character decapitalized per JavaBeans/Spring conventions.

```java
@Service
public class CustomerService {
}

@Repository
public class CustomerRepository {
}

@Component
public class AuditPublisher {
}
```

Default bean names are typically:

| Class | Default Bean Name |
|---|---|
| `CustomerService` | `customerService` |
| `CustomerRepository` | `customerRepository` |
| `AuditPublisher` | `auditPublisher` |

`@Service`, `@Repository`, and `@Controller` are specialized `@Component` stereotypes, so they participate in the same component naming mechanism.

### 2.2. Two Classes with the Same Simple Name in Different Packages

This is a frequent cause:

```java
package com.example.billing;

@Service
public class PaymentService {
}
```

```java
package com.example.reporting;

@Service
public class PaymentService {
}
```

If component scanning covers both packages, both classes receive the default bean name `paymentService`.

Different packages do not automatically make default bean names unique. When both candidates are registered in the same ApplicationContext, their names collide.

### 2.3. Explicit Bean Naming

You can assign distinct names:

```java
@Service("billingPaymentService")
public class PaymentService {
}
```

```java
@Service("reportingPaymentService")
public class PaymentService {
}
```

If both implement the same interface, callers can select an implementation using `@Qualifier` or `@Primary`. Bean names should describe role/domain, such as `billingPaymentService` or `reportingPaymentService`.

## 3. @Bean Methods Also Create Bean Names

The default name of a bean declared with `@Bean` is usually the factory method name:

```java
@Configuration
public class PaymentConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new HttpPaymentGateway();
    }
}
```

The default bean name is `paymentGateway`.

If another configuration also declares:

```java
@Configuration
public class TestPaymentConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
```

Both methods register the bean name `paymentGateway`. If both configurations are imported or scanned into the same context, the registry hits a conflict when overriding is disabled.

You can assign distinct names:

```java
@Bean("livePaymentGateway")
public PaymentGateway livePaymentGateway() {
    return new HttpPaymentGateway();
}
```

```java
@Bean("testPaymentGateway")
public PaymentGateway testPaymentGateway() {
    return new FakePaymentGateway();
}
```

A `@Bean` can also declare multiple names; the first is the bean name and subsequent names are aliases. Aliases are also lookup names, so avoid aliases that collide with other bean names.

## 4. When Does BeanDefinitionOverrideException Occur?

Within the same bean registry, a new bean definition attempts to use a name already registered by another definition. When the registry disallows overriding, Spring rejects the registration and throws the exception.

Common causes:

1. Two components share the same default name.
2. Two `@Bean` methods share the same name.
3. A configuration is imported across multiple modules and registers a bean with the same name.
4. An application bean collides with a bean name provided by a library or auto-configuration.
5. Component scanning covers unexpected packages.
6. Test configuration adds a bean with the same name as a production bean.
7. Two independent modules use generic names like `client`, `mapper`, or `configuration`.

### 4.1. Example Error Message

```text
The bean 'paymentGateway', defined in
com.example.billing.PaymentConfiguration,
could not be registered.

A bean with that name has already been defined in
com.example.shared.SharedPaymentConfiguration
and overriding is disabled.
```

The exact message depends on Spring Framework/Spring Boot versions and bean definition sources. Read both sides:

- **New definition:** the configuration class or component attempting to register.
- **Existing definition:** the bean name already held in the registry.

Do not search only for the bean name string inside the failing service. The conflicting source may reside in another module, a starter, or test configuration.

### 4.2. At Which Stage Does the Error Occur?

The error usually occurs during ApplicationContext refresh, before the application is ready to handle requests. Because the context has not finished initializing, Actuator endpoints cannot be used to investigate.

Start from the stack trace, failure analysis, and class/resource names cited. Once a context runs successfully, introspection APIs can list bean definitions.

## 5. Distinguishing Duplicate Bean Name vs. Duplicate Bean Type

This is the most important distinction when choosing a fix.

### 5.1. Duplicate Bean Name

```java
@Configuration
class FirstConfiguration {

    @Bean("paymentGateway")
    PaymentGateway firstGateway() {
        return new FirstPaymentGateway();
    }
}

@Configuration
class SecondConfiguration {

    @Bean("paymentGateway")
    PaymentGateway secondGateway() {
        return new SecondPaymentGateway();
    }
}
```

Both definitions use the same name `paymentGateway`. With overriding disabled, the context cannot register the second definition.

This is a **registry naming** problem.

### 5.2. Duplicate Bean Type with Different Names

```java
@Configuration
class GatewayConfiguration {

    @Bean("cardGateway")
    PaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }

    @Bean("bankGateway")
    PaymentGateway bankGateway() {
        return new BankPaymentGateway();
    }
}
```

Both beans share the `PaymentGateway` interface yet have distinct names. The registry stores both. However, injection by type:

```java
public CheckoutService(PaymentGateway gateway) {
    this.gateway = gateway;
}
```

can trigger `NoUniqueBeanDefinitionException` because Spring finds multiple candidates.

This is a **dependency selection** problem, not a bean definition override.

### 5.3. Comparison Table

| Scenario | Common Error | Resolution Direction |
|---|---|---|
| Two definitions with the same bean name | `BeanDefinitionOverrideException` | Rename, remove duplicate registration, or use conditionals |
| Multiple differently named beans of the same type, injected by type | `NoUniqueBeanDefinitionException` | `@Qualifier`, `@Primary`, or explicit bean selection |
| Bean name alias collides with another name | Registration/alias error depending on case | Rename or adjust alias |
| Child context bean shadows parent bean of the same name | Hierarchy shadowing | Verify lookup context and design intent |

`@Primary` and `@Qualifier` do not resolve two bean definitions sharing the same name. They choose candidates among beans that are already validly registered.

## 6. When to Use @Qualifier and @Primary?

Suppose an application needs two gateways with different purposes:

```java
@Configuration
public class GatewayConfiguration {

    @Bean("cardGateway")
    PaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }

    @Bean("bankGateway")
    PaymentGateway bankGateway() {
        return new BankPaymentGateway();
    }
}
```

### 6.1. Using @Qualifier for Explicit Selection

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("cardGateway") PaymentGateway gateway
    ) {
        this.gateway = gateway;
    }
}
```

`@Qualifier` narrows injected candidates. In this example, the qualifier matches the bean name; qualifiers can also be custom metadata attached to beans.

### 6.2. Using @Primary for the Default Implementation

If most callers should use the bank gateway:

```java
@Bean("bankGateway")
@Primary
PaymentGateway bankGateway() {
    return new BankPaymentGateway();
}
```

When injecting by type without a qualifier, Spring prefers the bean marked `@Primary`.

### 6.3. Combining Both

Default bean:

```java
@Bean("bankGateway")
@Primary
PaymentGateway bankGateway() {
    return new BankPaymentGateway();
}
```

Callers needing the card gateway specify `@Qualifier("cardGateway")`. Other callers injecting `PaymentGateway` by type receive the primary bean.

If two methods still declare `@Bean("paymentGateway")`, adding `@Primary` will not make the registry name unique. Resolve the naming conflict first.

## 7. Fixing by Giving Beans Unique Names

If both implementations genuinely need to coexist, assign distinct names.

```java
@Service("emailNotificationService")
public class EmailNotificationService
        implements NotificationService {

    @Override
    public void send(String recipient, String message) {
        // Send email.
    }
}
```

```java
@Service("smsNotificationService")
public class SmsNotificationService
        implements NotificationService {

    @Override
    public void send(String recipient, String message) {
        // Send SMS.
    }
}
```

Callers choose the bean they need:

```java
@Service
public class AlertService {

    private final NotificationService emailService;

    public AlertService(
            @Qualifier("emailNotificationService")
            NotificationService emailService
    ) {
        this.emailService = emailService;
    }
}
```

Clear names reduce cross-module collisions and make dependencies easier to read.

## 8. Fixing Overly Broad Component Scanning

Another cause is placing `@SpringBootApplication` in a package that is too high in the hierarchy, causing Spring to scan classes outside the current application.

Example:

```text
com.example
├── application
│   └── Application.java
├── billing
│   └── PaymentService.java
├── reporting
│   └── PaymentService.java
└── legacy
    └── PaymentService.java
```

If the main application sits in `com.example`, default component scanning may discover multiple child packages.

### 8.1. Selecting Specific Scan Packages

```java
@SpringBootApplication(scanBasePackages = {
        "com.example.application",
        "com.example.billing"
})
public class BillingApplication {
}
```

This restricts component scanning to the necessary packages. Ensure all other required components are still registered.

### 8.2. Using excludeFilters When Needed

If you need to scan a broad package while excluding a specific candidate:

```java
@Configuration
@ComponentScan(
    basePackages = "com.example",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = LegacyPaymentService.class
    )
)
public class ApplicationComponents {
}
```

This is an intentional fix when you know exactly which class should not be registered. Do not use broad filters just to mask errors, as they may drop needed beans.

### 8.3. Avoid Arbitrarily Scanning Library Packages

Do not place component scanning at a shared root across multiple applications or third-party library packages unless necessary. Organize packages along application boundaries and place the main class at the appropriate root package.

## 9. Handling Conflicts Between Application Beans and Auto-Configuration

Spring Boot auto-configurations are typically designed to back off when the application supplies its own bean. A common pattern is `@ConditionalOnMissingBean`.

Example auto-configuration:

```java
@Configuration(proxyBeanMethods = false)
public class DefaultGatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    public PaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
```

Application supplies its own bean:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationGatewayConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new CustomPaymentGateway();
    }
}
```

The intent is: if the application already provides a `PaymentGateway`, auto-configuration does not create the default bean.

### 9.1. Why Is Conditional Back-Off Better Than Overriding?

- Intent to replace the default is explicit.
- Does not depend on registration order between two definitions with the same name.
- The application can provide an implementation under a different name.
- Auto-configuration backs off cleanly via a type- or name-based contract.

### 9.2. Conditional by Bean Name

You can use `@ConditionalOnMissingBean(name = "paymentGateway")` when the contract requires checking a specific name.

If what you really mean is "is there already an implementation of this interface?", a type-based condition expresses intent better.

### 9.3. Conditions Must Be Evaluated at the Right Time

`@ConditionalOnMissingBean` is designed primarily for auto-configuration. Using it in normal application configuration with unpredictable registration order can yield surprising outcomes.

When building starters/libraries, follow Spring Boot's auto-configuration conventions and test both default and custom bean scenarios.

## 10. Excluding Unneeded Auto-Configuration

If an application does not want a specific auto-configuration, exclude it rather than enabling global bean overriding.

```java
@SpringBootApplication(
    exclude = SomeClientAutoConfiguration.class
)
public class Application {
}
```

Or via property:

```properties
spring.autoconfigure.exclude=com.example.client.SomeClientAutoConfiguration
```

Class names here are examples; use the actual auto-configuration class from your dependency.

Exclude only once you understand what functionality will be lost. An auto-configuration can register several supporting beans beyond the one colliding.

### 10.1. Checking the Condition Evaluation Report

Running the app with `--debug` prints the condition evaluation report:

```bash
java -jar app.jar --debug
```

The report shows which auto-configurations matched or failed to match, and which conditions decided the outcome. It helps identify why an auto-configuration was enabled.

If the context fails right during bean definition registration, the condition report may not always list both conflicting definitions completely. Combine it with the stack trace and resources cited in the exception.

## 11. Profiles and Property Conditions

If two beans belong only to different environments, use profiles:

```java
@Configuration
@Profile("dev")
public class DevelopmentGatewayConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
```

```java
@Configuration
@Profile("prod")
public class ProductionGatewayConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new LivePaymentGateway();
    }
}
```

When only one profile is active, only the matching configuration applies. However, if both profiles are active simultaneously, both configurations register and conflict again.

You can use `@ConditionalOnProperty` when a bean depends on a property:

```java
@Bean
@ConditionalOnProperty(
    prefix = "payment",
    name = "provider",
    havingValue = "fake"
)
PaymentGateway fakePaymentGateway() {
    return new FakePaymentGateway();
}
```

Conditions select implementations based on runtime configuration. If two conditions both match and both beans share the same name, collisions can still occur.

## 12. When Should Bean Definition Overriding Be Allowed?

Spring Boot provides the property:

```properties
spring.main.allow-bean-definition-overriding=true
```

Or via `SpringApplication`:

```java
SpringApplication application =
        new SpringApplication(Application.class);

application.setAllowBeanDefinitionOverriding(true);

application.run(args);
```

When overriding is enabled, a bean definition registered later replaces an earlier definition under the same name in the same registry.

### 12.1. Why Should This Not Be the First Solution?

- The final bean depends on registration order.
- Order can shift when adding dependencies, configs, or upgrading framework versions.
- The original bean can vanish silently without notice.
- ApplicationContext still starts yet runs an unintended implementation.
- Wiring bugs are masked instead of fixed.

This is especially dangerous if the overridden bean is `DataSource`, `ObjectMapper`, `SecurityFilterChain`, a transaction manager, or an external client.

### 12.2. Default Depends on Spring Boot Version

Spring Boot 2.1 changed the default to **disallow bean definition overriding**. Thus older and newer applications may behave differently with unchanged source code.

Check your Spring Boot version and effective configuration. Never infer project defaults from guides written for another version.

### 12.3. If Overriding Is Genuinely Necessary

In specialized cases requiring replacement of a same-named definition:

1. Identify the exact old and new definitions.
2. Confirm registration order is deterministic.
3. Enable it only in the necessary scope if possible.
4. Write an integration test verifying the final bean is the expected implementation.
5. Document the reason and scope of the override.
6. Prefer conditional back-off if the design can be adjusted.

In typical applications, renaming or conditional configuration is far easier to maintain than global overriding.

## 13. Reading the Error to Find Both Registration Sources

When encountering `BeanDefinitionOverrideException`, extract four pieces of information:

- **Bean name:** the duplicate name, e.g., `paymentGateway`.
- **Existing definition:** the class/resource or factory method registered first.
- **New definition:** the class/resource or factory method being registered later.
- **Context/registry:** which ApplicationContext holds both definitions.

Then search the source for:

```text
paymentGateway
@Bean
@Component
@Service
@Repository
@ComponentScan
@Import
```

Find every place capable of registering that name, not only methods matching the exact string.

### 13.1. Inspecting Resource Descriptions When Context Runs

```java
ConfigurableApplicationContext context = ...;

for (String beanName :
        context.getBeanFactory().getBeanDefinitionNames()) {

    BeanDefinition definition =
            context.getBeanFactory().getBeanDefinition(beanName);

    System.out.printf(
            "name=%s, class=%s, factoryBean=%s, factoryMethod=%s, source=%s%n",
            beanName,
            definition.getBeanClassName(),
            definition.getFactoryBeanName(),
            definition.getFactoryMethodName(),
            definition.getResourceDescription()
    );
}
```

This reveals whether a bean comes from a class, `@Bean` factory method, or resource.

**Limitation:** if the context fails before refresh completes, this snippet cannot run as a bean inside that same context. In that case, use the stack trace, debug registration, or build a minimal diagnostic context with the same configuration.

### 13.2. Actuator beans Endpoint

If the application starts successfully, the Actuator `beans` endpoint lists beans and their owning contexts. Because it exposes internal structure, limit its exposure and protect it with appropriate security.

You cannot rely on this endpoint to diagnose a context that fails to start.

## 14. Example: Two @Configuration Classes Registering the Same Name

Billing module:

```java
@Configuration
public class BillingConfiguration {

    @Bean
    public PaymentClient paymentClient() {
        return new BillingPaymentClient();
    }
}
```

Reporting module:

```java
@Configuration
public class ReportingConfiguration {

    @Bean
    public PaymentClient paymentClient() {
        return new ReportingPaymentClient();
    }
}
```

Application imports both:

```java
@SpringBootApplication
@Import({
    BillingConfiguration.class,
    ReportingConfiguration.class
})
public class Application {
}
```

Both methods default to registering bean name `paymentClient`. With overriding disabled, the context fails when registering the duplicate definition.

### 14.1. If Both Clients Must Exist

Rename by role:

```java
@Bean("billingPaymentClient")
public PaymentClient billingPaymentClient() {
    return new BillingPaymentClient();
}
```

```java
@Bean("reportingPaymentClient")
public PaymentClient reportingPaymentClient() {
    return new ReportingPaymentClient();
}
```

Then inject the right client:

```java
public BillingService(
        @Qualifier("billingPaymentClient") PaymentClient client
) {
    this.client = client;
}
```

### 14.2. If Only One Client Should Be Used

If the reporting module only provides a default, design auto-configuration to back off when a `PaymentClient` already exists:

```java
@Bean
@ConditionalOnMissingBean(PaymentClient.class)
public PaymentClient paymentClient() {
    return new ReportingPaymentClient();
}
```

Never register two same-named definitions and rely on "whichever bean is created last" to choose the implementation.

## 15. Example: Two Classes with the Same Default Name

```java
package com.example.legacy;

@Component
public class JsonMapper {
}
```

```java
package com.example.platform;

@Component
public class JsonMapper {
}
```

Both classes receive the default name `jsonMapper`. If both packages are on the scan path, the registry collides.

Fix with explicit names:

```java
@Component("legacyJsonMapper")
public class JsonMapper {
}
```

```java
@Component("platformJsonMapper")
public class JsonMapper {
}
```

Or narrow component scanning if one class does not belong in this application's context.

When two classes serve distinct roles, domain-specific names are better than generic ones like `jsonMapper`, `client`, `helper`, or `config`.

## 16. Bean Name Aliases Must Also Be Checked

A bean can have multiple names:

```java
@Bean(name = {"primaryObjectMapper", "jsonMapper"})
public ObjectMapper objectMapper() {
    return new ObjectMapper();
}
```

The first name is the bean name; subsequent names are aliases for the same bean. If another configuration attempts to register a bean named `jsonMapper`, the registry may hit an alias/name conflict depending on registration details.

When investigating, check:

- `@Bean(name = {...})`.
- Aliases registered via `BeanDefinitionRegistry`.
- `registerAlias(...)`.
- Framework or library configurations with custom bean names.

Aliases do not create extra instances; they create additional lookup names for the same bean.

## 17. Beans in Parent and Child ApplicationContexts

A system may have a context hierarchy, such as a root context and a web child context. The same bean name can exist in both parent and child; the child context can shadow the parent's same-named bean during lookups.

This differs from two definitions sharing a name inside **the same registry**.

When seeing two beans with the same name in a multi-context application:

1. Identify which context each bean belongs to.
2. Check which context the caller looks up from.
3. Check whether the child intentionally shadows the parent bean.
4. Distinguish context hierarchies from component scanning/importing into a single registry.

Do not mechanically apply single-context fixes to hierarchical systems.

## 18. Collisions in Test Configurations

Tests often add replacement beans to isolate dependencies:

```java
@TestConfiguration
public class TestGatewayConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
```

If a test also imports the production configuration declaring `paymentGateway`, the test context can encounter a naming conflict.

Options depending on goal:

- Use the mock/bean-replacement mechanism supported by your Spring Boot/Spring Framework version.
- Give the test bean a distinct name and inject with a qualifier if both must coexist.
- Use profiles/conditionals so only one implementation registers.
- Avoid importing production configuration if the test does not need it.
- Use an appropriate test slice or minimal context.

Never enable overriding across the entire test suite just to silence errors. Doing so can cause tests to use real or fake beans unpredictably.

## 19. Designing Starters/Auto-Configurations to Avoid Collisions

When developing a Spring Boot starter, default beans should allow application customization.

```java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
```

Applications can supply their own implementation:

```java
@Configuration
public class ApplicationGreetingConfiguration {

    @Bean
    public GreetingService customGreetingService() {
        return new CustomGreetingService();
    }
}
```

Auto-configuration backs off by type when a matching bean already exists.

When building a starter, you should:

- Use `@ConditionalOnClass` to activate only when required dependencies are present.
- Use `@ConditionalOnProperty` when a feature should be explicitly toggled.
- Use `@ConditionalOnMissingBean` to back off.
- Specify auto-configuration ordering when dependencies exist.
- Test both default and custom bean scenarios.

The goal is giving applications explicit implementation choice rather than letting scan order decide the final bean.

## 20. Testing to Catch Bean Name Collisions

You can use `ApplicationContextRunner` in auto-configuration tests to verify that a context starts or fails as expected.

Example with two configurations registering the same name:

```java
class BeanNameCollisionTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            FirstGatewayConfiguration.class,
                            SecondGatewayConfiguration.class
                    );

    @Test
    void failsWhenTwoDefinitionsUseSameName() {
        contextRunner.run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .hasRootCauseInstanceOf(
                            BeanDefinitionOverrideException.class
                    );
        });
    }
}
```

This is an illustrative test; it assumes two configurations in test sources register the same bean name with corresponding test dependencies.

### 20.1. Testing After Fixing

After renaming:

```java
contextRunner.run(context -> {
    assertThat(context).hasNotFailed();
    assertThat(context).hasBean("billingPaymentClient");
    assertThat(context).hasBean("reportingPaymentClient");
});
```

If only one implementation should exist conditionally:

```java
contextRunner.run(context -> {
    assertThat(context).hasNotFailed();
    assertThat(context).hasSingleBean(PaymentClient.class);
});
```

`ApplicationContextRunner` is great for auto-configuration tests because it creates small, fast, controlled contexts. Real applications still need integration tests covering full runtime configuration.

## 21. Step-by-Step Investigation Workflow

When an application reports `BeanDefinitionOverrideException`:

### Step 1. Record the Duplicate Bean Name

For example, `paymentGateway`. This is the primary search key.

### Step 2. Read Both the New and Existing Definitions

Stack traces/failure messages usually indicate the class, factory method, or resource. Record both sides, not just the last one mentioned.

### Step 3. Find Every Registration Source for That Name

Search the project for:

- `@Component("...")`, `@Service("...")`, `@Repository("...")`.
- `@Bean` methods and `@Bean(name = ...)`.
- `@Import` and `@ComponentScan`.
- Custom `BeanDefinitionRegistryPostProcessor`.
- Alias registrations.
- Test configurations.
- Auto-configurations from dependencies.

### Step 4. Decide Whether You Need Two Beans or One

If both are needed, rename them and use qualifiers. If you only want to replace a default, use conditional back-off or exclude unneeded auto-configuration.

### Step 5. Handle Duplicate Types Separately

Once bean names are resolved, the application may encounter `NoUniqueBeanDefinitionException` if multiple beans share a type. Use `@Qualifier`/`@Primary` per dependency contract.

### Step 6. Start the Context and Verify the Actual Bean

Check bean names, types, resource descriptions, and implementations. Do not stop just because the exception disappeared; verify services receive the right implementation.

### Step 7. Add Tests to Prevent Regression

For starters or shared configuration modules, context tests should cover both default and custom bean scenarios.

## 22. Fix Options and When to Use Each

| Fix | Use When | Caveats |
|---|---|---|
| Rename `@Component`/`@Bean` | Multiple beans must coexist | Callers must select the right bean |
| `@Qualifier` | Multiple beans share a type with different names | Does not solve duplicate bean names |
| `@Primary` | Multiple candidates exist with one default | Does not solve duplicate bean names |
| `@ConditionalOnMissingBean` | Default auto-configuration should yield to custom beans | Place properly in auto-configuration |
| `@Profile` | Only one configuration suits a given environment | Multiple active profiles can register both |
| `@ConditionalOnProperty` | Selecting implementation by property | Loose conditions can both match |
| Narrow component scan | Scanning picks up unintended beans | Ensure needed beans are not excluded |
| Exclude auto-configuration | Starter feature is not needed | Check side effects on related beans |
| Allow overriding | Intentional special case | Order-dependent; requires strict tests |

## 23. Commonly Confused Errors

### 23.1. NoUniqueBeanDefinitionException

Messages typically state Spring found multiple beans matching a dependency type:

```text
No qualifying bean of type 'PaymentGateway' available:
expected single matching bean but found 2
```

If bean names differ, use `@Qualifier` or `@Primary`. Do not rename beans simply because two beans share a type unless current names are confusing.

### 23.2. NoSuchBeanDefinitionException

This message indicates no matching bean was found. Possible causes:

- Class was not scanned/imported.
- Profile or condition did not match.
- Dependency was not declared.
- Lookup used the wrong bean name/type.

This is not a duplicate name error.

### 23.3. BeanCurrentlyInCreationException

This usually involves a circular dependency or a bean accessed mid-creation, not simply two beans sharing a name. Inspect the dependency graph and constructor injection.

### 23.4. BeanDefinitionOverrideException

This is a conflict when registering a definition whose name already exists in the same registry while overriding is disabled. Focus on the two registration sources and the bean name.

## 24. Common Misconceptions

| Statement | True or False? | Explanation |
|---|---|---|
| Two classes in different packages always get different bean names | **False** | Default names usually derive from short class names |
| Two beans of the same type always cause `BeanDefinitionOverrideException` | **False** | With different names, the issue is usually dependency selection |
| `@Primary` fixes two beans with the same name | **False** | Primary selects a candidate by type after registration |
| `@Qualifier` prevents the registry from registering duplicate names | **False** | Qualifier selects beans at injection time |
| Renaming a `@Bean` method is always harmless | **False** | Code looking up by bean name/qualifier may need updating |
| Enabling overriding is always a good solution | **False** | It can hide conflicts and make results order-dependent |
| Auto-configuration always overrides application beans | **False** | Auto-configuration typically uses back-off conditions |
| `@ConditionalOnMissingBean` is the same as `@Primary` | **False** | Conditional decides whether to register a definition; Primary chooses a candidate |
| Same bean name in parent/child contexts always throws an override exception | **False** | Context hierarchies have their own lookup/shadowing rules |
| Actuator beans endpoint always works when startup fails | **False** | The endpoint requires a started and exposed context |
| Same bean name in two config files always causes an error | **False** | You must check whether both enter the same registry/context |
| `@Profile("dev")` and `@Profile("prod")` are always mutually exclusive | **False** | Multiple profiles can be active simultaneously |

## 25. Practice Exercises

### Exercise 1. Two Components with the Same Default Name

Create two `PaymentService` classes in two packages:

```java
package com.example.billing;

@Service
public class PaymentService {
}
```

```java
package com.example.reporting;

@Service
public class PaymentService {
}
```

Place the main application in the parent package to scan both.

**Question:** Why can the context hit `BeanDefinitionOverrideException`?

**Answer:** Both classes may receive the default bean name `paymentService` in the same registry.

**Fix:** Assign distinct names such as `billingPaymentService` and `reportingPaymentService`.

### Exercise 2. Two Implementations of the Same Interface

```java
@Bean("cardGateway")
PaymentGateway cardGateway() {
    return new CardPaymentGateway();
}

@Bean("bankGateway")
PaymentGateway bankGateway() {
    return new BankPaymentGateway();
}
```

Inject `PaymentGateway` without a qualifier.

**Question:** Which error can appear?

**Answer:** `NoUniqueBeanDefinitionException` because two beans have different names yet share the same type.

**Fix:** Use `@Qualifier("cardGateway")` or mark one bean `@Primary` if a sensible default exists.

### Exercise 3. Auto-Configuration Back-Off

A starter creates a default `PaymentGateway`. The application needs to use its own gateway.

**Requirement:** update the starter so the default bean is created only when no `PaymentGateway` exists.

**Hint:** Use `@ConditionalOnMissingBean(PaymentGateway.class)` on the auto-configuration's bean method.

### Exercise 4. Identifying Bean Sources

An exception reports two sources:

```text
existing: SharedClientConfiguration#apiClient
new: ReportingConfiguration#apiClient
```

**Question:** What should you check before enabling overriding?

**Answer:** Determine whether both clients are needed, which bean callers expect, which configuration imports both classes, and whether renaming or conditionals can be used.

### Exercise 5. Context Testing

Use `ApplicationContextRunner` to verify that two configurations both registering `paymentGateway` cause context failure when overriding is disabled. Then rename the beans and verify the context starts.

**Goal:** test both the registration error and the fixed configuration.

## 26. Takeaways

- Bean names serve as registry identifier keys for bean definitions.
- `@Component`/`@Service` default to the decapitalized short class name; two classes with the same name in different packages can still collide.
- `@Bean` methods default to the method name as the bean name; explicit names and aliases can also collide.
- `BeanDefinitionOverrideException` concerns **duplicate registration names** within the same registry when overriding is disallowed.
- Multiple beans of the same type with different names usually cause `NoUniqueBeanDefinitionException`.
- `@Qualifier` and `@Primary` select among candidates; they do not fix two definitions sharing a bean name.
- Rename beans when multiple implementations are needed, or narrow component scanning if unintended beans are discovered.
- Auto-configurations should use `@ConditionalOnMissingBean` to yield to custom beans by contract.
- Use profile/property conditions when only one implementation should register at runtime.
- Exclude auto-configuration when the application does not need that feature, after understanding related beans.
- `spring.main.allow-bean-definition-overriding=true` can hide bugs and make behavior dependent on registration order; use only intentionally with clear tests.
- Inspect both old and new definitions in the exception; check component scanning, `@Import`, `@Bean`, aliases, test configs, and auto-configuration.
- Verify the context after fixing and confirm the right implementation is injected.

When encountering `BeanDefinitionOverrideException`, ask yourself: **"Which bean name is being registered twice, where do those two sources come from, do I need both beans or only to replace a default, and which implementation should callers receive?"** Answering these questions helps fix the real registry conflict instead of masking it with a global override setting.
