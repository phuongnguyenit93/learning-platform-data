# Distinguishing the bootstrap class loader from the invokedynamic bootstrap method

In Java, there are two terms that both contain the word **bootstrap**, yet refer to **two completely different JVM mechanisms**:

1. **Bootstrap class loader** is a component of the **class loading and definition** mechanism: it is responsible for many foundational classes of the Java runtime, such as `java.lang.String` and `java.lang.invoke.LambdaMetafactory` on a standard JDK 17. In the `Class.getClassLoader()` API, a class defined by the bootstrap class loader is represented by `null`.
2. **Bootstrap method (BSM) of `invokedynamic`** is a **method or method handle used to link a dynamic call site**. The JVM invokes it during the resolution/linking of an `invokedynamic` instruction, expecting a `java.lang.invoke.CallSite`. A BSM can be defined by a library/the JDK or by **the application itself**; there is no requirement that the class containing the BSM be loaded by the bootstrap class loader.

**Quick mnemonic:** *The bootstrap class loader answers “who defines this class?”; the bootstrap method of `invokedynamic` answers “which target should this dynamic call site be linked to?”*

The overlap of the word *bootstrap* carries the meaning of “setting up something initially” in two different contexts, with **no equivalence between them**. Even when a BSM is a method of a class loaded by the bootstrap loader (for example, `LambdaMetafactory`), that is a **characteristic of the example**, not a rule defining BSMs.

This lesson introduces the mechanisms at the class-loading and bytecode levels, the `CONSTANT_InvokeDynamic` / `BootstrapMethods` entries in the ClassFile, the roles of `MethodHandles.Lookup` and `CallSite`, common errors, along with a **compilable/runnable Java 17 program** and the `javap` command to observe them yourself.

## 1. Direct comparison table

| Criterion | Bootstrap class loader | Bootstrap method of invokedynamic |
| --- | --- | --- |
| Nature | Component of the class loading and definition mechanism in the JVM | Method handle/method used by the JVM to link a dynamic call site |
| Unit processed | A class/interface defined by the JVM from bytecode/runtime image | A call-site specifier of the `invokedynamic` bytecode |
| Purpose | Make a `Class<?>` exist with the right defining loader/type identity | Produce a linkage result as a `CallSite` with an appropriate target `MethodHandle` |
| Typical inputs | Class name, bytecode/module/source depending on the loader/runtime | Caller's `Lookup`, call-site name, `MethodType`, static bootstrap arguments |
| Result | A `Class<?>` definition usable by the JVM | A `CallSite`; dynamic invocations use the call site's target |
| Observation API | `Class.getClassLoader()`; `ClassLoader`; `jcmd`/class loading logs | `javap -v -p`: `InvokeDynamic`, `BootstrapMethods`; `java.lang.invoke` |
| Must it reside in application Java code? | The bootstrap loader is a runtime mechanism, not necessarily a regular Java `ClassLoader` object | A custom bootstrap method can be written in Java; usually declared public static and returning `CallSite` |
| Must they be related to each other? | No | No; a BSM being defined in a bootstrap-loaded class is just one possibility |
| Typical errors | `ClassNotFoundException`, `NoClassDefFoundError`, `LinkageError` related to loading/linking | `BootstrapMethodError` if BSM/call-site linkage is invalid or the BSM fails |

Both participate in the overall operation of the JVM, but **their starting points, goals, failure conditions, and lifecycles are different**.

## 2. Bootstrap class loader: defining foundational classes

A reference type in the JVM is identified by the pair:

~~~text
Type identity = (binary name, defining class loader)
~~~

The bootstrap class loader is the core foundational loader. The Java API uses `null` to represent it in `Class.getClassLoader()`; this is **not a NullPointerException and not “the class has not been loaded”**, but an intentional representation.

Typical Java 17 example:

~~~java
System.out.println(String.class.getClassLoader() == null);
System.out.println(
        java.lang.invoke.LambdaMetafactory.class.getClassLoader() == null);
~~~

This is a **fragment** that must be placed inside a method; both lines print `true` on a standard JDK 17.

### Role in the delegation model

A typical class-loading path:

~~~text
Custom/plugin class loader
          |
          v
Application/system class loader
          |
          v
Platform class loader
          |
          v
Bootstrap class loader
          |
          v
Appropriate foundational classes, e.g., java.lang.String
~~~

This is a generalized parent delegation model, with **no guarantee that every custom loader follows a single tree**. Java 9+ has a modular runtime image; do not assume that the bootstrap loader only reads from `rt.jar` (that file was removed in Java 9) or that every `jdk.*`/`javax.*` class is loaded by the bootstrap loader.

A normal custom loader is not allowed to define classes in packages starting with `java.` via `defineClass`; the API enforces restrictions and may throw `SecurityException`. Some foundational modules are assigned to the **platform loader**, so for a specific class, check `Class.getClassLoader()`/`Class.getModule()` rather than guessing solely from the package name.

### When does it operate?

The bootstrap class loader participates whenever the JVM needs to load the appropriate foundational classes: JVM startup, dependency resolution, using Java APIs, linking a method, or other initialization processes. **It is not invoked in the sense of “a BSM method running whenever a lambda is encountered”**. It is a **type-definition** mechanism, not a factory for dynamic call sites.

A normal application class when run with:

~~~bash
java BootstrapTerminologyDemo
~~~

is usually defined by the **system/application class loader**, whereas the foundational `java.lang.*`/`java.lang.invoke.*` classes in the example are defined by the bootstrap loader. Both can be used together during the linking of an `invokedynamic` instruction.

## 3. What is an invokedynamic bootstrap method?

`invokedynamic` is an opcode in the JVM instruction set, first introduced in Java 7 (JSR 292). Unlike fixed invocations such as `invokestatic` or `invokevirtual`, which have symbolic references to a method/class via their own mechanism, `invokedynamic` uses a **call-site specifier** in the constant pool to ask the JVM to **link a dynamic call site**.

Each `invokedynamic` is represented by a `CONSTANT_InvokeDynamic_info` entry in the constant pool and references an entry in the **`BootstrapMethods`** class-file attribute. This entry describes the BSM through a `CONSTANT_MethodHandle` along with static bootstrap arguments, if any.

~~~text
ClassFile containing the caller's method
  |
  +-- bytecode: invokedynamic #N
  |                   |
  |                   v
  +-- constant_pool[N]: CONSTANT_InvokeDynamic_info
  |           +-- call-site name + method descriptor
  |           +-- bootstrap_method_attr_index
  |                                 |
  |                                 v
  +-- BootstrapMethods attribute
              +-- bootstrap_method_ref
              |       (CONSTANT_MethodHandle)
              +-- bootstrap_arguments[]
                      |
                      v
         JVM resolves/links dynamic call site
                      |
                      v
         Invoke bootstrap method handle
                      |
                      v
              CallSite / target
                      |
                      v
      invokedynamic instruction invokes target
~~~

The BSM is not responsible for “loading the entire application”. Its role is to help the JVM determine the **MethodHandle target for a specific dynamic call site**. The JVM itself is responsible for managing resolution/linkage, checking the method type, and selecting the linkage result according to JVMS rules.

### Common BSM signature form

A typical BSM takes the first three arguments provided by the JVM:

~~~java
public static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String invokedName,
        MethodType invokedType,
        Object... staticArguments) throws Throwable
~~~

This is a **generalized signature**, not a standalone runnable method. Actual BSMs can use other fixed types for static arguments. The kinds of method handles permitted as bootstrap methods are also governed by JVMS rules; **do not claim that every BSM must be a public static Java method with this exact signature**. In practice, many useful BSMs are static methods.

Meaning:

- `caller` / `Lookup`: the caller class context and its corresponding lookup/access capabilities; do not confuse this with a JVM-wide default class loader.
- `invokedName`: the name of the dynamic call site per the constant pool, **not necessarily the name of an actual Java method on the called class**.
- `invokedType` / `MethodType`: the parameter/return types required by the `invokedynamic` instruction.
- `staticArguments`: arguments compiled into the `BootstrapMethods` entry; for example, `MethodType`s, `MethodHandle`s, or recipe strings for string concatenation.
- `CallSite`: the object holding a **target `MethodHandle`** compatible with the call-site descriptor.

After successful linkage, subsequent executions of the dynamic call site **do not need to invoke the BSM every time** to obtain the same linkage result. The JVM invokes the linked target according to `CallSite` rules. Certain conditions such as **concurrent resolution** can cause a BSM to be executed multiple times during linkage races; do not treat a BSM as a constructor guaranteed to run **exactly once globally**.

## 4. Why is a BSM not required to be loaded by the bootstrap class loader?

Consider two cases:

**Case A — foundational library:**

~~~text
Application class: Demo (application loader)
    |
    +-- bytecode invokedynamic (lambda)
           |
           +-- BSM handle points to LambdaMetafactory.metafactory
                    |
                    +-- LambdaMetafactory belongs to java.base,
                        usually bootstrap-loaded
                    |
                    +-- returns valid CallSite for lambda
~~~

**Case B — custom-written bootstrap method:**

~~~text
Application class: App (application loader)
    |
    +-- invokedynamic has BSM handle to com.acme.runtime.DynamicLinker
           |
           +-- DynamicLinker can also be application/plugin-loaded
           |
           +-- DynamicLinker.bootstrap(...) returns CallSite
~~~

For case B, the JVM still has to **resolve the class containing the BSM** and the method handle according to class loading/access rules. However, the fact that that class belongs to the application loader **does not disqualify the BSM from being a bootstrap method**. The word *bootstrap* here means **initializing linkage information for the call site**, not having to run inside the bootstrap class loader.

A public static Java method written by the application only becomes a **BSM of a call site** when the **ClassFile actually has an appropriate bootstrap method reference** and the JVM resolves the call site using it. Merely naming a method `bootstrap`, calling it from Java source, or importing `java.lang.invoke.*` **does not automatically generate an `invokedynamic` instruction pointing to that method**.

In ordinary Java source code, creating a custom `invokedynamic` call-site specifier usually requires a compiler/runtime that emits appropriate bytecode or a ClassFile generation/manipulation tool (ASM, Byte Buddy, a JVM language compiler, etc.). The example in the next section uses Java 17 `javac` to generate standard `invokedynamic` for lambdas and string concatenation, **without creating a custom BSM from plain source**.

## 5. Standalone Java 17 example: distinguishing both concepts at runtime

Create **a single file** `BootstrapTerminologyDemo.java`:

~~~java
import java.lang.invoke.LambdaMetafactory;

public class BootstrapTerminologyDemo {
    @FunctionalInterface
    interface TextTask {
        String run();
    }

    static String makeMessage(String name) {
        return "Hello, " + name;
    }

    public static void main(String[] args) {
        System.out.println("String bootstrap-loaded: " +
                (String.class.getClassLoader() == null));

        System.out.println("LambdaMetafactory bootstrap-loaded: " +
                (LambdaMetafactory.class.getClassLoader() == null));

        System.out.println("Demo application-loaded: " +
                (BootstrapTerminologyDemo.class.getClassLoader()
                        == ClassLoader.getSystemClassLoader()));

        TextTask task = () -> "lambda target";
        System.out.println("Lambda result: " + task.run());

        String name = args.length == 0 ? "Java" : args[0];
        System.out.println("Concat result: " + makeMessage(name));
    }
}
~~~

Compile and run with JDK 17 or later, in the directory containing the file:

~~~bash
javac --release 17 BootstrapTerminologyDemo.java
java BootstrapTerminologyDemo
~~~

**Exact stdout** for the command above in a standard JDK 17 environment:

~~~text
String bootstrap-loaded: true
LambdaMetafactory bootstrap-loaded: true
Demo application-loaded: true
Lambda result: lambda target
Concat result: Hello, Java
~~~

### What is each line measuring?

1. `String.class.getClassLoader() == null` demonstrates that `String` is a class defined by the **bootstrap class loader** by API convention.
2. `LambdaMetafactory.class.getClassLoader() == null` illustrates that the JDK library BSM is also housed in a **bootstrap-loaded class**. This **does not equate** the class loader with the bootstrap method.
3. `BootstrapTerminologyDemo.class.getClassLoader() == ClassLoader.getSystemClassLoader()` shows that under this standard classpath launch, the demo is a class belonging to the **application/system loader**.
4. The lambda expression `() -> "lambda target"` is compiled by standard Java 17 `javac` into a dynamic call site using `LambdaMetafactory.metafactory`; calling `task.run()` executes the string-returning implementation.
5. Dynamic string concatenation `"Hello, " + name` in `makeMessage` is compiled by a standard Java 17 compiler via the **`invokedynamic` mechanism with `StringConcatFactory.makeConcatWithConstants`**. The output is `Hello, Java`.

**Note on example determinism:** The printed lines are determined by the code and the standard classpath run. Details regarding the **number of `invokedynamic` instructions, the order of constant-pool entries, and bootstrap method indices** in `javap` may vary across JDK/compiler versions or compilation options; they **must not be treated as fixed stdout values**.

### 5.1. Inspecting bytecode with javap -v -p

Run:

~~~bash
javap -v -p BootstrapTerminologyDemo
~~~

The command above prints extensive ClassFile information. Look for the following strings:

~~~text
InvokeDynamic
BootstrapMethods:
LambdaMetafactory.metafactory
StringConcatFactory.makeConcatWithConstants
~~~

These are **the strings to look for in the disassembly**, not a complete copy of the `javap` output (constant pool indices vary). With the default `javac --release 17`, you should observe:

- An `invokedynamic` related to **lambda creation** for `TextTask`, whose BSM is `java/lang/invoke/LambdaMetafactory.metafactory`.
- At least one `invokedynamic` related to **string concatenation**, whose BSM is `java/lang/invoke/StringConcatFactory.makeConcatWithConstants`.
- A **`BootstrapMethods` attribute** in the ClassFile listing method handles and bootstrap arguments.
- One or more `InvokeDynamic` constant-pool entries pointing to the bootstrap information and the call site's name/type.

An **abbreviated illustrative snippet**, not the full compiler output:

~~~text
BootstrapMethods:
  ... REF_invokeStatic java/lang/invoke/StringConcatFactory.makeConcatWithConstants
  ... REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory
~~~

In the actual printout, `javap` includes method descriptors, constant-pool indices, and `Method arguments:`. The code `() -> "lambda target"` may also appear as a synthetic method `lambda$main$0` in the class containing the lambda. Names/indices and implementation layout may change; what matters is that **the call-site reference and BSM handle are recorded in the ClassFile by the compiler**.

### 5.2. Reverse-reading questions on the results

When `LambdaMetafactory` is loaded by the bootstrap class loader while the lambda resides in `BootstrapTerminologyDemo`:

- **Who defines `LambdaMetafactory.class`?** The bootstrap class loader, as shown by `getClassLoader() == null`.
- **Who defines `BootstrapTerminologyDemo.class`?** The application/system class loader in the demo.
- **Who decides how to link the lambda's `invokedynamic`?** The JVM uses the **bootstrap method handle** pointing to `LambdaMetafactory.metafactory` to obtain an appropriate `CallSite`.
- **Which “bootstrap” term applies when reading the `BootstrapMethods` attribute?** **The bootstrap method of call-site linkage**, not a list of classes loaded by the bootstrap class loader.

If the BSM is switched to an appropriate method defined by the application in another ClassFile, the loader containing the BSM can be an application/plugin loader, yet the `invokedynamic` mechanism still works by the same principle.

## 6. Detailed invokedynamic linkage cycle

It can be visualized through the following steps:

### Step A — the class containing invokedynamic is defined

A defining class loader (application loader, plugin loader, or another loader) defines the class containing `invokedynamic`. The JVM reads the ClassFile and the class's constant pool/attributes information.

**This does not mean every dynamic call site is already linked.** The JVM decides the appropriate resolution timing; do not assume rigidly that the BSM always runs right at `ClassLoader#defineClass` or only when the instruction is first executed.

### Step B — the JVM resolves the call-site specifier

When an `invokedynamic` needs to be linked, the JVM resolves the corresponding information:

~~~text
CONSTANT_InvokeDynamic_info
  bootstrap_method_attr_index
  name_and_type_index
       |
       v
BootstrapMethods[bootstrap_method_attr_index]
  bootstrap_method_ref
  bootstrap_arguments[]
~~~

The BSM method handle can point to a method in a class defined by **any appropriate class loader**. The process of resolving this method handle may trigger loading of related classes, but **it does not change the identity of already-defined classes**.

### Step C — the JVM passes arguments to the BSM

The JVM provides the caller context (`Lookup`), the `invokedynamic` name, the descriptor (`MethodType`), and the static bootstrap arguments. For example, `LambdaMetafactory.metafactory` uses the SAM method information, the target implementation method, and the instantiated method type to return a call site for the lambda.

For string concatenation, `StringConcatFactory` can use the recipe and constants to build a target that performs the appropriate string concatenation.

### Step D — the BSM returns a CallSite

`java.lang.invoke.CallSite` holds the target `MethodHandle`. Depending on the linkage goal, there are implementations such as:

- **`ConstantCallSite`:** the target does not change after being set; suitable for many stable dynamic call sites.
- **`MutableCallSite`:** the target can be changed via the API's mechanism; attention must be paid to visibility across threads.
- **`VolatileCallSite`:** intended to provide volatile-like target update visibility semantics in accordance with the API.

`invokedynamic` requires the method type of the call site/target to be compatible with the descriptor used. A BSM cannot return `null` or a CallSite with the wrong type and expect the JVM to coerce it arbitrarily; resolution will fail according to linkage rules.

### Step E — the invokedynamic instruction invokes the linked target

Once the call site is validly linked, `invokedynamic` uses the target `MethodHandle`. The JVM can optimize and JIT-compile the path; semantically, however, **the BSM establishes the linkage**, while **the target executes the call's logic**.

### Be careful with the statement “a bootstrap method only runs once”

For an already-linked call-site specifier, the BSM does not re-run on every execution of the target. However, when **multiple threads race to link** an unresolved call site, the JVMS allows the BSM to execute concurrently multiple times and then selects one result to link. Therefore:

- Do not place **critical exactly-once side effects** inside a BSM without an appropriate synchronization/idempotency design.
- Do not treat a BSM as a JVM-global singleton constructor.
- Multiple `invokedynamic` call sites can use the same BSM while still having their own separate linkage processes.
- Linkage may fail/cache failure conditions according to JVM rules, rather than always retrying on every invocation.

## 7. How does a custom-written BSM differ from a normal method?

In terms of **Java code**, a BSM can be a static method returning `CallSite`. Here is an **illustrative fragment**, not a directly runnable program and **not yet referenced by any `invokedynamic` instruction**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class DynamicLinker {
    public static String hello() {
        return "hello from target";
    }

    public static CallSite bootstrap(
            MethodHandles.Lookup caller,
            String name,
            MethodType invokedType) throws Throwable {

        MethodHandle target = caller.findStatic(
                DynamicLinker.class, "hello", invokedType);

        return new ConstantCallSite(target);
    }
}
~~~

Conditions for this BSM snippet to be used properly:

1. A ClassFile must contain **`CONSTANT_InvokeDynamic_info` / `BootstrapMethods`** referencing `DynamicLinker.bootstrap` via a valid method handle.
2. The call site's `invokedType` descriptor must match the target `DynamicLinker.hello`: in the example, taking no parameters and returning `String`.
3. `Lookup` must have access permission to the target method in the caller context (in this example `hello` is public), along with other linkage conditions.
4. The JVM resolves and invokes the BSM, and the BSM returns a `ConstantCallSite`. Only then is the target invoked by `invokedynamic`.

If you only write:

~~~java
DynamicLinker.bootstrap(lookup, "hello", methodType);
~~~

this is only a **regular Java method call** in source (with appropriate `lookup` and `methodType` variables). It does not automatically create an `invokedynamic` bytecode for the JVM to link using that BSM. **The difference lies in how the ClassFile points to the BSM in a call-site specifier**, not in whether the method is named `bootstrap` or where it is called from.

### A BSM can be application/plugin code

`DynamicLinker` can certainly be loaded by a valid custom/plugin class loader. It is still a BSM if it is resolved by the JVM from a caller class's `BootstrapMethods` attribute. Conversely, `LambdaMetafactory` in JDK 17 is a foundational class, yet **it is not the bootstrap class loader itself**; it is a class containing factory methods that can be used as BSMs.

## 8. invokedynamic, LambdaMetafactory, and string concatenation

Two cases where Java 17 `javac` commonly emits `invokedynamic` automatically without the source author having to write the opcode directly:

### 8.1. Lambda expression

~~~java
Runnable task = () -> System.out.println("work");
task.run();
~~~

This is a valid fragment inside a method. The compiler typically encodes **functional interface instance creation** using `invokedynamic`. The typical BSM is `LambdaMetafactory.metafactory` or another variant such as `altMetafactory` when additional properties are needed.

**Do not confuse these two points in time:**

- When the lambda-creating `invokedynamic` is linked, the BSM provides the call site/target for the mechanism that creates the functional-interface instance.
- When code calls `task.run()`, that is an **interface call on the created lambda object**; it does not mean the JVM calls `LambdaMetafactory.metafactory` again on every `run()`.

A lambda may be implemented by the JVM via a dynamically generated class or a hidden class in modern implementations, but **the backing class details are runtime internals**; do not write business logic assuming that the generated lambda class name, module name, or bytecode will always remain invariant.

### 8.2. String concatenation with +

~~~java
String who = "Java";
String greeting = "Hello, " + who;
~~~

If the compiler determines that the expression has a dynamic part, default Java 17 `javac` typically emits an `invokedynamic` involving `StringConcatFactory.makeConcatWithConstants`. **All-constant** concatenations can be constant-folded at compile time and **do not need invokedynamic**.

In the demo in section 5, `makeMessage(String name)` receives a runtime argument, so the dynamic string concatenation path is visible via `javap -v -p`.

### 8.3. On other JVM languages

`invokedynamic` was designed to support JVM-managed dynamic linkage, which is useful for compilers and runtimes of other JVM languages or flexible call-site mechanisms. It does not serve only lambdas/string concatenation. A BSM can supply a target customized by the call-site name, signature, and static args, as long as it adheres to the linkage contract.

## 9. Distinguishing from ConstantDynamic (condy)

In modern Java ClassFiles there is also `CONSTANT_Dynamic_info`, commonly called a **dynamic constant** or *condy*. It also uses the **`BootstrapMethods` attribute** to describe a bootstrap method, but its goal is different:

| Mechanism | What is the bootstrap method used to produce? |
| --- | --- |
| **`CONSTANT_InvokeDynamic_info` / invokedynamic** | A **`CallSite`** to link a dynamic call site. |
| **`CONSTANT_Dynamic_info` / dynamic constant** | A resolved **constant value** of the requested type, not requiring a CallSite. |

A condy BSM has similar initial arguments, except the target type argument is the constant's **`Class<?>`** rather than a call site's `MethodType`; the result is a constant value according to JVM rules. Do not see `BootstrapMethods` in a ClassFile and assume it is always metadata exclusive to `invokedynamic`.

Both remain distinct from the **bootstrap class loader**: a condy BSM is likewise not required to live in a class defined by the bootstrap class loader.

## 10. Common errors: loading failures vs. bootstrap linking failures

| Symptom | Mechanism to investigate | Hints |
| --- | --- | --- |
| `ClassNotFoundException` when a custom loader looks up a class | **Class loading** | Classpath/module path, binary name, parent delegation, byte source. |
| `NoClassDefFoundError` when a dependency definition is needed | **Class loading/linking** | Missing class, prior initialization failure, loader visibility. |
| `ClassCastException: A cannot be cast to A` | **Type identity** | Two different defining loaders defined the same name; the BSM itself is not necessarily at fault. |
| `SecurityException` when trying to define `java.*` | **Protected platform namespace** | Do not override foundational classes using an application loader. |
| `BootstrapMethodError` when using invokedynamic | **Bootstrap linkage** | Wrong BSM method handle, BSM throws an exception, returns `null`/a `CallSite` of the wrong type, dependency access permissions. |
| `WrongMethodTypeException` at MethodHandle invocation | **Method handle signature/type** | `MethodType`, `invokeExact`/`invoke`, and adaptation capability. |
| `IllegalAccessError`/access error | **Resolution/module access** | Caller lookup, `exports`/`opens`, member access, and defining loader. |
| `ExceptionInInitializerError` from static initializer | **Class initialization** | `<clinit>` throws an exception; this is a different phase from the BSM linking a call site. |

`BootstrapMethodError` belongs to the `LinkageError` family. It usually indicates a failure in resolving/bootstrapping a dynamic call site or dynamic constant; **it does not mean the bootstrap class loader is broken**. When you encounter this error, read the full stack trace and **cause**, and inspect the method handle/BSM being used and the type expected by the site.

A BSM can fail due to a target method handle with a mismatched descriptor, insufficient access permissions, an exception in user code, or missing dependency configuration. You should check both the **ClassFile** and the **loader that defined the BSM class**, rather than trying to fix it by forcing the BSM into the bootstrap loader.

### Conditions that cannot be overlooked

- The returned `CallSite` must be non-null and have a target `MethodHandle` whose type matches the invokedynamic descriptor.
- If using `ConstantCallSite`, the target is stable; `MutableCallSite`/`VolatileCallSite` have their own update semantics, rather than “re-linking on every call”.
- The BSM is invoked by the JVM **during linking**; errors may arise lazily when the call site is resolved, not necessarily immediately when the class containing the bytecode is loaded.
- The BSM method handle/caller context is subject to resolution/access checks just like other related symbolic references. A class loader's name does not automatically grant permission to bypass JPMS.
- Do not swallow `BootstrapMethodError` and try running some arbitrary alternative method without a specifically designed fallback; doing so can mask serious ABI/linkage bugs.

## 11. Practical diagnostics: inspecting class loader and bytecode from both directions

When encountering a class that uses lambdas/strings or a framework with dynamic bytecode, investigate in this order:

### Step 1 — which class contains invokedynamic?

Run:

~~~bash
javap -v -p -classpath . BootstrapTerminologyDemo
~~~

Identify the method containing `invokedynamic`, the `InvokeDynamic` constant-pool entry, and the `BootstrapMethods` section. If the class is inside a JAR, use the appropriate classpath instead of `.` and the corresponding binary class name.

### Step 2 — where does the bootstrap method handle point?

In `BootstrapMethods`, look for the owner/BSM name:

~~~text
java/lang/invoke/LambdaMetafactory.metafactory
java/lang/invoke/StringConcatFactory.makeConcatWithConstants
com/acme/runtime/DynamicLinker.bootstrap
~~~

These are **example symbolic names**, not assumed to coexist in a single ClassFile. In the program from section 5, only the first two are present.

### Step 3 — which loader defines the caller, BSM owner, and API types?

Example **fragment**:

~~~java
System.out.println(callerClass.getClassLoader());
System.out.println(bsmOwnerClass.getClassLoader());
System.out.println(callerClass.getModule());
System.out.println(bsmOwnerClass.getModule());
~~~

This snippet requires two valid `Class<?>` variables `callerClass` and `bsmOwnerClass`. Do not replace `bsmOwnerClass` with `BootstrapMethods`: **an attribute is not a Java class**. Seeing `null` from `getClassLoader()` usually indicates that the defining loader is the bootstrap loader, **not proof that a method is being used by the JVM as a BSM**.

### Step 4 — check the signature and bootstrap arguments

An `invokedynamic` BSM must accept arguments according to the JVMS and return a `CallSite` with the right signature. For `LambdaMetafactory`, check the functional interface, implementation method handle, and instantiated method type. For `StringConcatFactory`, check the recipe/constants and matching dynamic argument count.

### Step 5 — separate three causes that are often conflated

1. **The loader cannot find the BSM owner or a dependency**: an initial loading/visibility error.
2. **The BSM owner is loaded, but the BSM invocation fails**: a bootstrap linkage error.
3. **The BSM links successfully, but the target/user logic fails at runtime**: this may be an exception from the target, **not necessarily `BootstrapMethodError`**.

Observation tools can help, though they should not be conflated:

- `-Xlog:class+load=info` (HotSpot Java 17) can help observe the source/classes being loaded.
- `javap -v -p` helps inspect `invokedynamic`/`BootstrapMethods` in the compiled file.
- Stack trace/cause and thread dumps help distinguish BSM errors, initialization errors, and target code errors.
- `Class.getClassLoader()` / `Class.getModule()` information helps track type identity/module.

Example run with logging:

~~~bash
java -Xlog:class+load=info BootstrapTerminologyDemo
~~~

**There is no fixed stdout** for this command because logging produces many lines depending on the JDK/runtime and environment; focus on the source class and loader, and do not treat the log as a replacement for `javap`.

## 12. Common misconceptions

**“A bootstrap method must be loaded by the bootstrap class loader.”** False. A BSM is a method handle for linking a call site; the BSM owner can be an application/plugin class if the JVM can resolve and validly access it.

**“`LambdaMetafactory` is the bootstrap class loader.”** False. `LambdaMetafactory` is **a class** that provides factory methods such as `metafactory`; the bootstrap class loader is the component that loads that class. The two entities are completely different in nature.

**“If `SomeClass.class.getClassLoader() == null`, then the methods in that class are all bootstrap methods.”** False. `null` refers to the loader that **defined the Class**, not which methods appear in a caller's `BootstrapMethods` attribute.

**“Every string concatenation in Java 17 needs a BSM.”** False. The compiler can fold constants at compile time. Only concatenation involving dynamic values is typically encoded by `javac` via StringConcatFactory.

**“invokedynamic means the JVM skips type checking.”** False. The call-site descriptor, MethodHandle target, verifier, and access rules are still checked; dynamic linkage is not a mechanism for disabling type safety.

**“The BSM re-runs every time a lambda or target is called.”** False. The BSM participates in linking the call site; the target runs when invokedynamic is executed after linkage. There is an exception for resolution races, but the BSM is not re-invoked for every invocation.

**“A BSM is always invoked exactly once.”** Also false. The JVM may execute the bootstrap method more than once under concurrent resolution for the same site and then select an appropriate result. Do not rely on a BSM as a once-only hook for side effects.

**“Changing the thread's class loader is the way to fix BootstrapMethodError.”** There is no such rule. TCCL only affects APIs that use the context loader; linking a symbolic BSM/call site still depends on the ClassFile owner, access, method type, module, and appropriate defining loader.

**“BootstrapMethods only appears for invokedynamic.”** Not entirely: dynamic constants (`CONSTANT_Dynamic`) also use the bootstrap methods attribute.

**“Clicking on a lambda expression in source shows the BSM.”** Not quite. Lambda source does not declare a BSM directly; the compiler writes `invokedynamic`/`BootstrapMethods` into the ClassFile. Use `javap -v -p` to prove it.

## 13. Knowledge self-check

**Question 1.** What does `String.class.getClassLoader() == null` indicate?

**Answer:** `String` is defined by the bootstrap class loader according to the Java API representation. It does **not** mean that the constructor or every method of `String` is a BSM.

**Question 2.** `LambdaMetafactory.metafactory` is listed by `javap` under `BootstrapMethods`. Is this a class loader or a method used to link a call site?

**Answer:** A **bootstrap method** used in `invokedynamic` linking; the fact that the `LambdaMetafactory` class is loaded by the bootstrap loader is a separate matter.

**Question 3.** Is a custom BSM in `com.acme.DynamicLinker` (application loader) valid?

**Answer:** It can be valid if the ClassFile has a valid BSM method handle, the JVM can resolve/access the class/method, and the BSM returns a `CallSite` with the right method type. It is not required to belong to the bootstrap loader.

**Question 4.** What does an invokedynamic BSM typically return?

**Answer:** A `java.lang.invoke.CallSite` (for example, `ConstantCallSite`) with an appropriate target method handle.

**Question 5.** Who supplies `Lookup`, `name`, and `MethodType` to the BSM?

**Answer:** The JVM, based on the call-site specifier/constant pool information and the caller context when linking `invokedynamic`.

**Question 6.** If the target method has already been linked, does the JVM have to call the BSM again on every target execution?

**Answer:** No. The call site holds the target according to the semantics of the `CallSite` type; the BSM belongs to the link phase, whereas the target belongs to the execution phase.

**Question 7.** Does a `BootstrapMethodError` prove that the bootstrap class loader is broken?

**Answer:** No. It signals a bootstrap linking problem (or dynamic constant resolution problem) and requires checking the BSM handle, arguments, method types, and cause.

**Question 8.** Why does `javac --release 17` usually generate `invokedynamic` for lambdas without requiring the user to write a BSM?

**Answer:** The Java compiler automatically generates `CONSTANT_InvokeDynamic_info` and `BootstrapMethods` referencing libraries such as `LambdaMetafactory`. The JVM performs linking according to that metadata at runtime.

## Key takeaways

- **Bootstrap class loader** = the foundational class loader, which helps **define Class<?>**; classes defined by it return `null` from `Class.getClassLoader()`.
- **Bootstrap method of invokedynamic** = a method handle used to **link a call site**, typically receiving `Lookup` + name + `MethodType` + static args and returning a `CallSite`.
- Both concepts contain the word *bootstrap*, yet they have **different responsibilities**. A BSM can reside in the JDK or an application class; it **is not restricted to running inside a bootstrap-loaded class**.
- Observe class loading with `Class.getClassLoader()`; observe dynamic linking with `javap -v -p`, `InvokeDynamic`, and `BootstrapMethods`.
- When debugging, distinguish between **class loading failure, bootstrap-linking failure, and target execution errors**; do not infer from `BootstrapMethodError` that the bootstrap class loader is broken.

**Java SE 17 standard references:**

- *Java Virtual Machine Specification*, §5.3 (Creation of Classes and Interfaces), §5.4.3.6 (Dynamically-Computed Call Site and Constant Resolution): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- *Java Virtual Machine Specification*, §4.4.10 (`CONSTANT_Dynamic`/`CONSTANT_InvokeDynamic`), §4.7.23 (`BootstrapMethods`): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- *Java Virtual Machine Specification*, §6.5, `invokedynamic`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
- Java SE 17 API, `ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `java.lang.invoke.LambdaMetafactory`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html
- Java SE 17 API, `StringConcatFactory`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html
- Java SE 17 API, `CallSite`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html
