# Resource Lookup in Modular Classes (Java JPMS)

## 1. Objectives and Context

Since Java 9, the Java Platform Module System (JPMS) allows applications to organize code into **named modules** declared via `module-info.java`. When migrating from the classpath to the module path, the way configuration files, templates, text, JSON, or resources packaged with the application are located can change.

After this lesson, you will be able to:

- Accurately determine a resource's name and its location inside a JAR/module.
- Choose appropriately among `Class.getResource(...)`, `Class.getResourceAsStream(...)`, `Module.getResourceAsStream(...)`, and `ClassLoader.getResource(...)`.
- Understand why the same resource can be read from a class inside a module yet returns `null` when looked up through a class loader or from another module.
- Use `opens` in the right situations; distinguish `opens` from `exports`.
- Read resources safely when running from an IDE, JAR, or module path without depending on machine-local paths.

**Scope:** "Resource" here refers to a file packaged in the build output/JAR and looked up by a logical name, such as `com/example/app/app.properties`. It is not synonymous with a physical file on disk that can be opened directly via `Path`.

## 2. Resource Names and APIs to Remember

Suppose the structure inside the packaged artifact is:

~~~text
module-info.class
com/example/app/App.class
com/example/app/app.properties
com/example/app/templates/welcome.txt
config/global.json
~~~

Resource names use forward slashes `/` as separators, even when the program runs on Windows. Do not include `src/main/resources` or absolute machine paths in the lookup name.

| API | How the name is interpreted | Suitable when |
| --- | --- | --- |
| `App.class.getResource("app.properties")` | Relative to package `com.example.app`; returns `URL` or `null` | You need the URL of a resource alongside the class |
| `App.class.getResourceAsStream("app.properties")` | Relative to package `com.example.app`; returns `InputStream` or `null` | Reading the contents of a resource in the class's module |
| `App.class.getResourceAsStream("/config/global.json")` | Leading `/` denotes the module/classpath root | The resource is not in the same package |
| `App.class.getModule().getResourceAsStream("com/example/app/app.properties")` | Full name from the module root, **without** a leading `/` | You want to target the exact module owning the resource |
| `App.class.getClassLoader().getResource("com/example/app/app.properties")` | Name from the loader's search root, **without** a leading `/` | Looking up via class loader when visibility boundaries are clearly understood |

For `Class.getResource*`, a name starting with `/` is absolute; a name not starting with `/` is resolved relative to the class's package. By contrast, `ClassLoader.getResource*` and `Module.getResourceAsStream` take a logical name from the root, without a leading `/`.

For example, the following calls target the same resource:

~~~java
App.class.getResourceAsStream("app.properties");
App.class.getResourceAsStream("/com/example/app/app.properties");
App.class.getModule().getResourceAsStream(
    "com/example/app/app.properties"
);
~~~

They are not completely interchangeable in every situation: each API has its own module-selection context and access rules, especially when the resource resides in a named module.

## 3. Complete Example: Reading Configuration Directly Inside a Named Module

Below is a Java 11+ project structure using the standard Maven/Gradle layout:

~~~text
src/
  main/
    java/
      module-info.java
      com/example/app/App.java
    resources/
      com/example/app/app.properties
~~~

File `src/main/java/module-info.java`:

~~~java
module com.example.app {
}
~~~

File `src/main/resources/com/example/app/app.properties`:

~~~properties
app.name=ModularResourceDemo
app.mode=production
~~~

File `src/main/java/com/example/app/App.java`:

~~~java
package com.example.app;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws IOException {
        Properties settings = loadSettings();
        System.out.println(settings.getProperty("app.name"));
        System.out.println(settings.getProperty("app.mode"));
    }

    public static Properties loadSettings() throws IOException {
        Properties settings = new Properties();

        try (InputStream in =
                 App.class.getResourceAsStream("app.properties")) {
            if (in == null) {
                throw new IOException(
                    "Missing resource com/example/app/app.properties"
                );
            }

            settings.load(
                new InputStreamReader(in, StandardCharsets.UTF_8)
            );
        }

        return settings;
    }
}
~~~

Expected output:

~~~text
ModularResourceDemo
production
~~~

**Why does this work?** `App.class` is in `com.example.app` and belongs to module `com.example.app`. The relative name `app.properties` resolves to `com/example/app/app.properties`. The resource is in the same module as the reading code; neither `exports` nor `opens` is needed solely for internal reads like this.

When using Maven/Gradle with the default configuration, files in `src/main/resources` are copied into the build's classpath/output and can then be packaged into the JAR. With manual `javac` builds, you must copy resource files into the right output location yourself because `javac` does not package resources automatically.

Note: `Properties.load(InputStream)` follows the properties format's own rules and does not interpret all bytes as UTF-8 by default. The example uses `InputStreamReader` with `StandardCharsets.UTF_8` to explicitly specify the encoding.

## 4. JPMS Encapsulation and Access Rules

A common cause of `null` is **encapsulation**: JPMS can hide resources inside a named module's packages from code in other modules or lookups via a class loader.

Distinguish:

- `exports com.example.lib;` exposes **public types** of the package to other modules at compile time and runtime; it does not automatically open the package's resources to all lookup APIs.
- `opens com.example.lib;` opens the package to all modules at runtime, supporting both deep reflection and the associated resource lookup rules.
- `opens com.example.lib to com.example.consumer;` opens conditionally to the specified module.
- `open module com.example.lib { ... }` opens all packages of the module; use only if such broad access is intentionally needed.

A practical view:

| Context of looking up a resource in a named module's package | Behavior to remember |
| --- | --- |
| A class in the same module calls `Class.getResourceAsStream` | Can find internal resources using the proper name; no need to open the package externally |
| Code in another module calls `targetModule.getResourceAsStream` | The package containing the resource must be opened to the calling module |
| `ClassLoader.getResource` / `getResourceAsStream` searches via loader | For ordinary resources inside a named module's package, the package must be **opened unconditionally** |
| Only `exports`, without `opens` | Not sufficient to guarantee finding resources via a loader or from another module |

Important detail: Java documentation includes an exception for resource names ending in `.class` in encapsulation rules. Do not infer from being able to look up `Foo.class` that every `.properties`, `.json`, or template file in the same package is also accessible.

**Qualified opens is not equivalent to unconditional opens.** For example, `opens com.example.assets to com.example.consumer;` may allow code in `com.example.consumer` to use `Module.getResourceAsStream`, but it does not make a global search via `ClassLoader.getResource` see resources in that package the way `opens com.example.assets;` does.

## 5. Example: Reading a Resource from Another Module

Suppose an application has two named modules, `com.example.assets` and `com.example.consumer`. The assets module has a Java class in package `com.example.assets` and a `colors.json` file packaged in the same package.

Structure of the relevant parts:

~~~text
com.example.assets
  module-info.java
  com/example/assets/Anchor.java
  com/example/assets/colors.json

com.example.consumer
  module-info.java
  com/example/consumer/Consumer.java
~~~

`module-info.java` of assets:

~~~java
module com.example.assets {
    opens com.example.assets to com.example.consumer;
}
~~~

`module-info.java` of consumer:

~~~java
module com.example.consumer {
    requires com.example.assets;
}
~~~

In `Consumer.java`:

~~~java
package com.example.consumer;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class Consumer {
    public static void main(String[] args) throws IOException {
        Module assets = ModuleLayer.boot()
            .findModule("com.example.assets")
            .orElseThrow(() -> new IllegalStateException(
                "Module com.example.assets is not resolved"
            ));

        try (InputStream in = assets.getResourceAsStream(
                "com/example/assets/colors.json")) {
            if (in == null) {
                throw new IOException("Cannot read colors.json");
            }

            String json = new String(
                in.readAllBytes(), StandardCharsets.UTF_8
            );
            System.out.println(json);
        }
    }
}
~~~

Conditions that must be satisfied:

1. `com.example.assets` is in the resolved module graph; in the example above, `requires com.example.assets;` ensures the module relationship.
2. `colors.json` is actually packaged under `com/example/assets/`.
3. Package `com.example.assets` is opened to module `com.example.consumer`; calling `Module.getResourceAsStream` checks the caller's module.
4. The name passed to `Module.getResourceAsStream` is the name from the module root and does **not** start with `/`.

If any module needs to access this resource, you can use `opens com.example.assets;`. If only one specific consumer needs it, `opens ... to ...` usually expresses intent more clearly.

When a resource serves only the internal needs of the assets module, a better option is to let assets itself expose an API that reads it internally and returns the processed data; the consumer does not need to know the resource's location inside the JAR.

## 6. Why Can `ClassLoader.getResource` Return `null`?

Example:

~~~java
ClassLoader loader = App.class.getClassLoader();

var fromClass = App.class.getResource(
    "/com/example/app/app.properties"
);

var fromLoader = loader.getResource(
    "com/example/app/app.properties"
);
~~~

In a named module whose package is not unconditionally `opens`-ed, `fromClass` can locate the internal resource while `fromLoader` returns `null`. This is a difference in access rules, not necessarily a path error or build error.

Two additional points to note:

- A class loader can serve multiple modules; looking up by name through a loader is not an accurate way to select the module owning a resource. When names might collide, obtain the `Class` or `Module` of the component you actually want to read from.
- `Thread.currentThread().getContextClassLoader()` is suitable for certain frameworks/plugin mechanisms, but it does not automatically bypass JPMS encapsulation. Do not arbitrarily replace `App.class.getResourceAsStream` with the context loader when migrating an application to the module path.

The `ClassLoader` of some platform classes can be `null` (the bootstrap loader). If you need a loader API, you must handle this case; in ordinary modular application code, approaches based on `Class` or `Module` remain clearer in intent.

## 7. Reading Text, JSON, or Binary Data Using Streams

A simple way to read UTF-8 text, with the resource name from the module root:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class ResourceText {
    private ResourceText() {
    }

    public static String read(String absoluteResourceName)
            throws IOException {
        try (InputStream in = ResourceText.class.getModule()
                .getResourceAsStream(absoluteResourceName)) {
            if (in == null) {
                throw new IOException(
                    "Resource does not exist or is not accessible: "
                    + absoluteResourceName
                );
            }

            return new String(
                in.readAllBytes(), StandardCharsets.UTF_8
            );
        }
    }
}
~~~

Example usage inside the same module containing `ResourceText`:

~~~java
String text = ResourceText.read(
    "com/example/app/templates/welcome.txt"
);
~~~

For large resources, do not use `readAllBytes()` if you do not need to hold the entire content in memory; process incrementally via a stream or reader. For JSON, pass the stream/reader to an appropriate parser library. For images or binary data, keep them as bytes and avoid converting through `String`.

**Do not assume a resource is a regular file:**

~~~java
// Prone to failure when packaged in a JAR or runtime image:
Path path = Path.of(App.class.getResource("app.properties").toURI());
~~~

A URL from `getResource` may carry a scheme such as `jar:` or a runtime image scheme, which cannot always be converted into a `Path` on the default filesystem. If the downstream API accepts an `InputStream`, pass the stream directly. If a library strictly requires a physical file, you need a temporary extraction workflow with explicit lifecycle management.

## 8. Checking Packaging and Diagnosing Errors

When receiving `null`, check in order:

1. **Is the resource name exact?** `App.class.getResource("x.txt")` is relative to the package; `App.class.getResource("/x.txt")` is from the root. `Module` and `ClassLoader` do not use a leading `/`.
2. **Is the resource inside the artifact?** For a JAR, you can use `jar tf application.jar` to find the exact entry, including uppercase/lowercase letters. Java resource names are case-sensitive by path.
3. **Which module is it in?** Print `App.class.getModule().getName()` and check the module graph. Classes on the classpath belong to the unnamed module, unlike named modules on the module path.
4. **Which API is being used?** If `Class.getResourceAsStream` works while `ClassLoader.getResource` fails, review the `opens` package rules for named modules.
5. **Is it being called from another module?** With `Module.getResourceAsStream`, check `opens p to caller;` or `opens p;`. `exports` alone does not solve all resource lookup cases.
6. **Were resource files copied during the build?** `javac` compiles Java classes and does not copy resources automatically; Maven/Gradle typically have a resource processing step.
7. **Does it depend on class loader ordering?** If multiple JARs or modules contain the same name, do not rely on whichever resource is found first; reference the owning module/class to reduce ambiguity.

Minimal diagnostic snippet inside the failing module:

~~~java
System.out.println("Module: " + App.class.getModule().getName());
System.out.println("Loader: " + App.class.getClassLoader());
System.out.println("Relative: "
    + App.class.getResource("app.properties"));
System.out.println("Absolute: "
    + App.class.getResource(
        "/com/example/app/app.properties"));
~~~

There is no need to log the entire contents of configuration files, especially if the resource contains sensitive data. Log only the logical name, module, API called, and found/not-found result.

## 9. Common Misunderstandings

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `getResource("config.yml")` returns `null` | The file is at the root, but a relative name gets the package prepended | Use `getResource("/config.yml")` or move the file into the package |
| `ClassLoader.getResource("/a/b.txt")` cannot find it | Has a leading `/` in the name | Use `getResource("a/b.txt")` |
| Works in IDE, not found in JAR | Resource was not included in the JAR or artifact path differs | Check build output and `jar tf` |
| `Class` can read it, `ClassLoader` cannot find it | Package of the named module is not unconditionally `opens`-ed | Prefer lookup via the owning class/module; only open packages when genuinely needed |
| Another module cannot read via `Module.getResourceAsStream` | Package is not opened to the calling module | Declare `opens p to consumer;` or expose an internal reading API |
| Already `exports`-ed, yet resource still not found | `exports` governs public type accessibility, not equivalent to `opens` | Review the lookup API and package-opening rules |
| `Path.of(url.toURI())` fails | Resource resides inside a JAR/runtime image | Read via `InputStream` |
| Looking up resource in an unresolved module | Module does not belong to the active layer/graph | Ensure the module is resolved and select the right `ModuleLayer` |

## 10. Best Practices

- Prefer `SomeClass.class.getResourceAsStream(...)` for resources tied to that Java component; use `SomeClass.class.getModule().getResourceAsStream(...)` when you want to explicitly state the target module and absolute resource name.
- Use stable resource names without embedding source/build paths in application code; organize resources near the consuming package where sensible.
- Check for `null` and report errors with the resource name; wrap `InputStream` in `try-with-resources`.
- Use `opens` only to the extent required; do not open an entire module just to fix one incorrect lookup call.
- Establish clear API boundaries: the module owning the data can return parsed objects rather than forcing every consumer to locate files inside the module.
- When resources vary by environment, distinguish **read-only packaged resources** from **external configuration files**. For external files, use `Files.newInputStream(Path)` and a clear configuration policy.
- When integrating `ResourceBundle`, `ServiceLoader`, or frameworks using reflection, resource lookup and service registration are separate mechanisms; follow the contract of each API rather than merely changing paths.

## 11. Quick Checklist

1. `Class.getResource("x")`: relative to package; `Class.getResource("/x")`: from root.
2. `ClassLoader.getResource("a/b")` and `Module.getResourceAsStream("a/b")`: use root-based names, without a leading `/`.
3. In a named module, **the owning module and the package containing the resource** determine accessibility.
4. `exports` exposes Java APIs; `opens` governs runtime package openness, including resource lookup rules.
5. `Module.getResourceAsStream` is suitable when targeting a specific module; `ClassLoader.getResource` has lookup restrictions for encapsulated resources.
6. Read via streams, check for `null`, close streams; verify the resource is present in the artifact before suspecting JPMS.

**References for further lookup:** Javadoc for `java.lang.Class#getResource`, `java.lang.ClassLoader#getResource`, `java.lang.Module#getResourceAsStream`; *The Java Language Specification*, chapter on modules; OpenJDK JPMS guides.
