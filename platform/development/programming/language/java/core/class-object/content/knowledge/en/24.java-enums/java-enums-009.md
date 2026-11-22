# Avoid Using `ordinal()` as a Persistent Data Code in Java 17

## Learning Objectives

A Java `enum` helps represent a finite, named, type-safe set of constants. Each constant has a **declaration position** that Java provides via `ordinal()`. This value is very convenient for internal order-based mechanisms, but it is a **dangerous choice for storing in a database, sending over an API, writing logs with a long-term contract, encoding messages, or exchanging between multiple software versions**.

After this lesson, you will be able to:

- Explain accurately what `ordinal()` returns and why the value can change even though the constant name does not.
- Reproduce the data bug: code `1` meant `PAID` yesterday, yet a new version reads it as `PENDING_REVIEW`.
- Distinguish between **enum constant identity**, **declared name**, **declaration order**, and **persistent business code**.
- Design explicit `String`/`int` codes and a reliable decoder: unique, null-aware, fail-fast, and order-independent.
- Understand the trade-offs between `name()`, `toString()`, `ordinal()`, and explicit codes.
- Correctly assess the risks of `@Enumerated(EnumType.ORDINAL)` when using JPA, along with how to replace it with a managed converter/mapping.
- Plan a migration when a system **has already inadvertently stored ordinals**: freeze the old-version mapping, inspect data, convert, deploy safely, roll back, and monitor for errors.
- Test code stability across reordering/adding constants without accidentally writing a test that depends on `ordinal()`.

The demonstration programs use **Java 17**; each standalone `.java` file has deterministic `javac --release 17`, `java`, and stdout. Some sections are explicitly labeled as **illustrative snippets** or **before/after version code**: do not combine two versions with the same class name into the same compilation unit.

## 1. What Is `ordinal()` Actually?

Consider the enum:

```java
enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
```

Each enum constant has a position **starting from 0**, in the exact order it appears in the enum declaration:

| Constant | `name()` | `ordinal()` |
| --- | --- | ---: |
| `NEW` | `"NEW"` | 0 |
| `PAID` | `"PAID"` | 1 |
| `SHIPPED` | `"SHIPPED"` | 2 |
| `CANCELLED` | `"CANCELLED"` | 3 |

`ordinal()` is a final method provided by `java.lang.Enum`. We **cannot set the ordinal ourselves** in an enum constructor, nor can we override it.

Syntax:

```java
int position = OrderStatus.PAID.ordinal(); // 1
```

This is the **declaration position**, not a domain-validated ID, nor a chronological order, priority level, or database value. Two different enum constants have different ordinals within the same enum class in a given version; that **does not guarantee** that a constant's ordinal stays the same across source versions.

### Intended Use of Ordinal

According to the Java API, `ordinal()` is designed primarily for enum-based data structures such as `EnumSet` and `EnumMap`. Those structures understand the declaration order within the scope of the current enum. Application code usually **does not need to manipulate ordinals directly** for business logic programming.

**Core rule:** information computed from **source line order** should not by default become a **multi-year storage code**.

## 2. First Runnable Example

Save **`OrdinalBasicsDemo.java`**:

```java
enum DeliveryStatus {
    CREATED, PAID, SENT
}

public class OrdinalBasicsDemo {
    public static void main(String[] args) {
        for (DeliveryStatus status : DeliveryStatus.values()) {
            System.out.println(status.name() + ":" + status.ordinal());
        }

        System.out.println(
                DeliveryStatus.PAID == DeliveryStatus.valueOf("PAID"));
    }
}
```

Run:

```bash
javac --release 17 -encoding UTF-8 OrdinalBasicsDemo.java
java OrdinalBasicsDemo
```

**Exact stdout:**

```text
CREATED:0
PAID:1
SENT:2
true
```

The last line shows that `valueOf("PAID")` returns the exact **canonical enum constant**. This relates to constant identity; it does **not** make the constant's ordinal a stable code.

## 3. Why Is `ordinal()` Unstable?

Treat the following two declarations as **two versions of the same enum**, not existing at the same time:

**Version 1:**

```java
enum OrderStatus {
    NEW,
    PAID,
    SHIPPED
}
```

**Version 2:** add `PENDING_REVIEW` between NEW and PAID:

```java
enum OrderStatus {
    NEW,
    PENDING_REVIEW,
    PAID,
    SHIPPED
}
```

Comparison:

| Constant | Ordinal v1 | Ordinal v2 |
| --- | ---: | ---: |
| `NEW` | 0 | 0 |
| `PENDING_REVIEW` | Not present | 1 |
| `PAID` | 1 | 2 |
| `SHIPPED` | 2 | 3 |

If version 1 stores `PAID` as the number `1` in the `orders` table, version 2 reading `1` by looking up element 1 of `OrderStatus.values()` will return **PENDING_REVIEW**.

No exception necessarily occurs. The scariest part is that **data can be silently misread**.

### Risky Changes

- Inserting a constant at the beginning/middle of the enum.
- Reordering constants alphabetically for "prettier source".
- Regrouping constants according to new business rules.
- Deleting an unused constant, shifting the positions of subsequent ones.
- Moving an enum into a different declaration with a changed order.
- One service running a new version while another service still uses an old version.

**Appending a constant at the end** does not shift existing ordinals in that source version, yet it still does not turn ordinal into a stable code: order changes can still happen later, and protocols generally do not guarantee that all consumers upgrade simultaneously.

## 4. Experimenting with Two Versions and Stdout

Save **`OrdinalVersion1Demo.java`**:

```java
enum OldStatus {
    NEW,
    PAID,
    SHIPPED
}

public class OrdinalVersion1Demo {
    public static void main(String[] args) {
        System.out.println(OldStatus.PAID.ordinal());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OrdinalVersion1Demo.java
java OrdinalVersion1Demo
```

Stdout:

```text
1
```

Save **`OrdinalVersion2Demo.java`** under a separate type name so the two examples can coexist independently:

```java
enum NewStatus {
    NEW,
    PENDING_REVIEW,
    PAID,
    SHIPPED
}

public class OrdinalVersion2Demo {
    public static void main(String[] args) {
        System.out.println(NewStatus.PAID.ordinal());
        System.out.println(NewStatus.values()[1]);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OrdinalVersion2Demo.java
java OrdinalVersion2Demo
```

Stdout:

```text
2
PENDING_REVIEW
```

In production, the type named `OrderStatus` usually **stays unchanged**, while the source code version changes. Using `OldStatus`/`NewStatus` in the two files is only to demonstrate the results simultaneously without a name collision.

## 5. What Counts as "Persistent Data"?

A code is considered a **persisted/external contract** if it must retain its meaning after the current process ends or across multiple deployments.

Examples:
- A `status` column in MySQL/PostgreSQL or a data file.
- A key/value in Redis if the data survives across deployments.
- A Kafka/Pulsar event payload that has been sent and may be replayed.
- A JSON response/request of a public API.
- Messages sent between microservices of different versions.
- Records in an audit log used for later investigation.
- CSV exports/imports for partners.
- Configuration codes that persist across restarts.
- Long-lived cache data that needs to be read by a new version.

In those environments, data needs **stable contract-based meaning**, not meaning tied to the incidental position of a constant in a source file.

Conversely, short-term indexing within an internal algorithm can depend on declaration order if you fully control the lifecycle and **do not expose the ordinal across a persistence/protocol boundary**.

## 6. Failure Mode When Storing Ordinals in a Database

Imagine the table:

```text
orders
+----+--------+
| id | status |
+----+--------+
| 10 |   1    |
| 11 |   2    |
+----+--------+
```

With enum v1 `NEW, PAID, SHIPPED`, the application interprets:

```text
id=10 → PAID
id=11 → SHIPPED
```

After a developer inserts `PENDING_REVIEW` in the middle, those same two numbers are read as:

```text
id=10 → PENDING_REVIEW   (wrong meaning)
id=11 → PAID             (wrong meaning)
```

The error can continue to propagate:
1. The UI displays the wrong status.
2. Authorization/transition logic takes the wrong branch.
3. A batch job reprocesses data under the new label.
4. The system overwrites the wrong result back into the database.
5. Audit logs record events that are hard to recover from.

**The danger:** if all ordinals still fall within the 0..N-1 range of the new enum, the lookup code may not throw any exception.

### Not Just a Display Bug

With a `PAID` status read as `PENDING_REVIEW`, the payment system may refuse delivery, charge again, or trigger an incorrect workflow. This is a **data integrity** error.

## 7. Common Anti-Pattern

```java
// Wrong when persisted status is a stable business ID:
int valueForDatabase = status.ordinal();
```

And when reading:

```java
// Dangerous: only makes sense if the data schema and enum order
// truly belong to the same version, and still should not be used long-term.
OrderStatus loaded = OrderStatus.values()[savedNumber];
```

Drawbacks of `values()[savedNumber]`:
- If the number is negative or out of range: `ArrayIndexOutOfBoundsException`.
- If the number is valid but the enum version was reordered: **decoded to the wrong constant**.
- There is no schema version information.
- There is no way to detect that `1` originally represented a different old constant.
- Constant names, field contents, or a new contract do not help recover the correct meaning.

**Do not "fix" this by catching the exception and picking a default constant**. Silent misinterpretation cases still produce no exception, and defaulting can erase traces of data errors.

## 8. Runnable: Reproducing Silent Misinterpretation

Save **`OrdinalDataCorruptionDemo.java`**:

```java
enum OriginalStatus {
    NEW, PAID, SHIPPED
}

enum ModifiedStatus {
    NEW, PENDING_REVIEW, PAID, SHIPPED
}

public class OrdinalDataCorruptionDemo {
    public static void main(String[] args) {
        int stored = OriginalStatus.PAID.ordinal();

        OriginalStatus original = OriginalStatus.values()[stored];
        ModifiedStatus modified = ModifiedStatus.values()[stored];

        System.out.println("stored=" + stored);
        System.out.println("original=" + original);
        System.out.println("modified=" + modified);
        System.out.println(original.name().equals(modified.name()));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OrdinalDataCorruptionDemo.java
java OrdinalDataCorruptionDemo
```

Stdout:

```text
stored=1
original=PAID
modified=PENDING_REVIEW
false
```

The integer code `1` does not carry enough information to say "this is PAID". **It only has meaning when paired with a specific declaration version**.

## 9. Similar Errors in APIs and Events

Example of an event:

```text
{ "orderId": 10, "status": 1 }
```

The old producer uses `OrderStatus.PAID.ordinal()==1`. The new consumer interprets `1` as PENDING_REVIEW. Even if both producer and consumer use Java, there is no guarantee that enum order automatically stays synchronized between two binary versions.

If the consumer is written in Python, Go, JavaScript, or is an external partner outside the company, they do not even see the Java source declaration. The numeric code `1` needs to be defined **in the protocol specification**, not implicitly depend on `ordinal()`.

### Rolling Deployments Complicate the Problem

During a blue/green or rolling update, multiple versions can run at the same time:
- Service A v1 writes the number 1 meaning PAID.
- Service B v2 reads the number 1 meaning PENDING_REVIEW.
- Service B v2 writes the number 2 meaning PAID.
- Service A v1 reads the number 2 meaning SHIPPED.

A single reorder can create **bidirectional incompatibility**. Therefore, a migration must account for the possibility of multiple versions coexisting simultaneously, not just a single restart.

## 10. Four Easily Confused Concepts

| Concept | Example | Stable when reordering constants? |
| --- | --- | --- |
| Constant object identity | `OrderStatus.PAID` | Same constant referenced in the corresponding runtime |
| `name()` | `"PAID"` | **Yes** if the name is kept unchanged; renaming changes it |
| `ordinal()` | `1` | **No** if constants are added/reordered before PAID |
| Explicit code | `"P"` or `200` | **Can be**, when managed stably as a contract |

**An explicit code is not automatically immutable.** It is only durable if the team enforces rules: never reuse codes, never modify them silently, perform deliberate migrations, and test the contract.

### `toString()` Is Not a Default Key

An enum's `toString()` can be overridden for UI or logging. If used as a persisted key, changing the wording/locale later can break data.

Use explicitly:
- `name()` when the contract commits to the source constant name.
- `code()` when the contract has its own dedicated code.
- `label(locale)` for multilingual display.
- `ordinal()` only for legitimate internal ordering.

## 11. Preferred Solution: Explicit `String` Codes

```java
enum OrderStatus {
    NEW("N"),
    PENDING_REVIEW("R"),
    PAID("P"),
    SHIPPED("S");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }
}
```

Each constant has a fixed code:
- NEW → N.
- PENDING_REVIEW → R.
- PAID → P.
- SHIPPED → S.

Now changing the order of constants **does not change the `code` field**, provided you keep the same argument associated with each constant.

This is an important separation between **declaration order** and **external representation**.

### Why Is String Often Convenient?

- Easy to read visually in databases, logs, and JSON.
- Can be short and stable, for example `"P"`.
- Not mistaken for an offset/array.
- Can extend namespaces with prefixes when needed.

However, String is not mandatory. An explicit `int` is also fine if the protocol has meaningful numeric codes, not ordinals.

## 12. Runnable: Stable String Code

Save **`ExplicitStringCodeDemo.java`**:

```java
enum OrderStatus {
    NEW("N"),
    PENDING_REVIEW("R"),
    PAID("P"),
    SHIPPED("S");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }
}

public class ExplicitStringCodeDemo {
    public static void main(String[] args) {
        OrderStatus status = OrderStatus.PAID;

        System.out.println(status.code());
        System.out.println(status.ordinal());
        System.out.println(status.name());
        System.out.println(status == OrderStatus.PAID);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ExplicitStringCodeDemo.java
java ExplicitStringCodeDemo
```

Stdout:

```text
P
2
PAID
true
```

`P` is the external contract code we designed ourselves. `2` is only the ordinal in the current source version. If `PAID` is reordered to the top, `ordinal()` changes to 0, while `code()` remains P.

## 13. Explicit `int` Codes Are Also a Solution

Using integers is not wrong. What is wrong is **using integers derived from `ordinal()` without a stable contract**.

Example:

```java
enum PaymentStatus {
    PENDING(100),
    PAID(200),
    FAILED(900);

    private final int code;

    PaymentStatus(int code) {
        this.code = code;
    }

    public int code() {
        return code;
    }
}
```

These are **100/200/900** codes that are explicitly chosen and documented. We can add the `REFUNDED(300)` status at any position without changing the old codes.

### Rules for Numeric Codes

- Have a clear namespace and definition.
- Unique within the set of constants.
- Do not reuse an old code for a new meaning after it is retired.
- Do not derive codes using `ordinal()+1`.
- Have a strategy for unknown codes.
- Do not depend on enum sorting/reordering.
- Have tests ensuring backward compatibility.

## 14. Runnable: Stable Numeric Codes

Save **`ExplicitNumericCodeDemo.java`**:

```java
enum PaymentStatus {
    PENDING(100),
    PAID(200),
    FAILED(900);

    private final int code;

    PaymentStatus(int code) {
        this.code = code;
    }

    int code() {
        return code;
    }
}

public class ExplicitNumericCodeDemo {
    public static void main(String[] args) {
        for (PaymentStatus status : PaymentStatus.values()) {
            System.out.println(status.name()
                    + ":code=" + status.code()
                    + ",ordinal=" + status.ordinal());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ExplicitNumericCodeDemo.java
java ExplicitNumericCodeDemo
```

Stdout:

```text
PENDING:code=100,ordinal=0
PAID:code=200,ordinal=1
FAILED:code=900,ordinal=2
```

The key point is that **`code` is not generated from `ordinal`**. Even if the numbers currently happen to correlate with the declaration order, the contract lies strictly in the explicit codes.

## 15. Designing a Decoder: Do Not Read `values()[number]`

When the database/API returns `"P"`, it needs to map back to `OrderStatus.PAID`.

A simple approach for a small enum:

```java
static OrderStatus fromCode(String code) {
    for (OrderStatus status : values()) {
        if (status.code.equals(code)) {
            return status;
        }
    }
    throw new IllegalArgumentException("Unknown code: " + code);
}
```

Benefits:
- Looks up by explicit code, not ordinal.
- Reordering the enum has no impact.
- Unknown codes are detected instead of being silently wrong.
- O(n) cost, usually sufficient for small enums and low frequency.

### Do Not Use `toString()` or `name()` as an Implicit Decoder

`Enum.valueOf(Type.class, input)` looks up by **constant name**, not by `code`. If `PAID` has the code `"P"`, then `valueOf("P")` does **not** select PAID.

Name the `fromCode` method clearly, without assuming Java automatically understands custom fields.

## 16. Runnable: Linear Decoder and Unknown Codes

Save **`EnumDecoderDemo.java`**:

```java
enum OrderState {
    NEW("N"),
    PAID("P"),
    SHIPPED("S");

    private final String code;

    OrderState(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }

    static OrderState fromCode(String code) {
        for (OrderState candidate : values()) {
            if (candidate.code.equals(code)) {
                return candidate;
            }
        }
        throw new IllegalArgumentException("unknown code");
    }
}

public class EnumDecoderDemo {
    public static void main(String[] args) {
        OrderState state = OrderState.fromCode("P");

        System.out.println(state);
        System.out.println(state == OrderState.PAID);
        System.out.println(state.code());

        try {
            OrderState.fromCode("X");
        } catch (IllegalArgumentException error) {
            System.out.println("UNKNOWN");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumDecoderDemo.java
java EnumDecoderDemo
```

Stdout:

```text
PAID
true
P
UNKNOWN
```

`fromCode` returns the **canonical enum object**, not a copy. Mapping from `"P"` to PAID stays correct even if a developer changes the declaration order.

## 17. When to Use a Lookup Map?

For large enums or very frequent decoding, a `Map<String,EnumType>` can be created once:

```java
private static final Map<String, OrderStatus> BY_CODE = ...;
```

Map lookup is typically O(1) on average, but the main benefit here is not just performance:
- Checks for duplicate codes as soon as the class initializes.
- Centralizes mapping logic.
- Makes it easy to define an unknown-code policy.
- Can expose the `fromCode` method without exposing a mutable map.

**Do not build the map inside the enum constructor by touching a static map of the enum itself while it is being initialized.** Enum constants are constructed before regular static fields, and Java has restrictions against referencing uninitialized static fields inside an enum constructor. Place the map-building logic after all constants are ready, for example in an appropriate static initializer or static field initialization.

### The Map Should Be Immutable After Creation

If the mapping is part of the enum's contract:
- Build a local mutable map to check uniqueness.
- Publish an immutable `Map.copyOf` or `Collections.unmodifiableMap`.
- Do not expose a map where a caller could `put` and break invariants.
- Avoid nulls in codes and duplicate codes.

## 18. Runnable: Immutable Map Decoder with Duplicate Code Detection

Save **`EnumCodeMapDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

enum ReviewStatus {
    NEW("N"),
    APPROVED("A"),
    REJECTED("R");

    private final String code;

    ReviewStatus(String code) {
        this.code = Objects.requireNonNull(code);
    }

    String code() {
        return code;
    }

    private static final Map<String, ReviewStatus> BY_CODE;

    static {
        Map<String, ReviewStatus> map = new HashMap<>();

        for (ReviewStatus status : values()) {
            ReviewStatus previous = map.putIfAbsent(
                    status.code, status);
            if (previous != null) {
                throw new IllegalStateException(
                        "duplicate enum code");
            }
        }

        BY_CODE = Map.copyOf(map);
    }

    static ReviewStatus fromCode(String code) {
        ReviewStatus result = BY_CODE.get(code);
        if (result == null) {
            throw new IllegalArgumentException(
                    "unknown enum code");
        }
        return result;
    }
}

public class EnumCodeMapDemo {
    public static void main(String[] args) {
        ReviewStatus status = ReviewStatus.fromCode("A");

        System.out.println(status);
        System.out.println(status.code());
        System.out.println(status == ReviewStatus.APPROVED);

        try {
            ReviewStatus.fromCode("Z");
        } catch (IllegalArgumentException error) {
            System.out.println("unknown");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumCodeMapDemo.java
java EnumCodeMapDemo
```

Stdout:

```text
APPROVED
A
true
unknown
```

**Important:** `BY_CODE` is built in a `static` block **after the constant list**. It uses `values()` once the constants have already been initialized. `putIfAbsent` catches duplicate errors right when the enum type initializes, avoiding silent "last value overwrites previous value" behavior.

**Null policy:** `Map.copyOf` does not allow null keys or values; the constructor prevents null codes. `BY_CODE.get(null)` on this immutable map can throw a `NullPointerException`, so a production decoder should explicitly check for null before lookup if a consistent error type is desired.

## 19. Explicit Decoder Handling for Null and Invalid Input

External input can contain:
- `null`;
- Empty strings;
- Strings with extra spaces;
- Different casing;
- Codes that are no longer supported;
- Future codes that the current version does not yet know.

There is no single policy for every domain:
- **Fail fast** with `IllegalArgumentException` when the status affects money or authorization.
- Return `Optional<Status>` if an unknown value is an expected scenario.
- Return a result object representing `Unknown(rawCode)` if unknown data needs to be preserved for forwarding.
- Normalize input only when the protocol defines normalization (do not arbitrarily `trim()`/uppercase and conflate distinct codes).

### The Trap of Defaulting to NEW

`return Status.NEW;` for every unknown code can be a serious bug: a PAID status from a future version gets read as NEW, leading to reprocessing or canceling the flow. Defaulting is only valid when the system's semantics truly define it and it is tested.

## 20. Runnable: Safe Parsing with Optional

Save **`EnumOptionalDecoderDemo.java`**:

```java
import java.util.Optional;

enum Channel {
    EMAIL("e"),
    SMS("s");

    private final String code;

    Channel(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }

    static Optional<Channel> tryFromCode(String input) {
        if (input == null) {
            return Optional.empty();
        }

        for (Channel channel : values()) {
            if (channel.code.equals(input)) {
                return Optional.of(channel);
            }
        }
        return Optional.empty();
    }
}

public class EnumOptionalDecoderDemo {
    public static void main(String[] args) {
        System.out.println(Channel.tryFromCode("e").orElseThrow());
        System.out.println(Channel.tryFromCode("S").isPresent());
        System.out.println(Channel.tryFromCode(null).isEmpty());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumOptionalDecoderDemo.java
java EnumOptionalDecoderDemo
```

Stdout:

```text
EMAIL
false
true
```

Here the code is case-sensitive: `"s"` is valid, and `"S"` is unknown. That is an intentional protocol choice.

## 21. When Is `name()` Better Than `ordinal()`?

Example:

```java
enum OrderStatus {
    NEW, PAID, SHIPPED
}
```

Storing `OrderStatus.PAID.name()` writes `"PAID"`. When adding `PENDING_REVIEW` before PAID:
- `name()` remains `"PAID"` if the constant is not renamed.
- `OrderStatus.valueOf("PAID")` still correctly returns PAID.
- The ordinal of PAID changes.

Thus, **storing the constant name is generally safer than storing the ordinal** across order changes.

However, there are caveats:
- Renaming PAID → SETTLED causes old `"PAID"` data to no longer be recognized by `valueOf`.
- Deleting a constant makes historical rows require migration.
- The source name becomes a public data contract, restricting the ability to refactor names.

If the code is internal and renames are rare, name-based mapping may suffice. If the API/database has an independent lifecycle, an explicit stable code gives you a stronger layer of abstraction.

## 22. `name()` and `toString()` Are Different

`Enum.name()` is final and returns the exact declaration name. `toString()` also returns the name by default, but can be overridden:

```java
enum Status {
    PAID;

    @Override
    public String toString() {
        return "Đã thanh toán";
    }
}
```

`Status.PAID.name()` is `"PAID"`; `Status.PAID.toString()` is `"Đã thanh toán"`.

**Do not use UI text as a persistent ID**. Locale, wording, A/B experiments, and translation changes can make the text differ while the domain meaning remains unchanged.

You should separate:
- `code`: stable persistence/wire code.
- `name`: Java declaration identifier.
- `label`: UI translation.

## 23. Runnable: Label Changes Do Not Affect the Code

Save **`EnumLabelVsCodeDemo.java`**:

```java
enum TicketStatus {
    OPEN("O", "Đang mở"),
    CLOSED("C", "Đã đóng");

    private final String code;
    private final String label;

    TicketStatus(String code, String label) {
        this.code = code;
        this.label = label;
    }

    String code() {
        return code;
    }

    String label() {
        return label;
    }
}

public class EnumLabelVsCodeDemo {
    public static void main(String[] args) {
        TicketStatus status = TicketStatus.CLOSED;

        System.out.println(status.name());
        System.out.println(status.code());
        System.out.println(status.label());
        System.out.println(status.ordinal());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumLabelVsCodeDemo.java
java EnumLabelVsCodeDemo
```

Stdout:

```text
CLOSED
C
Đã đóng
1
```

You can edit the label to another translation without changing `"C"`, as long as the code mapping is committed to remaining stable.

## 24. JPA `EnumType.ORDINAL`: Understanding the Risks Accurately

If the project uses Jakarta Persistence/JPA, an enum entity field can be mapped as ordinal or string depending on the annotation/provider/version.

Example **snippet depending on a JPA library**, not plain Java SE 17:

```java
@Enumerated(EnumType.ORDINAL)
private OrderStatus status;
```

The usual meaning of `EnumType.ORDINAL` is to map the enum by ordinal number. If the source enum is reordered, data in the column can be decoded incorrectly.

**Warning:** depending on the JPA namespace/version, it may be `javax.persistence` or `jakarta.persistence`; the snippet above will not compile with only the JDK without the JPA dependency and entity context.

### Is `EnumType.STRING` Completely Safe?

Snippet:

```java
@Enumerated(EnumType.STRING)
private OrderStatus status;
```

It typically maps by enum name, avoiding the reordering problem, yet still depends on the **constant name**. Renaming/deleting a constant requires migration.

Default settings and schema/provider details can vary by JPA specification and version; do not rely on unverified defaults. Verify the mapping used in the actual project.

### When a Stable Business Code Is Needed

Use an application-controlled converter/mapper: `OrderStatus.code()` when writing and `OrderStatus.fromCode(...)` when reading. The implementation mechanism can be a JPA `AttributeConverter` or a mapper at the persistence layer, depending on the design/provider.

**Do not simultaneously use `@Enumerated` and a custom converter on the same field** without understanding the precedence rules and limitations of the provider and specification. Choose one clear mapping strategy and perform integration testing.

## 25. Which Code Should the Database Schema Store?

There are two common options:

**String code:**

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status_code VARCHAR(16) NOT NULL
);
```

**Numeric explicit code:**

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status_code INTEGER NOT NULL
);
```

Both snippets are **illustrative DDL**, without vendor-specific constraints/migrations. The application writes `"P"` or `200` according to the explicit enum code, not `ordinal()`.

Schema questions:
- Nullable or not null?
- Is there a CHECK/foreign key/reference table constraint?
- Do old codes still need to be recognized in historical data?
- Is the column length sufficient for future codes?
- Are there index/unique constraints that need adjustment?
- Are old application versions reading the column at the same time?
- Is there a need to store a schema version to replay multi-year data?

Do not treat changing a column type from SMALLINT to VARCHAR as a Java-source-only change. It is a **data migration** and requires planning.

## 26. Migration: What to Do If the System Already Stored Ordinals?

If `orders.status` currently contains `0,1,2`, immediately changing the code to explicit `fromCode` without migrating data will cause errors or misreads.

Deliberate process:

1. **Freeze the mapping that was used to write the data**: find the exact source/binary version of the enum when the data was created.
2. **List the historical versions**, deployment timelines, and the possibility of multiple different mappings.
3. **Measure the value distribution**: which ordinals exist in the database, null ratio, and out-of-range numbers.
4. **Determine the unambiguity** of each value in each period; if a single number ever had two meanings and there is no version/timestamp, recovery may be uncertain.
5. **Choose stable codes** and document the official mapping.
6. **Create a new column or a controlled transition phase** to avoid mixing old and new values.
7. **Backfill using the fixed mapping of the old version**, not using the current enum's `values()[n]`.
8. **Reconcile counts, checksums, and business samples** before switching the reader.
9. **Ensure compatibility during rolling deploy**: dual-read/dual-write if needed and carefully designed.
10. **Switch readers/writers to the stable code**, then remove ordinal support according to plan.
11. **Monitor unknown/missing codes**, rollback, audit trails, and newly generated data.
12. **Remove the ordinal write path and add guards/tests** so the bug does not return.

The most important step is **step 1**. If you use the new enum source to decode old numbers, the migration itself can produce permanently wrong data.

## 27. Build Legacy Mapping by Historical Declaration, Not by Current Enum

Suppose the history has:

```text
V1 historical ordinal:
0 = NEW
1 = PAID
2 = SHIPPED
```

The new version adds PENDING_REVIEW. During migration, define the old mapping explicitly:

```java
static OrderStatus fromLegacyV1Ordinal(int saved) {
    return switch (saved) {
        case 0 -> OrderStatus.NEW;
        case 1 -> OrderStatus.PAID;
        case 2 -> OrderStatus.SHIPPED;
        default -> throw new IllegalArgumentException(
                "Unknown legacy ordinal: " + saved);
    };
}
```

**Do not** write `OrderStatus.values()[saved]` here, because the current enum declaration has changed.

### What If There Are Multiple Historical Source Versions?

Define migration logic according to the corresponding data version/source-era:

```java
switch (record.schemaVersion()) {
    case 1 -> decodeV1(record.ordinal());
    case 2 -> decodeV2(record.ordinal());
    default -> throw new IllegalArgumentException();
}
```

This is a design snippet: `record` needs a model with schemaVersion/ordinal. Do not invent a version if the database currently lacks the corresponding field. If data is already mixed and it is impossible to tell which version wrote a record, forensic evidence, manual reconciliation, and uncertainty handling may be needed; never claim a perfect mapping.

## 28. Runnable: Migrating from Old Ordinals to New Codes

Save **`LegacyOrdinalMigrationDemo.java`**:

```java
enum CurrentState {
    NEW("N"),
    PENDING_REVIEW("R"),
    PAID("P"),
    SHIPPED("S");

    private final String code;

    CurrentState(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }

    static CurrentState fromLegacyV1(int oldOrdinal) {
        return switch (oldOrdinal) {
            case 0 -> NEW;
            case 1 -> PAID;
            case 2 -> SHIPPED;
            default -> throw new IllegalArgumentException(
                    "unknown old ordinal");
        };
    }
}

public class LegacyOrdinalMigrationDemo {
    public static void main(String[] args) {
        int[] oldDatabaseValues = {0, 1, 2};

        for (int old : oldDatabaseValues) {
            CurrentState state = CurrentState.fromLegacyV1(old);
            System.out.println(old + " -> " + state.code());
        }

        System.out.println(CurrentState.PAID.ordinal());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LegacyOrdinalMigrationDemo.java
java LegacyOrdinalMigrationDemo
```

Stdout:

```text
0 -> N
1 -> P
2 -> S
2
```

The last line proves PAID now has ordinal **2**, yet legacy ordinal **1** is still migrated to PAID via the **historical mapping** rather than the current position.

## 29. SQL Migration Must Rely on Old Schema Documentation

Example of a **conditional backfill idea**:

```sql
UPDATE orders
SET status_code = CASE legacy_status
    WHEN 0 THEN 'N'
    WHEN 1 THEN 'P'
    WHEN 2 THEN 'S'
    ELSE NULL
END;
```

This is only **illustrative SQL**, not a production script to run verbatim:
- Actual column names may differ.
- `ELSE NULL` only serves to illustrate an unknown value; in a real migration, you should raise an error/audit rather than silently turning unknown values into null.
- Transaction batching, locks, online schema changes, and replication planning may be needed.
- With mixed versions, a single mapping for all rows can be wrong.
- After backfilling, counts and samples must be reconciled against business rules.

### Before Running the Migration

You should have:
- A restorable backup/snapshot.
- A dry run on representative data.
- A report of row counts per legacy ordinal.
- Queries to detect invalid/unknown ordinals.
- A rollback plan and write compatibility.
- A verified maintenance window or phased rollout.
- Owners responsible for signing off on integrity checks.

"Changing the annotation from ORDINAL to STRING" does **not** automatically convert existing numbers to the correct enum names.

## 30. Historical Data May Not Be Completely Recoverable

Suppose:
- v1: `0 NEW, 1 PAID, 2 SHIPPED`;
- v2: `0 NEW, 1 PENDING_REVIEW, 2 PAID, 3 SHIPPED`;
- the database already contains many records written by both;
- records have no schema version, reliable deployment timestamp, or audit state.

The value `1` could mean:
- PAID if written by v1;
- PENDING_REVIEW if written by v2.

No Java computation can reliably recover the meaning from **a single standalone number 1**. The problem already lost information at the time the data was written.

You must:
- Collect logs, events, timestamps, and version metadata if available.
- Check the business rules constraining each record.
- Identify the group that cannot be inferred and handle it separately.
- Report the uncertainty clearly; do not pretend all rows were fixed accurately.

This is why preventing ordinal persistence **is much cheaper** than fixing the aftermath.

## 31. Migration in a Rolling Deployment

If the entire system cannot be stopped at once:

**Schema expansion phase:** add `status_code` while keeping the legacy ordinal column. Deploy new readers that can read the stable code when present and fall back to the historical mapping when absent.

**Dual-write phase:** new writers write both columns **only when dual-write is designed safely**, as legacy code cannot represent every new status; avoid writing an ordinal for a new constant that old consumers will misinterpret.

**Backfill and verification:** convert old rows according to the right version mapping; detect unsupported/ambiguous rows.

**Cutover phase:** switch all readers and writers to the new code. Monitor the fallback rate, unknown codes, and consistency.

**Contraction phase:** stop legacy writes, remove the fallback once data has been verified, and then drop the ordinal column in an appropriate release.

### Key Checkpoint

If v2 code has a new constant that does not exist in v1, legacy consumers may not understand that status even with dual-write. You may need version gating, feature flags, or delaying the release of new values until all consumers have upgraded.

Dual-write is not a magic solution for incompatibility.

## 32. Rule Set for Managing Explicit Codes

To keep codes truly persistent:

1. Each code has a unique meaning within its defined namespace.
2. The code of an existing status **does not change due to reordering**.
3. Do not reuse the code of a retired status for a different meaning.
4. Adding a new constant must assign a new code, not derive it from ordinal.
5. Renaming a Java identifier does not change the code if the business semantics stay the same.
6. Keep aliases for old data only when the semantics remain equivalent and documented.
7. Have a policy for unknown codes from future versions.
8. Have tests protecting the code mapping and uniqueness.
9. Public API contracts/documentation clearly state the code values.
10. Migration is performed using verified historical mappings, not current indexes.

If numeric codes also carry business meaning (for example HTTP 200, 404), set the code according to the corresponding specification, not according to the enum position.

## 33. Test the Contract Rather Than Implementation Details

A weak unit test:

```java
assertEquals(1, Status.PAID.ordinal());
```

It only locks down declaration order. If reordering is a valid internal change, the test will hinder refactoring while **not protecting the external contract**.

A better test:

```java
assertEquals("P", Status.PAID.code());
assertSame(Status.PAID, Status.fromCode("P"));
```

If you want to ensure no duplicates:
- Collect codes from `values()` into a `Set`.
- Assert that the Set size equals `values().length`.
- For public persistence codes, assert all known contract pairs using concrete values.

### Principle

**Test what clients/the database see; do not lock source positions if position is not part of the contract.**

## 34. Runnable: Testing an Ordinal-Independent Contract

Save **`StableCodeContractTestDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

enum ShipmentStatus {
    CREATED("C"),
    IN_TRANSIT("T"),
    DELIVERED("D");

    private final String code;

    ShipmentStatus(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }

    static ShipmentStatus fromCode(String code) {
        for (ShipmentStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException("unknown code");
    }
}

public class StableCodeContractTestDemo {
    public static void main(String[] args) {
        require(ShipmentStatus.CREATED.code().equals("C"));
        require(ShipmentStatus.IN_TRANSIT.code().equals("T"));
        require(ShipmentStatus.DELIVERED.code().equals("D"));

        Set<String> codes = new HashSet<>();

        for (ShipmentStatus status : ShipmentStatus.values()) {
            require(codes.add(status.code()));
            require(ShipmentStatus.fromCode(status.code()) == status);
        }

        System.out.println("CONTRACT_OK");
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("contract failed");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 StableCodeContractTestDemo.java
java StableCodeContractTestDemo
```

Stdout:

```text
CONTRACT_OK
```

You can reorder `ShipmentStatus` and still pass the test as long as the code fields remain unchanged. This tests **independence from declaration order**.

## 35. Tests Against Regressions from `ordinal()`

In addition to unit tests, you can perform:
- Code search to find `.ordinal()` in persistence DTO mappers/API serializers.
- Organization-specific static analysis rules for `ordinal()` flowing across boundary methods.
- Integration tests verifying that raw database values match the published codes.
- Contract tests between producers/consumers of different versions.
- Schema tests with legacy data and unknown values.
- Golden JSON/CSV snapshots based on stable codes, not ordinals.
- Migration tests from historical mappings using exact fixtures.

**There is no need to strictly ban every single use of `ordinal()`**. There are legitimate internal algorithm usages; what needs control is the point where **it becomes an external persistent representation**.

## 36. When Is `ordinal()` Still Appropriate?

Some internal scenarios:

- Relying on enum order to represent an internal array within **the same version and the same lifecycle**, if the design genuinely requires that order.
- Processing the natural order of an enum when the declaration order is understood as the natural order.
- Inspection/debugging: printing name/ordinal to understand the enum declaration.
- Specialized JDK structures such as `EnumSet`/`EnumMap` that already manage internal details.

Internal index example:

```java
int index = current.ordinal();
```

If the index is used to access an array **built from the exact same current enum declaration**, the code can be valid within a single runtime. Still, review:
- Does the array have matching length/ordering?
- Is there a risk this code gets reused for persisted data?
- Would it be easy to replace with `EnumMap` to reduce coupling?
- Are there thread safety/visibility issues?

In other words, **ordinal is not "forbidden in Java"**; it is simply **not a persistent data code**.

## 37. Why Is `EnumMap` Better Than an Array Manually Indexed by Ordinal?

Suppose:

```java
String[] labels = {"new", "paid", "shipped"};
String label = labels[status.ordinal()];
```

If a constant is added between NEW and PAID and someone forgets to adjust the array, `labels[status.ordinal()]` can return the wrong label.

Use `EnumMap<OrderStatus,String>`:

```java
EnumMap<OrderStatus, String> labels =
        new EnumMap<>(OrderStatus.class);
labels.put(OrderStatus.NEW, "new");
labels.put(OrderStatus.PAID, "paid");
labels.put(OrderStatus.SHIPPED, "shipped");
```

The map binds values to **enum constants as keys**, not to raw array offsets managed by the application. If a new constant is added, you still need to decide on a label for it; code reading the map can detect a missing key and handle it explicitly.

This is a **snippet** example; to run it, add `import java.util.EnumMap;` and define the enum.

## 38. Runnable: Using EnumMap Instead of an Ordinal Array

Save **`EnumMapInsteadOfOrdinalDemo.java`**:

```java
import java.util.EnumMap;

enum OrderStage {
    NEW, PENDING_REVIEW, PAID, SHIPPED
}

public class EnumMapInsteadOfOrdinalDemo {
    public static void main(String[] args) {
        EnumMap<OrderStage, String> labels =
                new EnumMap<>(OrderStage.class);

        labels.put(OrderStage.NEW, "new");
        labels.put(OrderStage.PENDING_REVIEW, "review");
        labels.put(OrderStage.PAID, "paid");
        labels.put(OrderStage.SHIPPED, "shipped");

        System.out.println(labels.get(OrderStage.PAID));
        System.out.println(labels.get(OrderStage.PENDING_REVIEW));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumMapInsteadOfOrdinalDemo.java
java EnumMapInsteadOfOrdinalDemo
```

Stdout:

```text
paid
review
```

`EnumMap` is specialized for enum keys and handles internal representation automatically. Application code does not tie labels to raw ordinal numbers.

## 39. Enum Natural Order Still Relies on Declaration Order

`Enum.compareTo` orders constants by ordinal order. `EnumSet` and `EnumMap` also iterate keys in natural declaration order.

If UI/priority ordering is a **business contract**, add an explicit `rank`:

```java
enum Priority {
    LOW(10),
    MEDIUM(20),
    HIGH(30);

    private final int rank;

    Priority(int rank) {
        this.rank = rank;
    }

    int rank() {
        return rank;
    }
}
```

Sort with `Comparator.comparingInt(Priority::rank)` when you want ordering based on the rank field. Gaps (10,20,30) can be kept to insert new levels without changing the codes of existing levels, but do not confuse rank with ID if the two roles require separate contracts.

### Order Does Not Equal Identity

`Priority.HIGH` is a canonical enum constant. The `rank=30` field describes relative ordering. `ordinal()` describes source position. Three different meanings.

## 40. Runnable: Explicit Order Independent of Declaration

Save **`EnumExplicitRankDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

enum Priority {
    HIGH(30),
    LOW(10),
    MEDIUM(20);

    private final int rank;

    Priority(int rank) {
        this.rank = rank;
    }

    int rank() {
        return rank;
    }
}

public class EnumExplicitRankDemo {
    public static void main(String[] args) {
        List<Priority> priorities =
                new ArrayList<>(List.of(Priority.values()));

        priorities.sort(Comparator.comparingInt(
                Priority::rank));

        for (Priority p : priorities) {
            System.out.println(p.name() + ":" + p.rank());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumExplicitRankDemo.java
java EnumExplicitRankDemo
```

Stdout:

```text
LOW:10
MEDIUM:20
HIGH:30
```

The declaration order is HIGH, LOW, MEDIUM; the order by rank is LOW, MEDIUM, HIGH. If ordinal were used to represent rank, the two meanings would be conflated.

## 41. Data from Future Versions: Forward Compatibility

Suppose a v2 service adds `REFUNDED("F")`. A v1 service reads the code `"F"`, but v1's enum does not yet have the REFUNDED constant.

This is a different issue from ordinals:
- With stable codes, v1 clearly recognizes `"F"` as an **unknown code**.
- With ordinals, v1 could suffer an out-of-range error or mis-map it to an existing constant.
- Stable codes help **fail clearly**, though they do not automatically teach an old version how to handle new business semantics.

Forward compatibility strategies:
- Unknown-as-error for strict workflows.
- Preserve the raw code at the integration/event forwarding layer.
- Version the message schema.
- Feature gating so new values are not emitted before consumers are ready.
- Use a sealed result type like `Known(Status) / Unknown(String rawCode)` at the boundary if unknown values must be preserved.

Do not arbitrarily add an `UNKNOWN` enum constant and map every unfamiliar code to it if the system needs to preserve the original code for retry/replay.

## 42. Synchronizing Codes Across Multiple Languages

A Java service has:

```java
PAID("P")
```

A Go/TypeScript service can have a corresponding constant `"P"`. The systems coordinate by the **protocol field `"P"`**, not by whichever declaration order each side chooses.

Define codes in:
- API specification.
- Schema registry/IDL when appropriate.
- Shared contract tests.
- Migration/deprecation documentation.
- Generated code or constants produced from a contract source if the system supports it.

**Do not force multiple languages to commit to the same Java ordinal**. Each language has different enum semantics, and reordering a Java source file is not a protocol versioning mechanism.

## 43. Compatibility When Renaming Constants

Suppose the business wants to rename the Java constant `PAID` to `SETTLED`, while the external code still needs to remain `"P"`.

```java
enum Status {
    SETTLED("P");
    // ...
}
```

If the code mapping stays unchanged, old `"P"` data still decodes accurately to the new constant. This is a clear benefit of a **stable explicit code** compared to storing `name()`.

However, there are other compatibility surfaces:
- Old Java source code referencing `Status.PAID` will have to be updated.
- Old data storing enum names via `name()` or Java native enum serialization may be affected.
- Audit logs/metrics using `name()` may need mapping.
- External clients calling constant names directly, if a Java API is published, will need migration.

Stable codes protect **the persistence/wire boundary that chose to use the code**; they do not guarantee automatic compatibility across every other API.

## 44. Do Not Reuse Codes from Deleted Statuses

A very important rule for longevity:

If `CANCELLED("C")` is retired, **do not assign `"C"` to another status such as `CHARGEBACK`**, because historical rows/events carrying `"C"` still mean CANCELLED.

Alternatives can be:
- Keep a deprecated constant if the domain still has to read old data.
- Map legacy `"C"` to a historical record representation with clear meaning.
- Use an old-code translation table with a migration.
- Reserve a new code for the new status.
- Version the API/schema if the semantics change fundamentally.

**Swapping a code under the same string is a breaking data-contract change**, even if `ordinal()` no longer appears.

## 45. Logging and Auditing: Which Name Should Be Recorded?

An audit record should contain:
- A stable event type.
- A stable status code.
- Context (entity ID, timestamp, actor).
- A schema version if replay is needed.
- A human-readable label as supplemental information, not the sole identifier.

Illustrative message example:

```text
order_id=10 status_code=P status_label=Paid schema_version=2
```

Do not record only `status_ordinal=1`, because future readers will not know which source enum produced it.

Even if logs are retained very short-term, ordinals can still cause trouble when an incident investigation spans deployments. Stable codes are usually cheaper in the long run.

## 46. When Is an Explicit Code Still Not Enough?

A code can stay stable while **its semantics change**. For example, `"P"` meant "paid in full" yesterday, and today means "deposit paid". Keeping the same code can make the data syntactically compatible while **incompatible in business semantics**.

You additionally need:
- Versioning or a new status with a new code.
- A migration governed by business rules.
- Validation and contract tests.
- Documentation of when the meaning changed.
- Ownership control over schema changes.

**Stable syntax does not automatically guarantee stable meaning.** Avoiding `ordinal()` is only the first line of defense.

## 47. Difference from Java Native Enum Serialization

Java native object serialization has its own mechanism for enum constants: fundamentally it resolves by enum type/name and does not store `ordinal()` as a public persistence representation for constants the way many developers implement manually.

This has two consequences:
- Java native enum deserialization should not be described as a simple `values()[ordinal]`.
- Renaming/removing an enum constant can still cause compatibility issues due to old name/type data.

JSON libraries, ORMs, Protobuf, and other serializers **have their own mapping policies**. Do not assume that because native Java enum serialization relies on names, every framework behaves the same way.

### Common Misconception Example

Saying "Java can already serialize enums, so storing `ordinal()` in the DB will also be safe" is wrong: you are choosing a different representation from the standard serialization mechanism.

## 48. Checklist for Reviewing Persistence Code

When seeing an enum field written to a database or message:

1. Is the wire/database field a number or a String?
2. Does that number come from an **explicit code** or from `ordinal()`?
3. If the source enum is reordered, does the raw stored value retain its meaning?
4. If a new constant is added, how do old readers react?
5. If a constant is renamed, does the raw stored value get altered?
6. Where is the mapping documented, and does it have an owner?
7. Is there uniqueness validation?
8. Is there a clear policy for unknown/null/empty codes?
9. Are there long-lived historical records using old mappings?
10. Are there integration tests reading old data with the new version?
11. Is there a rolling deployment with mixed versions?
12. Is there auditing/observability for unknown codes?
13. Are there DB constraints/DDL migrations that need updating?
14. Is `values()[id]` accidentally used anywhere?
15. Is `toString()` used as an ID anywhere?
16. Is the JPA mapping ORDINAL, STRING, or a converter?
17. If using `EnumType.STRING`, how are renames/deletions managed?
18. If using explicit codes, have you ensured old codes are not reused for new meanings?
19. Is there a safe rollback path when readers/writers switch columns?
20. Are there tests that detect double meanings of historical ordinals?

## 49. Exercise 1 — Inserting a Constant in the Middle

Given:

```java
enum Status {
    NEW, PAID, SHIPPED
}
```

The DB stores `PAID.ordinal()`. After changing the declaration to `NEW, REVIEW, PAID, SHIPPED`, what does the old number `1` decode to using `values()[1]`?

**Answer:** `REVIEW`, not PAID. This is silent data corruption if the system does not detect the mismatch.

## 50. Exercise 2 — Reordering While Keeping Names Unchanged

`enum Color { RED, GREEN, BLUE }` is changed to `BLUE, RED, GREEN`. Does `Color.RED.name()` change? Does `ordinal()` change?

**Answer:** `name()` stays `"RED"`; `ordinal()` changes from 0 to 1.

## 51. Exercise 3 — Are Numeric Codes Always Bad?

`enum Status { NEW(100), PAID(200) }` with constructor field `code`. Does storing `status.code()` in the DB have the same problem as ordinal?

**Answer:** No, if `100`/`200` are defined and kept stable as an independent contract. Integers are not the problem; **deriving them from declaration position** is the problem.

## 52. Exercise 4 — Using `name()`

Store `status.name()` and then reorder constants. Does the DB get the wrong meaning?

**Answer:** No, because reordering does not change names. However, renaming/deleting constants still requires a migration/compatibility strategy.

## 53. Exercise 5 — Using `toString()`

An enum overrides `toString()` to return a Vietnamese label. Should the result be stored in the DB as the canonical status?

**Answer:** Usually no; UI labels can change by language and wording. Separate the stable code from the display label.

## 54. Exercise 6 — Unknown Ordinal Within Range

The DB contains the number 1; the new enum has 4 constants. `values()[1]` runs without error. Can we conclude the data is correct?

**Answer:** No. A number that is valid as an index can still have had a different meaning in the old version.

## 55. Exercise 7 — Unknown Ordinal Out of Range

An old record has the number 9, and the current enum has 4 constants. What does `values()[9]` do?

**Answer:** `ArrayIndexOutOfBoundsException`. Catching the exception does not solve cases where the number is valid in range yet mapped to the wrong constant.

## 56. Exercise 8 — Legacy Mapping

V1: `0 NEW, 1 PAID, 2 SHIPPED`. V2: `0 NEW, 1 REVIEW, 2 PAID, 3 SHIPPED`. When backfilling a record with legacy ordinal 2, which stable code is it?

**Answer:** The code of `SHIPPED` according to the V1 mapping, such as `"S"`, not V2's code for PAID.

## 57. Exercise 9 — Mixed Versions

V1 and V2 both wrote raw ordinal 1 representing two different statuses; there is no schema version.

**Answer:** It is not always possible to infer the right constant from the number 1 alone. Supplemental historical/audit data is needed to classify them, or inconclusive records must be handled separately.

## 58. Exercise 10 — Duplicate Codes

`NEW("N")` and `NOTIFIED("N")` share the same code `N`. Which decoder is dangerous?

**Answer:** A decoder that picks the first/order-dependent constant and ignores duplicates; the mapping becomes order-dependent or gets overwritten. Unique codes must be validated and fail-fast on duplicates.

## 59. Exercise 11 — When Is the Static Map Created?

Should you write the enum constructor `Registry(String code) { BY_CODE.put(code,this); }` when `BY_CODE` is a static mutable map field declared after the constants?

**Answer:** No, you should not, and there are compile-time initialization restrictions regarding referencing static nonconstant fields of an enum inside its constructor. Build the map in a static block after the constants, once `values()` is ready.

## 60. Exercise 12 — JPA ORDINAL

A field uses `@Enumerated(EnumType.ORDINAL)`. A developer inserts a constant in the middle of the enum list without a DB migration.

**Answer:** There is a risk of old data being misread. You need to inspect raw stored values, historical mappings, and managed migrations/mappers.

## 61. Exercise 13 — JPA STRING

Does switching the mapping to `EnumType.STRING` automatically convert old integers to the right names?

**Answer:** No. Data migration and verification are needed; the annotation changes the representation in code, without automatically recovering the meaning of historical ordinals.

## 62. Exercise 14 — Appending a Constant at the End

Does adding `REFUNDED` to the end of the enum break the ordinals of old constants?

**Answer:** It does not shift old ordinals in that change itself. However, old consumers may not be able to handle the new constant and the risk of future reordering still exists; do not use this as a reason to design long-term ordinal persistence.

## 63. Exercise 15 — Idempotent Migration

What can go wrong if a backfill runs a second time and reads from the already-migrated column instead of the legacy field?

**Answer:** It could misread the new code as an ordinal or rewrite based on the wrong mapping. A migration must have explicit source/target columns and version/idempotency conditions; test reruns and rollback.

## 64. Exercise 16 — Name vs. Code After a Rename

The Java constant is renamed `PAID` → `SETTLED`, while the external code remains `"P"`. Does data using the code still decode validly?

**Answer:** Yes, it can, if the new decoder maps `"P"` to SETTLED and the semantics stay the same. Data storing `name() == "PAID"` needs separate handling.

## 65. Exercise 17 — Multi-Language Data

A Go service and a Java service share the same status protocol. Should Java's `ordinal` be transmitted?

**Answer:** No. Publish an explicit stable code in the shared schema; each language has its own implementation/mapping and contract tests.

## 66. Exercise 18 — Defaulting Unknown to NEW

A decoder receives an unknown code `"F"` and returns `Status.NEW`. Is that safe?

**Answer:** Usually not for sensitive business logic: unknown and NEW are two different semantics. Return an error or an Unknown representation containing the raw code according to requirements.

## 67. Exercise 19 — EnumSet

In what order does `EnumSet` iterate constants? Should the iteration position be persisted?

**Answer:** Natural declaration order. Do not persist the position as an ID; the Set can represent the constants directly, or each constant outputs its stable code when stored.

## 68. Exercise 20 — Retired Statuses

An old status with code `"C"` is no longer used. Can C be reused for a new status?

**Answer:** You should not if historical events/records still exist. Reusing it will give old data the new meaning. Use a new code and managed migration/aliases.

## 69. Exercise 21 — Which Test Is Better?

A. `assertEquals(1, Status.PAID.ordinal())`.  
B. `assertEquals("P", Status.PAID.code())` and `assertSame(Status.PAID, Status.fromCode("P"))`.

**Answer:** B protects the persistence contract. A only protects declaration order and ties the test to an implementation detail that can be refactored.

## 70. Exercise 22 — Stable Code with Changed Semantics

Code `"P"` previously meant "paid in full", and later means "partially paid". Is data still fully compatible?

**Answer:** No. The code remains the same, yet business semantics changed; a new version/code or deliberate migration is needed.

## 71. Exercise 23 — Assigning an Explicit Rank

An enum declares HIGH, LOW, MEDIUM, while its `rank` field is 30, 10, 20. What should be used to sort by priority?

**Answer:** `Comparator.comparingInt(Status::rank)` (with the appropriate enum type), not `ordinal()`. Rank can differ from source position.

## 72. Exercise 24 — Null Code

What should `fromCode(null)` do?

**Answer:** Depends on the API: fail with a clear exception or return Optional.empty. Do not silently map it to a valid status if null does not carry that meaning; document the contract.

## 73. Exercise 25 — Serializer

Java native enum serialization uses a special mechanism by type/name. Does that prove storing `ordinal()` in JSON/DB is safe?

**Answer:** No. Native serialization and custom persistence mappings are different. Each boundary must specify its own representation.

## 74. Exercise 26 — Constant Identity

Is `Status.PAID == Status.valueOf("PAID")` true?

**Answer:** True when Status has a PAID constant, because `valueOf` returns the canonical enum constant. Identity semantics say nothing about ordinal stability.

## 75. Exercise 27 — Should Historical Ordinals Be Hardcoded in a Migration?

Is `switch (oldOrdinal) { case 1 -> PAID; ... }` "violating the advice not to use ordinal"?

**Answer:** No, if it is **isolated within a migration from a verified historical schema** and not used as a new write representation. This is a controlled way of reading old ordinal data.

## 76. Exercise 28 — Is Reordering Allowed After Adopting Stable Codes?

If all external mappings truly use explicit stable codes, is reordering completely safe?

**Answer:** Not necessarily: `values()`, `ordinal()`, `compareTo`, `EnumSet`/`EnumMap` iteration, and UI source-order code can still change. Stable codes protect the designed boundary, not every behavior.

## 77. Exercise 29 — Unit of Migration Verification

A migration converts 0→N, 1→P, 2→S. Should only the row count be checked?

**Answer:** No. Row-level sampling/business invariants, distribution by status, unknown counts, unique constraints, dual-write consistency, and a rollback plan are needed.

## 78. Exercise 30 — Final Decision

An application has an enum stored in the DB, sent over Kafka, and used in a public API. Choose `ordinal()`, `name()`, or an explicit code?

**Answer:** Usually prefer an **explicit stable code** with a specification, decoder, uniqueness validation, migration policy, and compatibility tests. `name()` can be used when source names are committed to remain stable; `ordinal()` should not serve as a long-lived contract.

## 79. Checklist to Avoid Ordinal Persistence

- [ ] Do not write `enum.ordinal()` directly to a DB/API/event/config if the value needs to persist.
- [ ] Do not read historical data via `EnumType.values()[saved]` if the declaration has ever changed.
- [ ] Document exact historical ordinal mappings if the legacy system used ordinals.
- [ ] Declare stable String/int codes separately, not derived from index/ordinal.
- [ ] Ensure each code is unique and non-null according to the contract.
- [ ] Have tests that detect duplicate codes.
- [ ] Have tests preserving the code ↔ constant mapping across reordering.
- [ ] Have a policy for renaming/deleting/retiring constants.
- [ ] Do not reuse old codes for new meanings.
- [ ] Do not use UI `toString()` as a persistence code.
- [ ] If storing `name()`, manage rename risks.
- [ ] If using JPA, verify whether `ORDINAL`/`STRING`/converter mapping is actually being applied.
- [ ] Do not change a JPA annotation while skipping migration of existing data.
- [ ] Migrate using the **correct historical version**, not the enum's current values.
- [ ] Measure statistics of invalid/mixed-era values before migration.
- [ ] Have a strategy for handling historical ordinals that cannot be decoded with certainty.
- [ ] Have a realistic rolling deploy/dual-read/dual-write plan.
- [ ] Have rollback and data integrity verification.
- [ ] List codes and semantics in API schemas/public docs.
- [ ] Detect and handle unknown codes according to the contract.
- [ ] Do not default unknown values to a normal business status without justification.
- [ ] Have automated producer/consumer contract tests.
- [ ] Have observability for decoding errors in production.
- [ ] Distinguish between code, name, label, rank, and ordinal.
- [ ] Assess the impact of reordering on sorting/`values()`/`EnumSet`/`EnumMap`.
- [ ] Do not introduce codes generated from `ordinal()+1` or other ordinal arithmetic.
- [ ] Build lookup maps after enum constants are ready.
- [ ] If sharing an enum contract with other languages, have all sides use the same stable codes.
- [ ] When semantics change, introduce an appropriate version or new code.
- [ ] Test reordering/adding a constant in your implementation and verify persisted codes do not change.

## 80. Summary

`ordinal()` is the **zero-based position of an enum constant in the current source declaration**. It is not a stable business code, even though Java guarantees the identity of each constant. Inserting, deleting, or reordering constants can change ordinals and cause old database records and message/API payloads to be misinterpreted.

**For data to survive across multiple software versions:**
1. Declare an **explicit String/int code** for each constant.
2. Write `code()` and `fromCode(...)` independently of declaration order.
3. Validate code uniqueness and handle null/unknown explicitly.
4. Manage codes as an **external contract**: do not arbitrarily change or reuse them.
5. If ordinals were already stored, migrate based on the **correct historical mapping**, not on the new enum source.
6. Test database/API compatibility when adding/renaming/reordering constants.

In short: **`ordinal()` returns a number representing a constant's position, not a promise about what that number will mean in a future release.** Separate those two roles before letting an enum leave the memory of a single runtime execution.

## Java 17 References

- Java SE 17 `java.lang.Enum.ordinal()` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html#ordinal()
- Java SE 17 JLS `8.9 — Enum Classes`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9
- Java SE 17 `EnumSet`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html
- Java SE 17 `EnumMap`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html
