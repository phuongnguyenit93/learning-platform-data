# Wakeup, Canceling SelectionKey, and Closing Selector in Java NIO

## 1. Why Are Three Different Operations Needed?

In Java NIO, a `Selector` manages multiple `SelectableChannel` instances so a program can wait for channels ready to read, write, accept connections, or finish connecting without dedicating a waiting thread per socket. Each registration of a channel with a selector creates or returns a `SelectionKey` representing that registration relationship.

As an event loop runs, an application typically needs to handle three very different tasks:

1. **`selector.wakeup()`:** wakes up a waiting selection call, or causes the next selection call to return immediately. The selector and channels remain usable.
2. **`key.cancel()`:** cancels the registration of **one channel with one selector**; the key becomes invalid immediately, while removal from key sets and actual deregistration happen during a subsequent selection pass.
3. **`selector.close()`:** ends the lifecycle of **the entire selector**, invalidating all keys bound to it and releasing selector resources; **it does not automatically close registered channels**.

Do not treat these three calls as equivalent ways to "stop I/O."

| Operation | What Changes Immediately | Do Channels Close? | Is Selector Still Usable? |
|---|---|---|---|
| `wakeup()` | A select pass is woken up or the next select is pre-signaled | No | Yes |
| `SelectionKey.cancel()` | Key becomes invalid; placed in cancelled-key set | No | Yes |
| `Selector.close()` | Selector closes; associated keys are invalidated and deregistered | **Not automatically** | No |
| `channel.close()` | The channel itself closes and its registrations are canceled | **Yes, that channel** | Yes if selector is not closed |

Note: if a channel is registered on **multiple selectors**, `key.cancel()` only cancels the registration bound to that key. Conversely, `channel.close()` acts on the channel itself and invalidates all keys registering that channel.

## 2. Understanding Selector, SelectionKey, and the Three Key Sets

`Selector.open()` creates a selector. Only a `SelectableChannel` in **non-blocking mode** can be registered via `channel.register(selector, ops)`. For TCP:

~~~java
SocketChannel channel = SocketChannel.open();
channel.configureBlocking(false);
SelectionKey key = channel.register(selector, SelectionKey.OP_READ);
~~~

This is an **illustrative snippet**; it requires an open `Selector selector` variable, an appropriately conditioned channel, and imports. A newly opened, unconnected channel should generally not register `OP_READ` before connecting completes; this example only illustrates the `register` API and is not a standalone runnable program.

According to Java 17, a selector has three logical sets:

- **Key set — `selector.keys()`:** the set of keys registered with the selector (cannot be arbitrarily added to or removed from).
- **Selected-key set — `selector.selectedKeys()`:** keys detected as ready in the preceding selection pass. The application normally removes keys from this set after handling them.
- **Cancelled-key set:** an internal set containing keys that have been canceled but not yet deregistered. **There is no public API to read this set directly.**

At the start of a selector's lifecycle, the sets are empty. After `register`, the key appears in the key set. After `select` detects readiness, the key may appear in the selected-key set. After `cancel`, the key becomes invalid immediately yet may still appear in `keys()` until the next selection processes cancellation.

~~~text
register(channel, OP_READ)
       |
       v
Valid key in selector.keys()
       |
       +-- select detects readiness --> selectedKeys may contain key
       |                                  |
       |                                  +-- application handles then iterator.remove()
       |
       +-- key.cancel() --------> key invalid immediately
                                         |
                                         v
                              Internal cancelled-key set
                                         |
                                      next select
                                         |
                                         v
                             Deregister, remove from sets
~~~

**Distinction:** `selectedKeys().remove(key)` only removes the key from **the list of events awaiting application handling**, without canceling registration. `key.cancel()` is what requests stopping monitoring of that registration.

## 3. \`Selector.wakeup()\`: Waking Up a Selection Pass

`Selector.wakeup()` is a coordination tool when a thread is waiting inside `select()` or when another thread needs to update the event loop's work or `interestOps`.

Cases:

1. **A thread is already blocked in `select()`:** `wakeup()` causes that operation to return early. It **does not guarantee** the return value is `0`, because a key may simultaneously be ready.
2. **No selection is currently waiting:** the next selection call returns immediately, unless a `selectNow()`/`selectNow(Consumer)` consumes that pending wakeup state beforehand.
3. **Calling wakeup multiple times between two selection passes:** the effect is like **a single call**; there is no queue counting wakeup signals.
4. **After a woken selection pass:** the following selection pass blocks normally if no readiness or new signal exists.
5. **`wakeup()` does not register, cancel, or close any channel**, nor does it put a task into an application queue by itself.

Signature:

~~~java
public abstract Selector wakeup()
~~~

The method returns the selector itself to support chaining, though clear event-loop code typically writes `selector.wakeup();`.

### When to Use Wakeup?

Suppose a thread managing an event loop is doing:

~~~java
while (running) {
    selector.select();
    // Process ready keys and tasks sent from other threads.
}
~~~

If another thread needs to ask the event loop to modify an interest set, register a channel, send data, or stop the loop, it can **push a request into a queue first and then call wakeup**. Upon waking up, the event loop processes the requests before calling select again.

~~~text
Worker thread: queue.add(task) ---> selector.wakeup()
                                            |
                                            v
Event loop thread: select() returns --> drain queue --> update state
                                                    --> process readiness
                                                    --> select again
~~~

To avoid losing requests under contention, the queue must be thread-safe (such as `ConcurrentLinkedQueue`) or properly synchronized. `wakeup` is a **wakeup signal**, not a substitute for a queue and carries no payload.

### Wakeup Before Select Still Takes Effect

There is no need to try using `Thread.sleep` to "time" when the thread is blocking. Java guarantees that a **wakeup called before the next select** also takes effect. For example:

~~~java
selector.wakeup();
int updated = selector.select(); // returns immediately, updated may be 0
~~~

This is an illustrative snippet. If a channel is ready, the result can be non-zero. `selectNow()` returns immediately in all cases and **clears any unused wakeup effect**.

### Wakeup vs. Thread.interrupt

Another thread calling `selector.wakeup()` **does not set the interrupt flag** on the event-loop thread. Calling `thread.interrupt()` while that thread is blocked in selection sets the interrupt flag and wakes up the selector similarly to calling `wakeup()`. Do not automatically infer that waking `Selector.select()` throws `ClosedByInterruptException` or closes channels; that exception belongs to blocking I/O on an `InterruptibleChannel`, whereas `select` has its own contract.

If the intent is merely to signal "there is a new task," `wakeup()` usually expresses that intent more cleanly than `interrupt()`.

## 4. \`SelectionKey.cancel()\`: Canceling a Registration

`SelectionKey.cancel()` has exact semantics:

- Upon return, `key.isValid()` is **`false`**.
- The key is added to the selector's **cancelled-key set** and will be removed from all key sets, while the channel is deregistered, during the next selection pass.
- Canceling the same key repeatedly is **idempotent**: subsequent calls have no additional effect.
- A canceled key **never becomes valid again**. If you need to watch the channel again, wait for deregistration to finish and call `register` to obtain a new key.
- **`cancel()` does not close the channel**. The application can still use the channel directly if it remains open and in an appropriate state.

Observing the state:

~~~java
key.cancel();
System.out.println(key.isValid()); // false
selector.selectNow();              // processes cancelled-key set
~~~

This snippet illustrates the operation sequence while `selector` is still open. If you only call cancel without calling a selection afterward, the key can still show up in `selector.keys()`; that is a valid intermediate state.

### Distinguishing Cancel vs. Removing from selectedKeys

Two operations appear together in the same event loop but have different effects:

~~~java
Iterator<SelectionKey> it = selector.selectedKeys().iterator();
while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove(); // took one event out of the selected-key set

    if (!key.isValid()) {
        continue; // key may have been canceled on another thread
    }

    if (key.isReadable()) {
        // Read until no more data is currently available or budget is exhausted.
    }
}
~~~

This is **a snippet inside a method that already has a `selector` variable**; the read processing is just a comment. `it.remove()` does not cancel and does not close the channel; it only avoids reprocessing an old event. Because `selectedKeys()` does not auto-clear after each turn, forgetting this is a common source of CPU busy loops.

### What Happens to selectedKeys on Cancel?

After `cancel()`, the key becomes invalid immediately yet may remain inside `selectedKeys()`/`keys()` until a selection operation runs its cancellation cleanup step. Therefore, when iterating selected keys, check `key.isValid()` before calling `readyOps()`, `isReadable()`, `isWritable()`, or updating `interestOps()`.

Those calls can throw `CancelledKeyException` if the key is invalid. Checking and acting can also race with another thread; avoid letting multiple threads arbitrarily manipulate the same key without ownership rules.

### What If You Want to Cancel and Re-Register Immediately?

`cancel()` does not immediately deregister the underlying registration. In code running proactively on the event loop, you can call `selector.selectNow()` to drive cancelled-key processing, and only then re-`register` the channel if it is still open and non-blocking. This highlights the distinction between **immediate key invalidation** and **selection-driven deregistration**.

Do not call `selectNow()` arbitrarily from multiple threads concurrently with an event loop owning a selector; designate one thread to own selection to avoid contention.

## 5. \`Selector.close()\`: Stopping the Selector Without Closing Channels

`Selector` implements `Closeable` and `AutoCloseable`. Therefore, use `try-with-resources` or a shutdown method ensuring `close()` is called by the proper owner.

According to Java 17, `selector.close()`:

1. Marks the selector closed and frees internal resources belonging to the selector.
2. If another thread is blocked in a selection operation, it is woken up as if via `wakeup()`.
3. Still-registered keys are invalidated, and channels are **deregistered from this selector**.
4. Calling `close()` a second time has no additional effect.
5. Subsequent uses of the selector after closing (except `close()`/`wakeup()`) throw `ClosedSelectorException`.
6. **Does not automatically close `SocketChannel`, `ServerSocketChannel`, `DatagramChannel`, `Pipe.SourceChannel`, or other registered channels**.

The last point is critical for resource leaks: closing a selector is **not** a command to close all socket connections. The server must close the channels it owns separately from the selector.

Example:

~~~java
Selector selector = Selector.open();
SocketChannel channel = SocketChannel.open();
try {
    channel.configureBlocking(false);
    channel.register(selector, SelectionKey.OP_CONNECT);

    selector.close();
    System.out.println(channel.isOpen()); // true
} finally {
    channel.close();
}
~~~

**Illustrative snippet**: can throw `IOException`; the newly opened socket is not connected yet, though it can still register `OP_CONNECT` interest per `validOps`. `selector.close()` does not close `channel`. Do not treat this as a complete TCP connection example.

### Closing While a Thread Is Selecting

Another thread can call `selector.close()` to stop a blocking `select()`. However, the event loop must be prepared to observe the closed selector, potentially catching `ClosedSelectorException` on a subsequent operation, and stop using the selector. **Do not rely on a fixed number of ready keys** when close/cancel runs concurrently.

If you only want the event loop to wake up, run new tasks, and continue, use `wakeup()`. Only when the selector's lifecycle is actually ending should you call `close()` as part of shutdown.

## 6. Runnable Java 17+ Demo: wakeup, cancel, close

The following demo uses only an internal `Pipe` and `Selector`, requiring no network connection or port. No bytes are sent into the pipe, so with no readiness present, `wakeup()` makes `select()` return with 0 selected keys. It then cancels the key and demonstrates that the channel stays open even after the selector is closed.

**File: `SelectorLifecycleDemo.java`**

~~~java
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;

public class SelectorLifecycleDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Selector selector = Selector.open();
             Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {

            source.configureBlocking(false);
            SelectionKey key =
                    source.register(selector, SelectionKey.OP_READ);

            System.out.println("registered=" + selector.keys().size());

            selector.wakeup();
            System.out.println("selected=" + selector.select());

            System.out.println("valid before=" + key.isValid());
            key.cancel();
            System.out.println("valid after=" + key.isValid());
            System.out.println(
                    "pending count=" + selector.keys().size());

            selector.selectNow(); // processes cancelled-key set
            System.out.println(
                    "removed count=" + selector.keys().size());
            System.out.println(
                    "source open after cancel=" + source.isOpen());

            SelectionKey second =
                    source.register(selector, SelectionKey.OP_READ);
            System.out.println("second valid=" + second.isValid());

            selector.close();
            System.out.println(
                    "second valid after close=" + second.isValid());
            System.out.println(
                    "source open after selector close=" + source.isOpen());
        }
    }
}
~~~

Compile and run:

~~~bash
javac SelectorLifecycleDemo.java
java SelectorLifecycleDemo
~~~

**Stdout on JDK 17+ under the conditions described in the demo:**

~~~text
registered=1
selected=0
valid before=true
valid after=false
pending count=1
removed count=0
source open after cancel=true
second valid=true
second valid after close=false
source open after selector close=true
~~~

Explanation:

1. `source.configureBlocking(false)` is required to register with the selector.
2. `wakeup()` before `select()` ensures the select pass returns immediately; because the pipe has no data, `selected=0`.
3. `key.cancel()` makes `key.isValid() == false` immediately, yet prior to the next selection pass the key remains in `selector.keys()`: `pending count=1`.
4. `selector.selectNow()` processes cancellation and deregistration, leaving the key set empty.
5. The source channel stays open after `cancel()`, so it can be re-registered; the new key is valid.
6. `selector.close()` invalidates the new key but **does not close the source channel**.
7. `try-with-resources` still closes both source and sink when the scope ends, leaving no leaked pipe resources.

There is no `Thread.sleep()` in the demo: the immediacy of `select()` comes directly from the `wakeup()` contract, independent of thread timing. The demo models a channel with no readiness; in an application with ready keys, `select()` can return a non-zero count even when woken up.

## 7. Event Loop Receiving Commands from Other Threads via Task Queue and Wakeup

A clean architecture is to have **one dedicated thread** execute `select`, iterate `selectedKeys`, update `interestOps`, and close channels owned by the event loop. Other threads never touch the selected-key set directly; they push commands into a queue and signal `wakeup`.

Skeleton example (illustrates structure only, not a complete program):

~~~java
final class LoopCommands {
    private final Selector selector;
    private final Queue<Runnable> pending =
            new ConcurrentLinkedQueue<>();

    LoopCommands(Selector selector) {
        this.selector = selector;
    }

    void submit(Runnable task) {
        pending.add(task);
        selector.wakeup();
    }

    void drain() {
        for (Runnable task; (task = pending.poll()) != null; ) {
            task.run();
        }
    }
}
~~~

Imports for `java.nio.channels.Selector`, `java.util.Queue`, and `java.util.concurrent.ConcurrentLinkedQueue` are needed in a real program. `drain()` is called by the **event-loop thread**. Placing `pending.add(task)` before `selector.wakeup()` ensures the task is already in the queue when the loop wakes up.

A typical event loop:

~~~java
while (running) {
    selector.select();
    commands.drain();

    Iterator<SelectionKey> keys = selector.selectedKeys().iterator();
    while (keys.hasNext()) {
        SelectionKey key = keys.next();
        keys.remove();

        if (!key.isValid()) {
            continue;
        }
        // Handle OP_ACCEPT / OP_CONNECT / OP_READ / OP_WRITE.
    }
}
~~~

This is illustrative code: `running`, `commands`, and `selector` are already initialized variables, and I/O handling must be implemented. Other threads call `commands.submit(...)` to add or cancel interest or flip shutdown state. Production code needs handling for `IOException`, `CancelledKeyException`, per-client state, backpressure, and errors inside `Runnable` so one failing command does not unintentionally bring down the entire event loop.

**Note:** `wakeup()` **does not force a selector already inside a selection pass to immediately apply `interestOps` changes to that same pass**. Java 17 specifies that changes to an interest set made during an ongoing select take effect on the **next selection pass**. Consequently, using a queue + wakeup and mutating `interestOps` on the event-loop thread is easier to reason about.

## 8. The Selected-Key Set and Common Contention Issues

### 8.1. selectedKeys Does Not Clear Completely on Its Own

`selector.selectedKeys()` returns the set of selected keys for the application to process. If you iterate without `iterator.remove()`, a key can stay in that set after its readiness was handled. On the next select pass, new ready operations of an already-present key can be merged into its old state. This easily causes **duplicate readiness processing** and busy loops.

The standard practice is removing each key from the selected-key set before dispatching.

### 8.2. Two Different Styles of Select in Java 17

- `select()` / `select(timeout)` / `selectNow()` use the **selected-key set**, which the application cleans up itself.
- Java 11+ overloads taking `Consumer<SelectionKey>`, such as `select(action)` or `selectNow(action)`, **invoke the callback directly** on ready keys, **without adding keys to the selected-key set** for that selection style.

With callback selection, be very careful because the callback runs during synchronized selection. **Never perform a reentrant selection operation on the same selector inside the callback**; behavior is not uniformly defined across providers. If the callback closes the selector, the selection call throws `ClosedSelectorException` once the callback returns.

### 8.3. Thread Safety of the Sets

Per the `Selector` documentation:

- **The selector and its key set** are safe for certain concurrent operations documented by the API.
- **The selected-key set and cancelled-key set are not considered thread-safe** for arbitrary direct use.
- `key.cancel()` may be called from another thread, though actual deregistration happens during a selection operation.
- Before handling a key taken from a set, account for the possibility that the key was canceled or the channel was closed on another thread.
- If multiple threads access the selected-key set directly, synchronize per the API contract; it is simpler to assign iterating and removing selected keys strictly to one event-loop thread.

`selector.keys()` should also **not be used as a list guaranteed to hold only valid keys**, because canceled keys may not yet be removed from the set.

## 9. Proper Shutdown: Wakeup, Cancel Keys, Close Channels, and Close Selector

To stop a server/event loop without leaking sockets or file descriptors, cleanly separate **signaling** from **cleanup**.

A common sequence:

1. Set state `running = false` or enqueue a shutdown command in a thread-safe manner.
2. Call `selector.wakeup()` so a waiting event-loop thread exits `select()` and receives the stop command.
3. Stop accepting new registrations or opening new sockets; stop accepting new messages per server policy.
4. Cancel keys and/or close each channel still owned by the service. `key.cancel()` alone does not close connections.
5. Close the `selector` in `finally` / `try-with-resources` to release selector resources; stop calling `select` after closing.
6. Reclaim remaining resources such as worker executors, message buffers with special ownership, timers, or linked adapters.

An illustrative shutdown skeleton:

~~~java
void requestStop() {
    running = false;       // e.g. running is volatile
    selector.wakeup();     // signal to the event-loop thread
}

void cleanupOnLoopThread() throws IOException {
    for (SelectionKey key : selector.keys()) {
        key.channel().close(); // close channel resource owned by the loop
    }
    selector.close();
}
~~~

This is **illustrative code inside a manager class** with fields `volatile boolean running` and `Selector selector`, omitting full error handling and synchronization. Only loop and close all `key.channel()` if the event loop **truly owns** all of those channels; for channels borrowed from another component, coordinate ownership explicitly.

### Why Not Just Call selector.close?

If you only close the selector, socket channels can remain open. That holds onto OS resources and connections unnecessarily, leading to "too many open files" errors or exhausting file descriptors and network resources. **Closing the selector does not substitute for closing channels**.

### Why Not Just Call key.cancel?

`cancel()` only removes the channel from multiplexing, and actual removal happens on the next selection. The channel stays open. Unless the application intentionally keeps the channel to use outside the selector, it must close it when finished.

### Why Not Call Thread.interrupt Instead of wakeup?

Interrupt is a thread-level signal that affects how tasks handle cancellation and other blocking operations. `wakeup` is purpose-built for selection; with task queues/event loops, it generally has clearer semantics. If a thread has been interrupted, code must respect the interrupt flag and the application's shutdown policy.

## 10. When to Use selectNow vs. When to Use wakeup?

| Scenario | Appropriate API | Note |
|---|---|---|
| Thread A is in event loop `select()`, B just submitted a task | `selector.wakeup()` | Task must be stored outside the selector |
| A thread wants to poll readiness without blocking | `selector.selectNow()` | Also consumes any pending wakeup |
| Want to cancel a registration | `key.cancel()` | Does not close channel; waits for selection pass |
| Want to process canceled keys immediately on selector-owning thread | `selector.selectNow()` | Advances deregistration |
| Want to shut down the selector completely | `selector.close()` | Keys invalid, channels still need cleanup |
| Want to terminate a TCP connection | `socketChannel.close()` | Channel registrations are also canceled |
| Only want to remove a dispatched event from the selected-key set | `iterator.remove()` | Registration remains valid |

A common pattern seen in older code is calling `selector.wakeup()` multiple times to "send multiple tasks." However, wakeup **does not count events**; use a queue, drain until empty, and use wakeup purely as a wakeup signal.

## 11. Common Mistakes

1. **"`wakeup()` closes the selector."** False. It only wakes up one selection or sets a pending wakeup.
2. **"Each `wakeup()` adds one wakeup turn to a queue."** False. Multiple wakeups between two selections behave as one.
3. **"Calling wakeup before select has no effect."** False. The next select pass can return immediately.
4. **"`wakeup()` always makes `select()` return 0."** False. Ready keys can still be detected.
5. **"`key.cancel()` removes the key from `keys()` immediately."** False. The key becomes invalid immediately, while deregistration happens during a later selection operation.
6. **"`key.cancel()` closes the socket."** False. The channel stays open unless closed separately.
7. **"`selector.close()` closes all registered channels."** False. It closes the selector, invalidates keys, and deregisters; channels must be closed by their owner.
8. **"`selector.keys()` contains only valid keys."** False. Canceled keys can remain there temporarily.
9. **"Removing a key from `selectedKeys` cancels the registration."** False. It only clears the selected event.
10. **"`selectedKeys` is auto-cleared by Java after every select."** False. The application must remove handled keys itself.
11. **"Always read `isReadable()` whenever a key is in `selectedKeys`."** False. The key might have been canceled, so check validity and account for races.
12. **"Selector and all key sets are thread-safe for arbitrary manipulation."** False. The selected-key set requires proper synchronization or strict single-thread ownership by the event loop.
13. **"Changing `interestOps` from another thread during select takes effect immediately in that same pass."** Not guaranteed; it takes effect in the next selection pass.
14. **"After closing a selector, you can select again after calling wakeup."** False. A closed selector continues throwing `ClosedSelectorException` on selection.

## 12. Self-Check Questions

**Question 1:** Thread A is in `selector.select()`, thread B enqueues a task and calls `selector.wakeup()`. Does A need to close the selector to handle the task?

**Answer:** No. `wakeup` makes select return; A processes the task and can continue selecting on the still-open selector.

**Question 2:** Right after calling `key.cancel()`, what is `key.isValid()` and can the key still be in `selector.keys()`?

**Answer:** `false` immediately. Yes; removal from the key set and deregistration occur during the next selection pass.

**Question 3:** Does closing the selector automatically close registered `SocketChannel`s?

**Answer:** No. The selector invalidates keys and deregisters, while open channels must be managed and closed by their owner if needed.

**Question 4:** What is the difference between `iterator.remove()` on `selectedKeys` and `key.cancel()`?

**Answer:** `iterator.remove()` only removes an event from the selected set; `cancel()` invalidates the channel's registration on the selector.

**Question 5:** Do five `wakeup()` calls between two `select()` calls guarantee the next five selects will not block?

**Answer:** No. Wakeups coalesce into one; after the selection pass that consumes the wakeup, subsequent passes can block.

### Official Java 17 Documentation

- [Selector: key sets, selection, concurrency, wakeup, close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [SelectionKey: cancel, isValid, interestOps](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html)
- [SelectableChannel: register and blocking mode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html)
- [CancelledKeyException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CancelledKeyException.html)
- [ClosedSelectorException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ClosedSelectorException.html)
