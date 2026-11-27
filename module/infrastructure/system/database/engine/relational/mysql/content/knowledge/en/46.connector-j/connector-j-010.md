# connectionTimeZone, preserveInstants, and JDBC Timezone Synchronization

When a Java application connects to MySQL via Connector/J, a temporal value can pass through multiple timezone layers: the JVM, Connector/J configuration, the MySQL session timezone, and the storage column type. When these layers are poorly understood, the same `Timestamp` can display different hours between the application and an SQL client; data written to `TIMESTAMP` can be shifted by hours; and queries executed via a connection pool can receive an unexpected session time zone.

Connector/J provides `connectionTimeZone`, `preserveInstants`, and `forceConnectionTimeZoneToSession` to control how the driver interprets time and synchronizes sessions. They address different parts of the problem. Combine them with a clear understanding of `TIMESTAMP`, `DATETIME`, Java time APIs, and MySQL's `time_zone` configuration.

## 1. At Which Layers Do Timezones Appear?

A JDBC connection has at least four distinct time concepts:

| Layer | Configuration source | Role |
|---|---|---|
| JVM default time zone | `user.timezone`, OS/container, or `TimeZone.setDefault()` | Default timezone used by Java code and some legacy APIs |
| Connector/J connection time zone | `connectionTimeZone` property | Timezone the driver uses when converting temporal values between Java and MySQL |
| MySQL session time zone | `@@session.time_zone` | Rule MySQL uses when reading/writing `TIMESTAMP` and evaluating session-dependent temporal functions |
| MySQL server/system time zone | `@@global.time_zone`, `@@system_time_zone` | Default for new sessions and OS timezone detected by the server |

These layers can coincide, but they do not automatically align. For instance, the JVM may run in `Asia/Ho_Chi_Minh`, the MySQL session may use `SYSTEM` set to UTC on the server, while the application wants a UTC convention for all instants. Without explicit configuration, conversions can fall back to mismatched defaults.

Before fixing issues, identify what the data represents:

- **Instant:** an absolute point on the timeline, such as when a payment was confirmed. This value does not change when users are in different timezones.
- **Local date-time:** wall-clock time at a location, such as a store opening at 09:00 local time. It does not uniquely identify an instant without a timezone.
- **Pure date or time:** birth date, accounting date, or opening hours, not necessarily bound to a global instant.

Never choose Java or SQL types just because their names look similar. Choose based on business semantics first, then configure the driver.

## 2. How Do MySQL TIMESTAMP and DATETIME Differ?

These two types cause the most confusion:

| MySQL Type | How it stores and reads | Appropriate for |
|---|---|---|
| `TIMESTAMP` | MySQL converts from session time zone to UTC on write and from UTC to session time zone on read; column does not store original timezone name | Instants such as order creation, payment, or event ingestion times |
| `DATETIME` | Stores date/time components as supplied; MySQL does not auto-convert by session time zone | Local wall-clock times, appointments, or timestamps that must keep exact components |
| `DATE` | Stores date only | Birth dates, invoice dates, holidays |
| `TIME` | Stores time/duration values per `TIME` semantics, not timezone-aware instants | Time of day or elapsed durations per application convention |

Example:

```sql
CREATE TABLE event_log (
  event_id BIGINT PRIMARY KEY,
  occurred_at TIMESTAMP(6) NOT NULL,
  store_local_time DATETIME(6) NOT NULL,
  business_date DATE NOT NULL
);
```

`occurred_at` represents an instant. `store_local_time` holds local wall-clock components at the store; if converting it to an instant is required, the application must know the store's timezone at that time. `business_date` is simply a business date.

MySQL `TIMESTAMP` does not retain the original offset or timezone name. On read, results are expressed in the current session time zone. Thus, two sessions with different timezones may see different formatted hour strings pointing to the exact same instant. `DATETIME` does not perform that conversion automatically.

`TIMESTAMP` has a narrower range than `DATETIME` (in current MySQL releases, the traditional upper limit of `TIMESTAMP` is the year 2038). Both `TIMESTAMP` and `DATETIME` support up to six fractional second digits; choose precision matching your source accuracy and how the application handles nano/microseconds.

## 3. connectionTimeZone Controls Connector/J's Timezone

`connectionTimeZone` is the Connector/J property specifying the timezone the driver uses for temporal value conversions. This property was introduced in Connector/J 8.0.23. Common values:

- `LOCAL`: uses the JVM default timezone. This is the default value.
- `SERVER`: instructs the driver to determine the MySQL server's timezone.
- A valid timezone ID, such as `UTC`, `Asia/Ho_Chi_Minh`, or `America/New_York`.

Example JDBC URL specifying UTC:

```text
jdbc:mysql://db.example.internal:3306/orders?connectionTimeZone=UTC
```

Setting `connectionTimeZone=UTC` causes the driver to use UTC in its conversion logic. However, this property alone **does not automatically change** MySQL's `@@session.time_zone`. The session may continue using `SYSTEM`, `+07:00`, or another value per server configuration or prior session commands.

The `SERVER` value is helpful when you want the driver to follow the server's timezone rather than the JVM's. However, environments with multiple servers, replicas, or containers with differing OS configs require careful checks. Abbreviated system timezones or inconsistent DST configurations can be confusing. For applications needing a stable convention, an explicit timezone ID like `UTC` is usually easier to operate.

> `serverTimezone` is the legacy property name retained as a compatibility alias for `connectionTimeZone` in corresponding Connector/J versions. For new configurations, use `connectionTimeZone` and avoid declaring both with conflicting values.

## 4. forceConnectionTimeZoneToSession Synchronizes the MySQL Session

`forceConnectionTimeZoneToSession` controls whether Connector/J sets the MySQL session timezone to match `connectionTimeZone`. The default is `false`.

When set to `true`, the driver instructs the session to use the configured timezone. Example:

```text
jdbc:mysql://db.example.internal:3306/orders?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true
```

After connecting, verify from that same connection:

```sql
SELECT
  @@session.time_zone,
  @@global.time_zone,
  @@system_time_zone,
  NOW(),
  UTC_TIMESTAMP();
```

If the session uses UTC, `NOW()` and `UTC_TIMESTAMP()` normally show the same time value; if the session uses another timezone, `NOW()` returns session time while `UTC_TIMESTAMP()` returns UTC.

Setting the session time zone affects more than `Timestamp` conversion: it also affects `NOW()`, `CURRENT_TIMESTAMP`, how MySQL interprets literals written into `TIMESTAMP`, and several session-dependent date/time functions. Consequently, enabling `forceConnectionTimeZoneToSession` is a policy decision for the entire session's time convention. Do not enable it arbitrarily if existing application code or SQL depends on the server's local time.

If `forceConnectionTimeZoneToSession=true` and the driver sets a named timezone such as `Asia/Ho_Chi_Minh` on the session, MySQL requires its timezone tables to be loaded and up to date. If the server reports `Unknown or incorrect time zone`, check the timezone tables. Using a fixed offset like `+00:00` avoids DST table lookups, though fixed offsets cannot express seasonal DST shifts for a geographic region.

## 5. preserveInstants and Instant Semantics

`preserveInstants` was introduced in Connector/J 8.0.23 and defaults to `true` in versions that support it. It controls how the driver preserves instants when converting Java types representing absolute points in time to/from MySQL temporal types.

When `preserveInstants=true`, Connector/J uses `connectionTimeZone` when converting instant-based values. The goal is preserving the exact same instant even when the JVM and MySQL session run in different timezones. This property is especially important for `java.sql.Timestamp` and instant-representing JDBC APIs.

When `preserveInstants=false`, the driver skips instant preservation via `connectionTimeZone` and falls back to legacy conversion behavior, which can depend on the JVM default timezone. Results can diverge if JVM, connection time zone, and session time zone differ. Never switch it to `false` merely to make one screen match in development; first clarify whether the column stores an instant or a local date-time.

JDBC example:

```java
Instant instant = Instant.parse("2026-11-19T08:30:00Z");
Timestamp timestamp = Timestamp.from(instant);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO event_log (event_id, occurred_at) VALUES (?, ?)")) {
    ps.setLong(1, 1001L);
    ps.setTimestamp(2, timestamp);
    ps.executeUpdate();
}
```

`Instant` represents an absolute point in time; `Timestamp.from()` converts it to a JDBC `Timestamp`. With consistent UTC settings and `preserveInstants=true`, the application can store and read back instants independently of the JVM's display timezone.

`preserveInstants` does not make `DATETIME` timezone-aware. When storing instants in `DATETIME`, the application and driver must agree on a conversion convention—such as always writing UTC components and always interpreting them as UTC on read. If business logic needs local wall-clock time, use `LocalDateTime` and preserve the wall-clock value rather than coercing it into an instant.

## 6. Distinguishing Java Time APIs from java.sql.Timestamp

Different Java types express different temporal meanings:

| Java Type | Meaning | Typically suitable SQL type |
|---|---|---|
| `Instant` | An absolute point on the UTC timeline | `TIMESTAMP` or an explicit UTC convention in `DATETIME` |
| `java.sql.Timestamp` | JDBC instant-carrying type with nanoseconds | Typically used with `TIMESTAMP`; check Connector/J conversion rules |
| `LocalDateTime` | Wall-clock date and time without offset/time zone | `DATETIME` |
| `LocalDate` | Calendar date only | `DATE` |
| `LocalTime` | Time only, without date/timezone | `TIME` |
| `OffsetDateTime` / `ZonedDateTime` | Date/time with offset or timezone | MySQL has no column type storing full zone IDs; normalize or store zone separately |

Connector/J supports Java 8 date/time types depending on driver version and specific JDBC methods. Check your driver version's documentation before calling `setObject()` or `getObject()` with `OffsetDateTime` or `ZonedDateTime`; never assume MySQL `TIMESTAMP` preserves the original offset/zone.

Example storing local time:

```java
LocalDateTime appointment = LocalDateTime.of(2026, 11, 20, 9, 0);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO appointments (appointment_id, local_start) VALUES (?, ?)")) {
    ps.setLong(1, 501L);
    ps.setObject(2, appointment);
    ps.executeUpdate();
}
```

The `local_start` column should be `DATETIME`, because the appointment is defined as 09:00 local time. If the actual instant must be derived, store the location's zone ID alongside it, such as `Asia/Ho_Chi_Minh`, or store the precomputed instant derived from local date-time and zone per business rules.

Never convert a `LocalDateTime` to `Timestamp` implicitly using `ZoneId.systemDefault()` if the source value has no timezone. That introduces a hidden assumption that breaks when the application runs in another container or region.

## 7. Recommended JDBC URL Configurations

For systems storing instants and standardizing all sessions on UTC, the configuration can be:

```text
jdbc:mysql://db.example.internal:3306/orders?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true&preserveInstants=true
```

Meaning:

- `connectionTimeZone=UTC`: driver uses UTC when converting temporal values.
- `forceConnectionTimeZoneToSession=true`: instructs the MySQL session to use UTC.
- `preserveInstants=true`: preserves instants when converting instant-based Java types.

If you do not want to alter the session time zone because the application needs `NOW()` in the server's local time, set `forceConnectionTimeZoneToSession=false` or omit it. In that case, understand the current session time zone and test conversions between the connection time zone and session time zone.

Using `Properties` with Connector/J instead of URL parameters:

```java
Properties props = new Properties();
props.setProperty("user", "orders_app");
props.setProperty("password", "<read-from-secret-manager>");
props.setProperty("connectionTimeZone", "UTC");
props.setProperty("forceConnectionTimeZoneToSession", "true");
props.setProperty("preserveInstants", "true");

Connection connection = DriverManager.getConnection(jdbcUrl, props);
```

The password in this example is a placeholder; applications must fetch secrets from a secret store. TLS settings such as CA, hostname verification, and SSL mode must also be configured separately per connection policy. A UTC timezone does not replace TLS encryption.

## 8. Inspecting Timezone State from JDBC and MySQL

When investigating time shifts, gather state from both the JVM and MySQL on the exact same connection.

In Java:

```java
System.out.println("JVM zone: " + ZoneId.systemDefault());
System.out.println("Instant now: " + Instant.now());
System.out.println("Local date-time: " + LocalDateTime.now());
```

In MySQL:

```sql
SELECT
  @@global.time_zone AS global_time_zone,
  @@session.time_zone AS session_time_zone,
  @@system_time_zone AS system_time_zone,
  NOW(6) AS session_now,
  UTC_TIMESTAMP(6) AS utc_now,
  TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), NOW()) AS session_offset_seconds;
```

Run the query across connections borrowed from the pool, not only on a separate admin connection. If some connections report a different `@@session.time_zone`, session initialization code or an earlier task may have mutated session state.

Test round trips with a fixed instant:

```sql
CREATE TABLE timezone_probe (
  probe_id BIGINT PRIMARY KEY,
  instant_value TIMESTAMP(6) NOT NULL,
  wall_clock_value DATETIME(6) NOT NULL
);
```

Pick a known instant, write it to `instant_value` via `Timestamp`, and write `wall_clock_value` per your defined UTC or local-time convention. Read them back from the same connection and from a connection with a different session time zone. For `TIMESTAMP`, formatted strings may differ, but the resolved instant must match. For `DATETIME`, the stored time components must remain unchanged; the driver cannot guess whether it is UTC or local time unless the data contract specifies it.

## 9. Daylight Saving Time and Timezone Databases

Timezone IDs such as `America/New_York` or `Europe/Berlin` have DST rules. A local hour can occur twice when clocks fall back, or not exist at all when clocks spring forward. Thus, a `LocalDateTime` such as 01:30 on a DST transition date may correspond to two instants or none.

If business logic needs appointments in a geographic region, store both local date-time and zone ID; when computing instants, apply an explicit policy for ambiguous or nonexistent times. Never use a region's current offset to calculate a future date when DST rules might change.

The JVM uses the timezone database bundled with the JDK/OS; MySQL uses the server's timezone tables when resolving named timezones. The two datasets can be on different versions. This can cause Java and MySQL to compute different offsets for certain historical or future dates.

Recommendations:

- Use UTC for event timestamps and inter-service data exchange.
- Use IANA zone IDs for local schedules instead of storing only a fixed offset.
- Update JDK timezone data and MySQL timezone tables as part of operational maintenance.
- Test DST transition timestamps in your test suite, especially for bookings and recurring billing.
- Avoid ambiguous timezone abbreviations such as `CST`; use `Asia/Shanghai`, `America/Chicago`, or exact business zone IDs.

## 10. Connection Pools and Session Time Zone

`time_zone` is a session variable. When a connection returns to the pool, session state can persist into the next borrow if the pool does not reset it or the application fails to reinitialize it.

Risk example:

1. Request A runs `SET time_zone = '+07:00'` on a pooled connection.
2. The connection returns to the pool without resetting session state.
3. Request B borrows that exact connection assuming the session uses UTC.
4. Request B's `NOW()` evaluations or `TIMESTAMP` writes behave unexpectedly.

To prevent errors:

- Configure `connectionTimeZone` and `forceConnectionTimeZoneToSession` consistently in datasource settings.
- Never alter `time_zone` arbitrarily inside a request; if unavoidable, restore the original value before returning the connection.
- Use connection initialization SQL or a pool hook to verify/set session state when opening new connections.
- Enable the pool's connection state reset mechanism if supported and test behavior with Connector/J.
- Add periodic health checks reading `@@session.time_zone` from real pooled connections.

Running `SET GLOBAL time_zone` only changes the default for new sessions; it does not update existing open sessions. Similarly, changing a JDBC URL does not update connections already created in a running pool; recycle the pool per deployment procedures.

## 11. Calendar Overloads and Legacy JDBC APIs

JDBC provides overloads accepting a `Calendar` when reading or writing `Timestamp`/`Date`/`Time`. The Calendar specifies the timezone for that particular operation:

```java
Calendar utcCalendar = Calendar.getInstance(TimeZone.getTimeZone("UTC"));

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO event_log (event_id, occurred_at) VALUES (?, ?)")) {
    ps.setLong(1, 1002L);
    ps.setTimestamp(2, timestamp, utcCalendar);
    ps.executeUpdate();
}
```

When reading:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT occurred_at FROM event_log WHERE event_id = ?")) {
    ps.setLong(1, 1002L);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            Timestamp value = rs.getTimestamp(1, utcCalendar);
            Instant instant = value.toInstant();
        }
    }
}
```

Calendar overloads are useful when integrating legacy code or specifying a timezone for an individual call. However, mixing a UTC Calendar with a connection configured for another timezone without a unified convention easily introduces double conversions. For new applications, prefer consistent Connector/J settings and Java time APIs matching data semantics.

## 12. Common Errors and Diagnostics

| Symptom | Possible cause | Verification and resolution |
|---|---|---|
| Time shifted by exact timezone hour offset | JVM, connection time zone, and session time zone differ | Print `ZoneId.systemDefault()`, query `@@session.time_zone`; configure explicitly |
| Written correctly but read with wrong offset | `TIMESTAMP` converts by session zone on read, driver converts by connection zone | Check `preserveInstants`, `connectionTimeZone`, and session zone on the same connection |
| `DATETIME` shifts after reading through driver | Code uses instant-based types or inconsistent conversion rules | Use `LocalDateTime` for wall-clock times and enforce a UTC convention if storing instants in DATETIME |
| Only some connections in the pool drift | Session state not reset or inconsistent connection initialization | Check `@@session.time_zone` across multiple connections; reset/recycle pool |
| `Unknown or incorrect time zone` | MySQL lacks timezone tables or invalid zone ID | Load/update timezone tables or use a valid zone ID; test fixed offsets if appropriate |
| Wrong time around DST transitions | Ambiguous/nonexistent local time or Java/MySQL tzdb mismatch | Store zone ID, define DST policy, and synchronize timezone databases |
| Errors on new connections after driver upgrade | Timezone property renamed/changed or legacy driver lacked property support | Check Connector/J version; use supported properties instead of legacy configs |
| Loss of microseconds | Column precision or mapping mismatch | Choose `TIMESTAMP(6)`/`DATETIME(6)` when needed and run round-trip tests |

When troubleshooting, never add/subtract a fixed hour offset in SQL or Java to hide a shift. That may appear to work in one season and break when DST changes or when connections move to another region.

## 13. Pre-Production Test Plan

Testing must cover both configuration and data:

1. Record Connector/J version, JDK version, JVM default zone, MySQL version, and timezone tables.
2. Run with `connectionTimeZone=UTC`, `forceConnectionTimeZoneToSession=true`, `preserveInstants=true` in staging.
3. Open a fresh connection and verify `@@session.time_zone` is genuinely UTC.
4. Round-trip a fixed `Instant` through `TIMESTAMP(6)` and verify `toInstant()` equals the original value.
5. Round-trip a `LocalDateTime` through `DATETIME(6)` and verify time components remain unchanged.
6. Verify `NOW()`, `UTC_TIMESTAMP()`, `CURRENT_TIMESTAMP`, and table timestamp defaults.
7. Repeat with the JVM running in a different timezone to expose hidden dependencies on `ZoneId.systemDefault()`.
8. Test DST using timestamps before/after transitions in business-relevant regions.
9. Borrow multiple connections from the pool and confirm `@@session.time_zone` does not drift across requests.
10. Test microseconds, nulls, boundary values, and historical data stored under prior conventions.

Never change production timezone configuration before knowing whether historical data was stored as instants or local wall-clock times. If legacy data was written inconsistently, plan a dedicated classification and data migration; changing the JDBC URL alone will not fix already-misstored values.

## 14. Practical Scenario

A Java ordering application runs in a UTC+7 container, while MySQL Server runs in UTC with multiple replicas. The application records payment timestamps in `TIMESTAMP` and store delivery appointment times in `DATETIME`. Some requests reading from the connection pool see payment times shifted by seven hours.

**Step 1 — Identify semantics.** `paid_at` is an instant, so use `TIMESTAMP(6)`; `delivery_local_time` is local wall-clock time, so use `DATETIME(6)` and store the store's zone ID if deriving instants is needed.

**Step 2 — Synchronize instants.** Configure the datasource:

```text
jdbc:mysql://db.example.internal:3306/orders?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true&preserveInstants=true
```

**Step 3 — Verify sessions.** Borrow connections from the pool, run `SELECT @@session.time_zone, NOW(6), UTC_TIMESTAMP(6)`, and confirm the session uses UTC. Check multiple connections, not just a single test connection.

**Step 4 — Fix Java mapping.** Use `Instant` or `Timestamp.from(instant)` for `paid_at`. Use `LocalDateTime` for `delivery_local_time`; do not convert local time into an instant without applying the store's zone ID.

**Step 5 — Run round-trip tests.** Write a known instant to `paid_at`, read it back with `getTimestamp(...).toInstant()`, and compare. Write a `LocalDateTime` to `delivery_local_time`, read it back with `getObject(..., LocalDateTime.class)` if supported by the driver version, and compare components.

**Step 6 — Roll out to pool.** Recycle the connection pool after updating the URL, ensuring old connections are no longer reused and no request mutates session timezone on its own.

For historical data, audit the origin of each field. If `paid_at` was previously written while the session used UTC+7 yet the application treated it as UTC, you may need a scoped data correction for affected ranges and timestamps; never run bulk `DATE_SUB` updates without auditing first.

## 15. Pre-Production Checklist

- [ ] Identified which fields are instants, local date-times, pure dates, or pure times.
- [ ] Selected appropriate SQL types among `TIMESTAMP`, `DATETIME`, `DATE`, and `TIME`.
- [ ] Recorded Connector/J version, JDK timezone, and MySQL timezone configuration.
- [ ] Set `connectionTimeZone` explicitly instead of relying implicitly on JVM defaults.
- [ ] Decided whether `forceConnectionTimeZoneToSession=true` is required.
- [ ] Understood and tested `preserveInstants` with actual Java/JDBC types.
- [ ] Verified `@@session.time_zone` on connections borrowed from the pool.
- [ ] Checked timezone tables if using IANA zone IDs in MySQL.
- [ ] Tested DST, ambiguous/nonexistent local times, and timezone database differences.
- [ ] Executed round-trip tests with `TIMESTAMP(6)` and `DATETIME(6)`.
- [ ] Verified Calendar overloads or legacy APIs do not introduce unexpected extra conversions.
- [ ] Audited historical data before changing settings and prepared a separate migration plan if needed.

JDBC timezone synchronization is more than just setting the server to UTC. `connectionTimeZone` determines the timezone the driver uses for conversions, `forceConnectionTimeZoneToSession` synchronizes the MySQL session, and `preserveInstants` preserves absolute points in time across conversions. Combining all three properties with semantics-driven `TIMESTAMP`/`DATETIME` choices, pooled session checks, and DST testing keeps Java applications reading and writing consistent timestamps between the JVM and MySQL.
