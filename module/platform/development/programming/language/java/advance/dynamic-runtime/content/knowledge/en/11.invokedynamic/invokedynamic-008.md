# 11.8 BootstrapMethodError, Linkage Errors, and Reuse Behavior

## 1. Lesson Objectives and Scope

In the Java Virtual Machine, `invokedynamic` is a bytecode instruction whose **target is determined at linkage time** through a **bootstrap method (BSM)**. The BSM is not business logic that runs again on every call. It is used to create a `java.lang.invoke.CallSite` for a specific `invokedynamic` site; after successful linkage, subsequent executions of that instruction go to the call site's target.

This lesson answers four easily confused questions:

1. When does the JVM throw **`BootstrapMethodError`**, and when do we encounter a different `Error`/`LinkageError`?
2. What happens if the BSM throws an exception, returns `null`, or returns a `CallSite` with a target of the wrong `MethodType`?
3. **Does calling the exact same `invokedynamic` site that failed to link run the BSM again?** Can modifying a configuration flag or Java state rescue that site?
4. Do two instructions referencing **the same `CONSTANT_InvokeDynamic` entry** in the constant pool share linkage state? What if the class is reloaded by a different class loader?

We will verify this with a Java 17+ program that **generates a minimal class file containing `invokedynamic` bytecode on its own**, without needing ASM/Javassist libraries or `--add-exports`. The experiment code distinguishes between **linkage failure**, **linkage success**, and **exceptions occurring in the target after linkage**.

> **Key takeaway:** On **sequential** uses, if the resolution of an `invokedynamic` instruction has failed, subsequent uses of **that same instruction** continue to report an error and **do not retry calling the BSM**. Linkage state belongs to each **lexical occurrence of the instruction**, not just based on the method name or constant pool entry index. For **concurrent** initial linkage attempts, the BSM may run multiple times in parallel; the JVM will choose one result to publish.

## 2. The Linkage Mechanism of `invokedynamic`

### 2.1. From Bytecode to Target

An `invokedynamic` instruction in a class file links to a `CONSTANT_InvokeDynamic` entry, which specifies:

- **Bootstrap method** via the `BootstrapMethods` attribute and a `CONSTANT_MethodHandle`.
- **Dynamic invocation name** (`String name`) and **method descriptor** (`MethodType type`).
- **Static bootstrap arguments** if any, such as strings, numbers, method types, method handles, or suitable dynamically-computed constants.

Conceptual flow:

```text
First execution of a lexical invokedynamic instruction
    |
    v
Resolve bootstrap MethodHandle + name, MethodType, static args
    |
    v
Invoke BSM with (Lookup caller, String name, MethodType type, ...)
    |
    v
Validate result:
  - must be a non-null CallSite
  - callSite.type() must match the exact MethodType required by the instruction
    |
    +-- invalid / BSM error --> linkage fails --> report error
    |
    +-- valid --> bind CallSite to instruction --> invoke target
                                               |
                            Subsequent calls reuse the existing linkage
```

A BSM typically has the form:

```java
public static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String name,
        MethodType type) throws Throwable {
    // Create a CallSite of the right type.
}
```

This is only an **illustrative signature**, not a standalone runnable program. Some bootstrap methods take additional static arguments or have signatures permitted by Method Handle conversions.

`caller` is not a business object: it is the `Lookup` bound to the class containing the instruction. `name` and `type` are taken from the static description of the instruction in the class file. For example, a site called with no arguments returning `String` will have `type == MethodType.methodType(String.class)`, displayed as `()String`.

### 2.2. `CallSite` and `target` Must Match Types

A valid result can be a `ConstantCallSite`, `MutableCallSite`, or `VolatileCallSite`, as long as the call site's type **equals the exact** method descriptor required by the instruction.

Valid example for `()String`:

```java
// Snippet inside bootstrap, assuming the type variable is ()String.
MethodHandle target =
        MethodHandles.constant(String.class, "linked");
return new ConstantCallSite(target.asType(type));
```

`MethodHandles.constant(String.class,"linked")` is a MethodHandle with no arguments returning `String`. `ConstantCallSite` fixes the target corresponding to the instruction.

Invalid example:

```java
// Snippet: target has type ()int, but invokedynamic requires ()String.
return new ConstantCallSite(
        MethodHandles.constant(int.class, 123));
```

`ConstantCallSite` can be validly constructed for `()int`; however, **the JVM checks it against the `()String` descriptor of `invokedynamic`**. Because they do not match, linkage fails with `BootstrapMethodError`. This is a **bootstrap result** error, and no business invocation has been executed yet.

### 2.3. Linkage and Execution Are Two Separate Phases

Keep separate:

- **Linkage:** resolving symbolic references, invoking the bootstrap, checking/setting the `CallSite`.
- **Invocation:** running the `CallSite` target when the instruction is executed after being linked.

If the target later throws `IllegalStateException`, that error belongs to **target logic**. It does not cause the linkage state to become failed or the BSM to automatically run again. A target can throw an exception a thousand times after being successfully linked, whereas the BSM only needs to create the site for that instruction.

Similarly, changing the target of a `MutableCallSite` via `setTarget` is **changing the behavior of an already-linked site**, not re-linking the instruction from scratch.

## 3. What Is `BootstrapMethodError`?

`java.lang.BootstrapMethodError` is a subclass of `java.lang.LinkageError`, and `LinkageError` is a subclass of `java.lang.Error`:

```text
Throwable
  └── Error
       └── LinkageError
            └── BootstrapMethodError
```

The core meaning of `BootstrapMethodError`: the bootstrap process for `invokedynamic` or a dynamic constant could not complete as required, for instance because resolving the BSM/arguments failed or the bootstrap did not return a result of the right type.

**Do not confuse `BootstrapMethodError` with exceptions thrown by the target business method.** It relates to the process of constructing/resolving the call site; the target may have never run.

### 3.1. Common Causes

| Situation | Phase | Notable behavior / error form |
| --- | --- | --- |
| BSM throws `IllegalStateException` or another checked/runtime exception **not of type Error** | During BSM execution | JVM creates `BootstrapMethodError` and attaches the original exception as `cause` |
| BSM returns `null` instead of `CallSite` | Checking BSM result | `BootstrapMethodError` |
| BSM returns `CallSite` whose `type()` differs from the `invokedynamic` descriptor | Type checking | `BootstrapMethodError` |
| Cannot resolve a bootstrap method handle or its dependencies | Before/during BSM resolution | May be an appropriate `LinkageError`; do not assume all errors are of the same type |
| BSM directly throws an `Error`, such as `AssertionError`/`LinkageError` | Inside BSM | According to JVMS rules, that `Error` is used as the resolution error, not necessarily wrapped in `BootstrapMethodError` |
| Target is successfully linked, but throws `IllegalStateException` when running | **After linkage** | Caller receives the target's error; not a `BootstrapMethodError` from the BSM |
| Malformed bytecode or verification failure | Class loading/verification | May be `ClassFormatError` or `VerifyError`, not evidence that the BSM ran |

This table presents **categories of causes**, not a claim that every erroneous combination will necessarily produce the exact same subclass. When diagnosing, observe the **actual error**, `getCause()`, stack trace, and failure point.

### 3.2. Why Are Checked/Runtime Exceptions Usually Wrapped?

Suppose the BSM throws:

```java
throw new IllegalStateException("not ready");
```

`IllegalStateException` is a `RuntimeException`, **not** an `Error`. JVMS rules turn this bootstrap failure into `BootstrapMethodError`, with `cause` being `IllegalStateException`.

If the BSM directly throws:

```java
throw new AssertionError("broken bootstrap");
```

then this is already a subclass of `Error`; the JVM does not need to wrap it into `BootstrapMethodError` under the same rule. Therefore, the statement **"every error in a BSM becomes a BootstrapMethodError"** is inaccurate.

### 3.3. When Is It Not a Linkage Error?

If a valid `CallSite` points to the target:

```java
public static String alwaysFails() {
    throw new IllegalStateException("target failed");
}
```

and `invokedynamic` is successfully linked, then the exception thrown when running the target remains `IllegalStateException`. Subsequent calls can enter the target again. **An invocation error after linkage does not cause the JVM to mark the instruction as a resolution error**.

The full example below uses a separate site named `targetThrows` to verify this difference using the execution counts of the bootstrap and the target.

## 4. Reuse Behavior: Exact Scope of Caching

### 4.1. After a Successful Link

For **the same lexical `invokedynamic` instruction**:

1. First time execution is needed: the JVM performs linkage.
2. BSM returns a valid `CallSite`; the JVM binds that call site to the instruction.
3. Subsequent executions: the instruction uses **the existing linkage**; the BSM is not called again.
4. For `ConstantCallSite`, the target stays fixed. For `MutableCallSite`/`VolatileCallSite`, the target can be updated according to the API contract, but that **does not re-run the bootstrap**.

Changing a Java variable `ready` after the site has successfully linked does not make the JVM pick a different BSM. Only target logic or the target-updating mechanism of a mutable/volatile call site can change execution behavior by design.

### 4.2. After a Failed Link

If the first attempt of an `invokedynamic` instruction ends in a linkage error:

1. The JVM marks **the resolution result as failed for that instruction**.
2. Subsequent executions of **that same instruction** continue to fail with the recorded resolution error.
3. **The BSM is not retried** simply because the caller caught (`catch`) the exception.
4. Fixing a `ready` flag or updating configuration after the failure **cannot rescue the failed site** in the already-loaded class.

**Do not write a retry loop around `BootstrapMethodError` expecting it to re-invoke the BSM.** It is not a transient I/O retry API. If you want a recovery mechanism, design a CallSite upfront that successfully links to a target capable of fallback/retry, or load a **new class in a new loader** when appropriate.

### 4.3. Caching per Instruction, Not Just per Constant Pool Entry

Two different `invokedynamic` instructions in a class file **can reference the same `CONSTANT_InvokeDynamic`**. The JVM still resolves each **lexical occurrence** separately:

```text
IndyGenerated.fire()  : invokedynamic #19  ---> first time BSM fails
IndyGenerated.other() : invokedynamic #19  ---> first time BSM succeeds
                                             (same #19 entry, different opcode site)
```

The failure of `fire()` **does not cause `other()` to be marked failed** just because both instructions point to `#19`. In the experiment, `fire()` fails when `ready=false`, then `ready=true` and `other()` links successfully. This does not contradict the caching rule: they are **two instructions**, so they have two independent linkage states.

### 4.4. Reloading the Class with a Different Class Loader

In the JVM, class identity is tied to **class name + defining class loader**. The same `IndyGenerated.class` bytes defined by a different `ClassLoader` create **a different class**, carrying its own instructions/runtime linkage state.

The experiment will use:

```java
Class<?> c1 = new Definer().create(bytes);
Class<?> c2 = new Definer().create(bytes);
```

This is a **snippet** of the complete program, not standalone runnable code. Two `new Definer()` calls create two different defining loaders. `c1` and `c2` have the same binary name but **do not share class identity**, so the call site in `c2` can link anew. This is not a "successful retry on the old site" but a **new site of a new class**.

### 4.5. Warning About Concurrency

The rule "bootstrap runs once" must be understood in the context of **sequential uses after linkage has completed**. The JVMS allows multiple threads to simultaneously attempt linking an unresolved site, so **the BSM can be invoked concurrently multiple times** for the same symbolic reference. The JVM chooses one linkage result to publish; the other concurrent results are discarded.

Therefore:

- A BSM with shared side effects must be designed to be thread-safe.
- Do not prove correctness by assuming `bootstrapRuns == 1` in all multithreaded stress tests.
- The experiment below **intentionally runs sequentially**, so the counts are deterministic and the cause-and-effect relationship is clear.
- For a site whose resolution has failed, subsequent calls afterward do not trigger new retries just because multiple threads participated in linkage earlier.

## 5. Java 17+ Experiment: Generating Real `invokedynamic` Without External Libraries

### 5.1. Why Not Just Write a Lambda in Java Source?

`javac` typically emits `invokedynamic` for lambdas/method references and may do so for string concatenation depending on the version/compilation mode. However, the bootstraps generated by the compiler in those examples are `LambdaMetafactory` or `StringConcatFactory`, validly configured by the compiler. It is difficult to deliberately make those bootstraps **throw an error at the exact moment** without relying on classfile transformation.

To accurately verify "BSM fails the first time and then is retried," we will **write a minimal JVM class file ourselves** using `DataOutputStream`. It has four `public static` methods:

| Method in generated class | Constant pool entry | Bootstrap behavior | Purpose |
| --- | --- | --- | --- |
| `fire()` | `#19` | BSM will throw an exception when `ready=false` | Test caching of a failed site |
| `other()` | **`#19`** | BSM succeeds when `ready=true` | Prove same CP entry but different instruction |
| `wrong()` | `#22` | BSM returns `ConstantCallSite` of type `()int` instead of `()String` | Prove type checking at linkage |
| `unstable()` | `#26` | BSM succeeds; target always throws `IllegalStateException` | Distinguish target error from bootstrap error |

All four instructions have descriptor `()Ljava/lang/String;` corresponding to MethodType `()String`. They use **the same bootstrap method handle** in the `BootstrapMethods` attribute, but pass different symbolic names for their respective sites.

### 5.2. Complete Source Code

Save the following content verbatim as **`IndyFailureLab.java`**. The program runs on **JDK 17 or higher**; the generated classfile uses **major version 51** (Java 7), which is the JVM format that supports `invokedynamic`.

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;

public class IndyFailureLab {
    private static int bootstrapRuns;
    private static int targetRuns;
    private static boolean ready;

    public static String throwFromTarget() {
        targetRuns++;
        throw new IllegalStateException("target failed");
    }

    // BSM referenced by MethodHandle from the generated class.
    public static CallSite bootstrap(
            MethodHandles.Lookup lookup, String name, MethodType type)
            throws ReflectiveOperationException {
        bootstrapRuns++;

        if ("badType".equals(name)) {
            // This CallSite has type ()int, differing from ()String required by the site.
            return new ConstantCallSite(
                    MethodHandles.constant(int.class, 123));
        }
        if ("targetThrows".equals(name)) {
            // Links successfully; only when RUNNING the target does it throw an exception.
            return new ConstantCallSite(MethodHandles.lookup().findStatic(
                    IndyFailureLab.class, "throwFromTarget", type));
        }
        if (!ready) throw new IllegalStateException("not ready");

        return new ConstantCallSite(
                MethodHandles.constant(String.class, "linked").asType(type));
    }

    static final class Definer extends ClassLoader {
        Definer() {
            super(IndyFailureLab.class.getClassLoader());
        }

        Class<?> create(byte[] bytes) {
            return defineClass("IndyGenerated", bytes, 0, bytes.length);
        }
    }

    private static void utf8(DataOutputStream out, String value)
            throws IOException {
        out.writeByte(1);
        out.writeUTF(value);
    }

    private static byte[] bytecode() throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);

        out.writeInt(0xCAFEBABE);
        out.writeShort(0);
        out.writeShort(51); // Java 7 class file; readable by JDK 17+.
        out.writeShort(28); // Constant pool: entries #1..#27.

        utf8(out, "IndyGenerated");                // #1
        out.writeByte(7); out.writeShort(1);       // #2 Class
        utf8(out, "java/lang/Object");             // #3
        out.writeByte(7); out.writeShort(3);       // #4 Class
        utf8(out, "Code");                         // #5
        utf8(out, "fire");                         // #6
        utf8(out, "()Ljava/lang/String;");         // #7
        utf8(out, "other");                        // #8
        utf8(out, "BootstrapMethods");             // #9
        utf8(out, "IndyFailureLab");               // #10
        out.writeByte(7); out.writeShort(10);      // #11 Class
        utf8(out, "bootstrap");                    // #12
        utf8(out, "(Ljava/lang/invoke/MethodHandles$Lookup;"
                + "Ljava/lang/String;Ljava/lang/invoke/MethodType;)"
                + "Ljava/lang/invoke/CallSite;");  // #13
        out.writeByte(12);                        // #14 NameAndType
        out.writeShort(12); out.writeShort(13);
        out.writeByte(10);                        // #15 Methodref
        out.writeShort(11); out.writeShort(14);
        out.writeByte(15);                        // #16 MethodHandle
        out.writeByte(6); out.writeShort(15);     // REF_invokeStatic
        utf8(out, "dynamicName");                 // #17
        out.writeByte(12);                        // #18 NameAndType
        out.writeShort(17); out.writeShort(7);
        out.writeByte(18);                        // #19 InvokeDynamic
        out.writeShort(0); out.writeShort(18);    // BootstrapMethods[0]
        utf8(out, "badType");                     // #20
        out.writeByte(12);                        // #21 NameAndType
        out.writeShort(20); out.writeShort(7);
        out.writeByte(18);                        // #22 InvokeDynamic
        out.writeShort(0); out.writeShort(21);    // BootstrapMethods[0]
        utf8(out, "wrong");                       // #23
        utf8(out, "targetThrows");                // #24
        out.writeByte(12);                        // #25 NameAndType
        out.writeShort(24); out.writeShort(7);
        out.writeByte(18);                        // #26 InvokeDynamic
        out.writeShort(0); out.writeShort(25);    // BootstrapMethods[0]
        utf8(out, "unstable");                    // #27

        out.writeShort(0x0021); // ACC_PUBLIC | ACC_SUPER
        out.writeShort(2);      // this_class
        out.writeShort(4);      // superclass java.lang.Object
        out.writeShort(0);      // interfaces_count
        out.writeShort(0);      // fields_count
        out.writeShort(4);      // methods_count

        int[] names = {6, 8, 23, 27};
        int[] indyIndexes = {19, 19, 22, 26};
        for (int i = 0; i < names.length; i++) {
            out.writeShort(0x0009); // ACC_PUBLIC | ACC_STATIC
            out.writeShort(names[i]);
            out.writeShort(7);      // descriptor ()String
            out.writeShort(1);      // one Code attribute
            out.writeShort(5);      // UTF8 "Code"
            out.writeInt(18);       // Code attribute length
            out.writeShort(1);      // max_stack
            out.writeShort(0);      // max_locals
            out.writeInt(6);        // code_length
            out.writeByte(0xba);    // invokedynamic
            out.writeShort(indyIndexes[i]);
            out.writeShort(0);      // two mandated zero bytes
            out.writeByte(0xb0);    // areturn
            out.writeShort(0);      // exception_table_length
            out.writeShort(0);      // nested attributes_count
        }

        out.writeShort(1);   // class attributes_count
        out.writeShort(9);   // "BootstrapMethods"
        out.writeInt(6);
        out.writeShort(1);   // one BSM entry
        out.writeShort(16);  // bootstrap MethodHandle
        out.writeShort(0);   // no static bootstrap arguments
        out.flush();
        return bytes.toByteArray();
    }

    // Reflection wraps exceptions thrown by the target method/bytecode.
    // Unwrap to see the actual BootstrapMethodError/IllegalStateException.
    private static String invoke(Method method) throws Throwable {
        try {
            return (String) method.invoke(null);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = bytecode();
        Files.write(Path.of("IndyGenerated.class"), bytes);

        Class<?> firstClass = new Definer().create(bytes);
        Method fire = firstClass.getMethod("fire");
        Method other = firstClass.getMethod("other");
        Method wrong = firstClass.getMethod("wrong");
        Method unstable = firstClass.getMethod("unstable");

        // Site #1: BSM throws exception because ready=false.
        try {
            invoke(fire);
        } catch (BootstrapMethodError ex) {
            System.out.println("first=" + ex.getClass().getSimpleName());
            System.out.println("cause="
                    + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("calls after first=" + bootstrapRuns);

        // Fix state after failure: DOES NOT cause site #1's BSM to run again.
        ready = true;
        try {
            invoke(fire);
        } catch (BootstrapMethodError ex) {
            System.out.println("retry=" + ex.getClass().getSimpleName());
        }
        System.out.println("calls after retry=" + bootstrapRuns);

        // Site #2: different instruction using the same CP entry #19.
        System.out.println("other=" + invoke(other));
        System.out.println("calls after other=" + bootstrapRuns);

        ready = false;
        System.out.println("other again=" + invoke(other));
        System.out.println("calls after reused success=" + bootstrapRuns);

        // Site #3: BSM returns CallSite with incompatible MethodType.
        try {
            invoke(wrong);
        } catch (BootstrapMethodError ex) {
            System.out.println("wrong type=" + ex.getClass().getSimpleName());
        }
        System.out.println("calls after wrong type=" + bootstrapRuns);
        try {
            invoke(wrong);
        } catch (BootstrapMethodError ex) {
            System.out.println("wrong retry=" + ex.getClass().getSimpleName());
        }
        System.out.println("calls after wrong retry=" + bootstrapRuns);

        // Site #4: linkage succeeds, TARGET throws exception twice.
        for (int i = 1; i <= 2; i++) {
            try {
                invoke(unstable);
            } catch (IllegalStateException ex) {
                System.out.println("target " + i + "="
                        + ex.getClass().getSimpleName());
            }
        }
        System.out.println("calls after target invokes=" + bootstrapRuns);
        System.out.println("target body runs=" + targetRuns);

        // Same bytecode but class defined under a NEW loader.
        ready = true;
        Class<?> freshClass = new Definer().create(bytes);
        System.out.println("fresh=" + invoke(freshClass.getMethod("fire")));
        System.out.println("calls after new class=" + bootstrapRuns);
    }
}
```

### 5.3. Compile and Run

In the directory containing `IndyFailureLab.java`, run:

```bash
javac IndyFailureLab.java
java IndyFailureLab
```

The program will also generate the file `IndyGenerated.class` in the current directory. This file is a **programmatically generated class file**, not a Java source class needing a second compilation. It has no default constructor but has four `public static` methods; the program only accesses those methods via Reflection.

**Verified exact stdout of the program:**

```text
first=BootstrapMethodError
cause=IllegalStateException
calls after first=1
retry=BootstrapMethodError
calls after retry=1
other=linked
calls after other=2
other again=linked
calls after reused success=2
wrong type=BootstrapMethodError
calls after wrong type=3
wrong retry=BootstrapMethodError
calls after wrong retry=3
target 1=IllegalStateException
target 2=IllegalStateException
calls after target invokes=4
target body runs=2
fresh=linked
calls after new class=5
```

This stdout was observed when running **sequentially**, with no competing threads. The counts are based on `bootstrapRuns++` and `targetRuns++`, independent of memory addresses, class loader names, or stack trace contents.

### 5.4. Reading Bytecode to Confirm `invokedynamic` Is Not "Simulated"

After running the program, type:

```bash
javap -v -c IndyGenerated.class
```

In the long output of `javap`, look for `InvokeDynamic`, `BootstrapMethods`, and the `invokedynamic` opcode. The core lines look like:

```text
major version: 51
#19 = InvokeDynamic ... // dynamicName:()Ljava/lang/String;
#22 = InvokeDynamic ... // badType:()Ljava/lang/String;
#26 = InvokeDynamic ... // targetThrows:()Ljava/lang/String;

fire():     invokedynamic #19
other():    invokedynamic #19
wrong():    invokedynamic #22
unstable(): invokedynamic #26
```

The snippet above is an **excerpt of the relevant lines**, not the full `javap` output. The actual dump also includes flags, method descriptors, constant-pool indices, `BootstrapMethods`, and many auxiliary lines. The repetition of **`invokedynamic #19` in two different methods** proves they share a constant-pool entry yet are two independent instructions.

The program actually contains the bytecode `0xba`, which is the opcode of `invokedynamic`, followed by a **2-byte constant pool index** and **2 zero bytes**. `0xb0` is the `areturn` opcode for the `String` reference result. Because the classfile generator is intentionally concise, each method has only one `invokedynamic` followed by `areturn`.

## 6. Reading the Experiment Results by Group

### 6.1. Site `fire()`: Fails Once, Still Errors on Retry

On the first call to `fire()`:

- The BSM receives `name="dynamicName"` and `type=()String`.
- `bootstrapRuns` increments from 0 to 1.
- `ready=false`, so the BSM throws `IllegalStateException("not ready")`.
- The JVM reports `BootstrapMethodError`; `getCause()` of the first error is `IllegalStateException`.

Next, the program sets `ready=true` and calls **the same `fire()`** again:

- Output is still `retry=BootstrapMethodError`.
- `bootstrapRuns` remains **1**.
- There is no opportunity for the BSM to observe the `ready=true` state at that instruction, because resolution has failed and the result is recorded.

This is direct proof for the "reuse attempt" question in the topic. **Catching and calling again is not a BSM retry.**

Note: Do not use `error1 == error2` comparison as the primary test of caching. What needs to be verified is that **the same site continues to receive a resolution error and the BSM is not called again**; the object identity details of exception instances thrown by the JVM across call paths are not a reliable way to describe the linkage mechanism.

### 6.2. Site `other()`: Same CP Entry, Different Instruction

`other()` uses **the same constant pool entry `#19`** as `fire()`, but is located at a different lexical instruction:

- When `ready=true`, the call to `other()` creates a valid `CallSite`, returning `linked`.
- `bootstrapRuns` increases to **2**.
- Resetting `ready=false` and calling `other()` again still returns `linked`; the count stays **2**.

Thus, **`fire()`'s cache does not corrupt `other()`**. After `other()` is successfully linked, external state changes do not cause `other()`'s BSM to run again.

Do not overgeneralize this conclusion to "every call to method `other` links anew": it is **one instruction in the method body**; each time the method is called, **the same instruction** is repeated, so it reuses the already-linked site.

### 6.3. Site `wrong()`: BSM Returns the Right Object Class but Wrong Target Type

`wrong()` has descriptor `()String`, but the BSM (when name is `badType`) returns:

```java
return new ConstantCallSite(MethodHandles.constant(int.class, 123));
```

`ConstantCallSite` has target type `()int`, which does not equal `()String`. The JVM throws `BootstrapMethodError` **immediately when validating the bootstrap result**. At this point, the `()int` target is never invoked and "fails to cast the result" — it **never gets past the linkage phase**.

Output:

```text
wrong type=BootstrapMethodError
calls after wrong type=3
wrong retry=BootstrapMethodError
calls after wrong retry=3
```

Because the BSM returned the wrong `MethodType`, calling `wrong()` again does not make the JVM check again with a new target.

### 6.4. Site `unstable()`: Target Throws Exception, Yet Linkage Remains Intact

The BSM of `unstable()` creates a `ConstantCallSite` pointing to the Java method `throwFromTarget()`, which has **the exact `()String` type**. Every time this method runs, it increments `targetRuns` and then throws `IllegalStateException`.

After two calls:

```text
target 1=IllegalStateException
target 2=IllegalStateException
calls after target invokes=4
target body runs=2
```

Meaning:

- This site's BSM **only needs to run once** in the sequential experiment: the bootstrap count increases from 3 to 4.
- The target is **invoked twice**, so `targetRuns=2`.
- The surfaced error is `IllegalStateException` from the target, **not** `BootstrapMethodError`.
- Successful linkage is preserved after each target exception.

Thus, **retrying a failing target** is completely different from **re-resolving a site whose BSM failed**.

### 6.5. New Class Loader: A New Site Can Link Successfully

At the end of the program, `ready=true` and a new `Definer` defines the class `IndyGenerated` from the same `bytes` array:

```text
fresh=linked
calls after new class=5
```

`freshClass` differs from `firstClass` in class identity despite having the same binary name. The `fire()` instruction in the new class has never been linked, so the BSM can run (incrementing `bootstrapRuns` to 5) and succeed.

**This is not "successfully fixing the old site's error."** The old site in `firstClass` still has its failed resolution history; the new class has its own state.

## 7. Other Linkage Errors to Distinguish

An exception observed when running `invokedynamic` can come from different verification layers:

| Error / situation | Suggested cause | What to investigate |
| --- | --- | --- |
| `BootstrapMethodError` with `cause=IllegalStateException` | BSM threw a non-`Error` exception | BSM code, static config, dependency initialization, `cause`, and stack trace |
| `BootstrapMethodError` when BSM returns `null` or wrong type | Bootstrap result does not satisfy the JVM contract | Is `CallSite` null? Does `callSite.type()` match the exact descriptor? |
| `NoSuchMethodError` or `IllegalAccessError` | May be an error resolving a method/handle/dependency during linkage | Did name/descriptor/class loader/module/access change? |
| `ClassFormatError` / `VerifyError` | Malformed class file or invalid bytecode | Bytecode generator/transformer, stack maps, constant pool, JVM version |
| `ExceptionInInitializerError` | Class initializer of a dependency failed | `<clinit>` and inner cause, whether it is on the bootstrap path |
| `UndeclaredThrowableException` / `InvocationTargetException` | Reflection/proxy wrapper at the caller layer | Unwrap the right layer; do not conclude the BSM failed solely from the wrapper |
| `WrongMethodTypeException` when calling `MethodHandle.invokeExact` | Java call site of a Method Handle has the wrong signature | Distinct from the JVM rejecting a `CallSite` target type during `invokedynamic` linkage |
| `ClassCastException` / `NullPointerException` from target | Execution logic after linkage | Did the BSM return a valid CallSite and is the target running? |

Read **the root error rather than just the outermost class**. In the experiment program, `Method.invoke` wraps errors thrown by the invoked method in `InvocationTargetException`. The helper:

```java
try {
    return (String) method.invoke(null);
} catch (InvocationTargetException ex) {
    throw ex.getCause();
}
```

is to strip the **Reflection wrapper** and observe the exact error at the `invokedynamic`/target layer. It **does not** create or cure `BootstrapMethodError`.

### 7.1. Why Should You Not Always `catch (BootstrapMethodError)` and Continue?

`BootstrapMethodError` is an `Error` related to JVM linkage. If production code catches it and immediately calls the same site again, it will very likely just get the same error state back. Catching it is only reasonable when:

- Writing a reproduction test/experiment.
- Collecting diagnostics and reporting an error with context.
- Having a fallback strategy **that does not rely on the failed instruction**.

Do not swallow the error and return a dummy value that makes the rest of the application think the system initialized validly. A site that failed after a misconfiguration usually requires fixing the cause and then **creating a new JVM/class identity** at the deployment level; sometimes it requires changing how the framework designs its BSM.

### 7.2. Do Not Lump Every `LinkageError` Into a Bootstrap Error

A `NoSuchMethodError` may be due to binary incompatibility: the caller references a method descriptor that no longer exists. An `IllegalAccessError` may come from a visibility/module boundary change. A `VerifyError` may come from a bytecode transformer emitting invalid instructions. Those errors **are not always the result of the BSM having been called**, so diagnosis must distinguish:

1. Was the class loaded/verified?
2. Were the bootstrap method handle and static arguments resolved?
3. Did the BSM actually start running (logs/counters)?
4. Did the BSM throw an exception or return a result?
5. Did the JVM accept the CallSite type?
6. Was the target executing when the exception occurred?

## 8. Why Do These Rules Matter for Lambdas and String Concatenation?

### 8.1. Lambda / Method Reference

On modern Java versions, the compiler may emit `invokedynamic` for a lambda or method reference, typically referencing `java.lang.invoke.LambdaMetafactory` or `altMetafactory` in `BootstrapMethods`.

If the lambda's bootstrap fails to resolve a method handle, an involved class had its binary signature changed, or metafactory conditions are not met, the caller may see a linkage error. **Do not conclude that the lambda body failed while running** before checking whether the error occurred when creating the lambda object (linkage) or when invoking the functional interface method (target execution).

You can inspect the bytecode of a regular Java class:

```bash
javac MyLambdaDemo.java
javap -c -v MyLambdaDemo.class
```

This is a **command template**: `MyLambdaDemo.java` must be source code with a lambda that you create, not a file included with the main experiment. Look for `InvokeDynamic`, `BootstrapMethods`, and owner `LambdaMetafactory` if the compiler uses that strategy.

### 8.2. String Concatenation

`javac` on Java 9+ typically compiles string concatenation using a strategy based on `invokedynamic` and `StringConcatFactory`. This is a compiler/runtime optimization, not a reason for a normal application to handle BSMs itself.

If the system uses a bytecode enhancer, agent, obfuscator, or custom classloader, those components can corrupt the bootstrap arguments or descriptors expected by the compiler. Inspect the bytecode **both before and after the transformer**, because the Java source code may be completely valid while the modified classfile is no longer compatible.

**Do not** infer that every `"a" + value` string across every compiler/JDK generates `invokedynamic`: constant folding can eliminate the call, and compiler flags/strategies may differ.

### 8.3. Dynamic Constants (`CONSTANT_Dynamic`) Are Related but Not Identical

Java classfiles also have `CONSTANT_Dynamic` for constant values computed via a bootstrap. It has conceptually similar resolution/cached result rules, but:

- An `invokedynamic` bootstrap receives a `MethodType` and must provide a `CallSite` of the matching type.
- A dynamic constant bootstrap receives the constant's type (a `Class<?>`) and must provide a **compatible value**.
- `BootstrapMethodError` can also report dynamic constant failures.

This topic focuses on **linkage of the `invokedynamic` instruction**. Do not use an `ldc CONSTANT_Dynamic` experiment as substitute evidence for the caching scope **per lexical `invokedynamic` instruction**.

## 9. Maintainable Bootstrap Design Practices

### 9.1. BSMs Should Minimize Dependence on Transient State

A BSM that depends on service discovery, the network, config files, or unready services can cause a **poisoned call site** if it fails on the first link. When lazy initialization or genuine retry is needed, a better strategy is:

1. The BSM **returns a valid CallSite** with the exact target type.
2. This target is responsible for checking conditions/delegation and can retry business logic.
3. If the target needs to change, use `MutableCallSite` or `VolatileCallSite` in accordance with type and visibility contracts.
4. Short-term business failures are reported as exceptions from the target, rather than turning into a permanent BSM linkage failure.

This does not mean every BSM must "swallow" configuration errors: if an invalid configuration is an unrecoverable error, failing fast with a linkage error can be intentional. Distinguish between **transient failure** and **invalid linkage contract**.

### 9.2. Validate the Exact `MethodType` Before Returning the `CallSite`

Even though the JVM will validate it, a BSM can proactively check:

```java
// Illustrative snippet inside a bootstrap.
MethodHandle target = ...; // Created where sufficient context is available.
if (!target.type().equals(type)) {
    target = target.asType(type); // Only valid if a supported conversion exists.
}
return new ConstantCallSite(target);
```

`asType` can throw `WrongMethodTypeException` or other conversion errors if conversion is not possible. Code must decide to fail-fast or report a clear error, rather than assuming every target type can adapt automatically.

Do not "fake" a `()String` CallSite with a `()int` target hoping the JVM will auto-cast it. The `wrong()` experiment shows the error occurs **during linkage**.

### 9.3. Observe the BSM in a Controlled Manner

A BSM is a sensitive runtime code path. If adding logs/counters for diagnosis:

- Log `caller.lookupClass()`, `name`, `type`, and static args **when permitted**, but avoid leaking sensitive data.
- Log the phases of entering the BSM, creating the target, creating the CallSite, and returning separately.
- If concurrent linkage is possible, counters must be thread-safe (`AtomicInteger` instead of `int++`). Do not use BSM side effects as business results because the BSM may run multiple times concurrently.
- Log exception class + cause, not just the message. Avoid assuming the outermost class in the log is the root error.

JVM/specification logs may vary across JDK versions; prioritize **the error, cause, and execution result** rather than matching the entire stack trace against online examples.

## 10. Investigation Workflow for a Real-World Error

When encountering `BootstrapMethodError` or suspecting an `invokedynamic` error, proceed in order:

1. **Collect the Java version and class loader.** Record `java -version`, how the JVM is started, the loader of the class containing the site, and whether any framework/agent modifies bytecode.
2. **Extract the cause chain.** If the error surfaced through `Method.invoke`, unwrap `InvocationTargetException`. If the error is wrapped by a proxy/wrapper, inspect the cause chain rather than just the outer layer.
3. **Identify the actual failing site.** Use the stack trace, method name, and `javap -v -c <class>` to locate the `invokedynamic` opcode and `BootstrapMethods` entry.
4. **Distinguish before/after linkage.** Did the BSM run? Did it return a `CallSite`? Is there a method type mismatch? Or did the target itself run and throw an exception?
5. **Check name/descriptor.** `CallSite.type()` must match the instruction's `MethodType`. For dynamic arguments/condy, inspect static argument resolution.
6. **Reproduce in a fresh initial attempt.** A failed site does not re-link when called again in the same class. To verify after fixing the root cause, use a **new JVM or a class defined under a new loader** if the architecture allows; do not just call the method repeatedly.
7. **Rule out concurrency.** A bootstrap counter greater than 1 during concurrent initialization does not necessarily prove the JVM "retried after failing"; multiple threads may have run concurrently.
8. **Write a separate test for the target.** If the CallSite is already valid, test exceptions from the target independently; do not conflate them with BSM errors.
9. **Fix at the right layer.** If the bytecode is wrong, fix the transformer/generator. If the BSM returns the wrong type, fix the BSM. If a dependency is missing, fix the binary/module graph. If it is a transient business error, consider a target with proper retry.
10. **Re-verify from a clean state.** Compare results at a new site/new JVM; do not use the old site as the sole measurement after resolution has failed.

Quick reference table:

| Symptom | Appropriate interpretation | Action |
| --- | --- | --- |
| Calling the same site again always throws `BootstrapMethodError` and BSM counter stays flat | Failure cached per instruction | Do not retry there; fix the root cause and test on a new class/JVM |
| Two methods share `InvokeDynamic #19` but have different results | Two independent lexical occurrences | Inspect each opcode, do not group solely by CP index |
| BSM counter increments once but target throws exception multiple times | Linkage succeeded, invocation failed | Diagnose the target |
| `BootstrapMethodError` has cause from BSM exception | BSM threw a non-`Error` | Fix BSM logic/configuration |
| BSM returns CallSite with wrong target type | Link validation failed | Create/cast MethodHandle to the exact `MethodType` |
| New site in a new class loader works | Different linkage state | Confirm loader identity, do not call this recovering the old site |

## 11. Questions and Exercises with Answers

**Question 1.** The BSM `bootstrap(...)` throws `IllegalStateException` on the first call to `invokedynamic`. What error type does the JVM report?  
**Answer:** Typically `BootstrapMethodError` with `cause` being `IllegalStateException`, because this exception is not a subclass of `Error`.

**Question 2.** After a linkage error, you change a variable `ready=false` to `ready=true` and call the same instruction again. Does the BSM run again?  
**Answer:** No. For sequential uses after failed resolution of **the same site**, the JVM retains the error result and does not attempt to call the bootstrap again.

**Question 3.** Two instructions in the same class both reference entry `CONSTANT_InvokeDynamic #19`. Does one site failing force the other site to fail?  
**Answer:** No. Resolution of an `invokedynamic` call site is scoped **per lexical instruction**, even when sharing a CP entry. The `fire` and `other` examples demonstrate this.

**Question 4.** The BSM returns `new ConstantCallSite(MethodHandles.constant(int.class,1))` for a `()String` instruction. At which phase does the error occur?  
**Answer:** Checking the bootstrap result during **linkage**, because the target type `()int` does not equal the descriptor `()String`; the JVM reports `BootstrapMethodError`.

**Question 5.** The BSM returns a valid `CallSite`; the target throws `IllegalStateException` on every execution. Do subsequent calls re-link?  
**Answer:** No. The site has already linked successfully. The target can continue to be invoked and throw an exception each time; this is a target error, not a BSM error. The `unstable()` example runs the BSM once and the target twice.

**Question 6.** After catching `BootstrapMethodError`, should you put `Thread.sleep(1000)` and call the old site again to "give the BSM a second try"?  
**Answer:** No. Sleeping for one second does not clear the failed resolution state. Fix the root cause at the linkage step and verify on a new site/class identity when needed.

**Question 7.** Why can a new class loader create `fire()` successfully even though the old site failed?  
**Answer:** A class with the same binary name but a **different defining loader** is a different class identity with fresh site linkage state; it is not resetting the old site.

**Question 8.** If multiple threads hit an unlinked site simultaneously, can the bootstrap counter be greater than 1?  
**Answer:** Yes. The JVMS allows the BSM to be executed concurrently, then selects one result to publish. Do not use unsynchronized `int++` to assert correctness in that scenario.

**Question 9.** The BSM directly throws `AssertionError`. Is it always wrapped in `BootstrapMethodError`?  
**Answer:** No. According to JVMS rules, an `Error` thrown in the BSM is used as the resolution error instead of always creating a BME wrapper for it.

**Question 10.** Why is `javap -v -c` needed instead of only reading Java source when diagnosing `invokedynamic`?  
**Answer:** The compiler/transformer determines the `InvokeDynamic` entries, bootstrap arguments, and method descriptors in the classfile. Source code may not directly describe the instruction or may have been modified by an enhancer.

**Question 11.** A site is linked to a `MutableCallSite`. Does calling `setTarget` make the bootstrap run again?  
**Answer:** No. `setTarget` changes the target of **the already-linked site**, with a matching type and according to the memory visibility contract; it does not re-resolve the instruction.

**Question 12.** How do you distinguish a `BootstrapMethodError` observed through Reflection from `InvocationTargetException`?  
**Answer:** `Method.invoke` wraps exceptions thrown by the invoked method. Call `InvocationTargetException.getCause()` to see the actual error; unwrapping does not alter the linkage result.

## 12. Summary and References

- `invokedynamic` is linked through a bootstrap to obtain a `CallSite` matching the descriptor.
- **`BootstrapMethodError`** reflects bootstrap failures or invalid call site results; an `Error` thrown directly by a BSM follows its own error propagation rules.
- **An instruction with failed resolution does not re-bootstrap when called again**, even if external conditions have changed.
- **Two different instructions** can link independently even when sharing a constant-pool entry; a **new class loader** creates a new class/linkage state.
- **Errors from the target after linkage** are not linkage failures and do not turn the site into a failed state.
- **Concurrency** can cause the BSM to run multiple times concurrently on the first link, but does not make sequential retries after failure valid.
- When diagnosing, inspect **cause chain, bytecode, bootstrap descriptor, CallSite type, and class loader** instead of just repeating the call.

**Official Documentation:**

- [JVMS Java SE 17 — `5.4.3 Resolution` and `5.4.3.6 Dynamically-Computed Constant and Call Site Resolution`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): defines resolution errors, behavior after failed resolution, independence of `invokedynamic` instructions, and bootstrap racing.
- [Oracle Java SE 17 — `java.lang.invoke` package overview](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/package-summary.html): call site linkage, timing, types, behavior when bootstrap throws an exception, and static arguments.
- [Oracle Java SE 17 — `BootstrapMethodError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/BootstrapMethodError.html): error meaning and relationship with `LinkageError`.
- [Oracle Java SE 17 — `CallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html): call site type, dynamic invoker, and target.
- [Oracle Java SE 17 — `ConstantCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantCallSite.html) and [`MutableCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html): distinguishing immutable targets from the ability to update targets after linkage.
- [Oracle Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): `-c` displays bytecode, `-v` displays constant pool information and bootstrap metadata.
