# `Class.isSealed()` and `Class.getPermittedSubclasses()` in Java 17

## 1. What can reflection tell us about a `sealed` type?

Java 17 adds two methods to `java.lang.Class` so that a program can inspect information about **sealed classes** and **sealed interfaces** at runtime:

- `Class.isSealed()` indicates whether the type represented by the `Class` object is a `sealed` type.
- `Class.getPermittedSubclasses()` returns `Class<?>` objects representing the classes or interfaces **directly permitted** to extend or implement that type.

These two methods are useful when building type-structure inspection tools, frameworks, test suites, data converters, or inheritance-tree display utilities. Instead of parsing type names from source code, a program can query the JVM for the metadata of a loaded type.

Simple example:

~~~java
Class<?> type = PaymentResult.class;

System.out.println(type.isSealed());

Class<?>[] permitted = type.getPermittedSubclasses();
for (Class<?> child : permitted) {
    System.out.println(child.getName());
}
~~~

If `PaymentResult` is a valid `sealed` interface, the program can discover its permitted direct subtypes. The result consists of `Class<?>` objects, so you can continue inspecting each subtype's name, package, module, superclass, interfaces, and `sealed` status.

**Version note:** both APIs have existed since Java 17 and are stable APIs. They do not require `--enable-preview`. This lesson only uses current APIs in Java SE 17.

## 2. What is a `Class<?>` object?

Reflection in Java works with `Class` objects representing a type that exists in the application. Such an object can be obtained from a class literal:

~~~java
Class<String> stringType = String.class;
Class<Integer> integerType = Integer.class;
Class<?> unknownType = String.class;
~~~

`Class<?>` is commonly used when the exact type is only known at runtime. The `?` indicates that we know this is a `Class` object without asserting its specific type parameter.

Some ways to obtain a class token:

| Syntax | Meaning |
|---|---|
| `PaymentResult.class` | Obtains the class token from a type name known at compile time. |
| `object.getClass()` | Obtains the actual runtime type of an existing object. |
| `Class.forName(name)` | Finds and loads a type by name; this overload may initialize the class. |
| `Class.forName(name, false, loader)` | Loads a type using the specified class loader without requiring class initialization. |

When you know the type you want to inspect, prefer a class literal because it is concise, type-safe, and avoids manual name handling. For example, to inspect the `PaymentResult` contract, use `PaymentResult.class` instead of calling `getClass()` on a specific instance.

### 2.1. An object's declared type and runtime type can differ

~~~java
PaymentResult result = new Approved("TX-17");

System.out.println(PaymentResult.class.isSealed());
System.out.println(result.getClass().isSealed());
~~~

The first line inspects the **root interface** `PaymentResult`. The second line inspects the **actual class** `Approved`. If `Approved` is a record, it is implicitly `final`, not a `sealed` type; therefore, the two results can differ.

When the goal is to see which types a hierarchy permits, start from the class token of the `sealed` supertype. If you only call `object.getClass()`, you might be inspecting a `final` leaf type and get `false` even though the interface it implements is `sealed`.

## 3. `Class.isSealed()`

Signature:

~~~java
public boolean isSealed()
~~~

The method returns:

- `true` if the `Class` object represents a class or interface declared as `sealed`.
- `false` if that type is not sealed.

According to the Java SE 17 API, the result is also `false` for primitive types, `void`, and array types.

Example:

~~~java
System.out.println(String.class.isSealed());      // false
System.out.println(int.class.isSealed());         // false
System.out.println(void.class.isSealed());        // false
System.out.println(String[].class.isSealed());    // false
~~~

With a hierarchy:

~~~java
sealed interface PaymentResult
        permits Approved, Declined, Pending {
}

record Approved(String reference) implements PaymentResult {
}

record Declined(String reason) implements PaymentResult {
}

record Pending(int queuePosition) implements PaymentResult {
}
~~~

`PaymentResult.class.isSealed()` returns `true`. The records `Approved`, `Declined`, and `Pending` are permitted direct subtypes, but they themselves are not `sealed` types; records are implicitly `final`.

### 3.1. `sealed` is different from `final`

`isSealed()` does not return `true` merely because a class cannot be subclassed. For example:

~~~java
final class Token {
}

sealed class Credential permits ApiCredential {
}

final class ApiCredential extends Credential {
}
~~~

| Type | `isSealed()` | Explanation |
|---|---:|---|
| `Token` | `false` | `final` prevents all subclasses; it has no permitted subclass list. |
| `Credential` | `true` | `sealed` and has one permitted direct subclass. |
| `ApiCredential` | `false` | The subclass is `final`, not `sealed`. |

A `non-sealed` class also has `isSealed() == false`. It opens up the inheritance branch so other types can continue extending it according to normal Java rules.

### 3.2. Do not check `sealed` with `Modifier.isSealed()`

`java.lang.reflect.Modifier` provides methods to check modifiers such as `public`, `abstract`, `final`, `static`, `native`, and several others. Java 17 **does not have** `Modifier.isSealed()` or a `Modifier.SEALED` flag to check for sealed types.

Call directly:

~~~java
boolean sealed = PaymentResult.class.isSealed();
~~~

You should not try to infer sealed status by parsing the string returned by `Modifier.toString(type.getModifiers())`. The dedicated `Class.isSealed()` API is the right and clear approach.

## 4. `Class.getPermittedSubclasses()`

Signature:

~~~java
public Class<?>[] getPermittedSubclasses()
~~~

The method returns a `Class<?>[]` array representing the **direct subclasses** or **direct subinterfaces** permitted to extend or implement the current class or interface.

There are three important points:

1. It only returns **direct** subtypes, not all descendants at deeper levels.
2. The order of elements in the array is **not guaranteed**.
3. If the type is not `sealed`, the method returns `null`; if the type is `sealed` but has no permitted subclasses, the method returns an empty array.

Example:

~~~java
Class<?>[] children = PaymentResult.class.getPermittedSubclasses();

for (Class<?> child : children) {
    System.out.println(child.getSimpleName());
}
~~~

With the `PaymentResult` hierarchy above, the array contains the class tokens corresponding to `Approved`, `Declined`, and `Pending`. There is no guarantee that the order will always be Approved, Declined, Pending.

### 4.1. Distinguishing `null` and an empty array

This is a distinction that must be handled accurately:

| Inspected type | `isSealed()` | `getPermittedSubclasses()` |
|---|---:|---|
| A regular class | `false` | `null` |
| A regular interface | `false` | `null` |
| A `sealed` class/interface with permitted subtypes | `true` | Array of class tokens. |
| A `sealed` class/interface with an empty permitted list in metadata | `true` | Empty array. |
| Primitive type, `void`, or array | `false` | `null` |

Therefore, you must not assume `getPermittedSubclasses()` always returns a non-null array:

~~~java
Class<?>[] children = String.class.getPermittedSubclasses();

// Error: children is null because String is not sealed.
// System.out.println(children.length);
~~~

The safe approach is to check `isSealed()` first, or check for `null` directly:

~~~java
static void printPermitted(Class<?> type) {
    if (!type.isSealed()) {
        System.out.println(type.getName() + " is not sealed");
        return;
    }

    Class<?>[] permitted = type.getPermittedSubclasses();
    System.out.println(type.getName()
            + " has " + permitted.length + " permitted direct type(s)");
}
~~~

By the API contract, if `isSealed()` returns `true`, then `getPermittedSubclasses()` returns a non-null array, which may be empty.

### 4.2. Only direct subtypes

Consider the inheritance tree:

~~~java
sealed class Document
        permits TextDocument, MediaDocument {
}

final class TextDocument extends Document {
}

sealed class MediaDocument extends Document
        permits ImageDocument {
}

final class ImageDocument extends MediaDocument {
}
~~~

When calling:

~~~java
Document.class.getPermittedSubclasses()
~~~

the result only includes `TextDocument` and `MediaDocument`. `ImageDocument` is not a direct subtype of `Document`; it directly extends `MediaDocument`.

To see the next level, you must continue inspecting `MediaDocument.class`:

~~~java
MediaDocument.class.getPermittedSubclasses()
~~~

the result includes `ImageDocument`. The API does not automatically flatten the entire inheritance tree.

## 5. Complete example: inspecting and printing a sealed tree

We build a program with:

- `Shape` as the root sealed interface.
- `Circle` as a record, hence final.
- `Polygon` as a non-sealed branch, which can be further extended.
- `Rectangle` as another sealed branch, with subtype `FilledRectangle`.

Create `SealedReflectionDemo.java`:

~~~java
import java.util.Arrays;

public final class SealedReflectionDemo {
    private SealedReflectionDemo() {
    }

    public sealed interface Shape
            permits Circle, Polygon, Rectangle {
    }

    public record Circle(double radius) implements Shape {
    }

    public non-sealed static class Polygon implements Shape {
    }

    public sealed static class Rectangle implements Shape
            permits FilledRectangle {
    }

    public static final class FilledRectangle extends Rectangle {
    }

    private static void printSealedTree(
            Class<?> type, String indentation) {

        System.out.println(indentation + type.getSimpleName()
                + (type.isSealed() ? " [sealed]" : ""));

        Class<?>[] permitted = type.getPermittedSubclasses();
        if (permitted == null) {
            return;
        }

        Arrays.stream(permitted)
                .sorted((left, right) ->
                        left.getName().compareTo(right.getName()))
                .forEach(child ->
                        printSealedTree(child, indentation + "  "));
    }

    public static void main(String[] args) {
        System.out.println("Shape is sealed: "
                + Shape.class.isSealed());
        System.out.println();

        printSealedTree(Shape.class, "");
        System.out.println();

        System.out.println("Polygon is sealed: "
                + Polygon.class.isSealed());
        System.out.println("Circle is sealed: "
                + Circle.class.isSealed());
        System.out.println("Rectangle is sealed: "
                + Rectangle.class.isSealed());
    }
}
~~~

Compile and run with JDK 17:

~~~text
javac --release 17 -encoding UTF-8 SealedReflectionDemo.java
java SealedReflectionDemo
~~~

The output looks like:

~~~text
Shape is sealed: true

Shape [sealed]
  Circle
  Polygon
  Rectangle [sealed]
    FilledRectangle

Polygon is sealed: false
Circle is sealed: false
Rectangle is sealed: true
~~~

The example uses `Arrays.stream` and sorts by name so the display output is deterministic. Sorting is only for readable output; the underlying API does not guarantee array order.

### 5.1. Why doesn't the tree show every subclass?

`Polygon` is declared `non-sealed`. When the program inspects `Polygon.class`:

- `isSealed()` returns `false`.
- `getPermittedSubclasses()` returns `null`.
- The recursive function stops there.

This matches the design: the `Polygon` branch is open to other subtypes, so the API cannot provide a closed list of all future subclasses.

`Rectangle`, on the other hand, is sealed, so the program can continue retrieving `FilledRectangle`. `Circle` is a final record, so it also has no subtree to traverse.

## 6. Recursively traversing a multi-level hierarchy

A tree traversal function typically has the structure:

1. Print the current type.
2. Check `isSealed()`.
3. If not sealed, stop the branch.
4. If sealed, call `getPermittedSubclasses()`.
5. Continue traversing each direct subtype.

It can be written explicitly:

~~~java
static void inspect(Class<?> type) {
    System.out.println("Type: " + type.getName());

    if (!type.isSealed()) {
        System.out.println("  No permitted-subclass list");
        return;
    }

    Class<?>[] children = type.getPermittedSubclasses();

    if (children.length == 0) {
        System.out.println("  No permitted direct subclasses");
        return;
    }

    for (Class<?> child : children) {
        System.out.println("  Permitted: " + child.getName());
    }
}
~~~

If you want to build a multi-level tree, call the function recursively for each element. In a valid hierarchy, inheritance edges do not form cycles; however, general-purpose tools can still use a `Set<Class<?>>` to avoid duplicate processing when the same interface appears across multiple branches or when combining multiple roots.

### 6.1. Stopping at a `non-sealed` branch

Reflection can only list the closed set of a sealed type. When encountering a permitted subclass declared `non-sealed`, that branch can be extended by other types without updating the ancestor's `permits` list.

Example:

~~~java
sealed interface Event permits Completed, Retryable {
}

record Completed() implements Event {
}

non-sealed class Retryable implements Event {
}

final class NetworkRetry extends Retryable {
}

final class DatabaseRetry extends Retryable {
}
~~~

`Event.class.getPermittedSubclasses()` returns `Completed` and `Retryable`. It does not return `NetworkRetry` or `DatabaseRetry`, because those two classes are descendants of the open `Retryable` branch rather than direct subtypes of `Event`.

`Retryable.class.isSealed()` is `false`, and `Retryable.class.getPermittedSubclasses()` is `null`. There is no way to use these two APIs to list every class that might appear under a non-sealed branch.

## 7. Bytecode metadata: the `PermittedSubclasses` attribute

The two reflection APIs read information from class file metadata. According to the JVM Specification, a class file for a sealed class or interface contains the attribute:

~~~text
PermittedSubclasses
~~~

This attribute records the type names permitted to **directly** extend or implement the current type. The JVM uses this metadata when creating or loading a type with a corresponding inheritance relationship to verify whether it is in the permitted set.

Notable points:

- In the class file, there is no separate access flag named `ACC_SEALED` equivalent to `ACC_FINAL`.
- The presence of the `PermittedSubclasses` attribute represents a sealed type at the class-file level.
- A `final` class has the `ACC_FINAL` flag and does not have the `PermittedSubclasses` attribute.
- `Class.isSealed()` and `Class.getPermittedSubclasses()` reflection provide a way to read this metadata through a high-level Java API.

You can inspect the bytecode using the `javap` tool in the JDK:

~~~text
javap -v -classpath out SealedReflectionDemo$Shape
~~~

When running in a shell, quote the class name containing `$` appropriately for your shell to avoid environment variable expansion. In the verbose output, look for the `PermittedSubclasses:` section.

There is no need to parse class files manually in normal applications. Use `Class` reflection to read the information; `javap -v` is suitable when studying bytecode or investigating metadata.

## 8. Reflection does not equal member access permission

`getPermittedSubclasses()` returns `Class<?>` objects describing the permitted subtypes. It **does not**:

- Instantiate the subtype.
- Invoke constructors.
- Read or write private fields.
- Grant access to private methods.
- Bypass module or package boundaries.

For example, after obtaining:

~~~java
Class<?>[] permitted = PaymentResult.class.getPermittedSubclasses();
~~~

you can call type-descriptive methods such as:

~~~java
for (Class<?> child : permitted) {
    System.out.println(child.getName());
    System.out.println(child.getPackageName());
    System.out.println(child.getModule().getName());
    System.out.println(child.isInterface());
    System.out.println(child.isRecord());
}
~~~

These operations only read type-descriptive information. If you want to invoke constructors or reflectively access members, you must follow Java access rules and the corresponding module boundaries. You do not need `setAccessible(true)` just to inspect the list of permitted subclasses.

### 8.1. `getPermittedSubclasses()` does not replace `getDeclaredClasses()`

The two methods answer two different questions:

| API | Question |
|---|---|
| `getPermittedSubclasses()` | Which direct subclasses/subinterfaces are permitted to extend/implement this sealed type? |
| `getDeclaredClasses()` | Which classes/interfaces are declared as member types inside this class/interface? |

A permitted subtype can be a top-level class in the same package or module, not necessarily a nested class. Conversely, a nested class may have nothing to do with the `permits` list.

Therefore, do not use `getDeclaredClasses()` as a substitute for `getPermittedSubclasses()` when the goal is to inspect a sealed hierarchy.

## 9. Type names, class loaders, and modules

`getPermittedSubclasses()` returns loaded class tokens, not a plain list of name strings. This has several implications when working with multi-module or multi-class-loader applications.

### 9.1. Use class tokens instead of string name comparisons

Prefer:

~~~java
if (child == Approved.class) {
    // Same Class object.
}
~~~

Do not rely solely on:

~~~java
if (child.getName().equals("example.Approved")) {
    // Name comparison only.
}
~~~

Two classes with the same binary name but defined by two different class loaders can still be two distinct runtime types. Comparing `Class` objects preserves type identity.

### 9.2. Class loader used to load subtypes

When `getPermittedSubclasses()` is called, Java attempts to obtain the class token for each type recorded in metadata using the **defining class loader of the current class/interface**.

If a permitted type cannot be loaded as a `Class` object, the API specifies that the type is omitted from the returned array. Thus, in dynamic deployment environments or with custom class loaders, the returned array might not include every name recorded in metadata.

This is why you should treat the reflection result as **the subtypes that the runtime can resolve**, and pay attention to class loader configuration when building plugin systems or frameworks.

### 9.3. Package and module constraints of a sealed hierarchy

At the Java language level:

- If the sealed type is in a **named module**, the permitted direct subtypes must be in the same module.
- If the sealed type is in an **unnamed module**, the permitted direct subtypes must be in the same package.

These constraints keep the sealed hierarchy managed within the same module or package boundary. When reflection reveals subtypes, you can inspect:

~~~java
System.out.println(type.getModule());
System.out.println(child.getModule());
System.out.println(type.getPackageName());
System.out.println(child.getPackageName());
~~~

This information is useful for diagnosing module/package configuration. In modular applications, check the module descriptor and class packaging rather than relying only on package names.

## 10. Distinguishing direct subtypes using other reflection APIs

`getPermittedSubclasses()` already returns direct subtypes per the API contract. To understand the difference between direct and indirect relationships, you can look at:

- `getSuperclass()`: the direct superclass of a class.
- `getInterfaces()`: the interfaces directly implemented or extended by a class or interface.

Example:

~~~java
sealed interface Result permits Success, Failure {
}

sealed interface Success extends Result permits CachedSuccess {
}

record CachedSuccess(String value) implements Success {
}

record Failure(String message) implements Result {
}
~~~

With `Result.class.getPermittedSubclasses()`, the result is `Success` and `Failure`. `CachedSuccess` is not in this array because it directly implements `Success`.

You can check directly:

~~~java
System.out.println(CachedSuccess.class.getInterfaces()[0].getName());
~~~

The output shows that `CachedSuccess`'s direct interface is `Success`. For classes, `getSuperclass()` gives the direct superclass. Do not use `isAssignableFrom()` in place of checking a direct relationship, because that method also returns `true` for indirect inheritance relationships.

## 11. Building a utility to inspect a sealed type

A small utility can return the list of direct subtypes in a deterministic name order:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

static List<Class<?>> permittedTypesOf(Class<?> type) {
    if (!type.isSealed()) {
        throw new IllegalArgumentException(
                type.getName() + " is not sealed");
    }

    return Arrays.stream(type.getPermittedSubclasses())
            .sorted(Comparator.comparing(Class::getName))
            .toList();
}
~~~

`List.copyOf` or `Stream.toList()` can be used to create a read-only collection depending on the Java version. In Java 17, `Stream.toList()` is available and returns an unmodifiable list.

Usage example:

~~~java
permittedTypesOf(PaymentResult.class)
        .forEach(type ->
                System.out.println(type.getSimpleName()));
~~~

If you need to check whether a specific type belongs to the permitted list:

~~~java
static boolean isPermittedDirectly(
        Class<?> sealedType, Class<?> candidate) {

    if (!sealedType.isSealed()) {
        return false;
    }

    return Arrays.stream(sealedType.getPermittedSubclasses())
            .anyMatch(permitted -> permitted == candidate);
}
~~~

This snippet checks class token identity and only considers direct subtypes. It does not return `true` for a deeper-level descendant.

## 12. Limitations and edge cases

### 12.1. The returned array is not sorted

Do not write tests assuming the first element is always type A and the second element is always type B. If you need deterministic output for logs, UI, or snapshot tests, sort by `getName()` or `getCanonicalName()`.

### 12.2. Not every permitted class necessarily appears in the array

The API attempts to load each subtype using the defining class loader of the root type. If a class token cannot be loaded, that type is skipped. Therefore, the returned array reflects the types resolvable at runtime; in complex class-loader setups, do not treat it as a verbatim dump of every metadata name.

### 12.3. `null` does not mean "sealed with no children"

`null` means the type is not sealed (including primitives, void, and arrays). An empty array is the non-null value with zero elements. Keep these two cases separate in your logic.

### 12.4. A `non-sealed` branch cannot be exhaustively enumerated

When a permitted subclass is `non-sealed`, other types can extend it without being listed on the sealed ancestor. These two APIs can only continue traversing when the current node is also sealed.

### 12.5. There is no `isNonSealed()` API

Java 17 provides `isSealed()`, but does not have `Class.isNonSealed()`. `false` can mean a regular class/interface, a `final` type, or a `non-sealed` type. If the type is already known to be a valid direct permitted subclass, you can combine `isSealed()` with `Modifier.isFinal()` to interpret the leaf/branch status:

- `isSealed() == true`: the branch continues with its own permitted list.
- `isSealed() == false` and final modifier: the branch terminates.
- `isSealed() == false` and not final: for a valid direct permitted subtype, this is a `non-sealed` branch.

That is an inference based on a valid hierarchy context, not a separate `non-sealed` flag returned by reflection.

## 13. Practical applications

### 13.1. Hierarchy visualization tools

IDEs, internal documentation, or analysis tools can use these two APIs to present the direct options of a sealed type. Sorting results by name keeps the UI stable.

### 13.2. Model validation at startup

A framework can verify that a plugin interface only has the permitted direct implementations. Checks should rely on loaded class tokens and should not treat reflection as the sole input validation or security boundary.

### 13.3. Generating test cases per variant

When testing a function that takes a sealed type, you can inspect the permitted direct types to remind the team to add fixtures for each branch. If there are nested sealed branches, traverse recursively; if there is a non-sealed branch, you must test against the open branch's contract since you cannot enumerate all descendants.

### 13.4. Checking converter completeness

For example, a converter takes `PaymentResult` and needs to map each variant to a DTO. Reflection can help detect when the list of direct subtypes changes between versions. However, reflection does not prove each conversion branch is correct; behavior and expected-output tests are still required.

## 14. Practice exercises

### Exercise 1 — Checking sealed types

Create three types:

~~~java
sealed interface Message permits TextMessage, BinaryMessage {
}

record TextMessage(String text) implements Message {
}

record BinaryMessage(byte[] data) implements Message {
}
~~~

Write a program that prints the result of `isSealed()` for `Message.class`, `TextMessage.class`, `String.class`, and `int[].class`. Explain each result.

### Exercise 2 — Reading the direct permitted list

Use `Message.class.getPermittedSubclasses()` to print the full name of each type. Sort by name before printing. Try changing the order of types in `permits` and observe why you should not rely on array order.

### Exercise 3 — Distinguishing direct and indirect

~~~java
sealed interface Root permits Branch, Leaf {
}

sealed interface Branch extends Root permits Twig {
}

record Twig() implements Branch {
}

record Leaf() implements Root {
}
~~~

Determine the results of `Root.class.getPermittedSubclasses()` and `Branch.class.getPermittedSubclasses()`. Why does `Twig` not appear in `Root`'s list?

### Exercise 4 — Stopping at non-sealed

Add `non-sealed class OpenBranch implements Root` and a class `final class Extension extends OpenBranch`. Explain why `Extension` does not appear in the result of `Root.class.getPermittedSubclasses()` and why `OpenBranch.class.getPermittedSubclasses()` returns `null`.

### Exercise 5 — Distinguishing null and an empty array

Write a method taking `Class<?>`, checking `isSealed()`, and printing one of three states: not sealed, sealed with an empty list, or sealed with subtypes. Why must you check for `null` before reading `length`?

### Exercise 6 — Traversing a multi-level tree

Use the `Shape` hierarchy from section 5. Write a recursive function that prints each type with indentation by level, sorting child names. Ensure the `Polygon` branch does not cause a null error when calling `getPermittedSubclasses()`.

### Self-check hints

- Exercise 1: `Message` is sealed; the two records and `String` are not sealed; the array `int[]` is not sealed.
- Exercise 2: Get the array, use `Arrays.stream(...).sorted(...)`, then print `getName()`.
- Exercise 3: `Root` returns `Branch` and `Leaf`; `Branch` returns `Twig`.
- Exercise 4: `OpenBranch` is non-sealed so the API returns `null`; its descendants are not in `Root`'s direct list.
- Exercise 5: `null` indicates a non-sealed type; an empty array is the case of being sealed with no returned elements.
- Exercise 6: Check `isSealed()` or check the array for `null` before streaming.

## 15. Key principles to remember

- `Class.isSealed()` and `Class.getPermittedSubclasses()` have existed since Java 17 and can be used without preview.
- `isSealed()` checks the class/interface represented by the current class token; use the supertype's class token when checking a sealed contract.
- `getPermittedSubclasses()` returns `Class<?>[]` of the directly permitted subclasses/subinterfaces.
- Array order is not guaranteed; sort if deterministic output is needed.
- Non-sealed types return `null`; sealed types may return an empty array or an array containing subtypes.
- Reflection only reports direct subtypes; to inspect a multi-level tree you must traverse recursively.
- A `non-sealed` branch opens the hierarchy without a bounded list, so these two APIs cannot enumerate all descendants of that branch.
- `Class.isSealed()` is not `Modifier.isSealed()`; Java 17 has no separate modifier flag for sealed in `Modifier`.
- Class file metadata uses the `PermittedSubclasses` attribute; `javap -v` can help inspect bytecode.
- `getPermittedSubclasses()` attempts to load class tokens using the root type's defining class loader; unresolvable types are omitted.
- Both APIs only inspect type structure; they do not instantiate objects or grant access to private members.

### References

- [Java SE 17 API — Class.isSealed() and Class.getPermittedSubclasses()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
- [Java SE 17 Language Specification — Section 8.1.6: Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6).
- [Java SE 17 Language Specification — Section 9.1.4: Permitted Direct Subclasses and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4).
- [Java Virtual Machine Specification — Section 4.7.31: The PermittedSubclasses Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.31).
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409).
