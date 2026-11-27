# Bigtable Java Client and HBase Compatibility

> **Chapter:** Bigtable and Memorystore  
> **Module:** **CLOUD_PROVIDERS_GCP** — Explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners learn how to choose services, secure resources, automate releases, and monitor reliability alongside cost.

**Cloud Bigtable** is a managed wide-column NoSQL service on Google Cloud suited for very large datasets accessed by **row key, prefix, or key range**. Java applications can use the **native Bigtable Java client** or the **Cloud Bigtable HBase client for Java** to preserve code built on Apache HBase APIs. The two paths are not identical: they differ in APIs, configuration, and operational limits.

This lesson builds a Java application that writes and reads **IoT device telemetry**. We design row keys, create a table/column family, write and scan data with the native client, run the same tasks through the HBase compatibility layer, and analyze migration/performance. You can start with the **Bigtable emulator** without provisioning a billable cloud cluster.

**Note:** Memorystore is a separate caching/in-memory service, not Bigtable's HBase compatibility layer. Never run commands that create or delete cloud resources in production, and do not treat Bigtable as a replacement for a relational database merely because both use the term "table."

## Learning Objectives

1. Explain instances, clusters, tables, row keys, column families, qualifiers, cells, timestamps, and app profiles.
2. Design row keys that avoid hotspots and support point reads and prefix/range scans.
3. Configure Maven, ADC, and use **`BigtableDataClient`** together with **`BigtableTableAdminClient`**.
4. Perform put/get/scan operations and understand single-row atomicity, batching, and retries.
5. Use **`BigtableConfiguration.connect`** with HBase **`Put`, `Get`, `Scan`, `ResultScanner`**.
6. Identify compatibility limits: coprocessors, region/admin APIs, filters, GC, and timestamps.
7. Test with the emulator, verify IAM/networking in a real environment, monitor, and optimize costs.
8. Plan an HBase → Bigtable migration with contract tests and rollback.

## 1. Bigtable Data Model and Row Keys

| Component | Meaning | Example |
|---|---|---|
| **Instance** | Management group for tables and clusters | `iot-lab` |
| **Cluster** | Compute nodes/replication in a single zone | `iot-lab-c1` |
| **Table** | Rows ordered lexicographically by row-key bytes | `device-metrics` |
| **Row key** | Unique row identifier, byte sequence | `07#sensor-42#20261119T100000Z` |
| **Column family** | Predeclared column group with GC policy | `reading` |
| **Qualifier** | Dynamic column name within a family | `temperature`, `humidity` |
| **Cell** | Value + timestamp under `family:qualifier` | `"23.4"` |
| **App profile** | Instance traffic routing/transaction policy | `default` |

~~~mermaid
flowchart TB
    APP["Java application"] --> N["Native Bigtable Java client"]
    APP --> H["Bigtable HBase adapter"]
    H --> API["Bigtable Data API"]
    N --> API
    API --> TABLE["Table: device-metrics"]
    TABLE --> ROW["Row: 07#sensor-42#20261119T100000Z"]
    ROW --> CELL1["reading:temperature = 23.4"]
    ROW --> CELL2["reading:humidity = 64"]
~~~

Bigtable **has no foreign keys/JOINs or PostgreSQL-style multi-row transactions**. It excels at queries for which the row key is designed upfront; arbitrary queries on any qualifier do not automatically get indexes.

### 1.1. Row Keys Start from Query Patterns

Requirements: read **a single sample** by device + timestamp, read **a range** of samples for a device, and ingest data from thousands of devices concurrently.

~~~text
07#sensor-42#20261119T100000Z
07#sensor-42#20261119T101000Z
19#sensor-73#20261119T100000Z
~~~

Here **07/19** is a deterministic hash bucket prefix derived from the device ID. A device always maps to the same prefix so its history can be scanned. When selecting the bucket count, benchmark write-load distribution and scan cost rather than guessing.

| Query type | Key design | Trade-off |
|---|---|---|
| Point read of one sample | `hash#device#timestamp` | Requires knowing the full key |
| Device history | `hash#device#` as prefix | Efficient prefix scan |
| All devices within one hour | May need another table/materialized index | Device-prefixed keys do not support this directly |
| Latest sample first | Can use reverse timestamp | Must handle units/ordering |
| Concurrent writes across devices | Hash prefix spreads load better | Cross-device scans require fan-out |

**Avoid monotonically increasing timestamp prefixes** like `20261119T100000Z#device` under heavy load, because new writes concentrate in a narrow range. Timestamps should use a fixed UTC format or deterministic binary sort order; if multiple records arrive per second, append milliseconds/sequence to prevent row-key collisions. Row keys are **bytes**, not sorted by arbitrary Unicode collation rules.

### 1.2. Families, Versions, and Garbage Collection

The demo family is `reading`, with qualifiers `temperature` and `humidity`. Bigtable supports multiple cell versions by timestamp. For instance, **GC `maxVersions(1)`** targets keeping one version, yet **GC runs asynchronously** and does not guarantee old versions disappear from every read the instant a new version is written.

| GC rule | Use case | Note |
|---|---|---|
| `maxVersions(1)` | Need only the latest value | Not an instant delete |
| `maxAge(7 days)` | Time-expiring data | May need a read filter to hide expired values |
| `union(maxAge, maxVersions)` | Eligible for deletion when either rule is met | Do not confuse with intersection |
| Application retention | Must hide data immediately per business rules | Must enforce via read/delete logic, not wait for GC |

Unlike HBase, **Bigtable can return expired data while awaiting GC** if a query omits an appropriate filter. For sensitive data, retention/GC does not replace an auditable deletion policy.

## 2. Native Java Client or HBase Compatibility?

| Criterion | **`google-cloud-bigtable`** | **`bigtable-hbase-1.x/2.x`** |
|---|---|---|
| Best fit | New Java apps adopting Bigtable | Existing code using Apache HBase APIs |
| Java API | `BigtableDataClient`, `RowMutation`, `Query`, `Filters` | `Connection`, `Table`, `Get`, `Put`, `Scan` |
| Maven artifact | `com.google.cloud:google-cloud-bigtable` | `com.google.cloud.bigtable:bigtable-hbase-2.x` |
| Admin | `BigtableTableAdminClient` | Only a subset of HBase Admin |
| Async | Native async and batch | HBase 2.x adapter provides async |
| HBase coprocessors | Not an HBase interface | **Not supported** |
| Recommendation for new code | **Preferred** | Use only for compatibility needs |

The Bigtable HBase client **does not launch HBase region servers**; it translates Java API calls to the Google-managed Bigtable backend. "HBase-compatible" does not mean every byte layout, scan filter, timestamp, and administration semantic is preserved identically.

### 2.1. Choosing the Matching Runtime Artifact

- **`bigtable-hbase-1.x`**: HBase 1.x applications.
- **`bigtable-hbase-2.x`**: HBase 2.x applications; includes async client.
- **`-hadoop` variant**: Hadoop environments.
- **`-shaded` variant**: resolves conflicts with older protobuf/Guava libraries.

**Never add both HBase 1.x and 2.x** to the same classpath. Check the dependency tree and supported libraries at [Bigtable client libraries](https://docs.cloud.google.com/bigtable/docs/reference/libraries).

## 3. Lab Environment, Emulator, and IAM

### 3.1. Preparation

- Java **17/21**, Maven, `gcloud` CLI, and Bash/Cloud Shell terminal (PowerShell requires adapting export syntax).
- **Cloud Bigtable emulator** for the offline demo, requiring no billing/IAM.
- Optionally, a real lab project with the Bigtable API enabled and an authorized instance/table.
- In the cloud: use **Application Default Credentials** or a runtime service account; never create long-lived service account keys.

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
INSTANCE_ID="YOUR_BIGTABLE_INSTANCE"
TABLE_ID="device-metrics"

# READ-ONLY.
gcloud auth list
gcloud config list project
gcloud bigtable instances list --project="$PROJECT_ID"
gcloud services list --enabled --project="$PROJECT_ID" \
  --filter="name:bigtable.googleapis.com"
~~~

### 3.2. Least-Privilege IAM

| Principal | Typical role | Use strictly for |
|---|---|---|
| Read-only app | **`roles/bigtable.reader`** | `ReadRows` |
| Read/write app | **`roles/bigtable.user`** | Data access, not infrastructure admin |
| Table admin | **`roles/bigtable.admin`** or custom role | Creating tables/families/GC |
| Developer | Approved ADC principal | Testing in a lab instance |
| Bigtable service agent | Platform-managed role | Do not grant to developers |

**Separate Table Admin from Data Client:** production apps do not need permissions to create or delete tables just to read/write telemetry. The emulator does not enforce IAM; proving least privilege requires testing in an authorized real environment.

### 3.3. Starting the Emulator (No Cloud Resources Created)

~~~bash
# Terminal 1 — local emulator.
gcloud beta emulators bigtable start --host-port=localhost:8086

# Terminal 2 — Java client will target the local endpoint.
export BIGTABLE_EMULATOR_HOST="localhost:8086"
export PROJECT_ID="demo-project"
export INSTANCE_ID="demo-instance"
export TABLE_ID="device-metrics"
~~~

The emulator **stores data strictly in RAM**, does not support full instance/cluster management APIs, **provides no TLS**, and does not work with HBase shell; however, it lets Java clients create tables and test reads/writes. To return to real Bigtable, stop the emulator (`Ctrl+C`) and **unset `BIGTABLE_EMULATOR_HOST`**. Never leave a variable pointing to localhost in production runtime.

## 4. Maven and the Native Java Client

Create a **`bigtable-native-lab/`** directory in your own practice workspace—do not create sample files inside the knowledge repository directory:

~~~text
bigtable-native-lab/
├── pom.xml
└── src/main/java/lab/BigtableNativeLab.java
~~~

### 4.1. Maven Dependency

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>lab.example</groupId>
  <artifactId>bigtable-native-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>libraries-bom</artifactId>
        <version>26.90.0</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>google-cloud-bigtable</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**`libraries-bom`** manages compatible versions across Google Cloud Java libraries, without replacing CVE scanning and compatibility checks. Before production, verify current releases at [Bigtable client libraries](https://docs.cloud.google.com/bigtable/docs/reference/libraries). Never add HBase 1.x/2.x to a native POM just to "have both options."

### 4.2. Data API and Admin API

- **`BigtableTableAdminClientV2`**: inspect/create tables and families during provisioning and migrations.
- **`BigtableDataClient`**: reads/writes in runtime services where tables and data permissions already exist.
- Initialize the data client **once** per application, share it across threads, and close it on shutdown. Opening a client per HTTP request is very expensive.
- Streaming iterators and **`Batcher`** instances should not be shared across threads; bound read ranges instead of scanning whole tables unbounded inside REST requests.

## 5. Native Java: Creating a Table, Writing, and Reading

File **`src/main/java/lab/BigtableNativeLab.java`**:

~~~java
package lab;

import com.google.api.gax.rpc.NotFoundException;
import com.google.api.gax.rpc.ServerStream;
import com.google.bigtable.admin.v2.ColumnFamily;
import com.google.bigtable.admin.v2.CreateTableRequest;
import com.google.bigtable.admin.v2.GcRule;
import com.google.bigtable.admin.v2.GetTableRequest;
import com.google.bigtable.admin.v2.Table;
import com.google.cloud.bigtable.admin.v2.BigtableTableAdminClientV2;
import com.google.cloud.bigtable.data.v2.BigtableDataClient;
import com.google.cloud.bigtable.data.v2.models.Query;
import com.google.cloud.bigtable.data.v2.models.Row;
import com.google.cloud.bigtable.data.v2.models.RowCell;
import com.google.cloud.bigtable.data.v2.models.RowMutation;
import com.google.cloud.bigtable.data.v2.models.TableId;

public final class BigtableNativeLab {
    private static final String FAMILY = "reading";

    public static void main(String[] args) throws Exception {
        String project = required("PROJECT_ID");
        String instance = required("INSTANCE_ID");
        String tableId = System.getenv().getOrDefault(
                "TABLE_ID", "device-metrics");

        // DEMO: single program both creates schema and operates on data.
        // Production should separate admin from runtime services.
        try (BigtableTableAdminClientV2 admin =
                     BigtableTableAdminClientV2.create();
             BigtableDataClient data =
                     BigtableDataClient.create(project, instance)) {

            createTableIfMissing(admin, project, instance, tableId);

            String key1 = "07#sensor-42#20261119T100000Z";
            String key2 = "07#sensor-42#20261119T101000Z";

            data.mutateRow(RowMutation.create(TableId.of(tableId), key1)
                    .setCell(FAMILY, "temperature", "23.4")
                    .setCell(FAMILY, "humidity", "64"));

            data.mutateRow(RowMutation.create(TableId.of(tableId), key2)
                    .setCell(FAMILY, "temperature", "23.7")
                    .setCell(FAMILY, "humidity", "61"));

            // Point read: null if row does not exist.
            System.out.println("POINT READ");
            printRow(data.readRow(TableId.of(tableId), key1));

            // Bounded range scan with prefix for the same device.
            Query query = Query.create(TableId.of(tableId))
                    .prefix("07#sensor-42#")
                    .limit(20);
            System.out.println("PREFIX SCAN");
            ServerStream<Row> rows = data.readRows(query);
            for (Row row : rows) {
                printRow(row);
            }
        }
    }

    private static void createTableIfMissing(
            BigtableTableAdminClientV2 admin,
            String project, String instance, String tableId) {
        String parent = "projects/" + project + "/instances/" + instance;
        String name = parent + "/tables/" + tableId;

        try {
            admin.getTable(GetTableRequest.newBuilder()
                    .setName(name)
                    .setView(Table.View.NAME_ONLY)
                    .build());
            System.out.println("Table exists: " + name);
        } catch (NotFoundException missing) {
            ColumnFamily family = ColumnFamily.newBuilder()
                    .setGcRule(GcRule.newBuilder()
                            .setMaxNumVersions(1).build())
                    .build();
            admin.createTable(CreateTableRequest.newBuilder()
                    .setParent(parent)
                    .setTableId(tableId)
                    .setTable(Table.newBuilder()
                            .putColumnFamilies(FAMILY, family)
                            .build())
                    .build());
            System.out.println("Created: " + name);
        }
    }

    private static void printRow(Row row) {
        if (row == null) {
            System.out.println("No row found");
            return;
        }
        System.out.println("rowKey=" + row.getKey().toStringUtf8());
        for (RowCell cell : row.getCells()) {
            System.out.printf("  %s:%s=%s timestamp=%d%n",
                    cell.getFamily(),
                    cell.getQualifier().toStringUtf8(),
                    cell.getValue().toStringUtf8(),
                    cell.getTimestamp());
        }
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing env: " + name);
        }
        return value;
    }
}
~~~

**Expected result:** if the table does not exist yet, it creates family `reading` with GC `maxVersions(1)`; writes two rows, point-read returns `temperature`/`humidity` for `key1`, and the prefix scan returns `key1` and `key2`. If rerun, `setCell` can create new versions and GC handles old versions later. **Do not delete tables** in sample programs.

**Limitations:** temperature values in the demo are **UTF-8 text**, not binary floats. For production, use Protobuf/Avro or versioned fixed encoding, design realistic row keys/hashes, benchmark latency, and bound scans. If the table already exists without family `reading`, writes will fail; never modify the schema of a table owned by someone else.

### 5.1. Running Locally with the Emulator

Keep the emulator running in terminal 1; in terminal 2 inside the Java project:

~~~bash
export BIGTABLE_EMULATOR_HOST="localhost:8086"
export PROJECT_ID="demo-project"
export INSTANCE_ID="demo-instance"
export TABLE_ID="device-metrics"

mvn -B clean package

# Example running temporarily via Maven exec plugin.
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java \
  -Dexec.mainClass=lab.BigtableNativeLab
~~~

When rerun while the emulator is alive, the program reads the existing table on the emulator. Once the emulator stops, data is **lost**, unlike production. If Maven hits dependency errors, inspect `dependency:tree`; do not force HBase versions into the native module.

### 5.2. Filter Returning Only the Latest Version

~~~java
// Snippet inside a method where data/tableId/key1 are already initialized:
import static com.google.cloud.bigtable.data.v2.models.Filters.FILTERS;
import com.google.cloud.bigtable.data.v2.models.Filters.Filter;

Filter newestOnly = FILTERS.limit().cellsPerColumn(1);
Row latest = data.readRow(TableId.of(tableId), key1, newestOnly);
~~~

Place imports at the **top of the file** if integrating into a class; this is a snippet, not a complete Java file. Filters do not replace effective row-key design: overly wide ranges still incur server-side processing.

### 5.3. Bulk Writes: Atomic Per Row, Not Per Batch

~~~java
// Snippet; add imports for BulkMutation and Mutation.
BulkMutation batch = BulkMutation.create(TableId.of(tableId));
batch.add("07#sensor-42#20261119T102000Z",
        Mutation.create().setCell("reading", "temperature", "23.9"));
batch.add("07#sensor-42#20261119T103000Z",
        Mutation.create().setCell("reading", "temperature", "24.1"));
data.bulkMutateRows(batch);
~~~

Bigtable guarantees each row mutation is atomic, yet a **bulk batch is not a multi-row transaction**. On partial failure, inspect which rows succeeded and retry per your idempotency policy; in particular, read-modify-write increments/appends can repeat side effects on retry. At high throughput, use benchmarked batching/async APIs with backpressure and thorough error handling.

## 6. HBase Compatibility Layer: Keeping Get/Put/Scan While Changing Backends

If a Java system already uses the Apache HBase API, the Cloud Bigtable HBase client can reduce code rewrites. Even so, the application must verify **every method, filter, and behavior** before shifting production traffic.

To avoid dependency conflicts, create a **separate lab project**:

~~~text
bigtable-hbase-lab/
├── pom.xml
└── src/main/java/lab/BigtableHBaseLab.java
~~~

### 6.1. Maven Dependency for HBase 2.x

~~~xml
<dependencies>
  <dependency>
    <groupId>com.google.cloud.bigtable</groupId>
    <artifactId>bigtable-hbase-2.x</artifactId>
    <version>2.6.5</version>
  </dependency>
</dependencies>
~~~

This is a **dependencies snippet** to add to a Java Maven project that already has compiler/packaging configuration. **`2.6.5`** is an illustrative version from Google Cloud docs; verify the version compatible with your app and Hadoop environment before deployment. If the app still uses HBase 1.x, choose **`bigtable-hbase-1.x`** rather than migrating the entire HBase model to 2.x without tests.

### 6.2. `BigtableHBaseLab.java`

This code uses the same table `device-metrics` and family `reading` created in Section 5. If run standalone before the native lab, the table/family must already be created via Admin API or a valid provisioning process.

~~~java
package lab;

import com.google.cloud.bigtable.hbase.BigtableConfiguration;
import java.io.IOException;
import org.apache.hadoop.hbase.TableName;
import org.apache.hadoop.hbase.client.Connection;
import org.apache.hadoop.hbase.client.Get;
import org.apache.hadoop.hbase.client.Put;
import org.apache.hadoop.hbase.client.Result;
import org.apache.hadoop.hbase.client.ResultScanner;
import org.apache.hadoop.hbase.client.Scan;
import org.apache.hadoop.hbase.client.Table;
import org.apache.hadoop.hbase.util.Bytes;

public final class BigtableHBaseLab {
    private static final byte[] CF = Bytes.toBytes("reading");
    private static final byte[] TEMP = Bytes.toBytes("temperature");

    public static void main(String[] args) throws IOException {
        String project = required("PROJECT_ID");
        String instance = required("INSTANCE_ID");
        String tableId = System.getenv().getOrDefault(
                "TABLE_ID", "device-metrics");

        // Create one Connection for the application lifecycle and reuse it.
        try (Connection connection =
                     BigtableConfiguration.connect(project, instance);
             Table table = connection.getTable(TableName.valueOf(tableId))) {

            byte[] key = Bytes.toBytes("07#sensor-42#20261119T104000Z");

            // Put -> Bigtable row mutation.
            Put put = new Put(key)
                    .addColumn(CF, TEMP, Bytes.toBytes("24.0"));
            table.put(put);

            // Get -> point read.
            Result result = table.get(new Get(key));
            if (result.isEmpty()) {
                System.out.println("No row");
            } else {
                System.out.printf("Get row=%s temperature=%s%n",
                        Bytes.toString(result.getRow()),
                        Bytes.toString(result.getValue(CF, TEMP)));
            }

            // Scan -> prefix read; close scanner after use.
            Scan scan = new Scan()
                    .setRowPrefixFilter(Bytes.toBytes("07#sensor-42#"));
            try (ResultScanner scanner = table.getScanner(scan)) {
                int count = 0;
                for (Result row : scanner) {
                    System.out.println(Bytes.toString(row.getRow()));
                    if (++count >= 10) {
                        break;
                    }
                }
            }
        }
    }

    private static String required(String name) {
        String v = System.getenv(name);
        if (v == null || v.isBlank()) {
            throw new IllegalArgumentException("Missing env: " + name);
        }
        return v;
    }
}
~~~

**Key points:**

- **`Connection`** is a heavyweight resource; reuse it across threads/requests per documentation instead of reconnecting per row.
- **`Get`** maps to a point read; **`Put`** maps to a row mutation; **`Scan`** returns a range/prefix depending on configuration.
- Both the native client and HBase adapter access the same Bigtable data; row keys and cell values are fundamentally **bytes**. HBase `Bytes.toBytes("24.0")` stores a UTF-8 string, whereas `Bytes.toBytes(24.0)` stores an IEEE-754 binary double that cannot be decoded with `Bytes.toString`.
- Scanners should bound row counts and be closed after use. For very large datasets, design key ranges and streaming rather than loading all `Result`s into RAM.
- The emulator works with the Java HBase client per client-library support, but **HBase shell does not work** with the Bigtable emulator.

### 6.3. Direct Comparison: Native vs. HBase

| Operation | Native Java | HBase Java |
|---|---|---|
| Client/connection | `BigtableDataClient` | `BigtableConfiguration.connect` → `Connection` |
| Write row | `RowMutation.setCell` + `mutateRow` | `Put.addColumn` + `Table.put` |
| Read row | `readRow(TableId, rowKey)` | `Table.get(Get)` |
| Prefix scan | `Query.prefix` + `readRows` | `Scan.setRowPrefixFilter` + `getScanner` |
| Iterate cells | `Row.getCells` | `Result.rawCells` or `getValue` |
| Limit versions | `Filters.limit().cellsPerColumn` | `Get`/`Scan` read versions + filters (verify compatibility) |
| Create table | `BigtableTableAdminClientV2` | HBase `Admin` supports only a subset |
| Batch writes | `bulkMutateRows` / `Batcher` | `Table.put(List)` / `BufferedMutator` per support |

**Do not assume Bigtable native API = HBase API 100%**. During migration, keeping the HBase adapter changes fewer lines of code when swapping endpoints, but can mask semantic differences if integration tests are missing.

## 7. Differences Between HBase and Bigtable You Must Test

### 7.1. Compatibility Matrix

| Feature group | Verdict | Migration impact |
|---|---|---|
| **`Get`, `Put`, `Scan`** | Core operations supported | Verify byte formats, filters, ranges |
| **Single-row atomic mutations** | Supported | Do not infer multi-row transactions |
| **Coprocessors** | **Not supported** | Move logic to another service/Dataflow/worker |
| **Regions/RegionServer/compaction** | Managed by Bigtable; many Admin APIs inapplicable | Remove or rewrite HBase operational code |
| **HBase namespaces** | Bigtable has no namespaces | Use table/row-key prefixes or separate instances |
| **HBase filters** | Some supported/limited/unsupported | Inventory every filter and its semantics |
| **`Scan#setCaching` / `Scan#setBatch`** | May be ignored | Do not rely on them to control response size |
| **Timestamps** | Bigtable microseconds, HBase milliseconds | Avoid scaling errors when migrating explicit timestamps |
| **TTL/GC** | Cleanup mechanics differ | May need read filters to hide expired cells |
| **Cell tags/visibility/row ACLs** | Not a 1-to-1 match | Design IAM/Authorized Views beyond row-level semantics |
| **HBase snapshots** | No equivalent HBase Admin operation | Design Bigtable-native backup/restore |
| **Custom filters** | Not all HBase `Filter` subclasses supported | Rewrite query/denormalization |
| **HBase shell** | Cannot be used with Bigtable emulator | Use Java client or native tooling |

The list of unsupported HBase APIs varies by adapter version; do not treat this table as a replacement for [official HBase differences](https://docs.cloud.google.com/bigtable/docs/hbase-differences).

### 7.2. Filters: Do Not Wait Until Production to Discover Gaps

Filter families like prefix or column-prefix work; however, filters such as **`DependentColumnFilter`, `WhileMatchFilter`, `SkipFilter`, `ParseFilter`**, and **custom HBase `Filter` subclasses** are unsupported. Others behave **with limitations** that differ from HBase.

- **Regex comparators** use **RE2** syntax, not full Java regex.
- **Filter expressions** have a size limit (e.g., 20 KiB per documentation); huge filters generated from thousands of conditions can fail.
- Value filters usually **do not replace an index**: Bigtable may still scan far more data than a well-designed key range.
- Never base business logic on a "partially supported" HBase filter without comparing outputs between HBase and Bigtable using test fixtures.

### 7.3. Microseconds, Milliseconds, and Custom Timestamps

Bigtable stores timestamps in **microseconds**, whereas HBase Java client APIs typically express timestamps in **milliseconds**. The adapter converts units, yet extreme timestamp values or **very large reverse timestamps** can be clamped or misconverted if outside the supported range.

~~~text
UNIX epoch example:
  milliseconds = 1700000000000
  microseconds = 1700000000000000

Relationship:
  microseconds = milliseconds × 1000
~~~

Never multiply by 1,000 twice when passing timestamps between the HBase adapter and native client. Use golden records covering small/large timestamps, multiple cell versions, and boundary tests. Bigtable's default timestamp granularity can still be **milliseconds** even though the wire protocol uses microseconds; verify table settings before supplying custom timestamps.

### 7.4. Garbage Collection and Reading Expired Data

HBase can filter out expired cells on read; Bigtable can still return cells past retention that have not yet been GC'd. To prevent an endpoint from serving expired data:

1. Define retention by event time vs. server time.
2. Apply appropriate filters/time-ranges or write/delete logic; test cases where a cell exists physically yet is expired.
3. Configure GC policies to bound long-term storage footprint.
4. Verify impacts on backups/replication/streaming and legal compliance before modifying TTLs.

**GC is not an instant-deletion guarantee.** For systems requiring legally mandated deletion, design data procedures independent of GC.

### 7.5. Operational, IAM, and Schema Differences

- HBase **`Admin.compact()`, `flush()`, `splitRegion()`, snapshots, and region management** have no direct equivalents in the Bigtable HBase adapter.
- Bigtable column family names must match valid regex rules, avoiding arbitrary characters allowed in legacy systems.
- **There are no HBase row ACLs/cell visibility labels** in the strict HBase sense. Use Google Cloud IAM, Authorized Views, and schema/instance/table separation as appropriate.
- Benchmark query latency on real Bigtable, because the emulator does not simulate clustering, autoscaling, compaction, replication, or production performance.

## 8. Migration Plan: HBase → Bigtable

A safe migration requires more than swapping a Maven dependency and editing `hbase-site.xml`. You must ensure **query results, data, throughput, latency, access controls, and operational procedures** match across all active business flows.

~~~mermaid
flowchart TD
    AUDIT["Audit HBase APIs, filters, row keys, regions, jobs"] --> DESIGN["Compatibility matrix + schema + test fixtures"]
    DESIGN --> PROTO["Prototype adapter on emulator/lab"]
    PROTO --> DATA["Historical data + incremental sync/dual write"]
    DATA --> DIFF["Compare checksums, counts, and golden queries"]
    DIFF --> LOAD["Load test, latency/cost, and failover"]
    LOAD --> GO{"Go/no-go met?"}
    GO -- "No" --> FIX["Fix design/rollback"]
    GO -- "Yes" --> CUT["Shift traffic in cohorts"]
    CUT --> WATCH["Monitor and decommission source per retention"]
~~~

### 8.1. What Must Be Inventoried

| Question | Required evidence |
|---|---|
| Does Java use HBase 1.x or 2.x? | Dependency tree and code imports |
| Are there coprocessors, custom filters, or HBase Admin region/snapshot calls? | Source search/API call inventory |
| How is data encoded? | Byte encoding, row key, qualifier, versions, timestamps |
| What are read/write rates and cell sizes? | Throughput p50/p95/p99, row size, scan ranges |
| Does business logic depend on TTL, tags, ACLs, or namespaces? | Contract/golden read tests |
| Does the HBase cluster rely on ordering/strong read behavior? | Consistency/transaction assumptions |
| Does the app have external side effects? | Idempotency/dual-write protocol |
| Backup/RPO/RTO and cutover window? | Runbook, rollback criteria |
| Is there sensitive data or regional residency constraints? | IAM, encryption, residency review |

### 8.2. Execution Phases

1. **Freeze the contract:** capture Get/Put/Scan/Filter behavior from HBase using golden fixtures covering multi-versions, null/empty cells, timestamps, and boundary keys.
2. **Choose the adapter:** use `bigtable-hbase-2.x` for HBase 2.x projects; exercise every API actually used. For new apps, prefer the native client.
3. **Design tables/keys:** do not import hotspot-prone row keys; define column families, GC, app profiles, and permissions.
4. **Choose data migration path:** select an import/batch/copy pipeline matching data volume, versioning, and cutover deadline; verify sample checksums, row counts, and point/range queries.
5. **Catch up writes:** build incremental sync/dual-write with explicit conflict and idempotency rules; never assume identical write ordering across both targets.
6. **Load test** on real Bigtable with representative traffic and estimated region/scale; never use the emulator for latency baselines.
7. **Canary cutover:** shift a subset of clients and monitor p95/p99, errors, stale reads, hot-row warnings, and cost.
8. **Rollback:** keep the source stable or define clear replay/failback steps; never delete the HBase source before reconciliation completes.

**Dual-write risk:** succeeding on HBase while failing on Bigtable (or vice versa) causes divergence. There is no default distributed transaction across both systems; use outbox/change-log/reconciliation patterns per business requirements and verify conflict handling.

### 8.3. What Can Stay vs. Change in an HBase App?

The smallest change may be swapping the HBase dependency and connection config to the Bigtable adapter while keeping `Get`/`Put`/`Scan`. However, if the code relies on HBase namespaces, coprocessors, or unsupported filters, you must **refactor behavior** rather than merely changing connection strings.

Operations must also drop assumptions about region servers/compaction tuning and move monitoring, backups, IAM, and capacity planning onto Bigtable primitives.

## 9. Retries, Consistency, and Atomicity

### 9.1. Single-Row Atomicity, Not Multi-Row

Bigtable mutations on **a single row** apply atomically; **`CheckAndMutateRow`** executes condition + mutation on the same row as a single-row transaction. `BulkMutateRows` across multiple rows does not create a batch-wide transaction.

| Operation | How can it be retried? | Risk |
|---|---|---|
| `SetCell` with fixed key/qualifier/timestamp and payload | Can be idempotent if designed so | Auto server timestamp creates a new version |
| `Put` across multiple qualifiers of **the same row** | Atomic per row | No guarantee across other rows |
| Bulk mutation across multiple rows | Retry with per-row reconciliation | Partial success |
| Increment counter | Do not retry unconditionally after timeout | Can double-increment |
| Append | Do not retry unconditionally after timeout | Can double-append |
| `CheckAndMutateRow` | Useful for single-row conditional checks | Does not replace multi-row transactions |

**Common mistake:** a deadline error after a write does not prove the server failed to commit. For financial data or counters, use durable event/job IDs and explicit deduplication; never retry blindly expecting Bigtable to enforce exactly-once side effects.

### 9.2. Multi-Cluster Replication and App Profiles

A Bigtable instance can span multiple replicated clusters. Read/write patterns and consistency depend on **app profile routing**, not solely on the Java library.

- **Single-cluster routing** helps when read-after-write consistency assumptions are required within a single cluster.
- **Multi-cluster routing** spreads traffic across clusters, but cross-cluster replication **can be eventually consistent**; new data may not appear simultaneously everywhere.
- For single-row transactions/conditional mutations, observe app profile restrictions and never send conflicting writes to multiple clusters expecting global transaction semantics.
- When immediate read-after-write is mandatory, configure matching SLAs and routing strategies with integration tests for failover/replication lag.

**Never claim Bigtable is a globally serializable multi-cluster database.** When requirements demand multi-row transactional writes, evaluate Cloud Spanner or an appropriate relational database instead of stitching together independent `RowMutation` calls.

### 9.3. Timeouts and API Errors

Errors typically surface as **gRPC/`ApiException`**: permission denied, not found, unavailable, resource exhausted, or deadline exceeded. Client libraries retry certain transient errors by default; applications must configure **end-to-end request deadlines, backoff budgets, and idempotency reviews**.

- **`PERMISSION_DENIED`/`UNAUTHENTICATED`**: check ADC/SA/IAM; do not increase retries.
- **`NOT_FOUND`**: table/instance/family or key missing; distinguish normal null rows from missing resources.
- **`UNAVAILABLE`**: safe to retry with backoff; monitor availability.
- **`RESOURCE_EXHAUSTED`**: quota/capacity/throttling; measure load before increasing parallelism.
- **`DEADLINE_EXCEEDED`**: server may have completed the write; check state before retrying non-idempotent side effects.

## 10. Designing for Throughput, Latency, and Row Hotspots

### 10.1. Avoiding Hotspots and Expensive Scans

Bigtable sorts rows by key bytes, so key distribution governs read/write load. An ascending row key or excessive traffic to a single row/family can trigger hotspots even when overall instance CPU has spare headroom.

| Symptom | Hypothesis | Action |
|---|---|---|
| Write p99 climbs, few hot keys | Row-key hotspot | Hash/salt prefix or split hot entities |
| Device scan is slow | Key range too wide | Exact prefix/range, `limit`, server filters |
| App fetches many rows then filters client-side | Not leveraging key order | Redesign query schema |
| Bigtable CPU high while QPS is low | Large rows/cells, expensive filters | Shrink row/cell sizes, inspect metrics |
| Single device accumulates millions of cells | Unbounded wide row | Split key by time/partition |
| Excessive client connections | Creating `BigtableDataClient` per request | Reuse singleton across app lifecycle |
| Thought GC rule deleted immediately | Asynchronous GC | Read filters/retention procedures |
| Latency spikes on multi-cluster routing | Replication/network/routing | Inspect app profile and client zone |

### 10.2. Illustrative Capacity Formula Only

Suppose a system has **20,000 devices**, each emitting 1 event per minute, one row per event:

\[
\text{Average writes}
= \frac{20,000}{60} \approx 333\ \text{rows/sec}.
\]

If each row contains two values plus metadata, mutation/cell counts exceed row write counts; actual throughput and cost must be measured by payload/row size rather than row keys alone. During a 5× burst, peak reaches roughly **1,667 rows/s**; benchmark p95/p99 latency and load distribution before finalizing node capacity.

Never conclude from this math that a fixed node count is "enough." Performance depends on schema, data size, read/write ratio, replication, storage type, and Bigtable compute/autoscaling settings.

### 10.3. Client Tuning

- Initialize **`BigtableDataClient` once** and reuse it, avoiding repeated gRPC channel creation.
- Choose **sync** for simple calls and **async/batcher** when high throughput with backpressure is needed.
- Set **timeouts** and retry budgets aligned with SLAs; avoid unbounded retries when quota is exhausted.
- Bound streaming scans by row count/range to prevent excessive RAM usage.
- Track client-side metrics (latency/retries/transport) where supported by the library, alongside server-side Cloud Monitoring.
- Keep client and gRPC dependencies on supported versions; test in staging before raising connection/channel counts.

## 11. Security, Monitoring, and Cost

### 11.1. Role-Appropriate Permissions

- Grant only **Bigtable Reader/User** to runtimes needing data; reserve **Table Admin** for approved provisioning/migrations.
- Locally use Application Default Credentials of an authorized identity; on Cloud Run/GKE use a runtime service account or Workload Identity.
- Never embed JSON service account keys in container images, source code, or logs.
- If using **Authorized Views**, verify table/family/qualifier scope and granted roles—never equate a view with full-table read rights.
- Encryption, network controls, row-key metadata, and retention must align with device/user data classification; never log raw sensitive cell values.

### 11.2. Operational Dashboard

| Layer | Metric/signal | Question |
|---|---|---|
| Cluster | CPU utilization, node count, storage | Is capacity sufficient and balanced? |
| Data API | Read/write ops, error rate, p95/p99 | Are SLOs being met? |
| Key Visualizer | Hot rows and hot key ranges | Does the schema have hotspots? |
| Replication | Routing, lag/failover | Does consistency match the app profile? |
| Java client | Retries, deadlines, gRPC latency | Are there connection/network bottlenecks? |
| Application | Rows read/written successfully, duplicate/invalid data | Is business logic correct? |
| Billing | Compute capacity, storage, backups, egress | What is the cost per 1M rows/ops? |

**The emulator does not simulate distribution, replication, quotas, or real Bigtable latency.** Use it strictly for API and logic tests. Run load tests on an authorized lab instance with explicit metrics and budgets.

### 11.3. Billable Cost Drivers

| Item | Depends on |
|---|---|
| Bigtable compute | Nodes/processing capacity and cluster/edition choice |
| Data storage | Cell size, versions, GC policies |
| Multi-cluster replication | Clusters/regions/replica storage and networking |
| Backups | Retention and backed-up data volume |
| Network transfer | Cross-zone/region traffic per active SKUs |
| Logging/Monitoring | Ingestion/sampling/retention |
| Migration pipeline | Dataflow, Cloud Storage, data transfer, compute |

Zero traffic does not mean zero cost: Bigtable provisions dedicated database compute/storage. Cross-check **Cloud Billing by SKU** and HA requirements before scaling down capacity, retention, or replicas.

## 12. Troubleshooting Native Java and the HBase Adapter

| Symptom | Possible cause | How to investigate |
|---|---|---|
| `PERMISSION_DENIED` | ADC/runtime SA lacks IAM | Verify principal and Bigtable roles |
| `NOT_FOUND` | Wrong project, instance, table/family | Resource IDs, Table Admin |
| Column family not found | Demo missing family `reading` | Table schema/GC |
| `UNAVAILABLE` | Transient transport/service issue | Backoff, server metrics |
| `RESOURCE_EXHAUSTED` | Quota, hotspot, capacity | Bigtable CPU, Key Visualizer |
| `DEADLINE_EXCEEDED` | Wide scan, slow downstream | Query/range, p95/p99, retries |
| HBase `UnsupportedOperationException` | Unsupported HBase Admin/filter API | HBase differences matrix |
| HBase scan differs from legacy output | Filter/GC/timestamp semantics | Golden tests on identical data |
| Decoded cell value is garbled | UTF-8 vs. binary encoding | `Bytes.toString`/`toLong`/`toDouble` |
| Maven `NoSuchMethodError` | HBase/Guava/protobuf conflict | `dependency:tree`, shaded variant |
| App slows down under scale | Creating new client per request | Reuse long-lived client |
| Local emulator OK, cloud fails | Emulator skips IAM/network/scale | Cloud lab instance test |
| Reading another cluster misses write | Multi-cluster eventual consistency | App profile, replication lag |
| High cost while idle | Compute/replication/storage still running | Cloud Billing by SKU |

### 12.1. Ordered Investigation Runbook

1. Verify **`BIGTABLE_EMULATOR_HOST`** is not accidentally pointing Java to localhost.
2. Check **`PROJECT_ID`, `INSTANCE_ID`, `TABLE_ID`**, app profile, and exact family names.
3. Verify the ADC/runtime SA principal, data roles, and admin roles at the right step.
4. Read Java logs/errors; distinguish a **normal null row** from **`NOT_FOUND` on the table**.
5. For latency, inspect client retries, server p95/p99, and key hotspots rather than blindly raising thread counts.
6. For migration diffs, compare raw row keys, qualifiers, values, timestamps, filters, and GC.
7. Roll back client version/config/traffic if tests fail; never delete HBase/Bigtable data as a fix.

Never paste credentials or raw cell contents into tickets. If correlation IDs are needed, generate request/job IDs free of personal data.

## 13. Case Study: Migrating Java Telemetry from HBase

A factory operates **50,000 sensors** with a Java/HBase app using **`Get`/`Put`/`Scan`**, TTLs, and a coprocessor to aggregate alerts.

**Migration design:**

1. **API inventory:** choose the HBase 2.x adapter for `Get`/`Put`/`Scan`; replace the coprocessor with another component such as Dataflow/Cloud Run matched to the workload.
2. **Row key design:** `hash#device#timestamp` avoids concentrating writes on ascending timestamps.
3. **Data:** backfill history and sync deltas; compare row counts, checksums, timestamps, and golden queries.
4. **Client:** test functionality on the emulator; benchmark latency/cost on a lab Bigtable instance.
5. **Cutover:** canary 1% then ramp up; track error rates, stale reads, hot rows, and cost.
6. **Rollback:** retain the HBase source until reconciliation finishes, with a plan for records written during dual-write.

**Hypothetical incident:** the team copied row key `20261119T101000Z#sensor-42` verbatim from HBase to Bigtable. Concurrent writes from all sensors hit the latest key range and p99 climbed even though overall cluster capacity was not full. The team must redesign row keys around workloads, run load tests, switch to `hash#device#time`, and add a dedicated index if hourly cross-device queries are needed.

**Acceptance criteria:** byte- and timestamp-accurate data, no unsupported HBase APIs in critical paths, p95/p99 within SLO, zero lost/duplicated side effects during migration, verified IAM/backups/rollback, and Bigtable + pipeline costs within budget.

## 14. Exercises and Guided Answers

### 14.1. Exercise A — Native Client on the Emulator

1. Start the emulator, create the Maven project, and run **`BigtableNativeLab`**.
2. Write an extra key `07#sensor-42#20261119T102000Z` with `temperature=24.0`.
3. Scan by prefix `sensor-42`, recording row keys, qualifiers, values, and timestamps.
4. Read a non-existent row and confirm **`null`**.
5. Stop/restart the emulator and confirm data is not persisted.

**Pass criteria:** writes/reads succeed, and you can explain why the emulator does not validate IAM or production performance.

### 14.2. Exercise B — HBase Get/Put/Scan

Run **`BigtableHBaseLab`** against the created table. Compare **`Put` ↔ `RowMutation`**, **`Get` ↔ `readRow`**, **`Scan` ↔ `Query.prefix`**, and how HBase converts `byte[]` to `String`. List three HBase APIs Bigtable does not support.

**Answer:** the Bigtable adapter hits the same Bigtable backend without running an HBase RegionServer; coprocessors, many region-management Admin calls, and namespaces have no equivalent support.

### 14.3. Exercise C — Choosing a Row Key

Choose among `timestamp#device`, `device#timestamp`, and `hash(device)#device#timestamp` for 10,000 events/s across many devices.

**Answer:** leading timestamp risks hotspots; leading device works if devices are diverse, though a single hot device remains risky; deterministic hash prefix improves spread while forcing cross-device scans to fan out. Decide after benchmarking.

### 14.4. Exercise D — Timestamps

An HBase timestamp of **1,700,000,000,000 ms** equals how many microseconds?

\[
1,700,000,000,000 \times 1000
= 1,700,000,000,000,000\ \mu s.
\]

Why cannot extreme reverse timestamps be copied verbatim through the adapter? **Answer:** ms → µs conversion is range-bounded and can clamp/corrupt ordering for huge values; validate with golden tests and boundary cases.

### 14.5. Exercise E — Compatibility Review

An HBase app uses a **custom coprocessor, `PageFilter`, namespaces, snapshots, and `Scan#setCaching`**. Can you simply swap the Maven artifact?

**Answer:** no. Coprocessors are unsupported; certain filters are limited; namespaces/snapshots/region Admin calls lack equivalents; `setCaching` may be ignored. You must audit, refactor, and test before cutover.

### 14.6. Exercise F — Retrying a Bulk Operation

A bulk mutation contains 100 rows; 99 succeed and 1 fails. Can the client blindly retry the entire batch without inspecting per-row status?

**Answer:** batches are not atomic across rows. Retries must inspect partial results and follow an idempotency policy; **increments/appends** must never be retried blindly because they can execute twice.

## 15. Safe Lab Cleanup

**Emulator:** stop with `Ctrl+C` and unset environment variables to avoid connecting to localhost by mistake:

~~~bash
unset BIGTABLE_EMULATOR_HOST
unset PROJECT_ID INSTANCE_ID TABLE_ID
~~~

The emulator retains no data after stopping; you do not need to create or delete Bigtable cloud resources to complete Exercises A–F.

If practicing on a real Bigtable instance, before deleting any table or instance:
- Verify the exact project, instance, table, owner, and whether others share it.
- Check backups, replication/app profiles, retention, and security policies.
- Never run bulk deletions or delete an instance just because a test finished.
- Only the owner performs cleanup under change approval; IAM bindings, logs, and backups have independent lifecycles.

**Never delete a production Bigtable instance to save money**, and never delete source HBase tables before completing migration reconciliation.

## 16. References and Checklist

- [Bigtable overview](https://docs.cloud.google.com/bigtable/docs/overview)
- [Bigtable data model and schema design](https://docs.cloud.google.com/bigtable/docs/schema-design)
- [Bigtable Java client libraries](https://docs.cloud.google.com/bigtable/docs/reference/libraries)
- [Bigtable Java hello world](https://docs.cloud.google.com/bigtable/docs/samples-java-hello-world)
- [Bigtable Java DataClient reference](https://docs.cloud.google.com/java/docs/reference/google-cloud-bigtable/latest/com.google.cloud.bigtable.data.v2.BigtableDataClient)
- [Bigtable Java AdminClient reference](https://docs.cloud.google.com/java/docs/reference/google-cloud-bigtable/latest/com.google.cloud.bigtable.admin.v2.BigtableTableAdminClient)
- [Bigtable read examples](https://docs.cloud.google.com/bigtable/docs/reading-data)
- [Bigtable write examples](https://docs.cloud.google.com/bigtable/docs/writing-data)
- [Bigtable emulator](https://docs.cloud.google.com/bigtable/docs/emulator)
- [Bigtable HBase API](https://docs.cloud.google.com/bigtable/docs/hbase-bigtable)
- [Differences between HBase and Bigtable](https://docs.cloud.google.com/bigtable/docs/hbase-differences)
- [Connect using HBase](https://docs.cloud.google.com/bigtable/docs/hbase-connecting)
- [Bigtable app profiles and routing](https://docs.cloud.google.com/bigtable/docs/routing)
- [Bigtable IAM roles](https://docs.cloud.google.com/bigtable/docs/access-control)
- [Bigtable Key Visualizer](https://docs.cloud.google.com/bigtable/docs/keyvis-overview)
- [Bigtable pricing](https://cloud.google.com/bigtable/pricing)

**Checklist:** define query patterns → design row keys/families/GC → native client for new apps or HBase adapter for migrations → emulator CRUD/scan tests → verify IAM on cloud lab → compatibility matrix/filter/timestamp tests → bulk/retry/idempotency → benchmark p95/p99/hotspots → replication/backups/cost → evidence-backed cutover/rollback.

**Connecting to the `CLOUD_PROVIDERS_GCP` track:** Bigtable fits large-scale row-key workloads; Cloud Run/GKE/Compute Engine can access it via the Java client, while still requiring **IAM, networking, reliability observability, and cost control**. Choose the **native client** when no HBase abstraction is needed; during migration, the adapter preserves interfaces **without erasing semantic differences** between Bigtable and Apache HBase.
