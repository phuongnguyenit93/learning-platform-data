# Library JAR vs. Application Executable JAR

When learning Spring Boot, you often see two files that both end in `.jar` yet are used very differently. One file is added as a dependency so another application can call the classes inside it; the other can be run with `java -jar app.jar`, starts the Spring `ApplicationContext` itself, and uses packaged dependencies.

This difference involves the **artifact's purpose**, **internal JAR structure**, **classpath**, **manifest**, and **Spring Boot's launcher mechanism**. Without distinguishing them, you easily run into errors like "no main manifest attribute", "ClassNotFoundException", "Could not find or load main class", or a library that appears to be added to the project yet Spring cannot find its classes.

This lesson belongs to the **Run and Package** chapter of **Spring Boot Fundamentals**. We will distinguish a library JAR (plain/library JAR) from a Spring Boot executable JAR, look at how to create them with Gradle and Maven, organize multi-module projects, inspect artifact contents, and identify the right JAR type to release.

## 1. First: what is a JAR?

**JAR** (Java ARchive) is an archive format commonly used to package `.class` files, resources, and metadata for Java applications. Fundamentally, it is based on the ZIP format and can contain files such as:

```text
META-INF/MANIFEST.MF
com/example/demo/OrderService.class
com/example/demo/Order.class
application.properties
```

The same `.jar` format can serve multiple purposes:

- A library used by another application on the classpath.
- An artifact containing a Java program with a `main` method.
- An executable JAR packaged by Spring Boot along with required dependencies.
- An artifact containing infrastructure or annotation processors used during build time.
- A JAR produced using another tool's shading/assembly strategy.

Therefore, **the `.jar` extension is not enough to conclude a file can run standalone**. You need to examine its structure, manifest, classpath, and how it was built.

### 1.1. Two different goals

A **library JAR** typically answers the question:

> "Which classes, interfaces, and resources can other modules use?"

A **Spring Boot executable JAR** typically answers the question:

> "How do we run the entire application from this artifact, with an entry point and the appropriate dependencies?"

This difference in goals leads to different packaging layouts.

## 2. Library JAR (plain/library JAR)

Suppose you have a pricing library:

```java
package com.example.pricing;

import java.math.BigDecimal;

public class PriceCalculator {

    public BigDecimal calculateTotal(
            BigDecimal unitPrice,
            int quantity
    ) {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
```

After compiling and packaging it into `pricing-lib.jar`, the typical structure is:

```text
pricing-lib.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/
    └── example/
        └── pricing/
            └── PriceCalculator.class
```

The `PriceCalculator` class sits directly under its package path at the **root classpath of the JAR**.

Another application can put the JAR on its classpath and use:

```java
import com.example.pricing.PriceCalculator;
```

### 2.1. A library does not necessarily have a main method

A library usually does not have:

```java
public static void main(String[] args)
```

and its manifest does not need to declare a `Main-Class` entry point.

That is not a bug. A library is designed to **be loaded by another application**, not to run as an independent process itself.

### 2.2. Are the library's dependencies packaged inside it?

With standard Java/Gradle/Maven `jar` tasks, the artifact mainly contains the classes and resources produced by the module itself, **without automatically stuffing all dependency JARs inside**.

Example:

```text
pricing-lib.jar
  └── PriceCalculator.class

dependency-a.jar
dependency-b.jar
```

If `PriceCalculator` needs classes from dependency A at runtime, the consuming application must have dependency A on its runtime classpath through the appropriate build/dependency management mechanism.

A `pom.xml` or Gradle module metadata file can describe dependencies for the dependency manager. A plain JAR itself does not know how to download missing dependencies at runtime.

### 2.3. Is every library JAR non-executable?

No. A plain JAR can contain `main` and configure a `Main-Class` manifest entry. Then `java -jar` can launch that entry point.

However, that **does not automatically make it a Spring Boot executable JAR**. If the application needs external libraries, you still have to arrange the runtime classpath or package them with an appropriate strategy.

The phrase "library JAR" here describes the **artifact's role and organization**, not an absolute constraint of the JAR format.

## 3. What is a Spring Boot executable JAR?

Spring Boot provides a mechanism to package an application into an artifact that can be run directly:

```bash
java -jar orders-app.jar
```

A standard executable JAR created by a Spring Boot plugin typically contains:

- The application's classes and resources.
- Runtime dependency JARs packaged as **nested JARs**.
- Spring Boot launcher/loader classes.
- A manifest declaring the launcher and the application start class.
- Possibly additional metadata for layers or a classpath index, depending on configuration and version.

Typical structure:

```text
orders-app.jar
├── META-INF/
│   └── MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   ├── com/example/orders/OrdersApplication.class
│   │   ├── com/example/orders/OrderService.class
│   │   └── application.yml
│   ├── lib/
│   │   ├── spring-boot-*.jar
│   │   ├── spring-context-*.jar
│   │   ├── spring-core-*.jar
│   │   ├── logging-*.jar
│   │   └── pricing-lib-*.jar
│   └── layers.idx                 (may be present)
└── org/springframework/boot/loader/
    └── ...                        (launcher/loader classes)
```

Exact JAR names and extra paths depend on the Spring Boot version and actual runtime dependencies.

### 3.1. The two most important directories

**`BOOT-INF/classes/`** holds the main application's classes and resources.

Example:

```text
BOOT-INF/classes/com/example/orders/OrdersApplication.class
BOOT-INF/classes/application.yml
```

**`BOOT-INF/lib/`** holds the packaged runtime dependency JARs.

Example:

```text
BOOT-INF/lib/spring-context-*.jar
BOOT-INF/lib/jackson-databind-*.jar
BOOT-INF/lib/pricing-lib-1.0.0.jar
```

Not every executable JAR has those exact dependencies. If the application has no HTTP server or does not use Jackson, the corresponding libraries may not appear.

### 3.2. Why are dependencies stored as nested JARs?

Instead of unpacking classes from all dependencies and mixing them into one giant package tree, Spring Boot typically keeps each dependency as a separate JAR inside the executable JAR.

Example:

```text
orders-app.jar
  └── BOOT-INF/lib/pricing-lib-1.0.0.jar
        └── com/example/pricing/PriceCalculator.class
```

This organization has several benefits:

- Keeps each library's structure relatively isolated.
- Reduces conflicts caused by unpacking and improperly merging resource files.
- Makes it easier to see which dependencies are packaged.
- Supports the Spring Boot launcher mechanism for loading dependencies at runtime.

However, nested JARs **are not read by the default JVM classpath like external loose JARs**. Spring Boot needs its own launcher to set up proper class loading.

## 4. Direct comparison of the two JAR types

| Criterion | Plain library JAR | Spring Boot executable JAR |
|---|---|---|
| Goal | Used by other projects | Launching an application |
| Module's main classes | Usually at root by package | Under `BOOT-INF/classes/` |
| Dependencies | Usually not packaged directly | Usually under `BOOT-INF/lib/` |
| Entry point | Optional | Has launcher and application start class |
| `java -jar` | Not guaranteed to run | Standard way to run |
| Used as a dependency | Suitable | Usually unsuitable |
| Created with Gradle | `jar` | `bootJar` |
| Created with Maven | `maven-jar-plugin`/`package` | `spring-boot-maven-plugin:repackage` |
| Class loading | Standard JVM and build-tool classpath | Spring Boot loader handles nested JAR structure |
| Where typically published | Maven repository, shared libraries | CI artifacts, servers, container images |

The easy trap is that **both are `.jar` files**. Looking at the filename alone does not tell you which column it belongs to.

## 5. How do java -cp and java -jar differ?

These two ways of running are not equivalent.

### 5.1. Running with -cp

```bash
java -cp "app-classes:pricing-lib.jar" com.example.Main
```

`-cp` (classpath) specifies the locations where the JVM should look for classes and resources.

On Windows, the classpath separator is usually a semicolon:

```powershell
java -cp "app-classes;pricing-lib.jar" com.example.Main
```

The example above assumes `app-classes` contains `com/example/Main.class` and `pricing-lib.jar` contains the classes used.

When you add a library JAR to the classpath, the JVM can locate classes along package paths inside the JAR root.

### 5.2. Running with -jar

```bash
java -jar orders-app.jar
```

The JVM reads entry-point metadata from `META-INF/MANIFEST.MF` of the specified JAR and runs the corresponding main class.

In `-jar` mode, typical user classpath settings via `-cp` or the `CLASSPATH` variable are not applied the way you might expect for that JAR. Required dependencies must be arranged through the executable JAR mechanism or properly designed manifest/classpath attributes.

For a Spring Boot executable JAR, the entry point is the **Boot launcher**, which then loads the application.

### 5.3. Why does java -jar library.jar usually fail?

If a library JAR's manifest has no `Main-Class`, you may see:

```text
no main manifest attribute, in pricing-lib.jar
```

It is not because `PriceCalculator` is broken or the library is invalid. The JAR simply does not declare a program for the JVM to launch.

If a library JAR does have a `Main-Class` yet lacks runtime dependencies, it can still throw `ClassNotFoundException` or `NoClassDefFoundError` at runtime.

### 5.4. Why not use java -cp to run a Boot JAR like a library?

Application classes inside a Spring Boot executable JAR live at:

```text
BOOT-INF/classes/com/example/orders/OrdersApplication.class
```

not at the root:

```text
com/example/orders/OrdersApplication.class
```

The standard JVM classpath does not treat `BOOT-INF/classes` as a classpath root merely because you added the executable JAR to `-cp`.

Similarly, `BOOT-INF/lib/*.jar` are nested JARs that the default JVM classpath does not open automatically to search for dependencies.

Therefore, a command like:

```bash
java -cp orders-app.jar com.example.orders.OrdersApplication
```

is not the standard way to run a Spring Boot executable JAR and can fail to find the application class.

Instead, use:

```bash
java -jar orders-app.jar
```

or run via the Gradle/Maven plugin, an IDE, or a classpath assembled in the standard layout.

## 6. Role of META-INF/MANIFEST.MF

The manifest is a metadata file that can describe the entry point and certain attributes of a JAR.

For a simple library JAR, the manifest may contain very little information:

```text
Manifest-Version: 1.0
```

For a Spring Boot executable JAR, the manifest may look similar to:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.orders.OrdersApplication
Spring-Boot-Version: ...
Spring-Boot-Classes: BOOT-INF/classes/
Spring-Boot-Lib: BOOT-INF/lib/
```

The launcher name in `Main-Class` changes across versions: older Spring Boot lines used paths like `org.springframework.boot.loader.JarLauncher`, whereas newer lines may use `org.springframework.boot.loader.launch.JarLauncher`. Do not hard-code a specific launcher name without checking the version.

### 6.1. Main-Class vs. Start-Class

In a Spring Boot executable JAR:

- `Main-Class` usually points to the **Spring Boot launcher**.
- `Start-Class` points to the **application's main class**.

Example:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.orders.OrdersApplication
```

When using `java -jar`, the JVM invokes the launcher's main method. The launcher sets up class loading for the Boot layout and then invokes the application class's main method.

That is why the manifest may not place `OrdersApplication` directly in `Main-Class` like a hand-crafted plain executable JAR.

### 6.2. Simplified startup flow

```text
java -jar orders-app.jar
          │
          ▼
JVM reads META-INF/MANIFEST.MF
          │
          ▼
Spring Boot JarLauncher
          │
          ▼
Sets up classpath from:
  BOOT-INF/classes/
  BOOT-INF/lib/*.jar
          │
          ▼
Loads application Start-Class
          │
          ▼
OrdersApplication.main(args)
          │
          ▼
SpringApplication.run(...)
          │
          ▼
ApplicationContext starts up
```

This diagram illustrates the purpose of each step, not all internal class loader details.

## 7. Inspecting JAR structure locally

You do not need to guess the artifact type. You can inspect internal entries with the JDK `jar` tool.

### 7.1. Listing entries

```bash
jar tf pricing-lib.jar
```

Example output:

```text
META-INF/
META-INF/MANIFEST.MF
com/example/pricing/PriceCalculator.class
```

For a Boot JAR:

```bash
jar tf orders-app.jar
```

You might see:

```text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/orders/OrdersApplication.class
BOOT-INF/lib/spring-core-...jar
BOOT-INF/lib/pricing-lib-...jar
org/springframework/boot/loader/...
```

From the output, the clearest identifying signs are `BOOT-INF/classes` and `BOOT-INF/lib`.

### 7.2. Filtering output on Linux/macOS

```bash
jar tf orders-app.jar | grep "BOOT-INF/"
```

### 7.3. Filtering output in PowerShell

```powershell
jar tf orders-app.jar | Select-String "BOOT-INF/"
```

This inspection is handy when working with Windows IDEs, CI artifacts, or a JAR provided by someone else.

### 7.4. Reading the manifest

You can extract the manifest into a temporary directory:

```bash
mkdir inspect-jar
cd inspect-jar
jar xf ../orders-app.jar META-INF/MANIFEST.MF
```

Then read it:

```bash
cat META-INF/MANIFEST.MF
```

In PowerShell:

```powershell
Get-Content .\META-INF\MANIFEST.MF
```

Note that `jar xf` writes files to the current directory, so work inside a temporary folder rather than extracting directly into the project root unnecessarily.

## 8. Gradle: jar and bootJar

In a Gradle project, two common tasks are:

```text
jar
bootJar
```

### 8.1. The jar task

The `jar` task is provided by Gradle's Java plugin. It builds a standard JAR from the module's compiled classes and resources.

Library example:

```groovy
plugins {
    id 'java-library'
}
```

Run:

```bash
./gradlew jar
```

The artifact is usually placed in:

```text
build/libs/
```

Example:

```text
build/libs/pricing-lib-1.0.0.jar
```

Structure:

```text
com/example/pricing/PriceCalculator.class
META-INF/MANIFEST.MF
```

The `jar` task is suitable for library modules.

### 8.2. The bootJar task

When the Spring Boot Gradle plugin is applied to an application module, the `bootJar` task creates an executable JAR following Boot's layout.

Run:

```bash
./gradlew bootJar
```

The artifact is also usually placed in:

```text
build/libs/
```

Example:

```text
build/libs/orders-app-1.0.0.jar
```

Its structure includes `BOOT-INF/classes`, `BOOT-INF/lib`, and the launcher.

Run:

```bash
java -jar build/libs/orders-app-1.0.0.jar
```

### 8.3. Artifact names can vary

Do not assume every project always outputs the exact path:

```text
build/libs/app.jar
```

The filename depends on:

- `project.name`.
- `version`.
- `archiveBaseName`.
- `archiveClassifier`.
- `archiveVersion`.
- How the Gradle task is configured.
- The version of the Spring Boot Gradle plugin.

Inspect `build/libs` to pick the right artifact.

### 8.4. Why is there a -plain.jar file?

In many versions/configurations of the Spring Boot Gradle plugin, when both `jar` and `bootJar` are enabled, the plain JAR may receive the `plain` classifier to avoid colliding with the executable JAR's name.

Example:

```text
build/libs/orders-app-1.0.0.jar
build/libs/orders-app-1.0.0-plain.jar
```

Typically:

- `orders-app-1.0.0.jar`: Boot executable JAR.
- `orders-app-1.0.0-plain.jar`: plain JAR.

This is a convention dependent on plugin version/build configuration, **not a rule of the JAR format**. Always verify with `jar tf` and the manifest when unsure.

### 8.5. Configuring the bootJar filename

Gradle Groovy DSL example:

```groovy
tasks.named('bootJar') {
    archiveFileName = 'orders-app.jar'
}
```

After building, the executable JAR gets a fixed name:

```text
build/libs/orders-app.jar
```

Fixed naming can be convenient for deployment scripts. However, if you release multiple versions side by side, consider keeping the version in the artifact name to avoid unintended overwrites.

## 9. Gradle: does a library module need the Spring Boot plugin?

A module that only contains domain models, utilities, API contracts, or reusable service implementations **does not have to** apply the Spring Boot plugin.

Example library module:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    // Declare needed libraries when applicable.
}
```

When running:

```bash
./gradlew :pricing-lib:jar
```

you get a normal JAR artifact.

### 9.1. Why not enable bootJar for every module?

If every module builds an executable JAR, library modules may:

- Lack an application main class.
- Have a `BOOT-INF/classes` layout unsuitable for standard dependency classpaths.
- Pull dependencies into unnecessary nested JARs.
- Be difficult for other modules to consume via Gradle/Maven dependencies.
- Cause publication pipelines to select the wrong artifact.

Hence, a common rule of thumb in multi-module projects is:

> **Library modules produce plain JARs; application modules produce executable JARs.**

### 9.2. What if a library also uses Spring annotations?

A module with `@Service`, `@Configuration`, or `@ConfigurationProperties` can still be a normal library JAR.

Example:

```java
package com.example.shared;

import org.springframework.stereotype.Service;

@Service
public class CurrencyConverter {
    // ...
}
```

It does not need to become an executable JAR just because it uses Spring annotations. The consuming module must put the artifact on its classpath and register the beans via component scanning, `@Import`, auto-configuration, or another appropriate mechanism.

### 9.3. What if a module uses the Boot plugin but only wants a library?

A project with shared build conventions might apply the Boot plugin across many modules. When a module is only a library, you can disable `bootJar` and enable `jar`:

```groovy
tasks.named('bootJar') {
    enabled = false
}

tasks.named('jar') {
    enabled = true
    archiveClassifier = ''
}
```

This snippet assumes the `bootJar` task actually exists because the Boot plugin has been applied. The right configuration depends on the plugin version and the project's publication conventions.

If there is no reason to apply the Boot plugin to a library, the simpler approach is to use `java-library` and declare the needed dependencies.

## 10. Maven: plain JAR and spring-boot:repackage

In a Maven project, `mvn package` normally triggers the packaging lifecycle. For a project with `<packaging>jar</packaging>`, the Maven JAR Plugin can create a plain JAR from compiled classes/resources.

Example:

```xml
<project>
    ...
    <packaging>jar</packaging>
    ...
</project>
```

The artifact is usually located at:

```text
target/pricing-lib-1.0.0.jar
```

### 10.1. Role of the Spring Boot Maven Plugin

The Spring Boot Maven Plugin provides the goal:

```text
spring-boot:repackage
```

This goal takes an already-built JAR/WAR and repackages it in Spring Boot's executable layout, with the launcher and required dependencies.

A common plugin configuration:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

The plugin version must be managed by the Spring Boot parent, dependency/plugin management, or an explicit version declaration per project.

After:

```bash
mvn package
```

the application artifact can become an executable JAR if `repackage` is bound and executes successfully.

### 10.2. A Maven parent is not enough to prove repackage ran

A project using `spring-boot-starter-parent` and Boot dependencies still needs its actual plugin executions checked. Depending on parent configuration, declared plugins, and lifecycle, `repackage` may or may not execute.

Do not guess solely from `@SpringBootApplication` being in the source. Check:

- Effective POM/plugin configuration.
- Build logs for `repackage`.
- Artifact contents in `target`.
- Manifest and `BOOT-INF` entries.

### 10.3. Keeping both plain JAR and executable JAR using a classifier

Some applications or build pipelines need both:

- A plain JAR to be used as a normal artifact.
- An executable JAR to run.

The Spring Boot Maven Plugin can use a classifier for the repackaged variant:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Illustrative output:

```text
target/orders-app-1.0.0.jar
target/orders-app-1.0.0-exec.jar
```

The second artifact is the executable variant, while the primary artifact can remain a plain JAR under the appropriate configuration.

If using publishing, confirm the classifier and which artifact is attached/deployed. Do not let an executable application JAR be published accidentally as a consumable library.

## 11. Multi-module example: shared library and Spring Boot application

Let us build a project consisting of:

- `greeting-lib`: a plain Java library.
- `greeting-app`: a Spring Boot application using the library.

### 11.1. Overall structure

```text
greeting-project/
├── settings.gradle
├── build.gradle
├── greeting-lib/
│   ├── build.gradle
│   └── src/main/java/com/example/greeting/
│       └── GreetingFormatter.java
└── greeting-app/
    ├── build.gradle
    ├── src/main/java/com/example/app/
    │   └── GreetingApplication.java
    └── src/main/resources/
        └── application.yml
```

### 11.2. settings.gradle

```groovy
rootProject.name = 'greeting-project'

include 'greeting-lib'
include 'greeting-app'
```

### 11.3. Library: greeting-lib/build.gradle

```groovy
plugins {
    id 'java-library'
}
```

Class in the library:

```java
package com.example.greeting;

public class GreetingFormatter {

    public String format(String name) {
        return "Hello, " + name + "!";
    }
}
```

This module does not need `@SpringBootApplication` or a `main` method.

### 11.4. Application: greeting-app/build.gradle

Configuration fragment for the application module:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
}

dependencies {
    implementation project(':greeting-lib')
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

This snippet assumes the Spring Boot plugin version, repositories, and dependency management are configured in the root project or per the corresponding build setup. It demonstrates the relationship between modules, not a complete standalone Gradle file for every project.

### 11.5. Application using the library

```java
package com.example.app;

import com.example.greeting.GreetingFormatter;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class GreetingApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(GreetingApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }

    @Bean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter();
    }

    @Bean
    CommandLineRunner greetingRunner(
            GreetingFormatter formatter
    ) {
        return args -> System.out.println(
                formatter.format("Minh")
        );
    }
}
```

Here, the application **registers `GreetingFormatter` as a bean via `@Bean`**. The library does not have to know anything about Spring Boot.

### 11.6. Building each module

Build the library:

```bash
./gradlew :greeting-lib:jar
```

Build the application's executable JAR:

```bash
./gradlew :greeting-app:bootJar
```

Illustrative artifacts:

```text
greeting-lib/build/libs/greeting-lib-1.0.0.jar
greeting-app/build/libs/greeting-app-1.0.0.jar
```

Actual filenames depend on version/classifier configuration.

### 11.7. Inside the executable JAR

When inspecting the `greeting-app` executable JAR, you will encounter:

```text
BOOT-INF/classes/com/example/app/GreetingApplication.class
BOOT-INF/lib/greeting-lib-1.0.0.jar
BOOT-INF/lib/spring-boot-*.jar
BOOT-INF/lib/spring-context-*.jar
...
```

This illustrates the relationship:

```text
greeting-lib.jar
      │
      │ dependency
      ▼
greeting-app
      │
      │ bootJar
      ▼
greeting-app-executable.jar
      ├── application classes
      └── nested greeting-lib.jar
```

### 11.8. Running the application

```bash
java -jar greeting-app/build/libs/greeting-app-1.0.0.jar
```

Output from the runner may be:

```text
Hello, Minh!
```

You do not run `greeting-lib.jar` by itself. The application executable JAR uses the packaged library JAR at runtime.

## 12. Why shouldn't a Spring Boot executable JAR be used as a dependency?

This is a critical rule when designing multi-module projects.

Suppose project A produces:

```text
service-a-exec.jar
└── BOOT-INF/classes/com/example/a/MyService.class
```

Project B adds that file as a normal dependency, for instance placing the executable JAR on the classpath.

The JVM and build tools typically look for:

```text
com/example/a/MyService.class
```

right from the JAR root. Yet the actual class sits at:

```text
BOOT-INF/classes/com/example/a/MyService.class
```

Thus, a tool consuming the JAR like a normal library JAR may fail to find the class.

### 12.1. The problem is not just the main method

Even if the executable JAR has a valid `Start-Class` and runs, it is still not a convenient library for another project to import classes from.

The difference lies in **the layout and classpath mechanism**.

### 12.2. What if another application needs to share logic?

Extract the shared logic into a module that builds a plain/library JAR:

```text
shared-domain.jar
      ▲                ▲
      │                │
  orders-app       billing-app
      │                │
      ▼                ▼
orders-exec.jar   billing-exec.jar
```

Both applications use the library JAR, while each application has its own executable JAR with its own entry point and dependencies.

This separates responsibilities cleanly and is far easier to release than having application A depend on application B's executable JAR.

### 12.3. What if you need to share APIs without duplicating code?

You can create modules:

- `shared-api`: interfaces, DTOs, public contracts.
- `shared-core`: shared implementations, if appropriate.
- `orders-app`: first application/entry point.
- `billing-app`: second application/entry point.

Shared modules produce plain JARs; application modules produce executable JARs. They can be published via an internal Maven repository or consumed as Gradle project dependencies in a monorepo.

## 13. Spring Boot starters and auto-configuration are usually library JARs

A starter/integration library may contain Spring classes and metadata so Spring Boot automatically discovers configuration when users add the dependency.

Example:

```text
acme-mail-autoconfigure.jar
├── META-INF/
│   └── spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── com/acme/mail/autoconfigure/
    └── MailAutoConfiguration.class
```

This can still be a **normal library JAR**. It does not need `java -jar` or its own `SpringApplication` main class.

### 13.1. How is auto-configuration discovered?

When a Spring Boot application adds the library to its runtime classpath, Spring Boot can read the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

and locate the listed auto-configuration classes.

Example:

```text
com.acme.mail.autoconfigure.MailAutoConfiguration
```

Boot then evaluates conditions such as `@ConditionalOnClass`, `@ConditionalOnProperty`, and `@ConditionalOnMissingBean` to decide whether bean definitions are registered.

**Auto-configuration inside a library JAR does not turn that JAR into an executable JAR.** It only provides configuration that another application can load.

### 13.2. Distinguishing a starter from an executable app

| Artifact | Role |
|---|---|
| `spring-boot-starter-web` | Dependency bundle for the web stack; not a standalone web app |
| `acme-mail-autoconfigure.jar` | Provides auto-configuration for consuming apps |
| `acme-mail-starter.jar` | Typically combines dependencies and auto-configuration |
| `orders-app.jar` built with `bootJar` | Executable JAR to launch the application process |

Having "spring-boot" in the name does not prove an artifact is executable. Look at the artifact's responsibility.

## 14. How does a Boot executable JAR differ from a shaded/uber JAR?

"Fat JAR", "uber JAR", and "executable JAR" are sometimes used interchangeably, yet their packaging mechanisms can differ greatly.

### 14.1. Spring Boot executable JAR keeps nested dependencies

```text
BOOT-INF/lib/library-a.jar
BOOT-INF/lib/library-b.jar
BOOT-INF/classes/...
```

Dependency JARs remain separate archives inside the main JAR.

### 14.2. Shaded/uber JARs may merge classes

Tools like Maven Shade or Gradle Shadow typically unpack dependency contents and merge them into a single archive:

```text
com/example/app/Application.class
org/example/liba/Helper.class
org/example/libb/Utility.class
META-INF/services/...
```

An advantage of shading is a standard root classpath and support for package relocation to avoid certain package conflicts.

However, merging archives requires properly handling duplicate resources, JAR signatures, and service loader metadata. You cannot simply copy/overwrite files arbitrarily.

### 14.3. Key differences

| Aspect | Spring Boot executable JAR | Typical shaded JAR |
|---|---|---|
| Dependency packaging | Nested JARs | Merged classes/resources |
| Class loading | Spring Boot loader | Usually standard JVM classpath |
| Package layout | `BOOT-INF/classes` and `BOOT-INF/lib` | Classes usually at root by package |
| Resource merging | Rarely requires manually merging dependency contents | Often requires transformer/merge config |
| Entry point | Boot launcher and Start-Class | Depends on configured manifest/Main-Class |

A shaded JAR can also run with `java -jar` if it has a valid main manifest. However, it does not share the same layout as `bootJar`.

### 14.4. Do not build a Boot JAR manually by zipping files

If you manually zip `BOOT-INF/classes` and `BOOT-INF/lib` without the proper launcher/manifest, `java -jar` can fail.

Use the appropriate `bootJar` or `spring-boot:repackage` plugin. They know how to generate a layout and metadata compatible with the Spring Boot loader for the version in use.

## 15. Does an executable JAR contain every dependency?

Normally a Spring Boot executable JAR contains the runtime-classpath dependencies selected by the build plugin. Still, you should not claim "every dependency in the project is inside the JAR".

There are multiple dependency scopes:

- `implementation`: used at compile time, usually included on the runtime classpath.
- `runtimeOnly`: needed only at runtime.
- `compileOnly`: usually not included on the default runtime classpath.
- `testImplementation`: for tests, should not be packaged into production artifacts.
- Maven `provided` or other scopes: packaging depends on the plugin and packaging type.

Some dependencies or configurations follow special rules in the Spring Boot plugin. Inspect the final artifact instead of guessing solely from scope names.

### 15.1. Database driver example

Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

In a JDBC application using PostgreSQL, the driver is a runtime dependency and normally needs to be inside the executable JAR.

After building, check:

```text
BOOT-INF/lib/postgresql-*.jar
```

If the driver is missing at runtime, you may encounter driver/class-not-found errors or `DataSource` initialization failures.

### 15.2. Non-packaged dependencies may still be needed outside the application

An executable JAR contains the dependencies needed to run Java code, but that does not mean every environmental dependency is inside the artifact.

The application may still require:

- A compatible Java runtime/JDK.
- A running database server.
- Network access.
- Secrets and environment variables.
- External configuration.
- Read/write permissions on files or directories.
- A message broker, cache server, or other APIs.

"Self-contained" in the context of a Boot executable JAR mainly means **packaging Java application code together with its dependencies**, not bundling the operating system and all external services.

## 16. How Spring Boot automatically finds the main class

An application module typically has:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

The build plugin can determine the start class from classes containing `main` or from user configuration.

### 16.1. When a project has multiple main classes

Suppose a module has:

```text
com.example.orders.OrdersApplication
com.example.orders.AdminToolApplication
```

Automatic main class detection can become ambiguous.

With the Spring Boot Gradle plugin, you can configure:

```groovy
springBoot {
    mainClass = 'com.example.orders.OrdersApplication'
}
```

Or configure a specific task as needed:

```groovy
tasks.named('bootJar') {
    mainClass = 'com.example.orders.OrdersApplication'
}
```

After building, read the manifest to confirm the actual `Start-Class`.

### 16.2. The main class does not have to have a web controller

A Spring Boot executable JAR can be:

- A REST API.
- A reactive web app.
- A batch/CLI application.
- A message consumer.
- A scheduler.
- A background worker.

`@SpringBootApplication` with `SpringApplication.run(...)` does not require an embedded web server. The application type depends on the classpath and `WebApplicationType`.

### 16.3. If the build fails because no main class is found

A library-only module may have no `main`. If you try to run `bootJar` on that module, the plugin may fail reporting it cannot find a suitable main class.

This is usually a sign to clarify the module's role:

- Library: use `jar`.
- Application: provide a main class and use `bootJar`.

Do not add a dummy `main` method just to build an executable JAR for a library if the library is not genuinely a runnable program.

## 17. Where are resources packaged and how are they read?

The standard Gradle/Maven directory:

```text
src/main/resources/
```

may contain:

```text
application.yml
templates/email.html
data/default-categories.json
META-INF/services/com.example.Plugin
```

When creating a plain JAR, these resources are usually placed at the classpath root inside the JAR:

```text
application.yml
templates/email.html
data/default-categories.json
```

When creating a Boot executable JAR, resources from the application module usually live under:

```text
BOOT-INF/classes/application.yml
BOOT-INF/classes/templates/email.html
BOOT-INF/classes/data/default-categories.json
```

### 17.1. Read via classpath, not relative paths to source

In Java:

```java
try (InputStream in =
        getClass().getResourceAsStream(
                "/data/default-categories.json"
        )) {
    if (in == null) {
        throw new IllegalStateException("Resource not found");
    }

    // Read data from in.
}
```

Using classpath resources usually works in both the IDE and an executable JAR, as long as the resource is packaged properly.

Do not write:

```java
Files.readString(
        Path.of("src/main/resources/data/default-categories.json")
);
```

and expect it to keep working when deploying the JAR from another directory. `src/main/resources` is the source project layout; it is not a real external file path beside the JAR after building.

### 17.2. Resources in nested library JARs

If `greeting-lib.jar` contains a resource:

```text
com/example/greeting/messages.properties
```

when it sits in `BOOT-INF/lib/greeting-lib.jar`, the Spring Boot launcher allows the class loader to find the library's resource.

The application should use classpath APIs such as `ClassLoader#getResourceAsStream` or Spring `ResourceLoader`, rather than manually concatenating `BOOT-INF/lib/...` paths to open it like a normal file.

### 17.3. Why not convert a resource URL into a File arbitrarily?

A resource inside an executable JAR/nested JAR is not necessarily representable as a `java.io.File` on the filesystem.

The following may fail after packaging:

```java
File file = new File(
        getClass().getResource("/data/default-categories.json").toURI()
);
```

When the resource is inside an archive, the URI is not a standard `file:` path.

It is better to read via `InputStream` or use Spring `Resource`:

```java
Resource resource =
        resourceLoader.getResource(
                "classpath:data/default-categories.json"
        );

try (InputStream in = resource.getInputStream()) {
    // Process content.
}
```

## 18. Configuration outside the executable JAR

An executable JAR can contain a default `application.yml` in `BOOT-INF/classes`, yet Spring Boot supports many sources of externalized configuration.

Example:

```text
deploy/
├── orders-app.jar
└── config/
    └── application-prod.yml
```

You can run with a profile:

```bash
java -jar orders-app.jar --spring.profiles.active=prod
```

Or specify an additional configuration location:

```bash
java -jar orders-app.jar --spring.config.additional-location=optional:file:./config/
```

**You do not need to open the JAR and edit `application.yml` inside** every time you switch environments.

### 18.1. One artifact, many environments

```text
orders-app.jar
       │
       ├── local + local config
       ├── staging + staging config
       └── production + production config
```

The same application artifact can be deployed across environments using:

- Environment variables.
- Java system properties.
- Command-line arguments.
- External config files.
- Profile-specific configuration.

This keeps build/publish workflows consistent: build once, deploy across multiple environments with the appropriate configuration.

### 18.2. Do not package secrets inside released JARs

Avoid storing passwords, API tokens, or private keys directly in `src/main/resources/application.yml` and committing/packaging them into release artifacts.

Use a secrets manager, environment variables, or secure external configuration provided by the deployment platform. A JAR can be downloaded, copied, or unpacked by many people in a pipeline.

## 19. Spring Boot executable JARs and Docker/containers

An executable JAR can be copied into a container image and run with a suitable Java runtime.

Simple Dockerfile example:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY orders-app.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

This example assumes the application is compatible with Java 21 and the `orders-app.jar` artifact was built before building the image. Choose the base image according to your project's Java baseline and security policies.

### 19.1. A container image does not replace the executable JAR

A container image encompasses a broader runtime and packaging environment, whereas the executable JAR is the Java artifact run inside the image.

Relationship:

```text
Container image
├── Java runtime
├── Required OS libraries
└── /app/app.jar
    ├── BOOT-INF/classes
    └── BOOT-INF/lib
```

### 19.2. Layers and layers.idx

Spring Boot can write metadata describing layers of the executable JAR:

```text
BOOT-INF/layers.idx
```

Layering lets container image build tools separate application code, frequently changing dependencies, and stable dependencies. This can improve layer caching during image builds.

However, `layers.idx` **is not the sole proof of an executable JAR**, and it is not a file the application should read as business configuration.

Tools such as Spring Boot layertools/jarmode or buildpacks can leverage layering metadata depending on the version and build setup.

### 19.3. Considering buildpack images

Beyond writing a Dockerfile and calling `java -jar`, Spring Boot plugins also support building OCI images via buildpacks integration, depending on configuration and environment.

Gradle task example:

```bash
./gradlew bootBuildImage
```

This is a different deployment path and does not change the fundamental distinction between a library JAR and a Spring Boot application artifact.

## 20. Is every Boot JAR a "fully executable JAR"?

Some Spring Boot versions/configurations support a **fully executable archive** with a launch script prepended to the JAR file.

For example, in Gradle you might see configuration in compatible plugin lines:

```groovy
tasks.named('bootJar') {
    launchScript()
}
```

The idea is to prepend a shell script so that on compatible systems the archive can be run directly:

```bash
./orders-app.jar
```

This differs from the standard command:

```bash
java -jar orders-app.jar
```

### 20.1. Do not confuse the two meanings of executable

In this lesson, **Spring Boot executable JAR** primarily means **a JAR runnable via `java -jar`** thanks to the Boot launcher.

A "fully executable JAR" is a variant with an added launch script to support running as a script/executable file on certain systems.

Not every Boot JAR has a launch script; you do not need a launch script to run `java -jar`.

### 20.2. Watch out for ZIP/JAR tools

Some archive tools behave differently when a JAR file starts with a shell script prefix. Therefore, if you need to inspect or distribute a fully executable archive, verify your toolchain supports this file type.

In container environments, standard `java -jar` is usually simpler and more predictable.

## 21. How does an executable WAR differ from an executable JAR?

Spring Boot can support packaging web applications as WARs instead of JARs.

### 21.1. WARs for servlet containers

A traditional WAR is designed to be deployed into a servlet container such as Tomcat in the target environment.

A WAR layout typically includes:

```text
WEB-INF/classes/
WEB-INF/lib/
META-INF/
```

Spring Boot can produce an executable WAR containing a launcher to run via `java -jar` in appropriate setups, while also serving certain servlet container deployment requirements.

### 21.2. Do not confuse with a library JAR

Three main roles:

| Artifact | Goal |
|---|---|
| Library JAR | Used by other modules as a dependency |
| Boot executable JAR | Launches an application with embedded runtime/server when appropriate |
| WAR | Packages a web application for servlet deployment or Boot executable WAR per config |

Choose WAR only if you have a specific deployment requirement. For many modern Spring Boot applications, an executable JAR is the simpler choice for standalone execution.

## 22. Common errors when running or using JARs

| Symptom | Common cause | Solution |
|---|---|---|
| `no main manifest attribute` | Plain/library JAR lacks `Main-Class` | Use `bootJar`/`repackage` for apps; do not run libraries as apps |
| `Could not find or load main class` | Wrong classpath/entry point | Check layout, manifest, and launch command |
| `ClassNotFoundException` when using Boot JAR as dependency | Application classes sit under `BOOT-INF/classes` | Extract shared library into a plain JAR |
| `NoClassDefFoundError` at runtime | Missing runtime dependency or incompatible version | Check `BOOT-INF/lib` or dependency tree |
| JAR runs but cannot find `src/main/resources/...` file | Using source project filesystem path | Use classpath resources |
| `bootJar` cannot find main class | Module lacks entry point or has multiple main classes | Only use bootJar for apps, or configure `mainClass` |
| Both `-plain.jar` and un-classified JAR exist | Gradle creates two packaging variants | Check which file contains `BOOT-INF` |
| App runs in IDE but fails with `java -jar` | Different classpath, resources, profile, or build artifact | Compare runtime dependencies and jar entries |
| `UnsupportedClassVersionError` | Java runtime older than bytecode target | Use compatible Java runtime version or build target |
| App JAR has dependencies but cannot connect to database | External service/config not ready | Check config, network, credentials, DB availability |
| `java -cp app.jar Application` cannot find class | Boot JAR uses nested layout and launcher | Run `java -jar app.jar` |
| Public library published as executable JAR | Build/publish picked wrong artifact | Publish plain JAR; reserve executable JAR for deployment |

### 22.1. "no main manifest attribute" error

Example:

```text
no main manifest attribute, in app-plain.jar
```

Most likely you are running the plain JAR.

Check `build/libs` or `target` to see if the Boot executable JAR was created. If not, run the appropriate application packaging task/goal.

### 22.2. "ClassNotFoundException" for a dependency

If the build resolved the dependency yet runtime cannot find the class, distinguish whether:

- The project is running a plain JAR without putting dependencies on the classpath.
- An executable JAR was created, but the needed dependency is missing from `BOOT-INF/lib`.
- The dependency was excluded or declared in the wrong scope.
- Dependency/version conflicts occurred.
- The library contains the class in a different package than the code imports.

Not every `ClassNotFoundException` means the Spring Boot loader is broken.

### 22.3. Java version errors

Example:

```text
java.lang.UnsupportedClassVersionError
```

usually appears when classes were compiled for a newer Java version than the runtime in use.

Check:

```bash
java -version
```

and the build's Java toolchain/release configuration. A Spring Boot executable JAR does not automatically bundle a compatible Java runtime inside by default.

## 23. How running from an IDE differs from running an executable JAR

When you click Run in an IDE, the IDE usually builds a classpath containing:

```text
build/classes/java/main/
build/resources/main/
dependency-a.jar
dependency-b.jar
...
```

Then the IDE calls:

```text
com.example.orders.OrdersApplication.main(...)
```

It does not necessarily invoke Spring Boot's `JarLauncher`.

Conversely:

```bash
java -jar orders-app.jar
```

uses the executable JAR's layout and launcher.

### 23.1. Why does it work in the IDE yet fail when packaged?

Some possibilities:

- A resource was on the IDE classpath but excluded when building the JAR.
- A dependency was included by the IDE but does not belong to the artifact's runtime classpath.
- Code uses absolute paths or paths relative to the project root.
- Main class/manifest is misconfigured.
- The IDE runs a different profile than `java -jar`.
- A module build is missing a required library.
- Annotation processor/generated resources were not included in the artifact.

This is why you should verify the **final artifact**, not rely solely on a successful IDE Run.

### 23.2. What is bootRun?

The Spring Boot Gradle plugin typically provides the task:

```bash
./gradlew bootRun
```

`bootRun` starts the application by running from compiled classes/resources and the runtime classpath, **without requiring an executable JAR to be built first**.

Comparison:

| Run method | Characteristics |
|---|---|
| Run main in IDE | Classpath prepared by IDE/Gradle/Maven integration |
| `./gradlew bootRun` | Runs from project classpath via Gradle task |
| `java -jar build/libs/app.jar` | Runs packaged artifact using Boot launcher |
| `java -cp ... Main` | Runs Java main with manually specified classpath |

When verifying actual deployment behavior, run the exact final executable artifact, not only `bootRun`.

## 24. Proper packaging does not mean the application is guaranteed to start

Successfully building a Boot executable JAR only confirms that packaging created the artifact as configured. When executed, the application still goes through:

```text
JVM starts
    │
    ▼
Spring Boot launcher loads classes
    │
    ▼
SpringApplication.run
    │
    ▼
Environment and Config Data
    │
    ▼
Auto-configuration and bean registration
    │
    ▼
Instantiate/inject beans
    │
    ▼
Run startup callbacks and runners
    │
    ▼
Application ready (if successful)
```

A completely valid JAR can still fail because of:

- Invalid database URL.
- Missing password or API key.
- Missing bean dependency.
- Server port already in use.
- Configuration properties failing to bind/validate.
- `ApplicationRunner` throwing an exception.
- External service unavailability.

Do not try to fix a bean wiring error by switching from `jar` to `bootJar` when the artifact already has the right launcher and dependencies. Identify whether the error belongs to **packaging/classpath** or **application startup**.

## 25. Publishing: which artifact should go to a Maven repository?

A library published for other projects to consume should typically have:

- A plain JAR with classes/resources in standard layout.
- Valid Maven POM or Gradle module metadata.
- Appropriate `api`/`implementation`/`runtime` dependency declarations.
- A stable version.
- Optionally sources JAR and Javadoc JAR when needed.

An application's executable JAR is typically published to:

- CI/CD artifact storage.
- A container image repository (after building an image).
- A server or deployment platform.
- Operations release packages.

### 25.1. Why does accidentally publishing an executable JAR cause errors?

A Maven consumer puts the artifact on its classpath as a library. If the artifact's classes live under `BOOT-INF/classes`, they are not in the layout standard classpath resolvers expect.

Thus, an artifact that "runs great with `java -jar`" does not automatically mean it "works great as a dependency".

### 25.2. Can both variants be published?

Yes, a project can publish plain and executable artifacts with different classifiers or through separate publications.

However, align clearly on:

- What is the primary artifact?
- Which artifact do dependency consumers use?
- Which artifact does CI deployment pick?
- Are names/classifiers unambiguous?
- Could a nested-dependency JAR accidentally be published as the main library?

If a module acts as both library and application, splitting it into two modules usually makes management easier and reduces ambiguity.

## 26. Distinguishing "containing dependencies" from "resolving dependencies"

An important foundational point when using Java build tools:

### 26.1. At build time

Gradle or Maven reads dependency declarations to download and select library versions:

```text
build.gradle / pom.xml
          │
          ▼
Dependency resolution
          │
          ▼
Compile classpath + runtime classpath
```

### 26.2. When creating a library JAR

```text
Compiled classes/resources
          │
          ▼
jar
          │
          ▼
library.jar
```

Publication metadata can describe dependencies so the consuming application resolves them itself.

### 26.3. When creating a Boot executable JAR

```text
Application classes/resources
            +
Runtime dependencies
            │
            ▼
bootJar / repackage
            │
            ▼
Boot executable JAR
  BOOT-INF/classes/
  BOOT-INF/lib/
```

### 26.4. At runtime

With a library JAR, the application launcher/build tool must assemble a classpath containing the library and its needed dependencies.

With a Boot executable JAR, the Boot loader loads the packaged runtime dependencies according to the Boot layout.

That is why successful dependency resolution at build time does not guarantee you can run a plain JAR with `java -jar` without preparing a runtime classpath.

## 27. Artifact verification checklist before deployment

Although it does not replace testing, a sound technical verification flow may include:

### Step 1 — Confirm module role

Is this module a reusable library or an application entry point?

### Step 2 — Choose the right task/goal

- Library: `jar` or Maven JAR packaging.
- Application: `bootJar` or `spring-boot:repackage`.

### Step 3 — Check artifact filename

Inspect `build/libs` or `target`, distinguishing `-plain`, `-exec`, and other classifiers.

### Step 4 — Inspect contents

```bash
jar tf artifact.jar
```

- Classes at root package path? Usually a library/plain JAR.
- `BOOT-INF/classes` and `BOOT-INF/lib` present? Usually a Boot executable JAR.

### Step 5 — Check manifest

Confirm `Main-Class` and `Start-Class` if an executable JAR is expected.

### Step 6 — Check dependencies

For a Boot JAR, verify critical runtime dependencies appear in `BOOT-INF/lib`.

### Step 7 — Check resources

Verify `application.yml`, templates, and required resources are packaged in the right place.

### Step 8 — Run matching the deployment model

Example:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Do not rely only on the IDE or `bootRun` if production runs `java -jar`.

### Step 9 — Inspect startup logs

Separate launcher/classpath errors, configuration errors, and Spring `ApplicationContext` errors.

### Step 10 — Verify Java runtime

Confirm the runtime environment's Java version is compatible with the bytecode and Spring Boot version.

## 28. Practical scenarios

### 28.1. "I just want to write a shared library; do I need @SpringBootApplication?"

No. A Java library may only need ordinary classes and interfaces. If Spring beans are needed, the module can still provide `@Configuration` or auto-configuration without needing a main application class.

Use a plain JAR.

### 28.2. "I want to run a Spring Boot app with only a CommandLineRunner"

You still need an application entry point. You can use `@SpringBootApplication`, `SpringApplication.run(...)`, and `WebApplicationType.NONE`.

Then build a Boot executable JAR to run:

```bash
java -jar batch-app.jar
```

You do not need to add a web dependency just to make the executable JAR runnable.

### 28.3. "I have a repository module, a service module, and a web module"

Shared repository/service modules are normally library JARs. The web/application module is the entry point, creating an executable JAR that includes the module dependencies.

```text
repository.jar
      │
      ▼
service.jar
      │
      ▼
web-app executable.jar
```

Depending on the build graph, the application executable JAR may contain both the repository and service JARs under `BOOT-INF/lib`.

### 28.4. "I need to import classes from app A into app B"

If those classes are shared business logic, extract them into a library module. Do not add app A's executable JAR as a regular dependency of app B.

### 28.5. "I have a Spring Boot starter; should I build bootJar?"

Normally no. Starter/autoconfigure modules are consumed as library JARs, contributing dependency metadata and auto-configuration resources.

Build a plain JAR; the consuming application builds the executable JAR.

### 28.6. "I want an artifact that runs on a server without Maven/Gradle installed"

Use a Spring Boot executable JAR with a compatible Java runtime:

```bash
java -jar application.jar
```

The server does not need source code or Gradle/Maven to run the built artifact. It still needs the runtime, permissions, configuration, and any external services the application depends on.

### 28.7. "Can I unpack the JAR and run classes manually?"

You can for experimentation, though you would need to reconstruct the classpath containing application classes and dependencies. This is error-prone and unnecessary for a Boot executable JAR.

Prefer the launcher mechanism provided by the plugin unless you have a specialized deployment requirement.

## 29. Practice exercises

### Exercise 1 — Create a plain library JAR

Create a `math-lib` module with class `MathHelper` and method `square(int value)`. Use the Gradle `java-library` plugin, run `jar`, and verify the class sits at the root package path in the artifact.

### Exercise 2 — Try running the library JAR with java -jar

Try:

```bash
java -jar math-lib.jar
```

Observe the entry-point error when the manifest lacks `Main-Class`. Explain why this is not a library build failure.

### Exercise 3 — Use the library via classpath

Create a `Main` class in another module that calls `MathHelper.square(5)`. Build the class and run with `-cp` containing the library JAR, noting classpath separator differences between Windows and Linux/macOS.

### Exercise 4 — Create a Boot executable JAR

Create a Spring Boot application with a `CommandLineRunner`. Use `bootJar` and run via:

```bash
java -jar app.jar
```

Observe the runner and startup logs.

### Exercise 5 — Compare the two artifacts

In a Boot app, build both a plain JAR and an executable JAR if the build allows. Use `jar tf` to check the class path, `BOOT-INF/classes`, `BOOT-INF/lib`, and manifest.

### Exercise 6 — Analyze Main-Class and Start-Class

Open `META-INF/MANIFEST.MF` of a Boot executable JAR. Identify the launcher name and application main class, then explain the `java -jar` flow.

### Exercise 7 — Multi-module project

Create `shared-lib` and `main-app`. Have `main-app` depend on `shared-lib` and build `bootJar`. Verify `shared-lib.jar` resides in `BOOT-INF/lib` of the app's executable JAR.

### Exercise 8 — Reproduce the error of using a Boot JAR as a library

Create a Boot executable JAR, then try using it as a regular classpath dependency in another project. Observe the difference compared to a plain JAR with classes at root, then redesign it as a library module.

### Exercise 9 — Reading resources from a JAR

Place `data/sample.txt` in `src/main/resources`. Read it with `getResourceAsStream` instead of `Path.of("src/main/resources/...")`. Compare behavior in the IDE and when running the executable JAR.

### Exercise 10 — Two main classes

Create two classes with `public static void main` in the same application module. Configure `springBoot.mainClass` or `bootJar.mainClass` to pick the entry point. Check `Start-Class` in the manifest.

### Exercise 11 — Maven repackage

Create a Maven Spring Boot application with `spring-boot-maven-plugin` and the `repackage` execution. Run `mvn package` and inspect the artifacts, distinguishing the plain version from the repackaged version.

### Exercise 12 — Runtime-only dependency

Create an application using a driver or integration library at runtime. Verify the dependency is present in `BOOT-INF/lib` and distinguish `implementation`, `runtimeOnly`, and `testImplementation`.

### Exercise 13 — External configuration

Build a single executable JAR and run it sequentially with two different profiles/configs. Observe the effective configuration changing without rebuilding the artifact.

### Exercise 14 — Java version mismatch

Compile an application targeting a higher Java release than the test Java runtime (in an allowed environment). Observe the version error and explain why packaging a Boot JAR does not automatically bundle a JRE.

### Exercise 15 — Docker deployment

Create a container image containing a Java runtime and Boot executable JAR. Launch it with `java -jar`, then explain the JAR's role relative to the image.

## 30. Official references

- [Spring Boot Reference — Executable Jars](https://docs.spring.io/spring-boot/reference/packaging/executable-jar/index.html): `BOOT-INF` structure, nested JARs, and launcher.
- [Spring Boot Reference — Gradle Plugin](https://docs.spring.io/spring-boot/gradle-plugin/index.html): `bootJar`, `bootRun`, and packaging tasks.
- [Spring Boot Reference — Maven Plugin](https://docs.spring.io/spring-boot/maven-plugin/index.html): `repackage` goal and artifact configuration.
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): how applications read configuration outside the artifact.
- [Gradle Documentation — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): creating library JARs and distinguishing API vs. implementation dependencies.
- [Apache Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/): creating standard JARs.
- [Oracle Java Documentation — The JAR File Format](https://docs.oracle.com/javase/8/docs/technotes/guides/jar/jar.html): JAR structure and manifest.

**Principle to remember:** A library JAR is an artifact loaded as a dependency, typically placing classes directly along package paths at root; a Spring Boot executable JAR is an artifact used to **run an application**, typically placing classes in `BOOT-INF/classes`, dependencies in `BOOT-INF/lib`, and using a launcher in the manifest. Choose `jar` for reusable libraries, `bootJar` or `spring-boot:repackage` for application entry points, and always inspect actual artifact contents when facing classpath or startup issues. A `.jar` extension only indicates the archive format—not whether it was packaged correctly for the role you need.
