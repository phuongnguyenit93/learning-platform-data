# ApplicationPreparedEvent: After Loading Bean Definitions and Before Refresh

## 1. What Is ApplicationPreparedEvent?

In Spring Boot, **ApplicationPreparedEvent** is emitted when **the ApplicationContext has been prepared and initial source BeanDefinitions have been loaded**, yet **refresh() has not been executed yet**. It is a milestone in the application startup process, not the milestone where the application is ready to serve requests.

In Spring Boot 3.5, the event class's full name is **org.springframework.boot.context.event.ApplicationPreparedEvent** and it extends **SpringApplicationEvent**. The Javadoc states that at the time of this event, **the Environment is ready for use and the context exists, though it has not been refreshed yet**.

Distinguish three states:

1. **Context created:** the container object exists. Boot can attach the Environment, resource loader, initializers, and bootstrap settings.
2. **BeanDefinitions loaded:** configuration sources and bean metadata have been placed into the registry. This does not mean instances of business beans have been created yet.
3. **Context refreshed:** Spring finishes processing configuration classes, post-processors, and initializing non-lazy singletons; the container enters its active operational state.

**ApplicationPreparedEvent sits between step 2 and step 3.** Keep this meaning in mind when reading startup logs or developing a listener that intervenes before refresh.

## 2. Diagram of Events Around Prepared

~~~text
main(String[] args)
       |
       v
SpringApplication.run(args)
       |
       +--> ApplicationStartingEvent
       |       No Environment yet, no Context yet
       |
       +--> Prepare ConfigurableEnvironment
       |       ApplicationEnvironmentPreparedEvent
       |       Environment exists, Context not created yet
       |
       +--> Create ApplicationContext
       |       Run ApplicationContextInitializer
       |       ApplicationContextInitializedEvent
       |       Context created, primary sources not loaded yet
       |
       +--> Load initial primary sources/BeanDefinitions
       |
       +--> ApplicationPreparedEvent  <--- FOCUS
       |       Context exists, Environment ready
       |       Source definitions loaded
       |       Context NOT refreshed yet
       |
       +--> ApplicationContext.refresh()
       |       ConfigurationClassPostProcessor
       |       BeanDefinitionRegistryPostProcessor
       |       BeanFactoryPostProcessor
       |       BeanPostProcessor, create non-lazy singletons
       |       ContextRefreshedEvent
       |
       +--> ApplicationStartedEvent
       |       LivenessState.CORRECT
       |
       +--> ApplicationRunner / CommandLineRunner
       |
       +--> ApplicationReadyEvent
       |       ReadinessState.ACCEPTING_TRAFFIC
       |
       v
run(args) returns ConfigurableApplicationContext
~~~

The diagram depicts the key milestones of a **successful startup**. It does not list every internal callback. In a web application, **WebServerInitializedEvent** may be emitted during refresh, before ApplicationStartedEvent.

| Event | Context created? | Primary source definitions loaded? | Refreshed? | Runners executed? |
| --- | --- | --- | --- | --- |
| **ApplicationEnvironmentPreparedEvent** | No | No | No | No |
| **ApplicationContextInitializedEvent** | Yes | Not via Boot's source-loading flow yet | No | No |
| **ApplicationPreparedEvent** | **Yes** | **Yes** | **No** | No |
| **ContextRefreshedEvent** | Yes | Yes, and additional metadata processed during refresh | **Yes** | Not necessarily |
| **ApplicationStartedEvent** | Yes | Yes | **Yes** | **No** |
| **ApplicationReadyEvent** | Yes | Yes | Yes | **Completed** |

The crucial difference between **ApplicationContextInitializedEvent** and **ApplicationPreparedEvent** is **the milestone of loading BeanDefinitions from primary sources**. Both are emitted before refresh, but the Prepared event arrives **later**.

## 3. Does "BeanDefinitions Loaded" Mean All Beans Already Exist?

**No.** This is the easiest part of this lesson to misunderstand.

A **BeanDefinition** is metadata instructing Spring how to create a bean: bean class, name, scope, factory method, dependencies, and lifecycle settings. A **bean instance** is the actual Java object created and managed. They are not synonymous:

~~~text
BeanDefinition           Bean instance
--------------           ---------------------------
Describes how to build   Actual created Java object
Name/class/scope         Constructor already invoked
Can exist pre-refresh    Depends on creation phase
No running bean needed   May have run init callbacks
~~~

At ApplicationPreparedEvent, Boot has loaded the **input configuration sources**. For example:

~~~java
SpringApplication app =
        new SpringApplication(DemoApplication.class);
app.run(args);
~~~

**DemoApplication.class** is a primary source. SpringApplication loads this source into the context before emitting the Prepared event.

However, if that class defines:

~~~java
@Bean
GreetingService greetingService() {
    return new GreetingService();
}
~~~

then **the BeanDefinition for greetingService may not appear at Prepared yet**. Why? Because Spring processes **@Configuration** classes, discovers **@Bean** methods, handles **@Import**, **@ComponentScan**, and many auto-configurations inside **ConfigurationClassPostProcessor** during refresh. Those definitions can be registered **after Prepared**.

Therefore, both of the following statements are simultaneously true:

- **Definitions of the primary configuration source are loaded** before ApplicationPreparedEvent.
- **Not all @Bean method and component definitions are processed** until refresh runs.

Do not write a check asserting "total BeanDefinition count equals X" and treat X as a Spring Boot constant. Classpath contents, versions, auto-configuration, bean conditions, and bundled libraries all change the count.

## 4. What Information Does ApplicationPreparedEvent Provide?

Listeners can access the following APIs:

~~~java
ConfigurableApplicationContext context =
        event.getApplicationContext();

SpringApplication application = event.getSpringApplication();
String[] args = event.getArgs();
~~~

This is an **illustrative snippet inside a callback**, requiring an **event** variable and appropriate imports. Meanings:

- **getApplicationContext():** returns the ConfigurableApplicationContext that has been prepared but not refreshed yet.
- **getSpringApplication():** reference to the SpringApplication performing bootstrap.
- **getArgs():** raw arguments for this launch.
- **context.getEnvironment():** the prepared Environment for looking up values and profiles.
- **context.containsBeanDefinition(name):** checks whether a specific definition is in the registry, **without confirming an instance was initialized**.
- **context.isActive():** observes the context's active state; in the normal flow, Prepared occurs before the context becomes active via refresh.

Metadata-only observation example:

~~~java
ConfigurableApplicationContext context =
        event.getApplicationContext();

System.out.println("active=" + context.isActive());
System.out.println("profiles="
        + String.join(",", context.getEnvironment().getActiveProfiles()));
System.out.println("sample definition="
        + context.containsBeanDefinition("sampleService"));
~~~

**Do not call getBean(MyService.class) to trigger business logic here.** When the context is unrefreshed, the registry and BeanPostProcessors are not fully established; forcing service initialization can fail or break lifecycle ordering.

Likewise, having Environment available does not mean every **@ConfigurationProperties bean** has been created and bound. Environment is a data source, whereas configuration-properties beans still belong to the ApplicationContext lifecycle.

## 5. Java 17+ Example: Printing Exact Milestones Before and After Refresh

The example below uses **Spring Boot 3.5.x**, **Java 17+**, and a **non-web** application to avoid web server noise. The example lets you observe:

1. Main begins configuring SpringApplication.
2. ApplicationPreparedEvent fires; the context is not refreshed yet.
3. A business singleton is created and runs its initialization callback during refresh.
4. ContextRefreshedEvent arrives after refresh.
5. ApplicationStartedEvent arrives before the runner.
6. ApplicationReadyEvent arrives after the runner.
7. SpringApplication.run returns to main.

### 5.1. Create the Project

Create a Spring Initializr project with **Maven**, **Java 17 or newer**, **Spring Boot 3.5.x**, package **com.example.demo**, and the **Spring Boot Starter** dependency. Keep the Maven Wrapper generated by Initializr. You do not need the Spring Web dependency because the app selects **WebApplicationType.NONE**.

Create **src/main/java/com/example/demo/PreparedPhaseApplication.java**:

~~~java
package com.example.demo;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;

@SpringBootApplication
public class PreparedPhaseApplication {

    public static void main(String[] args) {
        System.out.println("01 | Configure application");

        SpringApplication application =
                new SpringApplication(PreparedPhaseApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.addListeners(new TimelineListener());

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            System.out.println("09 | run returned; active="
                    + context.isActive());
        }

        System.out.println("10 | context closed");
    }

    @Bean
    SampleService sampleService() {
        return new SampleService();
    }

    @Bean
    ApplicationRunner startupTask(SampleService service) {
        return args -> System.out.println(
                "07 | ApplicationRunner: " + service.message());
    }

    static final class SampleService implements InitializingBean {

        SampleService() {
            System.out.println("03 | SampleService constructor");
        }

        @Override
        public void afterPropertiesSet() {
            System.out.println("04 | SampleService initialized");
        }

        String message() {
            return "hello";
        }
    }

    static final class TimelineListener
            implements ApplicationListener<ApplicationEvent> {

        @Override
        public void onApplicationEvent(ApplicationEvent event) {
            if (event instanceof ApplicationPreparedEvent prepared) {
                ConfigurableApplicationContext context =
                        prepared.getApplicationContext();

                System.out.println(
                        "02 | ApplicationPreparedEvent; active="
                        + context.isActive()
                        + "; sampleDefinition="
                        + context.containsBeanDefinition("sampleService"));
            } else if (event instanceof ContextRefreshedEvent) {
                System.out.println("05 | ContextRefreshedEvent");
            } else if (event instanceof ApplicationStartedEvent) {
                System.out.println("06 | ApplicationStartedEvent");
            } else if (event instanceof ApplicationReadyEvent) {
                System.out.println("08 | ApplicationReadyEvent");
            }
        }
    }
}
~~~

The program has one **@SpringBootApplication**, one **SampleService** bean, one **ApplicationRunner**, and one early-registered listener.

### 5.2. Explaining What Was Observed

- **SpringApplication(PreparedPhaseApplication.class)** designates the main class as a source. Boot loads this source's BeanDefinition before the Prepared event.
- **application.addListeners(new TimelineListener())** registers the listener **before run**; hence the listener receives the early event without waiting for component scan to create a listener bean.
- **ApplicationPreparedEvent** shows the context exists yet is unrefreshed. In the normal demo, **context.isActive()** is false; **sampleDefinition** is false because **@Bean** method metadata has not yet been parsed by ConfigurationClassPostProcessor.
- **SampleService** is instantiated when refresh creates non-lazy singletons. Its constructor and **InitializingBean.afterPropertiesSet()** print logs.
- **ContextRefreshedEvent** appears once refresh completes; **ApplicationStartedEvent** follows, though the runner has not run yet.
- **ApplicationRunner** executes before **ApplicationReadyEvent**.
- After **application.run(args)** returns, the try block prints the active context state, and **try-with-resources** closes the context upon exiting the block.

Closing the context immediately after run is a choice for a **non-web demo**. In a production web server application, do not use try-with-resources like this if you need to serve HTTP continuously.

### 5.3. Running and stdout

From the project directory generated by Spring Initializr:

~~~bash
# Linux / macOS
./mvnw spring-boot:run

# Windows (PowerShell or cmd)
# .\mvnw.cmd spring-boot:run
~~~

The lines **printed by the program itself**, in order under the default demo setup:

~~~text
01 | Configure application
02 | ApplicationPreparedEvent; active=false; sampleDefinition=false
03 | SampleService constructor
04 | SampleService initialized
05 | ContextRefreshedEvent
06 | ApplicationStartedEvent
07 | ApplicationRunner: hello
08 | ApplicationReadyEvent
09 | run returned; active=true
10 | context closed
~~~

Maven and Spring Boot may print additional logging in between; the block above does not represent all stdout. If a project adds listeners/initializers that manually register BeanDefinitions before Prepared, the definition check result can change; the example assumes the initial configuration described above.

**Why is line 02 false while the documentation says BeanDefinitions are loaded?** Because Spring has loaded the **primary source** without necessarily parsing **every @Bean method** of the primary source yet. That is the exact boundary between loading configuration sources and refreshing.

When compiling the project, use the Maven/Gradle Wrapper to supply Spring Boot dependencies. Standalone **javac PreparedPhaseApplication.java** will not work unless the Spring JARs are specified on the classpath.

## 6. Registering Listeners at the Right Time to Receive ApplicationPreparedEvent

### Approach 1 — SpringApplication.addListeners

~~~java
SpringApplication application =
        new SpringApplication(MyApplication.class);
application.addListeners(new MyListener());
application.run(args);
~~~

This snippet illustrates the API; **MyApplication** and **MyListener** must be defined in a real project. This is the clearest option when you control main.

### Approach 2 — SpringApplicationBuilder.listeners

~~~java
new SpringApplicationBuilder(MyApplication.class)
        .listeners(new MyListener())
        .run(args);
~~~

The builder fits when you want fluent startup configuration. The listener is added before **run(args)** begins bootstrapping.

### Approach 3 — Automatic Registration from a Library

For a library to attach a listener to every application that uses it, Spring Boot 3.5 supports the **org.springframework.context.ApplicationListener** key in **META-INF/spring.factories**.

Example **src/main/resources/META-INF/spring.factories**:

~~~properties
org.springframework.context.ApplicationListener=com.example.demo.MyListener
~~~

This is a registration syntax example; **com.example.demo.MyListener** must be implemented with an appropriate constructor. **Do not add this file to the Section 5 demo project unless the class is defined**; the runnable example already uses Approach 1.

**@Component**, **@Bean**, or **@EventListener** inside the container can be too late to receive the Prepared event because the container has not refreshed yet. Do not assume an annotated listener on a business bean will catch startup events emitted before the bean was created.

Also avoid registering the same listener through both **addListeners** and **spring.factories** unless you intentionally want multiple notifications from multiple instances.

## 7. What Can Be Done When ApplicationPreparedEvent Fires?

Appropriate tasks are generally lightweight and clearly bootstrap-oriented:

- **Observe Environment:** inspect active profiles and prepared properties while avoiding logging tokens/passwords.
- **Inspect BeanDefinition metadata:** confirm that a config source or a definition registered by an initializer is present.
- **Measure and mark startup:** record timestamps or counters to analyze context preparation sequences.
- **Intentionally add metadata/definitions:** only when you thoroughly understand BeanDefinitionRegistry and have a framework-level need before refresh.
- **Integrate library extensions:** for example, a library listener that needs to know the context exists and primary sources have been loaded.

Example reading the definition count:

~~~java
ConfigurableApplicationContext context =
        event.getApplicationContext();

String[] names =
        context.getBeanFactory().getBeanDefinitionNames();

System.out.println("Definitions currently loaded=" + names.length);
~~~

This snippet sits inside a listener; it is not a standalone Java file. Do not rely on a fixed number. The result does not prove any beans have been initialized.

### When You Truly Need to Add a BeanDefinition

Some contexts allow programmatic definition registration before refresh via **BeanDefinitionRegistry** or corresponding registration APIs, though this is a container-level extension. You must understand namespaces, names, scopes, and collision risks with definitions created during refresh.

Do not pick the Prepared event just to "work around" regular bean configuration. If you are merely declaring a service, **@Component** or **@Bean** is clearer and far less risky. If you need to modify metadata in bulk while Spring processes configuration classes, **BeanDefinitionRegistryPostProcessor** is usually a better fit.

## 8. What Should You Not Do at the Prepared Event?

### 8.1. Do Not Instantiate Business Beans Manually via getBean

~~~java
DataSource ds =
        event.getApplicationContext().getBean(DataSource.class);
~~~

This is an **anti-example snippet**, assuming **javax.sql.DataSource** is imported. The context has not refreshed yet; BeanFactoryPostProcessors and BeanPostProcessors may not have run, and @Bean definitions from @Configuration classes may not have been generated yet. Thus the code can fail, force premature bean creation, or bypass normal lifecycle steps.

**Do not use a Prepared listener to access databases, send messages, or invoke business services**. Such work belongs in post-refresh hooks or a properly scoped readiness component.

### 8.2. Do Not Call context.refresh() Yourself

**SpringApplication.run(...)** refreshes the context right after the Prepared event. Calling **context.refresh()** inside a listener can disrupt the lifecycle, cause Spring to attempt duplicate startup, or throw errors on contexts that do not support repeated refreshes.

### 8.3. Do Not Perform Long Blocking Tasks

Startup listeners normally run synchronously by default. Calling network APIs without timeouts, scanning large datasets, or sleeping can prolong startup and cause orchestration timeouts. If work is required before application-ready, consider an **ApplicationRunner** with appropriate timeout and failure policies.

### 8.4. Do Not Expect Late Config Changes to Re-run Bootstrap

**Environment** is prepared before Prepared. Settings such as **spring.config.name**, **spring.config.location**, or profiles affecting **ConfigData** may already have been processed prior to the event. Adding properties here **will not cause Spring Boot to re-run ConfigDataEnvironmentPostProcessor or reload files according to the new selection**.

When you need to intervene in configuration before this step, use an **EnvironmentPostProcessor** with appropriate ordering, CLI/environment/system properties, or a suitable ConfigData extension.

### 8.5. Do Not Treat This as a Readiness Signal

**ApplicationPreparedEvent** fires before ContextRefreshedEvent, ApplicationStartedEvent, and runners. The HTTP server may not even exist yet. An instance is marked ready only after Boot's and readiness probes' corresponding conditions, not merely because of the Prepared event.

## 9. Comparing with Neighboring Extension Points and Events

| Hook/event | Timing | Context state | Best suited for |
| --- | --- | --- | --- |
| **EnvironmentPostProcessor** | Environment preparation phase | Refreshed context not needed yet | Adding early PropertySources |
| **ApplicationContextInitializer** | After context creation, before Boot loads sources and before refresh | Context exists, unrefreshed | Initial context configuration |
| **ApplicationContextInitializedEvent** | After initializers, before loading sources | Context exists, sources not loaded | Observing context initialized milestone |
| **ApplicationPreparedEvent** | **After loading source definitions, before refresh** | Context exists, not fully active | Observing/adjusting loaded metadata |
| **BeanDefinitionRegistryPostProcessor** | During refresh, before creating business beans | Registry being processed | Registering/modifying definitions |
| **BeanFactoryPostProcessor** | During refresh | BeanFactory being prepared | Modifying bean metadata |
| **BeanPostProcessor** | Around each bean's initialization | Instance being processed | Callbacks, AOP/proxies, injection support |
| **ContextRefreshedEvent** | After refresh | Context refreshed | Reacting at the context level |
| **ApplicationStartedEvent** | After refresh, before runners | Context refreshed | Tracking Boot started |
| **ApplicationRunner** | After started, before ready | Context active | Startup tasks that must finish before ready |
| **ApplicationReadyEvent** | After runners | Boot signals startup complete | Reacting at the ready milestone |

Two distinctions are especially worth remembering:

**Prepared differs from Initialized:** at initialized, initializers have run, but SpringApplication has not yet loaded primary source definitions. At prepared, sources have been loaded; refresh still lies ahead.

**Prepared differs from Started:** at started, refresh has finished and required non-lazy singletons have generally been created. Prepared is still before refresh and does not guarantee business beans are ready.

## 10. Practical Scenario: Checking a DB Connection at the Right Time

An application needs to verify its DataSource before serving requests. The wrong approach is fetching the DataSource in a Prepared listener, as it may not be initialized yet.

If a project must abort startup when mandatory configuration is invalid, you can use a runner like the following inside a **@Configuration** class:

~~~java
@Bean
ApplicationRunner verifyDatasourceConfiguration(
        Environment environment) {
    return args -> {
        String url =
                environment.getProperty("spring.datasource.url");

        if (url == null || url.isBlank()) {
            throw new IllegalStateException(
                    "Missing spring.datasource.url");
        }
    };
}
~~~

This is a **configuration snippet**, not a standalone file. It requires imports for **ApplicationRunner**, **Bean**, **Environment**, and a project with a corresponding datasource policy. Its purpose is to show that **runners execute after refresh** and can block readiness if they throw an exception. It checks only that **the URL config exists**, not that the DB connection succeeds.

If you need to verify connectivity before readiness, perform an actual check with timeouts, retry/failure policies, and dedicated health/readiness indicators. Do not put unbounded network checks in a Prepared listener.

## 11. Parent/Child Contexts and Running Tests

In a hierarchy built with **SpringApplicationBuilder.parent(...).child(...)**, each context has its own lifecycle. Child context events can propagate to ancestor contexts. A listener attached to a parent may receive multiple events of the same type. When analyzing them, check **event.getApplicationContext()** rather than merely counting events.

In **@SpringBootTest**, Spring Test may cache and reuse the ApplicationContext. Do not assume the Prepared event will re-emit **for every test method**. When you need to test startup ordering, create a dedicated test-managed SpringApplication and attach listeners before run, or use **ApplicationContextRunner** for suitable configuration/auto-configuration tests (which does not necessarily emit the exact same full sequence of SpringApplication events).

If an application-registered listener or initializer has side effects, design it to be idempotent whenever possible and avoid depending on non-guaranteed ordering among listeners with the same priority.

## 12. Common Errors and How to Handle Them

| Symptom / misconception | Cause | Resolution |
| --- | --- | --- |
| Bean listener does not receive ApplicationPreparedEvent | Bean is created after the event | Register from main via addListeners or factories |
| BeanDefinition exists yet getBean fails | Context not refreshed / bean not ready | Wait for post-refresh hooks; avoid getBean in Prepared |
| containsBeanDefinition for a @Bean method returns false | ConfigurationClassPostProcessor has not parsed @Bean yet | Inspect after refresh; distinguish source definitions |
| Thinking Prepared means the app is ready | Event fires before refresh and runners | Use ApplicationReadyEvent / appropriate readiness |
| Seeing context.isActive=false and concluding failure | Context is in the pre-refresh phase | This may be completely expected behavior |
| Environment exists yet @ConfigurationProperties is unbound | Config beans belong to a later lifecycle phase | Read Environment when needed; do not force early bean creation |
| Adding spring.config.location at Prepared does not reload config | ConfigData was loaded earlier | Supply config settings from an earlier source |
| Calling context.refresh in listener causes errors | SpringApplication manages refresh itself | Do not call refresh manually |
| Listener is invoked multiple times | Duplicate registration or multiple contexts | Check registration sources and contexts |
| Startup hangs in listener | Listener does slow I/O or blocking | Reduce work, add timeouts, or move to another hook |
| Bean missing even though on classpath | Auto-configuration condition / @Configuration not processed yet | Inspect Condition Evaluation Report and lifecycle order |
| Opening HTTP port before Prepared finishes | Server cannot be expected to be ready at this milestone | Observe WebServerInitializedEvent / ready / probes |

Spring Boot supports **--debug** to view the Condition Evaluation Report when investigating auto-configuration, though you should not treat the report as proof that beans were already created at Prepared.

## 13. Exercises and Suggested Answers

**Exercise 1.** Sort: ApplicationContextInitializedEvent, ContextRefreshedEvent, ApplicationPreparedEvent, ApplicationStartedEvent, ApplicationReadyEvent.

**Exercise 2.** At the Prepared event, **containsBeanDefinition("sampleService")=false** even though Spring has loaded **DemoApplication.class**. Is there a contradiction?

**Exercise 3.** A listener has **@Component** yet does not see ApplicationPreparedEvent. Why, and how should it be registered?

**Exercise 4.** Can you call a repository in a Prepared listener to check the DB? State the risks.

**Exercise 5.** When adding a PropertySource that affects ConfigData loading, should you wait until the Prepared event?

**Exercise 6.** After the Prepared event, a @Bean bean is created, and then ApplicationRunner throws an exception. Which events occurred, and which event did not occur in this failed startup?

**Short answers:**

1. Initialized → Prepared → ContextRefreshed → Started → Ready (in a successful startup).
2. No. The primary source may be loaded, while @Bean methods are parsed during refresh.
3. Bean listeners are instantiated too late; register via **SpringApplication.addListeners**, builder listeners, or **META-INF/spring.factories**.
4. You should not; the context is not refreshed yet and dependencies/BeanPostProcessors are incomplete.
5. Usually no; intervene before ConfigData or use an appropriate extension.
6. Prepared, ContextRefreshed, and Started may have occurred; the runner error fails startup so **ApplicationReadyEvent is not emitted**.

## 14. Takeaways and Official Documentation

**ApplicationPreparedEvent occurs after SpringApplication loads initial BeanDefinition sources but before refreshing the ApplicationContext.** Both context and Environment exist; **you cannot assume all beans are initialized or that the application is ready**.

Milestone chain to memorize:

~~~text
ApplicationContextInitializedEvent
     -> load primary BeanDefinitions
     -> ApplicationPreparedEvent
     -> refresh() / ContextRefreshedEvent
     -> ApplicationStartedEvent
     -> ApplicationRunner / CommandLineRunner
     -> ApplicationReadyEvent
~~~

Official documentation matching your project version:

1. Spring Boot 3.5 — SpringApplication, Application Events and Listeners section: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
2. Spring Boot 3.5 Javadoc — ApplicationPreparedEvent: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationPreparedEvent.html
3. Spring Boot 3.5 Javadoc — ApplicationContextInitializedEvent: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationContextInitializedEvent.html
4. Spring Framework — Container Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
5. Spring Framework — Java Configuration and @Bean: https://docs.spring.io/spring-framework/reference/core/beans/java/basic-concepts.html

Examples use **Java 17+ / Spring Boot 3.5.x**. With other Spring Boot versions, consult the matching Javadoc, especially regarding bootstrap events, ApplicationContext selection, and listener registration.