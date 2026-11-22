# Why ArrayDeque Does Not Accept null

## 1. This Is the Class Contract, Not a Java Array Limitation

`ArrayDeque` is a resizable-array implementation of `Deque`. You can add and remove elements at both ends, using it as a queue or as a stack.

However, there is one explicit rule: **you must not store `null` as an element**. Calling an insertion method with `null` results in a `NullPointerException`, even when the method is named `offer`.

This does not mean reference arrays in Java cannot hold `null`. An `Object` array can contain `null`. This is a design choice of `ArrayDeque`, which preserves the meaning of the return value indicating no element is present and fits how the class organizes its storage slots.

There are two layers of explanation to distinguish:

- At the API level, `null` is used as the result signaling that there is no element to inspect or remove.
- In the OpenJDK 17 implementation, array slots that do not hold a deque member are also kept as `null`.

Users of the class must follow the public contract. Array details help explain the mechanism, but they are not a reason for a program to directly access internal private fields.

This lesson uses Java 17 examples to verify the insertion paths, batch addition cases, and ways to represent a message whose internal data is absent. You only need to know reference variables, methods, and generic collections; easily confused cases will be clearly separated.

## 2. The Word “null” Can Refer to Different Things

Consider the following expressions:

| Case | Meaning |
| --- | --- |
| `Deque<String> q = null` | There is no deque object yet to call methods on |
| `q.addLast(null)` | Attempting to add a `null` reference as a member |
| `q.pollFirst() == null` | On a valid `ArrayDeque`, the operation retrieved no element |
| `new Message(null)` | A `Message` object exists, but an internal field is `null` |
| `"null"` | A string object containing the four characters n, u, l, l |
| `""` | A string object of length 0 |

`ArrayDeque` forbids the case where **the element itself is `null`**. It does not automatically forbid every object that has a `null` field, nor does it forbid empty strings or strings containing the text “null”.

If the variable `q` itself is `null`, the error when calling `q.addLast` is different from having a real `ArrayDeque` reject a `null` element. The same exception name `NullPointerException` is not enough to conclude where the bug is; you must check which reference is absent or which precondition is being checked.

The type `Deque<String>` in Java 17 does not express the constraint “element reference must be non-null” at the compiler level. The implementation checks its condition when receiving data. Therefore, a call can compile and still be rejected at runtime.

## 3. API-Level Reason: Keeping null as the Signal for No Element

`ArrayDeque` provides the operations:

~~~text
peekFirst / peekLast : inspect one end without removing
pollFirst / pollLast : retrieve and remove from one end
~~~

When empty, they return `null`. When non-empty, they return an actual element stored at the corresponding end.

Because `ArrayDeque` has no `null` members, the two states are clearly distinguished:

~~~text
non-null result → an element was received
null result     → no element was present for that peek/poll
~~~

With a structure that allows storing `null`, a `null` result can have two meanings: “there is no member” or “there is a member, and its value is `null`”. If the API only returns a single reference, the caller cannot distinguish between the two from that value alone.

A counterexample using `LinkedList`, a class that allows `null`:

~~~text
initial contents : [null, next]
pollFirst()      : null
remaining        : [next]
~~~

The `null` just returned is data that was retrieved, not proof that the deque was initially empty. `ArrayDeque` eliminates this ambiguity by rejecting `null` data from the start.

`Deque` in general does not force every implementation to forbid `null`, but strongly recommends avoiding `null` because of its empty-signal role. `ArrayDeque` chooses a specific and explicit prohibition policy. [Java 17: Deque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html).

## 4. Implementation-Level Reason: Empty Slots and Members Have Different Meanings

OpenJDK 17 uses a circular array to store references. Slots that do not belong to members are kept as `null`; head points to the next position to take from, and tail points to the next position to insert into. When an element is removed, the old slot is cleared to `null`. [ArrayDeque source code, OpenJDK 17](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/ArrayDeque.java).

The illustration below uses eight hypothetical slots:

~~~text
index:        0      1      2      3      4      5      6      7
array slots: [C]  [null] [null] [null] [null] [null]  [A]    [B]

head = 6: position of A
tail = 1: empty slot for the next insertion
member order: slot 6 (A) → slot 7 (B) → slot 0 (C)
~~~

The logical path in the diagram wraps past the end of the array back to slot 0. The `null` slots are not elements to be traversed. The number eight is only for illustration, not the default capacity.

The rule against storing `null` elements allows reading a slot at the head to distinguish whether an element is present. If `null` were allowed as data while keeping that same check, a valid value would be confused with an empty slot.

Another array-based structure could support `null` by tracking presence through a different mechanism. Therefore, do not infer that “a circular array theoretically cannot store `null`”. The point here is the alignment between `ArrayDeque`'s contract and its representation.

## 5. poll and get Can Share the Meaning of a Non-Element Slot

In `ArrayDeque`'s model, when there is a real reference at the head, `pollFirst` retrieves it, clears the reference from the old slot, and advances head. When there is no element, the result is `null`.

`getFirst` is the form that requires an element to exist: if none is present, it throws `NoSuchElementException`; if present, it returns the element without removing it.

Thanks to the `null` prohibition, an empty result is not confused with a valid member. However, the caller must still choose the right effect:

| Method | When an element is present | When empty |
| --- | --- | --- |
| `peekFirst()` | Returns the element, leaves the deque unchanged | `null` |
| `pollFirst()` | Returns the element and removes it | `null` |
| `getFirst()` | Returns the element, leaves the deque unchanged | `NoSuchElementException` |
| `removeFirst()` | Returns the element and removes it | `NoSuchElementException` |

The `Last` side has similar pairs for the tail end. Shorter `Queue` names such as `peek` and `poll` operate at the front end of the deque.

Forbidding `null` does not turn every operation into a removal. `peek` still only inspects; you cannot use seeing an element as proof that it has been processed or has left the structure.

## 6. Clearing the Old Reference Is Not a Guarantee of Immediate Garbage Collection

When an element is removed, setting the old slot to `null` also drops the deque's reference to that object. An array region that no longer holds a member should not continue holding onto an object just because the old value remains in the slot.

That does not mean the object is garbage-collected immediately after `poll`. If another variable or another structure still references it, the object can still be used. The exact timing of garbage collection is also not guaranteed by a `poll` call.

In the verification program, we only observe the membership contract and method results. We do not invoke the garbage collector to try to prove when an object disappears, and we do not use reflection to read the class's private array.

Separate “the deque has dropped its reference” from “there are no references left anywhere in the program”. These two conclusions are not equivalent.

## 7. Which Insertion Paths Reject null?

For `ArrayDeque`, the policy applies to all direct insertion methods:

| Call | Meaning with a valid element | When the element is `null` |
| --- | --- | --- |
| `add(e)` | Add at the tail | `NullPointerException` |
| `offer(e)` | Add at the tail | `NullPointerException` |
| `addFirst(e)` | Add at the head | `NullPointerException` |
| `addLast(e)` | Add at the tail | `NullPointerException` |
| `offerFirst(e)` | Add at the head | `NullPointerException` |
| `offerLast(e)` | Add at the tail | `NullPointerException` |
| `push(e)` | Push onto the head when used as a stack | `NullPointerException` |

There is no workaround like “use `push` instead of `add`” to get `null` in. Changing the method name does not change the element contract.

`offer` is the form that can return `false` to indicate an insertion failed due to capacity limits in bounded structures. It does not turn a forbidden input reference into a `false` result.

`ArrayDeque` grows its capacity automatically as needed according to the class contract and does not impose a fixed maximum capacity via the initial size argument. Rejecting `null` is a data issue, not evidence that the deque is full. [Java 17: ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

If you change the variable type from `ArrayDeque` to `Deque` or `Queue` while still using the same `ArrayDeque` object, the policy does not change either. The interface type does not disable the checks of the actual object.

## 8. Constructors and addAll Must Also Follow the Policy

It is not only single-element insertion calls that can receive invalid data. A source `Collection` can contain `null` and then be passed to a constructor or `addAll`.

Example of a source that is valid for `Arrays.asList` but invalid as `ArrayDeque` members:

~~~java
List<String> input = Arrays.asList("before", null, "after");
~~~

This snippet requires importing `java.util.List` and `java.util.Arrays`. `Arrays.asList` allows `null` elements, so it can be used to test the deque itself receiving the data.

If you create `new ArrayDeque<>(input)`, construction does not complete normally and the calling code receives a `NullPointerException`. You do not get a successfully constructed deque containing a `null` member.

If you already have a deque and call `addAll`, there is an additional point to note: **an exception does not mean all earlier changes made by the call were rolled back**.

In the OpenJDK example verified in the program:

~~~text
deque before: [stable]
source:       [before, null, after]

addAll throws NullPointerException

deque after:  [stable, before]
~~~

`before` was added; `null` was rejected; `after` was not added. No `null` member bypassed the policy, but the deque was partially modified.

The bulk addition contract of `Deque` notes the possibility that only part of the data is added before an error occurs. Do not treat `addAll` as an atomic transaction just because it is a single method call. [Java 17: Deque.addAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html#addAll(java.util.Collection)).

## 9. Validating a Batch Before Modifying the Deque

If a function's contract is “reject a batch containing `null` before adding any element of the batch”, you can do this in two phases:

1. Snapshot the source into a separate list and check the element references.
2. Only add the validated list to the target when all checks succeed.

Function in the program:

~~~java
static <E> void appendValidated(
        ArrayDeque<E> target, Collection<? extends E> input) {
    List<E> snapshot = new ArrayList<>(input);
    for (E element : snapshot) {
        Objects.requireNonNull(element, "Phan tu cua lo khong duoc null");
    }
    target.addAll(snapshot);
}
~~~

This is an excerpt from the complete code. The snapshot list holds the same element references without deep-cloning each object.

When the batch contains `null`, the error occurs during the validation phase before the function calls `addAll` on `target`. In the example, `target` remains `[stable]`. When the batch is clean, containing `first` and `second`, the result is `[stable, first, second]`.

The scope of the guarantee should be stated accurately: the function avoids modifying `target` due to **detecting `null` in the batch during the validation step** under the example's usage conditions. It is not a transactional mechanism for every resource error or concurrent operation.

The chosen target type is `ArrayDeque`, not an arbitrary `Deque` that might fill up mid-batch due to a fixed capacity limit. Do not automatically extend this conclusion to implementations with different element-acceptance conditions.

Filtering out `null` is a different policy from rejecting it. Only skip `null` when the domain data permits it; do not silently drop a missing message and then report that the entire batch was accepted intact.

## 10. Complete Program Using Java 17

Save as `ArrayDequeNullDemo.java`. The program tests insertion paths, `null` lookup/removal, `Collection` sources with `null`, batch additions, empty signals, and two ways of wrapping internal data that may be absent.

The `checkNullInput` method only serves the test cases. Its `Runnable` parameter holds a call, and `() -> ...` creates the operation for the method to execute. Each test knows the deque receiving the call is a real object, so the error being tested is the policy on `null` input.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Optional;

public class ArrayDequeNullDemo {
    record Message(String payload) {}

    static void checkNullInput(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + "=accepted");
        } catch (NullPointerException exception) {
            System.out.println(label + "=" + exception.getClass().getSimpleName());
        }
    }

    static <E> void appendValidated(
            ArrayDeque<E> target, Collection<? extends E> input) {
        List<E> snapshot = new ArrayList<>(input);
        for (E element : snapshot) {
            Objects.requireNonNull(element, "Phan tu cua lo khong duoc null");
        }
        target.addAll(snapshot);
    }

    public static void main(String[] args) {
        ArrayDeque<String> direct = new ArrayDeque<>();
        direct.addLast("stable");
        checkNullInput("add", () -> direct.add(null));
        checkNullInput("offer", () -> direct.offer(null));
        checkNullInput("addFirst", () -> direct.addFirst(null));
        checkNullInput("addLast", () -> direct.addLast(null));
        checkNullInput("offerFirst", () -> direct.offerFirst(null));
        checkNullInput("offerLast", () -> direct.offerLast(null));
        checkNullInput("push", () -> direct.push(null));
        System.out.println("after direct attempts=" + direct);
        System.out.println("contains(null)=" + direct.contains(null));
        System.out.println("remove(null)=" + direct.remove(null));
        System.out.println("after null search=" + direct);

        checkNullInput("constructor", () ->
                new ArrayDeque<>(Arrays.asList("before", null, "after")));
        checkNullInput("List.of source", () ->
                List.of("before", null, "after"));

        ArrayDeque<String> bulk = new ArrayDeque<>();
        bulk.addLast("stable");
        List<String> badBatch = Arrays.asList("before", null, "after");
        checkNullInput("addAll", () -> bulk.addAll(badBatch));
        System.out.println("after failing addAll=" + bulk);

        ArrayDeque<String> checked = new ArrayDeque<>();
        checked.addLast("stable");
        checkNullInput("validated batch", () -> appendValidated(checked, badBatch));
        System.out.println("after validation rejection=" + checked);
        appendValidated(checked, List.of("first", "second"));
        System.out.println("after valid batch=" + checked);

        Deque<String> signals = new ArrayDeque<>();
        signals.addLast("A");
        System.out.println("nonempty peek=" + signals.peekFirst());
        System.out.println("size after peek=" + signals.size());
        System.out.println("nonempty poll=" + signals.pollFirst());
        System.out.println("empty peek=" + signals.peekFirst());
        System.out.println("empty poll=" + signals.pollFirst());
        try {
            signals.getFirst();
        } catch (NoSuchElementException exception) {
            System.out.println("empty getFirst=" + exception.getClass().getSimpleName());
        }

        Deque<String> nullable = new LinkedList<>();
        nullable.addLast(null);
        nullable.addLast("next");
        System.out.println("linked first poll=" + nullable.pollFirst());
        System.out.println("linked empty after null=" + nullable.isEmpty());
        System.out.println("linked next poll=" + nullable.pollFirst());

        Deque<Message> messages = new ArrayDeque<>();
        messages.addLast(new Message(null));
        messages.addLast(new Message("hello"));
        Message first = messages.pollFirst();
        System.out.println("message reference present=" + (first != null));
        System.out.println("message payload absent=" + (first.payload() == null));
        System.out.println("second payload=" + messages.pollFirst().payload());
        System.out.println("no message=" + messages.pollFirst());

        Deque<Optional<String>> options = new ArrayDeque<>();
        options.addLast(Optional.empty());
        options.addLast(Optional.of("data"));
        Optional<String> wrapper = options.pollFirst();
        System.out.println("optional wrapper present=" + (wrapper != null));
        System.out.println("optional payload present=" + wrapper.isPresent());
        System.out.println("next optional=" + options.pollFirst());
        System.out.println("no optional element=" + options.pollFirst());

        Deque<String> text = new ArrayDeque<>();
        text.addLast("");
        text.addLast("null");
        System.out.println("empty string length=" + text.pollFirst().length());
        String literal = text.pollFirst();
        System.out.println("literal value='" + literal + "'");
        System.out.println("literal is null=" + (literal == null));
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 ArrayDequeNullDemo.java
java ArrayDequeNullDemo
~~~

Use JDK 17 or higher. `--release 17` checks the code and API against Java 17. The filename must match the public class.

Expected output:

~~~text
add=NullPointerException
offer=NullPointerException
addFirst=NullPointerException
addLast=NullPointerException
offerFirst=NullPointerException
offerLast=NullPointerException
push=NullPointerException
after direct attempts=[stable]
contains(null)=false
remove(null)=false
after null search=[stable]
constructor=NullPointerException
List.of source=NullPointerException
addAll=NullPointerException
after failing addAll=[stable, before]
validated batch=NullPointerException
after validation rejection=[stable]
after valid batch=[stable, first, second]
nonempty peek=A
size after peek=1
nonempty poll=A
empty peek=null
empty poll=null
empty getFirst=NoSuchElementException
linked first poll=null
linked empty after null=false
linked next poll=next
message reference present=true
message payload absent=true
second payload=hello
no message=null
optional wrapper present=true
optional payload present=false
next optional=Optional[data]
no optional element=null
empty string length=0
literal value='null'
literal is null=false
~~~

## 11. Reading the Output Boundary by Boundary

### 11.1. No Successful null Insertion Path

The first seven lines are all `NullPointerException`. After them, `after direct attempts=[stable]` shows that the existing element is preserved and no new member came from the `null` insertion calls.

`offer` also throws an exception rather than returning `false`. `push` does not create an exception to the policy just because the deque is being used as a stack.

### 11.2. Searching for null Is Different from Inserting null

`contains(null)=false` and `remove(null)=false` show that the two value-based lookup/removal calls did not find a `null` member in the example's `ArrayDeque`. The contents remain `[stable]`.

Do not generalize “`ArrayDeque` does not accept `null` as an element” into “any method with a `null` argument must throw `NullPointerException`”. The policy for each parameter must still be read from the method's contract. Insertion operations and presence-query operations are not the same thing.

### 11.3. Batch Addition Can Change State Before Throwing

`after failing addAll=[stable, before]` clearly contrasts the part added before the error. If code catches the exception and retries the entire batch, it can add another copy of `before`. `ArrayDeque` allows equal elements to appear multiple times, so there is no automatic deduplication to compensate for a flawed retry policy.

`after validation rejection=[stable]` shows that pre-validation changes when the error is detected: `target` has not received any element from the batch.

### 11.4. Two Different Sources of NullPointerException

`constructor=NullPointerException` tests `ArrayDeque` receiving a source that allows `null`.

`List.of source=NullPointerException` tests a different step: `List.of` already rejected `null` when creating the source. At that point, no call to insert that data into the deque had occurred yet.

Therefore, when writing examples or tests, know whether the error happens at the source or at the receiver. Creating `List.of("before", null, "after")` and using it to “prove `addAll` rejects `null`” misattributes responsibility to a method that was never executed.

## 12. No Element vs. a Message Missing Data Are Two Different States

Suppose a message can exist without having a payload yet. You do not need to turn the deque element itself into `null` to express that.

The program defines:

~~~java
record Message(String payload) {}
~~~

`new Message(null)` is a real `Message` reference. It is non-null and is accepted by `ArrayDeque`. Only the internal `payload` field has no value.

Output:

~~~text
message reference present=true
message payload absent=true
~~~

These two lines answer two separate questions:

- Was a message retrieved?
- Does that message have a payload?

When no `Message` remains, `pollFirst` returns `null` at the message-reference level. Once a `Message` has been received, the code then inspects the meaning of its internal field according to `Message`'s contract.

`ArrayDeque` does not deeply validate every field of an object. If business rules require `payload` to be present, enforce that condition in the domain model or at the message receiver. The deque accepting an object does not prove the object satisfies all business rules.

The wrapper pattern separates the presence of an element from the presence of the data contained within it. It is not a way to bypass the policy to store a `null` member: the stored member is a non-null `Message`.

## 13. Optional.empty Is Also a Non-null Object

Another illustrative option is `Deque<Optional<String>>`:

~~~text
no element in the deque               → poll returns null
Optional.empty in the deque          → poll returns a non-null Optional with no inner value
Optional containing "data" in deque  → poll returns Optional[data]
~~~

The program receives:

~~~text
optional wrapper present=true
optional payload present=false
~~~

This does not conflict with the `null`-prohibition policy. `Optional.empty` is a valid `Optional` value; it is not a `null` reference.

Conversely, `options.addLast(null)` is still rejected, even though the element type is `Optional`. Wrapping with a generic type does not make an outer-level `null` reference valid.

`Optional` has an API describing the presence or absence of an inner value. When modeling a real message, a domain type like `Message` can express field names and the meaning of absence more clearly. You do not need to wrap every element just to avoid writing input checks; choose the model based on what the data means. [Java 17: Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html).

Do not rely on reference identity of `Optional.empty` instances for business rules. In the example, we only use the non-nullness of the element and `isPresent` of the wrapped value.

## 14. Empty Strings and the String “null” Are Still Real Data

The program adds `""` and `"null"` in turn to `ArrayDeque` and then retrieves them.

Output:

~~~text
empty string length=0
literal value='null'
literal is null=false
~~~

An empty string has a real reference but zero characters. The string `"null"` has four characters. Both are non-null at the reference level, so `ArrayDeque` accepts them.

Do not use display formatting as proof of reference identity. A string that prints the text `null` and a `null` reference can be confused if you only look at a line of text without context. The program places quotes around the string and checks `literal == null` to distinguish them.

Similarly, the number `0` or an object named `"EMPTY"` can still be valid data if the model allows it. If you want to use an object as an application-specific sentinel, you must define its type and policy explicitly; the deque does not automatically know that its name or content is special.

If you replace a failing `null` value with the string `"null"` just to make insertion succeed, you have changed the data, not just fixed how it is stored. That is only valid when the input contract genuinely intends such a string.

## 15. Do Not Infer a Universal Collection Policy from ArrayDeque

Some structures such as `ArrayList` or `LinkedList` can accept `null`. `ArrayDeque` cannot. The fact that classes all hold object references does not force them to share the same element contract.

When transferring data from a `null`-allowing source to a `null`-forbidding target, you must choose an explicit policy:

| Policy | Meaning |
| --- | --- |
| Reject the batch | Preserve the requirement that every member must have a real reference |
| Skip `null` | Accept losing those data positions because the domain allows it |
| Use a non-null message type with an optional field | Preserve message presence while separately representing absent internal data |
| Fix the data at the source | Perform a meaningful, predefined transformation |

Do not simply swap the class for a `null`-allowing structure to make the exception disappear and then keep using `poll`-until-`null` loops as before. Once `null` data is allowed in, the interpretation of the return value has changed.

Likewise, do not treat `Arrays.asList` allowing `null` as proof that every `Collection` receiving that batch must accept it. Each receiver has the right to enforce its own element contract; the transfer step is a boundary that must be checked.

In the program, `LinkedList` is only used as a counterexample to illustrate the ambiguity in `null` results. The remaining operations use `ArrayDeque` to maintain a consistent no-`null`-members policy.

## 16. Limits of Reasoning from null and Array Details

For a validly used `ArrayDeque`, a `null` result from a `poll`/`peek` call indicates there is no element to return for that operation. It does not mean no element will be added later.

A non-null `peek` does not reserve the element for the caller that just inspected it either. If a modifying operation intervenes between `peek` and `poll`, the two calls can observe different states.

`ArrayDeque` is not synchronized for arbitrary concurrent modification by multiple threads. The empty-slot rules in the implementation are not a coordination mechanism between threads. You cannot rely on “already checked non-null” to replace a proper data-sharing contract.

The circular array details in the explanation are matched against OpenJDK 17. Slot indices, array size, and resizing behavior are not APIs for application code to depend on. The examples only use public methods to verify outcomes that users of the class are allowed to rely on.

If you need to diagnose a `NullPointerException`, first determine whether the error comes from a `null` deque variable, inserting a `null` element, retrieving from an empty deque and using the result unchecked, or an internal field of an object. Do not lump those causes together into a single claim like “`ArrayDeque` null bug”.

## 17. Common Misconceptions

| Misconception | What to understand correctly |
| --- | --- |
| “Java arrays cannot hold `null`” | Reference arrays can; `ArrayDeque` forbids `null` as a member by contract |
| “`offer` uses `false`, so `offer(null)` does not throw” | Forbidden `null` data still leads to `NullPointerException` |
| “Using `push` can put `null` onto the stack” | `push` still follows the policy of the same `ArrayDeque` |
| “Changing the variable to `Deque` disables the check” | The actual object is still `ArrayDeque` |
| “Having `null` in array slots means the deque contains `null`” | A slot not holding a member is different from a valid element |
| “`poll` clears the slot so the object is collected immediately” | It drops one reference; other references and GC timing still matter |
| “If `addAll` throws, the target is guaranteed unchanged” | Part of the batch may have been added before encountering `null` |
| “`List.of` with `null` is a good source to test the deque” | `List.of` can fail before the deque is ever called |
| “`ArrayDeque` will validate all internal fields” | It checks the element reference, not every rule of the domain type |
| “`Optional.empty` is `null`” | It is a non-null `Optional` containing no inner value |
| “A string with the text `null` is a `null` reference” | A string is a real object with character content |
| “Some collections accept `null`, so `ArrayDeque` must too” | The receiving class's policy must be read separately |
| “Replacing `null` with an empty string does not change the data” | That is a semantic transformation and needs an explicit contract |

A useful habit is to distinguish three levels: the container object, the element reference, and the data inside the element. Many bugs appear simply because those three levels are all referred to by the single word “null”.

## 18. Practice with Solutions

### Exercise 1: `offer(null)` when there is plenty of space

A newly created `ArrayDeque` is empty. Does `offerLast(null)` return `false` because it could not be added?

**Solution:** No. `null` is a forbidden element, so the call throws `NullPointerException`. Capacity state does not turn forbidden data into a valid value.

### Exercise 2: Same object, different variable type

You hold an `ArrayDeque` through a `Deque<String>` variable and call `push(null)`. Does the policy change?

**Solution:** No. The actual object is still `ArrayDeque` and `push` is an insertion path into it. `null` is still rejected.

### Exercise 3: Empty slots in the array

An internal array diagram has many `null` slots, while the deque's `size` is 3. Is the deque holding `null` members?

**Solution:** No. Slots that do not hold members can contain `null` to represent empty slots. `size` and member order are not identical to the entire physical array length.

### Exercise 4: Reading `poll` results

A valid `ArrayDeque<String>` currently contains one `"A"`. What do two consecutive `pollFirst` calls return?

**Solution:** The first returns `"A"` and removes it. The second returns `null` because no members remain. With this class, there is no real `null` element to cause ambiguity.

### Exercise 5: Batch addition failing mid-way

The deque before is `[stable]`, and the `Arrays.asList` batch is `before, null, after`. Can a `NullPointerException` from `addAll` be taken as proof that `stable` is the only member afterward?

**Solution:** No. The example in the program retains `[stable, before]` after the error. The beginning of the batch may already have been added, while `null` was not stored. To reject a batch before modifying the target, pre-validation according to an appropriate contract is needed.

### Exercise 6: A test that fails in the wrong place

You create a `List.of` containing `null` intending to pass it to `ArrayDeque`. An exception occurs. Can you conclude that the `ArrayDeque` constructor ran and rejected the source?

**Solution:** Not if the error occurred when creating `List.of`. You need a source that actually allows `null`, such as `Arrays.asList`, to reach the step where the deque receives the data.

### Exercise 7: Object with a `null` field

Can you add `new Message(null)` to an `ArrayDeque<Message>`?

**Solution:** Yes, under `ArrayDeque`'s element-reference policy, because the `Message` object is non-null. If the domain model requires `payload` to be present, that condition must be checked separately.

### Exercise 8: `Optional.empty`

An `ArrayDeque<Optional<String>>` has an `Optional.empty` member. What object does `pollFirst` return? How does that differ from an empty deque?

**Solution:** It returns a non-null `Optional` with no inner value. When the deque is empty, `pollFirst` returns `null` at the element-reference level.

### Exercise 9: Is searching for `null` the same as inserting `null`?

An `ArrayDeque` currently contains `stable`. What do `contains(null)` and `remove(null)` do in the program?

**Solution:** They return `false` and do not modify the contents. These are value-based lookup/removal calls, not attempts to insert a `null` member. Do not infer the behavior of every `null` parameter solely from the insertion rule.

### Exercise 10: The string `"null"`

You add the string `"null"` and then check the retrieved element with `== null`. What is the result?

**Solution:** `false`. There is a `String` object containing four characters. An empty string is also a real reference and is accepted, even though its length is 0.

### Exercise 11: Removal and garbage collection

After `pollFirst`, the deque no longer holds member `X`. An external variable still points to `X`. Can we say `X` has been garbage-collected immediately?

**Solution:** No. The deque has dropped its reference, but the external variable still holds the object. The API does not guarantee garbage-collection timing.

### Exercise 12: Filter or reject?

A source contains `null`, but each position represents a job that must be recorded. Should you silently drop every `null` and report that the full batch was accepted?

**Solution:** Not if doing so loses the meaning of the data. You need to reject it or use an explicit message model according to the contract. Skipping is a policy that can alter the count and meaning of members, not a transparent bug fix.

## 19. Applying This in Real Code

At the boundary where data enters an `ArrayDeque`, check the element reference and define a policy if the source can contain `null`. For batches, explicitly decide whether partial addition before an error is acceptable or whether pre-validation is required.

If you need to represent “a message exists, but its content is not present yet”, keep a non-null element object and describe the internal absence with an appropriate data type.

When reading from the deque, use `null` strictly for its meaning of no element present, and distinguish peek operations from removal operations. Clarity at both the insertion and reading boundaries is a direct benefit of `ArrayDeque`'s no-`null` contract.
