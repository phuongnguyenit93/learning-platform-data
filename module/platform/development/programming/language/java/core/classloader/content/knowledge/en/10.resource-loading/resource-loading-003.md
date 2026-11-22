# ClassLoader.getResource: Paths Relative to the Resource Root

## 1. The problem: which “resource root” is it?

In Java, **ClassLoader.getResource(String name)** helps locate data packaged with the program, such as configuration files, templates, images, public certificates, or text files. A resource is identified by a **path name separated by /**, for example:

~~~text
config/app.properties
templates/email.html
images/logo.png
com/example/messages.txt
~~~

The key point: **ClassLoader.getResource looks up resource names relative to the class loader's search roots**, without automatically prepending the calling class's package name. Therefore:

~~~java
ClassLoader loader = Example.class.getClassLoader();
URL url = loader.getResource("config/app.properties");
~~~

The name **config/app.properties** is searched at **the root of each classpath entry / resource source managed by the loader**. It does not become **com/example/config/app.properties** by default just because Example is in the com.example package. Nor is it an operating system absolute path, nor is it inferred from the current working directory.

**Lesson objectives:** choose the right resource name, distinguish between the Class and ClassLoader APIs, read streams safely, understand parent delegation and resources in JARs/modules, handle multiple resources with the same name, and diagnose why a resource exists in the project yet still returns null at runtime.

## 2. Which location does a resource name correspond to?

Suppose the built program has the following structure:

~~~text
out/
├── demo/
│   ├── ResourceRootDemo.class
│   └── local.txt
└── config/
    └── app.properties
~~~

When the **out** directory is on the application classpath, we have:

| Resource name passed to ClassLoader | Search location in the out entry | Expected |
| --- | --- | --- |
| **config/app.properties** | out/config/app.properties | Yes |
| **demo/local.txt** | out/demo/local.txt | Yes |
| **local.txt** | out/local.txt | No, if the file only exists under demo/ |
| **demo/config/app.properties** | out/demo/config/app.properties | No |
| **/config/app.properties** | Not a valid relative name in a typical example | Usually not found |
| **config\\app.properties** | Do not use a backslash as a resource separator | Not the standard notation |

The root here is **out** because it is a classpath entry. If the classpath is replaced by a JAR, the corresponding root is **the root of the entries inside the JAR**. If a custom loader fetches resources from another source, the “root” is defined by that loader.

**You do not need to, and should not, add a /** at the beginning of the ClassLoader.getResource argument. A leading slash only has special meaning for **Class.getResource**; it is not a rule that ClassLoader.getResource strips by default.

### 2.1 / is the standard separator for resource names

Even when the application runs on Windows, resource names are still written as:

~~~java
loader.getResource("config/app.properties");   // Correct
loader.getResource("demo/local.txt");          // Correct
~~~

Do not write them in Windows file path format such as:

~~~java
loader.getResource("C:\\project\\config\\app.properties"); // Not a suitable resource name
loader.getResource("config\\app.properties");                  // Wrong slash convention
~~~

The **name** argument is the logical name of the resource in the loader's lookup space. It is not a filesystem path and cannot necessarily be converted into a **java.nio.file.Path**.

### 2.2 A classpath can have multiple roots

For example, the command:

~~~bash
java -cp out:assets:lib/util.jar demo.Main
~~~

on Linux/macOS; on Windows, the classpath separator is **;**, not **:**:

~~~powershell
java -cp "out;assets;lib/util.jar" demo.Main
~~~

The loader can search for a resource name in the appropriate sources **out**, **assets**, **util.jar**, and those provided by its parent. Do not tie a resource name to a single filesystem directory.

**Note:** There are many types of class loaders, module paths, and custom environments; the classpath example above describes the typical behavior of the application loader with the unnamed module, not a guarantee that every loader reads the same list of directories.

## 3. What does the ClassLoader.getResource API return?

Signature:

~~~java
public URL getResource(String name);
~~~

On success, the API returns a **java.net.URL** pointing to a location that can be used to read the resource. When it cannot be found or access is not permitted (according to the applicable rules), the method returns **null**. Passing **null** as name may throw **NullPointerException** according to the API.

Safe usage:

~~~java
ClassLoader loader = MyClass.class.getClassLoader();
URL resource = loader.getResource("config/app.properties");

if (resource == null) {
    throw new IllegalStateException("Missing config/app.properties");
}

try (InputStream in = resource.openStream()) {
    // Read data...
}
~~~

This is a snippet to place in an application that has MyClass, imports, and the data-reading code; it is not yet a standalone program. Section 6 has an example with complete files, run commands, and stdout.

**URL is not Path:** when running from a directory, the URL may start with **file:**; when packaged into a JAR, the URL usually has the form **jar:file:...!/config/app.properties**; JDK system resources may have the **jrt:** form. Therefore, you should not take **url.getFile()** and convert it into a **File** to read across all environments.

## 4. Comparing ClassLoader.getResource and Class.getResource

This is the biggest source of confusion.

### 4.1 ClassLoader rules

With ClassLoader:

~~~java
ClassLoader loader = Demo.class.getClassLoader();

URL a = loader.getResource("config/app.properties");
URL b = loader.getResource("demo/local.txt");
~~~

The name passed in is interpreted as a **path name from the resource search root**. There is no rule that automatically prepends the **demo** package name to the resource name. Do not put a leading slash on the string.

### 4.2 Class rules

With Class:

~~~java
URL a = Demo.class.getResource("local.txt");
URL b = Demo.class.getResource("/config/app.properties");
URL c = Demo.class.getResource("/demo/local.txt");
~~~

If **Demo** belongs to the **demo** package:

- **getResource("local.txt")**: the name does not start with a slash, so **Class** builds the absolute name **demo/local.txt**.
- **getResource("/config/app.properties")**: the name starts with a slash, so **Class** strips that slash and looks up **config/app.properties** from the root.
- **getResource("/demo/local.txt")**: strips the leading slash and looks up **demo/local.txt** from the root.

Thus, **Class.getResource("/demo/local.txt")** and **ClassLoader.getResource("demo/local.txt")** can find the same resource in a simple classpath program. However, Class and ClassLoader are not completely identical APIs: in a **named module**, Class.getResource is tied to the Class's module and checks encapsulation according to the rules for the caller.

### 4.3 Comparison table

Suppose **demo/LocalDemo.class**, **demo/local.txt**, and **config/app.properties** are all at the same classpath root:

| Expression | Name looked up in the example | Result |
| --- | --- | --- |
| **loader.getResource("demo/local.txt")** | demo/local.txt | Found |
| **loader.getResource("local.txt")** | local.txt | Not found |
| **loader.getResource("/demo/local.txt")** | A name with a leading slash is not automatically stripped by ClassLoader | Not found in a standard classpath loader |
| **LocalDemo.class.getResource("local.txt")** | demo/local.txt | Found |
| **LocalDemo.class.getResource("/demo/local.txt")** | demo/local.txt | Found |
| **LocalDemo.class.getResource("config/app.properties")** | demo/config/app.properties | Not found |
| **LocalDemo.class.getResource("/config/app.properties")** | config/app.properties | Found |

**Easy-to-remember rule:**

~~~text
ClassLoader.getResource("x/y.txt")
            |
            └─ x/y.txt from the loader root

Class.getResource("y.txt")
            |
            └─ package/of/Class/y.txt

Class.getResource("/x/y.txt")
            |
            └─ x/y.txt from the root (Class strips the leading /)
~~~

Do not use another API variant to “fix” an incorrect path; determine which root entry the resource is packaged in and which API fulfills your intent.

## 5. Paths from the root, not the open project directory

Common question: “I have a file in the **src/main/resources** directory, why doesn't getResource accept the string **src/main/resources/config/app.properties**?”

In a typical Maven/Gradle application, files under **src/main/resources** are **copied to the resource output**, and then the output directory is placed on the runtime classpath or packaged into a JAR:

~~~text
project/
├── src/main/java/demo/App.java
├── src/main/resources/
│   └── config/app.properties
└── target/classes/                 (Maven example)
    ├── demo/App.class
    └── config/app.properties
~~~

The resource name at runtime is normally:

~~~java
loader.getResource("config/app.properties");
~~~

**Not:**

~~~java
loader.getResource("src/main/resources/config/app.properties");
~~~

because the source name **src/main/resources** is not part of the runtime resource structure of an artifact built under this convention.

Similarly with Gradle, resource-processing tasks typically produce resource outputs and package them into the classpath/JAR. You need to inspect the **actual** artifact if the build has been configured differently from the default.

### 5.1 CWD can only have an indirect effect

If you run:

~~~bash
java -cp out:assets demo.ResourceRootDemo
~~~

then **out** and **assets** are relative classpath entries. They are interpreted relative to where the command is run when starting the JVM. **However, the resource name** is still **config/app.properties**, not an arbitrary relative path to the working directory.

If changing the working directory causes the paths in **-cp** to no longer be valid, the resource may be missing. In that case, the cause lies in the **configured classpath root**, not in ClassLoader.getResource searching using CWD on its own.

## 6. Runnable example 1: checking root, package, and slashes

Create the directory structure:

~~~text
project/
├── src/
│   └── demo/
│       └── ResourceRootDemo.java
└── assets/
    ├── config/
    │   └── app.properties
    └── demo/
        └── local.txt
~~~

**assets/config/app.properties**:

~~~properties
mode=demo
~~~

**assets/demo/local.txt**:

~~~text
welcome-from-package
~~~

**src/demo/ResourceRootDemo.java**:

~~~java
package demo;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public class ResourceRootDemo {
    private static String readText(InputStream source) throws Exception {
        if (source == null) {
            return "<missing>";
        }

        try (InputStream in = source) {
            return new String(
                    in.readAllBytes(),
                    StandardCharsets.UTF_8
            ).strip();
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = ResourceRootDemo.class.getClassLoader();

        System.out.println("loader root = "
                + (loader.getResource("config/app.properties") != null));

        System.out.println("loader leading slash = "
                + (loader.getResource("/config/app.properties") != null));

        System.out.println("class relative = "
                + (ResourceRootDemo.class.getResource("local.txt") != null));

        System.out.println("class absolute = "
                + (ResourceRootDemo.class.getResource("/config/app.properties")
                        != null));

        System.out.println("class mistaken relative = "
                + (ResourceRootDemo.class.getResource("config/app.properties")
                        != null));

        Properties properties = new Properties();
        try (InputStream in = loader.getResourceAsStream(
                "config/app.properties")) {
            if (in == null) {
                throw new IllegalStateException("Missing properties");
            }
            properties.load(in);
        }

        System.out.println("mode = " + properties.getProperty("mode"));
        System.out.println("local = "
                + readText(loader.getResourceAsStream("demo/local.txt")));
    }
}
~~~

From the **project** directory, compile:

~~~bash
javac -d out src/demo/ResourceRootDemo.java
~~~

Run on Linux/macOS:

~~~bash
java -cp out:assets demo.ResourceRootDemo
~~~

Or on Windows PowerShell:

~~~powershell
java -cp "out;assets" demo.ResourceRootDemo
~~~

**Expected stdout** with the application classpath as shown above, the resource files matching the example, and no resource with the same name in a parent loader:

~~~text
loader root = true
loader leading slash = false
class relative = true
class absolute = true
class mistaken relative = false
mode = demo
local = welcome-from-package
~~~

### 6.1 Why does it produce this result?

- **loader root = true**: the file **assets/config/app.properties** is under the **assets** root, and the application loader recognizes the name **config/app.properties**.
- **loader leading slash = false**: **ClassLoader.getResource** does not convert the string **/config/app.properties** to root-relative like Class.getResource does; a standard classpath loader does not find this name with a leading slash.
- **class relative = true**: ResourceRootDemo belongs to the **demo** package, so **Class.getResource("local.txt")** looks up **demo/local.txt**.
- **class absolute = true**: Class.getResource strips the leading slash and looks up **config/app.properties**.
- **class mistaken relative = false**: Class.getResource does not ignore the package when the name has no slash; it looks up **demo/config/app.properties**, and that path does not exist.
- **mode** and **local** prove that resources are **read via InputStream**, without needing to know whether they are OS files or archive entries.

### 6.2 How to check if stdout differs

If all values are false, check that you are in the right working directory, using the OS's classpath separator, that both resource files were created properly, and that the actual classpath includes the **assets** entry. If only one value changes unexpectedly, check whether there is a **resource with the same name** in a parent loader/another JAR or whether a custom loader behaves differently from the default rules.

**Important:** the example uses the API of an unnamed module on a standard classpath. In named modules, **module encapsulation** must also be considered as discussed in section 10.

## 7. Using getResourceAsStream: reading data without needing the URL

In many cases you need the **content**, not the URL. ClassLoader provides:

~~~java
public InputStream getResourceAsStream(String name);
~~~

A short example inside a method that has **loader** and exception handling:

~~~java
try (InputStream in = loader.getResourceAsStream(
        "config/app.properties")) {
    if (in == null) {
        throw new IllegalStateException(
                "Resource missing: config/app.properties"
        );
    }

    Properties props = new Properties();
    props.load(in);
}
~~~

Rules:

- **Null** means the resource could not be found or is not provided under the applicable access policy.
- **The InputStream must be closed** after reading; use try-with-resources.
- **Properties.load(InputStream)** by specification uses ISO-8859-1 encoding and properties-format escaping rules. If the file requires non-ASCII UTF-8, consider **Properties.load(Reader)** with **InputStreamReader(..., UTF_8)** or an appropriate parser API.
- For regular UTF-8 text files, use InputStreamReader / new String(bytes, UTF_8) instead of relying on an implicit default charset.
- Do not call **available()** to infer the total length of the resource; available only indicates the number of bytes that can be read immediately without blocking.
- Do not reopen the stream multiple times if you can read it in one pass and cache the content appropriately.

### 7.1 Do not force a URL into a File

The following snippet may work only when the resource actually resides on the filesystem:

~~~java
// DO NOT use generically for file/JAR/module:
File file = new File(url.getFile());
~~~

When packaged into a JAR, the URL may have the form:

~~~text
jar:file:/path/to/app.jar!/config/app.properties
~~~

There is no separate OS file at **/path/to/app.jar!/config/app.properties**. This is an entry inside an archive. It is best to read using **URL.openStream()** or **ClassLoader.getResourceAsStream()**; convert to **Path** only if the protocol and filesystem provider actually support it, and you manage the corresponding filesystem lifecycle.

## 8. Packaging as a JAR does not change the resource name

Using the same example from section 6, from **project** after compiling:

~~~bash
jar --create --file demo-resources.jar -C out . -C assets .
jar --list --file demo-resources.jar
~~~

The archive will contain entries such as:

~~~text
demo/ResourceRootDemo.class
demo/local.txt
config/app.properties
~~~

Metadata entries such as **META-INF/MANIFEST.MF** may also appear, so the list above only shows the entries of interest.

Running the JAR via the classpath on Linux/macOS or Windows uses a single entry:

~~~bash
java -cp demo-resources.jar demo.ResourceRootDemo
~~~

The expected stdout is **the same as in section 6** because the resource names remain **config/app.properties** and **demo/local.txt**. The loader simply changes where it reads bytes from: from the assets directory to the JAR entries.

**Takeaway:** do not prepend the JAR file name to the **getResource** argument:

~~~java
// Wrong meaning when intending to read the entry:
loader.getResource("demo-resources.jar/config/app.properties");

// Correct:
loader.getResource("config/app.properties");
~~~

Changing the packaging format does not require you to change the resource name if **the resource's path inside the root** stays the same.

### 8.1 Limitations of the packaging example

If the JAR is modularized and placed on the module path, the lookup rules for non-class resources also depend on the named module and package openness. The example above uses a plain classpath, without **module-info.java**.

## 9. Parent delegation: where does ClassLoader.getResource search first?

According to the default implementation in the ClassLoader API:

1. Search for the resource through the **parent loader**; if there is no parent, search on the resource lookup path of the appropriate bootstrap loader.
2. If the parent does not find it, call **findResource(name)** on the current loader.
3. Return the first URL found, or null if no valid resource exists.

~~~text
child.getResource("config/app.properties")
             │
             ▼
   parent.getResource(name)
             │
       ┌─────┴──────┐
       │ found URL? │
       └─────┬──────┘
       true  │ false
         │   ▼
         │ child.findResource(name)
         │   │
         └───┤
             ▼
        return URL / null
~~~

**Important:** A file inside a child loader's JAR is not guaranteed to be picked if the parent also has a resource **with the same name**; the parent can win under default delegation. Do not assume that whenever resources share the same name, the one from the entry closest to the calling class is always selected.

### 9.1 findResource and getResource are different

- **getResource(name)** is the loader's public entry point, handling delegation according to the default contract.
- **findResource(name)** is a protected hook overridden by subclasses to locate a resource in the sources they manage.
- **findResources(name)** is a protected hook for locating multiple resources with the same name in the loader's sources.
- Custom loader implementations may override getResource and choose a different policy; in that case, you need to inspect the actual implementation.

A custom loader that simply wants to add a regular resource source should override **findResource** (and **findResources** if it supports multiple resources), while keeping default delegation when there is no clear reason to change it.

### 9.2 Resource lookup does not mean class loading

**loader.getResource("demo/Widget.class")** may be able to locate the class-file bytes, but finding the resource **does not by itself create a java.lang.Class** for Widget. **ClassLoader.loadClass("demo.Widget")** is a semantically different process of finding/defining a runtime type.

Conversely, a custom loader might provide a Class via in-memory generated bytecode without making a corresponding stream discoverable via **getResource("demo/Widget.class")**. Do not use getResource as the sole test to confirm that a class can be loaded.

## 10. Named modules: the resource exists yet is still not found

Since Java 9, named modules have an **encapsulation** mechanism for many non-class resources. For **ClassLoader.getResource(name)** and **ClassLoader.getResources(name)**, the Javadoc specifies:

- Resources in named modules are subject to encapsulation rules as specified by **Module.getResourceAsStream**.
- Except when the name ends with **.class**, a resource in a named module's package is generally only found by the **ClassLoader.getResource** API when that package is **opened unconditionally**, even if the caller is in the same module.
- Otherwise, **getResource** may return null even though the resource is actually packaged in the module.
- If multiple modules defined by the same loader contain resources with the same name, the search order across modules may be unspecified.

This is a difference from the simple classpath example.

### 10.1 Illustrative module-info.java example

Suppose a named module **sample.resources** contains a resource in package **sample.internal**, and you want **ClassLoader.getResource("sample/internal/settings.json")** to be able to locate it through the loader from outside. The module declaration can be written as:

~~~java
module sample.resources {
    opens sample.internal;
}
~~~

**opens sample.internal;** opens the package unconditionally. By contrast, **opens sample.internal to another.module;** only opens it conditionally to the named module, which does not satisfy ClassLoader.getResource's rule that the package be opened **unconditionally** for non-class resources.

You should not open every package just so arbitrary code can read resources; module encapsulation exists for API design and access-control reasons. When a resource belongs to a specific module and the caller has appropriate access permissions, you can consider **Class.getResourceAsStream** or **Module.getResourceAsStream**, which have module-aware semantics and corresponding caller rules.

### 10.2 Class.getResource in a named module also has its own rules

For a Class belonging to a **named module**, **Class.getResource** searches for the resource within the Class's module, rather than simply prepending the package and relying on a general classpath search. It also applies encapsulation based on the caller's access rights. Therefore:

~~~java
SomeClass.class.getResource("/sample/internal/settings.json");
~~~

is not guaranteed to be an equivalent transformation to:

~~~java
SomeClass.class.getClassLoader()
        .getResource("sample/internal/settings.json");
~~~

in every named-module application. Avoid mechanically applying the slash rules once module boundaries are present.

## 11. getResources: what if multiple copies share the same name?

A loader also has the API:

~~~java
public Enumeration<URL> getResources(String name) throws IOException;
~~~

It searches for **multiple URLs** with the same name. The default implementation searches the parent first and then appends resources from **findResources(name)** of the current loader. This is a useful tool when detecting a resource shadowed by another JAR.

Java 9+ also provides:

~~~java
public Stream<URL> resources(String name);
~~~

The stream is lazy and may wrap I/O errors into an **UncheckedIOException** during traversal; if you want code that handles checked exceptions explicitly, **getResources** remains a clear choice.

### 11.1 Runnable example 2: two classpath roots with the same name

Create:

~~~text
project/
├── src/demo/ResourceOrderDemo.java
├── assets-a/demo/banner.txt
└── assets-b/demo/banner.txt
~~~

**assets-a/demo/banner.txt**:

~~~text
blue
~~~

**assets-b/demo/banner.txt**:

~~~text
green
~~~

**src/demo/ResourceOrderDemo.java**:

~~~java
package demo;

import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Enumeration;

public class ResourceOrderDemo {
    static String read(URL url) throws Exception {
        if (url == null) {
            return "<missing>";
        }

        try (InputStream in = url.openStream()) {
            return new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader =
                ResourceOrderDemo.class.getClassLoader();
        String name = "demo/banner.txt";

        System.out.println("first = " + read(loader.getResource(name)));

        Enumeration<URL> matches = loader.getResources(name);
        int count = 0;

        while (matches.hasMoreElements()) {
            count++;
            System.out.println("resource " + count + " = "
                    + read(matches.nextElement()));
        }

        System.out.println("count = " + count);
    }
}
~~~

Compile:

~~~bash
javac -d out src/demo/ResourceOrderDemo.java
~~~

Linux/macOS:

~~~bash
java -cp out:assets-a:assets-b demo.ResourceOrderDemo
~~~

Windows PowerShell:

~~~powershell
java -cp "out;assets-a;assets-b" demo.ResourceOrderDemo
~~~

With a standard application classpath in this command and no duplicate provided by the parent, expected stdout:

~~~text
first = blue
resource 1 = blue
resource 2 = green
count = 2
~~~

If you reverse the order of the classpath roots:

~~~bash
java -cp out:assets-b:assets-a demo.ResourceOrderDemo
~~~

on Linux/macOS, or on Windows:

~~~powershell
java -cp "out;assets-b;assets-a" demo.ResourceOrderDemo
~~~

then the first selected resource is usually **green**, and the enumeration order changes accordingly, provided the loader searches the classpath entries in the configured order of the example.

**Limitation:** Do not generalize the order above to **every custom loader** or to cases where **multiple named modules** contain the same resource. According to the Javadoc, the search order across modules in a loader can be unspecified. When a project truly requires explicit priority configuration, design the sources and precedence rules explicitly rather than relying accidentally on duplicate resource names.

### 11.2 Using getResources to diagnose duplicate files

If an application uses multiple JARs and loads the wrong **META-INF/services/...**, **config/defaults.properties**, or template, print the URLs returned by getResources. Do not print sensitive contents directly; listing the URLs is enough to see which sources contain the resource. The result may be a **jar:** URL or another custom source.

## 12. Context class loader, system loader, and a Class's loader

Java has several ways to obtain a loader; do not confuse them:

| Way to obtain the loader | Typically used for |
| --- | --- |
| **MyClass.class.getClassLoader()** | Defining loader of MyClass; suitable when you want resources tied to the component containing MyClass. |
| **ClassLoader.getSystemClassLoader()** | System/application loader of the JVM process. |
| **ClassLoader.getSystemResource(name)** | Resource lookup via the system loader. |
| **Thread.currentThread().getContextClassLoader()** | Loader assigned to the thread to support certain frameworks, service providers, and runtime containers. |

A library running in an application server might be defined by a parent loader yet need to locate a plugin's resource via the **thread context class loader**. In that case, the resource may not be visible through the library class's own loader.

Illustrative example placed inside a method (not a standalone program):

~~~java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

ClassLoader defining =
        SomeLibrary.class.getClassLoader();

URL fromContext = context == null ? null
        : context.getResource("plugin/settings.properties");

URL fromDefining = defining == null ? null
        : defining.getResource("plugin/settings.properties");
~~~

The two URLs may differ, or one may be null. Do not just keep swapping loaders until it “stops returning null”; clarify **which component the resource belongs to, who owns the resource, and which loader the runtime is using**.

## 13. Diagnosing when getResource returns null

If you observe:

~~~java
URL url = loader.getResource("config/app.properties");
// url == null
~~~

check systematically.

### 13.1 Is the resource name correct from the root?

Check for extra or missing prefix mistakes:

- Wrong for ClassLoader: **/config/app.properties** (leading slash).
- Wrong when the file has already been copied to the root: **src/main/resources/config/app.properties**.
- Wrong when the file actually sits inside a package: **local.txt** instead of **demo/local.txt**.
- Wrong separator: **config\\app.properties** instead of **config/app.properties**.

### 13.2 Was the resource copied into the build output/JAR?

Existing in the Git repository **does not prove** it was packaged into the running artifact. Inspect the output directory or the entries inside the JAR:

~~~bash
jar --list --file demo-resources.jar
~~~

The line **config/app.properties** must appear at the exact root entry. If using Maven/Gradle, check resource sources, include/exclude filters, and build output.

### 13.3 Which classpath is the application running with?

Distinguish between:

- The classpath when compiling with **javac**.
- The classpath when launching with **java**.
- The module path if using named modules.
- The classpath in the IDE/test runner/container.

Successfully compiling the code **does not guarantee** that the runtime launcher brings along all resource files, because the compiler does not necessarily read those resources.

### 13.4 Are you querying the right ClassLoader?

Compare:

~~~java
System.out.println(MyClass.class.getClassLoader());
System.out.println(ClassLoader.getSystemClassLoader());
System.out.println(Thread.currentThread().getContextClassLoader());
~~~

This is a snippet placed inside a method with a real MyClass. Different loader results may be valid; check parent delegation and the plugin's scope.

### 13.5 Is named module encapsulation involved?

Especially for non-.class resources in packages of named modules: ClassLoader.getResource may fail to find them if the package is not **opened unconditionally**, even though the file exists. Check **module-info.java**, the resource's package, where the module is loaded, and the caller API being used.

### 13.6 Is a duplicate-named resource shadowing it?

If getResource returns a URL but the content is the “wrong version”, use **getResources(name)** to list all discovered copies and verify the parent/classpath/JAR order. Do not assume there is only one copy of a given filename on the classpath.

### 13.7 Is it actually an I/O or URL error?

- **getResource == null**: the resource is missing, not visible, or not permitted per the API.
- **getResource returns a URL but url.openStream() fails**: the resource may have become inaccessible, the archive may be closed, or there may be a permission or I/O issue.
- **getResourceAsStream returns null**: do not treat it as an empty stream; it indicates the resource could not be found or access is not permitted.
- **name == null**: the API throws NullPointerException, not “resource absent”.

Separate the name lookup step from opening and reading the stream to see where the failure occurs.

## 14. Resource lookup and security

Resources may contain sensitive configuration data or valuable templates in a system, yet **ClassLoader.getResource is not a security API for hiding secrets**. If you put a secret into a JAR, anyone who has the archive can typically read its contents. Do not package unprotected credentials or private keys as public resources.

If the resource name comes from external input, apply an allowlist and appropriate name validation. Do not let users pass arbitrary **../** paths and rely on the loader to block all out-of-scope access. Responsibility for protecting paths, source names, and access permissions also depends on the specific custom loader implementation and URL protocol.

If a resource is large, consider streaming instead of reading all bytes with **readAllBytes()**. Examples using readAllBytes are only meant to keep learning code short for small resources. Close the InputStream properly using try-with-resources.

## 15. Practical scenarios and how to choose an API

| Need | Approach |
| --- | --- |
| Fixed resource at a component's root on the classpath | **MyClass.class.getClassLoader().getResource("config/app.properties")** if the loader is not null. |
| Resource located alongside a class in the same package | **MyClass.class.getResource("local.txt")**. |
| Resource located at the root but called via Class | **MyClass.class.getResource("/config/app.properties")**. |
| Only need to read bytes/text | **getResourceAsStream** + try-with-resources. |
| Need a URL for another API to open the resource | **getResource**, then check for null and inspect the protocol; do not assume it is always a File. |
| Suspect multiple duplicate-named copies of a resource | **getResources** / **resources**. |
| Plugin resources not belonging to the library's loader | Check the plugin loader or thread context loader per the framework contract. |
| Named module with encapsulated resources | Consider **Module.getResourceAsStream** and module openness rules, instead of just changing slashes. |
| Resource located on the filesystem outside the artifact | Use **Path/Files** with an explicitly configured path; do not conflate this with ClassLoader.getResource. |

**Distinguishing the two data sources:**

~~~text
Filesystem external configuration:
    Path.of("/etc/myapp/config.yml")
    Files.newInputStream(path)

Classpath/module resource:
    loader.getResourceAsStream("config/defaults.yml")
~~~

These are two different distribution models. Packaged resources are typically suited for defaults or read-only data; external files are suited for deployment configuration that can change independently.

## 16. Self-check questions

**Question 1.** An app has class **com.example.Tool** and resource **com/example/help.txt**. Does calling **Tool.class.getClassLoader().getResource("help.txt")** automatically search under package com.example?

**Answer:** No. ClassLoader.getResource takes a name from the root; use **com/example/help.txt**, or **Tool.class.getResource("help.txt")** if you want to search relative to the package.

**Question 2.** When using ClassLoader, does the string **/config/app.properties** mean “search from the root” like in Class.getResource?

**Answer:** No. ClassLoader does not apply the leading-slash removal rule. Use **config/app.properties**. Only Class.getResource uses a leading slash to denote the root.

**Question 3.** Why does the resource exist at **src/main/resources/config/app.properties**, yet the code looks up **config/app.properties**?

**Answer:** A standard build copies the contents of the resources folder into the root of the resource output or JAR. The name src/main/resources is not part of the runtime resource name.

**Question 4.** Does switching from running with a classpath directory to running a JAR force you to change the getResource argument?

**Answer:** No, if the entry path inside the root stays the same. The API returns a URL with a different scheme, but the resource name stays unchanged.

**Question 5.** Why does calling **new File(url.getFile())** fail to read a resource inside a JAR?

**Answer:** A JAR entry does not exist as a standalone file on the filesystem. Use **URL.openStream** or **getResourceAsStream** instead.

**Question 6.** A child loader has config.txt, and its parent also has config.txt. With the default ClassLoader implementation, which copy is usually found first?

**Answer:** The parent first, and then the child loader calls findResource if it has not been found.

**Question 7.** Can a resource in a named module exist while ClassLoader.getResource returns null?

**Answer:** Yes. Non-.class resources in a named module's package can be hidden by module encapsulation if the package is not opened unconditionally.

**Question 8.** ClassLoader.getResource returns a URL, but the content is the wrong copy. Which API helps find all copies with the same name?

**Answer:** **getResources(name)** (or **resources(name)** in Java 9+), and then inspect each source.

**Question 9.** Can you confirm that **loadClass("com.example.Tool")** will succeed solely because getResource("com/example/Tool.class") returns a URL?

**Answer:** No. Finding a class-file resource and JVM class loading are two semantically different mechanisms; custom loaders and module rules may handle them differently.

**Question 10.** Does ClassLoader.getResource search for an arbitrary file relative to the CWD?

**Answer:** No. It searches the loader's resource roots; the CWD can only indirectly affect how relative classpath entries are interpreted when the program starts.

## 17. Key takeaways

**Most important practical formula:**

~~~text
ClassLoader.getResource("dir/file.txt")
     → dir/file.txt from the loader's resource search root

SomeClass.class.getResource("file.txt")
     → package/of/SomeClass/file.txt

SomeClass.class.getResource("/dir/file.txt")
     → dir/file.txt from the root (Class strips the leading slash)
~~~

- Resource names use **/**, not OS paths.
- A **classpath root** can be a directory, a JAR, or a source provided by a custom loader.
- URLs may use **file:**, **jar:**, **jrt:**, or another scheme; prefer **openStream** instead of assuming a File.
- **getResourceAsStream** is suitable for reading a resource; always check for null and close the stream.
- Parent-first delegation can determine which URL is returned; **getResources** helps investigate duplicate names.
- In **named modules**, resource encapsulation can affect lookup.
- Resources on the filesystem outside the artifact are a separate matter; use **Files/Path** when appropriate.
- Finding a resource does not prove the corresponding class has been loaded or initialized by the JVM.

### Reference documentation

- **ClassLoader Java SE 21 API** – getResource, getResources, findResource, getResourceAsStream: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
- **Class Java SE 21 API** – getResource and relative/absolute name rules: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- **Module Java SE 21 API** – getResourceAsStream and module encapsulation: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
- **java Command Java SE 21** – -classpath and module/class loading: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
