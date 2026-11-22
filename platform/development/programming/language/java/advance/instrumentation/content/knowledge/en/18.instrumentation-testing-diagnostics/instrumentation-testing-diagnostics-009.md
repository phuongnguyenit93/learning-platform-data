# Reproducing Missing Helper, Wrong Module, VerifyError, ClassFormatError, and LinkageError

A Java instrumentation agent can return a `byte[]` from `ClassFileTransformer.transform` without throwing an error, yet when the JVM defines or links the transformed class, the application still encounters `NoClassDefFoundError`, `VerifyError`, `ClassFormatError`, or `LinkageError`. The cause is not always in the transformer code: a helper may be missing, have the wrong version, lie outside the class loader's visibility, or a named module may not allow access. To diagnose accurately, we need to **reproduce each error individually, with a working control**, and know at which stage the error arises.

This lesson belongs to the **Testing and Diagnostics** group in Java Advance – instrumentation. It builds a lab using Java 17+ with no external libraries, covering these scenarios:

1. Missing helper → `NoClassDefFoundError` (often with `ClassNotFoundException` as its cause).
2. Helper exists but has the wrong method ABI → `NoSuchMethodError`.
3. Named module not opened for deep reflection → `InaccessibleObjectException`.
4. Classfile bytes with corrupted magic number → `ClassFormatError`.
5. Method declared to return `int` but bytecode uses `areturn` → `VerifyError`.
6. A defining class loader redefines the same binary name → `LinkageError`.
7. Both format/verify errors are reproduced again **through a real Java agent**, illustrating the step where the JVM checks the output after the transformer callback.

**All cases were actually compiled and run using OpenJDK 24 with `javac --release 17`**; the key results are recorded below. The exception type and mechanism are what matter to learn, while log prefixes, stack trace line numbers, or message details may differ across JVM implementations.

**Use only on a test directory and a separate JVM.** The bytecode mutations below **intentionally create invalid classfiles**; do not attach a bytecode-corrupting agent to a running application or real data. Each negative test is run in a fresh JVM to avoid class loading/resolution state from the previous run.

## 1. Do Not Lump Every Error Under One “instrumentation failed” Label

~~~text
Source class / JAR / module
          |
          v
Look up class name in defining loader
          |-- missing helper --------> NoClassDefFoundError
          v
Parse classfile structure
          |-- bad magic / constant pool -> ClassFormatError
          v
Verify instructions + operand stack
          |-- wrong value type -------> VerifyError
          v
Link / resolve symbolic references
          |-- method does not exist --> NoSuchMethodError
          |-- loader identity error --> LinkageError
          v
Check module / reflection permissions
          |-- private reflection blocked -> InaccessibleObjectException
          v
Run method and business logic
~~~

This is a **map of check categories**, not a rigid JVM schedule. According to the Java Virtual Machine Specification (JVMS), the JVM may resolve certain symbolic references eagerly or lazily when an instruction is actually used. A link error can arrive **after** the class loads successfully or at the time it is prepared/verified by the JVM. You need to record the **stage and cause chain**, not just a single final console line.

### 1.1. The Error Hierarchy Matters

~~~text
java.lang.Error
  └── LinkageError
       ├── NoClassDefFoundError
       ├── ClassFormatError
       │    └── UnsupportedClassVersionError
       ├── VerifyError
       ├── IncompatibleClassChangeError
       │    ├── NoSuchMethodError
       │    ├── NoSuchFieldError
       │    └── IllegalAccessError
       └── many other linkage errors

java.lang.RuntimeException
  └── java.lang.reflect.InaccessibleObjectException
~~~

`VerifyError` and `ClassFormatError` **both belong to the `LinkageError` family**. Therefore, case 6 intentionally uses a **different cause** (duplicate class definition) to demonstrate `LinkageError` directly. `InaccessibleObjectException` does not belong to this family: it is a reflection API error when suppressed access checks cannot be enabled.

| Error | First Question to Ask |
| --- | --- |
| `ClassNotFoundException` | Does the explicit class lookup (e.g., `Class.forName`) have the right name/loader/path? |
| `NoClassDefFoundError` | Does the bytecode/loader have a dependency that cannot be defined or initialized? |
| `NoSuchMethodError` | Does the runtime helper class have the **exact owner/name/descriptor** recorded in the caller? |
| `InaccessibleObjectException` | Is the package belonging to the named module **open to the caller module**? |
| `ClassFormatError` | Do the bytes follow valid classfile structure, magic, constant pool, and attributes? |
| `VerifyError` | Are the operand stack, return opcode, types, control flow, and stack map valid? |
| `LinkageError` from duplicate | Is the same loader trying to `defineClass` the same binary name a second time? |

**Do not confuse checked `ClassNotFoundException` with `NoClassDefFoundError`.** The second is an `Error` at the point the JVM needs to define or resolve a class. It may carry a `ClassNotFoundException` as its cause, but it can also have other causes such as failed class initialization. You must read the entire root cause.

## 2. Files for the Java 17+ Lab

Create a dedicated directory with the following structure:

~~~text
fault-lab/
  src/
    helper-v1/demo/helper/Probe.java
    helper-v2/demo/helper/Probe.java
    app/demo/app/Caller.java
    app/demo/app/Main.java
    fixture/demo/bytes/Target.java
    fixture/demo/bytes/Run.java
    demo.secret/module-info.java
    demo.secret/demo/secret/Secret.java
    tools/ModuleCheck.java
    tools/FaultLab.java
    agent/CorruptingAgent.java
  MANIFEST.MF

  build/             (javac creates the output directories)
  mods/demo.secret/  (exploded named module)
  corrupt-agent.jar  (startup agent JAR)
~~~

The two `Probe.java` files in `helper-v1` and `helper-v2` have the **same binary name but different methods**. They are only used as two variants **not placed together on the runtime classpath**. The other cases use the `demo.bytes.Target` classfile fixture and test harnesses in two independent classes.

Read the structure first, then create the **exact files** according to each section below. The example is completely independent of any existing project source code.

## 3. Missing Helper Case: `NoClassDefFoundError`

First, create the helper with the static method the caller needs:

**`src/helper-v1/demo/helper/Probe.java`**

~~~java
package demo.helper;

public final class Probe {
    public static String label() {
        return "helper-ok";
    }
}
~~~

**`src/app/demo/app/Caller.java`**

~~~java
package demo.app;

public final class Caller {
    public static String call() {
        return demo.helper.Probe.label();
    }
}
~~~

**`src/app/demo/app/Main.java`**

~~~java
package demo.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("RESULT=" + Caller.call());
    }
}
~~~

`Caller.class` contains a symbolic method reference to `demo/helper/Probe.label:()Ljava/lang/String;`. This is similar to bytecode injected by a transformer into an application class when it wants to call a telemetry helper.

At **compile** time, we place helper-v1 on the classpath so `javac` can resolve the method. At **run** time, we intentionally **omit the helper** to create a mismatch between the compile-time classpath and the runtime classpath.

Working control:

~~~text
RESULT=helper-ok
~~~

The tested missing-helper case produces these key identifying lines:

~~~text
java.lang.NoClassDefFoundError: demo/helper/Probe
Caused by: java.lang.ClassNotFoundException: demo.helper.Probe
~~~

This is an **excerpt of the core lines** of the stack trace, not stdout from the `Main` program. On the test JVM, the command exited with exit code `1` and `RESULT=...` was not printed.

**Java agent connection:** a helper packaged inside an agent JAR is not necessarily visible to the defining loader of the class being instrumented. A bootstrap class does not automatically look down into the system loader; a child/plugin loader may have its own delegation/isolation rules. `Instrumentation.appendToSystemClassLoaderSearch` only extends the search of the **system loader**, whereas `appendToBootstrapClassLoaderSearch` is a different API. If the helper is placed in a named module, readability/exports/opens must also be considered depending on the access type.

### 3.1. Finding Out Whether the JAR Is Missing or the Defining Loader Is Wrong

Two situations can produce similar symptoms:

- There is no `helper.jar` file in the runtime environment: a **packaging/classpath** error.
- The file is present and the agent can load it, but the loader defining the class with the call cannot see the helper: a **loader topology/module access** error.

Do not rely solely on `jar --list` to conclude. Combine information about the JAR's location, the class loader of **the class containing the invocation**, the helper's class loader if it can be loaded, and the module objects. Do not call `Class.forName` on the class **currently being defined by the JVM** inside `transform` to “test the helper”: that can cause reentrant loading or class circularity.

## 4. Helper Present but Wrong ABI Version: `NoSuchMethodError`

**`src/helper-v2/demo/helper/Probe.java`**

~~~java
package demo.helper;

public final class Probe {
    public static String renamed() {
        return "helper-v2";
    }
}
~~~

`Caller.class` was still compiled against helper-v1, so it expects the method `label()Ljava/lang/String;`. However, at runtime we only provide helper-v2, where that method **does not exist**, even though the class `demo.helper.Probe` can still be loaded. The tested JVM throws:

~~~text
java.lang.NoSuchMethodError:
  'java.lang.String demo.helper.Probe.label()'
~~~

**The difference:** a missing helper means the class cannot be found; a wrong ABI means the class was found, but **a method with the exact signature could not be found**. `NoSuchMethodError` is a subclass of `IncompatibleClassChangeError`, which in turn extends `LinkageError`.

Real-world instrumentation scenario:

~~~text
Injected bytecode:
  invokestatic demo/helper/Probe.hit:(Ljava/lang/String;)V

Actual runtime helper:
  static void hit(Object event)
~~~

This is a **bytecode/contract description**, not standalone Java source. The descriptor `(Ljava/lang/String;)V` **does not match** `(Ljava/lang/Object;)V` even though the Java source types have a subtype relationship. JVM resolution uses the exact symbolic reference, rather than performing overload resolution like the Java compiler. If a method is changed from static to instance, you may encounter `IncompatibleClassChangeError` instead of `NoSuchMethodError`. Therefore, always compare **owner, name, descriptor, and opcode**.

If a helper class has already been loaded from v2, appending v1.jar afterward does not “hot-swap” the old class in the same loader. ABI tests must run in a fresh JVM and place only **one helper version** on the runtime classpath.

## 5. Wrong Module: Deep Reflection Permission Differs from Class Visibility

Create a named module without `exports` or `opens`:

**`src/demo.secret/module-info.java`**

~~~java
module demo.secret {
}
~~~

**`src/demo.secret/demo/secret/Secret.java`**

~~~java
package demo.secret;

public final class Secret {
    private static String reveal() {
        return "inside";
    }
}
~~~

**`src/tools/ModuleCheck.java`**

~~~java
import java.lang.reflect.InaccessibleObjectException;

public final class ModuleCheck {
    public static void main(String[] args) throws Exception {
        Module secret = ModuleLayer.boot()
                .findModule("demo.secret").orElseThrow();
        Module caller = ModuleCheck.class.getModule();

        System.out.println("OPEN="
                + secret.isOpen("demo.secret", caller));

        Class<?> type = Class.forName("demo.secret.Secret");
        var method = type.getDeclaredMethod("reveal");

        try {
            method.setAccessible(true);
            System.out.println("REFLECT=" + method.invoke(null));
        } catch (InaccessibleObjectException ex) {
            System.out.println("REFLECT=BLOCKED");
        }
    }
}
~~~

Here `ModuleCheck` is on the classpath, so it belongs to an **unnamed module**. `Secret` is in a **named module** whose package is not open. It is possible to obtain class metadata by name, but `setAccessible(true)` to invoke the private method is blocked.

Without opens permission:

~~~text
OPEN=false
REFLECT=BLOCKED
~~~

Add the right JVM flag:

~~~bash
--add-opens=demo.secret/demo.secret=ALL-UNNAMED
~~~

Result:

~~~text
OPEN=true
REFLECT=inside
~~~

Both sets of stdout ran properly with the module resolved via `--add-modules demo.secret`.

### 5.1. Three JPMS Concepts That Must Not Be Confused

| Condition | How to Check | Typical Configuration |
| --- | --- | --- |
| Is the module resolved in the layer? | `ModuleLayer.boot().findModule("demo.secret")` | `--module-path` + `--add-modules` |
| Does module M read N? | `M.canRead(N)` | `requires`, `--add-reads`, or `extraReads` |
| Is the package open for deep reflection? | `M.isOpen("pkg", caller)` | `opens`, `--add-opens`, or `extraOpens` |
| Is the public API exported? | `M.isExported("pkg", caller)` | `exports`, `--add-exports`, or `extraExports` |

`InaccessibleObjectException` in `setAccessible` **differs from** `IllegalAccessError` when the JVM checks access permissions of a symbolic reference in bytecode. Thus, “wrong module” does not map to a single exception type. `--add-opens` handles deep reflection, but it does not create a missing module or fix a `VerifyError`.

A Java agent can use `Instrumentation.redefineModule(...)` to **expand** the reads/exports/opens relationships of an existing module, if `isModifiableModule` permits. This is an **additive** operation that does not allow revoking granted permissions; it does not resolve new modules or replace classfile method bodies. You must choose narrow packages and target modules so as not to accidentally expose too much private state.

### 5.2. Why Does the Module Test Need Two JVMs?

When running with `--add-opens`, permission is granted right at startup; it is not a toggle switch within the same process that can be “closed again” after testing. Run the CLOSED and OPEN cases in **two separate java commands**. With `Instrumentation.redefineModule`, added read/open edges are not automatically revoked just because agent code changes configuration or a transformer is removed.

## 6. Classfile Format Errors and Bytecode Verification Errors Are Two Different Layers

A valid JVM classfile begins with the magic number:

~~~text
CA FE BA BE
~~~

After the magic come `minor_version`, `major_version`, the constant pool, and the fields/methods/attributes tables. Format checking detects bad magic, wrong length/truncation, and malformed constant pool/descriptors. That is the role of `ClassFormatError`.

Verifying goes deeper: instruction operand stack types must be correct, branch targets must be valid, and stack-map frames and return types must obey verifier constraints. That is the role of `VerifyError`.

A classfile can **pass format checking and still fail verification**. For example, if a method is declared `()I` (returns int) but the return opcode is `areturn` (returns a reference) while the stack holds an integer, the JVM rejects it with `VerifyError`.

### 6.1. Valid Fixture Before Corruption

**`src/fixture/demo/bytes/Target.java`**

~~~java
package demo.bytes;

public final class Target {
    public static int answer() {
        return 42;
    }
}
~~~

With `javac --release 17` in the lab, the method `answer()I` contains the instructions:

~~~text
bipush 42  -> bytes 10 2A
ireturn    -> byte  AC
~~~

Only within the lab, we will replace `AC` with `B0` (`areturn`) to produce a VerifyError. The method still carries the descriptor `()I`, creating a **mismatch between the operand stack type and the opcode**.

To produce a ClassFormatError, clone the valid bytes and change `bytes[0]=0` to corrupt the magic. Neither operation **overwrites** the class file that `javac` just produced.

### 6.2. Avoid Copying Raw Byte Patching Into Production

The pattern `10 2A AC` is a **verified match for this fixture** for `return 42;`. In an arbitrary classfile, those bytes might appear in the constant pool or attributes rather than in code. Therefore, the test harness counts **exactly one match** and throws an error if that fails; you must never use scanning for these three bytes as a bytecode parser.

A production transformer must use a library for reading/building classfiles that supports the corresponding bytecode version; it must preserve constant pool references, labels, exception tables, `StackMapTable`, `max_stack`, and method descriptors. The JVM verifier is the last line of defense, **not** a substitute for transformer unit tests.

## 7. LinkageError from Defining the Same Binary Name and Defining Loader Twice

A class in the JVM is identified not by name alone. **Binary name + defining class loader** is a key part of class identity. Two different class loaders can define classes with the same name (though loader constraints may impose additional restrictions). However, a single loader cannot **redefine the same name** with `defineClass` a second time.

We chose this error to reproduce `LinkageError` separately from the subclasses discussed above. In the test:

~~~text
IsolatedLoader L
   |
   +-- defineClass(bytes of demo.bytes.Target) -> succeeds
   |
   +-- defineClass(same bytes and name)        -> LinkageError
~~~

This is not the same as a parent-first application class loader picking up an existing class from its parent: that situation may not invoke `defineClass` a second time. The test intentionally calls `defineClass` twice so the error is repeatable.

### 7.1. `src/tools/FaultLab.java` — Full Harness

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public final class FaultLab {
    static final class IsolatedLoader extends ClassLoader {
        IsolatedLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        Class<?> define(byte[] bytes) {
            return defineClass(null, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] valid = Files.readAllBytes(Path.of(args[0]));

        byte[] malformed = valid.clone();
        malformed[0] = 0;
        try {
            new IsolatedLoader().define(malformed);
            System.out.println("FORMAT=UNEXPECTED");
        } catch (ClassFormatError expected) {
            System.out.println("FORMAT=ClassFormatError");
        }

        byte[] invalidCode = valid.clone();
        int matches = 0;
        for (int i = 0; i + 2 < invalidCode.length; i++) {
            if ((invalidCode[i] & 255) == 0x10
                    && (invalidCode[i + 1] & 255) == 0x2a
                    && (invalidCode[i + 2] & 255) == 0xac) {
                invalidCode[i + 2] = (byte) 0xb0;
                matches++;
            }
        }

        if (matches != 1) {
            throw new IllegalStateException(
                    "Expected one bipush 42;ireturn");
        }

        try {
            Class<?> invalid = new IsolatedLoader().define(invalidCode);
            invalid.getDeclaredMethod("answer");
            System.out.println("VERIFY=UNEXPECTED");
        } catch (VerifyError expected) {
            System.out.println("VERIFY=VerifyError");
        }

        IsolatedLoader loader = new IsolatedLoader();
        loader.define(valid);
        try {
            loader.define(valid);
            System.out.println("DUPLICATE=UNEXPECTED");
        } catch (LinkageError expected) {
            System.out.println("DUPLICATE=LinkageError");
        }
    }
}
~~~

**Why does this work?**

- `IsolatedLoader` uses the **platform class loader** as its parent, so it does not pick up `demo.bytes.Target` from the harness's application classpath.
- `defineClass(null,...)` reads the binary name from the source bytes instead of inferring it from a file name.
- The mutated arrays are all **clones** of the valid `Target.class`. The `Target.class` file remains intact on disk.
- Each negative parse/verify test uses a fresh loader so it is unaffected by class definitions or verification state from the previous case.
- The JVM may verify during `defineClass` or later; `invalid.getDeclaredMethod("answer")` makes the test force the JVM to process the defined class further. Because both are inside the `try` block, a `VerifyError` from either step is caught properly.
- `matches==1` is a fixture invariant; if the compiler emits different bytecode, the test **fails fast** instead of silently producing a false positive.
- The duplicate test uses the **exact same** loader instance to clearly violate the class identity constraint.
- The `catch` blocks are only for checking **expected failures** in the lab. You must not catch `LinkageError` or `VerifyError` and continue as if nothing happened in a production application.

**Exact verified standard output:**

~~~text
FORMAT=ClassFormatError
VERIFY=VerifyError
DUPLICATE=LinkageError
~~~

All three errors are **actively caught by the harness**, so the process exits 0 when the test passes. If `UNEXPECTED` or `IllegalStateException` appears, the test must be marked FAIL even if the exit code in another branch might not be as expected.

## 8. Practicing Through a Real `ClassFileTransformer`

In `FaultLab`, we called `ClassLoader.defineClass` directly on corrupted bytes. The real instrumentation scenario is that a transformer receives valid bytes from the JVM and then **returns a new byte array**; only then does the JVM check the classfile output. We will use an agent with a very narrow filter on the target class name to simulate that.

**`src/fixture/demo/bytes/Run.java`**

~~~java
package demo.bytes;

public final class Run {
    public static void main(String[] args) {
        System.out.println("ANSWER=" + Target.answer());
    }
}
~~~

Without an agent, stdout:

~~~text
ANSWER=42
~~~

**`src/agent/CorruptingAgent.java`**

~~~java
package agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class CorruptingAgent {
    public static void premain(String mode, Instrumentation inst) {
        if (!"format".equals(mode) && !"verify".equals(mode)) {
            throw new IllegalArgumentException("Select format or verify");
        }

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String name,
                    Class<?> redefined, ProtectionDomain domain,
                    byte[] data) {
                if (!"demo/bytes/Target".equals(name)) {
                    return null;
                }

                byte[] out = data.clone();
                if ("format".equals(mode)) {
                    out[0] = 0;
                } else {
                    int count = 0;
                    for (int i = 0; i + 2 < out.length; i++) {
                        if ((out[i] & 255) == 0x10
                                && (out[i + 1] & 255) == 0x2a
                                && (out[i + 2] & 255) == 0xac) {
                            out[i + 2] = (byte) 0xb0;
                            count++;
                        }
                    }
                    if (count != 1) {
                        System.out.println("PATCH_SKIPPED_UNEXPECTED_PATTERN");
                        return null;
                    }
                }

                System.out.println("TRANSFORM=" + mode);
                return out;
            }
        }, false);
    }
}
~~~

Key points to note:

1. `premain` receives `Instrumentation` provided by the JVM when running `-javaagent`; the app does not create this object.
2. The `"demo/bytes/Target"` filter runs **before any modification**. For other classes, the callback returns `null`.
3. `out=data.clone()` avoids modifying the source `classfileBuffer` directly. This is the minimal step when constructing separate output.
4. Mode `format` corrupts the magic; mode `verify` corrupts the return opcode in the fixture. Both are **negative tests**, not a valid instrumentation technique.
5. `return out` **does not mean the JVM has accepted the class**. After the callback, the JVM still parses, verifies, and links.
6. When returning `null`, the transformer makes no byte changes at its layer. An exception thrown **inside the callback** may be treated by the `ClassFileTransformer` mechanism as no transformation so other transformers can continue; do not throw an exception assuming the JVM is guaranteed to fail-closed.
7. `println` inside a transformer is only for learning, not suitable for a high-throughput production callback; you need filters, counters, and small buffers.

### 8.1. `MANIFEST.MF` for the Startup Agent

~~~text
Manifest-Version: 1.0
Premain-Class: agent.CorruptingAgent

~~~

Keep the newline and blank line ending the main section. Do not use `Can-Retransform-Classes` because the demo only modifies **at initial load**, without calling `retransformClasses`.

### 8.2. Running Three Times in Separate Processes

Baseline (no agent):

~~~bash
java -cp build/fixture demo.bytes.Run
~~~

Output:

~~~text
ANSWER=42
~~~

Intentionally returning a classfile with bad magic:

~~~bash
java -javaagent:corrupt-agent.jar=format -cp build/fixture demo.bytes.Run
~~~

Verified identifying lines:

~~~text
TRANSFORM=format
java.lang.ClassFormatError: Incompatible magic value ...
~~~

Intentionally returning a classfile with a bad type in the method:

~~~bash
java -javaagent:corrupt-agent.jar=verify -cp build/fixture demo.bytes.Run
~~~

Verified identifying lines:

~~~text
TRANSFORM=verify
java.lang.VerifyError: Bad type on operand stack
~~~

These are **the core parts of the stack trace**, not a guarantee of verbatim stderr across every JVM. Each failing command returned exit code `1` in testing, after printing the `TRANSFORM=...` line from the callback.

**Diagnostic significance:** `premain` can complete and the callback can run, yet the JVM rejects **the bytes returned afterward**. If a production agent prints `"transform success"` before the JVM defines the class, that message only means **the transformer produced output**, and cannot represent “the class verified/linked and ran safely”.

## 9. Compiling the Entire Fixture

From the `fault-lab/` directory using JDK 17+:

~~~bash
javac --release 17 -d build/helper-v1 src/helper-v1/demo/helper/Probe.java
javac --release 17 -d build/helper-v2 src/helper-v2/demo/helper/Probe.java
javac --release 17 -cp build/helper-v1 -d build/app src/app/demo/app/Caller.java src/app/demo/app/Main.java
javac --release 17 -d build/fixture src/fixture/demo/bytes/Target.java src/fixture/demo/bytes/Run.java
javac --release 17 -d build/tools src/tools/FaultLab.java src/tools/ModuleCheck.java
javac --release 17 -d mods/demo.secret src/demo.secret/module-info.java src/demo.secret/demo/secret/Secret.java
javac --release 17 -d build/agent src/agent/CorruptingAgent.java
jar --create --file corrupt-agent.jar --manifest MANIFEST.MF -C build/agent .
~~~

Each command is single-line and runs in a POSIX shell or Windows PowerShell. `--release 17` ensures the source conforms to Java 17 public platform APIs and classfile target; a Java 17+ compiler supports the corresponding flag.

After building:

- `build/helper-v1` contains the version with `Probe.label()`.
- `build/helper-v2` contains the version **without** `Probe.label()`.
- `build/app` contains the caller compiled **against helper-v1**.
- `build/fixture` contains the valid `Target` and `Run`.
- `build/tools` contains the two harnesses.
- `mods/demo.secret` contains an exploded named module.
- `corrupt-agent.jar` contains the manifest, the `agent.CorruptingAgent` class, and the anonymous nested class generated by javac.

Because the compiler generates an anonymous transformer class (e.g., `CorruptingAgent$1.class`), packaging with `-C build/agent .` includes the nested class as well. If you only package the main class, the JVM may hit a `NoClassDefFoundError` due to the missing nested class, unrelated to the bytecode mutation of Target.

### 9.1. Windows: Three Helper Cases

On Windows, the classpath separator is **`;`**:

~~~powershell
java -cp "build/app;build/helper-v1" demo.app.Main
java -cp build/app demo.app.Main
java -cp "build/app;build/helper-v2" demo.app.Main
~~~

- Command 1: `RESULT=helper-ok`, exit `0`.
- Command 2: `NoClassDefFoundError: demo/helper/Probe` and cause `ClassNotFoundException`, exit `1` in the tested JVM.
- Command 3: `NoSuchMethodError` for `Probe.label()`, exit `1`.

### 9.2. Linux/macOS: Three Helper Cases

The classpath separator is **`:`**:

~~~bash
java -cp "build/app:build/helper-v1" demo.app.Main
java -cp build/app demo.app.Main
java -cp "build/app:build/helper-v2" demo.app.Main
~~~

Do not change the order of flags or change it to “put both helper-v1 and helper-v2 on the classpath”. When two classes share the same binary name, the runtime may pick one version based on class lookup order, causing the test to no longer measure the ABI mismatch properly.

### 9.3. Bytecode and Module Harnesses

~~~bash
java -cp build/tools FaultLab build/fixture/demo/bytes/Target.class
java --module-path mods --add-modules demo.secret -cp build/tools ModuleCheck
java --module-path mods --add-modules demo.secret "--add-opens=demo.secret/demo.secret=ALL-UNNAMED" -cp build/tools ModuleCheck
~~~

Corresponding verified output:

~~~text
# FaultLab
FORMAT=ClassFormatError
VERIFY=VerifyError
DUPLICATE=LinkageError

# ModuleCheck without opens
OPEN=false
REFLECT=BLOCKED

# ModuleCheck with opens
OPEN=true
REFLECT=inside
~~~

The lines starting with `#` in the block above are **annotations separating the three runs**, not stdout printed by the Java programs. Each command was run once in a fresh JVM.

On Windows PowerShell, keep `"--add-opens=..."` inside quotes so it remains a single JVM argument. Place the flag **before** the class name `ModuleCheck`, because everything after the class name is application args, no longer launcher options.

## 10. Standard Tools for Triaging Errors

| Tool / Check | What It Is Used For | What It Does Not Prove |
| --- | --- | --- |
| `jar --list --file some.jar` | View which classes/helpers a JAR contains | Does not prove the defining loader sees it |
| `javap -c -p Target.class` | View instructions such as `bipush`, `ireturn` | Does not verify output modified by an agent at runtime |
| `javap -verbose Target.class` | Major/minor, constant pool, attributes | Does not confirm proper module access |
| `java -Xverify:all` | Enable stricter bytecode verification | Does not fix a missing helper or ABI mismatch |
| `java "-Xlog:class+load=info"` | Track class loading sources on HotSpot | Does not automatically show every class transformed by an agent |
| `Class.getClassLoader()` | Know the defining loader of a loaded class | Does not replace checking the module graph |
| `Class.getModule()` | Know the module object containing a class | Does not automatically allow reflection into privates |
| `Module.isOpen(pkg, caller)` | Deep reflection permission of a package to a caller | Does not guarantee the class/method exists |
| `Module.canRead(other)` | Readability edge | Does not guarantee the package is exported/open |
| `Throwable.getCause()` | Follow the root cause | Not every error is guaranteed to have a cause |
| `$LASTEXITCODE` / `echo $?` | Status of the process that just ran | Not sufficient for a harness that catches expected errors itself |

Inspect the original classfile:

~~~bash
javap -c -p build/fixture/demo/bytes/Target.class
javap -verbose build/fixture/demo/bytes/Target.class
java -Xverify:all -cp build/fixture demo.bytes.Run
~~~

Use HotSpot class-load logging when needed:

~~~bash
java "-Xlog:class+load=info" -cp build/fixture demo.bytes.Run
~~~

If your bytecode library has its own `verify` API, use it to catch errors early before returning new bytes, but the JVM remains the final authority on defining the class in a specific runtime. Do not log entire classfile bytes/constant pools in production; they may contain literals, class names, or data that needs to be protected.

### 10.1. Three Groups of Data to Collect for an Error

**About the target:** internal class name, method name and descriptor, classfile major/minor, and load/redefine/retransform phase.

**About the runtime:** Java version, defining loader (a small ID sufficient to distinguish it), module name, target package, helper location/version, and module reads/exports/opens state.

**About the failure:** exact exception class, cause chain, failed symbolic reference, bytecode/toolkit version, and the transform stage that produced the output. You can add an artifact hash for comparison, but do not treat the hash as the sole proof of class version when JVM retransformation can restructure the constant pool.

Do not hold strong references to `ClassLoader`, `Class<?>`, or entire `classfileBuffer` arrays in unbounded caches; doing so can prevent class unloading and increase native/heap memory.

## 11. Why Can the Same Error Name Have Different Causes?

### 11.1. `NoClassDefFoundError` Is Not Always a Missing File

Besides a missing helper JAR, a class may fail to be defined/initialized due to an error in a dependency or an earlier static initializer. Subsequent uses of the class can produce `NoClassDefFoundError: Could not initialize class ...` with the appropriate cause. Inspect the full message and error chain; do not always recommend “copy another JAR”.

### 11.2. `VerifyError` Is Not Only Caused by Return Opcodes

Verifier errors can be caused by stack height/type mismatches, invoking with wrong operand types, branching to an invalid location, uninitialized `this` in a constructor, or an incorrect `StackMapTable` after inserting instructions. This lesson chose the return opcode because it is easy to reproduce; production patches must preserve all method invariants.

### 11.3. `ClassFormatError` Is Not Only Caused by the Magic Number

A class with a valid magic number but an invalid constant pool, attribute lengths, descriptors, or truncation at the end can still fail format checking. Conversely, a classfile with a valid format can still fail the verifier or linking to a helper. Do not fix the error by “changing the first 4 bytes to `CAFEBABE`”; you must fix **the underlying structure or the transformation that corrupted it**.

### 11.4. `LinkageError` from Loader Constraints Differs from Duplicate Define

For example, loader A and loader B can load two classes with the same name independently, but a symbolic reference or method signature can impose a loader identity constraint. When violated, the JVM can also throw `LinkageError`. Therefore, the duplicate test in this lesson is **one clear mechanism**, not the entirety of reasons `LinkageError` can appear.

### 11.5. The Time of Occurrence Can Be Late

An injected helper invocation on a rare branch may **not yet be resolved** during a startup smoke test. The application may run for several minutes before entering the method path containing the probe and throwing `NoSuchMethodError`. You need integration tests covering normal paths, exceptions, concurrency, constructors, and conditional branches; do not rely solely on `java -version` and app startup.

## 12. Designing Tests and Rollback Suitable for Instrumentation

### 12.1. Separating Agent Tests from Application Tests

A good strategy has four layers:

1. **Selector unit tests:** identify the right class/method/descriptor, and do not instrument the agent's own helpers.
2. **Bytecode tests:** parser accepts the classfile version, code transform preserves original instructions, output verifies successfully, and idempotence holds across multiple transforms.
3. **Loader/module integration:** app with custom loaders, bootstrap/system helpers, module exports/opens, and matching helper ABI.
4. **End-to-end behavior:** business results are unchanged with best-effort hooks, latency/CPU/GC overhead is acceptable, and a failing telemetry exporter does not crash requests.

Cases that intentionally cause `VerifyError` and `ClassFormatError` belong only in **separate negative tests**, and must never be bundled into a released agent. The `-javaagent:corrupt-agent.jar=format`/`verify` command in this lesson is a controlled fault-injection tool, not a “profile” or “debug flag” for production.

### 12.2. Limitations When Redefining/Retransforming

`retransformClasses` and `redefineClasses` have constraints on class modifiability and schema. A classfile that is valid at initial load may be invalid during redefine because it adds a method/field or changes the hierarchy. Conversely, a `ClassFileTransformer` can return `null` on a pass to preserve the bytes at that layer, but it does not automatically undo transformations from other transformers in the pipeline.

Test flow for an agent with retransform:

~~~text
Load baseline
   |
   v
First instrument -> verify -> link helper -> run behavior
   |
   v
Retransform 1 -> verify -> count hooks
   |
   v
Retransform 2 -> verify -> no duplicate hooks
   |
   v
Valid redefine (if supported) -> verify -> behavior
   |
   v
Retransform after redefine -> check baseline and telemetry
~~~

Do not reproduce corrupted classfiles on a JVM handling production transactions. Enable the right capabilities, use dummy classes, and have timeouts/watchdogs because native/bytecode bugs can cause the process to terminate abnormally.

### 12.3. When to Choose Fail-Open vs. Fail-Closed?

If instrumentation is only used to collect optional telemetry, skipping an unsupported class may be acceptable under the product contract: the transformer returns `null` while incrementing a counter/drop metric on a safe channel. However, if instrumentation is used for **security enforcement** or mandatory auditing, silently returning `null` and reporting “success” is dangerous. There must be an explicit fail/rollback policy at startup/deployment or the policy layer, without treating an exception in the transformer as a guarantee that the JVM will reject every class.

A general principle: **do not compromise application correctness to preserve telemetry**. Helpers should not throw on the hot path or should have appropriate fault isolation, with no unbounded I/O or blocking.

## 13. Verified Test Matrix

| Case | Trigger | Key Signal | Expectation |
| --- | --- | --- | --- |
| Standard helper | Runtime uses helper-v1 | `RESULT=helper-ok` | Exit 0 |
| Missing helper | Only `build/app` present | `NoClassDefFoundError`, cause `ClassNotFoundException` | Negative pass |
| Wrong helper ABI | Runtime uses helper-v2 | `NoSuchMethodError` | Negative pass |
| Blocked module | No `--add-opens` | `OPEN=false`, `REFLECT=BLOCKED` | Negative pass |
| Opened module | With `--add-opens` | `OPEN=true`, `REFLECT=inside` | Exit 0 |
| Classfile format | First magic byte changed | `FORMAT=ClassFormatError` | Harness records match |
| Bytecode verify | `ireturn` replaced by `areturn` | `VERIFY=VerifyError` | Harness records match |
| Duplicate loader | `defineClass` twice on same loader | `DUPLICATE=LinkageError` | Harness records match |
| Standard app fixture | No fault-injecting agent loaded | `ANSWER=42` | Exit 0 |
| Transformer format | `-javaagent:corrupt-agent.jar=format` | `TRANSFORM=format` then ClassFormatError | Non-zero exit |
| Transformer verify | `-javaagent:corrupt-agent.jar=verify` | `TRANSFORM=verify` then VerifyError | Non-zero exit |

Negative tests with an uncaught Error **typically** exit with a non-zero exit code; `FaultLab` catches the Error to print the result, so it exits 0 when correct. Assert both the **error type/signal** and program state, rather than relying on only one check.

## 14. Common Mistakes

1. **“LinkageError is just the sixth error, completely different from VerifyError.”** False: VerifyError and ClassFormatError are subclasses of LinkageError.
2. **“Having ClassNotFoundException and NoClassDefFoundError means two independent errors.”** They can be part of the same cause chain.
3. **“The transformer returned bytes successfully, so the class must load.”** The JVM still needs to parse/verify/link.
4. **“The agent can load the helper, so bootstrap/plugin classes can load it too.”** No: you must check the target's loader.
5. **“Having the helper JAR is enough.”** Method name/descriptor, static/instance kind, and dependency ABI may be wrong.
6. **“--add-opens solves every module problem.”** No: module resolution, readability, and public exports differ from deep reflection.
7. **“ClassFormatError is a bad bytecode stack.”** That is usually VerifyError; ClassFormatError is about format.
8. **“For VerifyError, just disable the verifier.”** No: you must fix the bytecode transform.
9. **“Scanning a few bytes in a classfile is a parser.”** No: the pattern hack is only for the fixture whose match count was verified.
10. **“Two loaders defining the same name always error.”** Not by default; duplicate errors occur when **the same defining loader** tries to define an already-defined name.
11. **“Returning null undoes all previous transformers.”** Null only leaves the output unchanged at the current layer.
12. **“Throwing in the callback guarantees fail-closed.”** The ClassFileTransformer contract does not promise that.
13. **“Testing startup alone is enough.”** Helper linking can happen lazily when the call site is used.
14. **“Catching Throwable and continuing is how to recover from VerifyError.”** That hides serious correctness bugs.
15. **“Putting both helper-v1 and helper-v2 on the classpath will test ABI mismatch.”** The runtime may pick a different version due to ordering.
16. **“Opening to ALL-UNNAMED is least privilege in every case.”** Grant to the specific caller module whenever possible.
17. **“Module errors can be cured by corrupting magic.”** Format, module, and linkage are different layers.
18. **“Logging all class bytes is always good for debugging.”** It risks exposing data and retaining unbounded memory.

## 15. Self-Check Questions

1. Why is `ClassFileTransformer.transform` returning `byte[]` not enough to prove the JVM defined the class successfully?
2. When the JVM reports `NoClassDefFoundError: demo/helper/Probe`, which loader do you check first?
3. If `Probe` is present but the `label()` method is gone, which error applies?
4. Why does the signature `label()Ljava/lang/String;` differ from `label()Ljava/lang/Object;` even with the same method name?
5. Does `InaccessibleObjectException` belong to `LinkageError` or `RuntimeException`?
6. Why is `--add-modules demo.secret` needed before the module is found in the boot layer, while `--add-opens` solves a different issue?
7. When can a private method of a named module be invoked from an unnamed app?
8. Is a magic number error a verifier opcode error?
9. Why is `bipush 42; areturn` invalid in a method with descriptor `()I`?
10. Why must you check that the match count of the byte pattern equals 1?
11. Why do two `defineClass` calls on **the same loader** lead to LinkageError?
12. Can a different classloader define a class with the same binary name?
13. What does it prove when the callback prints `TRANSFORM=verify` and then the JVM reports VerifyError?
14. If `return null` is used in a transformer, are all modifications from previous transformers erased?
15. Why is it necessary to distinguish stdout, stderr, and exit code when reading stack traces?
16. What additional tests are needed if a helper is only called on a rare exception branch?
17. Can `java -Xverify:all` fix a missing helper or an unopened package?
18. Does `Instrumentation.redefineModule` cure ClassFormatError?
19. Why is `NoClassDefFoundError` sometimes related to static initialization rather than just a missing JAR?
20. When can an optional transform error be skipped, and when is an explicit fail policy required?

## 16. Checklist for Handling Errors in Real Applications

1. Run a baseline without instrumentation and record output/behavior.
2. Classify the exact error class and find the **root cause**.
3. Verify that the target class/method internal name and descriptor were selected correctly.
4. Inspect the target's defining loader, the helper's search path/loader, and package/module rules.
5. Check the helper ABI, nested dependencies, and the version actually loaded.
6. If it is a module issue, separate resolution, readability, exports, and opens; open only the necessary scope.
7. If `ClassFormatError`, inspect input/output classfile structure, version, and attributes.
8. If `VerifyError`, inspect operand stack, frames, return type, branches, and exception handlers.
9. If `LinkageError`, inspect binary name, defining loader, duplicate definitions, and constraints.
10. Test each case in a fresh JVM, without carrying class-load failure state between negative fixtures.
11. For transformer output, verify before release; do not push intentionally invalid bytes to production.
12. Run integration tests on real JVM versions and loaders/modules, including rare branches.
13. Do not log excessively or trigger classloading recursion inside the callback.
14. Have a skip/rollback mechanism for optional telemetry and an explicit fail strategy when instrumentation is mandatory.
15. Maintain regression tests for fixed root causes to prevent recurrence when upgrading JDK/toolkits.

## 17. Conclusion

Reproducing each error individually helps pinpoint **the exact layer that needs fixing**: a missing helper belongs to class lookup; a wrong ABI belongs to symbolic references; a wrong module belongs to access permissions; ClassFormatError belongs to file structure; VerifyError belongs to bytecode type-safety; LinkageError can arise from loader identity or ABI constraints.

**The key takeaway for Java instrumentation:** a callback having run does not mean the class was accepted by the JVM. The JVM still parses, verifies, resolves, links, and checks access on the output produced by the transformer. A suite of negative tests run in isolated JVMs, with controls, expected exceptions, and loader/module/bytecode checks, is a reliable way to prove an agent **does not break application correctness**.

### Official Documentation

- [Oracle Java 17 – LinkageError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html): subclass hierarchy.
- [Oracle Java 17 – NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html): dependency class cannot be found/defined.
- [Oracle Java 17 – NoSuchMethodError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodError.html): runtime method ABI mismatch.
- [Oracle Java 17 – ClassFormatError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassFormatError.html): classfile structure error.
- [Oracle Java 17 – VerifyError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/VerifyError.html): bytecode verification.
- [Oracle Java 17 – InaccessibleObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): deep reflection access error.
- [JVMS 17 – Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): classfile magic, format, and verification.
- [JVMS 17 – Loading, Linking, Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loader identity, verification, resolution timing.
- [Oracle Java 17 – ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer contract and output.
- [Oracle Java 17 – java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `--add-modules`, `--add-opens`, `-Xverify:all`, classload logging.
