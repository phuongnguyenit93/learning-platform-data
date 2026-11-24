# Query Objects and @ParameterObject

A search endpoint often accepts several related query parameters: keyword, status, date range, price threshold, page number, and page size. Declaring each parameter individually in the controller signature can make the method long and hard to extend. Spring MVC allows grouping these values into a query object (or model attribute). With springdoc-openapi, the **@ParameterObject** annotation lets you document that object's properties as separate query parameters in the OpenAPI specification.

This article explains the role of model attributes in Spring MVC, how @ParameterObject generates OpenAPI metadata, how to combine it with validation, date formatting, and Pageable, and the limitations to keep in mind when designing query objects.

## 1. Why Group Query Parameters into an Object?

Suppose an order search API accepts these parameters:

- keyword: search term for order code or buyer name.
- status: order status.
- createdFrom and createdTo: creation date range.
- minTotal: minimum total amount.
- page, size, and sort: pagination and sorting.

Declaring every parameter individually can result in a lengthy controller signature:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> searchOrders(
    @RequestParam(required = false) String keyword,
    @RequestParam(required = false) OrderStatus status,
    @RequestParam(required = false) LocalDate createdFrom,
    @RequestParam(required = false) LocalDate createdTo,
    @RequestParam(required = false) BigDecimal minTotal,
    @RequestParam(defaultValue = "0") int page,
    @RequestParam(defaultValue = "20") int size
) {
    // Search orders.
    return Page.empty();
}
~~~

As filters grow, the method becomes harder to read and reuse. Search criteria can be grouped into a class:

~~~java
public class OrderSearchCriteria {
    private String keyword;
    private OrderStatus status;
    private LocalDate createdFrom;
    private LocalDate createdTo;
    private BigDecimal minTotal;

    // Default constructor, getters, and setters.
}
~~~

The controller accepts one object instead of many parameters:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> searchOrders(
    @ModelAttribute OrderSearchCriteria criteria
) {
    return orderService.search(criteria);
}
~~~

In Spring MVC, @ModelAttribute tells Spring to bind request data into the object's properties. For GET requests, query parameters like keyword, status, and createdFrom map to the corresponding properties. Such an object is commonly called a query object, filter object, or search criteria.

Grouping parameters keeps controller signatures concise, enables reusing the same filter type across endpoints, and centralizes validation logic in one class.

## 2. @ModelAttribute and @ParameterObject Have Different Roles

These two annotations often appear together but serve two distinct purposes:

| Annotation | Role |
|---|---|
| @ModelAttribute | Spring MVC binds request data into the object and adds it to the controller model |
| @ParameterObject | Springdoc inspects the object's properties to generate query parameters in OpenAPI |

Example:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> searchOrders(
    @ParameterObject
    @ModelAttribute
    OrderSearchCriteria criteria
) {
    return orderService.search(criteria);
}
~~~

When the client sends:

~~~http
GET /api/orders?keyword=keyboard&status=PAID&minTotal=100000
~~~

Spring MVC binds the values into OrderSearchCriteria. Springdoc reads @ParameterObject and documents keyword, status, and minTotal as individual parameters in the OpenAPI document.

**@ParameterObject does not perform data binding itself and does not alter HTTP behavior.** It is a hint for documentation generation. If you omit @ModelAttribute in cases where Spring MVC needs explicit model attribute binding, make sure you understand Spring's default binding rules before relying on a shorter signature.

In many Spring MVC controllers, an object-typed parameter without special annotations is inferred as a model attribute. Even so, explicitly using @ModelAttribute makes binding intent clear to readers. To have OpenAPI expand the object into query parameters, add @ParameterObject.

## 3. Declaring a Query Object

A standard query object is a JavaBean with a default constructor and getters/setters. Example:

~~~java
import io.swagger.v3.oas.annotations.Parameter;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Size;
import org.springframework.format.annotation.DateTimeFormat;

import java.math.BigDecimal;
import java.time.LocalDate;

public class OrderSearchCriteria {

    @Parameter(
        description = "Search by order code or buyer name",
        example = "ORD-2026"
    )
    @Size(max = 100)
    private String keyword;

    @Parameter(
        description = "Filter by order status",
        example = "PAID"
    )
    private OrderStatus status;

    @Parameter(
        description = "Creation date from, inclusive",
        example = "2026-01-01"
    )
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate createdFrom;

    @Parameter(
        description = "Creation date to, inclusive",
        example = "2026-01-31"
    )
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate createdTo;

    @Parameter(
        description = "Minimum total amount",
        example = "100000"
    )
    @DecimalMin("0.00")
    private BigDecimal minTotal;

    public OrderSearchCriteria() {
    }

    // Add getters and setters for the properties.
}
~~~

Properties are bound by Spring according to query parameter names. For example, a request with keyword=ORD-2026 assigns that value to the keyword property.

Design principles:

- Use wrapper types such as Integer, Boolean, or BigDecimal when you need to distinguish an omitted parameter from 0 or false.
- Choose Java types fitting the data: LocalDate for dates, Instant for absolute points in time, and enums for fixed status sets.
- Keep the query object focused on search criteria; avoid placing persistence entities or services in this class.
- Set size and value bounds to prevent invalid requests or overly expensive queries.
- Use a default constructor and getters/setters following Spring MVC's standard JavaBean binding convention.

Enum example:

~~~java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    PAID,
    CANCELLED
}
~~~

OpenAPI can represent enums as lists of allowed values. Swagger UI users can then see the selectable status options.

## 4. Using @ParameterObject in a Controller

Once the query object is defined, place @ParameterObject on the controller parameter:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Page;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders")
    @Operation(
        summary = "Search orders",
        description = "Filter orders by keyword, status, creation date, and total amount."
    )
    public Page<OrderResponse> searchOrders(
        @ParameterObject @ModelAttribute OrderSearchCriteria criteria
    ) {
        return orderService.search(criteria);
    }
}
~~~

In this example:

- @ModelAttribute helps Spring bind the query string into criteria.
- @ParameterObject instructs springdoc to document criteria's properties as query parameters.
- @Operation provides summary and description for the operation.
- OrderService executes the business query.

With springdoc-openapi v2, import @ParameterObject from the org.springdoc.core.annotations package. If the project uses springdoc v1, the annotation package may differ; check the migration documentation for your exact version rather than copying imports from another major release.

## 5. How Is the OpenAPI JSON Generated?

Assuming the controller receives OrderSearchCriteria as above, the corresponding OpenAPI portion can be summarized as follows:

~~~json
{
  "paths": {
    "/api/orders": {
      "get": {
        "summary": "Search orders",
        "parameters": [
          {
            "name": "keyword",
            "in": "query",
            "required": false,
            "description": "Search by order code or buyer name",
            "schema": {
              "type": "string",
              "maxLength": 100
            }
          },
          {
            "name": "status",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "enum": [
                "PENDING",
                "CONFIRMED",
                "PAID",
                "CANCELLED"
              ]
            }
          },
          {
            "name": "createdFrom",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "format": "date"
            }
          },
          {
            "name": "minTotal",
            "in": "query",
            "required": false,
            "schema": {
              "type": "number",
              "minimum": 0
            }
          }
        ],
        "responses": {
          "200": {
            "description": "List of orders"
          }
        }
      }
    }
  }
}
~~~

The key takeaway is that properties appear inside the parameters array, each with:

- name: query parameter name.
- in: data location, here query.
- required: whether the parameter is mandatory.
- description: descriptive text if declared.
- schema: data type, enum, format, and inferred constraints.

A query object does not necessarily appear as a request body schema. For GET endpoints, properties are represented as individual query parameters passed by clients in the URL.

## 6. Describing Each Property with @Parameter

You can place @Parameter on fields or properties to add descriptions, examples, display names, and required statuses for documentation.

~~~java
public class ProductSearchCriteria {

    @Parameter(
        name = "q",
        description = "Keyword to search product name or SKU",
        example = "wireless mouse"
    )
    private String keyword;

    @Parameter(
        description = "Only return in-stock products",
        example = "true"
    )
    private Boolean inStock;

    @Parameter(
        description = "Maximum number of results",
        example = "50"
    )
    private Integer limit;

    // Constructor, getters, and setters.
}
~~~

If you rename a parameter using the name attribute, test the actual binding. OpenAPI metadata can display a name different from the Java property, whereas Spring MVC still binds by Java property name unless you configure a corresponding binding mechanism. Do not change the documented name without verifying that requests using that name are accepted by the application.

You can declare required in metadata:

~~~java
@Parameter(
    description = "Required store code",
    required = true,
    example = "HCM-01"
)
private String storeCode;
~~~

However, required in OpenAPI is a descriptive contract. To make the application actually reject missing data, combine it with validation and checks in the request-handling layer.

## 7. Combining Bean Validation

Query objects can use Bean Validation to constrain input data. Example:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;

public class ProductSearchCriteria {

    @Size(max = 80)
    private String keyword;

    @Min(0)
    private Integer minPrice;

    @Min(1)
    @Max(100)
    private Integer limit = 20;

    // Getters and setters.
}
~~~

Enable validation on the controller parameter:

~~~java
@GetMapping("/api/products")
public List<ProductResponse> searchProducts(
    @Valid @ParameterObject @ModelAttribute ProductSearchCriteria criteria
) {
    return productService.search(criteria);
}
~~~

For validation to run, the project needs a Bean Validation implementation, typically included via Spring Boot's validation starter. If validation does not execute, check the validation dependency, the @Valid annotation, and controller configuration.

Common annotations:

| Annotation | Effect |
|---|---|
| @NotNull | Value must not be null |
| @NotBlank | String must contain at least one non-whitespace character |
| @Size | Limits string length or collection size |
| @Min / @Max | Limits integer or numeric values |
| @DecimalMin / @DecimalMax | Limits decimal values |
| @Positive / @PositiveOrZero | Requires positive or non-negative numbers |
| @Pattern | Validates string against a regular expression |

Not every validation annotation automatically becomes an OpenAPI constraint identically across all versions. Inspect the generated JSON and verify runtime behavior with both valid and invalid requests.

## 8. Formatting Dates, Times, and Enums

Query parameters are passed in the URL as strings. Spring must convert those strings into the corresponding Java types. For dates, standardize on ISO formats so clients can use them easily.

Example:

~~~java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate createdFrom;

@DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
private LocalDateTime createdAtFrom;
~~~

Sample request:

~~~http
GET /api/orders?createdFrom=2026-01-01&createdAtFrom=2026-01-01T08:30:00
~~~

LocalDate represents a calendar date without a time zone. LocalDateTime represents date and time without an offset or timezone. If the API needs absolute instants across multiple time zones, consider Instant or OffsetDateTime and clearly document formatting and UTC/offset conventions in the contract.

Enums constrain input values:

~~~java
public enum PaymentStatus {
    PENDING,
    SUCCESS,
    FAILED,
    REFUNDED
}
~~~

If a client sends a value not in the enum, Spring may return a type conversion error. Document valid values and standardize uppercase/lowercase per API conventions.

## 9. Using @ParameterObject with Pageable

List APIs commonly require pagination and sorting. Spring Data provides Pageable to group page, size, and sort into one object.

Example:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> searchOrders(
    @ParameterObject @ModelAttribute OrderSearchCriteria criteria,
    @ParameterObject
    @PageableDefault(
        size = 20,
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return orderService.search(criteria, pageable);
}
~~~

With springdoc, Pageable can be documented as individual query parameters such as:

| Parameter | Meaning | Example |
|---|---|---|
| page | Page number, usually starting at 0 | page=0 |
| size | Number of items per page | size=20 |
| sort | Property and sort direction | sort=createdAt,desc |

Request combining filters and pagination:

~~~http
GET /api/orders?keyword=ORD&status=PAID&page=0&size=20&sort=createdAt,desc
~~~

@PageableDefault defines default values for Pageable. Ensure the application enforces a maximum page size so clients cannot request an excessively large page. Spring Data Web and springdoc settings can affect how Pageable parameters appear; check the actual specification at /v3/api-docs.

## 10. When Should You Avoid @ParameterObject?

@ParameterObject works well for a flat set of query properties with clear names. Not every object structure is suited for automatic conversion into query parameters.

Consider these cases:

- **Nested objects:** nested query objects are not supported or are not flattened the way clients expect in all cases. Flatten the DTO or declare parameters explicitly.
- **Complex structures:** multi-level filters, AND/OR conditions, or search expressions should use a request body on an appropriate endpoint, or a clearly designed query syntax.
- **Overlapping property names:** multiple parameter objects sharing property names can cause conflicting query parameter names.
- **Large payloads:** complex lists of criteria do not fit long URLs; consider POST search with a request body if API design allows.
- **Special formatting requirements:** maps, custom objects, or data types without clear conversion rules must be documented explicitly.

Example of a nested structure:

~~~java
public class OrderSearchCriteria {
    private CustomerFilter customer;
    private DateRange createdAt;
}
~~~

Do not assume springdoc will automatically generate query names like customer.name or createdAt.from matching backend conventions. If the API truly accepts those names, design binding explicitly and verify the OpenAPI document. A simpler option is flattening:

~~~java
public class OrderSearchCriteria {
    private String customerName;
    private LocalDate createdFrom;
    private LocalDate createdTo;

    // Getters and setters.
}
~~~

When filters grow complex enough to represent nested condition groups, a request body is usually easier to understand and extend than a query string.

## 11. A Query Object Is Not a Request Body

A common design mistake is assuming that when a controller takes an object, clients must send JSON. That depends on Spring's annotations and binding rules.

| Declaration | Data Location | How Clients Send Data |
|---|---|---|
| @ModelAttribute + @ParameterObject | Query parameters or form fields per Spring MVC binding | URL query string |
| @RequestBody | HTTP request body | JSON, XML, or declared media type |
| @PathVariable | Path segment | Part of the URL |
| @RequestHeader | HTTP header | Request header |

Query object example:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> search(
    @ParameterObject @ModelAttribute OrderSearchCriteria criteria
) {
    return orderService.search(criteria);
}
~~~

Client call:

~~~http
GET /api/orders?status=PAID&keyword=ORD
~~~

Request body example:

~~~java
@PostMapping("/api/orders/search")
public List<OrderResponse> advancedSearch(
    @RequestBody AdvancedOrderSearchRequest request
) {
    return orderService.advancedSearch(request);
}
~~~

Client sends JSON:

~~~http
POST /api/orders/search
Content-Type: application/json

{
  "statuses": ["PAID", "CONFIRMED"],
  "created": {
    "from": "2026-01-01",
    "to": "2026-01-31"
  }
}
~~~

Choose the data transport method based on API semantics and complexity. GET with query parameters suits simple filters that can be bookmarked and cached by URL. POST with a request body can suit complex queries or large payloads.

## 12. Verifying Output in OpenAPI JSON and Swagger UI

After starting the application, save the specification:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Use jq to inspect the operation's parameters:

~~~bash
jq '.paths["/api/orders"].get.parameters' openapi.json
~~~

List parameter names and locations:

~~~bash
jq -r '
  .paths["/api/orders"].get.parameters[]
  | [.name, .in, (.required // false)]
  | @tsv
' openapi.json
~~~

Compare the output against the query object:

- Have all properties meant for publication appeared?
- Do parameter names match what the controller receives?
- Do all parameters have in=query?
- Do enums list the right values?
- Do dates have appropriate date or date-time formats?
- Are validation constraints reflected if supported by the library?
- Does Pageable include page, size, and sort as expected?

Open Swagger UI and verify the displayed fields. If a property is missing, review getters/setters, visibility, the @ParameterObject annotation, data types, and springdoc configuration. Then send test requests to confirm Spring MVC actually binds values accurately.

## 13. Common Errors

| Symptom | Cause to Check |
|---|---|
| Query object does not appear in OpenAPI | Missing @ParameterObject or controller parameter analyzed via another mechanism. |
| Only a single generic object parameter appears | springdoc did not flatten the object as desired; check annotations and parameter types. |
| Some properties are missing | Missing getters/setters, field not introspected, property hidden, or unsupported data type. |
| Swagger UI shows query parameters but Spring receives null | Parameter name mismatches property or model attribute binding is misconfigured. |
| Dates fail conversion | Missing @DateTimeFormat or string does not match format. |
| Validation does not run | Missing Bean Validation implementation, @Valid, or proper validation configuration. |
| Pageable displays incorrectly | Check spring-data-commons, @ParameterObject, @PageableDefault, and springdoc configuration. |
| Nested object represented inaccurately | Flatten the query DTO or declare explicit parameters. |
| Two filters generate duplicate query parameter names | Rename properties or group filters into an object with clear naming. |

When investigating, separate two questions: does OpenAPI document the parameters properly, and does Spring MVC bind the request into the object properly? One side being right does not guarantee the other is.

## 14. Query Object Design Checklist

- [ ] Query object contains only necessary filtering, search, or pagination data.
- [ ] Property names are clear and stable as query parameter names.
- [ ] Constructor and getters/setters fit the binding mechanism.
- [ ] Appropriate Java types are used for dates, instants, numbers, and enums.
- [ ] @ParameterObject is placed on parameters meant to be documented as query parameters.
- [ ] @ModelAttribute is used explicitly when indicating Spring MVC binding.
- [ ] Parameters are annotated with @Parameter when descriptions or examples are needed.
- [ ] Validation and page size limits are applied.
- [ ] Nested objects are not assumed to flatten automatically.
- [ ] Query objects are not mixed up with request bodies.
- [ ] Parameters have been verified in /v3/api-docs.
- [ ] Real requests have been sent to verify binding and validation.

## 15. References

- [springdoc-openapi – Documentation](https://springdoc.org/)
- [springdoc-openapi – FAQ](https://springdoc.org/#faq)
- [Spring Framework – Model Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Data – Web Support and Pageable](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object)

@ParameterObject helps springdoc represent a query object as separate parameters in OpenAPI. Spring MVC remains responsible for binding and validating actual data. Whenever modifying a query object's structure or upgrading springdoc, verify both the JSON specification and runtime requests to ensure clients can send valid data.
