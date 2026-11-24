# Monitoring Disk Capacity and Free Disk Space

An application can still receive requests normally while about to run out of space to write logs, create temporary files, or export reports. Monitoring disk space helps show how much more capacity the storage location has left, rather than waiting for a write operation to fail.

In Spring Boot Actuator, the `disk.total` and `disk.free` measurements report capacity related to the filesystem containing the monitored path. The decisive points are **which path is being measured and which API defines "free."** This is neither a sum of every physical drive on the machine nor a measurement of a single directory's size.

This lesson uses the behavior of Spring Boot 3.3.0 and Micrometer 1.13.0 to explain configuration, querying, and proper interpretation of the figures. The Java example targets Java 17 language level, runs on JDK 21, and includes both a sample-data mode and a real-filesystem mode.

## 1. The Path Is the Starting Point of the Measurement

Suppose an application writes reports into `/data/reports`. This directory sits on a filesystem with 100 GiB total capacity and 20 GiB available to the JVM.

Those figures describe the filesystem containing the path. They do not say that:

- The reports directory currently holds exactly 80 GiB of files.
- Every subdirectory has its own separate 100 GiB of space.
- The entire host has only one 100 GiB drive.
- The application is guaranteed to be able to write another 20 GiB under all conditions.

The application's path may reside on the root filesystem, a mounted volume, a network drive, or another storage area depending on environment configuration. Therefore, start from where the application actually writes data.

Spring Boot auto-configures system metrics, including the `disk.` group. Micrometer provides the `DiskSpaceMetrics` binder to register capacity measurements for a path. [System metrics in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html), [Micrometer Disk Space Metrics](https://docs.micrometer.io/micrometer/reference/reference/system.html).

## 2. Two Meters to Read

| Meter | Underlying Read in Micrometer 1.13.0 | Unit | Meaning |
| --- | --- | --- | --- |
| `disk.total` | `File.getTotalSpace()` | Byte | Total capacity of the partition/filesystem identified by the path as seen by the JVM and OS |
| `disk.free` | `File.getUsableSpace()` | Byte | Capacity usable by the JVM according to the API result |

Both meters are `Gauge`s: they read state at the moment of observation. Available space can increase when data is freed, decrease on new writes, and change due to activity from both the application and other processes.

Do not treat these numbers as cumulative counters. Disk space going from 20 GiB to 18 GiB does not mean a "counter reset" occurred; it is a change in storage state.

### 2.1. disk.free Uses Usable Space

The name includes `free`, yet in the implementation under examination, the data source is `getUsableSpace()`, not `getFreeSpace()`.

Java distinguishes unallocated space from the space reported as usable to the JVM. Where possible, `getUsableSpace()` also accounts for constraints such as write permissions and OS restrictions. The result remains point-in-time information and does not guarantee every subsequent write will succeed. [JDK 21 File API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/File.html).

Hence, two tools talking about "free disk" can report different numbers if they use different concepts or scopes. Before assuming a metric is wrong, check filesystem, process permissions, display units, and each tool's definition of "available."

### 2.2. Do Not Infer Directory Size

`disk.total` does not sum the sizes of individual files beneath the path. A tiny directory and a huge directory on the same filesystem can yield the exact same total and usable capacity.

To find out which directory is consuming space, a different inspection is needed. Do not use this pair of metrics to claim how much space logs, reports, or temporary files alone have used.

## 3. Enabling Integration and Choosing Paths to Monitor

In a Spring Boot project that already uses Boot dependency management, add the Actuator starter to the build configuration. Gradle snippet example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

This is a declaration for an existing Spring Boot project, not a complete standalone build file. When metrics auto-configuration and an appropriate registry are active, system binders are registered.

### 3.1. Default Value of the Path

In Spring Boot 3.3.0, `management.metrics.system.diskspace.paths` defaults to a list containing `.`. That is a relative path based on the process working directory, not automatically where all business data lives.

Changing how the JAR is launched, the service working directory, or container configuration can make `.` point elsewhere. Do not infer the default path from where source files sit in the repository.

### 3.2. Configuring Paths Explicitly

Example for a web application in an environment where `/data/reports` exists:

```yaml
management:
  metrics:
    system:
      diskspace:
        paths:
          - /data/reports
  endpoints:
    web:
      exposure:
        include: health,metrics
```

`management.metrics.system.diskspace.paths` is the list of paths for which measurements should be reported. The setting does not create directories, mount volumes, or allocate additional disk space. [Spring Boot 3.3 Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

On Windows, an absolute path for that environment can be used, such as `"D:/data/reports"`. The names in examples illustrate syntax only; replace them with paths that actually exist on the machine running the application.

If multiple locations are needed:

```yaml
management:
  metrics:
    system:
      diskspace:
        paths:
          - /data/reports
          - /var/log/report-service
```

This is another configuration option for the same property. Two paths do not automatically mean two independent filesystems. Check their storage relationship before adding figures together.

Keep the path list stable according to the storage locations that need management. Do not create a new binder for every uploaded file or every request just to measure the same filesystem.

## 4. Reading Names, Units, and the path Tag

In a web application with Actuator accessible, check the names:

```http
GET /actuator/metrics/disk.total
GET /actuator/metrics/disk.free
```

The response reports measurements and `availableTags`. In the binder under examination, the `path` tag holds the absolute path string of the `File` object used for registration.

With multiple paths, querying by name alone may aggregate the gauges. To inspect one specific location, use the exact `path` value reported by the application.

For example, if the existing tag equals `/data/reports`:

```shell
curl --get "http://localhost:8080/actuator/metrics/disk.free" --data-urlencode "tag=path:/data/reports"
curl --get "http://localhost:8080/actuator/metrics/disk.total" --data-urlencode "tag=path:/data/reports"
```

Use the same tag set for both numerator and denominator when computing ratios. Do not divide `disk.free` of one location by `disk.total` of another.

Equivalent paths at the filesystem level can have different string representations. The default `.` or paths traversing links can also produce labels different from what you write by hand. Read `availableTags` instead of guessing labels or normalizing strings manually before filtering.

On Windows, URL-encoding as shown preserves the drive-letter colon and path characters. If your shell aliases `curl` to something else, invoke `curl.exe` with the corresponding arguments.

## 5. Computing GiB and Usable Percentage

Given two valid samples from the same filesystem:

```text
free GiB = disk.free / 1,073,741,824
free % = 100 × disk.free / disk.total
```

1 GiB equals `1024 × 1024 × 1024` bytes. 1 GB in decimal equals one billion bytes. The two representations do not yield the same numeric value; state units explicitly when comparing.

Example with 100 GiB total and 20 GiB usable:

| Quantity | Result | Interpretation |
| --- | --- | --- |
| `disk.total` | 107,374,182,400 bytes | Total of the monitored filesystem |
| `disk.free` | 21,474,836,480 bytes | Usable according to the API for the JVM |
| Remaining usable | 20 GiB | Same quantity in a readable unit |
| Usable percentage | 20% | 20/100 |
| Total minus usable | 80 GiB | Portion not reflected as usable to the JVM |

### 5.1. total - usable Is Not Always the Size of Used Files

If total is 100 GiB, unallocated space is 30 GiB, yet space usable by the JVM is only 20 GiB, then `total - usable` is 80 GiB. That number does not mean there are exactly 80 GiB of application file contents.

The difference can involve already allocated data and space unavailable due to system limits. Thus, when using `100 - free %`, interpret it accurately according to the usable definition rather than calling it the exact percentage occupied by the application's own files.

### 5.2. Handling Invalid Samples

Only compute a percentage when total is greater than 0, values are finite, and numbers are within a sensible range. `total=0`, `NaN`, or a missing meter should not be turned into "0% disk free" or "100% disk free."

Java can return 0 when partition information cannot be determined. When `free=0`, inspect the path, permissions, and filesystem state to distinguish an actually full disk from unreadable information.

The two reads for total and usable are not an atomic read transaction over the entire storage system. If mounts change or abnormal states occur between reads, validate samples before interpreting.

## 6. Java Example: Fixed Sample Data and Reading a Real Filesystem

The program uses Micrometer's `DiskSpaceMetrics` directly. It has two modes:

- `--sample`: supplies a mock `File` object so output is fixed and you can verify calculations and which method the binder reads.
- A real path or no argument: reads filesystem info for the path; defaults to the current working directory.

Sample mode creates no files, allocates no 100 GiB volume, and does not describe the running machine. Real mode also only reads capacity information without writing test data to fill the disk.

### 6.1. Setup

Create a separate test directory:

```text
disk-space-metrics-demo/
├── pom.xml
└── DiskSpaceMetricsDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>disk-space-metrics-demo</artifactId>
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

The standalone example pins Micrometer 1.13.0. In a Spring Boot project, continue using Boot's shared dependency version management.

### 6.2. Source Code

`DiskSpaceMetricsDemo.java`:

```java
import java.io.File;
import java.util.Locale;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.binder.system.DiskSpaceMetrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class DiskSpaceMetricsDemo {
    static final long GIB = 1024L * 1024 * 1024;

    static final class SampleFile extends File {
        SampleFile() {
            super("sample-volume");
        }

        @Override
        public long getTotalSpace() {
            return 100 * GIB;
        }

        @Override
        public long getUsableSpace() {
            return 20 * GIB;
        }

        @Override
        public long getFreeSpace() {
            return 30 * GIB;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 1) {
            throw new IllegalArgumentException("Use --sample or one existing path");
        }
        boolean sample = args.length == 1 && args[0].equals("--sample");
        File path = sample ? new SampleFile()
                : new File(args.length == 0 ? "." : args[0]).getCanonicalFile();
        if (!sample && !path.exists()) {
            throw new IllegalArgumentException("Path must exist: " + path);
        }

        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            new DiskSpaceMetrics(path).bindTo(registry);
            String pathTag = path.getAbsolutePath();
            Gauge totalGauge = registry.get("disk.total")
                    .tag("path", pathTag).gauge();
            Gauge freeGauge = registry.get("disk.free")
                    .tag("path", pathTag).gauge();

            double total = totalGauge.value();
            double usable = freeGauge.value();
            double percent = usablePercent(total, usable);

            System.out.println("mode=" + (sample ? "sample" : "real"));
            if (!sample) {
                System.out.println("path=" + pathTag);
            }
            System.out.printf(Locale.ROOT, "disk.total=%.0f bytes%n", total);
            System.out.printf(Locale.ROOT, "disk.free=%.0f bytes%n", usable);
            System.out.printf(Locale.ROOT,
                    "freeGiB=%.3f freePercent=%.3f%n",
                    usable / GIB, percent);
            System.out.printf(Locale.ROOT,
                    "totalMinusUsableGiB=%.3f%n", (total - usable) / GIB);
            System.out.printf(Locale.ROOT,
                    "type=%s unit=%s pathTagMatches=%s%n",
                    freeGauge.getId().getType(),
                    freeGauge.getId().getBaseUnit(),
                    pathTag.equals(freeGauge.getId().getTag("path")));
        } finally {
            registry.close();
        }
    }

    static double usablePercent(double total, double usable) {
        if (!Double.isFinite(total) || !Double.isFinite(usable)
                || total <= 0 || usable < 0 || usable > total) {
            throw new IllegalArgumentException("Invalid disk-space sample");
        }
        return 100.0 * usable / total;
    }
}
```

Details to watch:

1. `DiskSpaceMetrics` registers two gauges. Code looks them up by both name and `path` tag to avoid mixing groups.
2. `SampleFile` defines total as 100 GiB, usable as 20 GiB, and free via `getFreeSpace()` as 30 GiB. The `disk.free` output is still 20 GiB because the binder uses usable.
3. `usablePercent(...)` refuses to divide when total is non-positive or samples are invalid. It does not hide missing data behind an apparently valid percentage.
4. The name `totalMinusUsableGiB` keeps the subtraction's meaning clear without calling it the exact size of used files.
5. The real-read branch uses `getCanonicalFile()` to normalize the program's path. With an auto-configured binder in another application, still read the actual tag rather than assuming the label string matches this normalization.
6. `Locale.ROOT` keeps number formatting consistent. The registry created by the program is closed in `finally`.

### 6.3. Compiling and Running Sample Mode

Maven and JDK 17 or higher are required. With JDK 21, still compile at Java 17 level using `--release 17`.

Download dependencies into `lib`:

```shell
mvn -q dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=lib
```

PowerShell/Windows:

```powershell
New-Item -ItemType Directory -Path out -Force | Out-Null
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out DiskSpaceMetricsDemo.java
java -cp "out;lib/*" DiskSpaceMetricsDemo --sample
```

Linux/macOS:

```shell
mkdir -p out
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out DiskSpaceMetricsDemo.java
java -cp "out:lib/*" DiskSpaceMetricsDemo --sample
```

Classpath uses `;` on Windows and `:` on Linux/macOS. The first download requires network access if libraries are not yet cached locally.

Fixed stdout of sample mode:

```text
mode=sample
disk.total=107374182400 bytes
disk.free=21474836480 bytes
freeGiB=20.000 freePercent=20.000
totalMinusUsableGiB=80.000
type=GAUGE unit=bytes pathTagMatches=true
```

The output confirms the names, gauge type, byte unit, and filtering by path. It also illustrates why you should not use the 30 GiB value of `getFreeSpace()` as the predicted result for `disk.free`.

### 6.4. Running Real Mode

With a real path on Windows:

```powershell
java -cp "out;lib/*" DiskSpaceMetricsDemo "D:/data/reports"
```

With a real path on Linux/macOS:

```shell
java -cp "out:lib/*" DiskSpaceMetricsDemo /data/reports
```

Or pass `.` to read the working directory's filesystem. The path in the command must already exist; the example does not create it.

Real output adds a `path=...` line. Capacities depend on the system and can change between runs, so there is no single fixed set of numbers valid for all machines. Verify name, unit, path, and validity conditions before comparing values.

The standalone program does not run an HTTP server. To query via `/actuator/metrics/...`, use a web application with Actuator as configured earlier.

## 7. Avoiding Double-Counting Multiple Paths

### 7.1. Two Paths Can Share One Filesystem

Suppose `/data/reports` and `/data/archive` sit on the same filesystem with 100 GiB total and 20 GiB usable. Registering both paths can create two tag groups:

| path | disk.total | disk.free |
| --- | --- | --- |
| `/data/reports` | 100 GiB | 20 GiB |
| `/data/archive` | 100 GiB | 20 GiB |

Querying the gauges aggregated by name can show 200 GiB total and 40 GiB usable. That does not mean a new filesystem appeared; the capacity of the same storage location was observed through two paths.

In Spring Boot 3.3.0, the multi-path binder registers measurements for each configured element. Do not rely on the paths list assuming duplicate filesystems are automatically detected and deduplicated.

Select a specific tag when inspecting. If you need to aggregate actual capacity, identify independent storage volumes and deduplicate before summing.

### 7.2. An Aggregate Percentage Can Hide a Nearly Full Location

Even when two filesystems are independent, an aggregated percentage can mask a local problem:

| Filesystem | Total | Remaining Usable | Usable Percentage |
| --- | --- | --- | --- |
| A | 100 GiB | 1 GiB | 1% |
| B | 900 GiB | 450 GiB | 50% |
| Combined | 1000 GiB | 451 GiB | 45.1% |

An overall 45.1% ratio does not give A more space to write. Writes to A still depend on A's usable space.

Therefore, when monitoring exhaustion risk, retain enough dimensions to know which location is running low. A system-wide sum may serve a different question, but it does not replace checking each business-critical filesystem.

## 8. Metrics and DiskSpaceHealthIndicator Have Two Roles

| Component | What Does It Provide? |
| --- | --- |
| `disk.total`, `disk.free` | Numeric values for observation, historical storage, and calculation |
| `DiskSpaceHealthIndicator` | Health status evaluation based on configured path and threshold |

Health is not another meter name for `disk.free`. An `UP` status also does not tell you whether space is dropping rapidly or whether enough room remains for upcoming needs.

Example health configuration for the same report output location, with an illustrative threshold of exactly one GiB:

```yaml
management:
  health:
    diskspace:
      path: /data/reports
      threshold: 1073741824B
```

This is an additional configuration snippet for a Spring Boot application; when merging into an existing file, place entries under the same `management` key rather than creating two parallel root `management` keys.

`management.health.diskspace.path` and `management.metrics.system.diskspace.paths` are two separate settings. Changing the metrics paths list does not automatically synchronize where health checks. To compare the two results, confirm they point to the same location. [Disk space health in Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

In version 3.3.0's code, health compares usable space against the threshold to choose status; the illustrative threshold is not a rule suited to every system. Changing the health threshold neither creates more disk space nor alters the two metrics.

## 9. Containers, Permissions, and Observation Scope

### 9.1. Observing From the Environment Running the JVM

When the application runs in a container, paths are resolved within the container's filesystem environment. The default working directory may lie on a different storage layer from the mounted data volume.

Choose the volume path where real data is written. Do not look at metrics for the container's root filesystem and infer that the database or reports volume definitely has room left.

Multiple instances may see the same shared volume. Summing capacities reported by each instance can count the same storage multiple times.

### 9.2. Having Free Bytes Does Not Guarantee Writes Succeed

Capacity is an important condition, yet writes can still fail due to permissions, read-only filesystems, storage quotas, device errors, or other conditions. On filesystems with an inode concept, running out of inodes can also be a separate failure mode.

A capacity sample does not replace monitoring actual write errors or checking environment state. Do not interpret a positive number as a guarantee that every subsequent file creation will succeed.

### 9.3. Capacity Is Not I/O Speed

`disk.free` and `disk.total` do not measure read/write operations per second, write latency, throughput, or the amount of data written by the process alone.

If usable space drops from 20 to 18 GiB, that is a state change between two timestamps. Understanding the trend requires history and must account for new writes, deletions, delayed space reclamation, and activity by other processes.

A single sample is not enough to accurately predict how soon space will run out. Monitoring should combine absolute capacity, ratios, and trends over time for the exact storage location being managed.

## 10. Cross-Checking When Numbers Look Confusing

First confirm the same path and filesystem, then compare values:

1. Read the meter's actual `path` tag.
2. Check whether the path exists in the JVM's environment and points where the application writes.
3. Determine whether configured paths share the same filesystem or shared volume.
4. Compare units: bytes, GB, and GiB.
5. Check whether the reference tool reports unallocated, usable, used space, or directory size.
6. Check sample timestamps and permissions of the process performing the read.

On Linux, the following read-only commands can help inspect an existing path:

```shell
df -B1 /data/reports
df -i /data/reports
```

The first command shows capacity in bytes according to the system tool; the second shows inodes when supported by the filesystem. Do not assume every field of this tool matches a Java API without comparing definitions and environments.

On Windows with a simple drive letter, you can check:

```powershell
Get-Volume -DriveLetter D | Select-Object DriveLetter, Size, SizeRemaining
```

This is an example for drive D, not an automatic verification for every UNC path or nested mount. Cross-check the exact storage backing the application's path.

| Symptom | What to Check |
| --- | --- |
| Both disk names missing | Actuator, registry, auto-configuration, filters, and paths list |
| Value is 0 or invalid | Path, permissions, and ability to query filesystem info |
| Total nearly double what was expected | Are multiple paths on the same filesystem or multiple instances on the same volume being summed? |
| Health is good but metrics for data write location are nearly full | Are the two configurations pointing to different paths? |
| System tool and metric differ | Units, definition of available, timing, permissions, and filesystem scope |
| Data deleted yet capacity has not risen as expected | Storage mechanism, open files, update timing, and other write activity |

## 11. Practice

Try each change on the sample program and explain the outcome:

1. Change usable in `SampleFile` from 20 GiB to 5 GiB. Usable percentage becomes 5%, and `totalMinusUsableGiB` becomes 95 GiB.
2. Change only `getFreeSpace()` from 30 GiB to 40 GiB, keeping usable at 20 GiB. `disk.free` of the active binder does not change.
3. Set total to 0 in sample mode. The program refuses to compute a ratio instead of producing a fake percentage.
4. Run real mode with two existing directories on the same filesystem. Compare total capacity and explain why they are not two separate drives; usable samples may differ slightly by read timestamp.
5. Configure multiple paths in a Boot application, inspect `availableTags`, then filter each path. Do not treat name-aggregated totals as total physical capacity without deduplicating.
6. Compare health and metrics paths in an existing configuration. Explain why the two results differ before changing thresholds or formulas.

When recording a disk capacity measurement, include the path, filesystem scope, unit, and observation time together. That distinguishes "20 GiB left where the JVM writes reports" from a generic capacity number with an unspecified target.
