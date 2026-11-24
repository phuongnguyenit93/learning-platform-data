# Distinguishing Time Zone, UTC Offset, and Locale in Spring Framework

## 1. Objectives and real-world scenario

A Spring application receives a booking request: **9:00 AM on July 1, 2026**. The critical question is not only whether the date-time string is formatted properly, but also **where it is 9:00 AM** and **how the user wants to see it**.

There are three independent concepts:

1. **Time zone**: rules for converting between an actual instant and local time in a region, typically represented by `ZoneId` such as `Asia/Ho_Chi_Minh`, `America/New_York`.
2. **UTC offset**: the amount of time added to or subtracted from UTC at a given instant, represented by `ZoneOffset` such as `+07:00`, `-04:00`.
3. **Locale**: language/region conventions used to display or parse strings, represented by `Locale` such as `vi-VN`, `en-US`, `fr-FR`.

They answer three different questions:

- **ZoneId:** Which location's time rules apply?
- **ZoneOffset:** At this instant, how far is that region from UTC?
- **Locale:** Under which conventions are dates, months, weekday names, digits, and messages displayed/interpreted?

For example, the same instant `2026-07-01T12:00:00Z` (UTC):

| Context | Local time at that instant | UTC offset |
| --- | --- | --- |
| `Asia/Ho_Chi_Minh` | 19:00 on 01/07/2026 | `+07:00` |
| `America/New_York` | 08:00 on 01/07/2026 | `-04:00` |
| UTC | 12:00 on 01/07/2026 | `+00:00` |

Changing `Locale.US` to `Locale.FRANCE` **does not change** the instant or New York's UTC offset; it can only change the textual representation. Conversely, changing `ZoneId` from Vietnam to New York **changes the wall-clock time** displayed for the same `Instant`, without changing the instant itself.

## 2. UTC, ZoneOffset, ZoneId, and Locale: comparison table

| Term | Related Java type | What does it contain? | What does it NOT contain? | Example |
| --- | --- | --- | --- | --- |
| UTC | Time reference standard | Reference scale with zero offset | Language, presentation format | `2026-07-01T12:00:00Z` |
| UTC offset | `ZoneOffset` | Fixed difference from UTC | History/rules for time changes in a region | `+07:00`, `-05:00` |
| Region time zone | `ZoneId` | Region ID and historical/future rules from tzdb | User's locale | `Europe/Paris` |
| Locale | `java.util.Locale` | Language, region, text/number/date conventions | Time zone or UTC offset | `vi-VN`, `en-US` |
| Instant | `java.time.Instant` | A point on the timeline | Original time zone or locale of input | `2026-07-01T12:00:00Z` |

**UTC is neither synonymous with Locale nor a geographic place.** The letter `Z` in ISO-8601 strings represents zero offset (`Zulu`/UTC); `+07:00` indicates local time seven hours ahead of UTC, while `-04:00` is four hours behind UTC. `+07:00` is an offset; it does not by itself say "Vietnam".

**`ZoneOffset` is a fixed form of `ZoneId`** in the `java.time` API, yet it carries no daylight saving time (DST) rules. `ZoneId.of("Asia/Ho_Chi_Minh")` is a region ID; `ZoneOffset.of("+07:00")` is only an offset. They may yield the same clock time at a modern instant yet differ in representation data and ability to handle historical changes.

**Locale does not imply time zone.** A user choosing Vietnamese (`vi-VN`) may live in New York; an `en-US` user may be in Ho Chi Minh City. Never infer `Locale` → `ZoneId` without an explicit business policy and user-provided location data.

## 3. A time zone is a set of rules; an offset is the result at an instant

The `America/New_York` zone can have two different offsets in 2026:

- January 2026: UTC`-05:00` (standard time).
- July 2026: UTC`-04:00` (daylight saving time).

Therefore, never say **"New York's time zone is always UTC-5"**. More accurately: "New York's offset at a specific `Instant` is computed from the rules of its `ZoneId`".

In Java:

```java
ZoneId zone = ZoneId.of("America/New_York");
Instant instant = Instant.parse("2026-07-01T12:00:00Z");
ZoneOffset offset = zone.getRules().getOffset(instant); // -04:00
```

This is an API illustration snippet, not a standalone program; imports from `java.time` are required. The `getOffset(instant)` method takes a resolved instant and therefore returns **one** result. For a local time without an offset, the answer can have 0, 1, or 2 results on DST transition days.

The system uses time zone rule data (tzdb/IANA), which may be updated when countries change their laws. Do not hard-code regions as fixed offsets, especially for future schedules.

### 3.1. Nonexistent and repeated hours during DST

In New York in 2026, under current time zone rules:

- **Gap:** `2026-03-08 02:30` is a nonexistent local time because clocks jump from around 02:00 to 03:00. `getValidOffsets(local)` returns an empty list.
- **Overlap:** `2026-11-01 01:30` occurs twice when clocks fall back; that hour has two valid offsets: `-04:00` and `-05:00`.
- Normal times have exactly one valid offset.

To check:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime requested = LocalDateTime.of(2026, 11, 1, 1, 30);
List<ZoneOffset> offsets = ny.getRules().getValidOffsets(requested);
System.out.println(offsets); // [-04:00, -05:00] with current tzdb
```

This snippet requires `java.time.*` and `java.util.List` imports.

**`LocalDateTime.atZone(zone)` is not a validator guaranteeing "this local time definitely exists".** By default, the API handles gaps by shifting the time past the gap and handles overlaps by picking a preferred offset. For ticketing, scheduled transfers, or time-sensitive transactions, do not silently accept that automatic adjustment.

A clearer policy:

1. No valid offset → ask the user to re-enter the time.
2. One valid offset → convert to `Instant`.
3. Two valid offsets → ask the user to choose the offset/occurrence, or apply a pre-published business rule.

Once an offset is chosen, you can use `ZonedDateTime.ofStrict(localDateTime, chosenOffset, zone)` to ensure the offset is genuinely valid for that zone and local time. When distinguishing the two occurrences of `01:30`, a string containing only `LocalDateTime` is insufficient.

## 4. Choosing the right `java.time` type before formatting or binding

| Type | What information does it carry? | When to use? |
| --- | --- | --- |
| `LocalDate` | Calendar date, no time/zone | Birth dates, effective dates independent of location |
| `LocalTime` | Wall-clock time, no date/zone | Opening hours like 09:00 local time |
| `LocalDateTime` | Local date and time, no offset/zone yet | User-entered appointment time before resolving the zone |
| `Instant` | Unique point in time on the timeline | Finalized timestamps, logs, transaction times |
| `OffsetDateTime` | Date/time with a specific offset | APIs sending instants with an offset, without needing zone rules |
| `ZonedDateTime` | Date/time, resolved offset, and `ZoneId` | Retaining both the instant and zone context |
| `ZoneId` | Region ID/offset rules | Recurring schedules in local time |
| `ZoneOffset` | Fixed difference from UTC | Recording the actual offset chosen at an instant |

Two representations can refer to the same `Instant`:

```text
2026-07-01T12:00:00Z
2026-07-01T19:00:00+07:00
2026-07-01T08:00:00-04:00
```

Meanwhile, `2026-07-01T19:00:00` **has no offset or zone**, so it does not yet identify an `Instant`.

To be clear when switching zones:

- `withZoneSameInstant(otherZone)`: preserves the instant, changes the displayed local time.
- `withZoneSameLocal(otherZone)`: tries to keep the wall-clock date/time, so it usually **changes the actual instant**; you must also handle gap/overlap rules of the target zone.

For example, a finalized meeting schedule uses `sameInstant` so participants elsewhere see the exact same moment. Scheduling store openings at 09:00 local time in another city is a `sameLocal` problem, requiring clear business rules.

For a **daily recurring schedule at 09:00 Paris time**, store `LocalTime`/recurrence rule and `Europe/Paris`. Storing only a fixed `+01:00` offset will shift the schedule by one hour when Paris switches to `+02:00`. For a finalized one-off event, store `Instant`, and if you need to reconstruct why that time was chosen, also store `ZoneId` and the chosen offset info.

## 5. Locale only controls how representations are displayed/parsed

A `Locale` typically specifies language, region, and cultural conventions; for example:

- `Locale.forLanguageTag("vi-VN")`: Vietnamese for Vietnam.
- `Locale.US`: English for the United States.
- `Locale.FRANCE`: French for France.

Locale affects month names, weekday names, day/month/year order in localized formats, message languages, and number or currency formats. It **does not turn an `Instant` into Hanoi/Paris time** unless you specify a `ZoneId`.

In `java.time.format.DateTimeFormatter`, the two settings are separate:

```java
Instant instant = Instant.parse("2026-07-01T12:00:00Z");
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("dd MMM uuuu HH:mm XXX", Locale.ENGLISH)
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
String display = formatter.format(instant);
```

`withZone(...)` chooses how to view `Instant` in a zone; `Locale.ENGLISH` determines the formatting of month name `MMM`. Changing the locale while keeping the zone leaves the local clock time and offset unchanged.

Tokens to remember:

| Pattern | Meaning | Notes |
| --- | --- | --- |
| `uuuu` | ISO/proleptic calendar year | Usually preferable to `YYYY` for calendar years |
| `MM` / `mm` | Month / minute | Case-sensitive |
| `dd` / `HH` | Day of month / hour 0–23 | Pair with appropriate date/time fields |
| `XXX` | ISO-style offset like `+07:00` | Offset only, contains no zone ID |
| `VV` | `ZoneId` | Can print `Asia/Ho_Chi_Minh` |
| `z` | Localized time zone name | Abbreviations like EST/CST can be ambiguous |
| `MMM` / `EEEE` | Abbreviated month / day of week | Depends on locale and JDK data |

Do not fabricate UTC ISO strings by appending `Z` to a local time string. Only use `Z` when the value truly represents UTC/zero offset. For system-to-system APIs, prefer ISO-8601/RFC 3339 with an explicit offset or UTC `Instant` format; UI data can be localized separately.

Using `DateTimeFormatter.ofLocalizedDate(...)` is convenient for UIs, but the exact string can vary across JDK/locale data. If an API contract requires an invariant format, specify an explicit pattern or ISO formatter rather than relying on environment-dependent `FormatStyle.SHORT`.

## 6. Standalone Java 17+ example: same Instant, multiple zones and Locales

This is a complete Java program requiring no Spring to understand the core concepts. The output below was verified under current time zone rules; tzdb data in another JDK may differ for regions/years whose laws changed.

Create file **`TimeZoneLocaleDemo.java`**:

```java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class TimeZoneLocaleDemo {
    static String displayDate(LocalDate value, Locale locale) {
        String pattern = locale.equals(Locale.FRANCE)
                ? "dd/MM/uuuu" : "MM/dd/uuuu";
        return value.format(DateTimeFormatter.ofPattern(pattern, locale));
    }

    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-07-01T12:00:00Z");
        ZoneId vietNam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId newYork = ZoneId.of("America/New_York");

        ZonedDateTime vnTime = instant.atZone(vietNam);
        ZonedDateTime nyTime = instant.atZone(newYork);
        System.out.println("instant=" + instant);
        System.out.println("vietnam=" + vnTime);
        System.out.println("nySummer=" + nyTime);
        System.out.println("nyWinter="
                + Instant.parse("2026-01-01T12:00:00Z").atZone(newYork));
        System.out.println("zoneId=" + vnTime.getZone());
        System.out.println("offset=" + vnTime.getOffset());
        System.out.println("offsetOnly=" + vnTime.toOffsetDateTime());
        System.out.println("sameInstant=" + vnTime.withZoneSameInstant(newYork));
        System.out.println("sameLocal=" + vnTime.withZoneSameLocal(newYork));
        LocalDate date = LocalDate.of(2026, 12, 31);
        System.out.println("localeUS=" + displayDate(date, Locale.US));
        System.out.println("localeFR=" + displayDate(date, Locale.FRANCE));
        LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);
        System.out.println("gapValidOffsets="
                + newYork.getRules().getValidOffsets(gap).size());
        System.out.println("overlapValidOffsets="
                + newYork.getRules().getValidOffsets(overlap).size());
    }
}
```

Run from the directory containing the file with JDK 17 or newer:

```bash
javac -encoding UTF-8 TimeZoneLocaleDemo.java
java TimeZoneLocaleDemo
```

Stdout output:

```text
instant=2026-07-01T12:00:00Z
vietnam=2026-07-01T19:00+07:00[Asia/Ho_Chi_Minh]
nySummer=2026-07-01T08:00-04:00[America/New_York]
nyWinter=2026-01-01T07:00-05:00[America/New_York]
zoneId=Asia/Ho_Chi_Minh
offset=+07:00
offsetOnly=2026-07-01T19:00+07:00
sameInstant=2026-07-01T08:00-04:00[America/New_York]
sameLocal=2026-07-01T19:00-04:00[America/New_York]
localeUS=12/31/2026
localeFR=31/12/2026
gapValidOffsets=0
overlapValidOffsets=2
```

Interpreting the results:

- `vietnam` and `nySummer` show two views of the same `instant`.
- `nyWinter` and `nySummer` have different offsets despite sharing `ZoneId` New York.
- `offsetOnly` retains `+07:00` but drops the `Asia/Ho_Chi_Minh` ID.
- `sameInstant` keeps `12:00Z`, whereas `sameLocal` keeps the digits 19:00 and shifts to a different instant.
- `localeUS` and `localeFR` represent the same `LocalDate` in two different orders. The example explicitly picks patterns based on locale for stable stdout; it does not assert that all US/French systems always use these exact patterns.
- `gapValidOffsets=0` and `overlapValidOffsets=2` illustrate why DST must be checked when accepting appointments in local time.

## 7. Connecting to Spring MVC: data binding, formatters, and request context

At the web layer, Spring usually receives strings from forms, query parameters, or path variables and converts them to `@ModelAttribute` property types/controller parameters via `WebDataBinder`, `ConversionService`, and the `Formatter` mechanism. These steps have distinct responsibilities:

1. **Binding:** mapping parameter `localStart=2026-07-01T19:00:00` into `LocalDateTime`.
2. **Parsing/formatting:** reading or printing strings according to configured `@DateTimeFormat`/`Formatter` and `Locale`.
3. **Resolving the instant:** combining `LocalDateTime` with an application-known `ZoneId` and valid offset rules.
4. **Business validation:** detecting nonexistent/repeated times, past dates, or out-of-hours bookings.
5. **Storage/display:** storing `Instant` or an appropriate schedule model, and using the viewer's zone + locale when displaying.

**`@DateTimeFormat` does not infer a time zone from `Locale`.** If the data only has `LocalDateTime`, the formatter can parse it into a local date-time, yet it still lacks enough information to produce an `Instant`.

Example form model for a meeting:

```java
import java.time.LocalDateTime;
import org.springframework.format.annotation.DateTimeFormat;

public class ScheduleForm {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
    private LocalDateTime localStart;
    private String zoneId;

    public LocalDateTime getLocalStart() { return localStart; }
    public void setLocalStart(LocalDateTime localStart) {
        this.localStart = localStart;
    }

    public String getZoneId() { return zoneId; }
    public void setZoneId(String zoneId) { this.zoneId = zoneId; }
}
```

Sample form values:

```text
localStart=2026-07-01T19:00:00
zoneId=Asia/Ho_Chi_Minh
```

Without `zoneId`, the `localStart` string alone gives the backend **insufficient data** to assert the meeting takes place at `12:00Z`.

### 7.1. Safely handling local date-time when creating schedules

The snippet below is **integration code in a Spring MVC/Spring Boot project with Web MVC**; it uses the `ScheduleForm` class above. It is not a standalone program runnable with section 6's `java` command.

```java
import java.time.*;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.*;

@RestController
public class ScheduleController {
    @PostMapping("/schedules")
    public ResponseEntity<String> create(
            @ModelAttribute ScheduleForm form,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()
                || form.getLocalStart() == null
                || form.getZoneId() == null) {
            return ResponseEntity.badRequest().body("Invalid form data");
        }

        final ZoneId zone;
        try {
            zone = ZoneId.of(form.getZoneId());
        } catch (DateTimeException ex) {
            return ResponseEntity.badRequest().body("Invalid zone ID");
        }

        LocalDateTime local = form.getLocalStart();
        List<ZoneOffset> validOffsets = zone.getRules().getValidOffsets(local);

        if (validOffsets.size() != 1) {
            return ResponseEntity.badRequest()
                    .body("Local time is missing or ambiguous in this zone");
        }

        Instant confirmed = ZonedDateTime
                .ofStrict(local, validOffsets.get(0), zone)
                .toInstant();

        return ResponseEntity.ok(confirmed.toString());
    }
}
```

With the sample form above, the response body will be `2026-07-01T12:00:00Z`. The controller intentionally rejects gaps/overlaps so the user can reconfirm; an application could support selecting a specific offset for repeated hours. In production, also add authorization checks for schedule creation, business rules, and error handling matching your API contract.

Key point: `BindingResult` sits immediately after the `@ModelAttribute` parameter so Spring MVC reports field conversion errors before the controller makes business decisions. `ZoneId.of(...)` validates the region ID (do not rely on `TimeZone.getTimeZone(...)`, as that legacy API silently returns GMT for invalid IDs).

### 7.2. Where does Spring get the request's Locale and time zone?

In Spring MVC (Servlet stack), `LocaleResolver` determines the request's `Locale`. A `LocaleContextResolver` can additionally supply `TimeZone` information. Common sources:

- The `Accept-Language` header can suggest a `Locale`, **not determine the browser's time zone**.
- Cookies/sessions/profiles/UI settings may hold a user-selected locale or time zone, depending on application strategy.
- `LocaleContextHolder` holds thread-bound locale context during synchronous request processing—e.g. `LocaleContextHolder.getLocale()` and `LocaleContextHolder.getTimeZone()`. The time zone value may be a default when the resolver supplies no dedicated time zone.

Illustrative code reading the context:

```java
import java.time.ZoneId;
import java.util.Locale;
import java.util.TimeZone;
import org.springframework.context.i18n.LocaleContextHolder;

Locale locale = LocaleContextHolder.getLocale();
TimeZone timeZone = LocaleContextHolder.getTimeZone();
ZoneId presentationZone = timeZone.toZoneId();
```

This snippet is for code running inside a Spring context with appropriate locale/time zone setup. It does not prove `presentationZone` is the user-chosen time zone. For scheduling logic requiring exact regions, read and validate `ZoneId` from profiles/parameters rather than silently falling back to the server's default time zone.

For async flows, queues, schedulers, or custom threads, do not assume `LocaleContextHolder` propagates automatically. Pass `Locale`/`ZoneId` explicitly as business data or job configuration; avoid relying on thread-locals across thread boundaries.

### 7.3. Separating form binding from JSON bodies

- `@ModelAttribute`, form/query fields, and `@DateTimeFormat`/Spring `FormattingConversionService` belong to the MVC binding/formatting pipeline.
- JSON `@RequestBody` is handled by `HttpMessageConverter`, typically via Jackson. `@DateTimeFormat` annotations do not automatically replace JSON Java Time serializer/deserializer configuration.
- `@JsonFormat` (Jackson) and `@DateTimeFormat` (Spring) address two different processing pipelines; use whichever matches the input protocol.
- An API accepting `"2026-07-01T19:00:00+07:00"` has enough offset info to resolve an instant, yet still lacks region time zone rules for a recurring future appointment.

With ISO-8601, accepting `OffsetDateTime` or `Instant` avoids much ambiguity when an API transmits **a known instant**. When users enter **an appointment time in a locality**, you need `LocalDateTime` + `ZoneId` and explicit DST handling.

### 7.4. Cautions with Date and default time zones

For legacy types such as `java.util.Date`, the time zone applied during formatting can depend on the annotation (`iso`/`style`/`pattern`) and Spring/JVM configuration. Do not extrapolate `@DateTimeFormat` behavior on `Date` directly onto `LocalDateTime` or `Instant`. Avoid calling `Locale.setDefault(...)`, `TimeZone.setDefault(...)`, or mutating JVM-wide time zone inside a request handler: that affects other concurrent requests.

If you simply need to display an `Instant` to a user, an explicit approach is:

```java
DateTimeFormatter output = DateTimeFormatter
        .ofPattern("dd/MM/uuuu HH:mm XXX", locale)
        .withZone(presentationZone);
String text = output.format(confirmedInstant);
```

Here `confirmedInstant` is the resolved instant, `presentationZone` is the chosen display zone, and `locale` is the language/display convention. Even though the numeric pattern is fixed, `locale` is still passed so templates with month/weekday names can vary cleanly later.

## 8. Real-world scenarios: data modeling and API contracts

**Scenario A — transaction logs:** store `Instant` in UTC and render for viewers in their zone. A log created in Vietnam and viewed in California refers to the exact same instant. To query by local "business day", compute day boundaries using the relevant `ZoneId` before converting to `Instant`.

**Scenario B — one-off finalized meeting:** the organizer enters local date/time and IANA zone; the backend resolves the valid offset (handling DST) and stores `Instant`. Retain `ZoneId` as well to display meeting context or apply policy updates as needed.

**Scenario C — recurring schedule at 09:00 in New York:** store recurrence rules, `LocalTime`, and `America/New_York`; compute `Instant` for each occurrence using that day's time rules. Do not use a fixed `-05:00` offset year-round.

**Scenario D — birthdays:** store `LocalDate`. A birthday does not inherently become an `Instant`; only when the system must send greetings "at 08:00 in the user's time zone" do you resolve a specific time and zone.

**Scenario E — multilingual UI:** a user in New York views a Vietnamese UI. Choose `Locale=vi-VN` and `ZoneId=America/New_York`; weekday/month names are in Vietnamese while displayed clock times match New York.

| Data | Recommended to send/store | Why |
| --- | --- | --- |
| Absolute event timestamp | `Instant` or UTC ISO with `Z` | Reproduces a single point on the timeline |
| Instant with client-side offset | `OffsetDateTime` | Preserves client-supplied offset, determines instant |
| Local appointment | `LocalDateTime` + `ZoneId` + DST policy | Unambiguous about region and clock rules |
| Recurring local-time schedule | `LocalTime`/`LocalDate` + `ZoneId` + recurrence rule | Tracks local wall-clock time across DST changes |
| Cultural/UI preference | `Locale` (e.g. BCP 47 tag `vi-VN`) | Serves language and formatting |
| Actual offset at an instant | `ZoneOffset` | Provides conversion context, does not replace region zone |

## 9. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Inferring `Asia/Ho_Chi_Minh` from `vi-VN` | Wrong for Vietnamese users abroad | Store locale and zone as two independent choices |
| Storing `UTC-5` instead of `America/New_York` | Schedule shifts during DST | Store region `ZoneId` for future scheduling rules |
| Using `LocalDateTime.now()` without a zone for audit logs | Depends on host machine and lacks an explicit instant | Use `Instant.now(clock)` or `OffsetDateTime.now(ZoneOffset.UTC)` per contract |
| Parsing `2026-07-01T19:00:00` and appending `Z` | Falsely assumes 19:00 UTC | Convert to UTC only after zone/offset is known |
| Using `withZoneSameLocal` when displaying to someone in another zone | Shifts the meeting instant | Use `withZoneSameInstant` |
| Ignoring DST gaps/overlaps | Times get silently shifted or hit two possible instants | Check `getValidOffsets` and handle per policy |
| Calling `TimeZone.getTimeZone("typo")` to validate | Invalid IDs can silently become GMT without error | Use `ZoneId.of(...)` and catch `DateTimeException` |
| Treating `Accept-Language` as a time zone | Wrong location inferred from language | Read time zone separately from config/user data |
| Applying `@DateTimeFormat` for JSON expecting Jackson to change | JSON still uses separate serialization config | Separate Spring formatting from JSON config |
| Using `YYYY-MM-dd` for calendar years | Can print wrong year near New Year's because `YYYY` is week-based-year | Use `uuuu-MM-dd`/ISO appropriately |
| Sharing mutable `SimpleDateFormat` across threads | Unsafe formatting/parsing | Use immutable `DateTimeFormatter` or per-call formatters |
| Relying on `LocaleContextHolder` across async threads | Locale/time zone lost or falls back to default | Pass required values per request/job |

Worthwhile tests to write:

1. Same `Instant` in multiple zones; assert post-conversion `Instant` values remain equal.
2. One `ZoneId` in winter and summer; assert offsets can differ.
3. `LocalDateTime` in DST gap and overlap; assert transparent accept/reject policy.
4. Different locales with the same zone; assert presentation differs while the instant is unchanged.
5. Invalid zone IDs, blank fields, malformed formats; verify `BindingResult` and HTTP 400.
6. Conversions via JSON/forms and across JDKs/locales if the product has strict formatting contracts.
7. Recurring schedules across DST transition dates; assert local wall-clock time stays accurate.

## 10. Rules to remember

- **`ZoneId` specifies a region's time rules; `ZoneOffset` specifies the UTC difference at an instant; `Locale` specifies language/formatting conventions.**
- `Instant` represents a real point in time; `LocalDateTime` does not represent a real point in time without a zone/offset.
- Time zone and offset determine **what time it is** locally; locale determines **how that date/time is written**.
- In Spring, `@DateTimeFormat` handles field parsing/printing, while resolving zones, handling DST, and choosing storage models are business decisions.
- Choose IANA regions (such as `America/New_York`) for local schedules needing DST rules; keep UTC/`Instant` for resolved instants; convert when presenting.
- Do not guess time zones from locale or server defaults: require explicit region information when business accuracy matters.

### References

- Java 17 `ZonedDateTime` and gap/overlap handling: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html
- Java `ZoneId`, `ZoneOffset`, `DateTimeFormatter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html
- Spring Field Formatting: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring MVC — Locale and Time Zone: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/localeresolver.html
- Spring MVC — Type Conversion: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html
- Spring MVC — `@ModelAttribute` and binding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
