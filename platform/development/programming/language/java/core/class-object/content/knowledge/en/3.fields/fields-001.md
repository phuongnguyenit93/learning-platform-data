# Field Declarations: Data Types, Names, and Initial Values in Java

## Objectives

After this lesson, you can:

- Identify a **field** in a Java class declaration and distinguish it from local variables, parameters, and computed properties.
- Write syntactically valid field declarations: **modifier**, **type**, **name**, and **optional initializer expression**.
- Choose appropriate primitive types, reference types, arrays, and parameterized types; name fields clearly and restrict access appropriately.
- Explain default field values when no initializer is present, and distinguish fields from local variables, which must be assigned before being read.
- Understand when initializers, initializer blocks, and constructors execute; use `this` to distinguish a field from a parameter with the same name.
- Apply `final` and `static`, and avoid common mistakes such as using `var` for a field, reading uninitialized variables, or unintentionally sharing mutable objects.

## 1. What Is a Field?

A **field** is a variable declared directly inside the body of a class or a corresponding type that supports fields, outside of methods and constructors. A field belongs to either an **object** (instance field) or a **class** (static field), depending on whether the `static` keyword is present.

Example declarations inside a class:

~~~java
public class Book {
    private String title;
    private int pages = 120;
    private boolean available = true;
    private static int totalBooks;
}
~~~

In this snippet:

- `title`, `pages`, and `available` are **instance fields**: each `Book` object has its own corresponding fields.
- `totalBooks` is a **static field**: a field associated with the `Book` class, not created as a separate copy in each object.
- `private` is the access level. It helps prevent code outside the class from arbitrarily modifying state.
- The data type determines the set of valid values for the field: `String` is a reference type; `int` and `boolean` are primitive types.
- `= 120` and `= true` are **field initializers**, meaning expressions that supply values when the object/class is initialized.
- `title` and `totalBooks` do not have explicit initializers; they are still **default-initialized** by Java according to the rules for fields.

A variable declared **inside** a method, constructor, or block is a **local variable**, not a field:

~~~java
public class Example {
    private int total;  // field

    public void add(int amount) {  // amount is a parameter
        int extra = 2;             // extra is a local variable
        total += amount + extra;   // uses field total
    }
}
~~~

`total` exists as part of the object's state; `extra` belongs only to the execution scope of the method block. Java does not allow declaring two local variables with the same name in the same invalidly nested scope, whereas a field and a parameter with the same name can coexist and are distinguished with `this`.

## 2. Syntax for Declaring a Field

Basic structure:

~~~text
[modifier ...] DataType fieldName [= initializerExpression];
~~~

Examples:

~~~java
private int age;
private String fullName = "Chưa có tên";
public static final int MAX_ITEMS = 100;
~~~

Component breakdown:

| Component | Meaning | Example |
| --- | --- | --- |
| Access modifier | Restricts where the field can be used | `private`, `protected`, `public`, or omitted |
| Other modifiers | Adjusts characteristics of the field | `static`, `final`, and certain specialized modifiers |
| Data type | Specifies the type of value the field can hold | `int`, `double`, `String`, `int[]`, `List<String>` |
| Field name | Valid identifier to refer to the field | `age`, `fullName`, `MAX_ITEMS` |
| Initializer | Optional expression providing the initial value | `= 18`, `= "Java"`, `= new int[3]` |
| The `;` character | Terminates the declaration statement | Required at the end of a field declaration |

If there is no access modifier, the field has **package-private** access, meaning other code in the same package can access it according to the language rules; a subpackage is a different package. A field does not have to have an initializer, but **it must have a valid name and type**, except for out-of-scope special syntax such as certain enum/record declarations.

### 2.1. Choosing a Field Name

Java conventions typically use `lowerCamelCase` for fields: `studentName`, `createdAt`, `quantity`; and `UPPER_SNAKE_CASE` for constants with fixed semantics, typically `static final`: `MAX_RETRIES`, `DEFAULT_PORT`.

The name must be a **valid identifier**: it cannot start with a digit, contain a hyphen `-`, or use keywords such as `class`, `int`, `new`, etc. Java is case-sensitive, so `score` and `Score` are two different names. Although the syntax allows many kinds of Unicode names and the `_` character, in real-world source code you should choose names that express responsibility and follow consistent conventions.

### 2.2. Declaring Multiple Fields of the Same Type

This syntax is valid:

~~~java
private int x, y;
private int width = 10, height = 20;
~~~

The first declaration creates **two fields**, `x` and `y`, of type `int`; the next line declares `width = 10` and `height = 20`. An initializer **only attaches to the variable written immediately before the `=` sign** and does not automatically apply to the other names.

For example:

~~~java
int a, b = 5;
~~~

If these are **fields**, `a` is default-initialized to `0`, while `b` is `5`. If this declaration is placed inside a method, reading `a` before assigning to it causes a compile-time error because local variables are not automatically assigned a default value.

For clarity and to make it easier to add comments or modifiers later, it is good practice to write **each field on its own line** when they have distinct meanings.

## 3. Choosing a Data Type for a Field

A field must have a **declared type**. Common groups include:

| Type | Field Example | Represented Values |
| --- | --- | --- |
| `byte`, `short`, `int`, `long` | `private long fileSize = 1000L;` | Integers within the type's value range |
| `float`, `double` | `private double temperature = 36.5;` | Floating-point real numbers |
| `boolean` | `private boolean active = false;` | `true` or `false` |
| `char` | `private char grade = 'A';` | One UTF-16 code unit |
| Class/reference type | `private String name = "An";` | Reference to an object or `null` |
| Array | `private int[] scores = new int[3];` | Reference to an array object or `null` |
| Interface/generic | `private java.util.List<String> tags = new java.util.ArrayList<>();` | Reference to an object of a compatible type |

The choice of type must suit the data: `int` for quantities within a reasonable range; `long` for large counts; `boolean` for status flags; `String` for character strings; and `List<String>` for a list of tags. Primitive types **do not accept `null`**, whereas ordinary reference types can hold `null`.

For currency requiring decimal precision, `double` may be unsuitable due to binary floating-point representation. For instance, you can use `java.math.BigDecimal` with an explicit initial value:

~~~java
private java.math.BigDecimal price = new java.math.BigDecimal("19.90");
~~~

This is an **illustrative field declaration line**, placed inside a class. Choosing `BigDecimal` for currency data is a data-modeling decision; the field declaration keywords themselves do not determine rounding rules.

### 3.1. Paying Attention to Literals and Type Conversions

Java checks the type of the initializer expression at compile time:

~~~java
private int quantity = 12;
private long distance = 9_000_000_000L;
private float rate = 0.5f;
private double ratio = 0.5;
private char symbol = 'J';
private String label = "Java";
~~~

The characters `L` and `f` create `long` and `float` literals, respectively. If you use `9_000_000_000` without the `L` suffix, the integer literal exceeds the `int` range and is invalid. A floating-point literal like `0.5` defaults to `double`, so direct assignment to `float` typically requires `f` or an appropriate explicit cast.

Certain integer constant assignments can use a narrowing conversion permitted by Java when the constant is within the target type's range, such as `byte b = 100;`; however, `byte b = 200;` does not compile because it exceeds the `byte` range.

Do not use `var` to declare fields. **Local variable type inference** with `var` is only for permitted local variable contexts in Java, such as `var count = 1;` inside a method; for a field, you must write the concrete type:

~~~java
// Invalid when placed at class level:
// private var count = 1;

// Valid at class level:
private int count = 1;
~~~

## 4. Default Values When No Initializer Is Declared

When an object is created, **instance fields** are assigned default values before explicit initializers, initializer blocks, and constructors execute according to Java's initialization order. **Static fields** are also assigned default values when the class is prepared, prior to running the corresponding static initializers.

Table of default values for **fields**:

| Field Type | Default Value |
| --- | --- |
| `byte`, `short`, `int` | `0` |
| `long` | `0L` |
| `float` | `0.0f` |
| `double` | `0.0d` |
| `boolean` | `false` |
| `char` | `'\\u0000'` (code value `0`) |
| Any reference type, including `String`, arrays, and interfaces | `null` |

For example, `String name;` does not mean the empty string `""`; the initial value of the field is `null`. `int[] values;` does not automatically create an empty array; to have an array object, you must initialize it, such as `new int[0]` or `new int[3]`. With `new int[3]`, the three **elements of the array** themselves are `0` according to the default value rules for array components.

A default value is not always a **valid business value**. For instance, `price = 0` may be inappropriate when a price must be greater than 0, and `name = null` can cause a `NullPointerException` if used as a non-null string. Therefore, explicitly initialize fields or validate inputs in the constructor when invariants are required.

### 4.1. Fields Differ from Local Variables

Example:

~~~java
public class DefaultsVsLocals {
    int field; // Default 0

    void demo() {
        int local;
        // System.out.println(local); // Error: local variable not yet assigned
        local = 7;
        System.out.println(field + local);
    }

    public static void main(String[] args) {
        new DefaultsVsLocals().demo();
    }
}
~~~

Save in **`DefaultsVsLocals.java`**, and run:

~~~bash
javac DefaultsVsLocals.java
java DefaultsVsLocals
~~~

Output:

~~~text
7
~~~

The compiler allows reading `field` because Java assigns a default of `0`. The variable `local` is assigned `7` before being read. If you uncomment `System.out.println(local);`, the program will **not compile** due to violating the definite assignment rule.

## 5. Complete Example: Types, Names, Initial Values, `static`, and `final`

The file **`FieldDeclarationDemo.java`** below can be compiled and run with JDK 17 or later, with no external libraries needed.

~~~java
public class FieldDeclarationDemo {
    static final class Defaults {
        int number;         // 0
        boolean enabled;    // false
        char initial;       // character with code 0
        String text;        // null
        int[] values;       // null
    }

    static final class Item {
        private final String id;          // Assigned in constructor
        private String title = "Chưa đặt tên";
        private int quantity;             // Default 0
        private double price = 12.5;
        private boolean active = true;
        private String note;              // Default null
        private int[] monthly = new int[2];

        private static int createdCount;       // Shared across the Item class
        private static final int MAX_QUANTITY = 100;

        Item(String id, String title, int quantity) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id must not be blank");
            }
            if (quantity < 0 || quantity > MAX_QUANTITY) {
                throw new IllegalArgumentException("invalid quantity");
            }
            this.id = id;
            this.title = title;
            this.quantity = quantity;
            createdCount++;
        }

        String description() {
            return id + " | " + title
                    + " | qty=" + quantity
                    + " | price=" + price
                    + " | active=" + active
                    + " | note=" + note
                    + " | month0=" + monthly[0];
        }

        static int createdCount() {
            return createdCount;
        }
    }

    static final class InitializationOrder {
        int first = 1;
        int second = first + 2;

        {
            first = 10;
        }

        InitializationOrder() {
            second = first + 5;
        }
    }

    public static void main(String[] args) {
        Defaults defaults = new Defaults();
        System.out.println("defaults: int=" + defaults.number
                + ", bool=" + defaults.enabled
                + ", charCode=" + (int) defaults.initial
                + ", text=" + defaults.text
                + ", values=" + defaults.values);

        Item first = new Item("SKU1", "Bút", 3);
        Item second = new Item("SKU2", "Vở", 0);

        System.out.println(first.description());
        System.out.println(second.description());
        System.out.println("created=" + Item.createdCount()
                + ", max=" + Item.MAX_QUANTITY);

        InitializationOrder order = new InitializationOrder();
        System.out.println("order: first=" + order.first
                + ", second=" + order.second);
    }
}
~~~

Run in the directory containing the file:

~~~bash
javac -encoding UTF-8 FieldDeclarationDemo.java
java FieldDeclarationDemo
~~~

Exact output:

~~~text
defaults: int=0, bool=false, charCode=0, text=null, values=null
SKU1 | Bút | qty=3 | price=12.5 | active=true | note=null | month0=0
SKU2 | Vở | qty=0 | price=12.5 | active=true | note=null | month0=0
created=2, max=100
order: first=10, second=15
~~~

**Explanation:**

1. The fields in `Defaults` have no initializers, so they start with default values. To observe the invisible default `char`, the program casts it to `int` and prints the code value `0`.
2. The `price`, `active`, `title`, and `monthly` fields of `Item` are explicitly initialized. Specifically, `monthly` is a two-element array; `monthly[0]` has the value `0`.
3. `title` initially starts as `"Chưa đặt tên"`, and is then assigned in the constructor to the name passed in. The observed value after object creation is `"Bút"` or `"Vở"`.
4. `id` has `final` and no initializer at its declaration; every valid constructor must assign this field according to the rules before completing.
5. The two `Item` objects have their own separate instance fields. Meanwhile, `createdCount` is a `static` field, so both constructor calls increment a shared counter.
6. `MAX_QUANTITY` is both `static` and `final`, representing a fixed limit of the class. This field cannot be reassigned after initialization.
7. In `InitializationOrder`, `first = 1` and `second = 3` are assigned in order, then the instance initializer block runs and sets `first = 10`, and finally the constructor assigns `second = 15`. Therefore, the final output is `first=10, second=15`.

The example illustrates language rules and does not require you to always use initializer blocks or `static` fields. In typical application code, constructors and initializers directly at the declaration are usually more readable when there are no special requirements.

## 6. Initialization Timing: Field Initializers, Instance Initializers, and Constructors

Having a declaration with an initializer does not mean the expression is evaluated when the compiler reads the source file. Key steps to understand:

1. **New object**: Java allocates the object and assigns default values to instance fields; if inheritance is involved, superclass initialization rules apply before the corresponding initialization of the subclass.
2. **Object initializers**: within a class, instance field initializer expressions and instance initializer blocks execute in **textual order** when it is that class's turn to initialize its portion.
3. **Constructor**: the constructor body executes after completing the corresponding instance initialization steps; the constructor can overwrite fields that already had initializers. Chained constructor calls `this(...)` or superclass calls `super(...)` refine the exact order, but do not change the final meaning of fields belonging to each object.
4. **Static fields**: default-initialized during class preparation; static field initializers and static initializer blocks execute in textual order during class initialization according to JVM rules. They **do not run again on every `new` call**.

Short example in the same class:

~~~java
class Counter {
    static int seed = 10;   // Class field
    int value = 1;         // Per-object field

    Counter() {
        value = 5;
    }
}
~~~

If `new Counter()` succeeds, the `value` of the new object after the constructor runs is `5`, not `1`. If multiple objects are created, each object has its own `value`; `seed` is a field of the class. This is an illustrative declaration snippet and has no `main` method to run standalone.

**Declaration order can matter**: an initializer can read a field initialized earlier; a simple reference to a field declared later can cause an `illegal forward reference` error under Java rules. Even when code uses a reference form permitted by the compiler to a field whose initializer has not yet run, the value read at that moment may only be the default value. To avoid confusing bugs, do not design circular dependencies between field initializers.

## 7. `this`: Distinguishing Parameters and Fields with the Same Name

See the standalone runnable example **`FieldAssignmentDemo.java`**:

~~~java
public class FieldAssignmentDemo {
    static final class Point {
        private int x = 1;
        private int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        void moveRight(int x) {
            this.x += x;
        }

        void print() {
            int x = 99;
            System.out.println("local=" + x
                    + ", field=" + this.x
                    + ", y=" + this.y);
        }
    }

    public static void main(String[] args) {
        Point p = new Point(4, 5);
        p.moveRight(3);
        p.print();
    }
}
~~~

Compile/run:

~~~bash
javac FieldAssignmentDemo.java
java FieldAssignmentDemo
~~~

Output:

~~~text
local=99, field=7, y=5
~~~

In `Point(int x, int y)`, `x` and `y` without `this.` are **parameters**, whereas `this.x` and `this.y` are **fields of the current object**. Writing `x = x;` only reassigns the parameter to itself and does not update the field. Similarly, `print()` has a local variable `x = 99`, yet `this.x` still holds the object's actual state: `4 + 3 = 7`.

In a **static method**, there is no `this`, because the method is not bound to a receiving object. Static fields are typically referenced explicitly using `ClassName.fieldName`.

## 8. `final` and `static` in Field Declarations

These are two modifiers frequently used with field declarations, yet they have independent meanings:

| Declaration | Meaning |
| --- | --- |
| `int count;` | Reassignable instance field |
| `final int id = 7;` | Instance field assigned under `final` rules, cannot be reassigned |
| `static int created;` | Reassignable static field, shared at the class level |
| `static final int LIMIT = 100;` | Static final field: a fixed value after class initialization |

A **blank final field** is a `final` field without an initializer at its declaration. For a blank final instance field, the constructor must ensure the field is assigned exactly once across all normal completion paths according to definite assignment rules; alternatively, it can be assigned via an appropriate instance initializer. For a blank `static final` field, the assignment typically takes place in a static initializer.

Example:

~~~java
class ConnectionSettings {
    private final String host;
    private final int port;

    ConnectionSettings(String host, int port) {
        this.host = host;
        this.port = port;
    }
}
~~~

This is a valid illustrative class declaration. The compiler checks that both `final` fields are assigned before the constructor completes normally; the line `this.host = host` distinguishes the field from the parameter.

**`final` does not mean the object referenced by a field is immutable.** For example:

~~~java
private final java.util.List<String> tags = new java.util.ArrayList<>();
~~~

This is a valid field declaration inside a class. You cannot reassign `tags = new ArrayList<>()` after the field is initialized, yet you can still call `tags.add("java")` if the list is accessible. Similarly, `static final` with a mutable collection **does not make the collection immutable**. If immutable data is desired, you need to choose an appropriate type/API and reference-management strategy.

**Important:** A `static` field is shared state; you should not turn every field into `static` just to use it in `main`. Per-object fields allow two instances to maintain independent state. `static` fields can be appropriate for constants or intentionally shared counters/registries; if multiple threads update them concurrently, synchronization must also be considered.

## 9. Initializers with Reference Types and Mutable State

Consider these field declarations:

~~~java
private String title = "";
private int[] scores = new int[3];
private java.util.List<String> tags = new java.util.ArrayList<>();
~~~

If these are **instance fields**, each object instantiation of the class generally evaluates the expressions that create a new array or list, so each object receives its own array/list from the initializers above. `String` is immutable, so it does not suffer from the same content-modification issues as mutable collections.

Conversely:

~~~java
private static final java.util.List<String> SHARED_TAGS =
        new java.util.ArrayList<>();
~~~

`SHARED_TAGS` is **a static field** referencing a mutable list shared across the class. `final` prevents replacing the reference; it does not prevent modifying the list's contents. If every object manipulates that list, their states can affect one another.

Another source of sharing is **assigning a reference passed from outside**:

~~~java
class Basket {
    private final java.util.List<String> items;

    Basket(java.util.List<String> items) {
        this.items = items; // Keeps the same reference as the caller
    }
}
~~~

Two `Basket` objects passed the same `List` will have two separate `items` fields, yet both hold the same reference. To isolate the list when needed, you can make a defensive copy: `this.items = new java.util.ArrayList<>(items);`. This is a **shallow copy**: reference-type elements may still be shared.

If a reference field is not initialized, remember to check for `null` before calling methods on it, or initialize it completely via the constructor. For required state, the constructor is typically the appropriate place to check for `null` using `java.util.Objects.requireNonNull(value, "value")` or an equivalent business validation.

## 10. Common Field Declaration Mistakes

| Issue | Example / Symptom | Explanation and Fix |
| --- | --- | --- |
| Missing `;` | `private int age = 18` | Every field declaration must end with `;`. |
| Missing type | `private name = "An";` | Write `private String name = "An";`. |
| Using `var` at class level | `private var score = 10;` | Fields must declare an explicit type, such as `private int score = 10;`. |
| Wrong literal type | `float ratio = 0.5;` | Use `0.5f` or the `double` type depending on your needs. |
| Exceeding integer range | `byte level = 200;` | Choose a sufficiently wide type or adjust to a valid value. |
| Confusing fields and locals | Reading `int x;` inside a method before assignment | Locals do not get default values automatically; you must assign before reading. |
| Confusing `null` with an empty value | `String name;` followed by `name.length()` | Reference fields default to `null`; initialize or validate before use. |
| Forgetting `this` when names match | `Person(String name) { name = name; }` | Assign `this.name = name;` to update the field. |
| Reassigning `final` | `final int x = 1;` followed by `x = 2;` | `final` has a single-assignment rule; remove the reassignment or remove `final` if it needs to change. |
| Unassigned blank final | Constructor finishes without assigning a `final` field | Assign it along every constructor completion path according to Java rules. |
| Assuming `static` is per-object | `static int count;` while expecting each object to have its own counter | Use an instance field if the state belongs to each object. |
| Using `final` to "lock" a collection | `final List<String> list = new ArrayList<>();` | Only the reference cannot be reassigned; the collection's contents remain mutable. |
| Wrong initialization dependency order | An initializer reads another field whose initializer has not run yet | Order declarations properly and avoid circular dependencies among field initializers. |
| Exposing mutable state publicly | `public java.util.List<String> items;` | Consider `private`, control modifications through methods, and copy when needed. |

### Distinguishing Declaration from Usage

The declaration `private int score;` specifies the name, type, and access level while creating the corresponding field on each object; it **does not** automatically create a `Score` object or invoke any method. When assigning `score = 8;`, the field's value changes. When `private String owner = new String("An");` runs at initialization, the `new` expression is what actually creates the referenced `String` object. Not every initializer containing an expression necessarily creates a new object: for instance, `= null`, `= 10`, and `= existingReference` have different semantics.

An initializer is a Java expression, so it can invoke methods and cause side effects. However, avoid complex initializers that depend on I/O or unready state: that makes object initialization unpredictable and difficult to test.

## 11. Review Questions with Answers

**Question 1.** Given the following class-level declarations:

~~~java
int a, b = 7;
String name;
boolean ready = true;
~~~

After creating an object successfully, what are the initial values?  
**Answer:** `a = 0`, `b = 7`, `name = null`, `ready = true`. Only `b` has the initializer `7`; the remaining fields use their default values or corresponding initializers.

**Question 2.** Why does declaring `private var age = 18;` in a class cause an error, even though `var age = 18;` can be used inside a method?  
**Answer:** `var` supports type inference for permitted local variables; a field must specify its type in the declaration, such as `private int age = 18;`.

**Question 3.** Is the field `private final String id;` valid without `= ...`?  
**Answer:** Yes. This is a blank final field; a constructor or permitted initialization location must assign the field according to the definite assignment rules before object initialization completes normally.

**Question 4.** How does `private int[] values = new int[2];` differ from `private int[] values;`?  
**Answer:** The first form initializes an array of length 2 whose `int` elements are `0`. The second form does not yet reference any array, so its default value is `null`.

**Question 5.** Why is `this` needed in `User(String name) { this.name = name; }`?  
**Answer:** The parameter `name` shadows the field of the same name. `this.name` specifies the object's field that should receive the value from the parameter.

**Question 6.** Two objects both have `private static int count;`. Do they have two independent `count` values?  
**Answer:** No. `static` declares a field belonging to the class, shared in the class context; if per-object values are needed, remove `static`.

**Question 7.** Does `private final List<String> items = new ArrayList<>();` prevent `items.add("X")`?  
**Answer:** No. `final` prevents reassigning the field reference; it does not automatically make the `ArrayList` immutable. State needs to be protected through proper API design if modification should be prevented.

## Key Takeaways

A field declaration has the structure **modifier + type + name + optional initializer + semicolon**. A field has a valid default value according to its data type even without an initializer; this **differs from local variables**. The final value after object creation also depends on initializers, initializer blocks, and constructors. Choose appropriate types, use clear names, apply `private` for encapsulation, use `final` for fields that do not need reassignment, use `static` when state truly belongs to the class, and control references to mutable objects to avoid unintended data sharing.
