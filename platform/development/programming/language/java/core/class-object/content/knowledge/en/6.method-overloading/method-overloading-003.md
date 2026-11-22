# Why Does Changing Only the Return Type Not Create Method Overloading in Java?

In Java, **method overloading** is declaring multiple methods with the **same name but different parameter lists** according to the *method signature* rules. **Changing only the return type**, such as from `int` to `String`, while keeping the name and parameters unchanged **does not create a valid overload**.

This is not a naming convention, but a rule of the Java language: **the return type is not part of the method signature used to distinguish overload declarations in source code**. For example, the following two methods in the same class will cause a compilation error:

~~~java
class Report {
    int read(int id) {
        return id;
    }

    String read(int id) {
        return "ID-" + id;
    }
}
~~~

Both have the signature `read(int)`. One method returns `int` and one method returns `String`, yet the compiler still treats them as **two declarations with duplicate signatures**, so no valid Java program is produced from this code snippet.

The lesson below explains exactly what a signature consists of, how the compiler selects an overload at a method call, how it differs from overriding, similar cases that are easy to confuse, and how to design APIs properly on Java 17+.

## 1. Distinguishing Name, Signature, and Return Type

Consider the example:

~~~java
class Printer {
    public String format(int number, boolean grouped) {
        return number + ":" + grouped;
    }
}
~~~

This is an **illustrative class declaration snippet**, without `main` to run standalone.

| Component | Value in the example | Role |
| --- | --- | --- |
| Method name | `format` | Name used when calling |
| Formal parameter list | `int number, boolean grouped` | Two parameters in exact order |
| Parameter types | `int, boolean` | Key component of the signature |
| Signature in conventional representation | `format(int, boolean)` | Distinguishes the method from other overloads |
| Return type | `String` | Specifies the result that the method body must produce and the caller receives |
| Modifier | `public` | Specifies accessibility; does not create a new signature |
| Parameter variable names | `number`, `grouped` | Do not create a new signature if only renamed |

According to **Java Language Specification (JLS) `8.4.2**, a method signature is determined by **the method name and parameters** according to the rules on type parameters and formal parameter types. When two generic methods are considered, Java also has rules for adapting type parameters to determine equivalent signatures; the key point here is that **the return type is not in the list of characteristics that distinguish overloads**.

Therefore:

~~~java
// Two declarations with the same signature f(int), NOT valid if in the same class:
int f(int x) { return x; }
long f(int y) { return y; }

// Two declarations with different signatures g(int) and g(long), can be in the same class:
int g(int x) { return x; }
long g(long x) { return x; }
~~~

These lines are **illustrations of method bodies**, not standalone code to be compiled together. In pair `f`, changing the result type and the parameter variable name does not help. In pair `g`, changing the parameter type from `int` to `long` creates an overload, regardless of whether their return types are the same or not.

**Summary:** to identify an overload, inspect **the name + parameter types in order and the number of parameters**, rather than comparing the return types.

## 2. Compilation Error When Changing Only the Return Type

Suppose you want to provide two ways to read an age:

**File `ReturnOnly.java` — intentionally incorrect example:**

~~~java
public class ReturnOnly {
    int getAge() {
        return 20;
    }

    String getAge() {
        return "20 tuổi";
    }
}
~~~

Run:

~~~bash
javac ReturnOnly.java
~~~

`javac` rejects it and typically produces a message like:

~~~text
ReturnOnly.java:6: error: method getAge() is already defined in class ReturnOnly
~~~

Line numbers, formatting, and other details may vary depending on the JDK version. The invariant cause: two methods have the **same signature `getAge()`** but different return types.

Even if, in the calling method, the programmer writes:

~~~java
int numericAge = person.getAge();
String ageLabel = person.getAge();
~~~

it still does not make the two `getAge()` declarations above valid. **The compiler must check the validity of method declarations first**, and cannot rely on what variable the caller intends to assign the result to in order to validate two methods with duplicate signatures.

### 2.1. One Fix: Name by the Meaning of the Result

If two representations of the same data are needed, use different names:

~~~java
class Person {
    private final int age;

    Person(int age) {
        this.age = age;
    }

    int getAge() {
        return age;
    }

    String getAgeLabel() {
        return age + " tuổi";
    }
}
~~~

Here `getAge()` and `getAgeLabel()` have **two different names**, so there is no longer a conflict. In addition to compiling cleanly, the names also tell the caller whether they are receiving a number or a display string.

### 2.2. Another Fix: Genuinely Different Parameters

~~~java
class Person {
    private final int age = 20;

    int getAge() {
        return age;
    }

    String getAge(boolean withUnit) {
        return withUnit ? age + " tuổi" : Integer.toString(age);
    }
}
~~~

The two methods have signatures `getAge()` and `getAge(boolean)`, so **the overload is valid**. However, adding a `boolean` parameter just to bypass the compiler error does not necessarily produce an easy-to-understand API. For data representation problems, `getAgeLabel()` or `formatAge()` usually makes the intent clearer.

Design principle: **change the parameter list when two ways of calling genuinely differ in input data or input-driven behavior**, rather than adding redundant parameters just to change the return type.

## 3. Why Did Java Design Overloading Around Parameters?

When encountering a method call, the compiler needs to determine **which method is being called** based on the source code context, method name, arguments, accessible overloads, and overload applicability/resolution rules.

For example:

~~~java
class Calculator {
    int doubleValue(int number) {
        return number * 2;
    }

    double doubleValue(double number) {
        return number * 2;
    }
}
~~~

If the caller writes `calculator.doubleValue(3)`, the argument has type `int`, so the overload accepting `int` is the appropriate choice. If the caller writes `calculator.doubleValue(3.5)`, the argument has type `double`, so the overload accepting `double` fits.

However, if only the return type differs and the parameter list stays identical, for example:

~~~java
// Invalid:
int convert(String text) { return Integer.parseInt(text); }
long convert(String text) { return Long.parseLong(text); }
~~~

then the call `convert("12")` carries no difference in name or parameter types to identify a single declaration. Java **specifies right at the declaration level** that two methods must not differ only by their return type.

There are two subtle points to understand correctly:

1. **The return type does not distinguish two declarations with the same signature.** This is a definite rule, with no exceptions simply because the compiler “looks at the variable receiving the result”.
2. For **already valid** overloads, especially generic methods/poly expressions, **target typing** and type inference may participate in checking and selecting a method in certain contexts. Therefore, one should not overstate that “Java never considers the result type at any step of method resolution”. Even with such advanced rules, they **do not validate** two methods that differ only in their return type.

In addition, a call can **ignore the result**:

~~~java
calculator.doubleValue(3); // valid: call the method and do not use the result
~~~

This further shows that callers cannot all be required to supply a “desired receiving type” to differentiate between two methods that share the same name and parameters.

## 4. Runnable Java 17+ Example: Valid Overloading Even with Different Return Types

Save everything to **`OverloadReturnDemo.java`**:

~~~java
import java.util.Locale;

public class OverloadReturnDemo {
    static int convert(int value) {
        return value * 2;
    }

    static String convert(String value) {
        return value.trim().toUpperCase(Locale.ROOT);
    }

    static double convert(double value) {
        return value / 2.0;
    }

    static int measure(String text) {
        return text.length();
    }

    static String measure(String text, String prefix) {
        return prefix + text;
    }

    static class Parent {
        Number result() {
            return 10;
        }
    }

    static final class Child extends Parent {
        @Override
        Integer result() {
            return 20;
        }
    }

    public static void main(String[] args) {
        System.out.println("int: " + convert(3));
        System.out.println("String: " + convert("  java  "));
        System.out.println("double: " + convert(8.0));

        System.out.println("length: " + measure("Java"));
        System.out.println("prefixed: " + measure("Java", "Hi-"));

        Parent parent = new Child();
        System.out.println("overridden: " + parent.result());
        System.out.println("runtime type: "
                + parent.result().getClass().getSimpleName());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 OverloadReturnDemo.java
java OverloadReturnDemo
~~~

**Exact stdout:**

~~~text
int: 6
String: JAVA
double: 4.0
length: 4
prefixed: Hi-Java
overridden: 20
runtime type: Integer
~~~

Explanation:

1. The three methods named `convert` have the signatures `convert(int)`, `convert(String)`, and `convert(double)`, so they are **three valid overloads**. The different return types `int`, `String`, and `double` cause no error at all because **the parameter lists already differ**.
2. `convert(3)` calls the version accepting `int`; `3 * 2` becomes 6. `convert("  java  ")` uses the overload accepting `String`, trims leading/trailing whitespace, and converts it to `JAVA` using `Locale.ROOT`. `convert(8.0)` accepts `double` and halves it to `4.0`.
3. The two `measure` methods differ in the **number of parameters**: `measure(String)` returns the string length, while `measure(String, String)` prepends a prefix to the string.
4. `Parent.result()` and `Child.result()` are **overriding**, **not overloading**: two methods with the same signature `result()` in two classes in an inheritance relationship. `Child` is allowed to return `Integer` because `Integer` is a subtype of `Number`, i.e., a **covariant return type**.
5. The variable `parent` has declared type `Parent` but references a `Child` object. When calling the instance method `result()`, dynamic dispatch selects the `Child` implementation; `20` is boxed into an `Integer`, so the runtime type name is `Integer`.

An easily overlooked point: `Parent.result()` returning `Number` and `Child.result()` returning `Integer` alone **does not create an overload**. The final result of the example illustrates the case of **an override with a narrower return type**, which follows a different set of rules.

## 5. When Can Methods Still Overload with Different Return Types?

A pair of methods with the same name is validly overloaded when **their parameter lists differ** according to Java rules. Their return types **may be the same or different**, but that difference does not determine the overload:

~~~java
class Converter {
    int parse(int number) {
        return number;
    }

    String parse(String text) {
        return text.trim();
    }
}
~~~

`parse(int)` and `parse(String)` are valid because **the parameter types differ**, not because of the int/String return types. Conversely, `int parse(String)` and `String parse(String)` in the same class will conflict.

| Two Declarations | Valid? | Distinguishing Factor |
| --- | --- | --- |
| `int f()` / `String f(int)` | Yes | Number of parameters |
| `int f(int)` / `String f(String)` | Yes | Parameter types |
| `int f(int,String)` / `String f(String,int)` | Yes | Order of types |
| `int f()` / `String f()` | **No** | Duplicate `f()` |
| `int f(int)` / `long f(int)` | **No** | Duplicate `f(int)` |

With generic methods, two types such as `List<String>` and `List<Integer>` can also cause a **name clash after erasure**, even though they look different in source code. Do not draw conclusions solely from return types or how type arguments are written.

## 6. Changes That Cannot Save Two Duplicate Signatures

Renaming a parameter from `userId` to `accountId`, changing `public` to `private`, changing `static` to instance, or adding `final` or `throws IOException` all **do not** create an overload when the method name and parameter signature remain the same. Declarations with different behavior, exceptions, or access modifiers still do not become two valid overloads in the same class if their signatures match.

How to review: temporarily strip away the return type/modifiers/parameter names/throws; compare the method name and parameter type list, then consider generic erasure and override-equivalent rules if needed. This lesson focuses on clarifying why the return type only describes **the result** and cannot serve as **a method overload selector**.

## 7. Distinguishing Overloading from Overriding

The two concepts are easy to confuse because both use the same method name.

**Overloading**: in a class or related hierarchy, there are multiple methods with the **same name but different parameters**. The compiler selects an overload from the applicable methods according to the argument types and resolution rules.

**Overriding**: a subclass provides an alternative implementation for an **instance method with a matching signature** in a superclass or implements the corresponding contract from an interface. Overriding has its own rules regarding return type, visibility, and checked exceptions.

Example of overriding with a covariant return type:

~~~java
class Vehicle {
    Vehicle copy() {
        return new Vehicle();
    }
}

class Bicycle extends Vehicle {
    @Override
    Bicycle copy() {
        return new Bicycle();
    }
}
~~~

The method `Bicycle.copy()` returns `Bicycle`, which is more specific than `Vehicle`, yet this is an **override** because it has the same signature `copy()` in an inheritance relationship, **not a new overload**.

### 7.1. Why Is a Covariant Return Type Accepted in Overriding?

A call site expecting `Vehicle` can still receive a `Bicycle` result because `Bicycle` is a subtype of `Vehicle`. Therefore, Java allows a **covariant return** with reference types when overriding conditions are met.

Within the **same class**, you cannot write both `Vehicle copy()` and `Bicycle copy()` with the same parameters, because those are still two method declarations with duplicate signatures. What is allowed is for **a subclass to replace the implementation** of a superclass method in a compatible way.

### 7.2. With Primitives, There Is No Covariant Return

~~~java
class Base {
    int code() {
        return 1;
    }
}

class Derived extends Base {
    // @Override
    // long code() { return 2L; } // Invalid: return int and long
}
~~~

If uncommented, both declarations still have the same signature `code()`; changing `int` to `long` in the subclass is not valid for overriding. The fact that `int` can widen to `long` **does not** allow a primitive return type of an override to change.

In overriding, **a compatible return type** is a validity check condition, but **not a component that distinguishes two overloads**.

### 7.3. Static Method Hiding Is Not Overloading by Return Type

If a subclass declares a `static` method with the same signature as an inheritable static method from the superclass, that is **method hiding** when valid. Hiding also has rules for return-type compatibility and does not turn a differing return type into an overload. Do not use `static` to “work around” the issue of two methods having the same signature.

## 8. How Does Overload Resolution Happen at the Call Site?

When writing a call such as `calculate(10)`, the compiler determines the method name, accessible methods, argument types/count, and applies rules to select the appropriate method.

For example:

~~~java
class Demo {
    static String choose(long value) {
        return "long";
    }

    static String choose(Integer value) {
        return "Integer";
    }

    public static void main(String[] args) {
        System.out.println(choose(10));
        System.out.println(choose(Integer.valueOf(10)));
    }
}
~~~

This is a runnable program in the file **`Demo.java`**. With JDK 17:

~~~bash
javac Demo.java
java Demo
~~~

Stdout:

~~~text
long
Integer
~~~

At `choose(10)`, the literal argument `10` has type `int`; primitive widening to `long` is considered in the strict invocation phase before the option requiring boxing to `Integer`. At `choose(Integer.valueOf(10))`, the argument has type `Integer`, so the version accepting `Integer` is a direct match.

This illustrates that overloading **does not simply look at the return type**. Overload selection is governed by many rules: primitive widening, boxing/unboxing, varargs, generic inference, method applicability, and most-specific selection. You should not invent a rule of thumb like “same name + compiler looks at the receiving variable” because it will lead to wrong predictions.

### 8.1. Using `null` Can Cause an Ambiguous Overload

~~~java
class NullChoice {
    static String describe(String value) {
        return "String";
    }

    static int describe(Integer value) {
        return 1;
    }

    public static void main(String[] args) {
        // describe(null); // Error: ambiguous between String and Integer

        System.out.println(describe((String) null));
        System.out.println(describe((Integer) null));
    }
}
~~~

If saved as **`NullChoice.java`** and run:

~~~bash
javac NullChoice.java
java NullChoice
~~~

Stdout of the version with the ambiguous line commented out:

~~~text
String
1
~~~

Both overloads are **valid** because their parameters are `String` and `Integer`, respectively. However, the expression `null` can convert to both reference types, neither of which has a clear subtype relationship to choose a more specific method, so the uncast call `describe(null)` is **ambiguous**.

Even if someone wants to assign the result of that call to a `String` variable, **the return type cannot arbitrarily serve as a “second signature”** to legitimize an ambiguous call. The clear resolution is to choose a more appropriate method name, use different parameters, or, when intentional, pass or cast an argument of a specific type.

### 8.2. The Result of a Value-Returning Method Can Be Ignored

~~~java
class Cleanup {
    static int compute(int n) {
        return n * 2;
    }

    static void run() {
        compute(10); // The result is ignored, yet the call is still valid
    }
}
~~~

Here, there is no “result-receiving” variable of any kind at the caller; `compute(10)` is still resolved. The language design does not require the caller to provide a desired result type for every call.

## 9. Varargs and Arrays: Two Forms That Can Share the Same Signature

Another misconception is that a `String...` parameter creates an overload different from `String[]`:

~~~java
class VarargsWrong {
    void join(String... parts) { }

    // void join(String[] parts) { } // Error: same signature when checked
}
~~~

`String...` is the syntax for declaring a **variable arity parameter**; in essence, that formal parameter has array type `String[]`. Therefore, you cannot declare two methods like those above in the same class merely by switching between varargs and array notation.

A genuinely different-parameter overload could be:

~~~java
class Joiner {
    void join(String text) { }

    void join(String... parts) { }
}
~~~

`join(String)` and `join(String[])` have different formal parameter types. However, calls with varargs also have applicability and most-specific rules; you must consider carefully if adding closely related overloads makes call behavior hard for callers to predict.

**Takeaway:** when comparing signatures, evaluate the formal parameter type according to Java's rules, not merely the textual syntax `...` and `[]`.

## 10. Generic Type Erasure: Different on the Surface, Yet Still Conflicting

Java generics make determining overload declarations slightly more complex. Consider:

~~~java
import java.util.List;

class ListService {
    void process(List<String> names) { }

    // void process(List<Integer> numbers) { }
}
~~~

If uncommented and compiled, Java rejects these two methods due to a **name clash / same signature erasure**. The two parameters look different (`List<String>` and `List<Integer>`), but upon **type erasure**, both have the erasure `List`. Java does not allow creating two overloads like this in the same class.

The error message typically looks like:

~~~text
name clash: process(List<Integer>) and process(List<String>)
have the same erasure
~~~

The actual wording may vary by JDK; the key message is **a conflict after erasure**.

This is a *different yet related* issue to the error of differing only in return type:

- `int f(int)` and `String f(int)`: duplicate source signature because only the return type differs.
- `void process(List<String>)` and `void process(List<Integer>)`: attempt to differentiate by generic type arguments yet conflict on **erasure**, even though they do not differ only in return type.

### 10.1. Renaming the Type Parameter Also Does Not Create an Overload

~~~java
class GenericWrong {
    <T> void handle(T value) { }

    // <U> void handle(U value) { } // Wrong: equivalent signature
}
~~~

The two generic methods have the same parameter structure; changing the symbol `T` to `U` does not create two overloads. Type parameter names are local to the declaration.

### 10.2. How to Design Valid Generic APIs

If two operations serve different purposes, give them specific names:

~~~java
import java.util.List;

class Processor {
    void processNames(List<String> names) { }

    void processIds(List<Integer> ids) { }
}
~~~

If a single generic behavior is genuinely appropriate, you can declare one generic method:

~~~java
import java.util.List;

class Printer {
    static <T> int count(List<T> items) {
        return items.size();
    }
}
~~~

A single `count(List<T>)` method serves many element types without needing to overload by type argument. Do not add a generic method just to disguise genuinely different behaviors: having the same result type does not mean two business tasks are the same.

## 11. Return Type, Method Signature, and JVM Descriptor Are Not the Same Concept

An advanced point that easily sparks debate: the **JVM method descriptor** in bytecode **does describe the result type**, whereas the **Java source method signature** used to determine overloads **does not use the return type to distinguish methods**.

For example, the JVM descriptor of a method taking `int` and returning `int` differs from the descriptor of a method taking `int` and returning `String`. However, that **does not allow writing in a Java source class** two methods `int f(int)` and `String f(int)`.

You may also encounter **bridge methods** generated by the compiler when supporting generics or covariant overriding in bytecode. They serve linkage and execution compatibility; this is **not a loophole** for an application to write two source declarations with duplicate signatures and treat them as overloads.

At the Java source level, follow the signature definition in JLS `8.4.2 and the method declaration rules. When debugging `javac`, focus on the **method name, formal parameter types, and erasure/subsignature** instead of confusing them with the JVM-level descriptor.

## 12. Constructor Overloading Also Depends on Parameters

A constructor has no return type declaration and does not use an independent method name: the constructor name is the class name. Constructors can be overloaded based on the number/type/order of parameters:

~~~java
class Point {
    private final int x;
    private final int y;

    Point() {
        this(0, 0);
    }

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    Point(int coordinate) {
        this(coordinate, coordinate);
    }
}
~~~

This is a class declaration snippet; the three constructors have parameter lists `()`, `(int, int)`, and `(int)`, so they validly coexist. You cannot create a new constructor that “differs only in return type” because **constructors do not have a return type**.

Writing `void Point() { }` is not a constructor declaration: it is a **method named Point** returning `void` (if valid in the declaration context), and does not replace a constructor. This confusion often makes learners think they have defined a constructor overload.

## 13. How to Design an API When Multiple Result Types Are Truly Needed

Suppose a data source can be presented in multiple forms. There are several better options than “two methods with identical parameters and different return types”:

### 13.1. Use Different Names According to Meaning

~~~java
class Student {
    private final int age;

    Student(int age) {
        this.age = age;
    }

    int ageValue() {
        return age;
    }

    String ageText() {
        return age + " tuổi";
    }
}
~~~

This is easiest to understand when the two results serve two different purposes. Reading `ageValue()` and `ageText()` in the code is enough to understand the intent.

### 13.2. Return a Value Object Containing Both Pieces of Information

~~~java
record AgeView(int value, String text) { }

class AgeService {
    AgeView describe(int age) {
        return new AgeView(age, age + " tuổi");
    }
}
~~~

This is a method inside a class together with a package-private top-level record in the same example; Java 17 supports records. A result containing both a number and a string is appropriate if they belong to **one descriptive operation**. Save `AgeView.java` and `AgeService.java` separately by convention as the codebase grows larger.

### 13.3. A General Result Type When the Contract Is Truly Shared

If the operation is singular and the result has multiple variants, it can be modeled using an appropriate interface or hierarchy instead of two methods differing only in return type. The caller will inspect the result type according to the contract.

Do not use `Object` and cast indiscriminately just to simulate “returning `int` in one case, `String` in another” when a stronger and clearer data type can be used.

### 13.4. Valid Generic Return When the Input Specifies the Type

~~~java
class Defaults {
    static <T> T supplied(T value) {
        return value;
    }
}
~~~

This is a single generic method, not two overloads. Java infers `T` from the input value; for example, `Defaults.supplied("A")` can return `String`. A generic method should not be taken as proof that Java accepts two methods with the same signature but different return types.

## 14. Checking Invalid and Valid Cases

| Declaration (same class unless stated otherwise) | Verdict | Explanation |
| --- | --- | --- |
| `int f()` and `String f()` | Invalid | Duplicate `f()` |
| `int f(int x)` and `String f(int y)` | Invalid | Duplicate `f(int)`; parameter names do not matter |
| `int f(int)` and `int f(long)` | Valid | Different parameter types |
| `int f(int)` and `String f(String)` | Valid | Different parameter types; differing return types are allowed |
| `void f(int, String)` and `void f(String, int)` | Valid | Different order of parameter types |
| `public int f(int)` and `private int f(int)` | Invalid | Access modifiers do not change the signature |
| `static int f(int)` and `int f(int)` | Invalid | Static vs. instance does not distinguish overloads |
| `void f(String...)` and `void f(String[])` | Invalid | Varargs is an array type in the signature |
| `void f(List<String>)` and `void f(List<Integer>)` | Invalid | Name clash due to identical erasure |
| `<T> void f(T)` and `<U> void f(U)` | Invalid | Equivalent generic signatures |
| Superclass `Number value()` and subclass `Integer value()` | Can be valid | Covariant **override**, not an overload |
| Superclass `int value()` and subclass `long value()` | Invalid | Incompatible primitive return type for overriding |
| `A()` and `A(int)` as constructors of class `A` | Valid | Constructor overloading via different parameters |

The “valid” verdicts in the table assume there are no other conflicts regarding generic erasure, inheritance, or declaration constraints; the table illustrates the fundamental conditions directly related to the return type.

## 15. Self-Check Exercises

**Question 1.** Can you declare two methods `String get()` and `int get()` in the same class? Why?

**Answer:** No. Both have the signature `get()`; the return type is not a component that distinguishes overloads.

**Question 2.** Are the two methods `int calc(int a, long b)` and `String calc(long a, int b)` a valid overload?

**Answer:** Yes, because the order of the formal parameter types differs: `calc(int, long)` and `calc(long, int)`. Having different return types is not the deciding factor.

**Question 3.** Does changing `int id(int value)` to `long id(int number)` create a new method overload?

**Answer:** No. Only the return type and parameter variable name change; the signature is still `id(int)`.

**Question 4.** `Parent Number create()` and `Child Integer create()` have the same parameter list and are in an inheritance relationship. Why can this be valid?

**Answer:** Because `Child.create()` can **override** `Parent.create()` with a covariant return type if the other overriding rules are satisfied. These are not two different overloads.

**Question 5.** Why do `void process(List<String>)` and `void process(List<Integer>)` not create a valid overload?

**Answer:** Java generics use type erasure; both parameterized `List` types have the erasure `List`, so the two declarations cause a name clash at compile time.

**Question 6.** Do `void show(String... a)` and `void show(String[] b)` have different signatures?

**Answer:** No. The varargs parameter `String...` has array type `String[]` for signature purposes.

**Question 7.** In a class containing `long read(long)` and `String read(String)`, does having two different return types violate overloading?

**Answer:** No. The two methods have different parameters, so they form a valid overload; having different return types causes no issue.

**Question 8.** Can the conflict between `int getValue()` and `String getValue()` be resolved by assigning the results to `int` and `String` respectively at the caller?

**Answer:** No. There is already a declaration error of two methods with duplicate signatures. The fix is to change the **method name**, change the **parameters according to actual API needs**, or design a clear result type.

**Question 9.** In a program with `choose(String)` and `choose(Integer)`, can a call `choose(null)` fail with an ambiguity error?

**Answer:** Yes. `null` matches both parameter types, which are unrelated by any subtype relationship to pick one specific overload; you can pass a value with an explicit type or use an appropriate cast.

**Question 10.** Why does the JVM descriptor include the return type while Java still forbids two source methods that differ only in their return type?

**Answer:** These are **two different levels of description**. The Java source method signature per the JLS governs declaration/overloading; the JVM descriptor serves representation and linkage in bytecode. Source-level rules still forbid those two declarations.

## 16. Checklist When Encountering “method is already defined”

1. **Read the method name** and identify declarations with the same name in the class or related hierarchy.
2. **Rewrite the list of parameter types in order**, ignoring parameter variable names; for example, `calculate(int, String)`.
3. **Do not rely on the return type, modifiers, or `throws`** expecting to separate two identical signatures.
4. **If generics are involved**, check erasure, type parameters, and the corresponding declaration constraints.
5. **If varargs are involved**, remember that a `T...` parameter corresponds to the array type `T[]` when evaluating signatures.
6. **If a subclass is involved**, determine whether the intent is overriding or overloading; check covariant return for reference types when overriding.
7. **If you want two different data representations from the same input**, prefer meaningful method names, a value object, or an appropriate generic contract.
8. **Recompile with `javac`** after fixing, then test representative calls to catch ambiguous overloads or unexpected overload selection.

### Key Takeaway

**Overloading is not based on the return type.** In Java, when two methods share the same name, **differing in the number, types, or order of parameter types** are the common ways to distinguish overloads. If you only change `int` to `String` in the return of two methods with the same signature, the compiler reports a duplicate method. **Covariant returns in overriding** and **return types in the JVM descriptor** are real concepts, but **they do not negate this rule** in Java method declarations.
