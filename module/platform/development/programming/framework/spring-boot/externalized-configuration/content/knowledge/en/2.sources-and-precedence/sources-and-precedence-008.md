# Test Property Sources and DevTools Global Settings

## 1. Why Do These Two Configuration Types Matter?

A Spring Boot application can obtain values from configuration files, environment variables, Java system properties, and command-line arguments. When running **tests** or developing locally on a personal machine, Spring Boot also adds sources with very specific purposes:

- **Test property sources** let each test class configure the data, endpoints, timeouts, or service ports it needs without modifying production operational config.
- **Spring Boot DevTools global settings** let a developer apply shared local development preferences across Spring Boot applications that have DevTools active on the same machine.

Both participate in **Spring Environment**, where **PropertySource** instances are ordered by precedence. When multiple sources define the same key, the application receives the value from the highest-precedence source at the time that value is resolved.

For example: **app.service-url** in **application.yml** points to a development environment API. An integration test can replace that key with the URL of a mock server or container started by the test itself. Meanwhile, customizing **spring.devtools.restart.trigger-file** in the user's home directory serves a personal development workflow and can apply across multiple projects.

**Distinction needed:** changing a test's configuration does not mean editing production runtime configuration; DevTools settings on a developer's machine are also not deployment configuration for the artifact.

## 2. Where Do Test Sources Sit in Precedence Order?

The **Spring Boot 3.3 — Externalized Configuration** documentation lists PropertySources from lowest to highest precedence. Here is the relevant excerpt for this lesson:

| Source | Role | Scope Notes |
| --- | --- | --- |
| **application.properties / application.yml**, including profile files | Base application values | Belongs to Config Data; can be overridden by appropriate external sources |
| **Environment variables** | Configuration supplied by the OS or deployment platform | Higher than standard Config Data files |
| **Java system properties** | Values supplied to the JVM | Typically written with the **-D** option |
| **Command-line arguments** | Keys supplied at application startup | E.g., **--app.message=hello** |
| **@SpringBootTest `properties`** or test slice | Direct values for tests | Only affects that test's ApplicationContext |
| **@DynamicPropertySource** | Values dynamically registered by tests | Useful when a resource's port or address is only known after startup |
| **@TestPropertySource** | Test-specific files or inline values | Used to set intentional configuration at the test-class level |
| **DevTools global settings** | Global settings for apps with DevTools active | Present when DevTools actually participates in running the app |

These are **the relevant sources extracted** from Spring Boot's list; the full list also includes default properties, **@PropertySource**, **random.***, JNDI, servlet init parameters, and **SPRING_APPLICATION_JSON**.

One detail to get right: the Spring Boot 3.3 documentation lists **@DynamicPropertySource** and **@TestPropertySource** in adjacent positions, while **Spring TestContext** documentation notes that dynamic properties can override test properties. Because these mechanisms have different registration lifecycles, **you should not have the same key compete across both annotations simultaneously to build test logic**. If you need to verify a specific case, inspect the actual order and values in the running test's **ConfigurableEnvironment**.

More important than memorizing a chart is placing values at **the right scope**: defaults in files, test-specific values in tests, runtime-generated test values via dynamic sources, and personal development habits via DevTools global settings.

## 3. Baseline Example: A Property in the Application

Assume the project uses Spring Boot 3.3, Java 21, and **spring-boot-starter-test**. In **src/main/resources/application.yml**, declare:

~~~yaml
app:
  message: "from-application"
  remote-url: "https://dev-api.example.invalid"
~~~

A bean can read both values from **Environment**:

~~~java
package com.example.config;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class MessageReader {
    private final Environment environment;

    public MessageReader(Environment environment) {
        this.environment = environment;
    }

    public String message() {
        return environment.getProperty("app.message");
    }

    public String remoteUrl() {
        return environment.getProperty("app.remote-url");
    }
}
~~~

In a normal application run, **message()** returns **from-application** if no higher-precedence configuration source overrides it. In tests, we will replace that value without editing the application's YAML file.

## 4. @SpringBootTest(properties): Inline Values for a Test

**@SpringBootTest** boots Spring Boot's ApplicationContext. Its **properties** attribute lets you directly supply keys to override for the test's context:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
    "app.message=from-spring-boot-test",
    "app.remote-url=http://localhost:9999"
})
class InlineConfigurationTest {

    @Autowired
    MessageReader reader;

    @Test
    void usesInlineTestProperties() {
        assertEquals("from-spring-boot-test", reader.message());
        assertEquals("http://localhost:9999", reader.remoteUrl());
    }
}
~~~

**Explanation:**

1. **application.yml** still holds the original values.
2. When the test starts, Spring Boot adds **@SpringBootTest(properties=...)**'s property source into the test's Environment.
3. Matching keys resolve from the test source, so assertions receive the inline values.
4. When running the JAR normally, test annotations are not used to configure production.

This mechanism suits **a few fixed properties**, such as disabling scheduling in tests, changing a timeout, or swapping a test endpoint. If many test classes share a common set of settings, consider a dedicated test file rather than repeating many strings across annotations.

Test slice annotations such as **@WebMvcTest** also have a **properties** attribute; they use an ApplicationContext scoped to that slice. There is no need to boot the full application when testing only a single web layer.

## 5. @TestPropertySource: Dedicated Test Property Sources

**@TestPropertySource** comes from the Spring TestContext Framework. It lets you declare:

- **locations**: **.properties** files on the classpath or supported resource locations.
- **properties**: key–value pairs written directly on the annotation.

Suppose you create **src/test/resources/config/lesson-test.properties**:

~~~properties
app.message=from-test-file
app.remote-url=http://localhost:8089
~~~

Then use it in a test:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@TestPropertySource(locations = "classpath:config/lesson-test.properties")
class FileConfigurationTest {

    @Autowired
    MessageReader reader;

    @Test
    void readsTestPropertyFile() {
        assertEquals("from-test-file", reader.message());
        assertEquals("http://localhost:8089", reader.remoteUrl());
    }
}
~~~

This result proves tests can swap configuration sources without editing **src/main/resources/application.yml**.

**Order within @TestPropertySource:** if the same key is declared in both a file under **locations** and the inline **properties** list, the inline value takes higher precedence. For example:

~~~java
@SpringBootTest
@TestPropertySource(
    locations = "classpath:config/lesson-test.properties",
    properties = "app.message=from-inline-test-property"
)
class OverrideInsideTestPropertySourceTest {
    // For key app.message, the inline property beats the file above.
}
~~~

**Note on YAML:** **@TestPropertySource** does not directly load YAML documents via **locations** under its default mechanism. Do not rename a file to **.yml** and assume it works the same way as **.properties**. If you want profile-based YAML files, use Spring Boot's Config Data mechanism together with **@ActiveProfiles**, covered in the next section.

**Note on context sharing:** Spring TestContext caches ApplicationContexts. Different test configurations can produce different context cache keys; avoid mutating global properties arbitrarily between tests and expecting a cached context to re-initialize itself.

## 6. How Do @ActiveProfiles("test") and application-test.yml Differ from @TestPropertySource?

A common way to organize tests is creating **src/test/resources/application-test.yml**:

~~~yaml
app:
  message: "from-test-profile"
  remote-url: "http://localhost:8088"
~~~

Activate the **test** profile:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("test")
class ProfileConfigurationTest {

    @Autowired
    MessageReader reader;

    @Test
    void readsProfileConfiguration() {
        assertEquals("from-test-profile", reader.message());
        assertEquals("http://localhost:8088", reader.remoteUrl());
    }
}
~~~

The difference lies in **loading mechanism and precedence level**:

| Configuration Approach | Loaded By What? | When to Use? |
| --- | --- | --- |
| **application-test.yml** + **@ActiveProfiles("test")** | Spring Boot's Config Data and profile system | A shared test suite configuration structured in YAML |
| **@TestPropertySource(locations=...)** | Spring TestContext | Want to directly add a properties file for a test class |
| **@TestPropertySource(properties=...)** | Spring TestContext | Want to override specific keys right on the test class |
| **@SpringBootTest(properties=...)** | Spring Boot test bootstrap | Want a few inline values for a Spring Boot test |
| **@DynamicPropertySource** | Spring TestContext with a supplier | Values unknown when writing the test, such as a container port |

**@ActiveProfiles** selects which profiles are active; it does not turn **application-test.yml** into a **@TestPropertySource** source. The profile file remains in the Config Data group, so an appropriate inline test value can override it.

The profile name **test** is a convention, not mandatory. Do not rely on **application-test.yml** merely existing to assume the profile is active; the test must actually select the profile through a valid mechanism.

## 7. @DynamicPropertySource: Values Generated at Test Runtime

Some values cannot be hardcoded in YAML:

- A randomly assigned port for a database container.
- The URL of a mock HTTP server started during the test.
- Host and port allocated by an integration test environment.
- Temporary access tokens created by a test fixture.

**@DynamicPropertySource** registers these keys with **DynamicPropertyRegistry**. The annotated method must be **static**, accept a single **DynamicPropertyRegistry** parameter, and register a **Supplier** for each property.

Example for an integration test using **Testcontainers** and PostgreSQL:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class DynamicDatabaseConfigurationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void registerDatabaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void contextStartsWithContainerDatabase() {
        // The app is configured to connect to the test container DB.
    }
}
~~~

This snippet assumes the project already has **Testcontainers**, the PostgreSQL JDBC driver, the appropriate Spring Data/JDBC dependencies, and Docker available for integration tests. It illustrates the configuration path; running successfully requires the project's actual datasource setup.

When the container gets a different port between runs, suppliers such as **postgres::getJdbcUrl** still provide the value matching the current run. Hardcoding that port in **application-test.yml** would risk failing tests or hitting the wrong resource.

**Choose the source based on the nature of the value:** static, shared keys can live in a test file; values produced at test runtime should come from **@DynamicPropertySource**. Avoid defining the same key across multiple annotations unless you have a specific override requirement.

## 8. What Are DevTools Global Settings?

**Spring Boot DevTools** is a module supporting development workflows, such as automatic application restarts when the classpath changes, LiveReload, and developer-friendly defaults. To include it in a Gradle project with the Spring Boot plugin, you typically add:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

When DevTools is active, Spring Boot 3.3 can read global configuration from the **$HOME/.config/spring-boot/** directory of the user running the application. Three filenames are supported:

- **spring-boot-devtools.properties**
- **spring-boot-devtools.yaml**
- **spring-boot-devtools.yml**

Choose whichever format fits best. There is no need to place that file in the project repository, nor to copy the same DevTools preferences across many **application.yml** files.

Example contents of **$HOME/.config/spring-boot/spring-boot-devtools.properties**:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
spring.devtools.livereload.enabled=false
~~~

Meaning:

- **spring.devtools.restart.trigger-file** selects the filename that triggers a restart check. The **.reloadtrigger** file must exist on the classpath, such as **src/main/resources/.reloadtrigger** in each project using that setting. Updating the trigger file causes a restart check when changes need processing.
- **spring.devtools.livereload.enabled=false** disables DevTools' LiveReload server if the developer does not use the corresponding browser refresh utility.

Equivalent YAML example:

~~~yaml
spring:
  devtools:
    restart:
      trigger-file: ".reloadtrigger"
    livereload:
      enabled: false
~~~

**Global** here means **on that machine and inside the user's home directory**, applying to applications using DevTools there. It is not a server-wide Spring Boot configuration file, not a network-shared config, and does not sync automatically to teammates' machines.

### Search Directory and Customization

By default **$HOME** is the user's home directory. You can customize the location using the **SPRING_DEVTOOLS_HOME** environment variable or the **spring.devtools.home** Java system property.

If no DevTools file is found in **$HOME/.config/spring-boot/**, Spring Boot 3.3 also checks the legacy **$HOME/.spring-boot-devtools.properties** file for backward compatibility with earlier versions. For new setups, use the **.config/spring-boot** path described in the current 3.3 documentation.

### Profile-Related Limitations

Global DevTools files **do not support profile-specific variants** like **spring-boot-devtools-prod.properties**. Nor do they support documents activated via **spring.config.activate.on-profile** inside the global file.

In particular, trying to set **spring.profiles.active** inside a global DevTools file is not a valid way to control loading **application-{profile}.yml**. Profiles must be selected through an appropriate, early-enough application configuration mechanism, such as the runtime environment, startup arguments, or test annotations.

## 9. Why Can Global DevTools Make a Value Appear "Overridden"?

In Spring Boot 3.3's PropertySource list, **DevTools global settings** sit at a high-precedence position when DevTools is active. That explains why a developer may see settings on their machine beat values seemingly declared in project files.

Example:

**In a project's application.yml:**

~~~yaml
spring:
  devtools:
    livereload:
      enabled: true
~~~

**In the developer's global DevTools file:**

~~~properties
spring.devtools.livereload.enabled=false
~~~

In a run where DevTools and global settings are actually active, the global configuration can dictate the effective value of this key. A teammate without that global file may observe different behavior, even from the exact same source checkout.

When encountering discrepancies across machines, inspect both project files **and the DevTools configuration in the home directory**. Do not edit source code or production files to "fix" a development preference that only exists on one machine.

**DevTools is not for production.** With Gradle's **developmentOnly** configuration, this dependency is excluded from the default executable JAR. Spring Boot also disables DevTools automatically in certain packaged runs such as **java -jar**. Do not try to enable DevTools in production to take advantage of a developer's global config file.

## 10. How to Determine Which Source Actually Supplies a Value

When a property has an unexpected value, looking only at **application.yml** is not enough. In a Spring test, you can inspect **ConfigurableEnvironment** to see which sources contain that key, in the order Environment uses.

Example in a test:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@SpringBootTest(properties = "app.message=from-inline-test")
class PropertySourceInspectionTest {

    @Autowired
    ConfigurableEnvironment environment;

    @Test
    void inspectMessageSource() {
        String key = "app.message";

        System.out.println("Resolved: " + environment.getProperty(key));

        for (PropertySource<?> source : environment.getPropertySources()) {
            Object localValue = source.getProperty(key);
            if (localValue != null) {
                System.out.println(source.getName() + " => " + localValue);
            }
        }
    }
}
~~~

**How to read the output:**

1. **getProperty(key)** shows the final resolved value.
2. **getPropertySources()** shows the sources in Environment's search order.
3. For a key present in multiple sources, the source checked first with a valid value usually decides the outcome.
4. Source names can depend on the Spring version and how the ApplicationContext was built; do not write production logic that depends on a specific internal source name.

Only use this printing snippet for **non-sensitive keys** like **app.message**. Never log passwords, tokens, or secret-bearing keys to debug precedence order.

If the project uses Spring Boot Actuator, the **env** endpoint can assist in investigating property sources when configured and secured properly. Avoid exposing this endpoint to unauthorized users; configuration data can be sensitive.

## 11. Common Pitfalls

**Confusing @ActiveProfiles with @TestPropertySource.** Profiles select the matching Config Data files; **@TestPropertySource** actively adds a Spring TestContext property source. Both mechanisms can be used together, but they are fundamentally different.

**Assuming @TestPropertySource reads YAML like application.yml.** By default, this annotation does not support loading YAML directly via **locations**. Use **.properties** with the annotation, or **application-test.yml** with a profile if you want YAML.

**Hardcoding ports for test containers.** Ports allocated by Docker can change. Use **@DynamicPropertySource** to register actual runtime endpoints so tests reflect the real resource in use.

**Scattering the same key across multiple annotations.** When the same key appears in **@SpringBootTest(properties)**, **@TestPropertySource**, and **@DynamicPropertySource**, tests become harder to understand. Choose one clear source per key, and trace via Environment when needed.

**Thinking the DevTools global file belongs to the repository.** It lives in each user's home directory and can affect multiple projects on that machine. A teammate being unable to reproduce an issue may stem from personal settings.

**Confusing global DevTools with production configuration.** DevTools serves development. Deployment environment configuration must be supplied by that environment's deployment mechanism, not by a DevTools file on a laptop.

**Trying to activate profiles from a global DevTools file.** These global files do not provide profile-specific mechanisms; instead use **@ActiveProfiles** for tests or an appropriate source supplying **spring.profiles.active** at application startup.

## 12. Hands-On Verification Exercises

**Exercise A — Overriding values from a test annotation**

1. Put **app.message=from-application** in **application.yml**.
2. Create a test with **@SpringBootTest(properties = "app.message=from-test")**.
3. Read the value via **Environment.getProperty("app.message")** and verify it is **from-test**.
4. Run the application normally to get **from-application** again when no other overrides are present.

**Exercise B — Separating test configuration into a file**

1. Create **src/test/resources/config/lesson-test.properties** with **app.message=from-file**.
2. Use **@TestPropertySource(locations = "classpath:config/lesson-test.properties")**.
3. Verify the value of **app.message** in the test.
4. Add **properties = "app.message=from-inline"** right inside that annotation and observe the new value.

**Exercise C — Using the test profile**

1. Create **src/test/resources/application-test.yml** with **app.message=from-profile**.
2. Activate **@ActiveProfiles("test")** on a **@SpringBootTest** class.
3. Verify **from-profile** is loaded from Config Data.
4. Try adding an inline value in **@SpringBootTest(properties)** and observe the override.

**Exercise D — Testing global DevTools**

1. Add the **spring-boot-devtools** dependency in the **developmentOnly** configuration.
2. Create **spring-boot-devtools.properties** inside **$HOME/.config/spring-boot/** containing **spring.devtools.livereload.enabled=false**.
3. Start the application in development mode with DevTools and verify the setting takes effect.
4. Temporarily change the value in the global file and restart to see local config affect the project.
5. Verify that doing this did not modify the project's **application.yml** or the contents of a built release JAR.

In these exercises, only change example keys; do not create real secrets and do not depend on production services.

## 13. Key Takeaways

- **Test properties** serve a single test run or test ApplicationContext; pick the annotation or test file based on need.
- **@SpringBootTest(properties)** fits small overrides, **@TestPropertySource** fits test resources/key pairs, and **@DynamicPropertySource** fits values generated when tests run.
- **@ActiveProfiles("test")** selects profile configuration; **application-test.yml** remains Config Data.
- **DevTools global settings** are user-level preferences on a development machine, active when DevTools runs, and do not support profile-specific mechanisms.
- When multiple values exist for the same key, **ConfigurableEnvironment** lets you trace origins and explain actual outcomes.

**Official References:**

- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Developer Tools, Global Settings: https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html
- Spring Framework — Test Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html
- Spring Framework — Dynamic Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
