# Constructor `<init>`, class initializer `<clinit>`, and the `uninitializedThis` state

> **Scope:** class file fundamentals and JVM verifier for readers/disassemblers or Java bytecode transformers. This article uses Java 17/21 as a baseline for source examples; the names `<init>`, `<clinit>`, and `uninitializedThis` are JVM-level concepts, not Java method names that can be called in source code.

## 1. Three concepts that must not be conflated

| Concept | Where is it? | When does it execute? | Role |
|---|---|---|---|
| `<init>` | Special method **per class** in the class file, with a descriptor of the form `(params)V` | When the JVM executes a valid constructor call; typically a constructor chain runs for each `new` object | Initializes the instance part according to inheritance and constructor chaining rules |
| `<clinit>` | Special method, **at most one** per class/interface, descriptor `()V` in modern class files | When the JVM initializes the class/interface according to *active use* rules | Runs `static` field initializers and `static { ... }` blocks in order |
| `uninitializedThis` | Verification type of the `this` reference at the start of `<init>` bytecode | Exists in the verifier's type analysis before the matching `this(...)` or `super(...)` call completes | Prevents using or leaking the object reference before the constructor chain is validly established |

Note that the two uses of the word "initialization" here refer to **two different things**. *Class* initialization (`<clinit>`) is not the same as *instance* initialization (`<init>`). `uninitializedThis` is not `null`, not another object, and not a boolean flag that a Java program can inspect; it is a state type tracked by the JVM verifier.

## 2. `<init>` in the class file structure

In Java source, a constructor bears the class name and has no return type:

```java
class Account {
    private final int id;

    Account(int id) {
        this.id = id;
    }
}
```

The compiler generates a bytecode method named **`<init>`** with descriptor **`(I)V`**: an `int` parameter, returning `void` at the JVM level. Two overloaded constructors `Account()` and `Account(int)` correspond to two `<init>` methods with different descriptors (`()V` and `(I)V`); they do not override each other. `<init>` is an *instance initialization method*, not `static`, and is not called via `invokevirtual`/`invokeinterface`. Valid constructor calls use `invokespecial` on a reference that is currently in an uninitialized state.

For an instance constructor, local variable slot 0 normally holds `this`; subsequent slots hold parameters (`long`/`double` occupy two slots). The `<clinit>` method, by contrast, has no `this`. Instance field initializers and `{ ... }` blocks in Java source are placed by the compiler into the execution path of the appropriate constructor, rather than becoming `<clinit>` themselves.

### From `new` to `invokespecial`

For the expression `new Account(7)`, you can observe the following opcode pattern (illustrative; offsets/constant pool indices depend on the compilation):

```text
new           Account             ; allocate, create an uninitialized reference
dup                               ; keep a copy of the reference as the expression result
bipush        7                   ; push int argument onto the operand stack
invokespecial Account.<init>:(I)V  ; consume reference + argument, run constructor
                                   ; the reference copy left on the stack is now
                                   ; treated by the verifier as an initialized Account type
```

`new` allocates the object, and instance fields initially hold their **default values** (`0`, `false`, `null`, ...). It does **not** execute the constructor body itself. The `invokespecial ...<init>` call is what does that. On the normal path, creating an instance may also trigger class initialization before allocation.

The verifier represents the reference just created by the `new` opcode at offset `p` as `uninitialized(p)`. Meanwhile, local 0 inside an `<init>` itself starts with the special type `uninitializedThis`. Both types describe a reference not yet permitted to be used as an initialized object, but they **do not share the same origin**:

- `uninitialized(p)` is tied to a specific `new` instruction and its bytecode address.
- `uninitializedThis` is tied to the receiver of the constructor currently being verified; no `new` instruction is needed inside that constructor itself.

When `invokespecial` invokes the constructor of the right object and **returns normally**, the verifier transitions **all tracked copies** of the corresponding uninitialized reference to the initialized object type. If the constructor call throws an exception, the object must not be considered successfully initialized.

## 3. Rules for `uninitializedThis` and the `this(...)`/`super(...)` chain

Consider this Java 17/21 snippet:

```java
class Parent {
    Parent(int code) {
        System.out.println("Parent: " + code);
    }
}

class Child extends Parent {
    private final String label;

    Child() {
        this("default");
    }

    Child(String label) {
        super(10);
        this.label = label;
        System.out.println("Child: " + label);
    }
}
```

Running `new Child()` calls `Child.<init>:()V`, which delegates to `Child.<init>:(Ljava/lang/String;)V` via `this("default")`; the target constructor calls `Parent.<init>:(I)V` via `super(10)`. After the superclass call succeeds, the code sets `label` and runs the rest of the body. The printed output is:

```text
Parent: 10
Child: default
```

In the bytecode of `Child.<init>`, local 0 is initially treated by the verifier as `uninitializedThis`. At the `invokespecial` instruction with this receiver, the target constructor must belong to **the current class itself** (`this(...)`) or **the direct superclass** (`super(...)`). When that call returns normally, the verifier state is updated to the current class type. On every **normal** exit path of a constructor (except the special case of `Object`), a valid initialization chain must be established before `return`.

Before this point, `this` must not be arbitrarily treated as a normal object reference. For example, bytecode that uses `aload_0` followed by `invokevirtual` on an instance method, or passes `this` to a `static` method accepting `Object` while it is still `uninitializedThis`, will be rejected by verification. **Bytecode-level exception:** the JVM permits certain restricted operations such as `putfield` on an instance field *declared directly in the current class* before calling the superclass constructor; this does not mean fields can be read or methods can be called on `this` arbitrarily. Java 17/21 source is even stricter: the `this(...)`/`super(...)` call is the first statement of the constructor.

Be careful with the phrase "`this` is initialized after `super()`". That is a **valid state for the verifier**, not a guarantee that all subclass fields have been assigned their intended values. Instance initializers and the rest of the subclass constructor body may still be running. Do not leak `this` externally just because the verifier allows using it.

### `StackMapTable` and verification errors

In class files with stack map frames, `verification_type_info` distinguishes `ITEM_UninitializedThis` from `ITEM_Uninitialized` (the latter carries the offset of the `new` instruction). The verifier merges locals and operand stack states across branches/exception handlers. If an instrumentation tool modifies `<init>`, mechanically replaces `uninitializedThis` with `Object`, breaks the path of `invokespecial`, or creates a `return` path before proper initialization, the JVM may throw `VerifyError` when verifying the class.

In particular, an exception handler covering an `<init>` call must accurately reflect the abnormal path: a failed constructor call does **not** produce an initialized reference. Frames before and after `invokespecial` must not be merged arbitrarily.

## 4. `<clinit>`: class initialization, not an instance constructor

The compiler may synthesize `static` assignments and `static { ... }` blocks of a class into a special method `<clinit>:()V`, in **the order they appear in source**. In modern Java class files, this method is `static`; a class/interface has **at most one** `<clinit>`. Not every class needs this method: if there is no suitable runtime initialization work, the compiler may omit generating it; `static final int` or `String` constant variables are typically represented via `ConstantValue`.

Regarding *active use*, the JVM initializes a class before operations such as creating an instance, invoking a `static` method **declared in that class**, writing a `static` field, or reading a `static` field that is not a constant variable. Certain reflection operations also trigger initialization. Conversely, merely writing `SomeType.class`, declaring a variable of that type, or reading an inlined constant variable **does not by itself** force `<clinit>` to run.

For a class, the JVM initializes its superclass (and relevant superinterfaces with default methods according to specification rules) before the subclass initialization. Initialization is synchronized across threads: if another thread is currently initializing the same `Class` object, the current thread waits for the result. Once succeeded, it does not run again for subsequent `new` calls. Class identity in the JVM depends on both the **binary name** and the **defining class loader**: the same name in two different loaders can be two separate classes, each initialized separately.

When `<clinit>` fails, the class may be marked *erroneous*. For exceptions other than `Error`, the first failure is typically wrapped in `ExceptionInInitializerError`; subsequent active uses typically receive `NoClassDefFoundError`. Do not mistake this for an instance constructor failure, and do not expect a subsequent `new` to re-run `<clinit>` to recover.

## 5. Runnable example: order of `<clinit>` and `<init>`

Save all the code below as **`InitLifecycleDemo.java`**:

```java
public class InitLifecycleDemo {

    static int mark(String message) {
        System.out.println(message);
        return 10;
    }

    static class Parent {
        static {
            System.out.println("Parent: static block");
        }

        Parent() {
            System.out.println("Parent: constructor");
        }
    }

    static class Child extends Parent {
        static int count = mark("Child: static field");
        static {
            System.out.println("Child: static block");
        }

        int value = mark("Child: instance field");
        {
            System.out.println("Child: instance block");
        }

        Child() {
            super();
            System.out.println("Child: constructor");
        }
    }

    public static void main(String[] args) {
        System.out.println("Before first new");
        new Child();
        System.out.println("Before second new");
        new Child();
    }
}
```

Compile and run with JDK 17 or later (the syntax also runs on JDK 21):

```bash
javac --release 17 InitLifecycleDemo.java
java InitLifecycleDemo
```

**Expected stdout**:

```text
Before first new
Parent: static block
Child: static field
Child: static block
Parent: constructor
Child: instance field
Child: instance block
Child: constructor
Before second new
Parent: constructor
Child: instance field
Child: instance block
Child: constructor
```

Class-by-class explanation:

1. When `main` runs, `InitLifecycleDemo` is already initialized. The first `new Child()` triggers initialization of `Child` if not yet done, which causes `Parent` to initialize first. Therefore `Parent: static block` precedes the two static lines of `Child`.
2. After class initialization, the `Child` constructor calls `Parent()`; after the superclass constructor returns, the instance field initializer and instance block of `Child` run in source order; finally, the body of the `Child` constructor runs.
3. On the second `new Child()`, **static block/field initializers are not repeated**, but the entire constructor and instance initialization flow runs again for the new object.

On Windows PowerShell, macOS, or Linux shells, use single quotes in the following commands to prevent the shell from interpreting the `$` character in the nested class name:

```bash
javap -c -p 'InitLifecycleDemo$Child'
javap -v -p 'InitLifecycleDemo$Child'
```

In the `javap -c -p` output, observe the `Child` constructor: it typically starts with `aload_0` then `invokespecial ...Parent."<init>":()V`; next are the `mark` call, `putfield value`, and instructions printing the instance block/constructor lines. The separate `static {};` section contains the `mark` call, `putstatic count`, and the static block message. In the `javap -v` output, check the `()V` descriptor, the `ACC_STATIC` flag of the initializer, and the `<init>`/`<clinit>` entries in the constant pool. Offsets, constant pool indices, and exact display syntax may vary across `javac`/`javap` versions.

## 6. Instrumentation perspective: where is it safe to insert probes?

Class file transformation tools (agents, ASM, Byte Buddy, or other transformers) must respect both **constructor semantics** and **verifier state**.

### Probe before `super()`: difference between calling a static method and passing `this`

The **invalid pseudo-bytecode** below illustrates an approach that easily causes `VerifyError`; this is not a Java program to compile:

```text
; In <init>, local 0 is still uninitializedThis
aload_0
invokestatic Probe.capture:(Ljava/lang/Object;)V   ; WRONG: cannot be used as Object yet
aload_0
invokespecial Parent.<init>:()V
```

Inserting `invokestatic Probe.enter:()V` without taking `this` can be valid for the verifier *if* control flow and stack maps are handled properly. However, a probe with side effects or that throws an exception will alter constructor behavior. A practical way to record an object is to insert after the appropriate superclass/same-class constructor call, and only use `this` when it is guaranteed to have transitioned to the initialized type on **all control flow paths**. Even then, avoid calling code that passes `this` to another thread/cache/listener before the entire subclass state is stable.

### Checklist before emitting transformed classes

- Identify methods precisely by **name `<init>` plus descriptor**, since a class can have multiple overloads. Do not confuse them with the method named `<clinit>`; the JVM invokes the class initializer itself, whereas `<init>` is called via `invokespecial`.
- Distinguish the bytecode region **before** and **after** the `this(...)`/`super(...)` call, along with all branches and exception edges. Do not assume all paths pass through the same offset if the transformer has modified the code.
- Maintain valid operand stack, `max_stack`/`max_locals`, jump offsets, exception table, and `StackMapTable`. When using ASM `COMPUTE_FRAMES`, a valid class hierarchy/classpath must still be provided; automatic frame computation cannot fix broken control flow.
- With `new`/`dup`/`invokespecial`, do not split or turn an `uninitialized(p)` reference into an initialized reference before the target constructor completes. Do not pass an uninitialized reference to `invokevirtual`, `invokeinterface`, or instructions requiring an initialized object.
- With `<clinit>`, watch out for probes that may load additional classes or cause initialization cycles; static initialization runs once per class identity, and failure can leave the class in an erroneous state. Transformers must not assume `<clinit>` can be "re-run" after redefining/retransforming a class.
- Test both **success** and **exception-throwing** paths. When testing transformed code, run it under a real JVM with verification enabled (the default) and compare the order of side effects before and after instrumentation.

### Three common misconceptions

| Misconception | Correct understanding |
|---|---|
| "`new` finishes calling the constructor immediately" | `new` creates/allocates an uninitialized reference; `invokespecial <init>` executes the constructor. |
| "`<clinit>` runs for every `new`" | It is the **class** initialization phase, typically at most once per `Class` object; `<init>` is on the initialization path of each instance. |
| "After `super()`, all subclass fields are complete" | The verifier may consider `this` initialized, but subclass instance initializers/constructor body may not have finished running yet. |

## 7. Self-check questions

1. Why does the verifier need both `uninitializedThis` and `uninitialized(offset)`? Because one describes the receiver of the current `<init>`, while the other describes an object created by a specific `new` instruction; constructor call rules and type transitions need to distinguish them.
2. When you have `Child() { this("x"); }`, does `Child()` also call `super()` itself? No. The delegated constructor continues the chain and eventually calls the appropriate superclass constructor; the superclass constructor is not called twice for a single object construction path.
3. Why does reading `static final int PORT = 8080` usually not run the static block? Because it is a constant variable with a compile-time value; clients can inline the value and reading it does not trigger class initialization.
4. Why can't you simply insert `aload_0; invokestatic log(Object)` at the beginning of a constructor's bytecode? Because local 0 has verification type `uninitializedThis`; it cannot be passed as `Object` before the valid point.
5. If initialization of `Child` fails in `<clinit>`, will the next `new Child()` "retry" it? No; the JVM marks the class erroneous and subsequent active use may throw `NoClassDefFoundError`.

## Official references

- [JVMS 21, §2.9 — Instance/Class Initialization Methods](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.9)
- [JVMS 21, §4.10.1.9 — Type Checking / invokespecial and uninitializedThis](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.10.1.9)
- [JLS 21, §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4)
- [JLS 21, §12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.5)
