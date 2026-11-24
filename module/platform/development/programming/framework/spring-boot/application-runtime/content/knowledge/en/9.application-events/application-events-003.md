# ApplicationEnvironmentPreparedEvent When Environment Is Prepared in Spring Boot

## 1. What Does This Event Signal?

**ApplicationEnvironmentPreparedEvent** is an event during **SpringApplication** startup. Spring Boot emits this event when **the Environment to be used by the application already exists and can be read/modified, while the ApplicationContext has not been created yet**.

This is an early bootstrap milestone, not an event signaling that the application has finished starting. Listener authors can read existing property sources at the time the listener is invoked, inspect certain configuration values, or add a **PropertySource** if truly needed. However, **you must not assume beans have been created**: the context itself does not even exist at this milestone.

In Spring Boot 3.3.x:

- Event class: **org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent**.
- Superclass: **SpringApplicationEvent**.
- **getEnvironment()** returns the **ConfigurableEnvironment** for the current startup run.
- Inherited APIs include **getSpringApplication()** and **getArgs()**.
- **getBootstrapContext()** provides a **ConfigurableBootstrapContext** for advanced bootstrap resource sharing.

**Understanding the word "prepared" properly:** SpringApplication has created and initially configured Environment to emit the event; **several EnvironmentPostProcessors continue adding/transforming property sources during the event dispatch itself**. Therefore, whether a listener sees Config Data contents depends on **listener ordering**. You should not assert that all configuration is complete at the moment event emission *begins*.

This lesson uses **Spring Boot 3.3.x / Spring Framework 6.1, Java 17+**. When moving to another framework branch, verify the corresponding APIs and listener registration mechanisms.

## 2. Position in the Startup Event Sequence

A successful Spring Boot startup has the following general sequence:

~~~text
main() calls SpringApplication.run(...)
    |
    +-- ApplicationStartingEvent
    |
    +-- SpringApplication creates/prepares Environment
    |      |
    |      +-- ApplicationEnvironmentPreparedEvent  <--- THIS LESSON
    |      |      +-- listeners process Environment
    |      |      +-- EnvironmentPostProcessors may run
    |      |      +-- Config Data may be loaded here
    |      |
    |      +-- binds appropriate spring.main.* properties
    |
    +-- Print banner (if enabled)
    +-- Create ApplicationContext
    +-- Apply ApplicationContextInitializer
    +-- ApplicationContextInitializedEvent
    +-- Load bean definitions / sources
    +-- ApplicationPreparedEvent
    |
    +-- ApplicationContext.refresh()
    |      +-- BeanFactoryPostProcessor
    |      +-- BeanPostProcessor
    |      +-- Initialize regular singletons
    |      +-- Web server (if present) initialized/started
    |
    +-- ApplicationStartedEvent
    +-- AvailabilityChangeEvent (LivenessState.CORRECT)
    +-- ApplicationRunner / CommandLineRunner
    +-- ApplicationReadyEvent
    +-- AvailabilityChangeEvent (ReadinessState.ACCEPTING_TRAFFIC)
    +-- SpringApplication.run(...) returns context
~~~

This is a summary diagram and does not list every step inside **SpringApplication.prepareEnvironment**, **refresh**, or Config Data processing. When startup fails, Boot may emit **ApplicationFailedEvent** instead of completing all success milestones.

### 2.1. Comparing with Easily Confused Events

| Event | Context created yet? | Meaning |
| --- | --- | --- |
| **ApplicationStartingEvent** | No | Start of run, before most preparation work |
| **ApplicationEnvironmentPreparedEvent** | **No** | Environment is available for early listeners to read/modify |
| **ApplicationContextInitializedEvent** | Yes, application bean definitions not loaded yet | ApplicationContextInitializers have been invoked |
| **ApplicationPreparedEvent** | Yes, configuration sources/bean definitions loaded, not refreshed yet | About to call refresh |
| **ApplicationStartedEvent** | Yes, refreshed | Before ApplicationRunner/CommandLineRunner |
| **ApplicationReadyEvent** | Yes, runners executed | Application has completed the normal startup sequence |
| **ApplicationFailedEvent** | May or may not exist | Startup failure; depends on which phase failed |

Thus, **EnvironmentPrepared** does not mean **ContextPrepared**, nor does it mean the web server has opened its port or the application is ready to accept traffic.

**Do not use ApplicationEnvironmentPreparedEvent to look up a @Service or @Repository.** At the time this event is dispatched, SpringApplication has not yet created the ApplicationContext to hold those beans.

## 3. What Does Environment Contain and How Can It Be Manipulated?

**Environment** is the abstraction for reading properties by name, checking active profiles, and managing configuration sources. With **ConfigurableEnvironment**, the application can work with:

- **PropertySources**: a collection of sources such as Java system properties, OS environment variables, command-line arguments, and Config Data (once loaded).
- **getProperty("key")**: reads a property value following the precedence order of existing sources.
- **getRequiredProperty("key")**: requires the property to exist; if absent, reading throws an exception.
- **getActiveProfiles()**: inspects profiles currently active in Environment at the time of reading.
- **getPropertySources().addFirst/addLast/addBefore/addAfter(...)**: inserts a property source at an intentional precedence position.

Example of reading and adding a default source inside a listener:

~~~java
ConfigurableEnvironment environment = event.getEnvironment();
String mode = environment.getProperty("demo.mode", "standard");

if (!environment.getPropertySources().contains("demo-defaults")) {
    environment.getPropertySources().addLast(
        new MapPropertySource(
            "demo-defaults",
            Map.of("demo.greeting", "Hello from defaults")));
}
~~~

This is a **snippet inside a callback**, assuming imports for **ConfigurableEnvironment**, **MapPropertySource**, **Map**, and that **event** is an **ApplicationEnvironmentPreparedEvent**. **addLast** places the PropertySource at lower precedence than existing sources: operator configuration can override this fallback.

### 3.1. PropertySources and Precedence Order

**MutablePropertySources** searches sources in order. For the same key, a higher-precedence source normally wins in **Environment.getProperty(...)**:

~~~text
Higher precedence source
    -> "demo.greeting" = "set by CLI"
    -> "demo.greeting" = "set in application.properties"
    -> "demo.greeting" = "fallback" (addLast)
Lower precedence source
~~~

The result is the value from the highest-precedence source containing a matching key, which in the example above is **set by CLI**. Spring Boot has additional precedence rules for different source types and runtime environments; when debugging, inspect the **actual property source** rather than looking only at application.properties.

You should not use **addFirst(...)** to impose defaults, because doing so can accidentally override CLI flags, secrets, or production configuration. **addFirst(...)** is only appropriate when the design truly requires prioritizing a new source above all others and the consequences are understood.

### 3.2. Active Profiles and Config Data

**spring.profiles.active** and profile-specific configurations affect which Config Data sources are loaded. However, calling **getActiveProfiles()** inside a very early listener can occur **before or after** the EnvironmentPostProcessors responsible for Config Data processing.

If a listener needs to observe the final profiles of standard configuration, ensure the listener runs **after** the Config Data processor in the active startup order. If you need to decide *how* Config Data is located and loaded, choose the dedicated Config Data bootstrap mechanism rather than arbitrarily inserting a PropertySource after loading has occurred.

### 3.3. Common APIs on the Event

~~~java
ConfigurableEnvironment env = event.getEnvironment();
SpringApplication application = event.getSpringApplication();
String[] arguments = event.getArgs();
ConfigurableBootstrapContext bootstrap = event.getBootstrapContext();
~~~

**getEnvironment()** is the most frequently used API. **getArgs()** returns arguments passed to SpringApplication; do not log all arguments by default because they may contain sensitive data. **getBootstrapContext()** serves cases where objects must be shared during the bootstrap phase and must adhere to the bootstrap context lifecycle.

**No ApplicationContext is available on this event.** If your problem requires **ConfigurableApplicationContext**, move to **ApplicationContextInitializer** or a later milestone.

## 4. Crucial Detail: The Event Is Emitted While Processors Are Still Running

This is the most frequently misunderstood detail about the name **ApplicationEnvironmentPreparedEvent**.

In Spring Boot 3.3, SpringApplication prepares Environment and then emits the event. Spring Boot also includes **EnvironmentPostProcessorApplicationListener**: this infrastructure listener reacts to the early event and triggers **EnvironmentPostProcessor** implementations registered via **META-INF/spring.factories**.

One critical processor is **ConfigDataEnvironmentPostProcessor**, responsible for **loading and applying Config Data** into Environment: **application.properties**, **application.yaml**, profile-specific configuration, imports, and supported config sources.

Simplified processing flow:

~~~text
SpringApplication.prepareEnvironment(...)
    |
    +-- Create/obtain ConfigurableEnvironment
    +-- Add early sources: arguments, system, env...
    |
    +-- Publish ApplicationEnvironmentPreparedEvent
           |
           +-- EnvironmentPostProcessorApplicationListener
           |      +-- ConfigDataEnvironmentPostProcessor
           |      +-- other EnvironmentPostProcessors
           |
           +-- Application-registered listeners
                  +-- read/modify Environment
    |
    +-- SpringApplication finishes prepareEnvironment(...)
    +-- bind spring.main.* from Environment
    +-- create ApplicationContext in the next step
~~~

**The ordering of the two listener branches in the diagram is not an absolute guarantee for every custom listener.** Spring orders them based on **Ordered/@Order** and related registration mechanisms. If a custom listener runs before **EnvironmentPostProcessorApplicationListener**, it **should not expect** to see values from application.properties. If it runs after that processor in a typical setup, it can read loaded Config Data.

This explains why on the exact same listener class, changing **@Order** or implementing **Ordered** can yield different **getProperty(...)** values.

### 4.1. Choosing Order for a Listener That Wants to Read Config Data

When the goal is to **observe** configuration already loaded by Boot, you can give the listener low precedence, for example:

~~~java
@Override
public int getOrder() {
    return Ordered.LOWEST_PRECEDENCE;
}
~~~

In a standard Boot 3.3 application, this order places the custom listener after the listener that invokes default EnvironmentPostProcessors. Reading **application.properties** in the callback will then produce more reliable results.

However, **LOWEST_PRECEDENCE does not mean "everything in Environment is permanently finalized."** Another listener with the same precedence or running later can still modify Environment; furthermore, SpringApplication continues other steps after event handling finishes.

### 4.2. When Should You Write an EnvironmentPostProcessor Instead of an Event Listener?

If the primary goal is to **add property sources to Environment**, especially when you want explicit ordering relative to **ConfigDataEnvironmentPostProcessor**, consider **EnvironmentPostProcessor**. This interface is directly designed for modifying Environment before refresh and supports **Ordered**.

An **ApplicationEnvironmentPreparedEvent** listener is suitable when you want to **observe the event milestone** or make a small, clear adjustment with predictable ordering. An **EnvironmentPostProcessor** is usually clearer to express when the requirement is **bootstrap configuration processing**.

Do not use a late-running listener and expect it to retroactively change config file loading decisions that already happened earlier.

## 5. Registering the Listener Properly: Must Be Present Before Event Emission

Spring Boot emits **ApplicationEnvironmentPreparedEvent before ApplicationContext exists**, so **you cannot rely on regular bean discovery** to receive the event for that startup run.

### 5.1. Direct Way: SpringApplication.addListeners(...)

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(new MyPreparedEnvironmentListener());
app.run(args);
~~~

In this snippet, **MyApplication** and **MyPreparedEnvironmentListener** are classes already defined in the project. **addListeners(...)** must be called **before run(args)**. This is transparent when you control the **main** method.

You can register via **SpringApplicationBuilder.listeners(...)** if the project uses the builder and context hierarchies.

### 5.2. Automatic Way: META-INF/spring.factories

If you write an integration library whose listener must be loaded regardless of how the application launches SpringApplication, Spring Boot 3.3 supports listener registration via:

**src/main/resources/META-INF/spring.factories**

~~~properties
org.springframework.context.ApplicationListener=\
com.example.runtime.MyPreparedEnvironmentListener
~~~

The listed class must be a valid **ApplicationListener** that Spring Boot can instantiate through its early registration mechanism. Do not expect constructor injection of a **@Service** into this listener, because the context holding beans does not exist yet.

**In the Section 6 sample application, use only addListeners; do not register the same listener simultaneously via spring.factories**, to avoid creating two instances and running duplicate callbacks.

### 5.3. Commonly Misused Approaches

~~~java
@Component
class WrongListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        // Not guaranteed to receive this early bootstrap event!
    }
}
~~~

**@Component** is only scanned and registered when the container processes bean definitions. Similarly, a method annotated with **@EventListener(ApplicationEnvironmentPreparedEvent.class)** on a normal bean is discovered too late to receive an early event that has already fired.

**Rule:** a listener that must receive events **before the context exists** must be registered via **SpringApplication**, **SpringApplicationBuilder**, or the corresponding automatic bootstrap mechanism. Do not turn it into a @Bean/@Component and expect Spring to "replay" past events.

## 6. Complete Java 17+ Example: Reading Config Data and Adding a Fallback

Goals of the example:

1. Register a listener before **run** starts.
2. The listener receives **ApplicationEnvironmentPreparedEvent** and reads **demo.mode** from the configuration file.
3. The listener adds **demo.greeting** in a low-precedence PropertySource if no source with that name exists yet.
4. **ApplicationRunner** reads the results after the context has refreshed.
5. **main** confirms that **run(...)** returned an active context.

Requirements: **Java 17+**, **Spring Boot 3.3.x**, **spring-boot-starter** dependency, and a Gradle/Maven project configured with the Spring Boot plugin. The example does not need an HTTP server.

Create **src/main/java/com/example/runtime/EarlyEnvironmentDemo.java**:

~~~java
package com.example.runtime;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class EarlyEnvironmentDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(EarlyEnvironmentDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        // Must register the listener BEFORE run begins.
        app.addListeners(new PreparedEnvironmentListener());

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN | active=" + context.isActive());
        }
    }

    @Bean
    ApplicationRunner inspectConfiguration(Environment environment) {
        return args -> {
            System.out.println(
                    "RUNNER | mode=" + environment.getProperty("demo.mode"));

            System.out.println(
                    "RUNNER | greeting="
                            + environment.getProperty("demo.greeting"));
        };
    }

    static final class PreparedEnvironmentListener
            implements ApplicationListener<ApplicationEnvironmentPreparedEvent>,
                       Ordered {

        @Override
        public int getOrder() {
            // Read after the default EnvironmentPostProcessors.
            return Ordered.LOWEST_PRECEDENCE;
        }

        @Override
        public void onApplicationEvent(
                ApplicationEnvironmentPreparedEvent event) {

            ConfigurableEnvironment environment = event.getEnvironment();

            System.out.println(
                    "EVENT | mode="
                            + environment.getProperty("demo.mode", "missing"));

            LessonDefaults.register(environment);
        }
    }

    static final class LessonDefaults {

        private static final String NAME = "lesson-defaults";

        static void register(ConfigurableEnvironment environment) {
            if (!environment.getPropertySources().contains(NAME)) {
                environment.getPropertySources().addLast(
                        new MapPropertySource(NAME, Map.of(
                                "demo.greeting", "Hello from early listener")));
            }
        }
    }
}
~~~

**src/main/resources/application.properties**:

~~~properties
demo.mode=from-file
~~~

Run on Linux/macOS from the project directory with Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

**Lines printed by the program itself, in the expected order for the example configuration:**

~~~text
EVENT | mode=from-file
RUNNER | mode=from-file
RUNNER | greeting=Hello from early listener
MAIN | active=true
~~~

Framework or build tool logs may appear between these lines. The example intentionally uses **WebApplicationType.NONE** so no web server needs to start; the context is closed via **try-with-resources** after printing the result.

### 6.1. Why Did EVENT Already See demo.mode from application.properties?

**PreparedEnvironmentListener** returns **Ordered.LOWEST_PRECEDENCE**. In standard Boot 3.3, the infrastructure listener that triggers **ConfigDataEnvironmentPostProcessor** has higher priority, so it has already loaded **application.properties** before our listener reads **demo.mode**.

If you set your listener to **HIGHEST_PRECEDENCE**, the result may differ: the listener may be invoked before Config Data is processed. You should not rely on config file contents without considering order.

### 6.2. Why Not Use @Bean to Register the Listener?

When the event is emitted, the context has not been created yet, so **@Bean PreparedEnvironmentListener** cannot receive this event from the regular bean event listener mechanism. The example creates the listener directly with **new PreparedEnvironmentListener()** and registers it via **app.addListeners(...)** before run.

The listener class does not inject **Environment** in its constructor and does not access service beans: it receives the exact **ConfigurableEnvironment** available from **event.getEnvironment()**.

### 6.3. Why Use addLast Instead of addFirst?

**LessonDefaults.register** adds the **lesson-defaults** source at the end to establish a fallback. If an operator supplies **demo.greeting** from the command line, system property, environment variable, or Config Data in a higher-precedence source, the operator's value is preserved.

Example running with an override:

~~~bash
./gradlew bootRun --args="--demo.greeting=Hello-from-CLI"
~~~

Here, in the sample application, the relevant printed lines will be:

~~~text
EVENT | mode=from-file
RUNNER | mode=from-file
RUNNER | greeting=Hello-from-CLI
MAIN | active=true
~~~

The listener still registers **lesson-defaults**, but **Environment.getProperty("demo.greeting")** selects the value from the higher-precedence argument.

### 6.4. Why Does event Appear Before runner and main?

The listener runs during **prepareEnvironment**, before context creation. **ApplicationRunner** runs only after context refresh succeeds. **main** prints the **MAIN** line after **SpringApplication.run(...)** returns.

Those lines reflect the **actual bootstrap order**, not source file layout or nested class declaration order.

## 7. Unit Testing PropertySources Modification Logic Separately

An early listener should keep its logic small so it can be tested without starting the entire application. In the example, **LessonDefaults.register** operates purely on **ConfigurableEnvironment**, needing no business beans or web server.

With the **spring-boot-starter-test** dependency (JUnit Jupiter and spring-test), create:

**src/test/java/com/example/runtime/LessonDefaultsTest.java**

~~~java
package com.example.runtime;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class LessonDefaultsTest {

    @Test
    void addsFallbackWhenPropertyMissing() {
        MockEnvironment environment = new MockEnvironment();

        EarlyEnvironmentDemo.LessonDefaults.register(environment);

        assertEquals(
                "Hello from early listener",
                environment.getProperty("demo.greeting"));
    }

    @Test
    void neverOverridesHigherPriorityValue() {
        MockEnvironment environment = new MockEnvironment();
        environment.setProperty("demo.greeting", "from-operator");

        EarlyEnvironmentDemo.LessonDefaults.register(environment);

        assertEquals(
                "from-operator",
                environment.getProperty("demo.greeting"));
    }

    @Test
    void repeatedRegistrationKeepsSingleNamedSource() {
        MockEnvironment environment = new MockEnvironment();

        EarlyEnvironmentDemo.LessonDefaults.register(environment);
        EarlyEnvironmentDemo.LessonDefaults.register(environment);

        assertNotNull(
                environment.getPropertySources().get("lesson-defaults"));
        assertEquals(
                "Hello from early listener",
                environment.getProperty("demo.greeting"));
    }
}
~~~

Run tests with the Gradle Wrapper:

~~~bash
./gradlew test
~~~

These tests verify the **fallback value**, **override behavior**, and **no duplicate registration of the same PropertySource name**. They do not prove that SpringApplication emitted the event at the right time: that requires an **integration/startup test** using a real SpringApplication.

**Note:** the nested class **LessonDefaults** is not declared **private**, so tests in the same package can access it. The test needs neither a mocked ApplicationEnvironmentPreparedEvent, nor starting an ApplicationContext, nor opening an HTTP port.

### 7.1. When Should You Test the Real Event?

If you want to verify that the listener truly reads files after Config Data, you can use a small **SpringApplication** with the listener registered, run with **WebApplicationType.NONE**, capture output from the callback, and close the context. Such a test needs to control external property sources so CI machine environment variables do not override expectations.

If the goal is merely to verify the fallback insertion algorithm, the unit test above is faster and more stable. Do not use **@SpringBootTest** for every simple MapPropertySource assignment.

## 8. Distinguishing Event Listeners and EnvironmentPostProcessor

Both can affect Environment, but their design roles differ:

| Criterion | ApplicationListener<ApplicationEnvironmentPreparedEvent> | EnvironmentPostProcessor |
| --- | --- | --- |
| Primary purpose | React to a bootstrap event milestone | Transform/provide Environment configuration |
| How Environment is received | **event.getEnvironment()** | **postProcessEnvironment(environment, application)** |
| Registration | **SpringApplication.addListeners**, builder, or **spring.factories** | **META-INF/spring.factories** |
| Ordering control? | **Ordered/@Order** or listener ordering rules | **Ordered/@Order** |
| Can @Service be injected? | No; no context exists yet | No; use bootstrap APIs and appropriate dependencies |
| Best used when | Observing milestones, selective logging, inspecting or simple configuration additions | Responsibly loading/modifying PropertySources, integrating bootstrap config |

A minimal EnvironmentPostProcessor:

~~~java
package com.example.runtime;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class ExtraDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        if (!environment.getPropertySources().contains("extra-defaults")) {
            environment.getPropertySources().addLast(
                    new MapPropertySource(
                            "extra-defaults",
                            Map.of("demo.extra", "enabled")));
        }
    }
}
~~~

For Boot 3.3 to discover the processor automatically, add to:

**src/main/resources/META-INF/spring.factories**

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.runtime.ExtraDefaultsEnvironmentPostProcessor
~~~

This is an **alternative example to illustrate the EnvironmentPostProcessor mechanism**; it is not a required step for the Section 6 program. If both run, they modify **different keys**. When a processor needs to read already-loaded Config Data, choose an explicit order relative to **ConfigDataEnvironmentPostProcessor** rather than guessing.

**Another difference:** EnvironmentPostProcessor is loaded by Boot via bootstrap machinery and can optionally accept **DeferredLogFactory** or **ConfigurableBootstrapContext** in its constructor per supported APIs. It is not a regular service bean.

## 9. Which Properties Can Be Modified at This Point?

A strength of this event is that it occurs **before SpringApplication creates the context and binds certain launch settings from Environment**. However, **that does not mean every kind of configuration can still be changed safely**.

### 9.1. Application Properties

A properly ordered listener can add a PropertySource containing **demo.mode**, **feature.enabled**, or keys bound by **@ConfigurationProperties**. When beans are created later, these values can be bound normally according to precedence.

The condition is that the setting has not already been consumed irreversibly by earlier bootstrap logic. Use a clearly named fallback with low precedence if you only intend to provide defaults.

### 9.2. spring.main.*

Properties under **spring.main.*** are bound to **SpringApplication** during prepareEnvironment. Therefore, changes introduced into Environment before the binding step can influence startup—for example, **spring.main.banner-mode** or **spring.main.lazy-initialization**.

However, values already **evaluated/read in an earlier step** or configured directly via dedicated APIs need separate consideration. Do not treat EnvironmentPreparedEvent as an arbitrary override mechanism for every SpringApplication decision.

### 9.3. spring.config.* and Profile Selection

Properties such as **spring.config.name**, **spring.config.location**, and **spring.config.additional-location** guide the **discovery and loading of Config Data**. If a listener runs **after** ConfigDataEnvironmentPostProcessor, adding them at that point **will not make Boot re-scan config files from scratch**.

When you need to change where configuration is read from, provide those values from an early-enough source such as **CLI**, **system property**, or **OS environment variable**, or write an intentionally ordered bootstrap extension. This is a key example of the principle that **a value must appear before the moment it is consumed**.

### 9.4. logging.*

Spring Boot also has an infrastructure listener that configures logging very early. Adding **logging.level.*** to Environment **after the logging system has already been initialized** does not automatically re-run full logging setup.

If you need to affect bootstrap logging, inspect listener ordering and Boot's supported logging mechanisms. Do not use a listener at the end of the chain and expect it to act as an early logging configuration source.

## 10. Common Errors and How to Diagnose Them

### 10.1. Using @Component or @EventListener but Callback Never Runs

Cause: the context does not exist yet when the event is emitted. Fix by registering via **SpringApplication.addListeners(...)**, builder listeners, or **spring.factories** before starting run.

### 10.2. Listener Reads application.properties but Gets null

The cause may be that the listener has very high precedence and runs **before** EnvironmentPostProcessorApplicationListener loads Config Data, or the file/property is not loaded under the current profiles/locations. Check order, config sources, and CLI arguments. For observation-only listeners, a late order such as **LOWEST_PRECEDENCE** is usually easier to reason about.

### 10.3. Attempting to Get @Repository with applicationContext.getBean(...)

At the EnvironmentPrepared milestone, **ApplicationContext has not been created yet**, so there is no application context bean to look up. Move bean-dependent work to an **ApplicationRunner**, a regular service, or an appropriate later event.

### 10.4. Adding a PropertySource at the Top and Overriding Production Config

**addFirst** can beat operator-defined sources. If data is only meant as a default, use **addLast**; check for duplicate source names and ensure no unintended side effects occur.

### 10.5. Setting spring.config.location Too Late in a Listener

If Config Data was already processed before the callback, new values will not restart import/file discovery. Place Config Data location properties in early bootstrap sources and verify actual ordering.

### 10.6. Calling Network/Database in the Callback

The event is handled during startup. Slow I/O or unhandled exceptions can delay or fail startup while application beans are not ready yet. Separate genuinely needed bootstrap configuration loading from business tasks; use timeouts/failure policies, or defer work to a later milestone.

### 10.7. Printing the Entire Environment or Command-Line Args for Debugging

PropertySources and args may contain passwords, tokens, or internal details. Log only **safe key names** and redacted values. Do not dump raw environment/args into production logs.

### 10.8. Expecting the Event to Occur Only Once Across the Entire JVM

Each **SpringApplication** run can emit its corresponding event. Multi-context applications, tests that recreate contexts, or multiple SpringApplications in the same process can trigger the listener multiple times. Side effects need unique source names, idempotency checks, and **per-run** lifecycle management rather than arbitrary static global variables.

### 10.9. Listener Throws an Exception and You Still Expect ApplicationReadyEvent

An exception in an early callback can cause startup to fail; Spring Boot may emit **ApplicationFailedEvent**. There is no guarantee the context gets created, runners execute, or ready appears after an error. Only fail startup if it is truly a mandatory condition; for non-essential observation tasks, handle errors according to an appropriate policy.

### 10.10. Using @Order but Results Still Differ from Expectations

The listener ecosystem includes both Boot infrastructure listeners and library listeners. Determine the **Order** of relevant listeners (especially Config Data and logging processors), registration points, and whether another listener modifies the same key afterward. Practical debugging prints the **PropertySource name** and the value of **one permitted key**, rather than relying on the assumption that "prepared means everything is frozen."

## 11. Quality Checklist for Designing an Early Listener

Before adding the listener to a project, verify:

- [ ] The listener is registered **before SpringApplication.run(...)**.
- [ ] It has no dependency on **ApplicationContext/@Service/@Repository** at event time.
- [ ] It processes only configuration keys that are genuinely relevant and readable in this phase.
- [ ] Its order relative to **EnvironmentPostProcessorApplicationListener** is defined if Config Data is needed.
- [ ] Default sources use low precedence and do not override operator settings.
- [ ] You do not expect late **spring.config.*** changes to re-run Config Data loading.
- [ ] You do not assume **logging.*** changes after the logging listener take retroactive effect.
- [ ] Measures prevent duplicate PropertySource registration or repeated side effects.
- [ ] The callback is fast, free of heavy business I/O, and does not log sensitive data.
- [ ] PropertySource manipulation logic has standalone unit tests.
- [ ] If actual event ordering needs testing, a startup test uses a real **SpringApplication**.
- [ ] You distinguish **EnvironmentPrepared**, **ApplicationPrepared**, **Started**, and **Ready**.

## 12. Self-Check Questions

**Question 1.** Is ApplicationEnvironmentPreparedEvent sent before or after Spring creates the ApplicationContext?

**Answer:** **Before**. Environment is available to read/modify, while ApplicationContext has not been created yet.

**Question 2.** Is a listener declared with @Component guaranteed to receive this event on the first SpringApplication.run?

**Answer:** **No**. Beans are created/discovered after this milestone. Listeners for early events must be registered before run or via an appropriate bootstrap mechanism.

**Question 3.** Why can two listeners handling ApplicationEnvironmentPreparedEvent read different PropertySources?

**Answer:** Because listeners have ordering. **EnvironmentPostProcessorApplicationListener** can load Config Data while the event is being dispatched; a listener running before it and one running after it will see different Environment states.

**Question 4.** In the example, if **--demo.greeting=Hello-from-CLI** is added, is the fallback value still the one read?

**Answer:** No. The fallback was added with **addLast**, while the CLI value lives in a higher-precedence source, so the runner reads **Hello-from-CLI**.

**Question 5.** Can you put **spring.config.location** in a listener running after ConfigDataEnvironmentPostProcessor and expect Boot to immediately search for extra files?

**Answer:** No. There is no automatic mechanism to re-run the entire Config Data discovery/loading process just because a listener added a key late.

**Question 6.** Does this event guarantee that all beans have been injected, all runners have executed, and the HTTP server is ready?

**Answer:** No. This is a bootstrap event before context creation; refresh, runners, and readiness still lie ahead.

**Question 7.** When implementing a custom configuration loader, why should you consider EnvironmentPostProcessor?

**Answer:** Because it has a dedicated contract to modify Environment before refresh, supports registration via spring.factories, and allows controlling processing order when needed.

**Question 8.** Should a configuration-observing listener call **getBean(MyService.class)** to fetch the application name from a database?

**Answer:** No. Business beans do not exist at this milestone. If a database and DI services are needed, use a later callback or a dedicated bootstrap loading architecture.

## 13. Summary and Official Documentation

**ApplicationEnvironmentPreparedEvent** is an early signal indicating that **Environment can be read and adjusted before ApplicationContext is created**. It sits between **ApplicationStartingEvent** and **ApplicationContextInitializedEvent**. Environment itself can continue to be enriched by EnvironmentPostProcessors and other listeners **during the same event dispatch pass**; therefore **listener ordering** is essential to understand.

A lifecycle-correct listener is registered **before run**, has no dependency on application beans, adds a PropertySource only when needed, and controls precedence. If the goal is specialized bootstrap configuration loading, **EnvironmentPostProcessor** is usually a better extension point. Configuration already consumed in an earlier phase is not reprocessed automatically just because Environment is modified later.

Official documentation for Spring Boot 3.3:

- **ApplicationEnvironmentPreparedEvent API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationEnvironmentPreparedEvent.html
- **Application events and listeners:** https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- **EnvironmentPostProcessorApplicationListener API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessorApplicationListener.html
- **ConfigDataEnvironmentPostProcessor API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataEnvironmentPostProcessor.html
- **EnvironmentPostProcessor API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
- **Externalized Configuration:** https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html