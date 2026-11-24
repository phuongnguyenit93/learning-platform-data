# Registering SpringApplicationRunListener, Constructor Requirements, and Execution Order

## 1. What kind of extension point is SpringApplicationRunListener?

**SpringApplicationRunListener** is an extension interface at the **SpringApplication.run(...)** layer. It allows a library or application to observe—and when truly necessary, lightly intervene in—very early milestones of the Spring Boot startup lifecycle: from starting the run, preparing the Environment, creating the ApplicationContext, refreshing the context, running startup runners, through reaching ready or failing.

Key characteristics of RunListener:

- One RunListener instance is created **per `SpringApplication.run(...)` call**, via Spring's factory loading mechanism.
- It is loaded **before the ApplicationContext is complete**, so it is not a regular Spring bean and does not receive automatic dependency injection like beans inside the context.
- Its methods are called by SpringApplication at **deterministic points**, rather than running as a separate worker thread, scheduler, or listener after services are ready.
- In Spring Boot 3.x, the interface methods are **default methods**, so you only need to override the callbacks you actually need.

RunListener is useful when integrating early startup observability, collecting startup timestamps, adding hooks in an infrastructure library, or diagnosing why bootstrap failed to reach the ready state. For normal business logic, use **ApplicationRunner**, **CommandLineRunner**, **ApplicationListener**, or bean/lifecycle hooks instead of defaulting to a RunListener.

**Distinguish two similar terms:** SpringApplicationRunListener receives **lifecycle callback invocations from SpringApplication**. ApplicationListener receives **application events** such as ApplicationStartedEvent and ApplicationReadyEvent published by Spring's event mechanism. Spring Boot includes an internal RunListener named **EventPublishingRunListener** acting as a bridge that publishes these events, but the two interfaces are not the same.

## 2. How to register RunListener in Spring Boot 3.x

Spring Boot uses **SpringFactoriesLoader** to locate and instantiate implementations of SpringApplicationRunListener from the classpath resource:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Example file contents:

~~~properties
org.springframework.boot.SpringApplicationRunListener=example.TraceRunListener
~~~

Here:

- On the left of the equals sign is **the fully qualified interface name**: org.springframework.boot.SpringApplicationRunListener.
- On the right is **the fully qualified implementation class name** (including package), not a bean name, Java filename, or method name.
- After packaging, the resource must actually exist at **META-INF/spring.factories** on the classpath. In standard Gradle/Maven projects, a file placed at **src/main/resources/META-INF/spring.factories** is copied into the output resources.
- If multiple implementations are needed, list them comma-separated, or across lines using valid properties continuation syntax. SpringFactoriesLoader loads the factories declared on the classpath and then applies their ordering.

Example registering two listeners:

~~~properties
org.springframework.boot.SpringApplicationRunListener=example.TraceRunListener,example.SecondRunListener
~~~

**In Spring Boot 3.x, RunListeners are still registered via META-INF/spring.factories.** Do not place that declaration in **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**: that path is for registering **auto-configuration classes**, not the SpringApplicationRunListener registry.

Do not just annotate a RunListener class with **@Component** and expect SpringApplication to discover it during early startup. Component scanning runs after RunListeners have already been loaded. Similarly, **app.addListeners(...)** adds an **ApplicationListener** to receive events; it is not the API for registering a SpringApplicationRunListener.

## 3. Exact constructor requirements

In Spring Boot 3.3.x, the implementation class must have a **public constructor** taking these exact two parameters in order and type:

~~~java
public TraceRunListener(SpringApplication application, String[] args) {
    // Store needed information without depending on Spring beans.
}
~~~

This is the signature used for an actual implementation class. The import for SpringApplication is **org.springframework.boot.SpringApplication**.

**Why does this constructor matter?** SpringApplication retrieves every declared RunListener via SpringFactoriesLoader and passes to the instantiation mechanism:

1. The **SpringApplication** currently starting.
2. The **String[]** arguments passed directly to **SpringApplication.run(args)**.

This mechanism does not instantiate RunListeners through the Spring BeanFactory, so the constructor should not require beans such as DataSource, an Environment bean, a Repository, or a custom service. At the moment RunListeners are created, the ApplicationContext has not been fully built yet.

Common mistakes:

| Constructor or design | Result |
| --- | --- |
| public TraceRunListener(SpringApplication application, String[] args) | Valid signature |
| Non-public TraceRunListener(SpringApplication application, String[] args) | Fails the public constructor requirement |
| public TraceRunListener() | Missing the two SpringApplication and String[] parameters |
| public TraceRunListener(String[] args, SpringApplication application) | Wrong parameter order per the contract |
| public TraceRunListener(SpringApplication application, List<String> args) | Wrong type for the second parameter |
| Constructor requesting @Autowired MyService | No bean constructor injection mechanism exists at this stage |
| Only declaring @Component without spring.factories | Not automatically loaded as a SpringApplicationRunListener |

A mistake in class name, package, constructor, or initialization dependency in **spring.factories** can prevent **SpringFactoriesLoader** from instantiating the RunListener and cause startup to fail before the context is even prepared. Keep the constructor simple: record provided args/config, avoid slow I/O, and do not open hard-to-clean resources.

**Each `run(...)` gets a new instance**—meaning this is not a Spring singleton. Do not store state in the instance to share data across application runs, and do not assume there is always only one `run(...)` in applications with multiple SpringApplications or a context hierarchy.

## 4. Callback order during a successful startup

Callbacks in the standard logical sequence:

| Order | Callback on SpringApplicationRunListener | State when called |
| --- | --- | --- |
| 1 | starting(ConfigurableBootstrapContext) | Right when SpringApplication.run(...) begins, before Environment is fully prepared |
| 2 | environmentPrepared(ConfigurableBootstrapContext, ConfigurableEnvironment) | Environment prepared, ApplicationContext not created yet |
| 3 | contextPrepared(ConfigurableApplicationContext) | Context created, initializers applied, application sources/bean definitions not fully loaded yet |
| 4 | contextLoaded(ConfigurableApplicationContext) | Sources/bean definitions loaded; context not refreshed yet |
| 5 | started(ConfigurableApplicationContext, Duration) | Context refreshed, but ApplicationRunner/CommandLineRunner have not executed yet |
| 6 | ready(ConfigurableApplicationContext, Duration) | Runners finished, application about to exit the successful run(...) branch |

**failed(ConfigurableApplicationContext, Throwable)** is the **error-branch** callback, not a seventh step that always happens after ready. If the error occurs before the context is created, the context parameter may be **null**.

Easy to remember:

~~~text
RunListener is instantiated
       |
       v
starting
       |
environmentPrepared     -- Environment exists
       |
contextPrepared         -- Context created, initializers applied
       |
contextLoaded           -- Sources loaded, not refreshed yet
       |
refresh ApplicationContext
       |
started                 -- Refresh finished
       |
ApplicationRunner / CommandLineRunner
       |
ready                   -- Runners finished, run(...) about to return
~~~

If an error causes startup to fail, callbacks after the failure point generally do not run. **failed(...)** may be called by the failure-handling mechanism, though it must not be treated as a callback guaranteed to catch every error, including errors during **loading or instantiating the RunListener itself**. Where the exception occurs matters: Boot 3.3 retrieves and instantiates RunListeners before the main startup processing enters the failure-catching block of `run(...)`.

**Correlation with Spring Boot events:** RunListener **started(...)** occurs after refresh and before runners, corresponding to the **ApplicationStartedEvent** milestone published by the system. RunListener **ready(...)** occurs after runners, corresponding to **ApplicationReadyEvent**. Do not conclude they are the same object or callbacks from the same interface; EventPublishingRunListener is the internal component translating lifecycle milestones into application events.

## 5. Two kinds of ordering that are easy to confuse

### 5.1. Order of SpringApplication phases

The callbacks **starting → environmentPrepared → contextPrepared → contextLoaded → started → ready** follow lifecycle order. You **cannot** use `@Order` to move **ready(...)** before **contextPrepared(...)** or make `started` run before refresh.

### 5.2. Order across multiple RunListeners

If the classpath contains multiple SpringApplicationRunListeners, **SpringFactoriesLoader** loads them and sorts implementations using **AnnotationAwareOrderComparator**. You can place **@Order(n)** on the class or implement **Ordered**.

Example:

~~~java
@Order(100)
public final class TraceRunListener implements SpringApplicationRunListener {
    // ...
}
~~~

~~~java
@Order(200)
public final class SecondRunListener implements SpringApplicationRunListener {
    // ...
}
~~~

Between **those two listeners**, a lower number means higher priority: listener **100 runs before 200 within the same phase**.

For instance, SpringApplication invokes `starting(...)` for each listener in sorted order before moving the entire chain to `environmentPrepared(...)`. It does not run all six callbacks of TraceRunListener first and then all six callbacks of SecondRunListener.

The `@Order` number of two custom listeners **does not strictly fix** their relative position against all other listeners on the classpath, because Spring Boot and libraries may register their own RunListeners with other priorities. If two listeners have the same order, do not rely on the listing order in the properties file as a durable business contract.

## 6. Runnable example: two RunListeners, one startup runner

Create a Spring Boot 3.3.x Gradle project using **JDK 17+**, the **spring-boot-starter** dependency, and the Spring Boot plugin. The example uses Java 17 and the code below needs no web server.

Directory structure:

~~~text
run-listener-demo/
  build.gradle
  settings.gradle
  src/
    main/
      java/
        example/
          RunListenerDemo.java
          TraceRunListener.java
          SecondRunListener.java
      resources/
        META-INF/
          spring.factories
~~~

### 6.1. Gradle configuration

File **settings.gradle**:

~~~groovy
rootProject.name = 'run-listener-demo'
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Gradle requires a version supported by Spring Boot 3.3 and access to download plugins/dependencies from the internet or a local cache. Use the project's Gradle wrapper if present; the configuration above uses **Spring Boot 3.3.13** to pin the example's version.

### 6.2. Main application

File **src/main/java/example/RunListenerDemo.java**:

~~~java
package example;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RunListenerDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(RunListenerDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("main.afterRun");
        }
    }

    @Bean
    ApplicationRunner demoRunner() {
        return args -> {
            System.out.println("runner");
            if (args.containsOption("demo.fail")) {
                throw new IllegalStateException("demo runner failure");
            }
        };
    }
}
~~~

**Explanation:** `WebApplicationType.NONE` lets the demo exit cleanly without starting an HTTP server. **ApplicationRunner** is a bean and runs only **after** the `started(...)` callback and **before** the `ready(...)` callback. The **--demo.fail** argument is used to trigger an error inside the runner when testing the failure branch. The main code closes the context after **app.run(...)** succeeds.

### 6.3. RunListener observing all major milestones

File **src/main/java/example/TraceRunListener.java**:

~~~java
package example;

import java.time.Duration;

import org.springframework.boot.ConfigurableBootstrapContext;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringApplicationRunListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.ConfigurableEnvironment;

@Order(100)
public final class TraceRunListener implements SpringApplicationRunListener {

    public TraceRunListener(SpringApplication application, String[] args) {
        System.out.println("trace.constructor args=" + args.length);
    }

    @Override
    public void starting(ConfigurableBootstrapContext bootstrapContext) {
        System.out.println("trace.starting");
    }

    @Override
    public void environmentPrepared(
            ConfigurableBootstrapContext bootstrapContext,
            ConfigurableEnvironment environment) {
        System.out.println("trace.environmentPrepared");
    }

    @Override
    public void contextPrepared(ConfigurableApplicationContext context) {
        System.out.println("trace.contextPrepared");
    }

    @Override
    public void contextLoaded(ConfigurableApplicationContext context) {
        System.out.println("trace.contextLoaded");
    }

    @Override
    public void started(
            ConfigurableApplicationContext context, Duration timeTaken) {
        System.out.println("trace.started");
    }

    @Override
    public void ready(
            ConfigurableApplicationContext context, Duration timeTaken) {
        System.out.println("trace.ready");
    }

    @Override
    public void failed(
            ConfigurableApplicationContext context, Throwable exception) {
        System.out.println("trace.failed");
    }
}
~~~

Key points: both **starting** and **environmentPrepared** receive a **ConfigurableBootstrapContext**; `environmentPrepared` also receives **ConfigurableEnvironment**. The two **started/ready** callbacks additionally receive **java.time.Duration**. **failed** receives a `Throwable` and a potentially null context. These are signatures for Spring Boot **3.3.x**; do not copy methods from examples written for very old versions where signatures have changed.

### 6.4. Second RunListener to verify @Order

File **src/main/java/example/SecondRunListener.java**:

~~~java
package example;

import java.time.Duration;

import org.springframework.boot.ConfigurableBootstrapContext;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringApplicationRunListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.annotation.Order;

@Order(200)
public final class SecondRunListener implements SpringApplicationRunListener {

    public SecondRunListener(SpringApplication application, String[] args) {
    }

    @Override
    public void starting(ConfigurableBootstrapContext bootstrapContext) {
        System.out.println("second.starting");
    }

    @Override
    public void ready(
            ConfigurableApplicationContext context, Duration timeTaken) {
        System.out.println("second.ready");
    }
}
~~~

`SecondRunListener` does not override the other milestones because the interface provides empty default methods. The constructor signature must still match. **@Order(100)** and **@Order(200)** produce an observable ordering at the two milestones (`starting`/`ready`) overridden by both listeners.

### 6.5. Registering both listeners

File **src/main/resources/META-INF/spring.factories**:

~~~properties
org.springframework.boot.SpringApplicationRunListener=example.TraceRunListener,example.SecondRunListener
~~~

You must use the exact key above, the exact **example** package, exact casing, and place the file on the classpath. There is no need to add `@Component` to either listener.

### 6.6. Running and comparing order

If the project has a Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If there is no wrapper yet but a compatible Gradle installation is available, you can use **gradle bootRun**.

On a run **without arguments**, the lines **explicitly printed by the example code** appear in this order:

~~~text
trace.constructor args=0
trace.starting
second.starting
trace.environmentPrepared
trace.contextPrepared
trace.contextLoaded
trace.started
runner
trace.ready
second.ready
main.afterRun
~~~

Internal Spring Boot/Gradle logs depending on the environment may interleave between these lines; only messages printed by the example code are listed here.

Observations:

1. The RunListener **constructor** is called before callbacks; it receives `SpringApplication` and the arguments array.
2. At **starting**, `TraceRunListener` with order **100** prints before `SecondRunListener` with order **200**.
3. Milestones **environmentPrepared → contextPrepared → contextLoaded → started** occur before the runner.
4. **runner** prints after `started`, before `ready`.
5. At **ready**, `TraceRunListener` still prints before `SecondRunListener`.
6. **main.afterRun** appears after **SpringApplication.run(args)** returns successfully.

Do not attach significance to which listener the user lists first in `spring.factories` when `@Order` is present: priority is the explicit mechanism that determines order among implementations.

## 7. Testing the failure branch and limits of the failed(...) callback

Re-run the demo with the argument that causes an error in the runner:

~~~bash
./gradlew bootRun --args="--demo.fail"
~~~

Then, milestones **constructor → starting → environmentPrepared → contextPrepared → contextLoaded → started** still appear, followed by the **runner** line. The runner throws an exception, SpringApplication switches to the startup failure path, and `TraceRunListener` may print:

~~~text
trace.failed
~~~

In this example's runner-failure case, **trace.ready**, **second.ready**, and **main.afterRun** will not appear. Spring Boot/Gradle may also log the stack trace and a build-failed message. **failed(context, exception)** must guard against `context == null` when an error occurs before context creation.

For errors occurring right when **SpringFactoriesLoader instantiates the RunListener**, or exceptions thrown in an ultra-early hook like **starting(...)**, do not rely on that same RunListener to catch its own failure. In Spring Boot 3.3's flow, retrieving/instantiating RunListeners and calling `starting` happens before the main try/catch managing startup. Inspect the caller's console/logs and avoid throwing exceptions inside RunListeners unless there is a clear requirement to reject startup.

Do not use a RunListener to open a connection pool or spawn background threads assuming **failed(...) will always be called and release resources**. If a hook must allocate a resource, use try/finally, a clear lifecycle owner, timeouts, and dedicated cleanup.

## 8. How does RunListener differ from nearby extension points?

| Mechanism | Common registration | Main phase | When to use |
| --- | --- | --- | --- |
| SpringApplicationRunListener | META-INF/spring.factories with key org.springframework.boot.SpringApplicationRunListener | Very early; multiple callbacks spanning SpringApplication.run | Infrastructure hooks / observing bootstrap sequence |
| ApplicationListener | app.addListeners(...), @Bean once context is ready, or spring.factories with key ApplicationListener | When Spring events are published | Observing/handling application events |
| ApplicationContextInitializer | app.addInitializers(...) or corresponding factory registration | After context creation, before refresh | Tweaking context before beans are instantiated |
| EnvironmentPostProcessor | Factory registration via spring.factories | Preparing Environment/config | Adding/adjusting property sources early |
| ApplicationRunner | Spring bean | After refresh, before ready | Running initialization tasks that can use DI |
| CommandLineRunner | Spring bean | After refresh, before ready | Startup tasks needing the String[] args array |

If you need a **DataSource**, **Repository**, or another bean for business work, **ApplicationRunner** is usually better because the context is already initialized. If you need to read/adjust configuration before beans are created, evaluate **EnvironmentPostProcessor**. If you only want to receive events, consider **ApplicationListener** instead of implementing a lower-level SPI.

**Ordering of ApplicationRunner/CommandLineRunner** can be controlled with `@Order`/`Ordered` on runner beans; that is a separate ordering system from `SpringApplicationRunListener` order. Even with the lowest numeric order, a runner never runs before the `RunListener.started(...)` milestone in a normal startup flow.

## 9. Common implementation mistakes

**Not called because the file is in the wrong place.** Check the actual path in build output: **META-INF/spring.factories** must be on the classpath. A file under the Java source directory or another `META-INF` folder will not be discovered.

**Wrong key used.** The key must be **org.springframework.boot.SpringApplicationRunListener**, not `ApplicationListener`, the implementation class name, or an arbitrary property.

**Non-public constructor or wrong parameters.** Even if a class implements `SpringApplicationRunListener`, `SpringFactoriesLoader` must instantiate it via the public constructor taking **SpringApplication, String[]**. Do not use a no-args constructor instead.

**Expecting Spring to auto-inject beans into the constructor.** RunListeners are created before the bean container is fully active. Do not put arbitrary repository/service beans in the constructor; switch to a runner or lifecycle hook when DI is needed.

**Using @Component instead of factory registration.** Component scanning does not replace loading RunListeners through `spring.factories`.

**Registering via AutoConfiguration.imports.** That is the auto-configuration registration mechanism, not RunListener registration. Note that Spring Boot 3.x still uses `spring.factories` for several extension SPIs like RunListener.

**Confusing started and ready callbacks.** `started(...)` happens after refresh but **before** runners; `ready(...)` happens after runners finish successfully.

**Confusing @Order ordering with phase ordering.** `@Order` only controls order among listeners at the same invocation point; it does not reorder the startup lifecycle itself.

**Heavy logging or I/O inside callbacks.** Callbacks normally run synchronously on the startup thread and can slow down startup. Avoid network calls without timeouts, unmanaged async work, or unbounded blocking.

**Reading beans in contextPrepared/contextLoaded.** These are pre-refresh phases, so beans are not guaranteed to be created or safe to use. Wait until `started` or a runner when initialized beans are needed.

**Not handling errors inside the listener.** If a listener throws an exception, it can abort startup and mask the underlying cause. For diagnostics/telemetry, log safely and ensure no hard dependency on a failing service.

**Not distinguishing multiple SpringApplications.** With context hierarchies or tests starting multiple times in one JVM, a new RunListener may be created each time; do not assume only one instance or one call per callback across the entire process.

## 10. Verifying results and diagnostics

When a RunListener does not behave as expected, follow this sequence:

1. Confirm the actual **Spring Boot 3.x and Java versions**. If copying code from older versions, verify callback signatures against the matching version's API.
2. Inspect build output or the JAR to confirm **META-INF/spring.factories** was packaged.
3. Verify the key and fully qualified class name in `spring.factories`, especially typos and commas.
4. Confirm the implementation is an accessible class with a **public constructor (SpringApplication, String[])**.
5. Use short log markers in the constructor and **starting(...)** to distinguish **failed to load implementation** from **loaded but callback failed**.
6. If ordering across multiple implementations is unexpected, check **@Order/Ordered** across all RunListeners instead of relying on listing order in properties files.
7. If only **ready(...)** is missing, check whether a startup runner threw an exception or the app failed before ready.
8. If you need to observe ultra-early failures, read the stack trace from the entrypoint; do not assume **failed(...)** is called if instantiating/starting the listener itself failed.

Reliable tests should verify **the order of lines printed by application code**, allowing framework log lines to interleave. In automated tests, replace `System.out` with a thread-safe event collector for testing rather than tying test assertions to internal log formatting.

## 11. Self-check questions

1. **Is annotating a class implementing SpringApplicationRunListener with @Component enough?** No. The implementation must be registered under the right key in META-INF/spring.factories.
2. **What signature must the constructor have?** A public constructor taking **SpringApplication** and **String[]** in that order.
3. **What should you use to run a task needing a Repository bean after Spring finishes initializing?** ApplicationRunner/CommandLineRunner is usually more appropriate.
4. **Between a listener with order 100 and order 200, which is called first at the same callback?** Order 100.
5. **Can a listener with order 1 make ready(...) run before contextLoaded(...)?** No. `@Order` only orders listeners within a phase; it does not alter the startup sequence.
6. **Does RunListener.started(...) mean all runners have completed?** No. Runners are called after `started`, before `ready`.
7. **Does an error in a runner fire ready(...)?** Not along the successful startup path; failure handling handles the error.
8. **Is failed(...) guaranteed to run if the RunListener constructor throws an exception?** No. RunListener instantiation can fail before the main startup error-catching mechanism.
9. **Is it correct to use AutoConfiguration.imports to register a RunListener?** No. RunListeners use the `spring.factories` mechanism.
10. **Why not use a RunListener to open a DataSource via @Autowired in the constructor?** Because RunListeners are created before the Spring context and bean injection are ready.

**Takeaway:** RunListener is a SpringApplication-level SPI that must be loaded via **META-INF/spring.factories** with a **public constructor(SpringApplication, String[])**. Callbacks execute in **startup phase order**; when multiple RunListeners exist, their relative order at each phase is controlled via **@Order/Ordered**, without altering the order of the phases themselves.

### References

- [Spring Boot 3.3 — SpringApplicationRunListener API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationRunListener.html)
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Framework 6.1 — SpringFactoriesLoader API](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/core/io/support/SpringFactoriesLoader.html)
- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
