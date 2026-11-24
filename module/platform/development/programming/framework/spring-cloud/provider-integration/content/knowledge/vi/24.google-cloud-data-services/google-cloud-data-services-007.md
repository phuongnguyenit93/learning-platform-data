# Tích hợp BigQuery bằng client, template và tải dữ liệu theo lô

## Mục tiêu học tập

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, Spring Boot tích hợp các dịch vụ managed của AWS, Azure và Google Cloud thông qua thư viện Spring Cloud tương ứng. Trên Google Cloud, **BigQuery** là data warehouse phục vụ phân tích dữ liệu lớn, truy vấn SQL, báo cáo và xử lý dữ liệu theo lô.

Bài học tập trung vào cách tích hợp BigQuery trong ứng dụng Spring Boot:

1. Cấu hình Spring Framework on Google Cloud BigQuery starter và Application Default Credentials.
2. Sử dụng BigQuery Java client để chạy GoogleSQL, truyền tham số và đọc kết quả.
3. Hiểu dataset, table, schema, location, partition và clustering ở mức cần thiết cho ứng dụng.
4. Dùng BigQueryTemplate và BigQueryOperations để nạp dữ liệu từ InputStream.
5. Phân biệt load job với BigQuery Storage Write API.
6. Tải CSV, newline-delimited JSON, Avro, ORC và Parquet từ Cloud Storage theo lô.
7. Chọn write disposition, schema và job ID để triển khai retry an toàn.
8. Cấu hình IAM tối thiểu, theo dõi chi phí, quota và trạng thái job.
9. Kiểm thử bằng mock và sandbox dataset trong môi trường CI.

> **Phạm vi:** Ví dụ tham chiếu Spring Framework on Google Cloud 8.2.1 và BigQuery Java client do BOM quản lý. Nhánh Spring Framework on Google Cloud 8.x tương thích Spring Boot 4.0/4.1. Nếu dự án dùng Spring Boot 3.5 hoặc 3.4, hãy chọn nhánh BOM tương ứng thay vì chép nguyên version 8.x.

## 1. BigQuery trong kiến trúc Spring Boot

### 1.1. BigQuery dùng cho workload nào?

BigQuery là kho dữ liệu phân tích dạng columnar, được quản lý hoàn toàn. Ứng dụng thường dùng BigQuery để:

- Tổng hợp đơn hàng, doanh thu, lượt truy cập hoặc hành vi sử dụng.
- Chạy báo cáo định kỳ và dashboard.
- Phân tích lịch sử sự kiện từ Pub/Sub, Cloud Storage hoặc hệ thống giao dịch.
- Lưu dữ liệu đã chuẩn hóa để phục vụ BI, machine learning hoặc data science.
- Chạy ELT/ETL và truy vấn dữ liệu từ nhiều nguồn.

BigQuery không thay thế mặc định cho cơ sở dữ liệu giao dịch của ứng dụng. Các thao tác CRUD nhỏ, cập nhật trạng thái đơn hàng theo từng request hoặc transaction nghiệp vụ thường phù hợp với Cloud SQL, Spanner hoặc database giao dịch khác. BigQuery phù hợp khi ứng dụng cần đọc/ghi dữ liệu phân tích theo tập lớn.

### 1.2. Các thành phần cơ bản

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Project | Ranh giới tài nguyên, IAM và billing | rental-analytics |
| Dataset | Nhóm bảng cùng location và chính sách | sales_reporting |
| Table | Lưu dữ liệu theo schema | orders_daily |
| Schema | Định nghĩa tên, kiểu và mode của field | order_id STRING, amount NUMERIC |
| Query job | Thực thi GoogleSQL và lưu metadata kết quả | Tổng hợp doanh thu |
| Load job | Nạp file vào table từ Cloud Storage hoặc nguồn hỗ trợ | CSV cuối ngày |
| Storage Write API | Ghi record qua stream gRPC | Sự kiện đến liên tục |

Dataset có location. Các job truy vấn hoặc load phải tương thích với location của dữ liệu liên quan. Với luồng nạp từ Cloud Storage, hãy chọn bucket và dataset theo yêu cầu location của BigQuery để tránh lỗi tương thích hoặc phí truyền dữ liệu liên vùng.

### 1.3. Kiến trúc tích hợp

~~~mermaid
flowchart TD
    APP["Spring Boot application"] --> STARTER["spring-cloud-gcp-starter-bigquery"]
    STARTER --> CLIENT["BigQuery Java client"]
    STARTER --> TEMPLATE["BigQueryTemplate"]
    CLIENT --> QUERY["Query jobs / table metadata"]
    CLIENT --> LOAD["Load jobs"]
    TEMPLATE --> CSV["CSV / InputStream load"]
    TEMPLATE --> JSON["NDJSON / Storage Write API"]
    GCS["Cloud Storage files"] --> LOAD
    QUERY --> BQ["BigQuery dataset and tables"]
    LOAD --> BQ
    CSV --> BQ
    JSON --> BQ
    ADC["ADC + runtime service account"] --> CLIENT
~~~

Có ba đường truy cập chính:

- **BigQuery client:** kiểm soát query job, table, dataset, schema, load job và metadata.
- **BigQueryTemplate:** wrapper theo dataset, thuận tiện cho việc nạp InputStream và JSON stream.
- **Spring Integration handler:** đưa file vào BigQuery từ message pipeline khi ứng dụng đã sử dụng Spring Integration.

Không có Spring Data repository kiểu JPA cho BigQuery. Ứng dụng thường dùng client hoặc template để thực hiện query và ingestion.

## 2. Dependency và cấu hình Spring Boot

### 2.1. Import BOM

Với Maven, import Spring Framework on Google Cloud BOM ở dependencyManagement:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>${spring-cloud-gcp.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Chọn giá trị spring-cloud-gcp.version theo compatibility matrix của Spring Boot. BOM quản lý các phiên bản client và module Spring Cloud GCP tương thích với nhau; không khai báo version riêng cho từng starter nếu không có lý do đặc biệt.

### 2.2. BigQuery starter

Thêm dependency:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-bigquery</artifactId>
</dependency>
~~~

Starter cung cấp auto-configuration cho BigQuery client và các credentials cần thiết. Khi starter có mặt, ứng dụng có thể inject bean BigQuery và BigQueryTemplate.

Nếu chỉ cần Java client, starter vẫn có thể là cách đơn giản để nhận client đã được cấu hình project ID và credentials. Không cần tự tạo BigQueryOptions trong mọi service.

### 2.3. Cấu hình application.yml

Ví dụ:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: rental-analytics
      bigquery:
        enabled: true
        project-id: rental-analytics
        dataset-name: sales_reporting
        json-writer-batch-size: 1000
        thread-pool-size: 4
~~~

Các property quan trọng:

| Property | Ý nghĩa |
| --- | --- |
| spring.cloud.gcp.bigquery.dataset-name | Dataset mà BigQueryTemplate và BigQueryFileMessageHandler sử dụng; cần có khi dùng template/handler |
| spring.cloud.gcp.bigquery.enabled | Bật/tắt BigQuery auto-configuration; mặc định true |
| spring.cloud.gcp.bigquery.project-id | Project dành cho BigQuery nếu khác project ID ở GCP core |
| spring.cloud.gcp.bigquery.credentials.location | File credentials riêng nếu khác ADC mặc định |
| spring.cloud.gcp.bigquery.json-writer-batch-size | Batch size của BigQueryJsonDataWriter; mặc định 1000 |
| spring.cloud.gcp.bigquery.thread-pool-size | ThreadPoolTaskScheduler dùng bởi BigQueryTemplate; mặc định 4 |

Tên property trong reference có thể viết camelCase như datasetName; Spring Boot relaxed binding cho phép dùng dạng kebab-case dataset-name trong YAML.

Không đặt service account private key vào Git, Docker image hoặc application.yml. Ưu tiên Application Default Credentials và service account gắn với workload. Chỉ dùng credentials riêng khi có yêu cầu cụ thể và lưu chúng trong cơ chế quản lý secret được kiểm soát.

### 2.4. Local development và production identity

Local developer có thể thiết lập ADC bằng Google Cloud CLI và đăng nhập tài khoản có quyền phù hợp. Trên Cloud Run, GKE hoặc Compute Engine, gắn service account/workload identity cho runtime.

Cùng một code path có thể chạy ở local và production vì starter lấy credentials từ CredentialsProvider. Không nên để code tự đọc file key từ đường dẫn cố định hoặc nhúng thông tin xác thực vào constructor.

## 3. BigQuery client: chạy truy vấn GoogleSQL

### 3.1. Inject BigQuery bean

GcpBigQueryAutoConfiguration tạo bean BigQuery dựa trên project ID và credentials được suy ra từ môi trường.

~~~java
import com.google.cloud.bigquery.BigQuery;
import org.springframework.stereotype.Service;

@Service
public class AnalyticsQueryService {

    private final BigQuery bigQuery;

    public AnalyticsQueryService(BigQuery bigQuery) {
        this.bigQuery = bigQuery;
    }
}
~~~

Client là object dùng chung cho các thao tác BigQuery. Không tạo một client mới cho mỗi query request; hãy để Spring quản lý bean và lifecycle.

### 3.2. Query với named parameters

Ví dụ truy vấn các đơn hàng của một khách hàng:

~~~java
import com.google.cloud.bigquery.BigQuery;
import com.google.cloud.bigquery.FieldValueList;
import com.google.cloud.bigquery.JobId;
import com.google.cloud.bigquery.QueryJobConfiguration;
import com.google.cloud.bigquery.QueryParameterValue;
import com.google.cloud.bigquery.TableResult;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public List<OrderMetric> findOrders(
        BigQuery bigQuery, String location,
        String customerId, long minimumAmount)
        throws InterruptedException {

    String sql = """
        SELECT order_id, status, total_amount
        FROM `rental-analytics.sales_reporting.orders`
        WHERE customer_id = @customerId
          AND total_amount >= @minimumAmount
        ORDER BY created_at DESC
        LIMIT 100
        """;

    QueryJobConfiguration queryConfig =
            QueryJobConfiguration.newBuilder(sql)
                    .addNamedParameter(
                            "customerId",
                            QueryParameterValue.string(customerId))
                    .addNamedParameter(
                            "minimumAmount",
                            QueryParameterValue.int64(minimumAmount))
                    .setUseLegacySql(false)
                    .setMaximumBytesBilled(2_000_000_000L)
                    .build();

    JobId queryJobId = JobId.newBuilder()
            .setJob("orders_query_" + UUID.randomUUID())
            .setLocation(location)
            .build();
    TableResult rows = bigQuery.query(queryConfig, queryJobId);

    List<OrderMetric> result = new ArrayList<>();
    for (FieldValueList row : rows.iterateAll()) {
        result.add(new OrderMetric(
                row.get("order_id").getStringValue(),
                row.get("status").getStringValue(),
                row.get("total_amount").getLongValue()));
    }

    return result;
}
~~~

QueryParameterValue có factory theo kiểu dữ liệu như string, int64, numeric, timestamp, bool và array/struct tương ứng. Chọn đúng kiểu BigQuery của field.

Named parameter được tham chiếu bằng @parameterName. Có thể dùng positional parameter ?, nhưng một query không được trộn named và positional parameters.

### 3.3. Vì sao cần bind parameter?

Không nối input người dùng trực tiếp vào SQL:

~~~java
// Không an toàn: input có thể thay đổi cấu trúc câu SQL.
String sql = "SELECT * FROM orders WHERE customer_id = '" + customerId + "'";
~~~

Hãy dùng parameter:

~~~sql
SELECT order_id, status
FROM `rental-analytics.sales_reporting.orders`
WHERE customer_id = @customerId;
~~~

Parameter bảo vệ giá trị đầu vào khỏi trở thành một phần cú pháp SQL và giúp BigQuery không ghi giá trị parameter nhạy cảm vào query log. Parameter chỉ thay thế **giá trị**, không thay thế tên project, dataset, table hoặc column. Nếu tên table được chọn động, hãy kiểm tra với allowlist hoặc mapping nội bộ.

### 3.4. Đọc kết quả và phân trang

TableResult có thể lặp qua iterateAll() để đọc toàn bộ kết quả. Với kết quả lớn, cần tránh materialize toàn bộ rows vào một List nếu không cần.

Các cách xử lý:

- Chọn đúng cột thay vì SELECT *.
- Dùng LIMIT nếu giao diện chỉ cần một trang.
- Dùng pageSize hoặc paging API khi đọc kết quả theo từng trang.
- Đưa tổng hợp vào SQL thay vì kéo hàng triệu row về JVM để tính.
- Nếu cần tải kết quả lớn cho pipeline xử lý, đánh giá BigQuery Storage Read API hoặc export job.

Không giữ TableResult rồi chuyển toàn bộ dữ liệu lớn thành object graph trong heap. Hãy đặt giới hạn kết quả và thiết kế query theo nhu cầu của API.

### 3.5. Dataset location và query job

Job phải chạy ở location tương thích với dataset được truy vấn. Với dataset ở location đơn vùng hoặc ngoài multi-region US/EU, BigQuery Java client yêu cầu chỉ định location trong JobId khi gọi overload query(QueryJobConfiguration, JobId, ...).

Khi thiết kế service, lưu location cùng metadata dataset hoặc cấu hình môi trường. Không giả định job luôn chạy ở US. Nếu query đọc nhiều dataset, các dataset phải đáp ứng quy tắc location compatibility của BigQuery.

### 3.6. Kiểm soát bytes và chi phí query

Trước khi chạy query production:

- Dùng setMaximumBytesBilled làm giới hạn bảo vệ theo use case.
- Dùng dry-run query job để ước lượng bytes xử lý trước khi chạy.
- Lọc partition column để tránh quét partition không cần thiết.
- Chỉ chọn các field cần dùng.
- Dùng partitioning và clustering theo query pattern.
- Theo dõi bytes processed, bytes billed, slot milliseconds và job status.

Dry run là một query job cấu hình setDryRun(true); nó không trả dữ liệu. Dùng bigQuery.create(JobInfo.of(dryRunConfig)) để gửi dry-run job và xem statistics. Không dùng BigQuery.query(...) để lấy kết quả từ dry run.

## 4. Schema và ánh xạ dữ liệu Java

### 4.1. BigQuery schema là contract dữ liệu

BigQuery table có schema gồm tên field, kiểu dữ liệu và mode (NULLABLE, REQUIRED, REPEATED). Một schema rõ ràng giúp kiểm soát data contract khi nạp file hoặc đọc kết quả.

Các kiểu thường gặp:

| Kiểu BigQuery | Kiểu Java gợi ý | Lưu ý |
| --- | --- | --- |
| STRING | String | UTF-8 text |
| INT64 | Long | Số nguyên 64 bit |
| NUMERIC | BigDecimal | Phù hợp số thập phân chính xác |
| FLOAT64 | Double | Số thực dấu phẩy động |
| BOOL | Boolean | Boolean |
| DATE | LocalDate hoặc string ISO | Ngày không có timezone |
| DATETIME | LocalDateTime | Ngày giờ không có timezone |
| TIMESTAMP | Instant hoặc Timestamp | Thời điểm tuyệt đối |
| BYTES | byte[] | Dữ liệu nhị phân |
| ARRAY<T> | List<T> | Field mode REPEATED |
| STRUCT | POJO/Map hoặc nested field mapping | Record lồng nhau |

Khi đọc FieldValue, chọn accessor theo kiểu field. Ví dụ getStringValue(), getLongValue(), getNumericValue() hoặc getBooleanValue(). Không ép tất cả giá trị thành String rồi parse lại nếu client đã cung cấp accessor đúng kiểu.

### 4.2. Tạo schema trong Java

~~~java
import com.google.cloud.bigquery.Field;
import com.google.cloud.bigquery.Schema;
import com.google.cloud.bigquery.StandardSQLTypeName;

Schema orderSchema = Schema.of(
        Field.of("order_id", StandardSQLTypeName.STRING),
        Field.of("customer_id", StandardSQLTypeName.STRING),
        Field.of("status", StandardSQLTypeName.STRING),
        Field.of("total_amount", StandardSQLTypeName.INT64),
        Field.of("created_at", StandardSQLTypeName.TIMESTAMP));
~~~

Schema trên có thể dùng khi tạo table hoặc truyền vào load API. Với field bắt buộc, nested record, repeated field hoặc precision đặc biệt, dùng builder của Field để khai báo mode và subfields rõ ràng.

### 4.3. Không có Spring Data repository cho BigQuery

BigQuery không được tích hợp như JPA repository hoặc Spring Data document repository. Ứng dụng dùng:

- BigQuery để chạy query, tạo dataset/table và load job.
- BigQueryTemplate cho các thao tác nạp dữ liệu tiện dụng.
- BigQueryOperations nếu muốn service phụ thuộc abstraction của template.
- DTO/record Java để ánh xạ kết quả query.

Đừng thiết kế BigQuery như một OLTP repository với save(entity) cho từng thao tác CRUD. Hãy nghĩ theo query job, load job, batch ingestion và analytics result.

## 5. BigQueryTemplate và BigQueryOperations

### 5.1. Vai trò của template

BigQueryTemplate là wrapper trên BigQuery client, đơn giản hóa thao tác nạp dữ liệu. Instance auto-configured được scope vào một dataset duy nhất, lấy từ spring.cloud.gcp.bigquery.dataset-name.

Vì vậy, khi gọi:

~~~java
bigQueryTemplate.writeDataToTable(
        "orders_stage",
        inputStream,
        FormatOptions.csv());
~~~

orders_stage là table name trong dataset đã cấu hình. Nếu cần ghi sang dataset khác, hãy dùng một template/client được cấu hình rõ ràng cho dataset đó hoặc dùng BigQuery client trực tiếp với TableId.

### 5.2. Nạp CSV từ InputStream

~~~java
import com.google.cloud.bigquery.FormatOptions;
import com.google.cloud.bigquery.Job;
import com.google.cloud.spring.bigquery.core.BigQueryTemplate;
import org.springframework.stereotype.Service;

import java.io.InputStream;
import java.util.concurrent.CompletableFuture;

@Service
public class BigQueryTemplateImportService {

    private final BigQueryTemplate bigQueryTemplate;

    public BigQueryTemplateImportService(
            BigQueryTemplate bigQueryTemplate) {
        this.bigQueryTemplate = bigQueryTemplate;
    }

    public CompletableFuture<Job> loadCsv(
            String tableName, InputStream csvInputStream) {

        return bigQueryTemplate.writeDataToTable(
                tableName,
                csvInputStream,
                FormatOptions.csv());
    }
}
~~~

writeDataToTable trả về CompletableFuture<Job>. Future hoàn tất khi load job đã hoàn thành. Nếu gọi trong batch worker đồng bộ, có thể chờ future rồi kiểm tra status. Nếu xử lý bất đồng bộ, hãy giữ InputStream mở cho đến khi future hoàn tất.

### 5.3. Nạp CSV với schema rõ ràng

Khi table chưa tồn tại hoặc cần kiểm soát schema, truyền thêm Schema:

~~~java
CompletableFuture<Job> future =
        bigQueryTemplate.writeDataToTable(
                "orders_stage",
                csvInputStream,
                FormatOptions.csv(),
                orderSchema);

Job job = future.get();
if (job.getStatus() != null && job.getStatus().getError() != null) {
    throw new IllegalStateException(
            "BigQuery load failed: " + job.getStatus().getError());
}
~~~

Đây là overload thuận tiện khi ứng dụng đã có schema Java. Với CSV có header, cần đảm bảo cấu hình parser bỏ qua header. Nếu cần skipLeadingRows, delimiter, quote hoặc null marker, dùng CsvOptions trong load job client API.

### 5.4. Nạp newline-delimited JSON qua Storage Write API

BigQueryTemplate.writeJsonStream dùng BigQuery Storage Write API để ghi newline-delimited JSON (NDJSON). Mỗi dòng là một JSON object độc lập:

~~~json
{"order_id":"ord-1001","customer_id":"cus-42","status":"PAID","total_amount":250000}
{"order_id":"ord-1002","customer_id":"cus-77","status":"PENDING","total_amount":180000}
~~~

Ví dụ:

~~~java
var future = bigQueryTemplate.writeJsonStream(
        "orders_events",
        jsonInputStream);

var response = future.get();

if (!response.isSuccessful()) {
    throw new IllegalStateException(
            "Storage Write API errors: " + response.getErrors());
}
~~~

Nếu table chưa tồn tại, có thể dùng overload truyền schema:

~~~java
var future = bigQueryTemplate.writeJsonStream(
        "orders_events",
        jsonInputStream,
        orderSchema);

var response = future.get();
if (!response.isSuccessful()) {
    throw new IllegalStateException(
            "Storage Write API errors: " + response.getErrors());
}
~~~

Khi không truyền schema, table phải tồn tại vì Storage Write API không tự tạo table trong overload này. Khi truyền schema, template có thể tạo table theo schema đó.

WriteApiResponse khác Job: đây là kết quả ghi qua Storage Write API. Hãy kiểm tra isSuccessful() và errors; không kiểm tra response như một load job.

### 5.5. Batch size và scheduler của template

Hai cấu hình ảnh hưởng đến template:

- json-writer-batch-size: số record trong một batch ghi JSON; mặc định 1000.
- thread-pool-size: kích thước ThreadPoolTaskScheduler dùng để polling job; mặc định 4.

Batch size quá nhỏ làm tăng overhead; quá lớn có thể tăng memory usage hoặc latency. Hãy benchmark theo kích thước record, throughput và giới hạn workload thay vì tăng giá trị tùy ý.

### 5.6. Write disposition của BigQueryTemplate

Template hỗ trợ cấu hình:
- WRITE_APPEND: nối dữ liệu vào table.
- WRITE_TRUNCATE: ghi đè dữ liệu hiện có.
- WRITE_EMPTY: chỉ ghi nếu table chưa có dữ liệu.

Mặc định BigQueryTemplate dùng append. Template có setWriteDisposition(...) và setCreateDisposition(...); đây là cấu hình của instance template. Nếu mỗi request cần disposition khác nhau, đừng thay đổi trạng thái bean singleton theo request đồng thời. Dùng BigQuery client với LoadJobConfiguration riêng cho từng job để kiểm soát disposition tường minh.

## 6. Load job: tải dữ liệu theo lô từ Cloud Storage

### 6.1. Khi nào nên dùng load job?

Load job phù hợp khi dữ liệu đã được chuẩn bị thành file và latency không cần tính bằng giây:

- Nạp file CSV cuối ngày.
- Nạp Parquet/Avro đã được ETL chuẩn hóa.
- Nạp hàng trăm file theo prefix trong Cloud Storage.
- Thay thế snapshot table định kỳ.
- Backfill lịch sử hoặc nhập dữ liệu từ hệ thống khác.

BigQuery hỗ trợ batch load từ Cloud Storage với các định dạng CSV, newline-delimited JSON, Avro, ORC và Parquet. Có thể load từ local file qua client library, nhưng với file lớn, nên đưa file lên Cloud Storage trước.

### 6.2. Load job có tính atomic

Load job được thực thi như một job. Kết quả load là atomic: khi job thất bại, dữ liệu của job không được công bố một phần; khi job thành công, dữ liệu được nạp theo write disposition đã chọn.

Điều này phù hợp với batch ETL vì downstream query có thể chờ job thành công rồi mới đọc table đích.

Không nhầm load job với việc gửi từng row bằng streaming insert. Load job không tạo một request cho mỗi record; BigQuery xử lý file theo batch.

### 6.3. Tải CSV từ Cloud Storage bằng BigQuery Java client

Ví dụ dưới đây dùng schema tường minh và bỏ qua dòng header:

~~~java
import com.google.cloud.bigquery.BigQuery;
import com.google.cloud.bigquery.CsvOptions;
import com.google.cloud.bigquery.Field;
import com.google.cloud.bigquery.Job;
import com.google.cloud.bigquery.JobId;
import com.google.cloud.bigquery.JobInfo;
import com.google.cloud.bigquery.LoadJobConfiguration;
import com.google.cloud.bigquery.Schema;
import com.google.cloud.bigquery.StandardSQLTypeName;
import com.google.cloud.bigquery.TableId;

public Job loadOrdersCsv(
        BigQuery bigQuery,
        String projectId,
        String datasetId,
        String location,
        String tableName,
        String sourceUri,
        String batchId,
        int attempt) throws InterruptedException {

    Schema schema = Schema.of(
            Field.of("order_id", StandardSQLTypeName.STRING),
            Field.of("customer_id", StandardSQLTypeName.STRING),
            Field.of("status", StandardSQLTypeName.STRING),
            Field.of("total_amount", StandardSQLTypeName.INT64));

    CsvOptions csvOptions =
            CsvOptions.newBuilder()
                    .setSkipLeadingRows(1)
                    .build();

    TableId destination = TableId.of(
            projectId, datasetId, tableName);

    LoadJobConfiguration loadConfig =
            LoadJobConfiguration.newBuilder(
                    destination, sourceUri, csvOptions)
                    .setSchema(schema)
                    .setCreateDisposition(
                            JobInfo.CreateDisposition.CREATE_IF_NEEDED)
                    .setWriteDisposition(
                            JobInfo.WriteDisposition.WRITE_APPEND)
                    .build();

    if (!batchId.matches("[A-Za-z0-9_-]+") || attempt < 1) {
        throw new IllegalArgumentException(
                "batchId must use letters, digits, underscore or dash; attempt must be positive");
    }

    JobId jobId = JobId.newBuilder()
            .setJob("load_orders_" + batchId + "_a" + attempt)
            .setLocation(location)
            .build();

    Job job = bigQuery.create(
            JobInfo.newBuilder(loadConfig)
                    .setJobId(jobId)
                    .build());

    Job completed = job.waitFor();

    if (completed == null) {
        throw new IllegalStateException(
                "BigQuery load job no longer exists");
    }

    if (completed.getStatus().getError() != null) {
        throw new IllegalStateException(
                "BigQuery load failed: "
                        + completed.getStatus().getError());
    }

    return completed;
}
~~~

sourceUri có dạng gs://bucket/path/file.csv. Khi dùng wildcard, BigQuery hỗ trợ một dấu * trong mỗi URI; không dùng wildcard trong bucket name. Hãy kiểm tra các object được chọn đúng với batch cần nạp.

### 6.4. Write disposition

| Disposition | Hành vi | Use case |
| --- | --- | --- |
| WRITE_APPEND | Nối rows vào table | Nạp partition/batch mới |
| WRITE_TRUNCATE | Xóa dữ liệu hiện tại rồi ghi dữ liệu mới | Thay snapshot hoặc staging table |
| WRITE_EMPTY | Chỉ ghi nếu table rỗng | Tạo dữ liệu lần đầu, tránh ghi đè |

Không đặt WRITE_TRUNCATE trên table production nếu mục tiêu chỉ là thêm dữ liệu. Với pipeline snapshot, có thể load vào staging table, kiểm tra dữ liệu rồi mới thay thế hoặc publish table/view.

### 6.5. Create disposition

| Disposition | Hành vi |
| --- | --- |
| CREATE_IF_NEEDED | Tạo table nếu chưa tồn tại |
| CREATE_NEVER | Job thất bại nếu table chưa tồn tại |

Chọn create disposition rõ ràng để tránh tạo table ngoài dự kiến. Với schema contract đã được quản lý qua migration, có thể dùng CREATE_NEVER để pipeline không âm thầm tạo table sai cấu trúc.

### 6.6. Các định dạng file

| Định dạng | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| CSV | Trao đổi đơn giản, file dễ kiểm tra | Cần xử lý delimiter, quote, header và encoding |
| NDJSON | Record JSON độc lập, nested object | Mỗi dòng là một JSON object |
| Avro | Batch data có schema, nested/repeated field | Thường phù hợp ingestion dữ liệu có schema |
| Parquet | Columnar analytics, file nén hiệu quả | Phù hợp pipeline dữ liệu lớn |
| ORC | Columnar format trong hệ sinh thái Hadoop | Kiểm tra schema và codec tương thích |

Với Avro, Parquet và ORC, schema có thể được lấy từ file format trong nhiều trường hợp. Với CSV và JSON, nên cân nhắc schema tường minh nếu cần contract ổn định.

### 6.7. Retry load job an toàn bằng job ID

Khi mạng bị ngắt sau khi client gửi job, ứng dụng có thể không biết job đã được BigQuery nhận hay chưa. Nếu tạo một job ID mới ngay lập tức, cùng batch có thể bị nạp hai lần.

Thiết kế an toàn:

1. Tạo batch ID ổn định và attempt number cho lần chạy cụ thể.
2. Gửi load job với job ID tạo từ batch ID và attempt number.
3. Nếu timeout khiến kết quả tạo job chưa rõ, tra cứu lại cùng job ID và location.
4. Nếu job đang chạy hoặc đã thành công, tiếp tục theo dõi/kết thúc batch thay vì tạo job khác.
5. Nếu job đã thất bại rõ ràng và cần chạy lại, tăng attempt number; không tạo ID mới chỉ vì client bị timeout.

Gửi lại request với cùng job ID giúp tránh tạo nhiều job độc lập cho cùng một attempt. Ví dụ code load phía trên nhận batchId ổn định, attempt và location của dataset. Với job ở location ngoài US/EU, phải chỉ định location khi tạo hoặc tra cứu job; có thể luôn truyền location tường minh để tránh phụ thuộc default.

### 6.8. Location của dataset và Cloud Storage bucket

Dataset BigQuery có location. Bucket Cloud Storage chứa source file phải ở location tương thích với dataset đích. Thiết kế bucket và dataset theo cùng vùng hoặc cặp location được BigQuery hỗ trợ.

Nếu bucket và dataset ở khác location, thao tác có thể không hợp lệ hoặc phát sinh phí truyền dữ liệu. Không chọn location chỉ theo vị trí ứng dụng; hãy cân nhắc data residency, latency, chi phí và các nguồn dữ liệu sẽ kết hợp trong query.

## 7. Storage Write API và streaming ingestion

### 7.1. Khi nào dùng Storage Write API?

Storage Write API dùng kết nối gRPC hai chiều để ghi record vào BigQuery. Nó phù hợp khi:
- Dữ liệu phát sinh liên tục.
- Cần latency thấp hơn batch load job.
- Nhiều worker cùng ghi dữ liệu.
- Cần quản lý stream, offset và commit theo batch.
- Cần schema update detection hoặc CDC upsert theo khả năng API.

Spring BigQueryTemplate.writeJsonStream cung cấp đường ghi NDJSON thuận tiện. Với workload nâng cao, có thể dùng trực tiếp BigQueryWriteClient và quản lý write stream.

### 7.2. So sánh load job và Storage Write API

| Tiêu chí | Load job | Storage Write API |
| --- | --- | --- |
| Nguồn dữ liệu | File hoặc URI trong Cloud Storage | Record gửi qua gRPC stream |
| Độ trễ | Batch; chờ job hoàn tất | Thấp hơn, phù hợp ingestion liên tục |
| Đơn vị xử lý | Job | Write stream và append request |
| Atomicity | Một load job là atomic | Pending streams có thể commit nhiều stream atomically |
| Retry | Dùng job ID ổn định | Dùng stream offset và retry semantics phù hợp |
| Use case | Nightly load, backfill, file import | Event ingestion, near-real-time pipeline |

Storage Write API có các loại stream với semantics khác nhau. Default stream ghi dữ liệu hiển thị nhanh và theo semantics at-least-once. Committed stream hỗ trợ offset để client retry append mà không ghi trùng trong stream đó. Pending stream giữ dữ liệu cho đến khi finalize và batch commit; nhiều pending streams có thể được commit atomically.

Spring Framework on Google Cloud cung cấp BigQueryJsonDataWriter, helper được mô tả cho exactly-once delivery mode. BigQueryTemplate dùng helper này trong đường ghi JSON. Khi tự dùng BigQueryWriteClient, ứng dụng phải tự chọn stream type, lưu offset và retry đúng semantics; không suy ra mọi Storage Write API call đều exactly-once.

Không gọi mọi thao tác Storage Write API là exactly-once. Semantics phụ thuộc stream type, offset và cách client retry. Đối với BigQueryTemplate.writeJsonStream, tham chiếu BigQueryJsonDataWriter của Spring Cloud GCP; với client API trực tiếp, tự thiết kế stream và offset.

### 7.3. Pending stream cho batch atomic

Một batch có nhiều worker có thể thực hiện theo trình tự:

1. Tạo pending write streams.
2. Chia batch thành các phần và giao cho worker.
3. Mỗi worker append rows vào stream riêng.
4. Finalize từng stream sau khi ghi xong.
5. Chờ mọi worker thành công.
6. Gọi BatchCommitWriteStreams để công bố toàn bộ batch.

Dữ liệu pending chưa hiển thị cho query trước khi commit. Nếu worker lỗi, chỉ retry phần stream tương ứng theo checkpoint/offset đã lưu. Sau khi finalize, không append thêm row vào stream đó.

Pending streams có thời hạn finalize/commit và quota buffer; không dùng chúng như một vùng lưu trữ dài hạn. Với tác vụ batch rất lớn, hãy cân nhắc load job từ Cloud Storage vì nó đơn giản hơn nếu dữ liệu đã có sẵn thành file.

### 7.4. Khi nào cần BigQuery Storage Write client trực tiếp?

Dùng BigQueryWriteClient khi cần kiểm soát:
- Tạo stream type.
- Append rows và offsets.
- Finalize stream.
- Batch commit.
- Retry theo checkpoint.
- Parallel writer và backpressure.

Đây là mức API thấp hơn BigQueryTemplate. Chỉ triển khai khi yêu cầu throughput/consistency đòi hỏi kiểm soát stream; với file NDJSON đơn giản, template thường đủ.

## 8. Spring Integration với BigQueryFileMessageHandler

Spring Framework on Google Cloud có BigQueryFileMessageHandler để đưa dữ liệu vào BigQuery trong pipeline Spring Integration.

Handler nhận các payload như:
- java.io.File
- byte[]
- org.springframework.core.io.Resource
- java.io.InputStream

Handler đọc message headers để xác định table và format:

| Header | Ý nghĩa |
| --- | --- |
| BigQuerySpringMessageHeaders.TABLE_NAME | Tên table trong dataset đã cấu hình |
| BigQuerySpringMessageHeaders.FORMAT_OPTIONS | Format của payload, ví dụ CSV hoặc JSON |

Có thể cấu hình trực tiếp table name và format options trên handler thay cho message headers.

Ví dụ cấu hình ServiceActivator:

~~~java
import com.google.cloud.bigquery.FormatOptions;
import com.google.cloud.spring.bigquery.core.BigQueryTemplate;
import com.google.cloud.spring.bigquery.integration.outbound.BigQueryFileMessageHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageHandler;

@Bean
DirectChannel bigQueryWriteDataChannel() {
    return new DirectChannel();
}

@Bean
DirectChannel bigQueryJobReplyChannel() {
    return new DirectChannel();
}

@Bean
@ServiceActivator(inputChannel = "bigQueryWriteDataChannel")
MessageHandler bigQueryFileHandler(BigQueryTemplate template) {
    BigQueryFileMessageHandler handler =
            new BigQueryFileMessageHandler(template);
    handler.setFormatOptions(FormatOptions.csv());
    handler.setOutputChannel(bigQueryJobReplyChannel());
    return handler;
}
~~~

### 8.1. Xử lý reply bất đồng bộ

Mặc định handler chạy async (setSync(false)) và gửi CompletableFuture<Job> lên reply channel. Future hoàn tất khi load job hoàn thành.

Nếu bật setSync(true), handler chặn thread cho đến khi load job kết thúc. Chỉ dùng synchronous mode khi pipeline cho phép chờ; với luồng message có throughput cao, nên giữ async và xử lý reply/failure channel riêng.

### 8.2. Pipeline điển hình

~~~mermaid
flowchart LR
    SOURCE["GCS file / inbound message"] --> INPUT["Spring Integration input channel"]
    INPUT --> HANDLER["BigQueryFileMessageHandler"]
    HANDLER --> JOB["CompletableFuture<Job>"]
    JOB --> SUCCESS["Job completed successfully"]
    JOB --> FAILURE["Load job error / retry queue"]
~~~

Khi xây dựng pipeline, cần correlation ID/batch ID để theo dõi source file đến job ID. Không đánh dấu file đã xử lý chỉ vì message handler đã nhận payload; chỉ cập nhật trạng thái sau khi load job hoàn tất thành công.

## 9. IAM và bảo mật

### 9.1. Quyền chạy query

Để tạo BigQuery job, runtime principal cần bigquery.jobs.create. Role thường dùng:
- roles/bigquery.jobUser ở project chứa job.
- roles/bigquery.dataViewer trên dataset/table nếu chỉ đọc.
- roles/bigquery.dataEditor trên dataset nếu cần tạo/cập nhật table hoặc nạp dữ liệu.

Cấp quyền theo project/dataset phù hợp. Không cấp roles/bigquery.admin cho runtime chỉ vì ứng dụng cần chạy query.

### 9.2. Quyền load từ Cloud Storage

Khi load file từ bucket, runtime principal cũng cần đọc source object. Quyền thường cần gồm storage.objects.get; nếu dùng wildcard URI có thể cần storage.objects.list.

Có thể cấp roles/storage.objectViewer trên đúng bucket thay vì cấp Storage Admin toàn project. BigQuery service và runtime principal phải có quyền phù hợp với cách ứng dụng gọi load job và truy cập source.

### 9.3. ADC và workload identity

- Local: ADC của developer với quyền giới hạn trong project sandbox.
- Cloud Run: service account riêng cho service.
- GKE: Workload Identity Federation for GKE.
- Compute Engine: service account gắn với VM.

Tách runtime principal khỏi deployment/migration principal. Runtime API thường chỉ cần đọc query hoặc ghi vào dataset được chỉ định; thao tác tạo dataset, thay IAM policy hoặc xóa table nên được thực hiện bởi pipeline quản trị riêng.

### 9.4. Bảo vệ dữ liệu

BigQuery hỗ trợ các cơ chế quản trị như dataset/table IAM, row-level access policies, column-level security và policy tags. Ứng dụng nên:
- Chỉ trả các cột mà API caller được phép xem.
- Không ghi dữ liệu nhạy cảm hoặc toàn bộ query result vào log.
- Dùng parameter binding cho giá trị query.
- Tránh trả dữ liệu PII nếu use case không cần.
- Theo dõi audit log và job history.
- Xác định retention và deletion policy cho dữ liệu phân tích.

Query parameter không thay thế authorization. Người dùng có thể không có quyền xem một row/cột dù service account của backend có quyền đọc table; backend cần kiểm tra business authorization trước khi trả dữ liệu.

## 10. Kiểm thử BigQuery trong ứng dụng Spring Boot

### 10.1. Unit test

BigQuery không có local emulator được cung cấp bởi Spring BigQuery starter. Unit test nên mock BigQuery hoặc BigQueryTemplate để kiểm tra:
- Câu SQL và parameter mapping.
- Quy tắc chuyển FieldValue thành DTO.
- Xử lý empty result.
- Xử lý exception và interrupted query.
- Kiểm tra job error và retry policy.
- Kiểm tra write disposition được chọn cho từng use case.

Không mock toàn bộ BigQuery client trong integration test rồi coi đó là bằng chứng IAM hoặc query thực tế hoạt động.

### 10.2. Integration test trên sandbox dataset

Tạo dataset test riêng trong project sandbox:
1. Dataset có location cố định.
2. Table có tên theo test run hoặc prefix.
3. Schema được tạo bằng code hoặc migration fixture.
4. Test query có parameter và đối chiếu kết quả.
5. Test load CSV từ bucket test hoặc InputStream.
6. Test write disposition trên table riêng.
7. Cleanup table/dataset sau test nếu được phép.

Dùng service account test có role tối thiểu. Không dùng dataset production để chạy test ghi hoặc truncate.

### 10.3. Test job completion

Job có trạng thái DONE không đồng nghĩa job thành công. Cần kiểm tra status.errorResult; nếu có lỗi, job thất bại. Một số lỗi từng dòng có thể xuất hiện trong status.errors mà không làm toàn bộ job thất bại, tùy maxBadRecords và cấu hình load.

Trong test, xác minh:
- Job ID.
- Job location.
- Job state.
- Fatal error.
- Nonfatal row errors nếu pipeline cho phép bad records.
- Số row đã nạp sau khi job thành công.

### 10.4. Test retry

Giả lập tình huống client mất kết nối sau khi gửi job:
- Tìm job theo ID đã tạo.
- Nếu job còn chạy, tiếp tục poll.
- Nếu job đã hoàn tất, đọc status.
- Chỉ tạo job ID khác khi bắt đầu batch mới.

Test cần chứng minh retry không nạp trùng cùng batch do client tự sinh ID mới sau timeout.

## 11. Vận hành, chi phí và quota

### 11.1. Theo dõi query job

Ghi nhận tối thiểu:
- Job ID và location.
- Dataset/table liên quan.
- Query label hoặc use case name.
- Bytes processed và bytes billed.
- Slot milliseconds.
- Thời gian chạy.
- Error result và execution errors.

Có thể truy vấn INFORMATION_SCHEMA.JOBS_BY_PROJECT để thống kê query, load, extract và copy job theo thời gian. Không lưu SQL chứa dữ liệu nhạy cảm vào log ứng dụng nếu không cần.

### 11.2. Quản lý chi phí query

- Ưu tiên partition filter trên bảng partitioned.
- Chọn cột cần thiết thay vì SELECT *.
- Dùng clustering theo cột filter/sort phù hợp.
- Dùng maximumBytesBilled cho query có rủi ro scan lớn.
- Dùng dry run khi xây dựng query mới.
- Theo dõi query cache và lịch sử job.
- Tách dashboard query khỏi API request có latency nghiêm ngặt.

Query tính phí theo bytes/slots tùy pricing model và reservation. Đừng chạy query phân tích lớn trong request HTTP đồng bộ nếu người dùng cần phản hồi nhanh; cân nhắc tạo job async và trả job ID để client poll.

### 11.3. Giảm số lượng load job

Load job có quota theo project/table và giới hạn tốc độ nạp. Nếu pipeline tạo một load job cho từng file nhỏ, số lượng job có thể tăng nhanh.

Thay vào đó:
- Gộp nhiều file cùng schema thành một batch khi phù hợp.
- Dùng wildcard URI hợp lệ để nạp nhiều object.
- Dùng Storage Write API khi dữ liệu đến liên tục.
- Theo dõi quota và lỗi quotaExceeded.
- Thiết kế retry có exponential backoff.

Không retry nhanh liên tục khi quota đã cạn; điều đó chỉ làm tăng tải và không giải quyết giới hạn.

### 11.4. Quan sát Storage Write API

Với Storage Write API, theo dõi:
- Batch size và append latency.
- Số stream đang mở.
- Số lần retry và offset.
- Lỗi schema mismatch.
- Pending stream chưa finalize/commit.
- Thời gian từ append đến khi dữ liệu query được.

Nếu dùng pending streams, cần giám sát tiến độ finalize/commit và thời hạn stream. Nếu dùng default stream, hiểu rõ at-least-once semantics và triển khai deduplication ở ứng dụng nếu sự kiện có thể được gửi lặp.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| PERMISSION_DENIED khi query | Thiếu bigquery.jobs.create hoặc quyền đọc table | Kiểm tra job project và dataset/table IAM |
| Access Denied khi load từ GCS | Runtime principal không đọc được object | Cấp storage.objects.get và list khi dùng wildcard |
| Dataset not found | Sai project, dataset ID hoặc location | Kiểm tra cấu hình project-id và dataset-name |
| Query location mismatch | Job chạy khác location dataset | Chỉ định đúng location trong JobId/job config |
| Unrecognized name | SQL dùng sai field hoặc schema khác thực tế | Kiểm tra schema và tên field |
| Parameter type mismatch | Dùng sai QueryParameterValue factory | Khớp kiểu parameter với kiểu BigQuery |
| Load job không parse được CSV | Header, delimiter, quote hoặc encoding không đúng | Cấu hình CsvOptions và schema tường minh |
| Header bị nạp thành row đầu | Không skip header | Dùng setSkipLeadingRows(1) |
| Schema mismatch | File source không khớp schema table | Chuẩn hóa schema, kiểm tra nullability và field order |
| quotaExceeded | Tạo quá nhiều load job hoặc table modifications | Gộp batch, giảm job frequency, backoff |
| Job state DONE nhưng dữ liệu thiếu | Có nonfatal row errors hoặc maxBadRecords | Kiểm tra status.errors và số row đích |
| Future chưa hoàn tất | Load job còn chạy hoặc job polling chậm | Theo dõi future/job ID, đặt timeout phù hợp |
| Storage Write API response thất bại | Schema mismatch hoặc stream error | Kiểm tra WriteApiResponse.getErrors() |
| Dữ liệu ghi lặp sau retry | Tạo job ID mới cho cùng batch hoặc stream semantics không idempotent | Giữ job ID/offset ổn định, deduplicate |
| Query quá đắt | Scan nhiều partition/cột hoặc thiếu giới hạn | Dry run, partition filter, projection, maximumBytesBilled |
| Ứng dụng giữ nhiều thread khi chờ job | Chờ future đồng bộ trong request path | Chạy ingestion async/batch worker, trả job ID |

## 13. Bài tập thực hành

### Bài A — Cấu hình starter

Thêm spring-cloud-gcp-starter-bigquery, cấu hình project ID và dataset name. Inject BigQuery và BigQueryTemplate; xác minh local ADC hoạt động với dataset sandbox.

### Bài B — Query có tham số

Viết service truy vấn orders theo customer ID, trạng thái và khoảng thời gian. Dùng named parameters; không nối input người dùng vào SQL. Map TableResult thành DTO.

### Bài C — Kiểm soát chi phí

Thêm maximumBytesBilled và thực hiện dry run cho query dashboard. So sánh bytes processed giữa query có partition filter và query không có filter.

### Bài D — BigQueryTemplate CSV

Nạp một file CSV vào table staging bằng writeDataToTable. Truyền schema rõ ràng, kiểm tra job status và so sánh số row với source file.

### Bài E — NDJSON và Storage Write API

Nạp file NDJSON bằng writeJsonStream. Thử cả overload table đã tồn tại và overload truyền schema. Kiểm tra WriteApiResponse.isSuccessful() và errors.

### Bài F — Load job từ Cloud Storage

Upload một batch CSV lên bucket cùng location với dataset. Tạo LoadJobConfiguration, đặt WRITE_APPEND, schema và job ID. Giả lập timeout rồi tra cứu lại job theo ID.

### Bài G — Spring Integration

Tạo input channel và BigQueryFileMessageHandler. Gửi Resource hoặc InputStream cùng table name/format headers. Xử lý CompletableFuture<Job> ở reply channel.

### Bài H — IAM và sandbox

Chạy ứng dụng bằng service account riêng. Cấp roles/bigquery.jobUser, roles/bigquery.dataEditor ở dataset test và quyền đọc bucket source. Xác minh thiếu quyền sẽ tạo lỗi rõ ràng.

### Bài I — Thiết kế pipeline

Chọn giữa load job và Storage Write API cho ba tình huống: nightly file, event stream và backfill lịch sử. Giải thích latency, atomicity, retry và quota của từng lựa chọn.

### Câu hỏi tự kiểm tra

1. BigQuery phù hợp với workload nào và khác database OLTP ra sao?
2. Project, dataset, table và schema liên hệ với nhau như thế nào?
3. spring-cloud-gcp-starter-bigquery tự cấu hình những bean nào?
4. BigQueryTemplate được scope theo property nào?
5. Vì sao query parameter không thể thay thế tên table?
6. Named parameter khác positional parameter như thế nào?
7. Vì sao nên dùng maximumBytesBilled và dry run?
8. Khi nào nên dùng BigQuery client thay template?
9. writeDataToTable trả về kiểu kết quả nào?
10. writeJsonStream khác load job CSV như thế nào?
11. Khi nào overload writeJsonStream cần schema?
12. WRITE_APPEND, WRITE_TRUNCATE và WRITE_EMPTY khác nhau ra sao?
13. Load job có atomic không?
14. Vì sao nên giữ job ID ổn định khi retry?
15. Những định dạng nào có thể batch load từ Cloud Storage?
16. Dataset location ảnh hưởng load job như thế nào?
17. Pending stream khác default stream ra sao?
18. Khi nào cần Storage Write API thay vì load job?
19. BigQueryFileMessageHandler nhận payload và reply như thế nào?
20. Runtime cần quyền IAM nào để chạy query và load từ GCS?
21. Vì sao DONE không đồng nghĩa job thành công?
22. Làm thế nào kiểm tra nonfatal row errors?
23. Vì sao không nên tạo một load job cho từng file rất nhỏ?
24. Khi nào cần chạy integration test trên sandbox thay vì mock client?

**Kết quả mong đợi:** người học cấu hình được BigQuery starter, chạy query GoogleSQL có tham số bằng Java client, nạp CSV/NDJSON bằng BigQueryTemplate, tạo load job theo lô từ Cloud Storage, lựa chọn Storage Write API khi phù hợp, kiểm tra job/retry an toàn, cấp IAM tối thiểu và theo dõi chi phí/quota trong ứng dụng Spring Boot.

## Tài liệu tham khảo

- [Spring Framework on Google Cloud 8.2.1 — BigQuery](https://googlecloudplatform.github.io/spring-cloud-gcp/8.2.1/reference/html/index.html#bigquery)
- [Spring Framework on Google Cloud — BigQueryTemplate Javadocs](https://googleapis.dev/java/spring-cloud-gcp/latest/com/google/cloud/spring/bigquery/core/BigQueryTemplate.html)
- [BigQueryJsonDataWriter Javadocs](https://googleapis.dev/java/spring-cloud-gcp/latest/com/google/cloud/spring/bigquery/core/BigQueryJsonDataWriter.html)
- [BigQuery Java client — QueryJobConfiguration](https://docs.cloud.google.com/java/docs/reference/google-cloud-bigquery/latest/com.google.cloud.bigquery.QueryJobConfiguration)
- [BigQuery Java client — JobId](https://docs.cloud.google.com/java/docs/reference/google-cloud-bigquery/latest/com.google.cloud.bigquery.JobId)
- [Run parameterized queries](https://docs.cloud.google.com/bigquery/docs/parameterized-queries)
- [Batch load data](https://docs.cloud.google.com/bigquery/docs/batch-loading-data)
- [Load CSV data from Cloud Storage](https://docs.cloud.google.com/bigquery/docs/loading-data-cloud-storage-csv)
- [BigQuery Storage Write API](https://docs.cloud.google.com/bigquery/docs/write-api-grpc)
- [Batch load with Storage Write API](https://docs.cloud.google.com/bigquery/docs/write-api-batch)
- [Optimize load jobs](https://docs.cloud.google.com/bigquery/docs/optimize-load-jobs)
- [BigQuery IAM roles and permissions](https://docs.cloud.google.com/bigquery/docs/access-control)

