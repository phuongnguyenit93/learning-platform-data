# 9.6 `compareAndSet`, `compareAndExchange`, and Atomic Update Operations with VarHandle

When multiple threads update a variable concurrently, `counter++` is not an atomic action: each increment consists of reading, computing, and writing. If two threads both read the old number before writing, an increment can be lost. `java.lang.invoke.VarHandle` (available since Java 9, well-supported in Java 17) provides several **atomic read-modify-write operations** on fields or array elements to perform check-and-update, addition, and bit manipulation without splitting into steps that another thread can interleave between.

Core points of this lesson:

- `compareAndSet(expected,newValue)` checks and updates atomically, returning a **`boolean` success/failure**.
- `compareAndExchange(expected,newValue)` also checks and updates atomically, but returns the **witness**: the value actually observed during the comparison.
- `weakCompareAndSet*` may suffer **spurious failure** even when expected matches; it requires proper retrying.
- `getAndSet`, `getAndAdd`, `getAndBitwiseOr/And/Xor`, and their Acquire/Release variants update atomically using built-in transformations and return the **old value**.
- **Atomicity and memory ordering are two different issues.** Choosing the wrong mode or inconsistently mixing plain and volatile accesses can make a concurrent program incorrect even when an individual RMW operation remains atomic.

This lesson focuses on VarHandle access modes in Java 17, how to invoke them with the right receiver/coordinates, return types, memory semantics, errors, and practical use cases.

## 1. Why is `volatile` not enough for incrementing?

The code snippet:

~~~java
volatile int counter;
counter++;
~~~

is **an illustrative snippet inside a class declaration**, not a standalone program. Logically, the increment can be viewed as:

~~~text
old  = read counter
next = old + 1
write counter = next
~~~

Two threads can interleave:

~~~text
initial counter = 0
Thread A                         Thread B
--------                         --------
read counter => 0
                                 read counter => 0
compute 1
                                 compute 1
write 1
                                 write 1
final = 1 instead of 2
~~~

A `volatile` declaration specifies the visibility and ordering of each individual volatile access, but **does not combine read + add + write into a single uninterruptible unit**. To increment correctly, you can use `synchronized`, `AtomicInteger.incrementAndGet`, or an atomic update via `VarHandle`.

Example of CAS (*compare-and-set*) on an integer variable:

~~~text
CAS(counter, expected=0, newValue=1)
           |
           +--- is counter currently 0? --- Yes ---> write 1, return true
                                         |
                                         No ---> keep unchanged, return false
~~~

Checking the witness and the conditional write are performed **atomically on a single target memory location**. No thread can interleave right between the check and the write of the same CAS. However, CAS **is not a transaction for an entire object or multiple variables**.

## 2. VarHandle references a variable and its coordinates

A `VarHandle` has a value type (**variable type** `T`) and a list of coordinate types (**coordinate types** `CT1,...,CTn`). The same handle can access a group of variables of the same shape, depending on the specific coordinates passed at invocation time.

| Case | Creating the handle | Coordinates | `compareAndSet` type |
| --- | --- | --- | --- |
| Instance field `Holder.number` of type `int` | `lookup.findVarHandle(Holder.class,"number",int.class)` | `Holder` instance | `(Holder,int,int)boolean` |
| Static field `Metrics.total` of type `int` | `lookup.findStaticVarHandle(Metrics.class,"total",int.class)` | None | `(int,int)boolean` |
| Element of `int[]` | `MethodHandles.arrayElementVarHandle(int[].class)` | `int[]`, `int` index | `(int[],int,int,int)boolean` |
| Instance field `Slot.value` of type `String` | `lookup.findVarHandle(Slot.class,"value",String.class)` | `Slot` instance | `(Slot,String,String)boolean` |

Main access mode signatures:

~~~text
getVolatile:          (CT1,...,CTn) -> T
setVolatile:          (CT1,...,CTn,T newValue) -> void
compareAndSet:        (CT1,...,CTn,T expected,T newValue) -> boolean
compareAndExchange:   (CT1,...,CTn,T expected,T newValue) -> T
weakCompareAndSet:    (CT1,...,CTn,T expected,T newValue) -> boolean
getAndSet:            (CT1,...,CTn,T newValue) -> T
getAndAdd:            (CT1,...,CTn,T delta) -> T
getAndBitwiseOr:      (CT1,...,CTn,T mask) -> T
~~~

VarHandle access mode methods are **signature-polymorphic**: the JavaDoc displays `Object...`, but the JVM checks the symbolic call-site descriptor against the actual access-mode type. This means **the arguments and return type at the call site must match**, including the receiver, array index, expected, newValue, and an appropriate return-type cast.

You can inspect types using `varType()`, `coordinateTypes()`, and `accessModeType(VarHandle.AccessMode.COMPARE_AND_SET)`. To check whether a mode is supported, use `isAccessModeSupported(...)`. These metadata APIs do not create transactions or grant access to fields that the caller is not permitted to look up.

## 3. How `compareAndSet` and `compareAndExchange` differ in their results

Both are **atomic conditional updates**: if the witness (the value read atomically from the variable) equals expected, write the new value; otherwise, do not write. For `int`, equality compares numeric values. For references, it uses identity `==`, not `equals`.

| Access mode | When expected matches | When expected does not match | Returns |
| --- | --- | --- | --- |
| `compareAndSet` | Writes new value | Does not write | `true` / `false` |
| `compareAndExchange` | Writes new value | Does not write | **Old witness**, i.e., the value read at the time of comparison |
| `compareAndExchangeAcquire` | Writes new value with Acquire memory ordering | Does not write | Witness |
| `compareAndExchangeRelease` | Writes new value with Release memory ordering | Does not write | Witness |

**Common point of confusion:** `compareAndExchange` **does not** return `newValue`. On success, it returns a witness equal to expected; on failure, it returns a witness different from expected. The return value only reflects that atomic observation. Another thread may update the variable immediately afterward, so the witness must not be treated as an immutable snapshot of the future.

### Example 1: Boolean CAS and exchange witness

Create the file **`CasCompareDemo.java`**:

~~~java
import java.lang.invoke.*;

public class CasCompareDemo {
    static class Holder {
        volatile int number;
    }

    public static void main(String[] args) throws Exception {
        VarHandle vh = MethodHandles.lookup().findVarHandle(
            Holder.class, "number", int.class
        );
        Holder holder = new Holder();

        System.out.println("type=" + vh.varType().getSimpleName());
        System.out.println("cas1=" + vh.compareAndSet(holder, 0, 5));
        System.out.println("casFail=" + vh.compareAndSet(holder, 0, 9));

        System.out.println(
            "exchangeFail=" + (int) vh.compareAndExchange(holder, 0, 9)
        );
        System.out.println("afterFail=" + (int) vh.getVolatile(holder));

        System.out.println(
            "exchangeSuccess=" + (int) vh.compareAndExchange(holder, 5, 8)
        );
        System.out.println("final=" + (int) vh.getVolatile(holder));

        System.out.println("casType=" + vh.accessModeType(
            VarHandle.AccessMode.COMPARE_AND_SET
        ));
    }
}
~~~

~~~sh
javac --release 17 CasCompareDemo.java
java CasCompareDemo
~~~

**Stdout:**

~~~text
type=int
cas1=true
casFail=false
exchangeFail=5
afterFail=5
exchangeSuccess=5
final=8
casType=(Holder,int,int)boolean
~~~

Step-by-step explanation:

1. `Holder.number` initializes to 0. `compareAndSet(holder,0,5)` succeeds and writes 5, so it returns `true`.
2. CAS with expected 0, new 9 fails because the current value is 5; returns `false`.
3. `compareAndExchange(holder,0,9)` also does not write, but **returns 5**, the actual witness. `getVolatile` afterward still sees 5 in this single-threaded example.
4. `compareAndExchange(holder,5,8)` writes 8, but returns **5**, the value before the write. Reading again yields 8.
5. `accessModeType` prints the signature `(Holder,int,int)boolean`: the instance receiver comes before expected and new value.

In concurrent problems, `compareAndSet` is usually sufficient when only a boolean success result is needed. `compareAndExchange` is useful when you want to know the witness from a failed attempt to derive a new expected value; it does not retry automatically.

## 4. Unconditional updates: `getAndSet`, `getAndAdd`, and bitwise RMW

If modifying the variable falls into a built-in category, you can use an atomic update **without writing a CAS loop yourself**:

| Access mode | Value after update | Return value |
| --- | --- | --- |
| `getAndSet(new)` | `new` | `old` |
| `getAndAdd(delta)` | `old + delta` | `old` |
| `getAndBitwiseOr(mask)` | `old \| mask` | `old` |
| `getAndBitwiseAnd(mask)` | `old & mask` | `old` |
| `getAndBitwiseXor(mask)` | `old ^ mask` | `old` |

In addition to the default modes, there are `getAndSetAcquire/Release`, `getAndAddAcquire/Release`, and `getAndBitwiseOr/And/XorAcquire/Release` variants with different memory orderings. The modes remain atomic on the target variable, but **support depends on the variable's type**. For example, there is no `getAndAdd` for `String` concatenation; bitwise updates apply to appropriate integral/boolean types.

### Example 2: static fields, counters, bit flags, and booleans

Save **`AtomicOpsDemo.java`**:

~~~java
import java.lang.invoke.*;

public class AtomicOpsDemo {
    static volatile int counter;
    static volatile int flags;
    static volatile boolean ready;

    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        VarHandle count = lookup.findStaticVarHandle(
            AtomicOpsDemo.class, "counter", int.class
        );
        VarHandle bits = lookup.findStaticVarHandle(
            AtomicOpsDemo.class, "flags", int.class
        );
        VarHandle state = lookup.findStaticVarHandle(
            AtomicOpsDemo.class, "ready", boolean.class
        );

        System.out.println("countOld=" + (int) count.getAndAdd(3));
        System.out.println("countNow=" + (int) count.getVolatile());

        System.out.println("setOld=" + (int) count.getAndSet(10));
        System.out.println("setNow=" + (int) count.getVolatile());

        System.out.println(
            "orOld=" + (int) bits.getAndBitwiseOr(0b0101)
        );
        System.out.println(
            "andOld=" + (int) bits.getAndBitwiseAnd(0b0011)
        );
        System.out.println(
            "xorOld=" + (int) bits.getAndBitwiseXor(0b0011)
        );
        System.out.println("bitsNow=" + (int) bits.getVolatile());

        System.out.println(
            "readyOld=" + (boolean) state.getAndBitwiseOr(true)
        );
        System.out.println("readyNow=" + (boolean) state.getVolatile());
    }
}
~~~

~~~sh
javac --release 17 AtomicOpsDemo.java
java AtomicOpsDemo
~~~

~~~text
countOld=0
countNow=3
setOld=3
setNow=10
orOld=0
andOld=5
xorOld=1
bitsNow=2
readyOld=false
readyNow=true
~~~

Flags: starts at 0; OR `0101` produces 5 and returns 0; AND `0011` produces 1 and returns 5; XOR `0011` produces 2 and returns 1. `ready` uses logical OR with boolean. All three fields are `static`, so **no receiver is passed**.

**`getAndAdd` returns old, not new.** `AtomicInteger.addAndGet` is a different API that returns new. If multiple threads are updating, a subsequent read right after the RMW may already see another update; the old value returned by the operation itself is the definitive information for that RMW.

Similarly, an integer addition can overflow according to Java numeric type rules. Atomicity does not automatically add range checks, balance limits, or business rules.

## 5. CAS on references uses `==`, does not call `equals`

For a VarHandle to a reference field, the condition that witness equals expected means **the same object**, not two objects with equivalent contents. This is an important property when storing immutable state, linked nodes, a reference cache, or a global snapshot.

### Example 3: Equal String contents, but CAS fails

Save **`ReferenceIdentityDemo.java`**:

~~~java
import java.lang.invoke.*;

public class ReferenceIdentityDemo {
    static class Slot {
        volatile String text;
    }

    public static void main(String[] args) throws Exception {
        VarHandle text = MethodHandles.lookup().findVarHandle(
            Slot.class, "text", String.class
        );
        Slot slot = new Slot();

        String original = new String("token");
        String equalButDifferent = new String("token");
        slot.text = original;

        System.out.println("equals=" +
            original.equals(equalButDifferent));
        System.out.println("sameRef=" +
            (original == equalButDifferent));

        System.out.println("casEqualContents=" + text.compareAndSet(
            slot, equalButDifferent, "changed"
        ));

        String witness = (String) text.compareAndExchange(
            slot, original, "changed"
        );
        System.out.println("witnessWasOriginal=" + (witness == original));
        System.out.println("now=" + (String) text.getVolatile(slot));
    }
}
~~~

~~~sh
javac --release 17 ReferenceIdentityDemo.java
java ReferenceIdentityDemo
~~~

~~~text
equals=true
sameRef=false
casEqualContents=false
witnessWasOriginal=true
now=changed
~~~

Two `new String("token")` calls create two distinct instances even though `equals` returns true. CAS with the different instance does not match expected. Exchange with the exact `original` reference succeeds; the witness equals the original object. You should not test identity examples using two string literals and claim they are different: interning can share the same reference.

**Note:** atomically swapping the reference in a field **does not** make mutable data inside that object automatically thread-safe. VarHandle protects access to the **referenced variable**, not every modification on the object that the variable holds.

## 6. Memory ordering: volatile, acquire, release, plain, and opaque

An operation can guarantee **atomicity on a single variable** while having different constraints on the order in which other variables are observed across threads. Java SE 17 defines several access modes with memory effects:

| Level | Examples | Meaning to understand |
| --- | --- | --- |
| Plain | `get`, `set` | Access similar to a non-volatile field; carries no cross-thread synchronization such as acquire/release |
| Opaque | `getOpaque`, `setOpaque` | Bitwise atomic and coherent order for the same variable; few ordering constraints with other data |
| Acquire | `getAcquire`, `...Acquire` | Loads/stores after acquire must not be reordered before acquire under the memory contract |
| Release | `setRelease`, `...Release` | Loads/stores before release must not be reordered after release under the contract |
| Volatile | `getVolatile`, `setVolatile`, `compareAndSet`, `compareAndExchange`, and normal RMW | Volatile read/write effects, stronger than individual acquire/release in common protocols |

For atomic updates:

- `compareAndSet` and `compareAndExchange` have `getVolatile` read and `setVolatile` write effects when the condition is met.
- `compareAndExchangeAcquire` reads the witness with `getAcquire` and writes the new value with `set` (plain).
- `compareAndExchangeRelease` reads the witness with `get` (plain) and writes the new value with `setRelease`.
- `getAndSetAcquire`, `getAndAddAcquire`, and bitwise `...Acquire` apply read-acquire + write-plain.
- `getAndSetRelease`, `getAndAddRelease`, and bitwise `...Release` apply read-plain + write-release.

A weaker mode name **does not mean the update loses atomicity**. However, one thread publishing data with release and another thread consuming with acquire must participate in **the same synchronization protocol**; replacing one side with plain arbitrarily can cause other data not to be visible in time.

Although the examples use `volatile` fields to make intent clear, VarHandle can use volatile/CAS access modes on fields not declared `volatile` when that mode is supported. However, mixing plain and volatile access paths without a consistent design is a source of data race/visibility risks. Only weaken memory ordering after proving correctness under the Java Memory Model.

## 7. `weakCompareAndSet*` may return a spurious false

Java 17 provides:

- `weakCompareAndSetPlain`: plain read/write.
- `weakCompareAndSet`: volatile read/write.
- `weakCompareAndSetAcquire`: acquire read, plain write.
- `weakCompareAndSetRelease`: plain read, release write.

They still perform an atomic CAS when they succeed, but **are allowed to fail spuriously** even when the witness matches expected. Therefore, you must not interpret every `false` from a weak CAS as proof that another thread changed the variable. Strong `compareAndSet` does not have this spurious failure path per the specification; `false` means the witness did not equal expected.

A **snippet** using the variable `VarHandle VALUE` and object `counter` (defined in Example 4 below) to increment a number with weak CAS:

~~~java
for (;;) {
    int old = (int) VALUE.getVolatile(counter);
    int next = old + 1;

    if (VALUE.weakCompareAndSet(counter, old, next)) {
        break;
    }

    Thread.onSpinWait(); // just a CPU hint
}
~~~

The loop re-reads the value after each failure to recompute next. It does not by itself guarantee completion time or a bounded number of attempts. `Thread.onSpinWait()` is a hint that helps optimize certain spin loops, not a synchronization primitive; under high contention, consider backoff or another solution.

With weak CAS Plain, do not mistakenly assume it carries volatile memory semantics just because it has "CAS" in its name. Choose the suffix based on your algorithm's visibility and ordering requirements.

## 8. CAS loops and `getAndAdd` in multithreaded applications

When an update depends on the old value, a loop is commonly used:

~~~text
old = read variable
next = f(old)
try CAS(expected=old, new=next)
  success: done
  failure: re-read and recompute
~~~

Thanks to CAS, the write only occurs if the data has not changed since reading expected (according to the exact comparison at the time of CAS). If you use `setVolatile(old + 1)` after a read, the check and write **are not an atomic unit**.

### Example 4: Four threads updating the same two counters

Save **`CasConcurrencyDemo.java`**:

~~~java
import java.lang.invoke.*;

public class CasConcurrencyDemo {
    static class Counter {
        volatile int value;
    }

    static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup().findVarHandle(
                Counter.class, "value", int.class
            );
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter cas = new Counter();
        Counter rmw = new Counter();
        Thread[] threads = new Thread[4];

        for (int t = 0; t < threads.length; t++) {
            threads[t] = new Thread(() -> {
                for (int i = 0; i < 10_000; i++) {
                    while (true) {
                        int old = (int) VALUE.getVolatile(cas);

                        if (VALUE.compareAndSet(cas, old, old + 1)) {
                            break;
                        }
                        Thread.onSpinWait();
                    }

                    VALUE.getAndAdd(rmw, 1);
                }
            });
            threads[t].start();
        }

        for (Thread thread : threads) {
            thread.join();
        }

        System.out.println("cas=" + (int) VALUE.getVolatile(cas));
        System.out.println("getAndAdd=" + (int) VALUE.getVolatile(rmw));
    }
}
~~~

~~~sh
javac --release 17 CasConcurrencyDemo.java
java CasConcurrencyDemo
~~~

~~~text
cas=40000
getAndAdd=40000
~~~

Each thread updates each counter 10,000 times. After `join()`, the total is 40,000 if all threads finish normally. `getAndAdd(rmw,1)` is convenient when the update rule is simply addition; a CAS loop is appropriate when `next=f(old)` is a custom function.

If you want to use the witness from `compareAndExchange` instead of calling `getVolatile` again after each failed CAS, you can write a **snippet that depends on VALUE and counter from the example above**:

~~~java
int seen = (int) VALUE.getVolatile(counter);
for (;;) {
    int witness = (int) VALUE.compareAndExchange(
        counter, seen, seen + 1
    );
    if (witness == seen) {
        break; // update succeeded
    }
    seen = witness; // observed value; retry
}
~~~

This snippet is not standalone; to use it in an application, place it inside a method that has `counter` and `VALUE` of the right types. Another thread can still modify the variable after the witness is returned, so **the next attempt must always check with CAS**, never assuming the witness is still the current value.

**Side effects:** the computation `f(old)` inside a retry loop may run multiple times. Avoid sending notifications, charging money, recording transactions, or performing side effects that cannot be safely repeated inside the computation before CAS is confirmed. A single-variable CAS also does not turn an entire business operation into a transaction.

## 9. Unsupported access modes and type errors

`VarHandle` only provides modes supported by the corresponding variable kind and type:

- A `final` field is treated as read-only through VarHandle; write, CAS, and RMW modes are not supported.
- `getAndAdd` on `String` is not string concatenation and is not supported.
- Bitwise modes are for appropriate integral/boolean types, not arbitrary updates on objects.
- An access mode may be valid while the call still has the wrong **signature**: missing instance receiver, missing array index, passing `long` when the field is `int`, or casting the return type incorrectly.

### Example 5: final field, String field, array element, and wrong type

Save **`ModesAndArrayDemo.java`**:

~~~java
import java.lang.invoke.*;

public class ModesAndArrayDemo {
    static class Data {
        final int id = 7;
        volatile String label = "start";
        volatile int counter = 7;
    }

    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        VarHandle id = lookup.findVarHandle(
            Data.class, "id", int.class
        );
        VarHandle label = lookup.findVarHandle(
            Data.class, "label", String.class
        );
        VarHandle count = lookup.findVarHandle(
            Data.class, "counter", int.class
        );
        Data data = new Data();

        System.out.println("finalCasSupported=" +
            id.isAccessModeSupported(
                VarHandle.AccessMode.COMPARE_AND_SET
            ));

        try {
            boolean ignored = id.compareAndSet(data, 7, 8);
        } catch (UnsupportedOperationException ex) {
            System.out.println(
                "finalCas=" + ex.getClass().getSimpleName()
            );
        }

        System.out.println("stringAddSupported=" +
            label.isAccessModeSupported(
                VarHandle.AccessMode.GET_AND_ADD
            ));

        try {
            String ignored = (String) label.getAndAdd(data, "x");
        } catch (UnsupportedOperationException ex) {
            System.out.println(
                "stringAdd=" + ex.getClass().getSimpleName()
            );
        }

        int[] values = { 10 };
        VarHandle element =
            MethodHandles.arrayElementVarHandle(int[].class);

        System.out.println("arrayCas=" +
            element.compareAndSet(values, 0, 10, 12));
        System.out.println("arrayOld=" +
            (int) element.getAndAdd(values, 0, 5));
        System.out.println("arrayNow=" + values[0]);

        try {
            boolean ignored = count.compareAndSet(data, 7L, 8L);
        } catch (WrongMethodTypeException ex) {
            System.out.println(
                "wrongType=" + ex.getClass().getSimpleName()
            );
        }
    }
}
~~~

~~~sh
javac --release 17 ModesAndArrayDemo.java
java ModesAndArrayDemo
~~~

~~~text
finalCasSupported=false
finalCas=UnsupportedOperationException
stringAddSupported=false
stringAdd=UnsupportedOperationException
arrayCas=true
arrayOld=12
arrayNow=17
wrongType=WrongMethodTypeException
~~~

`finalCasSupported=false` because the `id` field is final; `stringAddSupported=false` because `String` does not support numeric addition. The array `{10}` changes from 10 to 12 via CAS, and `getAndAdd(values,0,5)` returns old 12 and updates it to 17. For the `int` field `counter`, passing `long` expected/new values makes the call-site descriptor wrong, so `WrongMethodTypeException` is thrown.

**Specifically:** when using a handle that both **does not support the mode** and is called with the wrong signature, `UnsupportedOperationException` may appear before the type error. To test wrong type specifically, the example calls it on the writable `counter` field.

### Distinguishing exceptions to fix the root cause

| Exception | Common cause | What to check |
| --- | --- | --- |
| `NoSuchFieldException` | Lookup could not find the field/name/type | `findVarHandle`, field declaration, type |
| `IllegalAccessException` | Lookup lacks permission | Declaring type, package, module, `Lookup` mode |
| `UnsupportedOperationException` | Access mode unsupported on the VarHandle | `isAccessModeSupported(...)`, `final`, type |
| `WrongMethodTypeException` | Call-site descriptor does not match access-mode type | Coordinates, argument count, types, return cast |
| `ClassCastException` | A reference cast failed | Actual object type and descriptor |
| `NullPointerException` | Receiver/array coordinate is `null` or inappropriate `null` usage | Check inputs |
| `ArrayIndexOutOfBoundsException` | Invalid array index | Index coordinate |
| `ExceptionInInitializerError` | Class initialization failed when building handle in static initializer | Root cause |

Do not solve type errors by calling `setAccessible(true)` or defaulting to changing the variable to `Object`. Lookup permissions, mode support, and call-site types are independent conditions.

## 10. The ABA problem, multiple variables, and progress

### ABA: expected returns after having changed

Suppose thread A reads reference `A`. Meanwhile, thread B changes the reference to `B` and then changes it back to `A`:

~~~text
A reads expected=A
B writes B
B writes A
A compareAndSet(expected=A,new=C) => succeeds
~~~

CAS succeeds because the witness **is indeed A** at the time of comparison, but it **does not prove the state never changed**. This is the **ABA problem**. `compareAndExchange` does not solve ABA on its own either, because the witness can still equal expected after the A→B→A sequence.

If the algorithm needs to distinguish generations of the same reference, you can use `AtomicStampedReference`, or store an **immutable state containing both value and version** in a single reference and CAS-replace the entire snapshot. Simply incrementing a version in another field while CAS-ing the original field **does not automatically make the pair of fields an atomic unit**.

### Atomic on one field does not create a multi-field transaction

Transferring money from account A to B using two calls `getAndAdd(A,-amount)` and `getAndAdd(B,+amount)` is not atomic as a transaction. A third thread can observe the moment after subtraction but before addition. A transaction/locking mechanism or a combined-state-and-CAS model is needed.

### CAS does not guarantee every thread always makes fast progress

A CAS loop can be very efficient under low contention, but if threads continuously invalidate each other's expected values, retries repeat many times. **Do not infer wait-freedom** or a fixed completion time guarantee just because CAS is used. `Thread.onSpinWait()` does not create a progress guarantee. For extremely hot counters, `LongAdder` can reduce contention in some workloads, though it has different read semantics from `AtomicLong`; evaluate based on snapshot accuracy requirements.

## 11. Should you choose VarHandle or Atomic classes?

| Need | Suitable approach | Reason |
| --- | --- | --- |
| Need CAS with boolean result | `VarHandle.compareAndSet` | Simple, strong CAS |
| Need old witness for retry | `VarHandle.compareAndExchange` | Returns the actual value at comparison |
| Need unconditional replace and old value | `getAndSet` | Atomic exchange |
| Need increment/decrement | `getAndAdd` or `AtomicInteger` | Avoids writing a manual CAS loop |
| Need to update bit flags | `getAndBitwiseOr/And/Xor` | Atomic bitwise RMW |
| Need specific memory ordering | `Acquire/Release` variants | Fits proven synchronization protocols |
| Just need an application counter | `AtomicInteger`/`AtomicLong` | Direct API, often simpler than VarHandle |
| Many threads updating a very hot counter | Consider `LongAdder` | Can reduce contention, changes snapshot semantics |
| Must update an arbitrary function of old | CAS loop or `AtomicInteger.updateAndGet` | Proper retry; function must avoid side effects |
| Need to update multiple fields atomically like a transaction | Lock/transaction or combined state | A single CAS does not protect multiple variables |

**Note on VarHandle:** an immutable handle describes a field rather than owning the field's value. Example 4 uses the same `VALUE` on two instances `cas` and `rmw`: they are two distinct locations thanks to the receiver. When using libraries/concurrent abstractions, prefer clear high-level APIs rather than repeating lookup/error-handling boilerplate everywhere.

## 12. Self-check workflow and common mistakes

Before putting a VarHandle updater into concurrent code:

1. Check **variable and coordinates**: instance/static/array, `varType()`, `coordinateTypes()`; arrays require an index, static fields require no receiver.
2. Check **lookup access**: does `Lookup` have permission to access the declaring field and satisfy module constraints?
3. Check **access mode support**: `isAccessModeSupported(...)` before using type-dependent modes or `final` fields.
4. Check **call-site signature**: exact arguments and return type matching `accessModeType(...)`; do not confuse `long`/`int` or omit the receiver.
5. Distinguish **results**: `compareAndSet` is boolean; `compareAndExchange` is witness; `getAnd*` returns old.
6. Determine **memory ordering**: volatile/acquire/release/plain; ensure the entire publish/read protocol fits the Java Memory Model.
7. If **retrying**, recompute from the new old value, avoid repeated side effects, and evaluate contention/starvation.
8. Check **ABA** and multi-variable invariants; choose stamps/versions or another synchronization mechanism if needed.
9. For single-threaded tests, check both passing and failing CAS branches, return values, and post-operation state. For multithreaded tests, synchronize completion with `join()` and then verify the total. Repeated tests/stress runs are helpful but are not a formal proof of race freedom.

Common misconceptions:

- "`volatile counter++` is already atomic" — false.
- "`compareAndSet` returns the old number" — false: it returns a boolean.
- "`compareAndExchange` returns the new number" — false: it returns the witness.
- "Two `equals` objects mean reference CAS will definitely succeed" — false: CAS compares with `==`.
- "`weakCompareAndSetPlain` returning false proves the data changed" — false: it can fail spuriously.
- "`getAndAdd` returns the sum after adding" — false: it returns the old value.
- "Having a VarHandle for a `final` field means you can CAS it" — false: write/RMW access modes are unsupported.
- "Atomic RMW on one field makes the whole object thread-safe" — false.
- "CAS cannot suffer starvation because it doesn't use locks" — false.
- "Witness matching expected proves no change ever occurred" — false if ABA occurred.
- "Acquire/Release means non-atomic" — false; the atomic update is still atomic, but with different ordering effects.
- "Call VarHandle like a normal `Object[]` varargs method" — false; access modes are signature-polymorphic.

## 13. Self-practice questions

**Question 1.** With `int state=10`, calling `compareAndSet(expected=9,new=20)` returns what, and what is `state`?

**Answer:** Returns `false`, and `state` remains 10.

**Question 2.** What does `compareAndExchange(expected=9,new=20)` on state 10 return? What if expected=10?

**Answer:** For expected 9, it returns witness 10 and does not write; for expected 10, it returns witness **still 10** but writes `state` to 20.

**Question 3.** What does `getAndAdd(4)` on state 7 return?

**Answer:** Returns 7; `state` after the update is 11.

**Question 4.** What old/new result does `getAndBitwiseOr(0b0100)` on flags `0b0001` produce?

**Answer:** Returns old 1, and flags becomes `0b0101` (5).

**Question 5.** Two references have equal `equals` contents but are two different objects: will CAS using the second object as expected succeed if the field points to the first object?

**Answer:** No; `==` identity differs.

**Question 6.** Why must a weak CAS retry and re-check the value?

**Answer:** It can fail spuriously, and another thread may also update the variable between attempts. Each iteration must re-read/recompute the appropriate expected value.

**Question 7.** For a VarHandle of `int[]`, what arguments does `compareAndSet` require?

**Answer:** `int[] array`, `int index`, `int expected`, `int newValue`; returns boolean.

**Question 8.** Are two `getAndAdd` calls on two fields a single transaction?

**Answer:** No. Each call is atomic on its own; synchronization is needed for invariants spanning multiple fields.

**Question 9.** Why is `compareAndExchange` returning a witness different from expected useful when retrying?

**Answer:** The caller gets an observed value to use as the next expected value without necessarily re-reading immediately. However, another thread can still change it afterward, so CAS must still check.

**Question 10.** Do `isAccessModeSupported(COMPARE_AND_SET)==false` and `WrongMethodTypeException` indicate the same problem?

**Answer:** No. One means the mode is not supported, while the other means the call-site descriptor does not match the mode/handle.

## 14. Java 17 references

- `java.lang.invoke.VarHandle` — atomic access modes and memory ordering: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html
- `VarHandle.AccessMode`, `accessModeType`, `isAccessModeSupported`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.AccessMode.html
- `MethodHandles.Lookup.findVarHandle`, `findStaticVarHandle`, and `arrayElementVarHandle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- `java.util.concurrent.atomic.AtomicInteger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- `java.util.concurrent.atomic.AtomicStampedReference`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicStampedReference.html
- JLS Java 17, Chapter 17 — Threads and Locks/Memory Model: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html

**Remember:** `compareAndSet` returns boolean, `compareAndExchange` returns witness, and `getAnd*` returns old. They solve atomicity on **a single variable** and offer several memory ordering options. To use them correctly, you must understand coordinates, variable types, access mode support, reference identity, retries, ABA, and the atomicity boundaries of the entire system.