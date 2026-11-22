# Search Order and Duplicate Class Names Across Multiple JARs

## 1. The Problem: Which Class Does the JVM Choose When Multiple JARs Contain the Same Name?

Suppose both `a.jar` and `b.jar` contain the bytecode file:

~~~text
demo/dupe/Message.class
~~~

The source code in JAR A might return the string `"A"`, while JAR B returns `"B"`. If a ClassLoader is configured to see **both JARs**, which class will be used when the program requests `demo.dupe.Message`?

The answer depends on the **loader receiving the request**, the **delegation relationship to the parent**, and the **search order among the sources managed by that loader**. With a standard `URLClassLoader`, the common mechanism is:

1. Check whether the loader has already loaded that class.
2. **Parent-first:** ask the parent loader first.
3. If the parent does not find it, search the child loader's URLs in the configured order.
4. Once a class has been defined for that name in the loader, subsequent requests return that corresponding class; changing the order of the URL list **does not automatically replace an already loaded class**.

"Duplicate class names" can lead to two different outcomes that must be distinguished:

- **A single loader sees two JARs:** normally only the class in the **first-found** source becomes the class defined by that loader; the version in the later source is shadowed for that name.
- **Two separate loaders each define a class with the same name:** the JVM can have **two distinct runtime classes** existing simultaneously even though their binary names are identical. Runtime identity is based on the binary name **and the defining loader**, not on the JAR name.

This is the root cause of many "works on one machine, fails on another" bugs, library version conflicts, `NoSuchMethodError`, or `ClassCastException` when an application uses plugins, an application server, or a classpath containing overlapping JAR versions.

## 2. Search Order Is *Per-Loader*

The parent-first model of `ClassLoader.loadClass` is typically expressed as:

~~~text
Child.loadClass("demo.dupe.Message")
    │
    ├─ Already loaded in child?
    │      └─ Yes → return known Class<?>
    │
    ├─ Ask parent to find class
    │      └─ Parent found → return parent's class
    │
    └─ Parent did not find → child.findClass(...)
           ├─ First URL with valid bytecode → use that class
           └─ Continue to next URL if not yet found
~~~

This is a conceptual diagram for a **parent-first compliant ClassLoader**, not a guarantee for every custom loader. A child-first loader may reverse the lookup order. The Java Platform Module System (JPMS) also applies module resolution/readability and cannot be fully expressed by JAR order on the classpath.

In a `URLClassLoader` created from a URL array, the URL order determines the **priority for finding classes and resources in that loader's own search path**, when the parent has no result and there is no other special configuration such as a manifest `Class-Path` extending the search path. Therefore:

~~~java
// Illustrative code (aUrl, bUrl, and parent must be created).
URLClassLoader ab = new URLClassLoader(new URL[] {aUrl, bUrl}, parent);
URLClassLoader ba = new URLClassLoader(new URL[] {bUrl, aUrl}, parent);
~~~

If the parent does not find `demo.dupe.Message`:

- `ab` normally selects the class from `a.jar`.
- `ba` normally selects the class from `b.jar`.
- The two classes are defined by **two independent loaders**, so they are not the same runtime class.

If the parent **already** finds `demo.dupe.Message`, both `ab` and `ba` under parent-first will normally receive **the parent's class**. In that case, changing the URL order in the child cannot alter the result.

## 3. Classpath at Java Launch and Search Paths

In standard **classpath/unnamed modules** mode:

~~~bash
# Linux/macOS: the : character separates entries.
java -cp "a.jar:b.jar:classes" demo.app.Main

# Windows: the ; character separates entries.
java -cp "a.jar;b.jar;classes" demo.app.Main
~~~

When **the same application loader** searches for a class across classpath entries, entry position typically establishes priority order: earlier entries are examined first when the class is not yet loaded. If you use the wildcard `lib/*`, **the order in which JARs are expanded by the launcher is not specified to be stable**: do not design programs relying on "alphabetically sorted JAR names" or directory listing order.

Note:

- Classpath order does not override **parent delegation**. A class provided by the parent wins over URLs located in a child under the parent-first model, regardless of file name.
- A classpath can contain both directories and JARs. A `classes/` directory containing a class with the same FQCN can also shadow a JAR listed after it.
- A `MANIFEST.MF` file with a `Class-Path` attribute can add entries to the loader/launcher search path through its own mechanism, so inspecting only the `-cp` list is sometimes insufficient to explain the result.
- On Java 9+, the system class loader is not guaranteed to be a `URLClassLoader`; do not blindly cast it to modify the URLs of the running system loader.
- `--module-path` is not an equivalent classpath list with a "first JAR wins" rule. Named modules have their own resolution, package ownership, and class loading mechanisms.
- The manifest `Class-Path` attribute does not behave identically to the `-cp` option in all circumstances: it is only meaningful within the scope of supported URL/JAR types and rules.

## 4. Java 17+ Experiment: Two JARs with Duplicate Class Names and a Parent JAR

We create three JARs with the **same binary name** `demo.dupe.Message` but different results, along with a host that **does not directly reference this class at compile time**. This allows the host to actively inspect the selected type via reflection.

### 4.1. Project Structure

~~~text
jar-order-demo/
├── host-src/
│   └── demo/host/JarOrderDemo.java
├── a-src/
│   └── demo/dupe/Message.java
├── b-src/
│   └── demo/dupe/Message.java
├── parent-src/
│   └── demo/dupe/Message.java
├── a-resources/
│   └── label.txt
├── b-resources/
│   └── label.txt
└── parent-resources/
    └── label.txt
~~~

The three `Message.java` files in **three different source directories** all declare `package demo.dupe;` and `public class Message`. They are compiled **separately into three output directories**, then packaged into three independent JARs. Do not compile the three sources with the same FQCN together in a single `javac` command, because that leads to duplicate class definitions within the same compilation.

### 4.2. Class in JAR A

File **`a-src/demo/dupe/Message.java`**:

~~~java
package demo.dupe;

public final class Message {
    public static String origin() {
        return "A";
    }
}
~~~

File **`a-resources/label.txt`** contains exactly:

~~~text
A
~~~

### 4.3. Class in JAR B

File **`b-src/demo/dupe/Message.java`**:

~~~java
package demo.dupe;

public final class Message {
    public static String origin() {
        return "B";
    }
}
~~~

File **`b-resources/label.txt`**:

~~~text
B
~~~

### 4.4. Corresponding Class in the Parent's JAR

File **`parent-src/demo/dupe/Message.java`**:

~~~java
package demo.dupe;

public final class Message {
    public static String origin() {
        return "PARENT";
    }
}
~~~

File **`parent-resources/label.txt`**:

~~~text
PARENT
~~~

`parent.jar` enables an additional experiment on **parent-first precedence** without modifying the host or the two JARs A/B.

### 4.5. Host: Selecting URL Order and Checking Class Identity

File **`host-src/demo/host/JarOrderDemo.java`**:

~~~java
package demo.host;

import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.InvocationTargetException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class JarOrderDemo {
    private JarOrderDemo() {
    }

    private static String origin(ClassLoader loader)
            throws ClassNotFoundException, NoSuchMethodException,
            IllegalAccessException, InvocationTargetException {
        Class<?> type = loader.loadClass("demo.dupe.Message");
        return (String) type.getMethod("origin").invoke(null);
    }

    private static String resourceLabel(ClassLoader loader)
            throws IOException {
        try (InputStream stream = loader.getResourceAsStream("label.txt")) {
            if (stream == null) {
                return "(missing)";
            }
            return new String(
                    stream.readAllBytes(), StandardCharsets.UTF_8).strip();
        }
    }

    private static boolean parentCanLoad(ClassLoader parent) {
        try {
            parent.loadClass("demo.dupe.Message");
            return true;
        } catch (ClassNotFoundException ex) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: JarOrderDemo <a.jar> <b.jar>");
        }

        Path a = Path.of(args[0]).toAbsolutePath().normalize();
        Path b = Path.of(args[1]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(a) || !Files.isRegularFile(b)) {
            throw new IllegalArgumentException("Both JARs must exist");
        }

        URL aUrl = a.toUri().toURL();
        URL bUrl = b.toUri().toURL();
        ClassLoader parent = JarOrderDemo.class.getClassLoader();

        // AB and BA are two different loaders; each loader has its own URL order.
        try (URLClassLoader ab =
                     new URLClassLoader(new URL[] {aUrl, bUrl}, parent);
             URLClassLoader ba =
                     new URLClassLoader(new URL[] {bUrl, aUrl}, parent)) {

            System.out.println("AB class: " + origin(ab));
            System.out.println("BA class: " + origin(ba));

            System.out.println("AB resource: " + resourceLabel(ab));
            System.out.println("BA resource: " + resourceLabel(ba));

            Class<?> classAB = ab.loadClass("demo.dupe.Message");
            Class<?> classBA = ba.loadClass("demo.dupe.Message");

            System.out.println("AB and BA same Class: "
                    + (classAB == classBA));
            System.out.println("AB defined by child: "
                    + (classAB.getClassLoader() == ab));
            System.out.println("BA defined by child: "
                    + (classBA.getClassLoader() == ba));
            System.out.println("AB load again same Class: "
                    + (classAB == ab.loadClass("demo.dupe.Message")));
            System.out.println("Parent can load duplicate: "
                    + parentCanLoad(parent));
        }
    }
}
~~~

Key points:

- The host does not import `demo.dupe.Message`; it only knows the binary name as a string to attempt loading.
- `ab` has the URL order `[a.jar, b.jar]`, whereas `ba` has `[b.jar, a.jar]`.
- Both are created with **the same parent**: the loader that defined `JarOrderDemo`.
- `origin()` is a `public static` method, invoked via reflection to demonstrate which class was actually selected.
- `resourceLabel()` reads `label.txt` using `getResourceAsStream`. The example assumes there is only one copy of the file in each JAR and no resource with the same name in other entries outside the declared sources.
- `try-with-resources` closes both `URLClassLoader` instances to release the JAR resources. `close()` **does not force the JVM to unload classes immediately**.

## 5. Compiling and Packaging Each JAR

Requires JDK 17+ with `javac`, `jar`, and `java` on `PATH`. Run from the `jar-order-demo/` root directory with all files created as shown above.

**Bash (Linux/macOS/Git Bash):**

~~~bash
mkdir -p build/host build/a build/b build/parent dist

javac -encoding UTF-8 -d build/host \
  host-src/demo/host/JarOrderDemo.java

javac -encoding UTF-8 -d build/a a-src/demo/dupe/Message.java
javac -encoding UTF-8 -d build/b b-src/demo/dupe/Message.java
javac -encoding UTF-8 -d build/parent parent-src/demo/dupe/Message.java

cp a-resources/label.txt build/a/label.txt
cp b-resources/label.txt build/b/label.txt
cp parent-resources/label.txt build/parent/label.txt

jar --create --file dist/a.jar -C build/a .
jar --create --file dist/b.jar -C build/b .
jar --create --file dist/parent.jar -C build/parent .
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/host,build/a,build/b,build/parent,dist | Out-Null

javac -encoding UTF-8 -d build/host host-src/demo/host/JarOrderDemo.java

javac -encoding UTF-8 -d build/a a-src/demo/dupe/Message.java
javac -encoding UTF-8 -d build/b b-src/demo/dupe/Message.java
javac -encoding UTF-8 -d build/parent parent-src/demo/dupe/Message.java

Copy-Item a-resources/label.txt build/a/label.txt
Copy-Item b-resources/label.txt build/b/label.txt
Copy-Item parent-resources/label.txt build/parent/label.txt

jar --create --file dist/a.jar -C build/a .
jar --create --file dist/b.jar -C build/b .
jar --create --file dist/parent.jar -C build/parent .
~~~

Each JAR has its own `demo/dupe/Message.class` class and `label.txt` resource. You can verify with:

~~~bash
jar --list --file dist/a.jar
jar --list --file dist/b.jar
jar --list --file dist/parent.jar
~~~

The `jar --list` commands may also list `META-INF/MANIFEST.MF` and directory entries. These are plain JARs without a manifest `Class-Path`, without multi-release JAR entries, and without a module descriptor; therefore, the experiment results depend solely on the URL order and parent of the loaders described above.

## 6. Run 1: Parent Does Not Have the Duplicate Class

**Bash or PowerShell:**

~~~bash
java -cp build/host demo.host.JarOrderDemo dist/a.jar dist/b.jar
~~~

**Exact stdout:**

~~~text
AB class: A
BA class: B
AB resource: A
BA resource: B
AB and BA same Class: false
AB defined by child: true
BA defined by child: true
AB load again same Class: true
Parent can load duplicate: false
~~~

**Explanation:**

1. The parent is the application loader of `JarOrderDemo` and only contains `build/host`; it does not have `Message.class`. When `ab` asks the parent, the parent does not find it, so `ab` searches A before B and loads A's `Message` class.
2. The `ba` loader is independent and searches B before A, so it loads B's class.
3. Two different loaders **independently define** `demo.dupe.Message`; `classAB == classBA` is `false`. Having the same `getName()` does not make them the same runtime type.
4. Calling `ab.loadClass(...)` again returns the already known class rather than loading another version from B.
5. For the `label.txt` resource, `URLClassLoader` asks the parent first and then searches its own URLs. When the parent does not contain the resource, the A/B order also yields `A` or `B`.
6. `parentCanLoad(parent)` returns `false` because the parent does not inspect the URLs of child loaders.

**Do not interpret the "A wins" result as a JVM-wide rule.** It is the `ab` loader that prioritizes A in **its own** search path; the `ba` loader prioritizes B instead. If there are two different loaders, both classes can coexist at the same time.

## 7. Run 2: Parent Has the Duplicate Class

Now **do not modify the code, do not modify the JARs, and do not create a new loader by altering running bytecode**. Instead, **start a new JVM** while adding `dist/parent.jar` to the **application classpath**.

**Bash (Linux/macOS):**

~~~bash
java -cp "build/host:dist/parent.jar" \
  demo.host.JarOrderDemo dist/a.jar dist/b.jar
~~~

**Windows PowerShell:**

~~~powershell
java -cp "build/host;dist/parent.jar" demo.host.JarOrderDemo dist/a.jar dist/b.jar
~~~

**Exact stdout with default parent-first configuration:**

~~~text
AB class: PARENT
BA class: PARENT
AB resource: PARENT
BA resource: PARENT
AB and BA same Class: true
AB defined by child: false
BA defined by child: false
AB load again same Class: true
Parent can load duplicate: true
~~~

**Why do both AB and BA receive PARENT?**

- When `ab` and `ba` receive `loadClass("demo.dupe.Message")`, they ask the parent first.
- The parent finds `demo.dupe.Message` from `dist/parent.jar` on the application classpath and returns the class it defined.
- Both children receive **the same `Class<?>` object** from the parent; the A/B order inside the child ceases to have any effect for that class name.
- For `label.txt`, parent-first resource lookup also finds the parent's resource first; `getResourceAsStream` returns the content `PARENT`.

Practical takeaway: changing the child's URL order is **not enough** to solve "the host's JAR shadows the plugin's JAR." If the library is already present in the parent and the loader uses parent-first delegation, the parent version normally takes precedence.

## 8. What Happens When Two Class Versions Have Incompatible APIs?

The A/B experiment only changes the returned string, so either selected version still runs. In real applications, two JARs may contain different API versions:

~~~java
// Version v1 (illustrative code, not a file in the demo):
public final class Client {
    public static String build(String text) {
        return text;
    }
}

// Version v2 (illustrative code):
public final class Client {
    public static String build(String text, int count) {
        return text.repeat(count);
    }
}
~~~

Suppose the caller **is compiled against v2** and calls `Client.build("x", 2)`. If the runtime loader instead selects the v1 class (which lacks the corresponding method descriptor), executing the call can throw `NoSuchMethodError`. This is an issue of **binary compatibility** and which class gets loaded, not merely "whether a Class file is on the classpath."

Related common errors:

| Symptom | Likely Cause |
|---|---|
| `NoSuchMethodError` | Caller bytecode and the selected class version do not have the same method descriptor |
| `NoSuchFieldError` | The runtime class version is missing a field that the caller was compiled to access |
| `ClassCastException` | Two loaders defined two classes with the same name, or another class is incompatible with the target type |
| `LinkageError` | There is a conflict in type/loading constraints or binary incompatibility |
| `NoClassDefFoundError` | A class was requested for linking/initialization, but a dependency is unavailable at runtime or an initialization error was recorded |
| `ServiceConfigurationError` | A provider is misconfigured or incompatible with the service type required by the host |
| Behavior differs across environments | Different `-cp`/URL order, wildcards, transitive dependencies, or parent loaders |

**Diagnostic step:** identify **which class is actually used by the JVM**, rather than guessing from which JAR was "placed in the lib directory." Inspect the classloader topology, classpath/module path, and the defining source of the class. `Class.getProtectionDomain().getCodeSource()` is often helpful when a CodeSource is available, but it may return `null` and should not be treated as a mandatory indicator in every environment.

## 9. Duplicate Resource Names and `getResources`

For a standard `URLClassLoader`:

- `getResource(name)` returns the URL of the **first** resource the loader finds following the parent-first lookup chain and then the loader's own URL path.
- `getResources(name)` can return **multiple URLs** (for example, both A and B), typically ordered with parent resources first followed by child loader resources.
- `getResourceAsStream(name)` opens the corresponding first resource; the application must close the stream.
- For configuration files aggregated across multiple JARs, such as `META-INF/services/com.example.Service`, `ServiceLoader` can read **multiple** resource descriptors rather than simply taking the first file and ignoring all the rest.

In real applications, resource order can also affect configuration files such as `log4j2.xml`, `application.properties`, or default resources. However, each framework has its own configuration loading/merging rules; do **not** assume every framework uses Java's exact `getResource` logic and simply picks the first file.

For example, if you want to inspect all `label.txt` entries from loader AB, use this illustrative snippet inside a method where `ab` is already available:

~~~java
// Illustrative code; requires ab and import java.util.Enumeration.
java.util.Enumeration<URL> urls = ab.getResources("label.txt");
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
~~~

The URL contents depend on absolute paths, so this example **does not promise a specific stdout**. When an application needs to enumerate duplicate resources, this is a more appropriate operation than `getResource`. For resources in **named modules**, encapsulation/`opens` rules may affect visibility.

## 10. Distinguishing Three Levels of Precedence

| Level | Question | Example |
|---|---|---|
| **ClassLoader topology** | Does the child ask the parent first? | The parent has `Message`, so both A and B in the child are shadowed |
| **URL/classpath order of a loader** | When the parent does not have it, which source does the loader examine first? | `[a.jar, b.jar]` selects A; `[b.jar, a.jar]` selects B |
| **Runtime class identity and cache** | Which class has the loader already defined/received for that binary name? | A second `ab.loadClass` request still returns class A; another loader may return class B |

Two concepts that are often conflated should be separated:

**"First found"** is the search rule *within a lookup path* at the moment a class/resource needs to be located.

**"First loaded/defined"** refers to a loader's state with respect to a class. Once a loader has defined a class, the JVM does not allow that same loader to arbitrarily redefine the same binary name as a replacement; attempting to redefine it can cause a `LinkageError`. Changing the URL order of a running loader does not turn an already-defined class A into class B.

If you want to replace a plugin version within the same JVM, you typically create a **new loader**, stop using the old objects/loader, release references and resources, and then create new instances. There is no mechanism to alter an existing class object simply by modifying a JAR on disk.

## 11. Special Scenarios

### 11.1. Wildcard Classpath

~~~bash
java -cp "lib/*" demo.app.Main
~~~

The launcher expands `*` into matching JARs in the directory. **The expansion order is not guaranteed** by the Javadoc/launcher specification; do not intentionally place two versions with the same FQCN in `lib/` expecting `a.jar` to beat `b.jar` because its name comes first. Use an explicit dependency graph and eliminate redundant copies.

### 11.2. Multi-Release JAR

A **multi-release JAR** can contain versions of classes targeting different Java releases under `META-INF/versions/...`. Selecting a class version when reading the JAR also depends on the runtime version and multi-release rules; this is **different** from competition between two JARs containing the same FQCN.

### 11.3. Named Modules and Split Packages

When running with `--module-path`, JPMS resolves modules according to dependency relationships and package/module rules. Two modules providing the same package to the same consumer module can cause configuration/resolution or compilation to fail; there is no general "earlier on the module path wins for duplicate classes" rule.

### 11.4. Child-First in Plugin Containers

Some application servers implement child-first loading for each application's libraries to avoid conflicts with the host. In that case, a plugin can deliberately pick class versions in its child JARs before the parent, **but** it is very easy to end up creating two runtime interfaces/DTOs with the same name if shared APIs are not explicitly kept "parent-first". Dependency isolation must be accompanied by clear type boundaries.

### 11.5. Compile-Time Order Differing from Runtime

`javac` may select an API from the compile-time classpath, while `java` at runtime sees a different JAR due to a different dependency order. Successful compilation **does not prove** that the runtime class has the same method/field signatures. Dependency managers (Gradle/Maven) should lock/check versions and exclude unintended duplicate dependencies.

## 12. Quick Checks on Real Projects

1. **List entries containing the duplicate class**: inspect JARs with `jar --list --file path/to/library.jar` or dependency analysis tools. The `jar --list` command only proves **the file contains the class**, not that the JVM used that version.
2. **Record the runtime ClassLoader**: call `SomeClass.class.getClassLoader()`; compare loader identity using `==` rather than relying on `toString()` strings.
3. **Identify the bytecode source**: if available, check `SomeClass.class.getProtectionDomain().getCodeSource()`; it may be `null` for some loaders/classes.
4. **Inspect the launch config**: `java -cp`, IDE classpath, test runtime classpath, `java.system.class.loader`, module path, agents, and plugin loaders.
5. **Check whether order matters**: if the parent already has the class, reversing the child URL order normally does not change the result; if the parent does not have it, URL order can determine the outcome.
6. **Verify dependency versions**: if you see a `NoSuchMethodError`, check whether the actually loaded class has the expected signature using `javap` or an equivalent tool; do not just add JARs randomly.
7. **Separate shared APIs from implementations**: have the host and plugins communicate using types defined by a common parent to avoid cast errors across multiple loaders.

## 13. Common Mistakes and How to Fix Them

| Mistake | Why It Is Wrong | How to Fix |
|---|---|---|
| "Placing the new JAR at the end of `-cp` gives it priority" | On a standard shared classpath, earlier entries are usually searched first | Clarify the order and remove duplicate versions |
| "Reversing child URL order is guaranteed to change the class" | The parent may already have loaded or found the class | Check the parent and where the class is defined |
| "A single JVM cannot have two classes with the same FQCN" | Two different defining loaders can create two distinct runtime types | Compare `Class<?>` and `getClassLoader()` |
| "URLClassLoader always chooses JARs in alphabetical order" | The order comes from the URL array, not from sorting file names | Pass the URL order explicitly |
| "Wildcards `lib/*` have a stable order" | Wildcard expansion rules do not guarantee order | Remove duplicate classes and manage the classpath in a controlled manner |
| "The class is in a JAR, so the JVM definitely loaded it" | It may be shadowed by a class from another JAR/parent | Check the defining loader and CodeSource if available |
| "Java 17 classpath and module path are the same" | JPMS has different module/package, visibility, and resolution rules | Distinguish between classpath and `--module-path` |
| "Replacing a JAR on disk updates already-loaded classes" | Class objects/bytecode already defined by a loader do not change automatically | Create a new loader or restart the process |

## 14. Self-Check

**Question 1.** The parent does not have `demo.dupe.Message`. A child loader has URLs in the order `[a.jar, b.jar]`, with each JAR containing the same FQCN. Under the standard `URLClassLoader` in the example, which implementation is selected?

**Answer:** The version in `a.jar`, because it is the first URL containing the requested class.

**Question 2.** Two independent child loaders receive `[a.jar, b.jar]` and `[b.jar, a.jar]`, respectively. Are the two resulting `Class<?>` objects equal under `==`?

**Answer:** No, when each loader defines the class itself; runtime identity is binary name + defining loader.

**Question 3.** The parent has a class with the same name. If you swap the A/B URLs in the child without changing the parent, what is the typical result?

**Answer:** Both children receive the class defined by the parent (parent-first); changing the URL order inside the child is not enough to switch the class.

**Question 4.** How many resources can `child.getResources("label.txt")` see when both JARs contain that file?

**Answer:** It can list **two URLs** for A and B (plus any resource from the parent, if present). `getResource` returns only the single first result.

**Question 5.** Why can code compile cleanly yet encounter `NoSuchMethodError` at runtime?

**Answer:** The caller may have been compiled against the class in JAR v2, while the runtime loader selected the class in JAR v1 which no longer has the required method descriptor.

**Question 6.** Should you use `-cp "lib/*"` to guarantee that a library version is selected by JAR name?

**Answer:** No. Wildcard expansion order is not guaranteed. It is best to resolve duplicate dependencies and ensure explicit versions.

## 15. References

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, class identity, and resources.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): URL search path and closing the loader.
- [Java SE 17 — Java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `--class-path`, path separators, and wildcard expansion.
- [Java Virtual Machine Specification 17 — Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): concepts of defining loader and loading constraints.
- [JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): manifest `Class-Path` attribute and JAR structure.
- [Java SE 17 — Class#getProtectionDomain](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getProtectionDomain()): domain/source information when available.

**Key takeaway:** Determining which JAR "wins" requires considering **parent delegation first**, **the class search order within the specific loader second**, and **already-defined/cached classes**. If there are multiple ClassLoaders, two classes with the same FQCN can still coexist as two different runtime types.
