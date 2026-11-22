# Accessing `private` Members and Enclosing Members in Nested Classes (Java 17+)

A class declared inside another class can access `private` members of the enclosing class according to the **access rules between nested declarations**. The reverse can also happen: code in the enclosing class is permitted to use `private` members of a nested class belonging to the same nesting context. However, **being permitted to access** does not mean **automatically having an object available to access**.

For example, `Outer.Nested` is a static nested class: code inside `Nested` can access `private static` members of `Outer`, but to read `private int value` of a specific `Outer` object, it must have a reference such as `target.value`. Conversely, a **non-static inner class** attached to an enclosing instance can use `Outer.this.value` to specify the enclosing object.

This is a Java Core lesson, module **class-object**, section **Nested Classes**; the goal is to understand **`private` access**, **enclosing instances**, **name resolution**, and **API organization** together. The standalone programs use Java **17+**, with run commands and stdout for comparison. Snippets that are merely illustrative or point out compile-time errors are clearly marked to avoid confusion with complete programs.

## 1. Two Questions to Separate Before Reading Code

When encountering `nested.someField`, ask in order:

1. **Access permission:** is this code location permitted to access the `someField` member? The `private`/package-private/`protected`/`public` modifier and the nesting relationship determine this.
2. **Receiving object (receiver):** is `someField` static or instance? If it is an instance member, **which object's** field are we accessing? Is there a valid `nested` variable, `Outer.this`, `this`, `target` parameter, or reference expression?

The two questions are independent. You may have sufficient permission but **lack a receiver**. You may have a receiver but **lack sufficient permission**. They cannot replace each other.

For example:

~~~java
class Vault {
    private int code = 7;

    static class Reader {
        int read(Vault target) {
            return target.code;
        }
    }
}
~~~

This is a valid definition. `Reader` is permitted to read the `private code` field of `Vault` due to the nesting relationship, and the method receives a `Vault target` as the receiver. If you omit the parameter and write `return code;` inside `Reader`, it is invalid: `Reader` does not automatically carry an enclosing Vault instance.

## 2. Comparison Table of Access Contexts

| Where the expression is written | `Outer.privateStatic` | `Outer.privateInstance` | Is `Outer.this` available? |
| --- | --- | --- | --- |
| Inside an instance method of `Outer` | Allowed | Via `this`/appropriate simple name | `this` is Outer, no qualified this needed |
| Inside a static method of `Outer` | Allowed | Only when `Outer target` is present | No |
| Inside non-static `Outer.Inner` | Allowed | Allowed via the appropriate enclosing instance | Yes |
| Inside static `Outer.Nested` | Allowed | Only with an explicit Outer reference | No |
| Inside an independent class without a private-access relationship | Not allowed | Not allowed, even with an Outer reference | No, not under that relationship |

The table illustrates how this works within **a normal Outer declaration** where the accessed members are present in the proper scope. In practice, simple names are also affected by shadowing and inheritance; when name collisions occur, explicit qualified expressions should be used.

## 3. `private` Remains Protected from External Code

`private` does not mean "only the lines of code inside the exact braces of the owning class can use it". Java allows access among **declarations belonging to the same nesting relationship** according to the JLS, helping an enclosing class and nested types collaborate as an internal implementation.

However, external code outside the permitted scope **cannot automatically access private members** merely by knowing the class name, knowing the package, or already having an object reference:

~~~java
class Account {
    private int balance = 10;

    static class Reader {
        int read(Account target) {
            return target.balance;
        }
    }
}

// In an independent class not in the same nesting relationship:
// int n = new Account().balance; // Intentionally invalid.
~~~

The code above is **illustrative**; the invalid access line has been commented out. External code can use the public/package API that Account intentionally exposes, rather than treating `private` as rendered ineffective because of nested classes.

**Important point on API safety:** a public method of a nested class that has permission to read a private field and **returns it** can expose data externally. Java enforces access control based on the declaration location; it does not automatically infer the business confidentiality of the returned data.

## 4. Complete Program 1 — Static Nested Class Reading `private` Members via Receiver

Create **`PrivateAccessWithReceiverDemo.java`**:

~~~java
final class Account {
    private static final String UNIT = "VND";
    private final String owner;
    private int balance;

    Account(String owner, int balance) {
        this.owner = owner;
        this.balance = balance;
    }

    private String summary() {
        return owner + ":" + balance;
    }

    static class Reader {
        String describe(Account source) {
            return UNIT + "/" + source.summary();
        }

        int balanceOf(Account source) {
            return source.balance;
        }
    }
}

public class PrivateAccessWithReceiverDemo {
    public static void main(String[] args) {
        Account.Reader reader = new Account.Reader();
        Account a = new Account("An", 50);
        Account b = new Account("Binh", 80);

        System.out.println("a=" + reader.describe(a));
        System.out.println("b=" + reader.describe(b));
        System.out.println("a balance=" + reader.balanceOf(a));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 PrivateAccessWithReceiverDemo.java
java PrivateAccessWithReceiverDemo
~~~

**Stdout:**

~~~text
a=VND/An:50
b=VND/Binh:80
a balance=50
~~~

Explanation: `Reader` is a **static nested class** of Account; creating `new Account.Reader()` does not create or attach to any Account instance. Reader is permitted to use `UNIT` and call the `private summary()` method of Account. It receives the `source` parameter to specify the object whose data is read; the same Reader can read multiple Accounts.

**Do not mistakenly think** `source.balance` is valid because the balance field is "not truly private". The field is still private; access permission is simply granted by Java in the appropriate nesting context.

## 5. The Reverse Direction: Outer Accessing `private` Members of a Nested Class

It is not only the nested class that reads private members of Outer. Code in the enclosing Outer can also access private fields/methods/constructors declared by the nested class, according to the nesting relationship.

~~~java
class Envelope {
    private static class Payload {
        private final String text;

        private Payload(String text) {
            this.text = text;
        }

        private String reveal() {
            return text;
        }
    }

    String open(String input) {
        Payload value = new Payload(input);
        return value.reveal();
    }
}
~~~

This is a valid illustrative class definition. `Payload` is a private static nested class, `Payload(String)` is a private constructor, and `Payload.reveal()` is also private. The `Envelope.open` method is permitted to call those members because it is code of the enclosing type.

A completely independent class is not allowed to directly create `new Envelope.Payload(...)`. If the caller only needs to open the envelope, expose the appropriate outer method instead of making the nested implementation public.

## 6. Complete Program 2 — Bidirectional `private` Access

Create **`BidirectionalPrivateDemo.java`**:

~~~java
final class Box {
    private final String prefix = "BOX";

    private static final class Token {
        private final int value;

        private Token(int value) {
            this.value = value;
        }

        private String label() {
            return "T" + value;
        }
    }

    String build(int number) {
        Token token = new Token(number);
        return prefix + ":" + token.label()
                + ":" + token.value;
    }

    private String suffix() {
        return "END";
    }

    class Inside {
        private int count;

        private void increase() {
            count++;
        }

        String report() {
            return prefix + ":" + suffix() + ":" + count;
        }
    }

    String update(Inside inside) {
        inside.increase();
        return inside.report();
    }
}

public class BidirectionalPrivateDemo {
    public static void main(String[] args) {
        Box box = new Box();
        System.out.println("token=" + box.build(7));

        Box.Inside inner = box.new Inside();
        System.out.println("before=" + inner.report());
        System.out.println("after=" + box.update(inner));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 BidirectionalPrivateDemo.java
java BidirectionalPrivateDemo
~~~

**Exact stdout:**

~~~text
token=BOX:T7:7
before=BOX:END:0
after=BOX:END:1
~~~

Here, Box is allowed to call the `Token` private constructor and private method. `Box.update` calls `Inside.increase()` even though it is private. In the reverse direction, `Inside.report` calls `Box.suffix()` and reads `Box.prefix` (both private).

`Inside` is attached to `box` via `box.new Inside()`, whereas `Token` is a static nested class and does not have an automatic enclosing Box instance.

## 7. `Outer.this`: Valid Only for Inner Classes with an Enclosing Instance

In a non-static inner member class, `this` is the object of the **inner class**. `Outer.this` is a reference to the **enclosing Outer object** attached to the inner object, when that kind of qualified this is valid.

~~~java
class Outer {
    private int value = 10;

    class Inner {
        private int value = 20;

        int innerValue() {
            return this.value;
        }

        int outerValue() {
            return Outer.this.value;
        }
    }
}
~~~

This is a valid illustrative class. From external code permitted to call it, we create:

~~~java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
~~~

The call `outer.new Inner()` creates an Inner **linked to outer**. `this.value` in Inner is 20; `Outer.this.value` is 10.

`Outer.this` is not "a way to access static fields", nor is it a user-named local variable. It is the qualified `this` syntax according to Java's rules, and it is **not available in a static nested class** without a suitable enclosing instance.

## 8. Complete Program 3 — `this` and `Outer.this`

Create **`OuterThisDemo.java`**:

~~~java
final class Workspace {
    private final String name;
    private int completed;

    Workspace(String name) {
        this.name = name;
    }

    class Job {
        private int completed;

        void finish() {
            this.completed++;
            Workspace.this.completed++;
        }

        String report() {
            return name + ":job=" + this.completed
                    + ",workspace=" + Workspace.this.completed;
        }
    }

    int totalCompleted() {
        return completed;
    }
}

public class OuterThisDemo {
    public static void main(String[] args) {
        Workspace a = new Workspace("A");
        Workspace b = new Workspace("B");

        Workspace.Job first = a.new Job();
        Workspace.Job second = a.new Job();
        Workspace.Job third = b.new Job();

        first.finish();
        first.finish();
        second.finish();
        third.finish();

        System.out.println("first=" + first.report());
        System.out.println("second=" + second.report());
        System.out.println("third=" + third.report());
        System.out.println("A total=" + a.totalCompleted());
        System.out.println("B total=" + b.totalCompleted());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 OuterThisDemo.java
java OuterThisDemo
~~~

**Stdout:**

~~~text
first=A:job=2,workspace=3
second=A:job=1,workspace=3
third=B:job=1,workspace=1
A total=3
B total=1
~~~

Each Job has its own `completed` field. The two Jobs `first` and `second` share the same enclosing Workspace `a`, so both update `a`'s own total; `third` is linked to Workspace `b`.

**One outer object can have multiple inner objects**, and each inner object is attached to an enclosing instance specified when created. There is no global `Outer.this` variable shared across all inner objects.

## 9. Name Shadowing: Local Variables, Inner Fields, and Outer Fields

**Scope resolution** and **private access** are two independent questions. If a parameter, inner field, and outer field have the same name:

~~~java
class Screen {
    private int width = 100;
    class Panel {
        private int width = 50;
        void show(int width) {
            System.out.println(width);            // parameter
            System.out.println(this.width);       // Panel field
            System.out.println(Screen.this.width);// Screen field
        }
    }
}
~~~

`Screen.this.width` is allowed to read the private field of Screen from the nested Panel according to the nesting access rules. Meanwhile, choosing the right object when names collide falls under **lexical shadowing**; see the lesson **Name Shadowing and Qualification with Outer.this** to learn about multi-level, inheritance, and lambda contexts.

## 10. Complete Program 4 — Three Levels of the Name `value`

Create **`ShadowedOuterMemberDemo.java`**:

~~~java
class Container {
    private int value = 10;

    class Member {
        private int value = 20;

        void print(int value) {
            System.out.println("parameter=" + value);
            System.out.println("inner=" + this.value);
            System.out.println("outer=" + Container.this.value);
        }
    }
}

public class ShadowedOuterMemberDemo {
    public static void main(String[] args) {
        Container container = new Container();
        Container.Member member = container.new Member();
        member.print(30);
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 ShadowedOuterMemberDemo.java
java ShadowedOuterMemberDemo
~~~

**Stdout:**

~~~text
parameter=30
inner=20
outer=10
~~~

Each expression points to **a different storage location**. If you replace `this.value` with `value` in `print`, that is the parameter 30, not the field 20.

When names collide, writing `Outer.this.field` also makes **the intent to select the right enclosing object** clearly visible in code review.

## 11. Static Nested Class: Private Access Exists, but `Outer.this` Does Not

Consider:

~~~java
class Device {
    private static int shared = 7;
    private int personal = 9;

    static class Detail {
        int readShared() {
            return shared;
        }

        int readPersonal(Device device) {
            return device.personal;
        }

        // int invalid() { return personal; }
        // int alsoInvalid() { return Device.this.personal; }
    }
}
~~~

This is a valid illustrative class because the intentionally invalid lines have been commented out.

`Detail` is permitted to read `Device.personal` through the **device instance** provided by the caller; it does not automatically have `Device.this`. `Device.shared` is a static member, so it can be read using the class name or its simple name if not shadowed.

Changing `personal` to `public` **does not make `return personal;` valid** in a static nested class without a receiver. The same member can both be accessible and require a specific object.

## 12. Complete Program 5 — Static Nested Class Accessing Private Static and Instance Members

Create **`StaticNestedPrivateDemo.java`**:

~~~java
class Meter {
    private static final String UNIT = "kWh";
    private final int reading;

    Meter(int reading) {
        this.reading = reading;
    }

    static class Formatter {
        String format(Meter source) {
            return source.reading + " " + UNIT;
        }

        String unit() {
            return UNIT;
        }
    }
}

public class StaticNestedPrivateDemo {
    public static void main(String[] args) {
        Meter.Formatter formatter = new Meter.Formatter();
        System.out.println("unit=" + formatter.unit());

        Meter first = new Meter(5);
        Meter second = new Meter(11);

        System.out.println("first=" + formatter.format(first));
        System.out.println("second=" + formatter.format(second));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 StaticNestedPrivateDemo.java
java StaticNestedPrivateDemo
~~~

**Stdout:**

~~~text
unit=kWh
first=5 kWh
second=11 kWh
~~~

`Meter.Formatter` is created **before** any Meter instance, proving it does not need an enclosing object. The `format` method accepts a specific Meter instance to access `private reading`.

If Formatter is required to always process a single Meter, it can intentionally store a `private final Meter target` field in its constructor. That is an **explicit reference**, not an enclosing reference implicitly added by Java.

## 13. Private Constructor of a Nested Class and Factory in the Enclosing Class

An enclosing class can hide a nested implementation using a `private static class`, use its private constructor, and then expose a simple interface.

~~~java
interface Parser {
    int parse(String text);
}

final class Parsers {
    private Parsers() {
    }

    static Parser decimal() {
        return new DecimalParser();
    }

    private static final class DecimalParser implements Parser {
        private DecimalParser() {
        }

        @Override
        public int parse(String text) {
            return Integer.parseInt(text);
        }
    }
}
~~~

These are valid illustrative classes/interfaces. `Parsers.decimal()` is inside the enclosing class so it can call the private constructor `DecimalParser()`, and then return the object under the `Parser` interface.

A caller does not have permission to write `new Parsers.DecimalParser()` from an independent class even if it knows the nested type exists. Both **the private access of the type and the private access of the constructor** are checked by Java; a nested class does not automatically expose all of its members.

## 14. Complete Program 6 — Outer Building a Private Nested Implementation

Create **`PrivateNestedFactoryDemo.java`**:

~~~java
interface Formatter {
    String apply(String text);
}

final class Formatters {
    private static final String SEPARATOR = ":";

    private Formatters() {
    }

    static Formatter labeled(String label) {
        return new LabeledFormatter(label);
    }

    private static final class LabeledFormatter
            implements Formatter {
        private final String label;

        private LabeledFormatter(String label) {
            this.label = label;
        }

        private String prefix() {
            return label + SEPARATOR;
        }

        @Override
        public String apply(String text) {
            return prefix() + text;
        }
    }
}

public class PrivateNestedFactoryDemo {
    public static void main(String[] args) {
        Formatter a = Formatters.labeled("INFO");
        Formatter b = Formatters.labeled("WARN");

        System.out.println(a.apply("start"));
        System.out.println(b.apply("stop"));
        System.out.println("same=" + (a == b));
        System.out.println("runtime="
                + a.getClass().getSimpleName());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 PrivateNestedFactoryDemo.java
java PrivateNestedFactoryDemo
~~~

**Stdout:**

~~~text
INFO:start
WARN:stop
same=false
runtime=LabeledFormatter
~~~

`LabeledFormatter` is a private static nested implementation. External code uses the Formatter interface. This class is permitted to read `Formatters.SEPARATOR` even though that field is private static; the enclosing class is permitted to call the private constructor of LabeledFormatter.

`getClass()` returns the runtime class **LabeledFormatter**, even though external source code is not allowed to directly reference the private nested type by name.

## 15. Two Nested Classes Belonging to the Same Enclosing Class Can Access Each Other's Private Members

The access rules for nested declarations do not apply solely to the **Outer ↔ Nested** pair. Member nested classes in the same context can work with each other's private members if the nesting relationships and access rules are satisfied.

~~~java
class Group {
    private static class Writer {
        private final String data = "secret";
    }

    private static class Reader {
        private String read(Writer writer) {
            return writer.data;
        }
    }
}
~~~

This is a valid illustrative class. `Reader` is not a subclass of `Writer`; it can still use `writer.data` because of Java's lexical nesting relationship, and because **it already has the receiver** `writer`.

This does not mean "all classes in the same package can read each other's private fields". Two independent top-level classes in the same package **do not automatically receive this permission**.

## 16. Complete Program 7 — Private Access Between Sibling Nested Classes

Create **`SiblingNestedPrivateDemo.java`**:

~~~java
final class Workflow {
    private static class Data {
        private final String label;
        private final int code;

        private Data(String label, int code) {
            this.label = label;
            this.code = code;
        }
    }

    private static class Presenter {
        private String present(Data source) {
            return source.label + "#" + source.code;
        }
    }

    static String present(String label, int code) {
        Data data = new Data(label, code);
        Presenter presenter = new Presenter();
        return presenter.present(data);
    }
}

public class SiblingNestedPrivateDemo {
    public static void main(String[] args) {
        System.out.println(Workflow.present("A", 7));
        System.out.println(Workflow.present("B", 9));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 SiblingNestedPrivateDemo.java
java SiblingNestedPrivateDemo
~~~

**Stdout:**

~~~text
A#7
B#9
~~~

`Workflow` is permitted to instantiate the private nested types and call their private constructors. `Presenter.present` reads the private fields of `Data` even though Presenter and Data are **siblings**, with no extends relationship.

If you move `Presenter` out to a completely independent top-level class, that private access is not automatically preserved; an appropriate API must be designed.

## 17. Nested Classes Do Not Automatically Inherit Fields/Methods of the Enclosing Class

Declaring `class Outer { class Inner { ... } }` is **lexical nesting**, not `Inner extends Outer`.

For example:

~~~java
class Root {
    private int code = 3;

    class Leaf {
        int codeFromEnclosingObject() {
            return Root.this.code;
        }
    }
}
~~~

This is an illustrative definition. `Leaf` is not a subtype of Root, so you cannot automatically pass Leaf to a method expecting Root. It can access `Root.this.code` because **it has an enclosing Root object** and is granted private access, not because of inheritance.

Even if `Root` has a `protected` or `public` method, that does not automatically make Leaf a subclass. It is necessary to distinguish between the **inheritance graph** and the **lexical nesting graph**.

## 18. Enclosing Instances at Multiple Levels: `Outer.this` and `Middle.this`

Across multiple **non-static inner** levels, an inner class can refer to valid enclosing instances using `Outer.this`, `Middle.this`, and `this`. `private` visibility does not prevent a valid member nested class from accessing private members of enclosing classes; however, each expression must select the right **receiver**.

~~~java
class City {
    private String name = "City";
    class District {
        private String name = "District";
        class Street {
            String cityName() { return City.this.name; }
            String districtName() { return District.this.name; }
        }
    }
}
~~~

`City.District.Street` is still an inner type with its own scope/owner; the nested class name **does not imply** that Street extends City or District. Three-level resolution and shadowing are mainly taught in B216.

## 19. Complete Program 8 — Multiple Levels of Enclosing Instances

Create **`MultipleEnclosingLevelsDemo.java`**:

~~~java
class Region {
    private final String name;

    Region(String name) {
        this.name = name;
    }

    class Zone {
        private final String name;

        Zone(String name) {
            this.name = name;
        }

        class Cell {
            private final String name;

            Cell(String name) {
                this.name = name;
            }

            String path() {
                return Region.this.name + "/"
                        + Zone.this.name + "/"
                        + this.name;
            }
        }
    }
}

public class MultipleEnclosingLevelsDemo {
    public static void main(String[] args) {
        Region region = new Region("North");
        Region.Zone zone = region.new Zone("Z1");
        Region.Zone.Cell cell = zone.new Cell("C9");

        System.out.println(cell.path());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 MultipleEnclosingLevelsDemo.java
java MultipleEnclosingLevelsDemo
~~~

**Stdout:**

~~~text
North/Z1/C9
~~~

`Cell` reads three private `name` fields through three receivers **of the right type**: `Region.this`, `Zone.this`, and `this`. No field needs to be changed to public to be accessed from a location with a valid nesting relationship.

If there is a **static nested class** in between, the `Outer.this` path does not automatically reach across the static boundary as with the chain of inner classes here; each actual enclosing-instance context needs to be checked.

## 20. Static Boundary: Cannot Reference `Outer.this` Across a Point Where No Instance Exists

Qualified `Host.this` only makes sense when the lexical environment actually has a **Host enclosing instance**. After a static nested boundary:

~~~java
class Host {
    private int id = 1;
    static class StaticLayer {
        class Inner {
            int read(Host host) { return host.id; }
            // int wrong() { return Host.this.id; } // Invalid
        }
    }
}
~~~

`Inner` can use `StaticLayer.this`, and does **not** automatically have `Host.this`; however, `host.id` is still valid thanks to the explicit receiver parameter and nesting access for private members. This distinguishes **permission** from **enclosing-instance existence**; lesson B216 covers qualified-this in full.

## 21. Local Classes and Anonymous Classes: Both Private Access and Local Variable Capture

A **local class** declared inside a method and an **anonymous class** created from an expression have their own scope rules. They can reference members of the enclosing class when a valid context exists, while also capturing local/parameter variables in scope that must be `final` or **effectively final**.

For example:

~~~java
class Greeter {
    private final String prefix = "Hello ";

    Runnable action(String name) {
        String punctuation = "!";

        class LocalTask implements Runnable {
            @Override
            public void run() {
                System.out.println(
                        prefix + name + punctuation);
            }
        }

        return new LocalTask();
    }
}
~~~

This is a valid illustrative class, without a main method yet. `LocalTask` can read the private `prefix` of the enclosing Greeter object; the parameter `name` and local variable `punctuation` are **effectively final**, so they are captured.

You cannot modify `punctuation` after creating the local class and expect the capture to remain valid under Java rules. **Capturing local variables** is different from **holding an enclosing instance** and different from **private access permission** — three rules that work together but are not the same thing.

## 22. Complete Program 9 — Local and Anonymous Classes Accessing Outer Private Members

Create **`LocalAnonymousPrivateDemo.java`**:

~~~java
final class GreetingService {
    private final String prefix;

    GreetingService(String prefix) {
        this.prefix = prefix;
    }

    Runnable localTask(String name) {
        String end = "!";

        class LocalTask implements Runnable {
            @Override
            public void run() {
                System.out.println(
                        prefix + name + end);
            }
        }

        return new LocalTask();
    }

    Runnable anonymousTask(String name) {
        String end = "?";

        return new Runnable() {
            @Override
            public void run() {
                System.out.println(
                        GreetingService.this.prefix
                        + name + end);
            }
        };
    }
}

public class LocalAnonymousPrivateDemo {
    public static void main(String[] args) {
        GreetingService service =
                new GreetingService("Hi ");
        service.localTask("An").run();
        service.anonymousTask("Binh").run();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 LocalAnonymousPrivateDemo.java
java LocalAnonymousPrivateDemo
~~~

**Stdout:**

~~~text
Hi An!
Hi Binh?
~~~

Both Runnable objects execute after `localTask`/`anonymousTask` have returned. They still retain the captured values according to Java's contract.

In the anonymous class, `this` is the instance of the anonymous Runnable, whereas `GreetingService.this` points directly to the enclosing GreetingService object. This lesson writes `GreetingService.this.prefix` to avoid confusing the receiver.

**Do not treat local/anonymous classes like static nested classes**: their declaration location and ability to capture variables make their mechanisms and limitations different.

## 23. Lambda: `this` Has a Different Meaning from an Anonymous Class

In a lambda expression, `this` does not create a new `this` object scope like an anonymous class does. Inside an instance method of Outer, `this` inside a lambda refers directly to the **Outer instance** according to lexical rules.

~~~java
class LoggerOwner {
    private final String tag = "OWNER";

    Runnable lambda() {
        return () -> System.out.println(this.tag);
    }

    Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(LoggerOwner.this.tag);
            }
        };
    }
}
~~~

This is a valid illustrative class. Both implementations print the tag, yet **`this`** in the lambda and in the anonymous class have different meanings. The anonymous class can use `LoggerOwner.this` to access the enclosing instance.

Do not rely on runtime class names generated by the compiler/JVM for a lambda or anonymous class to identify business logic. Private access location and lexical capture are more appropriate for understanding the behavior.

## 24. Complete Program 10 — Difference Between Lambda `this` and Anonymous `this`

Create **`LambdaAnonymousThisDemo.java`**:

~~~java
final class Display {
    private final String title = "Screen";

    Runnable lambda() {
        return () -> {
            System.out.println("lambda owner="
                    + this.getClass().getSimpleName());
            System.out.println("lambda title=" + title);
        };
    }

    Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                Object self = this;
                System.out.println("anonymous is Display="
                        + (self instanceof Display));
                System.out.println("anonymous outer title="
                        + Display.this.title);
            }
        };
    }
}

public class LambdaAnonymousThisDemo {
    public static void main(String[] args) {
        Display display = new Display();
        display.lambda().run();
        display.anonymous().run();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 LambdaAnonymousThisDemo.java
java LambdaAnonymousThisDemo
~~~

**Expected stdout:**

~~~text
lambda owner=Display
lambda title=Screen
anonymous is Display=false
anonymous outer title=Screen
~~~

In the lambda, `this` refers to the Display instance creating the lambda. In the anonymous class, `this` is the anonymous Runnable object, not Display. Only qualified `Display.this` refers to the enclosing Display instance.

**Important distinction:** inside an anonymous class, `this` has the type of the anonymous class, so the direct expression `this instanceof Display` does not compile when `Display` is `final` and the two types cannot be compatible. The Java 17 example above assigns `Object self = this;` before using `self instanceof Display`; this check compiles and returns `false`, while `Display.this` can still access the enclosing object.

## 25. Java 11+ Nestmates: Connection to Bytecode and the JVM

Since Java 11, the JVM has had **nest-based access control**: classes sharing the same **nest host** are considered **nestmates** and can perform private access at the JVM level according to nest rules. Class files can carry `NestHost` and `NestMembers` attributes.

When compiling Java 17, a modern compiler can use this mechanism to allow member classes to access private members without needing some of the synthetic accessor methods that used to appear frequently in bytecode compiled targeting older JDKs.

However:

- **Access permissions in Java source** are specified by the JLS, not by users manually declaring nestmates.
- **The JVM nestmate relationship** is established by metadata/class loading rules; two classes with similar names or in the same package are not automatically nestmates.
- Do not assume that every form of private access generates a synthetic method, nor assume that bytecode across all compiler versions is always identical.
- Do not modify binary names or use reflection to "hack" private access when you only need to design an API with appropriate access permissions.

This JVM information helps explain **why two member classes can access each other's private members**, especially when reading bytecode, compiler output, or debugging Java 17.

## 26. Complete Program 11 — Inspecting Nestmate Metadata with Reflection

Create **`NestmateMetadataDemo.java`**:

~~~java
class Family {
    class Child {
    }

    static class Helper {
    }
}

public class NestmateMetadataDemo {
    public static void main(String[] args) {
        Class<?> parent = Family.class;
        Class<?> child = Family.Child.class;
        Class<?> helper = Family.Helper.class;

        System.out.println("host="
                + child.getNestHost().getSimpleName());
        System.out.println("same host="
                + (helper.getNestHost() == parent));
        System.out.println("nestmates="
                + child.isNestmateOf(helper));
        System.out.println("member child="
                + child.isMemberClass());
        System.out.println("member helper="
                + helper.isMemberClass());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 NestmateMetadataDemo.java
java NestmateMetadataDemo
~~~

**Stdout with class files compiled together by Java 17 `javac`:**

~~~text
host=Family
same host=true
nestmates=true
member child=true
member helper=true
~~~

Both `Family.Child` and `Family.Helper` are member classes of Family; the JVM treats them as belonging to the same nest in this normal compilation output. `Class.isNestmateOf` has been available since Java 11.

**Note:** obtaining `Family.Child.class` only retrieves the class token; it **does not require** creating a Family instance. That holds true even though Child is a non-static inner member class, because class metadata and object construction are two separate things.

## 27. Private Access in Java Source Is Not Arbitrary Reflection Access

Even though nested code is permitted by the JLS to read private fields of the enclosing class, **code from an independent class does not automatically have such permission**. Reflection has its own access checks; the Java module system also enforces *strong encapsulation* rules.

Theoretical example:

~~~java
// Illustrative snippet, not a standalone program.
// Field secret = SomeType.class.getDeclaredField("secret");
// secret.setAccessible(true);
~~~

Using reflection to bypass private access just to save a getter/factory should not be encouraged. In Java 17, `setAccessible(true)` can be rejected (for example, with `InaccessibleObjectException`) if the module does not open the package for appropriate reflective access.

Nesting **does not break** system-wide module boundaries. Normal API design should use private helpers and intentional public/package contracts instead of relying on reflection to mutate internal state.

## 28. Interfaces and Member Types

Types declared inside an interface have their own rules. A **member class** declared in an interface is **implicitly `public static`**, not an inner class bound to an "interface object".

~~~java
interface Protocol {
    class Packet {
        private final String payload;

        Packet(String payload) {
            this.payload = payload;
        }

        String read() {
            return payload;
        }
    }
}
~~~

This is valid code. Within the same package, a caller can create `new Protocol.Packet("data")` if constructor access allows it. An object implementing `Protocol` **does not need** to exist to create a Packet.

Do not equate a "member type inside an interface" with an "inner class with an enclosing interface instance"; an interface **does not have instance fields** like an ordinary class does, and the nested member type here is static.

## 29. Encapsulation: Private Data Can Be Exposed Through a Public Nested API

A helper in the same nest can read a private field, yet whether information is exposed is still determined by the **method being called**:

~~~java
final class User {
    private final String passwordHash;

    User(String passwordHash) {
        this.passwordHash = passwordHash;
    }

    public static class Debugger {
        public String unsafeReveal(User user) {
            return user.passwordHash;
        }
    }
}
~~~

This is illustrative code that is **valid yet an intentional anti-pattern for secure design**. A caller can create `new User.Debugger()` and call `unsafeReveal`, because the public method deliberately exports private state.

Java does not let a caller read `user.passwordHash` directly in another class, yet **private access does not automatically prevent a public nested helper from returning the value**. Do not write such helpers for secrets; instead expose filtered results, masked values, or safe business information.

At the same time, `private` is a **language-level access semantic**, not an encryption scheme or data classification policy. For sensitive data, always consider logging, serialization, and access controls at other layers.

## 30. Lifetime: An Inner Class Can Retain Its Enclosing Instance

A member inner object has an enclosing owner association. When a callback is retained by a long-lived registry, the strong-reference path can keep the owner reachable even after the application has closed the screen:

~~~text
Registry → inner listener → enclosing controller
~~~

`private` access does not determine object lifetime; lifetime belongs to **GC reachability and subscription lifecycle**. Static nested helpers do not automatically hold an owner, though they can still hold an explicit `private final Outer owner`. Details on the risks, how to unregister, weak references, callback method references, and heap diagnostics are covered in the lesson **Implicit References to the Enclosing Object and Memory Retention Risks**.

## 31. Choosing Private Access Designs Without Tangling Responsibilities

Nested classes are often suitable for:

- **Builder** of an immutable class: reads private constructors/fields during `build()` without needing an existing Outer instance when using a static nested Builder.
- **Iterator** or a helper associated with **a collection instance**: a non-static inner class can use the enclosing instance when that binding is appropriate and intentional.
- **Private adapter**: a static nested implementation exposed only through an interface.
- **Parser/validator** closely tied to a class: a private static nested helper that reads private static constants or accepts outer values.
- **Record-like result** nested to group APIs and use a controlled constructor.

Prefer the **least access necessary**; do not make every nested class public. When a helper grows large or is used widely across many places, extracting it into a top-level class with a clear API can be easier to maintain.

A nesting relationship does not turn two classes into **a single responsibility** by design. You should only nest when the relationship is meaningful and the code remains readable.

## 32. Compile-Time Errors to Recognize

| Code/Situation | Underlying Issue | How to Fix |
| --- | --- | --- |
| `Outer.Nested` reads `private int x` using the name `x` | Static nested class lacks an Outer instance | Accept `Outer target` and use `target.x` |
| `Outer.Nested` uses `Outer.this.x` | No enclosing Outer instance exists | Use an explicit reference |
| Independent code uses `outer.secret` even though secret is private | No private access | Use the API exposed by Outer |
| Independent code calls `new Outer.PrivateNested()` | Nested type is not visible | Outer factory/method |
| Outer writes `nested.privateField` but the receiver has a different type | Wrong receiver/member resolution | Use the right nested object type |
| Inner uses `x` and mistakenly gets Inner's field | Shadowing | Use `Outer.this.x` |
| In inner, `this` is assumed to be Outer | `this` is the inner receiver | Use `Outer.this` |
| In an anonymous class, `this` is mistaken for Outer | `this` is the anonymous object | Use qualified Outer.this |
| Local class captures a reassigned variable | Variable is not effectively final | Extract a local final value |
| Static nested class inside generic Outer uses Outer's `T` | Outer's type parameter is not available in a static context | Declare `Nested<U>` |
| Code assumes lexical nesting means `extends` | No subtype relationship exists | Only use extends if it fits the model |
| Making a helper public and returning private data | Exposes representation/sensitive data via API | Reduce visibility, return a safe projection |
| Making an Outer reference static so nested can read it | Changes state from per-instance to shared | Pass the proper target object |
| Member is `private`, yet reflection is used to bypass it | May hit module access denial | Design an appropriate public/package contract |

A missing-receiver error **should not be fixed** by making an Outer instance field static: doing so changes the state from **per-object** to **class-wide shared** state.

## 33. Process for Analyzing an Access Expression

When you need to prove whether a nested expression is valid or invalid, follow this order:

1. **Code location**: is it inside Outer, static nested, non-static inner, local, anonymous, or an independent top-level class?
2. **Owner declaration** of the member: which class does the field/method belong to?
3. **Access modifier**: is the member private, protected, package-private, or public?
4. **Nesting relationship**: is the accessing code within the same scope allowed for private access under the JLS?
5. **Static or instance**: does the member require a receiver object?
6. **Enclosing instance**: does the inner class have an appropriate `Outer.this`, or only a `Nested.this`?
7. **Is there shadowing?** Is the simple name shadowed by a closer local/parameter/field?
8. **Is the reference null?** Accessing an instance field/method through null will cause a runtime error even if the compiler permits it.
9. **Is the compile-time type appropriate?** Even with sufficient permission, the expression still needs a type containing the matching member.
10. **API consequences**: should a public nested method really return private data externally?

This process helps avoid "fixing" private access errors by unnecessarily broadening visibility everywhere.

## 34. Practice Exercises

**Question 1.** Can a `private` member in Outer be read by a static nested class of Outer itself? If it is an instance field, what else is needed?

**Question 2.** In `Outer.Inner`, are `this` and `Outer.this` the same object?

**Question 3.** Is `Outer` allowed to call a private constructor/method of the nested class `Outer.Helper`?

**Question 4.** Can two static nested classes `Outer.A` and `Outer.B` read each other's private members in the same context? Is an object receiver needed?

**Question 5.** `Outer.Nested` contains `return outerValue;` where `outerValue` is a private instance field of Outer. Why cannot the error be fixed by changing `private` to `public`?

**Question 6.** `Outer.Inner` has a field `x=20`, Outer has `x=10`, and an Inner method takes parameter `x=30`. Write three expressions to retrieve those three values.

**Question 7.** If a nested helper does not need Outer's state, should you consider making it static or non-static? Why?

**Question 8.** A static nested helper needs to work with several different Outer objects. What is a sensible way to pass the dependency?

**Question 9.** Does an inner object created with `outerA.new Inner()` automatically switch to enclosing `outerB` if assigned to another variable?

**Question 10.** Does a class declared inside an interface require an instance of an interface implementation to be created?

**Question 11.** Non-static `Outer.Inner` resides inside `Outer<T>`; can it use Outer's type parameter T? What about the corresponding static nested class?

**Question 12.** A local class inside a method uses a local variable that is later reassigned. Does the compiler allow capturing it?

**Question 13.** Which object does `this` inside an anonymous Runnable method refer to? What about inside a lambda created by an Outer instance method?

**Question 14.** What do `NestHost`, `NestMembers`, and `Class.isNestmateOf` help investigate in Java 17?

**Question 15.** Are two different top-level classes in the same package allowed to use each other's private fields?

**Question 16.** A private static nested implementation is returned by an outer factory under a public interface; can the caller use the interface's behavior?

**Question 17.** If a public nested helper reads a private password hash and exposes that string, has Java blocked the disclosure?

**Question 18.** If `Outer.StaticLayer.InnerInStatic` has an inner instance of StaticLayer, does `Outer.this` automatically exist?

**Question 19.** Why can retaining an inner listener long-term keep its enclosing controller reachable?

**Question 20.** Should the `instanceBalance` field be made static just because a static nested helper needs to read it?

### Reference Answers

1. It has private access permission by nesting. For an instance field, an Outer receiver is still required, for example `target.field`.
2. No. `this` is the inner instance, and `Outer.this` is the enclosing Outer instance.
3. Yes, when nesting access rules are satisfied; however, a suitable receiver is required for an instance method/field.
4. Yes, according to nesting rules; instance fields must still be read on a specific A/B object.
5. The error is **a missing receiver**, not missing visibility.
6. `x` (30), `this.x` (20), `Outer.this.x` (10).
7. Static nested, because it does not need an implicit enclosing reference and makes ownership clearer.
8. Pass `Outer target` into the method/constructor; or pass only the needed data.
9. No. The enclosing instance is a relationship bound when creating the inner object; it does not change due to variable assignment.
10. No. A member class of an interface is implicitly static.
11. An inner member class can use T in an appropriate context; a static nested class cannot automatically use T and must declare its own parameter.
12. No. A captured local variable/parameter must be final or effectively final.
13. Anonymous `this` is the anonymous object; lambda `this` preserves the semantics of the enclosing lexical context.
14. Exploring JVM nest-based private access and nestmate relationship class metadata.
15. No, simply being in the same package does not grant private access.
16. Yes. The interface exposes the behavior; the concrete implementation type can remain hidden.
17. No. The public method deliberately returns the data; a private field does not automatically enforce business data policy.
18. No. The enclosing instance of that inner class is StaticLayer; StaticLayer does not carry an implicit Outer instance.
19. Because an inner object typically holds a reference to its enclosing instance, affecting object reachability.
20. No. That changes state sharing; pass the proper Outer receiver instead.

## 35. Practice Checklist

- Clearly identify which class declares the member?
- Have you separated **private access permission** and **receiver object**?
- When a static nested class reads an Outer instance field, is there an explicit reference?
- When using `Outer.this`, are you in a non-static inner context with a valid enclosing instance?
- Are you using `this` properly for inner/lambda/anonymous code?
- If two fields share the same name, have you distinguished parameter, `this.field`, and `Outer.this.field`?
- Do you understand that a nested class is not automatically a subclass of Outer?
- Does the enclosing Outer intentionally expose private state through public nested methods?
- Is a private nested constructor used through an outer factory when hiding an implementation?
- If there are multiple sibling nested classes, do you understand that private access is not synonymous with same-package access?
- If a local/anonymous class captures a variable, is the variable effectively final?
- If outer is generic, does the static nested class declare its own type parameters?
- If a nested object is long-lived, do you understand the impact of an enclosing reference/explicit reference?
- Have you avoided changing an instance field to static just to fix a missing receiver?
- Did you verify Java 17 syntax with runnable examples and distinguish illustrative snippets?
- When reading bytecode, do you understand Java 11+ nestmates without confusing them with source-language access?
- Are important private fields protected through the **exposed API** rather than just modifiers?

## 36. Java 17 Reference Documentation

- [JLS 17 §6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): conditions for accessing members and classes, including private access.
- [JLS 17 §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): scope and name visibility.
- [JLS 17 §6.4 — Shadowing and Obscuring](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.4): cases of name collision.
- [JLS 17 §8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): enclosing instances.
- [JLS 17 §8.5 — Member Type Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.5): nested member types.
- [JLS 17 §8.5.1 — Static Member Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.5.1): static nested members.
- [JLS 17 §15.8.4 — Qualified this](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.4): `Outer.this` syntax.
- [JLS 17 §15.9 — Class Instance Creation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): `outer.new Inner()` and `new Outer.Nested()`.
- [JLS 17 §15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): lexical context and `this` in lambdas.
- [JLS 17 §8.1.3 and §14.3 — Local Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3): local class scope.
- [JVMS 17 §5.4.4 — Access Control](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4): nestmate private access at the JVM level.
- [Java SE 17 API — Class.getNestHost](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getNestHost()): nest host.
- [Java SE 17 API — Class.isNestmateOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isNestmateOf(java.lang.Class)): checking nestmates.

**Conclusion:** A nesting relationship permits code in Outer and nested types to access each other's corresponding `private` members according to Java access rules. However, **access permission does not create a receiver**: a non-static inner class has an enclosing instance and can use `Outer.this`, whereas a static nested class lacks that reference and must accept an `Outer target` to read instance state. When multiple names collide, use `this.field` and `Outer.this.field` to select the right storage location. Protect both **access scope** and **public APIs capable of exposing private state externally**.
