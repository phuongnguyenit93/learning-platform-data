# Bigtable Java client và tương thích HBase

> **Chương:** Bigtable và Memorystore  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

**Cloud Bigtable** là dịch vụ NoSQL dạng wide-column được quản lý trên Google Cloud, thích hợp cho dữ liệu rất lớn với truy cập theo **row key, tiền tố hoặc dải khóa**. Ứng dụng Java có thể dùng **Bigtable Java client gốc** hoặc **Cloud Bigtable HBase client for Java** để duy trì code dựa trên Apache HBase API. Hai con đường không hoàn toàn giống nhau: khác API, cấu hình và những giới hạn vận hành.

Bài xây dựng ứng dụng Java ghi và đọc **telemetry của thiết bị IoT**. Ta thiết kế row key, tạo table/column family, viết và quét dữ liệu với native client, thử cùng tác vụ qua HBase compatibility layer, rồi phân tích migration/performance. Có thể bắt đầu bằng **Bigtable emulator** mà không tạo cloud cluster tính phí.

**Lưu ý:** Memorystore là dịch vụ cache/in-memory riêng, không phải HBase compatibility layer của Bigtable. Không chạy lệnh tạo/xóa cloud resources trên production và không dùng Bigtable thay một cơ sở dữ liệu quan hệ chỉ vì cùng có khái niệm “table”.

## Mục tiêu học tập

1. Giải thích instance, cluster, table, row key, column family, qualifier, cell, timestamp và app profile.
2. Thiết kế row key tránh hotspot, hỗ trợ point-read và prefix/range scans.
3. Cấu hình Maven, ADC và dùng **BigtableDataClient** cùng **BigtableTableAdminClient**.
4. Thao tác put/get/scan, hiểu single-row atomicity, batch và retries.
5. Dùng **BigtableConfiguration.connect** với HBase **Put, Get, Scan, ResultScanner**.
6. Nêu giới hạn tương thích: coprocessors, region/admin APIs, filters, GC, timestamps.
7. Test với emulator, kiểm chứng IAM/network trên môi trường thật, giám sát và tối ưu chi phí.
8. Lập kế hoạch migration HBase → Bigtable có contract tests và rollback.

## 1. Bigtable data model và row key

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **Instance** | Nhóm quản lý tables và clusters | iot-lab |
| **Cluster** | Nơi có compute nodes/replication tại một zone | iot-lab-c1 |
| **Table** | Các rows có khóa được sắp thứ tự byte | device-metrics |
| **Row key** | Khóa duy nhất của hàng, byte sequence | 07#sensor-42#20261119T100000Z |
| **Column family** | Nhóm columns khai báo trước, có GC policy | reading |
| **Qualifier** | Tên cột có thể thêm động trong family | temperature, humidity |
| **Cell** | Value + timestamp thuộc family:qualifier | "23.4" |
| **App profile** | Định tuyến traffic/transaction policy của instance | default |

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

Bigtable **không có foreign keys/JOIN hoặc transaction đa hàng theo kiểu PostgreSQL**. Nó phục vụ tốt các query mà row key được thiết kế trước; truy vấn ngẫu nhiên trên bất kỳ qualifier nào không tự có index.

### 1.1. Row key bắt đầu từ query pattern

Yêu cầu: đọc **một mẫu** theo device + timestamp, đọc **một khoảng** mẫu của device, và ghi dữ liệu từ hàng nghìn devices cùng lúc.

~~~text
07#sensor-42#20261119T100000Z
07#sensor-42#20261119T101000Z
19#sensor-73#20261119T100000Z
~~~

Ở đây **07/19** là tiền tố hash bucket ổn định từ device ID. Một device luôn có cùng prefix để quét lịch sử được. Khi chọn số buckets, cần benchmark phân bố write load và chi phí scan; không chọn ngẫu nhiên.

| Kiểu truy vấn | Key design | Đánh đổi |
|---|---|---|
| Point read một sample | hash#device#timestamp | Cần biết khóa hoàn chỉnh |
| Lịch sử của device | hash#device# làm prefix | Hiệu quả prefix scan |
| Tất cả thiết bị trong một giờ | Có thể cần bảng/materialized index khác | Key theo device không hỗ trợ trực tiếp |
| Latest sample trước | Có thể dùng reverse timestamp | Phải xử lý units/ordering |
| Writes đồng thời nhiều devices | Hash prefix phân tán hơn | Cross-device scan phải fan-out |

**Tránh prefix timestamp chỉ tăng dần** như **20261119T100000Z#device** ở tải lớn, vì writes mới có thể dồn vào dải hẹp. Timestamp nên có định dạng UTC cố định hoặc binary sort order xác định; nếu nhiều records/giây, thêm millis/sequence để tránh trùng row key. Row key là **bytes**, không mặc định sắp theo mọi cách so chuỗi Unicode.

### 1.2. Families, versions và garbage collection

Family demo là **reading**, các qualifiers **temperature** và **humidity**. Bigtable hỗ trợ nhiều phiên bản cell theo timestamp. Ví dụ **GC maxVersions(1)** giữ mục tiêu một version, nhưng **GC chạy bất đồng bộ**, không bảo đảm phiên bản cũ biến mất khỏi mọi read ngay khi bạn ghi bản mới.

| GC rule | Ứng dụng | Lưu ý |
|---|---|---|
| maxVersions(1) | Chỉ cần giá trị cuối | Không phải delete tức thì |
| maxAge(7 days) | Dữ liệu hết hạn theo thời gian | Có thể cần read filter để ẩn giá trị đã expired |
| union(maxAge, maxVersions) | Điều kiện xóa khi một rule đạt | Đừng nhầm với intersection |
| Application retention | Cần ẩn data ngay theo nghiệp vụ | Phải kiểm soát read/delete, không trông chờ GC |

Khác HBase, **Bigtable có thể trả dữ liệu đã hết hạn trong lúc chờ GC** nếu query không áp filter phù hợp. Với dữ liệu nhạy cảm, retention/GC không thay thế chính sách xóa có kiểm chứng.

## 2. Native Java client hay HBase compatibility?

| Tiêu chí | **google-cloud-bigtable** | **bigtable-hbase-1.x/2.x** |
|---|---|---|
| Phù hợp | Java app mới dùng Bigtable | Code đã sử dụng Apache HBase APIs |
| API Java | BigtableDataClient, RowMutation, Query, Filters | Connection, Table, Get, Put, Scan |
| Maven artifact | com.google.cloud:google-cloud-bigtable | com.google.cloud.bigtable:bigtable-hbase-2.x |
| Admin | BigtableTableAdminClient | Chỉ một phần HBase Admin |
| Async | Native async và batch | HBase 2.x adapter có async |
| HBase coprocessors | Không phải giao diện HBase | **Không hỗ trợ** |
| Khuyến nghị khi viết mới | **Ưu tiên** | Chỉ dùng vì yêu cầu tương thích |

Bigtable HBase client **không khởi động HBase region servers**; nó dịch API Java sang backend Bigtable do Google vận hành. “HBase-compatible” không đồng nghĩa mọi byte, scan filter, timestamp và administration semantics được bảo toàn.

### 2.1. Chọn artifact tương ứng runtime

- **bigtable-hbase-1.x**: ứng dụng HBase 1.x.
- **bigtable-hbase-2.x**: ứng dụng HBase 2.x; có async client.
- Biến thể **-hadoop**: môi trường Hadoop.
- Biến thể **-shaded**: giải quyết một số xung đột thư viện protobuf/Guava cũ.

**Không thêm HBase 1.x và 2.x đồng thời** vào cùng classpath. Kiểm tra dependency tree và thư viện được hỗ trợ tại [Bigtable client libraries](https://docs.cloud.google.com/bigtable/docs/reference/libraries).

## 3. Môi trường lab, emulator và IAM

### 3.1. Chuẩn bị

- Java **17/21**, Maven, gcloud CLI và terminal Bash/Cloud Shell (PowerShell cần đổi cú pháp exports).
- **Cloud Bigtable emulator** cho phần demo offline, không cần billing/IAM.
- Tùy chọn project lab thật có Bigtable API bật và một instance/table đã được cho phép.
- Ở cloud: dùng **Application Default Credentials** hoặc runtime service account, không tạo long-lived service account key.

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
INSTANCE_ID="YOUR_BIGTABLE_INSTANCE"
TABLE_ID="device-metrics"

# CHỈ ĐỌC.
gcloud auth list
gcloud config list project
gcloud bigtable instances list --project="$PROJECT_ID"
gcloud services list --enabled --project="$PROJECT_ID" \
  --filter="name:bigtable.googleapis.com"
~~~

### 3.2. IAM tối thiểu

| Principal | Vai trò điển hình | Chỉ dùng cho |
|---|---|---|
| App chỉ đọc | **roles/bigtable.reader** | ReadRows |
| App cần read/write | **roles/bigtable.user** | Dữ liệu, không phải quản trị hạ tầng |
| Admin bảng | **roles/bigtable.admin** hoặc custom role | Create table/family/GC |
| Developer | Principal ADC đã được duyệt | Thử trong instance lab |
| Bigtable service agent | Role do nền tảng quản lý | Không cấp cho developer |

**Tách Table Admin khỏi Data Client:** app production không cần quyền tạo/xóa table chỉ để đọc/ghi telemetry. Emulator không kiểm chứng IAM; muốn chứng minh least privilege phải test trên môi trường thật được cấp quyền.

### 3.3. Khởi động emulator (không tạo cloud resource)

~~~bash
# Terminal 1 — local emulator.
gcloud beta emulators bigtable start --host-port=localhost:8086

# Terminal 2 — Java client sẽ trỏ tới endpoint local.
export BIGTABLE_EMULATOR_HOST="localhost:8086"
export PROJECT_ID="demo-project"
export INSTANCE_ID="demo-instance"
export TABLE_ID="device-metrics"
~~~

Emulator **chỉ lưu dữ liệu trong RAM**, không hỗ trợ đầy đủ API quản lý instances/clusters, **không cung cấp TLS** và không dùng HBase shell; nhưng cho phép dùng Java client để tạo table và thử read/write. Để quay lại Bigtable thật, dừng emulator (Ctrl+C) và **unset BIGTABLE_EMULATOR_HOST**. Không được giữ biến trỏ localhost trong runtime production.

## 4. Maven và native Java client

Tạo thư mục **bigtable-native-lab/** ở môi trường thực hành riêng của người học, không tạo tệp mẫu trong thư mục bài kiến thức:

~~~text
bigtable-native-lab/
├── pom.xml
└── src/main/java/lab/BigtableNativeLab.java
~~~

### 4.1. Maven dependency

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

**libraries-bom** quản lý dependency versions của Google Cloud Java libraries, không thay việc kiểm tra CVEs và compatibility. Khi dùng production cần rà soát bản mới của [Bigtable client libraries](https://docs.cloud.google.com/bigtable/docs/reference/libraries). Không thêm HBase 1.x/2.x vào POM native chỉ để “có cả hai lựa chọn”.

### 4.2. Data API và Admin API

- **BigtableTableAdminClientV2:** xem/tạo table và family, dùng trong provisioning và migration.
- **BigtableDataClient:** reads/writes, dùng trong runtime đã có table và quyền data.
- Data client nên **khởi tạo một lần** cho ứng dụng, chia sẻ giữa threads, đóng khi shutdown. Mở client trên mỗi HTTP request rất tốn tài nguyên.
- Streaming iterator và các **Batcher** không nên chia sẻ giữa threads; đọc giới hạn phạm vi, đừng scan toàn table vô hạn trong REST request.

## 5. Native Java: tạo table, ghi và đọc

File **src/main/java/lab/BigtableNativeLab.java**:

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

        // DEMO: một chương trình vừa tạo schema vừa thao tác data.
        // Production nên tách admin khỏi service runtime.
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

            // Point read: null nếu không có row.
            System.out.println("POINT READ");
            printRow(data.readRow(TableId.of(tableId), key1));

            // Range scan có giới hạn với prefix cùng device.
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

**Kỳ vọng:** nếu table chưa có, tạo family reading với GC maxVersions(1); ghi hai rows, point-read trả temperature/humidity tại key1, prefix scan trả key1 và key2. Nếu chạy lại, setCell có thể tạo các versions mới và GC xử lý versions cũ sau đó. **Không xóa table** trong chương trình mẫu.

**Giới hạn:** dữ liệu temperature trong demo là **UTF-8 text**, không phải binary float. Với production dùng protobuf/Avro hoặc encoding cố định được version hóa, thiết kế row key/hash thực tế, đo latency và giới hạn scan. Nếu table đã có nhưng thiếu family reading, thao tác ghi sẽ lỗi; không tự thay schema của table có owner khác.

### 5.1. Chạy local với emulator

Ở terminal 1 giữ emulator chạy; terminal 2 ở project Java:

~~~bash
export BIGTABLE_EMULATOR_HOST="localhost:8086"
export PROJECT_ID="demo-project"
export INSTANCE_ID="demo-instance"
export TABLE_ID="device-metrics"

mvn -B clean package

# Ví dụ chạy qua Maven exec plugin tạm thời.
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java \
  -Dexec.mainClass=lab.BigtableNativeLab
~~~

Khi chạy lại demo, program sẽ đọc table đã có trên emulator còn sống. Sau khi dừng emulator, dữ liệu **mất**, khác production. Nếu Maven lỗi dependency hãy xem kết quả dependency:tree; không ép phiên bản HBase vào module native.

### 5.2. Filter chỉ trả version mới nhất

~~~java
// Trích đoạn trong method có data/tableId/key1 đã khởi tạo:
import static com.google.cloud.bigtable.data.v2.models.Filters.FILTERS;
import com.google.cloud.bigtable.data.v2.models.Filters.Filter;

Filter newestOnly = FILTERS.limit().cellsPerColumn(1);
Row latest = data.readRow(TableId.of(tableId), key1, newestOnly);
~~~

Các dòng import phải đặt ở **đầu file** nếu tích hợp vào class; đây là trích đoạn, không phải file Java hoàn chỉnh. Filter không thay thế thiết kế row key hiệu quả: range quá rộng vẫn tốn xử lý server-side.

### 5.3. Bulk write: atomic theo row, không theo batch

~~~java
// Trích đoạn, thêm imports cho BulkMutation và Mutation.
BulkMutation batch = BulkMutation.create(TableId.of(tableId));
batch.add("07#sensor-42#20261119T102000Z",
        Mutation.create().setCell("reading", "temperature", "23.9"));
batch.add("07#sensor-42#20261119T103000Z",
        Mutation.create().setCell("reading", "temperature", "24.1"));
data.bulkMutateRows(batch);
~~~

Bigtable đảm bảo mỗi row mutation là nguyên tử, nhưng **bulk batch không phải transaction trên nhiều rows**. Khi có partial failure, đánh giá những row đã ghi và retry theo idempotency policy; đặc biệt read-modify-write increments/appends có thể lặp side effect khi retry. Khi throughput cao hãy dùng batching/async đã benchmark, backpressure và error handling đầy đủ.

## 6. HBase compatibility layer: giữ Get/Put/Scan khi chuyển backend

Nếu hệ thống Java đã sử dụng Apache HBase API, Cloud Bigtable HBase client có thể giảm lượng code phải viết lại. Tuy vậy, ứng dụng phải kiểm tra **từng method, filter và behavior** trước khi chuyển production traffic.

Để tránh xung đột dependency, tạo **project lab riêng**:

~~~text
bigtable-hbase-lab/
├── pom.xml
└── src/main/java/lab/BigtableHBaseLab.java
~~~

### 6.1. Maven dependency cho HBase 2.x

~~~xml
<dependencies>
  <dependency>
    <groupId>com.google.cloud.bigtable</groupId>
    <artifactId>bigtable-hbase-2.x</artifactId>
    <version>2.6.5</version>
  </dependency>
</dependencies>
~~~

Đây là **đoạn dependencies** thêm vào một Maven project Java đã có cấu hình compiler/packaging phù hợp. **2.6.5** là mốc ví dụ từ tài liệu Google Cloud; kiểm tra bản phù hợp với ứng dụng và môi trường Hadoop trước triển khai. Nếu ứng dụng vẫn dùng HBase 1.x, chọn **bigtable-hbase-1.x**, không tự thay toàn bộ HBase model sang 2.x khi chưa có test.

### 6.2. BigtableHBaseLab.java

Code dùng cùng table **device-metrics** và family **reading** đã tạo ở mục 5. Nếu chạy riêng trước native lab, table/family phải được tạo bằng Admin API hoặc quy trình hạ tầng hợp lệ.

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

        // Tạo một Connection cho lifecycle của ứng dụng, dùng lại nó.
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

            // Scan -> prefix read; đóng scanner sau khi dùng.
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

**Điều cần hiểu:**

- **Connection** là tài nguyên nặng, nên dùng lại giữa nhiều threads/requests theo hướng dẫn; không kết nối mỗi lần xử lý row.
- **Get** tương ứng point read; **Put** tương ứng mutation vào row; **Scan** trả range/prefix tùy cấu hình.
- Cả native client và HBase adapter cùng truy cập Bigtable data; row key và cell values về bản chất đều là **bytes**. HBase **Bytes.toBytes("24.0")** lưu chuỗi UTF-8; **Bytes.toBytes(24.0)** lưu encoding khác, không thể đọc về bằng **Bytes.toString** mà bảo đảm đúng.
- Scanner nên giới hạn số rows và đóng sau khi sử dụng. Với datasets rất lớn, thiết kế key ranges và streaming, không load tất cả Results vào RAM.
- Emulator dùng được với Java HBase client theo hỗ trợ client library, nhưng **HBase shell không dùng được** với Bigtable emulator.

### 6.3. So sánh trực tiếp native và HBase

| Nghiệp vụ | Native Java | HBase Java |
|---|---|---|
| Client/connection | BigtableDataClient | BigtableConfiguration.connect → Connection |
| Ghi row | RowMutation.setCell + mutateRow | Put.addColumn + Table.put |
| Đọc row | readRow(TableId, rowKey) | Table.get(Get) |
| Quét prefix | Query.prefix + readRows | Scan.setRowPrefixFilter + getScanner |
| Duyệt cells | Row.getCells | Result.rawCells hoặc getValue |
| Giới hạn versions | Filters.limit().cellsPerColumn | Get/Scan read versions + filters (kiểm tra tương thích) |
| Tạo table | BigtableTableAdminClientV2 | HBase Admin chỉ hỗ trợ subset |
| Batch writes | bulkMutateRows / Batcher | Table.put(List) / BufferedMutator theo hỗ trợ |

**Đừng suy Bigtable native API = HBase API 100%**. Khi migration, giữ HBase adapter giúp đổi endpoint ít code hơn nhưng có thể che khác biệt semantics nếu thiếu integration tests.

## 7. Những khác biệt giữa HBase và Bigtable phải kiểm thử

### 7.1. Ma trận compatibility

| Nhóm tính năng | Kết luận | Tác động khi migration |
|---|---|---|
| **Get, Put, Scan** | Có hỗ trợ các thao tác cốt lõi | Kiểm tra byte format, filters, ranges |
| **Single-row atomic mutations** | Có | Không suy ra transaction nhiều rows |
| **Coprocessors** | **Không hỗ trợ** | Chuyển logic sang service/Dataflow/worker khác |
| **Regions/RegionServer/compaction** | Bigtable tự quản, nhiều Admin APIs không áp dụng | Bỏ hoặc viết lại code vận hành HBase |
| **HBase namespaces** | Bigtable không dùng namespaces | Đặt tên table/row key prefix hoặc phân tách instance |
| **HBase filters** | Một số có/giới hạn/không hỗ trợ | Kiểm kê từng filter và semantic |
| **Scan#setCaching / Scan#setBatch** | Có thể bị bỏ qua | Không dựa vào chúng để kiểm soát response size |
| **Timestamps** | Bigtable microseconds, HBase milliseconds | Tránh sai khi migrate explicit timestamps |
| **TTL/GC** | Cơ chế dọn dẹp không giống hệt | Có thể cần read filter để ẩn expired cells |
| **Cell tags/visibility/row ACL** | Không tương thích một-một | Thiết kế IAM/authorized views ngoài row-level semantics |
| **HBase snapshots** | Không phải thao tác HBase Admin tương đương | Thiết kế backup/restore Bigtable riêng |
| **Custom filters** | Không hỗ trợ mọi subclass HBase Filter | Viết lại query/denormalization |
| **HBase shell** | Không dùng với Bigtable emulator | Dùng Java client hoặc native tooling |

Danh sách HBase APIs không hỗ trợ thay đổi theo phiên bản adapter; không coi bảng này là thay thế [official HBase differences](https://docs.cloud.google.com/bigtable/docs/hbase-differences).

### 7.2. Filters: đừng đợi đến production mới phát hiện

Các nhóm filters như prefix hoặc column-prefix có thể dùng được; nhưng một số **DependentColumnFilter, WhileMatchFilter, SkipFilter, ParseFilter** và **custom HBase Filter subclasses** không được hỗ trợ. Một số filters khác hoạt động **có giới hạn**, không giống HBase.

- **Regex comparators** dùng cú pháp **RE2**, không phải đầy đủ Java regex.
- **Filter expression** có giới hạn kích thước (ví dụ 20 KiB theo tài liệu); một filter cực dài sinh từ hàng nghìn điều kiện có thể fail.
- Filter theo value thường **không thay index**: Bigtable có thể phải đọc/quét dữ liệu nhiều hơn so với key-range phù hợp.
- Đừng dùng một filter HBase được hỗ trợ “có giới hạn” làm nền tảng cho quyết định nghiệp vụ nếu chưa so sánh outputs giữa HBase và Bigtable bằng test fixtures.

### 7.3. Microseconds, milliseconds và timestamp tự tạo

Bigtable lưu timestamp **microseconds**, trong khi HBase Java client APIs thường diễn đạt timestamps **milliseconds**. Adapter chuyển đổi, nhưng các giá trị timestamp đặc biệt hoặc **reverse timestamp rất lớn** có thể bị clamp/chuyển sai nếu vượt phạm vi tương thích.

~~~text
Mốc UNIX (ví dụ):
  milliseconds = 1700000000000
  microseconds = 1700000000000000

Quan hệ:
  microseconds = milliseconds × 1000
~~~

Không tự nhân 1000 hai lần khi đưa timestamp qua HBase adapter rồi native client. Dùng golden records gồm timestamps nhỏ/lớn, các version của cùng cell và test boundary. Bigtable mặc định timestamp granularity có thể giới hạn tới **milliseconds** dù giao thức dùng microseconds; hãy xem table setting trước khi tự chỉ định timestamp.

### 7.4. Garbage collection và khả năng đọc dữ liệu hết hạn

HBase có thể lọc expired cells khi đọc; Bigtable có thể vẫn trả cells đã tới hạn retention nhưng chưa được GC. Muốn endpoint không phục vụ data đã hết hạn:

1. Xác định retention theo event-time hay server-time.
2. Dùng filter/time-range hoặc ghi/delete logic phù hợp; kiểm thử khi cell tồn tại nhưng expired.
3. Đặt GC policy để kiểm soát storage footprint lâu dài.
4. Kiểm chứng ảnh hưởng tới backup/replication/streaming và pháp lý trước khi đổi TTL.

**GC không phải ngay-lập-tức delete guarantee.** Trong các hệ cần xóa dữ liệu theo yêu cầu pháp lý, thiết kế thủ tục dữ liệu độc lập với GC.

### 7.5. Operations, IAM và schema khác nhau

- HBase **Admin.compact(), flush(), splitRegion(), snapshots và region management** không có tương đương trực tiếp trong Bigtable HBase adapter.
- Bigtable column family names phải tuân regex hợp lệ, tránh ký tự tùy ý vốn được hệ cũ cho phép.
- **Không có HBase row ACL/cell visibility** theo đúng nghĩa HBase. Sử dụng Google Cloud IAM, Authorized Views và tách dữ liệu theo schema/instance/table khi phù hợp.
- Query access/latency phải benchmark trên Bigtable thật, vì emulator không mô phỏng clustering, autoscaling, compaction, replication và hiệu năng production.

## 8. Kế hoạch migration HBase → Bigtable

Một migration an toàn không chỉ thay Maven dependency và sửa **hbase-site.xml**. Cần đảm bảo **kết quả truy vấn, dữ liệu, throughput, độ trễ, quyền truy cập và quy trình vận hành** tương đương ở những phần nghiệp vụ đang sử dụng.

~~~mermaid
flowchart TD
    AUDIT["Audit HBase APIs, filters, row keys, regions, jobs"] --> DESIGN["Compatibility matrix + schema + test fixtures"]
    DESIGN --> PROTO["Prototype adapter trên emulator/lab"]
    PROTO --> DATA["Dữ liệu lịch sử + incremental sync/dual write"]
    DATA --> DIFF["So sánh checksums, counts và golden queries"]
    DIFF --> LOAD["Load test, latency/cost và failover"]
    LOAD --> GO{"Go/no-go đạt?"}
    GO -- "Không" --> FIX["Sửa thiết kế/rollback"]
    GO -- "Có" --> CUT["Chuyển traffic theo từng nhóm"]
    CUT --> WATCH["Giám sát và đóng source theo retention"]
~~~

### 8.1. Những việc phải kiểm kê

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Java đang dùng HBase 1.x hay 2.x? | Dependency tree và code imports |
| Có coprocessors, custom filters, HBase Admin region/snapshot calls? | Search source/API call inventory |
| Dữ liệu lưu dạng gì? | Encoding bytes, row key, qualifier, versions, timestamps |
| Tần suất read/write và kích thước cells? | Throughput p50/p95/p99, row size, scan range |
| Có nghiệp vụ dựa vào TTL, tags, ACL hoặc namespaces? | Contract/golden read tests |
| Cluster HBase có cần ordering/strong read behavior? | Consistency/transactions assumptions |
| App có external side effects? | Idempotency/dual-write protocol |
| Backup/RPO/RTO và cutover window? | Runbook, rollback criteria |
| Có dữ liệu nhạy cảm hay ràng buộc vùng địa lý? | IAM, encryption, residency review |

### 8.2. Các giai đoạn thực hiện

1. **Đóng băng contract:** ghi lại hành vi Get/Put/Scan/Filters từ HBase bằng bộ golden fixtures bao gồm multi-versions, null/empty cells, timestamps và boundary keys.
2. **Chọn adapter:** dùng **bigtable-hbase-2.x** cho project HBase 2.x; thử các APIs thực sự được dùng. Với ứng dụng mới, cân nhắc native client.
3. **Thiết kế table/keys:** không import row key gây hotspot; định nghĩa column families, GC, app profiles và quyền.
4. **Chọn đường dữ liệu:** dùng pipeline import/batch/copy phù hợp lượng data, versioning và deadline; kiểm tra sample checksums, row counts và point/range queries.
5. **Bắt kịp writes:** cần incremental synchronization/dual-write có quy tắc conflict và idempotency; không dựa vào thứ tự hai đích.
6. **Load test** trên Bigtable thật với traffic đại diện và vùng/quy mô đã dự toán; emulator không dùng làm chuẩn latency.
7. **Canary cutover:** chuyển một nhóm clients, ghi p95/p99, errors, stale reads, hot row warnings và cost.
8. **Rollback:** giữ source ổn định hoặc định nghĩa chiến lược replay/chuyển ngược rõ ràng; không xóa source HBase trước khi đối soát xong.

**Rủi ro khi dual-write:** gửi thành công vào HBase và thất bại ở Bigtable (hoặc ngược lại) có thể gây divergence. Không có distributed transaction mặc định giữa hai hệ; dùng outbox/change log/reconciliation theo nghiệp vụ và kiểm tra conflicts.

### 8.3. Điều gì được phép thay đổi ở HBase app?

Một thay đổi nhỏ nhất có thể là thay HBase dependency và cấu hình connection sang Bigtable adapter, giữ nguyên **Get/Put/Scan**. Nhưng nếu code dùng HBase namespaces, coprocessor hoặc unsupported filters, phải **refactor behavior**, không chỉ thay connection string.

Đội vận hành cũng phải bỏ assumptions về region servers/compaction tuning và chuyển monitoring, backup, IAM, capacity planning sang Bigtable primitives.

## 9. Retry, consistency và tính nguyên tử

### 9.1. Single-row atomicity, multi-row không nguyên tử

Bigtable mutations trên **một row** có thể áp dụng nguyên tử; **CheckAndMutateRow** thực hiện điều kiện + mutation trên cùng row theo transaction một row. BulkMutateRows nhiều rows không tạo transaction trên toàn batch.

| Thao tác | Có thể retry thế nào? | Nguy cơ |
|---|---|---|
| SetCell với key/qualifier/timestamp và payload cố định | Có thể idempotent nếu thiết kế như vậy | Auto server timestamp có thể tạo version khác |
| Put nhiều qualifiers của **cùng row** | Atomic theo row | Không bảo đảm với row khác |
| Bulk mutation nhiều rows | Retry có đối soát từng row | Partial success |
| Increment counter | Không retry vô điều kiện sau timeout | Có thể tăng hai lần |
| Append | Không retry vô điều kiện sau timeout | Có thể nối hai lần |
| CheckAndMutateRow | Hữu ích làm điều kiện trong 1 row | Không thay transaction nhiều rows |

**Sai lầm thường gặp:** lỗi deadline sau write không chứng minh server chưa commit. Với dữ liệu tài chính hoặc counters, dùng event/job ID bền vững và chiến lược chống trùng phù hợp; đừng ghi theo kiểu retry vô điều kiện rồi hy vọng Bigtable tự đảm bảo exactly-once side effects.

### 9.2. Multi-cluster replication và app profiles

Một Bigtable instance có thể có nhiều clusters với replication. Mẫu đọc/ghi và độ nhất quán phụ thuộc **app profile routing**, chứ không phải chỉ phụ thuộc Java library.

- **Single-cluster routing** hữu ích khi cần các giả định nhất quán/read-after-write trong một cluster thích hợp.
- **Multi-cluster routing** giúp điều phối traffic sang nhiều clusters nhưng replication giữa clusters **có thể eventual consistency**; dữ liệu mới có thể chưa xuất hiện đồng thời ở mọi cluster.
- Với các single-row transaction/conditional mutations, kiểm tra giới hạn app profile và không gửi conflicting writes đến nhiều clusters rồi mặc định kết quả giống một transaction toàn cầu.
- Khi phải đọc ngay sau ghi, đặt SLA và routing strategy phù hợp, có integration tests cho failover/replication lag.

**Không tuyên bố Bigtable là globally serializable multi-cluster database.** Khi requirement buộc multi-row transactional writes, cần đánh giá Cloud Spanner hoặc cơ sở dữ liệu quan hệ phù hợp thay vì tự xây transaction bằng nhiều RowMutation độc lập.

### 9.3. Timeouts và API errors

Các lỗi thường đến từ **gRPC/ApiException**: permission denied, not found, unavailable, resource exhausted hoặc deadline exceeded. Client libraries có thể retry một số lỗi tạm thời theo chính sách mặc định; ứng dụng cần đặt **end-to-end request deadline, backoff budget và idempotency review**.

- **PERMISSION_DENIED/UNAUTHENTICATED:** kiểm tra ADC/SA/IAM, không tăng retries.
- **NOT_FOUND:** table/instance/family hoặc key chưa tồn tại; phân biệt null row bình thường và resource missing.
- **UNAVAILABLE:** có thể retry có backoff, giám sát availability.
- **RESOURCE_EXHAUSTED:** quota/capacity/throttling; đo tải trước khi tăng parallelism.
- **DEADLINE_EXCEEDED:** server có thể đã hoàn tất write; kiểm tra trạng thái trước retry side effect không idempotent.

## 10. Thiết kế throughput, độ trễ và row hotspot

### 10.1. Tránh hotspot và scan đắt

Bigtable sắp rows theo key byte, nên phân bố key ảnh hưởng tải write/read. Một row key tăng dần hoặc quá nhiều requests cùng một row/family có thể gây hotspot dù instance tổng thể còn CPU.

| Triệu chứng | Giả thuyết | Hành động |
|---|---|---|
| Write p99 tăng, ít keys nóng | Row key hotspot | Hash/salt prefix hoặc phân tách hot entities |
| Scan theo device chậm | Dải key quá rộng | Prefix/range chính xác, limit, server filters |
| Ứng dụng tải nhiều rows rồi lọc | Không tận dụng key order | Thiết kế lại schema truy vấn |
| Bigtable CPU cao nhưng QPS thấp | Rows/cells lớn, filters đắt | Giảm row/cell size, xem metrics |
| Một device có hàng triệu cells | Wide row không được bounded | Split key theo thời gian/partition |
| Quá nhiều client connections | Tạo BigtableDataClient mỗi request | Reuse singleton theo app lifecycle |
| GC rule tưởng đã xóa ngay | GC bất đồng bộ | Read filter/retention procedure |
| Latency tăng ở multi-cluster routing | Replication/network/routing | Kiểm tra app profile và client zone |

### 10.2. Công thức capacity chỉ mang tính minh họa

Giả sử hệ thống có **20.000 thiết bị**, mỗi phút gửi 1 event, mỗi event là một row:

\[
\text{Writes trung bình}
= \frac{20.000}{60} \approx 333\ \text{rows/giây}.
\]

Nếu mỗi row chứa hai values và metadata, số mutations/cells cao hơn số row writes; throughput và chi phí thực phải đo theo payload/row size, không chỉ đếm row keys. Khi burst gấp 5 lần, peak lên khoảng **1.667 rows/s**; cần test độ trễ p95/p99 và load distribution trước khi quyết định node capacity.

Không suy từ phép tính này rằng một số lượng nodes cố định “đủ”. Hiệu suất phụ thuộc schema, kích thước dữ liệu, đọc/ghi, replication, storage và kiểu compute/auto-scaling của Bigtable.

### 10.3. Client tuning

- Khởi tạo **BigtableDataClient một lần** và tái sử dụng, tránh gRPC channels liên tục.
- Chọn **sync** cho thao tác đơn giản, **async/batcher** khi cần throughput cao và có backpressure.
- Set **timeouts** và retry budgets theo SLA; tránh retries không giới hạn khi quota thiếu.
- Streaming scans giới hạn row count/range để không dùng quá RAM.
- Theo dõi client-side metrics như latency/retry/transport khi dùng library đã hỗ trợ; phối hợp với Cloud Monitoring server-side.
- Giữ version client và gRPC dependencies được hỗ trợ; test ở staging trước khi tăng số connections/channels.

## 11. Bảo mật, giám sát và chi phí

### 11.1. Phân quyền đúng nhiệm vụ

- Chỉ cấp **Bigtable Reader/User** cho runtime cần data; quyền **Table Admin** dành cho provisioning/migrations đã phê duyệt.
- Local dùng Application Default Credentials của danh tính được cấp quyền; Cloud Run/GKE dùng runtime service account hoặc Workload Identity phù hợp.
- Không nhúng JSON service account key vào container image, source code hoặc logs.
- Nếu dùng **Authorized Views**, kiểm tra phạm vi table/family/qualifier và quyền được cấp, không suy view = quyền đọc toàn bộ table.
- Mã hóa, network controls, row-key metadata và retention cần phù hợp dữ liệu thiết bị/người dùng; không log raw sensitive cell values.

### 11.2. Dashboard vận hành

| Lớp | Metric/tín hiệu | Câu hỏi |
|---|---|---|
| Cluster | CPU utilization, node count, storage | Đủ capacity và phân bố tải không? |
| Data API | read/write ops, error rate, p95/p99 | Đạt SLO không? |
| Key Visualizer | hot rows và hot key ranges | Schema có hotspot không? |
| Replication | routing, lag/failover | Độ nhất quán theo app profile có đạt? |
| Java client | retries, deadlines, gRPC latency | Có bottleneck connection/network? |
| Application | rows đọc/ghi thành công, duplicate/invalid data | Nghiệp vụ có đúng? |
| Billing | compute capacity, storage, backups, egress | Cost trên 1 triệu rows/ops là bao nhiêu? |

**Emulator không mô phỏng phân tán/replication/quota/latency của Bigtable thật.** Chỉ dùng để test API và logic. Load tests phải được chạy trên instance lab được cấp quyền với số liệu và ngân sách cụ thể.

### 11.3. Những khoản có thể phát sinh phí

| Khoản | Phụ thuộc vào |
|---|---|
| Bigtable compute | Nodes/processing capacity và lựa chọn cluster/edition |
| Data storage | Dung lượng cells, versions, GC policy |
| Multi-cluster replication | Clusters/regions/replica storage và network |
| Backup | Retention và dữ liệu sao lưu |
| Network transfer | Luồng cross-zone/region theo SKUs hiện hành |
| Logging/Monitoring | Ingestion/sampling/retention |
| Migration pipeline | Dataflow, Cloud Storage, chuyển dữ liệu, compute |

Không thấy request không có nghĩa cluster không bị tính phí: Bigtable là dịch vụ database có compute/storage đã provision. Đối chiếu **Cloud Billing by SKU** và nhu cầu HA trước khi giảm capacity, retention hoặc replicas.

## 12. Troubleshooting native Java và HBase adapter

| Triệu chứng | Nguyên nhân khả dĩ | Cách điều tra |
|---|---|---|
| PERMISSION_DENIED | ADC/runtime SA thiếu IAM | Đúng principal, Bigtable roles |
| NOT_FOUND | Sai project, instance, table/family | Resource IDs, Table Admin |
| Column family not found | Demo thiếu family reading | Table schema/GC |
| UNAVAILABLE | Transport/service transient | Backoff, server metrics |
| RESOURCE_EXHAUSTED | Quota, hotspot, capacity | Bigtable CPU, Key Visualizer |
| DEADLINE_EXCEEDED | Scan rộng, downstream chậm | Query/range, p95/p99, retry |
| HBase UnsupportedOperationException | HBase Admin/filter API không hỗ trợ | HBase differences matrix |
| HBase scan khác kết quả cũ | Filter/GC/timestamp semantics | Golden tests trên cùng dữ liệu |
| Giá trị cell đọc ra sai | UTF-8 vs binary encoding | Bytes.toString/toLong/toDouble |
| Maven NoSuchMethodError | Xung đột HBase/Guava/protobuf | dependency tree, shaded variant |
| App chậm khi scale | Tạo client mới mỗi request | Reuse long-lived client |
| Local emulator OK, cloud fail | Emulator không kiểm tra IAM/network/scale | Cloud instance lab test |
| Đọc cluster khác chưa có write | Multi-cluster eventual consistency | App profile, replication lag |
| Chi phí cao khi idle | Compute/replication/storage vẫn chạy | Cloud Billing by SKU |

### 12.1. Runbook điều tra theo thứ tự

1. Xác minh **BIGTABLE_EMULATOR_HOST** không khiến Java trỏ nhầm localhost.
2. Kiểm tra **PROJECT_ID, INSTANCE_ID, TABLE_ID**, app profile và đúng family names.
3. Kiểm tra principal ADC/runtime SA, quyền data và admin ở đúng bước.
4. Đọc logs/errors từ Java; phân biệt **row null bình thường** với **NOT_FOUND table**.
5. Với latency, đo client retries, server p95/p99 và key hotspot, không tăng threads mù quáng.
6. Với migration diff, đối chiếu raw row keys, qualifiers, values, timestamps, filters và GC.
7. Rollback client version/config/traffic nếu test không đạt; không xóa dữ liệu HBase/Bigtable làm cách sửa lỗi.

Không ghi credentials/raw cell contents vào ticket. Nếu cần correlation ID, tạo request/job ID không chứa thông tin cá nhân.

## 13. Case study: di chuyển telemetry Java từ HBase

Một nhà máy có **50.000 cảm biến** và app Java/HBase dùng **Get/Put/Scan**, TTL cùng một coprocessor để tổng hợp cảnh báo.

**Thiết kế chuyển đổi:**

1. **Kiểm kê API:** chọn HBase 2.x adapter cho đường Get/Put/Scan; coprocessor phải thay bằng ứng dụng khác như Dataflow/Cloud Run theo đúng workload.
2. **Thiết kế row key:** hash#device#timestamp giúp tránh dồn writes ở timestamp tăng dần.
3. **Dữ liệu:** backfill lịch sử và sync delta; so row count, checksums, timestamps và golden queries.
4. **Client:** thử emulator để kiểm tra chức năng; dùng instance Bigtable lab để benchmark latency/cost.
5. **Cutover:** canary 1% rồi tăng dần; quan sát error rate, stale reads, hot rows và chi phí.
6. **Rollback:** giữ nguồn HBase đến khi xong đối soát, có chiến lược xử lý dữ liệu được ghi trong lúc dual-write.

**Sự cố giả định:** nhóm copy row key **20261119T101000Z#sensor-42** trực tiếp từ HBase sang Bigtable. Ghi đồng thời từ mọi sensor dồn vào vùng khóa mới nhất và p99 tăng dù cluster tổng thể chưa đầy. Đội phải thiết kế row key theo workload, chạy load test và có thể đổi sang **hash#device#time**, đồng thời bổ sung cách index riêng nếu cần truy vấn mọi devices theo giờ.

**Tiêu chí nghiệm thu:** dữ liệu chính xác theo bytes và timestamps, không còn unsupported HBase API trong luồng chính, p95/p99 đạt SLO, không mất/nhân đôi side effects trong migration, IAM/backup/rollback được kiểm chứng, chi phí Bigtable và pipeline trong ngân sách.

## 14. Bài tập và đáp án định hướng

### 14.1. Bài A — Native client trên emulator

1. Khởi động emulator, tạo Maven project và chạy **BigtableNativeLab**.
2. Ghi thêm key **07#sensor-42#20261119T102000Z** với temperature=24.0.
3. Đọc theo prefix sensor-42, ghi lại row keys, qualifiers, values và timestamps.
4. Đọc row không tồn tại, xác nhận **null**.
5. Dừng/restart emulator và xác nhận dữ liệu không được giữ lại.

**Đạt khi:** thao tác ghi/đọc thành công, biết tại sao emulator không chứng minh IAM/production performance.

### 14.2. Bài B — HBase Get/Put/Scan

Chạy **BigtableHBaseLab** với table đã tạo. So sánh **Put ↔ RowMutation**, **Get ↔ readRow**, **Scan ↔ Query.prefix**, và cách HBase chuyển byte[] sang String. Nêu ba HBase APIs mà Bigtable không hỗ trợ.

**Đáp án:** Bigtable adapter gọi cùng Bigtable backend, nhưng không khởi động HBase RegionServer; coprocessors, nhiều region-management Admin calls, namespaces không được hỗ trợ tương đương.

### 14.3. Bài C — Chọn row key

Chọn giữa **timestamp#device**, **device#timestamp** và **hash(device)#device#timestamp** khi có 10.000 events/s từ nhiều devices.

**Đáp án:** timestamp đầu có nguy cơ hotspot; device đầu có thể hợp lý nếu devices đa dạng nhưng hot device vẫn là vấn đề; hash prefix ổn định tăng phân tán nhưng truy vấn xuyên devices phải fan-out. Quyết định sau benchmark.

### 14.4. Bài D — Timestamps

HBase timestamp **1.700.000.000.000 ms** tương ứng bao nhiêu microseconds?

\[
1.700.000.000.000 \times 1000
= 1.700.000.000.000.000\ \mu s.
\]

Vì sao reverse timestamp cực lớn không thể copy nguyên qua adapter? **Đáp án:** chuyển đổi ms → µs bị giới hạn phạm vi, có thể clamp/làm sai ordering với giá trị lớn; cần golden tests và boundary cases.

### 14.5. Bài E — Compatibility review

App HBase dùng **custom coprocessor, PageFilter, namespace, snapshot và Scan#setCaching**. Có thể chỉ thay Maven artifact không?

**Đáp án:** không. Coprocessor không hỗ trợ; một số filters có giới hạn, namespace/snapshot/region Admin không tương đương; setCaching có thể bị bỏ qua. Phải audit/refactor/test trước khi cutover.

### 14.6. Bài F — Retry một bulk operation

Một bulk mutation gồm 100 rows; 99 rows thành công, một row thất bại. Client có thể retry toàn batch mà không xét trạng thái từng row không?

**Đáp án:** batch không atomic giữa rows. Retry phải dựa vào partial results và idempotency policy; **increments/appends** không được retry mù vì có thể thực hiện trùng.

## 15. Dọn lab an toàn

**Emulator:** dừng bằng Ctrl+C, hủy biến môi trường để tránh kết nối nhầm:

~~~bash
unset BIGTABLE_EMULATOR_HOST
unset PROJECT_ID INSTANCE_ID TABLE_ID
~~~

Emulator không lưu dữ liệu sau khi dừng; không cần tạo/xóa Bigtable cloud resources để hoàn thành các bài tập A–F.

Nếu thực hành trên Bigtable instance thật, trước khi xóa table hoặc instance:
- Xác minh đúng project, instance, table, owner và có người dùng khác hay không.
- Kiểm tra backups, replication/app profiles, retention và chính sách bảo mật.
- Không chạy lệnh xóa hàng loạt hoặc xóa instance chỉ vì test đã xong.
- Chỉ owner thực hiện cleanup theo change approval; IAM bindings, logs và backup có vòng đời riêng.

**Không xóa một Bigtable instance production để tiết kiệm chi phí** và không xóa table/source HBase khi chưa đối soát migration.

## 16. Tài liệu tham khảo và checklist

- [Bigtable overview](https://docs.cloud.google.com/bigtable/docs/overview)
- [Bigtable data model và schema design](https://docs.cloud.google.com/bigtable/docs/schema-design)
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
- [Bigtable app profiles và routing](https://docs.cloud.google.com/bigtable/docs/routing)
- [Bigtable IAM roles](https://docs.cloud.google.com/bigtable/docs/access-control)
- [Bigtable Key Visualizer](https://docs.cloud.google.com/bigtable/docs/keyvis-overview)
- [Bigtable pricing](https://cloud.google.com/bigtable/pricing)

**Checklist:** xác định query patterns → chọn row key/family/GC → native client cho app mới hoặc HBase adapter khi migration → emulator CRUD/scan tests → kiểm tra IAM trên cloud lab → compatibility matrix/filter/timestamp tests → bulk/retry/idempotency → benchmark p95/p99/hotspot → replication/backup/cost → cutover/rollback có bằng chứng.

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** Bigtable phù hợp các workload truy cập theo row key ở quy mô lớn; Cloud Run/GKE/Compute Engine có thể dùng Java client để truy cập, nhưng vẫn cần **IAM, mạng, quan sát độ tin cậy và kiểm soát chi phí**. Chọn **native client** khi không cần HBase abstraction; khi migration, adapter giúp giữ interface nhưng **không xóa được khác biệt semantics** giữa Bigtable và Apache HBase.





