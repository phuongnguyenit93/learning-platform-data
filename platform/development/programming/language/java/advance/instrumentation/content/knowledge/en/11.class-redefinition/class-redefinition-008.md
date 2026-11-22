# Redefinition: Simultaneously Replacing Dependent Classes and Evaluating the Whole Set Result

In Java Instrumentation, **Instrumentation.redefineClasses(ClassDefinition... definitions)** allows a Java agent to replace **the definitions of multiple classes already loaded by the JVM** in **the same request**. This is an important capability when a change to class A depends on a simultaneous change to class B: for example, an API class calling a Repository class, or a coordinator and a processor that need to use the same algorithm version.

According to the Java SE 17 contract, **redefineClasses operates on a set to support interrelated changes**. If **that call itself throws an exception**, **no classes in the set are redefined by that call**. This is completely different from calling redefineClasses(A) first and redefineClasses(B) afterward: if A is installed successfully while B fails, the JVM **does not automatically revert A** just because B belongs to the next call.

This lesson explains **ClassDefinition**, the **Can-Redefine-Classes** capability, class schema change limits, selecting dependent classes, atomicity at the class definitions level, how to verify **the whole set after an update**, and a runnable Java 17+ example with **three scenarios**: a successful simultaneous update, a full batch failure, and two separate calls producing a partial update result.

## 1. Learning Objectives

After studying this lesson, you should be able to:

1. Distinguish **redefineClasses** from **retransformClasses** and new class loading.
2. Use **ClassDefinition(Class<?> theClass, byte[] theClassFile)** to bind **the exact Class object** with a replacement class file.
3. Understand why classes with definition-level dependencies must be placed in **the same redefineClasses(...) call**.
4. Accurately analyze the **all-or-none guarantee when a call fails** and the limits of that guarantee.
5. Check **isRedefineClassesSupported()** and **isModifiableClass(...)**, and identify the correct defining class loader/module.
6. Prepare valid bytecode: preserve the class name and the parts of the class schema that are not allowed to change.
7. Verify **the entire group**, rather than concluding success from a single class or a single transformer log.
8. Distinguish the new definition from **active stack frames**, instance/static state, and side effects that may still remain.
9. Have a rollback/retry plan and observe state without creating a "half old version, half new version" bug.

## 2. Why Must Multiple Classes Be Replaced as a Set?

Suppose an application has:

~~~java
// Source code illustrating architecture, not a standalone runnable file.
public final class Api {
    public static String route() {
        return "API_V1>" + Store.value();
    }
}

public final class Store {
    public static String value() {
        return "STORE_V1";
    }
}
~~~

A logic change needs to move both to version 2:

~~~text
Api V1 ───── calls ────> Store V1
   │                        │
   │                        └── returns STORE_V1
   └── formats API_V1>STORE_V1

Target transition:
Api V2 ───── calls ────> Store V2
   │                        │
   │                        └── returns STORE_V2
   └── formats API_V2>STORE_V2
~~~

If only Api is replaced first, for a period of time the application may receive **API_V2>STORE_V1**. If the two classes only change *method bodies* while keeping the binary contract, this mixed state does not necessarily cause a JVM error; however, it can be semantically wrong—for example, protocol version A requires new data that only version B understands correctly.

A single request:

~~~java
// Illustration inside an agent/service that already has Instrumentation inst.
inst.redefineClasses(
    new ClassDefinition(Api.class, apiV2Bytes),
    new ClassDefinition(Store.class, storeV2Bytes)
);
~~~

allows the JVM to process two **interrelated class definitions** in the same call. Conversely:

~~~java
// Two independent calls, NOT a single transaction.
inst.redefineClasses(
    new ClassDefinition(Api.class, apiV2Bytes)
);
inst.redefineClasses(
    new ClassDefinition(Store.class, storeV2Bytes)
);
~~~

has no rollback guarantee across the boundary of the two calls. If the second call fails, Api installed in the first call can remain at V2.

### 2.1. Set Result vs. Per-Class Result

| Case | Single call redefine(A2, B2) | Two calls redefine(A2), then redefine(B2) |
| --- | --- | --- |
| Both A2/B2 are valid | The call succeeds, both definitions are updated | Both calls can succeed |
| B2 is not a valid class file | **The call throws an error; neither A2 nor B2 is installed from this call** | A2 may already be installed; B2 fails |
| B is not modifiable | The request fails, no element is installed | If A was already installed first, the JVM does not revert A |
| Verifying a synchronized logic version | Easy to attach a single version/operation ID to the whole group | Must manually coordinate independent updates |
| Retry | Can fix the cause and resend the entire group | Must know exactly which call succeeded to avoid version mismatch |

For dependent classes, **the atomic boundary of the request** must reflect **the compatibility boundary of the business logic**; choosing a set that is too small can cause the application to temporarily or permanently run two out-of-sync versions.

## 3. At What JVM Layer Does Redefinition Operate?

**redefineClasses** does not create a new Class with the same name as the old one. It asks the JVM to replace the **definition** of an **already loaded Class object**, within the limits allowed by the JVM. Existing objects remain instances of that class; fields/static state do not automatically reset to their initial state.

Conceptual diagram:

~~~text
In a running JVM:

Class A (v1)    Class B (v1)
       │           │
       └─────┬─────┘
             │  agent already has Instrumentation
             ▼
  prepare ClassDefinition(A.class, bytesV2_A)
  prepare ClassDefinition(B.class, bytesV2_B)
             │
             ▼
    redefineClasses(defA, defB)
             │
       ┌─────┴─────┐
       │           │
   all valid    any class causes error
       │           │
       ▼           ▼
  Install whole   Throw exception
  set of new      No class in that
  definitions     request is redefined
~~~

**ClassDefinition** is simply a Java object holding the **target Class<?>** and the **byte[] of the new class file**. The byte[] must describe **that same class** and satisfy schema constraints; you cannot pass a class file of a differently named class and ask the JVM to "rename the identity" of a running class.

### 3.1. Exact Interface in Java 17

~~~java
// JDK 17 API signatures. Reference snippet, not a standalone file.
boolean isRedefineClassesSupported();
boolean isModifiableClass(Class<?> theClass);

void redefineClasses(ClassDefinition... definitions)
    throws ClassNotFoundException, UnmodifiableClassException;
~~~

**ClassNotFoundException** still appears in the signature for API compatibility reasons; the Java 17 Javadoc notes that this exception **cannot be thrown by the current method**. Class format, linkage, and unsupported change errors can be an **Error** or a runtime exception, rather than being wrapped in a standard checked exception.

### 3.2. ClassDefinition Holds a Reference to the Byte Array

The Javadoc of the **ClassDefinition(Class, byte[])** constructor explicitly states that it **does not copy the byte[]**, but keeps a reference to the array passed by the caller. Therefore:

~~~java
// Illustration: keep the array stable while the request is using it.
byte[] stableBytes = Files.readAllBytes(path);
ClassDefinition definition =
        new ClassDefinition(targetClass, stableBytes);

// Avoid doing this before/during redefine:
stableBytes[0] = 0; // Can corrupt the header and alter the input data.
~~~

The snippet above uses **Files** and **Path** imported in the actual file; it only illustrates data ownership. You should produce the complete replacement data, verify/hash it first, and then **treat the byte[] as immutable** until the request finishes; if multiple threads prepare/deploy, use a snapshot/copy and clear ownership coordination.

## 4. Capability: Can-Redefine-Classes Is Required, Not Can-Retransform-Classes

**Redefinition** and **retransformation** are two **different** optional capabilities:

| API | Goal | Manifest capability |
| --- | --- | --- |
| **redefineClasses(...)** | Install class file bytes supplied by the caller | **Can-Redefine-Classes: true** |
| **retransformClasses(...)** | JVM re-runs the transform process from base class bytes | **Can-Retransform-Classes: true** |

For a startup Java agent, the manifest for the example is:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.AgentEntry
Can-Redefine-Classes: true
~~~

Even when the manifest declares **true**, the JVM must actually support the capability. Check in code:

~~~java
// Illustration inside an agent that has received Instrumentation inst.
if (!inst.isRedefineClassesSupported()) {
    throw new IllegalStateException("Class redefinition unavailable");
}
~~~

If the capability is not granted, **redefineClasses** may throw **UnsupportedOperationException**. **isModifiableClass** returning true is only a necessary condition, not a guarantee that redefinition will succeed: schema, class file version, internal name, linker/verifier, and other transformers can still cause the request to fail.

### 4.1. Avoiding Selecting the Wrong Class in Complex Class Loaders

**Class<?>** is the true identity of a running class, not just an FQCN string. Two plugins can both have **com.example.Service**, defined by two different class loaders; those are **two different JVM types**. A class file taken from plugin A's JAR and applied to plugin B's Class may not match, even if the name is identical.

If you need to find an already loaded Class, you can iterate **inst.getAllLoadedClasses()**, filtering by the exact binary name, defining class loader, module, and required criteria. Do not blindly replace this with **Class.forName("...")** if doing so loads a new class or selects the wrong loader.

### 4.2. Array/Primitive Classes and Certain Special JVM Classes

According to the Java 17 Javadoc, **primitive classes** and **array classes** are not modifiable. Therefore, do not put **int[].class** or **int.class** into a request expecting to replace their bytecode. Check each class:

~~~java
for (Class<?> type : targets) {
    if (!inst.isModifiableClass(type)) {
        throw new IllegalArgumentException(
            "Class not modifiable: " + type.getName()
        );
    }
}
~~~

A class may be modifiable yet still reject new class bytes due to schema limit violations. Preflight checks help catch errors early, **but do not replace the checks inside redefineClasses**.

## 5. Change Limits: Not Arbitrary Hot Deployment

In Java 17, redefining an already loaded class **does not allow every kind of source change**. Changes that are commonly prohibited or restricted at the JVM TI level include:

- Adding or removing fields/methods of an already defined class.
- Changing the class name, supertype, or disallowed inheritance relationships.
- Changing the descriptor/signature of a method or field in a way that alters the loaded class schema.
- Changing certain access/modifiers, structures related to records/nests/modules, and attributes that the JVM does not support updating.
- Supplying class bytes with the wrong version/invalid format or an internal name different from the class being redefined.

Suitable changes are typically **changing method body contents** within the existing schema limits; the compiler may produce a different constant pool/Code attribute as long as the definition remains valid. In the example below, both versions of each class have **the same package name, class name, constructor, and the same public static method with an unchanged descriptor**; only string values and internal code change.

**Note:** Do not assume that every change allowed during class loading is also allowed during redefinition. Real projects must verify against the actual JVM TI/JDK and run verifier/linkage tests on the new bytes.

### 5.1. Avoid Changing the Binary Protocol Between Two Classes When Disallowed

For example, suppose you want to change **Store.value():String** to **Store.value(int):String** and change **Api.route()** to call the new descriptor. Even if you want to redefine both at the same time, a standard JVM **does not allow changing the method set/schema like that** for already loaded classes. Set atomicity does not turn an invalid change into a valid one.

If you need to upgrade a binary protocol in that way, design **API versioning upfront**, use **indirection/helpers**, a new class loader, or a rolling restart depending on the environment. Use batch redefine for versions **compatible with JVM limits**.

## 6. Java 17+ Hands-On Lab: Replacing Two Dependent Classes in One Request

This lab **uses no external bytecode libraries**. We compile **two source sets in parallel**: one running version 1, and one producing version 2 class files. The agent loads at JVM startup and provides the Instrumentation handle to the sample application. The application reads **version 2 bytes from disk** and calls redefineClasses.

Three modes are explicitly designed:

- **batch-ok**: version 2 class files of both Api and Store are valid; send **one** redefineClasses(defApi, defStore).
- **batch-bad**: Api V2 is valid, but Store bytes are intentionally not a class file; send both **in one** redefineClasses, expecting **no classes installed**.
- **split-bad**: call redefineClasses(Api V2) first, which succeeds, then call redefineClasses(Store invalid), which fails; demonstrates **a partial update result caused by two independent requests**.

### 6.1. Directory Structure

~~~text
redefine-batch-demo/
  agent.mf
  src/
    agent/
      demo/
        AgentEntry.java
    base/
      demo/
        Api.java
        Store.java
        Main.java
    patch/
      demo/
        Api.java
        Store.java
~~~

The two files with the same name **Api.java** in **src/base** and **src/patch** have the same FQCN **demo.Api** but are compiled into **two different output directories**, never compiled together in one pass. The same applies to **demo.Store**.

### 6.2. Agent File: src/agent/demo/AgentEntry.java

~~~java
package demo;

import java.lang.instrument.Instrumentation;

public final class AgentEntry {
    private static volatile Instrumentation instrumentation;

    private AgentEntry() {
    }

    public static void premain(String options, Instrumentation inst) {
        if (inst == null) {
            throw new IllegalArgumentException("Instrumentation missing");
        }
        if (instrumentation != null) {
            throw new IllegalStateException("Agent installed twice");
        }
        instrumentation = inst;
    }

    public static Instrumentation required() {
        Instrumentation current = instrumentation;
        if (current == null) {
            throw new IllegalStateException(
                    "Start JVM with -javaagent:redefine-agent.jar"
            );
        }
        return current;
    }
}
~~~

**Instrumentation** is passed by the JVM into **premain**. **volatile** ensures the assigned reference is safely read from another thread under the Java Memory Model, though this example uses only one thread. In a real system, concurrent redefine requests and agent lifecycle must be coordinated. Do not write your own Instrumentation implementation or assume every application can obtain Instrumentation from a global API.

### 6.3. Manifest File: agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: demo.AgentEntry
Can-Redefine-Classes: true
~~~

**The manifest must have a trailing newline at the end of the file**. This is a **startup agent** using **-javaagent**, not dynamic attach; loading the agent after startup requires **Agent-Class** and an appropriate **agentmain**.

### 6.4. Two Version 1 Classes: src/base/demo/Api.java and Store.java

**File src/base/demo/Api.java**

~~~java
package demo;

public final class Api {
    private Api() {
    }

    public static String route() {
        return "API_V1>" + Store.value();
    }
}
~~~

**File src/base/demo/Store.java**

~~~java
package demo;

public final class Store {
    private Store() {
    }

    public static String value() {
        return "STORE_V1";
    }
}
~~~

**Api.route()** directly calls **Store.value()** at runtime; it does not just read a **static final String field** that risks being inlined at compile time. The two classes have a real call dependency, so if only Api is redefined, the Api V2 method will call Store V1. We will observe that mixed state in split-bad mode.

### 6.5. Two Version 2 Classes: src/patch/demo/Api.java and Store.java

**File src/patch/demo/Api.java**

~~~java
package demo;

public final class Api {
    private Api() {
    }

    public static String route() {
        return "API_V2>" + Store.value();
    }
}
~~~

**File src/patch/demo/Store.java**

~~~java
package demo;

public final class Store {
    private Store() {
    }

    public static String value() {
        return "STORE_V2";
    }
}
~~~

Both versions have **the same package, class name, constructor, and method descriptor**, changing only the string literal in the method. The JVM is permitted to redefine the method body if the capability and remaining conditions are satisfied.

Do **not** change the **Store.value()** method to **value(int)** or add new fields in the patch; doing so would break the goal of testing atomicity by causing an unintended independent schema error.

### 6.6. Coordinator: src/base/demo/Main.java

~~~java
package demo;

import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Main {
    private Main() {
    }

    private static String snapshot() {
        return Api.route() + "|" + Store.value();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2
                || (!"batch-ok".equals(args[0])
                    && !"batch-bad".equals(args[0])
                    && !"split-bad".equals(args[0]))) {
            throw new IllegalArgumentException(
                    "Usage: Main batch-ok|batch-bad|split-bad patch-dir"
            );
        }

        String mode = args[0];
        Path patchDir = Path.of(args[1]);

        Instrumentation inst = AgentEntry.required();
        if (!inst.isRedefineClassesSupported()) {
            throw new IllegalStateException(
                    "This JVM/agent lacks class redefinition capability"
            );
        }
        if (!inst.isModifiableClass(Api.class)
                || !inst.isModifiableClass(Store.class)) {
            throw new IllegalStateException(
                    "Api or Store is not modifiable"
            );
        }

        // Ensure both classes are loaded and running version V1.
        String before = snapshot();
        System.out.println("BEFORE=" + before);

        // Read the separately compiled V2 class files.
        byte[] apiV2 = Files.readAllBytes(
                patchDir.resolve("demo/Api.class"));
        byte[] storeV2 = Files.readAllBytes(
                patchDir.resolve("demo/Store.class"));

        if (!"batch-ok".equals(mode)) {
            // Intentionally create an invalid ClassDefinition for Store:
            // short class file without CAFEBABE magic.
            storeV2 = new byte[] {0, 1, 2, 3};
        }

        ClassDefinition apiDef =
                new ClassDefinition(Api.class, apiV2);
        ClassDefinition storeDef =
                new ClassDefinition(Store.class, storeV2);

        boolean failed = false;
        try {
            if ("split-bad".equals(mode)) {
                // Two separate requests: Api may already be installed
                // before Store fails.
                inst.redefineClasses(apiDef);
                inst.redefineClasses(storeDef);
            } else {
                // ONE request for the entire dependent class set.
                inst.redefineClasses(apiDef, storeDef);
            }
            System.out.println("REDEFINE_OK");
        } catch (UnmodifiableClassException
                 | UnsupportedOperationException
                 | LinkageError error) {
            failed = true;
            System.out.println("REDEFINE_FAILED");
        }

        String after = snapshot();
        System.out.println("AFTER=" + after);

        String expected = switch (mode) {
            case "batch-ok" -> "API_V2>STORE_V2|STORE_V2";
            case "batch-bad" -> before;
            case "split-bad" -> "API_V2>STORE_V1|STORE_V1";
            default -> throw new AssertionError("Unknown mode");
        };

        boolean expectFailure = !"batch-ok".equals(mode);
        if (failed != expectFailure || !expected.equals(after)) {
            throw new AssertionError(
                    "Unexpected redefine result: " + after
            );
        }
        System.out.println("CHECK=PASS");
    }
}
~~~

**Detailed Explanation:**

1. **AgentEntry.required()** retrieves the **Instrumentation** reference provided by the JVM at startup. If run without the agent, the program fails clearly instead of pretending redefinition succeeded.
2. **isRedefineClassesSupported()** checks the capability, while **isModifiableClass(...)** confirms each class can be considered for redefinition.
3. **snapshot()** calls **Api.route()** and **Store.value()** before reading the patch, causing both classes to be loaded and reflect version V1.
4. **Files.readAllBytes** reads **two separate .class files**, containing complete compiled bytes of the same FQCN. The code does not use an API to "recompile inside the JVM".
5. **ClassDefinition** pairs each **Class object in the current JVM** with the **corresponding V2 bytes**. The data is kept stable throughout the call.
6. **batch-ok** and **batch-bad** use **one** **redefineClasses(apiDef, storeDef)** call.
7. **split-bad** calls redefine for **Api** first and then redefine for **Store**. The first step can commit before the second step fails.
8. In failure modes, Store receives an array that **is not a valid class file**, so the request responds with failure. That is an **intentional test fixture**; never use invalid arrays in a production agent.
9. **ClassFormatError** and many class format/linkage errors are subclasses of **LinkageError**, which are caught in the example. **ClassNotFoundException** is in the API's throws clause for compatibility, but is not expected to occur; **main throws Exception** keeps the signature simple.
10. The final assertion distinguishes **the expected result of each mode** and prints **CHECK=PASS** only when the result actually matches. If the implementation does not support redefinition, the program fails fast and does not print a fake success transcript.

**Key takeaway:** In **batch-bad** mode, **Api V2 may be inspected/passed to the JVM before Store is rejected**, but because **the same call fails**, Api is not installed from that batch. Conversely, in **split-bad**, the API has no rollback mechanism across two calls, so the final result can be **Api V2 + Store V1**.

### 6.7. Compiling and Packaging on JDK 17

In the project root directory, using a **POSIX shell** (Linux/macOS or an equivalent bash environment):

~~~bash
mkdir -p build/agent build/base build/patch

# Compile the agent first, package JAR with Premain-Class.
javac --release 17 -d build/agent src/agent/demo/AgentEntry.java
jar cfm redefine-agent.jar agent.mf \
    -C build/agent demo/AgentEntry.class

# Compile V1 application, referencing AgentEntry from the JAR.
javac --release 17 -cp redefine-agent.jar \
    -d build/base \
    src/base/demo/Api.java \
    src/base/demo/Store.java \
    src/base/demo/Main.java

# Compile the two V2 classes independently into the patch directory.
javac --release 17 -d build/patch \
    src/patch/demo/Api.java \
    src/patch/demo/Store.java
~~~

On Windows PowerShell/cmd, use the same **javac/jar** commands, but write each command on **a single line** instead of using line-continuation backslashes. Create directories using syntax appropriate for your OS.

Result:

~~~text
build/
  agent/
    demo/AgentEntry.class
  base/
    demo/Api.class
    demo/Store.class
    demo/Main.class
  patch/
    demo/Api.class
    demo/Store.class
redefine-agent.jar
~~~

Note: **build/base** must contain only V1, and **build/patch** must contain only V2. Never write V2 into build/base during testing, because the example needs the JVM to start from V1 to verify the result. Inspect the JAR:

~~~bash
jar tf redefine-agent.jar
~~~

It must contain **META-INF/MANIFEST.MF** and **demo/AgentEntry.class**.

### 6.8. Running a Valid Batch: batch-ok

~~~bash
java -javaagent:redefine-agent.jar \
    -cp "build/base:redefine-agent.jar" \
    demo.Main batch-ok build/patch
~~~

In bash, **:** separates classpath entries. On Windows, use **;** between paths and run the command on one line:

~~~text
java -javaagent:redefine-agent.jar -cp "build/base;redefine-agent.jar" demo.Main batch-ok build/patch
~~~

On a standard HotSpot JDK 17 with class redefinition capability, the output is:

~~~text
BEFORE=API_V1>STORE_V1|STORE_V1
REDEFINE_OK
AFTER=API_V2>STORE_V2|STORE_V2
CHECK=PASS
~~~

**Reading the result:** before the batch, Api V1 calls Store V1; after redefineClasses returns normally, **new** calls to Api use the V2 body and Store uses the V2 body. The result is the exact requested version pair. Reading both **Api.route()** and **Store.value()** in snapshot also tests both the dependent call path and the direct call path.

### 6.9. Batch with One Invalid Class: batch-bad

Run in a **new JVM**, do not reuse the process from batch-ok:

~~~bash
java -javaagent:redefine-agent.jar \
    -cp "build/base:redefine-agent.jar" \
    demo.Main batch-bad build/patch
~~~

Output:

~~~text
BEFORE=API_V1>STORE_V1|STORE_V1
REDEFINE_FAILED
AFTER=API_V1>STORE_V1|STORE_V1
CHECK=PASS
~~~

**Store** is requested to be redefined with a 4-byte array lacking class file structure. The JVM rejects **the request containing both Api and Store**; by contract, **no class is redefined when the call throws an exception**. Even though Api has valid V2 bytes, the JVM keeps both definitions from before the failed call.

Do not rely on assuming whether the JVM checks Store first or Api first; the Javadoc does not require you to infer ordering from processing logs. The primary evidence is that **the call threw an error** and **all subsequent behavior remains on the old version**.

### 6.10. Two Separate Calls: split-bad

~~~bash
java -javaagent:redefine-agent.jar \
    -cp "build/base:redefine-agent.jar" \
    demo.Main split-bad build/patch
~~~

Output:

~~~text
BEFORE=API_V1>STORE_V1|STORE_V1
REDEFINE_FAILED
AFTER=API_V2>STORE_V1|STORE_V1
CHECK=PASS
~~~

This is an error-prone situation in multi-class update systems: the first call **redefineClasses(apiDef)** completes successfully. The second call **redefineClasses(storeDef)** fails. The two calls have two different atomic boundaries; the JVM **does not roll back Api**.

Because Api V2 still calls **Store.value()** via the old descriptor, the application continues running, but the output shows **an out-of-sync version pair**. In a real business system, that state can corrupt message structures, metrics, tracing context, or processing rules.

### 6.11. Checking On-Disk vs. In-JVM Versions

~~~bash
javap -c -p -classpath build/base demo.Api
javap -c -p -classpath build/patch demo.Api
~~~

The file **build/base/demo/Api.class** still represents V1; the file **build/patch/demo/Api.class** represents V2. Redefinition does not modify these two files on disk, but installs the method definition **in the running JVM**. Therefore, running **javap on the base file after batch-ok** still shows the old version and is not a sign that the agent failed.

## 7. Atomic Guarantee: What Exactly Is Guaranteed?

The Java 17 Instrumentation API states: if **redefineClasses(...) throws an exception, no classes have been redefined** by that call. It is essential to understand the exact subject of this guarantee.

### 7.1. What Is Guaranteed

- The **ClassDefinition** entries in **a single call** are processed as a set to support interrelated changes.
- If an error occurs and **the call throws an exception**, no class definition belonging to the set was installed **by that failed call**.
- Definitions installed in **previous successful calls** are not rolled back just because a later call fails.
- If the bytes are valid, capabilities are sufficient, and the call completes normally, the JVM has accepted the set's redefinition operation (but business semantics must still be verified).

### 7.2. What Is NOT Guaranteed by the JVM as a Business Transaction

| Component | Does a failed redefine batch automatically revert it? |
| --- | --- |
| **Class definitions of the failing request itself** | **Does not install** those new definitions |
| **Logs/counters already written by a transformer** | **No** |
| **I/O, network requests, threads created by callbacks** | **No** |
| **Static/in-memory configuration of the Java agent** | **No** |
| **Previously succeeded redefine batches** | **No** |
| **Other classes loaded/transformed independently** | **Outside this request's guarantee boundary** |
| **Static field values and object state** | **Not reset** |
| **Active stack frames currently executing the old method** | **Not switched instantaneously to new bytecode** |
| **Business requests already partway through a call path before replacement** | **Not re-run or rolled back** |

Therefore, the term **atomic** here must be understood as **all-or-none for class definitions in a failed call**, **not** an ACID transaction for the entire JVM.

### 7.3. During Transition, Threads Can Still Run Old Code

According to the API, if a method has **active stack frames**, those frames continue executing the old method's bytecode, while **new invokes** use the new definition. For example, request R entered Api V1 and then the JVM updates both Api and Store to V2; when R calls Store from Api V1 after the update, it may hit Store V2 if the call occurs after the update point.

Thus **all-or-none at the class-definition level** does not mean **every business request always sees the same version snapshot**. If the problem requires request-level consistency, you must add **quiescence, traffic draining, version pinning, generation-based routing, or application-side coordination**. A batch redefine cannot replace application transaction logic.

### 7.4. Static Initializers and Instances Do Not Re-run

Redefinition **does not re-run the class initializer <clinit>**, does not reset static fields, and does not recreate existing instances. Replacing a method that reads a static field does not automatically change the field's value. If the application uses caches, singletons, or state machines, you must determine whether V2 code is compatible with existing V1 state.

For example:

~~~java
// Source-level illustration.
static final java.util.Map<String, String> CACHE =
        new java.util.HashMap<>();

static String read() {
    return CACHE.get("key");
}
~~~

If you replace the body of **read()** while still using the existing CACHE, the cache entries are not automatically cleared. Do not design a new version assuming all static state has been reinitialized.

## 8. Evaluating the Whole Set Result: Not Just Catching Exceptions

A system managing class redefinition needs **two result layers**:

1. **API result:** whether redefineClasses returns normally or throws an exception.
2. **Whole-set functional result:** whether every class in the set has the right behavior, dependency protocol, and integrity after the update.

A call can complete normally even if you supplied class bytes equivalent to the current ones, or even if the new logic carries a business bug. The JVM verifies/links class definitions, not that your algorithm returns the desired business result.

### 8.1. Deployment States to Distinguish

~~~text
PREPARED
   │
   ├── VALIDATION_FAILED    → do not call API
   │
   ▼
REQUESTED
   │
   ├── REDEFINE_FAILED      → no class in the failed batch was installed
   │
   ▼
DEFINITIONS_APPLIED
   │
   ├── BEHAVIOR_MISMATCH    → classes were installed, but whole set is not business-correct
   │
   ▼
WHOLE_SET_VERIFIED
~~~

These labels are **application-defined states**, not a standard JDK enum. In particular, **BEHAVIOR_MISMATCH after a successful redefine** does not mean the JVM will automatically roll back. If rollback is needed, perform a controlled operation after verifying the required bytes and capability.

### 8.2. Verification Checklist for A and B

| Check item | Why is it needed? | Appropriate evidence |
| --- | --- | --- |
| Exact **Class object** | Avoid patching the wrong class loader | FQCN + defining loader/module |
| Exact **version bytes** | Avoid picking the wrong patch file | Hash/build ID of input class files |
| Capability granted | Avoid rejected calls | isRedefineClassesSupported() |
| All classes modifiable | Block invalid requests early | isModifiableClass on each Class |
| **Single** call contains whole set | Properly scoped all-or-none boundary | Request ID and ClassDefinition list |
| API completes normally | JVM accepted the request | No exception thrown |
| A V2 is correct | Not just seeing B change | Direct invocation of A |
| B V2 is correct | Not just seeing A change | Direct invocation of B |
| **A→B** is correct | Verify dependency and protocol version | Invocation across both classes |
| Original exceptions/returns intact | Do not break semantics | Regression tests |
| Active frames/state managed | Ensure request consistency when needed | Version routing/quiescence checks |

When a class has no API to read its version, define a **valid probe** or verify representative behavior. Do not rely solely on a "TRANSFORMED A" log line from a callback to conclude the whole set was installed.

### 8.3. Why Test A Individually, B Individually, and the A→B Dependency Path?

If you only test **Api.route()**, the output might look right by coincidence even if Store was not updated; for example, Api V2 might have a hard-coded result or the test branch might not reach Store. Conversely, testing **Store.value()** as correct does not prove Api is using Store under the new protocol.

At minimum, you need:

- **A-specific behavior**: Is Api using the new rules/logic?
- **B-specific behavior**: Is Store using the new rules/logic?
- **Cross-class behavior**: Does Api calling Store produce compatible output/protocol?
- **Failure-path behavior**: Do both classes retain old logic when the batch fails together?

The **snapshot()** example in this lesson reads both Api.route() and Store.value() so learners can directly see the mixed state in split-bad.

## 9. Role of ClassFileTransformer During redefineClasses

Distinguish **the ClassDefinition bytes provided by the caller** from **the final bytes installed by the JVM**. If registered ClassFileTransformers exist, they can participate in processing **the redefine event** according to the contract. Thus, the classfileBuffer passing through transformers can be transformed further, and the final class bytes may differ from the patch bytes read from file.

~~~text
ClassDefinition(Api.class, patchBytesApi)
    │
    ▼
JVM runs ClassFileTransformers applicable to redefine
    │
    ▼
final bytes of Api

ClassDefinition(Store.class, patchBytesStore)
    │
    ▼
JVM runs ClassFileTransformers applicable to redefine
    │
    ▼
final bytes of Store

               │
               ▼
       verify / install whole set
~~~

Semantics:

- **Returning null** from a transformer means that transformer provides no modification; it does not discard bytes produced by an earlier transformer.
- **Returning a new byte[]** provides replacement data for the next step; it is not itself proof that the class was installed.
- If a transformer **throws an exception**, the JVM may continue to other transformers; do not use throwing inside a callback as a primary protocol to force redefine to fail.
- If the final bytes of **any class** violate class format/schema, the redefineClasses call may throw an error; **the all-or-none guarantee still applies to the entire batch**.
- A transformer can also have **side effects** before the API detects an error in another class. Those side effects **are not rolled back by the JVM**.

### 9.1. Do Not Confuse redefine with retransform

**retransformClasses(A,B)** starts from base class bytes reconstructed by the JVM and applies transformations under retransformation rules. Meanwhile, **redefineClasses(defA,defB)** starts from **class file bytes actively supplied by the caller**, and then applies relevant transformers.

Both can process a set of multiple classes and guarantee that if the call throws an exception, no class in the set is installed, but they **differ in byte source and capability**. According to the API, if the goal is "replace a class definition with a class file freshly compiled from source", **redefineClasses** fits; if you want to re-run bytecode instrumentation on already loaded classes, **retransformClasses** is usually more appropriate.

## 10. Error Classification and Response Strategy

| Error | Common condition | How to handle |
| --- | --- | --- |
| **UnmodifiableClassException** | A Class in the set is not modifiable | Preflight each Class, adjust target set |
| **UnsupportedOperationException** | Missing capability or unsupported schema change | Check manifest/JVM, diff fields/methods/hierarchy |
| **ClassFormatError** | Byte[] is not a valid class file | Check magic, class file parser, transform pipeline |
| **NoClassDefFoundError** | Internal name in bytes does not match target Class | Check binary/internal class name and packaging |
| **UnsupportedClassVersionError** | Bytecode target version higher than JVM allows | Use appropriate javac --release and check major version |
| **ClassCircularityError** | Definition introduces an invalid class dependency cycle | Inspect hierarchy/dependencies |
| **LinkageError** | Related linkage/verification failure | Inspect cause, JVM logs, loader/module |
| **NullPointerException** | ClassDefinition array or element is null | Validate inputs, never pass null |
| **ClassNotFoundException** in signature | API compatibility legacy; Javadoc says cannot be thrown | Know the signature, do not assume it is a common runtime error |
| API succeeds but behavior is wrong | Patch has a logic bug or probe is wrong | Test all classes, dependency paths, and exception paths |

**Do not report partial success for a redefineClasses call that threw an exception.** Callbacks may have processed bytes, but that is not a definition installation result. If you observe partial state after a failure, check whether the system sent **separate calls earlier**, whether another agent is modifying classes, or whether you are observing old active frames/state.

### 10.1. Diagnostic: Isolating the Failing Class Without Breaking the Atomic Boundary

When a batch of 30 classes is rejected, it is tempting to binary-search: send the first half and then the second half. **Warning:** if you try that on the production JVM itself, the first half might **install successfully** and create a mixed state.

Safer approach:

1. **Offline pre-validation** of each class file for format/schema against the original.
2. Run the batch in a **production-like test JVM**, with the same JDK/agent/classloader, to isolate the error.
3. If you must test splitting the set, do so only in a test environment or design an update plan with true rollback.
4. In production, preserve the defined batch boundary, fix the bad bytes, and retry the complete set when safe.
5. Record hashes, build IDs, classloader identities, and exception stack traces for correlation.

A redefine call with an **empty array** is allowed by the Javadoc and does nothing. Do not log "all deployed" if you actually only sent an empty array.

## 11. Rollback, Retry, and Version Control

### 11.1. A Rejected Batch Needs No Rollback of Its Own Class Definitions

If **redefineClasses(A2, B2)** throws an exception, the class definitions from before the call remain intact. However, if callbacks/agents mutated variables, incremented counters, or emitted events to external systems, those side effects are not automatically reverted. You can record **FAILED** and fix the root cause before retrying.

### 11.2. Batch Succeeds but Post-Deployment Tests Fail

This is a different scenario: the API installed A2 and B2, and then a business regression test fails. The JVM **does not automatically roll back because your assertion failed**. You need **valid V1 class bytes** and must send a new redefine call containing **both A and B** to return to the old version, then re-verify.

~~~java
// Pseudocode, old bytes already verified, not a standalone file.
inst.redefineClasses(
    new ClassDefinition(Api.class, originalApiBytes),
    new ClassDefinition(Store.class, originalStoreBytes)
);
~~~

The rollback itself is still subject to capability/schema limits and any registered transformers. If a transformer callback adds advice, the final bytes after rollback may differ from the old bytes on disk. For critical systems, test the **rollback path** as early as staging—do not wait for a production failure.

### 11.3. Retries Need Generation Tracking and Idempotency

If the agent receives multiple requests close together:

~~~text
Request #101: change A,B to V2
Request #102: change A,B to V3
Request #101: late retry
~~~

without coordination, a late retry of #101 could overwrite V3 with V2 even though both requests are accepted by the JVM. Use an **operation ID, expected generation**, a single coordination point with an appropriate lock/queue, and state checks before sending. The JVM API does not manage application versions for you.

**ClassDefinition does not copy byte[]**, so if a producer/agent keeps a mutable buffer and another thread writes to it, hard-to-reproduce bugs can occur. Prepare immutable bytes per operation, use hashes/content-addressed artifacts where appropriate, and never share a mutable array across requests.

### 11.4. When Should You Restart Instead of Redefining?

If a patch requires changing the class schema, changing many dependencies beyond your control, changing object layout/state, or requiring all requests to see a new protocol immediately even with active frames, **a rolling restart, classloader-based versioning, or another application upgrade mechanism** is usually more suitable. Do not force redefineClasses to do a job the JVM does not guarantee.

## 12. Safe Operations Plan for a Dependent Class Set

### 12.1. PREPARE Phase

1. Identify the set **A, B, ...** based on method invocation/ABI relationships and business protocol.
2. Obtain the exact **target Class<?>** in the current JVM; verify loader/module.
3. Read/compile **all new class bytes** from the same build version; do not mix files from two artifact versions.
4. Compare old/new schemas: method descriptors, fields, hierarchy, modifiers, and class file version.
5. Check **isRedefineClassesSupported()** and **isModifiableClass**.
6. Verify/prepare runtime helpers and module access needed by the new body.
7. Plan the **per-class** and **cross-class** tests to run after the update.
8. Save bytes of the previous version (if rollback may be needed), hashes, and operation ID.

### 12.2. APPLY Phase

1. Avoid multiple controllers independently redefining the same Class objects in parallel if logical version consistency is required.
2. Freeze the target list and new bytes for the operation.
3. Create **one ClassDefinition per Class**.
4. Call **one redefineClasses(defA, defB, ...)** for the dependent set.
5. Report **DEFINITIONS_APPLIED** only when the call completes normally.
6. If the call throws an error, report **REDEFINE_FAILED** and **none installed by this call**; preserve the exact error type/cause.

### 12.3. VERIFY Phase

1. Run new invocations on the exact class/loader to check each class.
2. Test the A→B dependency path, not just A and B in isolation.
3. Verify returns, exception paths, concurrency, and side effects within the business scope.
4. Confirm the code generation switchover timing fits in-flight request states.
5. Mark **WHOLE_SET_VERIFIED** only after the set passes all conditions.
6. If a logic error occurs after API success, handle it via the rollback/feature-disable/restart runbook; **do not log it as "JVM transaction rolled back"**.

~~~text
PREPARE → VALIDATE → APPLY → VERIFY → ACTIVE
   │          │        │        │
   │          │        │        └── business error:
   │          │        │            requires separate remediation action
   │          │        └── API throw:
   │          │             none installed by this call
   │          └── pre-API error: do not call redefine
   └── identify class identity and artifact version
~~~

## 13. Common Misconceptions

### 13.1. "Putting two classes into ClassDefinition[] means the JVM will create new Classes"

False. Redefinition targets **already loaded Class objects**. It updates the allowed parts of the definition, not creating new runtime types to replace old ones. If you need a completely new type or new layout, use an appropriate class loading/deployment strategy.

### 13.2. "If one class fails, the JVM installs the valid ones and skips the failing class"

False for **a single multi-class redefineClasses call that throws an exception**. None of the elements in that call **are redefined**. If you observe a mixed state, check earlier separate calls that succeeded or activities outside the batch boundary.

### 13.3. "Caught an exception and saw an Api V2 log, so Api was installed"

Not necessarily. Callback logs, byte reading, and ClassDefinition creation can complete **before the JVM decides the batch failed**. Concluding that definitions were installed must be based on the API outcome and runtime probes.

### 13.4. "If Class A and B are installed together, all requests use the new version synchronously"

Not quite. **Active stack frames** can continue running old code, and object/static state persists. Atomicity of class definitions is not a full-request transaction. If consistency across a single request is needed, add an upgrade protocol at the application layer.

### 13.5. "Just changing Store's method body keeps Api automatically compatible"

Not guaranteed. Two classes can have a **logical protocol** change even when the binary descriptor does not change. You must test the **observable interface** between them.

### 13.6. "Having Can-Retransform-Classes is enough to redefine"

No. They are two separate capabilities; check **Can-Redefine-Classes** and **isRedefineClassesSupported()** for the redefine API.

### 13.7. "A batch succeeded but a later test failed, so catching the exception rolls it back"

No. A Java exception in a test does not revert definitions. You need a reverse redefine operation or another deployment mechanism.

### 13.8. "Keeping V1 class files on disk means it is rolled back"

No. The JVM may still be using the V2 definitions installed in memory. To change the runtime definition, perform the appropriate operation in the JVM, or restart according to deployment policy.

## 14. Required Test Matrix

| Test | Data | Expectation |
| --- | --- | --- |
| Baseline | V1 Api and Store | API_V1>STORE_V1 |
| Valid two-class batch | V2 Api and Store in one call | Both are V2, Api→Store path is correct |
| Batch with invalid Store bytes | Valid Api V2, bad Store | Call throws error; both stay pre-batch |
| Two independent calls, Store fails | Api V2 commits first | Mixed state Api V2 + Store V1; no automatic rollback |
| Non-modifiable class | Add int[].class | Preflight rejects or API fails; no commit from failed batch |
| Missing capability | Manifest does not enable redefine | Fail fast, do not log success |
| Null ClassDefinition | Array contains null | NullPointerException, nothing installed |
| Empty definitions array | redefineClasses() | Valid, no-op |
| Bytecode with wrong class name | ClassDefinition(A.class, bytes B) | Rejected; no class installed from failed batch |
| Bytecode with wrong version | Compiled for higher JDK than target | Rejected |
| Class schema change | Add field/method in patch | Disallowed by default JVM |
| Another ClassFileTransformer present | Output modified further | Verify final bytes and actual behavior |
| Two classloaders with same FQCN | Two distinct Class objects | Only the target Class in the set is modified |
| Old active request | Thread inside V1 method | Can continue V1; new invocations use V2 |
| Controlled rollback | Save old V1 bytes, apply whole set | Both return to V1 behavior after valid rollback request |
| Concurrency/retry | Two conflicting version operations | Coordinator prevents old version from overwriting new version |

### 14.1. Minimum Assertion Set

For this lesson's example, **do not assert only a single final string** if you want to prove the whole set at production level. Verify:

- Before: both **Api.route** and **Store.value** are V1.
- After batch-ok: **Api.route** contains the V2 format and the actual **Store.value** result is V2.
- After batch-bad: both still return V1; no class was installed from the failed call.
- After split-bad: Api V2/Store V1 serves as the control demonstrating the risk of splitting batches.
- Timing of normal API return vs. business probe timing.
- Class format/linkage errors are reported separately, not swallowed in callbacks.
- With real classloaders/modules: Class objects belong to the right loader and patch bytes belong to the right build.

## 15. Pre-Deployment Checklist

- I have identified the **dependent class set** and the version boundary requiring consistency.
- **Can-Redefine-Classes** is declared in the manifest and the JVM reports support.
- All target classes are loaded, belong to the right defining loader/module, and have **isModifiableClass=true**.
- New class files are compiled from the same artifact version, have the exact internal name, and match the target JDK.
- Changes keep the schema within JVM-supported limits, without arbitrarily adding/removing fields/methods.
- ClassDefinition pairs the exact Class and byte[]; **byte[] is not mutated after preparation**.
- Other transformers that may participate in redefinition have been accounted for.
- I use **a single redefineClasses(...)** for classes that must change together, without silently splitting into multiple requests.
- When the API throws an error, I report **none installed by this call** and preserve previous results.
- When the API returns normally, I run **per-class and cross-class dependency checks** before reporting whole-set success.
- I understand the JVM does not reset instance/static fields and does not automatically switch old active frames to new bytecode.
- A rollback/retry runbook and concurrency limits are in place if requests modify the same classes.
- I have tested **batch-ok**, **batch-bad**, and **split-bad** on the target JDK/framework.

## 16. Official References

- [Java SE 17 — Instrumentation.redefineClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineClasses(java.lang.instrument.ClassDefinition...)): class-set contract, exceptions, active frames, and no classes redefined when the call fails.
- [Java SE 17 — ClassDefinition](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): pairing Class with class bytes; constructor does not copy byte[].
- [Java SE 17 — isRedefineClassesSupported and isModifiableClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): capability and modifiable checks.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformers that can participate when a class is redefined.
- [Java SE 17 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): startup agent, premain, and Can-Redefine-Classes manifest attribute.
- [JVM TI Specification 17 — RedefineClasses](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html): class definition limits and class modification capabilities.
- [Java Virtual Machine Specification 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): class file structure and bytecode constraints.

**Conclusion:** Use **a single redefineClasses request containing all dependent classes** when you need an all-or-none boundary at the **class definitions** level. When that request throws an exception, **no class in the set has been redefined by that request**. When the request succeeds, you must still **evaluate the whole set via new invocations**, checking class identity, cross-class semantics, active frames, and application state; committing definitions does not by itself guarantee business success.