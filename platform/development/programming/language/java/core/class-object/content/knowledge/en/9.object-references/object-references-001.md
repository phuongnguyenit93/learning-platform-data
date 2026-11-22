# What Does a Reference Variable Store and How Does It Differ from an Object in Java?

When looking at the statement:

~~~java
Student student = new Student("Mai");
~~~

beginners easily interpret it to mean that **the variable `student` is the Student object itself**. This is an imprecise shorthand. In Java, `student` is **a variable of reference type `Student`**, whereas `new Student("Mai")` creates **a new object**. If initialization succeeds, the `new` expression provides a **reference value** to that object, and the assignment stores the reference value in the variable `student`.

Grasping this distinction is the foundation for understanding **aliasing**, **`null`**, **`==` versus `equals()`**, object state mutation behavior, passing parameters to methods, `final`, arrays, garbage collection, and class design.

## 1. Learning Objectives

After this lesson, you should be able to explain and practice:

1. What a **reference variable** is, what kind of value it stores, and how it differs from an **instance/object**.
2. Distinguishing between **declaring a variable**, **creating an object with `new`**, **assigning a reference**, and **modifying a field**.
3. Why two variables can **reference the same object**, and why two objects with the same data are still two objects.
4. Why reference assignment **does not clone an object** and also does not itself modify fields of the old object.
5. What `null` means and how it differs from an empty object; when `NullPointerException` occurs.
6. Differences between **primitive** values and **reference** values, including arrays and `String`.
7. Why Java **always passes parameters by value**, even when the parameter is an object reference.
8. Distinguishing between **object identity** and **value equality**, and understanding the roles of `==` and `equals()`.
9. Understanding why a **`final` reference** does not by itself make an object immutable.
10. Avoiding misconceptions about memory addresses, stack/heap, object lifecycles, and when the garbage collector runs.

Standalone runnable examples use **Java 17 or later**. Snippets that are not complete programs will be explicitly noted as illustrative code.

## 2. Three Concepts to Separate: Variable, Reference Value, and Object

Consider:

~~~java
Book book = new Book("Java Core");
~~~

There are three components:

- **`Book`**: the type (class) name defined by the programmer.
- **`book`**: the reference variable. In an appropriate context, this variable can store a **reference value to a Book object** or `null`.
- **`new Book("Java Core")`**: the expression that requests creating a new Book object; if it completes normally, the result is a reference to the newly created object.

Mental model:

~~~text
Variable                Object
+------------------+    +---------------------------+
| book             |    | Book instance             |
| reference value -+--->| title = "Java Core"       |
+------------------+    +---------------------------+
~~~

The arrow represents a **reference relationship**, not a concrete RAM address. Java defines how reference values work, but it does not require the programmer to see the object's machine address in order to use a reference.

Questions to ask:

- What is the variable? `book`.
- What is the object? The `Book` instance created by `new Book(...)`.
- Where does the `title` field belong in the **semantic model**? It belongs to the state of the Book object.
- Does assigning `book` to another object mean modifying `title` of the old object? **No**.

### A Variable Does Not Hold All of an Object's Data

If the `Book` class has ten fields, the assignment:

~~~java
Book another = book;
~~~

does not mean Java automatically copies the ten fields into a new Book. Java copies the **reference value** of `book` into the variable `another`. Both variables can now access **the same object**.

To create another object, you typically need a specific object-creation operation such as `new Book(...)`, a factory method, or an API-defined copy mechanism. Simply writing `another = book` does **not** create a new object.

## 3. First Example: Two Variables, One Object, and a Second Object

Create the file **`ReferenceBasicsDemo.java`**:

~~~java
public class ReferenceBasicsDemo {
    static final class Book {
        private final String title;
        private int pagesRead;

        Book(String title) {
            if (title == null || title.isBlank()) {
                throw new IllegalArgumentException("title required");
            }
            this.title = title;
        }

        void readPages(int pages) {
            if (pages <= 0) {
                throw new IllegalArgumentException("pages must be positive");
            }
            pagesRead = Math.addExact(pagesRead, pages);
        }

        String describe() {
            return title + ": " + pagesRead + " pages";
        }
    }

    public static void main(String[] args) {
        Book first = new Book("Java Core");
        Book alias = first;
        Book second = new Book("Java Core");

        alias.readPages(12);

        System.out.println("first: " + first.describe());
        System.out.println("alias: " + alias.describe());
        System.out.println("second: " + second.describe());
        System.out.println("first == alias: " + (first == alias));
        System.out.println("first == second: " + (first == second));
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac -encoding UTF-8 ReferenceBasicsDemo.java
java ReferenceBasicsDemo
~~~

Exact stdout:

~~~text
first: Java Core: 12 pages
alias: Java Core: 12 pages
second: Java Core: 0 pages
first == alias: true
first == second: false
~~~

Step by step:

1. The first `new Book("Java Core")` creates **Book object #1**; `first` holds a reference to it.
2. `Book alias = first;` **does not create a new Book object**; it only copies the reference.
3. The second `new Book("Java Core")` creates **Book object #2**, even though its `title` value is the same as Book #1.
4. `alias.readPages(12)` updates the `pagesRead` field on object #1.
5. `first.describe()` and `alias.describe()` read **the same object #1**, so both return 12 pages.
6. `second.describe()` reads object #2, so it still gives 0 pages.
7. For references, the `==` operator checks whether two reference values represent **the same object**. Therefore, `first == alias` is true, and `first == second` is false.

Illustration after calling `alias.readPages(12)`:

~~~text
first -----------+
                 +----> Book #1
alias -----------+      title = "Java Core"
                        pagesRead = 12

second ---------------> Book #2
                        title = "Java Core"
                        pagesRead = 0
~~~

**Conclusion:** Objects have **identity** and **state**. Two variables referencing the same object share observation of its state; two object creations do not become one just because their fields match.

## 4. Declaring a Variable Does Not Create an Object

The three steps below have different meanings:

~~~java
Book book;                         // Only declares a local variable.
book = new Book("Java Core");      // Creates an object and assigns the reference.
Book another = book;               // Copies the reference.
~~~

If `Book book;` is a **local variable**, Java requires the variable to be assigned before it is read. Writing:

~~~java
Book book;
// System.out.println(book); // Uncommenting causes an error: local variable not assigned.
~~~

does not mean a local reference automatically defaults to `null` in a way that allows immediate reading.

In contrast, a **reference-type field** that has not been explicitly initialized has a default value of `null`:

~~~java
class Holder {
    Book current; // Instance field defaults to null.
}
~~~

This is an illustrative class, requiring the `Book` type to be available in the compilation context. With `Holder holder = new Holder();`, `holder.current` is initially null, because `current` is a field and has not yet been assigned a reference to a Book object.

### Do Not Confuse with `new`

~~~java
Book book = null;
~~~

only stores the **null value** and does not create an "empty" Book object. Whereas:

~~~java
Book book = new Book("Java Core");
~~~

is what requests creating a Book object. A successful `new Book(...)` expression yields a non-null reference value. However, a **method** returning a Book can still return null if its contract allows it; for example, `Book findById(String id)` may return null when not found.

## 5. Does a Reference Variable Store an "Address" or a "Pointer"?

You can imagine a reference as an "arrow" to an object, but saying **"a Java reference variable definitely holds the raw memory address of the object"** is too strong and inaccurate according to the language specification.

According to the Java model:

- A reference-type value is a **reference to an object** or `null`.
- A reference allows operating on an object according to the rules for accessing fields, methods, and arrays.
- The Java language does not have common raw pointer operators such as address arithmetic `pointer + 1` or `&variable` from C/C++.
- The JVM may use **addresses, handles, compressed references, or optimized representations** depending on the implementation. Ordinary Java code must not depend on any specific representation.
- The variable name `book` is not the name of a fixed memory region where the object must stay forever; an object can be moved by the GC in corresponding implementations while program correctness is still preserved.

Therefore, when learning, you can say "a reference variable points to an object" in the sense of a **logical relationship**. However, do not use arrow diagrams to claim that every reference is actually a 64-bit address number.

### `System.identityHashCode` Is Not a RAM Address

`System.identityHashCode(object)` provides a hash code related to **identity** per the API contract; it does not expose a physical address. Two different objects are not guaranteed to have different identity hashes, and identity hash codes are not a reliable way to count the number of objects.

If you need to know whether two variables refer to the same object, use `==` for references (where types allow), and do **not** compare `identityHashCode`.

## 6. A Reference Value Can Be Reassigned Without Changing the Old Object

Create the file **`ReferenceReassignmentDemo.java`**:

~~~java
public class ReferenceReassignmentDemo {
    static final class Box {
        private final int number;

        Box(int number) {
            this.number = number;
        }

        int number() {
            return number;
        }
    }

    public static void main(String[] args) {
        Box first = new Box(10);
        Box saved = first;

        first = new Box(20);

        System.out.println("first=" + first.number());
        System.out.println("saved=" + saved.number());
        System.out.println("same=" + (first == saved));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReferenceReassignmentDemo.java
java ReferenceReassignmentDemo
~~~

Stdout:

~~~text
first=20
saved=10
same=false
~~~

Initially, `first` and `saved` both reference Box(10). The line `first = new Box(20);` performs **two things**:

1. Creates a new Box object with `number = 20`.
2. Assigns the new reference to **the variable `first`**.

No statement modifies the `number` field of Box(10). `saved` still holds a reference to Box(10), so reading `saved.number()` gives 10.

Diagram:

~~~text
Before assignment:
first ----+
          +----> Box #1 { number = 10 }
saved ----+

After first = new Box(20):
first ---------> Box #2 { number = 20 }
saved ---------> Box #1 { number = 10 }
~~~

**Assigning a reference variable is different from calling a method that mutates an object.** You must read the left-hand side carefully: `first = ...` assigns the variable `first`, whereas `first.setNumber(...)` may modify the object currently referenced by `first`.

## 7. Two Kinds of Values in Java: Primitive and Reference

Java has two main groups of types:

| | Primitive type | Reference type |
| --- | --- | --- |
| Examples | `int`, `long`, `double`, `boolean`, `char` | `Book`, `String`, `Integer`, `int[]`, `List<String>` |
| Value stored by variable | Primitive value of the type | Reference to an object or null |
| Can store `null`? | No | Yes (if the type/logic allows) |
| Assignment `b = a` | Copies the primitive value | Copies the reference value, **does not copy the object** |
| Using `==` | Compares according to primitive type rules | Compares identity for two compatible references |
| Shared object state via alias? | No primitive object to alias | Possible if multiple references point to the same mutable object |

There are exactly **eight primitive types** in Java: `byte`, `short`, `int`, `long`, `float`, `double`, `char`, `boolean`. `void` is used in method return type declarations, but it is not a primitive value type for which a variable can be declared to store a value in the manner above.

`String`, `Integer`, `Boolean`, and `int[]` **are all reference types**. Even though they hold/represent text or numeric values, that does not make variables of these types primitive.

### Comparing Primitive and Reference Assignment

~~~java
int left = 5;
int right = left;
right = 9;
// left is still 5.

Book first = new Book("A");
Book second = first;
// first and second both point to the same Book object.
~~~

This is an illustrative code snippet; `Book` requires an appropriate constructor. For primitives, `right = 9` modifies an independent variable. For references, `second = first` copies the reference, so reading/modifying mutable fields through both variables can affect the same object.

## 8. `null` Is a Special Reference Value, Not an Object

A reference variable can hold the value `null`:

~~~java
String text = null;
int[] numbers = null;
Object anything = null;
~~~

That **does not create three empty objects**. It indicates that the variables do not currently reference any object.

Do not confuse these:

| Expression | Is there an actual object? | Meaning |
| --- | --- | --- |
| `String text = null;` | No String object created by this assignment | Variable does not reference a String |
| `String text = "";` | Reference to an empty String | A valid String value |
| `int[] numbers = null;` | No array object created by this assignment | Cannot read `numbers.length` |
| `int[] numbers = new int[0];` | Has an array of length 0 | `numbers.length == 0` |
| `new int[] {0}` | Has an array of length 1 | First element is `0` |
| `new String[] {null}` | Has an array of length 1 | First element is null |

### When Does `NullPointerException` Occur?

If an expression needs to use an object as a receiver but the reference is null, a `NullPointerException` can be thrown:

~~~java
String name = null;
// name.length(); // If called, this will throw NullPointerException.
~~~

The comparison `name == null` does **not** dereference, so it is safe. `System.out.println(name)` can print `null` through String-handling logic, not because `name` has become an object.

### Standalone Runnable Example: Checking for null Before Use

Create the file **`NullReferenceDemo.java`**:

~~~java
public class NullReferenceDemo {
    static String describe(String value) {
        if (value == null) {
            return "(missing)";
        }
        return "length=" + value.length();
    }

    public static void main(String[] args) {
        String absent = null;
        String empty = "";
        String filled = "Java";

        System.out.println(describe(absent));
        System.out.println(describe(empty));
        System.out.println(describe(filled));
        System.out.println("absent == null: " + (absent == null));
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullReferenceDemo.java
java NullReferenceDemo
~~~

Stdout:

~~~text
(missing)
length=0
length=4
absent == null: true
~~~

`describe` defines its own contract that null means missing data. For another class, null may be rejected using `Objects.requireNonNull` or `IllegalArgumentException`. **Java does not decide on its own that every null is permitted from a business-logic perspective.**

## 9. Aliases and Effects Through Mutable Objects

**Aliasing** is the situation where multiple reference paths point to **the same object**. This is the source of many state changes that seem to happen "somewhere else".

Example:

~~~java
Account primary = new Account(100);
Account otherName = primary;
otherName.deposit(50);
~~~

If `deposit(50)` modifies the `balance` field of the Account object, reading through `primary` also shows the increased balance. There is no direct assignment to the `primary` variable, yet **the shared object state** has changed.

Do not confuse these operations:

- `otherName = new Account(0);`: reassigns **the variable `otherName`**.
- `otherName.deposit(50);`: may modify **the object currently referenced by otherName**.
- `primary = otherName;`: assigns a **reference value** to `primary`.
- `primary.balance`: reads the field when access permissions allow; does not create a new object.

### Standalone Example: An Alias Modified in Another Method

Save **`AliasingDemo.java`**:

~~~java
public class AliasingDemo {
    static final class Cart {
        private int items;

        Cart(int items) {
            this.items = items;
        }

        void add(int quantity) {
            items += quantity;
        }

        int count() {
            return items;
        }
    }

    static void update(Cart cart) {
        cart.add(2);
    }

    public static void main(String[] args) {
        Cart first = new Cart(1);
        Cart alias = first;

        update(alias);

        System.out.println("first=" + first.count());
        System.out.println("alias=" + alias.count());
        System.out.println("same=" + (first == alias));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AliasingDemo.java
java AliasingDemo
~~~

Stdout:

~~~text
first=3
alias=3
same=true
~~~

`update` receives a **copy of the reference value** to the Cart object. The call `cart.add(2)` modifies the shared object; both `first` and `alias` observe a count of 3.

If an object is designed to be immutable, a method will not directly alter the old state through a behavior like `add`. Having a reference **does not automatically grant permission to modify** the object; that depends on the API and access modifiers.

## 10. Java Always Passes Parameters by Value, Even for Object References

This is the most important rule when learning reference variables:

**Java uses pass-by-value for all parameters.** For parameters of class/array/interface types, the copied value is the **reference value**. The method does not receive an "alias of the caller's variable", so **reassigning the parameter does not reassign the caller's variable**.

Create the file **`ReferenceParameterDemo.java`**:

~~~java
public class ReferenceParameterDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void change(Box box) {
        box.value = 20;
        box = new Box(99);

        System.out.println("inside=" + box.value);
    }

    public static void main(String[] args) {
        Box original = new Box(5);

        change(original);

        System.out.println("outside=" + original.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReferenceParameterDemo.java
java ReferenceParameterDemo
~~~

Stdout:

~~~text
inside=99
outside=20
~~~

Analysis:

1. `original` references Box #1 with `value = 5`.
2. `change(original)` copies the **reference value** into the parameter `box`. Initially, both variables point to Box #1.
3. `box.value = 20` updates the **field of Box #1**, so the caller can read 20.
4. `box = new Box(99)` creates Box #2 and **reassigns the parameter `box`**. The caller's variable `original` still points to Box #1.
5. `inside=99` reads Box #2 through the reassigned parameter; `outside=20` reads Box #1 through the caller's variable.

Diagram:

~~~text
Start of change:
original ---+
            +----> Box #1 { value=5 }
box --------+

After box.value = 20:
original ---+
            +----> Box #1 { value=20 }
box --------+

After box = new Box(99):
original --------> Box #1 { value=20 }
box -------------> Box #2 { value=99 }
~~~

**Accurate conclusion:** A method can modify **shared object state**, but it cannot change the caller's reference variable simply with a `box = ...` statement inside the method.

### Why Do People Often Say "Pass Objects by Reference"?

That is a misleading shorthand. The accurate semantics is **passing a reference by value**. If the caller's variable were truly passed using "pass-by-reference" as in some other languages, reassigning the parameter would make the caller's variable point to another object. Java does not have that behavior for ordinary method parameters.

## 11. Returning an Object Also Returns a Reference Value

If a method is declared to return a reference type:

~~~java
static Book createBook(String title) {
    return new Book(title);
}
~~~

then it returns a **reference value** to the Book object created by `new`, rather than automatically cloning the object again. This is an **illustrative method**; you must define `Book` and place the method in an appropriate class.

If a method returns a reference it received:

~~~java
static Book identity(Book input) {
    return input;
}
~~~

then the caller receives a reference to **the exact object that `input` represents**; there is no `new` inside the method, so no new object is created by this method.

### Be Cautious When Returning a Mutable Field Directly

~~~java
class Library {
    private final java.util.List<String> books = new java.util.ArrayList<>();

    java.util.List<String> books() {
        return books;
    }
}
~~~

This is an illustrative class. The caller receives a **reference to the internal list**, so if the caller modifies that list, it affects the state of Library. Declaring the field `final` only prevents reassigning the field's reference; it does not make the ArrayList immutable.

If you do not want the caller to modify the internal list, you can use `List.copyOf(books)` when elements are non-null and it fits the contract, or provide a read-only API. **Encapsulation design and aliasing** always go hand in hand.

## 12. `final` on a Reference Variable Does Not Make the Object Immutable

Example:

~~~java
final StringBuilder builder = new StringBuilder("Java");
builder.append(" Core");             // Valid: modifies the object.
 // builder = new StringBuilder();   // If uncommented, compilation error.
~~~

The `builder` variable is marked `final`: once assigned a value according to the rules, it **cannot be reassigned another reference**. However, `StringBuilder` is a mutable object, so `append` still modifies its contents.

Similarly:

~~~java
final int[] numbers = {1, 2, 3};
numbers[0] = 9;                      // Valid.
 // numbers = new int[] {4, 5};     // Invalid.
~~~

`final` fixes **the variable's reference value**; it does not freeze the contents of the array object.

Further distinctions:

- `private final Address address`: the field cannot be reassigned after valid initialization; if `Address` is mutable, the Address object can still be modified through an alias.
- `final class User`: prevents other classes from extending `User`; this is a **different** meaning of `final`.
- An immutable class requires design rules: do not expose mutable state, do not provide behaviors that change observable state, and perform defensive copying when appropriate.
- A `final` reference does not automatically extend or shorten an object's lifetime with a simple guarantee.

### Runnable Example of `final` on a Reference

Save **`FinalReferenceDemo.java`**:

~~~java
public class FinalReferenceDemo {
    public static void main(String[] args) {
        final StringBuilder builder = new StringBuilder("A");
        builder.append("B");

        final int[] values = {1, 2};
        values[0] = 7;

        System.out.println(builder);
        System.out.println(values[0] + "," + values[1]);
    }
}
~~~

~~~bash
javac -encoding UTF-8 FinalReferenceDemo.java
java FinalReferenceDemo
~~~

Stdout:

~~~text
AB
7,2
~~~

In this example, the mutable object itself changed; no statement reassigned the `final` variables.

## 13. `String` Is a Reference Type, Yet Immutable

`String` often causes confusion because it looks like a primitive during string concatenation or literal assignment:

~~~java
String text = "Hello";
String alias = text;
text = text + " Java";
~~~

`String` is still a **reference type**. Semantically, the concatenation expression creates/yields a new String value; the assignment `text = ...` replaces the reference in the variable `text`. It **does not change the contents of the String object** that `alias` is referencing.

Create the file **`ImmutableStringDemo.java`**:

~~~java
public class ImmutableStringDemo {
    public static void main(String[] args) {
        String first = "Hello";
        String alias = first;

        first = first + " Java";

        System.out.println("first=" + first);
        System.out.println("alias=" + alias);
        System.out.println("same=" + (first == alias));

        StringBuilder mutable = new StringBuilder("Hello");
        StringBuilder shared = mutable;
        mutable.append(" Java");

        System.out.println("mutable=" + mutable);
        System.out.println("shared=" + shared);
        System.out.println("same builder=" + (mutable == shared));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableStringDemo.java
java ImmutableStringDemo
~~~

Stdout:

~~~text
first=Hello Java
alias=Hello
same=false
mutable=Hello Java
shared=Hello Java
same builder=true
~~~

With `String`, changing the variable `first` cannot modify the original string's contents. With `StringBuilder`, the `append` method modifies the shared object, so both `mutable` and `shared` observe the new contents.

**Do not conclude that every reference type is mutable.** A reference indicates a relationship to an object; **state mutability** is a property of the class and its API.

## 14. Distinguishing Object Identity from Logical Equality

These are two different questions: for compatible references, `a == b` checks whether they refer to **the same object** (or are both null); `a.equals(b)` asks whether two values are equal according to **the class's contract**. `Object.equals` defaults to identity, whereas a Java 17 record defines equality from its record components.

Standalone runnable example, file `ReferenceEqualityIntro.java`:

~~~java
public class ReferenceEqualityIntro {
    record Point(int x, int y) {}

    public static void main(String[] args) {
        Point a = new Point(2, 3);
        Point b = new Point(2, 3);
        Point alias = a;
        System.out.println("same object=" + (a == b));
        System.out.println("same value=" + a.equals(b));
        System.out.println("alias=" + (a == alias));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReferenceEqualityIntro.java
java ReferenceEqualityIntro
~~~

~~~text
same object=false
same value=true
alias=true
~~~

For String, prefer `equals` to compare **contents**; interning may make `==` evaluate to true in some cases that code should not rely on. `Objects.equals(a, b)` supports nullable references. Detailed rules for `equals/hashCode`, wrapper caching, and array comparison are taught primarily in the `==`/`!=` lesson; this section only establishes the core distinction.

## 15. A Variable's Declared Type Can Differ from the Runtime Class

Given `Dog extends Animal`, the snippet `Animal pet = new Dog();` is **a snippet assuming both classes have already been declared**. The variable pet has static type `Animal` yet points to an object whose actual class is `Dog`; upcasting does not create a new object.

The compiler checks which APIs can be called based on the type of the expression `pet`. When calling an overridden instance method, the JVM can dispatch Dog's version. Casting a valid reference only changes the type view; **it does not clone the object**. If the runtime class is incompatible, a downcast can throw `ClassCastException`.

In the dedicated lesson on declared type and runtime class, learners will contrast overriding/overloading, field hiding, generics, interfaces, and `getClass()`. For this foundational lesson, the key takeaway is that **a reference value and object identity do not change on their own when the type view changes**.

## 16. Arrays Are Objects; Each Slot Can Hold a Reference

~~~java
int[] values = {1, 2, 3};
int[] alias = values;
int[] copy = values.clone();
String[] names = new String[2];
~~~

This is a snippet inside a method. `values` and `names` are references to **array objects**. The elements of `int[]` hold primitive values; the two slots of `names` are references initially equal to null. `alias = values` shares the array object, so modifying `alias[0]` will be visible through `values[0]`. `copy` is a separate array object containing copies of the primitive values.

With `new Student[3]`, Java creates **one array** containing three null slots; it does not automatically create three Student objects. For `Student[]`, `clone()` only copies the element references (shallow copy). The object-arrays lesson will cover in greater depth the layers of aliasing, `Arrays.fill`, `Arrays.copyOf`, multidimensional arrays, and `ArrayStoreException`.

## 17. Collections: Same Reference Variable vs. Structural Copy

~~~java
java.util.List<String> original = new java.util.ArrayList<>();
original.add("A");
java.util.List<String> alias = original;
java.util.List<String> copy = new java.util.ArrayList<>(original);
~~~

This is a snippet inside a method. `alias` and `original` point to the same List, so structural mutations of the list appear in both. `copy` has its own list structure, but the **element references** can still be shared with the old list.

`List.copyOf(original)` creates/obtains an unmodifiable list, rejects null elements, does not guarantee a deep copy, and may reuse an eligible immutable list. When a class accepts or returns a mutable collection, it needs a contract on **ownership** and defensive copying if it wants to protect invariants. The aliasing lesson goes deeper into shallow/deep copying and sharing child objects.

## 18. The `this` Keyword Is Also a Reference, Not a Second Object

Inside a constructor or instance method:

~~~java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void add(int amount) {
        this.value += amount;
    }
}
~~~

`this` is an expression referring to **the current instance**. On the line `this.value = value`:

- The left-hand side is the field of the object being initialized.
- The right-hand side `value` is the constructor parameter of the same name.
- No new object is created merely by using `this`.
- `this` in each instance method call denotes the receiver of that call.

Distinguish `this` from `this(...)`: `this(...)` in a constructor is the syntax for **calling another constructor of the same class**; it does not create an extra instance. Instead, `new Counter(...)` is the expression that requests creating a new instance.

## 19. Variable Scope and Object Lifetime Are Not the Same

A local variable can only be used within its source-code **scope**, whereas an object can continue to be used after the method that created it finishes if a reference is passed/returned elsewhere.

Illustrative example:

~~~java
static Book create() {
    Book local = new Book("Java");
    return local;
}

// At the caller:
Book result = create();
~~~

`local` is a local variable of `create`. When the method ends, the name `local` is no longer an active local variable of that invocation. However, the reference value has been returned; `result` can use **the same Book object** after the `create` method finishes.

Therefore:

- "A variable going out of scope" does not mean "the object is destroyed immediately".
- An object can be referenced from a field, an array element, a collection, another local variable, a static field, or other data.
- An object with no remaining references that the program can semantically use may become unreachable, but **when the GC reclaims it is not guaranteed**.
- `System.gc()` is not a command that forces the JVM to immediately reclaim a specific object.
- There may be runtime optimizations that cause the physical allocation model not to match a diagram where "each object is always at a fixed heap location"; rely on observable behavior and contracts.

### When Dropping One Reference, an Object May Still Have Aliases

~~~java
Book first = new Book("Java");
Book alias = first;
first = null;
~~~

`alias` still references the Book object. Assigning `first = null` does not delete the Book object, nor does it turn `alias` into null. If the code still uses `alias`, the object still needs to have valid behavior.

## 20. A Static Field Can Hold a Reference Longer Than You Think

A static field is a member of the runtime class rather than belonging to a specific instance. If it holds a reference to an object, that object can remain reachable through the static field even after the original local variables have gone out of scope.

~~~java
class Cache {
    static Object latest;

    static void keep(Object item) {
        latest = item;
    }

    static void clear() {
        latest = null;
    }
}
~~~

This is an illustrative class. `keep(item)` copies the reference value into the static field `latest`; it does not create a new object. `clear()` assigns null to the static field, but it does not force the JVM to immediately reclaim the old object, and that object may still have other references.

Be careful with unbounded static collections/caches: if they keep retaining additional objects without an appropriate eviction policy, they can hold onto memory longer than expected. This is a common kind of **memory retention** in long-running applications.

### Class Loaders and Static State

You should not say "a static field lives forever until the JVM shuts down" as an absolute rule. Static state is tied to the corresponding runtime class; in systems using dynamic class loaders, a class can be unloaded when the appropriate runtime conditions are met. For small console programs, you can think of a static reference as existing while the class is still in use, though that is a simplified learning model.

## 21. Passing a Reference Variable into a Constructor

Example:

~~~java
class Team {
    private final java.util.List<String> members;

    Team(java.util.List<String> members) {
        this.members = members;
    }
}
~~~

The constructor receives **a copy of the reference value** to the list provided by the caller; assigning `this.members = members` causes the field to hold **the same reference**. If the List is mutable, the caller can modify the list's structure after creating Team, indirectly changing Team's state.

If you want to avoid that:

~~~java
class Team {
    private final java.util.List<String> members;

    Team(java.util.List<String> members) {
        this.members = java.util.List.copyOf(members);
    }

    java.util.List<String> members() {
        return members;
    }
}
~~~

This is an **alternative version** of the Team class; do not place two definitions with the same name together in one package. `List.copyOf` helps protect the list's structure in this case, provided the input is non-null and contains no null elements; if `members` is null, the method throws `NullPointerException`. You cannot infer that mutable element objects also automatically become immutable.

The right mindset is: **References can be shared; permission to modify a shared object must be designed and controlled.**

## 22. How to Read a Line of Code Involving References to Avoid Confusion

When encountering Java code with many variables and objects, identify them in order:

1. **Which variable?** Check the left-hand side and the declared type: `Book book`, `Object value`, `List<Item> items`.
2. **What value is being assigned?** `null`, a reference from another variable, a reference returned by a method, or the result of `new`.
3. **Is a new object created?** Look for an actual object-creation/factory/copy expression. Do not treat assignment as cloning.
4. **Which variables are aliasing the same object?** Draw arrows after each assignment.
5. **Does the statement modify the variable or the object?** `a = b` differs from `a.setValue(...)` and `a.field = ...`.
6. **Do the compile-time type and runtime type differ?** Upcasting does not create a new object; it changes which members are accessible through the reference.
7. **Comparing identity or value?** `==` for references asks whether they are the same object; `equals` asks about the equality contract.
8. **Is the object mutable or immutable?** Two references to the same String do not mean one variable can alter the contents of the old String.
9. **Could it be null?** Check dereferences before use.
10. **Where else might the object continue to be retained?** Return values, fields, arrays, collections, and static references can all keep an object in use later.

### Before-and-After Diagram Example

~~~java
Box a = new Box(1);
Box b = a;
b = new Box(2);
a.value = 3;
~~~

Assuming `Box` allows access to the `value` field in this context:

~~~text
After statement 1:
a ------> Box #1 { value=1 }

After statement 2:
a --+
    +----> Box #1 { value=1 }
b --+

After statement 3:
a ------> Box #1 { value=1 }
b ------> Box #2 { value=2 }

After statement 4:
a ------> Box #1 { value=3 }
b ------> Box #2 { value=2 }
~~~

This is an illustrative code snippet; simply tracking **every `new` and every reference assignment** allows you to accurately draw the relationships between variables and objects.

## 23. Common Misconceptions

| Incorrect or incomplete statement | Accurate explanation |
| --- | --- |
| "The variable `Student s` is the Student object itself." | `s` is a variable of a reference type; the object is the instance to which the reference can point. |
| "Declaring `Student s;` creates a Student." | It only declares the variable; there is no `new` yet. |
| "`Student b = a;` copies all fields." | It copies the reference and does not create a new object. |
| "If two objects have the same fields, `==` is true." | `==` compares reference identity, not fields. |
| "`new` merely assigns a value to a variable." | `new` requests creating an object; variable assignment is a separate operation. |
| "Assigning `a = new X()` modifies a's old object." | It replaces the reference value of `a`; the old object is not itself modified. |
| "`String` is a primitive because it can use literals." | `String` is a class, belonging to reference types. |
| "`Integer` stores a primitive just like `int`." | `Integer` is a wrapper reference type; a reference variable of this type can hold null. |
| "Java passes objects by reference like a C++ reference parameter." | Java passes **a copy of the reference value**. |
| "Reassigning an object parameter makes the caller's variable point to the new object." | No; reassigning the parameter only changes the parameter. |
| "`final List<?>` cannot have its elements changed." | `final` prevents reassigning the reference variable/field; a mutable object can still be modified. |
| "A reference is an exposed RAM address." | Java defines reference behavior without exposing a required raw-address representation. |
| "Having `null` means there is already an empty object." | Null means there is no object pointed to by that reference. |
| "When a local variable goes out of scope, the object disappears immediately." | The object may have other aliases; the GC does not guarantee immediate reclamation. |
| "`getClass()` and the declared type name are always the same." | A variable of a superclass type can hold a reference to a subclass instance. |
| "Array `clone()` performs a deep copy of all element objects." | Array `clone()` performs a shallow copy; element references can still share the same objects. |
| "`equals()` is always identity." | A class can override it to define value-based equality; records and String have their own rules. |
| "`System.identityHashCode` is a unique address." | An identity hash is not an address and does not guarantee uniqueness. |

## 24. Practice Exercises and Solutions

### Exercise 1 — Counting Objects

~~~java
Book a = new Book("A");
Book b = a;
Book c = new Book("A");
b = c;
~~~

Assume all object creations succeed. There are **two** `new Book(...)` expressions → **two Book objects**. After the last line, `a` points to object #1, while `b` and `c` point to object #2.

Results:

- `a == b` → false.
- `b == c` → true.
- `a == c` → false.

### Exercise 2 — Variable Assignment or Field Mutation?

~~~java
Box first = new Box(1);
Box alias = first;
alias.value = 5;
alias = new Box(9);
~~~

After these lines, the first object has `value = 5` and is still referenced by `first`. `alias` switches to a new Box object with `value = 9`. `first.value` is 5, and `alias.value` is 9. Reassigning alias does not restore the first object's value.

### Exercise 3 — Method Receiving a Parameter

~~~java
static void replace(Box value) {
    value = new Box(100);
}

// In the caller:
Box box = new Box(1);
replace(box);
~~~

`box` still points to the Box with `value = 1` because the method only reassigns **the parameter value**. If you want the caller to update its reference, one proper approach is `static Box replace(Box old) { return new Box(100); }` and then the caller assigns `box = replace(box);`.

### Exercise 4 — Null and Empty Arrays

~~~java
int[] missing = null;
int[] empty = new int[0];
int[] one = new int[1];
~~~

- `missing == null` → true; you must not use `missing.length`.
- `empty.length` → 0.
- `one.length` → 1; element `one[0]` defaults to 0.
- `empty == one` → false because they are two different array objects.

### Exercise 5 — Mutable and Immutable

~~~java
String s = "A";
String t = s;
s = s + "B";

StringBuilder x = new StringBuilder("A");
StringBuilder y = x;
x.append("B");
~~~

Afterward, `s` is `"AB"`, `t` is `"A"`; `x` and `y` both see `"AB"`. `String` is immutable, while `StringBuilder` is mutable.

### Exercise 6 — Does `final` Prevent Modifying an Object?

~~~java
final java.util.ArrayList<String> names =
        new java.util.ArrayList<>();
names.add("Mai");
~~~

Valid: it only modifies the ArrayList object without reassigning the `names` variable. If you write `names = new ArrayList<>();` after `names` has already been initialized, the compiler rejects it.

### Exercise 7 — Two Kinds of Equality

~~~java
record Key(int id) {}

Key a = new Key(7);
Key b = new Key(7);
Key c = a;
~~~

- `a == b` → false.
- `a.equals(b)` → true.
- `a == c` → true.
- `a.equals(c)` → true.

The snippets in Exercises 1–7 are **code fragments to place inside a practice class/method**; the `Book`/`Box` types require appropriate constructors/fields, and these are not standalone programs.

## 25. Completion Checklist

- [ ] I can distinguish between a **reference-type variable**, a **reference value**, and an **object instance**.
- [ ] I know that declaring a variable does not automatically create an object.
- [ ] I know that a `new Class(...)` expression completing normally provides a reference to a new object.
- [ ] I know that `a = b` copies the reference, without automatically copying the object.
- [ ] I can draw alias diagrams before/after `new` expressions and reassignments.
- [ ] I distinguish between modifying a reference variable and modifying an object's field.
- [ ] I understand that `null` points to no object and differs from an empty object.
- [ ] I know that primitive types differ from reference types, including String, wrappers, and arrays.
- [ ] I can explain Java pass-by-value for methods that receive an object.
- [ ] I distinguish between object identity (`==`) and contract-based equality (`equals`).
- [ ] I understand that a `final` reference does not guarantee an immutable object.
- [ ] I understand that upcasting/casting can change the type view but does not create a copy of the object.
- [ ] I know that `this` in an instance method refers to the current object and does not create another object.
- [ ] I know that variable scope and object lifetime are two different concepts.
- [ ] I do not infer object addresses from `identityHashCode` or force the JVM to perform GC on a predetermined schedule.
- [ ] I can run the Java 17+ examples myself, compare the output, and explain each variable's reference path.

**Conclusion:** A reference variable **stores a reference value or null**, not the object itself with all of its fields. An **object** is an entity with identity, a runtime type, and state/behavior; a **reference** allows the program to use that object; a **variable** is merely a place that stores a reference value according to scope and assignment rules. When you consistently separate these three conceptual layers, you will accurately understand the `new` operation, aliasing, method parameters, immutable objects, equality, and object lifetimes in Java.
