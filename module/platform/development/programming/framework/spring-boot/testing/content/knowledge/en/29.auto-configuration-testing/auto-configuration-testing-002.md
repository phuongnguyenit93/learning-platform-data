# AutoConfigurations.of and Configurations to Verify in Spring Boot Testing

## 1. Lesson goals

Spring Boot has an important capability: **auto-configuration**. When a library is on the classpath, the `Environment` contains matching properties, or the application has not defined a specific bean itself, Spring Boot can automatically register default beans. This makes applications easy to use, but also creates a class of bugs that are hard to spot if you only test with `@SpringBootTest` against a single configuration set:

- A default bean is created even though the user already provided a custom bean, leading to `NoUniqueBeanDefinitionException` or picking the wrong implementation.
- A bean that should be disabled when `demo.notify.enabled=false` is still created.
- Auto-configuration accidentally requires an optional library that is absent at runtime.
- A dependent bean is created before its dependency has been registered.
- Configuration works when running a large application but fails in another starter/library due to different bean ordering.
- A test boots `ApplicationContext` and only asserts there is no exception, without verifying actual condition outcomes.
- A tester uses `withUserConfiguration` to declare an auto-config and loses accurate ordering/conditional processing.
- The auto-config registration file in `META-INF/spring/...AutoConfiguration.imports` is missing, causing the real application not to import the class even though unit tests using explicit `AutoConfigurations.of(...)` stay green.

To test each intentional combination of inputs, Spring Boot provides **`ApplicationContextRunner`**; and **`AutoConfigurations.of(...)`** builds the group of auto-configuration classes passed to the runner via `withConfiguration(...)`.

This lesson is part of the **Auto-Configuration Testing** group in the **Spring Boot – testing** module, focusing on **AutoConfigurations.of and configurations to verify**. The focus is not on creating many `@SpringBootTest` suites, but on **verifying conditions and the bean graph using a small, reproducible test matrix**.

After this lesson, you will:

1. Understand when to use `AutoConfigurations.of` and when to use `withUserConfiguration`.
2. Create an `ApplicationContextRunner` that loads only the auto-configurations under test, without launching a full SpringApplication.
3. Verify `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnBean`, `@ConditionalOnProperty`, `matchIfMissing`, and `havingValue`.
4. Place multiple auto-configurations in `AutoConfigurations.of(...)` while preserving official ordering semantics.
5. Verify default beans, custom bean back-off, property enable/disable, dependency gating, user overrides, and missing classpath.
6. Use `FilteredClassLoader` to simulate a missing dependency without altering the real project classpath.
7. Check `ApplicationContext` startup success/failure without equating that to the feature working properly.
8. Use `ConditionEvaluationReportLoggingListener` to diagnose why a condition matched or did not match.
9. Distinguish **runner tests directly importing classes** from **real startup reading AutoConfiguration.imports**.
10. Write a `@SpringBootTest` smoke test to protect application integration.
11. Know when to use `WebApplicationContextRunner`/`ReactiveWebApplicationContextRunner`, and not use the plain runner to simulate a servlet context.
12. Run a complete demonstration project using **Java 17, Spring Boot 3.3.5, Gradle, JUnit Jupiter, AssertJ**, without needing Docker, a database, or an HTTP server.

**Core message:** With auto-configuration, what you want to verify is not just **"Does the context start?"** but **"Do the right beans appear/disappear and get configured properly in every circumstance?"**.

## 2. How does auto-configuration differ from manual configuration?

Spring Framework supports bean declarations via `@Configuration` and `@Bean`:

~~~java
@Configuration(proxyBeanMethods = false)
class UserNotificationConfiguration {

    @Bean
    NotificationClient myClient() {
        return message -> "USER::" + message;
    }
}
~~~

If the application imports this configuration, the bean is registered because the developer **explicitly declared** it.

Auto-configuration in Spring Boot typically uses `@AutoConfiguration` and conditions:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.notify.optional.OptionalTransport")
@ConditionalOnProperty(
    prefix = "demo.notify",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true)
class NotifyAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationClient.class)
    NotificationClient notificationClient() {
        return message -> "READY::" + message;
    }
}
~~~

In the example, the default bean should appear only when **the relevant conditions** are satisfied:

- The optional marker class is on the classpath.
- The feature is enabled; when the property is absent, `matchIfMissing=true` allows enabling by default.
- No `NotificationClient` has been declared by the user or another config within the search scope.

This is the error-prone part: flipping a single annotation, getting a property name wrong, or changing bean registration order alters the behavior.

### How is the decision order perceived?

One way to view it:

~~~text
ApplicationContextRunner
  |
  +-- user-defined configurations / beans
  |       |
  |       v
  |    Does user NotificationClient exist?
  |
  +-- auto-configuration candidates
          |
          +-- @ConditionalOnClass
          +-- @ConditionalOnProperty
          +-- @ConditionalOnMissingBean
          |
          +-- default NotificationClient if appropriate
          |
          +-- @ConditionalOnBean(NotificationClient)
                   |
                   +-- NotificationObservation if client exists
~~~

In Spring Boot, bean conditions check bean definitions already processed **at evaluation time**; therefore `@ConditionalOnMissingBean` and `@ConditionalOnBean` should be placed on **auto-configurations** rather than treated as global policies independent of registration order. `AutoConfigurations.of(...)` together with `@AutoConfiguration(after=...)` ensures the selected auto-configurations are verified in the proper order.

## 3. What exactly is `AutoConfigurations.of(...)`?

Import:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurations;
~~~

Key API:

~~~java
AutoConfigurations.of(
        NotifyAutoConfiguration.class,
        NotificationObservationAutoConfiguration.class)
~~~

It creates an object holding **auto-configuration** classes for an `ApplicationContextRunner`. The set of classes is sorted according to auto-configuration ordering semantics, including metadata such as `@AutoConfiguration(after=...)` or `@AutoConfigureAfter`.

Standard pattern:

~~~java
private final ApplicationContextRunner runner =
    new ApplicationContextRunner()
        .withConfiguration(
            AutoConfigurations.of(
                NotifyAutoConfiguration.class,
                NotificationObservationAutoConfiguration.class));
~~~

Then:

~~~java
runner.run(context -> {
    assertThat(context)
        .hasSingleBean(NotificationClient.class);
});
~~~

These are **snippets using classes declared by the sample project** below; they are not standalone code.

### Is `AutoConfigurations.of` a command to boot Spring Boot?

**No.** It does not create an ApplicationContext or start an application by itself. `AutoConfigurations.of` only supplies a group of configuration classes; `ApplicationContextRunner.run(...)` is what builds, refreshes, and closes an isolated test context.

### Does it automatically read the AutoConfiguration.imports file?

**Not in this explicit runner test.** When calling `AutoConfigurations.of(NotifyAutoConfiguration.class)`, you directly specify the candidate. If `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` does not exist, the runner can still test that class successfully; conversely, a full Boot startup may **fail to see** the starter's auto-configuration. Hence the sample project has **two layers of tests**:

- **Runner tests:** protect condition/bean wiring inside the auto-config class.
- **Full Boot smoke test:** protects the imports file and integration when the application actually starts.

### Does it automatically scan the entire classpath to auto-configure like an app?

**No.** The runner is designed to test the classes you specify, keeping scope small. It does not replace all of `SpringApplication.run`, does not run the lifecycle of every `EnvironmentPostProcessor` by default, and does not automatically load all app/auto-configurations. When a test depends on side effects from SpringApplication bootstrap, you must simulate them explicitly using `withInitializer`, properties, or add a full-startup test.

### Does the declaration order in `of(...)` guarantee bean creation order?

You must distinguish:

1. **Auto-config ordering:** `AutoConfigurations.of` sorts candidates according to auto-config semantics; it does not necessarily apply them in the order of arguments.
2. **Bean definition registration:** influenced by configuration ordering and Spring processing.
3. **Bean instantiation:** depends on the dependency graph, injection, lazy settings, and `@DependsOn`, which is **not identical** to definition order.

Do not swap two classes' positions in `AutoConfigurations.of(A.class, B.class)` as a fix for a broken bean condition. Declare `@AutoConfiguration(after=OtherAutoConfiguration.class)` when there is a real ordering dependency.

## 4. What can `ApplicationContextRunner` test?

Import:

~~~java
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
~~~

A standard runner operates in a cycle:

~~~text
new ApplicationContextRunner()
  -> withConfiguration(AutoConfigurations.of(...))
  -> withUserConfiguration(UserConfig.class) [per test]
  -> withPropertyValues("demo.notify.enabled=false") [per test]
  -> withBean(...) [per test]
  -> withClassLoader(new FilteredClassLoader(...)) [per test]
  -> run(context -> { assert bean graph / errors / properties; })
  -> context closes after callback
~~~

Each `run` creates a new context configured according to the current runner. Builder methods like `withPropertyValues` return **a newly configured runner** so the base runner can be reused repeatedly. This keeps test methods independent without calling `SpringApplication.run()` every time.

### Useful APIs

| API | Role | Use case |
| --- | --- | --- |
| `withConfiguration(AutoConfigurations.of(...))` | Loads auto-config candidates with Boot semantics | Lesson focus |
| `withUserConfiguration(UserConfig.class)` | Supplies user-declared configuration | Test `@ConditionalOnMissingBean` back-off |
| `withBean(Type.class, supplier)` | Directly registers a test bean | Quick override check without a config class |
| `withPropertyValues("key=value")` | Modifies `Environment` | Test feature flags/port/prefix |
| `withClassLoader(new FilteredClassLoader(...))` | Simulates a class missing from classpath | Test `@ConditionalOnClass` |
| `withInitializer(...)` | Hook before refresh | Report, custom setup |
| `withParent(...)` | Creates a context hierarchy | Bean search scopes, parent dependencies |
| `withAllowBeanDefinitionOverriding(...)` | Sets bean-definition override policy for a test | Supports intentional cases; not for hiding duplicates |
| `run(context -> ...)` | Creates, inspects, closes context | Each test case |
| `assertThat(context).hasSingleBean(...)` | Asserts bean by type | Default/back-off |
| `assertThat(context).doesNotHaveBean(...)` | Asserts bean absence | Condition false |
| `assertThat(context).hasFailed()` | Asserts startup failure | Invalid config |
| `context.getStartupFailure()` | Retrieves Throwable when context fails | Diagnose root cause |

For auto-configurations constrained by a servlet/reactive web environment, use **`WebApplicationContextRunner`** or **`ReactiveWebApplicationContextRunner`**; `ApplicationContextRunner` creates an annotation-based non-web application context by default.

### Is the runner a JUnit annotation?

No. It is a regular Java helper object used inside normal JUnit test methods. You do not need `@SpringBootTest` or `@ExtendWith(SpringExtension.class)` for tests using only `ApplicationContextRunner`, because the runner builds the context itself within the callback. This keeps test overhead low.

### Can the runner execute inside a native image?

According to Spring Boot 3.3 documentation, **`ApplicationContextRunner` does not work when running tests inside a native image**. Do not use runner results to claim a native build has been verified; native/AOT cases need a separate compatible test/build flow.

## 5. Conditions to verify: by category

### 5.1. `@ConditionalOnProperty`

Example:

~~~java
@ConditionalOnProperty(
    prefix = "demo.notify",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true)
~~~

States to test:

| `demo.notify.enabled` | `havingValue="true"` | `matchIfMissing=true` | Expected |
| --- | --- | --- | --- |
| Absent | — | Applied | Enabled |
| `true` | Matches | — | Enabled |
| `false` | Does not match | — | Disabled |
| `yes` | Does not match `true` under this string condition | — | Disabled |
| `unexpected` | Does not match | — | Disabled |
| Empty value | Does not match | — | Disabled |

When **`havingValue` is omitted**, the default semantics of `@ConditionalOnProperty` is that the property **exists and is not the string `false`**; that can be surprising if a learner assumes a boolean parser accepts only true/false. When you want a strict feature flag, use `havingValue="true"` and include negative cases.

**`matchIfMissing` is not a bean's default value.** It only determines **whether the condition matches when the key is absent**. Once the bean is created, remaining properties still need proper binding/resolution.

### 5.2. `@ConditionalOnClass`

~~~java
@ConditionalOnClass(
    name = "com.example.notify.optional.OptionalTransport")
~~~

Matches only if the corresponding class is on the classpath visible to the context's classloader. This is useful for auto-configuration of optional libraries like Redis, Kafka, HTTP clients, or DB drivers. **Testing on a laptop that already has all dependencies** may miss the missing-dependency case. Use `FilteredClassLoader` to build a negative case.

### 5.3. `@ConditionalOnMissingBean`

~~~java
@Bean
@ConditionalOnMissingBean(NotificationClient.class)
NotificationClient notificationClient() {
    return message -> "READY::" + message;
}
~~~

Spring creates the **default bean** if no matching target bean is found in the search at processing time. When the user defines their own `NotificationClient`, auto-config must **back off** and not create an extra default. Important assertions:

- `hasSingleBean(NotificationClient.class)`.
- The actual client retrieved comes from user-config, not from default.
- Downstream beans can use the exact client supplied by the user.

Tests that only check "context starts" can miss duplicate beans if no bean requires injection by type at startup.

### 5.4. `@ConditionalOnBean`

~~~java
@Bean
@ConditionalOnBean(NotificationClient.class)
NotificationObservation notificationObservation(
        NotificationClient client) {
    return new NotificationObservation(client);
}
~~~

If a client exists — default or user-defined — the observation bean is created; if not, observation is absent. To prevent the bean condition from missing the dependency due to registration order, the observation config uses `@AutoConfiguration(after=NotifyAutoConfiguration.class)`.

### 5.5. `@ConditionalOnWebApplication`

Used when you only want to configure a servlet or reactive web environment. Do not expect a non-web `ApplicationContextRunner` to match a servlet condition. When needed, use the web runner and simulate the appropriate classpath/environment. You should not merely "import WebMvcAutoConfiguration" into a plain runner and conclude a servlet `WebApplicationContext` was created.

### 5.6. `@ConditionalOnResource`, `@ConditionalOnMissingClass`, `@ConditionalOnExpression`

Other condition groups:

- `@ConditionalOnResource(resources="classpath:...")`: requires the resource to exist; test both present/absent resource.
- `@ConditionalOnMissingClass("...")`: activates when a class is missing, suitable for fallback implementations.
- `@ConditionalOnExpression`: uses SpEL; be cautious because expressions referencing beans can trigger very early bean initialization, affecting post-processing.
- `@ConditionalOnSingleCandidate`: requires a single clear candidate by type/primary policy; does not replace all `@Qualifier` needs.
- `@ConditionalOnJava`: depends on Java version.
- `@ConditionalOnCloudPlatform`: depends on platform signals; avoid excessive framework-specific assumptions.

You do not need to add all of them to one lab. The exercises after the runnable section will guide building corresponding small matrices.

## 6. Test matrix before writing source code

An example auto-configuration named `NotifyAutoConfiguration` provides a default `NotificationClient`. A second auto-config `NotificationObservationAutoConfiguration` creates an observation bean if `NotificationClient` exists and can be turned off separately via a property.

| # | Context | `NotificationClient` | `NotificationObservation` | Value worth checking |
| ---: | --- | --- | --- | --- |
| 1 | Marker present; properties absent | Default 1 bean | Present 1 bean | `READY::hello` |
| 2 | Custom prefix | Default | Present | Actual prefix changes |
| 3 | `enabled=true` | Default | Present | Explicit true match |
| 4 | `enabled=false` | Absent | Absent | Feature off |
| 5 | `enabled=yes` | Absent | Absent | `havingValue=true` blocks |
| 6 | `meter-enabled=false` | Default | Absent | Subfeature off |
| 7 | Optional marker filtered from classpath | Absent | Absent | Classpath guard |
| 8 | User-defined `NotificationClient` | User bean only | Present | Default back-off |
| 9 | `withBean(NotificationClient.class,...)` | Injected test bean only | Present | Direct override |
| 10 | Disabled default + user client | User bean still present | Present | Disabled auto-config does not delete user bean |
| 11 | Observation auto-config only, no client | Absent | Absent | `@ConditionalOnBean` no-match |
| 12 | Notify auto-config only | Default | Absent | Explicit runner scope |
| 13 | Broken user config | Context fails | No valid graph | Startup exception |
| 14 | Full Boot startup + imports file | Default | Present | Auto-discovery registration |

This is a **test specification**, helping each test verify a single cause. If you create one test that disables the feature, filters the classpath, and adds a custom bean all at once, the "no bean" result cannot tell which condition worked.

## 7. Java 17 + Spring Boot 3.3.5 + Gradle project

The sample project creates two auto-configurations with explicit ordering, requiring no networking. It has an application root **outside the auto-configuration package** to ensure classes are loaded via **AutoConfiguration.imports** rather than accidentally component-scanned.

### 7.1. Directory tree

~~~text
auto-config-testing-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/
    │   ├── java/
    │   │   ├── com/example/app/
    │   │   │   └── NotifyDemoApplication.java
    │   │   └── com/example/notify/
    │   │       ├── api/
    │   │       │   ├── NotificationClient.java
    │   │       │   └── NotificationObservation.java
    │   │       ├── optional/
    │   │       │   └── OptionalTransport.java
    │   │       └── autoconfigure/
    │   │           ├── NotifyAutoConfiguration.java
    │   │           └── NotificationObservationAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/example/notify/
        ├── NotificationAutoConfigurationTest.java
        └── BootAutoConfigurationSmokeTest.java
~~~

**Intentional package placement:** `com.example.app` does not scan `com.example.notify` by default. If you delete `AutoConfiguration.imports`, the full Boot smoke test must fail, whereas explicitly specified runner tests still run. This is a check against **false confidence**.

Gradle Wrapper files are scripts/JAR generated by Gradle, not content fully representable in Markdown. Once a compatible Wrapper is present, the Java/resource files below are sufficient for the `test` demo.

### 7.2. `settings.gradle`

~~~groovy
rootProject.name = 'auto-config-testing-lab'
~~~

### 7.3. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'

    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter` provides the Spring Boot/auto-configuration foundation without adding a web server/JPA/DB to the demo. `spring-boot-starter-test` supplies `ApplicationContextRunner`, JUnit Jupiter, and AssertJ. `spring-boot-autoconfigure-processor` can generate metadata supporting early filtering of auto-configurations; **it does not replace the `AutoConfiguration.imports` file** and must not be used as proof that an auto-config is registered.

`useJUnitPlatform()` lets Gradle run JUnit Jupiter tests.

### 7.4. `NotifyDemoApplication.java`

**`src/main/java/com/example/app/NotifyDemoApplication.java`**

~~~java
package com.example.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NotifyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(NotifyDemoApplication.class, args);
    }
}
~~~

Thanks to `@SpringBootApplication`, Spring Boot reads auto-configuration imports on dependencies/resource paths at startup. Do not add `@ComponentScan("com.example.notify")` just so auto-config classes are found; doing so can mask a missing registration file bug.

### 7.5. `NotificationClient.java`

**`src/main/java/com/example/notify/api/NotificationClient.java`**

~~~java
package com.example.notify.api;

@FunctionalInterface
public interface NotificationClient {

    String format(String message);
}
~~~

This is a small interface to test bean conditions; it does not actually send email/SMS and has no network side effects. The name `NotificationClient` was chosen for easy association with a library/starter auto-config.

### 7.6. `NotificationObservation.java`

**`src/main/java/com/example/notify/api/NotificationObservation.java`**

~~~java
package com.example.notify.api;

public record NotificationObservation(
        NotificationClient client) {

    public String sample() {
        return client.format("probe");
    }
}
~~~

Java 17 supports `record`. The `NotificationObservation` bean directly depends on `NotificationClient`, helping tests tell whether it uses the **default client** or the **user-provided client**.

### 7.7. `OptionalTransport.java`

**`src/main/java/com/example/notify/optional/OptionalTransport.java`**

~~~java
package com.example.notify.optional;

public final class OptionalTransport {

    private OptionalTransport() {
    }
}
~~~

This class is a **marker simulating an optional dependency**. In a real project, the marker could be `org.postgresql.Driver`, an SDK client class, or a class provided by a third-party library. This lesson uses a marker in the same project so the example is self-contained and can use `FilteredClassLoader` to simulate an absent class.

**Why not use `Class.forName` inside a `@Bean` factory?** If auto-config does not guard the class properly, a missing library can cause the context to fail before the condition is evaluated. Placing `@ConditionalOnClass` at the class level and separating type-dependent nested configs when needed is a safer pattern.

## 8. First auto-configuration: create default client only when conditions hold

**`src/main/java/com/example/notify/autoconfigure/NotifyAutoConfiguration.java`**

~~~java
package com.example.notify.autoconfigure;

import com.example.notify.api.NotificationClient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(
    name = "com.example.notify.optional.OptionalTransport")
@ConditionalOnProperty(
    prefix = "demo.notify",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true)
public class NotifyAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationClient.class)
    NotificationClient notificationClient(
            @Value("${demo.notify.prefix:READY}") String prefix) {

        return message -> prefix + "::" + message;
    }
}
~~~

### Explaining design choices

- `@AutoConfiguration`: identifies the class as an auto-configuration candidate.
- `@ConditionalOnClass(name=...)`: uses a String full name, avoiding forcing the JVM to load the optional class via method signatures. When the marker is missing, **the entire auto-config is excluded**.
- `@ConditionalOnProperty(...enabled...)`: when the property is absent, it still enables by default; explicit `false` blocks it; `havingValue="true"` prevents arbitrary strings like `yes` from counting as enabled.
- `@Bean @ConditionalOnMissingBean(NotificationClient.class)`: if the application already declared a `NotificationClient`, auto-config backs off.
- `@Value("${demo.notify.prefix:READY}")`: default prefix is `READY` if the property is absent, customizable per runner.
- The bean returns the interface type `NotificationClient`, giving Spring sufficient information to check candidates by type.
- The bean performs no I/O on initialization; runner tests focus on **bean graph/condition semantics**, independent of the network.

### Pitfall of `@ConditionalOnClass` on a `@Bean` method

Putting a bean method whose return type comes from an optional library **when that class is actually absent** can force the JVM to resolve the method signature before the condition is applied. For optional classes, the proper pattern is:

~~~java
@AutoConfiguration
class ExternalTransportAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.ExternalClient")
    static class ExternalClientConfiguration {

        // Bean methods referencing ExternalClient
        // are defined only in the nested config
        // when the corresponding class is available.
    }
}
~~~

This is a **design snippet**, not standalone runnable Java because there is no actual external client bean/method yet. Its goal is to avoid classloading an absent type before the condition can guard it.

### `matchIfMissing` does not mean default prefix

Two different defaults:

- No `demo.notify.enabled` -> auto-config is still enabled because `matchIfMissing=true`.
- No `demo.notify.prefix` -> the bean factory parameter receives `READY` via the `@Value` default.

A test should verify both to catch accidental edits to the condition or property resolution.

## 9. Second auto-configuration: create observer only when client exists

**`src/main/java/com/example/notify/autoconfigure/NotificationObservationAutoConfiguration.java`**

~~~java
package com.example.notify.autoconfigure;

import com.example.notify.api.NotificationClient;
import com.example.notify.api.NotificationObservation;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = NotifyAutoConfiguration.class)
@ConditionalOnProperty(
    prefix = "demo.notify",
    name = "meter-enabled",
    havingValue = "true",
    matchIfMissing = true)
public class NotificationObservationAutoConfiguration {

    @Bean
    @ConditionalOnBean(NotificationClient.class)
    NotificationObservation notificationObservation(
            NotificationClient client) {

        return new NotificationObservation(client);
    }
}
~~~

### Why use `after`?

`NotificationObservation` depends on the `NotificationClient` bean. If the observation auto-config is processed **before** the notification auto-config, `@ConditionalOnBean(NotificationClient.class)` may fail to match because the bean definition has not appeared yet. `@AutoConfiguration(after=NotifyAutoConfiguration.class)` clearly expresses dependency ordering between **definitions**.

Note:

- `after` does not mean the `NotificationClient` object is always completely instantiated before any auto-config class is parsed; bean instantiation and definition ordering are two different concepts.
- `@ConditionalOnBean` on the bean method means **only the observer bean** is guarded; the config class itself can still be registered even without a client.
- `demo.notify.meter-enabled=false` turns off the observer **without disabling `NotificationClient`**.
- `demo.notify.enabled=false` turns off the default client but **has no authority to delete a user bean**; if the user still provides `NotificationClient` and `meter-enabled=true`, the observation bean can still appear. This is semantics to test, not a bug.

### Do not use bean definition overriding to "force custom to win"

A flawed design might define both a default bean and a custom bean with the same name and then turn on:

~~~properties
spring.main.allow-bean-definition-overriding=true
~~~

That can hide configuration conflicts rather than resolving them. `@ConditionalOnMissingBean` is used so auto-config **backs off by type** when a user bean is present, fulfilling a starter's purpose. Tests must prove **only one bean by type** and that the instance is the user bean, rather than just checking a bean name.

## 10. Registering auto-configuration with Spring Boot

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

~~~text
com.example.notify.autoconfigure.NotifyAutoConfiguration
com.example.notify.autoconfigure.NotificationObservationAutoConfiguration
~~~

Each line is a fully qualified class name. Spring Boot 3.3 uses the resource **`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`** to discover auto-configurations in libraries. This is not the `spring.factories` auto-configuration registration style of older Boot versions.

### Why not let component scan find the classes?

Auto-configurations belonging to a library should have their own package, not scanned by the application as ordinary components. When the library is added to the classpath, Boot picks candidates from the imports file and evaluates conditions and auto-config ordering. If an auto-config is accidentally scanned as an ordinary `@Configuration`, bean/ordering conditions may be processed wrongly compared to intended auto-config semantics.

In the lab, `NotifyDemoApplication` belongs to `com.example.app`, while `NotifyAutoConfiguration` belongs to `com.example.notify.autoconfigure`, so it **does not lie under the app's component scan package**. Good integration proof is a smoke test that starts Boot and sees the client/observation beans **without manually `@Import`-ing the two configs**.

### How does testing the imports file differ from the runner?

`ApplicationContextRunner.withConfiguration(AutoConfigurations.of(...))` passes the classes **directly**, regardless of the imports file. Only `@SpringBootTest`/`SpringApplication.run` with Boot auto-configuration discovery covers the resource-based registration path. Thus:

- Runner tests pass + Boot smoke test passes: both condition behavior and auto-discovery work.
- Runner tests pass + Boot smoke test fails: suspect missing imports, wrong class names, configuration scan/order, resource packaging, or app context differences.
- Runner tests fail: condition/configuration wiring does not meet the contract yet; no need to blame packaging yet.

## 11. JUnit runner tests: the full test matrix

**`src/test/java/com/example/notify/NotificationAutoConfigurationTest.java`**

~~~java
package com.example.notify;

import com.example.notify.api.NotificationClient;
import com.example.notify.api.NotificationObservation;
import com.example.notify.autoconfigure.NotifyAutoConfiguration;
import com.example.notify.autoconfigure.NotificationObservationAutoConfiguration;
import com.example.notify.optional.OptionalTransport;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class NotificationAutoConfigurationTest {

    // Intentionally pass observer before client so the test confirms
    // @AutoConfiguration(after=...) determines ordering,
    // rather than relying on parameter order.
    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                NotificationObservationAutoConfiguration.class,
                NotifyAutoConfiguration.class));

    @Test
    void defaultAutoConfigurationCreatesBothBeans() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(
                    NotificationClient.class);
            assertThat(context).hasSingleBean(
                    NotificationObservation.class);

            NotificationClient client =
                    context.getBean(NotificationClient.class);

            assertThat(client.format("hello"))
                    .isEqualTo("READY::hello");
            assertThat(context
                    .getBean(NotificationObservation.class)
                    .sample())
                    .isEqualTo("READY::probe");
        });
    }

    @Test
    void customPropertyIsInjectedIntoDefaultClient() {
        runner
            .withPropertyValues("demo.notify.prefix=TEST")
            .run(context -> {
                assertThat(context).hasSingleBean(
                        NotificationClient.class);
                assertThat(context
                        .getBean(NotificationClient.class)
                        .format("message"))
                        .isEqualTo("TEST::message");
                assertThat(context
                        .getBean(NotificationObservation.class)
                        .sample())
                        .isEqualTo("TEST::probe");
            });
    }

    @Test
    void explicitTrueEnablesDefaultClient() {
        runner
            .withPropertyValues("demo.notify.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(
                        NotificationClient.class);
                assertThat(context).hasSingleBean(
                        NotificationObservation.class);
            });
    }

    @Test
    void explicitFalseDisablesDefaultClient() {
        runner
            .withPropertyValues("demo.notify.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(
                        NotificationClient.class);
                assertThat(context).doesNotHaveBean(
                        NotificationObservation.class);
            });
    }

    @Test
    void unexpectedFlagValueDoesNotCountAsTrue() {
        runner
            .withPropertyValues("demo.notify.enabled=yes")
            .run(context -> {
                assertThat(context).doesNotHaveBean(
                        NotificationClient.class);
                assertThat(context).doesNotHaveBean(
                        NotificationObservation.class);
            });
    }

    @Test
    void disablingMeterDoesNotDisableClient() {
        runner
            .withPropertyValues(
                "demo.notify.meter-enabled=false")
            .run(context -> {
                assertThat(context).hasSingleBean(
                        NotificationClient.class);
                assertThat(context).doesNotHaveBean(
                        NotificationObservation.class);
                assertThat(context
                        .getBean(NotificationClient.class)
                        .format("x"))
                        .isEqualTo("READY::x");
            });
    }

    @Test
    void missingOptionalClassDisablesAutoConfiguration() {
        runner
            .withClassLoader(
                new FilteredClassLoader(OptionalTransport.class))
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(
                        NotificationClient.class);
                assertThat(context).doesNotHaveBean(
                        NotificationObservation.class);
            });
    }

    @Test
    void userDefinedClientMakesDefaultBackOff() {
        runner
            .withUserConfiguration(CustomUserConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(
                        NotificationClient.class);
                assertThat(context).hasSingleBean(
                        NotificationObservation.class);

                NotificationClient custom =
                    context.getBean(
                        "customNotificationClient",
                        NotificationClient.class);

                assertThat(context
                        .getBean(NotificationClient.class))
                        .isSameAs(custom);
                assertThat(custom.format("hello"))
                        .isEqualTo("USER::hello");
                assertThat(context
                        .getBean(NotificationObservation.class)
                        .sample())
                        .isEqualTo("USER::probe");
            });
    }

    @Test
    void withBeanRegistersOverrideWithoutExtraConfig() {
        runner
            .withBean(
                NotificationClient.class,
                () -> message -> "REGISTERED::" + message)
            .run(context -> {
                assertThat(context).hasSingleBean(
                        NotificationClient.class);
                assertThat(context
                        .getBean(NotificationClient.class)
                        .format("x"))
                        .isEqualTo("REGISTERED::x");
                assertThat(context
                        .getBean(NotificationObservation.class)
                        .sample())
                        .isEqualTo("REGISTERED::probe");
            });
    }

    @Test
    void disabledDefaultDoesNotDeleteUserClient() {
        runner
            .withPropertyValues("demo.notify.enabled=false")
            .withUserConfiguration(CustomUserConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(
                        NotificationClient.class);
                assertThat(context).hasSingleBean(
                        NotificationObservation.class);

                assertThat(context
                        .getBean(NotificationObservation.class)
                        .sample())
                        .isEqualTo("USER::probe");
            });
    }

    @Test
    void observerAloneRequiresAnExistingClient() {
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                NotificationObservationAutoConfiguration.class))
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(
                        NotificationClient.class);
                assertThat(context).doesNotHaveBean(
                        NotificationObservation.class);
            });
    }

    @Test
    void baseClientAloneDoesNotCreateObserver() {
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                NotifyAutoConfiguration.class))
            .run(context -> {
                assertThat(context).hasSingleBean(
                        NotificationClient.class);
                assertThat(context).doesNotHaveBean(
                        NotificationObservation.class);
            });
    }

    @Test
    void startupFailureCanBeAssertedAndDiagnosed() {
        runner
            .withUserConfiguration(BrokenUserConfiguration.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasRootCauseInstanceOf(
                            IllegalStateException.class);
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomUserConfiguration {

        @Bean
        NotificationClient customNotificationClient() {
            return message -> "USER::" + message;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class BrokenUserConfiguration {

        @Bean
        Integer deliberatelyBroken() {
            throw new IllegalStateException(
                    "simulated invalid user configuration");
        }
    }
}
~~~

### 11.1. Why intentionally reverse the order in `AutoConfigurations.of`?

The test runner passes `NotificationObservationAutoConfiguration` before `NotifyAutoConfiguration`, even though observation depends on client. When using `AutoConfigurations.of(...)`, Spring Boot sorts candidates according to auto-config ordering, where the `after=NotifyAutoConfiguration.class` annotation takes effect. What must be protected is that the observer appears when the client appears; do not infer bean instantiation from argument order in Java.

If you remove `@AutoConfiguration(after=...)` on an experimental branch, run the default test and observe: the `@ConditionalOnBean` condition may see a missing client and the observer may not appear. That is a **detectable regression**, not a reason to rely on "Spring happening to process them in the right order today".

### 11.2. Why does each method run one context?

The runner is a builder with shared `withConfiguration(...)`. Each `run(context -> ...)` builds an independent context and closes it after the callback, preventing the previous test's enabled property or the next test's injected bean from bleeding across. Assertions use `context` within the callback scope. **Do not keep a bean reference and use it after the callback finishes** if the bean depends on closed resources.

### 11.3. Testing default and explicit true

Two distinct cases:

- `defaultAutoConfigurationCreatesBothBeans`: does not pass `demo.notify.enabled` and still expects the bean -> protects `matchIfMissing=true`.
- `explicitTrueEnablesDefaultClient`: property is present, value `true`, and condition matches -> protects explicit opt-in.

If a developer accidentally changes `matchIfMissing=false`, the default test must fail while the explicit true test still passes. If someone accidentally changes `havingValue="false"`, the explicit false/true tests will catch it.

### 11.4. Testing negative properties

`demo.notify.enabled=false` prevents creating the default client. Because no other client exists, the observation bean should also be absent. The test checks both the class-level condition and the downstream bean condition.

For `demo.notify.enabled=yes`, `havingValue="true"` forces the condition not to match. If you omit `havingValue`, `@ConditionalOnProperty`'s default semantics may match `yes` because that string differs from `false`, causing the test to fail. This is a useful negative case.

### 11.5. Subfeature property

`demo.notify.meter-enabled=false` prevents only the observer, without removing the client. If a class-level property was mistakenly placed on `NotifyAutoConfiguration` instead of the observation config, the test will catch the client being disabled unintentionally.

### 11.6. Simulating missing classpath properly

`FilteredClassLoader(OptionalTransport.class)` makes the listed class **no longer visible to the runner classloader**. Since `@ConditionalOnClass(name=...)` guards `NotifyAutoConfiguration`, the condition must fail and no default client is created. The observer is also absent because there is no `NotificationClient`.

Do not delete JARs or edit Gradle just to test a missing-class case; `FilteredClassLoader` provides fast, reproducible testing. For a real library's optional dependency, pick **the exact class governing the condition**, rather than filtering entire Spring packages and making the test fail because framework classes are missing.

### 11.7. User override: key starter logic

`CustomUserConfiguration` supplies `NotificationClient customNotificationClient()`. When the runner calls `withUserConfiguration(...)`, the user bean is registered before auto-config, so `@ConditionalOnMissingBean(NotificationClient.class)` must back off.

Assertions must confirm **only one bean** and **the exact user bean instance**:

~~~java
assertThat(context).hasSingleBean(NotificationClient.class);
assertThat(context.getBean(NotificationClient.class))
        .isSameAs(context.getBean(
                "customNotificationClient",
                NotificationClient.class));
~~~

If you only assert `context.containsBean("customNotificationClient")`, a second default bean could still exist without the test noticing. When the application autowires by type, duplicates can cause ambiguous injection; thus `hasSingleBean` is essential.

### 11.8. `withBean` vs `withUserConfiguration`

`withBean(NotificationClient.class, supplier)` is a quick way to test a user-supplied bean without writing a `@Configuration` class. It is great for verifying type-based bean back-off.

`withUserConfiguration(CustomUserConfiguration.class)` is suitable when testing:

- `@Bean` method return types and qualifiers.
- Configuration class/conditional metadata.
- A group of related custom beans.
- User configuration ordering combined with multiple auto-configurations.
- Autowiring logic expressed like an application.

Do not use `withBean` to conclude that a complex production `@Configuration` will automatically be scanned/registered; the runner cannot test discovery outside what was explicitly supplied.

### 11.9. When the user bean remains even if the default feature is disabled

`demo.notify.enabled=false` only disables `NotifyAutoConfiguration`. It does not delete `CustomUserConfiguration`. If the user still registers a client, `NotificationObservationAutoConfiguration` sees that bean and can create the observer under its own property.

This is not a "broken feature flag" if the starter contract is designed that way. If `enabled=false` is expected to block **the observer as well**, an explicit overall condition on the observation auto-config or a composite condition is needed. Write the test matrix according to the actual product specification rather than projecting an ambiguous meaning onto a single key.

### 11.10. What is the value of testing startup failure?

`BrokenUserConfiguration` intentionally throws an exception when Spring creates the bean. The runner still invokes the callback so the test can assert `hasFailed()` and `getStartupFailure()`. This guards error-handling behavior on misconfiguration, not claiming that the application's auto-config can automatically recover.

**Do not catch exceptions in a test to pretend the context started successfully.** Assert failure only when a case **intentionally tests fail-fast**. In normal cases, assert `hasNotFailed()` combined with the bean graph; merely "not failing" is still insufficient.

## 12. Smoke test: the imports file and a real SpringBootApplication

The runner tests above do not test `AutoConfiguration.imports`. Therefore, a tiny smoke test is needed that boots a Spring Boot application root outside the auto-config package.

**`src/test/java/com/example/notify/BootAutoConfigurationSmokeTest.java`**

~~~java
package com.example.notify;

import com.example.app.NotifyDemoApplication;
import com.example.notify.api.NotificationClient;
import com.example.notify.api.NotificationObservation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = NotifyDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "demo.notify.enabled=true",
        "demo.notify.meter-enabled=true",
        "demo.notify.prefix=BOOT"
    })
class BootAutoConfigurationSmokeTest {

    @Autowired
    private NotificationClient notificationClient;

    @Autowired
    private NotificationObservation notificationObservation;

    @Test
    void bootAutoDiscoversTheImportedConfigurations() {
        assertThat(notificationClient.format("hello"))
                .isEqualTo("BOOT::hello");

        assertThat(notificationObservation.sample())
                .isEqualTo("BOOT::probe");
    }
}
~~~

### Why is this smoke test different from runner tests?

`@SpringBootTest` boots a real Spring Boot application. `NotifyDemoApplication` is in `com.example.app` and does not scan `com.example.notify` classes. Only because the project has the `AutoConfiguration.imports` file does Spring Boot discover `NotifyAutoConfiguration` and `NotificationObservationAutoConfiguration` as candidates.

If you delete the imports file, `NotificationClient` and `NotificationObservation` will not appear in this context, causing the test to fail immediately upon injection. Meanwhile, runner tests could still stay green because they passed `AutoConfigurations.of(...)` explicitly. **The two tests protect against two different failures.**

### When does a smoke test need even more?

In a published starter/library, in practice you also need:

- Build the JAR and verify the imports file sits at the exact path inside the artifact.
- Use a separate minimal consumer app to test auto-discovery when depending on the JAR as a dependency, not only testing inside the same module.
- Verify it is not accidentally component-scanned.
- Check package names/imports of shaded/fat JARs and version metadata.
- Test conditions on classpaths with/without external dependencies, not just a marker in the same module.
- When using Spring Boot AOT/native, add separate tests/builds because the runner does not execute inside a native image.

The lab stays within one module so learners can run it easily, though the concept of separating auto-config module/starter/consumer app remains valuable when moving to real projects.

## 13. Running Gradle and reading results

The sample suite has:

| Class | `@Test` method count | Scope |
| --- | ---: | --- |
| `NotificationAutoConfigurationTest` | 13 | Properties, classpath, default/back-off, dependency ordering, failure |
| `BootAutoConfigurationSmokeTest` | 1 | Boot startup auto-discovery via imports |
| **Total** | **14** | Isolated condition tests + integration smoke |

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run individually:

~~~bash
./gradlew test --tests 'com.example.notify.NotificationAutoConfigurationTest'
./gradlew test --tests 'com.example.notify.BootAutoConfigurationSmokeTest'
~~~

With a project that has a Gradle Wrapper, JDK 17, and dependencies downloaded successfully, **14 JUnit methods are expected to pass**. This is **an expected result derived from source code**, not a claim that the tests have been executed on the learner's machine.

Gradle reports are normally located at:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.notify.NotificationAutoConfigurationTest.xml
    └── TEST-com.example.notify.BootAutoConfigurationSmokeTest.xml
~~~

There is no `System.out.println` in the test code, so there is **no fixed business stdout**. If Gradle returns `UP-TO-DATE` or `FROM-CACHE`, the task may have been reused. When diagnosing a regression:

~~~bash
./gradlew test --rerun-tasks
~~~

If there is no Wrapper yet but the machine has a suitable Gradle installed, you can generate it:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Then commit the Wrapper scripts/JAR according to repository policy. Do not upgrade Boot/Spring Security/Testcontainers of a real project just to match a tutorial.

### Why don't runner tests use `@SpringBootTest`?

`ApplicationContextRunner` is already sufficient to build/close a small context with the specified auto-configs. Using `@SpringBootTest` on **every test matrix case** loads many unrelated configurations, increases startup cost, and makes results depend on the full app environment, easily obscuring condition logic. The full Boot smoke test only verifies what the runner **cannot verify independently**: imports/discovery and real wiring.

## 14. Why does `AutoConfigurations.of` matter with multiple classes?

Suppose a starter has:

~~~text
CoreClientAutoConfiguration
          |
          v
MetricsAutoConfiguration
          |
          v
TracingAutoConfiguration
          |
          v
WebAdapterAutoConfiguration
~~~

`CoreClient` creates the primary client, `Metrics` runs only if a client exists, `Tracing` runs only if OpenTelemetry is on the classpath, and `WebAdapter` runs only in the appropriate servlet/reactive environment.

If in your test you use:

~~~java
new ApplicationContextRunner()
    .withUserConfiguration(
        CoreClientAutoConfiguration.class,
        MetricsAutoConfiguration.class);
~~~

then you are treating auto-configurations as **user configurations**. When conditions depend on registration ordering, results may not reflect real auto-config behavior. Choose:

~~~java
new ApplicationContextRunner()
    .withConfiguration(AutoConfigurations.of(
        CoreClientAutoConfiguration.class,
        MetricsAutoConfiguration.class));
~~~

This snippet requires classes provided by a real project; names like `CoreClientAutoConfiguration`/`MetricsAutoConfiguration` only illustrate the architecture. Rule: use **AutoConfigurations** for configs acting as auto-configs, and use **withUserConfiguration** for configs supplied by the application user.

### Should you test one auto-config at a time or all together?

Both, depending on the goal:

- Test **one class alone** to verify its exact conditions and reduce noise.
- Test **a related group** to verify dependency ordering and collaborative bean graphs.
- Add a **full Boot smoke** test to verify imports/discovery.
- Avoid stuffing all Boot auto-configurations into every runner test just because passing a long list is easy.

### When adding `@AutoConfiguration(afterName=...)`

If your auto-config needs to run after a class that may not exist or belongs to an optional artifact, `afterName` lets you reference the class name as a String instead of hard-linking the class. This is auto-config dependency ordering; it does not create classes/beans itself. Test both when the optional config is present and absent if order matters.

## 15. ConditionEvaluationReport: why did a bean not appear?

When a `doesNotHaveBean` test passes, you may still want to know why:

- Missing optional class?
- `enabled=false`?
- `@ConditionalOnMissingBean` did not match because the user supplied a bean?
- `@ConditionalOnBean` did not see the dependency?
- Wrong classpath, missing imports?
- Property name typo or unexpected value?

Spring Boot provides **`ConditionEvaluationReport`** to display matched/non-matched conditions. In runner tests, you can enable logging:

~~~java
import org.springframework.boot.autoconfigure.logging
        .ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

new ApplicationContextRunner()
    .withConfiguration(AutoConfigurations.of(
        NotifyAutoConfiguration.class))
    .withInitializer(
        ConditionEvaluationReportLoggingListener
            .forLogLevel(LogLevel.INFO))
    .withPropertyValues("demo.notify.enabled=false")
    .run(context -> {
        assertThat(context)
            .doesNotHaveBean(NotificationClient.class);
    });
~~~

This is an **illustrative snippet in a test method with appropriate imports**. `ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)` is supported in Spring Boot 3.3. Logs can show positive/negative matches, but **do not hardcode exact log text as a long-term assertion**: wording/format can change across versions.

### What to look for in the report

- Whether `NotifyAutoConfiguration` appears in the report.
- Whether `OnClassCondition` matched the marker.
- Which property/value `OnPropertyCondition` observed.
- Which type/name `OnBeanCondition` looked for and which candidates existed.
- Did the condition fail because the class was absent or the property was false?
- Is the auto-config class missing from the report because it was never imported? Check the imports file/runner candidate list before looking for BeanFactory bugs.

**Pitfall:** Seeing a custom log report state that a condition matched does not automatically prove the bean was instantiated or that the business feature works. You still need `hasSingleBean` and assertions on bean behavior.

### Debugging with startup failure

~~~java
runner.withUserConfiguration(BrokenUserConfiguration.class)
    .run(context -> {
        assertThat(context).hasFailed();
        assertThat(context.getStartupFailure())
            .hasRootCauseInstanceOf(IllegalStateException.class);
    });
~~~

For tests needing root cause diagnostics, `getStartupFailure()` gives the underlying Throwable/traversal. Never catch and swallow exceptions to turn a test green.

## 16. Common auto-configuration design mistakes

| Mistake | Impact | Test that catches it |
| --- | --- | --- |
| Missing `AutoConfiguration.imports` | App does not auto-load auto-config | `BootAutoConfigurationSmokeTest` |
| Using `withUserConfiguration` instead of `AutoConfigurations.of` | Ordering differs from production | Runner test of auto-config dependencies |
| Forgetting `@ConditionalOnMissingBean` | Duplicate user/default beans | `userDefinedClientMakesDefaultBackOff` |
| `@ConditionalOnMissingBean` checking wrong type | User override has no effect | `hasSingleBean` + `isSameAs` |
| Forgetting `matchIfMissing=true` | Feature disabled by default | `defaultAutoConfigurationCreatesBothBeans` |
| Forgetting `havingValue="true"` | `enabled=yes` may still match | `unexpectedFlagValueDoesNotCountAsTrue` |
| Wrong property prefix/name | Setting has no effect | explicit true/false + prefix tests |
| Meter enabled property put on core config by mistake | Turning off metrics removes client | `disablingMeterDoesNotDisableClient` |
| Missing `@ConditionalOnClass` | Context may fail when library missing | `missingOptionalClassDisablesAutoConfiguration` |
| `ConditionalOnClass` placed on method referencing missing type | Classload may fail before condition | Nested `@Configuration` + `FilteredClassLoader` |
| Wrong ordering between auto-configs | Observer misses client | Default graph + observer tests |
| `@ConditionalOnBean` checks unregistered bean | Unintended condition no-match | `@AutoConfiguration(after=...)` + runner tests |
| Forgetting to test user bean when default disabled | Misunderstanding feature flag semantics | `disabledDefaultDoesNotDeleteUserClient` |
| Test only asserts non-null context | Wrong bean graph yet test stays green | `hasSingleBean`, `doesNotHaveBean` |
| Runner tests green but app fails | Runner does not run full SpringApplication bootstrap | Full Boot smoke + consumer app test |
| Changing imports package/class name | App loses auto-config | Full Boot smoke |
| Condition report lacks config class | Candidate was never loaded | Check `of`/imports, not just conditions |
| Enabling global bean overriding to dodge error | Hides duplicate definitions | Type-based back-off tests |
| Bean method return type too generic | Condition fails to recognize candidate type | Check explicit return type and user override |
| Unexpected property value/case/empty | Does not match accurately | Property matrix |
| Native test runs runner | Unsupported native image workflow | Dedicated AOT/native test |
| Context runner used for servlet conditional | Web condition false | `WebApplicationContextRunner` |
| Test mutates JVM-wide system properties | State leaks between tests | `withPropertyValues` |
| Too many auto-configurations in runner | Slow, hard to diagnose | Limit candidates, separate smoke test |
| Using manual import order to fix bug | Breaks on refactor | `AutoConfiguration` before/after metadata |

### Distinguishing behavior errors from harness errors

If a test fails because `NotificationObservation` is missing, check:

1. Did the runner pass both classes into `AutoConfigurations.of`?
2. Did `NotifyAutoConfiguration` match class/property?
3. Does `NotificationClient` exist in the BeanFactory?
4. Does `NotificationObservationAutoConfiguration` have the right `after`?
5. Is the `meter-enabled` property turned off?
6. Does the observation bean method condition check the right type?
7. Which classloader/parent context is the runner using?
8. Is there an unexpected test-only user bean?
9. Was a startup failure ignored?
10. Was `withUserConfiguration` accidentally used for an auto-config?

If only the smoke test fails, inspect imports/discovery/package scanning and the full app environment before changing core logic.

## 17. Bean registration order and override precedence

A good auto-configuration provides defaults without imposing on user choices. `@ConditionalOnMissingBean` allows users to declare custom beans by type. Points to keep in mind:

- Conditions rely on **bean definitions already processed**, not perpetually re-evaluating after every registration.
- User configuration must be registered before auto-config for back-off to work properly per Boot's pattern.
- `AutoConfigurations.of` sorts candidates according to auto-config semantics; do not treat raw class array order as a contract.
- `@Primary` or `@Qualifier` resolves selection among multiple candidates, but **is not a substitute** for back-off semantics.
- `spring.main.allow-bean-definition-overriding=true` allows some bean definitions with the same name to override each other, without guaranteeing proper behavior by type.
- In multi-module projects, the dependency graph and imports file can change when adding another starter; test relevant combinations and failure paths.
- `@ConditionalOnSingleCandidate` considers primary beans and candidate selection; test with multiple beans when using it.

### Method return type pitfall

Example:

~~~java
@Bean
Object externalClient() {
    return new VendorClient();
}
~~~

When Spring evaluates `@ConditionalOnBean(VendorClient.class)` based on bean definition metadata, it may not see the exact return type because the signature is too generic. Declare the most specific appropriate return type:

~~~java
@Bean
VendorClient externalClient() {
    return new VendorClient();
}
~~~

These are illustrative snippets; **there is no `VendorClient` class**, and they do not belong to the runnable project. When an optional class may be absent from the classpath, extract a nested configuration as in section 8 instead of letting the signature cause `NoClassDefFoundError`.

## 18. `@ConfigurationProperties` and validation in auto-config tests

The sample project uses `@Value` for the prefix to minimize source size. In a real starter, a group of properties should have type-safe `@ConfigurationProperties`:

~~~java
@ConfigurationProperties(prefix = "demo.notify")
public record NotifyProperties(
        boolean enabled,
        String prefix,
        Duration timeout) {
}
~~~

This is a general API snippet, **not part of the runnable project**. When used in auto-configuration, you must register/bind the properties via `@EnableConfigurationProperties(NotifyProperties.class)` or an appropriate binding mechanism; you can use `@Validated`, `@NotBlank`, `@DurationUnit`, configure defaults, and add validation dependencies.

Important cases:

1. Property absent: defaults are applied per contract.
2. `prefix=TEST`: binds accurately.
3. `timeout=250ms`: binds `Duration` with the right unit.
4. `timeout=not-a-duration`: startup fails with the appropriate binding exception.
5. `prefix=""` if forbidden: fails validation.
6. Bean not created when feature disabled: should properties still validate?
7. Config overlaid from profiles/ENV has right precedence when running the real app?
8. Is custom properties metadata generated for IDE support?
9. Do not use the `spring.*` namespace for third-party starter keys; choose a prefix owned by your team.

**Do not treat a runner test with successful property binding as proof of ConfigData/profile precedence in a full SpringApplication.** When a feature relies on `application.yml`, bootstrap/profile loading, add smoke/integration tests.

## 19. Simulating web and reactive contexts

When an auto-config has:

~~~java
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.SERVLET)
~~~

then a **non-web** `ApplicationContextRunner` will not match. This is the right behavior, not a bug. Use:

~~~java
new WebApplicationContextRunner()
    .withConfiguration(AutoConfigurations.of(
        WebAdapterAutoConfiguration.class))
    .run(context -> {
        // Assert servlet-specific beans.
    });
~~~

This snippet requires `WebAdapterAutoConfiguration` and web dependencies, and **does not belong to the runnable project**. For WebFlux/reactive:

~~~java
new ReactiveWebApplicationContextRunner()
    .withConfiguration(AutoConfigurations.of(
        ReactiveAdapterAutoConfiguration.class))
    .run(context -> {
        // Assert reactive-specific beans.
    });
~~~

Creating a web context and having servlet classes on the classpath does not automatically test HTTP request handling, filters, CORS, or network server ports. To test endpoints, use `MockMvc`/`WebTestClient`/real HTTP tests as appropriate. The runner here is strictly for testing **conditional bean registration**.

### Classpath distinctions

`@ConditionalOnWebApplication` is not the same as `@ConditionalOnClass(DispatcherServlet.class)`. Having servlet library classes while the context is not a servlet web app will not match the web condition. Conversely, multi-stack apps having both MVC and WebFlux on the classpath need to account for Spring Boot's application type selection; test contexts should mirror the real runtime scenario.

## 20. Testing configuration exclusions

In Spring Boot, users can exclude auto-configurations via:

~~~java
@SpringBootApplication(
    exclude = NotifyAutoConfiguration.class)
class SomeApplication {
}
~~~

This is an illustrative snippet; the class may not run standalone. Exclusion belongs to application auto-configuration discovery, **which is not the same** as omitting the class from `AutoConfigurations.of` in the runner. A test runner loads only the candidates you pass; if you omit a class, the bean's disappearance is trivial and does not prove `@SpringBootApplication(exclude=...)` works in a real app.

If the starter has a "users can exclude" requirement, add a dedicated Boot startup integration test with the exclusion and assert no bean exists. In a full Boot app, other auto-configs may depend on that bean; check the exclusion's impact on the bean graph, not just one class.

## 21. Auto-configuration metadata vs imports

Two easily confused resources:

| Resource | Purpose |
| --- | --- |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Lists auto-configuration classes for Boot discovery |
| `META-INF/spring-autoconfigure-metadata.properties` | Optimization metadata for early condition filtering, usually generated by annotation processor |
| `META-INF/spring-configuration-metadata.json` | IDE/configuration property metadata support |
| `META-INF/spring.factories` | Historic multi-purpose metadata mechanism; **not used to register `@AutoConfiguration` in Boot 3.3** |
| `application.yml`/`application.properties` | Application configuration values, not the auto-config class list |

An explicit runner can pass even **without an imports file**; thus the smoke test in this lesson protects registration. Similarly, missing optimization auto-config metadata usually does not stop auto-configuration from working (when imports/conditions are right), though it can affect startup performance.

### Why verify the packaged JAR?

When a library is published, resources can be mispackaged, merged improperly in a shaded JAR, or filtered out by the build pipeline. A developer testing inside the source module can see the imports file, yet the consumer dependency might lack it. For a production starter:

- Build the artifact.
- Inspect JAR contents or use a minimal consumer app.
- Verify auto-config classes are discovered without manual importing.
- Verify properties metadata/resource paths after packaging.
- Verify conditional dependencies are marked optional properly and absent-library behavior is safe.
- Check supported Boot versions per the release matrix.

There is no need to inspect a packaged JAR directly in this Step 4 lesson; that is an **extended CI exercise**, not part of the Google Sheets connector.

## 22. Avoid side effects in config tests

`ApplicationContextRunner` creates and closes contexts; if auto-config spins up thread pools, JDBC clients, HTTP clients, cloud SDKs, or broker connections, each test can open real resources, slowing down the suite or creating environment dependencies. To keep tests isolated:

1. When testing conditional bean registration, choose **in-memory** implementations or mocks/fakes at boundaries that do not need I/O.
2. For beans that must create connections, use a test-specific fake connector or scoped Testcontainers.
3. Never let the runner pull real credentials from CI environment variables; inject test properties.
4. Test `@PreDestroy`/`AutoCloseable` bean destruction when lifecycle resources exist.
5. Avoid caching static clients across contexts.
6. Never mutate `System.setProperty` without restoring it.
7. When external systems are needed, separate fast **condition tests** from slower **integration tests**.
8. Never let user configuration call production endpoints inside `@Bean`.
9. Use diagnostics on startup failure rather than infinite auto-retries.
10. When apps have metrics/tracing exporters, disable or redirect them to a fake test collector.

The lab uses `NotificationClient` as a network-free formatter so every condition test runs offline.

## 23. Context hierarchy and `@ConditionalOnBean` pitfalls

`ApplicationContextRunner.withParent(...)` can create a context hierarchy. Bean conditions have a `search` attribute controlling how parent/ancestors are searched. For example, if a parent context already registered `NotificationClient`, child auto-config can back off depending on `SearchStrategy`.

If a starter is used in systems with parent/child contexts (web management contexts, test context hierarchies), you must test:

- Bean of same type in parent, absent in child.
- `SearchStrategy.CURRENT` vs `SearchStrategy.ALL` per contract.
- Bean of same name but different type in child.
- A primary bean in parent and a regular bean in child.
- Whether conditions inspect ancestors properly.
- When child sees the bean only through parent, which bean does downstream dependency injection pick?
- `@ConditionalOnSingleCandidate` behavior with multiple candidates.

**Do not expand this lab to hierarchies unless the feature requires it**; add corresponding tests when a real product uses a multi-context architecture.

## 24. Anti-patterns and how to fix them

### Anti-pattern A — Only checking for no exceptions

~~~java
runner.run(context -> {
    assertThat(context).hasNotFailed();
});
~~~

This does not prove the default client exists, the prefix bound properly, or custom beans back off. Fix with `hasSingleBean` + functional behavior.

### Anti-pattern B — Auto-config loaded as user config

~~~java
new ApplicationContextRunner()
    .withUserConfiguration(
        NotifyAutoConfiguration.class);
~~~

This can bypass ordering semantics and alter bean conditions compared to runtime. Use `withConfiguration(AutoConfigurations.of(...))`.

### Anti-pattern C — Removing conditions to make tests pass

Removing `@ConditionalOnClass` or `@ConditionalOnMissingBean` may let a full context load in one specific environment, but it will fail on other consumer classpaths. Write negative tests instead of deleting guards.

### Anti-pattern D — Testing only the default

~~~java
runner.run(ctx ->
    assertThat(ctx).hasSingleBean(NotificationClient.class));
~~~

If default creates the bean but `enabled=false` also still creates it, the test misses it. Add false property, user override, missing class, and meter disabled cases.

### Anti-pattern E — Using live system properties

~~~java
System.setProperty("demo.notify.enabled", "false");
~~~

JVM-global state can leak to other tests and fail to restore upon assertion failures. Use `runner.withPropertyValues("demo.notify.enabled=false")` per case.

### Anti-pattern F — Filtering the wrong class

If you filter `org.springframework.*` instead of the optional library class, the test fails due to missing framework classes rather than proving the starter's guard. Filter only the marker/third-party type under test.

### Anti-pattern G — Asserting bean name without checking type

~~~java
assertThat(context).hasBean("notificationClient");
~~~

Another bean of the same type could coexist, causing ambiguity. Use `hasSingleBean(NotificationClient.class)` and, for user overrides, `isSameAs(customBean)`.

### Anti-pattern H — Enabling bean overriding instead of back-off

`spring.main.allow-bean-definition-overriding=true` does not protect the user customization contract. Fix `@ConditionalOnMissingBean` and test both custom/default branches.

### Anti-pattern I — Asserting exact condition report text

Log messages from `OnBean`/`OnClass` conditions can change across Spring Boot patch/minor versions. Use the report for diagnosis; long-term assertions should verify **the bean graph/behavior**.

### Anti-pattern J — Not checking the imports file

Runner tests with explicit `of` stay green even if discovery resources are missing. Add a full Boot smoke test or minimal consumer integration test.

### Anti-pattern K — Testing servlet conditions with the plain runner

Non-web `ApplicationContextRunner` does not match `@ConditionalOnWebApplication(SERVLET)`. Use `WebApplicationContextRunner` and matching web dependencies.

### Anti-pattern L — Claiming native image coverage

Spring Boot docs state `ApplicationContextRunner` does not work in native image tests. If the app must run on GraalVM native, add suitable AOT/native smoke tests.

## 25. Practice exercises

**Exercise A — remove matchIfMissing:** In `NotifyAutoConfiguration`, temporarily change `matchIfMissing=false`. The default test must fail while explicit `enabled=true` still passes. Explain absent-property semantics.

**Exercise B — change havingValue:** Remove `havingValue="true"` while keeping the enabled property. Test `enabled=yes` to see the difference between default property matching and value-specific matching.

**Exercise C — change prefix:** Temporarily replace `demo.notify.prefix` with `demo.notify.label` in `@Value`, then run the custom prefix test. The `TEST::message` assertion must fail.

**Exercise D — remove @ConditionalOnMissingBean:** Running with `CustomUserConfiguration` will produce multiple `NotificationClient` beans or a startup failure. Analyze why user overrides are no longer safe.

**Exercise E — add user bean:** Write a `@Configuration(proxyBeanMethods=false)` class with `@Bean NotificationClient` returning `CUSTOM::...`. Use `withUserConfiguration` and verify single bean + observer sample.

**Exercise F — with withBean:** Register `NotificationClient` via `runner.withBean(...)` without creating a `@Configuration`; verify default back-off.

**Exercise G — simulate missing SDK:** Filter `OptionalTransport` with `FilteredClassLoader`. If you remove `@ConditionalOnClass` from the auto-config, check how the test changes.

**Exercise H — auto-config order:** Temporarily remove `after=NotifyAutoConfiguration.class` and reverse argument order like in the original runner. Observe the observer condition; determine when order affects bean definitions.

**Exercise I — meter-enabled false:** Disable only the subfeature; ensure the client still exists. Write another test enabling meter true.

**Exercise J — disabled default + custom bean:** Prove `demo.notify.enabled=false` does not delete user beans. If the real contract wants the entire feature disabled, adjust conditions on the observer and update tests.

**Exercise K — missing imports:** Delete/rename the `AutoConfiguration.imports` path on a branch. Runner tests may stay green, but `BootAutoConfigurationSmokeTest` must turn red. Restore the file.

**Exercise L — packaging:** Create a Gradle multi-module demo consisting of `notify-autoconfigure`, `notify-starter`, and `sample-consumer`, run a consumer test using the JAR as a dependency, and verify auto-discovery.

**Exercise M — report:** Enable `ConditionEvaluationReportLoggingListener.forLogLevel(INFO)` for `enabled=false` and inspect the `OnPropertyCondition` report. Re-enable and compare. Do not assert exact log text.

**Exercise N — startup failure:** Create a `@Bean` that intentionally throws so `context.getStartupFailure()` has a root cause; tests should expect startup failure only when that case is designed for it.

**Exercise O — @ConfigurationProperties:** Add a properties class using `Duration` and validation, and write valid/invalid cases. Verify binder failure when values have invalid formats.

**Exercise P — servlet branch:** Create a separate `@ConditionalOnWebApplication(SERVLET)` auto-config, use `WebApplicationContextRunner`, and compare with `ApplicationContextRunner`.

**Exercise Q — parent context:** Provide `NotificationClient` in a parent context and verify `@ConditionalOnMissingBean(search=...)` and downstream injection according to the desired strategy.

**Exercise R — bean return type:** Change the `@Bean` return type from a proper interface to `Object` and observe `OnBean` conditions. Write a regression test to prevent overly generic method signatures.

**Exercise S — test no native:** Plan a separate AOT/native smoke test; do not treat runner tests as native coverage.

**Exercise T — manual mutation:** Temporarily break property/back-off/class guard/imports/ordering and confirm each test group fails meaningfully; revert everything afterward.

## 26. Checklist before merging auto-configuration

- [ ] Auto-config classes have `@AutoConfiguration` matching the Boot version?
- [ ] Classes are registered in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`?
- [ ] Auto-config package is not accidentally component-scanned?
- [ ] Runner uses `withConfiguration(AutoConfigurations.of(...))`?
- [ ] User configs use `withUserConfiguration`, not mixed up with auto-config?
- [ ] Tests cover absent default property and explicit true/false?
- [ ] `@ConditionalOnProperty` has `havingValue/matchIfMissing` matching the contract?
- [ ] Configurable prefix/timeout actual values are asserted?
- [ ] Optional classpath guard has a negative case with `FilteredClassLoader`?
- [ ] Default bean has `@ConditionalOnMissingBean` so users can override?
- [ ] Override tests check `hasSingleBean` and instance identity?
- [ ] Downstream auto-config has `@ConditionalOnBean` and clear ordering?
- [ ] Tests verify disabling a subfeature does not accidentally disable the core feature?
- [ ] Tests verify user bean survives when default auto-config is disabled?
- [ ] Context startup success/failure is asserted intentionally?
- [ ] `ConditionEvaluationReport` is inspected when negative cases are unclear?
- [ ] Isolated tests run a single auto-config class when isolating conditions?
- [ ] Related-group tests verify after/before ordering?
- [ ] A Boot smoke test protects imports discovery beyond explicit runner tests?
- [ ] If building a starter, a consumer app test uses the JAR as a dependency?
- [ ] Global bean overriding is not enabled to mask duplicates?
- [ ] System properties are not used instead of runner config (avoiding test state leaks)?
- [ ] If auto-config depends on servlet/reactive context, the right web runner is used?
- [ ] Tests do not open real external networks/DBs outside scope?
- [ ] Runner coverage is not claimed for native images?
- [ ] JDK 17 / Boot 3.3.5 / BOM dependencies are compatible?
- [ ] Negative tests or mutation tests prove guards work?
- [ ] No indeterminate/placeholder code in the runnable project?
- [ ] CI reports show JUnit test methods actually ran?

## 27. References

The links below are official Spring Boot documentation; sample code targets **Spring Boot 3.3.5**, while the 3.3 reference pages may display the latest patch of that minor line. When using Spring Boot 3.4+, 3.5+, or 4.x, verify API/module names and condition semantics against the actual BOM.

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): conventions, conditional annotations, auto-config imports, `ApplicationContextRunner`, `AutoConfigurations.of`, `FilteredClassLoader`, condition evaluation reporting, ordering.
- [Spring Boot 3.3 — AutoConfigurations Java API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurations.html): `of(Class<?>...)`, sorting and merge semantics.
- [Spring Boot 3.3 — ApplicationContextRunner Java API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): test context runner and methods.
- [Spring Boot 3.3 — ConditionEvaluationReportLoggingListener](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html): factory `forLogLevel(LogLevel.INFO)`.
- [Spring Boot 3.3 — @ConditionalOnProperty](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): `havingValue`, `matchIfMissing`, prefix/name.
- [Spring Boot 3.3 — @ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): bean conditions/back-off.
- [Spring Boot 3.3 — @ConditionalOnClass](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html): missing classpath behavior and class metadata.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, focused context tests, and test slices.
- [Spring Framework — @Configuration and @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/basic-concepts.html): registration and bean factories.
- [JUnit Jupiter — User Guide](https://docs.junit.org/5.10.2/user-guide/): test methods and lifecycle.
- [AssertJ — Assertions](https://assertj.github.io/doc/): assertThat, root causes, instance identity.

**Remember:** `AutoConfigurations.of` is for **auto-configuration classes** in `ApplicationContextRunner`, while `withUserConfiguration` is for application configurations overriding defaults. Verify **bean presence**, **bean absence**, **exact user bean instance**, **property values**, **classpath guards**, **dependency ordering**, and **startup failures**. Runner tests are fast, but cannot replace a full Boot smoke test checking **AutoConfiguration.imports**; combine both to prevent auto-configuration regressions in starters and libraries.