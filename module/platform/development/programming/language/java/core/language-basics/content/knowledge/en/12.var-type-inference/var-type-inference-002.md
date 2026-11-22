# `var` Preserves Static Type Checking in Java 17+

## 1. Goal: Fewer Characters, Same Type Safety

In Java, `var` enables **local-variable type inference** from the initializer expression. This feature was introduced in Java 10 and continues to be supported in Java 17+.

~~~java
var count = 10;        // Compiler infers int
var title = "Java";    // Compiler infers String
var price = 12.5;      // Compiler infers double

System.out.println(count + 1);  // 11
System.out.println(title);      // Java
System.out.println(price);      // 12.5
~~~

The core point: **`var` does not turn Java into a dynamically typed language**. The variable's type is determined **at compile time**, and is then checked by the compiler in every subsequent assignment and method call.

~~~java
var count = 10;
count = 20;         // Valid: int -> int
// count = "twenty"; // Compile error: String cannot be converted to int
~~~

You can think of `var count = 10;` as having the same effect in terms of type and post-inference behavior as `int count = 10;`, **not** as a variable holding “any value”.

### What You Should Achieve After This Lesson

- Understand that `var` infers a static type and **does not change type upon reassignment**.
- Analyze the inferred type from literals, methods, constructors, and generics.
- Predict compile errors caused by mismatched-type assignments, missing initializers, or missing target types.
- Use `var` in the right places without making code hard to read.

## 2. The Static Type Is Locked Once from the Initializer

With `var name = expression;`, the compiler determines the type of `expression` at the time of declaration. Subsequent assignments must match the inferred type:

~~~java
var number = 7;              // int
number = 9;                  // Valid.
// number = 9L;              // Error: long does not automatically narrow to int.
var label = "Java";           // String
// label = 42;                // Error: int cannot be assigned to String.
~~~

Numeric width is determined by the literal or operation in the initializer, not by values you might want to assign later. The lesson “Types Inferred from Literals and Numeric Operations” analyzes numeric promotion and overflow separately.

## 3. Why Is This Still Static Typing?

The compiler still checks Java's normal rules:

1. **Assignment compatibility:** the type of the right-hand expression must be compatible with the inferred type.
2. **Method/field access:** only members valid according to the **static type** can be called.
3. **Operators:** operators are checked based on operand types.
4. **Generic types:** `List<String>` differs from `List<Integer>`; the compiler enforces element type checking.
5. **Overload resolution:** selects the method based on the static types of arguments at compile time.

~~~java
var text = "Java"; // String
System.out.println(text.length()); // 4
// System.out.println(text.nonExistingMethod()); // Compile error
// text = 123; // Compile error
~~~

You will see the exact same level of type checking if you write:

~~~java
String text = "Java";
~~~

**`var` is not `Object`**. With `var text = "Java";`, the variable has type `String`, so `text.length()` compiles; with `Object text = "Java";`, calling `text.length()` is invalid without a cast because `Object` does not declare `length()`.

**Nor is `var` JavaScript's `var`**: the two languages use the same sequence of characters for different mechanisms.

## 4. Two Examples with the Same `var` Keyword, Inferring Two Different Types

~~~java
var primitive = 42;                  // int
var wrapped = Integer.valueOf(42);  // Integer

System.out.println(primitive + 1); // 43
System.out.println(wrapped + 1);   // 43: unboxing then adding
~~~

In the `wrapped` example, the compiler knows the variable has type `Integer`; in the `primitive` example, the compiler knows the variable has type `int`.

This affects the ability to hold `null`:

~~~java
var count = 5;             // int
// count = null;            // Compile error: primitive int cannot hold null

var optionalCount = Integer.valueOf(5); // Integer
optionalCount = null;          // Compiles, because Integer is a reference type
~~~

However, when auto-unboxing a null wrapper, you still get a `NullPointerException` just as with a normal `Integer` declaration:

~~~java
if (optionalCount != null) {
    int safe = optionalCount;
    System.out.println(safe);
}
~~~

**Type inference does not automatically add runtime null checks.** `var` only reduces type-name repetition at the declaration site; it does not change the nullable contract of the inferred type.

## 5. Typical Compile Errors Proving the Type Remains Fixed

The commented lines below are **intentional error examples** and are not included in the runnable program later:

~~~java
var score = 10;
// score = "ten";             // String cannot be assigned to int

var city = "Hà Nội";
// city = 42;                 // int cannot be assigned to String

var names = new java.util.ArrayList<String>();
names.add("Lan");
// names.add(100);            // int does not match List<String>

var answer = 2 + 3;         // int
// answer.notARealMethod();   // int has no such method
~~~

There is no “second assignment that makes the variable change type”. The compiler **does not re-infer** the type of `score` or `city` in later statements.

An exception that is easy to misunderstand regarding values, though **not a type change**:

~~~java
var number = 3;   // int
number = (int) 3.9; // Valid: cast double -> int, value becomes 3
~~~

Here `number`'s type is still **int**. Using a cast can cause data loss; business correctness still needs to be checked separately.

## 6. Static Type Constraints Still Apply When Using `var`

The compiler can only infer when the initializer **has a valid type**. You cannot write `var item;`, `var item = null;`, `var values = {1, 2};`, or directly assign a lambda without a target type. You can use an explicit type or create an expression with a complete type:

~~~java
String nullable = null;
var typedNull = (String) null; // Type String even though value is null
var values = new int[] {1, 2}; // Type int[]
java.util.function.IntUnaryOperator f = x -> x + 1;
var f2 = (java.util.function.IntUnaryOperator) (x -> x + 1);
~~~

In both `f` and `f2`, the **functional interface** supplies the target type for the lambda; `var` does not invent a functional interface type on its own. The rules for inference from `null`, arrays, and allowed positions for `var` have dedicated lessons in this chapter; here they serve as **evidence that static typing is not bypassed**.

### Generic Types and Abstractions Are Still Preserved

~~~java
var strings = new java.util.ArrayList<String>();
strings.add("An");
// strings.add(5); // Compile error: String required

var bag = new java.util.ArrayList<>(); // ArrayList<Object>
bag.add("An");
bag.add(5);

java.util.List<String> names = new java.util.ArrayList<>();
~~~

Without a `String` target type for `bag`'s empty diamond, the variable infers `ArrayList<Object>`, and `add(5)` is valid (boxing to `Integer`). Place `List<String>` on the left-hand side when the goal is to use the **interface's API**, rather than letting `var` infer the concrete implementation class. After declaration, generics and the set of valid methods are still checked by the compiler; `var` **does not** bypass `UnsupportedOperationException` if an unsupported operation is called on a list from `List.of` at runtime.

## 7. Overloads Are Chosen by Static Type, Not Runtime Contents

Suppose we have two overloads:

~~~java
static void describe(Object object) {
    System.out.println("Object");
}

static void describe(String text) {
    System.out.println("String");
}
~~~

In `main`:

~~~java
var text = "Java";           // Type String
var object = (Object) "Java"; // Type Object

describe(text);   // String
describe(object); // Object
~~~

Both variables **can refer to the same String object**, but the overload is selected **at compile time** based on the expression's static type:

- `text` of type `String` → selects `describe(String)`.
- `object` of type `Object` → selects `describe(Object)`.

**`var` does not support switching overloads at runtime.** This is a clear sign that type inference in Java still belongs to the static typing model.



## 8. Standalone Runnable Java 17 Program

Create a file named **`VarStaticTypingDemo.java`**:

~~~java
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import java.util.function.BinaryOperator;
import java.util.function.IntUnaryOperator;

public final class VarStaticTypingDemo {
    private VarStaticTypingDemo() {}

    record Person(String name, int age) {}

    static int sum(int a, int b) {
        return a + b;
    }

    static void describe(Object object) {
        System.out.println("overload=Object");
    }

    static void describe(String text) {
        System.out.println("overload=String");
    }

    public static void main(String[] args) throws Exception {
        var number = 10;         // int
        number = 12;
        var longNumber = 10L;    // long
        var ratio = 2.5;         // double
        var enabled = true;      // boolean
        var title = "Java";      // String

        System.out.println("int=" + number);
        System.out.println("long=" + longNumber);
        System.out.println("double=" + ratio);
        System.out.println("boolean=" + enabled);
        System.out.println("text length=" + title.length());

        var answer = sum(2, 3); // int from return type
        System.out.println("sum=" + answer);

        var names = new ArrayList<String>();
        names.add("Lan");
        names.add("An");
        System.out.println("names=" + names);
        System.out.println("first name=" + names.get(0));

        var words = List.of("A", "B");
        for (var word : words) {
            System.out.println("word=" + word);
        }

        var bag = new ArrayList<>();
        bag.add("text");
        bag.add(123);
        System.out.println("Object bag=" + bag);

        var flags = new boolean[] {true, false};
        System.out.println("flags length=" + flags.length);

        var person = new Person("Mai", 20);
        System.out.println("person=" + person.name() + ":" + person.age());

        var asString = "Java";
        var asObject = (Object) "Java";
        describe(asString);
        describe(asObject);

        var optional = (String) null;
        System.out.println("typed null=" + (optional == null));

        var increment = (IntUnaryOperator) (x -> x + 1);
        System.out.println("lambda=" + increment.applyAsInt(4));

        BinaryOperator<String> merge =
                (var left, var right) -> left + "-" + right;
        System.out.println("lambda parameters=" + merge.apply("A", "B"));

        for (var i = 0; i < 2; i++) {
            System.out.println("for i=" + i);
        }

        try (var reader = new StringReader("X")) {
            System.out.println("resource char=" + (char) reader.read());
        }

        var original = new ArrayList<String>();
        var alias = original;
        alias.add("shared");
        System.out.println("same reference=" + (original == alias));
        System.out.println("original=" + original);
    }
}
~~~

**Compile and run with JDK 17+**. Open a terminal in the directory containing the file.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 VarStaticTypingDemo.java
java -cp . VarStaticTypingDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\VarStaticTypingDemo.java
java -cp . VarStaticTypingDemo
~~~

**Exact expected output:**

~~~text
int=12
long=10
double=2.5
boolean=true
text length=4
sum=5
names=[Lan, An]
first name=Lan
word=A
word=B
Object bag=[text, 123]
flags length=2
person=Mai:20
overload=String
overload=Object
typed null=true
lambda=5
lambda parameters=A-B
for i=0
for i=1
resource char=X
same reference=true
original=[shared]
~~~

**Clarifying easily confused results:**

- `number` infers type `int`; assigning `12` is allowed, but assigning a String is not.
- `answer` infers `int` from the `sum` method.
- `names` has type `ArrayList<String>`, so it only allows adding String values per generics.
- `bag` is created with an empty diamond and no target type outside `var`, so it infers `ArrayList<Object>`; adding both String and Integer is valid.
- `asString` and `asObject` lead to different overloads **based on static type**, not because the String object changed.
- `optional` still has type `String` even though its current value is null.
- `increment` gets its target type via the `IntUnaryOperator` cast; `merge` has target type `BinaryOperator<String>`.
- `for` and `try-with-resources` use `var` in valid positions.
- `alias = original` keeps the same reference and does not copy the ArrayList.

There are **no** intentional compile-error lines in this program; the invalid code examples in earlier sections were commented out or shown separately. The example uses standard JDK 17 APIs and requires no external libraries.



## 9. Exercises and Solutions

### Exercise A — Literal Inference

~~~java
var x = 1;
var y = 1L;
var z = 1.0f;
~~~

**Answer:** `x` is `int`, `y` is `long`, `z` is `float`.

### Exercise B — Reassignment with Wrong Type

~~~java
var label = "A";
label = "B";
// label = 10;
~~~

**Answer:** assigning `"B"` is valid; assigning `10` causes a compile error because `label` has its type locked to `String`.

### Exercise C — Generics

~~~java
var scores = new java.util.ArrayList<Integer>();
scores.add(1);
// scores.add("two");
~~~

**Answer:** `scores` has type `ArrayList<Integer>`, so adding `"two"` is invalid. `var` does not skip generic type checking.

### Exercise D — Overloads

~~~java
static void show(Object x) { System.out.println("Object"); }
static void show(String x) { System.out.println("String"); }

// In main:
var a = "Hi";
var b = (Object) "Hi";
show(a);
show(b);
~~~

**Answer:**

~~~text
String
Object
~~~

### Exercise E — null

~~~java
// var a = null;
String b = null;
var c = (String) null;
~~~

**Answer:** the declaration of `a` is invalid because the compiler cannot infer a type from the null literal. `b` and `c` are valid; `c` has type `String` even though it holds null.

### Exercise F — Choosing `var` or an Explicit Type?

You want to express the intent to work through the `List<String>` interface rather than `ArrayList`-specific operations:

~~~java
var names = new java.util.ArrayList<String>();
~~~

**Answer:** you can write:

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
~~~

This clearly expresses the **contract depending on `List`**. `var` is still type-correct; the issue here is readability and the desired abstraction level, not weaker type checking in Java.

## 10. Checklist and Conclusion

- [ ] With `var`, mismatched-type assignments are still rejected at compile time.
- [ ] Method access, generics, and overloads still rely on the inferred static type.
- [ ] Distinguish `int` from `Integer` and check for null before unboxing.
- [ ] Distinguish `var text = "Java";` from `Object text = "Java";`.
- [ ] Understand why variables pointing to the same `String` can select two different overloads when their static types differ.
- [ ] Able to run `VarStaticTypingDemo.java` and explain the outputs.

**Conclusion:** `var` shortens local variable declarations, but static type checking, overload resolution, and generic type checks still work just as they do with explicit declarations.