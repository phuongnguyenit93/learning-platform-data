# Checking Argument Types, Count, and Order When Calling Java Methods

## Learning Objectives

After this lesson, you will be able to:

- Distinguish a **formal parameter** in a declaration from an **argument** at a method or constructor call site.
- Check whether a call has the **correct number of arguments**, the **correct order**, and **compatible data types** for the corresponding parameters.
- Explain the conversions Java automatically performs during a call: primitive widening, reference widening, boxing, unboxing, and important limitations.
- Recognize the effects of overloading, variable-length parameters (`varargs`), generic type inference, `null`, arrays, and the invariance of generic types.
- Read compiler error messages when passing too few, too many, out-of-order, or wrong-type arguments; fix them yourself with proper declarations/calls instead of arbitrary casts.
- Understand that Java maps arguments by **position**, evaluates argument expressions **from left to right**, and passes the evaluated result values into the parameters.

## 1. Parameters and Arguments: Two Sides of a Call

Consider this example:

~~~java
public class Registration {
    static void register(String username, int age, boolean active) {
        System.out.println(username + " | " + age + " | " + active);
    }

    public static void main(String[] args) {
        register("Lan", 20, true);
    }
}
~~~

Save this as `Registration.java` and run it with JDK 17 or later:

~~~bash
javac Registration.java
java Registration
~~~

Output:

~~~text
Lan | 20 | true
~~~

The method declares **three formal parameters** in order: `String username`, `int age`, `boolean active`. The call `register("Lan", 20, true)` supplies **three actual arguments** in the same order: the string `"Lan"`, the integer `20`, and the boolean `true`.

Java maps arguments to parameters **by position**, from left to right:

| Position | Formal parameter | Corresponding argument | Check |
| --- | --- | --- | --- |
| 1 | `String username` | `"Lan"` | `String` is compatible with `String` |
| 2 | `int age` | `20` | Literal has type `int` |
| 3 | `boolean active` | `true` | `boolean` is compatible with `boolean` |

The variable names inside the method (`username`, `age`, `active`) are names for **the method body to use**. Callers do not pass arguments using those names. Java does not support calling by name such as `register(active=true, age=20, username="Lan")`; if written that way, it is not valid Java named arguments.

The same principles apply to **constructors**, for example `new Person("Lan", 20)`, and to instance methods, for example `account.deposit(100)`. Specifically, the call syntax may differ due to the receiver, generic type arguments, lambdas, or method references, but the compiler still needs to check the compatibility of the parameters and arguments.

## 2. Checking the Number of Arguments (Arity)

For a fixed-arity method:

~~~java
static void move(int x, int y) {
    System.out.println(x + "," + y);
}
~~~

Valid call:

~~~java
move(3, 4);
~~~

Because the method requires exactly **two arguments**, the following calls fail to compile:

~~~java
// Intentionally invalid examples; used for explanation only, do not run directly.
move(3);       // Missing the second argument
move(3, 4, 5); // Extra third argument
move();        // No arguments provided
~~~

There is no **default parameter value** mechanism in Java method declarations such as `void move(int x = 0)`. If you want to support calling with different numbers of arguments, you can:

1. **Overload** methods with different parameter lists and provide an explicit default call.
2. Use **varargs** when you need to accept a variable number of elements of the same type in the last position.
3. Use a configuration data type or a parameter object if there are many options with distinct business meanings.

Example of a valid overload:

~~~java
static void draw(int x, int y) {
    System.out.println("draw at " + x + "," + y);
}

static void draw(int x) {
    draw(x, 0);
}
~~~

These are two **illustrative method declarations inside a class**, not a standalone program. `draw(5)` will use the one-parameter overload; it calls `draw(5, 0)`. The "missing/extra arguments" rule is always evaluated against the **set of applicable methods**: `draw(5)` is valid in this example because a matching overload exists.

### 2.1. Variable-Length Parameters (`varargs`)

A method whose final parameter has the form `Type... name` accepts a variable number of arguments in that position:

~~~java
static void printLabels(String prefix, String... labels) {
    System.out.println(prefix + ": " + String.join(", ", labels));
}
~~~

This is an illustrative declaration inside a class. Calls can be:

~~~java
printLabels("none");
printLabels("one", "A");
printLabels("two", "A", "B");
printLabels("array", new String[] {"X", "Y"});
~~~

If a `main` method calls the four statements above in order, the output is:

~~~text
none: 
one: A
two: A, B
array: X, Y
~~~

The `prefix` parameter remains a **required fixed parameter**. The `labels` part can receive 0 or more `String` values in the variable-argument call form, or directly receive a compatible `String[]`. Inside the method body, `labels` has the array type `String[]`.

Only the **last parameter** may be declared as varargs; each method can have at most one varargs parameter. `void f(String... texts, int count)` is invalid. The `String...` and `String[]` syntaxes have differences at call sites, but you cannot declare both to create overloads with the same signature.

**Caution:** Varargs does not bypass type checking. `printLabels("bad", 1)` is invalid because `1` cannot be converted to `String` via an appropriate invocation conversion.

## 3. Checking Argument Data Types

The type of an argument expression does not have to **match** the parameter type **exactly**. Java allows several valid **call-time conversions** (*method invocation conversions*), provided the method applicability rules are satisfied.

Example:

~~~java
static void readLong(long value) {
    System.out.println(value);
}

static void display(Object value) {
    System.out.println(value);
}
~~~

Within a method of the same class, the following calls are valid:

~~~java
readLong(5);        // int -> long (primitive widening)
display("Hello");   // String -> Object (reference widening)
display(10);        // int is boxed to Integer, which can then be used as Object
~~~

Conversely, Java does not automatically convert every type into every other type:

~~~java
// Intentionally invalid examples when placed in the corresponding method:
// readLong("5");    // String is not automatically parsed into a long number
// readLong(true);   // boolean cannot become a long
~~~

### 3.1. Primitive Widening

Some typical automatic conversions:

| Argument type | Parameter types accepted via widening | Notes |
| --- | --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` | May lose precision when converting to float/double if sufficiently large |
| `short` | `int`, `long`, `float`, `double` | Does not automatically become `char` |
| `char` | `int`, `long`, `float`, `double` | `char` is an unsigned UTF-16 code unit |
| `int` | `long`, `float`, `double` | `int` does not automatically narrow to `byte` or `short` in a method call |
| `long` | `float`, `double` | Some values cannot be represented exactly in floating point |
| `float` | `double` | Converts to `double` |

`boolean` does not participate in numeric conversions. Widening comprises conversions permitted by the compiler, but **does not mean mathematical precision is always preserved**: `long` to `float` can be rounded.

### 3.2. Narrowing Conversions Do Not Occur Automatically in Method Calls

Example:

~~~java
static void acceptByte(byte value) {
    System.out.println(value);
}
~~~

The call `acceptByte(10)` is **invalid**, even though the literal `10` is within the `byte` range: the default type of an integer literal is `int`; Java does not automatically perform a narrowing conversion `int -> byte` just to match a parameter in a method call.

This is a difference from **assignment conversion**:

~~~java
byte b = 10;        // Valid: special rule for int constants in assignment
acceptByte(b);      // Valid: b already has type byte
acceptByte((byte) 10); // Valid: explicit cast
~~~

These `acceptByte` lines are examples inside a method of the class that has the `acceptByte(byte)` declaration above. Casting must have a reason; `(byte) 130` does not preserve the value 130 but gives a different result due to data loss. When an `int` value needs to be represented, choosing an `int` parameter is usually safer and clearer than casting to get past the check.

### 3.3. Boxing, Unboxing, and the Risk of `null`

Java can box `int` into `Integer`, or unbox `Integer` into `int` according to call rules. Example:

~~~java
static void takeInteger(Integer value) {
    System.out.println(value);
}

static void takeInt(int value) {
    System.out.println(value);
}
~~~

Inside an appropriate method:

~~~java
takeInteger(7);                 // Boxing int -> Integer
takeInt(Integer.valueOf(7));    // Unboxing Integer -> int
~~~

However:

~~~java
Integer maybe = null;
// takeInt(maybe); // Compiles validly, but throws NullPointerException at runtime when unboxing
~~~

When `maybe` is `null`, unboxing it to pass to an `int` parameter causes a runtime error. The compiler can check *types*, but it cannot guarantee that all runtime data is non-null.

A chain of conversions is not always allowed: for example, Java does **not** automatically widen `int -> long` and then box it to `Long` to match a `Long` parameter in a normal call. To call `takeLongObject(Long)` from `int x`, you can write `takeLongObject(Long.valueOf(x))` (converting `int` to `long` for the `Long.valueOf(long)` overload) or use an appropriately boxed `long` value.

### 3.4. Reference Widening and Static Type

If the parameter type is `Object`, you can pass an expression of type `String`, `Integer`, or an object of an appropriate subclass:

~~~java
static void inspect(Object item) {
    System.out.println(item);
}
~~~

`inspect("hello")` is valid because `String` is a subtype of `Object`; `inspect(5)` is valid because it is boxed to `Integer` and then compatible with `Object`.

Conversely, if a method expects `String`, a variable declared as `Object` **cannot be passed automatically** even if it currently points to a `String`:

~~~java
Object value = "text";
// consumeString(value); // Does not compile if consumeString(String) is the only overload
~~~

The compiler checks based on the **static type of the expression** and the allowed conversion rules; it does not ignore the declared type just because the runtime data happens to be of a narrower type. If narrowing is truly necessary, you can check with `instanceof` or perform a controlled cast; an incorrect cast can cause a `ClassCastException`.

## 4. Argument Order Determines Which Parameter Each Argument Maps To

Two calls with the same **count** and **set of types** do not necessarily have the same meaning:

~~~java
static int subtract(int left, int right) {
    return left - right;
}
~~~

`subtract(9, 4)` returns `5`, whereas `subtract(4, 9)` returns `-5`. Both are valid in terms of types because each argument has type `int`, but they have **different business meanings**. The compiler does not know which value you intended as the "minuend": parameter names are not used to automatically reorder arguments at the call site.

When the list of types also differs, reversing the order can cause a **compilation error**:

~~~java
static void pay(String accountId, int amount) {
    System.out.println(accountId + ": " + amount);
}
~~~

Valid: `pay("ACC-1", 100)`. Invalid: `pay(100, "ACC-1")` because position 1 expects `String` but receives `int`, and position 2 expects `int` but receives `String`. When the compiler can see multiple `pay` overloads, another overload might apply; therefore, you must examine the **set of callable methods with the same name**, rather than judging based on a single declaration alone.

### 4.1. Java Evaluates Argument Expressions from Left to Right

Java evaluates argument expressions in **left-to-right order**; the resulting values are then passed into the corresponding parameters. If argument expressions have side effects, the observable order matters:

File **`ArgumentOrderDemo.java`**:

~~~java
public class ArgumentOrderDemo {
    static int next(String label, int value) {
        System.out.println("evaluate " + label);
        return value;
    }

    static void accept(int first, int second) {
        System.out.println("called " + first + "," + second);
    }

    public static void main(String[] args) {
        accept(next("first", 10), next("second", 20));
    }
}
~~~

Run:

~~~bash
javac ArgumentOrderDemo.java
java ArgumentOrderDemo
~~~

Output:

~~~text
evaluate first
evaluate second
called 10,20
~~~

The first argument is evaluated before the second argument. This is the **evaluation order**, not the order in which an overload is selected: the compiler chooses the method based on type checking, whereas expression evaluation occurs when the program runs.

To keep code readable and less error-prone, you should avoid relying on multiple hard-to-follow side effects within the same argument list; you can compute clearly named variables beforehand and then call the method.

## 5. How Overloading Affects Type, Count, and Order Checking

**Method overloading** is declaring multiple methods with the same name and validly different parameter type lists. Example:

~~~java
static void send(String message) { }
static void send(String message, int retries) { }
static void send(int code, String message) { }
~~~

The snippet above contains illustrative declarations within the same class. Calls:

- `send("hello")` matches the single-`String`-parameter method.
- `send("hello", 3)` matches `send(String, int)`.
- `send(404, "Not found")` matches `send(int, String)`.
- `send(404)` does not match any of the three declarations; an overload accepting a single `int` is missing.
- `send(3, 4)` does not match because the two-parameter overloads both require at least one `String`.

Parameter names, return types, and `throws` clauses **are not enough to create a new overload** if the Java signature remains the same. At a call site, overload resolution is the step that determines which available methods are applicable and which method takes priority according to the language rules.

### 5.1. Which Applicability Takes Priority?

At a high level, Java checks overload applicability in **phases**:

1. **Strict invocation phase**: first considers calls with a fixed number of parameters and allows strict conversions such as primitive widening or reference widening, without needing boxing/unboxing.
2. **Loose invocation phase**: if the previous phase finds no applicable method, additionally considers boxing/unboxing and related permitted conversions.
3. **Variable-arity phase**: if the previous two phases still find no applicable method, considers calling varargs methods with a variable number of arguments.

Once there are applicable candidates in the appropriate phase, Java applies the **most specific** rule to select one. An **ambiguous** call can occur if a single best-matching method cannot be determined.

Therefore, the statement "Java always chooses the exact type match" is only an intuition for some simple situations, not the full overload resolution algorithm.

### 5.2. Widening Can Take Priority Over Boxing

Example:

~~~java
static String select(long value) {
    return "long";
}

static String select(Integer value) {
    return "Integer";
}
~~~

The call `select(7)` with the `int` literal `7` selects `select(long)` via primitive widening in the strict phase; Java does not yet need to box it into `Integer`. Conversely, `select(Integer.valueOf(7))` has type `Integer` and directly selects the matching `Integer` overload.

This explains why some programs print results different from what someone might expect if they only think "`int` goes with `Integer` because the names look alike." In Java, it is the **static type of the expression** and the overload resolution phases that decide.

### 5.3. Same Arity but Conflict When Passing `null`

Given two overloads:

~~~java
static void find(String text) { }
static void find(Integer number) { }
~~~

The call `find(null)` fails to compile due to ambiguity: `null` can be used for both reference types, and neither type is more specific than the other in this situation. Calls such as `find((String) null)` or `find((Integer) null)` express the intended type explicitly; however, **runtime values can still be `null`**, so the method needs to handle that appropriately.

You cannot pass `null` to a primitive parameter such as `int`. If an API frequently receives `null`, consider designing overloads to avoid ambiguous situations or defining a strict input contract.

### 5.4. Varargs Can Lose to a Fixed-Arity Overload

Suppose a class has:

~~~java
static void log(Object item) { }
static void log(String... items) { }
~~~

The call `log("hello")` normally selects `log(Object)`: the fixed-arity `Object` method already applies in the strict phase, whereas `log(String...)` requires the varargs mechanism for one `String`. If you call `log("A", "B")`, the `Object` overload does not accept two arguments; varargs can apply.

Note that when passing **a `String[]` array**, a varargs method can be applicable just like a method accepting **a single array argument in fixed form**. This rule is why you should not mechanically apply the statement "fixed arity always beats varargs" to every expression.

## 6. Complete Java 17+ Example: Checking Multiple Call Forms

Save the following standalone program as **`ArgumentValidationDemo.java`**:

~~~java
import java.util.List;

public class ArgumentValidationDemo {
    static void record(String label, int quantity) {
        System.out.println(label + ":" + quantity);
    }

    static int subtract(int left, int right) {
        return left - right;
    }

    static long square(long value) {
        return value * value;
    }

    static String select(long value) {
        return "long";
    }

    static String select(Integer value) {
        return "Integer";
    }

    static void printTags(String category, String... tags) {
        System.out.println(category + ":" + String.join(",", tags));
    }

    static <T> T identity(T value) {
        return value;
    }

    static void showNumbers(List<? extends Number> values) {
        System.out.println("numbers=" + values.size());
    }

    public static void main(String[] args) {
        record("apples", 3);

        System.out.println("minus=" + subtract(9, 4));
        System.out.println("minus reversed=" + subtract(4, 9));
        System.out.println("square=" + square(5));

        System.out.println("select int=" + select(7));
        System.out.println("select boxed=" + select(Integer.valueOf(7)));

        printTags("levels", "basic", "advanced");
        printTags("empty");

        Integer copy = identity(42);
        System.out.println("copy=" + copy);

        showNumbers(List.of(1, 2, 3));
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 ArgumentValidationDemo.java
java ArgumentValidationDemo
~~~

**Exact output:**

~~~text
apples:3
minus=5
minus reversed=-5
square=25
select int=long
select boxed=Integer
levels:basic,advanced
empty:
copy=42
numbers=3
~~~

Explanation of the calls:

| Call | Why is it valid? |
| --- | --- |
| `record("apples", 3)` | Exactly two arguments in the exact order `String, int` |
| `subtract(9,4)` and `subtract(4,9)` | Both match `(int,int)`, but reversing values and positions changes the result |
| `square(5)` | `int` is widened to `long` |
| `select(7)` | Selects the `select(long)` overload before boxing is needed |
| `select(Integer.valueOf(7))` | The argument's static type is `Integer`, matching the `select(Integer)` overload |
| `printTags("levels", "basic", "advanced")` | One fixed `String` argument, two `String` arguments for varargs |
| `printTags("empty")` | Valid because the varargs portion can have 0 elements |
| `identity(42)` | Generic type inference allows the call, and the result is compatible with `Integer` |
| `showNumbers(List.of(1,2,3))` | The argument is a list whose element type matches `? extends Number` |

Hands-on exercise: change `record("apples", 3)` to `record(3, "apples")` and run `javac` again. You will see a **no suitable call found** error because the two argument types are reversed. Restore the correct line before continuing to compile.

## 7. Generics: The Compiler Checks Element Types Too

The `<...>` type arguments in generic types **are not ignored** when checking Java source calls.

Example method:

~~~java
static void printNames(java.util.List<String> names) {
    for (String name : names) {
        System.out.println(name);
    }
}
~~~

Inside a method in the same class, calling it with a variable:

~~~java
java.util.List<String> names = java.util.List.of("Lan", "Minh");
printNames(names); // Valid
~~~

However:

~~~java
java.util.List<Integer> ages = java.util.List.of(20, 21);
// printNames(ages); // Type mismatch: List<Integer> cannot be converted to List<String>
~~~

Generics in Java are normally **invariant**: `List<Integer>` is not a subtype of `List<Number>`, even though `Integer` is a subtype of `Number`. If you write a method:

~~~java
static void show(java.util.List<Number> numbers) { }
~~~

then a variable of type `List<Integer>` cannot be passed directly to `show(List<Number>)`. This prevents code inside the method from adding a `Double` to a list that actually accepts only `Integer`.

To **read** numeric values without needing to add elements, you can choose the parameter `List<? extends Number>`; `List<Integer>`, `List<Double>`, and `List<Number>` lists are compatible in the corresponding contexts. Conversely, if a method needs to receive a container where it can **add Integer**, the type `List<? super Integer>` may be suitable, with different reading rules. Do not use wildcards just to silence errors; choose them based on actual read/write behavior.

### 7.1. Generic Methods and Type Inference

Example:

~~~java
static <T> T echo(T value) {
    return value;
}
~~~

This is a method declaration used inside a class. The call `String result = echo("Java");` is valid because the compiler can infer an appropriate type for `T`. In complex generic situations, the expected type in the result-receiving context can participate in type inference; therefore, selecting a generic method cannot always be described simply as "just looking at the literal and locking in the type."

What remains essential is: **the arguments must satisfy the type relationships required by the method signature**. Example:

~~~java
static <T extends Number> void numberOnly(T value) { }
~~~

`numberOnly(3)` is valid because `Integer` belongs to `Number`; `numberOnly("3")` is invalid because `String` does not satisfy the bound `T extends Number`.

### 7.2. Cannot Overload Solely Using Type-Erased Generic Arguments

The two declarations:

~~~java
// The following two lines cannot appear together in the same class:
// void process(java.util.List<String> values) { }
// void process(java.util.List<Integer> values) { }
~~~

cause a **name clash** related to type erasure. Although the `String` and `Integer` parts differ, the JVM-erased parameter types are both `List`. This is a validity issue of the overload declarations, distinct from a call having incompatible type arguments.

## 8. Error Messages for Invalid Arguments and How to Read Them

Exact messages vary depending on the JDK and the call site. However, analysis usually starts with the following:

| Error category | Situation | How to fix |
| --- | --- | --- |
| Missing argument | `register("Lan",20)` when only `register(String,int,boolean)` exists | Pass the third `boolean` argument or define an appropriate overload |
| Extra argument | `register("Lan",20,true,1)` | Remove the extra argument or choose an API that actually has four parameters |
| Wrong type order | `register(20,"Lan",true)` | Change the order to `String,int,boolean` |
| Incompatible primitive | `readLong(true)` | Cannot convert `boolean` to a number; review the meaning of the data |
| No automatic narrowing | `acceptByte(10)` with `acceptByte(byte)` | Use a `byte` variable, an intentional safe cast, or change the parameter to `int` |
| No applicable overload | `send(404)` when only a `String` or two-parameter overload exists | Fix the call to match the API or provide a meaningful overload |
| Ambiguous call | `find(null)` with `find(String)`, `find(Integer)` | Specify the intended type explicitly; consider an API with fewer ambiguous overloads |
| Passing `Object` to `String` | Variable declared as `Object` even though the runtime object is `String` | Perform an intentional type check and narrowing, or design an appropriate static type |
| `List<Integer>` to `List<String>` | Different generic type arguments | Pass a collection of the right type or adjust the abstraction to match requirements |
| Unboxing null | Null `Integer` variable passed to an `int` parameter | Check for null, use an intentional default value, or design the API to accept nullable |
| Array parameter | Method accepts `int[]` but caller passes two `int` values | Pass `new int[]{...}` or use `int...` as the last parameter if varargs is needed |
| Wrong overload due to boxing/widening | Expecting `Integer` but `int` selects `long` | Check the static type and the three applicability phases; write an explicit value/type when needed |
| Wrong constructor call | `new User("Lan", true)` when the constructor takes `(String,int)` | Check the constructor signatures and argument order directly |

When you encounter errors such as `method ... cannot be applied to given types`, `no suitable method found`, `incompatible types`, or `reference ... is ambiguous`, you should read the details for **required** (the required parameter types), **found** (the argument types the compiler sees), and **reason**. Do not blindly cast every argument just to make the error disappear: the compiler may be reporting a business-logic mismatch.

### 8.1. Why Can't Runtime Fix Compile-Time Type Errors?

Consider the illustrative snippet:

~~~java
Object object = "Java";
// printNames(object); // Invalid if printNames only accepts List<String>
~~~

A method requiring `List<String>` cannot directly accept `Object` just because the programmer knows `object` currently holds a `String` (in fact, the data is not even in the shape of a list). You should design types/arguments to reflect the actual data.

Another more accurate example for the Object/String relationship:

~~~java
static void printText(String text) {
    System.out.println(text);
}

// Inside a method:
Object object = "Java";
// printText(object); // Does not compile: Object does not implicitly convert to String
if (object instanceof String text) {
    printText(text);    // Valid: text has been verified to be String
}
~~~

The snippets above are examples to be placed inside an appropriate class, not standalone program files. Pattern matching for `instanceof` is available in Java 17. Static type checking by the compiler helps catch errors before the program runs; however, certain data issues such as `null` or conditional cast outcomes still need to be handled at runtime.

## 9. Constructors Are Also Argument-Checked

A constructor has the same name as the class and has no return type. When creating an object, the compiler must also find an applicable constructor with the right number and types of arguments:

~~~java
class Ticket {
    final String event;
    final int seats;

    Ticket(String event, int seats) {
        this.event = event;
        this.seats = seats;
    }
}
~~~

Inside an appropriate method:

~~~java
Ticket ok = new Ticket("Concert", 2);
// Ticket missing = new Ticket("Concert");     // Missing seats
// Ticket reversed = new Ticket(2, "Concert"); // Swapped argument types
// Ticket extra = new Ticket("Concert", 2, true); // Extra argument
~~~

Java supports **constructor overloading**, so a class can declare an additional `Ticket(String event)` to set a default number of seats, as long as it follows the signature rules. When using `this(...)` or `super(...)` to call another constructor, the arguments must also be compatible with the target constructor.

**Constructor overloads are not distinguished by return type**, because a constructor does not declare a return type. Writing `void Ticket(...)` declares a regular method named `Ticket`, not a constructor.

## 10. Passing Arguments by Value Does Not Mean Objects Are Copied

After the compiler selects an applicable method, at runtime Java **evaluates the argument expressions** and passes the resulting **values** into the corresponding parameters:

- For primitives, a value such as `int 5` is copied into the `int` parameter.
- For references, the **reference value** is copied; both caller and callee can point to the same object. The method can mutate the object if the object is mutable and the API permits it.
- **Reassigning a parameter** does not reassign the caller's variable.

Standalone runnable example **`ArgumentValuesDemo.java`**:

~~~java
public class ArgumentValuesDemo {
    static void update(int number, StringBuilder text) {
        number = 99;
        text.append("!");
        text = new StringBuilder("Other");
        System.out.println("inside=" + number + "," + text);
    }

    public static void main(String[] args) {
        int quantity = 5;
        StringBuilder label = new StringBuilder("Hi");

        update(quantity, label);
        System.out.println("outside=" + quantity + "," + label);
    }
}
~~~

Run:

~~~bash
javac ArgumentValuesDemo.java
java ArgumentValuesDemo
~~~

Output:

~~~text
inside=99,Other
outside=5,Hi!
~~~

The difference arises because the `number` parameter is a copy of the number `5`, whereas the `text` parameter initially holds a copy of the reference pointing to the same `StringBuilder`. The call `text.append("!")` modifies that object; afterward, the assignment `text = new StringBuilder("Other")` only changes the parameter variable inside the method.

**Connection to argument checking:** the type of `quantity` is `int`, and the type of `label` is `StringBuilder`; the compiler confirms both are compatible with the parameter order `(int,StringBuilder)` before the program runs. Java does not pass objects into a method by passing the caller's variable by reference.

## 11. Subtle Pitfalls That Affect How Calls Are Read

### 11.1. An Array Differs from Multiple Arguments

Suppose:

~~~java
static int lengthOf(int[] numbers) {
    return numbers.length;
}
~~~

`lengthOf(new int[]{1,2,3})` is **one argument of type `int[]`**, which is valid. `lengthOf(1,2,3)` is **three arguments of type `int`**, which is invalid because the method does not declare varargs. If you want to support passing multiple numbers, declare `static int lengthOf(int... numbers)`, a syntax that means variable-arity calls and receives an array in the method body.

### 11.2. An Argument Can Be a Complex Expression

`register("Lan".trim(), 18 + 2, !false)` still has three arguments, with static types `String`, `int`, and `boolean`, respectively. Each expression is evaluated to produce an **argument value**. Do not count commas inside generic type arguments or inside nested calls as separate arguments of the outer method; the parser determines the syntactic structure.

### 11.3. Type Order Differs from Name Order

Declaring `void position(int x, int y)` does not automatically protect you from `position(y, x)` when both expressions have type `int`. The compiler only sees a compatible call; the business result may be wrong. If parameters share the same type but their meanings are easily confused, use clearly named variables, a configuration object, or an API design that expresses intent.

### 11.4. Static Type Differs from Runtime Class

If you have overloads `display(Object)` and `display(String)`, calling `display(ref)` on a variable `Object ref = "Java";` selects the `display(Object)` overload based on the static type `Object`, even though the actual object is `String`. If the selected method is an instance method and is overridden, dynamic dispatch may choose the implementation at runtime, but **overload resolution already happened at compile time**. Do not use the object's runtime type to assume which overload is selected.

### 11.5. There Is No Conversion from Arbitrary Strings to Numbers

Even though `"42"` contains digit characters, `sum("42", 3)` is not compatible with `sum(int,int)`. If the data really is text input, convert it intentionally via `Integer.parseInt("42")`, while handling `NumberFormatException` if the data is invalid.

### 11.6. Passing `null` Can Be Type-Valid Yet Invalid in Business Logic

A reference-type parameter such as `String` can normally accept `null` in the standard Java type system, unless the API uses other verification tools or specific contracts. The compiler does not automatically forbid `greet(null)`; if the method body calls `name.length()`, there is a risk of `NullPointerException`. When a non-null value is required, use checks at the entry point or appropriate analysis mechanisms.

## 12. Step-by-Step Procedure for Checking a Call

When reading `service.process(arg1, arg2, ...)`, check:

1. **Receiver object/type and method name**: identify the accessible methods named `process` within the valid scope. Rules for `static`, instance, and access permissions may eliminate some candidates.
2. **Count the arguments at the call site**: do not confuse the number of elements in a passed array with the number of arguments. Check whether a suitable overload/varargs exists.
3. **Determine the static type of each expression**: literal, variable, arithmetic expression, method call, generic method invocation. Do not guess from runtime values.
4. **Pair each argument with each parameter in order**: position 1 with position 1, position 2 with position 2; Java does not automatically reorder by name.
5. **Check valid conversions**: exact match, primitive/reference widening, boxing/unboxing, and conversions in the overload resolution phases; do not assume automatic narrowing or string parsing.
6. **If there are multiple overloads**, apply the applicability phases and the most-specific rule. Check for the possibility of an **ambiguous method call**.
7. **If generics are involved**, examine bounds, type inference, and invariance/wildcards; do not infer that all `List<...>` types can be passed interchangeably.
8. **If varargs is used**, separate the fixed parameters and the trailing array/varargs portion; ensure each element has a compatible type.
9. **Check business meaning**: even if the compiler accepts the call, swapping two numbers of the same type or passing null can still be wrong.
10. **When an error occurs**, compare the `required`, `found`, and candidate method list details; fix the root cause in type, count, order, or API.

## 13. Self-Check Questions

**Question 1.** `static void order(String id, int count)` is called with `order(4, "X")`. Is this valid?  
**Answer:** No, if that is the only overload. The two arguments have their type order swapped. Fix it to `order("X", 4)`.

**Question 2.** Is calling `static void scale(long value)` with `scale(10)` valid?  
**Answer:** Yes. The `int` type of the literal `10` can be widened to `long`.

**Question 3.** Is calling `static void byteValue(byte b)` with `byteValue(10)` automatically valid because `10` is within the byte range?  
**Answer:** No. Method invocation does not automatically narrow an `int` literal down to `byte`. Use a variable of type `byte`, an intentional cast, or design the method to accept `int`.

**Question 4.** Given `static void labels(String... items)`, are `labels()`, `labels("A")`, and `labels("A", "B")` valid?  
**Answer:** Yes. The varargs part allows 0, 1, or more `String` values.

**Question 5.** Suppose `f(long)` and `f(Integer)` exist; which overload does `f(5)` normally select?  
**Answer:** `f(long)`, because primitive widening applies in the strict phase before `int -> Integer` boxing is needed.

**Question 6.** Given `void pick(String)` and `void pick(Integer)`, does `pick(null)` always select one of the overloads?  
**Answer:** No. In this case, the call is ambiguous because the two reference types do not have a most-specific relationship sufficient to select a single one.

**Question 7.** Is a variable `List<Integer> ages` directly compatible with a `List<Number>` parameter?  
**Answer:** No. Java generics are normally invariant. If you only need to read the numbers, `List<? extends Number>` may be a more suitable parameter.

**Question 8.** Do `subtract(9, 4)` and `subtract(4, 9)` differ in type checking if both parameters are `int`?  
**Answer:** Both are valid in terms of types and argument count, but their mathematical results differ. The compiler does not determine the intended "minuend" on behalf of the programmer.

**Question 9.** `Object obj = "A";`, the only method is `consume(String)`. Is `consume(obj)` automatically valid because obj currently holds a String?  
**Answer:** No. The static type of `obj` is `Object`; an intentional check and narrowing or an appropriate declared type change is needed.

**Question 10.** If a method accepts `int[]`, do `call(new int[]{1,2})` and `call(1,2)` have the same number of arguments?  
**Answer:** No. The first call has **one array argument**; the second call has **two integer arguments**. A method that only accepts `int[]` does not accept the second call form unless the API declaration supports variable arity.

## Key Takeaways

When calling a Java method, the **count**, **order**, and **static types of the arguments** must match an applicable method or constructor. Java matches arguments **by position**, not by parameter name. The compiler allows certain conversions such as widening, boxing/unboxing, and varargs, but does not perform arbitrary narrowing or parse strings into numbers. When multiple overloads exist, Java resolves them using phases and the most-specific method selection rule; generic type bounds and `null` can also determine whether a call is valid or fails. After validation, argument expressions are evaluated **from left to right** and their values are passed into the parameters. Compile-time checks help prevent type/count errors, while ensuring the correct **business meaning** of argument order remains the programmer's responsibility.
