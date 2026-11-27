# Context Initialized Multiple Times or Bootstrap Bean Accidentally Component-Scanned

When Spring Cloud is enabled, logs may show multiple ApplicationContexts being created, a configuration bean appearing in multiple places, or the application calling Config Server several times during startup. These signs look similar yet can stem from different mechanisms. You must determine whether it is an intentional context hierarchy, multi-stage configuration loading, or duplicate registration before changing dependencies or disabling bootstrap.

This lesson focuses on two common mistakes: confusing the bootstrap context with a second application startup, and placing a bootstrap configuration class inside a package scanned by the main application's component scan.

## 1. Distinguishing the Bootstrap Context from the Application Context

An ApplicationContext is the container managing beans, configuration, and lifecycles for part of a Spring application. An application can have multiple contexts within the same process. With Spring Cloud's traditional bootstrap mechanism, the context tree typically looks like:

~~~mermaid
flowchart TD
    B["Bootstrap context<br/>loads external configuration"]
    A["Main application context<br/>web, service, repository"]
    B -->|"parent"| A
~~~

The bootstrap context is a parent context created to load property sources from external sources and prepare required components before the main application context runs. A child context can look up beans in its parent context. If both contexts have a bean with the same name, the child context's local bean takes precedence when queried from the child context; the two beans still belong to two separate BeanFactories.

Therefore, seeing two contexts in the logs is not enough to conclude the application initialized twice. Check parent-child relationships and the purpose of each context. One bootstrap context plus one main context is a valid structure when an application enables the legacy bootstrap mechanism.

Spring Cloud allows registering bootstrap configuration classes via `META-INF/spring.factories` under the key `org.springframework.cloud.bootstrap.BootstrapConfiguration`. Those classes are used to build the bootstrap context. Beans declared there can be consumed by the main application context through the parent-child relationship.

## 2. Why Can a Bootstrap Bean Appear Twice?

### 2.1. Bootstrap Package Lies Inside Component Scan Scope

This is the first mistake to check when a configuration class is loaded via `BootstrapConfiguration` while simultaneously residing beneath the root package of the `@SpringBootApplication` class.

Confusing structure example:

~~~text
com.acme.orders
├── OrdersApplication.java
├── service/
└── bootstrap/
    └── RemoteBootstrapConfiguration.java
~~~

~~~java
package com.acme.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

`@SpringBootApplication` includes component scan behavior with the application class's package as the default root package. Because `RemoteBootstrapConfiguration` lies in `com.acme.orders.bootstrap`, the main context's component scan can discover it. Meanwhile, Spring Cloud also loads it into the bootstrap context via metadata. As a result, the same configuration class can create beans in both the parent context and the child context.

Consequences depend on the bean type and how the application looks them up:

- A bean may be instantiated in both contexts, causing constructors, `@PostConstruct`, or connection-opening logic to run multiple times.
- A same-named bean in the child context can shadow the same-named bean in the parent context when queried from the child context.
- If two configurations register the same bean within one BeanFactory, the application may hit duplicate bean definition errors; whether overriding is permitted depends on Spring Boot settings.
- Components intended to run only during bootstrap may be instantiated additionally during the main application lifecycle.

Not every bean appearing in both contexts is an error. Identify which beans belong in the bootstrap context, which belong in the main application, and which side effects are actually duplicated.

### 2.2. Application Intentionally Creates Multiple Contexts

Check all call sites of `SpringApplication.run` and `SpringApplicationBuilder`. The following situations can create multiple contexts:

- More than one entry point calls `SpringApplication.run` for the same application.
- A configuration manually constructs a new context instead of receiving beans from the current context.
- `SpringApplicationBuilder` declares parent, child, or sibling contexts to split the application into contexts with separate lifecycles.
- Tests launch multiple application contexts, or close and recreate contexts per test configuration.

Parent-child or sibling contexts can be valid designs. Only fix when context creation is unintentional or causes a resource to register multiple times.

### 2.3. Distinguishing Refresh from Restart

Spring Cloud Context provides configuration and bean refresh mechanisms. The `/actuator/refresh` endpoint can reload the bootstrap context and refresh `@RefreshScope` beans; this operation does not mean the entire main application context was recreated. The `/actuator/restart` endpoint closes and restarts the ApplicationContext and is disabled by default. If logs show refresh or restart, identify which endpoint or listener triggered that action before hunting for component scan bugs.

### 2.4. Multiple Config Requests Do Not Mean Multiple Context Initializations

Spring Boot Config Data can call Config Server in multiple steps. Spring Cloud Config documentation explains that the client first loads configuration with the default profile to discover activated profiles, then loads configuration for active profiles. Consequently, two or more config-fetching requests during startup can be normal behavior.

Since Spring Cloud 2022.0.3, `PropertySourceLocator` is also called twice following the profile workflow: first without profiles, and later after the main context starts with active profiles. This counts property source lookups, not proof that the entire application created two main contexts.

## 3. Ordered Inspection

### Step 1: Confirm Context Count and Parent-Child Relationships

Do not just count log lines containing “Starting”. Record the ID, class type, and parent of every context. You can use a diagnostic snippet in a test or temporary checkpoint:

~~~java
import org.springframework.context.ApplicationContext;

final class ContextDiagnostics {
    static void printContextHierarchy(ApplicationContext context) {
        ApplicationContext current = context;

        while (current != null) {
            ApplicationContext parent = current.getParent();
            String parentId = parent == null ? "<none>" : parent.getId();

            System.out.printf(
                "contextId=%s, type=%s, parentId=%s%n",
                current.getId(),
                current.getClass().getName(),
                parentId
            );

            current = parent;
        }
    }
}
~~~

If you see a bootstrap context as the parent of the main context, check whether the application intentionally enabled bootstrap. If you see multiple independent main contexts, locate calls to `SpringApplication.run`, `SpringApplicationBuilder`, or context creation in tests.

### Step 2: Find Bootstrap Configuration Registration Sources

Find all `BootstrapConfiguration` declarations in `META-INF/spring.factories` of the application and internal dependencies. For each declared class:

1. Identify the configuration class's package.
2. Identify the root package of `@SpringBootApplication` and any custom `scanBasePackages` or `@ComponentScan`.
3. Check whether the bootstrap class falls inside the main context's scan scope.
4. Check whether the class is also registered via `@Import` or another configuration.
5. Identify in which context beans are created and whether initialization has side effects.

You can enable detailed logging during investigation:

~~~yaml
logging:
  level:
    org.springframework.cloud.bootstrap: DEBUG
    org.springframework.context.annotation: TRACE
    org.springframework.boot.context.config: DEBUG
~~~

Helpful logger names and log levels may vary across versions. Enable TRACE only in development environments because component scan logs can be voluminous.

### Step 3: Check the Active Configuration Loading Mechanism

Read dependencies and startup properties to determine whether the application uses Config Data or legacy bootstrap. Focus on:

- `spring.config.import` in `application.yml` or `application.properties`.
- The `spring-cloud-starter-bootstrap` dependency.
- `spring.cloud.bootstrap.enabled` passed via system property or environment variable.
- `bootstrap.yml`/`bootstrap.properties` files and `spring.cloud.config.uri`.
- `PropertySourceLocator` classes and `BootstrapConfiguration` metadata.

Do not conclude the application has two contexts solely because Config Server receives multiple requests. Cross-check requests with context logs and loaded profiles.

## 4. Fixes

### 4.1. Separate the Bootstrap Package from the Application Package

Place bootstrap configuration classes outside the main application's scan scope. For example, if the application's root package is `com.acme.orders`, place bootstrap configuration in `com.acme.cloudbootstrap`:

~~~text
com.acme
├── orders
│   ├── OrdersApplication.java
│   └── service/
└── cloudbootstrap
    └── RemoteBootstrapConfiguration.java
~~~

Register that class in `META-INF/spring.factories`:

~~~properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=\
com.acme.cloudbootstrap.RemoteBootstrapConfiguration
~~~

The configuration class can declare `PropertySourceLocator` or beans genuinely needed for bootstrap:

~~~java
package com.acme.cloudbootstrap;

import java.util.Map;

import org.springframework.cloud.bootstrap.config.PropertySourceLocator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;

@Configuration(proxyBeanMethods = false)
public class RemoteBootstrapConfiguration {

    @Bean
    PropertySourceLocator remotePropertySourceLocator() {
        return environment -> new MapPropertySource(
            "remoteDefaults",
            Map.of("feature.example.enabled", true)
        );
    }
}
~~~

The example above illustrates placement and registration mechanics; in a real application, replace `MapPropertySource` with an appropriate configuration source and avoid putting secrets in source code. If the application uses `scanBasePackages` broader than `com.acme.orders`, re-check that scope: `com.acme.cloudbootstrap` can still be scanned if the root package is `com.acme`.

Another option is narrowing component scan to the application packages to manage or using an intentional exclude filter. Avoid scanning from overly broad packages such as `com` or `org`, as that can pull unintended configurations into the context.

### 4.2. Choose the Right Way to Load Config Server Configuration

With Spring Boot 2.4 or later, Config Data via `spring.config.import` is the default Config Server integration method. Example:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: "optional:configserver:"
~~~

You can specify the server address inside the import:

~~~yaml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
~~~

The `optional` prefix lets the application continue starting if Config Server is unreachable. If server configuration is mandatory, omit `optional` so startup fails when configuration cannot be loaded. The Config Data approach does not require `bootstrap.yml`.

If the system still needs legacy bootstrap, enable this mechanism via the `spring-cloud-starter-bootstrap` dependency or via system property/environment variable. Example:

~~~bash
java -Dspring.cloud.bootstrap.enabled=true -jar orders-service.jar
~~~

Then Config Server connection settings are typically placed in `bootstrap.yml`:

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    config:
      uri: http://localhost:8888
~~~

Choose the mechanism matching your architecture and running version. If already using Config Data, do not add legacy bootstrap just because logs show multiple requests. If legacy bootstrap must be retained, verify the enabling property is set early enough via system property, environment variable, or starter.

### 4.3. Create the Main Context Only Once

Keep a single clear startup entry point:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Do not call `SpringApplication.run` from beans, static initializers, `ApplicationRunner`, or per request. If multiple contexts are needed, declare parent/child/sibling relationships explicitly with `SpringApplicationBuilder` and document which context owns beans, executors, schedulers, connection pools, or listeners.

### 4.4. Avoid Fixing Symptoms by Enabling Bean Overrides

Do not enable bean overriding just to make the application start past a duplicate definition error. Doing so masks why configuration was loaded twice and makes the winning bean depend on registration order. Remove the duplicate registration path or narrow component scan first; use overrides only when it is an intentional design decision and the final active bean has been verified.

## 5. Interpreting Diagnostic Results

| Symptom | Likely Interpretation | What to Check |
|---|---|---|
| Bootstrap context exists as parent of main context | Legacy bootstrap is active | Check starter, system property, and whether bootstrap is needed |
| Same bootstrap class appears in metadata and component scan | Configuration loaded in both contexts | Move package outside scan scope or narrow scan |
| Bean with same name exists in parent and child | Bean registered separately in two BeanFactories | Determine which bean belongs in each context; check whether child shadows parent |
| Config Server receives requests with default then active profile | Config Data is resolving configuration in stages | Check profiles and Config Data logs; do not treat as two main contexts |
| Multiple independent main contexts with different IDs | Multiple startup entry points or context hierarchy design | Search for run/build calls, test configs, and context creation sites |
| Compatibility error appears after upgrade | Spring Boot and Spring Cloud may belong to incompatible generations | Check release train and BOM before adjusting bootstrap |

## 6. Version Notes

- Spring Boot 2.4 introduced Config Data and `spring.config.import`. For modern Spring Cloud Config Clients, this is the default loading mechanism; `bootstrap.yml` is unnecessary for this flow.
- Legacy bootstrap can still be enabled explicitly via `spring-cloud-starter-bootstrap` or `spring.cloud.bootstrap.enabled=true`. With this mechanism, distinguish the parent bootstrap context from the child main context.
- Since Spring Cloud 2022.0.3, `PropertySourceLocator` is invoked twice to support activating profiles from external configuration. When seeing multiple property source fetches, verify this flow before concluding the context was recreated.
- Prior to Spring Cloud 2022.0.3, `PropertySourceLocator` ran by default in the main application context. Spring Cloud docs mention `spring.cloud.config.initialize-on-context-refresh=true` in bootstrap configuration to require running in the bootstrap context.
- The Spring Cloud Release Train must be compatible with the Spring Boot generation. For example, Spring Cloud's compatibility table lists Boot `3.3.x` under train `2023.0.x` starting with `2023.0.2`; this is train mapping info and does not replace checking service releases and current support status. Use the Spring Cloud BOM instead of pinning disparate versions on individual modules.
- Registering `BootstrapConfiguration` via `spring.factories` is a dedicated contract of Spring Cloud bootstrap. Do not blindly replace this key with Spring Boot's auto-configuration metadata; the two mechanisms serve different purposes.

## 7. Troubleshooting Checklist

1. Record the ID and parent of every `ApplicationContext`.
2. Distinguish the bootstrap context, main context, and contexts created by tests or `SpringApplicationBuilder`.
3. Find all `BootstrapConfiguration` entries in `META-INF/spring.factories`.
4. Compare bootstrap configuration packages against the root package and `scanBasePackages` of `@SpringBootApplication`.
5. Check duplicate bean names, where beans are declared, and initialization side effects.
6. Identify whether Config Data or legacy bootstrap is enabled.
7. Cross-check Config Server request counts against profiles and the release train's `PropertySourceLocator` behavior.
8. Verify Spring Boot/Spring Cloud via BOM and the official compatibility table.
9. Restart once in a development environment and confirm every bean with side effects is created only in its intended context.

## Official Documentation

- [Spring Cloud Commons — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): bootstrap context, context hierarchy, and guidance on separating packages for `BootstrapConfiguration`.
- [Spring Cloud Config — Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data, `spring.config.import`, and legacy config-first bootstrap.
- [Spring Boot — Structuring Your Code](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html): application class placement and component scan scope.
- [Spring Cloud — Project and Release Train Compatibility](https://spring.io/projects/spring-cloud/): Spring Boot and Spring Cloud compatibility matrix.
