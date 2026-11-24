# Using the Static run Method and a Customized SpringApplication Instance

## Goal

In Spring Boot, the `org.springframework.boot.SpringApplication` class launches the application from the `main(String[] args)` method. There are two common ways to use it:

- **Static call:** `SpringApplication.run(RuntimeApplication.class, args)`. This is concise and suitable for most applications.
- **Instance creation:** `new SpringApplication(RuntimeApplication.class)`, configure the instance, and then call `application.run(args)`. This approach is suitable when you need to customize the startup process programmatically in Java.

Both approaches run Spring Boot's bootstrap mechanism. The primary difference is the ability to **configure options on the SpringApplication instance before calling run**; creating an instance does not mean reimplementing the Spring container yourself.

## 1. What Does SpringApplication Do?

When `run(...)` is called, Spring Boot uses the provided configuration sources (primary sources), prepares `Environment`, receives command-line arguments, selects the appropriate `ApplicationContext` type, loads configuration and beans, applies auto-configuration, refreshes the context, and then invokes `ApplicationRunner` and `CommandLineRunner` beans if present. When a web application is properly configured and has suitable web libraries, the startup process also creates an embedded web server.

`@SpringBootApplication` is typically placed on the startup class; this annotation combines Spring configuration, enables auto-configuration, and scans components starting from the package containing that class. Therefore, the main class should be placed in the root package of the application.

Distinguish between:

- **Static `run`** accepts the primary configuration class and `args`: `SpringApplication.run(RuntimeApplication.class, args)`.
- **Instance `run`** accepts `args` because the source class was already passed to the constructor: `application.run(args)`.
- Both return `ConfigurableApplicationContext`. You can use the context to access beans or close the application intentionally; do not close the context immediately after `run` if you want a web server to keep running.

## 2. Runnable Example: Calling the Static run Method

This example uses **Java 21, Spring Boot 3.3.13, and Gradle**. The project only uses `spring-boot-starter`, so it is an application without a web server; after running `CommandLineRunner`, the process can exit normally.

Directory structure:

~~~text
spring-application-run-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/runtime/RuntimeApplication.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'spring-application-run-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.runtime.RuntimeApplication'
}
~~~

File `src/main/java/com/example/runtime/RuntimeApplication.java`:

~~~java
package com.example.runtime;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class RuntimeApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuntimeApplication.class, args);
    }

    @Bean
    CommandLineRunner printMode(Environment environment) {
        return args -> System.out.println(
                "app.mode=" + environment.getProperty("app.mode", "basic"));
    }
}
~~~

Explanation:

1. `RuntimeApplication.class` is the primary configuration source that Spring Boot uses to locate configuration and beans. This parameter is **not** an object created with `new RuntimeApplication()`.
2. `args` passes program launch arguments into Spring Boot's processing mechanism. For example, the argument `--app.mode=from-cli` can become a property in `Environment`.
3. `@Bean` declares a `CommandLineRunner`; Spring Boot invokes the runner once the context has finished initializing.
4. `environment.getProperty("app.mode", "basic")` uses the value `basic` when the `app.mode` property is not set.

In the project directory, use an installed Gradle or the Gradle Wrapper (if the project has the wrapper files):

~~~bash
gradle bootRun
gradle bootRun --args="--app.mode=from-cli"
~~~

On Windows, when the Gradle Wrapper is present, you can replace `gradle` with `.\gradlew.bat`.

The line **printed by application code itself**, ignoring Spring Boot log lines that may differ across machines:

~~~text
app.mode=basic
~~~

With the second command, the line printed by the application is:

~~~text
app.mode=from-cli
~~~

This example does not use `spring-boot-starter-web`, so there is **no HTTP address or port 8080** to access. Add a web starter only when the problem genuinely requires a web application.

## 3. Customizing with a SpringApplication Instance

Keep `settings.gradle` and `build.gradle` unchanged. **Replace the entire contents** of `RuntimeApplication.java` with the version below:

~~~java
package com.example.runtime;

import java.util.Map;

import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class RuntimeApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(RuntimeApplication.class);

        application.setBannerMode(Banner.Mode.OFF);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setDefaultProperties(
                Map.<String, Object>of("app.mode", "custom-default"));
        application.setAdditionalProfiles("demo");

        application.run(args);
    }

    @Bean
    CommandLineRunner printMode(Environment environment) {
        return args -> System.out.println(
                "app.mode=" + environment.getProperty("app.mode", "basic"));
    }
}
~~~

Explanation of each configuration call:

| Call | Effect |
| --- | --- |
| `new SpringApplication(RuntimeApplication.class)` | Creates the bootstrap object with the same configuration source as the static example. |
| `setBannerMode(Banner.Mode.OFF)` | Turns off Spring Boot's ASCII banner. Does not mean turning off all logging. |
| `setWebApplicationType(WebApplicationType.NONE)` | Forces launching in non-web mode; does not create an embedded HTTP server even if web libraries are on the classpath. |
| `setDefaultProperties(...)` | Declares low-precedence default properties; configuration from higher-precedence sources, such as command-line arguments, can override them. |
| `setAdditionalProfiles("demo")` | Adds the `demo` profile to existing profiles, rather than replacing them completely. |
| `application.run(args)` | Starts bootstrapping using the settings just configured. |

Run again:

~~~bash
gradle bootRun
gradle bootRun --args="--app.mode=from-cli"
~~~

The corresponding line printed by `CommandLineRunner`:

~~~text
app.mode=custom-default
~~~

and when passing the argument:

~~~text
app.mode=from-cli
~~~

Thus `setDefaultProperties` sets a fallback value, while `--app.mode=from-cli` shows that command-line configuration can override default values. The `demo` profile only has an additional configuration effect when the application declares profile-scoped beans or has a file such as `application-demo.properties`.

**Note:** For the two commands above to use the intended version, keep only **one** version of `RuntimeApplication.java` at a time. The two example snippets illustrate two options for the same application, not a requirement to launch both contexts.

## 4. Static run or Customized Instance?

| Criterion | Static `SpringApplication.run(...)` | `new SpringApplication(...).run(...)` |
| --- | --- | --- |
| Steps in `main` | Few, easy to read | More steps due to pre-run configuration |
| Primary configuration source | Passed to `run` | Passed to the constructor |
| Spring Boot features | Bootstrap, auto-configuration, DI, runners | Same features |
| Java customization before bootstrap | No place to configure a dedicated instance in the shorthand call | Configure banner, application type, profiles, default properties, listeners, initializers... |
| Common use cases | REST API or service with standard configuration | Batch/CLI programs, custom launchers, or specialized startup configuration |

Using the static call **does not prevent** configuring Spring Boot via `application.properties`, `application.yml`, environment variables, or command-line arguments. Switch to the instance form only when you genuinely need to control bootstrap in code.

Several other useful options on the `SpringApplication` instance:

- `setLogStartupInfo(false)`: turns off startup info logged by SpringApplication, without turning off all application or error logs.
- `setLazyInitialization(true)`: defers initialization of many beans until first use; can reduce startup time but causes configuration errors to surface later.
- `addInitializers(...)` and `addListeners(...)`: integrates context initialization logic and lifecycle event listening. Use only when you have a specific need and understand when the callbacks are invoked.

If you want to configure a hierarchy of contexts or prefer a fluent syntax, Spring Boot also provides `SpringApplicationBuilder`. This is an additional tool, not a required step for the two launch styles above.

## 5. Common Mistakes and How to Check

**1. Forgetting args**

~~~java
SpringApplication.run(RuntimeApplication.class);
~~~

This call can start the application, but it does not pass `String[] args` from `main`. When you need to support `--spring.profiles.active=dev` or other options passed by the caller, use `SpringApplication.run(RuntimeApplication.class, args)` or `application.run(args)`.

**2. Passing wrong arguments to the instance run method**

~~~java
SpringApplication app = new SpringApplication(RuntimeApplication.class);
app.run(args); // Correct: the source was already supplied when creating app.
~~~

Do not confuse `app.run(args)` with the signature of the static `run` method.

**3. Accidentally creating two ApplicationContexts**

~~~java
SpringApplication.run(RuntimeApplication.class, args);
new SpringApplication(RuntimeApplication.class).run(args);
~~~

This performs **two startups**, not an "enhancement" of the first one. It can result in creating beans twice, running runners twice, or HTTP port conflicts. Choose **one** of the two approaches for a single launch.

**4. Thinking turning off the banner turns off logging**

`Banner.Mode.OFF` only disables the banner. If you need to adjust logs, use appropriate logging configuration. Do not suppress startup errors just to shorten the output.

**5. Enabling non-web for an application that needs HTTP**

`WebApplicationType.NONE` is suitable for CLI/batch. For a REST API using Spring MVC or WebFlux, let Spring Boot infer the application type from the classpath or choose a compatible type; if set to `NONE`, the HTTP server will not start.

**6. Ignoring configuration precedence**

`setDefaultProperties` does not lock values. Try both commands in the example to verify precedence yourself. Avoid treating default properties as a place to store secrets; sensitive information belongs in an appropriate configuration/secret management mechanism.

**7. Closing the context too early**

If you keep the return value of `run`, e.g., `ConfigurableApplicationContext context = application.run(args)`, do not call `context.close()` right afterward in a web application that needs to serve requests. Closing the context intentionally is more suitable for CLI tools or short-lived tasks.

## 6. Hands-On Practice

1. Run the static version; verify the runner prints `app.mode=basic`.
2. Pass `--app.mode=from-cli`; explain why the runner sees the new value.
3. Switch to the instance version; verify the banner disappears and the default value is `custom-default`.
4. Try passing `--app.mode=from-cli` to the instance version; verify that the default property can be overridden.
5. If building a REST API later, remove `WebApplicationType.NONE` and add the appropriate web starter; verify the server is started by the web context.

**Takeaway:** `SpringApplication.run(Main.class, args)` is the common shorthand; `new SpringApplication(Main.class)` + configuration + `run(args)` is used when explicit bootstrap control is needed. Both follow the same Spring Boot launch lifecycle.

## References

- Spring Boot 3.3.13 Reference — SpringApplication: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 API — SpringApplication: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
