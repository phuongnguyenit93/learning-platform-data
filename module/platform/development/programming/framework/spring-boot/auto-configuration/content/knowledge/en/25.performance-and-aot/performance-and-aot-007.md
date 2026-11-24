# Limitations on Changing Properties That Affect Bean Presence After AOT

## 1. Problem: Why Does Changing a Property at Runtime Not Make a Bean Appear or Disappear?

In a standard Spring Boot application, the container reads the classpath and Environment at startup. Conditions such as `@ConditionalOnProperty`, `@Profile`, `@ConditionalOnClass`, and `@ConditionalOnBean` are evaluated during ApplicationContext creation. Consequently, two startups with different properties can produce two different sets of beans.

Spring AOT changes the timing of this decision. During the build phase, Spring analyzes the ApplicationContext, processes configurations, and evaluates conditions to generate code that initializes bean definitions. When running an AOT-processed application, the generated code restores the bean structure decided at build time.

**Consequence:** properties affecting whether a bean is registered must already have the right values when AOT runs. If a bean was included in the bean graph at build time, changing the property to false at runtime does not remove the bean. If a bean was excluded at build time, changing the property to true at runtime does not create a new bean either.

This applies to native images as well as JVM applications using generated AOT code. It does not mean every property is fixed. Properties that only configure an already-registered bean can still receive values from the Environment when the application runs.

This lesson uses Spring Boot 3.3.x, Spring Framework 6.1, and Java 17+ to distinguish the two property groups, configure Maven/Gradle AOT, test behavior on a standard JVM, and demonstrate the limitation with two AOT builds.

## 2. What Does AOT Decide at Build Time?

AOT (Ahead-of-Time) analyzes the ApplicationContext during the build and generates resources that help start the application with less dynamic work. Spring Boot requires this step when turning a Spring ApplicationContext into a GraalVM Native Image; generated AOT code can also be run on the JVM to verify before building a native executable.

During AOT processing, Spring processes configurations and creates the required bean definitions. Conditions are evaluated in the build environment. Bean definitions failing conditions are excluded from the generated structure.

You can visualize it as:

```text
Build classpath + build Environment
              |
              v
       Parse configuration
              |
              v
    Evaluate @Conditional rules
              |
       +------+------+
       |             |
    condition      condition
      match        no-match
       |             |
       v             v
 keep bean       discard bean
 definition      definition
       |             |
       +------+------+
              |
              v
     Generate AOT code
              |
              v
      Package application
              |
              v
       Run AOT artifact
              |
              v
   Restore the build-time bean graph
```

Spring Framework describes the classpath as fixed at build time and bean definitions as unable to change arbitrarily at runtime. Environment properties affecting bean presence via conditions are considered only at build time. Profiles are subject to this same constraint because `@Profile` is implemented using conditions.

### 2.1. Decisions Commonly Fixed

| Mechanism | Example | Impact in AOT |
| --- | --- | --- |
| `@ConditionalOnProperty` | `feature.enabled=true` | Decides whether the bean/configuration enters the bean graph |
| `@Profile` | `@Profile("production")` | Profile must be selected when running AOT |
| `@ConditionalOnClass` | An SDK class is on the classpath | Classpath must be determined at build time |
| `@ConditionalOnBean` | Prerequisite bean exists | Decision based on bean definitions during AOT |
| `@ConditionalOnMissingBean` | No application-provided bean yet | Back-off is decided during AOT |
| Custom `Condition` reading Environment | Checks property or profile | Condition result is computed at build time |

It is not only `@ConditionalOnProperty` that is affected. Any condition deciding bean presence must be accounted for. If a custom condition reads `Environment` and returns true/false, the value it reads also belongs to the AOT environment.

### 2.2. Example with @ConditionalOnProperty

```java
@Configuration(proxyBeanMethods = false)
class FeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.feature",
            name = "enabled",
            havingValue = "true")
    FeatureClient featureClient() {
        return new FeatureClient();
    }
}
```

If `acme.feature.enabled=true` during AOT, `FeatureClient` is retained. When the AOT application runs with:

```bash
java -Dspring.aot.enabled=true -jar app.jar --acme.feature.enabled=false
```

the bean remains present because the registration decision was generated at build time.

If AOT ran with `acme.feature.enabled=false`, the bean is excluded. Switching to true at runtime cannot add a bean definition that AOT code never generated.

### 2.3. Profiles Are Conditions Too

Example:

```java
@Configuration(proxyBeanMethods = false)
@Profile("production")
class ProductionFeatureConfiguration {

    @Bean
    ProductionFeature productionFeature() {
        return new ProductionFeature();
    }
}
```

If the `production` profile is enabled during AOT processing, the production configuration enters the bean graph. When running AOT, this profile is kept according to the generated decision. If you need profile variants with different bean graphs, build a separate AOT artifact for each variant.

Do not confuse selecting a profile with reading ordinary properties. A profile can contain both bean-configuring properties and properties that only alter values on existing beans. The second set of properties can still vary across runtime environments.

## 3. Distinguishing Bean-Presence Properties from Bean-Configuring Properties

This is the most important distinction when designing AOT applications.

### 3.1. Properties Affecting Bean Presence

Example:

```properties
acme.feature.enabled=true
```

This property is used in `@ConditionalOnProperty`. It decides whether `FeatureClient` is registered. Therefore its value must be set in the environment used for AOT processing.

Similar forms:

- `acme.kafka.enabled` decides whether to create Kafka integration beans.
- `acme.storage.type` decides which configuration is selected conditionally.
- `spring.profiles.active` decides which `@Profile` configurations are considered.
- Properties read by a custom `Condition` to register an optional bean.

These values must match the deployment variant the artifact is built to serve.

### 3.2. Properties That Only Configure an Existing Bean

Example:

```properties
acme.feature.endpoint=https://api.example.test
acme.feature.timeout=3s
acme.feature.max-connections=20
```

If `FeatureClient` is always registered and the properties above are only bound into `@ConfigurationProperties` to configure endpoint, timeout, and connection pool, the values can be supplied by the Environment when the application runs.

Example:

```java
@ConfigurationProperties("acme.feature")
public record FeatureProperties(
        URI endpoint,
        Duration timeout,
        int maxConnections) {
}
```

`@ConfigurationProperties` describes configuration data for a bean. As long as these fields do not participate in conditions deciding bean presence, they are not frozen the way `@ConditionalOnProperty` is.

Distinguish "runtime configuration" from "hot reload." Values can differ between deployments/startups. Modifying the Environment after the application is already running does not automatically rebind every `@ConfigurationProperties` bean; hot refresh requires a separate refresh/rebinding mechanism.

### 3.3. Decision Table

| Property Usage | Example | Can It Change Across AOT Runs? |
| --- | --- | :---: |
| Input to `@ConditionalOnProperty` | `feature.enabled` | Cannot change bean presence of an AOT artifact |
| Read by a custom `Condition` | `feature.mode` inside condition | Cannot change bean presence |
| Selecting `@Profile` with different configuration beans | `production` / `development` | Profiles affecting bean graph must be chosen at build time |
| Bound to a field of an existing bean | `feature.timeout` | Yes |
| Passed into constructor to configure a retained bean | `feature.endpoint` | Yes |
| Read in a method to choose behavior of an always-present bean | `feature.strategy` | Yes, per Environment value bound/read at runtime |
| Adding classes/dependencies to classpath after build | New SDK present only at deployment | No; classpath is already fixed |

A property can be both bound into `@ConfigurationProperties` and used in a condition. In that case, the property's **bean-presence decision** is fixed, even though the property value may still exist in the runtime Environment. Do not infer that every read of the property is replaced by a build-time constant; what is fixed is the bean-structure decision.

## 4. Why Does AOT Need a Stable Bean Graph?

In standard Spring startup, the framework can read the classpath, parse configurations, evaluate conditions, and register bean definitions against the current Environment.

AOT performs most of this structural work earlier. Generated code restores the prepared bean factory state. If an application could arbitrarily add/remove beans based on runtime properties, the generated initialization code would no longer describe the analyzed structure.

Therefore:

- The classpath must be complete and fixed at build time.
- Conditional configurations must be evaluated in the accurate build Environment.
- Bean definitions cannot arbitrarily change by runtime profiles/properties.
- Do not rely on adding new dependencies or classes after a native image has been built.
- Custom registrations must use bean-definition registration mechanisms that AOT can process.

Spring Framework also notes that certain registration forms cannot be converted directly to AOT, such as bean definitions whose instance supplier is a lambda/method reference or singletons registered via `registerSingleton`. If programmatic bean registration is needed, consider `BeanDefinitionRegistry`, `BeanDefinitionRegistryPostProcessor`, or `ImportBeanDefinitionRegistrar` compatible with the AOT lifecycle.

## 5. Designing AOT-Friendly Feature Toggles

If a feature needs to be toggled per deployment without changing the bean graph, keep the bean always present and move the flag into the bean's logic. Do not use conditions to create/remove beans when the value must remain flexible after build.

### 5.1. Design Unsuitable When Runtime Toggling Is Needed

```java
@Bean
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true")
AuditPublisher auditPublisher() {
    return new AuditPublisher();
}
```

This approach works when you want to build distinct AOT artifacts for different deployment variants. It is unsuitable if the same AOT artifact needs to toggle the bean via a runtime property.

### 5.2. Keeping the Bean Always Present, Varying Behavior

```java
@ConfigurationProperties("acme.audit")
public record AuditProperties(
        boolean enabled,
        URI endpoint) {
}

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(AuditProperties.class)
class AuditConfiguration {

    @Bean
    AuditPublisher auditPublisher(AuditProperties properties) {
        return new AuditPublisher(properties);
    }
}

final class AuditPublisher {

    private final AuditProperties properties;

    AuditPublisher(AuditProperties properties) {
        this.properties = properties;
    }

    void publish(AuditEvent event) {
        if (!this.properties.enabled()) {
            return;
        }

        // Send event to configured endpoint.
    }
}
```

In this design, `AuditPublisher` is always in the bean graph. The `enabled` value is bound at runtime and decides method behavior. When changing the property between two deployments, the bean still exists yet can operate or no-op according to configuration.

This is a behavior-level feature toggle. If you need to strip dependencies, endpoints, security integrations, or entire beans out of an artifact to shrink footprint, build a separate AOT artifact rather than expecting a runtime property to alter the bean graph.

### 5.3. Choosing Between One Artifact and Multiple Artifacts

| Need | Design |
| --- | --- |
| Same bean always present, varying only endpoint/timeout/strategy | One AOT artifact; configuration properties read at runtime |
| Feature always has a bean yet can no-op via runtime flag | One AOT artifact; toggle lives inside bean logic |
| Feature genuinely needs bean present or absent | Build a separate AOT artifact per variant |
| Profile changes configuration/bean set | Select profile in AOT build; create separate builds when other profiles are needed |
| Dependencies/classpath differ across deployments | Build separate artifacts with the corresponding classpath |
| Want application to change bean graph freely at runtime | Use standard Spring startup mode; do not rely on a generated AOT bean graph |

## 6. Choosing the Right Environment for AOT Processing

Conditions must be evaluated in a build environment representative of the deployment the artifact will serve. Determine beforehand:

- Which profiles must be active?
- Which properties decide whether auto-configurations are applied?
- Which optional dependencies must be on the classpath?
- Which application-supplied beans cause auto-configurations to back off?
- Are any properties read by a custom `Condition`?
- Do deployment variants share the same bean graph or require separate artifacts?

If you build AOT locally with default properties while production requires a different condition, the artifact may hold the wrong bean graph for production. Do not expect runtime environment variables or a config server to add beans that were excluded at build time.

### 6.1. Maven: Configuring process-aot

The Spring Boot Maven Plugin provides the `process-aot` goal. The POM example below passes the feature property to the ApplicationContext created during AOT processing:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <id>process-aot</id>
                    <phase>process-classes</phase>
                    <goals>
                        <goal>process-aot</goal>
                    </goals>
                    <configuration>
                        <arguments>
                            <argument>--acme.feature.enabled=true</argument>
                        </arguments>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

`arguments` are the application arguments used during AOT processing. Additional build-time properties can be passed per the application's contract.

The Maven plugin also supports `profiles` to select Spring profiles for AOT processing. Example profile configuration:

```xml
<configuration>
    <profiles>production,cloud</profiles>
</configuration>
```

When using `spring-boot-starter-parent`, Spring Boot provides the `native` Maven profile to automatically configure the `process-aot` execution when the plugin is applied. That profile also configures the corresponding native build steps. If you only want to demonstrate AOT-generated initialization on the JVM, you can configure the `process-aot` goal as in the first example and package the JAR without running the native-image compiler.

### 6.2. Gradle: Configuring ProcessAot

With Gradle, pass application arguments to the `ProcessAot` task:

```groovy
tasks.withType(
    org.springframework.boot.gradle.tasks.aot.ProcessAot
).configureEach {
    args('--acme.feature.enabled=true')
    args('--spring.profiles.active=production,cloud')
}
```

Pass only the properties/profiles genuinely needed for the bean graph. These values will be used when conditions are evaluated during the build.

### 6.3. Separating Build Variants

If an application needs one artifact with the feature and one without, create two builds with different AOT inputs:

```text
AOT build: acme.feature.enabled=true
              |
              v
      FeatureClient included
              |
              v
       Artifact variant ON

AOT build: acme.feature.enabled=false
              |
              v
      FeatureClient excluded
              |
              v
       Artifact variant OFF
```

Name/tag artifacts or images clearly by variant to avoid accidental deployment mix-ups. Do not overwrite both variants to the same artifact path in the pipeline.

## 7. Runnable Example: Proving Bean Presence Is Fixed

This example uses Spring Boot 3.3.13, Java 17, and Maven. We create a conditional bean, then:

1. Verify normal behavior using `ApplicationContextRunner`.
2. Build AOT with property true, run on the JVM with property false.
3. Build AOT with property false, run on the JVM with property true.
4. Compare bean presence to observe that runtime properties do not reverse build decisions.

### 7.1. Project Structure

```text
aot-condition-lab/
├── pom.xml
└── src/
    ├── main/java/demo/aot/
    │   ├── AotConditionLabApplication.java
    │   ├── FeatureConfiguration.java
    │   └── FeatureMarker.java
    └── test/java/demo/aot/
        └── RuntimeConditionTest.java
```

### 7.2. POM

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>aot-condition-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <executions>
                    <execution>
                        <id>process-aot</id>
                        <phase>process-classes</phase>
                        <goals>
                            <goal>process-aot</goal>
                        </goals>
                        <configuration>
                            <arguments>
                                <argument>--acme.feature.enabled=true</argument>
                            </arguments>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

On the first build, AOT receives `acme.feature.enabled=true`. To test the OFF variant, change that exact argument to false, re-run `clean package`, and use the new JAR.

### 7.3. Conditionally Registered Bean

File `FeatureMarker.java`:

```java
package demo.aot;

public record FeatureMarker(String source) {
}
```

File `FeatureConfiguration.java`:

```java
package demo.aot;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.feature",
            name = "enabled",
            havingValue = "true")
    FeatureMarker featureMarker() {
        return new FeatureMarker("conditional-bean");
    }
}
```

File `AotConditionLabApplication.java`:

```java
package demo.aot;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.beans.factory.ObjectProvider;

@SpringBootApplication
@Import(FeatureConfiguration.class)
public class AotConditionLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(AotConditionLabApplication.class, args);
    }

    @Bean
    CommandLineRunner reportFeaturePresence(
            ObjectProvider<FeatureMarker> featureProvider) {

        return args -> System.out.println(
                "featurePresent=" + (featureProvider.getIfAvailable() != null));
    }
}
```

`ObjectProvider` allows checking whether the bean exists without requiring it to be present. When the feature is excluded at build time, the application still starts and prints `featurePresent=false`.

### 7.4. Testing Standard Behavior Before AOT

File `RuntimeConditionTest.java`:

```java
package demo.aot;

import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

class RuntimeConditionTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(FeatureConfiguration.class);

    @Test
    void propertyTrueRegistersFeatureBean() {
        runner.withPropertyValues("acme.feature.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(FeatureMarker.class);
                });
    }

    @Test
    void propertyFalseDoesNotRegisterFeatureBean() {
        runner.withPropertyValues("acme.feature.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(FeatureMarker.class);
                });
    }
}
```

The two tests prove that in a standard context, the same configuration can yield different outcomes depending on the startup property. This is the expected behavior before AOT fixes the bean graph.

The import `org.springframework.context.annotation.Import` is unnecessary in the test above; you can remove that import if your IDE reports an unused import.

### 7.5. Running Standard JVM Tests

From the project directory:

```bash
mvn clean test
```

Expected output:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Detailed summary lines may vary by Surefire version, yet both tests must pass.

### 7.6. Build AOT with Feature ON

Keep the POM argument:

```xml
<argument>--acme.feature.enabled=true</argument>
```

Build the JAR:

```bash
mvn clean package
```

Run the JAR on the JVM while instructing it to use AOT-generated initialization:

```bash
java -Dspring.aot.enabled=true -jar target/aot-condition-lab-1.0.0.jar --acme.feature.enabled=false
```

Expected output:

```text
featurePresent=true
```

The runtime value is false, yet the bean was retained when AOT processing ran with true.

### 7.7. Build AOT with Feature OFF

Edit the argument in the POM to:

```xml
<argument>--acme.feature.enabled=false</argument>
```

Then run a clean build:

```bash
mvn clean package
```

Run with runtime property true:

```bash
java -Dspring.aot.enabled=true -jar target/aot-condition-lab-1.0.0.jar --acme.feature.enabled=true
```

Expected output:

```text
featurePresent=false
```

The bean is not created even though the runtime property is true, because the AOT build excluded the bean from the bean graph.

### 7.8. Results of Both Variants

| Value During AOT | Value at Runtime | Bean Present? | Reason |
| --- | --- | :---: | --- |
| true | true | Yes | Bean retained at build time |
| true | false | Yes | Runtime does not remove generated bean |
| false | false | No | Bean excluded at build time |
| false | true | No | Runtime does not add excluded bean definition |

This is the key experiment of the lesson. It runs generated AOT code on the JVM without waiting for the native-image compiler. When packaging a native image, AOT is mandatory and the same bean-presence limitation still applies.

## 8. Testing AOT on JVM and Testing Native Image

It is not necessary to build a native image for every test run. Use multiple layers:

### 8.1. Standard Unit Tests

Use `ApplicationContextRunner` to verify conditions in standard runtime mode. These tests are fast, easy to run in the IDE, and verify feature ON/OFF by property.

### 8.2. AOT Processing Test

Run Maven goal `process-aot` or Gradle task `ProcessAot`. This step verifies the application can be analyzed and initialization code generated with the intended build Environment.

### 8.3. Running AOT Code on the JVM

Once the JAR contains AOT code, run:

```bash
java -Dspring.aot.enabled=true -jar target/aot-condition-lab-1.0.0.jar
```

This tests generated initialization without waiting for native image compilation. Ensure the artifact was actually built with AOT; otherwise, the standard JVM uses the normal runtime initialization flow.

### 8.4. Native Image Smoke Test

When confirming GraalVM, build the native image and run the executable. Native image uses AOT code automatically. Keep unit/integration tests on the JVM for most logic to shorten feedback cycles; reserve native smoke tests for areas where differences arise such as reflection, resources, serialization, dynamic proxies, and runtime hints.

A successful AOT step does not guarantee a native image will build cleanly. Runtime hints for reflection/resources/proxies and native compiler constraints are a separate verification layer from property conditions.

## 9. Common Design and Diagnostic Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Changed `feature.enabled=false` yet bean still exists | Bean was retained when AOT ran with true | Rebuild with property false |
| Changed `feature.enabled=true` yet bean does not appear | Bean was excluded when AOT ran with false | Rebuild with property true |
| Runtime profile does not load configuration with new bean | Profile affects conditions yet was not selected during AOT | Set profile in process-aot or build separate artifact |
| Local AOT works yet production misses a bean | Build Environment does not represent production | Align build-time properties/profiles with deployment |
| Added SDK at runtime yet auto-configuration does not appear | Classpath was fixed at build time | Add dependency before AOT and rebuild |
| Bean always exists even when feature is off | Bean was not excluded by condition; flag only configures behavior | Clarify whether this is a behavior toggle or true bean presence |
| Unit tests pass yet AOT app differs | Unit tests run standard context | Add AOT build/run smoke tests |
| AOT build fails on dynamic bean registration | Registration path unsupported by AOT | Use compatible BeanDefinitionRegistry/ImportBeanDefinitionRegistrar |
| Native image missing class/resource | Missing runtime hints or unrecognized resource | Add RuntimeHints and native integration tests |
| Test output stays unchanged after editing property because old JAR ran | Artifact was not cleaned/rebuilt | Run clean package and verify the right JAR |

### 9.1. Do Not Use Conditions for a Feature Toggle That Must Change at Runtime

If you want the same artifact deployed across environments while only toggling audit sending, metrics emission, or an integration, consider registering an always-present bean and letting the bean decide behavior from runtime properties.

Use conditions only when bean presence is genuinely an architectural decision fixed for the artifact, such as adapter type, server type, or integrations with separate dependencies.

### 9.2. Do Not Treat Every Property as a Build-Time Constant

AOT does not freeze all of `application.properties`. Properties that only configure endpoints, timeouts, pool sizes, logging levels, or business values of existing beans can still be bound at runtime.

Trace where the property is used:

- If it feeds into a condition, the bean-presence outcome is locked at build time.
- If it only goes into constructors/methods of an existing bean, values can come from the runtime Environment.
- If custom code reads the Environment directly to register bean definitions, ensure that registration runs during the AOT phase using compatible registry APIs.

## 10. Checklist Before Releasing an AOT Application

**Bean graph and conditions**

- [ ] Listed all `@ConditionalOnProperty`, `@Profile`, and custom `Condition` implementations.
- [ ] Identified conditions based on classpath, bean presence, and properties.
- [ ] Determined build-time values for every property affecting bean presence.
- [ ] Selected required profiles when running `process-aot`.
- [ ] Verified `@ConditionalOnMissingBean` does not back off unexpectedly.
- [ ] Avoided expecting runtime properties to add/remove beans after AOT.

**Runtime configuration**

- [ ] Properties that only configure existing beans still bind from runtime Environment.
- [ ] Did not confuse property binding with hot reload.
- [ ] Flexible feature toggles live inside the logic of always-present beans.
- [ ] When bean graphs differ, the pipeline produces separate AOT artifacts.

**Build and verification**

- [ ] Maven/Gradle ran the right AOT task.
- [ ] Build inputs (arguments, profiles, system properties) are recorded in the pipeline.
- [ ] Ran unit tests for standard runtime contexts.
- [ ] Ran the AOT-generated JAR on the JVM with `spring.aot.enabled=true`.
- [ ] Tested at least one runtime property opposite to the AOT value to confirm fixed bean presence.
- [ ] Cleaned before building another AOT variant.
- [ ] Ran native smoke tests when releasing a GraalVM image.
- [ ] Runtime hints for reflection/resources/proxies were verified separately.

**Takeaway:** AOT fixes the bean structure according to the build-time classpath and Environment. Properties driving `@Conditional` and profiles deciding bean presence cannot add/remove beans in the same artifact after build. Properties that only configure already-present beans can still vary with the runtime Environment. If behavior needs to change, keep the bean and use a runtime feature flag; if the bean graph needs to change, build a separate AOT artifact per variant.

## Official References

- Spring Boot 3.3.13 — Ahead-of-Time Processing and `process-aot` goal, `arguments`/`profiles` parameters: https://docs.spring.io/spring-boot/3.3/maven-plugin/aot.html
- Spring Boot 3.3 — Ahead-of-Time Processing With the JVM: https://docs.spring.io/spring-boot/3.3/reference/packaging/aot.html
- Spring Boot 3.3 — Testing GraalVM Native Images and running AOT code on the JVM: https://docs.spring.io/spring-boot/3.3/how-to/native-image/testing-native-applications.html
- Spring Framework — Ahead of Time Optimizations, fixed classpath, and condition/property constraints: https://docs.spring.io/spring-framework/reference/core/aot.html
