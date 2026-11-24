# Type Conversion and Date/Time Formatting

In Spring Boot, clients send data via paths, query strings, headers, forms, or JSON bodies. Spring MVC must convert HTTP representations into Java types such as `long`, `boolean`, `BigDecimal`, `LocalDate`, `OffsetDateTime`, or an application-defined value object. When handling dates and times, correctness depends not only on the pattern but also on the **temporal type, ISO 8601, locale, UTC offset, and timezone**.

This lesson belongs to the **Request Data** group and uses **Spring Boot 3.3.x, Spring MVC on the Servlet stack, and Java 17+**. The focus is on how Spring binds request parameters, how to use `@DateTimeFormat`, how to configure formatters/converters, and how this differs from Jackson when reading JSON.

## 1. Conversion, Formatting, and JSON Deserialization

A request:

~~~http
GET /api/events/42?day=2026-11-07&active=true HTTP/1.1
Host: localhost:8080
~~~

carries path/query values as text. A controller can declare:

~~~java
@GetMapping("/api/events/{id}")
EventView find(
    @PathVariable long id,
    @RequestParam("day")
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate day,
    @RequestParam boolean active) {
    // ...
}
~~~

Spring MVC selects the handler, finds the argument resolvers, and uses `ConversionService`/formatters to turn `"42"` into `long`, `"2026-11-07"` into `LocalDate`, and `"true"` into `boolean`.

For the request:

~~~http
POST /api/events HTTP/1.1
Content-Type: application/json

{"day":"2026-11-07","active":true}
~~~

The JSON body is converted to a DTO by an `HttpMessageConverter` (typically the Jackson JSON converter). **The binding path for query/path/form data is not the same as the JSON `@RequestBody` path.**

| Mechanism | Typically used for | Primary tools |
|---|---|---|
| Type conversion | Request string -> Java type | `ConversionService`, `Converter` |
| Field formatting | Formatted/localized string -> date, number | `Formatter`, `@DateTimeFormat`, `@NumberFormat` |
| HTTP message conversion | JSON/XML/text body -> object | `HttpMessageConverter` and Jackson/codecs |

Conceptual diagram:

~~~text
HTTP request
    |
DispatcherServlet -> HandlerMapping -> HandlerAdapter
    |
    +-- Query/path/form/header -> ArgumentResolver
    |                             -> WebDataBinder
    |                             -> ConversionService / Formatter
    |
    +-- JSON @RequestBody -----> HttpMessageConverter / Jackson
    |
Java arguments / DTO
    |
Controller -> service
~~~

If a converter/formatter cannot parse the input, the error may be handled **before the controller method is invoked**. For typical argument binding failures, Spring MVC returns **400 Bad Request**.

## 2. Converting Numbers, Booleans, and Enums

Spring provides many built-in converters. Example:

~~~java
@GetMapping("/api/search")
String search(
        @RequestParam int page,
        @RequestParam(defaultValue = "20") int size,
        @RequestParam(defaultValue = "false") boolean archived) {
    return "page=" + page
        + ",size=" + size
        + ",archived=" + archived;
}
~~~

The request `GET /api/search?page=2&size=10&archived=true` produces body:

~~~text
page=2,size=10,archived=true
~~~

If `page=abc` is sent, it cannot be converted to `int`; having `defaultValue` on `size` does not mean every invalid input falls back to a default. For `enum` types, parsing is normally based on enum constant names; if an API must accept aliases or lowercase strings, register a dedicated converter and test it.

For monetary amounts, consider `BigDecimal` to avoid binary floating-point rounding errors. You still must specify the text syntax; decimal separators `,` and `.` carry different meanings across locales.

## 3. Temporal Types in java.time

| Java type | Information carried | Example |
|---|---|---|
| `LocalDate` | Calendar date without time/zone | `2026-11-07` |
| `LocalTime` | Time of day without date/zone | `09:30:00` |
| `LocalDateTime` | Date + time, **without an offset** | `2026-11-07T09:30:00` |
| `OffsetDateTime` | Date + time + UTC offset | `2026-11-07T09:30:00+07:00` |
| `ZonedDateTime` | Date + time + zone/region | `2026-11-07T09:30+07:00[Asia/Ho_Chi_Minh]` |
| `Instant` | Absolute point on the UTC timeline | `2026-11-07T02:30:00Z` |
| `Duration` | Length in seconds/nanoseconds | `PT15M` |
| `Period` | Span in calendar years/months/days | `P1M` |

Choosing the right type is part of the API contract. `LocalDateTime` cannot identify an exact instant on its own because it lacks a timezone. `OffsetDateTime` preserves the offset; `ZonedDateTime` preserves a regional zone and may need to account for daylight saving time rules. `LocalDate` is a calendar date and does not automatically equal `00:00 UTC`.

Use `LocalDate` for birthdates or booking dates; `Instant` for audit timestamps; `OffsetDateTime` when clients send timestamps with an offset; and `ZonedDateTime` when business logic depends on regional calendar rules.

## 4. @DateTimeFormat(iso = ...) for Text Request Parameters

`@DateTimeFormat` resides in `org.springframework.format.annotation`. Explicit API declaration:

~~~java
@GetMapping("/api/reports")
String report(
        @RequestParam("day")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate day) {
    return day.toString();
}
~~~

With `GET /api/reports?day=2026-11-07`, the result is:

~~~text
2026-11-07
~~~

Common options:
- `ISO.DATE`: ISO date.
- `ISO.TIME`: ISO time.
- `ISO.DATE_TIME`: ISO date-time.
- `ISO.NONE`: no explicit ISO format applied.

When an instant with an offset is needed, combine `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)` with `OffsetDateTime`. Specifying ISO on the parameter makes the API more predictable than relying on environment-dependent localized formats.

## 5. @DateTimeFormat(pattern = ...) for Custom Formats

Legacy clients might send `07/11/2026` instead of `2026-11-07`:

~~~java
@GetMapping("/api/reports/local")
String localReport(
        @RequestParam("day")
        @DateTimeFormat(pattern = "dd/MM/uuuu")
        LocalDate day) {
    return day.toString();
}
~~~

The request `GET /api/reports/local?day=07%2F11%2F2026` returns:

~~~text
2026-11-07
~~~

Easily confused pattern letters: `MM` is month while `mm` is minute; `HH` is 0–23 hour while `hh` is 1–12 hour; `dd` is day of month; `uuuu` is proleptic year and is generally preferred for strict parsing with `java.time`. A pattern without an offset/zone does not infer a timezone from the input.

Prefer ISO 8601 for machine-to-machine APIs. Custom patterns are appropriate only when the contract truly requires them or when serving a form in a format explicitly displayed to users.

## 6. Spring Boot Configuration: spring.mvc.format.*

Spring Boot 3.3 supports:

~~~yaml
spring:
  mvc:
    format:
      date: "dd/MM/uuuu"
      time: "HH:mm:ss"
      date-time: "dd/MM/uuuu HH:mm:ss"
~~~

| Property | Types documented by Boot 3.3 |
|---|---|
| `spring.mvc.format.date` | `java.util.Date`, `LocalDate` |
| `spring.mvc.format.time` | `LocalTime`, `OffsetTime` |
| `spring.mvc.format.date-time` | `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime` |

When unspecified, Boot 3.3 notes that default formatters use `DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)`, `ofLocalizedTime(SHORT)`, and `ofLocalizedDateTime(SHORT)` respectively. Localized formats depend on locale, so public APIs should never force callers to guess a default format.

Setting `date-time: "dd/MM/uuuu HH:mm:ss"` globally can break endpoints expecting `OffsetDateTime` because that pattern includes no offset. If different APIs have different contracts, apply `@DateTimeFormat` on individual parameters/fields instead of changing global default formatters.

In WebFlux, the properties are `spring.webflux.format.date`, `spring.webflux.format.time`, and `spring.webflux.format.date-time`, not the `spring.mvc.*` namespace.

## 7. MVC ConversionService Differs from Configuration Properties Binding

Spring Boot can bind:

~~~yaml
app:
  client:
    timeout: 15s
    cache-size: 16MB
~~~

to `Duration` and `DataSize` when using `@ConfigurationProperties`. However, Spring MVC has a **different ConversionService** from the application configuration binder: the specialized `Period`/`Duration`/`DataSize` converters used for property binding do not automatically share the same semantics in MVC.

Do not assume `@RequestParam Duration timeout` understands `15s` just because `application.yml` does. Similarly, `@DurationUnit` and `@DataSizeUnit` are not general-purpose solutions for HTTP parameter binding. If an API requires a duration, define its syntax (milliseconds or ISO duration), register the necessary converter, and test it.

## 8. Converters for Domain Value Types

Suppose an event code `EV-42` needs a strong type:

~~~java
record EventCode(String value) {}
~~~

Register a converter via `WebMvcConfigurer.addFormatters`:

~~~java
@Configuration(proxyBeanMethods = false)
class MvcConversionConfiguration implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(String.class, EventCode.class,
            text -> {
                if (!text.matches("EV-[0-9]+")) {
                    throw new IllegalArgumentException("Invalid event code");
                }
                return new EventCode(text);
            });
    }
}
~~~

This snippet has its imports in the complete example below. With `@PathVariable EventCode code`, MVC invokes the converter before the controller runs. The input `EV-42` becomes a value object; `wrong` fails conversion and typically produces HTTP 400.

A converter should handle representation and syntax, not query a database or call an HTTP service to verify whether a code exists. Resource lookup and authorization belong in the service/domain layer.

`Formatter<T>` is appropriate when parsing and printing depend on `Locale`:
- `parse(String, Locale)`: text to object.
- `print(T, Locale)`: object to text.

For example, `1,234.50` and `1.234,50` can represent the same number in different locales. `@NumberFormat` is a tool for fields needing rule-based number formatting. For public APIs, publish an explicit syntax rather than relying implicitly on the server locale.

## 9. Locale Is Not TimeZone

In MVC, `LocaleResolver` and the `Accept-Language` header can influence localized formatters. However, `Locale` represents language/cultural conventions and **does not determine a timezone**. An `Accept-Language: vi-VN` header does not mean the client sent `Asia/Ho_Chi_Minh` or a specific UTC offset.

If business logic requires a timezone, include `ZoneId` and offset/zone in the input data according to the contract. Never construct a timestamp from a `LocalDateTime` using the JVM's default timezone without documenting it to clients.

## 10. The + Sign in Offsets and URL-Encoding

These two strings represent the exact same instant:

~~~text
2026-11-07T09:30:00+07:00
2026-11-07T02:30:00Z
~~~

In a query parameter, `+` can be decoded as a space under form-style rules. Clients must not append raw `?at=2026-11-07T09:30:00+07:00` and expect every server to parse it properly.

URL-encode it instead:

~~~bash
curl -G "http://localhost:8080/api/events/42" \
  --data-urlencode "day=2026-11-07" \
  --data-urlencode "at=2026-11-07T09:30:00+07:00"
~~~

Example resulting URI containing `%2B`:

~~~text
/api/events/42?day=2026-11-07&at=2026-11-07T09%3A30%3A00%2B07%3A00
~~~

Inside a JSON body, a `+` within a JSON string does not need URL-encoding. With MockMvc `.param("at", "2026-11-07T09:30:00+07:00")`, the parameter value is passed directly.

Plain Java 17 example:

~~~java
import java.time.OffsetDateTime;

public class TimeDemo {
    public static void main(String[] args) {
        OffsetDateTime time =
            OffsetDateTime.parse("2026-11-07T09:30:00+07:00");
        System.out.println(time.toInstant());
    }
}
~~~

Running `javac TimeDemo.java` then `java TimeDemo` prints exact stdout:

~~~text
2026-11-07T02:30:00Z
~~~

## 11. JSON @RequestBody Uses Jackson, Not @DateTimeFormat

Body:

~~~json
{"day":"2026-11-07","at":"2026-11-07T09:30:00+07:00"}
~~~

DTO:

~~~java
record CreateEventRequest(LocalDate day, OffsetDateTime at) {}
~~~

Spring MVC uses `HttpMessageConverter`—normally Jackson with the Java Time module included in `spring-boot-starter-web`—to read JSON into the Java record.

When you need a custom format for a **JSON field**, use Jackson's `@JsonFormat` or `ObjectMapper` configuration:

~~~java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.LocalDate;

record SpecialBody(
    @JsonFormat(pattern = "dd/MM/uuuu") LocalDate day
) {}
~~~

`@JsonFormat` does not alter `@RequestParam LocalDate`; query `@DateTimeFormat` is not the primary configuration for JSON bodies. The `spring.jackson.date-format` property affects Jackson, but does not guarantee that all `java.time` serializers/deserializers adopt the same pattern: always test the actual `ObjectMapper` in use.

Syntactically invalid JSON or invalid date values may be rejected by Jackson, causing Spring MVC to return 400. If `Content-Type` is unsupported by the handler/converter, the status can be 415.

## 12. Complete Spring Boot Example

A Java 17+ / Spring Boot 3.3.x project requires:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is the dependencies block, not the entire Gradle file. Place the following code in `src/main/java/com/example/demo/RequestFormatApplication.java`:

~~~java
package com.example.demo;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class RequestFormatApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestFormatApplication.class, args);
    }
}

record EventCode(String value) {}
record EventView(long id, String day, String instant) {}
record CreateEventRequest(LocalDate day, OffsetDateTime at) {}

@RestController
@RequestMapping("/api/events")
class EventController {

    @GetMapping("/{id}")
    EventView find(
            @PathVariable long id,
            @RequestParam("day")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate day,
            @RequestParam("at")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            OffsetDateTime at) {

        return new EventView(
            id, day.toString(), at.toInstant().toString());
    }

    @GetMapping("/local")
    Map<String, String> local(
            @RequestParam("day")
            @DateTimeFormat(pattern = "dd/MM/uuuu")
            LocalDate day) {
        return Map.of("isoDay", day.toString());
    }

    @GetMapping("/by-code/{code}")
    Map<String, String> byCode(@PathVariable EventCode code) {
        return Map.of("code", code.value());
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    EventView create(@RequestBody CreateEventRequest body) {
        return new EventView(
            43L, body.day().toString(),
            body.at().toInstant().toString());
    }
}

@Configuration(proxyBeanMethods = false)
class MvcConversionConfiguration implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(String.class, EventCode.class,
            text -> {
                if (!text.matches("EV-[0-9]+")) {
                    throw new IllegalArgumentException(
                        "Invalid event code");
                }
                return new EventCode(text);
            });
    }
}
~~~

What the example demonstrates within clear boundaries:
1. `@PathVariable long id` converts path text into `long`.
2. `@DateTimeFormat(ISO.DATE)` parses an ISO date query parameter.
3. `@DateTimeFormat(ISO.DATE_TIME)` parses a query datetime with offset.
4. `pattern = "dd/MM/uuuu"` handles a dedicated legacy route.
5. A custom Converter turns a String code into `EventCode`.
6. `@RequestBody` uses Jackson to read JSON, not query formatters.
7. `EventView` formats the UTC instant as a String for deterministic demo output. POST returns a mock ID 43 and standard HTTP 200; real resource-creation APIs should return 201/Location as appropriate.

Run with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

GET ISO query with offset:

~~~bash
curl -G "http://localhost:8080/api/events/42" \
  --data-urlencode "day=2026-11-07" \
  --data-urlencode "at=2026-11-07T09:30:00+07:00"
~~~

Body:

~~~json
{"id":42,"day":"2026-11-07","instant":"2026-11-07T02:30:00Z"}
~~~

GET legacy pattern:

~~~bash
curl -G "http://localhost:8080/api/events/local" \
  --data-urlencode "day=07/11/2026"
~~~

Body:

~~~json
{"isoDay":"2026-11-07"}
~~~

GET custom code:

~~~bash
curl http://localhost:8080/api/events/by-code/EV-42
~~~

Body:

~~~json
{"code":"EV-42"}
~~~

POST JSON:

~~~bash
curl -X POST "http://localhost:8080/api/events" \
  -H "Content-Type: application/json" \
  -d '{"day":"2026-11-07","at":"2026-11-07T09:30:00+07:00"}'
~~~

Body:

~~~json
{"id":43,"day":"2026-11-07","instant":"2026-11-07T02:30:00Z"}
~~~

The `\` line continuation follows Bash syntax; on Windows PowerShell, use `curl.exe` with appropriate quoting.

## 13. MockMvc Tests to Verify Binding Timing

Create `src/test/java/com/example/demo/RequestFormatApplicationTest.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestFormatApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void isoDateAndOffset() throws Exception {
        mvc.perform(get("/api/events/{id}", 42)
                .param("day", "2026-11-07")
                .param("at", "2026-11-07T09:30:00+07:00"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.instant")
                .value("2026-11-07T02:30:00Z"));
    }

    @Test
    void customDatePattern() throws Exception {
        mvc.perform(get("/api/events/local")
                .param("day", "07/11/2026"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.isoDay").value("2026-11-07"));
    }

    @Test
    void customConverter() throws Exception {
        mvc.perform(get("/api/events/by-code/EV-42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("EV-42"));
    }

    @Test
    void invalidDateIs400() throws Exception {
        mvc.perform(get("/api/events/{id}", 42)
                .param("day", "2026-02-30")
                .param("at", "2026-11-07T09:30:00+07:00"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void jacksonForJsonBody() throws Exception {
        mvc.perform(post("/api/events")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"day\":\"2026-11-07\","
                    + "\"at\":\"2026-11-07T09:30:00+07:00\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.instant")
                .value("2026-11-07T02:30:00Z"));
    }
}
~~~

In a project configured with JUnit Platform, run:

~~~bash
./gradlew test
~~~

These tests pass through Spring MVC's argument resolvers, formatters, converters, and Jackson, rather than testing standalone Java parsers. Beyond this example, test nonexistent calendar dates, missing query parameters, invalid JSON formats, UTC offsets, and edge locales.

## 14. @ModelAttribute and @InitBinder

For multi-field forms or queries, `@ModelAttribute` can bind into a form object:

~~~java
public class SearchForm {
    private String keyword;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate from;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate to;

    // Getters/setters so Spring can bind bean properties.
}
~~~

This is an illustrative snippet; add accessors and imports to run standalone.

For controllers needing to restrict bindable fields:

~~~java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("keyword", "from", "to");
}
~~~

`@InitBinder` applies within the corresponding controller or advice scope. Never bind JPA entities containing sensitive fields directly from client input. DTOs and allowed fields help prevent over-posting, though they do not replace authorization or business validation.

**Binding differs from validation:** parsing text into a `LocalDate` is conversion; `@Valid`/`@NotBlank` belong to Bean Validation when an implementation is present; rules such as "cannot schedule past the allowed date" belong to the service/domain layer. A syntactically valid date can still be invalid per business rules.

## 15. Common Errors

| Symptom | Investigation direction |
|---|---|
| `day=2026-02-30` returns 400 | Date parser/formatter rejected an invalid calendar date |
| Query with `+07:00` offset parses incorrectly | Encode `+` as `%2B` |
| JSON date works but query date fails | Jackson differs from MVC formatters |
| Lowercase enum query fails | String -> enum conversion rules; consider a Converter |
| `@RequestParam Duration` does not understand `15s` | MVC ConversionService differs from the property binder |
| Changing global date-time broke another API | Global pattern applies broadly and may lack offset support |
| Request body has wrong Content-Type | May return 415 Unsupported Media Type |
| Accept header incompatible with output | May return 406 Not Acceptable |
| Input error occurs without controller logging | Argument resolution failed before invoking the handler |

Conversion failures are typically represented by Spring via `MethodArgumentTypeMismatchException`, `TypeMismatchException`, or corresponding binding exceptions; JSON bodies can raise `HttpMessageNotReadableException`. Return HTTP 400 for unparseable input, avoiding 200 or leaking stack traces. When a uniform error format is needed, consider `@RestControllerAdvice`/`ProblemDetail`.

## 16. Takeaways and References

- MVC query/path/form binding uses `ConversionService`, `Formatter`, and `@DateTimeFormat`.
- JSON `@RequestBody` uses `HttpMessageConverter` and Jackson; for custom JSON patterns, use `@JsonFormat`.
- `spring.mvc.format.date`, `time`, and `date-time` configure MVC formatters; `spring.webflux.format.date` belongs to WebFlux.
- `LocalDate` is a calendar date; `OffsetDateTime` includes an offset; `Instant` is an absolute point in time.
- Query offsets containing `+` must be URL-encoded.
- `WebMvcConfigurer.addFormatters` registers converters/formatters without taking full control of MVC via `@EnableWebMvc`.
- Test the full HTTP pipeline with MockMvc to confirm real requests parse as intended.

Official documentation:
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Framework — Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework — MVC Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Java 17 — java.time API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html)

**Conclusion:** An API handles input data reliably when it distinguishes query/path/form binding from JSON deserialization, chooses the right `java.time` types, publishes explicit ISO or custom formats, avoids guessing offsets/timezones, and uses HTTP tests to verify both valid and invalid inputs.
