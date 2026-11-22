# Mixed Hierarchies of sealed, non-sealed, final, enum, and record

## 1. Multiple Type Kinds Can Represent One Model Together

A command model may require multiple forms of representation:

- A `record` carrying the command's data.
- An `enum` representing fixed choices.
- A `final` class with its own custom implementation.
- A `sealed` branch splitting further into smaller cases.
- A `non-sealed` branch allowing the system to extend further.

When reading the model via Reflection, do not split all types into two groups—"sealed" and "not sealed"—and stop there. You need to combine `isSealed()`, `isEnum()`, `isRecord()`, the `final` modifier, and direct relationships.

A single type can satisfy multiple properties simultaneously: a record is a `final` class; an enum can be implicitly `final` or implicitly `sealed`. Those properties describe different dimensions, not mutually exclusive labels.

## 2. Why Is a Sealed Interface Usually Chosen as the Common Root?

A record's direct superclass is `java.lang.Record`. An enum's direct superclass is `java.lang.Enum` with the corresponding type parameter. They cannot choose another domain class as their direct superclass.

Both records and enums can implement interfaces. Therefore, if you want a common root that directly contains records, enums, and ordinary classes, a sealed interface is the appropriate choice.

Conceptual example:

~~~text
Command — sealed interface
  Payload — record, final
  Halt — enum, implicitly final
  Policy — enum, implicitly sealed
  SystemCommand — sealed interface
    Reset — final class
    Trace — record, final
  Extension — non-sealed class
    PluginCommand — an extension example
~~~

This diagram preserves direct relationships. `Reset` and `Trace` belong to the `SystemCommand` branch; `PluginCommand` belongs to the `Extension` branch, not as direct entries of `Command`.

The directly permitted subtypes of a sealed interface must satisfy the extensibility rules: classes must be `final`, `sealed`, or `non-sealed` (including the implicit properties of enums/records); subinterfaces must continue as `sealed` or `non-sealed`.

## 3. Records and Enums Have Their Own Implicit Rules

| Type kind | Final? | Sealed? | Meaning for the hierarchy |
| --- | --- | --- | --- |
| Record | Always `final` | Not `sealed` | No subclasses |
| Enum with no constants carrying their own class body | Implicitly `final` | Not `sealed` | No constant-specific subclasses |
| Enum with at least one constant carrying its own class body | Not `final` | Implicitly `sealed` | Permits anonymous subclasses corresponding to the constant bodies |
| Ordinary `final` class | Yes | Not `sealed` | Stops inheritance at that class |
| `sealed` class/interface | Not simultaneously `final` | Yes | Controls direct subtypes |
| `non-sealed` class/interface | Not `final` | Not `sealed` | Reopens extensibility on that branch |

For a record, there is no need to write `final` explicitly to satisfy a sealed interface's rules; finality is already built in. Records cannot be declared `sealed` or `non-sealed`.

For an enum, do not manually add `final`, `sealed`, or `non-sealed` modifiers to the declaration. Java determines finality/sealing from whether the constants have their own class bodies.

Therefore, merely checking whether the source code has the `sealed` keyword at the top of an enum is not enough. `Class.isSealed()` can return `true` for an enum without the author ever writing that keyword.

## 4. Complete Example: Inspecting the Entire Model via Reflection

Save as `MixedSealedHierarchyDemo.java`:

~~~java
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.Comparator;
import java.util.stream.Collectors;

public class MixedSealedHierarchyDemo {
    sealed interface Command
            permits Payload, Halt, Policy, SystemCommand, Extension {
    }

    record Payload(String text) implements Command {
    }

    enum Halt implements Command {
        INSTANCE
    }

    enum Policy implements Command {
        STRICT {
            @Override
            int limit() {
                return 1;
            }
        },
        LENIENT;

        int limit() {
            return 10;
        }
    }

    sealed interface SystemCommand extends Command
            permits Reset, Trace {
    }

    static final class Reset implements SystemCommand {
    }

    record Trace(String area) implements SystemCommand {
    }

    static abstract non-sealed class Extension implements Command {
    }

    static final class PluginCommand extends Extension {
    }

    private static String role(Class<?> type) {
        if (type.isEnum()) {
            return "ENUM";
        }
        if (type.isRecord()) {
            return "RECORD";
        }
        if (type.isSealed()) {
            return "SEALED_BRANCH";
        }
        if (Modifier.isFinal(type.getModifiers())) {
            return "FINAL_CLASS";
        }
        return "OPEN_TYPE";
    }

    private static void show(Class<?> type) {
        System.out.println(type.getSimpleName()
                + " role=" + role(type)
                + " sealed=" + type.isSealed()
                + " final=" + Modifier.isFinal(type.getModifiers()));
    }

    private static String directNames(Class<?> sealedType) {
        return Arrays.stream(sealedType.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        show(Command.class);
        Arrays.stream(Command.class.getPermittedSubclasses())
                .sorted(Comparator.comparing(Class::getName))
                .forEach(MixedSealedHierarchyDemo::show);

        show(Reset.class);
        show(Trace.class);
        show(PluginCommand.class);

        System.out.println("Command.direct=" + directNames(Command.class));
        System.out.println("SystemCommand.direct="
                + directNames(SystemCommand.class));

        Class<?>[] policyChildren = Policy.class.getPermittedSubclasses();
        System.out.println("Policy.permitted=" + policyChildren.length);
        System.out.println("Policy.anonymousChild="
                + policyChildren[0].isAnonymousClass());
        System.out.println("STRICT.runtimeEnum="
                + Policy.STRICT.getClass().isEnum());
        System.out.println("STRICT.declaring="
                + Policy.STRICT.getDeclaringClass().getSimpleName());

        System.out.println("Extension.permitted="
                + Extension.class.getPermittedSubclasses());
        System.out.println("PluginCommand.isCommand="
                + Command.class.isAssignableFrom(PluginCommand.class));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 MixedSealedHierarchyDemo.java
java MixedSealedHierarchyDemo
~~~

Output with JDK 17:

~~~text
Command role=SEALED_BRANCH sealed=true final=false
Extension role=OPEN_TYPE sealed=false final=false
Halt role=ENUM sealed=false final=true
Payload role=RECORD sealed=false final=true
Policy role=ENUM sealed=true final=false
SystemCommand role=SEALED_BRANCH sealed=true final=false
Reset role=FINAL_CLASS sealed=false final=true
Trace role=RECORD sealed=false final=true
PluginCommand role=FINAL_CLASS sealed=false final=true
Command.direct=Extension,Halt,Payload,Policy,SystemCommand
SystemCommand.direct=Reset,Trace
Policy.permitted=1
Policy.anonymousChild=true
STRICT.runtimeEnum=false
STRICT.declaring=Policy
Extension.permitted=null
PluginCommand.isCommand=true
~~~

Names are sorted before printing. The array order returned by `getPermittedSubclasses()` is not used as a required order.

The `directNames` helper is only called with types known to be sealed. In a general-purpose tool, you must check whether a type is sealed or handle a `null` result before iterating.

## 5. Reading Each Node Type in the Output

### 5.1. A record is a data type closed to inheritance

`Payload` and `Trace` are identified by `isRecord()`, and also carry the `final` modifier. They do not need the `final` keyword in the example.

"Closed to inheritance" does not mean there is only one value. A record `Payload(String text)` can have many instances with different data. It simply prevents another class from extending it to create additional subclass forms.

Component types inside a record also do not automatically become inheritance edges. `Payload` having a `String` component does not mean `String` is a sub-branch of `Payload`.

### 5.2. A simple enum is final, yet can have multiple constants

`Halt` has no custom class body on any constant, so it is implicitly `final`. The example uses a single constant `INSTANCE`, yet an enum with many constants and no custom bodies still has that same `final` property.

The number of enum constants and the number of subclasses are two different numbers. To get enum values, use `getEnumConstants()`; do not use the permitted array to count constants.

### 5.3. An enum with custom bodies creates a technical class layer

`Policy.STRICT` has its own body to override `limit()`. Java generates an anonymous subclass of `Policy` for that body, and `Policy` becomes implicitly `sealed`.

In the example only `STRICT` has a custom body, so `Policy`'s permitted list has one class. `LENIENT` does not generate a corresponding separate class.

The `Policy.STRICT` object has that anonymous subclass as its runtime class, so `getClass().isEnum()` is `false`. `getDeclaringClass()` still returns `Policy.class`, which is the enum class declaring the constant.

Do not use compiler-generated anonymous class names as business variant names. That relationship is valid class metadata, but must be interpreted according to the tool's purpose.

### 5.4. A sealed branch continues providing direct branches

`SystemCommand` remains `sealed`, so it has its own direct list consisting of `Reset` and `Trace`.

`Reset` is an ordinary `final` class. `Trace` is a `final` record. Both nodes stop inheritance, yet have different declaration kinds and data metadata.

Do not check only `final` and lose record information, if the tool also needs to display record components or canonical constructors.

### 5.5. A non-sealed branch reopens extensibility

`Extension` is an `abstract non-sealed` class. It cannot be instantiated directly because it is `abstract`, yet allows other classes to extend the branch.

`PluginCommand` is an example. It is an indirect kind of `Command`, yet does not appear in `Command`'s direct permitted list.

`Extension.getPermittedSubclasses()` returns `null` because `Extension` is not sealed. `null` does not mean no subclasses exist; it does not provide a list of subclasses for an open branch.

The `OPEN_TYPE` label from `role` only has the technical meaning "not enum/record/sealed/final according to those checks". It is not general proof that every type receiving this label was declared with the `non-sealed` keyword. In this specific model, we know `Extension` is a `non-sealed` branch from its declaration and its direct position beneath a sealed type.

## 6. JVM Class Hierarchy vs. Business Model Presentation

The same metadata can be presented for two different purposes:

**Compiled-class viewer:** can expand `Policy` to show the anonymous subclass of the `STRICT` constant. This is appropriate when diagnosing override behavior or class relationships.

**Command-type viewer:** can present `Policy` as an enum type, with constants `STRICT` and `LENIENT` as value choices. There is no need to turn `STRICT`'s anonymous class into a new command type with a business name.

That is a presentation policy that should be stated explicitly, rather than altering metadata to make enums unsealed.

`role` checks enum and record before more general properties:

1. Enum: preserve the fact that it is an enum, even when the enum is sealed.
2. Record: preserve component information, even though records are also `final`.
3. Remaining sealed: can traverse further into directly permitted types.
4. Remaining `final`: a class terminating inheritance.
5. Remaining types: mark as open points or needing additional information.

If `isSealed()` is checked first and always recursed as a business branch, the tool may descend into an enum's anonymous class unintentionally. If `final` is checked first, records and `final` enums may lose their specialized labels.

There is no single mandatory classification order for every tool. The order above serves the command-type presentation in this article; a bytecode viewer might retain all flags and relationships simultaneously instead of picking one primary label.

## 7. A "Sealed Root" Does Not Guarantee the Whole Model Is Closed at Every Depth

The root controls direct branches. A `non-sealed` branch can continue extending with types not known to the tool in advance.

Therefore, you cannot take only `Command`'s permitted list and conclude you know every concrete class that can be a `Command`. At minimum, the `Extension` branch makes that inference false in this model.

Even when all branches are `final` or `sealed`, you must still distinguish:

- Number of declared types vs. number of values/instances.
- Concrete classes vs. `abstract` classes and interfaces.
- Enum classes vs. enum constants.
- Record classes vs. the data carried in their components.
- Obtained permitted structure vs. the completeness of the class-loading environment.

`getPermittedSubclasses()` returns only direct subtypes and can omit entries whose `Class` object cannot be obtained per the API contract. Auditing tools requiring stronger guarantees must cross-check the appropriate data and environment.

A permitted list also does not supply constructors, input data, or instantiation permission. Do not attempt to instantiate every node in the diagram just to verify that it belongs to the hierarchy.

## 8. Designs and Assumptions to Avoid

| Assumption or practice | Problem |
| --- | --- |
| Using a domain sealed class as the direct parent of both records and enums | Records and enums already have Java-mandated direct superclasses; use a common interface when needed |
| Manually adding `sealed`/`final`/`non-sealed` to an enum declaration | Those modifiers are not explicitly declared on enums; properties are inferred from enum rules |
| Assuming a record without `final` written can be subclassed | Records are implicitly `final` |
| Using `isSealed() == false` to conclude there are no subclasses | `non-sealed` branches and ordinary classes can have subclasses |
| Counting an enum's permitted list to count its constants | Only reflects subclasses for constant bodies, not all enum values |
| Using `constant.getClass()` as the general enum type | Constants with custom bodies have anonymous subclasses; use `getDeclaringClass()` |
| Every `final` node should be displayed the same way | Records, enums, and ordinary `final` classes have different metadata and semantics |
| Expanding every sealed enum into new "business types" | Confuses a constant's implementation class with an enum type in the model |
| One permitted call at the root lists all descendants | Direct lists and open branches do not allow that inference |

When a model contains both classes and interfaces, also preserve `Class` identity rather than merging by simple name. The names used in the examples are unambiguous within a single file; an application with multiple packages or class loaders can be more complex.

## 9. Self-Check

1. Why is a sealed interface an appropriate common root for both records and enums?
2. Is an enum with no custom bodies on its constants `final` or `sealed`?
3. If only one of three enum constants has a custom body, must the enum's permitted class count necessarily be three?
4. Why does `Policy` still receive the enum label even though `isSealed()` returns `true`?
5. Must `PluginCommand` appear in `Command`'s direct permitted list?
6. Does a `final` record mean there can only be one record instance?
7. When writing a bytecode viewer, can an enum's anonymous subclass be kept in the diagram?

Answers:

1. Records and enums can implement interfaces, whereas they cannot choose another domain class as their direct superclass.
2. Implicitly `final`.
3. No. Permitted classes correspond to constant bodies; in that scenario there is only one body.
4. "Enum" describes the type kind, while `sealed` describes the extensibility relationship; both facts can be true at the same time.
5. No. It inherits through the `Extension` branch.
6. No. `final` only closes inheritance; data and instance count are separate matters.
7. Yes. That is real class metadata; state the purpose clearly and do not treat it as a new business type.

## References

- [JLS 17 — sealed, non-sealed, final, and direct subtypes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2).
- [JLS 17 — Implicitly final or sealed enums](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9).
- [JLS 17 — Final records and direct superclass](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10).
- [Java 17 — Class.getPermittedSubclasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()).
