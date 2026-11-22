# isSealed and getPermittedSubclasses in Java Reflection

## 1. Observing Inheritance Boundaries When Only Class Is Known at Runtime

A `sealed` type restricts which types are allowed to extend or implement it **directly**. This helps the model author control the first-level branches of the hierarchy, instead of allowing any class to add a new direct branch on its own.

When writing tools to inspect type structure, generate documentation, or validate models at runtime, you may only receive a `Class<?>`. Since Java 17, two APIs on `Class` support this need:

- `isSealed()`: is the class or interface under inspection a sealed type?
- `getPermittedSubclasses()`: which direct subclasses or subinterfaces are permitted and can be obtained as `Class` objects in the runtime environment?

These two questions describe **type structure**. They do not instantiate objects, do not invoke constructors, and do not automatically discover every existing object or every implementing class.

## 2. Contract of the Two Methods

| API | Result |
| --- | --- |
| `type.isSealed()` | `true` when type is a sealed class or interface |
| `type.getPermittedSubclasses()` | `Class<?>[]` for a sealed type; `null` if type is not sealed |

Keep the different cases distinct:

- **Not sealed:** `isSealed()` is `false`, `getPermittedSubclasses()` is `null`.
- **Sealed:** `isSealed()` is `true`, the returned array is non-`null`.
- **Sealed with an empty result:** a zero-length array may be returned per the API contract; do not use length greater than 0 as the condition to detect whether a type is sealed.

For primitive types, `void`, and array types, `isSealed()` returns `false`, and `getPermittedSubclasses()` returns `null`.

The name `getPermittedSubclasses` does not mean the API only applies to classes. When called on a sealed interface, it can return both directly implementing classes and direct subinterfaces.

The order of elements in the array is unspecified. If stable output is needed for printing, display, or comparison, sort it yourself.

## 3. Complete Example: Sealed Interface, Subinterface, and Open Branch

Save as `SealedInspectionDemo.java`:

~~~java
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.stream.Collectors;

public class SealedInspectionDemo {
    sealed interface Event
            permits DataEvent, Command, Extension {
    }

    record DataEvent(String text) implements Event {
    }

    sealed interface Command extends Event permits Start, Stop {
    }

    record Start() implements Command {
    }

    record Stop() implements Command {
    }

    non-sealed interface Extension extends Event {
    }

    static final class PluginEvent implements Extension {
    }

    private static void show(Class<?> type) {
        Class<?>[] permitted = type.getPermittedSubclasses();

        System.out.println(type.getSimpleName()
                + ".isSealed=" + type.isSealed());

        String names = permitted == null
                ? "null"
                : Arrays.stream(permitted)
                      .map(Class::getSimpleName)
                      .sorted()
                      .collect(Collectors.joining(","));

        System.out.println(type.getSimpleName()
                + ".permitted=" + names);
    }

    public static void main(String[] args) {
        show(Event.class);
        show(Command.class);
        show(Extension.class);
        show(DataEvent.class);

        System.out.println("Event.directHasStart="
                + Arrays.asList(Event.class.getPermittedSubclasses())
                      .contains(Start.class));
        System.out.println("Event.assignableFromStart="
                + Event.class.isAssignableFrom(Start.class));
        System.out.println("Extension.assignableFromPluginEvent="
                + Extension.class.isAssignableFrom(PluginEvent.class));
        System.out.println("DataEvent.final="
                + Modifier.isFinal(DataEvent.class.getModifiers()));
    }
}
~~~

Compile and run with JDK 17 or later; no preview flag is needed:

~~~bash
javac --release 17 SealedInspectionDemo.java
java SealedInspectionDemo
~~~

Output:

~~~text
Event.isSealed=true
Event.permitted=Command,DataEvent,Extension
Command.isSealed=true
Command.permitted=Start,Stop
Extension.isSealed=false
Extension.permitted=null
DataEvent.isSealed=false
DataEvent.permitted=null
Event.directHasStart=false
Event.assignableFromStart=true
Extension.assignableFromPluginEvent=true
DataEvent.final=true
~~~

The example shows:

1. `Event` directly permits three branches: `DataEvent`, `Command`, `Extension`.
2. `Command` is itself a sealed interface with its own two direct subtypes.
3. `Start` is a kind of `Event`, but it goes through `Command`, so it is not in `Event`'s direct list.
4. `Extension` is `non-sealed`. It can still have implementing classes like `PluginEvent`, even though its `getPermittedSubclasses()` returns `null`.
5. `DataEvent` is a record, which is implicitly `final`. It is not sealed, and does not allow further inheritance.

The declarations are placed inside the same outer class so they can compile cleanly in a single file. In projects with modules/packages, the rules on where direct subtypes are declared must still be satisfied.

## 4. Direct List vs. Entire Hierarchy

`getPermittedSubclasses()` reads the direct boundary of the exact type under inspection. It does not automatically return all types at every depth.

For the example above, the relationships can be read as follows:

~~~text
Event [sealed]
  Command [sealed]
    Start [final record]
    Stop [final record]
  DataEvent [final record]
  Extension [non-sealed]
    PluginEvent [an implementation example]
~~~

The branches immediately beneath a sealed node are where you can continue calling `getPermittedSubclasses()`. The relationship from `Extension` to `PluginEvent` is not discovered by this API; the example program knows it because that class is in the source code.

If you need to inspect deeper, you must call the API again on each sealed node. When encountering a non-sealed and non-final branch, you must record that the branch can continue to be extended. Do not turn it into a "final leaf" just because the API does not return a list of children.

`isAssignableFrom` answers a different question: can the target type accept values of the source type according to the type relationship? It includes indirect relationships. Therefore, `Event.class.isAssignableFrom(Start.class)` is `true` while `Start.class` is not in `Event`'s direct permitted array.

Also do not use `getSuperclass()` to traverse backwards through all interface relationships. A class has only one direct superclass, but can implement multiple interfaces. Type relationship structure must be read according to the proper kind of relationship.

## 5. final, sealed, and non-sealed Do Not Have the Same Meaning

| Declaration kind | Meaning for extensibility |
| --- | --- |
| `final class` | No subclasses |
| `sealed class/interface` | Only the permitted direct subtypes |
| `non-sealed class/interface` | Reopens extensibility on that branch |
| Ordinary unsealed class/interface | Carries no sealed restriction of its own |

`isSealed() == false` does not prove that the source code used the `non-sealed` keyword. A final class, an ordinary class, or an ordinary interface can produce that same result.

In Java 17, there is no `Class.isNonSealed()` method. If you are at a known direct subtype of a sealed type, you can also use the type kind and the final flag to explain the branch's status according to the model. However, do not label every unsealed and non-final class across the entire system as "declared non-sealed".

Also do not detect sealed by searching for the string `sealed` in the output of `Modifier.toString`. Use `Class.isSealed()` for the sealed question and `Modifier.isFinal` for the corresponding final question.

A sealed class is not required to be abstract. Being permitted in the permitted list also does not guarantee that the type can be instantiated directly: it may be an interface or an abstract class, or require specific constructor arguments.

## 6. Example: Traversing Sealed Branches and Marking Open Points

Save as `SealedBranchWalkDemo.java`:

~~~java
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.Comparator;

public class SealedBranchWalkDemo {
    static abstract sealed class Result
            permits Success, Failure, Extensible {
    }

    static final class Success extends Result {
    }

    static abstract sealed class Failure extends Result
            permits Invalid, Timeout {
    }

    static final class Invalid extends Failure {
    }

    static final class Timeout extends Failure {
    }

    static non-sealed class Extensible extends Result {
    }

    static final class Custom extends Extensible {
    }

    private static void showBranch(Class<?> type, int depth) {
        String state = type.isSealed()
                ? "sealed"
                : Modifier.isFinal(type.getModifiers()) ? "final" : "open";

        System.out.println("  ".repeat(depth)
                + type.getSimpleName() + " [" + state + "]");

        if (!type.isSealed()) {
            return;
        }

        Class<?>[] children = type.getPermittedSubclasses();
        Arrays.sort(children, Comparator.comparing(Class::getName));
        for (Class<?> child : children) {
            showBranch(child, depth + 1);
        }
    }

    public static void main(String[] args) {
        showBranch(Result.class, 0);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 SealedBranchWalkDemo.java
java SealedBranchWalkDemo
~~~

Output:

~~~text
Result [sealed]
  Extensible [open]
  Failure [sealed]
    Invalid [final]
    Timeout [final]
  Success [final]
~~~

The word `open` here is the tool's display label for a node that is neither sealed nor final. In the specific model, `Extensible` is declared `non-sealed`.

`Custom` is not printed. It still exists in the example, but cannot be listed via `Extensible.class.getPermittedSubclasses()`. The printout must be understood as **the branches reachable via sealed metadata**, not a complete scan of every class in the application.

The example uses single class inheritance to stay focused on the API. If you extend a tool to interface graphs, the same type may appear along multiple paths; you must decide whether to display it again per path or track a set of visited `Class` objects to avoid duplicate processing.

## 7. Runtime Limitations of the Result

The API attempts to obtain `Class` objects for the types recorded as directly permitted, using the defining class loader of the type under inspection. If a `Class` object cannot be obtained, the corresponding entry may be silently omitted per the API contract.

Therefore:

- Do not treat the returned array as a guaranteed complete copy of every name recorded in the class file in all environments.
- An empty array is not equivalent to `isSealed() == false`.
- If an auditing tool needs to cross-check every name in binary metadata, it must have a suitable process for inspecting class files and the loading environment; these two APIs alone do not provide a per-entry report of omitted items.
- Access checks specified by the API can still fail, such as throwing `SecurityException` in environments with an active policy.

The example has all compiled classes in the same directory, so it retrieves the types shown in the output. In production deployments, do not patch a missing result by guessing class names or ignoring broken packaging.

Calling the metadata methods also does not imply that the JVM does no work: it may involve loading the required types. Neither API instantiates instances or executes constructors of the listed types. There is no need to speculatively instantiate each type just to display names and permitted relationships.

## 8. Applications and Inference Boundaries

**Model viewer:** displays direct branches, marking sealed nodes, final nodes, and open points. If an empty array or loading failure occurs, accurately convey the level of information obtained.

**Architecture check:** confirms that expected direct types are present, or detects changes in the deployed model. Compare using a canonical set/key rather than relying on the API's array order.

**Documentation tool:** links each type to its description. When a `non-sealed` branch is present, note that deeper subclasses may come from elsewhere.

**Object creation tool:** the permitted list is only a structural discovery step. It does not replace choosing the business type, checking permission to use that type, preparing data, or finding a valid constructor.

Do not assume that a sealed root always forms a finite set of concrete classes at every depth. A `non-sealed` branch can continue to expand. Even a tree without open points must still be interpreted accurately with respect to abstract classes, instantiable types, and the completeness of the metadata obtained.

The permitted list is also not a list of live objects, registered beans, or activated plugins. Those systems have their own lifecycles and registration sources.

## 9. Common Mistakes

| Mistake | Correct understanding or handling |
| --- | --- |
| Immediately iterating `getPermittedSubclasses()` on every `Class` | Check whether it is sealed or handle the `null` case |
| Using array length greater than 0 to detect sealed | Use `isSealed()`; a sealed array can be empty |
| Assuming the API returns all indirect subtypes | Only includes obtainable direct subtypes |
| Assuming every element is a concrete class | May include interfaces or abstract classes |
| Calling `getPermittedSubclasses()` on `non-sealed` to find implementations | The API returns `null`; another discovery source is needed if truly required |
| Treating array order as source order | Sort output yourself; API order is unspecified |
| Equating not sealed with the `non-sealed` keyword | Distinguish `final`, ordinary types, and reopened branches |
| Treating the returned array as sufficient proof of every entry in the class file | Account for the API's ability to omit entries whose `Class` cannot be obtained |
| Speculatively instantiating every permitted type | Permitted metadata does not provide an object instantiation contract |

When writing a utility function, decide whether you need to preserve the distinction between "not sealed" and "sealed with an empty result". Returning an empty list for both may be convenient for loops, but loses information if the caller needs to classify the model.

## 10. Self-Check

1. Why is `Start` not in `Event`'s direct permitted list, even though `Start` is a kind of `Event`?
2. Does `Extension.class.getPermittedSubclasses()` returning `null` mean `PluginEvent` cannot exist?
3. Is `isSealed() == false` sufficient to assert that a type was declared `non-sealed`?
4. Does the API guarantee the same order as the `permits` list in source code?
5. For an unsealed `Class`, should you directly access `getPermittedSubclasses().length`?
6. Must an element in the permitted array necessarily be instantiable via a no-arg constructor?

Answers:

1. `Start` directly implements `Command`; its relationship to `Event` is indirect.
2. No. `null` here means the type under inspection is not sealed; it is not an enumeration of implementations.
3. No; `final` or ordinary types can also be not sealed.
4. No. If stability is needed, you must sort according to your tool's rules.
5. No; the result is `null`, so accessing its length will throw `NullPointerException`.
6. No. It may be an interface, an abstract class, or a class with different constructor requirements.

## References

- [Java 17 — Class.isSealed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isSealed()).
- [Java 17 — Class.getPermittedSubclasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()).
- [JLS 17 — sealed, non-sealed, and final classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2).
- [JLS 17 — sealed and non-sealed interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4).
