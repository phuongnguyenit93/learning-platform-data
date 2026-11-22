# Method Signature and Components Not Part of the Signature in Java

## Learning Objectives

After this lesson, you will be able to:

- Identify the **method signature** according to Java's rules, distinguishing it from the full method declaration line and from a method call.
- Recognize the components that affect the signature: **the method name, the method's type parameters if any, and the formal parameter type list** according to Java's signature comparison rules.
- Point out the components that **do not make up the signature for distinguishing methods**: return type, parameter names, `throws`, access modifiers, `static`/`final`, `@...` annotations, and the method body.
- Predict when two declarations are considered to have the same signature, when an **overload** is valid, and when Java reports a duplicate declaration error or a *name clash* due to generic erasure.
- Distinguish a signature at the **Java language** level from a *JVM method descriptor*, and understand why changing the return type can affect API/binary compatibility even though it does not distinguish overloads.
- Distinguish overloading from overriding, including *covariant return type* and the role of `@Override`.

## 1. What Does a Method Declaration Consist Of?

Consider the example:

~~~java
public final class Calculator {
    public static int add(final int left, int right) throws IllegalArgumentException {
        return left + right;
    }
}
~~~

This is a valid, compilable `Calculator.java` file (without `main` to run standalone).

In such a declaration, we observe many components:

| Component | In the Example | Role |
| --- | --- | --- |
| Access modifier | `public` | Allows using the method from code that can access it |
| Other modifier | `static` | The method belongs to the class; no object is needed to call it |
| Return type | `int` | The type of value the method returns to the caller |
| **Method name** | `add` | The name used to look up the method |
| **Parameter types** | `int, int` | The types and order of accepted arguments |
| Parameter names | `left, right` | Variable names used inside the method body |
| Parameter modifier | `final` on `left` | Prevents reassigning that parameter variable inside the method body |
| `throws` | `IllegalArgumentException` | Lists the declared exception types; this is an unchecked exception |
| Method body | `{ return left + right; }` | Code executed when called |

The long declaration line consists of many components, but **not all of them participate in the method signature**. Making this distinction is very important when writing multiple methods with the same name, implementing interfaces, using inheritance, or changing an API.

## 2. Method Signature in the Java Language

In the Java Language Specification (JLS, Section 8.4.2), a **method signature** is based on:

1. **The method name**.
2. **The method's type parameters**, if the method is generic.
3. **The formal parameter types** in exact order, along with the rules for adapting type parameter names and comparing signatures in the JLS.

For a regular **non-generic** method, determining it is very intuitive:

~~~java
void save(String id, int amount) { }
~~~

The signature can be written concisely for study as **`save(String, int)`**. The two names `id` and `amount` do not participate in distinguishing the signature. When analyzing at the specification level, keep in mind that generic methods have additional rules regarding type parameters, and comparisons such as *same signature* and *subsignature* are not merely plain-text string comparisons.

For two methods:

~~~java
void save(String id, int amount) { }
void save(int amount, String id) { }
~~~

Their signatures are **`save(String, int)`** and **`save(int, String)`**, respectively. Because the order of parameter types differs, they can coexist as **overloads** (provided other class constraints are satisfied).

Conversely:

~~~java
void save(String id, int amount) { }
void save(String key, int count) { }
~~~

This is an **intentionally invalid example if both lines appear in the same class**: the parameter names change, yet the method name and the order of parameter types remain identical. Java will report an error that the method has already been declared.

### 2.1. The Signature Is Not the Method Name Alone

If a class has:

~~~java
void print(int value) { }
void print(String value) { }
void print(String text, int count) { }
~~~

the three signatures can be read as `print(int)`, `print(String)`, and `print(String, int)`. Having the same name `print` does not mean having the same signature, because the list of parameter types differs. The ability to define methods with the same name but different parameters is called **method overloading**.

### 2.2. Both the Number and Order of Parameters Matter

The following declarations have different signatures:

~~~java
void report() { }
void report(int page) { }
void report(int page, String format) { }
void report(String format, int page) { }
~~~

They have 0, 1, 2, and 2 parameters, respectively. The last two methods differ due to the **order of types**, not because of the names `page` or `format`.

If you swap the **names** without changing the type list, the signature does not change:

~~~java
// Only illustrates two declarations with duplicate signatures; do not put both in the same class.
void move(int x, int y) { }
// void move(int row, int column) { } // Duplicates move(int, int)
~~~

Renaming parameter variables can make code easier to understand, but it does not create a new overload.

## 3. Components That Do NOT Belong to the Signature for Distinguishing Methods

| Component | Does It Distinguish a Java Signature? | Example / Consequence |
| --- | --- | --- |
| **Method name** | **Yes** | `sum(int)` differs from `count(int)` |
| **Ordered list of parameter types** | **Yes** | `sum(int)` differs from `sum(long)` |
| **Type parameters of a generic method** | **Considered per JLS** | Comparison includes a step adapting corresponding type variables |
| Return type | **No** | `int get()` and `String get()` cannot both be declared solely by differing in return type |
| Parameter names | **No** | `f(int age)` and `f(int years)` have the same signature |
| Parameter modifiers such as `final` | **No** | `f(final int x)` and `f(int x)` have the same signature |
| `throws` | **No** | `read() throws IOException` and `read() throws Exception` do not create an overload |
| `public`, `private`, `protected` | **No** | Changing access visibility does not create a second method with the same name/parameters |
| `static`, `final`, `abstract`, `synchronized`, `native`, and other method modifiers | **No** | A `static` method and an instance method cannot have the same signature in the same class |
| Annotations such as `@Deprecated`, `@Override` | **No** | Annotations provide metadata/checks and do not create an overload |
| Local variable names, method body, and algorithm | **No** | Replacing `return a + b` with another calculation does not create a new signature |
| Generic parameter list of the **return type** | **No** | `List<String> load()` and `List<Integer> load()` do not create an overload when having the same formal parameters |

**Note:** “Not belonging to the signature” **does not mean unimportant**. For example, the return type determines type checking of the expression receiving the result, `throws` affects checked exception handling rules, access modifiers determine call permissions, and `static` determines how the method is bound to the class. They can affect the validity of an **override**, API compatibility, or method callability; changing them alone simply does not produce a different overload signature.

## 4. Why Can't You Overload by Return Type Alone?

For example, the following two declarations **will not compile when placed together in the same class**:

~~~java
// Intentionally invalid code; used only for analysis.
// class InvalidReturns {
//     int convert(String text) { return Integer.parseInt(text); }
//     long convert(String text) { return Long.parseLong(text); }
// }
~~~

Both have the signature `convert(String)`. The return type `int` or `long` does not help distinguish them; the error is declaring the same signature in one class.

A common misconception is that “the compiler will choose the `int convert(String)` method when assigning to `int`, and choose `long convert(String)` when assigning to `long`”. Java **does not allow defining overloads that way**. Overload resolution depends on rules regarding the name, arguments, applicability, specificity, generic inference, and context where applicable; it does **not** make two declarations with the same signature valid just because the target receiving the result has a different type.

Practical solutions:

- Choose **different names** according to meaning: `parseInt(String)` and `parseLong(String)`.
- Or design **meaningfully different parameters**, for example `convert(String)` and `convert(String, int radix)`, if they are genuinely two sensible ways to call the method.
- Do not add meaningless parameters just so the compiler allows overloading.

Nor can you use `void` versus a value-returning type to distinguish them:

~~~java
// Invalid if both declarations are placed in the same class:
// void refresh() { }
// boolean refresh() { return true; }
~~~

Both are `refresh()`.

## 5. `throws` and Parameter Names Do Not Change the Signature

Consider two declarations:

~~~java
// The following two lines cannot appear simultaneously in the same class:
// void read(String path) throws java.io.IOException { }
// void read(String fileName) throws java.lang.Exception { }
~~~

Both signatures are `read(String)` even though:

- `path` changes to `fileName`.
- `throws IOException` changes to `throws Exception`.

`throws` describes the exception contract according to Java's rules. When a method **overrides** a superclass method or implements an interface, the checked exceptions allowed to be declared may be constrained by the overridden declaration; therefore, `throws` is very important for override validity, even though it is not a component that creates an overload.

For example, if an interface declares `void read() throws IOException;`, the implementing class is permitted to declare no checked exceptions, or to declare a checked exception that conforms to Java's constraints. However, changing to a broader `throws Exception` can cause a compilation error when overriding. Unchecked exceptions have different rules.

## 6. Modifiers and Annotations Do Not Distinguish Overloads

The following two methods cannot appear together in the same class:

~~~java
// Code illustrating the error:
// static void reset(int value) { }
// void reset(int value) { }
~~~

Both have the signature `reset(int)`; adding or removing `static` does not create a new overloaded method.

Similarly, the method `public int size()` does not become a different signature when changed to `private int size()`, `protected int size()`, or when `final` is added. That is a change to the access/behavior contract, and it has its own rules regarding inheritance or overriding.

Annotations such as `@Deprecated` placed on a method also do not change the signature. `@Override` instructs the compiler to verify correctness when overriding/implementing; this annotation does not turn a method into an override if the actual name/parameter types do not match.

## 7. Varargs and Array Parameters: Not Two Different Signatures

A **variable arity parameter** declaration uses `...` to allow passing a flexible number of compatible arguments at the last parameter position. In terms of the corresponding signature, `String...` and `String[]` do not create two independent overloads:

~~~java
// Two declarations with the same signature; they cannot be used at the same time:
// void send(String... messages) { }
// void send(String[] messages) { }
~~~

Both are treated with the `String[]` array parameter form in the Java signature. The difference is the **calling capability** that varargs syntax provides: `send("A", "B")` is permitted with a varargs declaration, whereas with a declaration that only accepts an array, a matching array must be passed. A varargs method can also accept an array as an argument.

Valid example, saved in the file **`VarargsDemo.java`**:

~~~java
public class VarargsDemo {
    static int count(String... values) {
        return values.length;
    }

    public static void main(String[] args) {
        System.out.println(count());
        System.out.println(count("A", "B"));
        System.out.println(count(new String[] {"X", "Y", "Z"}));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac VarargsDemo.java
java VarargsDemo
~~~

Output:

~~~text
0
2
3
~~~

Here there is only **one** method `count(String...)`; all three calls are handled according to that method's applicability. When multiple overloads and varargs are present, Java prioritizes the phases evaluating fixed-argument calls before the varargs phase according to the overload resolution rules. Do not infer from the `...` notation that the JVM has a parameter type completely separate from an array.

## 8. Generic Methods: Type Parameters, Same Signature, and Erasure

Saying “a signature is just the name + parameter types” is a quick way to learn for non-generic methods. For generic methods, JLS 8.4.2 also considers the **type parameters of the method itself** and defines the *same signature* rule after adapting the corresponding type parameters.

Example:

~~~java
// Used only for comparison, not declared simultaneously:
<T> void accept(T item) { }
// <U> void accept(U value) { }
~~~

Whether using the name `T` or `U`, the two declarations still correspond to the same signature under Java's type parameter renaming/adaptation rules. Renaming a type variable does not create an overload.

A generic method can be declared as:

~~~java
public static <T> T identity(T value) {
    return value;
}
~~~

This snippet is a valid `static` method declaration if placed in an appropriate class; here `<T>` is the **method's type parameter**, `T` before the name `identity` is the return type, and `T value` is the parameter type. The very existence and matching of the type parameter declaration is different from merely changing the parameter name `value`.

### 8.1. Erasure Causes a Name Clash When Overloading Seems Possible

Consider two declarations:

~~~java
// NOT valid when placed in the same class:
// void process(java.util.List<String> items) { }
// void process(java.util.List<Integer> items) { }
~~~

Java generics use **type erasure**: at the corresponding level for checking name clashes and bytecode, both parameter types `List<String>` and `List<Integer>` have the erasure `List`. Therefore, these two declarations cannot be overloaded solely by the type arguments of the same generic type.

Similarly, changing `List<String>` to `List<Long>`, or renaming the variable `items`, still does not solve the issue. You can choose different method names (for example `processNames`, `processIds`) or change the API design based on the data that truly needs to be distinguished.

**Distinguishing the two causes:** an error due to *same signature* and a *name clash* error may be presented by the compiler with different messages. In the generic case, we must examine **subsignature/override-equivalence and erasure** thoroughly, rather than just looking at whether the character sequences inside `<...>` differ.

### 8.2. Do Not Confuse a Generic Parameter with a Generic Return Type

~~~java
// Invalid if both appear at the same time in a class:
// java.util.List<String> load() { return java.util.List.of("A"); }
// java.util.List<Integer> load() { return java.util.List.of(1); }
~~~

Both have the corresponding name and parameter list `load()`. The difference lies **solely in the return type**, so they do not create two overloads. One call site expecting `List<String>` and another expecting `List<Integer>` cannot be used to define two methods with the same signature in that way.

## 9. Complete Example: Valid Overload and Covariant Override

Save the program under the name **`MethodSignatureDemo.java`**:

~~~java
public class MethodSignatureDemo {
    static class Formatter {
        public String format(int value) {
            return "int=" + value;
        }

        public String format(String value) {
            return "text=" + value;
        }

        public String format(String value, int count) {
            return value.repeat(count);
        }

        public Number score(int value) {
            return value * 10;
        }
    }

    static final class AdvancedFormatter extends Formatter {
        @Override
        public Integer score(int value) {
            return value * 100;
        }
    }

    public static void main(String[] args) {
        Formatter formatter = new Formatter();

        System.out.println(formatter.format(7));
        System.out.println(formatter.format("Java"));
        System.out.println(formatter.format("Hi", 2));

        Formatter base = new Formatter();
        Formatter child = new AdvancedFormatter();

        System.out.println("base score=" + base.score(2));
        System.out.println("child score=" + child.score(2));
        System.out.println("child text=" + child.format("OK"));
    }
}
~~~

Compile and run:

~~~bash
javac MethodSignatureDemo.java
java MethodSignatureDemo
~~~

Exact output:

~~~text
int=7
text=Java
HiHi
base score=20
child score=200
child text=text=OK
~~~

**Explanation of each method's signature:**

| Declaration | Java Signature | Relationship |
| --- | --- | --- |
| `format(int value)` | `format(int)` | Overloads `format(String)` |
| `format(String value)` | `format(String)` | Overloads `format(int)` |
| `format(String value, int count)` | `format(String, int)` | Overload due to different number/order of parameter types |
| `Formatter.score(int value)` | `score(int)` | Method in the superclass |
| `AdvancedFormatter.score(int value)` | `score(int)` | **Overrides** the superclass method |

In `AdvancedFormatter.score(int)`, the return type changes from `Number` to `Integer`, yet the signature remains `score(int)`. This is a valid **covariant return**: `Integer` is a subtype of `Number`. When calling `child.score(2)` through a variable of type `Formatter`, the overriding implementation in the `AdvancedFormatter` object is selected and returns `200`.

If the return type in the subclass is changed to `String`, having the same signature `score(int)` alone will **not** turn it into an overload; the compiler will report an error that the return type is incompatible with the overridden method.

For the overloads `format(int)`, `format(String)`, and `format(String,int)`, the compiler decides the appropriate declaration based on the call's arguments. At runtime, for overridden instance methods, dynamic dispatch selects the corresponding implementation. Those are two related but distinct mechanisms.

## 10. Overloading, Overriding, and Signature-Related Constraints

### 10.1. Overload

**Overloads** are methods with the same name but parameter lists that differ enough to be considered valid declarations within the same class/inheritance context. For example:

~~~java
void log(int code) { }
void log(String message) { }
void log(String message, int level) { }
~~~

These are illustrative method declarations inside a class, without `main`. They have different signatures.

The following changes **are not ways to overload**:

~~~java
// The pairs below are intentionally invalid code if declared together:
// int size() { return 0; }
// long size() { return 0; }

// void update(int x) { }
// void update(int y) throws RuntimeException { }

// static void clear() { }
// void clear() { }
~~~

Common factor: each pair has **identical names and corresponding parameter types**; differing in return type, parameter names, `throws`, or modifiers does not resolve the duplication.

### 10.2. Override

**Overriding** applies to instance methods in an inheritance/implementation relationship when Java's rules on signature, subsignature, access, return type, and exceptions are satisfied. A method in a subclass can override a superclass method with a matching signature, while:

- It must not reduce the access level of the overridden method under Java's rules.
- The return type must be **return-type-substitutable**: it can be the same type, an appropriate covariant reference type, or generic cases permitted by the specification; primitive types cannot be arbitrarily changed.
- It cannot declare new/broader checked exceptions in violation of the overridden method's constraints.
- It cannot override a `final` instance method.
- Do not call this phenomenon an overload simply because the `@Override` annotation or parameter names are changed.

**Static methods are not overridden via dynamic dispatch like instance methods**: they can be *hidden* in a subclass under the conditions Java allows. Attempting to use an instance method to override a static method with the same signature in the superclass, or vice versa, will cause an error. This is a behavioral difference, not an additional signature.

### 10.3. A Subtle Case: Subsignature and Generic Code Compatibility

The JLS defines **subsignature**: two signatures may be identical, or one signature may match the **erasure** of the other according to specific rules. That mechanism helps preserve certain forms of overriding when an API is generified, without requiring every overriding case to have completely identical parameter type text.

When encountering generic methods, raw types, and inheritance, do not oversimplify the rule to “just having the same name and same number of parameters”. You must examine **types, order, type parameters, and the subsignature/override-equivalence rules**.

## 11. Method Declaration, Method Signature, Method Call, and JVM Descriptor

These four concepts are often loosely grouped together as “signature,” yet they are different:

| Concept | Explanation | Example |
| --- | --- | --- |
| Method declaration | The entire declaration including modifiers, type parameters, return type, name, parameters, `throws`, and body | `public int add(int x,int y) { return x+y; }` |
| Java method signature | The language-level concept used for comparing signatures, overloading, and overriding rules | `add(int,int)` (shorthand notation for a non-generic method) |
| Method invocation | The expression calling a method, with actual arguments and possibly a receiver | `calculator.add(1,2)` |
| JVM method descriptor | Representation of parameter types **and return type** in a JVM class file, not the overloading rule of Java source | `(II)I` corresponding to two `int` parameters, returning `int` |

Example:

~~~java
public int add(int x, int y) {
    return x + y;
}
~~~

This is an illustrative method snippet inside a class. At the Java source level, the signature is described as `add(int,int)`. At the JVM level, the **method descriptor** `(II)I` represents two `int` parameters and an `int` return type. Note that a *descriptor* does not itself contain the **method name**: in JVM method reference structures, the name is stored as a separate component.

Therefore, the statement “the return type is not part of the Java signature” **does not contradict** the fact that the return type appears in the JVM descriptor or in many API reporting formats. The compiler sometimes generates **bridge methods** to preserve generic/covariant return semantics in bytecode; that does not allow programmers to define overloads by return type alone within a Java class.

Documentation and tooling also sometimes use the word “signature” in a broader sense, or refer to the **generic signature attribute** in a class file. When discussing duplicate declarations/overloading in Java source, you must apply the **Java signature definition**; when discussing bytecode, you need to state clearly whether you are referring to a JVM descriptor or another form of metadata.

### 11.1. `javap` Shows That the Descriptor Includes the Return Type

With the `Calculator.java` file from the beginning, you can try:

~~~bash
javac Calculator.java
javap -s Calculator
~~~

The `javap -s` tool will display method descriptors, in which the method `add(int,int)` has the descriptor **`(II)I`**. This is a bytecode inspection command; the output formatting of `javap` may include a constructor and other lines depending on the tool version. You should not confuse the descriptor with the construct used to define overloads in Java source.

## 12. Confusing Scenarios in Overload Selection

### 12.1. Parameter Types Are Primary, but Call Resolution Has Many Rules

For example, a class has both `void f(int x)` and `void f(long x)`. The call `f(5)` typically selects `f(int)` because the literal `5` has type `int` and there is a directly applicable method. For `f(5L)`, the compiler selects `f(long)`. With generics, boxing/unboxing, widening, varargs, and multiple applicable overloads, the selection process becomes even more complex.

You need to distinguish:

1. **Can two methods be declared validly?** This is a question of signatures/erasure and declaration constraints.
2. **Which method will a specific call select?** This is a question of overload resolution based on argument types/expressions and context.
3. **Which overriding implementation runs at runtime?** This is dynamic dispatch for instance methods (when overriding conditions are satisfied).

The three questions are related, but not equivalent.

### 12.2. `null` Can Create an Ambiguous Call

For example, suppose there are two valid overloads:

~~~java
void send(String value) { }
void send(Integer value) { }
~~~

Placed in one class, these two methods differ in parameter type. However, the call `send(null)` causes an **ambiguous method call** error because both `String` and `Integer` accept `null`, yet neither type is more specific than the other under the relevant overload selection rules. You can clarify intent with `send((String) null)` or `send((Integer) null)`, though in practice APIs should avoid overloads that make calls ambiguous if they frequently accept `null`.

### 12.3. Autoboxing Is Not a Signature Change

The two overloads `f(int)` and `f(Integer)` have different signatures, because `int` is a primitive and `Integer` is a reference type. Java may perform boxing/unboxing in some calls, but that does not turn the two signatures into one. If you construct call examples yourself, you need to consider the overload resolution phases rather than inferring purely from simple boxing capabilities.

### 12.4. Generic Type Arguments Do Not Create Overloads on Their Own

`List<String>` and `List<Integer>` both have the erasure `List`. Creating two methods that differ only in the generic argument part will lead to a name clash. If you want to handle content of different types, consider one generic method, two clearly descriptive method names, or valid, meaningful distinguishing parameters.

## 13. How to Check the Signature When Reading a Method

When encountering a long declaration, you can follow this sequence:

1. **Find the method name** (after the return type, before the `(` of the parameter list).
2. **Identify the type parameters of the method itself**, if any (for example `<T extends Number>` appearing before the return type).
3. **Write down the parameter type list in exact order**: `(String id, int count)` becomes `(String,int)`. Match full types, not just simple names when packages differ.
4. **Ignore parameter names**, parameter modifiers, and annotations unrelated to distinguishing the signature.
5. **Do not use the return type, `throws`, method-level modifiers, or the method body to distinguish overloads**.
6. **If generics, varargs, or inheritance are involved**, also consider erasure, subsignature, override-equivalence, and array/varargs equivalence according to Java's rules.
7. **Only after confirming the declarations are valid**, examine the specific call and the rules for overload resolution or dynamic dispatch.

Example:

~~~java
public static <T extends Number> T pick(
        final T first,
        T second
) throws IllegalArgumentException {
    return first;
}
~~~

This is a valid illustrative method inside an appropriate class. The components to look at when examining the signature are: the name `pick`, the type parameter `T extends Number`, and the types of the two formal parameters `T, T`. Details such as `public static`, `final` on `first`, the names `first/second`, the return type `T`, and `throws IllegalArgumentException` do not create a new signature on their own. For a generic method, you must not replace `T` with an arbitrary type in the signature and conclude that two declarations differ; you must follow the rules of type parameter adaptation and erasure.

## 14. Common Errors and How to Fix Them

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Compiler reports the method is already defined | Two declarations have the same signature in the same class | Change the method name or parameter type list meaningfully; do not only change the return type/variable names |
| Expecting to distinguish `get(): int` and `get(): long` | Return type does not distinguish a Java signature | Use different descriptive names or redesign the API |
| Two methods with different `throws` still conflict | Exception declarations do not belong to the signature | Choose a `throws` contract matching the functionality or change the API |
| Using `f(String...)` and `f(String[])` in the same class | Varargs corresponds to an array parameter in the signature | Keep only one declaration matching the desired calling style |
| Two overloads differing only by `List<String>` and `List<Integer>` fail | Type erasure leads to a name clash | Use clear distinct names, use one generic method, or design meaningful different parameters |
| `@Override` reports that the method does not override | Wrong method name/parameter types or violation of override conditions | Compare the signature and the return/throws/access rules |
| Changing `static` to instance expecting another overload | Modifiers do not distinguish signatures | Keep one declaration or change the API; do not treat static/instance as two signatures |
| `send(null)` is ambiguous | Two overloads have reference types that are not comparable in specificity | Specify the type with a cast when needed; consider a design that avoids ambiguity |
| Seeing `(II)I` in `javap` and thinking the return type belongs to the Java method signature | Confusing the JVM descriptor with the Java language signature | Distinguish between the source level and the bytecode level |
| Renaming a parameter and thinking the overload API changed | Parameter names do not distinguish signatures | Change parameter types/count/type order if a new overload is truly needed |
| Two methods with the same name and different parameters still fail on a call | Valid overload declarations do not guarantee every call has a unique candidate | Check argument types, boxing, varargs, generic inference, and ambiguity |

## 15. Self-Check Questions

**Question 1.** Can the two declarations `int total(int a, int b)` and `long total(int x, int y)` appear together in the same Java class?  
**Answer:** No. Both have the signature `total(int,int)`; they differ only in return type and parameter names.

**Question 2.** Do `void send(String id, int count)` and `void send(int count, String id)` have the same signature?  
**Answer:** No. They are `send(String,int)` and `send(int,String)`, respectively. The order of parameter types differs, so they can be overloaded.

**Question 3.** Can the two declarations `void load() throws IOException` and `void load() throws SQLException` be overloaded?  
**Answer:** No. `throws` does not create a different signature; both are `load()`.

**Question 4.** Do `void log(String[] items)` and `void log(String... items)` create two different signatures?  
**Answer:** No. They share the same signature corresponding to the array form `log(String[])`.

**Question 5.** Why can't `void consume(List<String>)` and `void consume(List<Integer>)` be overloaded?  
**Answer:** Both have `List` as the erasure of their parameter and cause a name clash at the Java level; generic type arguments are not sufficient to create independent overloads.

**Question 6.** Is a subclass method returning `Integer` to override a superclass method returning `Number` necessarily invalid because the return types differ?  
**Answer:** No. With the matching signature, `Integer` can be a valid covariant return type of `Number`, provided the other override constraints are also satisfied.

**Question 7.** Do `public static int f(int x)` and `private int f(int y)` have different signatures?  
**Answer:** No. Both are `f(int)`. The modifiers `public/private/static`, the names `x/y`, and the return type do not distinguish signatures.

**Question 8.** `javap -s` displays the descriptor `(II)I`. What is the final `I`, and does it make the return type a component that distinguishes Java source signatures?  
**Answer:** The final `I` is the `int` return type in the JVM descriptor. This is a bytecode construct distinct from the Java source signature, so it does not allow overloading by return type alone.

**Question 9.** Why is comparing only the number of parameters insufficient to determine a signature?  
**Answer:** Because **types, type order, and generic rules** must also be considered. `f(int)` and `f(String)` have the same number of parameters yet different signatures.

## Summary

When looking at a Java method, do not confuse **the entire declaration** with **the signature**. For non-generic methods, the practical rule is **method name + parameter type list in exact order**; for generic methods, you must also consider type parameters according to the JLS and the name adaptation/erasure rules. **The return type, parameter names, `throws`, access modifiers, `static`, `final`, annotations, and method body do not distinguish the signature to create an overload**. The signature is directly tied to validity when declaring, overloading, and overriding; overload selection at the call site and the JVM descriptor are separate matters that need to be considered separately.
