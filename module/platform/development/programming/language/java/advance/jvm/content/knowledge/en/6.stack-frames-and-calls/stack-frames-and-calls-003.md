# `invokestatic`, `invokespecial`, `invokevirtual`, and `invokeinterface` in the JVM

## 1. Four Method Invocation Instructions Solve Different Problems

Java source code can use the same `object.method(...)` or `Type.method(...)` syntax, but at the JVM level, the compiler must choose a **method invocation instruction** that matches the nature of the method and the binding mechanism. The four instructions to distinguish are:

| Instruction | Primary role | Receiver object on operand stack? | How the method to execute is selected |
| --- | --- | --- | --- |
| `invokestatic` | Calls a **static method** of a class or interface | **No** | Based on the resolved symbolic reference to the static method; no dispatch based on an object's runtime type |
| `invokespecial` | Calls an instance initialization method `<init>`, `super` calls, and instance calls with special rules | **Yes** | Applies JVMS special lookup/selection; not the normal override dispatch of `invokevirtual` |
| `invokevirtual` | Calls a normal instance method through a **class type** | **Yes** | Selects the implementation based on the receiver's runtime class and override rules |
| `invokeinterface` | Calls an instance method through an **interface type** | **Yes** | Selects the matching method implemented or inherited by the receiver's runtime class, including default method rules |

The specification also has **`invokedynamic`** for call sites linked via a bootstrap method. It is the fifth invocation instruction, but it has a different linkage model and is not the main subject of this lesson. In Java 17, string concatenation can generate `invokedynamic`, so do not assume every line of `javap -c` output only contains the four instructions listed above.

**Right mindset:** the declared type of the expression and how the method is called allow the compiler to emit the instruction along with a constant-pool reference; then the JVM resolves and (for instructions requiring dynamic dispatch) selects the implementation based on the actual object. "Having the same method name" is not enough to conclude that the opcode will be the same.

## 2. Essential Context: Frame, Operand Stack, and Method Descriptor

Each Java method invocation can create a **frame** on the thread's JVM stack. A frame contains local variables, an operand stack, and information supporting linking/returning. Before an `invoke*` instruction, the JVM uses the operands prepared on the caller's **operand stack**.

Examples of JVM signatures:

| Java declaration | Method descriptor in the class file |
| --- | --- |
| `static int twice(int n)` | `(I)I` |
| `String say()` | `()Ljava/lang/String;` |
| `void save(String value, long time)` | `(Ljava/lang/String;J)V` |
| `Child()` | `<init>:()V` |
| `void process(int[] values)` | `([I)V` |

A descriptor records **the parameter types and the return type**, and does not carry Java parameter names like `n` or `time`. The JVM uses a symbolic method reference consisting of **the owning type of the method, the method name, and the descriptor** (along with other constant-pool information) to find the matching method. Overloaded methods based on different signatures will have different descriptors at the JVM level.

### Diagram of an Instance Call

~~~text
Caller frame:
  local variables:  ...
  operand stack:    [..., objectref, arg1, arg2]
                                      |
                        invokevirtual / invokeinterface /
                        invokespecial
                                      v
Callee frame (for an instance method):
  local slot 0: this = objectref
  subsequent slots: arg1, arg2, ...
  callee's own operand stack
                                      |
                            execute callee bytecode
                                      |
                           xreturn / return / athrow
                                      v
Caller continues after the invoke instruction;
if there is a return value, it is pushed onto the caller's operand stack
~~~

With `invokestatic`, **there is no `this`**: the first parameter (if any) starts at local slot 0 of the callee. With an instance method, slot 0 typically holds `this`. `long` and `double` values use **two local-variable slots** according to the JVM frame model; the number of parameters in the source does not always equal the number of local slots.

For example, calling `Child.say()` returning a `String`: the receiver is a reference, the descriptor is `()Ljava/lang/String;`, and the result returns to the caller via `areturn`. If the callee throws an exception, the call does not return normally; frames may be unwound while searching for an exception handler. Calling a method does not mean "copying the entire object into the new frame"; the frame receives the **reference value** for `this`.

## 3. Classes, Interfaces, and Symbolic Reference Information in the Constant Pool

An `invoke*` instruction specifies the **constant-pool index** to use for the method reference. The class file does not record the direct machine byte address of a method at each call site. Information looks like:

~~~text
#18 = Methodref             #... // InvokeModesDemo.twice:(I)I
#45 = Methodref             #... // InvokeModesDemo$Parent.label:()Ljava/lang/String;
#49 = InterfaceMethodref    #... // InvokeModesDemo$Speaker.say:()Ljava/lang/String;
~~~

This is an example of how `javap -v` displays it; the constant-pool index numbers **may vary** depending on the compiler and binary.

Points to distinguish:

- `CONSTANT_Methodref` and `CONSTANT_InterfaceMethodref` are different entry kinds; they contain the relationship to the corresponding class/interface and `NameAndType`.
- Under Java 17 class-file version constraints, `invokevirtual` uses `CONSTANT_Methodref`; `invokeinterface` uses `CONSTANT_InterfaceMethodref`. `invokestatic` and `invokespecial` can use either `Methodref` or `InterfaceMethodref` when valid according to the class file version and method kind.
- **Resolution** finds the matching symbolic method reference and checks linking/access conditions; **selection/dispatch** may still depend on the actual class of the receiver in `invokevirtual`/`invokeinterface`. Do not conflate resolution and dispatch into the single idea that "the JVM already knows the method at compile time".
- The Java compiler checks types, overloading, and accessibility at compile time, but the actual runtime classes and libraries may differ from the versions used during compilation, so the JVM can still encounter **linkage errors** at runtime.
- JIT/HotSpot may use vtables, itables, inline caches, or devirtualization for optimization. **Those specific data mechanisms are not mandatory definitions of the opcodes in the JVM Specification**.

A call can be heavily optimized in native code, but the observable semantics must still conform to the method selection mechanism defined by Java/JVM (except in cases of errors, program-undefined behavior, or specified differences).

## 4. `invokestatic`: Calling a Static Method Without a Receiver

When Java calls:

~~~java
int result = Math.max(4, 7);
~~~

A typical Java compiler emits `invokestatic` referencing the static method `Math.max:(II)I`. Before the call, the arguments `4` and `7` are pushed onto the operand stack. **There is no receiver object** for a static method, and on the callee side there is no `this`.

Conceptually:

~~~text
iconst_4
bipush 7
invokestatic java/lang/Math.max:(II)I
istore_1
~~~

This is a simplified representation, not guaranteed to be the exact full `javap` output; actual variables and offsets are decided by the compiler.

### Static Hiding Is Not Dynamic Overriding

~~~java
class Parent {
    static String kind() { return "PARENT"; }
}
class Child extends Parent {
    static String kind() { return "CHILD"; }
}
~~~

`Parent.kind()` and `Child.kind()` are **two separate static calls**. A static method in a subclass can **hide** a static method with the same signature in the superclass, but does not override it like an instance method.

If Java code allows calling a static method through a receiver expression such as `ref.kind()`, method resolution still follows the **compile-time type**, not dispatch based on the actual object. Writing `Type.kind()` is clearer and avoids misleading readers into thinking it is a virtual call.

**Class/interface initialization:** executing `invokestatic` can trigger initialization of the class or interface **that declares the resolved static method**, according to JVM initialization rules. This is separate from creating an object: a static method can be called even when the program has no instances of the class. Do not oversimplify by stating that "merely seeing the class name in source guarantees the static initializer runs"; initialization conditions are governed by the specification.

`invokestatic` can also call a **static method of an interface**, such as `Speaker.version()` in the example below; therefore, describing it as "only calling static methods in a class" is insufficient for modern Java.

## 5. `invokespecial`: Constructors, `super`, and Special Instance Handling

`invokespecial` has distinct semantics compared to normal virtual dispatch. Typical cases:

1. **Constructor `<init>`**: when bytecode creates an object with `new`, the instance initialization process uses `invokespecial` to call the constructor. A subclass constructor also calls a superclass constructor according to Java/JVM rules.
2. **Calling a superclass method via `super.method(...)`**: the source's intent is to **start accessing the implementation on the parent side** according to `super` semantics, rather than selecting a subclass override like a normal `this.method()`.
3. **Calling a specified default method via `InterfaceName.super.method(...)`** when permitted by Java and the superinterface relationship.
4. **Certain instance calls with special access/rules**, including cases involving private methods. You should not claim that **every** private call in **every** compiler version must carry the `invokespecial` opcode solely based on the `private` keyword; you need to inspect the actual class file and corresponding JVM rules.

### 5.1. Constructors: `new` Is Different from `invokespecial`

When writing:

~~~java
Child child = new Child();
~~~

The bytecode typically has the form:

~~~text
new           #... // class Child
dup
invokespecial #... // Method Child."<init>":()V
astore_1
~~~

- `new` allocates a new instance (after relevant initialization conditions are satisfied) and produces an **uninitialized object reference** at the verifier level.
- `dup` keeps a copy of the reference value on the operand stack to use after calling the constructor.
- `invokespecial Child.<init>` executes the instance initialization method; the JVM verifier places specific constraints on how uninitialized references may be used.
- `astore_1` is just an example of storing the initialized reference into a local slot; the compiler may lay it out differently.

**Only `invokespecial` is allowed to invoke an instance initialization method `<init>`** under class-file constraints. A constructor is not an overridable method; a constructor cannot virtual-dispatch to an "override constructor" in a subclass.

### 5.2. Super Calls Bypass Overrides According to Source Semantics

Example:

~~~java
class Parent {
    String label() { return "PARENT"; }
}
class Child extends Parent {
    @Override String label() { return "CHILD"; }
    String parentLabel() { return super.label(); }
}
~~~

With a `Child`, calling `child.label()` from outside is a normal virtual call and selects `Child.label()`. However, inside `Child.parentLabel()`, the expression `super.label()` has the semantics of calling the superclass-side implementation, so the compiler emits the appropriate `invokespecial`.

Do not interpret `invokespecial` as "always calling the exact class written in the constant pool without any selection rules". The specification has **special lookup/selection**, including the effect of `ACC_SUPER` and inheritance relationships. What to remember at this learning level is that **it does not perform normal override dispatch like `invokevirtual`**.

### 5.3. Interface Default Method via `Interface.super`

With an appropriate direct superinterface, the expression `Speaker.super.banner()` calls the default implementation from that interface, usually compiled using `invokespecial` with an **InterfaceMethodref**. This is **different** from calling through a `Speaker` variable, which can use `invokeinterface`.

Thus, even though it is the same interface method, **how it is called** (`Speaker.super.banner()` vs. `speaker.banner()`) can determine different instructions.

## 6. `invokevirtual`: Dispatch Based on the Runtime Object

This is the very common instance method invocation instruction for a **class-typed receiver**.

~~~java
Parent value = new Child();
System.out.println(value.label());
~~~

The compiler sees that variable `value` has declared type `Parent` and typically emits the symbolic reference `Parent.label:()Ljava/lang/String;`, while the actual object is `Child`. At runtime, `invokevirtual` performs implementation selection based on the **receiver's runtime class**, and therefore can select `Child.label()`.

~~~text
Compile time (by declared type)             Runtime (by actual object)
Parent value;                               receiver = Child instance
value.label()  ── invokevirtual Parent.label ──> Child.label()
~~~

**Notes:**

- `invokevirtual` can still appear when a method is `final` or has no actual subclass overrides. The opcode represents the invocation mode; it **does not prove** that runtime always needs a complex lookup.
- `private` methods are not overridden like normal virtual instance methods. The Java compiler and JVM have special rules, so you need to look at the concrete bytecode when analyzing private/nestmate cases.
- `static` methods do not participate in virtual dispatch. Static methods are hidden, not overridden.
- If the receiver value is `null`, an instance call that needs to dereference the receiver will throw `NullPointerException`, and no implementation is selected to run.
- `Object.equals`, `toString`, and `hashCode` are obvious examples of virtual methods; with a valid class override, the executed method can be the subclass's. The implementation selection rules themselves still depend on the runtime class and method selection rules.

### Overload Is Chosen First, Override Is Chosen Later

~~~java
class Parent {
    String pick(Object value) { return "OBJECT"; }
}
class Child extends Parent {
    @Override String pick(Object value) { return "CHILD_OBJECT"; }
    String pick(String value) { return "CHILD_STRING"; }
}
~~~

With `Parent p = new Child();`, for the expression `p.pick("JVM")`, the compiler selects the **overload `pick(Object)`** because the declared type `Parent` does not provide `pick(String)`. At runtime, `invokevirtual` selects the override **`Child.pick(Object)`**, and does not "switch overloads" to `Child.pick(String)` just because the actual object is `Child`. The descriptor is already fixed at compile time; dispatch selects the method **with the matching name/descriptor** according to override rules.

This point explains why the "dynamic" nature of virtual dispatch does not mean Java defers **all decisions about the method** until runtime.

## 7. `invokeinterface`: Calling Through an Interface Contract

When a variable has an **interface type**, bytecode typically uses `invokeinterface`:

~~~java
Speaker speaker = new Child();
String message = speaker.say();
~~~

The compiler references the symbolic method of `Speaker`, and the JVM finds the matching method provided or inherited by the receiver's **runtime class**. Here `Child.say()` executes.

The difference from `invokevirtual` is not that "interfaces have no code": since Java 8 interfaces can have **default methods**, and since Java 9 interfaces can also have private methods. `invokeinterface` still must follow resolution/selection rules to find the implementation, including cases of methods inherited by the class, `Object` methods under allowed rules, and default methods.

### 7.1. Default Methods

If an interface declares:

~~~java
interface Speaker {
    String say();
    default String banner() {
        return "INTERFACE_DEFAULT";
    }
}
~~~

Then the call `speaker.banner()` through a `Speaker` reference can use `invokeinterface`, and runtime can select the default implementation if the class does not provide a higher-priority override. Conversely, `Speaker.super.banner()` inside an implementing class is allowed to call through `invokespecial`.

Note: Java has rules for resolving default method conflicts when multiple superinterfaces provide the same signature. The compiler usually catches invalid cases; modified class files or binary mismatches can lead to linkage/invocation errors according to the specification. Do not invent a mental model that "it always picks the interface listed first in the `implements` clause".

### 7.2. `invokeinterface` Instruction Layout

In bytecode, `invokevirtual`, `invokespecial`, and `invokestatic` consist of the opcode plus a **2-byte constant-pool index**. `invokeinterface` is **5 bytes**:

~~~text
invokeinterface indexbyte1 indexbyte2 count 0
~~~

- The two bytes `indexbyte1/indexbyte2` form the constant-pool index to an `InterfaceMethodref`.
- The `count` byte records the number of local-variable slot units needed for **the receiver and the arguments**; `long`/`double` occupy two slots.
- The final byte must be `0` according to the class-file format.

For example, `javap` may print:

~~~text
invokeinterface #49,  1  // InterfaceMethod Speaker.say:()Ljava/lang/String;
~~~

For a method taking no source parameters, `count = 1` is still valid because there is the **receiver**. Do not infer that the `count` byte is the number of methods in the interface, the number of interfaces of the object, or the number of Java parameters excluding the receiver.

## 8. Complete Hands-On Lab on Java 17+

Create **`InvokeModesDemo.java`** in your working directory:

~~~java
public final class InvokeModesDemo {
    interface Speaker {
        String say();

        default String banner() {
            return "INTERFACE_DEFAULT";
        }

        static String version() {
            return "SPEAKER_STATIC";
        }
    }

    static class Parent {
        String label() {
            return "PARENT";
        }

        static String kind() {
            return "PARENT_STATIC";
        }
    }

    static class Child extends Parent implements Speaker {
        @Override
        String label() {
            return "CHILD";
        }

        @Override
        public String say() {
            return "CHILD_SAYS";
        }

        String parentLabel() {
            return super.label();
        }

        String interfaceBanner() {
            return Speaker.super.banner();
        }

        static String kind() {
            return "CHILD_STATIC";
        }
    }

    static int twice(int n) {
        return n * 2;
    }

    public static void main(String[] args) {
        Parent asParent = new Child();
        Speaker asSpeaker = (Speaker) asParent;
        Child exact = (Child) asParent;

        System.out.println("static=" + twice(3));
        System.out.println("classStatic=" + Parent.kind());
        System.out.println("hiddenStatic=" + Child.kind());
        System.out.println("virtual=" + asParent.label());
        System.out.println("interface=" + asSpeaker.say());
        System.out.println("super=" + exact.parentLabel());
        System.out.println("default=" + exact.interfaceBanner());
        System.out.println("interfaceStatic=" + Speaker.version());
    }
}
~~~

Compile/run with **JDK 17 or later**:

~~~bash
javac --release 17 InvokeModesDemo.java
java InvokeModesDemo
~~~

**Exact stdout:**

~~~text
static=6
classStatic=PARENT_STATIC
hiddenStatic=CHILD_STATIC
virtual=CHILD
interface=CHILD_SAYS
super=PARENT
default=INTERFACE_DEFAULT
interfaceStatic=SPEAKER_STATIC
~~~

The code was actually compiled with `javac --release 17` on JDK 21 and run with the exact results above. The nested classes are output by the compiler into files `InvokeModesDemo$Parent.class`, `InvokeModesDemo$Child.class`, `InvokeModesDemo$Speaker.class` (containing the `$` character in the filename), alongside `InvokeModesDemo.class`.

### 8.1. Inspecting the Main Class Bytecode

~~~bash
javap -c -p InvokeModesDemo
~~~

Look for these instructions in `main`:

| Source expression | Instruction to look for in the example |
| --- | --- |
| `new Child()` | `new`, `dup`, `invokespecial Child."<init>":()V` |
| `twice(3)` | `invokestatic InvokeModesDemo.twice:(I)I` |
| `Parent.kind()` | `invokestatic Parent.kind:()Ljava/lang/String;` |
| `Child.kind()` | `invokestatic Child.kind:()Ljava/lang/String;` |
| `asParent.label()` | `invokevirtual Parent.label:()Ljava/lang/String;` |
| `asSpeaker.say()` | `invokeinterface Speaker.say:()Ljava/lang/String;` |
| `exact.parentLabel()` | `invokevirtual Child.parentLabel:()Ljava/lang/String;` |
| `exact.interfaceBanner()` | `invokevirtual Child.interfaceBanner:()Ljava/lang/String;` |
| `Speaker.version()` | `invokestatic Speaker.version:()Ljava/lang/String;` |

**Distinguish carefully:** `main` calls `exact.parentLabel()` with `invokevirtual`, but **inside** `parentLabel()` there is a `super.label()` call using `invokespecial`. Similarly, `main` calls `exact.interfaceBanner()` with `invokevirtual`, while **inside that method** it uses `invokespecial` for `Speaker.super.banner()`. Do not conclude the opcode of an entire call chain solely from stdout results.

### 8.2. Inspecting Bytecode in Nested Classes with `javap`

In **Bash**, use single quotes so the shell does not expand the `$` character in the class name:

~~~bash
javap -c -p 'InvokeModesDemo$Child'
javap -c -p 'InvokeModesDemo$Parent'
javap -c -p 'InvokeModesDemo$Speaker'
~~~

In **PowerShell**, class names with `$` should also be placed in single quotes, for example:

~~~powershell
javap -c -p 'InvokeModesDemo$Child'
~~~

In the `Child` output, look for:

~~~text
InvokeModesDemo$Child();
  ...
  invokespecial ... // Method InvokeModesDemo$Parent."<init>":()V

java.lang.String parentLabel();
  ...
  invokespecial ... // Method InvokeModesDemo$Parent.label:()Ljava/lang/String;

java.lang.String interfaceBanner();
  ...
  invokespecial ... // InterfaceMethod InvokeModesDemo$Speaker.banner:()Ljava/lang/String;
~~~

This is an **excerpt of the meaning to look for**, not the entire `javap` output with fixed constant-pool indices/bytecode offsets. Running `javap -c` on JDK 21 on the compiled build above confirmed all three cases.

### 8.3. What Else Appears Besides the Four Opcodes?

In `main`, the Java 17 compiler may use:

- `getstatic java/lang/System.out` to obtain `PrintStream`.
- `checkcast` when casting `Parent` to `Speaker` or `Child`.
- `invokevirtual PrintStream.println` to print strings.
- `invokedynamic makeConcatWithConstants` to concatenate `"static=" + twice(3)` and the other output strings.
- `aload` and `astore` to move references between local variables and the operand stack.

These instructions help form the full context of the calls. When you see `invokedynamic` for string concatenation, **do not mistake it for the opcode calling `twice` or `label`**; those methods are still invoked via `invokestatic` or `invokevirtual` in the verified compiled output.

## 9. Looking From a Single Call: Compile Time, Link Time, and Run Time

Consider the call `asParent.label()` in the example. There are three milestones:

### Step 1 — Choosing Overload and Name/Descriptor at Compile Time

The compiler looks at the declared type `Parent`, checks that the method is accessible, and decides on the reference `label:()Ljava/lang/String;`. If there are multiple overloads, the compiler selects the overload matching the expression types and Java's overload resolution rules **before runtime**.

### Step 2 — JVM Resolves the Symbolic Method Reference

At execution, the JVM needs the appropriate class/method descriptor and ensures linking/access conditions. Resolution can happen at linking time or when the instruction needs it, depending on what the JVM allows. This is the act of identifying a symbolic reference that actually corresponds to a valid runtime element.

### Step 3 — Selecting the Implementation Based on the Actual Receiver

The receiver of `asParent` is a `Child` instance; `invokevirtual` following method selection rules will run `Child.label()`, because it is a valid override. **Resolving to the method denoted via `Parent` does not mean ignoring `Child`'s override.**

For `invokestatic Parent.kind()`, there is no receiver-based dispatch step. For `invokespecial super.label()`, special selection applies. For `invokeinterface Speaker.say()`, the JVM examines available implementations from the runtime class `Child` along with interface method rules.

### Method Lookup Does Not Mean the Call Stack Does Not Change

Whether `invokestatic` or `invokevirtual`, upon entering the callee body, in JVM semantics there is a **method call and a corresponding frame**, parameters/receiver are placed into locals, and then the method returns or throws an exception. When the JIT inlines, physical/internal frames may be optimized away; that does not change control-flow results or what the Java program is permitted to observe.

## 10. Cases Where a Method Is `null`, `final`, `abstract`, or Does Not Exist

### 10.1. Null Receiver

~~~java
Parent value = null;
// value.label(); // if run: NullPointerException
~~~

For instance calls requiring a receiver, `invokevirtual` and `invokeinterface` require a non-null reference. `invokespecial` calling an instance method also requires a valid receiver per invocation rules, except for verifier-specific details of uninitialized references during object construction.

`invokestatic` **does not require a receiver** and cannot throw `NullPointerException` merely because "the receiver of a static call is null"; the source may evaluate an expression using static-call-via-instance syntax, but the static method still has no `this` and no dynamic receiver dispatch. Do not use that syntax in new code.

### 10.2. Final Methods

A `final` instance method cannot be validly overridden in a subclass. The compiler can still emit `invokevirtual` to call it in bytecode. The JIT often has optimization opportunities when the target is known, but you must not use the presence of `invokevirtual` to conclude that multiple overrides are possible.

### 10.3. Abstract Methods and Interface Implementations

A class can declare an abstract method; a valid object of a concrete subclass must provide an implementation according to Java rules. If binary incompatibility causes the method selected at runtime to have no suitable implementation, the JVM can throw **`AbstractMethodError`**. This is a **linkage error** and should not be naively explained as a `NullPointerException`.

### 10.4. Class/Interface API Changes Between Compile Time and Runtime

For example, a caller was compiled against `Parent.label:()Ljava/lang/String;`, but the runtime library removes/changes the method or descriptor. The caller can run until it hits `NoSuchMethodError` or another linkage error. Changing a method from instance to static (or vice versa) breaks opcode compatibility and typically leads to **`IncompatibleClassChangeError`** under the appropriate circumstances.

| Common error | What to check |
| --- | --- |
| `NullPointerException` on instance call | Is the actual receiver `null`? |
| `NoSuchMethodError` | Does the runtime binary have the exact name and descriptor the caller was compiled against? |
| `IllegalAccessError` | Did access permissions or module/package/nest relationships change so that runtime access is no longer valid? |
| `IncompatibleClassChangeError` | Does the caller expect static/instance, class/interface, or an inheritance structure different from the running binary? |
| `AbstractMethodError` | Does the selected method have a valid implementation? |
| `StackOverflowError` | Is the recursion/call chain too deep for the thread's stack capacity? |

These are investigation leads, **not a guaranteed one-to-one mapping for every error**. Check the stack trace, classpath/module path, the actual class files loaded, class loaders, and dependency versions before drawing conclusions.

## 11. Method Overriding, Default Methods, and Access Permissions

### Overrides Must Be Valid According to Java/JVM

With `@Override`, the compiler helps verify that the new instance method's signature is compatible with the method it intends to override. Not every method with the same name overrides: private methods, static methods, constructors, and overloaded methods have different rules.

At the JVM level, overriding depends on the name and descriptor along with conditions such as accessibility, class relationships, and method overriding/selection rules. When generic erasure or covariant return types are involved, the compiler may generate a **bridge method** to keep the ABI consistent; you may see extra methods with `ACC_BRIDGE`/`ACC_SYNTHETIC` flags in `javap -v`. Therefore, you cannot always map "one method declaration in Java" to "exactly one JVM `method_info`".

### Interface Default Methods Can Be Overridden by a Class

If `Child` itself declares:

~~~java
@Override
public String banner() {
    return "CHILD_BANNER";
}
~~~

then a call through `Speaker speaker = new Child(); speaker.banner()` can select `Child.banner()` instead of the default implementation. However, an intentional `Speaker.super.banner()` call inside a class permitted to use it still invokes the appropriate default branch via special invocation.

**The snippet above only illustrates a modification compared to the hands-on program**; do not add it to the sample file if you want to preserve the stdout from section 8. If you add the override and recompile, the call result will normally change according to the new method implementation.

### Access and Module Boundaries

A method may exist in the class file, yet the caller is still not allowed to invoke it if Java/JVM access rules forbid it. A method can be `public`, `protected`, package-private, or `private`, and in modular Java projects there are also module accessibility conditions. Do not infer that just because `javap -p` shows a method, it can be validly called from any class.

## 12. JIT Optimizations That Do Not Change Instruction Semantics

HotSpot or other JVMs can use **inlining**, **devirtualization**, **inline caches**, profile-guided optimization, or other lookup techniques to speed up execution. When runtime observes that an `invokevirtual` call site encounters only one object type for a period of time, the JIT can optimize the call path and have a fallback/deoptimization mechanism when the assumption no longer holds.

These terms help when reading performance documentation, but they do not alter the meaning of `invokevirtual`: a valid override of the runtime receiver must still be respected. Similarly, `invokeinterface` is not inherently slower than `invokevirtual` in every workload and every JVM; the optimization level depends on the environment, data types, and actual number of implementations. When you want to compare performance, measure with a reliable benchmark (such as JMH), avoiding reliance on simply counting opcodes.

### Exceptions and `synchronized` Methods

If the invoked method is `synchronized`, the JVM has monitor entry/exit rules upon invocation/return or abnormal completion. It does not change whether a method is "static or virtual", but it affects the callee's synchronization mechanism. If the callee throws an exception, the caller can catch it via the exception table; exception propagation does not turn `invokevirtual` into `invokespecial`.

## 13. How to Read `javap` to Verify the Invoked Method

In a project with any class, follow this order:

1. **Compile for the right Java target** (e.g., `javac --release 17 ...`) and ensure the class file being read is the actual binary being run.
2. Use `javap -c -p ClassName` to locate the method containing the call site. Note that `javap` can also print `<init>`, synthetic/bridge methods, and compiler-generated code.
3. Observe **opcode + constant-pool reference + descriptor**: `invokestatic`, `invokespecial`, `invokevirtual`, or `invokeinterface`.
4. Identify the **receiver object** (if any) via `aload`, `getfield`, `new`, `checkcast`, and instructions preceding the call site.
5. For `invokevirtual`/`invokeinterface`, determine the **runtime class** of the object to understand the selected implementation; simply reading the method name in the `javap` comment is not enough to deduce the final target.
6. Use `javap -v` when you need to inspect `Methodref`/`InterfaceMethodref`, flags like `ACC_STATIC`, `ACC_BRIDGE`, signatures, class-file version, and metadata.
7. If runtime reports a linkage error, compare the class files **loaded at runtime** and the dependency tree against the classes the caller **was compiled against**.

Important technical point: numbers like `#45` after `invokevirtual` are **constant-pool indices**, not native method addresses. Line-leading numbers like `65:` are **bytecode PCs** within the method, not Java line numbers or physical addresses.

## 14. Common Misconceptions

1. **"`invokestatic` always needs an object to find the method."** False, a static call has no receiver and no `this`.
2. **"`invokevirtual` calls the exact method of the declared type, ignoring the actual object."** False, it uses method selection by runtime class when a valid override exists.
3. **"`invokeinterface` only runs code in the interface and cannot run class methods."** False, runtime finds the appropriate implementation on the object; an interface default method is one of the cases.
4. **"Constructors are called via `invokevirtual` like normal methods."** False, the instance initializer `<init>` is only called via `invokespecial`.
5. **"`super.method()` still dispatches to the override in the subclass."** False according to `super` semantics; it uses the special invocation path.
6. **"`invokeinterface` with `count=1` means one Java parameter."** False, `count` includes the receiver and counts argument slots.
7. **"A static method in a subclass overrides the parent's static method."** False, Java uses **hiding** for static methods.
8. **"Overload resolution is automatically changed by the JVM based on the runtime class."** False, the overload was already chosen by expression types at compile time; virtual dispatch only finds the matching override.
9. **"`final` methods cannot appear after the `invokevirtual` opcode."** False, the opcode does not guarantee the existence of subclass overrides.
10. **"Every private instance call is necessarily compiled to `invokespecial` on every JDK."** False, encoding details also depend on the JVM/compiler version and access context.
11. **"HotSpot's vtable/itable is a mandatory part of the JVMS."** False, the spec defines **semantics**, and implementations choose their own optimization structures.
12. **"Having a method with the same name and compiling successfully guarantees it will run on every library version."** False, runtime descriptors, access, and method kinds may have changed.

## 15. Self-Check Questions

1. When calling `Math.max(4,7)`, what opcode is typically seen and is there a receiver? **`invokestatic`; there is no receiver**.
2. Given `Parent p = new Child(); p.label()` where `Child` overrides `label()`, which method runs? **`Child.label()`**, because `invokevirtual` selects by runtime class.
3. Which instruction does a `super.label()` call from a `Child` method typically use? **`invokespecial`**, following super invocation semantics.
4. Which instruction is used to call the constructor `<init>`? **`invokespecial`**, not `invokevirtual`.
5. When a variable declared with type `Speaker` calls `say()`, what opcode does the compiler typically use? **`invokeinterface`**.
6. Why does `Speaker.version()` not use `invokeinterface`? Because it is a **static interface method**, called with `invokestatic`.
7. Do `Parent.kind()` and `Child.kind()` with the same name have dynamic overriding? **No**, that is static method hiding.
8. With `Parent p = new Child()`, if `Parent` only declares `pick(Object)` while `Child` adds overload `pick(String)`, which overload does `p.pick("x")` use? **`pick(Object)` already selected by the compiler**, then dispatched to its matching override.
9. If `invokeinterface` calls a method with no source parameters, can the `count` byte be `1`? **Yes**, because it includes the receiver.
10. Why might `javap` print `invokedynamic` even when studying the four instructions above? **Modern Java compilers use `invokedynamic` for certain call sites, such as string concatenation**.
11. Can you conclude which method actually runs solely from the `// Method Parent.label...` comment of `invokevirtual`? **Not enough**; you need the runtime receiver type and selection rules.
12. Does a call site initially inlined by the JIT change Java's override semantics? **No**, optimizations must preserve dispatch semantics.

## 16. Official References

- JVM Specification Java SE 17, **Method Invocation and Return Instructions**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.8
- JVMS, **Instruction Set** (`invokestatic`, `invokespecial`, `invokevirtual`, `invokeinterface`): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
- JVMS, **Method Resolution, Interface Method Resolution, Method Selection**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- JVMS, **Class-file Constraints** and constant pool: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- Java Language Specification, **Method Invocation Expressions**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12
- JDK 17 `javap`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html

**Technical takeaway:** `invokestatic` calls static methods **without a receiver**; `invokespecial` is used for constructors and instance calls with **special selection**, notably `super`; `invokevirtual` selects overrides based on the **runtime class** of the object; and `invokeinterface` performs calls through an **interface contract**. To accurately understand a JVM call, you need to read the **opcode**, the **method reference + descriptor**, the **receiver/runtime type**, and distinguish **resolution** from **method selection**.