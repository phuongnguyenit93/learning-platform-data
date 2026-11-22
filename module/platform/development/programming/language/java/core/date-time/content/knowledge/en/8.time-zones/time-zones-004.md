# Creating, Validating, and Listing Time Zone IDs in Java

## 1. Learning Objectives

When building a scheduling system, displaying international times, or storing appointments, a program needs to recognize the **time zone** selected by the user. Java provides `java.time.ZoneId` to represent a time zone identifier and `java.time.ZoneOffset` to represent a fixed UTC offset.

After this lesson, you will be able to:

- Create a `ZoneId` using `ZoneId.of(...)`, use `ZoneOffset` when a specific offset is needed, and read the system's default time zone.
- Distinguish between **region IDs with historical/DST rules** such as `Europe/Paris` and **fixed offsets** such as `+07:00`.
- Validate user-entered time zone IDs, distinguishing between syntactically invalid IDs, IDs missing from the data, and unmapped aliases.
- List IDs supported by Java using `ZoneId.getAvailableZoneIds()`, filter, sort, and provide the list for a UI.
- Understand the limitations of ID validation, time zone database (tzdb) versions, and how offsets change by date.

Examples use Java 17+ and the standard `java.time` API. When an example depends on the time zone dataset installed in the JDK, the lesson will clearly note that output may vary depending on the tzdb version.

## 2. Time Zone IDs Are Not Synonymous with UTC Offsets

A time zone ID is an identifier used to look up **rules for applying an offset at a given point in time**, including historical changes and daylight saving time (DST) transitions in regions where it applies.

Examples:

| Value | Type | Meaning |
| --- | --- | --- |
| `Asia/Ho_Chi_Minh` | Region ID | Set of time zone rules for the city/region |
| `Europe/Paris` | Region ID | Time rules in Paris, including seasonal offset changes |
| `America/New_York` | Region ID | Time rules in New York |
| `+07:00` | Fixed offset | Local time is 7 hours ahead of UTC |
| `-05:00` | Fixed offset | Local time is 5 hours behind UTC |
| `Z` or `+00:00` | Zero offset | UTC time, the same zero offset |
| `UTC`, `GMT`, `UT` | Prefix-style IDs | Identifiers for UTC/GMT/UT according to `ZoneId` rules |
| `UTC+07:00` | Prefix-and-offset ID | Based on the +07:00 offset, with no region-based DST rules |

Important distinctions:

- A **region `ZoneId`** can result in **different offsets at different points in time**. For example, Paris in 2024 is `+01:00` in mid-winter and `+02:00` in mid-summer.
- **`ZoneOffset`** is inherently a fixed offset. `+01:00` does not by itself represent the full rules of `Europe/Paris`.
- Two IDs may yield the same offset at one point in time, but they cannot be assumed interchangeable when scheduling in the future or interpreting historical data.
- `LocalDateTime` only holds local date/time fields; by itself it does not know any region ID or offset. Only when a `ZoneId` is attached can it be resolved to a `ZonedDateTime` and a specific `Instant` according to the time zone rules.

IANA IDs typically have the form `Area/Location`, but you should not assume every string containing `/` is a valid ID. The library must have corresponding rules in the time zone data being used.

## 3. Creating a ZoneId with ZoneId.of(...)

The most common way is:

```java
import java.time.ZoneId;

ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneId paris = ZoneId.of("Europe/Paris");
ZoneId newYork = ZoneId.of("America/New_York");
```

This is an **illustrative code snippet** inside a method; `ZoneId.of(String)` returns an immutable value after creation. Retrieve the ID string using `getId()`:

```java
System.out.println(vietnam.getId()); // Asia/Ho_Chi_Minh
System.out.println(paris.getId());   // Europe/Paris
```

Do not guess ID names by replacing spaces or using country names. Cities and region names follow their own historical conventions; you should look them up from the list Java actually supports.

`ZoneId.of(...)` also understands several other ID forms:

```java
ZoneId sevenHours = ZoneId.of("+07:00");
ZoneId utc = ZoneId.of("UTC");
ZoneId utcWithOffset = ZoneId.of("UTC+07:00");
ZoneId gmtWithOffset = ZoneId.of("GMT+7");
ZoneId zeroOffset = ZoneId.of("Z");
```

Normalized IDs when calling `getId()`:

| Input | `getId()` |
| --- | --- |
| `"+07:00"` | `+07:00` |
| `"UTC"` | `UTC` |
| `"UTC+07:00"` | `UTC+07:00` |
| `"GMT+7"` | `GMT+07:00` |
| `"Z"` | `Z` |

The form `GMT+7` is normalized to `GMT+07:00`. Each prefix represents an ID style supported by Java; you should not concatenate strings manually without knowing how offsets are parsed and normalized.

### Using ZoneOffset When the Problem Only Requires an Offset

`ZoneOffset` extends `ZoneId` and represents a fixed offset:

```java
import java.time.ZoneOffset;

ZoneOffset offset = ZoneOffset.of("+07:00");
ZoneOffset byHours = ZoneOffset.ofHours(7);
ZoneOffset utcOffset = ZoneOffset.UTC;
```

This is an illustrative snippet. `offset.equals(byHours)` returns `true`. Offsets must fall within the range allowed by Java (from -18:00 to +18:00, with valid minute/second component constraints).

`ZoneId.of("+07:00")` returns a `ZoneOffset`, whereas `ZoneId.of("UTC+07:00")` preserves the prefixed ID form. You can call `normalized()` to obtain a `ZoneOffset` when the ID's rules are actually a fixed offset:

```java
ZoneId namedFixed = ZoneId.of("UTC+07:00");
ZoneId normalized = namedFixed.normalized();
System.out.println(normalized.getId()); // +07:00
```

This is an illustrative snippet requiring `import java.time.ZoneId;`. For a region with changing offset rules, `normalized()` does not turn it into a single offset representing all points in time.

## 4. Getting the Default Time Zone of the Running Machine

`ZoneId.systemDefault()` returns the default time zone of the system/JVM:

```java
ZoneId defaultZone = ZoneId.systemDefault();
System.out.println(defaultZone.getId());
```

This is an illustrative snippet requiring `import java.time.ZoneId;`. The output **depends on the environment configuration**; it could be `Asia/Ho_Chi_Minh`, `UTC`, or another ID. Do not write tests asserting that the result always belongs to a specific country.

The default time zone can be affected by the runtime environment configuration, operating system, and JVM settings. In containers/cloud environments, a server may run with UTC even when users are in Vietnam.

**Application principle:** If a feature truly needs the "user's time", use a `ZoneId` explicitly selected/stored per user; do not silently read the server's `systemDefault()`. If a feature needs a unified point in time to store events, prefer `Instant`, while also storing the region ID when you need to reconstruct the appointment's meaning in local time.

## 5. Validating a Time Zone ID by Parsing the ID

The API does not have a `ZoneId.isValid("...")` method. The direct way to validate is to attempt creating a `ZoneId` and handle the error:

```java
import java.time.DateTimeException;
import java.time.ZoneId;

public class ZoneIdCheckDemo {
    public static void main(String[] args) {
        check("Asia/Ho_Chi_Minh");
        check("Europe/Paris");
        check("+07:00");
        check("CST");
        check("Mars/Olympus");
        check("UTC+25:00");
    }

    private static void check(String input) {
        try {
            ZoneId zone = ZoneId.of(input);
            System.out.println(input + " -> " + zone.getId());
        } catch (DateTimeException ex) {
            System.out.println(input + " -> INVALID");
        }
    }
}
```

Save the file as `ZoneIdCheckDemo.java`. Run:

```bash
javac ZoneIdCheckDemo.java
java ZoneIdCheckDemo
```

Output on a JDK with standard region data:

```text
Asia/Ho_Chi_Minh -> Asia/Ho_Chi_Minh
Europe/Paris -> Europe/Paris
+07:00 -> +07:00
CST -> INVALID
Mars/Olympus -> INVALID
UTC+25:00 -> INVALID
```

Explanation:

- `Asia/Ho_Chi_Minh` and `Europe/Paris` are valid region IDs in common JDK data.
- `+07:00` is a valid offset even though it is not an `Area/Location` region ID.
- `CST` is an abbreviation that can have multiple meanings, so `ZoneId.of("CST")` is not automatically resolved to a time zone by default.
- `Mars/Olympus` has no rules in standard time zone data.
- `UTC+25:00` has an offset outside the allowed range.

### Exceptions to Know

`ZoneId.of(...)` can throw `DateTimeException` when the string is malformed or the time zone is unsupported. A region ID that looks structurally valid but is not present in the data typically throws `java.time.zone.ZoneRulesException`, which is a subclass of `DateTimeException`. `null` throws `NullPointerException`.

Do not catch only `ZoneRulesException`, because syntax/offset errors can throw other `DateTimeException` instances. When validating a string parameter that has already been checked for non-null, catching `DateTimeException` generally covers user-entered time zone errors.

In a REST/UI application, error handling should return a message such as "invalid or unsupported time zone ID", rather than silently falling back to UTC and continuing to process the appointment.

## 6. Checking "In the Region List" vs. "Accepted by ZoneId.of"

`ZoneId.getAvailableZoneIds()` returns the set of region IDs known to the time zone rule providers of the current Java environment. However, `ZoneId.of(...)` also handles **fixed offsets** and **prefixed IDs** such as `UTC+07:00`.

Therefore, these are two **different** questions:

1. **Can this ID be parsed and used by Java?** → try `ZoneId.of(input)` and handle exceptions.
2. **Is this ID in the list of provided regions?** → `ZoneId.getAvailableZoneIds().contains(input)`.

For example, `ZoneId.of("+07:00")` succeeds, even though that string is not a region ID in the set returned by `getAvailableZoneIds()`. If the UI only allows selecting a region ID to represent local calendar rules, you should use the region list. If an API intentionally accepts **fixed offsets as well**, checking only against the region set is too restrictive.

A custom regex "syntax check" is also insufficient: regex cannot verify whether a region exists in tzdb or whether the system has rules for that region.

## 7. Listing Available Time Zone IDs

Method:

```java
Set<String> availableIds = ZoneId.getAvailableZoneIds();
```

This is an illustrative snippet requiring `import java.time.ZoneId;` and `import java.util.Set;`.

Characteristics:

- Returns a `Set<String>` containing the available region IDs from time zone providers.
- **No iteration order is guaranteed**; do not print the set directly and snapshot its exact output as fixed data.
- The count/set of IDs may vary depending on the JDK version, tzdb dataset, and providers.
- It does not automatically include every alias, abbreviation, offset ID, or prefixed ID that `ZoneId.of(...)` can accept.
- The returned set can be filtered and converted to a list to build a user-facing picker.

To display consistently by name, **sort** it:

```java
List<String> sortedIds = ZoneId.getAvailableZoneIds()
        .stream()
        .sorted()
        .toList();
```

This is an illustrative snippet with `import java.time.ZoneId;` and `import java.util.List;`. `Stream.toList()` was introduced in Java 16+, so it works in Java 17+; the resulting list is unmodifiable.

### Filtering by Region

When you only want IDs starting with `Asia/`:

```java
List<String> asiaIds = ZoneId.getAvailableZoneIds()
        .stream()
        .filter(id -> id.startsWith("Asia/"))
        .sorted()
        .toList();
```

This is an illustrative snippet with the corresponding imports. An ID prefixed with `Asia/` does not mean it necessarily belongs to a specific country; it is simply an ID organization convention.

You can search substrings by keyword:

```java
String keyword = "Ho_Chi_Minh";
List<String> matches = ZoneId.getAvailableZoneIds()
        .stream()
        .filter(id -> id.contains(keyword))
        .sorted()
        .toList();
```

This is an illustrative snippet. Substring matching is useful for simple lookup features, but ID names are **technical identifiers**, not full localized display names. In a real UI, you should support searching by city name, region name, and appropriate localized labels.

## 8. Complete Program: Creating, Filtering, and Listing in Order

Save the file **`ZoneIdCatalogDemo.java`**:

```java
import java.time.DateTimeException;
import java.time.ZoneId;
import java.util.List;
import java.util.Set;

public class ZoneIdCatalogDemo {
    public static void main(String[] args) {
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId paris = ZoneId.of("Europe/Paris");
        ZoneId fixed = ZoneId.of("+07:00");

        System.out.println("vietnam = " + vietnam.getId());
        System.out.println("paris = " + paris.getId());
        System.out.println("fixed = " + fixed.getId());

        Set<String> all = ZoneId.getAvailableZoneIds();
        System.out.println("hasVietnam = "
                + all.contains("Asia/Ho_Chi_Minh"));

        List<String> selected = all.stream()
                .filter(id -> id.equals("Asia/Ho_Chi_Minh")
                        || id.equals("Europe/Paris"))
                .sorted()
                .toList();
        System.out.println("selected = " + selected);

        for (String candidate : List.of(
                "Asia/Ho_Chi_Minh", "+07:00", "Mars/Olympus")) {
            try {
                System.out.println("valid = "
                        + ZoneId.of(candidate).getId());
            } catch (DateTimeException ex) {
                System.out.println("invalid = " + candidate);
            }
        }
    }
}
```

Compile and run:

```bash
javac ZoneIdCatalogDemo.java
java ZoneIdCatalogDemo
```

Deterministic output on a JDK with a standard set of region IDs including the two regions in the example:

```text
vietnam = Asia/Ho_Chi_Minh
paris = Europe/Paris
fixed = +07:00
hasVietnam = true
selected = [Asia/Ho_Chi_Minh, Europe/Paris]
valid = Asia/Ho_Chi_Minh
valid = +07:00
invalid = Mars/Olympus
```

Key takeaways:

1. Region IDs and offsets are created with the same `ZoneId.of(...)` API, but their semantics differ.
2. Checking `contains(...)` applies to the list of **region IDs**.
3. When printing the list, call `sorted()` so you do not rely on the iteration order of a `Set`.
4. Use `try/catch` when parsing user-supplied strings.
5. Do not assert the exact count of `getAvailableZoneIds()` in a test that runs across multiple tzdb versions.

## 9. Abbreviations and the ZoneId.SHORT_IDS Map

Abbreviations like `CST`, `IST`, `EST`, and `PST` can be ambiguous or carry different historical meanings depending on location. For example, "CST" can be interpreted differently in several regions around the world.

Java provides the `ZoneId.SHORT_IDS` map to support some legacy abbreviations when **explicitly requested**:

```java
ZoneId legacy = ZoneId.of("PST", ZoneId.SHORT_IDS);
System.out.println(legacy.getId());
// America/Los_Angeles
```

This is an illustrative snippet requiring `import java.time.ZoneId;`. `ZoneId.of("PST")` does not automatically use the `SHORT_IDS` map. This map is a Java-defined mapping, not a system for resolving every abbreviation across all countries and eras.

**Recommendation:** When designing new data, accept/store full region IDs like `America/Los_Angeles` or explicitly specified offsets. Only use `SHORT_IDS` for compatibility with legacy data whose meaning you know clearly and want to map specifically. Do not rely on abbreviations to guess a user's region.

## 10. Inspecting the Offset Rules of an ID

Once you have a `ZoneId`, use `zone.getRules()` to inspect the time zone rules via `java.time.zone.ZoneRules`. Offsets depend on the **point in time**; use an `Instant` when asking "what is the offset on that date?".

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

ZoneId paris = ZoneId.of("Europe/Paris");
ZoneOffset winter = paris.getRules().getOffset(
        Instant.parse("2024-01-15T12:00:00Z"));
ZoneOffset summer = paris.getRules().getOffset(
        Instant.parse("2024-07-15T12:00:00Z"));

System.out.println(winter); // +01:00
System.out.println(summer); // +02:00
```

This is an illustrative snippet inside a method; the two results are based on tzdb data containing Paris's historical rules for 2024. The offset change demonstrates why **a region `ZoneId` cannot be replaced by a fixed offset** for all dates.

Common rule inspection operations:

- `zone.getRules().isFixedOffset()`: whether the rules have a fixed offset (never changing over time).
- `zone.getRules().getOffset(instant)`: the offset in effect at a specific `Instant`.
- `zone.getRules().isDaylightSavings(instant)`: whether the point in time falls within a period considered DST by the rules.
- `zone.getRules().getValidOffsets(localDateTime)`: the list of valid offsets for a `LocalDateTime` label; may be empty during a DST gap or contain two elements during an overlap.

Do not fetch the offset at `Instant.now()` and treat it as a fixed offset for a meeting next year. A region's DST policy may produce a different result, and time zone laws can also be changed by governments in the future.

### Complete Example: Comparing a Region and an Offset

Save the file **`ZoneRulesDemo.java`**:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class ZoneRulesDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        ZoneOffset fixed = ZoneOffset.ofHours(1);

        Instant winter = Instant.parse("2024-01-15T12:00:00Z");
        Instant summer = Instant.parse("2024-07-15T12:00:00Z");

        System.out.println("Paris winter = "
                + paris.getRules().getOffset(winter));
        System.out.println("Paris summer = "
                + paris.getRules().getOffset(summer));
        System.out.println("Fixed winter = "
                + fixed.getRules().getOffset(winter));
        System.out.println("Fixed summer = "
                + fixed.getRules().getOffset(summer));
        System.out.println("Fixed isFixedOffset = "
                + fixed.getRules().isFixedOffset());
    }
}
```

Run:

```bash
javac ZoneRulesDemo.java
java ZoneRulesDemo
```

Output with 2024 Paris rules:

```text
Paris winter = +01:00
Paris summer = +02:00
Fixed winter = +01:00
Fixed summer = +01:00
Fixed isFixedOffset = true
```

**Interpretation:** Both may share the same offset in January, but in July Paris shifts to +02:00 while the fixed offset remains +01:00. Therefore, **checking whether an ID exists** is a different step from **confirming that the ID satisfies the business semantics you need to store**.

## 11. Using ZoneId in Appointments and Date-Time Conversions

If someone chooses the local date-time `2024-07-15 09:00` and the region `Europe/Paris`, you can combine them:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.Instant;

LocalDateTime local = LocalDateTime.of(2024, 7, 15, 9, 0);
ZoneId zone = ZoneId.of("Europe/Paris");

ZonedDateTime zoned = local.atZone(zone);
Instant instant = zoned.toInstant();

System.out.println(zoned);
// 2024-07-15T09:00+02:00[Europe/Paris]

System.out.println(instant);
// 2024-07-15T07:00:00Z
```

This is an illustrative snippet inside a method. `local.atZone(zone)` applies the region's offset rules at the selected date and time. Appointments may need to store the **local date-time** (the time the user selected), the **region ID**, and/or the **Instant** (absolute point in time) depending on the storage contract and policy for future rule updates.

**DST gap/overlap:** Some local time values may not exist or may have two valid offsets. The default behavior of `atZone(...)` handles this according to Java's rules; for financial/booking domains with special requirements, you need to explicitly detect and handle those cases rather than assuming a date-time label always maps uniquely.

## 12. Building a Time Zone Picker List for Users

A minimal picker can be based on Java's set of region IDs:

```java
import java.time.ZoneId;
import java.util.List;

public class ZonePickerDemo {
    public static void main(String[] args) {
        List<String> ids = ZoneId.getAvailableZoneIds()
                .stream()
                .sorted()
                .toList();

        List<String> selected = ids.stream()
                .filter(id -> id.startsWith("Asia/"))
                .filter(id -> id.contains("Ho_Chi_Minh")
                        || id.contains("Tokyo"))
                .toList();

        System.out.println("selected = " + selected);
    }
}
```

Save the file as `ZonePickerDemo.java`. Compile and run:

```bash
javac ZonePickerDemo.java
java ZonePickerDemo
```

Output on a JDK containing these two region IDs:

```text
selected = [Asia/Ho_Chi_Minh, Asia/Tokyo]
```

This is only an example **filtering two IDs to demonstrate the operation**. A real picker should search across the full list; it can display user-friendly labels such as "Ho Chi Minh" or "Tokyo", but **the value sent to the API should be an ID with clear rules**, not a UI label.

You can use:

```java
String label = ZoneId.of("Europe/Paris").getDisplayName(
        java.time.format.TextStyle.FULL,
        java.util.Locale.forLanguageTag("vi-VN"));
```

This is an illustrative snippet inside a method. Localized label output can depend on the JDK's locale data; do not write tests asserting a fixed display string across all environments. Do not use translated labels as storage identifiers.

### Process for Validating a Value Submitted from a Picker

1. Accept the ID string with a reasonable length limit and reject null/empty cases according to your contract.
2. If only **region IDs** are allowed, check against the valid region list published by the server.
3. If **offsets** are also allowed, use `ZoneId.of(...)` to validate according to Java syntax/semantics.
4. Apply business policies: do you allow regions outside your active list, regions without DST support, or only specific supported regions?
5. Store the **normalized ID** from `getId()` or a clearly defined mapping rule; do not guess from abbreviation characters.

The ID set on the frontend may differ from the backend if the two environments have different tzdb updates. The backend must still validate independently instead of trusting that every value sent from the UI is valid.

## 13. Why the ID List Can Differ Across JDKs

Region IDs and offset transitions are looked up from the **timezone database (tzdb)** and the providers used by the Java environment. The time zone data version is updated when laws or transition schedules change.

Consequences:

- New IDs may appear after updating the JDK/tzdb.
- Some aliases/region names may differ or be handled according to compatibility rules.
- The same region ID may have **updated future rules** when a government changes DST; the ID remains valid, but the offset for a future date may differ from before.
- Do not hardcode the element count of `ZoneId.getAvailableZoneIds()` as a system-wide constant.
- Do not rely on the direct iteration order of the `Set`; sort explicitly when displaying or exporting data.

If you need to diagnose rule versions, Java provides the `java.time.zone.ZoneRulesProvider.getVersions(zoneId)` API for eligible region IDs. It returns a mapping of version → `ZoneRules`; specific version names depend on the provider, so avoid assuming a fixed version number in documentation or tests.

For systems involving future appointments, you need a strategy for updating JDK/tzdb and testing with regions that have DST rules, rather than "locking in" an offset at the time data is created.

## 14. Common Pitfalls

### Using Abbreviations as Primary Identifiers

`CST` or `IST` do not carry a single global meaning. Require an explicit region ID, or an offset if the business logic truly only needs an offset. `ZoneId.SHORT_IDS` is a bridge for legacy data, not a way to guess every abbreviation.

### Treating +07:00 as Equivalent to All of Asia/Ho_Chi_Minh

Both values may share the same current offset, but the region ID carries historical rules and may be updated in the future. If you need to represent a local schedule, keep the region ID.

### Assuming getAvailableZoneIds() Lists Every Valid ZoneId.of(...)

The set of region IDs is not the entire space of offsets. `ZoneId.of("+07:00")` is accepted by Java even though it is not a region name in the returned IDs set.

### Using "Now"'s Offset for Another Date

`zone.getRules().getOffset(Instant.now())` only reflects the offset at the moment of inspection. A meeting on another date requires looking up the offset on that date with the appropriate DST/zone rules.

### Forgetting That the Server's Default Zone Differs from the User's Zone

Using `ZoneId.systemDefault()` arbitrarily causes the same application to return different results across laptops, containers, and production. Only use the system default when that is genuinely the intent. In business APIs, pass `ZoneId` explicitly.

### Using Regex Instead of Rule Validation

A string shaped like `Region/City` is not guaranteed to exist. Rely on the actual provider via `ZoneId.of(...)`, then check your application's allowlist if needed.

### Forgetting Sign-Inverted GMT Names

Some historical IDs in the `Etc/GMT±N` family follow the POSIX sign convention, which can be **the opposite of ISO-8601 offset interpretation**. For example, `Etc/GMT+7` corresponds to offset `-07:00` in common tzdb data. Do not construct offsets by concatenating `Etc/GMT` and an hour number; if you only need an offset, using `ZoneOffset.of("+07:00")` is clearer.

## 15. Practice Exercises

**Question 1.** When should you use `ZoneId.of("Europe/Paris")`, and when should you use `ZoneOffset.of("+01:00")`?

**Answer:** Use the Paris region when you need date/historical offset rules and DST. Use the +01:00 offset when the contract requires a fixed 1-hour offset independent of region rules.

**Question 2.** Is `ZoneId.getAvailableZoneIds().contains("+07:00")` a way to confirm every string that works with `ZoneId.of(...)`?

**Answer:** No. `+07:00` is a valid offset; the available zone IDs list is primarily for region IDs. Attempt to parse when you want to support offsets as well.

**Question 3.** Why should you not print `ZoneId.getAvailableZoneIds()` and expect a fixed order?

**Answer:** The result is a `Set` with no guaranteed iteration order. Use `stream().sorted().toList()` when a stable order is needed.

**Question 4.** Is the string `CST` a unique region ID?

**Answer:** No. It is an ambiguous abbreviation; `ZoneId.of("CST")` does not automatically use the `SHORT_IDS` mapping. Choose a full region ID.

**Question 5.** Paris can be `+01:00` in winter and `+02:00` in summer. Which API should you call to query the offset at an instant?

**Answer:** `ZoneId.of("Europe/Paris").getRules().getOffset(instant)` with an explicit `Instant`.

**Question 6.** A user in Vietnam selects "09:00 on 2024-07-15 in Paris". Is storing the string `"2024-07-15T09:00"` enough to know the instant?

**Answer:** Not yet. You need the appropriate time zone/offset, such as the region ID `Europe/Paris`; then `09:00` on that day corresponds to `07:00Z` under 2024 Paris rules.

**Question 7.** What should an API do when it receives the ID `Mars/Olympus`?

**Answer:** Catch `DateTimeException` when trying `ZoneId.of(...)` and return an invalid/unsupported ID message. Do not silently replace it with another time zone that corrupts the user's schedule.

## 16. Implementation Checklist

- Use `ZoneId.of(id)` to parse region IDs and other valid IDs; catch input errors.
- Use `ZoneOffset.of(...)` when you truly want a **fixed UTC offset**.
- Use `ZoneId.getAvailableZoneIds()` to build a **region** list; sort and filter before presenting it in a UI.
- Always distinguish **region identifier**, **offset at an instant**, and **local date-time label**.
- Avoid shortening IDs to abbreviations; check DST/tzdb data when scheduling on other dates.
- Update time zone data as needed; do not hardcode the ID count or a region's offset for all points in time.
- When receiving values from a UI/API, validate against application policy and provide clear error messages.

**Remember:** A region time zone ID like `Europe/Paris` represents **the time rules of a region**, whereas `+07:00` is only a **fixed offset**. Create and validate via `ZoneId.of(...)`; list region IDs with `ZoneId.getAvailableZoneIds()`; always look up the offset at a specific point in time when exact dates and times matter.