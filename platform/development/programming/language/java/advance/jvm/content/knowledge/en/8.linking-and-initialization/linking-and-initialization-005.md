# Resolution: turning symbolic references into runtime links

In the **Java Virtual Machine (JVM)**, bytecode in a `.class` file usually does not point directly to the memory address of a class, field, or method. Instead, the ClassFile has a **constant pool** containing **symbolic references**: class/interface names, member names, and **descriptors** describing JVM types or signatures. When it needs to use them, the JVM performs **resolution**: determining the runtime entity that the reference points to, while applying the rules for class identity, member lookup, access control, and compatibility.

Resolution is a part of **linking**, but it is not all of linking. It is also **not synonymous** with running the static initializer (`<clinit>`), not calling a method from Java source, and does not mean the JVM searches for the name from scratch every time an opcode runs.

Learning objectives:

1. Be able to read symbolic references from the constant pool using `javap -v`.
2. Understand what conditions allow a reference to become a valid runtime link.
3. Distinguish **loading**, **verification**, **preparation**, **resolution**, **initialization**, and **execution/dispatch**.
4. Explain errors such as `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, and `IncompatibleClassChangeError`.
5. Understand that resolution can happen eagerly or lazily, depending on the VM mechanism and reference kind; do not impose an artificial execution order on all JVMs.
6. Know the boundaries of resolution when encountering **`invokevirtual`**, **`invokeinterface`**, **`invokedynamic`**, and **constant dynamic**.

## 1. The constant pool contains “names to be interpreted”, not native addresses

A class compiled by `javac` can carry entries such as:

```text
CONSTANT_Class_info
CONSTANT_Fieldref_info
CONSTANT_Methodref_info
CONSTANT_InterfaceMethodref_info
CONSTANT_NameAndType_info
CONSTANT_Utf8_info
```

Reference entries **do not statically store the RAM address** where a field/method will reside on a specific JVM. They represent symbolic relationships, so that a class file can be carried to another JVM, another CPU architecture, and another class-loading environment while still using the same format.

Java example:

```java
class Account {
    int balance;

    int add(int amount) {
        balance += amount;
        return balance;
    }
}
```

This is an illustrative class that can be saved separately as `Account.java`. A method calling `Account.add(int)` can reference the method based on information of the form:

```text
Class:       Account
Method name: add
Descriptor:  (I)I
```

`(I)I` means the method takes one `int` and returns `int`. This triple is the **logical data of a symbolic method reference**, not a “function pointer” frozen into bytecode.

Conceptual diagram:

```text
Client's ClassFile
┌────────────────────────────────────────────────┐
│ constant_pool                                  │
│  #N  Methodref → Account.add:(I)I               │
└────────────────────────────────────────────────┘
                    │
                    │ resolution
                    ▼
    JVM finds the appropriate runtime class Account
    + finds the method with the required name/descriptor
    + checks access/compatibility rules
                    │
                    ▼
           a resolved reference
                    │
                    │ invocation, dispatch
                    ▼
       the appropriate method code is executed
```

This is an **explanatory model**, and does not require every JVM to store an address slot with the same structure. A JVM may use a runtime constant pool, caches, metadata pointers, inline caches, or other internal structures to implement linking.

## 2. ClassFile constant pool and runtime constant pool

According to the *Java Virtual Machine Specification* (JVMS), a ClassFile contains `constant_pool` — a binary structure storing symbolic references and constants. When the JVM creates a class/interface from a class file, it has a **runtime constant pool** corresponding to this information.

| Location | Role |
| --- | --- |
| `constant_pool` in `.class` | Serialized data in the file, using indices and `CONSTANT_*` tags |
| Runtime constant pool of a class/interface | Runtime structure that the JVM uses to work with constants and symbolic references |
| Resolution information | Internal result when the JVM has resolved a reference according to linking rules |
| Object/field/method at runtime | Runtime entity, with corresponding execution semantics; not a UTF-8 string in the file |

Example when viewing `javap -v`:

```text
#12 = Methodref          #18.#19  // Account.add:(I)I
#18 = Class              #20      // Account
#19 = NameAndType        #21:#22  // add:(I)I
#20 = Utf8                         Account
#21 = Utf8                         add
#22 = Utf8                         (I)I
```

This is an **illustrative excerpt**; indices `#12`, `#18`… are examples, not guaranteed output from a specific compilation. Actual output depends on `javac`'s constant pool ordering and the compiled code.

**NameAndType** combines **name** and **descriptor**. A class symbolic reference points to the appropriate class/interface name; Fieldref/Methodref/InterfaceMethodref links to a class/interface and a NameAndType. `Utf8` entries store formatted strings that the JVM uses to identify names, signatures, or metadata.

### 2.1. The descriptor is as important as the name

```text
foo:()I                 → no parameters, returns int
foo:(I)I                → one int, returns int
foo:(Ljava/lang/String;)V → one String, returns void
```

If a new class still has a method named `foo` but changes its descriptor, a binary client compiled against the old descriptor may **fail to resolve**. Therefore, one cannot simply find “a method with the same name” and consider it compatible.

For fields, the descriptor also identifies the field type, for example `I` for `int`, `Ljava/lang/String;` for `String`. Generic `List<String>` and `List<Integer>` typically have the descriptor `Ljava/util/List;` after **type erasure**; generic type information may reside in the `Signature` attribute but does not replace the JVM field descriptor.

## 3. Distinguishing loading, linking, and initialization

The lifecycle should be read in the right conceptual order:

```text
              Loading
                │
                ▼
              Linking
          ┌─────┼───────┐
          │     │       │
       Verify  Prepare  Resolve
                │       │
                │       └── can be performed on demand
                ▼
           Initialization
       (<clinit> if present, on
       active use conditions)
                │
                ▼
             Execution
```

The diagram groups the phases into one picture for comparison; **it does not assert that resolution must be completed entirely before initialization or that all symbols are resolved at the same time**.

- **Loading:** The JVM uses the appropriate class loader to find/obtain the class/interface definition and create its runtime representation. Finding a class does not guarantee the class is initialized.
- **Verification:** checks the structure and validity conditions of the class file/bytecode according to JVM rules.
- **Preparation:** creates/prepares static fields and assigns default values or constant values according to the specification rules, **not running the entire Java static initializer**.
- **Resolution:** turns symbolic references into concrete runtime entities according to JVMS rules.
- **Initialization:** executes the class/interface initialization procedure, including `<clinit>` if present and the related requirements for superclasses/superinterfaces.
- **Execution/dispatch:** executes bytecode and selects the appropriate invocation implementation at call time.

**Key difference:** resolving a reference to a class **does not automatically invoke `<clinit>`** of that class. A class may already be loaded/used to resolve a reference without having run its static initializer. Conversely, an active use may require initialization, and the JVM will ensure the linking preconditions needed for that operation.

## 4. When does resolution happen? Eager and lazy resolution

The JVM Specification allows flexibility in the strategy for **when** symbolic references are resolved. A JVM may choose to eagerly resolve some references after a class is loaded, or **lazily resolve them when an instruction needs them**, provided it obeys observable behavior and the error-reporting constraints of the specification.

### 4.1. Not the entire constant pool is resolved immediately at load time

Suppose a class has a method `unused()` that references a dependency not present on the runtime classpath, but the current execution path does not use that method. In some situations and JVMs, the class may load or start running without needing resolution of the symbol in the unused method. **Do not turn that observation into a guarantee for all JVMs**, because a VM may perform additional linking/checking operations when appropriate.

Whether resolution happens eagerly or lazily, it must still comply with the requirement to **report linking errors at a point where program usage could trigger an error under JVMS rules**, rather than arbitrarily changing program semantics.

### 4.2. Does a resolved symbolic reference need to be looked up from scratch on every use?

Semantically, the JVM performs resolution of a symbolic reference to a specific runtime definition and records the success or error outcome according to the corresponding rules; **there is no requirement to re-run the name-lookup algorithm on every bytecode execution**. The specific caching mechanism is up to the implementation.

**Do not confuse resolution caching with caching the result of a method call:** a reference `Animal.speak:()V` may be resolved to an appropriate representative method, but `invokevirtual` at different call sites/invocations still needs to find/select the implementation based on the **runtime class of the receiver**.

## 5. Resolution of class and interface symbolic references

A `CONSTANT_Class` contains a symbolic name denoting a class/interface or array class. When resolution needs to determine the runtime type, the JVM uses the appropriate **class loader** and enforces the related constraints.

### 5.1. Class identity is not just a name

For an ordinary class/interface, **runtime identity** is tied to the pair **(binary name, defining class loader)**. Two classes with the same name defined by **two different defining loaders** are not automatically the same runtime type.

```text
"org.example.Plugin" + Loader-A  → Runtime type A
"org.example.Plugin" + Loader-B  → Runtime type B

A.getName().equals(B.getName())    → true
A == B                             → false
```

The diagram assumes loaders A and B actually define the same name themselves. If loader B merely *delegates* and obtains loader A's exact type, then they are not two independent runtime definitions.

The **initiating loader** (the loader initiating the load) and the **defining loader** (the loader actually defining the class) can differ. During resolution, the JVM also has **loader constraints** to ensure that types appearing in descriptors are compatible across loader boundaries when type safety must be preserved.

### 5.2. Class accessibility checks

A type that is found is not necessarily **accessible** from the class carrying the symbolic reference. The JVM must respect accessibility rules, module access, and the appropriate runtime package relationship. In the JVM, a runtime package is not determined solely by package name, but also depends on the defining loader according to JVMS rules.

Therefore, resolution can detect issues such as:

- The class exists but is not accessible to the referencing party.
- The class is defined in a different loader than expected by the dependency, breaking identity or a loader constraint.
- A class/interface is needed but cannot be found or defined under the current loader mechanism.

**Do not call all of the above `ClassNotFoundException`**: this is a common checked exception of APIs like `Class.forName` and `ClassLoader.loadClass`, whereas bytecode operations linked by the JVM typically report `LinkageError` or corresponding errors.

## 6. Resolution of field symbolic references

A reference to a field is typically based on:

```text
CONSTANT_Fieldref
  ├── class/interface containing the symbolic owner
  └── NameAndType:
         fieldName
         fieldDescriptor
```

When resolving a Fieldref, the JVM must find the matching field via the **field lookup** algorithm according to class/interface rules and check accessibility. Finding a field is not simply taking a public field on the exact class named in source; **a field can be found through the hierarchy** according to JVM rules.

### 6.1. Example

```java
class Config {
    static int port = 8080;
}

class Reader {
    static int read() {
        return Config.port;
    }
}
```

These are two illustrative classes; they need to be placed in appropriate files or a valid compilation unit to run. The bytecode of `Reader.read()` may contain:

```text
getstatic Config.port:I
ireturn
```

Resolution of `Config.port:I` pertains to a **specific field**. However, `getstatic` also requires the field to actually be **static**, and accessing a static field can trigger **initialization of the class/interface declaring the field** according to the appropriate rules. These are checks/behaviors **distinct** from finding the field by name/descriptor.

### 6.2. Field resolution differs from method resolution

- Field lookup is based on name, descriptor, and field hierarchy rules.
- Method resolution has different algorithms depending on Methodref, InterfaceMethodref, and override/default method relationships.
- Instance fields use `getfield`/`putfield`, static fields use `getstatic`/`putstatic`. If a binary client expects a static field but the runtime class version changed it to an instance field, **`IncompatibleClassChangeError`** can occur.
- If the field was renamed, deleted, or had its descriptor changed, **`NoSuchFieldError`** can occur.

These errors usually result from **broken binary compatibility** when deploying a library different from the version used at compile time, which cannot always be detected when compiling only the client module.

### 6.3. Compile-time constants and inlining

```java
class Flags {
    static final int LIMIT = 100;
    static int dynamic = compute();

    static int compute() {
        return 25;
    }
}
```

When `Flags.LIMIT` is a constant variable inlined by the compiler into the client, the client's bytecode may **contain no Fieldref** to `LIMIT` at the usage site: it only contains the literal 100. Therefore, changing the value of `LIMIT` in the library without recompiling the client can cause the client to continue seeing the **old inlined value**, which is not an issue of “JVM resolution still caching the old Fieldref”.

By contrast, `Flags.dynamic` requires reading the static value at runtime and typically has `getstatic`. When diagnosing, use **`javap -c -v` on the client binary** to see whether a symbolic reference to the field actually exists.

## 7. Method resolution: resolving a symbol is not yet choosing the final implementation

A symbolic method reference contains **the owner class/interface name**, **method name**, and **method descriptor**.

| Constant-pool entry | Typical situation |
| --- | --- |
| `CONSTANT_Methodref` | Class method, used with `invokevirtual`, `invokespecial`, `invokestatic` depending on kind |
| `CONSTANT_InterfaceMethodref` | Interface method, used with `invokeinterface` and certain other valid invocation situations |
| `CONSTANT_NameAndType` | Holds name and descriptor serving both method and field references |

Example:

```java
interface Printer {
    String print();
}

class ConsolePrinter implements Printer {
    public String print() {
        return "console";
    }
}
```

Inside a method:

```java
Printer printer = new ConsolePrinter();
System.out.println(printer.print());
```

Bytecode typically contains:

```text
invokeinterface Printer.print:()Ljava/lang/String;
```

**Resolution** resolves the symbolic reference to the interface method according to the JVMS algorithm. But **at call time**, `invokeinterface` must also select the implementation method matching the **runtime class of the receiver object**, which here is `ConsolePrinter`.

### 7.1. Resolution and dynamic dispatch are two logical steps

```text
Constant pool:
  InterfaceMethodref Printer.print:()Ljava/lang/String;
                   │
                   ▼
      Resolution (interface method reference)
                   │
                   ▼
         invokeinterface executes
                   │
              receiver?
                   │
              ConsolePrinter
                   │
                   ▼
      ConsolePrinter.print() → "console"
```

A resolved method reference **does not force every subsequent virtual/interface call to point to a single implementation**. If the receiver belongs to another subtype that overrides the method, dispatch can select a different implementation.

### 7.2. Invocation opcodes

| Instruction | Common usage mechanism | Relationship to resolution |
| --- | --- | --- |
| `invokestatic` | Calls a static method of a class/interface | Requires appropriate method reference, staticness check, and initialization of the declaring type when applicable |
| `invokespecial` | Constructor `<init>`, private method, superclass/interface call with special semantics | Has special lookup/selection rules, not normal virtual dispatch |
| `invokevirtual` | Calls a class instance method capable of being overridden | Resolves symbolic method, then selects implementation based on receiver's runtime class |
| `invokeinterface` | Calls a method through an interface | Resolves interface method, then selects appropriate implementation at runtime |
| `invokedynamic` | Links a call site via a bootstrap method | Has its own resolution/linkage mechanism; see section 12 |

If source code writes `Child c = new Child(); c.run();`, you cannot guess the opcode just by looking at `run`. The compiler considers declared type, static/private/super, interface, overloading, and language rules; the actual result should be verified with `javap`.

### 7.3. Return type is also part of the JVM method descriptor

```text
method():Ljava/lang/Object;
method():Ljava/lang/String;
```

At the **ClassFile level**, these two descriptors are different, even though Java source does not allow overloading solely by return type. **Bridge methods** generated by the compiler to preserve overriding/dispatch when generics are erased or when covariant returns need support can share the same name and parameters, but have a **different return descriptor**. Do not equate “method with the same name” with “method reference guaranteed to resolve”.

## 8. Resolution is tied to access control and binary compatibility

Suppose client `C` is compiled when library `L` has a public method `run()`. Later, the runtime loads a modified version of the library:

- Method `run()` is removed or its descriptor changed → the old symbolic method reference may encounter **`NoSuchMethodError`**.
- Method becomes inaccessible from the client → may encounter **`IllegalAccessError`**.
- Static/instance member kind no longer matches the instruction in the client → may encounter **`IncompatibleClassChangeError`**.
- Library changes hierarchy, turns a class into an interface, or has other incompatible structural constraints → may encounter the appropriate linkage error.
- During virtual invocation execution, if no suitable concrete implementation can be found, **`AbstractMethodError`** may occur at the invocation stage even though the earlier resolution steps succeeded.

**Important:** errors in **resolution**, **invocation**, **loading**, and **initialization** can appear close together in a stack trace, but they are not identical. A program printing `NoSuchMethodError` does not automatically mean “the JVM picked the wrong overload in Java source”; usually the running binary does not match the ABI/signature that the client was compiled against.

## 9. Runnable Java 17+ example: symbols, dispatch, and initialization

Create file **`ResolutionDemo.java`**:

```java
public class ResolutionDemo {
    interface Greeter {
        String greet();
    }

    static class Human implements Greeter {
        static {
            System.out.println("Human initialized");
        }

        @Override
        public String greet() {
            return "hello";
        }
    }

    static class Machine implements Greeter {
        @Override
        public String greet() {
            return "beep";
        }
    }

    static class Service {
        static {
            System.out.println("Service initialized");
        }

        static int count = 5;

        static String message() {
            return "ready";
        }
    }

    static String use(Greeter greeter) {
        return greeter.greet();
    }

    public static void main(String[] args) {
        System.out.println("start");
        System.out.println("class literal: "
                + Service.class.getSimpleName());

        Greeter first = new Human();
        System.out.println("first: " + use(first));

        Greeter second = new Machine();
        System.out.println("second: " + use(second));

        System.out.println("static field: " + Service.count);
        System.out.println("static method: " + Service.message());
        System.out.println("static method again: " + Service.message());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 ResolutionDemo.java
java ResolutionDemo
```

**Exact standard output:**

```text
start
class literal: Service
Human initialized
first: hello
second: beep
Service initialized
static field: 5
static method: ready
static method again: ready
```

### Detailed explanation

1. `Service.class.getSimpleName()` uses the Class mirror but **does not require class initialization**, so it does not print `Service initialized` before `class literal: Service`.
2. `new Human()` creates an instance and requires `Human` to be initialized; Human's static initializer prints exactly once.
3. The calls `use(first)` and `use(second)` both go through the symbolic interface method `Greeter.greet:()Ljava/lang/String;` in `use`'s bytecode. However, the **receiver runtime classes** differ, so dispatch goes to `Human.greet()` and `Machine.greet()` respectively.
4. Reading `Service.count` is an appropriate active use and triggers **class initialization** of Service, printing `Service initialized` before reading the value 5.
5. Subsequent calls to `Service.message()` do not re-run `<clinit>`; resolution or the JVM caching the link does not mean the class must be initialized again.
6. The output does not depend on wall-clock time, thread scheduling, or JVM-specific error messages.

**Key takeaway:** this example uses readable source to show the consequences of the **resolution / initialization / dispatch** boundaries. You cannot rely solely on stdout order to know exactly when the VM resolved each constant pool entry; use `javap` to see the symbols and JVMS rules to reason about them.

### 9.1. Reading the constant pool and bytecode

```bash
javap -c -p ResolutionDemo
javap -c -p 'ResolutionDemo$Human'
javap -c -p 'ResolutionDemo$Service'
javap -v -p ResolutionDemo
```

If using Bash or PowerShell, single quotes protect the `$` character in nested class names; on Windows `cmd.exe`, use double quotes.

Look in `javap -c -p ResolutionDemo` for typical patterns:

```text
// In use(Greeter), abbreviated description:
aload_0
invokeinterface ResolutionDemo$Greeter.greet:()Ljava/lang/String;
areturn

// In main, abbreviated description:
ldc           ... ResolutionDemo$Service
invokevirtual ... Class.getSimpleName:()Ljava/lang/String;
...
getstatic     ... ResolutionDemo$Service.count:I
...
invokestatic  ... ResolutionDemo$Service.message:()Ljava/lang/String;
```

This is an **illustration**, not a listing with exact offsets/constant pool indices. `javap -v` lets you observe entries such as `Class`, `Fieldref`, `Methodref`, `InterfaceMethodref`, and `NameAndType` from these code paths.

You can answer for yourself:

- Does `Service.class` have a class literal, and did it cause `Service` to be initialized?
- What are the symbolic owner and method descriptor of `invokeinterface`?
- Does every call to `use` necessarily select the same implementation?
- What active use behavior does reading `Service.count` with `getstatic` have?
- Does `Service.message()` need resolution, and why does `<clinit>` not run again?

## 10. Binary incompatibility example: same client source, swapped runtime library

Resolution has major practical value when **compiling against one version and deploying another version**. The following example uses **two independent versions** of a class `Api`, to show that the compiled client still holds a symbolic reference to the old descriptor.

**Use a Bash terminal** (Linux, macOS, or Git Bash); on native Windows, replace `:` in the classpath with `;`.

Create the directory structure:

```text
resolution-lab/
  api-v1/Api.java
  api-v2/Api.java
  client/Client.java
```

File **`api-v1/Api.java`**:

```java
public class Api {
    public static String message() {
        return "v1";
    }
}
```

File **`api-v2/Api.java`**:

```java
public class Api {
    public static String renamed() {
        return "v2";
    }
}
```

File **`client/Client.java`**:

```java
public class Client {
    public static void main(String[] args) {
        System.out.println(Api.message());
    }
}
```

In the `resolution-lab/` directory:

```bash
mkdir -p out-api1 out-api2 out-client
javac --release 17 -d out-api1 api-v1/Api.java
javac --release 17 -cp out-api1 -d out-client client/Client.java
javac --release 17 -d out-api2 api-v2/Api.java
```

**Run with the library version the client was compiled against:**

```bash
java -cp out-client:out-api1 Client
```

**Standard output:**

```text
v1
```

Now keep **`Client.class`** unchanged but change the runtime classpath to load only Api v2:

```bash
java -cp out-client:out-api2 Client
```

At runtime, the call to `Api.message:()Ljava/lang/String;` no longer has a matching method in the loaded `Api` class. As a result, the program **fails with `java.lang.NoSuchMethodError`**. The full stack trace is not copied here because the message wording, trace lines, and runtime details vary by JDK.

### 10.1. Why did it still compile?

`Client.java` was compiled **when** `Api.message()` still existed in `out-api1`. `Client.class` contains a symbolic reference like:

```text
Methodref Api.message:()Ljava/lang/String;
```

Replacing the runtime library with an `Api.class` missing this method does not rewrite the client's bytecode. When the JVM needs to link the call, it searches for the method by **name and descriptor** in the present Api version and fails.

Observe:

```bash
javap -v -p -classpath out-client Client
```

Look for `Methodref` or the `invokestatic Api.message:()Ljava/lang/String;` call. Even though library v2 only has `renamed()`, **the symbolic reference inside the client does not automatically turn into `renamed()`**.

### 10.2. What if the client is recompiled?

Keeping the old `Client.java` and compiling with `-cp out-api2`, `javac` will report an error that it **cannot find symbol `Api.message()`** at compile time. This is a source-API compile-time error, distinct from **`NoSuchMethodError`** at runtime for the old client binary.

You do not need to delete the entire application to diagnose this: check the **client's bytecode**, **the actual JAR/class files on the runtime classpath**, **binary name**, **loader**, and **descriptor**.

### 10.3. Variant: changing a field

If library v1 has `public static int count;` and library v2 deletes or changes the field, an old client with `getstatic Api.count:I` may encounter `NoSuchFieldError`. If the name/descriptor is kept but `static` is changed to an instance field, the error type to consider is **`IncompatibleClassChangeError`**. These are different situations; do not lump them into `NoSuchMethodError`.

## 11. Error taxonomy: at which step does an error occur?

| Symptom/error | What to check? | Issue category |
| --- | --- | --- |
| `ClassNotFoundException` when calling `Class.forName` | Loader/API cannot find class by name/load path | Explicit reflective loading/lookup API |
| `NoClassDefFoundError` | Class is needed by the JVM but cannot be obtained/initialized in the current state | Loading/linking/initialization; check cause |
| `NoSuchFieldError` | Field name/descriptor in client binary does not match runtime library | Field resolution |
| `NoSuchMethodError` | Method name/descriptor of symbolic reference has no matching target | Method resolution/binary compatibility |
| `IllegalAccessError` | Runtime access permissions do not match the existing reference | Access check during linking |
| `IncompatibleClassChangeError` | Class/interface kind change, static/instance change, or other binary incompatibility | Linking/invocation |
| `AbstractMethodError` | Cannot find a suitable concrete implementation for the call | Invocation/dispatch |
| `ExceptionInInitializerError` | Static initializer failed in a case where the JVM wraps the exception | Class initialization, **not resolution** |
| `BootstrapMethodError` | Bootstrap method for dynamic linkage/constant failed in the corresponding case | Dynamic linkage / bootstrap |

A `NoClassDefFoundError` **does not necessarily** mean the file was not found; the class may have failed initialization earlier. Read the **cause chain, class name, loader, load path, and stack trace**.

**`LinkageError`** is a broad error family; the subtypes listed above have different semantic positions. `ClassNotFoundException` is a checked exception, not a subtype of `LinkageError`. Keep this distinction when writing catch clauses or reading logs.

## 12. `invokedynamic`, method handles, and dynamic constants: advanced resolution

Since Java 7, the ClassFile format and JVM have added dynamic linkage mechanisms. You should not assume every constant pool entry is a traditional `Fieldref`/`Methodref`.

### 12.1. `invokedynamic` and bootstrap methods

The **`invokedynamic`** instruction involves `CONSTANT_InvokeDynamic` and a **bootstrap method**. When a call site needs linking, the JVM uses the bootstrap information, method types/handles, and appropriate static arguments to create a **call site linkage** according to the JVMS.

```text
invokedynamic instruction
    │
    ├── name + method type
    ├── bootstrap method reference
    └── static bootstrap arguments
                │
                ▼
         Bootstrap invocation
                │
                ▼
             CallSite
                │
                ▼
        Invocation target handle
```

The diagram is a logical model and does not require a JVM implementation to execute the exact number of physical steps shown. `CallSite` and `MethodHandle` belong to the `java.lang.invoke` API; they are not simply `java.lang.reflect.Method`.

Modern compilers may use `invokedynamic` for **lambda expressions** and **string concatenation**, depending on the compiler version/strategy. For example:

```java
Runnable action = () -> System.out.println("run");
action.run();
```

This is an **illustrative snippet inside a method**, which may correspond to `invokedynamic` using a lambda metafactory, rather than the JVM having a special instruction named `lambda`.

### 12.2. `CONSTANT_MethodHandle` and `CONSTANT_MethodType`

- **`CONSTANT_MethodHandle`** describes a symbolic reference to a field/method/appropriate invocation mechanism; resolution has its own rules, including reference kind and access checks.
- **`CONSTANT_MethodType`** describes the type of a method at the parameter and return level; when resolved successfully, the JVM obtains the corresponding method type object.
- When resolution or bootstrapping involves a wrong loader/access, the error will depend on the symbolic reference kind and the actual step. Do not lump everything into `NoSuchMethodError`.

### 12.3. `CONSTANT_Dynamic` (condy)

**Constant dynamic** allows a constant in the constant pool to be computed via a bootstrap mechanism when linking the value. It differs from a simple inlined static final constant variable and differs from calling a Java method every time a constant is read.

`ConstantDynamic` is not necessarily present in ordinary class files: it depends on the JDK/compiler/library generating the bytecode. `javap -v` can display constant pool entries and `BootstrapMethods` when a class file actually contains that mechanism.

**Scope limit in this article:** the resolution rules for `CONSTANT_Dynamic`, `CONSTANT_InvokeDynamic`, and method handles have special rules regarding bootstrap, accessibility, type consistency, resolution cycles, and errors. To analyze a case accurately, read the corresponding sections of JVMS §5.4.3 and §6.5 rather than mechanically applying the ordinary Fieldref/Methodref algorithm.

## 13. Resolution, method selection, and JIT optimization: avoiding layer confusion

Three conceptual steps can occur around a call:

```text
Java Source            JVM semantics                  Implementation
-----------            -------------                  --------------
a.run()                symbolic method resolution     runtime pool/cache
                       + method selection             dispatch/vtable...
                       + invocation                   interpreter/JIT code
```

- **Resolution** determines the entity denoted by a symbolic reference according to JVM rules.
- **Selection/dispatch** determines the specific method implementation in a polymorphic call. The same resolved symbolic reference can lead to different implementations for different receivers.
- **JIT** may inline, devirtualize, or use inline caches, but only while preserving Java/JVM semantics; an optimization cannot turn an invalid symbolic reference into a valid one or be allowed to skip required linking errors.

Actual machine addresses and internal metadata structures **are not part of the standard format of `CONSTANT_Methodref`**. A class file moved to another CPU still contains the compiled symbolic reference, and the target JVM is responsible for loading and linking it according to its own runtime.

### 13.1. Resolution is not object construction

Resolving `CONSTANT_Class` to a runtime class does not create an instance of that class. `new SomeClass()` can cause the JVM to load/link/initialize the appropriate class, and only then allocate the object and run the `<init>` constructor in the proper sequence. Do not say “resolution calls `new`” or “resolution runs the constructor by itself”.

### 13.2. Resolution is not reflection

`Class.forName`, `Method.invoke`, and `getDeclaredMethod` are **Java APIs** for runtime type lookup and reflective access. They can lead to loading/linking/initialization/invocation underneath, but they are **not identical** to instruction-level resolution of a constant pool symbolic reference. For example, `ClassNotFoundException` from `Class.forName` differs from `NoSuchMethodError` of a binary Methodref.

### 13.3. Resolution does not depend solely on the classpath

The classpath/module path affects which classes are found/defined, but **class loader hierarchy, module boundaries, package access, descriptors, and runtime class identity** are also crucial. Two applications with the same `.class` files on disk can behave differently when their loader/module arrangements differ.

## 14. Step-by-step diagnostic guide when suspecting a resolution error

1. **Record the full error:** `Error`/exception type, class name, method/field, descriptor if printed, cause chain, and when it occurs.
2. **Verify the runtime:** `java --version`, classpath/module path, actual JARs, dependency versions. Do not look only at IDE configuration or build files.
3. **Inspect the client ClassFile:** `javap -v -p -classpath <client-path> Client`; find the relevant `Methodref`, `InterfaceMethodref`, `Fieldref`, `Class`.
4. **Inspect the dependency ClassFile:** `javap -p -s -classpath <runtime-lib-path> Api`; compare name, descriptor, and static/instance status against client expectations.
5. **Verify the class loader when needed:** log `SomeType.class.getClassLoader()` and `getProtectionDomain().getCodeSource()` when APIs/permissions permit; check delegation relationships and modules.
6. **Separate resolution from initialization:** an error caused by `<clinit>` is not “fixed” by changing descriptors, and a `NoSuchMethodError` does not go away by triggering a static initializer.
7. **Restore binary compatibility:** use a compatible library version or recompile/redeploy all sides consistently after changing a public API/ABI.

The placeholders `<client-path>` and `<runtime-lib-path>` in this section are **path placeholder markers**, not literal filenames to copy verbatim. For the complete example in section 10, replace them with `out-client` and `out-api1` or `out-api2`.

### Common pitfalls leading to wrong conclusions

| Hasty conclusion | Fact to verify |
| --- | --- |
| “`NoSuchMethodError` means the client source does not compile.” | The client may have compiled against an old API; the error occurs when **the binary is linked against a different runtime API** |
| “Every method call must re-search the full name from disk.” | The JVM can retain resolution results; polymorphic calls still have separate method selection |
| “Once resolution finishes, `<clinit>` has definitely run.” | Resolution does not automatically trigger class initialization |
| “`Class.forName` and `CONSTANT_Class` resolution are the same API function.” | Reflection and JVM symbolic resolution are two different layers |
| “Same class name means same runtime type.” | **Defining loader** is part of class/interface identity |
| “`Methodref` only needs a name, not a descriptor.” | The descriptor includes the parameters **and return type** of the method |
| “The JVM must resolve the entire constant pool right before `main`.” | The VM is allowed to use eager/lazy strategies under JVMS rules |
| “If JIT inlines a call, binary compatibility errors disappear.” | Optimizations must preserve semantic effects and errors |
| “Changing a static field to an instance field does not affect binary clients.” | A client with a `getstatic` opcode will be incompatible with an instance field |
| “`invokedynamic` is a normal class Methodref call.” | It has its own **bootstrap/call-site linkage** |

## 15. Self-check exercises

### Exercise 1 — Reading a symbolic method reference

An equivalent constant pool entry:

```text
Methodref: pkg/MathUtil.calc:(II)I
```

**Question:** What components does the JVM need for resolution?  
**Answer:** The appropriate runtime class `pkg.MathUtil`, method name `calc`, descriptor taking **two `int`s** and returning **`int`**, along with applicable loader, lookup, accessibility, and compatibility requirements. It cannot simply find any method named `calc`.

### Exercise 2 — Why don't overloads cause confusion?

A class has:

```java
static int parse(String text) { return 1; }
static int parse(int number)  { return 2; }
```

These are **two illustrative methods** in the same class. The pair of descriptors is different: `(Ljava/lang/String;)I` and `(I)I`; JVM method references can distinguish them. Overload selection happens at **Java source compile time**, while resolution resolves the symbol carrying the descriptor already recorded in the binary.

### Exercise 3 — Resolution or initialization?

Java source reads:

```java
int x = Settings.value;
```

where `Settings.value` is a static field that is **not a compile-time constant variable**.  
**Answer:** The JVM needs to link Fieldref `Settings.value` according to the rules, and `getstatic` may require **class initialization** before reading. These are two different responsibilities.

### Exercise 4 — One method symbol, two receivers

```java
Printer a = new ConsolePrinter();
Printer b = new NetworkPrinter();
a.print();
b.print();
```

Assume both classes implement `Printer`.  
**Question:** Does `invokeinterface` necessarily call the same implementation?  
**Answer:** No. The same symbolic interface method can dispatch differently based on the runtime class of `a` and `b`.

### Exercise 5 — Wrong library version

Client compiled with `Api.message:()Ljava/lang/String;`, but runtime `Api` only has `Api.renamed:()Ljava/lang/String;`.  
**Answer:** When the JVM needs to link the call, **`NoSuchMethodError`** may occur. Change the classpath to use a compatible binary or recompile the client after updating the source.

### Exercise 6 — Two loaders

Loader A and Loader B independently define the same binary name `example.Model`.  
**Question:** Does the JVM treat the two runtime classes as one just because their names are the same?  
**Answer:** No. The runtime identity of a class/interface depends on **binary name + defining class loader**.

### Exercise 7 — Compile-time constant

`static final int LIMIT = 9;` is a compile-time constant variable. Client source prints `Config.LIMIT`.  
**Question:** Does the client bytecode always contain `getstatic Config.LIMIT:I`?  
**Answer:** No. The compiler can **inline the number 9**; you must use `javap` to know what instruction the binary actually contains.

### Exercise 8 — Dynamic call sites

**Question:** Does `invokedynamic` require an ordinary symbolic class method reference carrying the final method implementation?  
**Answer:** Not under that model. It uses **bootstrap method linkage** to link a call site and method type; the mechanism differs from resolving a `Methodref` and calling a static method.

## 16. Summary and reference documentation

- **Symbolic reference** identifies a class, field, method, or dynamic kind by **name, descriptor, and constant-pool structures**.
- **Resolution** determines the runtime target according to JVM rules, including loading when needed, lookup, access/loader constraints, and appropriate error reporting.
- **Timing** can be eager or lazy; do not rely on a single resolution order for all JVMs.
- **Method resolution ≠ dynamic dispatch**; virtual/interface invocation also selects the implementation based on the receiver.
- **Resolution ≠ initialization**; `<clinit>` and active use are a separate JVM responsibility.
- **Binary compatibility** depends on matching name, descriptor, staticness, accessibility, and runtime constraints; changing a library without updating the client can cause `LinkageError`.
- **`invokedynamic`/`CONSTANT_Dynamic`** have specialized bootstrap linkage and cannot all be reduced to classic Fieldref/Methodref.

Standard references:

- *The Java Virtual Machine Specification*, **§5.3 Loading, §5.4 Linking, §5.4.3 Resolution, §5.5 Initialization**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- *JVMS* **§4.4 Constant Pool** and `CONSTANT_*` kinds: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- *JVMS* **§6.5 Instructions** — `getstatic`, `getfield`, `invokevirtual`, `invokeinterface`, `invokestatic`, `invokespecial`, `invokedynamic`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html

**Conclusion:** When a class's bytecode says “call `Api.message:()Ljava/lang/String;`”, it carries **a symbolic contract**, not a method address baked into the class file. **Resolution** is the bridge from that contract to the runtime world with concrete class names, defining loaders, access permissions, and descriptors. Once resolution is separated from initialization and dispatch, reading `javap` and handling binary compatibility errors becomes clear and verifiable.
