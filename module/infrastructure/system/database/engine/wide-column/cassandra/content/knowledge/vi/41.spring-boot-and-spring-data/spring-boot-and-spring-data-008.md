# CassandraTemplate/CassandraOperations và kiểm soát CQL

> **Chương:** Spring Boot và Spring Data  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — tìm hiểu Apache Cassandra phân tán và mô hình wide-column; partition key, thiết kế bảng theo truy vấn, consistency level, CQL, replication, compaction, repair, xử lý lỗi và tích hợp ứng dụng Java.

Một dịch vụ Spring Boot có thể truy cập Cassandra bằng repository, `CassandraTemplate`, `CassandraOperations`, `CqlTemplate` hoặc trực tiếp `CqlSession`. Tất cả cuối cùng đều gửi CQL qua Java Driver, nhưng mỗi lớp kiểm soát một phần khác nhau của đường thực thi. Một dòng Java trông như `template.select(query, Job.class)` không làm Cassandra trở thành cơ sở dữ liệu quan hệ: **vẫn phải truy vấn đúng partition key, chịu quy tắc clustering, RF/CL và chi phí đọc SSTable**.

Bài này giải quyết câu hỏi: **khi nào nên để Spring Data tạo và ánh xạ CQL; khi nào phải viết CQL tường minh; làm sao kiểm tra câu lệnh, consistency, timeout, paging và kết quả thực sự được gửi tới Cassandra?**

> **Ranh giới quan trọng:** `CassandraTemplate` là một **implementation** cụ thể, `CassandraOperations` là **giao diện** cho ứng dụng phụ thuộc vào. `CqlTemplate`/`CqlOperations` làm việc gần CQL và rows hơn. `CqlSession` là API Java Driver mức thấp. Chọn abstraction không thay đổi bản chất partitioning, đồng thuận LWT hoặc durability.

Các ví dụ lấy API Spring Data Cassandra **4.5.x** đi với Spring Boot **3.5.x** làm nền minh họa, Java 17 và Java Driver 4.x; các nhánh Spring Data/Boot mới hơn có thể có thay đổi về API, BOM và package. **Không tự ghép tùy tiện Spring Data 5.x vào Boot 3.5**; kiểm tra version dependency thực tế trước khi dùng code trên môi trường của bạn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Vẽ đường đi `Spring Boot → CassandraOperations/Template → CqlTemplate/Driver → coordinator → replicas`.
2. Phân biệt repository, mapping template, CQL template và raw driver; chọn đúng mức trừu tượng cho một yêu cầu nghiệp vụ.
3. Ánh xạ entity bằng `@Table`, `@PrimaryKey`, `@Column`, hiểu khác biệt giữa thuộc tính Java và tên cột CQL.
4. Tạo truy vấn `Query`/`Criteria` hợp lệ theo partition key, hiểu `limit`, projection, range và giới hạn của `ALLOW FILTERING`.
5. Sử dụng `QueryOptions`, `InsertOptions`, `UpdateOptions` để kiểm soát CL, timeout, page size, idempotency, TTL và LWT.
6. Gọi CQL tham số hóa qua `CqlOperations` hoặc `CqlSession` khi cần `TTL()`, `WRITETIME()`, native paging, tracing hoặc kết quả CAS chi tiết.
7. Nhận diện `wasApplied`/boolean của thao tác không điều kiện và timeout **chưa xác định** kết quả ghi.
8. Lập lab/test xác minh SQL-equivalent CQL thực tế, tránh full scan, dữ liệu trùng và sai consistency.

## 2. Bức tranh các lớp truy cập dữ liệu

~~~mermaid
flowchart TD
    A["HTTP/Job/Service Spring Boot"] --> B{"Cần mức kiểm soát nào?"}
    B --> C["Repository<br/>CRUD/query phổ biến"]
    B --> D["CassandraOperations<br/>Query/Criteria + entity mapping"]
    B --> E["CqlOperations<br/>CQL + bind + RowMapper"]
    B --> F["CqlSession Java Driver 4.x<br/>Prepared/BoundStatement, metadata"]
    C --> D
    D --> G["CassandraTemplate"]
    G --> H["CqlTemplate / statement factory"]
    E --> H
    H --> F
    F --> I["Native protocol, load balancing, retry, TLS"]
    I --> J["Cassandra coordinator"]
    J --> K["Replicas theo token, RF và consistency"]
~~~

### 2.1. Lựa chọn abstraction có chủ đích

| Nhu cầu | API phù hợp | Ưu điểm | Lưu ý |
|---|---|---|---|
| CRUD theo PK, mapping rõ ràng | Repository | Ít boilerplate, dễ tổ chức domain | Tên method không loại bỏ giới hạn CQL |
| Query động theo PK, kiểm soát projection, paging | `CassandraOperations` / `CassandraTemplate` | `Query/Criteria`, mapping, exception translation | Cần xem CQL được tạo và QueryOptions |
| CQL tùy biến, `TTL/WRITETIME`, kết quả ít cột | `CqlOperations` / `CqlTemplate` | CQL được nhìn thấy, bind, RowMapper | Tự chịu trách nhiệm thiết kế schema/query |
| Routing metadata, token, paging state, execution info, CAS current values | `CqlSession` | Kiểm soát `Prepared/BoundStatement` và kết quả driver | Nhiều code và logic chuyển lỗi hơn |
| Reactive end-to-end | `ReactiveCassandraOperations` | `Flux/Mono`, non-blocking pipeline | Không được gọi template đồng bộ trên event loop |
| Bulk export và xử lý page chính xác | Driver paging hoặc `stream/slice` đã kiểm thử | Tránh nạp toàn bộ vào một List lớn | Deadline, memory, retry và consistency vẫn cần |

`CassandraTemplate` thực thi `CassandraOperations`, dùng `MappingCassandraConverter` để đổi row ↔ entity, đồng thời dịch nhiều driver exceptions thành hệ `org.springframework.dao.DataAccessException`. Template được cấu hình thành bean có thể **dùng lại an toàn giữa các luồng**; không tạo một Template và CqlSession mới cho mỗi HTTP request.

### 2.2. Vì sao service nên phụ thuộc giao diện?

~~~java
import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.stereotype.Service;

@Service
public final class JobQueryService {
    private final CassandraOperations cassandra;

    public JobQueryService(CassandraOperations cassandra) {
        this.cassandra = cassandra;
    }

    // Các method dùng CassandraOperations nằm ở các phần sau.
}
~~~

Spring Boot có thể auto-configure bean template/session từ starter. Nếu có **nhiều keyspace hoặc nhiều session**, dùng `@Qualifier` để chọn đúng bean. Không viết hai bean cùng tên mơ hồ rồi chấp nhận query nhầm keyspace.

**Chú ý:** giao diện giúp giảm phụ thuộc implementation và thuận tiện test, nhưng **không khiến unit test mock chứng minh CQL thực chạy đúng**. Cần integration test với Cassandra thật/ephemeral cluster.

## 3. Cấu hình Spring Boot và kiểm tra BOM

### 3.1. Starter và Java runtime

Ví dụ Maven rút gọn, Spring Boot 3.5.x yêu cầu Java **17+**. Phiên bản parent dưới đây để minh họa quan hệ; **chọn patch đã được phê duyệt, cập nhật bảo mật** khi triển khai:

~~~xml
<parent>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-parent</artifactId>
  <version>3.5.0</version>
  <relativePath/>
</parent>
<properties>
  <java.version>17</java.version>
</properties>
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Không gắn thêm bừa `com.datastax.oss:java-driver-core` và `org.apache.cassandra:java-driver-core` chỉ để “có driver mới”; hai tọa độ có thể cung cấp class tương tự và gây xung đột classpath. Kiểm tra **effective POM, dependency tree, Spring Boot BOM và phiên bản Java Driver thực đã resolve**. Nếu muốn thay driver để dùng tính năng Cassandra 5.0, phải kiểm tra compatibility của cả Spring Data và Java Driver.

### 3.2. Cấu hình kết nối tối thiểu

~~~yaml
spring:
  cassandra:
    contact-points:
      - "db1.dc1.internal.example:9042"
      - "db2.dc1.internal.example:9042"
    local-datacenter: "dc1"
    keyspace-name: "spring_lab"
    port: 9042
    # Các tùy chọn auth/TLS phải lấy từ secret manager/driver config.
~~~

Địa chỉ là **mẫu**, không phải cluster hoạt động. Phải xác minh DC thật bằng `nodetool status`; tên `dc1` sai khiến Driver không chọn được node local. Nếu môi trường yêu cầu TLS, hostname verification, role/password, không bỏ trống trong production. Ưu tiên secret injection, **không commit mật khẩu hoặc khóa riêng** vào repository.

Các property `spring.cassandra.*` thuộc Spring Boot 3.x; Spring Boot có thể cho phép tùy biến driver qua `DriverConfigLoader`, customizer hoặc HOCON riêng. Khi nhiều lớp cùng đặt timeout/consistency, phải xác định **thứ tự ưu tiên cuối cùng tại runtime**.

### 3.3. Phân biệt ba loại thời gian kết nối

| Thiết lập | Ý nghĩa | Không nên nhầm |
|---|---|---|
| Connection timeout | Chờ thiết lập kết nối tới node | Không phải timeout cho SELECT |
| Driver request timeout / statement timeout | Giới hạn chờ một CQL request/execute theo Driver | Không tự giới hạn toàn HTTP workflow |
| Business deadline | Tổng ngân sách auth, cache, CQL, serialize, retry | Không reset mỗi lần gọi repository |

Không tăng mọi timeout để che `LOCAL_QUORUM` unavailable, schema mismatch hoặc backlog compaction.

## 4. Lab Cassandra theo thiết kế bảng phục vụ truy vấn

### 4.1. Topology giả định

Lab yêu cầu Cassandra 4.x/5.x, keyspace `spring_lab` trong DC tên `dc1` có **ba node, RF=3**, phù hợp với `LOCAL_QUORUM`. Nếu có một node, chỉnh RF và consistency theo topology; **không** lập RF3 rồi kỳ vọng cluster một node phục vụ mọi truy vấn.

~~~bash
nodetool status
nodetool describecluster
nodetool version
~~~

Trong `cqlsh`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS spring_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;
~~~

### 4.2. Hai bảng để thể hiện hai nhu cầu

**Tra trạng thái job theo ID** — partition key đơn giản, phù hợp Entity + CassandraOperations:

~~~sql
CREATE TABLE IF NOT EXISTS spring_lab.jobs_by_id (
  job_id uuid PRIMARY KEY,
  status text,
  version bigint,
  expires_at timestamp,
  last_error text
) WITH default_time_to_live = 0;
~~~

**Đọc sự kiện theo thiết bị/ngày, mới nhất trước** — partition key nhiều thành phần, phù hợp prepared CQL và paging:

~~~sql
CREATE TABLE IF NOT EXISTS spring_lab.events_by_device_day (
  device_id uuid,
  event_day date,
  event_time timestamp,
  event_id uuid,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Hai truy vấn hợp lý:

~~~sql
SELECT job_id, status, version, expires_at, last_error
FROM spring_lab.jobs_by_id
WHERE job_id = 11111111-1111-4111-8111-111111111111;

SELECT event_time, event_id, payload
FROM spring_lab.events_by_device_day
WHERE device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;
~~~

**Vì sao:** `job_id` chỉ một partition; event query chỉ một partition `(device_id, event_day)` rồi giới hạn theo clustering `event_time`. Nếu viết `WHERE status = 'FAILED'` trên bảng `jobs_by_id`, query đó **không** tự trở thành truy vấn hiệu quả dù dùng `Criteria.where("status")`. Nếu nghiệp vụ thường xuyên tìm job lỗi, thiết kế **bảng khác theo trạng thái/truy vấn** và quản lý đồng bộ.

`IF NOT EXISTS` ở DDL **không chỉnh lại bảng cũ**. Sau khi chạy, kiểm tra:

~~~text
DESCRIBE KEYSPACE spring_lab;
DESCRIBE TABLE spring_lab.jobs_by_id;
DESCRIBE TABLE spring_lab.events_by_device_day;
~~~

### 4.3. Dữ liệu mẫu

~~~sql
INSERT INTO spring_lab.jobs_by_id
  (job_id, status, version, expires_at, last_error)
VALUES (
  11111111-1111-4111-8111-111111111111,
  'PENDING', 1, '2026-11-22T08:00:00Z', null
);

INSERT INTO spring_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, payload)
VALUES (
  22222222-2222-4222-8222-222222222222,
  '2026-11-21', '2026-11-21T08:30:00Z',
  33333333-3333-4333-8333-333333333333,
  'sample-event'
);
~~~

Ví dụ không dùng tài khoản/thiết bị thật và không chạy trên production. Trường `expires_at` là deadline nghiệp vụ để ứng dụng diễn giải; **chỉ ghi nó không tự khiến Cassandra TTL expire hàng**. Nếu cần tự hết hạn lưu trữ, cấu hình TTL và cơ chế dọn riêng.

## 5. Ánh xạ domain object bằng Spring Data Cassandra

### 5.1. Entity có khai báo tên cột tường minh

~~~java
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("jobs_by_id")
public class JobRow {
    @PrimaryKey("job_id")
    private UUID jobId;

    @Column("status")
    private String status;

    @Column("version")
    private Long version;

    @Column("expires_at")
    private Instant expiresAt;

    @Column("last_error")
    private String lastError;

    public JobRow() {}

    public JobRow(UUID jobId, String status, Long version,
                  Instant expiresAt, String lastError) {
        this.jobId = jobId;
        this.status = status;
        this.version = version;
        this.expiresAt = expiresAt;
        this.lastError = lastError;
    }

    public UUID getJobId() { return jobId; }
    public void setJobId(UUID id) { this.jobId = id; }
    public String getStatus() { return status; }
    public void setStatus(String value) { this.status = value; }
    public Long getVersion() { return version; }
    public void setVersion(Long value) { this.version = value; }
    public Instant getExpiresAt() { return expiresAt; }
    public void setExpiresAt(Instant value) { this.expiresAt = value; }
    public String getLastError() { return lastError; }
    public void setLastError(String value) { this.lastError = value; }
}
~~~

Annotations giữ tên bảng/cột đúng CQL, giảm phụ thuộc naming strategy mặc định. `UUID` ánh xạ `uuid`, `Instant` ánh xạ `timestamp`, `Long` ánh xạ `bigint`. Với UDT, collections, custom codecs và converters, phải test kiểu giá trị thực; Spring converter không thể cứu một CQL type không tương thích với Java.

**Không dùng `@Version` cho thuộc tính này trong ví dụ cơ bản** vì nó sẽ bật optimistic locking bằng LWT ở một số entity operations, thay đổi semantics/chi phí so với update thường. Phần LWT sẽ giải thích riêng.

### 5.2. Null, absent và DELETE không giống nhau

Cassandra là wide-column: ô dữ liệu không có giá trị, null trong entity, CQL `null`, `UNSET` khi bind và `DELETE` có thể dẫn đến hành vi/tombstone khác nhau. Khi thực hiện `template.save(entity)` hoặc `template.update(entity)`, hãy kiểm tra các tùy chọn **insert/update null values** của đúng phiên bản, không giả định mọi null đều được “giữ nguyên” hoặc mọi null đều xóa.

Một service cập nhật chỉ `status` nên ưu tiên câu update **chỉ ghi cột ấy** thay vì serialize toàn entity với nhiều thuộc tính null. Điều này giảm mutation/tombstone không cần thiết và tránh ghi đè giá trị mới ở các cột khác.

## 6. CassandraOperations với Query và Criteria

### 6.1. SELECT theo khóa chính

Spring Data Cassandra dùng `org.springframework.data.cassandra.core.query.Query` và `Criteria`. Ví dụ:

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.data.cassandra.core.query.Query;
import static org.springframework.data.cassandra.core.query.Criteria.where;
import static org.springframework.data.cassandra.core.query.Query.query;

public final class JobReader {
    private final CassandraOperations operations;

    public JobReader(CassandraOperations operations) {
        this.operations = operations;
    }

    public Optional<JobRow> find(UUID jobId) {
        Query q = query(where("job_id").is(jobId)).limit(1);
        return Optional.ofNullable(operations.selectOne(q, JobRow.class));
    }
}
~~~

`selectOne` ánh xạ row thành entity và có thể trả `null` nếu không tìm thấy. `limit(1)` hợp lý cho PK đơn; **không** biến predicate không có partition key thành query tốt.

**Mapping:** ví dụ dùng tên cột CQL `job_id` trực tiếp trong Criteria; với property-to-column mapping/naming strategy phức tạp, hãy quan sát statement được tạo và thử integration trên phiên bản Spring Data thực. Nếu code dùng `where("jobId")`, phải xác minh nó ánh xạ chính xác tới `job_id` theo mapping của entity.

### 6.2. Query/Criteria là các object bất biến

~~~java
Query q1 = query(where("job_id").is(jobId));
Query q2 = q1.limit(1);

// Phải dùng q2 vì q1 không bị sửa tại chỗ.
JobRow job = operations.selectOne(q2, JobRow.class);
~~~

Các phép `and(...)`, `queryOptions(...)`, `withAllowFiltering()` và `sort(...)` cũng trả một Query mới. Trong Java Driver 4.x, `BoundStatement.setConsistencyLevel(...)`/`setTimeout(...)` cũng trả instance mới — bẫy tương tự.

### 6.3. Query DSL không xóa giới hạn CQL

| Criteria/API | CQL/ngữ nghĩa | Khi nào hợp lý |
|---|---|---|
| `where("job_id").is(uuid)` | `job_id = ?` | Tìm một partition theo khóa |
| `where("event_time").gte(from)` | `event_time >= ?` | Chỉ hiệu quả khi đã ràng buộc partition key và `event_time` là clustering |
| `where("event_time").lt(until)` | `event_time < ?` | Range trên clustering trong partition |
| `where("status").is("FAILED")` | `status = ?` | **Không hợp lệ/không tối ưu** trên jobs_by_id nếu không có index/mô hình phù hợp |
| `Query.limit(100)` | `LIMIT 100` | Giới hạn rows trả lại; không đảm bảo disk scan nhỏ |
| `Query.withAllowFiltering()` | `ALLOW FILTERING` | Có thể buộc server scan rất rộng; không là cách “tối ưu” |

Spring Data giúp tạo **cú pháp CQL**, không tự thiết kế partition key, replication, index, SAI, clustering order hay query workload cho ứng dụng. Query thiếu đầy đủ partition key có thể bị Cassandra từ chối ngay cả khi Java compile tốt.

### 6.4. Projection và SELECT *

Mặc định, template có thể lấy tất cả cột để mapping entity; với payload lớn, `SELECT *` làm tăng network, CPU codec và khả năng lộ dữ liệu. Nếu màn hình chỉ cần status:

~~~sql
SELECT status
FROM spring_lab.jobs_by_id
WHERE job_id = 11111111-1111-4111-8111-111111111111;
~~~

Có thể dùng projection DTO/interface qua fluent template/repository, hoặc CQL tường minh với `CqlOperations`. **Đừng sửa một partial entity được chọn thiếu identity thành bản ghi đầy đủ**: update/save sau đó có thể ghi nulls hoặc ghi đè giá trị.

### 6.5. Chuyển bài toán tìm theo status thành thiết kế bảng

Thay vì gọi:

~~~java
// KHÔNG coi đây là giải pháp trên bảng jobs_by_id:
// operations.select(query(where("status").is("FAILED"))
//     .withAllowFiltering(), JobRow.class);
~~~

thiết kế bảng theo query “liệt kê job lỗi của tenant theo ngày”:

~~~sql
CREATE TABLE IF NOT EXISTS spring_lab.failed_jobs_by_tenant_day (
    tenant_id uuid,
    job_day date,
    failed_at timestamp,
    job_id uuid,
    summary text,
    PRIMARY KEY ((tenant_id, job_day), failed_at, job_id)
) WITH CLUSTERING ORDER BY (failed_at DESC, job_id ASC);
~~~

Denormalization giúp đọc có partition key xác định, nhưng đòi hỏi cập nhật/sửa/xóa các bảng liên quan theo workflow có reconciliation. Một update nhiều bảng khác partition **không** thành ACID transaction chỉ vì gọi qua cùng CassandraOperations.

## 7. QueryOptions: kiểm soát Driver thực thi CQL

### 7.1. Consistency, timeout, page size và idempotency

`QueryOptions` cho phép đặt thuộc tính theo request:

~~~java
import java.time.Duration;
import org.springframework.data.cassandra.core.cql.QueryOptions;
import org.springframework.data.cassandra.core.query.Query;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import static org.springframework.data.cassandra.core.query.Criteria.where;
import static org.springframework.data.cassandra.core.query.Query.query;

QueryOptions opts = QueryOptions.builder()
    .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .timeout(Duration.ofMillis(600))
    .pageSize(100)
    .idempotent(true)
    .build();

Query q = query(where("job_id").is(jobId))
    .queryOptions(opts)
    .limit(1);

JobRow job = operations.selectOne(q, JobRow.class);
~~~

`LOCAL_QUORUM` phụ thuộc RF ở local DC; `timeout` giới hạn một request driver theo version, không là deadline toàn HTTP; `pageSize` điều khiển số rows mong muốn mỗi trang, **khác** `LIMIT`; `idempotent(true)` hợp lý cho SELECT thuần nhưng không nên gắn máy móc với counter increment, LWT hay side-effectful writes.

### 7.2. Chọn execution profile

~~~java
QueryOptions shortRead = QueryOptions.builder()
    .executionProfile("short-read")
    .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .timeout(Duration.ofMillis(350))
    .build();
~~~

Tên profile phải được khai báo trong driver config/HOCON thực. Các cấp default/template/profile/statement có thể tương tác; **kiểm tra runtime statement** theo bản Spring Data/Driver được chọn thay vì dựa vào suy đoán thứ tự override.

### 7.3. CL không phải khóa giao dịch hoặc cách chữa timeout

| CL | Ý nghĩa đơn giản trong DC có RF=3 | Rủi ro nếu chọn sai |
|---|---|---|
| `LOCAL_ONE` | Một replica local đủ trả kết quả | Có thể đọc bản sao chưa đồng bộ |
| `LOCAL_QUORUM` | Hai replica local cần đáp ứng theo CL | Timeout/unavailable khi không đủ replicas |
| `QUORUM` | Quorum theo tổng RF/topology | Có thể chịu RTT liên DC tùy cấu hình |
| `SERIAL/LOCAL_SERIAL` | Mức serial của LWT/serial read | Không thay regular consistency |

**Không tự giảm `LOCAL_QUORUM → LOCAL_ONE`** chỉ để dashboard ít timeout hơn nếu điều đó phá bất biến. Nếu workflow HTTP chỉ còn 150 ms trước deadline, không đặt một template query timeout 600 ms rồi coi như vẫn kịp; tính `min(configuredCeiling, remaining - responseReserve)` và fail fast khi cần.

### 7.4. Idempotency, retry và TTL

Một `UPDATE SET status='DONE'` có thể idempotent về giá trị nhưng retry với write timestamp mới có thể ghi đè phiên bản đồng thời. Một `INSERT USING TTL 600` gửi lại sau nhiều phút có thể **gia hạn thời điểm hết hạn**; counter increment hoàn toàn không idempotent. Đừng bật `idempotent(true)` cho mọi mutation, hoặc để gateway + service + Spring Retry + Java Driver cùng retry không giới hạn. Một business request có thể khuếch đại thành nhiều CQL attempts.

## 8. Prepared statements và CQL injection

### 8.1. CassandraTemplate có sẵn cơ chế prepared

Spring Data Cassandra 4.x thường bật prepared statements trên `CassandraTemplate` theo mặc định; có API `setUsePreparedStatements(boolean)` để kiểm soát. Java Driver 4.x có prepared statement cache trong `CqlSession`, nên không cần thêm một cache tùy biến theo CQL text khi không có nhu cầu rõ.

**Dùng bind markers cho giá trị**, tránh thay đổi text câu lệnh theo mỗi UUID. Nếu CQL text khác cho từng request, driver/server phải quản lý nhiều prepared IDs hơn và rủi ro injection tăng.

### 8.2. CQL có tham số an toàn với CqlOperations

Sai:

~~~java
// Không nối input từ HTTP vào CQL string:
String unsafe = "SELECT status FROM spring_lab.jobs_by_id " +
    "WHERE job_id = " + request.getParameter("jobId");
~~~

Đúng:

~~~java
UUID jobId = UUID.fromString(request.getParameter("jobId"));

String status = operations.getCqlOperations().queryForObject(
    "SELECT status FROM spring_lab.jobs_by_id WHERE job_id = ?",
    String.class,
    jobId
);
~~~

`queryForObject(String, Class, Object...)` là API CqlTemplate/CqlOperations dùng prepared binding; xử lý thêm tình huống không có row và số row không phù hợp.

**Bind marker chỉ dùng cho giá trị, không bind được tên bảng/column**. Nếu hệ thống thật sự cần chọn bảng động, dùng allowlist tên CQL tĩnh, không cho client tự đưa identifier vào query text.

### 8.3. So sánh các đường prepared

| API | Nơi tạo CQL | Ai map kết quả? |
|---|---|---|
| `operations.select(Query, JobRow.class)` | Template dựng CQL và prepare theo cấu hình | MappingCassandraConverter |
| `operations.select(SimpleStatement, JobRow.class)` | Template có thể prepare/bind từ SimpleStatement | Converter |
| `operations.getCqlOperations().queryForObject(cql,type,args...)` | CQL tĩnh + args được bind | CQL template scalar extraction |
| `CqlSession.prepare(...).bind(...)` | Application tự kiểm soát CQL, codec, CL và routing | Ứng dụng đọc Row/ResultSet |

Khi cần `TTL(status)`, `WRITETIME(status)`, tracing và retry/metadata chi tiết, `CqlOperations` hoặc `CqlSession` phù hợp hơn một mapping toàn entity.

## 9. Ghi, TTL, LWT và ý nghĩa kết quả

### 9.1. InsertOptions cho TTL và CL

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.data.cassandra.core.InsertOptions;

InsertOptions options = InsertOptions.builder()
    .ttl(Duration.ofMinutes(10))
    .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .timeout(Duration.ofMillis(800))
    .build();

JobRow row = new JobRow(jobId, "PENDING", 1L, expiresAt, null);
operations.insert(row, options);
~~~

TTL là **thời gian tồn tại tương đối** tính khi ghi cell. Ghi lại cùng TTL sau timeout có thể gia hạn hạn dùng; `expiresAt` trong entity là trường dữ liệu nghiệp vụ, không tự đồng bộ với Cassandra TTL. `USING TTL 0` nghĩa là **không TTL**, không phải xóa ngay. Giữ đúng retention deadline cần tính TTL còn lại và kiểm soát retry.

### 9.2. UPDATE một cột tránh ghi đè toàn entity

~~~java
import org.springframework.data.cassandra.core.query.Update;
import static org.springframework.data.cassandra.core.query.Query.query;
import static org.springframework.data.cassandra.core.query.Criteria.where;

boolean applied = operations.update(
    query(where("job_id").is(jobId)),
    Update.update("status", "RUNNING"),
    JobRow.class);
~~~

**Boolean từ UPDATE không điều kiện không chứng minh hàng đã tồn tại hoặc có compare-and-set thành công.** Cassandra cho phép upsert; Java Driver `wasApplied` trả true theo quy ước với non-LWT. Muốn update khi hàng có, hoặc theo version, cần conditional CQL/LWT.

### 9.3. Insert IF NOT EXISTS qua InsertOptions

~~~java
InsertOptions conditional = InsertOptions.builder()
    .withIfNotExists()
    .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .serialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
    .timeout(Duration.ofMillis(1200))
    .build();

var result = operations.insert(row, conditional);
if (!result.wasApplied()) {
    // Điều kiện IF NOT EXISTS không thỏa; báo business conflict.
    // result.getRows() có thể chứa những cột của hàng hiện hữu.
}
// Khi cần current row chi tiết, kiểm tra getRows()/ColumnDefinitions
// hoặc dùng low-level ResultSet phù hợp version.
~~~

`IF NOT EXISTS` là LWT/Paxos và kiểm tra **đúng primary key**, không tạo unique constraint tùy ý trên `status`. Khi `[applied]=false`, đó là xung đột điều kiện; timeout có thể là **unknown outcome**, không được đổi thành false hoặc retry vô hạn.

### 9.4. @Version kích hoạt optimistic locking

Spring Data Cassandra có `@Version` trên entity, sử dụng LWT cho các single-entity operations. Ví dụ một entity **khác** đã được thiết kế riêng:

~~~java
// @Table("state_by_id")
// public class StateById {
//   @PrimaryKey("id") UUID id;
//   @Version Long version;
//   String state;
// }
~~~

Các update/delete có điều kiện version có thể ném `OptimisticLockingFailureException`. Không gắn `@Version` cho mọi field tên version chỉ để map `bigint`; nó làm thay đổi semantics/chi phí Paxos và không tự tạo transaction multi-partition.

### 9.5. DELETE và tombstone

~~~java
boolean deleted = operations.delete(
    query(where("job_id").is(jobId)), JobRow.class);
~~~

DELETE tạo tombstone; boolean của lệnh không điều kiện không chứng minh hàng đã tồn tại trước đó hoặc disk bytes đã purge. `gc_grace_seconds`, compaction và repair là vấn đề vận hành riêng.

## 10. Khi cần kiểm soát CQL trực tiếp

### 10.1. CqlOperations qua CassandraOperations

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.core.CassandraOperations;

static String readStatus(CassandraOperations ops, UUID jobId) {
    return ops.getCqlOperations().queryForObject(
        "SELECT status FROM spring_lab.jobs_by_id WHERE job_id = ?",
        String.class,
        jobId
    );
}
~~~

Template cấp CQL giúp giữ prepared binding và exception translation mà không cần map toàn entity. Với per-cell TTL/writetime hoặc CQL functions, có thể dùng RowMapper/ResultSetExtractor; với metadata routing/paging/CAS chi tiết thì dùng `CqlSession`.

### 10.2. Prepared CQL cho partition key kép

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

void readRecent(CqlSession session, UUID deviceId, LocalDate day,
                Instant from, Instant until) {
    PreparedStatement prepared = session.prepare(
        "SELECT event_time, event_id, payload " +
        "FROM spring_lab.events_by_device_day " +
        "WHERE device_id = ? AND event_day = ? " +
        "AND event_time >= ? AND event_time < ? LIMIT ?");

    BoundStatement bound = prepared.bind(
            deviceId, day, from, until, 100)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setPageSize(50)
        .setIdempotent(true);

    ResultSet result = session.execute(bound);
    for (Row row : result) {
        UUID id = row.getUuid("event_id");
        Instant eventTime = row.getInstant("event_time");
        // Xử lý theo business deadline, không log payload nhạy cảm.
    }
    System.out.println("Coordinator=" +
        result.getExecutionInfo().getCoordinator());
}
~~~

**Lưu ý:** `CqlSession` là bean dài hạn do Spring quản lý, không đóng mỗi HTTP request. Driver suy routing key khi prepared query bind **đầy đủ partition key**; `setPageSize(50)` không giới hạn kết quả ở 50; iterator có thể lấy trang sau. `ExecutionInfo.getCoordinator()` không cho biết tất cả replicas phục vụ CL.

### 10.3. Raw CQL cho LWT và current version

~~~java
PreparedStatement cas = session.prepare(
    "UPDATE spring_lab.jobs_by_id " +
    "SET status = ?, version = ? WHERE job_id = ? " +
    "IF version = ?");

BoundStatement request = cas.bind("RUNNING", 2L, jobId, 1L)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

ResultSet rs = session.execute(request);
if (rs.wasApplied()) {
    System.out.println("CAS_APPLIED");
} else {
    Row current = rs.one();
    Long versionNow = current != null
            && current.getColumnDefinitions().contains("version")
            && !current.isNull("version")
        ? current.getLong("version")
        : null;
    System.out.println("CAS_CONFLICT version=" + versionNow);
}
~~~

Một CAS false là **điều kiện không thỏa**. Nếu exception/timeout, ghi có thể đã commit nhưng ACK mất: phải đánh dấu unknown/reconcile, không coi là false hay rollback. Với workflow nhiều bảng/partitions, hai API được gọi tuần tự **không** tạo transaction ACID; cần idempotency và reconciliation.

## 11. Paging, stream và giới hạn dữ liệu

### 11.1. LIMIT, page size và tổng số rows là ba khái niệm khác

| Cơ chế | Kiểm soát | Không bảo đảm |
|---|---|---|
| `Query.limit(100)` / CQL `LIMIT 100` | Số rows tối đa của một query theo semantics CQL | Không chứng minh disk chỉ scan 100 cells/tombstones |
| `QueryOptions.pageSize(50)` | Rows/page mong muốn qua native protocol | Không giới hạn toàn result ở 50 |
| `Slice<JobRow>` | Một đoạn kết quả kèm thông tin trang tiếp theo | Không tự rẻ nếu truy vấn thiếu partition key |
| `Stream<JobRow>` | Xử lý rows tuần tự/lười qua iterator | Không tự bảo vệ memory nếu caller `collect(toList())` |
| `ResultSet.getExecutionInfo()` | Metadata của execution đã nhận | Không phản ánh mọi replica và không luôn chứa thông tin tất cả pages |

Một `SELECT` trên partition có 10.000 rows và page size 100 có thể cần nhiều lần fetch mạng; một business deadline phải áp cho **cả quá trình tiêu thụ**, không khởi tạo budget mới cho mỗi page.

### 11.2. Streaming với CassandraOperations

~~~java
import java.util.stream.Stream;
import static org.springframework.data.cassandra.core.query.Query.query;
import static org.springframework.data.cassandra.core.query.Criteria.where;

Query q = query(where("job_id").is(jobId));
try (Stream<JobRow> rows = operations.stream(q, JobRow.class)) {
    rows.forEach(job -> {
        // Xử lý nhanh, không giữ tất cả entity trong một List lớn.
        // Với nguồn dữ liệu nhạy cảm, không log nguyên row.
    });
}
~~~

Ví dụ với PK đơn chỉ trả tối đa một row; nó minh họa vòng đời stream. Để thực sự đo paging, dùng bảng `events_by_device_day` có nhiều rows và một query ràng buộc đầy đủ partition key như mục 4; hoặc dùng Driver async paging.

**Cẩn trọng:** `Stream<T>` có thể sử dụng resources/lazy iteration liên quan driver. Dùng try-with-resources khi API yêu cầu và không để stream sống qua HTTP request sau khi session/transaction context đã bị đóng. Xử lý nặng, blocking I/O hoặc gọi HTTP trong mỗi row có thể khiến tổng thời gian vượt deadline và tạo request backlog.

### 11.3. Cassandra paging không giống OFFSET trong SQL

Cassandra **không** hỗ trợ cách phân trang tổng quát bằng `OFFSET 1000000` như nhiều RDBMS. Driver sử dụng paging state, phía Spring Data có các abstraction `Slice`/`CassandraPageRequest`/scrolling theo version. Không suy ra page 7 bằng cách quét lại từ đầu sáu trang trước nếu còn cách dùng paging state.

Quy tắc:

- Paging state phải gắn với **cùng CQL, bind parameters, query options phù hợp và schema**; không đưa token state từ query khác vào.
- Nếu trả paging state cho client, cân nhắc encode/sign, TTL và quyền truy cập; không để người dùng dùng một state của tenant khác.
- Paging state không phải snapshot transaction toàn cluster; dữ liệu có thể thêm/xóa/TTL giữa các pages.
- Với export cần nhất quán tuyệt đối, phải thiết kế watermark/time window, idempotent sink và kiểm thử duplicate/missing rows.
- Dùng `LIMIT` phù hợp workload; `pageSize` chỉ là kiểm soát kích thước từng đợt.

### 11.4. Sorting theo clustering, không theo tùy ý

Một câu `ORDER BY event_time DESC` có thể hợp lệ nhờ clustering order trong partition, nhưng sắp xếp tùy cột `status` hoặc `payload` không được Cassandra hỗ trợ như SQL. `Query.sort(...)` chỉ tạo CQL; nếu không phù hợp clustering restrictions, server từ chối hoặc query không tốt. Giải pháp là **thay data model theo query**, không thêm `ALLOW FILTERING` vào mọi truy vấn.

## 12. Imperative, async và reactive

### 12.1. Chọn execution model tương ứng với thread model

| Môi trường | API phù hợp | Lưu ý |
|---|---|---|
| Spring MVC / service thread-per-request | `CassandraOperations`, `CassandraTemplate` | Blocking; đo pool/inflight và HTTP deadline |
| Service dùng `CompletionStage` | `AsyncCassandraOperations/AsyncCassandraTemplate` hoặc driver async | Quản lý completion errors, không block callback |
| Spring WebFlux end-to-end | `ReactiveCassandraOperations/ReactiveCassandraTemplate` | `Mono/Flux`, cancellation, bounded concurrency |
| Low-level Reactor/Driver | `CqlSession.executeReactive(...)` | ReactiveResultSet cold/single-subscription, metadata riêng |

**Không** dùng `CassandraTemplate` blocking trực tiếp trong event-loop WebFlux rồi tuyên bố toàn pipeline non-blocking. Nếu tạm dùng blocking library, phải chuyển sang scheduler phù hợp và kiểm soát concurrency; tốt hơn dùng reactive operations nếu đó là lựa chọn kiến trúc đã duyệt.

### 12.2. ReactiveCassandraOperations với Query

~~~java
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.data.cassandra.core.query.Query;
import reactor.core.publisher.Mono;
import static org.springframework.data.cassandra.core.query.Criteria.where;
import static org.springframework.data.cassandra.core.query.Query.query;

Mono<JobRow> findReactive(
        ReactiveCassandraOperations ops, UUID jobId) {
    Query q = query(where("job_id").is(jobId)).limit(1);
    return ops.selectOne(q, JobRow.class);
}
~~~

`Mono` là publisher: truy vấn thường được thực thi khi subscribe, không gọi `block()` trong reactive controller. Một Reactor retry có thể **subscribe lại** và tạo một query mới, đặc biệt nguy hiểm nếu source là mutation, LWT hoặc side effect. Cần deadline và idempotency đúng.

### 12.3. Khi dùng @Async không đồng nghĩa reactive

Một repository method `@Async CompletableFuture<T>` có thể chuyển blocking work sang thread pool, còn ReactiveCassandraOperations sử dụng publisher semantics và backpressure riêng. Không “bọc” mọi blocking CassandraTemplate call vào `Mono.just(...)` trong event-loop; đó vẫn là lời gọi blocking trước khi tạo Mono. Nếu buộc bridging, dùng deferred publisher/scheduler có giới hạn và theo dõi backlog.

## 13. Kiểm tra chính xác CQL và quan sát hiệu năng

### 13.1. Những thứ phải kiểm chứng ở mức CQL

Một method như `operations.select(query(where("job_id").is(id)), JobRow.class)` chỉ đúng khi:

1. Tên cột CQL do converter render phù hợp với schema thật.
2. Câu WHERE có partition key đầy đủ.
3. CQL projection/mapping không âm thầm thiếu field bắt buộc.
4. Consistency level đúng DC/RF, không dùng CL mặc định ngoài ý muốn.
5. Page size, LIMIT và timeout nằm trong ngân sách nghiệp vụ.
6. Ghi/đọc dữ liệu đúng biến thể nullable, UDT, collection, timestamp.
7. Các thao tác conditional được phân biệt với upsert bình thường.

### 13.2. Log/tracing không được lộ dữ liệu

Có thể bật request tracing theo mẫu nhỏ:

~~~java
QueryOptions traced = QueryOptions.builder()
    .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .tracing(true)
    .build();
~~~

**Không bật tracing trên toàn bộ production QPS**: tracing có overhead; nhiều CQL rows/logs có thể chứa bind values, query text và dữ liệu nhạy cảm. Dùng sampled traces, masking và cấu hình retention hạn chế. Với driver low-level, `Statement.setTracing(true)` cũng phải được dùng theo phiên bản được kiểm chứng.

Metrics hữu ích:

| Metric | Lý do |
|---|---|
| Request p50/p95/p99 per CQL pattern | Phát hiện query không đúng partition/key |
| Timeout/unavailable/retries per CL | Kiểm tra RF, node Down và quá tải |
| In-flight, pool streams, throttling queue | Phân biệt thiếu tài nguyên client với backend chậm |
| Row count/bytes/page count | Phát hiện SELECT * hoặc trả dữ liệu quá nhiều |
| Tombstones scanned và SSTables per read | Giải thích reads chậm dù WHERE có partition key |
| CAS applied/conflicts/unknown | Xác minh write invariant và contention |
| Partition hot-key skew (ẩn danh) | Giải thích load bất cân xứng giữa replicas |
| GC/CPU/network/compaction/repair | Đánh giá sức khỏe toàn cluster |

Không log full token/API keys và không đưa UUID định danh người dùng vào metrics labels có cardinality quá lớn. Việc lấy logger categories cụ thể phụ thuộc bản Spring Data, Driver và hệ observability; xem config thực thay vì bật DEBUG bừa trên production.

### 13.3. Đọc EXPLAIN như SQL? Không suy luận vậy

Cassandra CQL không cung cấp một bộ `EXPLAIN ANALYZE` tương đương PostgreSQL cho mọi query. Tùy bản và công cụ, có thể dùng tracing, driver metrics, `nodetool tablestats`, histogram, system_schema/index metadata và benchmark có kiểm soát.

Nếu một query chỉ chạy được khi thêm `ALLOW FILTERING`, đó là một dấu hiệu cần xem lại **data model/index**, không phải bằng chứng query đã tối ưu.

## 14. Lab tích hợp: từ API Template đến CQL thật

### 14.1. Chuẩn bị và bảo vệ lab

Sử dụng schema của mục 4 trên **cluster Cassandra lab**. Với RF=3/`dc1` phải có đủ node, xác minh:

~~~bash
nodetool status
nodetool describecluster
nodetool tablestats spring_lab.jobs_by_id
~~~

Chỉ dùng địa chỉ/credentials lab, không tắt firewall/TLS của production để chạy bài tập. Nếu người học có một node, điều chỉnh RF=1 và consistency tương ứng **trước khi tạo keyspace**, sau đó kiểm chứng thật.

### 14.2. Bài thực hành A — đọc bằng ba API

Thực hiện:

1. Với UUID mẫu `11111111-1111-4111-8111-111111111111`, gọi `operations.selectOne(query(where("job_id").is(id)), JobRow.class)`.
2. Gọi `operations.getCqlOperations().queryForObject("SELECT status ... WHERE job_id=?", String.class, id)`.
3. Gọi `CqlSession.prepare("SELECT status ... WHERE job_id=?")` và `session.execute(bound)`.
4. So `status`, `CL`, coordinator, timeout và số request.
5. Ghi khác biệt giữa entity mapping, scalar result và raw driver metadata.

**Kỳ vọng:** cùng dữ liệu từ một hàng, nhưng độ sâu metadata có sẵn khác nhau. Nếu ba API trả khác kết quả, kiểm tra keyspace/schema, CL/replica consistency, data mutations xen kẽ và converter — **không** kết luận ngay framework sai.

### 14.3. Bài thực hành B — QueryOptions có hiệu lực?

1. Tạo `QueryOptions` với `LOCAL_QUORUM`, timeout 500 ms và page size 50.
2. Thực thi truy vấn PK và ghi thống kê thành công/timeout.
3. Đổi sang một execution profile đã cấu hình (chỉ trong lab) rồi so config thực.
4. Cố ý gọi `q.limit(1)` nhưng **không gán lại** rồi quan sát Query đã truyền vào method; sửa thành `q = q.limit(1)`.
5. Dùng logging/tracing mẫu thấp để xem CQL thực; xác nhận **không có ALLOW FILTERING**.

Kết quả phải dựa trên trace/metrics quan sát, không đoán rằng một setter đã thay đổi object.

### 14.4. Bài thực hành C — LWT xung đột version

Trên hàng có version 1:

~~~sql
UPDATE spring_lab.jobs_by_id
SET status = 'RUNNING', version = 2
WHERE job_id = 11111111-1111-4111-8111-111111111111
IF version = 1;
~~~

Chạy lần đầu và chạy lại:

- Lần đầu, nếu chưa có writer khác, `[applied]=true`.
- Lần sau khi version đã là 2, `[applied]=false` và có thể nhận `version=2`.
- Dùng code raw `ResultSet.wasApplied()` để phân biệt outcome.
- Nếu chỉ gọi `operations.update(query, Update, JobRow.class)` mà không thêm điều kiện, đó **không phải** CAS.
- Nếu timeout, không thể kết luận mutation không áp dụng; thực hiện read/reconcile.

### 14.5. Bài thực hành D — TTL và kiểm tra deadline

Chạy trong CQL lab:

~~~sql
UPDATE spring_lab.jobs_by_id USING TTL 120
SET last_error = 'temporary'
WHERE job_id = 11111111-1111-4111-8111-111111111111;

SELECT TTL(last_error), WRITETIME(last_error)
FROM spring_lab.jobs_by_id
WHERE job_id = 11111111-1111-4111-8111-111111111111;
~~~

Quan sát TTL giảm theo giây trong khi `version` hoặc `status` có thể có TTL khác. Không dùng một TTL duy nhất cho tất cả cột nếu ứng dụng copy/ETL cell riêng. So sánh `TTL()` với `expires_at` để thấy **deadline ứng dụng và TTL storage khác nhau**.

### 14.6. Bài thực hành E — anti-pattern theo non-key

Thử query `WHERE status = 'PENDING'` trên `jobs_by_id`:

1. Xem Cassandra từ chối như thế nào nếu không có index/partition key.
2. **Không** bật `withAllowFiltering()` trên production để “sửa”.
3. Phác thảo bảng theo query như `failed_jobs_by_tenant_day`.
4. Xác định partition key, clustering, RF/CL, TTL và workflow cập nhật bảng denormalized.
5. So số partitions/tombstones/bytes với query tốt, thay vì chỉ so thời gian ở dataset vài hàng.

### 14.7. Bảng kết quả thực nghiệm

| Case | API | CQL/partition key | CL | Rows/pages | p95/p99 | Đúng nghiệp vụ? |
|---|---|---|---|---|---|---|
| A1 | CassandraOperations | Job ID | _điền_ | _điền_ | _điền_ | _điền_ |
| A2 | CqlOperations | Job ID | _điền_ | _điền_ | _điền_ | _điền_ |
| A3 | CqlSession | Job ID | _điền_ | _điền_ | _điền_ | _điền_ |
| B | QueryOptions/profile | Job ID | _điền_ | _điền_ | _điền_ | _điền_ |
| C | LWT/CAS | Job ID, version | _điền_ | _điền_ | _điền_ | _điền_ |
| D | TTL/WRITETIME | Job ID | _điền_ | _điền_ | _điền_ | _điền_ |
| E | Non-key scan | Không đủ partition key | _điền_ | _điền_ | _điền_ | _điền_ |

Không tự điền benchmark nếu chưa chạy. Với một row trong lab, p99 không có ý nghĩa thống kê; tăng nhiều partitions/requests và lặp thử trong môi trường kiểm soát nếu thật sự muốn kết luận hiệu năng.

## 15. Những lỗi phổ biến khi dùng Template

| Ngộ nhận | Vì sao sai | Cách đúng |
|---|---|---|
| “CassandraTemplate tạo query tốt tự động” | Query DSL không thiết kế partition key | Xem CQL/WHERE và data model theo query |
| “CassandraOperations và CassandraTemplate là hai hệ thống khác” | Interface và implementation của cùng abstraction | Inject CassandraOperations, override implementation khi cần |
| “Template là ORM SQL và có JOIN đa bảng” | Cassandra không hỗ trợ JOIN quan hệ tùy ý | Denormalize/bảng theo truy vấn |
| “LIMIT 10 nghĩa chỉ đọc 10 cells” | Tombstones/filter có thể khiến server scan rộng | Xem data layout, trace, tombstone metrics |
| “ALLOW FILTERING tối ưu WHERE status” | Có thể tạo scan đắt | Thiết kế bảng/index theo workload |
| “pageSize=50 trả đúng 50 hàng tổng” | Page size khác query limit | Kiểm tra toàn bộ pages và deadline |
| “Gọi q.limit(1) đã sửa q” | Query immutable | Dùng giá trị Query mới trả về |
| “SELECT * là miễn phí vì converter chỉ dùng 2 fields” | Server vẫn có thể truyền dữ liệu thừa | Projection/DTO/CQL cột cần thiết |
| “Nối UUID vào CQL thuận tiện hơn bind” | Injection/quoting/prepared-cache risk | Prepared placeholders và typed bind |
| “Boolean update=true nghĩa có row cũ” | Non-LWT upsert, wasApplied=true mặc định | Dùng IF EXISTS nếu cần existence check |
| “Spring @Version chỉ là field mapping” | Nó bật LWT optimistic locking | Chỉ dùng khi yêu cầu CAS và chấp nhận chi phí |
| “DELETE=true nghĩa disk được giải phóng” | Tombstone/compaction tách biệt | Phân biệt logical deletion/physical purge |
| “Timeout chắc chắn write chưa commit” | ACK có thể mất sau khi mutation áp dụng | UNKNOWN + idempotency/reconcile |
| “Bật LOCAL_ONE để khỏi timeout luôn đúng” | Có thể phá consistency guarantee | Cấu hình CL theo RF/nghiệp vụ |
| “Reactive là dùng template sync trong Mono.just” | Blocking đã chạy trước khi Mono được subscribe | ReactiveCassandraOperations hoặc bridge có kiểm soát |
| “CqlSession mới mỗi request an toàn hơn” | Nhiều pools/metadata/prepares và overhead | Session ứng dụng sống dài |
| “BOM Spring Boot hỗ trợ mọi tính năng Cassandra mới” | Mapping/codec/driver patch cũng phải hỗ trợ | Test feature qua dependency tree và integration |

## 16. Câu hỏi và bài tập vận dụng

### Bài 1 — Chọn abstraction

Ứng dụng cần truy vấn theo `job_id` rồi map toàn entity. Nên dùng `CqlSession` trực tiếp cho mọi truy vấn không?

**Đáp án:** không cần. `CassandraOperations.selectOne(Query, JobRow.class)` phù hợp, dễ mapping/test. Dùng raw driver nếu cần metadata/paging/tracing/kiểu dữ liệu mà template không expose thuận tiện.

### Bài 2 — Vì sao Query DSL sinh lỗi?

Code `query(where("status").is("FAILED"))` compile nhưng Cassandra từ chối trên bảng `jobs_by_id(job_id PRIMARY KEY, status)`. Tại sao?

**Đáp án:** predicate không ràng buộc partition key và không có data model/index phù hợp. Template không thay Cassandra query restrictions; tạo bảng theo truy vấn hoặc chỉ mục đã kiểm chứng.

### Bài 3 — Query.limit không có hiệu lực

Developer gọi `q.limit(10); operations.select(q, JobRow.class);` nhưng query vẫn không có LIMIT. Nguyên nhân?

**Đáp án:** `Query` immutable; phải viết `q = q.limit(10)` hoặc dùng Query mới trả về.

### Bài 4 — Kiểm soát consistency

Keyspace RF3 ở dc1, service yêu cầu read-your-writes trong phạm vi local DC. Đội phát triển đổi CL từ `LOCAL_QUORUM` sang `LOCAL_ONE` khi node chậm mà không đánh giá invariant. Điều gì sai?

**Đáp án:** CL thấp hơn có thể trả bản cũ khi replica chưa đồng bộ; phải phân tích yêu cầu nhất quán, RF/repair/availability trước khi đổi.

### Bài 5 — TTL khi retry

Một job được ghi `InsertOptions.ttl(600)`. Sau năm phút, service retry cùng entity và TTL 600. Hạn hết hiệu lực có thể thay đổi thế nào?

**Đáp án:** dữ liệu vừa được ghi lại có thể sống thêm mười phút từ lần retry, gia hạn ngoài ý muốn. Cần deadline tuyệt đối, tính TTL còn lại và idempotency policy.

### Bài 6 — CAS false và timeout

`INSERT IF NOT EXISTS` trả false; ở trường hợp khác cùng request timeout. Có thể xử lý cả hai như `ALREADY_EXISTS` không?

**Đáp án:** không. False là điều kiện không thỏa, còn timeout có thể là unknown outcome (ghi đã commit nhưng ACK mất). Phải phân biệt conflict/reconciliation.

### Bài 7 — Projection thiếu cột

Một endpoint chỉ SELECT `status` rồi ánh xạ thành `JobRow`; sau đó dùng entity ấy để `save()`. Rủi ro?

**Đáp án:** entity thiếu ID/fields và có thể serialize null/ghi đè khi save. Dùng scalar/DTO cho projection, entity đầy đủ cho mutation.

### Bài 8 — WebFlux với template blocking

Service WebFlux viết `return Mono.just(operations.selectOne(q, JobRow.class));`. Đây có phải non-blocking IO?

**Đáp án:** không. `selectOne` đã chạy blocking **trước khi Mono được tạo**. Dùng ReactiveCassandraOperations hoặc bridge qua scheduler bounded với hiểu biết về giới hạn.

### Bài 9 — Pageable giống SQL offset?

Nhóm muốn lấy trang thứ 100.000 bằng offset để nhảy ngay vào Cassandra. Có thể không?

**Đáp án:** Cassandra paging sử dụng state/cursor, không có arbitrary-offset scan rẻ như SQL. Thiết kế keyset pagination theo clustering, paging state và giới hạn query phù hợp.

### Bài 10 — CqlSession khác với template

Khi cần lấy `TTL(last_error)`, `WRITETIME(last_error)` và coordinator để debug, bạn chọn gì?

**Đáp án:** CqlOperations/RowMapper hoặc CqlSession prepared statement với ResultSet/ExecutionInfo để thấy metadata tường minh; không ép CQL function vào entity mapping nếu khiến semantics khó kiểm chứng.

### Checklist hoàn thành bài

- [ ] Phân biệt Repository, CassandraOperations/CassandraTemplate, CqlOperations/CqlTemplate và CqlSession.
- [ ] Biết mapping `@Table`/`@PrimaryKey`/`@Column` và kiểm tra converter.
- [ ] Thiết kế truy vấn gắn partition key/clustering trước khi chọn API.
- [ ] Dùng Query/Criteria và giữ đúng semantics immutable.
- [ ] Không dùng ALLOW FILTERING như default optimization.
- [ ] Biết QueryOptions cho CL, timeout, pageSize, idempotency và execution profile.
- [ ] Phân biệt `LIMIT`, paging và tổng kết quả.
- [ ] Dùng prepared/bind, không nối input vào CQL.
- [ ] Dùng InsertOptions/UpdateOptions với TTL, tránh reset deadline khi retry.
- [ ] Biết update/delete không điều kiện không chứng minh hàng đã tồn tại.
- [ ] Phân biệt LWT wasApplied=false và timeout unknown outcome.
- [ ] Chỉ dùng @Version khi cần optimistic locking/Paxos.
- [ ] Dùng CqlOperations/CqlSession khi cần metadata hoặc CQL tường minh.
- [ ] Không tạo CqlSession mới mỗi HTTP request.
- [ ] Dùng ReactiveCassandraOperations cho reactive stack, không block event loop.
- [ ] Có integration test CQL/schema, RF/CL, paging, TTL, LWT và p95/p99.

## 17. Tài liệu tham khảo

1. Spring Data Cassandra — [Persisting Entities / CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): CassandraOperations, Query/Criteria, mapping, CRUD, optimistic locking.
2. Spring Data Cassandra — [Prepared Statements](https://docs.spring.io/spring-data/cassandra/reference/cassandra/prepared-statements.html): `CassandraTemplate.setUsePreparedStatements`, `CqlTemplate`, bind markers, caching.
3. Spring Data Cassandra — [CassandraOperations API 4.5](https://docs.spring.io/spring-data/cassandra/reference/4.5/api/java/org/springframework/data/cassandra/core/CassandraOperations.html): API select/update/delete/stream/slice/getCqlOperations.
4. Spring Data Cassandra — [QueryOptions.Builder API 4.5](https://docs.spring.io/spring-data/cassandra/reference/4.5/api/java/org/springframework/data/cassandra/core/cql/QueryOptions.QueryOptionsBuilder.html): CL, timeout, pageSize, tracing, idempotency, profile.
5. Spring Data Cassandra — [InsertOptions.Builder API 4.5](https://docs.spring.io/spring-data/cassandra/reference/4.5/api/java/org/springframework/data/cassandra/core/InsertOptions.InsertOptionsBuilder.html): TTL, `IF NOT EXISTS`, write timestamp, serial consistency.
6. Spring Data Cassandra — [Repository Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html): `@Query`, QueryOptions, consistency, limit và allow-filtering constraints.
7. Spring Boot 3.5 — [Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.cassandra.*`, local datacenter, contact-points, keyspace.
8. Spring Boot — [Cassandra auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/data/nosql.html): starter, Spring-managed CqlSession, injection.
9. Apache Cassandra Java Driver 4.19 — [Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/) và [Paging](https://apache.github.io/cassandra-java-driver/4.19.0/core/paging/): bind, routing key, paging state.
10. Apache Cassandra Documentation — [CQL DML](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) và [DDL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): PK, clustering, TTL, LWT, consistency, schema.
11. Apache Cassandra Documentation — [Operations & Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/): replica health, repair/compaction và các chi phí vận hành.
