# Method Selection by Compile-Time Type in Java

When a class has multiple **overloaded** methods with the same name, Java must determine **which method is called**. The fundamental point is: **overload selection is performed at compile time, based on the compile-time types of the expressions involved in the call**, along with the number of arguments, applicability, and the rules for selecting the most specific method.

This leads to a confusing situation: if a variable is declared with type `Animal` but references a `Dog` object, the call `describe(animal)` **does not automatically select** the overload with a `Dog` parameter. The compiler sees the expression `animal` as having the **static type `Animal`**.

Distinguish between two phases:

1. **Overload resolution — at compile time:** selecting the method signature based on the types of the receiver and arguments, access scope, and conversion rules.
2. **Dynamic dispatch — at runtime if the instance method is overridden:** once the selected signature is known, the JVM decides which **overriding implementation** runs based on the actual receiver object.

These two processes are related, but they do not replace each other. This article will clearly explain how overload selection works, type conversion precedence, ambiguous cases, and how to read Java 17 results accurately.

## 1. Overload Definition and a First Example

**Method overloading** is declaring multiple methods with the same name within the same type context, but with **different parameter type lists**. For example:

```java
static void show(int value) {
    System.out.println("int: " + value);
}

static void show(String value) {
    System.out.println("String: " + value);
}
```

The calls:

```java
show(10);     // Selects show(int)
show("10");   // Selects show(String)
```

What makes the signatures different can be:

- **Number of parameters:** `print()` and `print(String text)`.
- **Parameter types:** `print(int number)` and `print(String text)`.
- **Order of parameter types:** `combine(int number, String text)` and `combine(String text, int number)`.

Methods **cannot** be overloaded solely by parameter variable names or solely by return type:

```java
// INVALID if both are in the same class:
int calculate(int value) { return value; }
int calculate(int number) { return number * 2; }

// Also INVALID if both are in the same class:
int size(String text) { return text.length(); }
long size(String text) { return text.length(); }
```

The `INVALID` examples are used to illustrate compilation errors, not runnable programs. The parameter names `value`/`number` do not distinguish signatures; `int`/`long` in the return type position do not distinguish signatures either.

What matters for this article is **when valid overloads have been declared, which overload Java selects at the call site**.

## 2. What Is a Compile-Time Type (Static Type)?

The **static type** of an expression is the type that the compiler knows when analyzing the source code. It does not necessarily match the **actual runtime class** of the object to which the expression evaluates.

For example:

```java
class Animal { }
class Dog extends Animal { }

Animal pet = new Dog();
```

- `Animal` is the **declared type of the variable `pet`**, as well as the static type of the expression `pet`.
- `Dog` is the **actual class** of the object created by `new Dog()`.
- The static type of the expression `new Dog()` is `Dog`.
- The static type of the expression `(Dog) pet` is `Dog` after the cast, with the risk of a `ClassCastException` at runtime if the object is not actually compatible with `Dog`.

If we have:

```java
static void inspect(Animal value) {
    System.out.println("Animal");
}

static void inspect(Dog value) {
    System.out.println("Dog");
}
```

Then:

```java
inspect(pet);          // Selects inspect(Animal)
inspect(new Dog());    // Selects inspect(Dog)
inspect((Dog) pet);    // Selects inspect(Dog), if the cast is valid at runtime
```

**Core point:** Java does not look ahead to see that `pet` holds a `Dog` object in order to automatically select the `inspect(Dog)` overload. The selection must match the static type `Animal`, because at runtime, the variable `pet` could very well reference an object of another subclass.

## 3. Complete Program: Overload Selected by Static Type

Save to the file **`StaticTypeDemo.java`**:

```java
class Animal {
}

class Dog extends Animal {
}

class Cat extends Animal {
}

public class StaticTypeDemo {
    static void describe(Animal animal) {
        System.out.println("Overload: Animal");
    }

    static void describe(Dog dog) {
        System.out.println("Overload: Dog");
    }

    static void describe(Cat cat) {
        System.out.println("Overload: Cat");
    }

    public static void main(String[] args) {
        Animal pet = new Dog();
        Dog dog = new Dog();
        Cat cat = new Cat();

        describe(pet);
        describe(dog);
        describe(cat);
        describe(new Dog());
        describe((Dog) pet);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 StaticTypeDemo.java
java StaticTypeDemo
```

**Exact stdout:**

```text
Overload: Animal
Overload: Dog
Overload: Cat
Overload: Dog
Overload: Dog
```

Explanation of each call:

| Argument expression | Compile-time type | Runtime object class | Selected overload |
| --- | --- | --- | --- |
| `pet` | `Animal` | `Dog` | `describe(Animal)` |
| `dog` | `Dog` | `Dog` | `describe(Dog)` |
| `cat` | `Cat` | `Cat` | `describe(Cat)` |
| `new Dog()` | `Dog` | `Dog` | `describe(Dog)` |
| `(Dog) pet` | `Dog` | `Dog` | `describe(Dog)` |

In the program, the cast `(Dog) pet` works because `pet` currently holds a `Dog` object. You should not cast arbitrarily just to call an overload: for example, `(Dog) new Cat()` is detected as not convertible between two sibling classes in this situation; meanwhile, a cast from a parent-type variable to a subclass incompatible with the actual object can throw `ClassCastException`.

## 4. Overload Selection Process: Candidates, Applicability, Specificity

At an intuitive level, the selection process for a method call can be read as follows:

1. **Determine where to look up the method:** what type is the receiver, what is the method name, and which methods are inherited or accessible? Java also has specific rules for `super` calls, generics, method references, and interfaces.
2. **Consider the number and types of arguments:** to which overload's parameter types can the argument expressions be converted according to the applicability rules?
3. **Evaluate in phases:** prioritize methods applicable by **strict invocation**, then **loose invocation**, and finally **variable arity** if no method was applicable in an earlier phase.
4. **Select the most specific method:** in the first phase that has applicable candidates, Java compares them according to the language's `most specific` rule. If a single unique choice does not exist, the call may be reported as **ambiguous**.
5. **Check remaining rules:** access permissions, generic constraints, return type in context, and proper invocation compatibility with the selected method.

This is a practical guide; the formal algorithm has more details regarding generic types, lambda expressions, type inference, and methods with the same signature due to inheritance. Overload resolution cannot simply be viewed as comparing the "distance from the data type to the parameter type".

### Three Important Phases

| Phase | Approximate description | Example |
| --- | --- | --- |
| **1 — Strict invocation** | Uses conversions allowed in a strict context; no boxing/unboxing needed, no varargs expansion | `int` → `long` |
| **2 — Loose invocation** | If phase 1 has no candidates, additionally allows boxing/unboxing and specified conversions | `int` → `Integer`; `Integer` → `long` via unboxing then widening |
| **3 — Variable arity** | If the previous two phases have no candidates, considers varargs overloads with expanded elements | `f(int...)` called with `f(1, 2)` |

**A method declared with `int...` can be considered in the fixed-arity invocation phase** when an argument of type `int[]` is passed directly; the `...` in the declaration does not mean that all calls to it are only considered in phase 3.

## 5. Primitive Widening Is Considered Before Boxing and Varargs Expansion

One common misconception is that Java will choose the method whose type most closely matches the runtime value or automatically prefer wrapper types. In normal calls, **primitive widening** generally gets a chance in the strict phase before boxing is considered.

A runnable example, saved as **`PrimitiveOverloadDemo.java`**:

```java
public class PrimitiveOverloadDemo {
    static void select(long number) {
        System.out.println("long");
    }

    static void select(Integer number) {
        System.out.println("Integer");
    }

    static void select(int... numbers) {
        System.out.println("varargs " + numbers.length);
    }

    public static void main(String[] args) {
        select(5);
        select(Integer.valueOf(5));
        select((short) 5);
        select(1, 2);
        select(new int[]{3, 4, 5});
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 PrimitiveOverloadDemo.java
java PrimitiveOverloadDemo
```

Result:

```text
long
Integer
long
varargs 2
varargs 3
```

**Analysis:**

- `select(5)`: the literal `5` has type `int`. `select(long)` applies via **primitive widening `int → long`** in phase 1, ahead of `select(Integer)` which requires boxing in phase 2 and `select(int...)` which requires variable arity in phase 3.
- `select(Integer.valueOf(5))`: the expression already has type `Integer`; `select(Integer)` matches the exact type in phase 1, whereas `select(long)` requires unboxing `Integer → int` followed by widening `int → long` in phase 2.
- `select((short) 5)`: the expression has type `short` and can widen to `long` directly in phase 1.
- `select(1, 2)`: neither the `select(long)` nor the `select(Integer)` overload accepts two arguments; `select(int...)` is selected via varargs expansion.
- `select(new int[]{3, 4, 5})`: the argument is an `int[]` array, matching the array parameter of `select(int...)` via **fixed arity**, and inside the body there are three elements.

Distinguish between the *literal* type and the *variable* type: `Integer boxed = 5; select(boxed);` selects the `Integer` overload, whereas `int primitive = 5; select(primitive);` selects the `long` overload in this program.

### Conversions Cannot Always Be Combined Freely

For example:

```java
static void show(Long value) {
    System.out.println("Long");
}

// show(5); // Invalid if only show(Long) exists
```

Reason: `int` is not converted via the sequence **primitive widening `int → long` followed by boxing `long → Long`** in method invocation conversion that way. Java allows `int → Integer` via boxing, and `int → long` via widening, but does not automatically combine them into `int → Long`.

Conversely, an `Integer` argument can be **unboxed** to `int` and then widened to `long` when a method accepting `long` is considered in the appropriate phase.

## 6. Most Specific by Static Type

When multiple overloads are available in a phase, Java selects the **more specific** overload according to the rules of the language.

For example:

```java
static String tag(Object value) {
    return "Object";
}

static String tag(CharSequence value) {
    return "CharSequence";
}

static String tag(String value) {
    return "String";
}
```

The types have the relationships `String implements CharSequence` and `String extends Object`. If the above declarations are placed in a suitable class:

```java
System.out.println(tag("Java"));                  // String
System.out.println(tag((CharSequence) "Java"));  // CharSequence
System.out.println(tag((Object) "Java"));        // Object
```

When the argument is `"Java"`, its static type is `String`, so `tag(String)` is the most specific among the applicable overloads. With `(CharSequence) "Java"`, the static type of the expression after the cast is `CharSequence`; the `tag(String)` overload does not automatically apply just because the actual object is a `String`.

**Important point:** selecting the most specific method is performed **within the set of applicable candidates in the current phase**. The phase order cannot be bypassed just to prefer a boxing overload whose type name looks "closer" to the argument.

### Standalone Program Example

Save as **`MostSpecificDemo.java`**:

```java
public class MostSpecificDemo {
    static void tag(Object value) {
        System.out.println("Object");
    }

    static void tag(CharSequence value) {
        System.out.println("CharSequence");
    }

    static void tag(String value) {
        System.out.println("String");
    }

    public static void main(String[] args) {
        String text = "Java";
        CharSequence sequence = text;
        Object object = text;

        tag(text);
        tag(sequence);
        tag(object);
        tag((Object) text);
        tag((CharSequence) text);
    }
}
```

Commands:

```bash
javac -encoding UTF-8 MostSpecificDemo.java
java MostSpecificDemo
```

Stdout:

```text
String
CharSequence
Object
Object
CharSequence
```

All three variables `text`, `sequence`, and `object` can point to the **same `String` object**, yet the overload selection still differs because their **static types differ**.

## 7. When Is a Call Ambiguous?

A call is **ambiguous** when multiple applicable overloads exist and the rule for selecting the most specific method **cannot uniquely determine a single method**.

### 7.1. The `null` Literal and Two Reference Types With No Subtype Relationship

```java
static void display(String text) {
    System.out.println("String");
}

static void display(Integer number) {
    System.out.println("Integer");
}

// display(null); // INVALID: ambiguous
```

The `null` literal can match both `String` and `Integer`, but `String` and `Integer` do not have a subtype relationship with each other. Neither overload is more specific in this example.

You can clarify the intent:

```java
display((String) null);  // Selects display(String)
display((Integer) null); // Selects display(Integer)
```

**Note the distinction:** if the overloads are `display(Object)` and `display(String)`, then `display(null)` is **not ambiguous**: `String` is more specific than `Object`.

### 7.2. Ambiguous Arguments When There Are Multiple Varargs Overloads

For example:

```java
static void send(String... messages) {
    System.out.println("String varargs");
}

static void send(Integer... numbers) {
    System.out.println("Integer varargs");
}

// send();     // INVALID: ambiguous
// send(null); // INVALID: ambiguous
```

In `send()`, there is no value to distinguish `String[]` from `Integer[]` in varargs applicability. In `send(null)`, both overloads can receive a `null` array reference. Clearer ways to call them:

```java
send(new String[0]);
send(new Integer[0]);
send((String[]) null);
```

The snippets above are **illustrative code**, assumed to reside inside a class containing the corresponding declarations; they do not run standalone.

### 7.3. Ambiguity Is Not Resolved by Inspecting Actual Data

If there are two overloads `parse(String)` and `parse(Integer)`, Java **does not read the contents of `"123"` and automatically infer** that the integer-handling version is needed. The argument `"123"` has type `String`; to use `Integer`, the caller must create/convert it into an `Integer` value or use the corresponding API.

**When a call is ambiguous**, prioritize designing clear API names/types. Casting can be useful at a specific call site, but it should not be used to mask an overly confusing overload design.

## 8. Overload Selection Differs From Polymorphic Override Execution

This is the core difference between **overloading** and **overriding**:

| Aspect | Overloading | Overriding |
| --- | --- | --- |
| What varies | Parameter list of methods with the same name | Implementation of an instance method with a matching signature |
| Primary selection basis | Static types, number of arguments, and Java rules at compile time | Actual class of the receiver object at runtime |
| When selected? | Compile time | Runtime for overridden instance methods |
| Is a different return type enough to create an overload? | No | Must obey return-type substitutability when overriding |
| `static` methods | Can be overloaded; static methods are selected by static rules | Not dynamically overridden; may undergo **hiding** in a subclass |
| `private` methods | Can be overloaded within accessible scope | Not overridden in the normal polymorphic sense |

### 8.1. A Program Illustrating Both Processes

Save as **`OverloadOverrideDemo.java`**:

```java
class Animal {
}

class Dog extends Animal {
}

class Handler {
    String handle(Animal animal) {
        return "Handler: Animal";
    }

    String handle(Dog dog) {
        return "Handler: Dog";
    }
}

class SpecialHandler extends Handler {
    @Override
    String handle(Animal animal) {
        return "SpecialHandler: Animal";
    }

    @Override
    String handle(Dog dog) {
        return "SpecialHandler: Dog";
    }
}

public class OverloadOverrideDemo {
    public static void main(String[] args) {
        Handler handler = new SpecialHandler();
        Animal animal = new Dog();
        Dog dog = new Dog();

        System.out.println(handler.handle(animal));
        System.out.println(handler.handle(dog));
        System.out.println(handler.handle((Dog) animal));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 OverloadOverrideDemo.java
java OverloadOverrideDemo
```

**Stdout:**

```text
SpecialHandler: Animal
SpecialHandler: Dog
SpecialHandler: Dog
```

Line-by-line analysis:

1. `handler.handle(animal)`: the compiler sees that the receiver has static type `Handler` and the argument has static type `Animal`, so it selects the **signature `handle(Animal)`**. At runtime, the receiver is a `SpecialHandler` object, so the overriding implementation **`SpecialHandler.handle(Animal)`** is executed.
2. `handler.handle(dog)`: the compiler sees an argument of static type `Dog`, so it selects the signature **`handle(Dog)`**. Runtime executes the overriding version `SpecialHandler.handle(Dog)`.
3. `handler.handle((Dog) animal)`: the cast gives the argument expression the static type `Dog` and the runtime cast succeeds, so `handle(Dog)` is selected and the corresponding overriding version runs.

**Do not interpret** the first line as "runtime selects the `handle(Animal)` overload because the real object is `SpecialHandler`." The selection of `Animal` already happened at **compile time**; runtime only determines the overriding implementation of the **selected signature**.

### 8.2. Static Methods Do Not Have Dynamic Dispatch

Consider the illustrative declarations:

```java
class Base {
    static String label() {
        return "Base";
    }
}

class Derived extends Base {
    static String label() {
        return "Derived";
    }
}
```

With:

```java
Base value = new Derived();
System.out.println(value.label());     // Base
System.out.println(Derived.label());   // Derived
```

`Derived.label` **hides** `Base.label` rather than dynamically overriding it. Even though `value` references a `Derived` object, `value.label()` is bound according to the static type `Base`. You should call static methods via the **class name** (`Base.label()`) to avoid confusion.

The examples in this section are illustrative snippets; they are not complete programs with `main`. A real-world application should avoid calling static methods through an object variable.

## 9. A Parent-Type Receiver Can Limit the Set of Visible Overloads

The static type of the **receiver** also affects which methods the compiler can consider.

For example:

```java
class ParentPrinter {
    void print(Object value) {
        System.out.println("Parent Object");
    }
}

class ChildPrinter extends ParentPrinter {
    void print(String value) {
        System.out.println("Child String");
    }
}
```

In the calling code:

```java
ParentPrinter printer = new ChildPrinter();
printer.print("Hello");                // Parent Object
((ChildPrinter) printer).print("Hello"); // Child String
```

Explanation:

- The variable `printer` has static type `ParentPrinter`. For the expression `printer.print("Hello")`, the `print(String)` overload declared specifically in `ChildPrinter` **is not in the set of methods accessible through the `ParentPrinter` type**. The compiler selects `print(Object)`.
- `ChildPrinter` does not override `print(Object)` in this example. Therefore, runtime still executes `ParentPrinter.print(Object)`.
- After casting the receiver to `ChildPrinter`, the compiler sees both the inherited `print(Object)` and the subclass's `print(String)`, and selects the more specific `print(String)` for the argument `"Hello"`.

**Not only the arguments, the static type of the receiver also matters.** A subclass adding a new overload does not cause every variable of the parent class type to automatically recognize that new overload.

## 10. Overload Selection With Specific Primitive Types

Common cases can be understood through primitive conversion relationships:

```text
byte  -> short -> int -> long -> float -> double
char  ------------> int -> long -> float -> double
```

This simplified diagram shows some **primitive widening** paths, not the complete diagram of all Java conversions. For example, `char` does not automatically convert to `short`, and `boolean` does not participate in numeric conversions.

If we have:

```java
static void measure(long n) {
    System.out.println("long");
}

static void measure(double n) {
    System.out.println("double");
}
```

Then `measure(1)` selects `measure(long)` because `long` is more specific than `double` according to the relevant rule within the applicable overload group.

Remember the types of literals:

- `1` has type `int`.
- `1L` has type `long`.
- `1.0` has type `double`.
- `1.0f` has type `float`.
- `'A'` has type `char`.

Example of selection with `int`/`long`:

```java
static void test(int number) {
    System.out.println("int");
}

static void test(long number) {
    System.out.println("long");
}

// test(1)    -> int
// test(1L)   -> long
// test('A')  -> int (char widening to int)
```

An overload with a `long` parameter cannot automatically accept the string `"1"`: converting a `String` to a numeric value requires a conversion API or explicit logic.

### Conditional Expressions and Expression Types

A static type can be inferred from **the entire expression**, not from the value of only the branch that actually executes. For example, given `boolean flag`, `Animal a`, and `Dog d`:

```java
// inspect(flag ? d : a);
```

If `inspect` is overloaded for `Animal` and `Dog`, the compiler determines the type of the conditional expression `flag ? d : a` according to the conditional operator's typing rules for reference operands. When the expression's type is `Animal`, the `inspect(Animal)` overload is selected **even if at runtime the `flag` causes the expression to return a reference to a Dog**.

An overload cannot be selected merely by observing which branch will be executed in a single run.

## 11. Overloading, the `null` Value, and Variable Declared Types

Compare two cases:

**Case 1 — parent/child relationship exists:**

```java
static void show(Object o) { System.out.println("Object"); }
static void show(String s) { System.out.println("String"); }

// show(null) -> String
```

`String` is more specific than `Object`, so the `null` literal selects the `String` overload.

**Case 2 — no applicable parent/child relationship:**

```java
static void show(String s) { System.out.println("String"); }
static void show(Integer i) { System.out.println("Integer"); }

// show(null) -> INVALID: ambiguous
```

Within the same class, do not put these two cases with colliding names/signatures in the same file when testing. The two sets of declarations above are **two separate examples**.

If there is a variable `Object item = "abc";`, then `show(item)` under the `show(Object)`/`show(String)` overloads will select **`show(Object)`**. If a specialized overload is needed, you can check and convert the type intentionally:

```java
if (item instanceof String text) {
    show(text);
}
```

In Java 17, pattern matching for `instanceof` introduces the variable `text` with static type `String` inside the matching branch. Then the `show(String)` overload is selected. This approach is useful when you genuinely need to handle different subtypes; avoid casting without checking compatibility first.

## 12. Return Type Does Not Control Overload Selection

Suppose there are two valid overloads:

```java
static Object load(Object key) {
    return "from Object";
}

static String load(String key) {
    return "from String";
}
```

With:

```java
Object key = "id";
Object first = load(key);             // Selects load(Object)
String second = load((String) key);  // Selects load(String)
```

Which overload is chosen is based on **the type of the argument expression**. Do not assume that because the left-hand side of the assignment is `String`, the compiler will pick the overload returning `String`, ignoring parameter compatibility.

The following snippet is **invalid**:

```java
String text = load(key); // key has type Object: selects load(Object), returns Object
```

It cannot assign `Object` directly to `String` without an appropriate conversion.

**Advanced note:** Java has *poly expressions* (for example, certain lambda expressions, method references, and generic method invocations) in which the target type context can participate in type inference. That **does not change the general rule** that you cannot define two methods differing only by return type or arbitrarily choose an overload independently of signatures and applicability rules. Use examples with ordinary expressions to build a foundation before learning generic type inference.

## 13. Generics and Type Erasure: Two Related Situations

### 13.1. Generic Parameter Types Can Cause Signature Collisions After Erasure

Invalid example:

```java
// INVALID when declared in the same class:
static void process(java.util.List<String> items) { }

static void process(java.util.List<Integer> items) { }
```

Due to **type erasure**, both have the same parameter form `List` at the erased signature level; Java does not allow two such declarations to coexist in a class.

You can rename the methods or choose an API design that expresses the requirement clearly:

```java
static void processNames(java.util.List<String> names) { }

static void processNumbers(java.util.List<Integer> numbers) { }
```

Having different generic type arguments is **not always** sufficient to create a valid overload.

### 13.2. Overloading With Generics Can Depend on Type Inference

```java
static <T extends Number> String describe(T number) {
    return "Number generic";
}

static String describe(String text) {
    return "String";
}
```

In `describe(5)`, the `int` value can be boxed to `Integer` and matches the bound `T extends Number`, so the generic overload is applicable; `describe("hello")` selects the `String` overload because `String` does not satisfy `T extends Number`.

When lambdas or method references are involved, overload selection can be more complex because the expression's compatibility with a **functional interface** is part of compile-time analysis. Do not try to guess solely from the runtime type name of a lambda; you need to consider the target type and the formal overload rules.

### 13.3. Lambdas Can Make a Call Ambiguous

Illustrative example, **does not run standalone**:

```java
static void use(java.util.function.Function<String, String> f) { }

static void use(java.util.function.Consumer<String> c) { }

// use(s -> s.trim()); // May cause an unexpected selection;
// an expression-bodied lambda must be evaluated for both value-compatibility and void-compatibility.
```

To express the intent clearly, pass the lambda expression with a specific functional interface type or choose a different API name. For the foundational module, you should master cases where arguments are literals, variables, casts, and varargs before diving deeply into overload resolution for lambdas.

## 14. Common Conversions: Result Prediction Table

The following table presents several **independent** cases; each row assumes **only the overloads listed in that row exist**, without mixing them all into one class.

| Available overloads | Call | Result |
| --- | --- | --- |
| `f(int)`, `f(long)` | `f(1)` | `f(int)` — exact match |
| `f(int)`, `f(long)` | `f(1L)` | `f(long)` |
| `f(long)`, `f(Integer)` | `f(1)` | `f(long)` — widening in the strict phase |
| `f(Integer)`, `f(int...)` | `f(1)` | `f(Integer)` — boxing in the fixed-arity phase before variable arity |
| `f(int)`, `f(int...)` | `f(1)` | `f(int)` — fixed arity |
| `f(int)`, `f(int...)` | `f(1, 2)` | `f(int...)` |
| `f(Object)`, `f(String)` | `f("Hi")` | `f(String)` |
| `f(Object)`, `f(String)` | `f((Object) "Hi")` | `f(Object)` |
| `f(Object)`, `f(String)` | `f(null)` | `f(String)` |
| `f(String)`, `f(Integer)` | `f(null)` | Error: **ambiguous** |
| `f(String...)`, `f(Integer...)` | `f()` | Error: **ambiguous** |
| `f(long)` | `f(Integer.valueOf(2))` | `f(long)` via unboxing then widening |
| `f(Long)` | `f(2)` | Error: no suitable `int → Long` conversion |

The table illustrates how common situations are handled, but it **does not replace** the full algorithm of the Java Language Specification, especially when combining generics, inheritance, lambdas, or multiple levels of type conversions.

## 15. Errors and How to Diagnose Them

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| "Why doesn't `Animal a = new Dog(); f(a)` select `f(Dog)`?" | Overload resolution uses the static type `Animal` | Check the declared type of `a`; only cast/type-check when genuinely needed |
| "Why is the runtime object a subclass, yet the code prints from the parent class?" | The receiver only sees overloads according to its static type; the subclass may only have added an overload | Check the selected signature and see if that exact signature is overridden |
| "Why does `f(1)` select `f(long)` instead of `f(Integer)`?" | Primitive widening is considered in a phase prior to boxing | Identify the type of the literal `1` and the phase order |
| "Why does `f(1)` select `f(Integer)` instead of `f(int...)`?" | Fixed-arity boxing is considered before variable arity | View `...` as an array parameter and identify the invocation phase |
| "Why does `f(null)` report ambiguous?" | Two reference overloads have no most-specific relationship | Check the parameter types; use a different API name or cast intentionally |
| "Two overloads have different parameter names, yet the compiler reports a duplicate?" | Signatures do not include parameter names | Change the actual count/order/types of parameters |
| "Two overloads have different return types, yet the compiler reports a duplicate?" | Return type is not a factor that distinguishes overloads | Design different signatures/method names |
| "`List<String>` and `List<Integer>` cannot be overloaded?" | Erasure causes a signature conflict | Rename the API or add valid distinguishing parameter types |
| "Casting to call a specialized overload throws `ClassCastException`?" | A cast is only valid at runtime if the object is compatible | Use `instanceof` and validate the data |
| "Calling `f(null)` on `String...` treats it as a null array?" | The `null` expression can match `String[]` in fixed arity | Explicitly write `(String[]) null` or `(String) null` |
| "Changing a local variable's type while keeping the same object changes the call result?" | The argument's static type has changed | This is the expected behavior of overload resolution |
| "The right signature was selected, yet runtime prints from the subclass?" | The instance method is overridden in the actual receiver class | Distinguish the signature selection step from the dynamic dispatch step |

To trace a complex call, you should follow concrete steps: **record the static type of the receiver**, **record the static type of each argument**, **list the visible and accessible overloads**, **evaluate the phases**, and then **determine whether dynamic overriding applies**. This habit helps avoid reasoning erroneously based on runtime data.

## 16. Output Prediction Exercises

### Exercise 1 — Static Type of a Variable

Given two overloads:

```java
static void print(Object value) {
    System.out.println("Object");
}

static void print(String value) {
    System.out.println("String");
}
```

And the calling code:

```java
Object a = "Xin chào";
String b = "Xin chào";
print(a);
print(b);
print((Object) b);
```

**Answer:**

```text
Object
String
Object
```

All three arguments can represent a string object, yet their static types are `Object`, `String`, and `Object`, respectively. Consequently, different overloads are selected.

### Exercise 2 — Widening vs. Boxing

Given:

```java
static void process(long value) {
    System.out.println("long");
}

static void process(Integer value) {
    System.out.println("Integer");
}
```

And:

```java
int primitive = 3;
Integer boxed = 3;
process(primitive);
process(boxed);
```

**Answer:**

```text
long
Integer
```

`primitive` has type `int`, which widens to `long` right in the strict phase. `boxed` has type `Integer`, so it matches the `Integer` overload.

### Exercise 3 — Distinguishing Overloading and Overriding

Suppose there are classes `Base` and `Derived`:

```java
class Base {
    void run(Object value) {
        System.out.println("Base Object");
    }
}

class Derived extends Base {
    @Override
    void run(Object value) {
        System.out.println("Derived Object");
    }

    void run(String value) {
        System.out.println("Derived String");
    }
}
```

Calling code:

```java
Base receiver = new Derived();
receiver.run("A");
((Derived) receiver).run("A");
```

**Answer:**

```text
Derived Object
Derived String
```

For `receiver.run("A")`, the static type of `receiver` only has `run(Object)`, so that signature is selected; runtime runs `Derived`'s override. When the receiver is cast to `Derived`, the `run(String)` overload can be considered and is more specific.

### Exercise 4 — Is `null` Ambiguous?

Given:

```java
static void check(Object value) { }
static void check(String value) { }
```

`check(null)` is **valid** and selects `check(String)` because `String` is more specific than `Object`.

If the `check(Object)` overload is replaced by `check(Integer)`, `check(null)` will be **ambiguous** because `String` and `Integer` do not have a suitable subtype relationship.

### Exercise 5 — Overloading and Varargs

Given:

```java
static void total(int value) {
    System.out.println("one");
}

static void total(int... values) {
    System.out.println("many: " + values.length);
}
```

The calls:

```java
total(1);
total();
total(1, 2);
total(new int[]{1, 2, 3});
```

**Answer:**

```text
one
many: 0
many: 2
many: 3
```

`total(1)` prioritizes the fixed-arity `int` overload; `total()` and `total(1, 2)` require varargs expansion; `total(new int[]{1, 2, 3})` passes an array of three elements to the method declared with `int...`.

## 17. A Comprehensive Review Program

Save all the code below to the file **`OverloadReview.java`**:

```java
class BaseItem {
}

class SpecialItem extends BaseItem {
}

class Printer {
    String print(BaseItem item) {
        return "base item";
    }

    String print(SpecialItem item) {
        return "special item";
    }
}

class FancyPrinter extends Printer {
    @Override
    String print(BaseItem item) {
        return "fancy base item";
    }
}

public class OverloadReview {
    static String number(long value) {
        return "long";
    }

    static String number(Integer value) {
        return "Integer";
    }

    static String number(int... values) {
        return "varargs(" + values.length + ")";
    }

    public static void main(String[] args) {
        Printer printer = new FancyPrinter();

        BaseItem base = new SpecialItem();
        SpecialItem special = new SpecialItem();

        System.out.println(printer.print(base));
        System.out.println(printer.print(special));
        System.out.println(printer.print((SpecialItem) base));

        int primitive = 3;
        Integer boxed = 3;
        System.out.println(number(primitive));
        System.out.println(number(boxed));
        System.out.println(number(1, 2));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 OverloadReview.java
java OverloadReview
```

Result:

```text
fancy base item
special item
special item
long
Integer
varargs(2)
```

Explanation:

- `Printer printer = new FancyPrinter()` keeps the static type of the receiver as `Printer`, while the runtime receiver is `FancyPrinter`.
- `printer.print(base)` selects the signature `print(BaseItem)` because `base` has static type `BaseItem`; runtime runs `FancyPrinter`'s override → `fancy base item`.
- `printer.print(special)` selects `print(SpecialItem)` because of the argument's static type `SpecialItem`. Since `FancyPrinter` does not override this signature, the implementation inherited from `Printer` runs → `special item`.
- The cast `(SpecialItem) base` is valid at runtime in this example, causing the compiler to select `print(SpecialItem)`.
- `number(primitive)` selects `number(long)` via widening in the strict phase.
- `number(boxed)` selects the `number(Integer)` overload with the exact static type.
- `number(1, 2)` requires a variable-arity call, so it selects `number(int...)`.

Focus on **the signature selected at compile time**, and only then look at whether **the overriding implementation** is determined at runtime. These are two independent steps sufficient to explain the entire output in the example.

## Checklist When Analyzing Method Selection

1. **Identify declarations with the same name** and check whether they actually have different signatures.
2. **Note the static type of the receiver:** a parent-type variable may not see an overload declared only in a subclass.
3. **Note the static type of each argument expression:** literals, variables, casts, call results, and conditional expressions can carry different types.
4. **Consider accessibility and applicability** by parameter count/types; do not use the runtime actual type of an object to guess the overload.
5. **Evaluate by phases:** strict first, loose with boxing/unboxing next, variable arity last.
6. **If there are multiple candidates in the same phase, consider most specific**; recognize ambiguous errors for types with no unique choice.
7. **Do not use return type as an arbitrary criterion** to distinguish overloads; do not overload solely by parameter names or return type.
8. **Only after determining the signature, consider dynamic overriding** if it is an overridable instance method. For static methods, there is no dynamic dispatch.
9. **Check special corner cases:** `null`, varargs receiving an array directly, type erasure, casts, and generic inference.
10. **When designing APIs**, avoid multiple closely related overloads that make `null`, lambda, or integer calls ambiguous; method names with clear intent are usually easier to maintain.

Java does not select an overload by "looking at what kind of object it is at runtime." **Compile-time types and applicability rules** determine the signature; **dynamic dispatch** (if any) only determines the implementation corresponding to that signature.
