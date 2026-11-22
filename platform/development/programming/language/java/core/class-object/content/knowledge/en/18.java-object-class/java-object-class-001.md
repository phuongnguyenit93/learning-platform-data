# Object as the Root Class and Shared Methods in Java

## 1. Overview: Why Understand `java.lang.Object`?

In Java, **`java.lang.Object` is the root superclass of regular classes**. If a class does not declare `extends` for another superclass, it has `Object` as its direct superclass according to the language rules. If it `extends` another class, the superclass chain also ultimately leads to `Object`, except for `Object` itself.

Therefore, Java objects belonging to regular reference classes have **foundational behaviors** declared in `Object`: equality comparison (`equals`), obtaining a hash (`hashCode`), text representation (`toString`), obtaining the runtime class (`getClass`), monitor/synchronization operations (`wait`, `notify`, `notifyAll`), as well as the cloning mechanism (`clone`) and legacy finalization (`finalize`). Not all of them should be overridden or called directly in application code.

~~~java
class Book {
    private final String title;

    Book(String title) {
        this.title = title;
    }
}
~~~

This class **does not declare `extends Object`**, yet a `Book` object still has the applicable instance methods from `Object`. For example:

~~~java
Book book = new Book("Java");
System.out.println(book.getClass().getSimpleName());
System.out.println(book.toString());
~~~

This is a **fragment**, placed in an appropriate method. The first line prints `Book`. The second line uses the `Object.toString()` implementation if Book does not override it; the default string typically takes the form of class name + `@` + hexadecimal digits of the hash code, **with no fixed value to put in expected stdout**.

**Important:** `Object` carries specific Java-level contracts, but it is not the appropriate place for all business logic. A variable of type `Object` only provides a generic API; to express a `pay()`, `render()`, or `getPrice()` contract, you should use a domain-meaningful class/interface.

### 1.1. Lesson Scope

This Knowledge README targets **Java 17+**, belonging to the *Java Core → Class/Object → Object Class* group, and covers:

- `Object` in the type system: class, interface, array, enum, record, primitive, null, and boxing.
- Methods declared by `Object`, accessibility, and when to/not to override.
- Reference identity versus logical/value equality.
- The `equals/hashCode` contract and its impact on `HashMap` and `HashSet`.
- `toString`, `getClass`, and runtime polymorphism.
- `clone`, `Cloneable`, shallow copy, and the copy constructor alternative.
- Object monitor, `synchronized`, `wait`, `notify`, `notifyAll`, and conditions for safe usage.
- Deprecated `finalize`; resource management using `AutoCloseable`.
- Common pitfalls, case studies, standalone Java programs, and exercises with answers.

Do not confuse **the Object class** with **the object-oriented programming paradigm**: the word `Object` in `java.lang.Object` is **the name of a specific class**, whereas the word “object” can refer to any instance of a corresponding reference type.

## 2. Where Does `Object` Sit in the Class Hierarchy?

Example diagram:

~~~text
java.lang.Object
    |
    +-- Vehicle
    |      |
    |      +-- Car
    |
    +-- java.lang.Number
    |      |
    |      +-- java.lang.Integer
    |
    +-- java.lang.Enum<T>
    |      |
    |      +-- enum types
    |
    +-- java.lang.Record
           |
           +-- record classes
~~~

This is a **conceptual diagram, not all classes in the JDK**.

~~~java
class Vehicle {
}

class Car extends Vehicle {
}
~~~

- `Vehicle` has `Object` as its direct superclass.
- `Car` has `Vehicle` as its direct superclass, and `Object` as its indirect superclass.
- `Car` is a subtype of `Vehicle` and `Object`.
- An object with runtime class Car can be held in a variable of type `Car`, `Vehicle`, or `Object` when the assignment is valid.

~~~java
Car car = new Car();
Vehicle vehicle = car;
Object any = car;
~~~

**There are not three objects.** Three reference variables point to the same Car object; upcasting does not copy the object, does not invoke an additional constructor, and does not “erase” the state of Car.

### 2.1. What About a Class That Does Not Write `extends`?

~~~java
class Plain {
}
~~~

In terms of inheritance semantics, `Plain` has `Object` as its direct superclass. There is no need to write:

~~~java
class Plain extends Object {
}
~~~

because an explicit `extends Object` usually adds no extra meaning.

Only `Object` itself has no superclass. You cannot create a valid class sitting “above” Object using normal `extends`.

### 2.2. `Object` and Interfaces Are Different

An interface **does not declare `extends Object` as a class superclass**. Interfaces have their own superinterface inheritance mechanism. Even so, a concrete object implementing an interface is still an instance of a class, and that class has a relationship to `Object`.

~~~java
interface Printable {
    void print();
}

class Invoice implements Printable {
    @Override
    public void print() {
        System.out.println("Invoice");
    }
}
~~~

`Invoice` is a subtype of `Printable` and `Object`. A variable of type `Printable` can invoke the public instance methods associated with `Object` according to interface/type lookup rules (such as `toString()`), but this does not mean `Printable extends Object` under class inheritance syntax.

**Key point:** the superclass relationship between **classes** differs from the superinterface relationship between **interfaces**. `Object` is the root superclass, not a generic business interface.

### 2.3. Arrays Are Also Objects

Arrays in Java are **reference types and are objects**. For example:

~~~java
int[] numbers = {1, 2, 3};
Object value = numbers;
System.out.println(value instanceof Object); // true
~~~

An array has its own runtime class, uses the applicable methods of Object, and has a special `length` field. An array of a primitive type is still an object, even though its **elements** are primitive values.

An important point: `int[]` does not have content-based equals like `Arrays.equals` by default. Two distinct arrays with the same elements are usually **not equal** when using the `equals` method inherited from Object. To compare contents, use `java.util.Arrays.equals` (or `Arrays.deepEquals` for applicable nested object array structures).

### 2.4. Primitive Values Are Not Objects

The primitive types `int`, `long`, `double`, `boolean`, `char`... **do not inherit from Object**, because they are not reference class types.

~~~java
int count = 5;
// count.toString(); // Invalid: primitive int has no methods.
~~~

However, Java has **autoboxing** when converting a primitive to a reference wrapper:

~~~java
Object value = 5; // int is boxed into Integer.
System.out.println(value.getClass().getSimpleName()); // Integer
~~~

This does not mean the primitive `int` suddenly becomes a subtype of Object. An **Integer object** is a reference object, whereas `int` is a primitive value.

### 2.5. `null` Is Not an Object Instance

~~~java
Object value = null;
System.out.println(value instanceof Object); // false
~~~

`null` is a special value that can be assigned to applicable reference variables, but it **is not an instance of Object or any class**. `value.toString()` or `value.getClass()` when `value == null` throws `NullPointerException`.

## 3. Table of Important Methods of `Object`

| Method / Group | Primary Purpose | Can Be Overridden? |
| --- | --- | --- |
| `public boolean equals(Object obj)` | Compares equality according to the class's contract | Yes |
| `public int hashCode()` | Generates a hash code matching the equality contract | Yes |
| `public String toString()` | Textual representation of the object | Yes |
| `public final Class<?> getClass()` | Retrieves the runtime class of the object | **No**, because it is final |
| `protected Object clone() throws CloneNotSupportedException` | Creates a shallow copy per the Cloneable/arrays mechanism | Can be overridden within language constraints |
| `public final void wait()` | Waits on the receiver's monitor | **No**, final |
| `public final void wait(long timeoutMillis)` | Waits with a timeout according to wait rules | **No**, final |
| `public final void wait(long timeoutMillis, int nanos)` | Wait duration variant | **No**, final |
| `public final void notify()` | Wakes up a single thread waiting on the receiver's monitor | **No**, final |
| `public final void notifyAll()` | Wakes up all threads waiting on the receiver's monitor | **No**, final |
| `protected void finalize() throws Throwable` | Legacy finalization hook | Can be overridden in Java 17, **but deprecated and should not be used** |

In addition to methods, `Object` has a **public no-argument constructor**, which participates in constructor chaining of classes that directly extend Object. A constructor is not an inherited method like `toString()`.

**Note:** `equals` and `hashCode` are a pair that usually need to be designed together; `wait/notify` is only valid with monitor ownership; `clone` has restricted access and many design issues; `finalize` is not a reliable destructor.

## 4. Complete Program 1: Default Behaviors and Runtime Class

Create the file **`ObjectBasicsDemo.java`**:

~~~java
public class ObjectBasicsDemo {
    static final class Ticket {
        private final String code;

        Ticket(String code) {
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    public static void main(String[] args) {
        Object original = new Ticket("T-1");
        Object same = original;
        Object another = new Ticket("T-1");

        System.out.println("Same ref = " + (original == same));
        System.out.println("Different ref = " + (original == another));
        System.out.println("Default equals same = "
                + original.equals(same));
        System.out.println("Default equals another = "
                + original.equals(another));

        System.out.println("Runtime class = "
                + original.getClass().getSimpleName());
        System.out.println("Ticket type = "
                + (original instanceof Ticket));

        Object primitiveArray = new int[]{1, 2};
        System.out.println("Array is Object = "
                + (primitiveArray instanceof Object));

        Object boxed = 42;
        System.out.println("Boxed class = "
                + boxed.getClass().getSimpleName());
    }
}
~~~

Compile and run (JDK 17+):

~~~bash
javac -encoding UTF-8 ObjectBasicsDemo.java
java ObjectBasicsDemo
~~~

**Exact stdout:**

~~~text
Same ref = true
Different ref = false
Default equals same = true
Default equals another = false
Runtime class = Ticket
Ticket type = true
Array is Object = true
Boxed class = Integer
~~~

### 4.1. Why Is `Default equals another = false` Despite Having the Same Code?

`Ticket` does not override `equals`. The default `Object.equals` implementation checks **identity**: it is only true when two references point to **the same object**.

- `same = original`: both variables point to the same Ticket instance → `==` is true, `equals` is true.
- `another = new Ticket("T-1")`: a new object even though it holds the same String code → `==` is false, inherited `equals` is false.
- `getClass()` returns the **runtime class** Ticket, even though the variable `original` is declared as type `Object`.
- `Object boxed = 42` boxes the primitive into an Integer, so the runtime class is Integer.

The program intentionally **does not print the default `original.toString()` or `hashCode()`**, because default values can differ across runs and JVMs; using these values as fixed expected output is wrong.

### 4.2. What If You Want Two Tickets with the Same Code to Be Considered Equal?

You need to clearly define the **value equality contract** and override both `equals` and `hashCode`, or choose an appropriate record/value object. That is the topic of the next section.

## 5. `==`, `equals`, and Object Identity

For two reference variables:

~~~java
Object a = new Object();
Object b = new Object();
Object c = a;
~~~

- `a == b` is false for two separate `new Object()` calls.
- `a == c` is true because they share the same reference identity.
- `a.equals(c)` is true.
- `a.equals(b)` is false under the default Object implementation.

The `==` operator, when applied to two compatible reference expressions, checks **reference identity**; it does not call the `equals` method. Therefore, `==` cannot be overridden in Java.

### 5.1. Why Can `equals` Differ from `==`?

A class can override `equals` to define **logical equality**. For example, two Strings with the same content:

~~~java
String a = new String("java");
String b = new String("java");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
~~~

Here, the two `new String(...)` calls create distinct String objects, but `String.equals` compares character content. You should not rely on **string interning** to replace `equals` with `==` for content comparison.

### 5.2. `Objects.equals` for Null-Safe Comparison

~~~java
String a = null;
String b = null;

System.out.println(java.util.Objects.equals(a, b)); // true
~~~

`Objects.equals(a,b)` applies a null-safe rule: if both are null, it returns true; if one is null, it returns false; otherwise, it calls `a.equals(b)`. This helps avoid NPE when reference values may be null.

However, **`Objects.equals` does not automatically deep-compare arrays**: if a class/object only uses inherited equals, it still compares identity; for arrays, use `Arrays.equals` or `Arrays.deepEquals` when appropriate.

### 5.3. Do Not Mechanically Use `getClass() == ...` Instead of `equals`

Some equality implementations choose `getClass()` to require two runtime classes to be identical. Others use `instanceof` to support subtype equality. The choice depends on the contract and inheritance design; both have trade-offs.

For a **final value class**, `instanceof` is usually simple and has no subclasses that break symmetry. For an extensible hierarchy with new state, inheriting equality can be complex; sometimes you should use **composition**, `final class`, or a record.

## 6. `equals(Object)`: The Promise of Logical Equality

`Object.equals(Object)` compares **same instance** by default, but a class can override it to define **value or business-domain equality**. When overriding, the compiler only checks the signature; the developer is responsible for the contract:

| Property | Meaning |
| --- | --- |
| Reflexive | `x.equals(x)` is true if x is non-null |
| Symmetric | `x.equals(y)` and `y.equals(x)` return the same result |
| Transitive | If x equals y and y equals z, then x equals z |
| Consistent | Does not spontaneously change result if data used in comparison is unchanged |
| Non-nullity | `x.equals(null)` is false if x is non-null |

The exact override signature is `public boolean equals(Object other)`. Writing `equals(MyClass)` only creates an **overload** rather than replacing Object.equals; use `@Override` so the compiler helps detect it. If the type differs or the argument is null, the implementation typically returns false; do not cast without checking.

**Role in this chapter:** this overview only introduces why every object has this method. The *identity versus value* lesson builds domain-specific equality semantics; the *equals/hashCode contract* lesson examines symmetry/transitivity, code, and edge cases with dedicated examples.

## 7. `hashCode()`: Tightly Coupled to Equality Decisions

`hashCode()` returns an `int` integer; collections such as `HashMap` and `HashSet` use it together with `equals()`. The rule that must not be broken:

> If `a.equals(b)` is true, then `a.hashCode() == b.hashCode()` must be true.

**The converse does not hold:** two different objects may have the same hash; that is a valid collision. A hash is not a memory address, unique ID, cryptographic digest, or persistent key. If you override `equals()` based on fields `id` and `kind`, the `hashCode()` implementation must reflect **the same equality selection**.

~~~java
@Override
public int hashCode() {
    return java.util.Objects.hash(id, kind);
}
~~~

This is a method fragment requiring `id` and `kind` in the class, not a standalone program. `Objects.hash` is convenient but not mandatory; another hash formula is also valid as long as it preserves the contract.

**Warning about mutation:** modifying a field involved in equality/hashing while the object is inside a hash collection can invalidate lookups. The hash contract lesson analyzes design and testing; the mutable key lesson traces the consequences after state changes.

## 8. Complete Program 2: Overriding `equals/hashCode/toString` According to Contract

Create the file **`EqualityContractDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EqualityContractDemo {
    static final class Key {
        private final long id;
        private final String scope;

        Key(long id, String scope) {
            this.id = id;
            this.scope = Objects.requireNonNull(scope, "scope");
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Key key)) {
                return false;
            }
            return id == key.id && scope.equals(key.scope);
        }

        @Override
        public int hashCode() {
            return Objects.hash(id, scope);
        }

        @Override
        public String toString() {
            return "Key(" + id + "," + scope + ")";
        }
    }

    record Coordinate(int x, int y) {
    }

    public static void main(String[] args) {
        Key first = new Key(7, "A");
        Key sameValue = new Key(7, "A");
        Key different = new Key(8, "A");

        System.out.println("Same reference = "
                + (first == sameValue));
        System.out.println("Logical equals = "
                + first.equals(sameValue));
        System.out.println("Hash consistent = "
                + (first.hashCode() == sameValue.hashCode()));

        Set<Key> keys = new HashSet<>();
        keys.add(first);

        System.out.println("Contains same value = "
                + keys.contains(sameValue));
        System.out.println("Contains different = "
                + keys.contains(different));
        System.out.println("Display = " + first);

        Coordinate point = new Coordinate(2, 3);
        System.out.println("Record = " + point);
        System.out.println("Record equality = "
                + point.equals(new Coordinate(2, 3)));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 EqualityContractDemo.java
java EqualityContractDemo
~~~

**Exact stdout:**

~~~text
Same reference = false
Logical equals = true
Hash consistent = true
Contains same value = true
Contains different = false
Display = Key(7,A)
Record = Coordinate[x=2, y=3]
Record equality = true
~~~

### 8.1. Why Is This Code Correct?

- `Key` is a `final class` with two fields that do not change after construction; there are no subclasses complicating equality symmetry.
- `equals` performs a fast identity check, then checks the type using Java 17 `instanceof` pattern matching, and then compares `id` and `scope`.
- `hashCode` uses the exact same fields that participate in equality.
- Two distinct `Key` instances with the same values have logical equality true and equal hashes, so `HashSet.contains` finds the matching key.
- `toString` returns a deterministic string useful for debugging/logging.
- `Coordinate` is a record; Java generates the `equals/hashCode/toString` methods according to the record component contract, and `Coordinate[x=2, y=3]` is the typical representation of a record in Java 17.

### 8.2. Record Equality Also Requires Checking Mutable Components

A record such as `record R(List<String> items) {}` has a final component reference, but the List itself can be mutable. Record-generated equality uses component equality and does not automatically deep-copy or freeze a mutable List. If you want a stable value object to use as a HashMap key, you need defensive copying and must carefully consider mutable components.

### 8.3. Note on String Data

`String.equals` compares content, and String is immutable. Since `scope` is guaranteed non-null by the constructor, `scope.equals(key.scope)` is valid. If a field may be null, you can use `Objects.equals(scope, key.scope)`.

## 9. Common Incorrect Ways to Override `equals`

### 9.1. Overriding Only `equals`

~~~java
class BadKey {
    private final String id;

    BadKey(String id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BadKey key && id.equals(key.id);
    }

    // Does not override hashCode: violates the contract when equals is true
}
~~~

This illustrates a **flawed design**. Two BadKey objects with equal ids can have equals return true while using different identity-based inherited hashCodes. `HashSet.contains(new BadKey("A"))` may return false even though another BadKey "A" has already been added. Do not rely on hashes accidentally matching occasionally to assume the implementation is correct.

### 9.2. Accidentally Overloading `equals`

~~~java
class Wrong {
    public boolean equals(Wrong other) {
        return true; // Does not override Object.equals(Object).
    }
}
~~~

The compiler accepts the method overload, but APIs operating through type `Object` can still invoke the inherited `equals(Object)`. Adding `@Override` helps detect the signature mismatch.

### 9.3. Checking `getClass()` and Inheritance Without a Clear Contract

~~~java
if (other == null || getClass() != other.getClass()) {
    return false;
}
~~~

This is a **policy choice** in equality, not a mandatory formula. It rejects subclasses of a different class, which can make preserving symmetry easier; however, if the superclass API promises equality across polymorphic subtypes, it can also cause surprises. For values, consider `record` or `final` to avoid opening up a complex equality hierarchy.

### 9.4. Comparing Fields with `==` When Content Equality Is Needed

~~~java
// return this.name == other.name; // Wrong if you want to compare String content.
~~~

Two String objects with equal content can still have different references. Use `name.equals(other.name)` or `Objects.equals(...)` according to the null contract.

### 9.5. Computing `hashCode` from Mutable Data

If `Person` equality/hash depends on `displayName`, changing the name after inserting a Person into a HashSet can leave the key in a bucket that does not match the new hash. Use immutable value keys, stable identity, or a clear lifecycle instead of mutable hash keys.

## 10. `toString()`: Object Representation for Reading, Logging, and Debugging

The default implementation of `Object.toString()` has the conceptual form:

~~~text
runtimeClassName@hexHashCode
~~~

It does not automatically list private fields, does not guarantee a unique ID, and is **not stable** across program runs. If an object has domain meaning, overriding `toString()` is often useful:

~~~java
@Override
public String toString() {
    return "Order{id='" + id + "', total=" + totalCents + "}";
}
~~~

This is a **method fragment**; the class needs the corresponding fields.

### 10.1. When Does Java Automatically Call `toString()`?

Certain operations such as `System.out.println(object)`, `String.valueOf(object)`, or string concatenation with an object typically use the object's string representation according to the respective API.

~~~java
Object value = new Coordinate(1, 2);
System.out.println(value);
~~~

If `Coordinate` is an appropriate record, the representation consists of the record name and its components. For a class that does not override toString, the default result only contains the class name and hash formatting.

### 10.2. `toString` Is Neither JSON Serialization Nor a Stable Data API

- The content of `toString` usually serves **diagnostics**, not a wire protocol.
- Do not parse `toString` to exchange data between services.
- Do not write passwords, tokens, session secrets, or sensitive personal information into toString.
- Be careful with object graphs containing cycles: if Parent.toString calls Child.toString and vice versa, infinite recursion can occur.
- Be careful with lazy relationships/ORM: toString can trigger unintended queries or loading.
- Be careful logging an object from a constructor: a subclass's `toString` override may be called when subclass fields are not yet initialized.

### 10.3. `toString` and Dynamic Dispatch

`Object value = new Child(); System.out.println(value)` can invoke `Child.toString()` if class Child overrides it. Java uses the runtime receiver in overridable instance method calls; the static type Object does not force toString to always use Object's implementation.

## 11. `getClass()` Returns the Runtime Class

`getClass()` is a **final method** of Object, returning a `Class<?>` representing the runtime class of the object. For example:

~~~java
Object value = "Java";
Class<?> type = value.getClass();
System.out.println(type.getSimpleName()); // String
~~~

If a variable is declared as Object but holds a String, getClass returns the String class. `getClass` does not “turn into an Object method according to static type” and report Object.

### 11.1. Comparing `getClass()` with `instanceof`

~~~java
Number number = Integer.valueOf(5);

System.out.println(number instanceof Number);  // true
System.out.println(number instanceof Integer); // true
System.out.println(number.getClass() == Integer.class); // true
~~~

- `instanceof` checks **type compatibility** with the target type, including matching subtypes/interface implementations.
- `getClass() == SomeClass.class` checks for **the exact runtime class object**, and does not consider a subclass equal to the superclass class literal.
- `getClass()` throws NPE on a null receiver, whereas `null instanceof SomeClass` is false.

You should not drive all business behavior using chains of `if (value.getClass() == X.class)` if polymorphic virtual methods or interfaces express the contract more clearly.

### 11.2. Runtime Class Metadata Can Be Used for Reflection

`Class<?>` provides reflection APIs such as `getName()`, `getDeclaredMethods()`, `getSuperclass()`, etc. However, reflection is subject to access/module rules and has its own overhead/design implications. For normal Java Core code, prefer calling strongly typed methods rather than repeatedly using `getClass()` and reflection to look up methods by name.

### 11.3. `getClass()` Cannot Be Overridden

You cannot:

~~~java
// @Override
// public Class<?> getClass() { ... } // Error: Object.getClass() is final.
~~~

If an object needs to provide a **business type** different from its runtime class, add a dedicated method such as `kind()`, `category()`, or an appropriate interface. Do not try to override getClass to spoof runtime identity.

## 12. Complete Program 3: An `Object` Reference Still Has Polymorphism

Create the file **`ObjectPolymorphismDemo.java`**:

~~~java
public class ObjectPolymorphismDemo {
    static class Message {
        String render() {
            return "Message";
        }

        @Override
        public String toString() {
            return "Message<" + render() + ">";
        }
    }

    static final class Alert extends Message {
        @Override
        String render() {
            return "Alert";
        }
    }

    public static void main(String[] args) {
        Object value = new Alert();

        System.out.println("Text = " + value);
        System.out.println("Runtime = "
                + value.getClass().getSimpleName());
        System.out.println("Message type = "
                + (value instanceof Message));

        if (value instanceof Alert alert) {
            System.out.println("Render = " + alert.render());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ObjectPolymorphismDemo.java
java ObjectPolymorphismDemo
~~~

**Exact stdout:**

~~~text
Text = Message<Alert>
Runtime = Alert
Message type = true
Render = Alert
~~~

### 12.1. Why Is the Text `Message<Alert>`?

1. `Object value = new Alert()` upcasts an Alert object to a reference with compile-time type Object.
2. String concatenation uses `toString()` on the runtime Alert object. Alert does not override toString, so it uses `Message.toString()`.
3. Inside `Message.toString()`, the `render()` call is a virtual instance call and dispatches to `Alert.render()`.
4. `getClass()` returns runtime class Alert; `instanceof Message` is true due to inheritance.
5. Java 17 pattern matching `instanceof Alert alert` allows calling subtype-only APIs when the runtime type matches.

**Notably:** even when the `Message.toString()` implementation is inherited, the virtual method call inside it can still select the subclass behavior.

## 13. What Is `clone()`?

`Object` declares:

~~~java
protected Object clone()
        throws CloneNotSupportedException
~~~

By default, this method has **protected** visibility, so an external caller cannot arbitrarily call `someObject.clone()` merely because the object belongs to a class that inherits from Object.

For a regular instance class, the `Object.clone()` mechanism checks cloneability via `Cloneable`. A class wishing to use the corresponding inherited clone method typically **implements `Cloneable`** and exposes an overridden method with appropriate accessibility. **`Cloneable` is a marker interface**; it does not declare a public `clone()` method.

### 13.1. `Object.clone` Creates a Shallow Copy

A typical shallow copy:

- Creates another object with field values copied from the original object.
- Primitive fields have their values copied.
- Reference fields have their **reference values** copied, so both the original and the clone may point to **the same internal mutable object**.
- The class's regular constructor **is not invoked the way an object is created with `new`** in `Object.clone`.
- `final` fields in a shallow-cloned object also retain the copied reference values; `final` does not make child objects immutable.

Therefore, `clone()` is not an automatic solution for deep copying or invariant preservation. Many modern Java APIs prefer **copy constructors, static factories, immutable values, or explicit copy methods** to clearly control semantics.

### 13.2. Why Do Many Developers Rarely Use `Cloneable`?

The Cloneable/Object.clone API has common drawbacks:

- `Cloneable` does not declare the `clone` method in the interface.
- Object.clone is protected and declares a checked exception.
- Shallow copying easily causes unintended aliasing.
- How to deep-copy a graph containing collections, mutable children, and cycles requires a domain-specific policy.
- Constructors/validation do not run like the ordinary new-construction path; this can create inconsistencies with invariants if not carefully designed.

This is not to say that clone is forbidden or always wrong: arrays and some libraries use clone appropriately. However, you need to know the exact copy contract.

### 13.3. Array Cloning

Arrays support `clone()`, and cloning an array creates a **new array object**. For example:

~~~java
int[] first = {1, 2};
int[] second = first.clone();

second[0] = 9;
System.out.println(first[0]);  // 1
System.out.println(second[0]); // 9
~~~

For `Object[][]` or an array containing mutable elements, cloning only copies **the outer array/reference elements** under shallow-copy semantics; it does not deep-copy every nested object.

## 14. Complete Program 4: Shallow Clone and Independent Copy

Create the file **`CloneCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CloneCopyDemo {
    static final class Tags implements Cloneable {
        private final List<String> values;

        Tags(List<String> source) {
            this.values = new ArrayList<>(source);
        }

        void add(String tag) {
            values.add(tag);
        }

        List<String> snapshot() {
            return List.copyOf(values);
        }

        @Override
        public Tags clone() {
            try {
                return (Tags) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }

        Tags independentCopy() {
            return new Tags(values);
        }
    }

    public static void main(String[] args) {
        Tags original = new Tags(List.of("A"));
        Tags shallow = original.clone();
        Tags independent = original.independentCopy();

        shallow.add("B");
        independent.add("C");

        System.out.println("Original = " + original.snapshot());
        System.out.println("Shallow = " + shallow.snapshot());
        System.out.println("Independent = " + independent.snapshot());
        System.out.println("Different objects = "
                + (original != shallow));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CloneCopyDemo.java
java CloneCopyDemo
~~~

**Exact stdout:**

~~~text
Original = [A, B]
Shallow = [A, B]
Independent = [A, C]
Different objects = true
~~~

### 14.1. Line-by-Line Explanation

- `Tags` implements Cloneable, and the public `clone()` override calls `super.clone()`.
- `super.clone()` creates a **new Tags object** and copies the `values` reference; the two Tags objects share **the same ArrayList instance**.
- `shallow.add("B")` modifies the shared list, so `original.snapshot()` also includes B.
- `independentCopy()` goes through the `new Tags(values)` constructor; the constructor creates `new ArrayList<>(source)`, giving it a **separate list**.
- `independent.add("C")` modifies only its own list, producing the result `[A, C]`.
- `original != shallow` is true: the two Tags objects are different even though they share a nested list.

**`final List<String> values` does not prevent sharing a mutable list reference.** Final only restricts reassignment of the field inside an object according to Java language rules.

### 14.2. Is a Copy Constructor Unconditionally a Deep Copy?

No. For example, the constructor `new ArrayList<>(source)` only copies the List structure and **does not automatically clone each mutable element**. The program above uses immutable Strings, so a structural snapshot suffices to illustrate the point. If the List holds `MutableCustomer`, you must decide whether to create a new MutableCustomer for each element, share an immutable ID, or use another ownership protocol.

## 15. `wait()`, `notify()`, and `notifyAll()` Belong to `Object`

These are **final instance methods** of `java.lang.Object`, tied to the intrinsic monitor of **that exact receiver object**. They are not methods of `Thread` and differ from `Thread.sleep()`.

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
~~~

This is a snippet that requires `lock`, `ready`, and appropriate exception handling. The thread calling `lock.wait()` must own the monitor **of that lock itself**; otherwise, it can throw `IllegalMonitorStateException`. While waiting, `wait` releases the receiver's monitor and reacquires it before returning according to the rules. `Thread.sleep` does not release held monitors.

`notify()` selects one waiter, while `notifyAll()` notifies all waiters on the same receiver, **without immediately transferring the monitor** to them. A notification is not accumulated data; the condition `ready` is the state that must be protected. Use `while` to recheck the predicate after waking up, including for spurious wakeups or when another waiter has already consumed the data.

This lesson introduces the Object API and a small program in Section 16. The dedicated `wait/notify/notifyAll` topic at the end of the chapter analyzes ordering, interruption, timeouts, lost signals, bounded buffers, and `java.util.concurrent` in depth.

## 16. Complete Program 5: `wait`/`notifyAll` with Proper Condition and Monitor

Create the file **`ObjectMonitorDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public class ObjectMonitorDemo {
    static final class Gate {
        private boolean open;

        synchronized void awaitOpen() throws InterruptedException {
            while (!open) {
                wait(); // this.wait(): currently holding the monitor of this
            }
        }

        synchronized void open() {
            open = true;
            notifyAll(); // this.notifyAll(), same monitor
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Gate gate = new Gate();
        AtomicBoolean passed = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            try {
                gate.awaitOpen();
                passed.set(true);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        worker.start();
        gate.open();
        worker.join();

        System.out.println("Worker passed = " + passed.get());
        System.out.println("Main finished");
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ObjectMonitorDemo.java
java ObjectMonitorDemo
~~~

**Stdout in a normal run (without external interruption):**

~~~text
Worker passed = true
Main finished
~~~

### 16.1. Why Does the Example Avoid a “Lost” Notification Race?

Both thread scheduling sequences are correct:

- **Worker enters `awaitOpen` first:** sees `open=false`, calls `wait()`, and releases the Gate monitor. Main enters `open()`, sets open=true, and calls `notifyAll()`. Worker is woken up, reacquires the monitor, sees open=true, and exits the method.
- **Main opens the gate before the worker waits:** Main sets `open=true`. Worker enters `awaitOpen` afterward, sees the condition is already true, and **does not need to wait**. It does not depend on whether the notification “arrives first.”

In both cases, the condition `open` is accessed under synchronized methods on the same Gate object. `worker.join()` makes main wait for the worker to finish; `AtomicBoolean` here provides a simple way to store the result in a thread-safe manner, although `join` also participates in the appropriate memory visibility relationship.

### 16.2. Why Not Call `notifyAll` Without Setting the State?

If you only call `notifyAll()` while leaving `open=false`, the worker can wake up and go back to `wait()` because the condition is not yet met. This is the intended design: **notification does not replace updating the condition**.

### 16.3. Why Catch `InterruptedException` and Restore the Interrupted Status?

In the worker, the exception is caught, and then `Thread.currentThread().interrupt()` restores the interruption status so that thread-management code can know the thread was requested to interrupt. A real application must define a policy when interrupted: cancel the work, clean up, or propagate the exception. You should not silently swallow interruption inside an infinite wait loop.

### 16.4. Should You Use the Object Monitor API in New Applications?

It can be used correctly, but for many modern concurrency scenarios, APIs in `java.util.concurrent` **express intent more clearly and reduce errors**:

- `CountDownLatch`: wait for a number of events to complete.
- `BlockingQueue`: producer/consumer data exchange.
- `Semaphore`: limit the number of permits.
- `ReentrantLock` + `Condition`: conditions/locks with a separated API.
- `CompletableFuture`: represent asynchronous completion.
- `AtomicInteger`, `AtomicReference`: atomic state under the appropriate contract.

Understanding Object.wait/notify is still necessary for reading legacy code, explaining intrinsic locks, and understanding monitor principles. You should not replace it with busy waiting or `Thread.sleep` in a loop when condition-based coordination is actually needed.

## 17. `IllegalMonitorStateException`: A Common Monitor Error

Wrong:

~~~java
Object lock = new Object();
// lock.wait();      // Runtime error: not holding lock's monitor
// lock.notifyAll(); // Runtime error: not holding lock's monitor
~~~

The erroneous statements are commented out. The right way:

~~~java
Object lock = new Object();
synchronized (lock) {
    lock.notifyAll();
}
~~~

If there are no waiters, `notifyAll` simply wakes up no threads; the call itself does not create a “notification token” saved for the future. That is why shared condition state such as `open=true` in the Gate example is needed.

### 17.1. Locking on the Wrong Object Is Also a Bug

~~~java
Object lockA = new Object();
Object lockB = new Object();

synchronized (lockA) {
    // lockB.wait(); // Wrong: owning lockA does not mean owning lockB.
}
~~~

`wait/notify` is tied to **the exact monitor of the receiver object**. You should use a `private final Object lock = new Object();` or synchronized methods with `this` when the lifecycle/access is appropriate. Do not synchronize on objects easily shared with untrusted code unintentionally, because other code can increase contention or break the protocol.

### 17.2. Do Not Call wait/notify on an Object Just Because It Is an Object

Every object generally has a monitor, but **not every object should be used as a lock**. For example, locking on `String` literals or public `Class` objects can cause unrelated pieces of code to accidentally share the same monitor. A **private lock object** usually reduces coupling when designing concurrency.

## 18. `Object.finalize()` Is a Legacy API, Do Not Use It as a Destructor

Java 17 still has the legacy hook `Object.finalize()`, but finalization has been **deprecated** and is **unsuitable** for resource lifecycle management.

Reasons:

- There is no guarantee a finalizer will run in a timely manner.
- You cannot rely on the cleanup order of finalizers like a synchronous destructor.
- Finalization increases complexity, risk of resource leaks, and safety issues.
- Do not hold a file/socket/database connection waiting for GC to call finalize to close it.
- Do not write business logic based on when finalize runs.

**A typically suitable replacement:** implement `AutoCloseable` and use **`try-with-resources`**; use `Cleaner` in special cases requiring fallback cleanup when you truly understand its limitations, but do not use it as a primary substitute for deterministic closing.

### 18.1. `AutoCloseable` Is Not an Inherited Object Method

`AutoCloseable` is an interface with a `close()` method, **not** a method defined by `Object`. A class wanting an explicit close lifecycle typically implements AutoCloseable:

~~~java
final class Resource implements AutoCloseable {
    private boolean closed;

    void use() {
        if (closed) {
            throw new IllegalStateException("Resource đã đóng");
        }
        System.out.println("Using resource");
    }

    @Override
    public void close() {
        closed = true;
        System.out.println("Resource closed");
    }
}
~~~

A `try (Resource resource = new Resource()) { resource.use(); }` ensures close is called according to try-with-resources rules upon exiting the scope.

### 18.2. Timely Resource Closing Differs from Object Garbage Collection

`Object` and GC do not define a rule for you that “once an object is no longer used, the resource is closed immediately.” For files/sockets, the application must have a policy for **who owns them and when to close them**. `try-with-resources` fits lexical ownership; long-lived managed resources may need an explicit lifecycle manager.

### 18.3. Complete Program 6: Explicit Cleanup Instead of Finalization

Create the file **`ResourceLifecycleDemo.java`**:

~~~java
public class ResourceLifecycleDemo {
    static final class Resource implements AutoCloseable {
        private boolean closed;

        void use() {
            if (closed) {
                throw new IllegalStateException("Already closed");
            }
            System.out.println("Using resource");
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("Resource closed");
            }
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            resource.use();
            System.out.println("Work finished");
        }
        System.out.println("After scope");
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ResourceLifecycleDemo.java
java ResourceLifecycleDemo
~~~

**Exact stdout:**

~~~text
Using resource
Work finished
Resource closed
After scope
~~~

**Key takeaway:** `Resource.close()` runs due to **try-with-resources**, not because `Object.finalize()` or GC decides to run at that exact moment. `close()` in the example is idempotent in code to avoid printing twice, but idempotency must be designed according to the actual resource contract.

## 19. Overridable and Non-Overridable Object Methods

Summary design table:

| Method | Design Guideline |
| --- | --- |
| `equals` | Override when the class has a clear logical equality contract, preserving symmetry/transitivity |
| `hashCode` | Override consistently with equals if overriding equals |
| `toString` | Override for useful debugging/diagnostics, without leaking secrets |
| `getClass` | Final; do not override. Use runtime type metadata only if truly needed |
| `clone` | Consider carefully, protected and shallow copy; prefer an explicit copy contract |
| `wait/notify/notifyAll` | Final; do not override; follow the proper monitor/condition protocol |
| `finalize` | Legacy/deprecated; avoid completely in new designs |

**Not all objects need to override `equals`/`hashCode`.** An entity with its own identity can use reference identity if that is the intentional contract. Value objects typically need value equality; records provide built-in support based on components.

### 19.1. Why Is the Object API Only a Foundation?

Suppose a method accepts `Object data`:

~~~java
void process(Object data) {
    System.out.println(data);
}
~~~

The method can call `data.toString()` (if non-null) because Object exposes that method, but the compiler does not allow calling `data.validateInvoice()` unless the type of data has that API or you cast/check to an appropriate type.

Using `Object` for every parameter sacrifices semantic type safety. If a method needs an `Invoice`, write `process(Invoice invoice)`. If you need a common contract across multiple kinds, define an interface such as `Printable`/`Payable`.

## 20. Object Identity, Equality, and Hashing in Collections

### 20.1. `HashSet` and `HashMap`

`HashSet` relies on hashing/equality to determine membership. `HashMap` uses hashing/equality to look up keys. For keys to work reliably:

- The equality contract must be correct.
- Equal keys must have equal hash codes.
- Fields participating in equality/hashing must remain stable while the key is in the collection, or there must be an appropriate remove/reinsert policy.
- Do not use hashCode as a unique identifier or for security.

### 20.2. `IdentityHashMap` Uses Reference Identity

`java.util.IdentityHashMap` has identity-based semantics for keys and differs from `HashMap` in its comparison contract. It can be useful for object graph traversal or identity-sensitive use cases, but **it does not replace HashMap by default** when business logic relies on logical equality.

Do not confuse `System.identityHashCode(obj)` with an overridden `obj.hashCode()`. The identityHashCode API provides a hash following default identity semantics; **there is no guarantee that it is a unique code or a memory address**.

### 20.3. `TreeSet`/`TreeMap` Use Comparison Ordering

Sorted collections typically rely on `Comparator` or `Comparable` to determine ordering and, in many situations, also the notion of equivalent keys according to the comparator. That can differ from `Object.equals` if the comparator is inconsistent with equality; therefore, designing the comparator contract also requires care.

### 20.4. Arrays

~~~java
int[] a = {1, 2};
int[] b = {1, 2};

System.out.println(a.equals(b));              // false
System.out.println(java.util.Arrays.equals(a, b)); // true
~~~

The two arrays are two separate objects. An array's equals inherited from Object checks identity; `Arrays.equals` compares elements. For nested arrays, you need to understand shallow element equality versus deep array equality.

## 21. `Object` and Generic Types

Java generics operate on reference types. For example:

~~~java
java.util.List<String> names = java.util.List.of("Lan");
Object value = names;
~~~

`names` is a List object, so it can be held in an Object reference. However, the compiler does not allow calling `value.get(0)` if `value` has compile-time type Object; you need a type that exposes the List API or a checked cast.

### 21.1. Generic Erasure and Object

For an unbounded type parameter `T`, **type erasure** rules may use Object in the bytecode representation for certain positions. However, this does not mean every T value is an “Object class instance” in the primitive sense; normal generic type arguments must be reference types, and boxing/unboxing is applied when using primitive values as type-like arguments via wrappers.

### 21.2. `List<Object>` Is Not a Generic Container Superclass of Every `List<T>`

~~~java
java.util.List<String> names = java.util.List.of("Java");
// java.util.List<Object> all = names; // Invalid
~~~

Normal Java generics are **invariant**: `String extends Object` does not mean `List<String> extends List<Object>`.

If you only need to read values as type Object:

~~~java
void inspect(java.util.List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
~~~

This is a method fragment. `List<?>` uses a wildcard so it can accept various matching parameterized Lists; code cannot arbitrarily add an arbitrary Object to it because the compiler does not know the concrete element type.

## 22. `Object` and Records in Java 17

Record classes are a way of declaring data carriers that have generated implementations for:

- `equals` based on record components.
- matching `hashCode`.
- `toString` containing the record name/components.

~~~java
record Point(int x, int y) {
}
~~~

For `new Point(1, 2)`, `toString` has the representation `Point[x=1, y=2]`; two Points with the same components have equality true.

However, do not generalize that “records are always deeply immutable”:

~~~java
record Group(java.util.List<String> names) {
    Group {
        names = java.util.List.copyOf(names);
    }
}
~~~

The compact constructor copies the List structure. Because String elements are immutable, the example is easier to reason about. If a component is a mutable object graph, record-generated equals/hashCode can observe state changes over time; defensive copying must be as deep as the domain contract requires.

A record is a subtype of `java.lang.Record` and ultimately Object, but **cannot freely `extends` another custom superclass**. `Record` declares specific methods and contracts; not every Object method can be overridden the same way as in an ordinary class hierarchy.

## 23. `Object` and Enum

Each enum type has a special superclass mechanism through `java.lang.Enum`, and Enum ultimately inherits from Object. Enums have stable identity semantics for constants; enum `equals` is final in `Enum` so it cannot be arbitrarily overridden to use a different logical equality. `Enum.hashCode` is also final according to the API.

~~~java
enum Mode {
    SAFE, FAST
}
~~~

`Mode.SAFE == Mode.SAFE` is true. Using `==` to compare enum constants is idiomatic, because each enum constant is a corresponding singleton within the runtime enum class-loading context. There is no need to override `equals` to compare enum names.

**Do not treat enum behavior as an example for every class:** an ordinary value class may need logical equality via `equals`, whereas the identity of enum constants is part of the language design.

## 24. `Object` and Inheritance/Polymorphism

A subclass can override the instance methods of Object that are permitted to be overridden. For example:

~~~java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    @Override
    public String toString() {
        return "Person(" + name + ")";
    }
}
~~~

An `Object ref = new Person("Lan")` still invokes `Person.toString()` when `ref.toString()` is executed. This is **dynamic dispatch**, even though the reference has compile-time type Object.

### 24.1. Access Modifiers When Overriding

`equals`, `hashCode`, and `toString` are all **public** in Object. An overriding method must not reduce visibility to `protected`/package-private/`private`. Therefore, the override signature:

~~~java
@Override
public String toString() {
    return "Readable";
}
~~~

is valid; `protected String toString()` would be invalid due to reducing visibility.

### 24.2. `final` Object Methods Cannot Be Overridden

`getClass()`, `wait(...)`, `notify()`, and `notifyAll()` are final. You cannot “customize” how the JVM retrieves the runtime class or monitor behavior by overriding them. Create a separate abstraction/behavior if the domain requires it.

### 24.3. Design Restriction: Calling Overridable Object Methods in a Constructor

A superclass constructor can inadvertently call `toString()`, `equals`, or `hashCode` while the subclass state has not finished initializing. Java still performs dynamic dispatch, causing the override to read default values/null or throw exceptions.

For example:

~~~java
class Base {
    Base() {
        System.out.println(this); // May call Child.toString too early
    }
}
~~~

A subclass with `private final String id` assigned after `super()` is not necessarily ready inside the `toString()` override at that moment. **Avoid calling overridable methods and avoid leaking `this` too early during construction**.

## 25. `Object` Is Not a Copy/Equality Design Template for Every Domain

Different kinds of objects have different natures:

| Kind | Typically Suitable Equality | Typically Suitable Copy / Lifecycle |
| --- | --- | --- |
| Immutable value object | Compares values by components | Create new or share since immutable |
| Entity with stable ID | By domain identity, which may differ from reference identity | Usually not implicitly cloned; manage lifecycle separately |
| Mutable collection | By collection API such as `List.equals` comparing elements | Structural copy or immutable snapshot |
| Array | Reference identity by default | Shallow `clone` / `Arrays.copyOf` |
| Thread/task/resource | Usually identity-based | Explicit lifecycle, do not clone arbitrarily |
| Record | Components-based equality | Copy/new record, defensive-copy mutable components |
| Enum | Constant identity | Do not create arbitrary copies, do not clone |
| Proxy/framework entity | Per contract/framework | Be careful with lazy state, transactions, identity |

**There is no universal formula** such as “every class must override equals/hashCode/clone.” Before overriding, you need to answer:

1. Is this an entity or a value?
2. Do callers want to compare the same instance or the same content?
3. Are the fields participating in equality mutable?
4. Can the object reside in a hash-based collection?
5. Are there subclasses/proxies?
6. If copied, should mutable parts be shared?
7. Does the object hold an external resource/identity that cannot be cloned arbitrarily?

## 26. Common Misconceptions

1. **“Only classes that write `extends Object` have Object methods.”** False: regular classes without an explicit extends also have Object as their superclass.
2. **“Primitive `int` is a subclass of Object.”** False: primitives are not reference classes; boxing creates a wrapper Integer object.
3. **“An interface extends Object just like a class.”** Syntactically false; concrete implementing objects still have Object-related members.
4. **“An array is not an Object because it has primitive elements.”** False: an array is an object even when its elements are primitives.
5. **“`null instanceof Object` is true because Object encompasses everything.”** False: null is not an instance, so the result is false.
6. **“`Object.equals` compares all fields by default.”** False: it compares reference identity.
7. **“`==` on String always compares content.”** False: `==` compares reference identity; `String.equals` compares content.
8. **“Overriding equals alone is enough.”** False if equality semantics differ from identity; a consistent hashCode is needed.
9. **“Same hashCode means equals is true.”** False: hash collisions are valid.
10. **“hashCode is the memory address.”** There is no guarantee; do not rely on that.
11. **“Default `toString` provides a permanently unique ID.”** False; output can differ across runs and is not a stable ID.
12. **“Every `toString` should print all fields.”** False: it can expose secrets, trigger cycles, lazy loading, and performance issues.
13. **“`getClass()` returns the variable's declared type.”** False: it returns the object's runtime class.
14. **“You can override `getClass()` to fake a type.”** False: it is a final method.
15. **“`clone()` deep-copies all child objects by default.”** False: it performs a shallow copy.
16. **“Cloneable declares a public `clone()`.”** False: Cloneable is a marker interface, and Object.clone is protected.
17. **“A final reference field makes a nested list immutable.”** False: final only restricts reassigning the field.
18. **“`wait()` can be called outside synchronized without a lock.”** False: lacking monitor ownership causes IllegalMonitorStateException.
19. **“`notify()` always wakes up the exact thread you want.”** False: there is no guarantee which specific thread is chosen.
20. **“`notifyAll()` releases the lock immediately.”** False: the notifier still holds the monitor until it unlocks.
21. **“Once `wait()` wakes up, the condition is guaranteed true.”** False: you must recheck it inside `while`.
22. **“`Thread.sleep()` releases the monitor like wait.”** False.
23. **“finalize() is a destructor, so files can be closed inside it.”** False: it is deprecated and does not guarantee timely cleanup.
24. **“Every Object should override all methods.”** False; the choice depends on the semantics of the class.
25. **“`List<String>` is a subtype of `List<Object>`.”** False: generic invariance.
26. **“A record is deeply immutable in all cases.”** False when it has mutable reference components.
27. **“An Object reference lets you call every method of the runtime object.”** False: the compiler relies on the compile-time type when checking APIs.
28. **“An Object monitor means automatic thread safety.”** False: shared state requires a consistent synchronization protocol.
29. **“`equals(Object)` can be changed to `equals(MyType)` to override.”** False: that is an overload.
30. **“You can turn `Object` into a specific domain class just by casting regardless of runtime type.”** False: an incompatible type causes ClassCastException.

## 27. Self-Check Exercises with Answers

**Question 1.** Why does `class A {}` still have a `toString()` method?

**Answer:** A regular class that omits extends has `Object` as its direct superclass according to Java language rules, so it inherits the applicable members from Object.

**Question 2.** Is `int x = 3;` an Object instance?

**Answer:** No. `int` is a primitive; when used as `Object ref = x`, Java autoboxes it into an Integer reference.

**Question 3.** Is `int[] a = {1,2}; Object ref = a;` valid?

**Answer:** Yes. Arrays are objects/reference types and can be assigned to an Object reference.

**Question 4.** What does `new Object().equals(new Object())` return?

**Answer:** False, because these are two separate objects and the inherited Object.equals compares reference identity.

**Question 5.** Given `String a = new String("A"); String b = new String("A");`, what are `a==b` and `a.equals(b)`?

**Answer:** `a==b` is false due to two distinct instances, while `a.equals(b)` is true because the String contents are identical.

**Question 6.** Why does overriding `equals` require overriding `hashCode`?

**Answer:** Because the contract requires equal objects to have equal hash codes. Otherwise, HashMap/HashSet can fail to look up keys properly.

**Question 7.** Can two different objects have the same hashCode?

**Answer:** Yes. Collisions are valid; hash equality is not sufficient to conclude logical equality.

**Question 8.** Can `hashCode()` be used as a database primary key or a stable security token?

**Answer:** No. Hash codes are not guaranteed unique, are not stable across runs, and are not cryptographic secrets.

**Question 9.** Does `Object v = new Dog(); v.getClass()` return Object.class or Dog.class?

**Answer:** Runtime class Dog. `getClass` does not report the compile-time declaration type.

**Question 10.** Can `v.toString()` invoke Dog's implementation even though variable v has type Object?

**Answer:** Yes. `toString` is an overridable instance method, so it uses dynamic dispatch based on the runtime object.

**Question 11.** Can `getClass()` be overridden in a subclass?

**Answer:** No. `Object.getClass()` is final.

**Question 12.** Does `Objects.equals(null, null)` return true?

**Answer:** Yes. It is a null-safe equality helper.

**Question 13.** Given two arrays with the same elements, does `a.equals(b)` automatically compare their contents?

**Answer:** No. Arrays inherit identity-based equals; use `Arrays.equals` or `Arrays.deepEquals` as needed.

**Question 14.** Does a class implementing Cloneable automatically expose a public clone method?

**Answer:** No. Cloneable is a marker interface; Object.clone is protected. The class must design/publicly override it if it wants to expose clone.

**Question 15.** Does a shallow clone of an object with a final List field create a new List?

**Answer:** Not automatically. The reference to the List is copied, so the clone and the original can share the same mutable List.

**Question 16.** Why is a copy constructor usually clearer than clone?

**Answer:** It allows explicitly defining which fields/objects to copy, running validation, and deciding ownership/aliasing.

**Question 17.** Why must `lock.wait()` be inside synchronized(lock)?

**Answer:** The thread must own the monitor of the receiver lock; otherwise, it can throw IllegalMonitorStateException.

**Question 18.** Does calling `notifyAll` release the monitor immediately?

**Answer:** No. The notifier retains the monitor until the synchronized section ends/unlocks; waiters must reacquire the monitor to proceed.

**Question 19.** Once notified, can a waiter assume the condition is true?

**Answer:** No. It must recheck the condition in a loop due to spurious wakeups, contention, and state changes.

**Question 20.** Why is `Thread.sleep` not used instead of `Object.wait` in a condition protocol?

**Answer:** Sleep does not release the monitor; wait works with the monitor/condition, releasing the monitor according to wait's semantics.

**Question 21.** Does `Object.finalize()` guarantee closing a socket before the process exits?

**Answer:** No. Finalization is deprecated and does not guarantee timing or timely execution; use AutoCloseable/try-with-resources.

**Question 22.** Does a record need to manually implement standard equals/hashCode/toString?

**Answer:** Java generates implementations based on record components; they can be overridden within language/contract rules when needed, but should not be made inconsistent with the record's values.

**Question 23.** How does `IdentityHashMap` differ from HashMap?

**Answer:** It uses identity semantics for keys and does not replace a normal map based on logical equals/hashCode.

**Question 24.** Why is a mutable key dangerous in a HashSet?

**Answer:** If fields participating in hash/equality change after insertion, lookup/remove may fail to find the key in the current hash structure.

**Question 25.** Is `null.getClass()` valid?

**Answer:** No. Dereferencing a null reference throws NPE; null is not an Object instance.

**Question 26.** Should a method parameter be typed as Object when business logic only accepts Order?

**Answer:** Usually no. Use Order or a specific interface so the compiler checks the API and conveys the contract.

**Question 27.** Can `notify()` be overridden to build a custom notification mechanism?

**Answer:** No. `Object.notify` is final. Create a custom API or use java.util.concurrent primitives.

**Question 28.** Does `super.toString()` always bypass subclass hooks inside the superclass implementation?

**Answer:** No. A super-call selects the superclass toString at the entry point, but virtual calls triggered deeper inside can still dispatch to the subclass.

**Question 29.** If a class does not override equals, is that necessarily a design flaw?

**Answer:** No. For an identity-oriented object, the inherited Object.equals can match the intended contract.

**Question 30.** Can `Object` replace an interface like `Runnable` or `PaymentGateway`?

**Answer:** No. Object provides general object behaviors; domain interfaces provide contracts that the compiler and runtime can use polymorphically in a meaningful way.

## 28. Checklist When Deciding to Use the Object API

1. **Is this a reference object or a primitive?** Distinguish between boxing and reference types.
2. **Is reference identity or logical/value equality needed?** Do not use `==` for String content.
3. **If overriding equals, has hashCode also been overridden consistently?**
4. **Is mutable data being used as a hash key?** Check stability.
5. **Does `toString` leak secrets, or trigger cycles or lazy-loading side effects?**
6. **Is runtime class metadata needed?** `getClass` returns the concrete runtime type.
7. **Are exact class checks being overused instead of polymorphism?**
8. **If copying is desired, is a shallow copy sufficient?** Check nested mutable objects.
9. **Is Cloneable really needed?** Consider a copy constructor/factory.
10. **Are wait/notify called on the right monitor object while holding the monitor?**
11. **Is the shared condition updated under a consistent synchronization protocol?**
12. **Does the waiter use `while` to recheck the condition?**
13. **Is interruption handled according to the contract?**
14. **Should CountDownLatch/BlockingQueue/Condition be used instead of wait/notify?**
15. **Are resources being managed using finalize?** Replace with deterministic closing.
16. **For arrays, is Arrays.equals/Arrays.deepEquals needed?**
17. **For records, are component references mutable?** Consider defensive copying.
18. **For enums, is equals being overused instead of the `==` identity comparison?**
19. **Is the Object type being used where a specific domain type/interface is needed?**
20. **Are overridable Object methods called too early in a constructor?** Avoid observing subclass state that is not yet ready.

## 29. Summary

**`java.lang.Object` is the foundation of the Java class hierarchy**, because regular classes ultimately inherit from Object. This provides shared contracts such as **`equals`, `hashCode`, `toString`, `getClass`, `clone`, and the Object monitor methods**. However, you must understand **each method with its exact semantics**:

- **`equals` compares identity by default**, not field values automatically.
- **`hashCode` must be consistent with logical equals** if value equality is defined; collisions can still occur.
- **`toString` helps with representation/debugging**, and is not by itself a stable identifier or serialization protocol.
- **`getClass` reflects the runtime class** and cannot be overridden.
- **`clone` relates to shallow copying and Cloneable**, and does not automatically deep-copy an object graph.
- **`wait/notify/notifyAll`** are monitor methods, require a proper lock/condition protocol, and differ from `Thread.sleep`.
- **`finalize` is a legacy/deprecated mechanism**, not to be used as a destructor; replace it with **`AutoCloseable` and try-with-resources**.

Understanding Object properly helps you use **inheritance, polymorphism, Java collections, records, memory semantics, and concurrency** solidly. However, do not make Object the default parameter type for every business method: **dedicated classes/interfaces express responsibilities and business contracts better**, while Object only provides the shared foundation of Java objects.
