# Restrictions on Redeclaring Enclosing Variables in Java Lambdas

## 1. The Problem and the Core Rule

Lambdas make it possible to pass behavior as a value of a **functional interface**, for example `IntUnaryOperator operation = x -> x + 1;`. When writing a lambda inside a method, the program often already has parameters or local variables in the enclosing scope. An important question is: **can a lambda reuse those names to declare new parameters or local variables?**

In Java, **you cannot declare a parameter or local variable inside a lambda with the same name as a local variable, method parameter, `catch` parameter, or another lambda parameter that is still in the enclosing scope at the declaration site**. This is a compile-time error caused by two declarations having a name conflict; it is not an error that only appears at runtime.

An intentionally **non-compiling** example:

```text
void demo() {
    int number = 10;
    IntUnaryOperator operation = number -> number + 1;
    // Error: lambda parameter 'number' collides with outer local variable.
}
```

Conversely, a lambda is allowed to **read** an outer local variable if it satisfies the `final` or *effectively final* condition, and a lambda parameter can **share a name with a field of the class**. These cases must be distinguished accurately.

After this lesson, you will be able to determine which names are allowed, which names are forbidden, fix name conflicts, explain the difference between a lambda and an anonymous class, and understand the relationship with *variable capture*.

## 2. Distinguishing Scope Concepts

**Scope** is the region of a program in which a declared name can be used to refer to that variable or parameter. A method, block `{ ... }`, `catch` clause, or lambda expression each has its own scope rules.

An **enclosing variable** in this lesson mainly refers to a local variable or parameter that already exists in the scope containing the lambda expression. For example, `int offset = 3;` declared before the lambda in the same method is an enclosing local variable.

**Shadowing** is declaring a new name that matches an existing name, causing the new name to take precedence at the corresponding location. Java allows some forms of shadowing, such as a lambda parameter shadowing a **class field**; however, it does not allow a lambda parameter or local variable to be declared with the same name as a **local variable already in the enclosing scope**.

**Variable capture** occurs when a lambda uses a local variable or parameter outside its own declaration, for example `n -> n + offset` reading `offset`. When capturing a local variable, that variable must be `final` or *effectively final* (not reassigned after initialization).

The four concepts are related but not identical: **name conflict is a declaration issue; capture is referencing an already-declared variable; value mutation is a `final` constraint issue**.

## 3. Rules for Different Kinds of Names

| Existing name in enclosing scope | Redeclare as lambda parameter/local variable? | Explanation |
| --- | --- | --- |
| Local variable of the method | **No**, while the variable is still in scope | Variable declaration conflict |
| Parameter of the enclosing method | **No** | The parameter is a name already in scope |
| Parameter of an enclosing `catch` | **No**, when the lambda is inside the `catch` block | Collides with the exception parameter name |
| Parameter of an enclosing lambda | **No** in a lambda nested inside | The outer parameter name is still in scope |
| Local variable declared in a `{ ... }` block that has ended | **Yes**, can be reused after leaving that scope | The old name is no longer in scope |
| Parameter `n` of another independent lambda | **Yes**, can be reused | Two non-nested lambdas have separate parameter scopes |
| Field `private int amount` of the class | **Yes**, can use `amount` as a parameter | The parameter shadows the field; use `this.amount` to read the field |
| `static` field of the class | **Yes**, can use the same name, accessing the field via the class name | No local variable conflict; should distinguish names clearly in code |

Key takeaway: **not all duplicate names are forbidden in Java**. You must check what *kind of declaration* the duplicate name is, whether its scope is still active, and whether two lambdas are nested.

## 4. Lambdas Do Not Create a Region to Reset Enclosing Variable Names

The example below has a variable `value` in the method:

```text
import java.util.function.IntUnaryOperator;

class DuplicateParam {
    void test() {
        int value = 10;
        IntUnaryOperator op = value -> value + 1;
    }
}
```

This is **code that intentionally does not compile**. `value` on the left of `->` is a declaration of a **new parameter**, while the outer `value` is still in scope in the `test()` method. The compiler reports that the variable is already defined in the method.

Fix by renaming the parameter:

```java
int value = 10;
IntUnaryOperator op = input -> input + value;
```

These two statements illustrate the body of a method with `import java.util.function.IntUnaryOperator;`. Here `input` is the lambda parameter and `value` is the **captured** enclosing variable. If you want to add the constant 10, you can keep `value` without reassigning it; do not name the parameter the same as that variable.

A similar error occurs when declaring a **local variable in the lambda block body**:

```text
import java.util.function.IntUnaryOperator;

class DuplicateLocal {
    void test() {
        int total = 10;
        IntUnaryOperator op = x -> {
            int total = x + 1;
            return total;
        };
    }
}
```

The code above intentionally does not compile because declaring `int total` inside the lambda collides with the `total` variable in the enclosing method. Fix it to `int result = x + 1;` and then `return result;`, or use `x -> x + 1` directly.

The same rule applies if the enclosing scope contains a **method parameter**, such as `void evaluate(int input) { IntUnaryOperator op = input -> input + 1; }` — the lambda parameter `input` collides. Change it to `n -> n + input` if you want to capture `input`.

## 5. A Program Demonstrating Valid Cases

Create the file `LambdaNameScopeDemo.java`:

```java
import java.util.function.Function;
import java.util.function.IntUnaryOperator;

public class LambdaNameScopeDemo {
    private final int amount = 40;

    void demonstrate() {
        int offset = 3;
        IntUnaryOperator plusOffset = number -> number + offset;
        System.out.println(plusOffset.applyAsInt(4));

        IntUnaryOperator first = n -> n + 1;
        IntUnaryOperator second = n -> n * 2;
        System.out.println(first.applyAsInt(4));
        System.out.println(second.applyAsInt(4));

        IntUnaryOperator fieldExample = amount -> amount + this.amount;
        System.out.println(fieldExample.applyAsInt(2));

        Function<Integer, IntUnaryOperator> makeAdder =
                increment -> number -> number + increment;
        System.out.println(makeAdder.apply(5).applyAsInt(7));

        {
            int blockValue = 2;
            IntUnaryOperator useBlock = n -> n + blockValue;
            System.out.println(useBlock.applyAsInt(9));
        }
        IntUnaryOperator afterBlock = blockValue -> blockValue + 1;
        System.out.println(afterBlock.applyAsInt(3));
    }

    public static void main(String[] args) {
        new LambdaNameScopeDemo().demonstrate();
    }
}
```

Compile and run with Java 17 or newer:

```bash
javac --release 17 -encoding UTF-8 LambdaNameScopeDemo.java
java LambdaNameScopeDemo
```

Exact output:

```text
7
5
8
42
12
11
4
```

Step-by-step analysis:

1. `offset` is an enclosing local variable, while `number` is a lambda parameter. The names do not collide so it is valid; the lambda reads `offset = 3` and `4 + 3 = 7`. `offset` is captured and is not reassigned.
2. `first` and `second` both use the parameter name `n`. They are **two independent lambdas**, not nested, so they can reuse the name. `first(4)` gives `5`; `second(4)` gives `8`.
3. The class has a field `amount = 40`. The lambda's `amount` parameter is allowed to shadow this field. `amount` on the left of the addition is the parameter receiving `2`; `this.amount` accesses the field of the object executing `demonstrate()`, giving `42`.
4. `makeAdder` has two **nested** lambdas, but their names are `increment` and `number`, which do not collide. The inner lambda uses the outer lambda's `increment`: `makeAdder.apply(5).applyAsInt(7)` gives `12`.
5. The variable `blockValue = 2` only exists inside the `{ ... }` block. `useBlock` reads it validly and gives `9 + 2 = 11`. Once outside the block, the name `blockValue` is no longer in scope; the `afterBlock` lambda is allowed to declare a **new parameter with the same name** and gives `3 + 1 = 4`.

This is an important example of the difference between **the same name in two non-overlapping scopes** and **redeclaring when the enclosing scope is still active**.

## 6. Nested Lambdas: Do Not Redeclare Outer Parameters

Consider a function returning another function:

```java
Function<Integer, IntUnaryOperator> makeAdder =
        increment -> number -> number + increment;
```

The statement in section 5 is valid because the outer lambda parameter is `increment` and the inner lambda parameter is `number`. If both are changed to `x`:

```text
Function<Integer, IntUnaryOperator> bad =
        x -> x -> x + 1;
```

This is a **snippet that intentionally does not compile**. The inner lambda is inside the outer lambda's body, so the outer parameter `x` is still in scope. You cannot declare a new parameter `x` in the inner lambda. Besides choosing two different names, you should think about names that express their roles: `amount -> number -> amount + number` is easier to understand.

Conversely, two lambdas appearing in two independent statements can reuse `x`:

```java
IntUnaryOperator plusOne = x -> x + 1;
IntUnaryOperator doubleIt = x -> x * 2;
```

These are two statements placed in a method body with `IntUnaryOperator` imported; there is no need to change `x` to `y` in the second lambda. The parameter scope of the first lambda does not extend to the second lambda.

## 7. Class Fields Differ from Local Variables

Given the following class:

```java
class Formatter {
    private String prefix = "Hello ";

    java.util.function.Function<String, String> create() {
        return prefix -> prefix + this.prefix;
    }
}
```

This is a valid class declaration in Java 17. `prefix` on the left of `->` is the **lambda parameter**. `this.prefix` is the field of the `Formatter` object. The two names are the same but belong to different declaration kinds, so it is valid. Using the same name can reduce readability; in practice you should write `name -> name + this.prefix` or choose a domain-meaningful name.

For `static` fields, the clearest way to access them is `ClassName.fieldName` to distinguish them from a same-named parameter. `this` in a lambda keeps the meaning of the enclosing context: in an instance method, `this` is the object containing the lambda expression, **not a new separate object of the lambda body**. In a `static` method, there is no `this`.

The ability to use `this.amount` does not prove that a lambda has its own class scope. Java allows this form of **field shadowing**, while still forbidding redeclaring a name that matches an enclosing local variable currently in scope.

## 8. Contrast with Anonymous Classes

An anonymous class creates its own class body and methods. Therefore, a method parameter of an anonymous class can use the same name as a local variable of the enclosing method, whereas a direct lambda parameter with the same name is forbidden.

The following standalone program illustrates this:

```java
import java.util.function.IntUnaryOperator;

public class AnonymousScopeContrast {
    void demonstrate() {
        int number = 10;
        IntUnaryOperator operation = new IntUnaryOperator() {
            @Override
            public int applyAsInt(int number) {
                return number + 1;
            }
        };
        System.out.println(operation.applyAsInt(5));
        System.out.println(number);
    }

    public static void main(String[] args) {
        new AnonymousScopeContrast().demonstrate();
    }
}
```

Run:

```bash
javac --release 17 -encoding UTF-8 AnonymousScopeContrast.java
java AnonymousScopeContrast
```

Output:

```text
6
10
```

In `applyAsInt(int number)`, the parameter belongs to the **anonymous class method** and is allowed to use the name `number`. Meanwhile, the local variable `number = 10` of `demonstrate()` is not changed. If you wrote `IntUnaryOperator operation = number -> number + 1;` right there, Java would report a duplicate name declaration error.

In addition to the naming difference, `this` inside the anonymous class method points to the **anonymous class instance**, whereas `this` in a lambda (when valid) points to the **object in the enclosing context**. You should only choose an anonymous class when you genuinely need that object/method structure; when using a lambda, the simplest fix is usually to choose a different parameter name.

## 9. Other Scope Cases to Avoid Confusing

### 9.1. A `catch` Parameter Is Still in Scope

```text
try {
    throw new IllegalStateException();
} catch (IllegalStateException error) {
    IntUnaryOperator op = error -> error + 1;
}
```

This is a **snippet that intentionally does not compile** (assuming `IntUnaryOperator` is imported). Inside the `catch` block, the name `error` is the exception parameter currently in scope. The lambda cannot declare a new parameter with that same name; choose `n -> n + 1` to avoid conflict.

### 9.2. A Block Limits the Lifetime of a Name

```java
{
    int temp = 5;
    System.out.println(temp);
}
IntUnaryOperator op = temp -> temp + 1;
```

The snippet above consists of statements inside a method body with `IntUnaryOperator` imported. When the first block ends, `temp` is no longer in scope, so the lambda is allowed to declare a new parameter `temp`. This differs from declaring `int temp = 5;` directly in the lambda's enclosing block.

### 9.3. Naming Rules Still Apply with Explicit Types or `var`

```text
int index = 10;
IntUnaryOperator a = (int index) -> index + 1; // Invalid
IntUnaryOperator b = (var index) -> index + 1; // Invalid
```

This is code that intentionally does not compile. Writing an explicit type or using `var` does not change the duplicate-name rule. `index` already exists in the method scope, so both lambda parameter declarations collide.

## 10. Relationship with Variable Capture and Effectively Final

The difference between **redeclaring a name** and **reading an enclosing variable** is very important.

```java
int base = 10;
IntUnaryOperator addBase = n -> n + base;
```

These are two valid statements in a method body with `IntUnaryOperator` imported. `base` is the local variable **captured** by the lambda, while `n` is its own parameter. Because `base` is not reassigned, it is *effectively final*.

If you add `base = 20;` in the same method, Java no longer allows the lambda to capture `base`, even though `n` is named completely differently. This is a **variable capture condition error**, distinct from a **duplicate-name declaration error**.

Conversely, `IntUnaryOperator wrong = base -> base + 1;` is forbidden **right at the parameter name** if the enclosing local variable `base` is still in scope, even when the lambda does not read that local variable.

The *effectively final* constraint applies to captured local variables or parameters; it does not mean every referenced object becomes immutable. A lambda can use state fields of a class; when multiple threads access mutable fields concurrently, thread safety must be considered separately.

## 11. Fixing Naming Errors Deliberately

When the compiler reports `variable ... is already defined in method ...`, check in the following order:

1. Identify the **colliding declaration line**: a name on the left of `->`, a variable inside the `{ ... }` body, or a parameter of a nested lambda.
2. Find the same-named local variable/parameter in the enclosing scope that is still active. Do not just look for class fields; colliding with a field name can be valid.
3. If you want to **use the enclosing value**, keep the old variable name to reference it and **rename the lambda parameter** to match its role, e.g., `input -> input + offset`.
4. If you want **a new variable**, use a different name inside the lambda body, e.g., `result` instead of reusing `total`.
5. If two lambdas are **not nested**, you can reuse a short name `x` when there is no same-named local variable in the enclosing scope.
6. Only extract a `{ ... }` block when limiting scope fits the program structure; do not use an anonymous class just to bypass lambda naming rules.

Before-and-after example:

```text
// Invalid if 'limit' is an enclosing local variable:
int limit = 5;
Predicate<Integer> invalid = limit -> limit > 0;

// Valid: name the parameter by its role and read the enclosing variable:
int limit = 5;
Predicate<Integer> valid = value -> value > limit;
```

The two pairs of statements above are independent examples for comparison; do not combine them verbatim in the same method because `limit` would be declared twice. With a local variable `limit` that is not reassigned, the second approach captures the variable validly.

## 12. Self-Check Exercises

**Exercise 1.** In a method that already has `int offset = 5;`, is the lambda `offset -> offset + 1` valid when assigned to `IntUnaryOperator`?

Answer: **No**. The lambda parameter collides with the local variable `offset` already in scope. If you want to add 5, write `n -> n + offset`.

**Exercise 2.** Two variables `IntUnaryOperator a = x -> x + 1;` and `IntUnaryOperator b = x -> x * 2;` are declared in the same method, with no enclosing `x` variable. Is there a duplicate-name error?

Answer: **No**. These are two independent lambdas; the parameter name of the first lambda does not exist in the scope of the second lambda.

**Exercise 3.** A class has `private int score = 10;`. Is the lambda `score -> score + this.score` in an instance method valid? When the parameter receives `3`, what is the result?

Answer: **Yes**, because the name `score` matches a **field**, not a local variable. The result is `3 + 10 = 13`. You should use a different parameter name if clearer code is needed.

**Exercise 4.** Why is `amount -> amount -> amount + 1` invalid when the target type is `Function<Integer, IntUnaryOperator>`?

Answer: the inner lambda declares parameter `amount`, colliding with the outer lambda's parameter `amount` that is already in scope. It can be changed to `amount -> number -> amount + number`.

**Exercise 5.** You isolate `{ int temp = 2; ... }` into an independent block that has ended; after the block, can you declare a lambda parameter named `temp`?

Answer: **Yes**, if there is no other declaration of `temp` in the enclosing scope at the lambda's position. The old name's scope has ended.

## 13. Key Takeaways

- Parameters and local variables inside a lambda **cannot have the same name as a local variable/parameter still in the enclosing scope**; this applies to methods, `catch` blocks, and nested lambdas.
- Sharing a name with a **class field** can be valid: the lambda parameter shadows the field, while `this.fieldName` accesses the field in an instance context.
- **Two independent lambdas** can share the same parameter name; **nested lambdas** cannot redeclare an outer parameter name.
- When a local block ends, the names of local variables in that block are no longer in scope, so those names can be reused where appropriate.
- **Variable capture** is referencing an enclosing variable, not declaring a new variable; a captured local variable must be `final` or *effectively final*.
- An anonymous class has its own method scope and a different `this` rule from a lambda. Renaming the parameter is usually the simplest and clearest fix.

Java specification references: [JLS §15.27.1 — Lambda Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.1), [JLS §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3), and [JLS §15.27.2 — Lambda Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.2).