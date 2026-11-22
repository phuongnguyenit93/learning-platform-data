# Implicit requires java.base

In the Java Platform Module System (JPMS), every named module has a direct dependency relationship to the foundational module `java.base`, except `java.base` itself. If `module-info.java` does not explicitly write the directive `requires java.base;`, the Java compiler automatically adds this directive into the compiled module descriptor. Therefore, module source code usually does not need to declare `java.base` explicitly.

This is the foundational dependency of the Java ecosystem. Fundamental types such as `Object`, `String`, `System`, `Class`, `Throwable`, collections, basic I/O, date/time, and many common APIs reside in `java.base`. Every module needs readability to this module in order to use those foundational types.

## 1. java.base is the foundational module

`java.base` is the core module of Java SE. It contains packages widely used across almost all programs, for example:

| Package | API Examples |
|---|---|
| `java.lang` | `Object`, `String`, `System`, `Math`, `Class`, `Throwable` |
| `java.util` | `List`, `Map`, `Set`, `Optional`, `Collections` |
| `java.io` | `InputStream`, `OutputStream`, `File`, `Serializable` |
| `java.nio` and `java.nio.file` | `ByteBuffer`, `Path`, `Files` |
| `java.time` | `LocalDate`, `Instant`, `Duration` |
| `java.math` | `BigInteger`, `BigDecimal` |
| `java.util.concurrent` | `ExecutorService`, `CompletableFuture`, `ConcurrentHashMap` |

The `java.lang` package is also implicitly imported by Java into every compilation unit, so programs can use `String` or `System` without writing an `import` statement. That is an import rule of the Java language; it differs from module readability rules. Readability to `java.base` is the module-level condition for code in a module to use APIs belonging to the foundational module.

## 2. Why is requires java.base added implicitly?

A typical module can start with a very short descriptor:

```java
module com.acme.app {
}
```

Even without a `requires` line, the `com.acme.app` module can still read `java.base`. According to JPMS rules, if a module declaration does not contain `requires java.base;`, the compiler implicitly adds this dependency when generating the module descriptor. In the `module-info.class` file, the dependency is marked as `mandated` (mandatory by platform rules).

The following two forms can be understood as having the same meaning regarding readability to `java.base`:

```java
// Typical source: no need to declare java.base
module com.acme.app {
}
```

```java
// Explicit description of the foundational relationship
module com.acme.app {
    requires java.base;
}
```

In real-world projects, you should let the compiler handle this implicit dependency rather than adding an unnecessary line to every `module-info.java`. The key point is that the dependency still exists in the compiled module descriptor, even though it does not appear in the source code.

The `java.base` module cannot declare a dependency on itself. It is the foundation on which other Java SE modules rely, avoiding creating a dependency cycle at the lowest layer of the platform.

## 3. Example: Using java.base APIs without declaring requires

Modular project structure:

```text
src/
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
```

Descriptor:

```java
// src/com.acme.app/module-info.java
module com.acme.app {
}
```

Class using several APIs from `java.base`:

```java
// src/com.acme.app/com/acme/app/Main.java
package com.acme.app;

import java.time.LocalDate;
import java.util.List;

public class Main {
    public static void main(String[] args) {
        List<String> topics = List.of("String", "Collections", "Date");

        System.out.println("Today: " + LocalDate.now());
        System.out.println("Topics: " + topics);
        System.out.println("Runtime: " + System.getProperty("java.version"));
    }
}
```

Compile and run from the project directory:

```shell
javac --module-source-path src -d out -m com.acme.app
java --module-path out -m com.acme.app/com.acme.app.Main
```

The source code does not declare `requires java.base;`, yet it can still use `List`, `LocalDate`, `String`, and `System`. These types all belong to `java.base`, and the `com.acme.app` module reads the foundational module thanks to the implicit directive.

## 4. Inspecting the implicit dependency in the module descriptor

You can inspect a compiled module's descriptor using `javap`:

```shell
javap -v out/com.acme.app/module-info.class
```

In the `Module:` section, look for the `requires` entry. The output will show the `java.base` module along with the `mandated` flag, even though the `module-info.java` source file has no corresponding line. This flag indicates that the directive was added according to platform rules.

Another approach is to package the module into a JAR and then inspect its descriptor:

```shell
jar --create --file com.acme.app.jar -C out/com.acme.app .
jar --describe-module --file com.acme.app.jar
```

The module description output will list the `java.base` dependency as `mandated`. You can also inspect the foundational module of the JDK currently in use:

```shell
java --describe-module java.base
```

These commands are useful when inspecting actual artifacts, especially when a build configuration produces a module descriptor different from what a reader might infer from the source code.

## 5. java.base does not contain all of Java SE

You should not view `java.base` as the entirety of the Java standard library. Java SE is split into multiple modules to separate functionality. Several familiar APIs reside outside `java.base`:

| Module | Typical Functionality |
|---|---|
| `java.sql` | JDBC and database access APIs |
| `java.desktop` | AWT, Swing, and desktop graphics |
| `java.xml` | XML processing APIs |
| `java.logging` | Java Logging API |
| `java.net.http` | HTTP Client API |

If an application module uses APIs belonging to other modules, it must declare the corresponding dependencies. For example:

```java
module com.acme.reporting {
    requires java.sql;
}
```

Here, `requires java.sql;` is necessary if code in the module uses JDBC APIs. The implicit dependency on `java.base` does not automatically make an application read every module in the JDK.

You should also distinguish packages with similar names: basic `java.net` belongs to `java.base`, whereas the modern HTTP Client resides in a separate module `java.net.http`. Always look up the module that owns a package rather than inferring solely from package name prefixes.

## 6. The implicit dependency is neither exports nor requires transitive

The implicit `requires java.base` directive creates a readability relationship from the current module to `java.base`. It does not do any of the following:

- It does not export the application module's packages to other modules.
- It does not make the current module automatically read all other modules in the JDK.
- It does not replace `requires` for dependencies such as `java.sql`, `java.desktop`, or `java.xml`.
- It does not mean modules that depend on the application will automatically read all of the application's dependencies.

`requires` and `exports` address two different directions: `requires` declares which modules the current module needs to read; `exports` exposes which packages other modules can access. The implicit dependency on `java.base` does not alter the API boundaries of the application module.

## 7. Common Misconceptions

**"Without requires in module-info.java, a module cannot use String."**

False. Every regular named module has an implicit dependency on `java.base`, which contains `String`.

**"java.base contains all classes in the JDK."**

False. Many APIs are separated into modules such as `java.sql`, `java.desktop`, `java.xml`, and `java.net.http`. These modules still need to be declared when an application uses them.

**"The compiler doesn't write requires java.base because the dependency doesn't exist."**

False. The dependency is added into the compiled module descriptor and can be observed with `javap -v` or `jar --describe-module`.

**"java.base can be omitted to create a smaller runtime."**

The foundational module cannot be removed from a valid Java runtime. When creating a runtime image with `jlink`, `java.base` is a mandatory root module; image optimization focuses on the additional modules that the application actually needs.

## 8. How to apply when designing modules

- Keep `module-info.java` concise; do not declare `requires java.base;` in regular modules.
- Explicitly declare other JDK modules when using their APIs, such as `java.sql` or `java.logging`.
- When encountering the error `module ... does not read ...`, identify the module containing the package in use and add the appropriate `requires`; do not assume all APIs belong to `java.base`.
- When inspecting artifacts, examine the compiled module descriptor rather than reading only the source file.
- When creating a runtime image with `jlink`, keep `java.base` and include only the modules needed by the application.

The implicit `requires java.base` provides every Java module with the core language foundation and essential libraries. Thanks to this rule, module authors can focus on declaring application-specific dependencies, while the foundational relationship is always guaranteed by JPMS.