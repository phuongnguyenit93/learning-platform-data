# Using SpringApplicationBuilder to Express the Spring Boot Launch Process

## 1. Purpose and Significance

When starting a Spring Boot application, the most familiar style is calling **SpringApplication.run(MyApplication.class, args)** in the **main** method. This style is concise and fits most applications. When you want to **explicitly express each configuration choice before launching**, you can use **SpringApplicationBuilder**.

**SpringApplicationBuilder** is a builder class in the **org.springframework.boot.builder** package that provides a fluent API: chained calls return the builder to describe configuration sources, profiles, web/non-web application type, default properties, listeners, and how the ApplicationContext is structured. The final **run(args)** call is what actually bootstraps the application and returns the running **ConfigurableApplicationContext**.

Illustrative example:

~~~java
new SpringApplicationBuilder(MyApplication.class)
        .bannerMode(Banner.Mode.OFF)
        .profiles("local")
        .properties("app.mode=demo")
        .web(WebApplicationType.NONE)
        .run(args);
~~~

The snippet above states: use **MyApplication** as the configuration source; turn off the startup banner; add the **local** profile; supply the default property **app.mode=demo**; run in **non-web** mode; and finally launch with the program's command-line arguments.

**Key point:** the call order **bannerMode → profiles → properties → web** in the chain is not the execution order of Spring Boot's startup phases. Before **run**, the builder mainly accumulates options. Spring Boot executes the actual startup sequence when **run(args)** is called.

## 2. Expressing the Launch Flow with a Builder

The process can be divided into two clear phases:

~~~text
PHASE 1 — EXPRESS CONFIGURATION (in main)
  new SpringApplicationBuilder(Application.class)
      ├── sources(...) / bean sources
      ├── profiles(...) / additional profiles
      ├── properties(...) / default properties
      ├── bannerMode(...) / startup banner
      ├── web(...) / application type
      ├── listeners(...) / listeners
      └── initializers(...) / initializers
                        |
                        v
PHASE 2 — ACTUAL STARTUP
                    run(args)
                        |
                        v
                SpringApplication
                        |
                        v
      Prepare Environment / ApplicationContext
                        |
                        v
      Load configuration, create beans, refresh context
                        |
                        v
           Run ApplicationRunner and
                 CommandLineRunner
                        |
                        v
              ApplicationReadyEvent
                        |
                        v
             Application running
                        |
                        v
         Return ConfigurableApplicationContext
          (to inspect or close when appropriate)
~~~

In chronological order, runners execute **before the run method returns to main**. Other startup events and preparation steps are handled by Spring Boot; the diagram above focuses on key learning milestones rather than listing every internal callback.

Relationships between classes:

- **SpringApplicationBuilder:** expresses how to construct and launch the application, supporting multi-context hierarchies.
- **SpringApplication:** executes the bootstrap process according to the received configuration.
- **Environment:** supplies properties and active profiles; influenced by multiple configuration sources.
- **ApplicationContext:** manages beans, dependency injection, and bean lifecycles.
- **ConfigurableApplicationContext:** the context returned by **run**; can be used to check status, retrieve beans, and close the context when appropriate for the application.

The builder is a **runtime initialization** tool; it is not itself a bean container and does not turn each fluent call into an independently executing "startup step."

## 3. Commonly Used APIs and Exact Meanings

| API | Role | Key Point to Remember |
| --- | --- | --- |
| **new SpringApplicationBuilder(App.class)** | Specifies one or more primary sources for the application | Usually a class with **@SpringBootApplication** or **@Configuration** |
| **sources(OtherConfig.class)** | Adds configuration/bean sources for the application | Does not mean automatically activating every package on the classpath |
| **profiles("dev")** | Adds an active profile | Should not be assumed to clear all already-active profiles |
| **properties("key=value")** | Sets default properties | Values have lower precedence than many external config sources, e.g., command-line arguments |
| **properties(Map)** | Sets multiple default properties from a map | Suitable when configuration is constructed programmatically |
| **bannerMode(Banner.Mode.OFF)** | Hides the startup banner | Does not mean turning off all logging |
| **web(WebApplicationType.NONE)** | Selects a non-web application | Does not create an HTTP server from web auto-configuration |
| **web(WebApplicationType.SERVLET)** | Requests a servlet web app model | Requires dependencies compatible with a servlet web runtime |
| **web(WebApplicationType.REACTIVE)** | Requests a reactive web app model | Requires corresponding reactive infrastructure |
| **listeners(...)** | Registers application event listeners early | Useful for events published before the context creates beans |
| **initializers(...)** | Registers **ApplicationContextInitializer** instances | Runs when the context is prepared before bean definitions are loaded |
| **logStartupInfo(false)** | Disables part of startup info logged by SpringApplication | Does not replace full logging configuration |
| **lazyInitialization(true)** | Enables lazy bean initialization | Can shift bean creation errors from startup to when the bean is first used |
| **parent(...)**, **child(...)** | Creates a hierarchical ApplicationContext | Increases complexity around bean scope, events, and configuration |
| **build()** | Builds the configured **SpringApplication** | Does not mean initializing/refreshing ApplicationContext yet |
| **run(args)** | Launches and returns **ConfigurableApplicationContext** | This is the key execution step |

In a simple application's code, there is no need to call every API. Configuration should only include options with a clear reason; configuring Spring Boot via files and environment variables is often sufficient for many cases.

### Comparing Three Launch Styles

**Style 1 — static convenience API:**

~~~java
SpringApplication.run(DemoApplication.class, args);
~~~

**Style 2 — create SpringApplication then customize:**

~~~java
SpringApplication application = new SpringApplication(DemoApplication.class);
application.setBannerMode(Banner.Mode.OFF);
application.setWebApplicationType(WebApplicationType.NONE);
application.run(args);
~~~

**Style 3 — fluent builder API:**

~~~java
new SpringApplicationBuilder(DemoApplication.class)
        .bannerMode(Banner.Mode.OFF)
        .web(WebApplicationType.NONE)
        .run(args);
~~~

All three can bootstrap the same application. The builder fits when multiple options benefit from sitting side by side for readability, when expressing a hierarchical context structure, or when building **SpringApplication** before running. Do not choose the builder just because you believe it inherently makes the runtime faster.

## 4. Complete Java 17+ Example: Observing Startup from Builder

### 4.1. Create the Project

Create a Maven project using Spring Initializr, selecting Java 17 or higher and Spring Boot 3.x (for example, a 3.5.x release suited to the project). Use the **Spring Boot Starter** dependency for a non-web application; there is no need to add Spring Web for this exercise. Set the package to **com.example.demo**, and create/rename the main class to **BuilderStartupApplication**. If the generated project already has another main class, ensure you run only the class illustrated in this lesson.

File **src/main/java/com/example/demo/BuilderStartupApplication.java**:

~~~java
package com.example.demo;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class BuilderStartupApplication {

    public static void main(String[] args) {
        System.out.println("01 | Configure builder");

        try (ConfigurableApplicationContext context =
                new SpringApplicationBuilder(BuilderStartupApplication.class)
                        .bannerMode(Banner.Mode.OFF)
                        .web(WebApplicationType.NONE)
                        .profiles("lab")
                        .properties("lesson.mode=builder")
                        .run(args)) {
            System.out.println("03 | Context active=" + context.isActive());
        }

        System.out.println("04 | Context closed");
    }

    @Bean
    ApplicationRunner inspectRuntime(Environment environment) {
        return args -> {
            System.out.println("02 | ApplicationRunner");
            System.out.println("     profile lab active="
                    + Arrays.asList(environment.getActiveProfiles())
                            .contains("lab"));
            System.out.println("     lesson.mode="
                    + environment.getProperty("lesson.mode"));
        };
    }
}
~~~

**Part-by-part explanation:**

1. **@SpringBootApplication** provides the primary configuration point of the application, including Spring Boot mechanisms related to auto-configuration and component scanning.
2. **new SpringApplicationBuilder(BuilderStartupApplication.class)** selects the source class and initializes the builder.
3. **bannerMode(Banner.Mode.OFF)** disables the decorative banner, without suppressing other startup logs.
4. **web(WebApplicationType.NONE)** forces this to be a non-web runtime; the exercise creates no REST endpoints and opens no HTTP port.
5. **profiles("lab")** adds the **lab** profile to the set of active profiles.
6. **properties("lesson.mode=builder")** sets a default value for the exercise property.
7. **run(args)** executes startup, creates/refreshes the context, and runs runners before returning to main.
8. The **ApplicationRunner** bean prints values retrieved from **Environment** once startup reaches the runner phase.
9. **try-with-resources** closes the context after main passes through the try block. This style **deliberately demonstrates a short-lived lifecycle**; a long-running HTTP server does not normally close itself right after **run** returns.

### 4.2. Run and Test

From the root directory of the project generated by Spring Initializr:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows (PowerShell/cmd)
# .\mvnw.cmd spring-boot:run
~~~

The lines **printed by the example code itself**, in order, will be:

~~~text
01 | Configure builder
02 | ApplicationRunner
     profile lab active=true
     lesson.mode=builder
03 | Context active=true
04 | Context closed
~~~

Spring Boot may print additional logging and environment info between these lines; the block above does not claim to be the entire stdout. The output above assumes no external configuration source overrides **lesson.mode** and no startup error occurs. **Context active=true** is printed while the try block is still open; after closing, main prints **Context closed**.

You cannot take the Java file alone and compile it with **javac** without the Spring Boot classpath. Run through the project's Maven Wrapper/Gradle Wrapper so the build tool provides dependencies and executes the proper main class.

### 4.3. Passing Command-Line Arguments and Observing Configuration Precedence

Package the project:

~~~bash
./mvnw package
~~~

Run the executable JAR generated in the **target** directory (substitute your project's actual JAR filename):

~~~bash
java -jar target/builder-demo.jar --lesson.mode=command-line
~~~

If the actual artifact has a different name, replace **builder-demo.jar** with the built JAR filename. When command-line properties are enabled by default, the **--lesson.mode=command-line** argument has higher precedence than the default property declared via **properties("lesson.mode=builder")**. That line then changes to:

~~~text
     lesson.mode=command-line
~~~

This demonstrates the difference between **"a default value proposed by the builder"** and **"the effective value resolved by Environment"**. Other configuration sources, such as environment variables, config files, or command-line arguments, still participate in Spring Boot's externalized configuration mechanism.

If the application needs environment-specific configuration across deployments, consider using application.yml, profiles, and environment variables. Never hardcode secrets such as passwords or API tokens in **properties(...)** in source code.

## 5. Builder and SpringApplication Lifecycle Milestones

### Before run(args)

The builder simply holds the supplied options. For instance:

~~~java
SpringApplicationBuilder builder =
        new SpringApplicationBuilder(BuilderStartupApplication.class)
                .web(WebApplicationType.NONE);

SpringApplication application = builder.build();
~~~

**build()** returns a **SpringApplication** that can subsequently be used to run:

~~~java
ConfigurableApplicationContext context = application.run(args);
~~~

If you only call **build()** without calling **run()**, the application has not been bootstrapped into an active context yet. In ordinary code, calling **builder.run(args)** directly is easier to read when you do not need to keep the SpringApplication instance.

### During run(args)

The main activities coordinated by Spring Boot include: preparing Environment, creating the appropriate ApplicationContext, applying configuration, instantiating and wiring beans, refreshing the context, running runners, and then publishing corresponding startup events. Events like **ApplicationStartingEvent** appear very early; **ApplicationPreparedEvent** occurs before refresh; **ApplicationStartedEvent** occurs once the context has refreshed but before runners; **ApplicationReadyEvent** occurs after runners finish. When startup encounters an error, **ApplicationFailedEvent** may be published.

This helps identify the right hook for each need:

| Need | Suggestion |
| --- | --- |
| Intervene early before beans are loaded | **ApplicationContextInitializer** when appropriate |
| Listen to very early events | **builder.listeners(...)**, rather than a bean listener created later |
| Run a task after the context is initialized | **ApplicationRunner** or **CommandLineRunner** |
| React when Boot marks the application as ready | **ApplicationReadyEvent** |
| Execute business logic on each incoming request | Controller/service or corresponding handler; do not put in **main** |

For applications with readiness/liveness probes, **ApplicationReadyEvent** is Spring Boot's milestone; the actual status used by the deployment platform to route traffic also depends on probe configuration and external dependencies. Do not assume the system is completely healthy solely because **run(args)** returned.

### After run(args)

The **context** variable lets you inspect state, retrieve beans when genuinely needed, or call **close()** if the application's lifecycle requires it. For web applications continuously serving requests, **main** typically does not immediately close the context; Spring Boot usually registers a JVM shutdown hook to close managed resources on normal termination.

Distinguish **a running Java process** from **an active ApplicationContext**. The builder creates the runtime by asking SpringApplication to bootstrap a context; process and JVM resources remain managed by their respective layers.

## 6. Variation: Launching a Web Application from Builder

When the project has the **Spring Web** dependency and the main class is a servlet web application, you can write:

~~~java
new SpringApplicationBuilder(ApiApplication.class)
        .bannerMode(Banner.Mode.OFF)
        .web(WebApplicationType.SERVLET)
        .properties("server.port=8088")
        .run(args);
~~~

This is an **illustrative configuration snippet**, not a standalone complete Java program because **ApiApplication** and dependencies are not defined here. With a valid servlet web runtime, Boot creates the server as configured and opens port **8088** unless overridden by a higher-precedence config source.

If you just want Boot to auto-detect the application type from the classpath, you can **omit web(...)**. When both MVC and WebFlux are on the same classpath, default detection follows Spring Boot's rules; set **web(WebApplicationType.REACTIVE)** or **SERVLET** only when you intentionally select that runtime type and have the required dependencies.

Do not use **WebApplicationType.NONE** and expect a REST controller to open an HTTP port: NONE intentionally skips creating a web server. Do not close the context immediately via try-with-resources like the non-web example if the goal is to keep the HTTP server serving incoming requests.

## 7. Advanced: Expressing a Parent/Child ApplicationContext Hierarchy

A notable feature of **SpringApplicationBuilder** is creating a context hierarchy when an application genuinely needs to separate shared configuration layers from the web layer:

~~~java
new SpringApplicationBuilder(ParentConfiguration.class)
        .web(WebApplicationType.NONE)
        .child(WebApplication.class)
        .web(WebApplicationType.SERVLET)
        .run(args);
~~~

The snippet above **only illustrates the builder structure**; to run it, you must define **ParentConfiguration**, **WebApplication**, appropriate beans, and dependencies, while avoiding component scanning registering duplicate configurations across both contexts.

How to read the snippet:

1. Create configuration for the **parent context** from **ParentConfiguration** and set the parent to non-web.
2. **child(WebApplication.class)** switches to a builder representing the child context, using **WebApplication** as the child configuration source.
3. **web(WebApplicationType.SERVLET)** sets the web type for the child context.
4. **run(args)** launches the hierarchical structure and returns the context at the current builder level.

Rules to understand before applying this:

- Beans in the **child context** can look up beans from the **parent** through the appropriate lookup mechanism; the parent cannot automatically see beans declared only in the child.
- Spring Boot places certain constraints on context hierarchies; **web components must belong to the child context**, and contexts in the hierarchy share **Environment** according to the builder's contract.
- Child startup events can propagate up to the parent. Listeners in the parent may receive the same event type multiple times because multiple contexts exist; compare the event source context if you need to distinguish them.
- Calling **parent(...)** and **child(...)** affects context structure; it does not mean the two contexts are completely isolated regarding properties or events.
- Do not create a hierarchy just to "modularize" code. Most Boot applications are easier to maintain with a single ApplicationContext and clean package/bean organization.

In a microservices architecture, two independent services are normally two separately deployed processes/applications; a parent/child context is **not equivalent** to two microservices.

## 8. When Should You Use SpringApplicationBuilder?

**Appropriate situations:**

- Wanting launch choices clearly visible in one place inside **main**: profiles, runtime type, default properties, or listeners.
- Needing to build a non-web application to run a background program using Spring's bean infrastructure.
- Needing bootstrap customization before **ApplicationContext** exists.
- Needing to organize a parent/child hierarchy by deliberate design.

**Unnecessary situations:**

- An ordinary Spring Boot service with standard startup; **SpringApplication.run(...)** is clear enough.
- Only needing to change port, database URL, or log levels across environments; config files and environment variables are usually more appropriate.
- Wanting to configure a business bean; use **@Bean**, component stereotypes, and dependency injection.
- Wanting to control request/transaction logic after startup; the builder is not responsible for this.

Builder options are application-level bootstrap settings; they do not replace bean design or configuring thread pools, timeouts, security, or monitoring for runtime.

## 9. Common Mistakes and How to Spot Them

| Symptom / Misconception | Common Cause | How to Handle |
| --- | --- | --- |
| Called **build()** and application does not run | **build** only creates SpringApplication | Call **run(args)** on the builder or SpringApplication |
| Called **web(NONE)** and no HTTP port opens | NONE is non-web mode | Switch to the right web type and add required dependencies |
| Settings from **properties(...)** seem "lost" | These are default properties, overridable by other sources | Check Environment, command-line args, profiles, env vars |
| Banner disappeared but logs still appear | Banner and logging are separate mechanisms | Configure logging separately if needed |
| Bean listener misses very early events | Events fire before ApplicationContext creates beans | Register at bootstrap via **listeners(...)** if appropriate |
| Beans exist yet application fails at startup | Missing dependency, bean conflict, invalid config, or initialization error | Read root exception and startup log; do not blame the builder |
| Runner runs before code after **run(...)** executes | That is the right order: runners run in the startup phase | Move logic to the hook matching the requirement |
| Launched web app then closed context immediately | **close()**/try-with-resources ends context lifecycle | Do not close when it must keep serving |
| Parent cannot seem to find bean in child | Bean lookup across contexts is asymmetric | Place shared beans in parent or redesign |
| Event listener runs multiple times in hierarchy | Child events propagate up to parent | Check the ApplicationContext attached to the event |
| Added **profiles("dev")** and assumed only one profile is active | profiles is additive; multiple sources can activate profiles | Inspect actual **Environment.getActiveProfiles()** |

## 10. Practice Exercises

**Exercise 1 — Default property and command-line override:** run the section 4 example normally, then run the JAR with **--lesson.mode=command-line**. Compare the **lesson.mode** line. Explain why the output changed even though the builder kept the exact same **properties(...)** call.

**Exercise 2 — Non-web vs web:** answer why **web(WebApplicationType.NONE)** does not open a port even with Spring Boot on the classpath. Then outline the dependencies and changes required to use **WebApplicationType.SERVLET** to serve a REST endpoint.

**Exercise 3 — Startup order:** order the four milestones: creating the builder, **run(args)**, **ApplicationRunner**, the **Context active=true** line in main. Explain why the runner executes before the last line even though the bean method is declared below main.

**Exercise 4 — Context hierarchy:** examine the parent/child illustration and determine which context should hold web components; whether the parent can directly access a bean declared only in the child; and why a parent listener might observe multiple events.

Key answers: (1) command-line properties take precedence over default properties; (2) NONE chooses not to initialize a web runtime, servlet mode needs the right dependencies; (3) create builder → run starts → runner executes inside run → run returns context then main prints status; (4) web belongs in child, bean lookup primarily flows from child up to parent, events can propagate up to ancestors.

## 11. Takeaways and References

**SpringApplicationBuilder expresses launch configuration explicitly and can construct context hierarchies. Only the run(args) method creates the runtime, returns an active ApplicationContext, and triggers Spring Boot's startup milestones.** Clearly distinguishing **configure builder → execute SpringApplication → operate context** is the core lesson.

Official documentation to verify behavior for your project's version:

- Spring Boot Reference — SpringApplication, Fluent Builder API, and Application Events: https://docs.spring.io/spring-boot/4.0/reference/features/spring-application.html
- Spring Boot 3.5 API — SpringApplicationBuilder: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/builder/SpringApplicationBuilder.html
- Spring Boot Reference — How-to / ApplicationContext hierarchy, non-web application: https://docs.spring.io/spring-boot/4.0/how-to/application.html

When bringing examples into a project on a different Spring Boot version, verify against the Javadoc for that exact version, especially for advanced bootstrap settings and context hierarchy behavior.