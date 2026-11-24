# Fully Qualified Class Names, One Candidate per Line, and Comment Rules in AutoConfiguration.imports

## 1. Purpose of the Imports File in Spring Boot

In Spring Boot 3.x, a library can publish **candidate auto-configuration classes** so that an application using the library has them automatically discovered by Spring Boot. The candidate list resides in a text resource with a **fixed path and filename** on the classpath:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

This file can reside in **src/main/resources** when writing a library; after packaging, it must appear at the exact path above inside the JAR. When the application starts and enables auto-configuration, Spring Boot collects the corresponding imports resources present on the classpath, reads the candidate class names, and processes them as auto-configurations.

**Three core rules for the file content:**

1. **Each configuration line is a fully qualified class name** (*fully qualified class name*, abbreviated FQCN), including the package and the Java class name.
2. **Each line declares only one candidate**; do not group multiple class names with commas, semicolons, or YAML/JSON notation.
3. **Lines starting with `#` are comments**; blank lines are used to separate sections for readability. Comments should be placed on their own line with `#` at the start of the line; do not use inline trailing comments like **ClassName # explanation**.

The imports file answers the question **"Which auto-configuration classes should Spring Boot consider?"**. It does not guarantee that every class in the list creates a bean: conditions on the class, `@Bean` methods, and the application environment are still evaluated by Spring before deciding whether to register beans.

## 2. What Is a Fully Qualified Class Name (FQCN)?

In Java, a fully qualified class name consists of **package + dot + class name**, for example:

~~~java
package com.example.greeting.autoconfigure;

public class GreetingAutoConfiguration {
}
~~~

The FQCN of the class above is:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
~~~

Comparison:

| Syntax | Valid as an imports line? | Reason |
| --- | --- | --- |
| **com.example.greeting.autoconfigure.GreetingAutoConfiguration** | Yes | Complete package and class name. |
| **GreetingAutoConfiguration** | No | Simple class name only; Boot cannot infer the package. |
| **com.example.greeting.autoconfigure** | No | Package only, not a class. |
| **com.example.greeting.autoconfigure.\*** | No | Imports does not accept wildcard package scanning. |
| **com.example.greeting.autoconfigure.GreetingAutoConfiguration.class** | No | This resembles a Java class literal notation, not the class's FQCN. |
| **@AutoConfiguration(GreetingAutoConfiguration.class)** | No | This is not imports file syntax. |

**The FQCN must match the compiled class exactly.** If you rename or move the class to a different package, you must update the imports line. A single-character mismatch can cause candidate importing to fail when Boot attempts to load the configuration.

For **nested classes** registered as candidates, the corresponding binary name must be used; in the case of a normal nested class, `$` separates the outer and inner class, for example **com.example.autoconfig.Outer$Nested**. To avoid mistakes and keep packages clear, a new library is usually easier to maintain when each public auto-configuration class is a top-level class.

## 3. One Line Corresponds to One Candidate

A library can provide multiple auto-configurations. Each class is listed on **its own line**, for example:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
com.example.greeting.autoconfigure.GreetingMetadataAutoConfiguration
~~~

The lines above publish **two independent candidates**. During startup, Spring Boot may apply both, only one, or neither, depending on each configuration's conditions. Listing both does not prove their beans exist.

### Incorrect Formats to Recognize

**Wrong — comma-separated:**

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration,com.example.greeting.autoconfigure.GreetingMetadataAutoConfiguration
~~~

This is still **one line**, not two valid classes. Spring Boot will not interpret the comma here as syntax separating a candidate list.

**Wrong — adding labels or colons like property configuration:**

~~~text
autoConfigurations:
  - com.example.greeting.autoconfigure.GreetingAutoConfiguration
~~~

The imports file is neither YAML nor a **.properties** file with an **autoConfigurations** key.

**Wrong — putting Java statements into the file:**

~~~text
import com.example.greeting.autoconfigure.GreetingAutoConfiguration;
~~~

The **import** keyword and semicolon belong to **.java** file syntax, not **AutoConfiguration.imports**.

**Right — bare class names, one per line:**

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
com.example.greeting.autoconfigure.GreetingMetadataAutoConfiguration
~~~

Each name must point to an actual class in the library's JAR or on the classpath supported by the library. Do not declare the same class repeatedly just to “increase priority”.

## 4. Comment and Blank Line Rules

You can insert **full-line comments starting with `#`** to explain groups of configurations or note the purpose of each class. Blank lines help group entries by responsibility:

~~~text
# Default greeting service configuration
com.example.greeting.autoconfigure.GreetingAutoConfiguration

# Module metadata configuration
com.example.greeting.autoconfigure.GreetingMetadataAutoConfiguration
~~~

This is valid content: the two **#...** lines are treated as comments, the blank line does not represent a candidate, and the two FQCN lines are the two candidates to consider. Using accented Vietnamese in comments when the file is saved as UTF-8 is also valid; the example uses ASCII letters so tools display consistently across environments.

### What Not to Assume About Comment Syntax

- **`#` at the start of the line** is the documented, clear, and safe form. Do not rely on a parser possibly trimming leading whitespace before `#` in a specific Boot version; when writing, put `#` at column 1.
- **Do not place comments after an FQCN on the same line**. For example, **com.example.FooAutoConfiguration # foo** is not the documented form of a candidate and may be treated as an invalid class name.
- **Do not use `//` or `/* ... */`** out of Java habit as comment markers. The imports format rule is lines starting with `#`.
- **Do not put quotes** around the FQCN and do not add a trailing `;`.
- **Do not use comment lines to disable conditions inside a class**. Commenting out an FQCN line removes that class from being listed as a candidate from that file; by itself it does not alter the class code or auto-configurations provided by other JARs.

Create the file as **UTF-8 plain text**, keeping the exact filename and path, with one FQCN per line. Do not add a BOM or decorative content at the top of the file: unexpected characters can corrupt the first candidate name. A trailing blank line at the end of the file normally causes no issues.

## 5. File Location and Packaging into the JAR

With a standard Java/Gradle library:

~~~text
greeting-autoconfigure/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/greeting/
    │   │       ├── GreetingService.java
    │   │       ├── GreetingMetadata.java
    │   │       └── autoconfigure/
    │   │           ├── GreetingAutoConfiguration.java
    │   │           └── GreetingMetadataAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/consumer/
            └── GreetingDiscoveryTest.java
~~~

**Pay attention to directory names and letter casing**: **META-INF** is the parent directory, inside it is **spring**, and the filename contains the full string **org.springframework.boot.autoconfigure.AutoConfiguration.imports**. The file has no **.java** or **.txt** suffix. Do not place it in **src/test/resources** if you want it packaged into the library's main JAR.

When using the default resource structure of the **java** or **java-library** plugin in Gradle, **src/main/resources** resources are included in the JAR via the resource processing and jar tasks. If the build customizes source sets or resources, you must verify the artifact contents instead of only seeing the file in the source tree.

### 5.1. Difference Between Class Code and the Name Appearing in Imports

The **.java** file defines the actual class. The **.imports** file contains the *name* of the class for the framework to find and evaluate. Merely adding a name to the file does not cause the class to be generated, compiled, or have bytecode created.

Therefore, if there is a line:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
~~~

then at build time there must be corresponding class bytecode:

~~~text
com/example/greeting/autoconfigure/GreetingAutoConfiguration.class
~~~

The package/class names must match. If the source changed packages without updating imports, this error may only surface in another application during auto-configuration discovery.

## 6. Complete Example: Two Candidate Auto-Configurations in One JAR

To avoid only reading syntax in theory, let's build a small library with **two independent `@AutoConfiguration` classes**, one providing **GreetingService** and one providing **GreetingMetadata**. They are listed as two FQCN lines and discovered when a Spring Boot application enables auto-configuration.

The example uses **Java 21, Gradle 8.x, Spring Boot 3.3.13**. These are the specific versions for this exercise, not a claim about the latest versions. The program needs to download dependencies from Maven Central on the first run.

### 6.1. settings.gradle File

~~~groovy
rootProject.name = 'greeting-autoconfigure'
~~~

### 6.2. build.gradle File

~~~groovy
plugins {
    id 'java-library'
}

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

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Explanation:** the module is a library JAR so it only needs the **java-library** plugin; no Spring Boot executable bootJar is required. The BOM manages versions for Spring Boot and corresponding dependencies. **spring-boot-autoconfigure** provides **@AutoConfiguration** and conditions; JUnit and Spring Boot test support verifying candidates in a context.

### 6.3. Public API: GreetingService

File **src/main/java/com/example/greeting/GreetingService.java**:

~~~java
package com.example.greeting;

public final class GreetingService {

    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

### 6.4. Public API: GreetingMetadata

File **src/main/java/com/example/greeting/GreetingMetadata.java**:

~~~java
package com.example.greeting;

public record GreetingMetadata(String moduleName) {
}
~~~

This is a Java 21 record storing a module name to provide a second independent bean illustrating how **two** candidates are declared.

### 6.5. Candidate #1: GreetingAutoConfiguration

File **src/main/java/com/example/greeting/autoconfigure/GreetingAutoConfiguration.java**:

~~~java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new GreetingService();
    }
}
~~~

**@ConditionalOnMissingBean** lets the application provide its own GreetingService so the auto-configuration does not register an extra default bean. This condition lives entirely in the Java class; the imports line contains no conditional syntax.

### 6.6. Candidate #2: GreetingMetadataAutoConfiguration

File **src/main/java/com/example/greeting/autoconfigure/GreetingMetadataAutoConfiguration.java**:

~~~java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingMetadata;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class GreetingMetadataAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingMetadata.class)
    public GreetingMetadata greetingMetadata() {
        return new GreetingMetadata("greeting");
    }
}
~~~

### 6.7. AutoConfiguration.imports File

File **src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** contains:

~~~text
# Greeting service configuration
com.example.greeting.autoconfigure.GreetingAutoConfiguration

# Module metadata configuration
com.example.greeting.autoconfigure.GreetingMetadataAutoConfiguration
~~~

The two FQCN lines are explained as follows:

| Line | Meaning |
| --- | --- |
| **# Greeting service configuration** | Comment; not loaded as a class. |
| **com.example.greeting.autoconfigure.GreetingAutoConfiguration** | First candidate. |
| Blank line | Grouping separator, creates no candidate. |
| **# Module metadata configuration** | Comment; not a class. |
| **com.example.greeting.autoconfigure.GreetingMetadataAutoConfiguration** | Second candidate. |

**Do not add** **com.example.greeting.GreetingService** or **GreetingMetadata** to imports. Those two classes are data/bean types created by configuration, not auto-configuration classes to register as candidates.

## 7. Testing Spring Boot Auto-Discovery of Both Candidates

To confirm the imports file is read by Spring Boot, use a test application in **a different package**: **com.example.consumer**. The test enables **@EnableAutoConfiguration** and does not use **@Import** to list the two configuration classes directly.

File **src/test/java/com/example/consumer/GreetingDiscoveryTest.java**:

~~~java
package com.example.consumer;

import com.example.greeting.GreetingMetadata;
import com.example.greeting.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = GreetingDiscoveryTest.TestApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class GreetingDiscoveryTest {

    @Autowired
    ApplicationContext context;

    @Test
    void discoversBothCandidatesFromImports() {
        assertThat(context.getBeansOfType(GreetingService.class))
            .hasSize(1);
        assertThat(context.getBeansOfType(GreetingMetadata.class))
            .hasSize(1);

        assertThat(
            context.getBean(GreetingService.class).greet("Mai")
        ).isEqualTo("Xin chào, Mai!");

        assertThat(
            context.getBean(GreetingMetadata.class).moduleName()
        ).isEqualTo("greeting");
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {
    }
}
~~~

Run from the project root directory:

~~~bash
gradle test
~~~

If a Gradle Wrapper was created, you can use **./gradlew test** on macOS/Linux or **.\gradlew.bat test** on Windows. Gradle runs the tests and reports task status; there is no single fixed stdout to memorize.

**Why is this test valuable?** The configuration classes are registered via the imports resource on the test runtime classpath. Because the test application does not directly **@Import(GreetingAutoConfiguration.class)**, a passing test helps prove that the **discovery and condition** mechanism works together. Placing the test application in a different package reduces the chance of configurations being discovered accidentally via component scanning.

**Limitation:** The test runs on the project classpath, where **src/main/resources** already participates in resource processing; it does not prove the file is properly included inside the **published JAR**. Therefore, the next JAR verification step is mandatory when providing a library to other projects.

### 7.1. Try Removing One Imports Line to Observe the Impact

In a separate practice branch, comment out only the second line:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
# com.example.greeting.autoconfigure.GreetingMetadataAutoConfiguration
~~~

When re-running the discovery test (with no Metadata bean provided from another source), the assertion for **GreetingMetadata** will fail, while GreetingService can still be created. This clearly shows that **commenting out a candidate line** removes that class from the discovery list of this file, without modifying the Java class or deleting its bytecode. Restore the valid imports after the experiment.

## 8. Inspecting the Exact Resource Inside the JAR

Package the library with the **jar** task:

~~~bash
gradle jar
~~~

Because build.gradle sets version **1.0.0**, the standard artifact is:

~~~text
build/libs/greeting-autoconfigure-1.0.0.jar
~~~

Check entries:

~~~bash
jar tf build/libs/greeting-autoconfigure-1.0.0.jar
~~~

The list must include:

~~~text
com/example/greeting/autoconfigure/GreetingAutoConfiguration.class
com/example/greeting/autoconfigure/GreetingMetadataAutoConfiguration.class
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

**jar tf** only confirms the file is present. To be sure its contents were not packaged differently from source, open the **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** entry in the JAR using a ZIP/JAR reader tool and cross-check the exact FQCN lines against the built classes. With the **unzip** command on systems that have this tool:

~~~bash
unzip -p build/libs/greeting-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The content must include the two FQCN lines and the comment lines written, preserving the order from the resource. Not every Windows system has **unzip**; when unavailable, use an equivalent ZIP/JAR inspection tool.

**Evidence checkpoints to retain:** the file exists at the proper source path, bytecode for each class exists in the JAR, the resource contents after packaging match the exact class names, and the discovery test passes. Each checkpoint addresses a different class of error.

## 9. At Which Step Does Imports Participate in Candidate Selection?

Distinguish between **finding candidates** and **applying conditions**:

~~~text
Application enables auto-configuration
            |
            v
Spring Boot locates AutoConfiguration.imports
on the runtime classpath
            |
            v
Reads FQCNs, skips blank lines and # comment lines
            |
            v
Produces the list of candidate auto-configuration classes
            |
            v
Applies selection/filtering, ordering, and condition evaluation
            |
      +-----+------+
      |            |
    Match       No match
      |            |
      v            v
Apply matching   Skip config/bean
configuration    failing conditions
~~~

The imports file has no **enabled** column, **priority** column, or **ConditionalOnClass** expression. Those factors are expressed through code annotations or corresponding Spring Boot configuration mechanisms.

### 9.1. Is the Order of Lines the Bean Initialization Order?

**Do not treat line order in imports as a contract for bean creation order.** Spring Boot has its own auto-configuration ordering mechanism. When ordering relationships must be declared, use class-level metadata such as **@AutoConfiguration(before = ...)**, **@AutoConfiguration(after = ...)**, or mechanisms supported by Boot. Changing line order just to force bean registration order is a fragile approach.

### 9.2. What If Two JARs Both Have an Imports File?

Each library can package **a resource with the same path** in its own JAR. Spring Boot collects candidate lists from those resources on the classpath. Developers do not need to merge all FQCNs from every starter into a single file in the application.

However, creating a **fat JAR or shaded JAR** with custom tooling can accidentally overwrite same-named resources instead of preserving/merging their contents. If building a library packaged that way, you must inspect the final resource and run real discovery tests; do not rely solely on the file in the source module.

### 9.3. How Does Imports Differ from Component Scanning?

A class outside the application's component scanning scope can still become an auto-configuration candidate thanks to the imports file. This allows a library to provide auto-configuration without requiring users to add **@ComponentScan("com.example.greeting")**.

You should also avoid marking every ordinary class with **@Component** and placing them in imports as a replacement for component scanning. This list is meant for **auto-configuration classes**; library beans should be registered intentionally via **@Bean**, importing appropriate configurations, or Boot-supported mechanisms.

## 10. Common Errors When Authoring Imports

| Symptom | Possible Cause | How to Check/Fix |
| --- | --- | --- |
| Library configuration not found | Wrong filename/path, placed in test resources, not packaged | Run **jar tf**, verify exact path inside JAR. |
| Error loading class name | Wrote simple name, wrong package, wrong letter casing, or added **;** | Compare FQCN against package/class and bytecode in JAR. |
| Two classes on the same line | Used comma/semicolon to separate | Split into **two independent lines**. |
| A comment treated as a class name | Used **//**, inline trailing comment, or unsupported marker | Use **#** at the start of a dedicated line. |
| Class exists yet Boot does not consider it | Missing FQCN line or line is commented out | Read the imports entry in the actual JAR. |
| Candidate considered yet bean is missing | **@ConditionalOnMissingBean**, **@ConditionalOnProperty**, or other condition did not match | Enable **--debug** and read the Condition Evaluation Report. |
| Direct @Import test passes yet consumer sees no bean | Test bypassed imports discovery step | Create a test with **@EnableAutoConfiguration** without direct import; inspect the JAR. |
| Errors after renaming a class | Updated Java class but forgot FQCN in imports | Fix the resource, rebuild the JAR, and run tests. |
| Shaded build drops candidates | Same-named resources across JARs overwritten | Inspect final artifact and resource handling strategy. |

### Distinguishing File Syntax Errors from Condition Errors

A class **not appearing in the candidate list** usually leads us to check resources/classpath first. A class **that is discovered yet creates no bean** requires checking conditions instead. Adding beans directly to “patch” either error can mask the real underlying problem.

You can run a Spring Boot application with the argument:

~~~bash
java -jar app.jar --debug
~~~

The condition evaluation report helps find why a candidate/configuration was applied or excluded once the application loaded the relevant configuration. Combine this with JAR content inspection to accurately diagnose errors in the discovery step.

## 11. Safe Workflow for Creating Imports When Developing a Library

1. **Write the auto-configuration class** with a clear package and **@AutoConfiguration** annotation; use **@Bean** and appropriate conditions.
2. **Take the FQCN from the exact package + class name**; never guess from directory names if sources were refactored.
3. **Create the resource at the standard path** **src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**.
4. **Write one class per line**, without commas, quotes, semicolons, or the **import** keyword.
5. **Place comments on their own line starting with `#`** if explanations are needed; do not invent custom comment syntax.
6. **Compile and package the JAR**, verifying all class bytecode and the imports entry are present.
7. **Inspect the resource contents inside the artifact** to confirm the FQCNs remain accurate.
8. **Run the application/discovery test without direct @Import**, then inspect actual beans and the condition report if results differ from expectations.
9. **Add this verification to CI** to catch issues when renaming packages, renaming classes, or changing packaging pipelines.

This workflow is compact enough for small libraries and still applies when a JAR contains multiple candidates. The key point is that **correct syntax is not enough; the artifact must be right and runtime must actually auto-discover the classes**.

## 12. Self-Check Questions

**Question 1.** A line in imports reads **GreetingAutoConfiguration**. What is wrong?

*Answer:* missing package. Must write the FQCN, e.g., **com.example.greeting.autoconfigure.GreetingAutoConfiguration**.

**Question 2.** To register three candidates, can they be comma-separated on a single line?

*Answer:* no. Three separate FQCN lines must be used.

**Question 3.** Does the line **# com.example.XAutoConfiguration** cause X to be loaded as a candidate from that file?

*Answer:* no. That is a full-line comment.

**Question 4.** A file has two valid FQCNs. Is Spring Boot guaranteed to create beans from both classes?

*Answer:* no. The file only publishes candidates; conditions on the classes/beans and the environment still decide.

**Question 5.** A test using **AutoConfigurations.of(XAutoConfiguration.class)** passes. Does that prove imports in the JAR is accurate?

*Answer:* not yet. That test adds the class directly into the context, which can bypass resource-based discovery. You need to inspect the JAR and run a consumer/test using **@EnableAutoConfiguration**.

**Question 6.** A library has the right imports file in **src/test/resources**, yet a consuming application does not see the auto-configuration. Why?

*Answer:* test resources are normally not packaged into the main library JAR. Place the file in **src/main/resources** and inspect the artifact.

**Question 7.** What error occurs when moving an auto-configuration to a new package without updating imports?

*Answer:* the resource continues pointing to the old FQCN that is no longer valid; Boot may fail to load the candidate class. Fix the resource and re-run discovery verification.

## Conclusion

In Spring Boot 3.x, **AutoConfiguration.imports is a plain-text list of candidate auto-configuration classes**. The most important formatting rules are **exact FQCN, one class per line, full-line comments starting with `#`**, and packaging the resource properly at **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**.

From that list, Spring Boot proceeds to selection and condition evaluation. Therefore, to be confident a library auto-configures properly, verify all three parts: **the file content is right**, **the JAR has the file and classes**, and **the consuming application auto-discovers the configuration and creates beans according to conditions**.
