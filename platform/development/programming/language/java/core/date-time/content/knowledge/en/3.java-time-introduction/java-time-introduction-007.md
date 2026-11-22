# DateTimeException and UnsupportedTemporalTypeException in java.time

When working with **java.time**, two exceptions you will frequently encounter are **DateTimeException** and **UnsupportedTemporalTypeException**. They help distinguish two different questions: **is the date-time value valid?** and **does the data type being used support the requested temporal field or unit?** Understanding the difference helps you choose the right API, validate input data, and find the root cause of errors without masking design flaws.

This lesson uses Java 17+ and representative types such as **LocalDate**, **LocalTime**, **LocalDateTime**, **Instant**, **ZonedDateTime**, **ChronoField**, and **ChronoUnit**.

## 1. Where Do the Two Exceptions Sit in the Hierarchy?

~~~text
java.lang.RuntimeException
└── java.time.DateTimeException
    ├── java.time.temporal.UnsupportedTemporalTypeException
    ├── java.time.format.DateTimeParseException
    └── java.time.zone.ZoneRulesException
~~~

These are the commonly encountered branches, not an exhaustive list of all subclasses.

- **DateTimeException**: a runtime exception used for date-time-related issues, such as an invalid date, inability to convert a value according to the requested rules, or inappropriate zone/offset information.
- **UnsupportedTemporalTypeException**: a **specialized DateTimeException**, typically thrown when accessing a **TemporalField** or operating with a **TemporalUnit** that is not supported by the current temporal type. Some **get()** methods also throw this exception when the field must be read using **getLong()**.
- **DateTimeParseException**: a specialized branch thrown when parsing date-time text fails, for example when the string does not match the format or contains an invalid date.
- **ZoneRulesException**: a branch related to failing to find zone rules or errors looking up zone rules.

Because they extend **RuntimeException**, Java does not force you to declare **throws** or **catch**. That does not mean every error should be ignored: you must identify the root cause, handle input errors, and fix incorrect API usage.

**Key relationship:** every **UnsupportedTemporalTypeException** is a **DateTimeException**, but not every **DateTimeException** is related to an unsupported field or unit.

## 2. When Does DateTimeException Occur?

### 2.1. Non-existent Calendar Date

~~~java
LocalDate invalid = LocalDate.of(2026, 2, 30);
~~~

The example above throws **DateTimeException** because February 2026 only has 28 days. Similar cases include month 13, day 31 of April, or February 29 in a non-leap year. **LocalDate.of(...)** validates the calendar date immediately when creating the object, helping avoid storing invalid values.

You must distinguish between a **calendar-valid value** and a **business-valid value**: 2026-02-28 is valid for LocalDate, but it may not be an allowed delivery date. Constraints such as "no Sunday deliveries" or "no overdue dates" must be validated separately using business rules.

### 2.2. Unparseable Input String

~~~java
LocalDate parsed = LocalDate.parse("2026-02-30");
~~~

The statement above throws **DateTimeParseException**, which is a **DateTimeException**, because the text has an ISO date shape but the calendar date is invalid. Passing the string "30/02/2026" directly to the default **LocalDate.parse(...)** also fails because it does not match the required ISO format.

In an API that receives user input, catch **DateTimeParseException** to return a specific input error. If you catch **DateTimeException** directly for all cases, it becomes hard to distinguish bad input data from implementation bugs when accessing temporal fields.

### 2.3. Applying an Offset or Zone Under Strict Rules

A **LocalDateTime** in a time zone with daylight saving time (DST) may not exist in reality. For example, **2026-03-08T02:30** in **America/New_York** falls within the gap where the clock jumps from 02:00 to 03:00.

~~~java
ZonedDateTime strict = ZonedDateTime.ofStrict(
        LocalDateTime.of(2026, 3, 8, 2, 30),
        ZoneOffset.ofHours(-5),
        ZoneId.of("America/New_York")
);
~~~

**ZonedDateTime.ofStrict(...)** throws **DateTimeException** when the local date-time and offset are invalid according to the zone rules. Conversely, **LocalDateTime.atZone(zone)** by default **shifts a time in a gap to a valid time**; do not assume that this call always throws an exception.

In appointment scheduling, behaviors like "reject non-existent times", "shift to the next valid time", or "require choosing an offset during an overlap" are business decisions and should be explicitly specified before handling.

## 3. When Does UnsupportedTemporalTypeException Occur?

**java.time** separates temporal types by semantics. A calendar date (**LocalDate**) has year, month, and day but **contains no time of day**; a wall-clock time (**LocalTime**) has hour, minute, and second but **contains no date**; **LocalDateTime** has both date and time but **is not tied to an offset or time zone**. Therefore, not every type can perform the same operations.

### 3.1. Reading an Unsupported TemporalField

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);

int day = date.get(ChronoField.DAY_OF_MONTH); // Valid: 24
int hour = date.get(ChronoField.HOUR_OF_DAY); // UnsupportedTemporalTypeException
~~~

**ChronoField.DAY_OF_MONTH** is a component of LocalDate, whereas **HOUR_OF_DAY** only makes sense when an object carries time-of-day information (such as LocalTime, LocalDateTime, or ZonedDateTime). Java does not automatically substitute 00:00: if a time is added, that should be a decision made by business logic.

Another example:

~~~java
LocalDateTime local = LocalDateTime.of(2026, 10, 24, 9, 0);
long seconds = local.getLong(ChronoField.INSTANT_SECONDS);
~~~

The statement above throws **UnsupportedTemporalTypeException**. **LocalDateTime** has no offset/ZoneId, so it cannot infer seconds since the UTC epoch on its own. To obtain an absolute point in time, you must determine a ZoneId or ZoneOffset based on business data and then convert to Instant:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant timestamp = local.atZone(zone).toInstant();
~~~

**Note:** **atZone(...)** has a default policy for DST; when scheduling in a zone with DST, validate gaps/overlaps according to business rules before locking in the timestamp.

### 3.2. Adding/Subtracting an Unsupported TemporalUnit

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);
LocalDate next = date.plus(1, ChronoUnit.DAYS);  // Valid
LocalDate wrong = date.plus(1, ChronoUnit.HOURS); // UnsupportedTemporalTypeException
~~~

**ChronoUnit.DAYS** works with LocalDate because the object represents a calendar date. **ChronoUnit.HOURS** is inappropriate: LocalDate does not represent hours of the day. Do not arbitrarily coerce LocalDate into LocalDateTime just to make the operation run; ask why the business logic needs the "hour" unit and whether the input has sufficient time/zone context.

Similarly:

- **LocalTime.plus(1, ChronoUnit.MONTHS)** is invalid because LocalTime has no calendar months.
- **LocalDate.plus(1, ChronoUnit.MONTHS)** is valid: it adds one calendar month.
- **Instant.plus(1, ChronoUnit.MONTHS)** is unsupported: a month does not correspond to a fixed number of seconds on the timeline. If calendar months are needed, convert to an appropriate zone/date and apply calendar rules.

### 3.3. Supported Fields Where get() Can Still Throw

This is one of the easiest points to confuse: **isSupported(field) == true** does not guarantee that **get(field)** will return an **int**. Some fields have a wide value range, so the API only allows reading them via **getLong(field)**.

~~~java
LocalDate epochDate = LocalDate.of(1970, 1, 1);

boolean available = epochDate.isSupported(ChronoField.EPOCH_DAY); // true
long epochDay = epochDate.getLong(ChronoField.EPOCH_DAY);       // 0
int wrong = epochDate.get(ChronoField.EPOCH_DAY); // UnsupportedTemporalTypeException
~~~

Similarly, **Instant** supports **ChronoField.INSTANT_SECONDS**, but it must be read using **getLong(...)**:

~~~java
Instant epoch = Instant.EPOCH;
long seconds = epoch.getLong(ChronoField.INSTANT_SECONDS); // 0
int wrong = epoch.get(ChronoField.INSTANT_SECONDS); // UnsupportedTemporalTypeException
~~~

The reason is not whether the value 0 fits in an **int**; the contract of **get(field)** does not support fields like **EPOCH_DAY** or **INSTANT_SECONDS** because their general value range exceeds the safe range of **int**. Do not try casting **(int)** or catching the exception to return a dummy 0: use **getLong(field)** or a semantic API such as **Instant.getEpochSecond()**.

## 4. Distinguishing TemporalField and TemporalUnit

| Concept | Representative | Question | Examples |
|---|---|---|---|
| **TemporalField** | **ChronoField** | Which component to read/set? | YEAR, DAY_OF_MONTH, HOUR_OF_DAY, EPOCH_DAY |
| **TemporalUnit** | **ChronoUnit** | Which unit to add, subtract, or measure by? | DAYS, HOURS, MONTHS, SECONDS |
| **TemporalAccessor** | interface for reading temporal values | Can this field be read? | isSupported(field), getLong(field), range(field) |
| **Temporal** | extended interface for adjustments | Can this unit be operated on? | plus(amount, unit), minus(amount, unit), isSupported(unit) |

APIs can share the same name **isSupported** while taking different parameter types:

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);

boolean canReadHour = date.isSupported(ChronoField.HOUR_OF_DAY); // false
boolean canAddHour = date.isSupported(ChronoUnit.HOURS);        // false
boolean canAddDay = date.isSupported(ChronoUnit.DAYS);          // true
~~~

**get(...)** and **getLong(...)** use **TemporalField**. **plus(amount, unit)** and **minus(amount, unit)** use **TemporalUnit**. A type might support reading a field without supporting the corresponding addition unit; check the right overload for what you intend to do.

## 5. Complete Java 17+ Example: Comparing Exception Cases

Create the file **DateTimeExceptionsDemo.java**:

~~~java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeParseException;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.UnsupportedTemporalTypeException;

public class DateTimeExceptionsDemo {

    private static void check(String name, Runnable operation) {
        try {
            operation.run();
            System.out.println(name + " -> OK");
        } catch (UnsupportedTemporalTypeException e) {
            System.out.println(name + " -> UnsupportedTemporalTypeException");
        } catch (DateTimeParseException e) {
            System.out.println(name + " -> DateTimeParseException");
        } catch (DateTimeException e) {
            System.out.println(name + " -> DateTimeException");
        }
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(1970, 1, 1);

        check("invalid-date", () -> LocalDate.of(2026, 2, 30));
        check("invalid-parse", () -> LocalDate.parse("2026-02-30"));
        check("hour-on-date", () -> date.get(ChronoField.HOUR_OF_DAY));
        check("hours-plus-date", () -> date.plus(1, ChronoUnit.HOURS));

        System.out.println("supports-epoch-day=" +
                date.isSupported(ChronoField.EPOCH_DAY));
        check("epoch-day-get", () -> date.get(ChronoField.EPOCH_DAY));
        System.out.println("epoch-day-getLong=" +
                date.getLong(ChronoField.EPOCH_DAY));

        check("instant-seconds-get",
                () -> Instant.EPOCH.get(ChronoField.INSTANT_SECONDS));
        System.out.println("instant-seconds-getLong=" +
                Instant.EPOCH.getLong(ChronoField.INSTANT_SECONDS));

        check("local-without-zone", () -> LocalDateTime
                .of(2026, 5, 1, 12, 0)
                .getLong(ChronoField.INSTANT_SECONDS));

        check("strict-dst-gap", () -> ZonedDateTime.ofStrict(
                LocalDateTime.of(2026, 3, 8, 2, 30),
                ZoneOffset.ofHours(-5),
                ZoneId.of("America/New_York")));
    }
}
~~~

Compile and run:

~~~bash
javac DateTimeExceptionsDemo.java
java DateTimeExceptionsDemo
~~~

Output on Java 17+ with the time zone rules in effect for New York in 2026:

~~~text
invalid-date -> DateTimeException
invalid-parse -> DateTimeParseException
hour-on-date -> UnsupportedTemporalTypeException
hours-plus-date -> UnsupportedTemporalTypeException
supports-epoch-day=true
epoch-day-get -> UnsupportedTemporalTypeException
epoch-day-getLong=0
instant-seconds-get -> UnsupportedTemporalTypeException
instant-seconds-getLong=0
local-without-zone -> UnsupportedTemporalTypeException
strict-dst-gap -> DateTimeException
~~~

**How to read the output:**

1. **invalid-date** has an invalid calendar date when creating the object: **DateTimeException**.
2. **invalid-parse** fails while parsing the string: **DateTimeParseException**, which belongs to the DateTimeException family.
3. **hour-on-date** and **hours-plus-date** require time-of-day information that LocalDate does not carry: **UnsupportedTemporalTypeException**.
4. **supports-epoch-day=true** yet **epoch-day-get** still fails, while **getLong** returns 0: choose the right accessor method.
5. **Instant.EPOCH** has the INSTANT_SECONDS field, but **getLong**, not **get**, is the appropriate API.
6. **local-without-zone** shows that LocalDateTime is not equivalent to Instant.
7. **strict-dst-gap** shows that requesting an invalid offset at a skipped local time leads to DateTimeException.

In the **check** method, the **catch** order must place the subclasses before **DateTimeException**; catching the superclass first makes the subclass branches unreachable and Java will report a compilation error. This method is for **demonstrating exception classification**; in production code, do not swallow every DateTimeException and let execution continue as if it succeeded.

## 6. Checking Support Before Operating

When working with a **TemporalAccessor** whose concrete type is unknown, you can check whether the field is supported and then use the appropriate method:

~~~java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.temporal.ChronoField;
import java.time.temporal.TemporalAccessor;
import java.util.OptionalInt;

public class ReadHourDemo {

    static OptionalInt hourOfDay(TemporalAccessor value) {
        if (!value.isSupported(ChronoField.HOUR_OF_DAY)) {
            return OptionalInt.empty();
        }
        return OptionalInt.of(value.get(ChronoField.HOUR_OF_DAY));
    }

    public static void main(String[] args) {
        System.out.println(hourOfDay(LocalDate.of(2026, 10, 24)));
        System.out.println(hourOfDay(LocalTime.of(9, 15)));
    }
}
~~~

Run:

~~~bash
javac ReadHourDemo.java
java ReadHourDemo
~~~

Output:

~~~text
OptionalInt.empty
OptionalInt[9]
~~~

In this case, **HOUR_OF_DAY** fits within the **int** range, so **get(...)** is appropriate. If you are handling **EPOCH_DAY** or **INSTANT_SECONDS**, use **getLong(...)**. If the contract only accepts LocalTime, define the parameter as **LocalTime** from the start to avoid type confusion. Using the **TemporalAccessor** interface makes sense when you genuinely accept multiple temporal types.

For addition on **Temporal**, check **isSupported(ChronoUnit.HOURS)** if you need to work with a polymorphic object. However, if adding an hour is a mandatory requirement and the passed-in type does not support it, **signaling a clear design or contract error** is better than silently converting it to another type based on assumptions.

Some custom TemporalField/TemporalUnit implementations may have their own rules. **isSupported(...)** is not a guarantee that every operation will succeed: failures can still happen due to value ranges, data state, or the operation itself.

## 7. Designing Error Handling at the Right Layer of Responsibility

### 7.1. Validating User Input: Clear Feedback, Preserving the Cause

Suppose an API receives **startDate** in ISO format **yyyy-MM-dd**. Converting the string to an object can be placed at the input boundary:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

public class DateInput {
    public static LocalDate parseStartDate(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("startDate is required");
        }
        try {
            return LocalDate.parse(raw);
        } catch (DateTimeParseException e) {
            throw new IllegalArgumentException(
                    "startDate must be a valid ISO date (yyyy-MM-dd)", e);
        }
    }
}
~~~

This is a utility class without a **main** method, usable in a controller/service or validation layer. **LocalDate.parse** uses the ISO format by default and validates the date. Wrapping it into **IllegalArgumentException** only illustrates how to construct an error message; HTTP 400 or application error codes should be decided at the API layer.

In production systems:

- Return a message that helps the user fix the specific field, without exposing stack traces or internal details.
- Preserve the **cause** when wrapping exceptions for logging and diagnostics.
- Check for **null**, blank strings, and business constraints as well, because not every invalid case is a DateTimeParseException.
- Distinguish parse errors from errors caused by operating on the wrong temporal type in code.

### 7.2. Programming Errors: Fix the Model and Called Methods

If a service throws **UnsupportedTemporalTypeException** because it tries to read **HOUR_OF_DAY** from **LocalDate**, the right fix is usually to:

- Change the model/input to **LocalDateTime** or **LocalTime** if the hour is genuinely needed; or
- Remove the hour access if the business domain only deals with dates; or
- Combine LocalDate with a time defined by business policy, instead of arbitrarily picking 00:00.

Returning **null**, **0**, or **1970-01-01** in a catch block hides missing information. Do not turn a design bug into fake data.

### 7.3. When You Need to Classify Errors from a Shared Library

An adapter might receive multiple types and distinguish them as follows:

~~~java
try {
    // A clearly defined temporal operation
} catch (UnsupportedTemporalTypeException e) {
    // Incompatible field/unit: check the data type and API call
} catch (DateTimeParseException e) {
    // Unparseable date-time text: input error
} catch (DateTimeException e) {
    // Other date-time issue: inspect context and cause
}
~~~

The snippet above **only illustrates the catch order** and is not a standalone program. Catch exceptions **close to where they can be handled effectively**. Do not wrap an entire HTTP request in a broad catch block and treat every DateTimeException as "invalid user input": some may come from internal application bugs.

### 7.4. Error Types Outside These Two Exceptions

Do not assume every date-time problem throws DateTimeException:

| Situation | Possible Exception / Behavior | Lesson |
|---|---|---|
| Passing **null** to an API that requires a non-null object | **NullPointerException** | Check null contracts separately |
| Invalid pattern when calling **DateTimeFormatter.ofPattern(...)** | **IllegalArgumentException** | Misconfigured formatter, distinct from parsing a string |
| Arithmetic overflow in certain operations | **ArithmeticException** or a temporal exception depending on the operation | Do not assume one catch type covers everything |
| Valid date that violates business rules | Application-defined exception/validation | java.time only validates temporal data validity |
| DST time automatically adjusted by **atZone** | May **not throw an exception** | Must check business policy, do not rely on catch |

Items marked "Possible" reflect behavior depending on the specific API; check the contract of the method being called during implementation.

## 8. Handling DST to Avoid Unexpected DateTimeException

Suppose a user schedules an appointment in New York at **2026-03-08 02:30**. This zone has a DST gap, so no Instant corresponds to that local time. Before creating the schedule, you can check:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

public class ResolveWallTimeDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        LocalDateTime requested = LocalDateTime.of(2026, 3, 8, 2, 30);
        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(requested);

        if (offsets.isEmpty()) {
            System.out.println("GAP: local time does not exist");
        } else if (offsets.size() == 2) {
            System.out.println("OVERLAP: choose an offset");
        } else {
            System.out.println("VALID: " + offsets.get(0));
        }
    }
}
~~~

Run:

~~~bash
javac ResolveWallTimeDemo.java
java ResolveWallTimeDemo
~~~

Output according to the zone rules in effect for New York in 2026:

~~~text
GAP: local time does not exist
~~~

**Meaning:** **getValidOffsets** returns 0 offsets for a gap, normally 1 for a valid time, and 2 for an overlap. If there are 2, the application must have a policy to pick an offset or let the user choose. If there are 0, the application must reject it or decide to shift the time. **ofStrict(...)** is suitable when you want to require an exact verified offset and fail if it is invalid.

These rules depend on the IANA time zone data provided by the JDK; future schedule data can change if local laws change. When scheduling in the future, store **LocalDateTime + ZoneId** (and gap/overlap handling details if needed) to preserve the original scheduling intent rather than storing only the converted timestamp.

## 9. Diagnostic Checklist When Seeing a Stack Trace

When you see **DateTimeException** or **UnsupportedTemporalTypeException**, check in order:

1. **Which exact exception class is it?** Look at the class name, stack trace, and the operation being performed; DateTimeParseException is a separate branch.
2. **What is the actual type of the object?** LocalDate has no time, LocalTime has no date, LocalDateTime has no zone, and Instant has no standalone calendar month.
3. **Are you querying a TemporalField or using a TemporalUnit?** Reading field information differs from adding/subtracting units.
4. **Is that field/unit supported?** Check **isSupported(...)** with the right parameter type when operating on polymorphic types.
5. **If the field is supported, did you mistakenly call get() instead of getLong()?** Especially for **EPOCH_DAY** and **INSTANT_SECONDS**.
6. **Is the date-time value valid?** Month/day, leap year, zone/offset, and DST gap/overlap cases.
7. **What contextual information is missing?** If you need an Instant from only a LocalDateTime, you must specify a valid zone or offset.
8. **Is it an input error or a code bug?** Invalid input needs clear validation feedback; invalid field access requires fixing the design.
9. **Have you tested boundary cases?** Feb 29, Feb 30, end of month, DST transitions, and the same timestamp across different time zones.

## 10. Common Pitfalls and How to Fix Them

| Error-Prone Code | Cause | How to Fix |
|---|---|---|
| **LocalDate.of(2026, 2, 30)** | Invalid calendar date | Validate input dates; handle DateTimeException at the appropriate boundary |
| **LocalDate.parse("2026-02-30")** | Text does not form a valid date | Handle DateTimeParseException and report the invalid field |
| **LocalDate.get(HOUR_OF_DAY)** | LocalDate has no hour | Use LocalTime/LocalDateTime or do not query the hour |
| **LocalTime.plus(1, MONTHS)** | LocalTime has no month | Use LocalDate/LocalDateTime if the business logic involves calendar dates |
| **LocalDate.get(EPOCH_DAY)** | get() does not support wide-range fields | Use getLong(EPOCH_DAY) |
| **Instant.get(INSTANT_SECONDS)** | get() is unsuitable for this field | Use getLong(...) or getEpochSecond() |
| **LocalDateTime.getLong(INSTANT_SECONDS)** | No zone/offset to determine Instant | Attach a valid ZoneId/ZoneOffset then call toInstant() |
| **ZonedDateTime.ofStrict(...)** on a DST gap | Invalid time/offset per ZoneRules | Check getValidOffsets and apply policy |
| **catch(DateTimeException)** before **catch(UnsupportedTemporalTypeException)** | Subclass catch is shadowed, code fails to compile | Catch subclasses before the superclass |
| **catch(DateTimeException) { return null; }** | Swallows errors, produces hard-to-diagnose state | Handle at the appropriate layer or let the error propagate |
| Assuming **atZone** always throws on a gap | The API has a default adjustment rule | Proactively check for anomalous time intervals |

## 11. Self-Check Questions

**1. Why doesn't LocalDate.of(2026, 2, 30) throw UnsupportedTemporalTypeException?** Because the LocalDate type fully supports day/month/year; only the **calendar value** is invalid. That is a DateTimeException.

**2. LocalDate.isSupported(EPOCH_DAY) returns true; does that mean date.get(EPOCH_DAY) is guaranteed to work?** No. **get()** only returns int; you must use **getLong(EPOCH_DAY)**.

**3. Why can't LocalDateTime read INSTANT_SECONDS?** It lacks zone/offset information to pinpoint a moment on the timeline. You must add context confirmed by business rules.

**4. Should you catch DateTimeException for both the parser and the service?** Only when you can genuinely handle general errors. For input, prefer **DateTimeParseException**; for unsupported field/unit errors, fix the model or API.

**5. Does a local time in a DST gap always produce DateTimeException?** No. **ofStrict** may throw, but **atZone** by default can shift to a valid time. You must know the exact method being called.

**6. When LocalDate.plus(1, HOURS) fails, is adding 00:00 to make it run the right fix?** Not necessarily. LocalDate has no time; adding hours requires business rules to determine the time and possibly the time zone. Do not fabricate data to bypass an exception.

**Remember:** **DateTimeException** indicates a general temporal error; **UnsupportedTemporalTypeException** specifically indicates that the temporal type does not support the field/unit or accessor being used; **DateTimeParseException** indicates a parsing error. Fix the root cause at the right layer: input values, data type semantics, accessor methods, or time zone rules.
