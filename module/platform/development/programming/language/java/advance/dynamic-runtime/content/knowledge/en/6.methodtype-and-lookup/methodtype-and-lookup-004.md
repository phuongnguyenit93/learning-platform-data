# 6.4. Reading and building JVM method descriptors with class loader context

> **Context:** This lesson belongs to group **6. MethodType and Lookup** of the **Java Advance – dynamic-runtime** module. The goal is to accurately interpret *JVM method descriptors*, build and parse descriptors using the standard Java 21 API, and determine the role of the **class loader** in turning type names into actual `Class<?>` objects. The labs use public JDK APIs and run standalone on the classpath.

## 1. Objectives and prerequisites

After studying this lesson, you should be able to:

1. Analyze the `(parameters)return` form of a JVM method descriptor with primitive, object, and array types.
2. Distinguish between JVM descriptor syntax, Java source declarations, generic signatures, `MethodType`, and the invocation type of a `MethodHandle`.
3. Build a `MethodType` using `methodType(...)`, export its descriptor using `toMethodDescriptorString()`, and parse it back using `fromMethodDescriptorString(descriptor, loader)`.
4. Explain why a class loader must be chosen when a descriptor contains `L...;` and why **two equal descriptor strings** can still produce **unequal MethodType instances**.
5. Use `MethodHandles.Lookup` properly for static, virtual, and constructor lookups; understand the receiver position and return type.
6. Read `javap -s` output and inspect syntax/resolution/lookup/invocation errors by phase.

Prerequisites: classes/interfaces, static and instance methods, arrays, basic generics, `Class<?>`, `ClassLoader`, `java.lang.invoke`, and the terminal. No external frameworks or libraries are needed; all source code can be verified with `javac --release 21`.

## 2. How to read a JVM method descriptor

At the class file level, a **method descriptor** only encodes the **order of declared parameter types** and the **return type** of a method. The syntax according to JVMS `4.3.3:

```text
MethodDescriptor    := "(" { ParameterDescriptor } ")" ReturnDescriptor
ParameterDescriptor := FieldType
ReturnDescriptor    := FieldType | "V"
FieldType           := BaseType | ObjectType | ArrayType
BaseType            := B | C | D | F | I | J | S | Z
ObjectType          := "L" InternalClassName ";"
ArrayType           := "[" FieldType
```

There are no commas and no spaces between parameter descriptors. The `)` character marks the end of the parameters; the remainder is a single return descriptor.

### 2.1. Primitive type codes

| Descriptor | Java Type | Notes |
| --- | --- | --- |
| `B` | `byte` | primitive |
| `C` | `char` | primitive |
| `D` | `double` | occupies two parameter length units |
| `F` | `float` | primitive |
| `I` | `int` | primitive |
| `J` | `long` | occupies two parameter length units |
| `S` | `short` | primitive |
| `Z` | `boolean` | primitive |
| `V` | `void` | **valid only as a return type** |

**Specifically:** `J` is `long`, whereas `L...;` is used for reference classes/interfaces; `V` is not a valid parameter type. A descriptor such as `(V)I` will be rejected by the parser.

### 2.2. Reference classes and binary/internal names

The type `java.lang.String` becomes `Ljava/lang/String;`. The `L` starts the object type, `;` ends it, and `/` is used in the *internal name* instead of dots separating packages. For nested classes:

```text
Outer.Inner        → LOuter$Inner;
com.acme.Outer.Inner → Lcom/acme/Outer$Inner;
```

This is the rule for the **binary name** of nested classes; do not replace `$` with `/`. `java.lang.String` uses dots in Java code, but `Ljava.lang.String;` must not be used in a JVM descriptor.

### 2.3. Array types

Each `[` adds one array dimension; the trailing part is the component descriptor:

| Java Type | Descriptor |
| --- | --- |
| `int[]` | `[I` |
| `double[][]` | `[[D` |
| `String[]` | `[Ljava/lang/String;` |
| `String[][]` | `[[Ljava/lang/String;` |
| `Object[][][]` | `[[[Ljava/lang/Object;` |

An array is a reference type even when its component is primitive. `double[]` counts as **one parameter unit**; primitive `double` counts as **two**.

### 2.4. Translating a string into a Java method

Suppose the source has:

```java
// Illustrative method inside a class.
static java.util.List<String> transform(String[] words, int count) {
    return java.util.Arrays.asList(words)
            .subList(0, Math.min(count, words.length));
}
```

Its method descriptor is:

```text
([Ljava/lang/String;I)Ljava/util/List;
```

How to read it: `(` opens parameters, `[Ljava/lang/String;` is `String[]`, `I` is `int`, `)` closes parameters, `Ljava/util/List;` is the return type `List` after erasure.

Information **not included in the descriptor**: method name, parameter names, owner class, `static` modifier, generic argument `String` of `List<String>`, `throws`, and annotations. The JVM has separate metadata for those details; do not put them into the descriptor string.

## 3. Conversion table and limit rules

| Java method declaration | JVM method descriptor |
| --- | --- |
| `void ping()` | `()V` |
| `int add(int a, int b)` | `(II)I` |
| `boolean valid(byte[] input)` | `([B)Z` |
| `String join(String[] parts, int limit)` | `([Ljava/lang/String;I)Ljava/lang/String;` |
| `long[] convert(int[][] values)` | `([[I)[J` |
| `Object m(int i, double d, Thread t)` | `(IDLjava/lang/Thread;)Ljava/lang/Object;` |
| `List<String> transform(String[] words, int count)` | `([Ljava/lang/String;I)Ljava/util/List;` |

According to the JVMS, a descriptor must fit within a total limit of **255 parameter length units**; primitive `long`/`double` occupy two units, while other types occupy one. In the case of instance or interface invocation, one additional unit is counted for the `this` receiver. Therefore, 255 cannot be treated as a fixed parameter count for all methods.

An instance method's descriptor **does not record the `this` receiver** inside the parentheses. `static int add(int,int)` and `int add(int,int)` share the same descriptor `(II)I`; when actually invoking an instance method, the JVM passes the receiver according to the corresponding invocation mechanism. However, a `MethodHandle` for a virtual method represents the receiver in the **handle signature** — a difference that will be seen in Lab 3.

## 4. `MethodType` and ways to create descriptors

`java.lang.invoke.MethodType` describes the return type and parameter type list using **runtime `Class<?>` objects**. It is immutable; any signature modification creates a new `MethodType`. `MethodType.equals` compares the exact parameter and return types, not just the printed string.

| Java 21 API | Purpose |
| --- | --- |
| `MethodType.methodType(returnClass, parameters...)` | Creates from existing `Class<?>` objects without parsing class names. |
| `MethodType.fromMethodDescriptorString(descriptor, loader)` | Parses a JVM descriptor string and resolves class names via the specified loader. |
| `type.toMethodDescriptorString()` | Outputs the JVM method descriptor. |
| `type.descriptorString()` | Equivalent to `toMethodDescriptorString()`. |
| `type.parameterCount()`, `parameterType(i)`, `parameterArray()` | Inspects the list of runtime parameter types. |
| `type.returnType()` | Inspects the runtime return type. |
| `type.changeReturnType(...)`, `insertParameterTypes(...)` | Builds a new type from an existing one. |
| `type.toString()` | Human-readable display form, **not a JVM descriptor**. |
| `MethodTypeDesc.ofDescriptor(descriptor)` | Creates a nominal descriptor in `java.lang.constant` without resolving runtime classes. |

`void.class` may only be used as the **return class**, never as a parameter in `MethodType`. The call `MethodType.methodType(int.class, int.class, int.class)` describes `(II)I`. Its `toString()` may display `(int,int)int`, which is not a string to pass into `fromMethodDescriptorString`.

**Practical choice:** If you already hold the exact `Class<?>` objects of a plugin, you can build `MethodType` directly; when receiving a descriptor string from a class file or configuration, you must have an appropriate class loader to resolve it. If you only need syntax analysis, consider `MethodTypeDesc` before loading classes.

## 5. Lab 1 — round-trip, reflection, and parse errors

Create the file **`DescriptorRoundTripLab.java`**:

```java
import java.lang.constant.MethodTypeDesc;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

public class DescriptorRoundTripLab {
    public static List<String> transform(String[] words, int count) {
        return Arrays.asList(words).subList(0, Math.min(count, words.length));
    }

    public static void main(String[] args) throws NoSuchMethodException {
        MethodType type = MethodType.methodType(List.class, String[].class, int.class);
        String descriptor = type.toMethodDescriptorString();
        MethodType parsed = MethodType.fromMethodDescriptorString(
                descriptor, DescriptorRoundTripLab.class.getClassLoader());

        Method reflected = DescriptorRoundTripLab.class.getDeclaredMethod(
                "transform", String[].class, int.class);
        MethodType fromReflection = MethodType.methodType(
                reflected.getReturnType(), reflected.getParameterTypes());
        MethodTypeDesc nominal = MethodTypeDesc.ofDescriptor(descriptor);

        System.out.println("descriptor=" + descriptor);
        System.out.println("roundTrip=" + type.equals(parsed));
        System.out.println("fromReflection=" + fromReflection.toMethodDescriptorString());
        System.out.println("parameterCount=" + parsed.parameterCount());
        System.out.println("firstParameter=" + parsed.parameterType(0).getTypeName());
        System.out.println("returnType=" + parsed.returnType().getTypeName());
        System.out.println("nominal=" + nominal.descriptorString());

        try {
            MethodType.fromMethodDescriptorString(
                    "(V)I", DescriptorRoundTripLab.class.getClassLoader());
            System.out.println("invalid=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid=IllegalArgumentException");
        }

        MethodTypeDesc unresolved = MethodTypeDesc.ofDescriptor("(Lsample/missing/Absent;)V");
        System.out.println("nominalUnresolved=" + unresolved.descriptorString());
        try {
            MethodType.fromMethodDescriptorString(
                    unresolved.descriptorString(),
                    DescriptorRoundTripLab.class.getClassLoader());
            System.out.println("missing=unexpected");
        } catch (TypeNotPresentException expected) {
            System.out.println("missing=TypeNotPresentException");
        }
    }
}
```

Compile and run in the directory containing the file using a Java 21-compatible JDK:

```sh
javac --release 21 -Xlint:all DescriptorRoundTripLab.java
java DescriptorRoundTripLab
```

**Stdout:**

```text
descriptor=([Ljava/lang/String;I)Ljava/util/List;
roundTrip=true
fromReflection=([Ljava/lang/String;I)Ljava/util/List;
parameterCount=2
firstParameter=java.lang.String[]
returnType=java.util.List
nominal=([Ljava/lang/String;I)Ljava/util/List;
invalid=IllegalArgumentException
nominalUnresolved=(Lsample/missing/Absent;)V
missing=TypeNotPresentException
```

### 5.1. Detailed explanation

- `methodType(List.class, String[].class, int.class)` takes the known return type and parameters directly without manually assembling `[` and `L...;` markers.
- `toMethodDescriptorString()` produces a string containing array, primitive, and reference types; `fromMethodDescriptorString` uses the class loader to reconstruct the `Class<?>` objects for `List` and `String[]`. Since both are standard JDK types, the two `MethodType` instances are equal.
- `getDeclaredMethod` finds the method named `transform` with the erased parameter types; Reflection's `getReturnType()` returns `List.class` rather than an independent runtime `List<String>` type.
- `MethodTypeDesc.ofDescriptor` creates a **nominal descriptor** that can represent a nonexistent class name, because it does not yet require resolving that name into a `Class<?>`.
- `(V)I` is grammatically invalid because `void` cannot be a parameter, resulting in `IllegalArgumentException`.
- `(Lsample/missing/Absent;)V` is grammatically valid, but the loader cannot find the class: `TypeNotPresentException`.

At the system level, these are three distinct phases: **string validation**, **type resolution**, and then **specific member lookup** (if needed). Success in an earlier phase does not guarantee the next phase.

### 5.2. Using `javap` as a verification reference

```sh
javap -s -p DescriptorRoundTripLab
```

The output includes the method:

```text
public static java.util.List<java.lang.String> transform(java.lang.String[], int);
  descriptor: ([Ljava/lang/String;I)Ljava/util/List;
```

The command also prints the constructor, `main`, and other members; the two lines above are the relevant portion, not the entire output. `javap -s` extracts information from compiled bytecode, helping confirm the difference between a generic source declaration and a JVM method descriptor.

## 6. The `ClassLoader` parameter in `fromMethodDescriptorString`

When encountering `Lcom/acme/PluginMessage;`, the parser needs to convert the internal name into a **runtime class**. The Java 21 Javadoc specifies that `fromMethodDescriptorString(descriptor, loader)` resolves all reference class/interface names using the passed loader; if `loader` is `null`, the API uses the **system class loader**. Do not mistake `null` for "bootstrap loader only".

### 6.1. What the loader changes

1. Primitives `I`, `D`, `J`, `V` do not require resolving application classes.
2. For JDK classes like `java.lang.String`, the application loader typically delegates to the platform loader to obtain the same class.
3. For plugin classes, different loaders may see different sets of classes, causing `TypeNotPresentException` if a class cannot be found.
4. A class with the same **binary name** can be defined by two different **defining loaders**, becoming two distinct runtime types.
5. A descriptor does not record the loader or module layer. Therefore, **the string content alone does not uniquely identify a runtime type**.
6. Building a `MethodType` from a descriptor may trigger class loading, but **does not require class initialization** such as invoking a constructor or executing a static initializer; it does not turn the string into a method invocation by itself.
7. The parser does not check member access permissions, method name, or static/virtual/constructor kind on behalf of `Lookup`.

### 6.2. Defining loader and initiating loader

A loader asked to `loadClass` may **delegate to its parent** and return a class defined by the parent. It is the **lookup/initiating loader** context, whereas the *defining loader* is what participates in type identity for the same binary name. Two different loaders **do not automatically** create two different `Class<?>` objects if both delegate to the same class. The lab below intentionally uses a loader that creates its own definition of a single nested class to observe the difference clearly.

### 6.3. Why doesn't `MethodType.equals` compare descriptor text only?

`MethodType` holds each actual `Class<?>`, while a descriptor holds the *names* of the types. When two loaders each define `example.Message`:

```text
Descriptor text: (Lexample/Message;)V
                |                     |
          Loader A resolve       Loader B resolve
                |                     |
      Class(example.Message)  Class(example.Message)
         defined by A           defined by B
                \\                  /
           same descriptor string
              different Class<?> identities
                    |
            MethodType.equals == false
```

If a plugin system uses the descriptor string as a cache key across loaders without loader context, it may return the wrong `MethodType`/`MethodHandle` from another plugin. For a shared API or SPI, place the contract in a common loader when objects need to be exchanged across plugins; ensure caches are partitioned/invalidated according to loader lifecycle.

## 7. Lab 2 — same descriptor but different class loaders

Create the file **`LoaderContextLab.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodType;

public class LoaderContextLab {
    public static final class Payload {}

    private static final class CopyingLoader extends ClassLoader {
        private final String targetName;

        CopyingLoader(ClassLoader parent, String targetName) {
            super(parent);
            this.targetName = targetName;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> loaded = findLoadedClass(name);
                if (loaded == null && name.equals(targetName)) {
                    String resource = name.replace('.', '/') + ".class";
                    try (InputStream in = getParent().getResourceAsStream(resource)) {
                        if (in == null) throw new ClassNotFoundException(name);
                        byte[] bytes = in.readAllBytes();
                        loaded = defineClass(name, bytes, 0, bytes.length);
                    } catch (IOException e) {
                        throw new ClassNotFoundException(name, e);
                    }
                }
                if (loaded == null) loaded = super.loadClass(name, false);
                if (resolve) resolveClass(loaded);
                return loaded;
            }
        }
    }

    public static void main(String[] args) {
        String binaryName = Payload.class.getName();
        String descriptor = "(L" + binaryName.replace('.', '/') + ";)V";
        ClassLoader application = LoaderContextLab.class.getClassLoader();
        ClassLoader isolated = new CopyingLoader(application, binaryName);

        MethodType first = MethodType.fromMethodDescriptorString(descriptor, application);
        MethodType second = MethodType.fromMethodDescriptorString(descriptor, isolated);

        System.out.println("descriptor=" + descriptor);
        System.out.println("sameText=" +
                first.toMethodDescriptorString().equals(second.toMethodDescriptorString()));
        System.out.println("sameClass=" +
                (first.parameterType(0) == second.parameterType(0)));
        System.out.println("sameMethodType=" + first.equals(second));
        System.out.println("childDefined=" +
                (second.parameterType(0).getClassLoader() == isolated));
    }
}
```

```sh
javac --release 21 -Xlint:all LoaderContextLab.java
java LoaderContextLab
```

**Stdout when run on the default classpath:**

```text
descriptor=(LLoaderContextLab$Payload;)V
sameText=true
sameClass=false
sameMethodType=false
childDefined=true
```

### 7.1. Proving each value

- `Payload.class.getName()` produces the binary name `LoaderContextLab$Payload` (in the default package); `replace('.', '/')` converts package dots into internal name form if present.
- With the application loader, the descriptor is parsed into a `MethodType` whose `Payload` parameter is defined by the application loader.
- The experimental `CopyingLoader` handles loading only `targetName` itself: reading bytes from the resource and calling `defineClass`. All other classes still follow parent delegation via `super.loadClass`.
- Because the two `Class<?>` objects are defined by different loaders, `first.parameterType(0) == second.parameterType(0)` evaluates to `false`; consequently, the two `MethodType` instances are also unequal.
- Both parameter classes still have the same binary name, so `toMethodDescriptorString()` produces the **exact same text**; that is why `sameText=true`.
- `childDefined=true` confirms that the isolated loader actually owns the second class.

**Lab scope:** this is a minimal loader to illustrate class identity, not a production plugin loader. Custom class loading must account for package sealing, module boundaries, dependency resolution, bytecode source security, loading failures, and resource lifecycles. Do not replace all delegation or self-load JDK classes just to run experiments.

### 7.2. When applied to real plugins

If plugin A uses `com.acme.api.Message` from loader A and the main system resolves an identically named class through loader B, Java may reject casts/lookups even though logs show the same name. The fix is not changing the descriptor text: you need to align **contract class identity**, choose the right loader, and design the API/SPI sharing path. When unloading a plugin, release handles and caches holding `Class<?>` so the loader has a chance to be garbage-collected.

## 8. Connecting with `MethodHandles.Lookup`

Remember to distinguish:

- **Descriptor string:** describes the shape, without specifying method name/owner or loader.
- **`MethodType`:** holds concrete runtime `Class<?>` objects for the resolved shape.
- **`MethodHandles.Lookup`:** checks permissions and performs **member lookup** by owner, name, kind, and `MethodType`.
- **`MethodHandle.type()`:** the signature of the **handle invocation** after finding/binding/adapting, which may differ from the declared method descriptor.

Successfully building a `MethodType` does not mean you have found the method. `findStatic` must target a static method; `findVirtual` must target an appropriate instance method; `findConstructor` must target a constructor and use the `void` return type at the lookup step.

### 8.1. Receiver of an instance method

Consider a method with source:

```java
int add(int a, int b) { return a + b; }
```

The JVM method descriptor of the **declaration** is `(II)I`. When calling `lookup.findVirtual(Calculator.class, "add", MethodType.methodType(int.class,int.class,int.class))`, the `MethodType` argument passed to `findVirtual` **does not include the receiver**. The returned handle, however, has type:

```text
(LInvokeDescriptorLab$Calculator;II)I
```

The receiver is placed first because the handle accepts a `Calculator` object before invoking `add`. In Lab 3, the static handle with the same parameters/return has type `(II)I`, with no receiver.

### 8.2. Two perspectives on constructors

A constructor in a class file is a special method named `<init>`, with return descriptor `V`. Thus the constructor `Box(int)` has JVM descriptor `(I)V`. When calling `Lookup.findConstructor(Box.class, MethodType.methodType(void.class,int.class))`, the handle creates a new **Box object**, so `handle.type()` is `(I)LInvokeDescriptorLab$Box;`.

Both perspectives are correct for their respective roles: **the descriptor of constructor `<init>`** and **the signature of the constructor handle** are two different structures. Do not use return type `Box` when passing `MethodType` to `findConstructor`.

## 9. Lab 3 — static, virtual, and constructor

Create the file **`InvokeDescriptorLab.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class InvokeDescriptorLab {
    static class Calculator {
        int add(int a, int b) { return a + b; }
        static int multiply(int a, int b) { return a * b; }
    }

    static class Box {
        final int id;
        Box(int id) { this.id = id; }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        ClassLoader loader = InvokeDescriptorLab.class.getClassLoader();

        MethodType declared = MethodType.fromMethodDescriptorString("(II)I", loader);
        MethodHandle staticHandle = lookup.findStatic(
                Calculator.class, "multiply", declared);
        MethodHandle virtualHandle = lookup.findVirtual(
                Calculator.class, "add", declared);

        MethodType constructorDescriptor =
                MethodType.fromMethodDescriptorString("(I)V", loader);
        MethodHandle constructor = lookup.findConstructor(Box.class, constructorDescriptor);

        int multiplied = (int) staticHandle.invokeExact(3, 4);
        int added = (int) virtualHandle.invokeExact(new Calculator(), 5, 6);
        Box box = (Box) constructor.invokeExact(9);

        System.out.println("declared=" + declared.toMethodDescriptorString());
        System.out.println("static=" + staticHandle.type().toMethodDescriptorString());
        System.out.println("virtual=" + virtualHandle.type().toMethodDescriptorString());
        System.out.println("constructorLookup=" + constructorDescriptor.toMethodDescriptorString());
        System.out.println("constructorHandle=" + constructor.type().toMethodDescriptorString());
        System.out.println("multiply=" + multiplied);
        System.out.println("add=" + added);
        System.out.println("box.id=" + box.id);
    }
}
```

```sh
javac --release 21 -Xlint:all InvokeDescriptorLab.java
java InvokeDescriptorLab
```

**Stdout:**

```text
declared=(II)I
static=(II)I
virtual=(LInvokeDescriptorLab$Calculator;II)I
constructorLookup=(I)V
constructorHandle=(I)LInvokeDescriptorLab$Box;
multiply=12
add=11
box.id=9
```

### 9.1. Interpretation and call site type checking

`declared` is the same declared type for both methods; `virtualHandle` prepends the `Calculator` receiver, whereas `staticHandle` keeps the same type. `constructorDescriptor` returns `void` according to the JVM constructor declaration, while `constructor.type()` returns `Box`.

`invokeExact` is an invocation that requires **exact types at the call site**. `(int) staticHandle.invokeExact(3,4)` specifies the `int` return type; `new Calculator()` passes the exact receiver; `(Box) constructor.invokeExact(9)` specifies the `Box` return type. A mismatched parameter, receiver, or return type can cause `WrongMethodTypeException`.

The lab declares `throws Throwable` to focus on `MethodHandle`; in application code, you should layer and handle exceptions intentionally. Do not infer that every `MethodHandle` must be called with `invokeExact`: `invoke` provides type conversion mechanisms, though you should still verify the signature and permitted conversions.

## 10. JVM descriptor, generic signature, and runtime identity

Consider a generic method:

```java
// Example declaration, placed in a class with import java.util.List.
public List<String> normalize(List<Integer> values) {
    return List.of();
}
```

The JVM method descriptor of this method is:

```text
(Ljava/util/List;)Ljava/util/List;
```

It does not distinguish `List<Integer>` from `List<String>`, because generic information is removed by **type erasure** from the method descriptor. The generic `Signature` attribute in the class file can still store type arguments, which Reflection accesses via `getGenericReturnType()`/`getGenericParameterTypes()`. However, `MethodType` only holds `Class<?>`, so two generic instantiations do not produce two different method types if their erased types are the same.

| Representation | Purpose | Carries loader identity? |
| --- | --- | --- |
| Method descriptor string | Notation for parameter/return types in bytecode | **No** |
| Generic `Signature` | Generic information of the declaration if present | Insufficient to determine runtime object type |
| `Class<?>` | A runtime type in the JVM | Has identity by class definition/loader |
| `MethodType` | List of parameter/return `Class<?>` objects | Yes, via each `Class<?>` |
| `MethodTypeDesc` | Nominal description of a method type | Classes not yet resolved |
| `Lookup` | Permission context used to find members | Has class/module context and lookup modes |

### 10.1. A nominal descriptor is not equivalent to a resolved MethodType

`MethodTypeDesc.ofDescriptor("(Lplugin/Missing;)V")` only requires the string to have valid syntax; `plugin.Missing` does not need to exist. Conversely, `MethodType.fromMethodDescriptorString(..., loader)` must convert the name into an actual `Class<?>` and can throw `TypeNotPresentException`.

`MethodTypeDesc.resolveConstantDesc(lookup)` is a different mechanism: it resolves a nominal descriptor according to the permission context of `Lookup`, with corresponding class/module checks and its own exception contract. It can be suitable for nominal constant models; do not use it as a "bypass" for access checks.

The Java 21 Javadoc also states that `toMethodDescriptorString()` **is not a strict inverse** of `fromMethodDescriptorString()`: even if the descriptor is valid, using a different loader can yield different `Class<?>` objects; some types that cannot be described nominally (such as certain hidden classes) may produce strings that do not parse back as ordinary valid descriptors.

## 11. Identifying the right error type

| Symptom | Common cause | How to handle |
| --- | --- | --- |
| `IllegalArgumentException` for `(V)I` | `void` appears in the parameter list | Check grammar: `V` is only used in the return position. |
| `IllegalArgumentException` for `(Ljava.lang.String;)V` | Class name uses `.` instead of `/` | Fix to `(Ljava/lang/String;)V`. |
| `TypeNotPresentException` | Reference class in the descriptor cannot be found by the chosen loader | Check binary/internal name, plugin loader, classpath/module path, and cause. |
| `NoClassDefFoundError` / `LinkageError` | Class may be found, but a dependency or linking condition is incompatible | Find the root cause; check versions, dependencies, and loader constraints. |
| `NoSuchMethodException` / `NoSuchMethodError` | Wrong name, owner, static/virtual kind, or erased signature | Cross-check with `javap -s`, method type, and the right lookup API. |
| `IllegalAccessException` | `Lookup` lacks permission to access the member/package/module | Check access modifiers, lookup modes, JPMS exports/opens; use an authorized API. |
| `WrongMethodTypeException` | Call site of `invokeExact` does not match `handle.type()` | Print the handle type; check the receiver and return cast. |
| Two types have the same descriptor but cannot be cast | Different defining loaders | Compare `Class<?>` with `==`, check `getClassLoader()`, align shared contract. |
| Parsing a descriptor does not print static initializer output | Loading/resolution is not initialization | Only test initialization with an appropriate triggering operation on a fresh JVM. |
| Passing `loader=null` resolves the wrong plugin | `null` means using the system loader in this API | Pass the plugin's intended loader explicitly. |
| Handling a constructor as `(I)LBox;` | Confusing JVM constructor descriptor with handle type | Parse `(I)V` when looking up `<init>`, inspect handle type after `findConstructor`. |

**Investigation workflow:** Separate the phases: parse syntax → resolve reference types → select owner & method name → Lookup access → invocation type. An error in a later stage should not be "fixed" by arbitrarily altering the descriptor from an earlier stage.

## 12. Safe design when receiving descriptors from plugins/configuration

A system with dynamic method configuration should use a transparent sequence of operations:

```text
Config/bytecode metadata
  |
  +--> validate descriptor syntax / length limits
  |
  +--> choose a trusted ClassLoader & module context
  |
  +--> parse MethodType or keep unresolved MethodTypeDesc
  |
  +--> determine owner Class, method name, invocation kind
  |
  +--> Lookup.findStatic/findVirtual/findConstructor with valid permissions
  |
  +--> check handle.type() and appropriate invocation mode
  |
  +--> invoke and log errors per phase
```

Do not treat an external descriptor string as a reason to **load/invoke any arbitrary class or member**. Use allowlists, contract interfaces, and appropriate policies. `Lookup` should operate within the actual module model and access controls; do not grant yourself permissions with `setAccessible(true)` or `--add-opens` without justification.

A cache keyed by `(ownerName, methodName, descriptor)` can be wrong when multiple plugins use the same class name with different loaders. Design the key to include runtime owner/type identity or partition by loader; clean up caches, threads, and method handles when a plugin unloads to avoid retaining class loaders unnecessarily.

### 12.1. How to inspect bytecode accurately without guessing

Use these commands:

```sh
javap -s -p DescriptorRoundTripLab
javap -c -p InvokeDescriptorLab
```

`-s` prints descriptors. `-c` displays bytecode opcodes and helps distinguish `invokestatic`, `invokevirtual`, and `invokespecial`; depending on compiler output, you may also see `invokedynamic`. Do not claim that those opcodes directly reveal all JIT runtime behavior.

In generic code, the compiler may also generate *bridge methods* with their own descriptors to preserve polymorphism after erasure. When searching for members in bytecode or Reflection, do not assume there is only one method with a given name declared in the source.

## 13. Practice exercises with outcome criteria

**Exercise 1 – Read descriptors by hand.** Decode `(JLjava/lang/String;)[D`, `([[I[Ljava/lang/Object;)V`, and `()Ljava/util/Map;`. State the exact parameter count, types, order, and return type. Solution: `(long,String) → double[]`; `(int[][],Object[]) → void`; `() → Map` (in erased form).

**Exercise 2 – Array structure.** Write `static long merge(byte[] data, double factor, String[][] names)`, predict the descriptor `([BD[[Ljava/lang/String;)J`, compile, and verify with `javap -s`. Explain why `D` counts as two slots while `[[Ljava/lang/String;` counts as only one.

**Exercise 3 – Constructor.** Add `Box(String label, int id)` to Lab 3, look it up with `(Ljava/lang/String;I)V`, and print `handle.type().toMethodDescriptorString()`. Explain why the handle returns `Box` while `<init>` returns `void`.

**Exercise 4 – Same loader.** In Lab 2, pass `application` to both `fromMethodDescriptorString` calls and predict `sameClass=true`, `sameMethodType=true`. Then have the isolated loader delegate instead of defining its own class; explain why two different loader objects can still resolve the same class.

**Exercise 5 – Syntax or resolution?** Parse `(V)I` and `(Lno/such/Missing;)V`. Name the two different exceptions and their reasons. Use `MethodTypeDesc.ofDescriptor` on the second case to demonstrate that its syntax is still valid.

**Exercise 6 – MethodHandle receiver.** From Lab 3, print `declared`, `staticHandle.type()`, `virtualHandle.type()`, and compare parameter 0 of the virtual handle. Try passing the wrong receiver and explain the error; do not keep the broken code in the final result.

**Exercise 7 – Plugin cache.** Assuming two plugins share the name `com.acme.Message`, describe why a descriptor string key is insufficient; propose a key structure based on runtime type identity and how the cache is cleared when a plugin closes.

**Self-assessment:** You have completed this lesson when you can manually read nested array/reference descriptors, construct `MethodType` in two ways, demonstrate the differences between syntax/loader/lookup, and accurately interpret all stdout from the three labs without relying on the assumption that "same class name means same type".

## 14. Official Java 21 references

- [JVMS 21 `4.3.2 – Field Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3.2): primitive/object/array.
- [JVMS 21 `4.3.3 – Method Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3.3): parameters, return, slot limits, and `this`.
- [Java SE 21 – MethodType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html): factories, parser, descriptor methods, and equality.
- [Java SE 21 – MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): controlled static/virtual/constructor lookups.
- [Java SE 21 – MethodTypeDesc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/constant/MethodTypeDesc.html): nominal descriptors and resolution.
- [JDK 21 – javap](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): inspecting descriptors from compiled class files.

**Key takeaway:** A descriptor is the **invocation shape by type name**. `MethodType` holds **runtime Class objects**; the class loader determines which class a name resolves to; `Lookup` determines which member can be linked with the current permissions. Distinguish all three layers to build a sound dynamic runtime system.
