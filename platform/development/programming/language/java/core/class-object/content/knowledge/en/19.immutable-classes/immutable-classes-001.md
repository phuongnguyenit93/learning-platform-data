# Immutable Objects and the Benefits of Sharing References in Java

## Learning Objectives

After this lesson, you will be able to:

- Define **immutable object**: an object whose observable state does not change after valid construction.
- Distinguish immutability from a `final` variable, a `private` field, a class without setters, a *read-only view*, and a collection snapshot.
- Explain **aliasing**: multiple variables, fields, and threads holding a reference to the same object; understand why sharing a mutable object requires caution while sharing an immutable value object is usually easier to reason about.
- Design a Java 17+ final immutable class/record with constructor validation, private final state, accessors, and methods that create a new instance (*wither*), without exposing mutable representation.
- Recognize the difference between **shallow immutability** and **deep immutability**, array copying, shallow-copy object graphs, mutable elements, and collections with live backing.
- Correctly use `String`, `BigInteger`, `BigDecimal`, `LocalDate`, records, `List.of`, `List.copyOf`, `Collections.unmodifiableList`, and `Arrays.asList`.
- Distinguish between **modifying an object** and **changing a reference value**; understand that creating a new value does not turn the old object into the new value.
- Know the benefits of immutable value keys in `HashMap`/`HashSet`, immutable snapshots in APIs, mutable builders that produce immutable products, and safe shared structures.
- Explain the limitations: immutable objects do not automatically make every system thread-safe, do not replace safe publication, do not close files/sockets, and do not guarantee faster code or that objects are always interned.
- Run standalone Java 17+ programs with `javac`/`java` commands and verify stdout.

## 1. What Is Immutability?

A Java object is **immutable** if the state that clients observe through its public contract **cannot be changed after the constructor/factory completes**. Methods such as `plus`, `withCity`, and `concat` can return a **new value**, but they do not mutate the original object.

Example with `String`:

~~~java
String original = "Java";
String revised = original.concat(" 17");
~~~

`original` remains `"Java"`, and `revised` is `"Java 17"`. This differs from `StringBuilder.append`, which modifies the same builder object.

Immutability is a **contract about object state**, not "a reference variable cannot be reassigned." A non-final variable can sequentially point to multiple immutable objects.

### 1.1. Concepts That Must Not Be Equated

| Concept | Primary Guarantee | Does Not Guarantee by Itself |
| --- | --- | --- |
| `final` reference field | Field cannot be reassigned after valid initialization | The referenced object's state does not change |
| `private` field | Restricts direct access from other code | That a mutable reference cannot be exposed via a getter |
| No setters | No setters in this API | That mutable nested objects/aliases cannot be modified |
| Immutable object | Observable state does not change after construction | No external mutable services or resource lifecycle |
| Unmodifiable view | Caller cannot mutate through the view | That the backing collection is not mutated elsewhere |
| Unmodifiable snapshot | Snapshot structure is stable | That elements do not contain mutable references |
| Record | Components are final fields, with generated methods | Deep copying of arrays/lists/custom objects |
| Defensive copy | Copies at the desired representation level | Deep copying of the entire graph by an automatic rule |

**Key question:** Is there **any valid reference path** that allows external code to change the state that an object exposes after construction?

## 2. Aliasing: One Object Referenced from Multiple Places

With Java references:

~~~java
Address shared = new Address("Ha Noi");
Customer a = new Customer("Lan", shared);
Customer b = new Customer("Minh", shared);
~~~

If both Customers hold the exact reference to `shared`, then both see the **same Address object**. This is **aliasing**.

~~~text
Customer A.address --+
                     |
                     v
                  Address
                     ^
                     |
Customer B.address --+
~~~

If Address is mutable and someone calls `shared.changeCity("Hue")`, both Customers can see Hue. This is valid behavior, but it can cause bugs when each Customer assumes it has its own copy.

### 2.1. Mutable Aliasing Program

Save **`MutableAliasingDemo.java`**:

~~~java
public class MutableAliasingDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = city;
        }

        String city() {
            return city;
        }

        void move(String destination) {
            city = destination;
        }
    }

    static final class Customer {
        private final String name;
        private final Address address;

        Customer(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        String describe() {
            return name + "@" + address.city();
        }
    }

    public static void main(String[] args) {
        Address shared = new Address("Ha Noi");
        Customer lan = new Customer("Lan", shared);
        Customer minh = new Customer("Minh", shared);

        System.out.println("before=" + lan.describe()
                + "," + minh.describe());

        shared.move("Hue");

        System.out.println("after=" + lan.describe()
                + "," + minh.describe());
    }
}
~~~

Run:

~~~bash
javac MutableAliasingDemo.java
java MutableAliasingDemo
~~~

Output:

~~~text
before=Lan@Ha Noi,Minh@Ha Noi
after=Lan@Hue,Minh@Hue
~~~

Both `Customer.address` fields are `final`, yet they only fix the **reference** and do not freeze the Address object. When the object is modified through `shared`, both Customers read the same new state.

### 2.2. What If Address Is Immutable?

Without `changeCity` and without exposing any mutable representation, two Customers can share **the same reference to Address** without worrying about a third party modifying that Address itself.

When a different address is wanted, create a **new** Address and then create/replace the reference at the appropriate owner level. Anyone still holding a reference to the old Address has the old state.

## 3. Immutable Records and Creating New Values

With Java 17:

~~~java
record Address(String city) {
}
~~~

This record has a final component field, and the component is an immutable `String`. Without introducing other mutable state/behavior, Address has stable value state.

A record **does not imply** that every component is immutable: `record Values(int[] data)` keeps the array reference final, yet the array itself remains mutable.

### 3.1. Program Demonstrating Record Sharing and Version Replacement

Save **`ImmutableSharingDemo.java`**:

~~~java
import java.util.Objects;

public class ImmutableSharingDemo {
    record Address(String city) {
        Address {
            Objects.requireNonNull(city, "city");
            if (city.isBlank()) {
                throw new IllegalArgumentException("city required");
            }
        }

        Address withCity(String nextCity) {
            return new Address(nextCity);
        }
    }

    static final class Customer {
        private final String name;
        private final Address address;

        Customer(String name, Address address) {
            this.name = Objects.requireNonNull(name, "name");
            this.address = Objects.requireNonNull(address, "address");
        }

        String describe() {
            return name + "@" + address.city();
        }

        Customer withAddress(Address next) {
            return new Customer(name, next);
        }
    }

    public static void main(String[] args) {
        Address shared = new Address("Ha Noi");
        Customer lan = new Customer("Lan", shared);
        Customer minh = new Customer("Minh", shared);

        System.out.println("same address=" + (shared
                == new Address("Ha Noi")));
        System.out.println("original=" + lan.describe()
                + "," + minh.describe());

        Customer movedLan = lan.withAddress(
                shared.withCity("Hue"));

        System.out.println("old=" + lan.describe());
        System.out.println("new=" + movedLan.describe());
        System.out.println("other=" + minh.describe());
        System.out.println("shared=" + shared.city());
    }
}
~~~

Commands:

~~~bash
javac ImmutableSharingDemo.java
java ImmutableSharingDemo
~~~

Output:

~~~text
same address=false
original=Lan@Ha Noi,Minh@Ha Noi
old=Lan@Ha Noi
new=Lan@Hue
other=Minh@Ha Noi
shared=Ha Noi
~~~

**Explanation:** `==` on the first line compares the identity of two separately created record instances, so it is false. Both Customers initially use `shared` together without needing to copy Address. `withCity` and `withAddress` create new values; the old lan and minh still use the Ha Noi Address.

This gives the code natural **snapshot semantics**: a value does not change on its own due to operations elsewhere.

## 4. Immutability Does Not Mean `final`

Distinguish:

~~~java
final StringBuilder builder = new StringBuilder("A");
builder.append("B"); // Valid: same reference, state changes.
// builder = new StringBuilder("C"); // Invalid: reassigning final.
~~~

Meanwhile:

~~~java
String text = "A";
text = text.concat("B"); // Change the reference to the resulting String value.
~~~

The variable `text` is not final, yet String objects remain immutable.

### 4.1. Comparison Program

Save **`StringVsBuilderDemo.java`**:

~~~java
public class StringVsBuilderDemo {
    public static void main(String[] args) {
        String first = "Java";
        String alias = first;

        first = first.concat(" 17");

        System.out.println("first=" + first);
        System.out.println("alias=" + alias);
        System.out.println("same reference=" + (first == alias));

        StringBuilder builder = new StringBuilder("Java");
        StringBuilder builderAlias = builder;
        builder.append(" 17");

        System.out.println("builder=" + builder);
        System.out.println("builder alias=" + builderAlias);
        System.out.println("same builder=" + (builder == builderAlias));
    }
}
~~~

Run:

~~~bash
javac StringVsBuilderDemo.java
java StringVsBuilderDemo
~~~

Output:

~~~text
first=Java 17
alias=Java
same reference=false
builder=Java 17
builder alias=Java 17
same builder=true
~~~

`concat` does not modify the original String; `append` modifies the StringBuilder that all aliases see. Do not infer that String operations **always** allocate a new instance if the result does not change; the important contract is that the original state is not mutated.

## 5. Traditional Immutable Class Design

An immutable class typically has:

1. State held in `private` fields.
2. Fields assigned once (`final`) in a valid constructor.
3. A constructor that validates invariants and does not let `this` escape before completion.
4. No API that mutates state.
5. If holding a reference to a mutable object, appropriate copying of input/output.
6. A `final class` or a strategy to control subclassing to protect the contract.
7. Proper `equals`/`hashCode` if value equality is desired.

~~~java
public final class Category {
    private final String code;
    private final String displayName;

    public Category(String code, String displayName) {
        this.code = java.util.Objects.requireNonNull(code, "code");
        this.displayName = java.util.Objects.requireNonNull(
                displayName, "displayName");
        if (code.isBlank()) {
            throw new IllegalArgumentException("blank code");
        }
    }

    public String code() {
        return code;
    }

    public String displayName() {
        return displayName;
    }
}
~~~

This is a complete Java 17 class (saved in `Category.java`). Its `String` components are immutable, there are no setters, and the final class prevents subclasses from breaking immutability through overrides/extensions.

### 5.1. Immutability Does Not Always Require `final class`

It is possible to design an immutable hierarchy using strict constructors/contracts, but it is harder to guarantee. For simple value objects, `final` is an easy-to-understand option that makes immutability easy to preserve.

### 5.2. Immutability Does Not Automatically Define Equality

The class above does not override `equals`; according to Object, two separate Category instances can fail to be equal even when their fields are identical. If it is a value object, you should override both `equals`/`hashCode` consistently or choose an appropriate record.

### 5.3. Do Not Publish `this` from a Constructor

Registering `this` in a static registry, starting a new thread that holds `this`, or invoking an external callback inside a constructor can cause other code to observe the object **before initialization completes**. This also affects the guarantees of final field semantics.

Do not treat `final` as a license to publish a half-constructed object.

## 6. Immutable Value Objects with Business Logic

Save **`ImmutableMoneyDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class ImmutableMoneyDemo {
    record Money(long cents, String currency) {
        Money {
            Objects.requireNonNull(currency, "currency");
            currency = currency.toUpperCase(Locale.ROOT);
            if (currency.isBlank()) {
                throw new IllegalArgumentException("empty currency");
            }
        }

        Money plus(Money other) {
            Objects.requireNonNull(other, "other");
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException("currency mismatch");
            }
            return new Money(Math.addExact(cents, other.cents), currency);
        }

        Money withCents(long updated) {
            return new Money(updated, currency);
        }
    }

    public static void main(String[] args) {
        Money base = new Money(1500, "usd");
        Money fee = new Money(250, "USD");
        Money total = base.plus(fee);

        System.out.println("base=" + base);
        System.out.println("fee=" + fee);
        System.out.println("total=" + total);

        Money revised = total.withCents(2000);
        System.out.println("old total=" + total.cents());
        System.out.println("new total=" + revised.cents());
    }
}
~~~

Run:

~~~bash
javac ImmutableMoneyDemo.java
java ImmutableMoneyDemo
~~~

Output:

~~~text
base=Money[cents=1500, currency=USD]
fee=Money[cents=250, currency=USD]
total=Money[cents=1750, currency=USD]
old total=1750
new total=2000
~~~

Both `plus` and `withCents` return a new instance without modifying the original Money. `Math.addExact` catches integer overflow. Uppercase currency normalization is an **illustrative rule** and is not sufficient for real-world currency validation (ISO codes, minor units, separate scale/rounding).

Immutability helps reduce the risk of "the total suddenly changing" through an alias, but it does not replace transaction/concurrency control if an account or order has mutable state at another layer.

## 7. Shallow and Deep Immutability

An object can have `private final List<Line> lines` and still **not be immutable** if:

- `lines` is a mutable list passed as the raw reference.
- A getter returns the exact list so a caller can `clear()` it.
- The list is already unmodifiable, but a `Line` element has a setter and another party still holds a reference to it.
- A nested array inside Line remains mutable and is exposed.

### 7.1. Shallow Aliasing Diagram

~~~text
Immutable-looking Order
    final lines -------------> list structure (unmodifiable)
                                   |
                                   v
                              Mutable Line
                                   ^
                                   |
                            external reference
~~~

The list structure does not change, yet `Line.price` can change. The `total()` returned by Order can change over time, meaning Order's observable state is **not truly immutable**.

### 7.2. Single-Level Copying Does Not Automatically Deep Copy

`new ArrayList<>(source)` creates a new list, but retains references to the old elements.

`array.clone()` creates a new array object, but if the array holds references to mutable objects, the elements can still be shared. For `int[]`, clone copies primitive values, which is usually enough to protect the array's contents.

"Deep copy" is a decision based on the **object graph/domain**: mutable subobjects need to be copied to the extent of eliminating dangerous aliases, without necessarily copying immutable Strings/records.

With A↔B cycles and shared subobjects, arbitrary deep copying can distort the identity graph. There is no single Java operator that performs a deep copy suitable for every case.

## 8. Safe Immutable Sharing When a Field Points to an Array

An `int[]` array is mutable. If an object wants to expose an **immutable value for multiple references to read**, `private final int[]` alone is not enough: `final` fixes the field reference, without freezing the elements.

For example, a `Digits` class can hold a snapshot:

~~~java
final class Digits {
    private final int[] values;

    Digits(int[] input) {
        if (input == null) {
            throw new IllegalArgumentException("input");
        }
        this.values = input.clone();
    }

    int at(int index) {
        return values[index];
    }

    int[] copyValues() {
        return values.clone();
    }
}
~~~

This is a **class declaration**, without `main`. Cloning the input prevents changes through the `input` reference; cloning the output prevents the caller from modifying the internal array through the returned value. To observe input → modify alias → result and verify for yourself, you can write a `main` that stores `Digits d = new Digits(new int[]{1,2});` and then checks that `d.at(0)` does not change after modifying the source array or the returned clone.

**Scope of this lesson:** the key point is that *aliasing + immutable objects make it easy to share the same value*. The lesson **"Defensive Copying of Mutable Inputs and Outputs"** provides full guidance on copying mutable types; the lesson **"Testing Immutability When a Class Contains Arrays or Collections"** provides a test harness to guard against leaks in both directions. For `MutableElement[]` or nested arrays, an outermost `clone()` is only a **shallow copy**.

## 9. Records Do Not Automatically Provide Deep Immutability

`record Sample(int[] values)` has a final reference field, but does not automatically clone `int[]` when receiving or returning it; the generated `equals` uses array identity semantics for array components rather than comparing contents automatically.

### 9.1. Example of a Record with a Mutable Array

Save **`ShallowRecordDemo.java`**:

~~~java
public class ShallowRecordDemo {
    record Sample(int[] values) {
    }

    public static void main(String[] args) {
        int[] source = {1, 2};
        Sample a = new Sample(source);
        Sample b = new Sample(new int[] {1, 2});

        System.out.println("record equal=" + a.equals(b));
        System.out.println("before=" + a.values()[0]);

        source[0] = 9;
        System.out.println("input changed=" + a.values()[0]);

        a.values()[1] = 8;
        System.out.println("getter changed=" + source[1]);
    }
}
~~~

Run:

~~~bash
javac ShallowRecordDemo.java
java ShallowRecordDemo
~~~

Output:

~~~text
record equal=false
before=1
input changed=9
getter changed=8
~~~

To use a record with an array as a value object, you need a compact constructor that copies the input, a defensive-copying accessor, and potentially overrides of `equals`/`hashCode` to compare array contents if the domain requires it.

**This does not mean all records are mutable**: a record containing only primitives/String/LocalDate or other immutable components is usually an easy-to-use immutable value object.

## 10. List Snapshots: `List.copyOf` and Its Limitations

`List.copyOf(source)` returns a **structurally unmodifiable snapshot**. If elements are added to or removed from source afterward, the snapshot's structure does not change. It does not deep-copy mutable elements.

### 10.1. Record with a String List

Save **`RecordListSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RecordListSnapshotDemo {
    record Group(String name, List<String> members) {
        Group {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
            members = List.copyOf(members);
        }
    }

    public static void main(String[] args) {
        List<String> draft = new ArrayList<>(List.of("Lan"));
        Group group = new Group("A", draft);

        draft.add("Minh");

        System.out.println("draft=" + draft);
        System.out.println("group=" + group.members());

        try {
            group.members().add("Hoa");
        } catch (UnsupportedOperationException expected) {
            System.out.println("group cannot add");
        }
    }
}
~~~

Compile/run:

~~~bash
javac RecordListSnapshotDemo.java
java RecordListSnapshotDemo
~~~

Output:

~~~text
draft=[Lan, Minh]
group=[Lan]
group cannot add
~~~

The compact constructor `members = List.copyOf(members)` reassigns the parameter so that the record component stores the snapshot. The `String` elements are immutable; therefore, both the structure and the content of each text element remain stable.

### 10.2. `List.copyOf` Does Not Guarantee Allocating a New List

The API allows reusing a suitable unmodifiable list. You should not use `list1 != List.copyOf(list1)` as a contract test. Instead, check **values, unmodifiability, and snapshot semantics**.

`List.copyOf` also does not accept null elements; if the domain requires null as a marker, you must choose another representation rather than assuming the Collections API will keep null.

## 11. Live Unmodifiable Views Differ from Snapshots

~~~java
List<String> view =
        java.util.Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);
~~~

If source is a mutable list, `view` can still reflect changes in the backing source. Meanwhile, snapshot does not change its structure when source changes after the time of copying.

### 11.1. Demo Showing the Difference

Save **`ViewVsSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        source.add("B");

        System.out.println("source=" + source);
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        try {
            view.clear();
        } catch (UnsupportedOperationException expected) {
            System.out.println("view cannot clear");
        }

        try {
            snapshot.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot cannot add");
        }
    }
}
~~~

Run:

~~~bash
javac ViewVsSnapshotDemo.java
java ViewVsSnapshotDemo
~~~

Output:

~~~text
source=[A, B]
view=[A, B]
snapshot=[A]
view cannot clear
snapshot cannot add
~~~

Preventing modification through **one reference** is not the same as preventing mutation through **every alias**. If an API exposes an immutable snapshot, use a snapshot rather than just an unmodifiable live view.

## 12. Lists Containing Mutable Elements Still Have Loopholes

### 12.1. Counterexample Program

Save **`MutableElementDemo.java`**:

~~~java
import java.util.List;

public class MutableElementDemo {
    static final class Item {
        private String name;

        Item(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        void rename(String name) {
            this.name = name;
        }
    }

    static final class Catalog {
        private final List<Item> items;

        Catalog(List<Item> source) {
            items = List.copyOf(source);
        }

        String firstName() {
            return items.get(0).name();
        }
    }

    public static void main(String[] args) {
        Item item = new Item("old");
        Catalog catalog = new Catalog(List.of(item));

        System.out.println("before=" + catalog.firstName());
        item.rename("new");
        System.out.println("after=" + catalog.firstName());
    }
}
~~~

Run:

~~~bash
javac MutableElementDemo.java
java MutableElementDemo
~~~

Output:

~~~text
before=old
after=new
~~~

`Catalog.items` is final and the list is unmodifiable, yet the mutable Item object is still shared. Therefore, `Catalog` is not truly immutable with respect to the result of `firstName()`.

Solution: use an immutable item record/value object or copy the mutable Item into an immutable snapshot representation in the constructor without exposing mutable elements.

## 13. `Arrays.asList` Is a Fixed-Size Backing View, Not Immutable

`Arrays.asList(array)` returns a fixed-size list **backed by the array**. `add/remove` are invalid, whereas `set` can replace an element and reflect that change in the source array.

### 13.1. Example

Save **`ArrayBackedListDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;

public class ArrayBackedListDemo {
    public static void main(String[] args) {
        String[] array = {"A", "B"};
        List<String> view = Arrays.asList(array);
        List<String> snapshot = List.copyOf(view);

        array[0] = "X";
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        view.set(1, "Y");
        System.out.println("array=" + Arrays.toString(array));

        try {
            view.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("cannot add");
        }
    }
}
~~~

Run:

~~~bash
javac ArrayBackedListDemo.java
java ArrayBackedListDemo
~~~

Output:

~~~text
view=[X, B]
snapshot=[A, B]
array=[X, Y]
cannot add
~~~

**Do not use fixed-size as a synonym for immutable.** You must distinguish between the ability to change the **number of elements** and the ability to change **element values**.

## 14. Immutable Aggregates with Multiple Values

An `Order` that needs multiple `OrderLine` instances can hold an unmodifiable snapshot of **immutable line values**, and update methods return a new Order object.

### 14.1. One-to-Many Program

Save **`ImmutableOrderDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ImmutableOrderDemo {
    record Line(String sku, int quantity, long price) {
        Line {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank() || quantity <= 0 || price < 0) {
                throw new IllegalArgumentException("invalid line");
            }
        }

        long amount() {
            return Math.multiplyExact((long) quantity, price);
        }
    }

    static final class Order {
        private final String id;
        private final List<Line> lines;

        Order(String id, List<Line> source) {
            this.id = Objects.requireNonNull(id, "id");
            lines = List.copyOf(source);
        }

        int lineCount() {
            return lines.size();
        }

        long total() {
            long total = 0;
            for (Line line : lines) {
                total = Math.addExact(total, line.amount());
            }
            return total;
        }

        Order add(Line line) {
            List<Line> copy = new ArrayList<>(lines);
            copy.add(Objects.requireNonNull(line, "line"));
            return new Order(id, copy);
        }
    }

    public static void main(String[] args) {
        List<Line> draft = new ArrayList<>();
        draft.add(new Line("PEN", 2, 10));

        Order first = new Order("O-1", draft);
        draft.clear();

        Order second = first.add(new Line("BOOK", 1, 50));

        System.out.println("draft=" + draft.size());
        System.out.println("first lines=" + first.lineCount());
        System.out.println("first total=" + first.total());
        System.out.println("second lines=" + second.lineCount());
        System.out.println("second total=" + second.total());
    }
}
~~~

Run:

~~~bash
javac ImmutableOrderDemo.java
java ImmutableOrderDemo
~~~

Output:

~~~text
draft=0
first lines=1
first total=20
second lines=2
second total=70
~~~

- `Line` is an immutable value (String/primitives).
- `Order` captures the list structure with `List.copyOf`.
- A caller modifying `draft` does not change Order.
- `add` creates a new Order, leaving the old object intact.
- References to immutable lines can be **shared** across versions without needing a deep copy.
- This is a value snapshot model; a real-world Order domain entity has its own lifecycle/transaction semantics.

## 15. Mutable Builder Producing an Immutable Product

A builder can be mutable to make adding/configuring data convenient. The product from `build()` remains immutable as long as the builder does not expose aliases to internal mutable state.

### 15.1. Reusable Builder Demo

Save **`BuilderSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class BuilderSnapshotDemo {
    record Settings(List<String> features) {
        Settings {
            features = List.copyOf(features);
        }
    }

    static final class Builder {
        private final List<String> features = new ArrayList<>();

        Builder add(String value) {
            features.add(value);
            return this;
        }

        Settings build() {
            return new Settings(features);
        }
    }

    public static void main(String[] args) {
        Builder builder = new Builder().add("search");
        Settings first = builder.build();

        builder.add("report");
        Settings second = builder.build();

        System.out.println("first=" + first.features());
        System.out.println("second=" + second.features());
    }
}
~~~

Run:

~~~bash
javac BuilderSnapshotDemo.java
java BuilderSnapshotDemo
~~~

Output:

~~~text
first=[search]
second=[search, report]
~~~

The builder continues to mutate, yet each Settings version is an isolated structural snapshot. If the elements are mutable, the builder must have an appropriate copy/ownership policy; here the elements are immutable Strings.

## 16. Immutable Value Keys and `HashMap`

`HashMap`/`HashSet` require consistent properties of `equals`/`hashCode`. If a key changes state involved in hashing/equality after being placed into a hash table, lookups can fail because the entry's position was computed using the old hash.

Immutable keys have stable state and easily adhere to the contract. However, **immutability does not guarantee unique hashes**; collisions are still valid.

### 16.1. Unchanged Key Demo

Save **`ImmutableKeyDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class ImmutableKeyDemo {
    record Key(String sku, int version) {
        Key nextVersion() {
            return new Key(sku, version + 1);
        }
    }

    public static void main(String[] args) {
        Map<Key, String> map = new HashMap<>();
        Key first = new Key("PEN", 1);
        map.put(first, "blue");

        Key another = new Key("PEN", 1);
        Key updated = first.nextVersion();

        System.out.println("same value=" + first.equals(another));
        System.out.println("lookup=" + map.get(another));
        System.out.println("first version=" + first.version());
        System.out.println("updated version=" + updated.version());
        System.out.println("updated lookup=" + map.get(updated));
        System.out.println("old lookup=" + map.get(first));
    }
}
~~~

Run:

~~~bash
javac ImmutableKeyDemo.java
java ImmutableKeyDemo
~~~

Output:

~~~text
same value=true
lookup=blue
first version=1
updated version=2
updated lookup=null
old lookup=blue
~~~

The version 1 key placed into the map does not mutate at all. `nextVersion` returns a new key. With an immutable key, callers can share the reference or create an equal key for reliable lookups.

## 17. Multiple Threads Reading the Same Immutable Snapshot

If an object graph is **truly immutable** and properly initialized/published, there is no race between readers that **only read** that state. This often eliminates the need for a separate lock solely to protect the data inside the snapshot.

However:

- **Immutability** does not replace **safe publication**, the Java Memory Model, or synchronization of updated holder variables.
- `final` field semantics provide special guarantees for correctly constructed objects, provided that `this` is not allowed to escape during the constructor.
- A mutable service/buffer/connection invoked by the object from its methods still has its own concurrency contract.
- A mutable `currentSnapshot` holder updated across threads requires appropriate `volatile`/synchronization/atomic publication.
- If a two-step business operation requires atomicity, immutable input does not automatically turn the entire operation into an atomic transaction.

### 17.1. Demo of Reading from Two Tasks with Deterministic Output

Save **`ImmutableConcurrentReadDemo.java`**:

~~~java
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ImmutableConcurrentReadDemo {
    record Snapshot(List<Integer> numbers) {
        Snapshot {
            numbers = List.copyOf(numbers);
        }

        int sum() {
            int total = 0;
            for (int value : numbers) {
                total = Math.addExact(total, value);
            }
            return total;
        }
    }

    public static void main(String[] args) throws Exception {
        Snapshot shared = new Snapshot(List.of(1, 2, 3));

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> a = executor.submit(shared::sum);
            Future<Integer> b = executor.submit(shared::sum);

            System.out.println("first=" + a.get());
            System.out.println("second=" + b.get());
            System.out.println("main=" + shared.sum());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Run:

~~~bash
javac ImmutableConcurrentReadDemo.java
java ImmutableConcurrentReadDemo
~~~

Output:

~~~text
first=6
second=6
main=6
~~~

`Snapshot` only holds an unmodifiable list of immutable Integer values. Both tasks are read-only. `Future.get()` ensures that main waits for the results before printing in a deterministic order. The executor is shut down in finally.

**There is no need to guess thread execution order** to deduce stdout; they do not print directly, and main prints in the written order.

## 18. Safe Publication and Version-Swapped State

An application may need to **swap the reference to an immutable snapshot**:

~~~java
private volatile Snapshot current;
~~~

The writer builds a new Snapshot and assigns `current = next`. The reader reads `Snapshot snapshot = current` once and then reads multiple fields from the **same snapshot**, avoiding a half-new, half-old state from reading the holder multiple times in sequence.

However, this is only an illustrative pattern; it also requires:

- Defining Snapshot to be constructed and validated before publishing.
- Using `volatile`/locks/atomic references properly depending on requirements.
- Handling lost updates if multiple writers use read-modify-write.
- Preventing mutable components from being shared through aliases.
- Distinguishing an immutable snapshot from **eventual freshness**: a reader may have already obtained a valid older version while the writer publishes a new version.

Immutable objects help keep **each version** consistent; they do not guarantee that the system always reads the latest version without an appropriate happens-before relationship.

## 19. Built-in Java Types That Support Immutability

| Type/API | Key Point to Remember |
| --- | --- |
| `String` | Immutable text; `replace` and `concat` return results without modifying the original |
| `BigInteger` | Immutable large integers |
| `BigDecimal` | Immutable decimal numbers; `equals` distinguishes scale |
| `LocalDate`, `Instant` | Immutable value types from `java.time` |
| `UUID` | Immutable identifier value |
| Primitive wrappers | Immutable values, but `==` between references does not replace content equality |
| Java records | Final component fields, do not deep-copy mutable arrays/lists |
| `List.of`/`Map.of`/`Set.of` | Unmodifiable structures; mutable elements/values can still exist |
| `List.copyOf`/`Map.copyOf` | Structurally unmodifiable snapshots; do not deep-copy values |
| `Collections.unmodifiableList` | Unmodifiable *view*, the backing list can change |
| `Arrays.asList` | Fixed-size list backed by an array, `set` is valid |

A class documented as immutable in an API is a good candidate for reference sharing; however, check **how the data is wrapped**. A `List<Date>` containing mutable Date objects does not become deeply immutable merely because of `List.copyOf`.

## 20. Practical Benefits

### 20.1. Reducing Unexpected Mutation

When calling `service.process(command)` with an immutable command object, the service cannot modify the command object itself through a valid API; the caller knows the input still retains its old value after the call. This simplifies debugging and testing.

### 20.2. Snapshots for Logs, Events, Audits, and Caches

An immutable event DTO can be passed to multiple consumers, each reading the exact emitted payload value. If the data is an implicitly shared mutable array/list, logs and consumers may see contents change after publication—violating the "snapshot" expectation.

### 20.3. Reducing the Need for Defensive Copying

When a service receives an immutable `Address` or `Money`, it usually does not need to clone the object just to protect against caller modifications. When using a mutable DTO, the service might have to copy it or maintain a lock/ownership contract.

### 20.4. Easier Reasoning in Multithreading

Multiple readers do not simultaneously write to immutable state. However, external mutable caches, observers, holder references, and transaction state still require proper concurrency design.

### 20.5. Easier Caching, Hashing, and Comparison

An immutable value object has stable `equals`/`hashCode` when implemented properly. A mutable key can break lookup ability after its hashed state changes.

### 20.6. Trade-offs: Allocation and Copy Costs

Immutability does not automatically optimize every workload. Creating a new object on frequent updates can increase allocations, O(n) list copies, and GC pressure. **Persistent data structures** can use structural sharing efficiently; do not assume Java's `List.copyOf` is itself a persistent list with O(log n) updates.

Measure with profiling if performance is a requirement, and avoid claiming that immutable is always faster or slower than mutable.

## 21. Choosing Immutable or Mutable Based on the Domain

**Immutable is suitable** for:

- Value objects such as Money, Coordinates, and DateRange.
- Command/event/request snapshots that do not need to change after creation.
- Cache keys, identifiers, and map/set elements with stable equality.
- Shared configuration versions.
- Data shared widely across modules/threads.

**Mutable may be suitable** for:

- Builders within local scope.
- Buffers, streams, and active connections with a lifecycle.
- Domain entities that need to change state through operations with validation/transactions.
- Algorithms that continuously update very large structures under performance constraints.

A balanced strategy is **"mutable while building, immutable when sharing"**: use a local `ArrayList`/`StringBuilder` to build the data, then emit a String/immutable snapshot to consumers.

Do not try to turn a file/socket/DB connection into an "immutable resource" just because the field holding the handle is final. Resource lifecycles still require `AutoCloseable`/`try-with-resources` and deterministic cleanup.

## 22. Common Mistakes

| Mistake | Correct Understanding |
| --- | --- |
| "Final field ⇒ immutable object." | Final locks field assignment, not a mutable referent. |
| "Private fields ⇒ cannot be mutated." | Getters/constructors can expose mutable aliases. |
| "No setters ⇒ immutable." | There may still be nested mutable objects or other methods that modify state indirectly. |
| "Record ⇒ deep immutable." | Records are final at the component level, but do not automatically copy arrays/lists. |
| "List.copyOf ⇒ immutable elements." | Unmodifiable structure, yet references to elements remain shared. |
| "UnmodifiableList ⇒ snapshot." | Often a live view over a backing list. |
| "Arrays.asList cannot add ⇒ immutable." | Fixed-size list, yet `set` is allowed. |
| "Clone array ⇒ deep-copy every element." | Object array clone copies references, not each object. |
| "An immutable object must be copied every time it is passed." | References can be shared without worrying about mutation of that object itself. |
| "Two immutable objects equal ⇒ `==` true." | Value equality differs from object identity. |
| "Immutable objects create no GC pressure." | Multiple versions/allocations still have a cost. |
| "Final fields solve all data races." | External state/holder updates/publication have their own rules. |
| "An immutable snapshot is always the latest." | A snapshot is the version at the time it was created/retrieved. |
| "If a HashMap key changes, the map rehashes automatically." | No; use an immutable key or update the entry in a controlled manner. |
| "Immutability makes files close automatically." | Resource lifecycle is independent of Java object state. |
| "The builder must also be immutable." | A builder can be mutable; the product must isolate mutable aliases. |
| "All objects must be immutable." | Depending on domain/performance/lifecycle, keep mutation within a clear scope. |
| "Copying from a mutable object is always cheap." | Copying a large nested graph can be expensive; do not assume otherwise. |
| "Immutable == thread-safe for every system." | It only addresses the shared state of the immutable graph; communication and coordination are still needed. |

## 23. Checklist for Designing/Reviewing an Immutable Value Class

1. Which fields constitute the **observable state**?
2. Are all fields fully initialized in the constructor?
3. Are validations performed on the exact data that will be stored?
4. Are there mutable array/list/Date/StringBuilder/custom references?
5. Are incoming mutable values copied before storing?
6. Are outgoing values copied or returned as immutable snapshots?
7. Are elements inside collections mutable?
8. If subclassing is allowed, can a subclass break immutability?
9. Are there setters/mutating methods or methods calling an external mutable collaborator that cause observable state to change?
10. Is `this` allowed to escape during the constructor?
11. With multiple threads, is the object published according to the proper contract?
12. Does a version-swapping holder reference have the necessary synchronization/volatile/atomic semantics?
13. Are `equals`/`hashCode` stable and appropriate for the domain?
14. When used as a HashMap key, is hash-relevant state kept immutable?
15. Are aliasing, null, arrays, collections, and builder reuse handled in tests?
16. Are there resource lifecycles outside memory?
17. Are allocation/copy costs measured when they matter?

## 24. Exercises and Answers

**Question 1.** Does `final List<String> values` automatically make the list immutable?  
**Answer:** No. It only prevents reassigning the reference field/variable.

**Question 2.** Is it okay for two Customers to share an immutable Address?  
**Answer:** It can be safe regarding mutation of the Address's state because that object does not change.

**Question 3.** Given `String a="A"; String b=a; a=a+"B";`, what is b?  
**Answer:** `"A"`, because variable a is assigned the resulting String value, while the original String is not mutated.

**Question 4.** Two variables point to the same StringBuilder; if one calls append, what does the other see?  
**Answer:** The new state of the same builder object.

**Question 5.** Is `record Data(int[] values)` deeply immutable?  
**Answer:** Not yet. The array is mutable and shared through the component reference.

**Question 6.** If the constructor clones int[] but the getter returns the raw internal int[], is it safe?  
**Answer:** No. The getter still exposes the mutable representation.

**Question 7.** Why must copying be done at both the input and output boundaries?  
**Answer:** To prevent callers from modifying state through a reference retained from the constructor or received from the getter.

**Question 8.** Does cloning `Address[]` copy each Address object?  
**Answer:** No. It only clones the outer array; element references remain shared.

**Question 9.** Is `List.copyOf` with mutable elements deeply immutable?  
**Answer:** No. It only protects the structure of the list snapshot.

**Question 10.** Will `Collections.unmodifiableList(source)` see x after `source.add(x)`?  
**Answer:** Potentially yes, because it is typically a live view backed by source.

**Question 11.** Does `List.copyOf(source)` automatically add x after `source.add(x)`?  
**Answer:** No, the snapshot structure remains stable.

**Question 12.** Does `Arrays.asList(array)` allow calling `set`?  
**Answer:** Yes, it is backed by the array.

**Question 13.** When a different Money value is needed, should you mutate the old Money record?  
**Answer:** No; return a new Money object with the new values.

**Question 14.** How does an immutable key help HashMap?  
**Answer:** State involved in hashing/equality does not change, making lookups reliable.

**Question 15.** Are two immutable keys with different values guaranteed to have different hashes?  
**Answer:** No; hash collisions can still occur.

**Question 16.** Can an immutable snapshot be read by two threads without locking to protect its internal state?  
**Answer:** Yes, if the graph is truly immutable and properly initialized/published; external state still requires coordination.

**Question 17.** Is `private final List<MutableItem>` sufficiently deeply immutable?  
**Answer:** No. MutableItem objects can be modified through aliases.

**Question 18.** Can a mutable builder return multiple immutable Settings snapshots?  
**Answer:** Yes, if build isolates mutable data structures and the elements are suitable.

**Question 19.** Does immutability guarantee that objects are never garbage-collected?  
**Answer:** No. Garbage collection considers reachability, independent of whether an object is immutable.

**Question 20.** Can an immutable object be referenced by a non-final variable?  
**Answer:** Yes. Reassigning the variable does not mutate the old object.

**Question 21.** Does `final` field semantics guarantee that all multithreaded code is automatically thread-safe?  
**Answer:** No. There is the correctly constructed requirement as well as other visibility/coordination limits.

**Question 22.** When should mutable state be kept?  
**Answer:** When the domain or performance requires it, while limiting ownership and emitting an immutable snapshot when sharing.

**Question 23.** How can immutable objects help tests?  
**Answer:** Input values do not change on their own due to aliases, making assertions and before/after step states predictable.

**Question 24.** Does immutable state replace database transactions?  
**Answer:** No. Transactions/atomicity are a separate concern.

**Question 25.** If a getter returns a `Map.copyOf` snapshot whose values are mutable objects, can callers observe changes?  
**Answer:** Potentially yes through the values; an unmodifiable map structure does not make the value objects immutable.

**Question 26.** When creating a new order by copying a list of line references, is it necessary to deep-copy immutable line records?  
**Answer:** Usually no; immutable elements can be shared safely.

**Question 27.** When an "immutable" class uses an unsynchronized lazy mutable cache, does it require attention?  
**Answer:** Yes. The cache is internal mutable state, so you must ensure it does not alter semantics or violate thread safety and visibility.

**Question 28.** Why is `this` escaping in a constructor a risk?  
**Answer:** Other code can observe an incompletely initialized object, affecting invariants and final-field visibility guarantees.

**Question 29.** Must all immutable operations return a new object with a different identity?  
**Answer:** No. An API can reuse an instance when the result equals the old one; the key requirement is not mutating the original.

**Question 30.** State a simple design rule when data needs to be shared widely.  
**Answer:** Use a genuine immutable value/snapshot, validate in the constructor, defensively copy mutable boundaries, and publish references safely.

## 25. References

- Java Language Specification Java SE 17, [`4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): final variables.
- Java Language Specification, [`8.3.1.2 — final Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.1.2): final fields.
- Java Language Specification, [`17.5 — final Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): memory visibility of correctly constructed objects.
- Java Language Specification, [`8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record components/constructor semantics.
- Java Platform API, [`String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): immutable text.
- Java Platform API, [`List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot.
- Java Platform API, [`Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): view semantics.
- Java Platform API, [`Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)): fixed-size backed list.
- Java Platform API, [`HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): hashing contract.
- Java Platform API, [`BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): immutable decimal.
- Java Platform API, [`LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): immutable date value.
- Java Platform API, [`ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): concurrent task execution.

## Summary

An **immutable object** has observable state that does not change after construction. Because of this, multiple places can **share the same reference** without worrying about one place mutating that object itself through an alias. Benefits include avoiding bugs caused by shared mutable state, reducing unnecessary defensive copies, ease of use as value keys/snapshots, easier testing, and sharing among multiple readers.

**There is no single Java keyword that makes an entire object graph immutable.** `final` fixes a field reference, `private` restricts access, `record` has final component fields, and `List.copyOf` protects the collection structure; however, mutable arrays, elements, and references can still allow values to change indirectly. For true immutability, inspect constructors, two-way defensive copying, immutable components, subclassing permissions, and public methods.

Finally, **immutability does not automatically make an entire system thread-safe or optimize performance**. Safe publication, external mutable collaborators, holder updates, transactions/lifecycles, and the cost of creating new versions still require design. For widely shared data, prefer **immutable value objects and snapshots**; for parts that require mutation, keep modification rights within a clear ownership scope.
