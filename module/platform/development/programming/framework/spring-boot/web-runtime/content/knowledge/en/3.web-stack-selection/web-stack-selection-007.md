# Setting spring.main.web-application-type to Explicitly Select the Web Stack

In Spring Boot, the **spring.main.web-application-type** property specifies which web mode the application should initialize: **servlet**, **reactive**, or **none**. Normally, Spring Boot determines the application type automatically from libraries on the classpath. However, when a project has multiple starters, uses both MVC and WebClient, runs background tasks from the same codebase, or needs to control deployment environments, specifying it explicitly prevents misunderstandings about which ApplicationContext and web server will be created.

Distinguish between two decisions: **choosing the application type** and **providing the matching dependencies for that type**. Setting this property does not install Spring MVC, WebFlux, Tomcat, or Reactor Netty; nor does it automatically convert blocking code into non-blocking code.

## 1. The three values and their startup effects

| Value | Startup model | Suitable when |
|---|---|---|
| **servlet** | Initializes a Servlet ApplicationContext, typically using Spring MVC and an embedded Servlet web server such as Tomcat | REST APIs using Spring MVC, traditional request/response web applications |
| **reactive** | Initializes a Reactive Web ApplicationContext, typically using Spring WebFlux and a reactive web server such as Reactor Netty | APIs or gateways designed to handle I/O with a reactive/non-blocking model |
| **none** | Initializes a non-web ApplicationContext without opening an HTTP web server | Command-line tools, data importers, batch tasks, worker programs that do not accept HTTP requests |

The corresponding Java enum constants are **WebApplicationType.SERVLET**, **WebApplicationType.REACTIVE**, and **WebApplicationType.NONE**. In application.properties or application.yml, lowercase values such as servlet, reactive, or none can be used.

### Servlet

With the Servlet stack, Spring Boot can auto-configure DispatcherServlet, Servlet filters, and embedded Tomcat when the corresponding Spring MVC/Servlet dependencies are present. An HTTP request is typically processed by a Servlet server worker thread. Servlet APIs such as HttpServletRequest, Filter, or HandlerInterceptor belong to this context.

### Reactive

With the Reactive stack, Spring Boot can auto-configure WebFlux DispatcherHandler, WebFilter, and a reactive web server when all required dependencies are present. Non-blocking I/O allows serving many connections with a relatively small number of event-loop threads. This model does not by default turn JDBC calls, blocking libraries, or Thread.sleep into non-blocking operations.

Reactive mode does not automatically mean Reactor Netty must be used: the chosen server also depends on libraries and configuration. Reactor Netty is the common default choice for spring-boot-starter-webflux.

### None

With none, Spring Boot still creates an ApplicationContext, loads beans, and runs dependency injection, ApplicationRunner, and CommandLineRunner; however, it does not create an HTTP web server. Beans annotated with @RestController can still exist if scanned, yet the application will not serve HTTP endpoints merely because those beans exist. Background tasks, schedulers, or connections to external systems can still operate if configured.

**none is not server.port=0**: port 0 asks the operating system to pick an ephemeral free TCP port for the web server, whereas none does not start a web server at all.

## 2. How does Spring Boot choose by default?

When not explicitly configured, SpringApplication deduces WebApplicationType based on the web classes available at startup:

1. If **only WebFlux** matching the web stack is present, the application is typically deduced as **reactive**.
2. If **both Spring MVC and WebFlux are present**, Spring MVC is prioritized and the default is **servlet**.
3. If a suitable Servlet system is present and reactive-only conditions do not apply, the deduced type is **servlet**.
4. If no suitable web infrastructure is present, the application is deduced as **none**.

This is classpath-based deduction, not a choice based on controller package names or the return type of a method.

Common examples:

| Main dependency | Typical default type | Key note |
|---|---|---|
| spring-boot-starter-web | servlet | Starter brings Spring MVC and embedded Tomcat by default |
| spring-boot-starter-webflux | reactive | Starter brings WebFlux and Reactor Netty by default |
| Both starter-web and starter-webflux | servlet | Having WebClient does not switch the entire server to reactive |
| Plain spring-boot-starter only, no web stack | none | Application can run tasks without needing an HTTP server |

If a Spring MVC application needs to call external APIs with WebClient, having WebFlux on the classpath **does not require switching to reactive**. Spring MVC can remain the server web stack, while WebClient is simply an HTTP client used inside the application.

## 3. Setting it in application.yml or application.properties

### Specifying Servlet

~~~yaml
spring:
  main:
    web-application-type: servlet
~~~

Equivalent in application.properties:

~~~properties
spring.main.web-application-type=servlet
~~~

A project using servlet should have the matching dependency, for example in Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

This setting fits REST controllers using Spring MVC, Servlet filters, HandlerInterceptor, or servlet-based Spring Security. It does not automatically add dependencies if the project lacks starter-web.

### Specifying Reactive

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Typical dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

When genuinely building a WebFlux server, remove unnecessary Spring MVC dependencies to reduce auto-configuration ambiguity and avoid bringing Servlet components into a Reactive architecture. Explicitly setting reactive can help override default deduction when MVC components are on the classpath, yet this setting **does not** turn an MVC HandlerInterceptor into a WebFilter or transform a synchronous controller into a true reactive pipeline.

### Specifying not to start a web server

~~~yaml
spring:
  main:
    web-application-type: none
~~~

This is a clear choice when the same codebase carries web dependencies, yet a specific run only imports data or executes a worker. Beans that do not require HTTP are still initialized according to application configuration. If a configuration requires ServletWebServerApplicationContext or web-only beans, the application may fail when set to none; inspect those dependencies.

Only one effective value should be declared per run. You cannot simultaneously run both servlet and reactive ApplicationContexts in the same SpringApplication simply by listing multiple values for the property.

## 4. Overriding per environment and launch command

Configuration can be placed in application.yml, profile files, or passed externally. Example default application.yml:

~~~yaml
spring:
  main:
    web-application-type: servlet
~~~

When running without a web server, you can pass a program argument:

~~~bash
java -jar build/libs/my-app.jar --spring.main.web-application-type=none
~~~

Replace the JAR filename with the actual artifact. With the Gradle Spring Boot plugin:

~~~bash
./gradlew bootRun --args="--spring.main.web-application-type=none"
~~~

On Windows, you can use gradlew.bat instead of ./gradlew. The two commands above are alternative ways to launch, not steps to run sequentially in a single launch.

You can use an environment variable following Spring Boot's relaxed binding rules:

~~~bash
SPRING_MAIN_WEB_APPLICATION_TYPE=reactive
~~~

The line above shows the environment variable name and value; the exact syntax for setting it depends on the shell, Docker, Kubernetes, or deployment platform. Example configuration via application-reactive.yml:

~~~yaml
spring:
  config:
    activate:
      on-profile: reactive

  main:
    web-application-type: reactive
~~~

When the reactive profile is active, the corresponding property takes effect. A command-line argument normally takes precedence over values in application.yml under the default property source order; verify the effective configuration when multiple override sources exist.

Because the application type determines the ApplicationContext and web server during startup, **changing this configuration after the application has started does not switch the stack in place**. You must restart the application with the desired value.

## 5. Choosing the application type via Java API

If you want to select it directly in startup code, SpringApplication provides the setWebApplicationType method.

Example of a Spring Boot program **without starting an HTTP server**, file src/main/java/demo/BatchModeApplication.java:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BatchModeApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BatchModeApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }

    @Bean
    CommandLineRunner runBatch() {
        return args -> System.out.println("BATCH_DONE");
    }
}
~~~

This example requires a Spring Boot project with the spring-boot-starter dependency and the entry point configured to run BatchModeApplication. When Spring Boot starts successfully, alongside framework logs, the println statement outputs a line:

~~~text
BATCH_DONE
~~~

To run in a Gradle project configured with Spring Boot and the corresponding main class:

~~~bash
./gradlew bootRun
~~~

The value set in the example via Java API is **NONE**. If you need servlet or reactive via this API, use WebApplicationType.SERVLET or WebApplicationType.REACTIVE and ensure matching server dependencies are present. Avoid setting conflicting values between startup code and files/environment variables. Configuration sources bound by SpringApplication during startup can affect the effective value; keep a single clear decision source for each deployment mode.

SpringApplicationBuilder also supports specifying the application type when building the application. Choose between external configuration and programmatic configuration based on operational needs; external configuration is usually more convenient when running the same artifact in multiple modes.

## 6. Choosing the mode by use case

### Case A: Standard Spring MVC REST API

The application declares spring-boot-starter-web and uses @RestController returning DTOs, Servlet Filters, or Spring MVC HandlerInterceptor. Keeping the default servlet mode is usually sufficient; you can declare servlet explicitly to make the deployment contract visible and catch classpath changes.

### Case B: True WebFlux API server

The application uses WebFlux, Publisher/Mono/Flux or reactive functional endpoints, WebFilter, and non-blocking I/O. Use spring-boot-starter-webflux, avoid pulling in starter-web unnecessarily, and optionally set reactive explicitly. Also verify downstream resources: running blocking JDBC on the event loop can negate reactive benefits even when the ApplicationContext is reactive.

### Case C: Spring MVC calling external services with WebClient

The application uses starter-web and WebClient from the WebFlux library to call other APIs. The default remains servlet because MVC is present. Setting reactive just "to use WebClient" is unnecessary; WebClient does not require the server to be WebFlux.

### Case D: Running batch jobs or admin commands from the same artifact

The application has web dependencies, but a given run only needs ApplicationRunner/CommandLineRunner to migrate data. Use none to avoid starting an HTTP listener. If the program must exit after finishing, also inspect non-daemon threads, schedulers, clients, and bean lifecycles. none only omits the web server; it does not guarantee every background task stops automatically.

### Case E: Running multiple deployment variants

One codebase can be built into an artifact used both as a servlet API and as a batch worker. You can configure servlet for the web deployment and none for the worker deployment. However, check which beans are only valid in a Servlet context, which beans create background jobs, and which beans should be disabled per environment. The web application type does not automatically decide which business beans should run.

## 7. Relationship with auto-configuration and bean conditions

Spring Boot activates many auto-configurations based on **both** the application type and the classpath plus existing beans. The spring.main.web-application-type property affects building the ApplicationContext and configurations conditional on application type.

For example, an auto-configuration or bean conditional on Servlet is only evaluated when the context is actually Servlet; the corresponding Reactive condition applies to Reactive Web. Non-web conditions apply in a none context. Therefore, changing this value can cause certain beans to be created or omitted even when the project's Java files do not change.

Regarding request-processing systems, the two stacks do not share all integration classes:

| Component | Servlet MVC | Reactive WebFlux |
|---|---|---|
| HTTP server integration | Servlet web server | Reactive web server |
| Request dispatcher | DispatcherServlet | DispatcherHandler |
| Typical request API | HttpServletRequest | ServerWebExchange |
| Web filter | Servlet Filter | WebFilter |
| Security filter chain | SecurityFilterChain | SecurityWebFilterChain |
| Async/non-blocking handling | Requires APIs/approaches suited for Servlet MVC | Reactor and reactive streams are the core model |

If a project has security, filters, exception handlers, request binding, or API documentation written for MVC, verify compatibility before switching to reactive. Changing the ApplicationContext does not automatically rewrite those configurations.

Similarly, **@EnableWebMvc** and **@EnableWebFlux** are annotations for customizing the corresponding web configuration and should not be used in place of selecting WebApplicationType or to compensate for missing server dependencies.

## 8. Verifying the actual runtime mode

Do not look at a single configuration line and jump to conclusions; verify startup behavior and the effective ApplicationContext type.

1. **Inspect startup logs:** embedded Tomcat typically logs Tomcat startup; Reactor Netty typically logs Netty; with none, no web server is created by SpringApplication.
2. **Test endpoints:** servlet and reactive can serve HTTP if the server and mappings are configured. none does not open an HTTP server.
3. **Check ApplicationContext type:** Servlet contexts typically implement ServletWebServerApplicationContext; reactive ones typically implement ReactiveWebServerApplicationContext; none typically uses AnnotationConfigApplicationContext unless factory customization is present.
4. **Inspect the auto-configuration report if needed:** run with debug enabled to see which configuration conditions matched or did not match.

Example to enable debug on a run:

~~~bash
java -jar build/libs/my-app.jar --debug
~~~

Do not definitively infer "reactive" just because the application has the reactor-core dependency, a method returning Mono, or uses WebClient. What decides it is the effective web application type and the web/server configuration actually activated.

Note: concrete context types can be customized; checking the web context interface and actual logs is more accurate than hardcoding a comparison against a single class name.

## 9. Common errors and how to fix them

### 9.1. Added WebFlux, but the application still runs MVC

**Symptom:** both starter-web and starter-webflux are present, requests still pass through DispatcherServlet, or logs show a Tomcat Servlet server.

**Cause:** when both MVC and WebFlux are present, Spring Boot defaults to servlet.

**Fix:** if you only need WebClient, keep servlet. If you want a reactive server, investigate why starter-web is present, remove the unnecessary MVC dependency, use starter-webflux, and specify reactive where appropriate. Re-check Security, Filters, and controllers before running.

### 9.2. Set reactive, but the application fails to start

**Symptom:** auto-configuration errors involving ReactiveWebServerFactory, no suitable reactive web server found, or beans configured for servlet are missing.

**Possible causes:** missing reactive server dependency, configuration beans depending on Servlet context, or incompatible starter combinations.

**Fix:** check the dependency tree; verify starter-webflux and a compatible reactive web server are present; read the full root cause in startup logs; separate Servlet-only configurations from reactive configurations. Do not mask errors by randomly excluding auto-configurations.

### 9.3. Set none, yet controllers do not receive requests

**Symptom:** HTTP requests have nowhere to connect or connections are refused.

**Cause:** none does not start a web server. @RestController alone is not enough to create an HTTP listener.

**Fix:** use servlet or reactive if the application truly needs HTTP; keep none if the intent is batch/worker. Verify health probes, load balancers, and port expectations of the deployment environment.

### 9.4. Configured servlet, but no Servlet web server exists

**Symptom:** Spring Boot reports it cannot create ServletWebServerFactory or cannot start the web server.

**Possible causes:** only servlet was set in config while the required starter and embedded server are missing, or the server was excluded.

**Fix:** declare starter-web or a supported server dependency properly; inspect the dependency tree and exclusions. This property cannot substitute for missing jars on the classpath.

### 9.5. Enabled reactive for performance, yet latency remains high

**Symptom:** requests are slow when calling the database or external APIs.

**Cause:** blocking JDBC, synchronous HTTP calls, heavy CPU operations, or other resource waits can still occupy threads or stall the event loop.

**Fix:** measure latency/thread/pool metrics, use non-blocking drivers and clients where appropriate, bound concurrency, and offload blocking work from the event loop. Setting reactive mode alone does not guarantee higher throughput.

### 9.6. Profiles and launch arguments produce different results

**Symptom:** application.yml specifies servlet, yet the application starts in none or reactive mode.

**Possible causes:** profile-specific files, environment variables, or command-line arguments are overriding the value.

**Fix:** inspect active profiles, configuration sources, and the actual launch command. Pick one clear configuration source per deployment and verify the effective value at startup.

## 10. Distinguishing from similar-looking properties

- **server.port** picks the port for the running web server; it does not choose Servlet, Reactive, or None.
- **spring.main.lazy-initialization** changes the bean initialization strategy; it does not change the web stack.
- **spring.threads.virtual.enabled** affects how Spring Boot uses virtual threads in supported components; it does not change the choice between Servlet and Reactive.
- **spring.profiles.active** selects active configuration groups; it can indirectly affect the web application type if a profile file sets that property.
- **server.shutdown** and graceful shutdown properties control stopping the web server; they are not switches for choosing web application type.
- **management.endpoints.web.exposure.include** configures Actuator endpoints exposed over HTTP when web infrastructure is present; it does not create a web server for none.

Do not use the properties above to resolve confusion about web mode.

## 11. Decision process before specifying explicitly

1. Determine whether the application is an MVC HTTP API, a WebFlux HTTP API, or a process that does not serve HTTP.
2. Inspect actual dependencies; if both starter-web and starter-webflux exist, clarify which starter is for the **server** and which library is only for the **client**.
3. Pick servlet, reactive, or none matching the code and execution flow; prefer removing redundant dependencies before forcing a type to mask a conflict.
4. Set spring.main.web-application-type in a single clear configuration source, or select via the SpringApplication API if the application genuinely needs programmatic control.
5. Start up and inspect logs, ApplicationContext, HTTP endpoints, auto-configurations, and loaded dependencies.
6. Test business flows and web-stack-dependent components such as security, filters, exception handlers, schedulers, and actuator.
7. Verify post-deployment behavior: ports, readiness probes, batch lifecycle, and resource metrics.

**Rule of thumb:** let Spring Boot deduce automatically when the classpath clearly reflects the design; specify explicitly when you need to clarify a deployment mode or handle a special case. The web-application-type value must align with dependencies and source code; it determines which type of application is launched, rather than rebuilding the web stack for you.
