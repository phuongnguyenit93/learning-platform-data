# Confusing a Record Pattern with a Constructor Pattern in Java 21+

## 1. Common mental model error: similar-looking syntax that works differently

When learning Java 21, beginners can easily look at the following two snippets and assume both are ways of "calling a constructor" on a record:

~~~java
record Point(int x, int y) {}

// CREATE an object via a constructor call.
Point point = new Point(2, 3);

// MATCH and DECONSTRUCT data of an existing object.
Object value = point;
if (value instanceof Point(int a, int b)) {
    System.out.println(a + b); // 5
}
~~~

Both syntaxes use parentheses and the same name `Point`, but their meanings are completely different:

- `new Point(2, 3)` is a **class instance creation expression**. It invokes the constructor, creates a `Point` object, performs validation/normalization in the constructor, and returns a reference.
- `Point(int a, int b)` in `instanceof` is a **record pattern** (*deconstruction pattern*). It checks whether the value matches a `Point` record, then binds the components to the variables `a` and `b`. It **does not call the constructor** and **does not create a new `Point`**.
- In Java 21, **there is no general "constructor pattern"** for every class just because that class has a constructor. The `Type(...)` syntax of a record pattern is based on the **record components declaration**, not on the parameter list of an arbitrary constructor.

This article focuses on the confusion described above, how to distinguish them by syntactic context, common compiler errors, and how to use record patterns properly in program design. Record patterns became officially stable in **Java 21 (JEP 440)** and can be combined with pattern matching in `switch` (JEP 441).

## 2. Quick comparison between constructor and record pattern

| Criterion | Constructor invocation | Record pattern |
| --- | --- | --- |
| Example | `new Point(2, 3)` | `Point(int a, int b)` |
| Purpose | **Create** a new instance | **Test and deconstruct** an existing instance |
| Position | In an object creation expression, e.g. on the right-hand side of `=` | **Pattern** position: after `instanceof`, in a `switch` `case`, or inside a nested pattern |
| Parentheses content | **Argument values/expressions** matching the constructor parameter types | **Component patterns** in the exact order and types of the record components |
| Calls constructor? | Yes | No |
| Creates a new record object? | Yes | No |
| Introduces new variables | Assign the result to an external variable if desired | Binds **pattern variables** when the match succeeds |
| Structural basis | A valid constructor and its parameters | The list of **record components** declared in the record |
| If mismatched | Compile-time error or exception from the constructor | Compile-time error if the pattern has invalid types; if the pattern is valid but does not match the data at runtime, the branch does not execute |

A simple rule of thumb: **`new` creates, `instanceof`/`case` tests and deconstructs**. Similar record names and parentheses do not mean they use the same runtime mechanism.

## 3. Why are record patterns not constructor calls?

A Java record such as:

~~~java
record Point(int x, int y) {}
~~~

declares a **data structure** consisting of two components `x` and `y`. The compiler generates the canonical constructor, `x()`/`y()` accessors, and other appropriate members. The following code operates on an existing object:

~~~java
Point point = new Point(7, 4);

// Explicit access using accessors:
int a = point.x();
int b = point.y();

// Or using a record pattern (does not create a new object):
if (point instanceof Point(var x, var y)) {
    System.out.println(x + y); // 11
}
~~~

A record pattern can be understood **conceptually** as:

1. Determining whether the target object matches the requested record class.
2. Deconstructing the object by retrieving the record's components.
3. Matching each component against the pattern at the corresponding position.
4. If everything matches, binding the pattern variables and continuing within the valid scope.

This description is only for mental visualization, **not an exact source-code transformation required to be performed by the compiler**. The details of evaluating record patterns, component access order, and error handling follow the Java Language Specification.

Crucially: **when matching a record pattern, there is no `new Point(...)` step**. A compact constructor used to validate `Point` only runs when the record is created via its constructor, not every time a record pattern matches.

Record accessors can be explicitly declared by the programmer and contain custom behavior. Therefore, deconstruction may execute accessor code and may encounter an exception if an accessor itself throws an error. **Not calling a constructor** does not mean **no code at all is called** during matching.

## 4. Correct syntax by context: expressions and patterns

### 4.1. Creating an object: use actual argument expressions

~~~java
Point p = new Point(2, 3);          // Two int values.
Point q = new Point(p.x(), p.y());  // Can retrieve values from a previous object.
~~~

Argument expressions inside `new Point(...)` must produce **values** of the types required by the constructor. The following statement is **invalid**:

~~~java
// DOES NOT COMPILE: var x, var y here are not valid arguments.
// Point p = new Point(var x, var y);
~~~

`var` does not automatically turn a constructor argument into a pattern. `var` is only allowed in positions where Java syntax permits type inference, such as local variable declarations and component patterns; do not place `var x` as an argument value.

### 4.2. Matching an object: use component patterns

~~~java
Object input = new Point(2, 3);
if (input instanceof Point(int x, int y)) {
    System.out.println("Tổng: " + (x + y)); // Tổng: 5
}
~~~

Here `int x` and `int y` are **type patterns** for the components. No `Point(int x, int y)` constructor is called a second time. If you want the compiler to infer both component types:

~~~java
if (input instanceof Point(var x, var y)) {
    System.out.println(x * y); // 6
}
~~~

The compiler knows that both `x` and `y` of record `Point` are `int`, so the pattern variables are inferred as `int`. The `var` keyword does not introduce dynamic typing.

### 4.3. `Point(...)` is not a record creation expression

~~~java
// DOES NOT COMPILE — a record pattern is not an expression returning a Point.
// Point newPoint = Point(var x, var y);
~~~

Replace it with:

~~~java
Point newPoint = new Point(2, 3);
~~~

If the goal is to test/deconstruct data, place the record pattern in a pattern position such as `instanceof Point(var x, var y)` or `case Point(var x, var y) -> ...`, rather than using it as a standalone expression.

## 5. Record patterns apply only to record classes, not every constructor

A regular Java class having a constructor **does not mean** it has record components:

~~~java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}
~~~

The following form **does not compile** in Java 21:

~~~java
// DOES NOT COMPILE: Person is a regular class, not a record.
// Object obj = new Person("An");
// if (obj instanceof Person(String name)) {
//     System.out.println(name);
// }
~~~

The compiler error may be:

~~~text
deconstruction patterns can only be applied to records, Person is not a record
~~~

Even though the constructor `Person(String name)` looks like a "template with one string", Java **does not** automatically infer how to deconstruct class `Person` from its constructor. A constructor receives data when **creating** an object; it does not provide a general deconstruction contract for the language.

How to handle a regular class:

~~~java
Object obj = new Person("An");

if (obj instanceof Person person) {   // Regular type pattern.
    String name = person.name();      // Read via method.
    System.out.println(name);        // An
}
~~~

Here `instanceof Person person` is a type pattern, **not** a record pattern. If the data belongs to an appropriate value-object model and you genuinely want deconstruction by record components, you may consider designing `record Person(String name) {}`. However, you should not turn a mutable entity or a class carrying complex invariants into a record just to get concise syntax.

## 6. Constructors can validate; record patterns do not re-validate via the constructor

Consider a record with a compact constructor:

~~~java
record Point(int x, int y) {
    public Point {
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException("Tọa độ phải không âm");
        }
    }
}
~~~

When creating:

~~~java
Point ok = new Point(2, 3); // Valid.

// The following throws IllegalArgumentException from the constructor:
// Point bad = new Point(-1, 3);
~~~

When matching an already validly constructed object:

~~~java
Object value = ok;
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y); // 5
}
~~~

The constructor **does not run again**. The pattern only checks and extracts the existing components. This is important when you use invariants such as non-negative coordinates, non-empty values, or positive quantities:

- **The record's constructor** is responsible for guarding instance creation conditions.
- **The record pattern** is responsible for expressing match conditions and extracting data.
- **Domain services/handlers** are responsible for business rules that require external state.

If you need additional conditions when matching, combine the pattern with `&&` or `when`:

~~~java
Object input = new Point(4, 4);
if (input instanceof Point(int x, int y) && x == y) {
    System.out.println("Đường chéo"); // Đường chéo
}
~~~

This statement does not create a new `Point(4,4)`; it inspects the components of the existing instance and checks the condition `x == y`.

## 7. Distinguishing compiler errors from valid patterns that do not match at runtime

Four characteristic cases:

### Error A — wrong number of components

~~~java
record Point(int x, int y) {}

// DOES NOT COMPILE: Point has two components, the pattern provides only one.
// if (obj instanceof Point(int x)) { ... }
~~~

This is an error because the **number of component patterns** must match the number of record components; the compiler is not calling a one-parameter constructor overload.

### Error B — wrong component type

~~~java
// DOES NOT COMPILE: the first component has type int.
// if (obj instanceof Point(String x, int y)) { ... }
~~~

`String x` is not a pattern validly applicable to an `int` component. Fix:

~~~java
if (obj instanceof Point(int x, int y)) {
    System.out.println(x + y);
}
~~~

### Error C — using a record pattern on a regular class

~~~java
// DOES NOT COMPILE: Person is not a record.
// if (obj instanceof Person(String name)) { ... }
~~~

Use `obj instanceof Person person` and then call the class's accessor.

### Error D — using a pattern as a constructor argument

~~~java
// DOES NOT COMPILE:
// new Point(var x, var y);
~~~

Use actual **values**: `new Point(2, 3)` or `new Point(existing.x(), existing.y())`.

All of these errors are determined **at compile time**. Contrast them with a valid situation that does not match:

~~~java
Object obj = "hello";

if (obj instanceof Point(var x, var y)) {
    System.out.println(x + y);
} else {
    System.out.println("Không phải Point"); // Prints this line.
}
~~~

Here the syntax and pattern types are completely valid, but the instance has runtime class `String`, not `Point`. Java evaluates `instanceof` to `false` and executes the `else` branch. There is **no** constructor error.

## 8. Nested record patterns: not multiple nested constructor calls

A more easily confused example:

~~~java
record Point(int x, int y) {}
record Shipment(String id, Point destination) {}

Object value = new Shipment("S-1", new Point(1, 5));

if (value instanceof Shipment(var id, Point(var x, var y))) {
    System.out.println(id + " đến " + x + "," + y);
    // S-1 đến 1,5
}
~~~

In the **object creation expression**:

~~~java
new Shipment("S-1", new Point(1, 5))
~~~

Java actually calls the `Point` constructor and then the `Shipment` constructor as part of evaluating the argument expressions.

However, in the **record pattern**:

~~~java
Shipment(var id, Point(var x, var y))
~~~

Java does not call any constructor; it deconstructs the existing `Shipment` instance, then deconstructs the `destination` component if that component matches the `Point` record. Each pair of parentheses in the pattern corresponds to a **level of record data**, not a constructor being re-invoked.

**Null in a nested record:** If `destination` is `null`, the nested `Point(var x, var y)` does not match. This can cause the entire `Shipment(var id, Point(...))` pattern not to match even though the outer selector is a valid `Shipment`.

A fallback case can be provided:

~~~java
static String route(Object value) {
    return switch (value) {
        case Shipment(var id, Point(var x, var y)) ->
            id + " đến (" + x + "," + y + ")";
        case Shipment(var id, var destination) ->
            id + " thiếu điểm đến";
        case null -> "null";
        default -> "Kiểu khác";
    };
}
~~~

The specific record pattern branch **precedes** the general `Shipment(var id, var destination)` branch. For `new Shipment("S-2", null)`, the first branch does not match, while the second branch can still match and bind `destination == null`.

Note: an unconditional component pattern like `var destination` can bind a null reference value inside a record pattern. Do not confuse that with `null instanceof Point` — a standalone `instanceof` on null returns `false`.

## 9. `switch` pattern matching does not create new objects

In Java 21, record patterns are especially useful when branching based on existing data:

~~~java
static String describe(Object value) {
    return switch (value) {
        case Point(var x, var y) when x == y ->
            "Trên đường chéo: " + x;
        case Point(var x, var y) ->
            "Điểm (" + x + "," + y + ")";
        case null -> "null";
        default -> "Kiểu khác";
    };
}
~~~

Each `case Point(...)` is **a pattern**, not a `new Point(...)` call. The `when` guard is evaluated only after the pattern has matched and its pattern variables are bound.

- `case Point(var x, var y) when x == y`: selected only if it is a `Point` and both coordinates are equal.
- `case Point(var x, var y)`: handles the remaining `Point` instances.
- `case null`: handles a null selector explicitly.
- `default`: handles values not belonging to the types above.

**Case order matters.** If you place the unguarded `case Point(var x, var y)` branch first, a guarded branch of the same type after it may trigger a dominance error because it is shadowed. Branch selection does not depend on which constructor was used to create the `Point`, but on the **runtime value and pattern conditions**.

## 10. Generic records: type names with parentheses do not verify generic arguments at runtime

Record pattern syntax looking like a constructor can be even more misleading when a record has generics:

~~~java
record Box<T>(T value) {}

// Object instantiation:
Box<String> box = new Box<>("Java");

// Deconstruct component when the input type is already known:
if (box instanceof Box(var text)) {
    System.out.println(text.toUpperCase()); // JAVA
}
~~~

Here `new Box<>("Java")` calls the constructor, while `Box(var text)` only matches and deconstructs. The compiler infers `text` as `String` thanks to the static type `Box<String>` of `box`.

If the input is only `Object`, you cannot arbitrarily check a generic argument that has undergone **type erasure**:

~~~java
// DOES NOT COMPILE: Object -> Box<String> requires an unchecked conversion.
// if (unknown instanceof Box<String>(var text)) { ... }
~~~

Use a wildcard and check the actual component when needed:

~~~java
Object unknown = new Box<>("Java");

if (unknown instanceof Box<?>(var item)
        && item instanceof String text) {
    System.out.println(text.toUpperCase()); // JAVA
}
~~~

`Box<?>` allows testing the record class without assuming a concrete type argument; `item instanceof String` is what verifies the runtime type of the existing component. A record pattern is **not** a mechanism for creating/calling a generic constructor, nor does it recover an erased generic argument.

## 11. Complete Java 21+ example: creating records and matching records side by side

Save as **`RecordConstructorPatternDemo.java`**:

~~~java
public class RecordConstructorPatternDemo {
    record Point(int x, int y) {
        public Point {
            if (x < 0 || y < 0) {
                throw new IllegalArgumentException("Tọa độ phải không âm");
            }
        }
    }

    record Shipment(String id, Point destination) {}

    static Point create(int x, int y) {
        return new Point(x, y); // Creation: constructor runs.
    }

    static String readPoint(Object value) {
        if (value instanceof Point(int x, int y)) {
            return "Tổng = " + (x + y); // Match/deconstruct, does not create a Point.
        }
        return "Không phải Point";
    }

    static String describe(Object value) {
        return switch (value) {
            case Shipment(var id, Point(var x, var y)) ->
                id + " đến (" + x + "," + y + ")";

            case Shipment(var id, var destination) ->
                id + " thiếu điểm đến";

            case Point(var x, var y) when x == y ->
                "Trên đường chéo: " + x;

            case Point(var x, var y) ->
                "Điểm (" + x + "," + y + ")";

            case null -> "null";
            default -> "Kiểu khác";
        };
    }

    public static void main(String[] args) {
        Point p = create(2, 3);
        Point q = new Point(2, 3);

        System.out.println("Tạo: " + p);
        System.out.println("Bằng nhau: " + p.equals(q));
        System.out.println("Tách: " + readPoint(p));
        System.out.println("Match: " + describe(p));
        System.out.println("Chéo: " + describe(new Point(4, 4)));
        System.out.println("Lồng: " +
                describe(new Shipment("S-1", new Point(1, 5))));
        System.out.println("Thiếu: " +
                describe(new Shipment("S-2", null)));
        System.out.println("Null: " + describe(null));
        System.out.println("Khác: " + describe("hello"));

        try {
            new Point(-1, 3);
        } catch (IllegalArgumentException ex) {
            System.out.println("Lỗi tạo: " + ex.getMessage());
        }
    }
}
~~~

Compile and run with **JDK 21 or newer**:

~~~bash
javac --release 21 RecordConstructorPatternDemo.java
java RecordConstructorPatternDemo
~~~

Exact output:

~~~text
Tạo: Point[x=2, y=3]
Bằng nhau: true
Tách: Tổng = 5
Match: Điểm (2,3)
Chéo: Trên đường chéo: 4
Lồng: S-1 đến (1,5)
Thiếu: S-2 thiếu điểm đến
Null: null
Khác: Kiểu khác
Lỗi tạo: Tọa độ phải không âm
~~~

**Why is this a good distinguishing example?**

1. Two calls to `new Point(2,3)` create two instances with identical data; the record's `equals()` evaluates equality by component values, **not** object identity.
2. `readPoint(p)` uses `instanceof Point(int x,int y)` to extract the two numbers from instance `p`, then computes their sum without creating a new object.
3. `describe` uses `case Point(...)`, `case Shipment(...)`, and `when` to classify data structures using record patterns.
4. `new Shipment("S-1", new Point(1,5))` is a **real** nested constructor call; `Shipment(var id, Point(var x, var y))` is a nested record pattern and **does not** call any constructor.
5. `Shipment("S-2", null)` shows that a nested `Point` pattern can fail to match due to a null component, while a more general `Shipment` pattern can still handle it.
6. `new Point(-1,3)` throws an exception **at instantiation time** due to the compact constructor. No pattern match needs to re-run that validation.

## 12. Error identification and fix table

| Commonly confused code | Error category | Correct fix or explanation |
| --- | --- | --- |
| `new Point(var x, var y)` | Using pattern syntax as object creation arguments | `new Point(2,3)` or expressions returning `int` |
| `Point(var x,var y)` standalone on the right-hand side of an assignment | Using a pattern as an object creation expression | `new Point(x,y)` if a new instance is needed |
| `obj instanceof Person(String n)` where `Person` is a regular class | Assuming every constructor allows deconstruction | `obj instanceof Person p` then `p.name()` |
| `obj instanceof Point(int x)` | Wrong number of components compared to the record | `Point(int x,var ignored)` |
| `obj instanceof Point(String x,int y)` | Component `x` of `Point` is `int` | `Point(int x,int y)` or `Point(var x,var y)` |
| `case Point(var x,var y)` understood as a statement creating a `Point` | Confusing `switch` dispatch with object creation | This tests and extracts components of the selector |
| `Shipment(var id, Point(...))` understood as calling 2 constructors | Confusing nested patterns with nested creation | This is two levels of destructuring, with no `new` |
| `default` assumed to catch `null` | Misunderstanding `null` rules in `switch` | Use `case null` if `null` is accepted |
| `Point(var x,var y)` always matches any object | Overlooking record class check | Must match the record type and all component patterns must match |
| Using `Box<String>(...)` from `Object` and expecting the JVM to check the generic argument | Forgetting type erasure | Use `Box<?>` then check the needed component value |

## 13. Self-check exercises

**Exercise 1.** Given:

~~~java
record User(String name, int age) {}
~~~

Between `new User("An", 20)` and `User(var name, var age)`, which one creates an instance? Which one is a pattern? Write an `if` statement using the pattern to print `name` when the object matches.

**Exercise 2.** Consider the regular class:

~~~java
class Book {
    private final String title;

    Book(String title) {
        this.title = title;
    }

    String title() {
        return title;
    }
}
~~~

Why is `obj instanceof Book(String title)` invalid in Java 21, even though the class has a `Book(String title)` constructor? Rewrite it using a type pattern.

**Exercise 3.** Given `record Point(int x,int y) {}`, explain why `new Point(3,4)` is valid while `new Point(int x,int y)` is invalid in a constructor call expression context. What must you write to extract `x` and `y` from an existing `Point` instance?

**Exercise 4.** Given `record Delivery(String id, Point point) {}`, why might the pattern `Delivery(var id, Point(var x,var y))` fail to match `new Delivery("D-1",null)` even though the outer record is a valid `Delivery`?

**Exercise 5.** If the compact constructor of `Point` validates that coordinates are non-negative, does running `if (p instanceof Point(var x,var y))` re-invoke the compact constructor? Why should invariants be placed in the constructor rather than expecting patterns to validate them?

**Suggested answers:**

~~~java
// Exercise 1: Create an instance:
User user = new User("An", 20);
// Exercise 1: Match and deconstruct:
Object obj = user;
if (obj instanceof User(var name, var age)) {
    System.out.println(name); // An
}

// Exercise 2: Book is a regular class, use a type pattern:
if (obj instanceof Book book) {
    System.out.println(book.title());
}

// Exercise 3:
Point p = new Point(3, 4);  // Constructor.
if (p instanceof Point(var x, var y)) {
    System.out.println(x + y); // 7
}
~~~

Exercise 4: the nested `Point(...)` pattern does not match `null`; you can add a general `Delivery(var id,var point)` branch to handle it. Exercise 5: it does **not** re-invoke the constructor when matching; the constructor guards validity invariants when creating the record, whereas the record pattern uses existing data to test/deconstruct.

## 14. Conclusion

- **A constructor expression** `new RecordType(values)` uses **values** to **create** an object.
- **A record pattern** `RecordType(componentPatterns)` uses **patterns** to **match and deconstruct** an existing object.
- Java 21 does not have a general "constructor pattern" for every class with a constructor; record patterns rely on **record components**.
- When you see `Point(...)`, check the **context**: after `new` it is instance creation; after `instanceof` or in `case` it is pattern matching.
- Patterns do not re-run the canonical/compact constructor, but they still enforce type rules, component order, nested matching, null handling, and flow scoping.

### References

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): syntax and semantics of deconstruction patterns for records (Java 21).
- [JEP 395 — Records](https://openjdk.org/jeps/395): record components, constructors, accessors, and value-oriented records.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): using record patterns in `switch`, `when` guards, and exhaustiveness.
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [JLS 21, `14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
