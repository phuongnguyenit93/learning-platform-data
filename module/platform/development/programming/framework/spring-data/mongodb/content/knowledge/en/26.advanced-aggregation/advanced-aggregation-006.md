# Date/Time Expressions, Timezones, and Time-Based Grouping

## 1. The Problem: Which Timezone Does “June 1 Revenue” Belong To?

A sales system stores the payment timestamp of each order and needs revenue reports by **day, hour, week, and month**. For example, a store manager in Vietnam wants to view orders paid on **2025-06-01 in Vietnam time**.

Both of the following events happen near the day boundary:

~~~text
2025-05-31T16:59:00Z -> 2025-05-31 23:59 in Asia/Ho_Chi_Minh
2025-05-31T17:01:00Z -> 2025-06-01 00:01 in Asia/Ho_Chi_Minh
~~~

If grouped by **UTC date**, both events fall on May 31. If grouped by **Vietnam local date**, they fall on different days. Both outputs can be technically valid, yet only one answers the user's question.

That is why date/time expressions in MongoDB are about more than formatting an `Instant` into a string. You must align on:

- What type stores the event timestamp?
- Which timezone defines the business day?
- Should range filters query UTC or local calendar bounds?
- Do daily/weekly/monthly groupings use the exact same timezone?
- Does the region observe daylight saving time (DST)?
- How should a time bucket be represented so sorting and display remain unambiguous?

This lesson on **Date/Time Expressions, Timezones, and Time-Based Grouping** belongs to the **Advanced Aggregation** chapter of the **SPRING_DATA_MONGODB** module. The module focuses on connecting and mapping documents, working with `MongoTemplate` or repositories, query and aggregation design, indexing, transactions, reactive access, testing, and data performance diagnostics. The goal here is an aggregation pipeline that is accurate both semantically and at time boundaries.

After this lesson, you will be able to:

1. Distinguish BSON Date, UTC instant, local calendar date, and timezone.
2. Use **`$dateTrunc`**, **`$dateToString`**, **`$dateFromString`**, and related date operators.
3. Group by hour/day/week/month with the proper timezone.
4. Build **`$match`** filters using UTC intervals derived from local calendar bounds to leverage indexes.
5. Handle DST transitions, ISO weeks, year rollovers, malformed timestamps, and missing data.
6. Write aggregations using **`MongoTemplate`** and **`ReactiveMongoTemplate`**.
7. Test date boundaries, performance, and calculation consistency.

## 2. Data Model: Paid Orders

Suppose the **orders** collection has these documents:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  status: "PAID",
  createdAt: ISODate("2025-05-31T16:59:00Z"),
  totalMinor: NumberLong("100000")
}
~~~

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  tenantId: "shop-a",
  status: "PAID",
  createdAt: ISODate("2025-05-31T17:01:00Z"),
  totalMinor: NumberLong("200000")
}
~~~

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439013"),
  tenantId: "shop-a",
  status: "PAID",
  createdAt: ISODate("2025-06-01T01:00:00Z"),
  totalMinor: NumberLong("150000")
}
~~~

In these examples, **`createdAt`** is a BSON Date; money is stored in minor units to avoid floating-point errors when summing amounts. In a real system, choose the exact timestamp matching the metric: payment-date revenue should usually use **`paidAt`** instead of `createdAt`. Here `createdAt` is used for illustration, assuming we filter `status=PAID`.

Java entity:

~~~java
package com.example.orders;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id ObjectId id,
    String tenantId,
    String status,
    Instant createdAt,
    long totalMinor
) {}
~~~

**`Instant`** represents a point on the timeline; it carries no user timezone. **`@Document`** maps the entity to the collection. Field names used in the lesson's BSON pipelines match the stored field names.

### 2.1. One Dataset, Two Groupings

| UTC timestamp | UTC date | Date in Asia/Ho_Chi_Minh |
| --- | --- | --- |
| 2025-05-31T16:59Z | May 31 | May 31 |
| 2025-05-31T17:01Z | May 31 | June 01 |
| 2025-06-01T01:00Z | June 01 | June 01 |

For a June 01 report in Vietnam time, the result for those three documents is **2 orders** and **350,000 minor units**. Grouping by UTC date yields a different result.

## 3. BSON Date, Instant, LocalDate, and ZonedDateTime

A common source of bugs is treating every “date/time” value as the same type.

| Concept | Example | Meaning |
| --- | --- | --- |
| BSON Date | ISODate("2025-05-31T17:01:00Z") | An instant in time, stored as milliseconds since the Unix epoch. |
| Java Instant | 2025-05-31T17:01:00Z | An absolute instant; carries no calendar timezone rules. |
| LocalDate | 2025-06-01 | A calendar date; has no UTC boundaries without a timezone. |
| LocalDateTime | 2025-06-01T00:01 | A “wall-clock” time lacking timezone/offset. |
| ZoneId | Asia/Ho_Chi_Minh | Region identifier with historical and seasonal transition rules. |
| ZonedDateTime | 2025-06-01T00:01+07:00[Asia/Ho_Chi_Minh] | Local clock time paired with zone and corresponding offset. |
| OffsetDateTime | 2025-06-01T00:01+07:00 | Local clock time with numeric offset, without necessarily knowing zone rules. |

**BSON Date does not store a timezone name.** A single instant can be displayed in many timezones, while the underlying instant value stays identical.

~~~java
import java.time.Instant;
import java.time.ZoneId;

Instant moment = Instant.parse("2025-05-31T17:01:00Z");

var inVietnam = moment.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
var inNewYork = moment.atZone(ZoneId.of("America/New_York"));
~~~

Both variables represent the exact same **moment**, yet their local date and hour differ. That is why you must supply a timezone when grouping data by business calendar.

### 3.1. Avoid Storing Timestamps as Strings Whenever Possible

Avoid fields like:

~~~javascript
{ createdAt: "01/06/2025 00:01" }
~~~

This string carries no timezone, uses a locale-dependent format, and cannot be cleanly sorted or range-queried chronologically. If source data arrives as time strings, parse them into BSON Date on ingestion and store the source timezone separately if business rules need it.

### 3.2. Time Precision

BSON Date has **millisecond** precision. Java `Instant` can hold nanoseconds, which must conform to storage precision when converted to BSON Date. Never build grouping logic relying on nanosecond differences assuming MongoDB preserves nanoseconds inside a Date.

## 4. IANA Timezones vs. Fixed Offsets

MongoDB date operators accept a **`timezone`** parameter. Prefer IANA timezone database identifiers:

~~~text
Asia/Ho_Chi_Minh
America/New_York
Europe/Berlin
Asia/Tokyo
~~~

A fixed offset such as **`+07:00`** can express an offset from UTC, yet **offsets carry no seasonal or historical transition rules**.

For example:

- `Asia/Ho_Chi_Minh` currently uses UTC+07:00 and does not observe DST today.
- `America/New_York` alternates between UTC−05:00 and UTC−04:00.
- Any region can change offsets across years due to historical rules or legal changes.

**Never substitute `"-05:00"` for `America/New_York` across an entire year** if you want accurate local-time reporting.

### 4.1. Separating Data Timezone from Reporting Timezone

An order may be placed by a customer in another timezone while a store owner wants reports in the **store's timezone**. Define explicitly:

- Tenant/store timezone.
- Viewer timezone.
- Company-wide UTC standard.

If each viewer switches timezones, the same order can fall on different reporting dates. That is expected behavior when requirements are explicit, not a MongoDB bug.

### 4.2. Validating Timezone Inputs

When a client supplies a timezone:

1. Validate that the value is a valid timezone identifier.
2. Restrict it to business-allowed timezones.
3. Restrict changing timezones on finalized/closed reports.
4. Record the timezone used in response metadata.

Never interpolate untrusted timezone strings into JSON pipelines via string concatenation; construct BSON using `Document` or expression builders and validate inputs.

## 5. $dateTrunc: Bucketing Instants into Calendar Intervals

**`$dateTrunc`** truncates an instant to the start of a specified time unit, optionally taking a timezone.

~~~javascript
{
  $dateTrunc: {
    date: "$createdAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Common units include **hour, day, week, month, quarter, year** and smaller units. Depending on the unit, **`binSize`** or **`startOfWeek`** may also apply.

Example:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      createdAt: 1,
      localDayStart: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
]);
~~~

For `createdAt = 2025-05-31T17:01:00Z`, the start of the local day 2025-06-01 in Vietnam is:

~~~text
2025-06-01 00:00 in Asia/Ho_Chi_Minh
        = 2025-05-31T17:00:00Z
~~~

**The value returned by `$dateTrunc` is still a BSON Date representing a UTC instant**, not a string `"2025-06-01"` and without an attached timezone name. Keep this in mind when reading the group key in Java.

### 5.1. Do Not Assume dateTrunc Always Returns 00:00Z

~~~text
localDayStart = ISODate("2025-05-31T17:00:00Z")
~~~

This instant represents midnight **June 01 in Vietnam time**, not May 31 in the business calendar. If an API simply serializes ISO UTC without providing the timezone or local date label, users can easily misread it.

### 5.2. $dateTrunc Requires a Compatible MongoDB Version

Modern date operators such as **`$dateTrunc`**, **`$dateAdd`**, **`$dateSubtract`**, and **`$dateDiff`** were introduced in MongoDB 5.0. Check your project's actual MongoDB Server version; upgrading the Spring Data Java library alone does not make an older MongoDB Server understand new operators.

## 6. $dateToString: Formatting Buckets into Display Labels

Once you have the bucket start as a BSON Date, you can format a label in the same timezone:

~~~javascript
{
  $dateToString: {
    date: "$createdAt",
    format: "%Y-%m-%d",
    timezone: "Asia/Ho_Chi_Minh",
    onNull: null
  }
}
~~~

For instant `2025-05-31T17:01Z`, the local date label is **`"2025-06-01"`**.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 0,
      createdAt: 1,
      localDate: {
        $dateToString: {
          date: "$createdAt",
          format: "%Y-%m-%d",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
]);
~~~

Common format specifiers:

| Format pattern | Meaning |
| --- | --- |
| %Y-%m-%d | Date label as year-month-day |
| %Y-%m | Month label |
| %Y-%m-%d %H:00 | Local hour label |
| %G-W%V | ISO week with **ISO week-year**, where supported by server version |

**String labels are presentation data, not instants.** If you later need true elapsed durations between buckets, retain the `bucketStartUtc` Date field alongside the string.

### 6.1. Group by String or by Date?

You can group directly by `dateToString` formatted as `YYYY-MM-DD`, yet prefer **`dateTrunc` returning BSON Date** when you need to:

- Sort chronologically.
- Compute adjacent days or hours.
- Use a consistent bucket-start identifier.
- Distinguish repeated local hours on DST fall-back days.

A reporting API can expose both **`bucketStartUtc`** and **`localDate`**. For a daily report in a fixed timezone, `localDate` is a clean display label, though it should not replace all temporal context.

## 7. First Pipeline: Revenue by Local Day

Requirement: find **`shop-a`** Orders with status **`PAID`**, then aggregate by **day in `Asia/Ho_Chi_Minh`**.

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "shop-a",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 },
      revenueMinor: { $sum: "$totalMinor" }
    }
  },
  { $sort: { _id: 1 } },
  {
    $project: {
      _id: 0,
      bucketStartUtc: "$_id",
      localDate: {
        $dateToString: {
          date: "$_id",
          format: "%Y-%m-%d",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: 1,
      revenueMinor: 1
    }
  }
]);
~~~

Four pipeline steps:

1. **`$match`**: restricts tenant and status before computation.
2. **`$group`**: creates the group key from local day start and accumulates count/revenue.
3. **`$sort`**: sorts buckets chronologically by actual instant.
4. **`$project`**: formats the date label for the API while preserving the UTC bucket start.

With the three sample documents, the output looks like:

~~~javascript
[
  {
    bucketStartUtc: ISODate("2025-05-30T17:00:00Z"),
    localDate: "2025-05-31",
    orderCount: 1,
    revenueMinor: NumberLong("100000")
  },
  {
    bucketStartUtc: ISODate("2025-05-31T17:00:00Z"),
    localDate: "2025-06-01",
    orderCount: 2,
    revenueMinor: NumberLong("350000")
  }
]
~~~

**Note:** Outputs use BSON numeric types matching input types and summation. In Java DTOs, never assume every numeric field always deserializes to one specific `Number` subclass without verifying mapping.

### 7.1. Group First, Then Sort to Avoid Corrupting Totals

For daily summary metrics, **`$sort: {_id:1}`** after `$group` orders the resulting buckets. To find the top-N highest-revenue days, sort by `revenueMinor` after `$group`. Those are two distinct requirements.

Never place **`$limit` before `$group`** when computing totals across all matching orders; doing so aggregates only a subset.

## 8. Filtering a Local Day: Compute UTC Bounds Upfront

A user selects **June 01, 2025** in `Asia/Ho_Chi_Minh`. The target time span is:

~~~text
Local day start:      2025-06-01 00:00 +07
   -> UTC: 2025-05-31T17:00:00Z

Next local day start: 2025-06-02 00:00 +07
   -> UTC: 2025-06-01T17:00:00Z
~~~

The better query uses a half-open range **`[startInclusive, endExclusive)`**:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2025-05-31T17:00:00Z"),
    $lt: ISODate("2025-06-01T17:00:00Z")
  }
});
~~~

### 8.1. Why Use $lt Instead of $lte End-of-Day?

Avoid fabricating `"23:59:59.999"` with `$lte` whenever a half-open interval works:

- No guessing source millisecond/microsecond/nanosecond resolution.
- Adjacent daily intervals never overlap at boundaries.
- Combining days, weeks, or months is straightforward.
- Avoids bugs when DST makes a day longer or shorter than 24 hours.

Rule:

~~~text
startUtc <= createdAt < nextStartUtc
~~~

### 8.2. $match the Time Range Before $group

When a report covers a bounded date range, put the range filter on **raw BSON Date `createdAt`** in `$match` before `$dateTrunc`. This lets MongoDB leverage an index on the stored timestamp.

Conversely, a pipeline like:

~~~javascript
{
  $match: {
    $expr: {
      $eq: [
        {
          $dateToString: {
            date: "$createdAt",
            format: "%Y-%m-%d",
            timezone: "Asia/Ho_Chi_Minh"
          }
        },
        "2025-06-01"
      ]
    }
  }
}
~~~

must evaluate expressions across many documents and cannot leverage a `createdAt` range index directly. While semantically valid in niche cases, it should not be the default when UTC bounds are known upfront.

## 9. Java: Converting LocalDate to Timezone-Aware Instant Intervals

Use **`java.time`**, never add a fixed 86,400 seconds to find the next day's start.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2025, 6, 1);

Instant startInclusive = day.atStartOfDay(zone).toInstant();
Instant endExclusive = day.plusDays(1)
    .atStartOfDay(zone).toInstant();
~~~

This computes boundaries using `ZoneId` rules. In New York on DST spring-forward day, the span between two local midnights is only **23 hours**; on DST fall-back day, it is **25 hours**.

### 9.1. Filtering with MongoTemplate

~~~java
import java.util.Date;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("tenantId").is("shop-a")
        .and("status").is("PAID")
        .and("createdAt")
        .gte(Date.from(startInclusive))
        .lt(Date.from(endExclusive))
);
~~~

When the entity uses **`Instant`**, Spring Data still maps temporal queries to the proper BSON Date type. When building raw BSON, `Date.from` gives a clear BSON Date value for driver encoding.

### 9.2. Never Add 24 Hours Blindly

Wrong for zones with DST:

~~~java
Instant end = start.plusSeconds(24 * 60 * 60);
~~~

Right when you want **one calendar day** in a zone:

~~~java
Instant end = day.plusDays(1)
    .atStartOfDay(zone)
    .toInstant();
~~~

**One calendar day** differs from **a fixed 24-hour duration**. If a requirement genuinely means “the last 24 hours,” subtracting `Duration.ofHours(24)` is right; keep the two questions distinct.

## 10. Grouping by Week: Week Start and ISO Week-Year

A business week may begin on Monday or Sunday. With **`$dateTrunc`**, set `startOfWeek` when using `unit: "week"`:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "week",
          startOfWeek: "monday",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

The resulting `_id` is the **local calendar week start**, represented as a UTC BSON Date.

### 10.1. ISO Week-Year Does Not Always Equal Calendar Year

Days near New Year's Day can belong to the **previous or next ISO week-year**. For example, **2021-01-01** falls in **ISO week 53 of ISO year 2020**.

When using ISO week numbers, always pair **`isoWeekYear + isoWeek`**, never calendar `year` with ISO week.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      isoWeekYear: {
        $isoWeekYear: {
          date: "$createdAt",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      isoWeek: {
        $isoWeek: {
          date: "$createdAt",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      isoDayOfWeek: {
        $isoDayOfWeek: {
          date: "$createdAt",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
]);
~~~

**ISO weeks** begin on Monday. If a business defines weeks starting on Sunday or another weekday, apply a consistent business rule rather than calling every week number an ISO week.

### 10.2. Weekly Filters Also Need Exact Boundaries

Take the **`LocalDate` of the week start in the target timezone**, convert both endpoints to `Instant`, and apply `$match` on `createdAt`. For multi-month weekly reports, this avoids computing ISO week fields on every document prior to filtering.

## 11. Grouping by Month, Quarter, and Year

With **`$dateTrunc`**, changing granularity is just changing `unit`:

~~~javascript
// Start of local month.
{
  $dateTrunc: {
    date: "$createdAt",
    unit: "month",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

~~~javascript
// Start of local quarter.
{
  $dateTrunc: {
    date: "$createdAt",
    unit: "quarter",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

~~~javascript
// Start of local year.
{
  $dateTrunc: {
    date: "$createdAt",
    unit: "year",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Grouping by month:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "shop-a", status: "PAID" } },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "month",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orders: { $sum: 1 },
      revenueMinor: { $sum: "$totalMinor" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

If a company's fiscal year starts in April, a **calendar `quarter`** may not match the fiscal quarter. In that case, build a custom fiscal formula or a calendar dimension table defining period starts and ends.

### 11.1. Never Group by Month Number Alone

Grouping solely by **`$month(createdAt)`** merges June of every year into a single bucket. Across multiple years, include the **year** or use `$dateTrunc` with `unit: "month"` returning real month-start instants.

## 12. Grouping by Hour and Repeated Hours During DST

Grouping hourly:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "hour",
          timezone: "America/New_York"
        }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

In New York, on fall-back day **01:00–01:59 occurs twice** as clocks turn back from DST to standard time. Those two local hours correspond to two distinct UTC hour instants.

**If you group solely by the local string `"2025-11-02 01:00"`**, you can accidentally merge two distinct real hours into one group or lose ordering.

For hourly reports:

- Keep the bucket key as a UTC BSON Date when distinguishing each actual hour.
- Include timezone name and offset when presenting to users.
- Clarify whether business rules **merge same-labeled local hours** or keep them separate.
- Test DST transition days for supported regions.

### 12.1. Non-Existent Hours

On spring-forward DST day, a local clock hour can **not exist**. For example, clocks jump directly from 01:59 to 03:00.

Never generate 24 hourly labels for every day assuming each day has 24 hours. A “24-hour bar chart” needs explicit display handling on 23-hour and 25-hour days.

## 13. $dateFromString: Parsing Local Time Strings into Date

For legacy records holding strings like:

~~~javascript
{
  sourceLocalTime: "2025-06-01 00:15:00",
  sourceTimezone: "Asia/Ho_Chi_Minh"
}
~~~

To parse this string into an instant, specify format and timezone:

~~~javascript
db.legacy_orders.aggregate([
  {
    $set: {
      parsedAt: {
        $dateFromString: {
          dateString: "$sourceLocalTime",
          format: "%Y-%m-%d %H:%M:%S",
          timezone: "$sourceTimezone",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
~~~

When `sourceLocalTime = "2025-06-01 00:15:00"` in `Asia/Ho_Chi_Minh`, `parsedAt` becomes **`2025-05-31T17:15:00Z`**.

**`onError: null`** keeps the pipeline from failing on an unparseable string, though it can mask data-quality issues. During migrations, isolate and report failed rows rather than dropping them silently.

### 13.1. Do Not Specify Timezone Twice

If `dateString` already includes a timezone or offset such as `"2025-06-01T00:15:00Z"`, do not also supply a conflicting `timezone` parameter to reinterpret it. `$dateFromString` enforces strict rules on strings carrying embedded offsets; providing both can cause errors.

Best practice for source schemas:

- Strings **without timezone** → use the validated source timezone.
- Strings **with offset/UTC** → parse according to that offset/UTC.
- Timestamps with **unknown timezone** → do not guess when reporting accuracy is required.

### 13.2. Ambiguous Wall-Clock Times at DST

A string such as `"2025-11-02 01:30:00"` in `America/New_York` corresponds to **two distinct instants** on fall-back day. Without a stored offset or disambiguator, you cannot deterministically recover a single instant by guessing.

For critical ingestion paths, prefer sources supplying **UTC instants or explicit offsets at event time**.

## 14. $dateToParts and Calendar Components

If a report needs year, month, day, and hour split out in a timezone, MongoDB provides **`$dateToParts`**:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 0,
      localParts: {
        $dateToParts: {
          date: "$createdAt",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
]);
~~~

The result is an object with `year`, `month`, `day`, `hour`, `minute`, `second`, and `millisecond` fields in the chosen zone.

For ISO week calendars, check the **`iso8601`** option on compatible date-parts expressions; always verify output field names and semantics on your exact server version.

### 14.1. When to Use $dateToParts?

Useful when:

- A report buckets by **hour of day** (0–23) and day of week.
- An application needs numeric year/month/day fields for a composite key.
- Analyzing cyclical calendar patterns rather than contiguous interval buckets.

When the goal is simply **grouping by calendar day**, `$dateTrunc` is usually cleaner and preserves the bucket-start instant.

## 15. $dateAdd, $dateSubtract, and $dateDiff

Not every temporal query is a grouping problem. MongoDB also supports calendar-aware addition, subtraction, and differences.

### 15.1. $dateAdd: Adding Calendar Units

~~~javascript
db.orders.aggregate([
  {
    $project: {
      createdAt: 1,
      nextLocalDaySameTime: {
        $dateAdd: {
          startDate: "$createdAt",
          unit: "day",
          amount: 1,
          timezone: "America/New_York"
        }
      }
    }
  }
]);
~~~

When specifying **`timezone`** and units of day or larger, addition follows the zone's calendar rules, accounting for DST. It is not always equivalent to adding 86,400 seconds.

Example in New York:

~~~text
2025-03-09 00:00 (UTC-05) -> 2025-03-09T05:00:00Z
After 1 calendar day:
2025-03-10 00:00 (UTC-04) -> 2025-03-10T04:00:00Z

Elapsed instant difference: 23 hours
~~~

If business policy states **expires after exactly 24 hours**, use a 24-hour duration rather than “1 local calendar day.” If it states **expires at the same wall-clock time tomorrow in New York**, use calendar units with the proper timezone.

### 15.2. $dateSubtract: Calendar Subtraction

~~~javascript
{
  $dateSubtract: {
    startDate: "$createdAt",
    unit: "month",
    amount: 1,
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

For instance, “one month back” does not mean “subtract 30 days.” Months have different lengths, and month-end arithmetic follows clamping rules. Test 28/29/30/31-day edge cases and leap years against business expectations.

### 15.3. $dateDiff: Counting Unit Boundaries

~~~javascript
{
  $dateDiff: {
    startDate: "$createdAt",
    endDate: "$shippedAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

**`$dateDiff` with `unit="day"` counts calendar unit boundaries**, not elapsed hours divided by 24. It returns an integer counting boundaries crossed per operator rules.

Distinguish two questions:

| Question | Approach |
| --- | --- |
| How many actual hours elapsed? | Compute instant difference in hours/milliseconds. |
| How many New York day boundaries were crossed? | `$dateDiff` `unit: "day"`, `timezone: "America/New_York"`. |
| What is the Nth calendar day after order date? | `$dateAdd` `unit: "day"` in business timezone. |
| Exactly 24 hours after payment? | Add 24-hour duration; do not equate with calendar day. |

**Never put `$dateDiff` into an SLA contract without agreeing on business days, holidays, and timezone rules.** `$dateDiff` does not skip weekends or holidays automatically.

## 16. Grouping by Multi-Unit Intervals: binSize

For charts every 15 minutes or every 2 hours, **`$dateTrunc`** accepts **`binSize`**:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "minute",
          binSize: 15,
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orders: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Minute buckets align to 00, 15, 30, and 45 according to the reference point and operator truncation rules. For 15-minute charts, this is cleaner than slicing strings and formatting labels manually.

### 16.1. 7-Day Buckets Are Not Always Business Weeks

When requirements specify “weeks starting Monday,” prefer:

~~~javascript
{
  $dateTrunc: {
    date: "$createdAt",
    unit: "week",
    startOfWeek: "monday",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Do not substitute **`unit: "day", binSize: 7`** assuming it matches ISO weeks or business weeks. Seven-day bins and week boundaries anchor differently.

### 16.2. Do Not Blindly Use binSize for Custom Fiscal Calendars

A fiscal quarter starting outside January, a 4-4-5 retail calendar, or custom accounting cycles may not align with plain `$dateTrunc`. Define reporting periods from an approved calendar table and test period boundaries.

## 17. Implementing Daily Reports with MongoTemplate

The Spring Data MongoDB example below uses **`MongoTemplate`** and **`AggregationOperation`**. Stages are built with **`org.bson.Document`** to show BSON operators directly without relying on builder method names that can vary across library versions.

Because raw `Document`s are used, field names **`tenantId, status, createdAt, totalMinor`** in code must match **actual stored BSON names**. If entities use `@Field` renames, update stages accordingly or use entity-mapped aggregation APIs.

### 17.1. Result DTO

~~~java
package com.example.reports;

import java.time.LocalDate;

public record DailyOrderSummary(
    LocalDate localDate,
    long orderCount,
    long revenueMinor
) {}
~~~

The DTO exposes **`localDate`** in the selected timezone. A production API should also return metadata such as **`timezone`**, query start/end, and metric definition so consumers interpret numbers accurately.

### 17.2. Service with $match and $dateTrunc

~~~java
package com.example.reports;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;

public class DailyOrderReportService {

    private final MongoTemplate template;

    public DailyOrderReportService(MongoTemplate template) {
        this.template = template;
    }

    public List<DailyOrderSummary> report(
            String tenantId,
            LocalDate fromInclusive,
            LocalDate toExclusive,
            ZoneId zone) {

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant is required");
        }
        if (fromInclusive == null || toExclusive == null
                || !fromInclusive.isBefore(toExclusive)
                || zone == null) {
            throw new IllegalArgumentException("Invalid range/zone");
        }

        Instant start = fromInclusive.atStartOfDay(zone).toInstant();
        Instant end = toExclusive.atStartOfDay(zone).toInstant();

        AggregationOperation match = context ->
            new Document("$match",
                new Document("tenantId", tenantId)
                    .append("status", "PAID")
                    .append("createdAt",
                        new Document("$gte", Date.from(start))
                            .append("$lt", Date.from(end))));

        AggregationOperation group = context ->
            new Document("$group",
                new Document("_id",
                    new Document("$dateTrunc",
                        new Document("date", "$createdAt")
                            .append("unit", "day")
                            .append("timezone", zone.getId())))
                    .append("orderCount", new Document("$sum", 1))
                    .append("revenueMinor",
                        new Document("$sum", "$totalMinor")));

        AggregationOperation sort = context ->
            new Document("$sort", new Document("_id", 1));

        Aggregation pipeline =
            Aggregation.newAggregation(match, group, sort);

        List<Document> buckets = template.aggregate(
            pipeline,
            "orders",
            Document.class
        ).getMappedResults();

        return buckets.stream()
            .map(bucket -> toSummary(bucket, zone))
            .toList();
    }

    public static DailyOrderSummary toSummary(
            Document bucket, ZoneId zone) {

        LocalDate day = bucket.getDate("_id")
            .toInstant()
            .atZone(zone)
            .toLocalDate();

        long count =
            ((Number) bucket.get("orderCount")).longValue();
        long revenue =
            ((Number) bucket.get("revenueMinor")).longValue();

        return new DailyOrderSummary(day, count, revenue);
    }
}
~~~

**Key design points:**

1. Compute **`from/to`** from `LocalDate` and `ZoneId` before querying.
2. `$match` on actual Dates using **`[start, end)`** plus tenant/status.
3. `$group` using **`$dateTrunc`** `unit: "day"` and the same timezone.
4. `$sort` by `_id`, which is the bucket-start instant.
5. Convert `_id` Date back to `LocalDate` using **the exact same `ZoneId`** when building results.
6. Use **`Number.longValue()`** so mapping does not break depending on whether BSON accumulators emit int or long when values fit in `long`.

This example assumes **`totalMinor`** is stored as an integer and totals do not overflow `long`. If storing `Decimal128`, very large sums, or multiple currencies, choose appropriate output types and rounding rules—never add different currencies into a single revenue total.

### 17.3. Why Not Call dateToString and Group Immediately?

`dateToString` formats a display label, whereas **`dateTrunc` creates an instant-based bucket**. For local dates, either can work if contracts are explicit; for hourly reporting with DST, grouping by Date first preserves true chronological boundaries and avoids merging duplicate `01:00` labels.

### 17.4. Raw Stages and Field Mapping

The raw `AggregationOperation` stages above emit **literal BSON names**. If your Java entity uses:

~~~java
@Field("paid_at")
private Instant paidAt;
~~~

then a raw stage must reference **`"$paid_at"`**, not **`"$paidAt"`**. Entity-mapped aggregation operations can resolve Java property names; never mix the two without inspecting the final emitted BSON pipeline.

## 18. Using Spring Data Builders Instead of Raw Documents

Spring Data MongoDB includes aggregation builders such as:

~~~java
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.MatchOperation;
import org.springframework.data.mongodb.core.aggregation.SortOperation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.domain.Sort;

MatchOperation match = Aggregation.match(
    Criteria.where("tenantId").is("shop-a")
        .and("status").is("PAID")
);

SortOperation sort = Aggregation.sort(
    Sort.Direction.ASC, "_id"
);
~~~

Spring Data MongoDB also provides **`DateOperators`** for many temporal expressions. However, **exact method names** (such as `DateTrunc`, `DateToString`, `DateDiff`) and how `timezone`, `unit`, and nested expressions are passed vary across library versions.

When aiming for more strongly typed Java code:

1. Check the actual **`DateOperators`** API in your Spring Data MongoDB version.
2. Use **`Aggregation.project()`**, **`Aggregation.group()`**, and **`Aggregation.match()`** where they express your logic cleanly.
3. For operators without convenient builder support, fall back to a custom **`AggregationOperation`** returning BSON as in Section 17.
4. Inspect the generated BSON pipeline and compare with `mongosh`.
5. Never guess or write a nonexistent builder method just because its name resembles a MongoDB operator.

**Never build a multi-stage aggregation solely to use `DateOperators`.** For simple queries fetching documents within a day, a `MongoTemplate` range `Query` is lighter.

## 19. ReactiveMongoTemplate and Streaming Daily Results

In a reactive stack, keep the exact same date/timezone boundaries and pipeline while returning **`Flux`** instead of a synchronous `List`:

~~~java
import java.time.ZoneId;
import org.bson.Document;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import reactor.core.publisher.Flux;

public Flux<DailyOrderSummary> reportReactive(
        ReactiveMongoTemplate template,
        Aggregation pipeline,
        ZoneId zone) {

    return template.aggregate(
        pipeline, "orders", Document.class
    ).map(bucket ->
        DailyOrderReportService.toSummary(bucket, zone)
    );
}
~~~

Here **`pipeline`** is built from the same `$match`/`$group`/`$sort` stages as before, and **`toSummary`** is the static mapper. Spring WebFlux or the caller subscribes to the publisher to run the query.

### 19.1. Reactive Does Not Change Timezone Semantics

A pipeline specifying **`"Asia/Ho_Chi_Minh"`** in `$dateTrunc` does not revert to **UTC grouping** when executed via `ReactiveMongoTemplate`. MongoDB Server executes the operator with the supplied timezone.

### 19.2. Never Block or Collect Unboundedly

Avoid:

~~~java
// Avoid in reactive services/controllers.
var rows = template.aggregate(
    pipeline, "orders", Document.class
).collectList().block();
~~~

If an API requires a bounded result array (e.g., at most 31 daily buckets), **`collectList()`** after a bounded `$match` range can be reasonable inside a reactive chain, yet never call **`block()`** on an event-loop thread.

### 19.3. Each Subscription Can Re-Run the Aggregation

Do not call `subscribe()` yourself to “warm up” a publisher and then return it to a controller. That can double MongoDB load and yield differing results if documents are inserted or deleted between subscriptions.

## 20. Indexes and Pipeline Stage Ordering

A candidate index for tenant/status/time reports:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: 1
});
~~~

The idea is placing **equality fields** ahead of the range field so `$match` can use a compound index.

### 20.1. $match Before $group

~~~mermaid
flowchart LR
    A["Collection orders"] --> B["$match tenant/status/UTC range"]
    B --> C["$group by $dateTrunc(timezone)"]
    C --> D["$sort bucketStartUtc"]
    D --> E["Report DTO"]
~~~

For a report covering June 01–30 in Vietnam, compute UTC start/end for **the entire reporting window** and filter before grouping. Never compute `dateToString` across all historical documents first.

### 20.2. Why Projection Alone Does Not Make Queries Fast

Even if a pipeline returns only 30 summary rows, the server may still scan or read huge numbers of orders to sum revenue. Shrinking response size does not automatically shrink `$group` work or enable index usage in `$match`.

For frequent reports over billions of events, consider:

- Materialized daily summaries keyed by tenant/timezone/metric.
- Idempotent incremental processing with reconciliation.
- Time-series collections where appropriate.
- Retention, partitioning, and bounded query windows.

However, **summary caches** require policies for late-arriving orders, cancellations/refunds, and tenant timezone changes. Never just increment counters and call them “exact” if historical data can be amended.

### 20.3. Using explain("executionStats")

~~~javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "shop-a",
      status: "PAID",
      createdAt: {
        $gte: ISODate("2025-05-31T17:00:00Z"),
        $lt: ISODate("2025-06-30T17:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orders: { $sum: 1 }
    }
  }
]);
~~~

Inspect the execution path:

| Metric / Component | Question |
| --- | --- |
| `winningPlan` | Is MongoDB using the expected index? |
| `totalKeysExamined` | How many index keys were scanned? |
| `totalDocsExamined` | How many source documents were read? |
| `nReturned` | How many documents were returned/aggregated? |
| `SORT` stage | Is there an in-memory sort outside the index? |
| `GROUP` / aggregation stages | Is the pipeline processing a large intermediate set? |
| `executionTimeMillis` | What is latency under test conditions? |

Explain output formats vary across MongoDB versions and execution engines. Inspect actual results rather than writing code coupled to a rigid explain structure.

## 21. Days Without Data and Empty Buckets

`$group` creates groups only for matching documents. If June 02 has no Orders, the pipeline will **return no record for that date**.

Sample data:

~~~text
2025-06-01 -> 2 orders
2025-06-02 -> no orders
2025-06-03 -> 1 order
~~~

Typical `$group` result:

~~~json
[
  { "localDate": "2025-06-01", "orderCount": 2 },
  { "localDate": "2025-06-03", "orderCount": 1 }
]
~~~

For charts requiring a point on every day, **fill missing dates in the application layer** using `LocalDate`:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<LocalDate, DailyOrderSummary> byDate =
    reportRows.stream().collect(Collectors.toMap(
        DailyOrderSummary::localDate,
        Function.identity()
    ));

List<DailyOrderSummary> completed = fromInclusive
    .datesUntil(toExclusive)
    .map(day -> byDate.getOrDefault(
        day,
        new DailyOrderSummary(day, 0L, 0L)
    ))
    .toList();
~~~

This snippet assumes **`reportRows`, `fromInclusive`, and `toExclusive`** are available in the service. **`datesUntil`** iterates calendar `LocalDate`s without assuming every day is 24 hours long.

### 21.1. Use $densify or $fill?

MongoDB offers **`$densify`** and **`$fill`** on supported versions to fill series gaps according to rules. However, if local day-start buckets are represented by UTC instants spaced **23 or 25 hours apart across DST**, densifying by fixed **24-hour UTC** steps shifts the timestamps.

For reports by **calendar day per timezone**, filling with `LocalDate` in the API layer or using a verified business calendar is usually simpler and easier to test.

### 21.2. Distinguishing Zero from Missing

No documents on June 02 can be displayed as **0 orders**, provided source ingestion is complete. In pipelines with delayed ingestion, missing can mean “data not arrived yet” rather than truly zero. Reporting contracts should make this distinction explicit.

## 22. Critical Timezone and Data Bugs

| Symptom | Common cause | Fix |
| --- | --- | --- |
| 00:05 order counted in previous day | Grouped by UTC instead of business timezone | Pass `timezone` to `$dateTrunc` |
| `localDate` off by one day | Serialized `bucketStartUtc` directly as local date | Convert bucket instant via `ZoneId` before extracting `LocalDate` |
| Range filter misses early-morning orders | `$match` used UTC 00:00 instead of local midnight | Compute UTC bounds from `LocalDate + ZoneId` |
| Two reports for same day show different totals | Different timezones used | Publish timezone and metric definition |
| Missing/merged hours during DST | Grouped by local clock string | Keep UTC bucket key and include offset |
| DST days treated as 24h everywhere | Added 86,400 seconds | Compute next midnight via `atStartOfDay(zone)` |
| Year-end week assigned wrong year | Used calendar year with `isoWeek` | Pair `isoWeekYear + isoWeek` |
| June of two years merged together | Grouped solely by `$month` | Use `$dateTrunc` `month` or year + month |
| `$dateTrunc` unrecognized | MongoDB Server too old | Verify MongoDB 5.0+ server requirement |
| `$dateFromString` fails | Format/offset/timezone mismatch | Normalize source; `onError` + data error reporting |
| Many documents land in `null` bucket | `createdAt` is null/missing/wrong type | Check `$type` and validate before grouping |
| “Revenue” numbers look wrong | Used `createdAt` when business expects `paidAt` | Match event timestamp field to metric definition |
| Very slow `$group` | Missing `$match` index or filter placed after date expr | Range-match on stored Date before grouping |
| Ambiguous local hour labels | Plain `HH` string without offset | Include UTC bucket / offset in response |
| Wrong monetary totals | Mixed currencies or used `double` | Use minor units/`Decimal128` and group by currency |
| Tests differ across environments | Divergent timezone/driver/server rules | Standardize environment; test DST and zone data |

### 22.1. Pipeline Must Handle Malformed Timestamps

If legacy records contain String or null `createdAt`, consider filtering by type:

~~~javascript
{
  $match: {
    tenantId: "shop-a",
    status: "PAID",
    createdAt: { $type: "date" }
  }
}
~~~

This excludes non-BSON-Date records from the metric, **yet it does not repair underlying data**. Reports should track how many documents were skipped due to invalid schema so operators can remediate them.

When running `$dateFromString` migrations, never set `onError: null` and silently classify null records as “unknown date” without reporting them.

## 23. MongoDB Integration Testing: Vietnam Day Boundaries

Testing a Java timezone helper alone is insufficient: you must prove MongoDB evaluates `$dateTrunc` and UTC filters consistently.

JUnit 5 example using the Spring Boot test slice and a test MongoDB instance:

~~~java
package com.example.reports;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;
import java.util.List;
import java.util.UUID;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import com.mongodb.client.model.Filters;

@DataMongoTest
class DailyOrderReportTest {

    @Autowired
    MongoTemplate template;

    private Document order(
            String tenant, String instant, long totalMinor) {
        return new Document("_id", new ObjectId())
            .append("tenantId", tenant)
            .append("status", "PAID")
            .append("createdAt",
                Date.from(Instant.parse(instant)))
            .append("totalMinor", totalMinor);
    }

    @Test
    void groupsByLocalDayInsteadOfUtcDay() {
        String tenant = "TEST-" + UUID.randomUUID();
        var collection = template.getCollection("orders");

        try {
            collection.insertMany(List.of(
                order(tenant, "2025-05-31T16:59:00Z", 100_000L),
                order(tenant, "2025-05-31T17:01:00Z", 200_000L),
                order(tenant, "2025-06-01T01:00:00Z", 150_000L)
            ));

            DailyOrderReportService service =
                new DailyOrderReportService(template);

            List<DailyOrderSummary> rows = service.report(
                tenant,
                LocalDate.of(2025, 6, 1),
                LocalDate.of(2025, 6, 2),
                ZoneId.of("Asia/Ho_Chi_Minh")
            );

            assertThat(rows).hasSize(1);
            assertThat(rows.get(0).localDate())
                .isEqualTo(LocalDate.of(2025, 6, 1));
            assertThat(rows.get(0).orderCount())
                .isEqualTo(2L);
            assertThat(rows.get(0).revenueMinor())
                .isEqualTo(350_000L);
        } finally {
            collection.deleteMany(Filters.eq("tenantId", tenant));
        }
    }
}
~~~

This test verifies that the **`16:59Z`** document belongs to May 31 in Vietnam and is **excluded** from the June 01 report, while **`17:01Z`** and **`01:00Z`** are included.

**Never run tests against a production database.** Use a test MongoDB server/instance supporting `$dateTrunc` and isolate fixtures by tenant for clean teardown.

### 23.1. Testing DST and 23-Hour Days

A pure Java test verifying UTC boundary calculation:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import org.junit.jupiter.api.Test;

@Test
void newYorkDstStartHasTwentyThreeHours() {
    ZoneId zone = ZoneId.of("America/New_York");
    LocalDate day = LocalDate.of(2025, 3, 9);

    Instant start = day.atStartOfDay(zone).toInstant();
    Instant end = day.plusDays(1)
        .atStartOfDay(zone).toInstant();

    assertThat(start)
        .isEqualTo(Instant.parse("2025-03-09T05:00:00Z"));
    assertThat(end)
        .isEqualTo(Instant.parse("2025-03-10T04:00:00Z"));
    assertThat(Duration.between(start, end).toHours())
        .isEqualTo(23L);
}
~~~

To verify MongoDB behavior, seed events right around **`start/end`** of that day and assert `$dateTrunc` with `America/New_York` produces the right `localDay`. Repeat for the **25-hour** fall-back day.

### 23.2. Additional Test Matrix

| Case | Expected |
| --- | --- |
| 1 second before local midnight | Does not belong to new day |
| Exact local midnight | Belongs to new day |
| Exact next local midnight | Excluded from previous day due to `endExclusive` |
| Two Orders on same UTC date, different local dates | Grouped separately by timezone |
| 23-hour DST day | Not miscounted by adding 24h |
| 25-hour DST day | Handles repeated local hour |
| Jan 01 falling in prior ISO week-year | Accurate ISO week label |
| Document with null `createdAt` | Not silently merged into a real date bucket |
| Data containing String timestamps | Normalized or flagged per error policy |
| Order from another tenant or status | Excluded from report |
| Report with zero Orders | Returns empty or zero-filled per contract |
| Very large amounts / multiple currencies | Clear numeric/currency policy |
| Invalid `ZoneId` | Request rejected |
| Server lacking `$dateTrunc` | Compatibility verified before deployment |

## 24. Practice Exercises

### Exercise 1: Which Day Does It Group Into?

`createdAt = 2025-05-31T17:30:00Z`. What is the date in `Asia/Ho_Chi_Minh`?

**Answer:** `2025-06-01`, because local time is 00:30 on June 01, 2025.

### Exercise 2: Timezone-Aware $dateTrunc

Write an expression yielding the start of day in Vietnam:

~~~javascript
{
  $dateTrunc: {
    date: "$createdAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

**Note:** The returned value is a BSON Date/instant, not a `YYYY-MM-DD` string.

### Exercise 3: Filtering Exactly One Day

Requirement: June 01, 2025 in `Asia/Ho_Chi_Minh`. Which UTC range is correct?

**Answer:** `[2025-05-31T17:00:00Z, 2025-06-01T17:00:00Z)`. Use `$gte` for start and `$lt` for end.

### Exercise 4: Avoid Fixed 24h Offsets

In New York, 2025-03-09 starts at `05:00Z` and the next day starts at `04:00Z`. Why is it only 23 hours?

**Answer:** Clocks spring forward for daylight saving time, skipping one local hour. A calendar day is not always 24 hours long.

### Exercise 5: ISO Week

Which ISO week-year and ISO week does 2021-01-01 belong to?

**Answer:** ISO week-year **2020**, ISO week **53**. Always pair `isoWeekYear` and `isoWeek` with the same timezone.

### Exercise 6: Months Across Multiple Years

A pipeline groups solely by **`$month(createdAt)`**. What happens to June data from 2024 and 2025?

**Answer:** Both merge into group 6. Use `$dateTrunc` `unit: "month"` or a composite key with both year and month.

### Exercise 7: Date Addition Expression

A business rule requires expiration “at the same local time tomorrow.” Is adding 86,400 seconds always accurate?

**Answer:** No, not in regions with DST. Add one calendar day with a timezone, e.g., `$dateAdd` `unit: "day"`, `amount: 1`, and the appropriate `timezone`.

### Exercise 8: dateFromString

A source stores `"2025-06-01 00:15:00"` without a timezone. Can the exact instant be determined?

**Answer:** Not without knowing the source timezone. With `Asia/Ho_Chi_Minh`, it parses to `2025-05-31T17:15:00Z`.

### Exercise 9: Indexes and $match

A report only needs June, yet the pipeline computes `dateToString` across the whole collection before filtering. How should it be improved?

**Answer:** Compute UTC start/end for June in the business timezone, `$match` tenant/status/`createdAt` before `$group`, and evaluate a matching compound index.

### Exercise 10: Hourly Grouping with DST

Why shouldn't you always group by `"%Y-%m-%d %H"` in `America/New_York`?

**Answer:** On DST fall-back day, two distinct instants share the local label `01:00`. Keep the UTC bucket key and include offset/zone when displaying.

### Exercise 11: Days Without Data

`$group` returns June 01 and June 03, skipping June 02. Must `$group` emit a zero bucket for June 02?

**Answer:** No. `$group` emits buckets only for existing data; fill calendar gaps in the API layer or with a verified aggregation strategy if empty days must be displayed.

### Exercise 12: Java Conversion

From **`LocalDate(2025-06-01)`** and `ZoneId("Asia/Ho_Chi_Minh")`, compute both bounds:

~~~java
Instant start = day.atStartOfDay(zone).toInstant();
Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();
~~~

**Explanation:** Calculation follows local calendar rules rather than adding a fixed 24 hours.

### Exercise 13: Reactive

`ReactiveMongoTemplate.aggregate` returns a `Flux`, and you want DTOs per bucket. Should you `block()` before mapping?

**Answer:** No. Use **`.map(...)`** on the `Flux` and let WebFlux/caller subscribe; bound the query range in MongoDB upfront.

### Exercise 14: Wrong Revenue Timestamp

An Order is created on May 31 and paid on June 01. Which field should a payment-date revenue report group by?

**Answer:** **`paidAt`**, if that matches the metric definition. Never use `createdAt` merely because it happens to exist.

## 25. Pre-Production Checklist for Time-Based Reports

- **Metric:** Do you distinguish `createdAt`, `paidAt`, `canceledAt`, and `refundedAt`?
- **BSON type:** Are timestamps truly stored as BSON Date?
- **Timezone:** Using UTC, tenant timezone, or viewer timezone?
- **Timezone ID:** Are IANA IDs validated and governed by change policies?
- **Boundaries:** Are `startInclusive`/`endExclusive` computed from local calendar rules?
- **Pipeline:** Is the Date-range `$match` placed before grouping expressions?
- **Buckets:** Does `$dateTrunc` specify the right `unit`, `binSize`, `startOfWeek`, and `timezone`?
- **Labels:** Does the API expose timezone and avoid confusing UTC bucket start with local date?
- **DST:** Have 23-hour/25-hour days and repeated local hours been tested?
- **ISO week:** Are `isoWeekYear` and `isoWeek` paired properly?
- **Months/quarters:** Are standard calendar quarters distinguished from fiscal calendars?
- **Malformed data:** Are null or wrong-typed timestamp documents tracked?
- **Late data:** Do summary caches handle late arrivals or adjustments?
- **Zero buckets:** Is missing-day display behavior agreed upon?
- **Numerics:** Using minor units/`Decimal128` and keeping currencies separate?
- **Version:** Does MongoDB Server support all date operators in use?
- **Indexes:** Checked `winningPlan`, `keysExamined`, and `docsExamined`?
- **Reactive:** Pipeline non-blocking and not double-subscribed?
- **Testing:** Integration tests covering day boundaries and different timezones?

## 26. Summary

1. **BSON Date is an instant**, storing neither timezone nor local calendar date.
2. **Timezone defines day/week/month boundaries**, so the same dataset yields different groupings across regions.
3. **`$dateTrunc`** produces BSON Date bucket keys; **`$dateToString`** formats display labels; they serve different roles.
4. **`$dateFromString`** parses time strings using explicit format/timezone rules; handle bad inputs and DST carefully.
5. **`$dateAdd`, `$dateSubtract`, and `$dateDiff`** must be chosen for calendar vs. duration semantics without equating a day to 24 hours.
6. **Filtering by UTC `[start, end)`** derived from `LocalDate + ZoneId` avoids boundary errors and enables index usage.
7. **ISO weeks must be paired with ISO week-years**, making year boundaries critical test cases.
8. **Hourly grouping in DST zones should preserve UTC bucket keys** so repeated hours are not collapsed.
9. **`MongoTemplate` and `ReactiveMongoTemplate` share identical MongoDB semantics**, differing only in synchronous vs. publisher execution.
10. **`$match`, indexes, `explain`, and bounded reporting ranges** matter far more than merely trimming output fields.
11. **`$group` never creates empty buckets automatically**; zero-filling requires an explicit calendar and data-completeness policy.
12. **Integration testing time boundaries against real MongoDB** protects reports from subtle timezone, schema, and version regressions.

Mastering **date/time expressions, timezones, and time-based grouping** enables **`SPRING_DATA_MONGODB`** services to produce aggregation reports aligned with business calendars, handle DST and UTC conversions accurately, and deliver testable, performant implementations across `MongoTemplate`, repositories, and reactive access.
