# A static nested class does not need an enclosing object in Java

In Java, a **static nested class** is a member class declared **inside another class or interface**, with the `static` modifier where appropriate. The key point: **each instance of a static nested class does not automatically carry an implicit reference to an instance of the enclosing class**. Therefore, you can write `new Outer.Nested()` **without** creating `new Outer()` first.

~~~java
class Outer {
    static class Nested {
        String message() {
            return "Hello from Nested";
        }
    }
}
~~~

This is a valid illustrative class definition. If `Nested` is accessible from the call site, we create an object using `Outer.Nested object = new Outer.Nested();`. The `Nested` class **is not a static object**: each `new Outer.Nested()` still creates an object with its own identity, instance fields, and instance methods.

This lesson belongs to **Java core - class-object**, section **Nested classes**. The focus is the **static nested class – enclosing class – inner class** relationship in Java 17+: syntax, enclosing objects, access rules, `Outer.this`, type parameters, constructors, scope, initialization, bytecode, when to use them, and common mistakes. The complete programs include file names, compile/run commands, and **deterministic stdout**.

## 1. Terminology: nested class, member class, and inner class

A **nested class** is declared within the scope of a class or interface. In this lesson, we primarily distinguish two forms of **member class**:

- **Static nested class:** declared as `static class Nested` in the enclosing class; has no implicit enclosing instance.
- **Non-static member class**, commonly called **inner class:** declared as `class Inner` inside the enclosing class (without the `static` modifier); each instance is associated with an appropriate enclosing instance.

In addition, Java also has **local classes** (declared inside a block) and **anonymous classes** (created immediately via an expression), though they have their own rules. You should not call all classes declared inside another “inner class” in the technical sense of the Java Language Specification.

| Feature | Static nested class | Non-static inner member class |
| --- | --- | --- |
| How it is declared in an outer class | `static class Nested` | `class Inner` |
| Requires an Outer instance on creation? | **No** | Usually **yes** |
| Common syntax | `new Outer.Nested()` | `outer.new Inner()` |
| Automatically has an `Outer.this` reference? | **No** | Has an appropriate enclosing instance |
| Accesses an instance field of Outer without a reference? | No | Possible via the enclosing instance |
| Accesses a static field of Outer? | Yes, subject to access/scope rules | Yes, subject to access/scope rules |
| Has its own instance fields/methods? | Yes | Yes |
| Has its own constructors? | Yes | Yes |
| Can have its own type parameters? | Yes | Yes |

**Understand both levels accurately:** `static` here describes **the relationship between the nested class and the enclosing class**; it does not mean a Nested instance is a singleton, it does not mean every method of Nested must be `static`, and it does not mean the compiler creates an Outer object automatically.

## 2. Complete program 1 — creating a nested object when Outer has not yet been created

Create the file **`StaticNestedBasicsDemo.java`**:

~~~java
class School {
    private static final String PREFIX = "Course";

    static class CourseCode {
        private final String code;

        CourseCode(String code) {
            this.code = code;
        }

        String display() {
            return PREFIX + ":" + code;
        }
    }

    private final String schoolName;

    School(String schoolName) {
        this.schoolName = schoolName;
        System.out.println("School constructor: " + schoolName);
    }

    String name() {
        return schoolName;
    }
}

public class StaticNestedBasicsDemo {
    public static void main(String[] args) {
        School.CourseCode first =
                new School.CourseCode("J17");
        School.CourseCode second =
                new School.CourseCode("OOP");

        System.out.println("first=" + first.display());
        System.out.println("second=" + second.display());
        System.out.println("different=" + (first != second));

        School school = new School("North");
        System.out.println("outer=" + school.name());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 StaticNestedBasicsDemo.java
java StaticNestedBasicsDemo
~~~

**Exact stdout:**

~~~text
first=Course:J17
second=Course:OOP
different=true
School constructor: North
outer=North
~~~

**Explanation:**

1. The two `new School.CourseCode(...)` calls run **constructors of CourseCode**. They do not run the `School(String)` constructor.
2. `School` is only created when `new School("North")` is executed separately, after the two output lines about course codes.
3. `CourseCode` accesses `School.PREFIX` because `PREFIX` is a static field and access rules permit it.
4. The two course codes are **two different objects** even though their class is declared static nested.
5. The `schoolName` field is an instance field of School; a static nested class cannot arbitrarily write `return schoolName;` without a `School` reference.

`PREFIX` is a static final String constant. Using it does not create any enclosing instance.

## 3. Declaration syntax and usage syntax

Basic form:

~~~java
class Container {
    public static class Item {
        public Item() {
        }

        public String kind() {
            return "item";
        }
    }
}
~~~

This is valid illustrative code consisting of two classes; `Item` is declared `public static` so that code with access permissions can call:

~~~java
Container.Item item = new Container.Item();
String result = item.kind();
~~~

Points to distinguish:

- `Container.Item` is a **type name qualified** by the enclosing class name.
- `new Container.Item()` is the **expression that creates an instance of Item**.
- `Container.Item` **is not a field named Item** of a Container object.
- `new Container().new Item()` **is not the syntax for a static nested class**; that is the syntax form for creating a non-static inner object.
- If `Item` is only package-private, code in another package cannot access it arbitrarily; if `private`, only code with permission under the nesting/access rules can use it.

The enclosing class can have its own constructors, but a constructor of a static nested class **does not automatically receive an implicit Outer parameter**. If you need data from an Outer object, pass the data or reference into the Nested constructor **explicitly**.

## 4. The nested class is “static”, yet the object inside still has instance state

You should not think: “`static class`, so the data of all nested objects must be shared.”

~~~java
class CounterBox {
    static class Counter {
        private int count;

        void increase() {
            count++;
        }

        int value() {
            return count;
        }
    }
}
~~~

This is a valid definition. `count` is an **instance field of Counter**: each `new CounterBox.Counter()` has its own `count` value.

The Counter class can also declare its own static field:

~~~java
class Box {
    static class Counter {
        private static int created;

        Counter() {
            created++;
        }

        static int createdCount() {
            return created;
        }
    }
}
~~~

In the second illustrative definition, `created` is a static field **of Counter**, so it is shared by all Counter instances belonging to the same runtime class. The `static` modifier on the class declaration and the `static` modifier on the field declaration are **two different decisions**.

## 5. Complete program 2 — instance state and static state of a nested class

Create the file **`NestedStateDemo.java`**:

~~~java
class Game {
    static class Score {
        private static int constructed;
        private int points;

        Score(int points) {
            this.points = points;
            constructed++;
        }

        void add(int amount) {
            points += amount;
        }

        int points() {
            return points;
        }

        static int constructed() {
            return constructed;
        }
    }
}

public class NestedStateDemo {
    public static void main(String[] args) {
        Game.Score a = new Game.Score(10);
        Game.Score b = new Game.Score(20);

        a.add(5);
        System.out.println("a=" + a.points());
        System.out.println("b=" + b.points());
        System.out.println("same=" + (a == b));
        System.out.println("created="
                + Game.Score.constructed());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 NestedStateDemo.java
java NestedStateDemo
~~~

**Stdout:**

~~~text
a=15
b=20
same=false
created=2
~~~

The two `Score` objects hold different scores because `points` is an instance field. However, the `constructed` counter is a static field belonging to `Game.Score`; the two constructions increment the same variable.

**Concurrency note:** if multiple threads concurrently increment `constructed++`, this increment is not automatically atomic just because the field resides in a static nested class. To count accurately under contention, you must use a mechanism such as `AtomicInteger` or appropriate synchronization.

## 6. Precise comparison with a non-static inner class

A non-static inner member class needs an **enclosing instance**. It can reference the instance state of Outer without passing an Outer object through an explicit constructor.

Create the file **`StaticVsInnerDemo.java`**:

~~~java
class Library {
    private final String branch;
    private static final String SYSTEM = "Catalog";

    Library(String branch) {
        this.branch = branch;
        System.out.println("Library created: " + branch);
    }

    class Shelf {
        String describe() {
            return branch + " / " + SYSTEM;
        }
    }

    static class BookCode {
        private final String code;

        BookCode(String code) {
            this.code = code;
        }

        String describe() {
            return SYSTEM + ":" + code;
        }
    }
}

public class StaticVsInnerDemo {
    public static void main(String[] args) {
        Library.BookCode code =
                new Library.BookCode("B1");
        System.out.println("nested=" + code.describe());

        Library library = new Library("West");
        Library.Shelf shelf = library.new Shelf();
        System.out.println("inner=" + shelf.describe());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 StaticVsInnerDemo.java
java StaticVsInnerDemo
~~~

**Exact stdout:**

~~~text
nested=Catalog:B1
Library created: West
inner=West / Catalog
~~~

In the example:

- `Library.BookCode` is a **static nested class**. `BookCode` can read `SYSTEM`, but has no implicit reference to a specific Library to read `branch`.
- `Library.Shelf` is a **non-static inner class**. `library.new Shelf()` associates the newly created Shelf with `library`, so `Shelf.describe()` reads that Library's `branch`.
- `new Library.BookCode("B1")` occurs **before** `library` is created; it does not cause the Library constructor to run.

A self-check question: does a helper object need to know a **specific library branch**, or does it only need to format a general code? If it only works with a general code, using a static nested class is usually simpler.

## 7. No `Outer.this` in a static nested class

In a non-static inner class, `Outer.this` refers to the appropriate enclosing Outer instance. In a static nested class, **there is no automatic enclosing instance**, so that syntax is invalid.

An example that **intentionally does not compile if uncommented**:

~~~java
class Station {
    private final String name = "A";

    static class StaticMember {
        // String show() { return Station.this.name; }
        // Error: no enclosing instance of Station.
    }

    class InnerMember {
        String show() {
            return Station.this.name;
        }
    }
}
~~~

The commented lines describe the compile-time error scenario; the rest of the class is a valid Java definition.

Similarly, inside a static nested class, you **cannot** write:

~~~java
// return name;
~~~

if `name` is only an instance field of `Station` and no variable points to a Station object. It is not inaccessible because the field is `private`: the problem lies in the **lack of a receiver object**. Even if `name` is `public`, the static nested class still needs a specific instance to obtain that instance field's value.

## 8. Accessing `private` members of outer: allowed, but needs the right receiver

A static nested class is often used as an implementation detail inside Outer. Because both belong to the same nesting relationship, Java allows access to many private members under the appropriate access rules.

Distinguish two situations:

**Static member of outer:**

~~~java
class Vault {
    private static final int MAX = 100;

    static class Entry {
        int maximum() {
            return MAX;
        }
    }
}
~~~

`Entry.maximum()` reads `Vault.MAX` directly, without needing a Vault object.

**Instance member of outer:**

~~~java
class Vault {
    private final int secret;

    Vault(int secret) {
        this.secret = secret;
    }

    static class Inspector {
        int inspect(Vault target) {
            return target.secret;
        }
    }
}
~~~

This is a separate illustrative definition (do not combine it with the identically named Vault class in the previous snippet). `Inspector` **is allowed to read the private field `secret`**, but needs a **target reference** provided by the caller.

The two statements above do not contradict each other: **access control** answers “is there permission to read the field?”, while **instance ownership** answers “which object's field is being read?”.

## 9. Complete program 3 — reading a private instance field via an explicit parameter

Create the file **`NestedAccessDemo.java`**:

~~~java
final class Account {
    private static final String TYPE = "BASIC";
    private final String owner;
    private final int balance;

    Account(String owner, int balance) {
        this.owner = owner;
        this.balance = balance;
    }

    private String secretSummary() {
        return owner + ":" + balance;
    }

    static class AuditView {
        String describe(Account target) {
            return TYPE + "/" + target.secretSummary();
        }

        int balanceOf(Account target) {
            return target.balance;
        }
    }
}

public class NestedAccessDemo {
    public static void main(String[] args) {
        Account.AuditView audit = new Account.AuditView();
        Account first = new Account("An", 50);
        Account second = new Account("Binh", 80);

        System.out.println("first=" + audit.describe(first));
        System.out.println("second=" + audit.describe(second));
        System.out.println("first balance="
                + audit.balanceOf(first));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 NestedAccessDemo.java
java NestedAccessDemo
~~~

**Stdout:**

~~~text
first=BASIC/An:50
second=BASIC/Binh:80
first balance=50
~~~

`AuditView` is not automatically bound to `first` or `second`. It receives an Account via a parameter, so it can inspect multiple different Account objects, but only when the caller provides them.

Because `AuditView` is a nested class of `Account`, code inside it can access private `secretSummary()` and private `balance` according to Java rules. **This does not mean** any independent class outside has the same private access rights.

**Design warning:** private access permission is an implementation-organization tool; it does not automatically make exposing sensitive information through `AuditView.describe()` safe. You need to set access modifiers for APIs and control data according to actual requirements.

## 10. You can pass an Outer reference into a static nested object if truly needed

A static nested class has no **implicit Outer reference**, but you **can declare an explicit field** pointing to Outer when the domain requires it.

~~~java
class Workbench {
    private int completed;

    void finishOne() {
        completed++;
    }

    static class Button {
        private final Workbench target;

        Button(Workbench target) {
            this.target = java.util.Objects.requireNonNull(target);
        }

        void press() {
            target.finishOne();
        }
    }
}
~~~

This is a valid illustrative class; `Workbench.Button` has the `target` reference **because the programmer declared it themselves**. It is not a hidden `Workbench.this` generated automatically by the compiler as with a non-static inner class.

This structure is suitable when an object **intentionally** holds a dependency on Workbench. If Button only needs a primitive code or an immutable value, pass just the needed data instead of always holding the entire outer object.

The advantage of static nesting: **you are not forced to attach to an enclosing instance**. You explicitly control whether to store an Outer reference or not.

## 11. Complete program 4 — explicitly passed dependency

Create the file **`ExplicitOuterReferenceDemo.java`**:

~~~java
import java.util.Objects;

final class Machine {
    private final String name;
    private int jobsDone;

    Machine(String name) {
        this.name = name;
    }

    private void runJob() {
        jobsDone++;
    }

    int jobsDone() {
        return jobsDone;
    }

    static class Command {
        private final Machine machine;

        Command(Machine machine) {
            this.machine = Objects.requireNonNull(machine);
        }

        void execute() {
            machine.runJob();
        }

        String targetName() {
            return machine.name;
        }
    }
}

public class ExplicitOuterReferenceDemo {
    public static void main(String[] args) {
        Machine one = new Machine("M1");
        Machine two = new Machine("M2");
        Machine.Command first = new Machine.Command(one);
        Machine.Command second = new Machine.Command(two);

        first.execute();
        first.execute();
        second.execute();

        System.out.println("first target=" + first.targetName());
        System.out.println("second target=" + second.targetName());
        System.out.println("one jobs=" + one.jobsDone());
        System.out.println("two jobs=" + two.jobsDone());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ExplicitOuterReferenceDemo.java
java ExplicitOuterReferenceDemo
~~~

**Stdout:**

~~~text
first target=M1
second target=M2
one jobs=2
two jobs=1
~~~

`Machine.Command` is created with `new Machine.Command(one)`; **there is no need** to use `one.new Command()`, because Command is a static nested class.

In this case, each Command **deliberately stores a Machine reference**: that can keep Machine alive on the heap as long as Command remains reachable. You should not infer “a static nested class can never hold onto Outer”: it **just does not automatically have a hidden enclosing-instance reference**.

## 12. Inheritance and access permissions of a static nested class

A nested class can have appropriate access modifiers such as `public`, `protected`, package-private, or `private` when declared as a member class.

~~~java
public class ProductCatalog {
    public static class Entry {
        public String code() {
            return "P1";
        }
    }

    private static class Parser {
        static int parseId(String value) {
            return Integer.parseInt(value);
        }
    }

    public static int parse(String value) {
        return Parser.parseId(value);
    }
}
~~~

This is a valid illustrative class, assuming it is placed in the file `ProductCatalog.java` if `public class` is used. External callers can create `new ProductCatalog.Entry()`, but cannot directly call `ProductCatalog.Parser` without private access rights. The `ProductCatalog.parse(...)` method exposes a controlled API to the internal parser logic.

**Where the access modifier is placed matters:** top-level classes cannot be arbitrarily declared `private` or `protected`; member nested classes have those permissions under the JLS rules.

You should choose the smallest visibility that suffices. A static nested helper does not need to be public just because it “does not need an Outer object”.

## 13. Type names and namespaces: why nest classes?

When a type only makes sense in the context of another type, naming it `Outer.Nested` helps organize the API:

~~~java
class Network {
    static class Endpoint {
    }

    static class Options {
    }
}
~~~

These are valid definitions. The two classes `Endpoint` and `Options` are placed under the logical name `Network`, avoiding the need for long or overly generic top-level names.

**Advantages:**

- Group closely related types together.
- Set `private`/package-private visibility if it is an implementation detail.
- Use access to Outer's private members when genuinely needed.
- Use an enclosing class name as an API entry point, for example `Parser.Token`, `Graph.Node`, `Response.Status`.

**Trade-offs:** if Outer has too many large nested classes, the file becomes hard to read and class responsibilities bloat. A static nested class should not become a place to hold every unrelated utility simply because the syntax allows it.

## 14. A nested type name differs from a package name

In source code, `Outer.Nested` looks like a dotted name such as `java.util.Map.Entry`, but the relationship is a **member type**, not a package `Outer`.

If `Outer` belongs to package `com.example`, source code can use `com.example.Outer.Nested`. Upon compilation, the Java compiler typically generates class files like:

~~~text
Outer.class
Outer$Nested.class
~~~

The name containing `$` here is the binary-name convention for a member class in Java/JVM. In normal source code, use **`Outer.Nested`**, do not write `Outer$Nested` yourself as if it were the recommended source class name.

Do not guess the binary name by arbitrarily concatenating strings to write complex reflection code; use the class token `Outer.Nested.class` when possible, or `Class.getName()` and the metadata API.

## 15. Complete program 5 — Class objects and nested names

Create the file **`NestedClassMetadataDemo.java`**:

~~~java
class OuterType {
    static class StaticMember {
    }

    class InnerMember {
    }
}

public class NestedClassMetadataDemo {
    public static void main(String[] args) {
        Class<?> nested = OuterType.StaticMember.class;
        Class<?> inner = OuterType.InnerMember.class;

        System.out.println("nested simple="
                + nested.getSimpleName());
        System.out.println("nested binary=" + nested.getName());
        System.out.println("nested canonical="
                + nested.getCanonicalName());
        System.out.println("nested enclosing="
                + nested.getEnclosingClass().getSimpleName());

        System.out.println("inner binary=" + inner.getName());
        System.out.println("static nested is member="
                + nested.isMemberClass());
        System.out.println("inner is member=" + inner.isMemberClass());
        System.out.println("outer object required for token=false");
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 NestedClassMetadataDemo.java
java NestedClassMetadataDemo
~~~

**Exact stdout (classes in the unnamed package as in the file above):**

~~~text
nested simple=StaticMember
nested binary=OuterType$StaticMember
nested canonical=OuterType.StaticMember
nested enclosing=OuterType
inner binary=OuterType$InnerMember
static nested is member=true
inner is member=true
outer object required for token=false
~~~

Both the static nested member and the inner member are **member classes**; `Class.isMemberClass()` does not distinguish them by this boolean alone.

The last line is a **fixed message printed by the program**, illustrating that obtaining `OuterType.StaticMember.class` does not require creating an OuterType instance. To check the static modifier via reflection, you can inspect `Modifier.isStatic(nested.getModifiers())` instead of guessing from the class name.

## 16. Reflection can distinguish the `static` modifier

Class metadata allows checking:

~~~java
boolean staticMember = java.lang.reflect.Modifier.isStatic(
        OuterType.StaticMember.class.getModifiers());
~~~

This is an illustrative expression placed in a context that has `OuterType` as in the example above. With the declaration `static class StaticMember`, the result is indeed `true`.

For comparison:

~~~java
boolean innerMember = java.lang.reflect.Modifier.isStatic(
        OuterType.InnerMember.class.getModifiers());
~~~

With the non-static `class InnerMember`, the result is `false`.

This differs from `Class.isMemberClass()`: both are member classes, but only one member has the static modifier.

Do not use reflection just to “see whether Nested works” in a normal application. When the type is already known at compile time, creating `new Outer.Nested()` is clearer.

## 17. A generic Outer does not automatically pass its type parameter to a static nested class

A common source of errors:

~~~java
class Registry<T> {
    static class Key {
        private final String value;

        Key(String value) {
            this.value = value;
        }
    }
}
~~~

This is a valid illustrative generic class. `Registry<T>` has a type parameter `T` **belonging to the Registry instance/class declaration**, but `Key` is a static nested class so **it does not automatically have `T` within Outer's type parameter scope**.

The following code **intentionally does not compile** if uncommented:

~~~java
// class Registry<T> {
//     static class BadKey {
//         T payload; // T is a type parameter of Registry, invalid here.
//     }
// }
~~~

If a type parameter is needed for the nested class, **declare it directly on the nested class**:

~~~java
class Registry<T> {
    static class Key<U> {
        private final U payload;

        Key(U payload) {
            this.payload = payload;
        }

        U payload() {
            return payload;
        }
    }
}
~~~

`Registry.Key<String>` is a usable type, definitely not `Registry<String>.Key`. A static member class does not “accompany a generic Outer instance version” in that sense.

## 18. Complete program 6 — an independent generic nested type

Create the file **`GenericStaticNestedDemo.java`**:

~~~java
class Store<T> {
    private final T current;

    Store(T current) {
        this.current = current;
    }

    T current() {
        return current;
    }

    static class Receipt<U> {
        private final U item;

        Receipt(U item) {
            this.item = item;
        }

        U item() {
            return item;
        }
    }
}

public class GenericStaticNestedDemo {
    public static void main(String[] args) {
        Store<Integer> store = new Store<>(10);

        Store.Receipt<String> text =
                new Store.Receipt<>("paid");
        Store.Receipt<Integer> number =
                new Store.Receipt<>(42);

        System.out.println("store=" + store.current());
        System.out.println("text=" + text.item());
        System.out.println("number=" + number.item());
        System.out.println("receipt type="
                + text.getClass().getSimpleName());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GenericStaticNestedDemo.java
java GenericStaticNestedDemo
~~~

**Stdout:**

~~~text
store=10
text=paid
number=42
receipt type=Receipt
~~~

`Store<T>` and `Receipt<U>` have **independent type parameters**. `Store.Receipt<String>` is created directly with `new Store.Receipt<>("paid")`, without needing to provide a Store instance.

**Note on type erasure:** `Receipt<String>` and `Receipt<Integer>` still have the same runtime class `Store$Receipt`; type arguments do not create different concrete runtime classes.

## 19. A static nested class can contain other classes and its own members

A static nested class can further declare its own valid fields, constructors, methods, and nested types:

~~~java
class Packet {
    static class Header {
        static final int VERSION = 1;

        private final int sequence;

        Header(int sequence) {
            this.sequence = sequence;
        }

        int sequence() {
            return sequence;
        }

        static class Codec {
            static String encode(Header header) {
                return VERSION + ":" + header.sequence();
            }
        }
    }
}
~~~

This is valid illustrative code. You can use `Packet.Header.Codec.encode(new Packet.Header(5))`. Both `Header` and `Codec` are declared static nested; there is no implicit `Packet.this` or `Header.this` in Codec.

Even when types are nested across multiple levels, the number of enclosing instances **does not increase** for static nested classes. If code needs to access a Header instance, pass it into `encode(Header)` or a constructor.

Nesting too many levels deep can make an API long and hard to read. You should consider extracting types when they have independent responsibilities or are used in multiple places.

## 20. Complete program 7 — multiple levels of static nesting

Create the file **`NestedLevelsDemo.java`**:

~~~java
class Transport {
    static class Frame {
        private final int number;

        Frame(int number) {
            this.number = number;
        }

        static class Formatter {
            static String render(Frame frame) {
                return "frame#" + frame.number;
            }
        }
    }
}

public class NestedLevelsDemo {
    public static void main(String[] args) {
        Transport.Frame frame = new Transport.Frame(7);
        String output =
                Transport.Frame.Formatter.render(frame);

        System.out.println(output);
        System.out.println("class="
                + frame.getClass().getSimpleName());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 NestedLevelsDemo.java
java NestedLevelsDemo
~~~

**Stdout:**

~~~text
frame#7
class=Frame
~~~

Formatter can read `frame.number` via an explicit reference under nesting access rules. It does not need a Transport instance or Frame instance **to be initialized**; `render` in the example is a static method and takes a Frame object as a parameter.

## 21. A very common use case: static nested Builder

A **Builder** belongs to the logic of the Outer class, yet does not need to hold an **already-created Outer object** during the parameter-filling process. Therefore, `public static class Builder` is a common choice.

The idea:

~~~text
Create Outer.Builder (no Outer object yet)
     |
     | write candidate data into Builder
     v
call build()
     |
     | Outer's constructor/factory checks invariant
     v
return a complete Outer object
~~~

If Builder were a non-static inner class, the caller would normally have to **create Outer first**, whereas the purpose of a Builder is to prepare data **before Outer exists**. A static nested Builder avoids that circular dependency.

However, a Builder can hold its own mutable fields — `static nested` does not make a builder immutable. When `build()` returns a result, you must protect mutable data (lists, arrays) so that modifying the Builder afterward does not alter the already-built object.

## 22. Complete program 8 — static nested Builder creating an immutable outer

Create the file **`StaticNestedBuilderDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Course {
    private final String name;
    private final List<String> topics;

    private Course(Builder builder) {
        if (builder.name == null || builder.name.isBlank()) {
            throw new IllegalArgumentException("name rỗng");
        }
        name = builder.name;
        topics = List.copyOf(builder.topics);
    }

    String describe() {
        return name + "=" + topics;
    }

    static class Builder {
        private String name;
        private final List<String> topics = new ArrayList<>();

        Builder name(String next) {
            this.name = Objects.requireNonNull(next, "name");
            return this;
        }

        Builder addTopic(String topic) {
            topics.add(Objects.requireNonNull(topic, "topic"));
            return this;
        }

        Course build() {
            return new Course(this);
        }
    }
}

public class StaticNestedBuilderDemo {
    public static void main(String[] args) {
        Course.Builder builder = new Course.Builder()
                .name("Java")
                .addTopic("Class");

        Course first = builder.build();
        builder.addTopic("Object");
        Course second = builder.build();

        System.out.println("first=" + first.describe());
        System.out.println("second=" + second.describe());
        System.out.println("different=" + (first != second));

        try {
            first.describe();
            first.getClass();
            new Course.Builder().build();
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 StaticNestedBuilderDemo.java
java StaticNestedBuilderDemo
~~~

**Stdout:**

~~~text
first=Java=[Class]
second=Java=[Class, Object]
different=true
invalid=name rỗng
~~~

Explanation:

1. `new Course.Builder()` runs the Builder constructor, **without needing** a Course instance.
2. Builder can read and modify its own fields `name`, `topics`.
3. The private constructor `Course(Builder)` is allowed to read Builder's private fields under nesting access rules.
4. `Course` creates `List.copyOf(builder.topics)`, so the Builder adding another topic next does not modify the `first` object.
5. Builder does not depend on an implicit `Course.this`; it simply **passes itself** into the `Course` constructor when `build()` is called.
6. The call `new Course.Builder().build()` has no valid name, so the Course constructor throws an exception and does not return an invalid Course.

**Design note:** `Course.Builder` in the example is package-private to keep the lesson focused. If a library provides a Builder to code from another package, the API must declare `public static class Builder` and constructors/methods need appropriate `public` access. Another option is to add a static factory `Course.builder()`.

## 23. Factory method and `private` nested implementation

Not every nested class needs to be created directly by users. An Outer class can hide an implementation as a `private static class` and return an interface:

~~~java
interface Formatter {
    String format(String input);
}

final class Formatters {
    private Formatters() {
    }

    static Formatter prefix(String prefix) {
        return new PrefixFormatter(prefix);
    }

    private static class PrefixFormatter implements Formatter {
        private final String prefix;

        PrefixFormatter(String prefix) {
            this.prefix = prefix;
        }

        @Override
        public String format(String input) {
            return prefix + input;
        }
    }
}
~~~

This is valid illustrative code. The caller only knows the Formatter interface and the factory method `Formatters.prefix(...)`. The `PrefixFormatter` class is an implementation detail **placed under the name and access scope of Formatters**, without needing a Formatters instance.

This is a way to organize an implementation with a narrow scope of use, keeping the outer public API cleaner and avoiding exposing too many classes into the package.

## 24. Complete program 9 — private static nested implementation behind an interface

Create the file **`PrivateNestedImplementationDemo.java`**:

~~~java
interface Task {
    String run();
}

final class Tasks {
    private Tasks() {
    }

    static Task named(String name) {
        return new NamedTask(name);
    }

    private static final class NamedTask implements Task {
        private final String name;

        NamedTask(String name) {
            this.name = name;
        }

        @Override
        public String run() {
            return "run:" + name;
        }
    }
}

public class PrivateNestedImplementationDemo {
    public static void main(String[] args) {
        Task first = Tasks.named("A");
        Task second = Tasks.named("B");

        System.out.println("first=" + first.run());
        System.out.println("second=" + second.run());
        System.out.println("same=" + (first == second));
        System.out.println("runtime="
                + first.getClass().getSimpleName());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 PrivateNestedImplementationDemo.java
java PrivateNestedImplementationDemo
~~~

**Stdout:**

~~~text
first=run:A
second=run:B
same=false
runtime=NamedTask
~~~

`NamedTask` is a `private static final class`: external classes cannot directly reference this type by source name from places without access, but `Tasks.named` can create and return it under the `Task` interface.

`first.getClass()` still reflects the actual runtime class **NamedTask**, not Task; making the implementation class private only controls source access, and does not erase runtime class information.

## 25. Static nested classes help reduce implicit references to Outer

A non-static inner class can **hold onto its enclosing instance**. If the inner object outlives the outer object at the application level, that implicit reference can keep outer reachable so it is not yet reclaimed by the garbage collector.

A static nested class **does not automatically have that reference**, thereby avoiding a source of **unintended object retention** when the helper does not need outer state.

However:

- A static nested class **can still hold onto Outer** if you explicitly declare a field such as `Machine.Command.machine`.
- A static field in any class can still cause retention if it holds references for a long time.
- GC does not collect based simply on “whether the class is alive”; it depends on **object reachability** and class loader lifecycle.
- You should not promote “static nested classes never leak memory”; the accurate point is **there is no implicit enclosing-instance reference**.

If the helper needs outer state, having a non-static inner class attached to outer can be completely right. If not needed, a static nested class usually makes ownership easier to see.

## 26. Why does `Outer.Inner` sometimes require the `outer.new Inner()` syntax?

This stems from how a **non-static inner member class** is created, and does not apply to a static nested member class.

Example:

~~~java
class House {
    class Room {
    }

    static class Address {
    }
}
~~~

This is an illustrative definition. When the caller has:

~~~java
House house = new House();
House.Room room = house.new Room();
House.Address address = new House.Address();
~~~

`Room` needs a House enclosing instance, whereas `Address` does not. Even if you already have `house`, selecting Address from the `House` class still does not use `house.new Address()`.

When reading a compile-time error like “an enclosing instance that contains House.Room is required”, check whether you are using an **inner class** as a **static nested class**.

## 27. What `static nested` does NOT mean

Some common misconceptions:

| Misconception | Reality |
| --- | --- |
| “A nested object must create Outer first.” | A static nested class does not need an enclosing instance |
| “A static nested class means there is only one object.” | Each `new` still creates a separate instance |
| “Every field in a static nested class must be static.” | It can have instance fields and methods |
| “A static nested class cannot access Outer's private fields.” | It can under access rules; **instance fields need a receiver** |
| “A static nested class has `Outer.this`.” | There is no implicit enclosing instance |
| “A static nested class automatically inherits from Outer.” | No; lexical nesting **is not extends** |
| “A nested class has access to every object regardless of package.” | Access rules still apply; permissions within nesting follow declaration relationships |
| “`new Outer.Nested()` calls Outer's constructor.” | It only creates a Nested object, unless other logic is explicitly written |
| “Outer's generic parameter is automatically available in Nested.” | A static nested class must declare its own type parameter |
| “A nested class is a package.” | It is a member type of the enclosing type |
| “A static nested class cannot hold onto Outer.” | It can hold an **explicit reference** |
| “A static nested class is always better than a top-level class.” | It depends on scope of responsibility and API |
| “A static nested class is always immutable/thread-safe.” | Definitely not automatically |
| “A private static nested class is completely invisible at runtime.” | The runtime type still exists; source access is restricted |

## 28. Class initialization and object initialization: do not confuse them

Java has **class initialization** for static fields/blocks and **instance construction** for each object. A static nested class can have its own static initialization.

Key points:

- Simply mentioning `Outer.Nested` in source code or a class literal does not mean an Outer instance must be created.
- Creating `new Outer.Nested()` initializes the Nested class according to JVM rules, but **does not automatically create an Outer object**.
- Nested being a member of Outer does not automatically guarantee that every static initialization block of Outer must run before Nested is initialized; classes have initialization rules based on their own active use.
- If Nested code actively accesses a **non-constant static field** of Outer, that interaction can trigger initialization of Outer.
- Calling different constructors and class initialization are two distinct kinds of events.

Do not infer from the two class files `Outer.class` and `Outer$Nested.class` that the Outer constructor must run for the nested code to exist.

## 29. Complete program 10 — initializing Nested without creating an Outer instance

Create the file **`NestedInitializationDemo.java`**:

~~~java
class Host {
    static {
        System.out.println("Host static init");
    }

    Host() {
        System.out.println("Host constructor");
    }

    static class Worker {
        static {
            System.out.println("Worker static init");
        }

        Worker() {
            System.out.println("Worker constructor");
        }

        String work() {
            return "done";
        }
    }
}

public class NestedInitializationDemo {
    public static void main(String[] args) {
        System.out.println("begin");

        Host.Worker worker = new Host.Worker();
        System.out.println("work=" + worker.work());

        System.out.println("before Host");
        Host host = new Host();
        System.out.println("host class="
                + host.getClass().getSimpleName());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 NestedInitializationDemo.java
java NestedInitializationDemo
~~~

**Exact stdout:**

~~~text
begin
Worker static init
Worker constructor
work=done
before Host
Host static init
Host constructor
host class=Host
~~~

When `Host.Worker` is first created, the JVM initializes Worker and runs the Worker constructor. There is no reason yet to initialize Host in this section, because Worker does not actively read Host's static state.

At `new Host()`, the JVM initializes Host and runs the Host constructor. This proves that merely placing Worker **inside the Host declaration** does not automatically cause the Host constructor or static initializer to run when a Worker object is created.

**Scope of conclusion:** the standalone example has the exact class definitions shown above. If Worker accesses `Host.someNonConstantStaticField` during initialization, class initialization behavior may differ according to active-use rules.

## 30. How to convert an inner helper to a static nested class

When refactoring a helper from:

~~~java
class Outer {
    class Helper {
        void act() {
            doSomething();
        }
    }

    void doSomething() {
    }
}
~~~

to `static class Helper`, review all accesses to instance members:

1. Identify which fields/methods of Outer are being called **implicitly**.
2. If Helper does not actually need those values, remove the dependency.
3. If a small value is needed, pass that value into the Helper constructor/method.
4. If Helper needs to work with a specific Outer, pass an `Outer target` and make ownership explicit.
5. Replace all `outer.new Helper()` calls with `new Outer.Helper(...)` once the API has changed.
6. Update tests covering identity, lifecycle, and reference retention.
7. If Helper has a type parameter depending on Outer, declare a separate type parameter on the static nested class.

Do not mechanically convert every inner class into a static nested class: an inner class modeling “a room belonging to a specific house” may genuinely need the enclosing House instance.

## 31. Rules for choosing between inner and static nested for a problem

You can decide by asking:

**Does the helper need a specific enclosing object to operate?**

- **No:** a static nested class usually makes sense, for example `Configuration.Builder`, an independent `Tree.Node`, `Parser.Token`, a private adapter, an immutable result, or a helper that only uses static state or input parameters.
- **Yes:** a non-static inner class can express a tight relationship with the enclosing instance. Or a static nested class can accept an explicit Outer reference if clearer lifecycle control is desired.

**Does the helper need to exist as an independent public API in many places?**

- A **top-level class** may be easier to reuse, document, and test.
- If it is a small implementation detail used only by Outer, a private static nested class provides good encapsulation.

**Is Outer's generic type parameter needed?**

- A non-static inner class can reference the appropriate type parameter of Outer.
- A static nested class cannot directly use that type parameter; it needs its own `<U>` or must receive data under a different API.

Choose based on **data and ownership**, not merely on line count.

## 32. Common compilation errors

| Error/situation | Cause | Fix |
| --- | --- | --- |
| Creating inner with `new Outer.Inner()` from outside in a static context | Missing enclosing instance | Use `outer.new Inner()` |
| Creating static nested with `outer.new Nested()` | Using inner class syntax | Use `new Outer.Nested()` |
| Static nested code writes `Outer.this` | No implicit Outer instance | Pass an explicit Outer reference |
| Static nested code reads `outerInstanceField` directly | Missing receiver | Use `target.field` once a target is available |
| Using `private static class Helper` from external code | No private access | Use an outer public factory/API |
| Using generic `T` of `Outer<T>` inside static Nested | T is not in the static context | Declare `Nested<U>` |
| Thinking Nested is a subclass of Outer | Lexical nesting is not inheritance | Use `extends` only when the type relationship is right |
| Accessing `new Outer.Nested()` when constructor is private | Constructor is not accessible | Expose an appropriate constructor/factory |
| Reading an Outer instance field even though it is `private static`? | Confusing permission/receiver | Private static is readable under nesting rules |
| Builder holds a mutable list and passes it straight to Outer | Built object is aliased with Builder | Snapshot with `List.copyOf`/defensive copy |
| Assuming a nested class is automatically thread-safe | Static nesting does not synchronize | Use immutable state/concurrency APIs |
| Assuming static nested never retains Outer | There is an explicit reference field | Check object reachability/ownership |

### Intentional error example, not runnable code

~~~java
class Incorrect {
    private int number = 1;

    static class Nested {
        // int value() { return number; }
        // Wrong: number is an instance field of Incorrect.
    }
}
~~~

To read `number`, provide an `Incorrect target` reference and use `target.number`, or revise the design so that Nested only uses the data it actually needs.

## 33. Debugging by looking at reference types and access scope

When the compiler reports that a field cannot be found or a method cannot be accessed from a nested class:

1. Determine whether the identifier being used is a **class name** or an **object reference**.
2. Determine whether the field of Outer is **static** or **instance**.
3. Determine whether the nested class is a **static member** or a **non-static inner member**.
4. If it is an instance field, find the receiver object: is there a valid `this`/enclosing `Outer.this`, or a parameter `Outer target`?
5. Check the access modifiers (`private`, package-private, `protected`, `public`) of the member and the caller's location.
6. If the outer class is generic, check which type parameter belongs to which scope.
7. If the constructor is not accessible, check the visibility of the Nested constructor, not just the visibility of the Nested class.
8. For class-name errors, use `Outer.Nested` in source code and check packages/imports.

Do not fix a missing enclosing instance error by turning an **instance field into static** arbitrarily; doing so changes the nature of the state from per-Outer-object to class-wide shared state.

## 34. Practice exercises

**Exercise 1.** `class Outer { static class Nested {} }`: do you need to create `Outer outer = new Outer();` before calling `new Outer.Nested()`?

**Exercise 2.** Why can `static class Nested` still have instance fields?

**Exercise 3.** `Outer.Nested a = new Outer.Nested(); Outer.Nested b = new Outer.Nested();`. What is `a==b` normally?

**Exercise 4.** If Nested only reads `private static int LIMIT` of Outer, is an Outer instance needed?

**Exercise 5.** If Nested needs to read `private int id` of **a specific Outer object**, what is the valid and clear way?

**Exercise 6.** Does `Outer.this` exist in a static nested class? In which kind of member class does it usually exist?

**Exercise 7.** `class Outer { class Inner {} }`: from outside, what is the standard syntax to create Inner?

**Exercise 8.** `class Outer { static class Nested {} }`: is `outer.new Nested()` correct?

**Exercise 9.** Why is a Builder for an immutable Outer usually declared `static`?

**Exercise 10.** An `Outer.Builder` holds an ArrayList and the `build()` method passes that list directly to the published object. Can the Builder cause the already-built object to change?

**Exercise 11.** Does a nested helper have permission to read Outer's private fields? What question about the instance receiver must be distinguished?

**Exercise 12.** In `Outer<T>`, does a static nested class automatically see `T`? If you want a typed payload for Nested, what should you do?

**Exercise 13.** Can you create `Outer.Nested` with 10 objects without having any Outer object?

**Exercise 14.** Why can an `Outer.Nested` object still keep Outer alive for a long time on the heap even though it is a static nested class?

**Exercise 15.** What form does `Outer.Nested.class.getName()` usually have in the unnamed package?

**Exercise 16.** Does `Class.isMemberClass()` automatically distinguish static nested from non-static inner member?

**Exercise 17.** Does `new Outer.Nested()` necessarily run Outer's constructor and static initializer?

**Exercise 18.** Should you use a private static nested class or a public top-level class if the type is only an internal implementation of a factory?

**Exercise 19.** If a helper needs to depend on a specific Outer object to call an instance method, can a static nested class accept `Outer target` in its constructor?

**Exercise 20.** Does a static nested class automatically guarantee thread safety and immutability?

**Exercise 21.** Why should you pass only the necessary data instead of storing the entire Outer reference when the helper does not need ownership of the whole Outer?

**Exercise 22.** A public static nested class has a package-private constructor; can code in another package always do `new Outer.Nested()`?

**Exercise 23.** Does a static nested class inherit Outer's members merely because it is declared inside?

**Exercise 24.** In `Store<T>`, does `Store.Receipt<U>` have independent type arguments? Do you need to create a Store to create a Receipt?

### Answers and explanations

1. No. A static nested class is not bound to an enclosing instance.
2. `static` governs the nesting relationship; instances of Nested are still regular objects.
3. `false`, because the two `new` expressions create two distinct objects.
4. No; the member is static and Nested has private access rights via nesting rules.
5. Pass `Outer target` and then use `target.id`; access is permitted, but a receiver is still required.
6. No; a non-static inner member class has an appropriate enclosing instance and therefore can use `Outer.this`.
7. `outer.new Inner()` where `outer` is a valid Outer reference.
8. No, that is the syntax for a non-static inner class; use `new Outer.Nested()`.
9. The Builder must prepare data **before** the Outer object is constructed, so it does not need an enclosing instance.
10. Yes, if the built object and the Builder share the mutable list; the constructor should take a snapshot.
11. Yes, under access rules; an instance field still requires a **specific receiver object**.
12. No. A static nested class must declare its own type parameter such as `static class Nested<U>`.
13. Yes. `new Outer.Nested()` does not invoke the Outer constructor.
14. If the nested instance holds an explicit reference to Outer, or another link keeps Outer reachable.
15. Usually `Outer$Nested` for a member class, differing from the source name `Outer.Nested`.
16. No. Both are member classes; inspect the modifiers if you need to distinguish static.
17. No; nesting does not automatically require creating an Outer object, and class initialization has its own active-use rules.
18. A private static nested class is usually suitable for hiding an implementation; the factory returns an interface.
19. Yes. This is an explicit dependency, not an implicit enclosing instance.
20. No. Thread safety and immutability depend on fields, synchronization, ownership, and API.
21. To avoid unnecessary coupling and object retention; keep only dependencies that are actually needed.
22. No. Both class visibility and constructor visibility must be appropriate.
23. No. Nesting is a declaration/scope relationship, not `extends`.
24. Yes; `Receipt<U>` is independent of `Store<T>`, and no Store instance is required.

## 35. Checklist for using a static nested class

- Is the class placed inside an enclosing type for a clear purpose?
- Was **static nested** chosen instead of non-static inner because no implicit enclosing instance is needed?
- Is `new Outer.Nested(...)` used correctly instead of `outer.new Nested(...)`?
- Is the type name `Outer.Nested` distinguished from a package name and from an object reference?
- If reading Outer's instance state, is an **explicit reference** provided?
- Is `private` access not mistaken for automatically having a receiver?
- Are instance fields of Nested not mistaken for static fields?
- If the nested class is generic, have its own type parameters been declared?
- Is the constructor visibility appropriate for the callers?
- For an internal helper, was `private static class` considered to hide the implementation?
- For a Builder, does `build()` preserve the invariant and avoid mutable aliasing?
- If Nested holds an Outer reference, are lifecycle and retention understood?
- Is the number of nesting levels limited so that the code remains readable?
- If the class needs broad independent reuse, was a top-level class considered?
- Was creating Nested **before** any Outer instance tested to verify the assumption?
- Was mistakenly attributing singleton, immutability, or thread-safety guarantees to static nested avoided?

## 36. Official Java 17 documentation

- [JLS 17 §8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): distinguishing inner classes and enclosing instance contexts.
- [JLS 17 §8.5 — Member Type Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.5): declaring member classes/interfaces.
- [JLS 17 §8.5.1 — Static Member Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.5.1): static nested member classes and scope rules.
- [JLS 17 §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): `new` syntax, qualified creation, and inner classes.
- [JLS 17 §15.8.4 — Qualified this](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.4): `Outer.this` in appropriate contexts.
- [JLS 17 §6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): private/public/protected/member access.
- [JLS 17 §6.5 — Determining the Meaning of a Name](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.5): how Java resolves simple/qualified names.
- [JLS 17 §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): when static initialization occurs.
- [Java SE 17 API — Class.getEnclosingClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getEnclosingClass()): enclosing type metadata.
- [Java SE 17 API — Class.isMemberClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isMemberClass()): distinguishing member classes from local/anonymous classes.
- [Java SE 17 API — Modifier.isStatic](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Modifier.html#isStatic(int)): checking the static modifier via reflection.

**Conclusion:** A `static nested class` is a **member class grouped inside an enclosing type that does not carry an implicit enclosing instance**. You can create `new Outer.Nested()` without needing `new Outer()`. It is still a full class with its own constructors, instance state, methods, and visibility. If it needs private static members of Outer, it can access them under access rules; if it needs the **instance state of a specific Outer**, an explicit reference is required. Choose a static nested class when a type is tied to Outer for **API organization** but does not need to be bound to an **Outer object** — especially useful for Builders, helpers, and private implementations.
