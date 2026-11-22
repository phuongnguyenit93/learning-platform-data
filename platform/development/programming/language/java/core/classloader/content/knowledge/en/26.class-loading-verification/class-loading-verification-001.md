# Creating a Fixture with the Same Class Name in Two JARs to Verify ClassLoader

## 1. Why Is a Fixture with Duplicate Class Names Needed?

In a large Java application, two versions of a library may both package `com.example.Library.class`. The important issue when diagnosing is not just “both JARs contain the class” but also **which source the JVM selected the definition from, via which ClassLoader, and in what order**.

If you test on real project JARs, the results can easily be affected by the dependency graph, parent delegation, module path, manifest `Class-Path`, wildcard classpath, build cache, or an accidental classpath order. A **fixture** is a small, reproducible set of inputs: we create **two independent JARs containing the same binary name**, where the class contents return two distinguishable results. Then we use explicitly configured ClassLoaders to test each hypothesis.

Lesson fixture:

```text
A.jar
├── fixture/same/Versioned.class
│   └── origin() returns "A"
└── fixture/label.txt
    └── A

B.jar
├── fixture/same/Versioned.class
│   └── origin() returns "B"
└── fixture/label.txt
    └── B
```

The **binary name** of both versions is `fixture.same.Versioned`. The entry file name in the JAR for both is `fixture/same/Versioned.class`. Only the **method body** and the marker resource differ, which helps verify the chosen source without having to rely on the JAR name or timestamp.

Verification goals:

1. **Properly create two real JARs**, each containing the same class entry.
2. Load the class via `URLClassLoader` with URL orders `[A.jar, B.jar]` and `[B.jar, A.jar]`.
3. Prove that different URL orders can select **two different versions of the method** when the parent does not have the class.
4. Prove that each independent loader creates its own **runtime class identity** even when the binary name is the same.
5. Create a **parent→child** pair to demonstrate that parent-first delegation typically wins over the duplicate version in the child.
6. Distinguish **class definition** from **resource enumeration** when a resource name appears in multiple JARs.
7. Ensure the example has deterministic run commands and output, cleans up the fixture automatically, and requires no dependencies outside the JDK.

## 2. Some Concepts to Get Right Before Creating JARs

### 2.1. Binary Name Differs from the Entry Path in a JAR

Given the source:

```java
package fixture.same;

public final class Versioned {
    public String origin() {
        return "A";
    }
}
```

This is the **illustrative source** for version A. Version B has an identical package/class/method declaration, but returns `"B"`.

- **Binary name:** `fixture.same.Versioned`, used for `loader.loadClass(...)`.
- **Class file entry:** `fixture/same/Versioned.class`, used when placing the file into the JAR.
- **Root:** the JAR file containing that entry, not the Java package directory.
- **Separator:** entry names in a JAR use `/` across Linux, macOS, and Windows.
- **Bytecode:** the two versions must be **compiled separately**, not by compiling two files with the same fully-qualified name at the same time into a single output folder.

Two class files can coexist in **two JARs** without causing `javac` or the JAR format to automatically reject them. Conflicts are observed when they **both participate in the search path** of a loader/runtime or when different bytecode is incompatible with the calling code.

### 2.2. Parent-First Delegation Typically Occurs Before URL Order

`URLClassLoader` inherits the default parent-first `loadClass` mechanism:

```text
child.loadClass("fixture.same.Versioned")
    |
    +-- already recorded as loaded? -> return existing Class
    |
    +-- parent has class?           -> return parent's Class
    |
    +-- child.findClass             -> search local URLs along the search path
           |
           +-- A.jar before B.jar -> may select A
           +-- B.jar before A.jar -> may select B
```

**Therefore, “JAR A comes before JAR B” only describes the priority of the local search path under the condition that the parent has not already provided the class.** If the parent already has `fixture.same.Versioned`, the child receives the parent's definition, even if the child only has B.jar.

A custom plugin loader may change this to child-first or per-package, but that is **not** the default policy of `URLClassLoader`.

### 2.3. Same Binary Name Does Not Mean Same Runtime Type

A runtime class/interface is identified by the pair:

```text
(binary name, defining ClassLoader)
```

Therefore:

```text
("fixture.same.Versioned", LoaderAB) !=
("fixture.same.Versioned", LoaderBA)
```

Even when two loaders use the same JAR and the class files are byte-for-byte identical, if each loader **defines the class itself**, the two `Class<?>` objects represent **two different runtime classes**.

Verification indicators are `Class.getClassLoader()`, `Class<?> ==`, and `Class.isInstance(...)`, not merely comparing `getName()`.

## 3. Fixture Design: Simple Yet Sufficient to Differentiate

We intentionally use the following conditions:

| Component | Design | Reason |
| --- | --- | --- |
| Java version | Java 17+ | Runs on common JDKs; supports `JavaCompiler` and try-with-resources |
| Bytecode source | `javax.tools.JavaCompiler` | Generates real classes, not fake byte arrays |
| JAR packaging | `java.util.jar.JarOutputStream` | Real JARs with accurately named entries, without depending on external tools |
| Binary name | `fixture.same.Versioned` in both A and B | Creates an intentional conflict |
| Distinguishing method | `origin()` returns `A` or `B` | Observes which definition wins via stdout |
| Duplicate resource | `fixture/label.txt` | Separates resource lookup from class lookup |
| Parent of AB/BA | Platform ClassLoader | Prevents the application loader from accidentally seeing fixture classes |
| Parent-child test | Parent[A.jar] → Child[B.jar] | Verifies parent-first |
| Resource cleanup | Close loaders, `JarFile`, streams, delete temp directory | Does not hold file handles in the example |
| Assertion/observation | Prints booleans and clearly named values | Does not depend on object hash, PID, or temp path |

The fixture has **two JARs**, yet creates **four URLClassLoader objects** in one test run to clearly separate URL order and parent relationships. There is no need to use two external JARs or a separate testing library.

### Assumptions to Maintain

- The platform parent does not contain `fixture.same.Versioned` (true for standard JDKs).
- The program does not separately place A.jar/B.jar onto the application classpath.
- The generated class is an ordinary class in the unnamed module of its own loader, not a named module in JPMS.
- No custom classloader policy, transforming bytecode agent, or manifest `Class-Path` is used.
- The machine has a JDK with the `jdk.compiler` compiler module and read/write permissions for the temporary directory.

Thanks to the conditions above, the program's stdout can be predicted and verified accurately.

## 4. Complete Java 17 Program to Create and Test Two JARs

Save **all** of the code below as the file `DuplicateJarFixture.java`. The program:

1. Creates a temporary directory.
2. Generates and compiles two versions of `fixture.same.Versioned` into two different output roots.
3. Packages each version into a JAR along with the marker resource.
4. Checks that both JARs contain the class entry.
5. Tests ClassLoaders with different URL orders and parent hierarchies.
6. Reads resources and checks runtime class identity.
7. Closes the JARs/loaders and deletes the temporary files.

```java
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Enumeration;
import java.util.List;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.JarOutputStream;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class DuplicateJarFixture {
    private static final String BINARY = "fixture.same.Versioned";
    private static final String CLASS_ENTRY = "fixture/same/Versioned.class";
    private static final String LABEL_ENTRY = "fixture/label.txt";

    private static Path createJar(JavaCompiler compiler, Path root,
                                  String marker) throws IOException {
        Path source = root.resolve("source-" + marker + "/" + CLASS_ENTRY)
                .resolveSibling("Versioned.java");
        Path classes = root.resolve("classes-" + marker);
        Files.createDirectories(source.getParent());
        Files.createDirectories(classes);
        Files.writeString(source,
                "package fixture.same; public final class Versioned {"
              + " public String origin() { return \"" + marker + "\"; } }",
                StandardCharsets.UTF_8);
        int result = compiler.run(null, null, null,
                "--release", "17", "-encoding", "UTF-8",
                "-d", classes.toString(), source.toString());
        if (result != 0) {
            throw new IllegalStateException("Compilation failed: " + marker);
        }
        Path jar = root.resolve(marker + ".jar");
        try (JarOutputStream out = new JarOutputStream(Files.newOutputStream(jar))) {
            out.putNextEntry(new JarEntry(CLASS_ENTRY));
            out.write(Files.readAllBytes(classes.resolve(CLASS_ENTRY)));
            out.closeEntry();
            out.putNextEntry(new JarEntry(LABEL_ENTRY));
            out.write(marker.getBytes(StandardCharsets.UTF_8));
            out.closeEntry();
        }
        return jar;
    }

    private static String origin(Class<?> type) throws ReflectiveOperationException {
        Object instance = type.getDeclaredConstructor().newInstance();
        return (String) type.getMethod("origin").invoke(instance);
    }

    private static String read(URL resource) throws IOException {
        try (var in = resource.openStream()) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private static boolean hasEntry(Path jar, String entry) throws IOException {
        try (JarFile file = new JarFile(jar.toFile())) {
            return file.getJarEntry(entry) != null;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a full JDK 17+");
        }
        Path root = Files.createTempDirectory("duplicate-jar-fixture-");
        try {
            Path aJar = createJar(compiler, root, "A");
            Path bJar = createJar(compiler, root, "B");
            System.out.println("twoJarFiles="
                    + (Files.isRegularFile(aJar) && Files.isRegularFile(bJar)));
            System.out.println("bothContainClass="
                    + (hasEntry(aJar, CLASS_ENTRY) && hasEntry(bJar, CLASS_ENTRY)));
            URL a = aJar.toUri().toURL();
            URL b = bJar.toUri().toURL();
            ClassLoader platform = ClassLoader.getPlatformClassLoader();
            try (URLClassLoader ab = new URLClassLoader(new URL[]{a, b}, platform);
                 URLClassLoader ba = new URLClassLoader(new URL[]{b, a}, platform);
                 URLClassLoader parent = new URLClassLoader(new URL[]{a}, platform);
                 URLClassLoader child = new URLClassLoader(new URL[]{b}, parent)) {
                Class<?> classAB = ab.loadClass(BINARY);
                Class<?> classBA = ba.loadClass(BINARY);
                Class<?> classChild = child.loadClass(BINARY);
                System.out.println("abOrigin=" + origin(classAB));
                System.out.println("baOrigin=" + origin(classBA));
                System.out.println("abDefinedByAB=" + (classAB.getClassLoader() == ab));
                System.out.println("baDefinedByBA=" + (classBA.getClassLoader() == ba));
                System.out.println("sameBinaryName="
                        + classAB.getName().equals(classBA.getName()));
                System.out.println("sameRuntimeClass=" + (classAB == classBA));
                System.out.println("crossAssignable="
                        + classAB.isInstance(classBA.getDeclaredConstructor().newInstance()));
                System.out.println("repeatSameClass=" + (classAB == ab.loadClass(BINARY)));
                System.out.println("childOrigin=" + origin(classChild));
                System.out.println("childDefinedByParent="
                        + (classChild.getClassLoader() == parent));
                System.out.println("abFirstResource=" + read(ab.getResource(LABEL_ENTRY)));
                Enumeration<URL> resources = ab.getResources(LABEL_ENTRY);
                List<String> found = new ArrayList<>();
                while (resources.hasMoreElements()) {
                    found.add(read(resources.nextElement()));
                }
                System.out.println("abResources=" + String.join(",", found));
                System.out.println("resourceCount=" + found.size());
                System.out.println("stringFromBootstrap="
                        + (ab.loadClass("java.lang.String").getClassLoader() == null));
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }
}
```

### 4.1. Compile and Run

Open a terminal in the directory containing `DuplicateJarFixture.java` and use JDK 17 or later:

```bash
javac --release 17 DuplicateJarFixture.java
java DuplicateJarFixture
```

**There is no need to pre-create** `A.jar` or `B.jar`. They are created by the program in a temporary directory at runtime, then deleted at the end. Because the generated source code is Java 17-compatible, the program can run on JDK 17+ with a full compiler.

### 4.2. Expected Stdout When Running the Fixture on JDK 17+

With the Java compiler and the JARs created by the program, the expected stdout consists of 16 lines:

```text
twoJarFiles=true
bothContainClass=true
abOrigin=A
baOrigin=B
abDefinedByAB=true
baDefinedByBA=true
sameBinaryName=true
sameRuntimeClass=false
crossAssignable=false
repeatSameClass=true
childOrigin=A
childDefinedByParent=true
abFirstResource=A
abResources=A,B
resourceCount=2
stringFromBootstrap=true
```

If run on a minimal JDK without `JavaCompiler`, the program intentionally throws `IllegalStateException` with instructions to use a full JDK. If creating/deleting temporary files is not permitted, an I/O error will occur and should not be misinterpreted as a parent-first error.

### 4.3. Explanation of Results by Group

**`twoJarFiles=true`:** real A.jar and B.jar files were created. This checks file existence, but an existing JAR does not guarantee having the correct class entry — hence the next step is needed.

**`bothContainClass=true`:** uses `JarFile.getJarEntry("fixture/same/Versioned.class")` to confirm that both JARs contain the same entry path. This is a JAR structure check and does not by itself confirm that the JVM loaded the class from both.

**`abOrigin=A`, `baOrigin=B`:** with a platform parent that lacks the fixture class, the loader with URL[A,B] receives version A while URL[B,A] receives version B. This is empirical evidence of **local search order**.

**`abDefinedByAB=true`, `baDefinedByBA=true`:** `getClassLoader()` of the runtime classes equals the loader that defined them itself. If the parent already had the class, this might no longer hold true.

**`sameBinaryName=true`, `sameRuntimeClass=false`:** the two classes have the same Java name but different defining loaders, so they are **two runtime types**. The result of `getName().equals(...)` cannot be treated as proof that they are the same class.

**`crossAssignable=false`:** an instance created by class B is not an instance of class A. Attempting to cast directly between these two runtime classes may encounter a `ClassCastException` (in an applicable cast context). The example uses `Class.isInstance` to observe safely without intentionally causing the program to fail.

**`repeatSameClass=true`:** loader AB has already defined `fixture.same.Versioned`, so a subsequent call to `ab.loadClass(BINARY)` returns the same class object; changing bytecode on disk will not automatically create a new definition in the same loader.

**`childOrigin=A`, `childDefinedByParent=true`:** the child only has B.jar, whereas the parent contains A.jar. According to parent-first delegation, the child receives the Class defined by the **parent** from A.jar. Changing only the child's JAR does not make version B win on its own.

**`abFirstResource=A`, `abResources=A,B`, `resourceCount=2`:** `getResource` returns the first resource; `getResources` lists both resources with the same name across the JARs. Resource lookup and class definition are **two different mechanisms**. Two resources do not mean a loader has defined two classes with the same binary name.

**`stringFromBootstrap=true`:** `java.lang.String` belongs to the JDK runtime and is defined by the bootstrap loader. `null` from `getClassLoader()` represents the bootstrap loader in the API.

## 5. Reading the Fixture's ClassLoader Diagram

Two different tests have been included in the same program:

### 5.1. Testing URL Order with Two Independent Loaders

```text
Platform
    |
    +-- AB Loader: [A.jar, B.jar] -> Versioned.origin() = "A"
    |
    +-- BA Loader: [B.jar, A.jar] -> Versioned.origin() = "B"
```

Because AB and BA are **two defining loaders**, they can both define the name `fixture.same.Versioned` as two independent runtime classes. Within each individual loader, no two class definitions with the same binary name are created.

### 5.2. Testing Parent-First with Parent/Child

```text
Platform
    |
    +-- Parent: [A.jar]
           |
           +-- Child: [B.jar]

Child.loadClass("fixture.same.Versioned")
    -> parent.loadClass(...)
    -> Parent returns class from A.jar
    -> Child does NOT define version B itself
```

This is why there must be both the **URL-reversal** test and the **parent delegation** test. If we only test a single AB loader, we have not yet proven the case where the parent provides the class first.

If an application uses a child-first custom loader, another test must be written that accurately reflects its policy, rather than taking the parent-first output here as the expectation for every framework.

## 6. When Are Two JARs Considered to Have “Duplicate Classes”?

There are several types of duplication to distinguish:

| Phenomenon | Example | Is It Necessarily an Error? |
| --- | --- | --- |
| Duplicate **entry path** | Both A.jar and B.jar contain `fixture/same/Versioned.class` | Not automatically; the loader can select one version |
| Duplicate **binary name** | Two class files both declare `fixture.same.Versioned` | It is a conflict to manage if on the same search path |
| Byte-for-byte identical bytecode | Two JARs copy the exact same `.class` | Can still create different runtime types via two defining loaders |
| Same name but different bytecode | Fixture A returns `A`, B returns `B` | Can affect logic or ABI compatibility |
| Duplicate **resource** | Both contain `fixture/label.txt` | Can be intentional, such as service descriptors |
| Same package but different classes | A.jar has `pkg.X`, B.jar has `pkg.Y` | Can be valid; still subject to sealing/signers/JPMS |
| Two modules with the same package | Named modules on the module path | Have their own resolution/encapsulation rules |

The JAR format allows two **different** JARs to contain the same entry path. This differs from having **two duplicate entry names in the same JAR**, which should be avoided and is typically rejected by JAR creation tools with a duplicate entry error.

### Must Also Check the Actual Name Inside the Class File

The path `fixture/same/Versioned.class` in the JAR does not by itself prove that the class file inside actually declares `fixture.same.Versioned`. A renamed file or transformed bytecode may contain a different binary name, leading to a “wrong name” error when loaded.

In the fixture, `javac` compiles the source with matching package/class names and the program takes the exact output path, keeping the path name and binary name consistent. For a suspect JAR, use `javap -verbose` or a class-file format inspection tool instead of relying solely on the entry name.

## 7. Testing the Fixture in a Real Project: Maintaining Reproducible Conditions

### 7.1. Do Not Pass Two Class Sources with the Same Name into a Single javac Invocation

A common mistake is creating two files:

```text
src/a/fixture/same/Versioned.java
src/b/fixture/same/Versioned.java
```

and then compiling both in the same invocation with a shared output:

```bash
javac -d build/classes src/a/fixture/same/Versioned.java src/b/fixture/same/Versioned.java
```

This is an **intentionally incorrect command example**: when generating `fixture.same.Versioned` together, the compiler may report a duplicate class. It is **not** the way to create two JARs with independent bytecode versions.

The right way is **two independent invocations**, each with its own output root:

```text
src-a/fixture/same/Versioned.java --javac--> classes-a/
src-b/fixture/same/Versioned.java --javac--> classes-b/

classes-a/fixture/same/Versioned.class --jar--> A.jar
classes-b/fixture/same/Versioned.class --jar--> B.jar
```

The fixture program already performs this process automatically using `compiler.run(...)` twice and `JarOutputStream`.

### 7.2. Do Not Accidentally Place Fixture Classes in the Parent

If running the host with the classpath:

```bash
java -cp "fixture/A.jar:fixture/B.jar:app/classes" my.app.Main
```

(this is a Linux/macOS example; Windows uses `;`), the application parent loader may load `fixture.same.Versioned` before the plugin child. In that case, changing the URLs in the child will not necessarily change the result, because parent-first already prioritizes the parent.

The demo avoids this discrepancy by using the **platform loader** as the parent of the independent URLClassLoaders. For a real application, you must model the class loader tree accurately to match the deployment environment.

### 7.3. Wildcards Are Not a Way to Guarantee JAR Order

A command like:

```bash
java -cp "lib/*:app/classes" my.app.Main
```

has its wildcard expanded by the Java launcher into the JARs in the directory. The order of wildcard expansion is not guaranteed to be alphabetical or “newest version first”; you should not construct tests expecting A to beat B solely because of the file name.

In the fixture, the arrays `new URL[]{a,b}` and `new URL[]{b,a}` are declared with **explicit order**, so they do not depend on wildcards.

### 7.4. Repeatability During Build/Test

To make tests easily reproducible, you should:

- Use the same JDK toolchain/runtime target.
- Compile A and B separately so they do not depend on an accidental classpath.
- Assign a fixed binary name and clear marker output.
- Use distinct temporary JAR names/paths, separate from project artifacts.
- Let the test create and clean up the fixture itself instead of using a hand-edited JAR from a previous test run.
- Do not select the class source based on timestamp, file size, or filename version.
- Ensure the manifest does not indirectly add classpath entries that make the search order hard to control.
- Use separate class loaders for different scenarios, closing each loader.
- Do not let the IDE/test runner automatically add fixture classes to the application classpath.
- Check the **actual Class<?>** result, rather than only printing every file found in the JAR.

## 8. Keeping the Fixture to Inspect with jar and javap

The complete program in section 4 **deletes A.jar and B.jar after running**, because it is a self-cleaning test. To inspect manually with `jar tf` and `javap`, there are two options:

1. Use a debugger or a secondary test **designed to keep the artifacts** in a specific directory instead of deleting them.
2. Use a separate build process to package the two source versions into two stable JARs for integration testing.

You should not run `jar tf A.jar` after the program has deleted the temporary directory and conclude that the fixture failed because the file no longer exists.

Once the two JARs **are preserved**, the inspection commands are:

```bash
jar tf A.jar
jar tf B.jar
javap -classpath A.jar -public fixture.same.Versioned
javap -classpath B.jar -public fixture.same.Versioned
```

`jar tf` lists entries; `javap` displays the class and signatures. Because versions A and B have the same method descriptor `origin(): String`, `javap -public` **does not directly show the A/B value** in the method body. To inspect the method bytecode, you can use:

```bash
javap -c -classpath A.jar fixture.same.Versioned
javap -c -classpath B.jar fixture.same.Versioned
```

This command displays the instructions, including the constant `"A"` or `"B"` in the corresponding bytecode. When multiple classes are duplicated, compare names, method descriptors, and dependencies as well, not just a single string-returning method.

### Verification Using CodeSource

If you need to know which JAR actually provided a loaded class, you can use:

```java
java.security.CodeSource codeSource =
        type.getProtectionDomain().getCodeSource();

System.out.println(codeSource == null
        ? "<unknown>"
        : codeSource.getLocation());
```

This is a snippet that requires a `Class<?> type` already obtained from a runtime call. For `URLClassLoader` loading classes from normal JARs, `CodeSource.getLocation()` usually points to the selected JAR URL. However, CodeSource can be `null` for bootstrap or custom in-memory loaders; the absence of a CodeSource should not be taken as proof that the class was not defined.

In the A/B test, you can add assertions comparing `type.getClassLoader()` and the CodeSource URI against `A.jar`/`B.jar` depending on environment conditions. This is **supplementary verification**, while the primary result remains the marker method together with loader identity.

## 9. Duplicate Resource Names and Duplicate Class Names Provide Two Types of Evidence

The fixture places `fixture/label.txt` in both A.jar and B.jar. `ab.getResource("fixture/label.txt")` returns the first resource in search order, while `ab.getResources(...)` can enumerate both. This **does not mean the AB loader defined two runtime classes** with the binary name `fixture.same.Versioned`: `loadClass` returns one `Class<?>` per definition in that loader.

In real applications, `META-INF/services/...` can also have multiple valid resource entries consumed by `ServiceLoader`. The resource check here only tests the fixture's *candidate resources*; the lesson **Verifying Resource Lookup and Service Providers** is dedicated to descriptors, API/service identity, TCCL, and provider instantiation.

## 10. From Fixture to Automated Regression Testing

The fixture can be turned into assertions instead of only printing to stdout. A test suite should verify:

| Assertion | Expected | What Is Protected |
| --- | --- | --- |
| Two JAR files exist | Both A.jar and B.jar are files | Correct packaging |
| Both JARs have the same class entry | `JarFile.getJarEntry(CLASS_ENTRY) != null` | Duplicate binary-name candidate |
| URL[A,B] → `origin()` | `A` | Local URL order |
| URL[B,A] → `origin()` | `B` | Reversing URLs changes the class version |
| `classAB.getClassLoader() == ab` | `true` | AB is the defining loader |
| `classBA.getClassLoader() == ba` | `true` | BA is the defining loader |
| Two `Class<?>` objects | `classAB != classBA` | Different type identity |
| Instance B checked by class A | `isInstance(...) == false` | No automatic cross-loader casting |
| Repeated `ab.loadClass(...)` | Returns the same `Class<?>` | Cached class in loader |
| Child(B) with Parent(A) | Receives class from parent A | Parent-first delegation |
| Resource A/B | Enumeration has two markers | Class vs resource semantics |
| JDK String | Defining loader is bootstrap | Platform class loading |

A Java 17 assertion method that can be used:

```java
static void check(boolean condition, String description) {
    if (!condition) {
        throw new AssertionError(description);
    }
}
```

This is a helper, not a standalone program. You can replace the `System.out.println` lines in the demo with `check(...)` using the expected results.

### Checking Order and Avoiding Flakiness

When testing the fixture:

- **Do not** use `ClassLoader.toString()`, object identity hash, or random temp paths as exact stdout.
- **Do not** rely on when the JVM runs the class initializer unless you actively trigger/observe it.
- **Do not** require the garbage collector to unload the loader immediately after `close()`.
- **Do not** reuse cache from a previous test run when needing to load a fresh definition; create a new loader.
- **Do not** run multiple tests using the same binary name on the application parent classpath, which makes results depend on test order.
- If tests run across multiple threads, control environment state and do not share a mutable URL list.
- You should use a dedicated marker package name to avoid conflicting with real dependencies in the test runner.

A small fixture can be upgraded into a test for binary compatibility by giving A.jar and B.jar **different APIs**, but you must distinguish an intentional ABI failure result from a classloader setup error.

## 11. Advanced Variant: API Version Conflict

In the main fixture, both A and B provide:

```java
public String origin()
```

so the calling code invokes a method with the same signature in both versions. To illustrate `NoSuchMethodError` caused by a compile/runtime version mismatch, create two different library versions:

**Compile-time version A:**

```java
package fixture.same;
public final class Versioned {
    public String origin() {
        return "A";
    }
    public String newMethod() {
        return "only-in-A";
    }
}
```

**Runtime version B:**

```java
package fixture.same;
public final class Versioned {
    public String origin() {
        return "B";
    }
}
```

These are **two alternative source versions** and must not be compiled into the same output root. If the consumer was compiled to call A's `Versioned.newMethod()` but the runtime classloader defines `Versioned` from B, the JVM can throw `NoSuchMethodError` when resolution/invocation requires that method.

This scenario **is not part of the main demo's stdout**, but rather an intentional extension path. To test it accurately:

1. Compile the consumer with A.jar on the compile classpath.
2. At runtime, exclude A.jar from the loader that will define `Versioned`, providing B.jar instead.
3. Observe the actual exception, stack trace, and defining loader.
4. Compare method descriptors with `javap -classpath ... -p`.
5. Do not use `catch Throwable` to hide the link-time error and falsely report a passing test.

**Conclusion:** a duplicate class does not always cause an exception immediately at load time; sometimes the logic silently changes, and sometimes it only fails at the method call that depends on an API present only in another version.

## 12. Limitations When Moving the Fixture to Real JARs

The experiment uses the classpath/unnamed modules and two simple classes. With JARs that have **package sealing** or different signer signatures, defining classes in the same package can fail before we observe the `origin()` method; `SecurityException` errors or certificate/package constraints must be investigated separately. When using **JPMS named modules**, module resolution, readability, exports, and package conflicts apply differently from classpath URL ordering.

Do not generalize the `AB=A` output into a class selection rule for every module layer, application server, or plugin loader with its own policy. The package-private verification lesson focuses on **runtime package identity and loader** rather than the same package path.

## 13. Common Errors When Creating and Running a Duplicate-JAR Fixture

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `duplicate class` at compile time | Compiling two sources with the same binary name in one invocation/output | Compile A/B independently and separate outputs |
| `ClassNotFoundException` | Wrong JAR entry path, non-existent URL, incorrect binary name | Verify `JarFile`, path, and `loadClass` name |
| `NoClassDefFoundError: wrong name` | Renamed entry file while bytecode declares a different name | Check the constant pool/class identity |
| `ClassFormatError` / `VerifyError` | Corrupted or invalidly generated bytes | Use `javac`, `javap -verbose`, and check the source artifact |
| `UnsupportedClassVersionError` | Compiled with a newer JDK than the runtime supports | Use `--release 17` and run on JDK 17+ |
| A/B does not change when reversing URLs | Parent already has the class, the class is already cached, or checking the same loader | Print `getClassLoader()`, create separate loaders |
| `ClassCastException` with the same class name | Two different defining loaders | Share the API/SPI via the parent; do not cast arbitrarily |
| `NoSuchMethodError` | Runtime selects a class version missing the compile-time method | Compare the ABI of both JARs and the CodeSource |
| Resource returns A even though local class is B | Parent-first resource lookup or custom policy | Distinguish resource vs class search |
| `SecurityException: sealing violation` | A sealed package is defined from an invalid source | Check the manifest and code source |
| JAR cannot be deleted on Windows | Unclosed file handle/JarFile/stream/loader | Use try-with-resources for all of them |
| `ToolProvider.getSystemJavaCompiler() == null` | Running a runtime image without the compiler module | Use a full JDK |
| Stdout contains random paths/IDs | Test log depends on temp directory or identity hash | Only assert stable markers/booleans |

### Mistake: Checking Only File Existence

`Files.exists(A.jar)` and `Files.exists(B.jar)` are not enough. A JAR can be empty, contain the wrong class entry, or contain the same bytecode indistinguishable by output. You need to inspect with `JarFile`, then load the class and confirm the method returns the expected marker.

### Mistake: Believing the JAR File Name Indicates the “Winner”

A file `lib-2.0.jar` is not automatically prioritized by the JVM over `lib-1.0.jar`. With URLClassLoader, parent delegation, URL order, and related indirect sources are what must be analyzed. With Maven/Gradle, the dependency resolution step may also select or exclude versions before the runtime is even configured.

### Mistake: Not Closing JAR Resources

If you leave `JarFile`, `JarInputStream`, or `URLClassLoader` open indefinitely, tests can leave open file handles and affect deleting or updating the fixture on Windows. The example uses try-with-resources and cleans up the temporary directory in `finally`.

## 14. Three Distinctions When Interpreting the Fixture

- **Two JARs with the same entry** is different from **one runtime loader defining two classes with the same name**. Within each loader AB/BA, the class is defined once and cached by identity.
- **URL order** determines the local choice when the parent has not provided the type; parent delegation may select the version from the parent first.
- **Two `Class<?>` objects with the same `getName()`** do not guarantee `==` or a valid cast if the defining loaders differ. Compare the defining loaders and test empirically with `Class.isInstance(...)`.

## 15. Self-Check Exercises

**Question 1.** Why must the fixture compile A and B into two separate output roots?

**Answer:** Because both sources have the same binary name; compiling them together can cause a duplicate-class compile error, whereas we want to create two independent JARs, each containing one definition.

**Question 2.** If URLClassLoader AB has URL[A,B] and the platform parent does not have the fixture class, what does `origin()` return?

**Answer:** `A` according to the normal local search path; the fixture confirms `abOrigin=A`.

**Question 3.** If the URLs are reversed to [B,A] in a **new** loader, what is the result?

**Answer:** `B`, and the class defined by loader BA is a different runtime type from the version defined by AB.

**Question 4.** Child has B.jar while parent has A.jar. Under parent-first, which version does `child.loadClass(BINARY)` return?

**Answer:** Version A defined by the parent, provided the class is valid and the parent can load it.

**Question 5.** If two `Class<?>` objects have equal `getName()`, is `classA == classB` guaranteed?

**Answer:** No; they must have the same defining loader. The demo outputs `sameRuntimeClass=false`.

**Question 6.** Why can `getResources("fixture/label.txt")` see both A and B even though `loadClass` selects version A?

**Answer:** Resource enumeration returns multiple URLs with the same name, whereas class loading selects/records a single definition based on delegation and the loader.

**Question 7.** After `ab.loadClass(BINARY)` has returned class A, if JAR A is modified on disk, will calling the same loader again return the new code?

**Answer:** Not automatically. The loader has already recorded the class, and replacing an open artifact also introduces file handle/state risks; you must use an appropriate loader and fixture lifecycle.

**Question 8.** Two class versions have different APIs. What is the typical runtime error type when consumer bytecode is compiled against A but the runtime selects B, which is missing the method?

**Answer:** `NoSuchMethodError`, if the call to the missing method is resolved/executed by the JVM.

**Question 9.** When a class is loaded from the “wrong JAR”, what information should be logged first?

**Answer:** The actual class, `type.getClassLoader()`, `CodeSource` if available, the parent chain, URL order, and the runtime dependency graph. Not just the file name in the lib directory.

**Question 10.** Why does the fixture not make the two JARs named modules with module-info.java?

**Answer:** Because the goal is to verify URLClassLoader/classpath search; JPMS has different module resolution and split-package rules, which should not be conflated.

## 16. Verification Checklist Before Considering the Test Passed

- [ ] The two source classes have **the same package and class binary name**.
- [ ] The two sources differ in the marker method, making it possible to identify A/B.
- [ ] Compiled independently into JDK 17-compatible bytecode.
- [ ] Packaged `fixture/same/Versioned.class` properly into each JAR.
- [ ] Verified that the JAR files exist and `JarFile.getJarEntry` returns non-null.
- [ ] The AB/BA URL arrays declare explicit order; no environment-dependent wildcards are used.
- [ ] The parent of AB/BA does not have the fixture class.
- [ ] Tested parent A / child B separately to prove parent-first.
- [ ] Verified `Class.getClassLoader()`, binary name, `Class<?> ==`, and `isInstance`.
- [ ] Called the same loader twice to confirm it does not automatically redefine the class.
- [ ] Tested resource enumeration separately from class lookup.
- [ ] Closed JarFile/streams/URLClassLoader and deleted temporary files.
- [ ] Do not force GC/unloading as part of the stdout test.
- [ ] For product tests, verify both the JAR source and the ABI of the actual class.
- [ ] Do not use results based on file name, timestamp, temp path, or hash as the sole assertion.

## 17. Conclusion and References

A fixture with two JARs both defining `fixture.same.Versioned` while returning markers A and B is a very intuitive verification approach: **URL order** matters when a loader searches locally, **parent-first delegation** can override the child's local order, and **two separate defining loaders** can create two runtime classes with the same name that are type-incompatible. Adding a duplicate-named resource helps separate **resource enumeration** from **class definition**, avoiding misdiagnosis based solely on `getResources`.

When building the fixture, you need to compile the two sources separately, package the proper class entry, ensure the parent does not accidentally contain the class, use a consistent JDK version, and perform cleanup. From there, it can be extended into regression tests for JAR collision, plugin isolation, dependency version mismatch, and classloader routing.

Authoritative references:

- Java SE 17 `URLClassLoader` API (URL search, `getURLs`, parent): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 `ClassLoader` API (`loadClass`, `getResources`, delegation): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `JarOutputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarOutputStream.html
- Java SE 17 `JarFile`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- Java SE 17 `JavaCompiler` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Java SE 17 launcher `java` (classpath wildcard): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- JVMS 17 §5.3, *Creation of Classes and Interfaces* (binary name + defining loader): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
