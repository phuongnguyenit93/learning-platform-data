# How Does `permits` Metadata Differ from Every Existing Subtype?

`getPermittedSubclasses()` is often misunderstood as a way to "get all subtypes" of a class or interface. In reality, it reads a specific piece of **sealed hierarchy** metadata: the **directly permitted** subtypes of the type under inspection.

That is a different question from "what descendants exist", "which classes has the JVM loaded", or "what objects currently exist". Distinguishing these questions helps type-analysis tools, data mappers, or plugin processors avoid concluding that a list is complete when there is not enough basis to do so.

The sealed APIs in this article are available from Java 17 onward. The examples run on Java 17 or later, with no preview features required.

## 1. Four Sets of Information That Should Not Be Conflated

| Question | Scope of information |
| --- | --- |
| Which direct subtypes does the sealed root permit? | `permits` metadata of the root itself |
| Which types are direct or indirect descendants? | Type relationships over a defined scope of types |
| Which classes has the JVM loaded so far? | Class loading state at the moment of observation |
| Which objects are currently held or live? | Object state; not the type declaration list |

A class can be an indirect descendant without appearing in the root's direct list. A permitted type also does not need any instantiated objects to appear in metadata.

`Class.isAssignableFrom(candidate)` checks the relationship with **a given candidate**. It does not discover or list all candidates in the environment.

## 2. Meaning of Sealed Metadata

In Java, `sealed` restricts direct subtypes. For a sealed interface, permitted entries can be implementing classes or subinterfaces. These rules are defined in [the sealed hierarchy specification for classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.6) and [interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.4).

At the `.class` file level, the [`PermittedSubclasses`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.31) attribute records the types permitted to directly extend or implement the current type. It is not an object registry, nor does it store the entire descendant tree.

The API name contains `Subclasses`, yet when used with an interface, the result can still include subinterfaces. An entry in the result can also be an abstract class; you must not assume every entry is an instantiable class.

### The word `permits` does not have to appear in source code

When language conditions allow, the compiler infers the set of permitted subtypes from the same compilation unit. Therefore, a declaration that does not explicitly write a `permits` clause still has sealed metadata.

Reflection reads the compiled type structure; it is not searching for the literal text `permits` in the source file.

## 3. Hierarchy Used in the Experiment

```mermaid
flowchart TD
    E["Event · sealed"] -->|permits| S["Saved · final"]
    E -->|permits| L["LocalEvent · sealed, abstract"]
    E -->|permits| X["Extension · non-sealed"]
    L -->|permits| R["Renamed · final"]
    X -.->|known subtype| A["PluginA"]
    X -.->|known subtype| B["PluginB"]
```

The `permits` edges are direct metadata relationships. The two dashed edges illustrate subtypes of the open branch that the program already knows through another mechanism; they are not obtained from `Extension.getPermittedSubclasses()`.

## 4. Standalone Runnable Java 17+ Example

Save everything into **`SealedPermitsDemo.java`**:

```java
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class SealedPermitsDemo {
    public sealed interface Event permits Saved, LocalEvent, Extension {
    }

    public record Saved(String id) implements Event {
    }

    public abstract static sealed class LocalEvent implements Event
            permits Renamed {
    }

    public static final class Renamed extends LocalEvent {
    }

    public non-sealed interface Extension extends Event {
    }

    public static final class PluginA implements Extension {
    }

    public static final class PluginB implements Extension {
    }

    public sealed interface Inferred {
    }

    public static final class InferredLeaf implements Inferred {
    }

    private static String names(Class<?>[] types) {
        return Arrays.stream(types)
                .map(Class::getSimpleName)
                .sorted()
                .toList()
                .toString();
    }

    private static String permittedNames(Class<?> type) {
        Class<?>[] permitted = type.getPermittedSubclasses();
        return permitted == null ? "null" : names(permitted);
    }

    private static boolean isDirectPermitted(Class<?> parent, Class<?> candidate) {
        Class<?>[] permitted = parent.getPermittedSubclasses();
        return permitted != null
                && Arrays.asList(permitted).contains(candidate);
    }

    private static void collectByPermits(Class<?> type, Set<Class<?>> visited) {
        if (!visited.add(type)) {
            return;
        }
        Class<?>[] permitted = type.getPermittedSubclasses();
        if (permitted != null) {
            for (Class<?> child : permitted) {
                collectByPermits(child, visited);
            }
        }
    }

    public static void main(String[] args) {
        System.out.println("Event permits = " + permittedNames(Event.class));
        System.out.println("LocalEvent permits = " + permittedNames(LocalEvent.class));
        System.out.println("Extension isSealed = " + Extension.class.isSealed());
        System.out.println("Extension permits = " + permittedNames(Extension.class));
        System.out.println("Saved isFinal = "
                + Modifier.isFinal(Saved.class.getModifiers()));
        System.out.println("Saved permits = " + permittedNames(Saved.class));

        System.out.println("Renamed fits Event = "
                + Event.class.isAssignableFrom(Renamed.class));
        System.out.println("Renamed directly permitted by Event = "
                + isDirectPermitted(Event.class, Renamed.class));
        System.out.println("PluginA fits Event = "
                + Event.class.isAssignableFrom(PluginA.class));
        System.out.println("PluginA directly permitted by Event = "
                + isDirectPermitted(Event.class, PluginA.class));

        Set<Class<?>> reached = new HashSet<>();
        collectByPermits(Event.class, reached);
        reached.remove(Event.class);
        System.out.println("Reached through permits = "
                + names(reached.toArray(Class<?>[]::new)));

        Class<?>[] candidates = {
                Saved.class, LocalEvent.class, Renamed.class,
                Extension.class, PluginA.class, PluginB.class, String.class
        };
        System.out.println("Matching supplied candidates = "
                + Arrays.stream(candidates)
                        .filter(Event.class::isAssignableFrom)
                        .map(Class::getSimpleName)
                        .sorted()
                        .toList());

        List<Event> objects = List.of(new Saved("S1"), new PluginA());
        System.out.println("Types in supplied objects = "
                + objects.stream().map(Object::getClass)
                        .map(Class::getSimpleName)
                        .distinct()
                        .sorted()
                        .toList());
        System.out.println("Event permits after creating objects = "
                + permittedNames(Event.class));
        System.out.println("Inferred permits = "
                + permittedNames(Inferred.class));
        System.out.println("Object permits = " + permittedNames(Object.class));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 -Xlint:all -Werror SealedPermitsDemo.java
java SealedPermitsDemo
```

Output:

```text
Event permits = [Extension, LocalEvent, Saved]
LocalEvent permits = [Renamed]
Extension isSealed = false
Extension permits = null
Saved isFinal = true
Saved permits = null
Renamed fits Event = true
Renamed directly permitted by Event = false
PluginA fits Event = true
PluginA directly permitted by Event = false
Reached through permits = [Extension, LocalEvent, Renamed, Saved]
Matching supplied candidates = [Extension, LocalEvent, PluginA, PluginB, Renamed, Saved]
Types in supplied objects = [PluginA, Saved]
Event permits after creating objects = [Extension, LocalEvent, Saved]
Inferred permits = [InferredLeaf]
Object permits = null
```

`names()` and the list-printing sections explicitly sort the names. The program does not rely on the array's return order to determine type relationships.

## 5. Direct Does Not Mean All Descendants

`Event` directly permits `Saved`, `LocalEvent`, and `Extension`. `Renamed` is directly permitted by `LocalEvent`.

Therefore, the following two results do not contradict each other:

- `Event.class.isAssignableFrom(Renamed.class)` is `true`: `Renamed` has a valid type relationship with `Event` through `LocalEvent`.
- `Renamed` is not in `Event`'s direct list.

To go deeper into the sealed portion, you must query each sealed subtype in turn. `collectByPermits` performs that step and additionally finds `Renamed`.

However, the result `[Extension, LocalEvent, Renamed, Saved]` is only the nodes reachable via the metadata edges that the function traversed. It is not proof that no other subtypes exist in the entire hierarchy.

The `visited` set uses `Class<?>` to avoid duplicate processing if the same type is reached across multiple interface branches. The code prints short names only for readability; real tools should not identify types solely by `getSimpleName()`.

## 6. `non-sealed` Is an Open Boundary

`Extension` is permitted to directly extend `Event`, yet `Extension` itself is `non-sealed`. As a result, classes can implement `Extension` under the ordinary rules of accessibility and type relationships.

`PluginA` and `PluginB` are valid examples on that branch. They conform to `Event`, yet do not need to appear in `Event.permits` because they do not directly implement `Event`.

`Extension.class.getPermittedSubclasses()` returns `null`. This means **`Extension` is not a sealed type**, not that **`Extension` has no implementing classes**.

In the same experiment, `Saved` is a `final` record, which also returns `null`. Yet `Saved` has no valid subtypes, whereas `Extension` is an open branch. Therefore, seeing `null` alone is not enough to conclude that the hierarchy terminates in the same sense.

Even `Object.class.getPermittedSubclasses()` returns `null`, even though clearly a vast number of classes extend `Object`.

### When can a type tree be considered closed?

You can analyze a hierarchy along `sealed` and `final` branches once you have verified the metadata and that the required types are completely provided. If a `non-sealed` branch is encountered, traversing `permits` alone is not enough to enumerate all descendants of that branch.

Also do not collect only `final` leaves and call them "every class that can have instances". A sealed class can still be a concrete, non-abstract class; having subtypes does not prohibit instantiating that class itself. `LocalEvent` in the experiment is explicitly declared `abstract`.

## 7. Candidate Sets and Object Sets Are Different Sources

### Filtering supplied candidates

The program has a `candidates` array explicitly written in code. Filtering it with `Event.class::isAssignableFrom` finds both `PluginA` and `PluginB`.

This is **filtering a known set**, not automatically discovering every subtype in the JVM. If a class is not supplied in the candidate set, the filter will not find it on its own.

The result also includes `Extension` and `LocalEvent`, because the type relationship applies to subinterfaces and abstract classes as well. To get a list of concrete instantiable classes, additional criteria are needed; to know which constructors are suitable, further condition checks are required.

### Observing objects in a list

`Event`'s metadata array has three direct branches, while the `objects` list only contains one `Saved` and one `PluginA`. The result `[PluginA, Saved]` describes the classes of **the objects in that specific list**.

It does not describe every live object across the entire JVM, nor does it describe every valid type. Adding or removing objects in the list does not alter `Event`'s sealed metadata.

In an application, a plugin registry, configuration data, or a scanned scope of class files may provide the candidate set. Each source has its own scope and rules; do not turn its result into a global claim.

## 8. Obtaining `Class` Objects and Completeness Limits

The [`getPermittedSubclasses()` contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()) states that the API attempts to obtain `Class` objects for the entries recorded in metadata using the current type's defining class loader. Entries whose `Class` cannot be obtained are omitted and excluded from the returned array. Element order is not guaranteed; unsealed types return `null`, while sealed types return a non-`null` array, which may be empty.

That has two consequences to make explicit in tooling:

- The result is not a passive snapshot of classes already loaded prior to the call; the API performs work to obtain the needed `Class` objects.
- Array length alone should not be used to assert that every expected entry in a deployment artifact resolved successfully.

If a tool must prove list completeness against class-file metadata or a release artifact, it must cross-check the corresponding source and type resolution. Do not silently treat an absent entry as proof that the type was never permitted.

In the experiment, all class files are provided together in full, so concrete results can be cross-checked against the source code. This article does not assume every plugin environment or custom class loader shares those same conditions.

### Difference from the list of loaded classes

In the context of a Java agent, [`Instrumentation.getAllLoadedClasses()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#getAllLoadedClasses()) provides the classes currently loaded in the JVM at the time of observation. That is still a different data source: you can filter those classes by type relationship, but you cannot infer unloaded classes or live objects from that list.

Setting up an agent is a separate topic; the examples in this article do not use an agent and do not claim to measure when the JVM loads individual classes.

## 9. Choosing the Right Question When Designing Tools

| Need | Appropriate approach |
| --- | --- |
| Display direct branches of a sealed type | `getPermittedSubclasses()` with accurate scope interpretation |
| Traverse the closed portion of a hierarchy | Query each branch recursively, recording open boundaries and type-resolution limits |
| Check whether a candidate can be used in place of a root type | `isAssignableFrom` on the exact two `Class` objects |
| List plugins accepted by the application | Plugin registry or discovery source with a defined scope |
| Analyze loaded classes | Appropriate class-loading observation source, not `permits` metadata as a substitute |
| Count objects managed by the application | Object management data or observation tools suited to the requirement |

Relying solely on sealed metadata to accept or reject objects can also fail on open branches. For instance, a policy permitting any value of `Event` needs to recognize that `PluginA` is valid even though it is not in the root's direct list.

Conversely, if an application only allows a specific set of registered classes, that is an application-level policy. Do not equate it with Java's valid inheritance rules.

## 10. Common Mistakes and Self-Check

| Wrong inference | Distinction to maintain |
| --- | --- |
| `permits` list is all descendants | Direct vs. indirect |
| Recursive traversal is always complete | Closed branches vs. `non-sealed` branches |
| `null` means no subtypes exist | Not sealed vs. unable to have subtypes |
| Every entry is an instantiable class | Interfaces, abstract classes, and concrete classes |
| A listed type must have instances | Type metadata vs. object state |
| Result is the list of classes loaded before the call | Obtaining `Class` objects vs. observing class loading |
| No `permits` clause means no metadata | Explicit declaration vs. compiler-inferred set |
| Filtering a candidate array finds every class in the environment | Scope of the supplied candidates |

Verify your understanding with small changes:

1. Add a class `PluginC implements Extension`: must `Event`'s direct list be modified?
2. Add a new final descendant for `LocalEvent`: which results change at the root and at the branch?
3. Omit `Saved` from the `objects` list: why does `Event`'s metadata still contain `Saved`?
4. If you collect only `final` classes during traversal, is that enough to describe all subtypes or all instantiable classes?
5. When a deployment is missing a class file recorded in metadata, why should the returned array not be treated as a complete copy of the list in the `.class` file?

Interpret the scope accurately: **`permits` describes permission to form direct sealed type relationships; all descendants, loaded classes, and existing objects are different questions.**
