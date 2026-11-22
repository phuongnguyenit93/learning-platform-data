# 14.5. ConstantDesc, ClassDesc, MethodTypeDesc, and MethodHandleDesc

> **Scope:** Knowledge lesson in group **14. Dynamic Constants** of **Java Advance – dynamic-runtime**, based on Java SE 21. The focus is the `java.lang.constant` API suite: `ConstantDesc` as a **nominal descriptor**, `ClassDesc` describing classes, `MethodTypeDesc` describing method types, and `MethodHandleDesc` describing method handles. They can be **constructed, compared, and analyzed before the class/method exists or is resolved**, and then resolved within a `MethodHandles.Lookup` access context. The lesson also connects them to `DynamicConstantDesc` and the constant pool (`CONSTANT_Dynamic`), without equating creating a descriptive Java object with generating a class file.

## 1. Learning Objectives

After studying, you will be able to:

1. Distinguish **runtime values** (`Class<?>`, `MethodType`, `MethodHandle`) from **nominal descriptors** (`ClassDesc`, `MethodTypeDesc`, `MethodHandleDesc`).
2. Explain how `ConstantDesc.resolveConstantDesc(lookup)` uses a **Lookup context**, including class loading, module, and access checks, rather than merely parsing a string.
3. Create `ClassDesc` using `of`, `ofDescriptor`, `ofInternalName`, `arrayType`; accurately read *field descriptors* and internal names.
4. Create and transform `MethodTypeDesc` using `of`, `ofDescriptor`, `changeReturnType`, `insertParameterTypes`, `descriptorString`; recognize erased types and runtime limits.
5. Use `MethodHandleDesc.ofMethod`, `ofConstructor`, and `ofField` with the right `DirectMethodHandleDesc.Kind`; distinguish **lookup descriptor** from **invocation type**.
6. Resolve a method-handle descriptor with an appropriate `Lookup` and invoke it via `invokeExact`; understand errors caused by missing class, missing member, wrong kind/type, and insufficient access.
7. Describe the connection to `Constable.describeConstable()`, `ConstantDescs`, `DynamicConstantDesc`, and the bootstrap method of `CONSTANT_Dynamic`.
8. Independently run five standalone Java 21 programs, verify stdout, and know why the **same nominal description with different lookup contexts** can yield different results.

**Prerequisites:** JVM field/method descriptors, `Class<?>`, Reflection, `MethodHandles.Lookup`, static/virtual methods, constructors, fields, class loaders, JPMS, and basic Java generics/erasure. No ASM/Byte Buddy or JDK internal APIs needed. Examples use `javac --release 21` and APIs available in Java 21.

## 2. Why Does the JVM Need Nominal Descriptors?

In bytecode, a `CONSTANT_Class_info` describes a class by name; `CONSTANT_MethodType_info` describes a method type by a method descriptor string; `CONSTANT_MethodHandle_info` points to a method/constructor/field along with a *reference kind*. `CONSTANT_Dynamic_info` describes **a value to be computed at resolution time by a bootstrap method**. Constant pool entries are symbolic information; they do not inherently carry a linked `Class<?>` or `MethodHandle` of a specific Java process.

`java.lang.constant` (Java 12+) provides **Java objects representing** those descriptions, which is very convenient for bytecode readers/writers, code generation, constant-pool analysis, runtime metadata, and pre-link validation. According to the package Javadoc, a `ConstantDesc` is a **recipe for a constant value**: you can inspect the recipe, hold onto it, and resolve it when an appropriate context is available.

```text
JVM symbolic information                      Runtime objects
------------------------                      ---------------------------
ClassDesc("java.lang.String")     -- Lookup --> java.lang.String.class
MethodTypeDesc("(I)String")       -- Lookup --> MethodType(int -> String)
MethodHandleDesc(owner/name/kind) -- Lookup --> linked MethodHandle
DynamicConstantDesc(BSM, name...) -- Lookup --> value returned by BSM

                  resolveConstantDesc(lookup)
                  + class loading/module access
                  + member lookup/linkage (depending on kind)
```

The notation `"(I)String"` in the diagram is a **human-readable notation**, not a valid JVM method descriptor string. The actual JVM string for `String m(int)` is `(I)Ljava/lang/String;`.

**Key point:** `ClassDesc.of("com.acme.Widget")` does **not** immediately load `com.acme.Widget`. `MethodHandleDesc.ofMethod(...)` does **not** automatically find/invoke the method. The factories create *descriptor* objects; only the `resolveConstantDesc(lookup)` operation requests a runtime value. Running `resolveConstantDesc` with a different Lookup may fail or yield different runtime types.

## 3. The Four Core Concepts and Their Relationships

| API | Nominal description for | Main inputs/metadata | Result of `resolveConstantDesc(lookup)` |
| --- | --- | --- | --- |
| `ConstantDesc` | Common interface for describable constants | Resolution contract in `Lookup` | `Object` (subtypes typically return specialized types) |
| `ClassDesc` | Class, interface, primitive, array, void types | JVM field-type descriptor or nominal class name | `Class<?>` |
| `MethodTypeDesc` | Return + ordered parameter types | `ClassDesc` and JVM method descriptor | `MethodType` |
| `MethodHandleDesc` | A method/constructor/field handle | Owner `ClassDesc`, name, reference kind, type | `MethodHandle` |

Important properties:

- `ConstantDesc` in Java 21 is a **sealed interface**, with branches specified by the JDK. `ClassDesc`, `MethodTypeDesc`, and `MethodHandleDesc` are all `ConstantDesc`; `DirectMethodHandleDesc` is a specialized subtype for direct handles.
- `String`, `Integer`, `Long`, `Float`, `Double` are native constant types that can **act as `ConstantDesc` themselves** for their own values. **Do not assume** that every boxed primitive or every object directly implements `ConstantDesc`.
- Constant descriptors are designed to be **immutable**; compare semantic equality with `equals`, **not** with `==`, because the JDK does not guarantee that a descriptor is interned into a single instance.
- A `ConstantDesc` is not a promise that every resolution will always succeed. The runtime environment may lack the class, restrict access, or be unable to represent a type even when the nominal descriptor is valid.
- A Java descriptor object **does not automatically create** an extra `CONSTANT_*` entry in a class file: emitting bytecode requires a separate compiler or bytecode writer.

### 3.1. Comparing “Described” and “Resolved”

| Question to ask | Nominal descriptor | Runtime counterpart |
| --- | --- | --- |
| “What is the class name?” | `ClassDesc.descriptorString()` | `Class.getName()` or `getTypeName()` |
| “What component does the array have?” | `ClassDesc.componentType()` | `Class.getComponentType()` |
| “What types does the method take/return?” | `MethodTypeDesc.parameterType(i)`, `returnType()` | `MethodType.parameterType(i)`, `returnType()` |
| “Which method/field does the handle call?” | `DirectMethodHandleDesc.owner()`, `methodName()`, `kind()` | `MethodHandle`, `revealDirect` if sufficient privileges |
| “Is access permitted?” | Cannot be concluded from descriptor alone | `resolveConstantDesc(lookup)` and runtime checks |
| “Do two types with the same name have the same identity?” | Same nominal name may have `equals=true` | May be **different `Class<?>`** if loaders differ |

`MethodTypeDesc` is not a “renamed” version of `MethodType` in every context; nominal information is separate from runtime resolution and is subject to different JVM constraints.

## 4. `ConstantDesc`: The Interface for Recipes and Resolution

The core of `ConstantDesc` is:

```java
// Abbreviated signature from the API, not a complete interface declaration.
Object resolveConstantDesc(MethodHandles.Lookup lookup)
        throws ReflectiveOperationException;
```

A `lookup` carries a **lookup class**, class loader, and **access modes**, helping resolve class/member names according to JVM/JPMS rules. The result is the actual value of the constant:

- For `ClassDesc`: a `Class<?>` such as `String.class`.
- For `MethodTypeDesc`: a `MethodType` with concrete parameter/return `Class<?>`.
- For `MethodHandleDesc`: a resolved `MethodHandle`, ready to invoke with a valid signature.
- For `DynamicConstantDesc<T>`: the value computed by the bootstrap method, which may be `null` when the kind/BSM allows it.
- For `"hello"` or `Integer.valueOf(7)`: the native constant value itself.

Do not blindly catch every `ReflectiveOperationException` and treat it as “no descriptor”; the description may still be syntactically valid. Classify at least: **syntax/shape**, **class resolution**, **access**, **member lookup**, **linkage**, **invocation**.

### 4.1. Lookup Context Is Not Serialized into the Descriptor

Two class loaders can define two `com.acme.Message` classes with the same binary name. `ClassDesc.of("com.acme.Message")` is the same nominal description, but resolving through Lookups from different loaders may return **two `Class<?>` objects with different identities**, or fail if one side cannot see the class. A `MethodTypeDesc` or `MethodHandleDesc` containing that `ClassDesc` also inherits this contextual factor.

**Do not use only the descriptor string as a runtime cache key** across plugins/module layers. If you need to cache after resolution, partition by `Lookup`/loader/module and appropriate privileges, or use the runtime class/member identity itself.

### 4.2. Resolution Does Not Imply Caching

According to the Javadoc, `resolveConstantDesc` **does not guarantee caching the result per descriptor object**. Some runtime entities (`Class<?>`, `MethodType`) have sharing/caching characteristics at the JVM layer, but the descriptor contract does not rely on the identity of resolved results across calls. If optimizing with a cache, you must explicitly design its scope, lifecycle, and the possibility of keeping a class loader alive.

## 5. `ClassDesc`: From Class Name to Field Descriptor

`ClassDesc` expresses types in the same symbolic language as a JVM `field descriptor` (`ClassDesc` also allows describing `void`). Common creation methods:

| Call | Nominal type | `descriptorString()` |
| --- | --- | --- |
| `ClassDesc.of("java.lang.String")` | `String` | `Ljava/lang/String;` |
| `ClassDesc.ofInternalName("java/lang/String")` | `String` | `Ljava/lang/String;` |
| `ClassDesc.ofDescriptor("Ljava/lang/String;")` | `String` | `Ljava/lang/String;` |
| `ConstantDescs.CD_int` | primitive `int` | `I` |
| `ConstantDescs.CD_void` | `void` | `V` |
| `ClassDesc.ofDescriptor("[I")` | `int[]` | `[I` |
| `ClassDesc.of("java.lang.String").arrayType(2)` | `String[][]` | `[[Ljava/lang/String;` |
| `ClassDesc.of("java.util.Map$Entry")` | nested `Map.Entry` | `Ljava/util/Map$Entry;` |

**Different names for different purposes:**

1. `of("java.lang.String")` accepts the **dot-separated binary name** of a class/interface.
2. `ofInternalName("java/lang/String")` accepts the **slash-separated internal name**, commonly obtained from bytecode.
3. `ofDescriptor("Ljava/lang/String;")` accepts **a full field type descriptor**; also applies to primitives/arrays. Do not pass a method string `(I)V` into `ClassDesc.ofDescriptor`.
4. `arrayType()` adds one `[`; `arrayType(2)` adds two dimensions; `componentType()` removes one array dimension.
5. `displayName()` is a **human-facing display representation**, not a JVM descriptor, and the class name is not guaranteed to be unique when packages are omitted.

### 5.1. Referencing Nested Classes

In JVM internal names, package separators use `/`, while nested/member classes use the `$` character in the binary name:

```text
Java source:     java.util.Map.Entry
Binary name:     java.util.Map$Entry
Internal name:   java/util/Map$Entry
Field descriptor: Ljava/util/Map$Entry;
```

Do not pass `java.util.Map.Entry` to `ClassDesc.of` as the exact binary name of the nested class. Java source spelling and JVM binary name are not the same in this case.

### 5.2. Type Erasure and Generic Limitations

`ClassDesc` has no constructor for `List<String>` as a distinct class. The class file uses the runtime type `java.util.List` after erasure; generic type arguments (if any) are stored in the `Signature` attribute or other metadata, not in `ClassDesc`.

For example, `ClassDesc.of("java.util.List")` represents the raw runtime class; it **cannot** prove from that alone that elements are always `String`. If you need to analyze generic declarations, use `java.lang.reflect.Type` or a separate class-file signature parser.

## 6. Lab 1 — ClassDesc and Unsuccessful Resolution

Create a standalone file **`ClassDescLab.java`**:

```java
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.invoke.MethodHandles;

public class ClassDescLab {
    public static void main(String[] args) throws ReflectiveOperationException {
        ClassDesc string = ClassDesc.of("java.lang.String");
        ClassDesc fromInternal = ClassDesc.ofInternalName("java/lang/String");
        ClassDesc matrix = string.arrayType(2);
        ClassDesc nested = ClassDesc.of("java.util.Map$Entry");
        ClassDesc absent = ClassDesc.of("demo.missing.NotHere");

        System.out.println("string=" + string.descriptorString());
        System.out.println("sameNominal=" + string.equals(fromInternal));
        System.out.println("matrix=" + matrix.descriptorString());
        System.out.println("matrixDisplay=" + matrix.displayName());
        System.out.println("component=" + matrix.componentType().descriptorString());
        System.out.println("nested=" + nested.descriptorString());
        System.out.println("primitive=" + ConstantDescs.CD_int.descriptorString());
        System.out.println("void=" + ConstantDescs.CD_void.descriptorString());
        System.out.println("resolvedString=" +
                (string.resolveConstantDesc(MethodHandles.lookup()) == String.class));
        System.out.println("classDescribed=" + String.class.describeConstable().isPresent());
        System.out.println("absentNominal=" + absent.descriptorString());
        try {
            absent.resolveConstantDesc(MethodHandles.lookup());
            System.out.println("absentResolve=unexpected");
        } catch (ClassNotFoundException expected) {
            System.out.println("absentResolve=ClassNotFoundException");
        }
    }
}
```

Run from the terminal with a JDK supporting Java 21:

```sh
javac --release 21 -Xlint:all ClassDescLab.java
java ClassDescLab
```

**Stdout:**

```text
string=Ljava/lang/String;
sameNominal=true
matrix=[[Ljava/lang/String;
matrixDisplay=String[][]
component=[Ljava/lang/String;
nested=Ljava/util/Map$Entry;
primitive=I
void=V
resolvedString=true
classDescribed=true
absentNominal=Ldemo/missing/NotHere;
absentResolve=ClassNotFoundException
```

### 6.1. Why Do the Results Make Sense?

- The two descriptor creation methods `of` and `ofInternalName` produce the same nominal type, so `equals` returns `true`.
- `String[][]` is encoded as `[[Ljava/lang/String;`; the one-dimensional component is `[Ljava/lang/String;`.
- `CD_int` and `CD_void` are predefined nominal primitive/void descriptors in `ConstantDescs`.
- `String.class.describeConstable()` returns a present `Optional<ClassDesc>` because `String` is a type that can be described nominally.
- `ClassDesc.of("demo.missing.NotHere")` still creates a **valid descriptor** without loading the class. Only when `resolveConstantDesc(lookup)` runs does the request to resolve the non-existent class fail with `ClassNotFoundException`.

### 6.2. “Being Able to Create a ClassDesc” Is Not “Being Able to Load a Class”

Even a syntactically valid descriptor name may not exist in the class loader, may be blocked by module access, or may reference a broken dependency. That is why bytecode analysis libraries work nominally first, and defer resolution until an appropriate runtime environment is available.

## 7. `MethodTypeDesc`: Method Descriptors as ClassDescs

A JVM method descriptor has the structure:

```text
MethodDescriptor = "(" {ParameterDescriptor} ")" ReturnDescriptor
ParameterDescriptor = FieldType
ReturnDescriptor    = FieldType | V
FieldType           = BaseType | ObjectType | ArrayType
```

Primitive codes include `B`, `C`, `D`, `F`, `I`, `J`, `S`, `Z`; an object type is `Linternal/name;`; an array type has a `[` prefix. `V` is only valid as the return type; a `void` parameter is not allowed.

`MethodTypeDesc` provides the main factories:

- `MethodTypeDesc.of(returnClassDesc, paramClassDescs...)`: builds from existing nominal types.
- `MethodTypeDesc.ofDescriptor("(I[Ljava/lang/String;)Ljava/lang/String;")`: parses a JVM method descriptor **without necessarily loading the classes**.
- `descriptorString()`: outputs JVM format, e.g. `(I)Ljava/lang/String;`.
- `displayDescriptor()`: outputs human-readable format, e.g. `(int,String[])String`; **do not pass display text into a JVM parser**.
- `returnType()`, `parameterType(i)`, `parameterCount()`, and `parameterList()`: structural inspection.
- `changeReturnType(...)`, `changeParameterType(...)`, `dropParameterTypes(...)`, `insertParameterTypes(...)`: create a **new descriptor**, without mutating the old object.
- `resolveConstantDesc(lookup)`: creates a runtime `MethodType` if all referenced classes can be resolved and the type is valid.

### 7.1. Distinguishing MethodTypeDesc from MethodType

| `MethodTypeDesc` | `MethodType` |
| --- | --- |
| Holds nominal `ClassDesc` for types | Holds runtime `Class<?>` for return/parameters |
| Can exist when referenced classes are not yet loaded | Requires resolving classes to obtain runtime `Class<?>` |
| Does not bind a class loader directly to names | Runtime class identity depends on class loader/module |
| `displayDescriptor()`/`descriptorString()` | `toString()`/`toMethodDescriptorString()` |
| Created ahead of time for bytecode generation, metadata | Used directly in runtime MethodHandles/Lookup |

`MethodTypeDesc` can also describe a method descriptor that is **not representable by `MethodType`**, for example exceeding 255 parameter slots per the JVM; the Javadoc warns that resolving such descriptors may fail. Therefore, **successful parsing does not mean a runtime JVM method with that signature can exist**.

### 7.2. No Generics in JVM Method Descriptors

`List<String> transform(List<Integer> source)` has the descriptor after erasure:

```text
(Ljava/util/List;)Ljava/util/List;
```

`MethodTypeDesc` does not distinguish `List<Integer>` and `List<String>` as two different runtime `ClassDesc`s. When generic signatures are needed, use the `Signature` attribute and Reflection `getGenericReturnType()`/`getGenericParameterTypes()`.

## 8. Lab 2 — Creating, Transforming, and Resolving MethodTypeDesc

Create **`MethodTypeDescLab.java`**:

```java
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.MethodTypeDesc;
import java.lang.invoke.MethodType;
import java.lang.invoke.MethodHandles;

public class MethodTypeDescLab {
    public static void main(String[] args) throws ReflectiveOperationException {
        ClassDesc words = ClassDesc.of("java.lang.String").arrayType();
        MethodTypeDesc nominal = MethodTypeDesc.of(
                ConstantDescs.CD_String, ConstantDescs.CD_int, words);
        MethodTypeDesc parsed =
                MethodTypeDesc.ofDescriptor("(I[Ljava/lang/String;)Ljava/lang/String;");
        MethodTypeDesc extended =
                nominal.insertParameterTypes(1, ConstantDescs.CD_long);
        MethodTypeDesc changed =
                nominal.changeReturnType(ConstantDescs.CD_void);
        MethodType actual = nominal.resolveConstantDesc(MethodHandles.lookup());

        System.out.println("descriptor=" + nominal.descriptorString());
        System.out.println("equalParsed=" + nominal.equals(parsed));
        System.out.println("display=" + nominal.displayDescriptor());
        System.out.println("parameters=" + nominal.parameterCount());
        System.out.println("return=" + nominal.returnType().descriptorString());
        System.out.println("extended=" + extended.descriptorString());
        System.out.println("changedReturn=" + changed.descriptorString());
        System.out.println("resolved=" + actual.toMethodDescriptorString());
        System.out.println("describedBack=" +
                actual.describeConstable().orElseThrow().equals(nominal));
        try {
            MethodTypeDesc.ofDescriptor("(V)I");
            System.out.println("invalid=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid=IllegalArgumentException");
        }
        MethodTypeDesc missing = MethodTypeDesc.ofDescriptor("(Ldemo/missing/Never;)V");
        System.out.println("missingNominal=" + missing.descriptorString());
        try {
            missing.resolveConstantDesc(MethodHandles.lookup());
            System.out.println("missingResolve=unexpected");
        } catch (ClassNotFoundException expected) {
            System.out.println("missingResolve=ClassNotFoundException");
        }
    }
}
```

Run:

```sh
javac --release 21 -Xlint:all MethodTypeDescLab.java
java MethodTypeDescLab
```

**Stdout:**

```text
descriptor=(I[Ljava/lang/String;)Ljava/lang/String;
equalParsed=true
display=(int,String[])String
parameters=2
return=Ljava/lang/String;
extended=(IJ[Ljava/lang/String;)Ljava/lang/String;
changedReturn=(I[Ljava/lang/String;)V
resolved=(I[Ljava/lang/String;)Ljava/lang/String;
describedBack=true
invalid=IllegalArgumentException
missingNominal=(Ldemo/missing/Never;)V
missingResolve=ClassNotFoundException
```

### 8.1. Details Easy to Overlook

- `MethodTypeDesc.of` takes the **return type first**, followed by parameter types in order. In a descriptor string, the return type is written **after** the `)`. Do not swap the two conventions.
- `insertParameterTypes(1, CD_long)` inserts `long` before the `String[]` parameter at index 1; the result is `(IJ[Ljava/lang/String;)Ljava/lang/String;`.
- `changed` returns `void` while keeping the parameters; `nominal` is unchanged because descriptors are immutable.
- `displayDescriptor()` is a readable representation, not an input to `MethodTypeDesc.ofDescriptor`.
- `actual.describeConstable().orElseThrow()` returns the nominal descriptor if the method type is describable; in the experiment, all classes are nominal JDK types so the round-trip succeeds.
- `(V)I` is a syntax error (`void` cannot be a parameter), whereas `(Ldemo/missing/Never;)V` is **syntactically valid** but runtime resolution throws `ClassNotFoundException`.

## 9. `MethodHandleDesc`: Describing Handles for Methods, Constructors, and Fields

`MethodHandleDesc` is the nominal descriptor of a `MethodHandle`. Usually you create a `DirectMethodHandleDesc` via the interface's factories:

```java
// Illustrative API; not a complete example.
MethodHandleDesc.ofMethod(kind, owner, methodName, lookupMethodType);
MethodHandleDesc.ofConstructor(owner, constructorParamTypes...);
MethodHandleDesc.ofField(kind, owner, fieldName, fieldType);
```

Here:

- `owner` is the `ClassDesc` of the class/interface owning the member.
- `kind` is `DirectMethodHandleDesc.Kind`: determines whether the operation is static/virtual/special, constructor, or field getter/setter.
- `methodName` is the unqualified method name; for constructors, use `ofConstructor` to avoid manually passing `<init>`.
- `lookupMethodType` is the `MethodTypeDesc` of the **declared method used for lookup**, *without the receiver* for virtual methods.
- `fieldType` is the **ClassDesc of the field**, not a method descriptor.
- `invocationType()` is the `MethodTypeDesc` of the **handle when invoked** — which may differ from the lookup type due to the receiver and constructor return type.
- `resolveConstantDesc(lookup)` uses member resolution, class visibility, and access checks to produce a `MethodHandle`.

### 9.1. Important Kinds

| `DirectMethodHandleDesc.Kind` | Meaning | Lookup/JVM equivalent |
| --- | --- | --- |
| `STATIC` | Class static method | `findStatic` / `invokestatic` |
| `INTERFACE_STATIC` | Interface static method | `findStatic` / `invokestatic` |
| `VIRTUAL` | Instance class method | `findVirtual` / `invokevirtual` |
| `INTERFACE_VIRTUAL` | Instance interface method | `findVirtual` / `invokeinterface` |
| `SPECIAL` | Special invocation | `findSpecial` / `invokespecial` |
| `INTERFACE_SPECIAL` | Special interface invocation | `findSpecial` / `invokespecial` |
| `CONSTRUCTOR` | Constructor | `findConstructor` / `new` + `<init>` |
| `GETTER`, `SETTER` | Instance field read/write | `getfield`, `putfield` |
| `STATIC_GETTER`, `STATIC_SETTER` | Static field read/write | `getstatic`, `putstatic` |

`Kind` must match the owner/method/field category; a descriptor can be syntactically valid yet unable to resolve the member in an actual Lookup context.

### 9.2. Lookup Descriptor Differs from Invocation Type

Consider `Target.decorate(String):String`, which is an instance method:

```text
Owner:           MethodHandleDescLab$Target
Lookup type:     (Ljava/lang/String;)Ljava/lang/String;
Invocation type: (LMethodHandleDescLab$Target;Ljava/lang/String;)Ljava/lang/String;
                 ^ receiver is inserted at the front when invoking the handle
```

The method descriptor of an instance method in a class file does not contain `this`. However, the resolved `MethodHandle` needs to receive the receiver as a leading parameter.

For the constructor `Target(int)`:

```text
Constructor in JVM:      (I)V       // <init> has void return
Constructor handle:      (I)LMethodHandleDescLab$Target;
```

`MethodHandleDesc.ofConstructor(owner, CD_int)` builds the description for constructor invocation; `invocationType()` returns the **new instance** type, not `void`.

For fields:

```text
Instance getter String label: (LTarget;)Ljava/lang/String;
Static getter int shared:    ()I
Instance setter String label: (LTarget;Ljava/lang/String;)V
Static setter int shared:    (I)V
```

`LTarget;` in the field table is shorthand for illustration; the actual JVM descriptor must use the full **internal name** of the declaring class. Do not pass a `MethodTypeDesc` into `ofField` where the factory expects a `ClassDesc`.

## 10. Lab 3 — STATIC, VIRTUAL, CONSTRUCTOR, and FIELD Descriptions

Create file **`MethodHandleDescLab.java`**:

```java
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.DirectMethodHandleDesc;
import java.lang.constant.MethodHandleDesc;
import java.lang.constant.MethodTypeDesc;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;

public class MethodHandleDescLab {
    public static class Target {
        public String label;
        public static int shared = 11;

        public Target(int value) {
            this.label = "v" + value;
        }
        public static int add(int a, int b) {
            return a + b;
        }
        public String decorate(String text) {
            return "[" + text + "]";
        }
    }

    public static void main(String[] args) throws Throwable {
        ClassDesc owner = ClassDesc.of("MethodHandleDescLab$Target");
        DirectMethodHandleDesc staticDesc = MethodHandleDesc.ofMethod(
                DirectMethodHandleDesc.Kind.STATIC, owner, "add",
                MethodTypeDesc.of(ConstantDescs.CD_int,
                        ConstantDescs.CD_int, ConstantDescs.CD_int));
        DirectMethodHandleDesc virtualDesc = MethodHandleDesc.ofMethod(
                DirectMethodHandleDesc.Kind.VIRTUAL, owner, "decorate",
                MethodTypeDesc.of(ConstantDescs.CD_String, ConstantDescs.CD_String));
        DirectMethodHandleDesc constructorDesc =
                MethodHandleDesc.ofConstructor(owner, ConstantDescs.CD_int);
        DirectMethodHandleDesc fieldDesc = MethodHandleDesc.ofField(
                DirectMethodHandleDesc.Kind.GETTER,
                owner, "label", ConstantDescs.CD_String);
        DirectMethodHandleDesc staticFieldDesc = MethodHandleDesc.ofField(
                DirectMethodHandleDesc.Kind.STATIC_GETTER,
                owner, "shared", ConstantDescs.CD_int);

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle staticHandle = staticDesc.resolveConstantDesc(lookup);
        MethodHandle virtualHandle = virtualDesc.resolveConstantDesc(lookup);
        MethodHandle constructorHandle = constructorDesc.resolveConstantDesc(lookup);
        MethodHandle fieldHandle = fieldDesc.resolveConstantDesc(lookup);
        MethodHandle staticFieldHandle = staticFieldDesc.resolveConstantDesc(lookup);

        Target obj = (Target) constructorHandle.invokeExact(8);
        System.out.println("staticKind=" + staticDesc.kind());
        System.out.println("staticType=" + staticDesc.invocationType().descriptorString());
        System.out.println("virtualLookup=" + virtualDesc.lookupDescriptor());
        System.out.println("virtualType=" + virtualDesc.invocationType().descriptorString());
        System.out.println("constructorType=" + constructorDesc.invocationType().descriptorString());
        System.out.println("fieldType=" + fieldDesc.invocationType().descriptorString());
        System.out.println("staticFieldType=" + staticFieldDesc.invocationType().descriptorString());
        System.out.println("add=" + (int) staticHandle.invokeExact(3, 4));
        System.out.println("virtual=" + (String) virtualHandle.invokeExact(obj, "hi"));
        System.out.println("field=" + (String) fieldHandle.invokeExact(obj));
        System.out.println("shared=" + (int) staticFieldHandle.invokeExact());
    }
}
```

Compile/run:

```sh
javac --release 21 -Xlint:all MethodHandleDescLab.java
java MethodHandleDescLab
```

**Stdout:**

```text
staticKind=STATIC
staticType=(II)I
virtualLookup=(Ljava/lang/String;)Ljava/lang/String;
virtualType=(LMethodHandleDescLab$Target;Ljava/lang/String;)Ljava/lang/String;
constructorType=(I)LMethodHandleDescLab$Target;
fieldType=(LMethodHandleDescLab$Target;)Ljava/lang/String;
staticFieldType=()I
add=7
virtual=[hi]
field=v8
shared=11
```

### 10.1. How to Read Each Type

- `STATIC`: `add(int,int)` is `(II)I` for both lookup and invocation; there is no receiver.
- `VIRTUAL`: `lookupDescriptor()` for `decorate(String)` is `(Ljava/lang/String;)Ljava/lang/String;`. `invocationType()` prepends a `Target` before the String argument.
- `CONSTRUCTOR`: `ofConstructor` only takes parameter types; the invocation type returns `Target`.
- `GETTER`: the instance field getter takes receiver `Target` and returns `String`.
- `STATIC_GETTER`: the static field getter takes no receiver and returns `int`.
- The `invokeExact` calls use the exact cast/assigned return type so the call-site signature matches. Resolving the handle **does not execute** the member by itself; the calls at the end of the program perform the behavior.

**Note:** the code is placed in the default package for easy execution. If moved into a real package, the binary name of nested `Target` changes (e.g., `com.acme.MethodHandleDescLab$Target`), so `ClassDesc.of(...)` must be adjusted. Do not hard-code binary names in reusable libraries if you can obtain them from the proper class metadata source.

## 11. `MethodHandleDesc.asType` and Access Permission Lookup

`MethodHandleDesc` has `asType(MethodTypeDesc targetType)`, which creates a **nominal description of the adapted handle** conceptually corresponding to `MethodHandle.asType` at runtime. This does **not** change the `MethodTypeDesc` of the declared method, and does not guarantee that every conversion is valid.

Example:

```text
Actual method:     int twice(int)
Raw handle type:   (I)I
Adapted handle:    (B)J

caller sends byte  -- widen --> int twice(int) -- widen return --> long
```

This is a valid adaptation: input `byte` widens to `int`, and the `int` result widens to `long`. Conversely, an adaptation requiring an invalid conversion may fail at the resolve/adapt step.

### 11.1. Access Check Is a Separate Step

A `MethodHandleDesc` for `private static int Vault.secret()` can be created successfully, because the factory **does not need to check caller permissions**. However, when resolving:

- A `Lookup` **lacking PRIVATE mode** is not allowed to link a private member if access rules are not satisfied.
- A `Lookup` with sufficient nestmate/private privilege can succeed.
- `publicLookup()` is not equivalent to “a Lookup in the same loader without private permission”; in some situations it cannot even see an application class in the unnamed module from a bootstrap-only search context. Therefore, to test **private permission specifically** in the lab, use `dropLookupMode(PRIVATE)` on a lookup from the same class/loader and compare it with the full lookup.

Avoid using `setAccessible(true)` or adding `--add-opens` as a default workaround for missing permissions. A `Lookup` should be granted by the component that owns that capability, not faked via text.

## 12. Lab 4 — Access Denied Then Valid Resolution; asType Adapter

Create file **`AccessAndAdaptLab.java`**:

```java
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.DirectMethodHandleDesc;
import java.lang.constant.MethodHandleDesc;
import java.lang.constant.MethodTypeDesc;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;

public class AccessAndAdaptLab {
    public static class Vault {
        private static int secret() {
            return 42;
        }
        public static int twice(int x) {
            return x * 2;
        }
    }

    public static void main(String[] args) throws Throwable {
        ClassDesc owner = ClassDesc.of("AccessAndAdaptLab$Vault");
        DirectMethodHandleDesc privateMethod = MethodHandleDesc.ofMethod(
                DirectMethodHandleDesc.Kind.STATIC, owner, "secret",
                MethodTypeDesc.of(ConstantDescs.CD_int));
        System.out.println("privateNominal=" +
                privateMethod.invocationType().descriptorString());

        MethodHandles.Lookup restricted =
                MethodHandles.lookup().dropLookupMode(MethodHandles.Lookup.PRIVATE);
        try {
            privateMethod.resolveConstantDesc(restricted);
            System.out.println("restricted=unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("restricted=IllegalAccessException");
        }

        MethodHandle accessible =
                privateMethod.resolveConstantDesc(MethodHandles.lookup());
        System.out.println("nestmate=" + (int) accessible.invokeExact());

        MethodHandleDesc raw = MethodHandleDesc.ofMethod(
                DirectMethodHandleDesc.Kind.STATIC, owner, "twice",
                MethodTypeDesc.of(ConstantDescs.CD_int, ConstantDescs.CD_int));
        MethodTypeDesc desired =
                MethodTypeDesc.of(ConstantDescs.CD_long, ConstantDescs.CD_byte);
        MethodHandleDesc adapted = raw.asType(desired);
        MethodHandle adaptedHandle =
                adapted.resolveConstantDesc(MethodHandles.lookup());

        System.out.println("raw=" + raw.invocationType().descriptorString());
        System.out.println("adapted=" + adapted.invocationType().descriptorString());
        System.out.println("twice=" + (long) adaptedHandle.invokeExact((byte) 7));
        System.out.println("directDescribable=" +
                MethodHandles.lookup().findStatic(
                        Vault.class, "twice",
                        java.lang.invoke.MethodType.methodType(int.class, int.class))
                        .describeConstable().isPresent());
    }
}
```

```sh
javac --release 21 -Xlint:all AccessAndAdaptLab.java
java AccessAndAdaptLab
```

**Stdout:**

```text
privateNominal=()I
restricted=IllegalAccessException
nestmate=42
raw=(I)I
adapted=(B)J
twice=14
directDescribable=true
```

### 12.1. Distinguishing Permissions and Describability

- `privateMethod` still exists as a nominal object even though `restricted` cannot resolve the private member.
- `MethodHandles.lookup()` in `AccessAndAdaptLab` has sufficient nestmate privilege with nested `Vault` to resolve `secret` into a `MethodHandle` returning 42.
- `asType` converts the nominal invocation type from `(I)I` to `(B)J`. After resolution, `invokeExact((byte)7)` takes a `byte` argument and returns a `long` equal to 14.
- `MethodHandle.describeConstable()` can return an `Optional<MethodHandleDesc>` if the method handle has a valid nominal description (for example, a direct static method). Do not assume every transformed/anonymous handle is describable.

**Practical note:** `IllegalAccessException` permission errors differ from missing-class errors (`ClassNotFoundException`) and missing-member errors. Do not use a generic “descriptor invalid” message when the factory already created the descriptor successfully.

## 13. Connection to Dynamic Constants (CONSTANT_Dynamic)

The four types in the title form the foundation for describing constants, but **an actual dynamic constant** needs additional bootstrap metadata. `DynamicConstantDesc<T>` is a subtype of `ConstantDesc` representing a `CONSTANT_Dynamic_info` with:

- **Constant name**: the nominal name of the constant.
- **Constant type**: `ClassDesc` of the result type.
- **Bootstrap method**: a `DirectMethodHandleDesc` pointing to the bootstrap method.
- **Bootstrap arguments**: any other required static constant descriptors, depending on the bootstrap.
- **Resolution context**: `Lookup` and corresponding rules when resolution is requested.

The JVM has `CONSTANT_Dynamic` for loadable dynamic constants (`ldc` on the corresponding entry) and `CONSTANT_InvokeDynamic` for dynamic call sites. They are related via the bootstrap concept, but **are not the same constant pool tag**. `DynamicCallSiteDesc` in `java.lang.constant` serves as the nominal representation for dynamic call sites; it is not a replacement for `DynamicConstantDesc`.

### 13.1. Built-in Bootstrap Methods

`ConstantDescs` provides several nominal descriptors for built-in bootstrap handles, for example:

| ConstantDescs | Corresponding bootstrap | Typical meaning |
| --- | --- | --- |
| `BSM_NULL_CONSTANT` | `ConstantBootstraps.nullConstant` | Dynamic constant evaluating to `null` for a reference type |
| `BSM_PRIMITIVE_CLASS` | `ConstantBootstraps.primitiveClass` | `Class<?>` constant for a primitive |
| `BSM_ENUM_CONSTANT` | `ConstantBootstraps.enumConstant` | Looks up an enum constant by name |
| `BSM_GET_STATIC_FINAL` | `ConstantBootstraps.getStaticFinal` | Reads a valid static final field |
| `BSM_INVOKE` | `ConstantBootstraps.invoke` | Uses a bootstrap invocation to produce a value |
| `BSM_VARHANDLE_FIELD` | `ConstantBootstraps.fieldVarHandle` | Describes a dynamic constant whose value is a VarHandle for an instance field |

The `BSM_*` fields are descriptors for bootstrap methods, **not** computed bootstrap results. Choosing a bootstrap with the wrong signature, insufficient permissions, or invalid static args can cause resolution to fail. Do not let a dynamic constant reference arbitrary handlers supplied by untrusted users without a validation policy.

### 13.2. Creating a Descriptor Does Not Mean Adding CONSTANT_Dynamic to the Class File

The Java code below creates a `DynamicConstantDesc` **on the heap** and uses `resolveConstantDesc` to compute the value. It does not compile a new `ldc CONSTANT_Dynamic` into the program's own class file. To emit bytecode containing `CONSTANT_Dynamic_info`, you need an appropriate class-file generator and bootstrap resolution per JVMS `4.4.10`, `5.4.3.6`.

This is the difference between the **nominal model of the constant pool** and an **encoded class file**.

## 14. Lab 5 — DynamicConstantDesc and Native ConstantDesc

Create file **`DynamicConstantLab.java`**:

```java
import java.lang.constant.ConstantDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.DynamicConstantDesc;
import java.lang.invoke.MethodHandles;

public class DynamicConstantLab {
    public static void main(String[] args) throws ReflectiveOperationException {
        ConstantDesc text = "hello";
        ConstantDesc number = Integer.valueOf(7);
        DynamicConstantDesc<String> nominalNull = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_NULL_CONSTANT,
                "meaning",
                ConstantDescs.CD_String);

        System.out.println("stringSelf=" + text.resolveConstantDesc(MethodHandles.lookup()));
        System.out.println("integerSelf=" + number.resolveConstantDesc(MethodHandles.lookup()));
        System.out.println("dynamicSubtype=" + (nominalNull instanceof DynamicConstantDesc));
        System.out.println("dynamicName=" + nominalNull.constantName());
        System.out.println("dynamicType=" + nominalNull.constantType().descriptorString());
        System.out.println("dynamicResolvesNull=" +
                (nominalNull.resolveConstantDesc(MethodHandles.lookup()) == null));
        System.out.println("dynamicBootstrap=" +
                nominalNull.bootstrapMethod().methodName());
    }
}
```

```sh
javac --release 21 -Xlint:all DynamicConstantLab.java
java DynamicConstantLab
```

**Stdout:**

```text
stringSelf=hello
integerSelf=7
dynamicSubtype=true
dynamicName=meaning
dynamicType=Ljava/lang/String;
dynamicResolvesNull=true
dynamicBootstrap=nullConstant
```

### 14.1. Explanation

- String and Integer implement `ConstantDesc` for themselves, so resolution returns their respective values.
- `DynamicConstantDesc.ofNamed(BSM_NULL_CONSTANT,"meaning",CD_String)` creates a nominal description of a `String` constant whose value is `null`.
- `nominalNull.constantType()` is `CD_String`, so the descriptor is `Ljava/lang/String;`.
- `nominalNull.resolveConstantDesc(lookup)` invokes the bootstrap path per the descriptor contract and receives `null`; in this case `== null` is true.
- `bootstrapMethod().methodName()` returns `nullConstant`, showing which bootstrap the descriptor points to. The **constant name** `meaning` is distinct from the **bootstrap method name** `nullConstant`.
- Both `ConstantDesc` and `DynamicConstantDesc` are just Java objects created at runtime, not modifying the class file when running the lab.

**Note on null:** `null` is not a `ConstantDesc` instance; here a **descriptor object** exists and it *resolves to* the null value. Confusing these two will lead to logic bugs in code using generic `ConstantDesc`.

## 15. `Constable` and Reverse Description from Runtime Values

`Constable` is the interface for objects that **can describe themselves as a nominal constant descriptor**. Important APIs:

| Runtime object | API | Optional type returned |
| --- | --- | --- |
| `String` | `describeConstable()` | `Optional<String>` |
| `Integer` | `describeConstable()` | `Optional<Integer>` |
| `Class<?>` | `Class.describeConstable()` | `Optional<ClassDesc>` |
| `MethodType` | `MethodType.describeConstable()` | `Optional<MethodTypeDesc>` |
| `MethodHandle` | `MethodHandle.describeConstable()` | `Optional<MethodHandleDesc>` |

`describeConstable()` **is not guaranteed to always be present**. For example, some classes cannot be described by a stable nominal name (hidden classes); some method handles created via combinators/adapters may not be representable by a valid descriptor. Handle `Optional.empty()` as a meaningful result, rather than calling `orElseThrow()` indiscriminately on uncontrolled data.

### 15.1. When to Use Forward vs. Reverse Direction?

**Forward direction — nominal → runtime:**

```java
// Illustrative snippet in a scope with lookup permission.
ClassDesc desc = ClassDesc.of("java.lang.String");
Class<?> runtime = desc.resolveConstantDesc(MethodHandles.lookup());
```

Suitable when receiving class-file metadata or symbolic configuration, and then wanting to link in the current environment.

**Reverse direction — runtime → nominal:**

```java
// Illustrative snippet with a describable Class<?>.
java.util.Optional<ClassDesc> name = String.class.describeConstable();
```

Suitable when wanting to record a nominal description for tooling. Do not assume that a round-trip preserves **class loader identity**; nominal descriptors do not store the defining loader and require a proper Lookup when re-resolving.

### 15.2. Class Name and Descriptor Equality Are Not Enough to Replace Access Policy

A `ClassDesc` can be equal between two plugins while the runtime `Class<?>` objects differ. A `MethodHandleDesc` with the same owner/name/descriptor can also resolve to a different member or fail to resolve when changing Lookup. Therefore, `equals` on nominal descriptors is for **comparing description structure** — not for verifying granted capabilities.

## 16. Resolution Pipeline, Errors, and Safety Checks

A standard pipeline when using descriptors at runtime:

```text
[1] Receive metadata from class file/trusted config source
     |
[2] Create ClassDesc / MethodTypeDesc / MethodHandleDesc
     |   validate syntax and descriptor kind
     v
[3] Determine valid class loader, module layer, Lookup context
     |
[4] resolveConstantDesc(lookup)
     |   resolve class + access + member lookup/linking + bootstrap if any
     v
[5] Check runtime MethodType / MethodHandle type and capability
     |
[6] Invoke with exact signature or pass value to consumer
     |
[7] Record errors by phase, manage cache/lifecycle
```

**Error categories:**

| Symptom | Phase and common cause | How to handle |
| --- | --- | --- |
| `IllegalArgumentException` in `ClassDesc.ofDescriptor` | Field descriptor grammar error, e.g. object name missing `;` | Follow JVMS `4.3.2`; do not pass a method descriptor. |
| `IllegalArgumentException` in `MethodTypeDesc.ofDescriptor` | Method descriptor grammar error, e.g. `(V)I` | `V` is only valid as return; check parentheses, type order. |
| `ClassNotFoundException` when resolving `ClassDesc` | Valid name but lookup loader cannot find the class | Check binary name, classpath/module path, and lookup class loader. |
| `IllegalAccessException` when resolving handle | Lookup lacks permission to access class/member/module | Use a legitimate Lookup from the right owner/module, do not arbitrarily open access. |
| `NoSuchMethodException` / `NoSuchFieldException` | Member name/kind/type does not match runtime owner | Compare bytecode descriptor with `javap -s` and check erased types. |
| `LinkageError` | Resolution/linkage cannot complete | Check dependencies, class version, loaders, module graph. |
| `WrongMethodTypeException` on invoke | Call-site signature does not match `MethodHandle.type()` | Print `type()`, check receiver/return cast, adapt intentionally. |
| `ClassCastException` | Caller passes an object reference of wrong runtime type | Check class identity, loader, type conversions. |
| `Optional.empty()` from `describeConstable()` | Runtime entity has no valid nominal description | Design a fallback; do not assert every object is serializable. |
| Dynamic constant bootstrap failure | Bootstrap/name/type/static arguments mismatch | Check bootstrap signature, lookup permissions, and error cause. |

**Note on resolve errors:** The `ConstantDesc.resolveConstantDesc` API declares `ReflectiveOperationException`, but `LinkageError` or runtime exceptions can still be thrown depending on context. Do not catch `Exception` and discard the cause, or turn an access error into a syntax error.

### 16.1. The Class Loader Is a Mandatory Part of the Context

A nominal descriptor only holds the class name. If a plugin system has multiple class loaders:

- Do not use `ClassDesc.of("com.acme.Message")` and resolve it with the core Lookup when you actually need the plugin's class.
- Do not write a runtime cache key that is only the string `"Lcom/acme/Message;"`.
- Do not share a `MethodHandle` containing a runtime `Class<?>` from plugin A to invoke an instance defined by loader B just because the class name is the same.
- Decide on a clear shared API/SPI loader or lookup policy, then use `resolveConstantDesc` according to that rule.

**Resolution can be an observable action**, triggering class loading and sometimes linking/initialization of related members/bootstraps. Do not run resolution on a list of member/owner names supplied by untrusted users without filtering and resource limits.

## 17. From Constant Descriptors to Class Files

Although the labs use Java reflection, this API layer is especially useful when building bytecode reading/writing tools.

| Constant-pool structure | Information represented | Corresponding Java nominal API |
| --- | --- | --- |
| `CONSTANT_Class_info` | Class/interface/array symbolic type | `ClassDesc` |
| `CONSTANT_MethodType_info` | Method descriptor string | `MethodTypeDesc` |
| `CONSTANT_MethodHandle_info` | Reference kind and member reference | `DirectMethodHandleDesc` |
| `CONSTANT_Dynamic_info` | Bootstrap, name, return type, static args | `DynamicConstantDesc` |
| `CONSTANT_InvokeDynamic_info` | Bootstrap/linkage of a dynamic call site | `DynamicCallSiteDesc` |
| `CONSTANT_String_info` | String literal | `String` (native `ConstantDesc`) |
| Integer/Long/Float/Double entries | Numeric constants | Corresponding boxed numeric `ConstantDesc` |

**Do not interpret the table as a one-to-one mapping between class-file tags and runtime Java objects**. A class file also has indices, name-and-type structures, and the bootstrap-methods table; a bytecode writer must map those links properly. `ConstantDesc` is an interface for a symbolic recipe, not a class-file parser.

### 17.1. Inspecting Compiled Bytecode

After building `MethodHandleDescLab.java`:

```sh
javap -v -p MethodHandleDescLab
javap -s -p MethodHandleDescLab
```

- `-v` displays the constant pool and some class file metadata.
- `-s` displays method/field descriptors per the JVM; in Lab 3, `add` has descriptor `(II)I`, `decorate` has `(Ljava/lang/String;)Ljava/lang/String;`.
- Nominal descriptors that the program **creates via factories at runtime** do not necessarily appear directly as corresponding `CONSTANT_MethodHandle_info` entries in the program's own class file.
- Do not claim the Java compiler automatically emits `CONSTANT_Dynamic` just because the code has `DynamicConstantDesc.ofNamed(...)`. That is a **factory call**, not a compiler directive to emit a dynamic constant pool entry.

### 17.2. Method Types Not Representable at Runtime

`MethodTypeDesc` can hold a structurally valid method descriptor with **too many parameter slots** for `MethodType`, whereas an actual JVM method is constrained by slot rules. If writing a bytecode emitter, you must check **JVM constraints** before serializing into a class file and separate parser errors from runtime errors. Avoid assuming “successfully creating a nominal object” is a complete class-file validator.

## 18. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| “`ClassDesc.of` creates a runtime class” | The factory only creates a symbolic description; `resolveConstantDesc` attempts resolution. |
| “`ClassDesc` is a miniature `Class<?>`” | One holds a nominal description, the other holds a loader-bound runtime identity. |
| “`MethodTypeDesc` preserves `List<String>`” | Method type descriptors only hold erased JVM types; generic signatures are separate metadata. |
| “`MethodHandleDesc.ofMethod` proves the method exists” | The factory can succeed even if the owner/member does not exist. |
| “`ofMethod(VIRTUAL)` must take a type with the receiver” | The lookup method type does not include the receiver; `invocationType()` includes the receiver. |
| “Constructor description returns `void`” | JVM `<init>` returns void, but a constructor **handle invocation** returns the new instance. |
| “Field uses `MethodTypeDesc` as the factory input type” | `ofField` takes `ClassDesc fieldType`; invocation type is inferred from kind. |
| “`asType` is an immediate value cast” | It creates an adapted nominal handle; resolving and invoking performs the runtime conversion. |
| “Having the same descriptor means the same runtime method handle” | Lookup class/loader/module/permissions and owner identity may differ. |
| “`publicLookup()` is always the right lookup for any application class” | Public lookup's class search context is restricted, sometimes failing before access checks. |
| “`describeConstable()` always has a value” | Returns Optional, which may be empty for runtime values without a nominal representation. |
| “`DynamicConstantDesc` is already a bootstrapped value” | It is a recipe; `resolveConstantDesc` requests the bootstrap. |
| “Calling the factory automatically inserts `CONSTANT_Dynamic` into the class file” | Class-file generation is a separate task. |
| “Descriptor `equals` verifies safety” | Equals only compares symbolic descriptions, not authorization. |
| “Every `resolveConstantDesc` caches the same instance” | The contract does not guarantee caching per descriptor object. |

**Design rule of thumb:** choose between nominal and runtime by phase. Tooling can hold nominal descriptors, while execution needs controlled resolution. Do not write your own parser by splitting on dots/commas when the JDK already provides factories for the grammar.

## 19. Exercises and Guided Answers

**Exercise 1 — Creating ClassDesc.** Write nominal descriptions for `int`, `String[]`, `java.util.Map.Entry`, `long[][]`. Descriptor answers respectively: `I`, `[Ljava/lang/String;`, `Ljava/util/Map$Entry;`, `[[J`. Explain why nested classes use `$` instead of converting dots in the source class name into the internal name.

**Exercise 2 — Distinguishing nominal and runtime.** Use `ClassDesc.of("com.example.NotThere")` then `descriptorString()` before `resolveConstantDesc`. Why does the first step succeed while the second fails? Write error classification without misusing `IllegalArgumentException`.

**Exercise 3 — MethodTypeDesc factory.** Build a description for `String combine(int, String[])` using `MethodTypeDesc.of`, predict `(I[Ljava/lang/String;)Ljava/lang/String;`. Then insert a `long` at index 1 and change the return type to `void`. Verify via `descriptorString()`.

**Exercise 4 — Grammar.** Distinguish `(V)I`, `(I)V`, and `[I`. Only `(I)V` is a valid method descriptor; `[I` is the field descriptor for `int[]`, without method parentheses. `(V)I` is invalid because a parameter cannot be `void`.

**Exercise 5 — Virtual receiver.** From Lab 3, compute `virtualDesc.lookupDescriptor()` and `virtualDesc.invocationType()`. Why does `lookupDescriptor` only have a `String` parameter while `invokeExact` must pass `Target`?

**Exercise 6 — Constructor.** Add `Target(String,int)`, build `MethodHandleDesc.ofConstructor(owner,CD_String,CD_int)`. Explain why `<init>` in the class file has return `V` while `invocationType` returns `Target`.

**Exercise 7 — Field.** Add `public long count` in `Target`. Predict the invocation type for `Kind.GETTER` and `Kind.SETTER`. Answers: `(LMethodHandleDescLab$Target;)J` and `(LMethodHandleDescLab$Target;J)V`.

**Exercise 8 — Access modes.** In Lab 4, compare `restricted` with `MethodHandles.lookup()`, then change `Vault.secret` from private to public. Distinguish the effect of the access modifier from the class loader. Only test on classes/Lookups that you own.

**Exercise 9 — asType.** Replace adapter `(B)J` with `(S)J` for a `short` input. Explain widening `short → int` and `int → long`. Do not assume `String → int` can be converted.

**Exercise 10 — Dynamic constant.** Use `DynamicConstantDesc.ofNamed(BSM_NULL_CONSTANT,"empty",CD_String)`. Read `constantName()`, `constantType()`, and `bootstrapMethod()`. Why is the descriptor object **non-null** even though resolution returns `null`?

**Exercise 11 — Loader identity.** Imagine two plugin modules with the same binary name `plugin.api.Task` but different class loaders. Given a `ClassDesc.of("plugin.api.Task")`, predict `equals` of the two descriptions and distinguish `Class<?>` after resolution with Lookup A/B. State the proper way to cache.

**Exercise 12 — Constable Optional.** From runtime objects `String.class`, `MethodType.methodType(int.class,int.class)`, and `MethodHandles.lookup().findStatic(...)`, call `describeConstable()`. Check Optional before using; why can't you assume Optional is always non-empty in generic applications?

**Exercise 13 — Bytecode verification.** Use `javap -v` to inspect the class file of a lab. Distinguish an actual constant pool entry in the file from a `ConstantDesc` created by Java code on the heap. Do not assume every dynamic description becomes a `CONSTANT_Dynamic`.

### 19.1. Completion Checklist

- [ ] Can explain “recipe, not runtime value”.
- [ ] Can create/read `ClassDesc` for primitive, object, array, and nested classes with correct grammar.
- [ ] Can create/read `MethodTypeDesc` with correct return/parameter order and distinguish readable display.
- [ ] Can distinguish `MethodHandleDesc.lookupDescriptor` from `invocationType` for STATIC/VIRTUAL/CONSTRUCTOR/FIELD.
- [ ] Can resolve with a legitimate `Lookup`; invoke `MethodHandle.invokeExact` with a matching signature.
- [ ] Can identify grammar errors, missing class, access denied, and runtime conversion as distinct phases.
- [ ] Can distinguish `DynamicConstantDesc` and constant pool `CONSTANT_Dynamic` from `DynamicCallSiteDesc`.
- [ ] Do not hard-code loader identity, do not rely on `==` for descriptor objects, and do not assume every `Constable` has a nominal description.
- [ ] Have run and understood the stdout of all five labs.

## 20. Java SE 21 and JVM Reference Documentation

- [Java SE 21 — java.lang.constant package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/package-summary.html): concepts of nominal descriptors, constant pool, and resolution.
- [Java SE 21 — ConstantDesc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/ConstantDesc.html): sealed interface, `resolveConstantDesc`, no caching by contract.
- [Java SE 21 — ClassDesc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/ClassDesc.html): name factories, arrays, type descriptors, display, and resolution.
- [Java SE 21 — MethodTypeDesc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/MethodTypeDesc.html): method description, editing, and runtime resolution.
- [Java SE 21 — MethodHandleDesc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/MethodHandleDesc.html): static/virtual/field/constructor factories, adapter, invocationType.
- [Java SE 21 — DirectMethodHandleDesc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/DirectMethodHandleDesc.html) and [Kind](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/DirectMethodHandleDesc.Kind.html): member kind, owner, method name, and lookup descriptor.
- [Java SE 21 — ConstantDescs](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/ConstantDescs.html): predefined `CD_*` and `BSM_*`.
- [Java SE 21 — DynamicConstantDesc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/DynamicConstantDesc.html): bootstrap name/type/args.
- [Java SE 21 — Constable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/Constable.html): `describeConstable` and Optional.
- [JVMS 21 `4.3 — Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3): field/method grammar.
- [JVMS 21 `4.4 — Constant Pool](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.4): constant pool tags and symbolic references.
- [JVMS 21 `5.4.3 — Resolution](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3): from symbolic information to runtime entities.
- [Java SE 21 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): resolution and access permissions.
- [JDK 21 — javap](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): inspecting descriptors in class files.

**Key takeaway:** `ClassDesc` describes **a class by name**, `MethodTypeDesc` describes **a method signature by name**, `MethodHandleDesc` describes **a member-linking action by owner/name/kind/type**, and `ConstantDesc` is the common contract to **resolve them under a specific Lookup**. When a constant has a bootstrap, `DynamicConstantDesc` supplies that part of the recipe. Keep symbolic metadata separate from runtime authority and only resolve when a valid loader/module/Lookup is available.
