# Testing Empty, Boundary, Negative, Invalid, and Large Values in Java

Testing does not only verify that normal inputs work correctly. A reliable Java program must also have **well-defined behavior** when data is missing, sits right on boundaries, includes negative numbers, has invalid formatting, or exceeds numeric type limits. These cases must be designed from the **program's contract** (accepted inputs, bounds, expected results, and expected errors), rather than testing arbitrary numbers.

This lesson uses Java 17+ and an example handling a **product quantity** valid within the range `0..1_000_000`. Illustrative rules: `0` is valid; negative values and values greater than `1_000_000` are rejected; input must be a valid `int` string representation without automatic whitespace trimming. In other domains, bounds may differ and must be stated clearly before writing tests.

## 1. Categorizing inputs and defining expected results

| Category | Example input | What to verify |
| --- | --- | --- |
| Missing data | `null` for a `String` reference | Report missing value error; never invoke methods on `null` |
| Empty string | `""` | Report clear error; do not attempt to parse as a number |
| Whitespace only | `"   "` | Distinguish from a string containing a valid number |
| Lower bound and neighbors | `-1`, `0`, `1` | `-1` rejected, `0` and `1` valid |
| Upper bound and neighbors | `999999`, `1000000`, `1000001` | First two valid, last one out of bounds |
| Invalid format | `"12x"`, `"3.5"`, `" 5 "` | Do not silently convert into another value; consistent message |
| Outside `int` range | `"2147483648"` | `Integer.parseInt` throws `NumberFormatException`; program must handle it |
| Large value calculations | Price `50_000` × quantity `1_000_000` | Result `50_000_000_000` needs `long` or a suitable type; must not overflow `int` |

**"Empty" does not have a single meaning:** `null` means no object; `""` is a `String` of length 0; `"   "` is not empty according to `isEmpty()` yet `isBlank()` returns `true`. An empty list (`List.isEmpty()`) or an array with `length == 0` is structured data needing its own validation rule. For primitive `int`, the variable itself cannot hold `null`; missing data issues usually arise before parsing from a string or through `Integer`.

Do not automatically treat `0` as "not entered." It can be a valid quantity. If you want to forbid `0`, write the rule as `1..MAX` and update all corresponding tests.

## 2. Systematic boundary testing

If the valid domain is **`MIN <= x <= MAX`**, high-value test cases include:

- `MIN - 1` (out of range), `MIN` (exact lower bound), `MIN + 1` (just inside range).
- `MAX - 1` (just inside range), `MAX` (exact upper bound), `MAX + 1` (out of range).
- A normal mid-range value, such as `42`, to verify the main path.

In the example `MIN=0`, `MAX=1_000_000`, the values are `-1, 0, 1, 999999, 1000000, 1000001`. Specify clearly whether bounds are **inclusive** (`<=`) or **exclusive** (`<`); a single wrong operator character can flip the outcome right at the boundary. For large boundary calculations such as `Integer.MAX_VALUE + 1`, do not use `int` addition that overflows the test value itself; prepare test data with `long`, `String`, or `BigInteger` as appropriate.

Negative-number checks only make sense when the input can represent negatives. If the data is age, quantity, or non-negative duration, the behavior may be to reject with a defined error; if the data is Celsius temperature, negative numbers may be valid. Thus, **business requirements determine the expected outcome**.

## 3. Invalid data and exceptions

When text input must become an `int`, `Integer.parseInt(raw)` throws `NumberFormatException` if it cannot be parsed or the value exceeds the `int` range (`-2147483648` to `2147483647`). This is a subclass of `IllegalArgumentException`.

A clear validation design typically follows this order:

1. Check for `null` references and empty/blank data.
2. Parse strictly according to format. Decide **beforehand** whether to `trim()`/normalize whitespace; this example intentionally rejects `" 5 "`.
3. Check range rules: negative values, exceeding limits, inclusive/exclusive bounds.
4. Perform business logic only after input is valid; report errors clearly enough for the caller to handle.

Distinguish **format-invalid input** (`"12x"`) from **numerically valid but policy-invalid input** (`"1000001"`). Never use `catch (Exception)` and return a default `0`: that hides errors and makes wrong results look like success. In real applications, you can return a structured error result or throw an exception handled at the UI/API layer.

Note: underscores in Java numeric literals like `1_000_000` aid **source code** readability, but the input string `"1_000_000"` is not accepted by `Integer.parseInt`. `"3.5"` is not an integer string either, and casting to `int` after reading a `double` is a different behavior that must be specified separately.

## 4. Automated verification program in Java 17+

Save the entire program below into **`InputBoundaryChecks.java`** (no `package` declaration). The `expectValid` and `expectInvalid` methods verify **both the return value and the error message**; if actual behavior mismatches, they throw `AssertionError`. There is no need to enable JVM `-ea`.

```java
import java.math.BigInteger;

public final class InputBoundaryChecks {
    private static final int MAX_COUNT = 1_000_000;

    private InputBoundaryChecks() {
    }

    public static void main(String[] args) {
        expectInvalid("null", null, "thiếu giá trị");
        expectInvalid("rỗng", "", "rỗng hoặc chỉ khoảng trắng");
        expectInvalid("toàn khoảng trắng", "   ", "rỗng hoặc chỉ khoảng trắng");

        expectInvalid("âm -1", "-1", "phải không âm");
        expectValid("min 0", "0", 0);
        expectValid("min+1 1", "1", 1);
        expectValid("thông thường 42", "42", 42);
        expectValid("max-1 999999", "999999", 999_999);
        expectValid("max 1000000", "1000000", MAX_COUNT);
        expectInvalid("max+1 1000001", "1000001", "vượt 1000000");

        expectInvalid("sai chữ", "12x", "không phải int hợp lệ");
        expectInvalid("số thập phân", "3.5", "không phải int hợp lệ");
        expectInvalid("có khoảng trắng", " 5 ", "không phải int hợp lệ");
        expectInvalid("vượt int", "2147483648", "không phải int hợp lệ");

        checkLargeNumbers();
    }

    private static int parseCount(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("thiếu giá trị");
        }
        if (raw.isBlank()) {
            throw new IllegalArgumentException("rỗng hoặc chỉ khoảng trắng");
        }

        final int count;
        try {
            count = Integer.parseInt(raw);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("không phải int hợp lệ", e);
        }

        if (count < 0) {
            throw new IllegalArgumentException("phải không âm");
        }
        if (count > MAX_COUNT) {
            throw new IllegalArgumentException("vượt " + MAX_COUNT);
        }
        return count;
    }

    private static void expectValid(String name, String raw, int expected) {
        int actual = parseCount(raw);
        if (actual != expected) {
            throw new AssertionError(name + ": cần " + expected + ", nhận " + actual);
        }
        System.out.println(name + ": PASS -> " + actual);
    }

    private static void expectInvalid(
            String name, String raw, String expectedMessage) {
        try {
            parseCount(raw);
            throw new AssertionError(name + ": đáng lẽ phải báo lỗi");
        } catch (IllegalArgumentException e) {
            if (!expectedMessage.equals(e.getMessage())) {
                throw new AssertionError(name + ": sai thông báo lỗi", e);
            }
            System.out.println(name + ": PASS (" + e.getMessage() + ")");
        }
    }

    private static void checkLargeNumbers() {
        int unitPriceVnd = 50_000;
        int count = 1_000_000;

        try {
            Math.multiplyExact(unitPriceVnd, count);
            throw new AssertionError("phép nhân int phải bị tràn");
        } catch (ArithmeticException expected) {
            System.out.println("nhân int: PASS (phát hiện tràn)");
        }

        long totalPriceVnd = (long) unitPriceVnd * count;
        if (totalPriceVnd != 50_000_000_000L) {
            throw new AssertionError("sai thành tiền");
        }
        System.out.println("nhân long: " + totalPriceVnd);

        BigInteger aboveLongMax = BigInteger.valueOf(Long.MAX_VALUE)
                .add(BigInteger.ONE);
        System.out.println("BigInteger: " + aboveLongMax);
    }
}
```

Open a terminal in the file's directory with JDK 17 or later:

```bash
javac -encoding UTF-8 InputBoundaryChecks.java
java InputBoundaryChecks
```

**Exact stdout when all checks pass:**

```text
null: PASS (thiếu giá trị)
rỗng: PASS (rỗng hoặc chỉ khoảng trắng)
toàn khoảng trắng: PASS (rỗng hoặc chỉ khoảng trắng)
âm -1: PASS (phải không âm)
min 0: PASS -> 0
min+1 1: PASS -> 1
thông thường 42: PASS -> 42
max-1 999999: PASS -> 999999
max 1000000: PASS -> 1000000
max+1 1000001: PASS (vượt 1000000)
sai chữ: PASS (không phải int hợp lệ)
số thập phân: PASS (không phải int hợp lệ)
có khoảng trắng: PASS (không phải int hợp lệ)
vượt int: PASS (không phải int hợp lệ)
nhân int: PASS (phát hiện tràn)
nhân long: 50000000000
BigInteger: 9223372036854775808
```

The program uses `AssertionError` directly so any failing check fails the program immediately. `NumberFormatException` is wrapped with a message matching `parseCount`'s contract. `Math.multiplyExact(int, int)` detects overflow via `ArithmeticException`; `(long) unitPriceVnd * count` converts one operand to `long` **before multiplication**, yielding the exact result `50_000_000_000`. `BigInteger` represents values larger than `Long.MAX_VALUE`, though applications still need sensible business and memory limits.

## 5. Overflow, data types, and special cases

- `int` is a 32-bit signed integer, and `long` is 64-bit. Integer addition/multiplication normally **does not throw an exception on overflow**; the result wraps around silently and becomes wrong. Use `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, and `Math.toIntExact` when overflow detection is needed.
- Casting **after** an operation overflows does not rescue the data: `long total = price * count;` still multiplies two `int` values first. Convert at least one operand to `long` before the operation when the result fits in `long`.
- If values may exceed even `long`, use `BigInteger` for arbitrary-size integers. For currency with fractional parts or rounding rules, consider `BigDecimal` with an explicit `RoundingMode`.
- When working with floating-point `double`/`float`, check `NaN`, `Infinity`, precision, and rounding error according to the contract; do not compare for exact equality mechanically in approximate calculations.
- Large values can also cause **high CPU/memory usage** even when the numeric type fits; validate data size bounds, string lengths, element counts, or input magnitude before allocating.

## 6. Testing workflow for practice exercises

1. Write the contract: input types, whether values can be missing, inclusive/exclusive bounds, normalization rules, and error reporting format.
2. Build a test table by equivalence classes: **valid**, **empty/missing**, **out of bounds**, **invalid format**, **outside data type range**, **overflow during calculation**.
3. Add cases right **below, on, and above each boundary**; distinguish `0` from `null` if they have different meanings.
4. Verify output values and error types/messages; small exercises can use a runner like the one above, while larger projects can move the same cases into JUnit to run automatically on edits.
5. Rerun after changes, especially when switching `int` to `long`, changing limits, or deciding to `trim()` input automatically. Tests should fail whenever behavior drifts from the contract.

**Easy mistakes to make:** testing only happy-path data; missing `MIN` and `MAX`; using `==` instead of `equals` to compare `String` content; invoking methods on `null`; treating whitespace strings as empty via `isEmpty`; letting arithmetic overflow before casting; swallowing exceptions and returning `0`; or writing tests without specific expected values. A short, intentional suite covering empty, boundary, invalid, and large values catches more bugs than a large set of random examples.
