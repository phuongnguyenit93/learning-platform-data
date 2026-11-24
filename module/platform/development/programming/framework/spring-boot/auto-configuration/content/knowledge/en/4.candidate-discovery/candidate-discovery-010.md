# Distinguishing Candidate Discovery Failures from Unmet Candidate Conditions

## 1. Problem and Objectives

A common problem report in Spring Boot is: **“I added the starter or wrote `@AutoConfiguration`, yet the expected bean still does not appear.”** That symptom can stem from at least two very different stages:

- **Candidate discovery failure:** Spring Boot does not find the auto-configuration class in the candidate list for this run. Without another import mechanism, the configuration class does not enter the auto-configuration pipeline for its conditions to be evaluated.
- **Candidate discovered yet conditions unmet (condition mismatch):** Spring Boot knows about the configuration class, yet one or more `@Conditional` annotations on the class or `@Bean` method do not match; the corresponding configuration or bean is not registered.

Both can lead to the same outcome: `ApplicationContext` lacks the expected bean. Therefore, **“no bean” is insufficient to conclude “failed to load auto-configuration”**.

After this lesson, you will be able to identify the right failure stage, understand what evidence is strong enough for each case, inspect the classpath and metadata, read `ConditionEvaluationReport`, further distinguish exclusions and bean back-off, and practice on a runnable Java 17+ project.

The scope belongs to the **Candidate Discovery** group of Spring Boot auto-configuration. The lesson focuses on the diagnostic chain from **imports resource → candidate class name → filtering/exclusion → conditions → bean definition**. It does not collapse every startup failure into a discovery failure.

## 2. Lifecycle Map: Inspecting Failures in the Right Place

When an application has `@SpringBootApplication` (which includes `@EnableAutoConfiguration`), the main flow can be understood as:

~~~text
Dependency / JAR on runtime classpath
        |
        v
Resource META-INF/spring/
org.springframework.boot.autoconfigure.AutoConfiguration.imports
        |
        v
Read fully qualified class names
        |
        +---- Resource not found / expected class name absent
        |          -> Candidate not published/not discovered
        |
        v
AutoConfigurationImportSelector
        |
        +---- Exclusion / candidate selection filter
        |          -> May be removed from import list
        |
        v
Process selected @AutoConfiguration classes
        |
        +---- Class-level condition does not match
        |          -> Skip configuration
        |
        v
Process @Bean methods in configuration
        |
        +---- @Bean-level condition does not match
        |          -> Skip that specific bean definition
        |
        v
Register valid bean definitions
        |
        v
Instantiate beans via IoC container
        |
        +---- Constructor / dependency / lifecycle error?
                   -> Bean creation error, not a discovery error
~~~

The diagram highlights **decision gates**, without promising all conditional annotations run at one single moment or every filter emits the same log line. Spring Boot has candidate filtering steps and Spring Framework has distinct configuration parsing/registration phases.

Three questions must be kept separate:

1. **Is the class on the classpath?** Check dependencies and JAR contents.
2. **Is the class registered as an auto-configuration candidate?** Check the `AutoConfiguration.imports` file on the exact process classpath.
3. **Does the selected candidate satisfy conditions to register beans?** Check `@Conditional`, exclusions, properties, existing beans, and the condition report.

Having a class name in metadata **is not enough** to guarantee a bean exists. Having a class name in source code **is not enough** to guarantee Spring Boot knows that class is a candidate.

## 3. Identifying “Candidate Discovery Failure”

In Spring Boot 3.x, libraries normally publish auto-configuration classes via the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The file contains **one fully qualified class name per line**:

~~~text
com.example.feature.autoconfigure.FeatureAutoConfiguration
~~~

For example, a Maven project places the file at:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Typical mistakes:

- **Imports file not created:** the class has `@AutoConfiguration` yet is not listed on the runtime classpath.
- **Wrong location or filename:** placed under `src/main/java`, `src/test/resources`, wrong `META-INF` nesting level, missing `AutoConfiguration`, wrong letter casing.
- **Wrong FQCN:** package or class renamed while forgetting to update a line in the imports file.
- **Wrong artifact/classpath:** the project built the module containing metadata, yet the actual application lacks that module in runtime dependencies or is running a stale JAR.
- **Version mechanism mix-up:** copying `EnableAutoConfiguration` registration in `spring.factories` from an older Boot project into Boot 3.x. Spring Boot 2.7 introduced the imports file; for Boot 3.x, follow the registration mechanism appropriate for that version.
- **Accidentally relying on component scan:** in another application, the auto-configuration class lies outside the default scan range; `@AutoConfiguration` on the class alone does not make Spring Boot find it automatically.
- **Resource filtered out during build:** custom resource configuration, packaging plugins, or release steps dropped the file from the JAR.

### Strong Diagnostic Evidence

**Evidence 1 — Does the artifact contain the file?** For a plain library JAR:

~~~bash
jar tf path/to/feature-autoconfigure.jar
~~~

Look for the entry:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

For a Spring Boot executable JAR containing auto-configuration in the application module, the path is typically:

~~~text
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

If metadata lives in a dependency JAR, it is normally inside a nested JAR under `BOOT-INF/lib`, so inspect that exact dependency. `jar tf` only lists entries; it **does not** display file contents.

**Evidence 2 — Read the metadata contents.** Verify the line matches the fully qualified name of the actual class. If this line is absent from any imports resource on the runtime classpath, Boot will not discover the class via the standard imports mechanism. A line with an incorrect FQCN can trigger a class read/load error rather than being silently ignored; do not lump all metadata errors together.

**Evidence 3 — Does the real application enable auto-configuration?** Usually `@SpringBootApplication` enables it; a context using minimal `@Configuration` or a test loading only selected configurations may not run candidate discovery automatically. Check the startup setup instead of looking only at the JAR.

**Evidence 4 — Right classloader and version?** In multi-module environments, test slices, custom `ApplicationContext` setups, or packaged applications, the runtime classpath can differ from the IDE classpath. Try a clean build and inspect the exact artifact being executed.

Do not use the **mere absence of the class name from the condition report** as absolute proof of a discovery failure: the class could also have been removed by exclusions/filters, or the report could be scoped by environment/version. Conclusions must rest on multiple signals, especially metadata and the runtime classpath.

## 4. Identifying “Candidate Present Yet Condition Does Not Match”

Suppose Boot discovered:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true"
)
public class FeatureAutoConfiguration {
    // @Beans if the class condition matches.
}
~~~

This snippet **only illustrates annotations**, not a standalone program. If `demo.feature.enabled=false` or the key does not exist and `matchIfMissing` is not enabled, the class-level condition fails to match. The imports file is still valid, yet the configuration does not register the expected bean.

A real auto-configuration can contain these conditions:

| Condition | What to Check | Outcome If Unmet |
| --- | --- | --- |
| `@ConditionalOnClass` | Whether required classes/APIs are on the classpath | Skips the configuration or bean needing that library. |
| `@ConditionalOnMissingClass` | Whether a specific class is absent | Does not use the configuration branch meant for missing-class cases. |
| `@ConditionalOnProperty` | Final property value in `Environment`, `havingValue`, `matchIfMissing` | Skips configuration/bean when property does not match. |
| `@ConditionalOnBean` | Whether prerequisite bean was already processed and present at evaluation time | Skips configuration depending on prerequisite. |
| `@ConditionalOnMissingBean` | Whether a matching bean is already declared by the app or another config | **Back off**: does not register the corresponding default bean. |
| `@ConditionalOnWebApplication` | Whether web application type matches | Skips parts meant only for web environments. |
| `@ConditionalOnResource` | Whether required resource exists | Skips configuration needing that resource. |

A **class**-level condition may fail before `@Bean`-level conditions are even evaluated; or the class may pass while one `@Bean` method inside is skipped. Therefore, read the **exact line/method** in the condition report rather than looking only at the class name.

### Note on @ConditionalOnMissingBean

`@ConditionalOnMissingBean` is an easily misdiagnosed case. If the application already provided a matching bean, Spring Boot intentionally **backs off** to avoid creating an extra default. This is usually the intended behavior, not a candidate discovery failure.

Bean conditions inspect bean definitions already processed at evaluation time; they do not look ahead at every bean that might exist in the future. Boot processes auto-configurations in a deferred phase to give application-declared beans first chance. If you write bean-based conditions in arbitrary `@Configuration` classes, you cannot assume the same ordering as auto-configuration.

### Note on PropertySource Precedence

`@ConditionalOnProperty` queries values from `Environment`. A value in `application.properties` can be overridden by command-line arguments, environment variables, or system properties per precedence rules. When a condition does not match, inspect the **resolved value at condition evaluation time**, rather than looking at only one file.

## 5. Exclusion/Filter: The Third Case to Separate

A candidate can be **published** in the imports file yet **excluded from the applied list** via `@SpringBootApplication(exclude = ...)`, `excludeName`, or `spring.autoconfigure.exclude`.

Example:

~~~properties
spring.autoconfigure.exclude=com.example.feature.autoconfigure.FeatureAutoConfiguration
~~~

This is only an illustrative property example containing a class name. Even if the actual class exists and is properly registered, exclusion prevents Boot from applying it.

How it differs from a condition mismatch: exclusion is a **decision to omit the class from auto-configuration importing**, whereas a condition mismatch means a condition on the configuration/bean evaluated to false. Some optimizing filters may eliminate candidates early before Spring parses the class fully. Do not force every “missing from context” case into one of two labels if evidence shows it is an exclusion, filter, or class-loading error.

In diagnostic notes, record specifically:

- `NOT_DISCOVERED`: missing metadata/classpath or auto-configuration not enabled.
- `DISCOVERED_BUT_CONDITION_FALSE`: metadata present and exact condition failed to match.
- `EXCLUDED_OR_FILTERED`: excluded or eliminated during candidate selection.
- `REGISTERED_BUT_CREATION_FAILED`: bean definition exists yet bean creation failed.
- `INSUFFICIENT_EVIDENCE`: cause unclear; needs further investigation.

These labels are **diagnostic note templates**, not statuses printed automatically by Spring Boot.

## 6. Java 17+ Practice with Spring Boot 3.5.0

We will build a small Maven project to reproduce the **exact same missing-bean symptom** from two different causes:

1. Class registered in the imports file yet property condition does not match.
2. Imports file removed in a project copy, causing Boot not to discover the auto-configuration even though the Java class is still packaged.

The example also includes the valid case and back-off when the user provides a bean. This is a **standalone runnable application with Maven and Java 17+**, needing no web server, database, or external modules.

### 6.1. Directory Tree

~~~text
candidate-diagnosis/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── api/GreetingService.java
    │   ├── app/DemoApplication.java
    │   └── autoconfig/GreetingAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

`DemoApplication` sits in `com.example.app`; the auto-configuration class sits in the sibling package `com.example.autoconfig`. Spring Boot's default component scan starts from `com.example.app`, so it will not scan the auto-configuration class; bringing it in truly depends on imports metadata.

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>candidate-diagnosis</artifactId>
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

### 6.3. GreetingService.java

Place at `src/main/java/com/example/api/GreetingService.java`:

~~~java
package com.example.api;

public interface GreetingService {
    String greeting();
}
~~~

Merely having the interface on the classpath creates no bean. We will use a default bean from auto-configuration and an application-provided bean.

### 6.4. GreetingAutoConfiguration.java

Place at `src/main/java/com/example/autoconfig/GreetingAutoConfiguration.java`:

~~~java
package com.example.autoconfig;

import com.example.api.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true"
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService defaultGreetingService() {
        return () -> "AUTO";
    }
}
~~~

The class-level condition checks `demo.feature.enabled=true`. Because `matchIfMissing=false` is the default, missing the property also causes the condition not to match. `@ConditionalOnMissingBean(GreetingService.class)` on `@Bean` also lets the default bean step back if the application already provides a `GreetingService`.

### 6.5. AutoConfiguration.imports

Create the exact file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Exact single-line content:

~~~text
com.example.autoconfig.GreetingAutoConfiguration
~~~

The syntax is **one FQCN per line**; do not add `.class`, `.java`, or `spring.factories`-style keys.

### 6.6. DemoApplication.java

Place at `src/main/java/com/example/app/DemoApplication.java`:

~~~java
package com.example.app;

import com.example.api.GreetingService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.override",
            name = "enabled",
            havingValue = "true"
    )
    GreetingService customGreetingService() {
        return () -> "CUSTOM";
    }

    @Bean
    ApplicationRunner printResult(ObjectProvider<GreetingService> provider) {
        return args -> {
            GreetingService service = provider.getIfAvailable();
            System.out.println("SERVICE="
                    + (service == null ? "ABSENT" : service.greeting()));
        };
    }
}
~~~

`ObjectProvider` lets the application run normally even when no `GreetingService` exists, allowing us to observe the identical `SERVICE=ABSENT` stdout from two different errors. The example ensures at most one `GreetingService` bean in the presented cases; if you add multiple beans of the same type yourself without marking primary or qualifiers, `getIfAvailable()` can report a non-unique error.

### 6.7. application.properties

Place at `src/main/resources/application.properties`:

~~~properties
spring.main.banner-mode=off
logging.level.root=ERROR
~~~

Do not add `demo.feature.enabled` or `demo.override.enabled` to the file; use the command line to drive each scenario.

### 6.8. Building and Running the Scenarios

Install JDK 17+ and Maven, and from the directory containing `pom.xml`:

~~~bash
mvn -q -DskipTests package
java -jar target/candidate-diagnosis-1.0.0.jar --demo.feature.enabled=true
~~~

Line printed by the example:

~~~text
SERVICE=AUTO
~~~

Explanation: the imports file registers the candidate, the class condition matches, and no user-created `GreetingService` exists; the default bean is registered.

**Condition mismatch case while metadata remains valid:**

~~~bash
java -jar target/candidate-diagnosis-1.0.0.jar --demo.feature.enabled=false
~~~

Line printed by the program:

~~~text
SERVICE=ABSENT
~~~

The `GreetingAutoConfiguration` class is still a published candidate, yet `@ConditionalOnProperty` fails to match, so the default bean does not exist. With the sample configuration, omitting `--demo.feature.enabled` leaves the property absent and also yields `SERVICE=ABSENT`.

**Application-provided bean case where auto-configuration backs off:**

~~~bash
java -jar target/candidate-diagnosis-1.0.0.jar --demo.feature.enabled=true --demo.override.enabled=true
~~~

Line printed by the program:

~~~text
SERVICE=CUSTOM
~~~

The auto-configuration class can be selected, yet `@ConditionalOnMissingBean` prevents the default bean from being registered. This is intended behavior, distinct from a candidate discovery failure.

**Testing without the imports file:** In **an experimental copy of the project**, delete only `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, keeping all Java classes and remaining files. Then run a clean build to avoid stale copied resources lingering in `target/classes`:

~~~bash
mvn -q clean package -DskipTests
java -jar target/candidate-diagnosis-1.0.0.jar --demo.feature.enabled=true
~~~

Line printed by the program:

~~~text
SERVICE=ABSENT
~~~

At this point the property is right, yet `GreetingAutoConfiguration` is absent from metadata loaded via imports; the class sits outside component scan. Boot does not find it via the standard mechanism. Restore the imports file after the experiment.

**Key takeaway:** two `SERVICE=ABSENT` runs can arise from two causes: missing metadata or wrong property condition. Observing stdout alone cannot distinguish them; you must inspect the **imports resource/classpath** and the **condition report**.

### 6.9. Outcome Comparison Table

| Runtime State | Imports metadata has class name? | `demo.feature.enabled` | Condition and candidate | Program stdout |
| --- | --- | --- | --- | --- |
| Normal | Yes | `true` | Condition matches, no custom bean | `SERVICE=AUTO` |
| Condition mismatch | Yes | `false` | Candidate published yet class condition fails | `SERVICE=ABSENT` |
| App override | Yes | `true` | `@ConditionalOnMissingBean` fails due to app bean | `SERVICE=CUSTOM` |
| Discovery failure in copy | No | `true` | Boot does not pick up auto-configuration from imports | `SERVICE=ABSENT` |

## 7. Using the Condition Evaluation Report Properly

Spring Boot provides the **Condition Evaluation Report** to show which auto-configuration conditions matched or did not match. When investigating, enable debug and ensure the log level is high enough to view the report:

~~~bash
java -jar target/candidate-diagnosis-1.0.0.jar \
  --demo.feature.enabled=false \
  --debug \
  --logging.level.root=INFO
~~~

This command suits shells with line continuation `\` such as Bash. On Windows PowerShell, you can write the same command on **one line**:

~~~powershell
java -jar target/candidate-diagnosis-1.0.0.jar --demo.feature.enabled=false --debug --logging.level.root=INFO
~~~

In the condition report, look for `GreetingAutoConfiguration` and the reason the `demo.feature.enabled` property did not match. With the build keeping the imports file, a corresponding negative match entry can appear. Then run `--demo.feature.enabled=true` to compare when the condition is satisfied.

When **removing the imports file** and doing a clean build, `GreetingAutoConfiguration` is no longer published via metadata. Not seeing it in positive/negative matches is a signal to investigate discovery, yet **not sole proof**: exclusions, filters, logging, and how the context is initialized also affect what appears in the report.

The condition report describes **condition results**; it cannot replace verifying that the **JAR contains the right metadata**.

### Four Questions When Reading the Report

1. **Does the auto-configuration class name appear?** If yes, read the exact condition and decision; if not, check metadata/runtime and exclusions first.
2. **Is it a class-level or method-level condition?** A positive class does not guarantee a positive `@Bean`; inspect `Class#beanMethod` as well when present.
3. **What does the condition depend on?** Classpath, property, web context, existing bean, or resource?
4. **Are you diagnosing the right context?** Test slices (`@WebMvcTest`, `@DataJpaTest`), main app, management context, or custom test contexts can have different configuration sets.

In projects with Actuator and appropriate access permissions, the `/actuator/conditions` endpoint can also help inspect conditions. It is present only when dependencies, exposure configuration, and security permit; do not assume the endpoint is public in every application.

## 8. Inspecting Metadata in the Final Artifact

After building the example with the imports file, run:

~~~bash
jar tf target/candidate-diagnosis-1.0.0.jar
~~~

In a Spring Boot executable JAR, look for the resource:

~~~text
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

For a Maven library JAR not repackaged into an executable JAR, the entry to look for is typically:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

In a multi-module project, classes may live in module `feature-autoconfigure` while the application adds only module `feature-starter`; confirm the starter actually pulls the auto-config module into runtime. Do not look only at the source tree of another module.

To also verify the **contents** of the file, open the artifact with a ZIP/JAR tool or extract the resource alone into an inspection directory. Do not confuse seeing the entry with the FQCN inside the file being right. A metadata entry can contain an old class name after refactoring.

Checks that only inspect the file do not yet tell you whether conditions match. Therefore, the next step is always **reading the report and actual properties/environment**.

## 9. Decision-Driven Diagnostic Workflow

Follow this sequence when a default bean does not appear:

**Step 1 — Identify the exact expected bean and auto-configuration.** Find the configuration class that actually provides the bean, its `@Bean` method, bean name, and bean type. Do not infer from a starter name that a bean definitely exists.

**Step 2 — Check runtime dependencies.** Inspect `mvn dependency:tree` or `./gradlew dependencies --configuration runtimeClasspath` (whichever configuration matches the project). Ensure the library containing the class and metadata is in the running application, not only on test classpath or compile-only.

**Step 3 — Inspect the imports resource.** Locate the accurately named file in the right JAR version and read the actual FQCN. If metadata is missing, record a discovery/packaging error and fix the dependency or resource.

**Step 4 — Check that auto-configuration is enabled and not excluded.** `@SpringBootApplication` normally includes `@EnableAutoConfiguration`; however, the application may intentionally exclude specific configurations. Record the difference between “candidate not published” and “published yet excluded”.

**Step 5 — Read the Condition Evaluation Report.** If a condition fails to match, cite the exact annotation and facts: missing class, mismatched property value, bean presence/absence, web environment. Do not patch by adding imports files if a condition actually explains the issue.

**Step 6 — Compare property sources and profiles.** `application.properties` values can be overridden by profile-specific configs, environment variables, JVM properties, or command-line args. Find the final value used for evaluation, especially `havingValue` and `matchIfMissing`.

**Step 7 — Check bean definitions and initialization errors.** If conditions match yet the bean is still missing, check the bean method, scope, bean name, dependent configurations, and exception chain. A bean creation failure is a separate stage; do not call it a discovery failure.

**Step 8 — Try a minimal reproduction.** Using the app in section 6, change just one factor between runs: imports resource, property value, or application bean. That comparison yields clearer causal evidence than full logs of a large system.

You can briefly record the investigation summary:

~~~text
Expected bean: com.example.api.GreetingService
Auto-config class: com.example.autoconfig.GreetingAutoConfiguration
Artifact / classpath: candidate-diagnosis-1.0.0.jar
Imports resource: PRESENT | ABSENT | UNKNOWN
FQCN in resource: PRESENT | ABSENT | UNKNOWN
Excluded: YES | NO | UNKNOWN
Condition class/method: MATCH | NO_MATCH | NOT_EVALUATED | UNKNOWN
Bean definition: PRESENT | ABSENT | UNKNOWN
Root cause: discovery | exclude/filter | condition | creation | needs evidence
~~~

The values above are a note-taking template to avoid premature conclusions; they are **not** automatic output from a specific Boot tool.

## 10. Common Errors and Fixing at the Right Layer

| Finding | Appropriate Inference | Fix |
| --- | --- | --- |
| `@AutoConfiguration` present in code, imports file missing | Missing candidate registration via standard mechanism | Add resource at exact path with FQCN, rebuild/republish. |
| Imports file present in library yet absent from app's runtime classpath | Dependency/packaging error | Add runtime dependency on right module, inspect executed artifact. |
| Imports file valid yet app excludes class | Intentionally excluded or misconfigured | Check `exclude` / `spring.autoconfigure.exclude`, remove only if appropriate. |
| Class in report with `@ConditionalOnClass` unmatched | Participated in evaluation yet lacked required class | Add right dependency or accept skipping the optional branch. |
| Class in report with `@ConditionalOnProperty` unmatched | Property value did not satisfy condition | Check key name, value, profiles, precedence, `matchIfMissing`. |
| `@Bean` method skipped by `@ConditionalOnMissingBean` | Matching bean already present | If app bean is intentional, leave as is; otherwise find competing bean. |
| Report positive yet startup fails in constructor | Registration succeeded yet bean creation failed | Read exception chain and fix dependency/initialization. |
| Class not seen in report | Insufficient evidence to conclude yet | Check imports, exclusions, filters, context, and debug logging. |
| ApplicationContextRunner tests class directly and passes | Only proves configuration works when passed directly to context | Add artifact inspection / real discovery check via classpath. |

### Why “Adding the Starter” Can Mislead

Starters are usually convenient dependency bundles. Adding a starter only changes the **classpath**; auto-configuration also needs metadata, candidate selection, and conditions. A starter missing the auto-config module or mispackaging metadata leads to a discovery issue; a valid starter missing a service/configuration property can lead to a condition mismatch. Diagnosis must start from **where the bean is expected to be created**, not from assuming every starter always creates every bean.

### Why Not Fix with an Overly Broad @ComponentScan?

If you find an auto-configuration is not registered, scanning broadly into the library's package can cause the class to be treated as a regular Spring configuration and mask the metadata bug, while also unintentionally activating many other components. The proper fix is **putting the class into the right imports file** and ensuring the resource sits on the runtime classpath.

### Why Not Fix by Removing All @Conditional Annotations?

Conditions exist to avoid configuring integrations when prerequisite classes or beans are absent, and to yield priority to application configurations. Removing conditions can cause startup failures or competing beans. Verify the condition's purpose before changing it.

## 11. Self-Check Questions

1. **Does an application lacking bean X prove Spring Boot failed to discover auto-configuration X?** No; a class-level or `@Bean` condition might not match, it might be excluded, or bean creation might have failed.
2. **What happens if a class has `@AutoConfiguration` yet is not in the imports file?** Boot does not automatically discover it via standard auto-configuration metadata solely because of the annotation.
3. **What does a class appearing as a negative match in the condition report tell you?** At least one condition failed to match on the reported configuration/bean; read the detailed reason.
4. **Does a class being absent from the report prove metadata is missing?** No; you must inspect the classpath, imports file, exclusions, filters, and context type.
5. **Is an unmatched `@ConditionalOnMissingBean` always a bug?** No; it can be the intended back-off behavior when the application provides the bean.
6. **Is having the class on the classpath enough for auto-configuration to be registered?** No; imports metadata or another suitable import mechanism is also required.
7. **If metadata is valid yet `demo.feature.enabled=false`, does the demo bean appear?** No; the class condition rejects the configuration, and the program prints `SERVICE=ABSENT`.
8. **What if metadata is removed in the copy while the property is `true`?** The class is not discovered via imports and the default `GreetingService` is absent, also printing `SERVICE=ABSENT`.
9. **How do you distinguish a bean creation error from a discovery error?** Inspect the bean definition and exception chain; if the class/definition already participated and failed in the constructor/dependency, that is post-discovery.
10. **In a multi-module project, where should you inspect?** In the JAR and runtime classpath of the running application itself, not only in the source code of the module with the annotation.

## Official References

- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — Using Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — `ConditionEvaluationReport` API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Framework — `DeferredImportSelector` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.html

**Core takeaway:** a missing bean is only a **symptom**. To find the real root cause, you must prove whether Spring Boot found the candidate from metadata, check whether the class was excluded, read the actual conditions, and inspect bean definitions/instantiation. Once the right stage is identified, the fix is usually clear: fix resources/classpath if not discovered; fix conditions or configuration if the candidate was discovered yet failed to match.