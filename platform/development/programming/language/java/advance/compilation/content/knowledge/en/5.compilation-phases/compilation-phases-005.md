# Type Checking and Attribution of Expressions During Java Compilation

When reading a Java expression such as `small + 1`, `list.get(0)`, `choose(null)`, or `text -> text.length()`, we can guess what it will do. However, to generate bytecode, the compiler **must determine which name refers to which entity, what type each expression has, which operator/method is selected, and which conversions are permitted**. That process is commonly called *semantic analysis*, *name/type resolution*, *type checking*, and *attribution* (assigning types/semantics to nodes in the syntax tree).

This lesson is set in the context of **the phases of `javac`**, using Java 17 or later. The focus is on explaining why an expression is accepted or rejected **before the program runs**, and how to deduce from compilation error messages which check is failing.

## 1. From Valid Syntax to Meaningful Expressions

Consider three snippets:

~~~java
int sum = 1 + 2;
int sum2 = "1" + 2;
int sum3 = "1" - 2; // type/operator error: '-' does not apply to String and int
~~~

All three have a syntactic form matching a binary operation, yet only the first two expressions are valid in Java semantics.

- `1 + 2`: two `int` operands, `+` is integer addition; the result has type `int`.
- `"1" + 2`: when a `String` operand is present, `+` performs **string concatenation**; the result is a `String` with value `"12"`.
- `"1" - 2`: the `-` operator requires appropriate numeric operands; there is no `String` subtraction in the Java language. The compiler rejects it before generating bytecode.

The **parser** determines how expressions are organized into nodes in the abstract syntax tree (*AST*). **Semantic checking** examines which types, variables, methods, and operations those nodes refer to, and whether they are valid under language rules. A syntactically valid AST is not sufficient for a program to be accepted.

### 1.1. Position in the javac pipeline

The diagram below is a **conceptual model**, without guaranteeing that every internal operation in every `javac` version occurs as strictly separate phases:

~~~text
.java files
    |
    v
Read characters, lexical and syntactic analysis
    |
    v
AST: structured declarations and expressions
    |
    v
Enter / build symbol and scope information
    |
    v
Resolve + Attr + Check: resolve names, assign types,
check expressions, methods, conversions
    |
    v
Flow: check data flow / variable usage conditions
    |
    v
Representation transformation and bytecode generation steps
    |
    v
.class files
~~~

In OpenJDK `javac` source code, names such as `Enter`, `Resolve`, `Attr`, `Check`, and `Flow` correspond to related responsibilities; a specific check may require information from multiple collaborating components. Do not interpret the diagram as a mandatory ordering of every internal call.

- **Enter** records type declarations, members, and symbol information needed for analysis.
- **Resolve** looks up and selects meanings for names, members, or calls when multiple candidates exist.
- **Attr (attribution)** attaches type/semantic information to AST constructs based on context.
- **Check** verifies constraints such as type conversions, accessibility, and structural validity.
- **Flow** verifies properties related to control/data flow such as *definite assignment*, reachability, and related rules.

The result of attribution is that the compiler knows which method the expression `account.balance()` refers to and what return type it has. This information continues to be used during compilation.

## 2. Name Resolution and Symbol Lookup Before Attribution

The name `value` may refer to a local variable, parameter, field, or member of another type. The compiler relies on **scope**, declarations, and shadowing rules to locate the corresponding symbol.

~~~java
public class ScopeExample {
    private int value = 100;

    void print(int value) {
        int doubled = value * 2;
        System.out.println(doubled);   // parameter value: int
        System.out.println(this.value); // field value: int
    }
}
~~~

This is a valid Java class, though without `main` it does not run as a standalone program. In `print`, the simple name `value` resolves to the **parameter**, whereas `this.value` refers to the object's field. Both have type `int` yet are two different symbols; attribution does not merely read the word `int`, it identifies the **exact declaration**.

A name lookup process may examine:

1. Scope of local variables, parameters, types, and related declarations.
2. Members of the current class, superclasses, interfaces, and related types per Java rules.
3. Types brought in via `import`, fully qualified package names, and name resolution rules.
4. Accessibility of the declaration once found, such as `private`, package-private, or `public`.

`import` does not grant access permissions and does not automatically put JARs on the classpath. If a name is spelled correctly yet the compiler lacks the type declaration on the class/source search path, the name resolution step still fails. The `cannot find symbol` message typically points to this error.

Distinguish **shadowing** (one declaration with the same name hiding another by scope) from **overloading** (multiple methods with the same name yet different parameter signatures). Resolving a variable name and selecting an overload call follow different rules.

## 3. Expression Types and Expected Context

Java is a statically type-checked language. The compiler knows a variable's type or infers it from declarations/related expressions. Each expression is checked to see whether it can appear in that context.

~~~java
int count = 10;
long total = count;      // widening primitive: int -> long
Integer boxed = count;   // boxing: int -> Integer
int again = boxed;       // unboxing: Integer -> int
// int invalid = "10";   // error: String does not implicitly convert to int
~~~

Assignments are checked by the compiler under *assignment conversion* rules. They are not identical to every conversion that can be written with a cast. For example, `long` to `int` typically requires an explicit cast because data loss may occur:

~~~java
long large = 3_000_000_000L;
int truncated = (int) large; // may lose information
~~~

The compiler accepts valid cast syntax yet **does not guarantee** the numeric value is preserved. With reference casts, the compiler checks the type relationship allowing the cast; whether the actual object has the right type at runtime can still cause `ClassCastException`. Compiling cleanly does not mean every runtime path is safe.

### 3.1. Primitive types, reference types, and null

`int`, `long`, `double`, `boolean`, ... are primitive types; `String`, `List<String>`, `Integer`, arrays, and other classes/interfaces are reference types. The `null` literal has the special null type and can be assigned to compatible reference types, yet cannot be assigned directly to `int`.

~~~java
String text = null;        // valid
Integer boxed = null;      // valid
// int number = null;      // compile error
int value = boxed;         // compiles, yet NPE at runtime due to unboxing null
~~~

Keep two questions clearly separated: **does the expression have a compatible type to compile?** and **will the actual data cause an error at runtime?** Static type checking does not replace null checks or runtime condition checks.

### 3.2. Types of numeric operators

In numeric expressions, Java applies *unary/binary numeric promotion* rules. For arithmetic `+`, `byte`, `short`, and `char` are normally promoted to `int`; the result does not automatically retain the smaller type:

~~~java
byte a = 7;
int sum = a + 1;     // expression a + 1 has type int
// byte bad = a + 1; // error: requires conversion int -> byte
byte known = 1 + 2;  // valid because this is an int constant whose value fits in byte
~~~

The last case demonstrates **narrowing of constant expressions**, permitted in certain assignment/initialization contexts. Rules for compile-time constants differ from an arbitrary expression having the same value at runtime. Writing `byte known = 128;` is rejected by the compiler because the value exceeds the `byte` range.

Similarly:

~~~java
double result = 5 / 2;    // 5 / 2 is int division; result = 2.0
double fraction = 5 / 2.0; // double division; fraction = 2.5
~~~

The compiler has already decided which type the division applies to before evaluating the final assignment into `double`.

## 4. Determining the Invoked Method: Overload Resolution

Upon encountering `choose(small)`, the compiler must find accessible methods named `choose` that are **applicable to the argument type**. This is a call resolution step, not an arbitrary runtime choice by "closest type."

Java's overload selection rules use multiple applicability phases, preferring calls that apply without boxing/varargs before looser phases; then considering the **most specific** method. Hence primitive widening, boxing/unboxing, and varargs conversions do not always carry the same priority.

~~~java
static String choose(int value) {
    return "int";
}
static String choose(long value) {
    return "long";
}
static String choose(Integer value) {
    return "Integer";
}
~~~

The methods above are **snippets placed inside a class**; the full program is in section 8. With `byte small = 7;`:

| Call | Argument evaluated at compile time | Selected overload |
|---|---|---|
| `choose(small)` | `byte`; can widen to `int` | `choose(int)` |
| `choose(7L)` | `long` literal | `choose(long)` |
| `choose(Integer.valueOf(7))` | `Integer` | `choose(Integer)` |

Overload selection does not rely on the numeric value 7; the compiler relies on the **static type of the expression**.

### 4.1. null and ambiguous calls

If a class has two overloads:

~~~java
static void accept(String value) { }
static void accept(Integer value) { }
~~~

then the call `accept(null)` is **invalid**: `null` can convert to both `String` and `Integer`, yet neither type has a subtype relationship making one method more specific in the required way. `javac` reports `reference to accept is ambiguous`.

Conversely:

~~~java
static String label(Object value) { return "Object"; }
static String label(String value) { return "String"; }
~~~

The call `label(null)` is valid and selects `label(String)` because `String` is a subtype of `Object`, so in this situation the `String` overload is more specific.

**Overloading** is selected by compile-time types. **Overriding** can use dynamic dispatch at runtime: after the compiler selects the instance method signature, the JVM determines the overriding implementation corresponding to the actual object. Do not merge these two mechanisms into one.

### 4.2. Static type determines the overload

~~~java
Object item = "Java";
// label(item) selects label(Object), even though the runtime object is String.
~~~

If both `label(Object)` and `label(String)` exist, the compiler will select `label(Object)` because **variable `item` has static type `Object`**. Calling the `String` overload requires appropriate type information, such as a valid type check/cast. An invalid cast can throw an error at runtime.

## 5. Types Provided by Context: Target Typing and Poly Expressions

Not every expression has a standalone type inferred without looking outside. Certain Java expressions are checked against a **target type** from the context where they appear. The *poly expression* concept is important for lambdas, method references, generic invocations, and certain expressions such as conditional/switch in appropriate contexts.

### 5.1. Lambdas require a target functional interface

~~~java
java.util.function.Function<String, Integer> length =
    text -> text.length();
~~~

Because the target type is `Function<String, Integer>`, the compiler knows parameter `text` has type `String`. It checks that the call `text.length()` has type `int`, then evaluates the boxing conversion from `int` to `Integer` to match the expected result. The compiler does not need to run the lambda to know these types.

Conversely, the following snippet does not compile:

~~~java
// var operation = text -> text.length();
~~~

With only `var` and no target functional interface type, the lambda lacks sufficient context to determine its type. You must declare a suitable functional interface or provide the lambda in a context with a target type, such as an argument to a method accepting `Function<String, Integer>`.

A method reference, such as `String::length`, also needs compatibility checking against the functional interface signature in the specific context.

### 5.2. Generic type inference and invocation types

~~~java
static <T> T identity(T value) {
    return value;
}

String text = identity("OK");
~~~

The compiler infers type parameter `T` so the call `identity("OK")` fits the argument and assignment context. The expression's return type is attributed through type constraints; Java never executes the function to "observe" its return type.

Some generic method invocations are *poly expressions* in assignment/invocation contexts; the target type can participate in inference. Example:

~~~java
java.util.List<String> names = java.util.List.of("Lan", "Mai");
~~~

`List.of` is a generic method; the compiler finds a matching type argument. The list has `String` elements, so `names.get(0)` has compile-time type `String`.

Java generics are checked at compile time, yet much generic information does not exist as an independent parameterized type at runtime due to **type erasure**. Compile-time type and runtime class type are two different layers of information.

### 5.3. var infers from the initializer

~~~java
var names = java.util.List.of("Lan", "Mai");
var first = names.get(0); // first has type String
~~~

`var` is **local variable** type inference, not dynamic typing or default `Object`. The compiler must infer a valid type from the initializer. `var x = null;` does not compile because no type can be inferred under this rule; `var f = x -> x;` also lacks a target type for the lambda.

Note that `var list = new java.util.ArrayList<>();` does not automatically know "later we will add Strings" to the list; when a diamond constructor lacks clear element context, inference may yield `ArrayList<Object>`. Use an explicit declared type when that is a data contract to guarantee.

## 6. Type Compatibility in Generics, Conditional Expressions, and Switch

### 6.1. Generic invariance and wildcards

~~~java
java.util.List<Integer> integers = java.util.List.of(1, 2);
// java.util.List<Number> numbers = integers; // error
java.util.List<? extends Number> readonlyNumbers = integers;
~~~

Even though `Integer` is a subtype of `Number`, `List<Integer>` is **not** a subtype of `List<Number>`. If that assignment were permitted, a `Double` could be added to an `Integer` list via the `List<Number>` variable, breaking element constraints. The `? extends Number` wildcard allows reading elements as `Number` yet restricts adding elements other than `null` per the type contract.

The compiler also applies *capture conversion* rules to handle wildcards across many expressions and generic invocations. Not every generic inference error means "the compiler doesn't know the element type"; the constraint system may genuinely conflict.

### 6.2. Conditional expression

~~~java
int score = 10;
String category = score >= 8 ? "High" : "Low";
long count = true ? 1 : 2L;
~~~

The compiler determines that the condition `score >= 8` has type `boolean`, then checks the two branches of the `?:` expression according to specific rules. In the second example, `int` and `long` branches lead to a `long` result. For certain conditional expressions with reference types, the assignment's **target type** also participates in determining validity.

Do not always deduce the type of `?:` via a simplistic rule of "take the common supertype": Java has dedicated rule tables for boolean/numeric/reference branches, constant expressions, and poly contexts.

### 6.3. Switch expression

~~~java
int price = switch ("VIP") {
    case "VIP" -> 10;
    default -> 20;
};
~~~

Because this is a **switch expression**, the entire `switch` must provide a valid value, its branches are type-checked, and it must be capable of producing a result under Java rules. A traditional `switch` statement does not inherently have a result type to assign to a variable. The example above has a type compatible with `int` and returns 10 when run.

Like lambdas, some switch expressions can be evaluated against a target type. Compile-time checking of branch exhaustiveness differs from runtime selection of a branch during execution.

## 7. Semantic Checks Commonly Accompanying Type Attribution

**Correct types** are an important condition, yet not the only one for Java compilation to succeed.

### 7.1. Definite assignment

~~~java
void show(boolean condition) {
    int number;
    if (condition) {
        number = 42;
    }
    // System.out.println(number); // error: number might not have been assigned
}
~~~

The compiler analyzes control flow to know whether a local variable has been assigned on all paths reaching a usage site. Variable `number` has a definite `int` type, yet the read operation remains invalid when a branch has not assigned a value.

### 7.2. Variable scope in patterns and lambdas

~~~java
void printIfText(Object value) {
    if (value instanceof String s) {
        System.out.println(s.length());
    }
}
~~~

`s` is only in scope at positions where flow-scoping analysis guarantees the pattern `String s` matched. You cannot arbitrarily use `s` outside the allowed scope, even though the declaration already appeared in source code.

For lambdas, a captured local variable must be `final` or *effectively final*:

~~~java
int offset = 2;
java.util.function.IntUnaryOperator plus = x -> x + offset;
// offset = 3; // if uncommented, offset is no longer effectively final
~~~

Even though the `+` operator has valid operand types, the compiler still enforces capture and effective finality rules.

### 7.3. Access permissions, checked exceptions, and return types

The compiler also checks access to `private` members, may require `try/catch` or `throws` for checked exceptions, and checks that `return` statements are compatible with the declared type. Errors like `has private access`, `unreported exception`, or `incompatible types` reflect different semantic constraints; they should not be treated as syntax errors.

**Limits of static checking:** exceptions such as `NullPointerException`, `ClassCastException`, integer overflow, invalid data access, or wrong business outcomes can still occur at runtime even though the program passed all type checks.

## 8. Complete Java 17 Program to Observe Attribution Results

Create file **`TypeAttributionDemo.java`** with all of the following contents (no `package` line, so run in the directory containing the file). The program demonstrates numeric conversion, overloading, null handling, generic inference, lambda target typing, and switch expressions.

~~~java
import java.util.List;
import java.util.function.Function;

public final class TypeAttributionDemo {
    static String choose(int value) { return "int"; }
    static String choose(long value) { return "long"; }
    static String choose(Integer value) { return "Integer"; }

    static String label(Object value) { return "Object"; }
    static String label(String value) { return "String"; }

    static <T> T identity(T value) { return value; }

    public static void main(String[] args) {
        byte small = 7;
        int sum = small + 1;

        System.out.println(choose(small));
        System.out.println(choose(7L));
        System.out.println(choose(Integer.valueOf(7)));
        System.out.println(label(null));
        System.out.println(sum);

        List<String> names = List.of("Lan", "Mai");
        var first = names.get(0);
        System.out.println(first);

        Function<String, Integer> length = text -> text.length();
        System.out.println(length.apply("Java"));

        String text = identity("OK");
        System.out.println(text);

        int price = switch ("VIP") {
            case "VIP" -> 10;
            default -> 20;
        };
        System.out.println(price);
    }
}
~~~

Compile and run with JDK 17 or newer, in the directory containing the file:

~~~sh
javac --release 17 -encoding UTF-8 TypeAttributionDemo.java
java TypeAttributionDemo
~~~

**Exact stdout verified with a JDK running `javac --release 17`:**

~~~text
int
long
Integer
String
8
Lan
4
OK
10
~~~

Explanation of each group:

| Result | Compile-time decision |
|---|---|
| `int` | `choose(byte)` does not exist; widening `byte → int` selects `choose(int)` |
| `long` | `7L` literal has type `long`, selects `long` overload |
| `Integer` | Argument has type `Integer`, selects exact matching overload |
| `String` | `label(null)` selects `String` overload, which is more specific than `Object` |
| `8` | `small + 1` has type `int` |
| `Lan` | `names.get(0)` has type `String`; `var first` infers `String` |
| `4` | Lambda is target-typed as `Function<String,Integer>`; `length()` returns `int` |
| `OK` | Generic `identity` infers type matching `String` |
| `10` | Switch expression returns `int` from the `VIP` branch |

Decisions for overload selection, operator validity, type conversions, and lambda/generic inference are determined at compile time. Actual condition values, list elements, and method call execution still take place at runtime.

## 9. Two Reproducible Compile-Time Errors

The examples below are **intentionally invalid**. Save each snippet in a separate file; do not add them to `TypeAttributionDemo.java` if you want the sample program in section 8 to remain runnable.

### 9.1. Type incompatibility

File `InvalidAssignment.java`:

~~~java
public class InvalidAssignment {
    int value = "42";
}
~~~

Run:

~~~sh
javac --release 17 -encoding UTF-8 InvalidAssignment.java
~~~

The result is rejection by the compiler, with the corresponding error:

~~~text
error: incompatible types: String cannot be converted to int
~~~

Reason: `"42"` is a `String` literal even though its contents look like a number. Java does not automatically parse strings into numbers during assignment; to convert data, you must call an appropriate method such as `Integer.parseInt("42")` and handle invalid input.

### 9.2. Ambiguous overload

File `Ambiguous.java`:

~~~java
public class Ambiguous {
    static void accept(String value) {}
    static void accept(Integer value) {}

    public static void main(String[] args) {
        accept(null);
    }
}
~~~

Run:

~~~sh
javac --release 17 -encoding UTF-8 Ambiguous.java
~~~

The compiler rejects the call, with the error:

~~~text
error: reference to accept is ambiguous
~~~

Both methods can accept `null`, yet neither overload is determined to be more specific. Selection can be specified with an appropriate cast, such as `accept((String) null)`, if that is truly the author's intent. The error line and alignment of `^` may vary by version/compiler flags; the essence of the error is **inability to resolve the call to a single method**.

## 10. Reading Error Messages by Cause Category

An error from `javac` usually contains file/line position, error name, and expected context. Initial classification can be made as follows:

| Message/symptom | Common semantic cause | Questions to check |
|---|---|---|
| `cannot find symbol` | Name cannot be resolved | Is the name declared, and in the right scope/package/classpath? |
| `package ... does not exist` | Cannot find declarations from package | Are source path, classpath/module path configured properly? |
| `incompatible types` | Expression cannot convert to required type | What are source type, target type, and allowed conversions? |
| `no suitable method found` | No overload is applicable | What types do the arguments have; are valid conversions needed? |
| `reference to ... is ambiguous` | Multiple applicable overloads, no unique choice | Do competing overloads have any specificity relationship? |
| `bad operand types for binary operator` | Operator not allowed on operand types | What is the actual type of each side? |
| `variable ... might not have been initialized` | Definite assignment not guaranteed | Is there a path using the variable before assignment? |
| `local variables referenced from a lambda ... must be final or effectively final` | Local variable capture violates rule | Is the variable reassigned after initialization? |
| `has private access` | Violates member access rules | Is there an appropriate/public alternative API? |
| `unreported exception ... must be caught or declared` | Violates checked exception rules | Does it need `catch` or an appropriate `throws` declaration? |

Do not solve `incompatible types` errors with reckless casting. A cast may be invalid under language rules or produce runtime errors; check **data intent** before choosing a conversion.

### 10.1. Having javac print detailed diagnostics

Example command:

~~~sh
javac -Xdiags:verbose --release 17 -encoding UTF-8 InvalidAssignment.java
~~~

The `-Xdiags:verbose` option can provide helpful diagnostic details, especially for overload or generic inference errors. It does not turn an ill-typed program into a well-typed one.

Check flags supported by the JDK with `javac --help` and `javac -X`; some error formatting details may change by JDK release, display locale, or how build tools collect logs.

## 11. Boundary Between Compile-Time and Runtime Semantics

Some things the compiler **determines or checks**:

- Static types of expressions, declared types, and compatibility with context.
- Which name resolves to which field/variable/method.
- Which overload is selected from the name, argument types, and target type.
- Rules for widening, boxing, unboxing, casts, generics, wildcards, lambdas, switch expressions.
- Flow constraints such as definite assignment and effectively final.

Some things that normally require **runtime** to determine or execute:

- Values of variables and conditions during a specific run.
- The actual object for an overridden virtual call.
- Whether an unboxing operation encounters `null`.
- Whether a reference cast fails or succeeds.
- Whether a division divides by zero, or an array access goes out of bounds.
- Business logic outcomes, I/O, and external interactions.

There are exceptions and optimizations: the compiler can recognize **constant expressions** and fold constant values per language rules; the JVM/JIT can optimize many runtime computations. Even so, that does **not** turn Java into a dynamically typed language, nor does it replace the compile-time rules above.

## 12. Practice Exercises with Guided Answers

**Exercise 1 — Predict types and errors**

~~~java
byte b = 10;
int x = b + 1;
// byte y = b + 1;
byte z = 10 + 1;
double d = 5 / 2;
~~~

Explain each declaration. Guided answer: `b + 1` is `int`; `y` is invalid if uncommented; `10 + 1` is a constant expression with value 11 so `z` is permitted; `d` receives `2.0`, because division of two `int`s occurs before conversion to `double`.

**Exercise 2 — Overload selection**

~~~java
static void test(Object o) {}
static void test(String s) {}
Object value = "Java";
test(value);
test(null);
~~~

Place the code above inside a valid class/method context. Answer: `test(value)` selects `Object` due to static type; `test(null)` selects `String` as it is more specific. Changing the `Object` overload to `Integer` makes `test(null)` ambiguous.

**Exercise 3 — Type inference**

Why is `Function<String, Integer> length = s -> s.length();` valid while `var length = s -> s.length();` is invalid? Answer: a lambda needs the **target type** of a functional interface. The `var` context in the example does not provide that target type.

**Exercise 4 — Generics**

Why cannot `List<Integer>` be directly assigned to `List<Number>`? When you only need to read `Number` values from a list of `Integer`, consider `List<? extends Number>`. Point out what could go wrong if adding a `Double` were allowed into a list that actually holds `Integer`s.

**Exercise 5 — Systematic troubleshooting**

Given a `cannot find symbol` error in `service.BookService`, check in the exact order: declaration name, scope, package/imports, access permissions, source files included in the `javac` invocation, and required classpath/module path. Do not merely tweak syntax until the error message disappears; verify the compiler is finding the intended type.

## 13. Checklist When Analyzing an Expression

Before concluding whether a Java expression is valid or invalid, ask yourself:

1. What is the AST syntax of the expression, and where are the operands and calls?
2. Which declaration does each name resolve to? Is it shadowed or inaccessible?
3. What is the compile-time type of each operand; primitive, reference, or `null`?
4. Is there a **target type** from an assignment, method parameter, `return`, or another context?
5. Which conversion rules apply: widening, boxing/unboxing, numeric promotion, constant narrowing, or casting?
6. If it is a call, which overloads apply and which overload is most specific?
7. If generics/lambdas are involved, are the inference constraints and functional interface valid?
8. Are there any violations of flow, accessibility, checked exceptions, or other rules?
9. What has the compiler guaranteed, and what can only be determined at runtime?

**Core takeaway:** attributing meaning to expressions turns the syntax tree into operations with **symbols, types, conversions, and invocations determined according to the Java Language Specification**. Understanding this step helps explain `javac` messages accurately, avoid confusing compile-time with runtime, and write more maintainable Java code.