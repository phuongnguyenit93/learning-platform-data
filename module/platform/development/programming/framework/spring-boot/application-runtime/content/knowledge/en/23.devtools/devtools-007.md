# Diagnosing Classloader Errors in Multi-Module Projects Using Spring Boot Devtools

## 1. Symptoms and Objective

In a Spring Boot project with multiple Maven/Gradle modules, developers may run into cases where code runs fine as a packaged JAR yet fails when launched from an IDE or after a Devtools automatic restart:

- `ClassCastException` stating a class cannot be cast to the same class name.
- `ClassNotFoundException`, `NoClassDefFoundError`, or `LinkageError` in a shared module.
- An annotation or service provider discovered on the initial run yet missing after a restart.
- Editing code in a library module, IDE reports build succeeded, yet the app keeps old behavior.
- Errors appearing only after the second or third restart.
- Disabling Devtools restart makes the error vanish; switching to a normal JAR run cannot reproduce it.

These symptoms do not automatically prove Devtools has a bug. We must distinguish **classloader identity**, **classpath visibility**, **dependency/version mismatch**, **stale build output**, and **lifecycle leaks**.

This lesson outlines a reproducible method: determine where code is actually loaded from, measure each class's loader, test disabling restart under identical conditions, configure `META-INF/spring-devtools.properties` when needed, and re-verify the original bug. Examples use **Spring Boot 3.5.x and Java 17+**.

## 2. Why Do Classes with the Same Name Not Share the Same Type?

In Java, class identity depends on at least two factors:

~~~text
Class identity = (binary name, defining ClassLoader)

Example:
  example.contract.SharedMessage  defined by Loader A
  example.contract.SharedMessage  defined by Loader B

Despite identical binary names, these are two distinct Class objects
when A and B actually define the class independently.
~~~

An object of the type defined by Loader A cannot automatically be cast to the identically named type defined by Loader B. That is why you can see messages like:

~~~text
ClassCastException:
example.contract.SharedMessage cannot be cast to
example.contract.SharedMessage
~~~

Do not look solely at the FQCN and conclude the compiler or JVM is broken. Measure **`Class.getClassLoader()`**, compare the two `Class` objects with **`==`**, and inspect **`CodeSource`**. A loader can also delegate to a parent; thus the loader asked to locate a class is not necessarily the loader that ultimately defined it.

### Common Misconceptions

- Two distinct classes with the **same name** are not guaranteed to be binary-compatible or identical.
- An identical **`CodeSource` URL** does not guarantee two `Class` objects share identity if defined independently by two loaders.
- The loader shown in a log is not necessarily the root cause; a dependency may be missing or packaged incorrectly.
- `ClassCastException` can also appear in plugin architectures, OSGi, or custom `URLClassLoader` setups unrelated to Spring Boot Devtools.

## 3. Base Classloader and Restart Classloader

Spring Boot Devtools uses **two classloaders** for fast automatic restarts:

| Loader | Typically Loads | Behavior on Devtools Restart |
| --- | --- | --- |
| Base | Stable libraries from JARs, e.g. third-party dependencies | Usually reused |
| Restart | Application classes and resources under development, typically from IDE output directories | Replaced with a new loader |

Diagram:

~~~text
JVM does not exit
      |
      +-- Base ClassLoader
      |     Spring/third-party JARs
      |     some modules resolved as JARs
      |     retained across restarts
      |
      +-- Restart ClassLoader #1
            app/target/classes
            some IDE open projects
               |
      Devtools detects classpath change
               |
      +-- Base ClassLoader stays alive
      |
      +-- Restart ClassLoader #2
            initializes new ApplicationContext
            reloads application classes
~~~

This mechanism reduces restart time by avoiding reloading every JAR. It also introduces a boundary: code in **base** may load before code in **restart**, or a module may be treated as a stable JAR even though its source is edited in the same repository.

Notably, the Spring Boot 3.5 Reference states that **each open project in the IDE is normally loaded via the restart loader**, whereas **regular JAR files are normally loaded via the base loader**. With Maven `spring-boot:run` or Gradle `bootRun`, the module containing `@SpringBootApplication` may belong to restart while other modules resolved as JARs belong to base. These are **conditional defaults**, not a substitute for inspecting the real runtime classpath.

### Multi-Module Projects Easily Have Two Classpath Shapes

~~~text
IDE opens both modules:
  app/target/classes/                 -> usually restart
  shared-contract/target/classes/     -> usually restart
  spring-core-*.jar                   -> usually base

Maven runs only the app module:
  app/target/classes/                 -> usually restart
  ~/.m2/.../shared-contract-*.jar     -> usually base
  spring-core-*.jar                   -> usually base
~~~

If a module provides DTOs, annotations, interfaces, proxies, or library integrations that must load alongside application classes, that difference can cause `ClassCastException`, reflection failures, or missing types.

**Keep clear:** base and restart coexisting is the normal design. Bugs appear only when classes are defined incompatibly across loaders, a loader lacks visibility, or objects from an old restart generation are retained.

## 4. First Test: Completely Disable Devtools Restart

Spring Boot advises that the first diagnostic step is to **temporarily disable restart**. If the error disappears, Devtools' classloader boundary warrants investigation.

### Reliable Way: JVM System Property

In your IDE's **VM options** for launching the application:

~~~text
-Dspring.devtools.restart.enabled=false
~~~

Or set **before `SpringApplication.run`**:

~~~java
package example.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AppWithoutRestart {

    public static void main(String[] args) {
        System.setProperty(
                "spring.devtools.restart.enabled", "false");
        SpringApplication.run(AppWithoutRestart.class, args);
    }
}
~~~

This is a **complete Java file** given matching Spring Boot dependencies; use it as a diagnostic option, not simultaneously as an entry point alongside the demo in Section 8.

In the Maven plugin you can pass a JVM argument to the application's JVM:

~~~bash
mvn -pl app spring-boot:run -Dspring-boot.run.jvmArguments=-Dspring.devtools.restart.enabled=false
~~~

Argument quoting can vary by shell; in an IDE, entering VM options directly in the Run Configuration is easier to control. The key rule: the property must reach **the application's JVM before `run`**, not merely the Maven launcher in another process.

### Why Setting It in application.properties Is Not Enough

~~~properties
spring.devtools.restart.enabled=false
~~~

Per the Spring Boot 3.5 Reference, this normally **stops watching files for restart**, yet **the restart classloader may still be initialized**. Therefore, it is not a complete test to isolate the classloader. When you need to eliminate restart support completely, use an early System property or remove the Devtools dependency from the classpath.

### Comparison Matrix

| State | Observation | Tentative Conclusion |
| --- | --- | --- |
| Devtools restart enabled | `ClassCastException` occurs | Not enough proof yet |
| Same launch mode, System property disables restart | Error disappears | Strong evidence pointing to the Devtools boundary |
| Both fail | Check dependencies, JARs, versions, missing classes |
| `java -jar` works, IDE fails | Compare classpaths and packaging; not solely Devtools |
| Fails only after multiple restarts | Check static caches, threads, TCCL, and classloader leaks |

Never change **launch mode, Java version, Maven profile, and restart config** simultaneously when comparing. Change one variable at a time so results remain explainable.

## 5. Gathering Evidence: Exact Class, Exact Loader

For types appearing in stack traces, collect:

1. Binary class name.
2. **`Class.getClassLoader()`** identity.
3. Class origin URL via **`getProtectionDomain().getCodeSource()`**, if present.
4. **`Thread.currentThread().getContextClassLoader()`** on the failing thread.
5. Resource URLs for **`path/to/Type.class`** via `getResources`.
6. Build tool dependency tree and runtime classpath.
7. Failure timing: initial startup, after compile, or after several restarts.
8. Behavior when restart is completely disabled.

A Java helper:

~~~java
package example.app;

import java.security.CodeSource;

public final class LoaderInfo {

    private LoaderInfo() {
    }

    public static void print(String label, Class<?> type) {
        ClassLoader loader = type.getClassLoader();
        CodeSource source =
                type.getProtectionDomain().getCodeSource();

        System.out.println(label + ".name=" + type.getName());
        System.out.println(label + ".loader="
                + (loader == null ? "bootstrap"
                        : loader.getClass().getName() + "@"
                        + Integer.toHexString(
                                System.identityHashCode(loader))));
        System.out.println(label + ".source="
                + (source == null
                        ? "<unknown>"
                        : source.getLocation()));
    }
}
~~~

This is a **compilable Java helper**, without `main`; call it from other code. **`CodeSource`** can be null, especially for bootstrap/generated classes, and identity hashcodes are not stable across JVM runs.

Snippet to run on the exact failing thread:

~~~java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();

System.out.println("TCCL=" + tccl);
~~~

This is an illustrative snippet. **TCCL** is especially helpful when libraries use reflection, `ServiceLoader`, resource lookup, or deserialization.

Never log classpath paths/`CodeSource` alongside credentials or internal data on public endpoints. Instrumentation should happen strictly in dev/test environments.

## 6. Reading Exceptions in Context

| Symptom | Priority Root-Cause Category |
| --- | --- |
| `Foo cannot be cast to Foo` | Two defining classloaders or an old restart generation |
| `ClassNotFoundException` | Current loader cannot locate type or missing artifact |
| `NoClassDefFoundError` | Class failed to load/initialize; possible missing dependency or init failure |
| `LinkageError: loader constraint violation` | Visibility/type constraint conflict across loaders |
| `NoSuchMethodError` | Binary incompatibility, stale runtime version or artifact |
| `TypeNotPresentException` | Reflection/annotation references an absent type |
| `@Component`/`@Configuration` not detected | Scanning/conditionals or annotation type/loader mismatch |
| `ObjectInputStream ClassNotFoundException` | Deserialization uses a loader that cannot see restart classes |
| Edited code yet unchanged behavior | Classpath not compiled/copied or stale JAR in `~/.m2` |

**Never map one exception class to a single fixed cause.** For instance, `NoClassDefFoundError` can stem from an earlier static initializer failure; read `Caused by` and the very first failure timestamp. `NoSuchMethodError` is usually a compile-time vs. runtime API mismatch rather than automatically a Devtools issue.

## 7. Practical Multi-Module Maven Example

We create a reactor containing:

- **`shared-contract`:** a Java 17 JAR holding only a shared record.
- **`app`:** a Spring MVC executable application depending on `shared-contract`, with `spring-boot-devtools`.
- An `ApplicationRunner` printing loaders, `CodeSource`, TCCL, and intentionally creating a class identity mismatch via an independent `URLClassLoader` to illustrate `ClassCastException`.

### Directory Tree

~~~text
multi-module-devtools/
  pom.xml
  shared-contract/
    pom.xml
    src/main/java/example/contract/SharedMessage.java
  app/
    pom.xml
    src/main/java/example/app/MultiModuleApplication.java
    src/main/resources/application.properties
~~~

### Root pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>multi-module-devtools</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>shared-contract</module>
        <module>app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
    </properties>
</project>
~~~

The root is an aggregator POM. The Spring Boot parent manages Java version, dependency BOM, and plugin versions for modules.

### shared-contract/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>example</groupId>
        <artifactId>multi-module-devtools</artifactId>
        <version>0.0.1-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>shared-contract</artifactId>
    <packaging>jar</packaging>
</project>
~~~

This is a plain JAR module with no Spring or Devtools dependencies. Depending on whether the IDE resolves it as an output directory or Maven pulls the JAR from the repository, classloader placement can differ.

### shared-contract/src/main/java/example/contract/SharedMessage.java

~~~java
package example.contract;

public record SharedMessage(String value) {
}
~~~

This is a valid Java 17 record with public constructor **`SharedMessage(String)`** and accessor **`value()`**.

### app/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>example</groupId>
        <artifactId>multi-module-devtools</artifactId>
        <version>0.0.1-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>

    <dependencies>
        <dependency>
            <groupId>example</groupId>
            <artifactId>shared-contract</artifactId>
            <version>0.0.1-SNAPSHOT</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-devtools</artifactId>
            <optional>true</optional>
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

Devtools is declared only in the executable `app` module with **`optional=true`**. In Gradle, the standard configuration is **`developmentOnly("org.springframework.boot:spring-boot-devtools")`**. Do not add Devtools to every module's dependencies.

### app/src/main/resources/application.properties

~~~properties
spring.application.name=multi-module-devtools
server.address=127.0.0.1
server.port=8080
~~~

Bound to localhost since this demo app is for development and diagnostics. In real deployment environments, the app may need `0.0.0.0` depending on network policies.

### app/src/main/java/example/app/MultiModuleApplication.java

~~~java
package example.app;

import java.net.URL;
import java.net.URLClassLoader;
import java.security.CodeSource;
import java.util.Enumeration;

import example.contract.SharedMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MultiModuleApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiModuleApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectClassLoaders() {
        return args -> {
            printType("APP", MultiModuleApplication.class);
            printType("SHARED", SharedMessage.class);

            ClassLoader tccl =
                    Thread.currentThread().getContextClassLoader();
            System.out.println("TCCL=" + label(tccl));

            if (tccl != null) {
                Enumeration<URL> resources = tccl.getResources(
                        "example/contract/SharedMessage.class");
                int count = 0;
                while (resources.hasMoreElements()) {
                    count++;
                    System.out.println("SHARED_RESOURCE_"
                            + count + "=" + resources.nextElement());
                }
                System.out.println("SHARED_RESOURCE_COUNT=" + count);
            }

            demonstrateIdentity();
            System.out.println("DIAGNOSTICS_DONE");
        };
    }

    private static void printType(String key, Class<?> type) {
        CodeSource source =
                type.getProtectionDomain().getCodeSource();

        System.out.println(key + "_CLASS=" + type.getName());
        System.out.println(key + "_LOADER="
                + label(type.getClassLoader()));
        System.out.println(key + "_SOURCE="
                + (source == null ? "<unknown>"
                        : source.getLocation()));
    }

    private static String label(ClassLoader loader) {
        if (loader == null) {
            return "bootstrap";
        }
        return loader.getClass().getName() + "@"
                + Integer.toHexString(
                        System.identityHashCode(loader));
    }

    private static void demonstrateIdentity() throws Exception {
        CodeSource source =
                SharedMessage.class.getProtectionDomain()
                        .getCodeSource();

        if (source == null || source.getLocation() == null) {
            System.out.println("ISOLATION_SKIPPED=no-code-source");
            return;
        }

        URL root = source.getLocation();

        // Intentional experiment, NOT a Devtools bug.
        try (URLClassLoader isolated = new URLClassLoader(
                new URL[] { root }, null)) {

            Class<?> again = Class.forName(
                    "example.contract.SharedMessage",
                    true, isolated);

            System.out.println("SAME_BINARY_NAME="
                    + again.getName().equals(
                            SharedMessage.class.getName()));
            System.out.println("SAME_CLASS_IDENTITY="
                    + (again == SharedMessage.class));

            Object otherInstance = again.getConstructor(String.class)
                    .newInstance("other-loader");

            try {
                SharedMessage unexpected =
                        (SharedMessage) otherInstance;
                System.out.println("UNEXPECTED_CAST="
                        + unexpected.value());
            } catch (ClassCastException expected) {
                System.out.println("ISOLATED_CAST_FAILED=true");
            }
        }
    }

    @RestController
    static class PingController {

        @GetMapping("/demo/ping")
        public String ping() {
            return new SharedMessage("pong").value();
        }
    }
}
~~~

### Why It Is Runnable

- All imports are declared. The app runs on Java 17 with the record type in `shared-contract`.
- Spring Boot Starter Web starts embedded Tomcat; the nested static `@RestController` is picked up by component scanning.
- `ApplicationRunner` runs after context refresh.
- `URLClassLoader` is constructed from `SharedMessage`'s `CodeSource` URL. If `shared` is a JAR from the Maven repository, that URL points to the `.jar` file. If imported as an output directory, it points to the classes directory.
- The loader has **`null`** parent in this experiment so it does not delegate `SharedMessage` to the application loader; it still accesses bootstrap Java core classes.
- Both `Class` objects share the same FQCN yet differ in defining loader. The cast is **intentionally** attempted and catches `ClassCastException`.
- If `CodeSource` is absent, the demo logs `ISOLATION_SKIPPED` instead of guessing paths.
- Specific `CodeSource` values, hashcodes, resource URL counts, and classloaders depend on the environment.

This is a **normally running application**; the intentional `ClassCastException` is caught so the program continues. It is not meant to fail Spring context startup.

### Build and Run

In the root directory:

~~~bash
java -version
mvn -version

# Build all module dependencies and install into local Maven repository:
mvn -pl app -am install -DskipTests

# Then run only the module with the Spring Boot main class:
mvn -pl app spring-boot:run
~~~

The first command uses **`-pl app -am`** to build `app` and its dependent reactor modules. The second runs only `app`, so `shared-contract` may be resolved from the JAR installed in the local Maven repository. If you import the entire reactor into an IDE and run `main` directly, the classpath shape may differ.

Do not run **`spring-boot:run`** on every reactor module, since `shared-contract` has no Spring Boot main application.

While the app is running, check:

~~~bash
curl -i http://127.0.0.1:8080/demo/ping
~~~

Body:

~~~text
pong
~~~

Expected HTTP status is 200 when the server operates normally. HTTP headers and version formatting depend on Tomcat/`curl`.

### Self-Printed Markers

If the `CodeSource` URL can be used by an independent `URLClassLoader`, these markers have deterministic values:

~~~text
APP_CLASS=example.app.MultiModuleApplication
SHARED_CLASS=example.contract.SharedMessage
SAME_BINARY_NAME=true
SAME_CLASS_IDENTITY=false
ISOLATED_CAST_FAILED=true
DIAGNOSTICS_DONE
~~~

Example **illustrating only the shape** of varying lines:

~~~text
APP_LOADER=org.springframework.boot.devtools.restart.classloader.RestartClassLoader@...
SHARED_LOADER=jdk.internal.loader.ClassLoaders$AppClassLoader@...
SHARED_SOURCE=file:/.../.m2/repository/example/shared-contract/0.0.1-SNAPSHOT/shared-contract-0.0.1-SNAPSHOT.jar
TCCL=org.springframework.boot.devtools.restart.classloader.RestartClassLoader@...
SHARED_RESOURCE_COUNT=1
~~~

Do not write tests asserting on **`...`**, loader identity hashcodes, exact paths, or count `1`. What matters is comparing **`APP_LOADER` vs. `SHARED_LOADER`** and whether **`SOURCE` is a classes directory or a JAR**.

**Important:** even after fixing classloader mapping successfully, **`ISOLATED_CAST_FAILED=true`** will still appear because the demo deliberately creates a third isolated loader. Do not treat it as proof the fix failed.

## 8. Comparing Runs with Restart Enabled vs. Disabled

Run the app as above with Devtools enabled and save the diagnostic output. Then stop the JVM completely and re-run with the VM option:

~~~text
-Dspring.devtools.restart.enabled=false
~~~

In an IDE, place this in the Run Configuration. With the Maven plugin, pass the JVM argument as shown in Section 4.

Compare at least:

| Data | Restart Enabled | Restart Disabled |
| --- | --- | --- |
| `APP_LOADER` | Likely `RestartClassLoader` | Usually standard application loader |
| `SHARED_LOADER` | Base or restart depending on classpath | Follows classpath without Devtools restart |
| `APP_SOURCE` | `app/classes` | Likely still `app/classes` |
| `SHARED_SOURCE` | JAR or classes directory | Follows Maven/IDE resolution |
| Original business bug | Present / absent | Present / absent |
| `URLClassLoader` intentional cast | Still fails by demo design | Still fails by demo design |

Evaluate the **original business bug**, not the intentional type-identity experiment.

If the bug occurs only when restart is enabled, prioritize module classpath mapping, TCCL, reflection/deserialization, or references from an old restart loader. If it occurs in both runs, prioritize dependency versions and build output.

## 9. Configuring META-INF/spring-devtools.properties

Spring Boot 3.5 provides **`META-INF/spring-devtools.properties`** to specify which classpath entries are pulled into the restart loader or pushed down to the base loader.

Example after verifying `shared-contract` sits in a JAR in base and wanting that module in restart:

Create file:

~~~text
app/src/main/resources/META-INF/spring-devtools.properties
~~~

Content:

~~~properties
# Pattern applies to classpath entry, not Java package name.
restart.include.shared-contract=.*shared-contract-0[.]0[.]1-SNAPSHOT[.]jar
~~~

Explanation:

- Key starts with **`restart.include.`**.
- Suffix **`shared-contract`** identifies the rule; every key must be unique.
- The regex matches classpath entries containing filename **`shared-contract-0.0.1-SNAPSHOT.jar`**.
- Using **`[.]`** for literal dots avoids backslash escaping quirks in Java `.properties` files.
- If the artifact version or classpath path differs, adjust the regex to match the **actual running classpath entry**.
- If importing the shared module as an output directory, the entry will not contain the JAR name; this regex will not match.

Example for a module classes directory:

~~~properties
restart.include.shared-classes=.*shared-contract.*target.*classes.*
~~~

This is a relatively broad regex for illustration; narrow it to match the real path and use it only if the module is not already in the restart loader. Do not copy both rules into every project without measuring.

### Moving a Library Down to Base

You can use:

~~~properties
restart.exclude.legacy-library=.*legacy-library-1[.]2[.]3[.]jar
~~~

The **`restart.exclude.`** key prefix assigns the matching classpath entry to the **base classloader**. Only do this when you know the library needs to remain stable and does not depend on application-specific types from the restart loader.

### Important Spring Boot Rules

- The file must be at **`META-INF/spring-devtools.properties`**, copied onto the runtime classpath.
- Key prefixes are **`restart.include.`** and **`restart.exclude.`**.
- Property values are **regexes applied to classpath paths**, not package-name rules.
- All keys must be unique.
- Spring Boot reads **all** `META-INF/spring-devtools.properties` files on the classpath, including those inside library JARs.
- Loader mapping rules **cannot be replaced with standard System properties**.
- After adding/editing the file, restart the JVM for a clean test, then re-check **`APP_LOADER`**, **`SHARED_LOADER`**, and the actual error.
- Never pull all third-party libraries into the restart loader without reason; doing so reduces restart speed and can cause other problems.

### What Is NOT Loader Mapping?

In **`application.properties`** there are:

~~~properties
spring.devtools.restart.exclude=static/**,public/**
spring.devtools.restart.additional-exclude=generated/**
spring.devtools.restart.additional-paths=../shared-contract/src/main
~~~

These properties configure the **watcher**: which changed paths trigger restart/reload, and watching paths outside the classpath. They **do not move modules to the base or restart loader**.

Comparison:

| Name | Where Placed | Effect |
| --- | --- | --- |
| `spring.devtools.restart.exclude` | `application.properties` | Avoids full restart when specific resources change |
| `spring.devtools.restart.additional-exclude` | `application.properties` | Appends exclusion paths for the watcher |
| `spring.devtools.restart.additional-paths` | `application.properties` | Watches additional paths |
| `restart.include.shared-contract` | `META-INF/spring-devtools.properties` | Moves classpath entry to restart loader |
| `restart.exclude.legacy-library` | `META-INF/spring-devtools.properties` | Moves entry to base loader |

**Never put `restart.include.shared-contract` in `application.properties` expecting classloader mapping to work.**

## 10. Reflection and Undetected Annotations

The Spring Boot Devtools Reference notes that certain classes loaded by **reflection**, especially **annotations**, may be loaded early by a parent loader before application classes using those annotations are loaded by the restart loader.

How to investigate:

1. Identify the annotation FQCN, defining module, and runtime `CodeSource`.
2. Print the loader of the annotation type used by the framework and compare it with the type seen by the application.
3. Check for missing dependencies, component-scan base packages, and `@Conditional` before blaming classloaders.
4. Disable Devtools restart completely and check if results change.
5. If a boundary mismatch is confirmed, consider placing the project-related annotation module in the restart loader via an include rule.
6. Re-test startup, reflection, and proxy behavior across the next restart.

A class not being scanned by Spring is **not automatically** a classloader bug: package scanning, annotation metadata, and condition evaluation can also be the culprit.

## 11. ServiceLoader and Thread Context ClassLoader

Some libraries discover plugins via **`java.util.ServiceLoader`**, using TCCL or an explicit loader.

Illustrative snippet:

~~~java
ServiceLoader<MyService> loader =
        ServiceLoader.load(
                MyService.class,
                Thread.currentThread().getContextClassLoader());
~~~

This snippet is not standalone: it requires importing **`java.util.ServiceLoader`** and the **`MyService`** interface. When a provider implementation lives in restart while the interface is defined twice by different loaders, changing TCCL alone cannot fix type identity. Verify:

- Which loader defined the service interface?
- Does the provider implementation have visibility and matching type identity?
- Does the JAR have a proper `META-INF/services` file?
- Does runtime TCCL point to the right loader?
- Are module builds and dependency versions consistent?

Never call `setContextClassLoader` haphazardly to mask a missing dependency. If a library requires temporarily swapping TCCL, restore it in `finally` and check the library's contract.

## 12. ObjectInputStream and Serialization

Spring Boot 3.5 docs state that Devtools restart may not play nicely with **standard `ObjectInputStream`**, because class resolution does not always use a loader that can see application classes.

When data is trusted and controlled for deserialization, Spring Framework provides **`ConfigurableObjectInputStream`**:

~~~java
import java.io.InputStream;

import org.springframework.core.ConfigurableObjectInputStream;

try (InputStream input = /* trusted input */;
     ConfigurableObjectInputStream in =
             new ConfigurableObjectInputStream(
                     input,
                     Thread.currentThread().getContextClassLoader())) {

    Object obj = in.readObject();
}
~~~

This is an **illustrative snippet**, not a standalone runnable file. Real input, exception handling, and data types must be defined by your system.

**Security warning:** Java native deserialization of untrusted data poses severe risks. Changing the classloader for `ObjectInputStream` **does not make deserialization safe** and does not protect against gadget attacks. Whenever possible, use explicit formats/schemas or controlled allowlists instead of deserializing arbitrary objects.

If the error comes from a third-party library that ignores TCCL during deserialization, Spring Boot recommends contacting the library maintainers. No single Devtools regex guarantees fixing all such cases.

## 13. Errors That Only Occur After Multiple Restarts

Devtools replaces the old restart classloader with a new instance. Yet an object in the **base loader** or a long-lived background thread can retain references to classes, beans, proxies, or TCCLs from the previous restart loader:

~~~text
Base classloader
    |
    +--> static cache / shared library singleton
                  |
                  +--> Class<?> or object from RestartLoader #1

RestartLoader #2 is created
    |
    +--> app uses new class with the same name
                  |
                  +--> cast/proxy/metadata can be incompatible
~~~

Common causes:

- Static `Map` in a base library holding keys of application `Class` objects.
- `ThreadLocal`/MDC on thread pools not cleaned up.
- Executors, timers, schedulers, or listeners not unregistered when the context closes.
- Third-party caches holding Spring bean proxies from an old `ApplicationContext`.
- `ClassLoader`/TCCL stored as a static reference.
- JDBC/messaging clients not closed per contract.

Consequences can include `ClassCastException` after restart, resource/thread leaks, or growing metaspace. **Do not conclude every metaspace fluctuation is a classloader leak**; inspect classloader statistics, heap roots, and actual references.

Remediation: stop background workers when `ApplicationContext` closes, clear lifecycle-bound cache/listener registrations, clean up `ThreadLocal`s in scope, close clients, and avoid caching restart-loader references in base singletons.

Devtools relies on the **`ApplicationContext` shutdown hook** for safe restarts. If code disables the hook via **`SpringApplication.setRegisterShutdownHook(false)`**, docs warn restart will not work properly.

## 14. When Editing Source Does Not Trigger Devtools Restart

Devtools watches **classpath resources**, not arbitrary `.java` files anywhere.

- IntelliJ IDEA usually needs **Build > Build Project** or appropriate auto-compile settings.
- Eclipse can update output on save if automatic build is enabled.
- Maven/Gradle must compile so class files/resources update on the runtime classpath.
- A shared module enters the app as a JAR in **`~/.m2/repository`**: editing only shared's source does not update the old JAR.
- Compiling multiple modules in waves can make the watcher restart while output directories are half-updated.

You can tune the watcher in slow environments:

~~~properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
~~~

These numbers are experimental examples, not optimal defaults for every machine. They adjust polling frequency and quiet period; they do not move classes to another loader.

You can use a trigger file:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

The file must exist on the classpath. Updating the trigger file makes Devtools **check** detected classpath changes without necessarily restarting if no meaningful changes exist.

### Rebuilding the Shared Module Properly

~~~bash
mvn -pl app -am clean install -DskipTests
mvn -pl app dependency:tree
mvn -pl app spring-boot:run
~~~

These commands are for the demo project. Do not wipe all of `~/.m2` or upgrade multiple library versions without evidence; a clean rebuild verifies stale artifacts, not a silver bullet.

## 15. Distinguishing Dependency Errors from Classloader Errors

Common cases:

### Case A: Same FQCN Exists in Two JARs

A shaded library accidentally packages classes from a shared module while `app` also depends on the original JAR. **`getResources("example/contract/SharedMessage.class")`** returns multiple URLs. Fix dependencies, shading/relocation, and version alignment—do not just add `restart.include`.

### Case B: NoSuchMethodError After Changing a Shared DTO

`app` compiled against the new API while runtime has an old shared JAR. Compare `CodeSource`, dependency tree, and method signatures; rebuild/install the shared module. This error persists even with Devtools completely off.

### Case C: ClassNotFoundException in a Reflection Library

The framework uses the base loader or TCCL and cannot see a type in restart. Confirm the type is on the runtime classpath first; if present with wrong visibility, try including the module properly.

### Case D: Java Serialization Cannot Read Class

`ObjectInputStream` resolves the type via the wrong loader. Check Spring Boot's documented limitation, TCCL, and data origin. Never deserialize untrusted bytes.

### Case E: Code Behaves Differently Between IDE and JAR

The IDE runs modules as `target/classes`, whereas the executable JAR has nested libraries and Devtools auto-disabled. Those are **two different runtime classpaths**; inspect each configuration instead of assuming a passing JAR run proves every classloader rule is right.

## 16. Notes on Packaged Applications and Production

Spring Boot Devtools normally **disables itself** in fully packaged applications, especially when run via **`java -jar`**. Spring Boot Maven/Gradle repackaging also **excludes Devtools from executable archives by default** in standard configurations.

There is a way to force restart enabled via **`-Dspring.devtools.restart.enabled=true`**, yet **never do this in production**: documentation warns shipping Devtools to production creates security risks. This lesson is strictly limited to development/test environments.

For production runtimes:

- Never expose classpath/loader debug endpoints to public users.
- Never leak secrets into classpath logs, heap dumps, or uncontrolled shared stack traces.
- Never rely on Devtools to self-restart production Pods.
- Use proper deployment/restart pipelines, health probes, and observability.
- Verify duplicate dependencies and binary compatibility in build/release pipelines.

Spring Boot also notes auto-restart **is not supported with AspectJ weaving** per Devtools documentation; certain `ResourceLoader` overrides also have limitations. Inspect the specific setup instead of trying to force `restart.include` on every problem.

## 17. 12-Step Runbook for a Real Incident

1. **Reproduce:** record Spring Boot/JDK version, IDE, Maven/Gradle task, recently edited module, and restart count.
2. **Capture the exception chain:** read root cause, FQCN, method/class signatures, and loader names in messages.
3. **Print `Class.getClassLoader()`:** for expected type, actual type, and annotations/proxies if involved.
4. **Print `CodeSource`:** determine whether `.class` comes from `app/target/classes`, `module/target/classes`, or a repository JAR.
5. **Read TCCL:** at the exact failing thread and call site.
6. **Check duplicate resources:** `ClassLoader.getResources()` and `dependency:tree`.
7. **Completely disable Devtools restart:** via JVM System property before `SpringApplication.run`.
8. **Compare under the same launch mode:** check if the error vanishes without changing JVM/profile simultaneously.
9. **Fix the root cause:** rebuild stale artifacts, fix duplicate dependencies, or use `META-INF/spring-devtools.properties` for loader boundaries.
10. **Clean restart:** verify the devtools properties file and new artifacts are on the runtime classpath.
11. **Re-check loader mapping and test the real bug:** do not use the intentionally isolated loader experiment to evaluate the fix.
12. **Regression check:** test full IDE reactor, Maven `bootRun`, editing the shared module across multiple restarts, and packaged JAR without Devtools.

### Quick Decision Table

| Signal | Next Step |
| --- | --- |
| Disabling restart fixes the error | Inspect base/restart boundary and include/exclude |
| Disabling restart still fails | Check dependency tree, binary API, missing artifacts |
| Stale shared JAR from Maven repository | Build/install the right module and restart app |
| Two URLs for the same class | Duplicate classes, shading, or version conflict |
| Annotation class loaded by base across boundary | Inspect reflective loader and include relevant module |
| `ObjectInputStream` fails to resolve app type | Check TCCL / `ConfigurableObjectInputStream` |
| Fails only after multiple restarts | Clean up threads, caches, references from old generations |
| No restart after editing code | Inspect compiled classpath output / watcher |
| Only packaged JAR works | Compare runtime classpaths / Devtools enablement |

## 18. Questions and Exercises

**Question 1.** Are two classes with the same binary name yet different defining `ClassLoader`s the same Java type?

**Question 2.** Why does Devtools have a base loader and a restart loader? Which classpath entries typically go into each?

**Question 3.** How does **completely** disabling restart to isolate a bug differ from setting `spring.devtools.restart.enabled=false` in `application.properties`?

**Question 4.** Why is an error like `Foo cannot be cast to Foo` not actually nonsensical?

**Question 5.** When the same module enters runtime as a JAR versus `target/classes`, how can classloader placement differ?

**Question 6.** Which file and property pull a shared module JAR into the restart classloader?

**Question 7.** Does `restart.include`'s regex match against package names or classpath paths?

**Question 8.** How do `spring.devtools.restart.exclude` and `restart.exclude.some-library` differ?

**Question 9.** Why are `SAME_BINARY_NAME=true`, `SAME_CLASS_IDENTITY=false`, and `ISOLATED_CAST_FAILED=true` in the demo not a Devtools bug?

**Question 10.** You run Maven `app` `spring-boot:run` after editing `shared-contract`. Why might you still see the old version?

**Question 11.** When `ServiceLoader` fails to find a provider, what else must you check besides TCCL?

**Question 12.** Does `ConfigurableObjectInputStream` make Java native deserialization of untrusted input safe?

**Question 13.** A static cache in the base loader retains `Class<?>` from an old restart loader. What is the risk?

**Question 14.** Is a successful `java -jar` run enough to confirm Devtools classloader mapping is right?

### Suggested Answers

1. No; type identity depends on both binary name and defining loader.
2. To reuse third-party classes and restart faster; JARs normally go to base, open projects/classes directories normally go to restart.
3. A JVM System property set before `run` disables restart support, whereas the application property may only stop the watcher.
4. Two identically named types can be defined by different loaders.
5. JARs normally enter base; open project source/output directories normally enter restart.
6. `META-INF/spring-devtools.properties` with `restart.include.<uniqueName>`.
7. Classpath entry paths.
8. One configures the watcher/resource restart trigger; the other configures classloader selection.
9. The independent `URLClassLoader` deliberately creates a separate defining loader.
10. The JAR in `~/.m2` may not have been rebuilt/installed yet.
11. Service interface identity, `META-INF/services`, and dependencies/classpath.
12. No; deserialization security still requires avoiding untrusted data.
13. Classloader/metaspace leaks or type mismatches across generations.
14. No; packaged JARs have a different classpath shape and Devtools is normally disabled.

## 19. Checklist Before Concluding

- [ ] Captured exact Lesson/Java/Boot/IDE/Maven versions reproducing the bug?
- [ ] Recorded actual classloader, expected classloader, and `CodeSource`?
- [ ] Checked TCCL on the right thread?
- [ ] Checked classpath resources for duplicate classes?
- [ ] Checked JAR/module versions via `dependency:tree`?
- [ ] Tested disabling restart completely via JVM property?
- [ ] Distinguished Devtools boundary errors from stale JARs/missing dependencies?
- [ ] Verified regex matches the right classpath entry?
- [ ] `META-INF/spring-devtools.properties` placed at the proper resource path?
- [ ] Distinguished `restart.include/exclude` from `spring.devtools.restart.exclude`?
- [ ] Rebuilt the shared module and inspected the real classpath?
- [ ] Observed restart generations after compiling?
- [ ] Checked TCCL, reflection, annotations, and `ServiceLoader` when relevant?
- [ ] Reviewed serialization security?
- [ ] Cleaned up background threads/static caches after restarts?
- [ ] Devtools restart is not enabled in production?
- [ ] Verified the original bug disappeared, not merely a log message change?
- [ ] Saved a regression test and documented why the module required include/exclude?

## 20. Conclusion and Official Documentation

When Devtools hits classloader errors in a multi-module project, do not attempt to fix it merely by disabling restart, wiping the entire Maven cache, or increasing watcher timeouts. Follow the evidence chain:

~~~text
Stack trace and FQCN
        |
        v
ClassLoader + CodeSource + TCCL
        |
        v
Inspect output directory / JAR / duplicates
        |
        v
Try -Dspring.devtools.restart.enabled=false
        |
        +--> Error persists: inspect artifacts / dependencies / APIs
        |
        +--> Error disappears: inspect base/restart boundary
                          |
                          v
         META-INF/spring-devtools.properties
         restart.include / restart.exclude
                          |
                          v
                 Rebuild, restart, verify
                 and re-test real error
~~~

**Official documentation:**

1. Spring Boot 3.5 Developer Tools — Diagnosing Classloading Issues, Customizing Restart Classloader, Restart vs. Reload, Known Limitations: https://docs.spring.io/spring-boot/3.5/reference/using/devtools.html
2. Spring Boot Maven Plugin 3.5 — Running your application: https://docs.spring.io/spring-boot/3.5/maven-plugin/run.html
3. Java 17 Class API — `getClassLoader`, `getProtectionDomain`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
4. Java 17 `URLClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
5. Java 17 `ServiceLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
6. Spring Framework 6.2 `ConfigurableObjectInputStream`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/ConfigurableObjectInputStream.html

Examples use **Java 17+**, **Spring Boot 3.5.16**, **multi-module Maven**, and Devtools strictly for development. Loader/hashcode/path outputs differ across IDEs, Gradle, Maven, and packaged JARs; always verify against the classpath of the exact failing environment.