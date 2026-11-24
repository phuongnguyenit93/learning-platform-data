# ImportCandidates and Reading Resources from JARs on the Classpath

> **Context:** Spring Boot → auto-configuration → candidate discovery. This lesson explains the `ImportCandidates` class, the `.imports` file format, how the class loader finds **multiple resources at the same path** across JARs on the classpath, and the steps that happen **after** the candidate list is obtained. Examples use Java 17, Maven, and Spring Boot 3.5.7; details involving Spring Boot internals may vary in other versions.

## 1. Foundational Question: Where Does Spring Boot Find Auto-Configurations?

Suppose an application depends on:

- `spring-boot-autoconfigure.jar`: carrying Spring Boot's standard configurations;
- `alpha-autoconfigure.jar`: carrying configuration for the Alpha library;
- `beta-autoconfigure.jar`: carrying configuration for the Beta library.

All three JARs can contain a resource with the **exact same path**:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each resource is a text file with the **fully qualified class names** of the auto-configurations contributed by that JAR:

```text
# An imports resource provided by the Alpha library
dev.sample.alpha.AlphaAutoConfiguration
```

```text
# Another imports resource provided by the Beta library
dev.sample.beta.BetaAutoConfiguration
```

Spring Boot does not read just a single file from the application and ignore same-named files in dependency JARs. It can collect imports files **from all relevant classpath roots/JARs**, combine the candidate list, and proceed to filtering, ordering, and condition evaluation.

A class in `dev.sample.alpha` can become a candidate even if the `@SpringBootApplication` class resides in `dev.sample.app`. Finding auto-configuration candidates relies on **resource metadata** and the class loader, **not the application's `@ComponentScan`**.

## 2. What Is `ImportCandidates`?

The Spring Boot class:

```java
org.springframework.boot.context.annotation.ImportCandidates
```

provides the primary API:

```java
public static ImportCandidates load(
    Class<?> annotation,
    ClassLoader classLoader
);
```

This is an **illustrative API signature**, not a method written by the application. An `ImportCandidates` object implements `Iterable<String>`, and `getCandidates()` returns `List<String>`. The elements are candidate **class names**, not created beans and not instances of the auto-configurations.

The API documentation defines the resource path convention:

```text
META-INF/spring/<fully-qualified-annotation-class-name>.imports
```

In the case of `AutoConfiguration.class`, the exact path is:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

For example, a learner could call:

```java
List<String> names = ImportCandidates
    .load(AutoConfiguration.class, getClass().getClassLoader())
    .getCandidates();
```

This snippet is an **illustrative fragment**; it requires importing `java.util.List`, `ImportCandidates`, `AutoConfiguration`, and a method context with `getClass()`. The full Maven example in section 5 uses an equivalent call in a runnable program.

### Meaning of the `annotation` Parameter

This parameter identifies **which imports filename to look for**. It is not a package to scan and does not require scanning the entire classpath to discover annotations on every class.

- `ImportCandidates.load(AutoConfiguration.class, loader)` looks for `.../AutoConfiguration.imports`.
- A different annotation leads to **a different filename**. If libraries do not provide a file under that name, the discovered list may be empty.
- `@ImportAutoConfiguration` has cases where it uses its own imports mechanism for specified configurations, especially in tests; do not confuse that path with the general auto-configuration list.

### Meaning of the `classLoader` Parameter

The class loader is responsible for locating resources on the process's actual classpath. It can see resources in:

- `target/classes/META-INF/spring/...` when running a module from Maven/IDE;
- the resource root of dependency JARs;
- nested JARs under `BOOT-INF/lib/` of a Spring Boot executable JAR when using the class loader provided by the Spring Boot launcher.

A resource does not need to be a physical file easily opened directly with `java.io.File`. Inside an executable JAR, a resource URL may have a representation specific to nested JARs; read through the class loader, `URL.openStream()`, or Spring APIs instead of manually slicing a path string.

## 3. Why Must Multiple Same-Named Resources Be Read?

The Java APIs:

```java
ClassLoader.getResource(String name)
ClassLoader.getResources(String name)
```

behave differently:

| API | Result | When Appropriate? |
| --- | --- | --- |
| `getResource(name)` | A single `URL` or `null` | You intentionally want one resource according to class loader search order. |
| `getResources(name)` | `Enumeration<URL>` of discovered resources | When **multiple JARs can contribute the same resource path** and all must be traversed. |
| `ImportCandidates.load(annotation, loader)` | Candidate class names from the corresponding imports resources | When you need the mechanism for reading import candidates per Spring Boot's convention. |

If you write custom auto-configuration discovery code and only call `getResource(...)`, the program might see a file from JAR A while **missing** the file in JAR B. That bug is hard to catch when running in an IDE with few dependencies and only surfaces when packaging additional starters.

A standalone standard Java example, with no Spring Boot dependencies, to observe available resource URLs:

```java
import java.net.URL;
import java.util.Collections;
import java.util.List;

public class ListResourceUrls {
    public static void main(String[] args) throws Exception {
        String name = "META-INF/MANIFEST.MF";
        ClassLoader loader = ListResourceUrls.class.getClassLoader();
        List<URL> urls = Collections.list(loader.getResources(name));
        System.out.println("resourceCount=" + urls.size());
        for (URL url : urls) {
            System.out.println(url);
        }
    }
}
```

Run with JDK 17:

```bash
javac ListResourceUrls.java
java ListResourceUrls
```

The URLs and total resource count **depend on the classpath**, so this lesson does not invent a fixed stdout. The example simply shows how to convert `Enumeration<URL>` into `List<URL>` and iterate through all of them.

Spring Boot relies on the imports convention to read class names; across different Boot versions, internal implementation details may be optimized or changed. What matters architecturally is that **a single classpath can contain multiple files at the same path**, and every properly formatted contribution must be considered.

## 4. Format and Rules of the `.imports` File

The exact path when publishing an auto-configuration:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Rules:

1. Write the **fully qualified class name** including package, one name per line.
2. Lines starting with `#` can be used as comments.
3. Do not use wildcard package names like `dev.sample.autoconfigure.*`; Boot needs concrete class names.
4. The resource path must be exact, including letter casing and the `.imports` extension.
5. The declared class is normally annotated with `@AutoConfiguration` and placed in a separate package so component scan does not pick it up accidentally.
6. A library with two configurations lists two lines; other JARs can have their own files **at the same path**.

Example:

```text
# Client integrations
com.acme.payment.autoconfigure.PaymentAutoConfiguration
com.acme.payment.autoconfigure.PaymentMetricsAutoConfiguration
```

A line in the file **does not execute the class**; it only puts the class name into candidate discovery. Whether the class is actually imported and whether beans exist is a matter for **later steps**.

### Packaging Notes

Maven/Gradle normally place files under `src/main/resources` onto the artifact's classpath. In a standard Maven JAR, the resource appears at the JAR root:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

In a Spring Boot executable JAR, application classes/resources reside under `BOOT-INF/classes/`, while dependency JARs normally reside under `BOOT-INF/lib/`. The Boot launcher builds an appropriate class loader so the program sees these resources. Do not apply a “resource must exist at a current filesystem path” assumption to inspect a nested JAR.

When creating an autoconfigure library, keep the artifact as a **standard library JAR**; only the application module needs the repackaging plugin to produce an executable JAR.

## 5. Runnable Example: Two JARs Providing Two Imports Files

To clearly see candidates merged from multiple JARs, let's create a three-module Maven reactor: two **library JARs** and one **application**.

```text
candidate-demo/
├── pom.xml
├── alpha-autoconfigure/
│   ├── pom.xml
│   └── src/main/
│       ├── java/dev/sample/alpha/AlphaAutoConfiguration.java
│       └── resources/META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
├── beta-autoconfigure/
│   ├── pom.xml
│   └── src/main/
│       ├── java/dev/sample/beta/BetaAutoConfiguration.java
│       └── resources/META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── app/
    ├── pom.xml
    └── src/
        ├── main/java/dev/sample/app/CandidateApplication.java
        └── test/java/dev/sample/app/
            ├── ImportCandidatesTest.java
            └── ExcludedBetaTest.java
```

### 5.1. Root POM (Aggregator/Parent)

`candidate-demo/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>dev.sample</groupId>
    <artifactId>candidate-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <modules>
        <module>alpha-autoconfigure</module>
        <module>beta-autoconfigure</module>
        <module>app</module>
    </modules>
    <properties>
        <java.version>17</java.version>
    </properties>
</project>
```

The root uses `packaging=pom` so Maven builds modules in dependency order.

### 5.2. Alpha Module

`alpha-autoconfigure/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.sample</groupId>
        <artifactId>candidate-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>alpha-autoconfigure</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
    </dependencies>
</project>
```

`alpha-autoconfigure/src/main/java/dev/sample/alpha/AlphaAutoConfiguration.java`:

```java
package dev.sample.alpha;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AlphaAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(name = "alphaGreeting")
    public String alphaGreeting() {
        return "from-alpha-jar";
    }
}
```

Create file `alpha-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
# Auto-configuration provided by alpha-autoconfigure.jar
dev.sample.alpha.AlphaAutoConfiguration
```

### 5.3. Beta Module

`beta-autoconfigure/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.sample</groupId>
        <artifactId>candidate-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>beta-autoconfigure</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
    </dependencies>
</project>
```

`beta-autoconfigure/src/main/java/dev/sample/beta/BetaAutoConfiguration.java`:

```java
package dev.sample.beta;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class BetaAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(name = "betaGreeting")
    public String betaGreeting() {
        return "from-beta-jar";
    }
}
```

Create file `beta-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
# Auto-configuration provided by beta-autoconfigure.jar
dev.sample.beta.BetaAutoConfiguration
```

These two modules are **plain JARs** because they do not declare `spring-boot-maven-plugin` to repackage, whereas the application module will have that plugin.

### 5.4. Application Module and Two Dependencies

`app/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.sample</groupId>
        <artifactId>candidate-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>app</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>dev.sample</groupId>
            <artifactId>alpha-autoconfigure</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>dev.sample</groupId>
            <artifactId>beta-autoconfigure</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
```

### 5.5. Reading Candidates with `ImportCandidates` and `ClassLoader.getResources`

`app/src/main/java/dev/sample/app/CandidateApplication.java`:

```java
package dev.sample.app;

import java.net.URL;
import java.util.Collections;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.annotation.ImportCandidates;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class CandidateApplication {

    private static final String IMPORTS_PATH =
        "META-INF/spring/"
        + "org.springframework.boot.autoconfigure.AutoConfiguration.imports";

    public static void main(String[] args) throws Exception {
        ClassLoader loader = CandidateApplication.class.getClassLoader();

        List<URL> resources =
            Collections.list(loader.getResources(IMPORTS_PATH));

        List<String> demoCandidates = ImportCandidates
            .load(AutoConfiguration.class, loader)
            .getCandidates()
            .stream()
            .filter(name -> name.startsWith("dev.sample."))
            .distinct()
            .sorted()
            .toList();

        try (ConfigurableApplicationContext context =
                 SpringApplication.run(CandidateApplication.class, args)) {

            System.out.println("imports.multiple=" + (resources.size() >= 2));
            System.out.println(
                "candidates=" + String.join(",", demoCandidates)
            );
            System.out.println(
                "alpha.bean=" + context.getBean("alphaGreeting", String.class)
            );
            System.out.println(
                "beta.bean=" + context.getBean("betaGreeting", String.class)
            );
        }
    }
}
```

Part-by-part explanation:

- `loader.getResources(IMPORTS_PATH)` finds **resource URLs** matching the exact path on the classpath. The example has Boot's own resource plus at least two library modules; `imports.multiple` will print `true` when the modules are built/packaged properly.
- `ImportCandidates.load(AutoConfiguration.class, loader)` reads **class names** from valid resources. Because `spring-boot-autoconfigure.jar` also contributes many candidates, the code filters for `dev.sample.` so the output only displays the two classes created by the example.
- `distinct().sorted()` only makes **display** easy to verify. It is not a way to impose auto-configuration processing order in Spring Boot.
- Only then does `SpringApplication.run(...)` create the context. `getBean(...)` checks actual beans, a step distinct from reading the candidate list.

Build and run from the `candidate-demo/` root directory:

```bash
mvn -q clean package
java -jar app/target/app-1.0.0.jar
```

Ignoring Spring Boot logs and log ordering, the four lines printed by the application are:

```text
imports.multiple=true
candidates=dev.sample.alpha.AlphaAutoConfiguration,dev.sample.beta.BetaAutoConfiguration
alpha.bean=from-alpha-jar
beta.bean=from-beta-jar
```

**Why is this result noteworthy?**

- `CandidateApplication` resides in `dev.sample.app`.
- The two classes `AlphaAutoConfiguration`/`BetaAutoConfiguration` are in **sibling** packages `dev.sample.alpha` and `dev.sample.beta`, both **outside the default component scan scope**.
- They are still considered via the imports files in the two JARs.
- Each auto-configuration has one bean method, so when neither is excluded and no bean has a colliding name, the context has two differently named `String` beans. The example always looks up **by name**, avoiding ambiguity between two beans of the same type.

Do not infer from the `candidates=...` lines that the beans are already ready: only conclude a bean exists after the context starts and `alpha.bean`/`beta.bean` are checked.

## 6. Testing: Resources Are Real and Candidates Differ from Activated Beans

### 6.1. Test Observing Two JARs and Actual Beans

`app/src/test/java/dev/sample/app/ImportCandidatesTest.java`:

```java
package dev.sample.app;

import java.net.URL;
import java.util.Collections;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.annotation.ImportCandidates;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = CandidateApplication.class)
class ImportCandidatesTest {

    @Autowired
    ApplicationContext context;

    @Test
    void seesImportsAcrossMultipleJars() throws Exception {
        ClassLoader loader = CandidateApplication.class.getClassLoader();
        String path =
            "META-INF/spring/"
            + "org.springframework.boot.autoconfigure.AutoConfiguration.imports";

        List<URL> resources =
            Collections.list(loader.getResources(path));

        List<String> names =
            ImportCandidates.load(AutoConfiguration.class, loader)
                .getCandidates();

        assertThat(resources).hasSizeGreaterThanOrEqualTo(2);
        assertThat(names).contains(
            "dev.sample.alpha.AlphaAutoConfiguration",
            "dev.sample.beta.BetaAutoConfiguration"
        );
        assertThat(context.getBean("alphaGreeting", String.class))
            .isEqualTo("from-alpha-jar");
        assertThat(context.getBean("betaGreeting", String.class))
            .isEqualTo("from-beta-jar");
    }
}
```

### 6.2. Test Proving “Discovered” Does Not Mean “Activated”

`app/src/test/java/dev/sample/app/ExcludedBetaTest.java`:

```java
package dev.sample.app;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.annotation.ImportCandidates;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = CandidateApplication.class,
    properties = "spring.autoconfigure.exclude="
        + "dev.sample.beta.BetaAutoConfiguration"
)
class ExcludedBetaTest {

    @Autowired
    ApplicationContext context;

    @Test
    void discoveryCanIncludeAnExcludedCandidate() {
        List<String> candidateNames =
            ImportCandidates.load(
                AutoConfiguration.class,
                CandidateApplication.class.getClassLoader()
            ).getCandidates();

        assertThat(candidateNames)
            .contains("dev.sample.beta.BetaAutoConfiguration");
        assertThat(context.containsBean("alphaGreeting")).isTrue();
        assertThat(context.containsBean("betaGreeting")).isFalse();
    }
}
```

Run both tests:

```bash
mvn -q test
```

If the structure and imports files are right, both tests will pass. The second test is especially important:

- `ImportCandidates.load(...)` **still sees** `BetaAutoConfiguration` because the imports file sits inside the JAR on the classpath.
- `spring.autoconfigure.exclude` makes Spring Boot **exclude the candidate from the set of applied auto-configurations**.
- The context does not contain `betaGreeting`, even though the candidate list still contains the class name.
- Default component scanning did not change at all.

Both test classes use `@SpringBootTest` and do not declare nested `@Configuration` classes inside the app package, thus preventing test configurations from being accidentally picked up by component scan in the other test.

## 7. Sequence from Import Candidates to Actual Auto-Configuration

The diagram shows the steps at a functional level; some internal steps such as metadata filtering may be optimized across versions:

```text
Application enables @EnableAutoConfiguration
        |
        v
AutoConfigurationImportSelector
        |
        v
ImportCandidates.load(AutoConfiguration.class, ClassLoader)
        |
        v
Reads AutoConfiguration.imports from JARs/classpath roots
        |
        v
Candidate class name list (potentially from multiple JARs)
        |
        +--> deduplicates class names during candidate selection
        |
        +--> removes excluded auto-configurations
        |
        +--> applies filtering based on metadata/conditions
        |
        +--> applies auto-configuration ordering
        |
        v
Configurations are imported into bean definition processing
        |
        v
Evaluates remaining conditions at class and @Bean levels
        |
        v
Only qualifying beans are registered
```

### Do Not Conflate the Four States

| State | Meaning | Example |
| --- | --- | --- |
| **Classpath resource found** | Imports file can be located | `getResources(...)` shows the URL from the Alpha JAR. |
| **Candidate discovered** | Class name appears in the `ImportCandidates` list | `dev.sample.alpha.AlphaAutoConfiguration`. |
| **Auto-configuration considered/selected** | Passed exclusions, filtering, and import | Alpha is not excluded, initial conditions match. |
| **Bean registered** | `@Bean` method/configuration meets actual conditions | Bean `alphaGreeting` exists if no bean with a colliding name exists. |

`@ConditionalOnMissingBean` can make a default bean **back off** even after the auto-configuration class was imported. `@ConditionalOnClass` can make a candidate ineligible when a library is missing. `@ConditionalOnProperty` can also disable configuration via runtime configuration.

In addition, **the order of class names in imports files is not a mechanism that governs bean initialization order**. When relationships between auto-configurations are needed, use `before`/`after` attributes on `@AutoConfiguration` or `@AutoConfigureOrder` where appropriate. Bean instantiation order still primarily depends on dependency relationships and `@DependsOn`.

## 8. Different Classpath Scenarios

### 8.1. Running via Maven in an IDE

During development, modules may be present as `target/classes` directories or as JARs in the Maven local repository. The class loader can still find resources at the same path. If the IDE has not marked `src/main/resources` as a resources root, the imports file may not be copied to the output — candidates will be missing.

### 8.2. Running a JAR Packaged by the Spring Boot Plugin

Regular dependencies can be placed under `BOOT-INF/lib/` inside an executable JAR. This is **not** a flat regular classpath of loose files when viewed in a file explorer. The Spring Boot launcher builds a class loader that understands that layout, so `getResources(...)` and `ImportCandidates.load(...)` still work.

Do not convert a resource `URL` into `Path.of(url.toURI())` assuming every URL points to a physical file; with nested JARs that approach is unreliable.

### 8.3. Shaded/Uber JAR Dropping Multiple Imports Resources

Some packaging approaches **merge the bytecode of multiple JARs into a single flat JAR**, which can cause same-named files to overwrite one another. If Alpha's imports file is replaced by Beta's during shading, the class loader sees only one resource with one list, causing missing candidates.

When shading is unavoidable, configure a resource transformer to **merge imports contents properly**, and inspect the final artifact. Do not assume built-in transformers handle `AutoConfiguration.imports` as desired; transformers for `META-INF/services` or `spring.factories` do not necessarily handle this `.imports` resource path automatically. For typical Boot applications, prefer executable JAR packaging that keeps dependency JARs separate.

### 8.4. Missing Dependency at Runtime

If a module has an imports resource on the compile classpath yet is absent from the runtime classpath, Spring Boot will not discover that module's candidates in actual execution. Review dependency scopes, optional dependencies, packaging configuration, Maven profiles, and differences between IDE/test/production class loaders.

### 8.5. Multiple Class Loaders

Application servers, plugin systems, or isolated class loaders can have different resource visibility scopes. Do not conclude that because a file exists on disk the application's class loader **definitely** sees it. Diagnose using the exact class loader that Boot uses to discover candidates.

## 9. How to Inspect Imports Files in Artifacts

After running `mvn -q clean package` from the example root:

```bash
jar tf alpha-autoconfigure/target/alpha-autoconfigure-1.0.0.jar
jar tf beta-autoconfigure/target/beta-autoconfigure-1.0.0.jar
jar tf app/target/app-1.0.0.jar
```

In both library JARs, you should see the entry:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

In the app's executable JAR, look for:

```text
BOOT-INF/lib/alpha-autoconfigure-1.0.0.jar
BOOT-INF/lib/beta-autoconfigure-1.0.0.jar
```

`jar tf` lists entries; it **does not read the contents** of imports files inside nested JARs. To verify the class names inside, open the library JAR or read classpath resources using the example code above.

Another lightweight check when running the application:

```bash
java -jar app/target/app-1.0.0.jar --debug
```

Spring Boot's Condition Evaluation Report is useful when **the candidate was discovered yet created no bean**. If the candidate **does not appear in imports**, inspect the JAR/classpath first; the report cannot explain a class that was never registered as a candidate.

## 10. Comparison with `spring.factories` and Related APIs

Spring Boot previously used the mechanism of declaring `EnableAutoConfiguration` in:

```text
META-INF/spring.factories
```

Legacy syntax example (for recognition only, **not how auto-configurations are declared in the Spring Boot 3.5.7 example**):

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.OldAutoConfiguration
```

Since Spring Boot 2.7, the `AutoConfiguration.imports` registration mechanism was introduced; for Spring Boot 3.x, use the imports path per current documentation. Do not use `SpringFactoriesLoader` to read auto-configuration candidates in the new example and conclude nothing is there: **the two resource formats serve different purposes and version eras**.

Names to distinguish:

| Name | Function |
| --- | --- |
| `ImportCandidates` | Reads candidate names from `META-INF/spring/<annotation>.imports` files. |
| `AutoConfigurationImportSelector` | Selects auto-configurations to import based on the candidate list, exclusions, conditions/filters, and ordering. |
| `AutoConfiguration.imports` | Resource metadata declaring auto-configuration class names. |
| `@AutoConfiguration` | Annotation marking a class as auto-configuration; **does not create candidate discovery on its own if imports is missing**. |
| `@EnableAutoConfiguration` | Annotation activating the auto-configuration selection and import system; `@SpringBootApplication` includes this annotation. |
| `@ComponentScan` | Scans components in specified packages; not the standard loading path for auto-configurations. |
| `SpringFactoriesLoader` / `spring.factories` | Another metadata/factory loading system in the Spring ecosystem; does not replace `ImportCandidates` for Boot 3.x auto-configuration. |

## 11. Common Mistakes

**Mistake A — Using only `getResource(...)`, missing other JARs.** Use `getResources(...)` if you need to observe all resources sharing the same path, or use `ImportCandidates` directly to read the candidate list.

**Mistake B — Putting the imports file in the wrong directory.** Files under `src/main/java` are not runtime resources by default. Use `src/main/resources/META-INF/spring/...` and inspect the packaged artifact.

**Mistake C — Using the wrong annotation name in the resource path.** In Boot 3.5, the general auto-configuration file is named `org.springframework.boot.autoconfigure.AutoConfiguration.imports`, not `EnableAutoConfiguration.imports`. Distinguish the enabling annotation (`@EnableAutoConfiguration`) from the annotation marking candidate classes (`@AutoConfiguration`).

**Mistake D — Only putting `@AutoConfiguration` on the class.** Without an imports file, the class does not automatically become a candidate when depending on that JAR. It can still be imported by other mechanisms, but not via standard auto-discovery.

**Mistake E — Confusing candidates with beans.** Having a candidate's name in imports does not guarantee classpath/property/bean conditions match. When in doubt, check the candidate list, exclusions, and Condition Evaluation Report together.

**Mistake F — Reading resources via physical file paths.** Converting a `URL` to a `File` breaks easily when the JAR is nested inside an executable JAR or an environment providing a custom URL scheme.

**Mistake G — Shading overwrites the imports file.** Check the final JAR and resource merging strategy. If `AlphaAutoConfiguration` disappears from the candidate list after packaging, do not hastily switch to `@ComponentScan` as a fix.

**Mistake H — Trying to fix with `scanBasePackages`.** That is a component-scan setting; it neither restores missing imports resources nor automatically adds auto-configuration classes to the candidate list.

**Mistake I — Assuming import order matches file order.** Reading candidate names is the discovery phase; auto-configuration application order is still processed by Spring Boot and governed by ordering directives.

## 12. Self-Check Questions

1. Two JARs share the resource path `AutoConfiguration.imports`, each listing one class. Can `getResource(...)` miss one? **Yes**. `getResources(...)` is appropriate for traversing all resources of the same name.
2. Does `ImportCandidates.load(AutoConfiguration.class, loader).getCandidates()` return beans or class names? **Class names as `String`s**.
3. A library's auto-configuration is outside the `@SpringBootApplication` package. Is it skipped because `@ComponentScan` does not reach it? **Not necessarily**; if its name is in imports, it can be considered independently of scan scope.
4. `BetaAutoConfiguration` is in candidates yet excluded by `spring.autoconfigure.exclude`. Does Beta's default bean appear? **No**, because exclusion prevents that auto-configuration from being applied.
5. `@AutoConfiguration` is on the class, yet `AutoConfiguration.imports` is missing. Where is the fault? **Candidate registration mechanism**.
6. What is the exact path inside a Spring Boot 3.x JAR? **`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**.
7. Why is `java.io.File` not always suitable when reading imports from an executable JAR? **The resource may live in a nested JAR**, visible via the class loader without an ordinary filesystem path.
8. Does an imports file with two lines of the same class name make Boot create two identical beans? **No such conclusion can be drawn**; the candidate list is deduplicated and only qualifying beans are registered.

## Official References

- [Spring Boot 3.5 API — ImportCandidates](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/annotation/ImportCandidates.html): `load(Class, ClassLoader)` and annotation-based resource paths.
- [Spring Boot 3.5 Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html): imports file location, comments, starter architecture, and conditional configuration.
- [Spring Boot 3.5 API — AutoConfigurationImportSelector](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html): how the class selects auto-configuration candidates.
- [Spring Framework Javadoc — ClassLoader resource loading via Java SE](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `getResource`/`getResources`.
- [Spring Boot Reference — Executable Jar Format](https://docs.spring.io/spring-boot/reference/executable-jar/index.html): `BOOT-INF/classes`/`BOOT-INF/lib` layout and nested JAR class loading.
