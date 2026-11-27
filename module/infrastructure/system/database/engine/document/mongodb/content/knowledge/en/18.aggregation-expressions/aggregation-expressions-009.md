# Date/Time Calculations, Timezones, $dateTrunc, $dateAdd, and $dateDiff in MongoDB

An application frequently stores event timestamps, schedules appointments, calculates payment due dates, aggregates daily revenue, or measures request processing times. Operations that sound simple—"group orders by day", "add one month", "count days between two timestamps"—can easily go wrong when data involves **timezones**, calendar rules, months of varying lengths, and **Daylight Saving Time (DST)** transitions.

MongoDB provides **date/time aggregation expressions** to operate directly on BSON Dates, among which three key operators are:

- **$dateTrunc**: truncates a timestamp to the **start of the time interval** containing it, such as the start of a day, week, or month in a given timezone.
- **$dateAdd**: adds or subtracts a **number of calendar/time units** to a timestamp, accounting for timezone when specified.
- **$dateDiff**: computes the **count of unit boundaries** crossed between two timestamps, rather than simply dividing milliseconds by a fixed length for every unit.

This lesson focuses on using these expressions properly in MongoDB aggregation, distinguishing absolute instants from local calendars, avoiding day/month boundary bugs, analyzing performance, and applying them in Java/Spring Data MongoDB.

The operators **$dateTrunc**, **$dateAdd**, and **$dateDiff** were introduced in **MongoDB 5.0**. Verify your actual server version before applying them. The examples below use **mongosh** and a dedicated practice database.

## 1. Foundations: BSON Date, UTC, and Timezones

### 1.1. BSON Date Represents an Instant in Time

In MongoDB, a BSON Date is a timestamp value stored as milliseconds relative to the Unix epoch, anchored in UTC. Example:

~~~javascript
{
  _id: "E01",
  occurredAt: ISODate("2026-11-14T18:30:00Z")
}
~~~

The **Z** suffix stands for UTC. This is an **absolute instant in time**. It can be displayed differently depending on timezone:

| Timezone | Local time corresponding to the instant above |
|---|---|
| UTC | 2026-11-14 at 18:30 |
| Asia/Ho_Chi_Minh (UTC+07:00) | 2026-11-15 at 01:30 |
| America/New_York (EST, UTC−05:00 at this date) | 2026-11-14 at 13:30 |

**Key point:** a BSON Date value does not carry the user's original timezone name. Timezones are applied **when interpreting or computing**. If an application needs to remember "an appointment at 9:00 AM New York time," store the converted UTC instant alongside the business timezone if re-interpretation or calendar math is needed.

This difference in calendar date across timezones is why you must not group events purely by UTC day when a report requires "local day."

### 1.2. ISODate() Differs from a Date String

These two values do not share the same type:

~~~javascript
{ occurredAt: ISODate("2026-11-14T18:30:00Z") }

{ occurredAt: "2026-11-14T18:30:00Z" }
~~~

The first value is a BSON Date. The second is a BSON String. Do not assume date/time operators automatically convert every String into a Date.

If a data source stored ISO-8601 strings, you may need explicit conversion via **$toDate** or **$dateFromString** after establishing the format and error policy. Long-term, store timestamps consistently as BSON Dates and enforce types using schema validation.

### 1.3. Timezones Can Be IANA Names or UTC Offsets

In date/time expressions supporting the `timezone` parameter, MongoDB accepts valid timezone identifiers such as:

~~~javascript
timezone: "Asia/Ho_Chi_Minh"
timezone: "America/New_York"
timezone: "UTC"
timezone: "+07:00"
~~~

An IANA name like **America/New_York** applies DST rules for the evaluated date. A fixed offset like **"-05:00"** does not automatically know that New York switches to UTC−04:00 in summer.

**Never store or ingest local times without a timezone assuming MongoDB knows which city they belong to.** When a day has a skipped hour or a repeated hour during DST transitions, the application must define how local times are resolved.

### 1.4. Vietnam Time and UTC

With **Asia/Ho_Chi_Minh**, local time corresponds to UTC+07:00 and does not observe DST. Example:

~~~text
UTC:                 2026-11-14 17:00:00Z
Asia/Ho_Chi_Minh:    2026-11-15 00:00:00+07:00
~~~

Therefore, "start of Nov 15 in Vietnam time" is **17:00 UTC on Nov 14**. If you use a 00:00 UTC boundary to aggregate a day in Vietnam, totals will place certain events into the wrong day.

## 2. Preparing Practice Data

Select a dedicated database:

~~~javascript
use aggregation_dates_lab
~~~

Assume the **events** collection has no documents yet. Insert data with UTC timestamps, types, and amounts for reporting:

~~~javascript
db.events.insertMany([
  {
    _id: "E01",
    type: "ORDER",
    amount: NumberDecimal("100.00"),
    occurredAt: ISODate("2026-11-13T16:30:00Z")
  },
  {
    _id: "E02",
    type: "ORDER",
    amount: NumberDecimal("200.00"),
    occurredAt: ISODate("2026-11-13T17:30:00Z")
  },
  {
    _id: "E03",
    type: "LOGIN",
    amount: NumberDecimal("0.00"),
    occurredAt: ISODate("2026-11-14T01:00:00Z")
  },
  {
    _id: "E04",
    type: "ORDER",
    amount: NumberDecimal("75.00"),
    occurredAt: ISODate("2026-11-14T16:59:59Z")
  },
  {
    _id: "E05",
    type: "ORDER",
    amount: NumberDecimal("50.00"),
    occurredAt: ISODate("2026-11-14T17:00:00Z")
  },
  {
    _id: "E06",
    type: "ORDER",
    amount: NumberDecimal("40.00"),
    occurredAt: ISODate("2026-11-15T03:15:00Z")
  },
  {
    _id: "E07",
    type: "LOGIN",
    amount: NumberDecimal("0.00"),
    occurredAt: ISODate("2026-11-15T16:00:00Z")
  },
  {
    _id: "E08",
    type: "ORDER",
    amount: NumberDecimal("90.00"),
    occurredAt: ISODate("2026-11-15T17:00:00Z")
  }
])
~~~

These UTC values are intentionally placed near **17:00Z**, the start of a new day in Vietnam.

| ID | UTC Timestamp | Local Date (Asia/Ho_Chi_Minh) | Type | Amount |
|---|---|---|---|---:|
| E01 | 11/13 16:30 | 11/13 | ORDER | 100 |
| E02 | 11/13 17:30 | 11/14 | ORDER | 200 |
| E03 | 11/14 01:00 | 11/14 | LOGIN | 0 |
| E04 | 11/14 16:59:59 | 11/14 | ORDER | 75 |
| E05 | 11/14 17:00 | 11/15 | ORDER | 50 |
| E06 | 11/15 03:15 | 11/15 | ORDER | 40 |
| E07 | 11/15 16:00 | 11/15 | LOGIN | 0 |
| E08 | 11/15 17:00 | 11/16 | ORDER | 90 |

View data in chronological order:

~~~javascript
db.events.find().sort({ occurredAt: 1 });
~~~

**Note:** these examples assume an empty collection where `insertMany` runs once. Re-running causes duplicate `_id` errors. Expected counts and IDs below are based on this exact dataset, not on the default order of `find()`.

## 3. Where Do Date/Time Expressions Fit in Aggregation?

All three operators are **aggregation expressions**, commonly appearing inside stages such as **$project**, **$set/$addFields**, **$group**, and **$match combined with $expr**.

Example:

~~~javascript
db.events.aggregate([
  {
    $project: {
      _id: 1,
      occurredAt: 1,
      localDay: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
])
~~~

In aggregation:

- **"$occurredAt"** is a field reference expression reading the document's `occurredAt` field.
- **unit: "day"** is a string specifying the calculation unit.
- **timezone** governs the local calendar during calculation.
- **$dateTrunc** returns a **BSON Date**, not a string like `"2026-11-14"`.

Do not confuse this syntax with a query operator on a field:

~~~javascript
// This syntax does not express a simple date comparison.
// $dateTrunc belongs in an aggregation expression context.
{ occurredAt: { $dateTrunc: { unit: "day" } } }
~~~

If you want to filter based on a computed date, use **$expr** or compute a field in an earlier stage and **$match** in a later stage. If you can filter directly with a BSON Date range, that is usually far more index-friendly.

## 4. $dateTrunc: Truncating a Timestamp to the Start of an Interval

**$dateTrunc** finds the **start of the time interval** containing a timestamp based on a unit such as day, week, month, hour, or minute. Think of it as rounding **down to the appropriate calendar boundary**, not rounding to the nearest mark.

Syntax:

~~~javascript
{
  $dateTrunc: {
    date: <dateExpression>,
    unit: <timeUnit>,
    binSize: <positiveInteger>,    // optional, defaults to 1
    timezone: <timezone>,          // optional, defaults to UTC
    startOfWeek: <dayOfWeek>       // applies only when unit: "week"
  }
}
~~~

Common unit values include **"year"**, **"quarter"**, **"month"**, **"week"**, **"day"**, **"hour"**, **"minute"**, **"second"**, and **"millisecond"**. **unit** specifies the calendar level to truncate to; **binSize** groups into multi-unit buckets such as 15 minutes or 2 months.

### 4.1. Comparing Against Slicing Date Strings

Do not think `$dateTrunc` simply truncates an ISO string:

~~~text
UTC timestamp:                 2026-11-13 17:30Z
Vietnam time:                  2026-11-14 00:30+07
Start of day in Vietnam time:  2026-11-14 00:00+07
Resulting Date in UTC:         2026-11-13 17:00Z
~~~

`$dateTrunc` returns the **Date corresponding to the local boundary converted back to UTC**. When viewing the output directly as an `ISODate`, the hour may look like "17:00 of the previous day"; that is the exact right result.

### 4.2. $dateTrunc Example in UTC

~~~javascript
db.events.aggregate([
  {
    $project: {
      _id: 1,
      occurredAt: 1,
      utcDay: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day"
        }
      }
    }
  },
  { $sort: { occurredAt: 1 } }
])
~~~

For E02 with `occurredAt = 2026-11-13T17:30:00Z`, `utcDay` is **2026-11-13T00:00:00Z**. This is the start of the UTC day, not the start of the day in Vietnam time.

### 4.3. $dateTrunc Example in Asia/Ho_Chi_Minh

~~~javascript
db.events.aggregate([
  {
    $project: {
      _id: 1,
      occurredAt: 1,
      vietnamDay: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  },
  { $sort: { occurredAt: 1 } }
])
~~~

Sample values:

| Document | occurredAt UTC | vietnamDay UTC | Corresponding local date |
|---|---|---|---|
| E01 | 11/13 16:30Z | 11/12 17:00Z | 11/13 at 00:00 |
| E02 | 11/13 17:30Z | 11/13 17:00Z | 11/14 at 00:00 |
| E04 | 11/14 16:59:59Z | 11/13 17:00Z | 11/14 at 00:00 |
| E05 | 11/14 17:00Z | 11/14 17:00Z | 11/15 at 00:00 |
| E08 | 11/15 17:00Z | 11/15 17:00Z | 11/16 at 00:00 |

The contrast between E04 and E05 is striking: they are only **one second** apart, yet fall on **two different local days**.

### 4.4. Grouping by Start of Hour

~~~javascript
db.events.aggregate([
  {
    $project: {
      _id: 1,
      localHourStart: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "hour",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
])
~~~

For E02 at 00:30 on Nov 14 Vietnam time, the result represents **00:00 local time**, which corresponds to UTC **2026-11-13T17:00:00Z**.

### 4.5. Using binSize for 15-Minute Buckets

~~~javascript
db.events.aggregate([
  {
    $project: {
      _id: 1,
      quarterHour: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "minute",
          binSize: 15,
          timezone: "UTC"
        }
      }
    }
  }
])
~~~

A standalone calculation:

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      example: {
        $dateTrunc: {
          date: ISODate("2026-11-14T01:37:40Z"),
          unit: "minute",
          binSize: 15
        }
      }
    }
  }
])
~~~

The value of `example` is **2026-11-14T01:30:00Z**. Timestamps from 01:30:00 up to (not including) 01:45:00 fall into the same 15-minute bucket.

**binSize is the number of units per bucket**, not the number of documents per group. Combine `binSize` with `unit: "hour"` for 2-hour blocks, `unit: "month"` for bi-monthly blocks, and so on.

### 4.6. startOfWeek When unit Is week

A weekly report must define **which day starts the week**. With `$dateTrunc`:

~~~javascript
{
  $dateTrunc: {
    date: "$occurredAt",
    unit: "week",
    timezone: "Asia/Ho_Chi_Minh",
    startOfWeek: "monday"
  }
}
~~~

If `startOfWeek` is omitted, MongoDB uses **Sunday** as the start of the week for `$dateTrunc`. Never assume weeks default to ISO weeks (Monday start) across queries.

Example for **2026-11-14T12:00:00Z** (Saturday):

| startOfWeek | Start of week UTC when timezone = UTC |
|---|---|
| "sunday" | 2026-11-08T00:00:00Z |
| "monday" | 2026-11-09T00:00:00Z |

With timezone **Asia/Ho_Chi_Minh**, both local week starts correspond to **17:00Z of the preceding day**. Depending on how reporting periods are defined, you may need ISO week-year or custom week rules; `$dateTrunc` does not automatically encode every "fiscal week" rule.

### 4.7. Note on binSize Greater Than 1

With `binSize: 2` and `unit: "month"`, buckets do not simply round the current month back arbitrarily. MongoDB aligns buckets against the **operator's reference point** (for standard units, anchored to the start of year 2000, with dedicated rules for weeks). Therefore, when building two-month or multi-week blocks, verify how partitions align with the reference point rather than looking at a single month in isolation.

If a business uses fiscal cycles starting on the 5th or 4-4-5 periods, `$dateTrunc` with standard calendar units may be insufficient; design a calendar lookup table or supplementary transformation.

### 4.8. Null, Missing Fields, and Wrong Data Types

In many date/time expressions, a null/missing `date` or null/missing optional parameter yields `null` per operator rules. Non-date values can raise errors.

Do not expect the following to automatically parse Strings as Dates:

~~~javascript
{
  $dateTrunc: {
    date: "$occurredAt",
    unit: "day"
  }
}
~~~

if `occurredAt` is stored as the String **"2026-11-14"**. Standardize the schema or convert explicitly. When processing imported data, classify wrong-type records, log errors, and decide whether to skip or convert before grouping.

## 5. Using $dateTrunc to Aggregate by Local Day

Requirement: **count events and sum `amount` for each Vietnam day**. You can place `$dateTrunc` directly as the `$group` key:

~~~javascript
db.events.aggregate([
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      eventCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Logical results by local day:

| VN Date | _id Date in UTC | eventCount | totalAmount |
|---|---|---:|---:|
| 2026-11-13 | 11/12 17:00Z | 1 | 100.00 |
| 2026-11-14 | 11/13 17:00Z | 3 | 275.00 |
| 2026-11-15 | 11/14 17:00Z | 3 | 90.00 |
| 2026-11-16 | 11/15 17:00Z | 1 | 90.00 |

Total amount on Nov 14 is `200 + 0 + 75 = 275`. If you only want `ORDER` revenue, filter `type` before `$group`:

~~~javascript
db.events.aggregate([
  { $match: { type: "ORDER" } },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 },
      revenue: { $sum: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

`ORDER` results: Nov 13 has **1 order, 100.00**; Nov 14 has **2 orders, 275.00**; Nov 15 has **2 orders, 90.00**; Nov 16 has **1 order, 90.00**.

### 5.1. Formatting Date Labels with $dateToString

Because the group `_id` is a BSON Date in UTC, raw display may look like the previous day. To output **YYYY-MM-DD** labels in Vietnam time:

~~~javascript
db.events.aggregate([
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      count: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 0,
      dayStartUtc: "$_id",
      dayLabel: {
        $dateToString: {
          format: "%Y-%m-%d",
          date: "$_id",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      count: 1
    }
  },
  { $sort: { dayStartUtc: 1 } }
])
~~~

In the output, **dayStartUtc** remains a true BSON Date; **dayLabel** is a String for display. When comparing ranges or paginating chronologically, keep the Date rather than keeping only the string.

### 5.2. $dateTrunc Does Not Auto-Fill Days with Zero Events

If the collection has no events on Nov 17, `$group` will **not synthesize a row for that day**. If a chart must display days with `count = 0`, add a date-axis generation step, such as a calendar table in the application or aggregation stages supported by your MongoDB version.

Do not interpret an absent bucket as proof that the application stored a document with total `0`; those are two different states.

## 6. $dateAdd: Adding or Subtracting Time Units

**$dateAdd** takes a timestamp and adds **amount** time units to it. Syntax:

~~~javascript
{
  $dateAdd: {
    startDate: <dateExpression>,
    unit: <timeUnit>,
    amount: <integerExpression>,
    timezone: <timezone>  // optional, defaults to UTC
  }
}
~~~

Common units include **year, quarter, week, day, hour, minute, second, millisecond**. `amount` is an **integer**: positive to move forward in time, negative to move backward.

### 6.1. Adding Seven Days

~~~javascript
db.events.aggregate([
  { $match: { _id: "E02" } },
  {
    $project: {
      _id: 1,
      occurredAt: 1,
      afterSevenDays: {
        $dateAdd: {
          startDate: "$occurredAt",
          unit: "day",
          amount: 7,
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
])
~~~

E02 = **2026-11-13T17:30:00Z**, which is 00:30 on Nov 14 in Vietnam. Seven local days later is 00:30 on Nov 21, which is **2026-11-20T17:30:00Z**.

### 6.2. Adding 90 Minutes

~~~javascript
db.events.aggregate([
  { $match: { _id: "E02" } },
  {
    $project: {
      _id: 1,
      plusNinetyMinutes: {
        $dateAdd: {
          startDate: "$occurredAt",
          unit: "minute",
          amount: 90
        }
      }
    }
  }
])
~~~

Result: **2026-11-13T19:00:00Z**. For minute/second intervals, we usually think in actual elapsed duration; for days/months/years and timezones with DST, calendar rules apply.

### 6.3. Negative Amount Performs Subtraction

~~~javascript
db.events.aggregate([
  { $match: { _id: "E02" } },
  {
    $project: {
      _id: 1,
      threeDaysEarlier: {
        $dateAdd: {
          startDate: "$occurredAt",
          unit: "day",
          amount: -3,
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
])
~~~

E02 minus three local days returns **2026-11-10T17:30:00Z**.

MongoDB also provides **$dateSubtract** to write subtraction explicitly. This lesson focuses on `$dateAdd`; negative amounts are often handy when a formula accepts a signed parameter.

### 6.4. Adding One Month Is Not Equivalent to Adding 30 Days

Months can have 28, 29, 30, or 31 days. MongoDB applies calendar rules for month/quarter/year units and resolves non-existent target dates by clamping to the last valid day of the target month.

Leap year example:

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      oneMonthAfterJan31: {
        $dateAdd: {
          startDate: ISODate("2024-01-31T12:00:00Z"),
          unit: "month",
          amount: 1
        }
      },
      thirtyDaysAfterJan31: {
        $dateAdd: {
          startDate: ISODate("2024-01-31T12:00:00Z"),
          unit: "day",
          amount: 30
        }
      }
    }
  }
])
~~~

Results:

| Expression | UTC Timestamp |
|---|---|
| Add 1 month | 2024-02-29T12:00:00Z |
| Add 30 days | 2024-03-01T12:00:00Z |

Starting from **2025-01-31T12:00:00Z** and adding one month lands on **2025-02-28T12:00:00Z** because 2025 is not a leap year.

This is why a requirement like "renew a one-month subscription" must not be blindly implemented as adding `30 × 24` hours. Define business rules when the anchor day is the 29th, 30th, or 31st, especially across consecutive renewals.

### 6.5. Adding Months Sequentially Can Differ from Adding All at Once

From **2025-01-31**, adding one month gives **2025-02-28**; adding another month from Feb 28 gives **2025-03-28**. Yet adding two months directly to Jan 31 gives **2025-03-31**.

This is not a MongoDB bug—it is a consequence of calendar clamping at an intermediate month-end step. For contracts and billing cycles, clearly define:

- Is the next due date computed from the **current due date** or from **anchor date + N months**?
- Should an "end-of-month" rule be preserved?
- If the anniversary day does not exist in the target month, how is it handled?

Never let an arbitrary `$dateAdd` call dictate critical billing rules.

### 6.6. Leap Years and February 29

Example:

~~~javascript
{
  $dateAdd: {
    startDate: ISODate("2024-02-29T09:00:00Z"),
    unit: "year",
    amount: 1
  }
}
~~~

2025-02-29 does not exist, so the calendar calculation clamps to **2025-02-28T09:00:00Z**. If different rules apply for "Feb 29 birthdays" or "annual renewals," specify them explicitly in business logic.

## 7. $dateAdd and Daylight Saving Time (DST)

Timezones like **America/New_York** observe DST transitions, meaning a local day can be **23 hours** or **25 hours** long. Therefore, distinguish:

- **Adding one local calendar day**: preserves "same wall-clock time the next day" whenever possible.
- **Adding 24 real hours**: advances by exactly 24 hours on the UTC timeline.

For example, New York springs forward to DST on **2024-03-10**. Before the shift, 12:00 noon on Mar 09 in EST (UTC−05:00) is **2024-03-09T17:00:00Z**. After the shift, 12:00 noon on Mar 10 in EDT (UTC−04:00) is **2024-03-10T16:00:00Z**.

### 7.1. Adding 1 day vs. 24 hours Yields Different Results

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      calendarNextDay: {
        $dateAdd: {
          startDate: ISODate("2024-03-09T17:00:00Z"),
          unit: "day",
          amount: 1,
          timezone: "America/New_York"
        }
      },
      after24Hours: {
        $dateAdd: {
          startDate: ISODate("2024-03-09T17:00:00Z"),
          unit: "hour",
          amount: 24,
          timezone: "America/New_York"
        }
      }
    }
  }
])
~~~

Meaning:

| Addition | UTC Result | Local Time in New York |
|---|---|---|
| 1 day in NY calendar | 2024-03-10T16:00:00Z | Mar 10 at 12:00 EDT |
| 24 hours | 2024-03-10T17:00:00Z | Mar 10 at 13:00 EDT |

The UTC span between noon on those two days is only **23 hours**. For units of **day or larger**, timezone-aware calculations follow local calendar and DST rules; for smaller units, evaluate in elapsed time units. This is a crucial business distinction.

### 7.2. When Do You Need "24 Real Hours" vs. "Same Time Tomorrow"?

| Requirement | Appropriate Calculation |
|---|---|
| Token valid for exactly 24 hours | Absolute duration, e.g., 24 `hour` in UTC |
| Reminder at 09:00 local time tomorrow | Local calendar math with timezone |
| Checkout deadline at 12:00 the next day | Property's local calendar, do not assume 24 hours |
| Daily revenue report per city | `$dateTrunc` with the city's timezone |
| Alert after exactly 15 minutes | Add 15 `minute` from current timestamp |
| One-month rental period | `month` unit with agreed month-end policy |

If an application stores only a fixed `"-05:00"` offset for New York, calculations on Mar 10 will miss the shift to UTC−04:00. Always prefer IANA zone names when calendar timezone rules are needed.

### 7.3. Timezones Also Matter When Subtracting Days

If you want "the same wall-clock time yesterday," use `$dateAdd` with **unit: "day", amount: -1** and the business timezone. If you want an exact 24-hour lookback, use unit `hour` with amount `-24` or compute in UTC as required.

Never use ambiguous day additions/subtractions in systems involving bookings, invoices, appointments, or security expirations.

## 8. $dateDiff: Counting Unit Boundaries Between Two Timestamps

**$dateDiff** takes **startDate**, **endDate**, **unit**, and optionally **timezone** and **startOfWeek**:

~~~javascript
{
  $dateDiff: {
    startDate: <dateExpression>,
    endDate: <dateExpression>,
    unit: <timeUnit>,
    timezone: <timezone>,        // optional, defaults to UTC
    startOfWeek: <dayOfWeek>    // used when unit: "week"
  }
}
~~~

Time units include **year, quarter, month, week, day, hour, minute, second, millisecond**. The result is a **signed integer** oriented from `startDate` to `endDate`.

The single most important point: **$dateDiff counts the number of unit boundaries crossed**, not necessarily the number of full mathematical intervals elapsed.

### 8.1. Example: Two Minutes Apart, Yet Different Days

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      daysAcrossMidnight: {
        $dateDiff: {
          startDate: ISODate("2026-11-14T23:59:00Z"),
          endDate: ISODate("2026-11-15T00:01:00Z"),
          unit: "day",
          timezone: "UTC"
        }
      },
      minutesElapsed: {
        $dateDiff: {
          startDate: ISODate("2026-11-14T23:59:00Z"),
          endDate: ISODate("2026-11-15T00:01:00Z"),
          unit: "minute",
          timezone: "UTC"
        }
      }
    }
  }
])
~~~

Results:

| Expression | Value | Reason |
|---|---:|---|
| dateDiff unit day | 1 | Crossed the Nov 15 00:00 UTC day boundary |
| dateDiff unit minute | 2 | Crossed two minute boundaries |

Never take a result of **1 day** and claim 24 hours elapsed. The actual elapsed time between the two instants is **2 minutes**.

### 8.2. Even One Second Can Cross a Day Boundary

Two documents from the sample dataset:

~~~text
E04: 2026-11-14T16:59:59Z
E05: 2026-11-14T17:00:00Z
~~~

In UTC+07, these are:

~~~text
E04: 2026-11-14 23:59:59
E05: 2026-11-15 00:00:00
~~~

Evaluate:

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      localDayDifference: {
        $dateDiff: {
          startDate: ISODate("2026-11-14T16:59:59Z"),
          endDate: ISODate("2026-11-14T17:00:00Z"),
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      utcDayDifference: {
        $dateDiff: {
          startDate: ISODate("2026-11-14T16:59:59Z"),
          endDate: ISODate("2026-11-14T17:00:00Z"),
          unit: "day",
          timezone: "UTC"
        }
      }
    }
  }
])
~~~

Result: **localDayDifference = 1**, while **utcDayDifference = 0**. The actual elapsed time in both is **1 second**, yet day boundaries depend on timezone.

### 8.3. dateDiff by Month and Year

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      monthBoundary: {
        $dateDiff: {
          startDate: ISODate("2025-01-31T23:59:00Z"),
          endDate: ISODate("2025-02-01T00:01:00Z"),
          unit: "month"
        }
      },
      yearBoundary: {
        $dateDiff: {
          startDate: ISODate("2025-12-31T23:59:00Z"),
          endDate: ISODate("2026-01-01T00:01:00Z"),
          unit: "year"
        }
      }
    }
  }
])
~~~

Both results equal **1** because each span crosses one boundary of its respective unit. Even though each span is only two minutes long, they entered a new month or year.

For this reason, **`$dateDiff` with `unit: "year"` is not an accurate age calculation for arbitrary birthdates** if the application needs completed birthdays. It counts year boundaries, not whether the birthday has already occurred in the current year.

### 8.4. startDate After endDate: Negative Results

~~~javascript
{
  $dateDiff: {
    startDate: ISODate("2026-11-15T00:00:00Z"),
    endDate: ISODate("2026-11-12T00:00:00Z"),
    unit: "day",
    timezone: "UTC"
  }
}
~~~

Result: **-3**. The negative sign indicates `endDate` precedes `startDate` chronologically.

If business logic needs a non-negative distance, decide whether to take the absolute value or swap the timestamps. Do not silently swap order if the sign carries meaning like "days overdue" vs. "days remaining."

### 8.5. dateDiff by Week and startOfWeek

Consider Saturday **2026-11-14 12:00Z** to Sunday **2026-11-15 12:00Z**:

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      sundayWeek: {
        $dateDiff: {
          startDate: ISODate("2026-11-14T12:00:00Z"),
          endDate: ISODate("2026-11-15T12:00:00Z"),
          unit: "week",
          timezone: "UTC",
          startOfWeek: "sunday"
        }
      },
      mondayWeek: {
        $dateDiff: {
          startDate: ISODate("2026-11-14T12:00:00Z"),
          endDate: ISODate("2026-11-15T12:00:00Z"),
          unit: "week",
          timezone: "UTC",
          startOfWeek: "monday"
        }
      }
    }
  }
])
~~~

Result: **sundayWeek = 1** because it crossed the Sunday week start; **mondayWeek = 0** because it has not crossed Monday's week start yet.

If `startOfWeek` is omitted when `unit` is `"week"`, MongoDB uses Sunday. Specify it explicitly whenever a system defines weeks starting on Monday or another day.

### 8.6. dateDiff Does Not Return Fractional Results

~~~javascript
{
  $dateDiff: {
    startDate: ISODate("2026-11-14T00:00:00Z"),
    endDate: ISODate("2026-11-14T12:30:00Z"),
    unit: "day",
    timezone: "UTC"
  }
}
~~~

Result is **0**, not `0.5208` days. No UTC day boundary was crossed. When fractional duration is required, compute from **absolute milliseconds** and divide by the appropriate divisor.

## 9. Calendar dateDiff vs. Actual Duration Are Two Different Questions

To avoid bugs, determine whether the business question asks about **calendar boundaries** or **elapsed duration**.

| Question | Right Mental Model | Example |
|---|---|---|
| Do two timestamps fall on different days? | Day boundary in timezone | `$dateDiff` unit `day` |
| Exactly how many minutes elapsed? | Millisecond span between two instants | `$subtract` two Dates and divide by `60,000` |
| How many actual hours did a meeting last? | Actual milliseconds elapsed | `$subtract` and divide by `3,600,000` |
| How many month boundaries were crossed? | Month boundaries | `$dateDiff` unit `month` |
| Renew to the same time tomorrow? | Local calendar addition | `$dateAdd` unit `day` |
| Token valid for exactly 24 hours? | Elapsed duration addition | `$dateAdd` 24 `hour` or UTC calculation |

### 9.1. Subtracting Two BSON Dates to Get Milliseconds

MongoDB allows subtracting two Date values in aggregation:

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      elapsedMs: {
        $subtract: [
          ISODate("2026-11-14T23:59:00Z"),
          ISODate("2026-11-14T23:58:30Z")
        ]
      },
      elapsedSeconds: {
        $divide: [
          {
            $subtract: [
              ISODate("2026-11-14T23:59:00Z"),
              ISODate("2026-11-14T23:58:30Z")
            ]
          },
          1000
        ]
      }
    }
  }
])
~~~

Result: **elapsedMs = 30000**, **elapsedSeconds = 30**.

For actual elapsed hours:

~~~javascript
{
  $divide: [
    { $subtract: ["$endedAt", "$startedAt"] },
    3600000
  ]
}
~~~

This expression returns hours possibly with a fractional part. Both fields must be valid BSON Dates, and null/missing handling must be decided beforehand.

### 9.2. $dateDiff by hour Can Differ from Actual Elapsed Hours

Example from **12:59:59Z** to **13:00:01Z**:

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      hourBoundaries: {
        $dateDiff: {
          startDate: ISODate("2026-11-14T12:59:59Z"),
          endDate: ISODate("2026-11-14T13:00:01Z"),
          unit: "hour"
        }
      },
      actualHours: {
        $divide: [
          {
            $subtract: [
              ISODate("2026-11-14T13:00:01Z"),
              ISODate("2026-11-14T12:59:59Z")
            ]
          },
          3600000
        ]
      }
    }
  }
])
~~~

**hourBoundaries = 1**, because one hour boundary was crossed; **actualHours** is approximately **0.00000056**, because only two seconds actually elapsed.

Consequently, to measure request latency, job runtime, or SLAs in actual hours, use duration math rather than `$dateDiff` with `unit: "hour"`.

### 9.3. dateDiff and DST

Consider two 12:00 noon timestamps in New York on consecutive days across the 2024 DST spring-forward:

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      calendarDays: {
        $dateDiff: {
          startDate: ISODate("2024-03-09T17:00:00Z"),
          endDate: ISODate("2024-03-10T16:00:00Z"),
          unit: "day",
          timezone: "America/New_York"
        }
      },
      elapsedHours: {
        $divide: [
          {
            $subtract: [
              ISODate("2024-03-10T16:00:00Z"),
              ISODate("2024-03-09T17:00:00Z")
            ]
          },
          3600000
        ]
      }
    }
  }
])
~~~

Result: **calendarDays = 1** in the New York calendar, yet **elapsedHours = 23**. This clearly demonstrates why a calendar day does not always equal 24 actual hours when a timezone observes DST.

### 9.4. Calculating Age: Must Check Whether Birthday Has Passed

If you only write:

~~~javascript
{
  $dateDiff: {
    startDate: "$birthDate",
    endDate: "$asOfDate",
    unit: "year",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

the result counts **calendar New Year boundaries**, not completed birthdays. Someone born in December has not reached their birthday yet, even though `$dateDiff` increments on January 1.

To compute age from birth date, define:

1. Year difference between the two dates.
2. Whether the birthday has already arrived in the current year.
3. How February 29 is handled in non-leap years.
4. Which timezone defines "today."

Do not use **`$dateDiff` with `unit: "year"`** as a legal or business age formula without those adjustments.

## 10. Combining $dateTrunc, $dateAdd, and $dateDiff in One Pipeline

Suppose each event needs derived fields:

- **localDayStart**: start of day in Vietnam time.
- **nextLocalDayStart**: start of the next local day.
- **daysSinceEvent**: number of local day boundaries from occurrence until a fixed reporting timestamp.
- **expiresAt**: expiration timestamp seven calendar days later.

We can write:

~~~javascript
db.events.aggregate([
  {
    $set: {
      localDayStart: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  },
  {
    $set: {
      nextLocalDayStart: {
        $dateAdd: {
          startDate: "$localDayStart",
          unit: "day",
          amount: 1,
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      expiresAt: {
        $dateAdd: {
          startDate: "$occurredAt",
          unit: "day",
          amount: 7,
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      daysSinceEvent: {
        $dateDiff: {
          startDate: "$occurredAt",
          endDate: ISODate("2026-11-17T00:00:00Z"),
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      occurredAt: 1,
      localDayStart: 1,
      nextLocalDayStart: 1,
      expiresAt: 1,
      daysSinceEvent: 1
    }
  },
  { $sort: { occurredAt: 1 } }
])
~~~

For document **E02**:

| Field | UTC Value |
|---|---|
| occurredAt | 2026-11-13T17:30:00Z |
| localDayStart | 2026-11-13T17:00:00Z |
| nextLocalDayStart | 2026-11-14T17:00:00Z |
| expiresAt | 2026-11-20T17:30:00Z |

`daysSinceEvent` for E02 is computed from local day Nov 14 to Nov 17 07:00 in Vietnam (00:00Z), crossing **3 local day boundaries**: Nov 15, Nov 16, and Nov 17.

### 10.1. Why Split the Pipeline into Two $set Stages?

The first stage computes **localDayStart**. The second stage uses that value in **nextLocalDayStart**. Splitting into two stages makes it explicit that the later expression reads **a value produced by the preceding stage**.

Do not assume two new fields in the **same `$set` stage** can reference each other in declaration order. Each stage evaluates against the input document entering that stage.

### 10.2. You Do Not Always Need to Store Derived Fields in the Collection

In a read pipeline, `$set` only adds fields to documents **flowing through the pipeline**. It does not write changes back to the collection. When the goal is reporting, keeping calculations inside aggregation is usually sensible.

If the application frequently filters by **expiresAt** or **localDayStart**, consider persisting derived fields at write time and indexing them, while ensuring they stay updated if the timezone or source timestamp changes.

### 10.3. Computing with Each Document's Own Timezone

In multi-region applications, each booking may carry its own timezone field:

~~~javascript
{
  _id: "BOOKING-1",
  occurredAt: ISODate("2026-11-14T18:30:00Z"),
  businessTimezone: "America/New_York"
}
~~~

Instead of hardcoding one timezone for the whole collection, expressions can read the timezone name from a field:

~~~javascript
{
  $dateTrunc: {
    date: "$occurredAt",
    unit: "day",
    timezone: "$businessTimezone"
  }
}
~~~

If the timezone field can be null/missing or invalid, define a validation, fallback, or error-classification policy. Syntactically safe fallback example:

~~~javascript
timezone: {
  $ifNull: ["$businessTimezone", "UTC"]
}
~~~

However, falling back to UTC can be **business-wrong** if records must use the venue's timezone. Never treat a fallback as universally right for every application.

In multi-timezone reports, include the timezone or region code in the **group key** when you need to separate groups sharing the same UTC instant yet belonging to different local calendars.

## 11. Filtering by Local Date While Still Utilizing Indexes

Suppose you need **all events on Nov 14, 2026 in Vietnam time**. A natural idea is computing the day with `$dateTrunc` inside `$expr`:

~~~javascript
db.events.find({
  $expr: {
    $eq: [
      {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      ISODate("2026-11-13T17:00:00Z")
    ]
  }
});
~~~

The logic accurately describes Nov 14 in Vietnam, yet **a computation on the field happens inside an expression**, so you should not assume a standard index on `occurredAt` will directly support it as a range query.

A better pattern for fixed local-day filters is converting **start of day** and **start of next day** to UTC in the application, and querying a `[start, end)` range on the BSON Date:

~~~javascript
db.events.find({
  occurredAt: {
    $gte: ISODate("2026-11-13T17:00:00Z"),
    $lt: ISODate("2026-11-14T17:00:00Z")
  }
}).sort({ occurredAt: 1 });
~~~

Results: **E02, E03, and E04**.

### 11.1. Why Use $lt on the Upper Bound?

Event E05 has `occurredAt = 2026-11-14T17:00:00Z`, which is exactly **00:00 on Nov 15** in Vietnam. Using `$lte` on the upper bound would include E05 in the Nov 14 report, double-counting boundary events.

Common pattern:

~~~javascript
{
  occurredAt: {
    $gte: startOfLocalDayAsUtcDate,
    $lt: startOfNextLocalDayAsUtcDate
  }
}
~~~

This also avoids guessing "the last millisecond of the day" like `23:59:59.999`.

### 11.2. A Local Day Is Not Always 24 Hours Long

If the timezone is `America/New_York`, local day start and next local day start can be **23 or 25 UTC hours** apart around DST. Therefore, never construct the upper bound by blindly adding **86,400,000 milliseconds** to the lower bound when querying a "local calendar day."

Instead:

1. Determine the business date and timezone.
2. Compute **start of local day**.
3. Compute **start of next local day** in that same timezone.
4. Convert both instants to UTC BSON Dates/Instants.
5. Query `occurredAt` with **`$gte startUtc, $lt endUtc`**.

This same rule applies to monthly reports: use the start of the month and the start of the next month, never a fixed `+ 30 days`.

### 11.3. Creating Indexes for Time Filters

~~~javascript
db.events.createIndex(
  { occurredAt: 1 },
  { name: "idx_occurredAt" }
);
~~~

Range query:

~~~javascript
db.events.find({
  occurredAt: {
    $gte: ISODate("2026-11-13T17:00:00Z"),
    $lt: ISODate("2026-11-14T17:00:00Z")
  }
}).sort({ occurredAt: 1 });
~~~

is well-structured for MongoDB to scan a slice of the `occurredAt` index. If you frequently filter by `type` and then range on `occurredAt`:

~~~javascript
db.events.createIndex({
  type: 1,
  occurredAt: 1
});

db.events.find({
  type: "ORDER",
  occurredAt: {
    $gte: ISODate("2026-11-13T17:00:00Z"),
    $lt: ISODate("2026-11-14T17:00:00Z")
  }
}).sort({ occurredAt: 1 });
~~~

the compound index **`{type: 1, occurredAt: 1}`** is often ideal because `type` is an equality predicate and `occurredAt` serves both the range filter and sort order.

**Having an index does not guarantee the planner will pick it**, especially on a collection with eight documents. Benchmark on representative data and inspect `explain()`.

## 12. Typical Business Scenarios

### 12.1. Payment Due After 48 Real Hours

If a contract states "exactly 48 hours after creation," the expression:

~~~javascript
{
  $dateAdd: {
    startDate: "$createdAt",
    unit: "hour",
    amount: 48
  }
}
~~~

expresses an absolute duration. No timezone is needed if only 48 real elapsed hours matter.

### 12.2. Payment Due at End of Local Day

Suppose an order is created on Nov 14 in Vietnam time, and the deadline is the **start of local Nov 15** (i.e., end of Nov 14 under an exclusive upper-bound convention):

~~~javascript
{
  $dateAdd: {
    startDate: {
      $dateTrunc: {
        date: "$createdAt",
        unit: "day",
        timezone: "Asia/Ho_Chi_Minh"
      }
    },
    unit: "day",
    amount: 1,
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

This means **start of the next day**, which differs from adding 24 hours to `createdAt`. If the operational deadline is "23:59:59 on Nov 14," be careful with millisecond precision and prefer representing deadlines as exclusive upper bounds.

### 12.3. One-Month Rental Contract

~~~javascript
{
  $dateAdd: {
    startDate: "$rentalStart",
    unit: "month",
    amount: 1,
    timezone: "$locationTimezone"
  }
}
~~~

Define the month-end clamping policy and whether renewals anchor to the original start date or previous expiration date. For complex contracts, the expression is just a calendar calculation tool; it does not replace legal/business definitions of a rental term.

### 12.4. Counting Calendar Days from Order Creation to Payment

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      calendarDaysToPay: {
        $dateDiff: {
          startDate: "$createdAt",
          endDate: "$paidAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
])
~~~

If created at 23:59 and paid at 00:01 the next day, the day count is `1` even though only two minutes elapsed. To measure **processing duration**, compute the millisecond difference and convert to the display unit.

### 12.5. Detecting Expiration via Direct Date Comparison

If each document already stores **expiresAt** as a BSON Date, "is it expired right now?" is written directly:

~~~javascript
db.subscriptions.find({
  expiresAt: { $lt: new Date() }
});
~~~

This is an **absolute instant** check and can use an index on `expiresAt`. Do not replace it with:

~~~javascript
{
  $dateDiff: {
    startDate: "$expiresAt",
    endDate: "$$NOW",
    unit: "day"
  }
}
~~~

assuming only a day count `> 0` means expired: a record can be hours overdue without having crossed a midnight boundary yet.

When an expiration timestamp is derived from `startDate` by business rules, you can precompute `expiresAt` at write time for fast queries, provided you update the derived field if the contract or timezone changes.

### 12.6. Last 7 Calendar Days Report

"Seven days" has at least two interpretations:

- **Last 168 hours** from the current instant.
- **Seven local calendar days**, e.g., today plus the six preceding days.

For example, on report date **2026-11-17 in Vietnam**, for the **7 calendar days from Nov 11 through the end of Nov 17**, the local-timezone boundaries are:

~~~text
Start: 2026-11-11 00:00+07 = 2026-11-10 17:00Z
End:   2026-11-18 00:00+07 = 2026-11-17 17:00Z
~~~

Query:

~~~javascript
db.events.find({
  occurredAt: {
    $gte: ISODate("2026-11-10T17:00:00Z"),
    $lt: ISODate("2026-11-17T17:00:00Z")
  }
});
~~~

Do not call this window "the last 168 hours" in systems observing DST. Calendar day boundaries and real elapsed durations can differ.

### 12.7. Counting Days Between Two Booking Timestamps

In a booking system, the number of **nights stayed** may depend on check-in/check-out calendar dates at the property:

~~~javascript
{
  $dateDiff: {
    startDate: "$checkInAt",
    endDate: "$checkOutAt",
    unit: "day",
    timezone: "$propertyTimezone"
  }
}
~~~

However, if check-in/check-out are stored as exact timestamps at arbitrary hours, this expression counts day boundaries in that timezone. Confirm whether business logic needs number of nights, calendar stay days, or actual hours. Rules for late check-out, early check-in, or complimentary nights must be handled explicitly.

## 13. Handling Null, Missing Fields, and String-Input Timestamps

In real data, not every document already has `paidAt` or `completedAt`. Date/time expressions need clear policies for them.

### 13.1. Filtering Documents That Have Both Timestamps

For instance, compute processing duration only for completed jobs:

~~~javascript
db.jobs.aggregate([
  {
    $match: {
      startedAt: { $type: "date" },
      endedAt: { $type: "date" }
    }
  },
  {
    $project: {
      _id: 1,
      elapsedMinutes: {
        $divide: [
          { $subtract: ["$endedAt", "$startedAt"] },
          60000
        ]
      },
      minuteBoundaries: {
        $dateDiff: {
          startDate: "$startedAt",
          endDate: "$endedAt",
          unit: "minute"
        }
      }
    }
  }
])
~~~

The `$type` filter selects documents with BSON Dates. If the data model permits BSON Timestamps or other operator-supported date types, design matching filters and validation; never assume every type containing "date" is equivalent.

### 13.2. String Data Needs Explicit Conversion

Suppose a legacy feed contains:

~~~javascript
{
  createdAtText: "2026-11-14T08:30:00Z"
}
~~~

An expression can convert it with `$dateFromString`:

~~~javascript
{
  $dateFromString: {
    dateString: "$createdAtText",
    onError: null,
    onNull: null
  }
}
~~~

**onError** and **onNull** prevent invalid strings from aborting the entire pipeline, yet they can also mask faulty records if `null` outputs are silently ignored. During real ingestion, count or log conversion failures to repair the source data.

If a timestamp string **lacks an offset/timezone**, specify `timezone` when parsing. If the string already contains timezone information, follow the operator's rules rather than passing a conflicting `timezone`.

### 13.3. Using Schema Validation to Prevent Wrong Types

A new collection can require `occurredAt` to be a BSON Date:

~~~javascript
db.createCollection("validatedEvents", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["occurredAt"],
      properties: {
        occurredAt: {
          bsonType: "date"
        },
        type: {
          bsonType: "string"
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

A validator does not automatically convert existing data to Date; applying it to an existing collection requires auditing, migration, and a rollout plan.

## 14. MongoDB Java Sync Driver: Building Date/Time Aggregations

In Java using the **MongoDB Sync Driver**, aggregation expressions can be built with **org.bson.Document** and passed into **MongoCollection.aggregate()**. The key is keeping timestamps as BSON Dates rather than accidentally passing Strings.

Assume the project has a compatible **mongodb-driver-sync** dependency and the **MONGODB_URI** environment variable.

### 14.1. Daily Event Report in Vietnam Time

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Accumulators;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;
import java.util.List;

public class EventDailyReport {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        Bson localDayExpression = new Document(
                "$dateTrunc",
                new Document("date", "$occurredAt")
                        .append("unit", "day")
                        .append("timezone", "Asia/Ho_Chi_Minh")
        );

        List<Bson> pipeline = Arrays.asList(
                Aggregates.group(
                        localDayExpression,
                        Accumulators.sum("eventCount", 1),
                        Accumulators.sum("totalAmount", "$amount")
                ),
                Aggregates.sort(Sorts.ascending("_id"))
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> events = client
                    .getDatabase("aggregation_dates_lab")
                    .getCollection("events");

            try (MongoCursor<Document> cursor = events
                    .aggregate(pipeline)
                    .iterator()) {

                while (cursor.hasNext()) {
                    System.out.println(cursor.next().toJson());
                }
            }
        }
    }
}
~~~

In this code:

1. **Document("$dateTrunc", ...)** constructs the BSON expression matching `mongosh` syntax.
2. **Aggregates.group(...)** uses the truncated Date as the group key.
3. **Accumulators.sum** counts documents and sums the `amount` field.
4. **Aggregates.sort** sorts by bucket start timestamp.
5. **try-with-resources** closes the cursor cleanly after reading or on exception.

The business output covers **four local days Nov 13–16** with `eventCount` values **1, 3, 3, 1** as shown earlier.

### 14.2. Creating $dateAdd and $dateDiff with Document

Suppose a job has `startedAt` and `endedAt`:

~~~java
import org.bson.Document;
import org.bson.conversions.Bson;

Bson dueAtExpression = new Document(
        "$dateAdd",
        new Document("startDate", "$startedAt")
                .append("unit", "day")
                .append("amount", 7)
                .append("timezone", "Asia/Ho_Chi_Minh")
);

Bson calendarDaysExpression = new Document(
        "$dateDiff",
        new Document("startDate", "$startedAt")
                .append("endDate", "$endedAt")
                .append("unit", "day")
                .append("timezone", "Asia/Ho_Chi_Minh")
);
~~~

These two objects are only **BSON expressions**; they do not execute a query on their own. They can be placed as field values inside a `$project` or `$set` stage:

~~~java
import java.util.Arrays;
import java.util.List;

List<Bson> pipeline = Arrays.asList(
        new Document("$project",
                new Document("_id", 1)
                        .append("dueAt", dueAtExpression)
                        .append("calendarDays", calendarDaysExpression)
        )
);
~~~

Inside a method with `MongoCollection<Document> jobs`, call **jobs.aggregate(pipeline)** and consume the results. If `startedAt`/`endedAt` can be null or missing, define null-display policies and wrong-type handling before applying to business logic.

### 14.3. Creating Date Boundaries with java.time

Many local-day filter queries run much faster when both bounds are converted to UTC in Java. The **java.time** library applies timezone rules accurately:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2026, 11, 14);

Instant startInstant = day.atStartOfDay(zone).toInstant();
Instant endInstant = day.plusDays(1)
        .atStartOfDay(zone)
        .toInstant();

Date startUtc = Date.from(startInstant);
Date endUtc = Date.from(endInstant);
~~~

Result:

~~~text
startInstant = 2026-11-13T17:00:00Z
endInstant   = 2026-11-14T17:00:00Z
~~~

Notice **day.plusDays(1).atStartOfDay(zone)** rather than **startInstant.plus(24, HOURS)**. In zones with DST, those two approaches can yield different upper bounds.

### 14.4. Combining Boundaries and Filters in Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

Bson dayFilter = Filters.and(
        Filters.gte("occurredAt", startUtc),
        Filters.lt("occurredAt", endUtc)
);

// events is an initialized MongoCollection<Document>.
try (MongoCursor<Document> cursor = events.find(dayFilter)
        .sort(Sorts.ascending("occurredAt"))
        .iterator()) {

    while (cursor.hasNext()) {
        System.out.println(cursor.next().toJson());
    }
}
~~~

This snippet assumes **events**, **startUtc**, and **endUtc** are defined as in the preceding sections. MongoDB receives two BSON Date values and can use an index on `occurredAt` for a range query.

### 14.5. Do Not Convert Instant to String When Querying

If `occurredAt` is stored as a BSON Date, avoid:

~~~java
// WRONG comparison type when occurredAt in DB is a BSON Date.
Filters.gte("occurredAt", startInstant.toString());
~~~

Instead, pass **Date**, or use a properly configured codec/mapping for `Instant`:

~~~java
Filters.gte("occurredAt", Date.from(startInstant));
~~~

An ISO string that looks like a timestamp does not automatically become a BSON Date just because the field is named `occurredAt`.

## 15. Spring Data MongoDB: Using MongoTemplate and Aggregation Expressions

With **Spring Data MongoDB**, applications can use **MongoTemplate** and the aggregation APIs. Specific builder syntax for date operators can vary across Spring Data versions; when you want explicit MongoDB syntax without relying heavily on builder methods, use **AggregationOperation** to construct the BSON stage.

### 15.1. Computing localDayStart

~~~java
import java.util.List;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;

public class EventCalendarService {
    private final MongoTemplate mongoTemplate;

    public EventCalendarService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> listLocalDays() {
        AggregationOperation projectLocalDay = context ->
                new Document("$project",
                        new Document("_id", 1)
                                .append("occurredAt", 1)
                                .append(
                                        "localDayStart",
                                        new Document("$dateTrunc",
                                                new Document(
                                                        "date",
                                                        "$occurredAt")
                                                        .append("unit", "day")
                                                        .append(
                                                                "timezone",
                                                                "Asia/Ho_Chi_Minh")
                                        )
                                )
                );

        Aggregation aggregation = Aggregation.newAggregation(
                projectLocalDay,
                Aggregation.sort(Sort.by("localDayStart"))
        );

        return mongoTemplate.aggregate(
                aggregation,
                "events",
                Document.class
        ).getMappedResults();
    }
}
~~~

This example assumes `MongoTemplate` points to the **aggregation_dates_lab** database. On specific Spring Data versions, you can replace raw `Document` with built-in date expression APIs if they support the exact operator and `timezone` parameter needed.

### 15.2. Combining Query and Criteria for UTC-Converted Ranges

~~~java
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;
import java.util.List;

import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class EventRangeService {
    private final MongoTemplate mongoTemplate;

    public EventRangeService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> findByLocalDay(
            LocalDate localDate,
            ZoneId timezone) {

        Date start = Date.from(
                localDate.atStartOfDay(timezone).toInstant()
        );

        Date end = Date.from(
                localDate.plusDays(1)
                        .atStartOfDay(timezone)
                        .toInstant()
        );

        Query query = Query.query(
                Criteria.where("occurredAt")
                        .gte(start)
                        .lt(end)
        );

        return mongoTemplate.find(
                query,
                Document.class,
                "events"
        );
    }
}
~~~

This method finds events on any local date: the caller supplies `LocalDate` and `ZoneId`, Java computes both UTC bounds, and MongoDB filters by Date range. This demonstrates a clean separation of concerns: **the application knows the business timezone**, while **the database performs an index-eligible range scan**.

### 15.3. When Results Need Locale-Formatted Date Strings

An API does not have to return date strings instead of Dates. It can return BSON Dates/`Instant` values or UTC bucket timestamps to clients, which format them per user locale/timezone.

If a report needs pre-formatted labels from MongoDB, use **$dateToString** with the appropriate timezone. Either way, avoid losing business timezone context or mixing String labels with Date values in the same field.

## 16. Performance and Execution Plans

Date/time expressions are flexible, yet evaluating them across every document can be costly. A pipeline reading millions of events should prioritize **early filtering**, **index usage where possible**, and **computing only required fields**.

### 16.1. Early $match Using Timestamp Ranges

Instead of grouping the entire collection and filtering down to a few report days afterward:

~~~javascript
db.events.aggregate([
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      count: { $sum: 1 }
    }
  },
  {
    $match: {
      _id: {
        $gte: ISODate("2026-11-13T17:00:00Z"),
        $lt: ISODate("2026-11-16T17:00:00Z")
      }
    }
  }
])
~~~

move the time condition into a **`$match` on `occurredAt` before the `$group` stage**:

~~~javascript
db.events.aggregate([
  {
    $match: {
      occurredAt: {
        $gte: ISODate("2026-11-13T17:00:00Z"),
        $lt: ISODate("2026-11-16T17:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

The second query places an explicit range predicate on the source BSON Date field, enabling index usage over the time window. The example condition covers local days **Nov 14 through the end of Nov 16** in Vietnam. Ensure the pre-group range aligns precisely with the target buckets; never pick arbitrary UTC boundaries that slice off part of a local bucket.

### 16.2. Inspecting explain() for the Pipeline

~~~javascript
db.events.explain("executionStats").aggregate([
  {
    $match: {
      occurredAt: {
        $gte: ISODate("2026-11-13T17:00:00Z"),
        $lt: ISODate("2026-11-16T17:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      count: { $sum: 1 }
    }
  }
]);
~~~

Inspect **winningPlan**, **IXSCAN/COLLSCAN**, **totalKeysExamined**, **totalDocsExamined**, and downstream stages. Depending on MongoDB version and execution engine, the `explain` output layout may vary.

On eight sample documents, `COLLSCAN` is a reasonable choice. Never extrapolate production performance from a tiny collection; test with data volumes and selectivity matching real workloads.

### 16.3. When Should Day Buckets Be Materialized?

If millions of reports repeatedly compute start-of-day in one fixed timezone, consider storing a derived field, e.g.:

~~~javascript
{
  occurredAt: ISODate("2026-11-13T17:30:00Z"),
  localDayStart: ISODate("2026-11-13T17:00:00Z"),
  businessTimezone: "Asia/Ho_Chi_Minh"
}
~~~

You can then index `localDayStart` or build a compound index with `tenant`/`type`. However, ensure:

- `localDayStart` is derived from `occurredAt` and the right timezone.
- Whenever `timezone` or `occurredAt` changes, the derived field is recomputed.
- Historical documents are backfilled if introduced after data already exists.
- With multiple timezones, the timezone name is preserved or included in the group key when needed.

Do not materialize a field merely because a tiny-dataset `explain` looked slow; justify it with query frequency versus write and index overhead.

## 17. Common Mistakes with $dateTrunc, $dateAdd, and $dateDiff

| Symptom | Common Cause | How to Handle |
|---|---|---|
| Event at 00:30 on Nov 14 grouped into Nov 13 | Truncated in UTC while report needs UTC+07 | Specify `timezone: "Asia/Ho_Chi_Minh"` |
| `$dateTrunc` output shows `17:00Z` of previous day | BSON Date stores UTC instants | Format in local timezone; do not alter the Date value |
| Weekly report starts Sunday instead of Monday | `startOfWeek` omitted for unit `week` | Set `startOfWeek: "monday"` if required |
| 15-minute bucket mistaken for 15 records | Confusing `binSize` with document count | `binSize` is the number of time units per bucket |
| Date range includes start of next day | Using `$lte` on upper bound | Use `[start, nextStart)` with `$lt` |
| Adding 1 month from Jan 31 hits non-existent day | Months have different lengths | Understand month-end clamping and define contract policy |
| Adding 1 month twice differs from adding 2 months | Intermediate month-end clamping | Anchor schedule calculations to the original date |
| "Same time tomorrow" shifts by 1 hour in NY | Added 24 real hours instead of 1 calendar day with timezone | Use `$dateAdd` `day` with IANA timezone |
| New York timezone always treated as `-05:00` | Fixed offset ignores DST | Use `America/New_York` for local calendar rules |
| `$dateDiff` `day` returns 1 even seconds apart | Operator counts day boundaries | Use Date `$subtract` if elapsed duration is needed |
| `$dateDiff` `year` used as age returns 1 too high | Counts New Year boundaries, not birthdays | Check birth month/day and Feb 29 rules |
| `$dateDiff` `week` returns unexpected 0 or 1 | Mismatched week-start definition | Align `startOfWeek` and `timezone` |
| `dateAdd`/`dateTrunc` errors on date Strings | Field stored with wrong BSON type | Parse/convert explicitly or fix schema |
| Computing days for missing `paidAt` | Missing/null field | Define incomplete-record handling; filter/type-check |
| `$expr` date calculation query is slow | Evaluates expression across many documents | Convert local bounds to UTC and range-query raw field |
| UTC day start confused with business day start | Venue timezone not specified | Store `businessTimezone` and compute with it |
| Chart lacks columns for days with no data | `$group` only emits buckets with documents | Generate calendar axis and pad empty buckets if needed |
| Total days evaluates to 0 across 12 hours | `$dateDiff` `day` has not crossed midnight | Pick duration or calendar boundary per business intent |
| Sorting by date strings orders incorrectly | Mixed formats, timezones, or String types | Store Date; format only in presentation layer |
| Index exists yet `explain` still shows `COLLSCAN` on test data | Collection is tiny or filter has low selectivity | Evaluate on representative workload |

### 17.1. Distinguishing Date, LocalDate, and Timezone

In Java design:

- **Instant:** an absolute point on the UTC timeline.
- **LocalDate:** a calendar date, carrying no timezone itself.
- **LocalDateTime:** a local date and time, ambiguous as a UTC instant without a timezone/offset.
- **ZonedDateTime:** date/time bound to a `ZoneId` and timezone rules.
- **BSON Date:** represents an instant; does not store a separate IANA zone name.

Passing just a `LocalDate` `"2026-11-14"` into a query without specifying a `ZoneId` leaves the application unable to tell which UTC instants start and end Nov 14. That is a data modeling flaw, not a MongoDB flaw.

### 17.2. Questions to Clarify Before Choosing an Operator

State the requirement precisely:

1. Does "get events on Nov 14" mean **UTC**, **Vietnam time**, or the user's timezone?
2. Does "add one day" mean **calendar day** or **24 real hours**?
3. Does "difference in days" mean **midnight crossings** or **hours divided by 24**?
4. Does "one month" mean a calendar month with month-end clamping or a fixed 30-day cycle?
5. Does "start of week" mean **Sunday**, **Monday**, or another day?
6. Must the logic handle **nulls**, wrong-type timestamps, or legacy string inputs?

Answering these six questions avoids most date/time bugs caused by mismatched assumptions between database, backend, and users.

## 18. Practice Exercises

Exercises use the **aggregation_dates_lab** database and **events** collection created in section 2. Exercises referencing other collections are hypothetical schema examples; do not run write operations on production data.

### Exercise 1. Determining Vietnam Date

Given two timestamps:

~~~text
A = 2026-11-13T16:59:59Z
B = 2026-11-13T17:00:00Z
~~~

Determine the `Asia/Ho_Chi_Minh` local date of A and B. Then write a `$dateTrunc` expression to truncate them to start of day.

**Guidance:**

- A is **2026-11-13 at 23:59:59+07**, start of day **11/12 17:00Z**.
- B is **2026-11-14 at 00:00:00+07**, start of day **11/13 17:00Z**.

Expression:

~~~javascript
{
  $dateTrunc: {
    date: "$occurredAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

### Exercise 2. 15-Minute Bucket

Given timestamp:

~~~text
2026-11-14T01:37:40Z
~~~

Truncate it to the start of its 15-minute bucket in UTC.

~~~javascript
{
  $dateTrunc: {
    date: ISODate("2026-11-14T01:37:40Z"),
    unit: "minute",
    binSize: 15,
    timezone: "UTC"
  }
}
~~~

**Answer:** **2026-11-14T01:30:00Z**. If the timestamp were `01:45:00Z`, it would belong to the next bucket starting at `01:45:00Z`.

### Exercise 3. Total ORDER Revenue by Local Day

Requirement: include only documents with `type = "ORDER"`, group by Vietnam day, and compute **orderCount** and **revenue**.

~~~javascript
db.events.aggregate([
  { $match: { type: "ORDER" } },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 },
      revenue: { $sum: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

**Expected results:** Nov 13 has `100`, Nov 14 has `275`, Nov 15 has `90`, Nov 16 has `90`. Explain why Nov 14 has **two** orders rather than one or three.

### Exercise 4. Using Timezone When Determining Start of Week

Write an expression grouping events by week starting **Monday** in Vietnam time:

~~~javascript
{
  $dateTrunc: {
    date: "$occurredAt",
    unit: "week",
    timezone: "Asia/Ho_Chi_Minh",
    startOfWeek: "monday"
  }
}
~~~

If `startOfWeek` is omitted, will the result still use Monday? **No.** `$dateTrunc` defaults to Sunday for weeks.

### Exercise 5. Comparing Adding One Month vs. Adding 30 Days

Starting at **2024-01-31T12:00:00Z**, compute:

1. `$dateAdd` amount `1`, unit `month`.
2. `$dateAdd` amount `30`, unit `day`.
3. Explain why the results differ.

~~~javascript
{
  $dateAdd: {
    startDate: ISODate("2024-01-31T12:00:00Z"),
    unit: "month",
    amount: 1
  }
}

{
  $dateAdd: {
    startDate: ISODate("2024-01-31T12:00:00Z"),
    unit: "day",
    amount: 30
  }
}
~~~

**Answer:** `2024-02-29 at 12:00 UTC` and `2024-03-01 at 12:00 UTC`. One calendar month and thirty days are not equivalent.

### Exercise 6. Computing Expiration After Seven Days

Suppose event E02 expires after **seven calendar days in Vietnam**, measured from `occurredAt`.

~~~javascript
db.events.aggregate([
  { $match: { _id: "E02" } },
  {
    $project: {
      _id: 1,
      expiresAt: {
        $dateAdd: {
          startDate: "$occurredAt",
          unit: "day",
          amount: 7,
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
])
~~~

**Result:** **2026-11-20T17:30:00Z**. State the corresponding local time and distinguish it from "start of expiration day."

### Exercise 7. Calendar Days vs. Actual Duration

Two timestamps:

~~~text
Start: 2026-11-14T23:59:00Z
End:   2026-11-15T00:01:00Z
~~~

1. What does `$dateDiff` unit `day`, timezone `UTC` return?
2. How many actual minutes elapsed?
3. Can you multiply result (1) by 24 hours to report elapsed duration?

**Answer:** **1 day by UTC boundaries**, **2 actual minutes**, and **you cannot** use `1 × 24 hours` as the elapsed duration.

### Exercise 8. $dateDiff by Vietnam Day

E04 and E05 are only one second apart:

~~~javascript
db.events.aggregate([
  { $match: { _id: "E05" } },
  {
    $project: {
      _id: 1,
      localDaysSinceE04: {
        $dateDiff: {
          startDate: ISODate("2026-11-14T16:59:59Z"),
          endDate: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
])
~~~

**Answer:** **1**, because it crossed the Nov 15 midnight boundary in Vietnam time.

### Exercise 9. Distinguishing 1 day from 24 hours Across DST

Starting at **2024-03-09T17:00:00Z** in New York (12:00 EST), predict:

~~~javascript
{
  $dateAdd: {
    startDate: ISODate("2024-03-09T17:00:00Z"),
    unit: "day",
    amount: 1,
    timezone: "America/New_York"
  }
}

{
  $dateAdd: {
    startDate: ISODate("2024-03-09T17:00:00Z"),
    unit: "hour",
    amount: 24,
    timezone: "America/New_York"
  }
}
~~~

**Answer:** **2024-03-10T16:00:00Z** (12:00 EDT) and **2024-03-10T17:00:00Z** (13:00 EDT) respectively. Explain what happened when New York switched to DST.

### Exercise 10. Filtering a Local Day Using an Indexed Range

Requirement: retrieve all events on **Nov 14, 2026 in Vietnam**, sorted by `occurredAt` ascending.

~~~javascript
db.events.createIndex({ occurredAt: 1 });

db.events.find({
  occurredAt: {
    $gte: ISODate("2026-11-13T17:00:00Z"),
    $lt: ISODate("2026-11-14T17:00:00Z")
  }
}).sort({ occurredAt: 1 });
~~~

**Result:** E02, E03, E04. Explain why E05 at the upper bound is excluded and why a range query on the raw Date is generally more index-friendly than filtering with `$dateTrunc` per document.

### Exercise 11. When Is $dateDiff Unsuitable?

A billing system requires: "overdue when the current time is past `expiresAt` by even one millisecond." Should you compute `$dateDiff` unit `day` between `expiresAt` and `$$NOW` and check `> 0`?

**Answer:** No. If overdue within the same day, `$dateDiff` `day` will still be `0`. Compare the two BSON Dates directly:

~~~javascript
db.subscriptions.find({
  expiresAt: { $lt: new Date() }
});
~~~

This is also much better suited to using an index on `expiresAt`.

### Exercise 12. Imported Data Containing Strings

Suppose there are three records:

~~~javascript
{ _id: 1, occurredAt: ISODate("2026-11-14T08:00:00Z") }
{ _id: 2, occurredAt: "2026-11-14T08:00:00Z" }
{ _id: 3, occurredAt: null }
~~~

Propose how to unify the data before building reports:

1. Identify BSON types using `$type` or schema checks.
2. Convert strings in known formats using `$toDate`/`$dateFromString`, managing `onError`/`onNull` as needed.
3. Define a policy for `null`/missing.
4. Migrate legacy records and add a validator to prevent recurrence.

**Never** assume all three values can be used directly as dates in every calculation without normalization.

## 19. Operator Selection Table by Requirement

| Requirement | Operator / Approach to Consider |
|---|---|
| Get start of day, week, or month | `$dateTrunc` |
| Group data into 15-minute buckets | `$dateTrunc` unit `minute`, `binSize` 15 |
| Set week start to Monday | `$dateTrunc` with `startOfWeek: "monday"` |
| Add 7 local calendar days | `$dateAdd` unit `day`, `amount: 7`, `timezone` |
| Add exactly 48 hours | `$dateAdd` unit `hour`, `amount: 48` |
| Renew by one month | `$dateAdd` unit `month` plus month-end policy |
| Count day/month boundaries crossed | `$dateDiff` with appropriate `unit` and `timezone` |
| Measure exact elapsed time | `$subtract` between two BSON Dates |
| Display local date labels | `$dateToString` with `timezone` |
| Filter all events within one local day | Convert local bounds to UTC Dates, use `$gte`/`$lt` |
| Fast sorting/filtering by timestamp | Index on source BSON Date or consistently maintained derived field |
| Ensure field has valid date type | `$jsonSchema` with `bsonType: "date"` |

## 20. Conclusion

The three operators play complementary roles:

~~~text
BSON Date (UTC instant)
          |
          +------ $dateTrunc -----> Start of bucket in local calendar
          |
          +------ $dateAdd -------> New instant after adding/subtracting units
          |
          +------ $dateDiff ------> Number of unit boundaries crossed
          |
          +------ $subtract ------> Actual elapsed duration in milliseconds
~~~

**Key principles to remember:**

1. **A BSON Date is an absolute instant** and does not store the original timezone. When reporting by local calendar day, supply `timezone`.
2. **`$dateTrunc` returns the interval start as a Date**, not a day name or string. It can display as `17:00Z` of the prior day when `timezone` is `Asia/Ho_Chi_Minh`.
3. **`$dateAdd` with days/months/years is calendar arithmetic**, not always equivalent to adding a fixed number of hours or days. DST and month lengths can alter results.
4. **`$dateDiff` counts unit boundaries**, not fractional elapsed time. For elapsed duration, subtract the two Dates.
5. **Use `[startUtc, endUtc)` when filtering local days** to prevent boundary double-counting and leverage indexes on Date fields.
6. **Consistent BSON types matter just as much as formulas.** Control date strings, null/missing, and business timezones right at write time.
7. **Distinguish calendar calculation tools from contract definitions**: one-month rental terms, nights stayed, payment deadlines, birthdays, and SLAs require explicit business policies.

By separating **UTC instants**, **timezone-based calendars**, and **actual elapsed durations**, you can use `$dateTrunc`, `$dateAdd`, and `$dateDiff` to build accurate MongoDB reports as well as testable, scalable queries and Java applications across regions and timezones.
