# Declaring a Variable Does Not Mean Creating an Object — Java 17+

In Java, **declaring a reference variable** does not mean **creating an object**. These are two independent actions: a variable holds a **reference value** (or `null`), whereas an object is an entity created when an operation actually instantiates an object.

~~~java
Book book;                    // Only declares a local variable, no Book created yet.
book = null;                 // The variable references no object.
book = new Book("Java");     // Creates a Book, assigns its reference to book.
Book alias = book;           // Copies the reference, does NOT create a new Book.
~~~

You cannot read `book` immediately after the line `Book book;` if it is a local variable: it has not undergone *definite assignment*. By contrast, a class/object reference-type field that is not explicitly initialized will have the default value `null`.

## 1. Distinguishing the Operations

| Code snippet | What happens? | Creates a new `Book`? |
| --- | --- | --- |
| `Book a;` | Declares an unassigned local variable | **No** |
| `Book a = null;` | Declares and assigns a null reference | **No** |
| `Book a = new Book("A");` | Calls the constructor of a new Book | **Yes** |
| `Book b = a;` | Copies the reference, creating an alias | **No** |
| `a = new Book("B");` | Reassigns variable `a` to point to a new Book | **Yes** |
| `Book[] books = new Book[2];` | Creates **an array object**, with both elements initially null | **Does not create a Book** |
| `books[0] = a;` | Places an existing reference into an array element | **No** |

**Distinguish the kind of object created:** `new Book[2]` still creates a **`Book[]` array object**, but it does not call the `Book` constructor twice. Each element of the reference array is initially equal to `null`.

An object can also be accessed through the return value of a method, a field, or another variable. Do not mistakenly think that **every variable name** must correspond to its **own separate object**.

## 2. Runnable Java 17+ Program

Create a UTF-8 file named **`DeclarationAndCreationDemo.java`**:

~~~java
public class DeclarationAndCreationDemo {
    static class Book {
        static int constructed;
        final String title;

        Book(String title) {
            this.title = title;
            constructed++;
        }
    }

    static class Shelf {
        Book current; // Reference field defaults to null.
    }

    static Book shared; // Static reference field defaults to null.

    public static void main(String[] args) {
        Book pending;
        pending = null;
        System.out.println("pendingNull=" + (pending == null));
        System.out.println("constructedStart=" + Book.constructed);

        Shelf shelf = new Shelf(); // Creates a Shelf, does NOT create a Book.
        System.out.println("shelfBookNull=" + (shelf.current == null));
        System.out.println("sharedNull=" + (shared == null));

        Book first = new Book("Java");
        System.out.println("afterFirst=" + Book.constructed);

        Book alias = first; // No new, does not call constructor.
        System.out.println("afterAlias=" + Book.constructed);
        System.out.println("aliasSame=" + (alias == first));

        Book second = new Book("Java");
        System.out.println("afterSecond=" + Book.constructed);
        System.out.println("sameObject=" + (first == second));
        System.out.println("sameTitle=" + first.title.equals(second.title));

        Book[] slots = new Book[2];
        System.out.println("afterArray=" + Book.constructed);
        System.out.println("firstSlotNull=" + (slots[0] == null));

        slots[0] = first;
        shelf.current = first;
        shared = second;
        System.out.println("slotAlias=" + (slots[0] == first));
        System.out.println("shelfAlias=" + (shelf.current == first));
        System.out.println("sharedSecond=" + (shared == second));

        first = second;
        System.out.println("firstNowSecond=" + (first == second));
        System.out.println("aliasStillOld=" + (alias == slots[0]));
        System.out.println("constructedEnd=" + Book.constructed);

        try {
            System.out.println(pending.title);
        } catch (NullPointerException ex) {
            System.out.println("nullAccess=NullPointerException");
        }
    }
}
~~~

In the directory containing the file, open PowerShell or Bash and use **JDK 17+**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 DeclarationAndCreationDemo.java
java DeclarationAndCreationDemo
~~~

**Expected output** of the command `java DeclarationAndCreationDemo` (excluding JDK version information):

~~~text
pendingNull=true
constructedStart=0
shelfBookNull=true
sharedNull=true
afterFirst=1
afterAlias=1
aliasSame=true
afterSecond=2
sameObject=false
sameTitle=true
afterArray=2
firstSlotNull=true
slotAlias=true
shelfAlias=true
sharedSecond=true
firstNowSecond=true
aliasStillOld=true
constructedEnd=2
nullAccess=NullPointerException
~~~

### Explaining the Output

- `Book pending;` does not create a `Book`. After assigning `pending = null`, the variable is validly initialized, yet it still does not reference an object.
- `new Shelf()` **creates a Shelf** rather than pre-creating a Book. The `current` field inside Shelf and the `shared` field default to `null`.
- Each `new Book("Java")` expression invokes the `Book` constructor once. In the program, `Book.constructed` increases from 0 to 1 and then 2.
- `Book alias = first;` **does not call the constructor**. Both variables reference the same Book; `alias == first` is `true`.
- `first` and `second` are two distinct Books even though `title.equals` yields `true`. Here, `==` on two references compares **object identity**, not content.
- `new Book[2]` only creates **one array**. The two array slots receive null, without automatically receiving Books. Thus `afterArray=2`.
- Assigning `slots[0] = first`, `shelf.current = first`, and `shared = second` only stores **existing references**.
- `first = second` does not delete the old Book. `alias` and `slots[0]` still reference the old Book; no additional constructor is called.
- `pending.title` attempts to access a field through `null`, causing a `NullPointerException` which the program catches to print a deterministic message.

**Note:** `constructed` is merely a counter of *`Book` constructor invocations in this single-threaded example*. It is not a counter of all objects in the JVM: there are also the Shelf object, the array object, and other objects.

## 3. Unassigned Variables, `null` Variables, and Real Objects

~~~java
Book local;             // Local declaration; NOT yet assigned.
// System.out.println(local); // Compile error: no definite assignment yet.

local = null;           // Assigned, but no object.
System.out.println(local == null); // true.

local = new Book("A");  // Now there is a Book object.
System.out.println(local.title);   // A.
~~~

There are three states to keep separate:

1. **Local variable without definite assignment:** the compiler **does not allow reading** its value.
2. **Variable assigned `null`:** reading the variable itself is valid, but calling a method or reading a field through it throws `NullPointerException`.
3. **Variable pointing to an object:** members of that object can be accessed according to access rights and actual state.

Class/object fields differ from local variables: `Book field;` at class level receives the default value `null`. However, **null is not an empty Book object**. `new Book("")` creates a real Book, whereas `Book b = null;` does not.


## 4. Variables Can Obtain References from Multiple Sources

After `Book alias = first;`, both variables hold a reference to the same `Book`; assigning `slots[0] = first` does not create a new `Book` either. `Book shared = getBook();` receives a method's return value, and fields and parameters can also hold existing references. Therefore, **counting variables or assignments does not tell you how many objects were created**; in the runnable example, the constructor counter is what tracks `Book` instances specifically.


## 5. Does `final` Create or Preserve Objects?

`final Book b;` only declares an unassigned variable in local scope. It has not created a `Book` yet and still requires definite assignment before being read; after a valid assignment, the `final` variable cannot be reassigned. Dropping a reference by assigning `null` in another variable does not immediately destroy the object either: an alias can still use it. All of these are independent of how many times the constructor was invoked.


## 6. Distinguishing Easily Confused Cases

| Code | Creates a new `Book`? | Why? |
| --- | --- | --- |
| `Book a;` or `Book a = null;` | No | Only declares/assigns a variable |
| `Book b = a;` | No | Copies a reference |
| `new Book[2]` | No | Creates an **array**, not a `Book` |
| `Book b = new Book("X");` | Yes | One `Book` instantiation |
| `b = new Book("Y");` | Yes | Instantiates another `Book` and reassigns `b` |

Objects can also come from method calls or literals; not every reference is created on the variable declaration line.

## 7. Self-Check Exercises

**Exercise 1.** How many `Book` objects are created?

~~~java
Book a = new Book("X");
Book b = a;
Book c = null;
~~~

*Answer:* **One Book**. `b` is just an alias, and `c` is null.

**Exercise 2.** `Book[] a = new Book[3];` creates how many arrays and how many Books?

*Answer:* One **`Book[]` array**, **zero Books**; all elements are null.

**Exercise 3.** Why does `Book x; System.out.println(x);` inside a method fail to compile?

*Answer:* `x` is a local variable that has not undergone *definite assignment*.

**Exercise 4.** `Book x = new Book("One"); Book y = x; x = new Book("Two");`. Which object does `y` point to?

*Answer:* Still Book "One", while `x` points to Book "Two".

**Exercise 5.** Is `Book x = null;` equivalent to `Book x = new Book("");`?

*Answer:* No. The first statement creates no object; the second creates a Book whose `title` is an empty string.

## Checklist

- [ ] Distinguish **variable declaration** from **object creation**.
- [ ] Distinguish an unassigned local variable from a reference with the value null.
- [ ] Know that reference assignment creates an **alias**, without cloning the object.
- [ ] Know that a reference array is an **array object**, with elements initially null.
- [ ] Know that reassigning a variable does not change other references to the old object.
- [ ] Do not use `==` to infer that two objects have the same content.
- [ ] Do not assume `final` or assigning `null` automatically creates/deletes objects.

**Remember:** A variable is **a place that holds a reference value**; an object is **an entity that is created and has state**. Count actual object creations appropriately, **not variable names**, when analyzing a Java program.
