# Wrong Locale, Charset, Pattern, or Time Zone — Diagnosing Spring MVC Validation & Data Binding

## 1. Real-World Scenario: "Identical" Data Producing Different Results

A Java/Spring MVC API receives dates, monetary amounts, Vietnamese names, and appointment timestamps. Users report:

- Machine A accepts `amount=1,234.50`, while machine B accepts `amount=1.234,50`.
- A form submits `day=06/11/2026` yet the server reports `typeMismatch`; the same value in JSON is parsed differently.
- `@NotBlank` messages appear in English even though the client sends `Accept-Language: vi`.
- The name `Đà Nẵng` turns into garbled characters such as `Ä Ã  Nẵng`.
- `2026-11-06T09:30:00+07:00` and `2026-11-06T02:30:00Z` are treated as two different appointments.
- A user in Berlin selects `2026-03-29 02:30`, yet that local time **does not exist** due to daylight saving time (DST).
- After running in CI or deploying a container in the UTC zone, tests relying on `ZoneId.systemDefault()` suddenly fail.

These can stem from **four independent failure categories**:

| Category | What does it govern? | Example |
| --- | --- | --- |
| **Locale** | Message language, decimal separator, grouping separator, month/day names | `1,234.50` (US) vs. `1.234,50` (Germany) |
| **Charset / encoding** | How bytes decode into Unicode text, and how text encodes back to bytes | UTF-8 for `Đà Nẵng` |
| **Pattern** | Which input string the parser accepts, and where day/month/year appear | `dd/MM/yyyy` vs. `yyyy-MM-dd` |
| **Time zone / UTC offset** | Which instant a local date-time points to, and whether DST gaps/overlaps exist | `+07:00` vs. `Europe/Berlin` |

**Article goal:** follow a diagnostic process to pinpoint the exact failing layer rather than randomly tweaking `Locale.setDefault()`, `spring.jackson.time-zone`, or adding `@JsonFormat` until "the error goes away."

In the **Spring Framework - validation-data-binding** module, we care specifically about:
1. How Spring MVC determines the locale when binding queries/forms.
2. How `@DateTimeFormat`, `@NumberFormat`, and `ConversionService` select parsers.
3. How `@RequestBody` flows through Jackson, differing from `@ModelAttribute`/`@RequestParam`.
4. How Jakarta Validation and Spring `MessageSource` select translated messages.
5. Where HTTP request, response, and resource-bundle encodings live.
6. How Java Time distinguishes `LocalDate`, `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime`, and `Instant`.
7. Writing MockMvc/JUnit tests with explicit locale, charset, pattern, zone, and DST.

**Demonstrated versions:** Java 17+, Spring Framework 6.2.x, Spring Boot 3.5.6, Jakarta Validation, and Jackson managed by Spring Boot. These versions are fixed for the example, without claiming Boot 3.5.6 is the latest release.

## 2. Data Flow Diagram: Pinpointing Which Step Fails

```text
HTTP bytes
   |
   v
[1] HTTP decoding / request parameters
    Content-Type + charset, percent-encoding, query/form parsing
   |
   v
[2a] @RequestParam / @ModelAttribute
     ConversionService + Formatter + WebDataBinder
     @DateTimeFormat, @NumberFormat, type conversion
   |
   +------> [2b] @RequestBody JSON
                HttpMessageConverter / Jackson
                @JsonFormat, ObjectMapper, JavaTimeModule
   |
   v
[3] Jakarta Validation / Spring Validator
    @NotBlank, @NotNull, @Past, @Valid...
    LocalValidatorFactoryBean / MessageInterpolator
   |
   v
[4] Error handling / serialization
    BindingResult, FieldError, exception advice
    MessageSource, Locale, JSON response bytes
```

Do not conflate [1] and [2]: a string already decoded incorrectly from bytes cannot be repaired by `@DateTimeFormat`. Do not conflate [2a] and [2b]: `@JsonFormat` **does not** automatically control `@RequestParam`; `@DateTimeFormat` **does not** automatically control Jackson deserializing `@RequestBody`. Do not conflate [3] and [4]: localized messages are **validation output**, while the input data may or may not have converted cleanly.

### 2.1. Quick Symptom Table

| Symptom | Check first | Avoid doing immediately |
| --- | --- | --- |
| `typeMismatch` on `06/11/2026` | `@DateTimeFormat`, target Java type, URI encoding | Changing timezone before checking pattern |
| Monetary amount parsed wrongly | Request locale, `@NumberFormat`, grouping/decimal marks | Changing JVM default locale in request thread |
| JSON date parses differently from query | Jackson `@JsonFormat`/ObjectMapper vs. Spring Formatter | Assuming one annotation applies to both |
| Vietnamese text turns into "mojibake" | Raw bytes, request charset, resource encoding | Changing `Accept-Language` to fix Unicode |
| Error message in wrong language | `LocaleResolver`, `MessageSource`, `ValidationMessages` | Changing timezone |
| Two timestamps look different | Compare `Instant`, check offsets | Comparing raw date-time strings |
| Hour 02:30 occurs 0 or 2 times | ZoneId rules + DST transition | Using a static offset year-round |
| CI fails due to current date | Default `Clock`/ZoneId/Locale | Mutating JVM-wide locale/zone in parallel tests |

## 3. Locale: Language and Formatting Conventions, Not Time Zone

### 3.1. What Is `Locale`?

Java `Locale` represents a language and regional variants, for example:

```java
Locale.ENGLISH;                           // en
Locale.US;                                // en-US
Locale.GERMANY;                           // de-DE
Locale.forLanguageTag("vi-VN");          // vi-VN
```

A locale typically governs:
- Which resource bundle is selected.
- Decimal/grouping separators and number formatting.
- Month or weekday names if the pattern uses text (e.g., `MMM`, `EEEE`).
- Certain pluralization/message formatting rules.

**It carries no time zone meaning.** A `Locale.US` user might be in Paris, Tokyo, Đà Nẵng, or using a UTC schedule. Never infer timezone from `Accept-Language`.

### 3.2. How Spring MVC Resolves Request Locale

In Servlet Spring MVC, `LocaleResolver` manages the request-scoped locale. A common configuration is `AcceptHeaderLocaleResolver`, which reads the locale indicated by the client via `Accept-Language`. Application code can access it via:

```java
Locale locale = LocaleContextHolder.getLocale();
```

This is a **fragment**; it requires importing `org.springframework.context.i18n.LocaleContextHolder` and must be called within a request context. When tests/services run outside a request, `LocaleContextHolder` may fall back to the system/thread-local locale.

Example:

```http
GET /api/format/amount?amount=1.234,50
Accept-Language: de-DE
```

If the field has `@NumberFormat(pattern="#,##0.00")`, the de-DE formatter treats `,` as the decimal separator and `.` as the grouping separator; an equivalent en-US request normally uses `1,234.50`.

### 3.3. `Accept-Language` Does Not Specify Charset

The header:

```http
Accept-Language: vi-VN
```

only indicates language preference. It does **not** declare the body is UTF-8, does not "repair" misdecoded bytes, and does not select `Asia/Ho_Chi_Minh`. Encoding, locale, and zone decisions must each be configured separately.

## 4. `@NumberFormat` and Decimal/Grouping Separator Errors

### 4.1. MVC Example

```java
@GetMapping("/amount")
public Map<String, String> amount(
        @RequestParam("amount")
        @NumberFormat(pattern = "#,##0.00")
        BigDecimal amount) {

    return Map.of(
            "plain", amount.stripTrailingZeros().toPlainString());
}
```

This is a fragment of the full controller in Section 13. The pattern `#,##0.00` uses:
- Grouping separators according to **the active locale**.
- At least two fractional digits when formatting.
- A parser/formatter used by Spring's `FormattingConversionService`.

Two requests representing **the same numeric quantity**:

```http
GET /api/format/amount?amount=1,234.50
Accept-Language: en-US
```

```http
GET /api/format/amount?amount=1.234,50
Accept-Language: de-DE
```

Expected logical output:

```json
{"plain":"1234.5"}
```

`stripTrailingZeros().toPlainString()` is used in the example so output does not depend on `BigDecimal` scale (which could be `1234.50` or `1234.5`). This is the **demo's canonical display**, not a universal serialization contract for money.

### 4.2. Diagnosing the Parser: Right Locale Yet Wrong Value

Possible causes:
1. `@NumberFormat` is not placed on the **right** field/parameter.
2. The controller accepts `String` and calls `new BigDecimal(text)` manually, bypassing the formatter.
3. The request locale resolver was overridden.
4. The NumberFormat parser has unexpected leniency/coercion rules.
5. A custom `Converter<String,BigDecimal>` takes precedence.
6. You are using a `@RequestBody` JSON numeric value, which flows through Jackson.

**Important:** do not send `"1.234,50"` with locale en-US and assume it is guaranteed to fail. Some numeric parsers behave leniently or return a **different** value without throwing an exception. If the input contract must be strict, add dedicated validation or a strict parser that verifies full-input consumption and explicitly tests ambiguous cases.

### 4.3. `@NumberFormat(style=...)` or Pattern?

```java
@NumberFormat(style = NumberFormat.Style.CURRENCY)
BigDecimal price;
```

This can be used when UI requires locale-aware currency formatting, though currency symbols, spacing, and grouping depend on locale. For machine-to-machine APIs, **prefer canonical numbers without grouping** or an explicit schema rather than forcing clients to send formatted currency text.

When business logic involves money, `BigDecimal` is usually safer than `double` to avoid binary floating-point rounding errors. Rounding, currency scale, and monetary math must still be defined explicitly.

## 5. Date Patterns: `@DateTimeFormat` Differs from `@JsonFormat`

### 5.1. Spring MVC Query/Form Binding

```java
@GetMapping("/day")
public Map<String, String> day(
        @RequestParam("day")
        @DateTimeFormat(pattern = "dd/MM/yyyy")
        LocalDate day) {

    return Map.of("isoDate", day.toString());
}
```

Request:

```http
GET /api/format/day?day=06/11/2026
```

Result:

```json
{"isoDate":"2026-11-06"}
```

However:

```http
GET /api/format/day?day=2026-11-06
```

**does not match the `dd/MM/yyyy` pattern**. Spring's conversion path typically leads to `MethodArgumentTypeMismatchException`/`TypeMismatchException` with HTTP 400 (if an appropriate error resolver is present).

### 5.2. Do Not Mix Up Day–Month Order

With `dd/MM/yyyy`:
- `06/11/2026` is **November 6, 2026**.
- `11/06/2026` is **June 11, 2026**.

If the API uses `MM/dd/yyyy`:
- `06/11/2026` is **June 11, 2026**.

One string can be valid under **both patterns** while carrying different meanings. Testing only HTTP 200 is not enough: assert that `LocalDate` was interpreted properly (canonical ISO output).

### 5.3. Use ISO When Integrating Systems

Without special UI constraints, a clearer API signature is:

```java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
LocalDate day
```

with value `2026-11-06`. ISO is recommended for service/client APIs because it avoids day–month ambiguity. If business rules genuinely require `dd/MM/yyyy` for forms, **specify** and test the pattern rather than guessing from the default locale.

### 5.4. Setting a Pattern Does Not Give `LocalDate` a Time Zone

`LocalDate` describes only a **calendar date**, with no time of day, timezone, or UTC offset. Hence:
- Turning `06/11/2026` into `2026-11-06` is **changing date representation**, not shifting an instant.
- Never add or subtract 7 hours on a `LocalDate` to "adjust for Vietnam."
- When converting a calendar date into a time range (e.g., a 00:00–24:00 sales report), pick the **business `ZoneId`** and account for DST.

### 5.5. `dd/MM/yyyy`, `dd/MM/uuuu`, and Strict Parsing

In `java.time.format.DateTimeFormatter`:
- `y` is year-of-era.
- `u` is proleptic year.
- `ResolverStyle.SMART` and `ResolverStyle.STRICT` can yield different behavior for nonexistent dates or era handling.

JDK strict parsing example:

```java
DateTimeFormatter strict =
        DateTimeFormatter.ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT);

LocalDate parsed =
        LocalDate.parse("06/11/2026", strict);
```

This is a Java 17 fragment requiring `LocalDate`, `DateTimeFormatter`, and `ResolverStyle` imports. If **strict validation** is required across all inputs (rejecting nonexistent dates), use a parser with an explicit resolver style or custom validation. Do not assume every default `@DateTimeFormat` setup matches this strict JDK snippet.

## 6. JSON Has Its Own Date Formatting Path

When a controller uses:

```java
@PostMapping("/json")
public void json(@RequestBody SomeDto dto) {}
```

Spring MVC normally uses Jackson's `HttpMessageConverter`. For the request DTO:

```java
public record SomeDto(
        @JsonFormat(pattern = "dd/MM/yyyy")
        LocalDate day) {}
```

the `@JsonFormat` annotation here configures Jackson's handling of the `day` field in JSON; it does not replace `@DateTimeFormat` on queries/forms.

A DTO can carry both:

```java
@DateTimeFormat(pattern = "dd/MM/yyyy")
@JsonFormat(pattern = "yyyy-MM-dd")
private LocalDate day;
```

They apply on **two separate input paths**; tests should demonstrate that an `application/x-www-form-urlencoded` request and a JSON request have different expected inputs. Unless required, standardize on ISO at the boundary to avoid maintaining two format contracts.

**Note:** do not treat `spring.jackson.date-format` or `spring.jackson.time-zone` as an "app-wide format switch for every Java Time type." Jackson has distinct modules, serializers, and annotations for `java.time`; global properties do not necessarily affect `LocalDate`, `LocalDateTime`, `Instant`, and legacy `java.util.Date` identically. Verify the real JSON wire format with ObjectMapper tests or MockMvc.

## 7. Charset: A Bytes → String Bug, Not Locale

### 7.1. UTF-8 and Mojibake

A Java `String` uses Unicode. Over HTTP, it is encoded into bytes using a charset (typically UTF-8). The receiver must decode using a charset **matching the actual bytes**.

Standalone runnable Java example:

```java
// CharsetEvidence.java
import java.nio.charset.StandardCharsets;

public class CharsetEvidence {
    public static void main(String[] args) {
        String value = "Đà Nẵng";
        byte[] utf8 = value.getBytes(StandardCharsets.UTF_8);

        System.out.println(
                new String(utf8, StandardCharsets.UTF_8));
        System.out.println(
                value.equals(new String(
                        utf8, StandardCharsets.ISO_8859_1)));
    }
}
```

Run:

```bash
javac -encoding UTF-8 CharsetEvidence.java
java CharsetEvidence
```

**Deterministic** stdout:

```text
Đà Nẵng
false
```

This proves a wrong charset corrupts text even when `Locale.forLanguageTag("vi-VN")` is selected properly.

### 7.2. Places Where Encoding Can Diverge

1. **URL/query**: URI percent-encoding of non-ASCII characters; how the server decodes queries.
2. **HTML form**: `application/x-www-form-urlencoded` body typically carries percent-encoded bytes; request character encoding must match.
3. **JSON**: `application/json` on the Internet normally uses UTF-8; the Jackson JSON parser receives bytes via the message converter with its own encoding handling.
4. **Response**: Charset specified/applied when serializing text, especially plain text or HTML.
5. **Resource bundles**: Encoding used when reading `messages.properties`/`messages_vi.properties`.
6. **Source/build**: Java/properties file encoding and Maven compiler/resources encoding.
7. **Database**: Connection/column charset, collation, and previously stored data.
8. **Terminal/log viewer**: Console may render glyphs wrongly even when HTTP bytes and JSON are valid.

Do not merely stare at a "garbled text" screenshot: inspect bytes and each boundary to locate **the first point** where Unicode text was altered.

### 7.3. Spring Boot Servlet Encoding

Example configuration:

```properties
server.servlet.encoding.charset=UTF-8
server.servlet.encoding.force=true
spring.messages.encoding=UTF-8
```

`server.servlet.encoding.*` governs Servlet request/response encoding. `spring.messages.encoding` governs Spring `MessageSource` resource bundles. These two properties address **two different concerns**. Jackson JSON, databases, and terminals still have their own settings if applicable.

Do not change production encoding config merely because a `MockMvc.param(...)` test failed: `param(...)` passes **already-decoded Java Strings** into the mock request and **does not** thoroughly test wire bytes or percent-decoding.

### 7.4. Testing Raw Bytes Instead of Strings Alone

When testing JSON:

```java
String json = """
    {"name":"Đà Nẵng"}
    """;

mvc.perform(post("/api/echo")
        .contentType(MediaType.APPLICATION_JSON)
        .content(json.getBytes(StandardCharsets.UTF_8)))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.name").value("Đà Nẵng"));
```

Here `content(byte[])` feeds actual UTF-8 bytes into the mock HTTP message converter. Unlike a unit test calling `new String(...)`, it exercises Jackson and the MVC endpoint.

For forms:
- `.param("city", "Đà Nẵng")` tests binding of an already-decoded String.
- To test wire bytes of `application/x-www-form-urlencoded`, pass a URL-encoded byte body with the right encoding or run a real-server test. Avoid claiming `.param(...)` proves proxies/containers decode UTF-8 properly.

### 7.5. Do Not Fix Charset with `Accept-Language`

A user choosing English can still submit the name `Nguyễn Thị Mai`; UTF-8 must preserve Unicode intact. Locale controls message selection and certain formatting rules; charset controls bytes↔text.

## 8. `MessageSource`: "Right Error, Wrong Message Language"

### 8.1. Jakarta Validation Message Keys

A DTO record:

```java
public record EchoRequest(
        @NotBlank(message = "{request.name.required}")
        String name) {}
```

Spring Boot translations:

```properties
# messages.properties
request.name.required=Please enter a name
```

```properties
# messages_vi.properties
request.name.required=Vui lòng nhập tên
```

Spring Boot integrates `MessageSource` into validation message interpolation when using auto-configured Validator infrastructure. Thus the same `@NotBlank` returns different text depending on the request locale. **A base `messages.properties` file must exist** when relying on Boot's convention-based auto-configured message source.

### 8.2. Checking Wrong-Locale Message Bugs in Order

1. Does the endpoint use `@Valid` or `@Validated` to trigger Bean Validation?
2. Is `spring-boot-starter-validation`/a provider on the classpath?
3. Does `LocaleResolver` honor `Accept-Language` or was it overridden?
4. Are `messages.properties` and `messages_vi.properties` in the right place under `src/main/resources`?
5. Is there a typo in the key name, basename, or file encoding?
6. Does the handler return `FieldError.getDefaultMessage()` or a hard-coded English message?
7. Is a custom `LocalValidatorFactoryBean` or `MessageInterpolator` bypassing Spring `MessageSource`?
8. Does the test set an explicit locale or rely on the CI machine's default?

### 8.3. `getMessageTemplate()` Differs from `getMessage()`

For a Jakarta `ConstraintViolation`:
- `getMessageTemplate()` normally retains the original descriptor, e.g., `{request.name.required}`.
- `getMessage()` is the localized interpolated text.

For Spring MVC `MethodArgumentNotValidException`, `FieldError.getDefaultMessage()` normally contains the corresponding message from the validator. If you need a machine-readable error code, **do not use the translated text itself** as the code: use a dedicated stable code.

In the sample project, the JSON error response has:
- `code`: e.g., `VALIDATION_ERROR`, `TYPE_MISMATCH`.
- Stable `issues[].field` and `issues[].code`.
- `issues[].message` can be localized, without containing raw rejected values.

## 9. Time Zones: Local Date-Time, Offset, and Instant Are Three Different Things

### 9.1. Distinguishing Java Time Types

| Type | What does it hold? | Application example |
| --- | --- | --- |
| `LocalDate` | Calendar date, **no time/zone** | Birth date, report date |
| `LocalTime` | Time of day, **no date/zone** | Daily opening hour |
| `LocalDateTime` | Local date + time, **no zone/offset** | Appointment time chosen before a location is known |
| `OffsetDateTime` | Local date-time + concrete UTC offset | Client-sent timestamp with `+07:00` |
| `ZonedDateTime` | Date-time + `ZoneId` with timezone rules | Appointment in `Europe/Berlin` |
| `Instant` | A point on the UTC timeline | Storage, comparison, audit timestamps |
| `ZoneId` | Geographical timezone rules or fixed offset | `Asia/Ho_Chi_Minh`, `Europe/Berlin` |
| `ZoneOffset` | Fixed difference from UTC | `+07:00`, `+01:00` |

**Do not equate**:
- `LocalDateTime.of(2026,11,6,9,30)` and `Instant`: this local time alone does not identify an instant.
- `ZoneId.of("Europe/Berlin")` and `ZoneOffset.ofHours(1)`: Berlin observes DST; the offset can be `+01:00` or `+02:00` depending on date.
- `Locale.GERMANY` and `ZoneId.of("Europe/Berlin")`: selecting a locale does not select a zone.
- `Asia/Ho_Chi_Minh` and `+07:00`: they share the same offset at the point in time considered, yet one is a set of zone rules and the other is a static offset.

### 9.2. Two Different Strings Representing the Same Instant

```text
2026-11-06T09:30:00+07:00
2026-11-06T02:30:00Z
```

Both timestamps correspond to **2026-11-06T02:30:00Z**. Java:

```java
Instant first = OffsetDateTime.parse(
        "2026-11-06T09:30:00+07:00").toInstant();

Instant second = OffsetDateTime.parse(
        "2026-11-06T02:30:00Z").toInstant();

System.out.println(first.equals(second));  // true
```

Note that `Z` denotes zero UTC offset in an ISO timestamp. Tests must compare **`Instant`** rather than raw strings or `LocalDateTime` when checking "the same point in time."

### 9.3. `@DateTimeFormat(iso=ISO.DATE_TIME)`

With a query parameter:

```java
@GetMapping("/instant")
public Map<String, String> instant(
        @RequestParam("at")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
        OffsetDateTime at) {

    return Map.of("instant", at.toInstant().toString());
}
```

Requests can send `at=2026-11-06T09:30:00%2B07:00` (URL-encoding the plus sign) or `at=2026-11-06T02:30:00Z`. Expect the same canonical instant. If the URL does not encode `+` properly, some query/form decoders treat it as a space: the failure happens **before** DateTimeFormat parsing.

### 9.4. Where Should the Zone Live?

In a scheduling system, the API can accept:
- `local=2026-11-06T09:30:00`
- `zone=Asia/Ho_Chi_Minh`

and then resolve the instant using timezone rules. Explicitly tie the zone to the **location/event**, never infer it from UI language.

If a user supplies `LocalDateTime` without selecting a zone:
- An exact instant cannot be determined in a multi-region system.
- Unless business rules fix an explicit single zone, require clients to send an offset/zone.
- Never silently attach the server's `ZoneId.systemDefault()`, because deploying in another region changes results.

## 10. DST: Gaps and Overlaps Must Be Handled Intentionally

### 10.1. DST Gap — Nonexistent Local Time

In `Europe/Berlin` on **2026-03-29**, clocks jump from 02:00 to 03:00 (offset changes from `+01:00` to `+02:00`). Thus `2026-03-29T02:30` is a **nonexistent local time**.

Java:

```java
LocalDateTime local = LocalDateTime.of(2026, 3, 29, 2, 30);
ZoneId zone = ZoneId.of("Europe/Berlin");
List<ZoneOffset> offsets =
        zone.getRules().getValidOffsets(local);

System.out.println(offsets.size()); // 0
```

Calling `local.atZone(zone)` makes Java automatically resolve the gap by shifting the local time forward to a valid instant. Yet when business rules require users to pick an **exact appointment time**, that silently hides an invalid input. The demo project **returns a `GAP` status** instead of shifting the clock automatically.

### 10.2. DST Overlap — Local Time Occurs Twice

In `Europe/Berlin` on **2026-10-25**, clocks fall back. `2026-10-25T02:30` can correspond to:
- `+02:00`, or
- `+01:00`.

```java
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);
ZoneId zone = ZoneId.of("Europe/Berlin");

List<ZoneOffset> offsets =
        zone.getRules().getValidOffsets(local);

System.out.println(offsets.size()); // 2
```

A single instant cannot be determined from local time + `ZoneId` alone during an overlap hour without an offset-selection policy. The demo project returns **`OVERLAP`** along with both offsets for the client or business policy to decide.

### 10.3. Do Not Use a Fixed `+07:00` for Every Schedule Worldwide

`Asia/Ho_Chi_Minh` has offset `+07:00` for modern timestamps considered here and currently does not observe DST transitions. Never apply that assumption to `Europe/Berlin`, `America/New_York`, or arbitrary timezones.

### 10.4. "Current" Time and Deterministic Tests

Flaky code:

```java
LocalDate today = LocalDate.now();
```

For testing, inject `Clock`:

```java
Clock clock = Clock.fixed(
        Instant.parse("2026-11-06T02:30:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDate today = LocalDate.now(clock);
// today = 2026-11-06
```

Use `Clock.fixed` so tests do not depend on when CI runs. For user-facing logic, pick the use case's proper zone. Never call `TimeZone.setDefault(...)`/`Locale.setDefault(...)` in parallel tests when dependencies/locales can be passed explicitly, as those mutate global state.

## 11. Designing an Error Contract for Accurate Diagnosis

We use an application-defined JSON envelope:

```json
{
  "code": "TYPE_MISMATCH",
  "issues": [
    {
      "field": "day",
      "code": "typeMismatch",
      "message": "Invalid value or format"
    }
  ]
}
```

Another Bean Validation error:

```json
{
  "code": "VALIDATION_ERROR",
  "issues": [
    {
      "field": "name",
      "code": "NotBlank",
      "message": "Vui lòng nhập tên"
    }
  ]
}
```

**Definitions:**
- `code`: stable, non-localized category, e.g., `TYPE_MISMATCH`, `BODY_UNREADABLE`, `BINDING_ERROR`, `VALIDATION_ERROR`, `UNEXPECTED_FIELD`, `INVALID_TIME_INPUT`.
- `issues[].code`: stable field-level cause, not a raw exception message.
- `issues[].message`: user-facing text, localized when appropriate.
- Type-mismatched inputs do not echo the raw request value in the message; a simple `"Invalid value or format"` is used.
- `issues[]` is sorted for deterministic testing.
- Never return rejected values, full request bodies, stack traces, internal class names, or SQL details.

**Key distinction:** a data binder's `typeMismatch` is not `@Min`/`@NotBlank`. If parsing fails first, the validator cannot inspect the expected typed value.

Real projects may use Spring `ProblemDetail`/RFC 9457, while this article chooses a small schema so learners clearly see the mapping between binding/validation and responses.

## 12. Diagnostic Checklist Before Changing Configuration

### 12.1. Gather at Least Four Facts

Record:
1. **Input form**: query, form, JSON, or path variable?
2. Java target type and annotations: `LocalDate`/`OffsetDateTime`/`BigDecimal`/`String`, `@DateTimeFormat`, `@NumberFormat`, `@JsonFormat`?
3. **Active** locale/charset/zone at each layer: request locale, request encoding, `MessageSource`, parser, business zone?
4. **Where** the outcome occurs: converter, binder, Jackson, validator, message interpolation, or serializer?

Only then fix the root cause. Changing global JVM locale/zone prematurely may mask one bug while introducing another.

### 12.2. Classifying via Exceptions and `BindingResult`

| Exception/output | Diagnostic hint |
| --- | --- |
| `MethodArgumentTypeMismatchException` | Query/path parameter failed conversion; check pattern and converter |
| `FieldError.isBindingFailure()==true` | Form field binder conversion failed, likely inside `BindingResult` |
| `HttpMessageNotReadableException` | JSON body unreadable; Jackson parse/type/schema issue |
| `MethodArgumentNotValidException` | DTO validation and possibly binding errors depending on argument |
| `HandlerMethodValidationException` | Direct constraints on handler parameters or return value (Spring MVC 6.1+) |
| `FieldError.getDefaultMessage()` in wrong language | Check Spring `MessageSource`/locale and provider interpolation |
| `DateTimeParseException` from service | Wrong Java Time pattern/zone/offset or invalid input |

Do not guess solely from HTTP status: several of the errors above return 400. If `@Validated` AOP method validation is active on services, the exception path differs from built-in MVC method validation; this article focuses on query/form/JSON.

### 12.3. Safe Logging

Logs should capture:
- Correlation/request ID.
- Endpoint name and error category.
- Contract-defined **field name**, not arbitrary unbounded raw field paths.
- Request locale, resolved charset, formatter/pattern name, and business zone if applicable.
- Failing phase: decoding, binding, validation, or domain time resolution.
- Never log sensitive values or raw bodies by default.

Do not use raw user input as a metric label; cardinality and privacy quickly become operational hazards.

## 13. Runnable Project: Java 17, Spring Boot 3.5.6

The project exposes these endpoints:
- `GET /api/format/day`: binds `LocalDate` using `dd/MM/yyyy`.
- `GET /api/format/amount`: binds `BigDecimal` using `@NumberFormat` and locale.
- `GET /api/format/instant`: binds `OffsetDateTime` and returns canonical `Instant`.
- `GET /api/format/zone`: checks `ZoneId` and DST gap/overlap for a local time.
- `POST /api/echo`: accepts UTF-8 JSON, validates name, and returns en/vi messages.
- `POST /api/form`: binds UTF-8 form, date/number, reporting pattern/type errors and out-of-allowlist fields.

Includes complete source code, resource bundles, and JUnit/MockMvc tests. No external database or network service is needed.

### 13.1. Directory Tree

```text
locale-time-diagnostics/
├── pom.xml
├── src/main/java/demo/diagnostics/
│   ├── DiagnosticsApplication.java
│   ├── TimeDiagnostics.java
│   ├── DiagnosticForm.java
│   ├── EchoRequest.java
│   ├── DiagnosticError.java
│   ├── DiagnosticController.java
│   └── DiagnosticAdvice.java
├── src/main/resources/
│   ├── application.properties
│   ├── messages.properties
│   └── messages_vi.properties
└── src/test/java/demo/diagnostics/
    ├── DateNumberMvcTest.java
    ├── UnicodeLocaleMvcTest.java
    ├── TimeZoneMvcTest.java
    ├── FormBindingMvcTest.java
    └── TimeDiagnosticsTest.java
```

### 13.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>locale-time-diagnostics</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Keep dependencies Boot-managed; do not manually mix mismatched versions of Jackson, Jakarta Validation, or Spring Framework. Spring Boot 3.5.6 requires Java 17 or newer.

### 13.3. `application.properties`

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8

server.servlet.encoding.charset=UTF-8
server.servlet.encoding.force=true
```

Do not add `spring.jackson.time-zone=Asia/Ho_Chi_Minh` hoping every `LocalDateTime` turns into an instant; business zone is passed **explicitly** to the `/zone` endpoint.

### 13.4. `messages.properties`

```properties
request.name.required=Please enter a name
form.city.required=Please enter a city
form.day.required=Please select a day
form.amount.required=Please enter an amount
```

### 13.5. `messages_vi.properties`

```properties
request.name.required=Vui lòng nhập tên
form.city.required=Vui lòng nhập thành phố
form.day.required=Vui lòng chọn ngày
form.amount.required=Vui lòng nhập số tiền
```

Save files as UTF-8. A base `messages.properties` file is required for Boot to auto-configure `MessageSource` by convention when no custom message source bean exists.

### 13.6. `DiagnosticsApplication.java`

```java
package demo.diagnostics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiagnosticsApplication {
    public static void main(String[] args) {
        SpringApplication.run(DiagnosticsApplication.class, args);
    }
}
```

### 13.7. `TimeDiagnostics.java`

```java
package demo.diagnostics;

import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

public final class TimeDiagnostics {

    private TimeDiagnostics() {}

    public record Analysis(
            String status,
            String instant,
            List<String> offsets) {
    }

    public static Analysis analyze(String localRaw, String zoneRaw) {
        LocalDateTime local = LocalDateTime.parse(localRaw);
        ZoneId zone = ZoneId.of(zoneRaw);

        List<ZoneOffset> valid =
                zone.getRules().getValidOffsets(local);

        if (valid.isEmpty()) {
            return new Analysis("GAP", null, List.of());
        }

        if (valid.size() > 1) {
            return new Analysis(
                    "OVERLAP",
                    null,
                    valid.stream()
                            .map(ZoneOffset::toString)
                            .toList());
        }

        ZoneOffset offset = valid.get(0);

        return new Analysis(
                "OK",
                local.atOffset(offset).toInstant().toString(),
                List.of(offset.toString()));
    }
}
```

**Explanation:**
- `LocalDateTime.parse` parses ISO local date-time, e.g., `2026-11-06T09:30:00`.
- `ZoneId.of` requires a valid zone ID; otherwise it throws `DateTimeException` (including `ZoneRulesException`).
- `getValidOffsets(local)` returns 0/1/2 offsets for gap/normal/overlap.
- With one offset, `local.atOffset(offset).toInstant()` yields a deterministic instant.
- For gaps or overlaps, **do not silently pick** an instant on the user's behalf.
- `status` is the demo's contract output, not a standard Java Time enum.

Because the method uses the timestamp and zone passed by the caller, it does not depend on `ZoneId.systemDefault()`/`LocalDateTime.now()`. Tests remain stable in CI.

### 13.8. `DiagnosticForm.java`

```java
package demo.diagnostics;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;

import java.math.BigDecimal;
import java.time.LocalDate;

public class DiagnosticForm {

    @NotBlank(message = "{form.city.required}")
    private String city;

    @NotNull(message = "{form.day.required}")
    @DateTimeFormat(pattern = "dd/MM/yyyy")
    private LocalDate day;

    @NotNull(message = "{form.amount.required}")
    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public LocalDate getDay() {
        return day;
    }

    public void setDay(LocalDate day) {
        this.day = day;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
```

`@NotNull` enforces that the field has a value. `@DateTimeFormat` and `@NumberFormat` control **conversion syntax**, not Jakarta constraints themselves. If a field fails to parse, `WebDataBinder` records a binding failure; if the field is missing, `@NotNull` can produce a constraint error.

### 13.9. `EchoRequest.java`

```java
package demo.diagnostics;

import jakarta.validation.constraints.NotBlank;

public record EchoRequest(
        @NotBlank(message = "{request.name.required}")
        String name) {
}
```

This JSON DTO has no `@JsonFormat` because `name` is Unicode text. For date/time JSON fields in real applications, use `@JsonFormat` per Jackson schema; do not confuse it with query/form `@DateTimeFormat`.

### 13.10. `DiagnosticError.java`

```java
package demo.diagnostics;

import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public record DiagnosticError(
        String code,
        List<Issue> issues) {

    public record Issue(
            String field,
            String code,
            String message) {
    }

    public static DiagnosticError simple(String code) {
        return new DiagnosticError(code, List.of());
    }

    public static DiagnosticError one(
            String code,
            String field,
            String issueCode,
            String message) {

        return new DiagnosticError(
                code,
                List.of(new Issue(field, issueCode, message)));
    }

    public static DiagnosticError fromBindingResult(
            BindingResult bindingResult) {

        List<Issue> issues = bindingResult
                .getFieldErrors()
                .stream()
                .map(e -> new Issue(
                        e.getField(),
                        e.isBindingFailure()
                                ? "typeMismatch"
                                : Objects.toString(e.getCode(), "invalid"),
                        e.isBindingFailure()
                                ? "Invalid value or format"
                                : Objects.toString(
                                        e.getDefaultMessage(),
                                        "Invalid value")))
                .distinct()
                .sorted(Comparator.comparing(Issue::field)
                        .thenComparing(Issue::code))
                .toList();

        boolean hasBindingFailure =
                bindingResult.getFieldErrors().stream()
                        .anyMatch(FieldError::isBindingFailure);

        return new DiagnosticError(
                hasBindingFailure
                        ? "BINDING_ERROR"
                        : "VALIDATION_ERROR",
                issues);
    }
}
```

`getDefaultMessage()` is used for **constraint violations** after message interpolation; type-binding failures use a fixed safe phrase to avoid echoing raw rejected values or exception text. In production, you can also map `ObjectError` and localize `typeMismatch`, while keeping the machine-readable `code` stable.

### 13.11. `DiagnosticController.java`

```java
package demo.diagnostics;

import jakarta.validation.Valid;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.Map;

@RestController
@RequestMapping("/api")
public class DiagnosticController {

    @GetMapping("/format/day")
    public Map<String, String> day(
            @RequestParam("day")
            @DateTimeFormat(pattern = "dd/MM/yyyy")
            LocalDate day) {

        return Map.of("isoDate", day.toString());
    }

    @GetMapping("/format/amount")
    public Map<String, String> amount(
            @RequestParam("amount")
            @NumberFormat(pattern = "#,##0.00")
            BigDecimal amount) {

        return Map.of(
                "plain", amount.stripTrailingZeros().toPlainString());
    }

    @GetMapping("/format/instant")
    public Map<String, String> instant(
            @RequestParam("at")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            OffsetDateTime at) {

        return Map.of("instant", at.toInstant().toString());
    }

    @GetMapping("/format/zone")
    public ResponseEntity<?> zone(
            @RequestParam("local") String local,
            @RequestParam("zone") String zone) {

        try {
            return ResponseEntity.ok(
                    TimeDiagnostics.analyze(local, zone));
        } catch (DateTimeException ex) {
            return ResponseEntity.badRequest().body(
                    DiagnosticError.simple("INVALID_TIME_INPUT"));
        }
    }

    @PostMapping(path = "/echo",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> echo(
            @Valid @RequestBody EchoRequest body) {

        return Map.of("name", body.name());
    }

    @InitBinder("diagnosticForm")
    void binder(WebDataBinder binder) {
        binder.setAllowedFields("city", "day", "amount");
    }

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> form(
            @Valid @ModelAttribute("diagnosticForm")
            DiagnosticForm form,
            BindingResult errors) {

        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest().body(
                    DiagnosticError.simple("UNEXPECTED_FIELD"));
        }

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body(
                    DiagnosticError.fromBindingResult(errors));
        }

        return ResponseEntity.ok(Map.of(
                "city", form.getCity(),
                "day", form.getDay().toString(),
                "amount", form.getAmount()
                        .stripTrailingZeros().toPlainString()));
    }
}
```

**MVC contract of the example:**
- `/format/day` accepts `dd/MM/yyyy` on the query parameter.
- `/format/amount` uses the request locale to interpret `@NumberFormat`.
- `/format/instant` accepts a timestamp with UTC offset and returns canonical `Instant`.
- `/format/zone` returns `GAP`, `OVERLAP`, or `OK`, without confusing locale with zone.
- `/echo` tests raw UTF-8 JSON + localized `@NotBlank`.
- `/form` tests `WebDataBinder` with 3 fields, including suppressed fields and binding failures.

`@InitBinder` is not used to impose `@DateTimeFormat` onto JSON via Jackson. `BindingResult` stands immediately after the model attribute so the controller handles errors locally.

### 13.12. `DiagnosticAdvice.java`

```java
package demo.diagnostics;

import org.springframework.beans.TypeMismatchException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class DiagnosticAdvice extends ResponseEntityExceptionHandler {

    private ResponseEntity<Object> reply(
            HttpHeaders headers,
            HttpStatusCode status,
            DiagnosticError error) {

        return new ResponseEntity<>(error, headers, status);
    }

    @Override
    protected ResponseEntity<Object> handleTypeMismatch(
            TypeMismatchException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        if (status.is5xxServerError()) {
            return reply(headers, status,
                    DiagnosticError.simple("SERVER_CONVERSION_ERROR"));
        }

        String field =
                ex instanceof MethodArgumentTypeMismatchException m
                        ? m.getName()
                        : "input";

        return reply(headers, status,
                DiagnosticError.one(
                        "TYPE_MISMATCH",
                        field,
                        "typeMismatch",
                        "Invalid value or format"));
    }

    @Override
    protected ResponseEntity<Object> handleMissingServletRequestParameter(
            MissingServletRequestParameterException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status,
                DiagnosticError.one(
                        "MISSING_PARAMETER",
                        ex.getParameterName(),
                        "required",
                        "Required parameter is missing"));
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status,
                DiagnosticError.simple("BODY_UNREADABLE"));
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status,
                DiagnosticError.fromBindingResult(
                        ex.getBindingResult()));
    }
}
```

This exception advice is scoped to the errors produced by the demo: query type mismatch, missing parameter, unreadable JSON, and request DTO Bean Validation. It does **not** try to "catch every Spring MVC error." If an application has direct method constraints `@Min`/`@NotBlank` on handler parameters, add handling for `HandlerMethodValidationException` (Spring MVC 6.1+) to preserve the JSON contract.

Do not declare an `@ExceptionHandler` duplicating exceptions already handled by `ResponseEntityExceptionHandler` in the superclass; prefer overriding protected methods. Preserve the `HttpStatusCode status` passed by the framework rather than forcing every `TypeMismatchException` to HTTP 400, because conversion failures can stem from server configuration.

## 14. MockMvc Tests: Locale and Pattern

### 14.1. `DateNumberMvcTest.java`

```java
package demo.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Locale;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DateNumberMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void dayPatternIsExplicitDayMonthYear() throws Exception {
        mvc.perform(get("/api/format/day")
                        .param("day", "06/11/2026"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.isoDate")
                        .value("2026-11-06"));
    }

    @Test
    void isoDateIsNotAcceptedByDdMmYyyyPattern()
            throws Exception {

        mvc.perform(get("/api/format/day")
                        .param("day", "2026-11-06"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("TYPE_MISMATCH"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("day"));
    }

    @Test
    void ambiguousDateShowsImportanceOfPattern()
            throws Exception {

        mvc.perform(get("/api/format/day")
                        .param("day", "11/06/2026"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.isoDate")
                        .value("2026-06-11"));
    }

    @Test
    void datePatternWorksWithGermanLocaleToo()
            throws Exception {

        mvc.perform(get("/api/format/day")
                        .locale(Locale.GERMANY)
                        .param("day", "06/11/2026"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.isoDate")
                        .value("2026-11-06"));
    }

    @Test
    void usLocaleParsesCommaGroupingDotDecimal()
            throws Exception {

        mvc.perform(get("/api/format/amount")
                        .locale(Locale.US)
                        .param("amount", "1,234.50"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.plain")
                        .value("1234.5"));
    }

    @Test
    void germanLocaleParsesDotGroupingCommaDecimal()
            throws Exception {

        mvc.perform(get("/api/format/amount")
                        .locale(Locale.GERMANY)
                        .param("amount", "1.234,50"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.plain")
                        .value("1234.5"));
    }

    @Test
    void missingAmountIsPresenceErrorNotParsingError()
            throws Exception {

        mvc.perform(get("/api/format/amount")
                        .locale(Locale.US))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MISSING_PARAMETER"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("amount"));
    }

    @Test
    void obviouslyNonNumericAmountIsRejected()
            throws Exception {

        mvc.perform(get("/api/format/amount")
                        .locale(Locale.GERMANY)
                        .param("amount", "not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("TYPE_MISMATCH"));
    }
}
```

**Meaning of the assertions:**
- The pattern determines day/month order, not merely whether parsing "succeeded."
- Fixed pattern `dd/MM/yyyy` does not flip order under the German locale.
- `@NumberFormat` uses decimal/grouping separators according to locale.
- A missing parameter is not a converter failure.
- Pick an input that is **clearly non-numeric** for the negative test; do not rely on ambiguous numeric strings when parsers are lenient.

## 15. MockMvc Tests: UTF-8 JSON and Multilingual Messages

### 15.1. `UnicodeLocaleMvcTest.java`

```java
package demo.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.charset.StandardCharsets;
import java.util.Locale;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UnicodeLocaleMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void utf8JsonBytesRoundTripVietnameseName()
            throws Exception {

        byte[] body = """
                {"name":"Đà Nẵng"}
                """.getBytes(StandardCharsets.UTF_8);

        mvc.perform(post("/api/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name")
                        .value("Đà Nẵng"));
    }

    @Test
    void vietnameseConstraintMessageUsesRequestLocale()
            throws Exception {

        mvc.perform(post("/api/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .locale(Locale.forLanguageTag("vi-VN"))
                        .content("{\"name\":\"\"}".getBytes(
                                StandardCharsets.UTF_8)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("name"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("NotBlank"))
                .andExpect(jsonPath("$.issues[0].message")
                        .value("Vui lòng nhập tên"));
    }

    @Test
    void englishConstraintMessageIsDifferent()
            throws Exception {

        mvc.perform(post("/api/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .locale(Locale.ENGLISH)
                        .content("{\"name\":\"\"}".getBytes(
                                StandardCharsets.UTF_8)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[0].message")
                        .value("Please enter a name"));
    }

    @Test
    void malformedJsonIsNotBeanValidation()
            throws Exception {

        mvc.perform(post("/api/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":".getBytes(
                                StandardCharsets.UTF_8)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BODY_UNREADABLE"));
    }

    @Test
    void blankTextIsInvalidRegardlessOfLocale()
            throws Exception {

        mvc.perform(post("/api/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .locale(Locale.forLanguageTag("vi"))
                        .content("{\"name\":\"   \"}".getBytes(
                                StandardCharsets.UTF_8)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[0].code")
                        .value("NotBlank"));
    }
}
```

**Key point:** the first test passes **UTF-8 bytes** via `content(byte[])`, rather than passing a pre-built `String` or invoking the converter manually. The two message tests choose explicit locales and assert English/Vietnamese messages while `code` remains unchanged.

If localized message tests fail while the Unicode JSON round-trip passes, that indicates HTTP payload encoding is **working** while `MessageSource`/locale interpolation is misconfigured. Never change the request charset just to fix a localized message.

## 16. MockMvc Tests: `OffsetDateTime` and DST

### 16.1. `TimeZoneMvcTest.java`

```java
package demo.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TimeZoneMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void vietnamOffsetConvertsToUtcInstant()
            throws Exception {

        mvc.perform(get("/api/format/instant")
                        .param("at",
                                "2026-11-06T09:30:00+07:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.instant")
                        .value("2026-11-06T02:30:00Z"));
    }

    @Test
    void equivalentUtcTimestampHasSameInstant()
            throws Exception {

        mvc.perform(get("/api/format/instant")
                        .param("at",
                                "2026-11-06T02:30:00Z"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.instant")
                        .value("2026-11-06T02:30:00Z"));
    }

    @Test
    void localTimeWithVietnamZoneHasOneOffset()
            throws Exception {

        mvc.perform(get("/api/format/zone")
                        .param("local", "2026-11-06T09:30:00")
                        .param("zone", "Asia/Ho_Chi_Minh"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("OK"))
                .andExpect(jsonPath("$.instant")
                        .value("2026-11-06T02:30:00Z"))
                .andExpect(jsonPath("$.offsets[0]")
                        .value("+07:00"));
    }

    @Test
    void berlinSpringGapIsReported()
            throws Exception {

        mvc.perform(get("/api/format/zone")
                        .param("local", "2026-03-29T02:30:00")
                        .param("zone", "Europe/Berlin"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("GAP"))
                .andExpect(jsonPath("$.offsets", hasSize(0)));
    }

    @Test
    void berlinAutumnOverlapIsReported()
            throws Exception {

        mvc.perform(get("/api/format/zone")
                        .param("local", "2026-10-25T02:30:00")
                        .param("zone", "Europe/Berlin"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("OVERLAP"))
                .andExpect(jsonPath("$.offsets", hasSize(2)));
    }

    @Test
    void invalidZoneIdIsClientInputError()
            throws Exception {

        mvc.perform(get("/api/format/zone")
                        .param("local", "2026-11-06T09:30:00")
                        .param("zone", "Not/A_Real_Zone"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_TIME_INPUT"));
    }

    @Test
    void invalidLocalDateTimeIsClientInputError()
            throws Exception {

        mvc.perform(get("/api/format/zone")
                        .param("local", "06/11/2026 09:30")
                        .param("zone", "Europe/Berlin"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_TIME_INPUT"));
    }

    @Test
    void missingZoneStillUsesRequiredParameterError()
            throws Exception {

        mvc.perform(get("/api/format/zone")
                        .param("local", "2026-11-06T09:30:00"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MISSING_PARAMETER"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("zone"));
    }
}
```

The offset test uses `.param(...)`, which supplies an already-decoded Java `String`; over real HTTP, `+` in a query string must be percent-encoded, e.g., `%2B07:00`. To test query byte encoding over the wire, add a real-server test or a dedicated raw URL test.

**Why HTTP 200 for GAP/OVERLAP?** In the demo, `/zone` is a **diagnostic endpoint** returning the analysis to the caller. A real **appointment booking** API might return 400/422 when a local time gap/overlap is unresolved; that is a business API decision, not a Spring-mandated status.

## 17. MockMvc Tests: Form Field Encoding, `@DateTimeFormat`, and `@NumberFormat`

### 17.1. `FormBindingMvcTest.java`

```java
package demo.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.util.Locale;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FormBindingMvcTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequestBuilder form() {
        return post("/api/form")
                .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED);
    }

    @Test
    void validFormBindsVietnameseTextAndUsNumber()
            throws Exception {

        mvc.perform(form()
                        .locale(Locale.US)
                        .param("city", "Đà Nẵng")
                        .param("day", "06/11/2026")
                        .param("amount", "1,234.50"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.city").value("Đà Nẵng"))
                .andExpect(jsonPath("$.day").value("2026-11-06"))
                .andExpect(jsonPath("$.amount").value("1234.5"));
    }

    @Test
    void validFormBindsGermanNumber()
            throws Exception {

        mvc.perform(form()
                        .locale(Locale.GERMANY)
                        .param("city", "Berlin")
                        .param("day", "06/11/2026")
                        .param("amount", "1.234,50"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.amount").value("1234.5"));
    }

    @Test
    void invalidDatePatternIsBindingFailure()
            throws Exception {

        mvc.perform(form()
                        .locale(Locale.US)
                        .param("city", "Hue")
                        .param("day", "2026-11-06")
                        .param("amount", "1,234.50"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("day")))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("typeMismatch")));
    }

    @Test
    void nonNumericFormValueIsBindingFailure()
            throws Exception {

        mvc.perform(form()
                        .locale(Locale.US)
                        .param("city", "Hue")
                        .param("day", "06/11/2026")
                        .param("amount", "not-money"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("amount")));
    }

    @Test
    void blankCityIsValidationError()
            throws Exception {

        mvc.perform(form()
                        .locale(Locale.US)
                        .param("city", "   ")
                        .param("day", "06/11/2026")
                        .param("amount", "1,234.50"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotBlank")));
    }

    @Test
    void unknownFieldIsRejectedSeparately()
            throws Exception {

        mvc.perform(form()
                        .locale(Locale.US)
                        .param("city", "Hue")
                        .param("day", "06/11/2026")
                        .param("amount", "1,234.50")
                        .param("admin", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"));
    }

    @Test
    void missingDayIsConstraintError()
            throws Exception {

        mvc.perform(form()
                        .locale(Locale.US)
                        .param("city", "Hue")
                        .param("amount", "1,234.50"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotNull")));
    }
}
```

**Understanding `.param(...)` correctly:** `MockMvc.param("city", "Đà Nẵng")` passes a Java `String` into the mock request, so it proves binding/validation preserves Unicode text once decoded, yet it **does not** prove a real HTTP client, proxy, or servlet container decodes UTF-8 percent-encoding properly. The article includes a JSON test using `content(byte[])` to verify bytes, and you can add a real integration test for form wire bytes when encoding sensitivity is critical.

## 18. Java Time Unit Tests: Without Spring

### 18.1. `TimeDiagnosticsTest.java`

```java
package demo.diagnostics;

import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TimeDiagnosticsTest {

    @Test
    void hoChiMinhZoneProducesExpectedUtcInstant() {
        var result = TimeDiagnostics.analyze(
                "2026-11-06T09:30:00",
                "Asia/Ho_Chi_Minh");

        assertEquals("OK", result.status());
        assertEquals("2026-11-06T02:30:00Z",
                result.instant());
        assertEquals(1, result.offsets().size());
        assertEquals("+07:00", result.offsets().get(0));
    }

    @Test
    void berlinSpringGapHasNoValidOffset() {
        var result = TimeDiagnostics.analyze(
                "2026-03-29T02:30:00",
                "Europe/Berlin");

        assertEquals("GAP", result.status());
        assertNull(result.instant());
        assertTrue(result.offsets().isEmpty());
    }

    @Test
    void berlinFallOverlapHasTwoValidOffsets() {
        var result = TimeDiagnostics.analyze(
                "2026-10-25T02:30:00",
                "Europe/Berlin");

        assertEquals("OVERLAP", result.status());
        assertNull(result.instant());
        assertEquals(2, result.offsets().size());
    }

    @Test
    void fixedClockMakesCurrentDateDeterministic() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-06T02:30:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        assertEquals(LocalDate.of(2026, 11, 6),
                LocalDate.now(clock));
    }

    @Test
    void utcAndVietnamOffsetRepresentSameInstant() {
        Instant fromVietnam = java.time.OffsetDateTime.parse(
                "2026-11-06T09:30:00+07:00").toInstant();
        Instant utc = Instant.parse(
                "2026-11-06T02:30:00Z");

        assertEquals(utc, fromVietnam);
    }
}
```

Benefits of pure unit tests:
- No Spring `ApplicationContext` needed.
- Diagnoses Java Time logic independently of HTTP/locale.
- Uses concrete dates so tests never depend on current wall-clock time.
- Uses real `ZoneId` rather than fixed offsets for DST scenarios.

## 19. Running and Verifying

There are five test classes:
- `DateNumberMvcTest` tests locale-aware date/amount formatting.
- `UnicodeLocaleMvcTest` tests UTF-8 JSON and en/vi translations.
- `TimeZoneMvcTest` tests offset/instant conversion and DST gap/overlap via MVC.
- `FormBindingMvcTest` tests form binding, patterns, and field suppression.
- `TimeDiagnosticsTest` tests Java Time logic outside Spring.

Run from the `locale-time-diagnostics` directory:

```bash
mvn test
```

Run individual groups:

```bash
mvn -Dtest=DateNumberMvcTest test
mvn -Dtest=UnicodeLocaleMvcTest test
mvn -Dtest=TimeZoneMvcTest test
mvn -Dtest=FormBindingMvcTest test
mvn -Dtest=TimeDiagnosticsTest test
```

Start the server:

```bash
mvn spring-boot:run
```

The expected JSON payloads and assertions above represent **expected behavior** for the sample project with matching dependencies. They are **not executed test output**; when practicing, inspect `target/surefire-reports` and fix by root cause if framework or environment differences appear.

### 19.1. Key Diagnostic Requests Summary

| Request | Expected outcome |
| --- | --- |
| `GET /api/format/day?day=06/11/2026` | `2026-11-06` |
| `GET /api/format/day?day=2026-11-06` | `TYPE_MISMATCH` |
| Amount `1,234.50` + locale en-US | `1234.5` |
| Amount `1.234,50` + locale de-DE | `1234.5` |
| JSON `{"name":"Đà Nẵng"}` as UTF-8 bytes | Echoes exact `Đà Nẵng` |
| JSON blank name + locale vi-VN | `Vui lòng nhập tên` |
| ISO offset `09:30+07:00` | Instant `02:30:00Z` |
| Berlin `2026-03-29T02:30` | `GAP` |
| Berlin `2026-10-25T02:30` | `OVERLAP` |
| Form `day=2026-11-06` under `dd/MM/yyyy` pattern | `BINDING_ERROR` |
| Form with `admin=true` | `UNEXPECTED_FIELD` |

## 20. Trying the API with `curl`: Watch URL-Encoding

### 20.1. Date Using Form Pattern

```bash
curl -i -G 'http://localhost:8080/api/format/day' \
  --data-urlencode 'day=06/11/2026'
```

Expected:

```json
{"isoDate":"2026-11-06"}
```

### 20.2. Locale-Aware Numeric Value

```bash
curl -i -G 'http://localhost:8080/api/format/amount' \
  -H 'Accept-Language: de-DE' \
  --data-urlencode 'amount=1.234,50'
```

Expected:

```json
{"plain":"1234.5"}
```

Try en-US:

```bash
curl -i -G 'http://localhost:8080/api/format/amount' \
  -H 'Accept-Language: en-US' \
  --data-urlencode 'amount=1,234.50'
```

### 20.3. Instant with Plus Sign in Offset

```bash
curl -i -G 'http://localhost:8080/api/format/instant' \
  --data-urlencode 'at=2026-11-06T09:30:00+07:00'
```

`--data-urlencode` ensures the `+` in `+07:00` is properly encoded in the query string. Expected:

```json
{"instant":"2026-11-06T02:30:00Z"}
```

### 20.4. Diagnosing DST Gap/Overlap

```bash
curl -i -G 'http://localhost:8080/api/format/zone' \
  --data-urlencode 'local=2026-03-29T02:30:00' \
  --data-urlencode 'zone=Europe/Berlin'
```

Expect status `GAP` with empty offsets. With local `2026-10-25T02:30:00` in the same zone, expect `OVERLAP` with 2 offsets.

### 20.5. UTF-8 JSON and Localized Errors

```bash
curl -i -X POST 'http://localhost:8080/api/echo' \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: vi-VN' \
  --data-binary '{"name":"Đà Nẵng"}'
```

Expected:

```json
{"name":"Đà Nẵng"}
```

With `{"name":""}` and locale vi-VN, expect an error issue with `message="Vui lòng nhập tên"`.

### 20.6. Form with Unicode Characters

```bash
curl -i -X POST 'http://localhost:8080/api/form' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  -H 'Accept-Language: en-US' \
  --data-urlencode 'city=Đà Nẵng' \
  --data-urlencode 'day=06/11/2026' \
  --data-urlencode 'amount=1,234.50'
```

Expect `city="Đà Nẵng"`, `day="2026-11-06"`, and `amount="1234.5"`. If diacritics break in the form while JSON works, focus diagnosis on **form decoding/Servlet request encoding**; do not touch `@DateTimeFormat` or timezones.

## 21. Diagnostic Fallacies and Fixes

| Fallacy / wrong inference | Primary cause | How to verify |
| --- | --- | --- |
| "Vietnamese locale must format decimals with a comma" | Locale `vi` has specific formatting rules; never guess from language labels | Test with formatter and exact locale |
| "`Accept-Language: vi` fixes UTF-8 bugs" | Charset differs from locale | Compare HTTP bytes and decoded Strings |
| "`@JsonFormat` fixes query parameter dates" | Jackson applies only to JSON path | Test `@RequestParam` + `@DateTimeFormat` |
| "`@DateTimeFormat` fixes JSON date fields" | JSON goes through Jackson | Check `@JsonFormat`/ObjectMapper |
| "Every ISO date is accepted by `@DateTimeFormat` pattern=dd/MM/yyyy" | Pattern is an explicit contract | Assert type mismatch with ISO input |
| "Locale automatically selects Asia/Ho_Chi_Minh" | Locale carries no timezone | Pass explicit ZoneId |
| "Offset +01:00 is always Berlin time" | Berlin observes DST | Check `getValidOffsets` at that timestamp |
| "`LocalDateTime` identifies an instant" | Lacks ZoneId/offset; gap/overlap | Use `Instant`/`OffsetDateTime` or `ZoneRules` |
| "`LocalDate` needs +7 hours added" | `LocalDate` has no time/zone | Convert only if business defines start-of-day zone |
| "Just change the server default timezone for convenience" | Environment-dependent, breaks tests | Inject `Clock`/`ZoneId` |
| "Formatter parse error is a Jakarta Validation error" | Converter/binder failed before validator | Check `FieldError.isBindingFailure()` |
| "Testing `.param` Unicode tests wire charset" | Param is already a Java String | Test content bytes/real server |
| "Testing only status 400 is enough" | Fails to pinpoint category/field/message | Assert stable codes and exception class as needed |
| "Parsing a number in the wrong locale always throws" | Parsers may be lenient or return another number | Test semantic numeric value + strict parser if needed |
| "`spring.jackson.time-zone` changes all Java Time types" | JavaTimeModule/annotations have distinct semantics | Test wire JSON per type |
| "`MessageSource` works with only `messages_vi.properties`" | Boot auto-config convention normally needs base bundle | Provide `messages.properties` + locale files |
| "Garbled accents = DB fault" | Multiple encoding boundaries exist | Trace bytes→String→response step by step |
| "DST gaps/overlaps are always handled automatically" | Business must pick a policy | Check `ZoneRules.getValidOffsets` |
| "`Date`/`Calendar` is the only timezone solution" | `java.time` provides clearer types | Pick `LocalDate`/`OffsetDateTime`/`Instant` properly |
| "Changing JVM default locale in parallel tests is safe" | Global mutable state | Use `MockMvc.locale` / explicit `Locale` / `Clock` |

## 22. QA Checklist When Changing Format, Locale, or Time Zone

1. Identify the data path: query/form `ConversionService` or JSON Jackson.
2. Record the exact target Java type and active annotations.
3. Verify the request locale is chosen via header or test helper.
4. Check language/region and `LocaleResolver` precedence.
5. Check source file encoding, request body encoding, and response content encoding.
6. For forms, test URI percent-encoding and real character encoding when needed.
7. For JSON, test raw UTF-8 bytes via `content(byte[])`.
8. For messages, verify the base bundle, locale-specific bundle, and encoding.
9. For `@NumberFormat`, assert **numeric meaning**, not merely HTTP 200.
10. For dates, assert canonical `LocalDate` `yyyy-MM-dd`, not just parser success.
11. For `@JsonFormat`, test JSON separately; do not infer from form tests.
12. For `@DateTimeFormat`, test queries/forms separately; do not infer from JSON tests.
13. If strict date validity is required, specify the resolver style/algorithm.
14. For `OffsetDateTime`, test two timestamps with different offsets representing the same instant.
15. For local + zone, test normal time, DST gap, and DST overlap.
16. Use a business `ZoneId`; avoid `ZoneId.systemDefault()` at boundaries.
17. Avoid `Locale.setDefault()`/`TimeZone.setDefault()` in parallel tests.
18. Inject `Clock` so tests do not depend on current date/time.
19. Map type mismatches to stable error codes without exposing raw values.
20. For form `BindingResult`, distinguish binding failures from constraints.
21. For Bean Validation, assert localized messages under explicit locales.
22. When upgrading Spring Boot/Jackson/Hibernate/TZDB, re-run regression tests.
23. Verify which formats browser input types (`date`/`datetime-local`/`number`) actually submit.
24. In logs, record safe metadata about locale/charset/pattern/zone and request ID.
25. For public APIs, document format/zone contracts in OpenAPI and SDK docs.

## 23. Self-Practice Exercises

1. Add an endpoint accepting `@DateTimeFormat(iso=DATE) LocalDate`; verify `2026-11-06` succeeds and `06/11/2026` fails.
2. Change `dd/MM/yyyy` to `MM/dd/yyyy` and compare the same input `06/11/2026`; explain the difference.
3. Use `ResolverStyle.STRICT` + `dd/MM/uuuu` to reject `31/02/2026`.
4. Send a de-DE request with `amount=1.234,50` and en-US with `amount=1,234.50`; compare semantic `BigDecimal` values.
5. Try numeric text in the wrong locale; do not assume an exception is thrown—inspect the full parsed result.
6. Add a `@JsonFormat(pattern="dd/MM/yyyy") LocalDate` in a JSON DTO and compare with query `@DateTimeFormat`.
7. Add an XML/form endpoint permitting only UTF-8, and test raw percent-encoded Vietnamese text against a real server.
8. In tests, use `Locale.forLanguageTag("vi-VN")` and `Locale.ENGLISH`; the message must change while the error code stays stable.
9. Change `spring.messages.basename` to a different bundle name; test missing keys for diagnosis.
10. Remove `spring.messages.encoding=UTF-8` in a test profile and investigate whether behavior still holds on the current Boot version.
11. Add timestamps `2026-11-06T09:30:00+07:00` and `2026-11-06T02:30:00Z`; verify equal `Instant`.
12. Pick Berlin `ZoneId` for `2026-03-29T02:30`, returning `GAP` rather than silently shifting to 03:30.
13. Pick Berlin `ZoneId` for `2026-10-25T02:30`, prompting the client to pick an offset during overlap.
14. Inject `Clock.fixed` into "before today" checks so tests are not flaky.
15. Compare `LocalDateTime.now(Clock.systemUTC())` with `LocalDateTime.now(Clock.system(ZoneId.of("Asia/Ho_Chi_Minh")))` at the same instant.
16. Add a `@NumberFormat(style=CURRENCY)` endpoint and test currency symbols and locales with/without decimal commas.
17. Add `@Past`/`@Future` with Jakarta Validation's `ClockProvider` when controlling current time.
18. Simulate a mojibake message from a wrongly encoded resource file and diagnose where bytes were misdecoded.
19. Send a wrong `Content-Type` (`text/plain` to a JSON endpoint) and distinguish HTTP 415 from JSON 400.
20. Add correlation IDs and structured safe logs recording category, locale, and zone without logging raw request bodies.

**Conclusion:** Never apply a single global tweak to fix all "formatting bugs." **Locale** picks language/display conventions; **charset** governs Unicode over bytes; **pattern** defines date/number syntax; **time zone/offset** determines instants and handles DST. To diagnose Spring MVC accurately, identify whether the request flows through `ConversionService/WebDataBinder` or Jackson, test each layer separately, and assert the **semantic value** after parsing. Use `Instant`/`OffsetDateTime`/`ZoneId` in their proper roles, explicit locale/encoding, and MockMvc/JUnit regression suites.

## 24. Official References

- [Spring Framework 6.2 — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [Spring Framework 6.2 — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html)
- [Spring Framework 6.2 — DateTimeFormat annotation](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html)
- [Spring Framework 6.2 — NumberFormat annotation](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/annotation/NumberFormat.html)
- [Spring Framework 6.2 — MVC Locale](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/localeresolver.html)
- [Spring Framework 6.2 — Data Binding / @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring Boot 3.5 — Internationalization](https://docs.spring.io/spring-boot/3.5/reference/features/internationalization.html)
- [Spring Boot 3.5 — Servlet Encoding](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot 3.5 — Testing with MockMvc](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Java 17 — java.time package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html)
- [Java 17 — ZoneRules.getValidOffsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html)
- [Java 17 — DateTimeFormatter and ResolverStyle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Jackson — JsonFormat annotation](https://fasterxml.github.io/jackson-annotations/javadoc/2.15/com/fasterxml/jackson/annotation/JsonFormat.html)
- [Jakarta Validation 3.0 — Message Interpolation](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)