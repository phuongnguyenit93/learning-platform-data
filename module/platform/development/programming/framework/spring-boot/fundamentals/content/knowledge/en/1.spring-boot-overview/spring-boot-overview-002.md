# What Foundation Does the Spring Framework Provide and What Does Spring Boot Add?

When building Java applications with Spring, the two names **Spring Framework** and **Spring Boot** often appear together. This can easily give the impression that they are competing frameworks or that Spring Boot has replaced the Spring Framework. In reality, **Spring Boot is built on top of the Spring Framework**: the Spring Framework provides the core mechanisms for organizing and running an application, while Spring Boot makes assembling, configuring, launching, and operating a Spring application more convenient.

Imagine a requirement: create an API that accepts a user's name and returns a greeting. The developer needs to write the rule for generating the greeting and how to accept HTTP requests. Yet the application also needs to create objects, wire them together, route HTTP requests, start a server, choose compatible libraries, read configuration, and expose operational information. The Spring Framework and Spring Boot solve different parts of that picture.

## 1. The Big Picture: Three Layers of Responsibility

~~~text
Your Application
  ├─ Business logic: GreetingService, OrderService, ...
  ├─ Interfaces: REST controller, message listener, batch job, ...
  └─ System-specific rules and configuration
           │ uses
           ▼
Spring Boot
  ├─ Starter dependencies and library version management
  ├─ Conditional auto-configuration
  ├─ Application startup and embedded server when needed
  ├─ Configuration conventions and environment-based configuration
  └─ Testing, packaging, and observability utilities
           │ built on
           ▼
Spring Framework
  ├─ IoC container, beans, and Dependency Injection
  ├─ Application configuration, object lifecycle, events
  ├─ AOP, transaction management
  ├─ Spring MVC / Spring WebFlux
  └─ Data integration, testing, and other infrastructure
           │ uses
           ▼
Java, JVM, third-party libraries, servers, and system resources
~~~

A useful distinction:

- **Spring Framework answers:** How are application components created, linked, invoked, and managed? How do we handle web requests, transactions, and cross-cutting technical concerns?
- **Spring Boot answers:** Given the available libraries and configuration, what needs to be set up so a Spring application runs quickly, consistently, and is easy to configure and operate?
- **Your code answers:** What should the application actually do, what data is valid, and what business rules must be enforced?

Spring Boot **does not bypass** the Spring Framework. When a controller in a Boot application receives an HTTP request, Spring MVC and the Spring IoC container are still doing the work.

## 2. What Foundation Does the Spring Framework Provide?

### 2.1. The IoC Container: Managing Application Objects

In plain Java, a class often creates the objects it needs on its own:

~~~java
public class GreetingController {
    private final GreetingService greetingService = new GreetingService();
}
~~~

This style is simple in small examples, but it couples the consumer directly to the instantiation of its dependency. As the application grows, swapping implementations, sharing configuration, testing with mocks, or managing lifecycles becomes difficult.

The Spring Framework solves this with **Inversion of Control (IoC)**: control over creating and wiring many objects is transferred to the **Spring container**. Objects managed by the container are called **beans**. A commonly encountered container interface is **ApplicationContext**; it extends BeanFactory capabilities and adds application-level services.

Example of a service:

~~~java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

**@Service** is a specialized form of **@Component**. When a class lies within the component-scanned scope, Spring can register it as a bean. Besides annotation scanning, beans can be declared explicitly using **@Bean** inside a **@Configuration** class. Not every Java object automatically becomes a bean.

### 2.2. Dependency Injection: Supplying the Right Objects

**Dependency Injection (DI)** is the pattern of supplying dependencies to an object from the outside rather than having the object create them itself. The Spring container can perform DI via constructor, setter, or field; for required dependencies, **constructor injection** is usually the clearest and easiest to test.

~~~java
package com.example.demo.web;

import com.example.demo.service.GreetingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/hello")
    public String hello(@RequestParam(defaultValue = "friend") String name) {
        return greetingService.greet(name);
    }
}
~~~

If both classes are registered as beans, the container creates **GreetingService** and then passes it to the constructor of **GreetingController**. Because the controller only knows that the dependency arrives through its constructor, you can pass another implementation or a mock object when writing plain Java tests.

Distinguish concepts that often appear together:

| Concept | Meaning |
|---|---|
| IoC | The principle of inverting control over object creation, assembly, and management. |
| DI | A realization of IoC by providing dependencies to an object. |
| Bean | An object managed by the Spring container. |
| ApplicationContext | The container and entry point to Spring's object-management services. |

DI was not invented by Spring Boot: **it is a foundation of the Spring Framework**.

### 2.3. Bean Lifecycle and Application Configuration

Spring does more than just invoke a constructor. Depending on the bean type and configuration, the container can also:

1. Read bean definitions from annotations or Java configuration.
2. Resolve dependencies, instantiate objects, and perform injection.
3. Apply bean post-processors, proxies, and required initialization callbacks.
4. Make the bean available to serve other components in the application.
5. Invoke destruction callbacks when the context closes, if supported by the bean and scope.

Annotations such as **@Configuration**, **@Bean**, **@Component**, **@Service**, **@Repository**, and **@Controller** belong to the Spring Framework's configuration and component model. Some annotations only take effect when the corresponding mechanism is enabled; for instance, **@Component** must be scanned or registered appropriately.

The container also supports scopes such as **singleton** (default for regular beans) and **prototype**, along with web-related scopes when an appropriate web environment exists. Singleton here means **one instance per bean definition within a single container**, not necessarily a single instance across the entire JVM.

### 2.4. Web: Spring MVC and Spring WebFlux

The Spring Framework provides two major web models:

- **Spring MVC**: a Servlet-based web framework commonly used for synchronous REST/HTTP applications. **DispatcherServlet** receives requests and coordinates handler mapping, data conversion, exception handling, and response generation.
- **Spring WebFlux**: a web framework supporting reactive programming and asynchronous processing streams, built on Reactor. This is a separate architectural choice; using Spring Boot does not automatically make an application reactive.

In the **GreetingController** example, **@RestController**, **@GetMapping**, and **@RequestParam** are **Spring MVC** components, even though the example is commonly run with Spring Boot.

An MVC-style HTTP processing flow can be visualized as follows:

~~~text
HTTP GET /hello?name=Lan
        │
        ▼
HTTP server / Servlet container
        │
        ▼
Spring MVC DispatcherServlet
        │ finds matching handler
        ▼
GreetingController.hello("Lan")
        │ calls bean via DI
        ▼
GreetingService.greet("Lan")
        │
        ▼
HTTP 200, body: Hello, Lan!
~~~

The HTTP server handles network connections and Servlet requests; Spring MVC routes to application code. Spring Boot can prepare the server and configure Spring MVC for you, but the business logic and handlers are still written by you.

### 2.5. Transactions, AOP, Data, and Testing

Beyond web and DI, the Spring Framework provides other critical foundations:

| Spring Framework Capability | Problem Solved | Examples |
|---|---|---|
| **AOP (Aspect-Oriented Programming)** | Apply common cross-cutting behaviors around method calls via mechanisms like proxies | Logging, transaction control, declarative cross-cutting concerns |
| **Transaction abstraction** | Define transaction boundaries across data access technologies | **@Transactional**, **PlatformTransactionManager** |
| **Data access integration** | Reduce boilerplate code and integrate data APIs | **JdbcTemplate**, JPA integration |
| **Validation and conversion** | Convert, bind, and validate data via appropriate mechanisms | **Validator**, conversion service |
| **Testing support** | Support creating, caching, and configuring the Spring context in tests | Spring TestContext Framework |
| **Events, resources, scheduling, caching** | Provide reusable infrastructure for common needs | **ApplicationEventPublisher**, **Resource**, **@Scheduled**, **@Cacheable** |

For example, **@Transactional** marks the intent to execute a unit of work within a transaction. However, an appropriate transaction manager must exist and the call must go through Spring's transaction management mechanism; adding the annotation to an arbitrary Java method does not create a transaction by itself.

It is also important to distinguish the **Spring Framework** from other projects in the Spring ecosystem. For example, **Spring Data**, **Spring Security**, and **Spring Cloud** are related projects with their own responsibilities. Spring Boot helps integrate and configure many of those projects, but it does not turn all of them into core features of the Spring Framework itself.

## 3. What Does Spring Boot Add?

You can already build a complete application with the Spring Framework without using Spring Boot. However, developers must select dependencies, initialize the context, configure the web runtime, wire components, manage versions, and prepare a lot of repetitive setup. Spring Boot provides a setup approach with **sensible conventions as defaults** while still allowing customization when needed.

### 3.1. Starter Dependencies: Selecting a Compatible Group of Libraries

Instead of manually declaring individual libraries for web, JSON, server, and testing, Boot provides **starters**. Starters are convenience dependency descriptors that pull in a set of related libraries.

For example, in a Gradle project configured with the Spring Boot plugin and corresponding dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

With **Spring Boot 3.x**, the typical web starter brings Spring MVC, required web libraries, and embedded Tomcat by default onto the classpath. The test starter gathers commonly used testing tools. Listing a starter **does not generate controllers or business rules**.

Spring Boot also provides **dependency version management** through a set of tested, compatible versions (BOM/dependency management). This reduces the effort of aligning Spring library versions and related dependencies. It does not guarantee that every third-party library or every manually overridden version will be compatible.

Other starters in the ecosystem include **spring-boot-starter-data-jpa**, **spring-boot-starter-validation**, and **spring-boot-starter-actuator**. Only add the starters that your application actually uses.

### 3.2. Auto-configuration: Conditional Automatic Configuration

This is a very important difference. Boot's **auto-configuration** inspects dependencies on the classpath, current configuration, application type, and existing beans to decide which configurations should be applied.

For example, in a Servlet-based web starter application:

1. Boot sees the required web libraries and identifies the application as a Servlet web application.
2. Matching auto-configurations prepare Spring MVC infrastructure, an embedded server, and related components if conditions are satisfied.
3. Spring creates and manages the application's controllers, services, and beans.
4. The application can receive HTTP requests without you having to write **DispatcherServlet** initialization or Tomcat configuration code for common cases.

Auto-configuration **does not mean every feature is enabled unconditionally**. A configuration can depend on:

- Whether a class or library is present on the classpath.
- Whether a property has an appropriate value.
- Whether a bean of a certain type has already been declared.
- Whether the current environment is an appropriate web application.

Conditional annotations such as **@ConditionalOnClass**, **@ConditionalOnMissingBean**, and **@ConditionalOnProperty** are key tools in this mechanism.

For example, simply adding a database connector library does not mean Boot can guess the URL, credentials, and schema of your real system. Depending on dependencies and conditions, Boot might configure a default DataSource, require additional properties, or skip the configuration altogether.

**Can auto-configuration be customized or disabled?** Yes. Spring Boot allows declaring your own beans/configurations, supplying properties, or excluding specific auto-configurations. The extent of override depends on each configuration and its conditions; you should not assume any arbitrary bean automatically replaces all Boot defaults.

### 3.3. A Standardized Starting Point

A typical Boot application has an entry point like this:

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

**SpringApplication.run(...)** orchestrates preparing the environment, creating the appropriate Spring application context, loading configuration, registering beans, and starting the runtime environment. If it is a suitably configured web application, Boot can also launch the embedded HTTP server.

**@SpringBootApplication** combines key roles:

| Component | Role |
|---|---|
| **@SpringBootConfiguration** | Marks the application configuration class; based on Spring's **@Configuration** mechanism. |
| **@EnableAutoConfiguration** | Allows Boot to evaluate eligible auto-configurations. |
| **@ComponentScan** | Scans for components/beans starting from the application class's package and its subpackages by default convention. |

Therefore, placing **DemoApplication** in the root package **com.example.demo** and putting **GreetingService** and **GreetingController** in subpackages is an intentional choice. If components are placed outside the scan scope, Spring may not find the beans; you need to adjust package organization or declare matching scan configuration.

### 3.4. Embedded Server and Executable Packaging

For a standard Spring MVC application, Boot can run **embedded Tomcat** directly inside the application process. A common workflow is packaging into an executable JAR and running it on the JVM, or using **bootRun** during development.

~~~text
JVM
 └─ Spring Boot Application
     ├─ Embedded Servlet container (e.g., Tomcat)
     ├─ Spring MVC DispatcherServlet
     ├─ Spring ApplicationContext
     └─ Controllers, services, repositories, ...
~~~

This reduces the need to manually package a WAR file and deploy it into a pre-installed Servlet server for every project. However, **Spring Boot does not require being a web app or always having Tomcat**: a command-line application may not open an HTTP port; a WebFlux application has different runtime options; and a Servlet Boot application can still be packaged appropriately for deployment to an external servlet container when needed.

### 3.5. Externalized Configuration: Separating Configuration from Code

Boot standardizes supplying configuration from multiple sources such as **application.properties**, **application.yml**, environment variables, command-line arguments, and other supported configuration sources. This lets the same application artifact use different configurations per environment.

Example **src/main/resources/application.yml** file:

~~~yaml
server:
  port: 8081

spring:
  application:
    name: greeting-demo
~~~

The **server.port** property controls the embedded web server port according to Boot configuration. When run in an appropriate environment, the example above changes the HTTP port from the common default **8080** to **8081**.

For custom properties such as **app.greeting-prefix**, Boot only provides the mechanism to read and bind configuration; you still have to write code to consume that value, for example via **@ConfigurationProperties** or **@Value**. Boot does not automatically turn a business property into new behavior.

**Profiles** support configurations activated by environment, such as **dev** and **prod**. Use appropriate configuration and secret mechanisms instead of hardcoding passwords in source code or writing secrets into committed config files.

### 3.6. Application Observability and Development Support

Spring Boot includes additional utilities commonly needed in real applications:

- **Actuator** (added via a separate starter): provides health information, metrics, and management/observability endpoints. For example, the web endpoint **/actuator/health** can be provided when Actuator is enabled; which endpoints are exposed depends on configuration and security.
- **Logging conventions**: sets up default logging integration for common scenarios and supports customizing log levels.
- **Development tools**: optional tools such as **spring-boot-devtools** make the development loop more convenient.
- **Testing support**: utilities like **@SpringBootTest** support testing within a Boot context, built upon Spring's testing foundation.
- **Packaging and startup tools**: build plugins support creating appropriate executable JAR/WAR files, running the application, and packaging tasks.

These features do not automatically guarantee the application is secure or production-ready. For instance, exposing management endpoints requires explicit decisions about networking, access control, and security.

## 4. Direct Comparison: Spring Framework vs. Spring Boot

| Question | Spring Framework | Spring Boot |
|---|---|---|
| What is its nature? | Foundational framework suite for Java applications. | Tooling and conventions built on top of the Spring Framework. |
| Who creates and wires beans? | Spring IoC container. | Still the Spring IoC container; Boot helps initialize and configure it. |
| Who provides **@Service**, **@Bean**, DI? | Spring Framework. | Reuses those mechanisms. |
| Who provides **@RestController**, **@GetMapping**? | Spring MVC within Spring Framework. | Can auto-configure MVC infrastructure when matching dependencies exist. |
| Who provides **@Transactional**? | Spring's transaction infrastructure. | Can auto-configure certain transaction components when conditions fit. |
| How are dependencies chosen? | Developers decide and manage them manually. | Provides starters and managed version sets. |
| How much configuration is needed? | Depends on setup; typically requires assembling more pieces manually. | Provides many conditional defaults while still allowing customization. |
| Starting an HTTP server? | Provides the web framework, while server integration is configured by the app. | Can launch an embedded server in appropriate web applications. |
| Environment configuration? | Provides **Environment**, **PropertySource**, and core configuration capabilities. | Standardizes loading and using multiple configuration sources, conventions, and profiles. |
| Health/metrics utilities? | Has foundational mechanisms for integration. | Actuator provides observability features when added and configured. |
| Can it be used standalone? | **Yes.** Spring Framework does not require Boot. | **Not in the sense of replacing the Framework:** Boot relies on Spring Framework. |

A key point to remember is that **the same Spring Framework APIs can appear in both Boot and non-Boot applications**. For example, the controller in the earlier section is still a Spring MVC controller; Boot simply makes preparing its runtime environment easier.

## 5. Side-by-Side Example: Same GreetingService, Two Ways to Start

### 5.1. Using Spring Framework Directly, Without Boot

If you only want a Java program to instantiate beans and invoke business logic, you can create an **ApplicationContext** using Spring Framework APIs:

~~~java
package com.example.demo;

import com.example.demo.service.GreetingService;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan("com.example.demo.service")
class CoreConfig {
}

public class PlainSpringApp {
    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(CoreConfig.class)) {
            GreetingService service = context.getBean(GreetingService.class);
            System.out.println(service.greet("Lan"));
        }
    }
}
~~~

Output:

~~~text
Hello, Lan!
~~~

This demonstrates that **IoC, component scanning, and DI work without Spring Boot**. This program does not open an HTTP server; if you want to provide a REST API directly with Spring MVC, you need to add dependencies and configure an appropriate web runtime. Modern Spring Framework can be configured using Java annotations and does not require XML.

### 5.2. Using Spring Boot for a REST API

With **GreetingService** and **GreetingController** defined in section 2, a typical Boot application needs:

1. A project with appropriate Spring Boot plugin/dependency management configuration and the **spring-boot-starter-web** dependency.
2. The **DemoApplication** class with **@SpringBootApplication** and **SpringApplication.run(...)**.
3. Components located within the application's scan scope.

After running the application with the **bootRun** task or a built executable JAR, you can send:

~~~http
GET /hello?name=Lan HTTP/1.1
Host: localhost:8080
~~~

The application returns a response with body:

~~~text
Hello, Lan!
~~~

In this example, **Spring Framework** handles beans, DI, the controller, and MVC routing; **Spring Boot** handles dependency selection, MVC setup, creating the web application context, starting the embedded server, and loading configuration.

If you already set **server.port: 8081** as shown earlier, requests must be sent to port **8081** instead of **8080**. The result also assumes the server actually started and no other path/security configuration interferes.

### 5.3. What Happens When Calling SpringApplication.run

At a conceptual level, the startup flow can be described as follows:

~~~text
DemoApplication.main()
    │
    ▼
SpringApplication.run(...)
    │
    ├─ Prepare environment and configuration sources
    ├─ Create appropriate ApplicationContext type
    ├─ Process application configuration and eligible auto-configurations
    ├─ Register, instantiate, and wire beans via Spring container
    ├─ Start embedded server if appropriate web application
    └─ Complete startup phase
                    │
                    ▼
       Ready to handle business logic / requests
~~~

This is a model for understanding responsibilities, not an exact list of every internal callback; exact ordering varies by application type, version, and extension points.

## 6. When to Use the Framework Directly vs. Boot?

**Spring Boot is usually the sensible default** for a REST service, web backend, background worker, or new Spring application that needs fast setup, consistent dependency management, and standalone execution. The benefit is especially clear when a team builds multiple services with similar structure and runtime setup.

**Using Spring Framework directly** still fits if you are writing an integration library that should minimize coupling to Boot, running in an externally managed container environment, or wanting full manual control over infrastructure initialization. That is a deliberate technical choice, not a mandatory phase everyone must pass through before learning Boot.

In both cases, it is still essential to understand how **beans are created**, **dependencies are injected**, **components are scanned**, **MVC processes requests**, and **transactions are managed**. Without that foundation, errors like *bean not found*, *multiple beans of the same type*, *circular dependency*, or *auto-configuration not activating* become hard to diagnose.

## 7. Common Misconceptions

**"Is Spring Boot a newer version of the Spring Framework?"**  
No. They are two projects with different roles, evolving and remaining compatible across specific versions. Spring Boot uses the Spring Framework as its foundation.

**"If I use Boot, do I not need to learn IoC/DI and Spring MVC?"**  
You still need to. Boot reduces repetitive configuration code; objects and requests are still managed by the Spring Framework. Knowing the foundation helps you understand behavior and debug issues.

**"Adding @RestController makes an API automatically work?"**  
Not by itself. You must have a Spring context registering the controller, corresponding web infrastructure, an HTTP server, and proper configuration. Boot usually provides many of those pieces when the right starter is present.

**"Does auto-configuration mean Boot knows everything I want?"**  
No. It makes decisions based on predefined conditions and defaults. It cannot infer your custom business rules, access permissions, endpoints, or arbitrary database connections.

**"Is a starter the same thing as auto-configuration?"**  
No. A **starter** primarily brings a group of dependencies into the project; **auto-configuration** is conditional configuration code that runs based on the classpath and environment information. The two mechanisms complement each other.

**"Does Spring Boot always use Tomcat and only build REST APIs?"**  
No. Tomcat is a common default choice for Servlet web applications with the matching starter. Boot also supports other application types, other runtimes, and programs without any HTTP server.

**"With Spring Boot, is everything in Spring Data/Security/Cloud ready out of the box?"**  
No. Each project has its own dependencies, configuration, and behavior. Boot helps assemble the selected pieces; you still need to add libraries and design appropriate policies.

## 8. How to Verify What Boot Has Done Yourself

When learning a new feature, instead of just looking at code that "works," trace three questions:

1. **Where does this bean or API come from?** For instance, **@GetMapping** belongs to Spring MVC; **@SpringBootApplication** belongs to Spring Boot.
2. **Which library brings this feature onto the scene?** For instance, the web starter brings in the dependencies needed for typical Spring MVC web apps.
3. **Which configuration activates the feature?** It could be component scanning, conditional auto-configuration, a property, or a bean you declared.

In a Spring Boot environment, you can run with the **--debug** option to view additional diagnostic information about auto-configuration conditions, including which configurations were applied or skipped. Do not confuse this log with Boot creating every bean automatically: application-declared components are still managed by the Spring container using Framework mechanisms.

A sensible hands-on extension is to replace the static greeting with a **GreetingService** that has its own configurable prefix, then pass a fake dependency in a unit test. When you swap the service via constructor injection without editing the controller, you are observing the benefit of **Spring DI**; when you adjust **application.yml** without recompiling business logic, you are observing the benefit of **Spring Boot externalized configuration**.

## Key Takeaways

**Spring Framework is the technical foundation:** IoC container, DI, bean lifecycle, MVC/WebFlux, transactions, AOP, and core application programming infrastructure.

**Spring Boot is the organization and automation layer built on that foundation:** starters, dependency management, auto-configuration, entry point, embedded servers, externalized configuration, packaging, and operational utilities.

**Your application is still designed by you:** choosing modules, defining beans, APIs, business logic, data, security, and deployment. Understanding this boundary lets you leverage Spring Boot's convenience while still explaining what is actually happening underneath.
