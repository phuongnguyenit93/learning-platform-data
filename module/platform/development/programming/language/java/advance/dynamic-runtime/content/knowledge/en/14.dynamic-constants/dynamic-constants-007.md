# 14.7 Distinguishing nominal descriptors from existing `Class` objects or handles

In the dynamic constant (**condy**) system and Java 17's `java.lang.constant` APIs, a **nominal descriptor** is a **description by name, type, and structure** that can be stored/exchanged to be resolved later into an actual value. It is **not** the runtime object itself that the JVM is using.

Intuitive examples:

- `ClassDesc.of("java.lang.String")` **describes** the class constant `String.class`; it is **not** `String.class`.
- `MethodTypeDesc` describes a method signature using `ClassDesc` instances; it is **not** a `MethodType` that already holds runtime `Class<?>` objects.
- `MethodHandleDesc` describes how to look up a method/field/constructor; it is **not** a `MethodHandle` that can be invoked with `invokeExact`.
- `DynamicConstantDesc` describes **how to compute a dynamic constant** using a bootstrap method, name, type, and bootstrap arguments; this descriptor is **not** the computed result of the bootstrap.

The most important difference: **a descriptor does not carry a class loader, actual access permissions, or an already-computed bootstrap result on its own**. To turn a description into an existing object, a resolution context is required, typically `MethodHandles.Lookup`; resolution can fail or produce different results depending on the environment.

This article uses **Java SE 17+** and places the topic in the context of dynamic constants, not stopping at ordinary reflection.

## 1. From constants in a class file to nominal descriptors

A JVM class file contains a *constant pool* with entries that can represent class types, method types, method handles, strings, numbers, and dynamic constants. Some entries store **symbolic references** rather than pointers to already-loaded objects.

In Java 12+, the `java.lang.constant` package introduces Java objects that model how those constant-pool entries are described. The purpose is to let bytecode analysis/generation code, runtime tools, or libraries exchange a **nominal recipe** without forcing immediate resolution of the underlying class/method.

Two layers to separate:

~~~text
DESCRIPTION LAYER (NOMINAL)
  ClassDesc / MethodTypeDesc / MethodHandleDesc / DynamicConstantDesc
                │
                │ resolveConstantDesc(Lookup)
                │ check class loader + access permissions + type
                ▼
RUNTIME LAYER (LIVE)
  Class<?> / MethodType / MethodHandle / dynamic constant value
                │
                ▼
    compare identity, invoke handle, use value
~~~

The path from top to bottom is **conditional**, with no guarantee that it will always succeed. A valid `ClassDesc` may describe a class that **does not exist yet** or is inaccessible in the current context. Similarly, a `MethodHandleDesc` may describe a method not present in the loaded class.

### 1.1. Mapping table of key types

| Nominal description | Corresponding object/value upon resolution | What information does it contain? |
| --- | --- | --- |
| `ClassDesc` | `Class<?>` | Type name or field descriptor, for example `Ljava/lang/String;` |
| `MethodTypeDesc` | `MethodType` | Parameter types and return type as `ClassDesc` |
| `MethodHandleDesc` / `DirectMethodHandleDesc` | `MethodHandle` | Kind (static/virtual/constructor/field...), owner, name, lookup type, or adapter |
| `DynamicConstantDesc<T>` | Corresponding value of type `T` | Bootstrap method descriptor, constant name, `ClassDesc` of the constant type, and static bootstrap arguments |
| `String`, `Integer`, `Long`, `Float`, `Double` | The corresponding values themselves | Constants that have a direct representation in the constant pool can themselves be `ConstantDesc` |

**Intentional exception:** not **every** `ConstantDesc` is an object "different" from its value. For example, `String` is a `ConstantDesc` for itself. The "descriptor ≠ live object" rule is especially important for `ClassDesc`, `MethodTypeDesc`, `MethodHandleDesc`, and `DynamicConstantDesc`.

## 2. `ClassDesc` is not `Class<?>`

A name like `java.lang.String` is a **nominal name**. The JVM can only answer which `Class<?>` corresponds to it once the **class-loading context** and access permissions are known.

~~~java
ClassDesc nominal = ClassDesc.of("java.lang.String");
System.out.println(nominal.descriptorString());
// Ljava/lang/String;

Class<?> live = (Class<?>) nominal.resolveConstantDesc(
        MethodHandles.lookup());
System.out.println(live == String.class); // true
~~~

This snippet illustrates the idea inside a method with appropriate imports; the complete program is in section 7.

- `ClassDesc.of("java.lang.String")` **creates a description** from a binary name, without looking up the real `Class` yet.
- `ClassDesc.ofDescriptor("Ljava/lang/String;")` creates an equivalent description from a **JVM field descriptor string**.
- `resolveConstantDesc(lookup)` **resolves** according to the class loader and permissions of `Lookup`, returning the `Class` object.
- `nominal.equals(otherNominal)` compares nominal structure; `liveClassA == liveClassB` compares for **the same runtime class object**.

### 2.1. Two naming notations not to confuse

| Meaning | Example |
| --- | --- |
| Binary name used with `ClassDesc.of` | `java.lang.String` |
| JVM field descriptor used with `ClassDesc.ofDescriptor` | `Ljava/lang/String;` |
| Primitive `int` descriptor | `I` or `ConstantDescs.CD_int` |
| Array `String[]` descriptor | `[Ljava/lang/String;` |
| Binary name of nested class `Outer.Inner` | `pkg.Outer$Inner` |

Do not pass `"Ljava/lang/String;"` to `ClassDesc.of` as if it were a binary name; use `ClassDesc.ofDescriptor`. For primitives, use the predefined constants in `ConstantDescs` or the corresponding primitive descriptor.

### 2.2. Having a description still does not guarantee the class exists

~~~java
ClassDesc unknown = ClassDesc.of("example.missing.NotThere");
System.out.println(unknown.descriptorString());
// Lexample/missing/NotThere;
~~~

The line above succeeds even if the application has no `example.missing.NotThere` class. Only when attempting to resolve:

~~~java
Class<?> missing = (Class<?>) unknown.resolveConstantDesc(
        MethodHandles.lookup());
~~~

can it throw `ClassNotFoundException` (a `ReflectiveOperationException`) or another access/linkage error depending on the situation.

**Do not use the ability to construct a `ClassDesc` successfully as a check that a dependency is installed, a module is readable, or a class has been loaded.**

## 3. The same nominal descriptor can resolve to two different `Class` objects

In the JVM, the runtime identity of a class is typically determined by **binary name + defining class loader**. Two independent class loaders can define two classes with the **same name** that are not the same Java type.

~~~text
                   ClassDesc
          "app.api.Payload"
                │
       ┌────────┴────────┐
       ▼                 ▼
  Lookup in loader A  Lookup in loader B
       │                 │
       ▼                 ▼
  Class<?> A          Class<?> B
  name "app.api.Payload" in both
              A != B
~~~

`ClassDesc` **does not contain** a reference to loader A or B, so descriptions can be `equals` to each other while the `Class<?>` objects obtained from two different contexts are **not `==` to each other**.

Practical consequences:

- An API returning `ClassDesc` is saying "the type with **this name**", not guaranteeing it is the `Class<?>` loaded by a specific plugin or framework.
- `Class.cast`, `instanceof`, reflection, and `MethodHandle` check against the **actual runtime type**, not the name string. Having the same name can still cause a `ClassCastException`.
- If a library receives a descriptor and needs to resolve it, pass/design the proper `Lookup` of the caller with appropriate permissions and loader. Do not arbitrarily substitute `ClassLoader.getSystemClassLoader()` if the application has its own plugin loaders.
- Module boundaries (JPMS) and access permissions can cause resolution to fail even when the class exists.

Section 8 provides a **runnable example with two `URLClassLoader` instances** confirming this observation.

## 4. `MethodTypeDesc` is not `MethodType`

`MethodTypeDesc` holds a **nominal signature** using `ClassDesc` instances. For example, a method taking `String` and returning `String`:

~~~java
MethodTypeDesc nominalType = MethodTypeDesc.of(
        ConstantDescs.CD_String, ConstantDescs.CD_String);
System.out.println(nominalType.descriptorString());
// (Ljava/lang/String;)Ljava/lang/String;

MethodType liveType = (MethodType) nominalType.resolveConstantDesc(
        MethodHandles.lookup());
System.out.println(liveType);
// (String)String
~~~

In this example:

- `MethodTypeDesc` answers the question *how are the method's parameters/return type described?*
- `MethodType` is the runtime object already carrying the real `Class<?>` objects of the parameters and result.
- The form `(Ljava/lang/String;)Ljava/lang/String;` is a **JVM method descriptor**, while `(String)String` is the human-readable printed form of `MethodType`. The two representations are not the same object.

**Java 17 compatibility note:** the `resolveConstantDesc` method, when called through several descriptor interfaces in Java 17, has a declared return type of `Object`, so the examples use explicit casts `(MethodType)`, `(Class<?>)`, or `(MethodHandle)` when needed. Do not copy covariant return signatures from newer Java versions into Java 17 code without verifying.

The description can exist before the involved classes are loaded. `MethodTypeDesc` can also represent signatures that cannot form a valid `MethodType` (for example, exceeding the JVM parameter slot limit). That is another reason why **creating a description** and **resolving to a live type** are two distinct steps.

## 5. `MethodHandleDesc` is not `MethodHandle`

A `MethodHandleDesc` lets you talk about **the handle to be looked up**, without yet having a handle ready to invoke. Given the method `public static String decorate(String)` in class `NominalVsLiveDemo`:

~~~java
MethodTypeDesc signature = MethodTypeDesc.of(
        ConstantDescs.CD_String, ConstantDescs.CD_String);

DirectMethodHandleDesc nominalHandle = MethodHandleDesc.ofMethod(
        DirectMethodHandleDesc.Kind.STATIC,
        ClassDesc.of("NominalVsLiveDemo"),
        "decorate",
        signature);

MethodHandle liveHandle = (MethodHandle) nominalHandle.resolveConstantDesc(
        MethodHandles.lookup());
System.out.println(liveHandle.type()); // (String)String
~~~

The snippet above is an **excerpt** from the complete program in section 7.

The description has the following components: **reference kind** (`STATIC`), **owner** (`ClassDesc`), **member name** (`decorate`), and **lookup method type** (`(String)String` in descriptor form). Only upon resolution does the JVM/`Lookup` check whether the method actually exists, has the right kind and signature, and whether the caller has permission to look up the method.

| `MethodHandleDesc` | `MethodHandle` |
| --- | --- |
| Describes a symbolic target/adapter | Runtime reference to the ability to invoke a method/field/constructor or adapter |
| Can be created even if the method is not yet on the classpath | Exists only once a valid handle has been obtained |
| Has no `invokeExact` to run business logic | Has `invokeExact`, `invoke`, `type()`, combinators... |
| Uses `resolveConstantDesc(lookup)` to find the real handle | Can call `describeConstable()` to request creating a reverse descriptor, **if representable** |
| Compares descriptors with `equals` | Do not infer identity from having the same descriptor; focus on `type()` and invocation semantics |

For instance methods (for example kind `VIRTUAL`), the method's **lookup descriptor** describes only the declared method parameters, whereas the **handle's invocation type** usually has an additional **receiver as the first parameter**. Do not confuse `lookupDescriptor` with `invocationType()` when designing nominal method handles.

### 5.1. A descriptor for an absent method can still be created

~~~java
DirectMethodHandleDesc missing = MethodHandleDesc.ofMethod(
        DirectMethodHandleDesc.Kind.STATIC,
        ClassDesc.of("NominalVsLiveDemo"),
        "noSuchMethod",
        MethodTypeDesc.of(
                ConstantDescs.CD_String, ConstantDescs.CD_String));
~~~

Creating this descriptor **does not invoke** and **does not look up** `noSuchMethod`. However, `missing.resolveConstantDesc(lookup)` will fail, for instance with `NoSuchMethodException` in the verified example.

With a real method name where the caller lacks access permission, the error may be `IllegalAccessException`. With an unresolvable class, the error may occur earlier at the class resolution step. Do not lump all these errors together as "MethodHandleDesc syntax error".

### 5.2. Not every runtime handle can be described in reverse

The `Constable` interface has `describeConstable()` returning `Optional<ConstantDesc>` (or a suitable subtype). `MethodHandle` implements `Constable`, but not every adapter chain, object-bound handle, closure, or dynamic handle has a suitable nominal representation.

~~~java
java.util.Optional<java.lang.constant.MethodHandleDesc> description =
        liveHandle.describeConstable();
~~~

This is an illustrative snippet with an existing `liveHandle` variable. `Optional.empty()` is a valid outcome; **do not** call `orElseThrow()` unconditionally to assume every handle has a descriptor. Simple direct handles can usually be described in reverse, while composed handles may not.

Even when `describeConstable()` returns a non-empty `Optional`, it is still a **description**, not a mechanism that preserves the handle's **object identity** or the entire program state for transfer to another JVM.

## 6. `DynamicConstantDesc` and real dynamic constants in the constant pool

This is the direct connection to topic **14. Dynamic constants**.

### 6.1. Real condy in a class file

A Java 11+ class file can contain a `CONSTANT_Dynamic_info` entry (tag 17), pointing to:

~~~text
CONSTANT_Dynamic_info:
  bootstrap_method_attr_index  -> bootstrap method + static arguments
  name_and_type_index          -> constant name + field descriptor

Theoretical example:
  name: MY_VALUE
  type: Ljava/lang/String;
  bootstrap: ConstantBootstraps.invoke
  static args: method handle describing decorate(String)String, "Java"
~~~

This is a **diagram**, not a `javap` dump from the program in section 7. `CONSTANT_Dynamic_info` is resolved when a bytecode `ldc` / `ldc_w` / `ldc2_w` uses that constant (or when it is resolved as a static bootstrap argument).

During **resolution**, the JVM obtains:

1. `MethodHandles.Lookup` associated with the class containing the symbolic reference.
2. The **constant name** as a `String`, for example `MY_VALUE`.
3. The **actual constant type** as a `Class<?>` (for example `String.class`), **not** a `MethodType`.
4. The already-resolved **static bootstrap arguments**.

The BSM is executed to compute **a value** matching the constant's field descriptor, such as a `String` or `Class<?>`. The JVM verifies/converts the result according to JVMS rules. After successful resolution, the same symbolic reference in the runtime constant pool returns **the linked result** without running the BSM again; resolution errors are also recorded.

### 6.2. `DynamicConstantDesc` is only a description, not a linked JVM entry

`DynamicConstantDesc.ofNamed(...)` creates a **nominal descriptor on the Java heap**:

~~~java
DynamicConstantDesc<String> desc = DynamicConstantDesc.ofNamed(
        ConstantDescs.BSM_INVOKE,
        "MY_VALUE",
        ConstantDescs.CD_String,
        nominalHandle,
        "Java");
~~~

This is an excerpt with `nominalHandle` from section 5. It describes the standard bootstrap `ConstantBootstraps.invoke`, the constant name, the `String` type, and two static arguments (the method handle description + the string `Java`). **No `String` value has been computed merely by constructing the `desc` object.**

Meaning of each component:

| Component | Example value | What it is not yet |
| --- | --- | --- |
| `bootstrapMethod()` | `ConstantDescs.BSM_INVOKE` — a `DirectMethodHandleDesc` | The live `MethodHandle` of the BSM |
| `constantName()` | `MY_VALUE` | A Java field name that must exist |
| `constantType()` | `ConstantDescs.CD_String` — `ClassDesc` for the result type | Live `String.class` or a string value |
| `bootstrapArgs()` | Descriptor of `decorate` and the string `"Java"` | An invocation `decorate("Java")` that has already happened |
| `resolveConstantDesc(lookup)` | Computes the value in the current context | A mere "create descriptor" step |

**Two meanings of the word `Class` in the example must be distinguished:**

- `ClassDesc.of("java.lang.String")` in section 2 **describes a class constant** whose resolved value is **`String.class`**.
- `dynamic.constantType() == ConstantDescs.CD_String` states that **the type of the dynamic constant to be returned is `String`**, so `dynamic.resolveConstantDesc(...)` returns a **string**, not a `Class<?>` object.

If the dynamic constant is meant to return a `Class<?>` itself, `constantType` would describe the type `java.lang.Class`, for example `ConstantDescs.CD_Class`; the BSM's result must still be a value of the corresponding type. Do not confuse the type of the **result** with the class that the result is describing.

### 6.3. Major difference: cached or not?

The following two paths **do not have the same caching semantics**:

~~~text
A. Resolving a descriptor from the Java API:
  DynamicConstantDesc instance
    ├─ resolveConstantDesc(lookup) -> runs bootstrap, produces value A
    └─ resolveConstantDesc(lookup) -> may run bootstrap again, value B

B. JVM resolving CONSTANT_Dynamic_info of a class file:
  constant-pool symbolic reference
    ├─ first resolution -> runs bootstrap, records result
    └─ subsequent uses  -> same result, does NOT run bootstrap again
~~~

The Java 17 Javadoc of `ConstantDesc.resolveConstantDesc` explicitly states that it **does not cache resolution results**. Meanwhile, JVMS `5.4.3` specifies that **resolution of a symbolic reference in the runtime constant pool** is recorded; a real condy's bootstrap does not automatically re-run each time the same symbolic reference is used. Both must be distinguished before reasoning about performance, side effects, or identity.

In the program in section 7, calling `dynamic.resolveConstantDesc(lookup)` twice causes the `decorate` function to increment the counter twice. This is **not** evidence that the JVM ran the bootstrap **twice for the same `CONSTANT_Dynamic_info` entry**; this program does not emit a corresponding condy entry.

### 6.4. Do not confuse condy with `invokedynamic`

| Point | `CONSTANT_Dynamic_info` (condy) | `CONSTANT_InvokeDynamic_info` |
| --- | --- | --- |
| Commonly used bytecode | `ldc` / `ldc_w` / `ldc2_w` | `invokedynamic` |
| Descriptor type in `NameAndType` | **Field descriptor** of the value (e.g. `Ljava/lang/String;`) | **Method descriptor** of the call site (e.g. `(I)Ljava/lang/String;`) |
| Target type received by BSM | `Class<?>` | `MethodType` |
| Bootstrap result | A **constant value** | A **`CallSite`** |
| After linking | Reuses the resolved value of the symbolic reference | The linked instruction uses the chosen site to dispatch to the target |
| Java nominal model | `DynamicConstantDesc` | Not identical to `DynamicConstantDesc`; call site info is `invokedynamic` metadata |

Even though both use a BSM, a **dynamic constant** is not "a method handle always invoked every time", and **invokedynamic** is not "a string constant computed once". A condy BSM can **return a MethodHandle or Class object as a value**, but it is still a resolved constant, not automatically turned into a call site.

## 7. Complete Java 17 example: creating descriptors, resolving, invoking a handle, and observing a condy descriptor

Save the program as **`NominalVsLiveDemo.java`**. Run it on the class path in the directory containing the file. This snippet **executes `DynamicConstantDesc.resolveConstantDesc` via the Java API**, and does not itself compile into a constant-pool `CONSTANT_Dynamic_info`. It is especially useful because it shows the difference between **describing** and **resolving**.

~~~java
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.DirectMethodHandleDesc;
import java.lang.constant.DynamicConstantDesc;
import java.lang.constant.MethodHandleDesc;
import java.lang.constant.MethodTypeDesc;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class NominalVsLiveDemo {
    static int calls;

    public static String decorate(String input) {
        calls++;
        return "value(" + input + "):" + calls;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        ClassDesc classDesc = ClassDesc.of("java.lang.String");
        ClassDesc equivalent = ClassDesc.ofDescriptor("Ljava/lang/String;");
        System.out.println("class symbolic: " + classDesc.descriptorString());
        System.out.println("same description: " + classDesc.equals(equivalent));
        Class<?> actualClass = (Class<?>) classDesc.resolveConstantDesc(lookup);
        System.out.println("resolved class is String: " + (actualClass == String.class));

        MethodTypeDesc typeDesc = MethodTypeDesc.of(
                ConstantDescs.CD_String, ConstantDescs.CD_String);
        MethodType actualType = (MethodType) typeDesc.resolveConstantDesc(lookup);
        System.out.println("method descriptor: " + typeDesc.descriptorString());
        System.out.println("runtime method type: " + actualType);

        DirectMethodHandleDesc handleDesc = MethodHandleDesc.ofMethod(
                DirectMethodHandleDesc.Kind.STATIC,
                ClassDesc.of("NominalVsLiveDemo"),
                "decorate", typeDesc);
        MethodHandle actualHandle = (MethodHandle) handleDesc.resolveConstantDesc(lookup);
        System.out.println("handle descriptor type: " +
                handleDesc.invocationType().descriptorString());
        System.out.println("runtime handle type: " + actualHandle.type());
        System.out.println("direct handle describable: " +
                actualHandle.describeConstable().isPresent());

        DynamicConstantDesc<String> dynamic = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_INVOKE,
                "MY_VALUE",
                ConstantDescs.CD_String,
                handleDesc,
                "Java");
        System.out.println("dynamic name: " + dynamic.constantName());
        System.out.println("dynamic type: " + dynamic.constantType().descriptorString());
        System.out.println("calls before resolve: " + calls);
        System.out.println("resolve first: " + dynamic.resolveConstantDesc(lookup));
        System.out.println("resolve second: " + dynamic.resolveConstantDesc(lookup));
        System.out.println("calls after resolve: " + calls);
        System.out.println("handle invocation: " + (String) actualHandle.invokeExact("API"));

        ClassDesc missing = ClassDesc.of("example.missing.NotThere");
        System.out.println("missing symbol: " + missing.descriptorString());
        try {
            missing.resolveConstantDesc(lookup);
            throw new AssertionError("Expected missing class failure");
        } catch (ReflectiveOperationException e) {
            System.out.println("missing resolve: " + e.getClass().getSimpleName());
        }

        DirectMethodHandleDesc absentMethod = MethodHandleDesc.ofMethod(
                DirectMethodHandleDesc.Kind.STATIC,
                ClassDesc.of("NominalVsLiveDemo"),
                "noSuchMethod", typeDesc);
        System.out.println("missing method described: " +
                absentMethod.methodName());
        try {
            absentMethod.resolveConstantDesc(lookup);
            throw new AssertionError("Expected missing method failure");
        } catch (ReflectiveOperationException e) {
            System.out.println("missing method resolve: " + e.getClass().getSimpleName());
        }
    }
}
~~~

Commands to run with **JDK 17 or later**:

~~~bash
javac --release 17 NominalVsLiveDemo.java
java NominalVsLiveDemo
~~~

**Verified exact stdout** (OpenJDK 21 running code compiled at Java 17 level):

~~~text
class symbolic: Ljava/lang/String;
same description: true
resolved class is String: true
method descriptor: (Ljava/lang/String;)Ljava/lang/String;
runtime method type: (String)String
handle descriptor type: (Ljava/lang/String;)Ljava/lang/String;
runtime handle type: (String)String
direct handle describable: true
dynamic name: MY_VALUE
dynamic type: Ljava/lang/String;
calls before resolve: 0
resolve first: value(Java):1
resolve second: value(Java):2
calls after resolve: 2
handle invocation: value(API):3
missing symbol: Lexample/missing/NotThere;
missing resolve: ClassNotFoundException
missing method described: noSuchMethod
missing method resolve: NoSuchMethodException
~~~

**Reading the output layer by layer:**

1. The two `ClassDesc` instances have the same structure, so `same description: true`. Only at the resolution step is the real `Class<?>` obtained, and then checked with `== String.class`.
2. `MethodTypeDesc` prints the JVM descriptor, whereas `MethodType` prints `(String)String`. Those are two objects at two different layers.
3. `handleDesc` describes `decorate(String)String`; `actualHandle` is the real handle. You can call `actualHandle.invokeExact("API")`; you cannot use `invokeExact` directly on `handleDesc`.
4. `calls before resolve: 0` proves that **merely constructing `DynamicConstantDesc` has not executed `decorate`**.
5. Two calls to `resolveConstantDesc` produce `value(Java):1` and `value(Java):2` — **there is no caching** on this API path.
6. Afterward, `handle invocation` produces `value(API):3`, proving the live handle is an existing callable capability with the real class's state.
7. Both `ClassDesc` for an absent class and `MethodHandleDesc` for an absent method construct successfully; they only fail upon **resolve**.

Note: the program intentionally uses `static int calls` to observe side effects. A real constant bootstrap in a class file has different caching rules; do not use this program's counter to infer the JVM's BSM invocation count for real condy.

## 8. Complete Java 17 example: same `ClassDesc` but two different class loaders

This is a practical exercise focused on **identity**. Save the file **`LoaderResolutionDemo.java`** in the same directory (or a new directory) with the following content:

~~~java
import java.lang.constant.ClassDesc;
import java.lang.invoke.MethodHandles;
import java.net.URL;
import java.net.URLClassLoader;

public class LoaderResolutionDemo {
    public static class Marker {}

    public static void main(String[] args) throws Throwable {
        ClassDesc nominal = ClassDesc.of(Marker.class.getName());
        URL root = LoaderResolutionDemo.class.getProtectionDomain().getCodeSource().getLocation();

        try (URLClassLoader loaderOne = new URLClassLoader(
                     new URL[] {root}, ClassLoader.getPlatformClassLoader());
             URLClassLoader loaderTwo = new URLClassLoader(
                     new URL[] {root}, ClassLoader.getPlatformClassLoader())) {

            Class<?> first = Class.forName(Marker.class.getName(), false, loaderOne);
            Class<?> second = Class.forName(Marker.class.getName(), false, loaderTwo);
            MethodHandles.Lookup accessOne =
                    MethodHandles.privateLookupIn(first, MethodHandles.lookup());
            MethodHandles.Lookup accessTwo =
                    MethodHandles.privateLookupIn(second, MethodHandles.lookup());

            System.out.println("one name: " + first.getName());
            System.out.println("same name: " + first.getName().equals(second.getName()));
            System.out.println("same live Class: " + (first == second));
            System.out.println("same nominal: " +
                    first.describeConstable().orElseThrow().equals(
                            second.describeConstable().orElseThrow()));
            System.out.println("resolve one: " + (nominal.resolveConstantDesc(accessOne) == first));
            System.out.println("resolve two: " + (nominal.resolveConstantDesc(accessTwo) == second));
        }
    }
}
~~~

Note on running conditions: compile this file to a **regular class directory** and then run from the class path; here `CodeSource` is the URL of the directory containing the `.class` files. Both `URLClassLoader` instances use **the platform loader as parent** so they do not automatically delegate loading `LoaderResolutionDemo$Marker` to the application loader. Because both can read the same bytecode yet define the class themselves, they create **two distinct `Class<?>` objects**. `privateLookupIn` grants an appropriate lookup context for each instance in this example running on the class path/unnamed module; in a named module, appropriate `opens` configuration may be required.

~~~bash
javac --release 17 LoaderResolutionDemo.java
java LoaderResolutionDemo
~~~

**Verified stdout:**

~~~text
one name: LoaderResolutionDemo$Marker
same name: true
same live Class: false
same nominal: true
resolve one: true
resolve two: true
~~~

Meaning:

- `first.getName().equals(second.getName())` is `true`, but `first == second` is `false`.
- The two `ClassDesc` instances produced by `Class.describeConstable()` are **equal in description**.
- `nominal.resolveConstantDesc(accessOne)` resolves to `first`, while `nominal.resolveConstantDesc(accessTwo)` resolves to `second`.
- Therefore, **a nominal descriptor is not tied to a specific `Class<?>` object or loader**. Do not treat `ClassDesc.equals` as a substitute for checking loader identity when writing a plugin framework.

The example does not create live `MethodHandle` instances from the two loaders because demonstrating the difference at the **`Class`** level is sufficient. When handles are resolved in two such environments, a `MethodHandle`'s type can reference `Class<?>` objects with different identities, and cast/invocation behavior is also affected.

## 9. `Constable.describeConstable` is a conditional reverse path

The `java.lang.constant.Constable` API supports asking whether a runtime object can **describe itself** with a descriptor:

~~~text
LIVE OBJECT                    NOMINAL DESCRIPTOR
String.class        --describeConstable()--> ClassDesc
MethodType          --describeConstable()--> MethodTypeDesc
direct MethodHandle --describeConstable()--> MethodHandleDesc
                                       │
                                       ▼
                        resolveConstantDesc(lookup)
                                       │
                                       ▼
                        corresponding LIVE OBJECT
~~~

However, `describeConstable()` returns an **`Optional`**, not a guarantee that a value is always present. A complex handle produced by combinators or binding runtime state may have no equivalent nominal representation, and can therefore return `Optional.empty()`.

Moreover, even with a valid descriptor:

- The descriptor can be resolved in a **different `Lookup` context**, leading to a different live class/handle or an access error.
- There is no guarantee of **object identity** between the original object and the object recreated from the description. A `Class<?>` in the same loader may be the same class, but a new `MethodHandle` does not need to be `==` to the previous handle.
- `describeConstable()` is not general-purpose serialization of the heap, threads, class loaders, or captured state.

**How to compare properly:** use `equals` for nominal descriptors, use `Class<?> ==` when class identity is needed, use `MethodType.equals` to check runtime signatures, and invoke `MethodHandle` according to its type/argument contract rather than inferring from printed names.

## 10. Common misconceptions when working with condy

| Misconception | What to actually remember |
| --- | --- |
| "`ClassDesc` is a lightweight `Class<?>`." | It is a **nominal description**, lacking access permissions, a loader, and runtime metadata like `Class<?>`. |
| "Being able to create `ClassDesc.of(name)` means the class exists." | Only resolution tells; you may encounter `ClassNotFoundException` or access/linkage issues. |
| "If two `ClassDesc` instances are equal, the two runtime `Class` objects are definitely the same." | No. The resolver uses `Lookup` and a loader; two loaders can define two different classes with the same name. |
| "`MethodTypeDesc` is `MethodType`." | `MethodTypeDesc` holds the signature in nominal form; `MethodType` holds resolved runtime classes. |
| "`MethodHandleDesc` can be invoked with `invokeExact`." | Only a **resolved `MethodHandle`** has the invocation APIs. |
| "A valid method description guarantees the method exists." | You can describe an absent method; resolution is what looks it up and checks permissions. |
| "Every `MethodHandle.describeConstable()` has a value." | It returns `Optional`, which can be empty for handles not representable in the constant pool. |
| "`DynamicConstantDesc.ofNamed` has already run the BSM." | It only builds the recipe; the BSM is called when attempting to resolve via the API or when the JVM links a real dynamic constant. |
| "`constantType()` returns the dynamic constant value itself." | It returns the **`ClassDesc` describing the result type**, not the value. |
| "`resolveConstantDesc` caches like a real `ldc`." | This Java API **does not cache**; resolution of a condy symbolic reference in the JVM **is recorded**. |
| "Both condy and `invokedynamic` return a `CallSite`." | Condy returns a **value of a field-descriptor type**; invokedynamic requires a **`CallSite`**. |
| "`javac` generates `CONSTANT_Dynamic_info` whenever I create a `DynamicConstantDesc`." | Creating a descriptor in Java source **does not insert** a constant-pool entry into the class file. Appropriate bytecode tools/generators are needed if you want to actually emit condy. |
| "Adding `--add-opens` fixes all loader errors." | Module permissions and class identity are two separate issues; the flag does not unify two class definitions loaded by different loaders. |

## 11. Practical workflow when debugging

1. **Identify what kind of object you have:** `ClassDesc` or `Class<?>`? `MethodHandleDesc` or `MethodHandle`? `DynamicConstantDesc` or the value itself? Use actual class/API names, not `toString()` strings.
2. **Record the nominal structure:** `descriptorString()`, owner, kind, method name, `invocationType()`, constant name/type, bootstrap method, and bootstrap args.
3. **Record the resolution context:** `Lookup.lookupClass()`, the caller's class loader/module, and module/package permissions. With multiple plugins, use the proper `Lookup` that has permissions in the target resolution area.
4. **Resolve in a controlled way:** call `resolveConstantDesc(lookup)` in tests that handle `ReflectiveOperationException` and `LinkageError` appropriately; avoid running bootstraps with side effects in unauthorized diagnostic paths.
5. **Compare at runtime:** `Class<?> ==`, `MethodType.equals`, `MethodHandle.type()`; if permitted, invoke the handle with `invokeExact` using the exact descriptor and controlled inputs.
6. **If real condy is involved:** inspect with `javap -v -p` or a classfile tool to look for `CONSTANT_Dynamic_info`, `BootstrapMethods`, and the name/field descriptor; do not just look at a `DynamicConstantDesc` object on the heap and assume the classfile has condy.
7. **Distinguish caching:** clearly note whether you are testing `DynamicConstantDesc.resolveConstantDesc` from the Java API or executing an `ldc` referencing a linked JVM dynamic constant.
8. **Maintain the boundary between name and authority:** do not treat an externally supplied descriptor string as automatic permission to access private classes/methods. `Lookup` and JVM checks still apply.

## 12. Self-check questions

**1.** `ClassDesc.of("my.plugin.Service")` can be created when the JAR is not yet on the classpath. Does that prove `Service.class` already exists?  
**Answer:** No. The descriptor only stores a nominal description. Resolution in an actual loader/`Lookup` determines whether the class exists/is accessible.

**2.** Two separate class loaders both define `my.plugin.Service`. The two `ClassDesc` instances created from that name are equal; are the corresponding `Class<?>` objects necessarily `==`?  
**Answer:** No. Runtime class identity also depends on the defining loader.

**3.** `MethodHandleDesc.ofMethod(...)` points to a non-existent method. When is the error typically detected?  
**Answer:** When `resolveConstantDesc(lookup)` attempts to look up the method, not when creating the description.

**4.** A `DynamicConstantDesc<String>` has `constantType()==CD_String`. Does calling `constantType()` return the `String` created by the bootstrap?  
**Answer:** No. It returns a `ClassDesc` for the **result type**, not the value.

**5.** With `DynamicConstantDesc.resolveConstantDesc(lookup)` called twice, can the bootstrap run twice? What if the same `CONSTANT_Dynamic_info` is used multiple times by `ldc`?  
**Answer:** The reflective API **does not cache**, so it can execute the BSM twice. Successful JVM resolution of the **same symbolic reference** in the runtime constant pool is recorded; subsequent uses do not call the BSM again.

**6.** You need to invoke a method described by `DirectMethodHandleDesc`. Before `invokeExact`, which API is needed?  
**Answer:** `resolveConstantDesc(lookup)` to obtain a `MethodHandle` with the appropriate type, then invoke `invokeExact` with the exact descriptor.

**7.** Why should you not use the result of `describeConstable()` to check whether two function objects have the same identity?  
**Answer:** It describes the nominal recipe when representable, and **does not** guarantee the identity of the runtime object or captured state.

**8.** A bootstrap for a dynamic constant returns a `MethodHandle`. Does that turn condy into `invokedynamic`?  
**Answer:** No. Condy remains a constant with result type `MethodHandle`; `invokedynamic` is a dynamic call site linked to a `CallSite`.

## Official documentation (Java 17)

- [`java.lang.constant`: Nominal Descriptors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/package-summary.html)
- [`ConstantDesc.resolveConstantDesc` and the no-caching rule](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/ConstantDesc.html)
- [`ClassDesc`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/ClassDesc.html)
- [`MethodTypeDesc`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/MethodTypeDesc.html)
- [`MethodHandleDesc` and `DirectMethodHandleDesc`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/MethodHandleDesc.html)
- [`DynamicConstantDesc`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/DynamicConstantDesc.html)
- [`Constable`, `ConstantDescs`, `ConstantBootstraps`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/Constable.html)
- [JVMS 17 `4.4.10: `CONSTANT_Dynamic_info`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4.10)
- [JVMS 17 `5.4.3: Resolution and result recording](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3)
- [JVMS 17 `5.4.3.6: Resolution of dynamic constants and call sites](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6)