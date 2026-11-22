# Resolution: Resolving Symbolic References in the Java Class Lifecycle

**Resolution (symbolic reference resolution)** is a stage of **linking** in the class lifecycle on the JVM. When compiling Java source code, the compiler usually cannot yet bind usages of classes, fields, and methods to specific runtime objects. Instead, the class file stores **symbolic references**: information describing the name and type of the target to be accessed. When resolution takes place, the JVM converts such a reference into the corresponding runtime entity, while performing related checks such as member lookup, access permissions, and class loader constraints.

This is a major reason why **compilation succeeds yet the application still fails at runtime**: the method name remains in the application's bytecode, but the JAR loaded at runtime has changed its API; the class exists, but access is not permitted; or the same class name is defined by an incompatible class loader.

## 1. Putting Resolution in the Right Place

```text
.java
  │ javac: parses source, checks types, generates class file
  ▼
.class: bytecode + constant pool containing symbolic references
  │
  ▼
Loading: loader finds/defines class in the JVM
  │
  ▼
Linking
  ├─ Verification: is bytecode/class file valid?
  ├─ Preparation: creates and sets default values for static fields
  └─ Resolution: symbolic reference → runtime target + linking checks
          │
          ├─ Can be performed early during linking
          └─ Can be deferred until the reference is used
  │
  ▼
Initialization when Java requires active use
  │
  ▼
Execute methods, create objects as needed
```

The diagram illustrates **logical relationships**, without forcing resolution to finish completely before initialization. According to the JVM Specification, verification and preparation must complete before initialization, but the JVM can resolve symbolic references **eagerly** (early) or **lazily** (on demand). Some resolutions may continue after the class has been initialized. If resolution detects an error, the JVM must report the error at the point when the program directly or indirectly uses the offending reference.

| Step | Key question | Distinction from resolution |
| --- | --- | --- |
| Loading | Which class data is brought into the JVM, and which class loader defines it? | Having a runtime class does not mean every member reference has been resolved. |
| Verification | Are the format, structure, and bytecode valid? | Checking bytecode differs from determining the target for each symbolic reference. |
| Preparation | What default values do static fields have? | Most Java static initializers have not yet been executed. |
| **Resolution** | Which runtime class, field, method, or call site does this name/descriptor point to? | May involve loading and access checks; not synonymous with calling a method. |
| Initialization | Have `static` blocks and static initializers been executed yet? | Usually triggered by `new`, `getstatic`, `putstatic`, `invokestatic`, or other active uses. |
| Method selection | For the actual receiver object, which implementation is chosen? | Typically occurs when running `invokevirtual`/`invokeinterface` after the method reference has been resolved. |

Do not treat the order above as the exact execution trace of every JVM. Resolution is a concept specified at the JVM level; how a JVM caches information or performs in-memory optimizations is an implementation detail.

## 2. Where Do Symbolic References Come From?

A `.class` file has a **constant pool**, containing string literals, constant values, names/descriptors, and entries describing references. The JVM constructs a corresponding **run-time constant pool** for the created class. Many bytecode instructions point into it by **index**, rather than carrying the machine address of the class or method.

Java example:

```java
int n = Calculator.total;
String text = Calculator.format(n);
```

The compiler may generate symbolic references similar to:

```text
CONSTANT_Fieldref       demo/Calculator.total:I
CONSTANT_Methodref      demo/Calculator.format:(I)Ljava/lang/String;
```

Here:

- `demo/Calculator` is the internal name of the class in the class file; the corresponding Java binary name is `demo.Calculator`.
- `total` is the field name; the descriptor `I` means `int`.
- `format` is the method name; the descriptor `(I)Ljava/lang/String;` means it takes an `int` and returns `java.lang.String`.
- The field/method name and **descriptor** form the member identifier required by the bytecode. A method's JVM descriptor also includes its return type; looking only at the name `format` is not enough to understand a reference in the constant pool.

This is a simplified descriptive syntax for learning, not a required JAR path. Actual entries have `#...` indices, `Class`/`NameAndType` links, and bytecode offsets; use `javap -verbose` to see the exact structure.

Common reference forms:

| Constant-pool entry | Represents | Related bytecode(s) |
| --- | --- | --- |
| `CONSTANT_Class` | Class/interface/array type | `new`, `checkcast`, `instanceof`, `anewarray`, `ldc` with a class literal |
| `CONSTANT_Fieldref` | Field by owner, name, and field descriptor | `getfield`, `putfield`, `getstatic`, `putstatic` |
| `CONSTANT_Methodref` | Class method by name and method descriptor | `invokevirtual`, `invokespecial`, `invokestatic` |
| `CONSTANT_InterfaceMethodref` | Method referenced through an interface | `invokeinterface`; some calls to static/private interface methods depending on the opcode |
| `CONSTANT_MethodType` | Call type including parameters and return type | `ldc` for a method-type constant |
| `CONSTANT_MethodHandle` | Field-access/method-invocation behavior by reference kind | `ldc` and bootstrap components |
| `CONSTANT_Dynamic` | Constant value computed via a bootstrap method | `ldc`/`ldc_w`/`ldc2_w` depending on the type |
| `CONSTANT_InvokeDynamic` | Dynamically linked call-site descriptor | `invokedynamic` |

Name/descriptor entries such as `CONSTANT_Utf8` and `CONSTANT_NameAndType` are structural components of references. Do not assume that every string or number in the constant pool goes through field/method resolution.

## 3. Resolution Mechanism: From Name to Runtime Target

Consider an instruction such as `getstatic demo/Calculator.total:I` in the bytecode of `demo.Main`:

1. **Obtain the symbolic reference.** The bytecode points to the `Fieldref` entry in the run-time constant pool of the class containing the instruction.
2. **Resolve the owning class/interface.** The JVM uses the defining loader of the class containing the reference to create/look up the owning class according to loading and delegation rules, thereby determining the correct runtime type instead of searching for the class by name string alone.
3. **Look up the matching field/method.** For a field, the JVM uses the name and descriptor and searches according to JVM lookup rules. For a method or interface method, the lookup rules differ and may consider superclasses/superinterfaces.
4. **Check access and loading constraints.** Is the member actually accessible from the referencing class? Are the types appearing in the descriptor consistent across the relevant defining loaders?
5. **Succeed or fail.** If successful, the JVM obtains the corresponding runtime result for the reference; if it fails, the appropriate linkage error is reported. Instruction-specific conditions such as static/instance can also cause linkage errors.
6. **Continue instruction semantics.** For example, `getstatic` may cause the class declaring the field to be initialized before reading the value; `invokevirtual` will further select the implementation based on the receiver's runtime class.

The reference `demo.Calculator` is resolved in the context of **the class containing the constant-pool entry**, rather than randomly picking a class with that name across the entire process. This determines the correctness of plugin architectures that use multiple class loaders.

### Why Is It Not "Replacing a Name String with a Machine Address"?

Under the specification, the result of resolution can be a class/interface, field, method, `MethodType`, `MethodHandle`, or a runtime constant/call site. A JVM implementation may store lookup data in a cache or optimized structures, but **there is no standard Java interface that returns a native pointer** for a constant-pool entry. Use the wording "**binding a symbolic reference to a runtime entity**" instead of assuming every case becomes a function address.

## 4. Specific Resolution Cases

### 4.1. Class and Interface Resolution

For a reference from class `D` to a type named `N`:

- The JVM uses **`D`'s defining loader** to request the creation/lookup of the type named `N`. The loader may delegate to its parent. The class actually created may have a **different defining loader** from the loader that initially received the request.
- If the reference is an array class with reference-type elements, resolution involving the element type is also handled according to the corresponding rules.
- The JVM checks `D`'s access permissions to the target type.

If that type cannot be found/created, resolution may fail due to a loading error. If the class exists but `D` is not permitted to access it, resolution may report `IllegalAccessError`. The existence of a `.class` file in a JAR does not by itself guarantee that the JVM can resolve to it.

For example, named modules also require considering **module readability/exports**; a public type in a package not exported to the requesting module can still lack valid access from that module. Runtime access rules consider packages, modules, and class loader identity under the Java Platform Module System, not only the `public` keyword.

### 4.2. Field Resolution

A `Fieldref` identifies the **target class/interface, field name, and field descriptor**. After resolving the class, the JVM looks up the field declared in that class, continuing according to lookup rules across superinterfaces and superclasses. If no matching name **and descriptor** are found, the JVM throws `NoSuchFieldError`; if found but the caller lacks access permissions, it may be `IllegalAccessError`.

**Field resolution** must be distinguished from instruction checks: `getfield` requires an instance field, whereas `getstatic` requires a static field. If a binary API changes a static field to an instance field while the caller's bytecode still uses the old opcode, the error can be `IncompatibleClassChangeError`, even though the field name and descriptor still match.

Descriptor examples:

```text
int count                → count:I
long total               → total:J
String label             → label:Ljava/lang/String;
int[] numbers            → numbers:[I
String[] names           → names:[Ljava/lang/String;
```

### 4.3. Class Method Resolution

For a `Methodref`, the JVM first resolves the owning class and then looks up the matching method, including special rules for superclasses and default interface methods. If no method is found by name and descriptor, the result is typically `NoSuchMethodError`. If a `Methodref` entry instead points to an interface where the rules require a class, the JVM may report `IncompatibleClassChangeError`.

Constructors have the special JVM name `<init>`; class initializers are `<clinit>`. Do not treat `<clinit>` as an ordinary method that can be invoked directly from Java source code.

A seemingly minor source-level change can still break compatibility at the bytecode level:

```text
Before: String version() → descriptor ()Ljava/lang/String;
After:  int version()    → descriptor ()I
```

The already-compiled old caller still expects `()Ljava/lang/String;`. If only `()I` is present at runtime, Java does not automatically "convert the return type" to salvage the link. The runnable example in practice section B will observe this error.

### 4.4. Interface Method Resolution

For an `InterfaceMethodref`, the JVM must resolve an **interface**, look up the method with the requested name/descriptor, and follow the rules for inherited methods (including default method scenarios). It cannot be mechanically replaced by the class lookup algorithm. If the runtime class implementing the interface differs from the caller's expectations, resolution and/or method selection may encounter an error.

Two distinct stages:

- **Interface method resolution:** determines which method the reference from the `invokeinterface` bytecode denotes at the declaration/type-system level.
- **Method selection:** when the instruction actually invokes the method, inspects the **receiver's runtime class** to select the appropriate implementation (for example, `EnglishGreeting` or `VietnameseGreeting`).

Therefore, "resolving a method" does not necessarily mean fixing one implementation for every receiver instance of the call.

### 4.5. Method Type, Method Handle, Dynamic Constant, and `invokedynamic`

Modern Java also includes these kinds of resolution:

- **Method type:** resolves the classes/interfaces appearing in the descriptor; the result is a `java.lang.invoke.MethodType`.
- **Method handle:** resolves field-access/method-invocation behavior according to the reference kind; checks the applicable conditions and creates a `java.lang.invoke.MethodHandle`.
- **Dynamically-computed constant (`CONSTANT_Dynamic`):** a bootstrap method produces a value based on constant-pool information and bootstrap arguments. After successful resolution, the result is retained for the reference; the bootstrap does not automatically re-run each time that constant is read.
- **`invokedynamic` call site:** the JVM resolves the bootstrap method, arguments, and resulting `CallSite`. For this kind, resolution is tied to a **specific `invokedynamic` instruction**, even when multiple instructions reference the same constant-pool entry.

Common practical examples are lambda expressions and modern string concatenation. The details depend on how the compiler generates the class file; Java source containing `+` or a lambda is **not enough to assert** when the bootstrap is run. Use `javap -v` to identify `InvokeDynamic` and `BootstrapMethods` in the actual build.

If the bootstrap is invalid or fails, a `BootstrapMethodError` may occur. These cases are dynamic linking according to the JVM specification, not ordinary "reflection".

## 5. When Does Resolution Happen? Does a Reference Have to Be Resolved Multiple Times?

Within a defined class, the JVM may resolve a symbolic reference before an instruction uses it (eager) or when needed (lazy), within the limits of the JVMS. A successful resolution is remembered per reference; if it fails, subsequent uses of that reference continue to encounter the corresponding error. **The time an error is detected inside the JVM may differ from the time the error becomes observable in the program.** The API version-change experiment above illustrates the consequences of binary incompatibility; the next article delves into where errors surface under eager/lazy resolution.

## 6. Practice A — Inspecting Symbolic References with `javap`

Create the exact file structure:

```text
resolution-lab/
└── src/
    └── demo/
        ├── Library.java
        └── Main.java
```

**File `src/demo/Library.java`:**

```java
package demo;

public final class Library {
    public static int number = 7;

    static {
        System.out.println("Library initialized");
    }

    public static String greet(String name) {
        return "Hello, " + name;
    }
}
```

**File `src/demo/Main.java`:**

```java
package demo;

public class Main {
    public static void main(String[] args) {
        System.out.println("start");

        Class<?> type = Library.class;
        System.out.println("literal=" + type.getName());

        System.out.println("before field");
        System.out.println("number=" + Library.number);
        System.out.println("call=" + Library.greet("Java"));
    }
}
```

From the `resolution-lab` directory, compile and run using JDK 17+:

```sh
javac --release 17 -d out src/demo/Library.java src/demo/Main.java
java -cp out demo.Main
```

**Stdout:**

```text
start
literal=demo.Library
before field
Library initialized
number=7
call=Hello, Java
```

Explanation:

- `Library.class` is a class literal: it requires the corresponding `Class` representation, but is not an active use that triggers `Library` initialization. Do not infer from this the exact print line at which loading or resolution occurs inside the JVM.
- `Library.number` is a **non-final static field**. `getstatic` requires a valid field reference and requires the class declaring the field to be initialized; therefore, the line `Library initialized` is printed **before** `number=7`.
- `Library.greet("Java")` uses `invokestatic`. At this point, the class has already been initialized, so the static block does not run again. The concatenation logic inside `greet` may use `invokedynamic` when compiled with JDK 17.
- The stdout order reflects **observable side effects**; it does not prove that the JVM performed lazy resolution at a specific offset.

Inspect the class file without modifying its contents:

```sh
javap -classpath out -c -p demo.Main
javap -classpath out -v demo.Main
```

In `javap -c`, look for the instructions corresponding to reading the field and calling the method:

```text
getstatic     ...  // Field demo/Library.number:I
invokestatic  ...  // Method demo/Library.greet:(Ljava/lang/String;)Ljava/lang/String;
```

The `...` placeholders represent indices/offsets generated by the tool, **not the complete verbatim output**. In `javap -v`, the `Constant pool` section explains each `Fieldref`, `Methodref`, `Class`, and `NameAndType` entry. The `#n` indices may change when editing the source, changing the compiler, or switching JDKs. The constant pool table shows **what needs to be resolved**; it does not confirm when the JVM actually performed resolution at runtime.

To test how the compiler eliminates some references, try changing `Library.number` to `public static final int number = 7;` and recompiling. Now it is a **constant variable**, so the compiler typically inlines the value at the use site, meaning there may no longer be a `getstatic` instruction for that read. Check `javap` before drawing conclusions. Once the value is inlined, reading it does not require initializing `Library`, although the subsequent `greet` call is still an active use.

## 7. Practice B — Swapping the Runtime JAR Causes `NoSuchMethodError`

This is an experiment on **binary compatibility**: compile against API version 1, then run with an **incompatible** version 2. No manual bytecode editing is needed.

Create three separate source files:

```text
resolution-compat/
└── src/
    ├── v1/
    │   └── api/
    │       └── Service.java
    ├── v2/
    │   └── api/
    │       └── Service.java
    └── client/
        └── demo/
            └── Client.java
```

**`src/v1/api/Service.java`:**

```java
package api;

public class Service {
    public static String version() {
        return "v1";
    }
}
```

**`src/v2/api/Service.java`:**

```java
package api;

public class Service {
    public static int version() {
        return 2;
    }
}
```

**`src/client/demo/Client.java`:**

```java
package demo;

import api.Service;

public class Client {
    public static void main(String[] args) {
        System.out.println("before");
        try {
            System.out.println(Service.version());
        } catch (NoSuchMethodError error) {
            System.out.println(error.getClass().getSimpleName());
        }
    }
}
```

From the `resolution-compat` directory, using JDK 17+:

```sh
javac --release 17 -d out-v1 src/v1/api/Service.java
javac --release 17 -cp out-v1 -d out-client src/client/demo/Client.java
javac --release 17 -d out-v2 src/v2/api/Service.java
```

Run the baseline check with API v1 on **Windows PowerShell/CMD**:

```powershell
java -cp "out-client;out-v1" demo.Client
```

**Correct stdout:**

```text
before
v1
```

Then run with API v2 on **Windows** (without recompiling Client):

```powershell
java -cp "out-client;out-v2" demo.Client
```

**Correct stdout:**

```text
before
NoSuchMethodError
```

On Linux/macOS, replace the `;` classpath separator with `:`, for example `-cp "out-client:out-v2"`. When running the experiment, do not put both `out-v1` and `out-v2` on the same classpath: we intentionally select **one** version of `api.Service` at runtime.

**JVM-level explanation:**

1. During `Client` compilation, the compiler sees the method `api.Service.version:()Ljava/lang/String;`.
2. The `Client.class` bytecode keeps a symbolic method reference with a **String return type**.
3. When running with `out-v2`, the JVM can find the `api.Service` class, but it only contains `version:()I`.
4. The old method reference cannot find a method with the matching name and descriptor; the JVM reports `NoSuchMethodError` at the point of use. The `try/catch` in the example catches that exact error to keep stdout concise.
5. The proper fix is to provide a binary-compatible API version or recompile the client and all affected components against the new contract; changing the classpath incidentally may hide the error, but does not solve version management.

Use the bytecode inspection commands to cross-check for yourself:

```sh
javap -classpath out-client -v demo.Client
javap -classpath out-v1 -s api.Service
javap -classpath out-v2 -s api.Service
```

With `javap -s`, v1 contains the descriptor `()Ljava/lang/String;`, while v2 contains `()I`. At the source level, Java does not allow declaring two methods with the same name and parameter list that differ only in return type within the same class; this example uses two mutually replacing builds, not a valid overload.

## 8. Practice C — Resolution Is Not Dynamic Dispatch

An `invokeinterface` call can resolve a reference to a method declared in an interface, and then **method selection** chooses the code based on the runtime type of the receiver.

Create **a single** file `DispatchDemo.java` (the auxiliary types are not `public`, so they are allowed in the same file):

```java
package demo;

interface Greeting {
    String say();
}

class EnglishGreeting implements Greeting {
    @Override
    public String say() {
        return "Hello";
    }
}

class VietnameseGreeting implements Greeting {
    @Override
    public String say() {
        return "Xin chao";
    }
}

public class DispatchDemo {
    public static void main(String[] args) {
        Greeting greeting = new EnglishGreeting();
        System.out.println(greeting.say());

        greeting = new VietnameseGreeting();
        System.out.println(greeting.say());
    }
}
```

Save it at `src/demo/DispatchDemo.java` in a separate practice directory, then run:

```sh
javac --release 17 -d out src/demo/DispatchDemo.java
java -cp out demo.DispatchDemo
javap -classpath out -c demo.DispatchDemo
```

**The two stdout lines from the `java` command:**

```text
Hello
Xin chao
```

The subsequent `javap` command will additionally print the disassembly, which is not included in the two stdout lines above. In `main`, the two calls through the `Greeting`-typed variable typically appear as `invokeinterface demo/Greeting.say:()Ljava/lang/String;`. The interface-level reference remains the same, while the first instance is `EnglishGreeting` and the second instance is `VietnameseGreeting`; selecting which method is actually invoked depends on the receiver. There may not be a "single method address" used for all instances once the interface reference has been resolved.

Key distinctions:

- **Resolution:** Is `Greeting.say:()Ljava/lang/String;` a valid reference to the interface method?
- **Selection:** For the object receiving the call, which implementation fulfills this contract?
- **Invocation:** The JVM executes the selected method and returns the result.
- **Initialization:** Initialization of the required classes occurs according to their respective triggers when creating instances and calling static members.

## 9. Class Loader, Runtime Identity, and Loading Constraints

In the JVM, the identity of a runtime class/interface is based on the **pair (binary name, defining loader)**. Two plugin loaders can define two `api.Dto` classes with the same name yet **different types**. Resolution across loaders may obtain incompatible runtime definitions even though the source package is identical.

Conceptual example:

```text
AppLoader      defines api.Dto (type A)
PluginLoader   defines api.Dto (type B)

api.Dto of AppLoader != api.Dto of PluginLoader
```

When linking a field or method whose descriptor contains types spanning loader boundaries, the JVM can apply **loading constraints** to ensure that the same type name in a linkage signature must resolve to the same runtime class/interface. If a constraint is violated, a `LinkageError` may occur. This protects type safety, especially in plugin systems or application servers.

Use these inspection points:

```java
Class<?> type = object.getClass();
System.out.println(type.getName());
System.out.println(type.getClassLoader());
```

This is an **illustrative** snippet; an `object` variable is needed in an actual program. Note that `getClassLoader() == null` typically means the class was defined by the **bootstrap loader**, not an error. To find out where a specific class comes from, examine the runtime module/classpath or class-loading logs together with defining loader information.

**Module access:** If a public type resides in a named module whose package is not exported to the caller module, symbolic resolution can still fail due to access permissions. "Having a class file on the module path" is not enough.

**Scope boundary:** The content above discusses runtime linkage, which differs from generics type erasure and Spring dependency injection. Do not assume that the word "resolution" across every library means the same thing as JVM `5.4.3`.

## 10. Diagnosing Errors: At Which Step Does the Error Occur?

| Symptom | Common scenario | What to check |
| --- | --- | --- |
| `ClassNotFoundException` | `Class.forName`/`ClassLoader.loadClass` API cannot find the requested name | Fully qualified name, loader used, JAR/classpath/module path; this is a checked exception of lookup APIs. |
| `NoClassDefFoundError` | Bytecode/runtime needs a class that cannot be defined/found, or a previous initialization attempt failed | Read the message and `Caused by`; do not equate every error with a missing class file. |
| `NoSuchFieldError` | Constant-pool `Fieldref` does not match the runtime field | Name **and descriptor**; field type changes; actual JAR version. |
| `NoSuchMethodError` | `Methodref`/`InterfaceMethodref` does not match the runtime API | Parameters, return descriptor, binary incompatibility; experiment B. |
| `IllegalAccessError` | Access to a type/member is denied at runtime | Package/nest/module permissions, build dependency differs from runtime; distinct from `IllegalAccessException` in some Reflection APIs. |
| `IncompatibleClassChangeError` | Incompatible static/instance usage or a class/interface change breaking the linkage contract | Caller opcode, modifiers, and runtime API version. |
| `AbstractMethodError` | Call to a contract method with no matching implementation at runtime | Interface, stale implementation, version mismatch; may relate to method selection/invocation. |
| `BootstrapMethodError` | Bootstrap for a dynamic constant/`invokedynamic` fails | `BootstrapMethods`, method handle, bootstrap arguments, root cause. |
| `VerifyError` | Invalid bytecode / fails verification | Class-file generation/modification tools, bytecode version, verification; distinct from lookup failures. |
| `ExceptionInInitializerError` | Static initialization execution fails | `<clinit>` code, static values, underlying exception cause; distinct from resolution. |

`NoSuchMethodError`, `NoSuchFieldError`, and several errors above belong to the **`LinkageError`** family (with many specific subclasses). They often appear after **compile-time and runtime dependencies diverge**, but you must not immediately deduce a single cause. Inspect the stack trace, where the error occurred, and the class loader instead of unsystematically trying to add JARs.

An error such as `NullPointerException` inside a method body is a **program execution error**, not proof that resolution failed. Conversely, seeing `NoSuchMethodError` before the target method's code runs makes sense: the JVM has not been able to resolve the target requested by the bytecode.

## 11. Workflow for Debugging Resolution in Real-World Applications

1. **Identify the failing call site.** Capture the first stack trace and the `Caused by` chain. Identify the bytecode of the caller class (do not look only at the latest source code).
2. **Read the requested descriptor.** Run `javap -classpath ... -v -c package.Caller`. Find the `Fieldref`, `Methodref`, or `InterfaceMethodref` associated with the opcode at the relevant location.
3. **Inspect the actual runtime class.** Use `javap -classpath ... -s package.Target` on the exact JAR or class directory the application is running with. Compare the descriptor, static/instance status, and access modifiers.
4. **Check versions and loading paths.** Verify classpath ordering, module path, fat JAR shading, plugin loaders, and package exports. With Gradle/Maven, view the runtime dependency tree; the compile tree does not guarantee matching runtime dependencies.
5. **Separate error categories.** `NoSuchMethodError` typically points to a binary mismatch; `IllegalAccessError` points to access; `LinkageError` with a loading-constraint violation points to loader type identity; `ExceptionInInitializerError` points to the static initializer.
6. **Reproduce in a controlled environment.** Create a clean build, specify the JDK, and use the same classpath/module path; add deliberate logging instead of guessing eager/lazy ordering.
7. **Fix at the source.** Align the binary API/dependency contract, adjust exports/access permissions or the plugin/shared-loader contract; re-verify with the same executable distribution used in production.

Useful tools in JDK 17+:

```sh
javap -classpath out -v -c demo.Main
javap -classpath out -s demo.Library
java -Xlog:class+load=info -cp out demo.Main
```

`-Xlog:class+load=info` is Unified Logging for HotSpot/JDK builds that support this flag; the log reports **loading events**, not a detailed list of every resolution. JVMs have different logging options depending on version/implementation; avoid claiming that a class-load line proves a field/method has been resolved. `javap` reads class files on disk and does not assert that the exact file was selected by the runtime class loader if the actual classpath differs.

To compare the caller and the runtime target in JARs:

```sh
javap -classpath app.jar -v -c com.example.app.Caller
javap -classpath dependency.jar -s com.example.lib.Target
```

These are **command templates**; `app.jar` and the class/package names must be replaced with actual artifacts, not treated as a standalone example with predetermined output.

## 12. Misconceptions to Avoid

- **"Once loading completes, all symbolic references are resolved."** False: other references may still remain unresolved.
- **"Resolution always runs after preparation and before all static initialization along a single straight line."** Inaccurate: the linking structure includes resolution, but eager/lazy strategies differ; the JVM may continue resolving after initialization.
- **"Resolving a method means selecting the object's specific method implementation."** False for virtual/interface invocation: method resolution must be separated from method selection.
- **"The class name is enough to find the right type."** False with multiple defining loaders; the name/loader pair is the runtime identity.
- **"Changing a method's return type does not affect callers if the name and parameters stay the same."** False for bytecode: the return type is in the JVM method descriptor.
- **"Seeing `Methodref` in `javap` means the method has been executed."** False: `javap` only shows metadata/static bytecode; resolution/execution are runtime events.
- **"Every `LinkageError` is caused by a missing JAR."** False: it can be due to method/field mismatches, access, loader constraints, class/interface mismatches, or bootstrap errors.
- **"Editing a JAR file in place is enough to make running classes relink automatically."** False under the normal model: defined classes and resolution results have caching/failure rules; you need to replace the runtime/deployment properly and typically restart or create a new loader under a valid architecture.

## 13. Self-Check Questions

**1. Why can the compiler generate `Methodref` instead of a method address?** Because the class file is an environment-independent format, while the runtime class/method and class loader are determined when the program runs.

**2. What steps does `getstatic` require?** Resolve the field reference and perform the appropriate linking checks; when needed, initialize the class/interface **declaring the field** before reading the value. Do not conflate the two mechanisms.

**3. When does `NoSuchMethodError` appear even though `javac` previously succeeded?** When the caller bytecode references a method descriptor no longer satisfied by the runtime class/interface; usually due to a binary-incompatible dependency.

**4. Are two `Class` objects with the same binary name necessarily equal?** No. If their defining loaders differ, they are two different runtime types.

**5. Will a reference that failed to resolve automatically be looked up again after copying in an additional JAR?** You cannot rely on that: the JVMS binds the result/failure of the previous resolution on that reference.

**6. Why do two calls to `Greeting.say()` produce two different outputs?** The same symbolic interface method may be resolved, but method selection chooses the implementation according to the runtime receiver.

**7. What is a notable difference between `CONSTANT_InvokeDynamic` and `Methodref`?** Resolution of a dynamic call site uses a bootstrap method and binds the result to the specific `invokedynamic` instruction.

**8. In debugging, why must you check the descriptor in addition to the method name?** Because the JVM requires an exact binary signature; the same method name with a different descriptor is a different reference.

## 14. Authoritative References for Verification

- [The Java Virtual Machine Specification, Java SE 17 — 4: Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): constant pool, `CONSTANT_*`, and field/method descriptors.
- [The Java Virtual Machine Specification, Java SE 17 — 5.4.3 Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3): timing of resolution, success/failure outcomes, and reference kinds.
- [The Java Virtual Machine Specification, Java SE 17 — 5.4.4 Access Control and 5.4.6 Method Selection](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): access checks and method selection.
- [The Java Virtual Machine Specification, Java SE 17 — 5.5 Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): distinguishing resolution from class initialization.

**Rule to remember:** resolution is the JVM **binding bytecode symbolic references to the right runtime entity, under the right class loader and check rules**. Loading creates the class; resolution identifies the target a reference asks for; initialization runs static logic when needed; selection/invocation decides and executes the appropriate method. Separating these four mechanisms is the foundation for understanding class linkage errors, dependency conflicts, and plugin isolation in Java.
