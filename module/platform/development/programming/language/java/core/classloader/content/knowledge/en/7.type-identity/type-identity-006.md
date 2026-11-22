# Package-Private Access Across Classes Defined by Different ClassLoaders

## 1. Scenario and Core Answer

Suppose two Java classes both declare `package lab.boundary;`. When compiled together, one class can call a **package-private** method (having no `public`, `protected`, or `private` modifier) of the other class. However, if at runtime the two classes are **defined by two different ClassLoaders**, that package-private access is **no longer valid**, even though the package name strings are identical.

The key condition is not merely the *package name in source code* but the **run-time package**. According to the JVM Specification, the run-time package of a class or interface is determined by:

1. **Package name**.
2. **The ClassLoader that defined the class** (defining loader).

Therefore:

~~~text
Compile time:
  Host.java  -> package lab.boundary
  Guest.java -> package lab.boundary
  => javac allows Guest to call Host.secret() (package-private)

Runtime:
  Host  -> package lab.boundary, defining loader = L_parent
  Guest -> package lab.boundary, defining loader = L_child

  Same package name                       : TRUE
  Same run-time package identity          : FALSE
  Guest calls Host.secret() (package-private): IllegalAccessError
~~~

This is a **JVM-level access rule**, not a bug where the compiler arbitrarily changes the rules. The ClassLoader forms part of the type identity boundary and the package boundary at runtime.

**After this lesson, you should be able to:**

- Distinguish between a *source-level package* and a JVM *run-time package*.
- Explain why identical package names with different defining loaders can cause `IllegalAccessError`.
- Interpret `getPackageName()` and `getClassLoader()` evidence in a standalone Java 17+ program.
- Distinguish access control errors during **compilation**, **linking/resolution**, and **reflection**.
- Design APIs between a host and plugins when each side has its own loader.

## 2. What Does Package-Private Mean at Each Stage?

### 2.1. In Source Code and at Compile Time

A member declared without an access modifier has **package access**, commonly called *package-private* or *default access*:

~~~java
package lab.boundary;

public class Host {
    static String secret() { return "parent-only"; } // package-private
    public static String open() { return "public-ok"; } // public
}
~~~

Another class in the same source package can call `Host.secret()` if all other requirements are met:

~~~java
package lab.boundary;

public class Guest {
    public static String callPrivate() {
        return Host.secret();
    }
}
~~~

The two snippets above are **two separate illustrative Java files**, not a single standalone file. If `Guest.java` is compiled with `Host.class` on the compile classpath, `javac` sees that both are in `lab.boundary` and permits the call. However, the compiler **cannot know for certain** which loaders will define the two classes in every future run.

If you change the package of `Guest` to `other.pkg` while still calling `Host.secret()`, `javac` will report an access error immediately at compile time. That is a **different** scenario from this lesson: here, the source code **compiles cleanly**, but runtime loading alters the package boundary.

### 2.2. In the JVM: Same Name String Is Not Enough

JVM Specification `5.3` defines a runtime class by **binary name + defining loader**, and a run-time package by **package name + defining loader**.

Notation:

~~~text
Host:
  binary name     = lab.boundary.Host
  package name    = lab.boundary
  defining loader = L_parent
  run-time package = (lab.boundary, L_parent)

Guest:
  binary name     = lab.boundary.Guest
  package name    = lab.boundary
  defining loader = L_child
  run-time package = (lab.boundary, L_child)
~~~

If `L_parent != L_child`, the two run-time packages are **different**. Package-private access between the two classes is not permitted simply because `getPackageName()` returns the same string.

This also explains a familiar issue in plugins/containers: separate loaders ensure type isolation, but that isolation can break package-private calls that the compiler allowed when the sources were in the same package.

### 2.3. Defining Loader and Initiating Loader Are Not the Same

- **Defining loader** is the loader that actually **defines** the class, directly or through the corresponding JVM mechanism. `SomeClass.class.getClassLoader()` reflects the defining loader (which may be `null` for a bootstrap-defined class).
- **Initiating loader** is the loader that **initiates the lookup** of the class, and it may delegate the definition to its parent.

For example: `L_child.loadClass("lab.boundary.Host")` may return `Host` **defined by `L_parent`** because of parent-first delegation. When determining the run-time package, use the **defining loader** of each class; do not draw conclusions based on the fact that "the child requested the load."

In the hands-on example below, the parent defines `Host` while the child defines `Guest`. Even though the child can find `Host` through the parent, they still belong to two different run-time packages.

## 3. How Does the JVM Detect an Access Violation?

### 3.1. Checking When Resolving a Symbolic Reference

In the bytecode of `Guest.callPrivate()`, the call `Host.secret()` is a reference to a method. When the JVM performs **resolution** of that reference, it checks whether the target method is accessible from the calling class.

The key rule in [JVMS `5.4`.4](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.4):

- `public` method: accessible if its declaring class is also accessible and relevant rules are satisfied.
- `protected`: follows subclass/same run-time package rules and additional conditions.
- No access modifier (*package-private*): allowed if the **class declaring the member** and the **accessing class** belong to the **same run-time package**.
- `private`: based on a valid class/nest relationship, not merely sharing a package.

When method access is invalid during resolution, the JVM throws **`java.lang.IllegalAccessError`**. This error is a `LinkageError` (under `Error`), **not** reflection's `IllegalAccessException`.

**Time of observation:** Under the specification, the JVM is permitted to resolve certain references eagerly or lazily. In this specific example, `IllegalAccessError` appears when executing the call `Guest.callPrivate()`. You should not assert that every JVM will always throw the error at the exact same opcode if more complex linking scenarios occur.

### 3.2. Not a "Class Not Found" Error

Both classes in the example may have already been loaded successfully. Finding `Host` and `Guest` does not guarantee that the statement `Host.secret()` is allowed to execute. Distinguish carefully:

| Symptom | Meaning |
|---|---|
| `ClassNotFoundException` | An API requested to find a class by name, but the loader could not find the class |
| `NoClassDefFoundError` | The JVM lacks or cannot use a required class definition at runtime; multiple possible causes |
| `IllegalAccessError` | The JVM found the definition, but the **access check** during linking/resolution failed |
| `IllegalAccessException` | The reflection API reports that an access was denied; this is a checked exception belonging to reflection |
| `InaccessibleObjectException` | Can occur when trying to bypass access checks using deep reflection and getting blocked, especially across module boundaries |
| `ClassCastException` | Invalid runtime cast; in plugins, can happen due to two classes with the same name but different defining loaders |

The distinction between `IllegalAccessError` and `IllegalAccessException` is especially useful: one is the result of a **JVM bytecode access check**, while the other typically arises from **reflection** operations.

## 4. ClassLoader Diagram of the Example

Intentional layout:

~~~text
Application / System ClassLoader (parent)
  |
  +-- defines lab.boundary.Host
  +-- defines Launcher
  |
  v  (parent-first delegation)
URLClassLoader child
  |
  +-- does not redefine Host
  +-- defines lab.boundary.Guest from build/guest

Guest -> Host.open()   : valid (public)
Guest -> Host.secret() : IllegalAccessError (package-private)
~~~

**Decisive point:** `Guest.class` is **not** on the parent's runtime classpath; conversely, `Host.class` is **only** in the output directory intended for the parent. If you accidentally add `build/guest` to the system classpath as well, parent-first delegation may cause **both Host and Guest to be defined by the parent**, causing the test to no longer demonstrate the intended loader boundary.

The example uses the standard `URLClassLoader` and a `Launcher` class. No custom subclass or external library is required.

## 5. Java 17+ Hands-On: Standalone Example to Verify the Error

### 5.1. Create the Directory Tree

From an empty directory of your choice (here called `demo`), create the following source tree:

~~~text
demo/
  src-host/
    lab/
      boundary/
        Host.java
  src-guest/
    lab/
      boundary/
        Guest.java
  src-launcher/
    Launcher.java
  build/
    host/              # output of Host and Launcher
    guest/             # output of Guest
~~~

You can create the `src-*` and `build/*` directories via IDE/file explorer or command line before compiling. The two outputs must be **separate**: the program will run with a system classpath containing **only** `build/host`.

### 5.2. File `src-host/lab/boundary/Host.java`

~~~java
package lab.boundary;

public class Host {
    static String secret() {
        return "parent-only";
    }

    public static String open() {
        return "public-ok";
    }
}
~~~

`Host` is a **public class**, so a guest in another run-time package can reference the class itself. However, `secret()` has no modifier: it only allows code belonging to the same **run-time package** to call it. The public `open()` method serves as a control check.

### 5.3. File `src-guest/lab/boundary/Guest.java`

~~~java
package lab.boundary;

public class Guest {
    public static String callPrivate() {
        return Host.secret();
    }

    public static String callPublic() {
        return Host.open();
    }
}
~~~

At compile time, `javac` sees both classes in the same source package `lab.boundary` and allows both calls. The violation only arises after `Guest` is defined by a different loader at runtime.

### 5.4. File `src-launcher/Launcher.java`

~~~java
import java.lang.reflect.InvocationTargetException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import lab.boundary.Host;

public class Launcher {
    public static void main(String[] args) throws Exception {
        URL source = Path.of("build/guest").toUri().toURL();

        try (URLClassLoader child = new URLClassLoader(
                new URL[] { source },
                Host.class.getClassLoader())) {

            Class<?> guest = Class.forName(
                    "lab.boundary.Guest", true, child);

            System.out.println("samePackageName="
                    + Host.class.getPackageName()
                            .equals(guest.getPackageName()));

            System.out.println("sameLoader="
                    + (Host.class.getClassLoader()
                            == guest.getClassLoader()));

            System.out.println("public="
                    + guest.getMethod("callPublic").invoke(null));

            try {
                guest.getMethod("callPrivate").invoke(null);
            } catch (InvocationTargetException ex) {
                System.out.println("failure="
                        + ex.getCause().getClass().getSimpleName());
            }
        }
    }
}
~~~

**Structural explanation:**

1. `Path.of("build/guest").toUri().toURL()` adds the directory containing `Guest.class` to the search path of `URLClassLoader`.
2. The parent is `Host.class.getClassLoader()`: in this execution setup, that is the system/application loader, which already defined `Host`.
3. Parent-first delegation searches for `lab.boundary.Guest` in the parent first; because the parent does not have `Guest.class`, the child loader then searches in `build/guest` and defines `Guest`.
4. `Class.forName(..., true, child)` locates and initializes `Guest`. `Guest` has public methods; reflection is used here solely to invoke two methods of a class on which `Launcher` has no compile-time dependency.
5. `Guest.callPublic()` successfully calls `Host.open()`: `Host` is public, `open()` is public; both classes belong to the unnamed modules of their respective loaders, which satisfies public access here.
6. `Guest.callPrivate()` triggers `IllegalAccessError` when linking the `Host.secret()` call. Reflection wraps the error thrown by the invoked method in `InvocationTargetException`; the code extracts `getCause()` and prints the simple name of the underlying error.

### 5.5. Compile and Run Properly

From the `demo` directory, create the two output directories. On Bash:

~~~sh
mkdir -p build/host build/guest
javac --release 17 -d build/host src-host/lab/boundary/Host.java src-launcher/Launcher.java
javac --release 17 -cp build/host -d build/guest src-guest/lab/boundary/Guest.java
java -cp build/host Launcher
~~~

On Windows PowerShell, the equivalent commands are:

~~~powershell
New-Item -ItemType Directory -Force build/host, build/guest | Out-Null
javac --release 17 -d build/host src-host/lab/boundary/Host.java src-launcher/Launcher.java
javac --release 17 -cp build/host -d build/guest src-guest/lab/boundary/Guest.java
java -cp build/host Launcher
~~~

Mandatory condition: **do not add `build/guest` to the `java -cp build/host Launcher` command**. Keep the working directory at `demo` so that the `build/guest` path in `Launcher` points to the right location.

**Verified stdout with JDK 21 compiled at `--release 17`:**

~~~text
samePackageName=true
sameLoader=false
public=public-ok
failure=IllegalAccessError
~~~

The output has four layers of meaning:

- `samePackageName=true`: both classes declare the exact same package name string.
- `sameLoader=false`: their defining loaders are **different**, so their run-time packages are different.
- `public=public-ok`: the class is still found and the public method works; it is not a missing class or path error.
- `failure=IllegalAccessError`: the package-private call is rejected by the JVM; the fact that `javac` previously allowed it does not guarantee runtime access.

There is no need to print `URLClassLoader.toString()` because the loader's string representation is runtime-dependent. Comparing loader objects with `==` is more meaningful.

### 5.6. Inspecting Bytecode to See Where the Error Occurs

~~~sh
javap -classpath build/guest -c lab.boundary.Guest
~~~

In `callPrivate()`, `javap` shows an `invokestatic` instruction pointing to `lab/boundary/Host.secret`. The bytecode syntax was generated successfully at compile time; the error occurs when the JVM processes access control for the method reference at runtime.

A control experiment: if you put `Guest.class` on the **system classpath** alongside `Host.class` before launching, the parent-first loader can define both and the package-private call may succeed. In that case, re-check `sameLoader`: if it is `true`, the experiment no longer separates the two run-time packages. That is **a different runtime environment**, not a "quick fix" for a plugin system that wants loader isolation.

## 6. Distinguishing Compile-Time Package from Run-Time Package

The Java compiler inspects the `package lab.boundary;` declarations and the compile-time classpath to decide whether to permit a package-private call. At runtime, the JVM links symbolic references and checks **runtime package = (package name, defining loader)**; two equal package names can still belong to two different runtime packages.

Therefore, in the experiment above, the `Guest` source compiles, yet the call to `Host`'s package-private member fails with `IllegalAccessError` when the classes are defined by different loaders. Successful compilation does not guarantee that runtime access checks will succeed.

## 7. Why Do Frameworks and Plugins Frequently Encounter This?

Plugin systems, application servers, and containers often create a ClassLoader per plugin/application. They may:

- Share an API in the parent loader.
- Load plugin implementations through child loaders.
- Have two dependency versions with the same package under different child loaders.
- Load some classes from the parent and others from the child, even though the original build placed them in the same package.

Example:

~~~text
Parent loader:
  api/Service.class
  shared/internal/Helper.class

Plugin loader A:
  shared/internal/PluginTask.class

Plugin loader B:
  shared/internal/AnotherTask.class
~~~

If `PluginTask` directly calls `Helper.packagePrivateMethod()` (assuming both packages are `shared.internal`), the call can compile cleanly when the build puts both sources in the same package. But at runtime `Helper` is defined by the parent while `PluginTask` is defined by plugin loader A, so they have **different run-time packages**, leading to an access error during resolution.

For Plugin A and Plugin B, even two classes with the same name in two separate loaders are **two different runtime types**, which can additionally cause `ClassCastException` if an implementation type is used as a shared API. That is a distinct issue, but it shares the same root cause: **the defining loader is part of type and package identity**.

## 8. Designing Fixes That Address the Root Cause

### 8.1. Use a Public Contract for Loader Boundaries

When you **intentionally** separate classes across multiple loaders, the sustainable approach is to expose a public contract for the required communication:

~~~java
package lab.api;

public interface Service {
    String execute();
}
~~~

The snippet above illustrates an **API contract**, not a standalone runnable program. Place this interface on the shared classpath/JAR defined by the parent loader, then let plugins define implementations and communicate through the interface's `public` methods.

Benefits:

- Code from different loaders does not need to call each other's package-private members.
- The host and plugins reference **the same `lab.api.Service` Class object** defined by the parent loader, avoiding type identity mismatches.
- Plugin implementations and internal dependencies can remain isolated.

If you must expose a behavior, consider a small, controlled `public` API, a public adapter/bridge, or changing how classes are partitioned between parent and child. Do not arbitrarily turn every internal method into `public` just to mask a classloader issue; `public` visibility is part of your API contract and requires careful consideration.

### 8.2. If Package-Private Is Truly Needed, Place Classes in the Same Run-Time Package

If two classes **genuinely must** share package-private logic, they must have the same package name **and** the same defining loader at runtime. For multi-loader applications, this may require grouping them on the same side of the loader boundary or redesigning the module/plugin architecture.

However, arbitrarily changing the parent loader or adding JARs to the classpath can cause dependency conflicts, duplicate classes, or broken isolation. The success condition must be verified via `getClassLoader()` for **both classes** after deployment.

### 8.3. Reflection and Opening Modules Do Not Remove the Run-Time Package Requirement

- `setAccessible(true)` affects **reflective access** according to its own rules; it **does not turn** a bytecode `invokestatic Host.secret()` into a valid package-private call across two run-time packages.
- With **named modules**, `requires`, `exports`, and `opens` govern the use of public types and deep reflection. `exports` or `opens` **does not grant** package-private access across two different defining loaders.
- Do not replace package-private with `protected` assuming "a subclass in another loader will get full access": `protected` has its own subclass, receiver, and runtime package rules that must be analyzed for each call site.

## 9. Diagnosing the Error in Real Projects

When you see an `IllegalAccessError` pointing to a method/field that looks like it is in the "same package":

1. **Read the exact caller and target member.** The stack trace usually includes the referencing class name, the member name, and on modern JVMs, possibly loader/module information.
2. **Determine the member's access modifier** in the running bytecode, not just in edited source code. Use `javap -p` or `javap -c -p`, and confirm the exact JAR/version.
3. **Check the defining loader of both classes** using `SomeClass.class.getClassLoader()` or logs/class-loading diagnostics. Comparing `getPackageName()` strings alone is not enough.
4. **Inspect parent delegation and class sources.** If the parent already has the same class, the child-first/parent-first policy and the actual class source determine where the class is defined.
5. **If the application uses JPMS**, also check `clazz.getModule()`, readability, and `exports`/`opens`. Those rules can also cause access errors, though from a different root cause than split package-private runtime packages.
6. **Try a minimal reproduction.** Two classes in the same package, output to two directories, using separate system/child loaders, letting a public call succeed and then attempting the package-private call. This proves the access issue without depending on the entire framework.

### Quick Elimination Questions

| Symptom | First Thing to Investigate |
|---|---|
| `javac` reports `is not public ... cannot be accessed from outside package` | Package/access right in source code, before runtime |
| Runtime `IllegalAccessError` on a package-private member | Defining loader and run-time package; then check version/modifiers |
| `IllegalAccessError` on a `public` type in a named module | Module readability/`exports` |
| `IllegalAccessException` when calling `Method.invoke` | Reflection permissions; may need `canAccess` or a public API |
| `ClassCastException` when class names match | Two `Class` objects with the same name but different defining loaders |
| `ClassNotFoundException` | Class/JAR source, classpath, and the loader being passed |
| `NoSuchMethodError` | ABI/version mismatch; runtime dependency differs from compile time |

Do not treat all these errors by blindly adding `--add-opens`, `--add-exports`, or `setAccessible(true)`. Identify the root cause first, because those flags do not change a class's defining loader or run-time package.

## 10. Common Misconceptions

1. **"Both files have `package lab.boundary;`, so package-private will always work."** False at runtime if the defining loaders differ.
2. **"`Guest.class.getPackageName().equals(Host.class.getPackageName())` is sufficient proof."** False; you must also compare defining loaders.
3. **"The child can load `Host` through the parent, so Host belongs to the child's package."** False; the initiating loader does not change `Host`'s defining loader.
4. **"If compilation succeeds, the JVM cannot throw an access error."** False; the compiler relies on the compile-time view, while the JVM verifies runtime access.
5. **"`IllegalAccessError` is the same as `IllegalAccessException`."** False; their error category, origin, and investigation steps differ.
6. **"Just using `setAccessible(true)` fixes a bytecode call."** False; reflection does not rewrite the access check at resolution for a direct call.
7. **"A public class means all of its members are public."** False; `Host` being public does not make `Host.secret()` public.
8. **"Just changing classpath order does not require considering isolation."** False; loading order/source can change the defining loader and create other errors.
9. **"Simply adding `opens` on a JPMS package makes cross-loader package-private valid."** False; module access and run-time package are two separate conditions.
10. **"`NoClassDefFoundError` is the inevitable result when using package-private across different loaders."** False; this example finds both classes and throws **`IllegalAccessError`**.

## 11. Self-Check Questions

1. Which two components determine a run-time package? Do two classes with the same package name but different defining loaders share the same run-time package?
2. Why can `javac` accept `Guest.callPrivate()` while the JVM throws `IllegalAccessError`?
3. If `L_child.loadClass("lab.boundary.Host")` successfully delegates to the parent, which loader's run-time package does `Host` belong to?
4. In the Section 5 example, why is `samePackageName=true` while `sameLoader=false`?
5. Why does `Guest.callPublic()` succeed right before `Guest.callPrivate()` fails?
6. If `build/guest` is accidentally added to the system classpath, what can happen to the loader defining `Guest`? Why does that invalidate the experiment's proof?
7. How do `IllegalAccessError` and `IllegalAccessException` differ?
8. Why should changing a package-private member to `public` be accompanied by API contract control rather than done indiscriminately?
9. If a host and a plugin need to exchange objects, why is a shared public interface defined by the parent loader usually appropriate?
10. With named modules, do `exports` or `opens` allow two classes with different defining loaders to share a package-private member solely because they have the same package name?
11. How do you distinguish an access error caused by split package-private from a `NoSuchMethodError` caused by a version mismatch?
12. In a log showing two classes in the same package with different ClassLoaders, what is the first question you should check when a package-private call occurs?

**Completion criteria:** accurately predict the example's stdout, prove that two run-time packages differ despite having the same package string, explain when `IllegalAccessError` occurs, and propose an appropriate public API boundary between host and plugin.

## 12. Standard References

- [JVMS Java SE 21 `5.3` — Creation of Classes and Interfaces](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): type identity and run-time package by package name + defining loader.
- [JVMS Java SE 21 `5.4.4` — Access Control](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.4): access checks for classes, fields, and methods; when `IllegalAccessError` is thrown.
- [JLS Java SE 21 `6.6` — Access Control](https://docs.oracle.com/specs/jls/se21/html/jls-6.html#jls-6.6): accessibility concepts at the Java language level, including package access.
- [Java SE 21 `ClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): defining/initiating loader, parent delegation.
- [Java SE 21 `URLClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): finding and defining classes from URLs/directories/JARs.
- [Java SE 21 `InvocationTargetException` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): reflection wrapping exceptions/errors thrown by an invoked method.

The example was compiled with `--release 17` and run on JDK 21 to verify stdout; the content uses standard rules applicable to Java 17+. The scope of this lesson is package-private access across defining loaders, without assuming any specific framework or plugin system.