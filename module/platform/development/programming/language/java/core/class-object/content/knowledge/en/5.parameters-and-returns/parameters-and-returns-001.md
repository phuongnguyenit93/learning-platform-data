# Distinguishing Formal Parameters and Call-Site Arguments in Java

When reading a Java method call such as `greet("An", 2)`, it is necessary to distinguish two concepts:

- **Formal parameter**: a variable **declared in the method definition** to receive data when the method is called. For example, `String name` and `int times` in `void greet(String name, int times)`.
- **Argument (actual argument)**: an **expression supplied at the call site** to pass data into the corresponding parameters. For example, `"An"` and `2` in `greet("An", 2)`.

The two concepts sit on **two different sides of a call**: a formal parameter is part of the *declaration*, whereas an argument is part of the *call*. Java passes the **value** obtained from the argument expression into the parameter variable, even when that value is an **object reference**.

## 1. Quick Identification with an Example

```java
static void greet(String name, int times) {
    for (int i = 0; i < times; i++) {
        System.out.println("Xin chào " + name);
    }
}

// When called in main or another method:
greet("An", 2);
```

In the **declaration**:

- `String name` is the first formal parameter, of type `String`, named `name`.
- `int times` is the second formal parameter, of type `int`, named `times`.

In the **call**:

- `"An"` is the first argument, a string expression.
- `2` is the second argument, an integer literal.

When called, the value `"An"` is used to initialize the parameter `name`, and `2` is used to initialize `times`. Therefore, the method prints twice:

```text
Xin chào An
Xin chào An
```

The snippet above illustrates the syntax and behavior; to run it standalone, the method declaration and the call must be placed inside an appropriate class/method. A compilable, runnable program is in section 4.

| Criterion | Formal parameter | Call-site argument |
| --- | --- | --- |
| Where does it appear? | Inside the `(...)` of a method/constructor **declaration** | Inside the `(...)` of a **call expression** |
| Example | `int quantity` in `buy(int quantity)` | `3` in `buy(3)` |
| Nature | A **variable** with a declared name and type, belonging to the method's scope | An **expression** evaluated to produce the value passed in |
| Must it be a variable? | It is a parameter variable declaration | No: it can be a literal, variable, calculation, method call, `new ...` |
| Scope | Inside the method body according to scope rules | In the calling code; the expression itself does not create a parameter variable |
| When does it get a value? | Each time the method is called, the parameter is initialized with the corresponding argument value | The argument expression is evaluated at the call site |
| Type relationship | The parameter type participates in checking the validity of the call | The expression result must be appropriately convertible to the parameter type |

**Reading tip:** `calculate(int x, int y)` is *naming the inputs*; `calculate(10, value + 1)` is *supplying the input values*.

## 2. Structure of a Method Declaration and Call

A basic method declaration:

```java
static int add(int left, int right) {
    return left + right;
}
```

A call:

```java
int sum = add(10, 5);
```

The components play different roles:

- `add` is the method name, and `int` before `add` is the **return type**.
- `int left` and `int right` are **two formal parameter declarations**.
- `10` and `5` are **two argument expressions**.
- `sum` is the **variable receiving the returned result**; it is not a parameter of `add`.
- `return left + right;` returns an `int` result back to the caller; returning a result is different from passing arguments into the method.

An argument expression does not have to be a hardcoded value:

```java
int base = 4;
int result = add(base + 1, Math.max(2, 7));
```

In this case:

1. The first argument `base + 1` evaluates to `5`.
2. The second argument `Math.max(2, 7)` evaluates to `7`.
3. The two parameters `left` and `right` of `add` receive the values `5` and `7`.
4. The method returns `12` and the variable `result` receives that value.

**There is no naming arguments by parameter name at a call** in Java 17. You do not write `add(left: 5, right: 7)` like the named arguments syntax of some other languages. The standard way to call it is `add(5, 7)` with corresponding positions.

## 3. How Java Passes Values from Arguments to Parameters

When a method is called, Java logically performs:

1. Determines the method to invoke according to the rules for name, types, number of arguments, overloading, and accessibility.
2. Evaluates the receiver expression if needed and the argument expressions according to Java's evaluation order rules.
3. Checks/performs the appropriate conversions to initialize the parameter variables.
4. Executes the method body with **a dedicated set of parameter variables for that call**.
5. When the method finishes, returns control to the caller, along with a return value if the method is declared with a type other than `void`.

Key point: **Java always passes parameters by value (pass-by-value)**.

- For primitive-type arguments such as `int`, `double`, or `boolean`, the parameter receives a **copy of the primitive value**.
- For reference-type arguments such as `Person` or `List<String>`, the parameter receives a **copy of the reference value**. Both the caller and the parameter can refer to the **same object**, yet they are still **two different variables**.
- **Reassigning a parameter** does not reassign the caller's reference variable.
- **Modifying the state of the shared referenced object**, if the object permits it, can be observed by the caller.

You should not phrase this as “Java passes objects by reference” because that can easily be misunderstood to mean Java allows a method to directly modify the caller's *variable*. Java passes a **copy of the reference value**, not a pass-by-reference mechanism for variables in that sense.

## 4. Complete Example: Parameters, Arguments, and Pass-by-Value

Save all of the following code to **`ParameterArgumentDemo.java`**:

```java
class Person {
    String name;

    Person(String name) {
        this.name = name;
    }
}

public class ParameterArgumentDemo {
    static void greet(String name, int times) {
        for (int i = 0; i < times; i++) {
            System.out.println("Xin chào " + name);
        }
    }

    static int add(int left, int right) {
        return left + right;
    }

    static void changeNumber(int number) {
        number = 999;
        System.out.println("Trong changeNumber: " + number);
    }

    static void changeName(Person person) {
        person.name = "Bình";
    }

    static void replacePerson(Person person) {
        person = new Person("Linh");
        System.out.println("Trong replacePerson: " + person.name);
    }

    public static void main(String[] args) {
        greet("Java", 2);

        int base = 7;
        System.out.println("Tổng: " + add(base, 5));

        changeNumber(base);
        System.out.println("Sau changeNumber: " + base);

        Person original = new Person("An");
        changeName(original);
        System.out.println("Sau changeName: " + original.name);

        replacePerson(original);
        System.out.println("Sau replacePerson: " + original.name);
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 ParameterArgumentDemo.java
java ParameterArgumentDemo
```

**Expected output:**

```text
Xin chào Java
Xin chào Java
Tổng: 12
Trong changeNumber: 999
Sau changeNumber: 7
Sau changeName: Bình
Trong replacePerson: Linh
Sau replacePerson: Bình
```

Detailed explanation:

- In `greet(String name, int times)`, `name` and `times` are formal parameters; in `greet("Java", 2)`, `"Java"` and `2` are arguments.
- In `add(int left, int right)`, `left` and `right` are parameters. In `add(base, 5)`, the **variable `base` in the argument position** is *read to obtain the value* `7` and the literal value `5` is passed in; the two parameters are not two new names for the variable `base`.
- `changeNumber(base)` copies the primitive value `7` into the parameter `number`. Assigning `number = 999` only changes the **parameter inside the call**, so `base` in `main` remains `7`.
- `changeName(original)` copies the **reference to the `Person` object** into the parameter `person`. `person.name = "Bình"` modifies the shared object, so `original.name` becomes `"Bình"`.
- `replacePerson(original)` also receives a copy of the reference. `person = new Person("Linh")` only reassigns the parameter variable `person` to refer to the new object; the variable `original` in `main` still points to the original object named `"Bình"`.

Diagram right after calling `changeName(original)`:

```text
In main:   original ──┐
                      ├────> Person { name: "An" }
Parameter:   person ──┘

person.name = "Bình"    => shared object changes name to "Bình"
```

Diagram inside `replacePerson(original)` **after reassigning the parameter**:

```text
In main:   original ────────> Person { name: "Bình" }

Parameter: person   ────────> Person { name: "Linh" }
```

The two reference variables no longer point to the same object; only the **local variable `person`** has changed. After the method finishes, `original` has not been reassigned.

## 5. What Kinds of Expressions Can Arguments Be?

An argument is an **expression with a compatible value**, and does not have to be a declared variable. The following examples assume they appear in a context with the corresponding declarations:

| Call | Argument expression | Passed value |
| --- | --- | --- |
| `printNumber(5)` | Literal `5` | Integer `5` |
| `printNumber(total)` | Reading variable `total` | Current value of `total` |
| `printNumber(a + b)` | Addition expression | Result of the addition |
| `printNumber(Math.abs(-8))` | Method call | `8` |
| `showName("An" + " Bình")` | String concatenation | `"An Bình"` |
| `save(new Person("Lan"))` | Object creation | Reference to the new object |
| `showPerson(null)` | `null` literal | Null reference, if the parameter type is compatible |
| `process(flag ? x : y)` | Conditional expression | Value of the selected branch |
| `accept(list.get(0))` | Method call on an object | Result of `get(0)` |

Because each argument can be an expression, the number of formal parameters of a method **is not equivalent to** the number of local variables appearing in the call. For example, `sum(a + b, c * 2)` has **two arguments**, even though the expressions read **three variables** `a`, `b`, `c`.

### Argument Expressions Are Evaluated Before the Method Body Runs

```java
static void show(int value) {
    System.out.println("Trong show: " + value);
}

// Inside a method:
int number = 3;
show(number++);  // Argument is evaluated, number is incremented
```

`show` receives the **old value `3`** because `number++` is a post-increment; the variable `number` at the call site is afterward `4`. If you want to avoid hard-to-follow side effects, compute the result in a separate statement and then pass it into the method.

## 6. Java Evaluates Argument Expressions from Left to Right

The order of expressions with side effects is important knowledge when calling methods with multiple parameters. Java specifies that the evaluation order of argument expressions is **from left to right**.

A standalone Java 17 example, saved as **`ArgumentOrderDemo.java`**:

```java
public class ArgumentOrderDemo {
    static int trace(String label, int value) {
        System.out.println("Đánh giá " + label + ": " + value);
        return value;
    }

    static int add(int left, int right) {
        System.out.println("Bắt đầu add");
        return left + right;
    }

    public static void main(String[] args) {
        int result = add(
                trace("trái", 2),
                trace("phải", 3)
        );
        System.out.println("Kết quả: " + result);
    }
}
```

```bash
javac -encoding UTF-8 ArgumentOrderDemo.java
java ArgumentOrderDemo
```

**Stdout:**

```text
Đánh giá trái: 2
Đánh giá phải: 3
Bắt đầu add
Kết quả: 5
```

Meaning:

1. Java evaluates the first argument `trace("trái", 2)` and obtains `2`.
2. Only after that does it evaluate the second argument `trace("phải", 3)` and obtain `3`.
3. Once the argument values have been prepared, the body of `add` receives the parameters `left = 2` and `right = 3`.
4. The return value `5` is assigned to `result`.

If an argument expression throws an exception and the call is aborted, subsequent argument expressions may **not be evaluated**. Therefore, avoid overusing increment/decrement operations or state updates inside an argument list when doing so makes the code hard to understand.

**Arguments are not necessarily computed where the method is declared.** An argument expression runs at call time; only the parameters are used inside the body of the corresponding call.

## 7. Count, Position, and Data Types Between Arguments and Parameters

For a method without `varargs`, Java requires the **number of arguments** to match the **number of formal parameters**, and each argument must have a type that can be converted to the parameter type according to the applicable rules.

```java
static void register(String username, int age) {
    System.out.println(username + ": " + age);
}
```

Calls:

```java
register("An", 20);       // Valid
register("Bình", 18);     // Valid

// register("An");        // INVALID: missing one argument
// register("An", 20, 1);  // INVALID: one extra argument
// register(20, "An");     // INVALID: incompatible order/types
```

The call examples assume they are placed inside a method; the two commented-out statements will not compile if uncommented.

**Position matters.** Java matches the first argument with the first parameter and the second argument with the second parameter, except in the special case of the varargs mechanism. Parameter names themselves do not control how arguments are matched.

### 7.1. Valid Type Conversions When Passing Arguments

The argument type does not always have to be **identical to** the parameter type. Java allows compatible conversions in a method invocation context, such as:

```java
static void showLong(long number) {
    System.out.println(number);
}

static void showBoxed(Integer number) {
    System.out.println(number);
}

static void showObject(Object value) {
    System.out.println(value);
}
```

Examples inside a method:

```java
showLong(10);       // int -> long: widening primitive
showBoxed(10);      // int -> Integer: boxing
showObject("Hello");// String -> Object: widening reference
```

In addition, unboxing (`Integer` to `int`) occurs when conditions are appropriate. **Do not assume that all types are converted**: `showLong("10")` is invalid because Java does not automatically convert a string to an integer in a method call. If you pass `null` to a parameter that expects `int`, the call is invalid; if you pass an `Integer` variable whose value is `null` to be unboxed into `int`, it can throw a `NullPointerException` at runtime.

Which conversions are accepted in a call also depends on overloading and the phases of method selection. Do not infer that Java will pick just any overload simply based on the “most convenient cast”.

### 7.2. Parameter Types Participate in Overload Selection

Example:

```java
static void display(int number) {
    System.out.println("int: " + number);
}

static void display(String text) {
    System.out.println("String: " + text);
}
```

`display(5)` calls the overload with an `int` parameter; `display("5")` calls the overload with a `String` parameter. Declarations with the **same name but different parameter type lists** constitute overloading.

Overloads **cannot differ only in parameter names**:

```java
// INVALID when both are in the same class:
// static void set(int first) { }
// static void set(int second) { }
```

The names `first` and `second` do not make the two method signatures different.

Similarly, two overloads with the same name and parameter type list that differ only in **return type** are also invalid. Java selects an overload based on the types and number of arguments along with the corresponding rules, not merely on formal parameter names or the type of the variable on the left-hand side of an assignment.

### 7.3. `null` Can Cause Ambiguous Overloads

Consider two overloads:

```java
static void read(String text) { }
static void read(Integer number) { }
```

`read(null)` is an **ambiguous call** because `null` can be used for both `String` and `Integer`, and the two types have no direct subtype relationship to choose a more specific overload. You can make your intent explicit when needed:

```java
read((String) null);
read((Integer) null);
```

These snippets only illustrate syntax and are not standalone programs. For real-world APIs, avoid overloads that can easily cause ambiguity, or use different method names to express intent.

## 8. Formal Parameters Are Local Variables Per Call

Parameter names have their own scope inside the method body according to language rules. Each call has **its own parameter variables**, so calls do not share the same parameter variable just because they use the same name.

```java
static int twice(int value) {
    value = value * 2;
    return value;
}
```

A calling snippet:

```java
int original = 6;
int first = twice(original);
int second = twice(original);

System.out.println(original); // 6
System.out.println(first);    // 12
System.out.println(second);   // 12
```

In each call, the parameter `value` is initialized to `6` from the argument `original`; the line `value = value * 2` only modifies the **parameter variable of the current call**.

**Parameters cannot be declared with duplicate names in the same parameter list.** For example, `void f(int x, int x)` is invalid. Inside the method body, you also cannot declare a local variable with the same name as a parameter in an overlapping scope:

```java
static void show(int count) {
    // int count = 0; // INVALID: duplicate parameter name in the same scope
    System.out.println(count);
}
```

Conversely, different methods can use the same parameter name, such as `add(int value)` and `multiply(int value)`, because they are in different method scopes.

### 8.1. Parameters Can Shadow Fields

```java
class User {
    private String name;

    User(String name) {
        this.name = name;
    }

    void rename(String name) {
        this.name = name;
    }
}
```

In the constructor and `rename`:

- `name` (without `this`) is the **formal parameter**.
- `this.name` is the **field of the current object**.
- `this.name = name;` copies the reference value from the parameter to the field.

Using a parameter name that matches a field name is common and valid. `this` helps clearly distinguish the two independent variables; `this.name` is not another parameter.

## 9. Applying `final` to Formal Parameters

A parameter can be declared `final`:

```java
static void printLength(final String text) {
    System.out.println(text.length());
    // text = "Khác"; // INVALID: cannot reassign a final parameter
}
```

`final` prevents **reassigning the parameter variable** inside the method body. It does **not** prevent calling methods on a referenced mutable object:

```java
static void addItem(final java.util.List<String> items) {
    items.add("Mới"); // Valid if the List supports adding elements
    // items = new java.util.ArrayList<>(); // INVALID: reassigning a final parameter
}
```

The line `items.add("Mới")` operates on the referenced `List` object; it does not reassign the `items` variable. To prevent the method from modifying the list, there must be an appropriate contract and implementation, not just adding `final` to the parameter.

Using `final` is a choice of the API or development team; it does not turn Java's parameter-passing mechanism into pass-by-reference or automatically guarantee object immutability.

## 10. Variable-Length Parameters (Varargs) and Call-Site Arguments

For a method with **varargs**, the last parameter is declared with the syntax `Type... name`. Inside the method body, it behaves like **an array variable** of the corresponding type.

```java
static int sumAll(int... numbers) {
    int sum = 0;
    for (int n : numbers) {
        sum += n;
    }
    return sum;
}
```

In the declaration `sumAll(int... numbers)`, there is only **one formal parameter**: `numbers`, whose type used inside the body is `int[]`.

When calling it, variable arguments can be passed:

```java
sumAll();                     // No additional arguments, empty array
sumAll(1, 2, 3);              // Three int argument expressions
sumAll(new int[]{4, 5});     // One argument, an int[] array
```

Java can package those individual int values into an array to supply to the varargs parameter according to method invocation rules. `varargs` must be placed **at the end of the parameter list**, and there can only be **one variable-length parameter** in a declaration.

Standalone example, save as **`VarargsDemo.java`**:

```java
public class VarargsDemo {
    static int sumAll(int... numbers) {
        int sum = 0;
        for (int number : numbers) {
            sum += number;
        }
        return sum;
    }

    static void report(String title, int... scores) {
        System.out.println(title + ": " + sumAll(scores));
    }

    public static void main(String[] args) {
        System.out.println(sumAll());
        System.out.println(sumAll(1, 2, 3));
        System.out.println(sumAll(new int[]{4, 5}));
        report("Điểm", 2, 3, 4);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 VarargsDemo.java
java VarargsDemo
```

Stdout:

```text
0
6
9
Điểm: 9
```

In `report(String title, int... scores)`, `title` and `scores` are **two formal parameters**. The call `report("Điểm", 2, 3, 4)` has **four argument expressions**. The last three integers are processed by the varargs mechanism into the `scores` array.

**Do not infer that “the number of arguments is always equal to the number of parameters”.** That holds for normal non-varargs calls at the argument-list level, but with varargs the actual number of expressions can vary. In the array-style call `sumAll(new int[]{4, 5})`, the entire array is **one argument**.

## 11. Constructor Parameters Also Differ from `new` Arguments

Constructors have **formal parameters** just like methods, and when creating an object with `new`, the expressions inside the parentheses are **arguments** to the constructor call.

```java
class Book {
    private final String title;
    private final int pages;

    Book(String title, int pages) {
        this.title = title;
        this.pages = pages;
    }

    String summary() {
        return title + " (" + pages + " trang)";
    }
}
```

Call snippet inside a method:

```java
Book book = new Book("Java Core", 320);
System.out.println(book.summary());
```

In the declaration `Book(String title, int pages)`, `title` and `pages` are **formal parameters of the constructor**. In `new Book("Java Core", 320)`, the string and the number are **two arguments**. `this.title` and `this.pages` are **fields of the new object** assigned by the constructor from the parameters.

This does not turn `new Book(...)` into a `void` method call: a constructor **declares no return type**; the object creation expression `new Book(...)` creates the object and yields a reference to the object if it completes normally.

## 12. Instance Method Call Arguments and the Receiver Expression

Consider:

```java
class Calculator {
    int multiply(int a, int b) {
        return a * b;
    }
}
```

A call:

```java
Calculator calculator = new Calculator();
int result = calculator.multiply(3, 4);
```

It is necessary to distinguish:

- `calculator` is the **receiver expression** (the object on which the method is called).
- `3` and `4` are **two argument expressions** of the call.
- `int a` and `int b` are **two declared formal parameters**.
- The `this` keyword inside the instance method body (if used) refers to the receiver object; it is **not a formal parameter that you declare in the `(...)` list**.
- `result` receives the **return value** `12`; it is not an argument passed into `multiply`.

For a `static` method such as `Math.max(3, 4)`, `Math` is the class name used to access the method and there is no instance receiver `this`. The two expressions `3` and `4` are still arguments.

A method can have no formal parameters at all:

```java
static String greeting() {
    return "Xin chào";
}
```

The call `greeting()` has no arguments. The empty parentheses are part of the call syntax and do not mean the method cannot return a value.

## 13. Lambdas and Type Parameters: Do Not Confuse Them with Value Arguments

In Java, the word “parameter” also appears in other contexts that need to be distinguished when reading code:

### 13.1. Formal Parameters of a Lambda Expression

```java
java.util.function.Function<Integer, Integer> square =
        (Integer number) -> number * number;

int result = square.apply(5);
```

`number` is the **formal parameter of the lambda**; it receives data when the function is invoked through the corresponding functional method. `5` is the argument of the call `apply(5)`; the example returns `25`.

Java also allows type inference in many lambdas:

```java
java.util.function.Function<Integer, Integer> doubleIt =
        value -> value * 2;
```

`value` is still a parameter, even though the `Integer` type is not written explicitly.

### 13.2. Type Parameters and Type Arguments in Generics

```java
static <T> T identity(T value) {
    return value;
}
```

In this declaration, there are **two different categories**:

- `T` in `<T>` is the **type parameter** of the generic method.
- `T value` is the **formal parameter receiving a value**; its type depends on the generic application.

Call:

```java
String text = MyUtils.<String>identity("Java");
```

Assuming the `identity` method has been declared `static` in the `MyUtils` class, `String` in `<String>` is the **type argument**, while `"Java"` inside `(...)` is the **value argument** of the method.

Both include the word “argument”, but in **different contexts**. When a question asks about “formal parameters and arguments at a method call”, the focus is on the **variable list inside parentheses** and the **argument expressions inside parentheses**, not the generic syntax inside `<...>`.

## 14. The `String[] args` Parameter of the `main` Method

Traditional entry-point method:

```java
public static void main(String[] args) {
    System.out.println(args.length);
}
```

In the declaration `main(String[] args)`, `args` is **one formal parameter** of type `String[]`.

When running the program via the launcher:

```bash
java Main red blue
```

If the `Main` class contains the `main` method shown above and has been compiled, the application normally receives a command-line argument array with two string elements `"red"` and `"blue"`, and therefore prints `2`.

Note that there are **two different invocation levels**:

- In the Java class, `main` has **one formal parameter** of array type.
- The user supplies words on the command line so that the launcher constructs the array data for `main`.

Do not confuse the number of tokens on the command line with the number of declared parameters of `main`. If you explicitly call `Main.main(new String[]{"red", "blue"})` from Java code, this call has **one array argument expression**.

Runnable example, save as **`Main.java`**:

```java
public class Main {
    public static void main(String[] args) {
        System.out.println("Số phần tử: " + args.length);
        for (String arg : args) {
            System.out.println(arg);
        }
    }
}
```

```bash
javac -encoding UTF-8 Main.java
java Main red blue
```

Stdout:

```text
Số phần tử: 2
red
blue
```

## 15. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “`int x` in `f(int x)` is an argument.” | `x` is the declared **formal parameter**; arguments appear in `f(10)` or `f(value)`. |
| “The passed variable name must match the parameter name.” | Only position, count, and type need to match; `f(total)` can still pass a value into a parameter named `x`. |
| “An argument must be the name of a variable.” | It can be a literal, a calculation, a call result, a `new` expression, etc. |
| “`f(a + b)` has two arguments because there are two variables.” | It has **one argument expression**, which is `a + b`. |
| “An `int` parameter and the `int` variable at the call site are the same variable.” | The parameter receives a **copy of the value** of the argument. |
| “Java passes objects by reference, so reassigning a parameter changes the caller's variable.” | Java copies the **reference value**; reassigning the parameter does not change the caller's variable. |
| “Every call must have a number of arguments strictly equal to the number of parameters.” | With **varargs**, the number of argument expressions can vary. |
| “Parameter names determine overloading.” | Overloading is based on the parameter type list and invocation rules, not on parameter names. |
| “`this` is an argument written inside `object.method(...)`.” | `this` represents the receiver inside an instance method, not an explicit argument inside the parentheses. |
| “`return` is a way to pass arguments.” | `return` transfers a result **out of the method**, whereas arguments supply data **from the call site into the method**. |
| “`final Person p` means the Person object cannot be modified.” | `final` on a parameter only forbids reassigning the parameter variable; it does not make the object immutable. |
| “`T` in `<T>` and `T value` are both value parameters.” | `T` is a **type** parameter; `value` is the formal parameter that receives a **value**. |

## 16. Self-Check Questions

### Question 1 — Counting Parameters and Arguments Correctly

```java
static int calculate(int x, int y, int z) {
    return x + y * z;
}

// Inside a method:
int a = 2;
int b = 3;
int result = calculate(a + b, 4, a);
```

**Answer:** `calculate` declares **three formal parameters**: `x`, `y`, `z`. The call has **three argument expressions**: `a + b`, `4`, `a`. The passed values are `5`, `4`, `2` respectively; the result is `5 + 4 * 2 = 13`.

### Question 2 — Modifying an Outer Primitive Variable?

```java
static void increment(int count) {
    count++;
}

// Inside a method:
int n = 10;
increment(n);
System.out.println(n);
```

**Answer:** Prints `10`. `n` is a variable argument; the parameter variable `count` is initialized with a **copy of the number `10`**. `count++` does not change `n`.

### Question 3 — Modifying the Object or Modifying the Parameter?

```java
class Box {
    int value;
}

static void change(Box box) {
    box.value = 20;
    box = new Box();
    box.value = 50;
}
```

Assuming the declarations above are already in a valid context, the calling snippet:

```java
Box original = new Box();
original.value = 5;
change(original);
System.out.println(original.value);
```

**Answer:** Prints `20`. The assignment `box.value = 20` modifies `original`'s object. After that, `box = new Box()` only switches the **parameter variable** to a new object; `box.value = 50` does not affect `original`.

### Question 4 — Number of Arguments with Varargs

```java
static void print(String heading, int... values) {
    System.out.println(heading + ": " + values.length);
}
```

Count them:

- `print("A");` has **one argument expression**, and the `values` array has `0` elements.
- `print("B", 1, 2);` has **three argument expressions**, and the `values` array has `2` elements.
- `print("C", new int[]{5, 6});` has **two argument expressions**, and the `values` array has `2` elements.

In all three cases, the `print` declaration has only **two formal parameters**: `heading` and `values`.

### Question 5 — Distinguishing Kinds of Names

```java
static <T> T echo(T item) {
    return item;
}
```

For the call `Util.<String>echo("OK")` (assuming `echo` belongs to the class `Util`):

- `T` is the **type parameter**.
- `item` is the **formal parameter receiving a value**.
- `String` in `<String>` is the **type argument**.
- `"OK"` in `("OK")` is the **value argument**.
- The returned result is the string `"OK"`.

## Key Takeaways

1. **Formal parameters** belong in the **declaration**: `method(Type parameterName)`.
2. **Arguments** belong at the **call site**: `method(expression)`. An argument can be any expression with a valid value, not necessarily a variable.
3. Arguments are evaluated and their values are used to initialize the parameter variables according to invocation rules; Java uses **pass-by-value**, even for references.
4. Changing a **parameter variable** does not change the caller's variable value; changing the **shared referenced object** can be observed from the caller.
5. The count, order, and types of arguments must match the selected method; **overloading** and **varargs** are cases requiring additional consideration.
6. **Passed-in arguments** and **`return` values** represent two different directions of data flow; the receiver, the variable receiving the result, and type arguments are also not formal parameters receiving values inside parentheses.
