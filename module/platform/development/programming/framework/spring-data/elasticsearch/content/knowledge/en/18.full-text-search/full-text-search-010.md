# Range Queries for Numbers and Dates/Times

In full-text search, applications often need to combine text conditions with constraints on price, quantity, rating, or time. For example, a user searches for products whose name contains "keyboard", priced from 50 to 200, updated within the last 30 days. The text search part can use a match query, while numeric and time bounds are expressed with range queries.

Elasticsearch provides the range query to find documents whose field value falls within an interval. Spring Data Elasticsearch supports building this query type through the Criteria API, NativeQuery, and JSON queries declared in repositories. Picking the right approach keeps queries clear, controls boundaries accurately, and leverages properly typed mappings.

## 1. What Is a Range Query?

A range query selects documents based on one or more bounds on a field. Basic operators:

| Operator | Meaning | Includes boundary value? |
| --- | --- | --- |
| gt | Greater than | Excludes lower bound |
| gte | Greater than or equal | Includes lower bound |
| lt | Less than | Excludes upper bound |
| lte | Less than or equal | Includes upper bound |

Example finding products priced from 100 to 500, inclusive on both ends:

~~~json
{
  "query": {
    "range": {
      "price": {
        "gte": 100,
        "lte": 500
      }
    }
  }
}
~~~

If you need prices strictly greater than 100 and strictly less than 500, excluding both bounds:

~~~json
{
  "query": {
    "range": {
      "price": {
        "gt": 100,
        "lt": 500
      }
    }
  }
}
~~~

Range queries do not analyze text like match queries. They compare values according to the field's data type in the mapping. Therefore, the mapping type must match the meaning of the data.

## 2. Mappings for Numeric Fields

Elasticsearch supports multiple numeric types depending on the range and precision needed:

| Elasticsearch type | Typical use case |
| --- | --- |
| byte | Very small integers |
| short | Small-range integers |
| integer | 32-bit integers |
| long | 64-bit integers |
| unsigned_long | Non-negative integers with a large range |
| half_float | Low-precision floating-point numbers |
| float | 32-bit floating-point numbers |
| double | 64-bit floating-point numbers |
| scaled_float | Floating-point numbers stored using a scaling factor |

Do not choose a type solely because a Java property has a similar type name. Base the choice on value range, precision, storage size, and how business logic compares values.

### 2.1. Declaring numeric mappings with Spring Data

Example product entity with price, stock quantity, and rating:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private double price;

    @Field(type = FieldType.Integer)
    private int stockQuantity;

    @Field(type = FieldType.Float)
    private float rating;

    // Constructors, getters, and setters
}
~~~

The corresponding JSON mapping can be written:

~~~json
{
  "properties": {
    "sku": {
      "type": "keyword"
    },
    "name": {
      "type": "text"
    },
    "price": {
      "type": "double"
    },
    "stockQuantity": {
      "type": "integer"
    },
    "rating": {
      "type": "float"
    }
  }
}
~~~

Spring Data annotations help generate the mapping when creating an index from entity metadata. If the index already exists, changing annotations does not automatically update the existing mapping. Always verify the actual mapping with:

~~~http
GET /catalog-products/_mapping
~~~

### 2.2. Storing currency and precision

Do not use binary floating-point numbers to represent money if business rules require exact comparison down to the smallest currency unit. For instance, instead of storing 19.99 as double, store 1999 cents as long:

~~~java
@Field(type = FieldType.Long)
private long priceInCents;
~~~

Range queries on priceInCents will compare exact integers. The application handles converting currency units to minor units and formatting for display.

Another option is Elasticsearch's scaled_float type. Example JSON mapping:

~~~json
{
  "properties": {
    "price": {
      "type": "scaled_float",
      "scaling_factor": 100
    }
  }
}
~~~

With scaling_factor set to 100, values are stored internally multiplied by the factor, fitting two decimal places. Choose the factor based on business precision. Check how your Spring Data version maps BigDecimal and declares scaled_float; do not assume every decimal Java type automatically generates the intended mapping.

### 2.3. Range queries on numeric array fields

A numeric field can hold multiple values. A range query matches a document if at least one value in the field falls within the specified range.

Example:

~~~json
{
  "priceHistory": [80, 120, 250]
}
~~~

A query searching for values from 100 to 150 will match this document because it contains 120. Range queries do not require every element in the array to lie inside the interval.

If business logic needs to correlate multiple attributes within the same element of an object array, consider nested mappings and nested queries; regular range queries across object fields may not preserve per-element relationships.

## 3. Mappings for Date/Time Fields

Elasticsearch typically stores dates internally as epoch milliseconds, while allowing date-time values to be sent as strings matching a declared format or as appropriate numbers.

Default date mappings generally accept ISO date-times and epoch milliseconds. When an application uses a custom format, declare it explicitly so indexing writes and range queries follow the same convention.

### 3.1. Date/time types in Java

| Java type | Meaning |
| --- | --- |
| Instant | An absolute point on the timeline, typically represented in UTC |
| OffsetDateTime | Date and time with a UTC offset |
| ZonedDateTime | Date and time attached to a time zone with DST rules |
| LocalDate | Calendar date without time or time zone |
| LocalDateTime | Local date and time without offset/time zone |
| Date | Legacy point-in-time type with millisecond precision |

For event timestamps such as createdAt, paidAt, or lastUpdatedAt, Instant is usually a clear choice because it represents an absolute instant. For birthdates or effective dates with pure calendar meaning, LocalDate can fit better. Avoid LocalDateTime for global events unless explicit time-zone rules exist.

### 3.2. Declaring date mappings

Example:

~~~java
import java.time.Instant;

import org.springframework.data.elasticsearch.annotations.DateFormat;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Field(type = FieldType.Date, format = DateFormat.date_time)
private Instant createdAt;
~~~

Corresponding JSON mapping:

~~~json
{
  "properties": {
    "createdAt": {
      "type": "date",
      "format": "strict_date_optional_time||epoch_millis"
    }
  }
}
~~~

Formats with multiple alternatives are separated by ||. Elasticsearch tries the formats in list order to parse incoming values. Include only formats that are actually needed; overly permissive formats can lead to inconsistent data that is hard to control.

### 3.3. Custom date formats

If the system must accept a custom format, declare a pattern:

~~~java
@Field(
    type = FieldType.Date,
    format = DateFormat.custom,
    pattern = "uuuu-MM-dd HH:mm:ss"
)
private Instant importedAt;
~~~

Corresponding JSON mapping might be:

~~~json
{
  "properties": {
    "importedAt": {
      "type": "date",
      "format": "uuuu-MM-dd HH:mm:ss"
    }
  }
}
~~~

This pattern contains no time zone. If input strings lack an offset, the system must have a clear rule for interpreting that timestamp. For event data, prefer ISO-8601 with an offset or normalize to UTC before indexing.

### 3.4. date and date_nanos

Elasticsearch has two common date types:

- date: internal precision in milliseconds.
- date_nanos: precision down to nanoseconds, useful when distinguishing events occurring very close together.

date_nanos has a narrower representable range than date and higher cost in some scenarios. Use it only when nanosecond precision has real business value. Java's Instant precision does not mean the index automatically stores nanoseconds if the mapping is date.

## 4. Numeric Range Queries with Query DSL

Example finding products priced from 50 to under 200:

~~~http
GET /catalog-products/_search
{
  "query": {
    "range": {
      "price": {
        "gte": 50,
        "lt": 200
      }
    }
  }
}
~~~

Example filtering stock quantity 1 or higher and rating at least 4:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "range": {
            "stockQuantity": {
              "gte": 1
            }
          }
        },
        {
          "range": {
            "rating": {
              "gte": 4.0,
              "lte": 5.0
            }
          }
        }
      ]
    }
  }
}
~~~

When multiple range conditions are only for filtering, put them in bool.filter to avoid unnecessary relevance score calculation. Range queries inside filter context still decide which documents are selected.

## 5. Date/Time Range Queries with Query DSL

### 5.1. Fixed time intervals

Suppose you need events in March 2026:

~~~http
GET /events/_search
{
  "query": {
    "range": {
      "createdAt": {
        "gte": "2026-03-01T00:00:00Z",
        "lt": "2026-04-01T00:00:00Z"
      }
    }
  }
}
~~~

This interval includes the start of March and excludes the start of April. Using an exclusive upper bound is very helpful when partitioning data by month/day because adjacent intervals do not overlap.

### 5.2. Time intervals with time zones

If a user selects March in Vietnam time, the month boundaries are:

- Start: 2026-03-01 00:00:00 +07:00.
- Exclusive end: 2026-04-01 00:00:00 +07:00.

You can pass the offset directly:

~~~json
{
  "query": {
    "range": {
      "createdAt": {
        "gte": "2026-03-01T00:00:00+07:00",
        "lt": "2026-04-01T00:00:00+07:00"
      }
    }
  }
}
~~~

Elasticsearch converts values with offsets onto the same timeline for comparison. This clarifies boundary time zones and avoids confusing a user's calendar day with UTC.

Another way is passing offset-less values together with the time_zone parameter:

~~~json
{
  "query": {
    "range": {
      "createdAt": {
        "gte": "2026-03-01T00:00:00",
        "lt": "2026-04-01T00:00:00",
        "time_zone": "+07:00"
      }
    }
  }
}
~~~

time_zone is used to interpret date-time values in the query and affects date math rounding. The value now is always based on the current UTC time; time_zone does not change the instant `now` itself.

### 5.3. Using date math

Date math lets you construct time intervals relative to the current time:

| Expression | Meaning |
| --- | --- |
| now | Current instant |
| now-1d | One day before the current instant |
| now-7d | Seven days ago |
| now-1M | One calendar month ago |
| now/d | Rounded down to the start of the current day |
| now-7d/d | Back seven days, rounded down to the start of that day |
| now+1d/d | Start of the next day |

Example finding events in the last 24 hours:

~~~json
{
  "query": {
    "range": {
      "createdAt": {
        "gte": "now-24h",
        "lte": "now"
      }
    }
  }
}
~~~

Example fetching data from the start of 6 days ago through the start of tomorrow, in Vietnam time:

~~~json
{
  "query": {
    "range": {
      "createdAt": {
        "gte": "now-6d/d",
        "lt": "now+1d/d",
        "time_zone": "+07:00"
      }
    }
  }
}
~~~

Date math is very handy for dashboards and scheduled reports. However, distinguish a rolling 24-hour window from a calendar-day window. Those two concepts produce different results around midnight.

## 6. Interval Boundary Rules and Half-Open Intervals

Range queries let you choose inclusive/exclusive independently at each end. In time-series data systems, a common convention is the half-open interval:

\[
[start,\ end)
\]

That means inclusive of start and exclusive of end. Example:

~~~json
{
  "range": {
    "createdAt": {
      "gte": "2026-01-01T00:00:00Z",
      "lt": "2026-02-01T00:00:00Z"
    }
  }
}
~~~

Benefits:

- No need to construct end timestamps like 23:59:59.999.
- Avoids missing data with sub-millisecond precision.
- Adjacent intervals never overlap.
- Cleanly represents months, days, billing cycles, or sync windows.

For instance, January is [01-01, 02-01), and February is [02-01, 03-01). A document at exactly 00:00 on February 1 belongs only to February.

For numeric values, half-open intervals can also be used when partitioning non-overlapping buckets. However, if business rules explicitly state "from 100 to 200 inclusive of 200", use gte/lte to reflect that rule faithfully.

## 7. Range Queries with NativeQuery

NativeQuery uses the typed query DSL of the Elasticsearch Java API Client. This is a good choice when combining multiple queries, date math, time zones, or detailed range options.

### 7.1. Numeric range

Example finding products priced from 50 to under 200:

~~~java
import co.elastic.clients.json.JsonData;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.domain.PageRequest;

Query priceRange = Query.of(q -> q
    .range(r -> r
        .number(n -> n
            .field("price")
            .gte(JsonData.of(50))
            .lt(JsonData.of(200))
        )
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(priceRange)
    .withPageable(PageRequest.of(0, 20))
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

In the Java API Client, numeric range values are represented via JsonData. Exact builder types depend on the client version managed by Spring Boot.

### 7.2. Date range

Example finding documents in an ISO-8601 time range:

~~~java
Query dateRange = Query.of(q -> q
    .range(r -> r
        .date(d -> d
            .field("createdAt")
            .gte("2026-03-01T00:00:00Z")
            .lt("2026-04-01T00:00:00Z")
        )
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(dateRange)
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

### 7.3. Date math and time zone

A range query using date math can be expressed as:

~~~java
Query recentEvents = Query.of(q -> q
    .range(r -> r
        .date(d -> d
            .field("createdAt")
            .gte("now-30d/d")
            .lt("now+1d/d")
            .timeZone("+07:00")
        )
    )
);
~~~

Verify builder method names in your active Java API Client version. Across versions with different generated typed DSLs, structure may vary while the resulting JSON remains equivalent to the desired Query DSL.

## 8. Combining Range with Full-Text Queries

In full-text search, range is rarely the sole query. For example, finding products matching "keyboard", priced from 50 to under 200, and created in the last 90 days:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "keyboard"
          }
        }
      ],
      "filter": [
        {
          "range": {
            "price": {
              "gte": 50,
              "lt": 200
            }
          }
        },
        {
          "range": {
            "createdAt": {
              "gte": "now-90d",
              "lte": "now"
            }
          }
        }
      ]
    }
  }
}
~~~

Meaning:

- must holds the match query to compute relevance scores based on name content.
- filter holds range queries to exclude documents outside the price or time interval.
- Filter conditions do not contribute to relevance scores.

This is a common pattern for search pages with filters for price, creation date, stock, rating, or quantity ranges.

### 8.1. Combining with NativeQuery

~~~java
Query combinedQuery = Query.of(q -> q
    .bool(b -> b
        .must(m -> m
            .match(match -> match
                .field("name")
                .query("keyboard")
            )
        )
        .filter(f -> f
            .range(r -> r
                .number(n -> n
                    .field("price")
                    .gte(JsonData.of(50))
                    .lt(JsonData.of(200))
                )
            )
        )
        .filter(f -> f
            .range(r -> r
                .date(d -> d
                    .field("createdAt")
                    .gte("now-90d")
                    .lte("now")
                )
            )
        )
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(combinedQuery)
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

In applications, search terms and bounds typically arrive from a request DTO. Validate that min is not greater than max, cap page size, and normalize timestamps before building the query.

## 9. Range Queries Using the Criteria API

Spring Data Elasticsearch's Criteria API lets you construct property conditions without writing JSON or typed DSL directly.

Numeric range example:

~~~java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.domain.PageRequest;

Criteria criteria = Criteria.where("price")
    .greaterThanEqual(50)
    .lessThan(200);

CriteriaQuery query = new CriteriaQuery(criteria);
query.setPageable(PageRequest.of(0, 20));

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

Common comparison methods:

- greaterThan(value): strictly greater than.
- greaterThanEqual(value): greater than or equal to.
- lessThan(value): strictly less than.
- lessThanEqual(value): less than or equal to.
- between(lower, upper): interval between two values according to your API version's semantics.

When precise boundary control is needed, prefer two separate comparison calls instead of relying on assumptions about between.

### 9.1. Combining multiple Criteria conditions

~~~java
Criteria criteria = Criteria.where("price")
    .greaterThanEqual(50)
    .lessThan(200)
    .and("stockQuantity")
    .greaterThan(0);

CriteriaQuery query = new CriteriaQuery(criteria);
~~~

Criteria works well for dynamic user-selected filters. For example, if the user only enters a minimum price, the app only adds greaterThanEqual; if both bounds are supplied, it adds both conditions.

### 9.2. Range on dates/times

You can pass time values compatible with Spring Data converters, such as Instant or ISO-8601 strings:

~~~java
import java.time.Instant;

Instant start = Instant.parse("2026-03-01T00:00:00Z");
Instant end = Instant.parse("2026-04-01T00:00:00Z");

Criteria dateCriteria = Criteria.where("createdAt")
    .greaterThanEqual(start)
    .lessThan(end);

CriteriaQuery query = new CriteriaQuery(dateCriteria);
~~~

If using ISO-8601 strings, align offsets and formats with the mapping. When date math like now-30d/d or the time_zone option is needed, NativeQuery generally expresses it more directly and clearly than the Criteria API.

## 10. Range Queries in Repositories with `@Query`

For fixed queries, you can use the `@Query` annotation:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Query("""
        {
          "range": {
            "price": {
              "gte": ?0,
              "lt": ?1
            }
          }
        }
        """)
    List<ProductDocument> findByPriceRange(
        double minimum,
        double maximum
    );
}
~~~

`@Query` fits when query structure is stable. If the number of optional conditions varies per request, NativeQuery or CriteriaQuery is easier to build and maintain.

Do not manually concatenate user data into JSON strings. Use placeholders or typed builders to prevent escaping errors, type mismatches, and query injection risks.

## 11. Date Math and Time Units

Elasticsearch date math supports units such as:

| Symbol | Unit |
| --- | --- |
| y | years |
| M | months |
| w | weeks |
| d | days |
| h or H | hours |
| m | minutes |
| s | seconds |
| ms | milliseconds |

Examples:

- now-15m: 15 minutes ago.
- now-6h: 6 hours ago.
- now-2d: 2 days ago.
- now-1w: 1 week ago.
- now-3M: 3 months ago.

Case matters: M is months, m is minutes. Confusing these two symbols can make time intervals severely wrong.

### 11.1. Rounding in date math

The / operator rounds down to the start of a unit:

- now/d: start of the current day.
- now/w: start of the current week per Elasticsearch rules.
- now/M: start of the current month.
- now/y: start of the current year.

Example:

~~~json
{
  "range": {
    "createdAt": {
      "gte": "now/M",
      "lt": "now+1M/M"
    }
  }
}
~~~

This query selects data from the beginning of the current month up to before the beginning of the next month. When time_zone is provided, rounding can be performed in that time zone.

### 11.2. now is not the application server's local clock

The now expression is evaluated server-side by Elasticsearch. If the application runs in a different time zone from the cluster, do not assume now automatically uses the application's time zone.

For reports based on a user's calendar days:

1. Obtain the user's time zone from business configuration.
2. Compute start/end of the day or month in that time zone.
3. Convert to Instant/UTC or pass local date-times along with time_zone.
4. Use gte for start and lt for end.

This clarifies time boundaries and makes testing easier.

## 12. Sorting Results by Numbers and Dates/Times

A range query only filters documents. If results need to be sorted by price or creation date, add a separate sort clause.

Query DSL:

~~~json
{
  "query": {
    "range": {
      "price": {
        "gte": 50,
        "lt": 200
      }
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "createdAt": {
        "order": "desc"
      }
    }
  ]
}
~~~

You can use Spring Data Sort:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.domain.PageRequest;

NativeQuery query = NativeQuery.builder()
    .withQuery(priceRange)
    .withSort(Sort.by(
        Sort.Order.asc("price"),
        Sort.Order.desc("createdAt")
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Sort fields must have an appropriate type and be sortable in Elasticsearch. For text fields, sorting usually targets a keyword subfield rather than the analyzed text field.

## 13. Range Queries and Pagination

You can paginate with Pageable:

~~~java
PageRequest pageRequest = PageRequest.of(0, 20);

NativeQuery query = NativeQuery.builder()
    .withQuery(priceRange)
    .withPageable(pageRequest)
    .build();
~~~

Offset pagination works well for small and medium result sets. For very large datasets or deep scrolling, consider search_after with a stable sort or Point in Time. Range queries do not by themselves overcome deep pagination limits.

When sorting by multiple fields, include a stable tie-breaker to prevent result ordering from shifting across pages when multiple documents share identical sort values.

## 14. Range Queries, exists, and Missing Fields

A range query only matches documents that have a suitable value for the field. Documents missing the field do not match range.

Example finding documents with price 100 or higher:

~~~json
{
  "query": {
    "range": {
      "price": {
        "gte": 100
      }
    }
  }
}
~~~

To ensure the field exists and lies within the range, you can combine exists:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "exists": {
            "field": "price"
          }
        },
        {
          "range": {
            "price": {
              "gte": 100
            }
          }
        }
      ]
    }
  }
}
~~~

Pay special attention when using must_not:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "range": {
            "price": {
              "gte": 100
            }
          }
        }
      ]
    }
  }
}
~~~

This query can also match documents missing price because those documents do not match the negated range. If business logic wants only documents that have a price and fall outside the range, add exists inside filter.

## 15. Range Query vs. Range Aggregation

Two features have similar names but different purposes:

| Feature | Purpose |
| --- | --- |
| range query | Filters documents by a value interval |
| range aggregation | Groups documents into interval buckets for statistics |

Example range aggregation bucketing products by price:

~~~json
{
  "size": 0,
  "aggs": {
    "price_buckets": {
      "range": {
        "field": "price",
        "ranges": [
          { "to": 50 },
          { "from": 50, "to": 100 },
          { "from": 100, "to": 200 },
          { "from": 200 }
        ]
      }
    }
  }
}
~~~

Range aggregation returns document counts in each bucket and can power price distribution charts. When you merely want to select results within an interval, use a range query.

## 16. Range Queries on IP Fields and Range Types

Beyond numbers and dates, Elasticsearch also supports range queries on ordered types such as IP addresses and dedicated range field types.

### 16.1. IP ranges

Fields of type ip can be filtered by matching address or address range:

~~~json
{
  "query": {
    "range": {
      "client.ip": {
        "gte": "192.168.1.0",
        "lte": "192.168.1.255"
      }
    }
  }
}
~~~

This performs IP-type comparison rather than ordinary string comparison. Declare mapping type ip so Elasticsearch interprets it properly.

### 16.2. Range field types

Elasticsearch also provides dedicated range field types such as integer_range, long_range, float_range, double_range, date_range, and ip_range. These store an interval as a single field value, unlike a document having a scalar numeric field filtered by a range query.

With range fields, queries can use relations such as INTERSECTS, CONTAINS, or WITHIN depending on query and data type. That is a different model from common price or createdAt examples and requires dedicated mapping design.

## 17. Common Mistakes

**Using range queries on text fields.** Range does not perform numeric comparison on analyzed strings. Declare properly typed numeric/date mappings.

**Numeric values stored as keyword.** Comparison can fall back to lexicographical ordering instead of numeric ordering. Inspect mappings and create a new index if type changes are needed.

**Confusing gt with gte or lt with lte.** This drops or includes extra boundary documents. Document inclusive/exclusive rules clearly.

**Using between without confirming semantics.** When exact bounds matter, use separate comparison methods and test both boundary values.

**Using LocalDateTime without specifying time zones.** The same date-time string can represent different instants. Normalize to UTC or pass explicit offset/time_zone.

**Using m instead of M in date math.** m is minutes, M is months. Verify symbols and write tests for time expressions.

**Using now/d when business logic needs rolling 24 hours.** now/d is the start of the day, not 24 hours ago. Use now-24h for a rolling window.

**Using upper bound 23:59:59.999.** Can miss data with higher sub-millisecond precision. Use half-open intervals with lt at the start of the next period.

**Forgetting time zones when filtering calendar days.** A UTC day can be shifted from a user's local day. Compute start/end in the business time zone.

**Using double for currency without evaluating precision.** Consider storing minor units as long or using scaled_float with a suitable scaling factor.

**Range query matching multiple array elements unexpectedly.** Range matches if at least one element satisfies the condition. If correlation between fields of the same object is needed, use nested.

**Negating a range while forgetting missing fields.** must_not range can include documents lacking the field. Combine with exists when needed.

**Sorting on a text field.** Sorting should use keyword or appropriate numeric/date types. Inspect mappings and doc values.

## 18. Testing and Debugging

When a range query returns unexpected results, check:

1. Actual field mapping via _mapping.
2. Data inside _source of sample documents.
3. Data types and input formats.
4. Numeric units, e.g., cents vs. whole currency units.
5. Inclusive/exclusive boundaries.
6. Offsets and time zones of date-time values.
7. Date math and rounding behavior.
8. Whether the field exists on documents.
9. The final Query DSL sent to Elasticsearch.
10. Whether sorting and pagination alter displayed results unexpectedly.

You can validate query syntax using _validate/query:

~~~http
POST /catalog-products/_validate/query?explain=true
{
  "query": {
    "range": {
      "price": {
        "gte": 50,
        "lt": 200
      }
    }
  }
}
~~~

Then run _search against test data with boundary cases: price equal to 50, price equal to 200, price inside the range, price outside the range, and documents missing price.

For dates/times, create documents right at start, just before end, right at end, and on both sides of day boundaries in the relevant time zone to confirm semantics.

## 19. Complete Example: Searching Products by Text, Price, and Time

Suppose the requirements are:

- Product name matches user keywords.
- Price is greater than or equal to minimumPrice and less than maximumPrice.
- Only include products created within the user-selected time interval.
- Sort by ascending price, then newest creation date.
- Return 20 results per page.

Search criteria DTO:

~~~java
import java.time.Instant;

public record ProductSearchCriteria(
    String text,
    Double minimumPrice,
    Double maximumPrice,
    Instant createdFrom,
    Instant createdBefore,
    int page,
    int size
) {}
~~~

Service building the query:

~~~java
import co.elastic.clients.json.JsonData;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ProductDocument> search(
            ProductSearchCriteria criteria) {

        if (criteria.minimumPrice() != null
                && criteria.maximumPrice() != null
                && criteria.minimumPrice() >= criteria.maximumPrice()) {
            throw new IllegalArgumentException(
                "minimumPrice must be less than maximumPrice"
            );
        }

        if (criteria.page() < 0 || criteria.size() < 1
                || criteria.size() > 100) {
            throw new IllegalArgumentException("Invalid page or size");
        }

        Query query = Query.of(q -> q.bool(b -> {
            if (criteria.text() != null && !criteria.text().isBlank()) {
                b.must(m -> m.match(match -> match
                    .field("name")
                    .query(criteria.text())
                ));
            }

            if (criteria.minimumPrice() != null
                    || criteria.maximumPrice() != null) {
                b.filter(f -> f.range(r -> r.number(n -> {
                    n.field("price");
                    if (criteria.minimumPrice() != null) {
                        n.gte(JsonData.of(criteria.minimumPrice()));
                    }
                    if (criteria.maximumPrice() != null) {
                        n.lt(JsonData.of(criteria.maximumPrice()));
                    }
                    return n;
                })));
            }

            if (criteria.createdFrom() != null
                    || criteria.createdBefore() != null) {
                b.filter(f -> f.range(r -> r.date(d -> {
                    d.field("createdAt");
                    if (criteria.createdFrom() != null) {
                        d.gte(criteria.createdFrom().toString());
                    }
                    if (criteria.createdBefore() != null) {
                        d.lt(criteria.createdBefore().toString());
                    }
                    return d;
                })));
            }

            return b;
        }));

        NativeQuery nativeQuery = NativeQuery.builder()
            .withQuery(query)
            .withSort(Sort.by(
                Sort.Order.asc("price"),
                Sort.Order.desc("createdAt")
            ))
            .withPageable(PageRequest.of(
                criteria.page(),
                criteria.size()
            ))
            .build();

        return operations.search(nativeQuery, ProductDocument.class);
    }
}
~~~

This example illustrates combining optional conditions in the typed DSL. Builder names and JsonData types can vary across Elasticsearch Java API Client versions; use your project's dependencies. In real implementations, also validate that start date is not after end date, bound the interval span, and enforce business time-zone rules.

If a query has even more dynamic conditions, you can build a filter list beforehand and attach it to the bool query. For simple filters, CriteriaQuery can be shorter. For date math or specialized DSL options, NativeQuery is generally clearer.

## 20. Process for Choosing and Implementing Range Queries

When adding numeric or time filters to an application:

1. Identify the actual data type: integer, decimal, currency, calendar date, or instant.
2. Choose the matching mapping in Elasticsearch and verify the running index uses it.
3. Define units and precision clearly, e.g., cents, kilograms, milliseconds, or nanoseconds.
4. Decide whether lower/upper bounds are inclusive or exclusive.
5. For time ranges, standardize on UTC/offsets/time zones and use half-open intervals where appropriate.
6. Pick range queries in NativeQuery, CriteriaQuery, or `@Query` based on dynamism and complexity.
7. Combine full-text match in must with range filters in filter context where applicable.
8. Add sorting and pagination independently of range conditions.
9. Test boundary values and missing-field cases.
10. Monitor query latency and response size upon deployment.

Range queries are an essential filtering tool in full-text search. Accurate results rely on properly typed mappings, explicit boundary rules, and consistent time interpretation. When combined with full-text queries inside a bool query, applications can offer flexible price, quantity, and date filters while preserving relevance scoring for text search.

## 21. References

- [Elasticsearch - Range query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-range-query): gt/gte/lt/lte operators, date math, and time zone.
- [Elasticsearch - Date field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/date): date formats, epoch values, and how Elasticsearch stores timestamps.
- [Elasticsearch - Numeric field types](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/number): numeric types and mapping choices.
- [Elasticsearch - Date math](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/api-conventions#date-math): relative time expressions and rounding.
- [Spring Data Elasticsearch - Query methods and template](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): CriteriaQuery, NativeQuery, and query execution.
- [Spring Data Elasticsearch - Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html): entity mapping and field annotations.

Builder APIs may change across Spring Data Elasticsearch and Elasticsearch Java API Client versions. When implementing, verify against actual dependencies and the running index's mapping.
