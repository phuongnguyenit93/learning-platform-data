# Upcasting, Downcasting, `instanceof`, and `ClassCastException` in Java

## Learning Objectives

After this lesson, you can:

- Explain how the **static/declared type** (*compile-time type*) of a reference variable differs from the **actual type** (*runtime class*) of the object it references.
- Recognize **subtype/supertype** relationships through `extends` and `implements`, even when an object is viewed through a variable of a superclass or interface type.
- Use **upcasting** safely in assignments, parameter passing, and method returns, while understanding that this cast **does not create a new object**.
- Know when **downcasting** is needed to access subtype-specific members; distinguish between a **compile-time valid cast** and a **cast that actually succeeds at runtime**.
- Predict when the JVM throws `ClassCastException`; distinguish it from compile errors, `NullPointerException`, and `ArrayStoreException`.
- Write type checks using the `instanceof` operator and use **pattern matching for instanceof**, which is a standard feature in Java 17.
- Understand the scope (*flow scoping*) of a pattern variable, how `null` is handled, and combinations of `&&`, `!`, and `||` with branching conditions.
- Distinguish the effect of static type on **overloading/member lookup** from **dynamic dispatch** of overridden instance methods.
- Analyze interface casts, arrays, generics/type erasure, wrapper types, and the limitations preventing runtime checking of generic arguments.
- Choose **polymorphism, interface contracts, or visitor/strategy** designs when appropriate instead of overusing chains of `instanceof` followed by downcasting.
- Independently compile/run Java 17+ examples, inspect stdout, and fix common casting errors yourself.

## 1. Starting Point: One Object Can Be Viewed Through Multiple Types

Consider the inheritance tree:

~~~text
          Animal
          /    \
        Dog    Cat
~~~

A `Dog` object is a `Dog` and also satisfies the `Animal` type through inheritance. However, a `Cat` object is not a `Dog` just because they share the superclass Animal.

In Java:

~~~java
class Animal {
    void move() {
        System.out.println("animal moves");
    }
}

class Dog extends Animal {
    void bark() {
        System.out.println("woof");
    }
}

class Cat extends Animal {
    void meow() {
        System.out.println("meow");
    }
}
~~~

These are **illustrative declarations** that can be placed together in a suitable source file; there is no `main` yet.

Consider:

~~~java
Dog dog = new Dog();
Animal animal = dog;
~~~

- **Actual object:** a single object with runtime class `Dog`.
- **Variable `dog`:** has static type `Dog`.
- **Variable `animal`:** has static type `Animal`.
- **Reference value:** both variables can hold a reference to **the exact same Dog object**.

Diagram:

~~~text
dog: Dog  --------+
                 |
                 v
             [Dog object]
                 ^
                 |
animal: Animal --+
~~~

The line `Animal animal = dog;` **does not turn the Dog object into a new Animal object** and does not copy fields. It simply allows using the Dog reference through a variable with a broader static type.

### 1.1. Static Type and Runtime Type Answer Two Different Questions

**Static type** tells the compiler whether a member call is valid, which overloads are candidates, what cast checks are needed, and the result type of an expression.

**Runtime type** helps the JVM select the implementation of an overridden instance method and perform runtime safety checks when downcasting.

Therefore:

~~~java
Animal animal = new Dog();
animal.move(); // Allowed: Animal declares move().
// animal.bark(); // Does not compile: Animal does not have bark().
~~~

Even though the actual object is a Dog, the compiler does not allow `animal.bark()` because the expression `animal` has static type Animal and has no bark method in the corresponding API.

To call `bark`, you must ensure the real object is a Dog and express that with an appropriate check/cast.

## 2. Upcasting: From Subtype to Supertype

**Upcasting** is viewing a reference of a subtype through an appropriate supertype, such as `Dog` → `Animal` or `Dog` → an interface that Dog implements.

Example:

~~~java
Dog dog = new Dog();

Animal asAnimal = dog;  // Implicit upcasting.
Object asObject = dog;  // Dog is a subtype of Object.
~~~

This is a **widening reference conversion** in Java. For valid type relationships, an explicit cast is usually not necessary:

~~~java
Animal asAnimal = (Animal) dog; // Valid to write, but redundant.
~~~

A Dog object already fulfills the Animal contract, so this is a valid reference conversion.

### 2.1. Upcasting Occurs in Many Contexts

**Assignment:**

~~~java
Animal animal = new Dog();
~~~

**Parameter passing:**

~~~java
static void examine(Animal animal) {
    animal.move();
}

examine(new Dog());
~~~

**Returning from a method:**

~~~java
static Animal createAnimal() {
    return new Dog();
}
~~~

**Collection elements:**

~~~java
java.util.List<Animal> animals = new java.util.ArrayList<>();
animals.add(new Dog());
animals.add(new Cat());
~~~

The examples above are **illustrative snippets** that require appropriate `Animal`, `Dog`, and `Cat` declarations in the same context.

**Common point:** in the contexts listed above, a Dog/Cat instance can be used through an interface/superclass contract without recreating the object.

### 2.2. Upcasting Does Not Erase Specific Members

The Dog object can still hold its own state and the `bark()` method; the compiler only **limits the view through the Animal variable**. If a method takes an `Animal` and returns the same reference, or if the caller keeps the original Dog reference, the Dog's state does not disappear at all.

Do not say that “upcasting loses Dog's properties.” The accurate statement is that **the static type Animal does not expose Dog's specific members for direct calls**.

## 3. Runnable Program: Upcasting and Dynamic Dispatch

Save **`UpcastingDemo.java`**:

~~~java
public class UpcastingDemo {
    static class Animal {
        String sound() {
            return "unknown";
        }

        String category() {
            return "animal";
        }
    }

    static final class Dog extends Animal {
        @Override
        String sound() {
            return "woof";
        }

        void bark() {
            System.out.println("Dog.bark");
        }
    }

    static final class Cat extends Animal {
        @Override
        String sound() {
            return "meow";
        }
    }

    static void describe(Animal animal) {
        System.out.println(animal.category() + ":" + animal.sound());
    }

    public static void main(String[] args) {
        Dog dog = new Dog();

        Animal asAnimal = dog;
        Object asObject = dog;

        System.out.println("same Dog reference=" + (dog == asAnimal));
        System.out.println("same Object reference=" + (dog == asObject));
        System.out.println("sound=" + asAnimal.sound());

        describe(dog);
        describe(new Cat());

        dog.bark();
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac UpcastingDemo.java
java UpcastingDemo
~~~

**Exact stdout:**

~~~text
same Dog reference=true
same Object reference=true
sound=woof
animal:woof
animal:meow
Dog.bark
~~~

Explanation:

1. `dog`, `asAnimal`, and `asObject` all point to the same Dog object.
2. `asAnimal.sound()` is valid because Animal defines `sound()`; the runtime implementation is `Dog.sound()` thanks to **dynamic dispatch**.
3. `category()` is not overridden, so the Animal implementation returns `animal`.
4. `describe(Animal)` works with Dog or Cat without needing to downcast to know each subtype.
5. `dog.bark()` can be called because the variable `dog` has static type Dog.

**Key takeaway:** upcasting **does not break polymorphism**. On the contrary, using a common type to invoke overridden behavior is the classic case for polymorphism.

## 4. Downcasting: From a Wider Type to a Narrower Type

**Downcasting** is converting a reference viewed through a supertype back to a specific subtype:

~~~java
Animal animal = new Dog();
Dog dog = (Dog) animal;
dog.bark();
~~~

`(Dog) animal` is an explicit **narrowing reference conversion**. The compiler accepts it because `Animal` and `Dog` have a castable relationship, but whether the cast succeeds **depends on the runtime object**.

In this example, the runtime object is indeed a Dog, so the cast succeeds. If the runtime object were a Cat, casting to Dog would fail.

### 4.1. Downcasting Does Not “Transform the Object”

~~~java
Animal animal = new Dog();
Dog dog = (Dog) animal;
~~~

After the cast:

- `animal` still has static type Animal.
- `dog` has static type Dog.
- Both references still point to **the same Dog object**.
- No new Dog constructor is called.
- There is no copying of fields or conversion of data values.
- There is no such thing as a cast “turning a Cat into a Dog” or allocating a Dog object in place of a Cat.

A cast expression only **checks/interprets a reference as the target type**, if the language permits it.

### 4.2. Do Not Downcast Just to Access a Method

If a method is a shared behavior of Animal (such as `speak()`), declare it on Animal/interface and override it in subtypes. Then the caller uses `Animal.speak()` instead of `if (animal instanceof Dog) ... else ...`.

Downcasting is more appropriate when a behavior truly **exists only in the subtype** or at a runtime type inspection boundary (parser, framework, event handler), and you have decided to handle the non-subtype case explicitly.

## 5. Runnable Program: Successful and Failed Casts

Save **`DowncastingDemo.java`**:

~~~java
public class DowncastingDemo {
    static class Animal {
        String kind() {
            return "animal";
        }
    }

    static final class Dog extends Animal {
        void bark() {
            System.out.println("woof");
        }
    }

    static final class Cat extends Animal {
        void meow() {
            System.out.println("meow");
        }
    }

    public static void main(String[] args) {
        Animal first = new Dog();
        Dog dog = (Dog) first;

        System.out.println("successful cast=" + (dog == first));
        dog.bark();

        Animal second = new Cat();

        try {
            Dog impossible = (Dog) second;
            impossible.bark();
        } catch (ClassCastException expected) {
            System.out.println("Cat cannot be cast to Dog");
        }

        System.out.println("runtime kind=" + second.getClass().getSimpleName());
    }
}
~~~

Run:

~~~bash
javac DowncastingDemo.java
java DowncastingDemo
~~~

Output:

~~~text
successful cast=true
woof
Cat cannot be cast to Dog
runtime kind=Cat
~~~

**Explanation:**

- `first` has static type Animal, while its runtime class is Dog → casting to Dog succeeds.
- `second` has static type Animal, but its runtime class is Cat → casting to Dog fails with `ClassCastException`.
- The catch block demonstrates classifying the exception by **type**, not by relying on the verbatim exception message (messages can differ across JDKs).
- `second.getClass().getSimpleName()` returns the runtime class name Cat in this example.

**Do not** rely on `catch (ClassCastException)` for normal control flow when you can check the type beforehand. Exceptions should represent abnormal errors or contract violations; later sections will use `instanceof`.

## 6. Static Type Allowing a Cast Does Not Guarantee a Compatible Runtime Object

Scenario:

~~~java
Animal animal = new Cat();
Dog dog = (Dog) animal; // Compiles; throws ClassCastException at runtime.
~~~

The compiler sees that **Animal can reference a Dog**, so the cast can be valid when writing code. However, the runtime value actually points to a Cat.

**Two verification steps must be clearly separated:**

1. **Compile-time compatibility:** Does Java allow the source and target types to have a possible reference conversion under its rules?
2. **Runtime cast check:** Is the specific object an instance of the target type or a compatible subtype?

Any failure at step 1 is a **compile-time error**; a failure at step 2 of an explicit reference cast is typically a `ClassCastException`.

### 6.1. Some Casts Are Incompatible at Compile Time

~~~java
String name = "Lan";
// Integer invalid = (Integer) name; // Cannot cast between final classes
//                                  // String and Integer have no compatible relationship.
~~~

This is an illustrative snippet with the invalid line commented out. The compiler can immediately reject impossible casts between unrelated concrete class types.

However:

~~~java
Object unknown = "Lan";
// Integer value = (Integer) unknown; // Compiles, but fails at runtime.
~~~

The compiler only sees that `Object` can hold an Integer, so the cast `(Integer) unknown` can compile. The actual runtime object is a String, so executing that line throws `ClassCastException`.

**Not every cast between two unrelated interfaces is blocked at compile time.** A class can implement multiple interfaces, so there are casts to another interface that the compiler allows, yet runtime still has to check the object.

## 7. What Is `ClassCastException`?

`java.lang.ClassCastException` is an unchecked exception belonging to the hierarchy:

~~~text
Throwable
  |
Exception
  |
RuntimeException
  |
ClassCastException
~~~

It is thrown when a runtime reference conversion attempts to treat an object as a type that it **is not**.

Key points to remember:

- Valid upcasting does not throw `ClassCastException`.
- Downcasting performs a runtime check; if incompatible, it can throw `ClassCastException`.
- Casting `null` to any valid reference type **does not throw** `ClassCastException`; null remains null.
- Calling a method on null can throw `NullPointerException`; this is a different error.
- Primitive casts such as `(int) 3.9` are **numeric conversions**, not runtime reference casts, and do not throw `ClassCastException` because the number is rounded.
- Storing an element into a runtime array with a narrower component type can throw `ArrayStoreException`, which is different from `ClassCastException`.

### 7.1. Exception Messages Are Not a Fixed Output Contract

In many JVMs, the error message contains the source name, target name, module, or class loader. You should not design logic around parsing text from `ClassCastException.getMessage()`. Rely on the exception's **type** and fix the invalid data source or contract.

For illustrative tests, you can print `expected.getClass().getSimpleName()`; the `ClassCastException` result is more stable than printing the entire stack trace.

### 7.2. A Casting Error May Indicate a Design Flaw

For example, if the caller always has to write:

~~~java
Dog dog = (Dog) service.getAnimal();
~~~

When the `getAnimal()` method can return a Cat, that is a sign of an unclear contract. Options:

- Have the method return type `Dog` if the result is guaranteed to always be a Dog.
- Have the method return `Optional<Dog>` when a Dog may not exist.
- Have the method return `Animal` and let the caller use a polymorphic API.
- Classify with `instanceof` and handle other branches intentionally.

A cast should not replace documentation or API invariants.

## 8. `instanceof`: Checking Whether an Object Belongs to a Type

The traditional `instanceof` operator:

~~~java
if (animal instanceof Dog) {
    Dog dog = (Dog) animal;
    dog.bark();
}
~~~

The expression `animal instanceof Dog` returns `true` when the runtime object is non-null and has a type compatible with Dog under Java rules; otherwise it returns `false`.

Key points:

- The check is based on the **runtime object**, not just the variable's type.
- A subclass of Dog can also satisfy `instanceof Dog` if Dog is not final.
- An object can satisfy **multiple** `instanceof` checks: subclass, superclass, and implemented interfaces.
- `null instanceof Dog` is **false**, without throwing an exception.
- In Java 17, `instanceof` also supports a **type pattern** to both check the type and create a pattern variable.

### 8.1. Traditional Style Program

Save **`TraditionalInstanceofDemo.java`**:

~~~java
public class TraditionalInstanceofDemo {
    static class Animal {
    }

    static final class Dog extends Animal {
        void bark() {
            System.out.println("woof");
        }
    }

    static final class Cat extends Animal {
    }

    static void inspect(Animal animal) {
        if (animal instanceof Dog) {
            Dog dog = (Dog) animal;
            dog.bark();
        } else if (animal instanceof Cat) {
            System.out.println("cat detected");
        } else {
            System.out.println("other or null");
        }
    }

    public static void main(String[] args) {
        inspect(new Dog());
        inspect(new Cat());
        inspect(null);
        inspect(new Animal());
    }
}
~~~

Run:

~~~bash
javac TraditionalInstanceofDemo.java
java TraditionalInstanceofDemo
~~~

Output:

~~~text
woof
cat detected
other or null
other or null
~~~

`instanceof` has confirmed Dog before the cast, so the cast in the same branch on an unchanged value can succeed. However, a separate check far away from the cast site in code with state/concurrency can make reasoning more complex, so keep the check and its use close together.

### 8.2. When Does the Check Return False?

`instanceof` returns false if:

- The reference variable holds `null`.
- The runtime object belongs to a type incompatible with the type test.
- The object does not implement the tested interface.

Do not use `instanceof` as a check on an object's contents (for example, valid balance or properly formatted email); it only answers a question about **type relationships**.

## 9. Pattern Matching for `instanceof` in Java 17

Java 17 provides standard support for the syntax:

~~~java
if (animal instanceof Dog dog) {
    dog.bark();
}
~~~

`Dog dog` is a **type pattern**. When the check succeeds, the variable `dog` has static type Dog and references the same object as `animal`. There is no need for another explicit cast.

**This is not** declaring a new Dog object: the pattern variable only **holds the reference bound after the type test succeeds**.

### 9.1. Complete Java 17 Program

Save **`PatternInstanceofDemo.java`**:

~~~java
public class PatternInstanceofDemo {
    interface Pet {
        String name();
    }

    static final class Dog implements Pet {
        private final String name;

        Dog(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }

        String bark() {
            return "woof";
        }
    }

    static final class Cat implements Pet {
        private final String name;

        Cat(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }

        String meow() {
            return "meow";
        }
    }

    static void describe(Pet pet) {
        if (pet instanceof Dog dog) {
            System.out.println("dog " + dog.name() + ": " + dog.bark());
        } else if (pet instanceof Cat cat) {
            System.out.println("cat " + cat.name() + ": " + cat.meow());
        } else {
            System.out.println("unknown pet");
        }
    }

    public static void main(String[] args) {
        describe(new Dog("Milo"));
        describe(new Cat("Luna"));
        describe(null);
    }
}
~~~

Compile/run:

~~~bash
javac PatternInstanceofDemo.java
java PatternInstanceofDemo
~~~

Output:

~~~text
dog Milo: woof
cat Luna: meow
unknown pet
~~~

Explanation:

- `pet` has static type Pet; the Dog/Cat implementations satisfy the interface.
- `pet instanceof Dog dog` checks the runtime object and then brings the pattern variable `dog` into the proper scope of the true branch.
- Within that branch, the compiler knows `dog` is a Dog, so it can call `bark()`.
- `pet == null` makes both type tests false, falling into the final branch without throwing an NPE.
- If a third Pet kind is added later, the current method prints `unknown pet`; that is the contract chosen in the example, and it does not automatically support new behavior.

### 9.2. Java 17 Pattern Matching Differs from Pattern Switch

**Pattern matching for `instanceof` is a standard feature in Java 17.** Do not confuse it with **pattern matching for switch** in later Java releases; pattern switch was previously in preview and has rules that vary by version.

To keep the README compiling with Java 17 `javac` **without preview enabled**, all examples use pattern `instanceof` rather than relying on pattern switch syntax such as `case Dog d ->`.

## 10. Pattern Variable Scope: Flow Scoping

A pattern variable does not have method-wide scope just because its name appears in an `instanceof`. The compiler analyzes **which control-flow paths guarantee that the pattern matched**.

Example:

~~~java
if (value instanceof String text) {
    System.out.println(text.length());
}
// System.out.println(text); // Invalid here: text is out of scope.
~~~

This is an illustrative snippet: `value` has static type Object or another suitable type. In the true branch, `text` exists with type String; after a normal if, there is no guarantee that the pattern matched.

### 10.1. Combining with `&&`

If an expression:

~~~java
if (value instanceof String text && text.length() >= 3) {
    System.out.println(text.toUpperCase());
}
~~~

then `text` can be used on the right-hand side of `&&` because the right-hand side is evaluated only when the left-hand side is true and the pattern has matched.

**In contrast:**

~~~java
// if (value instanceof String text || text.isBlank()) {
//     ...
// }
~~~

is an **invalid** example when using `text` on the right-hand side of `||`: the right-hand side executes when the left-hand side is false, at which point the pattern variable is not validly assigned/bound.

### 10.2. `!` and Early Return

A Java 17 idiom:

~~~java
static int requireLength(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("String required");
    }
    return text.length();
}
~~~

Because the non-matching branch completes abnormally via `throw`, after the if statement the compiler knows `text` has matched. A `return` in the non-matching branch also typically creates a similar flow-scoping condition.

**Do not infer that any negated if makes a pattern variable stay in scope indefinitely**: the compiler must prove that all paths reaching the point of use have matched.

## 11. Runnable Program: Flow Scoping and Guarded Conditions

Save **`PatternFlowScopeDemo.java`**:

~~~java
public class PatternFlowScopeDemo {
    static void printLongName(Object value) {
        if (value instanceof String text && text.length() >= 4) {
            System.out.println("long=" + text.toUpperCase());
        } else {
            System.out.println("not long string");
        }
    }

    static int requireLength(Object value) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("String required");
        }
        return text.length();
    }

    public static void main(String[] args) {
        printLongName("Java");
        printLongName("Go");
        printLongName(42);
        printLongName(null);

        System.out.println("length=" + requireLength("Learn"));

        try {
            requireLength(10);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid type rejected");
        }
    }
}
~~~

Run:

~~~bash
javac PatternFlowScopeDemo.java
java PatternFlowScopeDemo
~~~

Output:

~~~text
long=JAVA
not long string
not long string
not long string
length=5
invalid type rejected
~~~

In `value instanceof String text && text.length() >= 4`, the right-hand side uses `text` only when it has matched. In `requireLength`, the negated branch throws an exception before reaching `return text.length()` if the input is not a String.

This is a more concise and safer way to write than the traditional pattern: `instanceof String` followed by `(String) value`.

### 11.1. When a Pattern Is Considered Always True Due to the Static Type

In Java 17, certain type patterns are rejected by the compiler if **the static type of the expression is already a subtype of the pattern type**, making the check redundant/meaningless under language rules. For example:

~~~java
String text = "Java";
// if (text instanceof String value) { } // Compile-time error
// in Java 17: the expression is already a subtype of the pattern type.
~~~

Do not automatically convert every legacy `instanceof` into a pattern where it is unnecessary. If the variable already has type String and you only want to check for null, use `text != null`.

## 12. `null` with `instanceof` and Casts

`null` does not point to any object. The expressions have different semantics:

~~~java
Object unknown = null;

boolean isString = unknown instanceof String; // false.
String text = (String) unknown;                 // null; no CCE.
// text.length();                              // NPE on dereference.
~~~

**There is no actual object to check for subtyping**, so `instanceof` returns false. However, casting a null reference to a permitted reference type is valid and the result remains null.

### 12.1. Program Determining Each Case

Save **`NullCastingDemo.java`**:

~~~java
public class NullCastingDemo {
    public static void main(String[] args) {
        Object unknown = null;

        System.out.println("is String=" + (unknown instanceof String));

        String text = (String) unknown;
        System.out.println("cast is null=" + (text == null));

        try {
            System.out.println(text.length());
        } catch (NullPointerException expected) {
            System.out.println("null dereference rejected");
        }
    }
}
~~~

Run:

~~~bash
javac NullCastingDemo.java
java NullCastingDemo
~~~

Output:

~~~text
is String=false
cast is null=true
null dereference rejected
~~~

**Distinguish the conclusions:**

- `unknown instanceof String` does not throw NPE.
- `(String) unknown` does not throw CCE when unknown is null.
- `text.length()` throws NPE because it dereferences null.

If an API does not allow null, use an explicit precondition, such as `Objects.requireNonNull`, instead of using a cast as if the cast also checks for non-null.

## 13. Upcasting Through Interfaces and Downcasting to Implementations

A class can implement multiple interfaces:

~~~java
interface Printable {
    void print();
}

interface Scannable {
    void scan();
}

class MultifunctionDevice implements Printable, Scannable {
    public void print() { }
    public void scan() { }
}
~~~

A `MultifunctionDevice` object can be upcast to `Printable` or `Scannable`. When the caller holds only `Printable`, the compiler allows only the methods that Printable exposes (plus inherited Object methods according to the rules). To call `scan()`, the caller can check whether it is Scannable:

~~~java
if (printable instanceof Scannable scanner) {
    scanner.scan();
}
~~~

An object can simultaneously satisfy **two interfaces that have no extends relationship with each other**. This is why you cannot simply conclude that “for two different interfaces, casting between them is always invalid.”

### 13.1. Runnable Example of Interface Cross-Casting

Save **`InterfaceCastingDemo.java`**:

~~~java
public class InterfaceCastingDemo {
    interface Printable {
        void print();
    }

    interface Scannable {
        void scan();
    }

    static final class Device implements Printable, Scannable {
        public void print() {
            System.out.println("print");
        }

        public void scan() {
            System.out.println("scan");
        }
    }

    static final class PrinterOnly implements Printable {
        public void print() {
            System.out.println("printer only");
        }
    }

    static void inspect(Printable printer) {
        printer.print();
        if (printer instanceof Scannable scanner) {
            scanner.scan();
        } else {
            System.out.println("scan unavailable");
        }
    }

    public static void main(String[] args) {
        Printable both = new Device();
        Printable justPrinter = new PrinterOnly();

        inspect(both);
        inspect(justPrinter);

        System.out.println("both implements Scannable=" +
                (both instanceof Scannable));
    }
}
~~~

Run:

~~~bash
javac InterfaceCastingDemo.java
java InterfaceCastingDemo
~~~

Output:

~~~text
print
scan
printer only
scan unavailable
both implements Scannable=true
~~~

The `inspect` method does not assume that **every Printable is Scannable**. If the runtime printer is a Device, the pattern-matching branch yields a scanner. If it is a PrinterOnly, the method explains that the feature is unavailable.

**Practical design:** If every Printer in a use case is required to have scanning capability, the chosen interface may be too broad. In that case, define an appropriate contract instead of checking at runtime on every call.

## 14. Overloading Selects by Static Type; Overriding Selects at Runtime

This is a common pitfall when learning casting and polymorphism.

**Overloading**: multiple methods with the same name but different parameter lists. Java selects the valid call based on **compile-time types**, applicability rules, and overload resolution.

**Overriding**: a subclass provides an implementation of the **same instance method signature**. When invoked through an object, runtime can select the corresponding override.

### 14.1. Program Demonstrating the Difference

Save **`OverloadOverrideCastDemo.java`**:

~~~java
public class OverloadOverrideCastDemo {
    static class Animal {
        String speak() {
            return "animal";
        }
    }

    static final class Dog extends Animal {
        @Override
        String speak() {
            return "dog";
        }

        void fetch() {
            System.out.println("fetch");
        }
    }

    static void inspect(Animal animal) {
        System.out.println("overload Animal");
    }

    static void inspect(Dog dog) {
        System.out.println("overload Dog");
    }

    public static void main(String[] args) {
        Dog dog = new Dog();
        Animal animal = dog;

        inspect(dog);
        inspect(animal);

        System.out.println("runtime speak=" + animal.speak());
        inspect((Dog) animal);

        ((Dog) animal).fetch();
    }
}
~~~

Compile/run:

~~~bash
javac OverloadOverrideCastDemo.java
java OverloadOverrideCastDemo
~~~

Output:

~~~text
overload Dog
overload Animal
runtime speak=dog
overload Dog
fetch
~~~

- `inspect(dog)` selects the Dog overload because the expression dog has type Dog.
- `inspect(animal)` selects the Animal overload because the expression animal has **static type Animal**, even though the runtime object is a Dog.
- `animal.speak()` selects the Dog override due to dynamic dispatch of instance methods.
- `inspect((Dog) animal)` selects the Dog overload because **the static type of the cast expression** is Dog; the runtime cast succeeds because the actual object is a Dog.
- If animal actually pointed to a Cat, the cast `(Dog) animal` would throw CCE before calling the Dog overload.

**Do not think** the JVM uses the runtime type to pick all overloads according to “the method best matching the actual object.” Java overload resolution takes place at compile time.

## 15. How Do `getClass()`, `instanceof`, and `Class.isInstance` Differ?

Distinguish between:

- `obj instanceof Animal`: true for an Animal object **or a compatible subclass**; null gives false.
- `obj.getClass() == Animal.class`: checks for the **exact runtime class Animal**, not a subclass. Calling `getClass()` on null throws NPE.
- `Animal.class.isInstance(obj)`: performs a runtime membership check similar to `instanceof Animal` for the appropriate class type, and returns false for null.
- `Animal.class.isAssignableFrom(Dog.class)`: returns true if there is a type relationship allowing a Dog instance to be assigned to a variable of type Animal; uses **two Class objects** instead of an object instance.

### 15.1. Runnable Program

Save **`RuntimeTypeCheckDemo.java`**:

~~~java
public class RuntimeTypeCheckDemo {
    static class Animal {
    }

    static final class Dog extends Animal {
    }

    public static void main(String[] args) {
        Object value = new Dog();

        System.out.println("Animal instanceof=" + (value instanceof Animal));
        System.out.println("Dog instanceof=" + (value instanceof Dog));
        System.out.println("exact Animal=" +
                (value.getClass() == Animal.class));
        System.out.println("exact Dog=" +
                (value.getClass() == Dog.class));

        System.out.println("Animal.isInstance=" +
                Animal.class.isInstance(value));
        System.out.println("Animal assignable from Dog=" +
                Animal.class.isAssignableFrom(Dog.class));
        System.out.println("Dog assignable from Animal=" +
                Dog.class.isAssignableFrom(Animal.class));
        System.out.println("null isInstance=" +
                Animal.class.isInstance(null));
    }
}
~~~

Commands:

~~~bash
javac RuntimeTypeCheckDemo.java
java RuntimeTypeCheckDemo
~~~

Output:

~~~text
Animal instanceof=true
Dog instanceof=true
exact Animal=false
exact Dog=true
Animal.isInstance=true
Animal assignable from Dog=true
Dog assignable from Animal=false
null isInstance=false
~~~

**When to use which?**

- `instanceof`: usually appropriate when checking whether an object belongs to a subtype/interface in code where the type is written directly.
- `getClass() == ...`: when you truly need the **exact runtime class** (for example, a specific equality contract), without accepting subclasses.
- `Class.isInstance`: useful when the type is selected as a `Class<?>` value at runtime.
- `Class.isAssignableFrom`: checks the relationship between two type descriptors; the direction **supertype.isAssignableFrom(subtype)** is very easy to write backward.

### 15.2. `Class.cast`

The `Class<T>.cast(Object)` API provides a runtime-checked cast via a `Class<T>` object. It throws `ClassCastException` when the object is incompatible, and can return null when the input is null.

~~~java
Class<Dog> type = Dog.class;
Object unknown = new Dog();
Dog dog = type.cast(unknown);
~~~

This is an illustrative snippet using a suitable Dog class. It is useful for generic APIs accepting `Class<T>`, but it does **not** mean the `Class.cast` method is safe for every runtime object; CCE still occurs if the caller passes the wrong object.

## 16. Java Generics and Type Erasure: Not All Type Parameters Can Be Checked

Something that seems reasonable but is **invalid in Java 17**:

~~~java
Object value = java.util.List.of("A");
// if (value instanceof java.util.List<String> strings) { }
// Invalid: List<String> is not reifiable for this type test.
~~~

Generic type arguments such as `String` generally undergo **type erasure** at runtime. Therefore, you cannot use `instanceof List<String>` to verify that the entire list contains Strings.

**Valid:**

~~~java
if (value instanceof java.util.List<?> items) {
    System.out.println("size=" + items.size());
}
~~~

`List<?>` is a valid type pattern for the runtime kind of the collection. However, it **only proves that the object is a List**, not that all elements are Strings.

### 16.1. The Unchecked Cast Pitfall

Suppose an `Object` actually holds a `List<Integer>`:

~~~java
Object unknown = java.util.List.of(42);
@SuppressWarnings("unchecked")
java.util.List<String> texts = (java.util.List<String>) unknown;
~~~

The cast can succeed at runtime as a cast to raw List due to erasure, but reading an element as a String can throw `ClassCastException` when the compiler-inserted cast at the element retrieval site executes.

### 16.2. Program Demonstrating Delayed Runtime Failure

Save **`GenericCastErasureDemo.java`**:

~~~java
import java.util.List;

public class GenericCastErasureDemo {
    public static void main(String[] args) {
        Object source = List.of(42);

        if (source instanceof List<?> list) {
            System.out.println("list size=" + list.size());

            @SuppressWarnings("unchecked")
            List<String> wrong = (List<String>) source;

            System.out.println("casted list size=" + wrong.size());

            try {
                String text = wrong.get(0);
                System.out.println("text=" + text);
            } catch (ClassCastException expected) {
                System.out.println("element cast failed");
            }
        }
    }
}
~~~

Run:

~~~bash
javac GenericCastErasureDemo.java
java GenericCastErasureDemo
~~~

Output:

~~~text
list size=1
casted list size=1
element cast failed
~~~

**What to understand:**

- The runtime object is a List containing an Integer.
- `instanceof List<?>` only knows that it is a List.
- The unchecked cast to `List<String>` does not verify individual elements at cast time.
- When `wrong.get(0)` is used in a context expecting a String, the runtime checks the element and encounters an Integer → `ClassCastException`.

**Do not treat `@SuppressWarnings("unchecked")` as a fix for data type errors.** The annotation only suppresses a warning intentionally; the program can still fail. Prefer designing APIs that use generic types consistently throughout, avoiding raw types and unchecked casts.

### 16.3. Generics Invariance

Even though Dog extends Animal, `List<Dog>` is **not** a subtype of `List<Animal>`:

~~~java
java.util.List<Dog> dogs = new java.util.ArrayList<>();
// java.util.List<Animal> animals = dogs; // Compile-time error.
~~~

If such an assignment were allowed, a caller could add a Cat to a list originally intended only for Dogs. Java generics use **invariance** for regular type parameters; to read via a supertype, you can use a wildcard:

~~~java
java.util.List<? extends Animal> animals = dogs;
~~~

However, that restricts adding arbitrary Animals to the list. This is a different mechanism from upcasting **a single Dog object** to Animal, and you should not try to downcast a List to bypass the check.

## 17. Array Covariance and `ArrayStoreException`

Arrays of reference types in Java have **covariance**: `Dog[]` can be viewed as `Animal[]`. However, the JVM still retains the runtime component type of the array.

If a caller tries to place a Cat into an array that is actually a `Dog[]` through an `Animal[]` variable, runtime throws `ArrayStoreException`.

### 17.1. Runnable Program

Save **`ArrayCovarianceDemo.java`**:

~~~java
public class ArrayCovarianceDemo {
    static class Animal {
    }

    static final class Dog extends Animal {
    }

    static final class Cat extends Animal {
    }

    public static void main(String[] args) {
        Dog[] dogs = new Dog[2];
        Animal[] animals = dogs;

        animals[0] = new Dog();
        System.out.println("stored Dog=" +
                (animals[0] instanceof Dog));

        try {
            animals[1] = new Cat();
        } catch (ArrayStoreException expected) {
            System.out.println("Cat cannot enter Dog[]");
        }

        System.out.println("array length=" + animals.length);
    }
}
~~~

Run:

~~~bash
javac ArrayCovarianceDemo.java
java ArrayCovarianceDemo
~~~

Output:

~~~text
stored Dog=true
Cat cannot enter Dog[]
array length=2
~~~

**Do not confuse the two errors:**

- `ClassCastException`: casting an object reference to an incompatible type.
- `ArrayStoreException`: attempting to **store an element** whose runtime class is incompatible with the runtime component type of the reference array.

With generics, `List<Dog>` does not allow assignment to `List<Animal>`, so this kind of error from adding a Cat is prevented earlier at compile time.

### 17.2. `instanceof` with Arrays

A `Dog[]` object is also a compatible `Animal[]` and `Object`. You can use a type test for arrays:

~~~java
Object array = new Dog[2];

boolean isAnimalArray = array instanceof Animal[];
boolean isDogArray = array instanceof Dog[];
~~~

Both return true in the example. **Do not infer** that every array element is non-null or initialized. Elements of a reference array default to null until assigned.

## 18. Numeric Casting and Wrapper Types Are Not Class Hierarchy Downcasting

Compare two kinds of conversions:

~~~java
double fraction = 3.9;
int roundedTowardZero = (int) fraction; // 3.
~~~

This is a **narrowing primitive conversion**: it changes the numeric representation and discards the fractional part according to Java rules (within appropriate bounds). There is no object reference cast and no `ClassCastException` is thrown.

Meanwhile:

~~~java
Object number = Integer.valueOf(7);
// Long wrong = (Long) number; // Runtime ClassCastException.
~~~

`Integer` and `Long` are two different wrapper classes; an Integer object does not turn into a Long object through a reference cast.

If you need to convert numeric content from `Number` to a wider type, use an appropriate **numeric value** conversion API.

### 18.1. Runnable Program Distinguishing Conversions

Save **`NumericVsReferenceCastDemo.java`**:

~~~java
public class NumericVsReferenceCastDemo {
    public static void main(String[] args) {
        double decimal = 3.9;
        int integral = (int) decimal;

        System.out.println("primitive cast=" + integral);

        Object boxed = Integer.valueOf(7);
        Number numeric = (Number) boxed;

        System.out.println("long value=" + numeric.longValue());

        try {
            Long wrong = (Long) boxed;
            System.out.println(wrong);
        } catch (ClassCastException expected) {
            System.out.println("Integer is not Long");
        }
    }
}
~~~

Run:

~~~bash
javac NumericVsReferenceCastDemo.java
java NumericVsReferenceCastDemo
~~~

Output:

~~~text
primitive cast=3
long value=7
Integer is not Long
~~~

**Note:** `Number.longValue()` extracts the numeric value according to the corresponding subtype's rules. For excessively large numbers, floating-point values, or custom types, the conversion can lose data/precision; `Number.longValue()` is not by itself a numeric conversion that preserves every value.

### 18.2. Do Not Confuse Boxing with Reference Casting

~~~java
int value = 7;
Integer boxed = value; // Autoboxing.
Object object = boxed; // Reference upcasting.
~~~

If you want to obtain `int`:

~~~java
int back = (Integer) object; // Downcast Object -> Integer, then unboxing.
~~~

The two steps happen through different mechanisms. If object is null, unboxing can throw `NullPointerException`. If object is a Long, the reference cast to Integer can throw CCE first.

## 19. Good Design: Use Polymorphism Instead of Cast Chains When Appropriate

A less extensible design:

~~~java
static double shippingFee(Delivery delivery) {
    if (delivery instanceof BikeDelivery) {
        return 10;
    }
    if (delivery instanceof TruckDelivery) {
        return 50;
    }
    throw new IllegalArgumentException("unsupported delivery");
}
~~~

This is an **illustrative snippet** that requires actual types. If every time you add a new delivery method you have to edit a series of `instanceof` branches, branching logic becomes scattered and cases are easily missed.

You can place the behavior on the contract:

~~~java
interface Delivery {
    int fee();
}
~~~

Implementations provide `fee()` themselves, and the caller uses `delivery.fee()` without needing to know the runtime subtype.

### 19.1. Program Using Polymorphism

Save **`PolymorphismInsteadOfCastDemo.java`**:

~~~java
public class PolymorphismInsteadOfCastDemo {
    interface Delivery {
        String name();
        int fee();
    }

    static final class Bike implements Delivery {
        public String name() {
            return "bike";
        }

        public int fee() {
            return 10;
        }
    }

    static final class Truck implements Delivery {
        public String name() {
            return "truck";
        }

        public int fee() {
            return 50;
        }
    }

    static void quote(Delivery delivery) {
        System.out.println(delivery.name() + "=" + delivery.fee());
    }

    public static void main(String[] args) {
        quote(new Bike());
        quote(new Truck());
    }
}
~~~

Run:

~~~bash
javac PolymorphismInsteadOfCastDemo.java
java PolymorphismInsteadOfCastDemo
~~~

Output:

~~~text
bike=10
truck=50
~~~

When adding a new Delivery subtype, it must implement the `name()` and `fee()` contract. The caller does not need to add `instanceof NewDelivery` just to compute the basic fee.

**However, polymorphism does not replace every type test:** if you are working with a plugin system, optional capabilities, or framework data where subtype-specific behavior genuinely differs, runtime checking with `instanceof` can be appropriate. The goal is **clear design rationale**, not forbidding casting.

## 20. Using `instanceof` with `sealed` Types (Java 17)

Java 17 standardizes **sealed classes/interfaces**, restricting the allowed set of subclasses/implementers at the declaration level. When a model belongs to a closed set of cases, code sometimes needs to dispatch by subtype.

Example:

~~~java
sealed interface Result permits Success, Failure {
}

record Success(String value) implements Result {
}

record Failure(String message) implements Result {
}
~~~

This is illustrative code that needs to be placed into a valid file/package. In Java 17, you can use `if (result instanceof Success success)`/`else if (...)` to handle each kind. **Do not use pattern switch as a standard non-preview feature of Java 17**, because its syntax and stability status differ across versions.

### 20.1. Program Handling a Closed Subtype Set

Save **`SealedInstanceofDemo.java`**:

~~~java
public class SealedInstanceofDemo {
    sealed interface Result permits Success, Failure {
    }

    record Success(String value) implements Result {
    }

    record Failure(String message) implements Result {
    }

    static String describe(Result result) {
        if (result instanceof Success success) {
            return "ok=" + success.value();
        }
        if (result instanceof Failure failure) {
            return "error=" + failure.message();
        }
        return "missing";
    }

    public static void main(String[] args) {
        System.out.println(describe(new Success("42")));
        System.out.println(describe(new Failure("timeout")));
        System.out.println(describe(null));
    }
}
~~~

Run:

~~~bash
javac SealedInstanceofDemo.java
java SealedInstanceofDemo
~~~

Output:

~~~text
ok=42
error=timeout
missing
~~~

With `Result` sealed, direct permitted implementations are controlled by the language; however, `null` still does not match either pattern, so the method chooses `missing`.

When changing the set of subtypes in another version of the API, review the branching code. A sealed hierarchy can help design a clearer type domain, but it does not automatically prove that every `if`/`else` handles exhaustive cases in Java 17.

## 21. Casts the Compiler Allows That Easily Fail at Runtime

Compare the following cases:

| Expression | Compiles? | Runtime if executed | Why |
| --- | --- | --- | --- |
| `Animal a = new Dog();` | Yes | Succeeds | Widening reference |
| `Dog d = (Dog) a;` with a pointing to Dog | Yes | Succeeds | Actual object is Dog |
| `Dog d = (Dog) a;` with a pointing to Cat | Yes | `ClassCastException` | Actual object is not Dog |
| `Object o = "hello"; Integer i = (Integer) o;` | Yes | `ClassCastException` | Runtime String is not Integer |
| Direct cast `String` → `Integer` | No, in the case of unrelated final classes | Does not run | Compile-time inconvertible types |
| `String s = (String) null;` | Yes | `s == null` | Casting null does not throw CCE |
| `o instanceof Dog` with o null | Yes, when the type test is valid | false | Null is not an instance |
| `Animal[] a = new Dog[1];` | Yes | Succeeds | Reference array covariance |
| `a[0] = new Cat();` when runtime array is Dog[] | Yes | `ArrayStoreException` | Component type mismatch |
| `List<String> l = (List<String>) o;` when o holds List<Integer> | Can compile with an unchecked warning | Can throw CCE when retrieving a String element | Type erasure |
| `int i = (int) 3.9;` | Yes | i equals 3 | Numeric conversion, not a reference cast |

The table assumes appropriate Animal/Dog/Cat/List declarations and a valid access context. Do not combine all snippets into a single file with duplicate identifiers.

## 22. What Conditions Does a “Safe Cast” Actually Require?

If you want to obtain a subtype:

~~~java
if (value instanceof Dog dog) {
    dog.bark();
}
~~~

then:

1. `value` has a static type compatible with a type test for Dog.
2. If the runtime object is a Dog or a suitable subtype, the pattern matches.
3. The pattern variable `dog` is used only on control-flow paths where the compiler knows it matched.
4. Calling `bark()` must also have valid visibility and method signature.
5. If `value` is null or another subtype, the branch does not execute.
6. There is no **copy** or **class conversion** of the actual object.

### 22.1. Beware of Fields That Can Change Between Check and Cast

Example:

~~~java
if (holder.value instanceof Dog) {
    Dog dog = (Dog) holder.value;
}
~~~

This is an illustrative snippet requiring an appropriate Holder/value. If `holder.value` is a mutable field and can be modified between the two reads (by another thread or another side effect), the result of the first check does not guarantee that the subsequent cast sees the same reference.

Safer and more readable:

~~~java
Animal snapshot = holder.value;
if (snapshot instanceof Dog dog) {
    dog.bark();
}
~~~

Assume value has type Animal. The pattern checks and binds **the same snapshot reference value**. However, if the Dog object has mutable state, pattern matching **does not automatically lock or synchronize state**; thread safety is a separate concern.

### 22.2. `instanceof` Does Not Check Invariants

Even when `value instanceof BankAccount` is true, that does not guarantee a valid balance, that the account is active, or that the object is thread-safe. The type is part of the contract, whereas state conditions must be checked through business APIs.

## 23. Should You Cast When the Caller Already Knows the Subtype?

If a method accepts:

~~~java
static void handleDog(Dog dog) {
    dog.bark();
}
~~~

then there is **no need** to upcast to Animal and then downcast back to Dog. If your API always accepts Dog, declare Dog in the parameter/return type.

Conversely, if a method needs to accept any Animal:

~~~java
static void handleAnimal(Animal animal) {
    System.out.println(animal.sound());
}
~~~

use the common contract. Casting should be used **when there is a runtime-type reason**, not as a substitute for choosing an accurate type signature.

### 23.1. Design Choices by Need

| Need | Option to consider |
| --- | --- |
| Same behavior across all subtypes | Method in superclass/interface + override |
| Dependency with a swappable implementation | Composition via interface/strategy |
| Handling different event types with distinct behaviors | Type pattern `instanceof` with an explicit fallback |
| API guarantees Dog | Parameter/return type Dog |
| API may not find a Dog | `Optional<Dog>` or an appropriate result type |
| Homogeneous generic collection | `List<Dog>`, preserving type information throughout |
| Handling a closed type graph | Sealed hierarchy + type tests/polymorphism per Java version |
| Framework accepting `Class<T>` | `Class.cast`, `Class.isInstance` with runtime checks |
| Object with optional capability | Appropriate interface type test and no-capability handling |

## 24. Common Mistakes When Learning Casting

| Misconception | Fact |
| --- | --- |
| “Upcasting creates a new Animal object.” | It only copies/interprets the reference under the supertype. |
| “Dog turns into Animal, so it loses bark().” | The runtime object is still Dog; static type Animal does not allow calling bark directly. |
| “If a cast compiles, it is guaranteed to succeed at runtime.” | Downcasting performs a runtime check and can throw CCE. |
| “`(Dog) new Cat()` is a way to turn a Cat into a Dog.” | No. The types are incompatible; a cast does not construct a new object. |
| “`instanceof` checks the variable name.” | It checks the runtime object against a type. |
| “`null instanceof Dog` throws NPE.” | False. |
| “Casting null to Dog causes CCE.” | It is valid and results in null, if the cast type is valid. |
| “A pattern variable has method-wide scope.” | It is flow-scoped, only where the compiler proves a match. |
| “`&&` and `||` work the same way for pattern variables.” | `&&` guarantees matching on the right-hand side; `||` has no such guarantee. |
| “`@Override` is a cast.” | No; it marks a compile-time override check. |
| “Overloading selects by runtime class.” | Overload selection uses compile-time types. |
| “Overridden methods are chosen by variable type.” | Dynamic dispatch can select the implementation by runtime class. |
| “`getClass()==Animal.class` and `instanceof Animal` are identical.” | Exact class vs subtype relationship. |
| “`List<Dog>` is a subtype of `List<Animal>`.” | Generics are generally invariant. |
| “`instanceof List<String>` checks each element.” | Invalid for non-reifiable generic parameters. |
| “An unchecked cast List<Integer>→List<String> validates elements.” | No; reading elements can cause CCE later. |
| “Since `Animal[]` holds Dog[], you can add a Cat.” | The JVM checks the runtime component type, which can throw ArrayStoreException. |
| “Cast an Integer object to Long to convert the number.” | Reference casts do not convert wrapper objects; use a number conversion API. |
| “Casting `double` to `int` throws CCE if the fractional part is lost.” | Numeric casts follow numeric rules and do not throw CCE. |
| “ClassCastException always has a fixed message.” | Do not rely on the message/stack trace in test logic. |
| “Using instanceof makes all state thread-safe.” | A type test does not protect mutable state. |
| “An instanceof chain is always good polymorphism.” | It can be a sign that behavior should be moved into an interface/subtype. |

## 25. Checklist for Reading a Java Snippet with a Cast

Before accepting `(Dog) value`, ask yourself:

1. **What is the static type of `value`?** Why does the caller only have the supertype?
2. **Which runtime objects can appear?** Dog, Cat, null, or another implementation?
3. **Is the cast valid at the language/compile-time level?**
4. **What guarantees the actual runtime object is a Dog?** API invariant, type pattern, or class token?
5. **If it is the wrong subtype, what is the expected contract?** Ignore, return Optional, report an error, or throw an exception?
6. **Is the downcast actually necessary?** Can a common polymorphic method be called instead?
7. **Does the cast create a new object?** No; do not expect state to be converted.
8. **Is `instanceof Dog dog` used to keep the type test and reference together?**
9. **Is the pattern variable still in scope at the point of use?**
10. **Are null and valid state checked?**
11. **Are there overloads causing the compiler to select a different method than you expected?**
12. **If it is a generic collection, does the cast produce an unchecked warning?**
13. **If it is an array, what is the runtime component type?**
14. **If it is a wrapper, do you need to convert a numeric value or cast the object type?**
15. **If references are mutable fields, do the check and cast use the same snapshot?**
16. **Are there tests with at least Dog, Cat, null, and a potential future subtype?**

## 26. Self-Check Questions and Answers

**Question 1.** How many objects does `Dog dog = new Dog(); Animal animal = dog;` create?  
**Answer:** One Dog object, with two references pointing to the same object.

**Question 2.** Does `Animal animal = new Dog(); animal.bark();` compile if only Dog declares bark?  
**Answer:** No. Static type Animal does not expose bark().

**Question 3.** Can `animal.sound()` run Dog.sound when Animal declares sound and Dog overrides it?  
**Answer:** Yes. This is dynamic dispatch.

**Question 4.** When does `Dog d = (Dog) animal;` succeed?  
**Answer:** When the runtime value is null or references an object compatible with Dog (with null, the cast returns null); for a non-null Animal pointing to Dog or a subtype, it succeeds.

**Question 5.** If animal is a Cat at runtime but the code casts to Dog, what happens?  
**Answer:** `ClassCastException` at runtime if the cast is permitted by the compiler.

**Question 6.** Does the compiler always reject `(Dog) animal` because Animal is wider than Dog?  
**Answer:** No. A narrowing reference cast can be valid at compile time and checked at runtime.

**Question 7.** What does `null instanceof Dog` evaluate to?  
**Answer:** `false`.

**Question 8.** Does `Dog dog = (Dog) null;` throw CCE?  
**Answer:** No. dog receives null.

**Question 9.** What error does `dog.bark()` cause when dog is null?  
**Answer:** `NullPointerException`, because it invokes an instance method on null.

**Question 10.** Does `if (value instanceof Dog dog)` create a new Dog?  
**Answer:** No, the pattern variable holds the matched reference.

**Question 11.** Why is `value instanceof String text && text.length()>3` valid?  
**Answer:** Short-circuit `&&` runs the right-hand side only after the pattern has matched.

**Question 12.** Why is `value instanceof String text || text.isBlank()` invalid?  
**Answer:** The right-hand side executes when the left-hand side is false, and text has not been bound by the pattern.

**Question 13.** Does Java 17 require `--enable-preview` for `instanceof Dog dog`?  
**Answer:** No. Pattern matching for instanceof is already a standard feature.

**Question 14.** Two interfaces Printable and Scannable do not extend each other; can one object satisfy both?  
**Answer:** Yes, a class can implement both.

**Question 15.** When does `Object o = "hello"; Integer x = (Integer) o;` fail?  
**Answer:** At runtime with `ClassCastException` because the actual object is a String.

**Question 16.** Is a direct cast between String and Integer allowed in the case of unrelated final classes?  
**Answer:** No; the compiler can determine that they are inconvertible types.

**Question 17.** When both overloads exist, does `Animal a = new Dog(); inspect(a)` choose the Animal or Dog overload?  
**Answer:** It chooses Animal based on the static type of argument a.

**Question 18.** Which implementation does `a.speak()` choose when a has static type Animal and runtime type Dog?  
**Answer:** Dog.speak if it is a valid override.

**Question 19.** Are `a.getClass()==Animal.class` and `a instanceof Animal` the same when a is a Dog at runtime?  
**Answer:** No: exact class comparison is false, while instanceof Animal is true.

**Question 20.** What does `Animal.class.isAssignableFrom(Dog.class)` return?  
**Answer:** `true` because Dog is a compatible subtype of Animal.

**Question 21.** Can `List<Dog>` be assigned to `List<Animal>`?  
**Answer:** No, due to generic invariance.

**Question 22.** Can `value instanceof List<String>` be used to verify String elements?  
**Answer:** No; generic type arguments are not reifiable at runtime for this type test.

**Question 23.** Does an unchecked cast from List<Integer> to List<String> necessarily throw CCE immediately?  
**Answer:** No. Due to erasure, the error can occur later when retrieving an Integer to use as a String.

**Question 24.** What does `Animal[] animals = new Dog[1]; animals[0]=new Cat();` throw?  
**Answer:** `ArrayStoreException` if the runtime array is Dog[].

**Question 25.** Does `int i=(int)3.9;` throw ClassCastException?  
**Answer:** No; this is a numeric conversion, resulting in 3.

**Question 26.** Does `Object o=Integer.valueOf(7); Long l=(Long)o;` convert Integer to Long?  
**Answer:** No; it throws CCE. To obtain a long value, use `((Number)o).longValue()` when appropriate.

**Question 27.** Should `instanceof` be used to check for a valid bank balance?  
**Answer:** It is not sufficient. `instanceof` checks only the type, not business invariants.

**Question 28.** When multiple subtypes all have `fee()`, should you write an instanceof chain or a common interface?  
**Answer:** Usually prefer an interface/superclass method and polymorphism if the behavior belongs to a shared contract.

**Question 29.** Does pattern `instanceof` make an object thread-safe?  
**Answer:** No. Runtime type checking does not synchronize mutable state.

**Question 30.** What is the most important thing when downcasting?  
**Answer:** **The runtime object must be compatible with the target type**, not merely that the compiler accepts the cast syntax.

## 27. References

- Java Language Specification (Java SE 17), [`4.10 — Subtyping](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10): subtype/supertype relationships.
- Java Language Specification, [`5.1.5 — Widening Reference Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.5): upcasting and widening reference conversions.
- Java Language Specification, [`5.1.6 — Narrowing Reference Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.6): downcasting.
- Java Language Specification, [`5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5): conversions in casts.
- Java Language Specification, [`15.16 — Cast Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.16): syntax and semantics of cast expressions.
- Java Language Specification, [`15.20.2 — Type Comparison Operator `instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): type tests and patterns.
- Java Language Specification, [`14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30): Java 17 pattern matching.
- Java Language Specification, [`6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): pattern-variable flow scoping.
- Java Language Specification, [`15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): overload resolution and runtime invocation.
- Java Language Specification, [`4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): type test limitations with generics.
- Java Language Specification, [`10.5 — Array Store Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5): runtime component type checks.
- Java Platform API, [`ClassCastException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassCastException.html): casting exception.
- Java Platform API, [`Class.isInstance](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isInstance(java.lang.Object)): runtime type test via class token.
- Java Platform API, [`Class.cast](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#cast(java.lang.Object)): cast via class token.

## Conclusion

**Upcasting** allows a subtype reference to be used safely through a superclass/interface without creating a new object. **Downcasting** recovers a specific subtype view, but must satisfy **runtime object compatibility**; if the actual object does not have a compatible type, Java can throw `ClassCastException`.

Remember that the **static type** determines which members the compiler allows to be used and which overload is selected, while the **runtime type** determines the overridden instance method implementation and the results of type checks. `instanceof`, especially **type patterns in Java 17**, helps check the runtime type before using subtype-specific behavior. Null does not match `instanceof`, whereas a null reference can be cast, though dereferencing it can throw NPE.

For collections, type erasure means unchecked generic casts do not prove the types of individual elements; for arrays, covariance can defer errors to runtime as `ArrayStoreException`. When multiple subtypes perform a shared behavior, **prefer polymorphism** over long chains of downcasts. Only downcast when there is a clear contract and reason, handling incompatible-type branches proactively.
