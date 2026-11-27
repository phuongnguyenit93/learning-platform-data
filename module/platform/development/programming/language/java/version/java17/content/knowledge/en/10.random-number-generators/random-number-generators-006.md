# Generating Bounded Numbers and Validating Value Ranges in Java 17

When generating pseudo-random numbers, a program often needs a value within a specific range: a score from 0 to 100, a die face from 1 to 6, an item count from 0 to 9, or a valid list index.

In Java, it is important to understand **whether the lower bound is included and whether the upper bound is included**, validate the input range before generating, and choose the right API for the purpose. Java 17 provides bounded number generation via \`Random\`, \`RandomGenerator\`, \`ThreadLocalRandom\`, and \`SecureRandom\`.

> **Scope:** This lesson uses APIs built into Java 17. \`RandomGenerator\` belongs to the \`java.util.random\` package added in Java 17. No preview features are required.

## 1. Value Ranges: Inclusive Bounds vs. Exclusive Bounds

Before calling an API, define the target range.

There are two common notations:

| Notation | Meaning | Example |
|---|---|---|
| \`[min, max]\` | Includes both lower bound and upper bound | \`[1, 6]\` includes 1, 2, 3, 4, 5, 6 |
| \`[min, max)\` | Includes lower bound, excludes upper bound | \`[1, 7)\` also includes 1, 2, 3, 4, 5, 6 |

Many Java number generation APIs follow the **inclusive lower bound, exclusive upper bound** convention:

\`\`\`java
random.nextInt(origin, bound);
\`\`\`

Where:

- \`origin\`: the smallest value that can appear.
- \`bound\`: the upper limit that **cannot appear** in the result.
- Validity condition: \`origin < bound\`.

Example:

\`\`\`java
Random random = new Random();

int dice = random.nextInt(1, 7);
\`\`\`

The result can be 1, 2, 3, 4, 5, or 6. The value 7 can never be returned.

**Memory tip:** With an API like \`nextInt(origin, bound)\`, to get an integer range from 1 to 6, pass 1 and 7.

## 2. Bounded Number Generation APIs in Java 17

### 2.1. \`Random.nextInt(bound)\`: Generating from 0 to bound Minus 1

This is a common way to get a bounded non-negative integer:

\`\`\`java
import java.util.Random;

public class BoundedRandomDemo {
    public static void main(String[] args) {
        Random random = new Random();

        int value = random.nextInt(10);
        System.out.println(value);
    }
}
\`\`\`

Values can range from 0 to 9.

Conditions:

- \`bound\` must be greater than 0.
- If \`bound <= 0\`, the method throws \`IllegalArgumentException\`.
- The result excludes \`bound\`.

Using it to pick a list index:

\`\`\`java
List<String> names = List.of("An", "Binh", "Chi");
Random random = new Random();

int index = random.nextInt(names.size());
String selected = names.get(index);
\`\`\`

Because \`names.size()\` is 3, \`index\` can only be 0, 1, or 2, matching the valid indices of the list.

Check for an empty list before calling \`nextInt(names.size())\`, because \`nextInt(0)\` is invalid.

### 2.2. \`Random.nextInt(origin, bound)\`: Generating in Any Range

Starting in Java 17, \`Random\` implements the \`RandomGenerator\` interface; the \`nextInt(origin, bound)\` method can be used directly:

\`\`\`java
import java.util.Random;

public class RandomRangeDemo {
    public static void main(String[] args) {
        Random random = new Random();

        int temperature = random.nextInt(-10, 41);
        System.out.println(temperature);
    }
}
\`\`\`

The result lies in \`[-10, 41)\`, meaning from -10 to 40.

Other examples:

\`\`\`java
int score = random.nextInt(0, 101);  // 0..100
int dice = random.nextInt(1, 7);     // 1..6
int offset = random.nextInt(-5, 6);  // -5..5
\`\`\`

The upper bound remains excluded. With \`nextInt(origin, bound)\`, the condition \`origin >= bound\` causes the method to throw \`IllegalArgumentException\`.

### 2.3. Using the \`RandomGenerator\` Interface in Java 17

Java 17 adds the \`java.util.random\` package and the \`RandomGenerator\` interface to provide a common interface for pseudo-random number generators:

\`\`\`java
import java.util.Random;
import java.util.random.RandomGenerator;

public class RandomGeneratorDemo {
    public static void main(String[] args) {
        RandomGenerator generator = new Random(12345L);

        int dice = generator.nextInt(1, 7);
        long ticket = generator.nextLong(1L, 1_000_001L);
        double ratio = generator.nextDouble(0.0, 1.0);

        System.out.println(dice);
        System.out.println(ticket);
        System.out.println(ratio);
    }
}
\`\`\`

This interface lets code receive a generation source via an abstract type instead of depending directly on a concrete class. \`Random\` is an implementation assignable to a \`RandomGenerator\` variable.

Commonly used bounded methods:

| Method | Result Range |
|---|---|
| \`nextInt(bound)\` | \`[0, bound)\` |
| \`nextInt(origin, bound)\` | \`[origin, bound)\` |
| \`nextLong(bound)\` | \`[0, bound)\` |
| \`nextLong(origin, bound)\` | \`[origin, bound)\` |
| \`nextDouble(bound)\` | \`[0.0, bound)\` |
| \`nextDouble(origin, bound)\` | \`[origin, bound)\` |

For two-argument methods, the lower bound must be less than the upper bound. For methods taking only \`bound\`, bound must be positive.

### 2.4. \`ThreadLocalRandom\` When Multiple Threads Generate Numbers

In multithreaded applications, \`ThreadLocalRandom\` is a convenient choice to avoid multiple threads contending over a single \`Random\` object:

\`\`\`java
import java.util.concurrent.ThreadLocalRandom;

public class ConcurrentRandomDemo {
    static int generateScore() {
        return ThreadLocalRandom.current().nextInt(0, 101);
    }
}
\`\`\`

Each thread uses its own random source bound to the current thread. You do not manually instantiate \`ThreadLocalRandom\` via a constructor; retrieve the instance via \`ThreadLocalRandom.current()\`.

Use when:

- Multiple threads need to generate numbers independently.
- You do not need to reproduce the result sequence with a fixed seed per thread.
- The goal is performance and convenience for general pseudo-random numbers.

Do not use \`ThreadLocalRandom\` to generate tokens, verification codes, or data that must resist prediction.

### 2.5. \`SecureRandom\` When Unpredictability Is Required

\`Random\` and \`ThreadLocalRandom\` serve general pseudo-random needs. If a value is used in a security context, choose \`SecureRandom\`:

\`\`\`java
import java.security.SecureRandom;

public class SecureRandomDemo {
    public static void main(String[] args) {
        SecureRandom secureRandom = new SecureRandom();

        int verificationCode = secureRandom.nextInt(1_000_000);
        System.out.println(verificationCode);
    }
}
\`\`\`

The result lies between 0 and 999,999. When a full 6-digit display code is needed, format it explicitly because numeric values may have leading zeros:

\`\`\`java
String code = "%06d".formatted(verificationCode);
System.out.println(code);
\`\`\`

For example, \`verificationCode = 42\` will be displayed as \`000042\`.

\`SecureRandom\` is more suitable for tokens or codes used in security workflows, but you still need proper expiration, attempt limits, storage, and verification design. Secure number generation does not automatically make the entire authentication flow secure.

**Do not set a predictable seed on \`SecureRandom\`** or use \`new Random()\` to generate security tokens.

## 3. Validating Value Ranges Before Generating Numbers

A common requirement is for a user to input lower and upper bounds. Before calling the API, the program must determine whether that range is valid according to business requirements.

For example, to generate scores from 0 to 100:

- The lower bound must not be less than 0.
- The upper bound must not exceed 100.
- The lower bound must not exceed the upper bound.
- If the API uses an exclusive upper bound, the range must satisfy \`min < maxExclusive\`.

Separating **business domain validation** from **generator API preconditions** prevents confusing errors.

### 3.1. Validating a Half-Open Range

\`\`\`java
static int randomInRange(RandomGenerator random, int min, int maxExclusive) {
    if (random == null) {
        throw new IllegalArgumentException("Random source must not be null");
    }

    if (min >= maxExclusive) {
        throw new IllegalArgumentException(
                "min < maxExclusive is required");
    }

    return random.nextInt(min, maxExclusive);
}
\`\`\`

The method above requires the range to contain at least one integer value. Examples:

| min | maxExclusive | Valid? | Possible Results |
|---:|---:|---|---|
| 1 | 7 | Yes | 1..6 |
| 0 | 1 | Yes | Only 0 |
| -5 | 6 | Yes | -5..5 |
| 5 | 5 | No | Empty range |
| 8 | 3 | No | Lower bound exceeds upper bound |

You could let the API throw an exception on invalid bounds, but validating beforehand typically yields error messages that align better with the business contract.

### 3.2. Validating a Score Range

If a system accepts a score range from the user but only permits scores from 0 to 100:

\`\`\`java
static int randomScore(
        RandomGenerator random,
        int min,
        int maxExclusive
) {
    if (min < 0 || maxExclusive > 101 || min >= maxExclusive) {
        throw new IllegalArgumentException(
                "Score range must be within 0..100");
    }

    return random.nextInt(min, maxExclusive);
}
\`\`\`

Examples:

- \`randomScore(random, 0, 101)\`: generates 0..100.
- \`randomScore(random, 50, 81)\`: generates 50..80.
- \`randomScore(random, -1, 50)\`: rejected.
- \`randomScore(random, 50, 102)\`: rejected.
- \`randomScore(random, 80, 50)\`: rejected.

Here \`maxExclusive <= 101\` because the value 100 must be includable.

### 3.3. Distinguishing Input Validation from Output Checking

Do not generate over the entire domain and only then check whether the result falls inside the range:

\`\`\`java
int value = random.nextInt();

// Do not generate across the entire range and loop to filter a simple interval.
while (value < min || value >= maxExclusive) {
    value = random.nextInt();
}
\`\`\`

This approach is both hard to read and can loop for a very long time if the valid range is small relative to the full domain. When the API already supports bounds, pass the bounds directly into the method:

\`\`\`java
int value = random.nextInt(min, maxExclusive);
\`\`\`

Validate inputs beforehand to guarantee bounds match business rules; let the API generate directly within the required domain.

## 4. Including the Upper Bound: Handling Off-by-One Correctly

A common bug is needing a range **inclusive of both endpoints** while passing the upper bound as if it were inclusive.

Suppose you need to generate a number from 1 to 6:

\`\`\`java
int wrong = random.nextInt(1, 6);
\`\`\`

This produces results from 1 to 5; the number 6 can never appear.

If the upper bound is less than \`Integer.MAX_VALUE\`, you can write:

\`\`\`java
int dice = random.nextInt(1, 6 + 1);
\`\`\`

However, \`max + 1\` can **overflow** if \`max == Integer.MAX_VALUE\`. To handle the entire \`int\` domain safely, widen the bound to \`long\` before adding:

\`\`\`java
static int randomIntInclusive(
        RandomGenerator random,
        int minInclusive,
        int maxInclusive
) {
    if (random == null) {
        throw new IllegalArgumentException("Random source must not be null");
    }

    if (minInclusive > maxInclusive) {
        throw new IllegalArgumentException(
                "minInclusive <= maxInclusive is required");
    }

    long exclusiveUpper = (long) maxInclusive + 1L;

    return (int) random.nextLong(
            (long) minInclusive,
            exclusiveUpper
    );
}
\`\`\`

Explanation:

1. Cast \`maxInclusive\` to \`long\` **before adding 1**.
2. The value \`Integer.MAX_VALUE + 1\` is representable in \`long\`.
3. \`nextLong(origin, bound)\` generates in a half-open interval.
4. Every result in the interval fits within \`int\`, so casting back to \`int\` is safe.

This function also handles \`minInclusive == maxInclusive\`: the range contains only one value, and the result is always that value.

### 4.1. Do Not Add 1 in int Before Casting

Wrong:

\`\`\`java
int exclusiveUpper = maxInclusive + 1;
long bound = exclusiveUpper;
\`\`\`

If \`maxInclusive\` is \`Integer.MAX_VALUE\`, the addition has already overflowed before assignment to \`long\`.

Right:

\`\`\`java
long exclusiveUpper = (long) maxInclusive + 1L;
\`\`\`

Principle: **widen the data type before any operation that could overflow**.

### 4.2. Inclusive Ranges for long Need Attention at the Maximum Bound

For \`long\`, \`maxInclusive + 1L\` can overflow if \`maxInclusive == Long.MAX_VALUE\`. Do not mechanically apply the helper above to the entire \`long\` domain.

If the requirement only needs an exclusive upper bound, use \`nextLong(origin, bound)\` directly. If you genuinely need an inclusive range that may include \`Long.MAX_VALUE\`, you must design an algorithm that handles the boundary case separately or use a proven specialized approach/API. Never silently add 1 in \`long\`.

## 5. Generating Bounded Floating-Point Numbers

For \`double\`, you can use \`nextDouble(origin, bound)\`:

\`\`\`java
RandomGenerator random = new Random();

double ratio = random.nextDouble(0.0, 1.0);
double temperature = random.nextDouble(18.5, 30.0);
\`\`\`

The range has the form \`[origin, bound)\`: the lower bound can appear, while the upper bound is excluded. The precondition is \`origin < bound\`.

Do not confuse generating a \`double\` with generating exact decimal numbers:

- \`double\` represents binary floating-point numbers; many decimal numbers cannot be represented exactly.
- \`nextDouble()\` is suitable for simulations, probabilities, ratios, or numerical algorithms.
- Do not use \`double\` to represent exact monetary amounts.
- If business logic requires currency or decimals with fixed scale, use \`BigDecimal\` with appropriate rounding rules.

Example generating a discount rate for illustration:

\`\`\`java
double discountRate = random.nextDouble(0.05, 0.21);
\`\`\`

The value lies from 0.05 to less than 0.21. If discrete steps of 0.01 are needed, generate an integer in a range and divide according to business rules rather than comparing \`double\` values with exact equality.

## 6. Avoiding Incorrect Generation via Modulo

A common but flawed pattern:

\`\`\`java
int value = Math.abs(random.nextInt()) % 10;
\`\`\`

There are two problems:

1. \`Math.abs(Integer.MIN_VALUE)\` remains negative because the absolute value of the smallest \`int\` cannot be represented in \`int\`.
2. Taking modulo of a random outcome does not guarantee each remainder occurs with equal probability when the source value count is not divisible by 10. This is **modulo bias**.

The right way:

\`\`\`java
int value = random.nextInt(10);
\`\`\`

Or with a custom range:

\`\`\`java
int value = random.nextInt(20, 31); // 20..30
\`\`\`

Java's bounded API handles bounded sampling without manual modulo.

Similarly, do not write:

\`\`\`java
int value = (random.nextInt() % 10 + 10) % 10;
\`\`\`

This expression makes the result non-negative but **does not eliminate modulo bias**.

## 7. Choosing an Appropriate Generator and Seed

### 7.1. \`Random\`: Easy to Use and Reproducible

\`\`\`java
Random random = new Random(12345L);

int first = random.nextInt(1, 7);
int second = random.nextInt(1, 7);
\`\`\`

With the same seed and same call sequence on the same \`Random\` algorithm, results can be reproduced. This is helpful for:

- Exercises and teaching examples.
- Tests needing stable mock data.
- Debugging a bug dependent on a random number sequence.

A fixed seed makes the result sequence predictable. **Do not use a fixed seed or \`Random\` for security purposes.**

If no seed is passed, \`Random\` initializes its own initial state. That does not turn it into a cryptographic random source.

### 7.2. \`ThreadLocalRandom\`: General Tasks in Multithreaded Environments

\`\`\`java
int value = ThreadLocalRandom.current().nextInt(100, 201);
\`\`\`

Suitable when multiple threads need general-purpose random numbers and you do not need to control seeds per result sequence.

### 7.3. \`SecureRandom\`: Tokens and Security Codes

\`\`\`java
SecureRandom secureRandom = new SecureRandom();
byte[] tokenBytes = new byte[32];
secureRandom.nextBytes(tokenBytes);
\`\`\`

Use \`SecureRandom\` for data requiring unpredictability, such as random tokens. If you need to represent the token as a string, use a suitable encoding such as URL-safe Base64; do not use \`String.valueOf(byteArray)\` because it does not represent the byte contents as intended.

**Note:** A six-digit OTP code has only one million possibilities. Beyond using a secure generation source, the system must enforce expiration, attempt limits, replay protection, and a proper verification flow.

### 7.4. Quick Selection Table

| Need | Choice |
|---|---|
| Exercises, simple simulations | \`Random\` |
| Tests needing reproducible results | \`new Random(seed)\` |
| Multiple threads generating general-purpose numbers | \`ThreadLocalRandom.current()\` |
| Needing a common API type across implementations | \`RandomGenerator\` |
| Tokens, verification codes, unpredictable values | \`SecureRandom\` |

There is no single generator suited for every problem. Choose according to reproducibility, performance, and security requirements.

## 8. Generating Numbers from Lists and Business Domains

### 8.1. Picking a Random Element from a List

\`\`\`java
static <T> T chooseOne(
        List<T> values,
        RandomGenerator random
) {
    if (values == null || values.isEmpty()) {
        throw new IllegalArgumentException(
                "List must contain at least one element");
    }

    if (random == null) {
        throw new IllegalArgumentException("Random source must not be null");
    }

    return values.get(random.nextInt(values.size()));
}
\`\`\`

Valid list indices have the form \`[0, size)\`. Therefore \`nextInt(values.size())\` is the right choice. If the list is empty, \`size()\` is 0 and the API cannot generate a valid index.

### 8.2. Generating a Bounded Item Quantity

Suppose you want to generate a product quantity from 1 to 5:

\`\`\`java
int quantity = random.nextInt(1, 6);
\`\`\`

If the maximum quantity is an input value, validate it beforehand:

\`\`\`java
static int randomQuantity(RandomGenerator random, int maxInclusive) {
    if (maxInclusive < 1) {
        throw new IllegalArgumentException(
                "Maximum quantity must be at least 1");
    }

    return random.nextInt(1, maxInclusive + 1);
}
\`\`\`

This snippet still risks overflow if \`maxInclusive == Integer.MAX_VALUE\`. You can use the inclusive helper written in section 4 for more general handling:

\`\`\`java
static int randomQuantity(
        RandomGenerator random,
        int maxInclusive
) {
    if (maxInclusive < 1) {
        throw new IllegalArgumentException(
                "Maximum quantity must be at least 1");
    }

    return randomIntInclusive(random, 1, maxInclusive);
}
\`\`\`

### 8.3. Validating Business Domain Before Creating Objects

Suppose valid scores must range from 0 to 100. We can model that domain:

\`\`\`java
record Score(int value) {
    public Score {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "Score must be within 0..100");
        }
    }
}
\`\`\`

Then generate a valid value directly:

\`\`\`java
Score score = new Score(random.nextInt(0, 101));
\`\`\`

The constructor enforces domain validation for every source that creates the object, including data coming from APIs, files, or databases. The random generator is merely one data producer; do not put all business domain correctness solely at the random call site.

## 9. Complete Example: Generating and Validating a Score Range

Create the file **\`BoundedScoreDemo.java\`**:

\`\`\`java
import java.util.Random;
import java.util.random.RandomGenerator;

public class BoundedScoreDemo {

    record Score(int value) {
        public Score {
            if (value < 0 || value > 100) {
                throw new IllegalArgumentException(
                        "Score must be within 0..100");
            }
        }
    }

    static int generateScore(
            RandomGenerator random,
            int minInclusive,
            int maxInclusive
    ) {
        if (minInclusive < 0
                || maxInclusive > 100
                || minInclusive > maxInclusive) {
            throw new IllegalArgumentException(
                    "Score range must be within 0..100 and min <= max");
        }

        return randomIntInclusive(
                random,
                minInclusive,
                maxInclusive
        );
    }

    static int randomIntInclusive(
            RandomGenerator random,
            int minInclusive,
            int maxInclusive
    ) {
        if (random == null) {
            throw new IllegalArgumentException("Random source must not be null");
        }
        if (minInclusive > maxInclusive) {
            throw new IllegalArgumentException("min must be <= max");
        }

        return (int) random.nextLong(
                (long) minInclusive,
                (long) maxInclusive + 1L
        );
    }

    public static void main(String[] args) {
        RandomGenerator random = new Random(2026L);

        for (int i = 0; i < 5; i++) {
            int value = generateScore(random, 0, 100);
            Score score = new Score(value);
            System.out.println(score);
        }
    }
}
\`\`\`

Compile and run with JDK 17:

\`\`\`bash
javac --release 17 BoundedScoreDemo.java
java BoundedScoreDemo
\`\`\`

Because a fixed seed is used, the sequence of numbers is reproduced when rerunning the same program with the same call order. Specific individual values need not be memorized; what matters is:

- Values always belong to 0..100.
- \`generateScore\` rejects ranges outside the business domain.
- \`Score\` protects its own object invariant.
- The inclusive helper uses \`long\` arithmetic to avoid the \`max + 1\` overflow bug in \`int\`.

## 10. Common Errors

| Error | Why It Happens | Resolution |
|---|---|---|
| Using \`nextInt(1, 6)\` to roll a die | Upper bound 6 is excluded, generating only 1..5 | Use \`nextInt(1, 7)\` |
| Calling \`nextInt(0)\` | Bound must be positive | Check collection size before generating |
| Calling \`nextInt(min, max)\` when \`min == max\` | Empty half-open range | Clarify business logic: if a single value is needed, use an inclusive range or handle separately |
| Adding 1 to \`Integer.MAX_VALUE\` in \`int\` | Integer overflow | Cast to \`long\` before adding |
| Using \`Math.abs(nextInt()) % n\` | Negative edge case and skewed modulo distribution | Use \`nextInt(n)\` |
| Thinking \`nextInt()\` is always non-negative | Unbounded call returns integers across the whole domain, including negatives | Use bounded overloads |
| Using \`Random\` to generate security tokens | Pseudo-random sequence can be predicted | Use \`SecureRandom\` |
| Generating \`double\` for currency | Binary floating-point representation inaccuracy | Use \`BigDecimal\` and currency rules |
| Checking results only after generating across the full domain | Can loop long and hurt performance | Validate bounds first and generate directly within the range |

## 11. Practice Exercises

### Exercise 1: Rolling a Die

Write a method \`rollDice(RandomGenerator random)\` that returns an integer from 1 to 6.

**Suggested Answer:**

\`\`\`java
static int rollDice(RandomGenerator random) {
    return random.nextInt(1, 7);
}
\`\`\`

The upper bound 7 is excluded, so 6 can still appear.

### Exercise 2: Finding the Off-by-One Bug

Code snippet:

\`\`\`java
int score = random.nextInt(0, 100);
\`\`\`

The requirement is to generate scores from 0 to 100, inclusive of 100. What is wrong with the code?

**Answer:** \`100\` is excluded. Fix to:

\`\`\`java
int score = random.nextInt(0, 101);
\`\`\`

### Exercise 3: Validating Input Bounds

Write a function generating an integer in the half-open range \`[min, maxExclusive)\`; if \`min >= maxExclusive\`, throw \`IllegalArgumentException\`.

**Suggested Answer:**

\`\`\`java
static int generate(
        RandomGenerator random,
        int min,
        int maxExclusive
) {
    if (min >= maxExclusive) {
        throw new IllegalArgumentException("Invalid range");
    }

    return random.nextInt(min, maxExclusive);
}
\`\`\`

### Exercise 4: Inclusive Range with Maximum Bound

Why should you not write:

\`\`\`java
random.nextInt(min, maxInclusive + 1);
\`\`\`

when \`maxInclusive\` can be \`Integer.MAX_VALUE\`?

**Answer:** The addition occurs in \`int\` and can overflow before the method is called. Widen to \`long\` before adding, then use \`nextLong((long) min, (long) maxInclusive + 1L)\` and cast the result back to \`int\`.

### Exercise 5: Choosing a Number Source

Match each scenario with the appropriate API:

| Scenario | Choice |
|---|---|
| Running tests with a repeatable sequence | \`new Random(seed)\` |
| Generating numbers across multiple worker threads | \`ThreadLocalRandom.current()\` |
| Generating unpredictable tokens | \`SecureRandom\` |
| Writing an API accepting a general random source in Java 17 | \`RandomGenerator\` |

### Exercise 6: Why Is Modulo Unsuitable?

Explain why \`Math.abs(random.nextInt()) % 10\` is not a good way to generate numbers 0..9.

**Answer:** \`Math.abs(Integer.MIN_VALUE)\` remains negative, and modulo can create a skewed distribution if the number of source states is not divisible by 10. Use \`random.nextInt(10)\`.

## 12. Key Takeaways

When generating bounded numbers in Java 17, determine the range clearly first:

~~~text
[min, max)  -> lower bound can appear, upper bound cannot appear
[min, max]  -> both bounds can appear
~~~

Choose the right API for the representation:

- \`nextInt(bound)\` for \`[0, bound)\`.
- \`nextInt(origin, bound)\` for \`[origin, bound)\`.
- \`nextLong(origin, bound)\` when a wider range is needed or when handling inclusive int via long arithmetic.
- \`nextDouble(origin, bound)\` for floating-point ranges.
- \`ThreadLocalRandom\` for general needs in multithreaded environments.
- \`SecureRandom\` for data requiring unpredictability.

Finally, **validate business domains before generating**, avoid off-by-one bugs and overflow when adjusting bounds, do not manually use modulo to restrict outputs, and do not use ordinary number generators for security purposes.

## 13. References

- [Oracle Java SE 17 — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): pseudo-random number generator interface, bounded methods, and range rules.
- [Oracle Java SE 17 — Random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): traditional pseudo-random number generator and compatibility with \`RandomGenerator\`.
- [Oracle Java SE 17 — ThreadLocalRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): generator bound to the current thread.
- [Oracle Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): random number source for security purposes.
- [OpenJDK JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): enhancements and common interface for pseudo-random number generators since Java 17.
