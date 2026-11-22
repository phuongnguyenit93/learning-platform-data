# Placing ResourceBundle at the Correct Path When Packaging a JAR in Java

## 1. Why Does ResourceBundle Work in the IDE but Fail When Running the JAR?

A common error in multilingual Java applications:

- When running `Main` in the IDE, Vietnamese messages load normally.
- After running `mvn package` or `gradle jar`, the program throws `MissingResourceException`.
- Inspecting the JAR reveals that the `Messages_vi_VN.properties` file was not included, or it resides under a directory that is not part of the classpath root.

For example, the program calls:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "com.example.i18n.Messages",
        Locale.forLanguageTag("vi-VN"));
```

This is a **snippet** requiring imports of `java.util.ResourceBundle` and `java.util.Locale`. Java looks up the bundle by **base name**, **locale**, and **classpath/module resources**. For `.properties` bundles on the traditional classpath, a resource can be found at the path:

```text
com/example/i18n/Messages_vi_VN.properties
```

**It must be understood that this is a relative path from the classpath root or from the root of the JAR contents**, not the path to the source file in the project. When packaging, even a single extra directory level such as `src/main/resources/` inside the JAR can prevent Java from finding the resource.

This article explains how to lay out a resource bundle, organize Maven/Gradle and manual JAR builds, how Java selects files by locale and the fallback mechanism, how to inspect the actual JAR, distinguish classpath from filesystem, and special considerations in Java 9+/Java 17+, named modules, and Spring Boot.

## 2. Three Concepts: Base Name, Resource Path, and Classpath Root

| Concept | Example | Role |
| --- | --- | --- |
| **Base name** | `com.example.i18n.Messages` | Logical name passed to `ResourceBundle.getBundle`, using dots, **without** the `.properties` extension |
| **Locale-specific bundle name** | `Messages_vi_VN.properties` | File name using the `_<language>_<country>` convention when matching a locale |
| **Resource path** | `com/example/i18n/Messages_vi_VN.properties` | Relative path from the classpath/JAR root |
| **Classpath root** | `target/classes`, `build/resources/main`, or the **content root** of a JAR | Location Java uses as the starting point to search for resources |
| **JAR entry** | `com/example/i18n/Messages_vi_VN.properties` | Entry name that needs to appear inside the `.jar` file, using `/` |
| **Filesystem path in repo** | `src/main/resources/com/example/i18n/Messages_vi_VN.properties` | Source file location; the build step must copy it to the classpath output |

With the base name `com.example.i18n.Messages`, Java considers bundle names such as:

```text
com.example.i18n.Messages_vi_VN
com.example.i18n.Messages_vi
com.example.i18n.Messages
```

When looking up property-based bundles on the classpath, dots in the package part are converted to `/` and `.properties` is appended:

```text
com/example/i18n/Messages_vi_VN.properties
com/example/i18n/Messages_vi.properties
com/example/i18n/Messages.properties
```

That is why the **directory structure** and **file names** must match the base name. If you pass `"Messages"` instead of `"com.example.i18n.Messages"`, Java will search at the **root** of the classpath and will not automatically look inside the `com/example/i18n` directory.

### Testing Path Names Using the Java API

In a classpath/unnamed module application, `ResourceBundle.Control` has methods to observe the name transformation:

```java
import java.util.Locale;
import java.util.ResourceBundle;

ResourceBundle.Control control = ResourceBundle.Control.getControl(
        ResourceBundle.Control.FORMAT_DEFAULT);

Locale locale = Locale.forLanguageTag("vi-VN");
String bundleName = control.toBundleName(
        "com.example.i18n.Messages", locale);

String path = control.toResourceName(bundleName, "properties");
System.out.println(bundleName);
System.out.println(path);
```

This is a **snippet placed inside a method**, not a standalone class. Verified output:

```text
com.example.i18n.Messages_vi_VN
com/example/i18n/Messages_vi_VN.properties
```

**Note:** `ResourceBundle.Control` describes details specific to the classpath strategy; some `getBundle(..., Control)` overloads are **not supported when called inside a named module**. For JPMS applications, follow the corresponding module API and packaging rules; do not copy classpath handling verbatim onto the module path.

## 3. Standard Maven/Gradle Project Structure

A typical Java project:

```text
bundle-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── app/
        │               └── Main.java
        └── resources/
            └── com/
                └── example/
                    └── i18n/
                        ├── Messages.properties
                        ├── Messages_vi.properties
                        └── Messages_vi_VN.properties
```

In Maven, `src/main/resources` is the default directory for runtime resources. With the Gradle Java plugin, `src/main/resources` is also the default resource source directory. The build step places the contents of that directory into the output resources or copies them into the JAR.

Do **not** place these files in `src/main/java/com/example/i18n` and assume every build tool by default will include `.properties` files from the source code tree in the JAR. Some IDEs may handle this differently, but CLI builds do not always copy non-`.java` resources from the source tree.

Do **not** treat `src/main/resources` as a package that needs to exist inside the JAR. It is an input directory for the build tool, not part of the base name.

### What Should the Inside of a Standard JAR Look Like?

After packaging a JAR to run on the traditional classpath, the key entries must have the structure:

```text
com/example/app/Main.class
com/example/i18n/Messages.properties
com/example/i18n/Messages_vi.properties
com/example/i18n/Messages_vi_VN.properties
```

They should not look like:

```text
src/main/resources/com/example/i18n/Messages_vi_VN.properties
resources/com/example/i18n/Messages_vi_VN.properties
target/classes/com/example/i18n/Messages_vi_VN.properties
```

unless the runtime is configured and the base name is specifically designed to handle those layouts. For the standard base name example in this article, entry names with extra prefixes like the above are **in the wrong location**.

## 4. Java 17+ Example: ResourceBundle Working Before and After Packaging

This example is a Maven project **with no external runtime libraries**, sufficient to build a simple JAR and run it with `java -cp`.

### 4.1. Creating the Message Files

**`src/main/resources/com/example/i18n/Messages.properties`**

```properties
greeting=Hello
app.title=Localization Demo
only.base=Base fallback
```

**`src/main/resources/com/example/i18n/Messages_vi.properties`**

```properties
greeting=Xin chào
app.title=Ứng dụng bản địa hóa
```

**`src/main/resources/com/example/i18n/Messages_vi_VN.properties`**

```properties
greeting=Xin chào từ Việt Nam
```

Create and save all three files in **UTF-8**. In Java 9 and later, property resource bundles use UTF-8 by default (with an ISO-8859-1 fallback mechanism for legacy data in case of invalid UTF-8 bytes). Java 17+ supports Vietnamese characters directly as shown in the example.

All three files share the **same base name `com.example.i18n.Messages`** but differ in their locale suffix. The root file `Messages.properties` serves as the fallback. The `Messages_vi.properties` file provides general Vietnamese translations; `Messages_vi_VN.properties` contains overrides specific to Vietnam.

The `Messages_vi_VN.properties` resource **does not need to repeat every key** from its parent; `ResourceBundle` allows looking up keys along the parent bundle chain when a key is absent from the child bundle.

### 4.2. Complete Main.java Program

Create **`src/main/java/com/example/app/Main.java`**:

```java
package com.example.app;

import java.net.URL;
import java.util.Locale;
import java.util.ResourceBundle;

public class Main {
    public static void main(String[] args) {
        String baseName = "com.example.i18n.Messages";
        Locale locale = Locale.forLanguageTag("vi-VN");

        ResourceBundle bundle =
                ResourceBundle.getBundle(baseName, locale);

        System.out.println("Bundle locale: "
                + bundle.getLocale().toLanguageTag());
        System.out.println("Greeting: "
                + bundle.getString("greeting"));
        System.out.println("Title: "
                + bundle.getString("app.title"));
        System.out.println("Base fallback: "
                + bundle.getString("only.base"));

        String resourcePath =
                "com/example/i18n/Messages_vi_VN.properties";
        ClassLoader loader = Main.class.getClassLoader();
        URL url = loader.getResource(resourcePath);

        System.out.println("Resource in classpath: "
                + (url != null));
    }
}
```

This is a Java 17+ class that is runtime-standalone (using Java SE), but **to run successfully, the `.properties` files must be packaged/placed on the classpath exactly as shown above**.

Explanation:

1. `getBundle(baseName, locale)` uses the dot-separated name, **without** needing the `_vi_VN` suffix because Java automatically selects candidate bundles.
2. `bundle.getLocale()` reports the locale of the loaded bundle — here `vi-VN`.
3. `getString("greeting")` retrieves the value from `Messages_vi_VN.properties`.
4. `getString("app.title")` resolves to the parent `Messages_vi.properties` because the key is not in `vi_VN`.
5. `getString("only.base")` resolves to the root `Messages.properties`.
6. `ClassLoader.getResource(path)` checks the resource via the **classpath**, not based on the current working directory.

With the files created properly and Java 17+ locale data, expected stdout:

```text
Bundle locale: vi-VN
Greeting: Xin chào từ Việt Nam
Title: Ứng dụng bản địa hóa
Base fallback: Base fallback
Resource in classpath: true
```

If the terminal does not support Unicode, characters on screen may display incorrectly even though `ResourceBundle` reads them properly. To diagnose, inspect the code points or write UTF-8 output to a file rather than relying solely on glyph rendering.

## 5. Packaging with Maven: Resources Must Be Copied to target/classes

### 5.1. Minimal pom.xml

Create **`pom.xml`** at the project root:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>bundle-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

This configuration allows Maven to compile source for Java 17. When the project does not define custom `resources`, Maven treats `src/main/resources` as the standard resource directory. The `process-resources` phase copies the files to `target/classes`, and the `package` goal bundles them together with compiled classes into the JAR.

### 5.2. Building and Inspecting

Run from the **project root**:

```bash
mvn -q clean package
jar tf target/bundle-demo-1.0.0.jar
```

`jar tf` lists all entries in the JAR. Look for the following entries (this is a **relevant excerpt**, not the full output of `jar tf`):

```text
com/example/app/Main.class
com/example/i18n/Messages.properties
com/example/i18n/Messages_vi.properties
com/example/i18n/Messages_vi_VN.properties
```

If the `.properties` files do not appear, **the issue lies in the build configuration, resource path, ignore/exclude/filter rules, or the artifact being inspected**. If the files appear under `src/main/resources/...`, the entry structure inside the JAR still does not match the base name.

Run via classpath (this approach **does not require Main-Class in the manifest**):

```bash
java -cp target/bundle-demo-1.0.0.jar com.example.app.Main
```

With this example, the command prints the five lines shown in section 4.2. Java uses the JAR as a **classpath entry**: the path `com/example/i18n/Messages_vi_VN.properties` is resolved from the root of the JAR.

Do **not** run `java -jar target/bundle-demo-1.0.0.jar` and expect it to succeed with the minimal `pom.xml` example: the default JAR may **lack a `Main-Class` in the manifest**. `java -cp <jar> <main-class>` is the right way to run without a manifest entry. If you want to use `java -jar`, configure a plugin to generate a manifest with `Main-Class`; this is separate from packaging `.properties` files.

### 5.3. Where Are Resources Located at Each Stage?

| Stage | Location | Why |
| --- | --- | --- |
| Before build | `src/main/resources/com/example/i18n/*.properties` | Resource source files |
| After process-resources | `target/classes/com/example/i18n/*.properties` | Maven classpath output |
| After compile | `target/classes/com/example/app/Main.class` | Java bytecode |
| After package | Entries `com/example/i18n/*.properties` in JAR | Loadable on runtime classpath |
| After `java -cp ...` | Java looks up in the JAR classpath | No separate physical files needed beside the JAR |

**Never** write code that reads `src/main/resources/...` using `new File(...)`: when the application is deployed, the source tree usually does not exist.

## 6. Packaging with the Gradle Java Plugin

The Gradle Java plugin also uses a standard layout:

```text
src/main/java/
src/main/resources/
src/test/java/
src/test/resources/
```

With the default configuration, files in `src/main/resources` are processed into runtime resources (typically at `build/resources/main`) and included in the JAR created by the `jar` task. Minimal Gradle Kotlin DSL example:

**`build.gradle.kts`**

```kotlin
plugins {
    java
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
```

This is a Gradle build file; the `src/main/java` and `src/main/resources` structure stays the same as in section 3. Build using the project's Gradle Wrapper if available:

```bash
./gradlew clean jar
```

On Windows, you can use `gradlew.bat clean jar`. The JAR is usually located under `build/libs/`, for example `bundle-demo-1.0.0.jar` if the project name is `bundle-demo`. Then inspect and run:

```bash
jar tf build/libs/bundle-demo-1.0.0.jar
java -cp build/libs/bundle-demo-1.0.0.jar com.example.app.Main
```

If the project name or version differs, **substitute the actual artifact file name**; do not assume every Gradle build produces this exact name.

### When Can Resources Disappear from a Gradle JAR?

- `sourceSets.main.resources.srcDirs` was changed to another directory.
- The `processResources` task has an `exclude` or an improper filter.
- The `jar` task customized `from` or `duplicatesStrategy`.
- The application is running a different artifact than the JAR just built.
- You ran `javac` directly outside Gradle and forgot to add `src/main/resources` to the classpath.

Compare the source resource files, the `build/resources/main` output, and the actual JAR entries to distinguish between a **missing copy**, a **wrong-path copy**, and a **runtime classpath** error.

## 7. Manual JAR Packaging with javac and jar

Even without Maven or Gradle, you can verify each layer explicitly:

```bash
javac -encoding UTF-8 -d out src/main/java/com/example/app/Main.java
jar --create --file bundle-demo.jar -C out . -C src/main/resources .
jar tf bundle-demo.jar
java -cp bundle-demo.jar com.example.app.Main
```

These are **JDK 17+** commands run from the project root. Their meaning:

1. `javac -d out` creates `out/com/example/app/Main.class`.
2. `-C out .` in `jar` puts the **contents inside** `out` into the JAR root.
3. `-C src/main/resources .` puts the **contents inside** the resources directory into the JAR root.
4. `jar tf` verifies the actual entry names.
5. `java -cp bundle-demo.jar com.example.app.Main` runs with the generated artifact.

Note: these shell commands are instructions, not Java code. On Windows, use the `javac` and `jar` tools in `PATH`; the `-C` option syntax of the `jar` tool is independent of the OS classpath separator.

If you want to run **without packaging a JAR** from two separate directories, you must put **both the class output and the resource root** on the runtime classpath:

Linux/macOS:

```bash
java -cp "out:src/main/resources" com.example.app.Main
```

Windows:

```powershell
java -cp "out;src/main/resources" com.example.app.Main
```

The classpath entry separator is `:` on Unix-like operating systems and `;` on Windows. Do not put only `out` on the classpath and expect `getBundle` to read resources located in `src/main/resources` without copying them or adding that root to the classpath.

## 8. Why Can't Resources Inside a JAR Be Read with new File?

Another common mistake:

```java
File file = new File("src/main/resources/com/example/i18n/Messages_vi_VN.properties");
```

In the IDE, the working directory may match the repo root and the file exists. But in a deployment, the runtime usually has only `bundle-demo.jar`, without the `src/main/resources` directory.

Even when you obtain the URL to an entry inside the JAR:

```text
jar:file:/.../bundle-demo.jar!/com/example/i18n/Messages_vi_VN.properties
```

it is **not** a regular filesystem `Path`. Do not take `getResource(...).getFile()` and blindly convert it to `new File(...)`; this approach can break with URLs containing spaces, `!` characters, escaped paths, or nested JARs.

### Reading Resources via ClassLoader

When you need to read a resource directly (without using `ResourceBundle`):

```java
import java.io.InputStream;

try (InputStream in = Main.class.getClassLoader()
        .getResourceAsStream(
                "com/example/i18n/Messages_vi_VN.properties")) {

    if (in == null) {
        throw new IllegalStateException("Resource not found");
    }
    // Read from InputStream with the appropriate charset.
}
```

This is a **snippet placed inside a method of class Main**. `getResourceAsStream` returns an `InputStream` that can access the entry's contents directly inside the JAR without extracting it. Always close the stream after use.

Distinguish between the two APIs:

- `Main.class.getClassLoader().getResourceAsStream("com/example/...")` takes a path **relative to the classpath root**, **with no leading `/`**.
- `Main.class.getResourceAsStream("/com/example/...")` takes an **absolute path from the classpath root** because of the leading `/`.
- `Main.class.getResourceAsStream("local.txt")` without a leading `/` searches **relative to the `com/example/app` package** of `Main`.

`ResourceBundle.getBundle` performs bundle/fallback lookup logic, not just reading a single file. Therefore, for multilingual messages, prefer `ResourceBundle` over manually probing `.properties` paths, unless the application uses a custom resource format.

## 9. Candidate Locales, Fallback, and Inherited Keys

When calling:

```java
ResourceBundle.getBundle(
        "com.example.i18n.Messages",
        Locale.forLanguageTag("vi-VN"));
```

with the files in the example, Java evaluates matching candidate bundles; in the simple `vi-VN` case:

```text
Messages_vi_VN.properties
Messages_vi.properties
Messages.properties
```

With the data prepared in section 4, the keys resolve as:

| Key | File containing the used value | Value |
| --- | --- | --- |
| `greeting` | `Messages_vi_VN.properties` | `Xin chào từ Việt Nam` |
| `app.title` | `Messages_vi.properties` | `Ứng dụng bản địa hóa` |
| `only.base` | `Messages.properties` | `Base fallback` |

A note on the default algorithm: `ResourceBundle` has a strategy for **candidate locales and fallback to the default locale** if no bundle for the requested locale is found, depending on the situation. You should not rigidly state that "every request tries locale -> root and stops" for all configurations. For instance, setting `Locale.getDefault()` to another region can change which bundle is chosen when candidates for the requested locale are missing.

If you need **no fallback via the JVM default locale** on the classpath, you can use `ResourceBundle.Control.getNoFallbackControl(...)` — but understand that this API cannot be used the same way in all named modules.

Explicitly controlling the locale is better than calling the overload without a locale:

```java
ResourceBundle selected = ResourceBundle.getBundle(
        "com.example.i18n.Messages", Locale.forLanguageTag("vi-VN"));
```

Do not call `ResourceBundle.getBundle(baseName)` in a multi-region server and expect every user to see their own language: that overload relies on the JVM's default locale, not the locale of each request.

### MissingResourceException Has Two Distinct Causes

- **Bundle not found:** `ResourceBundle.getBundle(...)` throws `MissingResourceException` because no suitable bundle could be loaded from the classpath/module.
- **Bundle found, but key missing:** `bundle.getString("some.key")` can also throw `MissingResourceException` because the key does not exist in the selected bundle or its parents.

Having the same exception name **does not mean having the same fix**. Check the **base name, classpath, and JAR entries** when the error occurs at `getBundle`; check **key names and parent hierarchy** when the error is at `getString`.

## 10. Encoding: ResourceBundle .properties and Java 9+

For Java 17+, `.properties` files of `PropertyResourceBundle` are read as **UTF-8** by default (changed since Java 9, JEP 226). If a file is not valid UTF-8, the default implementation falls back to **ISO-8859-1** for compatibility with legacy resources.

You can use the system property `java.util.PropertyResourceBundle.encoding` with the value `UTF-8` or `ISO-8859-1` to fix how it is read. This property is evaluated when `PropertyResourceBundle` initializes; do not change its value at runtime and expect already-cached bundles to be re-decoded.

Points to distinguish:

| API | Charset rule |
| --- | --- |
| `PropertyResourceBundle(InputStream)`, Java 9+ | UTF-8 first, fallback to ISO-8859-1 on invalid bytes, unless configured explicitly |
| `Properties.load(InputStream)` | By traditional specification, decodes ISO-8859-1 bytes; **not** UTF-8 by default |
| `Properties.load(Reader)` | Uses characters already decoded by the Reader according to its charset |
| `ResourceBundle.getBundle(...)` loading property bundles | Follows `PropertyResourceBundle`/provider mechanisms and the corresponding classpath/module environment |

**JDK 18 changing the default charset to UTF-8 (JEP 400) is not the cause of the JEP 226 change**: the UTF-8 property resource bundle rule has existed since Java 9.

### Build Tool Errors That Mutate Resources

Not only the Java runtime, but also the **build step** can alter bytes:

- Resource filtering plugins replace placeholder patterns inside `.properties`.
- The build tool reads the file with an inappropriate charset and writes it back, causing mojibake.
- The file is actually saved in a legacy encoding while code/docs claim UTF-8.
- `.properties` escaping mistakes: characters `=`, `:`, `#`, `!`, `\\`, and line continuations have syntactic meaning; do not assume a resource file is just a plain "key=value" text file needing no escaping.

With Java 17+, save source properties in UTF-8 and declare the appropriate build encoding. Only enable Maven/Gradle resource filtering when truly needed; do **not** use filtering to automatically transform translated content if there is a risk of corrupting diacritics, quotes, or placeholders.

## 11. Named Modules (JPMS) and Resource Bundles

The traditional classpath model places JARs on `-cp` and classes reside in the **unnamed module**. When an application uses `module-info.java` and runs with `--module-path`, resource lookup must also obey **module encapsulation**.

Key points:

1. A resource bundle in the **same named module** as the application can be loaded by code inside that module via `ResourceBundle.getBundle(baseName, locale)`.
2. A resource bundle in **another module** is not open by default for everyone to read; accessibility also depends on module exports/opens and the module lookup mechanism.
3. The Java 9+ API supports `ResourceBundle.getBundle(baseName, locale, module)` to look up on behalf of a specific module.
4. Resource bundles can be provided across modules via the **`ResourceBundleProvider` service**, with appropriate `uses`/`provides` declarations.
5. Some `getBundle` overloads accepting `ResourceBundle.Control` are **not supported in named modules**; follow proper JPMS rules and modern APIs.

An example statement in a meaningful module context:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "com.example.i18n.Messages",
        Locale.forLanguageTag("vi-VN"),
        Main.class.getModule());
```

This is a **snippet**, requiring the resource to reside in the specified module or be accessible to that module under encapsulation rules; it is not guaranteed to automatically find resources hidden in unrelated modules.

**Do not solve the error by arbitrarily opening entire modules externally.** Check whether the bundle is in the same module or another module, what access the module is granted, and which API is being called. See the *Resource Bundles and Named Modules* section of the official Javadoc.

## 12. Spring Boot Executable JARs Differ from Standard Classpath JARs

A Spring Boot executable JAR typically has the structure:

```text
BOOT-INF/classes/com/example/app/Main.class
BOOT-INF/classes/com/example/i18n/Messages_vi_VN.properties
BOOT-INF/lib/...
META-INF/MANIFEST.MF
```

This is the **layout of a Spring Boot executable JAR**, not the root entry names of a standard JAR run directly with `java -cp`. The Spring Boot loader constructs the runtime classpath from `BOOT-INF/classes` and the nested dependency JARs. Therefore:

- `jar tf app.jar` can show `BOOT-INF/classes/com/example/i18n/Messages_vi_VN.properties` and still be **correct** for Spring Boot.
- Use the standard Spring Boot run command, such as `java -jar app.jar` when the manifest/loader is properly configured.
- Do not mechanically apply the "entries must be at the JAR root" rule from section 3 to different executable archive formats.
- If using **Spring MessageSource** with `spring.messages.basename`, that parameter follows Spring's resource lookup rules and corresponding configuration, which may not behave identically to all uses of `java.util.ResourceBundle`. Consult Spring's specific documentation and configuration.

The source path is still typically `src/main/resources`. The difference lies in **how Boot packages and loads resources**. When debugging, determine the **type of JAR** first, then decide which entries are valid.

## 13. ClassLoader and Multi-JAR Packaging Traps

In real-world systems, bundles may reside in a dependency module or a separate JAR. In that case:

- The JAR containing the resources must be placed on the **runtime classpath** (or module path with appropriate rules).
- A resource can exist in multiple different JARs under the **exact same path**. Classloader lookup order/strategy may determine which file gets picked; do not rely on path collisions.
- In plugin systems and application servers, thread context classloaders may differ from the application class's classloader. `ResourceBundle.getBundle(baseName, locale, loader)` or the module overload can be useful when you need to specify the loading environment.
- On Java 9+, bundle caches may be tied to the classloader/module and locale. Modifying a JAR on disk does not necessarily force live bundles in the JVM to reload automatically.
- `ResourceBundle.clearCache()` exists for certain testing reload scenarios, but it does not replace designing resource updates with properly managed classloaders and lifetimes.

A simple program does not need a custom classloader. Only use advanced overloads when the system genuinely involves distinct loaders or modules. Do not write code to scan the entire filesystem for `Messages*.properties` files when the root cause is simply a misconfigured classpath.

## 14. Systematic Workflow for Diagnosing MissingResourceException

When the error occurs after packaging:

### Step 1. Identify Where the Exception Is Thrown

- `getBundle(base, locale)` fails -> check bundle/resource path and runtime loader.
- `getString(key)` fails -> check key name, parent files, and the selected bundle locale.

### Step 2. Log the Exact Base Name and Locale

```java
System.out.println("Bundle base: " + baseName);
System.out.println("Requested locale: " + locale.toLanguageTag());
```

This is a snippet, assuming `baseName` and `locale` have already been created.

Pay attention to letter casing in directory names, file names, and locale suffixes; for example, `Messages_vi_VN.properties` differs from `messages_vi_vn.properties` on many environments. Follow the naming convention generated by `ResourceBundle`; do not manually change `vi_VN` to `vi-VN` in the file name just because BCP 47 uses a hyphen.

### Step 3. Inspect Classpath Output and Artifact

With Maven:

```bash
mvn -q clean package
jar tf target/bundle-demo-1.0.0.jar
```

With Gradle: inspect `build/resources/main` and then `jar tf build/libs/<actual-name>.jar`. With Spring Boot: check `BOOT-INF/classes`, not just root entries.

### Step 4. Compare the Expected Path with the Actual Entry

```text
Expected: com/example/i18n/Messages_vi_VN.properties
Actual:   src/main/resources/com/example/i18n/Messages_vi_VN.properties
```

This case means **the file is inside the JAR but at the wrong path**. Fix the build packaging/copy root, not the locale or charset conversion.

### Step 5. Verify the Exact JAR Being Executed

Sometimes `jar tf` is run on the latest artifact while the deployment executes an older build or a differently named JAR. Confirm the actual launch script, container image, `-cp`, `-jar`, module path, and classloader.

### Step 6. Verify Runtime getResource

```java
String resourcePath =
        "com/example/i18n/Messages_vi_VN.properties";
boolean found = Main.class.getClassLoader()
        .getResource(resourcePath) != null;
System.out.println(found);
```

This is a snippet. If `false`, the active classloader **cannot find the exact path**. If `true` yet `getBundle` still fails, check the base name, candidate locales, format, module constraints, conflicting class/property bundles, or differing loaders.

### Step 7. Separate Encoding Errors from Resource Lookup Errors

If `getBundle` and `getString` **succeed** but Vietnamese diacritics turn into garbled characters, the resource was likely loaded from the right path, while the bytes were decoded wrongly or the console displays them improperly. Only then should you inspect UTF-8, resource filtering, and output encoding.

## 15. Common Error Reference Table

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Works in IDE, fails in JAR | Resource not included in JAR | Put file in `src/main/resources`; check `jar tf` |
| File is in JAR, still `MissingResourceException` | Entry prefixed with `src/main/resources/` or `resources/` | Package the **contents** of the resource root into the JAR root |
| `getBundle("Messages", locale)` not found | Base name missing package | Use `com.example.i18n.Messages` when file is in that package |
| Passing `Messages_vi_VN.properties` as base name | Base name is not a file name | Strip extension and locale suffix; pass the base name |
| `.properties` located in `src/main/java` | Build does not copy non-code files in source tree | Move to `src/main/resources` |
| Fails only on Linux | Case mismatch in file/package name | Verify exact casing of path and suffix |
| `getString` missing key even though bundle exists | Key absent from bundle and parents | Check parent chain and key name |
| Shows unexpected language | Locale/default locale and fallback | Pass locale explicitly; check `getLocale()` |
| Reads fine but Vietnamese text is corrupted | Resource or console encoding | Verify UTF-8, JEP 226, output pipeline |
| `getResourceAsStream` returns null | Wrong classpath root, leading `/` used with ClassLoader | Use correct path relative to classpath root |
| `new File("src/main/resources/...")` fails on deploy | Different working directory, source tree absent | Use `getResourceAsStream`/`getBundle` |
| `java -jar` reports no main manifest attribute | JAR lacks `Main-Class` | Configure manifest or run `java -cp jar Main` |
| `java -cp` on Boot fat JAR fails | Nested `BOOT-INF` layout | Run via Boot loader/`java -jar` properly |
| Named module cannot see bundle | Module encapsulation or wrong loader | Check JPMS ResourceBundle docs and valid package opening |
| Locale changes but old content still shows | Long-lived bundle cache/classloader | Check deployment and cache/reload strategy |
| Wrong bundle loaded from a dependency | Duplicate resource path across multiple JARs | Use a distinct namespace; check classloader |
| Build filtering breaks placeholders | Plugin unintentionally processes resource text | Configure excludes/encoding/filtering properly |
| File named `Messages_vi-VN.properties` | Wrong underscore convention for bundle locale files | Use `Messages_vi_VN.properties` |
| Missing root file | Fallback behaves unexpectedly or no matching bundle | Consider creating `Messages.properties` as root fallback |

## 16. Automated Testing After Packaging

Testing in the IDE is not enough, because the IDE may automatically add `src/main/resources` to the runtime classpath. You should run a **smoke test directly against the built JAR**.

With the minimal Maven project in this article:

```bash
mvn -q clean package
jar tf target/bundle-demo-1.0.0.jar
java -cp target/bundle-demo-1.0.0.jar com.example.app.Main
```

Expectations to verify:

1. The JAR contains the exact entry `com/example/i18n/Messages_vi_VN.properties`.
2. Output shows `Bundle locale: vi-VN`.
3. `Greeting: Xin chào từ Việt Nam`.
4. Key `app.title` inherits from `vi` and `only.base` inherits from root.
5. `Resource in classpath: true`.
6. Testing **after moving the JAR** to another directory still runs via `java -cp /path/to/jar com.example.app.Main`, without needing the source tree.
7. If running inside a container, resource paths are resolved from the **artifact/runtime classpath**, not from the current working directory.

### Useful Invariants for Pipelines

- **All required bundle variants are packaged** at the right paths.
- **Every base name has a root bundle** when the product requires predictable fallback.
- Mandatory keys are verified across all supported product locales.
- No unintended duplicate resource paths exist.
- The build artifact's checksum/version matches the deployed build.
- Do not rely on files existing in the source tree to read resources at runtime.

For systems requiring strict testing, you can write an integration test that executes `java -cp artifact.jar Main` after the build. Source-resource root bugs are often caught only at this step.

## 17. Practice Exercises and Answers

**Question 1.** What base name does `src/main/resources/com/acme/i18n/Labels_fr_CA.properties` correspond to?

**Answer:** `com.acme.i18n.Labels`. The corresponding locale is `fr-CA`. A standard classpath JAR must contain `com/acme/i18n/Labels_fr_CA.properties`.

**Question 2.** Why is `src/main/resources/Labels_vi.properties` not found when calling `getBundle("com.acme.Labels", Locale.forLanguageTag("vi"))`?

**Answer:** The base name specifies package `com.acme`, so Java looks for `com/acme/Labels_vi.properties` from the classpath root. A file placed at the root of resources has path `Labels_vi.properties`, which does not match.

**Question 3.** `Messages_vi_VN.properties` appears in `jar tf`, but under `src/main/resources/com/example/i18n`. Is that sufficient?

**Answer:** No, for the base name in the example. Java searches under `com/example/i18n` relative to the classpath root/JAR root, not under a `src/main/resources` folder inside the JAR.

**Question 4.** If `Messages_vi_VN.properties` does not have `app.title` while `Messages_vi.properties` does, what does `getString("app.title")` return?

**Answer:** Following the parent bundle chain, it returns `Ứng dụng bản địa hóa` from `Messages_vi.properties`.

**Question 5.** Why does `java -cp bundle-demo.jar com.example.app.Main` run while `java -jar bundle-demo.jar` reports a missing main manifest?

**Answer:** `-cp` specifies the JAR on the classpath and the Main class name explicitly; `-jar` requires a suitable manifest/launcher. These are separate concepts from whether resources have been packaged.

**Question 6.** Can we fix this in production using `new File("src/main/resources/...")`?

**Answer:** No, you should not. When packaged into a JAR, the source tree is not necessarily deployed. Use `ResourceBundle` or `ClassLoader.getResourceAsStream` to read entries via the classpath.

**Question 7.** Why does a Spring Boot JAR contain `BOOT-INF/classes` and still load resources?

**Answer:** A Spring Boot executable JAR uses a loader that constructs the runtime classpath from its own layout. The root-entry rule for standard classpath JARs does not apply directly to this layout.

**Question 8.** Can Java 17 read Vietnamese messages directly in `.properties` saved in UTF-8?

**Answer:** Yes, for standard Java 9+ property resource bundles, per JEP 226. Do not confuse this with `Properties.load(InputStream)`, which uses ISO-8859-1 rules.

**Question 9.** `getBundle(...)` succeeds, but `getString("missing.key")` fails. Should you fix packaging first?

**Answer:** Not necessarily. Check the key in the bundle and its parents. `MissingResourceException` can be a **missing key** error rather than a missing file error.

**Question 10.** To be sure a deployed JAR does not depend on the IDE, which test is reliable?

**Answer:** Run `jar tf` to inspect the entries, then execute the built JAR directly using the appropriate runtime launcher/classpath from an environment **without the source tree**.

## 18. Summary

- **Base names** use dots, **resource paths** use `/`; for `com.example.i18n.Messages` and `vi-VN`, the file must have the path `com/example/i18n/Messages_vi_VN.properties` from the classpath root.
- In standard Maven/Gradle projects, place files in `src/main/resources` so the build tool copies and packages them; do not nest the entire `src/main/resources` directory inside the JAR.
- **Verify the built JAR with `jar tf`** and test running the artifact directly; running in the IDE does not prove packaging is right.
- `ResourceBundle.getBundle` performs locale variant lookup and key fallback. `ClassLoader.getResourceAsStream` reads a specific resource; `new File(...)` is unsuitable for entries inside a JAR.
- Java 9+ has UTF-8 rules for property resource bundles. Resource path errors, missing keys, encoding errors, and manifest/launcher errors are **different** classes of problems.
- Named modules and Spring Boot executable JARs have their own resource lookup/packaging models; verify the exact runtime type before applying a fix.

**Official Documentation and References:**

- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Java SE 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html)
- [OpenJDK JEP 226 — UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226)
- [Maven Resources Plugin — Resource directories](https://maven.apache.org/plugins/maven-resources-plugin/examples/resource-directory.html)
- [Gradle Java Plugin — Project layout and resources](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Java SE 21 — jar tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
