# Changing Parameter Types, Return Values, and Type Conversion Rules

In Java, the data types appearing in a method signature and at the call site determine whether the compiler accepts the source code. When upgrading a library or refactoring an API, changing a parameter type, return type, or overload can cause consumers to fail to compile, select a different method, or encounter runtime errors.

With Java Compatibility Migration, both **source compatibility** and **binary compatibility** need to be considered. A change may still allow old source code to compile after very few edits, while making already-released bytecode no longer able to link. Conversely, a generic change can keep the method descriptor unchanged after type erasure yet still cause source consumers to fail or change behavior due to casts on the caller side.

## 1. Method Signatures and the Role of Data Types

In Java, a method signature (*method signature*) is determined primarily by the method name and formal parameter types, after applying the rules for generics and erasure. The return type is not used to distinguish two overloads.

Example:

```java
public String findName(long id) { ... }
public String findName(String code) { ... }
```

Two methods can coexist because the parameter type lists are different. However, Java does not allow declaring two methods that differ only in return type:

```java
// Invalid: cannot overload solely by return type.
public String getValue() { ... }
public CharSequence getValue() { ... }
```

This leads to a point to keep in mind when changing an API:

- Changing a parameter type changes the source signature and usually changes the method's descriptor in bytecode.
- Changing a return type does not create a new overload, but affects how the caller uses the result and also changes the descriptor at the JVM level.
- Adding an overload can change which method is selected at call sites that previously compiled successfully.
- Changing a generic type can affect type checking in source code even though the descriptor after erasure does not change.

## 2. Changing Parameter Types

Parameter types determine which arguments can be passed to a method. When parameter types change, related call sites, subclass overrides, method references, overloads, and generic types need to be checked.

### 2.1. Changing a Parameter Type from More Specific to More General

Suppose API version 1 accepts `String`:

```java
public class NameService {
    public void setName(String name) {
        // Process the name.
    }
}
```

Calling application:

```java
NameService service = new NameService();
String name = "An";
service.setName(name);
```

Version 2 changes the parameter to `CharSequence`:

```java
public class NameService {
    public void setName(CharSequence name) {
        // Process a general string.
    }
}
```

The call with `String` still compiles because `String` implements `CharSequence`. This is an example of a parameter type change where some call sites remain source-compatible.

However, it cannot be concluded that all consumers are compatible. If a consumer has a subclass overriding the old method, the outcome will differ:

```java
public class CustomNameService extends NameService {
    @Override
    public void setName(String name) {
        System.out.println("Custom: " + name);
    }
}
```

When the library changes the superclass method to `setName(CharSequence)`, the `setName(String)` method in the subclass no longer overrides that method. The `@Override` annotation causes the compiler to report an error. If the annotation is removed, the subclass still has a separate overload, but calls dispatched through the `NameService` type will no longer invoke the old implementation as before.

Therefore, when changing parameters in an API that can be subclassed, it is also necessary to check implementation/override classes outside the library.

### 2.2. Changing a Parameter Type from More General to More Specific

If the old version accepts `CharSequence`:

```java
public void setName(CharSequence name) { ... }
```

and the new version only accepts `String`:

```java
public void setName(String name) { ... }
```

call sites passing `String` may still compile. However, code passing `StringBuilder` or another `CharSequence` implementation will no longer be valid:

```java
service.setName(new StringBuilder("An"));
```

The compiler reports that no suitable method was found because `StringBuilder` is not a `String`.

Replacing a general parameter with a more specific type usually narrows the set of valid arguments. If compatibility needs to be maintained, the library can keep the old overload or create an adapter, provided the contract can still be fulfilled correctly.

### 2.3. Changing Primitive Types

Primitive types have widening and narrowing rules. Some parameter changes remain acceptable thanks to widening primitive conversion.

For example, the old version accepts `long`:

```java
public void setTimeout(long millis) { ... }
```

The new version accepts `int`:

```java
public void setTimeout(int millis) { ... }
```

Call sites passing an `int` value still compile, whereas call sites holding a `long` variable cannot automatically narrow down to `int`:

```java
long timeout = 5_000L;
service.setTimeout(timeout); // Error: explicit narrowing conversion is required.
```

Conversely, if the API changes from `int` to `long`, an `int` argument can widen automatically:

```java
int timeout = 5_000;
service.setTimeout(timeout); // Can convert int to long.
```

Even though the call site compiles, changing the type can still alter semantics: value bounds, overflow, calculations, serialization, or values stored in the database.

### 2.4. Changing Between Primitives and Wrappers

Java supports automatic boxing and unboxing in many contexts.

```java
public void setCount(int count) { ... }

Integer value = 10;
service.setCount(value); // Unboxing Integer to int.
```

If `value` is `null`, the code still compiles but throws a `NullPointerException` when unboxing.

Conversely:

```java
public void setCount(Integer count) { ... }

int value = 10;
service.setCount(value); // Boxing int to Integer.
```

Replacing `int` with `Integer` can change how an absent value is represented: `0` and `null` are not the same. It can also affect overload resolution, performance due to boxing/unboxing, and APIs that accept generic types.

### 2.5. Changing Generic Parameters

Generic types are checked at compile time and Java applies type erasure when generating bytecode. However, type arguments still matter for source compatibility.

Suppose the old API:

```java
public void addNames(List<String> names) { ... }
```

The new API changes to:

```java
public void addNames(List<Object> names) { ... }
```

Call sites using `List<String>` no longer compile because Java generics are invariant: `List<String>` is not a subtype of `List<Object>`.

Notably, after type erasure, both parameters erase to `List`. The method descriptor at the JVM level may still be:

```text
(Ljava/util/List;)V
```

Therefore, an old binary may still be able to link, while source code being recompiled fails. This is a clear example showing that source compatibility and binary compatibility are not identical.

If the method only reads data, a wildcard may be more appropriate:

```java
public void printNames(List<? extends CharSequence> names) {
    for (CharSequence name : names) {
        System.out.println(name);
    }
}
```

`? extends` allows accepting lists whose elements are subtypes of `CharSequence`, but does not allow adding an arbitrary value to that list (except `null`). If the method needs to write to the collection, choose an appropriate generic contract instead of changing the type argument mechanically.

### 2.6. Changing Array and Varargs Parameters

A varargs parameter:

```java
public void log(String... messages) { ... }
```

is represented as an array parameter `String[]` at the method signature/descriptor level. Changing between `String[]` and `String...` does not create two different signatures; the main difference is how call sites are allowed to pass the argument list.

Adding or changing a varargs overload can change method selection, especially when call sites pass `null`, an array, or varying numbers of arguments. Consumers with such call patterns need to be recompiled to detect ambiguous calls or unexpected overload selection.

## 3. Changing Return Types

The return type determines the data type that the caller receives. When the return type changes, expressions that use the result need to be rechecked.

### 3.1. Replacing a Specific Return Type with a More General Type

Old API:

```java
public String getDisplayName() {
    return "An";
}
```

Caller:

```java
String name = service.getDisplayName();
```

New API:

```java
public CharSequence getDisplayName() {
    return "An";
}
```

The old caller no longer compiles because `CharSequence` cannot be automatically converted to `String`:

```java
String name = service.getDisplayName(); // Data type error.
```

If the caller only needs a broader abstraction, the variable type can be changed:

```java
CharSequence name = service.getDisplayName();
```

However, if the caller needs APIs specific to `String`, changing the variable type is not enough; the appropriate conversion must be determined, such as `toString()` when semantics allow.

### 3.2. Replacing a General Return Type with a More Specific Type

If the API changes from `CharSequence` to `String`, many callers receiving the result into `CharSequence` still compile because `String` is a subtype. Callers using method references or generic inference may also infer a more specific type.

Example:

```java
CharSequence name = service.getDisplayName();
```

remains valid if the new method returns `String`.

However, changing the return type still requires reviewing subclass overrides. A subclass overriding with `CharSequence` will no longer be able to override if the superclass return type is narrowed to `String`, because `CharSequence` is not a subtype of `String`.

### 3.3. Covariant Return Types in Overrides

Java allows an overriding method to return a subtype of the superclass method's return type. This is called a *covariant return type*.

```java
class Animal {}
class Dog extends Animal {}

class AnimalFactory {
    Animal create() {
        return new Animal();
    }
}

class DogFactory extends AnimalFactory {
    @Override
    Dog create() {
        return new Dog();
    }
}
```

`Dog` is a subtype of `Animal`, so the override is valid. Callers can see the more specific return type when referencing through `DogFactory`:

```java
Dog dog = new DogFactory().create();
Animal animal = new DogFactory().create();
```

If the superclass API changes its return type from `Animal` to a narrower type incompatible with the subclass's return type, the subclass source code may no longer compile. When designing a library intended for inheritance, overrides in consumers need to be checked.

### 3.4. Return Types Do Not Create Overloads

Java does not allow distinguishing overloads solely by return type. Therefore, if a new API with a different return type needs to be provided while keeping the old API, a different method name or a separate wrapper/adapter type usually has to be used.

Example:

```java
public String getName() {
    return currentName;
}

public Optional<String> findName() {
    return Optional.ofNullable(currentName);
}
```

This approach helps users migrate intentionally and avoids unexpected changes across all call sites.

### 3.5. Impact of Return Types on Generic Inference and Method References

The return type participates in expression type checking and can affect generic inference or method references.

Example:

```java
Supplier<String> supplier = service::getDisplayName;
```

If `getDisplayName()` changes from `String` to `CharSequence`, the method reference no longer matches `Supplier<String>`. The target type may need to be changed:

```java
Supplier<CharSequence> supplier = service::getDisplayName;
```

Similarly, the return type of a generic method can affect the inferred type arguments. When changing an API, call sites using method chaining, lambdas, method references, and generic helpers need to be checked, not only direct variable assignment lines.

## 4. Type Conversion Rules in Java

The compiler only accepts conversions permitted by the Java Language Specification in each context. A conversion valid in variable assignment is not necessarily valid in method invocation or overload selection.

### 4.1. Identity Conversion

Identity conversion does not change the type. For example, passing a `String` variable into a `String` parameter:

```java
void print(String value) { }

String name = "An";
print(name);
```

This is the simplest case and is usually low-risk when the API does not change.

### 4.2. Widening Primitive Conversion

Widening primitive conversion converts a primitive value to a type with a wider representation range according to Java rules. Example:

```java
byte b = 10;
short s = b;
int i = s;
long l = i;
float f = l;
double d = f;
```

Some common conversion paths:

| From | Can widen to |
|---|---|
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |

`boolean` does not convert to numeric types. Widening does not mean every value is preserved with full precision: converting `long` to `float` or `double` can lose precision because floating-point numbers have a finite number of significand bits.

### 4.3. Narrowing Primitive Conversion

Narrowing converts to a type with a narrower range and usually requires an explicit cast:

```java
long total = 1_000L;
int count = (int) total;
```

If the value exceeds the target type's range, the result may overflow or lose information. A cast does not automatically check whether the value is safe.

Java has an exception in the assignment context: a constant expression of type `int` whose value is representable in `byte`, `short`, or `char` can be assigned without a cast:

```java
byte small = 10; // Valid: int constant is within the byte range.
```

However, this exception does not apply in the same way to method invocation:

```java
void accept(byte value) { }

accept(10); // Invalid: method invocation does not automatically narrow int to byte.
```

The difference between assignment context and method invocation context is a common source of errors when changing parameter types.

### 4.4. Widening Reference Conversion

An object can be referenced through a superclass or interface it implements:

```java
String text = "Java";
CharSequence sequence = text;
Object value = text;
```

This conversion does not change the actual object; it only changes the static type that the compiler uses to check access.

If an API changes a parameter from a subtype to a supertype, some call sites may continue to compile thanks to widening reference conversion. However, that change can affect overrides, overloads, and implementation semantics.

### 4.5. Narrowing Reference Conversion and Casts

Converting from a supertype to a subtype requires a cast:

```java
Object value = "Java";
String text = (String) value;
```

The compiler may accept the cast, while runtime checks the actual object type. If the object is not a `String`, the program throws `ClassCastException`.

When an API changes its return type from `String` to `Object`, the caller may add a cast to compile, but this is not a safe fix unless there is a guarantee about the actual object type.

### 4.6. Boxing and Unboxing

Boxing converts a primitive into its corresponding wrapper; unboxing does the reverse:

```java
int count = 5;
Integer boxed = count; // Boxing.

Integer stored = 10;
int unboxed = stored;  // Unboxing.
```

Unboxing `null` throws `NullPointerException`. Boxing can also allocate objects and affect allocation/performance in large loops or frequently called APIs.

There is no conversion combining boxing with widening primitive conversion in arbitrary directions. For example, `int` does not automatically box to `Long`; `Integer` does not automatically convert to `Long` just because `int` can widen to `long`.

### 4.7. Numeric Promotion in Expressions

In many arithmetic operations, `byte`, `short`, and `char` are promoted to `int` before performing the operation:

```java
byte a = 1;
byte b = 2;
// byte result = a + b; // Error: expression has type int.
byte result = (byte) (a + b);
```

If the operation involves `long`, `float`, or `double`, the operands are promoted according to binary numeric promotion rules. When changing parameter types or return types, the type of the passed expression must also be examined, not just the declared type of the original variable.

### 4.8. Null and Reference Types

`null` can be assigned to a reference type, but cannot be assigned to a primitive. When an API replaces a wrapper with a primitive, call sites passing `null` no longer compile or may undergo unboxing causing errors depending on context.

`null` can also make overloads ambiguous:

```java
void send(String value) { }
void send(java.nio.file.Path value) { }

send(null); // Error: String and Path have no subtype relationship with each other.
```

When adding overloads to a public API, inspect call sites that may pass the `null` literal or expressions with broad reference types.

## 5. Overload Resolution and Call Site Behavior Changes

The compiler does not choose an overload solely based on the number of parameters. It considers the static types of arguments, allowed conversions, generic inference, varargs, and rules for selecting the most specific method.

### 5.1. Phases of Overload Lookup

At a high level, Java considers applicable methods in order:

1. Strict invocation phase: matching identity, widening primitive, and widening reference conversions.
2. Loose invocation phase: additionally allows boxing/unboxing along with specified conversions.
3. Variable arity phase: considers varargs methods when the earlier phases find no applicable method.

When multiple methods are applicable in the same phase, the compiler selects the most specific method according to type relationships. If there is no single most specific method, the call is reported as ambiguous.

### 5.2. Adding an Overload Can Change Which Method Is Called

Initial library version:

```java
public void send(Object value) {
    System.out.println("object");
}
```

Calling application:

```java
send("hello");
```

After the library adds an overload:

```java
public void send(String value) {
    System.out.println("string");
}
```

The old source still compiles, but the call `send("hello")` now selects the `String` overload because it is a more specific type. Runtime behavior can change even without a compiler error.

If two overloads taking two unrelated types are added, a call passing `null` can become ambiguous:

```java
public void send(String value) { }
public void send(java.nio.file.Path value) { }

send(null); // Cannot determine the most suitable overload.
```

This is why adding APIs also needs to be evaluated for source compatibility, not only removing or renaming APIs.

### 5.3. Overloads with Primitives, Wrappers, and Widening

Example:

```java
void choose(long value) {
    System.out.println("long");
}

void choose(Integer value) {
    System.out.println("Integer");
}

choose(1);
```

The call selects `choose(long)` because widening primitive conversion belongs to the strict invocation phase and is evaluated before the phase requiring boxing to `Integer`. If an overload or argument type changes, the selected method can change.

During API migration, check call sites using numeric literals, wrappers, `null`, generic methods, lambdas, and method references. These locations are often more sensitive to overload changes than calls with variables of specific types.

## 6. Generic Types, Erasure, and Bridge Methods

### 6.1. Type Erasure Does Not Eliminate Source Impact

Java generics are implemented via type erasure. For example, `List<String>` and `List<Integer>` have the same raw type `List` at runtime. However, the compiler still checks type arguments when compiling source code.

Therefore, changing a parameter from `List<String>` to `List<Object>` can preserve the descriptor after erasure while preventing consumers from recompiling. Conversely, if a new implementation assumes every element is an `Object` while old callers were compiled against a different contract, errors may only appear at runtime.

### 6.2. Name Clashes Due to Erasure

Two methods with different generic signatures but the same erasure cannot be overloaded:

```java
void process(List<String> values) { }

// Invalid: same erasure is process(List).
void process(List<Integer> values) { }
```

The compiler reports a name clash because the two method descriptors after erasure collide. When changing a generic API, check erasure, type bounds, and existing overloads as well.

### 6.3. Bridge Methods

The compiler may generate bridge methods to preserve polymorphism after type erasure or to support covariant returns. Example:

```java
class Box<T> {
    T get() { return null; }
}

class StringBox extends Box<String> {
    @Override
    String get() { return "value"; }
}
```

The compiler can generate a bridge method in `StringBox` so that calls through the type-erased generic type still dispatch properly. Bridges are bytecode details managed by the compiler; one should not rely on manually creating bridges or assume every generic change is automatically protected by erasure.

## 7. Impact on Binary Compatibility

Source compatibility is the ability to recompile consumer source code. Binary compatibility is the ability for previously compiled bytecode to link against the new library version.

A JVM method descriptor includes parameter types and the return type. Therefore, changing parameter types or the return type can change the descriptor.

For example, an old binary was compiled to call:

```java
String getName()
```

the descriptor has a return type portion of `Ljava/lang/String;`. If the new library only has:

```java
CharSequence getName()
```

the new descriptor ends with `Ljava/lang/CharSequence;`. The old binary may fail to find the method descriptor it referenced and encounter `NoSuchMethodError`.

Similarly, changing the parameter `String` to `CharSequence` changes the descriptor from `(Ljava/lang/String;)V` to `(Ljava/lang/CharSequence;)V`. Even though source consumers passing `String` may still compile, old binary consumers still need the old method descriptor to link.

If the library needs to maintain binary compatibility, the common solution is to keep the old method and have it delegate to the new implementation:

```java
public void setName(String name) {
    setName((CharSequence) name);
}

public void setName(CharSequence name) {
    // New implementation.
}
```

For return types, Java source cannot declare two methods differing only in return type. Therefore, to preserve the old descriptor, one usually has to keep the old method and add a differently named method for the new API, or use a bytecode bridge mechanism controlled by specialized tools. One should not assume changing the return type is a safe change merely because source callers can be updated easily.

## 8. Designing APIs to Reduce Migration Risk

### 8.1. Keep Old Overloads During the Transition Period

If changing a parameter type while still being able to maintain semantics, keep the old overload and delegate:

```java
public void setName(String name) {
    setName((CharSequence) name);
}

public void setName(CharSequence name) {
    // Process according to the new contract.
}
```

The old overload can be marked deprecated so consumers migrate gradually. Remove it only in a major release with clear announcements and a migration guide.

### 8.2. Choose an Appropriate Abstraction from the Start

If a method only needs to read character contents, accepting `CharSequence` may be more appropriate than `String`. If data needs to be modified, a different abstraction or copying data into an internal type may be needed. Do not widen a parameter type if the implementation cannot properly support every implementation of that abstraction.

For collections, consider wildcards following the producer/consumer principle:

- Use `? extends T` when mainly reading values of type T from the collection.
- Use `? super T` when mainly writing values of type T into the collection.

This is a way to design more flexible generic APIs while maintaining type safety.

### 8.3. Avoid Unnecessary Overloads

Many closely related overloads can make calls with `null`, lambdas, or numeric literals unpredictable. If two behaviors differ significantly, separate method names can make call sites clearer.

### 8.4. Do Not Use Casts to Mask Contract Changes

Casting can make the compiler stop reporting errors but pushes failures to runtime. Before adding a cast, verify that the actual object always has the target type or add appropriate checks. For numeric narrowing, verify value bounds and handle overflow.

## 9. Process for Evaluating Type Changes During a Migration

1. **Lock the API baseline:** save the old artifacts, public API, generic signatures, and dependency versions.
2. **Find consumers:** identify every module, service, or application that calls the API, extends classes, or implements related interfaces.
3. **Compare declarations:** record changes to parameters, return types, generic bounds, checked exceptions, visibility, and overloads.
4. **Recompile consumers:** compile all consumer source code against the new library to detect type and overload errors.
5. **Verify binaries:** if released binaries need to be supported, run old consumers against the new library or use binary compatibility analysis tools.
6. **Verify behavior:** test overload dispatch, null, boxing/unboxing, numeric boundaries, generic collections, serialization, and exceptions.
7. **Maintain transition paths:** keep adapters/overloads or release a major version with a migration guide when the old contract cannot be maintained.
8. **Record decisions:** document the reason for the type change, affected consumers, removal version of the old API, and support timeline.

### 9.1. Finding Call Sites and Overrides

Searching by API name is the first step, but it is also necessary to check:

- Subclasses that `@Override` that method.
- Interface implementations in other modules.
- Method references such as `service::getValue` or `service::setValue`.
- Lambdas and generic helpers whose type inference depends on the return type.
- Call sites passing `null`, numeric literals, wrappers, or generic collections.
- Reflection invoking methods by name and parameter types.

Source search cannot always find dynamically created relationships. For public libraries, consumers outside the repository need to be considered if the entire ecosystem is not controlled.

### 9.2. Supporting Tools

`javap -s` displays method descriptors in bytecode:

```bash
javap -classpath old-library.jar -s com.example.NameService
javap -classpath new-library.jar -s com.example.NameService
```

Comparing outputs helps identify descriptor changes. `javap -v` can additionally show generic signatures, flags, and bridge methods.

API/binary compatibility analysis tools such as japicmp or Revapi can help detect public API changes between two artifacts. Module scope, filters, and policies must be configured properly because tools do not automatically know which contracts were intentionally changed.

For source compatibility, the most direct check remains recompiling representative consumers against the new API. For binary compatibility, previously compiled artifacts need to be tested. For behavioral compatibility, tests need to be run across key input cases and business flows.

## 10. Comprehensive Example: Type Changes Can Affect Multiple Layers

Suppose the old library:

```java
public class ReportService {
    public String format(int count) {
        return "count=" + count;
    }
}
```

Consumer:

```java
ReportService service = new ReportService();
String text = service.format(10);
```

In the new version, the library changes the parameter to `long` and the return type to `CharSequence`:

```java
public class ReportService {
    public CharSequence format(long count) {
        return "count=" + count;
    }
}
```

The call `service.format(10)` can still find the method thanks to widening from `int` to `long`. However, assigning the result to `String` is no longer valid because the return type is `CharSequence`.

Even when updating the consumer:

```java
CharSequence text = service.format(10);
```

the old binary still references the descriptor with an `int` parameter and `String` return type. If the library releases only the new method, the old binary may encounter `NoSuchMethodError`. If `ReportService` is subclassed in the consumer, the old overriding method also needs to be updated.

A transitional design can keep the old API:

```java
public class ReportService {
    @Deprecated(since = "2.0", forRemoval = true)
    public String format(int count) {
        return format((long) count).toString();
    }

    public CharSequence format(long count) {
        return "count=" + count;
    }
}
```

The code snippet illustrates keeping the old method so consumers have time to transition. In an actual library, it is necessary to confirm that converting from `int` to `long` and `CharSequence` to `String` preserves the same semantics, null handling, and performance according to the old contract.

## 11. Checklist for API Type Changes

- [ ] Recorded method signatures and descriptors before/after the change.
- [ ] Checked all call sites and static types of arguments.
- [ ] Reviewed subclass overrides and interface implementations.
- [ ] Examined primitive widening/narrowing and risk of data loss.
- [ ] Checked boxing/unboxing, especially with `null`.
- [ ] Checked generic invariance, wildcards, erasure, and name clashes.
- [ ] Evaluated overload resolution with literals, `null`, lambdas, and method references.
- [ ] Checked return types in assignments, chaining, and generic inference.
- [ ] Determined source compatibility and binary compatibility separately.
- [ ] Recompiled consumers and ran old binaries if compatibility is required.
- [ ] Tested behavior, boundary values, exceptions, and serialization.
- [ ] Provided adapters/deprecation/migration guides if the old API needs a transition period.

## 12. Conclusion

Changing parameter types and return types can affect call sites, overrides, overloads, generic inference, and method descriptors. Java's automatic conversions such as widening, boxing, and unboxing help some source code continue to compile, but do not guarantee unchanged behavior. Narrowing, generic invariance, overload ambiguity, and null are often points prone to errors.

When changing an API in Java Compatibility Migration, check both consumer source code and already-released binaries, examine type conversion rules at each call site, and keep adapters or old overloads when a transition period is needed. Only confirm the migration after compilation, binary linking, and behavioral testing all satisfy the published contract.