# Selectively Saving Input/Output Bytes and Reading Them Back with javap

## 1. When a transformer runs but you don't know what bytecode the JVM received

In a Java instrumentation system, a `ClassFileTransformer` can return a new byte array without throwing an error, yet the application still exhibits `VerifyError`, `NoClassDefFoundError`, unhooked methods, broken `try/finally` branches, or wrong observed data. Simply logging “transform invoked” and a processing time number is usually not enough to find the root cause.

A practical diagnostic approach is to **selectively capture classfile bytes at two checkpoints**:

1. **Input snapshot:** copy the `classfileBuffer` passed into the exact transformer callback being investigated.
2. **Output snapshot:** copy the `byte[]` array that the transformer **intends to return** after transformation.

Then use the built-in JDK tool, **`javap -c -v -p`**, to read both classfiles, comparing the constant pool structure, instructions, method descriptors, attributes, exception table, and source line information (if present).

**Key point:** The “before” and “after” snapshots represent **one step in the pipeline**. They are not by default the original bytes on disk and the final bytes the JVM installs, especially when multiple transformers participate or the JVM normalizes certain classfile details.

### What will you be able to do after learning this?

- Know exactly where `classfileBuffer` and `return byte[]` sit in the transform order.
- Filter by **internal class name**, defining class loader, `Module`, and load/retransform/redefine events, avoiding capturing the entire application.
- Save both snapshots as **binary `.class`** files (not `byte[]` strings, `Arrays.toString`, or base64) with size limits and stable names for the demo.
- Run a **Java 17+** example: before `"BEFORE"`, after `"AFTER!"`; verify with `javap -c -v`, then run the application to cross-check.
- Recognize the limitations of patching literals directly in the constant pool; do not use the demonstration trick as a production bytecode writer.
- Avoid risks around performance, class-loading reentrancy, I/O errors, data sensitivity, duplicate filenames, and classloader collisions when debugging an agent.

## 2. The transformer pipeline: what do “input” and “output” actually mean?

### 2.1. From classfile to running class

Consider when a class is first defined:

~~~text
Class loader / JVM provides classfile bytes
                    |
                    v
          Transformer A (may modify)
                    |
                    v
        [input of transformer B] -----> capture BEFORE at B
                    |
                    v
          Transformer B transforms
                    |
                    +---------------> capture AFTER that B returns
                    |
                    v
          Transformer C (if any)
                    |
                    v
        JVM verifies/links/defines class
                    |
                    v
             App executes method
~~~

In `ClassFileTransformer.transform(...)`:

- The `classfileBuffer` parameter is the input to the **current callback**, which may **already have been modified by previous transformers**.
- If the transformer does not want to make changes, return **`null`**.
- If creating new bytes, return a **valid `byte[]` array**; **do not mutate `classfileBuffer` in place**.
- The transformer runs **before** the JVM verifies/accepts the resulting class definition; returning an output does not guarantee the class will verify/link successfully.
- If another transformer runs **after**, your output is not necessarily the final output of the pipeline.
- Transformers are invoked according to the group order and registration order described in the Javadoc. When multiple agents are active, you must inspect the **entire chain**.

Therefore, label them clearly:

~~~text
transformer-B.input.class
transformer-B.returned.class
~~~

Rather than arbitrarily naming them `original.class` or `jvm-installed.class` without strong evidence.

### 2.2. When `transform(...)` returns `null`, what is “after”?

`null` means **no transformation was performed at this step**. Do not create a file labeled `after-transformed` just by writing the input again and claiming the transformer modified it.

You can choose a policy:

| Callback result | Useful capture policy |
|---|---|
| Transformer returns a new `byte[]` | Capture input and returned bytes, mark `transformed=true` |
| Transformer returns `null` | Capture input if needed, record metadata `unchanged=true`, do not fabricate a new after file |
| Transformer throws an exception | Log minimal error via an independent channel; do not treat output as valid |
| Class does not match filter | Do not capture, do not log sensitive data of that class |
| Classfile exceeds limit | Skip snapshot or fail per policy, do not allocate/write files unboundedly |

**In the runnable example**, the transformer only captures when it finds the exact literal and actually returns a new array. If the literal is not found, the example returns `null` and does not write the snapshot pair.

### 2.3. Retransform/redefine differs from initial class load

A callback can occur when a class is **loaded for the first time**, **retransformed**, or **redefined**:

- For an initial load, `classBeingRedefined` is normally `null`.
- For redefine/retransform, `classBeingRedefined` is the existing class object; the source of the callback's input must be understood according to the Instrumentation contract.
- During `retransformClasses`, the JVM may re-invoke transformers registered with `canRetransform=true`, while reapplying the results of non-capable transformers.
- After a `redefineClasses` call, the baseline source for a subsequent retransform may be the bytes from the **most recent redefine**, not the JAR at startup.
- Multiple callbacks for the **same binary name** may use different bytes over time.

Do not just name the file `MyClass.class` and overwrite it repeatedly. If the goal is to study multiple passes, you need metadata including **load/redefine/retransform**, sequence number, loader identity, module, timestamp, and byte hashes to distinguish them. The demo below intentionally **captures only a single initial load** so that files and stdout are deterministic.

## 3. Filter before saving: choose a sufficiently narrow class set

A real Java agent may see thousands or tens of thousands of class definitions. If every callback writes full bytes:

- Startup and class loading slow down due to filesystem I/O.
- Disk usage grows rapidly; snapshots may contain logic, string literals, URLs, tokens, or sensitive information in the constant pool.
- Dumping multiple classes from different loaders with the same name can overwrite one another.
- The agent's own helper/logging classes can trigger reentrancy or cause unintended additional class loads.
- Capturing too broadly pollutes the evidence, making it hard to find the offending class.

**Safety principle:** filter cheaply using metadata **before reading/modifying/copying classfile bytes**, and only then check size and capture budget limits.

### 3.1. Recommended filter order

| Criterion | What to check | Why |
|---|---|---|
| Class name | `"demo/target/Greeter".equals(className)` | The JVM uses the **internal name** with `/`, not `demo.target.Greeter` |
| Class loader | `loader == expectedLoader` | Same binary name with a different defining loader is a different class |
| Module | `module == null \|\| !module.isNamed()` in the lab | Example app on classpath belongs to an unnamed module; named modules need their own policy |
| Phase | `classBeingRedefined == null` | Demo only captures initial load, avoiding mixing retransform/redefine |
| Capture budget | `AtomicBoolean.compareAndSet(false, true)` | Only one snapshot is accepted; prevents concurrent callback races |
| Byte budget | `input.length <= MAX_BYTES` | Avoid unbounded class dumps, reducing memory/disk risk |
| Transform result | Save only when the patch produces valid bytes per demo policy | So the before/after pair has a real difference |

**Do not use `className.endsWith("Service")` in production to dump the entire system**. If multiple classes are needed, use a configured allowlist with limits on size/file count/memory/TTL, security policies, and a dedicated storage location.

### 3.2. `className` may need a null check

Per the `ClassFileTransformer` contract, the internal name is provided in many cases, but there are special class definition paths where the name can be `null`. Writing:

~~~java
if (!"demo/target/Greeter".equals(name)) {
    return null;
}
~~~

is safer than `name.equals(...)` when the value is unknown. Similarly, bootstrap-defined classes have `loader == null`; if you filter `loader == ClassLoader.getSystemClassLoader()`, you will **not** catch bootstrap classes.

### 3.3. `Module` and class loader do not replace each other

Two classes with the same `className` and the same loader do not necessarily have the same module access requirements when deploying complex module architectures. With Java 9+, the six-parameter callback receives `Module`; you can read `module.getName()` if it is a named module.

Since the example only uses a normal classpath, the target's module is **unnamed**, and the filter allows `module == null` (compatibility path) or `!module.isNamed()`. In real plugin/custom loader setups, module, layer, and class identity conditions must be defined according to the target. Do not just compare `module.getName()` because it can be null on an unnamed module.

## 4. Designing snapshots so they can be compared without breaking the runtime

### 4.1. Save raw classfile bytes, not text representations

Correct example:

~~~java
Files.write(path, classfileBuffer, StandardOpenOption.CREATE_NEW);
~~~

This call takes `byte[]` and writes **byte-for-byte**. Conversely, approaches like:

~~~java
System.out.println(Arrays.toString(classfileBuffer));
Files.writeString(path, new String(classfileBuffer));
~~~

do not produce a usable `.class` file. Bytecode is binary data; converting it to a string can corrupt data or alter the encoding.

The code above is only an **API illustration snippet**, not a standalone program: `path`/`classfileBuffer` must be available in the callback with imports added. A complete example appears in a later section.

### 4.2. Do not overwrite and do not mix runs

The demo uses the names:

~~~text
captures/run-001/Greeter-before.class
captures/run-001/Greeter-after.class
~~~

and `StandardOpenOption.CREATE_NEW`. If the path already exists, the call fails instead of **overwriting** the old snapshot. Each run uses a new directory: `run-001`, `run-002`, etc.

In production, you can structure it as:

~~~text
captures/
  run-id/
    loader-id/
      module-id/
        internal/name/target-<sequence>-input.class
        internal/name/target-<sequence>-returned.class
        target-<sequence>-metadata.json
~~~

That is a **naming convention pattern**, not automatic output from the demo. Never blindly trust `System.identityHashCode(loader)` as a persistent ID across runs or globally unique forever: collisions can occur, and the value has no global meaning. If a stronger identity is needed, use a process-scoped object identity registry plus a sequence/UUID; remember not to accidentally keep class loaders alive too long.

### 4.3. What should accompanying documentation include?

A manifest/log entry for each snapshot pair should contain:

- JVM/version, agent/build version, timestamp, and run ID.
- Internal class name, defining loader identity, and module/layer if relevant.
- Phase: initial load, redefine, or retransform.
- Transformer ID and pipeline order if known.
- Input length, returned length, SHA-256 of both; optional classfile major version.
- Transform outcome: transformed, unchanged, skipped, error.
- Skip reason and size limits.
- Link to testcase/reproduction context, without storing secrets in logs.

A **checksum** tells you whether two files have the same bytes; it does **not** prove the bytes are valid or the behavior is correct. `javap` helps inspect structure; the JVM verifier and execution tests provide further correctness information.

### 4.4. Performance and resilience

Writing files directly inside `transform(...)` can block class loading on I/O, alter timing, increase p99 latency, and cause deadlocks if touching a filesystem/network mount. Therefore:

1. Enable capture via a feature flag **only when diagnosing**.
2. Filter first, with small and bounded allocations/copies.
3. Cap the number of classes, bytes, and callbacks per budget.
4. Do not perform blocking network exports inside the callback.
5. If many captures are needed, use a carefully designed bounded queue/writer thread; log dropped snapshots, and flush/shut down properly.
6. Do not swallow all errors and claim the capture succeeded.

The demo uses synchronous `Files.write` only to make **a single small class captured once** easy to reproduce. That is not an optimal throughput pattern for a production agent.

## 5. Java 17+ Experiment: Greeter before and after transformation

We create:

- Application class `demo.target.Greeter`, with method `message()` returning the literal `"BEFORE"`.
- Startup Java agent `demo.agent.SnapshotAgent`, registering a transformer that filters for this exact class.
- The transformer reads the constant pool and **changes only one six-byte ASCII literal** from `"BEFORE"` to `"AFTER!"`, without changing the classfile length.
- The agent saves the input to `Greeter-before.class` and the returned bytes to `Greeter-after.class`.
- The app calls `Greeter.message()`; when the agent is used properly, the output is `"AFTER!"`.
- `javap -c -v` is used to inspect the literal and the `ldc` instruction in both versions.

**Limitations of the experiment:** patching `CONSTANT_Utf8` directly without a library parser is a trick **only for two equal-length ASCII literals in a controlled class**. It is not suitable for arbitrary classfiles, real bytecode instrumentation, modifying StackMapTable, adding branches, or changing method signatures. When building production software, use a bytecode library with verifier/testing support such as ASM/Byte Buddy; do not copy a minimal parser into a general-purpose tool.

### 5.1. Directory tree

~~~text
snapshot-lab/
├── AGENT.MF
├── src/
│   ├── agent/demo/agent/SnapshotAgent.java
│   └── app/demo/
│       ├── app/App.java
│       └── target/Greeter.java
├── out/                         # created on build
│   ├── agent/
│   ├── app/
│   └── snapshot-agent.jar
└── captures/                    # created on run
    └── run-001/
        ├── Greeter-before.class
        └── Greeter-after.class
~~~

The files in `captures` are generated by the agent; do **not** put them on the runtime classpath. The snapshot filenames do not match the original `Greeter.class`, but `javap` can still read **a path to classfile bytes** as shown below.

### 5.2. File `src/app/demo/target/Greeter.java`

~~~java
package demo.target;

public final class Greeter {
    private Greeter() {}

    public static String message() {
        return "BEFORE";
    }
}
~~~

The method only returns a string literal. When compiled with `javac --release 17`, the constant pool contains a `CONSTANT_String` referencing a `CONSTANT_Utf8` with content `BEFORE`. The method can use the `ldc` instruction to load the literal; after the transformer changes the UTF8 entry, the instruction does not need to change its opcode or constant-pool index.

### 5.3. File `src/app/demo/app/App.java`

~~~java
package demo.app;

import demo.target.Greeter;

public final class App {
    private App() {}

    public static void main(String[] args) {
        System.out.println("[app] message=" + Greeter.message());
    }
}
~~~

The application triggers loading of `Greeter` when the class is needed (it might be loaded earlier by the JVM depending on implementation, but in the demo run the callback still occurs after the startup agent has registered). It does not call the instrumentation API itself.

### 5.4. File `src/agent/demo/agent/SnapshotAgent.java`

~~~java
package demo.agent;

import java.io.IOException;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicBoolean;

public final class SnapshotAgent {
    private SnapshotAgent() {}

    public static void premain(String args, Instrumentation inst) {
        if (args == null || args.isBlank()) {
            throw new IllegalArgumentException(
                    "Pass an empty capture directory as agent argument");
        }
        Path directory = Path.of(args).toAbsolutePath().normalize();
        inst.addTransformer(new SnapshotTransformer(directory), false);
    }

    private static final class SnapshotTransformer implements ClassFileTransformer {
        private static final int MAX_BYTES = 1024 * 1024;
        private final Path directory;
        private final AtomicBoolean captured = new AtomicBoolean();

        SnapshotTransformer(Path directory) {
            this.directory = directory;
        }

        @Override
        public byte[] transform(ClassLoader loader, String name,
                Class<?> classBeingRedefined, ProtectionDomain domain, byte[] bytes) {
            return capture(null, loader, name, classBeingRedefined, bytes);
        }

        @Override
        public byte[] transform(Module module, ClassLoader loader, String name,
                Class<?> classBeingRedefined, ProtectionDomain domain, byte[] bytes) {
            return capture(module, loader, name, classBeingRedefined, bytes);
        }

        private byte[] capture(Module module, ClassLoader loader,
                String name, Class<?> redefining, byte[] input) {
            if (!"demo/target/Greeter".equals(name)
                    || loader != ClassLoader.getSystemClassLoader()
                    || (module != null && module.isNamed())
                    || redefining != null || input == null) {
                return null;
            }
            if (!captured.compareAndSet(false, true)) {
                return null;
            }
            if (input.length > MAX_BYTES) {
                System.err.println("[agent] skip capture: classfile too large");
                return null;
            }

            byte[] output = patchLiteral(input);
            if (output == null) {
                System.err.println("[agent] skip capture: expected literal not found");
                return null;
            }
            try {
                Files.createDirectories(directory);
                Files.write(directory.resolve("Greeter-before.class"),
                        input, StandardOpenOption.CREATE_NEW);
                Files.write(directory.resolve("Greeter-after.class"),
                        output, StandardOpenOption.CREATE_NEW);
                System.out.println("[agent] captured demo/target/Greeter");
            } catch (IOException ex) {
                System.err.println("[agent] capture error: "
                        + ex.getClass().getSimpleName());
            }
            return output;
        }

        private static byte[] patchLiteral(byte[] input) {
            if (input.length < 10
                    || (input[0] & 255) != 0xCA
                    || (input[1] & 255) != 0xFE
                    || (input[2] & 255) != 0xBA
                    || (input[3] & 255) != 0xBE) {
                return null;
            }
            int count = u2(input, 8);
            int pos = 10;
            int changed = 0;
            byte[] copy = input.clone();

            for (int entry = 1; entry < count; entry++) {
                if (pos >= input.length) return null;
                int tag = input[pos++] & 255;
                switch (tag) {
                    case 1: {
                        if (pos + 2 > input.length) return null;
                        int length = u2(input, pos);
                        pos += 2;
                        if (pos + length > input.length) return null;
                        if (length == 6 && asciiEquals(input, pos, "BEFORE")) {
                            asciiWrite(copy, pos, "AFTER!");
                            changed++;
                        }
                        pos += length;
                        break;
                    }
                    case 3: case 4:
                    case 9: case 10: case 11: case 12:
                    case 17: case 18:
                        pos += 4;
                        break;
                    case 5: case 6:
                        pos += 8;
                        entry++; // long/double occupy two slots
                        break;
                    case 7: case 8: case 16:
                    case 19: case 20:
                        pos += 2;
                        break;
                    case 15:
                        pos += 3;
                        break;
                    default:
                        return null;
                }
                if (pos > input.length) return null;
            }
            return changed == 1 ? copy : null;
        }

        private static int u2(byte[] bytes, int pos) {
            return ((bytes[pos] & 255) << 8) | (bytes[pos + 1] & 255);
        }

        private static boolean asciiEquals(byte[] bytes, int pos, String text) {
            for (int i = 0; i < text.length(); i++) {
                if ((bytes[pos + i] & 255) != text.charAt(i)) return false;
            }
            return true;
        }

        private static void asciiWrite(byte[] bytes, int pos, String text) {
            for (int i = 0; i < text.length(); i++) {
                bytes[pos + i] = (byte) text.charAt(i);
            }
        }
    }
}
~~~

### 5.5. Why is this Java code reliable within the scope of the demo?

**Filtering:**

- `"demo/target/Greeter".equals(name)` selects only the exact internal name, avoiding NPE.
- `loader == ClassLoader.getSystemClassLoader()` accepts only the target handled by the system loader. A `Greeter` from another plugin loader is **not** captured.
- `module == null || !module.isNamed()` accepts only the lab's classpath context.
- `redefining == null` excludes retransform/redefine; does not mix initial load with later callbacks.
- `captured.compareAndSet(false, true)` ensures processing starts only once even though callbacks can be concurrent. The flag is flipped **before** checking size/patch; if skipped due to an error, the demo does not retry — this is intentionally “one shot”.
- `MAX_BYTES` blocks classfiles over 1 MiB in the lab. This limit is only an example, not a JVM threshold or general requirement.

**Transformation:**

- Reads the `CAFEBABE` classfile header, `constant_pool_count`, and sequentially parses tags commonly found in Java 17 classfiles; does not assume the constant pool only contains UTF8 entries.
- For a `CONSTANT_Utf8` with exactly six ASCII bytes `BEFORE`, creates `copy` and replaces it with `AFTER!` — the same length so offsets do not shift.
- If **exactly one** matching literal is not found, returns `null` so the class is left unchanged.
- Does not mutate the `input` array in place, adhering to the transformer contract. `copy` preserves structure/length, only changing the UTF8 content for the demo class.
- Both `transform` overloads are implemented: the five-parameter form for legacy API compatibility and the six-parameter form receiving `Module` since Java 9+; Java 17 supports it.

**Saving:**

- Saves the exact `input` before transformation and the `output` returned, without serializing a string.
- `Files.write(..., CREATE_NEW)` refuses to overwrite an existing snapshot.
- If I/O fails, the code prints `[agent] capture error: ...` and **still returns the transformed bytes**. Thus, you may see the app return AFTER! without having both files; you must check stderr and pair integrity.
- Two `Files.write` calls are **not an atomic transaction**. Cases where the before file is created but the after file fails require cleanup/metadata protocols in production.
- No network I/O or complex instrumentation logging is used inside the callback. However, `System.out/err` inside a callback is still I/O and can cause unexpected class loading/dependencies in real systems; in a simple lab, they help show ordering.

**Do not extend this parser for arbitrary classfiles.** It does not prove every Java bytecode output is valid, does not update StackMapTable/offsets, does not add methods, does not handle every classfile edge case, and does not replace libraries like ASM/Byte Buddy. With JDK versions newer than Java 17, other classfile features may appear; the demo is compiled with `--release 17` and uses only a controlled class.

### 5.6. Manifest file `AGENT.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.SnapshotAgent

~~~

The manifest must have a trailing newline and `Premain-Class` in the main section. `Can-Retransform-Classes` or `Can-Redefine-Classes` is not needed because the demo **only transforms on initial load**. Writing snapshots requires no additional capabilities beyond an active startup agent.

### 5.7. Compiling with JDK 17 or higher

Open a terminal at the `snapshot-lab` root.

**Bash/macOS/Linux:**

~~~bash
mkdir -p out/agent out/app
~~~

**PowerShell/Windows:**

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app | Out-Null
~~~

Compile the agent and application, then package the JAR:

~~~bash
javac --release 17 -d out/agent src/agent/demo/agent/SnapshotAgent.java

javac --release 17 -d out/app src/app/demo/target/Greeter.java src/app/demo/app/App.java

jar cfm out/snapshot-agent.jar AGENT.MF -C out/agent .
~~~

The file `out/app/demo/target/Greeter.class` remains the **original classfile after javac**; transformation happens at runtime when the class loader loads the class. Do not modify this file on disk.

**Separating output directories** for the agent and the application helps distinguish agent classes from target business classes. If building with Maven/Gradle, the same principle applies: the agent JAR has the manifest; the application has the target classes. The demo does not require Maven/Gradle.

### 5.8. Running with a new capture directory

**Bash/macOS/Linux:**

~~~bash
java -javaagent:out/snapshot-agent.jar=captures/run-001 -cp out/app demo.app.App
~~~

**PowerShell/Windows:**

~~~powershell
java "-javaagent:out/snapshot-agent.jar=captures/run-001" -cp out/app demo.app.App
~~~

Distinguish the two arguments:

- `-javaagent:<jar>=<args>` loads the startup agent, passing `captures/run-001` as agent arguments.
- `-cp out/app` is the classpath of the **application**; the JVM uses the agent JAR automatically via `-javaagent`.
- `demo.app.App` is the main class; when run, it references `demo.target.Greeter`.

**Verified expected stdout:**

~~~text
[agent] captured demo/target/Greeter
[app] message=AFTER!
~~~

This is the actual output for the Java 17-target experiment when run on a test JDK with the default system class loader. If re-running, use a **new** directory such as `captures/run-002`; `CREATE_NEW` intentionally prevents overwriting `run-001` files.

**If run without the agent**:

~~~bash
java -cp out/app demo.app.App
~~~

the application uses the untransformed literal:

~~~text
[app] message=BEFORE
~~~

This proves the behavioral difference comes from the runtime transformer, not from modifying the `Greeter.java` source.

## 6. Using `javap` to read the two saved files

### 6.1. Commands to inspect both the constant pool and bytecode

`javap` is the disassembler tool included in the JDK. In the lab:

~~~bash
javap -c -v captures/run-001/Greeter-before.class
javap -c -v captures/run-001/Greeter-after.class
~~~

Depending on the level of detail needed, you can add:

~~~bash
javap -c -v -p captures/run-001/Greeter-after.class
~~~

The flags:

| Flag | Meaning |
|---|---|
| `-c` | Disassemble bytecode instructions of methods |
| `-v` (or `-verbose`) | Show verbose classfile details: constant pool, flags, version, attributes, line tables... |
| `-p` (or `-private`) | Show all members, including private, instead of only public/protected |
| `-l` | Show line/local variable tables if present; `-v` also provides much of this information |
| `-s` | Print internal type signatures/descriptors; `-v` also includes descriptors |
| `-classpath` | Used to look up a class by **class name**; not needed when you already provide the path to a snapshot file |

**Note:** passing `captures/.../Greeter-before.class` to `javap` instructs it to read **that classfile**. If you only use:

~~~bash
javap -c -v -classpath out/app demo.target.Greeter
~~~

`javap` will read `Greeter.class` located in `out/app`, which is the **original file from javac**, not the `Greeter-after.class` file that the agent saved. When debugging a transformer, confusing these two paths can lead to the false conclusion that the transformation “did not happen”.

### 6.2. Sections to look for in the output

In the before snapshot, the constant pool and method body will have content similar to:

~~~text
#N = String             #M          // BEFORE
#M = Utf8                             BEFORE

public static java.lang.String message();
  Code:
     0: ldc           #N                // String BEFORE
     2: areturn
~~~

In the after snapshot:

~~~text
#N = String             #M          // AFTER!
#M = Utf8                             AFTER!

public static java.lang.String message();
  Code:
     0: ldc           #N                // String AFTER!
     2: areturn
~~~

These are **abbreviated representative lines**, not the full `javap` stdout. Indices `#N/#M` may vary by compiler/versions. The actual experiment shows both snapshots have the `message()` method, the `ldc` instruction at the same offset, and the constant pool literals `BEFORE` and `AFTER!` respectively.

Why is the instruction still `ldc`? Because the classfile `CONSTANT_String` points to the modified `CONSTANT_Utf8`, so no change to the instruction opcode/operand is needed. This is a minimal demo case; with a transformer that inserts instructions, differences may appear in `Code`, branch offsets, the exception table, StackMapTable, and descriptors.

### 6.3. Cross-checking with the original `.class` file

Read the file produced by `javac`:

~~~bash
javap -c -v out/app/demo/target/Greeter.class
~~~

In the lab with **only one transformer and no upstream modifications**, the original content and the before capture are expected to be equivalent, because the callback receives the bytes provided by the class loader. However, in a system with multiple transformers:

- `out/app/.../Greeter.class` is the build artifact on disk.
- `Greeter-before.class` is the **input to this transformer's callback**.
- `Greeter-after.class` is the **array returned by this transformer**.
- The JVM-installed bytes may be the result of **subsequent steps**, or the JVM may preserve equivalent information while the classfile layout is not byte-for-byte identical to the snapshot.

Do not automatically assume any pair among the four items above is “guaranteed identical”.

### 6.4. Hash, file size, and diff: complementary, not a replacement for `javap`

On Linux/macOS there is the `sha256sum` utility:

~~~bash
sha256sum captures/run-001/Greeter-before.class captures/run-001/Greeter-after.class
~~~

On PowerShell:

~~~powershell
Get-FileHash captures/run-001/Greeter-before.class -Algorithm SHA256
Get-FileHash captures/run-001/Greeter-after.class -Algorithm SHA256
~~~

They tell you whether two files **differ in bytes** and help preserve integrity when sharing with others. Hashes **do not tell you where the change is**; use `javap` to understand the constant pool and instructions.

A text diff can be useful:

~~~bash
javap -c -v captures/run-001/Greeter-before.class > before.txt
javap -c -v captures/run-001/Greeter-after.class > after.txt
diff -u before.txt after.txt
~~~

These commands create **report files chosen by the user**, not files automatically generated by the agent. `javap -v` also prints the classfile path, so the diff may contain differing lines purely due to **filenames**. Focus on the constant pool/method code/attributes and account for incidental differences caused by paths, compiler, or version.

On PowerShell:

~~~powershell
javap -c -v captures/run-001/Greeter-before.class > before.txt
javap -c -v captures/run-001/Greeter-after.class > after.txt
Compare-Object (Get-Content before.txt) (Get-Content after.txt)
~~~

If your program saves multiple output classfiles, adding checksums and manifest metadata helps preserve the exact **input/output relationship of the same transform pass**.

## 7. Reading `javap` to diagnose common bytecode errors

Some symptoms and where to inspect:

| Symptom | Compare in `javap -v -c -p` | Hypothesis to verify |
|---|---|---|
| Hook does not appear | `Code` of target method, `invokestatic`/`invokevirtual` calling helper | Transformer filtered the wrong class/method or returned `null` |
| `NoClassDefFoundError` at runtime | Class/method references, descriptors in constant pool | Helper is not visible to target class loader/module |
| `NoSuchMethodError` | `Methodref`, owner, name, descriptor | Actual helper signature differs from inserted reference |
| `IllegalAccessError` | Owner/descriptor and module/package/class loader context | Access permissions differ from what transformer assumed |
| `VerifyError` | StackMapTable, branch offsets, stack/local use | Frame/bytecode writer generated invalid code |
| `ClassFormatError` | Classfile header, constant pool, attributes | Classfile layout invalid before JVM verification |
| `UnsupportedClassVersionError` | `major version` in classfile header | Writer targeted the wrong Java version |
| Exception handler stops working | `Exception table`, `from/to/target` ranges | Instruction inserted in the wrong try/catch/finally region |
| Method appears unchanged | Class name, method descriptor, class loader identity | Reading a different `.class` copy or same name in another loader |
| Multiple dumps overwrite each other | Filename/sequence/phase metadata | Naming bug, multiple callbacks |
| JVM runs differently from output snapshot | Transformer list and order; retransform/redefine phase | Another transformer runs later, or runtime chose different bytes |

**`javap` is a disassembler, not a formal verifier or profiler.** It can read a classfile and print bytecode, but it does not prove the JVM will accept every StackMapTable, module access, or dependency. Combine it with actual load/run, behavior tests, JVM exceptions, and — where appropriate — the bytecode checker of the classfile-writing library.

### 7.1. Constant pool references and descriptors

Example output:

~~~text
#12 = Methodref          #3.#21   // demo/agent/Hook.enter:()V
#21 = NameAndType        #22:#23  // enter:()V
#22 = Utf8                         enter
#23 = Utf8                         ()V
...
  invokestatic #12                 // Method demo/agent/Hook.enter:()V
~~~

This is an **illustrative example**, not present in the Greeter demo. You need to verify that the owner name and method descriptor are correct, the helper is visible to the target class's loader/module, and the method signature does not differ in return type or parameter count.

### 7.2. Exception tables, monitors, and frames

A transformer inserting logging before/inside `try/catch/finally` can break side-effect ordering or miss exception paths. If instrumenting `synchronized` methods or code with monitorenter/monitorexit, check balance and scope. `javap -v` can show you the StackMapTable/exception table, but the JVM verifier and runtime tests are needed to confirm validity.

If the agent only measures duration, test both normal returns and exceptions, methods with multiple returns, constructors, static initializers, bridge methods, and lambdas. Saving output bytes of the exact method before/after helps distinguish “transform did not run” from “transform has wrong semantics”.

### 7.3. Already-loaded methods still running the old version?

If a class was loaded **before** registering the transformer via Attach, adding the transformer does not automatically replay already-loaded classes. Running `javap` on a separate output file **does not prove** the JVM redefined/retransformed that class. For loaded classes, you must consider `isRetransformClassesSupported`, `isModifiableClass`, and `retransformClasses`/`redefineClasses` as appropriate, along with active stack frame constraints.

This is why you should save **phase** metadata and verify behavior after the operation, rather than just seeing an `after.class` file on disk.

## 8. Security and operational limitations of saving classfile bytes

### 8.1. Classfile data can be sensitive

A snapshot can contain:

- Proprietary algorithms and class/method/field names.
- String literals containing URLs, headers, tokens, or passwords if source accidentally hardcodes them.
- Debug symbols, method parameter names, source file names, and line tables.
- Internal service names, package layout, and dependency information.

Do not automatically save all classfiles to `/tmp`, upload them to shared storage, or attach them to public incident tickets. Save only with consent/policy, in a directory with restricted permissions, retention periods, and appropriate secure deletion mechanisms. Do not treat `.class` files as “non-sensitive” just because `.java` source is absent.

### 8.2. Preventing classpath and path traversal risks

The demo takes the capture directory path from the user's agent args and uses `Path.of(args).toAbsolutePath().normalize()`. This is **not** a sandbox mechanism. In production:

- Only allow writing to a configured base directory with explicit permissions.
- Do not build filesystem paths directly from `className`/module name coming from untrusted input without normalization/validation.
- Consider symlink attacks, file permissions, and all forms of overwrite.
- Use opaque/sequence names to avoid leaking system structure.
- Cap file counts, total bytes, file age, and storage locations.
- Do not upload confidential classfiles to analysis environments outside the organization without authorization.

`CREATE_NEW` prevents **overwriting an existing file** per filesystem semantics, but does not by itself solve all race/permission/symlink concerns in large systems.

### 8.3. Synchronous I/O inside a transformer

The callback may run on a latency-sensitive class loading path. If `Files.write` waits on disk or antivirus, class definition can slow down. If the callback calls an unloaded library, a logging framework can trigger recursive class loads. When multiple threads load classes concurrently, there is a risk of contention and cascading delays.

The production solution is typically:

~~~text
filter very early
    |
clone input/returned bytes (bounded)
    |
enqueue snapshot into bounded internal queue
    |
dedicated writer thread -> file/metadata/metrics
~~~

**This architectural pattern is not standalone code.** The writer thread requires lifecycle design, flushing, shutdown, overflow/drop counters, and a safe logging mechanism. If the queue is full, an observability agent typically chooses a policy to drop snapshots while counting drops rather than blocking class-defining threads indefinitely. However, if the goal requires mandatory byte-for-byte capture, the policy may differ and must be stated upfront.

### 8.4. Non-atomic snapshot pairs and callback ordering

Two separate `Files.write` calls are not atomic as a pair. If writing before succeeds but after fails, an orphan snapshot remains on disk. A reliable system needs to:

1. Write to separate staging files for the same request ID.
2. Flush/verify integrity, and generate checksum metadata.
3. Move/mark the pair complete once both have succeeded.
4. Never throw an error that accidentally alters the class loading outcome just because auxiliary capture failed, unless policy requires fail-fast.
5. Track partial failures and clean up staging files.

`AtomicBoolean` in the demo limits capture to **one callback**; it does not assign sequence IDs for thousands of class definitions. In production, a concurrent registry with quotas and keys built from **class identity / phase / sequence** is needed to avoid overwrites, uncontrolled disk usage, and memory leaks from retaining loaders.

## 9. Comparing performance and correctness when capture is enabled

Snapshot measurement is only diagnostic if you can account for the **side effects of capturing itself**.

| Dimension | Question/metric needed |
|---|---|
| Class loading latency | Does the callback increase class define/verify/link time? |
| Startup time | How much do total `premain` and pre-main class loading times increase? |
| CPU | How much do parsing, hashing, and copying bytes cost? |
| Memory | How much `byte[]` is held in the queue? Is it capped by quota? |
| Disk | File count, total bytes, write time, write failures |
| Functional correctness | Does the method still return the expected result/exception? |
| Transformation correctness | Does the output have the right class name, version, method signatures, StackMapTable? |
| Coverage | Are the right target classes hit? Are unexpected ones skipped? |
| Security | Do files/logs contain sensitive data? Is the retention policy appropriate? |

When diagnosing a bug that only occurs under load, enabling capture may change the bug's timing; compare against no-capture/low-capture runs using timestamps and bounded logs. Do not conclude “the bug disappeared when capture was on” means “the bug is fixed”.

### A common misconception: low CPU does not mean capture is cheap

If the filesystem is slow, a thread can **block** in I/O without high CPU utilization, yet startup/classloading latency and p99 suffer. Therefore, measure elapsed time and blocked time alongside CPU. If capture uses a bounded queue, do not measure only enqueue time while ignoring write/dropped rates.

## 10. Error cases and how to handle them

| Symptom | Possible cause | How to check |
|---|---|---|
| No snapshot files | Class name filter mismatch on `/`, class not loaded, excluded by loader/module/phase filter | Confirm internal name and that target actually loaded |
| Prints `[agent] skip capture: expected literal not found` | Greeter source changed, compiler used different literal, or upstream bytes were modified | Run `javap -v` on build artifact and check exact UTF8 |
| Prints `classfile too large` | Exceeded demo's 1 MiB limit | Raise quota in a controlled way or choose another class |
| Prints `FileAlreadyExistsException` | Reused `run-001` directory, `CREATE_NEW` refused overwrite | Choose a new directory, do not accidentally delete old snapshots |
| Has before but missing after | Error writing the second file | Check stderr, filesystem, permissions; pair is incomplete |
| Has after but app still prints BEFORE | Read wrong JVM/run, target not loaded, downstream transformer overwrote output, or different artifact file | Verify runtime args, classloader, pipeline, and behavior |
| App throws `VerifyError` | Invalid output classfile/frames | Analyze `javap -v`, bytecode checker, and verifier error |
| `javap` shows BEFORE in “after” | Snapshot is not the returned bytes, wrong file, or patch did not work | Check file paths and transform code |
| `javap -classpath out/app demo.target.Greeter` still shows BEFORE | Reading original file after `javac` | Pass the path to `Greeter-after.class` |
| Each run creates files with the same name | Missing run/phase/classloader/sequence metadata | Identify each callback uniquely, do not overwrite |
| App is still correct but startup is slow | Synchronous filesystem I/O in callback | Narrow filter, quota, measure time, bounded async writer |
| Bytecode from snapshot misses some transformations | Capturing mid-pipeline, not at the end | Identify agent/transformer order and phase |

A dump is only useful if you know **which callback**, **which class**, **which loader**, and **which point in time** it belongs to. Without metadata, two classfiles with the same package can lead to wrong conclusions.

## 11. Practical test matrix

| Case | Adjustment | Expected result |
|---|---|---|
| 1. Baseline | Run app without `-javaagent` | `[app] message=BEFORE` |
| 2. Standard demo | Agent, new directory, correct Greeter target | Two files, agent captured, app AFTER! |
| 3. Byte comparison | `javap -v -c` on before/after | Constant pool literal differs, method `ldc` matches |
| 4. No overwrite | Re-run with same `run-001` | Logs I/O error; old files are not overwritten |
| 5. New directory | Use `run-002` | New capture succeeds |
| 6. Name filter | Change target name or app does not load Greeter | No new files created |
| 7. Loader filter | Load class with same name from custom loader | Non-matching loader callback is not captured |
| 8. Phase filter | Actively retransform/redefine in an extended exercise | Demo does not capture passes with `classBeingRedefined != null` |
| 9. No literal | Change Greeter to return `"CHANGED"`, rebuild | Patch returns null, no pair captured, app returns source literal |
| 10. Invalid output | Use a transformer generating an invalid classfile in a separate test | JVM may reject it, `javap` does not replace verifier |
| 11. Disk full/permission | Only in a controlled test sandbox | Capture logs error, does not claim files exist |
| 12. Multiple transformers | Register additional transformers running before/after | before/after only bounds one callback, analyze pipeline |
| 13. Large class | Input longer than `MAX_BYTES` | Skips and reports reason |
| 14. Security | Capture class with sensitive string literal in a simulated environment | Quota, access permissions, deletion, and no unauthorized upload |

**Do not run “disk full” fault injection on a development machine or real production**: use a controlled sandbox/quota to avoid affecting the system and other applications.

## 12. Before–After Diagnostic Checklist

### Before enabling snapshot

- [ ] Identified **a single class/internal name** or a small intentional allowlist?
- [ ] Identified defining class loader and module/phase?
- [ ] Set budgets for capture count, bytes, file count, and lifetime?
- [ ] Dedicated directory, access permissions, no overwrite, and data cleanup policy in place?
- [ ] Aware that snapshots can contain proprietary code, debug symbols, and string literals?
- [ ] Know which agents/transformers participate in the pipeline, or have a plan to find out?
- [ ] Know what failure needs to be proved: missing hook, VerifyError, linkage error, or wrong behavior?
- [ ] Have baseline tests and overhead measurement tools?

### During capture

- [ ] Filter metadata **before** parsing/copying/writing bytes?
- [ ] Do not mutate `classfileBuffer` in-place?
- [ ] Handle `null` output explicitly without creating misleading transformed labels?
- [ ] Input and returned bytes share the same run ID/phase/class identity?
- [ ] Write raw bytes, no `String` conversion?
- [ ] Control concurrent callbacks and avoid recursive class loading?
- [ ] Log skip/I/O failures without leaking sensitive information?
- [ ] If capturing via queue, measure dropped/queued/written counts?
- [ ] Limit synchronous I/O inside the transformer callback?

### When using `javap`

- [ ] Read the **exact snapshot file path**, not just `-classpath` pointing to build output?
- [ ] Use `-v` to inspect constant pool, version, attributes/StackMapTable?
- [ ] Use `-c` to inspect instructions/branch targets and exception table?
- [ ] Use `-p` if private methods/constructors are needed?
- [ ] Distinguish snapshot output from the final bytes executed by the JVM?
- [ ] Hash only confirms bytes differ, not validity?
- [ ] Run the JVM/behavior tests and read the first error?
- [ ] Document scope/limitations of conclusions?

### After diagnosis

- [ ] Do not leave capture enabled indefinitely or keep files past retention?
- [ ] Do not copy snapshots containing secrets onto tickets/buckets without authorization?
- [ ] Have an accurate conclusion: wrong transformer filter, invalid output, invisible helper, or downstream rewrite?
- [ ] Reproducible from identified source/agent/build/configuration?
- [ ] If the bug disappeared during capture, considered measurement overhead/race timing?

## 13. Review Questions

**1.** Why is the before file in transformer B's callback not always identical to the original `.class` file?

> Because transformer A may have modified the bytes before B. B's `classfileBuffer` is the input **at B's position in the pipeline**.

**2.** Is B's after file guaranteed to be the final bytes installed by the JVM?

> No. Transformer C may run after B, and the JVM still verifies/links and manages certain internal representation details. The file only proves the bytes B returned.

**3.** Why must `className` be filtered before reading/writing files?

> To reduce overhead, disk usage, target mix-ups, and the risk of capturing sensitive data from unrelated classes.

**4.** Inside the callback, in what form does the class name `demo.target.Greeter` appear?

> Internal name `demo/target/Greeter`, using `/` instead of dots.

**5.** What does `classBeingRedefined != null` indicate?

> The callback is processing an existing class in a redefine/retransform pass, not an initial load per the demo filter.

**6.** Is `Files.writeString(path, new String(bytes))` a valid way to save a `.class` file?

> No. Classfile bytes are binary; converting through text encoding can corrupt the data. Use `Files.write(path, bytes, ...)`.

**7.** Why does `javap -classpath out/app demo.target.Greeter` still print BEFORE when the agent runs successfully?

> It reads the build artifact in `out/app`, not the `Greeter-after.class` snapshot. You must pass the path to the actual after file.

**8.** How do `javap -c` and `javap -v` differ?

> `-c` displays instructions; `-v` adds the constant pool, attributes, version, and metadata. Use both for broader comparison.

**9.** When the after file has a method reference to a helper but the app throws `NoClassDefFoundError`, what should you check?

> Loader/module visibility, method/class owner, descriptors, when the helper becomes available, the pipeline, and the first linkage failure — not just the bytes.

**10.** If `transform` returns `null`, has bytecode transformation succeeded?

> Not at that step; `null` means the transformer did not provide replacement bytes.

**11.** In the demo, why can `"BEFORE"` be changed to `"AFTER!"` without fixing branch offsets?

> Both literals are six ASCII bytes long in the constant pool; the output preserves classfile length and structure, changing only the UTF8 value referenced by `ldc`.

**12.** Why shouldn't the demo's constant pool parser be used for production applications?

> It is a narrow demo, does not support all classfiles/versions/cases, and does not check all verifier constraints; use a proper bytecode library and testing.

**13.** Does `CREATE_NEW` guarantee that the before/after snapshot pair is written atomically?

> No. Two separate write calls can succeed/fail independently. Production needs staging/metadata/commit protocols and cleanup.

**14.** If a class has the same name but is loaded by two defining loaders, can they share the same snapshot filename?

> They should not. Class identity is tied to the defining loader; loader/phase/sequence metadata and collision avoidance are needed.

**15.** Once you have input/output snapshots and reasonable `javap` output, is the runtime guaranteed to be completely correct?

> Not yet. The JVM must verify/link successfully, and you must test returns/exceptions/side effects, check helpers, modules, and other transformers.

## 14. Official References

- Java SE 17, `ClassFileTransformer` — load/redefine/retransform callbacks, order, buffer/return contract, `null`, and exceptions: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17, `Instrumentation` — `addTransformer`, `retransformClasses`, `redefineClasses`, runtime capabilities: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17, `java.lang.instrument` package — startup agent and `Premain-Class` manifest: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Java SE 17, `javap` tool — `-c`, `-v`, `-p`, file path, and classpath flags: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- Java SE 17, Java Virtual Machine Specification, Chapter 4 — classfile structure, constant pool, Code/StackMapTable attributes: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- Java SE 17, `Files` — `write(Path, byte[], OpenOption...)` and atomicity limitations: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Java SE 17, `StandardOpenOption.CREATE_NEW` — file creation with existence check: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html
