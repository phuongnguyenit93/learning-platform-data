# @ConditionalOnResource: checking classpath or filesystem resources

## 1. Objectives and Context

In Spring Boot Auto Configuration, a configuration sometimes only makes sense if the application **actually has a required resource**: a template file packaged into the JAR, an adapter definition file on the classpath, or a configuration/signal file outside the application on the filesystem. The **@ConditionalOnResource** annotation lets you decide **whether to register a configuration or bean** based on the presence of that resource.

After this lesson, the learner should be able to:

1. Explain when @ConditionalOnResource is evaluated and why it affects bean registration.
2. Write correct paths for the classpath and filesystem paths using the file: prefix.
3. Apply the annotation on @Configuration/@AutoConfiguration or on an individual @Bean method.
4. Understand multi-resource conditions, how checking existence differs from reading/validating content, and the consequences when a file changes after startup.
5. Run a Java 17+ example to verify whether beans are registered or not, and diagnose using the condition report.

Distinguish right from the start: @ConditionalOnResource answers **“does the resource already exist when Spring evaluates the configuration?”**, not “does Spring read and parse the file content correctly?” or “does the file exist at every moment throughout runtime?”.

## 2. Concept and Mechanism

**Annotation:** org.springframework.boot.autoconfigure.condition.ConditionalOnResource, which belongs to Spring Boot (not a core Java or Spring Framework annotation).

Basic usage:

~~~java
@Bean
@ConditionalOnResource(resources = "classpath:demo/ready.flag")
FeatureService featureService() {
    return new FeatureService();
}
~~~

This is an **illustrative method placed inside a @Configuration or @AutoConfiguration class**; FeatureService is an application-defined type.

While processing bean definitions, Spring Boot evaluates the condition using Spring's **ResourceLoader**. It resolves each resource location and checks whether the resource exists. When the condition matches, the configuration/bean definition is accepted for processing; when it does not match, the definition carrying the annotation is skipped.

~~~text
Initialize ApplicationContext
    |
    v
Read configurations and process bean definitions
    |
    v
Encounter @ConditionalOnResource(resources = ...)
    |
    +-- Do all requested resources exist?
          |
          +-- Yes ---> Condition MATCHES ---> Register configuration/bean
          |
          +-- No  ---> Condition DOES NOT MATCH ---> Skip configuration/bean
    |
    v
Instantiate matching beans, resolve dependencies, and complete startup
~~~

Key points:

- **The condition is a bean registration gate.** If it does not match, the conditional bean does not appear in the ApplicationContext.
- **Does not automatically read content.** An existing file that is empty or malformed can still cause the condition to match; the bean creation code must read/validate it itself when needed.
- **Does not automatically watch the filesystem.** Adding/deleting a file after the condition has been evaluated does not automatically register or destroy a running bean. Typically, the ApplicationContext must be re-initialized / the application restarted to re-evaluate.
- **Do not turn the condition into a health check.** A resource existing at startup does not guarantee it will always be readable in the future or that the service using the resource is always available.
- **When multiple resources are required, all of them must exist** for the condition to match (an AND relationship, not OR).

## 3. Syntax and Where to Place the Annotation

### 3.1. On a @Bean method

~~~java
@Configuration(proxyBeanMethods = false)
class ReportConfiguration {
    @Bean
    @ConditionalOnResource(resources = "classpath:reports/default-template.txt")
    ReportRenderer reportRenderer() {
        return new ReportRenderer();
    }
}
~~~

This is an **illustrative configuration pattern**: appropriate Spring imports and the application's ReportRenderer class are required. Only the reportRenderer bean is subject to the condition; other beans in ReportConfiguration (if any) are still evaluated normally.

### 3.2. On a configuration class

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:reports/default-template.txt")
class ReportFeatureConfiguration {
    @Bean
    ReportRenderer reportRenderer() {
        return new ReportRenderer();
    }

    @Bean
    ReportMetrics reportMetrics() {
        return new ReportMetrics();
    }
}
~~~

This is also an **illustrative pattern**, not a standalone Java program. When the resource is missing, **this entire configuration is excluded from registration**, so neither @Bean method in the configuration is registered through this class.

In auto-configuration libraries, placing it on the class is commonly used when **an entire feature** requires the resource; placing it on @Bean is suitable when **only an optional bean** depends on the resource.

### 3.3. Multiple resources in resources

~~~java
@ConditionalOnResource(resources = {
    "classpath:features/schema.json",
    "classpath:features/rules.json"
})
~~~

The condition above only matches when **both schema.json and rules.json** exist. If either is missing, the configuration/bean is excluded. This is **not a list of candidates to pick one from**, nor does it check whether the JSON is valid.

## 4. Distinguishing Classpath and Filesystem Resources

| Location | Typical syntax | Where does the resource actually live? | When should you use it? |
| --- | --- | --- | --- |
| Classpath | classpath:features/ready.flag | Inside directories and JARs on the runtime classpath | Features depending on files packaged with the application or library |
| Linux/macOS filesystem | file:/opt/myapp/config/feature.flag | A file at an absolute path on the host machine | Resources deployed, mounted, or managed outside the JAR |
| Windows filesystem | file:///C:/myapp/config/feature.flag | A file on drive C of the host machine | Same filesystem scenario, using Windows path syntax |
| No prefix | features/ready.flag | Depends on how ResourceLoader/ApplicationContext interprets it | Not recommended for configurations that need a clear distinction between classpath and disk |

**Classpath:** In a typical Maven/Gradle project, a file placed in src/main/resources/features/ready.flag is copied to the output classpath and packaged inside the JAR. When using the annotation:

~~~java
@ConditionalOnResource(resources = "classpath:features/ready.flag")
~~~

Spring looks for **the resource on the runtime classpath**. You should not and must not assume a standalone file exists at the src/main/resources path once the JAR is deployed. A file with the same name could also come from a dependency JAR, so libraries should use sufficiently distinct names/paths to avoid accidental matches due to name collisions.

**Filesystem:** With:

~~~java
@ConditionalOnResource(resources = "file:/opt/myapp/config/feature.flag")
~~~

Spring checks the filesystem path outside the application. That file is **not automatically packaged into the JAR**. On Windows, you can use the syntax file:///C:/myapp/config/feature.flag for an absolute path. Absolute paths are clearer than relative paths, because the working directory when running from an IDE, CI, Docker, systemd, or java -jar can differ.

**Note on notation:** classpath: points to a specific location in this example; file: points to a filesystem resource URL. Do not assume that multi-resource scanning syntax like **classpath*:** or wildcards like **/*.json** are handled by @ConditionalOnResource as a multi-file discovery mechanism. The annotation checks the resource location returned by ResourceLoader; if you want to find and count resources by pattern, you need a ResourcePatternResolver or an appropriate custom condition.

**Deployment comparison table:**

| Scenario | classpath: | file: |
| --- | --- | --- |
| File is packaged inside the application JAR | Suitable | No, unless it is also copied as a separate file on disk |
| Modify an external file outside the JAR and restart | Does not automatically use the external copy | Suitable if pointed to the right path |
| Running inside a container | Depends on the image/JAR contents | Depends on volume/mount and permissions |
| Using the same path across operating systems | Relatively easy thanks to slashes and resource names | Must pay attention to OS path syntax |
| Using the content as a java.io.File | Unsafe when the resource is inside a JAR | Can usually be resolved to a real file, if appropriate |

When you need to **read data from a classpath JAR**, prefer Spring's Resource.getInputStream() instead of Resource.getFile(), because the target may reside inside a JAR and not be a standalone File.

## 5. Runnable Java 17+ Example: Checking Classpath and Registering Beans

The following example provides a minimal Spring Boot application requiring no database or web server. It tests three beans:

- **readyFeature**: created when features/ready.flag is on the classpath.
- **optionalFeature**: created when features/optional.flag is on the classpath.
- **combinedFeature**: created only when both files are present.

### 5.1. Project structure

~~~text
resource-condition-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/resourcecondition/
        │       └── ResourceConditionApplication.java
        └── resources/
            └── features/
                └── ready.flag
~~~

**Do not create features/optional.flag on the first run**.

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>resource-condition-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

The Spring Boot parent manages library versions. spring-boot-starter provides the basic ApplicationContext and auto-configuration; spring-boot-maven-plugin is used to run/package an executable JAR.

### 5.3. ResourceConditionApplication.java

Create the file **src/main/java/com/example/resourcecondition/ResourceConditionApplication.java**:

~~~java
package com.example.resourcecondition;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnResource;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@SpringBootApplication
public class ResourceConditionApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(ResourceConditionApplication.class, args)) {
            System.out.println("readyFeature=" + context.containsBean("readyFeature"));
            System.out.println("optionalFeature=" + context.containsBean("optionalFeature"));
            System.out.println("combinedFeature=" + context.containsBean("combinedFeature"));
        }
    }
}

record FeatureMarker(String source) {
}

@Configuration(proxyBeanMethods = false)
class FeatureConfiguration {
    @Bean
    @ConditionalOnResource(resources = "classpath:features/ready.flag")
    FeatureMarker readyFeature() {
        return new FeatureMarker("ready");
    }

    @Bean
    @ConditionalOnResource(resources = "classpath:features/optional.flag")
    FeatureMarker optionalFeature() {
        return new FeatureMarker("optional");
    }

    @Bean
    @ConditionalOnResource(resources = {
        "classpath:features/ready.flag",
        "classpath:features/optional.flag"
    })
    FeatureMarker combinedFeature() {
        return new FeatureMarker("both");
    }
}
~~~

**Key points to understand in the code:**

1. @SpringBootApplication enables application configuration; FeatureConfiguration is in the same package so it is processed by component scan.
2. @ConditionalOnResource is attached to each @Bean method. No bean is created by a method excluded from registration.
3. context.containsBean("...") checks the **actual** bean name in the ApplicationContext. It does not just check a property value.
4. record FeatureMarker is a Java 17 type used as a demo value; there is no “hidden” mechanism in the bean. The purpose of the example is to observe registration.

### 5.4. Required resource file

Create the file **src/main/resources/features/ready.flag** with the content:

~~~text
present
~~~

The value present **is not parsed by the annotation**; the existence of the file is enough for evaluating the condition. There is no features/optional.flag file on the first run.

### 5.5. Running and results

In the resource-condition-demo directory, using JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

After the Spring Boot logs, the three lines printed by the program are:

~~~text
readyFeature=true
optionalFeature=false
combinedFeature=false
~~~

Explanation for each line:

- ready.flag is on the classpath, so readyFeature is registered.
- optional.flag does not exist yet, so optionalFeature is not registered.
- combinedFeature requires **both ready.flag and optional.flag**; missing optional.flag causes the condition not to match.

Now add the file **src/main/resources/features/optional.flag** (with any content, e.g. present), stop the application, and run the same command again. The three lines become:

~~~text
readyFeature=true
optionalFeature=true
combinedFeature=true
~~~

Deleting both source files and running again will cause all three conditions not to match, resulting in:

~~~text
readyFeature=false
optionalFeature=false
combinedFeature=false
~~~

To verify when running from a packaged JAR:

~~~bash
mvn package
java -jar target/resource-condition-demo-1.0.0.jar
~~~

**Important:** You must rebuild the JAR after adding/removing files in src/main/resources. Editing the source directory directly after packaging **does not** change the classpath inside the already built JAR.

## 6. Checking the Filesystem: Resources Outside the JAR

The next example simulates a marker file placed on the server by an operator. Put the following configuration in the same package as the application (you can create **src/main/java/com/example/resourcecondition/FileFeatureConfiguration.java**):

~~~java
package com.example.resourcecondition;

import org.springframework.boot.autoconfigure.condition.ConditionalOnResource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class FileFeatureConfiguration {
    @Bean
    @ConditionalOnResource(resources = "file:/opt/resource-demo/feature.flag")
    FileFeature fileFeature() {
        return new FileFeature();
    }
}

final class FileFeature {
}
~~~

This is a **complete Java file to add to the sample project**. The path file:/opt/resource-demo/feature.flag is for Linux-like systems. To test on Linux, you can create the file before starting:

~~~bash
mkdir -p /opt/resource-demo
touch /opt/resource-demo/feature.flag
mvn spring-boot:run
~~~

Depending on machine permissions, you may need to choose a different absolute directory that the account running the application has read access to. When the file exists, the fileFeature bean is registered; when the file is missing, the bean is not registered. To verify immediately in the program, add the following line inside the try block in main:

~~~java
System.out.println("fileFeature=" + context.containsBean("fileFeature"));
~~~

This one-line snippet **depends on the context variable from the example in section 5**, not a standalone Java program. With the path present, the corresponding line is fileFeature=true; when absent, it is fileFeature=false.

On Windows, change the annotation string to an appropriate absolute URL, for example:

~~~java
@ConditionalOnResource(resources = "file:///C:/resource-demo/feature.flag")
~~~

and create the file **C:\resource-demo\feature.flag** before running. This is a path change in the annotation, not creating a different bean. If deploying with Docker, the path must exist **inside the container's filesystem**; a file that only exists on the host machine without being mounted into the container will not satisfy the condition.

**Do not confuse with classpath:** Having src/main/resources/features/ready.flag does not mean file:/opt/resource-demo/feature.flag exists. Conversely, mounting a file outside the JAR does not automatically make classpath:features/ready.flag appear.

### 6.1. What happens if the file is deleted after the application is already running?

Suppose at startup file:/opt/resource-demo/feature.flag is present: fileFeature is registered. Later the file is deleted:

- Spring **does not automatically destroy** fileFeature.
- Spring **does not automatically re-evaluate** @ConditionalOnResource to decide whether to register or remove the bean.
- If a method on the bean needs to read the file later, the read operation may fail because the file is gone.

To test the “missing file” branch, restart the ApplicationContext after deleting the file and check the bean name. If the system needs to react immediately to file changes, you must design a dedicated watcher or reload mechanism; @ConditionalOnResource does not replace that mechanism.

## 7. Checking Existence Does Not Mean the File Is Valid

A resource may be present yet:

- Be empty or contain invalid JSON/YAML/XML.
- Be a directory path instead of a file that the program expects to read.
- Be modified/deleted between the time the condition is evaluated and when the bean actually opens the stream to read it.
- Lack read permissions at runtime, or depend on an unstable network/volume.
- Share the same classpath name in another dependency JAR, causing the condition to match unexpectedly.

Therefore, when the content is **actually needed**, validate and handle errors directly in the code that uses the resource. The following example shows a @Bean reading a classpath text file properly:

~~~java
@Bean
@ConditionalOnResource(resources = "classpath:features/message.txt")
String featureMessage(org.springframework.core.io.ResourceLoader loader)
        throws java.io.IOException {
    var resource = loader.getResource("classpath:features/message.txt");
    try (var input = resource.getInputStream()) {
        String content = new String(
                input.readAllBytes(),
                java.nio.charset.StandardCharsets.UTF_8
        ).trim();
        if (content.isEmpty()) {
            throw new IllegalStateException("Message file is empty");
        }
        return content;
    }
}
~~~

This is an **illustrative method to place inside a configuration class**; there is no need to convert a classpath resource into a java.io.File. The condition avoids calling the bean factory method when the resource does not exist; the method must still handle empty content and IOException if the resource has issues.

**Design rule:** If a missing file means the feature should not be enabled, use the condition to skip the bean. If the file is **required** data for the application to function properly, fail fast with a clear configuration error rather than silently disabling a critical component. A condition is only appropriate when the absence of the resource is a designed and validly handled state.

## 8. Using in a Library's Auto-Configuration

The example illustrates a library that only registers a template processor when the module's resource is on the classpath:

~~~java
package com.example.library;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnResource;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnResource(
        resources = "classpath:META-INF/example-library/adapter-template.txt")
public class AdapterAutoConfiguration {
    @Bean
    public AdapterService adapterService() {
        return new AdapterService();
    }
}
~~~

**AdapterService is a class provided by the library** and must exist in the same source; the snippet above illustrates library configuration, not a full standalone project. For Spring Boot 3 to automatically load the library JAR's auto-configuration, register the class name in:

**META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.library.AdapterAutoConfiguration
~~~

When a consuming application adds the library dependency:

- If the resource META-INF/example-library/adapter-template.txt is on the classpath, the configuration class qualifies to provide AdapterService.
- If the resource is absent, the entire AdapterAutoConfiguration is excluded by the condition.
- A resource present on the classpath could also come from **another dependency JAR**; if that is not desired, choose a clearly namespaced path or a condition with additional constraints.

Multiple **AND** conditions can be combined on the same configuration:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.library.AdapterService")
@ConditionalOnResource(
        resources = "classpath:META-INF/example-library/adapter-template.txt")
class AdapterOptionalAutoConfiguration {
    // @Bean methods of the optional module
}
~~~

This is a **configuration illustration** snippet, not a complete class to compile verbatim. Both the class and the resource must match. In a real project, you must still ensure that directly referenced classes are only loaded when the corresponding dependency exists; conditions do not replace dependency management.

## 9. Comparison with Other Spring Boot Conditions

| Annotation | Condition of interest | Target example |
| --- | --- | --- |
| @ConditionalOnResource | Is there a resource at a specified location? | Register template renderer only when the template file exists |
| @ConditionalOnClass | Is a class on the classpath? | Enable adapter when a Java dependency is installed |
| @ConditionalOnProperty | Does a property have a value satisfying the requirement? | Enable feature with feature.enabled=true |
| @ConditionalOnBean | Has a matching bean already been processed? | Create metrics adapter only if the main service exists |
| @ConditionalOnMissingBean | Has no matching bean been processed yet? | Provide a default bean when the user has not configured one |
| @Profile | Does the current Spring profile match? | Create beans only for dev/prod environments |

**Using the right tool:**

- Want to **intentionally toggle on/off** via operational configuration? Usually choose @ConditionalOnProperty.
- Want to check if a **Java library/API** is on the classpath? Choose @ConditionalOnClass.
- Want to check if a **physical file/resource** is available? Choose @ConditionalOnResource.
- Want to decide based on **user-provided beans**? Choose @ConditionalOnBean or @ConditionalOnMissingBean.
- Want to read a configuration file and merge properties into the Spring Environment? Use an appropriate config-loading mechanism like spring.config.import or @PropertySource when suitable; @ConditionalOnResource **does not automatically load properties** from a file.

**Distinguishing example:** feature.audit.enabled=false while classpath:features/audit.flag exists. @ConditionalOnResource on this file can still match because it checks **file existence**, not the feature.audit.enabled property. To require both conditions, you can also place @ConditionalOnProperty on the configuration/bean; the combined condition is AND.

## 10. Common Pitfalls and How to Diagnose

| Symptom | Common cause | Check/fix |
| --- | --- | --- |
| File is in src/main/resources but condition does not match | File was not copied into runtime classpath/JAR, or wrong name/path/casing | Check target/classes, JAR contents, and actual classpath: string |
| Works from IDE, fails when running JAR | Unprefixed path depends on working directory; file is in source tree but not packaged | Use classpath: for packaged resources, absolute file: for external resources |
| file: matches on dev machine but fails in container | File only exists on host; volume is not mounted or path inside container differs | Check filesystem inside container and permissions on target path |
| Resource exists but bean is skipped | Another condition does not match, resource is in wrong location, or annotation is on outer class | Check condition report and where annotations are placed |
| Bean still exists even though file was deleted while app is running | Condition is only evaluated when creating the context, no automatic watcher | Restart context; if dynamic reload is needed, design it separately |
| File exists but bean creation still fails | Resource has invalid/unreadable content; condition does not check schema or parsing | Add clear validation/exception handling in bean code |
| Using classpath*: or wildcards but result is not as expected | @ConditionalOnResource checks specific locations, not a pattern-scanning API | Use specific resource paths or custom Condition + ResourcePatternResolver |
| A condition path works on Linux but not on Windows | Non-portable filesystem URL/path | Use OS-appropriate absolute path, or separate conditional configurations |

### 10.1. Enable the Condition Evaluation Report

In the sample Maven project, you can run:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Or with the packaged JAR:

~~~bash
java -jar target/resource-condition-demo-1.0.0.jar --debug
~~~

Spring Boot can output a **Condition Evaluation Report** helping distinguish matching and non-matching conditions, including the reason for a missing resource if the configuration item is included in the report. Depending on logging levels and how the application is started, specific details may be presented differently. Do not guess solely from a bean's absence; read both the condition info and other conditions on the class/method.

### 10.2. Checking a resource with ResourceLoader directly

When you need to diagnose a path, you can use the following snippet inside a bean/service that already has a ResourceLoader:

~~~java
var resource =
        resourceLoader.getResource("classpath:features/ready.flag");
System.out.println(resource.exists());
~~~

This is an **illustrative snippet**; the resourceLoader variable must be injected or declared beforehand. ResourceLoader resolves the location according to Spring; do not replace it directly with Files.exists(Path.of("src/main/resources/...")) because that is a path **in the source tree**, which is not necessarily present when running from a JAR.

## 11. Real-World Scenarios: Choosing the Right Design

**Scenario A: plugin using an optional template.** If you want to register a plugin only when its template file is packaged with the dependency, classpath: with @ConditionalOnResource fits well. If the template is absent, code calling the plugin must also tolerate the missing bean; otherwise startup will fail due to a missing dependency.

**Scenario B: application with a license/config file mounted into the container by ops.** If a missing file means an **optional** feature should be disabled, you can use file: and the condition. If the file is a **mandatory** requirement for the application to function, failing fast with a clear configuration error is better. Verify the file path inside the container, not just on the host.

**Scenario C: intentional toggle configuration while the resource is always present.** Checking only the resource cannot replace a flag; choose @ConditionalOnProperty or combine property and resource.

**Scenario D: needing to react when a file appears while the app is running.** @ConditionalOnResource does not automatically alter the bean graph after startup. You can design a dedicated watcher, refresh, or application-managed state; do not confuse a startup condition with a dynamic feature toggle.

## 12. Self-Assessment Questions

**Q1.** The project has src/main/resources/features/a.flag, but the JAR was built before the file was added. Is @ConditionalOnResource(resources = "classpath:features/a.flag") guaranteed to match when running the old JAR?  
**Answer:** No. The runtime classpath of the old JAR does not automatically update with the source tree; you must rebuild the artifact containing the file.

**Q2.** The annotation requires resources = {"classpath:a.txt", "classpath:b.txt"}. Only a.txt exists. Does the condition match?  
**Answer:** No. Every resource in the list must exist.

**Q3.** @ConditionalOnResource is placed on a @Configuration class and the file is missing. Are the two @Beans inside the class registered?  
**Answer:** Not through that configuration class, because the entire class is excluded by the condition.

**Q4.** The file contains syntactically invalid JSON, but the path exists. Does @ConditionalOnResource reliably exclude the bean?  
**Answer:** No. It only checks existence, not JSON parsing; the bean creation/reading logic must validate and report errors if needed.

**Q5.** The file was created on the host machine, but the app running in a container still reports the condition as false. What should you check?  
**Answer:** Check whether the file is mounted into the container, whether the file: path inside the container is correct, and whether the account running the app has access permissions.

**Q6.** A bean has been created, and then the file that made the condition match is deleted. Does the bean disappear automatically?  
**Answer:** No. @ConditionalOnResource is evaluated during context creation and does not auto-reload after runtime changes.

**Q7.** The goal is to toggle a feature via application.properties even though the file is always inside the JAR. What should you use?  
**Answer:** @ConditionalOnProperty, or combine them if both the flag and the file are needed. @ConditionalOnResource alone does not check the toggle intent of a property.

## 13. Key Takeaways and Reference Documentation

- **classpath:** checks resources on the runtime classpath, usually packaged from src/main/resources or located inside dependency JARs.
- **file:** checks resources on the filesystem, and must use a path valid where the program actually runs.
- **@ConditionalOnResource** decides configuration/@Bean registration **based on resource existence**, without validating content or monitoring the file throughout runtime.
- **Multiple resources = all must be present.** If one resource is missing, the condition does not match.
- **Two-step diagnosis:** verify the resource location in the runtime environment, then inspect the Condition Evaluation Report and all related conditions.

Official documentation for further reference:

- Spring Boot, ConditionalOnResource API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnResource.html
- Spring Framework, Resources and ResourceLoader: https://docs.spring.io/spring-framework/reference/core/resources.html
- Spring Boot Reference, Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
