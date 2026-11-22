# `NoSuchElementException` and Accessing When No Element Exists in Java

In Java, `java.util.NoSuchElementException` is an **unchecked exception** used to indicate that an operation **requests an element, but there are no suitable elements left to return**. It commonly occurs when calling `Iterator.next()` past the last element, `Scanner.next()` when no tokens remain, `Optional.get()` when the `Optional` is empty, or `Queue.remove()` on an empty queue.

The key point is not that every empty collection automatically throws `NoSuchElementException`. **Only a call to an API with a "throw if absent" element retrieval contract throws this exception**, and each API has corresponding safe alternatives: `hasNext()`, `hasNextLine()`, `poll()`, `peek()`, `isPresent()`, `orElseThrow(...)`, or another result type.

This lesson clarifies **when `NoSuchElementException` occurs, how to check for it, when to handle it, why "already checked" can still fail in a program with state changes, and how to choose an API with the right contract**. Complete programs use Java 17+ with explicitly documented output; non-standalone illustrative snippets are labeled separately.

## 1. Definition, Hierarchy, and Meaning

`NoSuchElementException` is in `java.util` and has the following hierarchy:

```text
java.lang.Object
  └── java.lang.Throwable
       └── java.lang.Exception
            └── java.lang.RuntimeException
                 └── java.util.NoSuchElementException
```

This means:

- It is **not a checked exception**. The compiler does not force the caller to `catch` it or declare `throws`.
- It is still a real exception that can be `throw`n and `catch`ed, carrying a message and stack trace like normal `Throwable` types.
- If there is no handler, it propagates up the call stack and can cause the running execution path to terminate abnormally.
- This class describes a **call that requires an element, but the requested element does not exist according to the API contract**. It does not by itself mean "the entire application is broken" or "data is lost".
- `NoSuchElementException` is not a subclass of `IllegalArgumentException`, `IllegalStateException`, or `IndexOutOfBoundsException`; those belong to different unchecked branches.

You need to import:

```java
import java.util.NoSuchElementException;
```

If using multiple classes in `java.util`, you can import each specific class. Most programs do not need to `new NoSuchElementException` themselves: the JDK library throws it when an access call exceeds the allowed condition.

## 2. Distinguishing "No Element" from Other Failures

Some situations look similar but belong to different contracts:

| Situation | Example API | Typical Outcome |
| --- | --- | --- |
| Iterator is exhausted, yet next is called | `Iterator.next()` | `NoSuchElementException` |
| Scanner has no tokens left | `Scanner.next()` | `NoSuchElementException` |
| Scanner has no lines left | `Scanner.nextLine()` | `NoSuchElementException` |
| `Optional` is empty, yet `get()` is called | `Optional.get()` | `NoSuchElementException` |
| Queue is empty, yet `remove()` or `element()` is called | `Queue` | `NoSuchElementException` |
| Queue is empty and `poll()` or `peek()` is called | `Queue` | Returns `null` per contract, does not throw for emptiness |
| Array/list index is out of bounds | `List.get(index)` | `IndexOutOfBoundsException` |
| Object reference is `null` and dereferenced | `obj.method()` | `NullPointerException` |
| Scanner is closed and used again | `Scanner.next()` | `IllegalStateException` |
| Scanner has a token, but it does not match the requested type | `Scanner.nextInt()` | `InputMismatchException` |
| `Iterator.remove()` is called in the wrong sequence | Many iterators supporting remove | `IllegalStateException` |
| Collection is structurally modified improperly during iteration | Many fail-fast iterators | Possible `ConcurrentModificationException` |

**Do not use a single `catch (RuntimeException)` to treat all these situations as "out of data".** They have very different causes and fixes. Accurate reasoning always starts from the **contract of the method being called**, not just the collection name.

## 3. Two API Families: Mandatory Retrieval and Empty-Signaling Retrieval

Many APIs provide both styles:

**Mandatory element style**:

```java
E value = iterator.next();  // Throws if exhausted.
E head  = queue.remove();   // Throws if queue is empty.
```

This is an **illustrative skeleton** in a context where `iterator` and `queue` are declared.

**Possibly absent element style**:

```java
if (iterator.hasNext()) {
    E value = iterator.next();
}

E head = queue.poll();  // Returns null when queue is empty.
```

This is also an **illustrative skeleton**, without a full `E` class or variable declarations. The important point is that choosing the API changes the contract between the caller and the method:

- With `next()` or `remove()`, the caller says: "I expect the element to exist; if not, it is an error for this operation."
- With `hasNext()` or `poll()`, the caller says: "Having no element is a possible outcome, and I will actively handle it."

Neither style is always better. **If the element is a required invariant, throwing an error may be right; if running out of data is a common branch, checking or returning an empty result is usually clearer.**

## 4. `Iterator.next()`: The Most Classic Example

`Iterator<E>` has two commonly used methods:

- `boolean hasNext()`: are there more elements to iterate over?
- `E next()`: returns the next element; throws `NoSuchElementException` if no elements remain.

Save the program **`IteratorExhaustionDemo.java`**:

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;

public class IteratorExhaustionDemo {
    public static void main(String[] args) {
        List<String> names = Arrays.asList("An", "Bình");
        Iterator<String> iterator = names.iterator();

        System.out.println(iterator.next());
        System.out.println(iterator.next());
        System.out.println("Còn phần tử: " + iterator.hasNext());

        try {
            iterator.next();
            System.out.println("Không đến dòng này");
        } catch (NoSuchElementException e) {
            System.out.println("Đã hết phần tử");
        }
        System.out.println("Kết thúc");
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 IteratorExhaustionDemo.java
java IteratorExhaustionDemo
```

**Exact stdout**:

```text
An
Bình
Còn phần tử: false
Đã hết phần tử
Kết thúc
```

After two successful `next()` calls, the iteration position reaches the end of the list. `hasNext()` returns `false`; the third `next()` call violates the contract and throws `NoSuchElementException`.

The error does not occur when **creating the iterator**, nor does it happen automatically when **`hasNext()` returns `false`**; it occurs at **the call requesting the next element when no such element exists**.

## 5. How to Safely Iterate with `Iterator`

Standard pattern:

```java
while (iterator.hasNext()) {
    E item = iterator.next();
    process(item);
}
```

This is **illustrative code**, where `E` and `process` represent the appropriate type and processing logic. It expresses the contract: **only call `next()` when the condition that an element remains is confirmed in the normal iteration flow**.

Java 17 example **`SafeIteratorDemo.java`**:

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;

public class SafeIteratorDemo {
    public static void main(String[] args) {
        List<Integer> numbers = Arrays.asList(2, 4, 6);
        Iterator<Integer> it = numbers.iterator();
        int sum = 0;

        while (it.hasNext()) {
            sum += it.next();
        }

        System.out.println("Tổng: " + sum);
        System.out.println("Đã hết: " + !it.hasNext());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 SafeIteratorDemo.java
java SafeIteratorDemo
```

**Exact stdout**:

```text
Tổng: 12
Đã hết: true
```

Advantages of this pattern:

- Running out of data is the **loop termination condition**, not an exception used to control a normal loop.
- No need to catch `NoSuchElementException` on every iteration.
- Readers can easily see the stopping condition.
- You can accumulate, filter, and process elements without guessing the initial number of elements.

**Limitation:** the `hasNext()` check and `next()` call only form a reliable pattern when the iterator/source is used according to its contract and is not invalidly modified in between. It is not a thread-safety guarantee for every iterator.

## 6. The Enhanced `for` Loop and When to Use It

For a standard `Iterable` object, the enhanced `for` loop uses the iterator mechanism under the hood:

```java
for (String name : names) {
    System.out.println(name);
}
```

This is **illustrative code** with `names` as an `Iterable<String>`. This syntax reduces the chance of misordering `hasNext()/next()` manually and is suitable when you only need to traverse elements sequentially.

However:

1. Enhanced `for` does not change the nature of the iterator; if the iterator is implemented incorrectly, it can still fail at runtime.
2. With fail-fast collections, modifying the collection's structure directly while iterating can throw `ConcurrentModificationException`.
3. If you need to remove via an iterator, the `Iterator.remove()` API (when supported) has its own rules; do not replace it by arbitrarily calling `collection.remove(...)` inside the `for` loop.
4. For lazily loaded data sources or I/O-related iterators, you must consider exceptions, performance, and resource lifecycles according to the specific API.

**Enhanced `for` is a safer syntax for normal traversal, not an automatic mechanism against all concurrent modifications.**

## 7. Do Not Confuse Exhausted `next()` with Invalid-State `remove()`

`Iterator.remove()` has a different contract from `next()`. In many iterators that support removal, calling `remove()` **before the first valid `next()`**, or calling `remove()` **twice after the same `next()`**, throws `IllegalStateException`.

Standalone Java 17 example **`IteratorStateVsElementDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;

public class IteratorStateVsElementDemo {
    public static void main(String[] args) {
        List<String> values =
                new ArrayList<>(Arrays.asList("A"));
        Iterator<String> it = values.iterator();

        try {
            it.remove();
        } catch (IllegalStateException e) {
            System.out.println("Sai trạng thái remove");
        }

        System.out.println("next: " + it.next());
        it.remove();
        System.out.println("Danh sách: " + values);

        try {
            it.next();
        } catch (NoSuchElementException e) {
            System.out.println("Không còn phần tử next");
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 IteratorStateVsElementDemo.java
java IteratorStateVsElementDemo
```

**Exact stdout**:

```text
Sai trạng thái remove
next: A
Danh sách: []
Không còn phần tử next
```

On the first call, `remove()` violates **API usage order**, rather than trying to fetch the next element. After `next()` and `remove()` succeed, the iterator is exhausted, and only the subsequent `next()` call throws `NoSuchElementException`.

Additionally, some iterators do not support `remove()` and may throw `UnsupportedOperationException`. Do not assume from the method name that every iterator allows removal.

## 8. `Scanner.next()`: Throws When Tokens Run Out

`Scanner` provides methods to read token data from a source:

- `hasNext()`: is there a next token?
- `next()`: retrieves the next token; throws `NoSuchElementException` if no tokens remain.
- `hasNextInt()` / `nextInt()`: checks/reads an `int` token according to the delimiter and appropriate locale/radix.
- `hasNextLine()` / `nextLine()`: checks/reads a line instead of a token.

Example **`ScannerEndDemo.java`**:

```java
import java.util.NoSuchElementException;
import java.util.Scanner;

public class ScannerEndDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("alpha beta")) {
            System.out.println(scanner.next());
            System.out.println(scanner.next());
            System.out.println("hasNext: " + scanner.hasNext());

            try {
                scanner.next();
            } catch (NoSuchElementException e) {
                System.out.println("Scanner không còn token");
            }
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 ScannerEndDemo.java
java ScannerEndDemo
```

**Exact stdout**:

```text
alpha
beta
hasNext: false
Scanner không còn token
```

`Scanner("alpha beta")` reads from a fixed string, independent of the console. After two tokens, `hasNext()` is `false`, so `next()` is rejected.

In the example, `Scanner` implements `AutoCloseable`, so `try-with-resources` is used to manage its lifecycle. However, be careful when a `Scanner` wraps a shared source: **closing the `Scanner` can close the underlying source as well**; do not arbitrarily close `Scanner(System.in)` if other parts of the program still need `System.in`.

## 9. `Scanner.nextLine()`: Running Out of Lines Is Not the Same as Running Out of Tokens

`Scanner.nextLine()` operates by **line**, rather than only extracting whitespace-delimited tokens. If no new line is found, it can throw `NoSuchElementException`.

Standalone example **`ScannerLineDemo.java`**:

```java
import java.util.NoSuchElementException;
import java.util.Scanner;

public class ScannerLineDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("dòng một\ndòng hai")) {
            while (scanner.hasNextLine()) {
                System.out.println("Đọc: " + scanner.nextLine());
            }

            try {
                scanner.nextLine();
            } catch (NoSuchElementException e) {
                System.out.println("Không còn dòng");
            }
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 ScannerLineDemo.java
java ScannerLineDemo
```

**Exact stdout**:

```text
Đọc: dòng một
Đọc: dòng hai
Không còn dòng
```

Keep them distinct:

- `hasNext()` checks whether a **token** remains.
- `hasNextLine()` checks whether a **line** can be read.
- `next()` reads a token.
- `nextLine()` reads the remainder of the current line, which does not necessarily correspond to a single token.

If you call `nextInt()` followed by `nextLine()`, the remainder of the line containing the number may be an empty string; that is **not necessarily a sign that data is exhausted**. Parser design should use a consistent token-reading or line-reading mode.

## 10. Scanner: Having a Token with the Wrong Format Is a Different Error

`Scanner.nextInt()` can throw **`InputMismatchException`** if the next token cannot be interpreted as a valid `int`. It only reports **`NoSuchElementException`** when there is no token to retrieve.

Save **`ScannerMismatchDemo.java`**:

```java
import java.util.InputMismatchException;
import java.util.NoSuchElementException;
import java.util.Scanner;

public class ScannerMismatchDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("42 abc")) {
            System.out.println("Số: " + scanner.nextInt());

            try {
                scanner.nextInt();
            } catch (InputMismatchException e) {
                System.out.println("Token không phải số nguyên");
            }

            System.out.println("Token còn lại: " + scanner.next());

            try {
                scanner.nextInt();
            } catch (NoSuchElementException e) {
                System.out.println("Đã hết token");
            }
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 ScannerMismatchDemo.java
java ScannerMismatchDemo
```

**Exact stdout**:

```text
Số: 42
Token không phải số nguyên
Token còn lại: abc
Đã hết token
```

When `nextInt()` encounters `abc`, `Scanner` throws `InputMismatchException` and **does not consume the mismatched token**; the subsequent `next()` reads that exact `abc`. The final `nextInt()` hits EOF and therefore throws `NoSuchElementException`.

For a **closed** `Scanner`, many operations such as `next()` throw `IllegalStateException`. **Do not catch `NoSuchElementException` to pretend that a closed scanner or malformed data is also EOF.**

## 11. Using `hasNextInt()` and Choosing How to Handle Invalid Tokens

If the input must be an integer, a clear pattern is:

```java
if (!scanner.hasNext()) {
    // End of source: no token available.
} else if (!scanner.hasNextInt()) {
    String badToken = scanner.next();
    // Log or report validation error for badToken.
} else {
    int value = scanner.nextInt();
    // Process value.
}
```

This is an **illustrative skeleton**, without declaring `scanner`. This handling distinguishes three situations:

1. **No data left**: `hasNext() == false`.
2. **Token exists, but is not an int**: `hasNext() == true`, `hasNextInt() == false`.
3. **Valid int token exists**: read using `nextInt()`.

In a source that can change concurrently, the check itself is not an absolute guarantee; you must follow the source's synchronization contract. With `Scanner` on interactive input, `hasNext()` can also **block waiting for data**; do not assume it is an instant, non-blocking check in every environment.

A robust input-processing system should clearly define: will an invalid token be discarded, trigger a re-prompt, or halt the entire task?

## 12. `Optional.get()`: Empty Does Not Mean `null`

`Optional<T>` represents a value that may **be present or absent**. An `Optional.empty()` contains no value; calling `get()` on it throws `NoSuchElementException`.

Example **`OptionalGetDemo.java`**:

```java
import java.util.NoSuchElementException;
import java.util.Optional;

public class OptionalGetDemo {
    public static void main(String[] args) {
        Optional<String> present = Optional.of("OK");
        Optional<String> missing = Optional.empty();

        System.out.println("Có: " + present.get());
        System.out.println("Rỗng: " + missing.isEmpty());

        try {
            missing.get();
        } catch (NoSuchElementException e) {
            System.out.println("Không có giá trị Optional");
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 OptionalGetDemo.java
java OptionalGetDemo
```

**Exact stdout**:

```text
Có: OK
Rỗng: true
Không có giá trị Optional
```

`Optional.get()` does not return `null` when empty; it throws an exception. **Also, do not confuse `Optional.empty()` with an `Optional` containing `null`**: `Optional.of(null)` throws `NullPointerException`, whereas `Optional.ofNullable(null)` creates `Optional.empty()`.

In modern Java, when you are not sure a value is present, many other `Optional` APIs express intent much more clearly than `get()`.

## 13. Alternatives to `Optional.get()`

Common alternatives:

| API | When Present | When Empty |
| --- | --- | --- |
| `get()` | Returns value | Throws `NoSuchElementException` |
| `orElse(defaultValue)` | Returns value | Returns the passed fallback |
| `orElseGet(supplier)` | Returns value | Calls supplier to produce fallback |
| `orElseThrow()` | Returns value | Throws `NoSuchElementException` |
| `orElseThrow(exceptionSupplier)` | Returns value | Creates and throws the exception provided by supplier |
| `ifPresent(consumer)` | Calls consumer | Does nothing |
| `ifPresentOrElse(present, empty)` | Runs present branch | Runs empty branch |
| `isPresent()` / `isEmpty()` | Returns boolean | Returns corresponding boolean |

**No single option is always right.** If missing data is a normal outcome, use a fallback or an empty branch. If missing data **violates a contract**, `orElseThrow(...)` with a specific semantic exception type may be better.

Note: `orElse(value)` evaluates **the `value` argument before calling the method** according to Java's evaluation rules, even when the `Optional` already holds a value; `orElseGet(supplier)` only invokes the supplier when the `Optional` is empty. This matters if the fallback is expensive or has side effects.

## 14. Java 17 Example: `Optional` Fallbacks

Save **`OptionalFallbackDemo.java`**:

```java
import java.util.Optional;

public class OptionalFallbackDemo {
    static String createFallback() {
        System.out.println("Tạo fallback");
        return "mặc định";
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("thật");
        Optional<String> empty = Optional.empty();

        System.out.println("orElse: "
                + present.orElse(createFallback()));
        System.out.println("orElseGet: "
                + present.orElseGet(OptionalFallbackDemo::createFallback));
        System.out.println("empty: "
                + empty.orElseGet(OptionalFallbackDemo::createFallback));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 OptionalFallbackDemo.java
java OptionalFallbackDemo
```

**Exact stdout**:

```text
Tạo fallback
orElse: thật
orElseGet: thật
Tạo fallback
empty: mặc định
```

The call `present.orElse(createFallback())` prints `Tạo fallback` even though the `Optional` contains `"thật"`. In contrast, `present.orElseGet(...)` does not invoke the supplier. For the empty `Optional`, `orElseGet` then creates the fallback.

This behavior **does not change `get()`'s exception**, but it helps you choose an API that matches the meaning of emptiness without using `try/catch NoSuchElementException` as part of normal control flow.

## 15. `orElseThrow` Has Two Different Forms

- `optional.orElseThrow()`: returns the value if present; otherwise throws `NoSuchElementException`.
- `optional.orElseThrow(() -> new SomeException(...))`: lets the caller **choose the exception type** created when the `Optional` is empty.

Standalone Java 17 example **`OptionalOrElseThrowDemo.java`**:

```java
import java.util.Optional;

public class OptionalOrElseThrowDemo {
    static String requireName(Optional<String> optional) {
        return optional.orElseThrow(
                () -> new IllegalArgumentException(
                        "name là bắt buộc"));
    }

    public static void main(String[] args) {
        System.out.println(requireName(Optional.of("Lan")));

        try {
            requireName(Optional.empty());
        } catch (IllegalArgumentException e) {
            System.out.println("Bắt: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 OptionalOrElseThrowDemo.java
java OptionalOrElseThrowDemo
```

**Exact stdout**:

```text
Lan
Bắt: name là bắt buộc
```

In this example, **missing a name** violates the precondition of `requireName`, so `IllegalArgumentException` expresses the contract more specifically than a generic `Optional` access error.

If a missing record is an expected business branch, you can choose to return `Optional` to the caller or a domain result type, rather than forcing it into an exception.

**A note on checked exceptions:** the `orElseThrow(exceptionSupplier)` overload can be used with a supplier that creates a checked exception; in that case, the enclosing method must catch or declare it according to Java's checked exception rules. It does not automatically turn a checked exception into an unchecked one.

## 16. `OptionalInt`, `OptionalLong`, and `OptionalDouble`

Java has specialized `Optional` classes for primitives to avoid boxing in certain situations:

- `OptionalInt.getAsInt()`
- `OptionalLong.getAsLong()`
- `OptionalDouble.getAsDouble()`

When the corresponding object is empty, these mandatory-element methods **throw `NoSuchElementException`**, just like `Optional<T>.get()`.

Example **`PrimitiveOptionalDemo.java`**:

```java
import java.util.NoSuchElementException;
import java.util.OptionalInt;

public class PrimitiveOptionalDemo {
    public static void main(String[] args) {
        OptionalInt present = OptionalInt.of(7);
        OptionalInt missing = OptionalInt.empty();

        System.out.println("Có: " + present.getAsInt());
        System.out.println("Rỗng: " + missing.isEmpty());

        try {
            missing.getAsInt();
        } catch (NoSuchElementException e) {
            System.out.println("Không có giá trị int");
        }

        System.out.println("Fallback: " + missing.orElse(-1));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 PrimitiveOptionalDemo.java
java PrimitiveOptionalDemo
```

**Exact stdout**:

```text
Có: 7
Rỗng: true
Không có giá trị int
Fallback: -1
```

Just because primitives do not have `null` does not mean `getAsInt()` always has a value: **absence is represented by the `Optional`'s state**, and a mandatory retrieval call can still fail.

## 17. `Queue`: `remove/element` vs. `poll/peek`

`java.util.Queue<E>` provides two sets of operations with different semantics when the queue is empty:

| Purpose | Throws if Empty | Returns `null` if Empty |
| --- | --- | --- |
| Retrieve and remove head element | `remove()` | `poll()` |
| Inspect head element without removing | `element()` | `peek()` |

On an empty queue, `remove()` and `element()` can throw `NoSuchElementException`. Meanwhile, `poll()` and `peek()` return `null` per the `Queue` contract.

Save **`QueueEmptyDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.NoSuchElementException;
import java.util.Queue;

public class QueueEmptyDemo {
    public static void main(String[] args) {
        Queue<String> queue = new ArrayDeque<>();

        System.out.println("poll rỗng: " + queue.poll());
        System.out.println("peek rỗng: " + queue.peek());

        try {
            queue.remove();
        } catch (NoSuchElementException e) {
            System.out.println("remove rỗng: NoSuchElementException");
        }

        queue.add("A");
        System.out.println("element: " + queue.element());
        System.out.println("remove: " + queue.remove());
        System.out.println("Sau remove rỗng: " + queue.isEmpty());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 QueueEmptyDemo.java
java QueueEmptyDemo
```

**Exact stdout**:

```text
poll rỗng: null
peek rỗng: null
remove rỗng: NoSuchElementException
element: A
remove: A
Sau remove rỗng: true
```

In the example, `ArrayDeque` does not permit `null` elements, so `poll() == null` indicates no element is present. **At the general `Queue` interface level, some implementations may allow `null` elements**, so callers must not assume the same inference for every queue type.

Choose the API by contract: for a queue used as a work source that can normally be empty, `poll()` is usually more appropriate than `remove()`.

## 18. `Deque` and Stack: `getFirst/removeFirst/pop`

`java.util.Deque<E>` extends operations at both ends of the queue. Several methods **throw `NoSuchElementException` when empty**:

- `getFirst()` and `getLast()`: read without removing.
- `removeFirst()` and `removeLast()`: read and remove.
- `pop()`: stack operation equivalent to retrieving and removing the head element; throws if empty.

The empty-signaling alternatives are:

- `peekFirst()` / `peekLast()`.
- `pollFirst()` / `pollLast()`.
- `peek()` / `poll()` at the head of the queue.

Example **`DequeEmptyDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.NoSuchElementException;

public class DequeEmptyDemo {
    public static void main(String[] args) {
        Deque<String> stack = new ArrayDeque<>();

        System.out.println("peek rỗng: " + stack.peek());

        try {
            stack.pop();
        } catch (NoSuchElementException e) {
            System.out.println("pop rỗng: NoSuchElementException");
        }

        stack.push("A");
        stack.push("B");

        System.out.println("top: " + stack.getFirst());
        System.out.println("pop: " + stack.pop());
        System.out.println("pop: " + stack.pop());
        System.out.println("poll cuối: " + stack.poll());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 DequeEmptyDemo.java
java DequeEmptyDemo
```

**Exact stdout**:

```text
peek rỗng: null
pop rỗng: NoSuchElementException
top: B
pop: B
pop: A
poll cuối: null
```

When using `Deque` as a stack, `push`/`pop` express LIFO semantics, while `peek` allows checking the top element without removing it. **Do not throw an exception to signal an empty stack in a normal branch if the caller can actively handle it with `peek` or `isEmpty`.**

## 19. Be Careful with `null` in Collections

You should not say "`NoSuchElementException` is the same as `null`":

- `NoSuchElementException` is **an error object**, with a type and a stack trace.
- `null` is a **reference value** indicating it points to no object.
- `Optional.empty()` is **an `Optional` object in an empty state**, not `null`.
- `Queue.poll()` can use `null` as an empty signal per the interface contract.
- Some collections can hold **valid `null` elements**, so a returned `null` does not always prove there is no element.
- `ArrayDeque` does not allow adding `null`, so it avoids this ambiguity in the `Queue`/`Deque` examples above.

If an API contract needs to distinguish **"no element"** from **"an element exists whose value is null"**, design a separate state-returning mechanism, such as `Optional` (noting that `Optional` cannot hold `null`), a result object, or a contextual structural check.

**Do not blindly convert `NoSuchElementException` into `null`** if the API's caller needs to know this is an abnormal invariant violation.

## 20. `Enumeration.nextElement()` Can Also Throw

The legacy API `java.util.Enumeration<E>` has two methods:

- `hasMoreElements()`: checks if more elements remain.
- `nextElement()`: retrieves the next element; throws `NoSuchElementException` if exhausted.

Example **`EnumerationDemo.java`**:

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.Enumeration;
import java.util.NoSuchElementException;

public class EnumerationDemo {
    public static void main(String[] args) {
        Enumeration<String> e =
                Collections.enumeration(Arrays.asList("X"));

        System.out.println("Phần tử: " + e.nextElement());
        System.out.println("Còn: " + e.hasMoreElements());

        try {
            e.nextElement();
        } catch (NoSuchElementException ex) {
            System.out.println("Enumeration đã hết");
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 EnumerationDemo.java
java EnumerationDemo
```

**Exact stdout**:

```text
Phần tử: X
Còn: false
Enumeration đã hết
```

`Enumeration` appears in legacy APIs and code; when designing new code, `Iterator` or appropriate collection/stream APIs are more familiar. However, when using an `Enumeration` from a library, keep the **`hasMoreElements()/nextElement()` pair** intact rather than calling `nextElement()` until an error occurs as a default approach.

## 21. `StringTokenizer.nextToken()` When No Tokens Remain

`java.util.StringTokenizer` is a long-standing token-splitting API. `nextToken()` throws `NoSuchElementException` when no tokens remain.

Java 17 example **`StringTokenizerDemo.java`**:

```java
import java.util.NoSuchElementException;
import java.util.StringTokenizer;

public class StringTokenizerDemo {
    public static void main(String[] args) {
        StringTokenizer tokenizer = new StringTokenizer("a,b", ",");

        while (tokenizer.hasMoreTokens()) {
            System.out.println("Token: " + tokenizer.nextToken());
        }

        try {
            tokenizer.nextToken();
        } catch (NoSuchElementException e) {
            System.out.println("Không còn token");
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 StringTokenizerDemo.java
java StringTokenizerDemo
```

**Exact stdout**:

```text
Token: a
Token: b
Không còn token
```

This example is not meant to recommend `StringTokenizer` for all modern parsers. If you need to parse CSV, JSON, or a format with escapes/quotes, you need a proper format-specific library/parser; simple token splitting may not suffice.

The common thread is that **every API with a "get next element" method must clearly specify its behavior at the end**.

## 22. `Stream.findFirst()` Returns `Optional`, Does Not Throw on an Empty Stream

When using Java Streams:

```java
Optional<String> first = stream.findFirst();
```

This is an **illustrative snippet**, with `stream` as a `Stream<String>`. If the stream has no elements, `findFirst()` returns `Optional.empty()`. Calling `findFirst()` on an empty stream **does not itself throw `NoSuchElementException`**.

The exception occurs if the caller subsequently **demands a value from the empty `Optional`** using `get()` or zero-argument `orElseThrow()`.

Standalone example **`StreamOptionalDemo.java`**:

```java
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.stream.Stream;

public class StreamOptionalDemo {
    public static void main(String[] args) {
        Optional<String> first = Stream.<String>empty().findFirst();

        System.out.println("Có phần tử: " + first.isPresent());
        System.out.println("Fallback: " + first.orElse("không có"));

        try {
            first.orElseThrow();
        } catch (NoSuchElementException e) {
            System.out.println("Bắt: Optional rỗng");
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 StreamOptionalDemo.java
java StreamOptionalDemo
```

**Exact stdout**:

```text
Có phần tử: false
Fallback: không có
Bắt: Optional rỗng
```

Another note: many Stream operations producing `Optional` require **a non-null element value**; if a `null` element is selected, the behavior may involve `NullPointerException` rather than `Optional.empty()`. Do not treat every stream containing a `null` element as an empty stream.

## 23. `List.get(index)` Does Not Throw the Same Type as an Exhausted Iterator

Suppose `List<String> list = List.of("A", "B")`:

- `list.get(0)` returns `"A"`.
- `list.get(2)` accesses an out-of-bounds index and throws `IndexOutOfBoundsException`.
- Calling `list.iterator().next()` until the iterator is exhausted throws `NoSuchElementException`.

Both errors occur because an access operation cannot return an element, but **their access contracts differ**:

- `List.get(index)` takes an **explicit position**. The error is an invalid index.
- `Iterator.next()` takes no index. The error is **no next element remaining**.

Java 17 example **`IndexVsElementDemo.java`**:

```java
import java.util.List;
import java.util.NoSuchElementException;

public class IndexVsElementDemo {
    public static void main(String[] args) {
        List<String> values = List.of("A");

        try {
            values.get(1);
        } catch (IndexOutOfBoundsException e) {
            System.out.println("List: chỉ số ngoài phạm vi");
        }

        var it = values.iterator();
        System.out.println("Iterator: " + it.next());

        try {
            it.next();
        } catch (NoSuchElementException e) {
            System.out.println("Iterator: không còn phần tử");
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 IndexVsElementDemo.java
java IndexVsElementDemo
```

**Exact stdout**:

```text
List: chỉ số ngoài phạm vi
Iterator: A
Iterator: không còn phần tử
```

Do not write a `catch (NoSuchElementException)` handler expecting it to catch all out-of-bounds collection accesses. It **does not** automatically catch `IndexOutOfBoundsException`.

## 24. When Should You Throw `NoSuchElementException` Yourself?

If you implement an **`Iterator`** yourself, the `next()` method must follow the contract: when no elements remain, throw `NoSuchElementException`. This is a case where **creating the exception yourself is appropriate** because you are implementing a standard API.

Example:

```java
@Override
public E next() {
    if (!hasNext()) {
        throw new NoSuchElementException(
                "No elements left in iterator");
    }
    return data[index++];
}
```

This is **illustrative code** inside a class implementing `Iterator<E>`, with corresponding `data` and `index` fields. `NoSuchElementException` should be thrown **before accessing out of bounds in the array/collection** to preserve the iterator contract, rather than letting an accidental `ArrayIndexOutOfBoundsException` surface.

You do not need to throw `NoSuchElementException` in every failed lookup method of an application. If the application has a contract where "user ID not found" is an expected business case, an `Optional` or an explicit result type may be more appropriate.

## 25. Example of Implementing an `Iterator` According to Contract

Save **`CustomIteratorDemo.java`**:

```java
import java.util.Iterator;
import java.util.NoSuchElementException;

public class CustomIteratorDemo {
    static class RangeIterator implements Iterator<Integer> {
        private int current;
        private final int limit;

        RangeIterator(int start, int limit) {
            if (start > limit) {
                throw new IllegalArgumentException(
                        "start không được lớn hơn limit");
            }
            this.current = start;
            this.limit = limit;
        }

        @Override
        public boolean hasNext() {
            return current < limit;
        }

        @Override
        public Integer next() {
            if (!hasNext()) {
                throw new NoSuchElementException(
                        "Range đã hết");
            }
            return current++;
        }
    }

    public static void main(String[] args) {
        RangeIterator it = new RangeIterator(3, 5);

        while (it.hasNext()) {
            System.out.println("Số: " + it.next());
        }

        try {
            it.next();
        } catch (NoSuchElementException e) {
            System.out.println("Bắt: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 CustomIteratorDemo.java
java CustomIteratorDemo
```

**Exact stdout**:

```text
Số: 3
Số: 4
Bắt: Range đã hết
```

The range form here is **[start, limit)**, meaning inclusive of `start` and exclusive of `limit`. When `current == limit`, `hasNext()` returns `false`, and `next()` throws a `NoSuchElementException` with a message designed by the class itself.

The example uses `Integer` to implement `Iterator<Integer>`; boxing is a minor detail acceptable for learning purposes. For very large sequences or performance requirements, a primitive iterator or specialized stream can be used if appropriate.

Note on numeric bounds: if designing a general-purpose integer iterator, consider `current++` overflow near `Integer.MAX_VALUE` and the stopping condition. The small range example here does not encounter that situation.

## 26. When Is Checking Beforehand Better Than Catching?

The standard pattern:

```java
while (iterator.hasNext()) {
    consume(iterator.next());
}
```

is usually better than an exception-based termination pattern:

```java
while (true) {
    try {
        consume(iterator.next());
    } catch (NoSuchElementException e) {
        break;
    }
}
```

Both are **illustrative code** with `consume` undefined. The second pattern has a subtle issue: **if `consume(...)` also throws `NoSuchElementException` from its own logic**, an overly broad handler may mistakenly catch the error from `consume` and treat it as the iterator being exhausted.

When using a `hasNext()` loop, the scope of the termination condition is clearer. If a special protocol forces using an exception as an EOF signal, **narrow the catch scope** to only around the source call and document that choice.

Principle: **do not use exceptions to control a normal branch when the API provides an explicit check or empty value**.

## 27. Why `hasNext()` Is Not a Concurrency Lock

In a single-threaded program that follows the iterator contract, the `hasNext()/next()` pair is the standard traversal approach. However, in a multithreaded program or with a source modified elsewhere, **check-then-act** may not be atomic.

Skeleton example:

```java
if (!queue.isEmpty()) {
    // Another thread may remove the last element here.
    String value = queue.remove();
}
```

This is a **concurrency counterexample**, without a queue declaration. With a shared queue, another thread can empty the queue **after `isEmpty()` but before `remove()`**. When that happens, `remove()` can throw `NoSuchElementException`.

If using a concurrency-supporting queue, a more suitable solution is to **perform an atomic operation per the queue API**:

```java
String value = queue.poll();
if (value == null) {
    // Queue is currently empty, assuming the queue does not allow null elements.
} else {
    process(value);
}
```

This is **illustrative code** assuming the queue does not allow `null` elements and a `process` function exists. Queues like `ConcurrentLinkedQueue` or `BlockingQueue` have their own contracts for concurrent operations.

**Do not blindly switch to `catch (NoSuchElementException)` to "fix" a race condition.** Choose an operation with the right atomicity/synchronization for the data structure and desired waiting policy.

## 28. `BlockingQueue`: When Having No Element Is Temporary

With a `BlockingQueue`, an empty queue may only be a **temporary** state because producers have not added elements yet. Depending on the API:

- `poll()`: can return `null` immediately if no element is available.
- `poll(timeout, unit)`: waits for a bounded time; returns `null` if the timeout expires without retrieving an element.
- `take()`: **waits** until an element is available and can throw `InterruptedException` if interrupted.
- `remove()`: immediate retrieval operation per the queue contract; when empty, can throw `NoSuchElementException`.

These are **different operational policies**, not merely syntactic variants of the same behavior.

Standalone Java 17 example without a producer thread, so output is deterministic:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class BlockingQueueDemo {
    public static void main(String[] args) {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);

        System.out.println("poll: " + queue.poll());
        queue.add("A");
        System.out.println("poll: " + queue.poll());
        System.out.println("empty: " + queue.isEmpty());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 BlockingQueueDemo.java
java BlockingQueueDemo
```

**Exact stdout**:

```text
poll: null
poll: A
empty: true
```

Do not use `take()` in an example without a producer because it can wait indefinitely. When using real blocking APIs, **handle interrupts** per contract; do not treat `InterruptedException` like `NoSuchElementException`.

## 29. Empty-Element Exception vs. `ConcurrentModificationException`

Many iterators on collections such as `ArrayList` have a **best-effort fail-fast** mechanism when detecting structural modification of the collection outside the iterator during iteration. When this occurs, the iterator may throw `ConcurrentModificationException`.

That is **different** from `NoSuchElementException`:

- `NoSuchElementException`: the caller requested the next element, but **there is no next element** per the contract.
- `ConcurrentModificationException`: the iterator detected a **structural modification condition incompatible** with its iteration contract.

An invalid structural modification must not be reinterpreted as "reached the end of iteration". **Do not catch `NoSuchElementException` to mask improper collection modification.**

The fail-fast mechanism is not a synchronization tool guaranteed to detect every race; the JDK documentation describes detection as best-effort in concurrent/structural modification scenarios. For correct concurrent operations, choose appropriate data structures and ownership rules.

## 30. Does `NoSuchElementException` Have Constructors and a Message?

This class can be instantiated directly with a message:

```java
throw new NoSuchElementException(
        "No more records in cursor");
```

This is an **illustrative statement**, requiring `import java.util.NoSuchElementException`. The message helps distinguish the element source when there are multiple iterators/cursors.

Like normal `RuntimeException`s, the message:

- Is accessed via `getMessage()`.
- Can be `null` depending on the constructor.
- Does not guarantee a stack trace or cause is printed if you only call `getMessage()`.
- Should not be parsed with `contains(...)` to drive business logic.
- Should not contain passwords, tokens, or sensitive data.

If you **wrap an error from another layer** into a `NoSuchElementException`, consider whether it makes semantic sense. Do not convert every I/O, database, or timeout failure into "no element" because doing so can mislead the caller about the nature of the error.

## 31. When Is Catching `NoSuchElementException` Reasonable?

There are appropriate cases:

1. An API **requires an element** and the caller wants to convert the exception into a failure state at a boundary.
2. An adapter must conform to a legacy protocol that uses exceptions to signal end-of-data.
3. A unit test intentionally verifies the `next()` contract on an exhausted iterator.
4. A wrapper layer translates the exception into a **clear domain error type** when the absence of an element is genuinely meaningful for its API.

However, **you should not catch it just to ignore the error** or make the program act as if data was read.

Example:

```java
try {
    return iterator.next();
} catch (NoSuchElementException e) {
    return DEFAULT_RECORD;
}
```

This is an **illustrative skeleton**. It is only valid if `DEFAULT_RECORD` is a fallback genuinely permitted by the contract and clearly defined. If the element is required due to a data invariant, returning a dummy object can hide a problem.

A better approach when an API has an empty option from the start is to **return `Optional` or a stateful result type** rather than catching exceptions on every access.

## 32. Do Not Catch at Too Broad a Scope

An anti-pattern:

```java
try {
    while (true) {
        Item item = iterator.next();
        process(item);
    }
} catch (NoSuchElementException ignored) {
    // Assumes iteration is finished.
}
```

This is a **counterexample skeleton**. If `process(item)` throws `NoSuchElementException` due to another internal cursor, the handler will **accidentally mask the real error** and conclude that the outer iterator is exhausted.

If you must handle an exception from a special API, isolate the catch block to the right scope:

```java
Item item;
try {
    item = iterator.next();
} catch (NoSuchElementException endOfIterator) {
    // Handle end of source here.
    return;
}
process(item);
```

This is **illustrative code inside a method**. Still, for standard `Iterator`s, a `hasNext()` loop remains the more normal solution.

Remember that **where an exception is thrown** is just as important as **the exception type**. An overly broad handler loses context and can swallow errors from unrelated operations.

## 33. Testing Empty Behavior with Plain Java

A good test not only verifies that an exception occurs, but also confirms:

- Accessing when elements remain works correctly.
- When exhausted, the contract-bound method **throws `NoSuchElementException`**.
- Empty-signaling methods like `hasNext()`, `poll()`, or `peek()` return expected values.
- No unintended state changes or lost elements occur after a failed call.
- If it is a fallback API, the fallback only runs under the documented conditions.

Example **`NoSuchElementAssertionsDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Queue;

public class NoSuchElementAssertionsDemo {
    static void expectNoElement(Runnable action) {
        try {
            action.run();
            throw new AssertionError("Thiếu NoSuchElementException");
        } catch (NoSuchElementException expected) {
            System.out.println("PASS: đã ném NoSuchElementException");
        }
    }

    public static void main(String[] args) {
        Iterator<Integer> iterator = List.of(1).iterator();

        if (iterator.next() != 1 || iterator.hasNext()) {
            throw new AssertionError("Sai trạng thái iterator");
        }

        expectNoElement(iterator::next);

        Queue<String> queue = new ArrayDeque<>();
        if (queue.poll() != null) {
            throw new AssertionError("Queue phải rỗng");
        }

        expectNoElement(queue::remove);
        System.out.println("PASS: hợp đồng rỗng được giữ");
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 NoSuchElementAssertionsDemo.java
java NoSuchElementAssertionsDemo
```

**Exact stdout**:

```text
PASS: đã ném NoSuchElementException
PASS: đã ném NoSuchElementException
PASS: hợp đồng rỗng được giữ
```

`Runnable` allows using method references `iterator::next` and `queue::remove` here because those methods return a value, and a call in a `void` functional interface context can discard the result. `NoSuchElementException` is unchecked, so there is no checked `throws` obstacle.

The test uses `throw new AssertionError(...)` to fail explicitly, without depending on the `-ea` flag of the `assert` keyword.

## 34. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "`NoSuchElementException` is checked so `throws` must be declared." | False. It extends `RuntimeException` and is unchecked. |
| "`hasNext()` returning `false` throws the exception automatically." | No. Calling `next()` when exhausted is what throws per the iterator contract. |
| "Every empty collection automatically throws `NoSuchElementException`." | No. It depends on the method: `peek/poll` can return `null`. |
| "`Queue.remove()` and `Queue.poll()` are identical." | No. On an empty queue, `remove` throws while `poll` returns `null`. |
| "`Queue.element()` and `Queue.peek()` are identical." | No. On an empty queue, `element` throws while `peek` returns `null`. |
| "`Deque.pop()` on an empty stack returns `null`." | False. `pop` throws `NoSuchElementException` when empty. |
| "`Optional.empty().get()` returns `null`." | False. It throws `NoSuchElementException`. |
| "`Optional.orElseThrow()` just creates another unchecked exception." | No. The no-arg version throws `NoSuchElementException` when empty. |
| "`orElse(default())` only calls `default()` when `Optional` is empty." | False. The argument expression is evaluated before the call; use `orElseGet` when a lazy fallback is needed. |
| "`Scanner.nextInt()` throws `NoSuchElementException` on letters." | When a token of the wrong type remains, it usually throws `InputMismatchException`; only when no tokens remain is it `NoSuchElementException`. |
| "`Scanner.nextLine()` and `Scanner.next()` are always equivalent." | No. One reads a line, the other reads a token. |
| "Out-of-bounds `List.get(index)` throws `NoSuchElementException`." | False. It typically throws `IndexOutOfBoundsException`. |
| "After `hasNext()`, another thread definitely cannot modify the source." | No. The check does not lock the source; you must follow the concurrency contract. |
| "Catching `NoSuchElementException` around the whole loop is the best way." | It easily masks errors from processing logic; use `hasNext()` where appropriate. |
| "`ConcurrentModificationException` means the iterator is out of elements." | False. It indicates structural modification violating the fail-fast iterator's conditions. |
| "A queue returning `null` always means empty in every implementation." | Some `Queue` implementations can hold `null`; check the implementation contract. |
| "`NoSuchElementException` signals corrupted data or a timeout." | Not by default; those causes have different exception contracts. |
| "Catching the exception means you can return success." | Only if a valid fallback truly exists; do not turn failure into fake success. |

## 35. Self-Check Questions

**1.** `Iterator.hasNext()` returns `false`. What happens if you call `next()`?  
**Answer:** `next()` throws `NoSuchElementException` per the `Iterator` contract.

**2.** Is `NoSuchElementException` checked or unchecked?  
**Answer:** Unchecked, because it extends `RuntimeException`.

**3.** Why is a `while (it.hasNext()) { it.next(); }` loop better than using an exception to stop?  
**Answer:** The end-of-data condition is expressed directly, with less risk of accidentally catching errors from other processing logic.

**4.** Calling `Iterator.remove()` before `next()` on an iterator that supports removal can throw what?  
**Answer:** `IllegalStateException`, which differs from `NoSuchElementException` when `next()` runs out of elements.

**5.** How do `Queue.remove()` and `Queue.poll()` differ when the queue is empty?  
**Answer:** `remove()` throws `NoSuchElementException`; `poll()` returns `null`.

**6.** How do `Queue.element()` and `Queue.peek()` differ when the queue is empty?  
**Answer:** `element()` throws; `peek()` returns `null`.

**7.** Does `Deque.pop()` on an empty deque return `null`?  
**Answer:** No. It throws `NoSuchElementException`.

**8.** What does `Optional.empty().get()` return?  
**Answer:** It does not return normally; it throws `NoSuchElementException`.

**9.** What does `Optional.empty().orElse("fallback")` return?  
**Answer:** `"fallback"`.

**10.** What does `Optional.empty().orElseThrow(() -> new IllegalStateException(...))` throw?  
**Answer:** The exception created by the supplier—in this example, `IllegalStateException`.

**11.** What does `OptionalInt.empty().getAsInt()` throw?  
**Answer:** `NoSuchElementException`.

**12.** How does `Scanner.nextInt()` encountering the token `"abc"` differ from encountering EOF?  
**Answer:** If a token exists but is not in integer format, it throws `InputMismatchException`; if no token exists, it throws `NoSuchElementException`.

**13.** After an `InputMismatchException` from `Scanner.nextInt()`, is the invalid token automatically consumed?  
**Answer:** No. That token can be read or skipped using an appropriate method, such as `next()`.

**14.** Is `Scanner.next()` on a closed `Scanner` a normal "no tokens left" case?  
**Answer:** No. Using a closed `Scanner` can throw `IllegalStateException`.

**15.** Does `List.of("A").get(1)` throw `NoSuchElementException`?  
**Answer:** No. That is an invalid index access and typically throws `IndexOutOfBoundsException`.

**16.** What does `Enumeration.nextElement()` throw when exhausted?  
**Answer:** `NoSuchElementException`.

**17.** What does `StringTokenizer.nextToken()` throw when no tokens remain?  
**Answer:** `NoSuchElementException`.

**18.** Does `Stream.empty().findFirst()` itself throw `NoSuchElementException`?  
**Answer:** No. It returns `Optional.empty()`; an exception occurs if the caller forces retrieval from the empty `Optional`.

**19.** One thread checked `!queue.isEmpty()`, and another thread removed the last element before `queue.remove()`. What can happen?  
**Answer:** `remove()` can throw `NoSuchElementException`; use an appropriate API/synchronization, such as `poll()` on a suitable queue.

**20.** Why shouldn't you wrap all of `consume(iterator.next())` in `catch (NoSuchElementException)`?  
**Answer:** `consume` might itself throw the same exception type from another source, causing the program to mistake it for the end of the outer iterator.

**21.** When writing `Iterator.next()` yourself, what should you do if `hasNext() == false`?  
**Answer:** Throw `NoSuchElementException` per the contract, rather than letting an accidental index error occur instead.

**22.** Is `NoSuchElementException` synonymous with `null`?  
**Answer:** No. One is an exception, the other is a reference value.

**23.** A job queue can be temporarily empty. Should you choose `remove()` or `poll()/take()`?  
**Answer:** It depends on the policy. `poll()` allows an empty result, `take()` on a `BlockingQueue` waits for an element; `remove()` throws an exception when empty.

**24.** If data not found is an expected business outcome, are you required to throw `NoSuchElementException`?  
**Answer:** No. You can return `Optional` or an explicit result type.

## 36. Practical Checklist

When encountering or wanting to prevent `NoSuchElementException`:

1. **Identify which method actually throws:** `next`, `nextLine`, `get`, `remove`, `element`, `pop`, or another API?
2. **Read the exact API contract:** do not infer from the collection name and overlook `poll/peek/hasNext` options.
3. **Is emptiness normal?** If normal, use a check or empty-signaling method.
4. **Is an element required by an invariant?** If so, throwing the appropriate type with a contextual message may be suitable.
5. **With `Iterator`, did you use `hasNext()` before `next()`?**
6. **With `Scanner`, did you distinguish tokens, lines, and data format?** Do not confuse `InputMismatchException` with EOF.
7. **With `Optional`, can you use `orElse`, `orElseGet`, `orElseThrow(supplier)`, or `ifPresentOrElse`?**
8. **With `Queue`, are you using `remove/element` when `poll/peek` is more suitable?**
9. **With `Deque`, did you distinguish `pop` from `poll`, and `getFirst` from `peekFirst`?**
10. **With `List`, did you confuse `IndexOutOfBoundsException` with `NoSuchElementException`?**
11. **Can the collection contain `null`?** Ensure the `null` signal is not ambiguous.
12. **Can the source be modified concurrently?** Check for races between "element exists" and "retrieve element".
13. **Is the handler catching too broadly?** Avoid swallowing a `NoSuchElementException` from unrelated logic.
14. **Are you accidentally returning fake success after catching the error?**
15. **Do you really need a custom exception class?** If implementing `Iterator`, use the standard JDK class.
16. **Did you test both the element-present path and the exhausted path?**
17. **Did you test the state after a failed operation?** Ensure no elements are lost or iterator positions shifted.
18. **In a concurrent environment, did you choose a queue/lock/atomic operation matching the contract?**
19. **If using `BlockingQueue`, are there appropriate timeout and interrupt policies?**
20. **Do logs include enough source and failed operation names without exposing sensitive data?**

## 37. Conclusion

`NoSuchElementException` is an **unchecked exception indicating that an operation requested an element, but that element does not exist** according to the method's contract. Typical cases are `Iterator.next()` when exhausted, `Scanner.next()/nextLine()` when no suitable data remains, `Optional.get()` when empty, and `Queue.remove()/element()` or `Deque.pop()` when the container is empty.

**Do not turn normal empty situations into errors by choosing the wrong API.** With `Iterator`, use `hasNext()`; with `Optional`, choose `orElse`/`orElseGet`/`orElseThrow(supplier)` per the contract; with `Queue`/`Deque`, consider `poll/peek`. If an element is mandatory, an exception is an intentional way to signal a violation and should include a sufficiently contextual message when building your own API.

Most importantly: **do not equate "no element" with "invalid index", "malformed input", "closed scanner", "concurrently modified collection", or "null value"**. Classifying the cause accurately and choosing the API with the right contract makes programs easier to read and test, without swallowing errors or returning fake success results.
