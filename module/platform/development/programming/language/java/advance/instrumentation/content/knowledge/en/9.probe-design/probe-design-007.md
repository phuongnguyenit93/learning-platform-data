# Injecting Code into a Constructor After `this` Has a Valid State

## 1. Objectives and Key Takeaways

In Java Instrumentation, adding measurement code to a **constructor** (a bytecode method named `<init>`) is harder than adding it to a regular method. At the beginning of a constructor, the reference to the object being created is **not yet considered by the JVM to be a fully initialized instance**. If a transformer inserts instructions that read fields or call methods on `this` at the wrong time, the class can be rejected with a `VerifyError`. Even when the JVM accepts the bytecode, **the object's business state may still be incomplete**, especially when `final` fields, field initializers, constructor delegation, or inheritance are involved.

This lesson clarifies two distinct requirements:

1. **Valid according to the JVM verifier:** use `this` as an initialized instance reference only at bytecode points where it is permitted.
2. **Valid according to the application lifecycle:** collect or publish state only when the fields needed by the measurement have already been set, and do not accidentally let `this` escape to another thread before the object finishes construction.

Those two moments **do not necessarily coincide**. For example, immediately after a superclass constructor returns, `this` may already be usable according to the verifier, yet the subclass has not yet assigned its own fields. A "constructor-return" hook on the parent class also does not prove that an instance of a subclass is complete.

### Learning Outcomes

After this lesson, you can:

- explain `uninitializedThis` and the role of `invokespecial <init>`;
- distinguish calling `super(...)` from `this(...)` and identify duplicate-measurement risks;
- choose a probe placement **after the initialization call** or **right before `RETURN`**, depending on the goal;
- avoid using `this` in a constructor when it is not yet valid and avoid reading fields before assignment;
- distinguish a normal return from an exception path;
- implement/read a transformer pattern based on ASM `AdviceAdapter`;
- test a Java 17+ program with inheritance, field initializers, constructor chaining, and exceptions.

## 2. Object Construction Lifecycle: Three Distinct Stages

Consider:

~~~java
class Base {
    Base() { /* Base's body */ }
}

class Child extends Base {
    String label = "field-init";
    final String id;

    Child(String id) {
        super();
        this.id = id;
    }
}
~~~

Conceptually, when running `new Child("ready")` on Java 17:

~~~text
Object allocation:
    label = null, id = null          (default field values)
        |
        v
Child.<init>(String) starts:
    this has not yet completed the initialization step according to the verifier
        |
        v
invokespecial Base.<init>()
    Base initializes Base's part and runs Base's body
        |
        v
Base.<init>() call returns normally
    this can be used according to applicable verifier rules
        |
        v
Child's field initializer runs
    label = "field-init", id = null
        |
        v
Child constructor body continues
    id = "ready"
        |
        v
RETURN of Child.<init>(String)
    Child(String) constructor completes normally
~~~

### 2.1. "Initialized According to the Verifier" Does Not Mean "Complete State"

The JVM verifier cares about **bytecode type safety**. For instance, before an appropriate initialization call, the local 0 reference has a special verifier state; it cannot be freely used like a normal reference. After the initialization call on the same instance returns normally, the verifier state changes.

The application cares about **invariants**: whether `id` is already non-`null`, whether a collection has been created, whether dependencies have been assigned, or whether configuration has been validated. The JVM does not infer these business invariants automatically.

Therefore:

| Measurement Point | Is `this` valid as an initialized object per the verifier? | Is application state complete? | Appropriate Purpose |
|---|---|---|---|
| Before the appropriate `super/this` initialization call | **Must not be assumed** | Not yet | Measure only using data that does not require `this`, if bytecode and stack frames allow |
| Immediately after the appropriate initialization call returns | Usable per the verifier | **Not necessarily**; field initializers/body of the current class may not have run yet | Count/record technical events, do not read all fields |
| Middle of the constructor body | Usually yes, if after the initialization call | Depends on assignment order | Read only fields already assigned, avoid assuming the entire object is ready |
| Right before `RETURN` of `<init>` | Yes, if the return is valid | Current constructor completed **normally** | Success hook for a specific constructor |
| `RETURN` of a superclass constructor | Yes for the parent constructor | Subclass may not be initialized yet | Do not treat as completion of the entire dynamic object |
| Before `ATHROW` or inside an exception handler | Depends on whether a valid initialization call has been passed | May be incomplete | Do not use `this` unless state can be proven; separate failure hook |

**Measurement points should be based on the preconditions of the measurement**, not merely on a callback reporting "entered constructor".

## 3. Bytecode Rules: `uninitializedThis` and `invokespecial`

### 3.1. A Constructor Is Not a Regular Method

On the JVM, a Java constructor is represented by an instance initialization method named **`<init>`** with a `void` return type; constructors are not inherited like regular methods. When the class verifier analyzes a constructor's code, **local 0** initially usually carries the verification type **`uninitializedThis`**.

Before the initialization call on the same instance succeeds, `uninitializedThis` cannot be treated as a normal reference to:

- arbitrarily invoke instance methods;
- pass directly as `Object` to a probe such as `Probe.observe(Object)`;
- arbitrarily read instance fields;
- publish a reference to an incomplete object.

Special operations used to carry out initialization, such as `invokespecial` to an appropriate `<init>`, and certain field assignments constrained by the specification, must be analyzed according to verifier rules; one must not infer that every `ALOAD 0` operation is valid for every purpose.

An **illustrative-only** bytecode sketch, not a full disassembly output:

~~~text
aload_0
invokespecial #Base.<init>:()V     ; initialize superclass
; FROM HERE operations requiring an initialized reference can be performed
aload_0
ldc "value"
putfield #Child.id:Ljava/lang/String;
return
~~~

If you add:

~~~text
aload_0
invokestatic #Probe.observe:(Ljava/lang/Object;)V
~~~

**before** the appropriate initialization call, the JVM may reject the class because the probe's receiver is not a valid initialized `java/lang/Object` at that point. Avoid the approach of "inserting before the first instruction of `<init>`" using a visitor written for regular methods.

### 3.2. Do Not Just Look for "the First `invokespecial` Instruction"

`invokespecial` is used for multiple cases (constructors, private methods, special invocations) and can appear for **another object** while computing constructor arguments. A class may execute `new Helper()`, call `Helper.<init>` to prepare an argument, and only then call `super(...)`; that **does not make `this` initialized**.

When instrumenting a constructor:

1. Identify the **`<init>` call whose receiver is `uninitializedThis` itself**, not just any `invokespecial <init>`.
2. Treat the object's own constructor as having passed the initialization call only when that instruction **completes normally**.
3. If the bytecode has branches or exception handlers, track verifier frames/stack accurately rather than guessing based on textual position.
4. Use a constructor-aware adapter/framework instead of manually inserting instructions when state cannot be analyzed.

ASM `AdviceAdapter` supports identifying this phase; it should not be replaced by checking "first opcode equals `INVOKESPECIAL`" without conditions on the receiver and control flow.

### 3.3. What If `super()` Throws an Exception?

If the parent constructor call throws an exception, the object **does not become normally initialized** merely because the `invokespecial` opcode executed. Verifier rules for exception edges treat a partially initialized object as no longer usable. A hook on the exception path **must not use `this` as a complete object**.

Therefore, do not write a catch-all handler covering the region before `super()` and then use `ALOAD 0` to call a probe taking `Object` inside that handler. If you need to log errors, use safe information such as the class name or an error code; catching exceptions after the init phase needs separate evaluation.

## 4. Constructor Chaining, Inheritance, and Field Initializers

### 4.1. `super(...)` and `this(...)` Differ in Lifecycle

- `super(...)` calls the parent class constructor. When the superclass constructor returns, the subclass's fields and body may **not have been processed yet**.
- `this(...)` delegates to another constructor **in the same class**. The called constructor executes down the chain; after it returns, the delegating constructor continues the rest of its body.
- Each `<init>` constructor is a separate method at the bytecode level; each method has its own `RETURN`.

Example:

~~~java
Child() {
    this("ready");       // Delegate to Child(String)
    // Return after Child(String) returns
}

Child(String id) {
    super();
    this.id = id;
}
~~~

If a transformer inserts "success" before **every `RETURN` of every constructor**, a single `new Child()` may record **two success events**: one in `Child(String)` and one in `Child()`. If inheritance is also involved, the parent class constructor may record its own event as well.

**Counting completed constructors does not necessarily equal counting newly allocated objects.** For metrics needs, you must clearly define whether you are measuring constructor invocations, completed object creations, or factory operations.

### 4.2. Field Initializers Do Not Necessarily Appear Right After `super` in Source

In Java 17, the compiler typically emits instructions executing **instance field initializers and instance initializer blocks** after the superclass constructor call completes, before the remaining body of a non-delegating constructor. Thus, placing a probe in **bytecode immediately after `invokespecial super.<init>`** may run **before** initializers that the source code shows at the top of the class.

For example, `String label = "field-init";` may not yet be assigned in bytecode immediately after `super.<init>`, even though the field declaration line in source precedes the constructor declaration.

A hook placed at the **beginning of the constructor body in Java source**, on the other hand, can observe `label="field-init"` because the compiler inserted the field initializer before that body code. Do not equate these two measurement points.

### 4.3. A Parent Class Cannot Assume the Subclass State Is Complete

When the `Base` constructor runs, the actual object may be an instance of `Child`; `Child`'s fields are still at their default values. If the parent class calls a virtual method overridden in the subclass, the overridden code may read unready state. Avoid implementing a post-`super()` probe by calling an instance method that can be overridden.

If you need to observe the object during construction, prefer **measuring safe scalars** or a static probe that does not retain the reference. Do not push `this` into a queue, thread, registry, external callback, or shared state structure before invariants are satisfied.

## 5. Runnable Java 17 Demo: Observing Each Initialization Phase

The following example is **complete Java code**, with no ASM dependency. It simulates the positions where a probe can be placed using explicit calls, helping you see the **actual state**; afterward we use `javap` to inspect the corresponding bytecode.

File **`ConstructorProbeDemo.java`**:

~~~java
public class ConstructorProbeDemo {
    static class Base {
        Base() {
            Probe.log("base-body", this);
        }
    }

    static final class Child extends Base {
        String label = "field-init";
        final String id;

        Child() {
            this("ready");
            Probe.log("delegating-exit", this);
        }

        Child(String id) {
            super();
            Probe.log("child-body-start", this);
            this.id = id;
            Probe.log("target-exit", this);
        }
    }

    static final class Fragile extends Base {
        Fragile(boolean fail) {
            super();
            if (fail) throw new IllegalArgumentException("boom");
            Probe.log("fragile-exit", this);
        }
    }

    static class Probe {
        static void log(String stage, Base object) {
            if (object instanceof Child child) {
                System.out.println(stage + ": label=" + child.label
                        + ", id=" + child.id);
            } else {
                System.out.println(stage + ": other");
            }
        }
    }

    public static void main(String[] args) {
        new Child();
        try {
            new Fragile(true);
        } catch (IllegalArgumentException expected) {
            System.out.println("caught:" + expected.getMessage());
        }
    }
}
~~~

**Compile and check with the verifier** (JDK 17 or later):

~~~bash
javac --release 17 ConstructorProbeDemo.java
java -Xverify:all ConstructorProbeDemo
~~~

**Verified stdout:**

~~~text
base-body: label=null, id=null
child-body-start: label=field-init, id=null
target-exit: label=field-init, id=ready
delegating-exit: label=field-init, id=ready
base-body: other
caught:boom
~~~

**Explanation of the six lines:**

1. `base-body`: the parent constructor can already pass `this` to the static `Probe.log`, yet `Child`'s fields are still `null`. This clearly demonstrates **parent-level initialized ≠ subclass-level fully initialized**.
2. `child-body-start`: in `Child(String)`'s source, `label`'s initializer has already executed, but `id` has not yet been assigned.
3. `target-exit`: near the end of the constructor, `id="ready"`.
4. `delegating-exit`: the `Child()` constructor continues after `this("ready")` returns; there is still only one object, but there are **two constructor exit points**.
5. `base-body: other`: the parent constructor is also called during the creation of `Fragile`.
6. `caught:boom`: `Fragile` throws an exception; **there is no `fragile-exit`** because the success path does not execute.

**Limitations of the demo:** The `Probe.log` calls are source code placed at points permitted by Java; it does not inject itself into other classes' bytecode. The example uses `instanceof Child` to read unready fields **only in a single-threaded test environment** to illustrate the risk. Do not copy publishing `this` during an incomplete phase into production applications.

### 5.1. Using `javap` to See the Exact Bytecode

After compiling, run:

~~~bash
javap -c -p 'ConstructorProbeDemo$Child'
~~~

On Bash, single quotes protect the `$` character so the shell does not interpolate it. In PowerShell, single quotes also preserve the nested class name string literally.

Key instructions in the **`Child(String)`** constructor:

~~~text
0: aload_0
1: invokespecial ... Base."<init>":()V
4: aload_0
5: ldc           ... String field-init
7: putfield      ... Field label:Ljava/lang/String;
10: ldc          ... String child-body-start
...
16: aload_0
17: aload_1
18: putfield     ... Field id:Ljava/lang/String;
...
27: return
~~~

The `...` ellipses merely represent shortened constant-pool indices and comments; this is a **selective instruction excerpt**, not verbatim output for copy-pasting into an assembler. From it, you can clearly see the instruction assigning `label` appears **after** `Base.<init>` yet **before** the `child-body-start` call in source.

The **`Child()`** constructor begins with `invokespecial ... Child."<init>":(Ljava/lang/String;)V` and has its own `return`. That is precisely why a probe at the end of every `<init>` can count twice for a single object creation.

### 5.2. Counter-Example Check

If you move `Probe.log("target-exit", this)` above `this.id = id`, Java still compiles because the probe is called **after `super()`**, but the output will print `id=null`. There is no `VerifyError`, yet the "object is ready" measurement is **semantically wrong**.

This reinforces the conclusion: passing the verifier is only a **necessary condition**, not proof that the object already satisfies the desired invariants.

## 6. Where to Place Probes for the Right Purpose?

| Need | Common Insertion Point | Should `this` Be Read? | Caveats |
|---|---|---|---|
| Count **constructor entries** | Static counter at a safe point, or measure at the call-site | Not needed | Does not cause verifier errors; constructor chaining can produce multiple counts |
| Know when **`super`/`this` initialization call succeeded** | Hook after the verified initialization call | Possible, but **do not read uninitialized state** | Field initializers and body may still be about to run |
| Measure **a constructor completing normally** | Right before `RETURN` of that `<init>` | Possible under valid frame conditions | Multiple constructors may run for a single object |
| Measure an object of a **specific class** with fields assigned | After the required field assignments, or before `RETURN` of that class's constructor | Only when state is truly ready | Do not generalize to incomplete subclasses |
| Measure **objects actually finished creating** at a call-site | After allocation + constructor returning successfully at the call-site | Possible, if the reference is already valid | Does not cover objects created elsewhere |
| Count **failed constructors** | Guard/exception path after an appropriate initialization call; consider call-site | Usually not needed | `ATHROW` does not cover every error thrown from nested calls |
| Attach end-to-end timing | Combine a valid start point and all exit paths to measure | Usually no object reference needed | Avoid altering constructor behavior if the probe fails |

**There is no single insertion point that is universally right for every measurement.** The designer must clearly decide the unit of measurement: **per `<init>`**, **per initialization of a class type**, **per factory call**, or **per allocation site**.

## 7. Bytecode Injection with ASM `AdviceAdapter`

ASM is a library outside the JDK, commonly used in Java agents to visit and generate bytecode. The **`asm-commons`** module provides `AdviceAdapter`, an adapter that understands when a constructor invokes its initialization method, making it safer to implement hooks than inserting opcodes at the very start of the method.

According to the `AdviceAdapter` documentation:

- `onMethodEnter()` is called at the start of a regular method, or **after the appropriate initialization call** in a constructor.
- `onMethodExit(int opcode)` is called before a method-exiting instruction such as `RETURN` or `ATHROW`.
- The adapter tracks the operand stack to recognize the initialization step, rather than relying on "the first `invokespecial`".
- The callback does not automatically know the object's business invariants. Being after `super(...)` still does not mean all fields are ready.

### 7.1. Visitor Pattern for Inserting a Success Hook Before `RETURN`

The example below is **a complete helper class for ASM 9.x**, but **not a standalone Java 17 program using only the JDK**: you must add compatible `org.ow2.asm:asm` and `org.ow2.asm:asm-commons` libraries, and have the `demo.ConstructorMetrics` class on a classpath loadable by the target loader.

~~~java
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.commons.AdviceAdapter;

public final class ConstructorWeaver {
    public static byte[] instrument(byte[] original) {
        ClassReader reader = new ClassReader(original);
        ClassWriter writer = new ClassWriter(
                reader, ClassWriter.COMPUTE_MAXS);

        ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
            private String owner;

            @Override
            public void visit(int version, int access, String name,
                    String signature, String superName,
                    String[] interfaces) {
                owner = name;
                super.visit(version, access, name,
                        signature, superName, interfaces);
            }

            @Override
            public MethodVisitor visitMethod(int access, String name,
                    String descriptor, String signature,
                    String[] exceptions) {
                MethodVisitor mv = super.visitMethod(
                        access, name, descriptor,
                        signature, exceptions);

                if (mv == null || !"<init>".equals(name)) {
                    return mv;
                }

                return new AdviceAdapter(
                        Opcodes.ASM9, mv, access, name, descriptor) {
                    @Override
                    protected void onMethodExit(int opcode) {
                        if (opcode != Opcodes.RETURN) {
                            return;
                        }

                        // No ALOAD 0 needed: avoid leaking this.
                        visitLdcInsn(owner.replace('/', '.'));
                        visitMethodInsn(
                                Opcodes.INVOKESTATIC,
                                "demo/ConstructorMetrics",
                                "completed",
                                "(Ljava/lang/String;)V",
                                false);
                    }
                };
            }
        };

        reader.accept(visitor, ClassReader.EXPAND_FRAMES);
        return writer.toByteArray();
    }
}
~~~

**Logical result**: before each `RETURN` of a constructor, the callback inserts the call:

~~~java
demo.ConstructorMetrics.completed("class.Name");
~~~

The line above only illustrates the **bytecode effect**, not Java source automatically generated in the target class. The probe receives the class name instead of `this`, reducing the risk of object escape, invariant dependency, and unintended reference retention.

A simple measurement helper (which must be placed where the application's class loader can find it) can be:

~~~java
package demo;

import java.util.concurrent.atomic.LongAdder;

public final class ConstructorMetrics {
    private static final LongAdder COMPLETED = new LongAdder();

    public static void completed(String className) {
        COMPLETED.increment();
    }

    public static long count() {
        return COMPLETED.sum();
    }
}
~~~

**Do not automatically interpret `COMPLETED` as the number of unique objects.** With `this(...)` constructor chaining or when instrumenting both parent and child classes, the measurement may record multiple times for one object. If you need to distinguish them, you must clearly specify which constructors/entry points are instrumented and the unit of measurement.

### 7.2. When Should `onMethodEnter()` Be Used?

If the goal is to place a technical probe **immediately after the initialization call**, `AdviceAdapter.onMethodEnter()` is the right place in a constructor-aware transformer. However, **do not read all fields of `this` here**; field initializers and the body may still not have run.

A logical snippet for a very lightweight hook:

~~~java
@Override
protected void onMethodEnter() {
    // Only record a metric that does not depend on fields of this.
    visitMethodInsn(
            Opcodes.INVOKESTATIC,
            "demo/ConstructorMetrics",
            "constructorPhaseReached",
            "()V",
            false);
}
~~~

**This is an excerpt** placed inside an `AdviceAdapter` subclass and does not run standalone; the `ConstructorMetrics.constructorPhaseReached()` method must be implemented separately if using this pattern. If you need to observe `this`, use it only after the adapter determines the reference is initialized per the verifier, while also ensuring appropriate invariants yourself.

### 7.3. Technical Details When Integrating an Agent

1. **Do not just add ASM to source:** you must build, package, and make the dependency libraries loadable in the agent context. Do not rely on internal ASM `jdk.internal.org.objectweb.asm` via `--add-exports` as a production solution.
2. **Do not blindly inject hooks into every class:** filter by `className`, loader, and module, and avoid instrumenting agent classes, metrics helpers, and JVM core classes to prevent recursion or deadlocks.
3. **Preserve verifier-correct bytecode:** a simple example adding `invokestatic` before `RETURN` only increases stack usage and uses `COMPUTE_MAXS`. When changing control flow, handlers, or frames, you may need `COMPUTE_FRAMES` and a strategy to resolve superclasses from the right class loader. Do not assume frame computation is harmless in every runtime.
4. **Stack at `RETURN`:** constructors return `void`, so `RETURN` has no return value on the stack. If adding code before `ATHROW`, the operand stack contains the throwable and must preserve the stack state properly.
5. **When retransforming:** the same `Instrumentation` limits apply—do not arbitrarily change fields, methods, or class hierarchy, and guard against duplicate instrumentation.
6. **Helper methods can throw exceptions:** if a probe throws an error before `RETURN`, it can turn a constructor that would have succeeded into a failure. Hot paths must be extremely safe, measured for overhead, and avoid blocking I/O.

### 7.4. Measuring When a Constructor "Completes" Does Not Mean the Subclass Is Complete

Even the ASM pattern that only inserts before `RETURN` **does not prove the object is complete at every inheritance level**. The `Base.<init>` constructor can `RETURN`, and then `Child.<init>` processes its fields and may even throw an error. Therefore, this metric should be named **constructor invocation completed** for a specific class/descriptor, rather than **object created successfully** if that cannot be proven.

## 8. Constructor Exceptions: Normal Path and Exceptional Path

### 8.1. `RETURN` vs. `ATHROW`

- **`RETURN`** in a constructor represents the normal exit path of that `<init>` method itself.
- **`ATHROW`** represents an explicit throwable-throwing instruction at that location, but **not every exception exiting a method passes through an `ATHROW` located inside that method**.
- Exceptions can originate from calling another method, field initializers, superclass constructors, array accesses, or VM checks and propagate outward without passing through an `ATHROW` emitted by the constructor's own code there.

A visitor that only invokes `onMethodExit` before the `ATHROW` opcode may **miss some exception paths**. To measure failures comprehensively, you need a try/catch/finally covering the permitted region while preserving verifier state, or measure at the **call-site/factory** if the goal is success/failure of the entire object creation process.

### 8.2. Do Not Use `this` If `super` Has Not Returned Normally

If an exception occurs **before or during superclass initialization**, the `uninitializedThis` state must be handled according to verifier and exception stack frame rules. A newly added handler must not use `ALOAD 0` as an initialized receiver merely because that code "runs at the end of the method".

For failure hooks, prefer passing **class name, descriptor, exception category, or timestamp**, rather than an object reference that is not guaranteed to be valid. When you are certain it is after the initialization step and want to measure state, you still need to check business invariants.

### 8.3. Do Not Let the Probe Become the Cause of Failure

A normal constructor:

~~~text
new Customer(...) --> init fields --> RETURN --> valid object
~~~

If a probe is inserted before `RETURN`:

~~~text
new Customer(...) --> init fields --> Probe.report(...)
                                    |
                                    +--> report throws exception
                                            |
                                            v
                                   constructor does not RETURN
~~~

Therefore, calling a probe from a constructor must be designed to be **unlikely to throw**, avoid business logic or synchronous network exports, and have an appropriate fallback strategy. An "observing" hook that alters initialization outcomes is a significant instrumentation bug.

## 9. Situations Requiring Extra Caution

### 9.1. Record Constructors

Records have canonical constructors and may use compact constructors. Record fields are assigned by the compiler according to language rules; **do not infer when each field is written solely from source position**. If you need to measure complete record state, inspect the compiled `<init>` bytecode, read fields only after they are assigned, and prefer an appropriate normal exit.

### 9.2. Enum and Compiler-Generated Constructors

Enum constructors have compiler-generated parameters/bytecode details beyond the parameters appearing in source. Do not hardcode the assumption "constructors always have descriptor `()V`". Match by the `<init>` name and actual descriptor, and verify the loader/bytecode version. Framework-generated classes may also contain synthetic constructs.

### 9.3. Constructors with Multiple Paths

Java source can have conditional branches and throws. Bytecode `RETURN` instructions must be handled consistently if the goal is counting success—do not place a hook at a single source point and miss other paths. For control-flow changes, test stack map frames, exception tables, and the verifier.

### 9.4. JDK 25 and Flexible Constructor Bodies

Starting in **JDK 25**, JEP 513 makes **Flexible Constructor Bodies** a standard feature: Java source can contain certain statements **before** `super(...)` or `this(...)`. The early construction context still imposes **strict restrictions** on referencing the instance being created; certain field assignments are permitted, but you cannot arbitrarily read `this` or call instance methods before the appropriate initialization call.

Consequently, do not write an absolute rule "all statements before super are forbidden by Java" across all modern JDKs. The safe instrumentation rule remains: **rely on the verifier state and actual initialization path, not on the length of the constructor prologue or an assumed instruction order**. The Java 17 example in Section 5 uses Java 17 source rules and was compiled with `--release 17`.

### 9.5. Instrumentation Must Not Cause `this` to Escape

Avoid:

~~~java
static void unsafeRegister(Object thisObject) {
    GlobalRegistry.put(thisObject);
    new Thread(() -> use(thisObject)).start();
}
~~~

This is an **anti-pattern**, not standalone compilable code: `GlobalRegistry` and `use` merely illustrate external systems. It publishes the reference before there is proof the object has complete state. In a multithreaded environment, the consequence is not only reading default values but also **safe publication** issues, data races, and broken invariants.

**Counting with a static counter** or recording the class name reduces risk, though you must still measure overhead and ensure the probe does not throw exceptions.

## 10. Design and Testing Checklist

### 10.1. Before Writing the Transformer

- [ ] Clearly define whether you are measuring **per constructor**, **per complete object**, or **call-site/factory**.
- [ ] List constructors with `super(...)`, `this(...)`, inheritance, and overloads.
- [ ] Inspect actual bytecode with `javap -c -p`, rather than inferring from source.
- [ ] Determine whether every field needed for measurement has been assigned at the hook point.
- [ ] Verify that parent class constructors can run before any subclass initialization.
- [ ] Distinguish normal return from exceptional exit, avoiding counting failed creations as successes.
- [ ] Choose a library/adapter that understands the `uninitializedThis` verifier frame.
- [ ] Do not require helpers to retain references to invalid objects.
- [ ] Distinguish where helper code is loaded and the target class's classloader/module path.

### 10.2. After Transforming the Class

- [ ] The generated classfile is verified by the JVM; use `java -Xverify:all` in an isolated test.
- [ ] No `VerifyError`, `ClassFormatError`, or `NoClassDefFoundError` due to unloadable helpers.
- [ ] Constructor branches, `this(...)`, and `super(...)` preserve their exact semantics.
- [ ] The success hook runs **for the exact unit** defined (constructor invocation or object count).
- [ ] When a constructor throws, the success hook does not run erroneously.
- [ ] When a superclass constructor throws, `this` is not used in an invalid exception handler.
- [ ] The probe does not throw exceptions, hold locks too long, or cause recursion.
- [ ] Verify superclass/subclass state with field initializers and `final` fields.
- [ ] Test on the target Java 17+ runtime, bytecode version, and multiple classloaders if applicable.
- [ ] Measure hot-path overhead; rate-limit logs and do not prolong construction time.

## 11. Common Errors and Diagnostics

| Symptom | Common Cause | Recommendation |
|---|---|---|
| `VerifyError` when inserting at the start of `<init>` | Probe uses `this` while the verifier still treats it as `uninitializedThis` | Wait for the initialization call on `this` to complete; use a constructor-aware adapter |
| `this` is valid but fields are still `null` | Field initializers/body have not run yet, or superclass is initializing a subclass object | Choose a measurement point after required field assignments; do not equate verifier state with invariants |
| Metric increments twice when creating one object | `this(...)` delegation is present; each constructor has a `RETURN` | Redefine the unit of measurement, select the appropriate constructor, or measure at the call-site |
| Metric increments even when the object ultimately fails to create | Hook is at superclass return, but subclass constructor throws an exception | Do not call it "object created"; measure after full construction |
| Hook fails to catch all errors | Only intercepts the `ATHROW` opcode, missing exceptions from other calls | Design an exception handler over the proper region or hook at the call-site |
| Surprises when instrumenting generated classes | Constructor descriptor differs from expectation, synthetic code present | Rely on bytecode `<init>`/descriptor and actual verifier behavior |
| Classloader error when calling helper | Instrumented class cannot find `ConstructorMetrics` | Place helper in an appropriate loader/module and handle visibility |
| Probe method prevents app from starting | Helper throws exceptions, causes deadlock, or class loading recursion | Minimize dependencies, avoid blocking operations, add error fallbacks |
| Stack map frame error after adding a branch | Incorrectly updated frames/max stack | Use the right ASM compute strategy, verify with JVM verifier and check control flow |
| Parent constructor calls override and reads unassigned child field | Dynamic dispatch occurs during construction | Avoid calling overridable instance methods in early hooks |

To diagnose errors, first identify the **opcode and frame** where the JVM reports the error, the constructor descriptor, the parent class, and the `super/this` path, then compare bytecode before and after transformation. If the stack trace reports `VerifyError: Bad type on operand stack`, especially check the flow of `uninitializedThis` through instructions passing arguments or calling static/instance probes.

## 12. Exercises and Self-Assessment Questions

### Exercise A — Predict Output Before Running

For `ConstructorProbeDemo`, predict the values of `label` and `id` at `base-body`, `child-body-start`, `target-exit`, and `delegating-exit`. Verify using the `javac --release 17` and `java -Xverify:all` commands in Section 5.

**Answer:** the value pairs in order are `(null, null)`, `("field-init", null)`, `("field-init", "ready")`, `("field-init", "ready")`.

### Exercise B — Per-Constructor vs. Per-Object Measurement

Suppose you instrument **both** `Child()` and `Child(String)` with a success hook at `RETURN`. When running `new Child()`, how many hooks fire? **Two**. Why is there still only one object? Because `this(...)` invokes the other constructor on the same instance.

Extending this to superclass `Base` also having a hook: if Base's constructor is also counted, there will be one more success event for this `Child` creation. Rename the metric to `constructor_return_count` to avoid misinterpreting it as `allocated_objects_count`.

### Exercise C — Observing Valid `this` with Unready State

Move the `Probe.log("target-exit", this)` call above `this.id = id`. Java can compile, but the data differs. How does that prove **verifier correctness and semantic correctness are different**?

### Exercise D — Choosing a Measurement Point for Constructor Errors

Add `throw new IllegalArgumentException("boom")` after `super()`, then try inserting a success probe before `RETURN` and a probe before `ATHROW`. Why does `ATHROW` only cover a subset of cases? Point out an error from another constructor call that can propagate without a corresponding `ATHROW` in the current constructor's bytecode.

### Exercise E — Detecting Misplaced Insertion

A transformer finds **the first `INVOKESPECIAL` opcode in `<init>`** and inserts `ALOAD 0` + `Probe.observe(Object)` right after it. Explain why this can be wrong if that instruction only initializes **another object**, while `super(...)`/`this(...)` on the instance itself has not executed yet.

### Quick Check Questions

1. **Why can `ALOAD 0` + calling a static hook taking `Object` before `super/this` be rejected?** — Because the verifier does not yet treat `uninitializedThis` as a normal reference.
2. **After `super(...)`, are all subclass fields assigned yet?** — Not necessarily.
3. **When does `AdviceAdapter.onMethodEnter` run in a constructor?** — After the initialization call tracked by the adapter; not at the very first bytecode instruction.
4. **Does inserting before `RETURN` guarantee the subclass object is ready?** — No, if the hook is in a superclass; furthermore, constructor chaining has multiple returns.
5. **Does `onMethodExit(ATHROW)` catch every exceptional exit?** — No, exceptions can originate from other instructions/calls.
6. **When a probe does not use `this`, are there still risks?** — Yes: classloader issues, exceptions from the probe, overhead, recursion, and miscounted metric units.
7. **Does JDK 25 allow some code before `super(...)` in source?** — Yes, with early construction context restrictions; `this` cannot be used freely.
8. **What is the final check to avoid verification errors?** — Disassemble, use the target JVM's verifier, test constructor chaining/exceptions, and compare bytecode before/after.

## 13. Summary

**The most important design rule:** when injecting instrumentation into a constructor, **do not use `this` as an initialized object before the appropriate initialization call on that instance completes**. After that point, **continue evaluating business state completeness**: field initializers, constructor bodies, `this(...)` delegation, and superclass/subclass relationships make "initialized per the verifier" different from "ready".

If you need to **count constructors completing normally**, insert a lightweight probe right before `RETURN` of the selected constructor, without intercepting `ATHROW` as success. If you need to **count complete objects**, you must define a point after the entire initialization chain, which may be more appropriate at the call-site/factory. Whether using ASM `AdviceAdapter` or another tool, testing actual bytecode, stack map frames, exception paths, and classloaders is the ultimate proof.

### Official References

- [Java SE 17 JLS `12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): order of superclass constructor, instance initializers, constructor body, and dispatch during object creation.
- [Java SE 17 JVMS `4.10.1.9 — Type Checking Instructions](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.10.1.9): verifier rules for `uninitializedThis`, `invokespecial`, and exception edges.
- [ASM 9.x — AdviceAdapter](https://asm.ow2.io/javadoc/org/objectweb/asm/commons/AdviceAdapter.html): callbacks after initialization call and before `RETURN`/`ATHROW`.
- [JDK 25 — Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/25/language/flexible-constructor-bodies.html): early construction context and Java source rules before `super(...)` or `this(...)`.
- [JEP 513 — Flexible Constructor Bodies](https://openjdk.org/jeps/513): milestone finalizing the language feature in JDK 25.
