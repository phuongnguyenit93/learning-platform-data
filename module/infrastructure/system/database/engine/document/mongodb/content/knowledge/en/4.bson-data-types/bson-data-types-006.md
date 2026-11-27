# Date, Timestamp, Timezones, and Time Representation in MongoDB

## 1. Why Does Time Data Need Careful Modeling?

In real-world applications, time appears across many business domains: account creation, order placement, delivery dates, appointments, login sessions, promotion deadlines, system logs, and change history. While all of these look like "dates and times" at first glance, they do not necessarily share the same semantics.

For example:

- "The order was created at **08:30 on 2026-11-14 in Vietnam**" is a **specific instant** on the timeline.
- "The application deadline is **2026-11-14**" may be a **calendar date** without a specific time of day.
- "The store opens at **09:00 every day**" is a **recurring local wall time**, which requires a timezone and calendar rules.
- "An event version in the oplog" orders internal events and is not necessarily a user-facing business timestamp.

MongoDB offers multiple ways to represent time. Within **BSON and data types**, two distinct types to separate are **BSON Date** and **BSON Timestamp**. Beyond storage types, you must handle **timezones** and **display formatting** at the application layer or inside query transformations.

Lesson objectives:

1. Understand the value and limitations of BSON Date and BSON Timestamp.
2. Create, store, read, and compare dates/times in `mongosh`.
3. Distinguish UTC, UTC offsets, and IANA timezone names.
4. Filter data over time ranges, especially by **local calendar day**.
5. Use MongoDB operators to parse, format, extract, add/subtract, and group by time.
6. Avoid confusing seconds with milliseconds, local dates with UTC dates, or storing timestamps as inconsistent strings.

## 2. Mental Model: Instants, Calendar Dates, and Timezones

### 2.1. Absolute Instant

An **instant** is an exact point on the timeline. The same instant can be written in multiple ways depending on the timezone:

```text
2026-11-14 01:30:00 UTC
           ||
2026-11-14 08:30:00 Asia/Ho_Chi_Minh (UTC+07:00)
           ||
2026-11-14T08:30:00+07:00
           ||
2026-11-14T01:30:00Z
```

All of these denote the **exact same instant**. `Z` designates UTC (`+00:00` offset), while `+07:00` indicates a display time seven hours ahead of UTC. At the example instant, `Asia/Ho_Chi_Minh` uses the UTC+07:00 offset.

**BSON Date** is designed to store instants. A Date value carries neither a timezone name nor its original string formatting; displaying it as "01:30 UTC" or "08:30 in Vietnam" is purely an interpretation at read time.

### 2.2. Calendar Date

A value like `2026-11-14` identifies only a calendar date. When the domain has no concept of time-of-day, arbitrarily attaching UTC midnight can cause confusion: when displayed in another timezone, the date may shift.

For instance, birthdates, holidays, payroll cutoff dates, or due dates should sometimes be stored as standardized `YYYY-MM-DD` strings or an explicit year–month–day structure rather than pretending they are instants. If the business rule requires a concrete deadline instant, state the timezone governing that day boundary.

### 2.3. Recurring Local Wall Time

"09:00 AM every Monday in Hanoi" is not yet an instant because it lacks a **specific date**. For recurring schedules, store structured fields such as:

```javascript
{
  schedule: {
    localTime: "09:00",
    weekdays: ["MON"],
    timeZone: "Asia/Ho_Chi_Minh"
  }
}
```

The application then computes the exact instant for each occurrence. This is especially critical in regions observing Daylight Saving Time (DST), where the UTC offset changes across dates.

## 3. BSON Date: An Instant in Milliseconds Since the Unix Epoch

### 3.1. What Does BSON Date Actually Store?

BSON Date is a **signed 64-bit integer** representing the **number of milliseconds** before or after the Unix epoch `1970-01-01T00:00:00Z`.

```text
Unix epoch:         1970-01-01T00:00:00.000Z
                     |
                     + 1000 milliseconds = 1 second
                     |
Date value: milliseconds since epoch (signed 64-bit)
```

Key facts to remember:

- BSON Date resolution is **milliseconds**, not nanoseconds.
- Values can be negative for pre-epoch instants; it is not limited to modern dates.
- MongoDB stores instants on the UTC timeline; it **does not embed timezone names** like `Asia/Ho_Chi_Minh` inside the BSON Date value itself.
- In `mongosh`, BSON Date is typically displayed as `ISODate("...Z")`. This is a friendly presentation; the persisted value is a BSON Date.
- The 64-bit BSON range is wider than some client date/time APIs. For example, JavaScript's `Date` object is bounded by the runtime's supported range; do not assume every BSON Date value produces a valid JavaScript `Date`.

### 3.2. Creating Dates in `mongosh`

```javascript
// Capture the current instant using the clock of the machine running mongosh.
const now = new Date();

// Write an instant explicitly in UTC.
const inUtc = ISODate("2026-11-14T01:30:00.000Z");

// Write the same instant using the UTC+07:00 offset.
const inVietnam = ISODate("2026-11-14T08:30:00+07:00");

print(inUtc.getTime() === inVietnam.getTime()); // true
print(inVietnam.toISOString()); // 2026-11-14T01:30:00.000Z

// This numeric value is milliseconds since the epoch.
print(inUtc.getTime());
```

`new Date()` generates the current time from the clock of the **client machine running JavaScript**. `Date.now()` returns only a **number of milliseconds**, not a BSON Date object. When writing a timestamp field, use a proper Date instead of accidentally storing an untyped number.

**Warning on timezone-less strings:** avoid writing `new Date("2026-11-14 08:30:00")` and expecting identical results across all runtimes. Use ISO 8601 strings with `Z` or an explicit offset, or parse with an explicit timezone using a suitable library or context.

### 3.3. Writing and Reading BSON Date

The following commands use an isolated test database `bson_time_lab`. Run them only against a MongoDB environment where you have write permissions.

```javascript
const lab = db.getSiblingDB("bson_time_lab");
const events = lab.getCollection("events");
const runId = "time54-" + new ObjectId().toHexString();

const inserted = events.insertOne({
  runId: runId,
  eventType: "check-in",
  occurredAt: ISODate("2026-11-14T08:30:00+07:00"),
  createdAt: new Date(),
  sourceTimeZone: "Asia/Ho_Chi_Minh"
});

printjson(events.findOne({ _id: inserted.insertedId, runId: runId }));
```

When reading the document back, `occurredAt` is a BSON Date corresponding to the instant `2026-11-14T01:30:00.000Z`. The string `sourceTimeZone` is stored **separately** because BSON Date does not remember that the original input carried `+07:00`. If the application needs to display events in their origin timezone, persisting the source timezone can be the right design choice.

MongoDB permits multiple types in the same collection; therefore, avoid writing `occurredAt` sometimes as a BSON Date and other times as a date string. Two values that look similar on screen may differ in data type and comparison behavior.

## 4. BSON Timestamp: Seconds and Counter, Typically for Internal Mechanisms

### 4.1. Structure Differs from BSON Date

**BSON Timestamp** is a distinct BSON type separate from BSON Date. It consists of two 32-bit parts:

| Part | Meaning |
| --- | --- |
| `t` | Time component, representing seconds since the Unix epoch |
| `i` | Incrementing ordinal (*increment*) used to distinguish or order events within the same second |

Concept:

```text
BSON Timestamp (64 bit)
┌──────────────────────────┬──────────────────────────┐
│  t: seconds (32 bits)    │  i: increment (32 bits)  │
└──────────────────────────┴──────────────────────────┘
```

MongoDB uses the Timestamp type in internal mechanisms, most notably for time markers in the **oplog** supporting replication. The `i` counter does not represent milliseconds, microseconds, or fractional seconds. Two Timestamps can share the same `t` while having different `i` values.

Example in `mongosh`:

```javascript
const ts1 = Timestamp({ t: 1760000000, i: 1 });
const ts2 = Timestamp({ t: 1760000000, i: 2 });
printjson(ts1);
printjson(ts2);
```

This example illustrates **how to construct a BSON Timestamp value**, not a recommendation to assign Timestamps for order creation times. For storing business dates/times and standard temporal filtering, **prefer BSON Date**.

### 4.2. Why Not Replace Date with Timestamp?

| Criterion | BSON Date | BSON Timestamp |
| --- | --- | --- |
| Common purpose | Business instants: creation, updates, payments, expiration | Ordering/time markers for internal MongoDB mechanisms |
| Resolution | Milliseconds | Time component in seconds; `i` is an ordinal counter |
| Structure | A signed 64-bit value holding milliseconds since epoch | Two 32-bit components `t` and `i` |
| Stores timezone inside the value? | No | No |
| Used for appointments, invoices, daily reports? | Typically appropriate | Should not replace Date |
| Used in the oplog? | Other metadata fields may use Date | Timestamp plays a specialized role |

**A Timestamp does not mean "more accurate than Date."** Reading `Timestamp({ t: ..., i: 7 })` and interpreting `i = 7` as 7 milliseconds will corrupt your data.

### 4.3. Extended JSON Representations Also Differ

When moving through JSON files or export/import APIs, MongoDB uses a specialized representation called **Extended JSON** (*EJSON*). Example:

```json
{
  "createdAt": {
    "$date": "2026-11-14T01:30:00.000Z"
  },
  "oplogPosition": {
    "$timestamp": {
      "t": 1760000000,
      "i": 7
    }
  }
}
```

This illustrates *relaxed* EJSON for Dates within the standard date range and the dedicated structure for Timestamp. *Canonical* Date format may use `{"$date":{"$numberLong":"..."}}` to represent the exact millisecond value. Both differ from plain JSON strings and preserve **BSON type** metadata during proper export/import.

Do not treat `{"$date":"..."}` as a regular nested document when handling EJSON; that wrapper carries type semantics during Extended JSON decoding.

## 5. UTC, UTC Offset, and IANA Timezones

### 5.1. Three Commonly Confused Concepts

**UTC** is the time reference system used to pin down instants. **UTC offset** is the difference from UTC at a specific moment, such as `+07:00`. An **IANA timezone** such as `Asia/Ho_Chi_Minh` or `America/New_York` is a region identifier holding historical and current UTC offset rules, including Daylight Saving Time transitions where applicable.

| Representation | Description | Enough to Compute Future Local Times? |
| --- | --- | --- |
| `2026-11-14T01:30:00Z` | Instant in UTC | Gives the instant, but not which region the user wants to view |
| `2026-11-14T08:30:00+07:00` | Instant with offset at representation time | Does not describe full timezone rules across years |
| `Asia/Ho_Chi_Minh` | IANA timezone region name | Must be paired with an instant/date and time to compute a concrete result |
| `2026-11-14 08:30` | Local time without offset or region | Insufficient to identify a unique instant |

In Vietnam, the current timezone is UTC+07:00 and DST is not currently observed. However, in international systems, never hardcode a single fixed offset for all regions and dates. For example, `America/New_York` may use UTC−05:00 or UTC−04:00 depending on the time of year.

### 5.2. Storage and Display Principles

For an **event that already occurred**, typically store:

```javascript
{
  occurredAt: ISODate("2026-11-14T01:30:00Z"),
  sourceTimeZone: "Asia/Ho_Chi_Minh"
}
```

Where:

- `occurredAt` is used for exact comparisons, sorting, indexing, and duration arithmetic.
- `sourceTimeZone` is stored only when the business logic needs the origin region or origin-timezone formatting.
- If audit requirements demand preserving the original raw input, store the original string/offset separately by design; never force those fields to replace the primary instant.

For **future schedules or recurring events**, typically store local wall time, calendar/recurrence rules, and the IANA timezone name, then compute each occurrence's instant. In DST regions, a local wall time may be skipped or occur twice on transition days; business policy must specify how to handle those edge cases.

### 5.3. Watch Timezones During Display

MongoDB does not automatically pick a display timezone for every user. The shell normally renders Dates in UTC, while web/mobile apps format them according to device timezone, user account timezone, or business timezone.

Example for the same BSON Date:

```text
UTC:                 2026-11-14 01:30
Asia/Ho_Chi_Minh:    2026-11-14 08:30
```

If one screen shows "01:30" and another shows "08:30," check the **formatting rules and output timezone** first rather than assuming the database holds wrong data.

## 6. Time-Range Filtering: Half-Open Intervals and Day Boundaries

### 6.1. The `[start, end)` Interval

When filtering events within a range, the cleanest expression is:

```text
start <= occurredAt < end
```

In MongoDB:

```javascript
const lab = db.getSiblingDB("bson_time_lab");
const events = lab.getCollection("events");

const start = ISODate("2026-11-14T00:00:00Z");
const end = ISODate("2026-11-15T00:00:00Z");

events.find({
  occurredAt: {
    $gte: start,
    $lt: end
  }
});
```

Using `$gte` (greater than or equal to) for the start bound and `$lt` (less than) for the end bound prevents adjacent intervals from double-counting boundary events. You do not need to construct "the last millisecond of the day" like `23:59:59.999`; that pattern breaks easily across type conversions or precision changes.

### 6.2. A Local Day in Vietnam Differs from a UTC Day

Suppose a report asks for **all events on 2026-11-14 in Vietnam time**. The local interval is:

```text
[2026-11-14T00:00:00+07:00,
 2026-11-15T00:00:00+07:00)
```

Converted to UTC:

```text
[2026-11-13T17:00:00Z,
 2026-11-14T17:00:00Z)
```

MongoDB query:

```javascript
events.find({
  occurredAt: {
    $gte: ISODate("2026-11-13T17:00:00Z"),
    $lt: ISODate("2026-11-14T17:00:00Z")
  }
});
```

Equivalently, you can write ISO strings with an explicit offset directly:

```javascript
events.find({
  occurredAt: {
    $gte: ISODate("2026-11-14T00:00:00+07:00"),
    $lt: ISODate("2026-11-15T00:00:00+07:00")
  }
});
```

Both describe the exact same interval. Filtering from `2026-11-14T00:00:00Z` to `2026-11-15T00:00:00Z` selects the **UTC day**, which spans 07:00 on Nov 14 to 07:00 on Nov 15 in Vietnam time, returning different results.

### 6.3. DST Regions: Do Not Always Add 24 Hours

In timezones with Daylight Saving Time, a local calendar day can be **23 hours or 25 hours** long. When generating daily reports for regions like `America/New_York`, compute the start and end bounds from **two consecutive local midnights** in that timezone, then convert to instants. Never assume `end = start + 24 hours`.

In applications, a date/time library supporting IANA timezones can compute exact day boundaries. On the MongoDB side, operators like `$dateFromString`, `$dateTrunc`, and `$dateAdd` accept a `timezone` parameter to operate on local calendar semantics.

### 6.4. Indexing Time-Range Queries

If a collection has many documents and frequently filters by `occurredAt`, create an index:

```javascript
events.createIndex({ occurredAt: 1 });

events.find({
  occurredAt: {
    $gte: ISODate("2026-11-14T00:00:00+07:00"),
    $lt: ISODate("2026-11-15T00:00:00+07:00")
  }
}).sort({ occurredAt: 1 });
```

For queries that also filter by `userId`, `tenantId`, or `status`, consider compound indexes tailored to actual queries. The goal is comparing directly against an indexed BSON Date field rather than converting every date value to a string before filtering.

## 7. Parsing, Formatting, and Transforming Time in Aggregation

MongoDB supports numerous date/time expression operators. The examples below illustrate common aggregation tasks.

### 7.1. `$dateToString`: Formatting Date by Timezone

```javascript
db.getSiblingDB("bson_time_lab").events.aggregate([
  {
    $project: {
      _id: 0,
      occurredAt: 1,
      timeInVietnam: {
        $dateToString: {
          format: "%Y-%m-%d %H:%M:%S",
          date: "$occurredAt",
          timezone: "Asia/Ho_Chi_Minh",
          onNull: null
        }
      }
    }
  }
]);
```

If `occurredAt` is `ISODate("2026-11-14T01:30:00Z")`, `timeInVietnam` becomes the string `"2026-11-14 08:30:00"`. The projected field is a **string** for display; the original `occurredAt` remains a BSON Date.

Specifiers such as `%Y`, `%m`, `%d`, `%H`, `%M`, and `%S` are MongoDB format tokens. When generating display strings, enforce consistent timezone handling across the application.

### 7.2. `$dateFromString`: Parsing Date/Time from Strings

Suppose an upstream source sends local time `"2026-11-14 08:30:00"` and you know it is Vietnam time:

```javascript
db.getSiblingDB("bson_time_lab").getCollection("imports").aggregate([
  {
    $project: {
      eventAt: {
        $dateFromString: {
          dateString: "$localDateTime",
          format: "%Y-%m-%d %H:%M:%S",
          timezone: "Asia/Ho_Chi_Minh",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

This example assumes the `imports` collection has a `localDateTime` field in that exact string format. The resulting `eventAt` is a Date corresponding to `2026-11-14T01:30:00Z`.

If the input string already includes a timezone/offset token recognized by the parser, do not supply a conflicting `timezone` argument. `onError` helps handle dirty rows without crashing the entire pipeline on a single parse failure; however, the application should track and handle failed rows rather than silently ignoring them.

### 7.3. `$dateTrunc`: Grouping Events by Local Day

Example counting events per **Vietnam calendar day**:

```javascript
db.getSiblingDB("bson_time_lab").events.aggregate([
  {
    $match: {
      occurredAt: { $type: "date" }
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
      total: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
```

The `_id` returned by `$dateTrunc` is still a **BSON Date**, representing the instant corresponding to the **start of the local day**. Consequently, the start of 2026-11-14 in Vietnam may print in the shell as `2026-11-13T17:00:00Z`; this is not an off-by-one-day bug, just the same boundary expressed in UTC.

If a report only needs calendar date labels, chain `$dateToString` with the same `timezone` to produce `YYYY-MM-DD` strings.

### 7.4. `$dateAdd`, `$dateSubtract`, and `$dateDiff`

MongoDB supports adding, subtracting, and computing differences across time units in aggregation. Example calculating the instant of the **next local calendar day**:

```javascript
db.getSiblingDB("bson_time_lab").events.aggregate([
  {
    $project: {
      occurredAt: 1,
      nextLocalDay: {
        $dateAdd: {
          startDate: "$occurredAt",
          unit: "day",
          amount: 1,
          timezone: "America/New_York"
        }
      }
    }
  }
]);
```

In DST regions, adding one **calendar day** in a timezone can span a millisecond duration other than 24 hours. Conversely, if the requirement is literally "exactly 24 hours after the event," express it in hours or an appropriate absolute duration. `$dateDiff` is helpful for counting unit boundaries between two Dates, but interpret `unit` and `timezone` carefully; calendar-day differences do not always equal milliseconds divided by 86,400,000.

### 7.5. Extracting Year, Month, and Day by Timezone

```javascript
db.getSiblingDB("bson_time_lab").events.aggregate([
  {
    $project: {
      yearVN: {
        $year: { date: "$occurredAt", timezone: "Asia/Ho_Chi_Minh" }
      },
      monthVN: {
        $month: { date: "$occurredAt", timezone: "Asia/Ho_Chi_Minh" }
      },
      dayVN: {
        $dayOfMonth: {
          date: "$occurredAt",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
]);
```

When `timezone` is omitted, many date/time operators default to UTC. Therefore, daily/monthly analytics for users across regions must specify the target timezone explicitly.

## 8. ISO 8601 Strings, EJSON, and Numeric Timestamps

Across the path client → API → MongoDB → reports, the same instant can appear in multiple forms.

| Form | Example | Type/Meaning | Notes |
| --- | --- | --- | --- |
| BSON Date | `ISODate("2026-11-14T01:30:00Z")` in shell | Instant, milliseconds | Use for business date/time fields |
| ISO 8601 UTC | `"2026-11-14T01:30:00.000Z"` | String | Can be parsed into Date, but storing a string does not make it BSON Date |
| ISO 8601 with offset | `"2026-11-14T08:30:00+07:00"` | String with offset info | Represents the same instant as the UTC example |
| Unix time (seconds) | Seconds since 1970-01-01 UTC | Number | Common in APIs/logs; verify units |
| Unix time (milliseconds) | Milliseconds since epoch | Number | Matches BSON Date unit, but Number differs from Date type |
| Extended JSON Date | `{"$date":"2026-11-14T01:30:00Z"}` | Typed notation in EJSON | Use an EJSON parser when preserving types |
| BSON Timestamp | `Timestamp({t: ..., i: ...})` | Seconds + counter | Reserved for specialized contexts; does not replace Date |

### 8.1. A Very Common Bug: Seconds vs. Milliseconds

Many APIs return **Unix timestamps in seconds**, whereas JavaScript `Date` expects **milliseconds** when constructed from a number:

```javascript
// 1_700_000_000 is in seconds, not milliseconds.
const epochSeconds = 1700000000;

// Correct: convert seconds -> milliseconds.
const dateFromSeconds = new Date(epochSeconds * 1000);

// Semantically wrong if the API provides seconds and you pass it directly.
const mistaken = new Date(epochSeconds);

print(dateFromSeconds.toISOString());
print(mistaken.toISOString());
```

Whenever timestamps appear shifted back to around 1970 or far into the future, check the epoch unit first.

### 8.2. ObjectId Can Indicate Approximate Creation Time

An `ObjectId` embeds a timestamp component with **second-level** resolution. In `mongosh`:

```javascript
const id = new ObjectId();
print(id.getTimestamp());
```

This value can be useful for diagnostics, but should not blindly replace `createdAt` because an ObjectId may be client-generated, allocated before insertion, imported from external sources, and only accurate to the second. When your application requires accurate business timestamps, store an explicit Date field.

### 8.3. Differences Between Client Clock and Server Clock

`new Date()` in `mongosh` reads the clock of the machine running the shell. If multiple application hosts have clock skew, client-generated timestamps can drift. For pipeline-style updates, MongoDB provides the system variable `$$NOW` to obtain the current server time within the expression context:

```javascript
db.getSiblingDB("bson_time_lab").events.updateOne(
  { _id: inserted.insertedId, runId: runId },
  [
    {
      $set: {
        processedAt: "$$NOW"
      }
    }
  ]
);
```

This snippet reuses the `inserted` and `runId` variables from Section 3.3 in the **same shell session**. `$$NOW` yields a consistent Date value within that pipeline context; it does not store a timezone name. Both client and server clocks still require proper operational time synchronization.

## 9. Error-Prone Designs

### 9.1. Storing Time as Local Strings Without Timezone Info

**Confusing data:**

```javascript
{ createdAt: "14/11/2026 08:30" }
```

This string lacks an offset/timezone and is not a BSON Date; string-based sorting also breaks depending on format. If it represents an occurred event, store a Date such as `ISODate("2026-11-14T01:30:00Z")` and store the source timezone separately if needed.

### 9.2. Using a Fixed Offset Instead of Full Timezone Rules

`+07:00` specifies an offset at one instant; `Asia/Ho_Chi_Minh` specifies a region. For future schedules in regions with DST or changing local time laws, IANA names enable systems to apply the proper rules. Keep timezone databases updated in systems with long-horizon or high-precision scheduling needs.

### 9.3. Computing End-of-Day Using "23:59:59"

An event at `23:59:59.500` will be missed by an `$lte` filter ending at `23:59:59.000`. Instead of trying to calculate the end of the day, use the `[start of day, start of next day)` interval with `$gte` and `$lt`.

### 9.4. Mixing Date, Timestamp, and String in One Field

```javascript
// Three different types; never mix them in the same business field.
{ occurredAt: ISODate("2026-11-14T01:30:00Z") }
{ occurredAt: "2026-11-14T01:30:00Z" }
{ occurredAt: Timestamp({ t: 1760000000, i: 1 }) }
```

This layout complicates filtering, sorting, and aggregation because MongoDB treats these as **different BSON types**. Enforce schema/validation on important date/time fields and migrate legacy records in a controlled manner.

### 9.5. Reminders Storing Only Instants Without Local Semantics

If a user schedules "09:00 AM every Monday," each occurrence corresponds to a different instant. A timezone transition or DST shift can cause adding `7 * 24 hours` to miss local 09:00. Store the recurrence rule and IANA timezone, then generate subsequent occurrences per calendar rules.

### 9.6. Assuming Timestamp Provides Microsecond/Nanosecond Precision

BSON Timestamp has `t` and `i`; `i` is an ordering counter, not milliseconds or sub-millisecond fractions. If business requirements demand tracking events at sub-millisecond precision, design an explicit high-resolution field; do not "upgrade" BSON Date to BSON Timestamp thinking it is a nanosecond timestamp.

## 10. Comprehensive Practice

### Exercise A: Find Events by Vietnam Calendar Day

Suppose the `events` collection holds:

```javascript
[
  { _id: "A", occurredAt: ISODate("2026-11-13T16:59:59.999Z") },
  { _id: "B", occurredAt: ISODate("2026-11-13T17:00:00.000Z") },
  { _id: "C", occurredAt: ISODate("2026-11-14T01:30:00.000Z") },
  { _id: "D", occurredAt: ISODate("2026-11-14T17:00:00.000Z") }
]
```

For **2026-11-14 in Vietnam**, documents **B** and **C** fall inside the range; **A** belongs to the end of Nov 13, and **D** sits right at the start of Nov 15. Use the query in Section 6.2 to verify if you create an isolated test collection. Do not use `$lte` on the upper bound.

### Exercise B: Predict Timezone Display Outputs

An application stores `ISODate("2026-11-14T01:30:00Z")`. Answer the following:

1. What time does a user in Vietnam see?
2. Does the BSON Date value itself contain the string `Asia/Ho_Chi_Minh`?
3. To group events by **local calendar day**, which parameter should specify `timezone`?
4. If the application receives `"2026-11-14 08:30:00"` from an upstream system, what additional information is needed to turn it into an instant?

### Exercise C: Inspect Data Types, Then Clean Up Test Records

If you ran the insert in Section 3.3, check the type of the stored field:

```javascript
events.aggregate([
  { $match: { _id: inserted.insertedId, runId: runId } },
  {
    $project: {
      occurredAt: 1,
      occurredAtType: { $type: "$occurredAt" },
      vietnamTime: {
        $dateToString: {
          date: "$occurredAt",
          format: "%Y-%m-%d %H:%M:%S",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
]);
```

The expected `occurredAtType` value is `"date"`. Once finished, **inspect the exact document from this run**, then delete it using both `_id` and `runId`:

```javascript
const exactFilter = { _id: inserted.insertedId, runId: runId };
printjson(events.findOne(exactFilter));

const removed = events.deleteOne(exactFilter);
printjson(removed);
print("remaining=" + events.countDocuments(exactFilter));
```

This snippet reuses `events`, `inserted`, and `runId` within the same shell session; if starting a new session, use the exact saved values rather than guessing `_id` or issuing broad deletes. Under normal deletion, `deletedCount` is `1` and `remaining` is `0`.

## 11. Checklist When Designing Temporal Data

| Need | Representation to Consider | What Must Be Decided Explicitly |
| --- | --- | --- |
| Instant an event occurred | BSON Date | Store a single instant; format by display timezone |
| Event with local regional significance | BSON Date + IANA timezone field | Retain origin or business timezone if required |
| Birthdates/holidays without time-of-day | Calendar date as `YYYY-MM-DD` string or year/month/day object | Do not impose a timezone when the domain only has a date |
| Appointments / recurring schedules | Date, local wall time, IANA timezone, and recurrence rule | DST policy, generated occurrences, timezone law changes |
| Filtering reports by local calendar day | BSON Date + `[start, end)` interval | Compute both boundaries in the target timezone |
| Oplog / internal ordering markers | BSON Timestamp in its MongoDB context | Never treat counter `i` as milliseconds |
| Integrating APIs using Unix epoch | Explicitly clarify seconds vs. milliseconds then convert | Control field units and data types |
| JSON export/import preserving BSON types | Extended JSON and matching parser | Distinguish plain JSON strings from typed representations |

When working with MongoDB, start by asking: **"Is this value an instant, a calendar date, or a local wall time?"** Then choose the matching BSON type, store timezone metadata where business rules require it, and define query boundaries with unambiguous instants. That mindset prevents off-by-one-day bugs, timezone drift, and misusing BSON Timestamp.
