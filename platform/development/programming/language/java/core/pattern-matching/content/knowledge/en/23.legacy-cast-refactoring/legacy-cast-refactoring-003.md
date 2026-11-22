# Refactoring if-else Chains by Subtype

**Topic:** Refactoring legacy casts in Java Core Pattern Matching. This article uses Java 21+ for the **pattern matching for switch** and **record patterns** examples; **type patterns with instanceof** have been available since Java 16, so they can be adopted incrementally on Java 17.

## 1. Identifying if-else chains to refactor

In legacy Java code, a parameter of a parent type is often branched by subtype using **instanceof**, followed by a manual cast to extract data:

~~~java
// Illustration inside a method receiving a command variable.
if (command instanceof Register) {
    Register register = (Register) command;
    // Process Register data.
} else if (command instanceof Disable) {
    Disable disable = (Disable) command;
    // Process Disable data.
} else if (command instanceof Ping) {
    // Process Ping.
} else {
    // Input did not match.
}
~~~

This structure is valid, but as the number of subtypes grows, the repeated **type check → cast → use object** pattern makes the code verbose and makes it harder to see which cases have already been handled. A change to the hierarchy can cause the final branch to silently accept a new type, even when the business logic actually requires dedicated handling.

The goals of refactoring are:

- Remove casts already guaranteed by **instanceof**, using a pattern variable of the right type directly in the condition.
- Place each subtype's logic in an easily identifiable branch.
- When appropriate, use a **switch expression** with a sealed hierarchy so the compiler checks branch exhaustiveness.
- Preserve the meaning of sub-conditions, precedence order, error messages, return values, and null policy.

**A successful refactor means intentional behavior is preserved.** Shorter code is not enough: if you change the branch order or alter the meaning of the else branch, the result can differ.

## 2. First, lock down the current behavioral contract

Before making changes, document what each branch actually does. Consider a command hierarchy with three subtypes:

~~~java
sealed interface Command permits Register, Disable, Ping {}

record Register(String username, int age) implements Command {}
record Disable(String username) implements Command {}
record Ping() implements Command {}
~~~

Suppose the processing contract is:

| Input | Expected result |
| --- | --- |
| Register with non-blank username, age from 18 | Return REGISTER message with name |
| Register not meeting conditions | Return INVALID REGISTER |
| Disable | Return DISABLE message with name |
| Ping | Return PONG |
| null | Return NO COMMAND |

In the hierarchy above, Command is a sealed interface and only three records are permitted to implement it directly. Records are final types, so there are no deeper subtypes beneath them. If a real project has **regular classes** or **non-sealed subtypes**, the type domain may be more open; in that case, the refactoring plan must also account for types not listed directly.

Examine separately the elements most prone to unintentional changes: child subtype branches versus parent subtype branches; numeric/string guard checks; null-handling branches; side effects such as logging, API calls, or state updates; exceptions and accessor call order. Do not merge or alter business branches just because new pattern syntax is available.

## 3. The safest step: replace instanceof + cast with a type pattern

Instead of checking a type and then casting to the same type, you can bind a variable directly in **instanceof**:

**Before:**

~~~java
if (command instanceof Register) {
    Register register = (Register) command;
    return register.username();
}
~~~

**After:**

~~~java
if (command instanceof Register register) {
    return register.username();
}
~~~

With the **Register register** syntax, the compiler both checks the type and introduces the variable `register` with the exact type Register. No manual cast is needed. If it does not match, the if branch does not execute and the `register` variable is not in scope on that path.

Example with multiple subtypes:

~~~java
// Illustrative snippet: assumes the three records from section 2 are present.
static String typePatternVersion(Command command) {
    if (command instanceof Register register) {
        String username = register.username();
        if (username != null && !username.isBlank()
                && register.age() >= 18) {
            return "REGISTER:" + username;
        }
        return "INVALID REGISTER";
    } else if (command instanceof Disable disable) {
        return "DISABLE:" + disable.username();
    } else if (command instanceof Ping ping) {
        return "PONG";
    }
    return "NO COMMAND";
}
~~~

Notable points:

- We **only replace the check/cast**; every action, if/else order, condition, and return path is kept unchanged.
- With **instanceof**, a null value does not match any type pattern, so it falls through to the final return just like the legacy code.
- This code works on Java 17; you do not have to switch to `switch` just to eliminate casts.
- When a branch has many statements or side effects, keeping the if/else form is sometimes clearer than converting the entire block to a switch.

### Flow scoping of pattern variables

A variable introduced by a type pattern has a scope that depends on control flow. For example:

~~~java
if (command instanceof Register register
        && register.age() >= 18) {
    System.out.println(register.username());
}
~~~

The right-hand side of **&&** is only evaluated if the left-hand pattern matches, so `register` already exists. Conversely, using `register` on the right-hand side of **||** as shown below is invalid:

~~~java
// Does not compile: when the left-hand side is false, register is not bound.
if (command instanceof Register register
        || register.age() >= 18) {
    // ...
}
~~~

Use **&&** according to the actual business logic; do not change conditional operators just to force a pattern variable into another scope.

## 4. When should you convert to a switch expression?

If the branches all **return a value**, the dispatch is primarily based on subtype, and each branch has a clear purpose, a **switch expression** consolidates all branching into a single expression.

With records, you can extract components directly in the case branch:

~~~java
// Illustration: uses the declared Command, Register, Disable, Ping records.
static String switchVersion(Command command) {
    return switch (command) {
        case Register(String username, int age)
                when username != null && !username.isBlank() && age >= 18 ->
                "REGISTER:" + username;

        case Register(var username, var age) -> "INVALID REGISTER";
        case Disable(var username) -> "DISABLE:" + username;
        case Ping() -> "PONG";
        case null -> "NO COMMAND";
    };
}
~~~

There are two distinct mechanisms here:

1. **Subtype/record pattern** describes the input case, such as Register or Disable, and can bind component values.
2. **when** is a guard on a switch branch: once the pattern matches, the guard determines whether that branch is selected.

The guarded Register branch handles only a subset of Register values. The unguarded Register branch below it handles **all remaining Register values**, so the branch chain does not lose cases where `username` is blank or `age` is under 18.

**Why is there no default?** The selector type is the sealed Command; Register, Disable, and Ping are all covered. For a switch expression, the compiler requires **exhaustiveness** (complete coverage). The null case is written explicitly to preserve the legacy if-else chain's behavior of returning NO COMMAND. If you omit **case null**, a switch may still be exhaustive over the subtypes, but it will throw a NullPointerException when given null.

With a selector of type **Object** or a more open hierarchy, the cases above do not cover all subtypes: an appropriate branch for the remainder is required, such as **default** (or a general type pattern), depending on the business contract.

## 5. Complete Java 21 example: comparing before and after refactoring

The following program contains two implementations of the same business logic: the legacy version using an **if-else + cast** chain and the modern version using **switch + record patterns**. Both are invoked on multiple inputs, including guard boundaries and null.

Save the file as **SubtypeRefactorDemo.java**:

~~~java
public class SubtypeRefactorDemo {
    sealed interface Command permits Register, Disable, Ping {}

    record Register(String username, int age) implements Command {}
    record Disable(String username) implements Command {}
    record Ping() implements Command {}

    static String legacy(Command command) {
        if (command instanceof Register) {
            Register register = (Register) command;
            String username = register.username();
            if (username != null && !username.isBlank() && register.age() >= 18) {
                return "REGISTER:" + username;
            }
            return "INVALID REGISTER";
        } else if (command instanceof Disable) {
            Disable disable = (Disable) command;
            return "DISABLE:" + disable.username();
        } else if (command instanceof Ping) {
            return "PONG";
        }
        return "NO COMMAND";
    }

    static String modern(Command command) {
        return switch (command) {
            case Register(String username, int age)
                    when username != null && !username.isBlank() && age >= 18 ->
                    "REGISTER:" + username;
            case Register(var username, var age) -> "INVALID REGISTER";
            case Disable(var username) -> "DISABLE:" + username;
            case Ping() -> "PONG";
            case null -> "NO COMMAND";
        };
    }

    public static void main(String[] args) {
        Command[] samples = {
                new Register("Lan", 21),
                new Register("Mai", 16),
                new Register(" ", 30),
                new Register(null, 25),
                new Disable("Nam"),
                new Ping(),
                null
        };

        for (Command command : samples) {
            String before = legacy(command);
            String after = modern(command);
            System.out.println(after + " | same=" + before.equals(after));
        }
    }
}
~~~

Compile and run with **JDK 21+**:

~~~bash
javac SubtypeRefactorDemo.java
java SubtypeRefactorDemo
~~~

Output:

~~~text
REGISTER:Lan | same=true
INVALID REGISTER | same=true
INVALID REGISTER | same=true
INVALID REGISTER | same=true
DISABLE:Nam | same=true
PONG | same=true
NO COMMAND | same=true
~~~

The **same=true** result across all seven cases shows that the two implementations are equivalent on the example's test dataset. This is not proof that two methods are always equivalent for every input or after every change: for real code, you must add tests for the specific rules and code paths.

**How to read the Register branches:** the pattern **Register(String username, int age)** extracts the two components in the order declared by the record. The condition **username != null** avoids calling **isBlank()** on null. If `username` is blank or `age` is under 18, the guard evaluates to false and the second Register case handles it. The Disable and Ping branches do not change in meaning. Case null reproduces the legacy method's final return path when the input is null.

A record pattern that binds components does not automatically validate business data. It expresses the type and extracted data; the condition **age >= 18** must still be written explicitly. When a record allows a reference component to be null, matching with an unconditional pattern like **var username** does not guarantee that component is non-null.

## 6. Subtype ordering: the easiest place to change behavior

In a class hierarchy with multi-level inheritance, an instance of a subtype is also an instance of its parent type. An if/else chain with a parent-type branch placed before a specific subtype may have **shadowed** the later branch.

Conceptual example:

~~~java
// Suppose SpecialEvent extends Event and value has type Object.
if (value instanceof Event) {
    return "general";
} else if (value instanceof SpecialEvent) {
    return "special"; // Unreachable for SpecialEvent.
}
~~~

If you mechanically convert this to a switch with **case Event e** before **case SpecialEvent s**, the compiler will report that the SpecialEvent branch is **dominated** (covered by a broader case). To classify specific subtypes properly, you usually need to place **SpecialEvent before Event**:

~~~java
return switch (value) {
    case SpecialEvent s -> "special";
    case Event e -> "general";
    case null -> "no event";
    default -> "other";
};
~~~

**However, changing the order may fix an old bug rather than being a pure refactor.** Before changing it, determine whether the actual requirement is to keep the "general" behavior for SpecialEvent or fix it to "special". If a business behavior change is needed, state it explicitly and add new tests. Avoid mixing a subtle business bug fix into a syntax change.

In switch branches with **when**, place the more specific guarded case before the general case of the same subtype:

~~~java
case Register(var name, int age) when age >= 18 -> "adult";
case Register(var name, var age) -> "minor";
~~~

If you place the unguarded Register branch first, the guarded branch after it will be shadowed. Evaluate both **dominance** (whether a later case still has a chance to run) and **exhaustiveness** (whether any input is left unhandled by any case).

## 7. Switch exhaustiveness when refactoring a hierarchy

A **switch expression** requires all selector values to have a handling branch, according to the compiler's static analysis. This is an advantage when the hierarchy is modeled with sealed classes/interfaces and controlled subtypes.

In the example above, if you later add:

~~~java
// Illustrates a separate change, do not copy alongside the old Command declaration.
sealed interface Command permits Register, Disable, Ping, Reset {}
record Reset() implements Command {}
~~~

without adding **case Reset()** in `modern()`, recompiling the switch expression will report a missing branch. Meanwhile, an if/else chain could silently fall through to `return NO COMMAND` without forcing you to consider the purpose of Reset.

This shows why **omitting default** can be useful: the compiler reminds the author to update behavior for the new subtype. However, this only applies when the static type and cases actually give the compiler enough information to prove exhaustiveness; a **non-sealed** subtype can still allow new subclasses beneath it and requires a case covering that branch.

If the business logic intentionally has common behavior for all unknown values, **default** can make sense. However, writing `default` too early suppresses the signal when a hierarchy gains a new subtype that has not yet been given dedicated behavior.

Also remember: **case null** is for a null selector; **default** is normally not a substitute for null handling. With **instanceof**, null does not match and falls into the final else/return branch. When converting to switch, check the null contract rather than inferring it from exhaustiveness.

## 8. Choosing a type pattern or a record pattern?

| Branch need | Usually clearer approach | Example |
| --- | --- | --- |
| Only need to know the object belongs to a subtype | Type pattern or type check | **command instanceof Ping** |
| Need to pass/call methods on the whole object | Type pattern | **command instanceof Register register** |
| Need multiple components of a record | Record pattern | **case Register(var name, int age)** |
| Nested records and need inner components | Concise nested record pattern | **case Outer(Inner(var id))** |
| Multiple subtypes each return a value | Switch expression | **return switch (command) { ... };** |
| Long per-subtype logic, many side effects | If/else with type pattern or extracted method | **handleRegister(register)** |

**Record patterns only work on records.** If a subtype is an ordinary class with getters, you cannot write **case OrdinaryClass(var x)** just because the class has a matching constructor. Use a type pattern and call getters, or design an intentional conversion layer.

When you are not ready to convert everything to a switch, using **instanceof patterns** to remove casts first is a small, easy-to-review step that still adds value. Java 17 supports this approach; Java 21 is required to use record patterns and pattern switch as in the main example without enabling preview features.

## 9. Preserving fallback branches, exceptions, and side effects

Refactoring by subtype can alter behavior in ways that simple example outputs do not reveal:

- **Null:** An if/else chain with `instanceof` on null enters no branch; a pattern switch needs `case null` if you want to handle it intentionally as before.
- **Ordering:** A parent-type branch placed before a subtype can cover the subtype; changing the order requires revisiting the requirements.
- **Guards:** If a subtype has an additional check, you need a remaining branch for when the guard is false, and must not let the value fall into a branch with a different meaning.
- **Side effects:** If the legacy code calls an accessor with side effects, logs, mutates state, or calls services in a specific order, switching to patterns can change the timing and number of calls. In particular, record patterns invoke accessors to extract components; do not assume every overridden accessor is pure.
- **Exceptions:** Legacy code may throw an exception in one branch; changing it to return a default string or swallowing the error is a business logic change.
- **Fall-through:** An if/else chain may omit `return` in one branch and run shared code afterward. A switch expression requires every branch to produce a value, so shared code must be moved carefully.
- **Separate binary changes:** With sealed hierarchies, a switch is compiled against a known set of subtypes; out-of-sync class deployments can lead to a runtime case with no matching branch, such as `MatchException`. Compile and test dependent components together.

Do not convert an if/else block that calls multiple services, manages transactions, or has multiple return/break paths into a giant switch expression just for new syntax. You can use a switch statement or named handler methods, as long as the branches are clear and the behavior is tested.

## 10. A verifiable refactoring workflow

A practical workflow for large projects:

1. **Capture legacy behavior:** Tabulate each subtype, condition, result, exception, and side effect. Add tests for specific subtypes, null, and boundary values.
2. **Remove repeated casts:** Change **instanceof T** followed by **(T) value** to **instanceof T variable**; keep the branch order unchanged.
3. **Assess hierarchy depth:** Identify parent/child types, cases that might be shadowed by broader branches, and open/non-sealed types.
4. **Choose the branching construct:** If branches mainly return results, consider a switch expression; if there are many statements, use a switch statement or keep if/else.
5. **Move conditions:** Put simple guards in **when** and keep a fallback branch for when the guard is false; do not cram complex validation logic into a long case.
6. **Specify null and default explicitly:** Compare against legacy behavior; with sealed hierarchies, prefer omitting `default` when you want the compiler to detect new subtypes.
7. **Compile and run tests:** Verify exhaustiveness, dominance, behavior across subtypes, null, guard boundaries, and side-effect ordering.
8. **Review readability:** If record patterns are nested too deeply or a case is too long, extract methods by behavior.

You can organize a minimal test matrix:

| Case | Purpose |
| --- | --- |
| Each valid subtype | Ensure the right case is selected |
| Subtype with invalid data | Ensure false guard routes to the right fallback |
| Child subtype of a shared parent type | Check ordering and dominance |
| Null input | Preserve legacy behavior |
| Unsupported type, if selector allows | Check default/error branch |
| Adding a new subtype to sealed hierarchy | Verify compiler forces switch update |
| Logging, exceptions, or side effects present | Check execution order and count |

## 11. Common mistakes and warning signs

**Mistake 1: Changing syntax but dropping the false-guard branch.** A case with `when` does not represent the entire subtype; there must be a remaining case if that subtype can fail the condition.

**Mistake 2: Forgetting null when converting an instanceof chain to switch.** Legacy code often falls through to the final branch; new code may throw NullPointerException if null is not handled.

**Mistake 3: Putting a too-broad type pattern first.** The compiler may report later cases as dominated; when reordering, check whether you are changing legacy behavior.

**Mistake 4: Using record patterns on non-record classes.** Java does not have arbitrary deconstructors applicable to ordinary classes.

**Mistake 5: Using default to silence missing-subtype errors.** This can hide important warnings when a sealed hierarchy evolves.

**Mistake 6: Assuming all components extracted from a record are non-null.** An unconditional pattern can bind a null reference component; guards must check before calling methods.

**Mistake 7: Pulling complex business logic into an unreadable switch.** When conditions and side effects are complex, extract named methods instead of optimizing for fewer lines.

**Mistake 8: Testing only the happy paths.** Refactoring bugs often show up at boundary values, shadowed subtypes, null, exceptions, and newly added subtypes.

**Conclusion:** For **if-else chains by subtype**, start with type patterns to eliminate casts, then move to a switch expression when the branch structure fits. Record patterns let you extract record data directly in the case; sealed hierarchies let the compiler verify exhaustiveness. The real value of refactoring is **clearer code with preserved and verified behavior**, not merely swapping keywords.