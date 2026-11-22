# Parameterized Constructors and Constructor Overloading in Java

A **constructor** is the component executed during the creation of a Java object with `new` or through corresponding instantiation mechanisms. A **parameterized constructor** allows the caller to supply data so that the object starts in a meaningful state. **Constructor overloading** allows a class to provide multiple ways to create an object, differing in the number, types, or order of parameters, while still adhering to the same validity rules of the class.

Lesson objectives: understand the syntax, distinguish constructors from methods, design easy-to-use overloads, organize `this(...)` and `super(...)` call chains, control initial state, explain duplicate-signature/ambiguity errors, and self-verify with a runnable **Java 17+** program.

## 1. What Is a Parameterized Constructor Used For?

Consider a `Book` class used to model books in inventory. Each object needs a title, an author, and a number of copies. Instead of instantiating an object with incomplete information and letting external code arbitrarily modify its fields, we can require the data at creation time.

Illustrative snippet placed inside a `Book` class:

~~~java
private final String title;
private final String author;
private int copies;

Book(String title, String author, int copies) {
    if (title == null || title.isBlank()) {
        throw new IllegalArgumentException("Tên sách không hợp lệ");
    }
    if (author == null || author.isBlank()) {
        throw new IllegalArgumentException("Tác giả không hợp lệ");
    }
    if (copies < 0) {
        throw new IllegalArgumentException("Số bản sao không được âm");
    }

    this.title = title;
    this.author = author;
    this.copies = copies;
}
~~~

When used:

~~~java
Book book = new Book("Java Core", "An", 5);
~~~

This is an illustrative call snippet, not a standalone program. The expression `new Book(...)` creates the object and then executes the initialization process. The arguments correspond to the constructor's three parameters. The constructor validates the data before assigning it to ensure that a successfully created object does not have an empty `title` or negative `copies`.

If the constructor throws an exception, the object creation expression **does not complete normally** and does not return a new reference to the `book` variable. That does not mean the JVM rolls back every side effect that the constructor already performed before throwing the exception: avoid writing external data, exposing `this` externally, or updating irreversible resources in an incomplete constructor.

## 2. Structure and Characteristics of a Constructor

Simple declaration template:

~~~text
[access-modifier] ClassName(Type1 param1, Type2 param2, ...) {
    // validate and set up state
}
~~~

Elements in square brackets are descriptive notation, not literal Java syntax to type verbatim.

| Component | Example | Meaning |
| --- | --- | --- |
| Constructor name | `Book` | Must match the simple name of the declaring class |
| Parameter list | `(String title, int copies)` | Supplies input data at initialization time |
| Access modifier | `public`, `protected`, `private`, or omitted | Controls where the constructor is allowed to be called |
| Constructor body | `{ ... }` | Sets up state and performs initialization logic |
| Exception declaration | `throws IOException` when needed | Indicates checked exceptions that may be thrown |
| Delegation call | `this(...)` or `super(...)` | Delegates to a constructor in the same class or superclass |

**A constructor does not declare a return type**, not even `void`. This is an important syntactic difference from a method:

~~~java
class Sample {
    Sample(int value) {
        System.out.println("Constructor: " + value);
    }

    void Sample() {
        System.out.println("Đây là method, không phải constructor");
    }
}
~~~

`Sample(int)` is a constructor because its name matches the class and it has no return type. `void Sample()` is a **method** named `Sample`, even though readers can easily confuse it. This snippet only illustrates a class and has no `main`.

Constructors **are not inherited and cannot be overridden**, and do not take `static`, `final`, `abstract`, or `synchronized` as corresponding methods do. Constructors can be overloaded with different parameter lists. A value-less `return;` can be used to exit a constructor in valid contexts, whereas `return someValue;` is invalid.

## 3. Default Constructors and No-Arg Constructors

These two concepts are often referred to interchangeably, yet they are distinct:

- **Compiler-provided default constructor:** appears when a class **declares no constructors at all**. For a normal class, the parameterless default constructor calls the superclass's parameterless constructor via `super()` according to language rules; its access modifier depends on the class declaration. It only works if the superclass constructor invocation is valid.
- **Programmer-written no-arg constructor (*explicit no-arg constructor*):** declared by the developer, and can set default values, check conditions, and delegate to another constructor.

Separate illustrative example:

~~~java
class Plain {
    int value;
    // No constructor written: Java provides a default no-arg constructor.
}

class Configured {
    int value;

    Configured() {
        value = 10;
    }

    Configured(int value) {
        this.value = value;
    }
}
~~~

With `new Plain()`, the `value` field defaults to 0. With `new Configured()`, `value` is set to 10.

**Key takeaway:** as soon as a class declares **any constructor of its own**, Java **does not automatically generate a default constructor**. Example intentionally designed not to compile:

~~~java
class OnlyParameterized {
    OnlyParameterized(String name) {
    }
}

class UseIt {
    void test() {
        new OnlyParameterized(); // Error: no no-arg constructor.
    }
}
~~~

If the API needs to allow `new OnlyParameterized()`, you must declare a no-arg overload yourself and determine valid default values. Do not add an empty constructor merely to avoid a compile error if the object genuinely requires mandatory data.

## 4. Overloading Constructors by Signature

Within a single class, multiple distinct constructors can be defined:

~~~java
class Ticket {
    Ticket() { }
    Ticket(int seats) { }
    Ticket(String code) { }
    Ticket(String code, int seats) { }
    Ticket(int seats, String code) { }
}
~~~

This is an **illustrative class definition**. The overloads differ because:

| Constructor | Parameter count | Ordered type list |
| --- | ---: | --- |
| `Ticket()` | 0 | Empty |
| `Ticket(int)` | 1 | `int` |
| `Ticket(String)` | 1 | `String` |
| `Ticket(String,int)` | 2 | `String`, then `int` |
| `Ticket(int,String)` | 2 | `int`, then `String` |

Like methods, constructors cannot be overloaded **merely by changing parameter names**:

~~~java
class Duplicate {
    Duplicate(int age) { }
    Duplicate(int count) { } // Error: both are Duplicate(int).
}
~~~

Constructors inherently **have no return type**, so distinguishing overloads by return type is out of the question. Adding access modifiers or a `throws` clause also does not produce a different constructor signature.

The fact that you can declare both `Ticket(String,int)` and `Ticket(int,String)` **does not mean the design should have both**. Two parameter orderings can easily cause semantic confusion; choose a consistent convention and only add overloads when they genuinely benefit the caller.

## 5. Designing Overloads by Delegating via `this(...)`

If all overloads set up the same fields, copying the validation logic verbatim into every constructor easily leads to inconsistencies. Java allows **one constructor to call another constructor in the same class** using `this(...)`.

Example:

~~~java
Book() {
    this("Chưa đặt tên");
}

Book(String title) {
    this(title, "Chưa rõ");
}

Book(String title, String author) {
    this(title, author, 0);
}

Book(String title, String author, int copies) {
    // Validate and assign all state here.
}
~~~

Thus:

~~~text
new Book()
  -> Book("Chưa đặt tên")
    -> Book("Chưa đặt tên", "Chưa rõ")
      -> Book("Chưa đặt tên", "Chưa rõ", 0)
        -> validate and assign fields
~~~

Constructors with fewer parameters serve to **supply defaults**; the constructor with the most parameters serves as the **primary initialization point**. If the validity rules for `copies` change later, only the central logic needs to be modified.

### Rules to Remember for `this(...)`

In **Java 17**, an explicit `this(...)` constructor invocation must be the **first statement in the constructor body**; you cannot place assignments, `println`, or `if` statements before it. A constructor that chooses `this(...)` cannot also call `super(...)` as another explicit constructor invocation in the same body.

The `this(...)` statement does not mean "create another object": it continues **initializing the same object** using another constructor. The delegation chain must not form a **cycle**:

~~~java
class BrokenChain {
    BrokenChain() {
        this(1);
    }

    BrokenChain(int value) {
        this(); // Error: recursive constructor invocation.
    }
}
~~~

This is an **intentional error example**. If a termination path to an actual initializing constructor is missing, the compiler rejects the recursive invocation chain.

## 6. Complete Example: Ways to Create a Book with Parameters

Create the file **`ConstructorOverloadingDemo.java`** with two top-level classes: a package-private `Book` class and a `public ConstructorOverloadingDemo` class containing `main`.

~~~java
import java.util.Objects;

class Book {
    private final String title;
    private final String author;
    private int copies;

    Book() {
        this("Chưa đặt tên");
    }

    Book(String title) {
        this(title, "Chưa rõ");
    }

    Book(String title, String author) {
        this(title, author, 0);
    }

    Book(String title, String author, int copies) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Tên sách không hợp lệ");
        }
        if (author == null || author.isBlank()) {
            throw new IllegalArgumentException("Tác giả không hợp lệ");
        }
        if (copies < 0) {
            throw new IllegalArgumentException("Số bản sao không được âm");
        }

        this.title = title;
        this.author = author;
        this.copies = copies;
    }

    // A user-defined copy constructor, not an automatic copying
    // feature provided by Java.
    Book(Book source) {
        this(Objects.requireNonNull(source, "source").title,
                source.author, source.copies);
    }

    void addCopies(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số cộng phải dương");
        }
        copies = Math.addExact(copies, amount);
    }

    String summary() {
        return title + " | " + author + " | " + copies;
    }

    int copies() {
        return copies;
    }
}

public class ConstructorOverloadingDemo {
    public static void main(String[] args) {
        Book first = new Book();
        Book second = new Book("Java 17");
        Book third = new Book("Clean Architecture", "Lan");
        Book fourth = new Book("OOP thực hành", "Minh", 5);
        Book copy = new Book(fourth);

        System.out.println(first.summary());
        System.out.println(second.summary());
        System.out.println(third.summary());
        System.out.println(fourth.summary());
        System.out.println(copy.summary());
        System.out.println("Cùng object: " + (fourth == copy));

        fourth.addCopies(2);
        System.out.println("Bản gốc sau cộng: " + fourth.copies());
        System.out.println("Bản sao: " + copy.copies());

        try {
            new Book("Lỗi", "An", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }
    }
}
~~~

Open a terminal in the directory containing the file, using Java 17 or later:

~~~bash
javac -encoding UTF-8 ConstructorOverloadingDemo.java
java ConstructorOverloadingDemo
~~~

**Stdout:**

~~~text
Chưa đặt tên | Chưa rõ | 0
Java 17 | Chưa rõ | 0
Clean Architecture | Lan | 0
OOP thực hành | Minh | 5
OOP thực hành | Minh | 5
Cùng object: false
Bản gốc sau cộng: 7
Bản sao: 5
Từ chối: Số bản sao không được âm
~~~

### Examining Each Constructor Call

| Expression | Selected overload | Initial state |
| --- | --- | --- |
| `new Book()` | `Book()` | Default title and author, 0 copies |
| `new Book("Java 17")` | `Book(String)` | Default author, 0 copies |
| `new Book("Clean Architecture", "Lan")` | `Book(String,String)` | 0 copies |
| `new Book("OOP thực hành", "Minh", 5)` | `Book(String,String,int)` | 5 copies |
| `new Book(fourth)` | `Book(Book)` | Copies the values of the three fields at the time of the call |

Every creation path leads to `Book(String,String,int)` and goes through the same data validation. The `title` and `author` fields are `final`, so they are assigned once in the initialization chain; `copies` is a mutable field modified through the `addCopies` behavior.

`new Book(fourth)` **creates a different object**. Afterward, `fourth.addCopies(2)` only increments the copy count on `fourth` without modifying the primitive `copies` field of `copy`. Because `String` is immutable, sharing the title/author string reference values in the example does not allow modifying the string contents in place.

**Note on copy constructors:** Java does not automatically generate a `Book(Book)` constructor. This is an overload defined by the author. If a class contains a `List`, array, or mutable sub-object, the copy constructor must explicitly decide between a **shallow or deep copy**, avoiding the assumption that `new Book(other)` automatically creates a deep copy.

## 7. `this.field` and Parameters with the Same Name

In the primary constructor:

~~~java
this.title = title;
this.author = author;
this.copies = copies;
~~~

On the left side, `this.title` refers to the **field** belonging to the object being created; `title` on the right side is the **constructor parameter**. Using `this` is the way to distinguish two identifiers with the same name in the current scope.

If you write `title = title;`, both occurrences of `title` can be resolved as the **parameter**, because the parameter shadows the field name; the statement does not set the field as intended. If the `title` field is a blank final field, the compiler may also report that it has not been assigned by the end of the constructor.

Distinguish between:

- `this.title`: accesses a field of the current object.
- `this(...)`: **calls another constructor in the same class**.
- `super(...)`: **calls a superclass constructor**.
- `new Book(...)`: **creates a new object** and initializes it.

These four forms are all related to the initialization process, yet they have different meanings. `this(...)` does not create another new object, whereas `new` typically creates a new object according to the semantics of a class instance creation expression.

## 8. Constructor Overloading and Overload Resolution

When encountering `new Book("Java 17")`, the compiler examines the **accessible constructors** of that class and determines the most specific applicable overload based on the **compile-time types of the argument expressions**. The JVM does not try constructors one by one from top to bottom to see which one accepts the data.

Conversions such as **primitive widening**, **boxing/unboxing**, and **varargs** can participate in overload selection just as in overloaded method resolution. How `null` is handled also depends on the reference types of the parameters.

Create the standalone program **`ConstructorResolutionDemo.java`**:

~~~java
class Ticket {
    Ticket(int seats) {
        System.out.println("int");
    }

    Ticket(long seats) {
        System.out.println("long");
    }

    Ticket(Integer seats) {
        System.out.println("Integer");
    }

    Ticket(int... seats) {
        System.out.println("varargs:" + seats.length);
    }
}

public class ConstructorResolutionDemo {
    public static void main(String[] args) {
        new Ticket(3);
        new Ticket(3L);
        new Ticket(Integer.valueOf(3));
        new Ticket();
        new Ticket(3, 4);
        new Ticket(new int[] {5, 6});
    }
}
~~~

Run:

~~~bash
javac ConstructorResolutionDemo.java
java ConstructorResolutionDemo
~~~

**Stdout:**

~~~text
int
long
Integer
varargs:0
varargs:2
varargs:2
~~~

**Why?** `new Ticket(3)` uses an `int` literal type and selects `Ticket(int)`; `3L` is a `long`; `Integer.valueOf(3)` is already an `Integer` object. The no-argument call selects `Ticket(int...)` with an empty array. The two arguments `3, 4` are wrapped into varargs, while `new int[]{5, 6}` passes an existing array.

This program **does not declare `Ticket()`**, yet `new Ticket()` is still valid because the varargs constructor accepts **0 elements**. This is not a compiler-generated default constructor: because the class already declares constructors, the compiler does not provide a default constructor.

### Selection Can Become Unpredictable

If a class declares `Ticket(long)` and `Ticket(Integer)` but **does not have `Ticket(int)`**, the call `new Ticket(3)` selects `Ticket(long)` because primitive widening is considered before boxing. When designing an API, do not rely on callers guessing this conversion precedence; avoid providing too many primitive/wrapper overloads with differing behavior.

## 9. `null` Cases and Ambiguous Constructors

Example **intentionally causing an error at the call site**:

~~~java
class Parcel {
    Parcel(String label) {
    }

    Parcel(Integer number) {
    }
}

class ParcelUsage {
    void use() {
        // new Parcel(null); // Error if uncommented: ambiguous constructor.
        new Parcel((String) null);
        new Parcel((Integer) null);
    }
}
~~~

Both `Parcel(String)` and `Parcel(Integer)` are valid and have distinct signatures. However, `new Parcel(null)` has no single most specific overload: `null` matches both reference types, which have no subtype relationship with each other.

Writing `new Parcel((String) null)` can resolve **compile-time ambiguity**, but it does not guarantee that a constructor **accepts null under business rules**. If the constructor performs an `Objects.requireNonNull` check, the cast call will still throw a `NullPointerException`.

If `Parcel(Integer)` is replaced with `Parcel(Object)`, when calling `new Parcel(null)`, the compiler can select `Parcel(String)` because `String` is more specific than `Object`. However, being able to resolve an overload does not imply that `null` is a valid input.

**Good design** should not force callers to cast `null` just to select a way to create an object. When there are two fundamentally different ways to initialize an object, consider **named static factory methods** or types with clear intent.

## 10. Constructors with Varargs

Varargs are also valid in constructors; the varargs parameter, if present, must be the last parameter:

~~~java
class TagList {
    private final java.util.List<String> tags;

    TagList(String... tags) {
        if (tags == null) {
            throw new IllegalArgumentException("tags không được null");
        }
        this.tags = java.util.List.copyOf(
                java.util.Arrays.asList(tags));
    }
}
~~~

This is an **illustrative class definition** without `main`. The following expressions are all valid when placed inside a method:

~~~java
new TagList();
new TagList("java");
new TagList("java", "oop");
new TagList(new String[] {"java", "oop"});
~~~

`new TagList()` passes an empty varargs array. `new TagList((String[]) null)` passes a **null array argument** and will be rejected by the check in the constructor. `new TagList((String) null)` passes an array containing **one null element**; `List.copyOf` rejects null elements with a `NullPointerException`.

If a class has both `TagList(String[] values)` and `TagList(String... values)` constructors, the two declarations **collide in signature**: a varargs parameter corresponds to the array type `String[]`.

A varargs call using an existing array can share that array reference with the caller; in the `TagList` example, `List.copyOf(Arrays.asList(tags))` creates a separate list that cannot be modified through the API, but it **does not perform a deep copy** of mutable element objects if the element type is not immutable.

## 11. Superclass Constructors and `super(...)`

Constructors **are not inherited** from the superclass. When instantiating a subclass, a superclass constructor must participate in the initialization process before the subclass's initialization completes.

Create the complete file **`ConstructorInheritanceDemo.java`**:

~~~java
class Person {
    private final String name;

    Person(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.name = name;
    }

    String describe() {
        return "Person: " + name;
    }
}

class Student extends Person {
    private final int grade;

    Student(String name, int grade) {
        super(name);
        if (grade < 1 || grade > 12) {
            throw new IllegalArgumentException("Khối lớp không hợp lệ");
        }
        this.grade = grade;
    }

    @Override
    String describe() {
        return super.describe() + "; grade=" + grade;
    }
}

public class ConstructorInheritanceDemo {
    public static void main(String[] args) {
        Student student = new Student("An", 8);
        System.out.println(student.describe());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 ConstructorInheritanceDemo.java
java ConstructorInheritanceDemo
~~~

**Stdout:**

~~~text
Person: An; grade=8
~~~

In `Student(String,int)`, `super(name)` calls the `Person(String)` constructor. After the required superclass initialization completes, the `Student` constructor validates and assigns `grade`.

In **Java 17**, an explicit `super(...)` constructor invocation must be the **first statement** of a subclass constructor. If there is no explicit `this(...)` or `super(...)` call, Java inserts an implicit `super()` call according to the applicable rules.

### When the Superclass Has No No-Arg Constructor

In the example above, `Person` declares only `Person(String)`, so **there is no default `Person()` constructor**. If you write:

~~~java
class BrokenStudent extends Person {
    BrokenStudent() {
        // The compiler implicitly looks for super();, but Person() does not exist.
    }
}
~~~

This is an **intentional compilation error example**. Fix it by calling an accessible superclass constructor, such as `super("Ẩn danh");`, or by redesigning the subclass's required data. Do not add `Person()` if every `Person` must have a valid name.

**Do not interpret `super(...)` as instantiating a second, independent `Person` object.** It initializes **the superclass portion of the same `Student` object** being created.

## 12. Initialization Order and `final` Fields

When creating an instance of a normal class, Java sets default values for instance fields, executes the superclass initialization chain, and runs field initializers, instance initializer blocks, and constructor bodies in the order specified by the JLS.

A practical way to remember this for a superclass/subclass hierarchy:

1. The object is allocated, and instance fields first hold their **default values**.
2. The constructor chain up to `Object` is executed according to the `this(...)`/`super(...)` mechanism.
3. The superclass initialization parts complete before the corresponding initialization parts of the subclass complete.
4. Field initializers and instance initializer blocks of **each class** execute in that class's textual order at the appropriate initialization phase.
5. Finally, the body of the constructor selected through the delegation chain completes, or an exception is thrown if initialization fails.

You should not infer a simplistic order such as "all field initializers of every class run before all constructors", because superclass/subclass hierarchies and `this(...)` have distinct phases.

Small example **`InitializationOrderDemo.java`**:

~~~java
class Base {
    int x = print("Base field");

    Base() {
        print("Base constructor");
    }

    static int print(String message) {
        System.out.println(message);
        return 1;
    }
}

class Derived extends Base {
    int y = print("Derived field");

    Derived() {
        print("Derived constructor");
    }
}

public class InitializationOrderDemo {
    public static void main(String[] args) {
        new Derived();
    }
}
~~~

~~~bash
javac InitializationOrderDemo.java
java InitializationOrderDemo
~~~

Stdout:

~~~text
Base field
Base constructor
Derived field
Derived constructor
~~~

Here the `Derived()` constructor does not write `super()`, so Java calls the `Base()` constructor implicitly. `Base`'s field initializer runs before the body of `Base()`, and then `Derived`'s field initializer runs before the body of `Derived()`.

### `final` Fields and Multiple Constructors

A *blank final instance field* must be fully assigned according to **definite assignment** rules along every valid initialization path. In `Book`, we assign `title` and `author` in the core constructor; the overloads simply forward to it, avoiding missing an assignment or reassigning a `final` field.

Writing each constructor independently and forgetting to assign a `final` field is a compile error. Conversely, a field with an initializer `private final int size = 1;` cannot be reassigned with `size = 2;` inside a constructor. `final` prevents reassigning the **field** itself; it does not automatically make the object referenced by that field immutable.

## 13. Validating Input Data and Avoiding Improperly Initialized Objects

A constructor should establish **invariants** (state rules that must always hold) right from the start. For `Book`:

- `title` is non-`null` and not whitespace-only;
- `author` is non-`null` and not whitespace-only;
- `copies >= 0`.

Placing these rules in the core constructor keeps all overloads consistent. If the data is invalid, the constructor throws `IllegalArgumentException` before assigning fields. Validity conditions must also be maintained in **methods that mutate state after initialization**, such as `addCopies`.

**Not every constructor should have a large number of checks.** What needs to be validated depends on the API boundary: required data, resource state, business meaning, or the validity of strings or quantities.

### Computing Before Updating

If a constructor computes values from parameters, handle overflow, `null`, or invalid data early and explicitly. For operations with multiple external side effects (writing files, emitting events, modifying objects held by the caller), constructor failure **does not automatically roll back those changes**.

In a class that manages resources such as sockets or files, a partial initialization failure may require closing resources that have already been opened. Do not publish the `this` reference of a partially initialized object to listeners or other threads; doing so can allow other code to observe an unready state.

## 14. Constructor Access Modifiers and Static Factories

Constructors can be declared `public`, `protected`, `private`, or left with default package-private access. Access level determines **who is allowed to create an object using that constructor**, together with the class's access level and relevant package/module rules.

Example:

~~~java
public final class UserId {
    private final String value;

    private UserId(String value) {
        this.value = value;
    }

    public static UserId of(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("User ID không hợp lệ");
        }
        return new UserId(value);
    }
}
~~~

This is an **illustrative class definition**; to compile it separately, you must save it to a file named `UserId.java`. `new UserId("u1")` **cannot be called from code outside the class** because the constructor is `private`; callers use `UserId.of("u1")`.

Static factories named like `of`, `from`, or `parse` express intent clearly instead of forcing callers to distinguish among too many constructor overloads. They can also return an existing object, an appropriate subtype, or implement caching by design; a constructor with `new` creates a new object according to standard instance creation semantics.

When there are many independent optional parameters, consider a **builder or request object** instead of creating every combination of overloads:

~~~java
// Illustrates using an application-defined builder.
OrderSettings settings = OrderSettings.builder()
        .currency("VND")
        .retryCount(3)
        .timeout(java.time.Duration.ofSeconds(5))
        .build();
~~~

This is an **API idea, not standalone runnable code**, because `OrderSettings` is not yet defined. A builder can add boilerplate code; only use one when the number of options makes constructors hard to read.

## 15. Common Pitfalls with Constructor Overloading

| Error or misconception | Why it is wrong | How to handle it |
| --- | --- | --- |
| Writing `void Book(...)` and thinking it is a constructor | Because it has a return type, it is a **method** | Remove the return type and keep the name matching the class |
| Defining a parameterized constructor and then calling `new Book()` | The compiler no longer generates a default constructor automatically | Declare `Book()` explicitly if sensible default values exist |
| Renaming parameters to create a new overload | `Book(int count)` and `Book(int copies)` have the same signature | Change the parameter count, types, or order meaningfully |
| Calling `this(...)` after an assignment in Java 17 | An explicit constructor invocation must come first | Place `this(...)` as the first statement |
| Having `Book()` call `Book(String)` and vice versa | Recursive constructor invocation chain | Terminate at a core constructor |
| Calling `super()` when the superclass only has parameterized constructors | No parameterless superclass constructor is found | Call a valid `super(args)` |
| Thinking constructors are inherited or overridden | A constructor is an initializer of its own declaring class | Declare separate constructors in the subclass and call the superclass |
| Writing multiple overloads with inconsistent validation | Allows paths that construct an invalid object | Place core logic and validation in a shared constructor |
| Assuming `new Book(other)` automatically performs a deep copy | A copy constructor's behavior is defined by its author | Explicitly specify shallow vs. deep copy for mutable fields |
| Declaring both `Book(String)` and `Book(Integer)` and calling `new Book(null)` | The compiler cannot choose a single most specific overload | Avoid ambiguous APIs or cast intentionally |
| Assigning a `final` field in every constructor along a `this(...)` chain | A `final` field could be reassigned | Assign it only at the valid initialization site |
| Assuming a constructor error automatically rolls back side effects | An exception does not undo writes external to the object | Validate early and manage resources carefully |
| Thinking a `this(...)` call creates a new object | Constructor delegation still initializes the same instance | Distinguish `this(...)` from `new ClassName(...)` |

## 16. Choosing Which Overloads Are Necessary

Simply increasing the number of parameters does not mean you should add another constructor. An easy-to-use set of overloads typically satisfies:

1. **All overloads represent the same object concept**; they differ mainly in how data is supplied or the level of configuration.
2. **Required data is not obscured** by a no-arg constructor with arbitrary default values.
3. **Parameter order and units are clear**; avoid multiple consecutive `String`, `int`, or `boolean` parameters that are easy to swap.
4. **One core constructor** manages validation and establishes invariants where appropriate; shorter overloads only delegate.
5. **No ambiguity with `null`, varargs, or primitive/wrapper conversions** in common call patterns.
6. **`final` fields and resources are properly initialized**, without leaving the object in a usable state with missing data.
7. **Defaults and error conditions are documented**; callers know what author and copy count `new Book("Java")` produces.
8. **Test every initialization path** along with boundary values and failure scenarios.

Remember that overload selection happens at **compile time** based on argument types, not the order in which constructors appear in the file. Selecting one constructor **does not mean** the code of other constructors does not run: if that constructor uses `this(...)`, initialization continues through the defined delegation chain.

## 17. Self-Practice Exercises and Answers

**Question 1.** A class declares `Member(String name)`. Can you call `new Member()`? How can you provide a no-arg constructor with a default name?

**Question 2.** Can the two declarations `Member(int age)` and `Member(int years)` coexist? If not, why?

**Question 3.** When `Book()` calls `this("Chưa đặt tên")`, how many `Book` objects are created by a single `new Book()` statement? Can other constructors be executed?

**Question 4.** Why does the following code cause an error in Java 17?

~~~java
Member(String name) {
    System.out.println("init");
    this(name, 0);
}
~~~

Rewrite it so that constructor delegation is valid. The snippet above is an intentional error example, assuming an overload `Member(String,int)` exists.

**Question 5.** If the superclass only has `Parent(String)`, can the subclass `Child()` omit `super(...)` and rely on the implicit `super()`?

**Question 6.** Given two constructors `Packet(String)` and `Packet(Integer)`, is `new Packet(null)` valid? How does `new Packet((String)null)` differ?

**Question 7.** In the `Book(Book source)` example, why does `copy.copies()` remain 5 after `fourth.addCopies(2)`? Can that be generalized to every mutable reference field?

**Question 8.** State when to use multiple overloaded constructors and when to use a static factory or a builder.

**Suggested answers:**

1. No: declaring a parameterized constructor prevents the compiler from automatically adding the default constructor. Write `Member() { this("Ẩn danh"); }` alongside the appropriate `Member(String)` overload.
2. No; both have the signature `Member(int)`; parameter names do not distinguish overloads.
3. Only **one object**, but the constructors in the `this(...)` chain can be executed sequentially to set up that object.
4. In Java 17, `this(...)` must appear first in the body: `Member(String name) { this(name, 0); }`. If logging is needed afterward, place `println` after the `this(...)` statement.
5. No, if `Parent()` does not exist or is not accessible; a valid `super(args)` call is required.
6. Ambiguous, because both accept `null` and neither type is more specific; casting `(String)null` selects the `String` overload, though it must still satisfy preconditions.
7. The two objects have two separate `int copies` fields, whose **numeric value** was copied at initialization time. For mutable reference fields, a shallow copy can still share sub-objects, so this cannot be generalized.
8. Overloads are appropriate when there are a few ways to supply data for the **same way of creating an object**. A factory or builder is appropriate when you need clear intent-revealing names, control over object creation, or many configuration options.

## 18. References

- [Java Language Specification 17, §8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructor syntax, signatures, overloading, access modifiers, default constructors, and `this`/`super` invocations.
- [Java Language Specification 17, §12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): instance creation and initialization process.
- [Java Language Specification 17, §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): how `new` selects a constructor and creates an instance.
- [Java SE 17 API — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)): rejecting null references in copy constructors.

**Key takeaway:** parameterized constructors help objects start in a **valid state**; constructor overloading provides **multiple sensible ways to initialize**; `this(...)` centralizes default rules and validation, while `super(...)` initializes the superclass portion. Distinguish between a no-arg constructor that **you declare** and a default constructor that the **compiler provides only when a class declares no constructors at all**, and avoid overloads that leave callers uncertain about which constructor will be selected.
