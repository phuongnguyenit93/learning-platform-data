# Base Classloader and Restart Classloader in Spring Boot DevTools

## 1. Why Does DevTools Need Two Classloaders?

When developing a Java application, the usual way to restart is to stop the JVM and start it again. If every single class edit forced you to reload Spring Framework, logging libraries, JSON, database drivers, and hundreds of other JARs, the edit-compile-run loop would be quite slow.

**Spring Boot DevTools** partly solves this problem with a **two-classloader restart** technique:

- **Base classloader:** holds classes that rarely change, typically third-party dependency libraries packaged as JARs.
- **Restart classloader:** loads classes currently under development, typically classes located in the output directories of open project modules.

When a classpath change requires a restart, Spring Boot DevTools can **close the old application context, discard the old restart classloader, and create a new restart classloader**. Classes already loaded in the base classloader do not need to be reloaded the way they are on a fresh JVM startup.

```text
                    A JVM running in development mode
                    ┌─────────────────────────────────────────┐
                    │           BASE CLASSLOADER              │
                    │  Spring Framework / Boot JARs           │
                    │  Jackson, SLF4J, database driver ...    │
                    │               (retained)                │
                    └────────────────────┬────────────────────┘
                                         │
                             loads/delegates needed classes
                                         │
                  ┌──────────────────────▼──────────────────────┐
                  │          RESTART CLASSLOADER R1             │
                  │    Application.class / Service.class        │
                  │    Class output of module under development │
                  └──────────────────────┬──────────────────────┘
                                         │
                       edit source -> IDE/build compiles
                       classpath has change requiring restart
                                         │
                                   close context R1
                                   drop references to R1
                                         │
                  ┌──────────────────────▼──────────────────────┐
                  │          RESTART CLASSLOADER R2             │
                  │    New Application.class / Service.class    │
                  │    Base classloader is still reused         │
                  └─────────────────────────────────────────────┘
```

This diagram illustrates the *class loading idea*, not the entire classloader object tree in every JDK/IDE. The JVM also has bootstrap/platform/application classloaders and classloaders created by other libraries.

**Point to remember:** a DevTools restart is **not equivalent to starting a brand-new JVM**. Certain base classloader state and process-level resources can persist across restarts, while classes belonging to the restart classloader are reloaded.

Scope of this lesson: **Spring Boot 3.3.x, Spring Framework 6.x, and Java 17+** in development environments. Behavior may differ if the application is packaged as a production JAR, uses a custom launcher, Java agent, AspectJ weaving, or another reloading system.

## 2. What Is a Java Classloader?

A **ClassLoader** is responsible for finding and defining classes by binary name, such as `demo.customer.CustomerService`. The JVM does not identify a Java type **by class name alone**: a class's runtime identity is also tied to the **classloader that defined it**.

We can model this as:

```text
Type identity ≈ (binary class name, defining classloader)
```

This means:

```text
com.example.Order    loaded by loader A
com.example.Order    loaded by loader B
```

**Can be two distinct types**, even if the bytecode and package/class name are identical. An object of the type loaded by loader B cannot automatically be cast to `com.example.Order` loaded by loader A.

### 2.1. JVM and DevTools Classloaders

A typical Java application may use:

- **Bootstrap classloader**: loads core classes like `java.lang.String`; `String.class.getClassLoader()` usually returns `null` in Java.
- **Platform/application classloader**: loads runtime/application classes per JVM conventions.
- **Framework-created classloaders**: such as DevTools' `RestartClassLoader`.

In DevTools:

- The base classloader holds a relatively static set of classpath entries.
- The restart classloader loads classpath entries assigned to the restart portion and delegates loading of appropriate classes to base.
- The split is **based on classpath entries and configuration**, not on a rule like "packages starting with `com.example` always belong to restart".

**Do not conclude that two classes in the same package necessarily share the same classloader**. Part of the code from an open module may sit in a directory under the restart classloader, while another part packaged as a JAR sits in the base classloader.

### 2.2. A Class Is a Class Object

Java lets you inspect this:

```java
ClassLoader loader = SomeType.class.getClassLoader();
System.out.println(loader);
```

This snippet requires the type `SomeType` to exist. `loader` can differ across IDE runs, `bootRun`, tests, and packaged JARs.

For debugging, log the **classloader name**, **identity**, and **classpath entry origin** rather than just printing a vague short name. The class origin can be obtained via `ProtectionDomain/CodeSource` when available, though not every class has a non-null source or code source.

## 3. What Does the Base Classloader Hold?

According to Spring Boot DevTools 3.3 defaults:

- Third-party libraries distributed as **regular JARs** reside in the base classloader.
- Classes belonging to dependency modules already packaged as JARs can **also** reside in the base classloader, even if written by the same company.
- The base classloader **is not replaced on every DevTools restart** the way the restart classloader is.

Example:

```text
runtime classpath
  /home/dev/.gradle/caches/.../spring-context-6.x.jar      -> base
  /home/dev/.gradle/caches/.../jackson-databind-2.x.jar     -> base
  /home/dev/.gradle/caches/.../company-shared-1.2.jar       -> base
  /workspace/order-service/build/classes/java/main/        -> restart
```

This is an **illustrative classpath diagram**; actual paths and versions depend on your OS and build tool. Entry assignment can be altered via `spring-devtools.properties`.

Benefits:

1. No need to reload every large library after every application edit.
2. Stable metadata/runtime classes remain in base.
3. The restart loop is usually faster than a full JVM restart, especially when the classpath has many dependencies.
4. Business logic classes are updated in the new restart classloader after compilation.

### 3.1. Base Is Not "Immutable" in Terms of Data

A class in the base classloader can hold static fields, caches, and singleton instances managed by a library. Such state is **not automatically recreated** just because DevTools swaps the restart classloader.

Example code inside a library JAR:

```java
public final class SharedRegistry {
    private static final Map<String, Object> CACHE =
            new ConcurrentHashMap<>();

    // methods put/get...
}
```

This is an **illustrative snippet**, requiring imports for `Map` and `ConcurrentHashMap`, not a complete class. If this cache lives in the base classloader and holds references to objects created by an old restart classloader, it can prevent the old classloader from being garbage-collected.

Do not infer from the word "base" that base state resets when the application context restarts.

### 3.2. What Else Does Base Share?

Base avoids reloading libraries and Spring Framework repeatedly. Yet it also creates a **boundary** between library classes and project classes. A library using reflection, serialization, or class metadata caches must account for application classes changing loaders on each restart.

Good library design avoids holding long-lived references to application classes in static caches that are not cleared when the context closes, or implements cache invalidation keyed by classloader/context.

## 4. What Does the Restart Classloader Load?

By default, DevTools places **open projects in the IDE** in the restart classloader; with `mvn spring-boot:run` or `gradle bootRun`, the module containing `@SpringBootApplication` is loaded in the restart classloader, while other dependency JARs go into the base classloader.

An application class:

```java
package demo.devtools;

public final class GreetingService {
    public String hello() {
        return "hello";
    }
}
```

can be loaded by `org.springframework.boot.devtools.restart.classloader.RestartClassLoader` when DevTools restart is actually active.

After editing source and building:

```text
GreetingService.class in R1 ≠ GreetingService.class in R2
```

Even if the new class only changes a single string, the class defined by R2 is a **new runtime `Class` object**.

### 4.1. Why Not Patch the Already Loaded Class and Keep R1?

Under DevTools' restart mechanism, application classes are loaded by a **new classloader**. This differs from *hot code replacement* technologies that directly mutate bytecode of classes already defined by the JVM. Swapping the classloader lets DevTools restart quickly, yet **it is not an in-place patch of the class definition inside R1**.

Typical steps:

1. Edit `GreetingService.java`.
2. IDE or build tool compiles `GreetingService.class` in the classpath directory.
3. DevTools file watcher detects a meaningful change.
4. The old application context is closed by the restart mechanism.
5. Restart classloader R1 is dropped from active use; R2 is created.
6. The application is bootstrapped again using classes loaded by R2.
7. New beans are created and initialization callbacks run again per configuration.

This is a high-level timeline, not a guarantee that external libraries/drivers outside the context release every resource automatically. If an old thread retains context classloader R1 or a static cache in base holds a `Class<?>` from R1, garbage collection of R1 may be delayed.

## 5. Comparing Base and Restart Classloaders

| Criterion | Base classloader | Restart classloader |
| --- | --- | --- |
| Purpose | Reuse rarely changing classes | Reload application classes under development |
| Default examples | Spring/Jackson/third-party JARs | Classes from IDE project output directories |
| Replaced on every DevTools restart? | Usually **no** | **Yes**, creates a new loader |
| Static state of classes in the same loader | Can remain in the JVM | Static state of classes loaded by the new loader is re-initialized |
| Class identity across restarts | Stable for classes kept in base | Differs between R1 and R2 |
| Contains Spring application beans? | May hold library **types** or caches; does not mean it owns all beans | May hold application bean implementation classes |
| Memory impact | Keeps classes stable, though caches may retain old references | Can be GC'd once no references remain |
| Adjusting the partition | `restart.include` can pull entries up to restart | `restart.exclude` can push entries down to base |
| Replaces full JVM restart? | No | No; still inside the same JVM |

**Bean state and classloaders are not the same thing.** Spring `ApplicationContext` creates and closes beans, whereas classloaders determine a class's runtime type. A bean whose framework type resides in base can still be recreated in the context after a restart; meanwhile, classes in base can still retain old static state.

## 6. When Is a DevTools Restart Triggered?

DevTools **watches for changes on the classpath**, especially entries pointing to directories. Editing a `.java` file in the IDE **is not enough** if the IDE does not recompile the class output.

In Spring Boot 3.3:

- **Eclipse**: saving source usually updates the classpath via auto-build, which can trigger a restart.
- **IntelliJ IDEA**: use `Build -> Build Project` to update class output according to IDE settings.
- **Maven/Gradle**: run appropriate compile/build tasks to update class output files.
- **Other IDEs**: check the compilation path and actual classpath directory.

```text
Edit *.java
    |
    v
IDE / build tool produces new *.class on classpath
    |
    v
DevTools FileSystemWatcher detects change
    |
    v
Restart context and restart classloader
```

**Not every file change forces a restart.** DevTools excludes groups of resources such as `static/**`, `public/**`, and `templates/**` from restart by default so resource reloading occurs instead of rebuilding the application context.

### 6.1. Restart vs. LiveReload

- **Restart:** swaps the restart classloader and re-initializes the Spring application context when a restart-worthy classpath change happens.
- **LiveReload:** helps the browser refresh when resources change; does not mean Java classes were reloaded.
- **Full JVM restart:** stops the Java process and starts a new one; both base/restart classloader state and JVM-level state start from scratch.

A CSS file change may need a browser reload without creating a new restart classloader. A Java method change typically requires recompiling class output and restarting.

Do not treat LiveReload as proof that Java class code has been refreshed.

### 6.2. Configuring a Trigger File

When continuous IDE compilation triggers restarts too frequently, you can use:

```properties
spring.devtools.restart.trigger-file=.reloadtrigger
```

Create the file:

```text
src/main/resources/.reloadtrigger
```

This file must appear on the runtime classpath. When the trigger file is updated, DevTools checks whether restart-worthy changes have accumulated. The trigger file only controls **when to check**; it **does not move classes between base and restart loaders**.

### 6.3. Poll Interval and Quiet Period

If DevTools restarts too early while the IDE is still copying class files:

```properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
```

The watcher polls periodically and waits for a quiet period to batch changes, reducing the chance of restarting mid-build. This is a **file-watching** setting, not a classloader partitioning or business thread pool setting.

## 7. Runnable Example (Spring Boot 3.3, Java 17+): Inspecting Actual Loaders

The following example does not assume any hardcoded classloader name across all machines. We print the **classloader name** and compare the application class's classloader with `SpringApplication`'s classloader.

### 7.1. Project Structure

```text
devtools-loaders-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          devtools/
            LoaderSplitApplication.java
      resources/
        application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'devtools-loaders-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
```

**Why use `developmentOnly`?** DevTools is for development and should not accidentally become a production runtime dependency. In Spring Boot 3.3, the Gradle plugin handles the devtools dependency during executable archive creation using default rules. With Maven, you can declare `spring-boot-devtools` with `optional=true`.

The project needs a compatible Gradle wrapper; the build file above does not generate `gradlew` automatically. Version 3.3.13 is used to demonstrate Spring Boot 3.3 branch behavior; new projects should consider currently supported versions.

`src/main/resources/application.properties`:

```properties
spring.application.name=devtools-loaders-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
```

### 7.2. Self-Contained Java Code in the Boot Project

`src/main/java/demo/devtools/LoaderSplitApplication.java`:

```java
package demo.devtools;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class LoaderSplitApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoaderSplitApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectLoaders(LocalGreeting greeting) {
        return args -> {
            ClassLoader appLoader =
                    LoaderSplitApplication.class.getClassLoader();
            ClassLoader serviceLoader =
                    LocalGreeting.class.getClassLoader();
            ClassLoader frameworkLoader =
                    SpringApplication.class.getClassLoader();

            System.out.println("app.loader=" + nameOf(appLoader));
            System.out.println("service.loader=" + nameOf(serviceLoader));
            System.out.println("app.sameAsFramework="
                    + (appLoader == frameworkLoader));
            System.out.println("app.sameAsService="
                    + (appLoader == serviceLoader));
            System.out.println("greeting=" + greeting.message());
        };
    }

    private static String nameOf(ClassLoader loader) {
        if (loader == null) {
            return "bootstrap";
        }
        return loader.getClass().getSimpleName();
    }
}

@Component
class LocalGreeting {

    String message() {
        return "hello";
    }
}
```

`LocalGreeting` is a package-private top-level class in the same file; Java allows one public top-level class alongside non-public classes. `@SpringBootApplication` on `LoaderSplitApplication` sits in the same package, so `LocalGreeting` is picked up by component scanning.

### 7.3. Running with bootRun and Triggering Restart

Using the Gradle wrapper:

```bash
./gradlew bootRun
```

When DevTools restart is active with the typical classpath created by `bootRun`, the lines **printed by the example code** look like:

```text
app.loader=RestartClassLoader
service.loader=RestartClassLoader
app.sameAsFramework=false
app.sameAsService=true
greeting=hello
```

This is a **conditional expected output** when application classes belong to the restart loader and `SpringApplication` belongs to the base loader. In different IDEs or custom classloaders, the exact loader name may vary. Boot/Gradle also print extra logs outside the block above.

Reason:

1. `LoaderSplitApplication` and `LocalGreeting` belong to the project class output -> restart loader.
2. `SpringApplication` lives in a Spring Boot library JAR -> base loader.
3. The application and service classloaders match under this configuration.
4. The application classloader differs from the framework class's classloader.

### 7.4. Trying a Source Edit

Change:

```java
String message() {
    return "hello again";
}
```

This is a **replacement variant** for `LocalGreeting`'s method; do not add a duplicate method with the same signature. Recompile via your IDE/build tool while the devtools process is running. Once DevTools detects the classpath change, the app restarts and can print:

```text
app.loader=RestartClassLoader
service.loader=RestartClassLoader
app.sameAsFramework=false
app.sameAsService=true
greeting=hello again
```

Even though the simple classloader name is still `RestartClassLoader`, **the restart classloader instance has changed**. Two calls to `nameOf(...)` returning the same string do not mean they are the same loader object.

### 7.5. Checking Loader Identity Instead of Just Name

You can add to the runner:

```java
System.out.println(
        "app.loaderIdentity="
        + System.identityHashCode(
                LoaderSplitApplication.class.getClassLoader()));
```

This is an additional snippet inside `inspectLoaders`. `identityHashCode` is only a number for local process observation, **not a globally unique ID**—do not store it as a business key. Across restarts, the value usually differs, though accidental numeric collisions are possible. To compare definitively within the same JVM, hold references to two loader objects and compare with `==` in appropriate test code.

### 7.6. Why Does java -jar Produce Different Output?

Try:

```bash
./gradlew bootJar
java -jar build/libs/devtools-loaders-demo-1.0.0.jar
```

In Boot 3.3, DevTools is typically **excluded from executable archives**, and restart functionality **automatically disables itself in fully packaged applications**. Therefore, do not expect `RestartClassLoader` in normal `java -jar` runs. The output may look like:

```text
app.sameAsFramework=true
app.sameAsService=true
greeting=hello
```

The actual classloader name may be the executable JAR launcher classloader rather than `AppClassLoader`. This output block shows loader relationships in a typical packaged setup and **does not** prove every custom launcher uses the exact same loader.

**Do not use `java -jar` to test default DevTools restart**. Use an IDE or `bootRun`/`spring-boot:run` with the devtools dependency actually on the runtime classpath.

## 8. Plain Java 17: Same Class Name, Different Classloaders Mean Different Types

This experiment does not depend on Spring Boot and illustrates the fundamental principle of class identity.

### 8.1. Create Widget.java

```java
public class Widget {

    public Widget() {
    }
}
```

### 8.2. Create LoaderIdentityDemo.java

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class LoaderIdentityDemo {

    public static void main(String[] args) throws Exception {
        Path root = Path.of("out").toAbsolutePath();
        URL classpath = root.toUri().toURL();

        try (URLClassLoader first =
                    new URLClassLoader(new URL[] { classpath }, null);
             URLClassLoader second =
                    new URLClassLoader(new URL[] { classpath }, null)) {

            Class<?> left = Class.forName("Widget", true, first);
            Class<?> right = Class.forName("Widget", true, second);

            System.out.println("same.name="
                    + left.getName().equals(right.getName()));
            System.out.println("same.class=" + (left == right));
            System.out.println("assignable="
                    + left.isAssignableFrom(right));

            Object rightInstance =
                    right.getDeclaredConstructor().newInstance();

            try {
                left.cast(rightInstance);
                System.out.println("cast=success");
            } catch (ClassCastException exception) {
                System.out.println("cast=ClassCastException");
            }
        }
    }
}
```

### 8.3. Compile and Run

In the directory containing both files:

```bash
javac -d out Widget.java LoaderIdentityDemo.java
java -cp out LoaderIdentityDemo
```

Exact stdout:

```text
same.name=true
same.class=false
assignable=false
cast=ClassCastException
```

Explanation:

- Both loaders have the **same URL** pointing to the directory containing `Widget.class`.
- Passing `null` as parent in `URLClassLoader` prevents both loaders from delegating `Widget` to the application loader (they still retain access to core JVM platform classes).
- Two `Class.forName` calls define `Widget` via **two separate loaders**.
- Both names are `"Widget"`, yet `left != right`.
- An instance created from `right` cannot be `cast` to `left`.

This is why you can encounter a message like:

```text
com.acme.Model cannot be cast to com.acme.Model
```

in multi-classloader environments. The message is not contradictory: **two `com.acme.Model` classes can be two distinct runtime types** because their defining classloaders differ.

**Important:** this demo uses two independent `URLClassLoader` instances to clarify JVM semantics. DevTools has its own partitioning and delegation rules between base and restart loaders; it is not 100% identical to two loaders with `null` parent in this experiment.

## 9. What Kinds of Errors Does Class Identity Cause?

### 9.1. ClassCastException

A library in base retains an object created by an old restart classloader. After a restart, application code in R2 tries to cast that object to the identically named type loaded by R2:

```text
instance = CustomerModel (loader R1)
expected = CustomerModel (loader R2)

Cast -> ClassCastException
```

Whether an error occurs depends on how objects cross the boundary. Not every object crossing base/restart breaks: shared interfaces/classes defined in base can serve as valid contracts if code keeps types stable.

### 9.2. LinkageError and Type Resolution Errors

A library using reflection, proxies, or class metadata caches may load incompatible classes across different loaders, leading to:

- `ClassCastException`.
- `ClassNotFoundException`.
- `NoClassDefFoundError`.
- `LinkageError` in inconsistent linkage scenarios.
- Methods/annotations not detected by the framework as expected.

**Do not conclude every error of this kind is caused by DevTools.** They can also stem from dependency conflicts, version mismatches, invalid bytecode, or a broken classpath. A key diagnostic step is **disabling restart completely** and comparing.

### 9.3. Annotations and Reflection

Spring Boot 3.3 notes that classes loaded via reflection, especially annotations, may be loaded from a parent/base classloader before the application classes that need them are created. That can occasionally prevent annotations from being detected as expected.

Example scenario:

```text
shared-annotations.jar -> base
order-service classes -> restart

Reflective library creates/caches Class<?> or Annotation type too early
     |
     +-- After restart, application classes are defined by another loader
     +-- Must inspect type resolution across the loader boundary
```

**Do not solve this by blindly moving all JARs into restart.** Identify the relevant classpath entry, inspect which library caches/loads classes first, and adjust only the necessary scope.

## 10. Multi-Module Projects Are Where Classloader Errors Frequently Appear

Suppose a repository has:

```text
workspace/
  api-service/           -> module containing @SpringBootApplication
  shared-domain/         -> models + interfaces
  shared-annotations/    -> custom annotations
  legacy-adapter/        -> library adapter
```

There are at least two ways `shared-domain` enters the runtime classpath:

1. **Open project/module using a class directory**: DevTools can place it into the restart classloader.
2. **Pre-built JAR**: usually placed into the base classloader.

When an IDE imports all modules as active projects under development, they may be placed in the restart loader. When CI/build tools use a module's binary JAR, it may go into the base loader. Thus **the same repo can have different classloader splits across two launch methods**.

### 10.1. Why Does It Run in the IDE Yet Fail in bootRun?

Variables that can differ:

- The IDE determines "open projects" differently from Gradle's runtime classpath.
- A module uses an output directory in the IDE, whereas Gradle uses a JAR artifact.
- Whether a dependency is `project(":shared-domain")` or a repository artifact.
- A runtime library loads annotations/models reflectively before application classes.
- A classpath entry is mapped by a library's own `META-INF/spring-devtools.properties`.
- A custom classloader or Java agent alters class loading order.

Before changing code, **print the classloader and `CodeSource` of types on both sides** to see where they are loaded from.

### 10.2. A Partition Example to Watch Out For

```text
base:
    shared-domain-1.0.jar
    jackson-databind.jar

restart R1:
    api-service/build/classes/java/main

restart R2:
    api-service/build/classes/java/main (new version)
```

If a class inside `shared-domain.jar` holds a static cache containing a `Class<?>` from R1, that cache can survive across restarts while the new application uses R2.

Inspect the cache and cleanup logic. Sometimes moving `shared-domain.jar` into the restart loader aligns type identity across restarts; other times, the better fix is modifying the library so it does not hold long-lived class objects.

## 11. Customizing the Split via META-INF/spring-devtools.properties

Spring Boot DevTools provides dedicated configuration for **classloader partitioning**, separate from normal application properties:

```text
src/main/resources/META-INF/spring-devtools.properties
```

This file supports keys:

- `restart.include.<unique-name>`: pulls matching classpath entries **up into the restart classloader**.
- `restart.exclude.<unique-name>`: pushes matching classpath entries **down into the base classloader**.

Each key's value is a **regular expression applied to classpath entries when the JVM starts**. Key names must be unique; Spring Boot reads all `META-INF/spring-devtools.properties` files on the classpath, including those inside dependency JARs.

### 11.1. Sample Example

```properties
# Example regexes for Unix-style classpaths only.
# Pull shared-model JAR into the restart classloader:
restart.include.shared-model=.*/shared-model-[^/]+\\.jar

# Push compiled directory of generated-api module down to base:
restart.exclude.generated-api=.*/generated-api/build/classes/.*
```

These patterns **must be adapted to your real classpath** and operating system. In Java `.properties` files, for a regex to match a literal `\.`, you may need to double the backslash as in `\\.jar`. Overly broad patterns can drag large libraries into the restart loader, slowing restarts or introducing new type identity bugs.

On Windows, classpath URLs/paths may format separators differently. Avoid copying Unix regex examples and concluding DevTools ignored your config when the pattern simply matched nothing.

### 11.2. What Do Include/Exclude Actually Apply To?

These values are **not package names** and are not regexes matched against fully qualified class names like `com.acme.Foo`. They decide which **classpath entry** belongs to which loader.

Example:

```text
Classpath entry: /home/me/.m2/repository/acme/shared-model-1.2.jar
Pattern:         .*/shared-model-[^/]+\\.jar
Decision:        Move the entire shared-model-1.2.jar entry to restart
```

So if you want to "move just one class" inside a large JAR without changing artifact/module boundaries, these regex settings **are not a per-class selector**. Change packaging or classpath organization if finer granularity is needed.

### 11.3. Choosing Include or Exclude?

| Need | Action |
| --- | --- |
| An internal module JAR with frequently changing models/annotations | Consider `restart.include.*` so it restarts alongside the app |
| A rarely changing module directory currently treated as an open project | Consider `restart.exclude.*` to reduce restart overhead |
| A base library holds objects/classes from an old restart loader | Fix ownership/cache first; if appropriate, consider including the library |
| A class needs cross-module reflection/annotations | Inspect defining loader and load timing; adjust the relevant entry |
| Unsure which entry is misclassified | Print classpath/classloaders, check logs, then narrow the regex |
| A JAR change is not detected by the watcher | Check directory watching and build/restart mechanics; include does not guarantee watching every JAR |

**Do not confuse `restart.include` with a "watch file" command**. By default DevTools watches directory classpath entries; moving a JAR into the restart loader does not mean all changes to that JAR will be watched/restarted the same way.

### 11.4. Why Not Put Include/Exclude in application.properties?

`restart.include.*` and `restart.exclude.*` for **classloader partitioning** are a separate mechanism read from `META-INF/spring-devtools.properties`. Per Spring Boot 3.3 docs, system properties cannot replace this partition file.

In contrast:

```properties
spring.devtools.restart.enabled=false
spring.devtools.restart.additional-exclude=docs/**
```

are **Spring Boot DevTools application properties** for enabling/disabling restart and watching resource changes. Both contain the word "restart", yet they live in different namespaces with different responsibilities.

## 12. Four Easily Confused Mechanisms

| Mechanism | Configuration / Behavior | Effect |
| --- | --- | --- |
| Classloader partitioning | `META-INF/spring-devtools.properties` with `restart.include.*` / `restart.exclude.*` | Which **classpath entries** go to base vs. restart |
| Exclude resources from trigger | `spring.devtools.restart.exclude` | Which resource changes **do not trigger a restart** |
| Append exclusions while keeping defaults | `spring.devtools.restart.additional-exclude` | Appends to the non-triggering resource list |
| Watch additional paths | `spring.devtools.restart.additional-paths` | Watches extra paths; **does not move classpath entries to the restart loader** |
| Restart only when trigger file touched | `spring.devtools.restart.trigger-file` | Controls when restarts are checked |
| Disable restart | `spring.devtools.restart.enabled` | Stops or disables restart depending on how it is set |

Example to exclude generated docs while keeping defaults:

```properties
spring.devtools.restart.additional-exclude=docs/**,generated-notes/**
```

Example to **replace** the default exclusion list:

```properties
spring.devtools.restart.exclude=static/**,public/**
```

Note that `exclude` directly **replaces** the default group; if you want to **keep defaults and add more**, use `additional-exclude`. Whether a resource change triggers a restart says nothing about whether classes alongside it belong to the base or restart loader.

## 13. Checking CodeSource: Where Was a Class Loaded From?

When debugging multi-classloader errors, a helpful diagnostic is:

```java
import java.net.URL;
import java.security.CodeSource;

public final class LoaderDiagnostics {

    private LoaderDiagnostics() {
    }

    public static void print(String label, Class<?> type) {
        ClassLoader loader = type.getClassLoader();
        CodeSource codeSource =
                type.getProtectionDomain() == null
                ? null
                : type.getProtectionDomain().getCodeSource();

        URL location = codeSource == null
                ? null : codeSource.getLocation();

        System.out.println(label + ".type=" + type.getName());
        System.out.println(label + ".loader="
                + (loader == null ? "bootstrap" : loader));
        System.out.println(label + ".location="
                + (location == null ? "<unavailable>" : location));
    }
}
```

This is a complete Java class placed in `LoaderDiagnostics.java`; it can be called from application code:

```java
LoaderDiagnostics.print("app", LoaderSplitApplication.class);
LoaderDiagnostics.print("spring", SpringApplication.class);
LoaderDiagnostics.print("model", SharedModel.class);
```

This call block is a **snippet**: it requires importing `SpringApplication` and having a `SharedModel` type from a real module/library. It will not compile standalone unless `SharedModel` is defined.

**Security note:** `location` can expose machine paths, usernames, or internal directories. Use this diagnostics helper only in controlled development environments; never unconditionally log full paths in production.

### 13.1. How to Read the Output?

Hypothetical output example:

```text
app.loader=org.springframework.boot.devtools.restart.classloader.RestartClassLoader@...
app.location=file:/workspace/app/build/classes/java/main/
spring.loader=jdk.internal.loader.ClassLoaders$AppClassLoader@...
spring.location=file:/home/user/.gradle/caches/.../spring-boot-3.3.x.jar
model.loader=org.springframework.boot.devtools.restart.classloader.RestartClassLoader@...
model.location=file:/workspace/shared/build/classes/java/main/
```

This is an **illustrative example**, not exact stdout: paths, hashes, and JDK loader names vary by environment.

If `model` should be in the restart loader yet appears as a JAR in base, inspect module imports/build artifacts and consider `restart.include.*`.

## 14. What Role Does Thread Context ClassLoader (TCCL) Play?

Besides `SomeType.class.getClassLoader()`, Java provides:

```java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();
```

Many libraries use TCCL to **look up classes in the current thread's context**, especially when code in a base library needs to load an application type residing in the restart classloader.

Example:

```java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();

Class<?> type = Class.forName(
        "demo.devtools.LocalGreeting",
        true,
        tccl);
```

This is a **snippet** placed inside a method where `demo.devtools.LocalGreeting` is available. If TCCL points to the right loader, loading the application class succeeds. However, do not assume every thread's TCCL is always the restart loader.

### 14.1. Issues When Creating Threads Manually

A custom thread:

```java
Thread thread = new Thread(() -> {
    // A library might read TCCL here.
});
thread.start();
```

can inherit TCCL from its spawning thread or have it altered by an executor/framework. If the thread lives too long with TCCL pointing to R1, it can **retain a reference to the old restart classloader** after a DevTools restart.

Therefore:

- Prefer Spring-managed executors that shut down cleanly with the lifecycle.
- When creating threads manually, shut down or cancel them in `@PreDestroy` or `SmartLifecycle.stop(...)`.
- Never store threads or context classloaders in static caches without cleanup.
- Only change TCCL manually in tightly scoped blocks and restore it via `finally` when necessary.

### 14.2. Example of Changing and Restoring TCCL

```java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();

try {
    current.setContextClassLoader(targetLoader);
    // Call the library that needs targetLoader here.
} finally {
    current.setContextClassLoader(previous);
}
```

This is a snippet requiring a defined `targetLoader` of type `ClassLoader`. Always have a clear reason before altering TCCL; it is not a universal trick for every `ClassCastException`.

## 15. Serialization and ObjectInputStream Errors

Spring Boot 3.3 documentation notes a specific limitation: restarts can encounter issues when objects are deserialized using standard `java.io.ObjectInputStream`. The reason is that its class resolution does not always align with application classes residing in the restart classloader.

One option in **trusted, data-controlled** code is using Spring's `ConfigurableObjectInputStream`, passing the appropriate TCCL:

```java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.ConfigurableObjectInputStream;

public final class ClassAwareDeserializer {

    private ClassAwareDeserializer() {
    }

    public static Object read(InputStream source)
            throws IOException, ClassNotFoundException {

        ClassLoader loader =
                Thread.currentThread().getContextClassLoader();

        try (ConfigurableObjectInputStream in =
                new ConfigurableObjectInputStream(source, loader)) {
            return in.readObject();
        }
    }
}
```

This is a complete Java class **requiring Spring Core on the classpath**, not a plain `javac` program. It picks a loader to resolve class identity properly in certain DevTools scenarios. However, **never use Java deserialization on untrusted data**: `ObjectInputStream` generally carries severe security risks with malicious payloads. In production systems, prefer safe formats/serializers with explicit schemas or allowlists.

If a third-party library uses `ObjectInputStream` internally without exposing a classloader hook, changing application code may not suffice. You may need to upgrade the library, file an issue, switch serializers, or temporarily disable DevTools restart during development.

### 15.1. Do Not Equate JSON and Java Object Serialization

Jackson JSON typically relies on framework-provided type metadata and may have its own class loading hooks. Direct Java serialization via `ObjectInputStream` has different constraints. Both can hit classloader errors if a library caches wrong metadata/types, yet you should not arbitrarily swap serializers without understanding the data format.

## 16. Static Caches, Thread Leaks, and GC of Old Restart Loaders

A major issue across multiple DevTools restarts is **keeping old classloaders alive**.

A restart loader R1 can only be garbage-collected when no strong references remain to:

- Instances of classes defined by R1.
- `Class<?>` or `Method`/`Field` objects from R1.
- Threads whose TCCL points to R1.
- Listeners registered in a registry living in the base loader.
- Base library static caches holding proxies/metadata from R1.
- Resource callbacks attached to long-lived singletons outside the Spring context.
- Other classloaders holding handles or transformers from R1.

```text
Base library static CACHE
            |
            +--> Class<?> of OrderService (R1)
                         |
                         +--> RestartClassLoader R1

DevTools restart -> creates R2
R1 is still retained by base cache -> cannot be GC'd yet
```

After many restarts, retained old classloaders can accumulate, putting pressure on heap/metaspace. Not **every** restart leaks memory permanently: GC takes time and well-behaved caches release entries properly.

### 16.1. Designing Cleanup

A Spring-managed component can unregister subscriptions when the context closes:

```java
@Component
class RegistrationOwner {

    private final ExternalRegistry registry;
    private final Object listener = new Object();

    RegistrationOwner(ExternalRegistry registry) {
        this.registry = registry;
        this.registry.register(listener);
    }

    @PreDestroy
    void unregister() {
        registry.unregister(listener);
    }
}
```

This is a **snippet** requiring an `ExternalRegistry` interface with `register` / `unregister` methods and imports for `Component` and `jakarta.annotation.PreDestroy`. It illustrates the rule: objects registered with long-lived registries must be unregistered when the application context closes.

If the registry is base/static and the listener is an instance from the restart loader, unregistering is especially critical. Registering in the constructor may not be ideal if initialization can partially fail; in production, consider lifecycle hooks and partial-failure handling.

### 16.2. Testing for Leaks Properly

- Trigger multiple DevTools restarts with real classpath changes.
- Monitor heap/metaspace and retained `RestartClassLoader` counts after appropriate GC cycles.
- Use heap dumps or profilers in dev to trace retaining reference paths.
- Look for static caches and thread TCCLs pointing to old loaders.
- Verify `@PreDestroy`, executor shutdowns, and listener unregistrations.
- Do not attribute all memory growth to DevTools; JVM caching/JIT and other subsystems also allocate during warmup.

## 17. How Does DevTools Restart Close the Context?

DevTools restart relies on closing the current application context before creating a new one. Properly Spring-managed beans go through normal close/destroy lifecycle callbacks during shutdown.

However, distinguish between:

- **Spring bean lifecycle:** create, initialize, start, stop, destroy.
- **Java classloader lifecycle:** classes are loaded and become eligible for GC once unreferenced.
- **JVM process lifecycle:** the OS process stays alive during a DevTools restart.

A bean's `@PreDestroy` running does not by itself prove R1 has been GC'd; external caches or threads outside the context may still reference R1. Conversely, replacing the classloader does not mean tasks running outside Spring were cleanly stopped.

### 17.1. Do Not Arbitrarily Disable the Shutdown Hook

Spring Boot 3.3 docs note that DevTools requires the application context shutdown hook for restarts to work properly. If code calls:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setRegisterShutdownHook(false);
app.run(args);
```

this snippet requires `MyApplication` and importing `SpringApplication`; disabling the shutdown hook can break DevTools restarts. Do not use this setting as a workaround without understanding context lifecycle.

### 17.2. AspectJ Weaving

Spring Boot 3.3 states a limitation: DevTools automatic restart **is not supported when using AspectJ weaving**. Distinguish between:

- Standard Spring AOP proxies.
- AspectJ weaving (compile-time/load-time).

If you hit conflicts with AspectJ weaving, do not try forcing dozens of include/exclude regexes when automatic restart is unsupported in that setup.

## 18. Disabling Restart Properly for Diagnosis

There are **two levels** that are frequently conflated.

### 18.1. Disabling the Watcher in application.properties

```properties
spring.devtools.restart.enabled=false
```

According to Spring Boot 3.3, this **usually still initializes the restart classloader**, while disabling file watching for restarts. Therefore:

- No auto-restarts occur on code edits.
- The DevTools classloader split may still exist.
- It is **not yet** a test that completely removes the classloader boundary to diagnose `ClassCastException`.

### 18.2. Disabling Restart Completely Before SpringApplication.run

Set the **JVM system property** before DevTools activates:

```java
package demo.devtools;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DisableRestartApplication {

    public static void main(String[] args) {
        System.setProperty("spring.devtools.restart.enabled", "false");
        SpringApplication.run(DisableRestartApplication.class, args);
    }
}
```

This is a complete Spring Boot entry point (in `DisableRestartApplication.java`); use it **as a replacement variant** for another demo entry point, avoiding multiple `@SpringBootApplication` classes on the same component scan path so behavior stays clean.

Or via a JVM option at launch:

```bash
java -Dspring.devtools.restart.enabled=false ...
```

The `...` here is **illustrative syntax, not a complete runnable command**; replace it with the real classpath/main class or launcher. Inside the JVM, the property must be set early before `SpringApplication.run(...)`; do not change it after the context has already started.

### 18.3. Diagnostic A/B Procedure

1. Reproduce the error with DevTools restart active.
2. Capture classloaders, `CodeSource`, and redacted stack traces.
3. Disable restart completely via **system property before `run`** or by removing the DevTools dependency.
4. Start a fresh process and re-test.
5. If the error disappears, this **suggests** the classloader boundary is involved; it does not yet prove which pattern needs changing.
6. Use diagnostics to pinpoint the relevant classpath entry.
7. Adjust `META-INF/spring-devtools.properties` narrowly.
8. Re-enable restart and test multiple restart cycles covering both success and failure cases.
9. Check restart speed and memory to confirm no new regressions were introduced.

If the error persists with restart completely disabled, focus on dependency versions, shading, classpath conflicts, class initialization, and other reflection/serialization usage.

## 19. Why Is Disabling DevTools in Packaged JARs Different from Forcing Restart?

DevTools is a development tool. Spring Boot 3.3 **automatically disables** DevTools features in standard fully packaged applications, such as those started with `java -jar` or special launchers.

In Gradle, configuring:

```groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
```

keeps the dependency strictly for development/`bootRun` and out of production packages by default.

In Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
```

`optional` prevents devtools from propagating transitively to other modules. For packaged apps, respect Spring Boot plugin exclusions and production runtime rules.

**Never force DevTools on in production** via `-Dspring.devtools.restart.enabled=true`. Boot 3.3 docs warn this is a security risk. In production, build and deploy new versions through standard pipelines rather than relying on devtools classloader restart as hot deployment.

## 20. Multi-Module Debugging Case Studies

### 20.1. Model in a Shared Module Throws ClassCastException

**Symptom:**

```text
ClassCastException: com.acme.shared.OrderDto
cannot be cast to com.acme.shared.OrderDto
```

**How to handle:**

1. Print `getClassLoader()` of the actual object instance.
2. Print `OrderDto.class.getClassLoader()` at the cast site.
3. Identify which type was defined in R1, R2, or base.
4. Check whether a base static cache or serialization retained an old object.
5. Disable restart completely to test the hypothesis.
6. Only then consider pulling the shared JAR into the restart loader or fixing the cache/serializer.
7. Do not merely add `(OrderDto) object` or reflective casts, as class identity remains incompatible.

### 20.2. Custom Annotation Is Not Scanned

**Symptom:** an annotation exists in bytecode yet component scanning/reflection misses it, or a framework library sees a different type than Spring observes.

**How to handle:**

- Check whether the module containing the annotation is a directory or a JAR.
- Inspect the classloaders of the annotation type, annotated class, and scanner.
- Check whether the library caches metadata in base across restarts.
- Use include/exclude config to align the necessary loading scope, or adjust how the library uses TCCL.
- Do not assume widening `@ComponentScan` will fix it if the root cause is loader identity.

### 20.3. Third-Party Serializer Throws ClassNotFoundException

**Symptom:** a deserializer library in the base loader looks up a class that exists only in the restart loader.

**How to handle:**

- Check whether the deserializer accepts a custom classloader.
- For trusted Java object serialization, consider `ConfigurableObjectInputStream` with TCCL.
- If the third-party library does not support it, check library updates/issues.
- Disable restart if it cannot be safely resolved during development.
- Never broaden deserialization to untrusted objects merely to work around a classloader error.

### 20.4. Newly Built Shared JAR Is Not Picked Up

**Symptom:** you edit a module's source and rebuild its JAR dependency, yet the running app still uses the old version.

**Possibilities:**

- The JAR sits in the base loader and is not reloaded by a restart classloader swap.
- The file watcher does not watch JARs the same way it watches classpath directories.
- The build tool did not place the new JAR onto the running process's classpath.
- The IDE uses a cached or different project dependency than the newly built JAR.

**How to handle:** check `CodeSource` and runtime classpath, rebuild, and restart the process if needed. `restart.include.*` can change the JAR's mapping at an **appropriate startup**, though it does not guarantee the watcher monitors live JAR replacements while the process is running.

### 20.5. Memory Grows After 30 Restarts

**Symptom:** metaspace/class count rises steadily and does not drop after reasonable GC cycles/steady state.

**Possibilities:** a base-loader static cache holds `Class<?>`/proxies from R1, unstopped threads, or TCCLs still pointing to old loaders.

**How to handle:** inspect a heap dump for the **retaining path**, clean up listener registrations, thread pools, and object references, then test across multiple restarts. Do not merely raise `-XX:MaxMetaspaceSize` to hide a leak.

## 21. Designing DevTools-Friendly Internal Libraries

If you author a library consumed by multiple Spring Boot applications, follow these guidelines:

1. **Never keep unbounded static caches of `Class`/objects** originating from application contexts that are no longer alive.
2. If caching metadata keyed by `Class<?>`, provide cleanup/invalidation when the context closes or the classloader changes.
3. Expose explicit `close()`/`unregister()` APIs for listeners, subscriptions, and custom threads.
4. Avoid blindly calling `Class.forName(name)` when types live outside the library's defining loader; accept a `ClassLoader` parameter or use TCCL safely.
5. Support proper classloader selection in serialization, reflection, and annotation processing.
6. Use stable interfaces/models to pass data across boundaries; verify class identity when needed.
7. Test the library in both DevTools mode and fully packaged applications.
8. Never require enabling remote DevTools in production to paper over runtime classpath bugs.

**DevTools compatibility is a classloader and lifecycle management concern**, not a magic annotation you stick on every class.

## 22. Restart Speed: When Is It Fast, and When Is It Slow?

DevTools is fast when:

- Base holds most large, rarely changing libraries.
- Restarts only need to load application classes and rebuild the relevant context.
- The IDE compiles incrementally instead of rebuilding all modules every time.
- There are no heavy mandatory startup jobs or remote calls.
- Overly broad `include` rules are not pulling huge JARs into restart.

Restarts can still be slow if:

- `@PostConstruct` performs heavy I/O on every cycle.
- Application runners migrate/seed large datasets or wait on remote services.
- Context creation involves many heavy integrations.
- `restart.include.*` pulls too many dependencies from base into restart.
- The classpath watcher triggers repeatedly because the IDE copies files in waves.
- Memory leaks retain old R1/R2 loaders, increasing GC and metaspace pressure.
- The app runs under a JDK/IDE/build mode that does not isolate classloaders as expected.

**Do not misunderstand:** "the base loader does not reload Spring JARs" **does not mean** all Spring beans, the application context, database connections, and the web server stay untouched. The Spring context still rebuilds; only part of class loading is optimized.

## 23. Matching the Configuration to the Problem

| Symptom or Goal | Tool | Do Not Confuse With |
| --- | --- | --- |
| Check whether an app class is in the restart loader | `Class#getClassLoader()`, `CodeSource` | `Class.getName()` is only a string |
| Edited Java yet no restart occurs | Verify `.class` updated, watcher, and build/IDE | `restart.include.*` does not compile Java |
| Move a shared JAR into the restart loader | `META-INF/spring-devtools.properties`, `restart.include.*` | `spring.devtools.restart.additional-paths` |
| Push a module directory down to base | `restart.exclude.*` | `spring.devtools.restart.exclude` |
| Skip restart for CSS/templates only | `spring.devtools.restart.additional-exclude` | Changing the application's classloader |
| Manually trigger restart checks | `spring.devtools.restart.trigger-file` | Browser-only LiveReload |
| Disable watcher while keeping part of DevTools | `spring.devtools.restart.enabled=false` in app properties | Disabling classloader support completely |
| Completely disable DevTools restart isolation | System property `false` **before `run`** or remove dependency | Setting app property `false` too late |
| Java deserialization cannot find a class | Check TCCL / serializer / type identity | Simply adding `@ComponentScan` |
| Process leaks memory after many restarts | Check base caches, threads, retained R1 references | Increasing heap does not fix leaks |
| Fully packaged JAR has no restart loader | Default production behavior | Not a Spring Boot bug |
| Custom launcher / AspectJ weaving | Check support limitations | Do not force every devtools feature to work |

## 24. Practice Checklist

- [ ] Declared `spring-boot-devtools` as a development dependency.
- [ ] Running the app via IDE or `bootRun`/`spring-boot:run` properly to test restart.
- [ ] Know whether the IDE/build recompiles `.class` files in the classpath directory.
- [ ] Distinguished base classloader vs. restart classloader at runtime.
- [ ] Do not treat identical class names as identical runtime types when defining loaders differ.
- [ ] Inspected classloaders and `CodeSource` before editing multi-module configs.
- [ ] Know that `restart.include.*` / `restart.exclude.*` belong in `META-INF/spring-devtools.properties`.
- [ ] Do not confuse them with `spring.devtools.restart.exclude` for file watching.
- [ ] Every `restart.include.<name>`/`restart.exclude.<name>` key is unique.
- [ ] Classpath entry regexes are narrow and tested against real paths.
- [ ] Do not assume including a JAR automatically makes the watcher monitor every JAR change.
- [ ] Eliminated or cleaned up static caches holding classes/objects from old restart loaders.
- [ ] Custom threads/executors are shut down and do not retain R1's TCCL.
- [ ] Deserializers/reflection libraries can select the appropriate loader when needed.
- [ ] Never deserialize untrusted data with Java `ObjectInputStream`.
- [ ] Do not disable the `SpringApplication` shutdown hook while using DevTools restart.
- [ ] Tried **completely disabling restart** before claiming DevTools caused a bug.
- [ ] Tested both development restart and packaged `java -jar`.
- [ ] Never ship remote DevTools or force-enable restart in production.
- [ ] Never treat a single fast/slow restart run as sole proof of performance.

## 25. Reinforcement Questions and Exercises

### Exercise 1: Same Name, Different Loaders

There are two `Class<?>` objects both named `demo.Order`, one loaded by R1 and one by R2. Is `R1Class == R2Class` true or false? Why?

**Hint:** type identity consists of both binary name and defining classloader. Same name is not enough.

### Exercise 2: Identify Which Entry Lives in Base

A dependency `my-lib-1.0.jar` is added to the classpath with no special DevTools config. Where does it usually reside?

**Answer:** the base classloader, because it is a regular JAR.

### Exercise 3: Open Module

`shared-domain` is an open module in the IDE running as a class output directory. Which loader usually manages it?

**Answer:** the restart classloader under the default open-projects split.

### Exercise 4: Code Edited, No Restart

You save `OrderService.java`, yet `OrderService.class` on the classpath did not change. Does DevTools have enough signal to restart your class?

**Answer:** not necessarily; the classpath output must be updated via an appropriate compile/build step.

### Exercise 5: Distinguish Two Excludes

Explain the difference between:

```properties
spring.devtools.restart.additional-exclude=docs/**
```

and in `META-INF/spring-devtools.properties`:

```properties
restart.exclude.docs-module=.*/docs-module/build/classes/.*
```

**Hint:** one excludes resources from triggering a restart; the other assigns a classpath entry to the base classloader.

### Exercise 6: Serializer Uses Wrong Loader

A library in base deserializes a Java serialized object whose application type lives in restart. Why can `ClassNotFoundException` occur? Choose an appropriate check and fix.

**Hint:** try TCCL / `ConfigurableObjectInputStream` on trusted data, upgrade the library, or disable restart if unsupported.

### Exercise 7: Restart Leak

After 20 restarts, a heap dump shows `SharedRegistry.CACHE` in a base JAR still holding `Class<?>` from R1. Where should you fix it?

**Hint:** clean up the cache and registration lifecycle, rather than blindly setting `restart.include.*`.

### Exercise 8: Disabling Restart

Why is `spring.devtools.restart.enabled=false` in `application.properties` not the best test to rule out all two-classloader issues? What complete disable approach should you try?

**Hint:** set the **system property before `SpringApplication.run`**, or remove devtools.

### Exercise 9: Verify with Plain Java

Run `LoaderIdentityDemo` from Section 8. After obtaining two `Class<?>` objects with the same name, explain why `isAssignableFrom` returns false and `cast` throws an exception.

### Exercise 10: Choosing the Right Fix

A custom annotation lives in a module JAR cached by a reflection library in base. You should:

1. Print loader/`CodeSource`.
2. Check whether the cache clings to old types after restart.
3. Choose to include the module JAR if necessary.
4. Test multiple restarts and memory.

Why is merely adding `@ComponentScan` insufficient to solve every classloader mismatch?

## 26. Accurate Summary to Remember

1. **DevTools splits the classpath into two layers:** the base classloader holds rarely changing library classes; the restart classloader loads frequently changing application classes. This optimizes **class loading**, rather than "restarting the whole JVM".
2. On restart, **the old restart classloader is replaced by a new loader**, while base is reused. Classes with the same name across R1/R2 can be **two distinct runtime types**.
3. **By default:** open IDE projects/modules and app class directories usually go to restart; dependency JARs usually go to base. Multi-module builds as directories vs. JARs can change the outcome.
4. **`META-INF/spring-devtools.properties`** with `restart.include.*`/`restart.exclude.*` uses regexes **on classpath entries** to select loaders; completely different from `spring.devtools.restart.exclude`/`additional-paths`, which control **file watching**.
5. **Restarts require classpath changes:** editing `.java` must be compiled/copied to `.class`. Browser LiveReload does not replace a Java classloader restart.
6. **`ClassCastException`, reflection, annotation detection, serializers, and static caches** are the areas to inspect when two classloaders exist. Never blame DevTools before measuring.
7. **TCCL** helps libraries find application classes in some scenarios, yet threads holding R1 in TCCL can prevent the old loader from being GC'd.
8. **Setting the app property to false** usually only stops the watcher; to completely eliminate the restart classloader for diagnostics, set the **system property to false before `run`** or remove the dependency.
9. **Production packaged JARs** do not normally run DevTools restart; never force-enable DevTools in production.
10. For reliable diagnostics, **print classloader + class origin**, run an A/B test without restart, narrow classpath partition regexes, and re-test across multiple restarts.

### Official Documentation

- [Spring Boot 3.3 — Developer Tools](https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html): Restart vs. Reload, base/restart classloader, classpath watching, multi-module, `spring-devtools.properties` config, and known limitations.
- [Spring Boot 3.3 — Running Your Application](https://docs.spring.io/spring-boot/3.3/reference/using/running-your-application.html): ways to start in development environments.
- [Java 17 — ClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): class loading/delegation and the role of the defining loader.
- [Java 17 — URLClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): example of two independent classloaders.
- [Spring Framework — ConfigurableObjectInputStream](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/ConfigurableObjectInputStream.html): passing a classloader when reading Java serialization where needed.
