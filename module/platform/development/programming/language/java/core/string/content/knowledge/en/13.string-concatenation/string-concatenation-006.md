# Converting an Object via toString When Participating in String Concatenation in Java

In Java, the `+` operator does not only add numbers. When **at least one operand is a `String`**, it performs **string concatenation**. If the other operand is an object, Java applies **string conversion** to obtain a textual representation of that value; for a non-`null` object, the usual behavior is determined through the `toString()` method.

Example:

```java
Object value = Integer.valueOf(42);
String message = "Value: " + value;
System.out.println(message); // Value: 42
```

Here `Integer` provides `toString()`, so the concatenated portion is the text `42`. However, **do not assume every `Object` automatically has a human-readable representation**: if a class does not override `toString()`, the result typically has the form `ClassName@hexHash`; and for `null`, Java concatenates the literal text `"null"` instead of calling a method on a null reference.

This lesson focuses on **how an Object value is converted into text when participating in concatenation**, not merely on how to use the `+` operator.

## 1. String conversion when using the + operator

For the expression:

```java
String result = "Item: " + someObject;
```

if `someObject` has a reference type such as `Book`, `Object`, `List<?>`, or a user-defined type, Java needs a `String` representation of the right-hand value. In terms of the **semantic model**:

1. Evaluate the operands of `+` according to Java's expression evaluation rules.
2. If one operand has type `String`, `+` is string concatenation; the other operand is converted into an appropriate string representation.
3. For a **non-`null` object reference**, the textual representation behavior is tied to the `toString()` of its runtime type.
4. For a **`null` reference**, the result of string conversion is the four-letter text `"null"`.
5. Combine the textual parts to produce the `String` value of the concatenation expression.

**Technical note:** This is the **language-level observable** rule, not a guarantee that bytecode must explicitly call `String.valueOf(Object)` or construct a `StringBuilder`. Compilers and JVMs are permitted to use other optimization strategies as long as Java semantics are preserved.

When reading:

```java
String line = "User=" + user;
```

you can picture that Java needs a representation of `user` matching the meaning of `String.valueOf(user)` when `user` is an object reference. Still, do not conclude “Java definitely compiles this into a `user.toString()` call at that spot”: the exact execution mechanism depends on the compiler and JDK.

### Which values are converted to text?

| Operand kind | Example | Representation when concatenated |
|---|---|---|
| `String` | `"abc"` | Content of that string |
| Primitive integer | `42` | Text `"42"` |
| `boolean` | `true` | Text `"true"` |
| `char` | `'A'` | Text `"A"` |
| Object with a useful `toString()` | `new Book("Java")` | Value produced by `Book.toString()` |
| Object without overridden `toString()` | `new Object()` | Default pattern `ClassName@hexHash`, not business content |
| `null` reference | `(Object) null` | `"null"` |
| Array such as `int[]` | `new int[]{1,2}` | Usually default identity representation, **not** `"[1, 2]"` |

The rule for primitives involves **converting primitive data to text**; primitives **do not have** a `toString()` instance method. Only reference-type values can have `toString()` invoked on them.

## 2. Role of Object.toString()

Every Java class inherits or can override `toString()` from `java.lang.Object`. Signature:

```java
public String toString()
```

The default implementation in `Object` produces a string roughly of the form:

```text
Class_name@hex_hash_value
```

For example, `com.example.User@5e2de80c`. **Hash values, full class names, and object allocation counts should not be relied upon as fixed output in tests.** This is not an end-user display format or stable data.

A class should override `toString()` if the application needs a meaningful textual representation in logs or when embedding into messages.

```java
final class Book {
    private final String title;

    Book(String title) {
        this.title = title;
    }

    @Override
    public String toString() {
        return "Book(" + title + ")";
    }
}
```

This is an **illustrative class definition**. With `new Book("Java")`:

```java
Book book = new Book("Java");
System.out.println("Item: " + book); // Item: Book(Java)
```

The text `Book(Java)` is determined by **`Book.toString()`**. The `+` operator has no knowledge of what field `title` is and does not inspect object fields automatically.

### Polymorphism

When a variable is declared with the supertype `Object` but actually points to a `Book`, `Book.toString()` is still used:

```java
Object item = new Book("Java");
String line = "Item: " + item; // Item: Book(Java)
```

It is the **runtime object type** that determines which overridden method runs, not merely the variable's static type `Object`.

If a class does not override `toString()`, Java uses the inherited implementation. That explains why logs sometimes show `Book@...` instead of the expected `title` field.

## 3. Null: not the same as calling toString() directly

This is the most common source of confusion:

```java
Object missing = null;

String a = "Value: " + missing;
String b = String.valueOf(missing);

System.out.println(a); // Value: null
System.out.println(b); // null
```

Neither expression above **throws `NullPointerException`**. With the concatenation operator, a `null` reference is converted into the text `"null"`; `String.valueOf(Object)` handles `null` in the same way.

Conversely:

```java
Object missing = null;
// missing.toString(); // If executed: NullPointerException
```

**There is no object on which to invoke a method** when the receiver is `null`. Java does not secretly call `toString()` on `null` during string concatenation.

A comparison table:

| Expression | Result |
|---|---|
| `"x=" + (Object) null` | `"x=null"` |
| `String.valueOf((Object) null)` | `"null"` |
| `Objects.toString(null)` | `"null"` |
| `Objects.toString(null, "N/A")` | `"N/A"` |
| `((Object) null).toString()` | Throws `NullPointerException` |

The examples with `Objects` require `import java.util.Objects;`. Note that `Objects.toString(obj, nullDefault)` lets you specify a fallback string when the object is `null`—useful when you want to display `"(not available)"` or `"N/A"` instead of `"null"`.

### Be careful with uncast String.valueOf(null)

Java has multiple `String.valueOf(...)` overloads, including `valueOf(Object)` and `valueOf(char[])`. When writing:

```java
// String.valueOf(null); // May select the char[] overload and throw NullPointerException
String result = String.valueOf((Object) null); // "null"
```

The commented line is only there to explain **overload resolution**. Casting `(Object) null` ensures the overload for object references is selected. In regular code where a variable already has static type `Object`, `String.valueOf(variable)` selects the `Object` overload.

## 4. Is String.valueOf(Object) the same as toString()?

`String.valueOf(Object obj)` provides a convenient call site to turn a reference into a `String`. For a non-null object, it uses the representation returned by `obj.toString()`; for `null`, it returns the string `"null"`.

```java
Book book = new Book("Java");

String a = book.toString();
String b = String.valueOf(book);
String c = "" + book;

System.out.println(a.equals(b)); // true
System.out.println(b.equals(c)); // true
```

The example above assumes the `Book` definition from section 2. All have the same **content**; do not use `==` to infer that the variables necessarily reference the same `String` object.

Three questions should be kept separate:

- **What text does `toString()` return?** Depends on how the class implements it.
- **How does `String.valueOf(...)` handle null and overloads?** Depends on the argument type resolved by the compiler.
- **What result does the `+` concatenation operator produce?** Follows Java's *string conversion* and *string concatenation* rules.

A poorly designed `toString()` can also throw an exception or generate unstable text. `String.valueOf` and `+` **do not validate** or guarantee that the content provided by `toString()` is business-appropriate.

## 5. Standalone Java 17+ program

The example below avoids printing unpredictable identity hashes of arrays; instead it **compares behaviors** and uses `Arrays.toString` to print array data in a clear format.

Save as **`ObjectConcatDemo.java`**:

```java
import java.util.Arrays;

public class ObjectConcatDemo {
    static final class Book {
        private final String title;

        Book(String title) {
            this.title = title;
        }

        @Override
        public String toString() {
            return "Book(" + title + ")";
        }
    }

    static final class Tracked {
        static int calls;

        @Override
        public String toString() {
            calls++;
            return "tracked";
        }
    }

    public static void main(String[] args) {
        Object book = new Book("Java");
        Object missing = null;

        System.out.println("item: " + book);
        System.out.println("missing: " + missing);
        System.out.println("valueOf null: " + String.valueOf(missing));
        System.out.println("valueOf matches: "
                + String.valueOf(book).equals("Book(Java)"));
        System.out.println("book content equals: "
                + book.equals("Book(Java)"));

        int[] numbers = {1, 2, 3};
        System.out.println("array readable: "
                + Arrays.toString(numbers));
        System.out.println("array concat is readable: "
                + ("Array: " + numbers).equals("Array: [1, 2, 3]"));

        Tracked tracked = new Tracked();
        System.out.println("tracked: " + tracked);
        System.out.println("toString calls: " + Tracked.calls);

        System.out.println("math1: " + ("sum=" + 7 + 3));
        System.out.println("math2: " + ("sum=" + (7 + 3)));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ObjectConcatDemo.java
java ObjectConcatDemo
```

Output:

```text
item: Book(Java)
missing: null
valueOf null: null
valueOf matches: true
book content equals: false
array readable: [1, 2, 3]
array concat is readable: false
tracked: tracked
toString calls: 1
math1: sum=73
math2: sum=10
```

**Analysis:**

1. `book` is declared as `Object` but points to a `Book`; `Book.toString()` returns `"Book(Java)"`.
2. `missing` is `null`, so participating in `"missing: " + missing` becomes the text `"null"` without throwing an exception.
3. `String.valueOf(missing)` returns `"null"`. For `book`, `String.valueOf(book)` has content equal to `"Book(Java)"`.
4. `book.equals("Book(Java)")` is `false` because `Book` in the example does not override `equals`; it inherits `Object`'s identity comparison. **Having identical text representations does not make two values of different types equal**.
5. An `int[]` array does not automatically turn into `"[1, 2, 3]"` when concatenated. `Arrays.toString(numbers)` is the explicit method for displaying one-dimensional array contents.
6. `Tracked.toString()` increments the counter `calls` every time it is invoked. The simple concatenation `"tracked: " + tracked` produces `tracked: tracked` and makes **one call** on this object in the program.
7. `+` is a **left-associative** operator. `"sum=" + 7 + 3` is interpreted as `("sum=" + 7) + 3`, yielding `sum=73`, whereas `"sum=" + (7 + 3)` adds the numbers first to become `sum=10`.

This example shows that Java determines **when `+` is numeric addition and when it is string concatenation**, while how an `Object` is turned into text is a separate question.

## 6. Arrays are a very commonly misunderstood case

Java arrays are objects as well, yet `int[]`, `String[]`, and multidimensional arrays **do not override `toString()` by default to display each element**. Therefore:

```java
int[] scores = {7, 8, 9};
String message = "Scores: " + scores;
```

`message` does **not** take the form `"Scores: [7, 8, 9]"`. It will contain the array object's representation string, typically the JVM array type name and a hex identity-related code; the specific value is not stable for full-string equality testing.

If you need to present data, use:

```java
import java.util.Arrays;

int[] scores = {7, 8, 9};
String formatted = "Scores: " + Arrays.toString(scores);
System.out.println(formatted); // Scores: [7, 8, 9]
```

For multidimensional arrays:

```java
int[][] matrix = {{1, 2}, {3, 4}};
System.out.println("matrix: " + Arrays.deepToString(matrix));
// matrix: [[1, 2], [3, 4]]
```

The two snippets above are **illustrative code snippets**: place them in an appropriate method with `import java.util.Arrays`. If the value is a nested object array structure, consider `Arrays.deepToString(...)`. It is helpful for debugging, though when exporting formal data exchange formats (JSON, CSV, etc.) you should use a library/serializer with a well-defined contract.

### Special case: char[]

There is a surprising difference between **string concatenation** and **overload selection of println/valueOf**:

```java
char[] letters = {'J', 'a', 'v', 'a'};

System.out.println(letters);               // Java
System.out.println(String.valueOf(letters)); // Java
System.out.println("prefix: " + letters);   // Typically prefix: [C@...
```

`System.out.println(char[])` has a dedicated overload to print **the characters in the array**, and `String.valueOf(char[])` also has a specialized overload. However, in `"prefix: " + letters`, the array undergoes **string conversion** under concatenation rules, rather than automatically invoking the `char[]` printing overload. Do not expect the same result as the first two lines.

This is why looking only at `println(someValue)` output can mislead you about **the behavior of `"prefix: " + someValue`**: `println` has multiple overloads, whereas the `+` operator follows the language's rules.

## 7. Default toString(), equals(), and hashCode() are not the same

Three concepts must be separated:

- **`toString()`**: returns a textual representation of the object.
- **`equals(Object)`**: defines object equality (if overridden by the class).
- **`hashCode()`**: used in hash-based structures and must obey its contract with `equals`.

Overriding `toString()` **does not automatically alter** `equals` or `hashCode`. Having two objects with the same `toString()` does not mean they are equal, nor does it mean they are the same reference.

Example:

```java
Book one = new Book("Java");
Book two = new Book("Java");

System.out.println(one.toString().equals(two.toString())); // true
System.out.println(one == two);                             // false
System.out.println(one.equals(two));                        // false
```

This snippet uses the `Book` class declared above, which does **not** override `equals`. If a domain entity requires value comparison, design `equals`/`hashCode` explicitly or use a type with clear value semantics such as `record` where appropriate. Never use `toString()` as a substitute for value comparison.

Likewise, the default `Object.toString()` typically relates to `hashCode()` in the text after `@`, yet that hex representation is **not** a unique ID, is not stable across runs, and must not be used as a business key.

## 8. When is toString() called and what side effects can it have?

A `toString()` method can perform arbitrary work: computations, reading fields, accessing state, or even throwing exceptions. When an object participates in string concatenation, **its representation is evaluated during execution of the concatenation**. Java does not “pre-cache” a printed copy of the object when the object is constructed.

For example, if an object mutates its contents, concatenations performed at different times can produce different text:

```java
final class Counter {
    int value;

    @Override
    public String toString() {
        return "Counter(" + value + ")";
    }
}
```

Inside a method:

```java
Counter counter = new Counter();
String before = "State: " + counter;
counter.value = 2;
String after = "State: " + counter;

System.out.println(before); // State: Counter(0)
System.out.println(after);  // State: Counter(2)
```

Using `toString()` purely for formatting **does not make the object immutable**. If `toString()` throws an unchecked exception, the string-building operation can also fail. This matters in logging or error messages: a `toString()` with side effects or external service dependencies can make diagnostics difficult.

**Design recommendation:** `toString()` should be easy to understand, reasonably cheap, free of external service dependencies whenever possible, and never accidentally expose passwords, access tokens, financial details, or sensitive data. Logging `"user=" + user` puts the output of `toString()` into logs; actively control which fields are emitted.

### Recursive call cycles to avoid

If inside `toString()` you concatenate `this` itself:

```java
@Override
public String toString() {
    return "Self: " + this; // Wrong: repeatedly calls toString() again
}
```

infinite recursion can occur until a `StackOverflowError` is thrown. Instead, build the text from specific fields or simple data types. When an object graph contains cycles, chaining `toString()` across linked objects can also cause recursion; cycle-aware printing is needed if data has that structure.

## 9. Evaluation order, numeric addition, and string concatenation

With a `String` on the left, `"sum=" + 7 + 3` produces `"sum=73"`; parentheses in `"sum=" + (7 + 3)` produce `"sum=10"`. This rule matches other concatenations and does not turn the source `Object` into a `String`. The lesson **Left-to-right associativity** is dedicated to expression parsing, whereas here the focus is **when an object's `toString()` is invoked and what side effects it might have**.

## 10. StringBuilder.append(Object) and other formatting options

When building text from many parts in a loop, `StringBuilder` is commonly used:

```java
Object book = new Book("Java");

String message = new StringBuilder()
        .append("Item: ")
        .append(book)
        .toString();
```

`StringBuilder.append(Object)` uses the object's string representation (per the `String.valueOf(Object)` contract), so the example also produces `"Item: Book(Java)"`. For `null`, it appends the text `"null"` into the builder.

**However, `StringBuilder` has multiple overloads** such as `append(char[])` and `append(int)`. Passing a `char[]` array directly may select the `append(char[])` overload and append its characters, whereas `append((Object) letters)` uses object handling. Therefore, comparing behaviors always requires checking **the static type of the expression and which overload is selected**.

### Does string concatenation with + always create a StringBuilder?

No. Many older examples and JVM texts state that the compiler “translates concatenation into `StringBuilder`”, but that is not an immutable language rule. On modern JDKs, the compiler often uses the **`invokedynamic` mechanism with string-concat recipes** (JEP 280) and the JVM can apply further optimizations. The contract application code relies on is **the value and semantics of the concatenation expression**, not a specific bytecode sequence or builder structure.

You can inspect it using:

```bash
javac ObjectConcatDemo.java
javap -c -p ObjectConcatDemo
```

In bytecode produced by an appropriate compiler/JDK you may see `invokedynamic` for string concatenation. Do not infer performance solely from how many `new StringBuilder` instructions appear in an output: the JVM can apply many optimizations, and the cost of a custom class's `toString()` can sometimes outweigh the concatenation itself.

If measurement is needed, run proper benchmarks with JMH; do not assume `+` is always slower than `StringBuilder` in every context.

### When should you format explicitly instead of concatenating an Object?

- **Arrays:** `Arrays.toString` or `Arrays.deepToString`.
- **Dates/times:** use `java.time.format.DateTimeFormatter` when a deterministic format is needed.
- **Currency/numbers:** use `NumberFormat`/`DecimalFormat` with the appropriate locale and rounding rules.
- **JSON/XML data:** use a standard serializer, **never** treat `toString()` as JSON.
- **User-facing messages:** use clear templates/formatters and avoid exposing whole internal objects to the UI.
- **Logs:** `toString()` can be useful when data is non-sensitive, while controlling content, cost, and exceptions.

## 11. Common misunderstandings and mistakes

| Misunderstanding | Why it is wrong | Correct understanding / fix |
|---|---|---|
| “When concatenating an Object, Java calls `toString()` even on null.” | `null` has no instance on which to call a method; concatenation produces `"null"` via string conversion | Distinguish `"x=" + nullReference` from `nullReference.toString()` |
| “Every object automatically concatenates into its field values.” | Default `Object.toString()` usually prints only class name and hash | Override `toString()` when needed, or format fields explicitly |
| “`"Array: " + array` lists the elements.” | Arrays lack a `toString()` that prints elements | Use `Arrays.toString`/`deepToString` |
| “`System.out.println(charArray)` and `"x=" + charArray` work the same.” | `println` has a `char[]` overload; concatenation uses string conversion | Check the API and the static type of the argument |
| “`String.valueOf(null)` always returns `"null"`.” | The `char[]` overload may be selected for the `null` literal | Specify `String.valueOf((Object) null)` or use an `Object` variable |
| “Identical `toString()` text means `equals` must be true.” | Text representation does not define equality | Design `equals/hashCode` separately |
| “The Object is permanently converted into a String after concatenation.” | `+` only creates a result string value | The source variable retains its type and reference |
| “Default `Object.toString()` output is a stable ID.” | The `Class@hex` form is not a business key | Use a system-managed ID |
| “`toString()` cannot fail.” | An override can throw or recurse | Keep `toString()` simple and safe |
| “Java must compile string concatenation into `new StringBuilder`.” | Compiler/JDK details can vary | Rely on JLS semantics, not hardcoded bytecode strategies |

## 12. Self-check exercises

### Exercise 1: null and override

Given:

```java
final class User {
    final String name;
    User(String name) { this.name = name; }

    @Override
    public String toString() {
        return "User(" + name + ")";
    }
}

Object a = new User("Lan");
Object b = null;

System.out.println("a=" + a);
System.out.println("b=" + b);
```

**Answer:**

```text
a=User(Lan)
b=null
```

The first line uses `User.toString()` through polymorphism; the second line uses string conversion for a null reference.

### Exercise 2: difference between addition and concatenation

Predict:

```java
Object number = Integer.valueOf(8);
System.out.println("n=" + number + 2);
System.out.println("n=" + (8 + 2));
```

**Answer:**

```text
n=82
n=10
```

Once a `String` appears on the left, the remaining `+` operations concatenate text. The parenthesized expression performs numeric addition of the two numbers first.

### Exercise 3: arrays

Given:

```java
String[] names = {"Lan", "Minh"};
String a = "names=" + names;
String b = "names=" + java.util.Arrays.toString(names);
```

Which expression displays `names=[Lan, Minh]`? **Answer:** only `b`; `a` prints the array object representation instead of joining elements automatically.

### Exercise 4: object value vs. String value

A `Customer` class overrides `toString()` to return `"VIP"`. Two distinct objects both have `toString()` equal to `"VIP"`. Does that make `customer1 == customer2` true? **No.** Two distinct references still have different identities. Having two `String` values with identical contents does not change the equality of the two source objects.

## 13. Official references

- [Java Language Specification `15.18.1 — String Concatenation Operator +`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18.1): string concatenation rules for the `+` operator.
- [Java Language Specification `5.1.11 — String Conversion`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.11): handling primitive values, object references, and null when converting to string.
- [Java SE 17 — `Object.toString()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#toString()): behavior and purpose of the method.
- [Java SE 17 — `String.valueOf(Object)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#valueOf(java.lang.Object)): converting an object or null to text.
- [JEP 280 — Indify String Concatenation](https://openjdk.org/jeps/280): illustrates why Java concatenation should not be equated with a single bytecode strategy.

**Takeaway:** When an `Object` participates in concatenation with a `String` via `+`, Java performs *string conversion*: for a non-null object, the representation depends on the `toString()` of its runtime type; for null, the text is `"null"`. **`toString()` is only a textual representation—not identity, equality, or a serializer**—and for arrays or business data you should format explicitly when stable, clear output is needed.
