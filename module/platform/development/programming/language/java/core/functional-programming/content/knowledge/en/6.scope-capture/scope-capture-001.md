# Scope of Lambda Parameters and Local Variables (Java)

## 1. Lesson Objectives

When writing a lambda, we can declare parameters right before the `->` token and declare local variables inside a block body. At the same time, a lambda can reference names that already exist in the enclosing class or method. To understand which variable a name refers to and whether duplicate declarations are allowed, it is necessary to distinguish **scope**, **shadowing**, and **variable capture**.

In Java, a lambda **does not introduce a new level of name scoping like declaring a new class**. It still creates a scope for its own parameters and local variables, but **cannot use these names to redeclare a local variable or parameter that is already in the enclosing scope**. This is an important difference from an anonymous class.

After this lesson, you will be able to:
- Identify the scope of lambda parameters, variables declared in a block, and variables located in an outer block.
- Recognize name-collision errors at compile time.
- Distinguish declaring a new name in a lambda from reading/capturing an outer variable.
- Understand why `this` in a lambda points to the enclosing object, whereas `this` in an anonymous class points to the anonymous class object.
- Write nested lambdas where each parameter has a clear, non-conflicting name.

## 2. How Is the Scope of a Declaration Understood?

**Scope** is the region of a program in which a declared name can be referenced according to Java's rules. Scope is determined primarily by the declaration's position in the source code, not by when the lambda is executed.

Example (illustrative snippet placed inside a method):

~~~java
java.util.function.Function<String, String> normalize = value -> {
    String cleaned = value.trim();
    return cleaned.toUpperCase(java.util.Locale.ROOT);
};
~~~

Here:

| Name | Where is it declared? | Valid usage scope |
| --- | --- | --- |
| `normalize` | Local variable of the method containing the lambda | The remainder of the method block, from the declaration position according to Java rules |
| `value` | Parameter of the lambda | The body of that lambda |
| `cleaned` | Local variable in the lambda's block | From declaration to the end of the corresponding block |
| `String`, `Locale` | Type names | According to type/import naming rules, separate from local variable scope |

For example, after the `{ ... }` body of the lambda ends, outside code cannot access the name `cleaned`. Each time the functional method is called, the parameters and local variables of that execution have their own values according to execution rules.

### 2.1. A Lambda Parameter Only Has Scope Within the Lambda Body

There are three common ways to write the parameter of a lambda that takes one value:

~~~java
java.util.function.Function<String, Integer> a = text -> text.length();
java.util.function.Function<String, Integer> b = (text) -> text.length();
java.util.function.Function<String, Integer> c = (String text) -> text.length();
~~~

The three independent declarations in the illustrative snippet above are all valid and all represent taking the length. The name `text` is reused because **each parameter belongs to a different lambda** and the parameter scopes are not nested inside one another.

In a multi-parameter lambda, two names in the same parameter list must be different:

~~~java
java.util.function.BiFunction<Integer, Integer, Integer> add =
        (left, right) -> left + right;
~~~

The following snippet is **intentionally syntactically invalid** and should not be put into a runnable program:

~~~java
// ERROR: two parameters in the same lambda cannot have the same name.
// BiFunction<Integer, Integer, Integer> wrong = (x, x) -> x;
~~~

### 2.2. Local Variables in a Block-Style Lambda Body

A lambda body can be a single expression or a block:

~~~java
java.util.function.Function<String, String> simple =
        input -> input.trim();

java.util.function.Function<String, String> detailed = input -> {
    String trimmed = input.trim();
    String upper = trimmed.toUpperCase(java.util.Locale.ROOT);
    return upper;
};
~~~

With a block, Java's normal rules for local variables continue to apply: each name in the same scope must be validly declared, a variable must be assigned a value before being read, and `return` must match the result type of the functional interface.

The variables `trimmed` and `upper` only exist inside the block body of `detailed`; they cannot be accessed from outside by writing `detailed.trimmed`. A lambda does not create an object with public fields corresponding to these variables.

## 3. The Most Important Rule: Do Not Redeclare a Local Variable Already in the Enclosing Scope

When a local variable or method parameter is already in scope at the lambda's position, that same name cannot be used for a lambda parameter:

~~~java
// Illustration with compile error:
void example(String name) {
    // ERROR: name is a method parameter already in scope.
    // java.util.function.Function<String, String> bad =
    //         name -> name.trim();
}
~~~

Fix: choose a different parameter name, such as `value`:

~~~java
void example(String name) {
    java.util.function.Function<String, String> good =
            value -> name + ":" + value.trim();
}
~~~

This is an **illustrative method placed inside a class**, not a standalone program. The `good` (a variable of type `Function`) uses `value` as the lambda parameter and references `name` from the enclosing method.

The same rule applies to local variables declared **inside** the lambda. You cannot redeclare an outer variable with the same name in the lambda body even if you add a pair of curly braces:

~~~java
void count() {
    int total = 10;

    // ERROR: local total is already in the enclosing scope.
    // Runnable bad = () -> {
    //     int total = 20;
    //     System.out.println(total);
    // };

    Runnable good = () -> {
        int increment = 2;
        System.out.println(total + increment);
    };
    good.run();
}
~~~

The `count()` method placed inside a class will be valid if the commented error example lines are omitted. The `good` lambda references the value `total` and uses a new variable `increment`, so there is no name conflict.

**Common pitfall:** adding a `{ }` block does not always allow renaming a local variable already in scope. Java also forbids a local variable in a child block from being declared with the same name as a local variable in a parent block whose scope covers it.

### 3.1. Why Can a Name Be Reused in Two Sibling Lambdas?

Two lambdas declared side by side have separate parameter scopes, not the same parameter scope:

~~~java
java.util.function.Function<String, String> first = text -> {
    String result = text.trim();
    return result;
};

java.util.function.Function<String, String> second = text -> {
    String result = text.toUpperCase(java.util.Locale.ROOT);
    return result;
};
~~~

Both lambdas have a parameter `text` and a local variable `result`, but those declarations belong to **two different lambda bodies that do not enclose each other**. Therefore, the code is valid.

This case should also not be interpreted as "a lambda can shadow any outer name": the names `text` and `result` of the first lambda are **not** in the scope of the second lambda. They do not conflict because the scopes are independent.

### 3.2. When the Outer Name Is Not Yet in Scope

In a Java block, a local variable's scope begins from its declaration according to language rules, not from the beginning of the entire block. Therefore, having the same name in non-overlapping regions can be valid.

Illustrative example:

~~~java
Runnable earlier = () -> {
    int later = 1;
    System.out.println(later);
};
int later = 2;
~~~

When the lambda is written, the outer block's local variable `later` declared on the later line is not yet in scope at that point. However, this naming style easily misleads readers; it is still better to use names that reflect meaning.

## 4. Nested Lambdas: Checking Multiple Scopes Simultaneously

A lambda can return another lambda:

~~~java
java.util.function.Function<Integer,
        java.util.function.IntUnaryOperator> adder =
        outer -> inner -> outer + inner;
~~~

How to read it:

- `outer` is the parameter of the outer lambda.
- `inner` is the parameter of the inner lambda.
- The inner lambda body sees both `inner` and `outer`, because the inner lambda body is within the scope of the outer lambda's parameter.
- `adder.apply(3).applyAsInt(4)` returns 7.

You cannot use the same name `outer` for the inner lambda's parameter:

~~~java
// ERROR: outer lambda parameter is already in scope.
// Function<Integer, IntUnaryOperator> wrong =
//         outer -> outer -> outer + 1;
~~~

Nor can you declare an additional local variable `outer` in the inner lambda's block. When nesting lambdas, you should use names like `outerIndex`, `innerIndex`, `item`, or actual domain names instead of ambiguous symbols.

## 5. Field Names Differ from Local Variable Names

The rule forbidding duplicate declarations of a **local variable or parameter** in the enclosing scope does not forbid a lambda parameter from having the same name as a **field**.

Illustrative example placed in a class:

~~~java
class ScopeWithField {
    private String label = "field";

    void show() {
        java.util.function.Function<String, String> f =
                label -> label.toUpperCase(java.util.Locale.ROOT);
        System.out.println(f.apply("local")); // LOCAL
        System.out.println(this.label);       // field
    }
}
~~~

The lambda's `label` parameter can shadow the `label` field when using the simple name in the lambda body. You can explicitly access the enclosing object's field using `this.label` in an instance context.

Conversely, if a method has a parameter `label` in scope, using `label` as a lambda parameter inside the method is a compile error. That is, **you must distinguish fields from local variables/formal parameters** when checking name conflicts.

## 6. `this` and `super`: Lambdas Use the Enclosing Class Context

According to JLS §15.27.2, the meaning of names and of `this` and `super` inside a lambda largely preserves the enclosing context, except for names newly declared by lambda parameters. A lambda does not create a new class instance with its own `this` like an anonymous class does.

Suppose inside an instance method:

~~~java
Runnable lambda = () -> System.out.println(this.owner);
~~~

`this` is the object currently executing the enclosing method, so it reads the `owner` field of that object. In an anonymous class:

~~~java
Runnable anonymous = new Runnable() {
    private final String owner = "anonymous";

    @Override
    public void run() {
        System.out.println(this.owner);
    }
};
~~~

`this` inside the `run()` method is the instance of the anonymous class, because that is the context of a newly declared class.

With `super` in a lambda, lookup is also based on the lexical context of the enclosing class when there is a valid call. In a `static` context, `this` or `super` cannot be used as if there were an enclosing instance.

**Note:** how Java implements the object for a lambda in the JVM is a runtime detail; you should not rely on the generated class identity, internal class name, or treat `this` as the object representing the lambda itself.

## 7. Name Scope and Variable Capture Are Two Separate Rules

Scope determines **whether a name can be referenced**; capture determines how a lambda is allowed to use a value from the outer context.

Java only allows a lambda to capture a **local variable/parameter of the enclosing method** if it is `final` or **effectively final** (after being assigned according to Java rules, it is not reassigned). For example:

~~~java
void sample() {
    String prefix = "Hi ";
    java.util.function.Function<String, String> greet =
            name -> prefix + name;
    System.out.println(greet.apply("An")); // Hi An
}
~~~

Example that **does not compile** if uncommented:

~~~java
void invalidCapture() {
    int counter = 0;
    // java.util.function.IntSupplier reader = () -> counter;
    counter++;
    // ERROR if reader is declared above:
    // counter is modified so it is not effectively final.
}
~~~

This case is not a duplicate-name error; the lambda is **reading** the outer variable by the right name, but the outer variable does not satisfy the capture constraint.

**Further distinction:**
- A lambda parameter itself can be reassigned in the body if not declared `final`, although doing so is usually less clear. The effectively final condition mentioned above applies to **local variables captured from outside**.
- A class field can change and be accessed in a lambda if access rules allow. This is not restricted by the effectively final rule for local variables, though it can make behavior depend on shared state.
- An effectively final local reference can point to a **mutable** object. Forbidding reassignment of the reference variable does not mean forbidding modification of the state of the object it points to.

Name scope, immutability of the reference variable, and immutability of the object are **three different issues**.

## 8. Parameter Declaration Forms and Name Checking

Java supports lambda parameters with explicit types, inferred types, or `var` (Java 11+) depending on the context:

~~~java
java.util.function.BiFunction<Integer, Integer, Integer> sum1 =
        (Integer left, Integer right) -> left + right;

java.util.function.BiFunction<Integer, Integer, Integer> sum2 =
        (left, right) -> left + right;

java.util.function.BiFunction<Integer, Integer, Integer> sum3 =
        (var left, var right) -> left + right;
~~~

All three are valid on Java 17. You cannot mix explicit type declarations with type inference in the same list, or mix `var` with undeclared types:

~~~java
// INTENTIONALLY DOES NOT COMPILE:
// BiFunction<Integer,Integer,Integer> bad1 =
//         (Integer left, right) -> left + right;
// BiFunction<Integer,Integer,Integer> bad2 =
//         (var left, right) -> left + right;
// BiFunction<Integer,Integer,Integer> bad3 =
//         (var left, Integer right) -> left + right;
~~~

Using `var` for lambda parameters **does not** relax the naming rules: each parameter name must still be unique in the list and must not conflict with a local/parameter currently in the enclosing scope.

A name is just an **identifier**: you can rename `text` to `inputText` without changing the nature of the computation, as long as references in the body are updated consistently. However, when that name is already used by an outer variable, you must choose another name to avoid conflict.

## 9. Complete Java 17 Example

Create the file **LambdaScopeLesson.java**. The program demonstrates:
- Capturing an effectively final local.
- Declaring a separate local inside a block-style lambda body.
- Using a field in a lambda via `this`.
- Naming parameters in nested lambdas.
- Reusing the name `result` in two sibling lambdas.
- Comparing `this` of a lambda and an anonymous class.

~~~java
import java.util.Locale;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;

public class LambdaScopeLesson {
    private final String owner = "instance";
    private int increment = 5;

    void demonstrate() {
        String prefix = "pre";

        Function<String, String> process = input -> {
            String cleaned = input.trim();
            return prefix + ":" + cleaned;
        };
        IntUnaryOperator add = number -> number + this.increment;
        Function<Integer, IntUnaryOperator> sum =
                outer -> inner -> outer + inner;

        Function<String, String> first = text -> {
            String result = text.trim();
            return result;
        };
        Function<String, String> second = text -> {
            String result = text.toUpperCase(Locale.ROOT);
            return result;
        };

        Runnable lambda = () ->
                System.out.println("lambda this=" + this.owner);
        Runnable anonymous = new Runnable() {
            private final String owner = "anonymous";
            @Override
            public void run() {
                System.out.println("anonymous this=" + this.owner);
            }
        };

        System.out.println(process.apply(" Java "));
        System.out.println(add.applyAsInt(7));
        System.out.println(sum.apply(3).applyAsInt(4));
        System.out.println(first.apply(" Hi "));
        System.out.println(second.apply("Hi"));
        lambda.run();
        anonymous.run();
    }

    public static void main(String[] args) {
        new LambdaScopeLesson().demonstrate();
    }
}
~~~

Compile with JDK 17 or later:

~~~bash
javac --release 17 LambdaScopeLesson.java
java LambdaScopeLesson
~~~

Verified stdout:

~~~text
pre:Java
12
7
Hi
HI
lambda this=instance
anonymous this=anonymous
~~~

Explanation:
1. `prefix` is a local of `demonstrate` and is not reassigned, so `process` can capture it. `input` and `cleaned` are the lambda's own parameter/variable.
2. `add` takes the parameter `number` and reads the field `increment` via `this`: 7 + 5 = 12.
3. `sum` consists of two nested lambdas; `outer = 3` and `inner = 4`, so the result is 7.
4. The two lambdas `first` and `second` use the same names `text` and `result` but belong to independent scopes; both are valid.
5. `lambda` reads the `owner` field of `LambdaScopeLesson`, while the anonymous class declares its own `owner` field; therefore, the last two lines differ.

The program was actually compiled with `javac --release 17` and ran successfully. The **intentionally invalid** example snippets in earlier sections have been commented out so they are not mixed with the standalone runnable program.

## 10. Common Errors and Fixes

| Error | Cause | Fix |
| --- | --- | --- |
| Naming a lambda parameter the same as an outer local variable | Redeclaration within the local's scope | Rename the lambda parameter |
| Declaring a local inside a lambda with the same name as a method parameter | The method parameter is still in scope | Use a different local name |
| Two parameters with the same name in one lambda | Cannot have two formal parameters with the same identifier | Rename one of them |
| Inner lambda redeclaring an outer lambda parameter name | The outer parameter's scope covers the inner lambda | Use different names |
| Thinking `this` is the lambda object | A lambda does not have its own lexical `this` | Understand `this` according to the enclosing class |
| Capturing a local and then reassigning that local | The local is not effectively final | Put state in an object with a clear contract or redesign the operation |
| Placing a variable in a lambda body and accessing it from outside | The name only exists inside the lambda block | Return a value from the lambda or store the result at the call site |
| Assuming two adjacent lambdas cannot share parameter names | Confusing independent scopes with nested scopes | Reusing the name is valid, though meaningful names are preferable |

A practical way to check is to trace the "name visibility region" from declaration to the end of its scope, and then check at each new declaration whether the name already has a local/parameter in an enclosing scope. When an error occurs, the compiler usually reports that the variable is already defined or declared in an enclosing scope.

## 11. Self-Check

**Question 1.** Why is the following example invalid?

~~~java
// void work(int value) {
//     java.util.function.IntUnaryOperator op = value -> value + 1;
// }
~~~

Because `value` is already a parameter of the enclosing method; a lambda parameter cannot reuse this name within the active scope.

**Question 2.** Can two sibling lambdas both use the parameter `item`?

**Yes.** Each parameter only belongs to its own lambda body scope; there is no conflict when the two scopes are independent.

**Question 3.** If a lambda nested inside another lambda needs to read the parameter `outer`, can it name its own parameter `outer` as well?

**No.** The scope of the outer lambda's parameter covers the inner lambda's body. The inner lambda can **read** `outer`, but cannot **redeclare** a parameter with the same name.

**Question 4.** Does a lambda have its own `this` field?

**No.** In an instance context, `this` denotes the enclosing instance according to lexical context. An anonymous class has its own instance and `this`.

**Question 5.** Does a captured local being effectively final make the object it references immutable?

**No.** That constraint forbids reassigning the local variable; if the referenced object is mutable, its contents can still change.

**Question 6.** Why does renaming an outer local to a different name resolve some lambda errors?

Because the rule forbidding duplicate identifiers depends on declaration names having overlapping scopes. Renaming resolves the name collision, but you must ensure all references to the variable are updated with the right meaning.

## 12. Reference Documentation

- [Java Language Specification 17, §6.3 – Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3).
- [Java Language Specification 17, §6.4 – Shadowing and Obscuring](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.4).
- [Java Language Specification 17, §15.27.1 – Lambda Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.1).
- [Java Language Specification 17, §15.27.2 – Lambda Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.2).
- [Java Language Specification 17, §6.5.6.1 – Simple Expression Names (capture)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.5.6.1).

**Key Takeaway:** Parameters and locals inside a lambda have their own scope but cannot be given the same name as a local/parameter currently present in the enclosing scope. Two independent lambdas can reuse names. A lambda sees `this`/`super` according to the enclosing class; capturing a local from outside also requires that variable to be `final` or effectively final. Understanding these boundaries helps avoid compile errors and makes code easier to read.
