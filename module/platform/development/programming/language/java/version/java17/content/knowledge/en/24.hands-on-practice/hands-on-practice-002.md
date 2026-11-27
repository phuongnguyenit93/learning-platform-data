# Validating and Normalizing Data in Constructors

## 1. Constructors as the Boundary Protecting Object State

A constructor does more than assign parameters to fields. It is the point where an object is created and begins participating in the program. If an object represents a domain concept, invalid states must be rejected right when the object is constructed.

For example, an account might require:

- The account code must not be null or empty.
- The code is normalized to uppercase for consistent comparison.
- The display name must not contain only whitespace.
- The credit limit must not be negative.
- The list of tags must not contain null elements.
- Passed-in array data must not allow the caller to mutate internal state after the constructor returns.

If a constructor merely assigns values without enforcing these conditions, the object can exist in an invalid state. Such bugs often surface much later, in a method unrelated to where the data entered.

A good constructor ensures the object satisfies its **invariants** from the moment it is created. An invariant is the set of conditions that must always hold true for a valid instance throughout its lifetime.

In Java 17, validating and normalizing data in constructors typically combines:

- `Objects.requireNonNull` to reject required null parameters.
- `IllegalArgumentException` to reject invalid values.
- Explicit normalization operations such as `strip()`, `toUpperCase(Locale.ROOT)`, and Unicode normalization.
- Defensive copies for mutable collections and arrays.
- Constructor delegation to centralize invariants in one place.
- Compact constructors on records when using records as data carriers.

## 2. Distinguishing Validation and Normalization

### 2.1. Validation: Does the Data Satisfy the Contract?

Validation checks whether a value lies within the permitted domain. For example:

- Does the product code match the expected format?
- Is the quantity greater than 0?
- Is the end date on or after the start date?
- Is the item list empty?
- Is a status within the supported set of statuses?

If a value is invalid, the constructor refuses to create the object:

```java
if (quantity <= 0) {
    throw new IllegalArgumentException(
            "quantity must be greater than zero"
    );
}
```

### 2.2. Normalization: Bringing Data to a Consistent Representation

Normalization converts equivalent inputs into a canonical form defined by the domain contract. For example:

- Stripping leading and trailing whitespace from a code.
- Normalizing Unicode to NFC.
- Converting case-insensitive codes to uppercase using `Locale.ROOT`.
- Copying collections so the object owns its own snapshot.

For example:

```java
String normalizedCode = rawCode.strip().toUpperCase(Locale.ROOT);
```

After normalization, the constructor must still perform validation. Not every value becomes valid merely because it has been converted into canonical form.

### 2.3. Common Processing Order

A simple flow:

```text
Constructor arguments
        |
        v
Check required references for null
        |
        v
Normalize representation
        |
        v
Validate format, range and cross-field rules
        |
        v
Defensively copy mutable input
        |
        v
Assign fields
        |
        v
Valid object
~~~

You can adjust the copy/normalize order depending on the data type, as long as the constructor never lets a caller's mutable reference leak into the object.

### 2.4. Do Not Turn Normalization into Silent Data Modification

Do not automatically coerce an invalid value into another value unless the domain explicitly defines that rule.

For example, if a negative quantity is invalid, do not silently clamp it:

```java
this.quantity = Math.max(0, quantity);
```

This turns an input error into zero and can hide caller bugs. Reject it with an exception unless the business contract truly requires clamping values.

Similarly, do not silently truncate overly long user names, round money, or strip unexpected characters without an explicit business rule.

## 3. Choosing Exceptions for Invalid Data

### 3.1. Required Nulls: NullPointerException

For a required parameter, `Objects.requireNonNull` expresses the contract clearly:

```java
this.name = Objects.requireNonNull(name, "name must not be null");
```

If `name` is null, the constructor throws `NullPointerException` with the provided message.

This is an API contract: the caller must supply a reference. Using NPE here distinguishes a missing reference from a present value with invalid content.

### 3.2. Present but Invalid Values: IllegalArgumentException

For example:

```java
if (name.isBlank()) {
    throw new IllegalArgumentException("name must not be blank");
}
~~~

The name is a valid `String` by type, but its content fails the contract. `IllegalArgumentException` indicates that the caller passed an impermissible argument.

Other examples:

```java
if (age < 0) {
    throw new IllegalArgumentException("age must not be negative");
}

if (endDate.isBefore(startDate)) {
    throw new IllegalArgumentException(
            "endDate must not be before startDate"
    );
}
~~~

### 3.3. Domain Exceptions When Extra Semantics Are Needed

A domain can define its own exception if callers need to handle errors by business category:

```java
public final class InvalidAccountCodeException
        extends IllegalArgumentException {

    public InvalidAccountCodeException(String message) {
        super(message);
    }
}
~~~

Do not create a dedicated exception class for every minor check. Create one only when the error type or additional metadata makes the API easier to use and handle.

### 3.4. Messages Should Identify the Parameter and Violated Rule

Good messages:

```text
creditLimit must be zero or greater
accountCode must match [A-Z0-9-]{3,20}
endDate must not be before startDate
~~~

Unhelpful messages:

```text
Invalid input
Bad value
Something went wrong
~~~

Do not include passwords, tokens, sensitive personal information, or entire payloads in exception messages or logs. The parameter name and violated rule are usually sufficient for callers to fix the issue.

## 4. Checking Null and Blank Strings

### 4.1. requireNonNull

```java
String code = Objects.requireNonNull(rawCode, "rawCode");
~~~

This checks only for null. It does not reject an empty string or a string containing only whitespace.

### 4.2. isEmpty and isBlank

| Method | Meaning |
|---|---|
| `isEmpty()` | String has length 0 |
| `isBlank()` | String is empty or contains only characters recognized by Java as whitespace |
| `strip()` | Returns a new string with leading and trailing whitespace removed according to Java Unicode rules |
| `trim()` | Older API that only removes characters with code point at most U+0020 |

In Java 17 code, `strip()` and `isBlank()` are usually better suited than `trim()` when the contract must handle Unicode whitespace.

For example:

```java
String value = Objects.requireNonNull(rawValue, "rawValue");
String normalized = value.strip();

if (normalized.isEmpty()) {
    throw new IllegalArgumentException(
            "rawValue must not be blank"
    );
}
~~~

### 4.3. Creating a Shared Helper

```java
private static String requireText(String value, String name) {
    Objects.requireNonNull(value, name + " must not be null");

    String normalized = value.strip();
    if (normalized.isEmpty()) {
        throw new IllegalArgumentException(
                name + " must not be blank"
        );
    }
    return normalized;
}
~~~

This helper works well for fields that require non-empty text and want leading/trailing whitespace removed. Do not apply it mechanically to every `String`: passwords, tokens, signatures, or data where whitespace is meaningful must be preserved as-is.

### 4.4. Blank Differs from Punctuation-Only Strings

For example, `"---"` is not blank, yet it may not be a valid code. `isBlank()` checks only whitespace; format validation still requires its own rule.

## 5. Normalizing Identifiers

### 5.1. Use Locale.ROOT for Language-Independent Codes

If an account code is defined as case-insensitive, it can be normalized to uppercase:

```java
String code = rawCode.strip().toUpperCase(Locale.ROOT);
~~~

Use `Locale.ROOT` instead of the machine's default locale. Case conversion of technical codes should never vary with the user's language or OS locale.

For instance, some letters have locale-specific uppercase/lowercase mappings. Relying on the default locale can cause the same input to produce different codes on two machines.

Do not uppercase every display name. Personal names, addresses, and free-form text generally need to preserve their original casing according to the contract.

### 5.2. Validate Format After Normalization

For example, an account code allowing ASCII letters, digits, and hyphens:

```java
private static final Pattern ACCOUNT_CODE =
        Pattern.compile("[A-Z0-9-]{3,20}");

private static String normalizeAccountCode(String rawCode) {
    Objects.requireNonNull(rawCode, "accountCode must not be null");

    String code = Normalizer.normalize(
            rawCode.strip(),
            Normalizer.Form.NFC
    ).toUpperCase(Locale.ROOT);

    if (!ACCOUNT_CODE.matcher(code).matches()) {
        throw new IllegalArgumentException(
                "accountCode must match [A-Z0-9-]{3,20}"
        );
    }
    return code;
}
~~~

This rule is an example for a specific domain. If the system allows Unicode identifiers, design an explicit character policy covering normalization form, confusable characters, and comparison rules.

### 5.3. Do Not Use a Simple Regex for Every Format

A short email regex cannot accurately describe every valid email address. If a constructor holds an email, it can:

- Reject null/blank.
- Trim leading/trailing whitespace if the contract allows it.
- Normalize the domain according to an appropriate policy.
- Use a dedicated validator at the boundary if full syntax validation is needed.
- Avoid lowercasing the local-part unless the domain contract allows it.

Syntax validation does not prove an address exists or belongs to the user. Ownership verification requires a separate process such as sending a confirmation code.

## 6. Unicode Normalization and Display Strings

### 6.1. Two Visually Identical Strings Can Have Different Representations

Unicode can represent a visible character as a single code point or as a base character combined with combining marks. Two strings may look identical without sharing the same sequence of code points.

For example, an accented letter can be represented in precomposed form or as a base letter plus a combining mark. If a string is used as a comparison key, cache key, or identifier, decide on a normalization form.

### 6.2. Using java.text.Normalizer

```java
String normalized = Normalizer.normalize(
        rawName,
        Normalizer.Form.NFC
);
~~~

Common forms:

- **NFC:** canonical decomposition followed by canonical composition.
- **NFD:** canonical decomposition.
- **NFKC:** compatibility decomposition followed by canonical composition.
- **NFKD:** compatibility decomposition.

NFC is usually the right choice when you want canonically equivalent representation while preserving compatibility distinctions. NFKC can fold compatibility characters into different normalized forms and erase meaningful distinctions in some domains.

Do not pick NFKC just because its name sounds "stronger". Define the identifier contract and assess the impact on existing data.

### 6.3. Normalization Does Not Solve Every Unicode Issue

Normalization alone does not address:

- Look-alike characters from different scripts (confusables).
- Script mixing.
- Control characters or invisible characters.
- Grapheme cluster boundaries.
- Language-specific sorting/collation rules.

If an identifier is used in security, access control, or URLs, define a dedicated character and comparison policy. Do not rely solely on normalization to prevent name spoofing.

### 6.4. Preserve Display Text When Appropriate

For display names, it is usually best to:

1. Reject null.
2. Strip leading/trailing whitespace if the contract permits.
3. Apply Unicode normalization if the system requires a canonical representation.
4. Preserve casing and punctuation.

Do not automatically lowercase names or strip accents, as that can alter meaning or how the user intends their name to appear.

## 7. Validating Numeric Ranges and Monetary Values

### 7.1. Range Checks

For example, quantity must be positive:

```java
public Quantity(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException(
                "quantity must be greater than zero"
        );
    }
    this.value = value;
}
~~~

For bounded intervals:

```java
if (percentage < 0 || percentage > 100) {
    throw new IllegalArgumentException(
            "percentage must be between 0 and 100"
    );
}
~~~

Inclusive/exclusive boundary checks must reflect business logic accurately. Do not use `>=` instead of `>` just to guard against zero if zero is a valid value.

### 7.2. BigDecimal for Money

Do not use `double` to represent money when exact decimal arithmetic is needed. You can use `BigDecimal`:

```java
public Money(BigDecimal amount) {
    Objects.requireNonNull(amount, "amount");
    if (amount.signum() < 0) {
        throw new IllegalArgumentException(
                "amount must not be negative"
        );
    }
    this.amount = amount;
}
~~~

`BigDecimal` is immutable, so no defensive copy is needed.

### 7.3. Scale Is Part of the Contract

Do not automatically call `setScale(2, RoundingMode.HALF_UP)` in every monetary constructor. That is a business rule about precision and rounding, not merely format normalization.

If the domain requires at most two decimal places:

```java
if (amount.scale() > 2) {
    throw new IllegalArgumentException(
            "amount must have at most two fractional digits"
    );
}
~~~

If the domain accepts higher precision but requires rounding, choose an explicit rounding mode and document it in the contract. Distinguish an amount with scale 2 from an amount of equal numeric value with scale 4; `BigDecimal.equals` considers scale, whereas `compareTo` compares numeric value.

### 7.4. Avoiding Overflow in Arithmetic Checks

If an invariant depends on an integer sum or product, use overflow-checking arithmetic:

```java
long total = Math.addExact(first, second);
~~~

If overflow is invalid, let `ArithmeticException` propagate or translate it into an appropriate domain exception. Never let values wrap around and construct a corrupted object.

## 8. Multi-Field Validation and Cross-Field Invariants

Some conditions can only be evaluated by examining multiple parameters together:

- End date must not precede start date.
- Birth date must not be in the future if required by the domain.
- Amount must be non-negative and the currency must be supported.
- A min/max range must satisfy `min <= max`.
- Payment status must be consistent with payment timestamp.

For example:

```java
public DateRange(LocalDate start, LocalDate end) {
    this.start = Objects.requireNonNull(start, "start");
    this.end = Objects.requireNonNull(end, "end");

    if (end.isBefore(start)) {
        throw new IllegalArgumentException(
                "end must not be before start"
        );
    }
}
~~~

In critical code, validate all parameters into local variables before assigning fields:

```java
LocalDate normalizedStart =
        Objects.requireNonNull(start, "start");
LocalDate normalizedEnd =
        Objects.requireNonNull(end, "end");

if (normalizedEnd.isBefore(normalizedStart)) {
    throw new IllegalArgumentException(
            "end must not be before start"
    );
}

this.start = normalizedStart;
this.end = normalizedEnd;
~~~

This style clearly separates the validation phase from the state assignment phase. It is especially helpful when a constructor has many parameters and invariants spanning multiple fields.

### 8.1. Do Not Implicitly Depend on Current Time

If a constructor checks that an end date is after "today", the outcome depends on when the object is constructed and the default timezone.

Instead of calling `LocalDate.now()` implicitly inside a constructor, pass a `Clock` or move the temporal policy to a service/domain operation. For an object representing a valid date range, checking `end >= start` is a stable invariant; a rule like "cannot book in the past" usually belongs to the booking operation at a specific point in time.

## 9. Defensive Copies for Collections and Arrays

### 9.1. The Problem with Mutable Collections

This code retains a reference to the caller's list:

```java
public class Team {
    private final List<String> members;

    public Team(List<String> members) {
        this.members = members;
    }
}
~~~

The caller can mutate the list after the constructor returns:

```java
List<String> names = new ArrayList<>();
names.add("An");

Team team = new Team(names);
names.add("Bình"); // team state changes as well
~~~

A `final` field only prevents reassigning the reference. It does not make the referenced object immutable.

### 9.2. Using List.copyOf

Java 10 and later provide `List.copyOf`, which is available in Java 17:

```java
public Team(List<String> members) {
    this.members = List.copyOf(
            Objects.requireNonNull(members, "members")
    );
}
~~~

`List.copyOf` creates an unmodifiable list that does not retain an alias to the original mutable collection in a way that lets the caller mutate the snapshot. It also rejects null elements.

If the caller passes an already immutable list, the implementation may reuse the instance; the key contract is that the caller cannot mutate the collection observed by the object.

### 9.3. Normalizing Each Element

If every member must be non-blank text:

```java
private static List<String> normalizeMembers(List<String> input) {
    Objects.requireNonNull(input, "members");

    List<String> normalized = new ArrayList<>(input.size());
    for (String member : input) {
        normalized.add(requireText(member, "member"));
    }
    return List.copyOf(normalized);
}
~~~

This validates and normalizes each element before creating an immutable snapshot. If duplicates must be removed, use a clear structure and ordering rule; do not switch to a `Set` if order is part of the contract.

### 9.4. Defensive Copy Is Only a Shallow Copy

`List.copyOf` copies only the collection structure; it does not clone the elements inside. If the list contains mutable objects, the caller can still mutate those objects.

For example:

```java
List<Address> addresses = List.copyOf(input);
~~~

If `Address` is mutable, the object owning the list still observes mutations to each address. You can:

- Use immutable element types.
- Convert each element into an immutable value object.
- Perform a deep copy according to the domain contract.

There is no single safe generic deep copy for arbitrary object types.

### 9.5. Arrays Must Be Cloned

Arrays are always mutable:

```java
public final class Digest {
    private final byte[] bytes;

    public Digest(byte[] bytes) {
        this.bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

Cloning in the constructor prevents the caller from mutating the input array. Cloning in the accessor prevents the caller from mutating internal state after retrieving the value.

If you clone only in the constructor while the getter returns the internal array directly, the object can still be mutated from outside.

### 9.6. Maps and Sets

The corresponding immutable copy factories:

```java
this.roles = Set.copyOf(roles);
this.attributes = Map.copyOf(attributes);
~~~

They reject null collections and null keys/values by contract. If you need to normalize keys or values or preserve a specific order, create a copy and process elements explicitly before calling `Map.copyOf`/`Set.copyOf`.

## 10. Complete Example: Constructor Enforcing Invariants

Let us build `CustomerAccount` with these rules:

- `accountCode` is required, normalized to NFC, stripped, and uppercased with `Locale.ROOT`.
- The code allows only `A-Z`, `0-9`, and hyphens, 3 to 20 characters long.
- `displayName` is required, stripped, and normalized to NFC, while preserving casing.
- `creditLimit` is required and non-negative.
- `tags` are normalized, non-blank, non-null, and stored as an immutable list.
- Reference bytes are cloned both on input and on output.

~~~java
import java.math.BigDecimal;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;

public final class CustomerAccount {

    private static final Pattern ACCOUNT_CODE =
            Pattern.compile("[A-Z0-9-]{3,20}");

    private final String accountCode;
    private final String displayName;
    private final BigDecimal creditLimit;
    private final List<String> tags;
    private final byte[] externalReference;

    public CustomerAccount(
            String accountCode,
            String displayName,
            BigDecimal creditLimit,
            List<String> tags,
            byte[] externalReference
    ) {
        String normalizedCode = normalizeAccountCode(accountCode);
        String normalizedName = normalizeDisplayName(displayName);
        BigDecimal checkedLimit = validateCreditLimit(creditLimit);
        List<String> copiedTags = normalizeTags(tags);
        byte[] copiedReference =
                Objects.requireNonNull(
                        externalReference,
                        "externalReference must not be null"
                ).clone();

        this.accountCode = normalizedCode;
        this.displayName = normalizedName;
        this.creditLimit = checkedLimit;
        this.tags = copiedTags;
        this.externalReference = copiedReference;
    }

    private static String normalizeAccountCode(String raw) {
        Objects.requireNonNull(raw, "accountCode must not be null");

        String code = Normalizer.normalize(
                raw.strip(),
                Normalizer.Form.NFC
        ).toUpperCase(Locale.ROOT);

        if (!ACCOUNT_CODE.matcher(code).matches()) {
            throw new IllegalArgumentException(
                    "accountCode must match [A-Z0-9-]{3,20}"
            );
        }
        return code;
    }

    private static String normalizeDisplayName(String raw) {
        Objects.requireNonNull(raw, "displayName must not be null");

        String name = Normalizer.normalize(
                raw.strip(),
                Normalizer.Form.NFC
        );

        if (name.isEmpty()) {
            throw new IllegalArgumentException(
                    "displayName must not be blank"
            );
        }
        return name;
    }

    private static BigDecimal validateCreditLimit(BigDecimal value) {
        Objects.requireNonNull(value, "creditLimit must not be null");

        if (value.signum() < 0) {
            throw new IllegalArgumentException(
                    "creditLimit must not be negative"
            );
        }
        return value;
    }

    private static List<String> normalizeTags(List<String> input) {
        Objects.requireNonNull(input, "tags must not be null");

        List<String> normalized = new ArrayList<>(input.size());
        for (String tag : input) {
            String value = Objects.requireNonNull(
                    tag,
                    "tags must not contain null"
            ).strip();

            if (value.isEmpty()) {
                throw new IllegalArgumentException(
                        "tags must not contain blank values"
                );
            }
            normalized.add(
                    Normalizer.normalize(value, Normalizer.Form.NFC)
            );
        }
        return List.copyOf(normalized);
    }

    public String accountCode() {
        return accountCode;
    }

    public String displayName() {
        return displayName;
    }

    public BigDecimal creditLimit() {
        return creditLimit;
    }

    public List<String> tags() {
        return tags;
    }

    public byte[] externalReference() {
        return externalReference.clone();
    }
}
~~~

### 10.1. Why Use Local Variables Before Assigning Fields?

The constructor normalizes and validates parameters into local variables:

```java
String normalizedCode = normalizeAccountCode(accountCode);
String normalizedName = normalizeDisplayName(displayName);
...
this.accountCode = normalizedCode;
~~~

This makes it clear that values have passed validation before becoming object state. If validation fails, the constructor throws an exception and no instance is returned to the caller.

### 10.2. Why Does BigDecimal Not Need Cloning?

`BigDecimal` is immutable. There is no way to mutate an existing `BigDecimal` object; arithmetic operations return new instances. Therefore, the reference can be stored directly after validation.

### 10.3. Why Is List.copyOf Appropriate?

`tags` is built into a new list where each element is normalized, and then `List.copyOf` produces an unmodifiable collection. The caller cannot add or remove elements to alter the account's tags.

### 10.4. Why Must the byte[] Accessor Clone?

Arrays are mutable, so returning the internal reference lets the caller modify the data. The accessor returns a clone to protect the invariant after construction.

## 11. Constructor Delegation and Avoiding Duplicated Validation

### 11.1. Using this(...) to Centralize Logic

If a class has multiple constructors, delegate secondary constructors to one primary constructor:

~~~java
public final class Product {
    private final String code;
    private final String description;
    private final boolean active;

    public Product(String code) {
        this(code, "No description", true);
    }

    public Product(String code, String description) {
        this(code, description, true);
    }

    public Product(
            String code,
            String description,
            boolean active
    ) {
        this.code = requireText(code, "code");
        this.description = requireText(description, "description");
        this.active = active;
    }

    private static String requireText(String value, String name) {
        Objects.requireNonNull(value, name);
        String normalized = value.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
        return normalized;
    }
}
~~~

Every path to creating a `Product` goes through the primary constructor, so no overload skips invariant checks.

### 11.2. this(...) Must Be the First Statement

In a Java constructor, a `this(...)` call must appear first. Therefore, you cannot write validation statements before this call.

If a secondary constructor needs custom input normalization, move the rule into a static helper called inside the `this(...)` arguments, or let the primary constructor handle everything.

### 11.3. Avoiding Ambiguous Constructor Overloads

Multiple constructors differing only by parameters of similar types can be awkward to call, especially when callers pass `null`.

For example:

```java
new Report(null); // May be ambiguous if both String and Path overloads exist
~~~

When an API has many optional configurations, consider static factory methods or a builder so call sites are named and avoid overload ambiguity.

## 12. Using Static Factories When Input Conversion Is Needed

Constructors should focus on establishing object invariants. If inputs come from external formats such as date strings, JSON DTOs, or database rows, a static factory can convert them first:

~~~java
public final class Booking {
    private final LocalDate start;
    private final LocalDate end;

    public Booking(LocalDate start, LocalDate end) {
        LocalDate checkedStart =
                Objects.requireNonNull(start, "start");
        LocalDate checkedEnd =
                Objects.requireNonNull(end, "end");

        if (checkedEnd.isBefore(checkedStart)) {
            throw new IllegalArgumentException(
                    "end must not be before start"
            );
        }

        this.start = checkedStart;
        this.end = checkedEnd;
    }

    public static Booking fromIsoDates(
            String startText,
            String endText
    ) {
        LocalDate start = LocalDate.parse(
                Objects.requireNonNull(startText, "startText").strip()
        );
        LocalDate end = LocalDate.parse(
                Objects.requireNonNull(endText, "endText").strip()
        );
        return new Booking(start, end);
    }
}
~~~

Static factories make the conversion boundary explicit:

- Parse text input into domain types.
- Let the constructor enforce the domain object's invariants.

If parsing fails, `DateTimeParseException` is thrown. You can let callers handle format errors at the boundary or translate them into an API exception if a consistent message is required. Do not catch every `RuntimeException` and convert it into "invalid input", as that masks unrelated bugs.

## 13. Record Compact Constructors

### 13.1. Records Fit Value Data Carriers

Java 17 supports records. A record automatically generates private final fields, accessors, `equals`, `hashCode`, and `toString` based on its components.

Records can still validate and normalize components in their constructors. In a compact constructor, parameters can be reassigned; Java assigns their final values to the component fields after the constructor body finishes.

~~~java
public record DateRange(LocalDate start, LocalDate end) {
    public DateRange {
        start = Objects.requireNonNull(start, "start");
        end = Objects.requireNonNull(end, "end");

        if (end.isBefore(start)) {
            throw new IllegalArgumentException(
                    "end must not be before start"
            );
        }
    }
}
~~~

Do not write `this.start = start` inside a compact constructor; component assignment is generated by the compiler after the compact constructor body.

### 13.2. Normalizing Strings in a Record

~~~java
public record ProductCode(String value) {
    public ProductCode {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z0-9-]{3,20}")) {
            throw new IllegalArgumentException(
                    "value must match [A-Z0-9-]{3,20}"
            );
        }
    }
}
~~~

Once constructed, `ProductCode` always holds the normalized value.

### 13.3. Records Holding Collections Still Need Defensive Copies

A record does not automatically make referenced objects immutable:

~~~java
public record Team(List<String> members) {
    public Team {
        members = List.copyOf(
                Objects.requireNonNull(members, "members")
        );
    }
}
~~~

If `members` contains mutable elements, `List.copyOf` still copies only the list structure. Use immutable elements or deep copies according to the contract.

### 13.4. Records Do Not Fit Every Entity

Records fit data whose identity is defined by its components and that does not change after creation. For entities with independent identity, lifecycle, rich behavior, or different compatibility requirements, a regular class may be more appropriate.

Whether using a class or a record, invariants must still be protected.

## 14. What Should Constructors Avoid?

### 14.1. Do Not Perform I/O or Call Remote Services

Avoid writing:

~~~java
public Customer(String id) {
    this.id = id;
    this.profile = customerRepository.load(id);
}
~~~

The constructor now depends on a database, network, credentials, and system state. Object creation becomes slow, prone to environmental failures, and prone to hard-to-control side effects.

Perform I/O in a service or factory with explicit dependencies, then pass the loaded data into the constructor.

### 14.2. Do Not Register `this` Elsewhere Before Completion

Avoid letting `this` escape the constructor before all fields are initialized:

~~~java
public Listener() {
    Registry.register(this);
    this.name = "ready";
}
~~~

The registry or another thread could observe a partially initialized object. This is a form of `this` escape.

Register listeners after the object is completely constructed, such as via a lifecycle method or a factory managing initialization.

### 14.3. Do Not Call Overridable Methods in Constructors

A superclass constructor may invoke a method overridden by a subclass. That subclass method then executes before the subclass fields are fully initialized.

~~~java
class Base {
    Base() {
        initialize();
    }

    void initialize() {
    }
}

class Child extends Base {
    private String value = "ready";

    @Override
    void initialize() {
        System.out.println(value.length()); // value may still be null
    }
}
~~~

Avoid calling overridable methods from constructors. If invariant computation is needed, use private/static helpers or non-dispatchable logic.

### 14.4. Do Not Store Mutable Inputs Directly

Never rely on `final` to assume an array, collection, or `Date` is immutable. Copy mutable data or convert it to an appropriate immutable type.

### 14.5. Do Not Validate Partially and Skip Other Overloads

If a class has multiple constructors, all instantiation paths must converge on a single invariant check. Otherwise, one overload might produce valid objects while another creates invalid ones.

## 15. Constructor Validation vs. Application-Layer Validation

### 15.1. Two Layers Have Different Goals

Validation at the API/controller/form layer primarily serves input ergonomics:

- Displaying errors for specific fields.
- Aggregating multiple errors into one response.
- Checking request format.
- Converting JSON/form data into domain types.

Constructor validation protects object invariants:

- Does not depend on whether callers go through a controller.
- Guarantees valid objects when created from tests, batch jobs, message consumers, or internal services.
- Prevents invalid states from entering the domain model.

An API can use Jakarta Bean Validation annotations to validate request DTOs, but boundary annotation validation does not replace domain object invariants if the object must always be valid.

### 15.2. Do Not Duplicate Validation Pointlessly

You can validate formats at the boundary to return user-friendly errors while still protecting invariants in the constructor. The two places serve different purposes:

- Boundary: input errors and user feedback.
- Constructor: ensuring every object creation path honors the domain contract.

If the rule is complex, place it in a shared value object or helper to avoid divergent implementations.

### 15.3. Validation Requiring External Data Belongs in Services/Domain Operations

For instance, "email is not already used by another account" requires querying a repository. This is not an invariant verifiable from constructor parameters alone.

Check uniqueness in a service or domain operation using appropriate transactions and database constraints. Constructors check only intrinsic conditions such as null, blank, or contract format.

## 16. Testing Constructors

Constructor tests should verify all of the following:

- Valid inputs are normalized properly.
- Null inputs are rejected.
- Inputs with invalid format or range are rejected.
- Cross-field invariants are enforced.
- Mutable inputs cannot alter object state after creation.
- Accessors do not expose mutable internal state.

JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class CustomerAccountTest {

    @Test
    void normalizesAccountCodeAndDisplayName() {
        CustomerAccount account = new CustomerAccount(
                "  ac-100  ",
                "  Nguyễn An  ",
                new BigDecimal("100.00"),
                List.of(" premium "),
                new byte[] {1, 2, 3}
        );

        assertEquals("AC-100", account.accountCode());
        assertEquals("Nguyễn An", account.displayName());
        assertEquals(List.of("premium"), account.tags());
    }

    @Test
    void rejectsNullAccountCode() {
        assertThrows(
                NullPointerException.class,
                () -> new CustomerAccount(
                        null,
                        "An",
                        BigDecimal.ZERO,
                        List.of(),
                        new byte[0]
                )
        );
    }

    @Test
    void rejectsInvalidAccountCode() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new CustomerAccount(
                        "bad code",
                        "An",
                        BigDecimal.ZERO,
                        List.of(),
                        new byte[0]
                )
        );
    }

    @Test
    void rejectsNegativeCreditLimit() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new CustomerAccount(
                        "AC-100",
                        "An",
                        new BigDecimal("-0.01"),
                        List.of(),
                        new byte[0]
                )
        );
    }

    @Test
    void copiesTagsAndReferenceArray() {
        List<String> tags = new ArrayList<>(List.of("vip"));
        byte[] reference = {1, 2, 3};

        CustomerAccount account = new CustomerAccount(
                "AC-100",
                "An",
                BigDecimal.ZERO,
                tags,
                reference
        );

        tags.add("changed");
        reference[0] = 99;

        assertEquals(List.of("vip"), account.tags());
        assertArrayEquals(
                new byte[] {1, 2, 3},
                account.externalReference()
        );

        byte[] returned = account.externalReference();
        returned[1] = 88;

        assertArrayEquals(
                new byte[] {1, 2, 3},
                account.externalReference()
        );
    }
}
~~~

These tests illustrate how to verify a constructor contract. When applying them to a project, use the actual class package and test framework dependencies.

### 16.1. Testing Boundary Values

For each range or length condition, test:

- Minimum valid value.
- Maximum valid value.
- One value immediately below the boundary.
- One value immediately above the boundary.
- Null/blank if the data type permits them.

For example, a code with length 3 to 20 characters should be tested at lengths 2, 3, 20, and 21.

### 16.2. Testing Normalization Idempotence

A normalization function should typically be idempotent: normalizing once and then normalizing again produces the same result:

~~~java
String once = normalizeAccountCode(input);
String twice = normalizeAccountCode(once);
assertEquals(once, twice);
~~~

This is a useful property for identifier canonicalization. Do not apply it mechanically to transformations intended to vary with time or external state.

### 16.3. Testing the Immutability Boundary

Do not just check that getters return the expected data. Mutate inputs after construction and mutate outputs returned from accessors to confirm the object remains unchanged.

For collections containing mutable elements, also test mutating those elements if the contract requires deep immutability.

## 17. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Only assigning parameters to fields | Object can exist in an invalid state | Enforce invariants in the constructor |
| Calling `requireNonNull` and assuming validation is done | Empty strings, negative numbers, or bad formats slip through | Validate content after the null check |
| Using `trim()` for all strings | Whitespace rules are narrower than `strip()` | Choose the method according to the Java 17 contract |
| Using the default locale to normalize identifiers | Results can differ across machines/languages | Use `Locale.ROOT` for technical codes |
| Lowercasing display names | Alters user-supplied data | Normalize only fields with an explicit contract |
| Using a simple regex to validate full emails | May reject valid inputs or accept invalid ones | Use an appropriate validator and verify ownership separately |
| Using NFKC for all identifiers | May lose meaningful compatibility distinctions | Choose the Unicode normalization form per domain |
| Clamping invalid values to 0 | Hides input errors | Throw an exception unless the contract allows clamping |
| Storing caller's `List`/`Map`/`Set` directly | Caller can mutate the object after construction | Copy and store immutable collections |
| Cloning arrays only in the constructor | Getter still exposes internal array | Clone both on input and on output |
| Assuming `List.copyOf` is a deep copy | Mutable elements can still change | Use immutable elements or intentional deep copies |
| Duplicating validation across constructor overloads | Instantiation paths easily diverge | Use constructor delegation |
| Calling repositories/network inside constructors | Object creation has side effects and is hard to test/retry | Move I/O to a service or factory |
| Registering `this` before the constructor finishes | Object can be observed in a half-initialized state | Register after construction completes |
| Calling overridable methods from constructors | Subclass code may run before initialization finishes | Use private/static helpers |
| Validating only in controllers | Objects created from batches/tests/services can still be invalid | Keep invariants in domain constructors |
| Checking uniqueness in constructors | Constructor depends on DB and suffers race conditions | Use services/transactions and DB constraints |
| Skipping boundary and defensive-copy tests | Regressions can break invariants | Test boundaries and caller-side mutations |

## 18. Practice Exercises

### Exercise 1 — Value Object for Product Codes

Create `ProductCode`:

- Non-null.
- Strip leading/trailing whitespace.
- Normalize to uppercase using `Locale.ROOT`.
- Allow only ASCII letters, digits, and hyphens.
- Length from 3 to 20.

Write tests for valid input, null, blank, invalid characters, and boundary lengths.

### Exercise 2 — Money

Create `Money` using `BigDecimal`:

- Non-null amount.
- Non-negative amount.
- Non-null currency.
- Define an explicit scale policy.
- Do not round automatically unless required by the contract.

Write tests for zero, positive, negative, and out-of-bounds scale if the domain limits scale.

### Exercise 3 — Defensive Copying

Create a class accepting `List<String>`, `Map<String, String>`, and `byte[]`. Mutate the inputs after constructing the object; verify the object's state does not change. Then mutate the values returned by accessors and verify internal state remains protected.

### Exercise 4 — Cross-Field Invariants

Create `DateRange` or `BookingPeriod`:

- Required start/end.
- End not before start.
- No hidden clock calls in the constructor.
- Write tests for same day, later day, and earlier day.

### Exercise 5 — Constructor Delegation

Create a class with three constructors providing different default configurations. Ensure all paths delegate to a primary constructor and no creation path bypasses validation.

### Exercise 6 — Record Compact Constructor

Convert a simple value object into a record. Normalize components in the compact constructor and defensively copy collections. Explain why records do not automatically make collection components immutable.

### Exercise 7 — Unicode Normalization

Create two `String` values with canonically equivalent Unicode representations. Normalize them to NFC and compare the results. Try NFKC on some compatibility characters and explain why it should not be applied indiscriminately.

### Exercise 8 — Separating Boundary Validation and Invariants

Create a DTO receiving `String` data from a request and convert it to a domain value object. Identify which validations serve user-facing error reporting and which must be enforced in the constructor.

### Exercise 9 — Checking Constructor Anti-Patterns

Write a class whose constructor calls a repository and another that registers `this` before finishing. Refactor so I/O resides in a factory/service and lifecycle registration occurs after the object is constructed.

## 19. Self-Check Questions

1. What is an object invariant?
2. How does validation differ from normalization?
3. Why should a constructor reject invalid states?
4. When should `Objects.requireNonNull` be used?
5. When should `IllegalArgumentException` be used?
6. How do `String.isEmpty()` and `String.isBlank()` differ?
7. Why is `strip()` better suited than `trim()` in many Java 17 cases?
8. Why use `Locale.ROOT` when normalizing technical codes?
9. How do NFC and NFKC differ?
10. Why does Unicode normalization not prevent all confusable identifiers?
11. Why should not all display names be lowercased?
12. Why should `BigDecimal` not be rounded automatically in a constructor unless the contract requires it?
13. What does `List.copyOf` protect, and what does it not protect?
14. Why must arrays be cloned both when received and when returned?
15. How does a defensive copy differ from a deep copy?
16. How does constructor delegation help preserve invariants?
17. When does a record's compact constructor assign component fields?
18. Why should repositories or network calls not happen in a constructor?
19. Why is `this` escape in a constructor dangerous?
20. Why should overridable methods not be called from constructors?
21. Does controller validation replace domain validation?
22. Why do uniqueness checks usually belong in services/databases rather than constructors?
23. Which boundary cases should constructor tests cover?
24. When is a static factory more appropriate than constructor overloading?

## 20. References

- [Java SE 17 API — Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): `requireNonNull` and object utility methods.
- [Java SE 17 API — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `isBlank`, `strip`, `stripLeading`, `stripTrailing`.
- [Java SE 17 API — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): Unicode normalization forms.
- [Java SE 17 API — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): decimal arithmetic, scale, and rounding.
- [Java SE 17 API — List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): `copyOf` and immutable list factories.
- [Java SE 17 API — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): `copyOf` and immutable map factories.
- [Java SE 17 API — Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): `copyOf` and immutable set factories.
- [Java Language Specification, Java SE 17 — Records](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record declarations and canonical/compact constructors.
- [Java SE 17 API — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): locale-independent processing with `Locale.ROOT`.

A constructor is where an object's contract is established. Check for null, normalize data according to domain rules, validate ranges and cross-field conditions, and protect mutable values with defensive copies. Funnel all construction paths through a single clear invariant, keep I/O in the service/factory layer, and write tests for valid data, invalid data, and caller mutations after construction. Once an object is successfully created, its validity conditions must remain intact in Java 17.
