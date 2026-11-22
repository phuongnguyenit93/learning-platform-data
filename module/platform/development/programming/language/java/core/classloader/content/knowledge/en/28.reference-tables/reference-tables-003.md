# Error Table by Java Class Loading, Linking, Initialization, and Usage Phase

When a Java application reports an error involving a class, classloader, dependency JAR, framework, plugin, or reflection, **looking at the exception name and immediately modifying the classpath** is often not enough. A class goes through several distinct JVM steps: **loading**, **linking** (verification, preparation, resolution), **initialization**, and only then **class/object/method usage**. Each phase has typical errors with different causes and remedies.

For example:

- `ClassNotFoundException`: code **explicitly looks up a class by name**, but the chosen loader cannot find it.
- `NoClassDefFoundError`: the JVM needs a class definition that cannot be found via a bytecode reference, or the class previously failed initialization.
- `VerifyError`: bytecode fails verification checks.
- `NoSuchMethodError`: the symbolic method reference does not match a method on the **version of the class actually loaded**.
- `ExceptionInInitializerError`: static initialization runs and throws a non-`Error` exception.
- `ClassCastException`: an object cannot be cast to the requested runtime type, sometimes because the types share the same binary name but have **different defining class loaders**.

This article is a phase-by-phase **reference**, with error tables, Java 17+ examples reproducing common cases, diagnostic commands, and a workflow for isolating root causes. The tables describe the **causal phase**; the JVM is permitted to perform certain linking/resolution operations early or late, so **the moment a stack trace raises an error may not match the exact step the author expects**.

## 1. JVM Class Loading Phase Map

According to JVMS §5, the high-level flow is:

~~~text
    Source .java / library dependency / bytecode generator
                          |
                        javac
                          |
                     Class file bytes
                          |
                          v
                   (1) LOADING
           ClassLoader.loadClass/findClass
                          |
       find class representation, define runtime Class
                          |
                          v
                   (2) LINKING
         +----------------+------------------+
         |                |                  |
     Verification      Preparation        Resolution
     bytecode rules    static storage     symbolic refs
         |                |                  |
         +----------------+------------------+
                          |
                          v
                 (3) INITIALIZATION
             static fields / static blocks
                          |
                          v
                    (4) USAGE
         constructors, calls, reflection, casts,
          ServiceLoader, JNI, resource lookup
~~~

This conceptual order does not mean all symbolic references **must** be fully resolved before a class is initialized. The JVMS allows eager or lazy resolution depending on the rules; some `LinkageError` instances may only surface when the program **actually calls a method or accesses a field** along a code path.

**Key takeaway:** If an exception is thrown when calling `foo.bar()`, it may be a **linking/resolution error** even though class `Foo` was loaded/initialized earlier.

## 2. Quick Reference Table by Phase

| Phase / Situation | Typical Throwable | Symptoms | Investigate First |
|---|---|---|---|
| Explicit class lookup | `ClassNotFoundException` | `Class.forName`/`loadClass` by name fails | Binary name, caller/explicit loader, classpath/URL |
| JVM needs a dependency class | `NoClassDefFoundError` | Definition is needed during linking/usage but missing, or init previously failed | `Caused by`, runtime dependencies, init history |
| Deriving a class from bytes | `ClassFormatError` | Invalid class file structure | Bytes/JAR, generator, and corruption |
| Unsupported class-file version | `UnsupportedClassVersionError` | Bytecode built with a newer version than the runtime | `javac --release` and `java -version` |
| Verification | `VerifyError` | Bytecode violates type-safety/stack-map rules | Compiler/instrumentation/transformer |
| Inheritance loading | `ClassCircularityError` | Invalid circular superclass/interface graph | Bytecode/inheritance graph |
| Method resolution | `NoSuchMethodError` | Method name + descriptor missing on runtime type | ABI and version of the defining loader |
| Field resolution | `NoSuchFieldError` | Field symbol missing after a version change | Field name/type/staticness/runtime JAR |
| Binary compatibility | `IncompatibleClassChangeError` | Incompatible change in class/interface/instance/static shape | Compiler vs runtime ABI |
| Invocation | `AbstractMethodError` | Call has no compatible concrete implementation | Version skew/interface/class hierarchy |
| Access checking | `IllegalAccessError` | JVM denies access to method/field/class | Runtime package, loader identity, module exports |
| Static initialization | `ExceptionInInitializerError` | Static block/field initializer throws a non-Error exception | Root cause in `<clinit>` |
| Previous failed initialization | `NoClassDefFoundError` | `Could not initialize class ...` on subsequent attempts | **First initializer error** |
| Reflective lookup | `NoSuchMethodException`/`NoSuchFieldException` | Reflection lookup for member by name/signature finds nothing | Java reflection API and exact signature |
| Reflective accessibility | `IllegalAccessException`/`InaccessibleObjectException` | Reflection is blocked by visibility/module rules | `public`, `exports`, `opens`, caller |
| Runtime cast | `ClassCastException` | Object is not an instance of the runtime target type | `Class.getClassLoader()` of both |
| Array store | `ArrayStoreException` | Storing an object of the wrong runtime component type | Component type and array covariance |
| Native linking | `UnsatisfiedLinkError` | Incorrect JNI binary or native symbol loading | `java.library.path`, ABI, loader ownership |
| Service discovery | `ServiceConfigurationError` | Provider descriptor/type/constructor error | `META-INF/services`, TCCL, module uses/provides |
| Bootstrap method | `BootstrapMethodError` | Bootstrap of `invokedynamic`/dynamic constant fails | Generated bytecode and bootstrap cause |
| Classloader resource exhaustion | `OutOfMemoryError` | Heap/metaspace/native limit | Memory/GC/loader leaks and allocations |

The tables are **isolation hints**, not a guarantee that a throwable can appear in only one step. For example, `NoClassDefFoundError` can appear due to a missing dependency **or** an erroneous class after an initialization failure.

## 3. Loading: Finding Class Bytes and Creating the Runtime Class

### 3.1. `ClassNotFoundException` Is the Checked Exception for Explicit Lookup

~~~java
Class<?> type = Class.forName("com.example.plugin.Entry");
~~~

If the caller's loader cannot find the name `com.example.plugin.Entry`, the call can throw `ClassNotFoundException`. This is a **checked exception**, so it must be caught or declared with `throws`.

Commonly used APIs:

~~~java
Class.forName("p.Entry");
Class.forName("p.Entry", false, pluginLoader);
pluginLoader.loadClass("p.Entry");
~~~

This is an **illustrative snippet**; the `pluginLoader` variable must be declared. The single-parameter overload of `Class.forName` uses the caller's loader according to the API rules; the overload taking a `ClassLoader` uses the passed loader. `ClassLoader.loadClass` normally does not require immediate initialization, whereas `Class.forName(String)` requires initialization by default.

**Common causes:**

- Incorrect binary name: using `p/Entry.class` instead of `p.Entry`.
- Wrong package capitalization; nested classes must use `Outer$Inner`.
- Library is on the build classpath but **not** on the runtime classpath.
- The host class loader cannot see the child plugin JAR.
- `java -jar` uses different manifest/classpath semantics from `java -cp`.
- The plugin JAR is located at a different URL or class files were not copied into the artifact.
- A JPMS named module has not been resolved in the required layer.

**How to handle:** verify the name + loader + artifact roots before changing the global classpath.

### 3.2. `NoClassDefFoundError`: Not Always Equivalent to CNFE

A class `Main` compiled with:

~~~java
MissingLibrary.run();
~~~

but at runtime `MissingLibrary.class` is missing. The JVM resolves the symbolic reference on the code path that needs the class and may throw `NoClassDefFoundError`. This throwable is a **`LinkageError`**, not a checked exception.

Typically, the cause chain may contain:

~~~text
java.lang.NoClassDefFoundError: p/MissingLibrary
Caused by: java.lang.ClassNotFoundException: p.MissingLibrary
~~~

This is an **illustrative message format**; the exact stack trace depends on the JDK and loader. `NoClassDefFoundError` also appears when a class has been marked erroneous after an initialization failure — a completely different cause from a missing file.

**Warning:** Do not catch CNFE and assume all `NoClassDefFoundError` occurrences will disappear; you must identify the root cause and phase.

### 3.3. `ClassFormatError` and `UnsupportedClassVersionError`

- `ClassFormatError`: the class-file bytes are invalid according to the JVM class file structure, which can be caused by a corrupted JAR, a bytecode generator, or instrumentation producing malformed bytes.
- `UnsupportedClassVersionError` is a subtype of `ClassFormatError`, usually caused by a class file version newer than what the VM supports.

Diagnosis:

~~~bash
java -version
javac -version
javap -verbose -classpath libs/plugin.jar p.Entry
~~~

`javap -verbose` reports the class's `major version` when the tool can read the artifact. You should not draw conclusions based on the source file version; the compiler `--release`/target determines the bytecode version.

One way to build with JDK 17 compatibility:

~~~bash
javac --release 17 -d out src/p/Entry.java
~~~

This command is an illustrative snippet requiring the source to be at the right path. With a JDK supporting target 17, it generates the class file version corresponding to Java 17 and restricts API references according to the target release. However, **a runtime dependency with a different native/API version** can still cause other errors.

### 3.4. `ClassCircularityError`

When an invalid superclass/superinterface graph forms a cycle that the JVM detects during loading/linking, `ClassCircularityError` can occur. Normal Java source code is already prevented by the compiler from many forms of circular inheritance; this error is usually related to generated/instrumented bytecode or an abnormally behaving classloader.

Do not fix this by arbitrarily creating additional loaders; inspect the **binary class hierarchy**, the cycle, and the generator/build tool.

## 4. Linking Includes Verification, Preparation, and Resolution

### 4.1. Verification — `VerifyError`

The JVM needs to verify that bytecode satisfies type, operand stack, control flow, and class file verification constraints. For example, a transformer that modifies bytecode without appropriately updating stack map frames/bytecode metadata can cause:

~~~text
java.lang.VerifyError: Bad type on operand stack
~~~

This is an example wording, not fixed output. Things to check:

- Are the JVM/classfile versions correct?
- Does the bytecode generator/ASM/Byte Buddy version support the target?
- Are the StackMapTable/branch targets/instruction signatures valid?
- Is another Java agent/transformer modifying bytes after compilation?
- Test the class file before and after instrumentation.

**Do not disable bytecode verification in production** just to bypass the error; doing so removes the type safety protection layer.

### 4.2. Preparation — Static Fields and Memory

During preparation, the JVM allocates and initializes default values for static fields according to class preparation rules (not to be confused with executing Java initializer expressions in `<clinit>`). Errors here may involve `OutOfMemoryError` or failures while preparing structures.

For example:

~~~java
static int count = compute();
~~~

`compute()` is not executed by preparation like a regular Java initializer; it runs during **initialization** when the class is initialized.

Be sure to distinguish:

- **Preparation:** creates the default static state.
- **Initialization:** runs static field initializers and static blocks in Java order.
- **Compile-time constants:** follow special rules under the JVMS/JLS; do not assume every constant read requires initializing the class.

### 4.3. Resolution — Symbolic References to Runtime Entities

Bytecode contains symbolic references to classes, methods, fields, and dynamic call sites. When the JVM resolves them, the names/symbols must match the runtime definitions and access constraints.

Common errors:

| Error | Typical Cause | What to Compare |
|---|---|---|
| `NoSuchMethodError` | Runtime class lacks a method with the matching descriptor | Method name, params, return descriptor, runtime JAR |
| `NoSuchFieldError` | Runtime class lacks the corresponding field | Field name/type and binary version |
| `IllegalAccessError` | Access check is denied | `public`/package-private, loader, module |
| `IncompatibleClassChangeError` | Incompatible method/class/interface shape | Instance vs static, class vs interface, ABI |
| `AbstractMethodError` | No suitable concrete implementation at invocation time | Interface evolution, class hierarchy, version skew |
| `BootstrapMethodError` | Bootstrap method of a dynamic call site/constant fails | Bootstrap target and nested cause |

**Important:** The JVM may resolve references upon their first use, not immediately when the class is loaded. Therefore, a plugin may start up successfully and only throw `NoSuchMethodError` when a rarely used feature is invoked.

### 4.4. Why Do These Errors Often Appear After Updating a Library?

Suppose:

~~~text
Compile-time:
  api.Library v2 has static String extra()

Runtime:
  api.Library v1 does not have extra()
~~~

The `Client` code compiles against v2, but the application loader actually loads v1. When the bytecode executes `invokestatic api.Library.extra()`, the method does not exist on the runtime type and the JVM throws `NoSuchMethodError`.

Do not fix this by changing the `Class.forName` overload when the class is already loaded with the right name but the **wrong version/ABI**. You need to fix the classpath/container dependency version or loader ownership.

## 5. Java 17+ Demo Reproducing NoSuchMethodError Due to Version Skew

This experiment intentionally compiles `Client` against Library v2 but runs it with v1.

### 5.1. Project Structure

~~~text
project/
  src/
    v1/api/Library.java
    v2/api/Library.java
    client/Client.java
  out/
    v1/
    v2/
    client/
~~~

### 5.2. `src/v1/api/Library.java`

~~~java
package api;

public final class Library {
    public static String hello() {
        return "v1";
    }
}
~~~

### 5.3. `src/v2/api/Library.java`

~~~java
package api;

public final class Library {
    public static String hello() {
        return "v2";
    }

    public static String extra() {
        return "new-api";
    }
}
~~~

### 5.4. `src/client/Client.java`

~~~java
import api.Library;

public final class Client {
    public static void main(String[] args) {
        System.out.println(Library.extra());
    }
}
~~~

### 5.5. Build and Run

~~~bash
mkdir -p out/v1 out/v2 out/client

javac -d out/v1 src/v1/api/Library.java
javac -d out/v2 src/v2/api/Library.java

javac -cp out/v2 -d out/client src/client/Client.java

java -cp "out/client:out/v1" Client
~~~

The run command **intentionally** uses v1 instead of v2. The result is an error of the form:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError: 'java.lang.String api.Library.extra()'
~~~

This is an **illustrative primary line**; the full stack trace will also include source locations and may vary in signature formatting depending on the JVM. If run with the correct v2 runtime dependency:

~~~bash
java -cp "out/client:out/v2" Client
~~~

Stdout:

~~~text
new-api
~~~

**Lesson:** the `api.Library` class still exists and is loaded; the issue is that the **method symbol does not match the runtime definition**. It is not a `ClassNotFoundException`.

On Windows, the classpath separator in the `-cp` commands needs to be `;` instead of `:`.

## 6. Initialization — Running Static Blocks and Static Field Initializers

A class is initialized upon active use or when an API operation requires it under JLS/JVMS rules. `Class.forName(name, true, loader)` requires initialization; `Class.forName(name, false, loader)` does not.

### `ExceptionInInitializerError`

If a static block or static field initializer throws an exception that is not an `Error`, the JVM typically wraps the exception in an `ExceptionInInitializerError`.

~~~java
final class Config {
    static final String VALUE = load();

    static String load() {
        throw new IllegalStateException("bad config");
    }
}
~~~

This is an illustrative class, which does not yet have a `main`. When the class is initialized, the root error may be `IllegalStateException`, but the outermost Throwable is `ExceptionInInitializerError`. **Read `getCause()`** to see the actual cause.

If the initializer throws an `Error` such as `UnsatisfiedLinkError` from `System.loadLibrary`, the Error may be propagated directly and is not necessarily wrapped in `ExceptionInInitializerError`.

### Subsequent Uses — `NoClassDefFoundError`

A runtime class that failed initialization may be marked **erroneous**. For the same defining loader/runtime class, subsequent active uses typically throw:

~~~text
java.lang.NoClassDefFoundError: Could not initialize class ...
~~~

**This does not mean the class file suddenly disappeared.** To fix it, you must find the **first initializer error** and fix the config/dependency/logic; create a new loader generation if you need to load a fresh class definition. Do not retry the initializer indefinitely on the same erroneous class.

### Common Causes of Init Failures

- Reading a missing configuration file or an invalid environment variable.
- A static initializer calling a network/database and throwing.
- Static code using an incompatible dependency method.
- `System.loadLibrary` failing due to a JNI binary issue or duplicate load.
- Circular static initialization producing an unintended state.
- A static cache allocating a large resource and causing a memory issue.

**Better design:** Minimize side effects in static initializers; use a factory/lifecycle method with clear error handling when initializing plugins/services.

## 7. Java 17+ Demo Directly Distinguishing 4 Error Types

The standalone **`PhaseErrorsDemo.java`** file below creates intentional failure scenarios. The program only catches broad `Throwable` in a test harness to print the error name and avoid hiding differences between scenarios; **do not** apply this broad-catch technique in production business logic.

### 7.1. Complete `PhaseErrorsDemo.java` File

~~~java
public final class PhaseErrorsDemo {

    static final class Exploding {
        static {
            if (alwaysFail()) {
                throw new IllegalStateException("broken initializer");
            }
        }

        static boolean alwaysFail() {
            return true;
        }
    }

    public static void main(String[] args) {
        // 1. Explicit lookup of a missing class.
        try {
            Class.forName("missing.DoesNotExist");
        } catch (ClassNotFoundException ex) {
            System.out.println("lookup: "
                    + ex.getClass().getSimpleName());
        }

        // 2. First active use: initializer exception.
        try {
            Class.forName(
                    Exploding.class.getName(),
                    true,
                    PhaseErrorsDemo.class.getClassLoader());
        } catch (ExceptionInInitializerError ex) {
            System.out.println("init first: "
                    + ex.getClass().getSimpleName());
        }

        // 3. Subsequent attempt: class is in an erroneous state.
        try {
            Class.forName(
                    Exploding.class.getName(),
                    true,
                    PhaseErrorsDemo.class.getClassLoader());
        } catch (NoClassDefFoundError ex) {
            System.out.println("init second: "
                    + ex.getClass().getSimpleName());
        }

        // 4. An object with runtime type String cannot become an Integer.
        Object value = "hello";

        try {
            Integer number = (Integer) value;
            System.out.println(number);
        } catch (ClassCastException ex) {
            System.out.println("cast: "
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

### 7.2. Compile and Run

~~~bash
javac PhaseErrorsDemo.java
java PhaseErrorsDemo
~~~

**Expected stdout on JDK 17+:**

~~~text
lookup: ClassNotFoundException
init first: ExceptionInInitializerError
init second: NoClassDefFoundError
cast: ClassCastException
~~~

**Explanation:**

1. `missing.DoesNotExist` does not exist in the caller's loader, so the explicit lookup throws the checked `ClassNotFoundException`.
2. `Exploding.class` only obtains the class literal and does not require initialization. `Class.forName(..., true, ...)` runs the static block for the first time; `alwaysFail()` returns `true` and the `IllegalStateException` is wrapped in `ExceptionInInitializerError`.
3. The JVM does not automatically re-run the initializer of the same erroneous class as if it were a fresh class; the next active use causes `NoClassDefFoundError`.
4. The String object and the runtime type Integer are incompatible, so the cast throws `ClassCastException` during the **usage phase**.

Lines 2–3 demonstrate why you must preserve **the stack trace of the first failure**: if logs only start at the retry, operators may see `NoClassDefFoundError` and mistakenly think a class file is missing.

## 8. Usage — Errors That Appear Even After Loading and Initialization Succeed

### 8.1. `ClassCastException` and Defining Class Loaders

Two classes with the same binary name defined by two different defining loaders are **two distinct runtime types**:

~~~text
(com.acme.Plugin, LoaderA) != (com.acme.Plugin, LoaderB)
~~~

An object created by LoaderA cannot automatically be cast to an implementation type defined by LoaderB, even if the bytecode is identical. In plugin systems, this error is commonly caused by:

- A shared SPI/interface being redefined by a child-first loader.
- The host and plugin packaging two copies of the API with the same name.
- The classloader hierarchy not delegating properly to the parent.
- An object from an old generation being passed to a new generation.

**Fix:** place shared API/DTOs in a common parent loader and communicate through unified runtime types. Do not use `--add-opens` to "fix" differing class identity across loaders; module openness does not merge two `Class<?>` types.

### 8.2. `NoSuchMethodException` Differs from `NoSuchMethodError`

Reflection:

~~~java
String.class.getMethod("methodThatDoesNotExist");
~~~

Throws a **checked `NoSuchMethodException`** because the caller is looking up a method by name and signature through the reflection API.

Conversely, bytecode `invokevirtual`/`invokestatic` referencing a method missing from the runtime type can cause **`NoSuchMethodError`**. This is a `LinkageError`, usually caused by binary incompatibility.

**Do not use these two error names interchangeably** when troubleshooting.

### 8.3. `IllegalAccessException` and `IllegalAccessError`

`IllegalAccessException` is a checked reflection exception thrown when the caller is not permitted to access a method/constructor/field under access checks.

`IllegalAccessError` is a `LinkageError` that can occur when bytecode accesses a member/class that is no longer accessible at runtime, for example:

- A method was `public` at compile time, but the runtime version reduced its visibility.
- Two classes in the same source package are split across **different defining loaders**, so they are no longer in the same runtime package for package-private access.
- A module export/access change breaks the access rule required by the bytecode.

With JPMS reflection, `InaccessibleObjectException` is a **runtime exception** that can be thrown when `setAccessible(true)` is denied due to module encapsulation. Not only must the class have the "right name", you must also comply with exports/opens.

### 8.4. `ArrayStoreException`

Java arrays have a runtime component type; when storing an unassignable object into a reference array:

~~~java
Object[] elements = new String[1];
elements[0] = 123;
~~~

This is an **illustrative snippet** that causes an `ArrayStoreException` at runtime. Class loading and linking may be completely valid; the error belongs to array usage/mutation behavior.

### 8.5. `ServiceConfigurationError`

`ServiceLoader` reads service provider configs or module `provides` declarations and lazily locates/instantiates providers. Possible errors include:

- Misnamed `META-INF/services/<SPI binary name>`.
- The descriptor contains a provider binary name that does not exist.
- The provider is not assignable to the runtime SPI interface.
- The constructor/factory method does not conform to the contract.
- The TCCL or explicit loader cannot see the plugin.
- The module provider is not resolved or the consumer is missing `uses` per the module contract.

`ServiceConfigurationError` can be thrown during iteration/streaming, not when `ServiceLoader.load(...)` creates the instance. This is an **Error caused by service discovery**, and it may contain CNFE/linkage/init failures as its cause.

### 8.6. `UnsatisfiedLinkError`

Native linkage follows its own resolution path:

~~~java
System.loadLibrary("codec");
~~~

This is an illustrative snippet requiring a real JNI binary. If the library cannot be found, has the wrong OS/ABI/architecture, is missing a native dependency, lacks the JNI symbol, or the native library already belongs to another classloader, `UnsatisfiedLinkError` can be thrown.

A JNI library across multiple child loaders is subject to an **ownership rule**; adding to the Java classpath is not a way to fix a cross-loader native-library conflict. Usually a shared JNI bridge in the parent or process separation is needed when native state cannot be shared.

## 9. Comparison Table of Easily Confused Pairs

| Error Pair | Primary Difference | Identification Example |
|---|---|---|
| `ClassNotFoundException` vs `NoClassDefFoundError` | Explicit string lookup (checked) vs JVM class definition/linkage/previous init (Error) | `Class.forName("missing.X")` vs bytecode `new X()` with missing dependency |
| `NoSuchMethodException` vs `NoSuchMethodError` | Checked reflection lookup vs symbolic method resolution binary mismatch | `getMethod("missing")` vs built with v2/run with v1 |
| `IllegalAccessException` vs `IllegalAccessError` | Reflection API access denied vs bytecode access/linkage denied | `getMethod.invoke` vs runtime package split |
| `ExceptionInInitializerError` vs `NoClassDefFoundError` after init | First static non-Error exception vs subsequent erroneous class | `Exploding` demo |
| `ClassFormatError` vs `VerifyError` | Invalid class-file structure vs bytecode fails verifier constraints | Broken format vs invalid operand stack |
| `ClassCastException` vs `IllegalAccessError` | Runtime type mismatch vs bytecode access denied | Duplicate SPI classes vs package-private split |
| `UnsatisfiedLinkError` vs `ClassNotFoundException` | Native library/method linkage vs Java class name lookup | `System.loadLibrary` vs `loadClass` |
| `OutOfMemoryError` vs classloader leak | The Throwable is resource exhaustion; a leak is only one possible cause | Growing metaspace + retained loaders |

An error message may contain **multiple Throwable types in its cause chain**. Classify the **outermost error + root cause + first failure**, rather than just looking for the word "class" in the message.

## 10. How to Identify the Phase from a Stack Trace / Cause Chain

### Step 1 — Identify the Operation Being Executed

- `Class.forName`/`ClassLoader.loadClass`: explicit name lookup; is there an initialization flag?
- Constructor call/`new`: is linking/init required?
- `invokestatic`/`invokevirtual`: method resolution/invocation.
- `getstatic`/`putstatic`: field resolution/initialization.
- `ServiceLoader` iterator: provider discovery/instantiation.
- `System.load`/`native`: JNI loader/symbol.
- Reflection `getMethod`/`invoke`: reflective lookup/access/target invocation.

### Step 2 — Read the Full Cause Chain

Example:

~~~text
ExceptionInInitializerError
  caused by IllegalStateException: missing config
~~~

Fix the missing config/static init; **do not** add random JARs.

Example:

~~~text
NoClassDefFoundError: p/Dependency
  caused by ClassNotFoundException: p.Dependency
~~~

Fix the runtime dependency/loader visibility.

Example:

~~~text
ServiceConfigurationError
  caused by provider not found / not assignable
~~~

Fix the provider descriptor/visibility/runtime SPI identity.

### Step 3 — Print the ClassLoader and Class Source

Once you have a `Class<?>`:

~~~java
Class<?> type = object.getClass();
ClassLoader loader = type.getClassLoader();

System.out.println("type=" + type.getName());
System.out.println("loader=" + loader);
System.out.println("module=" + type.getModule());
~~~

This is an illustrative snippet assuming `object` is non-null. `getClassLoader() == null` is normal for bootstrap classes.

If CodeSource is available:

~~~java
var domain = type.getProtectionDomain();
var codeSource = domain == null ? null : domain.getCodeSource();

System.out.println(codeSource == null
        ? "source unknown"
        : codeSource.getLocation());
~~~

Not every class has a useful CodeSource; it may be `null`. For errors where the class has not yet been loaded, start from **the caller loader, binary name, and actual runtime URLs**.

### Step 4 — Inspect Artifacts and ABI

~~~bash
jar --list --file libs/plugin.jar
javap -classpath libs/plugin.jar -public p.Api
javap -classpath libs/plugin.jar -verbose p.Api
~~~

These commands are diagnostic examples requiring the corresponding JAR and class. `javap -public` can inspect method signatures, and `-verbose` shows the class-file major version and constant pool; do not rely solely on the build-time dependency tree.

### Step 5 — JVM Logging / JFR

On HotSpot Java 17:

~~~bash
java -Xlog:class+load=info,class+unload=info \
    -cp out/app Main
~~~

This is a **diagnostic command**, not fixed stdout. Class-loading logs/JFR help reveal class/source/load/unload behavior, but they do not automatically explain all access/cast/init/linkage errors. When a leak is suspected, combine classloader stats, metaspace metrics, thread/TCCL inspection, and heap dumps.

## 11. Distinguishing Errors Caused by Classpath, Loader Identity, and Module Access

### Classpath/Configuration

A class `p.Feature` may exist at `plugins/p/Feature.class`, yet the JVM is only running with `-cp out/app`. An explicit lookup through the app loader cannot see it and throws CNFE. Use the correct root URL/classpath or an explicit plugin loader.

### Loader Identity

Two copies of the same `api.Service` in the host and a child-first plugin are not the same runtime interface. Cast/provider verification can fail even though the class file exists in both places.

### JPMS Module Access

A class in a named module may exist and be resolved, yet its package is not appropriately exported/opened to the caller. This does not mean it is always CNFE; you may encounter `IllegalAccessError`, `IllegalAccessException`, or `InaccessibleObjectException` depending on the API/phase.

**Do not use `--add-opens` as a "fix for all class loading errors"**; it does not change class identity and does not add missing methods/dependencies.

## 12. Binary Compatibility and Change Matrix

| Change Between Compile Time and Runtime | Risk |
|---|---|
| Removing a method or changing a method descriptor | `NoSuchMethodError` |
| Removing a field / changing its descriptor | `NoSuchFieldError` |
| Changing a method from static to instance or vice versa | `IncompatibleClassChangeError` or a related subtype |
| Changing a class to an interface or vice versa | `IncompatibleClassChangeError` |
| Changing visibility so the caller cannot access it | `IllegalAccessError` |
| Adding an abstract method that the runtime implementation does not satisfy | `AbstractMethodError` at invocation |
| Inconsistently changing superclass/interfaces | Possibly `IncompatibleClassChangeError` or a related error |
| Building a class file for a higher Java version than the runtime | `UnsupportedClassVersionError` |
| Instrumentation making bytecode invalid | `VerifyError` or `ClassFormatError` |
| Duplicating shared API across multiple loaders | `ClassCastException`, `LinkageError`/provider errors |
| Invalid native library/method ABI | `UnsatisfiedLinkError` |

This is a table of **common risks**, not a guarantee that each change leads to only a single specific throwable. JVM resolution/invocation rules and the specific code path determine the observed error.

### Why Are the Compiler and Unit Tests Alone Not Enough?

The `Client` code compiles against dependency v2, but the production launcher/container uses v1. The compile-time classpath **differs from the runtime loader graph**, so unit tests may pass while the deployment throws `NoSuchMethodError`.

**You should perform final testing with the actual artifact and startup command**: parent classloader, child loaders, module path, JAR order, Java runtime version, resources, and providers.

## 13. Error-Handling Workflow by Category

### A. Explicit Lookup Failure

1. Record the exact binary name string actually passed to the API.
2. Identify the `Class.forName`/`loadClass` overload and the loader being used.
3. Inspect `jar --list` / the directory root.
4. Check the launcher `-cp`, `-jar`, and JPMS module graph.
5. Use an explicit loader when the class is owned by a child plugin; do not break the shared API boundary.

### B. Linking/ABI Failure

1. Find the method/field/class symbol in the exception.
2. Determine the defining loader of the class actually loaded by the JVM.
3. Compare the runtime CodeSource/JAR against the compile-time version.
4. Compare binary descriptors using `javap`.
5. Fix version alignment or adjust the selective loader policy if private dependencies require their own version.

### C. Initialization Failure

1. Find the **first error** in `<clinit>`.
2. Read the underlying cause: config, JNI, DB, static code, dependency.
3. Do not retry the initializer indefinitely on the same erroneous class.
4. After fixing it, use the appropriate JVM/plugin generation according to its lifecycle.

### D. Runtime Usage/Cast/Access Failure

1. Compare runtime `Class<?>` identity, not just the name.
2. Verify that the shared SPI/DTO/interface comes from a single defining loader.
3. Check reflection access/module exports/opens if applicable.
4. Do not blindly change the classpath in ways that introduce duplicate classes.

### E. Native/Service Discovery Failure

1. JNI: check the library path, OS/architecture, symbols, and cross-loader native library ownership.
2. SPI: check `META-INF/services` or `uses`/`provides`.
3. Check the TCCL/explicit loader, provider class, and constructor.
4. Run a test that actually instantiates the provider or invokes the native call.

## 14. Diagnostic Anti-Patterns

**Catching every Throwable and ignoring it:**

~~~java
try {
    Class.forName(configuredName);
} catch (Throwable ignored) {
    // Wrong: hides all linkage, init, memory, native errors...
}
~~~

This is an **illustrative anti-pattern**, not a solution. If an optional plugin is needed, catch `ClassNotFoundException` at an appropriate boundary and classify serious `LinkageError` types according to a clear policy.

**Fixing everything by adding all JARs to the application classpath:** this may make Java class lookup pass, but it breaks version isolation and creates `ClassCastException`, `NoSuchMethodError`, or duplicate native wrappers.

**Using `System.gc()` to cure all classloader errors:** GC does not change binary method signatures, fix the classpath, force immediate native library unloading, or re-run the static initializer of an erroneous class.

**Enabling `--add-opens` regardless of the error:** module openness only resolves part of reflection/resource access issues; it does not fix missing classes/methods or type identity.

**Reading only the exception message and ignoring the cause:** many errors are wrappers around deeper failures; you need the cause chain, suppressed exceptions, and the time of the first failure.

## 15. Quick Lookup Checklist Before Modifying Code

- [ ] Determine whether the outermost throwable is an `Exception`, `Error`, `LinkageError`, or runtime exception.
- [ ] Identify whether the loading, linking, initialization, or usage phase caused the error.
- [ ] Identify the API call/bytecode operation that triggered the behavior.
- [ ] Check the binary class/member name and full signature.
- [ ] Distinguish `ClassNotFoundException` from `NoClassDefFoundError`.
- [ ] If `NoClassDefFoundError`, inspect the init history and root cause.
- [ ] If `ExceptionInInitializerError`, preserve the stack trace from the first occurrence.
- [ ] If `NoSuchMethodError`/`NoSuchFieldError`, compare compile-time and runtime ABIs.
- [ ] If `ClassCastException`, check the defining loaders on both sides.
- [ ] If `IllegalAccessError`, check runtime package identity and JPMS exports.
- [ ] If `VerifyError`, inspect the transformer/generator and classfile version.
- [ ] If `UnsupportedClassVersionError`, check the Java target/runtime.
- [ ] If `UnsatisfiedLinkError`, check native ABI/library ownership.
- [ ] If `ServiceConfigurationError`, check descriptor/TCCL/JPMS provider rules.
- [ ] Do not assume error timing always coincides with `loadClass`; linking resolution can be lazy.
- [ ] Do not apply the same "add JAR" solution to every category of error.
- [ ] Test the final artifact with the right launcher and classloader policy.
- [ ] Log sufficient loader/code source metadata without exposing secrets.
- [ ] If using plugin generations, clean up TCCL/caches/threads properly per lifecycle.

## 16. Self-Check Exercises

**Question 1.** What checked exception does `Class.forName("p.Missing")` throw?

**Answer:** `ClassNotFoundException` if the caller's loader cannot find the class; check the binary name and loader/search path.

**Question 2.** Client is compiled against method `Library.extra()` from v2, but at runtime Library v1 is loaded. What is the typical error?

**Answer:** `NoSuchMethodError` when resolving/invoking the method symbol, because v1 does not have the corresponding method descriptor.

**Question 3.** A static initializer throws `IllegalStateException` on first use; what can the outermost error be?

**Answer:** `ExceptionInInitializerError`. A subsequent active use on the same erroneous class can become `NoClassDefFoundError`.

**Question 4.** Two different loaders each define the same `api.Plugin`. Is it guaranteed that the plugin object can be cast to the host's `api.Plugin`?

**Answer:** No. Having the same binary name is not enough; different defining loaders produce different runtime types, which can cause `ClassCastException`.

**Question 5.** Does `NoSuchMethodException` always mean `NoSuchMethodError`?

**Answer:** No. One is a checked reflection lookup exception, while the other is a `LinkageError` caused by a symbolic method resolution/invocation mismatch.

**Question 6.** Why shouldn't `VerifyError` be fixed by disabling the verifier?

**Answer:** It indicates bytecode does not satisfy type-safety constraints; you must fix the generator/transformer/classfile instead of removing the JVM's safety check layer.

**Question 7.** If a class file's major version is too new for the running JDK, what type of error commonly occurs?

**Answer:** `UnsupportedClassVersionError`; use the compiler `--release` option or a compatible runtime.

**Question 8.** The plugin loader has class `p.C`, yet `Class.forName("p.C")` from the host throws CNFE. Why?

**Answer:** The caller's loader cannot see the child plugin loader; you need an explicit plugin loader or an appropriate framework API.

**Question 9.** Reflection `setAccessible(true)` is denied because a named module does not open the package. Is this a missing class error?

**Answer:** No. This is an access/module encapsulation issue, potentially `InaccessibleObjectException`; address the module policy appropriately.

**Question 10.** A JNI library is loaded into LoaderA, and then LoaderB attempts to load the same library. What is the error and architectural fix?

**Answer:** `UnsatisfiedLinkError` due to native-library ownership; use a shared JNI bridge owned by the parent or separate processes if independent native state is needed.

## 17. Lookup Decision Tree

~~~text
Throwable occurs when using a Java class/plugin
                      |
                      v
         Which API/action triggered it?
           /       |        |       \
       Lookup    Linkage   Init    Runtime usage
         |         |        |         |
         v         v        v         v
    CNFE/NCDFE  ABI/verify  static    cast/access/
         |      /format      code     reflection/JNI
         |         |        |         |
   name+loader  version+    cause    type identity/
   +artifact    bytecode    chain    service/native
         \         |         |         /
          \        |         |        /
                  v
         Confirm phase + root cause
                  |
       compare runtime defining loader,
       CodeSource, module, signature
                  |
                  v
       fix the right dependency/policy/code
                  |
                  v
         test with real artifact + JVM
~~~

**Conclusion:** An error "with the word class in it" is not necessarily a classpath error. **Loading** is primarily about finding/defining a type; **linking** checks and resolves symbolic references; **initialization** runs static code; **usage** covers method calls, reflection, casts, SPI, and JNI. Only by identifying the right phase, **Throwable type**, **cause chain**, **runtime defining loader**, and **artifact ABI** can you fix the error sustainably without creating conflicts among other classloaders.

### Official References

- [JVMS 17 — Chapter 5: Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [Java SE 17 — ClassNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html)
- [Java SE 17 — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html)
- [Java SE 17 — ExceptionInInitializerError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html)
- [Java SE 17 — LinkageError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html)
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java 17 Java Language Specification — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html)
