# Static Methods and Calling via Class Name in Java

## 1. What Is a `static` Method?

In Java, a **static method** (or *class method*) is a method declared with the `static` modifier. It is associated with the **declaring type**, rather than being called on a **receiver object** like an instance method.

Typical syntax:

```java
class ClassName {
    static ReturnType methodName(ParameterType parameter) {
        // Process without needing an implicit receiver of ClassName.
        return /* appropriate value */;
    }
}
```

This is an **illustrative syntax template**, not complete code to be compiled verbatim.

Differences in how they are called:

- **Static method**: `ClassName.methodName(arguments)` — the **recommended** way to call it, indicating that the method belongs to the type's API.
- **Instance method**: `object.methodName(arguments)` — invokes behavior on a specific object.
- For a static method, **there is no implicit `this`** for the class declaring the method.
- A static method can access appropriate **static members**, use parameters, create objects, or access instance members through an **explicit object reference**.
- The `static` modifier **does not mean the method runs only once**. A static method can be called thousands of times; each call executes the method body according to Java semantics.

Familiar examples: `Math.max(3, 7)`, `Integer.parseInt("42")`, `Arrays.sort(array)`, and `Objects.requireNonNull(value)` are all static method calls via class name. Calling them does not require creating a `Math`, `Integer`, `Arrays`, or `Objects` instance.

**Remember:** a static method is **behavior accessed through a type**, not a “method that only uses static variables” or a “method that runs automatically”.

## 2. Declaring and Calling a Complete Static Method

File **`StaticMethodBasicsDemo.java`**:

```java
class Calculator {
    static int add(int a, int b) {
        return a + b;
    }

    static int square(int number) {
        return number * number;
    }

    static void printTitle() {
        System.out.println("Calculator");
    }
}

public class StaticMethodBasicsDemo {
    public static void main(String[] args) {
        Calculator.printTitle();

        int total = Calculator.add(10, 5);
        int result = Calculator.square(4);

        System.out.println("total=" + total);
        System.out.println("square=" + result);
    }
}
```

Compile/run with JDK 17+:

```bash
javac StaticMethodBasicsDemo.java
java StaticMethodBasicsDemo
```

**Standard output:**

```text
Calculator
total=15
square=16
```

Explanation:

1. `Calculator` is a class with three static methods.
2. `Calculator.printTitle()` calls a method with a `void` return type, which prints a message.
3. `Calculator.add(10,5)` returns an `int`; the caller assigns the result to `total`.
4. `Calculator.square(4)` computes the square of the argument.
5. There is no `new Calculator()` statement in `main`; **no Calculator object is needed** to call the three static methods.

A static method body can still declare local variables, use `if`, loops, throw exceptions, call other methods, and return results just like a regular method. The difference is that **there is no `this` receiver for the class containing the method**.

## 3. Why Should You Write `ClassName.method()`?

Java allows certain syntax for calling a static method through an object expression, such as `calculator.add(...)`, but that **does not turn a static method into an instance method**. Writing `Calculator.add(...)` is generally better because:

1. **Semantic accuracy**: the method belongs to the class and does not depend on the identity of `calculator`.
2. **Readability**: readers immediately see that this is a static API.
3. **Avoiding misconceptions about polymorphism**: static methods undergo **hiding**, not overriding via dynamic dispatch.
4. **Avoiding pointless evaluation of a qualifier expression**: if called through an expression with side effects, that expression can still be evaluated even though the resulting object is not used as a static receiver.
5. **Easier API discovery**: IDEs and code reviews clearly distinguish instance behavior from static utility/factory methods.

Example:

```java
Calculator calculator = new Calculator();

System.out.println(calculator.add(2, 3)); // Compiles, not recommended.
System.out.println(Calculator.add(2, 3)); // Recommended.
```

This is an **illustrative code snippet inside a method**; assume `Calculator` is the class with static `add` as in the previous section. Both lines return 5, but in the first line `calculator` is **not** passed to `add` as `this`.

Some IDE/compiler warnings refer to this as accessing a static member using an instance reference. Fix it for semantic correctness rather than treating it as a mandatory syntax error.

## 4. How Do Static Methods Differ from Instance Methods?

| Criterion | Static method | Instance method |
| --- | --- | --- |
| Declaration | Has `static` | Does not have `static` |
| Clear invocation | `TypeName.method()` | `reference.method()` |
| Receiver object of the declaring class | **None** | Has a receiver object |
| Direct `this` in the method body | Not allowed | Available in an appropriate instance context |
| Accessing an instance field by simple name | No, if there is no suitable receiver | Can use fields of `this` |
| Accessing a static field | Yes, subject to access permissions | Yes, though the class name should be used when clarity is needed |
| Overriding and runtime dispatch | **Does not override** like an instance method; can **hide** | Can be overridden and dynamically dispatched based on the object |
| Participating in an interface contract | A static method does not implement an instance abstract method | An instance method can implement an interface method |
| Needs an instance to call | No | Requires a valid receiver when called |
| Common purpose | Utility, factory, conversion, input-based processing | Object behavior and individual state |

### Example of a Class Containing Both Kinds of Methods

```java
class Student {
    private final String name;
    private int score;
    private static int created;

    Student(String name) {
        this.name = name;
        created++;
    }

    void addScore(int points) {
        this.score += points;
    }

    String summary() {
        return name + ":" + score;
    }

    static int createdCount() {
        return created;
    }
}
```

With `Student first = new Student("An");`:

- `first.addScore(10)`: **instance method**, the receiver is `first`, modifying `score` of this object.
- `first.summary()`: **instance method**, reads the state of the receiver object.
- `Student.createdCount()`: **static method**, reads the static field `created` shared by the class.
- `createdCount` cannot reference `this.score` on its own because no specific object has been selected.

**You should not** make `score` static just so a static method can read it. If `score` belongs to each individual Student, keep it as an instance field and provide an instance method or pass a Student object into a static method when appropriate.

## 5. Static Methods Have No `this`, Yet Can Still Operate on Objects

A common misconception: “You cannot use `this` inside a static method, so a static method cannot handle objects.” Wrong. It simply **has no implicit current object**; you can supply an object via a parameter.

Complete example, file **`StaticAndInstanceDemo.java`**:

```java
class Box {
    private int value;

    Box(int value) {
        this.value = value;
    }

    void add(int amount) {
        this.value += amount;
    }

    int value() {
        return value;
    }

    static void addTo(Box target, int amount) {
        target.add(amount);
    }

    static int sum(Box left, Box right) {
        return left.value + right.value;
    }
}

public class StaticAndInstanceDemo {
    public static void main(String[] args) {
        Box a = new Box(10);
        Box b = new Box(20);

        a.add(2);
        Box.addTo(b, 5);

        System.out.println(a.value());
        System.out.println(b.value());
        System.out.println(Box.sum(a, b));
    }
}
```

```bash
javac StaticAndInstanceDemo.java
java StaticAndInstanceDemo
```

```text
12
25
37
```

**Mechanism:**

- `a.add(2)`: the instance method `add` has `this == a`, modifying object `a` from 10 to 12.
- `Box.addTo(b, 5)`: the static method **has no `this`**; the parameter `target` holds the reference value to object `b`, then calls `target.add(5)` to modify b from 20 to 25.
- `Box.sum(a,b)`: the static method receives **two references** and reads the state of both objects to return 37.
- The instance fields `value` remain separate for each Box; having a static method access them **does not make the field static**.

Note: `Box.addTo(null, 5)` in the example will encounter a `NullPointerException` when attempting to call an instance method on a null `target`. A static method can be called without a Box receiver, but **the objects it uses itself** must still satisfy their own conditions.

## 6. Common Compile Error: Referencing an Instance Member Directly in a Static Context

Consider an intentionally incorrect declaration:

```java
// class User {
//     String name = "guest";
//
//     static void show() {
//         System.out.println(this.name); // Wrong: no this.
//     }
// }
```

Because `this.name` is located inside a static method body, the compiler cannot choose any `User` as the “current object”.

Even if `this` is omitted, writing `System.out.println(name);` is still invalid if `name` is an **instance field**: there is no suitable implicit receiver.

Similarly:

```java
class User {
    String name = "guest";

    void showName() {
        System.out.println(this.name);
    }

    static void show(User user) {
        // showName(); // Wrong: instance method has no receiver.
        user.showName(); // Correct if user is not null.
    }
}
```

This is a **compilable declaration**, because the intentionally invalid line has been commented out. Since `show(User)` is a static method, it uses the `user` parameter as an explicit receiver for the instance method `showName()`.

### Three Ways to Fix This Based on the Nature of the Need

1. If the behavior depends on the state of the **current object**, change the method into an **instance method** and call it through an object.
2. If the behavior processes an **object chosen by the caller**, keep it a static method, accept the object as a **parameter**, and access it through that reference.
3. If the data/behavior truly belongs at the **class level**, use a static field or a static utility without needing an instance.

Do not just add `static` to every field to stop the compiler from reporting an error; doing so can accidentally cause state that belongs to each individual object to be **shared across all instances**.

## 7. `main` Is Usually a Static Method

In the traditional way of writing Java programs:

```java
public static void main(String[] args) {
    // Program entry point.
}
```

`main` is a static method invoked by the Java launcher under the corresponding entry point contract. Because it is static, inside the body of `main` **there is no `this` for the program class**. It can call static helpers directly if in the same class or by class name:

File **`MainStaticDemo.java`**:

```java
public class MainStaticDemo {
    private int counter;

    static String heading() {
        return "Static Demo";
    }

    void increase() {
        counter++;
    }

    int counter() {
        return counter;
    }

    public static void main(String[] args) {
        System.out.println(MainStaticDemo.heading());

        // increase();     // Wrong: missing receiver.
        // this.increase(); // Wrong: main has no this.

        MainStaticDemo object = new MainStaticDemo();
        object.increase();
        object.increase();
        System.out.println(object.counter());
    }
}
```

```bash
javac MainStaticDemo.java
java MainStaticDemo
```

```text
Static Demo
2
```

In `main`:

- `MainStaticDemo.heading()` is an unambiguous static call.
- `object.increase()` is an instance call on an explicitly created object.
- `object.counter()` reads the object's own field.

A class with a static `main` method **can still contain instance methods/fields**; there is no rule that every method in the class containing `main` must be static.

## 8. Calling a Static Method from the Same Class: Simple Name or Class Name?

Inside the body of a class, Java generally allows calling a static method by its simple name:

```java
class TextUtils {
    static String normalized(String input) {
        return input.trim().toLowerCase();
    }

    static boolean matches(String left, String right) {
        return normalized(left).equals(normalized(right));
    }
}
```

This is a **class declaration**, without `main`. In `matches`, `normalized(left)` and `normalized(right)` resolve to the static method in the same class. They could also be written `TextUtils.normalized(left)` to emphasize where it is declared.

**Style rules:**

- Within the same class, a simple name like `normalized(...)` is usually short and readable when there is no conflict.
- When calling **another class**, prefer `ClassName.method(...)`.
- If shadowing/name resolution makes the code hard to follow, use an explicit qualifier such as `TextUtils.normalized(...)`.
- For static fields that are easily confused with instance fields, using `ClassName.FIELD` often helps clarify that the data belongs at the class level.

There is no requirement to write the class name before **every** static call in the same class; what matters is accurate and consistent expression.

## 9. Program Using a Static Utility and a Static Field

File **`TicketUtilsDemo.java`**:

```java
class Ticket {
    private final String code;
    private static int count;

    Ticket(String code) {
        this.code = code;
        count++;
    }

    String code() {
        return code;
    }

    static int createdCount() {
        return count;
    }

    static String formatCode(String raw) {
        return raw.trim().toUpperCase();
    }
}

public class TicketUtilsDemo {
    public static void main(String[] args) {
        Ticket first = new Ticket(Ticket.formatCode(" a-1 "));
        Ticket second = new Ticket(Ticket.formatCode(" b-2 "));

        System.out.println(first.code());
        System.out.println(second.code());
        System.out.println("created=" + Ticket.createdCount());
    }
}
```

```bash
javac TicketUtilsDemo.java
java TicketUtilsDemo
```

```text
A-1
B-2
created=2
```

- `formatCode` is static: it relies only on the input `raw`, without using the state of a specific Ticket.
- The `Ticket` constructor is **instance construction**, incrementing the static count when each object is created.
- `createdCount` is static: returns the total number of Ticket objects created by this constructor in the demo program.
- `first.code()` and `second.code()` are instance methods: each object has its own code.

If `count++` is used in a multithreaded program, synchronization/`AtomicInteger` is needed when an accurate count is desired. The `static` modifier makes a variable shared; it **does not automatically create thread safety**.

## 10. Static Methods Can Be Called Through a `null` Variable: Valid but Misleading

Consider:

```java
class Utility {
    static String message() {
        return "shared";
    }
}
```

A code snippet inside a method:

```java
Utility ref = null;

System.out.println(Utility.message()); // Recommended approach.
System.out.println(ref.message());     // Compiles; not recommended.
```

For a static method, the expression `ref.message()` is compiled into a static call according to the static type `Utility`, **without using `ref` as an instance receiver**. Therefore, `ref` being null in this snippet **does not** cause a `NullPointerException` solely from the static method call.

In contrast, `ref.instanceMethod()`, if `instanceMethod` is an instance method, will require a receiver object and cause a `NullPointerException` when ref is null, unless another exception occurs earlier during expression/argument evaluation.

### Runnable Example Comparing a Null Static Call and an Instance Call

File **`NullStaticCallDemo.java`**:

```java
class Greeter {
    static String shared() {
        return "shared";
    }

    String personal() {
        return "personal";
    }
}

public class NullStaticCallDemo {
    public static void main(String[] args) {
        Greeter greeter = null;

        System.out.println(greeter.shared());

        try {
            System.out.println(greeter.personal());
        } catch (NullPointerException ex) {
            System.out.println("instance receiver is null");
        }
    }
}
```

```bash
javac NullStaticCallDemo.java
java NullStaticCallDemo
```

```text
shared
instance receiver is null
```

**Conclusion:** this is a language behavior for understanding **how static invocation differs from virtual invocation**; **do not use `nullRef.staticMethod()` as a programming style**. Writing `Greeter.shared()` is both semantically safe and helps readers avoid mistakenly inferring a receiver.

## 11. The Expression Before the Dot Can Still Be Evaluated

A static call through an expression does not use the returned object as a receiver, yet **that expression can still be evaluated** and cause side effects.

File **`StaticQualifierEvaluationDemo.java`**:

```java
class Message {
    static void ping() {
        System.out.println("ping");
    }
}

public class StaticQualifierEvaluationDemo {
    static Message findMessage() {
        System.out.println("evaluating qualifier");
        return null;
    }

    public static void main(String[] args) {
        findMessage().ping();
        Message.ping();
    }
}
```

```bash
javac StaticQualifierEvaluationDemo.java
java StaticQualifierEvaluationDemo
```

```text
evaluating qualifier
ping
ping
```

- First, Java evaluates the expression `findMessage()`, prints `evaluating qualifier`, and returns null.
- Because the `ping` method is static, it **does not dereference this null value** to obtain an instance receiver; it prints `ping`.
- `Message.ping()` calls directly via the class name, with no `findMessage()` evaluation step, so it only prints `ping`.

This is why you should avoid `complexExpression().staticMethod()`: that call can **still perform unnecessary computation/side effects**, even though the selected method belongs entirely to the type.

## 12. Static Methods and Inheritance: Hiding, Not Overriding

**Instance methods** can participate in **dynamic dispatch**: the implementation is selected according to the runtime class of the receiver when the method is validly overridden.

**Static methods are not overridden in that sense**. When a subclass declares a static method whose signature matches a static method that could be inherited from the superclass, it can **hide** the superclass method. The method is selected based on **type and call resolution at compile time**, rather than on the runtime object like virtual dispatch.

### Example Contrasting Hiding with Overriding

File **`StaticHidingDemo.java`**:

```java
class Parent {
    static String typeName() {
        return "Parent-static";
    }

    String describe() {
        return "Parent-instance";
    }
}

class Child extends Parent {
    static String typeName() {
        return "Child-static";
    }

    @Override
    String describe() {
        return "Child-instance";
    }
}

public class StaticHidingDemo {
    public static void main(String[] args) {
        Parent reference = new Child();
        Child child = new Child();

        System.out.println(Parent.typeName());
        System.out.println(Child.typeName());

        System.out.println(reference.typeName());
        System.out.println(reference.describe());

        System.out.println(child.typeName());
        System.out.println(child.describe());
    }
}
```

```bash
javac StaticHidingDemo.java
java StaticHidingDemo
```

```text
Parent-static
Child-static
Parent-static
Child-instance
Child-static
Child-instance
```

Analysis:

1. `Parent.typeName()` is declared in Parent, so it returns `Parent-static`.
2. `Child.typeName()` selects the static method in Child, so it returns `Child-static`.
3. `reference` has static type `Parent` but its runtime object is Child. `reference.typeName()` **still selects Parent's static method**, returning `Parent-static`. Calling through a variable **should not be used** outside language-learning purposes.
4. `reference.describe()` is an overridden instance method, dynamically dispatched at runtime to `Child.describe()`, returning `Child-instance`.
5. `child.typeName()` selects the Child static method based on the static type `Child`; `child.describe()` calls the Child implementation.

**Proper practice:** when encountering multiple static methods with the same name across inheritance, use **`Parent.typeName()` or `Child.typeName()`** to accurately show which method is selected. Do not expect a static method to “be polymorphic by object”.

### You Cannot Change static/instance to “Override”

If a superclass has an instance method `void work()`, a subclass cannot declare `static void work()` with the same signature to override it; conversely, an instance method cannot be used to override an inherited static method under the relevant rules either. This is a **compile-time error**, not two different ways of overriding.

The `@Override` annotation is not used for static method hiding. If you place `@Override` on a static method intended to hide another, the compiler will report an error because static methods are not overridden like instance methods.

## 13. Not Every Static Method Is “Inherited” in the Same Way as an Instance Method

Static methods of a class can be **inherited or hidden** under the conditions Java applies to member inheritance. Thus, code such as `Child.someInheritedStatic()` can be valid if the static method is accessible and inherited, even though `Child` does not declare that method.

However, when you want to point directly to where the API is defined, prefer **the class name that actually declares the method** when that makes the code clearer.

**Important exceptions:**

- `private static methods` are not inherited like ordinary accessible members. A subclass declaring a method with the same signature as a private method of the superclass is not hiding in the same way as an inherited/accessible static member.
- Static methods on an **interface** have their own rule: they are **not inherited by an implementer or subinterface in a way that allows calling them through the implementer's/subinterface's name**; use **the declaring interface name**.
- Access modifiers, package boundaries, and module boundaries remain in effect when accessing a static method.

Do not generalize that “every static method can be called via any subclass name” or that “every static method is hidden by the same rules” without considering accessibility and the declaration source.

## 14. Static Methods in an Interface: Call Through the Interface Name Itself

Java allows an interface to declare static methods with a body. They often serve as helpers or factories directly related to the interface's contract.

File **`InterfaceStaticDemo.java`**:

```java
interface Validator {
    boolean valid(String input);

    static boolean notBlank(String input) {
        return input != null && !input.isBlank();
    }
}

class NameValidator implements Validator {
    @Override
    public boolean valid(String input) {
        return Validator.notBlank(input) && input.length() >= 3;
    }
}

public class InterfaceStaticDemo {
    public static void main(String[] args) {
        Validator validator = new NameValidator();

        System.out.println(Validator.notBlank("Java"));
        System.out.println(validator.valid("An"));
        System.out.println(validator.valid("Linh"));

        // NameValidator.notBlank("Java"); // Invalid.
        // validator.notBlank("Java");     // Invalid.
    }
}
```

```bash
javac InterfaceStaticDemo.java
java InterfaceStaticDemo
```

```text
true
false
true
```

- `Validator.notBlank(...)` is a **static interface method**, called through the name of the **declaring interface**.
- `valid(String)` is an instance abstract method of the interface. `NameValidator` implements the instance method using `@Override`.
- `NameValidator.notBlank(...)` is invalid because a static interface method is **not inherited** like a class static method.
- `validator.notBlank(...)` is also not a valid way to call an interface's static method; use `Validator.notBlank(...)`.

**Distinction:** `default` methods on an interface are instance methods with an implementation; static methods are not default methods and are not overridden like them.

## 15. Using Static Methods in a Utility Class

A utility class groups **functions independent of instance state** and usually has a `private` constructor to prevent callers from creating meaningless objects. In this example, `SlugUtils` provides two static methods and is called via the **class name** — fitting the focus of this lesson on static methods.

Save the file **`SlugUtilsDemo.java`**:

~~~java
final class SlugUtils {
    private SlugUtils() {}

    static String toSlug(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input required");
        }
        return input.trim().toLowerCase(
                java.util.Locale.ROOT).replace(' ', '-');
    }

    static boolean sameSlug(String left, String right) {
        return toSlug(left).equals(toSlug(right));
    }
}

public class SlugUtilsDemo {
    public static void main(String[] args) {
        System.out.println(SlugUtils.toSlug(" Java Core "));
        System.out.println(SlugUtils.sameSlug(
                " Hello World ", "hello world"));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SlugUtilsDemo.java
java SlugUtilsDemo
~~~

Stdout:

~~~text
java-core
true
~~~

`Locale.ROOT` avoids depending on the default locale when normalizing language-independent strings. Here `toSlug` and `sameSlug` operate on their arguments without reading the state of a `SlugUtils` instance.

**Boundary with the utility class design lesson:** the current lesson illustrates how to **call static methods**. The lesson **“Designing a Utility Class with a Private Constructor”** will further analyze constructor accessibility, `final`, API surface, the mutable static fields anti-pattern, testability, and cases where an instance service should be used instead of a utility.

## 16. Static Factory Method: Calling via Class Name to Create an Object

A static method **can still create instances**. This is the **static factory method** pattern, commonly seen in Java:

- `List.of(...)`: returns a list according to the API's contract.
- `LocalDate.of(...)`: returns a date value.
- `Integer.valueOf(...)`: returns an Integer object/value according to the API, possibly cached.
- `Optional.ofNullable(...)`: creates an Optional based on a possibly null reference.

**Not every static factory calls `new` every time**: an implementation may return an existing object, a cached object, or an appropriate subtype according to the contract.

Custom example, file **`StaticFactoryDemo.java`**:

```java
final class UserId {
    private final String value;

    private UserId(String value) {
        this.value = value;
    }

    static UserId of(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("blank id");
        }
        return new UserId(raw.trim().toUpperCase());
    }

    String value() {
        return value;
    }
}

public class StaticFactoryDemo {
    public static void main(String[] args) {
        UserId id = UserId.of(" u-7 ");
        System.out.println(id.value());
    }
}
```

```bash
javac StaticFactoryDemo.java
java StaticFactoryDemo
```

```text
U-7
```

- `UserId.of(...)` is a static method: the caller invokes it using the class name, without needing an existing `UserId`.
- `UserId(...)` is a private constructor: only code permitted to access it can call it to create an object.
- The instance method `value()` reads the state of the object returned by the factory.
- This design centralizes input validation and normalization; it prevents callers from bypassing conditions with `new UserId(...)` from external code.

**Avoid confusion:** a static factory is a **static method that returns a reference to an object**, not a constructor; a constructor has no return type and uses different syntax.

## 17. Method Overloading: Static Methods Can Also Share a Name with Different Parameters

A class can **overload** static methods with different parameter lists:

```java
class Converter {
    static String text(int number) {
        return "int:" + number;
    }

    static String text(double number) {
        return "double:" + number;
    }

    static String text(String value) {
        return "text:" + value;
    }
}
```

The call `Converter.text(5)` selects the overload taking `int`, `Converter.text(5.0)` takes `double`, and `Converter.text("A")` takes `String`, according to Java's overload resolution rules.

### Running Example

File **`StaticOverloadDemo.java`**:

```java
class Formatter {
    static String format(int value) {
        return "int=" + value;
    }

    static String format(String value) {
        return "str=" + value;
    }
}

public class StaticOverloadDemo {
    public static void main(String[] args) {
        System.out.println(Formatter.format(12));
        System.out.println(Formatter.format("12"));
    }
}
```

```bash
javac StaticOverloadDemo.java
java StaticOverloadDemo
```

```text
int=12
str=12
```

**Notes:**

- You cannot overload solely by **return type** when the name and parameter list are the same.
- The `static` modifier **does not create a different method signature**. In the same class, you cannot have both `static void print(int x)` and `void print(int x)` with the same signature.
- Overload resolution primarily occurs at compile time based on the argument types and Java rules; it is unrelated to the dynamic dispatch of instance overriding.

## 18. Generic Static Methods and Type Parameters

A static method can declare its own **type parameter**:

```java
class Identity {
    static <T> T keep(T value) {
        return value;
    }
}
```

Here `<T>` is declared **specifically for the method**, so `Identity.keep("Java")` returns an appropriate `String`, and `Identity.keep(42)` returns an appropriate `Integer` via boxing/inference.

### Runnable Example

File **`GenericStaticMethodDemo.java`**:

```java
class Values {
    static <T> T chooseFirst(T first, T second) {
        return first;
    }
}

public class GenericStaticMethodDemo {
    public static void main(String[] args) {
        String text = Values.chooseFirst("A", "B");
        Integer number = Values.chooseFirst(10, 20);

        System.out.println(text);
        System.out.println(number);
    }
}
```

```bash
javac GenericStaticMethodDemo.java
java GenericStaticMethodDemo
```

```text
A
10
```

**Generic class pitfall:**

```java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    // static T bad() { return null; } // Wrong: T is a type parameter of the class.
    static <U> U identity(U value) {
        return value;
    }
}
```

A static member of a generic class cannot directly use an **instance-level type parameter of the class** such as `T`. It is not bound to a particular `Box<String>` or `Box<Integer>` instance. However, a static method can declare **its own type parameter `<U>`**.

## 19. Static Import: Selectively Omitting the Class Name at Call Sites

Java supports `import static`:

```java
import static java.lang.Math.max;
import static java.lang.Math.min;
```

This makes it possible to write `max(3, 7)` instead of `Math.max(3, 7)` in the appropriate scope.

File **`StaticImportDemo.java`**:

```java
import static java.lang.Math.max;
import static java.lang.Math.min;

public class StaticImportDemo {
    public static void main(String[] args) {
        System.out.println(max(3, 7));
        System.out.println(min(3, 7));
        System.out.println(Math.max(10, 4));
    }
}
```

```bash
javac StaticImportDemo.java
java StaticImportDemo
```

```text
7
3
10
```

**Points to distinguish:**

- `import static` only affects how **names are resolved** in the source file. It **does not turn a static method into an instance method**.
- It does not automatically run the method, does not copy code, and does not create objects.
- Consider avoiding overuse of `import static ...*;` if static members easily collide with other method/constant names and make the code hard to read.
- For easily recognizable helpers such as `Math.max` or test assertions, static imports can improve clarity. For less familiar APIs, `ClassName.method()` usually expresses where the method is declared more clearly.

## 20. Method Reference to a Static Method

A static method can be used with a **method reference** using the syntax `TypeName::methodName` when it matches a functional interface.

File **`StaticMethodReferenceDemo.java`**:

```java
import java.util.function.Function;
import java.util.function.IntBinaryOperator;

public class StaticMethodReferenceDemo {
    static String decorate(String text) {
        return "[" + text + "]";
    }

    public static void main(String[] args) {
        Function<String, String> formatter =
                StaticMethodReferenceDemo::decorate;

        IntBinaryOperator bigger = Math::max;

        System.out.println(formatter.apply("Java"));
        System.out.println(bigger.applyAsInt(4, 9));
    }
}
```

```bash
javac StaticMethodReferenceDemo.java
java StaticMethodReferenceDemo
```

```text
[Java]
9
```

- `StaticMethodReferenceDemo::decorate` refers to the static method that takes a String and returns a String, matching `Function<String,String>`.
- `Math::max` refers to the overload matching `IntBinaryOperator`, which takes two `int` values and returns an `int`.
- This syntax does not call the method immediately when creating the reference; the invocation occurs when running the functional interface method (`apply` or `applyAsInt`).

**Distinction:** `object::instanceMethod` is a bound instance method reference, whereas `Type::instanceMethod` can be an unbound instance method reference when the functional interface provides the receiver as an argument. Not **every** `Type::method` necessarily refers to a static method; you must consider both the method and the target functional type.

## 21. Class Initialization Timing and Static Method Calls

A static method can be called without creating an instance, yet **calling a static method declared by a class** is typically one of the actions that triggers **class initialization** before the method body runs according to Java rules.

File **`ClassInitStaticCallDemo.java`**:

```java
class Service {
    static {
        System.out.println("Service initialized");
    }

    static void work() {
        System.out.println("Service.work");
    }

    Service() {
        System.out.println("Service constructor");
    }
}

public class ClassInitStaticCallDemo {
    public static void main(String[] args) {
        System.out.println("begin");
        Service.work();
        Service.work();
        new Service();
    }
}
```

```bash
javac ClassInitStaticCallDemo.java
java ClassInitStaticCallDemo
```

```text
begin
Service initialized
Service.work
Service.work
Service constructor
```

- The first call to `Service.work()` in the program triggers initialization of `Service` per the rules, so the static initializer prints once before the method.
- The second call **does not rerun** the static initializer, yet **re-executes** `work()` and prints the second line.
- Only `new Service()` invokes the constructor, so it prints `Service constructor` at the end.

**Do not confuse:** “a static initializer runs once in the class initialization lifecycle” is completely different from “a static method runs only once.” Class loaders/class initialization and failed class initialization scenarios have deeper rules, but there is no need to infer from the example that the method will be memoized or called automatically.

## 22. Static Fields and Static Methods: Shared Data Does Not Mean Thread Safety

A static method can access a static field:

```java
class Sequence {
    private static int next;

    static int nextId() {
        return ++next;
    }
}
```

`Sequence.nextId()` modifies a variable **shared at the class level**. In a single thread, the results of sequential calls may be 1, 2, 3... but across multiple threads, the `++next` operation is **not an atomic operation** as required for issuing unique IDs.

An alternative using an atomic counter:

```java
import java.util.concurrent.atomic.AtomicInteger;

class Sequence {
    private static final AtomicInteger NEXT = new AtomicInteger();

    static int nextId() {
        return NEXT.incrementAndGet();
    }
}
```

The second code snippet is an **alternative version** of the `Sequence` class; do not keep both in the same source set at the same time. AtomicInteger supports atomic updates according to its contract. In an environment requiring unique IDs across multiple JVMs/processes, an internal static counter is still **not sufficient**; an out-of-process coordination strategy is required.

### A Static Method Does Not Necessarily Have Static State

Many good static utilities are **stateless**:

```java
static int clamp(int value, int low, int high) {
    if (low > high) {
        throw new IllegalArgumentException("low > high");
    }
    return Math.max(low, Math.min(value, high));
}
```

This is a method fragment placed in a class. It relies only on its arguments and does not access shared mutable state. Therefore, do not equate “static” with “global variable” or “singleton”.

## 23. `synchronized static` Uses the Class Monitor, Not `this`

A static synchronized method locks the **monitor of the Class object** representing the class declaring the method; it does not lock a receiver instance because there is no `this`.

Example:

```java
class SharedCounter {
    private static int total;

    static synchronized void increase() {
        total++;
    }

    static synchronized int total() {
        return total;
    }
}
```

Both static synchronized methods belonging to `SharedCounter` use the monitor associated with `SharedCounter.class`.

An instance synchronized method instead locks the appropriate receiver object. Therefore, you cannot assume that a `synchronized` instance method and a `static synchronized` method **are locking the same monitor** to jointly protect a static field.

### Single-Threaded Runnable Example

File **`SynchronizedStaticDemo.java`**:

```java
class Counter {
    private static int count;

    static synchronized void increase() {
        count++;
    }

    static synchronized int count() {
        return count;
    }
}

public class SynchronizedStaticDemo {
    public static void main(String[] args) {
        Counter.increase();
        Counter.increase();
        System.out.println(Counter.count());
    }
}
```

```bash
javac SynchronizedStaticDemo.java
java SynchronizedStaticDemo
```

```text
2
```

The example only illustrates the **API and single-threaded behavior**; verifying concurrency requires a separate lesson with multiple threads and Java Memory Model guarantees. A static method is not automatically synchronized unless you declare/design an appropriate synchronization mechanism.

## 24. Access Modifiers: Calling via Class Name Still Requires Access Rights

Writing `ClassName.method()` does not “bypass” access checks.

Conditions may include:

- **The class name** must be accessible from the caller's location (public/package-private, enclosing types, and module boundaries if using JPMS).
- **The static method** must be accessible according to the `public`, `protected`, package-private, or `private` modifier.
- Methods located in an **interface** have their own access rules; static interface methods are called via the declaring interface name.
- If overloads exist, the selected signature must match the arguments and the access-control context.

Example:

```java
package library;

public class Secrets {
    private static String internal() {
        return "hidden";
    }

    public static String display() {
        return internal();
    }
}
```

From package `app`, if valid module/package access is present, `Secrets.display()` is accessible; `Secrets.internal()` is **not** accessible because it is private. The fact that a method belongs to the class and is called by class name does not make a private method public.

A static method on a **package-private top-level class** is also not automatically accessible from another package just because the method carries the public modifier.

## 25. Should Every Method That Does Not Use Fields Be Marked static?

Not necessarily. When choosing, consider **the method's role in the design**:

| Situation | Usually reasonable choice | Reason |
| --- | --- | --- |
| Computation function depending only on arguments | `static` utility | No receiver state |
| Factory creating an object with validation | `static` factory | No existing object needed |
| Reading/writing the current object's state | Instance method | Belongs to object behavior |
| Behavior that can be overridden by a subclass | Instance method | Requires polymorphic dispatch |
| Interface requiring each implementation to provide behavior | Instance method | Static cannot override an interface instance method |
| Helper serving only one class | `private static` if no receiver is needed, or private instance if one is | Clear access/design |
| Class-level behavior needing to update shared data | Static method with concurrency control | Shared data and API, not tied to one object |
| Method temporarily not using instance fields, yet possibly needing polymorphism/instance contract | Can remain instance | Do not force static just because the current body does not read `this` |

Do not turn static into a “mandatory performance optimization”. Java/JIT can optimize both static and instance methods; the choice should begin with **API semantics and extensibility**. A static method creates a static dependency point on a concrete type; in a system needing dependency injection/test doubles/multiple implementations, an instance abstraction or interface may be more suitable.

### Avoid Mutable Static State Unless Necessary

A **stateless** static utility is easy to test and reuse. If you write static methods depending on many static mutable fields, tests can affect one another due to shared state; concurrency is also difficult. When state has a clear lifecycle/identity, consider an object instance passed to the components that need it.

## 26. Common Mistakes and Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “A `static` method must be called using an object” | Should be called as `ClassName.method()`, no instance needed |
| “A static method runs only once” | It can run multiple times; static initializers are what have their own class-initialization rules |
| “A static method has `this` as the current class” | There is no implicit `this` in a static context |
| “A static method cannot access any object” | Can use an object passed as a parameter or an object created/found |
| “Add `static` to an instance field so a static method can read it” | Only right if the data is truly shared at the class level |
| “Calling `obj.staticMethod()` means the object is the receiver” | The syntax may be valid, but the method is still static; call it by class name |
| “`nullRef.staticMethod()` definitely throws NPE” | No, because static invocation does not dereference an instance receiver; avoid writing it that way |
| “A qualifier expression is not evaluated because the method is static” | It can still be evaluated and cause side effects |
| “A static method is overridden like an instance method” | Static method **hiding**, not dynamic dispatch |
| “`Parent ref = new Child(); ref.staticMethod()` calls the Child version” | The static method is selected by compile-time type/context, which may be the Parent version |
| “`@Override` is appropriate when hiding a static method” | No; `@Override` is for overriding instance methods |
| “The static/instance modifier is enough to overload the same signature” | No; identical signatures in the same class cause an error |
| “A static interface method is inherited by the implementer” | No; use the declaring interface name |
| “A static method implements an instance interface contract” | No; a matching instance method implementation is required |
| “`import static` turns the method into a method of the caller” | It only allows using the simple name via import resolution |
| “`Type::method` is always static” | It can refer to a static or an unbound instance method, depending on declaration/functional target |
| “A static generic method uses `T` from the generic class” | Must declare its own type parameter if needed |
| “`static` makes updating `count++` thread-safe” | No; appropriate concurrency control is needed |
| “A static method inside a public class is automatically public” | The method has its own access modifier |
| “A static factory is a constructor” | A factory is a static method returning an object, not a constructor |
| “A static method always needs to use a static field” | Stateless methods that only process arguments are also very common |
| “A static synchronized method locks `this`” | It locks the Class monitor; there is no `this` receiver |
| “You can call a static method on an interface via the implementing class name” | No, under the rules for static interface methods |

## 27. Quick Trace of How the Called Method Is Selected

Read the program and predict the output yourself:

File **`StaticCallTraceDemo.java`**:

```java
class Base {
    static String label() {
        return "Base";
    }

    String instance() {
        return "Base-instance";
    }
}

class Derived extends Base {
    static String label() {
        return "Derived";
    }

    @Override
    String instance() {
        return "Derived-instance";
    }
}

public class StaticCallTraceDemo {
    static String join(String left, String right) {
        return left + "/" + right;
    }

    public static void main(String[] args) {
        Base a = new Derived();
        Derived b = new Derived();

        System.out.println(Base.label());
        System.out.println(Derived.label());
        System.out.println(a.label());
        System.out.println(a.instance());
        System.out.println(join(b.label(), b.instance()));
    }
}
```

```bash
javac StaticCallTraceDemo.java
java StaticCallTraceDemo
```

```text
Base
Derived
Base
Derived-instance
Derived/Derived-instance
```

**Solution:**

1. `Base.label()` calls the static method declared in Base → `Base`.
2. `Derived.label()` calls the static method declared in Derived → `Derived`.
3. `a` has static type Base, even though it points to a Derived object. `a.label()` is a static invocation via an expression, so it selects Base → `Base`. This usage can be replaced with `Base.label()`.
4. `a.instance()` is an instance call; runtime dispatch goes to the Derived override → `Derived-instance`.
5. `b.label()` is static on type Derived; `b.instance()` uses instance dispatch to Derived; `join(...)` is a static method of the current class, called by its simple name within the same class; the combined result is `Derived/Derived-instance`.

**Skill to acquire:** when encountering `x.m()`, do not immediately assume that the JVM selects the method based on the runtime class of `x`. First check whether **the resolved declaration is static or instance**, and only then apply the right invocation rule.

## 28. Self-Check Questions with Answers

**Question 1.** Does the method `static int sum(int a,int b)` require creating an object before calling it?

**Answer:** No. Call `ClassName.sum(2,3)` if the method is accessible.

**Question 2.** Can `this.value++` be written directly inside a static method?

**Answer:** No. A static context has no `this` receiver. Use a specific object or move the behavior to an instance method when appropriate for the design.

**Question 3.** Can `static void update(Box b) { b.add(1); }` modify the caller's Box?

**Answer:** Yes, if `b` references a mutable Box object and `add` changes state. The parameter receives a copy of the reference value; a static method can still operate on an object via a parameter.

**Question 4.** Why should you use `Math.max(3,7)` instead of creating a Math object?

**Answer:** `max` is a static API associated with `Math`, requiring no receiver object and having no individual instance meaning.

**Question 5.** With `Greeter g = null; g.shared()` when `shared` is static, must an NPE necessarily occur?

**Answer:** No. A static method does not need to dereference a receiver instance. However, you should write `Greeter.shared()`.

**Question 6.** Does `find().ping()` with a static `ping` skip calling `find()`?

**Answer:** No. The qualifier expression is still evaluated according to language rules, so it can have side effects.

**Question 7.** Is a subclass declaring a static method with the same signature as a static superclass method overriding?

**Answer:** No; that is **method hiding** when the conditions are met. Static invocation does not use virtual dispatch like instance overriding.

**Question 8.** Interface `Check` declares `static boolean ok(...)`; can the implementer `CheckImpl` call `CheckImpl.ok(...)`?

**Answer:** That is not a valid way to call that static interface method. Use `Check.ok(...)`.

**Question 9.** Does `import static Math.max;` cause the static method to run automatically?

**Answer:** No. It only assists with name resolution; the full import syntax is normally `import static java.lang.Math.max;`.

**Question 10.** Is `static` synonymous with “shared mutable field”?

**Answer:** No. A static method can be completely stateless; mutable static fields are not required.

**Question 11.** Can a static method be overloaded?

**Answer:** Yes, if the parameter lists differ. You cannot overload solely by return type or solely by differing in the `static` modifier.

**Question 12.** Can a generic static method be written as `static <T> T id(T x)`?

**Answer:** Yes. `T` is the method's own type parameter. You cannot simply use a generic class's class-level type parameter `T` in a static context.

**Question 13.** Does calling a static method a third time re-run the static initializer?

**Answer:** Not under the normal class initialization process once the class has been successfully initialized; however, the static method still executes on every call.

**Question 14.** Which object's monitor does a `static synchronized` method lock?

**Answer:** The monitor of the `Class` object representing the class declaring the method; there is no `this` instance receiver.

**Question 15.** A public class has a private static method; can code in another package call `ClassName.privateMethod()`?

**Answer:** No. The method's access rules are still enforced separately.

**Question 16.** When should an instance method be used even though its current body does not read any field?

**Answer:** When the behavior belongs to the object contract or needs appropriate overriding/polymorphism; it is not mandatory to make it static just because the method does not currently use `this`.

## 29. Checklist When Writing or Reviewing a Static Method

- [ ] Does the method truly **not need an implicit instance receiver**?
- [ ] Can callers invoke it clearly using `DeclaringType.method(...)`?
- [ ] If the method needs to access instance state, does it accept an object/receive an explicit reference?
- [ ] Are you avoiding writing `this` or calling instance members by simple name from a static context?
- [ ] Is **static method invocation** distinguished from **constructors** and **instance methods**?
- [ ] Are you avoiding calling a static method through an instance variable, especially through a null variable or an expression with side effects?
- [ ] With inheritance, do you understand **hiding vs overriding** and avoid `@Override` for static methods?
- [ ] For interface static methods, are they called via the **declaring interface name**?
- [ ] Do overloads have validly distinct signatures, rather than differing only in return type/static?
- [ ] Does a generic static method declare its own type parameter if needed?
- [ ] If using `import static`, is the short name easy to understand and free of conflicts?
- [ ] If using a method reference, is the matching functional signature confirmed?
- [ ] If the method reads/writes static mutable state, is there a policy for test isolation and synchronization?
- [ ] If it is a static factory, does it validate inputs and clearly describe the returned object?
- [ ] Are class/method access permissions appropriate for the scope and module boundaries?
- [ ] Is the result of the static method used/verified against its contract rather than assuming shared state?
- [ ] Have you run `javac`/`java` with the right public class file and checked the actual stdout when possible?

---

**Remember:** **A static method belongs to the class level** and should be called in the form **`ClassName.method(args)`** or via the declaring interface name, without needing to create an object as a receiver. It **has no `this`**, yet can still operate on objects that are explicitly passed/referenced. A static call through an object may be valid, yet is easily misunderstood; **static hiding differs from instance overriding** and does not dynamically dispatch based on the runtime receiver. `static` does not mean called once, does not automatically provide thread safety, and does not turn all state into shared state. Choose static when **the behavior's semantics belong to the type or depend only on inputs**, and choose instance when the behavior needs receiver state or an object's polymorphic contract.
