# Providing a Minimal Consuming Application to Verify Auto-Discovery from Dependencies

## 1. Goal: Testing the Real Path of a Starter

A Spring Boot starter library may contain auto-configuration to register default beans for consuming applications. The mere existence of an auto-configuration class inside a JAR **does not prove** Spring Boot discovered and applied it.

A reliable way to verify this is creating **an independent consuming application**:

1. Build and install the starter JAR into the local Maven repository or publish it to an internal repository.
2. Declare the starter as a normal dependency in the consuming application.
3. Boot using only `@SpringBootApplication`; do not `@Import` the auto-configuration and do not component-scan the starter's packages.
4. Inject the bean provided by the starter.
5. Run an integration test or real application and verify the bean's behavior.

This lesson creates two separate Maven projects using **Java 17+ and Spring Boot 3.3.13**:

- `greeting-spring-boot-autoconfigure`: the library providing auto-configuration.
- `consumer-app`: a small application depending solely on the installed JAR and using the auto-discovered bean.

The consumer test is critical evidence: if the auto-configuration registration file is dropped from the JAR or the dependency is not resolved properly, the context will fail to create `GreetingService` and the test will fail.

## 2. Two-Project Layout

Create two sibling directories:

~~~text
auto-configuration-demo/
├── greeting-spring-boot-autoconfigure/
│   ├── pom.xml
│   └── src/
│       └── main/
│           ├── java/com/acme/greeting/
│           │   ├── GreetingProperties.java
│           │   ├── GreetingService.java
│           │   └── autoconfigure/GreetingAutoConfiguration.java
│           └── resources/
│               └── META-INF/spring/
│                   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── consumer-app/
    ├── pom.xml
    └── src/
        ├── main/
        │   ├── java/com/acme/consumer/ConsumerApplication.java
        │   └── resources/application.yml
        └── test/
            └── java/com/acme/consumer/GreetingAutoDiscoveryTests.java
~~~

The application package is `com.acme.consumer`, while the library sits in `com.acme.greeting`. `@SpringBootApplication`'s default component scan only scans the application package and its subpackages; it does not scan the starter's sibling package. Therefore, the `GreetingService` bean appearing in the consumer is proof of the auto-configuration discovery path.

## 3. Library Project: Declaring Auto-Configuration

### 3.1. Starter POM

File `greeting-spring-boot-autoconfigure/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>greeting-spring-boot-autoconfigure</artifactId>
    <version>1.0.0</version>
    <name>Greeting Spring Boot Auto-configuration</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>
    </dependencies>
</project>
~~~

The library needs `spring-boot-autoconfigure` for auto-configuration annotations and mechanisms. `spring-boot-configuration-processor` is optional, generating IDE metadata when using `@ConfigurationProperties`. If the starter requires third-party APIs or implementations, declare those dependencies and consider which ones should be optional.

### 3.2. Properties Configuration Class

File `src/main/java/com/acme/greeting/GreetingProperties.java`:

~~~java
package com.acme.greeting;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.greeting")
public class GreetingProperties {

    private String prefix = "Hello";

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
~~~

This class binds keys starting with `acme.greeting`. The default value `Hello` is used if `acme.greeting.prefix` is not set. Registering the properties class happens in the auto-configuration shown next.

### 3.3. Consumer-Facing API

File `src/main/java/com/acme/greeting/GreetingService.java`:

~~~java
package com.acme.greeting;

public class GreetingService {

    private final String prefix;

    public GreetingService(String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        return prefix + ", " + name + "!";
    }
}
~~~

This is a simple bean used as proof. The consuming application does not need to know which package implements the auto-configuration; it depends solely on the `GreetingService` API.

### 3.4. Auto-Configuration Creating the Default Bean

File `src/main/java/com/acme/greeting/autoconfigure/GreetingAutoConfiguration.java`:

~~~java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.GreetingProperties;
import com.acme.greeting.GreetingService;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(GreetingProperties.class)
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService(GreetingProperties properties) {
        return new GreetingService(properties.getPrefix());
    }
}
~~~

Three key parts:

- `@AutoConfiguration` marks the starter's auto-configuration class.
- `@ConditionalOnProperty` enables the feature when `acme.greeting.enabled=true`; if the property is missing, `matchIfMissing=true` enables it by default.
- `@ConditionalOnMissingBean(GreetingService.class)` creates the default bean only when the application has not already provided a compatible bean. If the consumer defines its own `GreetingService`, auto-configuration backs off.

`@EnableConfigurationProperties` registers `GreetingProperties` so Spring binds configuration. The `greetingService` method receives properties via dependency injection and creates the service.

### 3.5. Registering Auto-Configuration in the JAR

Create the exact file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

The file contains a single line:

~~~text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
~~~

This is the decisive step for auto-discovery in Spring Boot 3.3. Spring Boot reads the class list from this resource on the runtime classpath. The class name must be exact, including package and letter casing.

**Do not replace this file with component scanning.** The starter does not require consumers to scan `com.acme.greeting`. Consumers also do not need to write `@Import(GreetingAutoConfiguration.class)`; having to do so means the example no longer proves auto-discovery from the dependency.

Spring Boot 2.7+ and 3.x use `AutoConfiguration.imports` to register auto-configurations. The old registration mechanism via `spring.factories` is no longer the primary registration mechanism in Boot 3.

## 4. Building and Installing the Starter into the Local Maven Repository

Open a terminal in `auto-configuration-demo` and run:

~~~bash
mvn -f greeting-spring-boot-autoconfigure/pom.xml clean install
~~~

This command compiles, packages the JAR, and installs the artifact `com.acme:greeting-spring-boot-autoconfigure:1.0.0` into the local Maven repository, usually `~/.m2/repository`.

After building, verify the JAR contains the classes and imports file:

~~~bash
jar tf greeting-spring-boot-autoconfigure/target/greeting-spring-boot-autoconfigure-1.0.0.jar
~~~

The listing should include entries like:

~~~text
com/acme/greeting/GreetingProperties.class
com/acme/greeting/GreetingService.class
com/acme/greeting/autoconfigure/GreetingAutoConfiguration.class
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

If the imports file is missing from the JAR, check the resource path and Maven resource packaging. A file existing in the source tree under the wrong directory will not be read by Spring Boot when the consumer runs.

If using an internal repository instead of local Maven, publish the exact artifact/version to that repository and ensure the consumer configures that repository accordingly. Subsequent steps remain unchanged: the consumer simply declares a normal dependency.

## 5. Consumer Project: Declaring Only the Dependency

### 5.1. Consuming Application POM

File `consumer-app/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>consumer-app</artifactId>
    <version>1.0.0</version>
    <name>Minimal Auto-configuration Consumer</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>greeting-spring-boot-autoconfigure</artifactId>
            <version>1.0.0</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

The key dependency is `com.acme:greeting-spring-boot-autoconfigure:1.0.0`. The consumer does not declare `spring-boot-autoconfigure` directly, copy starter classes, or manually import the auto-configuration. Maven resolves the starter JAR from the local or published repository.

### 5.2. Minimal Spring Boot Application

File `consumer-app/src/main/java/com/acme/consumer/ConsumerApplication.java`:

~~~java
package com.acme.consumer;

import com.acme.greeting.GreetingService;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ConsumerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConsumerApplication.class, args);
    }

    @Bean
    ApplicationRunner greetingCheck(GreetingService greetingService) {
        return args -> System.out.println(
                "AUTO_DISCOVERY_OK: " + greetingService.greet("Ada"));
    }
}
~~~

This is the complete consuming application. Points to preserve during testing:

- Only `@SpringBootApplication`; no `@Import`.
- No `@ComponentScan("com.acme.greeting")` declaration.
- Root package is `com.acme.consumer`, separate from the starter package `com.acme.greeting`.
- `GreetingService` is injected into `ApplicationRunner`. If the starter is not discovered or conditions do not match, the context fails to create the bean and the application cannot start normally.

The runner prints a marker line to easily verify the application used the bean from the starter.

### 5.3. Consumer Properties

File `consumer-app/src/main/resources/application.yml`:

~~~yaml
acme:
  greeting:
    prefix: "Welcome"
~~~

`acme.greeting.enabled` is not declared. The starter uses `matchIfMissing=true`, so the feature is enabled by default. The `prefix` value binds to `GreetingProperties` and is passed to `GreetingService`.

When running, the expected application line is:

~~~text
AUTO_DISCOVERY_OK: Welcome, Ada!
~~~

Spring Boot may print its banner and startup logs before or after this line depending on logging configuration; the marker line printed by `ApplicationRunner` is fixed with the configuration above.

## 6. Consumer-Side Integration Test

Create file `consumer-app/src/test/java/com/acme/consumer/GreetingAutoDiscoveryTests.java`:

~~~java
package com.acme.consumer;

import com.acme.greeting.GreetingService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = ConsumerApplication.class)
class GreetingAutoDiscoveryTests {

    @Autowired
    ApplicationContext applicationContext;

    @Autowired
    GreetingService greetingService;

    @Test
    void starterBeanIsDiscoveredFromDependency() {
        assertThat(applicationContext.containsBean("greetingService"))
                .isTrue();

        assertThat(applicationContext.getBeansOfType(GreetingService.class))
                .hasSize(1);

        assertThat(greetingService.greet("Ada"))
                .isEqualTo("Welcome, Ada!");
    }
}
~~~

This test runs in the consumer project, where the starter is visible only as a dependency JAR. It does not load the configuration itself via `@Import`. Successfully injecting `GreetingService`, finding the bean by name, and verifying final behavior serve as integration proof that Spring Boot discovered the auto-configuration from the dependency.

Do not test `GreetingAutoConfiguration` only by importing it directly into `ApplicationContextRunner` and conclude auto-discovery is verified. That style of test is useful for checking condition logic in isolation, but it bypasses class registration from the `AutoConfiguration.imports` resource. An integration test in the consumer verifies the entire path: packaging → dependency resolution → auto-discovery → bean registration → injection.

Run tests from the consumer project:

~~~bash
mvn -f consumer-app/pom.xml clean verify
~~~

Expected result: `GreetingAutoDiscoveryTests` runs successfully with one passing test. If the test fails during injection, inspect the condition report and check the JAR rather than patching the consumer with a manual class import.

## 7. Running the Consuming Application Like a Real Library User

Once the starter is installed and the consumer is built:

~~~bash
mvn -f consumer-app/pom.xml spring-boot:run
~~~

Or package and run the JAR:

~~~bash
mvn -f consumer-app/pom.xml clean package
java -jar consumer-app/target/consumer-app-1.0.0.jar
~~~

Expected confirmation line:

~~~text
AUTO_DISCOVERY_OK: Welcome, Ada!
~~~

This is a smoke test through the real application startup path. It confirms the bean can be injected and used when the consumer runs, beyond the scope of a condition unit test.

You can check the resolved dependency:

~~~bash
mvn -f consumer-app/pom.xml dependency:tree -Dincludes=com.acme:greeting-spring-boot-autoconfigure
~~~

The output should show `com.acme:greeting-spring-boot-autoconfigure:jar:1.0.0` in the dependency tree. If Maven reports the artifact cannot be found, install the starter first or publish it to the repository the consumer uses.

## 8. Distinguishing Auto-Discovery, Component Scan, and `@Import`

| Mechanism | How does Spring find the class? | Does it prove starter auto-discovery? |
|---|---|---|
| `AutoConfiguration.imports` | Spring Boot reads auto-configuration names from the resource in a JAR on the classpath | **Yes** |
| `@ComponentScan` | Scans packages for components/configurations | No; can make beans appear even if the imports file is missing |
| `@Import(GreetingAutoConfiguration.class)` | Application references the configuration class directly | No; consumer is loading the configuration manually |
| `ApplicationContextRunner.withConfiguration(...)` | Test explicitly declares the auto-configuration under test | Does not itself prove discovery from a dependency |
| `@SpringBootTest` in consumer depending only on JAR | Boot starts the application and reads imports | **Yes**, if the consumer package does not scan the starter and does not import classes manually |

A good consumer test must intentionally **avoid** adding a broad component scan such as `@SpringBootApplication(scanBasePackages = "com.acme")`. Scanning `com.acme.greeting` as well could cause the bean to appear from component scanning or a scanned configuration, preventing the test from isolating the imports mechanism.

This is why the consumer and starter packages sit on two sibling branches. It exposes imports registration failures instead of letting component scanning hide them.

## 9. Verifying Conditions and Back-Off Scenarios

After the basic auto-discovery path succeeds, test starter behavior under conditions.

### 9.1. Disabling the Feature via Property

Run the consumer with:

~~~bash
mvn -f consumer-app/pom.xml spring-boot:run -Dspring-boot.run.arguments=--acme.greeting.enabled=false
~~~

Auto-configuration is disabled by `@ConditionalOnProperty`. In the current consumer there is no replacement user bean, so injecting `GreetingService` fails when constructing `ApplicationRunner`. This is expected behavior: the feature is disabled and no bean provides that dependency.

To test disabling via property without making the main application fail on a required bean, create a separate test context or use `ApplicationContextRunner` in the starter project. Do not conclude "auto-discovery is broken" merely because the user intentionally set the property disabling the feature.

### 9.2. Application Supplies Its Own Bean

If the consumer defines its own `GreetingService` bean, `@ConditionalOnMissingBean(GreetingService.class)` causes the default bean to back off once the user definition is processed before auto-configuration. This allows applications to swap implementations per the starter contract without matching bean names.

Custom configuration example in the consumer:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomGreetingConfiguration {

    @Bean
    GreetingService customGreetingService() {
        return new GreetingService("Hi");
    }
}
~~~

This is an extension example; if added to the consumer, the expected test output must change to `Hi, Ada!`. Do not keep asserting `Welcome, Ada!` when intentionally providing a replacement bean.

### 9.3. Inspecting Conditions with the Report

When a bean does not appear, run the consumer with `--debug`:

~~~bash
mvn -f consumer-app/pom.xml spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

The Condition Evaluation Report shows:

- Whether `GreetingAutoConfiguration` was processed.
- Whether `@ConditionalOnProperty` matched.
- Whether `@ConditionalOnMissingBean` backed off due to a user bean.
- Whether the auto-configuration was excluded.

If you need Actuator's `conditions` endpoint, expose it selectively and secure it with Spring Security/network policies; the report can disclose classpath and internal configuration structure. Do not expose diagnostic endpoints publicly just to verify a starter.

## 10. Common Mistakes When Verifying Auto-Discovery

### 10.1. JAR Lacks `AutoConfiguration.imports`

**Symptom:** the auto-configuration class exists in source or JAR, yet the report does not show it being processed.

**Cause:** the resource file is at the wrong path, misnamed, or not packaged.

**Check:** use `jar tf` to verify the `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` entry. Verify the class name in the file matches the compiled package/class.

### 10.2. Consumer Uses the Wrong Starter Version

**Symptom:** you modify the starter, yet the consumer still sees no change.

**Cause:** the local Maven repository or internal repository still holds an older artifact version, the consumer declares a different version, or dependency mediation picks another version.

**Fix:** build/install the right version, inspect `dependency:tree`, and verify the exact JAR resolved. In team environments, use explicit release/snapshot versioning workflows; do not rely on overwriting an already-published release version.

### 10.3. Component Scan Masks Imports Bugs

**Symptom:** the bean still appears even after deleting the imports file.

**Cause:** the consumer is scanning the starter package or using `@Import` directly.

**Fix:** restrict the consumer's scan packages and remove manual imports in auto-discovery tests. Keep sibling packages as in the example.

### 10.4. Class or Property Conditions Do Not Match

**Symptom:** auto-configuration is discovered, yet the bean method is not registered.

**Cause:** optional dependency absent from runtime classpath, property `false`, wrong key, or unintended `matchIfMissing`.

**Fix:** inspect the Condition Evaluation Report, effective properties, and dependency tree. Do not bypass conditions with `@Import`; doing so stops the test from verifying real behavior.

### 10.5. User Bean Causes Default Back-Off

**Symptom:** auto-configuration appears in the report, yet the default bean is absent.

**Cause:** `@ConditionalOnMissingBean` found an already-registered user bean.

**Assessment:** usually the intended behavior. Check which bean is injected instead of only counting default beans.

### 10.6. Tests Run Only Inside the Starter Module

**Symptom:** `ApplicationContextRunner` tests in the starter PASS, yet real consumers cannot find the bean.

**Cause:** starter tests import the auto-configuration directly, bypassing the imports file and dependency packaging.

**Fix:** keep a separate integration test in a consumer project depending on the installed starter JAR without manual auto-configuration imports.

### 10.7. Using Boot 2.x Registration in Boot 3.x

**Symptom:** older guides describe declaring auto-configuration in `spring.factories`, yet Boot 3.3 consumers do not discover the class.

**Cause:** using the legacy auto-configuration registration mechanism.

**Fix:** register the class in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. If the library must support multiple Boot generations, design compatible artifacts/versions and metadata intentionally instead of copying legacy files mechanically.

### 10.8. Consumer Fails to Resolve the Dependency

**Symptom:** Maven reports `Could not find artifact com.acme:...`.

**Cause:** the starter was not installed/published yet, versions mismatch, or the consumer uses a different repository.

**Fix:** run `mvn clean install` in the starter project first; then inspect `dependency:tree` in the consumer. In CI, publish the starter before building consumer integrations or use a multi-module reactor with explicit dependency ordering.

## 11. Completion Checklist

| Step | Required evidence | Done when |
|---|---|---|
| Build starter | Maven build succeeds | JAR of expected version exists |
| Package metadata | `jar tf` output | JAR contains `AutoConfiguration.imports` |
| Register class | Imports file content | Exact fully qualified class name |
| Resolve dependency | Maven dependency tree | Consumer resolves right artifact/version |
| Isolate component scan | Consumer packages and annotations | No starter scan, no `@Import` |
| Boot context | `@SpringBootTest` | Context starts and injects service |
| Verify behavior | Greeting assertion | Value `Welcome, Ada!` is exact |
| Run application | `ApplicationRunner` output | Line `AUTO_DISCOVERY_OK: Welcome, Ada!` appears |
| Verify conditions | Debug report when needed | Understand class/property/bean conditions |

Do not treat Maven compilation success alone as proof of auto-discovery. Compilation only proves the consumer can reference the API on the classpath; it does not prove Spring Boot read the imports resource or registered the bean.

## 12. Self-Check Questions

1. Why should a consumer test depend on the built/installed JAR instead of importing the auto-configuration class directly? **To test the full path of artifact packaging, dependency resolution, reading imports, and bean registration.**
2. Where does Boot 3.3's auto-configuration registration file live? **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**.
3. Does the consumer need `@Import(GreetingAutoConfiguration.class)`? **No.** Having to import manually does not prove auto-discovery.
4. Why are consumer and starter packages placed in two sibling branches? **So default component scanning does not scan the starter, avoiding masking imports file bugs.**
5. What does `@ConditionalOnProperty` `matchIfMissing=true` mean in the example? **If `acme.greeting.enabled` is omitted, the feature stays enabled.**
6. When the consumer defines its own `GreetingService`, what happens to the default bean? **`@ConditionalOnMissingBean` causes auto-configuration to back off if the user bean was processed beforehand.**
7. Does `ApplicationContextRunner` importing an auto-configuration directly prove the imports resource is read? **No.** An integration test in a consumer actually depending on the JAR is needed.
8. The JAR contains `GreetingAutoConfiguration` but lacks `AutoConfiguration.imports`. Will Spring Boot scan the entire JAR to find the class? **No.** The class must be registered via the auto-configuration mechanism.
9. Maven builds the starter successfully yet the consumer fails to resolve the artifact. What do you check? **Install/publish, version, repository, and `dependency:tree`.**
10. The condition report says the default bean backed off due to a user bean. Is that necessarily an error? **No.** Usually it is the starter's customization contract working properly.

## 13. Official References

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): registering auto-configuration, imports file, ordering, conditions, and testing.
- [Spring Boot 3.3 — AutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): annotation marking an auto-configuration.
- [Spring Boot 3.3 — ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): back-off behavior when a user bean already exists.
- [Spring Boot 3.3 — ConfigurationProperties API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html): binding external configuration onto properties beans.
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing): `ApplicationContextRunner` and testing auto-configuration conditions.
