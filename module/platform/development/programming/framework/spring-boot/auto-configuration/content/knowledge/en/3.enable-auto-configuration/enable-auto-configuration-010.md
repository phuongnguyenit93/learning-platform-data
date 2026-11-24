# Setting Up a Minimal Application to Observe Auto-Configuration Without a Web Server

## 1. Objectives and Big Picture

To understand **Spring Boot auto-configuration**, you do not need to create a REST API, controllers, an HTTP port, or run Tomcat. A console application containing only an `ApplicationContext` is enough to observe how Spring Boot finds candidate configurations, evaluates conditions, registers beans, and decides which beans exist.

In this lesson, you will build a minimal Spring Boot application using **Java 17+ and Spring Boot 3.3.13**. The application launches in **non-web mode** (`WebApplicationType.NONE`), exits automatically after printing results, and demonstrates three behaviors:

1. Auto-configuration present and conditions met: Boot creates a default bean.
2. Application declares its own bean: the default bean backs off because of `@ConditionalOnMissingBean`.
3. Disabling configuration via property or excluding the auto-configuration: the auto bean does not appear.

We will use two sources of evidence: bean state inside `ApplicationContext` and the *Condition Evaluation Report*, where Spring Boot records why conditions matched or did not match.

~~~text
                       Spring Boot console application
                                 |
        @SpringBootApplication  |  .web(WebApplicationType.NONE)
                                 v
                         AnnotationConfigApplicationContext
                                 |
                 @EnableAutoConfiguration is activated
                                 |
                   reads AutoConfiguration.imports
                                 |
                   DemoAutoConfiguration candidate
                                 |
                 classpath/property/bean conditions
                                 |
                +----------------+----------------+
                |                                 |
             conditions match              do not match
                |                                 |
     Default BeanDefinition               not registered
                |
      create bean on context refresh
                |
                v
      ApplicationContext / ConditionEvaluationReport
                |
           print output -> close context -> process exits
~~~

**Important limitation:** auto-configuration does not work only in web apps. Configurations for logging, JSON, task execution, properties, messaging, and many other libraries can work in an application without a web server if the corresponding dependencies and conditions match.

## 2. Choosing the Minimal Dependency Set for the Experiment

We use `spring-boot-starter` instead of `spring-boot-starter-web`. The basic starter provides components for application lifecycle, auto-configuration, logging, and context; it does **not** need a Servlet container or Netty server to run this example.

### `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>lab</groupId>
    <artifactId>auto-configuration-console</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

You need **JDK 17 or higher** and a compatible Maven version (such as Maven 3.9+). Gradle can be used instead of Maven; the auto-configuration mechanism does not change. Choosing Maven here keeps the example standalone and easy to copy, without depending on a specific repository's build setup.

### Complete Directory Tree

~~~text
auto-configuration-console/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── lab/
        │       ├── app/
        │       │   └── InspectApplication.java
        │       ├── contract/
        │       │   └── DemoService.java
        │       └── autocfg/
        │           └── DemoAutoConfiguration.java
        └── resources/
            └── META-INF/
                └── spring/
                    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

In this layout, the application class sits in `lab.app`; the auto-configuration sits in a **sibling** package `lab.autocfg`, outside the default component scan scope. That is essential to prove the configuration class is loaded from `AutoConfiguration.imports`, rather than accidentally picked up by `@ComponentScan`.

## 3. Three Java Classes and One Candidate Registration File

### 3.1. Service Contract: `DemoService.java`

~~~java
package lab.contract;

public interface DemoService {
    String origin();
}
~~~

This is a plain Java interface. With no `@Component`, Spring does not automatically create a bean from this interface. It lets us observe how a bean of the same type can originate from **auto-configuration** or **application-declared configuration**.

### 3.2. Auto-Configuration: `DemoAutoConfiguration.java`

~~~java
package lab.autocfg;

import lab.contract.DemoService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(DemoService.class)
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class DemoAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(DemoService.class)
    public DemoService defaultDemoService() {
        return () -> "auto";
    }
}
~~~

Each annotation handles one step:

- `@AutoConfiguration`: declares this as a Spring Boot auto-configuration class. Essentially, it is a Spring configuration with `proxyBeanMethods=false`.
- `@ConditionalOnClass(DemoService.class)`: applies the configuration only if `DemoService` is on the classpath. In the experiment, this condition always passes because the interface lives in the project.
- `@ConditionalOnProperty(...)`: applies the configuration only if `demo.feature.enabled=true`; because `matchIfMissing=true`, **omitting the property** also counts as matching.
- `@Bean`: supplies a bean definition named `defaultDemoService`, of type `DemoService`.
- `@ConditionalOnMissingBean(DemoService.class)`: allows the default bean only when no other `DemoService` bean visible to the condition exists yet.

A **class-level** condition differs from a **method-level** condition. When the property does not match, the entire auto-configuration is skipped. When the class remains eligible yet the application already has a `DemoService` bean, only the default bean is skipped. Those two outcomes will be distinguished by experiment.

**Do not add `@ComponentScan` on an auto-configuration class.** Spring Boot recommends registering auto-configurations through the imports file and using intentional `@Import` if splitting configuration is needed. In the experiment, component scan from `lab.app` does not see `lab.autocfg`.

### 3.3. Registering Candidates via `AutoConfiguration.imports`

Create the file with the **exact name and path**:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Content is a single line:

~~~text
lab.autocfg.DemoAutoConfiguration
~~~

Each line declares the fully qualified class name of a candidate auto-configuration. In Spring Boot 3.x, this file is the JAR-based auto-configuration registration mechanism. Merely putting `@AutoConfiguration` on a Java class without **registering it in imports** will not get it picked up automatically through this pipeline.

**Distinction:** `AutoConfiguration.imports` is a list of **candidate classes**, not a list of beans guaranteed to exist in the context. Spring Boot still applies exclusions, classpath, property, and bean conditions.

### 3.4. Console Application: `InspectApplication.java`

~~~java
package lab.app;

import lab.contract.DemoService;
import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class InspectApplication {

    @Bean
    @ConditionalOnProperty(
        prefix = "demo",
        name = "custom",
        havingValue = "true"
    )
    DemoService customDemoService() {
        return () -> "custom";
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                new SpringApplicationBuilder(InspectApplication.class)
                    .web(WebApplicationType.NONE)
                    .bannerMode(Banner.Mode.OFF)
                    .run(args)) {

            DemoService service =
                context.getBeanProvider(DemoService.class).getIfAvailable();

            ConditionEvaluationReport report =
                ConditionEvaluationReport.get(context.getBeanFactory());

            ConditionEvaluationReport.ConditionAndOutcomes classConditions =
                report.getConditionAndOutcomesBySource().get(
                    "lab.autocfg.DemoAutoConfiguration"
                );

            System.out.println("webServer=" +
                (context instanceof WebServerApplicationContext));
            System.out.println("defaultBean=" +
                context.containsBean("defaultDemoService"));
            System.out.println("customBean=" +
                context.containsBean("customDemoService"));
            System.out.println("selected=" +
                (service == null ? "none" : service.origin()));
            System.out.println("autoConfigClassMatched=" +
                (classConditions != null && classConditions.isFullMatch()));
        }
    }
}
~~~

The application has exactly one `main` entry point, one automatically imported default configuration, and one optional user-defined bean:

- `@SpringBootApplication` activates `@EnableAutoConfiguration` and component scan. `lab.autocfg.DemoAutoConfiguration` is **not** within the scan scope from `lab.app`.
- `SpringApplicationBuilder(...).web(WebApplicationType.NONE)` forces Boot to use non-web mode.
- `bannerMode(Banner.Mode.OFF)` suppresses the banner to keep logs concise; this does **not** disable auto-configuration.
- `try (ConfigurableApplicationContext ...)` guarantees the context is closed when the block finishes.
- `customDemoService()` creates a bean only if `--demo.custom=true` is passed.
- `context.getBeanProvider(DemoService.class).getIfAvailable()` lets us check even the **no-bean** case without crashing the application.
- `ConditionEvaluationReport.get(context.getBeanFactory())` retrieves the condition report inside the context. `classConditions` checks only conditions **on the auto-configuration class**, not the full `@Bean` method conditions.

In this small application, if you replaced `getIfAvailable()` with required injection of `DemoService`, the no-bean case would fail on startup. We use an optional lookup so all states can be observed.

## 4. Why Does `WebApplicationType.NONE` Matter?

Spring Boot normally infers the application type from the classpath:

- **`SERVLET`:** uses the Servlet web application model when relevant classes are present and appropriate.
- **`REACTIVE`:** uses the reactive web application model when the classpath matches.
- **`NONE`:** does not create a web application context.

Even though basic `spring-boot-starter` needs no web server, this example also **explicitly sets NONE** to lock down the experiment's scope. If a web starter were accidentally added later, the code would still actively run in non-web mode.

There are three common ways to select NONE mode:

~~~java
// Option 1: builder, used in the full example.
new SpringApplicationBuilder(InspectApplication.class)
    .web(WebApplicationType.NONE)
    .run(args);
~~~

~~~java
// Option 2: SpringApplication API.
SpringApplication application =
    new SpringApplication(InspectApplication.class);
application.setWebApplicationType(WebApplicationType.NONE);
application.run(args);
~~~

~~~properties
# Option 3: src/main/resources/application.properties
spring.main.web-application-type=none
~~~

**The three snippets above illustrate alternative options**, not to be combined into the same file simultaneously. Option 2 requires importing `org.springframework.boot.SpringApplication` and `WebApplicationType`.

NONE mode **does not turn off the Spring container** or auto-configuration; it merely states that Spring Boot will not create a web application context with an embedded web server. Web-independent beans are still managed. Some auto-configurations annotated with `@ConditionalOnWebApplication` will not match; those with `@ConditionalOnNotWebApplication` may match depending on other conditions.

### How Does "No Web Server" Differ from "No Open Port"?

A non-web application will **not start Spring Boot's default HTTP server**. However, if a bean you write or an arbitrary library actively opens a socket, `WebApplicationType.NONE` does not prevent that activity. In this example there are no networking beans, so no HTTP server starts.

We print `webServer=false` by checking whether the context is an instance of `WebServerApplicationContext`. This verifies the **context type** rather than trying to send an HTTP request to a guessed port.

## 5. First Run and Reading the Output

In the `auto-configuration-console` directory containing `pom.xml`:

~~~bash
java -version
mvn -version
mvn -q spring-boot:run
~~~

Note: the version-check commands print their own details. The Maven command may print Spring Boot logs; below we list only **the five lines emitted by the program's `System.out.println` statements**, not the full stdout/stderr.

~~~text
webServer=false
defaultBean=true
customBean=false
selected=auto
autoConfigClassMatched=true
~~~

Line-by-line interpretation:

1. `webServer=false`: the context is not a `WebServerApplicationContext`.
2. `defaultBean=true`: the `defaultDemoService` bean from auto-configuration was registered.
3. `customBean=false`: the user bean's property condition has not been enabled.
4. `selected=auto`: the `DemoService` type resolved to the default bean.
5. `autoConfigClassMatched=true`: the class-level conditions of `DemoAutoConfiguration` recorded a match.

Why not `selected=none`? Because `DemoService` is on the classpath, `demo.feature.enabled` is absent so `matchIfMissing=true` matches, and no application-supplied bean of the same type exists yet.

### Running the JAR Instead of the Maven Plugin

~~~bash
mvn -q -DskipTests package
java -jar target/auto-configuration-console-1.0.0.jar
~~~

When `main` completes, the context is closed by `try-with-resources` and the process normally exits. Because there is no HTTP server, the application does not wait for network requests. Background tasks or threads, if added later, could alter process lifetime; that would be behavior of those new components, not of the current example.

## 6. Four Key Verification States

### Case A — Keep Defaults

~~~bash
mvn -q spring-boot:run
~~~

Application output:

~~~text
webServer=false
defaultBean=true
customBean=false
selected=auto
autoConfigClassMatched=true
~~~

Auto-configuration is present, and both class and method conditions pass.

### Case B — Application Declares Its Own Bean

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.custom=true
~~~

Output:

~~~text
webServer=false
defaultBean=false
customBean=true
selected=custom
autoConfigClassMatched=true
~~~

`@ConditionalOnProperty` on `customDemoService` is satisfied. The application-declared bean is processed before auto-configuration, so `@ConditionalOnMissingBean(DemoService.class)` on the default bean no longer passes.

**Notable detail:** the auto-configuration's **class-level** condition still matches (`autoConfigClassMatched=true`); only the default bean's **method-level** condition fails. Do not conclude the entire auto-configuration was disabled just because the default bean backed off.

### Case C — Disable Configuration via Property

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.feature.enabled=false
~~~

Output:

~~~text
webServer=false
defaultBean=false
customBean=false
selected=none
autoConfigClassMatched=false
~~~

Here `@ConditionalOnProperty` **on the class** makes the configuration ineligible. Since there is no user bean, the context has no `DemoService`. `getIfAvailable()` returns `null` instead of throwing an exception.

### Case D — Disable Auto-Configuration Yet Keep User-Declared Bean

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments="--demo.custom=true --demo.feature.enabled=false"
~~~

Output:

~~~text
webServer=false
defaultBean=false
customBean=true
selected=custom
autoConfigClassMatched=false
~~~

The user bean is not deleted when auto-configuration fails its conditions. This shows that auto-configuration serves to provide context-aware defaults, while the application retains control over its own beans.

### Comparison Table of the Four Runs

| Input Variables | Auto-Config Class Eligible? | Default Bean | User Bean | `selected` |
| --- | --- | --- | --- | --- |
| No properties passed | Yes | Yes | No | `auto` |
| `demo.custom=true` | Yes | No | Yes | `custom` |
| `demo.feature.enabled=false` | No | No | No | `none` |
| Both properties as in D | No | No | Yes | `custom` |

Across all four runs, `webServer=false`. The differing beans have **nothing to do with whether an HTTP server exists**.

## 7. Observing the Condition Evaluation Report

Checking bean names with `containsBean` shows **the outcome**; the condition report answers **why**.

### Enabling the Report via `--debug`

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Spring Boot's `--debug` mode enables debug logging for several loggers and displays the *Condition Evaluation Report*. In the long output, look for `DemoAutoConfiguration` and `defaultDemoService`.

You must distinguish:

- **Positive matches:** conditions that matched during the run.
- **Negative matches:** conditions that were evaluated and did not match.
- **Exclusions:** auto-configuration classes explicitly excluded by the user from consideration.
- **Unconditional classes:** auto-configuration classes recorded as having no report-level conditions.

Exact group names/display formatting in the report can vary by version and logging level. Do not infer from a class appearing in the report that all beans of that class have been instantiated.

Try enabling debug with the user bean case:

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments="--debug --demo.custom=true"
~~~

Expect to see `DemoAutoConfiguration`'s class condition matching and `defaultDemoService`'s `@ConditionalOnMissingBean` condition **not matching**. That is the evidence explaining why `defaultBean=false` despite the class-level match being true.

### Reading the Report Programmatically in Java

In the example, the snippet:

~~~java
ConditionEvaluationReport report =
    ConditionEvaluationReport.get(context.getBeanFactory());

ConditionEvaluationReport.ConditionAndOutcomes conditions =
    report.getConditionAndOutcomesBySource().get(
        "lab.autocfg.DemoAutoConfiguration"
    );

boolean matched =
    conditions != null && conditions.isFullMatch();
~~~

is an **excerpt from the complete `main`**. This is how to retrieve the outcome group of the auto-configuration class and check whether all its class conditions matched.

To inspect method conditions, you can look up entries whose source starts with the class name plus `#defaultDemoService` in the report's map:

~~~java
report.getConditionAndOutcomesBySource().entrySet().stream()
    .filter(entry ->
        entry.getKey().startsWith(
            "lab.autocfg.DemoAutoConfiguration"
        )
    )
    .forEach(entry ->
        System.out.println(entry.getKey()
            + " -> " + entry.getValue().isFullMatch())
    );
~~~

*The snippet above runs inside `main`, once the `report` variable exists.* Use it to inspect sources specific to this class. The count and order of printed sources can vary across scenarios, so **no fixed stdout is given for this extension snippet**.

**Boundary of the report:** `ConditionEvaluationReport` is about condition evaluation, not a final inventory of every Java object. A bean definition can exist while its instance is uninitialized due to `@Lazy`/scope; a bean can fail instantiation due to invalid dependencies. When concluding that a bean actually exists, always cross-check with the context.

## 8. Trying Candidate Exclusion to Distinguish It from Condition Mismatch

Besides conditional properties, Spring Boot allows disabling a specific auto-configuration via `spring.autoconfigure.exclude`:

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--spring.autoconfigure.exclude=lab.autocfg.DemoAutoConfiguration
~~~

With `demo.custom` off, the program prints:

~~~text
webServer=false
defaultBean=false
customBean=false
selected=none
autoConfigClassMatched=false
~~~

This case looks identical to output C in the bean lines, yet **the cause differs**:

- **Property=false:** the class is in the candidate list yet its class condition fails.
- **Exclude:** the candidate class is proactively excluded before being processed as an eligible auto-configuration.

In the debug report, check the **Exclusions** section to verify the second cause. `autoConfigClassMatched=false` in the program is simply the combined result of finding no matching condition group; that boolean alone cannot distinguish **excluded** from **property mismatch**.

You can also exclude via annotation:

~~~java
@SpringBootApplication(
    excludeName = "lab.autocfg.DemoAutoConfiguration"
)
public class InspectApplication {
    // Keep other methods identical to the main example.
}
~~~

This is an **illustrative snippet showing how to change the annotation at the top of the class**, not a standalone program. When testing this way, omit the command-line exclusion to observe the annotation's effect in isolation.

## 9. Trying Removal of the Registration in Imports

Temporarily remove the line:

~~~text
lab.autocfg.DemoAutoConfiguration
~~~

from `AutoConfiguration.imports` (keeping the file valid, no need to add another class), then rerun with defaults. Because `lab.autocfg` is outside component scan from `lab.app`, the auto-configuration is not imported through the candidate mechanism. Output matches the no-default-bean case:

~~~text
webServer=false
defaultBean=false
customBean=false
selected=none
autoConfigClassMatched=false
~~~

For a console application, this behavior shows that a Java class annotated with `@AutoConfiguration` **is not enough**; it needs a registration path for Boot to discover it. Restore the line in imports before trying subsequent cases.

If you still see the default bean after removing the imports entry, check whether the class was pulled into component scan/`@Import` from somewhere else and clean the build so resources are updated.

## 10. When You Don't Want to Write a Custom Auto-Configuration

The minimal setup to **observe built-in auto-configurations** needs only the basic starter, `@SpringBootApplication`, and a `main` running `WebApplicationType.NONE`. This example can print the count of configuration sources appearing in the condition report without declaring `DemoAutoConfiguration`:

~~~java
package lab.app;

import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class InspectDefaults {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 new SpringApplicationBuilder(InspectDefaults.class)
                     .web(WebApplicationType.NONE)
                     .bannerMode(Banner.Mode.OFF)
                     .run(args)) {

            ConditionEvaluationReport report =
                ConditionEvaluationReport.get(context.getBeanFactory());

            long evaluatedSources =
                report.getConditionAndOutcomesBySource().size();

            System.out.println("evaluatedSources=" + evaluatedSources);
        }
    }
}
~~~

This is a **complete Java file** (`lab/app/InspectDefaults.java`), yet it requires `pom.xml`/dependencies as in section 2 and should be run in a separate project or with the right main class configured if the project has multiple entry points. The `evaluatedSources` count varies by classpath and version, so **no fixed stdout is given** for this output.

The extended example with `DemoAutoConfiguration` is more useful for learning because we actively control three kinds of conditions and can explain why outcomes change. When exploring real starters, keep the same observation methodology and swap in conditions relevant to the dependency under test.

## 11. Observing Beans and Bean Definitions More Accurately

### Existing Bean Names

Printing like this:

~~~java
String[] names =
    context.getBeanNamesForType(DemoService.class);
java.util.Arrays.sort(names);
System.out.println(java.util.Arrays.toString(names));
~~~

This is an **extension snippet for the complete program**, given the existing `context` variable. Across the four basic states, expect `[defaultDemoService]`, `[customDemoService]`, or `[]`.

### A Bean Definition Does Not Guarantee the Instance Is Ready

`containsBean("name")` and `getBeanNamesForType` report names/lookup availability in the context. To inspect registration more deeply, use:

~~~java
var factory = context.getBeanFactory();
boolean definitionExists =
    factory.containsBeanDefinition("defaultDemoService");
System.out.println("definitionExists=" + definitionExists);
~~~

In the default example, this line is `definitionExists=true`; when auto-configuration is excluded or the default bean backs off, `false`.

Do not confuse this with when the constructor/factory method runs. Default singletons are normally created during refresh; lazy beans can be deferred; prototypes are created per request. `getBean(...)` can trigger instantiation, so avoid calling it unnecessarily when you only want to inspect definitions.

### If Startup Fails Before `main` Can Read the Report

`SpringApplicationBuilder.run(args)` can throw an exception while building the context. At that point, code inside `try` **has not executed yet**, so expected `System.out.println` lines will not appear. Run with `--debug` and read the root cause exception; Spring Boot may print the Condition Evaluation Report before terminating on error. Do not conclude "the report is empty" just because code after `run` did not get to execute.

## 12. How to Verify for Sure That No Web Server Is Running

There are three independent checks with different purposes:

1. **Application configuration:** code has `.web(WebApplicationType.NONE)` or property `spring.main.web-application-type=none`.
2. **Context type:** `context instanceof WebServerApplicationContext` is `false` as in the example.
3. **Startup logs:** no message indicates an embedded HTTP server started for this application.

Do not rely on trying `http://localhost:8080` and getting a connection error as sole proof. A server might have used another port, or a separate service might occupy that port. Conversely, in NONE mode, Boot does not start an embedded web server even when web classes exist on the classpath.

**Note on dependencies:** If you use `spring-boot-starter-web` or `spring-boot-starter-webflux`, many extra components are pulled in and some classpath conditions change. NONE mode still dictates the context type, yet the non-web condition set may differ. To study the mechanism with minimal noise, keep the basic `spring-boot-starter` and add dependencies intentionally one at a time.

## 13. Common Errors and How to Fix Them

| Symptom | Cause to Check | Resolution |
| --- | --- | --- |
| Application starts an HTTP server | Web starter used without setting `WebApplicationType.NONE` | Add `.web(WebApplicationType.NONE)` or the corresponding property |
| `defaultDemoService` missing on default run | Wrong path/name for `AutoConfiguration.imports`, wrong FQCN, class excluded, or condition failed | Check file under `src/main/resources`, package, class name, and report |
| `customBean=true` yet `defaultBean=false` | `@ConditionalOnMissingBean` worked as designed | Expected result; inspect the method's report |
| `selected=none` and app still runs | `getIfAvailable()` used for optional bean | Expected result in state C |
| `NoSuchBeanDefinitionException` | Accessing a required bean when no matching instance/definition exists | Use an optional provider when observing, or add valid configuration |
| `--debug` prints huge number of configurations | Many Boot/starter auto-configurations are evaluated | Search for `DemoAutoConfiguration` and `defaultDemoService` |
| Debug conditions section not visible | Wrong argument passed to Maven plugin or logging misconfigured | Try `java -jar ... --debug` or configure logging per Boot docs |
| Auto-config class has annotation yet is not processed | Missing FQCN line in `AutoConfiguration.imports`, or class scanned/imported unexpectedly | Use imports and keep auto-config package outside component scan |
| Maven fails due to Java version | JDK too old or wrong `JAVA_HOME` | Check `java -version`, `mvn -version`, and Java 17+ |
| Output differs in log line count or other beans | Different classpath/Boot version/log settings | Compare only the demo's `System.out.println` lines, not full logs |
| Application does not exit | Background thread, scheduler, or other bean added | Check background tasks and lifecycle; original demo closes context itself |

### Investigation Workflow When Output Differs from Expectations

1. Verify `@SpringBootApplication` is properly on `lab.app.InspectApplication`, and the imports file states exact `lab.autocfg.DemoAutoConfiguration`.
2. Ensure you are running the right project, main class, Spring Boot version, and test arguments.
3. Check `webServer=false` to rule out running another application type.
4. Check `autoConfigClassMatched` first: if `false`, check class condition/exclusions/imports; if `true` yet `defaultBean=false`, check missing-bean on the method.
5. Check `customBean` to see whether the application supplied a `DemoService`.
6. Enable `--debug`, find the exact source name and condition message in the report. Do not rely solely on a JAR being present.
7. Cross-check `getBeanNamesForType` or `containsBeanDefinition` with printed lines before concluding.

## 14. Practice Exercises

1. **Change the default:** switch `matchIfMissing=true` to `false`. Run with no property and run with `--demo.feature.enabled=true`. Explain the change using the exact condition parameter.
2. **Test the user bean:** enable `--demo.custom=true`. Read the report section for `defaultDemoService` and identify why the default bean backed off.
3. **Intentionally disable auto-configuration:** use `spring.autoconfigure.exclude`, then enable `demo.custom=true`. Does the user-declared bean exist?
4. **Test imports:** remove the class name line in the imports file, rerun, then restore it. Why does the code still compile yet the default bean does not appear?
5. **Use non-web mode on a rich-dependency classpath:** add the web starter while keeping `WebApplicationType.NONE`. Compare context type and report entry count; analyze which conditions changed due to classpath.
6. **Compare definition and instance:** add `@Lazy` to the default bean, observe the difference between `containsBeanDefinition` and calling `getBeanProvider(...).getIfAvailable()`.
7. **Create a second conditional:** add `@ConditionalOnProperty(prefix = "demo.extra", name = "enabled", havingValue = "true")` on a new `@Bean` method with a different name. Check property states and report reasons. Avoid creating two beans of the same `DemoService` type without resolving ambiguous injection.
8. **Explain causes:** given `defaultBean=false`, name three distinct causes (class not imported, class condition failed, method condition failed) and state the evidence to read to distinguish them.

**Completion criteria:** you can create a Boot application without an HTTP server, intentionally enable/disable an auto-configuration, understand why a default bean backs off for an application bean, read `ConditionEvaluationReport`, and verify actual outcomes using `ApplicationContext`.

## 15. References

- [Spring Boot 3.3 — SpringApplication, running applications and startup configuration](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — WebApplicationType Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html)
- [Spring Boot 3.3 — ConditionEvaluationReport Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html)
- [Spring Boot 3.3 — SpringApplicationBuilder Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/builder/SpringApplicationBuilder.html)
