# `null` Represents the Absence of an Object in Java

In Java, a **variable, field, parameter, or method result of a reference type** can take the value **`null`**. This value indicates that **the current reference does not point to any object or array**. It is not an object named `null`, not an empty string, not the number 0, and not a memory address that the program is allowed to manipulate directly.

This is a foundational concept of object-oriented programming: when using `Customer customer`, we have a **reference variable of type `Customer`**; that variable can point to an actual `Customer` or can be `null`. Declaring a reference type **does not by itself create an object**.

First example:

~~~java
class Customer {
    String name;
}

class Demo {
    void run() {
        Customer customer = null;        // Does not reference any object yet
        customer = new Customer();       // Now there is a Customer object
        customer.name = "Lan";          // Access a field on an actual object
        customer = null;                // The variable no longer points to that object
    }
}
~~~

This is a **class declaration snippet**, not yet a standalone runnable program. When `customer = null` is executed at the end, **there is no immediate command to destroy the object**: if other references to the `Customer` still exist, the object can still be used; if it is no longer reachable, the JVM may reclaim it later via the garbage collection mechanism.

This lesson uses Java 17+ and focuses on the meaning of `null` for references, how to detect and handle the absence of an object, common mistakes, and how to design clear API contracts.

## 1. Correctly Identifying Reference Variables and Objects

Compare:

~~~java
Customer a = null;
Customer b = new Customer();
Customer c = b;
~~~

In this fragment:

- `a` has the **declared type `Customer`**, but its value is `null`: it does not point to any object.
- `b` has the **declared type `Customer`** and points to the object just created by `new Customer()`.
- `c` holds a **copy of the reference value** of `b`, so `b` and `c` both point to **a single object**.

Conceptual diagram:

~~~text
a ----------> null                  (no target object)

b ------+
        +-----> Customer object     (a real object)
c ------+
~~~

There is no “null object” after the first arrow. `null` is the state of **having no referenced object**, rather than a special object with fields or methods.

### 1.1. A Reference Type Does Not Mean an Object Has Been Created

~~~java
String text = null;         // No String object via text
int[] values = null;        // No array object via values
Runnable task = null;       // No implementation object via task
Object item = null;         // No object via item
~~~

Even though the declared types are respectively a class, an array, an interface, and `Object`, the variables can all accept null.

In contrast:

~~~java
String empty = "";          // There is a String object of length 0
int[] zero = new int[0];    // There is an array object of length 0
Object object = new Object(); // There is an actual Object
~~~

`""` and `new int[0]` **are not null**. They represent real objects even though they carry no content data or elements.

| Expression | Is there a referenced object? | Meaning |
| --- | --- | --- |
| `String s = null;` | No | No String via variable `s` yet |
| `String s = "";` | Yes | Empty String |
| `int[] a = null;` | No | No array |
| `int[] a = new int[0];` | Yes | Array exists, 0 elements |
| `Object o = new Object();` | Yes | Real Object |
| `String s = "null";` | Yes | String consisting of the four letters `n`, `u`, `l`, `l` |

How `s` is named or what its data type is does not turn `null` into an object. Only expressions that create or retrieve a valid reference make a variable point to an object.

## 2. Where Can `null` Be Used?

**Reference types** in Java include class, interface, and array types. In addition, applicable type variables also belong to the reference type system. For them, `null` can be the value of a variable/parameter/field or a method result according to language rules.

~~~java
class Account {
    String owner;      // reference field, can be null
    int[] history;     // reference field, can be null
}

class Service {
    Account findAccount(boolean found) {
        return found ? new Account() : null;
    }

    void setAccount(Account account) {
        // Caller can pass null if the API does not reject it
    }
}
~~~

This is an illustrative class snippet.

### 2.1. Primitives Cannot Directly Hold the Value `null`

Java has eight primitive types: `byte`, `short`, `int`, `long`, `float`, `double`, `char`, and `boolean`. Primitive values are not references to objects, so they cannot be directly assigned null:

~~~java
// int count = null;       // Compile error
// boolean active = null; // Compile error
// double rate = null;    // Compile error
~~~

If you need an integer that can be “unknown”, one option is a nullable `Integer` (reference type) or `OptionalInt` at method boundaries; the choice depends on the API contract.

### 2.2. `null` Is a Special Literal, Not a Class Name

You can write:

~~~java
Object value = null;
String title = null;
int[] scores = null;
~~~

But you cannot declare a variable with the “`null` type” like:

~~~java
// null value = null; // Invalid
~~~

The Java specification refers to the *null type* to describe the type of the null literal, but **`null` is not a type name used by developers for declarations like `String` or `Object`**.

## 3. Default Field Values: Reference Fields Start as `null`

When creating an object normally with `new`, fields that are not explicitly initialized receive a default value based on their type.

| Field type | Default value |
| --- | --- |
| Primitive `int` | `0` |
| Primitive `long` | `0L` |
| Primitive `double` | `0.0` |
| Primitive `boolean` | `false` |
| Primitive `char` | Character code `'\u0000'` |
| Reference `String` | `null` |
| Reference `Customer` | `null` |
| Reference `int[]` | `null` |

Example:

~~~java
class Order {
    String orderCode;  // null
    Customer buyer;    // null
    int quantity;      // 0
}
~~~

`new Order()` creates **a real Order object**, yet inside it, `orderCode` and `buyer` have the value null. These are two different levels of meaning:

1. The reference to the real **Order object**.
2. The reference field **buyer** inside that object may not point to any `Customer`.

Diagram:

~~~text
order -----> Order object
             +----------------------+
             | orderCode = null     |
             | buyer = null         |
             | quantity = 0         |
             +----------------------+
~~~

**Do not jump to conclusions:** an `Order` object is not null just because one or more of its fields are null.

### 3.1. Local Variables Differ from Fields

Unlike instance/static fields, a **local variable** in a method cannot be read before it has been definitely assigned (*definite assignment*):

~~~java
class Example {
    String field; // Defaults to null

    void test() {
        String local;
        // System.out.println(local); // Compile error: local is not initialized

        local = null;                 // Now assigned
        System.out.println(local == null);
    }
}
~~~

The Java compiler **does not automatically assign null for you to read** from a newly declared, unassigned local variable. After you explicitly assign `local = null`, reading it becomes valid with respect to definite assignment.

## 4. `null` in Arrays: A Null Array Differs from a Null Element

Arrays are objects in Java. A field/variable of an array type can be null, yet **an already created array** can still contain null elements.

~~~java
String[] names = null;             // No array object
String[] slots = new String[3];    // There is an array of three reference slots
int[] counts = new int[3];        // There is an array of three int values
~~~

For `slots`, each element of type `String` is initialized by default to null: `slots[0] == null` is true. For `counts`, the primitive `int` elements are initialized to 0.

Difference:

~~~java
// names.length;      // NullPointerException if executed because names == null
int size = slots.length;     // 3: the array object exists
String first = slots[0];     // null: the reference element does not have a String yet
int firstCount = counts[0]; // 0: default primitive element
~~~

A non-null array **does not guarantee that every reference element is non-null**. If you immediately process `slots[0].length()`, you will still encounter a `NullPointerException` because `slots[0] == null`.

## 5. Null Only Causes an NPE When an Operation Requires a Target Object

~~~java
String name = null;
System.out.println(name == null); // true, no dereference
// name.length(); // If executed, throws NullPointerException
~~~

This is a fragment inside a method. `null` has no receiver object for instance field/method or array access, yet **comparing against null** does not dereference and is therefore safe. `System.out.println(name)` can still print the text `null`; it does not create a String object for the variable name.

If null is valid, the code can use `name != null && !name.isBlank()`: the `&&` operator short-circuits. If null **is not allowed** by the contract, validate at the API boundary, such as `Objects.requireNonNull(name)`, instead of silently using a semantically wrong empty value.

Detailed NPE scenarios including nested dereferencing, nullable array slots, auto-unboxing, and bound method references belong to the lesson on **scenarios that cause NullPointerException**. The current lesson keeps the focus on the meaning of `null` as a **reference value pointing to no object**, rather than the full NPE debugging strategy.

## 6. Complete Example: null Means No Object, Not an Empty Object

Create the file **`NullReferenceDemo.java`**:

~~~java
import java.util.Objects;

public class NullReferenceDemo {
    static final class Customer {
        private final String name;

        Customer(String name) {
            this.name = Objects.requireNonNull(name, "name");
        }

        String display() {
            return "Customer: " + name;
        }
    }

    static Customer find(boolean found) {
        return found ? new Customer("Lan") : null;
    }

    public static void main(String[] args) {
        Customer present = find(true);
        Customer missing = find(false);

        System.out.println("present = " + present.display());
        System.out.println("missing == null = " + (missing == null));
        System.out.println("missing instanceof Customer = "
                + (missing instanceof Customer));

        System.out.println("same reference = "
                + (present == find(true)));

        Customer alias = present;
        System.out.println("alias == present = "
                + (alias == present));

        try {
            System.out.println(missing.display());
        } catch (NullPointerException ex) {
            System.out.println("NPE from dereference");
        }

        String[] names = new String[2];
        int[] quantities = new int[2];

        System.out.println("array exists = " + (names != null));
        System.out.println("first element null = " + (names[0] == null));
        System.out.println("first primitive = " + quantities[0]);

        Customer saved = present;
        present = null;

        System.out.println("present cleared = " + (present == null));
        System.out.println("saved still works = " + saved.display());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 NullReferenceDemo.java
java NullReferenceDemo
~~~

**Exact stdout:**

~~~text
present = Customer: Lan
missing == null = true
missing instanceof Customer = false
same reference = false
alias == present = true
NPE from dereference
array exists = true
first element null = true
first primitive = 0
present cleared = true
saved still works = Customer: Lan
~~~

Explanation:

1. `find(true)` creates a `Customer` object; `find(false)` returns null. The **declared return type `Customer`** allows both outcomes.
2. `missing == null` is true, whereas `missing instanceof Customer` is false because null is not an instance of a class.
3. `present == find(true)` is false: the second call to `find(true)` executes `new Customer("Lan")`, creating a different object even though the name is the same `"Lan"`.
4. `alias = present` copies the reference to the **same Customer**; therefore, `alias == present` is true.
5. `missing.display()` causes an NPE because the receiver is null; the example intentionally catches the error and prints a stable message, instead of relying on the wording of the exception.
6. `new String[2]` creates a real array, but the String elements are initially null; `new int[2]` creates a real array with int elements initially set to 0.
7. `present = null` only changes the value of the variable `present`. `saved` still points to the original Customer and can call `display()`. **There is no operation to destroy the Customer when setting present to null**.

Another important check: two objects with the same data do not necessarily have the same identity. For the `Customer` type in the example, `==` only asks whether they are the same object; it must not be used to infer whether the contents of two customers are the same.

## 7. `null` Differs from `0`, `false`, Empty Strings, and Empty Collections

An API must distinguish between **having no object** and **having an object with no content**.

| Result | State that can be expressed |
| --- | --- |
| `null` | No object/result according to the contract |
| `""` | There is a String with 0 characters |
| `"null"` | There is a String consisting of the text “null” |
| `new int[0]` | There is an array, length 0 |
| `List.of()` | There is an unmodifiable List that is currently empty |
| `Integer.valueOf(0)` | There is an Integer object holding the number 0 |
| `Boolean.FALSE` | There is a Boolean wrapper representing false |

Therefore, `null` should not be automatically replaced with `""` if “no name entered yet” and “an empty name was entered” carry different business meanings. Similarly, a quantity of 0 can be a valid value and **is not automatically equivalent** to “unknown quantity”.

For a method querying a list, returning an **empty collection** usually keeps iteration simple for the caller and avoids null-checks if the contract means “no elements found”. For a method finding **a single object**, representing “not found” with null or `Optional<T>` should be considered based on the API.

## 8. Assigning `null` Does Not Destroy an Object

A common misconception:

~~~java
Customer first = new Customer("Lan");
Customer second = first;

first = null;
// second still points to the original Customer
~~~

Assigning `first = null` only changes the value of the **variable first**. The object referenced by `second` is not thereby deleted and does not lose its data.

Key points:

- An object can be referenced from multiple variables/fields/collections at the same time (*aliasing*).
- Assigning null to one variable **does not modify other variables** even if they previously pointed to the same object.
- An object that is no longer reachable through any appropriate strong reference path can become eligible for collection; **there is no guarantee that it is collected immediately** when the assignment statement executes.
- Garbage collection is managed by the JVM; do not use `x = null` as a mechanism to close files/sockets/database connections or as a replacement for `close()` and `try-with-resources`.
- If an object is still held in a static collection or a listener registry, assigning null to a local variable is usually not enough to sever the reference path from that registry.

Distinguish the **lifetime of a reference value** from the **lifetime of the actual object** and from the **lifetime of resources outside the JVM**.

## 9. Comparing `null` with `==`, `equals`, and `Objects.equals`

### 9.1. `== null` Is a Direct Check

~~~java
String first = null;
String second = "Java";

System.out.println(first == null);   // true
System.out.println(second == null);  // false
~~~

This is a fragment inside a method. For references, `==` compares **reference values**, so checking `ref == null` is completely appropriate.

### 9.2. Do Not Call `equals` on a Potentially Null Reference

~~~java
String name = null;
// name.equals("Lan"); // NPE if executed
~~~

If the goal is to check content using String, you can write:

~~~java
boolean match = "Lan".equals(name); // false when name == null
~~~

Inverting the receiver on the literal works when the other side is always a non-null String literal, but do not treat that as a general rule for every type or every comparator.

### 9.3. `Objects.equals` Handles Null on Both Sides

~~~java
import java.util.Objects;

class TextCompare {
    static boolean same(String left, String right) {
        return Objects.equals(left, right);
    }
}
~~~

`Objects.equals(null, null)` returns true; `Objects.equals(null, "A")` returns false; `Objects.equals("A", "A")` returns true according to the `String.equals` contract. It handles null with the logic: same reference, or the first side is non-null and its `equals` content matches.

**Do not confuse equality with object identity.** `Objects.equals` relies on the data type's `equals` implementation when needed; two distinct objects with equal content can yield true. `==` on two non-null references is only true if they point to the same object.

## 10. `null` in the `instanceof` Operator and Java 17 Pattern Matching

In Java 17:

~~~java
Object value = null;

System.out.println(value instanceof String); // false

if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Because `value == null`, the `instanceof` condition is false and the `if` branch does not execute. The pattern variable `text` is only usable at valid locations when the condition matches successfully. This is a way to check both the type and a non-null reference simultaneously in appropriate contexts.

However, `instanceof` does not replace every null-check: if you only need to know whether a reference holds an object without caring about the runtime type, `value != null` is simpler and expresses the intent directly.

## 11. Null Parameters: Passing a Null Reference Does Not Create an Object

A method declaring a reference-type parameter can receive null:

~~~java
class Greeter {
    static String greeting(String name) {
        if (name == null) {
            return "Chào khách";
        }
        return "Chào " + name;
    }
}
~~~

Calling `Greeter.greeting(null)` is valid because `String` is a reference type and the method defines a handling path when no name is provided.

However, some methods **strictly require an object**. In that case, null should be rejected at the boundary:

~~~java
import java.util.Objects;

class PaymentRequest {
    private final String accountId;

    PaymentRequest(String accountId) {
        this.accountId = Objects.requireNonNull(
                accountId, "accountId");
        if (accountId.isBlank()) {
            throw new IllegalArgumentException("accountId rỗng");
        }
    }
}
~~~

`Objects.requireNonNull` throws `NullPointerException` when the input is null; afterward, the constructor checks for blankness according to the contract. This is an example of **validation**: knowing a reference type can be null does not mean the API is required to **accept** null.

### 11.1. Java Passes Arguments by Value, Including the Value null

~~~java
class ReferenceOps {
    static void replace(StringBuilder builder) {
        builder = null; // Only reassigns the local parameter
    }
}
~~~

If the caller has a `StringBuilder` object and calls `replace(builder)`, the method receives a **copy of the reference value**. Assigning null to the parameter **does not** make the caller's reference variable null.

Conversely, if the method receives a non-null reference and calls `builder.append("!")`, it modifies the object referenced by both caller and callee; that is an effect on the **object**, not changing the caller's variable.

## 12. Returning `null` from a Method

A method returning a reference type can return null when the contract allows it:

~~~java
class Directory {
    String findName(int id) {
        if (id == 7) {
            return "Lan";
        }
        return null; // Not found
    }
}
~~~

When the caller receives the result:

~~~java
String name = directory.findName(99);

if (name == null) {
    System.out.println("Không tìm thấy");
} else {
    System.out.println(name.toUpperCase());
}
~~~

This is a fragment inside a method with an appropriate `directory` variable. If you skip the check and write `directory.findName(99).toUpperCase()`, the `toUpperCase()` call has a null receiver and throws an NPE.

**The declared return type `String` does not automatically promise non-null.** Java 17 does not have standard type syntax enforcing a distinction between `String?` and `String` like some other languages; some static analysis tools use `@Nullable`/`@NonNull` annotations depending on the ecosystem, but they are not automatically enforced by the standard Java compiler as a universal language feature.

For primitive types, `int find() { return null; }` is a **compile error**; `null` cannot be directly converted into an `int`.

## 13. Wrappers and Auto-Unboxing: null Can Cause an NPE Even When the Assignment Compiles

`Integer` is a **reference type** corresponding to primitive `int`, so an `Integer` variable can be null:

~~~java
Integer count = null;
~~~

However, converting `Integer` to `int` (*unboxing*) needs to extract the number from the wrapper. If `count == null`, unboxing causes an NPE:

~~~java
Integer count = null;

// int number = count; // Compiles, but throws NPE at runtime
~~~

The error can also occur in arithmetic expressions:

~~~java
Integer value = null;

// int next = value + 1;    // NPE due to unboxing value
// if (value > 0) { }       // NPE due to unboxing
~~~

The difference is very important:

| Code snippet | Result |
| --- | --- |
| `int n = null;` | Compile error |
| `Integer n = null;` | Valid, n holds null |
| `Integer n = 5;` | Valid, boxing |
| `int x = n;` when n is 5 | Valid, unboxes to 5 |
| `int x = n;` when n is null | Runtime NPE |
| `n == null` | Valid for an Integer reference |

If an API uses `Integer` to represent “no number yet”, check for null **before computing or unboxing**. Do not default to using `0` in place of “unknown” if they are two different states.

## 14. `Optional<T>`: Explicitly Representing an Absent Result

Java provides `java.util.Optional<T>` to represent a reference result that **has** or **does not have** a value, which is especially useful in certain search/query APIs.

~~~java
import java.util.Optional;

class UserRepository {
    Optional<String> findName(int userId) {
        if (userId == 7) {
            return Optional.of("Lan");
        }
        return Optional.empty();
    }
}
~~~

When the caller invokes `findName(99)`, the result is **an empty Optional**, not null. Usage:

~~~java
String name = repository.findName(99).orElse("Khách");
~~~

This fragment requires an appropriate `repository` variable. `orElse("Khách")` returns the fallback when the Optional is empty; the caller does not need to dereference a null String before handling the absent case.

Some Optional APIs to remember:

| API | Meaning |
| --- | --- |
| `Optional.of(value)` | Creates an Optional with a value, requiring value to be non-null |
| `Optional.ofNullable(value)` | Null becomes an empty Optional |
| `Optional.empty()` | Case with no result |
| `isPresent()` / `isEmpty()` | Checks whether a value is present/absent |
| `orElse(defaultValue)` | Gets the value or fallback |
| `orElseGet(supplier)` | Runs the supplier to create the fallback only when the Optional is empty |
| `orElseThrow()` | Returns the value or throws an exception if empty |
| `map(fn)` | Transforms the value if present, keeping the empty state when absent |

**Do not return `null` from a method with return type `Optional<T>`:** the caller expects a non-null Optional object and may call `isPresent`/`orElse` immediately. If the method returns null, that very call causes an NPE, defeating the design purpose.

`Optional` is also a reference type; Java does not prevent an Optional variable from being assigned null by incorrect code, so the **code contract** remains important. The generic `Optional<int>` is invalid because a generic type argument requires a reference type; use `OptionalInt` when appropriate.

Not every nullable variable, field, or parameter needs to be wrapped in Optional. Optional is usually best suited for **return types**, depending on API style and the corresponding costs/limitations.

## 15. Complete Example: APIs Returning null, Optional, and Unboxing

Create the file **`NullContractDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class NullContractDemo {
    record User(String name) {
        User {
            Objects.requireNonNull(name, "name");
            if (name.isBlank()) {
                throw new IllegalArgumentException("Tên rỗng");
            }
        }
    }

    static User findNullable(int id) {
        return id == 7 ? new User("Lan") : null;
    }

    static Optional<User> findUser(int id) {
        return Optional.ofNullable(findNullable(id));
    }

    static String labelOrDefault(String input) {
        return input == null ? "unknown" : input;
    }

    public static void main(String[] args) {
        System.out.println("found = "
                + findUser(7).map(User::name).orElse("N/A"));
        System.out.println("missing = "
                + findUser(8).map(User::name).orElse("N/A"));
        System.out.println("label = " + labelOrDefault(null));

        Integer optionalCount = null;
        try {
            int count = optionalCount; // Unboxing null
            System.out.println(count);
        } catch (NullPointerException ex) {
            System.out.println("unbox null = NPE");
        }

        Map<String, String> values = new HashMap<>();
        values.put("presentNull", null);

        System.out.println("get absent null = "
                + (values.get("missing") == null));
        System.out.println("key exists with null = "
                + values.containsKey("presentNull"));
        System.out.println("key absent = "
                + values.containsKey("missing"));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 NullContractDemo.java
java NullContractDemo
~~~

**Exact stdout:**

~~~text
found = Lan
missing = N/A
label = unknown
unbox null = NPE
get absent null = true
key exists with null = true
key absent = false
~~~

Explanation:

1. `findNullable(7)` creates `User("Lan")`; `findNullable(8)` returns null. `findUser` turns the two results into an Optional with a value or an empty Optional.
2. `map(User::name)` calls the accessor only if a User is present; `orElse("N/A")` handles a missing User with a fallback.
3. `labelOrDefault(null)` accepts a null parameter, yet has a handling branch and returns `"unknown"` without attempting to access a field/method on null.
4. `Integer optionalCount = null` is valid because Integer is a reference type. The statement `int count = optionalCount` attempts to unbox null and throws an NPE; the example catches the error to produce stable stdout.
5. For `HashMap`, `get("missing")` returns null when there is no mapping. `get("presentNull")` will also return null because the map allows null values, **even though the key actually exists**. `containsKey` helps distinguish the two cases when needed.

**Do not generalize HashMap's rules to every Map implementation**: some maps such as `ConcurrentHashMap` do not allow storing null keys or null values. Specific collection APIs have their own null policies; check the contract of the type being used.

## 16. `null` in Overload Resolution: A Call Can Be Ambiguous

The null literal is compatible with multiple reference parameter types, so an **ambiguous overload** can occur:

~~~java
class Formatter {
    static String describe(String value) {
        return "String";
    }

    static String describe(Integer value) {
        return "Integer";
    }

    static void test() {
        // describe(null); // Compile error: ambiguous overload

        System.out.println(describe((String) null));
        System.out.println(describe((Integer) null));
    }
}
~~~

This is an illustrative declaration without `main`. Both overloads **are validly declared** because their parameters have different types, yet the call `describe(null)` cannot choose between `String` and `Integer` since they have no subtype relationship to make one method more specific.

Using a cast or a parameter expression that already has a specific type can identify which overload to invoke. However, **casting null to String does not create a String object**: `(String) null` is still the value null, just with a more explicit type context for overload selection.

An overload with an `Object` parameter and an overload with a `String` parameter normally select `String` when null is passed because `String` is more specific than `Object` under the most-specific rule. However, you should not design too many confusing nullable overloads only to force the caller to cast every time.

## 17. `null` in String Concatenation Does Not Mean There Is a String Object

Expression:

~~~java
String missing = null;

String result = "name=" + missing;
System.out.println(result); // name=null
~~~

In a string concatenation context, Java converts the representation of the null reference value into the text `"null"` in the result. That **does not change the variable `missing`** and does not turn it into a String object with content `"null"`.

Distinguish:

~~~java
String first = null;
String second = "null";

System.out.println(first == null);   // true
System.out.println(second == null);  // false
~~~

`first` does not point to an object, whereas `second` holds a String object containing four characters. If you want to display a friendlier, more meaningful label, do not rely on printing null as the text `"null"`; handle it with a fallback or a UI placeholder, such as `"Chưa có tên"`.

## 18. Null and Collection APIs

There is no single rule for every collection/map:

- `ArrayList` normally allows null elements.
- `List.of(...)` does not accept null elements; `List.of("A", null)` throws an NPE.
- `List.copyOf(collection)` also does not accept null elements, and returns an unmodifiable List.
- `HashMap` allows null keys and null values according to its contract.
- `ConcurrentHashMap` does not allow null keys or null values.
- `Collections.emptyList()` and `List.of()` return **real empty lists**, not null.

If a class's API specifies “the list is never null”, the constructor should validate/copy the input and the getter should return an empty list when there are no elements, rather than returning null unexpectedly:

~~~java
import java.util.List;

class Playlist {
    private final List<String> songs;

    Playlist(List<String> songs) {
        this.songs = List.copyOf(songs);
    }

    List<String> songs() {
        return songs;
    }
}
~~~

This is an illustrative snippet. For a list of immutable Strings, `List.copyOf` helps keep the data structurally unmodified by the caller. If the constructor receives null or a null element, it throws an NPE instead of creating an object in an unspecified state; that is behavior that should be documented in the contract.

For a list containing mutable objects, `List.copyOf` only creates an unmodifiable structural snapshot; it **does not automatically deep-copy all child objects**.

## 19. When Should null Be Used and When Should It Be Avoided?

Null is a normal part of Java. It is not “bad” in every context; the problem is an **unclear contract** or **failing to check where needed**.

| Case | Usually suitable option | Considerations |
| --- | --- | --- |
| Truly optional field | Nullable reference, or another data model with a contract | Every usage site must handle absence |
| Constructor requiring mandatory information | `Objects.requireNonNull` and validation | Reject early, avoiding an object with broken invariants |
| Query that may find no single result | `Optional<T>` or nullable `T` depending on the API | Choose consistently |
| Returning multiple results with no items | Empty list/collection | Caller does not need to check for null to iterate |
| Missing primitive value | `OptionalInt`, wrapper, or result type | Distinguish missing data from the number 0 |
| Serious business error | Exception or result type with an error state | Do not mask errors with an ambiguous null |
| External input (JSON/database/form) | Validate at the boundary and convert to a valid model | Prevent unexpected nulls from spreading into the core |
| Data to be cached but not created yet | Nullable field or controlled lazy initialization | Must consider concurrency and cache invalidation |

An API should state clearly: does null indicate **not found**, **not loaded yet**, **not applicable**, or **error**? These meanings are different. If they all share the same null, it is very hard for the caller to know what action to take. You can use an enum, a sealed hierarchy, a result record, or an appropriate exception when multiple states need to be distinguished.

## 20. Defensive Null Checking and the “Fail Fast” Principle

If a method strictly requires an object:

~~~java
import java.util.Objects;

class Receipt {
    private final String orderId;

    Receipt(String orderId) {
        this.orderId = Objects.requireNonNull(
                orderId, "orderId");
    }

    String orderId() {
        return orderId;
    }
}
~~~

The constructor fails immediately when the input is null, instead of creating a `Receipt` containing null and causing an NPE in a method far from where it was created. This is **fail fast**: detecting a contract violation at the nearest boundary.

For a value that may be missing and is allowed by the contract:

~~~java
class ReceiptLabel {
    static String display(String customerName) {
        if (customerName == null || customerName.isBlank()) {
            return "Khách";
        }
        return customerName;
    }
}
~~~

The condition uses short-circuiting `||`: if the name is null, Java does not call `customerName.isBlank()`. This is a legitimate handling approach, because null has meaning as one of the accepted input states.

**Do not catch `NullPointerException` broadly as a substitute for null-checks.** Catching NPE too broadly can hide unrelated dereference bugs, making troubleshooting harder. Only catch it when you genuinely need to handle an error per contract or demonstrate the mechanism as in the programs above.

## 21. Some Advanced Pitfalls

### 21.1. `this` Inside an Instance Method Is Not null

When an instance method is executing normally on a real object, `this` represents that receiver object, not a null reference. However, the object's **fields** can still be null:

~~~java
class Holder {
    String text; // defaults to null

    int length() {
        // this is the current Holder object, yet this.text can still be null
        return this.text.length();
    }
}
~~~

The error in `this.text.length()` comes from `this.text == null`, not from `this == null`. If you call `holder.length()` while `holder` is null, the method body does not even begin; dereferencing the receiver happens at the call site.

### 21.2. Multi-Level Access Chains

~~~java
customer.getAddress().getCity()
~~~

Can throw an NPE if `customer` is null or `getAddress()` returns null. That does not mean `getCity()` is wrong; the error may originate at **an earlier reference link**. Design domain invariants, nullable contracts, and APIs so users know which link is allowed to be missing.

### 21.3. Null in switch

With the standard `switch` syntax in Java 17, a `switch` on a null selector reference normally throws an NPE; do not assume Java automatically routes null to the `default` branch:

~~~java
String status = null;

// switch (status) {
//     default -> System.out.println("Khác");
// }
// When executing switch on a null status with this syntax: NPE
~~~

This is an incomplete snippet to explain behavior; handle null before `switch` if it is a valid input case. Some newer Java versions extend pattern matching for switch, but do not use knowledge of preview features or other language versions to draw incorrect conclusions about standard Java 17 code.

### 21.4. Null and Generic Collections

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
names.add(null);
~~~

This is valid with `ArrayList` even though the elements are declared with type `String`. Generics check the type of reference values; they **do not automatically make every element non-null**. If your class requires an invariant of “no null elements”, validate them or use a collection API whose contract rejects null.

### 21.5. Null in Multithreaded APIs

A reference field read and written by multiple threads can transition from an object to null or vice versa. Using null as a state signal does not automatically provide **visibility** or **atomicity** for a multi-step protocol. You need `volatile`, an atomic reference, a lock, or an appropriate synchronization tool depending on the requirements.

For example, `volatile Service current` guarantees visibility semantics for reading/writing that **reference field** itself, yet does not automatically make all mutable fields inside `Service` thread-safe. Do not rely on `if (current != null) current.run()` as a no-NPE guarantee on a field that another thread could set to null between the two reads; capture the reference value into a local variable and design appropriate lifecycle/synchronization.

## 22. Common Misconceptions

1. **“Null is an empty object.”** False. Null represents **having no referenced object**; an empty object is still a real object.
2. **“Declaring `Customer c;` automatically creates a Customer.”** False. An uninitialized reference field has the default value null; a local variable that has not been definitely assigned cannot be read.
3. **“`new String[3]` is null because all three elements are null.”** False. The array exists; only the reference elements inside it are initially null.
4. **“`null` and `0` are the same.”** False. `0` is a primitive value; null is for references.
5. **“Assigning `x = null` deletes the object immediately.”** False. It only changes one reference; the object may still have aliases, and GC is not guaranteed to run immediately.
6. **“`x == null` causes an NPE when x is null.”** False. This is a safe comparison.
7. **“`x.equals(y)` is safe even if x is null.”** False. A null receiver causes the instance method call to fail.
8. **“The String `"null"` is null.”** False. This is a String object whose content has four characters.
9. **“The `Integer` type always holds a number like `int`.”** False. Integer is a reference type and can be null; unboxing null causes an NPE.
10. **“Returning `Optional.empty()` is the same as returning null.”** False at the API level: an empty Optional is still a non-null Optional value with methods to handle the absent case.
11. **“Every collection accepts null elements.”** False. The policy depends on the implementation/API.
12. **“`ref instanceof Type` with null causes an NPE.”** False. A normal `instanceof` expression returns false when the reference is null.
13. **“If `ref != null`, all fields inside ref are non-null.”** False. The object exists, yet it can contain null fields.
14. **“If the result type is `String`, the compiler guarantees the method returns a non-null String.”** False. Java 17 allows `return null` for reference types.
15. **“Null can be used to replace every error state.”** You should not do this: it cannot distinguish between not found, not loaded yet, missing permissions, or system failure.
16. **“There is no need to check for null after `Map.get` because the map has the key.”** For maps that allow null values, `get` returns null even when a mapping exists; you need to understand the policy and use `containsKey` when distinguishing them is needed.
17. **“Assigning null to a parameter inside a method changes the caller's variable to null.”** False. Java passes a copy of the reference value.
18. **“Simply adding `volatile` to a reference is enough to make all child objects safe.”** False. It does not automatically synchronize operations on the object's contents.

## 23. Self-Check Exercises

**Question 1.** Does `Customer c = null;` create a Customer object?

**Answer:** No. Variable `c` has type `Customer` but its value is null, pointing to no object.

**Question 2.** For `Customer c = new Customer();`, can `c.name == null` be true?

**Answer:** Yes. The `Customer` object exists, but an explicitly unassigned reference field `name` defaults to null.

**Question 3.** `String[] words = new String[2];`. What are the expressions `words == null` and `words[0] == null` respectively?

**Answer:** False and true. The array has been created; the first String element initially does not reference a String object.

**Question 4.** For `int[] nums = new int[2];`, is `nums[0] == null`?

**Answer:** An `int` element cannot be compared directly with null. Element `nums[0]` holds the primitive value 0.

**Question 5.** Why can `Integer boxed = null; int n = boxed;` cause an error?

**Answer:** The boxing wrapper `Integer` is a reference type and allows null; assigning it to `int` requires unboxing, and null cannot be unboxed, which causes an NPE.

**Question 6.** Does `String s = null; if (s != null && s.length() > 0) ...` call `length()`?

**Answer:** No. `&&` short-circuits, so the second operand does not execute when `s != null` is false.

**Question 7.** Does `String s = "null";` make `s == null` true?

**Answer:** No. `s` points to an actual String object containing the text `"null"`.

**Question 8.** Does assigning `first = null` while `second == first` previously make `second` null as well?

**Answer:** No. If `second` and `first` initially pointed to the same object, reassigning `first` only changes the value of variable `first`; `second` retains the old reference.

**Question 9.** What should a method declared as `Optional<String> find()` return when nothing is found?

**Answer:** `Optional.empty()`, not null, to preserve the Optional contract.

**Question 10.** Why can `describe(null)` be ambiguous when overloads `describe(String)` and `describe(Integer)` exist?

**Answer:** The null literal is compatible with both reference parameter types, and these two types do not determine a more specific overload according to the relevant subtype order; the compiler cannot make a unique selection.

**Question 11.** Why does `map.get("missing") == null` not necessarily mean the key does not exist?

**Answer:** The Map implementation might allow mapping a key to a null value. With `HashMap`, use `containsKey` if you need to distinguish an absent key from a present-null mapping.

**Question 12.** Does `String text = null; System.out.println("text=" + text);` turn `text` into the String `"null"`?

**Answer:** No. The resulting string contains the text `"null"` for display, but the variable `text` remains null.

## 24. Checklist When Designing and Using Nullable References

1. **Identify the type:** is this a primitive or a reference? Only references can hold null directly.
2. **Define the absent state:** what business meaning does null have, or is it invalid input data that must be rejected?
3. **Distinguish an object from its fields:** a non-null object does not prove that every field/element is also non-null.
4. **Check before dereferencing:** especially in chains like `a.getB().getC()` and wrapper unboxing.
5. **Use short-circuiting properly:** `&&` and `||` help guard method-calling branches when conditions are written correctly.
6. **Do not use ambiguous sentinels:** `0`, `""`, an empty collection, and null are different states.
7. **Establish clear API contracts:** which methods can return null, which return Optional, and which promise non-null?
8. **Protect invariants in the constructor:** use validation such as `Objects.requireNonNull` for mandatory fields.
9. **For collections, check the specific contract:** `HashMap`, `List.of`, and `ArrayList` do not have the same null policy.
10. **With aliasing, remember that null does not destroy the object:** reassigning one reference does not alter the remaining references.
11. **With concurrency, do not use null as a signal without proper synchronization.**
12. **Test both object-present and object-absent branches:** do not test only non-null cases; test null arrays, null elements, unboxing, and missing results as well.

**Conclusion:** `null` is **the reference value representing “no object is being pointed to”**. It is not an empty object or the number 0. Writing safe Java requires distinguishing a **reference variable**, the **referenced object**, and the **fields/elements inside an object**, while clearly expressing in the API when absence is valid and when it must be rejected. Once you understand this, object creation, passing/receiving references, and handling `NullPointerException` become easier to predict and control.
