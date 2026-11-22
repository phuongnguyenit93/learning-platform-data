# Syntactic Positions Where Wildcards Are Disallowed in Java Generics

## 1. Learning objectives

The question mark `?` in Java Generics is a **wildcard type argument**: it denotes an unknown exact type argument, for example `List<?>`. A wildcard is not the name of an independent type, does not declare a new type variable, and cannot replace `T` in every position.

This lesson focuses on **syntactic positions or type contexts where Java disallows wildcards**, how to read error messages, and how to replace them properly. The focus is on the unbounded wildcard `?`; where necessary, the lesson also compares with `? extends T` and `? super T` to prevent wrong inferences.

After this lesson, you will be able to:

- Distinguish declaring a type parameter (`<T>`) from using a wildcard type argument (`<?>`).
- Recognize positions that forbid wildcards in declarations, inheritance, object instantiation, and generic calls.
- Understand contexts that *only* allow unbounded wildcards, especially `instanceof` and generic array creation.
- Choose the appropriate fix using a concrete type, `<T>`, diamond `<>`, or a `List<?>` reference depending on purpose.
- Distinguish **syntax/context** errors from **unsafe operation on a wildcard** errors.

## 2. Foundational rule: a wildcard is a type argument, not a type parameter

Look at two different concepts:

```java
class Box<T> {             // T is a type parameter: the declared type variable name.
    private final T value;
    Box(T value) { this.value = value; }
    T get() { return value; }
}

Box<String> named = new Box<>("Java"); // String is a concrete type argument.
Box<?> unknown = named;                 // ? is a valid wildcard type argument.
```

`Box<T>` defines a new generic type with name `T`. In `Box<?>`, `?` does not define a parameter: it only states that the actual argument of the `Box` object has some type, yet the current reference does not know that type.

General syntax:

```text
Declaring a generic type/method:
  class Box<T> { ... }
  static <T> T identity(T value) { ... }

Using a generic type:
  Box<String> b1;      // Concrete type argument.
  Box<?> b2;           // Unbounded wildcard.
  Box<? extends Number> b3;  // Upper-bounded wildcard.
  Box<? super Integer> b4;   // Lower-bounded wildcard.
```

**Quick rule of thumb:** If a place requires a **type name or type parameter name** so the program can refer back to it, `?` cannot replace that name. When a place requires a **type argument of a parameterized generic type**, a wildcard may be valid, though still subject to the contextual restrictions presented below.

## 3. Cannot use `?` to declare a type parameter

### 3.1. Class, interface, record, and generic method declarations

The following declarations are invalid:

```java
// class Box<?> { }                        // WRONG
// interface Repository<?> { }             // WRONG
// record Pair<?>(Object left, Object right) { }  // WRONG
// static <?> void print(Object value) { }  // WRONG
```

A declaration's type parameter list must have an identifier such as `T`, `E`, `K`, `V`, or another valid name. `?` is not an identifier and cannot serve as a type parameter.

How to fix:

```java
class Box<T> {
    T value;
}

interface Repository<E> {
    E find();
}

record Pair<T>(T left, T right) {}

class GenericMethods {
    static <T> T identity(T value) {
        return value;
    }
}
```

These are illustrative declarations, not a program with `main`. A wildcard can still **appear inside a parameter type or return type** of a method, such as `void print(List<?> values)`; what is forbidden is using `?` **as a type parameter name**.

### 3.2. Cannot write `?` standalone as a variable type or return type

```java
// ? item;                    // WRONG
// static ? first() { ... }   // WRONG
// void accept(? value) { }   // WRONG
// ?[] elements;              // WRONG
```

`?` is not a standalone type name. Wrap it inside a generic type in a position that allows a type argument:

```java
Object item;
List<?> elements;

static Object first(List<?> values) {
    return values.get(0);
}

static void accept(List<?> values) {
    System.out.println(values.size());
}
```

Note: `List<?>` is **a usable type in a signature**, whereas `?` by itself is not.

### 3.3. Cannot place `?` standalone after `extends` in a type parameter declaration

```java
// class NumberBox<T extends ?> { }  // WRONG: ? is not a type usable as a bound.
```

When you want to constrain `T` to be a numeric type:

```java
class NumberBox<T extends Number> { }
```

Meanwhile, a wildcard can completely appear **inside a type used as a bound**:

```java
class HasComparable<T extends Comparable<?>> { }
```

This is an important distinction: `Comparable<?>` is a valid parameterized type in a bound clause; the standalone `?` right after `extends` is not a valid type.

Similarly, `<T super Number>` is not valid syntax for declaring a lower bound on a type parameter. The `super` keyword for expressing a lower bound is part of a wildcard type argument, for example `List<? super Number>`.

## 4. Do not use wildcards in a direct superclass or superinterface

When defining a class or interface with an inheritance relationship, the direct generic type part in `extends`/`implements` **cannot contain wildcards**.

Invalid examples:

```java
class Parent<T> { }

interface Handler<T> {
    void handle(T value);
}

// class Child extends Parent<?> { }   // WRONG
// class X implements Handler<?> {      // WRONG
//     public void handle(Object x) {}
// }
// interface ChildHandler extends Handler<?> { }  // WRONG
```

When performing inheritance, Java needs an appropriate parameterization to define the inherited member contract. A wildcard expresses an unknown argument at a **reference use site**, not a suitable argument for a declared direct supertype relationship.

Correct alternatives:

```java
class StringChild extends Parent<String> { }

class GenericChild<T> extends Parent<T> { }

class StringHandler implements Handler<String> {
    @Override
    public void handle(String value) {
        System.out.println(value);
    }
}

interface GenericHandler<T> extends Handler<T> { }
```

You **can still declare a variable** `Parent<?>` to reference `Parent<String>` or `Parent<Integer>`:

```java
Parent<?> view = new StringChild(); // VALID.
```

The issue lies in the `extends/implements` position of the type declaration; not all uses of `Parent<?>` are forbidden.

## 5. Do not use a wildcard as a type argument in a `new` object creation expression

Distinguish the **reference type on the left** from the **object type to instantiate on the right**:

```java
List<?> view = new ArrayList<String>();  // VALID
List<?> inferred = new ArrayList<>();     // VALID: diamond
// List<?> wrong = new ArrayList<?>();    // WRONG
```

With an object creation expression `new ArrayList<...>()`, the type to instantiate must be specified with concrete type arguments or left for the compiler to infer via `<>` (diamond). Java does not allow writing a wildcard type argument directly in that position.

`<>` and `<?>` are completely different:

| Syntax | Meaning | Can be used right after `new ArrayList`? |
| --- | --- | --- |
| `<String>` | Selects `String` as the type argument | Yes |
| `<>` | Diamond: asks the compiler to infer the type | Yes |
| `<?>` | Refers to an unknown type argument | No |
| `<? extends Number>` | Upper-bounded wildcard | No |
| `<? super Integer>` | Lower-bounded wildcard | No |

Fix examples:

```java
// List<?> a = new ArrayList<?>();           // WRONG
List<?> a = new ArrayList<Object>();         // RIGHT
List<?> b = new ArrayList<>();               // RIGHT
List<? extends Number> c = new ArrayList<Integer>(); // RIGHT
```

Do not interpret `List<?> view = new ArrayList<>()` as an object actually instantiated with type `?`. The `view` variable has an external view type that is a wildcard, while the instantiation still selects a concrete type argument through inference.

This rule also applies to explicit type arguments of a generic constructor in a `new` expression; do not use `?` to ask Java to infer. Let the compiler infer or pass an appropriate concrete type.

## 6. Do not use a wildcard in an explicit type argument list when calling a generic method/constructor

Suppose we have:

```java
static <T> T identity(T value) {
    return value;
}
```

A generic method call is allowed to let the compiler infer `T`, or specify a **concrete type**:

```java
String a = identity("Java");
String b = MyClass.<String>identity("Generics");
```

Here `MyClass` stands for the class containing `static identity`; this snippet only illustrates call syntax, not a standalone file.

A wildcard cannot be written in the explicit type argument list of a call:

```java
// String x = MyClass.<?>identity("Java"); // WRONG
// List<?> y = Collections.<?>emptyList();  // WRONG
```

You can fix it by omitting the explicit type argument list or choosing a concrete type:

```java
List<?> a = java.util.Collections.emptyList();
List<?> b = java.util.Collections.<String>emptyList();
```

A similar rule exists for explicit type arguments of constructor calls `this(...)` or `super(...)`, and explicit type arguments in method references: wildcards do not serve as a type explicitly passed to a generic invocation. **`List<?> result` is valid**, whereas **`Collections.<?>emptyList()` is invalid**; the two positions carry different meanings.

## 7. Do not use a wildcard in the member-qualifying type of a method reference

Method references of the form `TypeName::method` can be used with generic classes/interfaces, yet the **reference type used to look up the method** cannot contain wildcard type arguments.

Example of normal usage:

```java
java.util.function.ToIntFunction<List<String>> size = List::size;
int count = size.applyAsInt(List.of("a", "b"));
```

The expression `List::size` is valid; the following illustrates the forbidden case:

```java
// ToIntFunction<List<String>> wrong = List<?>::size; // WRONG
```

If you need to keep a list with an unspecified element type, use a lambda accepting an explicitly typed parameter or choose a valid method reference:

```java
java.util.function.ToIntFunction<List<?>> countAny = values -> values.size();
```

Do not add `?` to a type reference signature just to indicate that the code does not depend on the element type. A lambda and a variable declaration of type `List<?>` already convey that.

## 8. Two special contexts: only the unbounded wildcard is safe

Some positions **allow `List<?>`**, yet forbid expressions using a non-reifiable generic type such as `List<String>` or `List<? extends Number>` in common cases starting from an `Object` variable. The reason is **type erasure**: the JVM does not store generic element type information to check them at runtime.

### 8.1. `instanceof`

```java
Object value = List.of("a", "b");

boolean valid = value instanceof List<?>; // VALID
// boolean wrong1 = value instanceof List<String>; // WRONG
// boolean wrong2 = value instanceof List<? extends Number>; // WRONG
```

`List<?>` is a **reifiable type** (a type having enough information needed for runtime type checking); therefore `instanceof List<?>` can check whether the object is a `List`. Yet that check does **not** prove the elements inside have any concrete type.

A pattern matching example in Java 17 is also valid:

```java
Object input = List.of("one");
if (input instanceof List<?> list) {
    System.out.println(list.size()); // 1
}
```

Some `instanceof` variants in newer JDKs also have rules checking castability according to the static type of the expression. In the common `Object input` scenario, choose `List<?>` and check elements individually if needed, instead of expecting the JVM to verify `List<String>`.

### 8.2. Array creation

Not every array with a generic component type is forbidden to create. When the component is the reifiable type `List<?>`, the following syntax is valid:

```java
List<?>[] groups = new List<?>[2]; // VALID
groups[0] = List.of(1, 2);
groups[1] = List.of("A", "B");
```

Contrast:

```java
// List<String>[] a = new List<String>[2];              // WRONG
// List<? extends Number>[] b = new List<? extends Number>[2]; // WRONG
// List<? super Integer>[] c = new List<? super Integer>[2];   // WRONG
```

`List<String>` and bounded wildcard parameterizations are not reifiable types usable as component types in an **array creation expression**. Conversely, `List<?>` is reifiable and allowed in `new List<?>[2]`. Declaring a `List<String>[]` **reference** is syntactically writable, yet differs from directly creating that array.

Being allowed also does not mean arrays are the best structure for generic data. Arrays have covariance and runtime type checks that differ from generics; for collection data, `List<List<?>>` is usually easier to use and avoids many array-related issues.

## 9. No class literal for generic types with wildcards

In Java, a class literal has the form `Type.class`, yet it cannot be written based on a generic parameterization:

```java
Class<?> listClass = List.class;  // VALID
Class<?> stringClass = String.class; // VALID

// Class<?> wrong1 = List<?>.class;     // WRONG
// Class<?> wrong2 = List<String>.class; // WRONG
```

Because type arguments are erased at runtime, `List<String>` and `List<Integer>` do not have two separate `Class` objects. Use `List.class` when you need a runtime representation of the class/interface; a variable typed as `Class<?>` is itself a **valid position for using a wildcard**.

Example:

```java
Class<?> type = java.util.ArrayList.class;
System.out.println(type.getSimpleName()); // ArrayList
```

When you genuinely must describe `List<String>` in full at runtime (for example in a serialization framework), you need another type representation such as `java.lang.reflect.ParameterizedType` or a library's type-token mechanism; `List<?>.class` cannot solve that problem.

## 10. Positions where wildcards are completely allowed

Avoid the knee-jerk reaction “whenever you see `?`, it is an error”. All of the following uses are valid:

```java
class WildcardUses {
    List<?> field;                           // Field.
    static List<?> shared;                   // Static field.
    List<List<?>> nested;                    // Nested generic.
    java.util.Map<String, ?> byName;         // Second type argument.
    Class<?> runtimeType = String.class;     // Class<?>.

    void consume(List<?> values) {           // Parameter.
        for (Object value : values) {
            System.out.println(value);
        }
    }

    List<?> readOnlyView() {                  // Return type.
        return List.of(1, 2, 3);
    }
}
```

In each example, `?` sits **inside the type argument list of a generic type being used**. It does not stand alone like `? value`, does not appear at the start of a class's type parameter declaration list, and does not occupy an explicit type argument slot of a `new` expression.

### 10.1. An unbounded wildcard is not a raw type

```java
List<?> safeView = List.of("a", "b");  // Generic still receives type checking.
List raw = List.of("a", "b");         // Raw type, avoid using in new code.
```

`List<?>` still preserves type checking: the compiler disallows `safeView.add("x")` because the element type is unknown. Raw `List` bypasses part of the generics mechanism and easily leads to unchecked warnings. Do not use a raw type as a “quick fix” for a disallowed wildcard.

### 10.2. Errors in operations on a wildcard differ from syntactic position errors

```java
List<?> values = new java.util.ArrayList<String>();
Object item = values.isEmpty() ? null : values.get(0); // VALID
// values.add("hello"); // INVALID under element type checking.
```

In this snippet, `List<?>` **is placed in the right position and is completely syntactically valid**; the issue is that the call `add("hello")` does not guarantee safety, because the actual list might have an element type other than `String`. `values.add(null)` is valid under type checking, yet an immutable implementation may reject modification at runtime.

Two different error groups lead to different fixes:

- **Forbidden wildcard position:** change the declaration syntax/structure, such as `<T>`, `new ArrayList<>()`, `Parent<String>`.
- **Wildcard in a valid position but operation is restricted:** change how the API is used, such as only reading as `Object`, adding a type parameter `<T>` to preserve type linkage, or choosing `? super T` if the API needs to accept `T`.

## 11. Complete, runnable Java 17+ program

Save the following snippet to the file **`WildcardSyntaxDemo.java`**:

```java
import java.util.List;

public class WildcardSyntaxDemo {
    static void show(List<?> values) {
        for (Object value : values) {
            System.out.print(value + " ");
        }
        System.out.println();
    }

    static <T> T first(List<T> values) {
        return values.get(0);
    }

    public static void main(String[] args) {
        List<?> words = List.of("Java", "Generics");
        Object firstWord = words.get(0);

        List<?>[] groups = new List<?>[2];
        groups[0] = words;
        groups[1] = List.of(1, 2);
        Object firstNumber = groups[1].get(0);

        Object candidate = groups[0];
        boolean isList = candidate instanceof List<?>;
        Class<?> type = List.class;

        System.out.println("word=" + firstWord);
        System.out.println("number=" + firstNumber);
        System.out.println("groups=" + groups.length);
        System.out.println("isList=" + isList);
        System.out.println("class=" + type.getSimpleName());
        System.out.println("first=" + first(List.of("OK")));
        show(words);
    }
}
```

Run with JDK 17 or later:

```bash
javac WildcardSyntaxDemo.java
java WildcardSyntaxDemo
```

Stdout:

```text
word=Java
number=1
groups=2
isList=true
class=List
first=OK
Java Generics 
```

The last line has **a trailing space right after the word `Generics`** because `System.out.print(value + " ")` is called for each element before `println()`. The program shows that `List<?>` can serve as a parameter, a variable type, an array component, and be used in `instanceof`. At the same time, `<T>` is the way to declare a generic method; `Class<?> type = List.class` distinguishes a variable's type from a class literal.

## 12. Quick reference table: right, wrong, and alternatives

| Position | Example | Result | Correct syntax / reason |
| --- | --- | --- | --- |
| Class type parameter declaration | `class Box<?> {}` | Wrong | `class Box<T> {}` |
| Method type parameter declaration | `<?> void run()` | Wrong | `<T> void run()` when `T` is truly needed |
| Standalone variable type | `? x;` | Wrong | `Object x;` or `List<?> x;` |
| Standalone parameter type | `void f(? x)` | Wrong | `void f(Object x)` or `void f(List<?> x)` |
| Type parameter bound | `<T extends ?>` | Wrong | `<T extends Number>` |
| Wildcard inside a valid bound | `<T extends Comparable<?>>` | Right | `Comparable<?>` is a type used as a bound |
| Direct superclass | `extends Parent<?>` | Wrong | `extends Parent<T>` or `extends Parent<String>` |
| Direct superinterface | `implements Handler<?>` | Wrong | `implements Handler<String>` |
| Object creation expression | `new ArrayList<?>()` | Wrong | `new ArrayList<>()` or `new ArrayList<String>()` |
| Type argument of generic method call | `Collections.<?>emptyList()` | Wrong | `Collections.emptyList()` |
| Receiver type of method reference | `List<?>::size` | Wrong | `List::size` or a lambda |
| Class literal | `List<?>.class` | Wrong | `List.class` |
| `instanceof` with unbounded wildcard | `obj instanceof List<?>` | Right | Only checks list, does not check element type |
| `instanceof` from `Object` variable with concrete element type | `obj instanceof List<String>` | Wrong | Check `List<?>` then inspect data |
| Unbounded wildcard array creation | `new List<?>[2]` | Right | `List<?>` component is reifiable |
| Generic array creation with concrete argument | `new List<String>[2]` | Wrong | Use `new List<?>[2]` or `List<List<String>>` |
| Field type | `List<?> field;` | Right | `?` is a type argument |
| Method return type | `List<?> get()` | Right | `?` sits inside `List<...>` |
| Nested generic | `Map<String, List<?>> data;` | Right | Wildcard is the type argument of the inner `List` |

Note: the table assumes the relevant classes/interfaces and variables are already declared and properly imported. The `Wrong` rows are syntax fragments for analysis; do not put them directly into a Java file meant to compile.

## 13. Classification and explanation exercises

Assume `import java.util.*;` and that `class Holder<T> {}` is already defined.

### Question 1. Can you declare the following?

```java
// class Strange<?> {}  // (a)
// Holder<?> h = new Holder<String>(); // (b)
// Holder<?> h = new Holder<?>(); // (c)
```

**Answer:** (a) is wrong because `?` cannot be a type parameter name; (b) is right because the wildcard is a type argument in the reference type; (c) is wrong because a wildcard cannot be used as a type argument in an object creation expression. Replace (c) with `new Holder<>()` or `new Holder<String>()`.

### Question 2. Why is this wrong?

```java
// class TextHolder extends Holder<?> {}
```

**Answer:** `extends` specifies a direct supertype. In this context a wildcard type argument is forbidden. Choose a concrete type (`extends Holder<String>`) or pass through a type parameter of the subclass (`class TextHolder<T> extends Holder<T> {}`).

### Question 3. Are these checks or array creations valid?

```java
Object o = List.of(42);
boolean a = o instanceof List<?>; // (a)
// boolean b = o instanceof List<Integer>; // (b)
List<?>[] c = new List<?>[3]; // (c)
// List<Integer>[] d = new List<Integer>[3]; // (d)
```

**Answer:** (a) is valid; (b) is invalid on an `Object` variable because the type argument `Integer` cannot be checked at runtime; (c) is valid because `List<?>` is reifiable; (d) is invalid because generic array creation with a `List<Integer>` component is non-reifiable.

### Question 4. Where is the following method call wrong?

```java
// List<?> result = Collections.<?>emptyList();
```

**Answer:** A wildcard is allowed in the variable type on the left, yet forbidden in the explicit type argument list of the generic method invocation on the right. Fix it to `List<?> result = Collections.emptyList();` or `List<?> result = Collections.<String>emptyList();`.

### Question 5. Can a wildcard be placed inside a bound?

```java
class Sample<T extends Comparable<?>> {}
```

**Answer:** Yes. `T` is the type parameter name, while `Comparable<?>` is **a type used as a bound**. This is not the invalid syntax `T extends ?`. When you need to ensure `T` compares with `T` itself, the pattern `T extends Comparable<T>` usually expresses a tighter relationship.

## 14. Troubleshooting workflow when `javac` reports an error involving `?`

1. **Read the error location first:** is `?` inside `List<?>` or standing alone like `? x`?
2. **Identify the context:** declaring a type parameter, declaring a supertype, creating an object, calling a generic method, writing a method reference, `instanceof`, or creating an array?
3. **If naming a type parameter**, replace `?` with `T`/`E`... and declare its scope of use.
4. **If using `new`**, choose a concrete type argument or the diamond `<>`.
5. **If declaring a direct supertype**, state a concrete type or forward a type parameter from the subclass.
6. **If it is an explicit type argument of a call**, usually omit `<...>` for inference, or state a concrete type.
7. **If it is `instanceof` or array creation**, check reifiability. `List<?>` differs from `List<String>` and `List<? extends Number>`.
8. **If the wildcard is in the right place yet `add` or `set` still errors**, that is a data-type safety/capture problem, not syntax. Consider `<T>` or an appropriate bounded wildcard.

## 15. Specification references and conclusion

- [Java Language Specification 17, §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): wildcards as type arguments and bound semantics.
- [Java Language Specification 17, §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): why `List<?>` differs from `List<String>` in runtime checks.
- [Java Language Specification 17, §4.11 — Where Types Are Used](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.11): summary of contexts forbidding wildcards and contexts requiring reifiable types.
- [Java Language Specification 17, §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): rules for type arguments and diamond in `new`.

**Key takeaway:** `?` is used to denote an *unknown type argument* in a generic type being used, such as `List<?>`; it cannot replace a type parameter `T`, cannot serve as a direct supertype, and cannot appear inside `new ArrayList<?>()` or `Collections.<?>emptyList()`. Uniquely, `List<?>` is a reifiable type, so `instanceof List<?>` and `new List<?>[n]` are valid.