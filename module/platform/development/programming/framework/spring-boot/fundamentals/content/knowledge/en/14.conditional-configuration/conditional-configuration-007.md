# `@ConditionalOnWebApplication`, `@ConditionalOnNotWebApplication`, and Application Types

Spring Boot can run applications in several modes: a web application using Spring MVC (Servlet), a web application using Spring WebFlux (Reactive), or an application that does not run as a web application. When a configuration is only suitable for one kind of application, you can use `@ConditionalOnWebApplication` and `@ConditionalOnNotWebApplication` so Spring Boot only registers the corresponding configuration or beans.

These two annotations commonly appear in auto-configurations and shared libraries. They allow a library to provide integrations for multiple application types without forcing all applications to share the same web stack.

## 1. Three Spring Boot Application Types

Spring Boot represents the application type using `WebApplicationType`:

| Type | Meaning | Example |
|---|---|---|
| `SERVLET` | Web application based on the Servlet API and a Servlet container | Spring MVC, Spring Web MVC |
| `REACTIVE` | Web application based on the reactive stack | Spring WebFlux with a reactive server |
| `NONE` | Application that does not initialize a web application context/server | Batch job, command-line application, worker |

A `SERVLET` application typically uses Spring MVC and runs on a Servlet container such as Tomcat or Jetty. Requests are handled under the Servlet model.

A `REACTIVE` application typically uses Spring WebFlux with a reactive server such as Reactor Netty. The processing flow is based on reactive types and non-blocking I/O when participating components support that model.

A `NONE` application does not start a web server. It can still use Spring IoC, dependency injection, scheduling, messaging, databases, or HTTP client libraries. Making outbound HTTP calls to another system does not turn an application into a web application.

For example, a batch worker using `WebClient` to send data to an external API can still be a `NONE` application. A web client is the ability to call remote services; web application type describes the kind of context the application creates to serve or process incoming requests.

## 2. `@ConditionalOnWebApplication`

`@ConditionalOnWebApplication` belongs to the package:

~~~java
org.springframework.boot.autoconfigure.condition
~~~

This annotation tells Spring Boot to apply the configuration only when the application is identified as a web application. It has a `type` attribute to restrict the web stack:

~~~java
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET
)
~~~

Supported values:

- `SERVLET`: matches only Servlet web applications.
- `REACTIVE`: matches only Reactive web applications.
- `ANY`: matches web applications of either Servlet or Reactive type.

If `type` is omitted, the default value is `ANY`. Therefore, the simple annotation below means the configuration applies to both Servlet and Reactive applications:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication
public class WebFeatureConfiguration {
}
~~~

The condition can be placed at the configuration class level or on a `@Bean` method. When placed at the class level, the condition decides whether the entire configuration is processed. When placed on a method, the condition only decides whether the bean declared by that method is registered.

### Applying Only to Servlet

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET
)
public class ServletWebConfiguration {

    @Bean
    WebStackDescriptor webStackDescriptor() {
        return new WebStackDescriptor("SERVLET");
    }
}
~~~

This configuration is only applied when the context is a Servlet web application. It is suitable for components integrating directly with the Servlet API, such as filters, interceptors, or a Spring MVC adapter.

### Applying Only to Reactive

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.REACTIVE
)
public class ReactiveWebConfiguration {

    @Bean
    WebStackDescriptor webStackDescriptor() {
        return new WebStackDescriptor("REACTIVE");
    }
}
~~~

This configuration is only applied to Reactive web applications. Integration components may include `WebFilter`, `HandlerFilterFunction`, or adapters for WebFlux.

In both examples above, `WebStackDescriptor` is an illustrative data type:

~~~java
public record WebStackDescriptor(String type) {
}
~~~

In real applications, each configuration typically declares beans with functionality tailored to its respective web stack. Both configurations above declare a bean named `webStackDescriptor` to illustrate that only the matching configuration is selected in a given context. If both conditions ever match due to unexpected configuration or context setup, re-check the application type and bean definitions.

## 3. `@ConditionalOnNotWebApplication`

`@ConditionalOnNotWebApplication` has the opposite meaning of the web condition: the configuration is only applied when the application is not identified as a web application.

For example, a library may provide a reporting component dedicated to batch workers:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnNotWebApplication
public class BatchSupportConfiguration {

    @Bean
    BatchAuditReporter batchAuditReporter() {
        return new BatchAuditReporter();
    }
}
~~~

The `BatchAuditReporter` bean is only registered in applications that do not run as a web application. This is useful when a library needs to provide dedicated components for command-line jobs, schedulers, or workers.

The annotation does not have a `type` attribute to distinguish Servlet vs. Reactive, because both are web applications. If you need to distinguish between the two web stacks, use `@ConditionalOnWebApplication(type = ...)`.

You can use `@ConditionalOnNotWebApplication` on a bean method if only one bean needs to depend on the non-web condition:

~~~java
@Bean
@ConditionalOnNotWebApplication
BatchAuditReporter batchAuditReporter() {
    return new BatchAuditReporter();
}
~~~

## 4. How Does Spring Boot Determine the Application Type?

Spring Boot determines the application type during startup preparation. The deduction is based on the web stacks present on the classpath and the selected `ApplicationContext` type. You can let Boot deduce it automatically or explicitly specify the application type via a property:

~~~yaml
spring:
  main:
    web-application-type: servlet
~~~

Common values are:

- `servlet`
- `reactive`
- `none`

For example, to force the application to run as non-web:

~~~yaml
spring:
  main:
    web-application-type: none
~~~

You can pass the value when running the JAR:

~~~bash
java -jar application.jar --spring.main.web-application-type=none
~~~

Or select Reactive:

~~~bash
java -jar application.jar --spring.main.web-application-type=reactive
~~~

When this property is set, it controls the type of context Spring Boot uses. Web conditions are then evaluated according to the chosen application type.

### When Both Spring MVC and WebFlux Are on the Classpath

A common scenario is a project having both `spring-boot-starter-web` and `spring-boot-starter-webflux`. Spring Boot prioritizes Spring MVC when both stacks are present and the application is not explicitly configured as Reactive.

Therefore, simply seeing a WebFlux dependency in a build file is not enough to conclude the application is Reactive. An MVC application can still use `WebClient` from WebFlux to call external APIs.

If you genuinely want to run on the Reactive stack, configure it explicitly:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

If you want the application not to start a web server even though web libraries are on the classpath, you can set `none`. After changing it, verify the context type and actual registered beans.

## 5. Combining Web Conditions with Other Conditions

Spring Boot conditions can be combined on the same configuration class or bean. For example, a Servlet integration is enabled only when the required library is present and the feature property is enabled:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET
)
@ConditionalOnClass(name = "jakarta.servlet.Filter")
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
)
public class ServletAuditConfiguration {

    @Bean
    ServletAuditSupport servletAuditSupport() {
        return new ServletAuditSupport();
    }
}
~~~

The configuration is only applied when all of the following conditions are satisfied simultaneously:

1. The application is a Servlet web application.
2. The Servlet API is on the classpath.
3. `app.audit.enabled` has the value `true`.

If any condition does not match, this configuration does not register the bean. Classpath conditions are especially useful for reusable libraries: applications without the Servlet API do not need to load Servlet-dependent components.

You can organize an auto-configuration suite by stack:

- Servlet configuration: `@ConditionalOnWebApplication(type = SERVLET)`.
- Reactive configuration: `@ConditionalOnWebApplication(type = REACTIVE)`.
- Shared web configuration: `@ConditionalOnWebApplication` with default `ANY`.
- Non-web configuration: `@ConditionalOnNotWebApplication`.

This separation prevents stack-specific dependencies from mixing together. A library supporting both MVC and WebFlux can provide separate adapters while still sharing services or domain logic.

## 6. Example: Structuring a Library That Supports Multiple Application Types

Suppose an audit library needs to provide three integration options:

- A Servlet filter for Spring MVC.
- A Reactive web filter for Spring WebFlux.
- A batch event recorder for non-web applications.

The configurations can be organized as follows:

~~~text
audit/
├── ServletAuditConfiguration
│   └── ServletAuditFilter
├── ReactiveAuditConfiguration
│   └── ReactiveAuditWebFilter
└── NonWebAuditConfiguration
    └── BatchAuditReporter
~~~

Each configuration class registers only the appropriate adapter:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET
)
class ServletAuditConfiguration {

    @Bean
    ServletAuditFilter servletAuditFilter() {
        return new ServletAuditFilter();
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.REACTIVE
)
class ReactiveAuditConfiguration {

    @Bean
    ReactiveAuditWebFilter reactiveAuditWebFilter() {
        return new ReactiveAuditWebFilter();
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnNotWebApplication
class NonWebAuditConfiguration {

    @Bean
    BatchAuditReporter batchAuditReporter() {
        return new BatchAuditReporter();
    }
}
~~~

If packaged as Spring Boot auto-configuration, these configuration classes can be published in the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The conditions on each configuration decide which adapter is registered. In real designs, `@AutoConfiguration` can be used instead of `@Configuration` to clearly indicate the auto-configuration role, along with any necessary classpath, property, or bean conditions.

Shared audit logic should reside in a service or component independent of Servlet and Reactive APIs. The adapters simply translate each stack's requests/events to the shared contract. Thus, batch applications do not pull in Servlet filters, and MVC applications do not register Reactive web filters.

## 7. When Are Conditions Evaluated?

`@ConditionalOnWebApplication` and `@ConditionalOnNotWebApplication` are evaluated while Spring is parsing configurations and registering bean definitions.

They decide whether a configuration or bean participates in the `ApplicationContext`. They are not mechanisms to toggle beans per request, nor do they re-evaluate automatically if the application changes web mode while running.

For example, if the application starts with:

~~~yaml
spring:
  main:
    web-application-type: servlet
~~~

then the Servlet configuration is chosen during context initialization. Changing the YAML file to `reactive` while the application is already running does not replace the Servlet context with a Reactive context. To change the application type, you need to start a new `ApplicationContext` with the corresponding configuration.

Nor should web conditions be understood as a check that an HTTP port is open. Conditions are evaluated during context creation; whether the server has bound a port is another aspect of the application lifecycle.

## 8. Testing Conditions by Application Type

When writing auto-configuration, test Servlet, Reactive, and non-web cases. A configuration may work in the main application yet accidentally break another application if it lacks a condition or depends on the wrong web stack.

You can use context runners in Spring Boot Test to spin up contexts of the corresponding type:

- `ApplicationContextRunner` for ordinary non-web configurations.
- `WebApplicationContextRunner` for Servlet web contexts.
- `ReactiveWebApplicationContextRunner` for Reactive web contexts.

Context runners allow loading configuration classes and asserting bean presence or absence without launching the entire application. When testing auto-configuration, you can combine runners with `FilteredClassLoader` to simulate cases where a library or API is absent from the classpath.

Additionally, you can verify the application across launch configurations:

| Case | Application type configuration | Result to verify |
|---|---|---|
| Spring MVC | `servlet` | Servlet configuration is registered |
| Spring WebFlux | `reactive` | Reactive configuration is registered |
| Batch/CLI | `none` | Non-web configuration is registered |
| Both MVC and WebFlux present | Boot default or explicitly specified | Verify the actual active stack |
| No web dependencies | No web stack | Non-web configuration is active |
| Feature disabled by property | e.g. `app.audit.enabled=false` | Configuration with additional property condition is not registered |

If a bean does not appear as expected, check the actual context type, classpath dependencies, the `spring.main.web-application-type` property, and the condition report. Spring Boot Actuator can expose the `conditions` endpoint in properly configured environments to inspect matched or unmatched conditions; do not expose this diagnostic endpoint publicly outside secure administration boundaries.

## 9. Common Misconceptions

### Having `WebClient` Means the Application Is Reactive

Incorrect. `WebClient` is an HTTP client that can be used in Servlet or non-web applications. The Reactive web application condition refers to the application's web stack and context, not merely having a reactive client on the classpath.

### Having a WebFlux Dependency Means the Application Is Definitely Reactive

Incorrect. If Spring MVC is also present, Spring Boot prioritizes MVC by default unless the application type is explicitly configured as Reactive. Check the created context type instead of looking at a single dependency.

### Using `@ConditionalOnWebApplication` Without Specifying `type` for a Servlet-Only Configuration

By default, the annotation matches both Servlet and Reactive. If the bean uses APIs available only in the Servlet stack, specify `type = SERVLET` and add an appropriate classpath condition when needed.

### Using `@ConditionalOnNotWebApplication` to Check That an Application Has No Web Libraries

The two concepts are not identical. The non-web condition checks the initialized application/context type. It is not a general check that all web libraries are absent from the classpath. An application can have web dependencies yet be configured to run with type `NONE`.

### Expecting Conditions to Update Automatically When Runtime Configuration Changes

Conditions are evaluated during context construction. They do not swap beans when properties or web modes change at runtime. Changing the application type requires a fresh context initialization.

## 10. Workflow for Choosing Conditions

When writing a configuration dedicated to a specific application type, decide in order:

1. Determine whether the configuration needs a web context or can be used across all application types.
2. If web is needed, determine whether the dependent API is Servlet, Reactive, or shared by both.
3. Use `@ConditionalOnWebApplication(type = SERVLET)` for Servlet integrations.
4. Use `@ConditionalOnWebApplication(type = REACTIVE)` for Reactive integrations.
5. Use `@ConditionalOnWebApplication` when the configuration genuinely supports both web stacks.
6. Use `@ConditionalOnNotWebApplication` for configurations intended only for non-web applications.
7. Combine with `@ConditionalOnClass`, `@ConditionalOnProperty`, or `@ConditionalOnMissingBean` if the configuration also depends on classpath, options, or user-provided beans.
8. Test the context for each application type and verify the registered beans.

These two annotations allow Spring Boot to tailor configuration to the type of `ApplicationContext` the application initializes. By properly distinguishing Servlet, Reactive, and non-web, libraries can supply the right adapters, keep shared business logic independent of web stacks, and avoid creating beans that depend on APIs absent in the current application type.
