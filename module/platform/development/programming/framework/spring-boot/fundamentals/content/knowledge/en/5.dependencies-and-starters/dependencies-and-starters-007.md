# How adding a dependency can trigger auto-configuration

In Spring Boot, a small edit to `build.gradle` or `pom.xml` can sometimes change the behavior of the entire application. Simply adding `spring-boot-starter-web` can turn the app into an HTTP server; adding `spring-boot-starter-security` can cause HTTP requests to require authentication; adding a data access library can cause Boot to create a `DataSource`, transaction manager, or repository infrastructure when conditions are met.

This is the effect of **auto-configuration**: Spring Boot inspects which libraries are actually present when the application starts, combines them with configuration properties and existing beans, and decides which additional Spring components to create. **Adding a dependency is an input signal, not a guarantee that every related configuration will activate.**

## 1. From dependency to bean: how the whole chain unfolds

Imagine the process in the following order:

~~~text
Edit build.gradle / pom.xml
             │
             ▼
Gradle / Maven resolves dependencies and transitive dependencies
             │
             ▼
Runtime classpath changes
             │
             ▼
Spring Boot starts, loads auto-configuration candidates
             │
             ▼
Evaluate conditions:
  - Are required classes/libraries present?
  - Which web application type is running?
  - Does a property enable the feature?
  - Has the application or another library already provided a bean?
  - Are other integration conditions satisfied?
             │
       ┌─────┴─────┐
       │           │
     TRUE        FALSE
       │           │
       ▼           ▼
Register beans   Skip configuration/beans
and infrastructure
       │
       ▼
Application exhibits new behavior at runtime
~~~

For example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

This dependency places Spring Web MVC, HTTP support libraries, and a default embedded Servlet container onto the runtime classpath according to the starter's dependency set. If the corresponding conditions all hold, Spring Boot automatically registers components such as `DispatcherServlet`, request-mapping infrastructure, HTTP message converters, and the web server. Thanks to this, we do not have to write `@Bean` definitions for all of them ourselves.

**Important timing note:** Auto-configuration evaluation normally happens **when creating the Spring application context during startup**. Editing `build.gradle` while leaving an already-running JVM open does not reconfigure the live context automatically; you must sync dependencies and rebuild/restart the application as appropriate.

## 2. Distinguishing dependency, starter, and auto-configuration

These three concepts are related, yet they are not the same.

| Concept | Nature | Effect |
|---|---|---|
| **Dependency** | Dependency relationship to a library/module | Makes the library's classes and resources present on compile/runtime classpaths depending on scope |
| **Spring Boot starter** | A convenient dependency grouping libraries commonly needed for a feature area | Brings the right set of dependencies into the project with minimal declaration |
| **Auto-configuration** | Conditional Spring configuration classes loaded by Boot when initializing the context | Decides which beans/infrastructure to create based on classpath, properties, beans, and environment |

For example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

- `spring-boot-starter-web` brings in libraries commonly used for Spring MVC-based HTTP applications.
- `spring-boot-starter-validation` puts appropriate Bean Validation infrastructure onto the classpath to support validation when configuration conditions match.
- Boot's auto-configuration classes inspect what is on the classpath and create applicable beans/infrastructure.

**A starter is neither an annotation nor active code that runs when you type the dependency line.** On the other hand, an individual library that is not a starter can still influence auto-configuration if it satisfies a classpath condition, or if that JAR itself provides auto-configuration via Boot's registration mechanism.

### Transitive dependencies also have an impact

Suppose a project adds just one starter, and the starter pulls in multiple libraries. Spring Boot observes the **runtime classpath after the build tool resolves it**, not only the lines directly declared by the developer:

~~~text
spring-boot-starter-web
   ├── spring-web
   ├── spring-webmvc
   ├── JSON library used by the starter
   └── default embedded servlet container
~~~

The exact list depends on the Spring Boot version and dependency configuration. Consequently, excluding a transitive dependency or changing a library version can also flip an auto-configuration condition from true to false.

## 3. Who enables auto-configuration?

A Spring Boot application typically has:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`@SpringBootApplication` includes capabilities equivalent to:

- `@SpringBootConfiguration`: declares the application's configuration source.
- `@EnableAutoConfiguration`: enables the auto-configuration selection mechanism.
- `@ComponentScan`: finds application-declared components within the configured packages.

Distinguish two frequently confused operations:

**Component scanning** finds `@Component`, `@Service`, `@Controller`, `@Configuration`, and corresponding stereotypes within specified package scopes. **Auto-configuration** imports configuration classes pre-registered by libraries and evaluates their conditions. Boot's auto-configuration does not depend on library configuration classes residing inside a subpackage of the main class.

In **Spring Boot 3.x**, auto-configuration classes are declared by libraries in the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Each line is the fully qualified name of a configuration class, such as `com.example.lib.ExampleAutoConfiguration`. When `@EnableAutoConfiguration` is active, Boot reads these lists from relevant JARs, evaluates conditions, and imports matching configurations. This is a candidate registration mechanism; it does not mean every candidate executes.

A plain library containing only classes and registering no auto-configurations can still change outcomes, because an existing configuration inside `spring-boot-autoconfigure` may check for the presence of the newly added classes.

## 4. Which conditions decide whether configuration activates?

Spring Boot uses the `@Conditional...` annotation family. Conditions can be placed on the auto-configuration class or on individual `@Bean` methods.

| Condition | Meaning | Example scenario |
|---|---|---|
| `@ConditionalOnClass` | Specific class is on the classpath | Matching JDBC/Jackson/Spring MVC library is present |
| `@ConditionalOnMissingClass` | Specific class is absent from the classpath | Pick a fallback configuration when an integration is missing |
| `@ConditionalOnBean` | A bean matching the requirement already exists | Create an integration only after a foundational component is registered |
| `@ConditionalOnMissingBean` | No matching bean exists yet | Allow default configuration to back off in favor of an application bean |
| `@ConditionalOnProperty` | A property exists or matches a conditional value | Enable/disable a capability via configuration |
| `@ConditionalOnWebApplication` | Application matches a web application type | Configure only Servlet or reactive web |
| `@ConditionalOnNotWebApplication` | Application is not running as a web app | Select configuration meant for non-web apps |
| `@ConditionalOnResource` | Specified resource is present | Activate only when the classpath contains a required resource |

Those are common conditions; real configurations may combine multiple conditions simultaneously, composite conditions, or custom logic. For example, to create beans for Spring MVC, an auto-configuration may require MVC classes to be present, the application to be a **Servlet web application**, and certain beans to be created beforehand.

### 4.1. Classpath opens up possibilities; it does not guarantee a bean appears

Consider this illustrative logic:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.mail.MailClient")
public class MailAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MailGateway.class)
    @ConditionalOnProperty(
            prefix = "app.mail",
            name = "enabled",
            havingValue = "true"
    )
    MailGateway mailGateway() {
        return new MailGateway();
    }
}
~~~

`MailAutoConfiguration` and `MailGateway` are illustrative types from a hypothetical library; they are **not** built-in Spring Boot classes.

The `MailGateway` bean can only be created when:

1. The library's auto-configuration is registered with Boot and included for evaluation.
2. The class `com.vendor.mail.MailClient` is on the classpath.
3. `app.mail.enabled=true`.
4. No other `MailGateway` bean exists that would cause `@ConditionalOnMissingBean` to fail.

If any condition is missing, the corresponding configuration or bean method is skipped. This is why a dependency may **produce no observable behavioral change** in the current environment.

### 4.2. The “back off” mechanism: respecting application-defined configuration

Many Boot auto-configurations use `@ConditionalOnMissingBean` to supply **sensible defaults**. When the application already declares a matching bean, Boot usually yields to that configuration.

Diagram:

~~~text
Auto-configuration wants to create a bean of type X
              │
              ▼
Does ApplicationContext already have a matching bean X?
       │                         │
      Yes                        No
       │                         │
       ▼                         ▼
Keep existing bean        Create default bean
and skip default          if other conditions hold
~~~

Do not overgeneralize that **every** auto-configuration automatically backs off by the exact same rule. Check the exact conditions on the bean of interest; some configurations also inspect properties, specific bean counts, or registration order.

### 4.3. Web application type is also a condition

Adding `spring-boot-starter-webflux` does not necessarily switch the server to reactive if the application already includes `spring-boot-starter-web`. Under Boot's default web application type selection, when both Spring MVC and WebFlux are present, the application is typically configured as a **Servlet/MVC application**. You can still use `WebClient` in that application.

This illustrates that **having classes on the classpath is not enough**: environment conditions and the web runtime type still decide which auto-configuration applies.

## 5. Example 1 — Adding the web starter gives the app an HTTP server

Suppose initially the application only has:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Without a web stack, this may be a **non-web** Boot application. Add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

The starter puts the components needed for Spring MVC and the default embedded Servlet container onto the runtime classpath. Unless special configuration changes the application type or disables web infrastructure, Boot will:

- Select the **Servlet web application** type.
- Configure the embedded Servlet web server and related web beans.
- Register `DispatcherServlet` along with handler lookup and request processing.
- Configure HTTP message converters matching libraries on the classpath, typically including JSON handling.

Then the controller:

~~~java
package com.example.catalog.api;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthGreetingController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring Boot";
    }
}
~~~

can be registered by Spring if `com.example.catalog.api` falls within component scan scope. Requests to `GET /hello` can be handled without manually writing `DispatcherServlet` configuration.

**Two mechanisms cooperate:** Auto-configuration builds the web infrastructure; component scanning discovers the controllers we write. Having the web starter while placing the controller outside the scan scope will still leave the endpoint unregistered.

## 6. Example 2 — Adding Spring Security changes HTTP API behavior

In a working MVC application, add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

This dependency puts Spring Security onto the classpath. When conditions match and the application does not supply an alternative security policy, Spring Boot and Spring Security can set up **default web security configuration**.

Observable effects in a typical MVC application include:

- Requests that previously worked unauthenticated may now be rejected or require login.
- The application gets a Spring Security filter chain attached.
- If no other user/authentication source is configured, Boot can generate a default development user and log the generated password at startup.

For example, before adding the starter, `GET /hello` may return HTTP 200. After adding the starter and restarting, unauthenticated requests may receive **HTTP 401**, or enter a different login flow depending on how the client sends requests and the negotiated authentication mechanism. Do not treat one specific HTTP code as invariant across all configurations.

If the application needs its own policy, you can declare a `SecurityFilterChain` bean (on the Servlet stack):

~~~java
package com.example.catalog.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/hello").permitAll()
                .anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This bean causes Boot's corresponding default web security configuration to **back off**; the application's policy decides which endpoints are public. This example illustrates only URL authorization. Real systems must also configure the right identity source, login mechanism, CSRF/CORS policies, and method protection suited to the client type.

For **WebFlux**, the corresponding Security configuration uses `SecurityWebFilterChain` and `ServerHttpSecurity`, not Servlet's `HttpSecurity` verbatim.

**Takeaway:** A starter that seems like merely adding an “API library” can activate new beans/filters and change how clients interact with the application.

## 7. Example 3 — Adding Spring Data JPA can activate database infrastructure

Gradle configuration snippet:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

The JPA starter puts libraries such as Spring Data JPA, a JPA provider, and related JDBC infrastructure onto the classpath. When database configuration is complete, Boot can configure:

1. A `DataSource` using the configured driver and connection details.
2. An `EntityManagerFactory` to manage JPA entities.
3. An appropriate transaction manager for JPA transactions.
4. Spring Data JPA repository infrastructure and repositories within the appropriate scan range.

Example configuration for PostgreSQL:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=app
spring.datasource.password=${DB_PASSWORD}
~~~

Application entity and repository code:

~~~java
package com.example.catalog.product;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import org.springframework.data.jpa.repository.JpaRepository;

@Entity
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}

interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

The code snippet puts both types in the same package for illustration; in real projects you can split them into two separate Java files.

However, **adding only the JPA starter does not guarantee the application will connect to a database successfully**. Without an appropriate driver, connection URL, an available embedded database, or valid configuration, `DataSource`/JPA initialization can fail and prevent startup. Some beans will also not be created if other conditions are unmet.

Conversely, if you add the starter when the application already declares a `DataSource`, some auto-configurations may reuse that bean or back off in favor of it, depending on specific conditions. View this mechanism as **coordination among dependencies, configuration, and existing beans**.

### Distinguishing from reactive data access

`spring-boot-starter-data-jpa` typically pairs with **JDBC**, a blocking I/O access model. Adding `spring-boot-starter-webflux` does not automatically make JPA reactive. For reactive SQL access, consider `spring-boot-starter-data-r2dbc`, an R2DBC driver, and a corresponding reactive transaction manager. Choose a starter matching the actual I/O path, not merely because a controller returns `Mono`.

## 8. Why does “adding a library” sometimes have no effect, and sometimes break the app?

### Case A: Classes exist, yet environment conditions are missing

Servlet auto-configuration applies only to Servlet web applications; CLI or reactive web apps may not satisfy that condition. The dependency is present, yet part of the configuration is skipped.

### Case B: A property disables the feature

Some auto-configurations require a property to satisfy a condition. For instance, in the illustrative `MailAutoConfiguration` above, without `app.mail.enabled=true` the bean is not created. Look up the exact property name and default value for each library; there is no single “enable all auto-configuration” property.

### Case C: An existing bean causes the default to be skipped

Many configurations use `@ConditionalOnMissingBean`. If the application already declared a matching bean, Boot may skip creating the default one. This is intentional to allow customization.

### Case D: Dependency is not on the runtime classpath

A library declared only in `testImplementation` serves tests and is normally **not on the production application's runtime classpath**. Different dependency scopes lead to different behavior. Likewise, `compileOnly` does not behave like `implementation` at runtime.

### Case E: Bean definition exists, yet initialization fails

Passing condition evaluation does not mean a bean can always be constructed. Connecting to a database, resolving secrets, binding configuration properties, or resolving constructor dependencies can fail. For instance, auto-configuration selects the JPA path, yet `DataSource` cannot connect to the database.

### Case F: A dependency shifts which configuration branch is selected

When a technology is added to or removed from the classpath, `@ConditionalOnClass`/`@ConditionalOnMissingClass` conditions can change outcomes; adding an application bean can also alter `@ConditionalOnMissingBean`. Thus, upgrading, adding, or excluding dependencies requires verifying **runtime behavior**, not just checking that the build succeeds.

## 9. What does a library-provided auto-configuration look like?

In Spring Boot 3.x, an integration library can declare its own auto-configuration. For example, a hypothetical audit library:

~~~java
package com.example.audit.autoconfigure;

import com.example.audit.AuditFormatter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AuditFormatter.class)
    @ConditionalOnProperty(
            prefix = "audit",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    AuditFormatter auditFormatter() {
        return new AuditFormatter();
    }
}
~~~

Assume `AuditFormatter` is a public class in the same library with a no-arg constructor. The library places the resource:

~~~text
src/main/resources/META-INF/spring/
  org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Contents:

~~~text
com.example.audit.autoconfigure.AuditAutoConfiguration
~~~

When a Boot application adds this library JAR to its runtime classpath, Boot can discover its auto-configuration without the user writing `@Import(AuditAutoConfiguration.class)`. With the setup above:

- `audit.enabled` is omitted: the property condition still passes thanks to `matchIfMissing = true`.
- `audit.enabled=true`: creates an `AuditFormatter` bean if no bean of the same type exists.
- `audit.enabled=false`: skips the bean declared by this method.
- The application registered its own `AuditFormatter` bean: `@ConditionalOnMissingBean` causes the default configuration to back off.

This example shows why adding a **JAR containing auto-configuration** can change the Spring context by itself. A library containing only ordinary classes without registering configuration like this will not create beans via this mechanism unless another already-present configuration reacts to its classes.

## 10. How does Boot handle ordering and resolve conflicts?

Auto-configuration does not evaluate each class in complete isolation. One configuration may depend on a bean created by another configuration, or need to be evaluated after user-declared beans are recorded.

Spring Boot supports specifying relative ordering of auto-configurations via metadata/annotations such as `@AutoConfigureBefore`, `@AutoConfigureAfter`, or the `before`/`after` attributes of `@AutoConfiguration`. This ordering affects **the processing order of auto-configuration definitions**, and does not guarantee bean instantiation order in every scenario.

In regular applications, do not rely on accidental dependency ordering to replace beans. When customization is needed, prefer:

1. Configuring via the starter's official properties.
2. Declaring an application bean if the auto-configuration supports backing off.
3. Excluding a specific auto-configuration only when there is a clear reason.

Spring Boot's **dependency management** helps select compatible versions of many popular libraries. However, managed versions and whether auto-configuration activates are **two separate concerns**: the same dependency can yield different configuration when properties, classpath, or beans change.

## 11. Controlling auto-configuration when you don't want the defaults

### 11.1. Prefer configuring with properties

Many starters provide properties such as `spring.datasource.*`, `spring.jpa.*`, `server.port`, or `management.*` to tune functionality. For example:

~~~properties
server.port=8081
spring.jpa.show-sql=false
~~~

Property names only take effect when the corresponding components are present and configured. Do not assume that adding `spring.jpa.show-sql=false` brings JPA into an application that lacks the dependency.

### 11.2. Provide custom beans

When an auto-configuration has `@ConditionalOnMissingBean`, you can let Spring use your application-declared bean. For example, custom web security configuration via `SecurityFilterChain` replaces default policy with real requirements.

### 11.3. Exclude auto-configuration

When you are certain you do not want Boot to create a specific piece of infrastructure, you can exclude that exact auto-configuration:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(
        exclude = DataSourceAutoConfiguration.class
)
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Or via a property:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

The two examples illustrate **two mutually alternative ways of configuring**, not something you need to use together. They are only appropriate when omitting a Boot-created `DataSource` is an intentional decision; other auto-configurations or beans depending on `DataSource` may still fail.

Do not exclude auto-configurations en masse just to get an application past startup errors. First determine why a condition matched and which bean failed.

## 12. Finding out exactly which auto-configurations are enabled or skipped

When you add a starter and see application behavior change, Spring Boot offers tools to investigate based on actual conditions.

### Enable the condition evaluation report

Run the application with:

~~~text
--debug
~~~

or configure:

~~~properties
debug=true
~~~

Boot can log the **Conditions Evaluation Report**. The report distinguishes:

- **Positive matches**: configurations whose evaluated conditions were satisfied.
- **Negative matches**: configurations skipped because one or more conditions failed.
- **Exclusions**: auto-configurations that were excluded.
- Unconditional configurations when reported.

Illustrative message example:

~~~text
DataSourceAutoConfiguration matched:
  - @ConditionalOnClass found required classes

SomeFeatureAutoConfiguration did not match:
  - @ConditionalOnProperty did not find the expected value
~~~

Exact content and formatting depend on the Spring Boot version, dependencies, and application. **Matched** means the configuration's conditions were met; it does not guarantee every bean initialized successfully or that external services are reachable.

### Spring Boot Actuator

If the application has `spring-boot-starter-actuator`, the `conditions` endpoint can expose condition evaluation details; whether it is callable over HTTP also depends on exposure and security configuration. Only enable/expose diagnostic endpoints in appropriate environments and security boundaries.

### Inspect the dependency tree

If you do not understand where a class came from, inspect resolved dependencies:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Or trace a specific library:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-webmvc \
  --configuration runtimeClasspath
~~~

These are **reference commands for learners to run** in a suitable Gradle project. Use `./gradlew` on Unix-like systems or `gradlew.bat` on Windows. Looking at **runtimeClasspath** matters because auto-configuration typically decides based on classes and resources present **when the application runs**.

### Ask root-cause questions

Suppose after adding `spring-boot-starter-data-jpa` the application fails to start:

1. Verify which starter and JDBC driver are on the runtime classpath.
2. Read the root error—for example, `DataSource` lacking a suitable URL/driver or failing to reach the database.
3. Read the Conditions Evaluation Report to see which configurations matched.
4. Check properties under the active environment/profile, declared beans, and exclusions.
5. Choose whether to fix configuration, supply a bean, or remove unneeded dependencies; **do not assume by default that the bug is in Spring Boot**.

## 13. Comparison scenario: same app, changing one dependency

Suppose a project has a `GET /products` controller using in-memory sample data. The outcomes below represent **typical behavior under default configuration**, and may differ if the application declares custom beans or properties.

| Dependency state | Observable changes |
|---|---|
| Only `spring-boot-starter` | Starts the Spring context; does not automatically provide an HTTP server from the base starter alone |
| Add `spring-boot-starter-web` | Servlet web application, embedded server, and Spring MVC infrastructure if conditions hold; can serve `/products` |
| Also add `spring-boot-starter-security` | Default security filter chain appears and authentication is required for many requests if uncustomized |
| Also add `spring-boot-starter-data-jpa` | Basis for configuring JPA, `DataSource`, and repositories; may fail startup if suitable database configuration is missing |
| Remove Security starter or add custom config | Security behavior changes according to remaining classpath, beans, and security policy |

Read the table left to right as **input changes** leading to re-evaluated startup conditions, not as a sequence of steps every Spring Boot application must take.

## 14. Practical guidelines when adding dependencies

When preparing to add a starter to Spring Boot, answer five questions:

1. **Which libraries actually enter the runtime classpath?** Check transitive dependencies, exclusions, and dependency scopes.
2. **Which auto-configurations could be triggered?** Identify configurations tied to the new classpath entries.
3. **Which other conditions must still hold?** Include application type, properties, existing beans, and environment configuration.
4. **Which runtime behaviors could change?** For example, an HTTP server starts listening, security filters appear, a database connection opens, or a default bean is replaced.
5. **How will you confirm the cause?** Check startup logs, the Conditions Evaluation Report, bean/endpoint listings, and appropriate integration tests.

A dependency in Spring Boot therefore **does more than provide classes for developers to call**. It can also act as a signal turning auto-configuration conditions true, causing Spring to register beans and set up infrastructure at startup. Conversely, when conditions fail or the application configures things explicitly, Boot can skip default configuration. Understanding the chain **dependency → classpath → conditions → beans → behavior** helps explain seemingly surprising changes after each starter is added.
