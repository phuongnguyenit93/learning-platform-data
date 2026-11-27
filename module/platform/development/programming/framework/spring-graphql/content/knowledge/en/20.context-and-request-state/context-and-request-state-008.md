# Locale and timezone

In Spring for GraphQL, **Locale** and **timezone** are two important pieces of request state when an API needs to return messages, dates/times, or content tailored to the user. Locale governs language and cultural formatting rules; timezone governs how an instant in time is converted into local time.

These two values are typically obtained from the HTTP request or preferences stored in the user's profile, and then placed into **GraphQLContext** so resolvers within the same execution can use them. This lesson explains how to distinguish `Locale` from `ZoneId`, read the `Accept-Language` header, accept timezone preferences, populate context via `WebGraphQlInterceptor`, access them in resolvers, and test per-request behavior.

## 1. Distinguishing Locale and timezone

Locale and timezone are related when displaying data, yet they represent two different concepts.

**Locale** describes the language and cultural conventions used when presenting data, for example:

- Display language for messages.
- Order and formatting of day, month, and year.
- Thousands and decimal separators.
- Pluralization or text formatting rules.
- Language-specific string sorting and collation.

Java represents a locale with `java.util.Locale`, such as `vi-VN`, `en-US`, or `ja-JP`.

**Timezone** determines the local time corresponding to a point in time, including UTC offset rules and daylight saving time changes if applicable in the region. Java represents a timezone with `java.time.ZoneId`, such as `Asia/Ho_Chi_Minh`, `Europe/Paris`, or `America/Los_Angeles`.

Someone may use the `vi-VN` locale while living in `America/Los_Angeles`. Locale does not automatically determine timezone.

| Concept | Java type | Example | Effect |
| --- | --- | --- | --- |
| Language and presentation conventions | Locale | vi-VN | Text, dates, numbers, and cultural formatting. |
| Timezone | ZoneId | Asia/Ho_Chi_Minh | Local time and DST rules. |
| Absolute point in time | Instant | 2026-11-20T04:00:00Z | A unique instant on the UTC timeline. |

Do not infer timezone solely from `Locale` or the country in a locale. A single country can span multiple timezones, and users may choose a language different from where they currently reside.

## 2. Locale and timezone are request preferences

A GraphQL operation can return many objects and many fields. When the entire response needs to share the same language and timezone, those values belong in request context.

Example HTTP request sent by a client:

~~~http
POST /graphql
Accept: application/json
Accept-Language: vi-VN, en;q=0.8
X-Time-Zone: Asia/Ho_Chi_Minh
Content-Type: application/json
~~~

In this request:

- `Accept-Language` is the standard HTTP header for clients to state preferred languages.
- `X-Time-Zone` is an application-defined header for passing timezone preference; it is not a mandatory standard HTTP timezone header.
- The server must validate values before using them.
- If missing or unsupported, the server applies a documented fallback policy.

Timezone may also come from the authenticated user's profile. Applications should define a clear precedence order, such as: valid user preference, then accepted header, and finally UTC. The examples in this lesson use headers to illustrate putting preferences into request state.

There is no need to add `locale` and `timezone` as arguments on every GraphQL field if they apply uniformly across the request. If a field genuinely needs to let the client choose a separate display format, you can design an explicit argument for that field.

## 3. Why put preferences into GraphQLContext?

`GraphQLContext` is where context data shared during a single GraphQL execution is stored. Resolvers can read the context to obtain locale, timezone, principal, or other server-determined request information.

Overall processing flow:

~~~mermaid
flowchart TD
    A["HTTP GraphQL request"] --> B["Read Accept-Language"]
    A --> C["Read timezone preference"]
    B --> D["Validate and select Locale"]
    C --> E["Validate and select ZoneId"]
    D --> F["WebGraphQlInterceptor"]
    E --> F
    F --> G["Execution's GraphQLContext"]
    G --> H["Query / Schema / Batch resolver"]
    H --> I["Localized response"]
~~~

`GraphQLContext` enables resolvers to receive the same set of preferences without passing them through every argument in the schema.

Key benefits:

- Data is bound to the current GraphQL execution.
- Multiple resolvers can read the same value.
- Asynchronous resolvers do not need to rely on thread-locals to find preferences.
- Does not alter the SDL schema or client operations.
- Easy to test requests with different headers.

`GraphQLContext` is not a place for global application state. Never put a request's `Locale` or `ZoneId` into a mutable field of a singleton bean, because concurrent requests can overwrite each other's data.

## 4. Resolving Locale from Accept-Language

The `Accept-Language` header can contain one or more languages with priority weights `q`.

Example:

~~~http
Accept-Language: vi-VN, en-US;q=0.9, ja-JP;q=0.7
~~~

The server should not simply take the first string and use it directly. It should match against the list of locales the application actually supports.

Java provides `Locale.LanguageRange.parse` to parse the priority list and `Locale.lookup` to find a matching locale in the supported list.

~~~java
import java.util.List;
import java.util.Locale;
import org.springframework.stereotype.Component;

@Component
public class RequestLocaleResolver {

    private static final Locale DEFAULT_LOCALE =
            Locale.forLanguageTag("vi-VN");

    private static final List<Locale> SUPPORTED_LOCALES = List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("ja-JP")
    );

    public Locale resolve(String acceptLanguage) {
        if (acceptLanguage == null || acceptLanguage.isBlank()) {
            return DEFAULT_LOCALE;
        }

        try {
            List<Locale.LanguageRange> ranges =
                    Locale.LanguageRange.parse(acceptLanguage);

            Locale match = Locale.lookup(ranges, SUPPORTED_LOCALES);
            return match != null ? match : DEFAULT_LOCALE;
        }
        catch (IllegalArgumentException exception) {
            return DEFAULT_LOCALE;
        }
    }
}
~~~

This example:

- Only returns a locale present in `SUPPORTED_LOCALES`.
- Respects priority order and weights in the header.
- Uses `vi-VN` if the header is missing, invalid, or contains no supported language.
- Does not construct arbitrary locales from any string sent by the client.

Fallback behavior should be consistent across endpoints. If your application has a different default locale, change `DEFAULT_LOCALE` according to product policy.

### Locale tags and normalization

Prefer BCP 47 language tags such as `vi-VN`, `en-US`, `fr-FR`. Java can convert a tag string into a `Locale`:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
~~~

Avoid splitting strings manually by hyphens to extract language/country, because language tags may include scripts, regions, and extensions. Use Java's standard APIs and a list of supported locales.

## 5. Reading timezone preference and validating ZoneId

HTTP does not define a universal timezone header that every application must use. An application may define its own header such as `X-Time-Zone`, or retrieve the timezone from the user profile.

Prefer IANA region names such as:

- `Asia/Ho_Chi_Minh`
- `Europe/London`
- `America/New_York`
- `Australia/Sydney`

Region names contain historical and regional UTC offset transition rules. Storing only a fixed offset such as `+07:00` cannot represent DST rules of another region.

Java can validate a timezone with `ZoneId.of`:

~~~java
import java.time.DateTimeException;
import java.time.ZoneId;
import org.springframework.stereotype.Component;

@Component
public class TimeZoneResolver {

    private static final ZoneId DEFAULT_ZONE = ZoneId.of("UTC");

    public ZoneId resolve(String timeZoneHeader) {
        if (timeZoneHeader == null || timeZoneHeader.isBlank()) {
            return DEFAULT_ZONE;
        }

        try {
            return ZoneId.of(timeZoneHeader);
        }
        catch (DateTimeException exception) {
            return DEFAULT_ZONE;
        }
    }
}
~~~

The example uses UTC as a fallback so machine-readable data has a consistent baseline. An application targeting a specific region may choose a different default as long as the rule is documented.

If the product only accepts IANA region IDs, you can also check `ZoneId.getAvailableZoneIds()` or use a dedicated allowlist. If fixed offsets like `+07:00` are permitted, explicitly document that as a supported option.

Do not use `TimeZone.getDefault()` or the server's default timezone as the user's preference. Results can vary depending on the deployment environment.

## 6. Putting Locale and ZoneId into GraphQLContext

For HTTP transport, `WebGraphQlInterceptor` is the right place to read request headers and add data to `ExecutionInput`.

Example interceptor:

~~~java
package com.example.catalog.graphql;

import java.time.ZoneId;
import java.util.Locale;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class RequestPreferencesInterceptor
        implements WebGraphQlInterceptor {

    private final RequestLocaleResolver localeResolver;
    private final TimeZoneResolver timeZoneResolver;

    public RequestPreferencesInterceptor(
            RequestLocaleResolver localeResolver,
            TimeZoneResolver timeZoneResolver) {
        this.localeResolver = localeResolver;
        this.timeZoneResolver = timeZoneResolver;
    }

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String acceptLanguage =
                request.getHeaders().getFirst(HttpHeaders.ACCEPT_LANGUAGE);

        String timeZoneHeader =
                request.getHeaders().getFirst("X-Time-Zone");

        Locale locale = localeResolver.resolve(acceptLanguage);
        ZoneId zoneId = timeZoneResolver.resolve(timeZoneHeader);

        request.configureExecutionInput((executionInput, builder) ->
                builder.graphQLContext(contextBuilder -> {
                    contextBuilder.put("requestLocale", locale);
                    contextBuilder.put("requestZoneId", zoneId);
                }).build()
        );

        return chain.next(request);
    }
}
~~~

The interceptor performs these steps:

1. Reads `Accept-Language` and the timezone header.
2. Calls resolvers to validate and choose valid values.
3. Places `Locale` and `ZoneId` into the execution's `GraphQLContext`.
4. Forwards the request to the GraphQL engine.

`WebGraphQlInterceptor` is integrated with HTTP transport by Spring for GraphQL. Register the interceptor as a Spring bean so the framework applies it to requests. If the application uses WebSocket, design how preferences are received via WebSocket interceptor/connection initialization mechanisms; do not assume an HTTP interceptor handles every message over WebSocket.

The keys `requestLocale` and `requestZoneId` are application-defined names. Use constants or a centralized keys class if multiple components read them, to avoid typos.

## 7. Reading request state in resolvers with @ContextValue

Spring for GraphQL provides `@ContextValue` to inject values from `GraphQLContext` into method parameters.

Example schema:

~~~graphql
scalar DateTime

type Query {
    events: [Event!]!
}

type Event {
    id: ID!
    startsAt: DateTime!
    startsAtLabel: String!
}
~~~

Here `DateTime` is a custom scalar that must be registered separately; it represents a point in time per the machine-readable contract. The `startsAtLabel` field is a display string formatted according to the request's locale and timezone.

Java model:

~~~java
import java.time.Instant;

public record Event(
        String id,
        Instant startsAt
) {
}
~~~

Resolver:

~~~java
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class EventController {

    @SchemaMapping(typeName = "Event", field = "startsAtLabel")
    public String startsAtLabel(
            Event event,
            @ContextValue("requestLocale") Locale locale,
            @ContextValue("requestZoneId") ZoneId zoneId) {

        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)
                        .withLocale(locale)
                        .withZone(zoneId);

        return formatter.format(event.startsAt());
    }
}
~~~

`@ContextValue` retrieves the objects placed into `GraphQLContext` by the interceptor. The resolver does not need to re-read HTTP headers or parse locale/timezone itself.

If a key might be absent, you can mark the context parameter as optional according to your Spring for GraphQL version's annotation API, or use `DataFetchingEnvironment` to read context and apply an explicit fallback. In this example, the interceptor always sets both keys, so the resolver can require them.

### Reading directly via DataFetchingEnvironment

When a resolver needs multiple context values or wants to check key presence, it can accept `DataFetchingEnvironment`:

~~~java
import graphql.schema.DataFetchingEnvironment;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

@SchemaMapping(typeName = "Event", field = "startsAtLabel")
public String startsAtLabel(
        Event event,
        DataFetchingEnvironment environment) {

    Locale locale =
            environment.getGraphQlContext().get("requestLocale");

    ZoneId zoneId =
            environment.getGraphQlContext().get("requestZoneId");

    return DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)
            .withLocale(locale)
            .withZone(zoneId)
            .format(event.startsAt());
}
~~~

Both approaches serve similar goals. `@ContextValue` works well when the method only needs a few known values; `DataFetchingEnvironment` is useful when reading context dynamically or accessing additional execution metadata.

## 8. Using Locale to format text and numbers

Locale does not affect dates alone. Java includes locale-aware formatters for numbers and currency.

Formatting numbers:

~~~java
import java.text.NumberFormat;

NumberFormat numberFormat = NumberFormat.getNumberInstance(locale);
String formattedCount = numberFormat.format(1234567.89);
~~~

Formatting currency:

~~~java
import java.text.NumberFormat;
import java.util.Currency;

NumberFormat currencyFormat =
        NumberFormat.getCurrencyInstance(locale);

currencyFormat.setCurrency(Currency.getInstance("VND"));
String formattedPrice = currencyFormat.format(amount);
~~~

Do not infer currency from `Locale` alone. An `en-US` locale does not mean every monetary value is USD; currency is distinct business data. Obtain the currency from the product, transaction, or business configuration, and use `Locale` only for formatting.

For translated messages, you can use Spring's `MessageSource`:

~~~java
String message = messageSource.getMessage(
        "event.notFound",
        new Object[] { eventId },
        locale
);
~~~

Resource bundles can contain translations such as `messages_vi.properties`, `messages_en.properties`, and `messages_ja.properties`. Using the `Locale` from request context lets the same service return messages in the client's chosen language.

Do not manually concatenate message strings from English or Vietnamese fragments inside resolvers. Placing messages in resource bundles keeps translation and maintenance centralized.

## 9. Using ZoneId to convert instants

Store and transmit absolute points in time using `Instant` or an explicit offset type. Convert to local time only when presenting to users.

Example:

~~~java
Instant startsAt = Instant.parse("2026-11-20T04:00:00Z");

ZonedDateTime localDateTime = startsAt.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);
~~~

`Instant` represents a point on the UTC timeline. `ZoneId` applies the region's rules to compute local time.

With `DateTimeFormatter`, you can format an `Instant` directly using `withZone`:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)
                .withLocale(Locale.forLanguageTag("vi-VN"))
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

String label = formatter.format(startsAt);
~~~

Do not store local wall-clock times as `LocalDateTime` without storing a timezone or offset if the data represents an event occurring at a specific instant. When switching timezones or handling DST, a local wall-clock time may not uniquely identify an instant.

For scheduled appointments defined in local time, store both the business-appropriate timezone rules, such as `LocalDateTime` alongside `ZoneId`, and define exact handling for gaps or overlaps during DST transitions.

## 10. Keeping API data stable, separate from display strings

Do not alter machine-readable values based on locale if clients need them for storage, comparison, or calculation.

Example schema:

~~~graphql
scalar DateTime

type Event {
    id: ID!
    startsAt: DateTime!
    startsAtLabel: String!
}
~~~

- `startsAt` returns the instant in the custom scalar's standard format, such as ISO-8601 UTC.
- `startsAtLabel` returns a presentation string formatted using the request's locale and timezone.

Clients can use `startsAt` for sorting, persistence, or synchronization. The UI can use `startsAtLabel` to display to users.

If there is only one `startsAt` field and the server changes its string format by timezone and locale, clients struggle to compare and cache results. Separating the two concerns keeps the API cleaner.

Locale/timezone can cause responses to differ even when the GraphQL document and variables are identical. If responses are cached at an HTTP gateway or CDN, the cache key must account for preferences that affect the response. For HTTP caching, consider `Vary: Accept-Language, X-Time-Zone` if those headers alter the representation.

## 11. Request scope and safety during asynchronous execution

GraphQL can resolve multiple fields in parallel. Resolvers may run on different threads or continue via futures/reactive pipelines.

Do not rely solely on `ThreadLocal` or `LocaleContextHolder` to carry request preferences across every asynchronous step. Execution threads can change, whereas explicit context is bound to the GraphQL execution and can be read directly by resolvers.

Some principles:

- Put `Locale` and `ZoneId` into `GraphQLContext` at the start of the request.
- Treat these values as immutable preferences throughout the execution.
- Never write request preferences into fields of singleton controllers/services.
- Never use static mutable variables to hold the current locale/timezone.
- For batch loaders, use the execution's context when needed; never hold context in shared variables.
- If a resolver needs a different preference for a specific field, pass it as an argument or design explicit local context instead of mutating the shared request context.

`GraphQLContext` suits request-wide data. If data only has meaning inside one branch of the selection tree, consider GraphQL Java's local context instead of putting everything into request-wide context.

## 12. Locale/timezone and DataLoader

DataLoaders cache by key within a request scope. If a batch loader returns data already formatted by locale or timezone, ensure those preferences do not change across calls to the same DataLoader within the request.

Typically, locale and timezone are fixed in `GraphQLContext` for the entire execution, so they can be read inside a batch loader via the batch environment/context.

If a batch result depends on a parameter that can vary per field invocation, that parameter must be included in a composite key or an appropriate context mechanism. For example, for the same `Event` ID where the client requests formatting in two different timezones, you cannot cache a single formatted string keyed solely by `Event` ID.

Better yet, batch loaders should return canonical domain data such as `Instant`, while resolvers format according to locale/timezone. This reduces the risk of caching presentation strings in the wrong context.

## 13. Testing per-request locale and timezone

Test both preference resolution and GraphQL context propagation.

### Testing RequestLocaleResolver

~~~java
@Test
void choosesFirstSupportedLocaleFromAcceptLanguage() {
    RequestLocaleResolver resolver = new RequestLocaleResolver();

    Locale locale = resolver.resolve("vi-VN, en-US;q=0.8");

    assertThat(locale).isEqualTo(Locale.forLanguageTag("vi-VN"));
}
~~~

Other cases:

- Missing header.
- Blank header.
- Malformed header syntax.
- Locale not in the supported list.
- Multiple locales with different `q` weights.
- Wildcard `*`.

### Testing TimeZoneResolver

~~~java
@Test
void fallsBackToUtcForInvalidTimeZone() {
    TimeZoneResolver resolver = new TimeZoneResolver();

    ZoneId zoneId = resolver.resolve("Invalid/Zone");

    assertThat(zoneId).isEqualTo(ZoneId.of("UTC"));
}
~~~

Also test valid timezones, empty values, and regions with DST to ensure the resolver uses `ZoneId` instead of hardcoded offsets.

### Testing GraphQL over HTTP

Use `WebTestClient` or `HttpGraphQlTester` to send requests with different headers:

~~~http
Accept-Language: vi-VN
X-Time-Zone: Asia/Ho_Chi_Minh
~~~

Then send a second request:

~~~http
Accept-Language: en-US
X-Time-Zone: America/Los_Angeles
~~~

The same GraphQL document can return different `startsAtLabel` values, while `startsAt` keeps the standard ISO-8601 value. Such tests confirm that the interceptor sets a distinct context per request and does not leak preferences across executions.

Also verify that resolvers/services are not invoked if a request is rejected by header policy, or that fallback behavior applies properly if the application chooses a fallback policy.

## 14. Common errors

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| Response always uses the default language | Not reading `Accept-Language`, or client locale is not in supported list. | Check interceptor, supported locales list, and fallback. |
| Locale priority is wrong | Taking only the beginning of the header or ignoring `q` weights. | Use `Locale.LanguageRange.parse` and `Locale.lookup`. |
| Invalid timezone causes resolver error | Passing client-sent string directly to `ZoneId.of`. | Validate and apply fallback or return a request error per policy. |
| Displayed time is offset from user's time | Using server timezone or fixed offset. | Use `ZoneId` from preference and format from `Instant`. |
| Locale mistaken for timezone | Assuming language/country uniquely determines a timezone. | Store `Locale` and `ZoneId` as two separate values. |
| Async resolver uses wrong preference | Relying on thread-local not propagated to other threads. | Read explicitly from `GraphQLContext`. |
| Concurrent requests affect each other | Storing preferences in mutable fields of a singleton. | Put data into per-request context. |
| Client cannot compare timestamps | Server returns localized date/time string in a machine-readable field. | Return standard `Instant`/`DateTime` and a separate label field. |
| Cache returns wrong format | Cache key ignores headers that change the response. | Include preferences in cache key or configure `Vary` properly. |
| Currency does not match locale | Inferring currency from `Locale`. | Take currency from business data, use `Locale` only for formatting. |

## 15. Workflow for implementing Locale and timezone

When adding request preferences to a GraphQL API, follow this sequence:

1. Identify which responses need localization.
2. Decide whether `Locale` and timezone come from headers, user profiles, or both.
3. Choose the supported `Locale` list and fallback.
4. Choose the timezone convention, preferring IANA `ZoneId`, and define the fallback.
5. Write dedicated resolvers to parse and validate each preference.
6. Register a `WebGraphQlInterceptor` to place values into `GraphQLContext`.
7. Use `@ContextValue` or `DataFetchingEnvironment` in resolvers.
8. Use `Locale` for message/number/date formatting.
9. Use `ZoneId` to convert `Instant` into local time.
10. Keep machine-readable time fields in standard format; split display fields if needed.
11. Check async resolvers, DataLoaders, and request isolation.
12. Test multiple headers, fallbacks, invalid timezones, and cache behavior.

## 16. Key takeaways

- `Locale` controls language and cultural formatting rules; `ZoneId` controls local time and DST rules.
- `Accept-Language` is a standard header; timezone headers like `X-Time-Zone` are application conventions.
- Only accept supported `Locale` values and validate timezones before use.
- Use `WebGraphQlInterceptor` to place preferences into the HTTP execution's `GraphQLContext`.
- Use `@ContextValue` or `DataFetchingEnvironment` to read context in resolvers.
- `GraphQLContext` is request state; never store preferences in singleton mutable fields or static variables.
- Store points in time as `Instant`/UTC; convert to `ZoneId` only for presentation.
- Never infer currency from `Locale`, and never infer timezone from language.
- Separate canonical timestamps from localized display strings.
- Response caching must account for `Locale`/timezone if those values alter the representation.

Locale and timezone enable a GraphQL API to present data tailored to each user without altering the core data contract. By validating preferences at the start of the request, storing them in `GraphQLContext`, and reading them explicitly in resolvers, a Spring for GraphQL application can handle localization consistently even when fields execute asynchronously.
