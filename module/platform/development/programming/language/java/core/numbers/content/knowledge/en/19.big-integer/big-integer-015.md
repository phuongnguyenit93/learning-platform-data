# Resource Limits of `BigInteger` Despite Having No Fixed Width Like `long`

## 1. Goal: Arbitrary-Precision Integers Do Not Mean Infinite Resources

`java.math.BigInteger` is the class representing **arbitrary-precision signed integers**. Unlike 64-bit fixed `long`, `BigInteger` can hold integers with hundreds, thousands, or huge numbers of digits without **wrapping modulo 2⁶⁴** like primitive operators.

However, "arbitrary" **does not mean "infinite"**. Every Java program still runs inside a JVM with finite RAM, heap, CPU, time, thread resources, and implementation limits. An oversized `BigInteger` operation can:

- Require memory for objects, data arrays, and intermediate results.
- Take substantial CPU time to add, multiply, divide, exponentiate, or convert to strings.
- Fail due to implementation data-size limits, or throw `OutOfMemoryError`.
- Monopolize shared resources, slowing down or starving other service requests.
- Pose risks from untrusted data, especially unusually long input strings or user-controlled exponents.

This lesson helps you distinguish **data type limits** from **application resource budgets**, estimate magnitude using `bitLength()`, guard fast-growing operations, and write safe Java 17+ examples.

## 2. `long` Is Fixed at 64 Bits, While `BigInteger` Grows with Value

| Property | `long` | `BigInteger` |
| --- | --- | --- |
| Form | 64-bit signed primitive | Immutable object class |
| Value range | `Long.MIN_VALUE` to `Long.MAX_VALUE` | Not locked to 64-bit width; bounded by implementation and resources |
| Overflow on ordinary add/multiply | Can wrap modulo 2⁶⁴ | Does not wrap at `long` bounds |
| Integer precision | Exact within `long` range | Exact for integers the JVM can represent/compute |
| Memory per value | Fixed primitive size | Depends on magnitude, object layout, and implementation |
| Result length | At most 64-bit primitive | Can grow across operations |
| When capacity is insufficient | Primitive arithmetic overflow | Can run out of memory, hit implementation limits, or exceed app budget |

Comparison example:

~~~java
long primitive = Long.MAX_VALUE;
System.out.println(primitive + 1); // -9223372036854775808

BigInteger extended = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE);
System.out.println(extended);      // 9223372036854775808
~~~

This is an illustrative snippet inside a method with `import java.math.BigInteger`, not a standalone program.

`BigInteger` loses no digits in the addition above. Still, the result value must be represented and stored on the heap. If the application keeps producing oversized results, it can still fail.

**Do not use `double` as a way to "avoid `long` overflow" when exact integers are needed.** `double` has 53 bits of significand precision, so many large integers cannot be represented exactly; `BigInteger` solves a completely different problem.

## 3. How Much Data Does `BigInteger` Store?

Mathematically, a positive integer `n` needs about:

\[
\text{bits}(n)=\lfloor\log_2(n)\rfloor+1,\qquad n>0
\]

bits to represent its magnitude in binary. For 0, the magnitude length is defined as 0 bits.

Java provides:

~~~java
BigInteger n = BigInteger.ONE.shiftLeft(1000);

System.out.println(n.bitLength());         // 1001
System.out.println(n.toString().length()); // 302
~~~

`n = 2¹⁰⁰⁰`, so its highest bit is at position 1000 (zero-based), giving **1001 bits**. Printed in decimal, `2¹⁰⁰⁰` has **302 digits**.

### Estimating Raw Bit Storage

A number with `b` magnitude bits needs at least about `ceil(b / 8)` bytes for raw bit content, before overhead:

\[
\text{rawMagnitudeBytes}\approx \left\lceil\frac{b}{8}\right\rceil.
\]

However, **this is not the actual heap size of `BigInteger`**. The JVM also has object headers, reference fields, sign metadata, word arrays, alignment, and temporary objects. Actual size depends on JDK version, architecture, GC, and implementation.

`BigInteger.toByteArray()` is **also not a heap-measurement tool**. This API allocates a **signed two's-complement** byte array, which may include an extra sign bit/byte and creates a copy.

~~~java
BigInteger value = BigInteger.ONE.shiftLeft(1000);
System.out.println(value.toByteArray().length); // 126
~~~

The example above has 126 bytes, matching the byte encoding of positive `2¹⁰⁰⁰`. It **does not** mean the `BigInteger` object occupies only 126 bytes on the heap.

### For Negative Numbers, Be Careful with `bitLength()`

`BigInteger.bitLength()` is defined using two's complement excluding the sign bit, so it does not always match the bit length of the **absolute magnitude** for negative numbers. If the goal is controlling operand size by magnitude, use:

~~~java
int magnitudeBits = value.abs().bitLength();
~~~

`BigInteger.ZERO.bitLength()` is 0. `abs()` preserves exact integer semantics; never narrow to `long` to take absolute value, as that can lose data or hit `Long.MIN_VALUE`.

## 4. "Not Fixed at 64 Bits" Does Not Mean "No Implementation Limits"

The `BigInteger` contract guarantees arbitrary-precision integer operations **within the range supported by the implementation**. Java API documentation states the type's constraints and warns that operations producing results outside the supported range may throw `ArithmeticException`.

Beyond implementation limits, independent limits also apply:

- **Array and object sizes:** a Java array cannot have infinite length; `BigInteger` capacity depends on in-memory data structures.
- **Heap limit:** even if theoretically representable, the JVM may lack allocatable heap space.
- **Temporary resources:** multiplication/division/parsing may require larger buffers than the final result size.
- **CPU and time:** even with sufficient RAM, computing or string-converting results can exceed request timeouts.
- **Application-imposed limits:** input size, output digit count, exponents, request deadlines, tenant quotas, container memory/CPU budgets.

Do not write in business documentation a universal hard limit like **"maximum BigInteger is always X bits."** Specific capacity can depend on Java version, implementation, and runtime environment; applications should enforce smaller, controllable, testable budgets of their own.

**Data type limits** and **system safety limits** are two separate concerns. A machine might hold a `BigInteger` with millions of bits, yet letting every web request build such a number can still be unsafe.

## 5. Result Size Grows Across Operations

The danger lies not only in inputs; **intermediate results can grow very rapidly**.

### Addition and Subtraction

When adding two numbers of magnitude up to about `b` bits, the result can take around `b + 1` bits. With arbitrary signs, cancellation can occur, yet you should not rely on cancellation to omit limits.

~~~java
BigInteger a = BigInteger.ONE.shiftLeft(100);
BigInteger b = a;
BigInteger sum = a.add(b);

System.out.println(a.bitLength());   // 101
System.out.println(sum.bitLength()); // 102
~~~

### Multiplication

Two positive numbers of about `m` and `n` bits produce a product with at most roughly `m + n` bits (when nonzero). For example, squaring a number can **nearly double the required bit count**.

~~~java
BigInteger a = BigInteger.ONE.shiftLeft(1000);
BigInteger square = a.multiply(a);

System.out.println(a.bitLength());      // 1001
System.out.println(square.bitLength()); // 2001
~~~

Alongside result size, there are computation costs and temporary arrays. Implementations may switch multiplication algorithms based on operand size; never claim every multiplication has one fixed complexity across all JDKs.

### Exponentiation

`BigInteger.pow(int exponent)` can make results grow very quickly with the exponent. For `base > 1`:

\[
\text{bits}(base^e) \approx e\log_2(base)+1.
\]

~~~java
BigInteger power = BigInteger.TWO.pow(1000);
System.out.println(power.bitLength()); // 1001
~~~

If the exponent is user-controlled and unchecked against a budget, a tiny request like `"base=2&exponent=1000000000"` can demand enormous output data. **Do not run the calculation just to "see if it fits"**; estimate size beforehand.

### Repeated Squaring Causes Especially Fast Growth

~~~java
BigInteger n = BigInteger.TWO;
for (int i = 0; i < 10; i++) {
    n = n.multiply(n);
}
System.out.println(n.bitLength()); // 1025
~~~

After 10 squarings, `n = 2¹⁰²⁴`, taking 1025 bits. Increasing the squaring count just a bit more grows bit length **exponentially in the number of steps**. Thus an innocent-looking short loop can create huge load without a size-based stop condition.

## 6. Not Just Arithmetic: Parsing and `toString` Also Consume Resources

Creating `BigInteger` from a string:

~~~java
BigInteger n = new BigInteger("123456789012345678901234567890");
~~~

Short string syntax looks harmless. Yet for strings with millions of digits, the program must read, validate format, convert to binary representation, allocate memory, and handle errors. For untrusted input, unbounded parsing can become a service **availability** issue.

Likewise, `n.toString()` must generate a decimal representation:

~~~java
String decimal = n.toString();
~~~

A number with millions of bits can produce a huge decimal string. Writing that string to logs, sending it over HTTP, embedding it in JSON, or storing it in another system consumes extra memory, CPU, bandwidth, and storage.

### Estimating Decimal Digit Count

A positive integer with `b` bits typically has around:

\[
\text{decimalDigits}\approx b\log_{10}(2)\approx 0.30103b.
\]

This is an **estimate**, not an exact length check for all values. For instance, `2¹⁰⁰⁰` has 1001 bits and 302 decimal digits.

For data that must stay intact, do not call `toString()` on a huge `BigInteger` just to ask "is it big?" `abs().bitLength()` provides a far cheaper size signal than building the entire string.

### Extremely Long Input Can Cause Risk Before the Constructor Runs

If a system already loads an entire HTTP body or file into a gigantic `String` before checking length, it has **already allocated resources for the input**. Therefore, bound request bodies/fields right at the ingestion boundary, before string inspection, parsing, and computation. A bounded parser at the business layer is a second line of defense, not a replacement for gateway/server limits.

## 7. A Digit-Limited Parsing Function

For example, suppose a system accepts only ASCII decimal integers of at most **40 digits**, excluding a `+` or `-` sign. The code below needs no external libraries:

~~~java
static BigInteger parseLimitedDecimal(String text, int maxDigits) {
    if (text == null || maxDigits <= 0) {
        throw new IllegalArgumentException("Invalid input or limit");
    }

    int start = 0;
    if (!text.isEmpty()
            && (text.charAt(0) == '+' || text.charAt(0) == '-')) {
        start = 1;
    }

    int digits = text.length() - start;
    if (digits < 1 || digits > maxDigits) {
        throw new IllegalArgumentException("Too many or no digits");
    }

    for (int i = start; i < text.length(); i++) {
        char c = text.charAt(i);
        if (c < '0' || c > '9') {
            throw new IllegalArgumentException("ASCII decimal digits only");
        }
    }

    return new BigInteger(text);
}
~~~

This is a **method placed inside a class body**, requiring `import java.math.BigInteger;`, not a standalone runnable file.

Checking ASCII explicitly is intentional: `BigInteger(String)` can accept various Unicode digits supported by `Character.digit`, whereas this example protocol specifies **only ASCII 0–9**. Never allow a broader character set and accidentally describe it as "ASCII digits only."

Strengths of this function:

1. Checks `null`, digit count, and length **before** constructing `BigInteger`.
2. Allows a leading sign without counting it as a digit.
3. Uses a simple loop to validate format; no need to parse first and check size afterward.
4. Produces an exact value when input is valid.
5. Fails explicitly when policy is violated.

If strings come from users, you also need to bound **payload length before forming the `String`** as noted above. The limit 40 is only an example, not a mandatory `BigInteger` threshold.

## 8. Checking Bit Count Before Multiplication

For two nonzero numbers with magnitude bit lengths `aBits` and `bBits`, the product has **no more than `aBits + bBits` bits**. We can use this conservative upper bound to **fail fast** on multiplications risking a budget overrun.

~~~java
static BigInteger multiplyWithinBitBudget(
        BigInteger a, BigInteger b, int maxBits) {
    if (a == null || b == null || maxBits < 1) {
        throw new IllegalArgumentException("Invalid operands or budget");
    }
    if (a.signum() == 0 || b.signum() == 0) {
        return BigInteger.ZERO;
    }

    long upperBound = (long) a.abs().bitLength()
            + b.abs().bitLength();
    if (upperBound > maxBits) {
        throw new IllegalArgumentException("Result may exceed bit budget");
    }

    return a.multiply(b);
}
~~~

This is a **conservative limit**, not an exact prediction of the product's bit count. An actual product may fit within budget even when `upperBound` exceeds the threshold: in that case, the function **intentionally rejects** to avoid risk. If business rules cannot accept false rejections, apply a tighter analysis or raise the budget.

Because `bitLength()` returns `int`, the sum of the two lengths is widened to `long` first to prevent integer overflow when summing the bound. Never estimate using `a.toString().length()` and `b.toString().length()` when inputs can be gigantic: building strings is itself resource-intensive.

An upper bound does not replace real memory limits. A multiplication within bit budget can still require **intermediate arrays**, hit heap exhaustion, or impact CPU.

## 9. Checking the Exponent Before Calling `pow`

`BigInteger.pow(int exponent)` requires a non-negative integer exponent. If `exponent < 0`, the API throws `ArithmeticException`. If the exponent is huge, the result can require an enormous number of bits.

For nonzero `base` and positive exponent, a simple upper bound is:

\[
\text{resultBits}\le \text{abs(base).bitLength()}\times exponent.
\]

We use `long` to multiply the two size parameters:

~~~java
static BigInteger powWithinBitBudget(
        BigInteger base, int exponent, int maxBits) {
    if (base == null || exponent < 0 || maxBits < 1) {
        throw new IllegalArgumentException("Invalid power parameters");
    }
    if (exponent == 0) {
        return BigInteger.ONE;
    }
    if (base.signum() == 0) {
        return BigInteger.ZERO;
    }

    long upperBound = (long) base.abs().bitLength() * exponent;
    if (upperBound > maxBits) {
        throw new IllegalArgumentException("Power may exceed bit budget");
    }
    return base.pow(exponent);
}
~~~

This is also a **conservative bound**. For instance, if `base = 1` or `base = -1`, the result always has magnitude 1 for any exponent, yet the estimate above can reject when the exponent is huge. To optimize acceptance, `0`, `1`, and `-1` bases can be special-cased.

**Note on `0^0` in the Java API:** `BigInteger.pow(0)` returns `BigInteger.ONE` (even when `base` is 0); the code above follows that behavior. If a mathematical/application model treats `0^0` as invalid, enforce a separate business check.

Returning an enormous `BigInteger` from exponentiation is not always appropriate. If you only need `base^exponent mod modulus`, use the dedicated modular operation discussed in the next section.

## 10. Complete Resource-Bounded Java 17+ Example

Save to file `BigIntegerResourceDemo.java`:

~~~java
import java.math.BigInteger;

public class BigIntegerResourceDemo {
    private static final int MAX_DIGITS = 40;
    private static final int MAX_RESULT_BITS = 2048;

    static BigInteger parseLimitedDecimal(String text) {
        if (text == null) {
            throw new IllegalArgumentException("Missing number");
        }
        int start = 0;
        if (!text.isEmpty()
                && (text.charAt(0) == '+' || text.charAt(0) == '-')) {
            start = 1;
        }
        int digits = text.length() - start;
        if (digits < 1 || digits > MAX_DIGITS) {
            throw new IllegalArgumentException("Invalid digit count");
        }
        for (int i = start; i < text.length(); i++) {
            char c = text.charAt(i);
            if (c < '0' || c > '9') {
                throw new IllegalArgumentException("Not ASCII decimal");
            }
        }
        return new BigInteger(text);
    }

    static BigInteger multiplyBounded(BigInteger a, BigInteger b) {
        if (a == null || b == null) {
            throw new IllegalArgumentException("Missing operand");
        }
        if (a.signum() == 0 || b.signum() == 0) {
            return BigInteger.ZERO;
        }
        long upperBound = (long) a.abs().bitLength()
                + b.abs().bitLength();
        if (upperBound > MAX_RESULT_BITS) {
            throw new IllegalArgumentException("Product too large");
        }
        return a.multiply(b);
    }

    static BigInteger powBounded(BigInteger base, int exponent) {
        if (base == null || exponent < 0) {
            throw new IllegalArgumentException("Invalid exponent");
        }
        if (exponent == 0) {
            return BigInteger.ONE;
        }
        if (base.signum() == 0) {
            return BigInteger.ZERO;
        }
        long upperBound = (long) base.abs().bitLength() * exponent;
        if (upperBound > MAX_RESULT_BITS) {
            throw new IllegalArgumentException("Power too large");
        }
        return base.pow(exponent);
    }

    public static void main(String[] args) {
        BigInteger powerOfTwo = BigInteger.ONE.shiftLeft(1000);
        System.out.println("bits=" + powerOfTwo.bitLength());
        System.out.println("decimal digits=" + powerOfTwo.toString().length());
        System.out.println("byte array length=" +
                powerOfTwo.toByteArray().length);

        BigInteger parsed = parseLimitedDecimal("12345678901234567890");
        System.out.println("parsed=" + parsed);
        try {
            parsed.longValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("longValueExact=rejected");
        }

        System.out.println("square=" +
                multiplyBounded(BigInteger.valueOf(1234),
                        BigInteger.valueOf(1234)));
        System.out.println("two^10=" + powBounded(BigInteger.TWO, 10));
        System.out.println("zero bits=" + BigInteger.ZERO.bitLength());

        try {
            powBounded(BigInteger.TWO, 2000);
        } catch (IllegalArgumentException ex) {
            System.out.println("oversized power=rejected");
        }
        try {
            parseLimitedDecimal("1".repeat(41));
        } catch (IllegalArgumentException ex) {
            System.out.println("too many digits=rejected");
        }
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac --release 17 BigIntegerResourceDemo.java
java BigIntegerResourceDemo
~~~

Stdout:

~~~text
bits=1001
decimal digits=302
byte array length=126
parsed=12345678901234567890
longValueExact=rejected
square=1522756
two^10=1024
zero bits=0
oversized power=rejected
too many digits=rejected
~~~

Explanation:

- `2^1000` is just over 1000 bits and still completely safe to demonstrate; no need to build a number with millions of digits.
- Narrowing a `BigInteger` larger than `Long.MAX_VALUE` with `longValueExact()` triggers `ArithmeticException`. This catches out-of-range values instead of silently dropping bits like `longValue()`.
- Small multiplication `1234 × 1234` yields exact `1522756`.
- `2^10` returns `1024`, well within the 2048-bit budget.
- `2^2000` **is not computed** in `powBounded`: the conservative upper bound already exceeded the budget and threw an error before constructing the big number.
- A 41-digit string is rejected **before initializing `BigInteger`**.

The demo aims to show **resource control via application policy**, not to benchmark CPU or heap. The 40-digit/2048-bit budgets are purely illustrative settings; real products must derive limits from business requirements and load testing.

## 11. Use `modPow` Instead of Building a Giant Power and Taking `mod`

Many problems only need:

\[
a^e\bmod m
\]

with `m > 0`. There is no need to compute the full `a^e` first and then take the remainder. `BigInteger.modPow(BigInteger exponent, BigInteger modulus)` performs modular exponentiation directly.

~~~java
BigInteger base = BigInteger.valueOf(7);
BigInteger exponent = BigInteger.valueOf(100);
BigInteger modulus = BigInteger.valueOf(13);

BigInteger modular = base.modPow(exponent, modulus);
System.out.println(modular); // 9
~~~

In the example above, `7^100 mod 13 = 9`. `modPow` avoids holding **all of `7^100`** in an intermediate result just to take the remainder.

Still, **`modPow` is not free**: huge exponents, huge moduli, or high call volumes still consume CPU and resources. With untrusted data, you must still bound the lengths of base, exponent, and modulus, enforce a positive modulus, and enforce processing deadlines.

`BigInteger.modPow` also has special rules for negative exponents (involving modular inverses when they exist); if business logic only expects standard modular exponentiation, **reject negative exponents up front** to keep the contract simple and predictable.

## 12. Do Not Build Giant Strings Just to Inspect or Log

Dangerous logging example:

~~~java
// Do not do this with a BigInteger without size limits:
logger.info("Computed result: " + hugeBigInteger);
~~~

String concatenation invokes `BigInteger.toString()` before or while constructing the message, potentially forcing the application to allocate a massive decimal string. Even when using logging placeholders, verify whether the logging framework actually defers formatting and whether a size cap is applied before formatting.

Instead of logging the full number, if policy allows, log **size metadata**:

~~~java
BigInteger value = BigInteger.ONE.shiftLeft(1000);
System.out.println("sign=" + value.signum()
        + ", bits=" + value.abs().bitLength());
// sign=1, bits=1001
~~~

When serving APIs, bound **both input and output**. A very long numeric string that finished computing can still exceed limits of the response, cache, broker, database, or downstream receiving protocol.

If an application truly must output a huge result in full, use streaming/batching or store it in an appropriate resource, and evaluate decimal formatting costs too. Do not assume that because computation succeeded, serialization will always be safe.

## 13. Costs of Other Operations

| Operation | Cost aspect to watch |
| --- | --- |
| `add` / `subtract` | Processes numeric limbs; allocates appropriate result |
| `multiply` / `square` | Result size grows; multiplication uses CPU and temporary memory |
| `divide` / `remainder` | Multi-word division algorithm; cost depends on sizes of both operands |
| `pow` | Result length can grow proportionally with exponent |
| `shiftLeft` | Can expand bit count by shift distance |
| `toString` | Generates decimal string; CPU/memory for conversion and string result |
| `new BigInteger(String)` | String parsing and representation conversion cost |
| `gcd` | Cost increases with operand sizes |
| `modPow` | Avoids building full power, yet still consumes resources |
| `isProbablePrime` / `nextProbablePrime` | Primality testing/searching can be CPU-heavy on large inputs |

Never assign a single runtime figure or complexity formula to all `BigInteger` operations across all JVMs; the JDK may pick different algorithms depending on operand length and structure. What matters is **measuring on real data and runtimes** while enforcing safety limits at design time.

Another caution: dividing by `BigInteger.ZERO` throws `ArithmeticException` due to an **invalid mathematical condition**, not resource exhaustion. Distinguish data errors, resource-bound errors, and infrastructure errors when logging or returning API responses.

## 14. Growth Cannot Be Stopped Only by "Small Input" Rules

An API accepting two integers of at most 100 digits each looks safe for addition. Yet if a user also supplies:

- A huge `repeatCount` for repeated multiplication or addition.
- An `exponent` passed to `pow`.
- A `shiftDistance` passed to `shiftLeft`.
- Number of prime-search iterations.
- Step counts or concurrent request counts.

then results and CPU can blow past the budget even though **each input operand is small**.

Loop example:

~~~java
BigInteger value = BigInteger.TWO;
for (int step = 0; step < 10; step++) {
    value = value.multiply(value);
}
System.out.println(value.bitLength()); // 1025
~~~

Increasing steps slightly further makes size explode abruptly. Good protection defines an **overall cost bound** for the algorithm, not just character limits on a single input.

If a system evaluates user-submitted mathematical expressions, restrict expression depth, operation count, exponents, intermediate result sizes, and call frequency. Checking output size only after computation finishes comes too late to protect resources.

## 15. Why Catching `OutOfMemoryError` Is Not a Solution

`OutOfMemoryError` is an `Error`, not an ordinary business `Exception`. When the heap is exhausted or the JVM cannot allocate a needed object, the system may already be in a severely resource-starved state.

Never write code like:

~~~java
// Pattern to avoid for "handling" oversized numbers in business logic:
//
// try {
//     return veryLargeComputation();
// } catch (OutOfMemoryError error) {
//     return BigInteger.ZERO;
// }
~~~

Returning zero masks failures and produces corrupt data. Furthermore, catching `OutOfMemoryError` **does not guarantee** the program has enough memory left to run safe recovery logic; higher-level resource management and service recovery are normally required.

Better solutions:

1. Cap payload size **before** creating large strings/objects.
2. Validate bit/digit counts and growth-driving parameters before computation.
3. Use appropriate operations, such as `modPow` when only modular remainders are needed.
4. Set timeouts, concurrency limits, and quotas at the job/request layer.
5. Use proper metrics/monitoring for heap, GC, CPU, latency, and load.
6. Load-test with data near budget edges and verify behavior when thresholds are exceeded.

## 16. Timeouts and Heap Size: Not a Guarantee for Every `BigInteger`

JVM flags like `-Xmx` set the **maximum heap ceiling**, but do not specify how much a single `BigInteger` may occupy. Heap is shared with other objects, threads, requests, caches, and temporary arrays. Increasing `-Xmx` can let a workload run, yet can also cause long GC pauses, host memory pressure, or higher operating cost.

Example command:

~~~bash
java -Xmx256m MyBigIntegerApp
~~~

This is an **illustrative command**; `MyBigIntegerApp` is not a class created in this lesson. It only caps heap via JVM configuration, without automatically making every `BigInteger` computation safe inside that cap.

**Timeouts** also exist at multiple layers: HTTP timeouts, queue deadlines, job cancellation, and container CPU limits. Do not assume calling `Thread.interrupt()` will instantly halt every executing `BigInteger` method. For untrusted workloads or long calculations, consider isolating jobs in separate processes/workers with execution, bounding, and cancellation mechanisms suited to the system.

## 17. Designing Business Resource Budgets

A practical approach is **defining allowed budgets before building the API**:

| Parameter | Example limit | Purpose |
| --- | --- | --- |
| Input decimal digits | 1–1000 | Prevent overly long strings |
| Input bit length | ≤ 4096 | Bound operand magnitudes |
| Estimated result bits | ≤ 8192 | Prevent unexpected growth |
| Exponent | 0–10000, possibly lower | Control `pow`/loops |
| Operations per request | Per workload | Block abnormally long expressions |
| Response size | Per API contract | Avoid serializing/logging oversized results |
| Deadline/CPU quota | Per job type | Protect response times |
| Concurrent jobs | Per machine capacity | Avoid simultaneous huge allocations |

**Numbers in the table are design examples, not default recommendations or Java limits.** You cannot pick a single "bit budget" in isolation and conclude a service is safe: algorithmic complexity and concurrent requests heavily determine real cost.

When different operations carry different risks, set separate limits for parsing, addition, multiplication, exponentiation, primality testing, and serialization. With user-supplied data, enforce controls **before** every step that can escalate cost, even if earlier steps passed validation.

## 18. When to Use `BigInteger`, When to Keep `long`?

Use `long` if:

- The data domain is well-defined and always fits in 64 bits.
- High volumes of primitive integer math are needed with simple cost/representation.
- Overflow can be checked explicitly with `Math.addExact`, `Math.multiplyExact`, and numeric range rules.

Use `BigInteger` if:

- Valid integer values exceed the `long` range.
- Exact integer arithmetic with variable bit counts is required.
- The problem uses big-integer operations such as modular arithmetic, combinatorics, or specialized algorithms.
- You have designed resource-limiting policies and error reporting for unprocessable cases.

A balanced option: use `long` with `Math.addExact`/`multiplyExact` to detect overflow, then **intentionally promote to `BigInteger`** when the problem permits large numbers. Never perform an already-overflowed calculation in `long` and then pass the **wrong result** to `BigInteger`; convert operands before computing or handle overflow in a dedicated branch.

~~~java
long a = Long.MAX_VALUE;
long b = 1;

BigInteger sum = BigInteger.valueOf(a)
        .add(BigInteger.valueOf(b));
System.out.println(sum); // 9223372036854775808
~~~

## 19. Common Mistakes

| Mistake | Why dangerous | Right approach |
| --- | --- | --- |
| "`BigInteger` is infinite" | Heap, CPU, arrays, and implementations are finite | Enforce resource budgets |
| "If `long` doesn't overflow, no error can occur" | `OutOfMemoryError` or implementation limits can still happen | Limit inputs/outputs and operations |
| Reading a multi-million-digit `String` before validating | Payload already consumed RAM before validation | Cap size at ingestion layer |
| Limiting only initial operand `bitLength` | `pow`, `multiply`, or `shiftLeft` expand results fast | Estimate size before each operation |
| Calling `pow` directly with user-entered exponent | Can build gigantic results | Validate exponent and result bit budget |
| Using `base.pow(e).mod(m)` when only modulo is needed | Unnecessarily builds full power | `base.modPow(e, m)` when applicable |
| Calling `toString()` to check size of any number | Builds huge decimal strings | Use `abs().bitLength()` and cost bounds |
| Using `toByteArray().length` as heap size | Two's-complement array excludes object/intermediates | Treat as encoding, not RAM measurement |
| Narrowing via `BigInteger.longValue()` before operations | Can drop high bits | Keep `BigInteger` or use `longValueExact()` |
| Catching `OutOfMemoryError` and returning 0 | Masks errors; recovery not guaranteed | Prevent beforehand; handle at operational layer |
| Assuming increasing `-Xmx` fixes everything | CPU/GC/concurrency and output limits remain | Measure workload and set quotas |
| Treating `Runtime.freeMemory()` as a safe computation bound | Misses intermediate allocations, GC, and concurrent load | Use design limits and real monitoring |
| Limiting only input characters, ignoring request count | Concurrent load can exhaust resources | Limit concurrency/rate |
| Extrapolating timing from one small run to all sizes | Algorithms can change with size | Benchmark across data ranges |
| Treating every `ArithmeticException` as divide-by-zero | Could be implementation limit overflow, exact conversion, negative exponent, etc. | Distinguish by API and context |

## 20. Self-Check Questions

**Question 1.** Why is `BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE)` accurate, yet still does not prove `BigInteger` is "infinite"?

**Answer:** `BigInteger` is not fixed at 64 bits like `long`, so it represents numbers beyond `Long.MAX_VALUE`. However, it still relies on heap and algorithms on a finite JVM with implementation and resource limits.

**Question 2.** How many bits does `2^1000` need to represent magnitude, and how many decimal digits does it have?

**Answer:** 1001 bits and 302 decimal digits. `BigInteger.ONE.shiftLeft(1000)` is the verification example.

**Question 3.** Why is `toByteArray().length` not the heap size of a `BigInteger`?

**Answer:** It is the length of **a newly allocated array holding signed two's-complement encoding**, which may include an extra sign bit/byte and excludes object headers, internal arrays, and other buffers.

**Question 4.** If the input is just 3 digits `"999"` yet the exponent is 1 billion, can it be considered safe?

**Answer:** No. `999^1000000000` has an enormous result size. Validate exponents and result bit bounds before computing.

**Question 5.** When needing only `7^100 mod 13`, should you use `pow(100).mod(13)` or `modPow(100,13)`?

**Answer:** `modPow` is more suitable because it computes the modular remainder directly without building the full power.

**Question 6.** Why should you not catch `OutOfMemoryError` and return `BigInteger.ZERO`?

**Answer:** Running out of memory is not the arithmetic result 0; doing so hides errors and may leave the JVM unable to recover. Design resource limits beforehand.

**Question 7.** Do `BigInteger.bitLength()` and `new BigInteger(text).toString().length()` have the same cost and units?

**Answer:** No. `bitLength()` returns bit count in numeric representation, whereas `toString()` builds decimal text and `length()` counts UTF-16 code units of that text. Converting huge numbers to strings can consume substantial resources.

**Question 8.** If the result bit budget is 2048, a multiplication has bound `aBits+bBits=2050` while the actual product might be only 2049 bits, should the conservative checker be called "wrong"?

**Answer:** No; the function is designed to be **conservative** and may intentionally reject cases that would actually fit in budget. To optimize acceptance rates, design a tighter estimation/check and accept the corresponding cost.

## 21. Key Takeaways and References

- **`BigInteger` is not capped at 64 bits**, yet it does not have infinite resources. Practical limits are determined by **implementation, heap, CPU, temporary objects, and application policy**.
- Bit count can be observed via `abs().bitLength()`; **do not use `toByteArray()` as a heap-measurement tool**.
- **Small inputs can create huge outputs** through multiplication, repeated squaring, left shifts, and `pow`.
- Enforce limits **before parsing, before heavy operations, and before serializing/logging**. Conservative size bounds should be clearly documented.
- When needing only modular exponentiation, prefer `modPow` over computing full `pow` then taking `mod`.
- `OutOfMemoryError` is not a way to report "result equals 0"; prevent it with quotas, validation, timeouts, and proper load isolation.
- Use `long` when a fixed range suffices; use `BigInteger` when large exact integers are truly needed and their costs are accepted.

Official references (Java 17):

- [BigInteger — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): supported range limits, `bitLength`, `multiply`, `pow`, `modPow`, `toByteArray`, `longValueExact`.
- [Math — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `addExact` and `multiplyExact` when primitive overflow detection is needed.
- [OutOfMemoryError — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/OutOfMemoryError.html): allocation error when the JVM cannot supply a required object.
- [Java launcher options — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xmx` heap options and JVM startup configurations.