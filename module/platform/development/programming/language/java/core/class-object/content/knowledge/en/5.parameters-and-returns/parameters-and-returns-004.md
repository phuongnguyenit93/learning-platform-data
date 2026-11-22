# Return Values as Primitive Data, References, or `null` in Java

A Java method can **return a primitive value**, **return a reference value** to an object, or **return `null`** when the return type allows it. How the return type is declared and how the `return` statement is written determine what the caller receives, how it can be manipulated further, and what risks arise.

Example of three methods:

~~~java
class Sample {
    int count() {
        return 12;
    }

    String title() {
        return "Java";
    }

    String missingTitle() {
        return null;
    }
}
~~~

This is an **illustrative declaration snippet** without a `main` method to run standalone:

- `count()` returns **the `int` value 12**; the caller can store that value in a compatible variable.
- `title()` returns **a `String` reference**, pointing to the object representing the string `"Java"`.
- `missingTitle()` returns **a null reference**, indicating that there is currently no `String` object to use.

Java **passes parameters by value and returns results by value**: if the result has a primitive type, the primitive value is passed back; if the result has a reference type, the **reference value** is passed back, rather than Java automatically creating a deep copy of the object. This is the central idea throughout this lesson.

## 1. Where Does the Return Type Appear in a Method Declaration?

A typical method declaration:

~~~java
class Product {
    private final String name;
    private final long price;

    Product(String name, long price) {
        this.name = name;
        this.price = price;
    }

    long getPrice() {       // Return type: long
        return price;
    }

    String getName() {      // Return type: String
        return name;
    }

    void printName() {      // No return value
        System.out.println(name);
    }
}
~~~

This is a declaration snippet, not a standalone program. In `long getPrice()`, `long` before the method name is the **declared return type**; in `String getName()`, `String` is a reference type. The `return` keyword ends execution of the current method, while also carrying a result expression when the method requires a value.

Distinguish among three forms:

~~~java
int doubleNumber(int n) {
    return n * 2;              // returns an int
}

String findName(boolean found) {
    if (found) {
        return "Lan";          // returns a String reference
    }
    return null;               // same String return type, but no object
}

void notifyDone() {
    System.out.println("Done");
    return;                    // valid: exits void method, no expression
}
~~~

These are **method declaration fragments** that must be placed inside a class. For a method with a result, the compiler checks that every execution path capable of completing normally must return a compatible value or be excluded by an exception/valid control flow. You cannot simply leave `return` empty if the method is declared to return `int` or `String`. A `void` method does not return a value; you can omit `return;` and let it end at the end of the method body.

A **constructor** is not a method with a return type: a constructor has the same name as the class and does not declare `int`, `String`, or `void`. A `return;` statement inside a constructor can be used to exit early when valid, but a constructor **does not return a result expression**; it is the `new Product(...)` expression that produces the reference to the object.

## 2. Overview of Results: primitive, reference, null, and void

| Declared type of method | Example | What the caller receives |
| --- | --- | --- |
| Primitive `int` | `int size() { return 3; }` | The `int` value 3 |
| Primitive `boolean` | `boolean isReady() { return true; }` | The `boolean` value true |
| Primitive `double` | `double rate() { return 0.5; }` | The `double` value 0.5 |
| Reference `String` | `String label() { return "A"; }` | A reference value to a `String` |
| Reference `int[]` | `int[] numbers() { return new int[]{1,2}; }` | A reference value to an array |
| Reference `Customer` | `Customer find() { return null; }` | A null value in the context of type `Customer` |
| Reference `Integer` | `Integer score() { return 10; }` | A reference to an `Integer` wrapper via boxing |
| `void` | `void clear() { return; }` | **No result value** |

The rows in the table are short methods for illustration, not a complete program. Java has only **eight primitive types**: `byte`, `short`, `int`, `long`, `float`, `double`, `char`, and `boolean`. Every class, interface, array, and corresponding reference type belongs to the reference group.

**`null` is not a method's declared return type**; you cannot write `null find()`. It is a special value that can be used for appropriate reference types: `String`, `Integer`, `List<String>`, arrays, records, interfaces, etc. In addition, Java has a **null type** in the language's type description, but you do not declare `null` as a regular return type.

## 3. Returning a Primitive: The Caller Receives an Independent Value

Example:

~~~java
class Battery {
    private int percentage = 75;

    int getPercentage() {
        return percentage;
    }

    void drain(int amount) {
        percentage -= amount;
    }
}
~~~

This is an illustrative snippet. When executing:

~~~java
Battery battery = new Battery();
int snapshot = battery.getPercentage();  // snapshot = 75
battery.drain(10);

// snapshot is still 75; battery.getPercentage() is now 65
~~~

`getPercentage()` returns the **current value** of the `percentage` field; the `snapshot` variable holds a copy of the value `75`. A command that changes the field later does not automatically update the `snapshot` variable.

With primitives, there is no object "behind the result" for the caller to modify through the result. The caller can perform calculations with `snapshot`, but assigning `snapshot = 100` does not write back to `battery.percentage`.

### 3.1. The `return` Expression Must Be Compatible with the Declared Type

Java allows certain valid conversions in a return context according to the language rules. For example, an `int` can be **widened** to a `long`:

~~~java
long count() {
    int local = 42;
    return local;             // int -> long: valid
}
~~~

However, narrowing is not automatically accepted arbitrarily:

~~~java
int rounded() {
    double value = 2.7;
    // return value;          // Compile error: double -> int does not narrow automatically
    return (int) value;       // Valid: returns 2 due to explicit cast
}
~~~

These examples are method fragments. When casting `double` to `int`, the fractional part is discarded according to Java's conversion rules, not rounded in the way users usually expect. Therefore, the name `rounded()` in the example only highlights a naming design mistake; if the real intention is rounding, use an appropriate rule such as `Math.round` and pay attention to the result type.

When designing a method, you should choose a declared return type that represents the **exact value domain**, avoiding casts that mask overflow errors or loss of precision.

### 3.2. Primitives Can Never Directly Return `null`

~~~java
int findQuantity() {
    // return null;          // Compile error
    return 0;
}
~~~

`0` is an actual value of type `int`, not necessarily synonymous with "not found". If the business domain needs to distinguish between "no quantity" and "quantity equal to 0", do not pick an arbitrary sentinel without defining a contract. You can use `OptionalInt`, a nullable `Integer` wrapper, a dedicated result type, or throw an exception when missing data is an error, depending on the API.

## 4. Returning a Reference: Sharing References Without Automatically Copying Objects

A method whose return type is a class, interface, array, or another reference type returns a **reference value**. That value can point to:

- An existing object held by a field of the class.
- An object newly created with `new`.
- An object retrieved from a cache, collection, or parameter.
- The receiving object itself via `this`, if the return type is compatible.
- No object at all, i.e., `null`.

Example:

~~~java
class City {
    String name;

    City(String name) {
        this.name = name;
    }
}

class TravelProfile {
    private final City home = new City("Huế");

    City getHome() {
        return home;          // returns a reference to the internal object
    }

    City copyHome() {
        return new City(home.name); // creates a new object
    }
}
~~~

Both methods have **the same `City` return type**, but different ownership contracts. `getHome()` exposes the internal mutable object; `copyHome()` creates an independent `City` object (in this example the String field is immutable, so copying the string does not cause mutable aliasing).

If the caller invokes:

~~~java
TravelProfile profile = new TravelProfile();
City shared = profile.getHome();
shared.name = "Đà Nẵng";
~~~

then the `City` object inside `profile` also changes its name to `"Đà Nẵng"`, because `shared` is **a reference to the exact internal object**. This part is a code fragment that must be placed inside a method.

Conversely:

~~~java
City independent = profile.copyHome();
independent.name = "Hà Nội";
// Does not modify profile's internal City object through independent
~~~

Remember: `return home;` **does not clone**, does not "freeze" the object, and does not transfer exclusive ownership to the caller. If the object is mutable, the caller can change the state of the object that both sides reference, depending on access rules.

### 4.1. Returning the Same Reference Received as a Parameter

~~~java
class TextOps {
    static StringBuilder appendBang(StringBuilder text) {
        text.append("!");
        return text;
    }
}
~~~

This is an illustrative snippet. `appendBang` both modifies the received object and returns **the same reference**. A method with a reference return is not by default a "query" or free of side effects; the intent must still be read from the contract.

Java also passes reference parameters **by value**. Reassigning the parameter inside the method, for example `text = new StringBuilder()`, does not make the caller's variable point to the new object; however, calling `text.append(...)` can modify the object referenced by both sides.

### 4.2. String Is a Reference, but Immutable

~~~java
class Message {
    private String text = "Xin chào";

    String getText() {
        return text;
    }
}
~~~

`getText()` returns a `String` reference, but `String` is immutable: the caller cannot directly modify the contents of the returned String object. Calling `returnedText.toUpperCase()` creates a result string (or may reuse the object if appropriate) without modifying the original String's contents.

**Do not infer "reference = mutable".** Mutability depends on the design of the class/data type. `String`, many records containing only immutable components, and immutable value objects can be returned by reference without exposing mutable state; arrays, `ArrayList`, and `StringBuilder` usually require more careful consideration.

## 5. `null` Is a Valid Result of a Reference Method

Example:

~~~java
class Directory {
    String findDisplayName(int id) {
        if (id == 7) {
            return "Lan";
        }
        return null;
    }
}
~~~

This is a simple API that uses `null` to indicate "not found". The method **is declared to return `String`**; it does not need to declare an additional `null` type in order to return null.

Calling code should check before operating on the object:

~~~java
Directory directory = new Directory();

String name = directory.findDisplayName(9);
if (name != null) {
    System.out.println(name.length());
} else {
    System.out.println("Không tìm thấy");
}
~~~

If you skip the check and run `name.length()` when `name == null`, the program will throw `NullPointerException`. Operations that **access a method/field or an array through null** are common sources of errors.

Not every operation on a null variable throws an exception:

- `name == null` is valid and returns a boolean.
- `System.out.println(name)` prints the text `null` when `name` is null thanks to the appropriate overload of the print method.
- `name instanceof String` returns `false` if `name` is null.
- `Objects.equals(name, "Lan")` safely returns `false` when name is null.
- `name.length()` throws `NullPointerException` when name is null.

### 5.1. Missing, Empty, and Default Data Are Different Concepts

For `String`, the following cases have different meanings:

| Return value | Possible meaning |
| --- | --- |
| `null` | No object/result (per the API contract) |
| `""` | A String exists, but its length is 0 |
| `" "` | A String exists containing a single space |
| `"Lan"` | A String exists with content "Lan" |

Do not arbitrarily convert every `null` to `""` if missing data and empty data carry different meanings. Similarly, for collections, returning `Collections.emptyList()` or `List.of()` expresses "a result exists, but the list is empty" in many APIs; returning `null` can express "no result", but it also places a checking burden on the caller. Choose one contract and apply it consistently.

### 5.2. No Mandatory Nullability Declaration in Standard Java Types

A method declared as `String getName()` **can still return `null`** and be accepted by the standard Java compiler. Java 17 does not distinguish in ordinary type syntax between a "non-nullable" and a "nullable" `String`. Some projects use annotations such as `@Nullable` or `@NonNull` together with a static analyzer or conventions; its effectiveness depends on the library and tools, and not every annotation automatically blocks null at runtime.

If an API guarantees a non-null result, enforce that with validation and consistent implementation; if the result can be absent, document it clearly or represent it with an appropriate type.

## 6. Wrapper Types: When a Numeric Value Can Also Be `null`

Classes such as `Integer`, `Long`, `Double`, and `Boolean` are **reference types** corresponding to the primitives. Example:

~~~java
class QuizResult {
    Integer getScore(boolean submitted) {
        if (!submitted) {
            return null;       // not yet submitted
        }
        return 0;              // boxing int 0 -> Integer
    }
}
~~~

`getScore(false)` returns null; `getScore(true)` returns an `Integer` containing the value 0. This helps distinguish "no score yet" from "an actual score of 0".

Java has **autoboxing** and **unboxing**:

~~~java
Integer boxed = 10; // boxing from int to Integer
int unboxed = boxed; // unboxing from Integer to int
~~~

If the `boxed` variable is null, unboxing causes a `NullPointerException`:

~~~java
Integer missing = null;
// int count = missing; // Compiles if uncommented, but NPE at runtime
~~~

The issue can also happen **right in the return statement**:

~~~java
int score(Integer result) {
    return result; // compiler unboxes Integer -> int; NPE if result == null
}
~~~

These are illustrative code fragments that need to be inside a class. Distinguish the errors:

- `int get() { return null; }`: **compile error**, because null does not convert directly to a primitive.
- `int get(Integer boxed) { return boxed; }`: **compiles**, but **can fail at runtime** when unboxing null.

A method returning `Integer` does not mean it always creates a new object each time; the JVM may cache wrappers for certain values according to specification and implementation. Do not use `==` to compare the numeric meaning of two `Integer` instances. If both are non-null and you need a numeric comparison, you can use `intValue()` or `equals` per the contract; if either can be null, `Objects.equals(a, b)` provides a safe comparison.

## 7. Runnable Example: Three Result Forms, Aliasing, and null

The following program fully illustrates **primitive result**, **shared reference result**, **copied reference result**, **`null` and wrapper**.

Save as the file **`ReturnKindsDemo.java`**:

~~~java
public class ReturnKindsDemo {
    static final class Inventory {
        private int stock = 10;
        private final int[] bins = {2, 4};
        private final String name = "Kho A";

        int getStock() {            // primitive
            return stock;
        }

        String getName() {          // immutable reference
            return name;
        }

        int[] getLiveBins() {       // returns the same internal array
            return bins;
        }

        int[] getBinsCopy() {       // returns a new array
            return bins.clone();
        }

        String findLabel(boolean found) {
            return found ? "Đã tìm thấy" : null;
        }

        Integer findStock(boolean found) {
            if (!found) {
                return null;
            }
            return stock;          // int is boxed into Integer
        }
    }

    public static void main(String[] args) {
        Inventory inventory = new Inventory();

        int copiedStock = inventory.getStock();
        copiedStock = 99;
        System.out.println("Copied stock = " + copiedStock);
        System.out.println("Real stock = " + inventory.getStock());

        int[] live = inventory.getLiveBins();
        live[0] = 8;
        System.out.println("Live first = " + inventory.getLiveBins()[0]);

        int[] copy = inventory.getBinsCopy();
        copy[0] = 77;
        System.out.println("After copy edit = " + inventory.getLiveBins()[0]);

        System.out.println("Name = " + inventory.getName());
        System.out.println("Missing label = "
                + (inventory.findLabel(false) == null));

        Integer missingStock = inventory.findStock(false);
        Integer presentStock = inventory.findStock(true);
        System.out.println("Missing stock = " + (missingStock == null));
        System.out.println("Present stock = " + presentStock);
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 ReturnKindsDemo.java
java ReturnKindsDemo
~~~

**Exact stdout:**

~~~text
Copied stock = 99
Real stock = 10
Live first = 8
After copy edit = 8
Name = Kho A
Missing label = true
Missing stock = true
Present stock = 10
~~~

**Result-by-result analysis:**

1. `getStock()` returns primitive `int` 10. Assigning `copiedStock = 99` only modifies the caller's variable, so `getStock()` still returns 10.
2. `getLiveBins()` returns a reference to **the array inside Inventory**. `live[0] = 8` modifies the original array, so calling `getLiveBins()[0]` again sees 8.
3. `getBinsCopy()` creates another `int[]` array using `clone()`. Modifying `copy[0] = 77` does not alter the original array: the printed result is still 8.
4. `getName()` returns a `String` reference to "Kho A". String is immutable; merely returning the reference poses no risk of directly modifying the String's contents.
5. `findLabel(false)` returns `null`; the `== null` comparison returns true and does not dereference.
6. `findStock(false)` returns `null` as an `Integer` reference; `findStock(true)` boxes `int` 10 into `Integer`. Both cases match the declared return type.

This is a way to observe the different semantics yourself **without guessing "whether the object is copied or not"**: check whether the `return` expression performs `new`/`clone` or simply returns the existing reference. If the type is mutable and there is no copy, you must actively evaluate aliasing.

## 8. Returning Arrays/Collections: Protecting Internal Data

A getter sometimes looks read-only but exposes mutable state:

~~~java
import java.util.ArrayList;
import java.util.List;

class BadLibrary {
    private final List<String> books = new ArrayList<>();

    List<String> getBooks() {
        return books; // caller can do books.clear(), books.add(...)
    }
}
~~~

This is an illustrative declaration snippet. The caller can write `library.getBooks().clear()`, bypassing methods that check invariants. The `private` access level of the field is not enough protection if a method directly returns a reference to the collection.

A protected way to return the result:

~~~java
import java.util.ArrayList;
import java.util.List;

class Library {
    private final List<String> books = new ArrayList<>();

    List<String> getBooks() {
        return List.copyOf(books);
    }

    void addBook(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Tên sách rỗng");
        }
        books.add(title);
    }
}
~~~

With immutable `String` elements, `List.copyOf(books)` provides a list that cannot be modified through its API and reflects the contents at the time the result is created, unlike a getter returning `books` directly. Because the source list `books` here is mutable, the result does not share structural mutability with the source list. `List.copyOf` does not accept null elements; if the domain allows null in the list, a different mechanism must be designed accordingly.

**Watch out for shallow copies:** if `books` is a `List<Book>` and `Book` is mutable, the structural copy of the list still holds references to **the same `Book` instances**. The caller can modify element contents when `Book`'s API permits. Depending on the contract, you need to return an immutable DTO/record or an appropriate deep copy.

### 8.1. Differences Among Snapshot, View, and Direct Reference

| Return approach | Characteristics |
| --- | --- |
| `return mutableList;` | Directly returns the internal object; caller can mutate it if the API allows |
| `return Collections.unmodifiableList(mutableList);` | View that disallows modification through the view, but can reflect changes in the original list |
| `return List.copyOf(mutableList);` | Unmodifiable result that does not reflect subsequent structural updates of the mutable source |
| `return new ArrayList<>(mutableList);` | New array/list that is **mutable**, shallow copy of the elements |
| `return array.clone();` | New array, shallow copy; for primitive arrays, element values are independent |

Choose the return approach based on two questions: is the caller allowed to modify the result, and does the result need to **track live state** or must it be a **snapshot of state** at the time of the call? The method name and documentation should make this clear.

## 9. Using `Optional` When a Result Might Not Exist

Java provides `java.util.Optional<T>` as a **return value** type representing "has a result" or "has no result" without requiring the caller to dereference a `null` directly.

~~~java
import java.util.Optional;

class UserDirectory {
    Optional<String> findName(int id) {
        if (id == 7) {
            return Optional.of("Lan");
        }
        return Optional.empty();
    }
}
~~~

This is an illustrative declaration snippet. Usage:

~~~java
Optional<String> result = directory.findName(7);
String name = result.orElse("Khách");
System.out.println(name);
~~~

This part requires a `directory` variable referencing `UserDirectory` and must be placed inside a method. When `id == 7`, the result is `"Lan"`; if not found, `orElse("Khách")` returns the fallback `"Khách"`.

Commonly used methods:

- `Optional.of(value)`: requires value to be non-null, throws `NullPointerException` if null.
- `Optional.ofNullable(value)`: returns `Optional.empty()` when value is null, otherwise contains the value.
- `Optional.empty()`: represents no result.
- `optional.isPresent()` or `optional.isEmpty()`: checks whether a value is present/absent.
- `optional.orElse(defaultValue)`: returns the value if present, or an already-evaluated fallback.
- `optional.orElseGet(supplier)`: invokes supplier to produce a fallback **only when needed**.
- `optional.orElseThrow()`: throws `NoSuchElementException` if empty, or `orElseThrow(supplier)` for a custom error.
- `optional.map(fn)`: transforms the present value while preserving the empty state when absent.

**Do not return `null` from a method declared to return `Optional<T>`**: when data is missing, return `Optional.empty()`. If you return null for an `Optional`, you force the caller to perform a null check outside Optional and defeat the purpose of the contract.

`Optional<T>` is a reference type with an **Optional object** containing a reference or an empty state; you cannot use a primitive directly as a type argument such as `Optional<int>`. If you need an optional `int` value, consider `OptionalInt`.

### 9.1. Complete Example with Optional and OptionalInt

Save as the file **`OptionalResultDemo.java`**:

~~~java
import java.util.Optional;
import java.util.OptionalInt;

public class OptionalResultDemo {
    static Optional<String> findCity(int personId) {
        return personId == 7
                ? Optional.of("Hà Nội")
                : Optional.empty();
    }

    static OptionalInt findAge(int personId) {
        return personId == 7
                ? OptionalInt.of(21)
                : OptionalInt.empty();
    }

    public static void main(String[] args) {
        System.out.println("City = " + findCity(7).orElse("Không rõ"));
        System.out.println("Missing city = "
                + findCity(9).orElse("Không rõ"));

        System.out.println("Age = " + findAge(7).orElse(-1));
        System.out.println("Has missing age = "
                + findAge(9).isPresent());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 OptionalResultDemo.java
java OptionalResultDemo
~~~

Stdout:

~~~text
City = Hà Nội
Missing city = Không rõ
Age = 21
Has missing age = false
~~~

Here, methods whose data may be missing return an **empty Optional**, not null. The caller must decide how to handle the empty case; `orElse(-1)` is a fallback at the call site, **not a default age value automatically created by Java**.

### 9.2. When to Use `null`, Optional, or an Exception?

| Situation | Suggested return type | Reason |
| --- | --- | --- |
| Result always exists by invariant | `String` or the corresponding type, guaranteed non-null | Simple API, clear contract |
| Not found is a normal outcome | `Optional<T>` or `OptionalInt` | Caller handles presence explicitly |
| Legacy API specifies returning null | `T` may return null, clearly documented | Compatible with existing contract |
| Missing value is a contract or operation error | Can throw an appropriate exception | Avoids returning an ambiguous sentinel |
| Can return an empty result set | `List<T>` returning an empty collection | Easy to iterate, avoids frequent null-checks |

`Optional` is not a "cure-all for null": it is also a reference type and, as far as the language goes, can be assigned null, even though an API should not do so. Optional has its own overhead and intended usage, and is not necessarily appropriate for every field, every parameter, or every serialization format.

## 10. Distinguishing `null`, Exceptions, and a Sentinel Value

Consider a method to look up a balance. The options:

~~~java
// Option 1: -1 is a valid sentinel only if the entire contract defines -1 as invalid
int findBalanceOrMinusOne(int id) {
    return id == 7 ? 100 : -1;
}

// Option 2: Integer allows distinguishing null from 0
Integer findBalanceNullable(int id) {
    return id == 7 ? Integer.valueOf(100) : null;
}

// Option 3: OptionalInt makes a missing value an explicit case
java.util.OptionalInt findBalance(int id) {
    return id == 7
            ? java.util.OptionalInt.of(100)
            : java.util.OptionalInt.empty();
}
~~~

These are method fragments that can be placed inside a class. If a valid balance can be negative, choosing `-1` as a sentinel can cause bugs. An exception is appropriate when an invalid id is an exceptional condition under the contract, not necessarily when "not found" is an expected outcome.

**Consistency matters more than fashionable choices:** if an API already has a contract to return null, the caller must be guided on how to handle it; if a project standardizes on Optional for lookups, apply it consistently at the appropriate boundaries. Do not return `0` just to avoid null if `0` is a valid business value.

## 11. Returning `this`, New Objects, and Superclass/Interface-Typed References

The return value can be the current object itself:

~~~java
class Builder {
    private String text = "";

    Builder append(String part) {
        text += part;
        return this;
    }

    String build() {
        return text;
    }
}
~~~

This is an illustrative snippet. `append` returns **the `this` reference** to chain calls; it also mutates state, so it is not a pure query. `build()` returns a String reference to the current result; since String is immutable, the caller cannot directly modify the received contents.

A method can declare its return type as an **interface or superclass** and actually return a reference to an object of a compatible implementation/subclass:

~~~java
import java.util.ArrayList;
import java.util.List;

class Selection {
    List<String> values() {
        return new ArrayList<>(List.of("A", "B"));
    }
}
~~~

`List<String>` is the declared return type, whereas the actual object is an `ArrayList<String>`. The caller can use the APIs exposed through the `List` type. Returning an implementation object through an interface does not make the object immutable: `ArrayList` remains mutable if the caller performs operations permitted by the interface.

**Do not confuse runtime class with declared return type.** The compiler checks that the `return` expression is compatible with the declared type; the actual object may belong to a subtype.

### 11.1. Covariant Return When Overriding

For overridden instance methods, Java allows a subclass to return **a more specific reference type** under the return-type substitutability rule:

~~~java
class Animal { }

class Dog extends Animal { }

class Shelter {
    Animal adopt() {
        return new Animal();
    }
}

class DogShelter extends Shelter {
    @Override
    Dog adopt() {
        return new Dog();
    }
}
~~~

This is an illustrative snippet without a `main` method. `DogShelter.adopt()` returns `Dog`, which is subtype-compatible with `Animal`. You cannot arbitrarily change primitive types when overriding—for example, having the superclass return `int` while the subclass returns `long`—because primitive widening does not create covariant returns in overriding.

## 12. Generic Methods Whose Return Type Is a Type Parameter

A generic method can express its result type via a type parameter:

~~~java
class Results {
    static <T> T first(T first, T second) {
        return first;
    }
}
~~~

This is a declaration snippet. If you call `String name = Results.first("Lan", "Mai")`, the caller receives a `String`; if you call `Integer number = Results.first(1, 2)`, the caller receives an `Integer` wrapper through generic type inference/boxing.

Because **a regular generic type argument must be a reference type**, you cannot write `List<int>` or `Optional<int>`; use `List<Integer>`, `OptionalInt`, or an appropriate structure. A generic method returning `T` can return `null` if the method body does so and the contract allows it; a generic type **does not by itself guarantee non-null**.

You should also note type erasure: it affects the runtime representation and certain type checks, but it does not change the "return by reference value" principle for generic results.

## 13. Notes on Lifecycle and Results Pointing to Shared Objects

A returned object may still be referenced in multiple places: internal fields, caches, static fields, call parameters, or other objects. Therefore, returning an object **does not transfer exclusive ownership** by default.

Scenarios:

1. **Returning a DTO/record containing only primitives and Strings:** suitable for sharing if there are no mutable components.
2. **Returning a mutable `ArrayList` used internally:** the caller can modify the internal list outside your control.
3. **Returning a shallowly copied list containing mutable objects:** the inner elements can still be shared.
4. **Returning an `InputStream` or connection:** you need to specify clearly **who closes the resource**; merely returning the value does not transfer closing responsibility under the language rules.
5. **Returning a reference to an object that can be modified from another thread:** a query call returning the same object does not create an atomic snapshot and does not provide thread-safety guarantees.
6. **Returning null for a "not present" result:** the caller needs a handling branch or an explicit result wrapper.

For mutable objects, you should clearly specify **ownership**, *mutability*, copy count, thread-safety, and the lifecycle of the returned object. This is part of the **method contract** and cannot be inferred solely from the `return` syntax.

## 14. Returning Results in a Multithreaded Context

Example of a method:

~~~java
class Metrics {
    private int count;

    int currentCount() {
        return count;
    }

    void increment() {
        count++;
    }
}
~~~

`currentCount()` returns a primitive, so the caller receives a single-read copy; however, when multiple threads call `increment()` and `currentCount()` without synchronization, there are still issues of data race, visibility, and lost updates. **A primitive return does not automatically make a shared field thread-safe**.

If returning a mutable reference, the caller may also encounter concurrent updates to the object's contents. A solution matching the contract is needed: `synchronized`, locks, atomic variables, safely published immutable snapshots, or concurrent collections where appropriate.

Example of a simple immutable snapshot:

~~~java
record Status(int completed, int failed) { }

class StatusHolder {
    private volatile Status current = new Status(0, 0);

    Status snapshot() {
        return current;
    }

    void replace(Status next) {
        current = java.util.Objects.requireNonNull(next);
    }
}
~~~

This is an illustrative snippet. `snapshot()` returns a reference to the current `Status` record, published through a volatile field. Each record contains two primitive components and has no mutable nested objects in the example; a caller reading both values through **the same result variable** will see a consistent version. However, `replace` is not an atomic cumulative update: two writers computing a new state from an old snapshot can overwrite each other. If atomic read-modify-write is needed, use an appropriate synchronization mechanism.

## 15. Common Mistakes with Return Types

| Mistake | Consequence | How to understand/fix |
| --- | --- | --- |
| `int get() { return null; }` | Compile error | Primitives do not accept null |
| `int get(Integer x) { return x; }` when x is null | Runtime `NullPointerException` | Unboxing requires a non-null value |
| Assuming `return object;` automatically clones | Caller shares the existing object | Create a copy if independence is needed |
| Getter directly returns an internal array | Caller can modify the array | Defensive copy or read-only API |
| Using `==` to compare String contents | Identity comparison, error-prone | `equals` / `Objects.equals` |
| Always returning `0` when a number is not found | Confuses missing data with the value 0 | Optional/wrapper/result type |
| Method declares `Optional<T>` but returns null | Breaks the Optional contract | Return `Optional.empty()` |
| Thinking `String` is a primitive | Misunderstanding of references | String is an immutable class |
| Thinking `void` returns `null` | Wrong: void returns no value | Do not use a void call as a value-producing expression |
| Calling `toString()` on a nullable result | May throw NPE | Perform a null check or handle Optional |
| Using `new` inside a method and thinking the caller receives a copy of the parameter | Cannot be inferred | Check which exact object is created/returned |
| Returning a copied collection and assuming all elements were deep-copied | Mutable child objects are still shared | Design a snapshot/deep copy if needed |

### 15.1. Questions That Look Simple but Are Easy to Confuse

~~~java
String a = new String("Java");
String b = new String("Java");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
~~~

This is a fragment inside a method. The two `new String(...)` expressions here create two different String objects that have equal contents. If a method returns `a` the first time and `b` the second time, the declared return type is String in both cases, yet the identities of the results differ. Do not use `==` as a text content comparison operator.

Another example:

~~~java
int[] createArray() {
    return new int[]{1, 2, 3};
}
~~~

This is a method fragment: the `int[]` return type is a **reference type**, even though the elements are primitive `int` values. Each execution of `new int[]{...}` creates a new array object; this differs from `return sharedArray;`, which returns a reference to the existing array.

## 16. Self-Check

**Question 1.** Does the method `int answer() { return 42; }` return an `Integer` object or a primitive `int`?

**Answer:** It returns a primitive `int`; the caller can box it automatically if assigning the result to `Integer` in a compatible context.

**Question 2.** Does the method `String find() { return null; }` cause a compile error?

**Answer:** No. The declared return type is the reference `String`, so `null` is valid; the caller needs to handle the possibility of null.

**Question 3.** If `int[] getNumbers()` directly returns the internal array, can the caller modify the internal array?

**Answer:** Yes, if the caller holds the reference and the array is not copied; for example, `getNumbers()[0] = 9` will modify the shared array.

**Question 4.** `Integer getScore()` returns null; why can `int score = getScore();` throw `NullPointerException`?

**Answer:** Assigning to `int` triggers unboxing; a null reference cannot be unboxed.

**Question 5.** Should `Optional<String> findName()` return `null` or `Optional.empty()` when data is missing?

**Answer:** Return `Optional.empty()`. Returning null forces the caller both to check for null and to handle Optional, which contradicts the intended contract.

**Question 6.** If a method returns `new ArrayList<>(source)`, are the mutable elements inside deep-copied?

**Answer:** No. The new list copies the structure, while the element references may still point to the same objects.

**Question 7.** Are two calls to a method `getCount()` returning `int` guaranteed to yield the same number?

**Answer:** No. The field can change between the two calls due to another command or another thread; the method returns a copy **at the time of the read**, and does not guarantee that the state will remain unchanged forever.

**Question 8.** Does a `void save()` method return `null` when it finishes executing?

**Answer:** No. `void` means there is no result value; you cannot assign the result of calling `save()` to an `Object` or `String` variable.

### Checklist When Designing Methods That Return Results

1. **Confirm the return type:** primitive, reference, or `void`?
2. **Define the meaning of a missing result:** can it be `null`, or is an Optional, empty collection, exception, or dedicated result type needed?
3. **For references, define ownership:** is it an internal object, a snapshot, a copy, or a new instance?
4. **Evaluate mutability:** can the caller modify the returned object and break the class's invariants?
5. **Handle type conversions:** could any boxing/unboxing, widening, casting, or null-unboxing cause errors?
6. **Write the contract for the caller:** whether the value can be null, whether a resource needs to be closed, and whether the result is safe to use from another thread?
7. **Test both values and effects:** results are correct, not-found cases are handled, and no out-of-contract state changes occur.

Understanding `return` properly means understanding **the value returned**, **the object that a reference value points to**, and **the meaning of absence (`null`)**. These three points help you write clear Java APIs, avoid null bugs, and control state sharing among objects.
