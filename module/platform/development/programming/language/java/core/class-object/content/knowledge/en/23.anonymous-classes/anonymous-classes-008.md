# Drawbacks of Double-Brace Initialization in Java

**Double-brace initialization** is the informal name for the idiom `new ArrayList<String>() {{ add("A"); add("B"); }}`. It looks like a special syntax for creating and populating a collection in one line, but **Java has no dedicated language construct called “double brace initialization”**. Behind it are two existing Java mechanisms:

1. The first pair of curly braces `{ ... }` opens the **body of an anonymous class** extending `ArrayList<String>`.
2. The second pair of curly braces `{ ... }` is an **instance initializer block** inside that anonymous class. This block runs when an instance is constructed.

Therefore, the expression does not merely create an ordinary `ArrayList`: it also declares an **anonymous subclass** of `ArrayList`, then executes the `add` statements during subclass initialization. That is the source of the trade-offs in runtime type, lifecycle, references to the enclosing object, serialization, and readability.

This lesson belongs to **Java core – class-object**, in the **Anonymous Classes** group. The goal is to understand **why double-brace syntax is usually discouraged** and know how to choose the corresponding alternative in Java 17: `List.of`, `Set.of`, `Map.of`, `List.copyOf`, `new ArrayList<>(...)`, `new HashMap<>(...)`, `LinkedHashMap`, a custom constructor, or a Builder.

The standalone programs below use Java **17+**, with defined file names, compilation commands, and deterministic stdout. Snippets with intentional compilation errors are clearly marked and are not considered runnable examples.

## 1. Accurately Identifying the Two Pairs of Curly Braces

Look at the expression:

~~~java
java.util.List<String> names =
        new java.util.ArrayList<String>() {{
            add("An");
            add("Binh");
        }};
~~~

This is a **valid snippet inside an appropriate method or initializer**, not a complete program with `main`.

Component-by-component breakdown:

~~~text
new ArrayList<String>() {     ← opens the class body of the anonymous subclass
    {                         ← opens the instance initializer block
        add("An");            ← calls a method on the object being initialized
        add("Binh");
    }                         ← closes the instance initializer
};                            ← closes the anonymous class and ends the statement
~~~

The `new` keyword begins a **class instance creation expression**. The `()` invokes the matching superclass constructor (here, the no-argument constructor of ArrayList). The created anonymous class is a subtype of ArrayList. After the superclass is properly initialized, the subtype's instance initializer runs and adds the elements.

**Do not confuse** these two pairs of braces with a lambda `() -> { ... }`, with an array initializer `new String[] { ... }`, or with a collection literal in other languages. Java 17 does not have a general literal syntax `["An", "Binh"]` to create an ArrayList.

## 2. Runnable Example 1 — Collection Holds the Right Data but Has a Different Class

Create the file **`DoubleBraceBasicsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DoubleBraceBasicsDemo {
    public static void main(String[] args) {
        List<String> doubleBrace = new ArrayList<String>() {{
            add("An");
            add("Binh");
        }};

        List<String> ordinary =
                new ArrayList<>(List.of("An", "Binh"));

        System.out.println("doubleBrace=" + doubleBrace);
        System.out.println("ordinary=" + ordinary);
        System.out.println("equal content="
                + doubleBrace.equals(ordinary));
        System.out.println("anonymous="
                + doubleBrace.getClass().isAnonymousClass());
        System.out.println("exact ArrayList="
                + (doubleBrace.getClass() == ArrayList.class));
        System.out.println("ordinary exact ArrayList="
                + (ordinary.getClass() == ArrayList.class));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 DoubleBraceBasicsDemo.java
java DoubleBraceBasicsDemo
~~~

**Exact stdout:**

~~~text
doubleBrace=[An, Binh]
ordinary=[An, Binh]
equal content=true
anonymous=true
exact ArrayList=false
ordinary exact ArrayList=true
~~~

The two collections have **equal data according to `List.equals`**, but their runtime classes are not the same. `doubleBrace` is an instance of an **anonymous subclass**, whereas `ordinary` is an instance of `ArrayList` itself.

Because `List.equals` compares contents in order, the result is `equal content=true`; do not hastily generalize that **every** class in Java considers a subclass and its superclass with the same data to be equal.

## 3. Why Was This Idiom Once Attractive?

Before Java provided convenient collection factory methods such as `List.of`, `Set.of`, and `Map.of` (Java 9+), learners often wanted to shorten:

~~~java
List<String> names = new ArrayList<>();
names.add("An");
names.add("Binh");
~~~

into a single expression usable in a field initializer or when passing an argument:

~~~java
consume(new ArrayList<String>() {{
    add("An");
    add("Binh");
}});
~~~

The `consume(...)` snippet is **illustrative**, assuming there is a corresponding `consume(List<String>)` method.

The visible benefit is **inline convenience**. However, the gain of a few lines of code comes in exchange for things the reader must recognize: a new anonymous subclass, an initializer running right during construction, a possible outer reference/capture, and a runtime type different from `ArrayList.class`.

Once you understand the real mechanism, you will see that this is **not a collection literal**, does not make the collection immutable, and does not guarantee simple serialization.

## 4. Comparing the Initialization Path: Superclass Constructor → Instance Initializer

In Java, an instance initializer `{ ... }` consists of statements that execute during object creation according to the class's initialization rules, after superclass construction takes place properly.

Conceptual example:

~~~java
class TraceList extends java.util.ArrayList<String> {
    TraceList() {
        System.out.println("TraceList constructor");
    }
}
~~~

If you write `new TraceList() {{ add("A"); }}`, you are creating an **anonymous subclass of TraceList**, not just creating a TraceList. Before the expression returns the object, the statements in the instance initializer of the anonymous subclass are executed.

The initializer block can have **side effects**: logging, modifying a captured object, or throwing an exception. Therefore, a way of creating a collection that seems only to “list data” can execute arbitrary code right at initialization time.

## 5. Runnable Example 2 — Constructor and Initializer Order

Create the file **`DoubleBraceOrderDemo.java`**:

~~~java
import java.util.ArrayList;

class TraceList extends ArrayList<String> {
    TraceList() {
        System.out.println("TraceList constructor");
    }
}

public class DoubleBraceOrderDemo {
    public static void main(String[] args) {
        System.out.println("before new");

        TraceList values = new TraceList() {{
            System.out.println("anonymous initializer");
            add("A");
        }};

        System.out.println("after new");
        System.out.println("values=" + values);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 DoubleBraceOrderDemo.java
java DoubleBraceOrderDemo
~~~

**Stdout:**

~~~text
before new
TraceList constructor
anonymous initializer
after new
values=[A]
~~~

The `TraceList` constructor runs before the anonymous subclass's instance initializer. Only after the initializer finishes and the `new` expression returns does the program print `after new`.

**Do not mistake the timing:** the `add` calls inside the initializer **do not wait** until you use the list. They take place immediately during creation.

## 6. Drawback 1 — Generating an Unnecessary Anonymous Subclass

An ordinary list of data usually does not need a subclass. However, each double-brace expression is an **anonymous class declaration**:

~~~java
List<String> first = new ArrayList<String>() {{
    add("A");
}};

List<String> second = new ArrayList<String>() {{
    add("B");
}};
~~~

These are snippets inside a method. The two expressions appear at **two different source locations**, so they declare **two different anonymous classes**; each expression also creates a separate object when evaluated.

This can make debugging and type reflection confusing:

- `getClass()` does not return `ArrayList.class`, even though the object is still an `ArrayList` according to `instanceof`.
- Stack traces and debuggers may display compiler-generated names.
- Frameworks that use the exact runtime class may treat an anonymous subtype differently from the base class.
- Each anonymous class declaration has its own metadata/class initialization, although the specific impact depends on the compiler, runtime, and number of declarations.

**Do not exaggerate:** a double-brace expression inside a loop does not necessarily create **a new class for each iteration**. It creates **a new object each time `new` runs**, but objects from the **same declaration** generally have the same runtime class. This is the distinction between class identity and object identity.

## 7. Runnable Example 3 — One Declaration, Multiple Objects

Create the file **`AnonymousClassIdentityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AnonymousClassIdentityDemo {
    static List<String> make(String value) {
        return new ArrayList<String>() {{
            add(value);
        }};
    }

    public static void main(String[] args) {
        List<String> a = make("A");
        List<String> b = make("B");

        List<String> anotherDeclaration =
                new ArrayList<String>() {{
                    add("C");
                }};

        System.out.println("a=" + a);
        System.out.println("b=" + b);
        System.out.println("different objects=" + (a != b));
        System.out.println("same class="
                + (a.getClass() == b.getClass()));
        System.out.println("other declaration same class="
                + (a.getClass()
                   == anotherDeclaration.getClass()));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AnonymousClassIdentityDemo.java
java AnonymousClassIdentityDemo
~~~

**Stdout:**

~~~text
a=[A]
b=[B]
different objects=true
same class=true
other declaration same class=false
~~~

The two calls to `make` create different instances of the **same anonymous class declaration** in `make`; the separate captured values are A/B. The expression in `main` defines **another anonymous class**, so `getClass()==` is false.

**Comparison:** `new ArrayList<>(List.of("A"))` creates an ArrayList itself, without adding a subclass for the purpose of populating a few elements.

## 8. Drawback 2 — Easily Holding a Reference to the Enclosing Object

In an **instance method** of the `Owner` class, an anonymous inner class declared in an instance context may have a link to the enclosing instance `Owner.this`. If the class body references state of `Owner`, it needs a path to that object.

~~~java
class Owner {
    private final String name = "O1";

    java.util.List<String> create() {
        return new java.util.ArrayList<String>() {{
            add(Owner.this.name);
        }};
    }
}
~~~

This is a valid illustrative class. Inside the instance initializer, `Owner.this.name` refers to the `Owner` object that called `create()`; `this` of the initializer, by contrast, is the anonymous ArrayList instance.

If the collection is placed into a **long-lived cache/listener registry**, the reference to the enclosing object can contribute to keeping that object reachable, causing resources or memory to be released later than intended.

**Accurate phrasing:** not every double-brace case generates a `this$0` field with a fixed name/representation. The compiler, Java version, and actual need can influence the bytecode. The risk lies in the **semantics of enclosing instances/captured references**, especially evident when the body actually needs `Owner.this`. You should not rely on specific synthetic field names to build application logic.

## 9. Runnable Example 4 — `this` Is the Anonymous List, Not the Outer Object

Create the file **`OuterReferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class DocumentOwner {
    private final String ownerName;

    DocumentOwner(String ownerName) {
        this.ownerName = ownerName;
    }

    List<String> makeList() {
        return new ArrayList<String>() {{
            add("owner=" + DocumentOwner.this.ownerName);
            add("anonymous=" + getClass().isAnonymousClass());
        }};
    }
}

public class OuterReferenceDemo {
    public static void main(String[] args) {
        DocumentOwner owner = new DocumentOwner("An");
        List<String> values = owner.makeList();

        System.out.println(values);
        System.out.println("is list=" + (values instanceof List));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 OuterReferenceDemo.java
java OuterReferenceDemo
~~~

**Exact stdout:**

~~~text
[owner=An, anonymous=true]
is list=true
~~~

Inside the initializer of the anonymous ArrayList, `getClass()` has no explicit receiver, so it is equivalent to invoking it on `this` of the anonymous object; `DocumentOwner.this.ownerName`, on the other hand, reads from the outer object.

If you only need to store the string `"An"`, using a precomputed value and an ordinary ArrayList usually has **fewer lifetime constraints** than keeping an anonymous subclass mechanism that needs the enclosing owner.

## 10. Not Every Use of Double-Brace Has an Outer Instance

Double-brace written inside a **static method** has no enclosing instance of the method's declaring class to use `Outer.this`. It still creates an anonymous subclass and runs the instance initializer.

~~~java
class Lists {
    static java.util.List<String> values() {
        return new java.util.ArrayList<String>() {{
            add("A");
        }};
    }
}
~~~

This is a valid illustrative class. This code does not require a `Lists` object. It still carries the other trade-offs: an anonymous subclass, initialization via a block, a runtime type different from ArrayList, and the ability to capture local variables/parameters of the static method.

Therefore, saying “double-brace **always** leaks an outer instance” goes too far. It is better to say: in an **instance context**, especially when the body references `Outer.this`, there is a **risk of unnecessarily retaining the enclosing object**; in a static context, that risk does not arise in the same way.

## 11. Runnable Example 5 — Double-Brace in a Static Method

Create the file **`StaticDoubleBraceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class StaticDoubleBraceDemo {
    static List<String> create() {
        String message = "static";

        return new ArrayList<String>() {{
            add(message);
        }};
    }

    public static void main(String[] args) {
        List<String> values = create();
        System.out.println("values=" + values);
        System.out.println("anonymous="
                + values.getClass().isAnonymousClass());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 StaticDoubleBraceDemo.java
java StaticDoubleBraceDemo
~~~

**Stdout:**

~~~text
values=[static]
anonymous=true
~~~

`message` is an effectively final local variable captured by the anonymous class. Although there is no `StaticDoubleBraceDemo.this`, the collection is still an anonymous subclass. This syntax does not turn into a “collection literal” just because it appears in a static context.

## 12. Drawback 3 — Can Cause Serialization to Fail

`ArrayList` implements `Serializable`. Because the anonymous subclass inherits that, you might see:

~~~java
values instanceof java.io.Serializable
~~~

return true, and assume the object can definitely be written through `ObjectOutputStream`.

However, serialization must process **all of the object's serializable state**. An anonymous subclass may hold **captured data** or a **reference to a non-serializable outer object**; those references cause serialization to fail.

**Do not claim** that every double-brace list is non-serializable. A simple anonymous subclass that holds no external state can be serialized under suitable conditions. The risk lies in adding an **anonymous implementation and captured references**, which makes serializability harder to predict than with a plain data structure.

The next example intentionally holds a field referencing a non-serializable Outer to produce a **reliable, reproducible** failure without depending on synthetic field names.

## 13. Runnable Example 6 — `Serializable` Yet Serialization Still Fails

Create the file **`DoubleBraceSerializationDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.NotSerializableException;
import java.io.ObjectOutputStream;
import java.util.ArrayList;
import java.util.List;

final class NonSerializableOwner {
    private final String label = "owner";

    List<String> createList() {
        return new ArrayList<String>() {
            private final NonSerializableOwner capturedOwner =
                    NonSerializableOwner.this;

            {
                add("A");
            }
        };
    }
}

public class DoubleBraceSerializationDemo {
    public static void main(String[] args) throws Exception {
        List<String> values =
                new NonSerializableOwner().createList();

        System.out.println("serializable="
                + (values instanceof java.io.Serializable));
        System.out.println("values=" + values);

        try (var bytes = new ByteArrayOutputStream();
             var output = new ObjectOutputStream(bytes)) {
            output.writeObject(values);
            System.out.println("serialization success");
        } catch (NotSerializableException ex) {
            System.out.println("serialization="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 DoubleBraceSerializationDemo.java
java DoubleBraceSerializationDemo
~~~

**Stdout:**

~~~text
serializable=true
values=[A]
serialization=NotSerializableException
~~~

Explanation: ArrayList implements Serializable, so the `instanceof Serializable` check returns true. However, the anonymous subclass in the example has a `capturedOwner` field pointing to `NonSerializableOwner`, a class that does not implement Serializable. When serialization traverses the object graph, it throws `NotSerializableException`.

This demonstrates that **“the object is of type Serializable” does not mean the entire object graph is guaranteed to be serializable**. Do not solve this by blindly making every service/controller implement Serializable: you should design snapshot data/DTOs that are independent of runtime objects and lifecycles.

## 14. Drawback 4 — Runtime Type Can Surprise Code That Relies on the Exact Class

With `ArrayList`, most APIs using the `List` interface still work normally. However, if an application or framework checks:

~~~java
value.getClass() == ArrayList.class
~~~

then a double-brace list does not satisfy it, even though:

~~~java
value instanceof ArrayList
~~~

is still true.

There are two levels of difference:

- **Subtyping:** the anonymous subclass **is an** ArrayList according to inheritance rules; `instanceof ArrayList` is true.
- **Exact runtime class:** it **is not the ArrayList class itself**; `getClass()==ArrayList.class` is false.

Some frameworks may process objects based on runtime subtype, annotations, or serialization metadata; an anonymous subclass can become an unexpected type. Do not claim that every framework will fail: **you must check the contract of the framework in use**.

For ordinary code, prefer programming against the `List`/ `Map` interfaces rather than requiring an exact implementation class unless truly necessary.

## 15. Issues with `equals` on Classes Sensitive to Runtime Type

A custom class may implement `equals` based on the exact runtime class. In that case, an anonymous subclass from double-brace can cause **two objects with the same data not to be equal**.

Example:

~~~java
class StrictList extends java.util.ArrayList<String> {
    @Override
    public boolean equals(Object other) {
        return other != null
                && other.getClass() == getClass()
                && super.equals(other);
    }

    @Override
    public int hashCode() {
        return super.hashCode();
    }
}
~~~

This is a valid illustrative class. `StrictList.equals` deliberately requires the **same exact runtime class**, not just comparing contents. Implementing equals this way is a decision that needs careful consideration according to the equality contract; it is used here solely to clarify the risk of an anonymous subclass.

If you use `new StrictList() {{ add("A"); }}`, the instance has an anonymous subclass as its runtime class, so it can differ from `new StrictList()` even with the same contents.

**Do not apply this reasoning to the default `ArrayList.equals`:** ArrayList compares the elements of the List, so two lists can be equal even with different runtime classes, as in Example 1.

## 16. Runnable Example 7 — Equality Depending on Exact Class

Create the file **`ExactClassEqualityDemo.java`**:

~~~java
import java.util.ArrayList;

class StrictList extends ArrayList<String> {
    @Override
    public boolean equals(Object other) {
        return other != null
                && other.getClass() == getClass()
                && super.equals(other);
    }

    @Override
    public int hashCode() {
        return super.hashCode();
    }
}

public class ExactClassEqualityDemo {
    public static void main(String[] args) {
        StrictList ordinary = new StrictList();
        ordinary.add("A");

        StrictList anonymous = new StrictList() {{
            add("A");
        }};

        System.out.println("contents="
                + ordinary.toString().equals(
                    anonymous.toString()));
        System.out.println("ordinary equals anonymous="
                + ordinary.equals(anonymous));
        System.out.println("anonymous equals ordinary="
                + anonymous.equals(ordinary));
        System.out.println("same runtime class="
                + (ordinary.getClass()
                    == anonymous.getClass()));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ExactClassEqualityDemo.java
java ExactClassEqualityDemo
~~~

**Stdout:**

~~~text
contents=true
ordinary equals anonymous=false
anonymous equals ordinary=false
same runtime class=false
~~~

The two objects print the same string `[A]`, yet StrictList's custom equality rejects objects with a different exact runtime class. Here, `hashCode` still obeys the requirement that if two objects are equal, their hashes must be equal; two objects that are **not** equal are still allowed to have the same hash.

This example reinforces a principle: **an anonymous subclass is a type change**, not just a shorthand for populating data.

## 17. Drawback 5 — Code Easily Confuses Readers About `this`

In the instance initializer of an anonymous class, `this` refers to the **anonymous object**, not the enclosing outer object. If you call `add(...)` from inside the initializer, that call is equivalent to `this.add(...)` with the collection being created as the receiver.

~~~java
class Container {
    private final String label = "outer";

    java.util.List<String> build() {
        return new java.util.ArrayList<String>() {{
            add("anonymous=" + getClass().isAnonymousClass());
            add("label=" + Container.this.label);
        }};
    }
}
~~~

This is a valid illustrative class. In `build()`, `Container.this.label` refers to the enclosing instance, whereas `this.getClass()` refers to the anonymous ArrayList instance.

The fact that expressions with `this` have a different meaning than in the enclosing method makes double-brace **harder to review** when the body becomes complex, especially when field names collide.

If subclassing is not needed and you only need to assemble data, a normal builder/list completely avoids an unnecessary new `this` scope.

## 18. Drawback 6 — Side Effects and Exceptions During Data Creation

Readers might think that:

~~~java
List<String> words = new ArrayList<String>() {{
    add("A");
    add("B");
}};
~~~

is “creating data” similar to a literal. In reality, the initializer can call arbitrary methods, update other objects, or throw an exception. If the initializer fails, the `new` expression **does not return a complete object for assignment**; however, **external side effects that have already occurred are not automatically rolled back**.

This is why initialization logic should be kept simple and business operations should not be mixed into a collection initializer hidden behind the second pair of braces.

For operations that require validation, computation, or produce side effects, using a named factory method or a normal code block makes failure points easier to spot.

## 19. Runnable Example 8 — Creation Fails, External Side Effects Persist

Create the file **`DoubleBraceFailureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DoubleBraceFailureDemo {
    public static void main(String[] args) {
        List<String> audit = new ArrayList<>();

        try {
            List<String> result = new ArrayList<String>() {{
                audit.add("initializer started");
                add("A");

                if (audit.size() == 1) {
                    throw new IllegalArgumentException("blocked");
                }
            }};
            System.out.println("result=" + result);
        } catch (IllegalArgumentException ex) {
            System.out.println("failure=" + ex.getMessage());
        }

        System.out.println("audit=" + audit);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 DoubleBraceFailureDemo.java
java DoubleBraceFailureDemo
~~~

**Stdout:**

~~~text
failure=blocked
audit=[initializer started]
~~~

The anonymous initializer modifies the external `audit` list and then throws an exception. The `result` variable does not receive an object because creation fails; nevertheless, the `initializer started` element remains inside audit.

**Do not treat this as a flaw specific to ArrayList:** any constructor/factory/initializer with side effects can run into the same issue. Double-brace is particularly likely to obscure the fact that inside what looks like a “data literal” lies a **block of statements that can fail**.

## 20. Drawback 7 — Inheritance and Extensibility Risks

Double-brace is **anonymous subclassing**. It can only be used when the superclass allows subclassing and the constructor to be called has appropriate accessibility.

For example, the `String` class is declared final. The following snippet **intentionally does not compile**:

~~~java
// String s = new String() {{ /* ... */ }};
~~~

There is no analogous double-brace syntax to subclass a **final class**.

For classes with private/inaccessible constructors, sealed classes with permits rules, or classes not designed for inheritance, anonymous subclassing may be invalid or a poor idea.

Beyond compilation, if a superclass has protected hooks or overridable methods, an anonymous subclass can participate in the object lifecycle differently from what a reader expects. **Do not use subclassing just to populate a few elements**, especially with domain types that have complex invariants and lifecycles.

## 21. Drawback 8 — Harder Code Observability and Debugging

The runtime name of an anonymous class is usually a compiler-generated binary name; for example, a `$` sign and an index number may appear. That sequence number **is not a stable API** to store in configuration, a database, or use in business comparisons.

A debugging stack trace may also point to the initializer or the anonymous class rather than an application-named constructor/factory. If the initializer block is long, tracing errors will be less intuitive than with a method such as `buildRules()` or `createSeedData()`.

**Do not claim** that the JVM always generates the same set of bytecode/synthetic fields across all compilers. The key point is that the source code has created **an unnecessary anonymous subtype**, making the implementation identity harder to recognize.

Readability is often the most prominent drawback in large codebases: someone reading `Map.of("a",1,"b",2)` immediately understands these are entries, whereas someone reading double-brace must recognize **anonymous subclass + instance initializer** before evaluating further.

## 22. Drawback 9 — Not Automatically Immutable or Thread-Safe

An ordinary double-brace ArrayList/HashMap **is still mutable**:

~~~java
List<String> names = new ArrayList<String>() {{
    add("A");
}};
names.add("B");
~~~

This is a valid snippet inside a method. The list afterward contains A and B; using double braces does not lock the data.

By contrast, `List.of("A")` creates an **unmodifiable list** (which does not support mutation methods). However, do not infer that every element inside List.of is immutable: the list can still hold references to **mutable objects**.

Regarding concurrency, double-brace does not automatically make `ArrayList` or `HashMap` safe when multiple threads modify it concurrently. You need synchronization or a concurrent collection suited to the problem.

## 23. Runnable Example 9 — Distinguishing Mutable Lists from Unmodifiable Lists

Create the file **`MutableVsUnmodifiableDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class MutableVsUnmodifiableDemo {
    public static void main(String[] args) {
        List<String> concise = List.of("A", "B");
        List<String> editable = new ArrayList<>(concise);

        editable.add("C");

        System.out.println("concise=" + concise);
        System.out.println("editable=" + editable);

        try {
            concise.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("concise mutation="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("editable class="
                + (editable.getClass() == ArrayList.class));
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 MutableVsUnmodifiableDemo.java
java MutableVsUnmodifiableDemo
~~~

**Stdout:**

~~~text
concise=[A, B]
editable=[A, B, C]
concise mutation=UnsupportedOperationException
editable class=true
~~~

How to choose:

- If you need **fixed data that cannot be added to or removed from**, `List.of` is usually easy to read.
- If you need a **mutable ArrayList**, use `new ArrayList<>(List.of(...))`: it creates an exact ArrayList with initial data.
- If you need a **snapshot** of an existing collection, `List.copyOf(source)` provides an unmodifiable list, although that operation itself does not deep-copy mutable elements.

Do not use `List.of` just because it is short and then be surprised when `add` throws an exception; nor should you use double-brace just hoping for an immutable result.

## 24. Alternative 1 — `List.of` and `new ArrayList<>(...)`

Quick selection table:

| Purpose | Common Java 17 Approach |
| --- | --- |
| Small list, no structural modification | `List.of("A", "B")` |
| ArrayList modifiable after initialization | `new ArrayList<>(List.of("A", "B"))` |
| Empty mutable list | `new ArrayList<String>()` |
| Structurally unmodifiable snapshot from an existing collection | `List.copyOf(existing)` |
| List from elements that may be `null` | `new ArrayList<>(Arrays.asList("A", null))` if business rules allow |
| Multi-step data creation/validation | Explicit factory/builder method |

**Do not confuse the contracts:** `List.of` does not accept `null`, allows duplicate elements, preserves argument order, and returns an unmodifiable list. `List.copyOf` does not accept null elements in the source. `Arrays.asList` returns a fixed-size list backed by an array in appropriate usage, **not a mutable ArrayList supporting add/remove**; wrap it with `new ArrayList<>(...)` if you need a list that supports adding/removing.

If you expect to update the list continuously, writing a mutable ArrayList with its constructor can be clearer than creating an intermediate unmodifiable list just to copy it; when the data is complex, writing ordinary `add` statements is usually easiest to inspect.

## 25. Alternative 2 — `Set.of`, `Map.of`, `Map.ofEntries`

Double-brace is often seen with HashSet and HashMap:

~~~java
Set<String> flags = new HashSet<String>() {{
    add("READ");
    add("WRITE");
}};

Map<String, Integer> scores = new HashMap<String, Integer>() {{
    put("An", 10);
    put("Binh", 20);
}};
~~~

These are snippets, assuming complete imports. For data that **does not need structural mutation**, Java 17 provides:

~~~java
Set<String> flags = Set.of("READ", "WRITE");
Map<String, Integer> scores =
        Map.of("An", 10, "Binh", 20);
~~~

When many entries are needed, use `Map.ofEntries(Map.entry(...), ...)`. These factory methods **are not exact functional equivalents** of a double-brace HashMap/HashSet:

- `Set.of` and `Map.of` create **unmodifiable** collections.
- `Set.of` rejects duplicate elements; `Map.of` rejects duplicate keys.
- These factory methods reject `null` per the API.
- **The iteration order of Set/Map factories is not guaranteed** like `List.of`; do not write expected stdout that depends on `Map.of(...).toString()` or iteration order.
- `HashMap.put` with the same key **replaces the previous value**, whereas Map.of throws IllegalArgumentException for duplicate keys. This is a business difference to consider.

If you need a mutable Map, write `new HashMap<>(Map.of(...))`; if you need insertion order, consider `LinkedHashMap` and add elements with explicit statements.

## 26. Runnable Example 10 — Set/Map Factories and Exceptions for Duplicates/Nulls

Create the file **`CollectionFactoryRulesDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CollectionFactoryRulesDemo {
    public static void main(String[] args) {
        List<String> names = List.of("A", "A");
        Set<String> flags = Set.of("READ", "WRITE");
        Map<String, Integer> scores =
                Map.of("An", 10, "Binh", 20);

        System.out.println("list=" + names);
        System.out.println("flags contain READ="
                + flags.contains("READ"));
        System.out.println("score An=" + scores.get("An"));

        try {
            Set.of("A", "A");
        } catch (IllegalArgumentException ex) {
            System.out.println("duplicate set="
                    + ex.getClass().getSimpleName());
        }

        try {
            Map.of("x", 1, "x", 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("duplicate map="
                    + ex.getClass().getSimpleName());
        }

        try {
            List.of("A", null);
        } catch (NullPointerException ex) {
            System.out.println("null list="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 CollectionFactoryRulesDemo.java
java CollectionFactoryRulesDemo
~~~

**Stdout:**

~~~text
list=[A, A]
flags contain READ=true
score An=10
duplicate set=IllegalArgumentException
duplicate map=IllegalArgumentException
null list=NullPointerException
~~~

The example uses `contains` and `get` instead of printing the Set/Map directly, so it **does not depend on iteration order**. Check the API requirements before replacing double-brace: if the old code intentionally called `put` multiple times with the same key to update a value, switching straight to `Map.of` will change the behavior from overwriting to throwing an exception.

## 27. Alternative 3 — Mutable HashMap or LinkedHashMap with Explicit Ordering

When you need to add/modify entries later:

~~~java
Map<String, Integer> scores = new HashMap<>();
scores.put("An", 10);
scores.put("Binh", 20);
scores.put("An", 11);
~~~

This is a valid snippet with imports. The last line **updates key An** to 11; it is very readable and creates no anonymous subclass.

If you need to guarantee **insertion order** when iterating over keys, use `LinkedHashMap` instead of HashMap:

~~~java
Map<String, Integer> scores = new LinkedHashMap<>();
scores.put("An", 10);
scores.put("Binh", 20);
~~~

Do not rely on the printed order of HashMap or Map.of as a permanently fixed contract. By turning the initialization logic into a named constructor/helper, you can easily add validation or choose the appropriate Map type.

## 28. Runnable Example 11 — Ordered Mutable Map Without a Subclass

Create the file **`LinkedHashMapAlternativeDemo.java`**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

public class LinkedHashMapAlternativeDemo {
    public static void main(String[] args) {
        Map<String, Integer> scores = new LinkedHashMap<>();
        scores.put("An", 10);
        scores.put("Binh", 20);
        scores.put("An", 11);

        System.out.println("scores=" + scores);
        System.out.println("first key="
                + scores.keySet().iterator().next());
        System.out.println("An=" + scores.get("An"));
        System.out.println("class="
                + (scores.getClass() == LinkedHashMap.class));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LinkedHashMapAlternativeDemo.java
java LinkedHashMapAlternativeDemo
~~~

**Stdout:**

~~~text
scores={An=11, Binh=20}
first key=An
An=11
class=true
~~~

`LinkedHashMap` here uses **insertion-order iteration** by default; updating the value for key An does not move An to the end of the insertion order. This is clearer behavior than relying on a single HashMap run.

The code uses ordinary statements: `new`, `put` calls, and then using the result. There is no anonymous subclass or instance initializer hidden behind two pairs of braces.

## 29. Alternative 4 — Named Factory Method for Computed Data

If the data is produced using multiple branches, multiple loops, or requires validation, instead of stuffing logic into an anonymous initializer:

~~~java
Map<String, Integer> scores = new HashMap<String, Integer>() {{
    put("A", calculateA());
    put("B", calculateB());
}};
~~~

this is just a **conceptual snippet**, assuming the methods `calculateA()`/`calculateB()` exist.

A clearer way to express it is a **named factory**:

~~~java
static Map<String, Integer> buildScores(int a, int b) {
    if (a < 0 || b < 0) {
        throw new IllegalArgumentException("negative score");
    }

    Map<String, Integer> result = new LinkedHashMap<>();
    result.put("A", a);
    result.put("B", b);
    return Map.copyOf(result);
}
~~~

This is a valid illustrative method in a class with imports. It describes:

- The two inputs are validated before publishing the result.
- There is a temporary mutable Map scoped to the method.
- The API returns an **unmodifiable Map snapshot** via Map.copyOf.
- `Map.copyOf` does not guarantee preserving the insertion order of LinkedHashMap, so do not print the result's entry order as a requirement.

If insertion order is also required in the returned API, you can return `Collections.unmodifiableMap(new LinkedHashMap<>(result))`; that view is protected because the wrapper holds a **separate copy** without the caller holding a mutable reference in this code.

## 30. Runnable Example 12 — Factory Creating a Validated Data Map

Create the file **`NamedFactoryAlternativeDemo.java`**:

~~~java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public class NamedFactoryAlternativeDemo {
    static Map<String, Integer> buildScores(int a, int b) {
        if (a < 0 || b < 0) {
            throw new IllegalArgumentException("negative score");
        }

        Map<String, Integer> values = new LinkedHashMap<>();
        values.put("A", a);
        values.put("B", b);

        return Collections.unmodifiableMap(
                new LinkedHashMap<>(values));
    }

    public static void main(String[] args) {
        Map<String, Integer> scores = buildScores(5, 9);
        System.out.println("scores=" + scores);

        try {
            buildScores(-1, 9);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }

        try {
            scores.put("C", 3);
        } catch (UnsupportedOperationException ex) {
            System.out.println("immutable structure="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("after=" + scores);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 NamedFactoryAlternativeDemo.java
java NamedFactoryAlternativeDemo
~~~

**Stdout:**

~~~text
scores={A=5, B=9}
invalid=negative score
immutable structure=UnsupportedOperationException
after={A=5, B=9}
~~~

`Collections.unmodifiableMap` creates an **unmodifiable view** of the Map passed in; we explicitly create a separate `new LinkedHashMap<>(values)` before wrapping, so no other mutable variable in the method holds that original map. Thanks to this, the output and insertion order are controlled within the scope of the example.

An unmodifiable view **does not automatically deep-copy mutable values**. If the map's values are `List<MutableItem>`, you must design an appropriate snapshot for the elements/deep nesting; see the next section.

## 31. Alternatives Do Not Equal Deep Immutability

A common conversion mistake: replacing double-brace with `Map.of` and then claiming **the entire object graph is immutable**.

~~~java
List<String> editableTags = new ArrayList<>();
editableTags.add("A");

Map<String, List<String>> view =
        Map.of("tags", editableTags);
~~~

This is a valid snippet. `view.put(...)` is rejected, yet `editableTags.add("B")` still causes `view.get("tags")` to contain B because **the map holds a reference to a mutable list**.

When a stable snapshot is needed, copy the owned portion:

~~~java
Map<String, List<String>> snapshot =
        Map.of("tags", List.copyOf(editableTags));
~~~

If the elements are immutable `String` objects, `List.copyOf` isolates structural mutations of the source list. With mutable elements, you still need a defensive element copy or a separate immutable representation.

**Do not promote `List.of`, `Map.of`, and `Collections.unmodifiableList` as unconditional deep immutability.** Those are collection-level unmodifiable contracts and distinctions regarding snapshots/views, not clones of entire objects.

## 32. Runnable Example 13 — Map.unmodifiable Does Not Freeze a List Value

Create the file **`NestedMutableValueDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class NestedMutableValueDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        Map<String, List<String>> shared =
                Map.of("tags", source);
        Map<String, List<String>> snapshot =
                Map.of("tags", List.copyOf(source));

        System.out.println("shared before="
                + shared.get("tags"));
        System.out.println("snapshot before="
                + snapshot.get("tags"));

        source.add("B");

        System.out.println("shared after="
                + shared.get("tags"));
        System.out.println("snapshot after="
                + snapshot.get("tags"));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 NestedMutableValueDemo.java
java NestedMutableValueDemo
~~~

**Stdout:**

~~~text
shared before=[A]
snapshot before=[A]
shared after=[A, B]
snapshot after=[A]
~~~

The result shows that returning an unmodifiable Map does not guarantee the list inside is also a copy. For `String` data, `List.copyOf(source)` is enough to create a structurally unmodifiable snapshot, if the caller has no other mutable reference to the list inside the snapshot.

## 33. Drawback 10 — Validity of Captured Variables

Because double-brace creates an anonymous class, it follows the condition of capturing **final/effectively final local variables and parameters** just like other anonymous classes.

~~~java
int value = 5;
List<Integer> numbers = new ArrayList<Integer>() {{
    add(value);
}};
~~~

This is a valid snippet inside a method if `value` is not reassigned.

However, if the same method adds `value++;`, the variable `value` is not effectively final, and **the anonymous initializer cannot capture it**. This is a compile-time error.

With `new ArrayList<>(List.of(value))`, there is no anonymous class capturing `value`; the expression immediately uses the variable's current value. That can be more convenient when the variable value is updated after creating the list.

**Warning:** this does not mean the named constructor `new ArrayList<>(...)` automatically snapshots all mutable elements. It only avoids **capture rules arising from an anonymous class** and creates the list container according to the constructor contract.

## 34. Runnable Example 14 — Reassigning a Variable Still Works Without an Anonymous Class

Create the file **`NoCaptureNeededDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class NoCaptureNeededDemo {
    public static void main(String[] args) {
        int value = 5;
        List<Integer> first =
                new ArrayList<>(List.of(value));

        value = 8;
        List<Integer> second =
                new ArrayList<>(List.of(value));

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("current value=" + value);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 NoCaptureNeededDemo.java
java NoCaptureNeededDemo
~~~

**Stdout:**

~~~text
first=[5]
second=[8]
current value=8
~~~

The `value` variable is reassigned normally because no anonymous class/lambda captures it here. Each constructor receives its data from the value at the time of the call.

If you replace it with an anonymous initializer that directly references `value` inside a method with this reassignment, the compiler will reject it. This is an **unnecessary cost** when the goal is only to populate a primitive value into a collection.

## 35. When Is an Anonymous Subclass Intentional?

An anonymous subclass **is not inherently bad**. It is a valid Java mechanism when you genuinely need to:

- Override superclass behavior at the point of use.
- Create a short implementation of an interface with multiple abstract methods.
- Have instance fields/helper methods serving a specific callback.
- Choose the appropriate `this` and superclass behavior of the anonymous instance.

What should be avoided is using subclassing **solely** to shorten:

~~~java
new HashMap<String, Integer>() {{
    put("a", 1);
    put("b", 2);
}}
~~~

if what you want to express is only “a Map containing two entries”. In that case, a Map factory/ordinary constructor states the intent more directly and avoids many side effects of subclassing.

**Decision criterion:** do you want a **new behavioral type** or simply **existing data in a collection**? If you only want data, double braces are usually a mismatched tool.

## 36. Replacement List by Specific Requirement

| Practical Requirement | Java 17 Suggestion | Notes |
| --- | --- | --- |
| List of a few Strings, no modification needed | `List.of("A","B")` | Does not accept null |
| Mutable list with initial data | `new ArrayList<>(List.of("A","B"))` | Exact ArrayList class |
| Mutable list allowing null | `new ArrayList<>(Arrays.asList("A",null))` | Avoid List.of because of null |
| Empty mutable list | `new ArrayList<>()` | Simple, no subclass |
| Unmodifiable set, unique elements | `Set.of("READ","WRITE")` | Duplicates/null are rejected |
| Mutable HashSet | `new HashSet<>(Set.of("READ","WRITE"))` | Does not guarantee iteration order |
| Small unmodifiable map | `Map.of("a",1,"b",2)` | No null/duplicate keys; iteration order unspecified |
| Large unmodifiable map | `Map.ofEntries(Map.entry(...), ...)` | Watch out for null/duplicates |
| Mutable HashMap | `new HashMap<>(Map.of("a",1))` | Can `put` later |
| Map needing insertion order | `LinkedHashMap` + statements | Controls iteration |
| Conditional or multi-step creation | Named factory method | Easy to validate and test |
| Need an unmodifiable snapshot from an existing list | `List.copyOf(existing)` | Does not deep-copy mutable elements |
| Want an unmodifiable view in insertion order | `Collections.unmodifiableMap(new LinkedHashMap<>(source))` | The view holds a separate copy |
| Domain object with multiple fields, invariants | Builder/constructor/factory | Do not put logic into an anonymous initializer |
| Need genuinely anonymous behavior | Anonymous class/lambda | Do not use double-brace merely as a data literal |

Do not choose based on syntactic brevity **while ignoring mutability, null policy, equality, and iteration order**.

## 37. Principled Alternative Example: An Immutable Domain Object

When there are multiple fields and validation, instead of double-bracing into a Map “containing everything”, use an explicit type.

Create the file **`ImmutableProfileDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Profile {
    private final String name;
    private final List<String> roles;

    private Profile(Builder builder) {
        if (builder.name == null || builder.name.isBlank()) {
            throw new IllegalArgumentException("name rỗng");
        }
        name = builder.name;
        roles = List.copyOf(builder.roles);
    }

    static class Builder {
        private String name;
        private final List<String> roles = new ArrayList<>();

        Builder name(String value) {
            name = Objects.requireNonNull(value, "name");
            return this;
        }

        Builder addRole(String role) {
            roles.add(Objects.requireNonNull(role, "role"));
            return this;
        }

        Profile build() {
            return new Profile(this);
        }
    }

    String describe() {
        return name + roles;
    }
}

public class ImmutableProfileDemo {
    public static void main(String[] args) {
        Profile.Builder builder = new Profile.Builder()
                .name("An")
                .addRole("reader");

        Profile first = builder.build();
        builder.addRole("editor");
        Profile second = builder.build();

        System.out.println("first=" + first.describe());
        System.out.println("second=" + second.describe());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ImmutableProfileDemo.java
java ImmutableProfileDemo
~~~

**Stdout:**

~~~text
first=An[reader]
second=An[reader, editor]
~~~

Builder is a **named static nested class**, designed to collect data before creating a Profile. The Profile constructor validates name and creates an unmodifiable snapshot of roles. If the Builder continues receiving new roles, the old Profile does not change.

This is an appropriate solution for **domain data with invariants**, not because every collection must use a builder. For just two String constants, `List.of` is simpler.

## 38. Performance Cost: Assessing It Accurately

Double-brace can add an anonymous class declaration to a program instead of using ArrayList/HashMap directly. That can affect:

- Class metadata and class loading.
- Code size, reflection/introspection, and debugging.
- Certain runtime/framework optimization or serialization capabilities.
- The lifetime of captured objects if they are retained for a long time.

However, **there is no rule** stating that “double-brace is always N times slower” or “each added element costs one class”. Actual performance depends on call sites, JIT, runtime, garbage collection, class loader, object count, and workload.

To optimize, measure with a profiler/JMH if needed. **The strongest reasons to avoid double-brace are usually correct semantics, readability, and avoiding type/lifecycle surprises**, rather than an unmeasured performance number.

Factory methods such as `List.of` may allow implementation-specific optimizations, yet Java does not require a specific runtime object layout or identity. Do not write code that depends on `getClass().getName()` of List.of.

## 39. Risks in Testing and Maintaining Legacy Code

If you encounter double-brace in a legacy codebase, do not mechanically replace every occurrence with `List.of` or `Map.of` without inspecting its behavior.

First, confirm:

1. **Is the collection modified after construction?** If so, a mutable alternative is needed.
2. **Are there null elements/keys/values?** The of/copyOf factories have stricter null policies.
3. **Are there duplicate keys/entries?** Map.of/Set.of may throw an exception where HashMap/HashSet previously did not.
4. **Is there a dependency on iteration order?** Choose LinkedHashMap/LinkedHashSet or an appropriate List.
5. **Does it capture an outer object or local variable?** Clean up that dependency if not needed.
6. **Does it override a method or add a field in the anonymous body?** In that case, it may be an intentional anonymous subclass, not just data initialization.
7. **Is serialization used?** Test the actual object graph.
8. **Does any framework rely on the runtime subclass?** Check the specific mapping/serialization.
9. **Are there initialization side effects?** Move them to a named execution path and check exception safety.
10. **Is there equality- or identity-sensitive code?** Removing the anonymous subtype may change the result of `getClass()`/custom equals.

**Two-way testing:** if you switch to an unmodifiable list, test mutation to see whether callers need to modify the data. If you switch to a mutable list, make sure callers do not inadvertently expose internal representation.

## 40. Checklist for Reviewing a Double-Brace Expression

When you see `new T(args) {{ ... }}` in code:

- Is T an inheritable class, and is the constructor with args accessible?
- Is the outer pair of braces an anonymous class body, or does it have another meaning?
- Is the inner pair of braces an instance initializer running at `new`?
- Is there a field/method override that genuinely needs an anonymous subclass?
- Can it be replaced with `List.of`, `Set.of`, or `Map.of`?
- Does the target collection need to be mutable or unmodifiable?
- Are there null/duplicates/order requirements?
- Is there an instance context where the body needs `Outer.this`?
- Are there captured final/effectively final local variables/parameters?
- Is there a risk of keeping Outer or a large dependency reachable for too long?
- Does the object need to be serialized? Are the captured references serializable?
- Will a runtime class different from the exact base class break a framework/test?
- Does the domain class's `equals` depend on the exact runtime type?
- Does the instance initializer have side effects, I/O, or complex validation?
- Is it appropriate to move the code into a named factory with dedicated tests?
- If the code has been changed, do tests preserve the data and mutation semantics?

## 41. Practice Exercises

**Question 1.** In `new ArrayList<String>() {{ add("A"); }}`, what do the first and second pairs of braces mean?

**Question 2.** Is `getClass()==ArrayList.class` true for a double-brace list? What about `instanceof ArrayList`?

**Question 3.** A double-brace expression inside a factory is called three times. Are there three anonymous classes or three objects from one declaration?

**Question 4.** Do two double-brace expressions at two different source locations necessarily have the same runtime class?

**Question 5.** Why can a double-brace created inside an instance method keep the enclosing Owner object reachable?

**Question 6.** Does writing it inside a static method automatically solve the anonymous subclass drawback?

**Question 7.** Why can a subclass of ArrayList be `instanceof Serializable` while `ObjectOutputStream.writeObject` still fails?

**Question 8.** Inside a double-brace instance initializer, which object does `this` point to?

**Question 9.** Given `List<String> a = List.of("X");`, can you call `a.add("Y")`?

**Question 10.** Which Java 17 syntax creates a mutable ArrayList containing X, Y without declaring an anonymous subclass?

**Question 11.** What does `Set.of("A","A")` do? What about a HashSet where A is added twice?

**Question 12.** How does `Map.of("x",1,"x",2)` differ from `HashMap.put("x",1); put("x",2);`?

**Question 13.** Why should you not print `Map.of("a",1,"b",2)` and use that string order as a fixed expected stdout?

**Question 14.** If you need to preserve insertion order when iterating over a Map, which collection should you choose?

**Question 15.** A custom list compares `getClass()` in `equals`. What surprise can an anonymous subclass create?

**Question 16.** Does double-brace make a list immutable or thread-safe?

**Question 17.** Does `Map.of("tags", mutableList)` deep-copy the list?

**Question 18.** If an anonymous initializer modifies an audit log and then throws an exception, is the audit log automatically rolled back?

**Question 19.** Suppose you want to capture variable `int n` in a double-brace initializer, and the method later writes `n++`. Can it compile?

**Question 20.** If you use `new ArrayList<>(List.of(n))`, can the method reassign n after creating the list?

**Question 21.** When you need multi-field validation and to return an immutable domain object, should you use a double-brace HashMap or a strongly typed constructor/builder?

**Question 22.** Does `List.copyOf(source)` deep-copy mutable elements?

**Question 23.** Why should you not rely on the binary name `Outer$1` of an anonymous class as an ID?

**Question 24.** When migrating double-brace to List.of, what are the two important test groups to run?

### Answers and Explanations

1. The outer pair is the **anonymous subclass body**, and the inner pair is the **instance initializer block**.
2. `getClass()==ArrayList.class` is false; `instanceof ArrayList` is true if it is a valid subclass.
3. Three objects from the same anonymous class declaration at one source location, not three classes by default.
4. No; two different anonymous declarations correspond to two different types.
5. The body can reference the enclosing instance, and a long-lived collection can keep that reference reachable.
6. No. A static method has no implicit Outer instance, but the anonymous subclass/initializer still exists.
7. Because the serialized object graph may contain a captured outer reference or non-serializable fields.
8. The anonymous collection object; `Outer.this` refers to the enclosing Outer when applicable.
9. No; List.of returns an unmodifiable list, and add throws `UnsupportedOperationException`.
10. `new ArrayList<>(List.of("X","Y"))`.
11. Set.of throws `IllegalArgumentException`; HashSet keeps A only once, and the second `add` returns false.
12. Map.of rejects duplicate keys with `IllegalArgumentException`; a subsequent HashMap.put overwrites the value.
13. Map.of does not guarantee iteration order in its contract.
14. `LinkedHashMap` iterates in insertion order by default.
15. A list with the same contents may not be equal because the anonymous runtime subclass differs from the exact class.
16. No; it depends on the actual collection and synchronization.
17. No; the map only holds a reference to the mutable list.
18. No; external side effects can still persist.
19. No; n is not effectively final due to the increment.
20. Yes; there is no anonymous class capturing n here.
21. A constructor/builder/factory with explicit validation and typed invariants.
22. No. It snapshots the list structure but does not automatically clone mutable elements.
23. Compiler-generated names are not a stable business contract.
24. Check **the required data and order**, as well as **mutability/null/duplicate behavior**; add serialization/runtime-type tests if the system relies on them.

## 42. Quick Comparison Table: Before and After Refactoring

| Before: double-brace | After: Java 17 | Benefits / Changes to Remember |
| --- | --- | --- |
| `new ArrayList<String>() {{add("A");add("B");}}` | `new ArrayList<>(List.of("A","B"))` | Preserves mutability and List ordering; no subclass |
| `new ArrayList<String>() {{add("A");}}` | `List.of("A")` | Becomes an unmodifiable list, not equivalent for mutation |
| `new HashSet<String>() {{add("A");add("B");}}` | `Set.of("A","B")` | Unmodifiable; rejects duplicates/null |
| `new HashMap<String,Integer>() {{put("a",1);put("b",2);}}` | `Map.of("a",1,"b",2)` | Unmodifiable; iteration order not guaranteed |
| `new HashMap<String,Integer>() {{put("a",1);}}` | `new HashMap<>(Map.of("a",1))` | Keeps a mutable HashMap, no anonymous subclass |
| Multi-step double-brace Map | Named factory with `put` statements | Easy to inspect side effects and validation |
| Double-brace list in domain object | Builder/constructor + defensive copy | Clear invariants and ownership |

**Do not silently change the contract.** If callers need to mutate a List, `List.of` is not a drop-in replacement. If data contains null, `List.of` can throw `NullPointerException`. If a Set/Map has duplicates, the of-factories can throw `IllegalArgumentException`. If iteration order is needed, check the returned collection type before choosing.

## 43. Official Documentation for Java 17

- [JLS 17 §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): `new` syntax and anonymous creation.
- [JLS 17 §15.9.5 — Anonymous Class Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5): why the outer braces create an anonymous subclass.
- [JLS 17 §8.6 — Instance Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.6): meaning of the inner braces.
- [JLS 17 §12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): construction/initialization order.
- [JLS 17 §8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): enclosing-instance behavior.
- [JLS 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): captured final/effectively final rules.
- [Java SE 17 — ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): constructors, List equality, mutability.
- [Java SE 17 — List.of / List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#of(E...)): list factories disallowing structural mutation, null handling.
- [Java SE 17 — Set.of](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#of(E...)): rejects null/duplicates.
- [Java SE 17 — Map.of](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#of()): unmodifiable map factories.
- [Java SE 17 — Map.ofEntries](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#ofEntries(java.util.Map.Entry...)): creating maps from multiple entries.
- [Java SE 17 — Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)): view disallowing mutation.
- [Java SE 17 — LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): iteration order when needed.
- [Java SE 17 — Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html): serialization marker and object graph.
- [Java SE 17 — ObjectOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html): writing the object graph and serialization failures.
- [Java SE 17 — Class.isAnonymousClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isAnonymousClass()): checking anonymous runtime type.

## 44. Summary

**Double braces are not a literal syntax for collections**. They create an **anonymous subclass** and execute an **instance initializer**, thereby carrying unnecessary overhead/risks when the sole purpose is data:

1. The runtime class is no longer strictly `ArrayList.class`/`HashMap.class`, which can affect reflection/frameworks and custom equality.
2. In an instance context, it may retain the **enclosing instance** or captured references longer than expected.
3. Serialization can fail if the object graph contains non-serializable references.
4. The initializer can have side effects or throw an exception right during creation.
5. Final/effectively-final capture rules apply, even if you only want to put a changing value into a list.
6. It **does not** provide immutability or thread safety, nor does it guarantee better performance.
7. The syntax forces readers to understand subclass/initializer mechanics instead of clearly seeing the intent to create a data collection.

**Pragmatic choice:** if the data does not need modification, use `List.of`, `Set.of`, and `Map.of` when their null, duplicate, and order semantics fit. If you need a mutable ArrayList/HashMap, use `new ArrayList<>(...)`/`new HashMap<>(...)` or ordinary `add`/`put` statements. If creating data with multi-step logic or validation, use a **named factory/Builder**. Only use an anonymous subclass when you **genuinely need a subtype with custom behavior**, not just to save a few lines of initialization.
