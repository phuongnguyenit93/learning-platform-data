# The spring.main.* Property Group and When It Is Applied in Spring Boot

## 1. Which Component Does spring.main.* Configure?

**spring.main.*** is the property group used to **configure the `SpringApplication` instance itself while it is starting up**: selecting whether the application is web or non-web, enabling/disabling the banner, controlling bean initialization, handling duplicate bean definitions or circular references, startup logging, and certain lifecycle policies. Spring Boot binds these values from **Environment** onto **SpringApplication** during the bootstrap process.

This is not the prefix for all Spring Boot configuration. For example:

- **spring.main.web-application-type** determines the type of context that SpringApplication attempts to create; **server.port** adjusts the port of the web server *if a web server exists*.
- **spring.main.lazy-initialization** affects the general bean initialization policy; a **@Lazy** annotation on a specific bean can create an exception for that bean.
- **spring.main.banner-mode** selects the banner printing mode; **spring.banner.location** points to the banner file.
- **spring.config.location** and **spring.config.name** determine where configuration files are loaded from at an earlier stage; **spring.profiles.active** selects profiles; they do not belong to the **spring.main.*** group.

The examples and lists below target **Spring Boot 3.3.x**, compatible with **Java 17+**. When upgrading Boot versions, check the Application Properties appendix of the exact version in use, because property names and configuration capabilities may change.

## 2. Key Point: Read and Applied Before Refreshing ApplicationContext

**Spring does not wait until beans are created to apply spring.main.*.** The simplified order of a successful startup is:

~~~text
Main code:
  new SpringApplication(MyApplication.class) / SpringApplication.run(...)
       |
       v
SpringApplication.run starts
  -> ApplicationStartingEvent
       |
       v
Prepare Environment
  -> read --... arguments, System properties, environment variables
  -> process Config Data: application.properties / application.yaml,
     profile-specific documents, config imports
  -> ApplicationEnvironmentPreparedEvent
       |
       v
Bind spring.main.* properties onto SpringApplication
  -> bindToSpringApplication(Environment)
       |
       v
Print banner (if enabled)
  -> select and create appropriate ApplicationContext
  -> prepare context, register sources, customize bean factory
       |
       v
Refresh ApplicationContext
  -> register/process bean definitions
  -> instantiate non-lazy beans
  -> execute container lifecycle mechanisms
       |
       v
ApplicationStartedEvent -> ApplicationRunner / CommandLineRunner
  -> ApplicationReadyEvent -> readiness
       |
       v
SpringApplication.run(...) returns ApplicationContext
~~~

This is a **high-level diagram**, not an exhaustive list of every internal callback. The most important point: **Environment and Config Data are already prepared before SpringApplication creates/refreshes the context**. Therefore, settings such as context type, bean factory policies, and lazy initialization have the opportunity to take effect during that very startup.

Points in time to distinguish:

1. **When instantiating the SpringApplication object:** Boot infers some default values from the classpath, such as the web application type; Java code can also call setters to customize it before running.
2. **During prepareEnvironment:** Spring Boot gathers `PropertySource`s, processes external configuration and profiles, and then binds the matching **spring.main.*** properties onto SpringApplication.
3. **Before or during prepareContext/refresh:** each property is *used* at the point where it is needed: selecting the context, printing the banner, processing configuration sources, managing bean definitions, and instantiating beans.
4. **After startup and at shutdown:** some options are read from the beginning, but their actual effect appears later, such as keeping the JVM alive or registering a shutdown hook.

**Reading configuration early** and **seeing the effect of configuration** are two different things. For example, **spring.main.lazy-initialization=true** is bound early, but becomes apparent when Spring decides whether to create beans during refresh or when a bean is accessed later.

## 3. Common spring.main.* Properties in Spring Boot 3.3

The following table covers the main keys listed in the Spring Boot 3.3.13 Common Application Properties appendix. Default values may be overridden by the application or a higher-precedence configuration source.

| Property | Boot 3.3 Default | Purpose and When It Takes Effect |
| --- | --- | --- |
| **spring.main.web-application-type** | Auto-detected from classpath | Selects **none**, **servlet**, or **reactive**; used when selecting/creating the ApplicationContext, before refresh. |
| **spring.main.banner-mode** | **console** | **console**, **log**, or **off**; determines how the banner is handled at the beginning of startup, before the context is refreshed. |
| **spring.main.log-startup-info** | **true** | Enables/disables the startup information lines generated by SpringApplication; affects logs at startup milestones, does not disable all logging. |
| **spring.main.lazy-initialization** | **false** | Enables on-demand bean initialization; applied to bean policies before the bean instantiation phase during refresh. |
| **spring.main.allow-bean-definition-overriding** | **false** | Allows/disallows registering a new bean definition with the **same name** as an existing bean definition; takes effect during bean definition registration. |
| **spring.main.allow-circular-references** | **false** | Allows Spring to attempt resolving certain bean circular references; configures the bean factory before bean instantiation, does not guarantee resolving every cycle. |
| **spring.main.sources** | None declared | Adds configuration sources such as class names or packages; used when Spring loads sources into the context before refresh. |
| **spring.main.register-shutdown-hook** | **true** | Enables registering a hook to close the context on JVM shutdown; configured at bootstrap, actual effect occurs at shutdown. |
| **spring.main.keep-alive** | **false** | Keeps the JVM alive even when no other non-daemon threads remain; useful for workloads using virtual threads; effect relates to process lifecycle after startup. |
| **spring.main.cloud-platform** | Auto-detected if applicable | Overrides SpringApplication's detected cloud platform value; set only when there is a clear reason to replace auto-detection. |

Typical usages:

- CLI/batch programs that do not need an HTTP server: **spring.main.web-application-type=none**.
- To reduce console noise: **spring.main.banner-mode=off**; consider **log-startup-info=false** if startup info log lines are genuinely unnecessary.
- To experiment with startup optimization: **spring.main.lazy-initialization=true**, then re-measure first-request latency and check for bean errors detected late.
- Java 21 applications using **@Scheduled** with virtual threads that risk having no non-daemon threads left to keep the JVM alive: consider **spring.main.keep-alive=true**. This property does not replace readiness conditions or health checks.

### 3.1. web-application-type and the Classpath

If not configured explicitly, SpringApplication deduces the application type from the libraries on the classpath:

- **servlet:** typically uses Spring MVC and a servlet web server.
- **reactive:** uses the WebFlux/reactive stack if classpath conditions match.
- **none:** a regular context, does not start an embedded web server.

When both Spring MVC and WebFlux are present, Spring MVC usually takes precedence in auto-detection. You can use **spring.main.web-application-type=reactive** to request the reactive type when compatible dependencies exist. Setting **none** prevents SpringApplication from starting an embedded web server for that context, even if **server.port** remains in the configuration file.

Selecting a context type **does not automatically add dependencies**. If you force **servlet** or **reactive** without the corresponding runtime components, startup can fail.

### 3.2. Bean Definition Overriding vs. Beans of the Same Type

**spring.main.allow-bean-definition-overriding=true** allows bean definitions with the same **name** to override each other in the corresponding cases. It does not resolve situations with **two beans of the same type** during dependency injection; a **NoUniqueBeanDefinitionException** still requires **@Primary**, **@Qualifier**, or appropriate design. Enabling overriding indiscriminately easily masks configuration conflicts.

**spring.main.allow-circular-references=true** is also not a fix for every dependency cycle. A mandatory constructor injection cycle between two beans generally cannot be resolved merely by enabling this flag. The better approach is to separate responsibilities, avoid dependency cycles, or redesign the interaction points between beans.

### 3.3. lazy-initialization Does Not Mean "Create No Beans"

When lazy initialization is enabled, Spring still has to create beans needed to run bootstrap, beans required by other beans, or beans declared with **@Lazy(false)**. Beans not yet needed may only be created when an endpoint, listener, or your code calls them. Therefore, an application starting up successfully **does not guarantee** that all lazy beans are valid.

Lazy initialization can reduce startup time at the trade-off of latency on the first access and delayed detection of configuration errors.

## 4. Where Should spring.main.* Values Be Written?

### 4.1. application.properties

Place in **src/main/resources/application.properties**:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
spring.main.lazy-initialization=true
spring.main.allow-bean-definition-overriding=false
spring.main.allow-circular-references=false
~~~

This is configuration for a **non-web** application, illustrating reducing the banner/startup logs and using lazy initialization. The **false** flags on the last two lines restate the default policy in Boot 3.3; you are not required to declare them.

The same content in **application.yaml** format (pick one primary format for the project):

~~~yaml
spring:
  main:
    web-application-type: none
    banner-mode: off
    log-startup-info: false
    lazy-initialization: true
    allow-bean-definition-overriding: false
    allow-circular-references: false
~~~

### 4.2. Runtime Arguments

When you have a Spring Boot JAR file named **app.jar**:

~~~bash
java -jar app.jar --spring.main.banner-mode=console --spring.main.lazy-initialization=false
~~~

In standard configurations, these two arguments are placed into **Environment** and have higher precedence than values with the same keys in **application.properties**. This is a way to test configuration changes for a single run without editing files.

With the Gradle Boot plugin, you can pass these arguments to the program:

~~~bash
./gradlew bootRun --args='--spring.main.lazy-initialization=false'
~~~

If the project uses Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--spring.main.lazy-initialization=false"
~~~

**Note:** **--spring.main.*** is a Spring Boot application argument. It differs from options for the Gradle runner itself or the JVM such as **-Xmx**.

### 4.3. Environment Variables and JVM System Properties

Values can come from OS environment variables, JVM system properties, Config Data, or command-line arguments. Spring Boot supports relaxed binding for property names. For example, the canonical environment variable name is **SPRING_MAIN_LOGSTARTUPINFO**, corresponding to **spring.main.log-startup-info**: replace dots with underscores, remove hyphens, and uppercase.

With a Java system property:

~~~bash
java -Dspring.main.banner-mode=off -jar app.jar
~~~

In this pattern, **-D** appears before **-jar** so the JVM sets the system property itself.

### 4.4. Precedence Order and Java Setters

SpringApplication has Java setters to configure it before running:

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.setBannerMode(org.springframework.boot.Banner.Mode.OFF);
application.run(args);
~~~

If **application.properties** also contains:

~~~properties
spring.main.banner-mode=console
~~~

the external value will **override the property set via the setter** when Spring Boot binds **spring.main.*** onto SpringApplication. Thus, the banner is printed in **console** mode, provided no higher-precedence source changes this value.

**Notable exception:** *primary sources* passed to the constructor **new SpringApplication(MyApplication.class)** or primary sources from SpringApplicationBuilder are preserved. If you set **spring.main.sources=com.example.MoreConfig**, that source **is added**, not replacing **MyApplication.class**.

In common configurations, **command line arguments** take precedence over **Java system properties**, which take precedence over **OS environment variables**, and these sources take precedence over **application.properties/application.yaml**. Config Data has its own rules for locations, profiles, and imported documents; when you need to find the actual effective value, inspect which PropertySource is winning rather than looking at just one file.

## 5. Why Are @PropertySource and @PostConstruct Often "Too Late"?

This is a very easy mistake to make when distinguishing **bootstrap configuration** from **bean configuration**:

~~~java
@Configuration
@PropertySource("classpath:late.properties")
class ExtraConfiguration {
}
~~~

If **late.properties** contains:

~~~properties
spring.main.web-application-type=none
~~~

do not expect it to change the ApplicationContext type. Spring Boot reads **@PropertySource** on **@Configuration** classes while processing/refreshing the context, whereas **spring.main.*** has already been bound onto SpringApplication **before refresh**. That is why the Spring Boot documentation explicitly notes that **@PropertySource** is too late for properties like **logging.*** and **spring.main.***.

Similarly:

~~~java
@PostConstruct
void changeStartupOption() {
    System.setProperty("spring.main.banner-mode", "off");
}
~~~

This example only illustrates **an operation at the wrong time** (assuming a bean contains the method above). By the time **@PostConstruct** runs, the banner has already been handled, the context type has been selected, and many startup settings have already been applied. Modifying a System property at that point does not go back and re-run completed steps.

**Practical rule:** to configure how SpringApplication starts up, supply properties via **Config Data**, CLI, environment, or system properties **before bootstrap reads them**. For configuration that even affects locating configuration files—such as **spring.config.name**, **spring.config.location**, and **spring.config.additional-location**—you must supply them at a very early stage (typically via CLI, System properties, or environment variables), not inside the very file being located.

## 6. Runnable Java 17+ Example: Observing Lazy Initialization and Binding Time

Create a Boot 3.3 application with the **spring-boot-starter** dependency and the corresponding build plugin. Java file:

**src/main/java/com/example/runtime/MainPropertiesDemo.java**

~~~java
package com.example.runtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MainPropertiesDemo {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(MainPropertiesDemo.class, args)) {

            System.out.println("Context active = " + context.isActive());

            boolean alreadyCreated =
                    context.getBeanFactory()
                           .containsSingleton("expensiveService");

            System.out.println(
                    "ExpensiveService created before lookup = "
                            + alreadyCreated);

            context.getBean(ExpensiveService.class).sayHello();
        }
    }

    @Bean
    ExpensiveService expensiveService() {
        return new ExpensiveService();
    }

    static class ExpensiveService {
        ExpensiveService() {
            System.out.println("Creating ExpensiveService");
        }

        void sayHello() {
            System.out.println("Hello from ExpensiveService");
        }
    }
}
~~~

Place in **src/main/resources/application.properties**:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
spring.main.lazy-initialization=true
~~~

Run:

~~~bash
./gradlew bootRun
~~~

Provided no other component proactively requests the **expensiveService** bean before **main** looks it up, the lines printed by the program itself, in order, are:

~~~text
Context active = true
ExpensiveService created before lookup = false
Creating ExpensiveService
Hello from ExpensiveService
~~~

Explanation: **run(...)** returned an active context, yet the **expensiveService** bean has not been initialized due to lazy initialization. The **context.getBean(...)** call creates the bean, producing the **Creating...** line, and only then invokes **sayHello()**. Some other library components may interleave log lines depending on configuration.

Run again and override the property from the command line:

~~~bash
./gradlew bootRun --args='--spring.main.lazy-initialization=false'
~~~

When lazy initialization is disabled, this standard singleton bean is created during refresh, **before run(...) returns**. The lines printed by the program will be in the order:

~~~text
Creating ExpensiveService
Context active = true
ExpensiveService created before lookup = true
Hello from ExpensiveService
~~~

The verification point here is that **the value from the CLI affected bean creation before the first statement after run(...) executed**.

**Why does the example close the context?** This is a short **non-web** program using **try-with-resources** to release the context after the observation. In a long-running web application, do not close the context immediately after **SpringApplication.run(...)**, because doing so will stop the application.

## 7. Concrete Mapping Between Property Groups and Lifecycle Milestones

Do not assume all properties take effect at the same moment. They can be grouped as follows:

| Phase | Related Property Group | Observable Effect |
| --- | --- | --- |
| After Environment/Config Data is ready | All **spring.main.*** with matching mappings | Values from Environment are bound onto SpringApplication before creating/refreshing the context. |
| Banner printing | **banner-mode** | Whether the banner is printed to console, log, or skipped. |
| Context creation and preparation | **web-application-type**, **sources**, **cloud-platform** | Selects the context, registers input configuration, and applies environment characteristics. |
| Bean registration and creation | **allow-bean-definition-overriding**, **allow-circular-references**, **lazy-initialization** | Affects the bean factory and how beans are registered/instantiated. |
| Startup log milestones | **log-startup-info** | Enables/disables the startup info log lines managed by SpringApplication. |
| Application lifecycle | **register-shutdown-hook**, **keep-alive** | Affects whether the JVM stays alive and/or whether the context is closed on JVM shutdown. |

**ApplicationStartedEvent** is published **after refresh**, before **ApplicationRunner/CommandLineRunner**. **ApplicationReadyEvent** is published **after runners**. The **spring.main.*** configuration has already exerted its influence on bootstrap before these events; waiting until a runner to reset startup properties is too late for the current run.

Early events in the chain, such as **ApplicationEnvironmentPreparedEvent**, occur before the context is created; listeners can observe or adjust the Environment at the appropriate early stage, but you need to understand listener ordering and Config Data. The easiest approach to control when framework customization is not needed is to supply configuration right in **application.properties**, **application.yaml**, CLI, or the deployment system.

## 8. Common Mistakes and How to Diagnose Them

### 8.1. Setting spring.main.web-application-type=none Yet Expecting HTTP Endpoints to Work

**none** intentionally omits the web application context/embedded server. To expose HTTP endpoints, you need a web application type and appropriate dependencies; **server.port=8080** alone does not create a server when SpringApplication runs in none mode.

### 8.2. Enabling allow-circular-references=true to "Fix" a Constructor Injection Cycle

This property only allows Spring to attempt resolving supported kinds of circular references. A constructor injection cycle cannot turn itself into a valid dependency graph because of a configuration flag. Inspect the stack trace, identify the beans in the cycle, and redesign the dependencies.

### 8.3. Enabling Overriding to Avoid Errors Injecting Two Beans of the Same Type

**allow-bean-definition-overriding** handles **duplicate definition names**; **@Qualifier** or **@Primary** solves choosing a bean when multiple candidates share the same type. The two errors have different root causes.

### 8.4. Turning Off log-startup-info and Thinking All Logs Are Disabled

**spring.main.log-startup-info=false** does not turn off loggers for libraries, beans, the web server, or the application. Control other logs with **logging.level.*** and the corresponding logging configuration.

### 8.5. Looking Only at application.properties When Results Do Not Match Expectations

Check environment variables, Java System properties, **--...** arguments, external files outside the JAR, and profile-specific files. For example, **--spring.main.banner-mode=console** on the CLI can beat **spring.main.banner-mode=off** in a file. Use property-source inspection mechanisms when needed, such as the Actuator **env** endpoint in an appropriately secured environment.

### 8.6. Changing Environment After the Application Is Ready and Expecting Startup to Re-run

After **run(...)**, Spring does not automatically recreate the ApplicationContext or re-execute banner printing, source loading, and bean factory configuration. To change bootstrap properties, you normally must **restart the application** with the new configuration.

### 8.7. Enabling Lazy Init and Assuming All Configuration Errors Were Caught at Startup

A lazy bean may only reveal an error on the first request or first task that requires it. Test actual usage flows, especially for critical dependencies; consider **@Lazy(false)** for beans that must be verified early.

## 9. Self-Check Questions

**Question A.** In **application.properties**, **spring.main.banner-mode=off** is set. In Java code, **application.setBannerMode(Banner.Mode.CONSOLE)** is called before **run(args)**. No other configuration source overrides it. What is the result?

**Answer:** The **off** mode from external configuration is bound onto SpringApplication during bootstrap and beats the Java setter value.

**Question B.** You put **spring.main.web-application-type=none** in a file loaded via **@PropertySource** on a **@Configuration** class. Is SpringApplication guaranteed to select a non-web context?

**Answer:** No. **@PropertySource** is processed too late for the **spring.main.*** group; place the value in Config Data, CLI, system properties, or appropriate environment variables.

**Question C.** **ApplicationReadyEvent** has been received, yet a lazy bean has never been requested. Has that bean definitely been created?

**Answer:** No. **ApplicationReadyEvent** marks the startup/runner milestone; the lazy initialization policy can defer bean instantiation until it is requested.

**Question D.** **spring.main.sources** declares two additional configuration classes. Does **MyApplication.class** passed into the constructor disappear?

**Answer:** No. The additional sources participate in the context together; the initial primary source is not replaced just by configuring additional sources.

**Question E.** Does disabling **register-shutdown-hook** cause the application to stop running right after **run(...)**?

**Answer:** No. That flag controls registering the shutdown hook, not instructing the process to exit. If the default hook is disabled, the application needs another way to close the context/resources properly according to its lifecycle.

## 10. Key Takeaway

**spring.main.*** are the switches configuring **SpringApplication before the context finishes initialization**, pulled from Environment and attached to the launcher object during bootstrap. **Binding time** happens early; **effect time** depends on each property: printing the banner, selecting the context, registering and creating beans, startup logs, or shutdown/JVM lifecycle.

When a value does not take effect, check **which configuration source actually wins** and **whether the value was available early enough**. In particular, **@PropertySource** and **@PostConstruct** are not suitable places to alter bootstrap decisions that have already been made.

### Official References

- Spring Boot 3.3.13 — Common Application Properties (see spring.main.* group): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html
- Spring Boot 3.3 — Externalized Configuration (PropertySource order, @PropertySource too late warning): https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — SpringApplication API (bindToSpringApplication, createApplicationContext): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot — Properties and Configuration / Externalize the Configuration of SpringApplication: https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html
- Spring Boot 3.3 — SpringApplication (lazy initialization, lifecycle/events): https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html