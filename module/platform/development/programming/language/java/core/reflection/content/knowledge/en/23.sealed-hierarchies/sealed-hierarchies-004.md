# Unsealed Cases and Corresponding API Results

## 1. False Does Not Fully Describe Inheritability

When inspecting a type with Reflection, the question:

~~~java
type.isSealed()
~~~

only determines whether that type is a sealed class or interface.

If the result is `false`, you still cannot conclude that:

- The type was declared with the `non-sealed` keyword.
- The type can be freely inherited.
- The type has no subclasses.
- The type is an instantiable class.
- You can call `getPermittedSubclasses()` and use the result as a non-`null` array.

For instance, a `final` class is not sealed, yet also does not allow subclasses. An ordinary class that is neither `final` nor `sealed` can have many subclasses. Ordinary interfaces, records, arrays, and primitive tokens each have their own characteristics.

To understand properly, separate **sealed status**, **other inheritance rules**, and **the list of directly permitted subtypes**.

## 2. The Two APIs and the false/null Contract

The APIs on `Class<?>`:

~~~java
public boolean isSealed();
public Class<?>[] getPermittedSubclasses();
~~~

These are abbreviated signatures for illustration; both methods exist in Java 17 and later.

Key contract:

| Status of the inspected type | `isSealed()` | `getPermittedSubclasses()` |
| --- | --- | --- |
| Sealed class or interface | `true` | Non-`null` array, may be empty per API contract |
| Unsealed class or interface | `false` | `null` |
| Array, primitive, or `void` | `false` | `null` |

Therefore, for an unsealed type, **the API result is `null`, not an empty array**. This is normal behavior, not a type-loading failure just because the return value is `null`.

The documentation for [Class.isSealed](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#isSealed()) and [Class.getPermittedSubclasses](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()) states this distinction.

Reference points to remember:

~~~text
null
    -> the type under inspection is not sealed

non-null array
    -> the type under inspection is sealed
    -> read the elements to see the direct subtypes obtained by the API
~~~

Do not use `permitted.length == 0` alone as the check for "not sealed". With a `null` result, that expression will also throw `NullPointerException`.

## 3. "Not Sealed" Differs from the non-sealed Keyword

In everyday speech, "not sealed" means `isSealed() == false`. This is a broad category.

The `non-sealed` keyword has a specific meaning in the Java language: it is used on a direct branch of a sealed hierarchy to allow that branch to remain extensible without maintaining a `permits` list on that branch itself.

Example:

~~~java
sealed interface Root permits OpenBranch, End {
}

non-sealed class OpenBranch implements Root {
}

final class End implements Root {
}
~~~

This is a group of declarations that can be placed in the same file within the same package.

Both `OpenBranch.class.isSealed()` and `End.class.isSealed()` return `false`, yet:

- `OpenBranch` allows further subclassing under normal Java rules.
- `End` is a `final` class, so it has no subclasses.

An ordinary standalone class also yields `false` without ever being declared `non-sealed`.

Consequently, **do not rename the result `!type.isSealed()` to "has the non-sealed modifier"** in an analysis tool. The `Class` APIs used in Java 17/21 in this article do not provide an `isNonSealed()` method to read that literal keyword.

The rules for `sealed`, `final`, and `non-sealed` classes are described in [JLS §8.1.1.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2).

## 4. Complete Program: Comparing Unsealed Groups

Save the following program to `NotSealedApiDemo.java`:

~~~java
import java.lang.reflect.Modifier;
import java.util.Arrays;

public class NotSealedApiDemo {
    public sealed interface Root permits OpenBranch, OpenApi, End {
    }

    public static non-sealed class OpenBranch implements Root {
    }

    public non-sealed interface OpenApi extends Root {
    }

    public static final class End implements Root {
    }

    public static class Extension extends OpenBranch {
    }

    public static class Plain {
    }

    public static final class Closed {
    }

    public interface OrdinaryInterface {
    }

    public record Point(int x, int y) {
    }

    public enum Light {
        RED, GREEN
    }

    static void inspect(String label, Class<?> type) {
        Class<?>[] permitted = type.getPermittedSubclasses();
        String result = permitted == null ? "null"
                : Arrays.stream(permitted)
                        .map(Class::getSimpleName)
                        .sorted()
                        .toList()
                        .toString();
        System.out.println(label
                + " -> sealed=" + type.isSealed()
                + "; permitted=" + result);
    }

    public static void main(String[] args) {
        inspect("sealed root", Root.class);
        inspect("non-sealed class", OpenBranch.class);
        inspect("non-sealed interface", OpenApi.class);
        inspect("permitted final leaf", End.class);
        inspect("indirect extension", Extension.class);
        inspect("ordinary class", Plain.class);
        inspect("ordinary final class", Closed.class);
        inspect("ordinary interface", OrdinaryInterface.class);
        inspect("record", Point.class);
        inspect("enum without constant bodies", Light.class);
        inspect("String array", String[].class);
        inspect("sealed-root array", Root[].class);
        inspect("primitive int", int.class);
        inspect("void", void.class);

        System.out.println("Closed is final: "
                + Modifier.isFinal(Closed.class.getModifiers()));
        System.out.println("Plain is final: "
                + Modifier.isFinal(Plain.class.getModifiers()));
        System.out.println("Root accepts Extension: "
                + Root.class.isAssignableFrom(Extension.class));
        System.out.println("Extension is directly permitted by Root: "
                + Arrays.asList(Root.class.getPermittedSubclasses())
                        .contains(Extension.class));
    }
}
~~~

Compile and run with JDK 17 or later, no preview required:

~~~bash
javac --release 17 -encoding UTF-8 NotSealedApiDemo.java
java NotSealedApiDemo
~~~

Exact output:

~~~text
sealed root -> sealed=true; permitted=[End, OpenApi, OpenBranch]
non-sealed class -> sealed=false; permitted=null
non-sealed interface -> sealed=false; permitted=null
permitted final leaf -> sealed=false; permitted=null
indirect extension -> sealed=false; permitted=null
ordinary class -> sealed=false; permitted=null
ordinary final class -> sealed=false; permitted=null
ordinary interface -> sealed=false; permitted=null
record -> sealed=false; permitted=null
enum without constant bodies -> sealed=false; permitted=null
String array -> sealed=false; permitted=null
sealed-root array -> sealed=false; permitted=null
primitive int -> sealed=false; permitted=null
void -> sealed=false; permitted=null
Closed is final: true
Plain is final: false
Root accepts Extension: true
Extension is directly permitted by Root: false
~~~

`Root`'s permitted list is sorted by name when printed. The API does not promise element ordering; sorting makes the output stable.

### 4.1. Ordinary classes and final classes both yield false/null

The two lines:

~~~text
ordinary class -> sealed=false; permitted=null
ordinary final class -> sealed=false; permitted=null
~~~

have the same pair of sealed results, even though their inheritance characteristics differ.

If a tool wants to know whether a **class** has the `final` modifier, it must check the appropriate property such as `Modifier.isFinal(type.getModifiers())`. In the program, `Closed` is `final` while `Plain` is not `final`.

Do not infer "not sealed means open for inheritance" from a single boolean value. Inheritability also depends on type kind, `final`, accessibility, and other language rules.

### 4.2. Ordinary interfaces and non-sealed interfaces both yield false/null

`OrdinaryInterface` does not belong to any sealed declaration. `OpenApi` is a `non-sealed` interface directly extending `Root`.

The two interfaces have different declaration contexts, yet neither is sealed at the type itself, so `getPermittedSubclasses()` returns `null` for both.

`null` is not an empty list of classes currently implementing the interface. This API is not responsible for scanning all classes implementing an open interface.

### 4.3. A subtype of a sealed type is not necessarily sealed

`Root` being sealed does not make all of its descendants sealed.

In the program:

- `Root` has `isSealed() == true`.
- `OpenBranch`, `OpenApi`, and `End` all have `isSealed() == false`.
- Each API call queries the status of the exact class or interface token receiving the call.

If you need the parent's status, obtain the parent token itself. Do not expect `OpenBranch.class.getPermittedSubclasses()` to return the list declared in `Root`.

### 4.4. Real subclasses exist yet permitted is still null

`Extension` is a subclass of `OpenBranch`. However, `OpenBranch` is not sealed, so the permitted API still returns `null`.

The final two lines of the program also show:

~~~text
Root accepts Extension: true
Extension is directly permitted by Root: false
~~~

`Extension` is an indirect subtype of `Root`, via `OpenBranch`. It is not an element in the list of subtypes **directly** permitted by `Root`.

From `getPermittedSubclasses() == null`, you cannot infer "no subclasses exist". The API does not list all actual descendants or all loaded classes.

## 5. Record, enum, array, primitive, and void

### 5.1. Records are not sealed

A record is implicitly a `final` class. For `Point` in the program:

~~~text
record -> sealed=false; permitted=null
~~~

This is not an open branch of the hierarchy. Records do not allow subclassing, but that characteristic comes from being `final`, not from sealed status.

Even when a record implements a sealed interface and is permitted as a direct branch, the record itself remains `final` and does not become `sealed`.

### 5.2. Enums require checking declaration structure

The enum `Light` has no constants with their own class bodies. It is implicitly `final` and yields:

~~~text
enum without constant bodies -> sealed=false; permitted=null
~~~

However, do not generalize that all enums are unsealed. If at least one constant has its own class body, the enum class is implicitly sealed; the anonymous classes of the constant bodies are the permitted direct subclasses.

Therefore, "not seeing the word sealed in source code" is not sufficient to conclude `isSealed() == false`.

### 5.3. Arrays do not inherit the sealed status of their elements

Both tokens below represent array types:

~~~java
String[].class
Root[].class
~~~

Even though `Root.class.isSealed()` is `true`, `Root[].class.isSealed()` is still `false` and the array type's permitted list is `null`.

The relationship between an array and its element type is not a subclass relationship in a `permits` list. If you want to inspect the element type's status, call `getComponentType()` and query that token.

### 5.4. Primitives and void also have Class tokens

`int.class` and `void.class` are valid tokens on which to call both APIs. They return `false` and `null`, without throwing an error just for not being ordinary object classes.

That does not mean primitives or `void` are inheritable classes. Use queries such as `isPrimitive()`, `isArray()`, and `isInterface()` for classification.

Also distinguish the `void.class` token from a `Class<?>` variable holding `null`. A `null` reference variable is not a type token; calling a method on it will throw `NullPointerException`.

## 6. Comparison Experiment: Implicitly Sealed Enum

To avoid classifying solely by the presence of keywords in source code, create `ImplicitSealedEnumDemo.java`:

~~~java
import java.lang.reflect.Modifier;

public class ImplicitSealedEnumDemo {
    public enum Mode {
        NORMAL,
        SPECIAL {
            @Override
            public String toString() {
                return "special";
            }
        }
    }

    public static void main(String[] args) {
        Class<?>[] permitted = Mode.class.getPermittedSubclasses();
        Class<?> bodyClass = Mode.SPECIAL.getClass();

        System.out.println("enum is sealed: " + Mode.class.isSealed());
        System.out.println("permitted count: " + permitted.length);
        System.out.println("contains constant body class: "
                + java.util.Arrays.asList(permitted).contains(bodyClass));
        System.out.println("body class is final: "
                + Modifier.isFinal(bodyClass.getModifiers()));
        System.out.println("body class is sealed: " + bodyClass.isSealed());
        System.out.println("body permitted is null: "
                + (bodyClass.getPermittedSubclasses() == null));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 ImplicitSealedEnumDemo.java
java ImplicitSealedEnumDemo
~~~

Output:

~~~text
enum is sealed: true
permitted count: 1
contains constant body class: true
body class is final: true
body class is sealed: false
body permitted is null: true
~~~

Here:

- `Mode` is implicitly sealed because `SPECIAL` has its own class body.
- The actual runtime class of constant `SPECIAL` is a `final` subclass of `Mode`.
- When querying that subclass itself, the result is `false/null`.

The example clarifies that status is observed per **individual type token**, rather than propagating automatically from an enum to its constant's subclass or vice versa.

The implicit `final` or `sealed` rules for enums are in [JLS §8.9](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.9).

## 7. Null and Empty Arrays Cannot Be Swapped Arbitrarily

An error-prone snippet is:

~~~java
// Illustrates an unchecked call; may throw NullPointerException.
for (Class<?> child : type.getPermittedSubclasses()) {
    System.out.println(child.getName());
}
~~~

The snippet above is only safe when `type` is already known to be sealed and the API call completes normally. If `type` is an ordinary class, the `null` result causes the loop to fail.

There are two ways to handle this depending on the tool's contract.

### 7.1. Process only sealed types

You can check the status first:

~~~java
// Illustrative snippet inside a method, with non-null type.
if (type.isSealed()) {
    for (Class<?> child : type.getPermittedSubclasses()) {
        System.out.println(child.getName());
    }
} else {
    System.out.println("NOT_SEALED");
}
~~~

The `else` branch indicates that the permitted-list API does not apply in the same way as to a sealed type. It does not say whether the type has descendants.

### 7.2. Normalize for convenience while preserving the status flag

If a presentation layer wants a non-`null` list at all times, preserve the sealed status separately.

For example, the supporting declarations below are placed inside a class; import `java.util.Arrays`, `java.util.List`, and `java.util.Objects`:

~~~java
record SealedInfo(boolean sealed, List<Class<?>> permitted) {
}

static SealedInfo inspectSealing(Class<?> type) {
    Objects.requireNonNull(type, "type");

    Class<?>[] permitted = type.getPermittedSubclasses();
    List<Class<?>> children = permitted == null
            ? List.of()
            : List.copyOf(Arrays.asList(permitted));

    return new SealedInfo(type.isSealed(), children);
}
~~~

Illustrative calls inside the first program:

~~~java
SealedInfo root = inspectSealing(Root.class);
SealedInfo open = inspectSealing(OpenBranch.class);
SealedInfo closed = inspectSealing(Closed.class);

System.out.println(root.sealed() + "/" + root.permitted().size());
System.out.println(open.sealed() + "/" + open.permitted().size());
System.out.println(closed.sealed() + "/" + closed.permitted().size());
~~~

Output of just the call snippet:

~~~text
true/3
false/0
false/0
~~~

The empty normalized lists for `open` and `closed` are **a convention of the helper function**, not the raw return value of `Class.getPermittedSubclasses()`.

Keeping the `sealed` flag avoids losing the difference between "not sealed" and "sealed where the API returned a list with no elements". If the tool also needs to distinguish `final` or other token kinds, add the exact classification information needed.

## 8. Why Does the API Still Allow an Empty Array for a Sealed Type?

Ordinary Java `sealed` declarations must satisfy the rules for permitted subtypes. You should not infer from Reflection's wording "the array may be empty" that a Java author can arbitrarily declare a sealed class with no valid branches.

At the API level, `getPermittedSubclasses()` attempts to obtain the `Class` objects recorded in metadata and includes in the result only those types it obtains that satisfy the direct relationship. If a corresponding `Class` object cannot be obtained, that entry may be omitted per the method contract.

Therefore, in incomplete class-loading or packaging environments, the observed element count should not be treated as an absolute inventory of every name in class-file metadata.

The distinction remains:

- `null`: the type is not sealed.
- Non-`null` empty array: the type is sealed, yet no elements were returned in that query.

Do not classify sealed status solely by checking element count. Also do not call a `non-sealed` branch "sealed with an empty list".

## 9. Do Not Infer Status from Modifier Strings or Class Names

In class files, sealing is represented by the `PermittedSubclasses` attribute, not an `ACC_SEALED` flag analogous to `ACC_FINAL`. This is described in [JVMS §4.7.31](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.31).

Therefore, tools should use `Class.isSealed()`, rather than searching for the word `sealed` in the string produced by `Modifier.toString(...)`.

Similarly, class names, whether a class is nested or top-level, or having a sealed superclass do not replace querying the exact status on the current token.

`getDeclaredClasses()` also does not replace `getPermittedSubclasses()`: one API inspects declared member classes, while the other inspects direct branches permitted by sealing. A subclass may be declared elsewhere, and a member class is not necessarily a subclass.

When encountering an unsealed type, if a tool needs to find all actual subclasses, that is a separate type-discovery problem. A `null` result does not provide a list of those classes.

## 10. Self-Check

1. A `final` class gives `isSealed() == false`. Does `getPermittedSubclasses()` return an empty array or `null`?
2. Can you conclude a class has the `non-sealed` keyword solely from `!type.isSealed()`?
3. `OpenBranch` has subclass `Extension`. Why is `OpenBranch`'s permitted list still `null`?
4. If `Root` is sealed, does `Root[].class.isSealed()` automatically return `true`?
5. Must an enum without the `sealed` keyword in source code necessarily return `isSealed() == false`?
6. Why should you not use `getPermittedSubclasses().length == 0` to detect an unsealed type?
7. Must an indirect subtype of a sealed root necessarily be present in the root's permitted list?
8. When a helper normalizes `null` into an empty list, why should the `sealed` flag be kept separately?

Answers:

1. It returns `null`.
2. No. Many other types such as `final` classes, ordinary classes, ordinary interfaces, and records also return `false`.
3. It is not sealed; the API is not responsible for listing actual subclasses of an open branch.
4. No. Array types return `false`; the element token and the array token are two different types.
5. No. An enum with a constant having its own class body is implicitly sealed.
6. For unsealed types, the result is `null` and accessing `length` throws an error; a non-`null` empty array also has a different API meaning.
7. No. The list only describes the directly permitted subtypes obtained by the API.
8. To preserve the distinction between an unsealed state and a sealed state whose returned list is empty.
