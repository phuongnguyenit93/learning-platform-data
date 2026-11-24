# Identifying Metrics by Name, Tags, and Unit

When reading a number on a chart, you first need to know what that number represents, which group it belongs to, and which unit it uses. The value `1000` could mean one thousand completed jobs, one thousand bytes, or one thousand milliseconds. A numeric value alone is not enough to interpret.

In Micrometer, the three pieces of information needed to understand a measurement are **the quantity name, the categorizing dimensions via tags, and the unit**. However, distinguish those from the key the registry uses to identify a meter: **within the same registry, identity is based on the name and tag set; the unit is metadata, not an independent key component**.

This lesson helps you design consistent names and tags, declare and read units accurately, and recognize when two registration calls refer to the same meter. Behaviors in the examples are demonstrated with Micrometer 1.13.0, suited for studying alongside Spring Boot 3.3.x; the code targets Java 17 and runs on JDK 21.

## 1. Distinguishing meter, measurement, and identity

`Meter` is the instrument that collects measurements. For example, a `Counter` reports the accumulated increment; a `Timer` provides at least the recorded count and total time. A single meter can produce multiple values exported to the monitoring system.

`MeterRegistry` manages meters. When you register a meter, the registry must decide whether to return an existing meter or create a new one.

Example of a job counter:

```text
Logical name: batch.jobs.completed
Tags:         queue=export, outcome=success
Unit:         jobs
Type:         Counter
Value:        3
```

Reading: three completed jobs have been recorded for the export queue, with a success outcome.

These are distinct roles:

| Information | Question answered | Example | Part of the name–tag key? |
| --- | --- | --- | --- |
| Logical name | Which quantity is being measured? | `batch.jobs.completed` | Yes |
| Tags | Which group does the quantity belong to? | `queue=export`, `outcome=success` | Yes |
| Base unit (`baseUnit`) | In which unit should the value be interpreted? | `jobs`, `bytes` | No |
| Meter type | By which mechanism is it recorded? | `Counter`, `Timer` | Does not create another name–tag key; must be compatible with the registered meter |
| Description (`description`) | What is the specific meaning of the quantity? | Number of finished jobs | No |
| Current value or statistic | How much has been measured? | `3`, total time `1` second | No |

`Meter.Id` carries extensive metadata describing a meter, but do not infer that every field in that object participates in identity comparison. In Micrometer 1.13.0, identity comparison uses the name and tag set. Micrometer's documentation also describes a meter as uniquely identified by its name and dimensions. [Meter model](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).

## 2. Naming so readers know what is being measured

### 2.1. The name is a contract about the quantity

A good name describes a relatively stable quantity, not bound to an individual instance or entity:

| Need | Meaningful logical name | Information better placed in tags or another source |
| --- | --- | --- |
| Count finished jobs | `batch.jobs.completed` | Queue, outcome |
| Measure job processing time | `batch.job.duration` | Queue, bounded job type |
| Measure output data size | `batch.output.size` | Format or queue group |
| Read number of pending jobs | `batch.queue.size` | Queue |

A viewer who only selects the name `batch.jobs.completed` must still understand that it represents the metric group for finished jobs. Tags then enable drilling down into success, failure, or individual queues.

Overly generic names like `value` or `count` force readers to hunt for context. Names containing individual job IDs like `batch.job.872391.completed` turn every job into a new name and make querying and aggregation unmanageable.

### 2.2. Keep logical names decoupled from destination conventions

Micrometer recommends lowercase names with words separated by dots. System-specific registries may translate names to conventions suitable for that target system. [Micrometer 1.13 naming conventions](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html).

For example, `batch.jobs.completed` is the name used in code. Upon export, the physical name may change separators or add suffixes according to the statistic type and unit. Do not assume the name in the monitoring system must match the Java string verbatim.

Distinguish three layers:

```text
Logical name registered in Java
    -> registry naming translation and representation rules
    -> name and time series in the monitoring system
```

Do not create two logical names that differ only in characters that the destination normalizes into the same form. For instance, `normalization.test` and `normalization_test` are two distinct names in an in-memory registry, yet both become `normalization_test` when snake_case normalization is applied. Their local coexistence does not guarantee export will not collide.

### 2.3. Descriptions clarify boundaries

`description` can explain at what point a job is counted as completed, whether retries are included, or whether size is measured before or after compression. Such details help operators use the data accurately.

Changing the description does not create a new meter and is not a mechanism for retroactively updating the meaning of already-recorded data. If the business definition of a quantity changes, handle the measurement contract change explicitly.

## 3. Tags create dimensions

A tag consists of a key and a value. The following combinations are three distinct identities in the same registry:

```text
batch.jobs.completed {queue=export, outcome=success}
batch.jobs.completed {queue=export, outcome=failure}
batch.jobs.completed {queue=import, outcome=success}
```

Changing `outcome` or `queue` sends measurements to a different group. Thus, one logical name can have multiple meters corresponding to the tag combinations that appear.

### 3.1. Tag order does not create a new group

These two snippets represent the same tag set:

```java
registry.counter("batch.jobs.completed",
        "queue", "export", "outcome", "success");
registry.counter("batch.jobs.completed",
        "outcome", "success", "queue", "export");
```

These are excerpts in a context that already has a `registry` variable. Swapping tag pair order does not create an independent counter.

If two components in the application increment a meter with the same name and tags in the same registry, their numbers add into the same counter. That can be intentional to aggregate across multiple recording sites, or it can be a bug recording the same event twice.

### 3.2. Value conventions must stay consistent

`outcome=success` and `outcome=SUCCESS` are not the same logical value in the registry. If two teams use two casings, operators may accidentally omit one group when filtering.

Within the same metric family, standardize:

- The meaning of each tag key.
- The allowed value set for each key and its exact spelling.
- Which keys are always present.
- How unknown or not-applicable cases are represented, if required by business logic.

Do not pass `null` as a tag value. Also do not repeat the same key with multiple values in one registration expecting multiple independent dimensions; build a clear tag set where each key has one meaning.

### 3.3. One name does not mean one time series

If there are two queues, three outcomes, and four regions, the number of combinations can be `2 × 3 × 4 = 24` before considering additional dimensions. That is the combinatorial limit for the example, not a guarantee that every combination will appear.

A timer also has multiple statistics, so the number of time series at the destination can exceed the number of meter identities. Histogram configurations can increase the series count even further.

The number of value combinations is often called cardinality. Tags per job ID, request ID, or user can grow alongside incoming data volume. Choose dimensions with controlled value sets; fine-grained per-execution identifiers usually fit better in logs or traces.

## 4. Unit is a contract about numeric meaning

### 4.1. baseUnit does not create an independent meter

Consider two registration calls with the same name and tags but different `baseUnit` declarations:

```text
First registration:  batch.jobs.completed + queue=export + outcome=success + jobs
Second registration: batch.jobs.completed + queue=export + outcome=success + tasks
```

With `SimpleMeterRegistry` and Micrometer 1.13.0, the second call returns the already-registered counter; the unit on that meter remains `jobs`. This is an intentionally conflicting declaration for observation, not a design pattern to follow.

Consequently, two components cannot separate two quantities merely by using the same name and tags with different units. A different unit does not open an extra storage slot.

If one component records bytes while another records kilobytes into the same meter, the registry will not detect the mismatched numeric meaning or convert them for you. The result may look valid as a Java number while losing consistent measurement meaning.

### 4.2. Base unit does not auto-convert input numbers

`DistributionSummary` is suitable for recording non-time values, such as output size. You can declare the unit with `baseUnit("bytes")`. [DistributionSummary and base unit](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html).

Snippet:

```java
DistributionSummary bytes = DistributionSummary.builder("batch.output.size")
        .baseUnit("bytes")
        .register(registry);
bytes.record(2);
```

This requires importing `io.micrometer.core.instrument.DistributionSummary`. The code above records the numeric value `2`. Under the chosen contract, the application is declaring that to be 2 bytes; the library does not know whether the input number was originally in bytes or KiB.

If the input source is 2 KiB and the meter's contract is bytes, the application must normalize before recording:

```java
double sizeInKiB = 2.0;
bytes.record(sizeInKiB * 1024);
```

Distinguish KiB and kB when designing the contract: 1 KiB is 1024 bytes, while 1 kB is 1000 bytes. Pick one meaning and stay consistent; do not use an ambiguous label to mask the difference.

Similarly, a ratio `0.25` and a percentage `25` cannot be mixed into the same meter without converting to the same scale. Unit metadata does not replace data normalization.

### 4.3. Timer has an explicit time-unit API

For durations, use `Timer` and pass a `Duration` or a value–`TimeUnit` pair:

```java
duration.record(Duration.ofMillis(250));
duration.record(750, TimeUnit.MILLISECONDS);
```

The total is 1000 ms, which is also 1 second. When reading via `totalTime(TimeUnit.MILLISECONDS)` or `totalTime(TimeUnit.SECONDS)`, you specify the result unit explicitly.

Timer handles time conversions through its API and according to the registry's base unit. This differs from merely attaching a `baseUnit` string to a summary. Do not assume all destinations use the same time unit, and do not hardcode an export-unit suffix into the logical name. [Timer and unit conversion](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html).

### 4.4. Meter type must match the quantity

Unit alone does not describe the measurement mechanism. A counter with unit `jobs` counts job volume; a gauge can also have unit `jobs` yet read the number of pending jobs at observation time.

Sharing a unit does not mean two quantities can be arbitrarily added together. "Total completed jobs" and "pending jobs" are still two different questions, so they need appropriate names and instrument types.

Conversely, registering a `Counter` and then registering a `Timer` with the same name and tags is a type conflict. In the example's version, the registry throws `IllegalArgumentException`; the `type` field does not turn them into two independent meters under the same name–tag key.

## 5. Complete example: observing identity and units

The example uses two in-memory registries to verify:

- Same name, same tags, and reversed tag order still use the same counter.
- Changing only the unit does not create a new counter.
- Changing a tag value creates a separate group.
- Timer converts time units on read.
- Summary retains input values according to the declared unit contract.
- Another registry has separate state, even with identical name and tags.

### 5.1. Preparing the experiment project

Create two files in a separate directory:

```text
meter-identity-demo/
├── pom.xml
└── MeterIdentityDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>meter-identity-demo</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

The example pins Micrometer 1.13.0 so results are reproducible. In a Spring Boot project, use the Boot-managed dependency version instead of copying the experiment's version number into your application.

### 5.2. Java code

`MeterIdentityDemo.java`:

```java
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class MeterIdentityDemo {
    public static void main(String[] args) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        SimpleMeterRegistry otherRegistry = new SimpleMeterRegistry();
        try {
            Counter success = Counter.builder("batch.jobs.completed")
                    .tag("queue", "export")
                    .tag("outcome", "success")
                    .baseUnit("jobs")
                    .description("Completed batch jobs")
                    .register(registry);

            Counter reordered = Counter.builder("batch.jobs.completed")
                    .tag("outcome", "success")
                    .tag("queue", "export")
                    .baseUnit("jobs")
                    .register(registry);

            Counter differentUnit = Counter.builder("batch.jobs.completed")
                    .tag("queue", "export")
                    .tag("outcome", "success")
                    .baseUnit("tasks")
                    .register(registry);

            Counter failure = Counter.builder("batch.jobs.completed")
                    .tag("queue", "export")
                    .tag("outcome", "failure")
                    .baseUnit("jobs")
                    .register(registry);

            success.increment();
            reordered.increment(2);
            failure.increment();

            System.out.println("sameAfterTagReorder=" + (success == reordered));
            System.out.println("sameAfterUnitChange=" + (success == differentUnit));
            System.out.println("keptBaseUnit=" + success.getId().getBaseUnit());
            System.out.printf(Locale.ROOT,
                    "successCount=%.0f failureCount=%.0f%n",
                    success.count(), failure.count());

            Timer duration = Timer.builder("batch.job.duration")
                    .tag("queue", "export")
                    .register(registry);
            duration.record(Duration.ofMillis(250));
            duration.record(750, TimeUnit.MILLISECONDS);
            System.out.printf(Locale.ROOT,
                    "timerCount=%d totalMs=%.0f totalSeconds=%.3f%n",
                    duration.count(),
                    duration.totalTime(TimeUnit.MILLISECONDS),
                    duration.totalTime(TimeUnit.SECONDS));

            DistributionSummary outputSize =
                    DistributionSummary.builder("batch.output.size")
                            .tag("queue", "export")
                            .baseUnit("bytes")
                            .register(registry);
            outputSize.record(2048);
            outputSize.record(512);
            System.out.printf(Locale.ROOT,
                    "sizeUnit=%s sizeCount=%d totalSize=%.0f%n",
                    outputSize.getId().getBaseUnit(),
                    outputSize.count(), outputSize.totalAmount());

            boolean typeConflict = false;
            try {
                registry.timer("batch.jobs.completed",
                        "queue", "export", "outcome", "success");
            } catch (IllegalArgumentException expected) {
                typeConflict = true;
            }
            System.out.println("typeConflict=" + typeConflict);

            Counter other = Counter.builder("batch.jobs.completed")
                    .tag("queue", "export")
                    .tag("outcome", "success")
                    .baseUnit("jobs")
                    .register(otherRegistry);
            System.out.printf(Locale.ROOT,
                    "sameAcrossRegistries=%s otherCount=%.0f%n",
                    success == other, other.count());
        } finally {
            registry.close();
            otherRegistry.close();
        }
    }
}
```

Two points to note before running:

1. `differentUnit` is an intentional test declaring a different unit to observe re-registration behavior. In real application code, all sites recording the same quantity must agree on the unit from the start.
2. The `IllegalArgumentException` catch block wraps only the intentionally provoked type-conflict test. Do not use this pattern to swallow all meter registration errors in an application.

The program calls `close()` in `finally` for the registries it creates. This is a standalone program and does not use Spring bean lifecycles.

### 5.3. Compile and run

Maven and JDK 17 or newer are required. The following commands also run on JDK 21, where `--release 17` sets the Java language and API level of the compiled code.

Download runtime libraries into `lib`:

```shell
mvn -q dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=lib
```

PowerShell/Windows:

```powershell
New-Item -ItemType Directory -Path out -Force | Out-Null
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out MeterIdentityDemo.java
java -cp "out;lib/*" MeterIdentityDemo
```

Linux/macOS:

```shell
mkdir -p out
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out MeterIdentityDemo.java
java -cp "out:lib/*" MeterIdentityDemo
```

The classpath uses `;` on Windows and `:` on Linux/macOS. Maven needs to download dependencies on the first run if the machine does not yet have the libraries cached.

Stdout:

```text
sameAfterTagReorder=true
sameAfterUnitChange=true
keptBaseUnit=jobs
successCount=3 failureCount=1
timerCount=2 totalMs=1000 totalSeconds=1.000
sizeUnit=bytes sizeCount=2 totalSize=2560
typeConflict=true
sameAcrossRegistries=false otherCount=0
```

`Locale.ROOT` keeps number formatting consistent, including the dot in `1.000`.

### 5.4. Reading the evidence from the output

| Output | What is verified |
| --- | --- |
| `sameAfterTagReorder=true` | Tag pair order does not create a different identity |
| `sameAfterUnitChange=true` | Changing unit metadata did not create a new counter |
| `keptBaseUnit=jobs` | The unit of the previously registered counter is retained in the experiment |
| `successCount=3 failureCount=1` | Two calls via the same counter add together; tag `failure` has separate data |
| `timerCount=2 totalMs=1000 totalSeconds=1.000` | The same total time can be read in explicit units |
| `sizeUnit=bytes sizeCount=2 totalSize=2560` | Two sizes 2048 and 512 are recorded under the bytes contract |
| `typeConflict=true` | You cannot use the same name–tags to create an additional timer alongside a counter |
| `sameAcrossRegistries=false otherCount=0` | The second registry has its own object and state |

Do not interpret `sameAcrossRegistries=false` as "names and tags no longer matter." Identity rules apply within the scope of the registry under consideration. Two independent registries do not automatically share counters just because they register the same name.

## 6. Querying the right metric group

### 6.1. Looking up in Java

To get the counter for the success group, specify the dimensions to filter on:

```java
Counter success = registry.get("batch.jobs.completed")
        .tags("queue", "export", "outcome", "success")
        .counter();
```

This is a snippet for a registry that already holds data. `get(...)` is a lookup requiring a match; use it when a missing meter is something you want to detect during verification.

A call such as `registry.get("batch.jobs.completed").counter()` does not automatically sum all counters with that name. When you need to aggregate in Java, select matching meters and perform a meaningful calculation.

Example for the exact counters in the experiment:

```java
double total = registry.find("batch.jobs.completed")
        .tag("queue", "export")
        .counters()
        .stream()
        .mapToDouble(Counter::count)
        .sum();
```

The result in the example's primary registry is `4.0`, consisting of three successful jobs and one failed job. This addition makes sense because both groups share the definition "finished jobs" and the same unit `jobs`.

Do not add a count in bytes to a count in KiB merely because two meters have similar names. Also do not add all statistics of a timer into one number: count and total time are quantities with different units.

### 6.2. Inspecting with Actuator in a web application

This section applies to a running Spring Boot web application that has registered the same meter contract into the Spring-managed registry. The CLI program in Section 5 exits after printing output and does not open an HTTP port.

To use the inspection endpoint in a learning environment, configure appropriate exposure, for example:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

This configuration lives in `application.yml` of a web application with Actuator; it does not create business meters by itself. Read access to the endpoint still needs to match the application's access configuration.

Select the logical name from code and filter with `tag=KEY:VALUE` parameters:

```shell
curl "http://localhost:8080/actuator/metrics/batch.jobs.completed"
curl "http://localhost:8080/actuator/metrics/batch.jobs.completed?tag=queue:export&tag=outcome:success"
```

The `metrics` endpoint uses the logical name before names are normalized for a monitoring system. It aggregates statistics of meters matching the name and filtered tags. With the experiment's exact two counter groups and data, querying by name has `COUNT=4`; querying with `outcome=success` has `COUNT=3`. That is the behavior of the endpoint, not a rule that every Java lookup API auto-sums. [Metrics endpoint in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

In a real application, new writes can increase numbers between two queries. When verifying exact numbers, control writes and select the right registry, instance, and time window.

## 7. Global rules that can change the effective identity

### 7.1. Common tags

An application can add tags at the registry level to distinguish the application or runtime region. The example below is for a self-managed registry and must execute before registering meters:

```java
registry.config().commonTags(
        "application", "batch-service",
        "region", "vn-south");
```

When inspecting the final identity, account for common tags alongside tags declared at the recording site. Someone looking only at two `.tag(...)` lines in a service might not see all the dimensions the meter actually carries.

In Spring Boot, common tags can be configured via `management.metrics.tags` or an appropriate registry customizer callback. Set them before meters are registered; do not expect adding a tag later to retroactively redesign every existing meter consistently.

### 7.2. Filters can cause two identities to collide

`MeterFilter` can modify names, add or strip tags before a meter is managed under the effective configuration. Therefore, consider those rules when explaining a conflict or merged metrics. [MeterFilter](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

Example of a filter ignoring the `outcome` tag:

```java
registry.config().meterFilter(MeterFilter.ignoreTags("outcome"));
```

This snippet requires importing `io.micrometer.core.instrument.config.MeterFilter` and configuring it before registering meters. Then these two groups can land in the same counter:

```text
batch.jobs.completed {queue=export, outcome=success}
batch.jobs.completed {queue=export, outcome=failure}
                         |
                         v
batch.jobs.completed {queue=export}
```

The result in a fresh in-memory registry is that increments from both groups accumulate into the same counter. That may serve an intentional goal of dropping an analysis dimension, yet it also removes the ability to distinguish success and failure on that metric path.

If dropping a tag to reduce cardinality, evaluate whether the merge is meaningful. The groups must remain compatible in quantity and unit; reducing series count by destroying meaning is not a good measurement outcome.

## 8. Maintaining the name–tag–unit contract as the code evolves

A measurement contract should clearly specify:

| Element | Contract example |
| --- | --- |
| Name | `batch.output.size` |
| Meaning | Output data size after compression for a completed job |
| Type | `DistributionSummary` |
| Input unit | Bytes |
| Tag keys | `queue`, `format` |
| Allowed values | Standardized queues and formats |
| Recording point | After the actual output size is known |

This prevents changes that the compiler may not catch:

- One version switches to recording pre-compression size while keeping the same name and description.
- One library receives values in KiB and passes them straight into a meter declared in bytes.
- One team uses `outcome=ok`, while another uses `outcome=success` for the same meaning.
- One instrumentation site omits the `format` tag, while other sites include it for the same metric family.

Keeping tag keys and their semantics consistent for the same meter family makes exporting and querying reliable. Some monitoring systems also enforce their own label-schema constraints; an in-memory registry accepting a registration does not prove every exporter accepts the same structure.

If the input unit must change, prefer normalizing to the existing contract when the quantity's meaning has not changed. If the change is truly incompatible, design a clear new name or contract and update metric consumers. Changing `baseUnit` in a single builder call does not convert previously recorded data or migrate history in the monitoring system.

## 9. Mistakes easy to spot from registration behavior

| Symptom | Possibility to check | Remediation |
| --- | --- | --- |
| Two counter variables share increments | Same name and tags in the same registry | Confirm whether intentional aggregation or double recording |
| Changed `baseUnit` but see no new meter | Unit does not participate in the name–tag key | Standardize the unit or design an explicit contract change |
| Values are off by a factor of 1000 or 1024 | Input unit and contract do not match | Convert at the data intake point before recording |
| Two groups `SUCCESS` and `success` appear | Inconsistent tag conventions | Normalize values according to the contract |
| Registry reports a type conflict | Using the same identity for counter and timer | Pick meaningful names or quantities; do not rely on type to split keys |
| Output in monitoring system collides or is rejected | Different names normalize identically or label schema is incompatible | Check exported name, effective tags, and destination requirements |
| Querying by name alone returns a larger number than expected | Result combines multiple tag groups, especially at an aggregating endpoint | Filter the dimensions you want to inspect and verify the addition makes sense |
| After configuring a filter, outcomes can no longer be distinguished | A categorizing tag was stripped | Check the filter's intent and which information must be preserved |

To diagnose, check in order: active registry, logical name, site tags, common tags, filters, type and unit, and then export renaming. This prevents editing the wrong name or unit when the real cause lies in a modified dimension.

## 10. Practice

Apply each change on a fresh run of the example and predict the output before running:

1. Change `.tag(...)` order in the call creating `reordered`. `sameAfterTagReorder` stays `true`, and the success count stays 3.
2. Change only `baseUnit("tasks")` to `baseUnit("bytes")` in the `differentUnit` test. With the same name and tags, the result is still the same counter and the previously registered unit remains `jobs`. Explain why this does not allow mixing byte measurements into a job counter.
3. Change `reordered`'s tag to `queue=import`. It becomes a separate group: the original `success` counter receives only one increment, while the import group receives an increment of 2.
4. Replace the two duration recordings with `record(1, TimeUnit.SECONDS)` and `record(500, TimeUnit.MILLISECONDS)`. The new total is 1500 ms or 1.5 seconds; the count is 2.
5. Query all `batch.jobs.completed` counters in the primary registry and sum `count()`. With the original program, the total is 4; do not add `otherRegistry`'s counter if the goal is only to observe the primary registry.
6. In a new registry, configure a filter ignoring the `outcome` tag before creating the success and failure groups. Observe the counters merging, then identify what analytical information was lost.

When verifying an instrumentation point yourself, record its name, effective tag set, instrument type, input unit, and owning registry. A numeric value matching expectations is meaningful only when those details also match the contract.
