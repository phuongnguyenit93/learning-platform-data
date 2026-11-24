# Packages, Classpath, JARs, and How Java Finds Classes

In Spring Boot, a class may compile normally yet fail at runtime with `ClassNotFoundException`, `NoClassDefFoundError`, or `Could not find or load main class`. To understand these errors, you first need to distinguish a **class's fully qualified name**, **where bytecode resides**, **how JARs are packaged**, and **the JVM's class-loading mechanism**.

This lesson belongs to the **Prerequisites** section of **Spring Boot Fundamentals**. Concepts are explained starting from plain Java, then connected to a Spring Boot project layout.

## 1. From a `.java` File to a Class Used by the JVM

A Java program typically goes through two distinct phases:

```text
Source code (.java)
    │
    ▼
javac — compiles; needs to find the data types referenced by the source code
    │
    ▼
Bytecode (.class)
    │
    ├── resides in the classes/ directory
    └── or packaged inside a JAR
                │
                ▼
java — launches the JVM
                │
                ▼
Class loader locates and loads the classes to be used
                │
                ▼
JVM links, initializes classes when needed, and executes bytecode
```

Three questions to keep separate:

- **What is the class's name?** The `package` name combined with the class name forms the *fully qualified class name*.
- **Where is the class located?** The `classpath` or corresponding class-loading mechanism indicates where compiled code can be found.
- **How is the class distributed?** A JAR bundles `.class` files and resources into an archive; the JAR structure determines how the program is launched.

A `.java` file is not what the JVM normally looks for to execute. The JVM requires compiled class definitions or classes supplied by the runtime.

## 2. `package`: Identifying and Organizing Classes

### 2.1. Short Name and Fully Qualified Name

Consider the class:

```java
package com.example.catalog;

public class Product {
    private final String name;

    public Product(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
```

- Short name: `Product`.
- Package: `com.example.catalog`.
- Fully qualified name: `com.example.catalog.Product`.

Two classes with the same short name can coexist if they belong to different packages, such as `com.example.catalog.Product` and `com.example.billing.Product`.

The `package` declaration normally sits at the top of the source file, before `import` statements. Java conventions use lowercase letters for package names and reverse domain names to reduce naming collisions.

### 2.2. `package` and Directory Paths

In a typical Maven or Gradle project, the source layout should mirror the package:

```text
src/main/java/
└── com/
    └── example/
        └── catalog/
            └── Product.java
```

After compiling to an output directory `out`, the class appears as:

```text
out/
└── com/
    └── example/
        └── catalog/
            └── Product.class
```

Here, `out` is the **classpath root**, and `com/example/catalog/Product.class` is the path corresponding to the class name. Using `.` in package names and directory separators in file paths are two representations of the same logical structure.

Keep the distinction clear: the `package` declaration determines the class's name; placing source files according to package is an important convention for build tools and IDEs. A compiler can accept source files from another path if explicitly specified, but maintaining the matching directory structure keeps source and resource lookup predictable for tools.

### 2.3. What `import` Does—and Does Not Do

Example in another package:

```java
package com.example.checkout;

import com.example.catalog.Product;

public class CheckoutService {
    public String label(Product product) {
        return product.getName();
    }
}
```

`import` lets you write `Product` instead of `com.example.catalog.Product` in source code. It does **not** download libraries, copy classes, or add anything to the classpath.

If `Product.class` or the library containing it is missing from the compilation inputs, `import` will not help `javac` find the class. If the class is present at compile time yet missing at runtime, the program can still fail when the JVM needs that class.

Classes in `java.lang` are imported implicitly; other classes generally require an `import` or their fully qualified name. Avoid using the *unnamed/default package* in real projects, especially in Spring Boot applications.

## 3. `classpath`: The Set of Locations to Search for Classes and Resources

The **classpath** is a list of directories containing bytecode and JAR files that Java tools can use to locate classes along with accompanying resources. It is neither a package nor a single directory.

Example:

```text
out/                     # root directory containing .class files
libs/common-utils.jar    # packaged library
libs/json-support.jar
```

When a class loader searches for `com.example.catalog.Product` inside directory `out`, the corresponding path is:

```text
out/com/example/catalog/Product.class
```

When searching inside a JAR, it looks up an entry named:

```text
com/example/catalog/Product.class
```

The classpath must point to the **root** containing the package hierarchy, not directly into the `.../catalog` directory just because the class happens to live there.

### 3.1. Compile-Time vs. Runtime Classpath

These two commands serve two separate stages:

```bash
javac -cp "libs/common-utils.jar" -d out src/com/example/app/Main.java
java -cp "out:libs/common-utils.jar" com.example.app.Main
```

- `javac -cp`: where the compiler searches for compiled types used by the source code.
- `java -cp`: where the application class loader searches for classes at runtime.
- `javac -d out`: where the compiler writes `.class` files; `-d` does **not** automatically place `out` on the classpath of a subsequent `java` command.
- `com.example.app.Main`: the fully qualified name of the class containing the `main` entry point.

The example above uses the Linux/macOS classpath separator. On Windows, use `;`:

```powershell
java -cp "out;libs/common-utils.jar" com.example.app.Main
```

The `:` or `;` character **separates classpath entries**, unlike `.`, which separates segments of a package name.

In simple commands, `-cp` and `-classpath` are equivalent. Depending on how an application is launched, the `CLASSPATH` environment variable may be used, but passing `-cp` explicitly in the command makes dependencies clear. When `-cp` is specified, its value overrides the `CLASSPATH` variable for that command.

### 3.2. Library Directories and Wildcards

You can include all JARs directly inside a directory:

```bash
# Linux/macOS
java -cp "out:libs/*" com.example.app.Main
```

```powershell
# Windows PowerShell
java -cp "out;libs/*" com.example.app.Main
```

`libs/*` is expanded by the Java launcher to the JARs inside that directory; it does not recursively search subdirectories. Wrapping the classpath in quotes prevents the shell from interpreting special characters unexpectedly.

The classpath is normally for application classes and external libraries; standard classes like `java.lang.String` come from the Java runtime modules, so you do not add JDK JAR files to the classpath.

## 4. Plain Java Practice: Compiling, Running, and Packaging a JAR

To observe the exact relationship between packages, class names, and the classpath, create these two source files:

```text
sample/
└── src/
    └── com/
        └── example/
            └── lesson/
                ├── Main.java
                └── Greeting.java
```

`src/com/example/lesson/Greeting.java`:

```java
package com.example.lesson;

public class Greeting {
    public static String message() {
        return "Hello from Java!";
    }
}
```

`src/com/example/lesson/Main.java`:

```java
package com.example.lesson;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
```

From the `sample` directory, run:

```bash
javac -d out src/com/example/lesson/Greeting.java src/com/example/lesson/Main.java
java -cp out com.example.lesson.Main
```

Output:

```text
Hello from Java!
```

After compilation, the resulting layout is:

```text
out/
└── com/
    └── example/
        └── lesson/
            ├── Greeting.class
            └── Main.class
```

Why not run `java -cp out Main`? Because the class is not named `Main` in the unnamed package; its actual name is `com.example.lesson.Main`. Likewise, `java -cp out/com/example/lesson com.example.lesson.Main` sets the wrong root for resolving the fully qualified class name.

### 4.1. Creating a Standard JAR

JAR (*Java ARchive*) is a ZIP-based archive format that can contain bytecode, resources, and metadata.

Continuing inside the `sample` directory:

```bash
jar --create --file lesson.jar --main-class com.example.lesson.Main -C out .
jar --list --file lesson.jar
java -jar lesson.jar
```

Depending on the JDK, the listing will include entries similar to:

```text
META-INF/
META-INF/MANIFEST.MF
com/example/lesson/Greeting.class
com/example/lesson/Main.class
```

`-C out .` instructs the `jar` tool to take the contents **inside** `out` as the root of the JAR. As a result, the archive contains `com/example/lesson/Main.class` without an `out/` prefix.

The `--main-class` option records the entry point in `META-INF/MANIFEST.MF`. The manifest may contain the line:

```text
Main-Class: com.example.lesson.Main
```

Because of this, `java -jar lesson.jar` knows which class to run. A JAR **does not require** a `Main-Class` if it is only used as a library.

With the example JAR, you can also run:

```bash
java -cp lesson.jar com.example.lesson.Main
```

This specifies the `main` class directly without relying on `Main-Class` in the manifest.

### 4.2. When a JAR Depends on External Libraries

Suppose `Main` uses a class inside `libs/parser.jar`. A standard JAR only contains the files explicitly included during packaging; it **does not automatically embed every dependent library**.

When running with a classpath:

```bash
# Linux/macOS
java -cp "lesson.jar:libs/*" com.example.lesson.Main
```

```powershell
# Windows
java -cp "lesson.jar;libs/*" com.example.lesson.Main
```

When running `java -jar lesson.jar`, the `-cp` option on the launch command is not used as the user classpath for the application. For standard JARs, to have `java -jar` locate external libraries, you can declare the appropriate paths in the manifest's `Class-Path` attribute or use another distribution/launch approach. The `Class-Path` attribute in the manifest points to separate external JARs or directories; it does not turn nested JARs inside the archive into regular classpath entries.

The key takeaway: **packaging the main class** does not equate to **packaging all dependencies required at runtime**.

## 5. How Does the JVM Find Classes via Class Loaders?

### 5.1. From Class Name to Bytecode

When the application needs `com.example.lesson.Greeting`, a class loader can look up the class definition via an entry corresponding to `com/example/lesson/Greeting.class`. If multiple directories/JARs exist on the classpath, their location and lookup order influence which definition gets chosen.

Simplified model:

```text
java -cp "out:libs/*" com.example.lesson.Main
       │
       ▼
Application class loader
       │
       ├── requested to load com.example.lesson.Main
       ├── locates the appropriate .class definition source
       ├── Main calls Greeting.message()
       └── when needed, loads com.example.lesson.Greeting
                       │
                       ▼
                    execution
```

Class loading does not mean the JVM scans and loads every available class immediately at startup. Many classes are only loaded, linked, or initialized on demand; exact timing depends on JVM rules and how the program references the class.

### 5.2. Common Class Loaders

Modern Java typically includes these tiers:

| Class Loader | General Role |
|---|---|
| Bootstrap class loader | Loads core platform classes of the Java runtime. |
| Platform class loader | Loads classes belonging to platform modules not handled directly by the bootstrap loader. |
| Application/System class loader | Loads application classes from the classpath under standard launch modes. |
| Custom class loader | Created by frameworks, application servers, or tools to support custom class-loading strategies. |

Most Java class loaders follow the **parent delegation** model. This enables sharing platform classes and prevents an application class from accidentally replacing core Java classes. Some frameworks implement custom strategies, so do not assume every class loader follows identical lookup rules.

The lifecycle around a class includes phases such as **loading**, **linking** (verification, preparation, and resolution of references), and **initialization**. For instance, a `static` block may run when the class is initialized, not necessarily when the JAR is opened.

### 5.3. Direct Class References vs. Runtime Lookup by Name

Explicit type references:

```java
Greeting.message();
```

differ from string-based lookup:

```java
Class<?> type = Class.forName("com.example.lesson.Greeting");
System.out.println(type.getName());
```

In the second case, the class name is resolved at runtime. If the appropriate loader cannot find the class definition, `Class.forName` can throw `ClassNotFoundException`. Frameworks frequently perform similar dynamic lookups when handling configuration, plugins, resources, or annotations.

Even when a class exists, the class loader does not automatically register it as a Spring bean. **Having a class on the classpath** and **having a bean in the Spring ApplicationContext** are two separate requirements.

### 5.4. Classpath and Module Path Are Not the Same

Since Java 9, the Java Platform Module System (JPMS) also provides the **module path** via `--module-path` and module descriptors via `module-info.java`. The module path adds rules for module readability, exported packages, and dependency enforcement.

This lesson uses the **classpath** model common to Spring Boot applications. When you encounter `--module-path` or `module-info.java`, recognize it as a distinct mechanism, not merely a new name for `-cp`.

## 6. Connecting to Spring Boot Project Structure

A Spring Boot application typically has the following source layout:

```text
src/main/
├── java/
│   └── com/example/shop/
│       ├── ShopApplication.java
│       ├── controller/ProductController.java
│       └── service/ProductService.java
└── resources/
    ├── application.yml
    └── static/
```

`ShopApplication.java`:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

`ProductController` and `ProductService` reside in subpackages under `com.example.shop`. Packages are not only for locating bytecode; they also affect Spring Boot's default component scanning scope: `@SpringBootApplication` typically enables scanning the application class's package and its subpackages. Consequently, placing the startup class in an appropriate root package is usually a good choice.

A class present in bytecode yet located outside the scan scope may not become a bean. In that case, a missing-bean error is not necessarily a classpath issue.

### 6.1. Build Tools Manage the Classpath

With Maven or Gradle, you declare dependencies; the build tool resolves libraries and constructs the compile classpath and runtime classpath. The standard source layout is:

- `src/main/java`: application Java code.
- `src/main/resources`: configuration and resources placed on the runtime classpath.
- `src/test/java` and `src/test/resources`: test code and resources, typically with their own classpath.

For example, `application.yml` is accessed on the classpath because of resource packaging, not because of a Java package declaration.

In a Gradle project with the Spring Boot plugin, the `bootJar` task builds an executable JAR; in a Maven project with the Spring Boot Maven Plugin and the `repackage` goal, the artifact can likewise be packaged into an executable JAR. Output filenames and locations depend on project configuration (commonly `build/libs/` for Gradle and `target/` for Maven).

### 6.2. Standard JAR vs. Spring Boot Executable JAR

A default-packaged Spring Boot executable JAR has a distinctive layout:

```text
shop-app.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/shop/ShopApplication.class
    │   └── application.yml
    └── lib/
        ├── spring-boot-....jar
        └── other-libraries.jar
```

Two key locations:

- `BOOT-INF/classes/`: application classes and resources.
- `BOOT-INF/lib/`: packaged dependency JARs nested inside.

Unlike the simple JAR earlier, `java -jar shop-app.jar` does not look for `ShopApplication.class` directly at the root of the archive. It runs the **Spring Boot launcher** specified by `Main-Class` in the manifest. The launcher sets up class loading capable of reading both `BOOT-INF/classes` and the nested JARs in `BOOT-INF/lib`, then invokes the application class declared in `Start-Class`.

Example of key manifest entries in Spring Boot 3.2+:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.shop.ShopApplication
```

This illustrates packaging that uses `JarLauncher`; exact launcher names can vary in other Spring Boot versions or packaging formats. Do not manually change `Main-Class` to `ShopApplication` and expect nested JAR loading to keep working.

To inspect the built archive:

```bash
jar --list --file build/libs/shop-app.jar
java -jar build/libs/shop-app.jar
```

These example commands assume the produced artifact is named `shop-app.jar`; substitute the actual filename generated by your project.

**Why not run `java -cp shop-app.jar com.example.shop.ShopApplication`?** In this executable JAR layout, application classes reside under `BOOT-INF/classes/` rather than the root of the JAR, and dependencies reside under `BOOT-INF/lib/`. The standard Java classpath does not automatically treat those nested locations as classpath roots. The intended way to launch it is `java -jar` or the launch mechanism provided by your build tool or framework.

## 7. Typical Errors and Their Causes

| Symptom | Common Cause | Investigation Path |
|---|---|---|
| `Could not find or load main class com.example.app.Main` | Wrong fully qualified main class name, wrong classpath root, or `Main.class` has not been compiled. | Check the `package` declaration, `.class` path, and `-cp` argument. |
| `ClassNotFoundException` | A runtime class lookup by name could not find the class via the active class loader. | Check the class name, involved class loader, dependencies, and JAR contents. |
| `NoClassDefFoundError` | The JVM needs a class definition but cannot load/link it even though compilation succeeded; sometimes caused by an earlier initialization failure. | Check the runtime classpath, the root cause in `Caused by`, and `static` initialization. |
| `NoSuchMethodError` | Runtime has a version of a class lacking a method expected by compiled code. | Check library versions and dependency conflicts. |
| `UnsupportedClassVersionError` | Bytecode was compiled for a newer Java version than the running JVM supports. | Compare `java -version` with the Java version used for compilation. |
| `Unable to access jarfile` | Incorrect JAR path, missing file, or insufficient read permissions. | Verify the file path and permissions. |
| Spring reports a missing bean | Class was not created/registered as a bean, scan scope does not cover it, or conditional configuration was not met. | Check `@Component`, `@Bean`, scanned packages, and Spring configuration. |

Two errors that are easiest to confuse:

- **`ClassNotFoundException`** is a checked exception typically thrown by dynamic class-loading APIs such as `Class.forName(...)`.
- **`NoClassDefFoundError`** is a `LinkageError`. For example, code compiled against `parser.jar` runs without that library present: the JVM only discovers the absence when it needs the class definition. This error can also appear after an earlier class initialization failed; always read the full stack trace rather than assuming every case is a missing JAR.

Another warning: if multiple versions containing the same class name exist on the classpath, the application may load a different version than the one used at compile time. This is a common cause of linkage errors like `NoSuchMethodError`. Consistent dependency version management with Maven/Gradle is much safer than manually copying JARs around.

## 8. How to Diagnose When Java Cannot Find a Class

Suppose a launch command fails; trace in order from the class name to where the class resides:

1. **Verify the fully qualified name.** Open the source file or entry-point configuration to verify the package and class name, e.g., `com.example.lesson.Main`.
2. **Verify the actual built artifact.** For a classes directory, the class must correspond to `com/example/lesson/Main.class` under a classpath root. For a JAR, inspect the entries inside the archive.
3. **Verify the launch mechanism.** `java -cp` requires the main class name; `java -jar` requires an executable archive with the right structure/manifest.
4. **Check runtime dependencies.** A library can be present on the compile classpath yet absent at runtime. For a Spring Boot executable JAR, also inspect `BOOT-INF/lib`.
5. **Read the deepest cause in the stack trace.** Sometimes the reported class name is a consequence of another incompatible dependency or a class initialization failure.

Helpful commands:

```bash
java -version
javac -version
jar --list --file lesson.jar
```

On JVMs supporting class-loading diagnostics, you can use `-Xlog:class+load=info` to observe where classes are loaded from:

```bash
java -Xlog:class+load=info -cp out com.example.lesson.Main
```

Depending on the application, the output can be very verbose; filter for the package under investigation. With custom framework class loaders, the reported class source may differ from a simple linear classpath mental model.

## 9. Three Scenarios to Remember

**Scenario A — Moving a source file while keeping the same `package`.** The class's fully qualified name is still determined by the `package` statement. When compiled with `javac -d out`, the output bytecode path continues to mirror the package; however, build tools may not find source files placed in arbitrary locations.

**Scenario B — Compiling succeeds with library A, but running fails without A.** The compile classpath satisfied the compiler, while the runtime classpath lacks the needed definition. Some code paths may run fine before hitting the missing class; the failure can surface late.

**Scenario C — `ShopApplication.class` lives under `BOOT-INF/classes`.** This is the normal structure of a Spring Boot executable JAR. Run `java -jar` so the Spring Boot launcher sets up the class-loading environment for the application and its nested dependencies.

Always separate **class name (package)**, **where classes are looked up (classpath/class loader)**, and **how code is packaged/launched (JAR/launcher)**. When all three align, both plain Java and Spring Boot have a consistent basis for finding and using the right classes.
