# Learning sequence for auto-configuration: from observing beans to writing and verifying a library

## Learning objectives and approach

An effective way to learn **Spring Boot auto-configuration** is to progress from **observing running behavior** to **explaining root causes**, and only then to **building** and **verifying** your own. If you start immediately by copying an **@AutoConfiguration** class, you may manage to create a bean without understanding why it appears, when it disappears, why user configuration takes precedence, or whether another application will automatically discover the library.

This workshop guides learners through six stages:

1. **Observe:** run a small Boot application and list infrastructure beans and application beans.
2. **Explain:** read condition evaluations, distinguishing component scanning, auto-configuration imports, and dependencies on the classpath.
3. **Design:** define a library's API, properties, conditions, and back-off policy.
4. **Implement:** package an **@AutoConfiguration** class and declare **AutoConfiguration.imports** properly.
5. **Isolated testing:** use **ApplicationContextRunner** to verify defaults, binding, toggling on/off, and custom beans.
6. **Integration verification:** consume the library in an independent application, inspecting actual beans, responses, and JAR contents.

After this lesson, learners can answer with **runnable evidence**: "Where did this bean come from?", "Which condition enables/disables it?", "Can an application replace the default?", and "If another application only adds the dependency, does Boot automatically discover the library's configuration?".

**Example context:** Java 21, Gradle 8.x, and Spring Boot 3.3.x. We build a **greeter-autoconfigure** library providing a default **Greeter** object, a **demo-app** application using that object, and JUnit 5 tests. The name "Greeter" is a small feature chosen to focus on mechanics, not assumed to be a general production configuration solution.

## Stage 1 — Observe real beans in a Boot application

### 1.1. Distinguish bean origins

In a Spring application, beans can come from multiple sources:

- A class discovered by component scanning, such as **@Component** or **@RestController** inside a scanned package.
- A **@Bean** method declared by the application.
- A **@Bean** method or configuration imported from a library, including auto-configuration.
- Other Spring bean registration mechanisms, such as certain BeanDefinitionRegistryPostProcessor implementations.

You cannot look at "a bean exists" and immediately conclude "that bean was created by auto-configuration". You must observe **bean name, bean type, definition source, and the condition report**.

### 1.2. Practice observing Servlet infrastructure first

Create a Boot application with **spring-boot-starter-web** and a **@SpringBootApplication** class. Inside this class, add the following snippet to observe the **DispatcherServlet** bean; this snippet is **part of the configuration class**, not a standalone Java file:

~~~java
@Bean
ApplicationRunner inspectServlet(ApplicationContext context) {
    return args -> {
        String[] names =
            context.getBeanNamesForType(DispatcherServlet.class);
        Arrays.sort(names);
        System.out.println(
            "DispatcherServlet beans: " + Arrays.toString(names));
    };
}
~~~

Required imports:

~~~java
import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.web.servlet.DispatcherServlet;
~~~

In a standard Spring Boot MVC application with the web starter and no other DispatcherServlet registered, the expected printed line is:

~~~text
DispatcherServlet beans: [dispatcherServlet]
~~~

This indicates the MVC infrastructure bean has appeared. It is **not yet enough to prove the bean's source**, so we continue inspecting the condition report in the next stage. If the application declares another servlet itself or has custom configuration, the actual list may differ.

### 1.3. Capture an "observation baseline" before intervening

Record in your study notes:

| Question | Evidence to collect |
| --- | --- |
| Which beans exist? | Bean names and types retrieved from ApplicationContext. |
| Did Spring create the bean exactly once as expected? | Bean count by specific type and name. |
| Was the bean written by the user or imported by configuration? | Bean definition source or condition report. |
| Does changing a dependency/property alter the outcome? | Results before and after changing one variable. |

The goal of stage 1 is to build the habit of **observing the running context** instead of guessing from starter names.

## Stage 2 — Read conditions and form hypotheses

### 2.1. Read the Condition Evaluation Report

Spring Boot auto-configures via auto-configuration classes imported into the application, then evaluates conditions such as:

| Annotation | Question the system needs to answer |
| --- | --- |
| **@ConditionalOnClass** | Is the required class on the classpath? |
| **@ConditionalOnBean** | Is the prerequisite bean available? |
| **@ConditionalOnMissingBean** | Has no matching bean been provided by the application or another configuration? |
| **@ConditionalOnProperty** | Does the property have a matching value? |
| **@ConditionalOnWebApplication** | Is this the right web application type? |

Enable debug on the Boot application:

~~~bash
gradle :demo-app:bootRun --args='--debug'
~~~

If using Gradle Wrapper:

~~~bash
./gradlew :demo-app:bootRun --args='--debug'
~~~

In Windows PowerShell you can use **.\gradlew.bat** instead of **./gradlew**. When running a real application, debug can display the **Condition Evaluation Report**, including satisfied items, unsatisfied items, and excluded configurations. Find the condition group related to **DispatcherServlet** or Web MVC, and note **which conditions matched**. Class names and report contents depend on the Spring Boot version, so do not infer report entry names from theory alone.

**Observations to distinguish:**

- **spring-boot-starter-web** brings the required dependencies into the project.
- **Component scanning** finds components written by the application inside scanned packages.
- **Auto-configuration** inspects candidate configuration classes and applies them only when conditions match.
- **@SpringBootApplication** includes the auto-configuration trigger mechanism, but does not mean every auto-configuration class is applied.

### 2.2. Experiment with "changing one condition"

Before writing a library, perform two small experiments:

1. View the dependency tree and identify MVC/Jackson/Tomcat components bundled with the web starter, for example using **gradle :demo-app:dependencies --configuration runtimeClasspath**.
2. Change a simple property, such as **server.port**, then observe the server starting on the new port. When investigating a missing bean, prioritize checking actual conditions instead of repeatedly adding **@Bean** by guesswork.

Do not remove dependencies arbitrarily just to induce hard-to-control errors. The goal is to learn the link **conditions → active configuration → observable beans/behavior**.

### 2.3. Completion criteria for stage 2

Learners can explain why "having a dependency" does not mean "guaranteed to have a bean", and know how to locate the condition report to determine why an auto-configuration did or did not take effect.

## Stage 3 — Design a small auto-configuration library

We want the library to create a **Greeter** bean with the behavior:

~~~text
Greeter.greet("Ada") → "Hello, Ada!"
~~~

The application can adjust the prefix:

~~~yaml
demo:
  greeting:
    prefix: "Xin chào"
~~~

to obtain:

~~~text
Greeter.greet("Ada") → "Xin chào, Ada!"
~~~

Design rules:

1. When the application has the library and has not declared a **Greeter**, auto-configuration creates **one default Greeter bean**.
2. **demo.greeting.prefix** defaults to **Hello** and can be overridden via external configuration.
3. **demo.greeting.enabled=false** disables the default bean created by the library; when undeclared, the feature is enabled by default.
4. When the user already has their own **Greeter**, the library **backs off** instead of trying to create a second bean.
5. The library must be **automatically discovered from its JAR** by another application without adding **@Import** or scanning internal library packages.

The corresponding verification suite will cover: default bean, property binding, backing off for a custom bean, disabling via property, discovery from JAR, and calling a real endpoint.

### 3.1. When should this library use auto-configuration?

Auto-configuration is appropriate when a **reusable library** wants to configure infrastructure or utility beans automatically with defaults based on dependencies and environment. If a bean is dedicated to only a single application, **@Configuration** and **@Bean** inside the application itself can be simpler and clearer.

In this example, Greeter is a simple bean to create a measurable experiment; the real value of the lesson lies in **registration, conditions, overriding, and testing workflows**.

## Stage 4 — Build a multi-module Gradle project and library

All code in this section forms a **runnable standalone project example**, requiring no code from other lessons.

### 4.1. Final structure

~~~text
auto-config-workshop/
├── settings.gradle
├── build.gradle
├── greeter-autoconfigure/
│   ├── build.gradle
│   ├── src/main/java/com/example/greeter/
│   │   └── Greeter.java
│   ├── src/main/java/com/example/greeter/autoconfigure/
│   │   ├── GreetingProperties.java
│   │   └── GreetingAutoConfiguration.java
│   ├── src/main/resources/META-INF/spring/
│   │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│   └── src/test/java/com/example/greeter/autoconfigure/
│       └── GreetingAutoConfigurationTests.java
└── demo-app/
    ├── build.gradle
    ├── src/main/java/com/example/demo/
    │   ├── DemoApplication.java
    │   └── GreetingController.java
    └── src/main/resources/application.yml
~~~

File **settings.gradle**:

~~~groovy
rootProject.name = 'auto-config-workshop'
include 'greeter-autoconfigure', 'demo-app'
~~~

Root **build.gradle** file:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}

subprojects {
    apply plugin: 'java'
    apply plugin: 'io.spring.dependency-management'

    group = 'com.example'
    version = '1.0.0'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

    repositories {
        mavenCentral()
    }

    dependencyManagement {
        imports {
            mavenBom 'org.springframework.boot:spring-boot-dependencies:3.3.13'
        }
    }

    tasks.withType(Test).configureEach {
        useJUnitPlatform()
    }
}
~~~

**Explanation:** Root uses Spring Boot's BOM so modules manage library versions consistently. The Java toolchain uses JDK 21. We **do not apply the Boot plugin to the library module**, because a library needs a regular JAR, not an executable bootJar. The Boot plugin is applied only to the consuming application.

File **greeter-autoconfigure/build.gradle**:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

**Explanation:** The library uses Spring Boot annotations and APIs to build auto-configuration; the configuration processor supplies property metadata at packaging time. Test dependencies include JUnit 5, AssertJ, and the **ApplicationContextRunner** helper class. The library does not need a web starter or HTTP server to test its own beans.

File **demo-app/build.gradle**:

~~~groovy
plugins {
    id 'org.springframework.boot'
}

dependencies {
    implementation project(':greeter-autoconfigure')
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Here the consuming application only adds **a dependency on the library**, besides the web starter for REST. There is no **@Import(GreetingAutoConfiguration.class)** and no component scan declaration targeting the library's package.

### 4.2. Write the library's public data type

File **greeter-autoconfigure/src/main/java/com/example/greeter/Greeter.java**:

~~~java
package com.example.greeter;

import java.util.Objects;

public record Greeter(String prefix) {

    public Greeter {
        Objects.requireNonNull(prefix, "prefix");
    }

    public String greet(String name) {
        return prefix + ", " + name + "!";
    }
}
~~~

This is a valid Java record on Java 21. The constructor disallows **prefix=null**; the greeting format stays fixed so tests can assert concrete outputs.

### 4.3. Define configuration properties

File **greeter-autoconfigure/src/main/java/com/example/greeter/autoconfigure/GreetingProperties.java**:

~~~java
package com.example.greeter.autoconfigure;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.greeting")
public class GreetingProperties {

    private String prefix = "Hello";

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
~~~

**@ConfigurationProperties** binds **demo.greeting.prefix** to the object. The default value **Hello** is used when the user has not set a prefix. In this example we use JavaBean getter/setter methods so the binding mechanism is easy to observe.

Do not place **@Component** on GreetingProperties: this object will be registered intentionally by the auto-configuration class via **@EnableConfigurationProperties**, independent of the application's component scan.

### 4.4. Write the auto-configuration class

File **greeter-autoconfigure/src/main/java/com/example/greeter/autoconfigure/GreetingAutoConfiguration.java**:

~~~java
package com.example.greeter.autoconfigure;

import com.example.greeter.Greeter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(GreetingProperties.class)
@ConditionalOnProperty(
    prefix = "demo.greeting",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Greeter.class)
    public Greeter greeter(GreetingProperties properties) {
        return new Greeter(properties.getPrefix());
    }
}
~~~

The policy here can be read in order:

1. **@AutoConfiguration** denotes a candidate configuration for the auto-configuration mechanism.
2. **@EnableConfigurationProperties** registers the properties class when the configuration is applied.
3. **@ConditionalOnProperty** enables the configuration when **enabled=true** or the property is absent; if **enabled=false**, this configuration does not apply.
4. **@ConditionalOnMissingBean(Greeter.class)** avoids registering the default Greeter bean when the context already has a user-provided Greeter.
5. The **greeter(...)** method reads the prefix from configuration properties and creates the default object.

**Important:** **@AutoConfiguration** characterizes the class. For Boot to find the class from an external JAR, its class name must be registered in the imports resource in the next step.

In a larger library, you can add classpath conditions like **@ConditionalOnClass** when the library depends on an optional API. In this example **Greeter** is always packaged in the same JAR, so adding **@ConditionalOnClass(Greeter.class)** would only be a redundant condition and might mislead learners about the mechanism.

### 4.5. Register discovery via AutoConfiguration.imports

Create the exact file:

~~~text
greeter-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Content: **one line with the full class name**:

~~~text
com.example.greeter.autoconfigure.GreetingAutoConfiguration
~~~

Spring Boot 3.x reads auto-configuration names in this file from JARs on the classpath. Consequently, a consuming application can activate the configuration via a **dependency**, without scanning the **com.example.greeter.autoconfigure** package.

If you forget the imports file, **ApplicationContextRunner** tests with explicit auto-configuration will still pass, yet **the consuming application will not automatically discover the configuration**. That is why both verification layers are needed: condition tests in stage 5 and real discovery tests in stage 6.

### 4.6. What the library needs to package

The library JAR must contain at least:

- Public class **com.example.greeter.Greeter**.
- Classes **GreetingProperties** and **GreetingAutoConfiguration**.
- Resource **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**.
- Property metadata generated by the annotation processor, if the processor is enabled and runs successfully.

Do not use **@ComponentScan** inside an auto-configuration class just to find all of the library's beans; define/import required beans intentionally. The auto-configuration package should also be kept separate from the consuming application's package to easily prove discovery actually goes through imports.

## Stage 5 — Verify conditions with ApplicationContextRunner

### 5.1. Why test with a small context?

**ApplicationContextRunner** builds a **minimal ApplicationContext** and runs the auto-configuration under test. It is well suited for testing conditions because there is no need to start an entire web server. Tests can customize properties, user beans, and candidate configurations, then assert bean counts and behavior.

Limitation to remember: calling **AutoConfigurations.of(GreetingAutoConfiguration.class)** in a test **explicitly specifies** the configuration under test. It tests configuration logic **but does not prove that AutoConfiguration.imports was packaged properly**. Discovery must be verified separately in stage 6.

### 5.2. Write all four essential tests

File **greeter-autoconfigure/src/test/java/com/example/greeter/autoconfigure/GreetingAutoConfigurationTests.java**:

~~~java
package com.example.greeter.autoconfigure;

import com.example.greeter.Greeter;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(GreetingAutoConfiguration.class));

    @Test
    void createsDefaultGreeter() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(Greeter.class);
            assertThat(context.getBean(Greeter.class).greet("Ada"))
                .isEqualTo("Hello, Ada!");
        });
    }

    @Test
    void bindsCustomPrefix() {
        runner.withPropertyValues(
            "demo.greeting.prefix=Xin chào"
        ).run(context -> {
            assertThat(context).hasSingleBean(Greeter.class);
            assertThat(context.getBean(Greeter.class).greet("Ada"))
                .isEqualTo("Xin chào, Ada!");
        });
    }

    @Test
    void backsOffWhenApplicationProvidesGreeter() {
        runner.withUserConfiguration(UserGreeterConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(Greeter.class);
                assertThat(context.getBean(Greeter.class).greet("Ada"))
                    .isEqualTo("Custom, Ada!");
            });
    }

    @Test
    void doesNotCreateGreeterWhenDisabled() {
        runner.withPropertyValues(
            "demo.greeting.enabled=false"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(Greeter.class);
        });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGreeterConfiguration {

        @Bean
        Greeter customGreeter() {
            return new Greeter("Custom");
        }
    }
}
~~~

### 5.3. Run tests and interpret evidence

From the project root directory:

~~~bash
gradle :greeter-autoconfigure:test
~~~

When Gradle Wrapper is installed for the project, you can use **./gradlew :greeter-autoconfigure:test**. On a successful build, Gradle reports the test task succeeded; console output depends on Gradle options and test logging, so **do not fabricate a fixed stdout transcript**.

Read the four tests as four controlled scenarios:

| Case | Action | Verifiable conclusion |
| --- | --- | --- |
| Default | Pass no property or custom bean | Context has one Greeter, returning **Hello, Ada!**. |
| Change config | Pass **demo.greeting.prefix=Xin chào** | Greeter returns **Xin chào, Ada!**. |
| User provides bean | Add **UserGreeterConfiguration** class | Only one Greeter; the user's object is used. |
| Disable feature | Pass **demo.greeting.enabled=false** | No Greeter created by auto-configuration. |

For the customization case, what is proven is **the bean set contains only the one Greeter provided by the user**. This is concrete evidence for the library's **@ConditionalOnMissingBean**. For the disabled case, the test requires no controller using Greeter, so the context can run validly even though the bean does not exist.

### 5.4. Expanding tests as the library grows

For a real library, you may also need:

- **@ConditionalOnClass**: run tests in a classloader filtering out the optional class to prove no bean is created when the dependency is absent.
- **@ConditionalOnBean**: create or omit the prerequisite bean and verify the corresponding branch.
- **@ConditionalOnWebApplication**: use the appropriate runner for Servlet/Reactive/non-web contexts, rather than any arbitrary context type.
- **Auto-configuration ordering**: use **before/after** when multiple auto-configurations genuinely depend on order.
- **Failure diagnostics**: verify that invalid user configuration reports a helpful error instead of swallowing errors or silently creating another bean.

Add conditions only when specifically required; do not pile on annotations just to "look like a starter". Every condition must have a reason and a matching test.

## Stage 6 — Run a consuming application to prove discovery from the JAR

### 6.1. Write an application independent of the auto-configuration package

File **demo-app/src/main/java/com/example/demo/DemoApplication.java**:

~~~java
package com.example.demo;

import com.example.greeter.Greeter;
import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.web.servlet.DispatcherServlet;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectBeans(ApplicationContext context) {
        return args -> {
            String[] servletNames =
                context.getBeanNamesForType(DispatcherServlet.class);
            String[] greeterNames =
                context.getBeanNamesForType(Greeter.class);

            Arrays.sort(servletNames);
            Arrays.sort(greeterNames);

            System.out.println("DispatcherServlet beans: "
                + Arrays.toString(servletNames));
            System.out.println("Greeter beans: "
                + Arrays.toString(greeterNames));
        };
    }
}
~~~

File **demo-app/src/main/java/com/example/demo/GreetingController.java**:

~~~java
package com.example.demo;

import com.example.greeter.Greeter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final Greeter greeter;

    public GreetingController(Greeter greeter) {
        this.greeter = greeter;
    }

    @GetMapping("/greet")
    public String greet(
        @RequestParam(defaultValue = "Ada") String name
    ) {
        return greeter.greet(name);
    }
}
~~~

File **demo-app/src/main/resources/application.yml**:

~~~yaml
demo:
  greeting:
    prefix: "Xin chào"
~~~

**Key point:** The application package is **com.example.demo**, while the auto-configuration is in **com.example.greeter.autoconfigure**. Default component scanning from **DemoApplication** does not scan external packages. If Greeter appears in the context, it was wired via the library's declared mechanism—specifically the **AutoConfiguration.imports** resource and Spring Boot conditions—not by accidental component scan.

### 6.2. Run and observe

From root:

~~~bash
gradle :demo-app:bootRun
~~~

When the application starts successfully with default configuration, the two bean-inspection lines have the expected content:

~~~text
DispatcherServlet beans: [dispatcherServlet]
Greeter beans: [greeter]
~~~

These two lines are **printed by ApplicationRunner**; they may appear interspersed with other log lines. The bean names in the example come from the **dispatcherServlet** method name in Boot's configuration and **greeter** in the library; applications with customizations may yield different results.

Call the endpoint in a second terminal:

~~~bash
curl -s "http://localhost:8080/greet?name=Ada"
~~~

Expected response body:

~~~text
Xin chào, Ada!
~~~

**This is the HTTP body**, not the entire stdout of bootRun or curl in all environments. The Vietnamese-accented greeting is returned from the **demo.greeting.prefix** value in application.yml. If the server changed port or port 8080 is occupied, use the configured port when calling the API.

### 6.3. Verify the JAR contains the auto-configuration declaration

Package the library with the **jar** task, without bootJar:

~~~bash
gradle :greeter-autoconfigure:jar
~~~

Inspect the entry list:

~~~bash
jar tf greeter-autoconfigure/build/libs/greeter-autoconfigure-1.0.0.jar
~~~

The list must include the paths:

~~~text
com/example/greeter/Greeter.class
com/example/greeter/autoconfigure/GreetingAutoConfiguration.class
com/example/greeter/autoconfigure/GreetingProperties.class
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

**Why check this:** **ApplicationContextRunner** tests pass the configuration class directly and therefore still pass if the imports declaration is forgotten. Seeing the exact file inside the JAR combined with a consuming application running automatically provides stronger evidence for the real path **JAR on classpath → Boot discovery → condition → bean → API**.

### 6.4. Demonstrate the back-off mechanism in the consuming application

After observing the default output, add **demo-app/src/main/java/com/example/demo/CustomGreeterConfiguration.java**:

~~~java
package com.example.demo;

import com.example.greeter.Greeter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomGreeterConfiguration {

    @Bean
    public Greeter customGreeter() {
        return new Greeter("Custom");
    }
}
~~~

Restart the application. Expected observed output:

~~~text
Greeter beans: [customGreeter]
~~~

Endpoint returns:

~~~text
Custom, Ada!
~~~

This means the user-declared **customGreeter** bean is registered, while the auto-configuration's **greeter** method does not create the default bean when **@ConditionalOnMissingBean(Greeter.class)** is not satisfied. Thus the application retains the right to alter behavior without modifying library code.

If you keep this custom class and then set **demo.greeting.enabled=false**, the endpoint can still run because **customGreeter** is supplied by the user; the property only disables the library's default configuration. To test the "no Greeter" case, test it with **ApplicationContextRunner** or decouple the controller from a mandatory dependency, avoiding confusion between a startup failure caused by the controller needing Greeter and an auto-configuration error.

### 6.5. Distinguish the verification layers

| Layer | Tool | What is confirmed | Limitation |
| --- | --- | --- | --- |
| Code inspection | Read annotations, properties, classes | Intended logic and defaults | Unknown how runtime executes it. |
| Isolated context test | ApplicationContextRunner | Bean created/skipped properly by conditions | Explicit import does not itself test the imports file. |
| Artifact inspection | jar tf | Classes and resources are packaged | Does not prove runtime applies configuration. |
| Consuming app test | bootRun + bean inspection | Boot actually discovers and registers the bean | Covers only one specific environment and classpath. |
| Behavior test | curl + changing property/bean | Output changes properly when user customizes | Additional application tests needed for production scenarios. |

A feature is only considered **verified** when there is appropriate evidence from the layers it affects. Relying solely on a test that directly imports the class can miss packaging bugs. Simply seeing an endpoint run does not guarantee the disabled and back-off branches were thoroughly tested.

## How to read results when an experiment fails

### Case A: Context test passes yet demo-app lacks Greeter

Check sequentially:

1. Does **demo-app** have a dependency on **greeter-autoconfigure** on runtimeClasspath?
2. Does the library JAR contain the exact **AutoConfiguration.imports** file?
3. Does the file contain the exact fully qualified class name without package/spelling mistakes?
4. Did an auto-configuration exclusion, disabled profile/property, or existing bean alter the outcome?
5. Does the Condition Evaluation Report say the configuration was not imported, or was imported yet failed a condition?

This is the most common scenario for distinguishing **unit testing a configuration** from **JAR discovery**.

### Case B: Bean exists yet has the wrong greeting prefix

Check whether **demo.greeting.prefix** has the exact prefix/key spelling; check whether the config file is loaded by the application; check whether a higher-precedence config source is overriding it. In the library, verify the bean factory method uses **properties.getPrefix()** rather than a hard-coded string.

### Case C: Two Greeter beans exist, controller reports ambiguous

Read the names and registration sources of both beans. Confirm the custom bean has the exact **Greeter** type that **@ConditionalOnMissingBean** checks, and that the auto-configuration class was not also registered as an application configuration class by another means. Do not mechanically patch the error with **@Primary** before understanding why two beans exist.

### Case D: The "disabled" test passes yet demo-app fails to start

When **enabled=false**, auto-configuration does not create Greeter. If **GreetingController** requires Greeter mandatorily and there is no replacement bean, the application will fail to satisfy the dependency. That is reasonable behavior; design feature toggles and consumers consistently. Testing "bean absent" and testing "full application starts cleanly" are two different goals.

### Case E: `@AutoConfiguration` is present yet not auto-discovered

Adding the annotation to the class alone is not enough for a Spring Boot 3.x library. Ensure **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** is inside the JAR and lists the exact class name. Do not assume a class outside scanned packages will be found by component scanning.

### Case F: Default is still created even when a custom bean is added

Check the exact bean type, bean name, **@ConditionalOnMissingBean** condition, when bean definitions are processed, and how the configuration was imported. For auto-configuration libraries, use **@AutoConfiguration** and the imports mechanism to preserve proper processing order relative to user configuration. Do not solve this by enabling global bean definition overriding.

## Library design principles to retain after this lesson

**First, auto-configuration is an explicit contract.** Document which beans may be created, which properties control them, what defaults apply, when they back off, and which conditions they depend on. Users should not have to read source code just to know how to disable a feature.

**Second, separate API and implementation when the library grows.** A production library can have a core module, an autoconfigure module, and a starter module. The starter distributes dependencies; the autoconfigure module supplies conditional beans; core owns the API and business logic. This exercise merged the Greeter API into the autoconfigure module for brevity. In real development, consider splitting modules so consumers do not unintentionally depend directly on implementations.

**Third, use properties for common configuration variations.** Changes such as prefix, endpoint, timeout, and feature enablement should have clear property names and safe defaults. Require custom beans only when behavior changes cannot be expressed via properties.

**Fourth, conditions must have a purpose.** **@ConditionalOnMissingBean** serves overridability; **@ConditionalOnProperty** serves toggling. Do not add **@ConditionalOnClass** when the class is always in the same JAR and not genuinely optional.

**Fifth, avoid leaking component scan outward.** Library configurations should register beans via intentional methods and **AutoConfiguration.imports**. Do not require every application to add **scanBasePackages** pointing to internal packages for the library to work.

**Sixth, verify both packaging and runtime.** Condition logic tests can pass even while the imports file is missing. Checking the classpath/JAR and running a consuming application in a different package are essential steps.

**Seventh, separate functional learning from operational readiness.** This demo proves auto-configuration; it does not prove production quality in security, secret configuration, performance, multi-version compatibility, concurrency, logging, or binary compatibility. Those concerns must be evaluated separately when releasing a library.

## Self-assessment checklist in learning order

Check off only after having real evidence, not merely after reading theory:

- [ ] Listed at least one Boot infrastructure bean and identified its registration source.
- [ ] Read Positive/Negative Matches in the Condition Evaluation Report of a real running application.
- [ ] Explained the difference between starter, component scanning, and auto-configuration.
- [ ] Clearly described the API, properties, defaults, and back-off condition before writing code.
- [ ] Built the library JAR containing **Greeter**, **GreetingProperties**, and **GreetingAutoConfiguration**.
- [ ] Verified the exact **AutoConfiguration.imports** resource is present in the JAR.
- [ ] Passed tests for default bean creation, changing prefix, custom bean, and disabled state.
- [ ] Ran demo-app without directly using **@Import** on the auto-configuration.
- [ ] Observed the expected Greeter bean and HTTP response.
- [ ] Added a custom bean and proved the default bean backs off.
- [ ] Explained why isolated tests do not replace verifying discovery through the JAR.

## Extension exercises to prove mastery

1. **Change a condition:** switch **matchIfMissing=true** to **false**. Predict which tests change before running; update tests to assert the new policy. When done learning, restore the original design.
2. **Add a property:** add **suffix** to **GreetingProperties**, update Greeter, and verify both default and custom values via tests.
3. **Missing imports:** temporarily remove the imports resource in an experimental branch; rerun ApplicationContextRunner and demo-app, and explain why results differ.
4. **Add a real classpath condition:** if the new library has an optional dependency, create an appropriate test classloader to verify the bean is skipped when the dependency disappears.
5. **Package as a starter:** split core, autoconfigure, and starter so a consuming application only needs to pick one starter dependency; verify that startup/discovery still works properly.

Each time, change **one factor**, record prediction → run → observe → conclude. This workflow helps learners distinguish cause from symptom instead of editing code until it merely "runs".

## Summary

The sequence that captures the true nature of auto-configuration begins with **observing existing beans**, proceeds to **reading bean-creation conditions**, then **designing the default contract**, **registering library configuration**, **testing with a small context**, and finally **running a consuming application to prove real discovery**.

The Greeter exercise provides a closed loop of evidence: the library publishes **AutoConfiguration.imports**, Boot imports **GreetingAutoConfiguration**, conditions control **Greeter** bean creation, properties configure behavior, user beans can replace the default, and both tests and a real running application confirm the outcome. Once you master this path, you have the foundation to read and write auto-configurations for more complex infrastructure libraries.
