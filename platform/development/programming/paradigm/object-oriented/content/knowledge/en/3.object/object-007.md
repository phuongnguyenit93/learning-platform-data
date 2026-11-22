# Object Sharing and the Effects of State Changes in Java

Multiple components of a program can **share one object**. This is useful when all need to work with common state, but if the object is *mutable*, an operation in one place can cause unexpected results elsewhere.

This lesson focuses on three practical questions:

1. **Who holds a reference to the specific instance being modified?**
2. **Who may update its state, and when do other components observe the changes?**
3. **When do we need shared *live state*, and when do we need an independent *snapshot*?**

Assignment `b = a` copies a reference value; it does not duplicate the object. However, knowing that multiple aliases exist is not enough for safe design: we must understand **how the effects of changes propagate** through objects and the contracts between components.

## 1. A Change Can Affect Other Components Without Direct Calls Between Them

Suppose a room-temperature control application has two interfaces:

- `MobileControl` changes the target temperature.
- `WallDisplay` displays the current target temperature.
- Both receive **the same `TemperaturePolicy`** during construction; this object holds the state and validates permitted values.

When the phone changes the target from 22°C to 24°C, the wall display **does not need a new copy of the policy**. The next time `WallDisplay` reads the shared object, it sees 24°C.

An important subtlety: modifying an object **does not automatically cause the UI to redraw**. In this example, `render()` must be invoked again; a real UI needs notifications, events, polling, or an appropriate state-update mechanism to know when to render.

~~~mermaid
flowchart LR
    M["MobileControl"] -->|giữ tham chiếu| P["TemperaturePolicy<br/>target = 24"]
    W["WallDisplay"] -->|giữ tham chiếu| P
    M -. "changeTarget(24)" .-> P
    P -. "lần đọc tiếp theo" .-> W
~~~

The arrows represent **reference relationships and operations on objects**. They make no claim about JVM memory layout.

## 2. Complete Java Example: Live State, Snapshots, and Reference Reassignment

Save as `SharingScenario.java` and run with JDK 17+:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class SharingScenario {
    static final class TemperaturePolicy {
        private int targetCelsius;
        private final List<String> history = new ArrayList<>();

        TemperaturePolicy(int initial) {
            validate(initial);
            targetCelsius = initial;
        }

        private static void validate(int value) {
            if (value < 16 || value > 30) {
                throw new IllegalArgumentException(
                        "Mục tiêu phải trong khoảng 16..30");
            }
        }

        void setTarget(int newValue) {
            validate(newValue);
            int oldValue = targetCelsius;
            targetCelsius = newValue;
            history.add(oldValue + " -> " + newValue);
        }

        int getTarget() {
            return targetCelsius;
        }

        List<String> getHistorySnapshot() {
            return List.copyOf(history);
        }
    }

    static final class MobileControl {
        private final TemperaturePolicy policy;

        MobileControl(TemperaturePolicy policy) {
            this.policy = Objects.requireNonNull(policy);
        }

        void changeTarget(int value) {
            policy.setTarget(value);
        }
    }

    static final class WallDisplay {
        private final TemperaturePolicy policy;

        WallDisplay(TemperaturePolicy policy) {
            this.policy = Objects.requireNonNull(policy);
        }

        String render() {
            return "Mục tiêu: " + policy.getTarget() + "°C";
        }

        boolean uses(TemperaturePolicy other) {
            return policy == other;
        }
    }

    public static void main(String[] args) {
        TemperaturePolicy shared = new TemperaturePolicy(22);
        MobileControl mobile = new MobileControl(shared);
        WallDisplay wall = new WallDisplay(shared);

        String oldRenderedText = wall.render(); // Ảnh chụp dạng String
        List<String> oldHistory = shared.getHistorySnapshot();

        mobile.changeTarget(24);

        System.out.println(wall.uses(shared)); // true
        System.out.println(oldRenderedText);
        System.out.println(wall.render());
        System.out.println(oldHistory);
        System.out.println(shared.getHistorySnapshot());

        // Gán lại biến cục bộ mobile không thay reference trong wall.
        TemperaturePolicy replacement = new TemperaturePolicy(18);
        mobile = new MobileControl(replacement);
        mobile.changeTarget(19);

        System.out.println(wall.render());
        System.out.println(replacement.getTarget());
    }
}
~~~

Run:

~~~bash
javac SharingScenario.java
java SharingScenario
~~~

Output:

~~~text
true
Mục tiêu: 22°C
Mục tiêu: 24°C
[]
[22 -> 24]
Mục tiêu: 24°C
19
~~~

### Why Is This Output Correct?

**Initialization:** `shared`, the `policy` field of `mobile`, and the `policy` field of `wall` all reference the same `TemperaturePolicy`. The interface objects are distinct instances; **the policy** is what they share.

**First update:** `mobile.changeTarget(24)` calls `setTarget(24)` on that same policy. `wall.render()` reads the updated field and therefore returns `"Mục tiêu: 24°C"`. No `new TemperaturePolicy` is executed during this update.

**Snapshot:** `oldRenderedText` is the `String` created when the target was still 22. Since `String` is immutable, it remains `"Mục tiêu: 22°C"`. `oldHistory` is a structural snapshot taken while the list was empty, because `List.copyOf` does not reflect elements later appended to `history`. The `String` elements here are immutable too.

**Reassignment:** after `mobile = new MobileControl(replacement)`, only the `mobile` variable in `main` refers to another controller. `wall` keeps the old policy at 24, while the new policy changes from 18 to 19. Reassigning one variable does not update every other reference in the program.

## 3. Impact Table: Which Object Actually Changes?

| Point in time | Operation | Old policy held by `wall` | New policy | Text in `oldRenderedText` |
|---|---|---:|---:|---|
| Initialization | `new TemperaturePolicy(22)` | 22 | Does not exist | "Target: 22°C" (translated) |
| After phone update | `mobile.changeTarget(24)` | 24 | Does not exist | "Target: 22°C" (translated) |
| Create another controller | `mobile = new MobileControl(replacement)` | 24 | 18 | "Target: 22°C" (translated) |
| Phone updates again | `mobile.changeTarget(19)` | 24 | 19 | "Target: 22°C" (translated) |

The table distinguishes two forms of state:

- **Live state:** `wall.render()` reads data from the `TemperaturePolicy` that `wall` references **at call time**.
- **Captured values:** `oldRenderedText` and `oldHistory` retain data from the snapshot moment; they do not update automatically with the policy.

When debugging, rather than vaguely asking “Why is the display wrong?”, determine **which policy the display references and whether it uses freshly read or previously cached data**.

## 4. Direct Sharing and Sharing Through Nested Structures

Sharing is not limited to `TemperaturePolicy b = a`. An instance may also be passed through constructors, getters, method parameters, or collections.

~~~java
final class Device {
    final TemperaturePolicy policy;

    Device(TemperaturePolicy policy) {
        this.policy = policy;
    }
}

TemperaturePolicy policy = new TemperaturePolicy(22);
Device heater = new Device(policy);
Device airConditioner = new Device(policy);

heater.policy.setTarget(23);
System.out.println(airConditioner.policy.getTarget()); // 23
~~~

The snippet is a short illustration in a context where the main example's classes are accessible. **Two different `Device` objects** still hold the same child `TemperaturePolicy`. Creating two parent objects does not imply that all nested state is independent.

Conversely, if each device gets a new policy:

~~~java
Device heater = new Device(new TemperaturePolicy(22));
Device airConditioner = new Device(new TemperaturePolicy(22));
~~~

then changing the heater's policy does not affect the air conditioner's policy. Objects with identical initial data still have **different identities**.

### Collections and Registries Can Hold Aliases Too

~~~java
Map<String, TemperaturePolicy> registry = new HashMap<>();
registry.put("living-room", policy);

TemperaturePolicy fromRegistry = registry.get("living-room");
System.out.println(fromRegistry == policy); // true
~~~

This snippet requires `import java.util.Map;` and `import java.util.HashMap;`, with `policy` already declared. `Map.put/get` stores and returns **element references**; it does not automatically duplicate `TemperaturePolicy`.

If `registry.put("living-room", new TemperaturePolicy(18))` executes later, the map points to the new policy for that key; a `WallDisplay` that already holds the old policy **does not switch automatically**. This is a common error when replacing objects in registries/caches while other components retain old references.

## 5. Who Owns the State? Contracts Matter More Than Syntax

When passing a mutable object between components, specify **who may modify it** and **who may only observe it**.

| Contract type | Meaning | Implications for callers |
|---|---|---|
| **Live shared object** | Both parties hold the same mutable instance | Mutations on one side may appear when the other reads again |
| **Read-only API on a live object** | The recipient can only call read methods, while others may still mutate the object | Read results at two moments can differ |
| **Value snapshot** | The recipient holds data captured at one point in time | Old values do not automatically reflect new updates |
| **Independent mutable copy** | The recipient owns a copy of the necessary mutable components | Mutations to the copy do not affect source data within the separated scope |
| **Immutable value object** | Data does not change after initialization | Safer to share; updates generally return another value |

In the main example, `getHistorySnapshot()` returns `List.copyOf(history)` because history entries are immutable `String` values. If history contained mutable element objects, the list snapshot **would not guarantee snapshots of those elements**. Full separation would require an appropriate copying strategy for children, as explained in *Shallow and Deep Copies*.

Avoid vague API names such as `getData()` if users cannot tell whether they receive a live view, copy, or immutable value. Choose intention-revealing names such as `getHistorySnapshot()`, `currentTarget()`, and `withUpdatedTarget(...)`, and document mutation semantics explicitly.

## 6. State Changes Do Not Automatically Send Notifications

For example, `WallDisplay.render()` reads current data on every call, but if a display renders **only once** and caches the string, changing the policy does not transform that old string into a new one.

Interactive applications may require one of these mechanisms:

- The interface proactively **reads again** when a user opens a page or clicks Refresh.
- The updating component **publishes an event** carrying change data, and interested components subscribe.
- A state manager handles subscriptions and notifies observers when state changes.
- Another service retrieves updated state through an API or message rather than relying on references shared within one JVM.

Shared references only let components **access the same state** within one process; they do not automatically create reactive UIs, send network notifications, or allow separate JVMs to share one Java object.

When using events, decide whether each event carries an immutable snapshot or a reference to a mutable object: passing only a shared reference means its contents may change **after event publication**, causing recipients to observe unexpected values.

## 7. Unintended Risks and How to Reduce Side Effects

Several problems arise directly from shared mutable state:

**Modifying data without the caller's awareness.** A `normalize(profile)` helper that accepts a `Profile` and directly changes fields can cause its caller to observe unexpected profile changes. If mutation is permitted, document it in the API; if normalization is only for validation, return a new value or work on a copy.

**Leaking internal references.** A getter that returns a mutable `List` directly allows external code to bypass `addItem/removeItem` rules. An unmodifiable view only blocks changes through that view; another reference can still mutate the original list and alter the view's contents. Alternatives include snapshots of immutable data or dedicated query APIs.

**Replacing a reference in one place but not elsewhere.** `registry.put(key, replacement)` updates the registry, but objects caching `oldReference` still see the old instance. Use a consistent reference-update strategy or a stable holder/service queried by all parties.

**Retaining unintended sharing too long.** A component holding a reference can keep state reachable after other components have released it. This is a lifecycle/ownership issue; do not try to “free an object” with `a = null` while assuming all other aliases disappear.

Choose a design based on **business intent**. Sharing a service/configuration implementation may be correct; mechanically copying every object can waste memory and break relationships that the system deliberately needs.

## 8. When Multiple Threads Modify the Same Object

The earlier examples execute sequentially on **one thread**, yet aliasing and propagated effects already occur. When two threads update the same mutable object concurrently, **atomicity** and **visibility** become additional concerns.

~~~java
class UnsafeCounter {
    private int value;

    void increment() {
        value++; // Read -> calculate -> write, không nguyên tử.
    }

    int getValue() {
        return value;
    }
}
~~~

If two threads both call `increment()`, they may read the same old value and write the same result, causing a **lost update**. The `private` keyword does not eliminate race conditions.

For **one independent counter**, you can use:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

final class SafeCounter {
    private final AtomicInteger value = new AtomicInteger();

    void increment() {
        value.incrementAndGet();
    }

    int current() {
        return value.get();
    }
}
~~~

For **multiple fields with a shared invariant**, making each field atomic/volatile may still expose invalid intermediate states. For example, a temperature range satisfying `min <= max` can be encapsulated as an immutable value and updated by replacing the entire reference:

~~~java
record TemperatureRange(int min, int max) {
    TemperatureRange {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
    }
}

final class RangeConfiguration {
    private volatile TemperatureRange current =
            new TemperatureRange(18, 26);

    TemperatureRange snapshot() {
        return current;
    }

    void replace(int min, int max) {
        current = new TemperatureRange(min, max);
    }
}
~~~

This demonstrates **reading a consistent snapshot of a pair of values** using an immutable object and `volatile` reference assignment. If multiple writers must avoid overwriting one another or update based on prior values, appropriate synchronization or compare-and-set is still needed. An immutable record alone does not make every multithreaded business operation safe.

## 9. Method for Tracing the Effects of State Changes

When debugging “I only changed A, but B changed too,” record these four columns:

| Step | Who acts? | Which instance does the reference point to? | Observable state |
|---|---|---|---|
| T0 | `main` creates `shared` | `wall.policy → Policy #1` | target = 22 |
| T1 | `mobile.changeTarget(24)` | `mobile.policy → Policy #1` | target = 24 |
| T2 | `wall.render()` | `wall.policy → Policy #1` | displays 24 |
| T3 | `mobile` is reassigned to another controller | new controller → Policy #2 | Policy #1 remains 24 |
| T4 | new controller changes Policy #2 | new controller → Policy #2 | #2 = 19; #1 = 24 |

Then check in order: (1) which statement actually creates a `new` instance, (2) which merely copies/reassigns references, (3) which method changes state, (4) who holds snapshot data, and (5) whether synchronization is missing when multiple threads are involved.

In a debugger, set breakpoints at `TemperaturePolicy.setTarget` and `WallDisplay.render`; inspect the called object's **identity**, call stack, and fields before/after. Logs should include business entity names or correlation IDs as appropriate, not rely on `identityHashCode` as a unique identifier.

## 10. Exercises and Answers

**Exercise 1 — Effects Across Components:** Two `WallDisplay` instances receive the same `TemperaturePolicy`. A `MobileControl` changes the target from 20 to 25. What do both displays show when they call `render()` again?

**Answer:** Both display 25°C if they still reference the modified instance and apply no other transformation. Previously cached rendered text does not change automatically.

**Exercise 2 — Does a Snapshot Update Automatically?** `List<String> history = policy.getHistorySnapshot();` is called when history is empty. A policy change is then recorded. What is `history.size()`?

**Answer:** 0. The resulting list is a structural snapshot taken at that moment, not a view of elements added later to the source list.

**Exercise 3 — Replacing a Map Entry:** `WallDisplay` already holds `Policy #1`; the `registry` map replaces that key's value with `Policy #2`. The `WallDisplay` field is not changed. Which object does the display read?

**Answer:** Still `Policy #1`. The map and the display hold **independent reference variables**; reassigning a map entry does not automatically change the display's field.

**Exercise 4 — Designing a Contract:** A service wants displays to see the latest configuration without being allowed to modify it arbitrarily. What API should it provide?

**Hint:** Provide a service/holder that owns mutation, a query API returning current state or immutable snapshots, and a suitable notification mechanism to trigger refreshes. Do not expose mutable references to every caller. In multithreaded environments, control state visibility and atomicity.

**Exercise 5 — Concurrency:** Why is `volatile int count` insufficient to make `count++` atomic?

**Answer:** `volatile` supports visibility for field reads/writes, but `count++` consists of separate read, addition, and write operations that threads can interleave. Use atomic increments or locking when safe incrementing is required.

## Remember

**Object sharing** occurs when multiple components have reference paths to the same instance. If it is mutable, changes made through one path may be observed through another on the next read. To manage these effects deliberately, define **state ownership**, whether contracts expose live references or snapshots, when interfaces refresh, and how threads synchronize their work.
