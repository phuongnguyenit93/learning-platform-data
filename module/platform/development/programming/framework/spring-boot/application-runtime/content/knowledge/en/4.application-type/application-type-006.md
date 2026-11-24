# Relationship Between Web ApplicationContext, WebServerFactory, and the Embedded Server in Spring Boot

## 1. Three Components with Distinct Roles

When running a Spring Boot web application as a JAR, the framework does not merely instantiate controllers and return a plain Spring ApplicationContext. It also needs a component to manage an **embedded web server** so the application can serve requests itself without deploying a WAR into a separate application server.

Three core concepts:

1. **Web ApplicationContext (web context)** is a **Spring IoC container capable of managing the web server lifecycle**. It registers, creates, and manages beans (controllers, services, filters, configurations...), initializes web integrations, and coordinates when the server is created, started, and stopped.
2. **WebServerFactory** is the **factory that creates the server**. It holds/configures options such as port, SSL, compression, connectors, and context path depending on the stack; when requested by the web context, it creates a **WebServer** object. The factory is typically **a Spring bean** provided by Spring Boot auto-configuration.
3. **WebServer** is the **object representing the created server** (for example **TomcatWebServer** or **NettyWebServer**), exposing **start()**, **stop()**, and **getPort()** methods. Behind this abstraction sits Tomcat, Jetty, Undertow, or Reactor Netty accepting and processing HTTP connections.

**Division of responsibilities:** the web context manages the lifecycle, the factory knows how to create/configure the server, and the server is the component that actually accepts network connections. **The factory is not the server itself**; nor is Spring ApplicationContext an HTTP server.

~~~text
SpringApplication
    |
    | Determine WebApplicationType and create context
    v
Web ApplicationContext (Spring IoC container)
    |                         |
    | manage beans            | look up a WebServerFactory bean
    |                         v
    |                  WebServerFactory
    |                  (configured via server.*,
    |                   customizers, dependencies)
    |                         |
    |                         | getWebServer(...)
    |                         v
    |                      WebServer
    |                  (Tomcat / Jetty /
    |                   Undertow / Netty)
    |                         |
    | start, stop              | listen for HTTP
    +-------------------------+----------------> client
~~~

This is the **application with an embedded server** model. When deploying a WAR to an external servlet container, the container may be managed by the deployment environment; do not apply the "web context creates its own embedded server" diagram verbatim to every WAR deployment style.

## 2. Two Web Context Branches for the Two Web Stacks

In Spring Boot 3.3, the web application type leads to **two distinct context and factory families**.

| Criterion | Servlet Stack (Spring MVC) | Reactive Stack (Spring WebFlux) |
| --- | --- | --- |
| Application type | **WebApplicationType.SERVLET** | **WebApplicationType.REACTIVE** |
| Common web context | **AnnotationConfigServletWebServerApplicationContext**, extending **ServletWebServerApplicationContext** | **AnnotationConfigReactiveWebServerApplicationContext**, extending **ReactiveWebServerApplicationContext** |
| Factory interface | **ServletWebServerFactory** | **ReactiveWebServerFactory** |
| Server-creation input | **getWebServer(ServletContextInitializer... initializers)** | **getWebServer(HttpHandler httpHandler)** |
| HTTP handling components | Servlet container, **Filter**, **DispatcherServlet**, Spring MVC handlers | **HttpHandler** and WebFlux handler chain |
| Default embedded server with common starter | **Tomcat**, via **spring-boot-starter-web** | **Reactor Netty**, via **spring-boot-starter-webflux** |
| Other selectable servers (Boot 3.3) | Jetty, Undertow | Tomcat, Jetty, Undertow |

**Exact class names depend on the version**, while the two-branch model is the core concept. Both context types implement the **WebServerApplicationContext** interface, allowing the server object to be retrieved via **getWebServer()**.

### 2.1. Servlet Web Context

**ServletWebServerApplicationContext** looks up **a single ServletWebServerFactory bean** in the context, typically provided by auto-configuration. The factory decides how to build the embedded container; the context prepares **ServletContextInitializer** instances to register Servlets, Filters, and listeners.

With Spring MVC, the request flow can be visualized as:

~~~text
HTTP Client
   |
   v
Embedded Tomcat / Jetty / Undertow
   |
   v
Servlet Filter chain
   |
   v
DispatcherServlet
   |
   v
HandlerMapping -> Controller -> Service
   |
   v
HTTP response
~~~

**DispatcherServlet** is Spring MVC's front controller, **not a web server**. Without Tomcat/Jetty/Undertow or a corresponding servlet container, DispatcherServlet does not open sockets or listen on a port by itself. Conversely, an embedded Tomcat can run, yet without registering appropriate endpoints/servlets, the expected MVC routes will not appear on their own.

Concrete factory examples:

- **TomcatServletWebServerFactory** creates **TomcatWebServer**.
- **JettyServletWebServerFactory** creates a Jetty-based server.
- **UndertowServletWebServerFactory** creates an Undertow-based server.

**ServletContextInitializer** instances help configure the servlet context before the application serves requests; Spring Boot also adapts Servlet, Filter, and certain EventListener beans to register them with the server.

### 2.2. Reactive Web Context

**ReactiveWebServerApplicationContext** plays an equivalent role, looking up **ReactiveWebServerFactory**. Instead of accepting ServletContextInitializer instances like the MVC branch, a reactive factory accepts an **org.springframework.http.server.reactive.HttpHandler** as the HTTP processing entry point.

~~~text
HTTP Client
   |
   v
Reactor Netty / Tomcat / Jetty / Undertow
   |
   v
Server adapter
   |
   v
HttpHandler
   |
   v
WebFlux chain (WebFilter, WebHandler)
   |
   v
Annotated controller / functional router
   |
   v
Reactive response
~~~

**HttpHandler** is the contract bridging the HTTP server to Spring WebFlux's request-handling mechanism. On servlet containers running WebFlux, an appropriate adapter bridges servlet requests into the reactive pipeline. **WebFlux does not mandate Netty**; Netty is simply the default choice of the WebFlux starter in Spring Boot 3.3.

Factory examples:

- **NettyReactiveWebServerFactory** creates **NettyWebServer**.
- **TomcatReactiveWebServerFactory**, **JettyReactiveWebServerFactory**, and **UndertowReactiveWebServerFactory** allow the reactive stack to use other servers when dependencies are configured accordingly.

Although the two branches use different factories, both produce a **WebServer** whose lifecycle is managed by the web context.

## 3. Who Creates the Web Context and Who Registers WebServerFactory?

In a typical case, the developer simply declares an application and chooses a starter:

~~~java
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

**SpringApplication** determines **WebApplicationType** by inspecting the classpath, unless explicitly set via **spring.main.web-application-type** or the corresponding API. Based on that, it chooses an appropriate ApplicationContext.

**Auto-configuration** then supplies the factory bean when the corresponding conditions hold:

- For Servlet: **ServletWebServerFactoryAutoConfiguration** and Tomcat/Jetty/Undertow configurations can create a **ServletWebServerFactory**.
- For Reactive: **ReactiveWebServerFactoryAutoConfiguration** can create a suitable **ReactiveWebServerFactory**.
- Common server properties from **server.port**, **server.address**, **server.ssl.***, **server.compression.***, and Tomcat/Jetty/Netty-specific settings are applied to the factory via configuration mechanisms and customizers.

Normally, Boot **does not require you to write a `@Bean WebServerFactory` yourself**. Changing dependencies affects which factory type gets registered. For example, **spring-boot-starter-web** brings Tomcat by default; to use Jetty, swap the Tomcat starter for the Jetty starter and recheck the dependency graph.

When both Spring MVC and WebFlux are on the classpath, **Spring MVC typically takes precedence** during automatic application type inference. Adding **spring-boot-starter-webflux** just to use **WebClient** does not mean the application runs on a reactive web context or Netty server.

**Key distinction:** choosing Servlet/Reactive determines request handling and context; choosing Tomcat/Jetty/Undertow/Netty determines the server built by the factory. The two decisions are related, yet belong to different layers of responsibility.

## 4. When Does the Factory Create the Server, and When Does the Server Actually Run?

Below is the high-level sequence for a successfully starting embedded application (Spring Boot 3.3, default synchronous listeners):

1. **SpringApplication prepares Environment** from configuration sources and determines Servlet, Reactive, or None.
2. **SpringApplication creates the appropriate ApplicationContext** and registers configuration sources/bean definitions.
3. **Auto-configuration registers the WebServerFactory bean**. **WebServerFactoryCustomizer** instances configure the factory before the server is created.
4. During **ApplicationContext.refresh()**, the web context looks up the factory and calls **getWebServer(...)**. The factory builds the WebServer with the configured parameters.
5. Once context refresh completes, Boot's lifecycle mechanism calls **WebServer.start()**. The server begins serving HTTP; **WebServerInitializedEvent** (or Servlet/Reactive variants) is published when the server is ready.
6. After refresh, Boot publishes **ApplicationStartedEvent**, runs **ApplicationRunner/CommandLineRunner**, then **ApplicationReadyEvent** and the readiness state when applicable.
7. **SpringApplication.run(...) returns ConfigurableApplicationContext**. A web process typically continues running and serving requests after `run` returns.
8. When **ApplicationContext closes**, the lifecycle mechanism shuts down the server and related resources.

~~~text
Environment + WebApplicationType
            |
            v
Create Web ApplicationContext
            |
            v
Register factory bean and customize factory
            |
            v
ApplicationContext.refresh()
       |
       +--> context calls factory.getWebServer(...)
       |            |
       |            +--> create WebServer (not serving HTTP yet)
       |
       +--> complete refresh
                    |
                    v
               WebServer.start()
                    |
                    v
          WebServerInitializedEvent
                    |
                    v
          ApplicationStartedEvent
                    |
                    v
          ApplicationRunner / CommandLineRunner
                    |
                    v
          ApplicationReadyEvent
                    |
                    v
          SpringApplication.run(...) returns
~~~

**Technical note:** exact *internal initialization* order varies by container, yet the contract of **ServletWebServerFactory.getWebServer(...)** and **ReactiveWebServerFactory.getWebServer(...)** in Boot 3.3 describes a **configured and paused WebServer**; clients should not be able to connect until **start()**. You can distinguish object/network configuration from actually serving HTTP.

**WebServerInitializedEvent does not equal ApplicationReadyEvent.** The server may have already opened its port while a synchronous **ApplicationRunner** is still executing. In production operations, combine readiness probes/health information appropriately; the "port bound" signal alone does not prove the entire application is ready to accept business traffic.

## 5. Runnable Java 17+ Example: Observing the Real Context, Factory, and Server

The example uses a **Spring Boot 3.3.x** project with **spring-boot-starter-web** (default embedded Tomcat). Place **src/main/java/com/example/runtime/ServerRelationshipApplication.java**:

~~~java
package com.example.runtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.boot.web.server.WebServer;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ServerRelationshipApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(ServerRelationshipApplication.class, args);

        if (context instanceof WebServerApplicationContext webContext) {
            WebServer server = webContext.getWebServer();
            ServletWebServerFactory factory =
                    context.getBean(ServletWebServerFactory.class);

            System.out.println(
                    "MAIN | context=" + context.getClass().getSimpleName());
            System.out.println(
                    "MAIN | factory=" + factory.getClass().getSimpleName());
            System.out.println(
                    "MAIN | server=" + server.getClass().getSimpleName());
            System.out.println(
                    "MAIN | port=" + server.getPort());
        }
    }

    @Bean
    ApplicationListener<WebServerInitializedEvent> serverListener() {
        return event -> {
            // Skip management context if the app uses a separate server.
            if (event.getApplicationContext().getServerNamespace() == null) {
                System.out.println(
                        "EVENT | server port=" + event.getWebServer().getPort());
            }
        };
    }

    @RestController
    static class GreetingController {
        @GetMapping("/hello")
        public String hello() {
            return "Hello from embedded server";
        }
    }
}
~~~

**Configuration** at **src/main/resources/application.properties**:

~~~properties
server.port=0
spring.main.banner-mode=off
~~~

Run command from the project directory with Gradle Wrapper and the Spring Boot plugin:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

**Meaning of expected output** (port numbers are illustrative since **server.port=0** picks an available port):

~~~text
EVENT | server port=51742
MAIN | context=AnnotationConfigServletWebServerApplicationContext
MAIN | factory=TomcatServletWebServerFactory
MAIN | server=TomcatWebServer
MAIN | port=51742
~~~

Standard Spring Boot/Tomcat logs may appear between these lines, and **the actual port varies on each run**. Points worth verifying:

- **EVENT** appears before the **MAIN** lines because the event is published while completing refresh, whereas main continues only after **SpringApplication.run(...)** returns.
- The factory implementation is **TomcatServletWebServerFactory**; the object created by the factory is **TomcatWebServer**; these are **two objects with distinct responsibilities**.
- The port from the event and the port read via **webContext.getWebServer().getPort()** match within the same startup.
- ApplicationContext stays active after the run method returns, so the web server continues accepting requests.

To call the endpoint, replace **51742** with the actual port from the logs:

~~~bash
curl http://localhost:51742/hello
~~~

The exact HTTP response body is:

~~~text
Hello from embedded server
~~~

In this example, **@RestController** provides the handler, yet Tomcat is what accepts HTTP connections. **DispatcherServlet** routes requests to the controller, while the **web context** manages beans, the factory, and the server.

**Why not call context.close() in main?** Because this is a long-running web server. Closing the context immediately after **run(...)** begins stopping the embedded server and the endpoint stops serving.

## 6. With the Same Example, How Does the Relationship Change if Switched to WebFlux?

Suppose we switch to a **spring-boot-starter-webflux** project without keeping **spring-boot-starter-web** (so Boot auto-selects REACTIVE from the classpath). Then:

- Context is typically **AnnotationConfigReactiveWebServerApplicationContext**.
- Factory is typically **NettyReactiveWebServerFactory**.
- WebServer is typically **NettyWebServer**.
- HTTP enters **HttpHandler** and the WebFlux pipeline; it does not go through Spring MVC **DispatcherServlet**.

To observe both stacks generically at runtime without tying to Servlet, use this snippet after **SpringApplication.run(...)**:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

if (context instanceof WebServerApplicationContext webContext) {
    WebServer server = webContext.getWebServer();
    System.out.println("Context = " + context.getClass().getSimpleName());
    System.out.println("Server = " + server.getClass().getSimpleName());
    System.out.println("Port = " + server.getPort());
}
~~~

This snippet **assumes** you declared **MyApplication** and imported **ConfigurableApplicationContext**, **SpringApplication**, **WebServerApplicationContext**, and **WebServer**; it illustrates the shared API, not a standalone Java file. In a REACTIVE application, **do not** call **getBean(ServletWebServerFactory.class)** as in the Servlet example: use **ReactiveWebServerFactory** if reading the specific factory.

Do not merely swap the **ServletWebServerFactory** import to **ReactiveWebServerFactory** and assume every servlet controller works automatically in WebFlux. **@RestController** exists in both stacks, yet the HTTP processing pipeline, filters, security, and API details differ.

## 7. Which Settings Go to the Factory, and Which Choose the Context?

Distinguish two property groups commonly used together:

| Configuration | What Does It Decide? | Consequence |
| --- | --- | --- |
| **spring.main.web-application-type=servlet** | Requests a Servlet web context | Requires suitable Servlet components and factory |
| **spring.main.web-application-type=reactive** | Requests a Reactive web context | Requires reactive HTTP stack and suitable factory |
| **spring.main.web-application-type=none** | Chooses a non-web context | Does not start an embedded HTTP server for the main app |
| **server.port=8081** | Configures the factory/server port | Does not automatically turn a non-web app into a web app |
| **server.port=0** | Requests the server to use an OS-selected free port | Must read the actual port after the server is initialized |
| **server.port=-1** | Disables HTTP endpoints while keeping the web application context | Differs from selecting WebApplicationType.NONE |
| **server.address**, **server.ssl.*** | Configures bind address and TLS | Applied when configuring and creating the server |
| **server.servlet.context-path=/api** | Context path for a servlet web server | Endpoint `/hello` URL typically becomes `/api/hello` in the Servlet stack |
| **server.compression.enabled=true** | Enables HTTP response compression if supported | May affect responses by content type and compression threshold |

**spring.main.web-application-type** determines the **container/context** type. **server.*** tunes the **web server** inside the chosen context. A common mistake is setting **server.port=8080** and expecting a **NONE** application to automatically spin up Tomcat; that does not happen.

### 7.1. External Configuration Precedence

Example file configuration:

~~~properties
server.port=8080
~~~

And running:

~~~bash
./gradlew bootRun --args='--server.port=9090'
~~~

Under standard configuration, **--server.port=9090** from the command line beats **8080** in the file, because properties are bound onto the factory from Environment in PropertySource precedence order. However, a **WebServerFactoryCustomizer** running afterward can still modify the factory: check actual configuration and customizers when debugging ports.

### 7.2. Customizing the Factory with WebServerFactoryCustomizer

Prefer built-in **server.*** properties first. When customization is needed that Spring Boot does not expose via a property, register a **WebServerFactoryCustomizer**.

Standalone example for the **Servlet stack**, if you genuinely want to set the port in Java code:

~~~java
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.servlet.server.ConfigurableServletWebServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CustomServletServerConfiguration {

    @Bean
    WebServerFactoryCustomizer<ConfigurableServletWebServerFactory>
            localPortCustomizer() {
        return factory -> factory.setPort(9090);
    }
}
~~~

This is a configuration class for a **Servlet Boot project**. When added, do not expect the **server.port=0** result from the earlier example because the customizer sets **9090**. In real projects, if the goal is merely changing the port, **server.port=9090** in configuration is clearer and easier to operate.

If you only want to customize a specific server, you can target a concrete factory type like **TomcatServletWebServerFactory**. For the Reactive stack, use **ConfigurableReactiveWebServerFactory** or the matching concrete factory such as **NettyReactiveWebServerFactory**.

**Do not manually instantiate a WebServer bean and call start() alongside** a web context already managed by Spring Boot. Doing so can produce two servers, port conflicts, inconsistent shutdown, or bypass context lifecycle.

### 7.3. When Should You Declare a Factory Bean Yourself?

You can declare your own **ServletWebServerFactory** or **ReactiveWebServerFactory** bean to replace the auto-configured factory when special requirements exist. But this is a strong customization level:

- You must ensure the factory matches the Servlet/Reactive context.
- Spring Boot may still apply auto-configured customizers to your factory.
- Two factory beans of the same type in one context can prevent the web context from uniquely resolving which factory to use.
- Prefer switching starters, configuring **server.***, or adding a **WebServerFactoryCustomizer** before replacing the factory outright.

## 8. Reading the Port and Observing Lifecycle at the Right Time

### 8.1. WebServerInitializedEvent

This event fires when the server has been initialized/is ready, exposing **getWebServer()** to read the server object and port.

~~~java
@Bean
ApplicationListener<WebServerInitializedEvent> portListener() {
    return event -> {
        int port = event.getWebServer().getPort();
        System.out.println("Actual HTTP port = " + port);
    };
}
~~~

This is a **@Bean** method placed inside a **@Configuration** or **@SpringBootApplication** class with appropriate imports. Useful for reading dynamic ports and observing server startup. **WebServerInitializedEvent** has **ServletWebServerInitializedEvent** and **ReactiveWebServerInitializedEvent** subtypes.

Do not confuse this event's timing with when the application is ready. The server initialized event arrives earlier than **ApplicationReadyEvent**. If Actuator management runs on a separate port, one application can have **multiple web contexts/servers** and emit multiple events; check **event.getApplicationContext()** or **getServerNamespace()** before treating an event as the main HTTP server.

### 8.2. Getting WebServer from the Web Context After run Returns

Once bootstrapping completes:

~~~java
ConfigurableApplicationContext context = SpringApplication.run(App.class, args);

if (context instanceof WebServerApplicationContext webContext) {
    WebServer server = webContext.getWebServer();
    if (server != null) {
        System.out.println("Listening on port " + server.getPort());
    }
}
~~~

This is a snippet (assuming an **App** class and appropriate imports). **WebServerApplicationContext.getWebServer()** returns the server created by the context or **null if the server has not been created yet**. After a successful **run(...)** with an active embedded HTTP server, a server is normally available to query.

### 8.3. Why Not Read local.server.port Too Early?

When using **server.port=0**, the actual port is only known once the server is initialized. Therefore, do not inject **local.server.port** into a bean created too early in bootstrap and expect it to hold the real port number.

In integration tests with **@SpringBootTest(webEnvironment = RANDOM_PORT)**, you can use **@LocalServerPort**; Spring Boot arranges injection after the server is initialized. In normal application code, **WebServerInitializedEvent** is a more reliable observation point for accessing the actual port.

## 9. Difference Between a Real Running Server and a Mock Web Context in Tests

**@SpringBootTest(webEnvironment = RANDOM_PORT)** starts an embedded server on a random port, suitable for testing the real HTTP flow from the network stack to the controller.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HelloHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate rest;

    @Test
    void endpointIsServedOverHttp() {
        String body = rest.getForObject(
                "http://localhost:" + port + "/hello", String.class);

        assertThat(body).isEqualTo("Hello from embedded server");
    }
}
~~~

This test assumes the example application from section 5 and the **spring-boot-starter-test** dependency. **TestRestTemplate** suits Servlet integration tests; in reactive projects, **WebTestClient** can be used.

By contrast, **@SpringBootTest(webEnvironment = MOCK)** or slice tests like **@WebMvcTest** build a context for testing MVC **without opening a real embedded HTTP listener**. Therefore, passing mock tests does not prove the real factory can bind ports, load TLS certificates, or accept HTTP requests over sockets.

## 10. Common Errors When Coordinating Context, Factory, and Server

### 10.1. Missing WebServerFactory Bean

Symptoms typically involve messages like **missing ServletWebServerFactory bean** or **missing ReactiveWebServerFactory bean**. Checks to perform:

1. Confirm **spring.main.web-application-type** matches your intended stack.
2. Check dependencies for **spring-boot-starter-web** or **spring-boot-starter-webflux** and the corresponding server starter.
3. Check whether auto-configuration or embedded server dependencies were excluded.
4. If a factory was declared manually, verify it implements the right interface and belongs to the current context.

**The context can be created yet fail during refresh** if no suitable factory is found. This is a bootstrap configuration error, distinct from a controller missing a route.

### 10.2. Multiple Factories of the Same Type

A web context normally expects **a single factory of the matching type**. If multiple beans of the same type exist and cannot be uniquely resolved, startup can fail reporting an ambiguous factory selection. Do not try to fix it by randomly injecting one factory; explicitly configure which bean to use or let auto-configuration manage it.

### 10.3. Port 8080 Already Occupied by Another Process

Even when controllers and context are completely valid, the server can fail to bind **server.port**. How to check: look for **Port ... was already in use**, pick another port, stop the process holding the port, or use **server.port=0** during testing.

### 10.4. Saw "Tomcat started" Log Yet Requests Still Fail

Distinguish three diagnostic layers:

- **Server/network:** bind address, port, reverse proxy, firewall, TLS, port conflicts, whether the server is running.
- **HTTP framework:** URL, context path, servlet mapping, DispatcherServlet, WebFlux routing, HTTP method.
- **Business/readiness:** external dependencies, runners, datasource, authentication, and whether the application is ready.

A server start log does not guarantee a specific endpoint exists, that handlers are error-free, or that all business dependencies are ready.

### 10.5. Both spring-boot-starter-web and spring-boot-starter-webflux Present

By default Spring MVC usually takes precedence when both libraries are present. Thus, having a **reactive dependency** or **WebClient** present does not turn the whole application into a reactive web server. If intentionally using REACTIVE, choose the stack, context type, and factory properly rather than guessing from one dependency's name.

### 10.6. Confusing server.port=-1 with NONE

**server.port=-1** keeps the web application context while disabling HTTP endpoints; **spring.main.web-application-type=none** chooses a non-web context. The two options serve different purposes and have different bootstrap consequences.

### 10.7. Calling factory.getWebServer(...) Directly in a Service

If a business bean calls the factory directly to create a new server, it can spin up an extra server instance outside the context lifecycle, causing port collisions or uncleaned resources at shutdown. Let the **web context** create and manage the server. To inspect the running server, use **WebServerApplicationContext.getWebServer()**.

### 10.8. Not Closing Context on Application Shutdown

The embedded server belongs to the application context lifecycle. Let Spring Boot's shutdown mechanism close the context cleanly; if the application manages the context manually, ensure **close()** is called when actually terminating. In a long-running web app, do not close the context right after `run`.

## 11. Self-Check Questions

**Question 1.** A Spring MVC application has a **TomcatServletWebServerFactory** bean. Is this bean **TomcatWebServer**?

**Answer:** No. **TomcatServletWebServerFactory** is a factory capable of creating a **WebServer**, whereas **TomcatWebServer** is the actual server object; the web context coordinates creating, starting, and stopping it.

**Question 2.** To switch from Spring MVC on Tomcat to Spring MVC on Jetty, must the web context change to ReactiveWebServerApplicationContext?

**Answer:** No. Spring MVC remains the Servlet stack; swap the server dependency/factory to Jetty while still using the **ServletWebServerApplicationContext** family.

**Question 3.** An application uses **spring-boot-starter-webflux** and Reactor Netty. What does the factory accept to wire HTTP handling?

**Answer:** **ReactiveWebServerFactory.getWebServer(HttpHandler)** accepts an **HttpHandler**, the bridge from the reactive server into the WebFlux pipeline.

**Question 4.** Inside **WebServerInitializedEvent**, you read the actual port. Has the application definitely published **ApplicationReadyEvent** yet?

**Answer:** Not yet. The server initialized event arrives before the full runner/ready sequence completes.

**Question 5.** With **server.port=0**, to test a real HTTP socket in tests, do you use **@WebMvcTest** or **@SpringBootTest(webEnvironment = RANDOM_PORT)**?

**Answer:** Choose **RANDOM_PORT** to get a real embedded HTTP server. **@WebMvcTest** primarily tests the MVC slice on mock request infrastructure.

**Question 6.** When **spring.main.web-application-type=none** yet **spring-boot-starter-web** is still on the classpath, does the container automatically create Tomcat?

**Answer:** Not under the normal embedded web server startup mechanism. Boot was instructed to select a non-web context; having the dependency alone is not enough for the main application to listen on HTTP.

**Question 7.** Why should you configure **server.port** instead of manually calling **new Tomcat()**?

**Answer:** Because Boot provides the factory, applies ServerProperties/customizers, and manages the lifecycle. Building Tomcat standalone bypasses this system and easily causes coordination or shutdown bugs.

## 12. Takeaways and Official Documentation

An embedded Spring Boot web application has three important layers:

**Web ApplicationContext (lifecycle manager) → WebServerFactory (server creator) → WebServer (HTTP listener).**

For Servlet, the web context uses **ServletWebServerFactory** and **ServletContextInitializer** to connect Spring MVC with Tomcat/Jetty/Undertow. For Reactive, the web context uses **ReactiveWebServerFactory** and **HttpHandler** to connect WebFlux with Reactor Netty or a compatible server. **The server started event** differs from **the application being ready**, and **`run(...)` returning** does not mean the web server stopped.

References for Spring Boot 3.3:

- Embedded Web Servers: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Servlet Web Applications, ServletWebServerApplicationContext section: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- ServletWebServerApplicationContext API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/context/ServletWebServerApplicationContext.html
- ServletWebServerFactory API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/server/ServletWebServerFactory.html
- WebServerApplicationContext API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/context/WebServerApplicationContext.html
- WebServerInitializedEvent API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/context/WebServerInitializedEvent.html