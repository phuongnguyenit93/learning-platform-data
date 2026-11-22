# Introducing `enum`, `record`, and `interface` — Reading Java 17+ Syntax

## 1. Quickly Recognizing the Three Declaration Kinds

Java does not only have `class`. When reading source code, you will frequently encounter:

~~~java
enum Priority { LOW, MEDIUM, HIGH }

record Point(int x, int y) {}

interface Printable {
    String label();
}
~~~

| Keyword | Primary purpose | Quick reading |
|---|---|---|
| `enum` | Represents a fixed set of named values | `Priority.MEDIUM` is a constant of type `Priority` |
| `record` | Declares a data carrier type with *components* | `new Point(2, 3)` has accessors `x()`, `y()` |
| `interface` | Defines a contract that other types can implement | `class/record X implements Printable` commits to providing `label()` |

All three produce **reference types**, not primitive types like `int`. This lesson focuses on **reading syntax accurately and basic usage** on Java 17, before diving deep into OOP design.

## 2. `enum`: Named Constants with an Explicit Type

~~~java
enum Priority {
    LOW, MEDIUM, HIGH
}

Priority current = Priority.MEDIUM;
System.out.println(current);
~~~

**Exact stdout:**

~~~text
MEDIUM
~~~

- `Priority` is the `enum` type name, and `LOW`, `MEDIUM`, `HIGH` are constants of that type.
- `Priority.MEDIUM` is not the string `"MEDIUM"`; it is a value of type `Priority`.
- `Priority.values()` returns an array containing the constants in declaration order; `Priority.valueOf("MEDIUM")` looks up the constant with that exact name.
- `current.name()` returns the constant's name; `current.ordinal()` is its 0-based position, though **you should not store ordinal as a durable business code** because reordering constants changes the numbers.
- An `enum` can have fields, methods, and constructors, though at a basic level simply listing constants may suffice.

~~~java
String action = switch (current) {
    case LOW -> "read";
    case MEDIUM -> "review";
    case HIGH -> "urgent";
};
System.out.println(action);
~~~

**Exact stdout:**

~~~text
review
~~~

This is a valid **switch expression** in Java 17: the branches cover every existing constant of `Priority`. You cannot write `new Priority()` to arbitrarily create extra enum constants.

## 3. `record`: Concise Declaration of a Data Type

~~~java
record Point(int x, int y) {}

Point p = new Point(2, 3);
System.out.println(p.x());
System.out.println(p.y());
System.out.println(p);
~~~

**Exact stdout:**

~~~text
2
3
Point[x=2, y=3]
~~~

`record Point(int x, int y)` declares two **record components** `x` and `y`. Java automatically provides several members that otherwise have to be written manually:

- A canonical constructor matching the components, e.g., `new Point(2, 3)`.
- Accessors named `x()` and `y()`, **not** `getX()`/`getY()` by default.
- `equals`, `hashCode`, and `toString` based on the components.
- Component fields are `private final` in the record and cannot be reassigned after initialization.

A record can still have its own methods and **validate data at creation time** via a compact constructor:

~~~java
record Lesson(String title, int minutes) {
    Lesson {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("blank title");
        }
        if (minutes < 0) {
            throw new IllegalArgumentException("negative minutes");
        }
        title = title.strip();
    }
}
~~~

`Lesson { ... }` is a **compact canonical constructor**: write validation/normalization logic, not a method named `Lesson`. After this body, Java assigns the processed component parameter values to the corresponding fields.

**Important:** `record` does not mean *deeply immutable*. If a component is an array or mutable object, the record can still hold a reference to data that can be mutated. A record is `final` (cannot be extended via `extends`); it can `implements interface`.

## 4. `interface`: Behavior Contract

~~~java
interface Describable {
    String label();

    default String summary() {
        return "Named:" + label();
    }

    static String kind() {
        return "describable";
    }
}
~~~

Reading the syntax:

- `String label();` declares an abstract method (implicitly `public abstract`); there is no body here.
- `default String summary() { ... }` has a **default body** that implementing classes can use or override.
- `static String kind() { ... }` is a static method on the interface, invoked as `Describable.kind()`.
- A class or record uses `implements Describable` and must provide implementations for unimplemented abstract methods.
- The method implementing `label()` from the interface must be `public`; you cannot reduce its visibility to package-private or `private`.

~~~java
record Lesson(String title, int minutes) implements Describable {
    @Override
    public String label() {
        return title;
    }
}
~~~

The snippet above only illustrates the declaration shape; the complete program in Section 6 adds a compact constructor for data validation.

**Do not write** `new Describable()`: an interface is not a concrete class that can be instantiated directly. However, a variable of interface type can **reference an object of a class/record implementing it**:

~~~java
Describable item = new Lesson("Java", 30);
System.out.println(item.label());
System.out.println(item.summary());
~~~

**Exact stdout:**

~~~text
Java
Named:Java
~~~

Java also supports a class implementing multiple interfaces, and an interface extending one or more other interfaces. Do not confuse the keyword `implements` (fulfilling a contract) with `extends` (permitted inheritance relationship between types).

## 5. Comparing the Three Types Side by Side

| Difference | `enum` | `record` | `interface` |
|---|---|---|---|
| Commonly used for | Finite states/options | Data bundle with named fields | Behavior contract |
| Creating values | Use predeclared constants | Typically `new RecordName(...)` | Cannot instantiate directly |
| Access example | `Priority.HIGH` | `lesson.title()` | `item.label()` |
| Methods with bodies | Can be declared | Can be declared | `default`, `static` (and `private` helpers in modern Java) |
| Can implement interfaces | Yes | Yes | Other interfaces can extend it |

When reading the signature `record Lesson(...) implements Describable`, read in order: defines the **record type** `Lesson`, declares components in parentheses, then confirms it **provides behavior** according to `Describable`.

In Java 17, all three syntaxes above are **stable, without needing preview features enabled**. Records became a standard feature in Java 16; enums and interfaces have existed in earlier Java versions.

## 6. Complete Java 17+ Program

Save exact file **`EnumRecordInterfaceDemo.java`**:

~~~java
public final class EnumRecordInterfaceDemo {
    private EnumRecordInterfaceDemo() {}

    enum Priority {
        LOW, MEDIUM, HIGH
    }

    interface Describable {
        String label();

        default String summary() {
            return "Named:" + label();
        }

        static String kind() {
            return "describable";
        }
    }

    record Lesson(String title, int minutes) implements Describable {
        Lesson {
            if (title == null || title.isBlank()) {
                throw new IllegalArgumentException("blank title");
            }
            if (minutes < 0) {
                throw new IllegalArgumentException("negative minutes");
            }
            title = title.strip();
        }

        @Override
        public String label() {
            return title;
        }
    }

    static final class Folder implements Describable {
        private final String name;

        Folder(String name) {
            this.name = name;
        }

        @Override
        public String label() {
            return name;
        }
    }

    public static void main(String[] args) {
        Priority priority = Priority.MEDIUM;
        System.out.println("enum value=" + priority);
        System.out.println("enum name=" + priority.name());
        System.out.println("enum count=" + Priority.values().length);
        System.out.println("enum lookup=" + (Priority.valueOf("MEDIUM") == priority));

        String action = switch (priority) {
            case LOW -> "read";
            case MEDIUM -> "review";
            case HIGH -> "urgent";
        };
        System.out.println("enum switch=" + action);

        Lesson first = new Lesson(" Java ", 30);
        Lesson second = new Lesson("Java", 30);
        System.out.println("record=" + first);
        System.out.println("record title=" + first.title());
        System.out.println("record minutes=" + first.minutes());
        System.out.println("record equals=" + first.equals(second));
        System.out.println("record identity=" + (first == second));

        Describable item = first;
        System.out.println("interface label=" + item.label());
        System.out.println("interface default=" + item.summary());
        System.out.println("interface static=" + Describable.kind());

        Describable folder = new Folder("Basics");
        System.out.println("class implements=" + folder.summary());

        try {
            new Lesson(" ", 5);
        } catch (IllegalArgumentException ex) {
            System.out.println("record invalid=" + ex.getMessage());
        }
    }
}
~~~

Requires **JDK 17 or later**, no Maven/Gradle, external libraries, or `--enable-preview`.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 EnumRecordInterfaceDemo.java
java -cp . EnumRecordInterfaceDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\EnumRecordInterfaceDemo.java
java -cp . EnumRecordInterfaceDemo
~~~

### Exact expected stdout

~~~text
enum value=MEDIUM
enum name=MEDIUM
enum count=3
enum lookup=true
enum switch=review
record=Lesson[title=Java, minutes=30]
record title=Java
record minutes=30
record equals=true
record identity=false
interface label=Java
interface default=Named:Java
interface static=describable
class implements=Named:Basics
record invalid=blank title
~~~

Reading the output flow: `priority` holds an enum constant; `Lesson` creates two objects with the same content (`equals=true`) but different references (`==false`); the record object can be assigned to the `Describable` interface variable because it `implements` it; the `Folder` class can also implement the same interface.

## 7. Common Syntax-Reading Mistakes

| Confusion | Correct understanding |
|---|---|
| Treating `Priority.HIGH` as a `String` | It is a constant of type `Priority`; use `.name()` if the string name is needed |
| Using `new Priority()` | Cannot instantiate new enum constants with `new` |
| Using `new Describable()` | An interface cannot be instantiated directly |
| Calling `lesson.getTitle()` by default | A record component has accessor `title()` |
| Thinking records are always deeply immutable | Mutable reference components can still be mutated |
| Calling `Describable.summary()` as static | `summary()` is an instance default method; only `kind()` is static |
| Implementing `label()` without `public` | Cannot reduce visibility of an interface method |
| Using `extends` instead of `implements` when a record implements an interface | Write `record Lesson(...) implements Describable` |
| Treating `record` as an extendable class | Records are implicitly `final` and cannot be `extends`-ed by other classes |
| Storing `enum.ordinal()` as a fixed code | Reordering constants changes ordinals |

## 8. Exercises with Answers

**A.** Given `enum Traffic { RED, YELLOW, GREEN }`, what type does `Traffic light = Traffic.RED;` hold? **`Traffic`**; `RED` is an enum constant, not a string.

**B.** Given `record Size(int width, int height) {}`, after creating `new Size(2, 5)`, how do you read the width? **`size.width()`** for variable `Size size`; Java does not automatically generate `getWidth()`.

**C.** An interface declares `void run();`. With what access level must a class implementing it write the method? **`public void run() { ... }`** (if the concrete class provides the implementation directly).

**D.** Can two records with identical component values have `equals` true yet `==` false? **Yes**: `equals` compares component contents, while `==` compares object identity.

**E.** Can `record Lesson(String name) implements Describable` declare additional methods of its own? **Yes**; a record is still a specialized class type that can declare methods and implement interfaces.

## 9. Checklist and Conclusion

- [ ] Recognize `enum`, constant lists, and `Type.CONSTANT` notation.
- [ ] Understand `record X(T component)` declares data and the `component()` accessor.
- [ ] Know that `equals` and `==` on records carry different meanings.
- [ ] Understand interfaces declare contracts; `implements` fulfills a contract.
- [ ] Distinguish `abstract`, `default`, and `static` methods in an interface.
- [ ] Know that a record can `implements interface`.
- [ ] Do not mistake records for deeply immutable types or enums for `String`.
- [ ] Compile and run `EnumRecordInterfaceDemo.java` with JDK 17+ and verify exact stdout.

**Conclusion:** `enum` fits **named choice sets**, `record` conveniently represents **structured data**, and `interface` expresses **behavior contracts**. Reading these three syntaxes correctly helps you understand how Java types work together before diving deeper into advanced OOP techniques.