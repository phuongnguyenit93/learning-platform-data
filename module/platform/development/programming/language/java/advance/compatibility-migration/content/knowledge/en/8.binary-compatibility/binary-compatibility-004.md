# Changing parameters, return types, and constructors

## 1. Why can signature changes break binary compatibility?

In Java, source code is compiled into bytecode. When compiling a method or constructor call, the compiler records information in the bytecode about the class name, member name, invocation kind, and descriptor of that member. At runtime, the JVM uses this information to link the call to the actual method or constructor in the loaded class.

Therefore, an already-compiled program can continue running with a new library version if the members referenced by bytecode still exist with matching descriptors and access permissions. Conversely, changing a parameter, return type, or constructor can change the descriptor. The new library's source code still compiles successfully, yet old client applications may fail when linking or invoking the member.

This is a **binary compatibility** issue. It differs from source compatibility:

- Source compatibility asks whether old client source code can recompile against the new API.
- Binary compatibility asks whether already-compiled client bytecode continues to link and run with the new API.
- Behavioral compatibility asks whether the program continues to produce the expected results and side effects as before.

These three aspects can produce different results. A change may leave descriptors unchanged yet alter behavior; a change may prevent source code from recompiling while old bytecode still links; and another change may cause old bytecode to throw `NoSuchMethodError` even though the new library's source code is completely valid.

In Java migration, pay special attention to three groups of changes:

1. Changing the type, count, or order of method parameters.
2. Changing the return type of a method.
3. Adding, removing, or changing constructors.

This lesson explains how the JVM identifies methods/constructors, compatibility-breaking cases, exceptions to understand such as bridge methods and type erasure, how to diagnose errors, and how to design an API migration path.

## 2. Method descriptors in the JVM

### 2.1. Descriptors describe parameters and return types

In a class file, a method is described by its name and descriptor. The descriptor represents the types of all parameters in order, followed by the return type. Examples:

| Java declaration | JVM descriptor |
| --- | --- |
| `int size()` | `()I` |
| `String name()` | `()Ljava/lang/String;` |
| `int parse(String text)` | `(Ljava/lang/String;)I` |
| `void save(long id, String value)` | `(JLjava/lang/String;)V` |
| `boolean contains(int[] values, int target)` | `([II)Z` |

Some basic type notations:

| Java type | Descriptor notation |
| --- | --- |
| `void` | `V` |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| Reference type, e.g., `java.lang.String` | `Ljava/lang/String;` |
| Array `int[]` | `[I` |
| Array `String[]` | `[Ljava/lang/String;` |

A method descriptor has the general form:

```text
(parameter-descriptors)return-descriptor
```

For example, `public int add(int left, int right)` has descriptor `(II)I`. The method `public void print(String value)` has descriptor `(Ljava/lang/String;)V`.

### 2.2. Parameter names are not in the descriptor

Renaming a parameter in source code:

```java
public void setName(String name) { ... }
```

to:

```java
public void setName(String displayName) { ... }
```

does not change the descriptor `(Ljava/lang/String;)V`. Thus, simply renaming parameters does not break binary linkage. Parameter names may appear in metadata if compiled with `-parameters`, and reflection or documentation tools can inspect that metadata, but the JVM does not use parameter names to resolve method calls.

This does not apply to parameter types. Changing `String` to `CharSequence` changes the descriptor, even though both are reference types and `String` implements `CharSequence`.

### 2.3. Return types are also in the descriptor

An important point is that JVM descriptors include the return type. For example:

```java
public int calculate(String input)
```

has descriptor `(Ljava/lang/String;)I`, whereas:

```java
public long calculate(String input)
```

has descriptor `(Ljava/lang/String;)J`.

In Java source code, you cannot declare two methods with the same name and parameter types differing only in return type to create an overload. However, at the bytecode level, the return type is still part of the descriptor referenced by already-compiled clients.

### 2.4. Constructors have the special name `<init>`

Constructors are represented in class files by the special name `<init>`. A constructor descriptor contains the parameter list and always has return type `V` (void), because constructors do not return a value in Java syntax.

Examples:

| Java declaration | JVM descriptor |
| --- | --- |
| `new Customer()` | `<init>()V` |
| `new Customer(String name)` | `<init>(Ljava/lang/String;)V` |
| `new Customer(long id, String name)` | `<init>(JLjava/lang/String;)V` |

When a client calls `new Customer()`, bytecode references constructor `<init>()V`. If the new library version no longer has that constructor, the JVM will not automatically redirect the call to a constructor taking different parameters.

## 3. Changing parameter types

### 3.1. Changing a parameter type changes the descriptor

Suppose library version 1 has:

```java
package com.example;

public class PriceCalculator {
    public int calculate(String amount) {
        return Integer.parseInt(amount);
    }
}
```

A client compiled against this API:

```java
PriceCalculator calculator = new PriceCalculator();
int result = calculator.calculate("120");
```

The client bytecode references method `calculate` with descriptor `(Ljava/lang/String;)I`.

If library version 2 changes the method to:

```java
public int calculate(CharSequence amount) {
    return Integer.parseInt(amount.toString());
}
```

the new descriptor is `(Ljava/lang/CharSequence;)I`. When running the old client with the new library, the JVM searches for the method using the old descriptor and cannot find it. When the call is linked, the program may throw `NoSuchMethodError`.

If the client source code is recompiled, it may still work because `String` is a subtype of `CharSequence`. However, that does not save previously compiled bytecode. This is a classic example where source compatibility and binary compatibility yield different results.

### 3.2. Changing primitive types also breaks descriptors

Primitive types have distinct descriptor notations. Changing parameter `int` to `long` changes the descriptor from `I` to `J`:

```java
// Version 1
public void setTimeout(int seconds) { ... }

// Version 2
public void setTimeout(long seconds) { ... }
```

Old bytecode invokes `setTimeout(I)V`; the new method has descriptor `(J)V`. The JVM does not perform widening from `int` to `long` during method linking to find an alternative descriptor. The compiler can automatically convert `int` to `long` when recompiling source code, but old bytecode still references the old signature.

Similarly, changing `Integer` to `int`, `double` to `BigDecimal`, or `byte[]` to `ByteBuffer` all change the descriptor.

### 3.3. Changing parameter count or order

Changing the number or order of parameters also changes the descriptor:

```java
// Version 1
public void transfer(String source, String destination) { ... }

// Version 2
public void transfer(String source, String destination, boolean overwrite) { ... }
```

The old descriptor is `(Ljava/lang/String;Ljava/lang/String;)V`, and the new descriptor is `(Ljava/lang/String;Ljava/lang/String;Z)V`. Old client bytecode still invokes the two-parameter descriptor and may receive `NoSuchMethodError` if the old method was removed.

Swapping the order of two parameters of the same type may leave the descriptor unchanged:

```java
public void move(String source, String destination)
```

and:

```java
public void move(String destination, String source)
```

both have descriptor `(Ljava/lang/String;Ljava/lang/String;)V`. Bytecode still links, but the meaning of the two parameters may be reversed. This is a dangerous behavioral change: the compiler and JVM do not know parameter names or business intent. Behavioral testing and API review are necessary even when the descriptor does not change.

### 3.4. Adding an overload usually preserves binary compatibility

If the new version keeps the old method and adds an overload:

```java
public void transfer(String source, String destination) {
    transfer(source, destination, false);
}

public void transfer(String source, String destination, boolean overwrite) {
    // New implementation
}
```

the old descriptor still exists, so old client bytecode can continue to link. New clients can use the new overload.

However, adding overloads can affect source compatibility because calls with lambdas, method references, `null`, or generic inference may become ambiguous or resolve to a different overload. Therefore, adding an overload is usually safer than deleting/changing the old method at the binary level, though the impact when consumers recompile still needs to be evaluated.

### 3.5. Varargs and arrays

In bytecode, a varargs parameter is represented by an array type. For example:

```java
public void log(String... messages)
```

has a descriptor corresponding to a `String[]` parameter: `([Ljava/lang/String;)V`. Replacing varargs syntax with an array declaration of the same type can preserve the binary descriptor, though it can change how calls are written in source code and the `ACC_VARARGS` metadata.

Conversely, changing `String...` to `Object...` changes the descriptor from `([Ljava/lang/String;)V` to `([Ljava/lang/Object;)V`, so it is no longer the same binary signature.

## 4. Changing return types

### 4.1. Changing the return type changes the descriptor

Suppose library version 1 has:

```java
public class Account {
    public int balance() {
        return 100;
    }
}
```

Compiled clients call the method with descriptor `()I`.

If version 2 changes it to:

```java
public long balance() {
    return 100L;
}
```

the new descriptor is `()J`. Although `int` can be widened to `long` when recompiling source code, the JVM will not match `()J` to satisfy the old bytecode call to `()I`. The result can be `NoSuchMethodError`.

Changing from one reference type to another also changes the descriptor:

```java
// Before
public Number value() { ... }

// After
public Integer value() { ... }
```

The descriptor changes from `()Ljava/lang/Number;` to `()Ljava/lang/Integer;`. The fact that `Integer` is a subtype of `Number` does not cause the old descriptor to automatically match the new descriptor.

### 4.2. Cannot overload solely by return type

Java does not allow declaring:

```java
public int value() { ... }
public long value() { ... } // Error: same name and same parameters
```

Therefore, when a return type must change while preserving binary compatibility, you cannot simply add another method with the same name and parameters and the new return type. Common options are:

- Keep the old method and add a new method with a different name, such as `balance()` and `balanceAsLong()`.
- Keep the old method and add an overload with distinguishable parameters if the API design makes sense.
- Create a new API or a new versioned interface with an adapter for old consumers.
- If possible, retain the old return type and convert internally, while providing a new API for the expanded data type.

Example:

```java
public class Account {
    /** @deprecated Use balanceAsLong() for the expanded range. */
    @Deprecated
    public int balance() {
        return Math.toIntExact(balanceAsLong());
    }

    public long balanceAsLong() {
        return 100L;
    }
}
```

This example preserves the `balance()I` descriptor so old clients continue to link. `Math.toIntExact` throws `ArithmeticException` if the value exceeds the `int` range, so this behavior must be documented and tested. If values cannot be guaranteed to stay within the old range, keeping the old method may require a different compatibility strategy.

### 4.3. Changing `void` to a value-returning type

Changing:

```java
public void refresh() { ... }
```

to:

```java
public boolean refresh() { ... }
```

changes the descriptor from `()V` to `()Z`. Old clients were compiled with a call to `refresh()V`; the new method does not have that descriptor, so binary linkage breaks.

Some assume that because old clients ignore the return value, they can keep running. However, bytecode does not look up methods solely by name and parameters; the return type is part of the descriptor. To preserve old clients, you can keep `void refresh()` and provide a new method with a different name such as `refreshAndReport()`.

### 4.4. Covariant return types and bridge methods

Java allows an overriding method to return a more specific reference type than the overridden method's return type. This is called a covariant return type.

```java
class Document { }
class PdfDocument extends Document { }

class BaseFactory {
    public Document create() {
        return new Document();
    }
}

class PdfFactory extends BaseFactory {
    @Override
    public PdfDocument create() {
        return new PdfDocument();
    }
}
```

At the source level, this override is valid because `PdfDocument` is a subtype of `Document`. However, the method descriptors in the two classes differ: the superclass has `()LDocument;`, while the subclass declares a method returning `()LPdfDocument;`.

The Java compiler typically generates a **bridge method** in the subclass to uphold the binary contract of the superclass method. The bridge has a descriptor returning `Document`, then calls the method returning `PdfDocument`. Bridge/synthetic methods can be observed with `javap -v`.

Bridge methods also appear in many generic scenarios due to type erasure. However, you should not infer that every return type change in a public API is automatically protected by a bridge. Covariant returns in an override relationship are a specific language rule; changing standalone method signatures in a library can still break binary compatibility.

## 5. Changing constructors

### 5.1. A constructor is a distinct binary call

When a client writes:

```java
Customer customer = new Customer();
```

the bytecode essentially allocates the object and then invokes constructor `<init>()V` using `invokespecial`. If the new version of the class no longer has a no-argument constructor, the old call cannot automatically switch to another constructor.

Example version 1:

```java
public class Customer {
    public Customer() {
    }
}
```

Version 2:

```java
public class Customer {
    public Customer(String name) {
        // Initialize customer
    }
}
```

Once a class declares a constructor with parameters, the compiler no longer generates a default no-argument constructor. Old clients calling `<init>()V` may receive `NoSuchMethodError` when running with the new class.

### 5.2. Adding constructor overloads

Adding a new constructor while keeping the old constructor generally preserves binary compatibility:

```java
public class Customer {
    public Customer() {
        this("Unknown");
    }

    public Customer(String name) {
        // Initialize customer
    }
}
```

Old clients continue calling `<init>()V`; new clients can call `<init>(Ljava/lang/String;)V`. The old constructor can be marked `@Deprecated` to guide consumers to transition gradually.

However, adding constructors can introduce source ambiguity. For example, when two constructors accept two unrelated reference types, a call like `new Customer(null)` may no longer select a unique overload. Therefore, source compatibility for consumers that recompile must also be tested.

### 5.3. Changing constructor parameter types or order

Constructors do not have arbitrary names to serve as another overloading mechanism. Changing parameter types or order changes the `<init>` descriptor:

```java
// Before
public Customer(String name, int age) { ... }

// After
public Customer(String name, long age) { ... }
```

The old descriptor is `<init>(Ljava/lang/String;I)V`, and the new descriptor is `<init>(Ljava/lang/String;J)V`. Old clients require the old constructor and may fail linkage.

If the order of parameters of the same type is swapped, the descriptor may remain unchanged while semantics change. For example, swapping two `String` parameters still leaves the same descriptor. The compiler and JVM do not recognize the meaning of `source` versus `destination`; only tests and API contracts catch such bugs.

### 5.4. Constructor visibility and inheritance

Constructors are not inherited like instance methods. Each class has its own constructors. Changing accessibility from `public` to `protected` or package-private can prevent clients in other packages from recompiling; old bytecode may encounter `IllegalAccessError` when the JVM checks access permissions.

Changing a superclass constructor can also prevent subclass constructors from compiling if `super(...)` calls no longer match. When building a library with an ecosystem of external subclasses, constructors invoked from subclass source code must be treated as part of the API contract.

### 5.5. Adding constructor parameters and factory methods

If a constructor needs additional configuration, you do not necessarily have to remove the old constructor. You can keep the old constructor delegating to the new constructor:

```java
public class HttpClientConfig {
    public HttpClientConfig(String endpoint) {
        this(endpoint, Duration.ofSeconds(10));
    }

    public HttpClientConfig(String endpoint, Duration timeout) {
        // Validate and store configuration
    }
}
```

When the number of parameters grows large, factory methods or builders can make the API easier to extend:

```java
HttpClientConfig config = HttpClientConfig.builder()
        .endpoint("https://service.example")
        .timeout(Duration.ofSeconds(10))
        .build();
```

This is an API design change; when moving from an old constructor to a builder, the old constructor still needs to be retained during a compatibility phase or removed in a major version with a clear roadmap.

## 6. Generic types, type erasure, and descriptors

### 6.1. Generic arguments are usually erased from descriptors

Java uses type erasure to implement generics. JVM descriptors usually contain the erased type, not the full generic type arguments.

For example:

```java
public void setNames(List<String> names) { ... }
```

and:

```java
public void setNames(List<Integer> names) { ... }
```

both have method descriptor `(Ljava/util/List;)V`, because both parameters are erased to `List`.

Consequently, changing `List<String>` to `List<Integer>` may leave the descriptor unchanged so old bytecode still links. However, this change can break source compatibility or cause runtime errors because old code assumes elements are `String` while the new library supplies `Integer`.

Example old client:

```java
List<String> names = service.names();
String first = names.get(0);
```

If the new implementation actually returns `List<Integer>` while keeping the erased descriptor `()Ljava/util/List;`, the call may link; when the compiler-generated cast to `String` executes, the client may receive `ClassCastException`.

### 6.2. Changing bounds can change erasure

Consider the method:

```java
public <T> T value() { ... }
```

Without a specific bound, the erasure of `T` is typically `Object`. Changing it to:

```java
public <T extends Number> T value() { ... }
```

causes the erasure of `T` to become `Number`. The descriptor may change from `()Ljava/lang/Object;` to `()Ljava/lang/Number;`, causing binary impact.

Therefore, when changing a generic API, do not only compare how `T` is written in source code. Determine the erasure of type variables, parameterized types, arrays, and bounds before and after.

### 6.3. Generic signatures and reflection

A class file can store generic signatures in the `Signature` attribute alongside erased descriptors. The Java compiler uses generic information when recompiling source; reflection can read generic types through APIs such as `getGenericParameterTypes()` or `getGenericReturnType()`.

Thus, changing generic arguments may not break JVM linkage yet still affect source consumers, reflection-based frameworks, dependency injection, serializers, or code generation tools. Descriptor-based binary compatibility does not cover all metadata that frameworks might use.

## 7. Other changes that can have impact even if the descriptor stays the same

Not every risk manifests as a different descriptor.

### 7.1. Changing the order of parameters of the same type

As noted, `send(String from, String to)` and `send(String to, String from)` have the same descriptor. Old clients link normally, but data can be swapped. This is a behavioral change, not a linkage failure.

### 7.2. Changing `static` to instance or vice versa

Descriptors do not directly encode the `static` modifier, but client bytecode uses different opcodes for static and instance calls (`invokestatic` vs. `invokevirtual`/`invokeinterface`). Changing an instance method to static or vice versa can cause old clients to encounter `IncompatibleClassChangeError`.

### 7.3. Changing access rights

Changing `public` to `protected` or package-private can prevent old clients from having permission to invoke the method/constructor and cause `IllegalAccessError`. Changing access permissions can also prevent client source code from recompiling.

### 7.4. Changing `throws`

Checked exception lists are not in JVM method descriptors. Thus, adding or removing `throws IOException` does not by itself change the descriptor. However, recompiling client source may require catching the new exception or encounter warnings/differences in the API contract. A runtime implementation can still throw undeclared exceptions; the JVM does not use `throws` to resolve methods.

### 7.5. Changing nullability or semantics

Changing a contract from accepting `null` to rejecting `null`, changing default values, or changing invalid-input handling can preserve descriptors while breaking behavioral compatibility. These changes require contract tests and release notes.

## 8. Common runtime errors

| Error | Common cause | Connection to signature changes |
| --- | --- | --- |
| `NoSuchMethodError` | Bytecode references a method/constructor that no longer has a matching descriptor in the runtime class | Deleting old method, changing parameter/return types or constructor |
| `IncompatibleClassChangeError` | Class structure changed in a way incompatible with old bytecode | Changing static/instance, class/interface, or member kind |
| `IllegalAccessError` | Bytecode invokes a member that is no longer accessible | Reducing visibility of method/constructor or changing module access |
| `AbstractMethodError` | Runtime class does not provide a suitable implementation for a method required by the caller | Changing interface/abstract contract or out-of-sync implementation |
| `ClassCastException` | Actual type does not match the cast inserted into bytecode by the compiler | Changing generic contract while preserving erased descriptor, changing data semantics |
| `NoSuchMethodException` | Reflection cannot find a method by the requested name and parameter types | API changed; differs from `NoSuchMethodError` in bytecode linkage |

`NoSuchMethodError` and `NoSuchMethodException` are not the same. The former is an `Error` occurring when the JVM links a bytecode call; the latter is a checked exception from reflection APIs when a program explicitly looks up a method via `Class.getMethod()` or `getDeclaredMethod()`.

When a linkage error occurs, do not simply add another dependency or clear caches. First identify which class is being loaded, which descriptor the bytecode references, and which API version the actual runtime classpath contains.

## 9. Diagnostics with `javap` and API analysis tools

### 9.1. Viewing descriptors in class files

`javap -s` displays method and constructor descriptors. Examples:

```bash
javap -classpath library-v1.jar -s com.example.PriceCalculator
javap -classpath library-v2.jar -s com.example.PriceCalculator
```

Compare the outputs to see which descriptors changed or were removed. For more detailed information:

```bash
javap -classpath library-v1.jar -p -s -c -v com.example.PriceCalculator
```

- `-p` displays non-public members as well.
- `-s` displays descriptors.
- `-c` displays method bytecode.
- `-v` displays detailed information such as flags, bridge/synthetic methods, and attributes.

### 9.2. Viewing calls referenced by compiled clients

After compiling the client against library version 1, inspect the bytecode:

```bash
javap -classpath client-classes:library-v1.jar -c -v com.example.Client
```

Look for `invokevirtual`, `invokeinterface`, `invokestatic`, or `invokespecial` instructions and the corresponding constant pool entries. The reference shows the owner, method name, and descriptor that the client requires at runtime.

On Windows, the classpath separator is a semicolon (`;`) instead of a colon (`:`). Run the command on the client's class files using a classpath appropriate for the environment.

### 9.3. Testing old clients against the new library

An important binary compatibility test is:

1. Compile the client once against library v1.
2. Keep the generated client bytecode unchanged.
3. Run the client with library v2 on the runtime classpath.
4. Record linkage errors or behavioral changes.

Do not recompile the client between steps 2 and 3. Recompiling causes the compiler to use the new API and the test no longer checks old bytecode.

Example directory structure:

```text
compat-check/
  library-v1.jar
  library-v2.jar
  client-classes/
```

Illustrative run command:

```bash
java -cp client-classes:library-v2.jar com.example.Client
```

### 9.4. API comparison tools

In library projects, API comparison tools such as japicmp or Revapi can be integrated to detect public/protected API changes between two artifacts. These tools help detect many forms of breaking changes in signatures, class hierarchy, and visibility.

Automated results must be reviewed against project policy. API comparison tools cannot automatically determine whether a behavioral change is acceptable, and not all metadata used by frameworks is fully evaluated under a default configuration.

## 10. Strategies for maintaining compatibility when API changes are needed

### 10.1. Keeping the old method and adding a new method

If parameters change, the old method can be kept as an adapter:

```java
public class ReportService {
    /** @deprecated Use export(Path, ExportOptions). */
    @Deprecated
    public void export(String fileName) {
        export(Path.of(fileName), ExportOptions.defaults());
    }

    public void export(Path path, ExportOptions options) {
        // New implementation
    }
}
```

Old clients continue linking to `export(String)`. New clients use `export(Path, ExportOptions)`. The adapter must convert data according to clear rules, including encoding, relative paths, permissions, and I/O errors.

### 10.2. Keeping the old constructor and delegating to the new constructor

```java
public class ReportService {
    /** @deprecated Use the constructor with options. */
    @Deprecated
    public ReportService(Path outputDirectory) {
        this(outputDirectory, ExportOptions.defaults());
    }

    public ReportService(Path outputDirectory, ExportOptions options) {
        // Validate and initialize
    }
}
```

The old constructor continues to exist with its original descriptor. Delegating via `this(...)` keeps a single primary initialization path, preventing logic divergence between constructors.

### 10.3. Retaining the old return type via a forwarding method

Because Java does not allow overloading solely by return type, use a new method name:

```java
public int count() {
    return Math.toIntExact(countLong());
}

public long countLong() {
    // Compute full count
    return 0L;
}
```

If the old method cannot represent all new values, clearly define the behavior on out-of-range values. Do not silently truncate or wrap numbers to maintain compatibility.

### 10.4. Using a new interface or versioned API when changes are too broad

If many methods and constructors change together, keeping numerous adapters can make the API confusing. In that case, you can create a new interface/class, such as `ClientV2`, or a new API package, and provide adapters between the old and new generations during the transition period.

This strategy fits when data contracts, lifecycle, or semantics change deeply. Define the parallel support period, how consumers migrate, and when the old API will be removed.

## 11. Planning migration by change type

### 11.1. When changing parameters

1. Obtain old and new descriptors using `javap` or API diffs.
2. Identify all compiled clients and consumers that need recompilation.
3. Check primitive/reference types, generic erasure, parameter order, and null semantics.
4. If binary compatibility must be preserved, keep the old method and delegate to the new implementation.
5. Check overload resolution for source consumers, especially calls with `null`, lambdas, and method references.
6. Run old-client tests against the new library and contract tests for new consumers.

### 11.2. When changing return types

1. Determine old and new descriptors; remember that the return type is part of the JVM descriptor.
2. Check covariant returns in override relationships and compiler-generated bridge methods.
3. If a standalone method needs a return type change, do not attempt to add an overload with the same name and parameters.
4. Consider a new method with a different name or a next-generation interface/API.
5. If keeping the old method, check whether conversion causes data loss, overflow, or nullability changes.
6. Test old client bytecode and source consumers after recompilation.

### 11.3. When changing constructors

1. List all existing `<init>` descriptors and constructors called by consumers.
2. Keep old constructors if binary compatibility is needed.
3. Add new overloads or factories/builders for expanded configuration.
4. Use `this(...)` to centralize initialization logic.
5. Check visibility and compilation of external subclasses.
6. Check calls with `null`, numeric literals, and new overloads to avoid source ambiguity.

### 11.4. Setting clear release criteria

For public libraries, release notes should state:

- Which members changed descriptors.
- Whether the old API remains or was removed.
- Which bridge methods or adapters are generated/provided.
- Whether consumers must recompile or can use old bytecode.
- The minimum Java/JDK level of the new artifact.
- Behavioral changes or conversion limits.
- The final version expected to support the old API.

Do not simply write "breaking changes in API" without specifying the exact methods/constructors. Consumers need to know precisely which call sites must be updated and how to migrate.

## 12. Comprehensive example: upgrading a library from version 1 to version 2

Suppose library version 1 has:

```java
public class FileRecord {
    public FileRecord() { }

    public void setSize(int size) { }

    public int size() { return 0; }
}
```

Old client:

```java
FileRecord record = new FileRecord();
record.setSize(120);
int size = record.size();
```

Version 2 changes all three simultaneously:

```java
public class FileRecord {
    public FileRecord(Path source) { }

    public void setSize(long size) { }

    public long size() { return 0L; }
}
```

All three changes impact descriptors:

| Member | v1 descriptor | v2 descriptor | Risk to old clients |
| --- | --- | --- | --- |
| Constructor | `<init>()V` | `<init>(Ljava/nio/file/Path;)V` | `NoSuchMethodError` when instantiating `FileRecord` |
| `setSize` | `(I)V` | `(J)V` | `NoSuchMethodError` when calling `setSize(int)` |
| `size` | `()I` | `()J` | `NoSuchMethodError` when calling `size()` |

If binary compatibility must be preserved, version 2 can retain the old members:

```java
public class FileRecord {
    @Deprecated
    public FileRecord() {
        this(Path.of("."));
    }

    public FileRecord(Path source) {
        // Initialize from source
    }

    @Deprecated
    public void setSize(int size) {
        setSize((long) size);
    }

    public void setSize(long size) {
        // Store size
    }

    @Deprecated
    public int size() {
        return Math.toIntExact(sizeLong());
    }

    public long sizeLong() {
        // Return full size
        return 0L;
    }
}
```

This example retains the old descriptors for the constructor, setter, and getter. However, it must clearly decide how the default constructor chooses `Path`, and how `size()` handles values exceeding the `int` range. If those decisions do not fit the old contract, do not pretend the adapter is completely equivalent. A major release with clearly announced breaking changes may be needed.

## 13. Binary compatibility review checklist

When reviewing public/protected API changes, check:

- [ ] Does the old method still exist with the same name and descriptor?
- [ ] Has the primitive/reference type of any parameter changed?
- [ ] Has the number or order of parameters changed?
- [ ] Has the return type changed?
- [ ] Do generic erasure and bounds change the descriptor?
- [ ] Does the old constructor still exist with the old `<init>` descriptor?
- [ ] Have visibility and the `static` modifier changed?
- [ ] Are required bridge methods present for overrides/covariant returns?
- [ ] Does adding an overload cause source ambiguity for `null`, lambdas, or method references?
- [ ] Do clients compiled against the old version run against the new artifact?
- [ ] Does the actual runtime classpath contain the expected new artifact?
- [ ] Do changes to semantics, nullability, and data have contract tests?

This checklist supports reviews; the most important evidence remains API diffs and testing the old client with the new library on a controlled classpath.

## 14. Common mistakes

**Assuming the return type is not in the descriptor.** In the JVM, the return type is part of the method descriptor. Changing `int` to `long` or `void` to `boolean` can prevent old clients from linking.

**Assuming the JVM automatically widens parameters or results during linking.** The compiler may insert conversions when recompiling source, but the JVM does not replace an old descriptor with a similar-looking one.

**Removing a no-argument constructor while forgetting compiled clients.** When a class declares another constructor, the default constructor is no longer generated automatically. Keep the old constructor or release a planned breaking change.

**Assuming generic arguments are always present in descriptors.** Type erasure can give `List<String>` and `List<Integer>` the same descriptor. Linkage may succeed while source/reflection/behavior still fails.

**Assuming the same descriptor means the same behavior.** Reordering parameters of the same type or changing semantics can preserve the descriptor while corrupting data.

**Only running tests after recompiling all clients.** Recompiling hides many binary compatibility bugs. Keep old client bytecode and swap only the runtime library.

**Confusing `NoSuchMethodError` with `NoSuchMethodException`.** One is a JVM linkage error of bytecode; the other is the result of looking up a method via reflection.

**Using bridge methods as a general solution for any return type change.** Bridges primarily serve covariant overrides and generic erasure; they do not automatically protect arbitrary public methods whose signatures changed.

## 15. Conclusion

Parameters, return types, and constructors are a direct part of the binary contract. The JVM links calls by member name and descriptor, where a method descriptor contains both parameter types and the return type, while constructors use the special name `<init>` and always have a descriptor returning `V`. Therefore, changing parameter types, parameter counts, return types, or removing constructors can cause old client bytecode to encounter linkage errors.

When compatibility must be preserved, the common strategy is keeping old descriptors, adding new APIs, and forwarding via adapters or constructor delegation. For return type changes, Java does not permit overloading solely by return type, so a new method name or next-generation API is typically required. Finally, inspect descriptors with `javap`, use API diff tools, and run old client bytecode with the new library to verify binary compatibility before release.
