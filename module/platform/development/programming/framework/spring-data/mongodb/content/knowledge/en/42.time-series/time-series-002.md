# Creating Time Series Collections with `@TimeSeries` or `CollectionOptions`

## Objectives

After this lesson, you will be able to:

- Explain why you must **create a Time Series collection before writing data** instead of only declaring a Java entity.
- Use `@TimeSeries` with `MongoTemplate.createCollection(Entity.class)`.
- Use `CollectionOptions.timeSeries(...)` when you need to declare a collection by name and configure it programmatically.
- Choose `timeField`, `metaField`, `granularity`, and retention duration (TTL), verify the configuration applied by MongoDB, and handle common pitfalls.

This lesson belongs to the **Time series** section of **SPRING_DATA_MONGODB**: using Spring Data MongoDB to connect, map documents, and operate on MongoDB through `MongoTemplate` or repositories. The focus is on **creating the collection properly as a Time Series collection** so subsequent writes, queries, aggregations, indexes, and performance monitoring stand on a sound foundation.

## 1. How Is a Time Series Collection Different from a Regular Collection?

A cold-storage monitoring system receives data like the following every 10 seconds:

```json
{
  "observedAt": "2026-11-20T02:10:00Z",
  "sensor": { "deviceId": "sensor-17", "site": "warehouse-a" },
  "temperatureC": 3.8
}
```

Each measurement carries a timestamp and source identification. MongoDB optimizes Time Series collections for this kind of data by organizing measurements into **buckets**. When reading by time range and by measurement source, the storage engine can process data more efficiently than storing discrete events in a regular collection.

MongoDB 5.0 introduced Time Series collections; both MongoDB and `featureCompatibilityVersion` must support this feature (5.0+). The key point: **the collection type is determined at collection creation time**. Simply putting `@TimeSeries` on a Java class **does not automatically convert** an existing regular collection into a Time Series collection. If you write data before creating the collection properly, implicit collection creation can leave you with a regular collection.

Main parameters:

| Parameter | Required? | Meaning and selection |
| --- | --- | --- |
| `timeField` | Yes | Field holding the timestamp, e.g., `observedAt`. In MongoDB this must be a **BSON Date**; in Java you can use `Instant`. |
| `metaField` | No | Field identifying the measurement series, e.g., `sensor` with `deviceId` and `site`. Should stay relatively stable over time. |
| `granularity` | No | `SECONDS`, `MINUTES`, `HOURS` in Spring Data; choose close to the measurement frequency. Omit to let the server use the default. |
| `expireAfter` / `expireAfterSeconds` | No | Policy for automatic expiration of old measurements over time; configured in Spring Data and translated to MongoDB's TTL option. |

**Metadata design:** If consecutive measurements come from the same device and site, put the identifying attributes in `sensor`, and keep fluctuating values like `temperatureC` as measurement fields. Do not put timestamps or values that change with every reading into metadata without a specific reason, as doing so reduces bucket grouping efficiency.

## 2. Approach 1 — Declaring `@TimeSeries` on an Entity

`@TimeSeries` belongs to package `org.springframework.data.mongodb.core.mapping`. It specifies the target collection and Time Series parameters bound to the Java type. `timeField` is a required attribute of the annotation.

Example using Java 17+ (the `SensorMeta` record) and Spring Data MongoDB:

```java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.TimeSeries;
import org.springframework.data.mongodb.core.timeseries.Granularity;

@TimeSeries(
    collection = "sensor_readings",
    timeField = "observedAt",
    metaField = "sensor",
    granularity = Granularity.SECONDS,
    expireAfter = "30d"
)
public class SensorReading {

    @Id
    private String id;
    private Instant observedAt;
    private SensorMeta sensor;
    private double temperatureC;

    protected SensorReading() {
        // For document mapping.
    }

    public SensorReading(Instant observedAt, SensorMeta sensor, double temperatureC) {
        this.observedAt = observedAt;
        this.sensor = sensor;
        this.temperatureC = temperatureC;
    }

    public String getId() { return id; }
    public Instant getObservedAt() { return observedAt; }
    public SensorMeta getSensor() { return sensor; }
    public double getTemperatureC() { return temperatureC; }

    public record SensorMeta(String deviceId, String site) {}
}
```

In this example:

- `collection = "sensor_readings"`: name of the collection used for `SensorReading`.
- `timeField = "observedAt"`: Spring Data maps the `Instant` property to a BSON Date field so MongoDB can process it chronologically.
- `metaField = "sensor"`: the entire metadata object is used to identify a measurement series; it should not point to `_id`, `timeField`, or an array/collection property.
- `granularity = Granularity.SECONDS`: appropriate when multiple samples arrive per minute; this is the **bucket granularity**, not a requirement to round timestamps to whole seconds.
- `expireAfter = "30d"`: requests removal of data older than 30 days. Spring Data MongoDB 4.4+ supports this attribute; ISO-8601 strings, SpEL expressions, or property placeholders are also supported.

### Creating the Collection from the Annotation

Once you have `MongoTemplate`, call it **explicitly**:

```java
import org.springframework.data.mongodb.core.MongoTemplate;

MongoTemplate template = /* Spring-managed bean */;

// Create only if the collection does not exist yet.
if (!template.collectionExists(SensorReading.class)) {
    template.createCollection(SensorReading.class);
}
```

`createCollection(SensorReading.class)` reads the entity metadata, including `@TimeSeries`, and sends a command to MongoDB to create the Time Series collection. This step creates the **storage structure**; measurements should only be written afterward.

In a Spring Boot application, you can use an `ApplicationRunner` to create the collection at startup:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.MongoTemplate;

@Configuration
public class MongoCollectionConfig {

    @Bean
    ApplicationRunner ensureTimeSeriesCollection(MongoTemplate template) {
        return args -> {
            if (!template.collectionExists(SensorReading.class)) {
                template.createCollection(SensorReading.class);
            }
        };
    }
}
```

When multiple application instances start concurrently, checking `collectionExists` and then creating the collection is **not atomic**: two instances may both observe that the collection does not exist. In practice, create the collection in a coordinated deployment/migration step, or handle the case where another instance just created it and **re-verify the actual configuration**. Also inspect the configuration if the collection *already* exists: `collectionExists == true` does not guarantee that the collection is Time Series with the desired options.

### Inserting a Measurement After Collection Creation

```java
SensorReading reading = new SensorReading(
    Instant.parse("2026-11-20T02:10:00Z"),
    new SensorReading.SensorMeta("sensor-17", "warehouse-a"),
    3.8
);

template.insert(reading);
```

When using a repository for `SensorReading`, the repository still handles saving and reading documents via Spring Data; **ensuring the Time Series collection exists before writing is still required**.

## 3. Approach 2 — Creating the Collection with `CollectionOptions`

Sometimes you do not have a dedicated entity yet, are building a data administration tool, or want to control collection creation at the database initialization layer. In that case, use Spring Data MongoDB's `CollectionOptions`:

```java
import java.time.Duration;

import org.springframework.data.mongodb.core.CollectionOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.timeseries.Granularity;

CollectionOptions options = CollectionOptions.timeSeries(
    "observedAt",
    ts -> ts.metaField("sensor")
            .granularity(Granularity.SECONDS)
            .expireAfter(Duration.ofDays(30))
);

if (!template.collectionExists("sensor_readings")) {
    template.createCollection("sensor_readings", options);
}
```

Note the two arguments to `createCollection`: **collection name** and **Time Series options**. Calling `createCollection("sensor_readings")` without options creates a regular collection.

The example above uses the `CollectionOptions.timeSeries(String, Function)` overload, available since **Spring Data MongoDB 4.4**. For minimal configuration, use the API available since Spring Data MongoDB 3.3:

```java
template.createCollection(
    "sensor_readings",
    CollectionOptions.timeSeries("observedAt")
);
```

The minimal call declares only `timeField`; it does not declare `metaField`, `granularity`, or TTL. If you need additional options on Spring Data versions older than the lambda overload, you can use `CollectionOptions.TimeSeriesOptions`:

```java
CollectionOptions.TimeSeriesOptions ts =
    CollectionOptions.TimeSeriesOptions.timeSeries("observedAt")
        .metaField("sensor")
        .granularity(Granularity.SECONDS);

CollectionOptions options = CollectionOptions.empty().timeSeries(ts);
template.createCollection("sensor_readings", options);
```

`expireAfter(Duration)` and `@TimeSeries(expireAfter = ...)` were added in Spring Data MongoDB 4.4. When using another version, check the Javadoc matching your project dependency. For the same collection name, **choose one creation path** and use it consistently; do not run two creation commands back-to-back.

### Relation to Native MongoDB Commands

Conceptually equivalent, the full `CollectionOptions` example produces a configuration like:

```javascript
db.createCollection("sensor_readings", {
  timeseries: {
    timeField: "observedAt",
    metaField: "sensor",
    granularity: "seconds"
  },
  expireAfterSeconds: 2592000
});
```

`2592000` seconds corresponds to 30 days. This is an **illustrative command for reference**; if the application already created the collection via Spring Data, do not run this Mongo shell command again on the same name.

## 4. Choosing `@TimeSeries` or `CollectionOptions`?

| Criterion | `@TimeSeries` | `CollectionOptions` |
| --- | --- | --- |
| Where declared | Directly on the Java entity | In initialization/migration code |
| Corresponding creation API | `template.createCollection(SensorReading.class)` | `template.createCollection(name, options)` |
| Collection name | Via `collection` or entity naming convention | Passed directly as a string |
| Time/meta/granularity config | Annotation attributes | Java API configuration |
| TTL | `expireAfter = "30d"` (Spring Data 4.4+) | `expireAfter(Duration.ofDays(30))` (Spring Data 4.4+) |
| Best fit | Fixed entity where keeping configuration near the model is preferred | Creating collections from deployment config or administrative operations |

**Selection rule:** If each collection maps to a clear domain entity, prefer `@TimeSeries` for readability and alignment with mapping. If the application manages multiple collections by configured name, or prefers not to couple storage options to domain classes, prefer `CollectionOptions`.

One thing to keep consistent: if an entity maps fields with `@Field("...")`, verify the field name **actually stored in MongoDB**. Spring Data may translate Java property names to mapped field names when processing Time Series options. A mismatch between written field names and collection configuration will cause errors or an inconsistent schema.

## 5. Verifying the Collection After Creation

Do not rely solely on the absence of exceptions. Open `mongosh` on the right database and inspect the metadata:

```javascript
const info = db.getCollectionInfos({ name: "sensor_readings" })[0];
printjson({
  name: info?.name,
  type: info?.type,
  timeseries: info?.options?.timeseries,
  expireAfterSeconds: info?.options?.expireAfterSeconds
});
```

The expected output looks like:

```json
{
  "name": "sensor_readings",
  "type": "timeseries",
  "timeseries": {
    "timeField": "observedAt",
    "metaField": "sensor",
    "granularity": "seconds"
  },
  "expireAfterSeconds": 2592000
}
```

This output shape is illustrative; some MongoDB versions may also display additional bucket properties. If `type` returns `collection`, you have a regular collection. If `timeseries` is incorrect, resolve the configuration mismatch before continuing to use it.

Then verify the data and query by device/time range:

```javascript
db.sensor_readings.find(
  {
    "sensor.deviceId": "sensor-17",
    observedAt: {
      $gte: ISODate("2026-11-20T00:00:00Z"),
      $lt:  ISODate("2026-11-21T00:00:00Z")
    }
  },
  { _id: 0, observedAt: 1, sensor: 1, temperatureC: 1 }
).sort({ observedAt: 1 });
```

With Spring Data, the equivalent query is:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("sensor.deviceId").is("sensor-17")
        .and("observedAt")
        .gte(Instant.parse("2026-11-20T00:00:00Z"))
        .lt(Instant.parse("2026-11-21T00:00:00Z"))
).with(Sort.by(Sort.Direction.ASC, "observedAt"));

List<SensorReading> readings =
    template.find(query, SensorReading.class);
```

Querying by measurement source and time range is the typical access pattern. As data volume grows, inspect `explain()`, bucket statistics, and the indexes created or permitted by MongoDB on Time Series collections before adding new indexes.

## 6. With `ReactiveMongoTemplate`: Creation Must Be Executed

The reactive API provides corresponding methods, but they return a `Mono`. Creating a `Mono` variable and ignoring it **will not send the collection creation command**. Chain the creation step into the execution flow so writes run after creation completes:

```java
import reactor.core.publisher.Mono;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;

Mono<Void> ensureCreated = reactiveTemplate
    .collectionExists("sensor_readings")
    .flatMap(exists -> exists
        ? Mono.<Void>empty()
        : reactiveTemplate.createCollection("sensor_readings", options).then()
    );

Mono<SensorReading> saved =
    ensureCreated.then(reactiveTemplate.insert(reading));

// Return 'saved' to the upstream flow;
// WebFlux or an actual subscriber will trigger the operation chain.
```

The snippet assumes `reactiveTemplate`, `options`, and `reading` have been initialized as in earlier examples. Multi-instance concurrent startup and checking existing collection configuration still apply in reactive setups.

## 7. Important Limitations and Error Scenarios

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| `@TimeSeries` present but `type: "collection"` | A regular collection was created earlier | Create a **new collection** with Time Series options and migrate data; collection type cannot be changed in place. |
| Collection creation reports already exists | Name is already in use, or two instances raced to create it | Read metadata via `getCollectionInfos`; verify type and options, handle startup race conditions. |
| Insert fails with `timeField` error | Missing field, string instead of BSON Date, or field name mapping mismatch | Ensure `Instant`/Java Date maps to a BSON Date named `observedAt`. |
| Data not deleted immediately after 30 days | TTL runs by bucket and background task | Check `expireAfterSeconds`, actual timestamps, and bucket cleanup intervals; TTL is not an exact-to-the-second schedule. |
| Queries slow down as reading count grows | Unhelpful `metaField`, mismatched `granularity`, or missing time filter | Redesign queries around `metaField` + time; check indexes/execution plans. |
| Need to change `timeField` or `metaField` after creation | These options are fixed to the collection at creation time | Create a new Time Series collection and migrate data. |

Several MongoDB Time Series limitations must be factored in before choosing this model:

- Arbitrary updates like regular collections are not available: MongoDB only allows updating metadata under specific conditions; measurement fields are unsuitable for models requiring frequent edits.
- MongoDB does not support **writing to a Time Series collection inside a transaction**; reads inside transactions may be supported subject to server constraints.
- Change streams and unique indexes are not supported on Time Series collections. There is no default `_id` index as in regular collections.
- A Time Series collection cannot be `capped`; other index types and validations also have restrictions depending on MongoDB version.
- TTL removes **buckets** only after all measurements in the bucket have expired, so a document may remain visible past its theoretical expiration timestamp.

Limitations as well as index and update capabilities depend on MongoDB version. When designing for production, consult the documentation for the exact server version you run.

## 8. Self-Check Lab Exercise

Create a Spring Boot application with `spring-boot-starter-data-mongodb` and a MongoDB instance supporting Time Series; complete in order:

1. Write the `SensorReading` entity as in section 2 and create the collection using `MongoTemplate.createCollection(SensorReading.class)` before inserting.
2. Use `getCollectionInfos` to verify `type: "timeseries"`, `timeField: "observedAt"`, `metaField: "sensor"`, and a 30-day TTL.
3. Insert at least three measurements for `sensor-17` at different timestamps and one measurement for `sensor-18`.
4. Query measurements for `sensor-17` over a time range; explain why `sensor` is metadata while `temperatureC` is measurement data.
5. In another test database, create an equivalent collection using `CollectionOptions`, inspect the result, and compare metadata with the annotation approach.
6. Experiment with changing `granularity` as a design exercise: if instead of every 10 seconds, devices only send one sample per hour, which configuration is more suitable, and which metrics would you use to evaluate the impact?

**Completion criteria:** You can explain which command actually creates the collection, verify the collection type from MongoDB, identify all 4 configuration parameters, and explain why an existing regular collection cannot be turned into Time Series just by editing an annotation.

## Official References

- [Spring Data MongoDB — Index and Collection Management / Time Series](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-collection-management.html)
- [Javadoc `@TimeSeries`](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/mapping/TimeSeries.html)
- [Javadoc `CollectionOptions`](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/CollectionOptions.html)
- [Javadoc `CollectionOptions.TimeSeriesOptions`](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/CollectionOptions.TimeSeriesOptions.html)
- [MongoDB — Create and Query a Time Series Collection](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-procedures/)
- [MongoDB — Time Series Collection Limitations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/)
- [MongoDB — Automatic Removal (TTL)](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/)
