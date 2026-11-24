# How Spring Boot Deduces the Application Type from the Classpath

## Objectives

Spring Boot needs to know which web model an application runs on before creating the ApplicationContext and configuring web components. This choice affects the ApplicationContext type, the web server, which auto-configurations are activated, and how requests are handled.

After this lesson, you will be able to:

- Distinguish the three values of WebApplicationType: SERVLET, REACTIVE, and NONE.
- Explain which classes on the runtime classpath Spring Boot relies on to deduce the application type.
- Understand why adding a starter can change the ApplicationContext type.
- Proactively configure the application type when needed.
- Inspect the dependency tree to find out why an application selected the wrong web stack.

## 1. What is WebApplicationType?

**WebApplicationType** is a Spring Boot enum describing the application model that SpringApplication will launch. The enum has three values:

| Value | Meaning | Typical ApplicationContext |
|---|---|---|
| SERVLET | Web application based on the Servlet API, typically using Spring MVC | AnnotationConfigServletWebServerApplicationContext |
| REACTIVE | Reactive web application, typically using Spring WebFlux | AnnotationConfigReactiveWebServerApplicationContext |
| NONE | Application that does not launch a web server | AnnotationConfigApplicationContext |

This is an application-level choice. It determines which type of context Spring Boot creates and which group of web configurations it enables.

**SERVLET** is suitable for traditional Spring MVC applications. Requests flow through the Servlet container, Filter chain, and DispatcherServlet. With the default starter, embedded Tomcat is typically used.

**REACTIVE** is suitable for Spring WebFlux applications. The framework uses the Reactive Streams model with types such as Mono and Flux; the common default runtime when using the WebFlux starter is Reactor Netty.

**NONE** is suitable for command-line, batch, or background task applications that do not need an HTTP server. Spring still creates an ApplicationContext to manage beans and dependency injection, but it does not create a web server.

Note: WebApplicationType is not the name of a web server. Choosing SERVLET does not necessarily require using Tomcat; the specific server also depends on dependencies and configuration. Similarly, REACTIVE describes the application model, while Reactor Netty is a common runtime option.

## 2. Spring Boot deduces from the runtime classpath

When creating SpringApplication, Spring Boot checks for the presence of specific indicator classes on the classpath. Here, the classpath refers to the actual set of libraries that the JVM can load when running the application, including direct dependencies and transitive dependencies.

Spring Boot does not directly read the contents of pom.xml or build.gradle at deduction time. The build tool resolves dependencies first; then the application runs with the resulting runtime classpath.

In Spring Boot 3.x, the key indicator classes include:

| Class | Role in detection |
|---|---|
| org.springframework.web.reactive.DispatcherHandler | Primary indicator of Spring WebFlux |
| org.springframework.web.servlet.DispatcherServlet | Indicator of Spring MVC |
| org.glassfish.jersey.servlet.ServletContainer | Indicator of Jersey running on Servlet |
| jakarta.servlet.Servlet | Jakarta Servlet API |
| org.springframework.web.context.ConfigurableWebApplicationContext | Spring Servlet web context type |

The deduction mechanism can be expressed in the following order:

1. Check for the WebFlux **DispatcherHandler** class.
2. If DispatcherHandler is present, while Spring MVC's DispatcherServlet is absent and Jersey's ServletContainer is also absent, Spring Boot chooses **REACTIVE**.
3. If the reactive condition is not met, Spring Boot checks the Servlet indicator classes. In Spring Boot 3.x, the two required classes are **jakarta.servlet.Servlet** and **ConfigurableWebApplicationContext**.
4. If either Servlet indicator class is missing, Spring Boot chooses **NONE**.
5. If the Servlet indicator classes are all present, Spring Boot chooses **SERVLET**.

This can be summarized in a diagram:

~~~mermaid
flowchart TD
    A[SpringApplication initializes] --> B{Is DispatcherHandler on classpath?}
    B -- No --> E{Are all Servlet indicator classes present?}
    B -- Yes --> C{Are DispatcherServlet and Jersey ServletContainer both absent?}
    C -- Yes --> R[REACTIVE]
    C -- No --> E
    E -- Yes --> S[SERVLET]
    E -- No --> N[NONE]
~~~

The key point to remember is that the reactive branch is evaluated before the Servlet branch. If an application has both Spring MVC and Spring WebFlux, the condition for choosing REACTIVE is not satisfied because DispatcherServlet is present. When the Servlet indicator classes are also present, the result is SERVLET.

Jersey is a special case in the reactive condition: if Jersey ServletContainer is present, Spring Boot does not choose REACTIVE based solely on DispatcherHandler; the result is then determined by the Servlet indicator classes.

### Examples of common scenarios

| Runtime classpath | Typical result | Explanation |
|---|---|---|
| Has spring-boot-starter-web | SERVLET | The starter brings Spring MVC, Servlet API, and embedded Tomcat onto the runtime classpath |
| Has spring-boot-starter-webflux, no MVC or Jersey Servlet | REACTIVE | DispatcherHandler is present; reactive exclusion indicators are absent |
| Has both starter-web and starter-webflux | SERVLET | DispatcherServlet is present, so the condition for REACTIVE is not satisfied |
| No WebFlux indicator and missing Servlet indicator | NONE | Not enough classes to select the Servlet model |
| Console application with no web dependencies | NONE | No suitable web runtime |

The table describes typical dependency configurations. Transitive dependencies brought in by other libraries can also change the result; therefore, inspect the actual runtime classpath when the outcome differs from expectations.

## 3. The role of starters

Starters are a convenient way to declare a group of related dependencies. Web starters do not just add annotations for writing controllers; they also bring the corresponding framework and runtime onto the classpath.

### 3.1. Spring MVC with spring-boot-starter-web

Maven declaration:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

This starter typically brings the following components onto the runtime classpath:

- Spring Web MVC, providing DispatcherServlet and the Servlet controller model.
- The Servlet API matching the Spring Boot version.
- Embedded Tomcat according to the starter's default configuration.
- Libraries supporting HTTP data conversion, typically including Jackson for JSON.

Because DispatcherServlet and the Servlet indicator classes are present, Spring Boot typically deduces the application type as SERVLET.

### 3.2. Spring WebFlux with spring-boot-starter-webflux

Maven declaration:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

This starter brings Spring WebFlux and the common default reactive runtime, Reactor Netty, onto the classpath. When Spring MVC and Jersey ServletContainer are absent, DispatcherHandler is the signal for Spring Boot to choose REACTIVE.

WebFlux can use several controller annotations that look like Spring MVC, but request handling and the runtime differ. You should not look solely at @RestController to conclude whether an application is using Servlet or Reactive.

### 3.3. When both starters are declared

If a project declares both spring-boot-starter-web and spring-boot-starter-webflux, the dependency graph typically contains both DispatcherServlet and DispatcherHandler. Following the deduction order, Spring Boot chooses SERVLET when the Servlet indicator classes are present.

This often happens when another library or module pulls in spring-webmvc as a transitive dependency. The development team may think the application only uses WebFlux, yet the runtime classpath contains MVC.

If the goal is to build a reactive application, review dependencies to remove Spring MVC when it is not needed. Merely forcing the application type to REACTIVE while keeping many MVC dependencies can complicate configuration and make it harder for the team to understand the actual runtime.

## 4. How does the application type affect the startup process?

WebApplicationType deduction occurs during the SpringApplication preparation phase. The result is used when creating the ApplicationContext and applying auto-configurations.

General flow:

1. The JVM runs the class with the main method.
2. The application creates a SpringApplication object.
3. Spring Boot deduces WebApplicationType from the runtime classpath, unless the application type has been explicitly configured.
4. SpringApplication prepares the Environment and initial configurations.
5. Boot creates the ApplicationContext matching the application type.
6. Auto-configuration registers the corresponding beans.
7. For SERVLET or REACTIVE, the appropriate web server factory creates the embedded server.
8. The context is refreshed; the server starts accepting requests and the application finishes starting up.

Three common context types:

- **SERVLET:** AnnotationConfigServletWebServerApplicationContext, integrating ServletWebServerFactory and Spring MVC components.
- **REACTIVE:** AnnotationConfigReactiveWebServerApplicationContext, integrating ReactiveWebServerFactory and WebFlux components.
- **NONE:** AnnotationConfigApplicationContext, a standard Spring context without an embedded web server.

Auto-configurations often use conditions such as @ConditionalOnWebApplication to register beans only when the application type matches. Therefore, changing WebApplicationType can cause a group of auto-configurations to be enabled or disabled.

Distinguish between two decisions:

- **WebApplicationType:** whether the application uses Servlet, Reactive, or does not run web.
- **Web server implementation:** the specific server chosen from present dependencies, such as Tomcat or Jetty on the Servlet stack, and Reactor Netty as a common option on the Reactive stack.

## 5. Observing the application type in Java code

In a project with Spring Boot dependencies, you can instantiate SpringApplication and inspect the deduced value before calling run.

Example:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebTypeApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(WebTypeApplication.class);

        System.out.println(
                "Detected WebApplicationType: "
                        + application.getWebApplicationType()
        );

        application.run(args);
    }
}
~~~

Explanation:

- The SpringApplication constructor determines the application type based on the classpath.
- getWebApplicationType() returns the value deduced or configured on the object.
- run(args) executes the context initialization and application startup process.

If the runtime classpath contains starter-web in a typical setup, the output line will look like:

~~~text
Detected WebApplicationType: SERVLET
~~~

If only starter-webflux is present without reactive-excluding classes, the output looks like:

~~~text
Detected WebApplicationType: REACTIVE
~~~

If no suitable web dependencies are present, the output is typically:

~~~text
Detected WebApplicationType: NONE
~~~

These results depend on actual dependencies. A single fixed value cannot be stated without knowing the project's runtime classpath.

## 6. Proactively configuring WebApplicationType

Automatic deduction covers most typical applications. However, you can configure it explicitly when an application has a special classpath or when you need to control the runtime environment.

### 6.1. Using SpringApplication.setWebApplicationType

Example forcing the application to run on the Servlet stack:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(Application.class);

        application.setWebApplicationType(WebApplicationType.SERVLET);
        application.run(args);
    }
}
~~~

You can replace SERVLET with REACTIVE or NONE:

~~~java
application.setWebApplicationType(WebApplicationType.REACTIVE);
~~~

~~~java
application.setWebApplicationType(WebApplicationType.NONE);
~~~

Configuring via the API is useful when SpringApplication creation is controlled in Java code. The explicitly set type overrides the default deduced result for that run.

### 6.2. Using application.properties

You can configure it in **src/main/resources/application.properties**:

~~~properties
spring.main.web-application-type=servlet
~~~

Valid values:

~~~properties
spring.main.web-application-type=servlet
~~~

~~~properties
spring.main.web-application-type=reactive
~~~

~~~properties
spring.main.web-application-type=none
~~~

Or using YAML:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

The configuration property is suitable when you want to select the runtime by profile or deployment environment without modifying the main class.

Do not force REACTIVE just to try to boost performance if business libraries remain blocking or the application still depends on Servlet. Choose the model based on architecture and actual libraries.

## 7. Inspecting dependencies when Spring Boot picks the wrong application type

When an application starts with an unexpected server or fails to create a web server, inspect the dependency graph before modifying code.

### 7.1. With Maven

List web-related dependencies:

~~~bash
mvn dependency:tree
~~~

You can filter key dependencies:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-web,org.springframework.boot:spring-boot-starter-webflux,org.springframework:spring-webmvc,org.springframework:spring-webflux
~~~

Look for notable libraries:

- spring-webmvc and DispatcherServlet: MVC indicators.
- spring-webflux and DispatcherHandler: WebFlux indicators.
- spring-boot-starter-tomcat: embedded Tomcat.
- reactor-netty-http: Reactor Netty runtime.
- jakarta.servlet-api: Servlet API in Spring Boot 3.x applications.

If spring-webmvc appears without being directly declared, check which dependency pulled it in.

### 7.2. With Gradle

View all runtime dependencies:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Find why a dependency was brought in:

~~~bash
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
~~~

Or inspect WebFlux:

~~~bash
./gradlew dependencyInsight --dependency spring-webflux --configuration runtimeClasspath
~~~

The dependencyInsight output helps identify which direct or transitive module introduced the library into the project.

### 7.3. Observing during startup

Some signs in the logs:

- A Tomcat started message typically indicates the application is running on the Servlet stack with Tomcat.
- A Netty started message typically appears for WebFlux applications using Reactor Netty.
- A NONE application will have no embedded web server startup log line.

You can enable the auto-configuration condition evaluation report with the **--debug** argument:

~~~bash
java -jar target/application.jar --debug
~~~

This report shows which auto-configurations were applied or excluded. It helps diagnose why web beans were or were not created, though you should still inspect the dependency tree to understand the classpath origin.

## 8. Common misconceptions and errors

### Misconception 1: Having @RestController definitely means Servlet

Incorrect. Both Spring MVC and Spring WebFlux support the annotated controller model. The application type is determined by WebApplicationType and its corresponding configuration, not solely by controller annotations.

### Misconception 2: Declaring a starter alone is enough to know the runtime

A starter can pull in many transitive dependencies. An internal module or third-party library may bring Spring MVC onto the classpath even if the main module only declares WebFlux.

Solution: inspect the runtime dependency tree and identify the dependency causing the presence of DispatcherServlet or DispatcherHandler.

### Misconception 3: Having WebFlux always selects REACTIVE

Incorrect. If DispatcherServlet is present or Jersey ServletContainer is present, the reactive condition is not satisfied. When the Servlet indicator classes are present, the result can be SERVLET.

### Misconception 4: NONE means there is no Spring ApplicationContext

NONE only means the application is not launched as a web application. Spring still creates a regular ApplicationContext, initializes beans, and runs the required components.

### Misconception 5: Choosing REACTIVE means every call is non-blocking

WebApplicationType only determines the web model and configuration group. If code calls synchronous JDBC or a blocking HTTP client on the event loop, the application can still get blocked. To take advantage of WebFlux, examine the entire dependency chain and how I/O is performed.

### Misconception 6: Having the Servlet API present definitely means the application uses Tomcat

The Servlet API is an indicator of the Servlet model, while the specific server is determined by server factories and dependencies. A project can use another embedded server if the corresponding dependencies and configurations are set up.

### Error: Application expected to be WebFlux starts Tomcat instead

A common cause is Spring MVC being brought onto the runtime classpath, directly or indirectly. Check the dependency tree, remove the unnecessary MVC starter, and re-verify WebApplicationType after building.

### Error: Application has no HTTP endpoints despite creating controllers

The application may be running with NONE, the controller may not be component-scanned, or web dependencies may be missing from the runtime classpath. Check WebApplicationType, the main class package location, and the dependency tree.

## 9. Web stack selection checklist

Before choosing or changing a web stack, check:

- Does the application need Servlet MVC, Reactive WebFlux, or no web server?
- Does the runtime classpath contain the expected starter?
- Are any transitive dependencies unexpectedly pulling in spring-webmvc or spring-webflux?
- Is WebApplicationType deduced or overridden via API or configuration?
- Which embedded server factory is present on the classpath?
- Do the database and HTTP client libraries support a non-blocking model if choosing WebFlux?
- Is the test environment using a different web application type than the production runtime?

## 10. Summary

Spring Boot deduces WebApplicationType based on the presence of indicator classes on the runtime classpath. In Spring Boot 3.x, DispatcherHandler is used to detect the reactive case, while excluding it when Spring MVC's DispatcherServlet or Jersey's ServletContainer is present. If reactive is not chosen, Boot checks the Servlet API and ConfigurableWebApplicationContext to decide between SERVLET and NONE.

This result determines the ApplicationContext type and the group of auto-configurations applied. Web starters bring frameworks and server runtimes onto the classpath; transitive dependencies can also affect the outcome. When needed, you can set the application type with SpringApplication.setWebApplicationType or the spring.main.web-application-type property.

When the runtime does not behave as expected, check the dependency tree and the WebApplicationType value before modifying controllers or server configuration.
