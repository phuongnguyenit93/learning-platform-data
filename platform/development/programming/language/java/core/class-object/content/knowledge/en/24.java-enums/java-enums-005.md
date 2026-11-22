# Constant-specific class bodies and distinct behavior in Java `enum`

## 1. Objectives and big picture

An `enum` in Java models a **predefined set of named constants**. When the constants differ not only in name or data, but also **in behavior**, Java allows writing a **per-constant body** (*constant-specific class body*).

Basic example:

```java
enum Operation {
    PLUS {
        @Override
        int apply(int a, int b) {
            return a + b;
        }
    },
    MINUS {
        @Override
        int apply(int a, int b) {
            return a - b;
        }
    };

    abstract int apply(int a, int b);
}
```

In the example:

- `PLUS` and `MINUS` are still **two constants of the same enum type `Operation`**.
- The `{ ... }` block after each constant name is a **constant-specific body**, where the behavior of the `apply` method is overridden.
- The `apply` method is declared `abstract` in the enum, forcing the constants to provide an appropriate implementation.
- The caller only holds a variable of type `Operation` and calls `operation.apply(a,b)`; the JVM selects the implementation according to the constant object receiving the call.
- The code does not need `if (operation == PLUS) ...` branching everywhere the calculation is performed.

**Key point:** An enum gives us a **closed set of choices**, while constant-specific bodies allow each choice to hold **the behavior suited to itself**. This is polymorphism applied to enum constants, not a capability for external plugins to register additional constants themselves.

### After this lesson, you should be able to

1. Write valid constant body syntax with or without constructor arguments.
2. Declare a shared abstract method and override it in each constant.
3. Have a default implementation in the enum, and **only override** it in special constants.
4. Combine immutable metadata, constructors, and constant-specific bodies.
5. Distinguish between **enum type**, **constant instance**, and **the implicit subclass created for a constant-specific body**.
6. Compare polymorphic enum design with `switch`, `if/else`, and strategy classes.
7. Identify common errors regarding method signatures, visibility, constructors, mutable state, testing, and maintenance.

The following examples prioritize Java 17+, clearly specifying file names and output. Snippets that only illustrate syntax or errors are marked separately.

## 2. Runnable example: each constant performs an operation

Create the file **`EnumOperationDemo.java`**:

```java
enum Operation {
    ADD {
        @Override
        int apply(int left, int right) {
            return left + right;
        }
    },
    SUBTRACT {
        @Override
        int apply(int left, int right) {
            return left - right;
        }
    },
    MULTIPLY {
        @Override
        int apply(int left, int right) {
            return left * right;
        }
    };

    abstract int apply(int left, int right);
}

public class EnumOperationDemo {
    public static void main(String[] args) {
        for (Operation operation : Operation.values()) {
            System.out.println(operation.name() + "="
                    + operation.apply(8, 3));
        }
    }
}
```

Compile and run:

```bash
javac EnumOperationDemo.java
java EnumOperationDemo
```

**Standard output:**

```text
ADD=11
SUBTRACT=5
MULTIPLY=24
```

**Reading it part by part:**

- `ADD { ... }` does not declare a local variable; it is an enum constant with its own class body.
- `@Override` requires the method in the body to match a method of an appropriate superclass/interface, so it helps the compiler catch typos or wrong signatures.
- `abstract int apply(...)` declares the shared behavior at the enum type level.
- `Operation.values()` returns the constants in declaration order.
- When the loop calls `operation.apply(8,3)`, the **dynamic dispatch** mechanism invokes the override appropriate for the actual constant.

The three constants differ in behavior, yet all still share the **API `Operation.apply(int,int)`**.

## 3. Standard syntax of a constant-specific class body

Conceptual pattern:

```java
enum Example {
    FIRST {
        @Override
        String describe() {
            return "first";
        }
    },
    SECOND {
        @Override
        String describe() {
            return "second";
        }
    };

    abstract String describe();
}
```

Components:

| Component | Meaning |
| --- | --- |
| `enum Example` | Enum type declaration |
| `FIRST`, `SECOND` | Named enum constants |
| `{ ... }` after each constant | Constant-specific class body |
| `@Override` | Compile-time override check |
| `abstract String describe()` | Shared method contract of the enum |
| Comma between constants | Separates constant declarations |
| `;` after the constant list | Separates the constant list from following member declarations |
| Closing `}` | Closes the enum declaration |

When an enum **has no fields/methods declared after the constants**, the `;` can be omitted. When the list is followed by an `abstract method`, constructor, or fields, place the `;` in the exact position shown in the example.

### Does a constant-specific class body have a class name?

There is no standalone **source-level class name** for clients to use like `new Example.FIRST()` or `extends Example.FIRST`. The Java compiler organizes a constant-specific class body as a form of **implicit/anonymous subclass** of the enum type for the corresponding constant.

An important point when designing APIs: clients work with the `Example` type and the `Example.FIRST` constant, and **do not need to and should not depend on class names generated at the bytecode level**.

## 4. How do constant-specific bodies differ from executable blocks?

These three ways of writing differ:

```java
enum Mode {
    FAST {
        @Override
        int weight() {
            return 2;
        }
    },
    SLOW {
        @Override
        int weight() {
            return 1;
        }
    };

    abstract int weight();
}
```

The block after `FAST` and `SLOW` declares **members for constant-specific subclasses**. It is not a block statement that just runs once and finishes.

Inside the body, you typically write:

- Method overrides.
- Helper instance methods.
- Separate fields if truly needed.
- An instance initializer if truly needed (be cautious about the lifecycle).

You **do not** write standalone statements like `System.out.println("x");` directly in the class body; if you need logic to run when creating the instance, it must belong in an initializer/field initializer/constructor according to Java rules.

### A constant-specific body does not create additional enum constants

`FAST { ... }` is still strictly one constant `Mode.FAST`. Having multiple methods in the body **does not** cause `Mode.values()` to have more elements.

## 5. Why is an `abstract method` a strong contract?

For an enum with multiple separate strategies, one approach is to declare an abstract method on the enum type:

```java
enum Choice {
    A {
        @Override
        String text() {
            return "a";
        }
    },
    B {
        @Override
        String text() {
            return "b";
        }
    };

    abstract String text();
}
```

The compiler requires each constant to provide a concrete implementation for the abstract method, because every constant must be an instantiable object.

### When adding a new constant

If you write:

```java
enum BrokenChoice {
    A {
        @Override
        String text() {
            return "a";
        }
    },
    B;

    abstract String text();
}
```

this is a **compile-error illustration**, not a runnable example. `B` has no implementation for `text()`, and the enum itself does not provide a default implementation. The compiler reports a missing abstract method implementation for B.

**Benefit:** When adding an element to the constant set and forgetting to define the required behavior, the error is detected **immediately at compile time**, instead of silently returning null or running incorrectly in an unchecked branch.

### Choosing an abstract or default method?

- If **every constant** must decide its own behavior, declare it abstract.
- If multiple constants share the **same default behavior** and only a few differ, declare a concrete method on the enum and override it where needed.
- If the method only returns metadata with no differing logic, a final field and getter are usually simpler than overriding for each constant.

## 6. Default implementation: not every constant needs a class body

An enum can define a concrete method for every constant to inherit, and only override it in exceptional constants.

Create **`EnumDefaultBehaviorDemo.java`**:

```java
enum Delivery {
    STANDARD,
    ECONOMY,
    EXPRESS {
        @Override
        int days() {
            return 1;
        }
    };

    int days() {
        return 5;
    }
}

public class EnumDefaultBehaviorDemo {
    public static void main(String[] args) {
        for (Delivery method : Delivery.values()) {
            System.out.println(method.name() + "="
                    + method.days());
        }
    }
}
```

```bash
javac EnumDefaultBehaviorDemo.java
java EnumDefaultBehaviorDemo
```

```text
STANDARD=5
ECONOMY=5
EXPRESS=1
```

- STANDARD and ECONOMY **have no separate body**: they use the existing `Delivery.days()`.
- EXPRESS **has a body** and overrides days() to return 1.
- All have static type `Delivery` at the caller, so you only need to call `method.days()`.

**Design consideration:** The default value must genuinely be the right rule for constants that do not override it. If 5 days is not the business default, putting a default in the enum can mask cases where implementation was forgotten. In that case, use an abstract method to force every constant to define it clearly.

## 7. Calling `super` to reuse shared behavior

A constant-specific subclass can override a concrete method and then **call the enum type's implementation via `super`** to extend it rather than replacing it completely.

Create **`EnumSuperMethodDemo.java`**:

```java
enum OutputMode {
    PLAIN,
    DECORATED {
        @Override
        String render(String text) {
            return "[" + super.render(text) + "]";
        }
    };

    String render(String text) {
        return text.trim();
    }
}

public class EnumSuperMethodDemo {
    public static void main(String[] args) {
        System.out.println(OutputMode.PLAIN.render(" Java "));
        System.out.println(OutputMode.DECORATED.render(" Java "));
    }
}
```

```bash
javac EnumSuperMethodDemo.java
java EnumSuperMethodDemo
```

```text
Java
[Java]
```

`super.render(text)` in DECORATED calls the `OutputMode.render` implementation; it does **not** mean calling the PLAIN constant.

**Identifying the receiver:**

- `this` inside a constant-specific body refers to the current constant object.
- `super` uses the corresponding superclass implementation.
- `OutputMode.PLAIN` is an enum constant that is a **different object**.
- Do not use `super` to select another constant; call the constant by name if that is actually the business requirement.

## 8. `this` inside a constant-specific body is the enum constant itself

Enum constants are objects. Inside a method of a constant-specific body, `this` references that constant.

Create **`EnumThisDemo.java`**:

```java
enum Action {
    START {
        @Override
        String describe() {
            return "start:" + this.name();
        }
    },
    STOP {
        @Override
        String describe() {
            return "stop:" + this.name();
        }
    };

    abstract String describe();
}

public class EnumThisDemo {
    public static void main(String[] args) {
        System.out.println(Action.START.describe());
        System.out.println(Action.STOP.describe());
        System.out.println(Action.START == Action.valueOf("START"));
    }
}
```

```bash
javac EnumThisDemo.java
java EnumThisDemo
```

```text
start:START
stop:STOP
true
```

`this.name()` calls the method inherited from `java.lang.Enum`, returning the declared constant name, not the binary name of the constant-specific class.

**Do not confuse:** Having a separate body does not turn an enum constant into a value allowed to be created with `new Action(...)`. `START` and `STOP` remain the unique named constant instances for each name in the enum type.

## 9. Parameterized behavior instead of hard-coding all data in the body

A constant-specific method can accept parameters and compute results based on input, rather than only returning a fixed string.

Create **`EnumDiscountDemo.java`**:

```java
enum Discount {
    NONE {
        @Override
        int finalPrice(int original) {
            return original;
        }
    },
    TEN_PERCENT {
        @Override
        int finalPrice(int original) {
            return original - original / 10;
        }
    },
    FIXED_20 {
        @Override
        int finalPrice(int original) {
            return Math.max(0, original - 20);
        }
    };

    abstract int finalPrice(int original);
}

public class EnumDiscountDemo {
    public static void main(String[] args) {
        int price = 150;

        for (Discount discount : Discount.values()) {
            System.out.println(discount.name() + "="
                    + discount.finalPrice(price));
        }
    }
}
```

```bash
javac EnumDiscountDemo.java
java EnumDiscountDemo
```

```text
NONE=150
TEN_PERCENT=135
FIXED_20=130
```

The example uses integer arithmetic: `original / 10` is rounded toward zero, so the result has the rounding behavior of `int`. This is a dispatch illustration, **not** a general standard way to calculate real money. For money/taxes/fractions, use an appropriate type and rounding policy (for example, BigDecimal with a defined scale/rounding).

**Proper criterion:** If each choice is genuinely a **different calculation rule**, a constant-specific method body expresses that naturally. If they only differ by a coefficient, a field may be simpler.

## 10. When only data differs: prefer fields and constructors

Instead of overriding the getter three times:

```java
enum Priority {
    LOW {
        @Override
        int weight() {
            return 1;
        }
    },
    MEDIUM {
        @Override
        int weight() {
            return 2;
        }
    },
    HIGH {
        @Override
        int weight() {
            return 3;
        }
    };

    abstract int weight();
}
```

you can use metadata:

```java
enum Priority {
    LOW(1), MEDIUM(2), HIGH(3);

    private final int weight;

    Priority(int weight) {
        this.weight = weight;
    }

    int weight() {
        return weight;
    }
}
```

The two snippets are **alternative illustrative enum declarations**; do not place them in the same file with the same type name.

**Why are fields/constructors simpler in this case?** The behavior of `weight()` is the same for all three constants: it just returns a stored value. Using three overrides easily leads to duplication and adds unnecessary code.

### Rules for choosing

| Indicator | Design direction |
| --- | --- |
| Differ only in code, label, weight, or limit | Constructor + final metadata fields |
| Each constant has a genuinely different algorithm | Constant-specific method bodies |
| Most use a default, a few constants are special | Concrete method + selective override |
| Every constant must provide its own policy | Abstract method + override per constant |
| Behavior depends on complex config/runtime services | Consider a strategy/service outside the enum |

## 11. Combining a shared constructor and constant-specific bodies

Constants can accept constructor arguments to store metadata used by their specific logic.

Create **`EnumMetadataAndBehaviorDemo.java`**:

```java
enum Shipping {
    NORMAL("N", 5) {
        @Override
        int fee(int items) {
            return 10 + items;
        }
    },
    EXPRESS("E", 1) {
        @Override
        int fee(int items) {
            return 20 + 3 * items;
        }
    },
    PICKUP("P", 0) {
        @Override
        int fee(int items) {
            return 0;
        }
    };

    private final String code;
    private final int promisedDays;

    Shipping(String code, int promisedDays) {
        this.code = code;
        this.promisedDays = promisedDays;
    }

    String code() {
        return code;
    }

    int promisedDays() {
        return promisedDays;
    }

    abstract int fee(int items);
}

public class EnumMetadataAndBehaviorDemo {
    public static void main(String[] args) {
        for (Shipping shipping : Shipping.values()) {
            System.out.println(
                    shipping.code() + ":"
                    + shipping.promisedDays() + ":"
                    + shipping.fee(2));
        }
    }
}
```

```bash
javac EnumMetadataAndBehaviorDemo.java
java EnumMetadataAndBehaviorDemo
```

```text
N:5:12
E:1:26
P:0:0
```

Meaning of the syntax:

```java
NORMAL("N", 5) { ... }
```

- `("N", 5)` are the arguments for the enum constructor `Shipping(String,int)`.
- `{ ... }` is the constant-specific body of the NORMAL constant.
- Fields `code` and `promisedDays` reside in the **shared enum type**; every constant has the corresponding data.
- The `fee` method truly has different logic for each constant, so abstract polymorphism is valuable.

**Do not write a constructor inside a constant-specific body to receive `"N",5`**. The shared constructor is defined in the enum declaration and is invoked when creating the constant according to Java rules.

## 12. Constructor restrictions with enums

Even though an enum has a constructor, clients **cannot** call `new Shipping("X", 9)`. The set of constant instances is determined by the declaration.

Rules to remember:

1. Enum constructors are **private or package-private in valid syntax**, yet access to create enum instances is restricted by the language; a constructor cannot be `public`/`protected`.
2. If the access modifier is omitted, the enum constructor is treated as having private access according to enum rules.
3. The arguments in the constant declaration initialize the shared metadata.
4. The constructor is executed during the initialization of the constants.
5. A constant-specific body is not a second constructor that clients can call.
6. Avoid relying on mutable static state inside constructors while the enum is in the initialization phase.

The following snippet is **intentionally invalid** and does not run:

```java
enum Invalid {
    ONE;

    // public Invalid() { } // Enum constructors cannot be public.
}
```

**Why?** If a public constructor could be used by callers, the "fixed set of constants" property would be broken. Java blocks this right at the language level.

## 13. Enum methods can implement a shared interface

An enum type can `implements` an interface so callers use the same contract without needing to know the concrete enum.

Create **`EnumInterfaceBehaviorDemo.java`**:

```java
interface Formatter {
    String format(String value);
}

enum FormatStyle implements Formatter {
    PLAIN {
        @Override
        public String format(String value) {
            return value;
        }
    },
    BRACKETED {
        @Override
        public String format(String value) {
            return "[" + value + "]";
        }
    },
    UPPERCASE {
        @Override
        public String format(String value) {
            return value.toUpperCase(
                    java.util.Locale.ROOT);
        }
    };
}

public class EnumInterfaceBehaviorDemo {
    static void show(Formatter formatter, String input) {
        System.out.println(formatter.format(input));
    }

    public static void main(String[] args) {
        show(FormatStyle.PLAIN, "Java");
        show(FormatStyle.BRACKETED, "Java");
        show(FormatStyle.UPPERCASE, "Java");
    }
}
```

```bash
javac EnumInterfaceBehaviorDemo.java
java EnumInterfaceBehaviorDemo
```

```text
Java
[Java]
JAVA
```

- `Formatter` is the interface implemented by `FormatStyle`.
- Each constant body has a public `format` override in accordance with interface method visibility.
- Callers can accept `Formatter` or `FormatStyle`.
- There is no need for three separate top-level classes just to describe three closed strategies of a small domain.

**Warning:** An interface allows multiple other implementations; having `FormatStyle` implement it does not make `FormatStyle` automatically accept additional enum constants from external classes.

## 14. Visibility error when overriding an interface method

Interface methods (excluding private/static special cases) normally have a public contract. An override in a constant body **must not reduce the access level**.

An **incorrect** snippet; placed in a suitable enum, it will not compile:

```java
interface Step {
    String execute();
}

enum InvalidStep implements Step {
    FIRST {
        @Override
        String execute() { // Incorrect: must be public.
            return "first";
        }
    };
}
```

The error is that `String execute()` in the enum constant body has package-private access, which is narrower than the `public` access of the interface method.

Fix it to:

```java
@Override
public String execute() {
    return "first";
}
```

This is a **method override fragment** for the error example above, not a standalone program.

**Be careful with `@Override`:** The annotation helps verify that the method signature matches; it **does not automatically fix** visibility, checked exceptions, or type compatibility.

## 15. You can place shared behavior in the enum type and branch only for certain constants

An enum can declare a shared helper method, used inside overridden methods to avoid duplication.

Create **`EnumSharedHelperDemo.java`**:

```java
enum MessageStyle {
    PLAIN,
    PREFIXED {
        @Override
        String decorate(String input) {
            return "msg:" + normalize(input);
        }
    },
    SUFFIXED {
        @Override
        String decorate(String input) {
            return normalize(input) + ":end";
        }
    };

    static String normalize(String input) {
        return input.trim();
    }

    String decorate(String input) {
        return normalize(input);
    }
}

public class EnumSharedHelperDemo {
    public static void main(String[] args) {
        for (MessageStyle style : MessageStyle.values()) {
            System.out.println(style.decorate(" hi "));
        }
    }
}
```

```bash
javac EnumSharedHelperDemo.java
java EnumSharedHelperDemo
```

```text
hi
msg:hi
hi:end
```

`normalize` is a common static helper of the enum, independent of constant identity. `decorate` is an instance method that a few constants override.

**Good design:** The constants share normalization logic in one place. If the shared helper becomes too complex or needs many dependencies, extract it into a clearly named utility/service instead of turning the enum into a large block of code.

## 16. Constant-specific bodies can call methods/fields of the shared enum

Constants with their own bodies are still objects belonging to the enum type; overridden methods can call members of the enum type according to access rules.

Create **`EnumCommonFieldDemo.java`**:

```java
enum Level {
    BASIC(2) {
        @Override
        int adjusted(int input) {
            return input + base();
        }
    },
    PREMIUM(5) {
        @Override
        int adjusted(int input) {
            return input * base();
        }
    };

    private final int value;

    Level(int value) {
        this.value = value;
    }

    final int base() {
        return value;
    }

    abstract int adjusted(int input);
}

public class EnumCommonFieldDemo {
    public static void main(String[] args) {
        System.out.println(Level.BASIC.adjusted(3));
        System.out.println(Level.PREMIUM.adjusted(3));
    }
}
```

```bash
javac EnumCommonFieldDemo.java
java EnumCommonFieldDemo
```

```text
5
15
```

Here `base()` is a `final` method of the enum, called in common by all constants; it does not need to be overridden and cannot be overridden. `adjusted` is the constant-specific behavior.

**Important distinction:**
- `final` method: cannot be overridden in a constant body.
- `abstract` method: requires implementation in the specific constant.
- Concrete non-final method: a constant body can override it as needed.

## 17. Error when trying to override a `final` method

This is **error-illustration code**, not a program to run:

```java
enum Bad {
    A {
        @Override
        int code() {
            return 2;
        }
    };

    final int code() {
        return 1;
    }
}
```

The compiler rejects overriding `final int code()`.

**Resolution**: If the method needs polymorphism, do not declare it final. If it represents an immutable shared invariant/value, keep it final and create a **different method** for the distinct behavior.

Do not remove `final` just to make the code compile if the method's business contract truly requires immutability.

## 18. Use `switch` or constant-specific behavior?

The same problem of converting a constant into a message can be written in two ways.

### Approach A: handling with an external `switch`

```java
String label(Phase phase) {
    return switch (phase) {
        case CREATED -> "new";
        case RUNNING -> "working";
        case FINISHED -> "done";
    };
}
```

This is an **illustrative method fragment**, assuming `enum Phase { CREATED, RUNNING, FINISHED }` already exists.

### Approach B: method inside the enum

```java
enum Phase {
    CREATED {
        @Override
        String label() {
            return "new";
        }
    },
    RUNNING {
        @Override
        String label() {
            return "working";
        }
    },
    FINISHED {
        @Override
        String label() {
            return "done";
        }
    };

    abstract String label();
}
```

This is an **illustrative enum declaration**, without a main method.

**There is no absolute winner:**

| Criterion | `switch` | Constant-specific method |
| --- | --- | --- |
| Where logic is placed | Inside the consumer/operation | Attached directly to each constant |
| When adding a constant | An exhaustive switch can report missing branches on rebuild | An abstract method can force the new constant to implement it |
| Behavior is just a small mapping | Usually concise | Can create many verbose overrides |
| Multiple consumers need the same behavior | Easy to duplicate switches | Easy to reuse the enum method |
| Logic varies by external dependency/context | Consumer/service may fit better | Easily makes the enum bulky |
| Behavior shares domain ownership with the enum | Can place switch in a domain service | An enum method is usually natural |
| Data differs only by fixed values | A mapping table may be concise | Final fields/constructor may be better |

**Recommendation:** Place behavior in the enum when it is small, pure, tightly coupled to the choice itself, and used in many places. Use a switch when it is **a consumer's perspective** that should not be embedded into the domain type.

## 19. Example comparing polymorphic dispatch and `switch` in the same program

Create **`EnumSwitchVersusOverrideDemo.java`**:

```java
enum Light {
    RED {
        @Override
        String action() {
            return "STOP";
        }
    },
    YELLOW {
        @Override
        String action() {
            return "WAIT";
        }
    },
    GREEN {
        @Override
        String action() {
            return "GO";
        }
    };

    abstract String action();
}

public class EnumSwitchVersusOverrideDemo {
    static String fromSwitch(Light light) {
        return switch (light) {
            case RED -> "STOP";
            case YELLOW -> "WAIT";
            case GREEN -> "GO";
        };
    }

    public static void main(String[] args) {
        for (Light light : Light.values()) {
            System.out.println(light.name() + ":"
                    + light.action().equals(fromSwitch(light)));
        }
    }
}
```

```bash
javac EnumSwitchVersusOverrideDemo.java
java EnumSwitchVersusOverrideDemo
```

```text
RED:true
YELLOW:true
GREEN:true
```

The example verifies that both implementations return the same result on the current set. However, production code **should not keep two duplicate rule sets** unless for equivalence verification; doing so increases the risk of logic divergence when adding a constant.

## 20. A workflow with different state rules

When each state has different transition rules, enum behavior can contain a small *transition* check.

Create **`EnumTransitionBehaviorDemo.java`**:

```java
enum OrderStage {
    NEW {
        @Override
        boolean canMoveTo(OrderStage next) {
            return next == PAID || next == CANCELLED;
        }
    },
    PAID {
        @Override
        boolean canMoveTo(OrderStage next) {
            return next == SENT || next == CANCELLED;
        }
    },
    SENT {
        @Override
        boolean canMoveTo(OrderStage next) {
            return next == DELIVERED;
        }
    },
    DELIVERED {
        @Override
        boolean canMoveTo(OrderStage next) {
            return false;
        }
    },
    CANCELLED {
        @Override
        boolean canMoveTo(OrderStage next) {
            return false;
        }
    };

    abstract boolean canMoveTo(OrderStage next);
}

public class EnumTransitionBehaviorDemo {
    public static void main(String[] args) {
        System.out.println(
                OrderStage.NEW.canMoveTo(OrderStage.PAID));
        System.out.println(
                OrderStage.NEW.canMoveTo(OrderStage.SENT));
        System.out.println(
                OrderStage.PAID.canMoveTo(OrderStage.SENT));
        System.out.println(
                OrderStage.CANCELLED.canMoveTo(OrderStage.PAID));
    }
}
```

```bash
javac EnumTransitionBehaviorDemo.java
java EnumTransitionBehaviorDemo
```

```text
true
false
true
false
```

### Important boundaries

- The enum gives us the **set of states** and small rules on state transition choices.
- Actually changing the state on an Order instance requires additional validation, atomicity, payment/inventory checks, persistence, and authorization per business rules.
- The `canMoveTo` method only computes a boolean and does not modify global state.
- Do not automatically assume that every transition defined by the enum is valid for every order.

An ideal design can keep **pure transition rules** in the enum, while keeping **side effects** in a separate service/aggregate.

## 21. `switch` may be a better fit for behavior depending on external sources

For example, each OrderStage requires checking a different service or database. If you put database client/network logic directly into a constant body, the enum risks becoming singleton objects holding dependencies and complex lifecycles.

Scenario:

- `PAID` needs to call the payment service.
- `SENT` needs the shipment service.
- `CANCELLED` needs the refund service.

These are operations with dependencies that can be configured/tested/mocked. In such cases, a **Strategy interface**, application service, or dispatch table managed via dependency injection may be more appropriate.

**Guiding pattern:**

```java
interface Handler {
    void handle(OrderContext context);
}
```

This is an **illustrative interface fragment**, not code from a specific framework. `OrderContext` is an example type that needs to be declared in a real application.

The enum can still hold the **identifier** of the processing type, while the factory/map from the identifier to Handler is stored in the service. This protects the enum from depending on external systems and allows independent unit tests.

## 22. Implicit subclasses and `getClass()`: an important detail

An enum constant with its own body is implemented via an implicit subclass of the enum. Therefore, the **runtime class** of a constant with its own body is not necessarily `Mode.class` directly.

The proper way to check the **declared enum type** is `getDeclaringClass()`.

Create **`EnumRuntimeClassDemo.java`**:

```java
enum Mode {
    NORMAL,
    SPECIAL {
        @Override
        String label() {
            return "special";
        }
    };

    String label() {
        return "normal";
    }
}

public class EnumRuntimeClassDemo {
    public static void main(String[] args) {
        System.out.println(
                Mode.NORMAL.getClass() == Mode.class);
        System.out.println(
                Mode.SPECIAL.getClass() == Mode.class);

        System.out.println(
                Mode.NORMAL.getDeclaringClass() == Mode.class);
        System.out.println(
                Mode.SPECIAL.getDeclaringClass() == Mode.class);

        System.out.println(Mode.SPECIAL.label());
    }
}
```

```bash
javac EnumRuntimeClassDemo.java
java EnumRuntimeClassDemo
```

```text
true
false
true
true
special
```

**Explanation:**

- NORMAL has no constant-specific body, so its runtime class is directly Mode.
- SPECIAL has a body, so its runtime class is an implicit subclass of Mode.
- `getDeclaringClass()` returns `Mode.class` for both constants.
- The `label` behavior is dispatched according to the actual constant.

**Common mistake:** `constant.getClass() == Mode.class` is not a valid condition for every constant. When you need to determine the enum type meaningfully, use `getDeclaringClass()`.

**Do not print hardcoded compiler-generated class names** with `getClass().getName()` and make them a contract. They are implementation details and can change depending on the compiler/source structure.

## 23. Constant names and identity do not change with constant-specific bodies

Even when a constant has an implicit subclass, `name()`, `ordinal()`, and `values()` remain tied to the enum declaration.

Create **`EnumConstantIdentityDemo.java`**:

```java
enum Operation {
    FIRST {
        @Override
        String answer() {
            return "A";
        }
    },
    SECOND {
        @Override
        String answer() {
            return "B";
        }
    };

    abstract String answer();
}

public class EnumConstantIdentityDemo {
    public static void main(String[] args) {
        for (Operation item : Operation.values()) {
            System.out.println(item.name() + ":"
                    + item.ordinal() + ":"
                    + item.answer());
        }

        System.out.println(
                Operation.valueOf("FIRST") == Operation.FIRST);
    }
}
```

```bash
javac EnumConstantIdentityDemo.java
java EnumConstantIdentityDemo
```

```text
FIRST:0:A
SECOND:1:B
true
```

`name()` is the declared name, `ordinal()` is the 0-based position, and `valueOf` looks up by name. The constant-specific body **does not turn `FIRST` into a new enum type for clients**.

**Do not use `ordinal()` as a business ID/persisted code:** Adding or reordering constants can change that number. Use a fixed `code` field if external compatibility matters.

## 24. `toString()` can also vary per constant

`toString()` is an overridable method. It is useful for display, but it must be distinguished from `name()` and `valueOf`.

Create **`EnumToStringOverrideDemo.java`**:

```java
enum Outcome {
    OK {
        @Override
        public String toString() {
            return "Thanh cong";
        }
    },
    ERROR {
        @Override
        public String toString() {
            return "That bai";
        }
    };
}

public class EnumToStringOverrideDemo {
    public static void main(String[] args) {
        System.out.println(Outcome.OK.name());
        System.out.println(Outcome.OK.toString());
        System.out.println(Outcome.valueOf("ERROR"));
    }
}
```

```bash
javac EnumToStringOverrideDemo.java
java EnumToStringOverrideDemo
```

```text
OK
Thanh cong
That bai
```

The third line, `valueOf("ERROR")`, looks up the constant by **`name`**, yet `println` calls ERROR's `toString()` override, so it prints "That bai".

**Display limitations:** When localization is needed, labels should usually come from resource bundles/message keys instead of hardcoding language strings in the enum. Do not use `toString()` as a stable API/database code if the output may change according to UI requirements.

## 25. Cannot add constants via inheritance or `new` from the outside

Constant-specific class bodies are Java's way of defining different behaviors within a **predefined set of constants**. They do **not** open the enum for subclassing from client code.

The following attempts are **invalid**:

```java
// class NewOperation extends Operation { ... }
// Operation extra = new Operation();
// Operation plugin = registerAtRuntime(...);
```

Besides enums not allowing user-defined subclasses like regular classes, `Operation` is not a plugin registry where additional constants can be added outside the source.

**When is this an advantage?** When the set of choices is closed and all constants must be handled according to a contract. The compiler can help catch missing behavior.

**When is this a limitation?** When third parties need to register previously unknown behavior at runtime: use an interface, concrete strategy implementations, and a separate registry/configuration.

## 26. Adding a new constant: benefits and responsibilities

Suppose the `Operation` enum initially has ADD/SUBTRACT, and later DIVIDE is added:

```java
DIVIDE {
    @Override
    int apply(int a, int b) {
        if (b == 0) {
            throw new ArithmeticException("division by zero");
        }
        return a / b;
    }
}
```

This is an **illustrative constant declaration fragment**, valid only when placed in the constant list of an enum that has the abstract method `apply(int,int)`.

When adding DIVIDE:

- The compiler requires overriding abstract apply if there is no shared implementation.
- Handling for `b == 0` must be explicitly defined.
- Integer division versus floating-point division must be defined.
- Consumers using `switch` may need updating.
- UI, serializers, persisted values, and tests may need to support the new name.
- `values()` now includes one more constant, and `ordinal()` may be affected depending on the insertion position.

**Do not treat "compile PASS" alone as proof of correct business behavior**. The compiler guarantees a syntactically/type-valid method implementation, not that the algorithm is correct.

## 27. Keep enum constants immutable whenever possible

Enum constants have **stable identity**, but instance fields are **not automatically immutable**.

Example:

```java
enum Counter {
    A;

    private int hits;

    void hit() {
        hits++;
    }

    int hits() {
        return hits;
    }
}
```

This is a valid declaration, yet `Counter.A` is a **shared singleton-like enum constant**. If multiple requests call `hit()`, the same `hits` field changes; it is no longer per-request state.

### Even greater risk with constant-specific state

```java
enum BadCache {
    ONE {
        private final java.util.ArrayList<String> items =
                new java.util.ArrayList<>();

        @Override
        int size() {
            items.add("x");
            return items.size();
        }
    };

    abstract int size();
}
```

This is a **valid declaration**, yet intentionally illustrates bad design: each call to `BadCache.ONE.size()` mutates the shared list, making the result depend on call order/count and not thread-safe.

**Recommendations:**

- Prefer final fields holding primitive/immutable metadata.
- Prefer pure methods that depend on inputs, with no side effects.
- Place request/session data in separate class instances.
- If mutable shared state is truly necessary, you must define synchronization, lifecycle, reset policy, and testing; an enum does not make that safe on its own.

## 28. Do not use an enum constant body to store per-user/per-request state

A common design misconception:

> "Each enum constant has its own class body, so can I store a user counter in that class body to create per-request state?"

No. An enum constant object is not re-created for each request. If a mutable field resides in a constant-specific body, that state is tied to the **constant instance** and can be shared across all callers.

An appropriate design:

- Enum `PlanType` describes BASIC/PRO.
- Class `Subscription` describes **a specific subscription**, with userId, startDate, status, limits…
- Method `PlanType.allowedSeats()` can return shared metadata.
- Method `Subscription.useSeat()` mutates the state of **one subscription**, not a system-wide enum constant.

**Distinguish a type/domain category from a domain entity instance.** Constant-specific behavior is suitable for category-level rules; mutable entity state belongs in other objects.

## 29. Execution order: constants are initialized as objects, not run on every call

Each enum constant is created during enum class initialization according to Java rules. A constant-specific body defines method implementations, yet **does not mean statements declared in an initializer run again every time the constant is used**.

Create **`EnumInitializationDemo.java`**:

```java
enum Feature {
    ALPHA {
        @Override
        int score() {
            return base() + 1;
        }
    },
    BETA {
        @Override
        int score() {
            return base() + 2;
        }
    };

    private final int base = 10;

    int base() {
        return base;
    }

    abstract int score();
}

public class EnumInitializationDemo {
    public static void main(String[] args) {
        System.out.println(Feature.ALPHA.score());
        System.out.println(Feature.ALPHA.score());
        System.out.println(Feature.BETA.score());
    }
}
```

```bash
javac EnumInitializationDemo.java
java EnumInitializationDemo
```

```text
11
11
12
```

`Feature.ALPHA` is not re-created between the two calls. The `score` method is called twice on **the same enum constant object**.

**Avoid code with side effects inside constructors/initializers** if you only want computation when calling a method. Conversely, if a method needs caching, design the cache with explicit thread safety/lifecycle rather than implicitly relying on enum initialization.

## 30. Method calls inside a body can use shared members and external helpers

An overridden method can delegate to a pure helper:

```java
@Override
int fee(int items) {
    return FeeRules.express(items);
}
```

This is an **illustrative override fragment**; `FeeRules` is a hypothetical helper class that must be defined in the application.

Every line of business logic does not have to live inside the enum. If the algorithm is large while the set of choices remains closed, the enum can hold:

- Code/label/metadata.
- A short coordinating method.
- Delegation to a pure helper or strategy that already has its own separately tested API.

This keeps **the enum behavior clear**, without turning the enum source file into an overly long block.

## 31. Constant-specific fields and method visibility

A constant-specific body can have its own helper field or method, but external code usually only knows the enum's static type, so **it cannot call constant-specific members not declared in the enum/interface**.

Example:

```java
enum Detail {
    SPECIAL {
        private String helper() {
            return "SPECIAL";
        }

        @Override
        String describe() {
            return helper();
        }
    };

    abstract String describe();
}
```

This is a **valid declaration**, without main.

Valid caller:

```java
String text = Detail.SPECIAL.describe();
```

However, the caller **does not have a direct `Detail.SPECIAL.helper()` API**, because the static type `Detail` does not declare the helper method. The helper is a private implementation detail inside the body.

**Encapsulation lesson:** Putting a method in a constant body does not automatically expose that method as a public API. Place shared contracts on the enum/interface, and keep helpers inside bodies if they only serve one constant.

## 32. `getDeclaringClass()` is better than `getClass()` for identifying the enum type

In a generic system handling enums, you may need to know **which enum declaration** a constant belongs to.

`constant.getDeclaringClass()` returns the enum type in which the constant is declared. Meanwhile, `constant.getClass()` may be an implicit subclass if the constant has its own body.

Diagram:

```text
Operation (enum type)
  |
  +-- ADD constant: runtime class has its own body
  |
  +-- SUBTRACT constant: runtime class has its own body

ADD.getDeclaringClass() == Operation.class
SUBTRACT.getDeclaringClass() == Operation.class
```

**Do not use binary-name string parsing** to extract the constant name or enum type. Use the public API:

- `name()` to get the constant name.
- `getDeclaringClass()` to get the enum type.
- `values()` to iterate over the constants of a specific enum.
- `Enum.valueOf(EnumClass.class, name)` when handling an enum class in generic code.

## 33. Specific restrictions on `equals`, `hashCode`, and `clone`

Enum constants inherit consistent identity rules from `java.lang.Enum`. You should not, and essentially cannot, override these final methods to turn individual constants into arbitrary value objects.

- Enum `equals` has identity semantics.
- `hashCode` is not a stable business ID.
- Enum's `clone()` is final and blocks copying constants via the API.
- Each constant has its own identity and can be compared with `==`.
- `name()` and `ordinal()` are metadata provided by Enum; do not override them to return different data.
- `compareTo` is based on declaration order, not a custom-defined business ranking.

**Reason:** Enums are named constant instances. If clients were allowed to clone them or redefine identity, the "single named constant" model would lose consistency.

**If you need multiple objects with the same category but different state:** create a separate class/record with a field pointing to the enum constant; do not try to clone the enum object.

## 34. Some common compile-time errors

| Intent / error | Why it is wrong | How to fix |
| --- | --- | --- |
| Forgetting `;` before member declarations after constants | Invalid enum body syntax | Add `;` after the constant list |
| Enum has an abstract method, yet a constant does not implement it | Missing concrete behavior | Override it or use a default method |
| Wrong parameter name/method signature in an override | Does not match the method to override | Keep `@Override` so the compiler reports it |
| Overriding an interface method with a package-private method | Reduces visibility compared to public | Use `public` |
| Overriding a method already marked `final` in the enum | Java forbids overriding final | Change the design or create another method |
| Trying to call `new EnumName()` | Enum instances are determined solely by the declaration | Use the constant name |
| Trying to write a constructor inside a constant body using the constant name | A constant body is not an independent enum declaration | Define the constructor in the enum |
| Trying to `extends AnotherEnum` | An enum has the special superclass Enum | Interface or composition |
| Trying to subclass an enum from an external class | Enums are not open to arbitrary subclassing | Strategy/registry if extensibility is needed |
| Using `getClass()==EnumType.class` for every constant | A constant with a body has a runtime subclass | Use `getDeclaringClass()` |
| Trying to call a helper that only exists inside a body via the enum type | The member does not belong to the enum type's API | Define a shared contract |
| Using `ordinal()` as a persisted ID | Reordering constants can change the number | Stable code field |
| Using `toString()` to parse the constant name | toString can be overridden | `name()/valueOf` or an external code parser |
| Placing a mutable list/counter inside a constant body | Shared singleton-like mutable state | Separate per-instance state |
| Assuming every constant body has its own constructor | Constructors belong to the shared enum | Pass arguments at the constant declaration |
| Abstract method returns wrong business result while compiler PASSES | Type checking does not prove the algorithm is correct | Tests for each constant |
| Copying identical logic into multiple overrides | Duplicated behavior | Common helper/default implementation |
| Putting I/O/DB/HTTP into an enum constant | Hard-to-test coupling/lifecycle | External service/strategy |

## 35. Self-test: thoroughly verifying the behavior of every constant

A good practice is to write tests that iterate over `values()` and confirm **every constant** behaves properly, rather than only testing one favorite constant.

Create **`EnumBehaviorSelfTest.java`**:

```java
enum MathAction {
    ADD {
        @Override
        int apply(int a, int b) {
            return a + b;
        }
    },
    SUBTRACT {
        @Override
        int apply(int a, int b) {
            return a - b;
        }
    },
    MAX {
        @Override
        int apply(int a, int b) {
            return Math.max(a, b);
        }
    };

    abstract int apply(int a, int b);
}

public class EnumBehaviorSelfTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        check(MathAction.values().length == 3, "count");
        check(MathAction.ADD.apply(8, 3) == 11, "ADD");
        check(MathAction.SUBTRACT.apply(8, 3) == 5,
                "SUBTRACT");
        check(MathAction.MAX.apply(8, 3) == 8, "MAX");

        for (MathAction action : MathAction.values()) {
            check(action.getDeclaringClass() ==
                    MathAction.class, "declaring class");
            check(action.apply(2, 2) >= 0,
                    "nonnegative sample");
        }

        check(MathAction.valueOf("ADD") == MathAction.ADD,
                "valueOf");
        System.out.println("enum behavior PASS");
    }
}
```

```bash
javac EnumBehaviorSelfTest.java
java EnumBehaviorSelfTest
```

```text
enum behavior PASS
```

`check` throws `AssertionError` directly when false, so it does not depend on the JVM `-ea` flag.

**Test scope:** This is a simple self-test for three operations on specific inputs. In production, add edge cases such as overflow, negative/positive values, equality, or property tests if the contract has broader invariants.

## 36. Testing default method and constant-specific override cases

An example has one concrete default and one override. Tests should verify **both the default path and the override path**.

Create **`EnumDefaultOverrideTest.java`**:

```java
enum Channel {
    EMAIL,
    SMS {
        @Override
        String label() {
            return "short message";
        }
    },
    PUSH;

    String label() {
        return "notification";
    }
}

public class EnumDefaultOverrideTest {
    static void check(boolean ok, String name) {
        if (!ok) {
            throw new AssertionError(name);
        }
    }

    public static void main(String[] args) {
        check(Channel.EMAIL.label().equals("notification"),
                "EMAIL default");
        check(Channel.PUSH.label().equals("notification"),
                "PUSH default");
        check(Channel.SMS.label().equals("short message"),
                "SMS override");

        System.out.println("default and override PASS");
    }
}
```

```bash
javac EnumDefaultOverrideTest.java
java EnumDefaultOverrideTest
```

```text
default and override PASS
```

If a developer later changes the default label, the tests must reflect the new policy. If the SMS override is accidentally removed, the test catches the error immediately, even though the compiler might not complain because the default method already exists.

**Compared to an abstract method:** An abstract declaration catches missing implementations; a default implementation does not catch missing overrides, so testing business behavior is even more important.

## 37. Exercise: write an enum for simple geometry

Build an enum `ShapeType` with two constants `SQUARE` and `RECTANGLE`. Each constant overrides an area calculation method taking two positive integer parameters. Goals:

- `SQUARE.area(side, ignored)` returns `side * side`.
- `RECTANGLE.area(width, height)` returns `width * height`.
- Validate positive inputs.
- Do not add runtime constants outside the declaration.
- Unit tests for each constant, including invalid values.

### A runnable reference solution

File **`ShapeTypeExercise.java`**:

```java
enum ShapeType {
    SQUARE {
        @Override
        int area(int first, int second) {
            requirePositive(first);
            return Math.multiplyExact(first, first);
        }
    },
    RECTANGLE {
        @Override
        int area(int first, int second) {
            requirePositive(first);
            requirePositive(second);
            return Math.multiplyExact(first, second);
        }
    };

    static void requirePositive(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException(
                    "positive dimensions required");
        }
    }

    abstract int area(int first, int second);
}

public class ShapeTypeExercise {
    public static void main(String[] args) {
        System.out.println(ShapeType.SQUARE.area(4, 0));
        System.out.println(ShapeType.RECTANGLE.area(4, 5));

        try {
            ShapeType.RECTANGLE.area(0, 5);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid size");
        }
    }
}
```

```bash
javac ShapeTypeExercise.java
java ShapeTypeExercise
```

```text
16
20
invalid size
```

**Design note:** To represent a square, ignoring the second parameter is a sign that the `area(int,int)` method signature is not optimal. A separate interface/value object could be designed for each shape if the API needs strict dimension representation. The example focuses on **different behavior per enum constant**, not proposing a real-world geometry library.

## 38. Exercise: metadata combined with constant-specific behavior

Implement an enum `Transport` with:

- `WALK("W", 0)`
- `BIKE("B", 1)`
- `CAR("C", 2)`

Each constant has `String code` and `int speedTier`, along with an `estimateMinutes(int kilometers)` method with its own calculation logic. Define it simply: 1 km WALK = 12 minutes, BIKE = 4 minutes, CAR = 2 minutes.

### Runnable solution

Create **`TransportExercise.java`**:

```java
enum Transport {
    WALK("W", 0) {
        @Override
        int estimateMinutes(int kilometers) {
            return Math.multiplyExact(kilometers, 12);
        }
    },
    BIKE("B", 1) {
        @Override
        int estimateMinutes(int kilometers) {
            return Math.multiplyExact(kilometers, 4);
        }
    },
    CAR("C", 2) {
        @Override
        int estimateMinutes(int kilometers) {
            return Math.multiplyExact(kilometers, 2);
        }
    };

    private final String code;
    private final int speedTier;

    Transport(String code, int speedTier) {
        this.code = code;
        this.speedTier = speedTier;
    }

    String code() {
        return code;
    }

    int speedTier() {
        return speedTier;
    }

    abstract int estimateMinutes(int kilometers);
}

public class TransportExercise {
    public static void main(String[] args) {
        for (Transport mode : Transport.values()) {
            System.out.println(mode.code() + ":"
                    + mode.speedTier() + ":"
                    + mode.estimateMinutes(3));
        }
    }
}
```

```bash
javac TransportExercise.java
java TransportExercise
```

```text
W:0:36
B:1:12
C:2:6
```

**Scope:** This is a hypothetical calculation for practicing enum design, not actual travel time; it does not account for traffic, terrain, speed, or rest breaks. In real-world use, you must validate that kilometers is non-negative and define rounding/units.

## 39. When does this approach make code better?

A constant-specific body is valuable when the following criteria hold:

- The set of types is **known in advance and closed per code version**.
- Each type has **different behavior yet shares a single API**.
- The method behavior is a small, stable rule strongly tied to the constant's identity.
- Callers repeat `switch/if` statements on the enum constant itself just to perform the same operation.
- The abstract method contract makes it **hard to forget** the implementation when adding a constant.
- The logic remains short enough to read and understand when viewing the enum declaration.

Good examples: simple arithmetic operators, formatter modes, policy levels, states with pure transition rules, fixed fee calculation methods.

### When should you avoid it?

- Differing only in numbers/labels: use constructor fields.
- Multiple large algorithms that change independently: use a Strategy/service.
- Type set added at runtime by users/plugins: use an interface/registry, do not close it in an enum.
- Behavior with side effects/lifecycle/DI: separate orchestration from the enum.
- Mutable state per request: use separate class instances.
- Multiple consumers wanting different views of the enum, such as UI and persistence: avoid cramming all behavior into the same enum.

**Maintenance principle:** An enum is a place to express a named domain type. Do not turn it into the hub of all business logic merely because method dispatch is convenient.

## 40. Checklist for reading and reviewing constant-specific bodies

- [ ] Does the enum have a **closed set of constants** matching the business domain?
- [ ] Which constants truly differ in behavior, rather than only in metadata?
- [ ] Is `{ ... }` after each constant placed with valid syntax?
- [ ] Is there a `;` after the constant list if the enum declares additional members?
- [ ] Are abstract methods implemented by all required constants?
- [ ] If a method has a default, do the constants that do not override it genuinely accept the default?
- [ ] Is `@Override` used to catch signature mismatches?
- [ ] If implementing an interface, do overridden methods have `public` appropriately?
- [ ] Are `final` methods not overridden?
- [ ] Do the constant name, constructor arguments, and constant-specific body have clear roles?
- [ ] Is the constructor declared only in the enum type, without treating a constant-specific body as a new constructor?
- [ ] Are methods pure, with no mutable shared per-user state?
- [ ] If there are fields, are immutable metadata and defensive copies prioritized when needed?
- [ ] Is `getDeclaringClass()` used when the enum type is needed, rather than inferring from `getClass()`?
- [ ] Is there no reliance on compiler-generated names of constant-specific subclasses?
- [ ] Are `name()`, `ordinal()`, and `toString()` used for their proper purposes?
- [ ] Is `ordinal()` not stored as an external ID?
- [ ] Has each constant been tested, including both default and overridden paths?
- [ ] Does adding a new constant trigger reviews/tests for behavior, switches, and mappings?
- [ ] Is an interface/strategy/service used when behavior is too complex or requires runtime extensibility?
- [ ] Are database/network resources not attached directly to shared enum constants without an explicit policy?
- [ ] Do the file/public class names and stdout of the examples match Java 17+?

## 41. Self-practice questions with answers

**Question 1.** Does `ADD { ... }` in an enum create an additional enum constant besides ADD?

*Answer:* No. That is the constant-specific body of constant ADD; there is still strictly one constant named ADD.

**Question 2.** Is every enum constant required to have its own body?

*Answer:* No. A body is only needed when a constant has its own implementation; other constants can use the default concrete behavior.

**Question 3.** If an enum has `abstract int apply(...)`, what must each constant do?

*Answer:* Provide an appropriate concrete implementation, usually by overriding it in a constant-specific class body.

**Question 4.** If an enum method is concrete and non-final, can a constant override it?

*Answer:* Yes, inside a constant-specific body following override rules.

**Question 5.** What if an enum method is `final`?

*Answer:* A constant-specific subclass cannot override it.

**Question 6.** What does `this` inside a method of a constant-specific body refer to?

*Answer:* The constant object itself that is receiving the call.

**Question 7.** Does `super.method()` in a constant-specific body call another constant's method?

*Answer:* No. It calls the superclass implementation, if the method is applicable.

**Question 8.** Why can `getClass() == EnumType.class` be false?

*Answer:* A constant with its own body has an implicit runtime subclass; use `getDeclaringClass()` to obtain the enum declaration type.

**Question 9.** What does `name()` on a constant with its own body still return?

*Answer:* The declared enum constant name, for example `ADD`.

**Question 10.** Where are constructor parameters `ADD("A",1) { ... }` received?

*Answer:* In the enum type's constructor, not in a constructor declared by the constant body itself.

**Question 11.** What access level does an enum constant implementing an interface method need?

*Answer:* The override must match the interface's visibility, usually `public`.

**Question 12.** When LOW/MEDIUM/HIGH differ only in weight, should you override weight three times or use fields?

*Answer:* Usually a final metadata field/constructor is simpler.

**Question 13.** When is a constant body better than `switch`?

*Answer:* When the behavior is small and tightly bound to the constant, reused across multiple consumers, and placing it on the enum avoids repeating switches.

**Question 14.** When is `switch`/a service better?

*Answer:* When the behavior belongs to a consumer perspective, changes independently, or needs external dependencies/resources.

**Question 15.** Can an enum with constant-specific bodies have constants added at runtime by a plugin?

*Answer:* No. The set of constants remains closed per the enum declaration.

**Question 16.** Should a per-user counter be kept inside an enum constant?

*Answer:* No. The constant instance is shared; state must live in a per-user object.

**Question 17.** Does `valueOf("ADD")` depend on the constant-specific runtime class name?

*Answer:* No, it looks up by the declared enum constant name.

**Question 18.** Can `toString()` return a different label from `name()`?

*Answer:* Yes, toString can be overridden; name still represents the constant name.

**Question 19.** When adding a new constant to an enum with an abstract method, how does the compiler help?

*Answer:* It can report a missing implementation if the new constant does not override it and has no concrete inherited implementation.

**Question 20.** What is the core benefit of a constant-specific class body?

*Answer:* Giving each named constant **its own polymorphic behavior** under a shared enum type API, while the set of constants remains finitely declared.

---

**End-of-lesson takeaway:** With a Java `enum`, **`CONSTANT { ... }`** is **a class body specific to the constant** (*constant-specific class body*), allowing you to override methods and apply **polymorphism** across a closed set of choices. When **every constant** must handle its own behavior, declare a shared `abstract method` so the compiler enforces implementation; when only a few constants are exceptions, use a concrete default method and selective overrides. Combine constructor/final fields for metadata, and use constant-specific bodies for **genuinely different algorithms**. These constants still belong to the same enum type via `getDeclaringClass()` even though `getClass()` may differ for constants with a body, and they **cannot be dynamically extended** by clients. Prefer small, pure behaviors with per-constant tests; for complex rules, mutable per-request state, or external dependencies, consider a separate strategy/service.
