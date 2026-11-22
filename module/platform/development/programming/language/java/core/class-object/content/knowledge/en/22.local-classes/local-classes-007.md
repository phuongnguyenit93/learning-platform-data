# Local enums and local records are implicitly static in Java

## Learning objectives

By the end of this lesson, you will be able to:

- Declare **local enums** and **local records** inside a method body, constructor, or valid block in Java 17.
- Explain accurately the term **implicitly `static`** for these two types: they **are not inner classes**, do not receive an implicit enclosing instance, and do not automatically capture local variables, parameters, or type parameters of the enclosing method.
- Distinguish them from a **local normal class** (a local class declared with `class`), which is an inner class and can use `final`/effectively final local variables as well as the enclosing instance when language conditions permit.
- Understand the apparent paradox: defined **inside a block** yet still **implicitly static**; `static` here refers to the relationship with the enclosing environment, and **does not** make all members or instances of the enum/record static.
- Understand the rule of **not writing the explicit `static` keyword** on a local enum/local record declaration, and not adding the access modifiers `public`/`protected`/`private` to the local type declaration itself.
- Know when you can use static members of the enclosing class, and when you must **pass data explicitly** into a record constructor or enum method.
- Utilize record components, compact constructors, validation, accessors, `equals`/`hashCode`/`toString`, as well as enum constants, constructors, methods, `switch`, and `values()` within a local scope.
- Understand the scope boundaries of a type name, the stability of enum constants across method calls, and the difference between object identity and value equality.
- Use a local record as an immutable data carrier carefully: a `final` component field **does not make** a nested mutable array/list deeply immutable.
- Analyze common compile-time errors, fix designs, and write standalone Java 17+ programs with reliable stdout.

> **Version:** This lesson uses Java 17 or later. Local records became a standard feature in Java 16 (JEP 395). Java 17 allows declaring local enums, local records, and local interfaces inside a block according to the Java SE 17 specification. Source snippets that intentionally demonstrate errors will be commented out or explicitly marked as **not a standalone compilable program**.

## 1. What is a local type?

A *local type declaration* resides **directly inside a block**, not as a member of a class or package. For example, inside `main`, you can declare:

~~~java
public class Example {
    public static void main(String[] args) {
        enum Mode {
            FAST, SAFE
        }

        record Point(int x, int y) {
        }

        Mode mode = Mode.FAST;
        Point point = new Point(2, 3);
        System.out.println(mode);
        System.out.println(point);
    }
}
~~~

The two types `Mode` and `Point` only have names **usable within the scope of that block**, though the Java compiler still compiles them into appropriate class files. `Mode.FAST` is an enum constant; `new Point(2,3)` is a record object. A local type name cannot be used arbitrarily from elsewhere like a package-level or member type.

### 1.1. “Local” refers to the declaration scope

- `Mode` is declared inside the method block.
- `Point` is also declared inside that block.
- Source code in another method cannot write `new Example.Point(2,3)` because Point **is not a member class of Example**.
- A local type has a **simple name** in scope (`Point`, `Mode`); it differs from an anonymous class, which has no programmer-declared type name.
- Scope and shadowing follow JLS `6.3/`6.4, and local class/interface declarations follow JLS `14.3.

### 1.2. “Implicitly static” refers to the enclosing context

Implicitly `static` **does not** mean that the local record itself cannot have instances, instance methods, or fields. It means:

1. Local enums/records are nested types belonging to the category that **are not inner classes**.
2. They **do not have an enclosing instance of the surrounding class** provided automatically.
3. They **do not have implicit access** to local variables, parameters, instance fields/methods, and type variables of the enclosing method/class the way a local normal class can.
4. They can work with static members that have appropriate accessibility, and can receive **explicit values/references** via constructor or method parameters.

This is precisely the intended meaning of the lesson title: **local in position**, yet **static in its relationship to an enclosing instance and capture**.

## 2. First program: declaring a local enum and a local record

Save **`LocalTypesFirstDemo.java`**:

~~~java
public class LocalTypesFirstDemo {
    public static void main(String[] args) {
        enum Level {
            LOW, MEDIUM, HIGH
        }

        record Score(String name, int points) {
            boolean passed() {
                return points >= 60;
            }
        }

        Level selected = Level.MEDIUM;
        Score lan = new Score("Lan", 75);
        Score minh = new Score("Minh", 45);

        System.out.println("level=" + selected);
        System.out.println("lan=" + lan);
        System.out.println("lan passed=" + lan.passed());
        System.out.println("minh passed=" + minh.passed());
    }
}
~~~

Run:

~~~bash
javac LocalTypesFirstDemo.java
java LocalTypesFirstDemo
~~~

**Stdout:**

~~~text
level=MEDIUM
lan=Score[name=Lan, points=75]
lan passed=true
minh passed=false
~~~

**Read carefully:**

- `Level` and `Score` are defined **inside the method**, not as fields or member classes of `LocalTypesFirstDemo`.
- The enum has three **constants**. Using `Level.MEDIUM` does not require `new Level()`.
- The record has two **components**: `String name` and `int points`. Java 17 generates a canonical constructor, component accessors `name()`/`points()`, `equals`, `hashCode`, and `toString`.
- `passed()` is an **instance method of the record**, which is completely valid even though a local record is implicitly static.
- There is no implicit reference to a `LocalTypesFirstDemo` instance, and since `main` is a static method, it does not have `this` either.

## 3. Four commonly confused kinds of local declarations

In Java 17, a block can contain several forms of type declarations.

| Declaration in block | Inner class? | Implicitly static? | Capture effectively final local? | Has implicit enclosing outer instance? |
| --- | --- | --- | --- | --- |
| Normal `class Local { }` | Yes | No | Yes, under specified conditions | May have one from an instance context |
| `enum LocalEnum { A }` | No | **Yes** | **No** | **No** |
| `record LocalRecord(int x) { }` | No | **Yes** | **No** | **No** |
| `interface LocalInterface { ... }` | No | **Yes** | **No** | **No** |

**Table note:** a local normal class can capture effectively final local variables; whether it has an enclosing instance of an outer class depends on **whether it is declared in an instance or static context**. In a static method, there is no `this` instance of the outer class to capture.

### 3.1. A local normal class is not a local record

~~~java
void process(int input) {
    int bonus = 10;

    class LocalCalculator {
        int calculate() {
            return input + bonus;
        }
    }

    // record LocalResult(int value) {
    //     int calculate() { return input + bonus; } // Wrong.
    // }
}
~~~

`LocalCalculator` can use `input` and `bonus` because they are effectively final. The local record `LocalResult` cannot directly access them that way because a record is implicitly static.

**Fix:** obtain the value from a component **explicitly passed** to the record in the constructor, for example `new LocalResult(input + bonus)`.

### 3.2. Why not view a record as a “local class with lots of generated code”?

A record provides a value-oriented state representation along with automatically generated methods, yet also has **static nesting constraints** and **does not capture enclosing locals**. Converting `class Local` into `record Local(...)` can change syntax, API, inheritance, mutability, and the ability to access method variables.

## 4. Local enums and local records do not write `static` explicitly

**Correct:**

~~~java
void demo() {
    enum Mode { FAST, SAFE }
    record Point(int x, int y) { }
}
~~~

**Incorrect when they are local declarations in a block:**

~~~java
void invalid() {
    // static enum Mode { FAST, SAFE } // Compile-time error.
    // static record Point(int x, int y) { } // Compile-time error.
}
~~~

JLS `14.3 prohibits the `static` modifier from appearing **explicitly** on local class/interface declarations, even when the type is already **implicitly static**. The access modifiers `public`, `protected`, and `private` also cannot be applied to **the local declaration itself**.

Do not infer that “implicitly static” means “allowed or required to write `static`”. For a **member record/enum** declared in the body of Outer, the member rules differ; here the topic is **local**.

### 4.1. Location and syntax differ from member enums/records

~~~java
class Outer {
    enum MemberMode { A, B }
    record MemberPoint(int x, int y) { }

    void method() {
        enum LocalMode { C, D }
        record LocalPoint(int x, int y) { }
    }
}
~~~

- `Outer.MemberMode` and `Outer.MemberPoint` are **member types**.
- `LocalMode` and `LocalPoint` are **local types** of the method block; outside the method they cannot be accessed via `Outer.LocalMode` or `Outer.LocalPoint`.
- Both **member** enums/records and **local** enums/records are nested static in semantics, but the way **their names are accessed** differs.

## 5. Program: local normal class with capture, local record receiving data

Save **`LocalCaptureContrastDemo.java`**:

~~~java
public class LocalCaptureContrastDemo {
    public static void main(String[] args) {
        int base = 10; // Effectively final.

        class Adder {
            int add(int value) {
                return base + value;
            }
        }

        record Sum(int left, int right) {
            int value() {
                return left + right;
            }
        }

        Adder adder = new Adder();
        Sum sum = new Sum(base, 5);

        System.out.println("class result=" + adder.add(5));
        System.out.println("record result=" + sum.value());
        System.out.println("record left=" + sum.left());
    }
}
~~~

Run:

~~~bash
javac LocalCaptureContrastDemo.java
java LocalCaptureContrastDemo
~~~

Output:

~~~text
class result=15
record result=15
record left=10
~~~

In `Adder.add`, `base` is a **captured local variable** of the enclosing method. Because Java captures only final/effectively final locals by rule, `base` is not reassigned afterward in the example.

In `Sum.value`, `left` and `right` are **record component fields**. The line `new Sum(base,5)` passes the **value** of base into the constructor. The record does not capture the variable `base` by secretly storing an enclosing frame/owner.

### 5.1. What if base changes?

If you add:

~~~java
// base++;
~~~

after declaring the local class `Adder` that references `base`, the method can be rejected by the compiler because the variable is no longer effectively final. That is the rule for **capture of a local normal class**; a local record that opts to receive data via its constructor is not subject to that same kind of capture.

If you want to compute with mutable state, design **what data enters the constructor/method at what time**, rather than expecting a local record to read enclosing method variables directly.

## 6. A local record has no `Outer.this`

A local record declared inside an instance method of `Outer` is still **not an inner class** and has no implicit enclosing Outer instance.

~~~java
class Outer {
    private int multiplier = 3;

    void run(int amount) {
        // record Result(int number) {
        //     int multiplied() {
        //         return multiplier * number; // Wrong: implicit instance field.
        //     }
        // }

        record Result(int number, int multiplier) {
            int multiplied() {
                return multiplier * number;
            }
        }

        System.out.println(new Result(amount, multiplier).multiplied());
    }
}
~~~

The right approach is to **make the required state a component** `multiplier`, and then instantiate it with `new Result(amount, multiplier)` inside the method. The instance method `run` itself has access to read Outer's `multiplier`; the local record on its own only knows the component passed to it.

### 6.1. Do not use `Outer.this` to bypass the constraint

In the instance method code of a local normal class, `Outer.this` can be a valid qualified-this. However, inside a local record body, there is no enclosing Outer instance for `Outer.this` to reference. To make a record method work with Outer, pass an Outer reference explicitly into the method/constructor; at the same time, consider lifetime/ownership and the deep immutability of the record.

## 7. Program: record uses only passed data

Save **`RecordOuterAccessDemo.java`**:

~~~java
public class RecordOuterAccessDemo {
    private final int multiplier;

    public RecordOuterAccessDemo(int multiplier) {
        this.multiplier = multiplier;
    }

    int calculate(int amount) {
        record Calculation(int amount, int multiplier) {
            int result() {
                return amount * multiplier;
            }
        }

        Calculation value = new Calculation(amount, multiplier);
        return value.result();
    }

    public static void main(String[] args) {
        RecordOuterAccessDemo service = new RecordOuterAccessDemo(4);

        System.out.println("first=" + service.calculate(3));
        System.out.println("second=" + service.calculate(5));
    }
}
~~~

Run:

~~~bash
javac RecordOuterAccessDemo.java
java RecordOuterAccessDemo
~~~

Output:

~~~text
first=12
second=20
~~~

- `calculate` has `this` as a `RecordOuterAccessDemo` instance and is allowed to read the `multiplier` field.
- The local record `Calculation` does not implicitly hold the service instance.
- `Calculation.result()` only reads `amount` and `multiplier` from the record object itself.
- If business logic needs access to the live service inside the record, you can pass the service reference explicitly, though in that case the record holds a reference to the service; do not assume it will avoid all ownership/memory issues.

## 8. Local enums do not capture local variables either

An enum defined inside a block is still an **enum type** with fixed constants. It does not receive the enclosing method frame/locals the way a local normal class does.

**Wrong:**

~~~java
void invalid(int threshold) {
    // enum Decision {
    //     ACCEPT;
    //
    //     boolean allowed(int n) {
    //         return n >= threshold; // Wrong: threshold from outer method.
    //     }
    // }
}
~~~

**Correct:** have the enum's method receive threshold **explicitly**:

~~~java
void valid(int threshold) {
    enum Decision {
        ACCEPT;

        boolean allowed(int n, int limit) {
            return n >= limit;
        }
    }

    System.out.println(Decision.ACCEPT.allowed(10, threshold));
}
~~~

The snippets above are illustrated inside an appropriate enclosing class; they **do not have their own main method**.

### 8.1. Enum constant constructors differ from record constructors

Enum constants are declared inside the enum body itself, for example `LOW(5)`/`HIGH(10)`, along with internal private constructors. Callers **do not** use `new LocalEnum(...)`.

A record is different: a caller can write `new LocalRecord(componentValues...)` from the right scope/type access. The corresponding instantiation syntax **does not affect** the fact that both are implicitly static.

## 9. Program: passing method arguments to a local enum

Save **`LocalEnumMethodDemo.java`**:

~~~java
public class LocalEnumMethodDemo {
    static void demonstrate(int input, int limit) {
        enum Rule {
            AT_LEAST {
                boolean test(int value, int bound) {
                    return value >= bound;
                }
            },
            ABOVE {
                boolean test(int value, int bound) {
                    return value > bound;
                }
            };

            abstract boolean test(int value, int bound);
        }

        System.out.println("at least=" +
                Rule.AT_LEAST.test(input, limit));
        System.out.println("above=" +
                Rule.ABOVE.test(input, limit));
    }

    public static void main(String[] args) {
        demonstrate(10, 10);
        demonstrate(11, 10);
    }
}
~~~

Run:

~~~bash
javac LocalEnumMethodDemo.java
java LocalEnumMethodDemo
~~~

Output:

~~~text
at least=true
above=false
at least=true
above=true
~~~

`Rule` does not directly read `input` or `limit` from the `demonstrate` method. Instead, both are **explicit method arguments** in `test(input,limit)`. Enum constants with class bodies provide their own implementation for `test`; that is enum constant polymorphism, not capture.

### 9.1. Why not declare a static local enum to resolve a capture error?

Because a local enum is already implicitly static, writing `static enum Rule` in addition is a compile-time error. The right solution is to **change the data flow**, not add a modifier.

## 10. Static members of Outer are still accessible

Suppose an enclosing class has a static constant or static method:

~~~java
class Outer {
    private static final int SCALE = 2;

    void example() {
        record Measure(int value) {
            int scaled() {
                return value * SCALE;
            }
        }

        System.out.println(new Measure(3).scaled());
    }
}
~~~

Because `SCALE` is a static member, the local record can access it when accessibility permits. This **does not** create an enclosing Outer instance. If `SCALE` were an instance field, the same source expression inside the record body would not be allowed implicit access.

Similarly, a local enum can reference static members of the enclosing class according to name resolution/access rules.

**Caution:** static **mutable** fields can change between calls; “implicitly static” does not guarantee that logic depending on static mutable state is thread-safe or side-effect-free.

## 11. Program: local enum and record reading static fields

Save **`LocalStaticContextDemo.java`**:

~~~java
public class LocalStaticContextDemo {
    private static final String PREFIX = "APP";
    private static final int BONUS = 5;

    void show(int points) {
        enum Category {
            NORMAL, BONUS
        }

        record Entry(int points) {
            String label() {
                return PREFIX + ":" + points;
            }

            int withBonus() {
                return points + BONUS;
            }
        }

        Entry entry = new Entry(points);
        Category category = Category.BONUS;

        System.out.println("category=" + category);
        System.out.println("label=" + entry.label());
        System.out.println("total=" + entry.withBonus());
    }

    public static void main(String[] args) {
        new LocalStaticContextDemo().show(10);
    }
}
~~~

Run:

~~~bash
javac LocalStaticContextDemo.java
java LocalStaticContextDemo
~~~

Output:

~~~text
category=BONUS
label=APP:10
total=15
~~~

In `Entry.label()`, `PREFIX` is a **static field of the enclosing class**. `BONUS` is also static. It is not that `Entry` captures `this` or implicitly passes a `LocalStaticContextDemo` object into the constructor.

### 11.1. The difference between a static field and a local constant

A local variable written as `final int limit=5;` inside an enclosing method **remains a local variable**; it does not become a static field just because its value is a compile-time constant. Local enums/records **do not capture local variables**, including local final constants. Do not mix up these two concepts.

## 12. Method type parameters: cannot be used implicitly inside a local record

For example, a generic method:

~~~java
<T> void method(T input) {
    // record Bad(T value) { } // Wrong: T belongs to the outer generic method.

    record Box<U>(U value) { } // Correct: U is a type parameter of Box.

    Box<T> box = new Box<>(input); // T is used in the outer method code.
    System.out.println(box.value());
}
~~~

Why?

- `T` is declared by the method `method`.
- Because a local record is implicitly static, **the record's body/signature cannot directly use the type variable T** of the enclosing method.
- `Box<U>` declares its own type parameter `U`, which is completely valid.
- Outside the local record declaration but still inside `method`, `T` is in scope, so `Box<T> box = ...` can be used.
- The data `input` is **explicitly passed** to the constructor, not captured.

Similarly, a local enum cannot reference an enclosing generic method type parameter. An enum itself **cannot declare type parameters** such as `enum Mode<T>`.

### 12.1. What about a generic Outer<T>?

If the method resides in `class Outer<T>`, a local record/enum cannot directly use `T` from generic Outer inside its type declaration just because the code is inside the class. If you want generic data, the local record can declare its own `record Data<U>(U value)` and instantiate `Data<T>` outside.

## 13. Program: generic local record declaring its own type parameter

Save **`GenericLocalRecordDemo.java`**:

~~~java
public class GenericLocalRecordDemo {
    static <T> void display(T input) {
        record Box<U>(U value) {
            String describe() {
                return String.valueOf(value);
            }
        }

        Box<T> box = new Box<>(input);
        System.out.println("boxed=" + box.describe());
    }

    public static void main(String[] args) {
        display("Java");
        display(17);
    }
}
~~~

Run:

~~~bash
javac GenericLocalRecordDemo.java
java GenericLocalRecordDemo
~~~

Output:

~~~text
boxed=Java
boxed=17
~~~

`U` belongs to the record. `T` is only used where **`Box<T>` is instantiated** inside the generic method body. This is how to preserve type safety without breaking its implicitly static nature.

### 13.1. Comparison with a local normal class

A local normal class inside a generic method can use an enclosing type parameter according to valid language rules, whereas a local enum/record cannot rely on the enclosing generic context like that. When migrating code from a local class to a local record, check both **captured variables** and **type parameters**.

## 14. Enum constants are named instances and cannot be created with `new` from outside

Local enum:

~~~java
enum Direction {
    NORTH, SOUTH, EAST, WEST
}
~~~

Usage:

~~~java
Direction north = Direction.NORTH;
Direction parsed = Direction.valueOf("SOUTH");
Direction[] choices = Direction.values();
~~~

- `Direction.NORTH` is an enum constant that exists for the lifecycle of the enum class.
- Callers do not write `new Direction()`.
- `Direction.values()` creates an array representing the constants at the time of the call; modifying the returned array does not change the enum's internal set of constants.
- `valueOf` is case-sensitive with respect to the constant name and does not automatically normalize input.
- A `switch` expression on the enum works normally within the scope.

### 14.1. Local scope does not create a new set of enum constants on each method call

The word “local” only indicates where the type name is declared. It does not mean that each method call defines a **new type** of enum or recreates new constants per invocation. Enum constants are members of the enum class, and the class is loaded/initialized by the JVM according to the classloader lifecycle.

This differs from `new Record(...)`: each `new` creates a regular new record object.

## 15. Program: enum constants across multiple method calls

Save **`LocalEnumIdentityDemo.java`**:

~~~java
public class LocalEnumIdentityDemo {
    static Object token() {
        enum Token {
            SINGLE
        }
        return Token.SINGLE;
    }

    static Object value(int number) {
        record Number(int number) {
        }
        return new Number(number);
    }

    public static void main(String[] args) {
        Object a = token();
        Object b = token();

        Object first = value(7);
        Object second = value(7);

        System.out.println("same enum constant=" + (a == b));
        System.out.println("same record object=" + (first == second));
        System.out.println("equal record value=" +
                first.equals(second));
    }
}
~~~

Run:

~~~bash
javac LocalEnumIdentityDemo.java
java LocalEnumIdentityDemo
~~~

Output:

~~~text
same enum constant=true
same record object=false
equal record value=true
~~~

`Token` has local scope, yet `SINGLE` is the same enum constant across calls. `Number` is a fixed local record type with respect to its declaration, whereas each `new Number(7)` creates a distinct object; the `equals` generated by the record compares the number component value and therefore returns true.

Using `==` with enum constants is a valid idiom for comparing identity. For record value objects, you normally use `equals` when you want to compare values, not `==`.

## 16. A local enum can have its own constructors and instance members

“Implicitly static” does not prevent a local enum from declaring **instance fields**, **constructors**, or **instance methods**. Static status describes the outer relation; it does not prevent enum instances from having their own state.

Example of a strategy enum with two rates:

~~~java
enum Rate {
    STANDARD(10),
    REDUCED(5);

    private final int percent;

    Rate(int percent) {
        this.percent = percent;
    }

    int percent() {
        return percent;
    }
}
~~~

This is a snippet that should be placed **inside a valid method/block**. The enum constructor cannot be invoked with `new Rate(10)` from callers; `STANDARD(10)` and `REDUCED(5)` declare the arguments for the constants in the enum body.

### 16.1. Why can you not use a method variable as an enum constructor argument?

A local enum cannot capture method parameters. Writing `STANDARD(rateFromOuterMethod)` inside the enum declaration attempts to access an enclosing local, which is an error. If the rate depends on runtime values, an enum method can accept the rate or return a strategy applied to the input; or choose a record if each object needs a different value.

## 17. Program: local enum with its own constructor

Save **`LocalEnumPolicyDemo.java`**:

~~~java
public class LocalEnumPolicyDemo {
    static void calculate(int price) {
        enum Rate {
            STANDARD(10),
            REDUCED(5);

            private final int percent;

            Rate(int percent) {
                this.percent = percent;
            }

            int taxed(int amount) {
                return amount + amount * percent / 100;
            }

            int percent() {
                return percent;
            }
        }

        System.out.println("standard percent=" +
                Rate.STANDARD.percent());
        System.out.println("standard total=" +
                Rate.STANDARD.taxed(price));
        System.out.println("reduced total=" +
                Rate.REDUCED.taxed(price));
    }

    public static void main(String[] args) {
        calculate(200);
    }
}
~~~

Run:

~~~bash
javac LocalEnumPolicyDemo.java
java LocalEnumPolicyDemo
~~~

Output:

~~~text
standard percent=10
standard total=220
reduced total=210
~~~

The enum field `percent` belongs to the enum constant instances. `price` belongs to the enclosing method and only enters the enum method via `taxed(price)`. The `percent` values are supplied by the enum declarations, not by local capture.

This is a simplified integer model; taxes/money in real systems require appropriate rounding rules, precision, currency, and overflow handling.

## 18. A local record can have constructor validation and methods

A record typically represents **unchanging data according to its component API**. For a local record:

~~~java
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
    }

    int length() {
        return end - start + 1;
    }
}
~~~

- `start` and `end` are components and corresponding final fields.
- The compact constructor `Range { ... }` validates values before the object is fully constructed.
- `length()` is an instance method, valid inside an implicitly static record.
- You cannot declare additional **instance fields** that are not record components due to Java record restrictions.
- You cannot write `extends SomeBase` because a record semantically extends `java.lang.Record`; a record can `implements` interfaces.

Do not confuse the ability to have methods/compact constructors with permission to use outer local variables. Those methods only have validly supplied state (components/parameters/static data).

## 19. Program: validation of a local record

Save **`LocalRecordValidationDemo.java`**:

~~~java
public class LocalRecordValidationDemo {
    public static void main(String[] args) {
        record Range(int start, int end) {
            Range {
                if (start > end) {
                    throw new IllegalArgumentException(
                            "start must be <= end");
                }
            }

            int length() {
                return end - start + 1;
            }
        }

        Range a = new Range(2, 5);
        System.out.println("range=" + a);
        System.out.println("length=" + a.length());

        try {
            new Range(8, 3);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid range rejected");
        }
    }
}
~~~

Run:

~~~bash
javac LocalRecordValidationDemo.java
java LocalRecordValidationDemo
~~~

Output:

~~~text
range=Range[start=2, end=5]
length=4
invalid range rejected
~~~

Constructor validation in a local record works the same as the record mechanism in general. Because the exception is caught with a custom-printed message, stdout does not depend on the stack trace/exception message.

**Note:** `length()` carries an overflow risk if extreme values are used; the example intentionally uses small ints. Production code should choose types/arithmetic checks appropriate for the domain.

## 20. Auto-generated `equals`, `hashCode`, and `toString` in a local record

A record provides value-oriented methods based on its component fields. For example:

~~~java
record Key(String name, int version) {
}
~~~

Two different Key instances can return true for `equals` if their components are equal; the `hashCode` contract requires that when objects are equal, their hash codes are equal.

This is one reason a local record is useful for creating **intermediate data** inside a method instead of manually writing a boilerplate-heavy local normal class.

However, **records are not automatically deeply immutable**. If a component is `int[]`, the accessor returns the array reference unless overridden, the array is mutable, and the default generated equality does not compare array contents like `Arrays.equals`. You need to choose the representation and defensive copying.

### 20.1. Program: equality by components

Save **`LocalRecordEqualityDemo.java`**:

~~~java
public class LocalRecordEqualityDemo {
    public static void main(String[] args) {
        record Key(String name, int version) {
        }

        Key a = new Key("A", 1);
        Key b = new Key("A", 1);
        Key c = new Key("A", 2);

        System.out.println("same object=" + (a == b));
        System.out.println("equal values=" + a.equals(b));
        System.out.println("equal hashes=" +
                (a.hashCode() == b.hashCode()));
        System.out.println("different version=" + a.equals(c));
        System.out.println("text=" + a);
    }
}
~~~

Run:

~~~bash
javac LocalRecordEqualityDemo.java
java LocalRecordEqualityDemo
~~~

Output:

~~~text
same object=false
equal values=true
equal hashes=true
different version=false
text=Key[name=A, version=1]
~~~

If you need a value snapshot to use as a key in a `HashMap`, a local record with **immutable component values** is a concise choice. However, if the key contains a mutable component, equality/hash codes may change or exhibit unexpected array identity semantics.

## 21. Why does static context not mean deep immutability?

A local record is implicitly static, yet can still hold a reference to mutable data if **passed explicitly**:

~~~java
void demo(int[] source) {
    record Payload(int[] data) {
    }

    Payload payload = new Payload(source);
    source[0] = 9;
    // payload.data()[0] also observes 9.
}
~~~

`Payload` does not capture `source` implicitly; the record constructor received the `source` reference **explicitly**. The final `data` field only prevents reassigning the reference inside the object according to the rules; it does not lock the elements of the array.

The takeaway: **not capturing the outer context** and **holding a mutable reference as a component** are two different things. Implicit static is not a “deep freeze” mechanism.

### 21.1. How to make a sufficiently deep immutable snapshot for `int[]`

~~~java
record Frozen(int[] values) {
    Frozen {
        values = values.clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }
}
~~~

You should still consider custom `equals`/`hashCode` if you want array content-value semantics, because record-generated methods do not automatically call `Arrays.equals` for array components. A simpler case is often to use an immutable List of immutable elements when the contract permits.

## 22. Program: local record with defensive copies

Save **`LocalRecordArrayDemo.java`**:

~~~java
import java.util.Arrays;

public class LocalRecordArrayDemo {
    public static void main(String[] args) {
        record Sample(int[] values) {
            Sample {
                values = values.clone();
            }

            @Override
            public int[] values() {
                return values.clone();
            }

            int sum() {
                return Arrays.stream(values).sum();
            }
        }

        int[] source = {1, 2, 3};
        Sample sample = new Sample(source);

        source[0] = 9;
        int[] read = sample.values();
        read[1] = 8;

        System.out.println("source=" + Arrays.toString(source));
        System.out.println("read copy=" + Arrays.toString(read));
        System.out.println("stored sum=" + sample.sum());
    }
}
~~~

Run:

~~~bash
javac LocalRecordArrayDemo.java
java LocalRecordArrayDemo
~~~

Output:

~~~text
source=[9, 2, 3]
read copy=[1, 8, 3]
stored sum=6
~~~

This example focuses on **preventing mutation of the internal array through input/output aliases**. It **does not** redefine array-content equality; record instances still use generated component equality, so `Sample` with an array here is not a complete value object for every `HashSet`/`HashMap` scenario requiring content comparison.

If array content comparison is required, you can override `equals`/`hashCode` consistently and test them. Do not conflate deep immutability and value equality into a single concept.

## 23. Local enum combined with a `switch` expression

A local enum is completely compatible with `switch` statements/expressions. Java 17 supports standard switch expressions:

~~~java
enum Command {
    ADD, SUBTRACT
}

int answer = switch (command) {
    case ADD -> a + b;
    case SUBTRACT -> a - b;
};
~~~

This is an **illustrative code snippet** requiring `command`, `a`, and `b` to be declared in an appropriate block. Because enum constants form a finite set, the compiler checks exhaustiveness according to the corresponding rules.

### 23.1. Complete switch expression program

Save **`LocalEnumSwitchDemo.java`**:

~~~java
public class LocalEnumSwitchDemo {
    public static void main(String[] args) {
        enum Operation {
            ADD, SUBTRACT, MULTIPLY
        }

        int a = 8;
        int b = 3;

        for (Operation op : Operation.values()) {
            int result = switch (op) {
                case ADD -> a + b;
                case SUBTRACT -> a - b;
                case MULTIPLY -> a * b;
            };
            System.out.println(op + "=" + result);
        }
    }
}
~~~

Run:

~~~bash
javac LocalEnumSwitchDemo.java
java LocalEnumSwitchDemo
~~~

Output:

~~~text
ADD=11
SUBTRACT=5
MULTIPLY=24
~~~

The order of `Operation.values()` is the order in which the enum constants are declared. Since it does not depend on HashMap ordering or thread scheduling, the output is deterministic.

If a new enum constant is later added without adding an appropriate case, the source `switch` expression may need to be updated to ensure exhaustiveness.

## 24. Scope: a type name exists only within a valid block

A local enum/record is scoped **by its source-code block**. That type name cannot be accessed from a sibling method using the name `Outer.LocalRecord`.

For example:

~~~java
class Example {
    void first() {
        record Temp(int n) {
        }

        Temp temp = new Temp(1); // Valid.
    }

    void second() {
        // Temp t = new Temp(2); // Local type Temp is not visible.
    }
}
~~~

A local record does not become a nested **member** class just because the compiler generates a `.class` file within the same compilation unit. The file name/bytecode name is an implementation detail and does not alter Java source-level scope.

### 24.1. Declaring inside a smaller block

~~~java
void demo() {
    {
        enum State { OPEN, CLOSED }
        State state = State.OPEN;
        System.out.println(state);
    }

    // State another = State.CLOSED; // Out of scope.
}
~~~

If a type is only needed in a small processing branch, placing it in the appropriate block reduces name scope and clarifies the type's purpose.

### 24.2. Do not use a local record directly as a public API

A method can return `Object` or an accessible interface/supertype holding an instance of the local record, but callers outside the method **cannot refer to the local record name directly**.

If the type is an important part of a public API that many places need to create/use, consider a member record or top-level record instead of a local record.

## 25. Using a local record as an implementation detail behind an interface

A local record can `implements` an interface accessible in an outer scope and be returned as that interface type.

### 25.1. Runnable program

Save **`LocalRecordInterfaceDemo.java`**:

~~~java
public class LocalRecordInterfaceDemo {
    interface Description {
        String text();
    }

    static Description create(String name, int count) {
        record DescriptionValue(
                String name, int count) implements Description {
            @Override
            public String text() {
                return name + ":" + count;
            }
        }

        return new DescriptionValue(name, count);
    }

    public static void main(String[] args) {
        Description a = create("A", 2);
        Description b = create("B", 3);

        System.out.println(a.text());
        System.out.println(b.text());
    }
}
~~~

Run:

~~~bash
javac LocalRecordInterfaceDemo.java
java LocalRecordInterfaceDemo
~~~

Output:

~~~text
A:2
B:3
~~~

Callers use the `Description` interface without needing to know the implementation type `DescriptionValue` inside the `create` method body. `DescriptionValue` receives both `name` and `count` explicitly, without capturing method parameters.

**Note:** the return type is an interface declared by the outer class, matching the scope. If callers need to access specific component accessors `name()`/`count()`, this interface does not expose those methods yet; an appropriate API must be designed.

## 26. Local declarations cannot have access modifiers for outside the block

Wrong:

~~~java
void invalid() {
    // public record Point(int x, int y) { } // Compile-time error.
    // private enum Mode { A } // Compile-time error.
    // protected record Pair(int a, int b) { } // Compile-time error.
}
~~~

Because a local type declaration resides **inside a block**, it is not a member type for which `public/protected/private` carries the usual member visibility meaning.

If you want the type to be public, place it as a member/top-level declaration with appropriate access.

### 26.1. `final` on records and enums

Records are implicitly final according to Java record semantics; enums also have special final/sealed rules depending on enum constant class bodies. Do not add modifiers arbitrarily. In particular, local declarations also have their own modifier restrictions such as `static`, `sealed`, and `non-sealed`.

The essential point to remember from this lesson is: **implicitly static, yet not explicitly declared static**; do not use modifiers to fix errors caused by missing enclosing context data.

## 27. Static nesting and lifetime: does not retain outer automatically

A local normal class declared in an instance method can use the outer `this` and effectively final locals; its object can retain the necessary references. Conversely, an implicitly static local enum/record has no implicit enclosing instance.

This is useful if you want to create a data carrier that **does not accidentally retain the entire enclosing service/controller object** in a callback or cache.

However:

~~~java
record Holder(Service service) {
}
~~~

is a local record **with a component reference to Service**, if passed explicitly. It can still keep Service reachable in the GC reference graph. Being implicitly static **does not prohibit** explicit strong references.

### 27.1. Do not treat a local type as “existing only on the stack”

- The scope of the **type name** is lexical.
- The lifetime of an **object instance** depends on references and GC reachability, not on whether the method has returned.
- Enum constants have a class-level lifecycle governed by the JVM/classloader, and are not recreated on each block invocation.
- Record instances can be placed into a collection, callback, or returned as an interface/Object and outlive the method that created them.

Therefore, local does not mean ephemeral object, and static does not mean leak-proof.

## 28. Program: a local record outliving a method via an interface

Save **`LocalRecordLifetimeDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LocalRecordLifetimeDemo {
    interface View {
        String render();
    }

    static View build(String label) {
        record Snapshot(String text) implements View {
            @Override
            public String render() {
                return text;
            }
        }

        return new Snapshot(label);
    }

    public static void main(String[] args) {
        List<View> saved = new ArrayList<>();

        saved.add(build("first"));
        saved.add(build("second"));

        for (View item : saved) {
            System.out.println(item.render());
        }
    }
}
~~~

Run:

~~~bash
javac LocalRecordLifetimeDemo.java
java LocalRecordLifetimeDemo
~~~

Output:

~~~text
first
second
~~~

Although `Snapshot` is declared inside `build`, the record object is stored through the `View` interface in `saved` and continues to be used after each `build` invocation finishes.

This does not violate local scope: the `main` method does not directly write the type name `Snapshot`. It only uses the public/interface-level contract `View`.

## 29. Nested local record in a generic context: distinguishing type declaration from construction

Consider:

~~~java
class Container<T> {
    void save(T item) {
        record Snapshot<U>(U data) {
        }

        Snapshot<T> snapshot = new Snapshot<>(item);
        System.out.println(snapshot.data());
    }
}
~~~

- `T` belongs to the class `Container<T>`.
- The local record declaration declares its own `U` and uses `U` in its components.
- Code after the record declaration (in the instance method) can use `T` to **parameterize Snapshot**: `Snapshot<T>`.
- The local record body does not have permission to directly refer to Outer's `T` to declare a component of type `T`.
- No enclosing `Container<T>` object is implicitly passed to `Snapshot`.

**This is the characteristic difference of implicitly static local types.**

### 29.1. What if a local enum needs type-generic behavior?

An enum cannot declare generic type parameters for the enum itself. If the logic needs to accept data of type `T` from an enclosing generic method, have the enum method accept `Object`/an appropriate interface, or place the transformation in the generic method/caller. Do not try to write `enum Operation<T>`.

## 30. Comparing local enums/records with lambdas and anonymous classes

These constructs can appear together in the same method, yet they do not share the same capture mechanism:

| Construct | Has a type name declared in source? | Captures enclosing local variables? | Has implicit enclosing outer? |
| --- | --- | --- | --- |
| Local normal class `class Task` | Yes | Possible, if effectively final | Possible, if instance context |
| Local enum `enum Mode` | Yes | No | No |
| Local record `record Data` | Yes | No | No |
| Anonymous class `new Runnable(){...}` | No | Possible | Possible, depending on context |
| Lambda `() -> ...` | Does not declare a named class type itself | Possible | `this` has lexical meaning, can capture receiver |
| Static nested member class | Has a member type name | Does not capture locals | No |

If you need a callback that reads an effectively final local variable, a lambda or local normal class may be suitable. If you only need a **snapshot data value**, a local record often expresses it more clearly: components must be passed explicitly.

Do not claim that a lambda always creates an object/class file following a fixed bytecode pattern; its representation is a runtime/compiler detail.

## 31. Compile-time errors: reading the root cause accurately

### 31.1. Error due to direct local variable access

~~~java
void demo(int offset) {
    // record Bad(int value) {
    //     int total() { return value + offset; } // Wrong.
    // }
}
~~~

**Cause:** `offset` is an enclosing method parameter, which a local record does not capture.  
**Fix:** declare `record Good(int value, int offset)` and instantiate `new Good(value,offset)`.

### 31.2. Error due to instance field access

~~~java
class Owner {
    int x = 2;

    void demo() {
        // enum Mode {
        //     A;
        //     int x() { return Owner.this.x; } // Wrong.
        // }
    }
}
~~~

**Cause:** a local enum is implicitly static and has no enclosing Owner instance.  
**Fix:** pass an Owner reference into the enum method, or pass the desired int value; avoid retaining the owner if only an int snapshot is needed.

### 31.3. Error due to a method type variable

~~~java
<T> void demo(T input) {
    // record Data(T value) { } // Wrong.
    record Data<U>(U value) { }
    Data<T> data = new Data<>(input);
}
~~~

**Cause:** a local record cannot use the type parameter `T` of the enclosing context in its declaration.  
**Fix:** the record declares its own `U`.

### 31.4. Error due to an explicit `static` modifier

~~~java
void demo() {
    // static enum Mode { A } // Wrong.
    // static record Data(int n) { } // Wrong.
}
~~~

**Cause:** JLS `14.3 does not allow writing `static` on a local type declaration, even though the type is implicitly static.  
**Fix:** remove the modifier.

### 31.5. Error due to an access modifier

~~~java
void demo() {
    // public record Data(int n) { } // Wrong.
}
~~~

**Cause:** local declarations are not public member declarations.  
**Fix:** remove the modifier; or move the type to member/top-level if a public API is needed.

### 31.6. Error due to a type name out of scope

~~~java
void make() {
    record Data(int n) { }
}

// Data d = new Data(1); // Data is not in scope here.
~~~

**Cause:** a local type name does not become a member type.  
**Fix:** use the type within scope, or return it as an interface/supertype, or move the declaration to member-level.

## 32. Process for choosing a type kind for code inside a method

If you want to declare a small type inside a method, ask:

1. Is there a fixed set of constants needing enum identity and `switch`? → **Local enum**.
2. Are there a few values that need to stay together with value semantics? → **Local record**.
3. Do you need to capture effectively final method variables/enclosing state? → **Local normal class** or an appropriate lambda/anonymous class.
4. Does the type need to appear across multiple methods or in a public API? → **Member/top-level enum or record**.
5. Do you need runtime data from the enclosing method while still wanting a local record? → **Pass values via the canonical constructor**.
6. Do you need to use an operation with a runtime threshold in a local enum? → **Pass the threshold into the enum method**.
7. Do you need a generic method type parameter inside a local record? → **Create a record with its own type parameter `U`**, and instantiate with `Box<T>` outside the declaration.
8. Are there mutable arrays/lists? → **Defensive copies/value representation** if an immutable snapshot is needed.
9. Is there nested state or large services? → **Consider ownership/lifetime**, and do not accidentally retain an explicit reference.
10. Does the code run before Java 16? → **Check the version/toolchain**; do not use Java 17 syntax with a source level that is too old.

**Short rule:** if you find a local enum/record trying to read an “outer method variable”, that is usually a sign you need to **turn that variable into an explicit input**.

## 33. Integrated program: local enum + record without capturing state

Save **`LocalTypesIntegrationDemo.java`**:

~~~java
import java.util.List;

public class LocalTypesIntegrationDemo {
    static void summarize(List<Integer> inputs, int threshold) {
        enum Verdict {
            PASS, FAIL
        }

        record Result(int input, int threshold, Verdict verdict) {
            String text() {
                return input + "/" + threshold + "=" + verdict;
            }
        }

        for (int input : inputs) {
            Verdict verdict = input >= threshold
                    ? Verdict.PASS : Verdict.FAIL;

            Result result = new Result(input, threshold, verdict);
            System.out.println(result.text());
        }
    }

    public static void main(String[] args) {
        summarize(List.of(3, 5, 8), 5);
    }
}
~~~

Run:

~~~bash
javac LocalTypesIntegrationDemo.java
java LocalTypesIntegrationDemo
~~~

Output:

~~~text
3/5=FAIL
5/5=PASS
8/5=PASS
~~~

**Analysis:**

- The `summarize` method accepts `inputs` and `threshold`.
- The local enum `Verdict` holds two constants and does not capture `threshold`.
- The comparison `input >= threshold` is performed **outside the local enum**, in the method scope.
- The local record `Result` holds three components supplied **explicitly** via the constructor.
- The record method `text` only reads its own components.
- If you need to use `Result` in other code, move the record to member/top-level scope or expose an appropriate interface.

This is a useful pattern for intermediate pipeline data, classification calculations, validation, and transformation without bloating the public class API.

## 34. Testing the differences with always-executed assertions

Save **`LocalTypesContractTest.java`**:

~~~java
public class LocalTypesContractTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static Object constant() {
        enum Token {
            ONE
        }
        return Token.ONE;
    }

    public static void main(String[] args) {
        record Item(String name, int count) {
        }

        Item a = new Item("A", 1);
        Item b = new Item("A", 1);

        check(a != b, "separate record identity");
        check(a.equals(b), "record value equality");
        check(a.hashCode() == b.hashCode(), "hash contract");

        check(constant() == constant(), "enum singleton constant");

        int local = 7;
        record Snapshot(int value) {
        }
        check(new Snapshot(local).value() == 7,
                "explicit constructor input");

        System.out.println("local enum and record checks passed");
    }
}
~~~

Run:

~~~bash
javac LocalTypesContractTest.java
java LocalTypesContractTest
~~~

Output:

~~~text
local enum and record checks passed
~~~

The `check` method is always invoked, without depending on Java's `assert`, which is disabled by default unless run with `-ea`. The test verifies identity/value behavior without using reflection on compiler-generated class names or predicting GC.

## 35. Common misconceptions

| Misconception | Correct conclusion |
| --- | --- |
| “A local enum is an inner class because it is inside a method.” | A local enum is **implicitly static**, not an inner class. |
| “A local record has an enclosing instance because it is inside an instance method.” | No; a record is **implicitly static**. |
| “Implicitly static means you must write `static`.” | Wrong: a local declaration **must not** write `static` explicitly. |
| “A static record cannot create objects.” | You can still create `new LocalRecord(...)` within scope. |
| “A static enum has no instance methods.” | Enum constants have methods and fields/constructors according to enum rules. |
| “A local record automatically captures local params.” | No; pass them via components/constructor. |
| “A local enum can use effectively final locals because a local class can.” | No; a local enum differs from a local normal class. |
| “`final int n` inside a method is a static field.” | No. A final local is still a local variable. |
| “A local record cannot read static fields.” | It can read accessible static members of the enclosing class. |
| “A generic method `T` can be used directly inside a local record declaration.” | No; the local record declares its own generic `U`. |
| “Enums support generic parameters like `enum E<T>`.” | No. |
| “Local enum constants are created anew on every method call.” | No; enum constants are tied to the enum class lifecycle. |
| “A local record type is created anew on every loop iteration.” | The type declaration is a single type; `new` creates a new instance, not a new class definition on each iteration. |
| “A record deep-copies array components.” | No; arrays are mutable, so defensive copying is needed if a snapshot is required. |
| “A record always compares arrays by contents.” | No; generated equality for array components is by identity. |
| “A local type name can be used from another method via `Outer.Name`.” | No; a local type is not a member type. |
| “A local record cannot implement an interface.” | It can implement an accessible interface. |
| “A local enum must be created with `new`.” | No; use named constants. |
| “A local record can extend any class arbitrarily.” | No; a record extends `java.lang.Record` semantically. |
| “Implicitly static ⇒ deeply immutable, thread-safe data.” | No. Static relation ≠ immutable nested graph/thread safety. |
| “A local type object cannot outlive the method.” | The object can live longer if a reference remains reachable. |
| “Passing an Owner reference into a record will never retain Owner.” | If a component holds an Owner reference, the GC graph can still retain Owner. |
| “When a local enum uses switch, the constant order is randomized by hash.” | `values()` follows the constant declaration order. |
| “A capture error can be fixed using the `private` modifier.” | No. Local type modifiers and capture rules are different. |

## 36. Checklist when code-reviewing local enums/records

- [ ] Is the code using a JDK and `--release`/`--source` suitable for Java 17+?
- [ ] Is the `enum`/`record` declared inside a valid block?
- [ ] Does the declaration accidentally write `static` explicitly?
- [ ] Are there any invalid `public`/`protected`/`private` access modifiers?
- [ ] Are they mistakenly being treated as inner classes?
- [ ] Does the local record/enum body attempt to directly read local variables/method parameters?
- [ ] Is there any attempt to use an instance field, instance method, or `Outer.this` from the local enum/record?
- [ ] Is method data passed through constructor/components or explicit method args?
- [ ] Does it use static members of the enclosing class while overlooking thread-safety if they are mutable?
- [ ] Inside a generic method/outer class, does the local record declare its own type variable `U` when needed?
- [ ] Is the type name used outside its lexical scope?
- [ ] Does the type need to be promoted to member/top-level if other callers must refer to the type name?
- [ ] Are local enum constants compared using `==`/switch` appropriately for the intended purpose?
- [ ] Does the local record have domain-appropriate validation, equality, and hash behavior?
- [ ] Are components such as arrays/lists/custom objects mutable?
- [ ] If acting as a data snapshot, are both input and output mutable references defensively copied?
- [ ] Does the code confuse “static” with singleton, immutable, or zero object allocations?
- [ ] Do the examples have matching class/file names and are they runnable with `javac`/`java`?

## 37. Practice exercises and solutions

**Question 1.** Is `enum LocalMode { A, B }` inside a method an inner class?  
**Answer:** No. A local enum is implicitly static.

**Question 2.** Is `record LocalPair(int a,int b)` inside a method an inner class?  
**Answer:** No. A local record is implicitly static.

**Question 3.** Why is `static record R(int n)` not written inside a method?  
**Answer:** A local type declaration cannot include an explicit `static` modifier according to JLS `14.3.

**Question 4.** Can a local normal class capture `final int bonus` of a method?  
**Answer:** Yes, under valid conditions (local final/effectively final), unlike local enums/records.

**Question 5.** Can a local record access `bonus` directly because bonus is effectively final?  
**Answer:** No, it does not capture enclosing locals.

**Question 6.** How do you pass bonus into a local record?  
**Answer:** Add a `bonus` component and pass `new R(value,bonus)`.

**Question 7.** What should you do if a local enum method wants to use the caller's runtime threshold?  
**Answer:** Add a method parameter and call `Rule.A.test(value,threshold)`.

**Question 8.** Can a local enum have instance fields?  
**Answer:** Yes, such as the enum constant state `percent` in the constructor.

**Question 9.** Can a local record declare instance methods?  
**Answer:** Yes, such as `sum()`/`passed()`.

**Question 10.** Can a local enum use `Outer.this.name` from an enclosing instance method?  
**Answer:** No, there is no implicit enclosing Outer instance.

**Question 11.** How should you pass an instance field of Outer if a local record needs to use it?  
**Answer:** Pass the field value or an Outer reference explicitly according to the contract, without using implicit capture.

**Question 12.** Can an accessible static field of Outer be read inside a local record?  
**Answer:** Yes, according to static access rules.

**Question 13.** Is `final int local = 7` a static member?  
**Answer:** No, it is still a local variable.

**Question 14.** Can a generic method `<T> void run(T x)` declare `record R(T x)`?  
**Answer:** No, T belongs to the enclosing generic method.

**Question 15.** How do you fix the exercise above?  
**Answer:** `record R<U>(U x){}` and inside the method `R<T> r = new R<>(x)`.

**Question 16.** Is the local enum `enum E<T>` valid?  
**Answer:** No; enum declarations do not have their own generic type parameters.

**Question 17.** Do two method calls returning `Token.ONE` of the same local enum declaration have the same reference?  
**Answer:** Yes, within the normal same classloader/class lifecycle.

**Question 18.** Do two calls to `new LocalRecord(1)` have the same reference?  
**Answer:** No, they are two separate object allocations; `equals` can be true.

**Question 19.** Can a `LocalRecord` inside a method be referred to as `Outer.LocalRecord` from another method?  
**Answer:** No, it is not a member type.

**Question 20.** Can you return a local record object via an interface?  
**Answer:** Yes, if the local record implements that interface and the return type is accessible.

**Question 21.** Can a local record use a compact constructor for validation?  
**Answer:** Yes.

**Question 22.** Is the local record `record D(int[] arr)` automatically deeply immutable?  
**Answer:** No; the array reference is held, and the elements are mutable unless defensively copied.

**Question 23.** Why is cloning only the input array still insufficient to protect the accessor?  
**Answer:** A getter returning the raw internal array still exposes mutation; defensive output copying is needed for a snapshot.

**Question 24.** Does the generated `equals` of a record with `int[]` compare array contents like `Arrays.equals`?  
**Answer:** No. Array components default to reference identity.

**Question 25.** Does `LocalEnum.values()` preserve constant order?  
**Answer:** Yes, following the declaration order of enum constants.

**Question 26.** Is a local record type redefined on every iteration of a loop?  
**Answer:** No; at runtime it creates instances when `new` is executed, without defining a new type on every iteration.

**Question 27.** Does implicitly `static` mean the record has no instance members at all?  
**Answer:** No, the record still has component fields and instance methods.

**Question 28.** Can a local enum/record be declared `public` on the local type declaration?  
**Answer:** No.

**Question 29.** If a type needs to be shared across multiple methods, where should it be placed?  
**Answer:** Consider a member or top-level enum/record instead of a local one.

**Question 30.** Can a local record be used as a temporary value in a pipeline?  
**Answer:** Yes, especially when components are passed explicitly and the type does not need to be exposed in the API.

**Question 31.** Can a local record retain an Owner object if Owner is passed into a component?  
**Answer:** Yes; implicitly static only removes the implicit enclosing reference, and does not prevent explicit references.

**Question 32.** What if you want a local enum to differ on each invocation?  
**Answer:** Enum constants are not recreated per invocation; if a changing runtime value is needed, use a record/class instance or pass runtime data into methods.

**Question 33.** Does JDK 17 require enabling `--enable-preview` to use local records?  
**Answer:** No, local records have been a standard feature since Java 16.

**Question 34.** What is the most concise difference between a local normal class and a local record/enum?  
**Answer:** A local normal class is an inner class and can capture an appropriate context; a local record/enum is implicitly static and **does not capture enclosing locals/instance**.

## 38. References

- Java Language Specification, Java SE 17, [`14.3 — Local Class and Interface Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3): local declarations, modifiers, and implicitly static local enums/records.
- Java Language Specification, [`8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): which types are inner and which are not.
- Java Language Specification, [`8.9 — Enum Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9): enum declarations, constants, and implicitly static nested enums.
- Java Language Specification, [`8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record components, constructors, methods, and static nested status.
- Java Language Specification, [`6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): lexical scope of type declarations.
- Java Language Specification, [`6.5.5.1 — Simple Type Names](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.5.5.1): restrictions on referencing type names/type variables from a static context.
- Java Language Specification, [`6.5.6.1 — Simple Expression Names](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.5.6.1): restrictions on accessing enclosing variables.
- Oracle Java 17 Language Guide, [Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): implicitly static local records, examples.
- OpenJDK JEP 395, [Records](https://openjdk.org/jeps/395): records standardized in Java 16.
- Java Language Specification, [`15.28 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): how a local final constant differs from a static field.
- Java API, [`java.lang.Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): base class and value methods of records.
- Java API, [`java.lang.Enum](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html): enum base class and methods.

## Conclusion

**Local enums and local records are both implicitly static in Java 17** even though they are declared inside a method/block. This does not turn them into static members of the enclosing class; the type name still has **local scope**, and the declaration **must not** include an explicit `static` keyword.

The key difference compared to a local normal class is **not capturing enclosing method variables, parameters, generic type variables, or an Outer instance**. When runtime data is needed, pass it via record components/constructor or arguments of enum methods; when only static data is needed, use accessible static members clearly.

A local enum is suitable for a fixed set of constants and `switch`/strategies; a local record is suitable for intermediate data with value semantics and constructor validation. Do not confuse implicitly static with “cannot create instances”, “automatically deeply immutable”, “a singleton per invocation”, or “automatically avoids all memory retention”. Properly understanding **scope + static relation + explicit data flow** will help you use both local types safely and clearly in modern Java.
