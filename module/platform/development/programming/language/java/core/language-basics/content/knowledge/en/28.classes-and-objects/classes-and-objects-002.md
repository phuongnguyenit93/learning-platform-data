# Fields Represent Data and Methods Represent Behavior — Java 17+

## 1. Two Fundamental Components of a Class

In Java, a **class** describes an object type. A class typically groups together:

- **Fields** to store an object's **data/state**, such as a book's title and whether it is currently borrowed.
- **Methods** to describe **behavior/operations**, such as borrowing a book, returning a book, or displaying its status.

~~~java
class Book {
    String title;       // Field: data about the book.
    boolean borrowed;   // Field: current state.

    void borrow() {     // Method: one behavior.
        borrowed = true;
    }

    void giveBack() {   // Method: another behavior.
        borrowed = false;
    }
}
~~~

This example only introduces the structure. The complete code below will use `private` and check conditions to prevent borrowing a book that is already borrowed.

**Important distinction:** a field describes "what an object **currently has / what state it is in**"; a method describes "what an object **can do**". The two components are inseparable: behavior can **read or update** state, while obeying the class's rules.

## 2. Declaring and Accessing Fields

General syntax:

~~~java
[accessModifier] [static] [final] Type fieldName;
~~~

Example:

~~~java
class Student {
    private String name;
    private int score;
    private boolean active;
}
~~~

`name`, `score`, and `active` are three **instance fields** — each `Student` object has its own state. When creating two objects with two `new` calls, changing a field of the first object does not automatically change the second object.

For fields that are not explicitly initialized, Java sets **default values** when the object is created:

| Field type | Default value |
|---|---|
| `int`, `long`, integer types | Corresponding `0` |
| `double`, `float` | Corresponding `0.0` |
| `boolean` | `false` |
| `char` | `'\\u0000'` |
| Reference types such as `String`, `int[]` | `null` |

**Difference:** a local variable declared as `int n;` **has no default value that can be read immediately**. For fields, Java performs default initialization before the constructor completes.

In code using `private`, code outside the class **cannot directly write** `book.borrowed = true;`. The class should expose a valid behavior such as `book.borrow()` if the state transition requires validation rules.

## 3. Declaring Methods and Invoking Behavior

General syntax of a method:

~~~java
[accessModifier] [static] ReturnType methodName(ParameterList) {
    // Method body.
}
~~~

Example:

~~~java
class Counter {
    private int value;

    void increase() {
        value++;
    }

    void add(int amount) {
        value += amount;
    }

    int getValue() {
        return value;
    }
}
~~~

- `void increase()`: a behavior that takes no arguments and returns no value.
- `void add(int amount)`: receives an **argument** when called (e.g., `add(3)`) through the parameter `amount`.
- `int getValue()`: returns an `int` via the statement `return value;`.
- `getValue()` **reads** state; `increase()` and `add(...)` **modify** state.

~~~java
Counter counter = new Counter();
counter.increase();
counter.add(3);
System.out.println(counter.getValue());
~~~

**Exact expected stdout:**

~~~text
4
~~~

The snippet above uses the `Counter` class immediately above it; it is not a standalone program if you copy only those four call lines. A complete program to run via CLI is provided in Section 9.


## 4. Constructors Provide Initial State for Fields

~~~java
class Student {
    private final String name;
    private int score;

    Student(String name, int score) {
        if (score < 0 || score > 100) {
            throw new IllegalArgumentException("score out of range");
        }
        this.name = name;
        this.score = score;
    }
}
~~~

A constructor validates and assigns fields of the new instance. A `final` field cannot be reassigned after initialization finishes according to Java rules; other fields can still change through validated behaviors. The `this` keyword selects **the current object's field** when a field name matches a parameter name. In this lesson, what matters is that **initial data and subsequent update methods obey the same state contract**. Constructor variants and `this(...)` have their own lesson.

## 5. Methods Operate on the Receiver's State

If `student.addScore(5)` is an instance call, `addScore` reads/updates the field of the object `student` points to. You can write `this.score += points;` or `score += points;` when the name is not shadowed. To distinguish a field from a parameter of the same name, explicitly write `this.score = score;`.

Two separately created objects have separate instance fields; two variables referencing the same object observe the same state. This section helps you read the `Book.borrow()` behavior below without needing to relearn all reference assignment mechanics.

## 6. Why Make Fields `private`?

Counter-example:

~~~java
class Book {
    public boolean borrowed;
}
~~~

Other code can set `book.borrowed = true;` or `false` from anywhere access is permitted, even when the borrow/return workflow must also update statistics or check conditions. State easily becomes **inconsistent**.

Encapsulation helps the class manage its own data:

~~~java
class Book {
    private boolean borrowed;
    private int borrowCount;

    boolean borrow() {
        if (borrowed) return false;
        borrowed = true;
        borrowCount++;
        return true;
    }

    boolean returnBook() {
        if (!borrowed) return false;
        borrowed = false;
        return true;
    }

    boolean isBorrowed() {
        return borrowed;
    }
}
~~~

Contract:

- `borrow()` returns `true` if borrowing succeeds and **transitions state** to borrowed; returns `false` if already borrowed, without incrementing `borrowCount`.
- `returnBook()` returns `true` when the book is currently borrowed and is returned successfully; if already available, returns `false`.
- `isBorrowed()` only **reads state**, without modifying data.

`private` does not automatically guarantee every design is right; the benefit is that state changes can be centralized inside methods that enforce rules. You do not necessarily have to create a setter for every field: a public setter without validation can defeat encapsulation.


## 7. Instance Fields and Methods Are Central to the Book Model

In the `Book` example, `borrowed` and `borrowCount` are **instance fields**: each book keeps its own borrowed status and borrow count. `borrow()`, `returnBook()`, and `summary()` are **instance methods** that read or mutate those fields.

`createdCount` and `getCreatedCount()` are **static** members, shared at the class level to illustrate a counter of successfully created objects. Call `Book.getCreatedCount()` via the class name. A static method does not have `this` to access a specific book's state; the dedicated lesson on `static` will explain initialization timing, shared state, and multithreading in more depth.

## 8. Data, Behavior, and Object Consistency

A simple model:

~~~text
                  class Book
         +--------------------------+
FIELDS   | title: String            |  State
         | borrowed: boolean        |
         | borrowCount: int         |
         +--------------------------+
METHODS  | borrow(): boolean        |  Behavior
         | returnBook(): boolean    |
         | summary(): String        |
         +--------------------------+

bookA ──> {title="Java", borrowed=true,  borrowCount=2}
bookB ──> {title="OOP",  borrowed=false, borrowCount=0}
~~~

Two objects of the same `Book` type can be in **two different states**. Methods are declared in a single class definition and operate on the object receiving the call.

**Business invariant** of the example: `borrowCount` is non-negative; only each successful borrow increments the counter; returning a book does not decrease the total borrow count. The constructor checks that `title` is non-blank to avoid creating an object without a valid name.

A getter typically **returns** information, whereas a behavioral method like `borrow()` communicates business intent more clearly than letting external code mutate the `borrowed` field directly.

## 9. Complete Java 17+ Program

Save the file with the exact name **`FieldsMethodsDemo.java`**:

~~~java
public final class FieldsMethodsDemo {
    private FieldsMethodsDemo() {}

    static final class Book {
        private static int createdCount;

        private final String title;
        private boolean borrowed;
        private int borrowCount;

        Book(String title) {
            if (title == null || title.isBlank()) {
                throw new IllegalArgumentException("title must not be blank");
            }
            this.title = title.strip();
            // borrowed defaults to false, borrowCount defaults to 0.
            createdCount++;
        }

        boolean borrow() {
            if (borrowed) {
                return false;
            }
            borrowed = true;
            borrowCount++;
            return true;
        }

        boolean returnBook() {
            if (!borrowed) {
                return false;
            }
            borrowed = false;
            return true;
        }

        boolean isBorrowed() {
            return borrowed;
        }

        int getBorrowCount() {
            return borrowCount;
        }

        String summary() {
            return title + " | borrowed=" + borrowed
                    + " | times=" + borrowCount;
        }

        static int getCreatedCount() {
            return createdCount;
        }
    }

    public static void main(String[] args) {
        System.out.println("initial created=" + Book.getCreatedCount());

        Book javaBook = new Book(" Java ");
        Book algoBook = new Book("Algorithms");
        System.out.println("created after new=" + Book.getCreatedCount());

        System.out.println("java start=" + javaBook.summary());
        System.out.println("algorithms start=" + algoBook.summary());
        System.out.println("borrow java=" + javaBook.borrow());
        System.out.println("borrow java again=" + javaBook.borrow());
        System.out.println("java after borrow=" + javaBook.summary());
        System.out.println("algorithms unchanged=" + algoBook.summary());

        System.out.println("return java=" + javaBook.returnBook());
        System.out.println("return java again=" + javaBook.returnBook());

        Book alias = javaBook;
        System.out.println("borrow alias=" + alias.borrow());
        System.out.println("alias same object=" + (alias == javaBook));
        System.out.println("java final=" + javaBook.summary());
        System.out.println("algorithms final=" + algoBook.summary());
        System.out.println("total created=" + Book.getCreatedCount());

        try {
            new Book(" ");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid title=" + ex.getMessage());
        }
        System.out.println("total after invalid=" + Book.getCreatedCount());
    }
}
~~~

**Requirements:** JDK 17+; no external libraries, Maven, Gradle, or preview features needed. The code uses one `public class` matching the filename and a nested `Book` class so everything can run from a single file.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 FieldsMethodsDemo.java
java -cp . FieldsMethodsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\FieldsMethodsDemo.java
java -cp . FieldsMethodsDemo
~~~

### Exact expected stdout

~~~text
initial created=0
created after new=2
java start=Java | borrowed=false | times=0
algorithms start=Algorithms | borrowed=false | times=0
borrow java=true
borrow java again=false
java after borrow=Java | borrowed=true | times=1
algorithms unchanged=Algorithms | borrowed=false | times=0
return java=true
return java again=false
borrow alias=true
alias same object=true
java final=Java | borrowed=true | times=2
algorithms final=Algorithms | borrowed=false | times=0
total created=2
invalid title=title must not be blank
total after invalid=2
~~~

**Phase-by-phase explanation:**

1. At startup, `createdCount` defaults to 0. Two successful `new Book(...)` calls make it 2.
2. `borrowed` and `borrowCount` are **instance fields** defaulting to `false` and `0` for **each** object.
3. Borrowing the `Java` book the first time succeeds; the second attempt is rejected, so `times` remains 1. The `Algorithms` book is unchanged.
4. Returning the book the first time succeeds; the second attempt returns `false` because the book is no longer borrowed.
5. `alias` and `javaBook` point to the same object; borrowing via `alias` causes `javaBook.summary()` to display `times=2`.
6. The constructor fails on a whitespace-only title **before** the line that increments the counter, so `createdCount` remains 2.

## 10. Common Mistakes

| Confusion | What to understand |
|---|---|
| Thinking fields and methods are both "variables" | Fields store data; methods are callable behavior declarations |
| Thinking `Book a;` creates an object | That is only a reference variable declaration; `new Book(...)` is required |
| Thinking two objects of the same class share all fields | **Instance fields** are per-object state; only **static fields** belong to the class |
| Writing `score = score;` when parameter name matches field | Use `this.score = score;` to assign to the field |
| Making every field `public` for arbitrary edits | Can break class rules; consider `private` and controlled methods |
| Calling `borrow()` and treating its return value as a field | The `boolean` value is computed/returned by the method, not a new field declaration |
| Calling an instance method from `static main` without an object | Create/obtain an object reference and call `book.borrow()` |
| Using `this` directly in a static method | A static context has no instance receiver |
| Thinking `final String title` makes the whole object immutable | Only the `title` field cannot be reassigned; `borrowed` and `borrowCount` can still change |
| Assigning `Book alias = book;` and thinking there is a copy of the object | Only copies the reference value; both variables point to the same object |

## 11. Exercises with Answers

**A.** Classify the following members:

~~~java
private int balance;
void deposit(int amount) { balance += amount; }
int getBalance() { return balance; }
~~~

**Answer:** `balance` is an **instance field**; `deposit` is a **state-mutating** method; `getBalance` is a **state-reading/returning** method.

**B.** If you create `Book first = new Book("A")` and `Book second = new Book("B")`, then call only `first.borrow()`, what is `second`'s `borrowed` field?  
**Answer:** `false`, because it is `second`'s own instance field.

**C.** Why is `private boolean borrowed` a better design than `public boolean borrowed`?  
**Answer:** callers cannot arbitrarily assign the field from outside the class, so the class can ensure state transitions through `borrow()`/`returnBook()` follow the rules.

**D.** If `Book alias = first;` and then `alias.borrow()`, does it affect the `first` object?  
**Answer:** **Yes**, because both references point to the same object.

**E.** Can a static method call `this.summary()` directly?  
**Answer:** **No**. A static method has no default instance receiver; a specific object reference is required.

**F.** Why does `new Book(" ")` in the complete program not increment `createdCount`?  
**Answer:** the constructor throws `IllegalArgumentException` during validation, before `createdCount++` executes.

## 12. Checklist and Conclusion

- [ ] Know that **fields store data/state** and **methods represent behavior**.
- [ ] Distinguish declaring a class from creating an object with `new`.
- [ ] Identify instance fields, instance methods, and `static` members.
- [ ] Understand that constructors establish initial state.
- [ ] Use `this.field` to distinguish a field from a parameter of the same name.
- [ ] Understand that methods can read, update fields, and return results.
- [ ] Use `private` and validated behaviors to keep state valid.
- [ ] Distinguish changing one object's state from changing another object.
- [ ] Know that an alias is multiple references to one object, not a new copy.
- [ ] Read and verify exact stdout of `FieldsMethodsDemo.java` on JDK 17+.

**Conclusion:** Java classes group **data** in fields and **behavior** in methods. Fields represent each object's state; methods use and modify state according to the class's rules. Designing `private` fields, valid constructors, and clearly purposed methods makes programs easy to understand, safe, and extensible.