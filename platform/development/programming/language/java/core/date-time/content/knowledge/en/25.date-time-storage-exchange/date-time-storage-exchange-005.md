# java.sql.Date with LocalDate and java.sql.Time with LocalTime

## 1. Two Type Pairs with the Same Meaning, Different API Generations

When working with JDBC, you may encounter the two legacy classes `java.sql.Date` and `java.sql.Time`. They serve to map SQL data types through JDBC, whereas modern business code is usually better suited to `java.time` types.

| Meaning to Represent | Modern Java Type | Legacy JDBC Bridge Class |
| --- | --- | --- |
| A date consisting of year, month, and day | `LocalDate` | `java.sql.Date` |
| A time of day, without a date or offset | `LocalTime` | `java.sql.Time` |

For example, a birth date or business date can use `LocalDate`. Daily opening hours can use `LocalTime`. Neither represents a single instant on the timeline.

Do not confuse `java.sql.Date` with `java.util.Date`:

- `java.util.Date` is commonly used to represent an instant based on milliseconds.
- `java.sql.Date` is used by JDBC for `DATE` type date values.
- `java.sql.Time` is used by JDBC for `TIME` type time values.
- The two SQL classes extend `java.util.Date` for historical design reasons, but that does not mean they share the full usage semantics.

The mapping in this article refers to the semantics of JDBC `DATE` and `TIME` types. When applying this to a specific DBMS, you still need to check the column type, precision, and driver behavior; do not just look at an SQL type name and assume all storage characteristics.

## 2. Converting Between java.sql.Date and LocalDate

Two direct methods:

```java
LocalDate local = LocalDate.of(2024, 2, 29);

java.sql.Date sql = java.sql.Date.valueOf(local);
LocalDate restored = sql.toLocalDate();
```

According to [java.sql.Date](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Date.html), `valueOf(LocalDate)` creates an SQL value with the same year, month, and day. `toLocalDate()` extracts the date components to create a `LocalDate`.

This is a conversion based on **calendar date** semantics, not an operation to "convert an instant to UTC". There is no need to go through `Instant` just to convert between these two date types.

Easily confused method names:

| Call | Meaning |
| --- | --- |
| `java.sql.Date.valueOf(localDate)` | Creates the JDBC date class from `LocalDate` |
| `sqlDate.toLocalDate()` | Reads the date back using the modern API |
| `java.util.Date.from(instant)` | Creates the legacy class for an instant; not a pure date mapping |
| `sqlDate.toInstant()` | Not supported |

`java.sql.Date` is a legacy class that can be mutated via methods such as `setTime`. `LocalDate` is immutable. Converting to `LocalDate` at the data-reading boundary prevents business logic from holding a mutable SQL object that could be changed unintentionally.

### 2.1. Do Not Use Legacy Constructors with Shifted Year and Month Conventions

The multi-component constructor of `java.sql.Date` has been marked deprecated and uses legacy conventions such as year minus 1900 and 0-based months. This is easily confused with `LocalDate.of`, which uses the actual year and months `1..12`.

Use `Date.valueOf(localDate)` instead of subtracting 1900 or 1 yourself. When converting from text data, parse into `LocalDate` according to the chosen contract first, then create the JDBC class if needed.

### 2.2. Do Not Treat getTime() as the Business Essence of a Date

The legacy SQL class still wraps a millisecond value and uses the interpretation rules of the legacy API. That millisecond value is not an appropriate contract for exchanging "birth date 2024-02-29" across zones.

Do not use the following chain of operations as a default formula:

```java
// Illustrates an inappropriate approach for a pure date:
// Instant.ofEpochMilli(sqlDate.getTime())
//        .atZone(ZoneId.of("UTC"))
//        .toLocalDate();
```

Interpreting milliseconds in UTC can shift the date relative to the context in which the legacy class was created. When the input is genuinely a `java.sql.Date` carrying a JDBC date, use `toLocalDate()` as intended by the API.

Legacy classes can depend on the time zone environment when constructing and reading components. Do not change the default time zone between conversion steps and expect all legacy objects to keep the same interpretation. In real integrations, unify driver/environment configuration and verify read–write dates, especially near boundaries.

## 3. Converting Between java.sql.Time and LocalTime

Two formally symmetric methods:

```java
LocalTime local = LocalTime.of(12, 34, 56);

java.sql.Time sql = java.sql.Time.valueOf(local);
LocalTime restored = sql.toLocalTime();
```

However, there is an important limitation: [java.sql.Time](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Time.html) only preserves the hour, minute, and second components through the `valueOf(LocalTime)`/`toLocalTime()` pair. The nanosecond part of `LocalTime` is dropped when passing through this bridge.

Example:

```java
LocalTime precise = LocalTime.of(12, 34, 56, 123_456_789);
java.sql.Time sql = java.sql.Time.valueOf(precise);
LocalTime restored = sql.toLocalTime();
```

The original value is `12:34:56.123456789`; the returned result is `12:34:56`, with `getNano() == 0`. The lost information cannot be recovered from that `java.sql.Time` instance itself.

This is not merely a matter of `toString()` hiding fractional seconds. Comparing `precise.equals(restored)` returns `false`: the time value has genuinely changed.

### 3.1. Choosing a Policy for Fractional Seconds

There are three common approaches:

| Policy | When Appropriate |
| --- | --- |
| Reject if `getNano() != 0` | The contract only allows second-level precision and silent truncation is unwanted |
| Explicitly drop fractional seconds | Business logic accepts second-level precision |
| Avoid the `java.sql.Time` bridge and use an appropriate modern mapping | Fractional seconds must be preserved and the driver/column supports them |

If choosing to drop fractional seconds, explicitly writing `localTime.withNano(0)` or `truncatedTo(ChronoUnit.SECONDS)` before the conversion step makes that decision clear. This is truncation, not rounding: `12:34:56.999` becomes `12:34:56`, not `12:34:57`.

If rounding according to another rule is required, state the policy and consider the case where it rolls over into a new day. `LocalTime` itself does not contain a date to hold day-increment information.

### 3.2. SQL TIME Is Not Synonymous with Duration

`LocalTime` represents a time of day. It does not represent "took 36 hours to process" or "a negative difference of 2 hours". Those quantities carry duration semantics and typically require `Duration` or another appropriate storage type.

A DBMS may give time columns their own specific capabilities. A column being named `TIME` is not enough to guarantee that the entire value domain of that column maps properly to `LocalTime`. Check the type contract before choosing the Java type.

## 4. toInstant() on Both SQL Classes Is Always Rejected

Both `java.sql.Date.toInstant()` and `java.sql.Time.toInstant()` throw `UnsupportedOperationException`:

- A pure date lacks a time and zone to determine an instant.
- A pure time lacks a date and zone to determine an instant.

Do not rely on inheritance to call a utility meant for `java.util.Date` without knowing the actual runtime class:

```java
java.util.Date reference = java.sql.Date.valueOf(
        LocalDate.of(2024, 2, 29));

// reference.toInstant() still invokes java.sql.Date's method.
```

A reference typed as `java.util.Date` does not change the actual underlying object. The call is still rejected.

If business logic needs to turn a date into the start of the day, an explicit policy must be added, such as `localDate.atStartOfDay(businessZone).toInstant()`. This creates an instant according to a new rule, rather than reading an instant already present in the pure date.

This article does not use `Timestamp` to "patch" missing information. Switching to a class with both date and time by inserting a fake date or time distorts the input meaning if there is no corresponding business requirement.

## 5. Complete Java 17+ Program

Save as `SqlDateTimeBridgeDemo.java`. The program uses the standard library and requires no external database or driver.

```java
import java.sql.Time;
import java.time.LocalDate;
import java.time.LocalTime;

public class SqlDateTimeBridgeDemo {
    static java.sql.Date toSqlDate(LocalDate value) {
        return value == null ? null : java.sql.Date.valueOf(value);
    }

    static LocalDate fromSqlDate(java.sql.Date value) {
        return value == null ? null : value.toLocalDate();
    }

    static LocalTime fromSqlTime(Time value) {
        return value == null ? null : value.toLocalTime();
    }

    static Time toSqlTimeRejectFraction(LocalTime value) {
        if (value == null) {
            return null;
        }
        if (value.getNano() != 0) {
            throw new IllegalArgumentException("Fractional seconds rejected");
        }
        return Time.valueOf(value);
    }

    static void unsupported(String label, Runnable operation) {
        try {
            operation.run();
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + " -> "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        LocalDate birthday = LocalDate.of(2024, 2, 29);
        java.sql.Date sqlDate = toSqlDate(birthday);
        LocalDate restoredDate = fromSqlDate(sqlDate);

        System.out.println("local date = " + birthday);
        System.out.println("SQL date = " + sqlDate);
        System.out.println("restored date = " + restoredDate);
        System.out.println("date equal = " + birthday.equals(restoredDate));

        LocalTime precise = LocalTime.of(12, 34, 56, 123_456_789);
        Time sqlTime = Time.valueOf(precise);
        LocalTime restoredTime = fromSqlTime(sqlTime);

        System.out.println("local time = " + precise);
        System.out.println("SQL time = " + sqlTime);
        System.out.println("restored time = " + restoredTime);
        System.out.println("restored nano = " + restoredTime.getNano());
        System.out.println("exact time equal = "
                + precise.equals(restoredTime));
        System.out.println("seconds equal = "
                + precise.withNano(0).equals(restoredTime));

        try {
            toSqlTimeRejectFraction(precise);
        } catch (IllegalArgumentException ex) {
            System.out.println("strict bridge = " + ex.getMessage());
        }

        Time wholeSecond = toSqlTimeRejectFraction(
                LocalTime.of(12, 34, 56));
        System.out.println("strict whole second = " + wholeSecond);
        System.out.println("null date preserved = "
                + (fromSqlDate(toSqlDate(null)) == null));
        System.out.println("null time preserved = "
                + (fromSqlTime(toSqlTimeRejectFraction(null)) == null));
        System.out.println("midnight preserved = "
                + Time.valueOf(LocalTime.MIDNIGHT).toLocalTime()
                        .equals(LocalTime.MIDNIGHT));

        unsupported("SQL date toInstant", () -> sqlDate.toInstant());
        unsupported("SQL time toInstant", () -> sqlTime.toInstant());

        java.util.Date baseReference = sqlDate;
        unsupported("base reference toInstant",
                () -> baseReference.toInstant());
    }
}
```

Compile and run:

```shell
javac --release 17 SqlDateTimeBridgeDemo.java
java SqlDateTimeBridgeDemo
```

Stdout:

```text
local date = 2024-02-29
SQL date = 2024-02-29
restored date = 2024-02-29
date equal = true
local time = 12:34:56.123456789
SQL time = 12:34:56
restored time = 12:34:56
restored nano = 0
exact time equal = false
seconds equal = true
strict bridge = Fractional seconds rejected
strict whole second = 12:34:56
null date preserved = true
null time preserved = true
midnight preserved = true
SQL date toInstant -> UnsupportedOperationException
SQL time toInstant -> UnsupportedOperationException
base reference toInstant -> UnsupportedOperationException
```

The bridge methods in the program have clear contracts:

- `toSqlDate` and `fromSqlDate` preserve `null` and convert date semantics.
- `fromSqlTime` preserves `null` and extracts hour–minute–second.
- `toSqlTimeRejectFraction` rejects any value with fractional seconds instead of silently losing information.
- `unsupported` is only for observing unsupported calls in the example.

The program shows that midnight is a valid value, distinct from `null`. It also shows that declaring a reference with the superclass does not change the `toInstant` behavior of the actual SQL object.

## 6. SQL NULL Must Be Preserved or Handled by Policy

`ResultSet.getDate` and `getTime` can return `null` when the column is SQL `NULL`. Calling `rs.getDate("business_date").toLocalDate()` directly will throw `NullPointerException` in that case.

The following legacy JDBC reading snippet shows **illustrative methods**, which need to be placed in a class and used with a `ResultSet` positioned on a valid row:

```java
static LocalDate readDateLegacy(
        java.sql.ResultSet rs, String column)
        throws java.sql.SQLException {

    java.sql.Date value = rs.getDate(column);
    return value == null ? null : value.toLocalDate();
}

static LocalTime readTimeLegacy(
        java.sql.ResultSet rs, String column)
        throws java.sql.SQLException {

    java.sql.Time value = rs.getTime(column);
    return value == null ? null : value.toLocalTime();
}
```

`null` can be kept in the data object, wrapped in `Optional` at an appropriate interface, or rejected if the field is required. Whichever choice is made must accurately reflect the meaning of the data domain.

Do not substitute SQL `NULL` with:

- `1970-01-01` for a date.
- `00:00` for a time.
- The machine's current date/time.

All of those values have real meaning. Using them to mean "no data" creates records that appear valid and become hard to distinguish later.

When writing with JDBC, you can express a typed `NULL` using `setNull(index, Types.DATE)` or `setNull(index, Types.TIME)`. There is no need to pass `null` through `Date.valueOf` or `Time.valueOf`; these methods do not treat `null` as a default date/time.

## 7. When Modern JDBC Is Available, Use java.time Directly

JDBC 4.2 added support for working with modern date-time types. When the driver supports the corresponding mapping, you can pass `LocalDate` for `DATE` and `LocalTime` for `TIME` instead of going through the legacy SQL classes.

Parameter binding example, assuming `statement` is a `PreparedStatement` already created with the proper statement:

```java
statement.setObject(1, businessDate, java.sql.Types.DATE);
statement.setObject(2, openingTime, java.sql.Types.TIME);
```

This is an integration snippet, not a standalone program. `businessDate` has type `LocalDate` and `openingTime` has type `LocalTime`. [PreparedStatement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html) provides `setObject` with the target SQL type to express how the mapping should be performed.

Reading as the desired type:

```java
LocalDate businessDate =
        rs.getObject("business_date", LocalDate.class);
LocalTime openingTime =
        rs.getObject("opening_time", LocalTime.class);
```

[ResultSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html) provides `getObject` accepting the target Java type when the conversion is supported. For SQL `NULL`, the resulting object is `null`.

For potentially `null` inputs, an illustrative binding method that handles values completely is:

```java
static void bindDateAndTime(
        java.sql.PreparedStatement statement,
        LocalDate date,
        LocalTime time) throws java.sql.SQLException {

    if (date == null) {
        statement.setNull(1, java.sql.Types.DATE);
    } else {
        statement.setObject(1, date, java.sql.Types.DATE);
    }

    if (time == null) {
        statement.setNull(2, java.sql.Types.TIME);
    } else {
        statement.setObject(2, time, java.sql.Types.TIME);
    }
}
```

The method assumes parameters 1 and 2 actually correspond to two matching columns in the SQL statement. Preparing the statement, executing it, and closing resources belong to the integration code using this method.

### 7.1. "Using LocalTime Directly" Does Not Guarantee Every Nanosecond Is Stored

The ability to preserve fractional seconds depends on:

- The declared column type and precision.
- The DBMS value domain.
- The driver version and configuration.
- How the driver handles values that do not fit the column's precision.

Avoiding `java.sql.Time` avoids the known nanosecond-dropping step of the legacy bridge method pair; it does not make a `TIME(0)` column suddenly store nine digits of fractional seconds.

Integration verification requires reading the value back from the database and comparing it against the contract. The non-DB program above only demonstrates the conversion behavior of the Java classes, not the storage behavior of a specific DBMS.

### 7.2. Do Not Catch Every SQLException and Silently Fall Back to the Legacy Path

A driver that does not support a mapping may report a conversion error or an unsupported-feature error. That is information that must be distinguished from a malformed SQL query, wrong column name, lost connection, or data error.

If a legacy compatibility path must be maintained, choose and verify it intentionally according to the driver in use. In particular, do not fall back to `java.sql.Time` silently when the system requires fractional seconds; the result may technically succeed while losing data.

## 8. Time Zones, Ranges, and Mutability of Legacy Classes

### 8.1. Time-Zone-Less Semantics Differ from Environment-Dependent Legacy Implementations

`LocalDate` and `LocalTime` do not carry a time zone. However, `java.sql.Date`/`Time` use the millisecond foundation of the legacy API, and the driver may have to interpret it according to the default time zone or corresponding configuration.

JDBC overloads accepting `Calendar` can affect how the driver constructs or reads legacy values. They do not attach a `ZoneId` to `LocalDate` or `LocalTime`. Do not arbitrarily mix creating milliseconds in one zone with reading components in another.

For legacy systems, verify the entire path: business value → JDBC call → actual column → read call → business value. Keep the environment explicit and prefer modern mappings when they are properly supported for your requirements.

### 8.2. Value Ranges Are Not Uniform Across All Classes and Databases

`LocalDate` supports a wide range of years. That does not mean the target system's driver or `DATE` column supports every value in that range.

Data far in the past can also encounter calendar rule differences between legacy classes and `java.time`'s proleptic ISO calendar. For applications that only allow a specific year range, validate against both the business range and the target system's capabilities. Do not treat a modern 2024 example as proof for all historical dates.

### 8.3. Do Not Let Mutable JDBC Classes Leak into the Business Domain

`java.sql.Date` and `Time` can be mutated through the legacy API; `LocalDate` and `LocalTime` are immutable. Convert immediately upon reading/writing so that business logic only sees modern values.

Do not store a shared SQL object and let other code mutate it via `setTime` while it is being processed. Using immutable types in the business layer prevents unexpected changes to dates and times.

You should also write out full class names where confusion is possible: `java.sql.Date` and `java.util.Date` share the short name `Date`. Do not wildcard-import both and force readers to guess which class is being used.

## 9. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `sqlDate.toInstant()` | `UnsupportedOperationException` | Use `toLocalDate` for a pure date |
| Calling `sqlTime.toInstant()` | Missing date, unsupported operation | Use `toLocalTime` for a pure time |
| Converting via epoch milliseconds to get a date in UTC | May shift the date relative to the input meaning | Use the type-appropriate bridge method |
| Assuming `Time.valueOf(LocalTime)` preserves nanoseconds | Loss of fractional seconds | Choose an explicit precision policy |
| Checking only `toString` to verify data preservation | May miss value changes | Compare `LocalTime` and `getNano` |
| Calling conversion on an SQL `NULL` value | `NullPointerException` | Check for `null` at the boundary |
| Replacing `NULL` with midnight or year 1970 | Mixes missing data with real values | Preserve or reject missing data per contract |
| Using `TIME` to store all kinds of durations | Wrong domain and semantics | Distinguish time of day from duration |
| Using a `java.util.Date` reference and treating the SQL object as a normal instant | Invokes the wrong behavior of the actual class | Check the exact type and semantics |
| Assuming a modern driver automatically preserves all precision | Data can still be truncated or rounded | Verify against the actual column type |

## 10. Self-Verification and Practice

1. Convert `LocalDate.of(2024, 2, 29)` to `java.sql.Date` and read it back. Verify using `equals`, not reference comparison.
2. Convert a `LocalTime` with non-zero fractional seconds through `java.sql.Time`. Verify that the returned time has `getNano() == 0` and is not equal to the original value.
3. Use a whole-second time and verify that the fraction-rejecting bridge still accepts it.
4. Use midnight to confirm it is a valid value, not a `NULL` signal.
5. Test the helpers with `null` on both the read and write sides. The `null`-preservation policy must be consistent.
6. Assign a `java.sql.Date` to a `java.util.Date` variable and call `toInstant` in a failure-catching example. Explain the result based on the actual runtime class of the object.
7. If you have a suitable DBMS and driver, create a separate read–write verification for a date column and a time column with a declared fractional-second precision. Clearly state which values must be preserved and which are rejected.
8. For a required column, modify the mapping layer to report a missing-data error instead of substituting a fake date or time.
9. Describe where to place conversions in an application so that business functions do not need to import `java.sql.Date` or `java.sql.Time`.
10. Before replacing a legacy JDBC path with a modern one, cross-check column semantics, `NULL` handling, precision, and read-back results; do not just check that the statement throws no errors.

The goal is to preserve exact date and time semantics across the JDBC boundary. For pure dates, use the `Date.valueOf`/`toLocalDate` bridge when legacy classes are needed; for times, explicitly account for `Time`'s fractional-second limitation and the driver's direct mapping capabilities.
