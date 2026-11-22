# Class.getResource: Relative Paths and Leading /

## 1. The Nature of Class.getResource

In Java, a *resource* is a data file used at runtime: configurations, templates, messages, images, certificates, etc. A resource can reside in a directory on the classpath, inside a JAR, or inside a named module. To locate a resource based on a class, Java provides:

~~~java
URL url = SomeClass.class.getResource("config.properties");
InputStream in = SomeClass.class.getResourceAsStream("config.properties");
~~~

`getResource` returns a `java.net.URL`, whereas `getResourceAsStream` returns an `InputStream`; both can return `null` when the resource is not found or cannot be accessed. Both APIs **share the same rules for interpreting path names**.

The most important point: **a leading `/` in the resource name string determines the starting point of the search**.

- **Without a leading `/`:** the path is relative to **the package of the `Class` object on which the method is called**.
- **With a leading `/`:** the path is absolute from **the root of the resource namespace**. The API strips the leading `/` when passing the name to the underlying lookup mechanism.
- The `/` character is the resource name separator regardless of the operating system; it is **not** a drive or filesystem root path.
- Neither where the source file is located nor the working directory determines relative names. What matters is **the package of the selected class** and **the location of the resource at runtime**.

For example, the class `com.acme.orders.OrderService` and the resource `com/acme/orders/config.properties` belong to the same resource package. The call `OrderService.class.getResource("config.properties")` specifies that exact file; adding a `/` without including the package instead requests a **different** resource at the root.

## 2. Path Name Normalization Algorithm

The `Class.getResource(String)` documentation specifies how a resource name is converted to an absolute name:

1. If `name` begins with `/`, strip the leading `/` and use the remaining part.
2. Otherwise, take the package of the referenced class, replace `.` with `/`, and append `/` followed by the string `name`.

Given `package com.acme.orders;`:

| Call | Absolute Name Looked Up | Explanation |
| --- | --- | --- |
| `getResource("config.properties")` | `com/acme/orders/config.properties` | Package-relative |
| `getResource("/config.properties")` | `config.properties` | Root resource |
| `getResource("/com/acme/orders/config.properties")` | `com/acme/orders/config.properties` | Same name as row 1 |
| `getResource("templates/mail.txt")` | `com/acme/orders/templates/mail.txt` | Package subdirectory |
| `getResource("/templates/mail.txt")` | `templates/mail.txt` | Root subdirectory |
| `getResource("com/acme/orders/config.properties")` | `com/acme/orders/com/acme/orders/config.properties` | Common mistake: duplicated package |

This is **the name requested for lookup**, with no guarantee that it will be found. To know whether it exists, you must examine the classpath/JAR/module, the class loader, and access permissions.

Imagine the classpath root is `out/classes`:

~~~text
out/classes/
├── root.txt
└── com/
    └── acme/
        └── orders/
            ├── OrderService.class
            ├── config.properties
            └── templates/
                └── mail.txt
~~~

The following calls have the expected results assuming only the resources shown in the tree exist:

~~~java
OrderService.class.getResource("config.properties");  // FOUND
OrderService.class.getResource("/com/acme/orders/config.properties"); // FOUND
OrderService.class.getResource("/config.properties"); // NOT_FOUND
OrderService.class.getResource("/root.txt");           // FOUND
OrderService.class.getResource("root.txt");            // NOT_FOUND
OrderService.class.getResource("templates/mail.txt");  // FOUND
~~~

This snippet only illustrates the expressions, not a standalone compilable program; treat them as statements inside a valid method. In a multi-JAR application, a name marked NOT_FOUND might still have a copy in another entry, so you must check the actual runtime classpath.

## 3. Distinguishing Class.getResource from ClassLoader.getResource

Although they share the name `getResource`, **their path rules are not the same**:

| API | Prepends package automatically? | Leading `/` |
| --- | --- | --- |
| `SomeClass.class.getResource(name)` | Yes, when the name does not start with `/` | Means absolute; Java strips that character |
| `SomeClass.class.getResourceAsStream(name)` | Yes, same as `Class.getResource` | Same rule |
| `someLoader.getResource(name)` | No | Pass the name from the root; normally **do not add** a `/` |
| `someLoader.getResourceAsStream(name)` | No | Uses the name from the root |
| `ClassLoader.getSystemResource(name)` | No | Uses the name from the root |

For example, if the actual resource name is `com/acme/orders/config.properties`:

~~~java
URL a = OrderService.class.getResource("config.properties");
URL b = OrderService.class.getResource(
        "/com/acme/orders/config.properties");

ClassLoader loader = OrderService.class.getClassLoader();
URL c = loader.getResource("com/acme/orders/config.properties");
~~~

All three expressions look up the same **logical name** in typical classpath/loader setups, though they are not always guaranteed to return the exact same resource in a named module or custom loader environment. The snippet above assumes `OrderService` and `loader` exist, and loader is not `null`.

**Common mistake:** `loader.getResource("/com/acme/orders/config.properties")`. There is no “strip leading slash” step in the `ClassLoader.getResource` contract; built-in loaders typically fail to find it and return `null`. The portable usage is to omit the `/` before names passed to `ClassLoader`.

**Bootstrap warning:** `String.class.getClassLoader()` typically evaluates to `null`, so chaining `.getResource(...)` will throw a `NullPointerException`. For a Class of a bootstrap type, use the `Class.getResource` API directly or the appropriate API for the desired resource; do not assume a Java loader object is available to call.

## 4. Java 17+ Hands-On Exercise: Package and Root Directories

Create two groups of files: the Java source and three text resources.

~~~text
example/
├── src/
│   └── demo/
│       └── ResourceDemo.java
└── resources/
    ├── global.txt
    └── demo/
        ├── config.properties
        └── assets/
            └── help.txt
~~~

The contents of `resources/demo/config.properties` are `ENV=training`, `resources/global.txt` is `ROOT`, and `resources/demo/assets/help.txt` is `HELP`. Each file contains a single line of plain text.

### File src/demo/ResourceDemo.java

~~~java
package demo;

import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public class ResourceDemo {
    private static void check(String name, URL url) {
        System.out.println(name + " -> "
                + (url != null ? "FOUND" : "NOT_FOUND"));
    }

    public static void main(String[] args) throws Exception {
        check("relative same-package",
                ResourceDemo.class.getResource("config.properties"));
        check("absolute same-package",
                ResourceDemo.class.getResource("/demo/config.properties"));
        check("relative root",
                ResourceDemo.class.getResource("global.txt"));
        check("absolute root",
                ResourceDemo.class.getResource("/global.txt"));
        check("wrong root",
                ResourceDemo.class.getResource("/config.properties"));
        check("relative subfolder",
                ResourceDemo.class.getResource("assets/help.txt"));

        check("loader root-path",
                ResourceDemo.class.getClassLoader()
                        .getResource("demo/config.properties"));
        check("loader leading-slash",
                ResourceDemo.class.getClassLoader()
                        .getResource("/demo/config.properties"));

        try (InputStream in = ResourceDemo.class
                .getResourceAsStream("config.properties")) {
            if (in == null) {
                throw new IllegalStateException("config missing");
            }
            String content = new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
            System.out.println("contents -> " + content);
        }
    }
}
~~~

`ResourceDemo` belongs to package `demo`, so the relative name `config.properties` is converted to `demo/config.properties`. Meanwhile, `/global.txt` specifies a root resource. The example also intentionally uses ClassLoader calls with and without a slash to show how the two APIs differ.

### Compiling and Running on Linux/macOS

From inside the `example` directory:

~~~bash
mkdir -p out/demo/assets
javac -d out src/demo/ResourceDemo.java
cp resources/demo/config.properties out/demo/config.properties
cp resources/demo/assets/help.txt out/demo/assets/help.txt
cp resources/global.txt out/global.txt
java -cp out demo.ResourceDemo
~~~

### Compiling and Running on Windows PowerShell

From inside the `example` directory:

~~~powershell
New-Item -ItemType Directory -Force out\demo\assets | Out-Null
javac -d out src\demo\ResourceDemo.java
Copy-Item resources\demo\config.properties out\demo\config.properties
Copy-Item resources\demo\assets\help.txt out\demo\assets\help.txt
Copy-Item resources\global.txt out\global.txt
java -cp out demo.ResourceDemo
~~~

You must **copy the resources as well**, because `javac -d out ...` does not automatically copy `.properties`/`.txt` files.

Stdout output when running with the resources placed in the correct locations:

~~~text
relative same-package -> FOUND
absolute same-package -> FOUND
relative root -> NOT_FOUND
absolute root -> FOUND
wrong root -> NOT_FOUND
relative subfolder -> FOUND
loader root-path -> FOUND
loader leading-slash -> NOT_FOUND
contents -> ENV=training
~~~

The output above has been verified using `javac`/`java` on an actual JDK. The line `loader leading-slash -> NOT_FOUND` reflects the standard application/system loader used in this experiment; do not treat a custom loader accepting a leading slash as a guaranteed contract.

### Packaging Resources in a JAR

Once the `out` directory contains `demo/ResourceDemo.class` and the resources at their proper paths, run:

~~~bash
jar --create --file resources-demo.jar -C out .
java -cp resources-demo.jar demo.ResourceDemo
~~~

These commands also apply in Windows PowerShell with JDK 17+. **The output is identical** to the directory-based run, and has been verified with a JAR containing both classes and resources. This is why you should read resources using the Java resource API rather than hardcoding filesystem paths.

## 5. Which Class Is a Relative Path Associated With?

Suppose there are two classes in two packages:

~~~java
package alpha;
public class A {}
~~~

~~~java
package beta;
public class B {}
~~~

The two snippets above are **two separate Java files**. The call `A.class.getResource("data.txt")` looks for `alpha/data.txt`, whereas `B.class.getResource("data.txt")` looks for `beta/data.txt`.

Even if the call `A.class.getResource("data.txt")` is written and executed by code inside `beta.B`, the resource base is still the `alpha` package. What matters is **the Class object** preceding `.getResource`, not the package of the caller or the name of the directory where the process is running.

For a nested class, the base package is also that type's package; the nested class name is not automatically appended. For a class in the default package, a relative name has no package prefix. In application code, you should use explicit packages to avoid ambiguity during packaging.

A reliable strategy for libraries is to use `MyLibraryClass.class.getResource("library-config.json")` when the resource resides alongside the library's class, or use a root path such as `"/com/vendor/library-config.json"` when an explicit name is needed to avoid accidentally reading another resource with the same name.

## 6. Reading Data: URL, InputStream, Encoding, and null

`Class.getResource` returns a `URL`, which is suitable when an API accepts a URL or when you want to open it via `url.openStream()`. `Class.getResourceAsStream` returns a stream directly. Both can return `null`; you should not call `url.openStream()` without checking first.

A safe pattern for reading bytes:

~~~java
try (InputStream in = MyClass.class
        .getResourceAsStream("/config/app.json")) {
    if (in == null) {
        throw new IllegalStateException(
                "Resource not found: /config/app.json");
    }
    String json = new String(in.readAllBytes(),
            StandardCharsets.UTF_8);
    // Process json with an appropriate JSON parser.
}
~~~

This is **an illustrative snippet inside a method**, assuming `InputStream` and `StandardCharsets` have been imported and the file exists. `readAllBytes` is suitable for small resources; for large data, read in chunks. *Try-with-resources* closes the stream even if an exception occurs during processing.

Do not assume the `Properties.load(InputStream)` API interprets UTF-8 text the same way `new String(..., UTF_8)` does: it has its own legacy encoding rules. If the resource is a UTF-8 properties file, consider `Properties.load(Reader)` with a reader configured with the appropriate encoding.

**Do not blindly convert a resource URL into a File:**

~~~java
URL url = MyClass.class.getResource("/config/app.json");
File file = new File(url.getFile()); // unreliable when running from a JAR
~~~

This is **a counterexample**, not a recommendation. Inside a JAR, the URL may look like `jar:file:...!/config/app.json`; the entry is not a standalone file on disk. Use a stream or an appropriate archive/URL-handling API, and only extract to a temporary file when another API strictly requires a filesystem path.

## 7. Runtime Location Is Not the Source Directory Location

In a typical Maven/Gradle Java layout:

~~~text
src/
└── main/
    ├── java/com/acme/app/Main.java
    └── resources/
        ├── global.properties
        └── com/acme/app/banner.txt
~~~

Typically, the build tool copies the contents under `src/main/resources` into **the resource output root** and packages them alongside the classes. Then `Main.class.getResource("banner.txt")` looks up `com/acme/app/banner.txt`; `Main.class.getResource("/global.properties")` looks up the root resource. Do not write the name `"src/main/resources/global.properties"`, because that source prefix **is no longer part of the runtime resource name**.

If running directly with `javac` and `java`, building only the source will not automatically guarantee that resources are copied. If it works when run from an IDE but fails in a JAR, inspect your packaging process. You can use `jar tf app.jar` to inspect the actual entries (entry names are separated by `/`).

**Property to remember:** `getResource("config.txt")` does not depend on the current working directory. Changing `user.dir` does not alter the package base; however, if you launch with a **relative** classpath and change the working directory before starting the JVM, classpath entries may point elsewhere.

## 8. JARs, Named Modules, and Custom Loaders: Special Cases

### JAR

Resources are stored in a JAR under entry names such as `demo/config.properties`. The leading `/` rule of `Class.getResource` is still based on **the logical name**; only the physical data-opening mechanism changes from a file to a JAR. If a resource only exists in the source tree and is not packaged into the JAR, the API will not automatically fall back to searching the source tree.

### Named Module (Java 9+)

For a class in a **named module**, `Class.getResource`/`getResourceAsStream` searches within the class's module, and resource access is also subject to module **encapsulation**. In particular, a non-`.class` resource inside a package that is not open to the calling module may be inaccessible even when both the name and file are correct.

A leading `/` **does not bypass package opening rules**. If the normalized path is already correct yet the result is `null`, check `module-info.java` and `opens` rules rather than just trying to add or remove a slash.

`ClassLoader.getResource` with named modules also has its own rules, under which a non-`.class` resource in a named module package generally must reside in a package that is **opened unconditionally** for the public `ClassLoader` API to find it. Therefore, do not assume that `Class.getResource` and `ClassLoader.getResource` are always completely equivalent when working with named modules.

### Custom Class Loader

For a class in an unnamed module, `Class.getResource` uses the defining loader of the selected class object to search for the resource after the name normalization step. A plugin loaded by a custom child loader can see the plugin's own resources, whereas a class from the parent may not see those files.

By default, `ClassLoader.getResource` typically tries the parent first and then calls `findResource` in the current loader, though a custom loader may follow a different policy. If multiple JARs contain resources with the same name, the result also depends on the loader and the search order. This is why you should pick the `Class` object that properly represents the component owning the resource.

The thread context class loader is only relevant if the application or framework **explicitly** uses it; it does not automatically become the base for all `SomeClass.class.getResource` calls.

## 9. Diagnosing Cases Where getResource Returns null

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `MyClass.class.getResource("config.yml") == null` | The file is at the root, but a relative name is searching inside the package. | Use `"/config.yml"` or place the file under the package. |
| `MyClass.class.getResource("/pkg/config.yml") == null` | The resource was not copied to the output/JAR, the name is wrong, or the letter case does not match. | Inspect the output tree and use `jar tf` to verify the entry. |
| Calling `getResource("pkg/config.yml")` in a class in package `pkg` | The package prefix gets duplicated: `pkg/pkg/config.yml`. | Use `"config.yml"` or `"/pkg/config.yml"`. |
| `loader.getResource("/pkg/config.yml") == null` | Misusing the leading `/` rule of `ClassLoader`. | Use `loader.getResource("pkg/config.yml")`. |
| Works from a folder, fails in a JAR | The resource was not packaged or the code forces the URL into a File. | Package the resource and read it via an InputStream. |
| File exists in a named module but still returns null | The resource package is encapsulated. | Check `opens` and the caller module. |
| Fails only when moving from Windows to Linux | Entry name case mismatch or using `\` for resources. | Use the exact name and `/`. |
| Multiple class loaders exist | The class chosen for lookup is defined by a loader that cannot see the resource. | Check `clazz.getClassLoader()` and the actual resource source. |

Do not just use `System.out.println(getResource(...))` and hardcode the absolute URL string into tests. The URL may contain temporary directories, `file:` or `jar:` prefixes, or environment-dependent encodings. Tests should verify **existence** and data **contents**.

## 10. Checklist and Review Questions

Before calling the API, determine: **(1)** the package of the class being used; **(2)** the resource entry name at runtime; **(3)** whether you want a relative lookup or a root lookup; **(4)** whether to use `Class` or `ClassLoader`; **(5)** which class loader/module provides the resource; **(6)** whether the resource resides in a JAR; and **(7)** whether you have checked for null, closed the stream, and specified the encoding.

**Question 1.** Class `org.demo.Widget` needs to read `org/demo/config.xml`. Which two resource names passed to `Widget.class.getResource` are equivalent?

**Answer:** `"config.xml"` and `"/org/demo/config.xml"`: both normalize to `org/demo/config.xml`.

**Question 2.** The file `global.txt` resides at the classpath root. Why does `Widget.class.getResource("global.txt")` usually fail to find it?

**Answer:** It searches for `org/demo/global.txt`. Use `Widget.class.getResource("/global.txt")` to request the root name.

**Question 3.** Should you add a leading slash when switching from `Widget.class.getResource("/org/demo/config.xml")` to `Widget.class.getClassLoader().getResource(...)`?

**Answer:** No. ClassLoader expects `"org/demo/config.xml"` and does not automatically strip a leading slash; you must also handle the case where the class loader is `null`.

**Question 4.** Does switching from a folder to a JAR change the leading slash rule of `Class.getResource`?

**Answer:** No. The logical name remains the same; only how the resource is stored and opened changes, so you typically read it via a stream rather than forcing the URL into a physical file.

## Official Documentation

- [Class.getResource(String), Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getResource(java.lang.String)): relative names and leading slash normalization.
- [Class.getResourceAsStream(String), Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getResourceAsStream(java.lang.String)): lookup rules and returning an InputStream.
- [ClassLoader.getResource(String), Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#getResource(java.lang.String)): root-based slash-separated names and parent delegation.
- [Module.getResourceAsStream(String), Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html#getResourceAsStream(java.lang.String)): resources in named modules and access permissions.
