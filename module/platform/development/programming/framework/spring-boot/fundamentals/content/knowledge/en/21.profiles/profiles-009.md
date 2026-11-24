# Distinguishing Spring profiles from build tool profiles or tasks

In a Spring Boot project, the word **profile** can appear in Spring Framework, Maven, and Gradle. They are often given similar names like `dev`, `test`, or `prod`, yet they do not share the same meaning. A **Spring profile** determines which configurations and beans are used when the ApplicationContext initializes; a **Maven profile** alters Maven's build model; and a **Gradle task** specifies the build or run work that Gradle executes.

Confusing these three concepts can lead to situations where a build command succeeds yet the application still connects to the wrong environment, or a JAR packaged supposedly for production runs with default configuration when deployed.

## 1. Three different questions: what to build, what to run, which configuration?

Distinguish the questions:

- **Build tool:** do we need to compile, test, package, or publish an artifact? Do dependencies or build behavior need to change?
- **Spring profile:** when the application runs, which beans and application configurations should be activated?
- **Deployment environment:** where is the process running, and with which environment variables, configuration files, and secrets?

For example, a service can:

1. Use Maven or Gradle to produce `catalog-service.jar`.
2. Deploy that exact same JAR to staging and production.
3. Launch staging with Spring profile `staging`.
4. Launch production with Spring profile `prod`.

There is no need to build a separate JAR for every Spring profile if the packaged logic and dependencies remain identical. This approach keeps artifacts immutable and makes releases easier to verify.

### Quick comparison table

| Concept | System | When it takes effect | Primary purpose |
|---|---|---|---|
| Spring profile | Spring Framework / Spring Boot | When creating the ApplicationContext | Select beans, `@Profile` conditions, profile-specific config files |
| Maven profile | Maven | When Maven builds the effective POM and runs lifecycle | Select properties, dependencies, plugins, build settings per POM config |
| Gradle task | Gradle | When running a build or task command | Perform tasks such as `test`, `bootJar`, `bootRun`, `publish` |
| Gradle project property (`-P`) | Gradle | When evaluating and executing the build script | Supply input values to the build script; takes effect only if the script uses it |
| Gradle `--profile` | Gradle | When running a Gradle build | Generates a build performance profiling report, not a Spring profile |

Matching names are merely conventions chosen by a project. Spring does not automatically read an enabled Maven profile or a Gradle task name to decide `spring.profiles.active`.

## 2. What do Spring profiles control?

A Spring profile is a logical configuration group. Spring uses active profiles to decide which beans with `@Profile` conditions are registered, and Spring Boot uses them when selecting profile-specific Config Data.

For example, an application has two implementations of `NotificationGateway`:

~~~java
public interface NotificationGateway {
    void send(String message);
}
~~~

Implementation for the development environment:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("dev")
public class LoggingNotificationGateway implements NotificationGateway {

    @Override
    public void send(String message) {
        System.out.println("DEV notification: " + message);
    }
}
~~~

Implementation for production:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("prod")
public class HttpNotificationGateway implements NotificationGateway {

    @Override
    public void send(String message) {
        // Send via configured notification service.
    }
}
~~~

When the `dev` profile is active, Spring considers registering `LoggingNotificationGateway`. With the `prod` profile, Spring considers `HttpNotificationGateway`.

`@Profile` is merely a bean registration condition, not a build execution mechanism. If both profiles are activated simultaneously, both implementations can coexist and lead to multiple candidates for interface-based injection. Design profile combinations, `@Primary`, `@Qualifier`, or explicit conditions according to requirements.

### File configuration per Spring profile

In `src/main/resources`, you can place:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
~~~

Shared file:

~~~yaml
spring:
  application:
    name: notification-service

app:
  notifications:
    timeout: 5s
~~~

`application-dev.yml`:

~~~yaml
app:
  notifications:
    endpoint: http://localhost:8081
    timeout: 1s
~~~

`application-prod.yml`:

~~~yaml
app:
  notifications:
    endpoint: https://notifications.example.test
    timeout: 3s
~~~

When Spring profile `prod` is activated, Spring Boot loads the corresponding profile-specific configuration document according to Config Data precedence order. Unoverridden properties can continue coming from `application.yml` and other configuration sources.

`application-prod.yml` **is not automatically activated** just because the build used an argument named `prod`. Spring Boot must receive the active profile during startup.

## 3. How to activate a Spring profile when running the application

Spring Boot provides several ways to supply `spring.profiles.active`. This is a property of the **running application**, not a command for selecting build configuration.

### Spring Boot command-line argument

After packaging the JAR:

~~~bash
java -jar build/libs/notification-service.jar --spring.profiles.active=dev
~~~

With Maven, the artifact location is usually `target/`:

~~~bash
java -jar target/notification-service.jar --spring.profiles.active=prod
~~~

The actual JAR filename depends on build configuration. What matters is that `--spring.profiles.active=prod` is passed after the JAR name, so Spring Boot reads it as an application argument.

### Environment variable

On Linux/macOS:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar notification-service.jar
~~~

In Windows PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar notification-service.jar
~~~

The `SPRING_PROFILES_ACTIVE` variable maps to the `spring.profiles.active` property via externalized configuration.

### Java system property

You can pass a JVM system property using `-D` **before** `-jar`:

~~~bash
java -Dspring.profiles.active=prod -jar notification-service.jar
~~~

Difference between the two forms:

~~~text
java -Dspring.profiles.active=prod -jar app.jar
java -jar app.jar --spring.profiles.active=prod
~~~

The first line uses a JVM system property; the second line uses a Spring Boot command-line property. Both can activate a Spring profile, yet belong to different configuration sources and follow separate precedence rules.

### Choosing a default profile

You can specify a value when no profile has been activated:

~~~yaml
spring:
  profiles:
    default: local
~~~

The `spring.profiles.default` value specifies the default profile set used when there is no active profile. If not explicitly configured, Spring uses a default profile named `default`.

The default profile does not mean every environment is `local`; it is simply a fallback chosen by the project. Verify its intent before using a default profile for integrations that have real side effects.

## 4. Maven profiles: altering how Maven builds

A Maven profile is part of the POM used to select or adjust build configuration such as properties, dependencies, plugin configuration, and Maven-supported build elements.

Example POM declaring a `ci` profile to set a property for the build process:

~~~xml
<project>
    <!-- Standard POM configuration sections -->

    <profiles>
        <profile>
            <id>ci</id>
            <properties>
                <build.channel>continuous-integration</build.channel>
            </properties>
        </profile>
    </profiles>
</project>
~~~

Activating that profile:

~~~bash
mvn -Pci package
~~~

When Maven builds the effective POM, it folds valid configurations from the `ci` Maven profile into the build model. In the example above, the `build.channel` property only makes a real difference if another part of the build consumes it; an arbitrary property does not automatically alter Java code or runtime environments.

Note:

- `-Pci` is a **Maven** parameter, not `spring.profiles.active`.
- `package` is a phase of the Maven lifecycle.
- Maven profiles can be activated via `-P`, POM activation conditions, or appropriate Maven settings.
- Naming a Maven profile `prod` carries no special meaning to Spring Boot unless the project explicitly writes configuration linking them.

For example:

~~~bash
mvn -Pprod package
~~~

This command tells Maven to use the build profile named `prod` if that profile is declared and successfully activated. It is **not** automatically equivalent to:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

An artifact built using Maven profile `prod` can still run with Spring profile `dev`, `test`, or no active profile, unless the build intentionally altered packaged resources or other logic.

### Maven profiles can alter the artifact

A Maven profile can change dependencies, build properties, resource filtering, or plugin executions. If a project decides to use Maven profiles to package distinct files per environment, the output JAR can differ.

That is a **build configuration decision**, not the nature of Spring profiles. This approach can be useful for genuinely distinct product variants, but makes it harder to verify a single artifact usable across every environment.

If the need is only changing endpoints, timeouts, or deployment details, it is usually better to keep the artifact identical and pass Spring properties at launch instead of using Maven profiles to bake environment values into the JAR.

## 5. Gradle tasks: performing work, not auto-selecting Spring profiles

Gradle organizes builds around **tasks**. A Spring Boot project typically has related tasks such as:

| Task | Role |
|---|---|
| `compileJava` | Compile Java source |
| `test` | Run tests per Gradle configuration |
| `bootJar` | Package an executable Spring Boot JAR |
| `bootRun` | Run the application using Gradle |
| `build` | Execute the build lifecycle per task dependencies |
| `publish` | Publish artifacts when an appropriate publishing plugin is configured |

For example:

~~~bash
./gradlew test
./gradlew bootJar
./gradlew bootRun
~~~

These commands ask Gradle to run the corresponding task. A task name by itself does not specify an active Spring profile.

`bootJar` **packages the application**; it does not run the application under any Spring profile. `bootRun` **runs the application**; in that case a Spring profile can be supplied as an argument or in the launched process's environment.

### Running bootRun with a Spring profile

Gradle supports passing application arguments to `bootRun`:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=dev'
~~~

On Windows PowerShell, you can use:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
~~~

Here:

- `bootRun` is the Gradle task.
- `--args` is the Gradle option used to pass arguments to the Java application executed by the task.
- `--spring.profiles.active=dev` is the argument Spring Boot receives to activate the Spring profile.

If you want to build a JAR and then run production, those are two independent steps:

~~~bash
./gradlew bootJar
java -jar build/libs/notification-service.jar --spring.profiles.active=prod
~~~

The JAR path is illustrative; use the exact filename produced by `bootJar`.

## 6. Gradle -P is not a Spring profile

Gradle has the `-P` option to supply a **project property** to the build script:

~~~bash
./gradlew -PtargetEnv=prod bootJar
~~~

The value `targetEnv=prod` belongs to Gradle. It only takes effect if `build.gradle` or `build.gradle.kts` reads that property and uses it in build logic.

Example in Gradle Kotlin DSL reading a project property to display build information:

~~~kotlin
val targetEnv = providers.gradleProperty("targetEnv")
    .orElse("unspecified")

tasks.register("printTargetEnvironment") {
    doLast {
        println("Build target: " + targetEnv.get())
    }
}
~~~

Run:

~~~bash
./gradlew -PtargetEnv=prod printTargetEnvironment
~~~

Output may be:

~~~text
Build target: prod
~~~

This remains solely a value inside the **Gradle build script**. No Spring ApplicationContext is created by this illustrative task, so no Spring profile is activated.

### Watch out for Gradle --profile

Gradle also has an option:

~~~bash
./gradlew build --profile
~~~

Here `--profile` is used to generate a profiling report for the Gradle build process. It is not equivalent to `spring.profiles.active` and does not mean activating a Spring profile named `build`.

Therefore, avoid saying simply "profile" in team discussions without clarifying whether you mean Spring or the build tool.

## 7. Maven spring-boot:run and Spring profiles

The Spring Boot Maven Plugin supports the `spring-boot:run` goal, allowing you to run the application during development.

You can pass profiles using the user property dedicated to the plugin:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=dev
~~~

In this command:

- `spring-boot:run` is a goal of the Spring Boot Maven Plugin.
- `-Dspring-boot.run.profiles=dev` is the property configuring the run goal.
- The plugin passes `dev` into the execution so Spring Boot activates the matching Spring profile.

This command **differs** from `mvn -Pdev spring-boot:run`. Unless Maven profile `dev` has dedicated configuration bound to the run goal, it does not automatically activate `dev` in Spring.

This example shows that a build tool **can be configured to forward profiles when running**, yet that mechanism must be explicit. It is not an automatic link merely because two profiles share the same name.

### Why should -D in Maven and java -D not be treated as identical?

The `-D` syntax is used by both Maven and the JVM, yet the parameter is received by different processes.

~~~text
mvn -Dsome.property=value ...
java -Dsome.property=value -jar ...
~~~

The first line sets a Maven user property. The second line sets a JVM system property for the running Java process. Do not assume every Maven `-Dspring.profiles.active=...` automatically reaches the application JVM, especially when plugins fork processes or have separate argument configurations.

When using `spring-boot:run`, pass properties supported by the plugin or configure the plugin explicitly, then confirm the active profile in the application logs.

## 8. Can build profiles and Spring profiles share the same name?

Yes, though you should understand they occupy **two separate semantic namespaces**.

For example, a project might have:

- Maven profile `prod`: selects build configuration suitable for the release pipeline.
- Spring profile `prod`: selects beans and Config Data when the JVM runs in the production environment.

Both configurations can coexist:

~~~bash
mvn -Pprod package
java -jar target/notification-service.jar --spring.profiles.active=prod
~~~

The first command selects the Maven build profile. The second command selects the Spring runtime profile.

Sharing names is not required. A clearer organization might be:

- Maven profiles: `ci`, `release`, `integration-tests`.
- Gradle tasks: `test`, `bootJar`, `integrationTest`, `publish`.
- Spring profiles: `local`, `staging`, `prod`.

Naming based on **purpose** reduces the risk of confusion. Build profiles describe how artifacts are built; Spring profiles describe how the application operates.

## 9. Common scenario: running tests with the Spring test profile

Running the Gradle `test` task or Maven `test` phase does not mean the Spring `test` profile is automatically activated.

~~~bash
./gradlew test
mvn test
~~~

Both commands instruct the build tool to execute tests. Inside a Spring Boot test, you can select profiles using the `@ActiveProfiles` annotation:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class NotificationServiceTests {

    @Autowired
    Environment environment;

    @Test
    void testProfileIsActive() {
        assertThat(environment.acceptsProfiles(
                org.springframework.core.env.Profiles.of("test")
        )).isTrue();
    }
}
~~~

`@ActiveProfiles("test")` belongs to Spring Test. It controls active profiles for the ApplicationContext built in that test; Gradle and Maven are only responsible for executing the test classes per build configuration.

You can add `application-test.yml` in `src/test/resources` to configure test-specific settings. When using `@ActiveProfiles("test")`, Spring Boot can load Config Data for this profile for the test context.

In projects with multiple test suites, decide profiles at the test or test-configuration level instead of assuming a build task name acts as a Spring profile. For instance, an `integrationTest` task does not automatically make all its tests use a Spring profile named `integrationTest`.

## 10. Active profiles and property sources outside the build tool

When an application launches, Spring Boot resolves `spring.profiles.active` from configuration sources such as:

- Command-line arguments: `--spring.profiles.active=prod`.
- Environment variables: `SPRING_PROFILES_ACTIVE=prod`.
- JVM system properties: `-Dspring.profiles.active=prod`.
- Properties in `application.yml` outside profile-specific documents.
- Programmatic configuration via `SpringApplication` or `Environment` at the appropriate phase.

If multiple sources set a value, Spring applies property source precedence.

For example, `application.yml` contains:

~~~yaml
spring:
  profiles:
    active: dev
~~~

Yet the process runs with:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Command-line arguments have higher precedence than file configuration under standard rules, so `prod` is selected. This is a runtime decision, unrelated to which Maven profile or Gradle task built the JAR.

### Do not put spring.profiles.active in profile-specific files

Do not configure `spring.profiles.active` in `application-prod.yml` or in a YAML document activated by `spring.config.activate.on-profile`. Spring Boot restricts profile-activation properties to non-profile-specific configuration documents to prevent circularities or unpredictable results.

For example, use:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

instead of placing `spring.profiles.active: prod` inside `application-prod.yml` itself.

### Multiple profiles simultaneously

Spring supports multiple active profiles, for example:

~~~bash
java -jar app.jar --spring.profiles.active=prod,metrics
~~~

Beans and configuration files are activated according to those profiles, subject to Spring Boot combination and precedence rules. If two profiles provide beans of the same type or conflicting configurations, design explicit conditions and precedence.

Do not turn profiles into a complete replacement for typed configuration. When changes are just URLs, timeouts, or toggling a single feature, properties are usually simpler than creating more profiles.

## 11. When do you need to build different artifacts?

There are cases where changes genuinely need to happen at build time, such as:

- Building multiple products with different dependencies.
- Creating distributions for different platforms or runtimes.
- Using distinct toolchains or compiler options.
- Running only a subset of tests, generating docs, or publishing artifacts.
- Deliberately using resource processing to embed build metadata into the artifact.

In those cases, Maven profiles or Gradle tasks/properties are appropriate. However, do not use build-time configuration to conceal a decision that really belongs at runtime.

For example, if staging and production share the same Java code and differ only in endpoints, credentials, and limits, use the same JAR and supply those values via externalized configuration.

Deployment diagram:

~~~text
Source code + build.gradle / pom.xml
                |
                v
       Maven package / Gradle bootJar
                |
                v
        notification-service.jar
                |
         +------+------+
         |             |
         v             v
      Staging       Production
         |             |
         v             v
SPRING_PROFILES_  SPRING_PROFILES_
ACTIVE=staging    ACTIVE=prod
         |             |
         v             v
Spring context    Spring context
for staging       for production
~~~

The artifact is identical, yet the ApplicationContext can have different beans and configuration values at launch.

## 12. Distinguishing commonly confused commands

| Command | Direct effect |
|---|---|
| `mvn -Pprod package` | Activates Maven profile `prod` while running the `package` phase |
| `mvn spring-boot:run -Dspring-boot.run.profiles=prod` | Runs the app via the Maven plugin with Spring profile `prod` |
| `./gradlew -PtargetEnv=prod bootJar` | Passes Gradle property `targetEnv` to the build; runs task `bootJar` |
| `./gradlew bootRun --args='--spring.profiles.active=prod'` | Runs the app with Gradle using Spring profile `prod` |
| `./gradlew build --profile` | Runs the build and enables Gradle's performance profiling report |
| `java -jar app.jar --spring.profiles.active=prod` | Runs the JAR with Spring profile `prod` |
| `SPRING_PROFILES_ACTIVE=prod java -jar app.jar` | Passes an environment variable to the Java process in a supporting shell |
| `java -Dspring.profiles.active=prod -jar app.jar` | Runs the JVM with a system property activating Spring profile `prod` |

From the table, you can see the exact same string `prod` plays very different roles depending on where it appears in the command.

## 13. Common mistakes

### Building with -Pprod and assuming Spring enabled prod

`mvn -Pprod package` only activates a Maven build profile, if declared. `./gradlew -PtargetEnv=prod bootJar` only creates a Gradle project property that the build script may use. Neither sets `spring.profiles.active` automatically.

Inspect the JAR launch command, process environment variables, and effective Spring configuration.

### Packaging application-prod.yml yet the app still reads default

`application-prod.yml` may already be inside the JAR, but Spring does not activate `prod` automatically just because the file exists. An active Spring profile `prod` or Config Data activation mechanism is required.

### Treating the test task as the Spring test profile

Gradle task `test` and Maven phase `test` only execute tests. To use the `test` Spring profile inside a test's ApplicationContext, use `@ActiveProfiles("test")` or configure the context appropriately.

### Using profiles to hold secrets in source code

Do not commit `application-prod.yml` containing real credentials or production-specific tokens. Spring profiles only select configuration; they do not protect secrets. Secrets must be supplied via the deployment environment's secret management and appropriate access controls.

### Using Maven profiles to produce a separate artifact per endpoint

If only runtime values differ, this approach usually complicates artifact management. Keeping artifacts immutable and using externalized configuration outside the JAR is generally easier to control.

### Believing active profiles cannot be overridden

A classpath file can set default or active profiles, yet higher-precedence command-line arguments, environment variables, or system properties can override them. When an application uses the wrong profile, inspect all property sources rather than just reading `application.yml`.

### Not checking beans under multiple active profiles

If both `dev` and `prod` are activated while two classes implement the same interface, the application can hit ambiguous dependency errors or unintended behavior. Validate allowed profile combinations and write clear conditional configurations.

## 14. Process for picking the right mechanism

When receiving a request saying "we need a profile for environment X", clarify the nature of the change:

1. If you need to swap beans or load `application-{profile}.yml` when the ApplicationContext is created, use a **Spring profile**.
2. If you need to change compiler settings, dependencies, plugins, or packaging behavior, use a **Maven profile** or corresponding build configuration.
3. If you need to choose build/test/run work, use a **Gradle task** or Maven lifecycle goal/phase.
4. If the build script needs parameters, use Gradle `-P` or Maven properties/profiles per build tool mechanics.
5. If only endpoints, timeouts, or feature flags change per environment, consider **externalized configuration** rather than producing a different build artifact.
6. If you want to launch the app directly via Maven/Gradle with a Spring profile, pass the application run arguments in the way supported by the plugin/task.
7. When deploying a JAR, verify `SPRING_PROFILES_ACTIVE`, `spring.profiles.active`, and external config files actually received by the JVM.
8. For tests, select the context's Spring profile using Spring Test mechanisms and verify that the intended profile is active.

Key takeaway: **Spring profiles select ApplicationContext configuration; Maven profiles select build configuration; Gradle tasks select build or run work.** These mechanisms can work together, yet they are never linked automatically simply by sharing names like `dev` or `prod`. Separating build-time and runtime decisions makes a Spring Boot project easier to deploy, test, and diagnose.
