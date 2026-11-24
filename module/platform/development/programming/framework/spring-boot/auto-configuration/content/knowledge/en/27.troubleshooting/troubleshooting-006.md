# Prerequisite Bean Exists Yet Dependent Configuration Was Evaluated at the Wrong Time

## 1. Symptom and Root Cause

A perplexing bug in Spring Boot auto-configuration occurs when a prerequisite bean eventually appears in the **ApplicationContext**, yet a bean depending on it never gets registered. Logs may show the prerequisite was created successfully, while **@ConditionalOnBean** on the dependent auto-configuration reports that the bean could not be found.

The cause can lie in when conditions are evaluated:

1. Spring processes configuration classes and registers bean definitions.
2. Bean conditions are evaluated during that processing.
3. Only after definitions are registered does Spring create bean instances according to the dependency graph and lifecycle.

**@ConditionalOnBean** and **@ConditionalOnMissingBean** see only the bean definitions already processed at the moment the condition runs. They do not wait for the context to finish initializing and then re-evaluate. If the dependent auto-configuration runs before the auto-configuration supplying the prerequisite bean, the condition can return **false**. A prerequisite bean registered afterward does not trigger the earlier condition to run again.

Therefore, a message stating "bean does not exist" sometimes literally means "the bean definition had not been processed yet at check time." It does not necessarily mean the dependency is missing from the entire application.

This lesson uses **Java 17 and Spring Boot 3.3.13** to demonstrate how to spot the error, declare ordering, design bean conditions, inspect type metadata, and write tests with **ApplicationContextRunner**.

## 2. Distinguishing Bean Definitions from Bean Instances

| Concept | Meaning | Timing |
|---|---|---|
| Bean definition | Metadata describing a bean: name, type, factory method, scope, dependencies, and initialization rules | Registered during the configuration processing phase |
| Bean instance | Actual Java object created from a bean definition | Usually created during context refresh or upon request if lazy |
| Bean condition | Condition deciding whether a configuration/bean definition is registered | When Spring processes configurations and registers bean definitions |
| Dependency injection | Wiring bean instances to their dependencies | When beans are created and initialized |

For example, when Spring processes:

~~~java
@Bean
SearchClient searchClient() {
    return new SearchClient();
}
~~~

Spring can register the bean definition for **searchClient** before the **SearchClient** object is instantiated. A bean-type condition can recognize this definition if it has already been processed and the method signature provides sufficient type information.

Conversely, if the condition runs before the configuration containing that method is processed, the registry has no definition for the condition to find. A log entry appearing after the application boots successfully does not prove the bean was present when the condition was evaluated.

## 3. Bean Conditions See Only Already-Processed Definitions

**@ConditionalOnBean** matches when a bean meeting the criteria already exists in the BeanFactory. It can check by type, bean name, or annotation.

By type:

~~~java
@Bean
@ConditionalOnBean(SearchClient.class)
SearchFacade searchFacade(SearchClient client) {
    return new SearchFacade(client);
}
~~~

By name:

~~~java
@Bean
@ConditionalOnBean(name = "acmeSearchClient")
SearchFacade searchFacade(SearchClient client) {
    return new SearchFacade(client);
}
~~~

**@ConditionalOnMissingBean** has the same timing limitation. If an auto-configuration providing a default bean runs before a configuration containing a custom bean, the condition may mistakenly conclude no bean exists and register the default.

Spring Boot recommends placing **@ConditionalOnBean** and **@ConditionalOnMissingBean** on auto-configuration classes. Auto-configuration is processed after application-declared bean definitions, allowing it to recognize custom beans.

Do not place a bean condition on an arbitrary component-scanned configuration class and assume every other bean is already registered. Processing order for regular configurations may not satisfy that assumption.

## 4. Typical Failure Scenario

Suppose a library has two auto-configurations:

- **SearchClientAutoConfiguration** provides the prerequisite bean **SearchClient**.
- **SearchFacadeAutoConfiguration** provides **SearchFacade** only when **SearchClient** already exists.

Without ordering declared, the dependent configuration can be processed first:

~~~text
1. Spring processes SearchFacadeAutoConfiguration
2. @ConditionalOnBean(SearchClient.class) is evaluated
3. SearchClient definition has not been processed yet
4. Condition returns false
5. SearchFacade is not registered
6. Spring processes SearchClientAutoConfiguration
7. SearchClient definition is registered
8. Context continues initialization and SearchClient appears
9. Earlier condition is not re-evaluated
~~~

The final outcome can be:

| Bean | State |
|---|---|
| SearchClient | Present |
| SearchFacade | Absent |
| ApplicationContext | May still start successfully |

If another bean strictly requires injecting SearchFacade, the application can fail with **UnsatisfiedDependencyException** or **NoSuchBeanDefinitionException**. If no bean requires the facade, the bug surfaces merely as an optional feature staying inactive.

## 5. The Fix: Declaring Auto-Configuration Order

Spring Boot provides **before**, **beforeName**, **after**, and **afterName** on **@AutoConfiguration**. When the prerequisite belongs to the same library, declare **after** directly.

### 5.1. Prerequisite Bean

File src/main/java/com/acme/search/SearchClient.java:

~~~java
package com.acme.search;

public class SearchClient {

    private final String provider;

    public SearchClient(String provider) {
        this.provider = provider;
    }

    public String provider() {
        return this.provider;
    }
}
~~~

### 5.2. Dependent Bean

File src/main/java/com/acme/search/SearchFacade.java:

~~~java
package com.acme.search;

public class SearchFacade {

    private final SearchClient client;

    public SearchFacade(SearchClient client) {
        this.client = client;
    }

    public String provider() {
        return this.client.provider();
    }
}
~~~

### 5.3. Auto-Configuration Supplying the Prerequisite Bean

File SearchClientAutoConfiguration.java:

~~~java
package com.acme.search.autoconfigure;

import com.acme.search.SearchClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class SearchClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SearchClient.class)
    SearchClient searchClient() {
        return new SearchClient("starter-default");
    }
}
~~~

**@ConditionalOnMissingBean** lets the application replace the default client with its own bean. The method returns the concrete type **SearchClient**, giving other bean conditions sufficient type information when inspecting the definition.

### 5.4. Dependent Auto-Configuration

File SearchFacadeAutoConfiguration.java:

~~~java
package com.acme.search.autoconfigure;

import com.acme.search.SearchClient;
import com.acme.search.SearchFacade;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = SearchClientAutoConfiguration.class)
public class SearchFacadeAutoConfiguration {

    @Bean
    @ConditionalOnBean(SearchClient.class)
    SearchFacade searchFacade(SearchClient client) {
        return new SearchFacade(client);
    }
}
~~~

The **after** attribute declares that **SearchFacadeAutoConfiguration** must be applied after **SearchClientAutoConfiguration**. When the facade's bean condition is evaluated, the client's definition has already been processed.

The **SearchClient client** parameter lets Spring inject the client when creating the facade, yet parameters do not replace condition ordering. The condition must match first for the bean method to be registered.

### 5.5. Registering Auto-Configurations

Create src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports:

~~~text
com.acme.search.autoconfigure.SearchClientAutoConfiguration
com.acme.search.autoconfigure.SearchFacadeAutoConfiguration
~~~

Each line is the fully qualified name of an auto-configuration class. Ordering is declared via annotations; do not rely on the incidental order of lines in the imports file to express dependencies.

Auto-configurations should be discovered via the imports file. Do not include the library's package in the application's component scan as a substitute for this mechanism.

## 6. Testing with ApplicationContextRunner

**ApplicationContextRunner** tests auto-configurations in a minimal context. **AutoConfigurations.of(...)** applies the ordering metadata of the provided auto-configurations.

File SearchAutoConfigurationTests.java:

~~~java
package com.acme.search.autoconfigure;

import com.acme.search.SearchClient;
import com.acme.search.SearchFacade;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class SearchAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    SearchFacadeAutoConfiguration.class,
                                    SearchClientAutoConfiguration.class
                            )
                    );

    @Test
    void registersDependentBeanAfterPrerequisiteDefinition() {
        this.runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(SearchClient.class);
            assertThat(context).hasSingleBean(SearchFacade.class);
            assertThat(context.getBean(SearchFacade.class).provider())
                    .isEqualTo("starter-default");
        });
    }

    @Test
    void skipsDependentBeanWhenPrerequisiteIsAbsent() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                SearchFacadeAutoConfiguration.class
                        )
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(SearchClient.class);
                    assertThat(context).doesNotHaveBean(SearchFacade.class);
                });
    }

    @Test
    void usesApplicationDefinedPrerequisite() {
        this.runner
                .withUserConfiguration(UserSearchClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(SearchClient.class);
                    assertThat(context).hasSingleBean(SearchFacade.class);
                    assertThat(context.getBean(SearchFacade.class).provider())
                            .isEqualTo("application");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserSearchClientConfiguration {

        @Bean
        SearchClient applicationSearchClient() {
            return new SearchClient("application");
        }
    }
}
~~~

Three test cases demonstrate three behaviors:

| Scenario | Expected outcome |
|---|---|
| Both auto-configurations present | Both client and facade are registered; facade uses default client |
| Only dependent auto-configuration present | Condition does not match; context still starts without facade |
| Application declares custom client | Default client backs off; facade uses application's client |

The first test intentionally lists the dependent auto-configuration before the prerequisite auto-configuration. The **after** annotation still guarantees the correct application order.

With Maven and Spring Boot 3.3.13, **spring-boot-autoconfigure** and **spring-boot-starter-test** (in test scope) are required. Place the 3.3.13 BOM in dependencyManagement or use the Spring Boot parent; the project requires Java 17.

Run:

~~~bash
./mvnw -Dtest=SearchAutoConfigurationTests test
~~~

Expected output when classes and dependencies are in the right packages:

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This is the expected output for the example, not the result of running on the current project.

## 7. Choosing Between before, after, and afterName

| Attribute | Meaning | When to use |
|---|---|---|
| **@AutoConfiguration(after = Other.class)** | Apply after the specified auto-configuration | Direct dependency exists and class is on the compile classpath |
| **@AutoConfiguration(before = Other.class)** | Apply before the specified auto-configuration | Configuration must register bean definitions ahead of another |
| **@AutoConfiguration(afterName = "...")** | Apply after the class named as a String | Avoid creating a compile dependency on an optional auto-configuration |
| **@AutoConfiguration(beforeName = "...")** | Apply before the class named as a String | Need ordering without a direct class reference |
| **@AutoConfigureAfter / @AutoConfigureBefore** | Dedicated ordering annotations | Use when separate annotations are needed or for style consistency |
| **@AutoConfigureOrder** | Set general ordering among auto-configurations | Auto-configurations with no direct relation that still need relative ordering |

If the prerequisite bean comes from an optional library whose auto-configuration class is not on the compile classpath, use the fully qualified name:

~~~java
@AutoConfiguration(
    afterName = "com.vendor.search.autoconfigure.VendorSearchAutoConfiguration"
)
public class AcmeSearchAutoConfiguration {
}
~~~

Declaring by name avoids referencing the optional class directly. If the prerequisite auto-configuration is absent from the runtime classpath, the prerequisite bean will also be absent; **@ConditionalOnBean** must still check whether the feature should be registered.

For a direct relationship between two classes in the same library, **after = SomeAutoConfiguration.class** is usually clearer and easier to refactor.

## 8. Ordering Bean Definitions vs. Ordering Bean Instances

Do not use **@DependsOn** or **@Order** to fix a bean condition:

| Mechanism | What does it control? | Fixes an early-evaluated condition? |
|---|---|---|
| **@AutoConfiguration(after = ...)** | Auto-configuration application and bean definition registration order | Yes, if the prerequisite lives in the ordered-before auto-configuration |
| **@DependsOn** | Bean instance initialization order | No |
| **@Order** | Element order in certain Spring-sorted collections/callbacks | No |
| **@Primary** | Preferred candidate when multiple beans share a type | No |
| **@Lazy** | Deferred bean instance initialization | No |

**@AutoConfiguration(after = ...)** does not require the client instance to be created before the facade instance. When the facade is instantiated, its constructor/method dependency parameter already informs Spring to create the client before injecting it.

**@DependsOn** matters only after bean definitions exist. It never causes a **@ConditionalOnBean** that already returned false to re-evaluate.

**@Order** is not an annotation for ordering auto-configuration classes. Use **@AutoConfigureOrder** when general ordering is needed; when an explicit prerequisite relationship exists, declare after or before directly.

## 9. Checking `@Bean` Method Type Metadata

Bean conditions rely on type information that Spring infers from processed bean definitions. Hence, the return type of a **@Bean** method matters greatly.

Good example when the condition checks **SearchClient.class**:

~~~java
@Bean
SearchClient searchClient() {
    return new DefaultSearchClient();
}
~~~

Example that easily loses type information:

~~~java
@Bean
Object searchClient() {
    return new DefaultSearchClient();
}
~~~

In the second example, the method signature advertises only **Object**. When the condition runs before instances are created, Spring cannot inspect the eventual runtime object to conclude the definition has type SearchClient.

If the condition checks the SearchClient interface, returning the interface type is enough. If the condition checks a concrete implementation, the return type should expose that concrete type when possible. Avoid returning Object, raw types, or overly broad types when bean conditions check specific types.

## 10. Distinguishing Similar-Looking Situations

### 10.1. The Prerequisite Bean Truly Does Not Exist

The dependency was not declared, a classpath condition did not match, or the prerequisite auto-configuration was excluded. The bean definition never appears at any point.

Check runtime dependencies, AutoConfiguration.imports, @ConditionalOnClass, property conditions, and exclusions.

### 10.2. The Prerequisite Bean Appears After the Condition

The prerequisite auto-configuration is present, yet applied after the dependent configuration. The condition runs first and misses the definition.

Declare after or afterName on the dependent auto-configuration.

### 10.3. The Prerequisite Bean Has Insufficient Type Metadata

The bean method declares an overly generic return type, preventing the condition from recognizing the desired type before instantiation.

Declare the concrete return type or the exact contract type checked by the condition.

### 10.4. The Prerequisite Bean Is Registered Dynamically Too Late

Some extensions register bean definitions dynamically using registry post-processors or dynamic mechanisms. If a definition appears only after the phase when conditions ran, bean conditions cannot anticipate it.

If possible, move the prerequisite into a clearly ordered configuration/auto-configuration. Otherwise, do not use @ConditionalOnBean to depend on dynamically registered beans produced after that phase; design an extension point suited to that registration lifecycle.

### 10.5. The Bean Resides in a Parent Context

An application can have a context hierarchy. A bean in the parent context is not the same as a bean definition in the child context's registry. Bean conditions expose the search attribute to control hierarchy search scope.

Determine which context owns the bean and choose the appropriate SearchStrategy. Do not assume a bean in an arbitrary context is visible to every condition.

### 10.6. A Bean Condition Gates Only One Method

When @ConditionalOnBean is placed on a @Bean method, only that bean method is affected. Other beans in the same configuration class can still be registered.

When placed on the class, it applies to the entire configuration class. Place the annotation according to the exact scope that needs gating.

## 11. Diagnosing with the Condition Evaluation Report

When a dependent bean does not appear, enable the condition report:

~~~bash
java -jar app.jar --debug
~~~

Or configure the logger:

~~~yaml
logging:
  level:
    org.springframework.boot.autoconfigure: DEBUG
~~~

Find the report entry for the relevant auto-configuration. A no-match result may state that the condition could not find the required bean type or bean name.

Read the report with these questions in mind:

1. Was the dependent auto-configuration discovered?
2. Was the prerequisite auto-configuration in the candidate list?
3. Which condition did not match?
4. Which bean type or name was the condition checking?
5. Was the prerequisite auto-configuration applied earlier or later?
6. Does the prerequisite bean method have a sufficiently specific return type?
7. Did any property, classpath condition, or exclusion block the prerequisite bean from registering?

The report usually states why a condition did not match, though it does not necessarily present the entire timeline chronologically. To reproduce, use ApplicationContextRunner and vary one input at a time.

Checking beans after startup verifies only the final state. To prove an ordering bug, inspect both the condition report and auto-configuration application order.

## 12. Fixes by Root Cause

| Cause | Fix |
|---|---|
| Dependent auto-configuration runs before prerequisite auto-configuration | Add @AutoConfiguration(after = BaseAutoConfiguration.class) |
| Prerequisite auto-configuration is an optional dependency | Use afterName and retain suitable bean/class conditions |
| Condition placed on a component-scanned configuration | Move bean condition to an auto-configuration class registered via imports |
| Return type of @Bean is too broad | Expose a specific return type so the condition can infer the type |
| Prerequisite bean missing due to classpath/property/exclusion | Fix the dependency or condition preventing prerequisite registration |
| Prerequisite bean lives in another context | Inspect context hierarchy and configure appropriate SearchStrategy |
| Bean registered dynamically after conditions | Move prerequisite to an orderable registration phase or revise extension design |
| Need to inspect bean instances or runtime state | Move logic to a bean/service/event after the context is created |

Do not add @DependsOn, @Lazy, or @Primary reflexively. They solve different problems and can hide symptoms without fixing condition evaluation timing.

## 13. Common Mistakes When Designing Dependent Auto-Configurations

- **Relying on imports file line order:** line order does not substitute for @AutoConfiguration(after = ...).
- **Omitting ordering between two dependent auto-configurations:** bean conditions may run before the prerequisite definition exists.
- **Placing @ConditionalOnBean on a configuration scanned like user config:** there is no guarantee all user bean definitions are already processed.
- **Assuming the bean instance must exist for the condition to match:** bean conditions work against already-processed bean definitions; instances do not need to be initialized yet.
- **Using @DependsOn to make a condition wait:** @DependsOn controls only instance creation.
- **Using @Order for auto-configurations:** use @AutoConfiguration ordering or @AutoConfigureOrder.
- **Returning Object from a bean method while checking a concrete type:** type metadata may be insufficient.
- **Putting prerequisite and dependent bean methods in the same class and relying on method order:** do not use method declaration order as a contract between bean conditions; split auto-configurations when registration ordering is required.
- **Assuming a false condition always fails startup:** usually it just skips the bean/configuration; startup fails only if another dependency strictly requires that skipped bean.
- **Using @ConditionalOnMissingBean to create defaults before user beans are processed:** place it on auto-configuration and keep proper ordering.
- **Ignoring context hierarchy:** beans in parent/child contexts may not be searched under the intended strategy.
- **Using conditions for runtime state:** conditions are not the place to call services, open connections, or read bean instances.
- **Not testing both with and without the prerequisite:** a single passing test does not prove the feature skips cleanly when the dependency is missing.
- **Inspecting only post-startup beans:** also inspect the condition report and ordering metadata to catch timing bugs.

## 14. Review Checklist for a Pair of Auto-Configurations

- [ ] Is the prerequisite auto-configuration listed in AutoConfiguration.imports?
- [ ] Is the dependent auto-configuration listed?
- [ ] Does the dependent class have the right after or afterName?
- [ ] Does the bean condition check the right bean type or name?
- [ ] Does the prerequisite @Bean method's return type provide enough type information?
- [ ] Is the bean condition on an auto-configuration class rather than an arbitrarily scanned config?
- [ ] Can user-defined beans override the default bean?
- [ ] When the prerequisite is absent, is the dependent feature skipped safely?
- [ ] Are there ApplicationContextRunner tests for both states?
- [ ] Is there a consumer test confirming auto-configuration imports discovery?
- [ ] Was the condition report inspected on test failures?
- [ ] Was misuse of @DependsOn, @Lazy, or @Order avoided?

## 15. Investigation Workflow in a Real Project

1. Confirm which dependent bean is missing and whether the prerequisite bean appears after context startup.
2. Read the condition report for why @ConditionalOnBean or @ConditionalOnMissingBean failed to match.
3. Identify which auto-configuration provides the prerequisite bean and which consumes it.
4. Check that both classes are listed in AutoConfiguration.imports.
5. Check ordering annotations on the dependent class.
6. Check whether the prerequisite's @Bean return type is specific enough.
7. Check whether the bean condition is class-level or method-level and whether the gating scope is right.
8. Build a minimal ApplicationContextRunner with the auto-configurations ordered like the application.
9. Write tests for prerequisite present, absent, and user-supplied.
10. Fix the ordering/metadata or dependency actually causing the fault.
11. Re-run tests, then run the consumer application with its real BOM and profiles.
12. Inspect the final condition report and bean graph before releasing.

## 16. Self-Check Questions

1. Why can a prerequisite bean exist after startup while @ConditionalOnBean still did not match? **Because conditions evaluate during bean definition registration and see only definitions processed up to that moment.**
2. Does a condition re-run automatically when the prerequisite bean is registered later? **No.**
3. Which attribute declares that a dependent auto-configuration must run after a prerequisite configuration? **@AutoConfiguration(after = BaseAutoConfiguration.class).**
4. When you want to avoid a compile dependency on an optional auto-configuration, what should you use? **afterName with the fully qualified class name.**
5. Which order does @AutoConfiguration(after = ...) control? **The order in which auto-configurations are applied and bean definitions are registered.**
6. Does it control bean instance creation order? **No.** The dependency graph and @DependsOn control instance creation.
7. Why cannot @DependsOn fix an early-evaluated condition? **The condition already decided whether to register the bean definition before instance creation begins.**
8. Why should @ConditionalOnBean be placed on auto-configurations? **Auto-configurations are processed after user-defined bean definitions and have explicit ordering relative to other auto-configurations.**
9. Why does a @Bean method's return type matter? **Bean conditions rely solely on type information available from the bean definition/method signature at evaluation time.**
10. When a condition does not match, does the application always fail startup? **No.** The bean may simply be skipped; startup fails if another bean requires that dependency.
11. Which tool shows condition match/no-match outcomes? **ConditionEvaluationReport, typically printed when running with --debug.**
12. Does @Order replace @AutoConfiguration(after=...)? **No.** The two annotations control different kinds of ordering.
13. When the prerequisite lives in a parent context, what should be checked? **The context hierarchy and the bean condition's SearchStrategy.**
14. Which test is suited for verifying auto-configuration ordering? **ApplicationContextRunner combined with AutoConfigurations.of(...), testing both with and without the prerequisite.**

## Official References (Spring Boot 3.3)

- [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): bean conditions, ordering, imports file, and recommendations for placing bean conditions on auto-configurations.
- [ConditionalOnBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html): matches only against bean definitions meeting the criteria that have already been processed.
- [ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): back-off condition when a matching bean already exists in the BeanFactory.
- [AutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): before, beforeName, after, and afterName attributes.
- [AutoConfigureAfter API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html): ordering between auto-configuration classes and distinguishing definition order from instance creation.
- [AutoConfigureOrder API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureOrder.html): general ordering among auto-configurations with no direct relationship.
- [ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): building isolated contexts to test auto-configurations and bean conditions.
