# Scenarios That Cause `NullPointerException` and How to Prevent It in Java

In Java, a **reference variable** can hold a reference to an object or the special value `null`. When a program attempts to use `null` where an object is required — such as reading a field, calling an instance method, accessing an array element, or automatically converting a wrapper to a primitive — Java can throw a **`NullPointerException` (NPE)**.

Example:

~~~java
String title = null;
System.out.println(title.length()); // NullPointerException.
~~~

`title` is a reference variable of type `String`, but at the moment `length()` is called it **does not reference any String object**. There is no instance on which to perform the call. The error arises when **using** a null value in an invalid way, not simply because a variable is declared or assigned null.

**Objectives:** After this lesson, you will be able to identify sources of null, distinguish the types of operations that cause NPE, use conditional checks and appropriate APIs to prevent it, choose input policies, read stack traces, test missing-data cases, and design classes that produce fewer unexpected NPEs.

This lesson uses **Java 17 or later**; complete programs include file names, `javac`/`java` commands, and reference stdout. Snippets that **intentionally trigger errors** are clearly indicated so learners do not mistake them for code that should be applied in production.

## 1. From Null to the Throw Site: NPE Diagnostic Mindset

`null` is a reference value that **does not point to an object**. When preventing `NullPointerException`, the more specific question is: **which step in the expression requires an object but receives null?**

~~~java
String missing = null;
System.out.println(missing == null); // true, no error
// System.out.println(missing.length()); // NPE if executed
~~~

Comparing reference values does not require an object, but calling `length()` requires a String receiver. Similarly, `Integer boxed = null; int value = boxed;` can throw an NPE due to **auto-unboxing**, even though the source does not explicitly call a method.

When reading a stack trace, trace **null source → dereference operation → nullable contract → validation/handling site**. This lesson prioritizes debugging and defensive design, rather than re-teaching the entire table comparing `null` with empty strings or empty arrays.

## 2. Find the Source of Null, Don't Just Mask the Explosion Site

Common sources of null include uninitialized reference fields, slots in `new String[3]`, parameters passed by a caller, an API returning null, `Map.get(key)`, JSON/DB/config data, or reset references. With `order.getCustomer().getAddress().city()`, you need to check `order`, `getCustomer()`, and `getAddress()` in turn; guarding at the **contract-owning boundary** is usually easier to understand than catching an NPE after it happens.

**Correcting an important misconception:** Java does not automatically return `null` when a method with a non-void return type "forgets a return statement". If the compiler sees a normal completion path without returning a value, that is a **compilation error**. A method only returns null if the returned statement/expression has the value null (or a branch intentionally returns null).

Distinguishing fields from locals:

~~~java
class Holder {
    String name;                   // instance field defaults to null
    String[] tags = new String[2]; // array is non-null, elements default to null
}
~~~

This is a class snippet. By contrast, a local variable declared only as `String value;` cannot be read until the compiler confirms **definite assignment**. When debugging, finding the exact **source of the null data** and fixing the nullable policy is more durable than a series of scattered checks.

## 3. Runnable Example: Identifying Null Values Before Dereferencing

Save the file **`NullSourcesDemo.java`**:

~~~java
public class NullSourcesDemo {
    static final class Holder {
        String name;
        String[] tags = new String[2];
    }

    public static void main(String[] args) {
        Holder holder = new Holder();

        System.out.println("name null: " + (holder.name == null));
        System.out.println("tags null: " + (holder.tags == null));
        System.out.println("first tag null: " + (holder.tags[0] == null));
        System.out.println("tags length: " + holder.tags.length);

        String missing = null;
        String empty = "";

        System.out.println("missing null: " + (missing == null));
        System.out.println("empty length: " + empty.length());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 NullSourcesDemo.java
java NullSourcesDemo
~~~

Stdout:

~~~text
name null: true
tags null: false
first tag null: true
tags length: 2
missing null: true
empty length: 0
~~~

Here **there is no NPE** because the program only compares references against null or uses a receiver guaranteed to be an object. Even though `tags[0]` is null, the expression `tags[0] == null` is still valid. Only if `holder.tags[0].length()` were called would the program dereference the null element and throw an NPE.

## 4. Common Operations That Cause `NullPointerException`

| Operation | Risky Example | Why Does NPE Occur? |
| --- | --- | --- |
| Calling an instance method | `text.length()` with `text == null` | No receiver object |
| Reading an instance field | `person.name` with `person == null` | No instance holding the field |
| Writing an instance field | `person.name = "Mai"` with `person == null` | No object to update |
| Reading array length | `items.length` with `items == null` | No array object |
| Reading/writing an array element | `items[0]` or `items[0] = value` when the array is null | No array to access |
| Enhanced for | `for (String s : items)` with a null array/list | Needs array length or an iterator from a null receiver |
| Auto-unboxing | `int n = boxed;` with `boxed == null` | Needs a primitive value from a wrapper object |
| `throw null;` | Throwing a null value instead of a Throwable object | JVM throws NPE |
| `synchronized (lock)` | `lock == null` | Monitor requires an actual object |
| `switch` with a null selector | `switch (name)`, standard Java 17 | Switch on `String`/enum does not normally support null |
| Bound method reference | `text::trim` when `text == null` | The receiver of a bound method reference requires an object |
| Explicit contract check | `Objects.requireNonNull(value)` | API intentionally throws NPE on null |

NPE is an unchecked exception belonging to `RuntimeException`. The compiler does not require methods to declare `throws NullPointerException`. However, the lack of a declaration requirement **does not mean null is safe**.

A method called on a real object can **itself** throw an NPE inside its body because one of the object's own fields is null; the NPE does not necessarily occur right where the caller invokes the method. Therefore, you must read the stack trace and examine the dereference chain.

## 5. Comprehensive Example of Multiple NPE Causes

Save the file **`NpeTriggersDemo.java`**:

~~~java
public class NpeTriggersDemo {
    static final class Box {
        int value;
    }

    static void report(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + " -> completed");
        } catch (NullPointerException ex) {
            System.out.println(label + " -> NullPointerException");
        }
    }

    public static void main(String[] args) {
        String text = null;
        Box box = null;
        int[] numbers = null;
        String[] words = null;
        Integer boxed = null;
        Object lock = null;

        report("method", () -> {
            System.out.println(text.length());
        });

        report("field", () -> {
            int value = box.value;
        });

        report("array length", () -> {
            int length = numbers.length;
        });

        report("array element", () -> {
            int first = numbers[0];
        });

        report("unboxing", () -> {
            int value = boxed;
        });

        report("foreach", () -> {
            for (String item : words) {
                System.out.println(item);
            }
        });

        report("synchronized", () -> {
            synchronized (lock) {
                System.out.println("inside");
            }
        });

        report("throw null", () -> {
            throw null;
        });

        report("switch", () -> {
            String code = null;
            switch (code) {
                case "A" -> System.out.println("A");
                default -> System.out.println("other");
            }
        });
    }
}
~~~

~~~bash
javac -encoding UTF-8 NpeTriggersDemo.java
java NpeTriggersDemo
~~~

Stdout:

~~~text
method -> NullPointerException
field -> NullPointerException
array length -> NullPointerException
array element -> NullPointerException
unboxing -> NullPointerException
foreach -> NullPointerException
synchronized -> NullPointerException
throw null -> NullPointerException
switch -> NullPointerException
~~~

This is a **program that intentionally triggers errors** to identify the mechanisms, not a way to implement business logic. The `report` helper catches each `NullPointerException` and prints only the label name, avoiding reliance on JVM-generated error text.

Analysis:

- `text.length()` requires a `String` object; `text` is null, so an NPE occurs.
- `box.value` requires a Box instance; `box` is null, so there is no field to read.
- `numbers.length` and `numbers[0]` both require the array to exist. If the array is **non-null but empty**, accessing element `[0]` will throw `ArrayIndexOutOfBoundsException`, **not NPE**.
- `int value = boxed;` requires auto-unboxing `Integer`; null cannot be unboxed.
- Enhanced for on a null array needs the array length, leading to an NPE. For a null collection, obtaining an iterator also requires a valid receiver.
- `synchronized (lock)` requires a monitor object, but `lock` is null.
- `throw null` is handled by Java by throwing `NullPointerException` rather than throwing a meaningful "null Throwable".
- `switch` with a null selector string in standard Java 17 throws an NPE.

**Do not catch NPE just to ignore the error.** In a real application, eliminate invalid states or perform intentional checks at the appropriate boundary.

## 6. A Statement with Multiple Dots: Pinpointing the Exact Null Link

Consider:

~~~java
String city = order.getCustomer().getAddress().getCity();
~~~

Receivers that could be null:

1. `order` is null → `getCustomer()` cannot be called.
2. `order.getCustomer()` returns null → `getAddress()` cannot be called.
3. `getAddress()` returns null → `getCity()` cannot be called.
4. `getCity()` returns null → **the assignment `String city = ...` itself is still valid** because a String reference can be null. An NPE may occur **later** if `city.length()` is used.

The distinction in step 4 is very important: **A method returning null does not always throw an NPE immediately**. An NPE occurs when code goes on to **use null where an object is required**.

### A Way of Writing That Makes Errors Easier to Locate

~~~java
Customer customer = order.getCustomer();
Address address = customer.getAddress();
String city = address.getCity();
~~~

This is **illustrative code**, requiring `Order`, `Customer`, and `Address` types along with valid objects. Splitting into variables helps identify the receiver at each step, but **by itself does not prevent NPE**. Safety requires validation, guard clauses, or domain data that guarantees invariants.

### Distinguishing Null from Other Exceptions

If `order` is non-null but `getCustomer()` itself throws `IllegalStateException`, that error **is not an NPE merely because it is in a dot chain**. Identify the actual exception type and the failing frame, rather than replacing everything with null-catching branches.

## 7. Guard Clause: Rejecting or Handling Null Right at a Logical Point

A guard clause is a condition at the start of a method to reject invalid input cases or handle missing-data cases before the main processing begins.

Example of rejecting:

~~~java
static int displayNameLength(String name) {
    if (name == null) {
        throw new IllegalArgumentException("name is required");
    }
    return name.length();
}
~~~

Example of accepting null as an absent value:

~~~java
static String displayName(String name) {
    if (name == null || name.isBlank()) {
        return "(anonymous)";
    }
    return name.strip();
}
~~~

These are **illustrative methods** that can be placed in an appropriate class. The two policies differ:

- `displayNameLength` treats null as a data error.
- `displayName` treats null as a state that can be handled with a default.

**Do not mix the two policies arbitrarily.** If the name is required in the domain model, it should usually be rejected when creating the object. If the field is optional, set a default value or return an explicit missing state at the point of use.

### Why Is the Condition `name == null || name.isBlank()` Safe?

`||` in Java **short-circuits** from left to right:

- If `name == null` is true, the right-hand expression `name.isBlank()` **is not evaluated**.
- If false, `name` has a non-null receiver in this expression, so `isBlank()` can be called.

Common mistake:

~~~java
if (name.isBlank() || name == null) {
    // This line can throw an NPE before checking for null!
}
~~~

The same applies to `&&`: `name != null && !name.isBlank()` is safe because the right-hand side only runs when `name != null`.

## 8. Runnable Example: Clear Guard Clause Policies

Create the file **`NullGuardDemo.java`**:

~~~java
public class NullGuardDemo {
    static String normalizeDisplayName(String name) {
        if (name == null || name.isBlank()) {
            return "(anonymous)";
        }
        return name.strip();
    }

    static int requiredLength(String value) {
        if (value == null) {
            throw new IllegalArgumentException("value is required");
        }
        return value.length();
    }

    public static void main(String[] args) {
        System.out.println(normalizeDisplayName(null));
        System.out.println(normalizeDisplayName("   "));
        System.out.println(normalizeDisplayName("  Mai  "));
        System.out.println("length=" + requiredLength("Java"));

        try {
            requiredLength(null);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullGuardDemo.java
java NullGuardDemo
~~~

Stdout:

~~~text
(anonymous)
(anonymous)
Mai
length=4
rejected: value is required
~~~

Both input-handling paths are **proactive**. NPE is not used as a mechanism to notify the caller that a required value is missing; instead, the API defines `IllegalArgumentException` and a meaningful message. For optional input, the method provides a default according to business requirements.

`isBlank()` and `strip()` are `String` methods available in Java 11+ and usable on Java 17. For passwords, identifiers that must preserve spaces, or digitally signed data, do not automatically strip/normalize if the contract does not permit it.

## 9. `Objects.requireNonNull`: Checking Contracts Right at the Boundary

`java.util.Objects.requireNonNull(value, "message")` takes a reference and:

- **If non-null:** returns **that same reference**.
- **If null:** throws `NullPointerException` with the specified message.
- **Does not create a copy of the object**, and does not automatically initialize a default value.

Example:

~~~java
class Product {
    private final String id;

    Product(String id) {
        this.id = java.util.Objects.requireNonNull(id, "id");
    }
}
~~~

This is an illustrative class. `new Product(null)` throws an NPE with the message `id` according to the `requireNonNull` contract. That can be appropriate for an API that specifies null as a programming error.

### When to Use `IllegalArgumentException` Instead of NPE?

Both approaches exist:

~~~java
if (id == null) {
    throw new IllegalArgumentException("id is required");
}
~~~

or:

~~~java
this.id = java.util.Objects.requireNonNull(id, "id");
~~~

Java does not require **every null input** to be reported with the exact same exception type. What matters is:

1. The public API has a consistent policy.
2. The message identifies the violated variable or rule.
3. Callers know whether they must supply valid data or handle the missing case.
4. Validation is not duplicated arbitrarily across multiple layers with conflicting policies.

**Do not catch `NullPointerException` broadly just to turn every error into "no data".** An NPE can also reflect a bug in the code that needs to be fixed.

### `Objects.requireNonNullElse`

Java has `Objects.requireNonNullElse(value, defaultValue)`. This method returns `value` if non-null, or returns `defaultValue` if value is null; **defaultValue must also be non-null**.

~~~java
String label = java.util.Objects.requireNonNullElse(name, "(unknown)");
~~~

If the default is also null, the method throws an NPE. Use this kind of API when a fallback value **is genuinely allowed by the contract**, not to mask a required ID.

## 10. Comparing Strings and Objects When Null Is Possible

A very common mistake:

~~~java
String status = null;
// if (status.equals("READY")) { ... } // May throw NPE.
~~~

There are two commonly used safe approaches:

~~~java
if ("READY".equals(status)) {
    // String literal is non-null, checks content.
}
~~~

or:

~~~java
if (java.util.Objects.equals(status, "READY")) {
    // Null-safe comparison.
}
~~~

`Objects.equals(a, b)` handles null cases according to the equality contract. If both are null, the result is true; if only one side is null, false; otherwise it delegates to `a.equals(b)`.

### Do Not Use `==` to Compare String Contents

~~~java
String left = new String("Java");
String right = new String("Java");
System.out.println(left == right);      // false
System.out.println(left.equals(right)); // true
~~~

For `String`, `==` compares the identity of two references; `equals` compares content. Sometimes two String literals share an interned instance so `==` happens to be true, but you must not rely on that to compare values.

### Complete Example Using Null-Safe APIs

Save **`NullSafeComparisonsDemo.java`**:

~~~java
import java.util.Objects;
import java.util.Optional;

public class NullSafeComparisonsDemo {
    public static void main(String[] args) {
        String status = null;

        System.out.println("ready=" + "READY".equals(status));
        System.out.println("both null=" + Objects.equals(null, null));
        System.out.println("same text=" + Objects.equals("Java", "Java"));
        System.out.println("description=" +
                Objects.toString(status, "(missing)"));

        String display = Optional.ofNullable(status)
                .map(String::strip)
                .filter(value -> !value.isEmpty())
                .orElse("(unknown)");

        System.out.println("display=" + display);
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullSafeComparisonsDemo.java
java NullSafeComparisonsDemo
~~~

Stdout:

~~~text
ready=false
both null=true
same text=true
description=(missing)
display=(unknown)
~~~

`Objects.toString(status, "(missing)")` provides fallback text when the reference is null. If you only use `String.valueOf(status)`, the result is the character string `"null"`, which differs from an intentional business placeholder.

## 11. Dereference Chains with Nested Objects: Example with Layer-by-Layer Checks

A Customer may not have an Address, and an Address may not have a City. Instead of calling getters consecutively without verifying state, define a clear display policy.

Save the file **`NestedNullGuardDemo.java`**:

~~~java
public class NestedNullGuardDemo {
    record Address(String city) {}
    record Customer(String name, Address address) {}

    static String cityLabel(Customer customer) {
        if (customer == null) {
            return "(no customer)";
        }

        Address address = customer.address();
        if (address == null) {
            return "(no address)";
        }

        String city = address.city();
        if (city == null || city.isBlank()) {
            return "(no city)";
        }

        return city;
    }

    public static void main(String[] args) {
        Customer absent = null;
        Customer noAddress = new Customer("Mai", null);
        Customer noCity = new Customer(
                "An", new Address(null));
        Customer complete = new Customer(
                "Binh", new Address("Ha Noi"));

        System.out.println(cityLabel(absent));
        System.out.println(cityLabel(noAddress));
        System.out.println(cityLabel(noCity));
        System.out.println(cityLabel(complete));
    }
}
~~~

~~~bash
javac -encoding UTF-8 NestedNullGuardDemo.java
java NestedNullGuardDemo
~~~

Stdout:

~~~text
(no customer)
(no address)
(no city)
Ha Noi
~~~

Here the records allow null to **simulate incomplete data**. They should not be viewed as value objects that already enforce strong invariants. If business rules require a Customer to **always have an Address**, a better design is to **validate directly in the constructor** and disallow creating a Customer missing an Address. Merely adding null guards at the display screen does not solve an invariant broken at the data source.

### Does Java Have a `?.` Operator Like Some Other Languages?

Java 17 **does not have** a general safe-navigation operator like `customer?.address?.city`. You must use conditionals, guard clauses, types with invariants, or APIs such as `Optional` where appropriate.

Do not write Java using Kotlin, C#, or JavaScript syntax and expect the compiler to understand it automatically.

## 12. `Optional` Can Express "Result Present or Absent"

`java.util.Optional<T>` is a container API for describing a value that may be present or absent, especially useful as the **return type** of search methods.

~~~java
static java.util.Optional<String> findNickname(String id) {
    if ("A".equals(id)) {
        return java.util.Optional.of("Mai");
    }
    return java.util.Optional.empty();
}
~~~

This is an illustrative method. The caller can write:

~~~java
String nickname = findNickname("X").orElse("(unknown)");
~~~

There is no need to assign null directly, unlike the case where `String findNickname(...)` might return null.

**Optional factories:**

- `Optional.of(value)` requires a non-null value; passing null causes an NPE.
- `Optional.ofNullable(value)` creates an empty Optional if value is null.
- `Optional.empty()` represents no value.
- `optional.orElse(defaultValue)` retrieves the content if present, otherwise takes the default.
- `optional.orElseGet(supplier)` computes a fallback using the supplier when the Optional is empty.
- `optional.map(transformer)` maps when a value is present; if the mapper returns null, the resulting Optional is empty.
- `optional.orElseThrow()` throws an error if empty; use when absence is genuinely an error.

### Optional Is Not a "Shield Against Every Null"

~~~java
java.util.Optional<String> optional = null;
// optional.orElse("default"); // NPE because the optional variable itself is null.
~~~

An API declared to return `Optional<String>` should have a contract **not to return a null Optional**, returning `Optional.empty()` instead when missing. Do not default to using `Optional` for every field and every parameter: it is itself an object, has overhead, and can make signatures more complex. In many cases, **validation in the constructor** and **explicit domain types** are better.

## 13. Runnable Example: Lookups with `Optional` and `Map`

Save **`OptionalLookupDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

public class OptionalLookupDemo {
    static Optional<String> find(Map<String, String> users, String id) {
        if (users == null) {
            throw new IllegalArgumentException("users is required");
        }
        if (id == null) {
            throw new IllegalArgumentException("id is required");
        }
        return Optional.ofNullable(users.get(id));
    }

    public static void main(String[] args) {
        Map<String, String> users = new HashMap<>();
        users.put("A", "Mai");
        users.put("B", null);

        System.out.println(find(users, "A").orElse("(missing)"));
        System.out.println(find(users, "B").orElse("(missing)"));
        System.out.println(find(users, "X").orElse("(missing)"));
        System.out.println("has B=" + users.containsKey("B"));
        System.out.println("has X=" + users.containsKey("X"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 OptionalLookupDemo.java
java OptionalLookupDemo
~~~

Stdout:

~~~text
Mai
(missing)
(missing)
has B=true
has X=false
~~~

`HashMap` allows null values. Therefore:

- `users.get("B")` returns null because **key B exists but maps to null**.
- `users.get("X")` also returns null, but because **there is no key X**.
- `Optional.ofNullable(users.get(id))` does not distinguish between the two states above.
- `containsKey` helps distinguish "key present" from "key absent" when the application needs to know.

With `Map.of(...)` or certain other implementations, null keys/values may be rejected. **Do not apply a single null rule to every Map type**. Read the contract of the implementation you are using.

If the system needs three states — **no record / record exists but data is missing / record exists and data is valid** — a specific result type may be more suitable than a standalone `Optional<String>`.

## 14. Null in Arrays and Collections: You Must Distinguish the Container from Its Elements

Two independent possibilities:

~~~java
String[] names = null;       // No array object yet.
String[] names2 = new String[2]; // Array exists; two elements are null.
~~~

For `names`, `names.length` throws an NPE; for `names2`, `names2.length == 2` is valid. However, `names2[0].length()` throws an NPE because the **first element** is null.

Similarly for collections:

~~~java
java.util.List<String> list = null;             // No List object.
java.util.List<String> empty = java.util.List.of(); // Empty List exists.
~~~

`empty.size()` gives 0, while `list.size()` throws an NPE. `List.of("A", null)` throws an NPE **immediately when creating the List** because this factory does not allow null elements.

### The for-each Loop

~~~java
for (String name : names2) {
    System.out.println(name);
}
~~~

The statement above **does not necessarily cause an NPE**: the body only prints a null String reference, so it can print `null`. However, if the body is changed to `System.out.println(name.length());`, it will throw an NPE at the null element. When `names` is a null array, the enhanced for loop throws an NPE before iterating over elements.

### Standalone Runnable Example Distinguishing the Levels

Save the file **`NullArrayLevelsDemo.java`**:

~~~java
import java.util.Arrays;

public class NullArrayLevelsDemo {
    public static void main(String[] args) {
        String[] missing = null;
        String[] empty = new String[0];
        String[] containsNull = new String[2];
        containsNull[1] = "Java";

        System.out.println("missing array=" + (missing == null));
        System.out.println("empty length=" + empty.length);
        System.out.println("contents=" + Arrays.toString(containsNull));
        System.out.println("first missing=" + (containsNull[0] == null));

        for (String value : containsNull) {
            System.out.println("value=" + value);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullArrayLevelsDemo.java
java NullArrayLevelsDemo
~~~

Stdout:

~~~text
missing array=true
empty length=0
contents=[null, Java]
first missing=true
value=null
value=Java
~~~

The benefit of this distinction is that you do not "fix" an array containing null elements merely by checking that the array reference is non-null. You must state clearly whether the container may be null **and** whether elements may be null.

## 15. Auto-unboxing: An NPE Without a Dot in the Code

Many NPEs surprise beginners because the statement has no `.method()`:

~~~java
Integer boxed = null;
int number = boxed; // Auto-unboxing null -> NPE.
~~~

When an `int` is required, Java can convert `Integer` to a primitive via unboxing. If the wrapper reference is null, there is no primitive value to retrieve.

Similar examples:

~~~java
Boolean flag = null;
// if (flag) { ... }  // NPE due to unboxing Boolean -> boolean.

Integer points = null;
// int doubled = points * 2;  // NPE due to unboxing Integer -> int.
~~~

Each snippet has the **risky operation commented out** for illustration and is not a standalone runnable program. Be careful with return values from `Map<String, Integer>`, wrapper-typed DTO fields, and database query results.

### Preventing Null Auto-Unboxing

One clear option:

~~~java
static int pointsOrZero(Integer points) {
    return points == null ? 0 : points;
}
~~~

If null is **invalid**, you should not automatically default to 0. Use validation to report the error:

~~~java
static int requiredPoints(Integer points) {
    if (points == null) {
        throw new IllegalArgumentException("points is required");
    }
    return points;
}
~~~

In the second case, unboxing only happens on the `return points;` line **after the check**, so it never encounters null.

### Runnable Example Without NPE

Create the file **`SafeUnboxingDemo.java`**:

~~~java
public class SafeUnboxingDemo {
    static int pointsOrZero(Integer value) {
        return value == null ? 0 : value;
    }

    static int requiredPoints(Integer value) {
        if (value == null) {
            throw new IllegalArgumentException("points is required");
        }
        return value;
    }

    public static void main(String[] args) {
        Integer missing = null;
        Integer present = 7;

        System.out.println("default=" + pointsOrZero(missing));
        System.out.println("present=" + pointsOrZero(present));
        System.out.println("required=" + requiredPoints(present));

        try {
            requiredPoints(missing);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected missing points");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeUnboxingDemo.java
java SafeUnboxingDemo
~~~

Stdout:

~~~text
default=0
present=7
required=7
rejected missing points
~~~

If the business domain **always has an integer**, consider using `int` right from the validated boundary instead of passing nullable `Integer` across multiple layers. When you need to represent the absence of a number, determine an appropriate representation mechanism.

## 16. Method Invocation: Null Receiver and Argument Evaluation Order

An advanced scenario that can cause you to misread logs: in an instance method invocation, Java evaluates the **receiver expression**, then the **argument expressions in left-to-right order**. If the receiver evaluates to null while an argument still has a side effect, that side effect can happen **before** the NPE is thrown because there is no instance to invoke on.

Create the file **`NullReceiverEvaluationDemo.java`**:

~~~java
public class NullReceiverEvaluationDemo {
    static class Service {
        void accept(int number) {
            System.out.println("body=" + number);
        }
    }

    static int prepareArgument() {
        System.out.println("argument prepared");
        return 5;
    }

    public static void main(String[] args) {
        Service service = null;

        try {
            service.accept(prepareArgument());
        } catch (NullPointerException ex) {
            System.out.println("receiver was null");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullReceiverEvaluationDemo.java
java NullReceiverEvaluationDemo
~~~

Stdout:

~~~text
argument prepared
receiver was null
~~~

`prepareArgument()` is executed and prints the log. After preparing the argument, the `Service.accept` call has no receiver object, so an NPE occurs. The body of `accept` **does not run**, so there is no `body=...` line.

**Distinction:** If the **receiver expression** itself throws an exception during evaluation, subsequent arguments may not be evaluated. If an **argument** throws an exception before the instance call is performed, that exception may appear instead of an NPE for a null receiver. Do not rely on exceptions to control side effects; it is better to check the receiver before preparing an operation with external effects.

## 17. Bound Method References and Null

In Java, a method reference of the form `reference::instanceMethod` is **bound to a receiver**. If the receiver is null, creating a **bound method reference** can cause an NPE right when the reference expression is evaluated, before the functional interface method is even called.

Example **intentionally causing an NPE**:

~~~java
String text = null;
// java.util.function.Supplier<String> trim = text::trim;
~~~

If you uncomment the second line, the program can throw an NPE when evaluating `text::trim`. This is unlike `String::trim`, which is an **unbound instance method reference** bound to a receiver parameter on a later invocation, or the lambda `() -> text.trim()`, where the actual dereference lies inside the lambda body at runtime.

In a safe-usage example, you can check the receiver before creating a bound reference:

~~~java
if (text != null) {
    java.util.function.Supplier<String> trim = text::trim;
    System.out.println(trim.get());
}
~~~

This is an illustrative snippet placed inside a method; it is not a standalone program. Distinguishing **when a callback is created** from **when the callback is invoked** will help locate NPEs in asynchronous code.

## 18. Constructors Should Establish Invariants to Limit Null Spreading Throughout the System

If the `Customer` class requires an email, you should not allow creating an object missing an email and then force every other method to check for null.

~~~java
class Customer {
    private final String email;

    Customer(String email) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("email is required");
        }
        this.email = email.strip();
    }

    String email() {
        return email;
    }
}
~~~

This is an illustrative class. After `new Customer(...)` **completes successfully**, the instance has a non-null and non-blank email as checked. If the class does not allow changing the email to null later, internal methods can rely on that invariant.

### Where Should You Validate?

- **System entry boundaries:** validate payload/request/database mapping appropriately.
- **Constructors/value objects:** protect the conditions that always hold true for a valid instance.
- **Methods accepting arguments:** validate the required parameters of a specific behavior.
- **Adapter/library boundaries:** verify the contract of external data.
- **Display sites:** only use a fallback if missing data is a valid state; do not by default "patch up" an object with broken invariants.

This does not mean scattering `if (x == null)` across every line. Intentional validation helps **reduce the places that need checks**, rather than increasing them without limit.

### Records Also Need Validation

~~~java
record CustomerId(String value) {
    CustomerId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("CustomerId is required");
        }
    }
}
~~~

Java records have final component fields by design, but a record **does not automatically check for null**. The compact constructor is the valid place to enforce invariants. A record containing a mutable reference also does not automatically become deeply immutable.

## 19. Choosing a Default, an Empty Object, or Rejecting Null?

No single policy fits every data domain.

| Scenario | Usually Suitable Approach | Why? |
| --- | --- | --- |
| Required identifier | Reject null with validation | Null is not a valid ID |
| Search result list with no elements | Return an empty collection when the contract allows | Caller can iterate without handling null |
| Single object not found | `Optional<T>` or nullable per contract | Represents result present/absent |
| Optional display name | Intentional placeholder | UI needs stable rendering |
| Required amount or quantity | Do not arbitrarily convert null to 0 | 0 is a **business value**, not the same as missing |
| Config failed to load | Report an error or use an explicit state model | Silent defaults can mask problems |
| Collection with null elements | Reject or handle null elements per contract | Checking only the container is not enough |

The **Empty Object pattern** can be used when an empty object has a **valid business meaning**, such as a shopping cart with 0 products. However, you should not create meaningless dummy objects just so every reference is non-null.

### An Empty List Does Not Mean Data Failed to Load

For example, `List<Order> orders = List.of();` can mean the query succeeded and there are no orders. A database connection error should be represented by an appropriate error/result type, rather than being turned into an empty list and giving the impression that the query succeeded.

## 20. Nullability Annotations and Static Analysis Tools

Some projects use annotations such as `@Nullable`, `@NonNull`, and `@NotNull` together with IDE tools, checkers, build plugins, or frameworks. They help express the contract of "whether a parameter/field/result can be null".

However:

- Java 17 **does not have a single `@NonNull` annotation enforced by default by the Java compiler for all code**.
- Semantics and checking capabilities depend on the annotation library, toolchain, and project configuration.
- Annotations do not automatically prevent a caller from using reflection or an external library to pass null in every situation.
- Runtime validation is still needed when data comes from untrusted sources or when the contract requires fail-fast behavior.

When working in a team, choose **one consistent nullability system** so all components share the same interpretation. Do not merely decorate code with annotations without enabling checks, writing tests, and maintaining invariants.

### Do IDE Warnings Replace Testing?

No. Static analysis can recognize obvious null paths, but it may not fully understand runtime data, databases, reflection, or library contracts. Combining **clear data types**, **validation**, **tooling**, and **testing missing-data cases** is more reliable than any single method.

## 21. Reading Stack Traces and Enhanced NPE Messages

When an NPE is unhandled, the JVM typically prints exception details to **stderr**, accompanied by a stack trace of the relevant calls.

For example, an illustrative message might explicitly identify which reference was null when calling a method:

~~~text
Exception in thread "main" java.lang.NullPointerException:
Cannot invoke "String.length()" because "name" is null
    at Example.main(Example.java:...)
~~~

This is an **illustrative format**, not a fixed output: line numbers, variable names, exact wording, and whether enhanced NPE messages are present depend on the JVM, runtime options, and compiled code. On many modern JVMs, NPE messages can help pinpoint the null expression more accurately, but **do not depend on a single phrasing of an exception message** to write business logic or tests.

### Investigation Workflow

1. Read the **exception class**: is it really `NullPointerException` or another error?
2. Find the **application code frame** closest to the failure site, and check the file and line number.
3. Read the entire expression containing multiple dereferences on that line.
4. Identify which reference value could be null, and **where it was created/returned/assigned**.
5. Walk backward up the call stack to callers and input data to find the source of null.
6. Decide whether null is **invalid input** or a **valid absent state**.
7. Fix the **contract/invariant/handling logic**, then add tests to prevent regression.

A common mistake is catching NPE and returning empty data without **identifying the source of null**. That approach can hide bugs in object state, leading to silent data corruption.

### Do Not Use Exception Messages to Decide Branching

Do not write `if (ex.getMessage().contains("name"))` to infer a missing name field: the message can change. Validate data **before dereferencing** and throw a clearly typed exception at the contract boundary.

## 22. Why Is `catch (NullPointerException)` Usually Not the Way to Prevent It?

The snippet:

~~~java
try {
    return order.getCustomer().getName();
} catch (NullPointerException ex) {
    return "(unknown)";
}
~~~

is an **illustrative method body**. It can hide several different problems:

- `order` is null;
- `getCustomer()` returns null;
- `getName()` itself throws an NPE **inside the method** due to another bug.

All three get collapsed into a single `"(unknown)"` result, losing the ability to identify the root problem. Especially if a method has side effects before the NPE, `catch` does not automatically roll back side effects.

A better approach is to check precisely for the values allowed to be missing:

~~~java
if (order == null) {
    throw new IllegalArgumentException("order is required");
}

Customer customer = order.getCustomer();
if (customer == null) {
    return "(no customer)";
}

String name = customer.getName();
return name == null ? "(unnamed customer)" : name;
~~~

This is also an **illustrative code fragment** that requires concrete classes and methods. It distinguishes a **required order**, an **optional customer**, and an **optional name** according to a chosen contract.

There are exceptions: at a technical boundary that genuinely needs to translate a runtime exception into a higher-level error type, code may catch NPE with a clear reason and preserve the cause. However, **you should not use catching NPE as a "null-safe operator" instead of proper data design**.

## 23. Testing for NPEs: Don't Only Run the Happy Path

Test cases should cover:

- **Null required input** → the API rejects it with the promised exception type.
- **Null optional input** → the API returns the proper fallback/Optional.empty.
- **Required fields after initialization** → invariants always hold.
- **Nested references** → missing objects at each layer have their own handling.
- **Arrays/collections** → null container, empty container, and container with null elements are different cases.
- **Wrappers** → verify unboxing when null.
- **Boundaries/side effects** → errors are detected before unwanted state changes occur.
- **Regression** → tests targeting exact null bugs previously found in production.

### Self-Running Test Example Without JUnit

Save the file **`NullContractTestDemo.java`**:

~~~java
import java.util.Objects;

public class NullContractTestDemo {
    static final class Username {
        private final String value;

        Username(String value) {
            Objects.requireNonNull(value, "value");
            if (value.isBlank()) {
                throw new IllegalArgumentException("username must not be blank");
            }
            this.value = value.strip();
        }

        String value() {
            return value;
        }
    }

    static void assertEquals(String expected, String actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    "expected=" + expected + ", actual=" + actual);
        }
    }

    static void expectNullRejected(Runnable operation) {
        try {
            operation.run();
        } catch (NullPointerException expected) {
            System.out.println("null rejected");
            return;
        }
        throw new AssertionError("Expected NullPointerException");
    }

    public static void main(String[] args) {
        Username valid = new Username("  Mai  ");
        assertEquals("Mai", valid.value());

        expectNullRejected(() -> new Username(null));

        System.out.println("All checks passed");
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullContractTestDemo.java
java NullContractTestDemo
~~~

Stdout:

~~~text
null rejected
All checks passed
~~~

This is a test of a **contract that intentionally rejects null using `Objects.requireNonNull`**, not a test of whether code unintentionally dereferences null. In real projects, JUnit provides `assertThrows` and more convenient test-organization tools. For `Username("")`, the constructor throws `IllegalArgumentException` after the `isBlank()` check; that is a case that should be added when testing thoroughly.

### Note on Messages in Tests

If an API promises a specific message, you may assert it. However, automatic enhanced NPE messages from the JVM **should not be treated as a fixed textual contract**. Tests should verify business behavior and error types defined by the API itself.

## 24. Null-Prevention Mistakes That Look Right but Fall Short

| Coding Pattern / Belief | Problem | Improvement |
| --- | --- | --- |
| `value.equals("OK")` | `value` can be null | `"OK".equals(value)` or `Objects.equals` |
| `name.isBlank() || name == null` | Dereferences before checking for null | `name == null || name.isBlank()` |
| `list != null` then calling `list.get(0)` | List may be empty | Check size/isEmpty; distinguish NPE from `IndexOutOfBoundsException` |
| `array != null` then calling `array[0].length()` | Element `array[0]` may be null | Check bounds and element |
| `Integer n = map.get(key); int x = n;` | Map returns null, unboxing causes NPE | Decide on a default or report missing |
| `if (user != null) user.getAddress().city()` | `getAddress()` can still be null | Guard each layer or enforce invariants |
| `Optional.of(value)` with a nullable value | `of` throws NPE | `Optional.ofNullable` |
| `optional.orElse("x")` when `optional` itself is null | An Optional reference can also be null | API must return a non-null Optional |
| `List.of(value)` with null | Factory does not accept null elements | Validate or use a structure that allows null |
| `try { ... } catch (NPE) { return null; }` | Masks bugs and makes debugging hard | Identify the missing receiver, handle per contract |
| `Objects.requireNonNull` on every field including optional ones | Turns a valid absent state into an exception | Distinguish required from optional |
| `null` can always be replaced with 0 or an empty string | 0/empty has a different meaning from "absent" | Choose fallbacks based on business semantics |
| `@NonNull` annotation is enough | Tooling does not necessarily enforce at runtime | Validation and testing at boundaries |
| `System.gc()` fixes NPE | NPE is not a GC issue | Fix reference/null logic |
| Seeing a dot means the NPE is definitely on the first object | An intermediate receiver could be null | Inspect each dereference and the stack trace |

## 25. Practical Scenario: Customer Data API

An application receives a name and a list of roles from external data. Requirements:
- The name is required and cannot be null/blank.
- Roles may be absent, in which case they default to an **empty list**.
- The list must not contain null elements.
- Once constructed, the object must not allow callers to modify the role contents through an alias.

Create the file **`CustomerNullBoundaryDemo.java`**:

~~~java
import java.util.List;
import java.util.Objects;

public class CustomerNullBoundaryDemo {
    static final class Customer {
        private final String name;
        private final List<String> roles;

        Customer(String name, List<String> roles) {
            Objects.requireNonNull(name, "name");

            String normalized = name.strip();
            if (normalized.isEmpty()) {
                throw new IllegalArgumentException("name must not be blank");
            }

            this.name = normalized;
            this.roles = roles == null ? List.of() : List.copyOf(roles);
        }

        String summary() {
            return name + " roles=" + roles.size();
        }

        List<String> roles() {
            return roles;
        }
    }

    public static void main(String[] args) {
        Customer first = new Customer("  Mai  ", null);
        Customer second = new Customer("An", List.of("READER"));

        System.out.println(first.summary());
        System.out.println(second.summary());

        try {
            new Customer(null, List.of());
        } catch (NullPointerException ex) {
            System.out.println("name is required");
        }

        try {
            new Customer("Binh", java.util.Arrays.asList("READER", null));
        } catch (NullPointerException ex) {
            System.out.println("null role rejected");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CustomerNullBoundaryDemo.java
java CustomerNullBoundaryDemo
~~~

Stdout:

~~~text
Mai roles=0
An roles=1
name is required
null role rejected
~~~

Analysis:

- `Objects.requireNonNull(name)` establishes that name is a **required** field.
- `name.strip()` only runs after null has been ruled out.
- `roles == null ? List.of() : List.copyOf(roles)` applies the **optional roles** policy.
- `List.of()` creates an unmodifiable empty list, distinct from a null reference.
- `List.copyOf(roles)` rejects null elements and protects the list structure from normal external modification.
- Because role elements are immutable `String`s, this example has no risk of mutating element state via a mutable alias. For a list of mutable objects, an appropriate deep defensive copy should be considered.

**An alternative design can also be right:** If roles are required, replace the fallback with `Objects.requireNonNull(roles, "roles")`. Do not mechanically choose an empty list without first determining what missing data means.

## 26. Frequently Asked Questions

### 26.1. Does `String.valueOf(null)` Throw an NPE?

When explicitly calling the overload with an `Object` reference parameter, `String.valueOf((Object) null)` returns the string `"null"`. With the literal call `String.valueOf(null)`, the compiler can select the `char[]` overload, which is more specific than `Object`/`String` among the available overloads; handling a null `char[]` can throw an NPE. Therefore, **you should not assume every `String.valueOf(null)` call is safe**, especially when a null literal meets overloading. Use:

~~~java
String text = String.valueOf((Object) null); // "null"
~~~

or an intentional fallback:

~~~java
String text = java.util.Objects.toString(null, "(missing)");
~~~

These are illustrative code fragments inside a method. This case demonstrates an important pitfall: **overload resolution** happens at compile time, and the type of the argument expression can change which method gets called.

### 26.2. Does `Objects.toString(null)` Throw an NPE?

`Objects.toString((Object) null)` returns the string `"null"` according to the API; `Objects.toString(value, defaultValue)` allows specifying a fallback. This differs from calling `value.toString()` directly on a null variable.

### 26.3. Does `new Customer(...)` Return Null If the Constructor Fails?

No. If a constructor or initializer throws an exception that is not handled during creation, the `new` expression **completes abnormally** and does not produce a successful reference. It does not automatically "return null to signal an error". The caller needs to handle the exception according to the contract. A factory method or lookup method **may choose** to return null, but that is the method's behavior, not a rule of `new`.

### 26.4. Is `null.equals(value)` Valid?

You cannot use the `null` literal as a suitably typed receiver for a normal method call; calling an instance method on a **variable** that is currently null results in an NPE. The right way to perform null-aware comparison is `Objects.equals(a, b)` or using a receiver guaranteed to be non-null.

### 26.5. If an NPE Occurs at `list.get(0).length()`, Is list Definitely Null?

No. `list` could be non-null, `get(0)` could succeed and **return a null element**, and then `length()` causes the NPE. If the list is empty, `get(0)` typically causes `IndexOutOfBoundsException`. You need to analyze the links in the chain and the actual exception type.

### 26.6. Should a Getter Return Null?

It depends on the contract. A getter for a required field should not return null when the object is in a valid state. For optional values, you can return a nullable value with a clearly documented contract or use `Optional<T>` in certain APIs. Do not assume every getter needs Optional; weigh clarity, performance, analysis tools, and project conventions.

### 26.7. Why Is Converting Every Field to `Optional<T>` Not Necessarily Good?

Optional is still a reference type that can be assigned null and does not automatically enforce invariants in constructors; adding Optional to every field can make models and serialization cumbersome. What matters more is **defining valid states and data boundaries**.

### 26.8. Is `Optional.ofNullable(null).orElse(...)` Always Safe?

`Optional.ofNullable(null)` returns an empty Optional; `orElse` takes the fallback. However, the expression computing the fallback can have side effects or throw an exception **before `orElse` is called** because Java evaluates arguments. If the fallback requires expensive computation, use `orElseGet(() -> computeFallback())` when appropriate.

## 27. Exercises: Predict Before Running

### Exercise 1 — Which Layer Does Null Come From?

~~~java
String city = customer.getAddress().getCity();
~~~

List all possible NPE cases. Answer: `customer` may be null; `getAddress()` may return null; `getAddress()` or `getCity()` itself may also throw an NPE due to internal logic. If `getCity()` merely returns null, the assignment `String city = null` is still valid; an NPE may occur upon a subsequent dereference of `city`.

### Exercise 2 — Short-Circuiting

Predict the outcome with `String s = null;`:

~~~java
boolean a = s == null || s.isBlank();
boolean b = s != null && !s.isBlank();
~~~

Result: `a == true`, `b == false`, no NPE. With the order `s.isBlank() || s == null`, an NPE will occur.

### Exercise 3 — Null Wrapper

~~~java
Integer score = null;
// int doubled = score * 2;
~~~

Uncommenting the second line causes an **NPE due to unboxing**. Write one version that rejects null with `IllegalArgumentException`, and another version that accepts null as a missing value and returns a default result per your specific requirements.

### Exercise 4 — Container vs. Elements

~~~java
String[] a = null;
String[] b = new String[1];
String[] c = new String[0];
~~~

- `a.length` → NPE.
- `b.length` → 1.
- `b[0] == null` → true.
- `b[0].length()` → NPE.
- `c.length` → 0.
- `c[0]` → `ArrayIndexOutOfBoundsException`, not NPE.

### Exercise 5 — Choosing a Policy in the Constructor

An `Invoice` class requires a mandatory `invoiceId` and an optional `description`. Design the constructor so that:
- `invoiceId == null` or blank is rejected.
- `description == null` can be normalized to `""` if business rules allow.
- Every successfully created object always has a valid ID.
- The getter does not return null for the required ID.

### Exercise 6 — Handling a Nullable Map Source

Given `Map<String,Integer> scores` that may not contain a key. Write a method `int getScoreOrZero(String id)`, using the value 0 only if a **missing key** truly equals 0 according to business rules. Also write a method that rejects missing entries with a message containing a safe parameter name. If the Map allows null mapped values, use `containsKey` when you need to distinguish a null value from an absent key.

## 28. Self-Assessment Checklist

- [ ] I can distinguish null from empty strings, empty arrays, and empty collections.
- [ ] I know that reference fields default to null, whereas unassigned local variables cannot be read.
- [ ] I can identify which receiver is null in a multi-dot chain.
- [ ] I understand that NPE can occur when reading fields, calling methods, using arrays, foreach, synchronized, throw null, or auto-unboxing.
- [ ] I can distinguish NPE from `ArrayIndexOutOfBoundsException` and other exceptions.
- [ ] I know `a == null` is safe, whereas `a.method()` requires a receiver object.
- [ ] I use `||`/`&&` short-circuiting in the correct order.
- [ ] I place guard clauses when null is invalid or when a contract-defined fallback is needed.
- [ ] I know `Objects.requireNonNull` intentionally throws NPE, while `Objects.equals` handles null safely.
- [ ] I know `Optional.of` differs from `Optional.ofNullable` and do not use a null Optional.
- [ ] I know `Map.get` can return null either because the key is absent or because the mapped value is null.
- [ ] I check for both a null container and null elements when needed.
- [ ] I understand that a null `Integer`/`Boolean` can cause an NPE during unboxing.
- [ ] I know that constructors/value objects can protect invariants to reduce cascading NPEs.
- [ ] I do not catch NPE to silently hide programming bugs.
- [ ] I know that enhanced NPE messages and stack traces are helpful for debugging but are not a fixed textual contract.
- [ ] I write tests for null required inputs, null optional inputs, dereference chains, and collections/arrays.
- [ ] I have run and can explain the stdout of the Java 17+ examples in this lesson.

**Conclusion:** `NullPointerException` is not merely an "error because a variable is null"; it indicates that code **used a null value where a valid object was required** or intentionally enforced a contract by throwing an NPE. The sustainable way to prevent it is to **identify which data is required and which is allowed to be absent; establish invariants right at the data-creation/ingestion boundary; validate at the proper points; and test null paths**. When you know exactly which references can be null and what callers must do when a value is missing, Java code becomes clearer and less prone to unexpected NPEs.
