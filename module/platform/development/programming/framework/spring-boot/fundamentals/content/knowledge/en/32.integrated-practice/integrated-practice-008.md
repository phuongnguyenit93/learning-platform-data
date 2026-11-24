# Using the Conditions Report to Explain Why a Bean Appears or Is Absent

When a Spring Boot application starts, Spring does not create every bean unconditionally. Many beans are registered based on classpath, properties, profiles, application type, other existing beans, or project-defined conditions. This mechanism is especially important for **auto-configuration**: a starter may ship many configurations, yet only those matching the current application are applied.

When a bean appears unexpectedly or fails to be created, reading Java classes alone is often insufficient. You need to know which conditions Spring evaluated, whether they matched, and what message explains the outcome. Spring Boot provides the **Condition Evaluation Report** (conditions report) to observe this process.

This lesson explains how to enable the report, read positive/negative matches, exclusions, and unconditional classes, trace conditions for a bean, distinguish matching conditions from actual bean instantiation, and use the report to resolve common configuration issues.

## 1. Why Might a Bean Appear or Be Absent?

A Spring bean can be registered in several ways:

- Component scanning discovers classes with `@Component`, `@Service`, `@Repository`, `@Controller`, or corresponding stereotypes.
- A configuration class is imported and declares beans with `@Bean`.
- Spring Boot auto-configuration registers beans when matching conditions hold.
- A profile or property toggles a configuration on or off.
- A library/starter registers beans based on classpath or application type.
- Another configuration supplies a replacement bean, causing default auto-configuration to back off.

For example, an auto-configuration creating a client when the feature is enabled:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "app.catalog",
        name = "enabled",
        havingValue = "true"
)
public class CatalogClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    CatalogClient catalogClient() {
        return new DefaultCatalogClient();
    }
}
~~~

The `catalogClient` bean can appear when:

1. The auto-configuration is imported/discovered.
2. Property `app.catalog.enabled` equals `true`.
3. No matching `CatalogClient` bean exists that would cause `@ConditionalOnMissingBean` not to match.

If any condition fails, the bean may not be registered. The conditions report helps identify **which conditions were evaluated and their outcomes**.

### 1.1. Two Questions to Keep Separate

When investigating a bean:

- **Was the bean definition registered?** This is a question about configuration and conditions.
- **Was the bean instance created successfully?** This is a question about lifecycle, dependency injection, constructors, proxies, and bean initialization.

A matching condition does not guarantee the final object will be instantiated successfully. Conversely, a bean not appearing in the report does not necessarily indicate an error: that bean might be registered by component scan or a configuration without conditional annotations.

## 2. What Is the Conditions Report?

Spring Framework has the `Condition` abstraction and `@Conditional` annotation. Spring Boot extends that mechanism with specialized conditions such as:

- `@ConditionalOnClass` / `@ConditionalOnMissingClass`
- `@ConditionalOnBean` / `@ConditionalOnMissingBean`
- `@ConditionalOnProperty`
- `@ConditionalOnResource`
- `@ConditionalOnWebApplication` / `@ConditionalOnNotWebApplication`
- `@ConditionalOnSingleCandidate`
- `@ConditionalOnExpression`

When Spring evaluates conditions during configuration processing, Spring Boot records the results in `ConditionEvaluationReport`.

The report summarizes information such as:

- Which configuration sources were evaluated.
- Which conditions matched.
- Which conditions did not match and why.
- Which auto-configurations were excluded.
- Some non-conditional configurations recorded as unconditional classes.

The report is typically used to explain auto-configuration. It is especially helpful when a starter fails to create an expected bean or a default configuration appears unexpectedly.

### 2.1. The Report Is Not a List of All Beans

Do not mistake the conditions report for a dump of `ApplicationContext.getBeanDefinitionNames()`.

The report reflects **conditions that were evaluated and recorded**. It is not a complete inventory of every existing bean. Beans created by ordinary component scanning, beans without conditional annotations, or beans registered through other mechanisms may not appear as individual condition entries.

To find out which beans actually exist, use appropriate bean inspection; to find out why auto-configurations were selected or skipped, read the conditions report. The two tools answer complementary questions.

## 3. Enabling the Conditions Report with `--debug`

The fastest way when running the application is passing the `--debug` flag:

~~~bash
java -jar catalog-service.jar --debug
~~~

With Gradle:

~~~bash
./gradlew bootRun --args='--debug'
~~~

With Maven:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Build tool argument syntax varies by plugin and shell; what matters is that the application receives Spring Boot's `--debug` command-line argument.

You can also enable it via property:

~~~properties
debug=true
~~~

Or YAML:

~~~yaml
debug: true
~~~

`--debug` / `debug=true` tells Spring Boot to enable debug logging for **a selected set of core loggers** and print the conditions evaluation report. It does not mean enabling `DEBUG` for every logger in the application.

### 3.1. Debug Mode Is Not `logging.level.root=DEBUG`

The two settings have different scopes:

| Setting | Effect |
|---|---|
| `--debug` or `debug=true` | Enables selected Spring Boot debug logs and the conditions report |
| `logging.level.root=DEBUG` | Sets the root logger to DEBUG, which can drastically increase log volume across the whole app |
| `logging.level.org.springframework=DEBUG` | Enables DEBUG for the corresponding Spring package |
| `logging.level.com.example=TRACE` | Enables TRACE for the specified application package |

When you only need to understand auto-configuration, starting with `--debug` is usually enough. Do not enable DEBUG/TRACE across an entire production application just to view a condition report.

### 3.2. Where Does the Report Appear?

The report is normally written to console/log output during startup. When startup fails, evaluated conditions may also be printed alongside the failure information depending on phase and version.

Save the entire startup log, not just the last line. The report typically appears after initialization logs under headings like:

~~~text
CONDITIONS EVALUATION REPORT
============================
~~~

Logger names, log levels, and formatting can vary across Spring Boot versions.

## 4. Enabling the Report via the Actuator `conditions` Endpoint

If the application includes Spring Boot Actuator, you can use the `conditions` endpoint to view condition evaluation results over HTTP.

Add the dependency if not present:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

By default, Actuator web endpoints have very restricted exposure. To expose the `conditions` endpoint in a protected development environment:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,conditions
~~~

Then call:

~~~bash
curl http://localhost:8080/actuator/conditions
~~~

This URL assumes the default management base path `/actuator` and the same application port. If the application changes the base path, management port, or security rules, the URL and access permissions will differ.

The endpoint returns groups of information such as:

~~~json
{
  "positiveMatches": {
    "SomeAutoConfiguration": [
      {
        "condition": "OnClassCondition",
        "message": "..."
      }
    ]
  },
  "negativeMatches": {
    "OtherAutoConfiguration": [
      {
        "condition": "OnPropertyCondition",
        "message": "..."
      }
    ]
  },
  "exclusions": [],
  "unconditionalClasses": []
}
~~~

This is a simplified illustrative structure. Actual responses are longer and contain many more classes and conditions.

### 4.1. Securing the `conditions` Endpoint

The conditions report can expose:

- Application class and package names.
- Libraries present on the classpath.
- Property names and configuration condition details.
- Activated infrastructure components.

Never expose `/actuator/conditions` publicly just for debugging convenience. Enable it only in appropriate environments, restrict network access, authentication, and authorization, and disable exposure when no longer needed.

## 5. Reading the Report Structure

A conditions report is typically organized into major sections:

~~~text
CONDITIONS EVALUATION REPORT

Positive matches:
-----------------
...

Negative matches:
-----------------
...

Exclusions:
-----------
...

Unconditional classes:
----------------------
...
~~~

### 5.1. Positive Matches

These are configuration sources whose relevant conditions all matched.

Illustrative example:

~~~text
Positive matches:
-----------------

   DataSourceAutoConfiguration matched:
      - @ConditionalOnClass found required classes
        'javax.sql.DataSource', 'org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType'
      - @ConditionalOnMissingBean did not find any beans
        of type 'javax.sql.DataSource'
~~~

How to read it:

- `DataSourceAutoConfiguration` was evaluated.
- Required classes were present.
- No matching `DataSource` bean existed when the condition was checked.
- Auto-configuration can supply the default `DataSource` configuration.

Exact messages depend on classpath, version, bean definitions, and runtime configuration. The example above illustrates how to interpret them.

### 5.2. Negative Matches

This is the key section when a bean or configuration **does not appear**.

Example:

~~~text
Negative matches:
-----------------

   DataSourceAutoConfiguration:
      Did not match:
         - @ConditionalOnClass did not find required class
           'javax.sql.DataSource'
~~~

This indicates the required dependency or class is missing from the runtime classpath.

Another example:

~~~text
   SomeFeatureAutoConfiguration:
      Did not match:
         - @ConditionalOnProperty (app.feature.enabled=true)
           found different value in property 'enabled'
~~~

The property condition failed. Inspect the effective property value and which configuration source provided it.

A configuration can have multiple conditions; if any required condition fails to match, the configuration may be skipped. The report shows which condition caused the mismatch.

### 5.3. Exclusions

This section lists auto-configurations explicitly excluded, for example via:

~~~java
@SpringBootApplication(
        exclude = DataSourceAutoConfiguration.class
)
public class CatalogApplication {
}
~~~

Or via property:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

If an auto-configuration does not apply despite matching classpath and properties, check `exclude` and `spring.autoconfigure.exclude`.

### 5.4. Unconditional Classes

This section displays imported auto-configurations without standard conditional matching. Depending on version and setup, it may list infrastructure classes not represented as typical condition chains.

Do not assume every class in this section succeeded in creating all of its beans. This is still information about configuration/condition processing, not confirmation that the entire bean lifecycle completed.

## 6. Reading Individual Condition Messages

The report normally logs both the condition name and an explanatory message. Read the message before changing code.

### 6.1. `@ConditionalOnClass`

This condition matches when required classes are present on the classpath.

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.search.SearchClient")
public class SearchAutoConfiguration {

    @Bean
    SearchService searchService() {
        return new SearchService();
    }
}
~~~

If the dependency containing `com.vendor.search.SearchClient` is absent from the runtime classpath, the auto-configuration will not match.

In the report, look for `OnClassCondition` and which class was not found.

Distinguish compile-time dependencies from runtime dependencies. A library declared as `compileOnly` or an inappropriate Maven scope may compile in the IDE while missing the class in the executable runtime.

### 6.2. `@ConditionalOnMissingClass`

This condition matches when a class is absent:

~~~java
@ConditionalOnMissingClass("com.vendor.native.Driver")
class FallbackDriverConfiguration {
}
~~~

If the class appears on the classpath, the fallback configuration is not applied. This is commonly used to pick an alternative implementation when an optional library is absent.

### 6.3. `@ConditionalOnProperty`

Example:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "app.search",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class SearchConfiguration {
}
~~~

The condition matches when `app.search.enabled` equals `true` per property comparison rules.

Key attributes:

- `prefix`: property group prefix.
- `name` or `value`: property name(s) to check.
- `havingValue`: expected value.
- `matchIfMissing`: whether to match when the property is absent.

If `havingValue` is omitted, `@ConditionalOnProperty`'s default behavior normally matches if the property exists and is not equal to `false` (case-insensitive per annotation semantics). For strict boolean checks, declare `havingValue` explicitly.

The report explains whether the property was missing, held a different value, or failed the condition.

### 6.4. `@ConditionalOnBean`

~~~java
@AutoConfiguration
@ConditionalOnBean(SearchClient.class)
public class SearchMetricsAutoConfiguration {
}
~~~

The condition matches when a matching bean type is already registered and visible to the search strategy.

If the bean has not yet been registered when the condition is evaluated, the configuration may fail to match even if another configuration creates that bean later.

This is why ordering between auto-configurations matters.

### 6.5. `@ConditionalOnMissingBean`

~~~java
@AutoConfiguration
public class PaymentAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

The condition matches when no matching `PaymentGateway` bean exists within the search scope.

If the application provides its own implementation, the auto-configuration backs off and skips creating the default bean. This is normally the desired behavior for user overrides.

The report helps explain both cases:

- No existing bean: default bean is registered.
- Existing user bean: default bean is skipped because the missing-bean condition no longer holds.

**Important:** `@ConditionalOnMissingBean` is generally recommended for auto-configuration because it runs in an ordered bean registration pipeline. Do not scatter it arbitrarily across unrelated component configurations where bean definition processing order is unclear.

### 6.6. `@ConditionalOnSingleCandidate`

This condition fits when a configuration needs a bean that can be uniquely resolved by resolution rules, such as a single primary candidate among multiple beans of the same type.

If two beans of the same type exist without a suitable primary, the condition fails to match. Read the message to see whether Spring found a single candidate.

### 6.7. `@ConditionalOnWebApplication`

This condition distinguishes application context / web application types at runtime. An auto-configuration targeting servlet web applications will not activate in non-web or reactive applications depending on its condition.

When running tests with `WebApplicationType.NONE`, seeing web auto-configurations not match is normal.

### 6.8. `@Profile`

`@Profile` is also a conditional mechanism in Spring:

~~~java
@Configuration
@Profile("dev")
class DevelopmentConfiguration {
}
~~~

If the `dev` profile is inactive, the configuration is not registered. When investigating, check:

~~~properties
spring.profiles.active=dev
~~~

or the corresponding environment variable / command-line argument.

The report can show profile conditions being evaluated, though you should also inspect actual profile sources and Config Data settings.

## 7. Searching for a Bean by Name in the Report

Once you know the desired bean, look up the **configuration class name or factory method name** involved.

Example:

~~~java
@AutoConfiguration
public class SearchClientAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.search",
            name = "enabled",
            havingValue = "true"
    )
    SearchClient searchClient() {
        return new DefaultSearchClient();
    }
}
~~~

The default bean name is typically `searchClient`. In the report, the condition source may appear as:

~~~text
SearchClientAutoConfiguration#searchClient
~~~

This indicates the condition on the bean factory method is being evaluated.

If the report shows the method condition did not match, read its message. If a class-level condition did not match, none of the bean methods inside that configuration are processed as intended.

### 7.1. The Bean Name May Differ from the Class Name

A `@Bean` method can customize the bean name:

~~~java
@Bean("primarySearchClient")
SearchClient searchClient() {
    return new DefaultSearchClient();
}
~~~

The source name in the report may use the class/method name, whereas the bean registry uses the custom bean name. When cross-referencing, distinguish the **configuration source** from the **final bean name**.

## 8. Why Can a Condition Match Yet the Bean Still Be Absent?

This is one of the most common points of confusion.

The conditions report may show that a configuration/bean method passed all conditions. Yet afterward, the bean can still fail to instantiate or be inaccessible as expected.

Causes include:

1. The bean's constructor throws an exception.
2. A required dependency is missing.
3. Multiple candidates cause `NoUniqueBeanDefinitionException`.
4. Bean initialization or `@PostConstruct` fails.
5. The bean is proxied, and the caller injects the wrong type.
6. Scope or lazy initialization means the instance has not been created at check time.
7. The bean definition has a different name than what you are looking for.
8. Another configuration modifies/overrides the registration in a supported way.

Example:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.search",
        name = "enabled",
        havingValue = "true"
)
SearchClient searchClient(RequiredCredential credential) {
    return new DefaultSearchClient(credential);
}
~~~

The property condition matches, yet if `RequiredCredential` does not exist, bean creation fails. The report does not turn a dependency injection failure into a condition mismatch.

**Distinction:** the report explains *why a configuration was selected or skipped*. The startup exception explains *why object creation subsequently failed*.

## 9. Why Can a Bean Exist Yet Not Appear in the Conditions Report?

Not every bean is created by a conditional auto-configuration.

Example:

~~~java
@Service
public class OrderService {
}
~~~

This bean is registered by component scanning without a separate conditional configuration entry recorded in the report.

Similarly:

~~~java
@Configuration(proxyBeanMethods = false)
class OrderConfiguration {

    @Bean
    OrderPolicy orderPolicy() {
        return new DefaultOrderPolicy();
    }
}
~~~

If the configuration uses no conditions, do not expect the conditions report to have a positive-match entry explaining this bean.

To verify which beans actually exist:

~~~java
String[] names =
        applicationContext.getBeanNamesForType(OrderPolicy.class);
~~~

Or:

~~~java
Map<String, OrderPolicy> candidates =
        applicationContext.getBeansOfType(OrderPolicy.class);
~~~

These APIs answer which candidates are in the bean registry. Use them together with the conditions report to understand why auto-configuration backed off or where a bean was registered.

## 10. Distinguishing the Report from Bean Inventory and Dependency Graph

These three tools serve different purposes:

| Tool | Question answered |
|---|---|
| Conditions report | Which conditions/configurations matched or did not match, and why? |
| Bean inventory | Which bean names/types are registered in the context? |
| Dependency graph/exception chain | Which bean needs which bean, and where did dependency resolution fail? |

For example:

- The report states `PaymentAutoConfiguration` did not match because a `PaymentGateway` already exists.
- Bean inventory shows two beans: `stripeGateway` and `bankGateway`.
- Startup exception reports `CheckoutService` required a single `PaymentGateway` but found two candidates.

No single tool replaces the others.

### 10.1. Actuator `beans` Endpoint

If Actuator is enabled and the `beans` endpoint is exposed under access control:

~~~text
GET /actuator/beans
~~~

This endpoint helps inspect bean names, types, and contexts. It is suited for confirming which beans were registered, while `/actuator/conditions` explains auto-configuration conditions.

Keep diagnostic endpoints inside protected networks. They can disclose application internals.

## 11. Reading Exclusions to Find Excluded Auto-Configurations

An application can exclude auto-configurations via annotation:

~~~java
@SpringBootApplication(
        exclude = {
                DataSourceAutoConfiguration.class,
                SecurityAutoConfiguration.class
        }
)
public class CatalogApplication {
}
~~~

Or via property configuration:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

When a starter's default bean is missing, check the `Exclusions` section.

Do not confuse an exclusion with a negative match:

- **Exclusion:** auto-configuration was explicitly requested to be excluded.
- **Negative match:** configuration was evaluated, and one or more conditions did not match.
- **Positive match:** relevant conditions all matched.

If an auto-configuration is excluded, tweaking properties to satisfy an internal condition will not bring it back; you must remove the exclusion first.

## 12. Investigating Missing or Incorrect Properties

Suppose the report states:

~~~text
@ConditionalOnProperty (app.search.enabled=true) did not find property 'enabled'
~~~

Check:

1. Does the property name use the exact prefix?
2. Is there a typo such as `app.search.enabled` vs. `app.search.enable`?
3. Is the expected profile active?
4. Is the config file in a Config Data location that gets loaded?
5. Does the environment variable map correctly to the property name?
6. Was the command-line argument actually passed to the Spring Boot process?
7. Did another property source override the value?
8. Are `havingValue` and `matchIfMissing` used as intended?

Configuration example:

~~~yaml
app:
  search:
    enabled: true
~~~

Corresponding environment variable via relaxed binding:

~~~text
APP_SEARCH_ENABLED=true
~~~

Running via command line:

~~~bash
java -jar catalog.jar --app.search.enabled=true
~~~

If the application still reports the property is missing, verify the running process actually received the argument and active profile/config location. Do not look only at a YAML file in the repository and assume runtime loaded it.

### 12.1. Actuator `env` Endpoint

The `/actuator/env` endpoint can help inspect property sources and effective values when exposed and secured appropriately. However, it can reveal sensitive configuration details, so never expose it publicly.

When investigating locally, selectively print non-sensitive property names and sources; avoid dumping the entire Environment or logging credentials.

## 13. Investigating Classpath and Dependency Scopes

If the report shows `@ConditionalOnClass` did not match, inspect the runtime dependency graph.

Gradle example:

~~~groovy
dependencies {
    compileOnly 'com.vendor:search-client'
}
~~~

Code compiles if the API is visible on the compile classpath, yet `compileOnly` does not add the library to the runtime classpath. When running the executable JAR, the class will be missing.

If the application needs the library at runtime:

~~~groovy
dependencies {
    implementation 'com.vendor:search-client'
}
~~~

Or `runtimeOnly` if code does not reference the API at compile time yet the library is required at runtime.

Inspect in Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

And inspect a specific dependency:

~~~bash
./gradlew dependencyInsight \
    --configuration runtimeClasspath \
    --dependency search-client
~~~

Maven:

~~~bash
./mvnw dependency:tree
~~~

Then inspect the built artifact, such as dependencies inside `BOOT-INF/lib` of the executable JAR. IDE classpaths and runtime artifacts do not always match.

## 14. Investigating `@ConditionalOnBean` and Auto-Configuration Ordering

A configuration may depend on a bean registered by another configuration:

~~~java
@AutoConfiguration
@ConditionalOnBean(SearchClient.class)
public class SearchIndexAutoConfiguration {

    @Bean
    SearchIndex searchIndex(SearchClient client) {
        return new SearchIndex(client);
    }
}
~~~

If `SearchClient` has not been registered when this condition is evaluated, `SearchIndexAutoConfiguration` may fail to match.

In auto-configuration, ordering matters because conditions like `@ConditionalOnBean` and `@ConditionalOnMissingBean` only see bean definitions already processed at evaluation time.

Spring Boot provides ordering mechanisms such as:

~~~java
@AutoConfiguration(after = SearchClientAutoConfiguration.class)
public class SearchIndexAutoConfiguration {
}
~~~

In older styles/versions you may see `@AutoConfigureAfter`, `@AutoConfigureBefore`, or `@AutoConfigureOrder`.

### 14.1. Why Does `@ConditionalOnMissingBean` Usually Fit Auto-Configuration?

A starter wants to provide a default bean while letting applications override it:

~~~java
@AutoConfiguration
public class SearchClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SearchClient.class)
    SearchClient searchClient() {
        return new DefaultSearchClient();
    }
}
~~~

If user configuration already registered a `SearchClient` before the auto-configuration evaluates its condition, the default bean backs off.

If an auto-configuration depends on a bean created later without proper ordering, the condition may miss the expected bean. Design ordering and conditions around auto-configuration rules, never relying on accidental component scan order.

### 14.2. Do Not Use `@ConditionalOnMissingBean` to Choose Between Two User Beans

If an application registers two implementations of the same type, `@ConditionalOnMissingBean` in a starter only decides whether to add a default bean. It does not choose between the two application-supplied implementations.

If a service needs a single bean, you still must use `@Primary`, `@Qualifier`, or a registry strategy.

## 15. Investigating Component Scan and Imports

If a bean does not appear yet the conditions report has no relevant negative match, the configuration may never have been brought into the context.

Check:

- Is the class's package within `@ComponentScan` scope?
- Was the configuration `@Import`ed?
- Did the starter register its auto-configuration using metadata matching its Boot version?
- In modern Spring Boot, are auto-configuration candidates listed in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`?
- In older starters, metadata may use `META-INF/spring.factories` per the corresponding version's mechanism.
- Is the dependency containing the configuration class on the runtime classpath?

Modern auto-configuration structure example:

~~~text
my-starter.jar
└── META-INF/
    └── spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Content:

~~~text
com.example.search.autoconfigure.SearchClientAutoConfiguration
~~~

If the metadata file is missing or misspells the class name, the auto-configuration will not be discovered. When a class is never imported/evaluated, the conditions report cannot show a negative match entry for it.

## 16. Conditions Report and `@ConditionalOnMissingBean`: Why Did the Default Bean Disappear?

A common scenario:

~~~java
@AutoConfiguration
public class CacheClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CacheClient.class)
    CacheClient cacheClient() {
        return new DefaultCacheClient();
    }
}
~~~

Meanwhile the application declares:

~~~java
@Configuration(proxyBeanMethods = false)
class ApplicationCacheConfiguration {

    @Bean
    CacheClient customCacheClient() {
        return new RedisCacheClient();
    }
}
~~~

Expected outcome:

- `customCacheClient` exists.
- The default `cacheClient` is not created.
- The conditions report notes the missing-bean condition did not match because a `CacheClient` bean was already found.

This is **back-off behavior** of auto-configuration, not an error.

If the application truly expects both beans, review the types, qualifiers, and design intent. `@ConditionalOnMissingBean` exists specifically to avoid creating a default when the user has supplied an implementation.

### 16.1. Why Doesn't the Report Tell You Where the Custom Bean Came From?

The report shows that the auto-configuration condition found a matching bean, though it does not always give the full registration story of that bean in the same entry.

Use bean inventory or bean definition inspection to identify which component or configuration declared the custom bean.

## 17. Writing Custom Conditions and Reading the Report

An application can define a custom condition when built-in annotations cannot express the rule.

Example condition checking a system/environment property:

~~~java
public class ExternalModeCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        return "external".equals(
                context.getEnvironment()
                        .getProperty("app.mode")
        );
    }
}
~~~

Usage:

~~~java
@Configuration
@Conditional(ExternalModeCondition.class)
class ExternalModeConfiguration {
}
~~~

When the condition fails to match, the configuration is skipped. The conditions report records the condition outcome, though custom messages are much more helpful when the condition states a clear reason.

### 17.1. Using `SpringBootCondition` for Clearer Messages

Spring Boot provides `SpringBootCondition` for conditions that integrate with condition evaluation reporting.

Illustrative example:

~~~java
public class ExternalModeCondition extends SpringBootCondition {

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        String mode = context.getEnvironment()
                .getProperty("app.mode");

        if ("external".equals(mode)) {
            return ConditionOutcome.match(
                    "app.mode is external"
            );
        }

        return ConditionOutcome.noMatch(
                "app.mode must be external; current value is " + mode
        );
    }
}
~~~

To compile, include the appropriate Boot condition API imports:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;
~~~

Messages should:

- Clearly state the condition being checked.
- State the reason for match/no-match.
- Never leak secrets or sensitive config values.
- Be concise enough for operators to understand.
- Avoid expensive I/O during condition evaluation.

### 17.2. Conditions Must Be Deterministic and Lightweight

Conditions are evaluated during configuration registration. Avoid:

- Making HTTP calls to external services.
- Querying a database to decide whether to register a bean.
- Mutating system state.
- Depending on random timing or side effects.
- Logging tokens/passwords inside messages.

Conditions are suited for checking classpath, environment properties, bean definitions, and available metadata. Runtime connectivity checks belong in health indicators, initialization, or service logic—never inside conditions.

## 18. Accessing `ConditionEvaluationReport` Programmatically

In advanced diagnostic scenarios, you can read the report from the bean factory:

~~~java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(beanFactory);
~~~

This API lives in package:

~~~java
org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport
~~~

The report exposes information such as condition outcomes by source, exclusions, and unconditional classes. Exact method names/types should be checked against the Spring Boot version your project compiles against.

Conceptual example reading sources:

~~~java
report.getConditionAndOutcomesBySource()
        .forEach((source, outcomes) -> {
            System.out.println(source);
            System.out.println("Matched: " + outcomes.isFullMatch());
        });
~~~

This is a diagnostic example, not code for business services. `ConditionEvaluationReport` is an API for auto-configuration diagnostics; avoid building business logic dependent on report structure or version-specific implementation details.

### 18.1. Reading the Report at the Right Time

The report only contains conditions evaluated up to the moment it is read. Accessing it too early misses configurations/conditions not yet processed.

For diagnostics, prefer reading after the context is prepared or from the Actuator `conditions` endpoint. If the context fails before refresh completes, rely on the startup report and exception log emitted by Boot.

## 19. Testing Auto-Configuration with `ApplicationContextRunner`

The conditions report is great for manual debugging, yet auto-configurations should also be covered by tests for important conditions.

`ApplicationContextRunner` spins up a small context, applies a set of configurations, properties, and user beans, and verifies the outcomes.

Auto-configuration example:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "app.catalog",
        name = "enabled",
        havingValue = "true"
)
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient catalogClient() {
        return new DefaultCatalogClient();
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CatalogAutoConfiguration.class
                            )
                    );

    @Test
    void createsClientWhenFeatureIsEnabled() {
        contextRunner
                .withPropertyValues("app.catalog.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(CatalogClient.class);
                    assertThat(context.getBean(CatalogClient.class))
                            .isInstanceOf(DefaultCatalogClient.class);
                });
    }

    @Test
    void doesNotCreateClientWhenFeatureIsDisabled() {
        contextRunner
                .withPropertyValues("app.catalog.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(CatalogClient.class);
                });
    }
}
~~~

The example assumes appropriate test dependencies and that `CatalogAutoConfiguration` is compiled on the test classpath.

### 19.1. Testing User Override

~~~java
@Test
void backsOffWhenUserProvidesClient() {
    contextRunner
            .withPropertyValues("app.catalog.enabled=true")
            .withBean(
                    CatalogClient.class,
                    () -> new CustomCatalogClient()
            )
            .run(context -> {
                assertThat(context).hasSingleBean(CatalogClient.class);
                assertThat(context.getBean(CatalogClient.class))
                        .isInstanceOf(CustomCatalogClient.class);
            });
}
~~~

This test confirms `@ConditionalOnMissingBean` backs off when the user provides an implementation.

### 19.2. Testing Classpath Conditions

For classpath-dependent conditions, `ApplicationContextRunner` supports classloader/filtering utilities as needed. The goal is testing both branches:

- Dependency present: auto-configuration applies.
- Dependency absent: auto-configuration steps aside while the context still starts.

Do not test only the "every dependency is present" case, because starters must behave properly when optional libraries are missing.

### 19.3. Why Are Runner Tests Better Than Booting the Whole App?

Small auto-configuration tests give precise control over:

- Property values.
- User-provided beans.
- Classpath.
- Web application type.
- Import order.
- Resulting bean registrations.

They pinpoint match/no-match reasons without starting databases, web servers, or an entire production system.

## 20. Practical Workflow When a Bean Is Missing

Suppose the application needs `SearchClient`, yet:

~~~java
@Autowired
SearchClient searchClient;
~~~

fails to resolve or the context reports a missing bean.

Follow these steps in order:

**Step 1 — Enable the report**

~~~bash
java -jar catalog.jar --debug
~~~

Or set `debug=true` in local configuration.

**Step 2 — Locate the relevant auto-configuration**

Search for class names like `SearchAutoConfiguration`, `SearchClientAutoConfiguration`, or the corresponding bean factory method.

**Step 3 — Read the negative match**

Look at the exact condition message:

- Missing class?
- Missing property?
- Wrong property value?
- Dependent bean not yet registered?
- Single candidate not found?
- Inactive profile?

**Step 4 — Check exclusions**

Look for the auto-configuration under `Exclusions`, and check `spring.autoconfigure.exclude` and annotations on the application class.

**Step 5 — Check the runtime classpath**

Inspect the dependency tree and actual artifact. Pay special attention to `compileOnly`, `provided`, `optional`, and exclusions.

**Step 6 — Check Config Data**

Verify active profiles, config locations, environment variables, command-line properties, and override values.

**Step 7 — Check bean inventory**

If the report shows the configuration matched, check whether the bean definition exists. If the bean exists yet injection failed, inspect qualifiers, primary, and the dependency graph.

**Step 8 — Read the bean creation root cause**

If conditions matched yet the bean failed to instantiate, trace `BeanCreationException`, `UnsatisfiedDependencyException`, or deeper initialization errors.

**Step 9 — Write a reproduction test**

Use `ApplicationContextRunner` with the failing properties/beans/classpath to lock down the expected behavior.

## 21. Workflow When a Bean Appears Unexpectedly

Suppose the application did not want auto-configuration to create a default `DataSource`, yet one still appears.

Check:

1. Does Positive matches list `DataSourceAutoConfiguration`?
2. Did `@ConditionalOnClass` match because JDBC classes are present?
3. Did `@ConditionalOnMissingBean` match because no other `DataSource` bean existed?
4. Do properties enable an embedded database or configure a datasource?
5. Did a starter transitively pull JDBC/embedded database onto the classpath?
6. Did a profile or config import enable a datasource?
7. Should the auto-configuration be excluded if the application genuinely does not use it?

If a user `DataSource` bean was registered, default auto-configuration usually backs off via the missing-bean condition. If the report says no bean was found, investigate why user configuration was not processed before the condition or why the bean type did not match.

Do not exclude all of `DataSourceAutoConfiguration` just to hide a duplicate-bean bug if the application still needs a datasource. Identify which unwanted default bean appeared and pick the right fix.

## 22. Cases Where the Report Does Not Give a Direct Answer

The conditions report is very helpful, yet it has limits.

### 22.1. Configuration Was Never Discovered

If a class was not reached by component scan, `@Import`, or auto-configuration discovery, its conditions never ran. There will be no negative match entry to read.

### 22.2. Bean Created by Component Scanning

An ordinary `@Service` may not have a dedicated condition report entry. Use bean inventory and inspect scan base packages.

### 22.3. Bean Creation Failed After Conditions Matched

The report does not replace stack traces. Read exceptions for constructors, dependencies, initialization, proxies, or resources.

### 22.4. Bean Overridden or Multiple Candidates

The conditions report may show default auto-configuration backed off, while `NoUniqueBeanDefinitionException` still requires inspecting candidate lists and qualifiers/primary.

### 22.5. Properties Changed After Startup

Condition evaluation runs while configuring the context. Mutating the Environment afterward does not re-run auto-configuration to add or remove beans. Bean definitions are not runtime feature toggles.

### 22.6. Custom Conditions With Unhelpful Messages

If a custom condition returns a generic outcome, the report can only print a generic explanation. Return clear messages in `SpringBootCondition` or use built-in conditions when suitable.

## 23. Common Errors and How to Handle Them

| Symptom | Common cause | Resolution |
|---|---|---|
| No conditions report visible | Debug not enabled or output suppressed by logging config | Run with `--debug` or `debug=true` |
| Auto-configuration missing from report | Class not discovered/imported or absent from runtime classpath | Check starter metadata, component/import, and dependencies |
| Negative match due to missing class | Dependency absent on runtime classpath | Fix dependency scope/version and check executable artifact |
| Negative match due to property | Wrong name, value, profile, or config location | Check property sources and `havingValue`/`matchIfMissing` |
| Default bean not created | `@ConditionalOnMissingBean` saw a matching user bean | This may be proper back-off; inspect bean inventory |
| Condition matched yet bean missing | Constructor/dependency/initialization failed | Read root cause of `BeanCreationException` |
| Bean exists yet absent from report | Registered via component scan or non-conditional config | Inspect bean inventory |
| Auto-config skipped despite matching conditions | Exclusion or another ordering/bean condition | Check exclusions and all condition outcomes |
| Bean exists in test but not in production | Different profiles, classpath, properties, or runtime config | Reproduce production configuration in a context test |
| Bean appears twice | Two registration paths or two implementations of same type | Check component scan, `@Bean`, imports, and qualifiers |
| Actuator conditions returns 404 | Endpoint not exposed or different management path/port | Configure exposure and check URL |
| Actuator conditions returns 401/403 | Security rules restrict endpoint | Grant minimal internal role; never open publicly |
| Report exposes too much detail | Broad debug enabled or diagnostic endpoint exposed | Disable debug after investigation; restrict access |
| Custom condition message is cryptic | Generic outcome message | Provide specific match/no-match messages without secrets |

## 24. Quick Checklist for Reading the Report

When opening a conditions report, proceed in order:

1. **Search for the auto-configuration or bean method name** related to the dependency under investigation.
2. Identify whether it sits under **Positive matches**, **Negative matches**, or **Exclusions**.
3. Read every condition message under that entry, not just the first line.
4. If `@ConditionalOnProperty` is present, verify property name, value, and active profile.
5. If `@ConditionalOnClass` is present, verify runtime dependencies.
6. If `@ConditionalOnBean` or `@ConditionalOnMissingBean` is present, inspect bean definitions and ordering.
7. If the configuration matched, verify the bean definition/instance via bean inventory.
8. If the bean failed to instantiate, trace the exception chain and root cause.
9. If the configuration is missing from the report, inspect discovery, imports, and component scan.
10. After identifying the cause, write a test reproducing both match and no-match branches.

## 25. Key Principles

- **The conditions report explains conditional configuration decisions**, especially auto-configuration.
- Use `--debug` or `debug=true` to print the report at startup.
- `--debug` does not mean enabling DEBUG for all loggers.
- Actuator `/actuator/conditions` serves the report over HTTP when exposed.
- **Positive matches** show matched conditions; **negative matches** state why conditions failed.
- **Exclusions** list explicitly excluded auto-configurations.
- **Unconditional classes** report configurations without typical conditions, not a guarantee every bean was created.
- The report is not a full bean list; use bean inventory to verify which beans actually exist.
- A matching condition does not guarantee successful bean instantiation; read exceptions on lifecycle/dependency errors.
- `@ConditionalOnMissingBean` lets user beans replace default auto-configurations.
- Auto-configuration ordering can affect `@ConditionalOnBean` and `@ConditionalOnMissingBean`.
- If a configuration is never discovered/imported, the report may have no entry explaining it.
- Custom conditions should be lightweight, deterministic, and produce clear messages.
- Never expose Actuator diagnostics publicly or put secrets into condition messages.
- Use `ApplicationContextRunner` to test property, classpath, and user-override branches.

**Conclusion:** Whenever a bean appears or is absent, the conditions report tells you which conditions Spring Boot evaluated and why each matched or failed. Start with `--debug`, locate the right configuration source, read positive/negative matches and exclusions, and cross-check with bean inventory and exception chains. Investigating layer by layer distinguishes property, classpath, auto-configuration ordering, component scanning, and bean creation issues without guessing blindly at annotations or dependencies.
