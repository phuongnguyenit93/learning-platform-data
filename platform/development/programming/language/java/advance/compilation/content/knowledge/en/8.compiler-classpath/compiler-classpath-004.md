# Search Order and Conflicts When Multiple Libraries Contain the Same Type in the Java Classpath

In a Java project, a type name such as `org.example.api.Message` can appear in multiple different JAR libraries. If two JARs both contain `org/example/api/Message.class`, the compiler or JVM must locate an appropriate definition according to the configured search paths. When two versions of a class have the same name yet different bytecode or APIs, the program may **run with unintended behavior**, or raise linkage errors such as `NoSuchMethodError`. Understanding search order helps explain why an application compiles cleanly yet fails upon deployment or changes behavior when JAR order is swapped.

This lesson focuses on the **classpath**, where `javac` looks for dependency bytecode and where the standard application class loader looks for classes at runtime. It must also be distinguished from the source path, module path, and custom class-loading mechanisms.

## 1. Classpath Entries and Type Names

A classpath is an **ordered list of entries**. An entry can be a root directory containing `.class` files or a JAR file containing those files. For example:

~~~text
project/
├── classes/
│   └── org/example/app/Main.class
├── libs/
│   ├── alpha.jar
│   │   └── org/example/api/Message.class    (JAR contents)
│   └── beta.jar
│       └── org/example/api/Message.class    (JAR contents)
└── src/
    └── org/example/app/Main.java
~~~

The binary name `org.example.api.Message` maps to the path `org/example/api/Message.class` underneath a **classpath entry root** or the root of a JAR. Therefore:

- If `classes` contains `classes/org/example/app/Main.class`, the classpath root is `classes`.
- If a JAR contains `org/example/api/Message.class` inside, the classpath entry is the **path to the JAR**, not the package path inside the JAR.
- The statement `import org.example.api.Message;` in source only allows using the short name `Message`. It **does not** add the JAR to the classpath.

The classpath is not a package name: `.` joins package segments, `/` or `\` joins directories, while the separator joining **classpath entries** depends on the operating system.

| Platform | Multiple classpath entry separator | Example command |
| --- | --- | --- |
| Linux/macOS | Colon `:` | `java -cp "classes:libs/alpha.jar:libs/beta.jar" org.example.app.Main` |
| Windows | Semicolon `;` | `java -cp "classes;libs\alpha.jar;libs\beta.jar" org.example.app.Main` |

Put quotes around the entire `-cp` value, especially when directory names contain spaces or when running PowerShell, where `;` acts as a command separator if left unquoted.

## 2. The "First Entry Tried First" Rule and Its Limits

In a normal `java -cp ...` run, **when the standard application class loader searches within its own classpath entries**, the list is checked in order. Suppose two libraries both have the class `org.example.api.Message`, and no preceding entry has another copy of that class:

~~~bash
java -cp "classes:libs/alpha.jar:libs/beta.jar" org.example.app.Main
~~~

In the standard situation, `alpha.jar` provides the class looked up before `beta.jar`. Swapping the two JARs can change which class is actually loaded:

~~~bash
java -cp "classes:libs/beta.jar:libs/alpha.jar" org.example.app.Main
~~~

However, **do not** treat classpath order as an all-encompassing rule for all class loading:

1. Standard class loaders **delegate to their parent first**. If the parent already provides the class, the application classpath below does not automatically replace that class.
2. A class already defined in a loader will not automatically change to bytecode from another JAR merely because a new JAR appears.
3. Frameworks/containers or plugin systems may use **custom loaders** with a child-first strategy, loader isolation, or another class-loading scheme. In that case, `-cp` is not enough to predict a class's origin.
4. The Java Platform Module System (JPMS) uses the **module path** and a module resolution mechanism distinct from the regular classpath.
5. `javac`'s rules for finding sources or classes have their own differences when compiling `.java` files directly; do not equate all source file handling with how the JVM picks `.class` files at runtime.

In this hands-on exercise, we deliberately use `java -cp` and the standard application class loader to verify classpath ordering.

## 3. Java 17+ Hands-On: Two JARs with the Same Binary Name

Create three files under the project directory `classpath-order-lab`:

~~~text
classpath-order-lab/
└── src/
    ├── alpha/org/example/api/Message.java
    ├── beta/org/example/api/Message.java
    └── app/org/example/app/Main.java
~~~

**File `src/alpha/org/example/api/Message.java`:**

~~~java
package org.example.api;

public final class Message {
    private Message() {
    }

    public static String text() {
        return "alpha";
    }
}
~~~

**File `src/beta/org/example/api/Message.java`:**

~~~java
package org.example.api;

public final class Message {
    private Message() {
    }

    public static String text() {
        return "beta";
    }
}
~~~

**File `src/app/org/example/app/Main.java`:**

~~~java
package org.example.app;

import org.example.api.Message;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
~~~

Both `Message.java` files declare **the same package, the same class name, and the same method signature `text(): String`**, yet have different bodies. Do not compile both versions of Message into the same output root: each version will sit in its own library.

### Compiling and Running on Linux/macOS

From the `classpath-order-lab` directory:

~~~bash
mkdir -p out/alpha out/beta out/app libs
javac -encoding UTF-8 -d out/alpha src/alpha/org/example/api/Message.java
javac -encoding UTF-8 -d out/beta src/beta/org/example/api/Message.java
jar --create --file libs/alpha.jar -C out/alpha .
jar --create --file libs/beta.jar -C out/beta .
javac -encoding UTF-8 -cp libs/alpha.jar -d out/app src/app/org/example/app/Main.java
~~~

When compiling `Main`, the compiler uses `Message` from `alpha.jar`. Run:

~~~bash
java -cp "out/app:libs/alpha.jar:libs/beta.jar" org.example.app.Main
~~~

Exact stdout:

~~~text
alpha
~~~

Swap the order of the two JARs:

~~~bash
java -cp "out/app:libs/beta.jar:libs/alpha.jar" org.example.app.Main
~~~

Exact stdout:

~~~text
beta
~~~

There is no need to recompile `Main`, because both versions of `Message.text()` have the same binary signature. The class loaded from beta still satisfies the call, yet returns a different value.

### Equivalent Commands on Windows PowerShell

From the `classpath-order-lab` directory:

~~~powershell
New-Item -ItemType Directory -Force "out\alpha", "out\beta", "out\app", "libs" | Out-Null
javac -encoding UTF-8 -d "out\alpha" "src\alpha\org\example\api\Message.java"
javac -encoding UTF-8 -d "out\beta" "src\beta\org\example\api\Message.java"
jar --create --file "libs\alpha.jar" -C "out\alpha" .
jar --create --file "libs\beta.jar" -C "out\beta" .
javac -encoding UTF-8 -cp "libs\alpha.jar" -d "out\app" "src\app\org\example\app\Main.java"
java -cp "out\app;libs\alpha.jar;libs\beta.jar" org.example.app.Main
java -cp "out\app;libs\beta.jar;libs\alpha.jar" org.example.app.Main
~~~

The two `java` commands respectively print:

~~~text
alpha
beta
~~~

Semicolon `;` is the Windows classpath entry separator, instead of `:` on Linux. The commands run from the project root; if run from another directory, relative paths are no longer valid. If paths contain spaces, quote the value completely, for example `-cp "out classes;third party\alpha.jar"`.

### Why Can't the Code Import "Both alpha and beta"?

Both libraries expose **the exact same Java type name**: `org.example.api.Message`. Import only identifies this type name; there is no `import ... as AlphaMessage` syntax to select a class by JAR. When the same class loader must define that binary name, the application cannot use two classes with different bytecode under the **same type/loader identity** simply by writing two import lines.

Solutions depend on the need: unify versions, remove duplicates, relocate to another package, or design two independent class loaders when truly needing to isolate multiple versions.

## 4. Compile Classpath Differs from Runtime Classpath

`javac` and `java` are invoked independently, so they can see different libraries.

| Stage | Classpath | Result |
| --- | --- | --- |
| Compile | `libs/alpha.jar` | `javac` verifies `Message.text()` against the declaration in alpha |
| Runtime A | `out/app:libs/alpha.jar:libs/beta.jar` | In the standard loader, alpha provides `Message` |
| Runtime B | `out/app:libs/beta.jar:libs/alpha.jar` | In the standard loader, beta provides `Message` |

When compiled, bytecode contains **symbolic references** to classes and methods (for example, the binary name of `Message` and descriptor `text:()Ljava/lang/String;`). The file `Main.class` does not hardcode the absolute path `libs/alpha.jar`. At runtime, the JVM must find a matching class definition, then resolve the appropriate method.

Consequently:

- Compiling successfully **does not guarantee** runtime uses the same library version used at compile time.
- Identical class and method names with different implementations can cause **behavioral discrepancies without any exception**.
- Different binary APIs can cause **runtime linkage** errors, not only compile errors.
- The runtime classpath must contain all genuinely needed dependency classes, even if the compiler saw them earlier.

Some build tools distinguish compile dependencies, runtime dependencies, and test dependencies. In a deployment environment, the launcher or container may contribute additional libraries. Inspect the **resolved classpath in the actual environment**, not only the build file or import statements.

## 5. When the beta Version Lacks the Method: NoSuchMethodError

Keep `Main.class` compiled against alpha from the example in section 3, and change **only** the file `src/beta/org/example/api/Message.java` to:

~~~java
package org.example.api;

public final class Message {
    private Message() {
    }

    public static String newApi() {
        return "beta-new";
    }
}
~~~

Then recompile beta separately and recreate the JAR. Linux/macOS:

~~~bash
javac -encoding UTF-8 -d out/beta src/beta/org/example/api/Message.java
jar --create --file libs/beta.jar -C out/beta .
java -cp "out/app:libs/beta.jar:libs/alpha.jar" org.example.app.Main
~~~

`Main.class` requests `Message.text(): String`, but the `Message` definition loaded from beta no longer has the `text()` method. Therefore, the JVM may throw:

~~~text
java.lang.NoSuchMethodError: ... Message.text() ...
~~~

The line above is only an **illustrative error type**; the exact stderr text, descriptor, and stack trace depend on the JDK. This is not fixed stdout of the program.

Try again with alpha first:

~~~bash
java -cp "out/app:libs/alpha.jar:libs/beta.jar" org.example.app.Main
~~~

Stdout is:

~~~text
alpha
~~~

Putting alpha first allows the experiment to run, yet in real systems you should **fix the version inconsistency**, avoiding using classpath order as a workaround to hide dependency conflicts.

If compiling `Main.java` directly against the new beta **without providing alpha**, `javac` will detect that `text()` does not exist. `NoSuchMethodError` is primarily notable when **already-compiled code** runs against a binary definition different from the one used at compile time.

Related errors:

| Error | A typical cause |
| --- | --- |
| `NoSuchMethodError` | Runtime class lacks the method/signature that existed at compile time |
| `NoSuchFieldError` | Runtime class lacks the field referenced by bytecode |
| `IncompatibleClassChangeError` | Incompatible change such as static/instance or class/interface |
| `NoClassDefFoundError` | The JVM needs the class but cannot find it or cannot complete its definition/initialization in the given context |
| `ClassCastException` | Object is incompatible with the cast type; can result from the same class name with different defining loaders |
| No error yet output changes | Binary API remains compatible, yet implementation comes from a different JAR |

Do not infer that every `NoClassDefFoundError` is caused by a missing JAR: in some cases the class failed initialization earlier, or the cause lies in other loading/linking issues. Read the entire cause/stack trace.

## 6. Class Loader Mechanism and Parent Delegation

A useful model for the standard Java launcher:

~~~text
Request: org.example.api.Message
              |
              v
Application class loader
              |
              +--> Parent/platform/bootstrap
              |       If a matching class already exists, usually returns it
              |
              +--> If parent does not satisfy
                      searches entries in application classpath
                      out/app -> libs/alpha.jar -> libs/beta.jar
~~~

This is a conceptual diagram. Parent delegation helps prevent application classes from easily replacing JDK platform classes such as `java.lang.String`. Loader structure, JDK modules, and class lookup have details that vary by Java version; do not use the diagram above as a description of every internal VM API.

**The runtime identity of a class** consists of its binary name and its **defining class loader**. This has two consequences:

1. Two JARs with the same binary name searched by the same loader: the standard loader selects one copy; the remaining copies do not create two separate runtime types inside the same defining loader.
2. Two **different defining loaders** can define two classes with the same binary name, yet they are **two distinct types**. An object from loader A may fail to cast to the class defined by loader B, even though the displayed names are identical.

Web containers, plugin engines, application servers, and hot-reload frameworks may use custom loaders or child-first loading. In such situations, knowing only the `-cp` string is not enough. You must inspect **which loader defined the class**, parent/child relationships, and the search paths the loader actually uses.

A class already defined in a loader does not automatically swap its bytecode when you modify a JAR on disk. To verify a new version with the standard `java` command, start a new process; dedicated instrumentation or reload mechanisms lie outside basic classpath rules.

## 7. Determining Where a Class Was Actually Loaded From

### 7.1. CodeSource and Class Loader

Add to the `main` method of `Main.java`:

~~~java
System.out.println(
        Message.class.getProtectionDomain()
                .getCodeSource()
                .getLocation()
);
System.out.println(Message.class.getClassLoader());
~~~

Then recompile `Main.java` with alpha and run the classpath-order-swapping commands from section 3. With standard JARs, `getLocation()` typically returns a URL such as `file:/.../libs/alpha.jar` or `file:/.../libs/beta.jar`. **There is no fixed output** here because the path depends on the environment and the class loader representation varies by JDK.

`getCodeSource()` can return `null` for some classes/loaders; if applied to classes other than in the experiment, handle null when building diagnostic tools. The CodeSource value is useful evidence, yet not a guaranteed API across all class-loading mechanisms.

### 7.2. Class Loading Logs

Java 17 on HotSpot supports unified logging for class loading:

~~~bash
java -Xlog:class+load=info -cp "out/app:libs/alpha.jar:libs/beta.jar" org.example.app.Main
~~~

Windows:

~~~bat
java -Xlog:class+load=info -cp "out\app;libs\alpha.jar;libs\beta.jar" org.example.app.Main
~~~

The log output will have many lines for JDK classes and application classes. Search for `org.example.api.Message` and the `source` information of the corresponding entry. Line count and log destination (stdout/stderr or a file if configured) depend on the JVM, so there is no single "exact stdout" for logging-enabled commands.

### 7.3. Inspecting JAR Contents and APIs with javap

~~~bash
jar --list --file libs/alpha.jar
jar --list --file libs/beta.jar
javap -classpath libs/alpha.jar org.example.api.Message
javap -classpath libs/beta.jar org.example.api.Message
~~~

`jar --list` shows whether the class file is really inside the JAR. `javap` displays the public signature of the specified class, letting you compare the alpha and beta versions. If you need to inspect symbolic references in `Main.class`, additionally use `javap -c -verbose -classpath out/app org.example.app.Main` and read the bytecode/constant pool; this is a diagnostic operation and does not modify bytecode.

Do not confuse "the JAR contains the file" with "the JVM loaded the file from that JAR": a library can be on the classpath yet shadowed by a preceding entry.

## 8. Classpath Wildcards: Do Not Rely on Random Ordering

Java supports classpath wildcards:

~~~bash
java -cp "out/app:libs/*" org.example.app.Main
~~~

The pattern `libs/*` includes matching JAR/ZIP files located **directly** in the `libs` directory. It does not recursively traverse subdirectories and is not an arbitrary glob like `libs/**/*.jar`. In Bash, quote the pattern to prevent the shell from expanding it into arguments before Java receives it.

**The order in which JARs are expanded from a wildcard is not guaranteed by Java.** Do not rely on filenames like `01-alpha.jar`, `02-beta.jar` or filesystem listing order to decide which version of a class is used. If you need to demonstrate order, list JARs explicitly:

~~~bash
java -cp "out/app:libs/alpha.jar:libs/beta.jar" org.example.app.Main
~~~

~~~bat
java -cp "out\app;libs\alpha.jar;libs\beta.jar" org.example.app.Main
~~~

Even when explicit ordering makes an experiment's outcome predictable, the **sustainable solution** is to resolve duplicate classes or incompatible versions in the dependency graph. Wildcards introduce extra variables when files in the directory change, build machines change, or operating systems change.

## 9. Common Duplicate Class Scenarios

### 9.1. Two Versions of a Library in the Same Application

For example, `logging-core-1.jar` and `logging-core-2.jar` both contain `org.example.logging.Logger`. The standard Java classpath **does not automatically select the newer version** based on filename or version number. It searches for classes according to the loader mechanism and effective classpath.

### 9.2. Transitive Dependencies

An application depends on A and B; A needs an older version of C, while B needs a newer version of C. Maven/Gradle have their own version selection/dependency resolution mechanisms. The file actually chosen for the runtime classpath may not match intuition from the first dependency declaration. Inspect the **resolved dependency graph**, not just the build file.

### 9.3. Project Output Shadowing a Library

If `out/app` also contains `org/example/api/Message.class` and is placed before `libs/alpha.jar`, the class from output can win. This is an easy mistake to make when stale classes remain or bytecode is copied into output. Inspect output contents, perform controlled clean builds, and avoid packaging vendor source/bytecode into the application classpath root unnecessarily.

### 9.4. Fat JARs, Shaded JARs, and Applications with Nested JARs

An uber JAR can bundle bytecode from many dependencies. When encountering two duplicate entries at the same path, the packaging tool may pick one copy, drop, overwrite, or report an error depending on its policy. A Spring Boot executable JAR with nested libraries and its own launcher also does not necessarily behave identically to a simple `java -cp` string.

**Shading relocation** changes the package of certain classes to avoid duplicate binary names, yet you must account for reflection, resource paths, ServiceLoader, serialization, and native integration. Do not merely rename classes mechanically.

### 9.5. Tests, Plugins, and Application Servers

Test runtime may add test classes or separate dependencies; servers may add shared libraries; plugin frameworks may use child-first loaders. Thus the same program can run differently across IDE, tests, CLI, and production.

Diagnostics should record: JDK version, launcher, runtime classpath, classloader identity, source of the loaded class, and packaged JAR versions.

## 10. JPMS Module Path Differs from Flat Classpath

Since Java 9, the **Java Platform Module System** allows named modules with `module-info.java`, `requires`, and `exports` declarations. The module path has different module/package resolution rules from the classpath.

Syntax illustration example (only runs if valid modules exist):

~~~bash
java --module-path "mods:external-mods" --module org.example.app/org.example.app.Main
~~~

Do not treat this as a direct equivalent to the `java -cp` example in section 3. With JPMS:

- The regular classpath provides classes in the **unnamed module**.
- The module path is the search path for resolved modules.
- **Split packages** across named modules can cause module resolution/visibility errors, rather than silently picking one class by "first JAR".
- Modules of the same name, automatic module naming, and reading/exporting packages require analyzing the specific module graph.
- Parent delegation and JDK platform classes still take effect; you cannot arbitrarily override JDK classes by putting a JAR at the front of the application classpath.

When an error states `module ... reads package ... from both ...`, inspect the module configuration rather than just swapping JAR order.

## 11. Duplicate Resource Names Are Not the Same as Duplicate Class Names

Two JARs can both contain a resource:

~~~text
config/default.properties
META-INF/services/org.example.spi.Plugin
~~~

Resources do not follow class definition under the exact same mechanism. For example, `ClassLoader.getResources("config/default.properties")` can return **multiple URLs**. Illustrative code placed inside a method declared to handle `IOException`:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
java.util.Enumeration<java.net.URL> urls =
        loader.getResources("config/default.properties");
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
~~~

The snippet above **is not a standalone program**; to use it, place it inside a method with `throws java.io.IOException` or exception handling. `getResource` returns one matching resource, whereas `getResources` enumerates multiple resources following class loader rules.

`META-INF/services` is often used by `ServiceLoader` to discover providers. When multiple JARs supply provider metadata, multiple providers may be discovered; do not assume only the first JAR is used as when picking a binary class name. Merging service configurations in a fat JAR must be handled intentionally.

## 12. Evidence-Based Conflict Diagnostic Procedure

When encountering wrong behavior or runtime linkage failure:

1. **Identify the affected binary name** (package + class name, including nested types when present).
2. **Obtain the actual compile classpath** used and the API seen by the compiler. Inspect source and bytecode/signatures using `javap`.
3. **Obtain the exact runtime classpath** from the launcher, build artifact, container, or run configuration. Check entry separators per OS.
4. **Trace the class actually loaded** using `-Xlog:class+load=info`, CodeSource if available, or information from the class loader.
5. **Find all copies** across JARs and output directories: use `jar --list` or duplicate-class checking tools.
6. **Compare API and implementation** between compile and runtime versions. Are methods/fields removed, changed between static/instance, different versions, or different behavior?
7. **Eliminate the conflict at the dependency level** by choosing a consistent version, removing redundant dependencies, using locks/constraints, or appropriate isolation.
8. **Re-verify** in a production-like environment and test behavior rather than only looking at `javac`'s exit code.

Some Gradle commands often useful in projects with a wrapper and the `runtimeClasspath` configuration:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency example-library --configuration runtimeClasspath
~~~

On Windows:

~~~bat
gradlew.bat dependencies --configuration runtimeClasspath
gradlew.bat dependencyInsight --dependency example-library --configuration runtimeClasspath
~~~

`example-library` is the placeholder for the dependency name to inspect, and configurations depend on the plugin/project. Maven has `mvn dependency:tree` when Maven and the appropriate dependency plugin are available. These commands help read the **resolved dependency graph**; with special loader systems, you still must check which class is loaded at runtime.

### Quick Identification Table

| Symptom | Hypothesis and action |
| --- | --- |
| Swapping JAR order changes stdout | Duplicate binary class with compatible API yet different implementation; check class origin |
| `NoSuchMethodError` in production | Compile/runtime API mismatch; inspect method descriptor and actual loaded JAR |
| `NoSuchFieldError` | Runtime class lacks the compatible field |
| `ClassCastException` between "same-named" objects | Check defining class loader; may be two classes with different runtime identities |
| `lib/*` produces nondeterministic results at runtime | Wildcard JAR order is not guaranteed; eliminate duplicate classes, use consistent dependencies |
| `package ... does not exist` at compile time | Missing class/JAR on compile classpath or wrong source path |
| `Could not find or load main class ...` | Wrong classpath root/main FQN, not necessarily a duplicate class |
| Tests pass, application fails | Compare test/runtime dependencies and custom loaders |
| Error "module reads package from both" | Focus on investigating module graph/split package; do not apply simple classpath rules |

## 13. Self-Check Exercises

**Exercise 1.** On Linux, `classes:libs/beta.jar:libs/alpha.jar` is the runtime classpath; both JARs contain `org.example.api.Message`, and the standard class loader does not find this class from its parent or `classes`. Which version wins?

**Answer:** Beta is searched before alpha on the application classpath. If the signature is compatible, the result of `Message.text()` in the experiment is `beta`.

**Exercise 2.** `Main.class` was compiled against alpha having method `text()`; runtime loads beta which removed `text()`. Does the compiler automatically detect the runtime error?

**Answer:** Not guaranteed. The compiler used alpha's API and succeeded. When the JVM resolves the method on beta, it may throw `NoSuchMethodError`. Recompiling source against the new beta will catch the missing method immediately at compile time.

**Exercise 3.** Is `libs/01-alpha.jar` guaranteed to beat `libs/02-beta.jar` when the classpath only says `libs/*`?

**Answer:** No. Wildcard expansion order is unspecified. Filenames are not a versioning policy.

**Exercise 4.** A `Greeting` with the same binary name is loaded by two different defining class loaders. Are they definitely the same type?

**Answer:** No. Runtime class identity also depends on the defining class loader; two types may not be castable to each other.

**Exercise 5.** Why does `jar --list --file libs/alpha.jar` showing `Message.class` still not prove alpha is being used?

**Answer:** Another preceding entry may supply the class, or the class may be defined by a parent/custom loader. You must check the source of the loaded class, not just its presence in the JAR.

**Exercise 6.** If there are two `META-INF/services/...` files in two JARs, is the second one dropped under the same duplicate-class rule?

**Answer:** Do not infer that. Service provider metadata can be enumerated/read from multiple resources; you must consider `ServiceLoader` and the corresponding module/loader.

## Key Takeaways

- **The classpath is ordered**; within the scope of the standard application class loader, the first entry supplying a binary class name is typically chosen.
- **Parent delegation, custom class loaders, and JPMS** can make merely looking at `-cp` insufficient.
- **Different compile and runtime classpaths** can cause different behavior or linkage errors such as `NoSuchMethodError`, even if the source compiled cleanly.
- **The wildcard `libs/*` does not guarantee JAR order**; do not use file renaming to solve duplicate classes.
- **Inspect evidence**: `jar --list`, `javap`, `-Xlog:class+load=info`, CodeSource, class loaders, and the resolved dependency graph.
- **Resolve conflicts at the dependency/version level** or via intentional isolation; do not assume swapping classpath order is a long-term fix.