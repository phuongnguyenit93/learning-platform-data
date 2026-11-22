# When Local Classes Help Keep Implementation Details Close to Where They Are Used in Java

## 1. Core Idea

**A local class** is a class declared inside a block, typically directly inside a method, constructor, or initializer block. It lets you group **an implementation slice that serves only a single operation** into a named type with its own fields, constructors, and methods, without having to elevate that type to a broader scope.

Guiding example:

```java
void process() {
    class Helper {
        void firstStep() {
            // ...
        }

        void secondStep() {
            // ...
        }
    }

    Helper helper = new Helper();
    helper.firstStep();
    helper.secondStep();
}
```

This is an **illustrative snippet**, not a standalone runnable program. The notable point is that the reader sees the `Helper` declaration **right before where it is used**, without having to look up another file/class to understand a detail that only has value inside `process()`.

When is this a good choice?

- The helper is genuinely an **implementation detail of a single method or block**.
- The logic has enough **state or multiple related methods** to warrant placing it in a named class.
- The helper needs to use some **effectively final parameters or local variables** right at the declaration site.
- There is a stable interface/superclass that the helper implements, while **the concrete type does not need to be exposed in the API**.
- Making the helper a member/top-level class would increase the number of concepts readers have to look up while **providing no genuine reuse**.

When should you avoid it?

- Only a very short expression/behavior suited to a **lambda** is needed.
- A helper is actually used by **multiple methods** or multiple modules.
- The implementation is large/complex enough that leaving it in the middle of the method makes reading the main flow harder.
- The helper needs a public, independently testable API with a type name accessible from multiple places.
- A static nested class that receives dependencies explicitly would be simpler than a local class capturing too many variables.

> **The goal of a local class is not to write fewer lines at all costs, but to keep a supporting idea right where it serves, while still having a sufficiently clear named structure.**

This article presents selection criteria, standalone compilable/runnable Java 17+ examples, capture and scope boundaries, state management, and how to organize code to avoid turning a local class into a “large class hidden inside a method”.

## 2. Three Levels for Placing a Helper

When a piece of logic begins to have an identity of its own, we typically consider three containing scopes:

| Location | Suitable when | Cost/warnings |
| --- | --- | --- |
| **Local class** inside a method | Used by only one workflow; needs its own methods/state | The type name cannot be used outside the block; the method may become too long |
| **Member class** or **static nested class** | Reused by a few methods in the enclosing class; responsibility belongs to the class | Increases the number of members, potentially widening the surface unnecessarily |
| **Top-level class** | Reused across multiple modules; has an independent API and tests | Adds another file and a broader level of abstraction |

A more “hidden” class is not automatically better. The principle is to **place an abstraction at the narrowest scope that still fits its responsibility and reusability**. When only a single method needs the helper, a local class can be a natural narrow level.

### Compared to Code Without a Class

If the helper only wraps a single addition or a single condition, adding a class can make the code longer and increase cognitive load. If the logic has two or three steps, a little mutable state, and a contract of its own, a named class helps give an **identity to that cluster of responsibilities**.

## 3. Runnable Example: A Helper Serving Only One Method

Create the file **`LocalHelperWorkflowDemo.java`**:

```java
import java.util.List;

public class LocalHelperWorkflowDemo {
    static void printAccepted(List<String> inputs) {
        String prefix = "OK:";

        class Checker {
            boolean valid(String item) {
                return item != null && !item.isBlank();
            }

            String present(String item) {
                return prefix + item.trim();
            }
        }

        Checker checker = new Checker();
        for (String item : inputs) {
            if (checker.valid(item)) {
                System.out.println(checker.present(item));
            }
        }
    }

    public static void main(String[] args) {
        printAccepted(List.of(" Java ", "", " OOP "));
    }
}
```

```bash
javac LocalHelperWorkflowDemo.java
java LocalHelperWorkflowDemo
```

**Standard output:**

```text
OK:Java
OK:OOP
```

Here:

1. `Checker` has two related responsibilities: **checking** and **presentation**.
2. It is only meaningful inside `printAccepted`.
3. The variable `prefix` has a fixed value per call and is used by the local class because it is effectively final.
4. There is no need to add a `Checker` member to `LocalHelperWorkflowDemo`, because the other methods do not currently use that helper.
5. The primary method reads like a workflow: create Checker, iterate through the inputs, check validity, and print the result.

**A detail about the data:** `List.of(...)` does not accept null elements; this example tests an empty string, not null. The `valid` method still handles null if a caller passes a List implementation that contains null.

### Design Value

The name `Checker` clearly conveys “this is a small object dedicated to handling two operations of the workflow”. It can replace repeated conditional/string-assembly snippets directly inside a method. However, if the helper only has a single line `item.trim()` and not much logic, creating such a class is not necessarily worthwhile.

## 4. When Is a Local Class Better Than a Lambda?

A lambda is well suited for a short function matching a functional interface:

```java
java.util.function.Predicate<String> nonBlank =
        text -> text != null && !text.isBlank();
```

This is a code snippet inside a method. If that predicate is the entire requirement, **a lambda is easier to read** than a local class implementing Predicate with a method of a few lines.

A local class is worth considering when **one or more of these signs** are present:

- There are **multiple methods** working together, such as `validate`, `explainFailure`, `normalize`.
- There is **per-instance state** and a constructor that establishes the state.
- You need a **type name that expresses a small responsibility**, helping with reading/tracing behavior.
- You need to implement an interface with **multiple abstract methods** (not a functional interface).
- You need private helper methods to structure the logic, instead of a lambda with a long body.
- You need to create **multiple independent instances** with different configurations/states within the block.

Having mutable state does not automatically mandate a local class: a lambda can capture a mutable object or another state-holder object, but a local class with its own fields often makes **ownership of state** clearer.

## 5. Example: A Local Class with Independent State per Instantiation

An example that a short lambda does not express naturally is a stateful counter for each generator.

Create **`LocalSequenceGeneratorDemo.java`**:

```java
import java.util.function.IntSupplier;

public class LocalSequenceGeneratorDemo {
    static IntSupplier sequence(int start, int step) {
        class Generator implements IntSupplier {
            private int next = start;

            @Override
            public int getAsInt() {
                int result = next;
                next += step;
                return result;
            }
        }

        return new Generator();
    }

    public static void main(String[] args) {
        IntSupplier odd = sequence(1, 2);
        IntSupplier hundreds = sequence(100, 10);

        System.out.println(odd.getAsInt());
        System.out.println(odd.getAsInt());
        System.out.println(hundreds.getAsInt());
        System.out.println(odd.getAsInt());
        System.out.println(hundreds.getAsInt());
    }
}
```

```bash
javac LocalSequenceGeneratorDemo.java
java LocalSequenceGeneratorDemo
```

```text
1
3
100
5
110
```

`Generator` is a local class declared where the `sequence` factory creates the object. Each call to `new Generator()` creates **an instance with its own `next` field**.

`start` and `step` are **effectively final** method parameters; Generator captures them. The `next` field belongs to each Generator object, so it can change after each `getAsInt()`.

**Concurrency note:** The Generator in the example has a mutable `int next` and is not inherently thread-safe. If this IntSupplier is shared across multiple threads, there must be an appropriate synchronization/atomic policy. The purpose is to illustrate per-instance local-class state, not to promise a concurrent sequence.

### Why Not Promote Generator to the Class Level?

Because the logic for creating Generator only needs to know `start`/`step` and is used through `IntSupplier`. If nowhere else uses the concrete Generator type, keeping the name `Generator` inside `sequence` reduces the surface area and helps the reader focus on the factory contract.

## 6. When Multiple Behaviors Are Needed in the Same Helper

A local class can contain several methods that share the same goal without needing to appear on the interface that the caller uses.

Create **`LocalValidationDemo.java`**:

```java
public class LocalValidationDemo {
    static String describeRegistration(String username, int age) {
        class Validator {
            boolean nameValid() {
                return username != null
                        && !username.isBlank();
            }

            boolean ageValid() {
                return age >= 18 && age <= 120;
            }

            String issue() {
                if (!nameValid()) {
                    return "invalid username";
                }
                if (!ageValid()) {
                    return "invalid age";
                }
                return "accepted";
            }
        }

        Validator validator = new Validator();
        return validator.issue();
    }

    public static void main(String[] args) {
        System.out.println(describeRegistration("An", 20));
        System.out.println(describeRegistration("", 20));
        System.out.println(describeRegistration("Binh", 16));
    }
}
```

```bash
javac LocalValidationDemo.java
java LocalValidationDemo
```

```text
accepted
invalid username
invalid age
```

Having the `nameValid`, `ageValid`, and `issue` methods close together makes it easier to read the invariant of the registration operation. There is no need to create a separate application-wide class named `RegistrationValidator` if **only a single method** needs them and the logic remains compact.

**Point to consider:** If the username/age rules become a business rule used in multiple places (API, UI, batch import), keeping multiple local Validator copies creates a risk of divergence. At that point, you should **extract a reusable service/value validator**, or at least a named nested class and shared tests.

## 7. When a Helper Needs Its Own Configuration and Constructor

A local class is still a class: it has fields, constructors, methods, and initializers just like ordinary classes, subject to the rules that apply to local classes.

Create **`LocalComparatorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

record WorkItem(String code, int urgency) {
}

public class LocalComparatorDemo {
    static List<WorkItem> order(List<WorkItem> input,
                                boolean highestFirst) {
        class WorkOrder implements Comparator<WorkItem> {
            private final int direction;

            WorkOrder(boolean highestFirst) {
                direction = highestFirst ? -1 : 1;
            }

            @Override
            public int compare(WorkItem a, WorkItem b) {
                int priority =
                        Integer.compare(a.urgency(), b.urgency());
                if (priority != 0) {
                    return direction * priority;
                }
                return a.code().compareTo(b.code());
            }
        }

        List<WorkItem> result = new ArrayList<>(input);
        result.sort(new WorkOrder(highestFirst));
        return result;
    }

    public static void main(String[] args) {
        List<WorkItem> items = List.of(
                new WorkItem("B", 2),
                new WorkItem("A", 2),
                new WorkItem("C", 1));

        for (WorkItem item : order(items, true)) {
            System.out.println(item.code() + ":" + item.urgency());
        }
    }
}
```

```bash
javac LocalComparatorDemo.java
java LocalComparatorDemo
```

```text
A:2
B:2
C:1
```

### Why Does This Example Use a Local Class?

- `WorkOrder` is a policy **meant only for the order method**.
- It has a `direction` field initialized via the constructor; the state belongs to the **comparator instance**.
- There is a primary comparison rule (urgency) and a secondary rule (code), so the class name and the `compare` method are meaningful.
- The name WorkOrder does not need to be exposed to other methods.

### When Should You Write It Shorter?

If you only need a simple sort, such as sorting `String` values in ascending order, `Comparator.naturalOrder()` or a lambda/method reference is a better choice. A local class is not mandatory just because we are calling `sort`.

**Design note:** `direction` only takes -1 or +1, and `Integer.compare` returns -1/0/1, so the multiplication here cannot cause overflow. Do not change this to subtraction `a.urgency()-b.urgency()` if there is a risk of overflow.

## 8. When a Helper Implements an Interface Used Outside the Method

A strength of a local class: **hiding the concrete implementation** while returning a contract with a broader scope.

Create **`LocalStrategyFactoryDemo.java`**:

```java
interface TextRule {
    String apply(String input);
}

public class LocalStrategyFactoryDemo {
    static TextRule prefixRule(String prefix) {
        class PrefixRule implements TextRule {
            @Override
            public String apply(String input) {
                return prefix + input;
            }
        }

        return new PrefixRule();
    }

    public static void main(String[] args) {
        TextRule rule = prefixRule("ID-");
        System.out.println(rule.apply("7"));
        System.out.println(rule.apply("8"));
    }
}
```

```bash
javac LocalStrategyFactoryDemo.java
java LocalStrategyFactoryDemo
```

```text
ID-7
ID-8
```

`PrefixRule` has a name only inside `prefixRule`. Users of the factory method only know the `TextRule` interface.

**Important:** Returning from `prefixRule` does not destroy the object or make it lose its behavior. The TextRule-typed reference still holds the PrefixRule instance; the `apply` method still uses the captured `prefix` value.

**This is a concrete encapsulation strategy:** The implementation is kept close to the factory, and the public-facing contract can remain stable. If the implementation is just a single very short method, the lambda `input -> prefix + input` is more concise. A local class provides clearer value when the implementation needs multiple methods/processing steps.

## 9. When a Helper Uses Local Variables: The Effectively Final Rule

A local class can use parameters and local variables of the enclosing method, but the captured local variables/parameters must be **final or effectively final**.

`Effectively final` means the variable is not reassigned in a way that violates the final condition after it has been initialized.

Create **`CapturedThresholdDemo.java`**:

```java
import java.util.function.IntPredicate;

public class CapturedThresholdDemo {
    static IntPredicate atLeast(int threshold) {
        class Minimum implements IntPredicate {
            @Override
            public boolean test(int value) {
                return value >= threshold;
            }
        }

        return new Minimum();
    }

    public static void main(String[] args) {
        IntPredicate rule = atLeast(10);
        System.out.println(rule.test(9));
        System.out.println(rule.test(10));
        System.out.println(rule.test(11));
    }
}
```

```bash
javac CapturedThresholdDemo.java
java CapturedThresholdDemo
```

```text
false
true
true
```

`threshold` is a parameter that receives a value and is not reassigned. The local class `Minimum` is allowed to read it in the `test` method; the instance continues to work after the factory returns.

### Mistake: Reassigning a Captured Variable

The snippet below **will not compile** if uncommented:

```java
void invalid() {
    int threshold = 10;

    class Rule {
        boolean test(int value) {
            return value >= threshold;
        }
    }

    // threshold = 20; // Makes threshold no longer effectively final.
}
```

This is an **error-illustrating method snippet**. It cannot be fixed by changing the local class into a lambda; lambdas also follow the effectively-final rules for captured local variables.

### Need a Mutable Value?

Place mutable state in a **field of the helper object** or in a state-holder object with clear ownership, instead of trying to update a captured local variable. If the state is shared, you must also consider thread safety and mutation aliasing.

## 10. Capturing a Reference Is Not Deep-Copying an Object

A reference variable can be effectively final while the object it points to remains mutable.

Create **`CapturedMutableDependencyDemo.java`**:

```java
public class CapturedMutableDependencyDemo {
    public static void main(String[] args) {
        StringBuilder buffer = new StringBuilder("A");

        class Appender {
            void add(String text) {
                buffer.append(text);
            }

            String content() {
                return buffer.toString();
            }
        }

        Appender helper = new Appender();
        helper.add("1");
        System.out.println(helper.content());

        buffer.append("2");
        System.out.println(helper.content());
    }
}
```

```bash
javac CapturedMutableDependencyDemo.java
java CapturedMutableDependencyDemo
```

```text
A1
A12
```

The `buffer` variable does not change its reference, yet the underlying `StringBuilder` changes its content. The local helper and the enclosing method see **the same object**.

**Selection criterion:** If a local helper captures a mutable dependency, decide whether sharing is intentional or dangerous. For snapshot/immutable processing tasks, copy the data at the appropriate point. **A local class does not automatically create isolation** for captured objects.

## 11. How Does a Named Local Class Help with Logging and Debugging?

Suppose a method processes through three stages:

- Checking the data.
- Computing the result.
- Generating diagnostic messages.

A local class named `Attempt`, `Parser`, or `Rule` can group supporting state and methods. During review, readers understand “this is a supporting idea” and see the invariants together.

However, **do not rely on compiler-generated binary names** such as `Outer$1Attempt` as a stable API. When logs need to identify the operation, define a meaningful label/logical operation name yourself.

Example:

```java
class Attempt {
    private final String operation = "parseOrder";

    String label() {
        return operation;
    }
}
```

This is a local-class **declaration snippet** intended to sit inside a block; the `operation` name is application data, unlike the runtime compiler-generated class name.

### Scope Helps Avoid a Public Surface

The name `Attempt` does not automatically become a member type `Outer.Attempt`. It is confined to the block, so code outside the block cannot accidentally depend on this concrete type. An interface/superclass can be the sole public contract.

## 12. When You Only Need a One-Off Callback: An Anonymous Class Can Be More Natural

If you need an object implementing an interface in just a single expression, without reusing a concrete type name, an **anonymous class** is sometimes a better fit than a local named class.

Create **`AnonymousAlternativeDemo.java`**:

```java
public class AnonymousAlternativeDemo {
    public static void main(String[] args) {
        Runnable action = new Runnable() {
            @Override
            public void run() {
                System.out.println("ANONYMOUS");
            }
        };

        action.run();
    }
}
```

```bash
javac AnonymousAlternativeDemo.java
java AnonymousAlternativeDemo
```

```text
ANONYMOUS
```

With `Runnable`, it is even simpler:

```java
Runnable action = () -> System.out.println("LAMBDA");
```

If the behavior is just one line, using a lambda is usually the most concise.

**A local named class stands out more** when you need to reuse the type name multiple times in the block, create multiple instances, write a constructor, hold multiple fields, or clearly group several helper methods. An anonymous class can declare its own state/methods, but it does not provide a concrete type name to reuse the way a local class does.

## 13. Three Options Solving the Same Problem and Their Differences

Create **`ThreeApproachesDemo.java`**:

```java
import java.util.function.IntUnaryOperator;

public class ThreeApproachesDemo {
    static void demonstrate(int offset) {
        IntUnaryOperator lambda = value -> value + offset;

        IntUnaryOperator anonymous = new IntUnaryOperator() {
            @Override
            public int applyAsInt(int value) {
                return value + offset;
            }
        };

        class LocalAdder implements IntUnaryOperator {
            @Override
            public int applyAsInt(int value) {
                return value + offset;
            }
        }

        IntUnaryOperator named = new LocalAdder();

        System.out.println(lambda.applyAsInt(2));
        System.out.println(anonymous.applyAsInt(2));
        System.out.println(named.applyAsInt(2));
    }

    public static void main(String[] args) {
        demonstrate(5);
    }
}
```

```bash
javac ThreeApproachesDemo.java
java ThreeApproachesDemo
```

```text
7
7
7
```

**All three produce the same result** because the calculation is simple. In this situation, the lambda is the most concise option.

Choosing a local class does not make addition “more correct”; it adds value when the structure is genuinely complex and **a named type makes it easier to understand**.

| Characteristic | Lambda | Anonymous class | Local named class |
| --- | --- | --- | --- |
| Requires a functional interface target | Yes | Not necessarily; can create a subclass/interface implementer | No; declares a class according to the rules |
| Has a source-level name for the implementation | No | No | Yes, within the block |
| Can declare its own constructor | No | Cannot declare a constructor for an anonymous class | Yes |
| Can declare fields/helper methods | State must be placed via capture or a collaborator | Yes | Yes |
| `this` inside the body | Follows the lexical enclosing context | Anonymous object | Local-class object |
| Re-instantiated by name in the same block | Not by type name | Not by type name | Yes |
| Best suited for | Short behavior | An in-place implementation, no name needed | A helper with state/clearly segmented logic |

There is no need to force a single uniform form for all callbacks. **Prioritize the approach in which the goal and scope are most clearly visible.**

## 14. A Local Class Can Create Multiple Instances Right Inside a Method

A local class does not have to be used just to create a single object. When you want multiple helper instances following the same local rules, having a class name is useful.

Create **`MultipleLocalInstancesDemo.java`**:

```java
public class MultipleLocalInstancesDemo {
    public static void main(String[] args) {
        class Accumulator {
            private int total;

            void add(int value) {
                total += value;
            }

            int total() {
                return total;
            }
        }

        Accumulator first = new Accumulator();
        Accumulator second = new Accumulator();

        first.add(10);
        first.add(5);
        second.add(2);

        System.out.println("first=" + first.total());
        System.out.println("second=" + second.total());
    }
}
```

```bash
javac MultipleLocalInstancesDemo.java
java MultipleLocalInstancesDemo
```

```text
first=15
second=2
```

Each Accumulator has its own `total` field. Reusing the `Accumulator` name inside the block makes it clear that the two instances belong to the same kind of helper with independent state.

**This is a mutable class**, not an immutable object. Being local only restricts **name scope**; it does not make fields safe to share across multiple threads or automatically apply defensive copying.

## 15. When an Algorithm Needs Explanation, Place the Class Close to the Algorithm

For example, consider a method that scans a string of characters and collects a token structure. You can extract a **scanner helper** directly inside the method if only one workflow uses it, instead of promoting it to a public API.

Create **`LocalScannerDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class LocalScannerDemo {
    static List<String> words(String input) {
        class Scanner {
            private int position;

            boolean hasMore() {
                skipSpaces();
                return position < input.length();
            }

            String nextWord() {
                skipSpaces();
                int start = position;

                while (position < input.length()
                        && input.charAt(position) != ' ') {
                    position++;
                }
                return input.substring(start, position);
            }

            private void skipSpaces() {
                while (position < input.length()
                        && input.charAt(position) == ' ') {
                    position++;
                }
            }
        }

        Scanner scanner = new Scanner();
        List<String> result = new ArrayList<>();

        while (scanner.hasMore()) {
            result.add(scanner.nextWord());
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println(words("Java  local   class"));
    }
}
```

```bash
javac LocalScannerDemo.java
java LocalScannerDemo
```

```text
[Java, local, class]
```

### Why Is a Scanner Local Class Useful?

- The `hasMore`, `nextWord`, and `skipSpaces` methods jointly manage a single `position` field.
- `position` is each Scanner instance's own state.
- `input` is an effectively final parameter of the `words` method.
- The main flow fits concisely in a few lines: create Scanner, call hasMore/nextWord, and store the results.
- If Scanner is not used outside `words`, placing it right here avoids creating an unnecessarily broad abstraction.

### When Should It Not Be Kept Local?

If word-splitting requirements grow (tabs/newlines, Unicode whitespace, escapes, quotes, token types, error recovery, streaming), the local Scanner can grow long and dominate the entire method. At that point, it should be promoted into a **named reusable scanner class** with its own API/tests. This example only splits tokens on the space character `' '`, and does not claim to be a general-purpose tokenizer.

## 16. Reasonable Complexity: Do Not Let the Helper Swallow the Main Flow

A large local class can cause a method to:

1. Begin with over a hundred lines of helper declarations.
2. Only afterward show the few main lines the reader needs to understand.
3. Force the reader to scroll past many details before knowing what the method does.

That is a sign that **details are being placed in too cramped a space**.

### Review Heuristics

- If the helper is short and belongs to only one workflow, a local class is a good choice.
- If the helper is long yet still belongs to only one workflow, consider a **private method** for pure steps, or a **private static nested class** to keep the main flow easy to read.
- If the helper has its own lifecycle, a multi-argument constructor, complex invariants, or needs to be tested directly, extract it into a named class outside the method.
- If the helper is called from two or more methods, check whether this is genuinely shared logic; avoid copying the local class to multiple places.
- If the helper needs to read a large number of local variables, consider bundling them into immutable configuration/parameters instead of capturing them en masse.

**There is no mandatory line-count threshold.** Evaluate based on readability goals, testability, coupling level, and frequency of change.

## 17. Capturing Many Variables Can Make Dependencies Hidden

For example, a local class references `currency`, `taxRate`, `discount`, `locale`, and `clock`, all from the enclosing method. Although the code compiles if the variables satisfy the effectively-final condition, anyone reading the helper has to inspect the earlier part of the method to understand its dependencies.

A clearer approach is sometimes:

```java
record Options(String currency, int taxPercent) {
}

class Formatter {
    private final Options options;

    Formatter(Options options) {
        this.options = options;
    }

    String format(int amount) {
        return options.currency() + ":" +
                (amount + amount * options.taxPercent() / 100);
    }
}
```

These are **two illustrative type declarations** if placed inside a suitable Java 17 block. With a local record `Options`, a record is implicitly static and does not capture enclosing local variables; it receives data through its components. `Formatter`, meanwhile, receives `Options` through its constructor.

With many dependencies, **explicit parameters** can be clearer than capture. A local class is still useful, but do not use it as a mechanism to “hide inputs” and make the code hard to test.

## 18. A Local Class in an Instance Method Can Access the Enclosing Object

When a local class is declared inside an **instance method** of the outer class, its code can use the enclosing instance when valid.

Create **`LocalClassOuterStateDemo.java`**:

```java
class Account {
    private int balance;

    Account(int balance) {
        this.balance = balance;
    }

    void applyBonus(int amount) {
        class BonusOperation {
            void apply() {
                Account.this.balance += amount;
            }
        }

        new BonusOperation().apply();
    }

    int balance() {
        return balance;
    }
}

public class LocalClassOuterStateDemo {
    public static void main(String[] args) {
        Account account = new Account(100);
        account.applyBonus(15);
        System.out.println(account.balance());
    }
}
```

```bash
javac LocalClassOuterStateDemo.java
java LocalClassOuterStateDemo
```

```text
115
```

- `Account.this` is the enclosing Account instance when `applyBonus` runs.
- `amount` is a captured effectively final method parameter.
- The local class BonusOperation has a name only inside `applyBonus`.
- `this` inside `BonusOperation.apply` is the **BonusOperation object**, not Account. Using `Account.this.balance` clarifies the target of the mutation.

**Design warning:** This is also coupling to outer state. If the helper does not need to automatically see Account, a static nested helper with an explicit dependency can be easier to read/test.

## 19. You Can Still Declare a Local Class Inside a Static Method

A local class **does not require an Outer instance** if declared in a static context, though in that case there is no implicit `Outer.this` to access instance fields.

Create **`StaticLocalClassDemo.java`**:

```java
public class StaticLocalClassDemo {
    static String format(String code) {
        class Formatter {
            String apply() {
                return "[" + code + "]";
            }
        }

        return new Formatter().apply();
    }

    public static void main(String[] args) {
        System.out.println(format("J17"));
    }
}
```

```bash
javac StaticLocalClassDemo.java
java StaticLocalClassDemo
```

```text
[J17]
```

Here `Formatter` captures the `code` parameter without needing an enclosing instance. When a static helper needs instance data, **pass the object through a parameter/constructor** instead of writing an invalid `Outer.this`.

**Do not confuse these:** Having a local class's name restricted to the method block is a rule about **lexical scope**; whether the method is static or instance only affects certain reference/capture context capabilities.

## 20. Local Classes and Constructors: Establishing State Before Use

A local class can define a constructor to check invariants and establish state.

Create **`LocalConstructorDemo.java`**:

```java
import java.util.function.IntUnaryOperator;

public class LocalConstructorDemo {
    static IntUnaryOperator multiplier(int factor) {
        class Multiply implements IntUnaryOperator {
            private final int value;

            Multiply(int value) {
                if (value <= 0) {
                    throw new IllegalArgumentException(
                            "positive factor required");
                }
                this.value = value;
            }

            @Override
            public int applyAsInt(int operand) {
                return Math.multiplyExact(operand, value);
            }
        }

        return new Multiply(factor);
    }

    public static void main(String[] args) {
        IntUnaryOperator twice = multiplier(2);
        System.out.println(twice.applyAsInt(7));

        try {
            multiplier(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid factor rejected");
        }
    }
}
```

```bash
javac LocalConstructorDemo.java
java LocalConstructorDemo
```

```text
14
invalid factor rejected
```

Even though `Multiply` only has a name inside `multiplier`, it still has a proper constructor, a final field, and validation. The return type `IntUnaryOperator` is the external contract.

`Math.multiplyExact` throws `ArithmeticException` on overflow. This is an explicit choice over silent overflow when the domain requires exact arithmetic.

**Choose a local class** when validation/state is only meaningful inside this factory. If other call sites also need to create/check Multiply under a shared contract, consider elevating the abstraction to a broader scope.

## 21. Local Classes Are Not Limited to a Single Instance

A method can declare a local class and then instantiate multiple objects. However, the class name can only be used **within the block where it is in scope**.

Create **`LocalInstanceCollectionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class LocalInstanceCollectionDemo {
    static List<Runnable> tasks() {
        List<Runnable> result = new ArrayList<>();

        class Task implements Runnable {
            private final String name;

            Task(String name) {
                this.name = name;
            }

            @Override
            public void run() {
                System.out.println(name);
            }
        }

        result.add(new Task("ONE"));
        result.add(new Task("TWO"));
        return result;
    }

    public static void main(String[] args) {
        for (Runnable task : tasks()) {
            task.run();
        }

        // Task t; // The name Task is not in scope in main.
    }
}
```

```bash
javac LocalInstanceCollectionDemo.java
java LocalInstanceCollectionDemo
```

```text
ONE
TWO
```

`Task` has a name only inside `tasks`, yet the objects continue to exist when a List<Runnable> holds them after the method returns. The scope of the **type name** does not equate to the lifetime of the **instance**.

If the helper is expected to be passed across a wider system, review whether the concrete type needs its own API/test/lifecycle. An object from a local class can still retain captured values or an enclosing instance reference.

## 22. Name Scope: Only from the Declaration to the End of the Block

Create **`LocalScopeBoundaryDemo.java`**:

```java
public class LocalScopeBoundaryDemo {
    public static void main(String[] args) {
        System.out.println("before local type");

        {
            class Local {
                String value() {
                    return "VISIBLE";
                }
            }

            Local item = new Local();
            System.out.println(item.value());
        }

        System.out.println("after block");
        // Local outside = new Local(); // Invalid.
    }
}
```

```bash
javac LocalScopeBoundaryDemo.java
java LocalScopeBoundaryDemo
```

```text
before local type
VISIBLE
after block
```

The name `Local` is in scope **from its declaration to the end of the immediately enclosing block**. After the block closes, that name cannot be used in the source code of the enclosing block, even though the object can be returned via an interface/superclass.

Two independent blocks or methods can use local classes with the same name because they are two distinct declarations.

**Design assessment:** A narrow scope is an advantage when the implementation is genuinely local. It becomes an inconvenience if shortly afterward you have to find a way to “name the class” in another method — a sign that a broader abstraction should be used.

## 23. A Local Class Can Help Scope a Specialized Algorithm

An algorithm used in only one method sometimes needs a small node/entry type.

Create **`LocalTraversalNodeDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.Deque;

public class LocalTraversalNodeDemo {
    static int sumChain(int[] numbers) {
        class Entry {
            final int value;
            final Entry previous;

            Entry(int value, Entry previous) {
                this.value = value;
                this.previous = previous;
            }
        }

        Entry head = null;
        for (int number : numbers) {
            head = new Entry(number, head);
        }

        int total = 0;
        for (Entry current = head;
             current != null;
             current = current.previous) {
            total += current.value;
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.println(sumChain(new int[] {2, 3, 4}));
    }
}
```

```bash
javac LocalTraversalNodeDemo.java
java LocalTraversalNodeDemo
```

```text
9
```

`Entry` exists as a dedicated type inside `sumChain`; it is not a system-wide domain entity. Code can use `Entry` inside the class's own body for the `previous` field, and after the declaration to create/traverse entries.

**Decision:** If this list/node structure serves only a single algorithm, a local class keeps it close to where it is used. If it becomes a common data structure, do not copy/paste multiple local Entry types; extract it into a reusable type.

**Performance note:** The example allocates an Entry object for each element; for the problem of merely summing an array, a direct summation loop is simpler and has fewer allocations. The example is intended to illustrate how to organize an algorithm *that requires keeping nested nodes/metadata*, not to recommend creating linked nodes just to compute a sum.

## 24. When Is a Local Record Better Than a Stateful Local Class?

Java 17 allows a local **record** for small data whose value is immutable by its component structure, provided the components are also immutable.

Create **`LocalRecordChoiceDemo.java`**:

```java
public class LocalRecordChoiceDemo {
    static String label(String code, int count) {
        record Entry(String code, int count) {
        }

        Entry entry = new Entry(code, count);
        return entry.code() + ":" + entry.count();
    }

    public static void main(String[] args) {
        System.out.println(label("A", 3));
    }
}
```

```bash
javac LocalRecordChoiceDemo.java
java LocalRecordChoiceDemo
```

```text
A:3
```

A local record fits a data carrier with components/auto-generated accessors/equals/hashCode. A local class is usually a better fit when there is mutable per-instance state or non-trivial logic/constructors.

**Key difference:** A local record is **implicitly static** and does not capture local variables/the enclosing instance the way a non-static local class does. Required data must be passed through components/method arguments. And a record is not automatically deep-immutable if a component is a mutable array/list.

Do not choose a local record merely for its short syntax when the abstraction genuinely needs complex behavior/state.

## 25. Why Should You Not Create a Local Class for Every Lambda?

The following situations are usually **not worth adding a local class**:

- Mapping a list of numbers to their squares: `n -> n * n`.
- Filtering elements by a short condition.
- Printing each element using a method reference.
- Calling a one-off callback that needs no name/state.
- Merely adapting an existing method into a functional object: `String::trim` or `System.out::println` when the type matches.

Example:

```java
List<Integer> doubled = numbers.stream()
        .map(n -> n * 2)
        .toList();
```

This is a code snippet, assuming `numbers` is an existing `List<Integer>` and `java.util.List` is imported. Adding a local class implementing Function just to perform `n * 2` would introduce unnecessary ceremony.

**Rule:** A lambda is good when the logic is short and the functional intent is clear. A local class is good when the behavior **has a structure worth naming** and there are multiple details that need to be grouped in one place.

## 26. Why Should You Not Create a Local Class Just to “Avoid Adding Another File”?

The goal is not to reduce the number of files at all costs. A complex 200-line local class can:

- Obscure the control flow of the enclosing method.
- Be difficult to test directly.
- Capture too many implicit dependencies.
- Duplicate logic across multiple methods.
- Have its own lifecycle/resource management without a clear place to manage it.
- Force editing a large method when changing a small rule.

If the class has a **stable business responsibility**, multiple public-facing consumers, or needs to define versioning/an API, consider a static nested/top-level class. The fact that it “is only called from one method today” is not enough to prove it must stay local forever if its complexity does not fit.

### Review Using Questions Instead of Line Counts

1. Does the concrete helper type need to be **named elsewhere**?
2. Can a reader of the method understand the main flow without reading every line of the helper?
3. Do the state fields and helper methods serve **only a single workflow**?
4. Are the captured dependencies clear?
5. Can it be tested sufficiently through the enclosing method/interface, or does it need to be tested as an independent class?
6. If future requirements are added, is the helper likely to be reused in multiple places?

The answers matter more than a rule like “a local class under N lines”.

## 27. Refactoring from a Local Class to a Static Nested Class When Reuse Begins

Suppose several methods need the same rule; we can promote the helper to a static nested class with explicit dependencies.

Create **`ReusableNestedHelperDemo.java`**:

```java
public class ReusableNestedHelperDemo {
    private static final class Prefixer {
        private final String prefix;

        Prefixer(String prefix) {
            this.prefix = prefix;
        }

        String apply(String value) {
            return prefix + value;
        }
    }

    static String labelA(String value) {
        return new Prefixer("A-").apply(value);
    }

    static String labelB(String value) {
        return new Prefixer("B-").apply(value);
    }

    public static void main(String[] args) {
        System.out.println(labelA("1"));
        System.out.println(labelB("2"));
    }
}
```

```bash
javac ReusableNestedHelperDemo.java
java ReusableNestedHelperDemo
```

```text
A-1
B-2
```

**Refactoring benefits:**

- `Prefixer` no longer belongs exclusively to a single method.
- Two methods reuse one implementation.
- The `prefix` dependency is passed explicitly via the constructor.
- Because the nested class is `static`, it does not automatically hold an implicit instance of the outer `ReusableNestedHelperDemo`.
- It remains `private` and does not become a top-level public API.

When should you continue extracting it into a separate file? When its responsibility and reusability extend beyond the enclosing class, or when tests/docs/dependencies need a separate module type.

## 28. Testing a Local Class Through Observable Behavior

Because a local class name is not in scope outside its block, unit tests typically verify it through the **enclosing method**, **interface**, or **public behavior**, rather than calling the local type's named constructor directly from a test class.

Create **`LocalClassBehaviorTestDemo.java`**:

```java
import java.util.function.IntUnaryOperator;

public class LocalClassBehaviorTestDemo {
    static IntUnaryOperator scaledAdder(int scale, int offset) {
        class Rule implements IntUnaryOperator {
            @Override
            public int applyAsInt(int input) {
                return input * scale + offset;
            }
        }

        return new Rule();
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        IntUnaryOperator rule = scaledAdder(2, 3);

        check(rule.applyAsInt(4) == 11, "positive input");
        check(rule.applyAsInt(0) == 3, "zero input");
        check(rule.applyAsInt(-2) == -1, "negative input");

        System.out.println("local helper behavior PASS");
    }
}
```

```bash
javac LocalClassBehaviorTestDemo.java
java LocalClassBehaviorTestDemo
```

```text
local helper behavior PASS
```

The `Rule` helper does not need to be exposed to test meaningful operations. Another public or package-private method can test it through the same interface.

If the logic has many complex branches that force tests to set up states hard to construct through the enclosing API, that can be a signal to promote the helper to a **testable named type** with an appropriate scope.

**Do not misunderstand:** Having a local class's name restricted is a compile-time property; it does not make the code “untestable”. It simply means we should test through the contract that external code actually uses.

## 29. A Local Class Can Hold Mutable State and Side Effects: Consider the Lifecycle

A helper named `Task` or `Processor` inside a method is sometimes **returned** as an interface and lives for a long time. In that case:

- Captured references can keep other objects alive longer than expected.
- Instance state can be mutated from other threads.
- The helper might hold a file/socket or callback that requires cleanup.
- State may no longer be valid when the external environment changes.

**Logical example:** A `Runnable` returned from a factory may be executed multiple times, on different threads. If it mutates an `ArrayList` captured from the caller, synchronization may be needed.

Do not view a local class as “existing only inside the method”: **only the class name is restricted in source scope**, while instances follow normal reference/GC lifecycles.

If the lifecycle is complex, moving the concrete class to a broader scope so the owner/cleanup contract is easier to observe can be better.

## 30. A Pitfall with `this` in Local Classes and Lambdas

A local class has its own `this` receiver. If declared inside an instance method of Outer, `Outer.this` points to the corresponding Outer instance.

In a lambda, `this` has the **lexical** meaning of where the lambda is declared, not a lambda object receiver.

Create **`LocalClassThisVsLambdaDemo.java`**:

```java
class Outer {
    private final String name = "OUTER";

    void show() {
        class Local {
            private final String name = "LOCAL";

            void print() {
                System.out.println("local this=" + this.name);
                System.out.println("outer=" + Outer.this.name);
            }
        }

        Runnable lambda = () ->
                System.out.println("lambda this=" + this.name);

        new Local().print();
        lambda.run();
    }
}

public class LocalClassThisVsLambdaDemo {
    public static void main(String[] args) {
        new Outer().show();
    }
}
```

```bash
javac LocalClassThisVsLambdaDemo.java
java LocalClassThisVsLambdaDemo
```

```text
local this=LOCAL
outer=OUTER
lambda this=OUTER
```

In `Local.print`, `this` is Local. In the lambda written directly inside `Outer.show`, `this` is the lexical Outer.

**Why this matters when choosing:** If the logic uses outer state, switching between a local class and a lambda can give `this` a different meaning. Do not refactor based solely on brevity without checking receiver identity.

## 31. A Local Class Does Not Automatically Become a Member Class Usable Elsewhere

Example:

```java
class Outer {
    void method() {
        class Helper {
        }
        Helper h = new Helper();
    }

    void other() {
        // Helper h; // Invalid.
        // Outer.Helper h; // Invalid.
    }
}
```

This is an **illustrative declaration** without `main`.

The name `Helper` is in scope from the class declaration line to the end of its enclosing method block. It **cannot be accessed as `Outer.Helper`** like a member nested type.

If a caller in another method needs the concrete type, the current scope cannot satisfy that; use an interface/supertype or refactor the helper into a member/static nested/top-level class.

### Two Local Classes with the Same Name in Two Methods Are Two Separate Types

This is valid when the scopes are separate:

```java
void first() {
    class Helper {
    }
    new Helper();
}

void second() {
    class Helper {
    }
    new Helper();
}
```

The two methods use the same simple name, yet they do not share a single Helper type; do not treat that as an implementation-sharing mechanism.

## 32. When Is a Private Method Better Than a Local Class?

A **private method** is usually better if:

- The logic is completely pure and needs no state of its own.
- There are already clear inputs/outputs, and parameters can be passed directly.
- You only want to name a short transformation.
- Adding a class only increases nesting depth without creating a clear semantic entity.

Example replacing a local helper:

```java
private static boolean isValidCode(String code) {
    return code != null && !code.isBlank();
}
```

This is a method snippet belonging to the class. If multiple call sites use `isValidCode`, a private method is both concise and convenient to reuse.

Conversely, if you have to repeatedly pass 5-6 parameters to a group of 4 helper methods, a helper object with clear fields/constructor can bundle the dependencies better.

**Ask the question:** Are you naming **a single operation** or **a group of behaviors/state**? Operation → private method/lambda. A group with identity and invariants → a class, of which a local class is a candidate if the scope is just a single block.

## 33. Signs of the Wrong Choice

| Sign | Potential issue | Direction to consider |
| --- | --- | --- |
| Local class has only one method returning a one-line expression | More ceremony than meaning | Lambda/private method |
| Identical local class copied across several methods | Duplicate logic | Static nested/top-level helper |
| Local class is too long, making the main method hard to see | Details overshadow the goal | Extract class/private helper |
| Helper captures very many local variables | Hidden dependencies | Immutable config/constructor parameters |
| Caller outside the method wants to use the implementation name | Scope does not support it | Public interface or suitable named type |
| Helper only takes primitive/immutable input and has no state | Class may be redundant | Pure function |
| Helper uses a mutable shared collection from the caller | Aliasing, race conditions | Ownership/defensive copy/synchronization |
| Helper holds resources with their own lifecycle | Cleanup is hard to spot | Scoped resource manager/named class |
| Helper needs too many edge cases tested directly | Contract exceeds “small detail” | Extract testable type |
| Helper is part of a widely used domain model | Named too narrowly | Domain class/value type |
| Local class in a static method calls `Outer.this` | No enclosing Outer instance | Explicit owner reference |
| Simple logic uses anonymous/local class out of habit | Hard to read | Lambda/method reference |
| “Everything” is made local to reduce file count | Increases coupling/method length | Refactor by responsibility |

**Remember:** A sound helper can still be placed in the wrong scope. Evaluate how **others read, test, and modify** the code as well.

## 34. Synthesis Exercise: Choosing a Design for Each Scenario

**Scenario A.** A method sorts three elements using a simple comparator with no state.

*Suggested choice:* A lambda or built-in Comparator, since no local class is needed.

**Scenario B.** A method parses a long string, needing a scanner that holds a cursor and has `peek`, `read`, and `skip` methods, and the scanner is not used anywhere else.

*Suggested choice:* A local class can be suitable if the overall length remains readable. If the parser grows, consider a separate class.

**Scenario C.** Three different methods all use the same validation rules.

*Suggested choice:* A shared private method or a static nested/top-level validator. Do not copy the same local class three times.

**Scenario D.** A factory creates a strategy implementing an interface, and only the factory cares about the implementation.

*Suggested choice:* A local class if the implementation has multiple steps/state; a lambda if it is just a short function.

**Scenario E.** A callback is returned outside and holds mutable state, running on multiple threads.

*Suggested choice:* First determine lifecycle, concurrency, and ownership. A local class is not automatically synchronized; a named component with clear tests/contract may be needed.

**Scenario F.** A helper may be called by several enclosing methods and does not need an Outer instance.

*Suggested choice:* `private static nested class` with dependencies passed explicitly.

**Scenario G.** A very short transformation is used repeatedly and has no fields.

*Suggested choice:* A private method or method reference instead of a local class.

**Scenario H.** A dedicated algorithm needs a small Node/Frame structure with two fields and a few helper operations; there are no users outside the algorithm.

*Suggested choice:* A local class, or a local record when storing only immutable data (subject to its restrictions), depending on the state model.

## 35. Review Checklist for a Local Class

- [ ] Does the local class serve **just one method/block** or multiple places?
- [ ] Does it have a **name that expresses its real responsibility**?
- [ ] Does it have enough **state/methods/constructor** for defining a class to be beneficial?
- [ ] Is the main flow of the enclosing method still easy to read with the class declaration inside it?
- [ ] Would a lambda/private method be simpler while remaining clear?
- [ ] Would an anonymous class be more suitable if only a single object is created in one expression?
- [ ] Would a static nested/top-level class be more appropriate due to reuse or complexity?
- [ ] Are the captured local variables/parameters final/effectively final?
- [ ] Do any captured references hold mutable state that is shared unintentionally?
- [ ] If the helper runs after the enclosing method returns, are lifecycle/ownership clear?
- [ ] If the helper object is returned, does the API have an appropriate visible interface/supertype?
- [ ] Is the local class name never used from code outside its lexical scope?
- [ ] Are you avoiding relying on compiler-generated binary class names as an API?
- [ ] If the helper is in a static method, are you avoiding the mistake of assuming `Outer.this` is always available?
- [ ] If `this` appears in a local class/lambda, has the lexical receiver been considered correctly?
- [ ] If the helper has mutable fields, is the concurrency contract reasonable?
- [ ] Do the helper methods share a single invariant, or are multiple responsibilities being crammed together?
- [ ] Is the helper copied verbatim in other methods?
- [ ] If the helper is long, is there a valid reason not to refactor it out into a named class?
- [ ] Do unit tests cover observable behavior through the enclosing method/interface?
- [ ] Does the public-facing API avoid leaking the local class name or implementation details?
- [ ] Do the Java 17+ examples have matching file/public class names and deterministic stdout?

## 36. Review Questions with Answers

**1.** When is a local class a natural choice?

**Answer:** When a cluster of implementation details has its own state/methods, is needed only inside a single block/method, and placing it close to where it is used makes the code easier to understand.

**2.** Can a local class have constructors, fields, and multiple instance methods?

**Answer:** Yes. It is a class subject to local class rules, not merely a named lambda.

**3.** If you only need `n -> n * 2`, should you create a local class?

**Answer:** Usually no. A lambda or an appropriate method is easier to read.

**4.** What if multiple methods need the same helper?

**Answer:** Consider a private method, static nested class, or top-level class for reuse.

**5.** Is a local class declared inside a static method valid?

**Answer:** Yes. However, there is no implicit enclosing Outer instance to use `Outer.this` in a static context.

**6.** Can a local class use a parameter of the enclosing method?

**Answer:** Yes, if the parameter is final/effectively final and satisfies the relevant rules.

**7.** Does a captured `StringBuilder` become immutable?

**Answer:** No. The reference variable can be effectively final, yet the object remains mutable.

**8.** After the method returns, can a local class instance still operate?

**Answer:** Yes, if a reference still holds the object, for example through an interface.

**9.** Can the local class name be used in another method?

**Answer:** No. Its scope runs from its declaration to the end of the block that directly encloses the declaration.

**10.** Why is an interface return type useful?

**Answer:** It allows callers to use the behavior without needing to know the concrete local class name.

**11.** In what important way does a local named class differ from an anonymous class?

**Answer:** A local class has a name so it can be instantiated multiple times and define its own constructor; an anonymous class has no source-level name or constructor declared using a class name.

**12.** Can a local record replace a mutable-state local class helper in all cases?

**Answer:** No. A local record is implicitly static and is a data carrier with component semantics; mutable state and capture behavior differ.

**13.** When a helper captures many dependencies, how can you make it clearer?

**Answer:** Group them into config/value objects or pass constructor parameters; consider a named helper with a broader scope.

**14.** Is a local class thread-safe by default just because its name exists only in one block?

**Answer:** No. Instances can outlive the call and be shared across threads, requiring a concurrency contract.

**15.** Why might a 200-line local class be inappropriate even if used in only one method?

**Answer:** It can obscure the main flow, be hard to test/reuse, and create coupling; refactoring should be considered.

**16.** Should you use a compiler-generated type name to call a local class from other code?

**Answer:** No. That is not a stable source API; use an interface/supertype or change the scope design.

**17.** Can a local class declare a field whose type links to itself?

**Answer:** Yes, the class name can be used inside the body of its own declaration to build structures like Node.

**18.** When is a static nested helper better?

**Answer:** When multiple methods of the outer class use it and the helper does not need an implicit owner instance.

**19.** When is a private method better?

**Answer:** When you need a name for a pure operation that does not require per-instance state/constructors.

**20.** What is the ultimate criterion for choosing a local class?

**Answer:** Whether it keeps **implementation details close to where they are used**, reduces unnecessary scope, and **improves readability/testability/maintainability** compared to the alternatives.

---

**Final takeaway:** **A local class** is worth using when a method has **a named helper with state or multiple related methods**, yet that concrete type does not need to be reused by name elsewhere. It helps **hide implementation details and keep the narrative close to where it is used**, can capture effectively-final parameters/local variables, and can return instances through an interface/supertype. However, a local class does not automatically make code better: a **lambda/private method** is usually better suited for short logic; a **static nested/top-level class** is more appropriate when the helper is reused, has its own lifecycle/API, or is too complex. Base your choice on **responsibility, actual usage scope, clarity of dependencies, and maintainability**, rather than on a goal of reducing file count or increasing class count.
