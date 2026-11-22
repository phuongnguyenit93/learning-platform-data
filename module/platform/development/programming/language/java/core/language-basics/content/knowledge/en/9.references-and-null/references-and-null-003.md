# `new` Creates an Object and Returns a Reference — Java 17+

## 1. Goal: Distinguishing an Object from a Reference Variable

In Java, the `new` expression is used to **create a new object** of an instantiable class (or a new array). When creating a class instance, Java allocates and initializes the object and executes the corresponding constructor; if the process succeeds, **the value of the `new` expression is a reference to the newly created object**.

~~~java
Person person = new Person("Lan");
~~~

Let us break the statement above into three parts:

1. `Person` is the **declared type of the variable** `person`.
2. `new Person("Lan")` **creates an instance** of `Person`, calls the constructor with the argument `"Lan"`, and produces a reference value to that instance if successful.
3. `=` **assigns this reference value** to the variable `person`.

The variable `person` **is not the object itself**. It holds a reference value that allows the program to access the object.

~~~java
final class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    String getName() {
        return name;
    }
}

// Inside a method:
Person person = new Person("Lan");
System.out.println(person.getName()); // Lan
~~~

A reference variable can be **reassigned** to point to a different object; meanwhile, the created object can have multiple variables referencing it at the same time.

## 2. `new` and Constructor: Who Does What?

Basic syntax when creating an object:

~~~java
ClassName variable = new ClassName(arguments);
~~~

- `new` begins the instance creation expression.
- `ClassName` specifies the class being instantiated.
- `(...)` passes arguments to the matching **constructor**.
- The entire expression `new ClassName(...)` has the reference type of the newly created instance (and can be assigned to a variable of a compatible type).

Example of a class with two constructors:

~~~java
final class Book {
    private final String title;
    private final int pages;

    Book(String title) {
        this(title, 0); // Calls another constructor in the same class
    }

    Book(String title, int pages) {
        this.title = title;
        this.pages = pages;
    }

    String describe() {
        return title + " (" + pages + " pages)";
    }
}

// Inside a method:
Book first = new Book("Java");
Book second = new Book("Java", 120);
System.out.println(first.describe());  // Java (0 pages)
System.out.println(second.describe()); // Java (120 pages)
~~~

A constructor has the **same name as the class** and **no return type**, not even `void`. Do not write `new` inside a constructor definition.

**Distinction:** a constructor is not an ordinary method that "returns an object"; it is **the `new` instance creation expression** that yields the reference value after the constructor completes normally.

### Is It Mandatory to Store It in a Variable?

No. The reference from `new` is an expression value, so it can be used directly:

~~~java
System.out.println(new Book("Direct", 20).describe());
// Direct (20 pages)
~~~

For an object that needs to be reused, you should store it in a clearly named variable for readability.

## 3. Each Separate `new` Creates a Distinct Instance

~~~java
Person a = new Person("Lan");
Person b = new Person("Lan");

System.out.println(a == b); // false
~~~

Even though both have the same `name` content, they are **two distinct objects** because they come from two separate instance creations using `new`.

Comparing reference variables with `==` checks **object identity** (*reference identity*): whether the two references point to the exact same object. It **does not automatically compare fields**.

| Statement | New `Person` instances | Reference value |
|---|---:|---|
| `Person a = new Person("Lan");` | 1 | `a` points to the new instance |
| `Person b = a;` | 0 | `b` copies the reference from `a` |
| `Person c = new Person("Lan");` | 1 | `c` points to a different instance |
| `b = c;` | 0 | `b` switches to `c`'s reference |

**Rule:** **reference assignment does not create a copy of the object**. To get another object, you must create one separately or use an appropriate copying mechanism provided by the API.


## 4. Using the Result of `new`

The result of `new Book("Java")` can be assigned immediately to a variable, returned from a method, or passed directly as an argument. Afterwards, `Book alias = book;` only copies the reference, whereas `alias = new Book("Other");` performs an additional instantiation. A method parameter receives a **copy of the reference value**; reassigning the parameter does not reassign the caller's variable. To replace the object on the caller's side, return the new reference and let the caller explicitly assign it.

## 5. `new` for Arrays: An Array Object Differs from Element Objects

`new` is also used to create **arrays**:

~~~java
int[] numbers = new int[3];
System.out.println(numbers.length); // 3
System.out.println(numbers[0]);     // 0
~~~

`new int[3]` creates an array object with 3 `int` elements, initialized by default to `0`.

However, a reference array only creates **an array holding references**, without automatically creating the objects for each element:

~~~java
Box[] slots = new Box[2];

System.out.println(slots.length); // 2
System.out.println(slots[0] == null); // true

slots[0] = new Box(50);
System.out.println(slots[0].value); // 50
~~~

Here there are **two creations** of two different kinds:

- `new Box[2]` creates **one array**, whose two reference elements are initially both `null`.
- `new Box(50)` creates **a separate Box instance** and assigns its reference to `slots[0]`.

**Do not confuse** `new Box[2]` with "automatically running the Box constructor twice".

## 6. Constructors and the Object Initialization Process

When executing a valid `new ClassName(...)`, Java prepares an instance, applies default values to fields, runs class/instance initialization, and executes constructor calls according to the language's inheritance and initialization rules.

Short example:

~~~java
final class Ticket {
    int id; // Field initially has default value 0

    Ticket(int id) {
        this.id = id;
    }
}

// Inside a method:
Ticket ticket = new Ticket(42);
System.out.println(ticket.id); // 42
~~~

Important points:

- Fields are initialized according to Java's rules; the constructor can assign specific values.
- A constructor can **throw an exception**. If initialization fails, the `new` expression does not complete normally to supply a resulting reference for that assignment.
- `new` can fail due to resource errors, such as `OutOfMemoryError`; **never assume every `new` call always succeeds**.
- A constructor is not restricted to only assigning fields; it can perform validation and other initialization logic. However, keep the object's state consistent and do not carelessly leak `this` while it is only partially initialized.

Regarding the memory model, objects are often described as "living on the heap", though the JVM/JIT may optimize allocation in some cases. What matters for Java source logic is **instance and identity semantics**, not guessing a physical address.


## 7. Observing Newly Created Objects

`new Box(10) == new Box(10)` is `false` because each side creates a separate instance. `equals` only compares values if the class defines the corresponding contract; by default `Object.equals` compares identity. Do not treat the string from `Object.toString()` as a memory address: the `ClassName@hash` format is not guaranteed to be a real address. If you need to print a readable state, define `toString()` yourself like in the `Counter` example below.

## 8. Standalone Runnable Java 17 Program

Create the file named exactly **`NewReferenceDemo.java`** with the following content:

~~~java
public final class NewReferenceDemo {
    private NewReferenceDemo() {}

    static final class Counter {
        static int created;

        private final String name;
        private int value;

        Counter(String name, int value) {
            this.name = name;
            this.value = value;
            created++;
        }

        void add(int amount) {
            value += amount;
        }

        @Override
        public String toString() {
            return name + "=" + value;
        }
    }

    static void mutate(Counter counter) {
        counter.add(2);
    }

    static void rebindParameter(Counter counter) {
        counter = new Counter("Local", 99);
        System.out.println("inside rebind=" + counter);
    }

    public static void main(String[] args) {
        Counter first = new Counter("A", 10);
        Counter alias = first;
        Counter other = new Counter("A", 10);

        System.out.println("first=" + first);
        System.out.println("alias same=" + (first == alias));
        System.out.println("other same=" + (first == other));

        alias.add(5);
        System.out.println("after alias first=" + first);
        System.out.println("other unaffected=" + other);

        alias = new Counter("B", 1);
        System.out.println("alias rebound=" + alias);
        System.out.println("first still=" + first);

        mutate(first);
        System.out.println("after method mutate=" + first);

        rebindParameter(first);
        System.out.println("after method rebind=" + first);

        Counter missing = null;
        System.out.println("missing is null=" + (missing == null));
        try {
            missing.add(1);
        } catch (NullPointerException ex) {
            System.out.println("null access=NullPointerException");
        }

        Counter[] slots = new Counter[2];
        System.out.println("slots length=" + slots.length);
        System.out.println("default slot null=" + (slots[0] == null));
        slots[0] = new Counter("Slot", 3);
        System.out.println("slot object=" + slots[0]);

        int[] numbers = new int[2];
        System.out.println("int defaults=" + numbers[0]
                + "," + numbers[1]);

        System.out.println("Counter instances created=" + Counter.created);
    }
}
~~~

Use **JDK 17+** and open a terminal in the directory containing the source.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 NewReferenceDemo.java
java -cp . NewReferenceDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\NewReferenceDemo.java
java -cp . NewReferenceDemo
~~~

**Expected output (independent of object addresses/hashes):**

~~~text
first=A=10
alias same=true
other same=false
after alias first=A=15
other unaffected=A=10
alias rebound=B=1
first still=A=15
after method mutate=A=17
inside rebind=Local=99
after method rebind=A=17
missing is null=true
null access=NullPointerException
slots length=2
default slot null=true
slot object=Slot=3
int defaults=0,0
Counter instances created=5
~~~

### Explaining How `new` Is Counted

The `Counter.created` variable only increments in the **`Counter(...)` constructor**. In the program there are 5 `Counter` instance creations:

1. `first = new Counter("A", 10)`.
2. `other = new Counter("A", 10)`.
3. `alias = new Counter("B", 1)`.
4. `counter = new Counter("Local", 99)` inside the method.
5. `slots[0] = new Counter("Slot", 3)`.

The statements `alias = first`, `mutate(first)`, and `new Counter[2]` **do not create additional Counter instances**. `new Counter[2]` only creates an **array object**. `new int[2]` also creates an array object and its numeric elements have the default value 0.

`alias = new Counter(...)` and reassigning the parameter inside `rebindParameter` **do not change which reference the `first` variable holds**. Only `mutate(first)` modifies the state of the object that `first` points to.


## 9. Verifying the Exact Meaning of Object Creation Expressions

- `new SomeType[n]` always creates an array if it succeeds; for a reference element type, the elements are initially `null` and **no `SomeType` instances have been created yet**.
- If a constructor throws an exception, the instance creation expression does not complete normally, so the assignment of the result does not occur.
- A `new` expression can also fail due to resources; do not rely on an assumption that every instantiation succeeds.
- `new` yields a reference value, whereas a constructor does not declare a return type; keep these two ideas distinct when reading code.


## 10. Exercises Focused on `new`

**Exercise A.** `Book a = new Book("A"); Book b = a; Book c = new Book("A");` performs how many `Book` instance creations?

*Answer:* Two. `b = a` does not call the constructor.

**Exercise B.** `Book[] shelf = new Book[3]; shelf[0] = new Book("B");` creates how many array objects and how many `Book` objects?

*Answer:* One array and one `Book`. The remaining two elements are still `null`.

**Exercise C.** If `new Book(null)` invokes a constructor that has `Objects.requireNonNull(title)` and throws `NullPointerException`, is the variable receiving the assignment updated?

*Answer:* No. When the constructor fails, the assignment is not executed. If it is a previously unassigned local variable, after the failure branch it must still obey *definite assignment* rules.

## 11. Checklist and Conclusion

- [ ] Distinguish an **object instance** from a **reference variable**.
- [ ] Understand that `new ClassName(...)` creates an instance, runs the constructor, and yields a reference value if successful.
- [ ] Distinguish `new ClassName(...)` from `ClassName other = existing;`.
- [ ] Know that `==` compares **same object** when applied to two references.
- [ ] Recognize that two alias variables can modify the same object.
- [ ] Understand that reassigning a variable does not modify the object that variable previously pointed to.
- [ ] Distinguish an unassigned local variable, a `null` reference, and a reference to an object.
- [ ] Know that `new SomeClass[n]` creates an **array**, not `n` instances of the class.
- [ ] Understand that Java passes references **by value**, not pass-by-reference.
- [ ] Do not infer physical addresses or GC timing from a `new` expression.
- [ ] Compile and run `NewReferenceDemo.java`, matching every line of output.

**Conclusion:** `new` is an expression that **creates an instance and evaluates to a reference** when initialization succeeds. Reference assignment does not clone the object; multiple variables can point to the same instance, whereas each separately executed `new ClassName(...)` instance creation expression represents a separate instance creation. Understanding this clearly helps handle identity, aliases, method parameters, `null`, and object lifecycles properly in Java 17+.
