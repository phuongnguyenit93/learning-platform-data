# Passing `Clock` into a Business Class

## 1. The business class uses time; the caller chooses the time source

A book-lending service needs to record when a slip is issued, determine the borrow date, and calculate the due date. If the service calls `Instant.now()` or `LocalDate.now()` internally, the time source becomes a hidden detail. Tests cannot easily place the service on a specific date, and zone rules may depend on the machine running the code.

Passing a `Clock` into the class means providing the time source as an explicit dependency. The class still performs the same business logic; the assembly site decides whether to use the system clock in production or a fixed clock in tests.

[Java SE 21 — Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html) describes how to use a replaceable clock source and pass it into code that needs "now". A dependency injection framework is not required: a plain Java constructor already accomplishes this.

```text
Initialization site
    chooses Clock and zone configuration
                 ↓
Business class receives dependency
    reads instant → applies rules → returns result
```

What changes is who owns the decision of choosing the time source, not adding an "if under test" branch into the algorithm.

## 2. Constructor design

A common structure is to accept a required `Clock` and hold it in a `final` field:

```java
// Illustrates the structure inside a class, not a standalone program.
private final Clock clock;

LoanService(Clock clock) {
    this.clock = Objects.requireNonNull(clock);
}
```

The constructor expresses that the class needs a time source to do its work. `requireNonNull()` rejects missing configuration early; `final` prevents another operation from silently swapping the time source after the object is constructed.

This approach does not force the class to accept `Clock.fixed()` directly. It only accepts the `Clock` contract; the concrete clock is chosen at the initialization site. A system clock still keeps ticking even though the field reference is `final`: `final` does not mean time is frozen.

If a class only computes from an already-supplied instant or date, it may not need to hold a `Clock`. For example, a pure function that takes a borrow date and computes the due date is easy to test directly. Place the clock source in the class that is actually responsible for deciding when to read "now", rather than passing it through every function just for a date addition.

## 3. Instant and business zone must have clear roles

`Clock` has both `instant()` and `getZone()`. There are two reasonable ways to organize them depending on the contract:

| Organization | How the date is read | When it fits |
| --- | --- | --- |
| The clock's zone is the business zone | `LocalDate.now(clock)` | The time source and zone are always configured together |
| The instant source and business zone are supplied separately | Read an `Instant`, then `LocalDate.ofInstant(instant, businessZone)` | You need to decouple the shared time source from the business unit's zone |

The program in this lesson chooses the second approach. `Clock` provides the instant, while `businessZone` determines the library's date. Therefore, a test clock can carry the UTC zone while the borrow date is still computed using the `Asia/Ho_Chi_Minh` zone passed separately.

[Java SE 21 — LocalDate.ofInstant()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#ofInstant(java.time.Instant,java.time.ZoneId)) obtains a date from an instant and a specific zone. This is not an operation that modifies the instant; one instant can belong to two different dates when viewed in two different zones.

There is no need to pass two zone configurations if the design has already chosen the clock's zone as the single source. What must be avoided is code that reads `LocalDate.now(clock)` in one place while converting with a different zone in another without a clear contract.

## 4. Rules of the book-lending service example

The example only computes the receipt details, with the following contract:

- The book ID must have content.
- `issuedAt` is an instant observed from the clock.
- `borrowedOn` is the date at the library according to `businessZone` from that exact instant.
- `dueOn` is the borrow date plus 14 calendar days.

The example does not persist data to storage and does not decrement book inventory; it isolates the time dependency for observation. "Plus 14 days" here means `plusDays(14)`, without adding holidays or business-day rules.

## 5. Complete runnable program

Save the code to `BusinessClockDemo.java`. The program uses Java 17 or later and requires no external libraries. Failed expectations throw `AssertionError` without needing `-ea` enabled:

```java
import java.time.*;
import java.util.Objects;

public class BusinessClockDemo {
    record LoanReceipt(String bookId, Instant issuedAt,
                       LocalDate borrowedOn, LocalDate dueOn) {}

    static final class LoanService {
        private final Clock clock;
        private final ZoneId businessZone;

        LoanService(Clock clock, ZoneId businessZone) {
            this.clock = Objects.requireNonNull(clock);
            this.businessZone = Objects.requireNonNull(businessZone);
        }

        LoanReceipt borrow(String bookId) {
            Objects.requireNonNull(bookId);
            if (bookId.isBlank()) {
                throw new IllegalArgumentException("bookId is blank");
            }
            Instant observedNow = clock.instant();
            LocalDate borrowedOn = LocalDate.ofInstant(observedNow, businessZone);
            LocalDate dueOn = borrowedOn.plusDays(14);
            return new LoanReceipt(bookId, observedNow, borrowedOn, dueOn);
        }
    }

    private static void expect(Object expected, Object actual, String label) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(label + ": expected " + expected
                    + ", got " + actual);
        }
        System.out.println(label + " = " + actual);
    }

    public static void main(String[] args) {
        Instant observed = Instant.parse("2025-12-31T18:00:00Z");
        Clock testClock = Clock.fixed(observed, ZoneOffset.UTC);
        ZoneId libraryZone = ZoneId.of("Asia/Ho_Chi_Minh");
        LoanService service = new LoanService(testClock, libraryZone);
        LoanReceipt receipt = service.borrow("BOOK-42");

        expect("BOOK-42", receipt.bookId(), "book");
        expect(observed, receipt.issuedAt(), "issuedAt");
        expect(LocalDate.of(2026, 1, 1), receipt.borrowedOn(), "borrowedOn");
        expect(LocalDate.of(2026, 1, 15), receipt.dueOn(), "dueOn");
        expect(receipt, service.borrow("BOOK-42"), "same inputs");

        LoanService utcLibrary = new LoanService(testClock, ZoneOffset.UTC);
        LoanReceipt utcReceipt = utcLibrary.borrow("BOOK-42");
        expect(LocalDate.of(2025, 12, 31), utcReceipt.borrowedOn(), "UTC date");
        expect(LocalDate.of(2026, 1, 14), utcReceipt.dueOn(), "UTC dueOn");

        Clock laterClock = Clock.fixed(
                Instant.parse("2026-01-01T18:00:00Z"), ZoneOffset.UTC);
        LoanReceipt later = new LoanService(laterClock, libraryZone)
                .borrow("BOOK-42");
        expect(LocalDate.of(2026, 1, 2), later.borrowedOn(), "later date");
        expect(LocalDate.of(2026, 1, 16), later.dueOn(), "later dueOn");
        System.out.println("all checks passed");
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 BusinessClockDemo.java
java BusinessClockDemo
```

Output:

```text
book = BOOK-42
issuedAt = 2025-12-31T18:00:00Z
borrowedOn = 2026-01-01
dueOn = 2026-01-15
same inputs = LoanReceipt[bookId=BOOK-42, issuedAt=2025-12-31T18:00:00Z, borrowedOn=2026-01-01, dueOn=2026-01-15]
UTC date = 2025-12-31
UTC dueOn = 2026-01-14
later date = 2026-01-02
later dueOn = 2026-01-16
all checks passed
```

`LoanReceipt` is a `record` used to carry the result. Comparing the two receipts on the `same inputs` line only verifies that the side-effect-free calculation in this lesson produces the same result given the same input data and the same instant. It does not mean that a real book-lending operation is allowed to execute twice or already has a deduplication mechanism.

## 6. Why read the clock only once in `borrow()`?

`observedNow` is used for both `issuedAt` and deriving `borrowedOn`. Both pieces of information therefore describe the same observation. If you called `clock.instant()` to get the instant and then called another time source to get the date, the two steps could land on opposite sides of midnight in production.

A fixed clock makes tests repeatable, while reading a single instant makes production operations consistent with the contract. These two benefits are related, but neither replaces the other.

You should not read "now" inside the constructor and keep it forever as the date for every loan. A service may stay alive across many days; the clock must be read at the time the business operation is processed if the rule is to use each operation's date.

Conversely, when a sequence of operations must share an instant pinned at the start of a request, an outer layer can read the clock once and pass that `Instant` down to calculation functions. The observation point must be placed at a meaningful boundary, not shifted arbitrarily just for coding convenience.

## 7. Wiring production and test time sources

When initializing production code, you can write within the same scope that has access to the example class:

```java
Clock productionClock = Clock.systemUTC();
ZoneId libraryZone = ZoneId.of("Asia/Ho_Chi_Minh");
LoanService production = new LoanService(productionClock, libraryZone);
```

`systemUTC()` provides the system time. Because the class already takes a separate business zone, the clock's zone is not used to derive the borrow date. If you choose a design that accepts only a clock and uses its zone, the initialization site can pass `Clock.system(libraryZone)` instead.

In tests, `Clock.fixed()` provides the exact instant to test. The program creates one clock for the year-end instant and another clock for the following day; there is no need to change the machine's clock, wait for a new day, or alter the algorithm inside `LoanService`.

If the application uses a dependency management framework, configuration outside the class can create the time source and pass it through the constructor just like any other dependency. The business class itself does not need to know who constructs it and does not need to load environment configuration to decide whether it is running in test or production.

## 8. Mistakes that make passing `Clock` ineffective

**Accepting a clock but not using it.** If one branch still calls `Instant.now()` with no arguments, that branch's instant is not controlled by the provided clock. You must trace every point where "now" is read that affects the result under test.

**Creating a system clock inside the method.** `Clock.systemUTC().instant()` inside `borrow()` is still hardcoded to the real source. Creating the clock at the assembly site is what makes the ability to swap sources explicit.

**Using a mutable global clock variable.** Concurrent tests or requests can interfere with one another when overwriting the time source. Supplying the dependency to the appropriate object keeps the configuration scope clear.

**Storing `now` as a constant at startup.** That captures a stale instant rather than providing a running time source. Keep the clock to read when needed; only store a fixed `Instant` when the business logic genuinely intends to pin that instant.

**Mixing calendar dates with durations.** The due date in this lesson is a calendar date plus 14 days. If a rule requires an exact number of seconds from issuance, it must be modeled with the corresponding instant/duration. Passing a `Clock` does not automatically choose the right business unit.

## 9. Test the class's behavior, not just the clock

The expectations in the program verify the receipt details: timestamp, borrow date, and due date. The year-end case clearly shows the zone effect; the different-clock case confirms that each operation uses the supplied source rather than a hardcoded instant captured when writing the program.

`Clock` only controls the code that reads it. If you later add a database that auto-generates `CURRENT_TIMESTAMP`, a scheduler, or another service that reads time on its own, you need to know whether that source falls within the current test's scope. Passing a parameter into `LoanService` does not automatically replace every time source in the application.

Exercise: change the loan period to 7 calendar days while keeping the instant and zone of the first receipt unchanged. The borrow date remains `2026-01-01`, and the due date must be `2026-01-08`. Then change only the clock to `2026-01-01T18:00:00Z`: the library's borrow date becomes `2026-01-02`. If you can explain why the class's time-reading code does not need to be modified when switching test scenarios, you have understood the responsibility boundary of the passed-in `Clock`.
