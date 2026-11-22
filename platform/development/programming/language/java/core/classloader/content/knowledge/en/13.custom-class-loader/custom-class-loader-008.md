# Classifying Not-Found and Invalid Bytecode Errors in Custom ClassLoaders

## 1. The Core Problem: "Unable to Load a Class" Does Not Have Just One Cause

When writing a custom `ClassLoader`, you may encounter many errors with the same outcome at the business layer: the application cannot use the requested class. However, **their underlying nature and handling approaches are completely different**:

- **`ClassNotFoundException`**: the loader **cannot find the requested class** through the lookup path being used. This is a **checked exception** typically declared on `loadClass` and `findClass`.
- **`ClassFormatError`**: the JVM received data to define a class, but the class file **is malformed or cannot be interpreted as a valid class file**.
- **`UnsupportedClassVersionError`**: the class file has a **major/minor version not supported by the current JVM**. It is a **subclass of `ClassFormatError`**.
- **`VerifyError`**: the class file is structurally valid enough for the JVM to enter verification, but the bytecode **violates verifier constraints**, such as stack/type correctness along control paths.
- **`NoClassDefFoundError`**: while the JVM needs to define, link, or initialize a class, a required definition **is unavailable** or a class **previously failed initialization**; in particular, `defineClass` can also throw this error when the requested name **differs from the binary name contained in the bytes**.
- **Other `LinkageError`s** such as `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, or `IncompatibleClassChangeError`: the JVM found the bytecode, but runtime symbol/API linkage does not match.

**Principle:** Do not turn everything into `ClassNotFoundException`. If the bytecode exists but is **invalid**, the key diagnostic information usually lies in an **Error** under the `LinkageError` hierarchy, not in a "file not found" condition.

## 2. Placing Errors in the Right Phase of the Class Lifecycle

```text
loader.loadClass("demo.Plugin")
          │
          ▼
1. findLoadedClass(name)
          │
          ▼
2. parent.loadClass(name)
          │ parent did not find it?
          ▼
3. findClass(name) [custom loader]
          │
          ├── No bytecode
          │     └── ClassNotFoundException
          │
          ├── Bytecode read
          │     └── defineClass(name, bytes, ...)
          │            ├── Malformed file → ClassFormatError
          │            ├── Unsupported version
          │            │      → UnsupportedClassVersionError
          │            ├── Name mismatch
          │            │      → NoClassDefFoundError
          │            └── Class<?> defined
          │
          ▼
4. Verification / preparation / resolution
          │
          ├── Violates verifier rules → VerifyError
          ├── Missing dependency → may throw NoClassDefFoundError
          └── Invalid binary API linkage → other LinkageError types
          │
          ▼
5. Initialization on active use
          │
          ├── Static initializer succeeds
          └── Static initializer fails
                 ├── first time: ExceptionInInitializerError
                 └── subsequent times: typically NoClassDefFoundError
```

**This is a diagnostic model, not a rigid schedule for every JVM.** Verification, resolution, and the use of symbolic references can be performed by the JVM at different times within specification boundaries. Therefore, `loadClass(name)` succeeding **does not yet prove** that every dependency, every method reference, and the class's static initializer will work.

### Two Boundaries to Remember

1. **Does the file exist?** This is only a step inside `findClass`. A file existing does not mean it is a valid class.
2. **Has the class been defined?** Finding bytes or receiving a `Class<?>` does not mean the class has been initialized or that all references resolve successfully.

If a custom loader itself uses `Files.readAllBytes(path)`, the read step is **application-written I/O**. Errors occurring after calling `defineClass` or when the JVM links the class are **JVM contract errors**. Keep this boundary clear in code and logs.

## 3. Exception/Error Classification Chart

| Error Type | Hierarchy | Common Meaning | Handling Approach |
|---|---|---|---|
| `ClassNotFoundException` | `Exception`, checked | Loader cannot find the class via configured sources | Check binary name, URL/classpath, JAR entry, delegation |
| `ClassFormatError` | `LinkageError` | Bytes do not have a valid class file structure | Check magic, constant pool, transformer, corrupted file |
| `UnsupportedClassVersionError` | `ClassFormatError` | Major/minor version is not supported by the runtime | Compare the runtime JDK and the `--release` target |
| `VerifyError` | `LinkageError` | Bytecode violates verifier constraints | Check bytecode generator/transformer, stack map, control flow |
| `NoClassDefFoundError` | `LinkageError` | JVM needs the class/definition, but it is absent; or init previously failed; or wrong name | Read the full message and cause; consider missing dependency/init/wrong name |
| `NoSuchMethodError` | `IncompatibleClassChangeError` → `LinkageError` | A method referenced at compile time does not exist with the exact signature at runtime | Compare compile-time and runtime JARs/APIs |
| `NoSuchFieldError` | `IncompatibleClassChangeError` → `LinkageError` | Field no longer matches the expected name/descriptor | Compare dependency versions |
| `IllegalAccessError` | `IncompatibleClassChangeError` → `LinkageError` | JVM found the member, but runtime access is not permitted | Check access modifiers, runtime package, module, loader |
| `ExceptionInInitializerError` | `LinkageError` | Static initialization logic failed | Read the root cause in `<clinit>` |
| `SecurityException` | `RuntimeException` | Security check violated when defining or accessing a class | Check packages such as `java.*`, certificates, security context |

**Inheritance note:** `UnsupportedClassVersionError extends ClassFormatError`. When writing separate `catch` blocks, you must catch the version error **before** `ClassFormatError`; otherwise, the version branch will be intercepted by the parent branch. `VerifyError` is a separate branch under `LinkageError`, not a subclass of `ClassFormatError`.

## 4. ClassNotFoundException: "Cannot Find Class Name"

Standard API:

```java
protected Class<?> findClass(String name)
        throws ClassNotFoundException
```

In a loader following the default delegation model, `findClass` is called after the parent fails to find the requested class. The default implementation of `ClassLoader.findClass(String)` throws `ClassNotFoundException`; subclasses override it to know where to find bytecode.

For a custom loader searching for classes on disk:

```java
// Excerpt inside the findClass override:
Path classFile = root.resolve(
        name.replace('.', '/') + ".class"
);

byte[] bytes;
try {
    bytes = Files.readAllBytes(classFile);
} catch (IOException cause) {
    throw new ClassNotFoundException(name, cause);
}
return defineClass(name, bytes, 0, bytes.length);
```

This is an **excerpt**; it requires `root`, imports, and a `ClassLoader` subclass. Wrapping `IOException` preserves the I/O cause; for example, `NoSuchFileException` indicates that the path does not exist.

In a production loader, you should further distinguish:
- **Class absent from this source**: `ClassNotFoundException` is a reasonable signal to let the caller know the class could not be found.
- **Source exists but I/O fails**: the `findClass` contract can still present this as a `ClassNotFoundException` with the **original cause**; path details, read permissions, timeouts, or storage errors must not be lost.
- **Bytes were read but corrupted**: do **not** catch `ClassFormatError` and replace it with `ClassNotFoundException`, because doing so hides the cause that "bytecode is present but invalid".

### Common Mistake

```java
// ANTI-PATTERN — do not use verbatim:
try {
    byte[] bytes = loadBytes(name);
    return defineClass(name, bytes, 0, bytes.length);
} catch (Throwable anything) {
    throw new ClassNotFoundException(name, anything);
}
```

This is **illustrative anti-pattern code**; the methods and variables are undefined. Catching `Throwable` swallows `LinkageError`, `OutOfMemoryError`, `ThreadDeath`, and other serious errors. The caller assumes the class is merely absent and may perform pointless retries/fallbacks. **Only catch the specific errors you can actually handle.**

## 5. ClassFormatError: "Bytes Present, but Not a Valid Class File"

A Java class file has a binary structure specified by the JVMS:

```text
u4 magic          // 0xCAFEBABE
u2 minor_version
u2 major_version
u2 constant_pool_count
...
```

**Example causes:**

- The beginning of the file lacks the `CAFEBABE` magic; a text/HTML/JAR/image file was mistakenly read as `.class`.
- The file was truncated during download, extraction, or deployment.
- The constant pool structure, indices, attributes, or other sections do not conform to the class-file format.
- A bytecode transformer tool generated malformed bytes.
- The loader read the wrong file due to a bug in mapping the binary name to a path.

`ClassFormatError` is an **`Error`**, not a checked `Exception`. `defineClass` can throw this error when given invalid bytes. You need to find the **source of the bytes** and the **cause of data corruption**, not merely retry the class name.

### Distinguishing File Existence from Valid Data

```java
// Excerpt:
byte[] bytes = Files.readAllBytes(classFile);
System.out.println("bytes length=" + bytes.length);
return defineClass(name, bytes, 0, bytes.length);
```

If `bytes.length > 0`, we only know that data was read; we do not yet know whether it is a Java class file. Even having the first four bytes be `CAFEBABE` **does not prove** that the constant pool, contents, or bytecode are valid.

## 6. UnsupportedClassVersionError: "Bytecode Is Newer/Unsupported by the JVM"

This is a **subclass of `ClassFormatError`**, for cases where `major_version`/`minor_version` in the class file is not recognized by the JVM under version rules.

Some milestones:

| Java release | Typical class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |
| Java 26 | 70 |

For example, if an application runs on **Java 17** while a custom loader reads a class compiled for **Java 21** (major 65), the Java 17 JVM cannot load that bytecode. Even though the class file exists and its magic is valid, `UnsupportedClassVersionError` is still thrown.

**Do not resolve this by changing the file extension, changing directories, or altering a few major-version bytes in the class file**: opcodes, constant pool entries, language features, and APIs may genuinely require the newer runtime.

Proper solutions:

1. Check the **active runtime JVM** using `java -version`, not only `javac -version`.
2. Check the **major/minor version of the actual .class file** using `javap -verbose` (or a reliable header-reading tool).
3. Recompile with `javac --release <supported-version>` if the code and the APIs it uses permit.
4. If the features cannot target an older version, **upgrade the Java runtime** accordingly.
5. If using a multi-release JAR, verify the exact versioned entry that the runtime/loader actually selects.

A subtle exception is **preview-feature class files** with `minor=65535` from releases supporting preview rules. They can usually only be used on a runtime of the **same release** with the corresponding preview flag enabled; do not infer that a lower major version means every newer JDK accepts preview bytecode.

## 7. VerifyError: Bytecode Passes Formatting but Fails the Verifier

`VerifyError` indicates that the JVM detected the class file **failed verification conditions**, for example:

- An instruction requires an operand stack with an incompatible type or depth.
- A branch jumps to an unsuitable offset or stack state.
- Return type/stack-map information does not match the control-flow path.
- Operations on local variables/receiver violate type-safety rules.

This category of issues typically occurs when:

- Manually generating bytecode with ASM/Byte Buddy or writing a class-file generator.
- Instrumenting/rewriting bytecode without properly updating stack map frames or max stack/local variables.
- An obfuscator/shader/agent tool generates bytecode incompatible with the target runtime.

**Distinguishing from `ClassFormatError`:** A class file can have a valid header/constant pool while containing code that violates the verifier. The JVM may only detect `VerifyError` when verification actually occurs; do not assign a fixed schedule to every JVM.

`javac` normally generates valid bytecode for supported targets; therefore, there is no need to try constructing a `VerifyError` example with plain valid Java source code. To produce a deterministic error, bytecode must be intentionally generated/mutated in a controlled way. In production, **do not disable the verifier** as a way to "fix" broken bytecode files.

## 8. Java 17+ Demo: Distinguishing Four Scenarios with a Custom Loader

The following example intentionally creates four paths:

1. `MISSING`: requests a binary name with no file → `ClassNotFoundException`.
2. `MALFORMED`: modifies the magic at the start of a valid class file → `ClassFormatError`.
3. `NEWER`: modifies the major version to a value higher than Java 17 supports → `UnsupportedClassVersionError`.
4. `WRONG_NAME`: requests a binary name different from the name declared in the bytes → `NoClassDefFoundError`.
5. `VALID`: uses valid bytes → loads the class, then reflection invokes the method and initializes the class.

The scenarios use a **separate loader per attempt** so `findLoadedClass` does not retrieve a class already loaded from a previous pass. The demo intentionally **does not create `VerifyError`** because that requires a suitable bytecode transformer, and also does not assume every JVM picks the exact same verification timing.

### 8.1. The Sample.java File

Create the file `Sample.java`:

```java
package demo;

public final class Sample {
    static {
        System.out.println("Sample initialized");
    }

    public static String greet() {
        return "hello";
    }
}
```

### 8.2. The FailureKindsDemo.java File

Create the file `FailureKindsDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class FailureKindsDemo {
    enum Mode {
        MISSING, MALFORMED, NEWER, WRONG_NAME, VALID
    }

    static final class TestLoader extends ClassLoader {
        private final Path root;
        private final Mode mode;

        TestLoader(Path root, ClassLoader parent, Mode mode) {
            super(parent);
            this.root = root;
            this.mode = mode;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            String relativePath = mode == Mode.WRONG_NAME
                    ? "demo/Sample.class"
                    : name.replace('.', '/') + ".class";

            byte[] bytes;
            try {
                bytes = Files.readAllBytes(root.resolve(relativePath));
            } catch (IOException cause) {
                throw new ClassNotFoundException(name, cause);
            }

            if (mode == Mode.MALFORMED) {
                bytes[0] = 0; // Corrupt the CAFEBABE magic.
            } else if (mode == Mode.NEWER) {
                bytes[6] = (byte) 0x7F; // Very high major version.
                bytes[7] = (byte) 0x7F;
            }

            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of("plugin-classes");
        ClassLoader parent = FailureKindsDemo.class.getClassLoader();

        for (Mode mode : Mode.values()) {
            TestLoader loader = new TestLoader(root, parent, mode);

            String name = switch (mode) {
                case MISSING -> "demo.Absent";
                case WRONG_NAME -> "demo.WrongName";
                default -> "demo.Sample";
            };

            try {
                Class<?> type = loader.loadClass(name);
                System.out.println(mode + " -> loaded: " + type.getName());

                if (mode == Mode.VALID) {
                    Object greeting =
                            type.getMethod("greet").invoke(null);
                    System.out.println("invoke: " + greeting);
                }
            } catch (ClassNotFoundException | LinkageError error) {
                System.out.println(
                        mode + " -> " + error.getClass().getSimpleName()
                );
            }
        }
    }
}
```

**Purpose of each step:**

- `TestLoader.findClass` looks for the file when the parent does not have the class. If `Files.readAllBytes` throws `IOException`, it converts it to `ClassNotFoundException(name, cause)`, preserving the original cause.
- `MALFORMED` corrupts the magic of the bytes: the data is no longer a valid class file.
- `NEWER` replaces the **major** at offsets 6–7 of the class file header with `0x7F7F` (32767): Java 17 does not support that version, while the other bytes still come from a valid class file.
- `WRONG_NAME` requests `demo.WrongName` but loads bytes declaring the name `demo.Sample`. `defineClass(name,...)` detects the binary name mismatch.
- `VALID` defines and returns `demo.Sample` with the right name; the static initializer only runs when reflection actually invokes `greet()`.

### 8.3. Compiling and Running

Create a separate plugin directory. On Bash:

```bash
mkdir -p plugin-classes
```

On PowerShell:

```powershell
New-Item -ItemType Directory -Force plugin-classes | Out-Null
```

Compile **with JDK 17**:

```bash
javac --release 17 -d plugin-classes Sample.java
javac --release 17 FailureKindsDemo.java
java -cp . FailureKindsDemo
```

Resulting files:

```text
working-directory/
├── Sample.java
├── FailureKindsDemo.java
├── FailureKindsDemo.class
├── FailureKindsDemo$Mode.class
├── FailureKindsDemo$TestLoader.class
└── plugin-classes/
    └── demo/
        └── Sample.class
```

**Test condition:** `plugin-classes` is **not on the host's `-cp`**. If you add `plugin-classes` to the application classpath, the parent loader may find `demo.Sample` first, and the custom `findClass` branch will not be called for that name.

### 8.4. Stdout on JDK 17

```text
MISSING -> ClassNotFoundException
MALFORMED -> ClassFormatError
NEWER -> UnsupportedClassVersionError
WRONG_NAME -> NoClassDefFoundError
VALID -> loaded: demo.Sample
Sample initialized
invoke: hello
```

**Breakdown in order:**

1. `MISSING`: the parent does not have `demo.Absent`; the child looks for `plugin-classes/demo/Absent.class` but does not find it, so it throws `ClassNotFoundException`.
2. `MALFORMED`: the parent does not have `demo.Sample`; the child reads the real file but modifies its magic. The JVM receives invalid bytes and throws `ClassFormatError`.
3. `NEWER`: reads the real file and sets an unsupported major version. The JVM classifies it as `UnsupportedClassVersionError`, **a specific kind of `ClassFormatError`**.
4. `WRONG_NAME`: the class file content is actually `demo.Sample`, but `defineClass` is requested with the name `demo.WrongName`; the error is `NoClassDefFoundError`, usually containing "wrong name" information in the actual message.
5. `VALID`: the class is defined successfully and prints `loaded: demo.Sample`. `loadClass` does not yet require running the static initializer; when calling `greet` via reflection, it prints `Sample initialized` and then `invoke: hello`.

The example prints **only the error class name** via `getClass().getSimpleName()` to get stable stdout. Detailed JVM messages may differ by JDK version and should not be used as hardcoded test strings. In real systems, you need to preserve **message + cause + stack trace** to know the error source and loading path.

### 8.5. What If You Run with a Newer Java Version?

The `NEWER` branch uses major `32767`, well above the class-file major versions of existing Java releases. It was chosen to simulate an unsupported version in the demo, **not** as a recommendation to edit bytes to "upgrade the class version".

For production data, do not manually edit headers; use the compiler with the appropriate target or inspect using `javap -verbose`. This experiment only helps observe **error classification**.

## 9. Why Is NoClassDefFoundError Different from ClassNotFoundException?

The names of the two errors are similar, but their relationship is not the same:

- `ClassNotFoundException` is a **checked Exception** that typically occurs when **code explicitly asks a loader to find a binary name and the loader cannot find it**.
- `NoClassDefFoundError` is a **LinkageError** that typically occurs when the JVM needs a definition to **link or execute a referenced class** but cannot supply it; in addition, there are distinct paths when the binary name in the bytes does not match `defineClass`, or when the class previously failed initialization.

For example, an application is compiled with the library `lib.Helper`, but at runtime only `App.class` remains without `lib.Helper.class`. A call to `Helper` in App code can cause a `NoClassDefFoundError` when the JVM needs to load that dependency class. Do not interpret this as the caller of `App` having directly called `ClassLoader.loadClass("lib.Helper")` and caught `ClassNotFoundException`.

In the JDK, a `ClassNotFoundException` can also sit nested inside the **cause** of a `NoClassDefFoundError`, depending on the loading path. When encountering `NoClassDefFoundError`, you must inspect both the message and the cause, not just the exception name.

### When a Class Has Failed Initialization

The first time code touches a class whose static initializer throws an exception that is not an `Error`, the JVM typically wraps it in `ExceptionInInitializerError`. The class enters an erroneous state; subsequent initialization attempts for the same runtime class typically throw `NoClassDefFoundError` with the message "Could not initialize class ...".

This is **not** evidence of a missing class file. Changing the classpath without checking the static initializer can end up fixing the wrong problem.

## 10. Separate Example: Class Loaded Successfully, but Initializer Fails

Create `InitFailureDemo.java`:

```java
public final class InitFailureDemo {
    static final class Broken {
        static int value = initialize();

        static int initialize() {
            throw new IllegalStateException("invalid configuration");
        }
    }

    public static void main(String[] args) throws Exception {
        String name = "InitFailureDemo$Broken";
        ClassLoader loader = InitFailureDemo.class.getClassLoader();

        System.out.println("loaded: "
                + (Class.forName(name, false, loader) != null));

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                Class.forName(name, true, loader);
            } catch (LinkageError error) {
                System.out.println(
                        attempt + ": " + error.getClass().getSimpleName()
                );
            }
        }
    }
}
```

Run:

```bash
javac --release 17 InitFailureDemo.java
java InitFailureDemo
```

Stdout:

```text
loaded: true
1: ExceptionInInitializerError
2: NoClassDefFoundError
```

The call `forName(..., false, ...)` succeeds, showing that the JVM **found the class** without requiring the initializer to run. The first `initialize=true` call fails because of the code in `Broken`, not because of a missing class file. On the next attempt, the class remains erroneous and does not run the initializer again.

**Debugging rule:** find the **first error that appeared**, because a subsequent chain of "Could not initialize class" errors may only be a secondary consequence.

## 11. Do Not Mask LinkageError by Falling Back to Another Loader

A custom ClassLoader following parent-first delegation typically does:

```text
findLoadedClass(name)
       ↓ not yet loaded
parent.loadClass(name)
       ↓ parent throws ClassNotFoundException
findClass(name)
```

The normal fallback condition is that the parent **did not find the class**, not that the parent threw just any error. If the parent found bytes but threw `ClassFormatError` or `VerifyError`, the default algorithm **does not silently switch to another copy of the class** in the child.

This is an important principle for plugin loaders:

- **Not found**: you may try the next class source according to the designed lookup policy.
- **Found but corrupted**: report the error; do not pretend the class does not exist.
- **Class has a newer version than the runtime**: arbitrarily switching to older bytes can hide build/deploy bugs. If controlled fallback is desired, explicitly design the artifacts/versions or a **multi-release JAR** per the spec, rather than catching `UnsupportedClassVersionError` and silently loading an unverified alternative class.
- **Security or package definition error**: do not swallow the error to bypass access policies.

In particular, inside a `loadClass` override, never use:

```java
// ANTI-PATTERN — do not run directly:
try {
    return parent.loadClass(name);
} catch (Throwable ignored) {
    return findClass(name);
}
```

Doing so can turn a corrupted bytecode error in the parent into loading a different copy of the class. This produces hard-to-reproduce results and risks class-identity and runtime-package conflicts.

## 12. Other Linkage Errors That Are Not "Class File Not Found"

### 12.1. NoSuchMethodError / NoSuchFieldError

These usually involve **binary incompatibility**: the caller class was compiled against API version A, whereas at runtime the loader loads dependency version B, which lacks the corresponding method/field.

Example of API source:

```java
// Library v1:
public class Api {
    public static String version() {
        return "v1";
    }
}
```

The caller is compiled against v1 and calls `Api.version()`. If at runtime it is replaced with library v2 where that method was removed, the JVM may throw `NoSuchMethodError` when resolving the call.

The snippet above only **illustrates two library versions**, not a standalone runnable file demonstrating the error. The fix is to clarify runtime dependencies and preserve binary compatibility, not to catch `ClassNotFoundException`.

### 12.2. IllegalAccessError

`IllegalAccessError` occurs when the JVM finds a field/method/class, but runtime access conditions are not satisfied. With custom loaders, two classes sharing the same textual package name but defined by **different defining loaders** **do not automatically belong to the same runtime package**. Therefore, code whose package-private access succeeded at compile time or under the same loader may fail in a different loader layout.

Do not handle access errors by substituting `ClassNotFoundException`, because the class **was already found**.

### 12.3. IncompatibleClassChangeError and Duplicate Definition

`IncompatibleClassChangeError` covers many binary contract changes, such as a static/instance mismatch. Calling `defineClass` directly multiple times for the same binary name within the same defining loader can cause a `LinkageError` due to duplicate class definition. The default `ClassLoader.loadClass` implementation checks `findLoadedClass` and uses appropriate locking to avoid some of these issues.

Do not call `findClass(name)` directly from client code when performing normal lookup operations: doing so can bypass the caching, delegation, and synchronization of `loadClass` and cause hard-to-control errors.

## 13. Catching Errors Properly at the Application Layer

At the **plugin/module loading boundary**, you can classify errors for logging and decision-making:

```java
// Excerpt inside a method with variables:
// ClassLoader loader; String binaryName;

try {
    Class<?> type = loader.loadClass(binaryName);
    useType(type);
} catch (ClassNotFoundException ex) {
    report("Class not found in configured sources", ex);
} catch (UnsupportedClassVersionError ex) {
    report("Class version not supported by this JVM", ex);
} catch (ClassFormatError ex) {
    report("Malformed or incompatible class-file format", ex);
} catch (VerifyError ex) {
    report("Bytecode verification failed", ex);
} catch (NoClassDefFoundError ex) {
    report("Required definition unavailable or class init failed", ex);
} catch (LinkageError ex) {
    report("Other JVM linkage failure", ex);
}
```

This is an **excerpt**; `useType` and `report` are application-defined methods, not standard Java APIs. The `catch` order matters: `UnsupportedClassVersionError` comes before `ClassFormatError`, and specialized cases come before `LinkageError`.

**Caution:** if a plugin API is used within a framework, it is not necessarily appropriate to catch `LinkageError` **everywhere**. Usually only boundary layers with an explicit plugin-management or fail-fast policy should do so. Do not catch Error and "keep running as if nothing happened". The system may already be in an inconsistent state.

### Preserving Diagnostic Information

A minimal log entry should include:

- **Requested binary name** (for example, `demo.Sample`).
- **ClassLoader and parent chain**; if available, the defining loader of the class actually returned.
- **Class file source**: URL, JAR entry, path, artifact version, and checksum if helpful.
- **JVM runtime** (feature version, vendor).
- **Error type, message, cause chain, suppressed exceptions**.
- **Phase when it occurred**: find bytes, defineClass, resolve/verify, initialize, or during method invocation.
- **Executing thread and TCCL** if the framework uses service/provider discovery.

Do not include sensitive data such as credentials or tokens in source URLs in production logs. When inspecting URLs from network sources, redact query strings or authentication details appropriately.

## 14. Diagnostics with javap, File Headers, and JVM Logs

### 14.1. Inspecting the Deployed Class File

```bash
javap -verbose -classpath plugin-classes demo.Sample
```

Look for useful details:

- `major version` and `minor version`.
- `this_class` corresponding to `demo/Sample`.
- Constant pool, method descriptors, bytecode, and attributes.

With the `javac --release 17` compilation command in the example, the `major version` of `demo.Sample` is **61**, and minor is normally **0**.

If `javap` cannot read it, check whether the file is actually a `.class` file and whether it was truncated/corrupted; this does not mean the JVM will necessarily throw the exact same error and message as `javap`.

### 14.2. Checking the Right JDK Runtime

```bash
java -version
javac -version
```

`java` and `javac` can come from two different JDK installations via PATH, IDE, Maven/Gradle toolchain, container image, or CI. A newer `javac` does not make an older runtime JVM understand newer bytecode.

### 14.3. Class Load Logging

With HotSpot supporting unified logging:

```bash
java -Xlog:class+load=info -cp . FailureKindsDemo
```

The log helps observe class loading and part of the class source, but class load logs should not be treated as **logging every step of findClass, verification, resolution, or initialization**. To know exactly what code inside a custom loader is doing, add logging before `Files.readAllBytes` and before `defineClass`, while avoiding logging potentially sensitive data.

### 14.4. Bytecode Transformers and Agents

If code only fails when run with a Java agent, AOP/ORM proxy, or bytecode enhancer, compare:

1. The **original** class file bytes before transformation.
2. The bytes **after transformation** right before `defineClass`.
3. The JVM version and the transformer library version.
4. Whether attributes such as `StackMapTable` were generated/updated properly.

Do not inspect only the Java source code: valid source can still have its bytecode broken by a transformer.

## 15. Caution with Already-Loaded Classes and Error Reproduction

Once a custom loader has successfully defined `demo.Sample`:

```java
Class<?> first = loader.loadClass("demo.Sample");
Class<?> second = loader.loadClass("demo.Sample");
System.out.println(first == second); // true, with the same default loader
```

This is an **excerpt**. If you replace `Sample.class` with a corrupted file **after a successful load**, the next default `loadClass` call typically uses `findLoadedClass` and **does not re-read the new file**. That can make an experiment appear as if "corrupted bytecode still loads" if you forget the class was already cached.

To test the new file:

- Run a **new JVM**, or
- Create a **new defining ClassLoader** with an appropriate parent layout, ensuring it does not delegate to a parent that already holds a class with the same name.

Similarly, if a class initializer has failed and the class has become erroneous, the JVM does not automatically retry initialization for **the same runtime class** on every call. Creating another class file on disk does not clear the erroneous state of that runtime class.

## 16. Decision Flow When a Plugin Load Fails

```text
Cannot use plugin class
          │
          ▼
Is there a ClassNotFoundException?
    ├─ Yes → binary name / path / URL / JAR / parent / permissions
    └─ No
          │
          ▼
Is there an UnsupportedClassVersionError?
    ├─ Yes → compare major/minor with Java runtime, --release
    └─ No
          │
          ▼
Is there a ClassFormatError?
    ├─ Yes → corrupted bytes / invalid structure / wrong file read
    └─ No
          │
          ▼
Is there a VerifyError?
    ├─ Yes → bytecode generator, StackMapTable, types/stack
    └─ No
          │
          ▼
Is there a NoClassDefFoundError?
    ├─ Yes → dependency, wrong name, failed initialization
    └─ No
          │
          ▼
Is there another LinkageError?
    ├─ Yes → binary API, access, class identity
    └─ No → inspect other application/framework exceptions
```

**This is a triage workflow**, not an exhaustive list of every JVM error. A plugin can have multiple issues at the same time; fix the first error and re-run in a **clean environment** to identify the next one.

## 17. Common Mistakes When Writing a ClassLoader

| Anti-pattern | Why is it wrong? | How to fix |
|---|---|---|
| Catching `Throwable` in `findClass` and throwing CNFE | Hides bytecode, linkage, OOME, and security issues | Only convert appropriate IOExceptions into CNFE; let Errors propagate |
| Concluding a class is valid just because the file exists | Bytes may have invalid magic/constant pool/major version/verification | Call `defineClass` so the JVM verifies it, and check logs |
| Treating `UnsupportedClassVersionError` like a "missing file" error | The JVM already read the class, but does not support its version | Check runtime, target, and recompile |
| Catching `ClassFormatError` before `UnsupportedClassVersionError` | The version branch is never reached | Catch the subclass first |
| Intercepting `LinkageError` and always falling back to the child | May substitute a copy of the class improperly, breaking identity | Fall back only when not found according to the defined policy |
| Writing a custom loader while forgetting binary names | `defineClass` may throw `NoClassDefFoundError: wrong name` | Map names/paths accurately; do not alter packages on your own |
| Loading from a new JAR using an old loader | `findLoadedClass` returns the old class | Use a new loader or a new process |
| Reusing a single JVM for all test variants | Loaded/initialized state prevents independent results | Use a separate loader or a separate process |
| Seeing `NoClassDefFoundError` and only changing the classpath | May be caused by failed initialization or wrong name | Read the message/cause and check the first error |
| Ignoring `VerifyError` because the source compiles | A transformer may produce invalid bytecode | Inspect the post-transformation bytes |
| Disabling the verifier to "fix" the error | Hides invalid bytecode and breaks JVM safety guarantees | Fix the generator/transformer |
| Not recording loader identity when debugging | Two classes with the same name can have different runtime types | Log the defining loader and source path |

## 18. Self-Check Exercises

1. **The class is not on the classpath and `findClass` cannot locate the file—which error is appropriate?** `ClassNotFoundException`.
2. **A loader reads four random bytes and calls `defineClass`—is it guaranteed to be CNFE?** No; if the JVM sees the bytes are not a valid class file, it throws `ClassFormatError`.
3. **What happens if Java 17 encounters Java 21 bytecode with major version 65?** It can throw `UnsupportedClassVersionError`, not "class not found".
4. **Is `UnsupportedClassVersionError` a subclass of `ClassFormatError`?** Yes.
5. **If a class file is structurally valid, yet an operand stack operation violates type safety, what error typically occurs?** `VerifyError`.
6. **What can `defineClass("p.Other", bytesOfPActual, ...)` throw?** `NoClassDefFoundError` due to a binary name mismatch.
7. **A class loads successfully, but its static initializer throws `IllegalStateException`—what can be observed on the first attempt and subsequent attempts?** `ExceptionInInitializerError`, then `NoClassDefFoundError`.
8. **Should you catch every LinkageError and convert it into CNFE?** No; doing so loses the real root cause and hinders triage.
9. **If the parent has a structurally invalid class file, does the child loader automatically try a file of the same name in its own directory?** No; default parent-first delegation only falls back when the parent fails to find the class per contract, without swallowing Errors.
10. **Do `ClassNotFoundException` and `NoClassDefFoundError` share the same direct superclass?** No; one branch is a checked Exception, while the other is a LinkageError.
11. **Why does the demo use a new loader for each mode?** So that a class already defined in another mode is not reused via `findLoadedClass`.
12. **Is a class file with a valid header and matching major version guaranteed to succeed when used by the JVM?** No; there are still verification, binary dependencies, access checks, and initialization.
13. **What should you do to be sure which bytecode the runtime is actually using?** Identify the JVM, loader, actual JAR entry/path, and inspect the bytes, `javap` output, and logs.
14. **If the class file version is supported but a method is missing at runtime, what error can occur?** `NoSuchMethodError` due to binary incompatibility.

## Official Documentation

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findClass`, `defineClass`, binary names, handling CNFE, and errors when defining classes.
- [Java SE 21 — ClassFormatError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassFormatError.html): malformed or uninterpretable class file.
- [Java SE 21 — UnsupportedClassVersionError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/UnsupportedClassVersionError.html): major/minor version errors and inheritance relationship with ClassFormatError.
- [Java SE 21 — VerifyError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/VerifyError.html): JVM verification errors.
- [Java SE 21 — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/NoClassDefFoundError.html): class definition is no longer available along the path required by the JVM.
- [JVM Specification — §4 The Class File Format](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html): class file format, major/minor versions, constant pool, bytecode attributes.
- [JVM Specification — §5 Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html): loading, resolution, verification, and class initialization.

**Conclusion:** When a custom loader cannot use a class, distinguish between **"bytes not found"** (`ClassNotFoundException`), **"bytes present but not a valid class"** (`ClassFormatError`), **"unsupported class version"** (`UnsupportedClassVersionError`), **"bytecode fails the verifier"** (`VerifyError`), and **"linkage/initialization failed"** (the `LinkageError`s). Preserving the original error type and root cause is the key to fixing the right classpath, JDK target, bytecode generator, or dependency structure.
