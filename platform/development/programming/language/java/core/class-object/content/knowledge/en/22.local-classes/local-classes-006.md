# Access Modifier and `static` Restrictions on Local Normal Classes in Java 17

A **local normal class** is a named class declared directly inside a block, such as a method body, constructor, or initializer. What makes this class special is that **it is not a member of the enclosing class**. Therefore, member class modifier rules cannot be applied to a local class declaration line.

Two easily confused statements must be kept separate:

1. **On the local normal class declaration itself**: you cannot write `public`, `protected`, `private`, `static`, `sealed`, or `non-sealed`.
2. **Inside the body of a local normal class in Java 17**: you can still declare **static fields, static methods, static initializer blocks, and static nested member types** according to the appropriate rules. This **differs from the restrictions in Java versions prior to Java 16**.

Valid example in Java 17:

```java
void demonstrate() {
    int offset = 2;

    final class Local {
        static int base() {
            return 10;
        }

        int calculate() {
            return base() + offset;
        }
    }

    System.out.println(new Local().calculate());
}
```

This is a **method snippet**, not yet a standalone runnable source file. Placing `final` on the local class declaration is valid. `static` placed on **method `base` inside Local** is also valid in Java 17. However, changing the line `final class Local` to `static class Local` is a **compilation error**.

This guide explains modifiers at the **class declaration** level versus modifiers at the **member declaration** level, rules according to the Java Language Specification (JLS), valid/rejected cases, local enum/record/interface, static contexts, captured variables, access scope, how to run `javac --release 17`, many examples with deterministic stdout, exercises, and a checklist.

## 1. Correctly Identifying a “local normal class”

Example:

```java
class Host {
    void process() {
        class LocalWorker {
            void execute() {
                System.out.println("working");
            }
        }

        new LocalWorker().execute();
    }
}
```

`LocalWorker` is a **local normal class** because the `class LocalWorker` declaration is contained directly inside the block of `process()`. It is not a field, method, member class, or top-level class.

Comparison:

```java
class Host {
    // This is a member nested class:
    private static class MemberHelper {
    }

    void process() {
        // This, however, is a local normal class:
        class LocalHelper {
        }
    }
}
```

`MemberHelper` is declared **in the body of Host**, at a member declaration position. `LocalHelper` is declared **in the block of a method**. This difference in position leads to different modifier rules.

### What Does “Normal” Mean?

In JLS 17 `14.3, a local class can be:
- **Local normal class**: declared with the `class` keyword; typically this is an **inner class**.
- **Local enum class**: an `enum` declaration in a block, **implicitly static**.
- **Local record class**: a `record` declaration in a block, **implicitly static**.

JLS 17 also allows a **local interface** in a block, which is also **implicitly static**. Enum/record/interface types have different rules from a local **normal** class, so do not lump them all together into a single conclusion that “a local class is always inner”.

## 2. Modifier Table to Remember

Consider the **modifiers written directly before `class Local`**, not the modifiers of methods/fields located inside it.

| Modifier on local normal class declaration | Java 17 | Notes |
| --- | --- | --- |
| No modifier | Valid | Common default |
| `final` | Valid | Prohibits subclasses of the local class |
| `abstract` | Valid | Cannot directly use `new Local()` |
| `strictfp` | Syntactically allowed | In Java 17, default strict floating-point makes this modifier have no practical effect |
| Applicable annotation `@...` | Valid per target | For example, an annotation with `@Target(TYPE)` |
| `public` | **Invalid** | A local class is not a public member/top-level type |
| `protected` | **Invalid** | No member access modifier on a local class declaration |
| `private` | **Invalid** | Name scope is determined by the lexical block |
| `static` | **Invalid** | A local normal class cannot include `static` in its declaration |
| `sealed` | **Invalid** | Prohibited by JLS `14.3 |
| `non-sealed` | **Invalid** | Prohibited by JLS `14.3 |
| `abstract final` together | **Invalid** | Two conflicting constraints |

**Do not infer:** “a local normal class cannot have static members”. That is a **different question** and in Java 17 it has a different answer.

## 3. Why Are `public`, `protected`, and `private` Prohibited?

The access modifiers of a **class declaration** serve to manage the accessibility of:
- Top-level class: `public` or package-private.
- Member class: `public`, `protected`, `private`, or package-private.
- Local class: **none of the three access modifiers above**.

The local class name is already restricted by the **lexical scope of the block** and does not become a member type that can be accessed using syntax like `Host.Local`.

Incorrect example:

```java
void run() {
    private class Local {
    }
}
```

This snippet **intentionally does not compile**: `private` cannot be used before a local class declaration. Remove `private`:

```java
void run() {
    class Local {
    }
    Local value = new Local();
}
```

A developer might think, “I want to restrict Local to the method, so I will declare it private”, but placing the declaration inside the method already restricts **the scope of the local class name**. Adding `private` does not make the class “more private”; it only causes a compilation error.

### `protected` Does Not Provide Extensibility Either

You cannot use `protected class Local` hoping that a subclass from another package will see the local class. A local type is not a protected member. If you need a type to be inherited from or accessed like a member from elsewhere, design an appropriate **member nested class or top-level class**.

## 4. Runnable: Valid Local Class Without an Access Modifier

Save **`LocalModifierBasics.java`**:

```java
public class LocalModifierBasics {
    static void execute() {
        class Counter {
            private int value;

            Counter(int initial) {
                value = initial;
            }

            int next() {
                return ++value;
            }
        }

        Counter counter = new Counter(3);
        System.out.println(counter.next());
        System.out.println(counter.next());
    }

    public static void main(String[] args) {
        execute();
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 LocalModifierBasics.java
java LocalModifierBasics
```

**Stdout:**

```text
4
5
```

Note the distinction:
- `class Counter` **does not have** `private` before the class keyword.
- `private int value` **inside Counter** is a valid field declaration.
- The constructor and instance method of Counter work just like on a normal class.
- The name `Counter` is used inside `execute()`, not as a member type `LocalModifierBasics.Counter` outside the method.

## 5. Access Modifier Restrictions on a *Class* Differ from *Member* Accessibility

A local normal class can still contain fields/methods with valid access modifiers for those members themselves.

```java
void process() {
    class Local {
        private int hidden = 1;

        public int read() {
            return hidden;
        }

        protected void update(int value) {
            hidden = value;
        }
    }

    Local local = new Local();
    local.update(7);
    System.out.println(local.read());
}
```

This is a snippet inside a method body. The `Local` declaration **has no access modifier**, but `hidden` is a private field; `read` is a public method; `update` is a protected method.

Java does not apply the “local class forbids public” rule to **every method inside it**. The prohibition rule in question is the **modifier on the local class or interface declaration line**.

### Should You Write Public Methods Inside a Local Class?

It can be syntactically valid; however, the type name `Local` is not exposed outside its scope. A public method is useful when an instance is returned via an interface/superclass whose method it overrides, or when valid code within the scope needs to use it.

The `public` modifier on a method **does not turn `Local` into a public top-level type**. Consider the actual API that the caller sees.

## 6. Runnable: Members of a Local Class with Access Modifiers

Save **`LocalMemberAccessDemo.java`**:

```java
public class LocalMemberAccessDemo {
    interface Reader {
        int read();
    }

    static Reader make() {
        class LocalReader implements Reader {
            private int value = 7;

            public int read() {
                return value;
            }

            private void set(int next) {
                value = next;
            }

            LocalReader() {
                set(9);
            }
        }

        return new LocalReader();
    }

    public static void main(String[] args) {
        Reader reader = make();
        System.out.println(reader.read());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalMemberAccessDemo.java
java LocalMemberAccessDemo
```

**Stdout:**

```text
9
```

`LocalReader` does not carry an access modifier on its **class declaration**, while the member method `read` is declared public to implement `Reader.read()`, which is implicitly public.

`LocalReader` is returned through the `Reader` interface. The caller only needs `reader.read()` and does not need to see the name `LocalReader` outside `make()`.

## 7. `final` on a Local Normal Class

Syntax:

```java
void process() {
    final class Local {
        String name() {
            return "local";
        }
    }
}
```

**Valid.** `final` prohibits other classes from inheriting from `Local`, just like final top-level/member classes.

It **does not**:
- Automatically make the instance fields of Local immutable;
- Prohibit creating multiple Local objects;
- Make Local static;
- Expand the scope of the name Local.

### Runnable: Final Local Class

Save **`FinalLocalDemo.java`**:

```java
public class FinalLocalDemo {
    public static void main(String[] args) {
        final class LocalMessage {
            private String text;

            LocalMessage(String text) {
                this.text = text;
            }

            String get() {
                return text;
            }
        }

        LocalMessage first = new LocalMessage("A");
        LocalMessage second = new LocalMessage("B");

        System.out.println(first.get());
        System.out.println(second.get());
        System.out.println(first == second);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 FinalLocalDemo.java
java FinalLocalDemo
```

Stdout:

```text
A
B
false
```

`final` on the class declaration restricts inheritance; the field `text` is still a regular field that can be mutable in methods that have access. This is not an example of deep immutability.

## 8. `abstract` on a Local Normal Class

Java 17 allows:

```java
void process() {
    abstract class LocalBase {
        abstract String describe();
    }

    class LocalImpl extends LocalBase {
        @Override
        String describe() {
            return "implemented";
        }
    }

    LocalBase item = new LocalImpl();
}
```

`LocalBase` is named inside the method and is used as the superclass of the local implementation. **It cannot be instantiated using `new LocalBase()`** because an abstract class is incomplete.

### Why Not Put Both `abstract` and `final`?

`abstract` indicates that the class is incomplete and needs a concrete subclass to create objects; `final`, on the other hand, prevents subclassing. Putting both constraints on the same class is a compile-time error.

**Distinction:** `abstract`/`final` are allowed **individually** on a local normal class declaration; not every combination of two individually valid modifiers is valid together.

## 9. Runnable: Abstract Local Class with a Local Implementation

Save **`AbstractLocalDemo.java`**:

```java
public class AbstractLocalDemo {
    static String describe(int number) {
        abstract class LocalBase {
            abstract String render();
        }

        final class Decimal extends LocalBase {
            @Override
            String render() {
                return "number=" + number;
            }
        }

        LocalBase value = new Decimal();
        return value.render();
    }

    public static void main(String[] args) {
        System.out.println(describe(7));
        System.out.println(describe(10));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AbstractLocalDemo.java
java AbstractLocalDemo
```

**Stdout:**

```text
number=7
number=10
```

The method parameter `number` is captured in the instance method of the local subclass and is **effectively final** because it is never reassigned.

Do not confuse this capture behavior with the validity of the `abstract` or `final` modifier on the two local class declarations.

## 10. `static class Local`: Invalid

Incorrect example:

```java
void run() {
    static class Local {
    }
}
```

This is an **intentional compile-negative example**. `static` cannot be placed **before the declaration** of a local normal class.

A conceptual reason: the `static` modifier on a **member nested class** declaration distinguishes whether a member type has an implicit enclosing instance or not, whereas a local class **is not a member class**.

Another valid example:

```java
class Outer {
    static class MemberNested {
    }
}
```

Here, `MemberNested` sits directly inside the body of Outer, so `static` is valid. It **is not a local class**.

### A Local Class Can Still Exist in a Static Method

`static` on the **enclosing method** is different from `static` on the **declaration of the local class**:

```java
static void work() {
    class Local {
    }
}
```

Valid code: the local class is declared **inside a static context**. This does not automatically provide an enclosing Outer instance.

The following two statements are not synonymous:
- “A local class is declared **inside a static method**.” → Can be valid.
- “The local class itself is declared as **`static class`**.” → Prohibited in `14.3`.

## 11. Runnable: Local Class Inside a Static Method

Save **`StaticMethodLocalDemo.java`**:

```java
public class StaticMethodLocalDemo {
    private static final String PREFIX = "S-";

    static String create(int id) {
        class Local {
            String value() {
                return PREFIX + id;
            }
        }

        return new Local().value();
    }

    public static void main(String[] args) {
        System.out.println(create(3));
        System.out.println(create(8));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 StaticMethodLocalDemo.java
java StaticMethodLocalDemo
```

Stdout:

```text
S-3
S-8
```

`Local` does not have `static` before `class`. It is still declared inside `static String create(...)`, uses the static field `PREFIX`, and captures the effectively final parameter `id`.

### No `Outer.this` in a Static Context

If `create` needs an instance field `ownerName`, there must be an **explicit owner reference**, or the code must be moved to an instance method. Declaring a local class does not give a static method `this`.

## 12. Java 16 Milestone: Changes to Static Member Restrictions

This is very important knowledge when reading code across multiple versions:

**Prior to Java SE 16**, inner classes had stricter rules: in general, they could not declare static initializers or static members, except for **constant variables** as defined by the JLS.

**Starting in Java SE 16 and in Java SE 17**, that restriction was relaxed. JLS `8.1.3 allows **an inner class to declare and inherit static members and have static initializers**, even though it remains an inner class itself.

Therefore, in Java 17:

```java
void process() {
    class Local {
        static int counter = 1;

        static int next() {
            return ++counter;
        }

        static {
            System.out.println("Local initialized");
        }
    }

    System.out.println(Local.next());
}
```

This is a method body snippet that is **valid when compiled with Java 17**. The line `class Local` does not have a static modifier, but the **members inside** have the static modifier.

### Comparing the Two Levels

| Where `static` is written | Example | Java 17 |
| --- | --- | --- |
| Before a local normal class declaration | `static class Local {}` in a method | **Error** |
| Before a field of a local normal class | `class Local { static int n; }` | **Valid** |
| Before a method of a local normal class | `class Local { static void run(){} }` | **Valid** |
| Static initializer of a local normal class | `class Local { static { ... } }` | **Valid** |
| Before a member class inside a local class body | `class Local { static class Nested{} }` | **Valid** |
| Local record/enum/interface declaration with explicit `static` | `static record R(int x) {}` in a block | **Error** |
| Local record/enum/interface without `static` | `record R(int x) {}` in a block | **Valid; implicitly static** |

**This is a distinction that cannot be replaced by the mantra “local classes forbid static”**.

## 13. Runnable: Static Field and Static Method in a Java 17 Local Class

Save **`LocalStaticMembersDemo.java`**:

```java
public class LocalStaticMembersDemo {
    static void demonstrate() {
        class LocalCounter {
            private static int count = 1;

            static int next() {
                return ++count;
            }

            int snapshot() {
                return count;
            }
        }

        LocalCounter counter = new LocalCounter();

        System.out.println(LocalCounter.next());
        System.out.println(counter.snapshot());
        System.out.println(LocalCounter.next());
    }

    public static void main(String[] args) {
        demonstrate();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalStaticMembersDemo.java
java LocalStaticMembersDemo
```

**Stdout:**

```text
2
2
3
```

**Explanation:**
- `LocalCounter` is a **local normal class** inside a static method.
- `count` is a static field **of the LocalCounter type itself**, not an instance field of `counter`.
- `next()` is a static method of LocalCounter.
- `snapshot()` is an instance method called on the LocalCounter object.
- The class remains **local** due to where it is declared; it does not become a member nested class simply because it has static members.

### Be Careful When Comparing with Java 8

Taking an older project compiling with `--release 8` and putting code with non-constant static fields/methods inside a local class into it can cause a compilation error. When covering Java 17, use the lesson's proper **language level** rather than rigidly applying historical limitations.

## 14. Runnable: Static Initializer in a Local Normal Class

Save **`LocalStaticInitializerDemo.java`**:

```java
public class LocalStaticInitializerDemo {
    static void demonstrate() {
        class LocalConfig {
            static final int VALUE;

            static {
                VALUE = 17;
                System.out.println("initializing LocalConfig");
            }

            static int version() {
                return VALUE;
            }
        }

        System.out.println(LocalConfig.version());
        System.out.println(LocalConfig.version());
    }

    public static void main(String[] args) {
        demonstrate();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalStaticInitializerDemo.java
java LocalStaticInitializerDemo
```

**Stdout:**

```text
initializing LocalConfig
17
17
```

The static initializer runs when the JVM initializes the `LocalConfig` type according to class initialization rules, not on every call to `version()`.

`VALUE` is a static final field assigned in the static initializer. It is not a *compile-time constant variable* because it does not have a constant expression initializer at its declaration.

This is a **valid capability in Java 17** that must be distinguished from the old rule prior to Java 16.

## 15. Static Contexts Inside a Local Class Are Still Restricted

“Allowing static members” does **not** mean a static method can automatically access every variable enclosing the local class.

Consider the snippet:

```java
void process() {
    int offset = 5;

    class Local {
        static int calculate() {
            // return offset; // Invalid.
            return 10;
        }

        int calculateWithOffset() {
            return calculate() + offset;
        }
    }
}
```

`offset` is a local variable in the **enclosing method**. The instance method `calculateWithOffset()` of Local can capture `offset` if it is effectively final. However, the static method `calculate()` of Local **cannot capture a local variable from the enclosing method across a static context boundary**.

Similarly, a static method:
- Does not have a `this` reference for a Local object.
- Does not have an implicit enclosing instance provided through it.
- Cannot use unqualified instance members without an appropriate receiver.
- Cannot use `Outer.this` merely due to lexical nesting while inside that static context.

### How to Fix It

Pass the value into the static method:

```java
class Local {
    static int calculate(int offset) {
        return 10 + offset;
    }
}

System.out.println(Local.calculate(offset));
```

This is a snippet inside a block. It expresses an explicit dependency. Alternatively, if the behavior genuinely needs captured instance state, move the logic into an **instance method** of the local class.

## 16. Runnable: Same Local Class Having Both Static and Instance Methods

Save **`StaticBoundaryDemo.java`**:

```java
public class StaticBoundaryDemo {
    static int compute(int input) {
        int bonus = 3;

        class Local {
            static int doubleValue(int value) {
                return value * 2;
            }

            int result() {
                return doubleValue(input) + bonus;
            }
        }

        return new Local().result();
    }

    public static void main(String[] args) {
        System.out.println(compute(4));
        System.out.println(compute(10));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 StaticBoundaryDemo.java
java StaticBoundaryDemo
```

**Stdout:**

```text
11
23
```

`doubleValue` uses only the parameter of **that static method itself** and does not capture `input` or `bonus` from the outer method. The instance method `result` is allowed to capture `input` and `bonus`.

This is a separation of **scope and receiver**, not a total ban on static members.

## 17. Static Member Type Inside a Local Class

In Java 17, a local normal class can contain a **static nested member class**.

Snippet:

```java
void demonstrate() {
    class Local {
        static class Detail {
            static String label() {
                return "detail";
            }
        }
    }

    System.out.println(Local.Detail.label());
}
```

`Detail` is a member class of `Local`, while `Local` is a local class of the block. There is no `static` before `class Local`.

### Runnable

Save **`LocalNestedTypeDemo.java`**:

```java
public class LocalNestedTypeDemo {
    static void execute() {
        class Local {
            static class Detail {
                static String label() {
                    return "detail";
                }
            }

            String instanceLabel() {
                return Detail.label() + "-instance";
            }
        }

        System.out.println(Local.Detail.label());
        System.out.println(new Local().instanceLabel());
    }

    public static void main(String[] args) {
        execute();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalNestedTypeDemo.java
java LocalNestedTypeDemo
```

Stdout:

```text
detail
detail-instance
```

Use `Local.Detail` only **within the scope where the name Local is still visible**. From another method, you cannot simply write `Local.Detail` as if Local were a public member type of the enclosing top-level class.

## 18. Local Interface, Record, and Enum: Same Block Position, Different Rules

Java 17 allows declarations inside a block:

```java
void run() {
    interface Rule {
        boolean accepts(int value);
    }

    record Pair(int left, int right) {
    }

    enum Mode {
        FAST, SAFE
    }
}
```

They have **local names**, but:
- A local interface is **implicitly static**.
- A local record is **implicitly static**.
- A local enum is **implicitly static**.

Therefore, they **have no implicit enclosing instance** in the way a local normal inner class can in an instance context. They do not capture enclosing local variables or Outer instance state through the instance mechanism of a local normal class.

**Do not write `static interface Rule`, `static record Pair`, or `static enum Mode` inside a block**. An explicit static modifier is prohibited by `14.3` on local declarations, even though they have **implicit** static semantics.

### A Local Interface Is Not an Annotation Interface

JLS 17 allows a normal local interface declaration, but **does not allow an annotation interface** as a local interface. Do not lump `@interface` into the same rule as a local normal interface.

## 19. Runnable: Local Interface, Record, Enum

Save **`LocalStaticKindsDemo.java`**:

```java
public class LocalStaticKindsDemo {
    static void demonstrate() {
        interface Rule {
            boolean accepts(int value);
        }

        record Pair(int left, int right) {
            int sum() {
                return left + right;
            }
        }

        enum Mode {
            FAST, SAFE
        }

        Rule positive = value -> value > 0;
        Pair pair = new Pair(3, 4);
        Mode mode = Mode.SAFE;

        System.out.println(positive.accepts(3));
        System.out.println(pair.sum());
        System.out.println(mode);
    }

    public static void main(String[] args) {
        demonstrate();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalStaticKindsDemo.java
java LocalStaticKindsDemo
```

**Stdout:**

```text
true
7
SAFE
```

The example does not pass enclosing method data to the implicitly static types. `Rule`, `Pair`, and `Mode` only have names within the method scope.

**Important:** the restrictions on `public/private/protected/static/sealed/non-sealed` for a **local type declaration** apply according to `14.3`; do not take rules specific to a member record/interface and place those modifiers directly onto a local declaration.

## 20. Local Records Do Not Capture Method Local Variables

Consider the snippet:

```java
void run() {
    int offset = 5;

    record Pair(int left, int right) {
        int sum() {
            return left + right;
            // return left + right + offset; // Invalid.
        }
    }
}
```

`Pair` is a **local record**, which is implicitly static, so an instance method of Pair cannot capture `offset` from the outer method the way an instance method of a local normal class can.

If `offset` is needed, pass it into:
- A record component;
- A method parameter;
- A permitted explicit dependency/constructor field;
- Or design a local normal class if enclosing capture is the intention.

### Runnable: Passing State via a Record Component

Save **`LocalRecordCaptureDemo.java`**:

```java
public class LocalRecordCaptureDemo {
    static int calculate(int value) {
        int offset = 5;

        record ValueWithOffset(int value, int offset) {
            int total() {
                return value + offset;
            }
        }

        ValueWithOffset item =
                new ValueWithOffset(value, offset);

        return item.total();
    }

    public static void main(String[] args) {
        System.out.println(calculate(3));
        System.out.println(calculate(10));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalRecordCaptureDemo.java
java LocalRecordCaptureDemo
```

Stdout:

```text
8
15
```

The record does not capture `offset` implicitly; the caller **explicitly passes offset** into the component when creating the record instance.

## 21. Local Variables Captured by a Normal Local Class

A local normal class can read a local variable or parameter from the enclosing method when it satisfies the following:
- The variable is declared and is within valid scope.
- The variable is definitely assigned when used.
- The variable is **final or effectively final**.
- The usage is not prohibited by another static context.

Example:

```java
void execute() {
    int threshold = 10;

    class Checker {
        boolean accepts(int value) {
            return value > threshold;
        }
    }

    System.out.println(new Checker().accepts(12));
}
```

`threshold` is assigned once, so it is effectively final.

### Incorrect Example Due to Reassignment

```java
void execute() {
    int threshold = 10;

    class Checker {
        boolean accepts(int value) {
            return value > threshold;
        }
    }

    threshold = 20; // No longer effectively final.
}
```

The compiler rejects using `threshold` inside the local class because the captured local variable is not effectively final. This is **different** from an access modifier error and **different** from an error from writing `static class Local`.

## 22. Runnable: Local Class Capturing an Effectively Final Parameter

Save **`EffectivelyFinalLocalDemo.java`**:

```java
public class EffectivelyFinalLocalDemo {
    static String formatter(String prefix, int id) {
        String suffix = "!";

        class LocalFormatter {
            String format() {
                return prefix + "-" + id + suffix;
            }
        }

        return new LocalFormatter().format();
    }

    public static void main(String[] args) {
        System.out.println(formatter("A", 3));
        System.out.println(formatter("B", 7));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EffectivelyFinalLocalDemo.java
java EffectivelyFinalLocalDemo
```

Stdout:

```text
A-3!
B-7!
```

`prefix` and `id` are method parameters; `suffix` is a local variable. None of these variables are reassigned, so they are all effectively final.

### Capturing a Reference Does Not Mean an Immutable Object

If an effectively-final local variable holds a `List` or array reference, the local class can still observe mutations of the referent through the alias. The effectively final rule applies to **variable reassignment**, and does not automatically create a deep copy or thread-safety.

## 23. Local Normal Class in an Instance Context

A local normal class declared in an **instance method** can access the state of the enclosing object in a valid context.

```java
class CounterHost {
    private int base = 10;

    int calculate(int value) {
        class Local {
            int result() {
                return base + value;
            }
        }

        return new Local().result();
    }
}
```

`base` is read from the enclosing `CounterHost` instance; `value` is captured from the effectively final method parameter.

If `calculate` is changed to a static method and still reads `base` directly, there will be no `CounterHost.this` in the static context.

**The term “local class” does not by itself determine whether there is an enclosing instance**: you must know **whether it is declared in an instance or static context**.

## 24. Runnable: Instance Context and `Outer.this`

Save **`LocalOuterContextDemo.java`**:

```java
public class LocalOuterContextDemo {
    private final String name;

    LocalOuterContextDemo(String name) {
        this.name = name;
    }

    String describe(int id) {
        class Local {
            String label() {
                return LocalOuterContextDemo.this.name + "#" + id;
            }
        }

        return new Local().label();
    }

    public static void main(String[] args) {
        LocalOuterContextDemo a =
                new LocalOuterContextDemo("A");
        LocalOuterContextDemo b =
                new LocalOuterContextDemo("B");

        System.out.println(a.describe(1));
        System.out.println(b.describe(2));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalOuterContextDemo.java
java LocalOuterContextDemo
```

Stdout:

```text
A#1
B#2
```

Here, `LocalOuterContextDemo.this` is valid because the local class resides in an appropriate instance method context. This does **not** turn Local into a member class; it is still a local normal class.

## 25. Static Methods of a Local Class Have No `Outer.this`

Inside a **static member** of a local class, there is no `this` receiver, and you cannot rely on enclosing instance/local captures.

Intentionally incorrect example:

```java
class Outer {
    private int base = 10;

    void method() {
        class Local {
            static int read() {
                // return Outer.this.base; // Static context error.
                return 0;
            }
        }
    }
}
```

Even though the local class is declared inside an Outer instance method, `read()` is a static method **inside Local**. It requires an explicit `Outer` object, a parameter, or an instance method of Local with valid access.

Distinction:
- An instance method of a local normal class can reference an appropriate enclosing context.
- A static method of a local normal class still obeys **static context rules**.

### Solution: Passing the Receiver

```java
class Local {
    static int read(Outer owner) {
        return owner.base;
    }
}
```

This is a snippet in a scope that has the Outer type and valid access. It **does not capture** the Outer instance; the receiver is supplied explicitly.

## 26. `strictfp`: Valid, But Should Not Be Overused

`strictfp` used to be required to enforce strict floating-point semantics. As of Java 17, Java applies **always-strict floating-point semantics** per the language update; using `strictfp` usually adds no effect and may produce a compiler warning.

Syntax example:

```java
void run() {
    strictfp class Local {
        double half(double value) {
            return value / 2.0;
        }
    }
}
```

This is a method body snippet. **Do not use strictfp to “fix” access/static modifier errors**: it pertains to floating-point semantics and has nothing to do with visibility or an enclosing instance.

Simply remember that `strictfp` is still present in JLS 17's list of class modifiers, but **it is no longer a useful way to alter calculation precision** in Java 17.

## 27. Annotations on a Local Normal Class

An annotation that applies to a **type declaration** can be written before a local normal class if the annotation's `@Target` permits it.

Example:

```java
void work() {
    @Deprecated
    class LocalOld {
        String value() {
            return "old";
        }
    }

    LocalOld value = new LocalOld();
}
```

`@Deprecated` here is an **annotation**, not an access modifier. It does not expose the class outside its scope.

Not every annotation is permitted everywhere: Java checks `@Target`, applicability, and retention. For example, an annotation intended only for FIELD cannot be arbitrarily applied to a local class declaration.

### Runnable: Annotation Type Target

Save **`AnnotatedLocalDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@interface Marker {
}

public class AnnotatedLocalDemo {
    static String read() {
        @Marker
        class Local {
            String value() {
                return "marked";
            }
        }

        return new Local().value();
    }

    public static void main(String[] args) {
        System.out.println(read());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnnotatedLocalDemo.java
java AnnotatedLocalDemo
```

Stdout:

```text
marked
```

The annotation has an appropriate TYPE target; the code does not assume the annotation will appear via Reflection since runtime retention is not declared. Declaring an annotation on a local class **does not replace an access modifier**.

## 28. `sealed` and `non-sealed`: Why Cannot They Be Placed on a Local Declaration?

Java 17 has sealed classes to restrict direct subclasses. However, **JLS `14.3 prohibits `sealed` and `non-sealed` on local class/interface declarations**.

Incorrect example:

```java
void work() {
    sealed class Local permits Child {
    }

    final class Child extends Local {
    }
}
```

This is **intentionally non-compiling code**, regardless of attempting to declare a permitted subclass. The primary reason is that the `sealed` modifier is invalid on a local class declaration.

A local normal class also **cannot directly extend a sealed class or implement a sealed interface** under the specific condition of JLS 14.3. This keeps local declarations separate from the permitted subclasses model of a sealed hierarchy.

### Alternative Design Approaches

- If you need an explicit public or private member sealed hierarchy, declare the hierarchy at the appropriate **top-level or member level**.
- If you only need two implementations inside a method, you can use an abstract local base class plus local concrete subclasses, but **without using the sealed modifier**.
- If a simple closed set of values is required, consider a local enum or nested enum depending on scope, rather than forcing a sealed local class.

## 29. Comparing Local Classes, Member Inner Classes, and Static Nested Classes

Here is a table to prevent confusion during code reviews:

| Example | What kind is it? | Access on declaration? | `static` on declaration? |
| --- | --- | --- | --- |
| `class Host { private class Inner {} }` | Member inner | `private` is valid | Cannot be used at the same time for it to remain inner |
| `class Host { private static class Helper {} }` | Static nested member | `private` is valid | Valid |
| `void m() { class Local {} }` | Local normal | Cannot use public/protected/private | Not allowed |
| `static void m() { class Local {} }` | Local normal in a static context | Cannot use access modifiers | Not allowed |
| `void m() { final class Local {} }` | Final local normal | `final` is valid | Not allowed |
| `void m() { abstract class Local {} }` | Abstract local normal | `abstract` is valid | Not allowed |
| `void m() { record R(int x) {} }` | Local record | Cannot use access modifiers | Implicitly static; do not write `static` |
| `void m() { interface I {} }` | Local interface | Cannot use access modifiers | Implicitly static; do not write `static` |

**Determine this from the declaration position.** The same name `Helper` placed in a class body versus a method block represents two different cases.

## 30. Scope of a Local Class Name

A local class has a **name within a local scope**. To use the `Local` type, code must be inside the scope where this name is visible according to lexical scope rules.

Example:

```java
void process() {
    class Local {
    }

    Local here = new Local();
}

void other() {
    // Local there = new Local(); // Name Local is not visible.
}
```

Even though a class file for the local class may be generated by the compiler, the name `Local` in source code **does not become a member `Outer.Local`**.

### Can a Local Class Be Returned?

Yes, via an interface/superclass with appropriate visibility:

```java
Runnable buildTask() {
    class LocalTask implements Runnable {
        @Override
        public void run() {
            System.out.println("done");
        }
    }

    return new LocalTask();
}
```

The caller holds the `Runnable` and calls `run()` after the method returns; the **runtime object remains alive** as long as it is reachable, even though the local class name is not visible outside the block.

## 31. Runnable: Returning a Local Class Instance via an Interface

Save **`LocalReturnScopeDemo.java`**:

```java
public class LocalReturnScopeDemo {
    static Runnable makeTask(String message) {
        class LocalTask implements Runnable {
            @Override
            public void run() {
                System.out.println(message);
            }
        }

        return new LocalTask();
    }

    public static void main(String[] args) {
        Runnable first = makeTask("first");
        Runnable second = makeTask("second");

        first.run();
        second.run();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalReturnScopeDemo.java
java LocalReturnScopeDemo
```

Stdout:

```text
first
second
```

`message` is captured because it is effectively final. `main` does not need to, and cannot, refer to the name `LocalTask` in its source scope.

### Why Not Add `public class LocalTask`?

Adding `public` before a local class declaration **does not expose the type**; it only causes a compilation error. If you want a named reusable API, move the type to an appropriate member class or top-level class.

## 32. Local Classes in Constructors and Initializer Blocks

Methods are not the only places with blocks for local class declarations. A constructor or initializer block can contain a valid local class.

Constructor snippet example:

```java
class Service {
    private final String name;

    Service(String source) {
        class Normalizer {
            String normalize() {
                return source.trim();
            }
        }

        name = new Normalizer().normalize();
    }
}
```

`Normalizer` only has scope inside the constructor block and captures the effectively final `source`.

**Do not confuse with a member class:** even though the class appears in the source body of Service, it is still **inside the constructor block**, so you cannot use `private class Normalizer` or `static class Normalizer`.

### Runnable

Save **`ConstructorLocalDemo.java`**:

```java
public class ConstructorLocalDemo {
    private final String name;

    ConstructorLocalDemo(String source) {
        class Normalizer {
            String normalize() {
                return source.trim().toUpperCase(
                        java.util.Locale.ROOT);
            }
        }

        name = new Normalizer().normalize();
    }

    public static void main(String[] args) {
        ConstructorLocalDemo value =
                new ConstructorLocalDemo(" java ");

        System.out.println(value.name);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ConstructorLocalDemo.java
java ConstructorLocalDemo
```

Stdout:

```text
JAVA
```

In the snippet, `source` is validly captured and the local class only serves to construct state for the constructor.

## 33. Reflection: `isLocalClass` Does Not Depend on the `static` Modifier

A local normal class can be classified using `Class.isLocalClass()`.

If the class has a static method/field in Java 17, it **is still a local class**. The `static` modifier of a member field/method does not cause `Class.getModifiers()` of the local type to report it as a static nested member class.

Useful methods:
- `Class.isLocalClass()`: whether it is a local class.
- `Class.isMemberClass()`: whether it is a member class.
- `Class.isAnonymousClass()`: whether it is an anonymous class.
- `Class.getEnclosingMethod()`/`getEnclosingConstructor()`: information on the lexical enclosing context when present.
- `Modifier.isStatic(clazz.getModifiers())`: the modifier at the **class level**, not the static members of that class.

### Runnable

Save **`LocalReflectionDemo.java`**:

```java
import java.lang.reflect.Modifier;

public class LocalReflectionDemo {
    static void inspect() {
        final class Local {
            static int number() {
                return 7;
            }
        }

        Class<?> type = Local.class;

        System.out.println(type.isLocalClass());
        System.out.println(type.isMemberClass());
        System.out.println(Modifier.isStatic(type.getModifiers()));
        System.out.println(Local.number());
    }

    public static void main(String[] args) {
        inspect();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalReflectionDemo.java
java LocalReflectionDemo
```

**Stdout:**

```text
true
false
false
7
```

`Local.number()` is a static method, yet **Local itself is not declared static**. That is the Java 17 distinction to understand.

Do not print `type.getName()` expecting a fixed value, because generated binary names of local classes depend on compiler/toolchain details.

## 34. Differences When Running `javac` with `--release`

Running:

```bash
javac --release 17 -encoding UTF-8 LocalStaticMembersDemo.java
```

requests syntax and APIs matching **Java 17**.

In a project still built with an older source level, such as Java 8, code containing a static method or non-constant static field inside a local normal class will not be accepted under the older source rules.

**`--release` is not just the JVM runtime version**: it instructs the compiler to select the language/API compatibility of the target release.

### Common Pitfalls

- The IDE uses JDK 21, but the project source language level is 8: Java 17 code can still be rejected by the IDE/compiler.
- Maven/Gradle is configured with `release = 8` even though a newer JDK is installed on the machine: the Java 17 examples in this lesson will be invalid under that configuration.
- Copying an example from Java 8 about static member restrictions and concluding “Java 17 prohibits it too”: incorrect.
- Trying to fix the error by writing `static class Local`: still wrong even on Java 17.

**When diagnosing errors, examine both the position of `static` and the release target.**

## 35. Do Not Use Static Members in Local Classes Just Because the Language Allows Them

In Java 17, the following syntax is valid:

```java
void run() {
    class Local {
        static int total;
    }
}
```

However, from a design standpoint:
- Static mutable state has a lifetime/class-loading behavior different from a call stack frame.
- Calling a method multiple times **does not create a separate new class type for each invocation** under Java class declaration semantics.
- A static field is not automatically a “local variable per method invocation”.
- Mutable static fields may require synchronization if used concurrently.
- The local type name exists only inside the block, so exposing the type's static API externally is not convenient either.

If you only want a temporary accumulator within a single method call, use a **local variable** or an object instance depending on your needs, rather than making it a static field of a local class.

### Are Static Constants More Reasonable?

`static final int LIMIT = 10` inside a local class can be valid and helps group the constant with helper code. However, if the constant is shared across multiple methods, a private static final field of the enclosing class can make the intent clearer.

## 36. Static State Persists Across Method Calls

Save **`LocalStaticLifetimeDemo.java`**:

```java
public class LocalStaticLifetimeDemo {
    static int next() {
        class Local {
            static int counter = 0;

            static int increment() {
                return ++counter;
            }
        }

        return Local.increment();
    }

    public static void main(String[] args) {
        System.out.println(next());
        System.out.println(next());
        System.out.println(next());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalStaticLifetimeDemo.java
java LocalStaticLifetimeDemo
```

**Stdout:**

```text
1
2
3
```

A local class declaration in source code is compiled into a type with static state; returning from the `next()` method **does not reset the static field**. `counter` is not a per-call `int counter = 0` local variable.

### Do Not Use This Example as a Concurrent Counter

`++counter` is not an atomic increment across multiple threads. The example only runs sequentially. If a real application needs a thread-safe counter, use synchronization or `AtomicInteger` with an appropriate scope/lifecycle.

## 37. Avoid Confusing Local Normal Classes with Anonymous Classes and Lambdas

An anonymous class:

```java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("done");
    }
};
```

has no named class declaration like `Local`, so there is no place to write modifiers such as `public class Local`.

A lambda:

```java
Runnable task = () -> System.out.println("done");
```

is not a local class declaration. It has its own rules regarding functional interfaces, lexical `this`, and capture.

**If a problem asks about modifiers of a “local normal class”**, first determine whether there is a `class Local { ... }` line inside a block. Do not use rules for lambdas or anonymous classes to answer in place of a local normal class.

## 38. Classifying Errors by Where the Modifier Appears

Consider the following cases:

**A. Error at the local class declaration**

```java
void f() {
    private class Local {
    }
}
```

Error because `private` is not allowed on a local declaration.

**B. Error at the local class declaration**

```java
void f() {
    static class Local {
    }
}
```

Error because `static` is on the local normal class declaration itself.

**C. Valid in Java 17**

```java
void f() {
    class Local {
        private static int value = 7;

        static int read() {
            return value;
        }
    }

    System.out.println(Local.read());
}
```

`private` is a field modifier, `static` is a field/method modifier; the local class declaration has no prohibited modifiers.

**D. Static context error**

```java
void f() {
    int captured = 7;

    class Local {
        static int read() {
            // return captured; // Invalid.
            return 0;
        }
    }
}
```

The error is that the static method accesses a captured local variable; not because a local class forbids static methods.

Snippets A/B are **compile-negative snippets**; do not place them directly into the same source file used to run examples C/D.

## 39. Diagnostic Table by Compiler Message

| Issue | Root Cause | Fix |
| --- | --- | --- |
| `modifier private not allowed here` when writing `private class Local` | Local type is not a member | Remove the modifier or change to a member class as needed |
| `modifier static not allowed here` when writing `static class Local` | `static` is prohibited on a local type declaration | Remove `static` from the class line |
| Cannot compile `sealed class Local` | Local declarations forbid sealed | Move the sealed hierarchy to member/top-level scope |
| Cannot compile `abstract final class Local` | Conflicting modifiers | Choose abstract or final |
| Cannot `new AbstractLocal()` | The class is abstract | Create a concrete subclass |
| Static method cannot read `offset` | Static context does not capture enclosing local variables | Pass as a parameter or use an instance method |
| Static method cannot read `Outer.this` | No enclosing instance in a static member context | Pass an Outer reference |
| `threshold` is captured but reassigned | Not effectively final | Keep the variable from being reassigned or change the data flow |
| Local record reads enclosing local variable | Record is implicitly static | Pass via a component/parameter |
| Local interface attempts to write `static interface` | `static` on a local declaration is prohibited | Remove the keyword; it is implicitly static |
| Assuming static field resets on every method call | Static state belongs to the local type | Use local/instance state if needed per invocation |
| Older compiler forbids static methods in a local class | Source release prior to Java 16 | Identify the target release or use a compatible alternative |
| `class Local` is not visible from another method | Lexical scope of the local type | Return an interface or extract to a member/top-level class |
| Inside Local there is a public method, but the caller cannot use the name Local | Visibility of the type differs from the method member | Expose an appropriate interface/supertype |

## 40. Exercise 1 — Basic Modifier Multiple-Choice

In Java 17, which option is allowed **before `class Local` declared inside a method block**?

A. `public`  
B. `private`  
C. `final`  
D. `static`

**Answer: C.** `final` is valid. `public`, `private`, and `static` are prohibited on a local normal class declaration. If `abstract` is present, it can also be valid on its own.

## 41. Exercise 2 — Is `protected` Valid?

```java
void run() {
    protected class Local {
    }
}
```

**Answer:** Does not compile. `protected` is an access modifier appropriate for a member class, not for a local class.

## 42. Exercise 3 — Static Method of a Java 17 Local Class

```java
void run() {
    class Local {
        static int twice(int x) {
            return x * 2;
        }
    }

    System.out.println(Local.twice(4));
}
```

**Answer:** Valid in Java 17; prints `8`. `static` is attached to the **method**, not placed before `class Local`.

## 43. Exercise 4 — Static Method of a Java 8 Local Class

The same snippet from Exercise 3 is compiled with Java 8 source level.

**Answer:** Java 8 rules do not allow a local inner class to declare such a static method. Do not apply the Java 8 conclusion to `--release 17`.

## 44. Exercise 5 — Distinguishing the Position of `static`

```java
class Outer {
    static class Member {
    }

    void method() {
        class Local {
        }
    }
}
```

**Answer:** `static` is valid because `Member` is a member nested class. `Local` is declared inside a block, not as a member class, so `static` cannot be added before `class Local`.

## 45. Exercise 6 — Local final and a Mutable Class

A `final class Local` has a field `int count` and a method that increments count.

**Answer:** The class is still mutable. `final` on a class only prohibits subclassing, not updating instance fields.

## 46. Exercise 7 — Local abstract

```java
void run() {
    abstract class Local {
        abstract void execute();
    }
}
```

**Answer:** The declaration is valid. However, `new Local()` is invalid because it is abstract; a concrete subclass is needed to implement the method.

## 47. Exercise 8 — `abstract final`

```java
void run() {
    abstract final class Local {
    }
}
```

**Answer:** Does not compile due to two conflicting class modifiers. It is not because the class is local; this combination is also invalid for other normal classes.

## 48. Exercise 9 — Private Field in a Local Class

```java
void run() {
    class Local {
        private int count;
    }
}
```

**Answer:** Valid. `private` is the modifier of the **field count**, not of the `class Local` declaration.

## 49. Exercise 10 — Public Method in a Local Class

```java
void run() {
    class Local {
        public int answer() {
            return 42;
        }
    }
}
```

**Answer:** Valid. `public` belongs to the `answer` method and does not make the Local type a public member/top-level type.

## 50. Exercise 11 — Java 17 Static Initializer

```java
void run() {
    class Local {
        static int value;
        static {
            value = 7;
        }
    }
}
```

**Answer:** Valid in Java 17. The static initializer/field are **members/declarations inside** the local inner class, not `static` on the local class declaration.

## 51. Exercise 12 — Local Static Nested Member Type

```java
void run() {
    class Local {
        static class Detail {
        }
    }
}
```

**Answer:** Valid in Java 17. `Detail` is a static nested member type inside Local; Local remains a local normal class without static on its declaration.

## 52. Exercise 13 — Static Method Capturing a Local Variable?

```java
void run() {
    int factor = 2;

    class Local {
        static int compute() {
            // return factor * 10;
            return 0;
        }
    }
}
```

**Answer:** If you uncomment it to return `factor * 10`, it will be rejected by the compiler. A static method does not capture a local variable from the enclosing method across a static context boundary. Pass factor as a parameter.

## 53. Exercise 14 — Instance Method Capturing a Local Variable?

```java
void run() {
    int factor = 2;

    class Local {
        int compute() {
            return factor * 10;
        }
    }

    System.out.println(new Local().compute());
}
```

**Answer:** Valid and prints `20`, because factor is effectively final and is used inside an appropriate instance method.

## 54. Exercise 15 — Captured Variable Is Reassigned

```java
void run() {
    int factor = 2;

    class Local {
        int compute() {
            return factor;
        }
    }

    factor = 3;
}
```

**Answer:** Does not compile because factor is not effectively final. Remove the reassignment or change the design; it is not an error caused by the local class lacking `public`.

## 55. Exercise 16 — Local Record

```java
void run() {
    record Point(int x, int y) {
    }
}
```

**Answer:** Valid in Java 17. A local record is implicitly static and is not a local normal inner class.

## 56. Exercise 17 — Writing `static record`?

```java
void run() {
    static record Point(int x, int y) {
    }
}
```

**Answer:** Invalid. The `static` modifier on a local declaration is prohibited, even though a local record itself is implicitly static.

## 57. Exercise 18 — Local Enum

```java
void run() {
    enum Status {
        NEW, DONE
    }
}
```

**Answer:** Valid. A local enum is implicitly static; you neither need nor are allowed to write `static` before `enum`.

## 58. Exercise 19 — Local Interface

```java
void run() {
    interface Rule {
        boolean allows(int n);
    }
}
```

**Answer:** Valid in Java 17. A local normal interface is implicitly static and does not capture outer local variables in the way a local normal inner class does.

## 59. Exercise 20 — Local Sealed Hierarchy

```java
void run() {
    sealed class Parent permits Child {
    }

    final class Child extends Parent {
    }
}
```

**Answer:** Invalid; JLS `14.3 prohibits `sealed` on a local class declaration. If you want a sealed hierarchy, organize it as an appropriate member or top-level hierarchy.

## 60. Exercise 21 — Adding `private` to Hide Local?

A developer wants a local type to be visible only inside a method, so they write `private class Local`.

**Answer:** Unnecessary and invalid. The local type name is already restricted by lexical scope; remove `private`. If you want a class hidden at the enclosing class level yet usable from multiple methods, choose an appropriate `private static class MemberHelper`.

## 61. Exercise 22 — Does Static Local State Reset on Each Call?

A method declares a local class with `static int n = 0` and a static method that increments n. Call the method three times within the same class loader.

**Answer:** `n` does not automatically reset to 0 after each invocation. Static state belongs to the local class type, not to each method stack frame.

## 62. Exercise 23 — Reflection and Static Members

A local class has `static void run()`. Does `clazz.isLocalClass()` become false?

**Answer:** No. It is still a local class due to its declaration location; `isLocalClass()` can be true and `Modifier.isStatic(clazz.getModifiers())` is not required to be true because a static method is not a class-level static modifier.

## 63. Exercise 24 — Annotation

```java
void run() {
    @Deprecated
    class Local {
    }
}
```

**Answer:** Can be valid, because the annotation applies to an appropriate type declaration. An annotation is not the same as a `private/public/protected` access modifier.

## 64. Exercise 25 — Enclosing Instance

A local normal class in an instance method uses `Outer.this.name`; afterward, the entire block is moved into a static method.

**Answer:** `Outer.this` cannot be used in a static method context because there is no enclosing Outer instance. You need an explicit Outer reference or to keep the instance context.

## 65. Exercise 26 — Choosing Another Design When a Public API Is Needed

A local class `Validator` needs to be called directly by name from other packages.

**Answer:** A local class does not expose its type name outside its lexical block. You should move the logic into a public/package-private top-level class, an accessible member nested type, or expose an appropriate interface/factory; it cannot be solved with `public class Validator` inside the method.

## 66. Exercise 27 — Distinguishing Compile Errors from Runtime Behavior

Given a local class with a static initializer and counter that is valid in Java 17. Someone says, “It is definitely an error because a local class cannot be static”.

**Answer:** You need to point out the exact **position of `static`**. Before `class Local`, it is an error; inside the body on a static field/method/initializer, Java 17 allows it. Only after the code compiles should you discuss lifetime/static initialization behavior.

## 67. Exercise 28 — Static Variable in an Enclosing Method?

```java
void run() {
    static int count = 0;
}
```

**Answer:** Invalid. Java does not support static local variable declarations like C. This is a rule for **local variables**, which differs from `static int count` placed **inside a local class** in Java 17.

## 68. Exercise 29 — Should You Create a Static Counter Using a Local Class?

A service needs a thread-safe global counter. A developer places a mutable static field inside a local class because only one method uses it.

**Answer:** The syntax may be valid in Java 17, but the design should consider concurrency, discoverability, initialization, and ownership. A properly named dedicated class/field with `AtomicInteger` or proper synchronization is usually clearer.

## 69. Exercise 30 — Modifiers Applied at Three Different Levels

Consider three snippets:
- `private static class Helper` placed directly in the class body.
- `class Local { static int x; }` placed in a method body.
- `static class Local {}` placed in a method body.

**Answer:** The first snippet is valid for a member nested class; the second is valid in Java 17 because the static modifier belongs to the **field**; the third is wrong because the static modifier is attached to the **local class declaration**.

## 70. Study and Source Code Review Checklist

1. Is the `class Local` declaration **inside a block**, or directly in the class body?
2. If it is inside a block, is it a **local normal class**?
3. Are `public/protected/private` placed **before `class Local`**? If so: error.
4. Is `static` placed **before `class Local`**? If so: error.
5. Are `sealed/non-sealed` placed on the local declaration? If so: error.
6. Is `final` placed on the Local declaration? Valid, but prohibits extending it.
7. Is `abstract` placed on the Local declaration? Valid, but cannot be instantiated directly with new.
8. Are `abstract final` used together? If so: error.
9. Is there an annotation before the declaration? Have you checked `@Target`?
10. Are you using `strictfp` and aware that Java 17 is always strict floating-point?
11. Have you distinguished **modifiers of the class declaration** from **modifiers of fields/methods**?
12. If there is a static field inside Local, is the project target **Java 16+**?
13. If there is a static method inside Local, does that code need to capture enclosing method variables?
14. If there is a static initializer inside Local, are class initialization and lifetime clear?
15. If there is a static nested member type inside Local, have you distinguished it from `static class Local`?
16. Is there static mutable state that requires synchronization under concurrency?
17. Do you understand that a static field does not reset on each method invocation?
18. Is the local class located in a static method or an instance method?
19. If in a static method, is there accidental access to `Outer.this` or an unqualified instance field?
20. Does the instance method of the local class properly capture final/effectively final variables?
21. Is the captured local variable definitely assigned and within valid scope?
22. Is the captured variable reassigned later, causing it to lose effectively final status?
23. Are you confusing a final reference with an immutable referent?
24. Have you distinguished a local normal class from a local record/enum/interface?
25. If it is a local record/enum/interface, do you remember it is **implicitly static** while forbidding the explicit `static` modifier?
26. Is a local record attempting to capture outer local variables?
27. Are you using a local sealed class/interface in violation of `14.3`?
28. Is the local class name being used outside its lexical scope?
29. If a publicly reusable type is needed, should it be extracted to a member/top-level class?
30. Are you relying on the compiler-generated `$1` class name in your reasoning?
31. Have you separated **compile-negative** snippets from runnable files?
32. Does each runnable example have the matching public class/file name and `javac --release 17` command?
33. Have you distinguished compile-time modifier errors from runtime class initialization?
34. When upgrading the source release, have you reviewed old Java 8 guidance about static inner members?
35. Have you consulted the exact JLS SE 17 `14.3 and `8.1.3 when precise justification is needed?

## 71. Key Takeaways

- A **local normal class** is declared inside a block, has a local name, and **is not a member class**.
- On a local normal class **declaration**, Java 17 **prohibits `public`, `protected`, `private`, `static`, `sealed`, and `non-sealed`**.
- `final` and `abstract` are valid **individually**; both cannot be combined on the same class.
- `strictfp` remains in the JLS 17 syntax, but brings no useful change under always-strict floating-point.
- The fact that the class-level modifier `static` is prohibited does not mean Local's body prohibits **static members**.
- **Starting in Java 16**, inner classes, including local normal classes, can declare static fields/methods/initializers/nested types; Java 17 retains this rule.
- A static method in a local class is still a **static context**: it has no `this` and does not capture enclosing local variables.
- A local class in a static method is valid, but that does not permit writing `static class Local`.
- Local interfaces/records/enums can appear in a Java 17 block; they are **implicitly static**, yet `static` cannot be explicitly written on the local declaration.
- The Local name only lives within its lexical scope; an instance can outlive the method via an interface/supertype.
- Read **the exact keyword position** and **the exact Java source release**, rather than concluding with the mantra “local classes cannot be static”.

## Official Reference Documentation

- **Java Language Specification, Java SE 17, `14.3 — Local Class and Interface Declarations:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3
- **JLS Java SE 17, `8.1.1 — Class Modifiers:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1
- **JLS Java SE 17, `8.1.3 — Inner Classes and Enclosing Instances:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3

**Conclusion:** For a local normal class in Java 17, the key restriction lies in the **modifiers on the class declaration line** and the **access context**, rather than prohibiting all static declarations inside the class body. Distinguishing those two levels is the key to writing correct code and understanding why examples from Java 8 can yield a different conclusion from Java 17.
