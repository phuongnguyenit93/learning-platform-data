# Historical relationship between spring.factories and auto-configuration registration

In older Spring Boot projects, you often see a file named `META-INF/spring.factories` used to list auto-configuration classes. Starting with Spring Boot 2.7, a dedicated registration file was introduced: `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. By Spring Boot 3.0, registering auto-configurations via the `org.springframework.boot.autoconfigure.EnableAutoConfiguration` key in `spring.factories` is no longer supported.

This change **does not mean Spring Boot removed `spring.factories`**. That file continues to serve many other extension points, such as `ApplicationListener`, `ApplicationContextInitializer`, `EnvironmentPostProcessor`, and `FailureAnalyzer`. Only the auto-configuration registration mechanism moved to the dedicated imports file.

This lesson belongs to the **Auto-configuration** chapter of **Spring Boot Fundamentals**. The goal is to understand why the legacy mechanism was used, the transition across versions, how to write the new registration file, how to maintain libraries compatible with multiple Spring Boot lines, and common mistakes when packaging starters or auto-configurations.

## 1. Auto-configuration needs a discovery mechanism

Spring Boot enables applications to start with minimal manual configuration. When appropriate dependencies are on the classpath, Boot can automatically register the necessary beans, provided the corresponding configuration conditions are satisfied.

For example, a library can provide auto-configuration for an email client:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(MailClient.class)
public class MailAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public MailClient mailClient(MailProperties properties) {
        return new MailClient(properties.host(), properties.port());
    }
}
```

The class above defines the configuration, but Spring Boot needs to know **how to find this class** when an application simply adds the library as a dependency. You cannot expect every application to manually import every auto-configuration from all starters.

Therefore, a library needs to publish a list of configuration classes permitted to participate in auto-configuration. Spring Boot reads this list from the classpath, then processes conditions, ordering, and bean definitions.

Over Spring Boot's history, how that list is published has changed:

```text
Spring Boot 1.x through 2.6
    META-INF/spring.factories
        key: EnableAutoConfiguration
                  │
                  ▼
Spring Boot 2.7
    AutoConfiguration.imports (new mechanism)
    spring.factories (legacy mechanism still compatible)
                  │
                  ▼
Spring Boot 3.0 and later
    AutoConfiguration.imports
    spring.factories remains for other extension points
```

This is an important historical milestone when reading an older Spring Boot library or upgrading a custom starter.

## 2. Historical mechanism: registration via spring.factories

Before Spring Boot 2.7, auto-configurations were usually registered in the file:

```text
META-INF/spring.factories
```

This is a Java properties-formatted file. The key is the fully qualified name of an extension point; the value is a comma-separated list of implementation classes.

Example of auto-configuration registration:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.mail.autoconfigure.MailAutoConfiguration,\
com.example.storage.autoconfigure.StorageAutoConfiguration
```

The key:

```text
org.springframework.boot.autoconfigure.EnableAutoConfiguration
```

is the fully qualified name of the `EnableAutoConfiguration` marker. The value lists the auto-configuration classes that Spring Boot needs to consider.

### 2.1. Each library can contribute its own spring.factories

Suppose an application uses three libraries:

```text
application.jar
├── spring-boot-autoconfigure.jar
├── mail-starter.jar
│   └── META-INF/spring.factories
├── storage-starter.jar
│   └── META-INF/spring.factories
└── metrics-starter.jar
    └── META-INF/spring.factories
```

Each library can declare implementations for the same key in its own file. Spring Boot uses a factory loading mechanism across the classpath to aggregate candidates from the libraries.

Because of this, an application does not need a single `spring.factories` file containing every auto-configuration from all dependencies. Each starter can publish its own extension components.

### 2.2. How Spring Boot processes the list

Conceptually, the flow can be described as:

```text
JARs on the runtime classpath
          │
          ▼
Locate META-INF/spring.factories files
          │
          ▼
Read the EnableAutoConfiguration key
          │
          ▼
Aggregate auto-configuration class names
          │
          ▼
Process exclusions, ordering, and conditions
          │
          ▼
Register matching bean definitions
          │
          ▼
Create beans in ApplicationContext
```

The `spring.factories` file is only **where implementations are published**. It does not directly create beans, nor does it guarantee an auto-configuration will definitely be applied.

After a class is discovered, Spring Boot still has to evaluate conditions such as `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, and `@ConditionalOnMissingBean`. An auto-configuration that is listed but whose conditions do not match may contribute no beans at all.

### 2.3. Historical example with a custom library

A library could have the structure:

```text
mail-starter/
├── src/main/java/
│   └── com/example/mail/autoconfigure/
│       └── MailAutoConfiguration.java
└── src/main/resources/
    └── META-INF/
        └── spring.factories
```

File content:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.mail.autoconfigure.MailAutoConfiguration
```

The consuming application only needs to declare the starter dependency. If the JAR is packaged properly and conditions match, Boot can discover the auto-configuration without the application importing that class manually.

### 2.4. Historical does not mean recommended for new projects

Many older guides or articles still instruct registering auto-configurations with `spring.factories`. Those examples are accurate for the corresponding Spring Boot versions, but should not be copied as-is into a library targeting only Boot 3.x.

When reading a guide, check which Spring Boot version is used. The exact same registration file can work in Boot 2.6, continue working in the 2.7 transition period, yet no longer register auto-configurations in Boot 3.0.

## 3. Why did Spring Boot move to AutoConfiguration.imports?

Spring Boot 2.7 introduced a dedicated file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

The new file addresses publishing the auto-configuration list with a clearer format:

- Dedicated exclusively to auto-configuration.
- Each line contains one fully qualified class name.
- No long properties key needed.
- No comma-separated class lists with line continuation backslashes.
- Comments starting with `#` can be added.
- Separates auto-configuration registration from other extension points that still use `spring.factories`.

For example:

```text
com.example.mail.autoconfigure.MailAutoConfiguration
com.example.storage.autoconfigure.StorageAutoConfiguration
com.example.metrics.autoconfigure.MetricsAutoConfiguration
```

### 3.1. Comparing the two formats

| Criterion | Legacy `spring.factories` | `AutoConfiguration.imports` |
|---|---|---|
| Location | `META-INF/spring.factories` | `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |
| Format | Java properties | List of classes, one class per line |
| Structure | Key and value | No key |
| Class list | Comma-separated | Each class on its own line |
| Comments | Properties syntax | Lines starting with `#` |
| Scope | Multiple extension points | Dedicated to the auto-configuration list |
| Modern status | EnableAutoConfiguration key unused since Boot 3.0 | Current auto-configuration registration mechanism |

### 3.2. The new file does not replace every function of spring.factories

This is the most easily misunderstood point.

Spring Boot 3.0 removed support for **registering auto-configurations via the EnableAutoConfiguration key in spring.factories**. That does not mean every other key in this file was deleted.

For example, extension points that still use `spring.factories`:

- `org.springframework.context.ApplicationListener`.
- `org.springframework.context.ApplicationContextInitializer`.
- `org.springframework.boot.env.EnvironmentPostProcessor`.
- `org.springframework.boot.diagnostics.FailureAnalyzer`.

Thus, a library may simultaneously need both files:

```text
META-INF/
├── spring.factories
└── spring/
    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Where:

- `spring.factories` contains extension points that still use the factories mechanism.
- `AutoConfiguration.imports` contains the auto-configuration list.

Do not delete `spring.factories` from a library simply because auto-configuration moved to the imports file. Inspect the other keys that the library still registers.

## 4. Timeline: Boot 2.6, 2.7, and 3.0

These three milestones are commonly used when explaining the transition.

### 4.1. Before Spring Boot 2.7

The common mechanism was:

```text
META-INF/spring.factories

org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.demo.autoconfigure.DemoAutoConfiguration
```

Spring Boot looked up the `EnableAutoConfiguration` key to collect auto-configuration classes.

### 4.2. Spring Boot 2.7: transition period

Spring Boot 2.7 introduced `AutoConfiguration.imports` and recommended migrating auto-configuration lists to the new file.

However, for backward compatibility:

- Boot 2.7 still reads legacy auto-configuration entries in `spring.factories`.
- The same auto-configuration can be listed in both files.
- Boot 2.7 deduplicates entries when they appear in both places.
- Loading auto-configurations from `spring.factories` was marked deprecated.

This was the appropriate phase for libraries to transition while remaining compatible with applications using older Boot lines.

### 4.3. Spring Boot 3.0: legacy registration key removed

Spring Boot 3.0 removed support for registering auto-configurations via the key:

```text
org.springframework.boot.autoconfigure.EnableAutoConfiguration
```

in `META-INF/spring.factories`.

Instead, auto-configurations must be listed in:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Entries under other keys in `spring.factories` are unaffected by this change.

### 4.4. Timeline table

| Version | `spring.factories` with EnableAutoConfiguration key | `AutoConfiguration.imports` |
|---|---|---|
| Boot 2.6 and earlier | Standard auto-configuration registration mechanism | Not yet a supported mechanism |
| Boot 2.7 | Still read for compatibility; legacy approach deprecated | Introduced and supported |
| Boot 3.0 and later | Key no longer supported for registering auto-configurations | Auto-configuration registration mechanism |

A library that must support multiple Boot lines has to pick a registration strategy matching the lowest and highest versions it commits to supporting.

## 5. Exact format and location of AutoConfiguration.imports

The full file name is critical. Not every file ending in `.imports` is an auto-configuration list.

Standard path:

```text
src/main/resources/META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

After building the JAR, the resource must appear at the same path inside the artifact:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Example content:

```text
com.example.mail.autoconfigure.MailAutoConfiguration
com.example.mail.autoconfigure.MailWebAutoConfiguration
```

### 5.1. Rules for writing class names

Each line uses a fully qualified class name:

```text
com.example.mail.autoconfigure.MailAutoConfiguration
```

Do not write:

```text
MailAutoConfiguration
```

Do not write a package path with slashes:

```text
com/example/mail/autoconfigure/MailAutoConfiguration.class
```

Do not append `.class`. The file contains Java class names, not class file paths.

### 5.2. Comments and blank lines

You can add comments starting with `#`:

```text
# Core auto-configuration
com.example.mail.autoconfigure.MailAutoConfiguration

# Optional web integration
com.example.mail.autoconfigure.MailWebAutoConfiguration
```

Comments help library maintainers understand the purpose of each configuration group. Blank lines can be used to separate groups for readability.

### 5.3. Nested auto-configuration classes

In the rare case where an auto-configuration is a nested class, use the `$` symbol between the outer class and the nested class:

```text
com.example.Outer$NestedAutoConfiguration
```

However, it is usually better to place auto-configuration classes in their own packages and top-level classes for easier management, testing, and ordering.

## 6. The @AutoConfiguration annotation introduced alongside the new mechanism

Spring Boot 2.7 introduced the annotation:

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
```

This annotation is used to mark top-level auto-configuration classes listed in `AutoConfiguration.imports`.

For example:

```java
package com.example.mail.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(MailClient.class)
public class MailAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public MailClient mailClient() {
        return new MailClient();
    }
}
```

`@AutoConfiguration` is meta-annotated with `@Configuration`, so an auto-configuration remains a normal Spring configuration. The new annotation also supports ordering attributes such as `before`, `beforeName`, `after`, and `afterName`.

### 6.1. @AutoConfiguration takes over marking top-level classes

Previously, auto-configurations typically used:

```java
@Configuration
public class MailAutoConfiguration {
}
```

With the new mechanism, top-level auto-configurations should use:

```java
@AutoConfiguration
public class MailAutoConfiguration {
}
```

Configuration classes nested inside or imported by an auto-configuration can still use `@Configuration` as usual.

Do not assume `@AutoConfiguration` replaces every `@Configuration` in an application. It has a dedicated purpose for auto-configuration classes.

### 6.2. @AutoConfiguration does not register the class automatically

Putting `@AutoConfiguration` on a class does not mean Spring Boot automatically finds the class in any package.

The class still needs to be listed in the imports file:

```text
com.example.mail.autoconfigure.MailAutoConfiguration
```

At the same time, auto-configuration classes should live in a separate package and not be targets of application component scanning. The imports registration mechanism is the discovery path for auto-configuration.

### 6.3. Ordering with @AutoConfiguration

You can declare:

```java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class MailDatabaseIntegrationAutoConfiguration {
}
```

Or:

```java
@AutoConfiguration(beforeName = "com.example.other.OtherAutoConfiguration")
public class MailIntegrationAutoConfiguration {
}
```

Ordering attributes determine the processing order of auto-configuration classes. They do **not** directly determine the creation order of bean instances. Bean instances are still created according to the dependency graph, scope, and relationships such as `@DependsOn`.

## 7. Complete example: migrating a library from spring.factories to imports

Suppose the `acme-mail-spring-boot-starter` library has an auto-configuration:

```text
acme-mail-spring-boot-starter/
└── src/main/
    ├── java/
    │   └── com/acme/mail/autoconfigure/
    │       └── AcmeMailAutoConfiguration.java
    └── resources/
        └── META-INF/
            └── spring/
                └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

### 7.1. Auto-configuration class

```java
package com.acme.mail.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(AcmeMailClient.class)
@ConditionalOnProperty(
        prefix = "acme.mail",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class AcmeMailAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public AcmeMailClient acmeMailClient(AcmeMailProperties properties) {
        return new AcmeMailClient(
                properties.host(),
                properties.port()
        );
    }
}
```

The example assumes `AcmeMailClient` and `AcmeMailProperties` are classes provided by the library and have matching binding configuration.

### 7.2. Imports file

Create:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Content:

```text
com.acme.mail.autoconfigure.AcmeMailAutoConfiguration
```

### 7.3. Configuration of an application using the starter

```yaml
acme:
  mail:
    enabled: true
    host: smtp.example.test
    port: 587
```

The application adds the starter dependency. Spring Boot finds the imports file in the JAR, collects the auto-configuration class, evaluates classpath and property conditions, and registers the bean if conditions match.

### 7.4. Users can replace the default bean

The application can declare its own:

```java
@Configuration(proxyBeanMethods = false)
public class CustomMailConfiguration {

    @Bean
    public AcmeMailClient acmeMailClient() {
        return new CustomAcmeMailClient();
    }
}
```

If the custom bean is registered before the auto-configuration method condition is evaluated, `@ConditionalOnMissingBean` causes the default bean to back off.

This is a common pattern: a library provides default behavior while allowing the application to customize with its own bean.

## 8. Supporting Spring Boot 2.x and 3.x simultaneously

A library used across multiple applications may need to support:

- Older applications on Spring Boot 2.6 or lower.
- Transitional applications on Spring Boot 2.7.
- Newer applications on Spring Boot 3.x.

In this case, you need to understand the compatibility window clearly.

### 8.1. Registering in both files during a transition period

A library can list the same auto-configuration in both:

```text
META-INF/spring.factories
```

and:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Legacy file example:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.mail.autoconfigure.MailAutoConfiguration
```

New file:

```text
com.example.mail.autoconfigure.MailAutoConfiguration
```

Outcome by version:

| Runtime version | Outcome |
|---|---|
| Boot 2.6 and earlier | Uses the entry in `spring.factories` |
| Boot 2.7 | Supports both locations and deduplicates |
| Boot 3.x | Uses the imports file; the EnableAutoConfiguration key in `spring.factories` is no longer read to register auto-configurations |

This is the approach described in the Spring Boot 2.7 release notes for libraries needing to support both legacy and modern lines.

### 8.2. Watch out for class annotations across versions

`@AutoConfiguration` was introduced in Spring Boot 2.7. If a library still commits to running on Boot versions older than 2.7, verify classpath compatibility of the annotations and APIs used.

Do not simply swap the registration file and assume all library source code remains compatible with every version. Check:

- The minimum supported Spring Boot version.
- Annotations/APIs referenced by the auto-configuration class.
- The Java baseline version.
- Spring Framework APIs used in the code.
- How to test the version matrix.

For libraries needing to support multiple major lines, you may need compatible source/APIs or separate artifact lines. Verify with real sample applications running on each committed version.

### 8.3. Do not remove the legacy file too early

If the library still needs to support Boot 2.6 or earlier, removing the `EnableAutoConfiguration` entry from `spring.factories` will prevent the auto-configuration from being discovered on those versions.

Conversely, if targeting only Boot 3.x, continuing to maintain the legacy key in `spring.factories` has no effect on auto-configuration registration and can mislead maintainers.

The decision to keep both files must be based on the supported version matrix, not habit.

## 9. Which extension points still use spring.factories?

The `spring.factories` file has a broader scope than auto-configuration. It is a factories mechanism for publishing implementations keyed by class/interface.

In modern Spring Boot, several extension points still use this mechanism.

### 9.1. ApplicationListener

A listener may need to receive events very early, even before the ApplicationContext is created. Registering it as a bean in the context can be too late.

For example:

```properties
org.springframework.context.ApplicationListener=\
com.example.bootstrap.StartupListener
```

Class:

```java
package com.example.bootstrap;

import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public class StartupListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("SpringApplication is starting");
    }
}
```

Spring Boot can load listeners from factories and register them with `SpringApplication` at the appropriate stage.

### 9.2. ApplicationContextInitializer

An initializer is used to customize the ApplicationContext before the context is refreshed:

```properties
org.springframework.context.ApplicationContextInitializer=\
com.example.bootstrap.CustomContextInitializer
```

For example:

```java
package com.example.bootstrap;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

public class CustomContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(
            ConfigurableApplicationContext applicationContext
    ) {
        System.out.println("Preparing ApplicationContext");
    }
}
```

This is a different extension point from auto-configuration. The initializer acts on context preparation; it is not a list of default bean configurations.

### 9.3. EnvironmentPostProcessor

`EnvironmentPostProcessor` allows adjusting the Environment before the ApplicationContext is refreshed:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.bootstrap.CustomEnvironmentPostProcessor
```

For example:

```java
package com.example.bootstrap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;

public class CustomEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        System.out.println("Environment is being prepared");
    }
}
```

This extension point is suitable when a library needs to load additional PropertySources or customize the Environment before bean creation begins.

### 9.4. FailureAnalyzer

A FailureAnalyzer helps turn a startup error into a clearer message:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.diagnostics.CustomFailureAnalyzer
```

Illustrative example:

```java
package com.example.diagnostics;

import org.springframework.boot.diagnostics.AbstractFailureAnalyzer;
import org.springframework.boot.diagnostics.FailureAnalysis;

public class CustomFailureAnalyzer
        extends AbstractFailureAnalyzer<IllegalStateException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure,
            IllegalStateException cause
    ) {
        return new FailureAnalysis(
                "Application configuration is invalid.",
                "Check the custom feature settings.",
                cause
        );
    }
}
```

FailureAnalyzer belongs to startup error diagnostics infrastructure, not a regular business bean.

### 9.5. Distinction table

| Purpose | Commonly used key/resource |
|---|---|
| Modern auto-configuration registration | `AutoConfiguration.imports` |
| Application listeners loaded via factories | `ApplicationListener` in `spring.factories` |
| Application context initializers | `ApplicationContextInitializer` in `spring.factories` |
| Environment post-processors | `EnvironmentPostProcessor` in `spring.factories` |
| Failure analyzers | `FailureAnalyzer` in `spring.factories` |

This list shows common examples, not every extension point loadable via factories. When migrating a library, inspect each key in the file instead of deleting the entire file.

## 10. Do not confuse AutoConfiguration.imports with other .imports files

Spring Boot uses several imports files for different purposes.

For example:

```text
META-INF/spring/
├── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── org.springframework.boot.actuate.autoconfigure.web.ManagementContextConfiguration.imports
```

The first file registers normal auto-configurations. The second serves management context configuration in Actuator.

Spring Boot 2.7 also moved registration of certain test slice configurations from `spring.factories` to files:

```text
META-INF/spring/<fully-qualified-name-of-test-annotation>.imports
```

This is a separate mechanism for test slices. Do not put test configurations into `AutoConfiguration.imports` just because both use the `.imports` extension.

When working with imports files, always verify the **exact full file name and the extension point that file registers**.

## 11. Packaging multiple libraries: why is resource merging needed?

An application can depend on multiple starters, each contributing a file:

```text
starter-a.jar
└── META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── com.example.a.AutoConfiguration

starter-b.jar
└── META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── com.example.b.AutoConfiguration
```

When running with a normal classpath or executable JAR, Spring Boot can locate resources of the same name across dependency JARs and aggregate candidates.

However, if you build an **uber JAR/shaded JAR** by unpacking multiple dependencies and merging them into one file, multiple resources sharing the same path can overwrite one another if the plugin is not configured to append.

Dangerous outcome: the application retains only part of the auto-configuration list, even though all libraries are still inside the JAR.

### 11.1. Example of an error when merging incorrectly

Suppose:

```text
starter-a: AutoConfiguration.imports
    com.example.a.AutoConfiguration

starter-b: AutoConfiguration.imports
    com.example.b.AutoConfiguration
```

If the packaging process only keeps one file at a colliding path instead of concatenating contents, the final output may contain only:

```text
com.example.b.AutoConfiguration
```

Starter A's auto-configuration vanishes from the discovery list.

This is a resource packaging bug, not a condition or component scanning bug.

### 11.2. Maven Shade Plugin

If using `maven-shade-plugin` to create a shaded JAR, you may need `AppendingTransformer` for imports resources:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports</resource>
</transformer>
```

If the project also packages management context imports, configure appending for that file as well:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring/org.springframework.boot.actuate.autoconfigure.web.ManagementContextConfiguration.imports</resource>
</transformer>
```

This configuration is for scenarios using the Maven Shade Plugin; it does not need to be added to every Maven project. A standard Spring Boot executable JAR is not the same as a shaded JAR unpacked and resource-merged in this manner.

### 11.3. Gradle Shadow Plugin

With the Gradle Shadow Plugin:

```groovy
tasks.withType(com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar).configureEach {
    append("META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports")
    append("META-INF/spring/org.springframework.boot.actuate.autoconfigure.web.ManagementContextConfiguration.imports")
}
```

Package/task type names may differ by plugin version. What matters is configuring Shadow to append colliding imports resources rather than keeping an arbitrary copy.

If the library also uses `spring.factories` for other extension points, check the plugin's corresponding factories merge mechanism. Do not merge only imports and accidentally lose still-needed factories entries.

### 11.4. Inspecting JAR contents after building

Use the command:

```bash
jar --list --file build/libs/application-all.jar
```

Look for:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Then you can extract or view the resource content to confirm all expected auto-configurations are in the final file.

If building a standard Spring Boot executable JAR, inspect resources inside nested dependency JARs or use appropriate tools to view each nested JAR's contents. Do not assume every dependency resource must be flattened into a single file at the root JAR.

## 12. How should an auto-configuration class be organized?

Changing the registration file does not replace auto-configuration design conventions.

A library structure might look like:

```text
acme-storage-spring-boot-autoconfigure/
├── src/main/java/
│   └── com/acme/storage/autoconfigure/
│       ├── AcmeStorageAutoConfiguration.java
│       ├── AcmeStorageProperties.java
│       └── AcmeStorageClient.java
└── src/main/resources/
    ├── META-INF/spring/
    │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── META-INF/
        └── additional-spring-configuration-metadata.json
```

### 12.1. Do not rely on component scanning to find auto-configurations

Auto-configuration classes should be discovered via the imports file. They should live in a separate package and not be targets of the application's regular component scanning.

For example, if the application's main class is in the package:

```text
com.acme.application
```

while the auto-configuration library is in:

```text
com.acme.storage.autoconfigure
```

then having the library's package outside the component scan area is normal. The imports file lets Boot discover it without scanning the entire library package.

Auto-configurations should not turn on broad component scanning to discover the library's own components. Use explicit `@Import` for necessary configurations or components to avoid accidentally scanning application packages.

### 12.2. Using conditions to avoid creating unnecessary beans

For example:

```java
@AutoConfiguration
@ConditionalOnClass(AcmeStorageClient.class)
@EnableConfigurationProperties(AcmeStorageProperties.class)
public class AcmeStorageAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    @ConditionalOnProperty(
            prefix = "acme.storage",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    public AcmeStorageClient acmeStorageClient(
            AcmeStorageProperties properties
    ) {
        return new AcmeStorageClient(properties.endpoint());
    }
}
```

This configuration illustrates an auto-configuration conditional on classpath, property, and existing bean. In a real project, ensure the class/property types are defined and conditions match the starter's intent.

### 12.3. Auto-configuration ordering

If an auto-configuration needs to be processed after another configuration:

```java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class AcmeJdbcAutoConfiguration {
}
```

You can use `before`, `beforeName`, `after`, and `afterName` attributes or the corresponding ordering annotations.

Ordering affects configuration application order and when bean-based conditions can observe definitions. It does not control instance creation order independently of the dependency graph.

## 13. Diagnosing when auto-configuration is not discovered

If an application adds a starter yet default beans do not appear, check layer by layer.

### 13.1. Check whether the registration file is inside the JAR

First inspect the library artifact:

```bash
jar --list --file acme-storage-spring-boot-autoconfigure.jar
```

You must see the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

If using an older Boot version and still needing `spring.factories` support, also check:

```text
META-INF/spring.factories
```

### 13.2. Check class names in imports

Each line must be a valid fully qualified name. Common mistakes:

- Wrong package.
- Wrong casing.
- Renamed class without updating the imports file.
- Adding `.class`.
- Using `/` instead of `.` between packages.
- Class absent from the runtime artifact.
- Class is a nested class but uses the wrong `$` notation.

### 13.3. Check the exact Spring Boot version

A library with only the `spring.factories` EnableAutoConfiguration key:

- Can run on Boot 2.6.
- Can still run on Boot 2.7 due to compatibility support.
- Does not register auto-configurations on Boot 3.0+.

If the application runs Boot 3 and beans do not appear, check the imports file before tweaking other conditions.

### 13.4. Check the condition report

Run the application with `--debug`:

```bash
java -jar application.jar --debug
```

The Condition Evaluation Report can indicate that the auto-configuration was discovered but its conditions did not match.

Distinguish:

```text
Auto-configuration candidate not found
          │
          └── Check imports resource, classpath, version

Candidate found but conditions do not match
          │
          └── Check classpath, properties, beans, profiles

Conditions match but bean is not created
          │
          └── Check dependencies, bean definitions, initialization
```

Do not conclude the imports file is wrong merely because a bean is missing. The auto-configuration may have been discovered while `@ConditionalOnProperty` or `@ConditionalOnMissingBean` led to a different outcome than expected.

### 13.5. Check exclusions

The application may exclude an auto-configuration via:

```java
@SpringBootApplication(
        exclude = MailAutoConfiguration.class
)
public class Application {
}
```

Or configuration:

```yaml
spring:
  autoconfigure:
    exclude:
      - com.example.mail.autoconfigure.MailAutoConfiguration
```

If the class is in imports yet excluded, it will still not be applied. Check exclusion lists in source code, properties, and the report.

## 14. Testing auto-configuration properly

A starter library should test that its auto-configurations are discoverable from resources and that conditions behave as expected.

Spring Boot provides `ApplicationContextRunner` to test a small configuration without starting an entire web application.

For example:

```java
class MailAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(MailAutoConfiguration.class)
                    );

    @Test
    void createsMailClientWhenEnabled() {
        contextRunner
                .withPropertyValues("acme.mail.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(MailClient.class);
                });
    }
}
```

Example illustrating an auto-configuration condition test. Corresponding test dependencies and necessary class imports are required.

### 14.1. Does the test check whether the class is discovered?

`ApplicationContextRunner` with `AutoConfigurations.of(...)` tests the contents of the specified configuration. However, this test **does not necessarily confirm that the AutoConfiguration.imports file in the JAR is packaged properly** because the class was passed directly in the test.

To verify discovery from the artifact, include an integration test or sample application that actually consumes the library as a dependency and starts Spring Boot normally.

### 14.2. Cases to test

- Optional dependency present and absent.
- Property enabled, disabled, and undeclared.
- User-provided bean replacing the default.
- Multiple beans of the same type.
- Auto-configuration excluded.
- Necessary auto-configuration ordering.
- Imports file present in the released JAR.
- Shaded/uber JAR preserving the complete resource list.

Condition tests and packaging tests answer two different questions. A passing context test does not guarantee the registration resource in the released artifact was not lost.

## 15. Common errors during migration

| Symptom | Possible cause | Resolution |
|---|---|---|
| Boot 3 does not find auto-configuration | Registered only via EnableAutoConfiguration key in `spring.factories` | Move the class to `AutoConfiguration.imports` |
| Boot 2.6 does not find auto-configuration after migration | Removed `spring.factories` entry while older version does not yet support imports | Keep the legacy entry if Boot 2.6 or earlier is still supported |
| Boot 2.7 works even with both files present | Boot 2.7 supports both locations and deduplicates | This is the designed compatibility behavior |
| Boot 3 still does not create the bean despite class in imports file | Condition mismatch or class cannot be loaded | Check Condition Evaluation Report and runtime classpath |
| Auto-configuration disappears after building shaded JAR | Colliding resource paths overwritten instead of appended | Configure a resource transformer/append |
| Another library feature still needs `spring.factories` | Deleted the entire file during migration | Keep keys that are still supported |
| Class registered but configuration is not applied | Class is in imports yet excluded or condition is false | Check exclusions and conditions |
| Auto-configuration registered twice | Registered in both files on Boot 2.7 with different classes or unexpected merge behavior | Verify identical FQCN, resource contents, and report |
| Class-not-found error when running on older Boot | Source references annotations/APIs only present in newer Boot | Check baseline version and compatibility |
| Tests pass but published starter does not work | Tests import class directly without checking artifact file | Add an integration test consuming the real JAR |

### 15.1. Do not confuse discovery errors with condition errors

If Boot 3 does not discover the class because the imports file is missing, conditions are not the cause yet. If Boot discovered the class but `@ConditionalOnClass` failed to match, changing the imports file will not fix it.

Diagnose in order:

1. Is the class in the artifact?
2. Does the registration file have the exact path and content?
3. Does the Boot version support that registration mechanism?
4. Is the auto-configuration excluded?
5. Do the conditions match?
6. Are bean definitions and dependencies valid?

## 16. Migration guide by scenario

### Scenario A — Library supports only Boot 3.x

Use:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Annotate the class with `@AutoConfiguration` and do not use the EnableAutoConfiguration key in `spring.factories` to register auto-configurations.

If the library still needs `ApplicationListener` or `EnvironmentPostProcessor`, keep `spring.factories` for those keys.

### Scenario B — Library supports Boot 2.7 and 3.x

You can register the same class in both files during the transition period:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.lib.autoconfigure.LibAutoConfiguration
```

and:

```text
com.example.lib.autoconfigure.LibAutoConfiguration
```

Boot 2.7 reads both and deduplicates; Boot 3 uses the imports file. Test on every Boot version actually supported.

### Scenario C — Library still supports Boot 2.6 or earlier

Keep the `spring.factories` entry because those versions do not yet support the new imports mechanism. You can simultaneously package the imports file for newer versions to use.

Check that annotations/APIs in the auto-configuration class are compatible with the lowest supported version. `@AutoConfiguration` appeared in Boot 2.7; if the artifact must still run with older Boot releases, do not assume the new annotation exists on their runtime classpath.

### Scenario D — Library has multiple extension points in spring.factories

Example legacy file:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.lib.autoconfigure.LibAutoConfiguration

org.springframework.context.ApplicationListener=\
com.example.lib.bootstrap.LibListener

org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.lib.bootstrap.LibEnvironmentPostProcessor
```

After migration, split out the auto-configuration part:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Content:

```text
com.example.lib.autoconfigure.LibAutoConfiguration
```

Keep `spring.factories` with the remaining keys:

```properties
org.springframework.context.ApplicationListener=\
com.example.lib.bootstrap.LibListener

org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.lib.bootstrap.LibEnvironmentPostProcessor
```

This is a deliberate migration: move exactly one extension point without deleting the factories mechanism for other extension points.

## 17. Distinguishing metadata files in Spring Boot

Inside the `META-INF` directory there can be several files with different names and purposes.

| File | Purpose |
|---|---|
| `META-INF/spring.factories` | Registers various factory/extension points; before Boot 3 also held the EnableAutoConfiguration key |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Registers auto-configuration classes |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements` | Declares replacement relationships between old and new auto-configuration classes in migration scenarios |
| `META-INF/spring-autoconfigure-metadata.properties` | Metadata generated by an annotation processor to quickly filter certain auto-configuration conditions and improve startup |
| `META-INF/spring-configuration-metadata.json` | Metadata supporting IDE/documentation for configuration properties |
| `META-INF/spring/<test-slice-annotation>.imports` | Registers configurations for test slices per the corresponding mechanism |

Do not misuse `spring-autoconfigure-metadata.properties` as an auto-configuration registration file. It is optimization metadata for condition filtering, whereas `AutoConfiguration.imports` is what lists candidate classes.

## 18. Relationship between imports, conditions, and auto-configuration metadata

An auto-configuration class may appear in imports yet not necessarily be applied.

Conceptual flow:

```text
AutoConfiguration.imports
          │
          ▼
List of auto-configuration candidates
          │
          ▼
Exclusions and ordering
          │
          ▼
Condition evaluation
  ├── classpath
  ├── property
  ├── bean registry
  ├── web application
  └── other conditions
          │
          ▼
Bean definitions registered
          │
          ▼
Bean instances created
```

Spring Boot can also generate `spring-autoconfigure-metadata.properties` via an annotation processor to filter out auto-configurations that cannot match early. This helps reduce startup processing work.

Optimization metadata does not replace the imports file. The two files serve two different stages:

- Imports answers: **which auto-configurations are candidates?**
- Auto-configuration metadata helps answer early: **which candidates can be eliminated based on condition metadata?**

You do not need to write the optimization metadata file manually in most projects. When building an auto-configuration library, configure the annotation processor according to Spring Boot documentation if you want to generate metadata for startup optimization and IDE assistance.

## 19. Post-migration verification workflow for a library

When migrating from spring.factories to AutoConfiguration.imports, you can follow this sequence:

### Step 1 — List existing keys

Open `META-INF/spring.factories` and note every key. Only the `EnableAutoConfiguration` key moves to the auto-configuration imports mechanism under the Boot 3.0 change.

Keys such as `ApplicationListener`, `ApplicationContextInitializer`, `EnvironmentPostProcessor`, and `FailureAnalyzer` should be kept if the library still uses them.

### Step 2 — Create the imports resource at the exact path

Create:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line is one fully qualified class name.

### Step 3 — Update auto-configuration annotations

With a Boot 2.7+ baseline, use `@AutoConfiguration` for top-level auto-configuration classes. Keep `@Configuration` for imported or nested sub-configurations as usual.

### Step 4 — Choose a compatibility strategy

If supporting Boot 2.6 or earlier, keep the legacy entry in `spring.factories`. If supporting only Boot 3, use imports as the primary auto-configuration registration mechanism.

### Step 5 — Inspect the artifact

Use `jar --list` and JAR inspection tools to confirm the imports file is present, correctly named, at the right path, and contains all classes.

### Step 6 — Check resource merging

If producing a shaded/uber JAR, configure appending for imports resources and inspect the resulting file after merging.

### Step 7 — Run a starter-consuming application

Create a small application that only declares the starter dependency. Do not import auto-configurations manually. Start the context and confirm the beans appear under the expected conditions.

### Step 8 — Test across Boot versions

If the library commits to supporting multiple lines, run integration tests on every supported line. Do not infer compatibility merely from compiling cleanly on one version.

## 20. Practice exercises

### Exercise 1 — Reading a legacy spring.factories file

Create `META-INF/spring.factories` with the `EnableAutoConfiguration` key and an auto-configuration class. Run the project with Spring Boot 2.6 or a compatible version to observe the class being discovered.

### Exercise 2 — Migrating to imports

Create `AutoConfiguration.imports` with the same fully qualified class name. Run on Boot 2.7. Put the class in both files to observe the compatibility and deduplication behavior.

### Exercise 3 — Trying Boot 3

Run the same library on Boot 3.x. Temporarily remove the imports file while keeping the legacy key in `spring.factories`. Observe that the auto-configuration is no longer registered via that key. Restore imports and run again.

### Exercise 4 — Preserving other extension points

Add an `ApplicationListener` or `EnvironmentPostProcessor` to `spring.factories`. After migration, confirm that extension point still works while auto-configuration has moved to imports.

### Exercise 5 — Checking custom bean back-off

Create an auto-configuration with `@ConditionalOnMissingBean`. Run once without a custom bean and once with a custom bean. Observe when the default bean is registered.

### Exercise 6 — Testing resource merging

Create two test libraries, each with an imports file at the same path listing a different class. Build a shaded JAR without appending resources, then configure appending. Compare the final contents to see why resource merging matters.

### Exercise 7 — Classifying META-INF files

Given a library with `spring.factories`, `AutoConfiguration.imports`, `spring-autoconfigure-metadata.properties`, and `spring-configuration-metadata.json`. Explain each file's purpose and when it is used.

### Exercise 8 — Testing a compatibility matrix

Create starter-consuming applications on the Boot versions your library commits to supporting. Confirm:

- Auto-configuration is discovered.
- Other extension points are still loaded.
- Conditions work properly.
- Custom beans can replace default beans.
- Final artifacts preserve all metadata resources.

## 21. Official references

- [Spring Boot 2.7 Release Notes — Auto-configuration Registration](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.7-Release-Notes): `AutoConfiguration.imports` file introduced, compatibility with `spring.factories`, and deduplication.
- [Spring Boot 3.0 Migration Guide — Auto-configuration Files](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): removal of support for the `EnableAutoConfiguration` key in `spring.factories`; other keys unaffected.
- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): path, imports format, ordering, and conventions for writing auto-configuration.
- [Spring Boot Reference — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html): registering listeners via `spring.factories`.
- [Spring Boot How-to — Customize the Environment or ApplicationContext Before It Starts](https://docs.spring.io/spring-boot/how-to/application.html): registering `ApplicationContextInitializer` and `EnvironmentPostProcessor`.

The core point of this transition history is: **`spring.factories` used to be where auto-configurations were registered, Boot 2.7 introduced the dedicated imports file while maintaining compatibility, and Boot 3.0 moved auto-configuration registration entirely to `AutoConfiguration.imports`.** Other extension points can still use `spring.factories`. When upgrading or publishing a starter, inspect specific keys, supported Boot versions, and resource packaging to avoid losing auto-configurations.
