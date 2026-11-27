# Converting Enums, Dates/Times, and Custom Parameter Types in Spring Data REST

Query methods exposed by Spring Data REST receive parameters from the query string of an HTTP request. Values in the URL are initially always text, whereas repository methods can declare parameters of enum types, date/time types, or domain value objects.

Spring Data REST uses ConversionService to convert request values into the Java types required by the query method before calling the repository. As a result, clients can send readable values in the URL without having to convert them into internal data types themselves.

## 1. Search parameter conversion flow

Suppose a repository declares a method to find orders by status and creation timestamp:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @RestResource(path = "by-status-and-created-after",
                  rel = "byStatusAndCreatedAfter")
    List<Order> findByStatusAndCreatedAtAfter(
        @Param("status") OrderStatus status,
        @Param("createdAfter") OffsetDateTime createdAfter
    );
}
~~~

The client invokes the search endpoint:

~~~http
GET /orders/search/by-status-and-created-after?status=PAID&createdAfter=2026-11-11T09%3A30%3A00%2B07%3A00
~~~

Spring Data REST reads the string values of the two query parameters, converts them into OrderStatus and OffsetDateTime, and passes the converted objects into the query method.

The flow can be pictured as follows:

1. The client sends a GET request to the query method resource.
2. Spring Data REST reads the query parameters and matches their names against parameters declared with @Param.
3. ConversionService converts each value from the request format into the corresponding Java type.
4. If conversion succeeds, Spring Data executes the query method with the typed parameters.
5. The query results are returned as a REST resource according to the application configuration.

Parameter conversion happens before the query method is executed. A converter is only responsible for producing the appropriate Java value; it does not replace repository query logic or business rules.

## 2. Converting enum parameters

Enums fit properties with a finite set of values, such as order status:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
~~~

The repository can accept the enum directly:

~~~java
List<Order> findByStatus(@Param("status") OrderStatus status);
~~~

The client sends the enum name in the query string:

~~~http
GET /orders/search/findByStatus?status=PAID
~~~

Spring provides a default converter to convert String into an enum. With standard enum conversion, the input value must match the constant name, including case sensitivity. For example, PAID matches OrderStatus.PAID, whereas paid may not match.

If you want the API to accept lowercase, aliases, or user-friendly names, register a custom converter. For example:

~~~java
public class StringToOrderStatusConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        String value = source.trim().toLowerCase(Locale.ROOT);

        return switch (value) {
            case "new" -> OrderStatus.NEW;
            case "paid", "payment-confirmed" -> OrderStatus.PAID;
            case "shipped" -> OrderStatus.SHIPPED;
            case "cancelled", "canceled" -> OrderStatus.CANCELLED;
            default -> throw new IllegalArgumentException(
                "Unsupported order status: " + source
            );
        };
    }
}
~~~

After registering the converter, values like paid and payment-confirmed can both be converted to OrderStatus.PAID. Which aliases to accept is an API contract decision; clearly document supported values and keep them stable for clients.

### Enum translation and query parameters

Spring Data REST also has an enum translation feature via resource bundles. This feature serves to display enums as friendly text in representations and process translated enum values.

It can be enabled via Spring Boot configuration:

~~~yaml
spring:
  data:
    rest:
      enable-enum-translation: true
~~~

Enum translation and query parameter converters are two distinct configuration points. If a search API needs to accept custom tokens such as payment-confirmed, define and test a converter for the query method. Do not assume that UI display labels are always suitable values to send in a URL.

## 3. Converting date and time parameters

Spring supports converting strings into Java Time API date/time types. Prefer ISO formats because they are clearly structured, easy to exchange between systems, and avoid day/month ordering ambiguity.

| Java type | Meaning | Example input |
|---|---|---|
| LocalDate | Calendar date, without time or time zone | 2026-11-11 |
| LocalTime | Time of day, without date or time zone | 09:30:00 |
| LocalDateTime | Date and time, without time zone | 2026-11-11T09:30:00 |
| OffsetDateTime | Date and time with UTC offset | 2026-11-11T09:30:00+07:00 |
| Instant | An absolute point on the UTC timeline | 2026-11-11T02:30:00Z |

Example repository searching for events on a date:

~~~java
List<Event> findByEventDate(
    @Param("date") LocalDate date
);
~~~

Request:

~~~http
GET /events/search/findByEventDate?date=2026-11-11
~~~

Example finding orders created after a point in time:

~~~java
List<Order> findByCreatedAtAfter(
    @Param("createdAfter") Instant createdAfter
);
~~~

Request:

~~~http
GET /orders/search/findByCreatedAtAfter?createdAfter=2026-11-11T02%3A30%3A00Z
~~~

### Choosing the right date/time type

- Use LocalDate when only the calendar date matters, such as birth date or delivery date.
- Use LocalTime when only the time of day matters, such as opening hours.
- Use LocalDateTime when date and time have meaning on a local calendar without needing to pinpoint a global instant.
- Use OffsetDateTime when requests need to carry a specific UTC offset.
- Use Instant when comparing absolute points in time, recording events, or filtering timeline data.

Do not use LocalDateTime as a substitute for an absolute instant if the application spans multiple time zones. LocalDateTime carries no time zone or offset information, so the same value can represent different instants in different regions.

### Watch out for special characters in URLs

The plus sign in an offset, such as +07:00, must be URL-encoded as %2B when placed in a query string. If sent as a raw plus sign, some query string parsers decode it as a space.

Safe example:

~~~http
GET /events/search/findByStartAt?startAt=2026-11-11T09%3A30%3A00%2B07%3A00
~~~

Clients should use a URI builder or HTTP library to encode query parameters rather than concatenating URL strings manually.

## 4. Using custom date and time formats

If an existing API requires a non-ISO format, such as dates formatted as dd-MM-yyyy, you can register a custom Converter<String, LocalDate>.

~~~java
public class StringToLocalDateConverter
        implements Converter<String, LocalDate> {

    private static final DateTimeFormatter FORMAT =
        DateTimeFormatter.ofPattern("dd-MM-uuuu", Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);

    @Override
    public LocalDate convert(String source) {
        return LocalDate.parse(source.trim(), FORMAT);
    }
}
~~~

After registering the converter, clients can send:

~~~http
GET /events/search/findByEventDate?date=11-11-2026
~~~

The converter must clearly specify the input format. Do not guess between patterns like dd-MM-yyyy and MM-dd-yyyy because a string such as 04-05-2026 can be interpreted in two different ways.

When designing a new API, keep ISO formats. Only use custom formats when required by backward compatibility or specific business conventions.

## 5. Registering converters with RepositoryRestConfigurer

For Spring Data REST to use a converter, register it via the configureConversionService method of RepositoryRestConfigurer.

~~~java
@Configuration
public class RepositoryRestConversionConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureConversionService(
            ConfigurableConversionService conversionService) {

        conversionService.addConverter(
            new StringToOrderStatusConverter()
        );

        conversionService.addConverter(
            new StringToLocalDateConverter()
        );
    }
}
~~~

Key imports:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.ConfigurableConversionService;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
~~~

This registration configures the ConversionService used by Spring Data REST. Merely declaring a Converter bean or registering a formatter for Spring MVC does not guarantee the converter has been added to Spring Data REST's own ConversionService.

Multiple converters can be grouped in the same RepositoryRestConfigurer. Keep each converter focused on a single source-and-target type pair for readability, testability, and reuse.

## 6. Converting custom parameter types

Beyond enums and dates/times, a query method can accept a domain value object. For example, a system uses CustomerCode instead of a plain String:

~~~java
public final class CustomerCode {

    private final String value;

    public CustomerCode(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Customer code must not be blank"
            );
        }

        this.value = value.trim();
    }

    public String getValue() {
        return value;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }

        if (!(other instanceof CustomerCode that)) {
            return false;
        }

        return value.equals(that.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }
}
~~~

Converter turning a String from the URL into a CustomerCode:

~~~java
public class StringToCustomerCodeConverter
        implements Converter<String, CustomerCode> {

    @Override
    public CustomerCode convert(String source) {
        return new CustomerCode(source);
    }
}
~~~

The repository can declare a parameter with the same type as the corresponding domain property:

~~~java
List<Customer> findByCustomerCode(
    @Param("code") CustomerCode code
);
~~~

Client sends:

~~~http
GET /customers/search/findByCustomerCode?code=CUS-001
~~~

Spring Data REST converts CUS-001 into CustomerCode and passes that object to the query method.

An important condition is that the parameter type must fit how Spring Data builds queries. A converter only converts request data; it does not automatically invent query semantics for an arbitrary object. If you want to pass a multi-field filter that does not map directly to a domain property, you need a repository query or custom repository implementation that handles that filter.

### Converters for composite parameters

A query parameter can carry multiple values, such as a date range. Spring Data REST allows registering a converter from String[] to a custom object type:

~~~java
public class DateWindowConverter
        implements Converter<String[], DateWindow> {

    @Override
    public DateWindow convert(String[] values) {
        if (values.length != 2) {
            throw new IllegalArgumentException(
                "Expected start date and end date"
            );
        }

        LocalDate start = LocalDate.parse(values[0]);
        LocalDate end = LocalDate.parse(values[1]);

        if (end.isBefore(start)) {
            throw new IllegalArgumentException(
                "End date must not be before start date"
            );
        }

        return new DateWindow(start, end);
    }
}
~~~

The client can send the same query parameter multiple times:

~~~http
GET /reports/search/findByWindow?window=2026-11-01&window=2026-11-30
~~~

The converter receives the string values and constructs DateWindow. Then the query method or custom repository logic must know how to use DateWindow to perform the search. Registering a converter alone does not make Spring Data automatically infer that start and end should become greater-than and less-than conditions on a property.

## 7. Distinguishing REST parameter conversion from persistence conversion

In a Spring Data application, several conversion layers may exist:

| Mechanism | Purpose |
|---|---|
| Spring Data REST ConversionService | Converts query parameters into the Java types of repository parameters |
| Jackson serializer/deserializer | Converts JSON data when reading or writing representations |
| JPA AttributeConverter | Converts between an entity property type and a database column type |
| Spring Data CustomConversions | Converts data types in the persistence layer of the corresponding Spring Data module |

For example, Converter<String, CustomerCode> lets Spring Data REST construct CustomerCode from a query parameter. If CustomerCode is stored in a JPA column as VARCHAR, the application may also need a JPA AttributeConverter<CustomerCode, String> to convert between CustomerCode and the column value.

The two converters serve two different flows. Registering a converter for REST does not automatically configure how JPA persists the value object to the database; conversely, configuring a JPA AttributeConverter does not guarantee that query parameters will be converted into CustomerCode.

## 8. Handling invalid values

If the client sends a value that cannot be converted, the query method cannot be invoked with valid arguments. For example:

~~~http
GET /orders/search/findByStatus?status=UNKNOWN
~~~

Or:

~~~http
GET /events/search/findByEventDate?date=31-02-2026
~~~

Conversion failures are typically returned as invalid request errors, usually HTTP 400 Bad Request. The exact response structure and error message depend on the versions of Spring Data REST, Spring Framework, and the application's exception handling configuration.

Converters should validate input data and throw a clear error when a value is invalid. Do not silently substitute a default status for an unrecognized enum or turn an invalid date into a different date, as that can cause the query to return wrong data without the client noticing.

Values to validate include:

- Whether an enum belongs to the supported set of values.
- Whether a date actually exists on the calendar.
- Whether offsets and time zones are properly formatted.
- Whether date/time ranges are in valid order.
- Whether a value object satisfies formatting and business rules.
- Whether a required query parameter is missing or blank.

Do not expose stack traces or internal domain details in public error responses. Provide an appropriate error message and log technical details on the server according to application policy.

## 9. Testing parameter conversion

Test converters individually as well as through integration tests against Spring Data REST endpoints. Unit tests verify the conversion rules; HTTP tests confirm the converter is actually registered in the ConversionService used by the query method.

Cases to test:

1. Valid enum with exact casing.
2. Enum aliases if the API supports aliases.
3. Non-existent enum or empty string.
4. LocalDate in ISO format.
5. LocalDate with custom format if the application registers a converter.
6. OffsetDateTime with positive offset, negative offset, and UTC value.
7. Query parameter containing URL-encoded plus signs.
8. Valid and invalid value objects.
9. Repeated query parameter when the converter accepts String[].
10. Missing, null, or insufficient elements according to endpoint rules.

For instance, an integration test can send a request searching for orders with status=PAID and a valid createdAfter timestamp, then assert the repository returns the expected orders. Another test sends status=UNKNOWN and asserts the request is rejected with a 4xx error rather than executing the query with a default value.

## 10. Implementation workflow

1. Declare concrete parameter types in query methods instead of using String everywhere.
2. Name query parameters explicitly with @Param.
3. Choose stable formats for enums and dates/times; prefer ISO for temporal data.
4. If aliases or custom formats are needed, write a Converter with accurate source and target types.
5. Register converters via RepositoryRestConfigurer.configureConversionService.
6. If a custom type is also stored in the database, separately configure appropriate persistence conversion.
7. Test both the converter and the live query endpoint with valid and invalid inputs.

## 11. Key points to remember

- Query parameters enter Spring Data REST as strings and are converted by ConversionService to the query method's Java parameter types.
- Enums can be converted by the default converter; use a custom Converter if aliases or case-insensitive rules are required.
- LocalDate, LocalDateTime, OffsetDateTime, and Instant have different temporal meanings; pick the type suited to the business domain.
- Use ISO date/time as the default interchange format and URL-encode special characters like the plus sign in offsets.
- Register custom converters through RepositoryRestConfigurer.configureConversionService.
- A converter only converts values; the query method or custom repository still defines how that parameter is used.
- REST request conversion, JSON conversion, and persistence conversion are separate flows; configuring one does not automatically configure the others.
- Test the live endpoint to confirm data is converted properly before the query executes.

## References

- [Spring Data REST — Repository resources and Query Method Resource](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Data REST — EnumTranslationConfiguration API](https://docs.spring.io/spring-data/rest/reference/5.2/api/java/org/springframework/data/rest/core/config/EnumTranslationConfiguration.html)
