# Date and DateTime Scalars

## Objectives

After this lesson, you will be able to:

- Distinguish calendar dates from instants on a timeline.
- Explain why GraphQL does not include built-in Date and DateTime scalars.
- Choose appropriate Java types such as `LocalDate`, `OffsetDateTime`, and `Instant`.
- Register Date and DateTime scalars in Spring for GraphQL.
- Map scalars into arguments, input objects, and return values.
- Design rules for timezones, formatting, nullability, and testing temporal data.

## 1. Why Are Date and DateTime Scalars Needed?

GraphQL defines five built-in scalars: `Int`, `Float`, `String`, `Boolean`, and `ID`. There is no standard built-in scalar named `Date` or `DateTime`.

If an API uses `String` for all temporal values, the schema cannot clearly express the format and meaning of the data. For example, both of the following values are strings, yet they represent two different concepts:

- `2026-11-20`: a calendar date, with no time of day or timezone.
- `2026-11-20T09:30:00+07:00`: a point in time with a time of day and a UTC offset.

By declaring custom scalars, the schema communicates data semantics more clearly:

~~~graphql
scalar Date
scalar DateTime

type Appointment {
  serviceDate: Date!
  startsAt: DateTime!
}
~~~

Clients know that `serviceDate` is a calendar date and `startsAt` is a point in time. The server can also validate the input format and convert values into the appropriate Java types.

The key point is that a scalar name does not define a format on its own. The application must choose a consistent convention for input parsing, output serialization, timezones, and invalid-data errors.

## 2. Distinguishing Date and DateTime

`Date` and `DateTime` should not be used interchangeably.

| Concept | Example | Appropriate Java Type | Has Timezone? |
|---|---|---|---|
| Calendar date | `2026-11-20` | `LocalDate` | No |
| Point in time with offset | `2026-11-20T09:30:00+07:00` | `OffsetDateTime` | Has UTC offset |
| Absolute point in time | `2026-11-20T02:30:00Z` | `Instant` | UTC |
| Local time without date | `09:30:00` | `LocalTime` | No |
| Local date and time without timezone | `2026-11-20T09:30:00` | `LocalDateTime` | No |

### Date: Calendar Date

A calendar date is commonly used for birth dates, invoice issue dates, holidays, local booking dates, or calendar-defined expiration dates.

Java `LocalDate` is appropriate because it contains only year, month, and day. It carries no time of day or timezone. A calendar date should not be automatically converted to UTC or shifted by an offset.

Example:

~~~java
LocalDate serviceDate = LocalDate.of(2026, 11, 20);
~~~

### DateTime: Point in Time with Offset

A point in time needs to be unambiguously placed on the timeline. A value with an offset such as `2026-11-20T09:30:00+07:00` specifies both the local time and the offset from UTC.

Java `OffsetDateTime` fits when the API contract needs to preserve the offset. `Instant` fits when the application only needs to represent an absolute instant in UTC.

Example:

~~~java
OffsetDateTime localTime = OffsetDateTime.parse(
        "2026-11-20T09:30:00+07:00");

Instant instant = localTime.toInstant();
~~~

These two values represent the same instant in time. `OffsetDateTime` preserves the input offset; `Instant` represents that instant on the UTC timeline.

### Offset Is Not the Same as Timezone

An offset like `+07:00` only states the difference from UTC at that specific moment. It does not store the timezone name, historical rules, or daylight saving time rules.

If business logic needs to know which timezone a user scheduled in, such as `Asia/Ho_Chi_Minh` or `Europe/Paris`, store the Zone ID separately. You can pass it as a dedicated field:

~~~graphql
input AppointmentTimeInput {
  startsAt: DateTime!
  timeZone: String!
}
~~~

The server validates `timeZone` using `ZoneId.of(...)` and applies the business rules. Do not assume that a fixed offset always represents a timezone.

## 3. Format Conventions to Standardize

An API must clearly define input and output formats. A common choice is ISO-8601 representation:

- Date: `yyyy-MM-dd`, for example `2026-11-20`.
- DateTime: date-time format with an offset or UTC, for example `2026-11-20T09:30:00+07:00` or `2026-11-20T02:30:00Z`.

Example GraphQL variables:

~~~json
{
  "date": "2026-11-20",
  "startsAt": "2026-11-20T09:30:00+07:00"
}
~~~

Rules to standardize:

1. Date accepts only valid Gregorian calendar dates; it does not accept times or offsets.
2. DateTime must include an offset or the UTC indicator `Z` if the contract requires an unambiguous instant.
3. Choose fractional-second precision, such as seconds or milliseconds, and stay consistent.
4. Define output normalization: either preserve the original offset or convert everything to UTC.
5. Reject malformed inputs or non-existent dates such as `2026-02-30`.

Do not silently interpret a DateTime without an offset using the server's default timezone. Doing so can cause results to differ across development, staging, and production environments.

## 4. Using Extended Scalars in Spring for GraphQL

You can write custom scalars manually using GraphQL Java. However, for common temporal types, the GraphQL Java Extended Scalars library provides pre-built scalars with conversion rules already implemented.

Declare a version property compatible with the GraphQL Java version managed by Spring Boot, then add the Maven dependency:

~~~xml
<dependency>
    <groupId>com.graphql-java</groupId>
    <artifactId>graphql-java-extended-scalars</artifactId>
    <version>${graphql-java-extended-scalars.version}</version>
</dependency>
~~~

Choose an Extended Scalars version compatible with the GraphQL Java version managed by Spring Boot. Do not upgrade GraphQL Java independently just to add a scalar without checking the compatibility matrix.

Register the scalars using `RuntimeWiringConfigurer`:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer dateScalars() {
        return wiringBuilder -> wiringBuilder
                .scalar(ExtendedScalars.Date)
                .scalar(ExtendedScalars.DateTime);
    }
}
~~~

Here:

- `ExtendedScalars.Date` provides the Date scalar, typically mapped to `java.time.LocalDate`.
- `ExtendedScalars.DateTime` provides the DateTime scalar, mapped to `java.time.OffsetDateTime`.
- `RuntimeWiringConfigurer` is detected by Spring Boot and applied when building the GraphQL runtime.

The scalar name in the SDL must match the registered scalar name. If the schema declares `scalar DateTime` but the runtime does not register the corresponding scalar, schema creation or coercion execution will not work as expected.

## 5. Declaring Date and DateTime in SDL

Schema example for an appointment:

~~~graphql
scalar Date
scalar DateTime

type Query {
  appointment(id: ID!): Appointment
}

type Mutation {
  reschedule(
    id: ID!
    serviceDate: Date!
    startsAt: DateTime!
  ): Appointment!
}

type Appointment {
  id: ID!
  serviceDate: Date!
  startsAt: DateTime!
}
~~~

The schema clearly expresses:

- `serviceDate` is a calendar date and is required.
- `startsAt` is a point in time with an offset and is required.
- The `reschedule` mutation requires the client to send both the calendar date and start time.
- The query returns the same scalar types so the client receives a consistent format.

If a date or time may not yet be determined, consider omitting the `!` on the corresponding field. Nullability decisions should reflect business semantics, not only Java types.

## 6. Mapping Date and DateTime to Java

Use `LocalDate` for Date and `OffsetDateTime` for DateTime when using the corresponding Extended Scalars.

DTO example:

~~~java
import java.time.LocalDate;
import java.time.OffsetDateTime;

public record Appointment(
        String id,
        LocalDate serviceDate,
        OffsetDateTime startsAt) {
}
~~~

Controller:

~~~java
@Controller
public class AppointmentController {

    private final AppointmentService appointmentService;

    public AppointmentController(
            AppointmentService appointmentService) {
        this.appointmentService = appointmentService;
    }

    @QueryMapping
    public Appointment appointment(@Argument String id) {
        return appointmentService.findById(id);
    }

    @MutationMapping
    public Appointment reschedule(
            @Argument String id,
            @Argument LocalDate serviceDate,
            @Argument OffsetDateTime startsAt) {

        return appointmentService.reschedule(
                id, serviceDate, startsAt);
    }
}
~~~

GraphQL Java performs scalar coercion when receiving variables and serializing results. Spring for GraphQL then binds the converted arguments into the Java parameters.

With Date input:

~~~graphql
mutation {
  reschedule(
    id: "apt-01"
    serviceDate: "2026-11-20"
    startsAt: "2026-11-20T09:30:00+07:00"
  ) {
    id
    serviceDate
    startsAt
  }
}
~~~

The Date input is converted into `LocalDate`, and DateTime into `OffsetDateTime`. When returning the response, the scalars convert those Java types into strings according to each scalar's serialization rules.

If you use an input object, you can group the temporal fields into a DTO:

~~~graphql
input RescheduleInput {
  serviceDate: Date!
  startsAt: DateTime!
}
~~~

~~~java
public record RescheduleInput(
        LocalDate serviceDate,
        OffsetDateTime startsAt) {
}

@MutationMapping
public Appointment reschedule(
        @Argument String id,
        @Argument RescheduleInput input) {

    return appointmentService.reschedule(
            id, input.serviceDate(), input.startsAt());
}
~~~

The input object structure must still be declared in the SDL, and the Java type must be able to bind the corresponding fields.

## 7. When Should You Use Instant Instead of OffsetDateTime?

In many systems, the database stores points in time in UTC and the Java domain model uses `Instant`. However, a common DateTime scalar may return `OffsetDateTime`. In that case, you can convert at the API boundary.

Example:

~~~java
Instant storedAt = appointment.getStartsAt();

OffsetDateTime responseTime = storedAt.atOffset(ZoneOffset.UTC);
~~~

When receiving input:

~~~java
Instant normalized = startsAt.toInstant();
~~~

This approach maintains a consistent UTC storage model while keeping the offset explicit in the API. If you need to display values in the user's timezone, convert them in the presentation or business layer using a validated Zone ID.

Do not store an important point in time as an arbitrary string in the database if the system needs to compare, sort, or calculate durations. Use the appropriate database and Java temporal types.

## 8. Implementing a Custom Scalar When Custom Rules Are Needed

Extended Scalars covers many common needs. If your API requires a specialized format, strict control over parsing/serialization, or a different Java type, you can build a custom scalar with GraphQL Java.

A scalar must define at least three conversion paths:

- **serialize:** converts a Java value into a JSON value returned to the client.
- **parseValue:** converts an input variable from JSON into a Java type.
- **parseLiteral:** converts a literal inside a GraphQL document into a Java type.

Skeleton example implementing Date with `LocalDate`:

~~~java
GraphQLScalarType dateScalar = GraphQLScalarType.newScalar()
        .name("Date")
        .description("Calendar date in ISO-8601 yyyy-MM-dd format")
        .coercing(new Coercing<LocalDate, String>() {

            @Override
            public String serialize(
                    Object input,
                    GraphQLContext context,
                    Locale locale) throws CoercingSerializeException {
                if (input instanceof LocalDate date) {
                    return date.toString();
                }
                throw new CoercingSerializeException(
                        "Date must be a LocalDate");
            }

            @Override
            public LocalDate parseValue(
                    Object input,
                    GraphQLContext context,
                    Locale locale) throws CoercingParseValueException {
                if (input instanceof String value) {
                    try {
                        return LocalDate.parse(value);
                    }
                    catch (DateTimeParseException ex) {
                        throw new CoercingParseValueException(
                                "Date must use yyyy-MM-dd format", ex);
                    }
                }
                throw new CoercingParseValueException(
                        "Date input must be a string");
            }

            @Override
            public LocalDate parseLiteral(
                    Value<?> input,
                    CoercedVariables variables,
                    GraphQLContext context,
                    Locale locale) throws CoercingParseLiteralException {
                if (input instanceof StringValue value) {
                    try {
                        return LocalDate.parse(value.getValue());
                    }
                    catch (DateTimeParseException ex) {
                        throw new CoercingParseLiteralException(
                                "Date literal must use yyyy-MM-dd format", ex);
                    }
                }
                throw new CoercingParseLiteralException(
                        "Date literal must be a string");
            }
        })
        .build();
~~~

This pattern follows the `Coercing` signatures of modern GraphQL Java versions. If your project uses an older version, method signatures may differ; check the Javadoc for the exact version managed by Spring Boot.

Register the newly created scalar:

~~~java
@Bean
RuntimeWiringConfigurer dateScalarConfigurer() {
    return wiringBuilder -> wiringBuilder.scalar(dateScalar);
}
~~~

In production code, place the scalar factory in a dedicated class, test all three conversion paths, and throw GraphQL Java's specialized coercion exceptions. Do not return null when input is malformed, as that hides contract violations.

## 9. Timezone Handling and Common Pitfalls

Temporal data is a common source of bugs because the same string can be interpreted differently depending on timezone and conversion rules.

| Symptom | Cause | Solution |
|---|---|---|
| Date shifts by one day after saving | Converting LocalDate to a UTC timestamp without matching semantics | Keep LocalDate for calendar dates |
| Points in time differ across environments | Parsing DateTime without an offset using the default timezone | Require an offset or Z |
| User timezone is lost | Storing only an offset like +07:00 | Store Zone ID as well if business logic needs it |
| Invalid input | Non-ISO-8601 string or non-existent calendar date | Let the scalar reject the input and return a clear error |
| Time precision discrepancies | Inconsistent truncation or rounding of fractional seconds | Define precision and normalize in one layer |
| Time changes during serialization | Unintentionally converting OffsetDateTime to UTC or vice versa | Choose a policy to preserve offset or normalize to UTC |

Examples that should be explicitly tested:

- Valid Date: `2026-11-20`.
- Invalid Date: `2026-02-30`.
- DateTime with offset: `2026-11-20T09:30:00+07:00`.
- UTC DateTime: `2026-11-20T02:30:00Z`.
- DateTime missing offset: `2026-11-20T09:30:00` — reject if the contract requires an absolute instant.

Do not automatically append `Z` to a value that lacks an offset. Doing so changes the temporal meaning and can produce a different instant than the client intended.

## 10. Testing Date and DateTime Scalars

Both input and output paths should be tested. With Spring for GraphQL, `GraphQlTester` lets you send operations and verify responses independently of how real clients invoke the API.

Mutation test example:

~~~java
@Test
void rescheduleShouldPreserveDateAndOffset() {
    GraphQlTester.Response response = graphQlTester.document("""
            mutation Reschedule(
                $id: ID!,
                $serviceDate: Date!,
                $startsAt: DateTime!
            ) {
                reschedule(
                    id: $id,
                    serviceDate: $serviceDate,
                    startsAt: $startsAt
                ) {
                    serviceDate
                    startsAt
                }
            }
            """)
            .variable("id", "apt-01")
            .variable("serviceDate", "2026-11-20")
            .variable("startsAt", "2026-11-20T09:30:00+07:00")
            .execute();

    response.path("reschedule.serviceDate")
            .entity(String.class)
            .isEqualTo("2026-11-20");

    response.path("reschedule.startsAt")
            .entity(String.class)
            .isEqualTo("2026-11-20T09:30:00+07:00");
}
~~~

You can also assert `startsAt` to ensure the offset is serialized according to your chosen policy. If the application normalizes to UTC, the expected value must be `2026-11-20T02:30:00Z`.

Cases to include in your test suite:

1. Valid Date and valid DateTime with offset.
2. Non-existent calendar Date.
3. DateTime missing an offset or malformed.
4. DateTime using UTC `Z` notation.
5. Values with fractional seconds if supported by the API.
6. Nullable fields accepting null and non-null fields rejecting null.
7. Input objects containing Date and DateTime fields.
8. Round-trip: parsing input into a Java temporal type and serializing back to the response.

For hand-written custom scalars, test `serialize`, `parseValue`, and `parseLiteral` individually. A scalar may work with variables yet fail when a client writes a literal directly in a GraphQL document if only one of the two parsing paths was implemented.

## 11. Temporal API Design Principles

When designing Date and DateTime for a GraphQL API, standardize on these principles:

- Use Date for calendar dates, mapped to `LocalDate`.
- Use DateTime for points in time with an offset, mapped to `OffsetDateTime` if supported by the scalar.
- Use `Instant` for absolute instants in the domain or persistence layer and convert explicitly at the API boundary.
- Store Zone ID separately if business rules depend on a named timezone.
- Do not treat `java.util.Date` or `LocalDateTime` as if they carry a timezone.
- Specify format, fractional-second precision, and output normalization policy.
- Reject invalid data instead of guessing or silently fixing timezones.
- Test JSON variables, GraphQL literals, and response serialization.

## Conclusion

Date and DateTime are essential custom scalars when a GraphQL API works with calendar dates and points in time. Date fits `LocalDate`; DateTime with an offset fits `OffsetDateTime`. If the system stores UTC instants, you can use `Instant` in the domain and convert explicitly at the API layer.

Spring for GraphQL enables scalar registration through `RuntimeWiringConfigurer`. The GraphQL Java Extended Scalars library provides Date and DateTime out of the box for many common scenarios. By clearly defining formats, offsets, timezones, nullability, and testing coercion, your API will avoid off-by-one-day bugs and misinterpreting timestamps.

## References

- [Spring for GraphQL — Schema and Runtime Wiring](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [GraphQL Java Extended Scalars](https://github.com/graphql-java/graphql-java-extended-scalars)
- [Java Date and Time API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/package-summary.html)
- [GraphQL Specification — Scalars](https://spec.graphql.org/October2021/#sec-Scalars)
