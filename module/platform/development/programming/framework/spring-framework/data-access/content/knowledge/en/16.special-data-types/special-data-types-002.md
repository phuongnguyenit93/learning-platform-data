# BigDecimal, Precision, and Scale for Decimal Data in Spring JDBC

Decimal data appears in unit prices, taxes, interest rates, ratios, weights, and measurements. When working with Spring Framework at the data access layer, a common mistake is holding a number in a Java `double` and writing it to a SQL `DECIMAL`/`NUMERIC` column, or passing a `BigDecimal` with too many fractional digits down to the database without first defining a rounding rule. Such mistakes can lead to small but accumulating discrepancies, inconsistent rounding, or errors when column limits are exceeded.

This lesson progresses from **the numeric representation of `BigDecimal`** to **SQL `DECIMAL(precision, scale)` constraints**, and then applies them in Spring `JdbcTemplate` and `NamedParameterJdbcTemplate`. The goal is to know what value will be stored, where to round, how to bind and read back the right type, and how to verify behavior on an actual JDBC driver.

## 1. Why Is BigDecimal Suitable for Decimal Data Requiring Exactness?

`double` and `float` store numbers in binary floating-point form. Many ordinary decimal numbers such as `0.1` cannot be represented exactly with a finite number of binary bits. Therefore:

~~~java
System.out.println(0.1 + 0.2);
~~~

Java's typical output is:

~~~text
0.30000000000000004
~~~

`BigDecimal` stores a value as an **unscaled integer value (`unscaled value`)** and a **`scale`**, mathematically:

~~~text
value = unscaledValue × 10^(-scale)
~~~

For example, `new BigDecimal("12.30")` has `unscaledValue = 1230` and `scale = 2`, so the exact value is `1230 × 10^-2 = 12.30`. `BigDecimal` is **immutable**: calls like `add`, `multiply`, or `setScale` return a new result object; they do not modify the original value.

`BigDecimal` enables exact decimal arithmetic **when inputs are already exact and operations are performed with appropriate rounding rules**. It does not retroactively fix data that already lost precision during `double` arithmetic, nor does it mean every division yields a terminating decimal result.

In applications, `BigDecimal` usually pairs with SQL `DECIMAL` or `NUMERIC` columns. However, you must distinguish the properties of **a Java value** from **the declared limits of a column**.

## 2. Precision and Scale of a BigDecimal

- **`precision()`:** the number of significant digits in `unscaledValue`, ignoring the minus sign and leading zeros. For zero, precision is 1.
- **`scale()`:** the number of digits to the right of the decimal point in standard notation when scale is non-negative. Scale can also be negative; in that case, the value is multiplied by a positive power of 10.
- **`unscaledValue()`:** the integer used with the scale to represent the value.
- **`toPlainString()`:** converts to a decimal string without exponential notation; useful for displaying the actual digits.

| Created from string | `unscaledValue` | `precision()` | `scale()` | Value |
| --- | ---: | ---: | ---: | --- |
| `"12.30"` | 1230 | 4 | 2 | 12.30 |
| `"123.456"` | 123456 | 6 | 3 | 123.456 |
| `"0.0010"` | 10 | 2 | 4 | 0.0010 |
| `"1000.00"` | 100000 | 6 | 2 | 1000.00 |
| `"0.00"` | 0 | 1 | 2 | 0.00 |
| `"1E+3"` | 1 | 1 | -3 | 1000 |

Therefore, `precision` **is not just the number of digits before the decimal point**, and `scale` **is not the total number of digits**. A value of `0.0010` has four digits after the decimal point but only two significant digits in its `BigDecimal` representation.

~~~java
BigDecimal amount = new BigDecimal("12.30");

System.out.println(amount.precision());      // 4
System.out.println(amount.scale());          // 2
System.out.println(amount.unscaledValue());  // 1230
System.out.println(amount.toPlainString());  // 12.30
~~~

This is a **Java code snippet** (requiring `import java.math.BigDecimal;`) illustrating the accessors, not a complete `main` class. Section 7 provides a standalone runnable Java 17+ program.

### Scale Can Change Even When the Numeric Value Does Not

~~~java
BigDecimal left  = new BigDecimal("2.0");   // precision 2, scale 1
BigDecimal right = new BigDecimal("2.00");  // precision 3, scale 2

System.out.println(left.compareTo(right));  // 0: same numeric value
System.out.println(left.equals(right));     // false: different scale
~~~

`compareTo` compares **numeric value**; `equals` compares both value and scale. Because `hashCode` is also affected by the representation, two values that are numerically equal but have different scales can behave differently when used as `HashMap` keys or `HashSet` elements. For business comparisons such as whether an amount is greater than 0 or two numbers are equal in value, `compareTo` is typically used. When scale is part of the data contract, normalize to the specified scale before comparing or storing.

`stripTrailingZeros()` can also alter scale significantly: `new BigDecimal("1000.00").stripTrailingZeros()` may end up with scale `-3` and `toString()` producing `1E+3`. Therefore, **do not use `stripTrailingZeros()` as a way to guarantee two decimal places when displaying money**; use `setScale(2, ...)` per business rules when two-digit formatting is required.

## 3. Precision and Scale of SQL DECIMAL(p, s)

With the standard declaration `DECIMAL(p, s)`:

- `p` is the **declared precision**: total number of decimal digits that can be stored per the column definition.
- `s` is the **declared scale**: number of digits in the fractional part.
- In the common form, `0 ≤ s ≤ p` and the integer part has at most `p - s` digits.

Example:

~~~sql
CREATE TABLE invoice_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    description VARCHAR(100) NOT NULL,
    amount DECIMAL(8, 2) NOT NULL,
    tax_rate DECIMAL(7, 5)
);
~~~

Column `amount DECIMAL(8,2)` fits normalized values like `1234.57` or `999999.99`. It reserves at most **6 integer digits and 2 fractional digits**, so `1000000.00` exceeds the limit of this definition. Column `tax_rate DECIMAL(7,5)` can serve rates with up to 5 fractional digits; it should not be forced to two digits like a monetary amount.

| Input | Target Column | Remarks |
| --- | --- | --- |
| `1234.57` | `DECIMAL(8,2)` | Fits within limit with exact 2 fractional digits |
| `999999.99` | `DECIMAL(8,2)` | Largest positive value for the standard `p=8, s=2` form |
| `1000000.00` | `DECIMAL(8,2)` | Exceeds integer-part capacity |
| `12.345` | `DECIMAL(8,2)` | Has an extra fractional digit; DB may round or error depending on engine and config |
| `0.07500` | `DECIMAL(7,5)` | Five-fractional-digit rate; should not be arbitrarily changed to scale 2 |

**Column precision differs from a Java value's precision.** For instance, `new BigDecimal("12.3")` has `precision() = 3`, `scale() = 1`; column `DECIMAL(8,2)` is defined for up to eight digits and scale two. The database/driver may read the value back as `12.30`, meaning the `BigDecimal` representation after reading has scale 2 even though the Java input had scale 1.

Do not check only `value.precision() <= p`. For example, `new BigDecimal("12345")` has precision 5, yet **cannot be stored intact** in `DECIMAL(5,2)` because the integer part requires 5 digits while the column only reserves 3. A useful check for the standard `0 ≤ s ≤ p` form is to normalize the scale first, then verify that the absolute value is less than `10^(p-s)`; Section 9 gives a concrete Java function.

Behavior when passing too many fractional digits is **not uniform across all DBs**. For instance, PostgreSQL `NUMERIC(p,s)` rounds to the column scale first, then rejects if the integer part exceeds the limit. Other DBs handle details differently. Therefore, **business rounding rules should be executed and tested in the application**, rather than implicitly relying on a database's rounding behavior.

## 4. Constructing BigDecimal Without Double Inaccuracy

The safe choice for exact decimal values is constructing from a decimal string or from integer data in the smallest unit:

~~~java
BigDecimal price = new BigDecimal("19.99");
BigDecimal rate = new BigDecimal("0.075");
BigDecimal quantity = BigDecimal.valueOf(3L);
BigDecimal result = price.multiply(quantity);
~~~

The values above preserve the exact meaning of the original strings or integer.

Avoid:

~~~java
BigDecimal unreliable = new BigDecimal(0.1);
~~~

The value `0.1` has already passed through `double`. The constructor taking `double` records the exact binary value of that `double`, so `unreliable` actually carries many extra fractional digits different from the intended decimal `0.1`.

~~~java
BigDecimal decimal = new BigDecimal("0.1");
BigDecimal viaValueOf = BigDecimal.valueOf(0.1);

System.out.println(decimal.equals(viaValueOf));     // true
System.out.println(decimal.equals(new BigDecimal(0.1))); // false
~~~

`BigDecimal.valueOf(double)` uses the `Double.toString(...)` string representation, so for the literal `0.1` it produces the same result as `"0.1"`. However, if the data **has already undergone `double` arithmetic**, earlier inaccuracies may still persist. When source data requires decimal exactness, avoid the `BigDecimal -> double -> BigDecimal` round-trip.

At API or file import boundaries, parse numeric strings according to explicit locale rules. For example, `new BigDecimal("1,25")` **does not** interpret a comma as a decimal separator; Java throws `NumberFormatException`. If the UI uses a decimal comma, parse the input according to a predefined format before creating the exact number. Do not blindly replace commas with periods when thousands separators might also appear.

## 5. setScale, RoundingMode, and MathContext Are Three Different Concepts

`setScale(n, mode)` determines **the number of digits after the decimal point in the result**. It returns a new `BigDecimal`; the original object is unchanged.

~~~java
BigDecimal amount = new BigDecimal("1.005");

System.out.println(amount.setScale(2, RoundingMode.HALF_UP));   // 1.01
System.out.println(amount.setScale(2, RoundingMode.HALF_EVEN)); // 1.00
~~~

- `HALF_UP`: when equidistant between two results, rounds away from 0; commonly used in certain monetary rules, though not the default for every domain.
- `HALF_EVEN`: when equidistant between two results, chooses the even last digit; commonly known as *banker's rounding*.
- `DOWN`: discards dropped digits toward 0. For negative numbers, toward 0 differs from `FLOOR`.
- `UNNECESSARY`: **refuses rounding**; throws `ArithmeticException` if the input cannot be represented exactly at the requested scale.

~~~java
new BigDecimal("12.340").setScale(2, RoundingMode.UNNECESSARY);
// Result 12.34: only drops a trailing zero, value unchanged.

new BigDecimal("12.345").setScale(2, RoundingMode.UNNECESSARY);
// Throws ArithmeticException because dropping digit 5 changes the value.
~~~

`setScale(2)` without a `RoundingMode` also requires no change in value; it throws `ArithmeticException` if rounding is needed. If the business policy is "accept at most two fractional digits and reject invalid values", `UNNECESSARY` is more appropriate than silent rounding.

### MathContext Limits Significant Digits, Not Decimal Places

`MathContext(precision, roundingMode)` applies **significant-digit precision to operation results**. For example:

~~~java
BigDecimal input = new BigDecimal("123.456");

System.out.println(input.setScale(2, RoundingMode.HALF_UP));
// 123.46: scale = 2

System.out.println(input.round(new MathContext(4, RoundingMode.HALF_UP)));
// 123.5: precision = 4, scale = 1
~~~

This is an **illustrative code snippet**, requiring imports for `java.math.BigDecimal`, `java.math.MathContext`, and `java.math.RoundingMode`. `new MathContext(4, ...)` is not equivalent to SQL column `DECIMAL(4,2)`. Column `DECIMAL(4,2)` also imposes a separate limit of at most two integer digits.

`MathContext.DECIMAL64` has a precision of 16 significant digits; do not interpret that as "16 digits after the decimal point". When multiplying/dividing across multiple steps, decide whether to round at each step or only at defined business checkpoints to avoid accumulating rounding errors.

### Division May Not Terminate

~~~java
BigDecimal one = new BigDecimal("1");
BigDecimal three = new BigDecimal("3");

// one.divide(three) throws ArithmeticException:
// the result 0.333... has no finite decimal representation.

BigDecimal third = one.divide(three, 4, RoundingMode.HALF_UP);
// third = 0.3333
~~~

Always specify scale and rounding mode for ratio divisions that are not guaranteed to yield a finite result. Do not wait until database persistence to decide how digits are truncated.

## 6. Scale Rules in Calculations and Comparisons

For **exact operations without passing a MathContext**, `BigDecimal` follows result scale rules:

| Operation | Exact Result Scale Usually Follows | Example |
| --- | --- | --- |
| `add`, `subtract` | Larger scale of the two operands | `1.20 + 2.3 = 3.50` (scale 2) |
| `multiply` | Sum of scales of the two operands | `1.20 × 3.00 = 3.6000` (scale 4) |
| `divide` | Has a preferred scale, but result is not necessarily finite | `1 / 3` needs a rounding rule |
| `setScale` | Specified scale; may require rounding | `2.345 -> 2.35` with `HALF_UP` |

Example calculating subtotal and tax:

~~~java
BigDecimal unitPrice = new BigDecimal("19.99");
BigDecimal count = BigDecimal.valueOf(3);
BigDecimal subtotal = unitPrice.multiply(count); // 59.97

BigDecimal taxRate = new BigDecimal("0.075");
BigDecimal exactTax = subtotal.multiply(taxRate); // 4.49775
BigDecimal tax = exactTax.setScale(2, RoundingMode.HALF_UP); // 4.50
BigDecimal total = subtotal.add(tax); // 64.47
~~~

Policies like "round tax per line item", "round tax on the whole invoice", or "round after every operation" can yield different results. This is a **business decision**, which must be documented and tested. `BigDecimal` ensures we execute the chosen rule accurately, but it does not choose the rule on behalf of the business.

When checking non-negativity:

~~~java
if (total.compareTo(BigDecimal.ZERO) < 0) {
    throw new IllegalArgumentException("Total must not be negative");
}
~~~

`compareTo` is used here because it compares **numeric value**, regardless of whether `total` has scale 1, 2, or 4. If the number needs to be used as a map/set key or compared with `equals`, normalize the scale consistently beforehand.

## 7. Standalone Java 17+ Example: Checking Precision, Scale, and Rounding

Create `DecimalMathDemo.java` containing the following complete program:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class DecimalMathDemo {
    private static void show(String label, BigDecimal number) {
        System.out.printf(
                "%s=%s p=%d s=%d%n",
                label,
                number.toPlainString(),
                number.precision(),
                number.scale());
    }

    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("123.450");
        show("amount", amount);
        show("scale2", amount.setScale(2, RoundingMode.UNNECESSARY));

        BigDecimal tax = new BigDecimal("19.99")
                .multiply(new BigDecimal("0.075"))
                .setScale(2, RoundingMode.HALF_UP);
        show("tax", tax);

        BigDecimal third = BigDecimal.ONE.divide(
                new BigDecimal("3"), 2, RoundingMode.HALF_UP);
        show("third", third);

        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        System.out.println("equals=" + a.equals(b));
        System.out.println("compare=" + a.compareTo(b));

        System.out.println("doubleConstructorExact="
                + new BigDecimal(0.1).equals(new BigDecimal("0.1")));
        System.out.println("valueOfDouble="
                + BigDecimal.valueOf(0.1).equals(new BigDecimal("0.1")));
    }
}
~~~

Compile and run with JDK 17+ (no dependencies needed):

~~~bash
javac DecimalMathDemo.java
java DecimalMathDemo
~~~

Exact stdout:

~~~text
amount=123.450 p=6 s=3
scale2=123.45 p=5 s=2
tax=1.50 p=3 s=2
third=0.33 p=2 s=2
equals=false
compare=0
doubleConstructorExact=false
valueOfDouble=true
~~~

`tax` is computed at the exact value `19.99 × 0.075 = 1.49925` before rounding to `1.50`. There is no intermediate `double` arithmetic. The last two lines show the risk of constructing directly from a `double` literal.

## 8. BigDecimal Data Flow Through Spring JDBC

Typical flow:

~~~text
Exact string/input
    ↓ parse
java.math.BigDecimal (precision(), scale())
    ↓ validate and apply business-defined RoundingMode
Column-normalized BigDecimal
    ↓ JdbcTemplate / NamedParameterJdbcTemplate binds JDBC parameter
PreparedStatement → DECIMAL/NUMERIC in DB
    ↓ query
ResultSet.getBigDecimal(...) or RowMapper
    ↓ compare value, check scale per DB/driver
Application data / response
~~~

`JdbcTemplate` does not know the business's monetary rounding rules. It passes parameters down to the JDBC driver and reads results. The database enforces `DECIMAL(p,s)` constraints; therefore, validation/normalization should happen **before passing values into INSERT/UPDATE statements**.

### 8.1. Writing with JdbcTemplate and PreparedStatement.setBigDecimal

Suppose the `amount` column has type `DECIMAL(8,2)`:

~~~java
BigDecimal amount = new BigDecimal("1234.567")
        .setScale(2, RoundingMode.HALF_UP);

int rows = jdbcTemplate.update(
        "INSERT INTO invoice_line (description, amount) VALUES (?, ?)",
        ps -> {
            ps.setString(1, "Service fee");
            ps.setBigDecimal(2, amount);
        });
~~~

This is a **DAO code snippet** with an existing `jdbcTemplate` variable, not a standalone Java class. `setBigDecimal` keeps the Java object as a decimal type rather than converting it to `double`. `rows` is **the number of affected rows**, not precision, scale, or a generated key value. Spring manages the PreparedStatement and connection lifecycle according to the transaction configuration.

You can pass `BigDecimal` directly in the shorthand form:

~~~java
jdbcTemplate.update(
        "INSERT INTO invoice_line (description, amount) VALUES (?, ?)",
        "Service fee",
        amount);
~~~

Spring usually binds parameters properly according to Java type and JDBC metadata. When a driver is sensitive to SQL type or `null` values, use a more explicit approach such as `PreparedStatement.setBigDecimal`/`setNull`, `SqlParameterValue`, or a parameter source with `Types.DECIMAL`.

### 8.2. Writing with NamedParameterJdbcTemplate and MapSqlParameterSource

~~~java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("description", "Service fee", Types.VARCHAR)
        .addValue("amount", amount, Types.DECIMAL);

int rows = namedJdbc.update(
        """
        INSERT INTO invoice_line (description, amount)
        VALUES (:description, :amount)
        """,
        params);
~~~

This is a **DAO code snippet** with `namedJdbc` and `amount` already initialized, not a standalone runnable program. `Types.DECIMAL` is **the parameter's SQL type code**; it **does not automatically apply scale 2, does not round, and does not widen the `DECIMAL(8,2)` limit**. Proactively normalize the number before binding.

If the column allows `NULL`, you can pass:

~~~java
MapSqlParameterSource nullableParams = new MapSqlParameterSource()
        .addValue("amount", null, Types.DECIMAL);
~~~

This snippet only creates a parameter source. If you pass `NULL` into a `NOT NULL` column like in `invoice_line`, the database will still reject it; `Types.DECIMAL` only tells the driver how to bind `NULL`, without altering constraints.

### 8.3. Reading with ResultSet.getBigDecimal or RowMapper

~~~java
BigDecimal stored = jdbcTemplate.queryForObject(
        "SELECT amount FROM invoice_line WHERE id = ?",
        BigDecimal.class,
        id);
~~~

This is a **DAO code snippet** with existing `jdbcTemplate` and `id` variables. If the SQL returns no rows, `queryForObject` throws the appropriate exception; if the SQL column holds `NULL`, the result may be `null`. Column reads can also use `RowMapper`:

~~~java
List<BigDecimal> amounts = jdbcTemplate.query(
        "SELECT amount FROM invoice_line ORDER BY id",
        (rs, rowNum) -> rs.getBigDecimal("amount"));
~~~

`ResultSet.getBigDecimal` retrieves the decimal value from the driver. **The scale of the read-back value may be represented differently by the driver/database than the input** (e.g., returning `12.30` for `12.3`). Compare values with `compareTo` and check scale separately if the business contract requires it. Do not use `getDouble` to read `DECIMAL` and reconstruct a `BigDecimal`, as this can introduce binary floating-point error into exact data.

## 9. Normalizing Scale and Checking Capacity of DECIMAL(p,s)

For standard decimal columns with `0 ≤ scale ≤ precision`, one way to control inputs consists of:

1. Checking non-null and business constraints such as non-negativity.
2. Deciding whether to **allow rounding** or **reject if there are too many fractional digits**.
3. Calling `setScale(s, mode)` to obtain the exact target scale.
4. **After rounding**, checking whether the absolute value is less than `10^(p-s)`. This step catches cases where rounding carries into the integer part.
5. Binding as `BigDecimal`; still leave the database's actual constraints as the final line of defense.

Java 17+ utility example:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public final class DecimalNormalizer {
    private DecimalNormalizer() {}

    public static BigDecimal forColumn(
            BigDecimal value, int precision, int scale,
            RoundingMode roundingMode) {
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(roundingMode, "roundingMode");

        if (precision < 1 || scale < 0 || scale > precision) {
            throw new IllegalArgumentException(
                    "Expected 0 <= scale <= precision, precision >= 1");
        }

        BigDecimal normalized = value.setScale(scale, roundingMode);
        BigDecimal exclusiveBound =
                BigDecimal.TEN.pow(precision - scale);

        if (normalized.abs().compareTo(exclusiveBound) >= 0) {
            throw new IllegalArgumentException(
                    "Value does not fit DECIMAL("
                    + precision + "," + scale + ")");
        }
        return normalized;
    }
}
~~~

Save as `DecimalNormalizer.java` to use as a standalone class; this code **compiles with JDK 17+**. The bound rule here applies to **standard decimal columns with p ≥ s ≥ 0**; some DBs support negative scale or scale exceeding `p` via vendor extensions, which require different rules. This function does not replace the maximum precision limit supported by each DB or business validation.

Example:

~~~java
BigDecimal a = DecimalNormalizer.forColumn(
        new BigDecimal("12.345"), 5, 2, RoundingMode.HALF_UP);
// a = 12.35, valid in DECIMAL(5,2)

BigDecimal b = DecimalNormalizer.forColumn(
        new BigDecimal("999.995"), 5, 2, RoundingMode.HALF_UP);
// Throws IllegalArgumentException:
// 999.995 rounds to 1000.00, exceeding the 999.99 limit.
~~~

The two statements above **illustrate calling the utility above**; the second line intentionally triggers an error, so it will not continue as a program expected to succeed. If automatic rounding is not allowed, pass `RoundingMode.UNNECESSARY` and handle `ArithmeticException` when the input has extra fractional digits.

Do not rely solely on `value.precision() <= p` because it can miss the integer-part limit. Conversely, increasing scale by adding trailing decimal zeros can increase `value.precision()` while **the numeric value remains unchanged**; what matters is representability in `(p,s)` after normalization.

## 10. Complete Spring JDBC Demo with DECIMAL(8,2) and H2

The example below uses **Java 17**, **Spring JDBC 6.1.14**, **H2 2.2.224**, and Gradle. It demonstrates two ways of binding decimals: a JDBC positional parameter with `setBigDecimal` and a named parameter with `Types.DECIMAL`; then reads the data back with `getBigDecimal` to verify the results.

Create the structure:

~~~text
decimal-jdbc-demo/
├── build.gradle
└── src/main/java/example/
    └── DecimalJdbcDemo.java
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.1.14'
    runtimeOnly 'com.h2database:h2:2.2.224'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.DecimalJdbcDemo'
}
~~~

File `src/main/java/example/DecimalJdbcDemo.java`:

~~~java
package example;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Types;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class DecimalJdbcDemo {
    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl(
                "jdbc:h2:mem:decimal_lecture;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("""
                CREATE TABLE invoice_line (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    description VARCHAR(100) NOT NULL,
                    amount DECIMAL(8,2) NOT NULL
                )
                """);

        BigDecimal input = new BigDecimal("1234.567");
        BigDecimal normalized = input.setScale(
                2, RoundingMode.HALF_UP);

        int first = jdbc.update(
                "INSERT INTO invoice_line (description, amount) "
                + "VALUES (?, ?)",
                ps -> {
                    ps.setString(1, "positional");
                    ps.setBigDecimal(2, normalized);
                });

        NamedParameterJdbcTemplate named =
                new NamedParameterJdbcTemplate(dataSource);
        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("description", "named", Types.VARCHAR)
                .addValue("amount",
                        new BigDecimal("5.20"), Types.DECIMAL);

        int second = named.update(
                "INSERT INTO invoice_line (description, amount) "
                + "VALUES (:description, :amount)",
                params);

        List<BigDecimal> stored = jdbc.query(
                "SELECT amount FROM invoice_line ORDER BY id",
                (rs, rowNum) -> rs.getBigDecimal("amount"));

        System.out.printf(
                "input=%s precision=%d scale=%d%n",
                input.toPlainString(), input.precision(), input.scale());
        System.out.printf(
                "normalized=%s precision=%d scale=%d%n",
                normalized.toPlainString(),
                normalized.precision(), normalized.scale());
        System.out.println("updated=" + first + "," + second);
        System.out.println("db=" + stored.get(0).toPlainString()
                + "," + stored.get(1).toPlainString());
        System.out.println("db-scale=" + stored.get(0).scale()
                + "," + stored.get(1).scale());
    }
}
~~~

Run in the directory containing `build.gradle` with Gradle installed:

~~~bash
gradle run
~~~

If the project already includes a Gradle Wrapper: use `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows. With a fresh H2 database and the exact versions above, **stdout produced by the program**:

~~~text
input=1234.567 precision=7 scale=3
normalized=1234.57 precision=6 scale=2
updated=1,1
db=1234.57,5.20
db-scale=2,2
~~~

Gradle also prints its own build logs. H2 stores the `DECIMAL(8,2)` column with scale two and the driver returns `BigDecimal` matching the column scale in this example. Another driver/DB might expose a different scale on read-back; therefore, integration tests must verify both **numeric value** and **representation** according to real requirements.

**Why the code works:** `DriverManagerDataSource` opens JDBC connections to in-memory H2; `DB_CLOSE_DELAY=-1` keeps the database alive across connections used by `JdbcTemplate` during the demo; Spring automatically manages statements and translates JDBC exceptions. `DriverManagerDataSource` is used here for instructional purposes, not as a recommended connection pooling choice for production.

Notice that the code explicitly normalizes `1234.567` to `1234.57` **before binding**. Without `setScale`, the result depends on the DB's rounding or error-reporting rules. When moving from H2 to PostgreSQL, MySQL, Oracle, or SQL Server, test with the deployed driver and column type.

## 11. Reading Column Metadata to Verify Precision and Scale

JDBC allows inspecting the precision/scale reported by the driver:

~~~java
List<String> metadata = jdbcTemplate.query(
        "SELECT amount FROM invoice_line WHERE 1 = 0",
        rs -> {
            var md = rs.getMetaData();
            return List.of(
                    "type=" + md.getColumnTypeName(1),
                    "precision=" + md.getPrecision(1),
                    "scale=" + md.getScale(1));
        });
~~~

This is a **DAO code snippet** with existing `jdbcTemplate` and table `invoice_line`; the query returns no data rows yet still provides column metadata. `ResultSetMetaData.getPrecision(1)` and `getScale(1)` reflect metadata supplied by the driver, which may be incomplete or differ from expectations for expressions/`CAST`. Actual column metadata can also be queried from `DatabaseMetaData.getColumns(...)` (e.g., `COLUMN_SIZE` and `DECIMAL_DIGITS`). Do not rely on metadata alone to replace schema migrations or insert/round-trip tests.

In a project with a fixed schema, `(p,s)` rules for each field are usually defined in the domain/application layer and migrations. If targeting multiple DBs, record the **DBMS, driver version, DDL, and return behavior** in test reports to catch differences.

## 12. Common Errors and How to Handle Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `new BigDecimal(0.1)` yields many extra digits | Input was already a binary `double` | Construct from exact decimal string or integer units; avoid going through `double` |
| `ArithmeticException` on `divide` | Non-terminating quotient or rounding required | Specify appropriate scale and `RoundingMode` |
| `ArithmeticException` on `setScale(2)` | Cannot reduce scale while remaining exact | Specify a rounding policy or use `UNNECESSARY` to reject explicitly |
| Database reports numeric overflow/out of range | Integer part or total length after rounding exceeds `DECIMAL(p,s)` | Normalize and check capacity before binding |
| Stored `12.345` but read `12.35` | DB/driver coerced to column scale | Round in Java per policy, test on a real DB |
| `equals` returns `false` for `2.0` and `2.00` | BigDecimal also compares scale | Use `compareTo` for numeric comparison, or unify scale |
| Read-back data has different scale than input | DB/driver normalizes decimal column | Test value and scale separately; do not assume input scale |
| Results have errors after API processing | Converting `BigDecimal` through `double` or JSON numbers parsed by client as floating-point | Keep exact decimals across steps; consider decimal strings at boundaries requiring lossless transfer |
| SQL `NULL` causes binding or constraint error | Driver lacks SQL type or column is `NOT NULL` | Use `Types.DECIMAL` when needed, check nullability and validation |
| Spring throws `DataAccessException` | JDBC driver/DB rejects value or SQL | Inspect root cause and SQLState, schema, parameter types, precision/scale |

**Do not automatically retry write commands solely because an exception occurred after sending to the database** without knowing the transaction outcome. Uncontrolled retries can create duplicate data. For multi-row operations, place actions in an appropriate transaction; a properly typed `BigDecimal` does not replace transactional consistency principles.

## 13. Essential Test Suite for DECIMAL/NUMERIC Data

When designing a Spring JDBC repository, test at minimum:

1. **Normal values:** `123.45` into `DECIMAL(8,2)`, read back and `compareTo` equals 0.
2. **Scale lower than column:** `12.3` into `DECIMAL(8,2)`; observe the read-back scale without assuming it is always 1 or 2 across all drivers.
3. **Excessive scale:** `12.345`: verify application policy (round to `12.35` or reject).
4. **Positive/negative bounds:** `±999999.99` fits `DECIMAL(8,2)`; `±1000000.00` must be caught as exceeding bounds.
5. **Carry from rounding:** `999999.995` rounded `HALF_UP` becomes `1000000.00`, must be rejected for `DECIMAL(8,2)`.
6. **Zero and negative sign:** `0`, `0.00`, `-0.00` after normalization have numeric value 0; scale is handled consistently.
7. **Rate calculations:** multiplication/division results, ties like `1.005` with `HALF_UP` and `HALF_EVEN`.
8. **NULL and wrong types:** bind nullable `DECIMAL` with `Types.DECIMAL`; confirm `NOT NULL` is rejected as specified by the schema.
9. **Round-trip on actual target DB:** run the same tests on the real database and driver, because passing on H2 does not prove production will behave identically in representation/rounding.
10. **Business consistency:** verify invoice totals when rounding per line item versus rounding at the total level; assert the chosen policy.

When comparing numeric content in tests, use `actual.compareTo(expected) == 0` to verify equal value, and assert `actual.scale()` separately **only when scale is a requirement of the data contract**. If you want to verify exact representation, you can assert `toPlainString()` after normalization; do not accidentally turn valid scale differences between drivers into business failures.

## 14. Checklist Before Storing Decimal Data

- **Source type:** construct `BigDecimal` from a decimal string/exact integer source; avoid passing through `double`.
- **Business rules:** define scale for each field (money, tax, rates, measurements may differ) and `RoundingMode` or rejection policy.
- **Schema:** choose `DECIMAL(p,s)`/`NUMERIC(p,s)` with sufficient integer and fractional digits for the data domain; do not assume all DBs handle out-of-range identically.
- **Processing order:** normalize scale, check bounds after rounding, then bind to JDBC.
- **Spring JDBC:** pass `BigDecimal`, `setBigDecimal`, or parameters with `Types.DECIMAL` as needed; never coerce to float/double.
- **Readback:** use `getBigDecimal`/`BigDecimal.class`, compare numerics with `compareTo`, check scale only when the contract truly requires it.
- **QA:** include unit tests for rounding and integration tests with the exact production DB/driver/schema.

**Key takeaway:** `BigDecimal.precision()/scale()` describes *a Java value*; `DECIMAL(p,s)` describes *the storage capacity of a SQL column*. `setScale` applies fractional rounding rules, `MathContext` limits total significant digits, and Spring JDBC passes data through the driver. The application layer must decide precision, rounding, and bounds before data is persisted.

## References

- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): definitions of unscaled value, scale, precision, operations, rounding, and `equals`/`compareTo`.
- [Java SE 21 — RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html): rounding modes.
- [Java SE 21 — MathContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/MathContext.html): operation precision and rounding policy.
- [Spring Framework — JDBC core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, parameter binding, updates, and `ResultSet` mapping.
- [Spring Framework — JDBC named parameters](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): `NamedParameterJdbcTemplate` and `MapSqlParameterSource`.
- [PostgreSQL — Numeric Types](https://www.postgresql.org/docs/current/datatype-numeric.html): example of `NUMERIC(p,s)` declaration behavior, rounding, and column limits (PostgreSQL-specific).
