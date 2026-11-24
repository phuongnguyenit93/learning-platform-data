# Distinguishing Spring Framework Configuration from Spring Boot Auto-Configuration in WebFlux

## 1. Two configuration layers solving two different jobs

**Spring WebFlux is part of Spring Framework.** The framework provides the reactive programming model, HTTP processing components, annotated controllers, functional endpoints, codecs, handler mappings, and configuration APIs. For those components to work, an application needs a way to initialize and assemble them.

**Spring Boot adds the auto-configuration mechanism**: based on dependencies, the application type, already-declared beans, and properties, it creates many required components automatically. Boot also integrates an embedded server, default configuration, property management, and operational utilities.

Therefore, when people say "configuring WebFlux with Spring Framework", they are usually talking about **deliberately enabling and customizing the WebFlux infrastructure**. When they say "Spring Boot auto-configures WebFlux", they mean Boot **automatically activates and combines the Framework infrastructure together with Boot's integrations**.

You can view it in two layers:

~~~text
Application (Controller / RouterFunction / Service)
                    |
                    v
        Spring WebFlux (Framework)
  HandlerMapping, HandlerAdapter, codecs,
  exception handling, WebFilter, HttpHandler...
                    |
                    v
        HTTP server runtime
  Reactor Netty / Tomcat / Jetty ...
                    |
                    v
          Network / HTTP clients

Spring Boot adds:
  - reactive web application and classpath detection
  - automatic configuration of WebFlux infrastructure
  - embedded server and server properties
  - codecs, static resources, WebJars, error defaults
  - conditions to back off when the application provides configuration itself
~~~

**Spring Boot does not replace Spring WebFlux.** Boot calls and configures the Framework's components, helping the application start faster. A plain Framework application can still use WebFlux, but the developer must manage more initialization steps themselves.

## 2. Configuring WebFlux at the Spring Framework level

At the Framework level, Java configuration can use `@EnableWebFlux`:

~~~java
@Configuration
@EnableWebFlux
public class WebConfig {
}
~~~

`@EnableWebFlux` imports the `DelegatingWebFluxConfiguration` configuration, which is based on `WebFluxConfigurationSupport`. This configuration registers the infrastructure components needed to handle annotated controllers and functional endpoints, and also provides defaults appropriate for the dependencies on the classpath (for example, JSON codecs when the corresponding library is present).

After enabling the infrastructure, you can implement `WebFluxConfigurer` to customize it:

~~~java
@Configuration
@EnableWebFlux
public class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                  .maxInMemorySize(512 * 1024);
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedMethods("GET", "POST");
    }
}
~~~

The example sets the memory limit for HTTP message codecs to 512 KiB and declares CORS for the `/api/**` path. This is a **Framework configuration pattern**; it requires importing `org.springframework.context.annotation.*`, `org.springframework.web.reactive.config.*`, and `org.springframework.http.codec.ServerCodecConfigurer`.

### What does WebFluxConfigurer do?

`WebFluxConfigurer` is a set of callbacks to add configuration to the WebFlux infrastructure. Common customization points:

| Callback | Purpose |
| --- | --- |
| `configureHttpMessageCodecs` | Add, adjust, or replace readers/writers for JSON, text, binary, and other media types |
| `addFormatters` | Register converters and formatters for request data |
| `configureContentTypeResolver` | Adjust how the media type is determined from `Accept` or another strategy |
| `addCorsMappings` | Configure global CORS by URL |
| `configureViewResolvers` | Declare view resolvers for applications returning HTML/templates |
| `configurePathMatching` | Adjust path matching rules |
| `configureArgumentResolvers` | Register resolvers for controller parameters when needed |
| `configureBlockingExecution` | Configure the executor for controller methods considered blocking in Framework versions that support this API |
| `getValidator` | Choose the shared validator for WebFlux |

Not every application needs to override all callbacks. You should configure only the parts with specific requirements to keep the useful Framework defaults.

### What else is needed if not using Spring Boot?

`@EnableWebFlux` enables the Spring WebFlux infrastructure, but **does not by itself provide the entire server runtime and bootstrap of a standalone application**. A plain Framework application needs:

1. Required Spring dependencies such as `spring-webflux`, `spring-context`, and Reactor.
2. A compatible HTTP server, such as Reactor Netty, reactive Tomcat, or reactive Jetty, along with the corresponding dependencies.
3. A Spring `ApplicationContext` to register controllers, routers, and configuration.
4. A way to connect WebFlux's `HttpHandler` to the server runtime and manage the server's start/stop lifecycle.

Example of plain Framework configuration:

~~~java
package com.example.web;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.EnableWebFlux;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
@EnableWebFlux
@ComponentScan(basePackages = "com.example.web")
public class FrameworkWebFluxConfig implements WebFluxConfigurer {
}
~~~

This is a **configuration class**, not a standalone server program. It turns on the infrastructure and scans controllers; the HTTP server bootstrap part still has to be assembled by the application itself or provided by another platform. When using the Framework directly, you take clearer responsibility for server dependencies, listening ports, TLS configuration, lifecycle, and runtime integration.

## 3. What does Spring Boot auto-configuration do?

In a Boot application, the dependency commonly used is `spring-boot-starter-webflux`. The starter pulls in the components required for WebFlux and provides Reactor Netty as the reactive embedded server by default. Boot also supports other reactive servers such as Tomcat and Jetty when you swap in the appropriate dependency.

A typical Boot application:

~~~java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` includes component scanning and enables auto-configuration. When the classpath and application type fit, Boot configures WebFlux automatically. Usually you do not need to declare `@EnableWebFlux` yourself.

WebFlux auto-configuration is applied conditionally, for example:

- The application is recognized as a **reactive web application**.
- The required WebFlux classes are on the classpath.
- No foundational WebFlux configuration has already been provided by the application itself.

The conditional mechanism helps Boot avoid re-registering the infrastructure when the developer has already configured it manually. Internal class and package names can change across major Boot versions; what matters is understanding the principle of **conditional auto-configuration**.

### What extra things does Boot provide?

Spring Boot adds many integrations on top of the Framework defaults:

- **Codec properties and customizers:** configure HTTP readers/writers, memory limits, JSON/Jackson, and codecs through properties or customizer beans.
- **Static resources:** automatically serve content from classpath directories such as `/static`, `/public`, `/resources`, `/META-INF/resources` as configured.
- **WebJars and welcome page:** support WebJars resources and a default welcome page.
- **Embedded reactive server:** automatically creates the server and configures ports, SSL, compression, and common server properties.
- **Error handling:** provides default error handling for HTTP responses; the application can add `ErrorAttributes`, `ErrorWebExceptionHandler`, or other appropriate mechanisms.
- **Properties and ecosystem integration:** ties WebFlux configuration to `application.properties`/`application.yaml`, logging, metrics, actuator, and related auto-configurations.

For example, instead of creating a server and configuring the port manually, you can set:

~~~properties
server.port=8081
spring.webflux.static-path-pattern=/assets/**
spring.http.codecs.max-in-memory-size=512KB
~~~

Property names and support may differ between Boot versions. Check the documentation for your project's exact version before using a new property.

## 4. Relationship between @EnableWebFlux and WebFluxConfigurer in Spring Boot

This is the most important point when moving from Framework configuration to Boot.

### Want to keep Boot's auto-configuration: implement WebFluxConfigurer only

In Boot, if you only want to add configuration, declare a `@Configuration` that implements `WebFluxConfigurer` **without adding `@EnableWebFlux`**:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.http.codec.ServerCodecConfigurer;

@Configuration(proxyBeanMethods = false)
public class WebFluxCustomization implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                  .maxInMemorySize(512 * 1024);
    }
}
~~~

Boot still manages the WebFlux infrastructure, embedded server, static resources, and auto-configured integrations; the application's callbacks add changes on top of that configuration.

### Adding @EnableWebFlux: the application takes control of the WebFlux infrastructure itself

If you declare:

~~~java
@Configuration
@EnableWebFlux
public class WebFluxCustomization implements WebFluxConfigurer {
}
~~~

`@EnableWebFlux` imports `WebFluxConfigurationSupport` through `DelegatingWebFluxConfiguration`. Boot sees that the application has already provided foundational WebFlux configuration, so **WebFlux auto-configuration backs off**. You take more responsibility for the WebFlux configuration and the default integrations that auto-configuration provides.

That **does not mean all of Spring Boot is disabled**: other unrelated auto-configurations can still run. The scope to pay attention to is the WebFlux infrastructure and the Boot parts directly tied to it.

### Quick comparison

| How it is declared in Boot | Result |
| --- | --- |
| No `WebFluxConfigurer`, no `@EnableWebFlux` | Boot auto-configures WebFlux with defaults |
| Implement `WebFluxConfigurer`, no `@EnableWebFlux` | Keeps Boot auto-configuration and adds customization callbacks |
| Add `@EnableWebFlux` | The application enables Framework configuration; Boot's WebFlux auto-configuration backs off |
| Declare low-level infrastructure beans yourself | May cause part of auto-configuration to back off depending on bean conditions; must check conditions and dependent beans |

There is no need to add `@EnableWebFlux` just because you want to override codecs, CORS, or formatters in a normal Boot application.

## 5. Runnable Java 17+ example with Spring Boot

This example uses **Spring Boot 3.5.0 and Java 17+**. The goal is to launch WebFlux with auto-configuration, add a controller, and customize codecs using `WebFluxConfigurer` without enabling `@EnableWebFlux`.

Project structure:

~~~text
webflux-boot-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/demo/
                ├── DemoApplication.java
                ├── GreetingController.java
                └── WebFluxCustomization.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-boot-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

File `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/demo/GreetingController.java`:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class GreetingController {

    @GetMapping("/hello")
    public Mono<Map<String, String>> hello() {
        return Mono.just(Map.of("message", "Hello WebFlux"));
    }
}
~~~

File `src/main/java/com/example/demo/WebFluxCustomization.java`:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class WebFluxCustomization implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                  .maxInMemorySize(512 * 1024);
    }
}
~~~

Run in the `webflux-boot-demo` directory with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Call the endpoint in another terminal:

~~~bash
curl http://localhost:8080/hello
~~~

Expected JSON body:

~~~json
{"message":"Hello WebFlux"}
~~~

What to observe:

1. `spring-boot-starter-webflux` puts WebFlux and the reactive server runtime onto the classpath.
2. `@SpringBootApplication` enables the auto-configuration mechanism.
3. Boot initializes the default server on port 8080 and assembles the WebFlux components.
4. Component scan detects `GreetingController`; the framework maps `GET /hello`.
5. `WebFluxCustomization` is detected as a customization configuration; because **there is no `@EnableWebFlux`**, Boot still keeps WebFlux auto-configuration.
6. The controller returns a `Mono`; the framework writes the result as JSON through the configured codecs.

This is a complete Boot application. You do not need to create an `HttpHandler`, `ReactorHttpHandlerAdapter`, call `HttpServer.bindNow()`, or manage the server lifecycle manually.

## 6. Same idea when using plain Spring Framework

Without Boot, the Framework configuration class usually needs to enable WebFlux explicitly:

~~~java
package com.example.web;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.web.reactive.config.EnableWebFlux;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.http.codec.ServerCodecConfigurer;

@Configuration
@EnableWebFlux
@ComponentScan(basePackages = "com.example.web")
public class FrameworkWebConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                  .maxInMemorySize(512 * 1024);
    }
}
~~~

This configuration does two things: enables the Framework's WebFlux infrastructure and registers the codec customization. When running a real application, you need to create an `ApplicationContext`, connect `HttpHandler` to a compatible server runtime, and manage start/stop. Those parts are usually done automatically by Boot when using `spring-boot-starter-webflux`.

Comparison of responsibilities:

| Responsibility | Plain Framework | Spring Boot |
| --- | --- | --- |
| Enable WebFlux infrastructure | `@EnableWebFlux` or advanced configuration | Boot conditional auto-config |
| Customize codecs/CORS/formatters | `WebFluxConfigurer` | `WebFluxConfigurer` or Boot properties/customizers |
| Register controllers | `ApplicationContext`, component scan, or beans | Component scan from `@SpringBootApplication` |
| Choose and add server | Add dependency/runtime yourself | Default starter provides server, can be replaced |
| Initialize HTTP handler/server | Assemble and manage lifecycle yourself | Boot creates embedded server and wires infrastructure |
| Manage common properties | Build configuration yourself | `application.properties`/`application.yaml` and typed properties |

## 7. Choosing the right dependencies and application type

To run a WebFlux server with Boot, you usually add:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

If the application only wants to use **`WebClient`** as a reactive HTTP client inside a Spring MVC application, you may still see `spring-boot-starter-webflux` on the classpath. When both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present together, Spring Boot **chooses Spring MVC by default**, because many MVC applications only add WebFlux to use `WebClient`.

If you really want to run a WebFlux server when both starters are present, you must explicitly choose the reactive application type, for example:

~~~java
SpringApplication application =
        new SpringApplication(DemoApplication.class);
application.setWebApplicationType(WebApplicationType.REACTIVE);
application.run(args);
~~~

This is an alternative startup approach in the main class; it is not strictly necessary if the project only has `spring-boot-starter-webflux`. In a real project, check the dependency tree to see whether the MVC starter is being pulled in indirectly by another dependency.

Boot uses Reactor Netty by default for `spring-boot-starter-webflux`; you can still use another reactive server if you exclude the default server dependency and add the corresponding starter. Choosing the server is a runtime decision, not something `@EnableWebFlux` decides on its own.

## 8. When do you need to inspect auto-configuration?

When a bean or configuration does not appear as expected, check in this order:

1. **Classpath:** are `spring-webflux`, codecs, and a suitable server runtime present?
2. **Application type:** is Boot starting a reactive or a servlet application?
3. **Auto-configuration conditions:** did an already-existing infrastructure bean cause WebFlux auto-config to back off?
4. **Annotations:** is `@EnableWebFlux` present on another configuration class?
5. **Component scan:** are the controller and configuration within the scan area of the application class?
6. **Custom beans:** did a `HandlerMapping`, `WebFluxConfigurationSupport`, or low-level component bean change the default conditions?
7. **Properties and codecs:** did memory limits, media types, static paths, or server settings cause requests/responses to behave unexpectedly?

You can enable condition evaluation logging when diagnosing:

~~~properties
debug=true
~~~

Boot will print the auto-configuration condition report during startup. Look for entries related to WebFlux to see which configuration matched, which backed off, and why.

In a development environment, the Actuator `conditions` endpoint can also help inspect the condition report if the endpoint is enabled and properly secured. Do not expose sensitive management endpoints publicly just for debugging.

## 9. Common mistakes

1. **Adding `@EnableWebFlux` to a Boot application just to adjust codecs:** causes Boot's WebFlux auto-configuration to back off. If you only need customization, use a `WebFluxConfigurer` bean without adding the annotation.
2. **Assuming `WebFluxConfigurer` turns on WebFlux by itself in plain Framework:** the interface is only callbacks. Plain Framework needs WebFlux configuration enabled with `@EnableWebFlux` or advanced mode.
3. **Assuming `@EnableWebFlux` starts an HTTP server by itself:** it turns on the Framework infrastructure; the server runtime and bootstrap still need to be provided.
4. **Confusing the WebFlux Framework with Spring Boot:** WebFlux belongs to the Framework; Boot only provides auto-configuration and convenient integrations.
5. **Using both starters together while expecting Boot to choose WebFlux automatically:** Boot defaults to MVC when both MVC and WebFlux starters are present; check and select the application type if a reactive server is intended.
6. **Declaring low-level infrastructure beans without understanding conditions:** can cause auto-configuration to back off, leading to missing codecs, handlers, or static resources.
7. **Duplicated configuration:** manually declaring infrastructure, adding `@EnableWebFlux`, and relying on Boot at the same time can create duplicate beans or change handler ordering.
8. **Assuming every property belongs to Spring Framework:** many properties such as `spring.webflux.*` or `server.*` are Boot features; plain Framework does not read Boot properties automatically.
9. **Forgetting the server runtime when using plain Framework:** having WebFlux classes is not enough to open an HTTP port.
10. **Assuming adding WebFlux makes every library non-blocking:** auto-configuration does not turn blocking JDBC or SDKs into reactive; you must choose suitable drivers/clients.
11. **Customizing codecs without considering payload size:** setting `maxInMemorySize` too large can increase memory usage under many concurrent requests; pick a limit according to data and load.
12. **Not checking versions:** callback APIs, packages, properties, and auto-configuration can change between Spring Framework/Spring Boot major versions; check the documentation matching your dependency version.

## 10. Quick decision table

| Situation | Appropriate approach |
| --- | --- |
| New Spring Boot WebFlux project | Add `spring-boot-starter-webflux`, use `@SpringBootApplication`, let Boot auto-config |
| Only adjust codecs, CORS, formatters in Boot | Declare `@Configuration` implementing `WebFluxConfigurer`, **without** `@EnableWebFlux` |
| Want to control the entire WebFlux infrastructure yourself in Boot | Use `@EnableWebFlux` and take responsibility for the required WebFlux configuration |
| Spring Framework application without Boot | Use `@EnableWebFlux`/advanced configuration, manage context, server runtime, and bootstrap yourself |
| Use `WebClient` in an MVC application | You can add the WebFlux dependency; Boot still defaults to MVC if both starters are present |
| Replace Reactor Netty with another reactive server in Boot | Replace the server dependency with the corresponding starter/runtime |
| Don't understand why Boot isn't creating WebFlux beans | Check classpath, application type, `@EnableWebFlux`, infrastructure beans, and condition report |

## 11. Self-check questions

**1. Does Spring WebFlux belong to Spring Framework or Spring Boot?** WebFlux belongs to **Spring Framework**. Spring Boot provides auto-configuration and integrations to launch it conveniently.

**2. What does `@EnableWebFlux` do?** It enables Java configuration for WebFlux by importing Framework configuration such as `DelegatingWebFluxConfiguration`.

**3. Does `WebFluxConfigurer` enable WebFlux on its own?** No. It provides customization callbacks for infrastructure that has already been enabled/provided.

**4. In Spring Boot, if you only want to adjust codecs, do you need `@EnableWebFlux`?** No. Declare `WebFluxConfigurer` without adding `@EnableWebFlux` to keep Boot's auto-configuration.

**5. Why can `@EnableWebFlux` cause Boot's WebFlux auto-configuration to back off?** Because the annotation imports foundational WebFlux configuration; Boot's auto-configuration conditions apply only when no corresponding foundational configuration already exists.

**6. Does plain Framework create an embedded Reactor Netty server automatically?** Not via Boot's auto-configuration mechanism. The application needs to add a runtime and bootstrap the server itself.

**7. What else does Boot provide beyond the Framework infrastructure?** Starters, embedded server, codecs/customizers, static resources, WebJars, properties, default error handling, and ecosystem integrations.

**8. If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, what does Boot choose by default?** Spring MVC; you can explicitly choose `WebApplicationType.REACTIVE` if you really want a WebFlux server.

**9. Does `@EnableWebFlux` disable all of Spring Boot?** No. It causes WebFlux auto-configuration to back off; other auto-configurations can still run.

**10. When should you use plain Framework?** When you need to control bootstrapping and infrastructure configuration yourself, or integrate into an existing runtime platform. For typical server applications, Boot significantly reduces assembly work.

**Remember:** Spring Framework provides the **WebFlux infrastructure and configuration APIs**. `@EnableWebFlux` enables that infrastructure; `WebFluxConfigurer` lets you customize it. Spring Boot automatically activates and integrates the infrastructure based on dependencies, application type, beans, and properties. In a Boot application, use `WebFluxConfigurer` **without `@EnableWebFlux`** for ordinary customizations; enable `@EnableWebFlux` only when you intentionally want to control the WebFlux configuration yourself.

**Official documentation:** [Spring Framework — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html), [Spring Boot — Reactive Web Applications and WebFlux Auto-configuration](https://docs.spring.io/spring-boot/reference/web/reactive.html), [Spring Boot — Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html).