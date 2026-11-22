# Combining Sealed Types with Exhaustive Switch

**Topic:** Java Core Pattern Matching — Pattern Composition. This content uses Java 21 or later, when pattern matching for switch (JEP 441) and record patterns (JEP 440) are standard features; `--enable-preview` is not required.

## 1. The Problem: Handling All Value Forms Completely

A supertype variable can represent multiple subtypes. For example, a message-processing system has two forms: **Ping**, which carries no data, and **Submit**, which carries text content and a priority. When processing messages, we want to guarantee that **every valid form has a handling branch**. If the program adds a new message type, ideally the compiler should remind us to update the branching code.

A hierarchy using an openly extensible supertype is often written using multiple `instanceof` checks ending with a fallback branch. For a system that allows only a fixed set of subtypes, Java provides **sealed classes/interfaces**. Combining them with a **switch expression** that supports type patterns gives us **exhaustiveness** checking at compile time: the compiler can determine whether the switch branches handle all permitted type possibilities.

Roles of the three components:

- **Sealed type:** declares which types are permitted to directly extend/implement the supertype.
- **Pattern:** describes the type and, if needed, extracts the components of a record in each branch.
- **Exhaustive switch:** has a branch applicable to every value of the selector's possible types, according to Java's static analysis. For a switch expression, exhaustiveness is a compile-time requirement.

Thus, the sealed type provides information about the type domain, patterns express each case, and switch leverages that information to check coverage.

## 2. Declaring a Closed Type Domain with a Sealed Interface

~~~java
sealed interface Message permits Ping, Submit {}

record Ping() implements Message {}

record Submit(String text, int priority) implements Message {}
~~~

The snippet above illustrates a group of declarations within the same permitted scope. **Message** permits only two direct subtypes: **Ping** and **Submit**. Records are implicitly final, so these two records satisfy the requirement for a type that directly implements a sealed interface.

A direct subtype of a sealed class/interface must explicitly specify one of the modifiers: **final**, **sealed**, or **non-sealed** (records are implicitly final). Location rules also matter: in a named module, permitted subclasses must reside in the same module; when there is no named module, they must reside in the same package. Names in **permits** must correspond to valid subtypes.

Sealed does not mean "every object in the application belongs strictly to those two classes" in every design. If a permitted branch is declared **non-sealed**, derived types under that branch can continue to extend it. What Java controls is **the direct subtypes**, while the switch must cover the actual hierarchy structure, for example by using a type pattern for the entire non-sealed branch.

## 3. Why Can default Be Omitted While Remaining Exhaustive?

With a selector of type **Message**, the two records above are all of the valid direct subtypes:

~~~java
static String kind(Message message) {
    return switch (message) {
        case Ping p -> "PING";
        case Submit s -> "SUBMIT";
    };
}
~~~

This is a **switch expression** with a return value. Even though there is no **default**, the compiler knows that every non-null Message value belongs to one of the covered branches. It accepts the switch because the type domain is closed by the sealed interface.

In this case, the two type patterns **Ping p** and **Submit s** are sufficient to prove exhaustiveness; a record pattern is not strictly required. We use a record pattern when we actually want to access the components, such as **Submit(var text, var priority)**.

**Distinguishing exhaustiveness from null:** exhaustiveness based on a sealed type does not turn a null selector into a subtype of Message. If **message == null** and the switch has no matching null branch, the switch will throw a **NullPointerException** at runtime. To handle null intentionally, add **case null**. A switch that has enough type branches but does not handle null can still compile.

### When Branches Have Guards

Suppose we only accept a Submit whose text is non-blank and whose priority is 1 or higher:

~~~java
return switch (message) {
    case Ping() -> "pong";
    case Submit(var text, var priority)
            when text != null && !text.isBlank() && priority >= 1 ->
            "accepted";
    case Submit(var text, var priority) -> "rejected";
    case null -> "missing message";
};
~~~

The key point: the first Submit branch has **when**, so it covers only **a subset** of Submit values. The second Submit branch without a guard covers the remaining Submit values. If only the guarded branch were kept, the switch expression would not be exhaustive, because a Submit that does not satisfy the condition would not be handled.

A specific branch with a guard must precede a broader branch of the same type; placing the general Submit branch first can dominate the subsequent branch and cause it to be rejected at compile time. The guard is evaluated only after the pattern matches and its variables are bound.

## 4. Complete Java 21 Example

The following program demonstrates a sealed interface, record patterns, a guard, null handling, and an exhaustive switch expression **without default**. Save the code in **SealedSwitchDemo.java**:

~~~java
public class SealedSwitchDemo {
    sealed interface Message permits Ping, Submit {}

    record Ping() implements Message {}

    record Submit(String text, int priority) implements Message {}

    static String handle(Message message) {
        return switch (message) {
            case Ping() -> "pong";

            case Submit(String text, int priority)
                    when text != null && !text.isBlank() && priority >= 1 ->
                    "accepted: " + text + ", priority=" + priority;

            case Submit(var text, var priority) -> "rejected";

            case null -> "missing message";
        };
    }

    public static void main(String[] args) {
        System.out.println(handle(new Ping()));
        System.out.println(handle(new Submit("deploy", 2)));
        System.out.println(handle(new Submit(" ", 2)));
        System.out.println(handle(new Submit(null, 2)));
        System.out.println(handle(null));
    }
}
~~~

Compile and run with JDK 21+:

~~~bash
javac SealedSwitchDemo.java
java SealedSwitchDemo
~~~

Exact output:

~~~text
pong
accepted: deploy, priority=2
rejected
rejected
missing message
~~~

Explanation of each case:

1. **new Ping()** matches **case Ping()**, returning pong.
2. **Submit("deploy", 2)** matches the record pattern and the guard, so it returns the accepted message.
3. **Submit(" ", 2)** matches the Submit type but does not satisfy **text.isBlank() == false**, so it enters the unguarded Submit branch.
4. **Submit(null, 2)** is still a valid Submit in terms of record type. The first guard checks **text != null** before calling **isBlank()**, so it does not cause a NullPointerException and falls through to the fallback Submit branch.
5. **null** matches **case null**. This branch handles null input explicitly.

In this code, **Submit(String text, int priority)** is a record pattern. It extracts the **text** and **priority** components at their corresponding positions in the record without invoking the constructor. A record pattern with a reference component can bind a null value when the component pattern is unconditional; the example checks for null separately using a guard. For a specific nested record such as **Address(...)**, a null nested record will not match that nested pattern.

## 5. Adding a New Subtype: The Compiler Helps Detect Missing Branches

Suppose later we want to add a **Cancel** message. We update the hierarchy declaration:

~~~java
// Illustrates a partial change to the example above, not a standalone program.
sealed interface Message permits Ping, Submit, Cancel {}

record Cancel(String reason) implements Message {}
~~~

At this point, the previous **handle(Message message)** method only has branches covering Ping and Submit; **Cancel** is not handled yet. Because the switch expression **has no default** and does not cover all permitted types, the compiler reports an error such as **the switch expression does not cover all possible input values**. Adding a class without adding handling forces us to re-evaluate the logic.

The clear way to update it is to add a new branch before case null:

~~~java
case Cancel(var reason) -> "cancelled: " + reason;
~~~

This forces the developer to actively decide the semantics of Cancel. Using **default** too early in a switch over a sealed hierarchy can forfeit this advantage: when a subtype is added, the code still compiles and the new branch is lumped into default, even though the business logic may require dedicated handling.

**When is default still appropriate?** When a requirement genuinely specifies the same fallback behavior for all other types, or at a boundary that needs a general rejection strategy. However, if the goal is "every added subtype must be reviewed at every handling site," do not write default just to silence the compiler.

It is also necessary to distinguish compile time from binary/runtime changes: if classes are compiled, deployed, and upgraded out of sync, the actual hierarchy may change after a switch has been compiled. Java has a runtime error mechanism (for example **MatchException**) if a switch presumed to be exhaustive encounters a value not handled by any branch due to separate compilation/compatibility situations. Compile-time guarantees are very useful, but they do not replace a consistent build and deployment process.

## 6. Multi-Level Sealed Hierarchies and non-sealed

The example below illustrates the branches solely to explain the structure:

~~~java
sealed interface Event permits Created, UpdateEvent {}

record Created(String id) implements Event {}

non-sealed interface UpdateEvent extends Event {}
~~~

**Event** has only two permitted direct subtypes. However, **UpdateEvent** is declared non-sealed, meaning that classes implementing UpdateEvent can be extended later. For a switch to cover this branch, we can use a general type pattern:

~~~java
static String label(Event event) {
    return switch (event) {
        case Created(var id) -> "created " + id;
        case UpdateEvent u -> "update";
        case null -> "null event";
    };
}
~~~

The **case UpdateEvent u** branch covers every value of the UpdateEvent interface, including implementing classes validly added later. As a result, the switch remains exhaustive with respect to the declared domain. If instead we want to distinguish each kind of UpdateEvent and have the compiler remind us when a new kind is added, we should consider keeping the intermediate branch sealed as well, with a clearly defined set of subtypes.

In a multi-level sealed hierarchy, leaf types can be listed in the switch if exhaustiveness analysis proves they cover all branches sufficiently. There does not necessarily need to be an exact one-to-one case for every name appearing in **permits** at the outer level; what is required is **covering every possible value**.

## 7. Comparison with enum, if/else, and switch with default

| Modeling Approach | Strengths | Trade-offs |
| --- | --- | --- |
| **enum + switch** | Suitable for a fixed set of choices where each choice is simple | Hard to represent each case having its own set of components and data types like distinct record subtypes |
| **sealed interface + switch pattern** | Each subtype has different data and behavior; the compiler checks subtype coverage | Must manage the hierarchy and understand the extensibility of non-sealed branches |
| **if/else + instanceof** | Convenient for a few linear checks or an open supertype | Does not inherently provide exhaustiveness checking like a switch expression over a sealed hierarchy |
| **switch with default** | Provides an explicit fallback branch for other cases | Can hide the addition of a new subtype that has not yet been designed for handling |

Not every finite choice needs a sealed type. Use an enum when there are only a fixed number of states or identifiers and the associated data is relatively uniform. A sealed hierarchy shines when each case is **its own distinct type**, such as a processing result consisting of Success(data), ValidationError(errors), and RetryAfter(duration), or expression nodes with different structures.

## 8. Combining Nested Record Patterns While Preserving Exhaustiveness

Exhaustiveness via a sealed type is about **covering the subtypes**, whereas nested record patterns are about **selecting a specific component shape**. The two aspects complement each other but do not replace each other.

Suppose Submit has a component that is another record:

~~~java
record Payload(String kind, int size) {}

record Submit(Payload payload, int priority) implements Message {}
~~~

This is an **alternative design version** of the Submit record in the main example; do not use both declarations with the same name simultaneously. If we write a case that only accepts a Submit with a non-null payload:

~~~java
case Submit(Payload(var kind, int size), int priority) ->
        "payload " + kind;
~~~

then a value **Submit(null, 1)** will not match that case. Even though the Submit subtype has been mentioned, the switch still needs a branch to handle other Submit values, such as:

~~~java
case Submit(var payload, var priority) -> "invalid submit";
~~~

The lesson is that **a case mentioning a subtype does not necessarily cover the entire subtype**, especially when the sub-pattern requires a nested record, has a guard, or imposes other constraints. To ensure exhaustiveness, evaluate the actual scope covered by each pattern.

## 9. Common Mistakes and How to Fix Them

1. **Having only cases with `when`:** Any Submit might fail to satisfy the guard. Add an unguarded case (or another branch that genuinely covers the remainder).
2. **Confusing "having a case for a subtype" with "covering the entire subtype":** A nested record pattern requires a matching nested component. Account for null and non-matching data shapes.
3. **Placing a broad case before a narrow case:** An unguarded case for Submit can capture all Submit instances and cause a subsequent specific case to be dominated.
4. **Adding `default` to every switch:** This can suppress warnings when new permitted types are added. Use it only when the business logic genuinely requires shared fallback behavior.
5. **Forgetting `null`:** A sealed interface describes valid subtypes; it does not make a null selector automatically become Ping or Submit. Use `case null` if it needs to be handled, or accept a NullPointerException per the method's contract.
6. **Assuming `sealed` closes every level:** A **non-sealed** permitted subtype still allows new descendants. Use a type pattern covering that branch when exhaustiveness is needed.
7. **Overusing patterns as a substitute for validation:** Type checking and component extraction do not automatically guarantee that data fields are non-empty, positive, or satisfy other business rules.
8. **Misunderstanding variable scope:** Variables introduced by a pattern or record pattern can only be used where matching succeeds and according to Java's scoping rules.
9. **Changing a hierarchy while compiling only partially:** Compile, test, and deploy related components together to avoid unexpected runtime errors.

## 10. Design and Testing Checklist

Before finalizing a switch over a sealed hierarchy, verify that:

- The selector type is actually sealed (or an exhaustively analyzable domain) and its subtypes are declared correctly.
- Every **permitted subtype** has at least one set of cases covering all values that need to be handled; pay attention to guards and nested record patterns.
- Specific branches come before broad branches; each branch has clear business meaning.
- The handling of **null** is explicitly decided: handled via `case null` or left to fail according to the contract.
- When a new subtype is added, try compiling to confirm that the switches needing review are detected.
- Tests exist for the subtypes, guard edge cases, and null nested components (if the model allows them).
- If the hierarchy permits a **non-sealed** branch, it is understood that descendants under that branch can still be extended.

**Key takeaway:** a sealed type creates a type domain that the compiler can analyze, while pattern matching for switch turns each subtype into a meaningful handling branch. Combining them properly allows a **switch expression to remain exhaustive without `default`**, while surfacing missing-branch errors at compile time when new subtypes are added.
