# VerifyError, Class Loading Errors, and Bytecode Transformation Errors

## 1. Why do these errors commonly appear when upgrading the JDK?

When migrating an application from an older JDK to a newer JDK, Java source may compile successfully yet the program fails to start, or fails only when invoking a specific feature. Messages like the following are often lumped together as "Java incompatibility errors":

~~~text
java.lang.VerifyError: Bad type on operand stack
java.lang.VerifyError: Expecting a stackmap frame at branch target ...
java.lang.NoClassDefFoundError: com/example/api/Order
java.lang.NoSuchMethodError: 'void com.example.api.Order.setId(...)'
java.lang.UnsupportedClassVersionError: ... class file version 65.0
java.lang.ClassFormatError: Invalid constant pool index ...
java.lang.reflect.InaccessibleObjectException: ...
~~~

Those errors **do not share the same cause**. Some stem from invalid bytecode; some come from the classpath and class loaders; some result from API changes between JARs; some stem from the Java Module System; and some appear after an agent, mocking framework, or instrumentation library transforms the class file.

Example scenarios:

- The application compiles on JDK 21 and uses class-file major version 65.
- A coverage agent embeds an old ASM that cannot yet read the new class file, so the tool reports `Unsupported class file major version 65`.
- Another agent can read the bytecode yet inserts a method call without updating stack map frames, causing the JVM to report `VerifyError`.
- A shaded JAR drops a dependency, leading to `NoClassDefFoundError` when the feature is called for the first time.
- A consumer is compiled against library v1 yet runs with v2 which changed a method descriptor, leading to `NoSuchMethodError`.

If fixed by arbitrarily adding JVM flags, changing the source level, or ignoring all exceptions, the migration process may temporarily mask errors while losing safety and reproducibility.

The goal of the lesson **"VerifyError, Class Loading Errors, and Bytecode Transformation Errors"** in the **Troubleshooting** chapter of **Java Advance Compatibility Migration** is to help identify the right error layer, gather evidence, pinpoint the culprit, and select the corresponding remediation.

## 2. Learning outcomes

After this lesson, the reader should be able to:

1. Explain the JVM phases of loading, linking, verification, preparation, resolution, and initialization.
2. Distinguish `VerifyError` from `ClassFormatError`, `UnsupportedClassVersionError`, `NoClassDefFoundError`, and other `LinkageError`s.
3. Determine when the error source is likely Java source/compiler, JAR deployment, custom class loader, or bytecode transformer.
4. Understand local variables, the operand stack, method descriptors, stack map frames, and control-flow merges well enough to investigate.
5. Use `java -version`, `jar`, `javap`, `jdeps`, class loading logging, and dependency graphs to find the actual class bytes running.
6. Investigate ASM, Byte Buddy, JaCoCo, Mockito, APM agents, generated code, and JVMTI/instrumentation when upgrading the JDK.
7. Design reproductions, a test matrix, and regression handling criteria without disabling bytecode verification.

## 3. The JVM does not just "open a .class file and run it"

A high-level representation:

~~~text
Java source / generated source / transformed bytecode
                        |
                        v
             .class / JAR / module
                        |
                        v
                Class loading
                        |
                        v
              Linking / Verification
                        |
                   Preparation
                        |
                 Resolution (*)
                        |
                        v
               Initialization
                        |
                        v
                 Execution
~~~

`(*)` Some resolution can be performed lazily during execution; this model does not mean every reference is resolved before the first method runs. The timing of checks and resolution operates within bounds permitted by the JVM Specification.

### 3.1. Loading

The JVM locates the binary representation of a class, usually bytecode in a JAR, directory, module image, or bytes supplied by a class loader/generator. **The class name and the class loader** together participate in the runtime identity of the type.

### 3.2. Linking

Linking includes verification, preparation, and resolution. The JVM must ensure the class file, bytecode, and references conform to runtime constraints. If bytecode violates verifier rules, `VerifyError` is a possible outcome.

### 3.3. Initialization

The JVM executes static initializers and assigns static values according to class initialization rules. A failure at this step can produce `ExceptionInInitializerError` or a root `Error`, and subsequent uses of the class may see `NoClassDefFoundError: Could not initialize class ...`.

### 3.4. Why can stack traces appear late?

A class is not necessarily loaded/verified right when the JVM starts up. For example, a payment adapter is only loaded when the first request passes through the payment path. Thus, a passing application health check does not prove every class across all JARs loads and links successfully.

## 4. Error types to distinguish before investigating

| Error/symptom | Typical failing layer | First question |
| --- | --- | --- |
| `ClassNotFoundException` | Class name lookup via API | Where is the class loader searching? |
| `NoClassDefFoundError` | Runtime fails to define/load or class init previously failed | Is a JAR missing, or was there a prior initializer failure? |
| `ClassFormatError` | Malformed class file | Are the class file bytes properly formatted? |
| `UnsupportedClassVersionError` | Class-file format exceeds JVM capability | Which JDK is the JVM running, and what is the class major version? |
| `VerifyError` | Bytecode violates verifier rules | Which operand stack, types, frames, or control flow are invalid? |
| `NoSuchMethodError` | Method symbolic reference mismatch | Which API did the caller compile against, and which method does runtime have? |
| `NoSuchFieldError` | Field symbolic reference mismatch | Did the field type/name change between JAR versions? |
| `IllegalAccessError` | Access during linking | Did an access modifier or module export change? |
| `AbstractMethodError` | Method invocation lacks a valid implementation | Was interface/class binary compatibility broken? |
| `IncompatibleClassChangeError` | Class/interface/method kind mismatch | Did static/instance or class hierarchy change? |
| `BootstrapMethodError` | Dynamic linkage bootstrap failure | Is there an error in `invokedynamic`/`ConstantDynamic` or the bootstrap method? |
| `InaccessibleObjectException` | Reflection restricted | Which module does not `opens` the package? |
| `Unsupported class file major version` from ASM/agent | Third-party bytecode parser | Which tool/embedded ASM does not yet support the new version? |
| `UnsatisfiedLinkError` | Native/JNI loading/binding | Are the native binary/symbol/OS/ABI right? |

This is a diagnostic map, not an absolute deduction table: an initial error may be wrapped or cause subsequent errors to appear. **Always preserve the first message along with `Caused by` chains and relevant class names.**

## 5. Inheritance hierarchy of related errors

~~~text
java.lang.Throwable
├── java.lang.Error
│   ├── java.lang.LinkageError
│   │   ├── VerifyError
│   │   ├── ClassFormatError
│   │   │   └── UnsupportedClassVersionError
│   │   ├── NoClassDefFoundError
│   │   ├── ClassCircularityError
│   │   ├── BootstrapMethodError
│   │   ├── UnsatisfiedLinkError
│   │   └── IncompatibleClassChangeError
│   │       ├── NoSuchMethodError
│   │       ├── NoSuchFieldError
│   │       ├── AbstractMethodError
│   │       └── IllegalAccessError
│   └── ExceptionInInitializerError
└── java.lang.Exception
    ├── ClassNotFoundException
    └── RuntimeException
        ├── ClassCastException
        └── java.lang.reflect.InaccessibleObjectException
~~~

The diagram shows only branches useful for this lesson. Subtype names in the `LinkageError` group are **Java Errors** and generally not errors that business code should broadly catch and continue past.

Specifically:

- `VerifyError` is a form of `LinkageError`.
- `NoClassDefFoundError` differs from `ClassNotFoundException` in both hierarchy and failure path.
- `UnsatisfiedLinkError` is still a `LinkageError`, though its cause usually lies in a native library or binding.
- `InaccessibleObjectException` is a runtime exception related to reflective access, not a `VerifyError`.

## 6. What does `VerifyError` actually mean?

`VerifyError` indicates that the JVM verifier detected a class file containing bytecode that cannot satisfy mandatory constraints of the Java Virtual Machine Specification.

Some common messages:

~~~text
java.lang.VerifyError: Bad type on operand stack
java.lang.VerifyError: Bad local variable type
java.lang.VerifyError: Inconsistent stackmap frames at branch target ...
java.lang.VerifyError: Expecting a stackmap frame at branch target ...
java.lang.VerifyError: Operand stack overflow
java.lang.VerifyError: Illegal type at constant pool entry ...
~~~

Exact wording may vary by JDK/vendor and check point. What matters is not memorizing messages, but understanding what the verifier protects:

- Every instruction must use valid operand types.
- The operand stack must not underflow/overflow and must remain consistent across control flow.
- Local variables must hold valid types at points of use.
- Branch targets must be valid.
- Method return instructions must match the declared return type.
- Object initialization and uninitialized references must obey rules.
- Stack map frames, when required, must describe consistent type states.
- Bytecode must not construct forbidden operations simply by writing arbitrary bytes.

The verifier is a JVM safety mechanism, not a code formatting linter. It validates bytecode-level constraints prior to/at the moment a class is used to uphold type safety.

## 7. How does the bytecode verifier differ from the Java compiler?

Java code emitted by `javac` is valid under normal conditions. However, the JVM does **not only** load code produced by official `javac`:

- A bytecode generator may synthesize classes directly.
- ASM/Byte Buddy may rewrite the instruction stream.
- An agent may transform bytes during class loading.
- A framework may generate proxies at runtime.
- A build plugin may instrument classes for coverage measurement.
- An obfuscator/shader may process classes at a post-compile stage.
- A custom class loader may define classes from decrypted data.
- Corrupt JARs, stale output, or wrong versions may appear in deployment.

Therefore:

~~~text
javac compilation successful
             ≠
all runtime class definitions are verifier-valid
~~~

In particular, if a build initially passes yet adding `-javaagent` triggers a JVM `VerifyError`, focus on **bytes before/after instrumentation** and the transformer version. Do not rush to edit business source that already compiles validly.

## 8. Operand stack: origin of "Bad type on operand stack"

Java bytecode is a stack-based architecture. Many instructions pop operands from the stack and push results back onto the stack.

Example method:

~~~java
public static int sum(int a, int b) {
    return a + b;
}
~~~

A typical bytecode representation shown by `javap -c`:

~~~text
0: iload_0
1: iload_1
2: iadd
3: ireturn
~~~

Stack progression:

| Instruction | Operand stack after instruction |
| --- | --- |
| `iload_0` | `[int a]` |
| `iload_1` | `[int a, int b]` |
| `iadd` | `[int result]` |
| `ireturn` | `[]`; returns `int` |

If a transformer replaces `iadd` with an instruction requiring a reference, such as `invokevirtual` without an appropriate receiver, the verifier can detect an invalid stack type.

### 8.1. Both stack height and stack types matter

A bytecode branch having the same **stack height** across two paths is not guaranteed valid if the element type at the corresponding slot is incompatible with the expected frame.

Illustrative example:

~~~text
Branch A stack: [java.lang.String]
Branch B stack: [int]
Merge target:   expects java.lang.String
~~~

One branch pushing an `int` to a point expecting a reference creates an inconsistency. The verifier must evaluate data flow according to instruction semantics rather than merely counting slots.

### 8.2. Category-1 and category-2 values

`long` and `double` occupy two slots in local variables/operand stack in the verifier's model, whereas many other types use one slot. A transformer changing a method descriptor from `(I)I` to `(J)J` without updating local indexes and stack handling can cause errors.

This is why changing a Java method signature or inserting instrumentation into methods with `long`/`double` must be handled through a bytecode library that understands descriptors, rather than adjusting indexes by guesswork.

## 9. Local variables, frames, and control-flow merges

A Java method can have multiple branches:

~~~java
static Object choose(boolean flag) {
    Object result;
    if (flag) {
        result = "ok";
    } else {
        result = Integer.valueOf(10);
    }
    return result;
}
~~~

The compiler generates a control-flow graph. At the merge point after `if/else`, the verifier must know the type state of locals and the operand stack. Java source may be valid because both values are assignable to `Object`.

If an agent adds a new branch without updating the stack map frame at the merge target, the JVM can reject the class:

~~~text
VerifyError: Inconsistent stackmap frames
VerifyError: Expecting a stackmap frame at branch target ...
~~~

### 9.1. What is `StackMapTable`?

`StackMapTable` is a class-file attribute describing verification type states at key locations within a method, supporting type checking under the specified verification mechanism.

It is not a Java stack trace; it is metadata **inside the class file**. Certain versions/methods have special handling rules, so do not assume every class file must contain an explicit attribute in all cases.

Inspect via:

~~~bash
javap -v -p -c -classpath build/classes example.Service
~~~

In the output, look for `StackMapTable`, `Code`, `max_stack`, `max_locals`, the exception table, and instruction offsets.

### 9.2. Offsets shift after instrumentation

When inserting instructions, branch target offsets and exception-handler ranges may need adjustment. Good bytecode libraries can manage these parts; a transformer manually manipulating byte arrays without understanding class-file structure risks producing an invalid class.

## 10. `max_stack`, `max_locals`, and exception handlers

The `Code` section of a class file describes:

- `max_stack`: operand stack limit per class file rules.
- `max_locals`: number of local variable slots required by the method.
- Sequence of bytecode instructions.
- Exception handler table.
- Attributes such as `StackMapTable`, line numbers, and local variable metadata.

A transformer adding logging with a helper call without increasing `max_stack` when necessary can cause the verifier to report an error. Adding local variables beyond `max_locals` can likewise cause class rejection.

Exception handlers are more complex because multiple control-flow edges lead to catch blocks. Inserting instrumentation at method entry/exit must account for exception paths, synchronized regions, constructor initialization, and paths going through `athrow`.

### 10.1. Constructors have specific constraints

Inside a constructor, the `this` reference is in an uninitialized state prior to the appropriate constructor call (`super(...)` or `this(...)`). A transformer using `this` prematurely as an initialized object can cause the verifier to reject the class.

Do not copy the same instrumentation snippet across every method including constructors, static initializers, and synthetic methods without considering bytecode rules.

## 11. `ClassFormatError` vs `VerifyError`

Both errors can occur when the JVM processes a class file, yet the validation angle differs.

**`ClassFormatError`** typically suggests the class file structure violates the format, such as a malformed constant-pool entry, wrong attribute length, or an invalid structural relationship.

**`VerifyError`** typically suggests bytecode/verification type state violates execution constraints, for example an instruction expects `int` while the operand stack holds an object reference.

Example:

~~~text
ClassFormatError: Invalid constant pool index ...
VerifyError: Bad type on operand stack ...
~~~

This is a diagnostic distinction, not a promise that message boundaries are identical on every JVM: the same bad class file might be caught at different check points depending on specification/implementation.

### 11.1. `UnsupportedClassVersionError` is a branch of `ClassFormatError`

When a class major version is newer than the JVM supports:

~~~text
java.lang.UnsupportedClassVersionError:
  class file version 65.0, this runtime only recognizes ...
~~~

The issue is usually not stack frames. Compare the compiler target with runtime, for example a Java 21 major 65 class file cannot run directly on a Java 17 JVM whose corresponding level is major 61.

## 12. Class-file major versions to know

| Java release | Class-file major |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

For newer JDKs, check the corresponding JVM Specification/JDK documentation instead of guessing by year.

Inspect a class:

~~~bash
javap -verbose -classpath build/classes example.Service
~~~

Look for:

~~~text
major version: 65
~~~

Or inspect a class inside a JAR:

~~~bash
javap -v -classpath app.jar com.example.Service
~~~

Note that `javap` must be used in the right mode when the JAR is a **multi-release JAR**. A root class might have major 52, while the same-named `META-INF/versions/21` variant has major 65; to diagnose, select the effective view matching runtime.

## 13. Why might "Unsupported class file major version 65" not be from the JVM?

The same message idea "does not understand Java 21 class files" can come from multiple tools:

~~~text
java.lang.UnsupportedClassVersionError: ...
~~~

usually appears when JVM/class loading encounters a class file exceeding recognized versions.

Meanwhile:

~~~text
java.lang.IllegalArgumentException:
  Unsupported class file major version 65
    at org.objectweb.asm.ClassReader...
~~~

usually indicates **the ASM version in use** does not yet understand the new format. The target JVM might fully be Java 21, yet an agent/formatter/coverage tool embedding an old ASM still fails.

### 13.1. Procedure to distinguish

1. Inspect the full exception class, not only the message.
2. Check whether the stack trace shows `java.lang.ClassLoader`, `org.objectweb.asm`, `net.bytebuddy`, `org.jacoco`, or another plugin.
3. Confirm `java -version` of the failing process.
4. Confirm the major version of the class the tool is reading.
5. Check the bytecode parser version embedded in that tool.
6. Choose a tool version published by the vendor as supporting the target class-file/JDK.

Do not fix by adding `--add-opens` if the cause is an ASM parser not understanding version 65; module access and parser format support are two separate issues.

## 14. `ClassNotFoundException` and `NoClassDefFoundError`

### 14.1. `ClassNotFoundException`

A checked exception typically thrown when code actively looks up a class by name:

~~~java
Class<?> plugin =
        Class.forName("com.example.plugins.JsonProvider");
~~~

If the class loader cannot find that class, `ClassNotFoundException` may be thrown. Check the class name, deployed JARs, class loader, classpath, and module path.

### 14.2. `NoClassDefFoundError`

`NoClassDefFoundError` is a `LinkageError`. It can occur when a class existed in the compile environment yet cannot be defined/found at runtime, or when the class previously failed initialization.

~~~text
java.lang.NoClassDefFoundError:
  com/example/json/JsonProvider
~~~

Check deployed JARs, excluded transitive dependencies, shading, class loaders, and modules.

### 14.3. `NoClassDefFoundError: Could not initialize class`

Example:

~~~java
public final class CryptoBridge {
    static {
        System.loadLibrary("cryptohelper");
    }
}
~~~

If the first attempt to invoke the class hits `UnsatisfiedLinkError` inside the static initializer, subsequent attempts in the same JVM can report:

~~~text
java.lang.NoClassDefFoundError:
  Could not initialize class example.CryptoBridge
~~~

Do not blindly add Java JARs to fix this case. Locate **the first time class initialization failed**; the root cause may be a native library.

## 15. `ExceptionInInitializerError` can mask the original stack trace

A static initializer:

~~~java
final class Settings {
    static final String URL = loadUrl();

    private static String loadUrl() {
        throw new IllegalStateException("missing URL");
    }
}
~~~

First use of `Settings` can produce:

~~~text
java.lang.ExceptionInInitializerError
Caused by: java.lang.IllegalStateException: missing URL
~~~

Subsequent uses may see `NoClassDefFoundError` because class initialization already failed.

Note: if static initialization throws an `Error` object, the JVM does not necessarily wrap it in `ExceptionInInitializerError`; read the exact `Caused by` and timeline.

### 15.1. Restarting is not proof the error is fixed

Starting a fresh JVM restarts class initialization. Right after restart you might see `UnsatisfiedLinkError` the first time, then `NoClassDefFoundError` on subsequent calls in the same process. That can be **one issue** appearing in two stages, not two separate bugs.

## 16. `NoSuchMethodError` and ABI errors that are not `VerifyError`

Suppose a consumer compiles against:

~~~java
// library v1
public final class PriceService {
    public int calculate(int units) {
        return units * 10;
    }
}
~~~

Yet runtime deploys v2:

~~~java
// library v2
public final class PriceService {
    public long calculate(long units) {
        return units * 10;
    }
}
~~~

Caller bytecode v1 still references method descriptor `calculate(I)I`. If runtime v2 no longer has that method, the JVM can report `NoSuchMethodError`. The caller's bytecode may be completely valid in type state; the error comes from symbolic reference resolution.

### 16.1. Method descriptors include the return type

Use:

~~~bash
javap -s -p -classpath library.jar example.PriceService
~~~

Typical descriptors:

~~~text
calculate(int): int    -> (I)I
calculate(long): long  -> (J)J
~~~

Changing the method descriptor, static/instance kind, class/interface shape, or field type can produce various linkage errors. Do not fix by increasing `max_stack` or recomputing stack map frames.

### 16.2. Why can a Java linkage error appear only after instrumentation?

A transformer may inject a call to a helper API that the agent compiled against a new version, while at runtime an old helper JAR gets resolved. The JVM may report `NoSuchMethodError` from the newly inserted instruction. The source of change is still instrumentation, yet **the nature of the error** is method linkage, not bytecode verification.

## 17. `IllegalAccessError` differs from reflection errors

`IllegalAccessError` can occur when bytecode tries to access a class/member disallowed by linking/access rules.

`java.lang.reflect.InaccessibleObjectException` typically occurs when reflective code attempts to open deep access to a class/package disallowed by the Java Module System.

Example:

~~~text
java.lang.IllegalAccessError: class A tried to access class B ...
~~~

versus:

~~~text
java.lang.reflect.InaccessibleObjectException:
  Unable to make ... accessible: module ... does not "opens" ...
~~~

The solution may be updating dependencies or configuring exports/opens where the contract allows. Do not attribute every module-related error to `VerifyError`; verifier type checking, module access, and reflection policy serve distinct purposes.

### 17.1. Do not use `--add-opens` as a universal cure

A flag such as:

~~~text
--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

is merely a syntax example for a specific reflective access scope. It does not add a missing method, does not fix a class-file format, and does not supply valid stack frames. When needed, identify exactly which library is accessing which package, what permission is missing, and the supported version.

## 18. Two classes with the same name are not necessarily one type

A Java runtime type is identified by **its binary name and defining class loader**. In an application server, plugin framework, or OSGi, two classes with the same name can be loaded:

~~~text
loader A -> com.example.Model
loader B -> com.example.Model
~~~

Type casting can result in:

~~~text
ClassCastException:
  class com.example.Model cannot be cast
  to class com.example.Model
~~~

That is usually a class identity/class-loader isolation error, not the JVM verifier. A bytecode transformer must also account for the class loader of the instrumented class when injecting helper references.

### 18.1. Parent delegation is not the only design

A custom class loader may use child-first or a custom strategy. If an agent assumes every helper exists on the system class loader, a class loaded by a plugin loader may fail to resolve the helper and throw `NoClassDefFoundError`. This may only occur when the plugin is invoked while the main application keeps working.

## 19. `ClassFileTransformer` mechanism in Java agents

The Java Instrumentation API allows agents to register transformers:

~~~java
instrumentation.addTransformer(transformer);
~~~

When a class is defined or reprocessed under instrumentation, the JVM can invoke the transformer to obtain new class bytes.

A minimal transformer that only observes class names:

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class ObserveClasses implements ClassFileTransformer {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {
        if (className != null
                && className.startsWith("example/service/")) {
            System.err.println("[agent] " + className);
        }
        return null; // Do not modify class bytes.
    }
}
~~~

The example uses the traditional overload; modern JDKs also provide an overload taking `Module`. When returning `null`, the transformer requests no byte modifications. If returning new bytes, the JVM validates the new class file according to the applicable constraints.

### 19.1. How does a transformer cause `VerifyError`?

Example modification chain:

~~~text
Original class bytes (valid)
             |
             v
Transformer inserts instructions
             |
             +--> updated method descriptor?
             +--> updated stack / locals?
             +--> updated branch targets?
             +--> updated StackMapTable?
             +--> preserved constructor constraints?
             |
             v
Transformed class bytes
             |
             v
JVM verifier
             |
             +--> valid -> class can link
             |
             +--> invalid -> VerifyError / related error
~~~

Errors can originate from **the transformer implementation**, **another transform before/after**, or **a bytecode library not supporting the new class-file version**.

## 20. Startup agent vs dynamic attach in troubleshooting

A startup agent is configured with:

~~~bash
java -javaagent:/opt/agents/monitor.jar -jar app.jar
~~~

The JVM calls `premain` before `main`. The agent can observe class loads very early.

Dynamic attach uses `VirtualMachine.loadAgent` via the Attach API so a running JVM invokes `agentmain` when policy/permissions permit.

### 20.1. Why know when the agent was loaded?

If the failing class was loaded before a dynamic agent appeared, a transformer registered afterward does not automatically change it. The agent needs retransformation/redefinition when supported by the JVM and when the class is modifiable. Conversely, a startup agent can intercept right on first definition.

Investigation must record:

- Agent JAR, version, and checksum.
- Startup or dynamic attach.
- Ordering of `-javaagent` flags.
- Which transformer returns new bytes.
- Whether the class loaded before or after the agent.
- Whether `Can-Retransform-Classes` is required.
- JVM support for `isRetransformClassesSupported()` and `isModifiableClass()`.

### 20.2. JEP 451 and JDK 21

Starting in JDK 21, dynamic agent loading can emit warnings under JEP 451 on applicable JVMs, moving toward policies requiring explicit authorization. This warning is not synonymous with `VerifyError`. An agent may load validly yet transform erroneously; or it may be blocked by policy before any class transformation occurs.

Do not disable security controls or enable broad dynamic attach merely to diagnose an exception if environment policy disallows it.

## 21. ASM: reading, writing, and computing frames

ASM is a library for manipulating bytecode at the class-file level. In an instrumentation pipeline, ASM can:

- Read via `ClassReader`.
- Create/transform visitors for classes and methods.
- Write via `ClassWriter`.
- Compute certain metadata such as maximum stack/local sizes and stack map frames.
- Provide utilities to check representations before the JVM loads the class.

Example illustrating reading and rewriting a class with ASM:

~~~java
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;

public final class BytecodeRewriter {
    public static byte[] rewrite(byte[] original) {
        ClassReader reader = new ClassReader(original);

        ClassWriter writer = new ClassWriter(
                reader,
                ClassWriter.COMPUTE_FRAMES
                        | ClassWriter.COMPUTE_MAXS);

        reader.accept(writer, ClassReader.EXPAND_FRAMES);
        return writer.toByteArray();
    }
}
~~~

This is a **mechanism example** to explore the flags, not a production transformer safe for every class loader/module. When `COMPUTE_FRAMES` needs to find a common superclass, ASM may have to resolve types. Its default resolution mechanism may not fit custom class loaders, modules, or classes that exist only inside the target JVM.

### 21.1. `COMPUTE_MAXS` does not replace `COMPUTE_FRAMES`

`COMPUTE_MAXS` helps compute stack/local limits. It does not mean every stack map frame is recomputed accurately for control-flow transformations. `COMPUTE_FRAMES` handles frame computation subject to the ASM version and the classpath/type hierarchy it can observe.

If an agent inserts jumps or alters data flow using only `COMPUTE_MAXS`, old frames may become invalid. However, simply enabling `COMPUTE_FRAMES` when the input class is malformed or hierarchy lookup fails will not solve everything either.

### 21.2. ASM compatibility with the JDK/class file is required

The ASM version must understand the class-file format/opcodes/attributes it needs to read/write. When upgrading from Java 17 to 21, an agent embedding an old ASM can report `Unsupported class file major version 65`.

The fix is upgrading **the tool or agent that actually packages ASM**, preferring a vendor-supported version. Forcing a transitive ASM dependency override in the application may have no effect if the agent shades ASM into its own JAR.

## 22. Checking ASM output with `CheckClassAdapter`

ASM includes utilities to check certain correctness properties of a class representation:

~~~java
import java.io.PrintWriter;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.util.CheckClassAdapter;

public final class InspectBytes {
    public static void inspect(byte[] bytes) {
        ClassReader reader = new ClassReader(bytes);
        CheckClassAdapter.verify(
                reader, false, new PrintWriter(System.err, true));
    }
}
~~~

This example depends on the ASM utility artifact and matching runtime/classpath. It is a helper step to detect issues **before the JVM defines the class**, not a certification that all behavior or the JVM verifier will accept the bytes in every environment.

Some variants of `CheckClassAdapter.verify` use a specific class loader to resolve types. When debugging application server/OSGi classes, provide the appropriate type resolution context if the API version allows.

### 22.1. Do not inspect the wrong bytes

If agent A produces bytes A, agent B modifies them further into bytes B, and the JVM loads B, checking that A "passes" does not prove B is valid.

You need **the bytes at each pipeline stage** and, whenever possible, inspect the final bytes the JVM actually receives. Instrumentation frameworks may offer a mechanism to dump transformed classes; use supported features and store files securely.

## 23. Byte Buddy and dynamic code generation

Byte Buddy is frequently used by frameworks to generate subclasses, proxies, method interceptors, or transform classes. During migration, errors can surface:

- When the library does not yet support a new class-file version.
- When a generated method returns a type mismatching the declared method.
- When instrumentation injects calls to a helper invisible to the class loader.
- When method/field access or module boundaries change.
- When agent retransformation hits structural class-change limits.
- When a mock framework or runtime library resolves the wrong Byte Buddy version.

Do not blame every error with `net.bytebuddy.*` frames on a Byte Buddy core bug. The plugin itself may have misconfigured a matcher/Advice or used an incompatible API version.

### 23.1. Advice and return types

Suppose a method has:

~~~java
public long getBalance() {
    return 100L;
}
~~~

Custom advice attempting to return an object reference instead of `long` without boxing/unboxing and matching descriptors can render the bytecode invalid. Instrumentation libraries provide APIs to declare bindings/return types; follow the exact contract instead of manually inserting stack instructions.

### 23.2. Distinguishing generation from transformation

Dynamic class generation can create a brand-new class; transformation modifies an existing class. When retransforming/redefining an already-loaded class, the JVM enforces limits on altering the class schema. An operation valid when creating a new class is not necessarily valid when retransforming an existing class.

## 24. Coverage, mocking, and APM agents

Tool groups that commonly manipulate bytecode:

| Tool/group | Mechanisms possibly used | Errors to watch when upgrading JDK |
| --- | --- | --- |
| JaCoCo/coverage | Inserts probes into methods | Unsupported classfile version, frames/instrumentation |
| Mockito with inline instrumentation | Byte Buddy/agent instrumentation | Dynamic attach policy, transformer compatibility |
| APM/tracing Java agents | Startup `-javaagent` and class transformers | Framework matchers, module access, classfile support |
| Profiling/monitoring | Java/native agents, JVMTI/JFR | Native/JVM version, permissions, and class loading |
| Framework proxies | Runtime-generated subclasses/classes | Constructors, method descriptors, module access |
| Build-time enhancer | Rewrites class files after `javac` | Stale output, bad frames, plugin version |

A unit test failing due to mocking/coverage does not mean application Java source is wrong. Yet when test infrastructure cannot run, the team lacks sufficient quality evidence to declare the migration complete.

### 24.1. When tests pass without the agent

This is an isolation signal, not a final conclusion:

~~~text
JDK 21 + application + agent A = VerifyError
JDK 21 + application without agent = PASS
~~~

Next, identify which class agent A transforms and why the bytes are invalid. Do not treat turning off performance/security/coverage agents in production as a valid fix if the agent is an operational requirement.

## 25. A pipeline with multiple transformers

Example:

~~~text
Original .class from JAR
          |
          v
Transformer A: tracing
          |
          v
Transformer B: mocking / testing
          |
          v
Transformer C: coverage
          |
          v
JVM verification and class definition
~~~

Simplified diagram: actual ordering and application rules can differ during retransformation or when transformers are registered in different groups. Yet it illustrates a reality: **an error appearing only when combining agents** can come from interacting transformations, even though each agent passes alone.

### 25.1. Testing combinations and ordering

When suspecting a conflict:

1. Record every `-javaagent` and `-agentlib`/`-agentpath`.
2. Confirm the actual startup ordering of agents.
3. Run A-only, B-only, and A+B in staging.
4. Compare class bytes or logs of transformed class names.
5. Inspect helper class visibility and duplicate instrumentation.
6. Read vendor guidance on two agents instrumenting the same framework.

Do not simply reorder agents in production without testing; impacts can ripple into observability, performance, and business behavior.

## 26. Class loading from shaded, relocated, or repackaged JARs

A JAR may be built cleanly, yet packaging steps alter the bytes:

- Maven Shade/Gradle Shadow relocation.
- Bytecode obfuscation/minification.
- Repackaging into fat/nested JARs.
- Dropping `META-INF/services` files or rewriting manifests.
- Merging duplicate classes across multiple dependencies.
- Build plugins instrumenting output post-compilation.

For example, library A references `com.vendor.Helper`, yet shading relocates it to `shaded.com.vendor.Helper` while missing a descriptor/annotation/reference. Runtime can encounter `NoClassDefFoundError`, `ClassFormatError`, `VerifyError`, or linkage errors depending on the broken site/reference.

### 26.1. Inspect the final artifact

Do not inspect only `target/classes` or `build/classes/java/main`. Inspect **the exact JAR/container/JVM image to be deployed**:

~~~bash
jar --list --file build/final-app.jar
java -version
~~~

Then run `javap`/`jdeps` on the right artifact, or extract classes into an isolated workspace when analysis requires it.

### 26.2. Multi-release JARs

An MRJAR has root classes and variants under `META-INF/versions/N`. A raw ZIP scanner might read the Java 21 variant on a lower JVM or skip the branch actually selected. With `javap`/`jdeps` support:

~~~bash
javap --multi-release 21 \
  -classpath library.jar -v com.example.Feature

jdeps --multi-release 21 --summary library.jar
~~~

Note: selecting a view in a tool does not replace runtime testing on the real JDK. Custom class loaders or nested-JAR launchers may differ in MRJAR support.

## 27. `invokedynamic`, lambdas, and bootstrap method errors

Since Java 7/8, the JVM has dynamic linkage mechanisms such as `invokedynamic`, widely used for lambdas and JVM languages. `ConstantDynamic` arrived in later class-file formats and also uses a bootstrap mechanism.

A bootstrap method can:

- Reside in an unavailable class/helper.
- Have a mismatched method handle/descriptor.
- Throw an exception while creating a call site or dynamic constant.
- Hit module accessibility or class-loader issues.

The result can be `BootstrapMethodError` or another linkage/initialization error, **not necessarily `VerifyError`**.

### 27.1. When to suspect bootstrap

If the stack trace contains:

~~~text
java.lang.BootstrapMethodError: bootstrap method initialization exception
~~~

or frames involving `java.lang.invoke`, inspect:

- Constant pool entries involving `InvokeDynamic`/`Dynamic`.
- The `BootstrapMethods` attribute.
- Method handles and referenced classes.
- Classpath/module path and helper JAR versions.
- Whether a bytecode transformer altered the constant pool or bootstrap arguments.

Do not fix by modifying `StackMapTable` before confirming there is an actual verification failure.

## 28. Errors specific to using the Java Module System

When upgrading from JDK 8 to JDK 11/17/21, strong encapsulation and module boundaries can break tooling.

Example:

~~~text
java.lang.reflect.InaccessibleObjectException
java.lang.IllegalAccessError
java.lang.NoClassDefFoundError
~~~

These errors can arise from an agent, annotation processor, reflection library, or custom loader. The cause is not automatically malformed bytecode.

### 28.1. Module readability and exports

A class in module A referencing a type in module B may need a read edge and appropriate package exports. A transformer injecting a helper reference that the target module is not permitted to access can cause runtime linkage failure.

### 28.2. Reflection requires opens

Frameworks using `setAccessible(true)` may need packages opened under JPMS rules. For older libraries, prioritize a version supporting the target JDK. If a workaround is needed, open only the specific package to the specific module with an owner/removal milestone.

### 28.3. `Instrumentation.redefineModule`

The Java Instrumentation API provides ways to adjust certain module relationships within JVM-supported bounds. This is an advanced API, not a reason to open all JDK internals. Agents must be tested for security/access on the exact runtime.

## 29. Bytecode created by annotation processors and generators

Not all generated code follows the same path:

- Ordinary annotation processors generate Java source which the compiler then compiles.
- Some bytecode generators write class files directly.
- Build-time enhancers modify class files after the compiler.
- Proxies are generated at runtime.
- OpenAPI/JAXB/protobuf generators primarily produce Java source, though the overall pipeline may integrate other enhancers/instrumentation.

If generated **Java source** fails to compile, the cause is not yet JVM `VerifyError`. If source compiles yet the class gets rewritten by a plugin and then fails to load, analyze the final output.

### 29.1. Distinguish the two errors

~~~text
error: cannot find symbol ...
~~~

is a compiler/source error in normal situations.

~~~text
java.lang.VerifyError: ...
~~~

indicates the JVM verifier is rejecting bytecode. Do not lump both together as "generator bug" while ignoring the phase in which it occurred.

### 29.2. Upgrade generators and compilers in sync

An older JDK parser/plugin may not understand records, sealed classes, or pattern switches. A newer class-file version may also exceed an enhancer's bytecode engine version. During migration, inventory **generator/parser/bytecode library versions** separately from **the application runtime JDK**.

## 30. Step-by-step investigation workflow

### Step 1 — Capture the first message

Record the full stack trace, `Caused by`, class name, method name, loader/module information, timestamp, and thread. If class initialization failed and then caused `NoClassDefFoundError`, find the **root error** in the same process.

### Step 2 — Identify the error layer

Ask:

- JVM rejects class file → `ClassFormatError` or `VerifyError`?
- JVM does not understand class-file version → `UnsupportedClassVersionError`?
- ASM tool rejects version → exception from parser library?
- JVM cannot find class/helper → `NoClassDefFoundError`?
- Method/field API changed → `NoSuchMethodError`/`NoSuchFieldError`?
- Is there deep reflection/module denial?
- Is there a JNI/native loader failure?

### Step 3 — Record the real environment

~~~bash
java -version
javac -version
~~~

Record the target JVM vendor/build, OS/image, CPU architecture, JVM flags, agents, and artifact hash.

### Step 4 — Locate the actual class bytes

Identify the JAR/directory/module source used by the runtime loader. If the class was generated or transformed, find the bytes **after** those steps, not only the class file in source output.

### Step 5 — Inspect the class file

~~~bash
javap -v -c -p -classpath path/to/classes-or.jar \
  com.example.Service
~~~

Look for version, methods, descriptors, `Code`, `StackMapTable`, and relevant constant-pool references.

### Step 6 — Compare baseline and target

Compare the same class before/after JDK migration, before/after transformer, or agent A enabled/disabled in a controlled environment.

### Step 7 — Fix at the right layer

- Wrong compile target → fix toolchain/`--release`.
- Mismatched JAR/version → fix dependency resolution and packaging.
- Outdated agent/ASM → upgrade tool per support matrix.
- Bad frames/bytecode → fix transformation logic and re-verify.
- Loader/module conflict → fix appropriate visibility/access policy.
- Missing native library → fix native artifact/image/ABI.

### Step 8 — Re-run regression tests

Run on the real JVM/runtime image; verify not only that the exception disappeared, but also that instrumentation, data behavior, tests, observability, and performance remain correct.

## 31. Analyzing errors directly from the `VerifyError` message

Example:

~~~text
Exception in thread "main" java.lang.VerifyError:
  Bad type on operand stack
Exception Details:
  Location:
    com/example/Service.process()V @25: invokevirtual
  Reason:
    Type integer (current frame, stack[0])
    is not assignable to 'java/lang/Object'
  Current Frame:
    bci: @25
    locals: { ... }
    stack: { integer }
  Bytecode:
    ...
  Stackmap Table:
    ...
~~~

This illustrates a HotSpot-style message structure; fields and wording vary by error.

**How to read:**

1. `Location`: class, method, descriptor, and bytecode index (`bci`).
2. `Reason`: which type constraint was violated.
3. `Current Frame`: locals and operand stack inferred by the verifier.
4. `Bytecode`: instruction region causing the problem.
5. `Stackmap Table`: expected verification states at relevant frames.

Place `bci 25` alongside `javap -c -v -p` to see which operand the instruction expects. If the class was rewritten by a transformer, use the disassembly of the **transformed bytes**, not the original source class.

### 31.1. `bci` is not a Java line number

Bytecode index is the offset in the instruction stream, not a source line number. `LineNumberTable` can help correlate them, yet generated/runtime-generated code may lack source line information. When debug metadata is absent, bytecode and stack state analysis remain the primary data source.

## 32. Class loading logging and class loader inspection

On HotSpot JDKs supporting unified logging:

~~~bash
java -Xlog:class+load=info -jar app.jar
~~~

The command can supply class names and loading sources to spot classes coming from unexpected JARs/versions. Logs can be very large; limit scope and avoid sharing sensitive paths/details indiscriminately.

`java -Xlog:help` helps check available tags/levels on a specific JVM. Do not assume every JDK vendor uses the exact same logging system or tags.

### 32.1. Inspecting class loaders on a running JVM

Some JDKs provide diagnostics via `jcmd`:

~~~bash
jcmd <pid> help
jcmd <pid> VM.classloaders
~~~

`<pid>` must be the PID of an authorized JVM; command availability depends on JVM/version and attach policy. Do not use these tools to access unauthorized processes, and do not treat the ability to run `jcmd` as proof that dynamic Java agent loading is also allowed.

### 32.2. Class source can differ from compile classpath

An application server with class loader isolation, or a fat JAR with nested dependencies, may load a different library version than IDE/`mvn dependency:tree` expects. Thus, the build dependency list is **one kind of evidence**, while runtime class source is another.

## 33. Dependency graph: finding the true runtime version

### 33.1. Maven

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

Inspect BOMs, scopes, exclusions, plugin dependencies, and actual JARs in deployment. Runtime dependencies and annotation processor/plugin classpaths may differ.

### 33.2. Gradle

~~~bash
./gradlew :app:dependencies \
  --configuration runtimeClasspath

./gradlew :app:dependencyInsight \
  --dependency byte-buddy \
  --configuration runtimeClasspath
~~~

If an error comes from a build plugin or test agent, the application's `runtimeClasspath` **does not necessarily contain the failing tool**. Inspect the corresponding buildscript/plugin/test configuration and standalone packaged agent JARs.

### 33.3. Dependency shading

An APM agent may embed ASM under a relocated package, so it does not appear under `org.objectweb.asm` in the application's dependency tree. Check **the agent release/version and embedded libraries** in vendor documentation.

## 34. Comparing original class and transformed class

Real-world scenario:

~~~text
classes/original/com/example/OrderService.class
classes/transformed/com/example/OrderService.class
~~~

If the framework provides a transformed bytecode dump feature, save to an authorized diagnostic workspace and compare:

~~~bash
javap -v -c -p \
  -classpath classes/original \
  com.example.OrderService

javap -v -c -p \
  -classpath classes/transformed \
  com.example.OrderService
~~~

Record:

- Class-file major/minor versions.
- Method descriptors.
- New instructions and method references.
- Exception handlers.
- `max_stack`/`max_locals`.
- `StackMapTable`.
- Helper classes and module references.

### 34.1. Do not publish transformed bytes containing secrets

Bytecode dumps can include string constants, class/method names, endpoint names, or business data. Store and share per security policy; do not post unvetted production artifacts on public forums.

### 34.2. Use observational data rather than guesswork

An A/B test confirming `VerifyError` appears only with the new agent is useful evidence. Yet the exact cause still requires inspecting bytes and stack traces. The new agent might simply be exposing a bug in another transformer rather than being the transformer directly creating the broken class.

## 35. Testing classes before passing them to a class loader

For an internal bytecode generator pipeline, have multiple verification layers:

1. Parse output with a compatible bytecode library.
2. Check structural invariants and frames via appropriate utilities.
3. Define the class in a test/isolated JVM matching the target JDK.
4. Execute methods containing branches, exceptions, and constructors.
5. Test with real class loaders and modules.
6. Run integration scenarios exercising the generated code.

### 35.1. Offline parsing/verification does not replace the JVM verifier

A library may read and check bytes cleanly, yet the JVM can still reject them due to deeper constraints, environment specifics, or unresolvable dependencies. Do not equate "ASM checks pass" with "JVM verified".

### 35.2. Do not inject malformed classes into production to test

Intentionally generating invalid class bytes should only be done in isolated tests or developer tooling with controlled data/scenarios. Never test directly on a production JVM serving traffic.

## 36. Why should bytecode verification not be disabled?

Some older docs or answers may advise:

~~~text
-Xverify:none
-noverify
~~~

These verification-skipping flags have been deprecated and/or are no longer useful/supported in modern JDKs. More importantly, **disabling the verifier does not fix malformed bytecode** and can strip away a JVM safety mechanism.

Do not treat this as a production fix for `VerifyError`. If an agent emits bad bytecode, fix the agent/transformer or pick a compatible version. If a class file has bad packaging, fix the artifact. If the compiler target is wrong, fix the build.

### 36.1. `-Xverify:all` serves a different role

On JVMs that support it, `-Xverify:all` requests verification under the specified mode, which can help during investigation. However, it is not a "compatibility booster" solution and does not replace inspecting bytes/stack traces. Confirm option availability with the target JDK vendor/release.

## 37. Three common diagnostic examples

### Example A — JDK 17 to 21, coverage parser cannot understand class file

Situation:

~~~text
Compile Java 21: SUCCESS
Start app without coverage: SUCCESS
Run tests with coverage: FAIL
IllegalArgumentException: Unsupported class file major version 65
Stack trace contains ASM/coverage library
~~~

Analysis:

- Major version 65 is Java 21.
- The Java 21 JVM runs the class itself fine.
- Failure occurs inside the coverage tool's bytecode parser, not the Java verifier.

Action plan:

1. Identify the actual coverage plugin/agent version.
2. Check the vendor support matrix for Java 21 class files.
3. Upgrade the right plugin/agent/embedded parser stack per policy.
4. Re-run unit tests, instrumentation, and coverage reports.
5. Check whether the agent loads at startup or dynamically; handle attach policy separately if relevant.

Do not downgrade the target to Java 17 just to hide an outdated coverage tool once the product has decided to move to Java 21.

### Example B — Agent inserts a branch missing frames

Situation:

~~~text
Java app without agent: PASS
Java app with tracing agent: VerifyError
  Expecting a stackmap frame at branch target ...
Affected class: com.example.OrderService
~~~

Primary hypothesis: Transformer inserts a jump/exception handler, leaving stack map frames inconsistent.

Action plan:

1. Record the agent JAR/version and class output path.
2. Dump transformed bytes if the tool supports it.
3. Compare `javap -c -v` before/after and check `bci` in the VerifyError.
4. Check whether the transformer updates control flow, stack/locals, and frames.
5. If using ASM, check `COMPUTE_FRAMES` and its ability to resolve the type hierarchy on the right class loader.
6. Use a byte-checking utility combined with a JVM load test.
7. Fix/upgrade the transformer and test on both old/new JDKs per contract.

Do not fix by adding hypothetical JARs or disabling the verifier.

### Example C — Shaded JAR missing helper class

Situation:

~~~text
CI unit test on classes directory: PASS
Packaged application start: PASS
First API request: NoClassDefFoundError
  com/vendor/codec/InternalHelper
~~~

Hypothesis: Helper was dropped/mis-relocated during shading or is invisible to the class loader.

Action plan:

1. Identify which class loads from the final JAR.
2. Inspect `jar --list` and packaging output.
3. Inspect the dependency graph and shading relocations.
4. Use `jdeps`/`javap` to check references.
5. Fix packaging/loader rules.
6. Test the feature requiring the helper on the final artifact, not just startup.

This is a class loading/linkage error; recomputing `StackMapTable` will not fix a missing class.

## 38. `NoSuchMethodError` only when adding an agent

An agent is compiled against `TraceHelper` v2 which has method:

~~~java
public static void onEnter(String operation, long startedAt);
~~~

Yet the runtime helper seen by the JVM is v1:

~~~java
public static void onEnter(String operation);
~~~

The transformer injects a call to descriptor v2. The JVM may load the transformed class, and then when resolving the helper method report:

~~~text
java.lang.NoSuchMethodError:
  'void example.agent.TraceHelper.onEnter(java.lang.String,long)'
~~~

Diagnostic points:

- A method-call instruction that is syntactically/stack-valid does not guarantee the method exists at runtime.
- The error is not `VerifyError` if bytecode structure and operand types are valid.
- Inspect the actual helper class resolved by the class loader and the agent JAR version.

For agents with shading/relocation or class-loader isolation, adding a `trace-helper` dependency onto the app classpath is not always right. Follow the agent packaging documentation and fix the loader strategy.

## 39. Multiple class loaders with the same class name

Suppose:

~~~text
AppClassLoader    -> com.example.spi.Payment
PluginClassLoader -> com.example.spi.Payment
~~~

When a plugin returns a `Payment` object defined by the plugin loader, application code casting to `Payment` defined by the app loader can hit `ClassCastException`.

If a transformer inserts a method call using a `Payment` helper class in a different loader, it can cause other linkage/access issues.

### 39.1. Investigation steps

1. Record the class name and defining loader of each type whenever possible.
2. Inspect the parent/child-first delegation model.
3. Determine whether API classes must be shared via a parent loader.
4. Check for duplicate JARs and plugin isolation.
5. Consider transformer/helper visibility across each loader.
6. Run integration tests with the real loader structure.

Do not treat two classes with the "same fully qualified name" as the same class type inside the JVM.

## 40. Test matrix for JDK migration

A minimal support matrix for a system with bytecode agents:

| Case | JDK | App artifact | Agent/instrumentation | Purpose |
| --- | --- | --- | --- | --- |
| A | Old JDK | Old artifact | Old agent | Baseline |
| B | New JDK | Old artifact if supported | Old agent if supported | Isolate runtime impact |
| C | New JDK | New artifact | No agent (staging) | Isolate app/packaging errors |
| D | New JDK | New artifact | New agent | Target combination |
| E | New JDK | New artifact | All real agents | Detect interactions |
| F | Minimum still-supported JDK | Matching final artifact | Compatible agent | Backward support |

Do not force running combinations unsupported by the vendor. Every test record should include JDK vendor/build, image digest, agent checksum, JVM flags, and test report.

### 40.1. Mandatory tests to include

- Clean build and source/bytecode target.
- JAR/module/classloader resolution.
- Generated code and proxies.
- Real bytecode verification when loading critical features.
- Unit/integration tests with approved agents/coverage/mocks.
- Startup and first-request smoke tests.
- Instrumented serialization/HTTP/JDBC/async paths.
- Module/reflection access and JNI if relevant.
- Observability: traces, metrics, and error capture.
- Performance/GC/startup overhead on critical workloads.

### 40.2. Test the released artifact, not only the build directory

A build plugin can transform classes after unit tests compile source. If only `build/classes` is tested while `app-all.jar` is deployed, the actual classes may differ. Run at least one smoke/integration suite on **the final artifact**.

## 41. Minimum evidence to collect when reporting an incident

Record template:

~~~text
Incident ID:
Java application artifact and SHA-256:
JDK vendor/version/build:
OS image/architecture:
First Throwable and full stack trace:
Class binary name / method / descriptor:
Bytecode index (bci), if VerifyError:
Class-file major/minor version:
Loaded-from JAR/module/class-loader:
Manifest/MRJAR version selected:
Build tool/compiler --release:
Transformers/agents and versions/checksums:
Transformation timing and class loading order:
Original/transformed class byte checksums:
Dependency and shading graph:
Known-good baseline:
Smallest reproducible scenario:
Fix and test evidence:
Owner and release decision:
~~~

Do not post credentials, tokens, heap/core dumps, or bytecode with sensitive info to public issues. Redact JVM arguments and paths according to policy.

### 41.1. Preserve the first error

A continuously restarting service may log across multiple processes. When class initialization fails, `NoClassDefFoundError` on a later request is not the root cause. Keep logs from the first time the JVM loaded the class/agent; across multiple processes, tag logs with the corresponding PID/container ID.

## 42. General diagnostic flow

~~~text
App does not start / fails at first use
                |
                v
      Which exception/error?
                |
     +----------+-----------------------------+
     |          |                             |
     v          v                             v
 VerifyError  ClassNotFound / NoClassDef    Method/field linkage
     |          |                             |
     v          v                             v
 Frames,     JAR/class-loader,             API descriptors,
 stack,      initialization cause,         resolved versions,
 control     shading, modules              static/instance kind
 flow
     |
     v
 Was class transformed?
     |
     +-- yes --> agent/ASM/Byte Buddy, bytes before/after
     |
     +-- no  --> compiler, generator, artifact integrity

 Cross-cutting:
 - JVM full version and class-file major
 - OS/container and runtime artifact
 - JPMS and security policy
 - original first stack trace
 - integration test on final artifact
~~~

This is an overview decision tree. If an exception originates from a native loader, FFM/JNI, or bootstrap method, pivot to the corresponding specialized investigation branch rather than forcing it into one of the three columns.

## 43. Anti-patterns to avoid

**"Enabling `-noverify` fixes `VerifyError`."** Incorrect and unsafe. Fix the malformed bytecode or the tool generating it.

**"Passing compilation means every runtime class is valid."** Incorrect if post-compile transformation, shading, code generation, or custom loaders occur.

**"`Unsupported class file major version` always means an old JVM."** Incorrect if the message comes from ASM or a bytecode parser tool.

**"Seeing `NoClassDefFoundError` just means add a JAR."** Incorrect when class initialization previously failed or the loader lacks visibility.

**"`NoSuchMethodError` is a stack-frame error."** Incorrect in most cases; check method descriptors/runtime ABI.

**"Just add `--add-opens` and all JDK 17/21 errors vanish."** Incorrect; this does not fix the verifier or missing methods/classes.

**"`COMPUTE_MAXS` automatically recomputes all stack map frames."** Incorrect; you must understand `COMPUTE_FRAMES` and type hierarchy.

**"`COMPUTE_FRAMES` always succeeds on any class loader."** Not guaranteed; common-superclass lookup may not see types in the real loader/module.

**"Agent loaded means instrumentation is right."** Incorrect; loaded classes, matchers, helper visibility, and behavior still require verification.

**"Just test one agent by itself."** Insufficient if production runs multiple transformers.

**"Files in `target/classes` are the final artifact."** Not guaranteed after shading/repackaging/instrumentation.

**"A JAR with the right dependency name is definitely the right version."** Incorrect; resolved version, checksum, class loader, and deployment evidence are required.

**"Same class name in class loaders means same type identity."** Incorrect; the defining loader is part of runtime identity.

**"Turning off coverage/APM makes the build green so migration is done."** Incorrect if those are mandatory quality/operational gates.

**"The error happened when calling the new feature, so the new feature must be buggy."** Not necessarily; the JVM may simply have loaded the class at that moment and caught bytes from an old transformer.

## 44. Checklist before finalizing the fix

- [ ] Saved the full first error, `Caused by`, and stack trace.
- [ ] Identified the exact error subtype: VerifyError, ClassFormatError, NoClassDefFoundError, etc.
- [ ] Recorded JDK vendor/build, OS/architecture, artifact, and actual JVM flags.
- [ ] Identified class-file major/minor version of the failing class.
- [ ] Identified the actual class/JAR/module/loader containing the loaded bytes.
- [ ] Checked API method/field descriptors if it is a linkage error.
- [ ] Found the initialization cause if `Could not initialize class` appeared.
- [ ] Reviewed classpath/module path, BOM, and dependency resolution.
- [ ] Checked shading, fat JAR, and MRJAR branch selection if applicable.
- [ ] Inventoried all Java/native agents and bytecode transformers.
- [ ] Distinguished JVM verifier errors from ASM/Byte Buddy parser errors.
- [ ] Inspected `bci`, stack state, branch targets, exception handlers, and `StackMapTable` if VerifyError.
- [ ] Checked `max_stack`/`max_locals` and constructor constraints when fixing a transformer.
- [ ] Checked helper class visibility, class-loader, and module access.
- [ ] Checked vendor-supported tool/agent versions on the target JDK.
- [ ] Confirmed original and transformed bytes are not confused.
- [ ] Did not use `-noverify` or unconditionally relax module/security policies.
- [ ] Attempted reproduction in staging with/without each agent if permitted.
- [ ] Ran regression tests on the final artifact and real runtime image.
- [ ] Checked observability/coverage and performance after the fix.
- [ ] Incident report includes artifact hash, owner, evidence, and release decision.

## 45. References to cross-check

When dealing with a specific JVM or bytecode library, prioritize documentation for **the exact release**:

- **Java Virtual Machine Specification**, chapters on class-file format, verification, loading/linking/initialization, and `invokedynamic`.
- **Java SE API — `java.lang.VerifyError`, `LinkageError`, `ClassFormatError`, `NoClassDefFoundError`, `ClassNotFoundException`**.
- **Java Instrumentation API — `Instrumentation` and `ClassFileTransformer`**, along with the Java agent manifest specification.
- **ASM User Guide and release notes** on `ClassReader`, `ClassWriter`, `COMPUTE_FRAMES`, `CheckClassAdapter`, and class-file version support.
- **Byte Buddy documentation/release notes** on agents, Advice, redefinition, and supported JDK versions.
- **JaCoCo, Mockito, APM vendor documentation** on test/coverage instrumentation and JVM/bytecode compatibility.
- **`javap`, `jdeps`, `jar`, and `java` tool guides** for inspecting bytes, dependencies, MRJAR variants, and class-loading diagnostics.
- **JPMS documentation** on `requires`, `exports`, `opens`, and module access.
- **Gradle/Maven compiler, toolchains, shading, and test plugin docs** for determining actual pipeline output.
- **OpenJDK JEP 451** if the incident involves dynamic agent loading on JDK 21 onward, without confusing it with verification.

Any rules regarding JVM flags, diagnostic tags, and bytecode parser versions may change by JDK or library. Fixes must be verified in **the actual deployed version combination**, not merely in examples from older documentation.

## 46. Conclusion

**`VerifyError` is the signal that the verifier rejected bytecode**, whereas class loading, method/field linkage, class initialization, module access, and bytecode parser errors typically reflect different layers of the JVM and tooling. These errors can appear simultaneously during Java Advance Compatibility Migration, especially when upgrading the JDK alongside ASM/Byte Buddy, Java agents, mocking/coverage tools, code generators, or build-time enhancers.

To diagnose properly, start from **the first error and the actual loaded class**, then cross-check class-file version, method descriptors, operand stack, local variables, control flow, and `StackMapTable` as needed. If code was transformed, analyze the final bytes and entire transformer pipeline; if a class/method is missing, investigate dependency resolution, shading, loaders, and module boundaries; if a parser does not understand a new Java release, upgrade the right tool according to support policy.

Do not disable bytecode verification just to "get the app running". A safe migration must prove that **the final artifact loads on the target JVM, instrumentation works properly, data/behavior do not regress, and test/quality gates remain intact**. When errors are fixed at the right layer and can be reproduced with the exact JDK, JAR, agent, and runtime image, upgrading to a new Java version has a reliable operational foundation.
