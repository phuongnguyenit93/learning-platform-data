# Repository, derived query, @Query và giới hạn biểu đạt trong Spring Boot + Spring Data Cassandra

## 1. Mục tiêu và bối cảnh

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**: dữ liệu được đặt lên các replica theo **partition key**, các row trong partition được sắp theo **clustering key**, và coordinator phục vụ truy vấn bằng CQL theo **consistency level** (CL) được chọn. Thiết kế bảng phải đi từ **những truy vấn thực tế**, không từ thói quen chuẩn hóa quan hệ và truy vấn tùy ý.

Khi xây dựng ứng dụng Java với **Spring Boot và Spring Data Cassandra**, bạn có thể khai báo interface repository và để framework sinh ra nhiều câu truy vấn từ tên phương thức. Cách này giảm mã lặp, nhưng **không biến Cassandra thành cơ sở dữ liệu quan hệ**: nếu tên phương thức đòi lọc một cột không có access path hợp lệ, truy vấn có thể bị server từ chối hoặc tốn tài nguyên.

Bài học thuộc chương **Spring Boot và Spring Data** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, tập trung vào:

1. Phân biệt `CassandraRepository`, **derived query**, `@Query`, `CassandraTemplate` và Java Driver.
2. Ánh xạ **composite primary key** đúng giữa CQL và Java.
3. Hiểu khi nào tên phương thức `findBy...` đủ biểu đạt truy vấn và khi nào không.
4. Dùng `@Query` để kiểm soát projection, điều kiện partition/clustering và `LIMIT`.
5. Giải thích giới hạn của **CQL**: không JOIN tùy ý, không WHERE/ORDER BY tùy ý như SQL, không OFFSET paging truyền thống.
6. Kiểm soát phân trang, RF/CL, token routing, TTL, LWT và tải replica.
7. Test generated CQL, theo dõi latency/error, xử lý schema evolution.
8. Biết khi nào nên chuyển sang **CassandraTemplate, CqlTemplate hoặc CqlSession**.

**Phạm vi phiên bản:** mã minh họa hướng tới Spring Boot **3.x / Spring Data Cassandra 4.x** và Java Driver 4.x được quản lý theo dependency/BOM tương thích. Không tự copy property hoặc annotation sang Boot 2.x/Driver 3.x mà không kiểm tra tài liệu của cặp phiên bản đang chạy. Không ấn định số phiên bản mới nhất hay bản phối hợp hỗ trợ chỉ từ tên “4.x”.

## 2. Các tầng làm việc trong ứng dụng

~~~mermaid
flowchart LR
    A["REST / Service"] --> B["Spring Data Repository"]
    B --> C["Spring Data Cassandra mapping / query creation"]
    C --> D["Java Driver CqlSession"]
    D --> E["Coordinator Cassandra"]
    E --> F["Replica theo token, RF, CL"]
    G["CassandraTemplate / CqlTemplate"] --> D
    H["@Query CQL tường minh"] --> C
~~~

| Tầng | Vai trò | Giới hạn |
|---|---|---|
| **Spring Boot auto-configuration** | Tạo cấu hình kết nối, beans và integrations theo starter/version | Không tự quyết định schema hay partition key tốt |
| **`CassandraRepository<T,ID>`** | CRUD, query methods, mapping entity | CRUD tổng quát có thể đắt hoặc không phù hợp với bảng wide-column |
| **Derived query** | Phân tích tên `findBy...` thành điều kiện query | Bị ràng buộc bởi CQL và metadata |
| **`@Query`** | CQL tường minh gắn vào repository method | Vẫn phải tuân thủ partition key/CL/query constraints |
| **`CassandraTemplate`** | API truy vấn và mapping object ở mức thấp hơn repository | Cần chủ động thiết kế query và quản lý tài nguyên |
| **`CqlTemplate` / `CqlSession`** | CQL/driver gần hơn với transport/statement | Nhiều mã và quyết định mapping/paging/timeout |
| **Cassandra cluster** | Hash partition key, đặt replica, compaction/repair, thực thi CL | Không biết tên phương thức repository của Java |

**Quan hệ quan trọng:** Spring Data Repository là *cách gọi CQL*, không phải *cách để bỏ qua giới hạn CQL*.

## 3. Data model của bài: đo lường thiết bị theo ngày

### 3.1. CQL schema dành cho truy vấn thực

Giả sử ứng dụng đọc lịch sử số đo của một thiết bị trong một ngày, theo thời gian mới nhất:

~~~cql
-- Chỉ dùng trên CLUSTER LAB có datacenter dc1 và đủ replica.
CREATE KEYSPACE telemetry_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry_lab.readings_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    reading_value double,
    status text,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Trong bảng này:

- Partition key là **`(device_id, event_day)`**. Hai giá trị cùng nhau xác định logical partition.
- Clustering key là **`event_time`**, sắp row trong partition mới nhất trước.
- Toàn bộ primary key gồm **ba** cột; định danh một row khác với định danh một partition.
- `reading_value` và `status` là cột thường; chúng **không trở thành filter tùy ý** nếu không có index/access path được thiết kế.
- `NetworkTopologyStrategy` và RF=3 là ví dụ lab; topology production cần RF/DC/rack riêng.

### 3.2. Những truy vấn dự kiến

| Nhu cầu | CQL hợp lý theo schema này? | Ghi chú |
|---|---|---|
| Lấy row có device/day/time cụ thể | **Có** | Đủ primary key |
| Lấy các row của device trong một ngày | **Có** | Đủ partition key |
| Lấy 20 row mới nhất của device/day | **Có** | Clustering order DESC và LIMIT |
| Lấy row trong một khoảng event_time của device/day | **Có** | Clustering range trong partition |
| Tìm mọi row theo `status = 'ALERT'` | **Không trực tiếp** | Thiếu partition key/access path, phải đổi mô hình/index phù hợp |
| Tìm mọi thiết bị hoạt động trong 7 ngày | **Không bằng một point query** | Cần bảng phục vụ access pattern, fan-out có giới hạn hoặc pipeline |
| Sắp toàn bộ table theo `reading_value DESC` | **Không như SQL thông thường** | CQL ORDER BY phụ thuộc clustering schema và partition |
| JOIN bảng thiết bị với bảng đo | **Không phải JOIN server-side SQL** | Denormalization/application composition hoặc query-specific tables |

**Mọi ví dụ repository phải được đánh giá trên CQL thực**, không chỉ trên tên phương thức nghe có vẻ hợp lý.

### 3.3. Dữ liệu mẫu

~~~cql
INSERT INTO telemetry_lab.readings_by_device_day
(device_id, event_day, event_time, reading_value, status)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:30:00Z',
    24.6,
    'OK'
);

INSERT INTO telemetry_lab.readings_by_device_day
(device_id, event_day, event_time, reading_value, status)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:29:00Z',
    24.1,
    'OK'
);
~~~

Ví dụ dùng UUID và timestamp cố định trên lab; đừng tạo bảng thật hoặc chạy DDL tự động trong mỗi lần start Spring Boot production.

## 4. Cấu hình Spring Boot an toàn và đúng phiên bản

### 4.1. Dependency theo BOM

Với Spring Boot, thông thường chọn starter Cassandra và **để Spring Boot BOM quản lý phiên bản phù hợp**:

~~~xml
<!-- Trích đoạn pom.xml của project Spring Boot tương thích. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra</artifactId>
</dependency>
~~~

Không pin tùy ý ba version Spring Data, Cassandra Driver và Spring Boot nếu chưa xác minh compatibility matrix. Với **reactive repository**, starter/API có thể khác; đừng nhầm `ReactiveCassandraRepository` với `CassandraRepository` chỉ vì đều truy cập một cluster.

### 4.2. application.yml minh họa

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1:9042
    local-datacenter: dc1
    keyspace-name: telemetry_lab
    schema-action: NONE
~~~

Các property minh họa cho dòng Spring Boot mới dùng namespace `spring.cassandra.*`. Các bản cũ có thể dùng `spring.data.cassandra.*`; **kiểm tra metadata config của Boot version thực**.

- `contact-points` giúp driver bootstrap/khám phá cluster, không có nghĩa mọi request đi tới đó.
- `local-datacenter` phải khớp DC thực sự được driver khám phá.
- `keyspace-name` đặt keyspace mặc định cho các query không ghi fully qualified name.
- `schema-action: NONE` tránh tự tạo hoặc thay schema production khi start service; DBA/migration tool quản lý DDL theo quy trình.
- Auth, TLS, secret và cấu hình timeout phải lấy từ hệ thống quản trị cấu hình; **không commit password, private key hoặc token** vào Git.

### 4.3. Kết nối không thay thế data modeling

Ứng dụng có thể khởi động thành công, repository bean được tạo và health endpoint báo UP, nhưng:

- Một derived method chưa từng gọi có thể gây lỗi khi chạy CQL.
- Bảng có thể chưa tồn tại hoặc schema khác trên cluster đích.
- `findAll()` có thể đọc nhiều partition tốn tài nguyên.
- Query vào một partition nóng có thể timeout dù pool khỏe.
- RF/CL/topology có thể không đáp ứng SLO khi một replica down.

**Smoke test phải thực thi những query shape thực tế**, không chỉ kiểm tra TCP 9042 mở.

## 5. Mapping khóa ghép bằng `@PrimaryKeyClass` và `@PrimaryKeyColumn`

### 5.1. Composite key là một value object

Spring Data Cassandra thường ánh xạ khóa ghép bằng một class có `@PrimaryKeyClass`, từng thành phần dùng `@PrimaryKeyColumn` và entity dùng `@PrimaryKey`.

~~~java
package demo.telemetry;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

@PrimaryKeyClass
public class ReadingKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(
        name = "device_id",
        ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID deviceId;

    @PrimaryKeyColumn(
        name = "event_day",
        ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(
        name = "event_time",
        ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private Instant eventTime;

    public ReadingKey() {}

    public ReadingKey(UUID deviceId, LocalDate eventDay,
                      Instant eventTime) {
        this.deviceId = Objects.requireNonNull(deviceId);
        this.eventDay = Objects.requireNonNull(eventDay);
        this.eventTime = Objects.requireNonNull(eventTime);
    }

    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID value) { deviceId = value; }

    public LocalDate getEventDay() { return eventDay; }
    public void setEventDay(LocalDate value) { eventDay = value; }

    public Instant getEventTime() { return eventTime; }
    public void setEventTime(Instant value) { eventTime = value; }

    @Override
    public boolean equals(Object object) {
        if (this == object) return true;
        if (!(object instanceof ReadingKey other)) return false;
        return Objects.equals(deviceId, other.deviceId)
            && Objects.equals(eventDay, other.eventDay)
            && Objects.equals(eventTime, other.eventTime);
    }

    @Override
    public int hashCode() {
        return Objects.hash(deviceId, eventDay, eventTime);
    }
}
~~~

Ví dụ sử dụng `instanceof ... other` theo Java 16+; nếu JDK thấp hơn, dùng cú pháp Java truyền thống. Chọn JDK theo **ma trận Spring Boot/Driver** hỗ trợ, không nâng JDK chỉ vì snippet.

### 5.2. Tại sao ordinal và type quan trọng?

- `PrimaryKeyType.PARTITIONED` đặt **device_id** và **event_day** vào partition key.
- `PrimaryKeyType.CLUSTERED` đặt **event_time** vào clustering key.
- `ordinal` và `Ordering.DESCENDING` phải khớp **định nghĩa CQL**.
- Java `UUID` / `LocalDate` / `Instant` phải tương thích kiểu CQL `uuid` / `date` / `timestamp`.
- `equals/hashCode` cần phù hợp giá trị khóa để DTO/domain hoạt động ổn định.

**Một lỗi ở annotation primary key có thể dẫn đến generated CQL sai hoặc mapping sai**, dù Java class compile được. Luôn xác minh schema và integration test trên cluster tương thích.

### 5.3. Entity mapping

~~~java
package demo.telemetry;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("readings_by_device_day")
public class Reading {

    @PrimaryKey
    private ReadingKey key;

    @Column("reading_value")
    private Double readingValue;

    @Column("status")
    private String status;

    public Reading() {}

    public Reading(ReadingKey key, Double readingValue, String status) {
        this.key = key;
        this.readingValue = readingValue;
        this.status = status;
    }

    public ReadingKey getKey() { return key; }
    public void setKey(ReadingKey value) { key = value; }

    public Double getReadingValue() { return readingValue; }
    public void setReadingValue(Double value) { readingValue = value; }

    public String getStatus() { return status; }
    public void setStatus(String value) { status = value; }
}
~~~

Dùng `Double` cho dữ liệu đo có thể thiếu để phân biệt **không có giá trị** với `0.0`. Không nhất thiết mọi field đều được ghi cho mọi row lịch sử.

### 5.4. Khóa dùng cho `findById` là **toàn bộ primary key**

~~~java
ReadingKey key = new ReadingKey(deviceId, day, eventTime);
Optional<Reading> found = repository.findById(key);
~~~

`findById(key)` tìm **một row có đúng ba thành phần primary key**, không có nghĩa tìm tất cả row trong partition của một ngày. Nếu API cần “20 giá trị mới nhất”, hãy viết một query theo `device_id` và `event_day` có `LIMIT 20`.

## 6. `CassandraRepository`: CRUD thuận tiện nhưng phải biết chi phí

### 6.1. Repository interface

~~~java
package demo.telemetry;

import org.springframework.data.cassandra.repository.CassandraRepository;

public interface ReadingRepository
        extends CassandraRepository<Reading, ReadingKey> {
}
~~~

Thông qua Spring Data, repository cung cấp các thao tác như `save`, `findById`, `existsById`, `deleteById`, `findAll` (tùy superinterface và version).

Nhưng **API tồn tại không có nghĩa hợp lý để gọi trên một bảng lớn**.

| Phương thức | Phù hợp khi | Rủi ro cần nhớ |
|---|---|---|
| `save(entity)` | Ghi row có primary key xác định | Cassandra upsert, timestamp/TTL/null semantics |
| `findById(fullKey)` | Tìm đúng một row | Phải cung cấp **đủ** partition+clustering keys |
| `existsById(fullKey)` | Kiểm tra hiện diện row cụ thể | Có chi phí đọc; không thay uniqueness txn |
| `deleteById(fullKey)` | Xóa một row theo ID đầy đủ | Tombstone, gc_grace_seconds và update cạnh tranh |
| `findAll()` | Chỉ khi dataset nhỏ/thử nghiệm đặc biệt | Có thể quét rộng nhiều partition |
| `count()` | Bảng nhỏ hoặc batch offline có kiểm soát | Không phải cách rẻ để đếm toàn cluster |
| `deleteAll()` | Tình huống admin/lab có kiểm soát | Nguy hiểm, có thể phát sinh rất nhiều mutations/tombstones |

Đừng dùng `findAll().stream().filter(...)` thay WHERE của Cassandra. Dữ liệu có thể được chuyển về client trước khi lọc, làm API OOM và tạo scan ảnh hưởng nhiều replica.

### 6.2. `save` không phải SQL transaction nhiều bảng

Trong Cassandra, `save` thường gắn với mutation/upsert theo primary key. Nó không đảm bảo:

- Atomic transaction xuyên nhiều partition/bảng như RDBMS.
- Unique constraint trên một cột thường.
- Isolation snapshot của chuỗi nhiều repository calls.
- CAS/LWT mặc định cho mọi mutation.
- “Lỗi timeout nghĩa là mutation chắc chắn chưa ghi”.

Khi cần nghiệp vụ điều kiện, phải thiết kế **conditional write/LWT hoặc version/invariant** phù hợp và đánh giá latency. Repository abstraction không tự tạo cơ chế đồng thuận ngoài Cassandra.

### 6.3. Vì sao key design quyết định repository design?

Đối với `PRIMARY KEY ((device_id, event_day), event_time)`:

- `findById` là full-row lookup.
- Đọc theo `device_id + event_day` là partition lookup.
- Đọc theo `device_id` đơn lẻ **không định vị được một partition**.
- Đọc theo `status` sẽ cần access path khác; chỉ thêm `findByStatus` trong Java không làm Cassandra có index đó.

Thiết kế interface **sau khi** mô hình hóa truy vấn là quy trình đúng, không thiết kế hàng trăm `findBy...` rồi ép schema chạy theo.

## 7. Derived query: từ tên phương thức sang CQL

### 7.1. Nguyên tắc

Spring Data phân tích tên như `findByKeyDeviceIdAndKeyEventDay` thành **property path** trên entity và tạo query cho những biểu thức được hỗ trợ bởi module Cassandra.

Ví dụ:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

public interface ReadingRepository
        extends CassandraRepository<Reading, ReadingKey> {

    // Sử dụng property path lồng trong trường "key".
    // Chỉ minh họa trên partition nhỏ / lab; kết quả chưa giới hạn.
    List<Reading> findByKeyDeviceIdAndKeyEventDay(
        UUID deviceId, LocalDate eventDay);
}
~~~

Dự kiến theo ý nghĩa:

~~~cql
-- Dạng CQL tương đương về mặt mục tiêu:
SELECT *
FROM telemetry_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?;
~~~

**Tên phương thức và cú pháp nested properties cần được xác minh bằng integration test trên phiên bản Spring Data thực tế**. Nếu parser không hiểu property path hoặc generated CQL không đúng key layout, có thể dùng `@Query` tường minh thay vì suy đoán.

### 7.2. Tên dài không tự làm query rẻ

Phương thức trên có thể đọc **tất cả row trong partition ngày**. Nếu thiết bị tạo một triệu số đo/ngày, `List<Reading>` có thể chiếm bộ nhớ lớn dù query chỉ có một partition.

Derived query không tự biết API chỉ cần 20 row. Hãy cân nhắc `@Query` có `LIMIT` hoặc phân trang Cassandra được hỗ trợ.

### 7.3. Phân biệt property path với tên cột CQL

Trong Java entity:

- `Reading.key.deviceId` → cột CQL `device_id`.
- `Reading.key.eventDay` → `event_day`.
- `Reading.key.eventTime` → `event_time`.
- `Reading.readingValue` → `reading_value`.

Tên method derived dùng **tên property Java**, không dùng trực tiếp snake_case CQL trong chữ ký như `findByDevice_id`. Mapping annotations quyết định cột thực.

Nếu property path có tên trùng hoặc parser không xác định đúng đoạn ghép, có thể phải dùng cơ chế chỉ định nested path theo Spring Data version hoặc viết `@Query` để loại bỏ sự mơ hồ.

### 7.4. Hãy kiểm thử CQL sinh ra

Không kết luận một derived method đúng chỉ vì project compile:

1. Bean repository có được khởi tạo không?
2. Phương thức được gọi có tạo CQL hợp lệ không?
3. CQL có **đủ partition key** và đúng clustering order không?
4. Query có phân trang/giới hạn row không?
5. Latency và số row thực tế ở partition lớn ra sao?
6. Có phải query bị server yêu cầu `ALLOW FILTERING` không?
7. Kết quả có đúng theo RF/CL dự kiến không?

**Lỗi runtime** xảy ra khi gọi phương thức cần được quan sát bằng integration test và logs an toàn, không chỉ đơn vị test mock repository.

## 8. `@Query`: biểu đạt CQL rõ hơn tên hàm

### 8.1. Giới hạn 20 row ở server

~~~java
import org.springframework.data.cassandra.repository.Query;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

public interface ReadingRepository
        extends CassandraRepository<Reading, ReadingKey> {

    @Query(
        "SELECT device_id, event_day, event_time, " +
        "reading_value, status " +
        "FROM readings_by_device_day " +
        "WHERE device_id = ?0 AND event_day = ?1 LIMIT 20")
    List<Reading> findLatest20(UUID deviceId, LocalDate eventDay);
}
~~~

Ở đây:

- `?0` và `?1` là **tham số ràng buộc theo chỉ số của Spring Data Cassandra** trong `@Query` cho các version hỗ trợ syntax này.
- Chúng phải ánh xạ đúng `UUID` và `LocalDate`.
- Câu CQL có đầy đủ partition key và **`LIMIT 20`**.
- Table có clustering order `event_time DESC`, nên kết quả trong partition theo thứ tự đã khai báo.
- Projection trả đủ key columns và field để mapper tạo `Reading`.

**Đừng ghép deviceId/day vào query string**. Cần dùng bind parameters; raw interpolation làm tăng rủi ro CQL injection và có thể mất lợi ích prepare/routing metadata.

### 8.2. Range theo clustering key

~~~java
import java.time.Instant;

@Query(
    "SELECT device_id, event_day, event_time, " +
    "reading_value, status " +
    "FROM readings_by_device_day " +
    "WHERE device_id = ?0 AND event_day = ?1 " +
    "AND event_time < ?2 LIMIT 50")
List<Reading> before(
    UUID deviceId, LocalDate day, Instant exclusiveBefore);
~~~

Một CQL query tương đương:

~~~cql
SELECT device_id, event_day, event_time, reading_value, status
FROM telemetry_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time < ?
LIMIT 50;
~~~

`event_time` là clustering column; range restriction trong **partition đã biết** phù hợp mô hình này. Với một bảng có nhiều clustering columns, thứ tự/ràng buộc CQL có quy tắc chặt hơn; không sao chép điều kiện range sang bất kỳ cột nào.

### 8.3. `@Query` không bypass CQL server

Đổi từ derived query sang:

~~~java
// ANTI-PATTERN: @Query tường minh nhưng query shape vẫn sai.
@Query("SELECT * FROM readings_by_device_day WHERE status = ?0")
List<Reading> findAllAlerts(String status);
~~~

**Không làm câu query trở nên hợp lệ hoặc hiệu quả** chỉ vì Java có annotation. Cassandra vẫn cần partition key hoặc một access path hỗ trợ được thiết kế và xác minh. `ALLOW FILTERING` không phải lời giải mặc định: nó có thể biến thành scan rộng và gây timeout.

### 8.4. Vì sao không nên mặc định `SELECT *`?

- Tải thêm field không dùng vào network/heap.
- Mapping phụ thuộc schema evolution; cột mới có thể chưa có dữ liệu ở row cũ.
- Một số collection/blob/UDT rất lớn làm response nặng.
- Khó phát hiện query contract nào đang dùng cột nào.
- Tăng chi phí serialization, GC và tổng số bytes khi paging.

Ưu tiên projection tường minh cho API có hợp đồng DTO ổn định. Nếu entity mapping đòi primary key và các cột khác, phải chọn **đủ những cột cần thiết**.

## 9. Bản chất của giới hạn biểu đạt: Spring Data không biến CQL thành SQL

### 9.1. Điều kiện WHERE phải hợp với key

| Nhu cầu Java | CQL có đường thực thi không? | Giải pháp phù hợp |
|---|---|---|
| `deviceId = ? AND eventDay = ?` | Có một partition rõ | Derived query hoặc `@Query` |
| `deviceId = ? AND eventDay = ? AND eventTime < ?` | Có clustering range | `@Query`/derived chỉ khi operator hỗ trợ |
| Chỉ có `deviceId` | Không đủ partition key của bảng ví dụ | Query-specific table, thay access pattern |
| Chỉ có `status` | Không đủ partition key | Bảng theo status hoặc index đã đánh giá |
| `status = 'ALERT' OR status = 'WARN'` | Không hỗ trợ OR tùy ý như SQL | Thiết kế bảng/index/aggregation theo truy vấn |
| JOIN hai bảng Cassandra | Không phải chức năng CQL JOIN | Denormalize/application-layer composition |
| Sắp theo reading value toàn bảng | Không phù hợp clustering order | Bảng khác hoặc analytics/index/search phù hợp |
| OFFSET 1.000.000 | Cassandra không có SQL OFFSET server-side thông thường | Paging state hoặc keyset/partition design |
| Chạy COUNT toàn bộ table liên tục | Có thể rất tốn tài nguyên | Counter/bảng tổng hợp/metrics với semantics rõ |

**Một derived method dài như `findByStatusOrReadingValueGreaterThan` không khiến Cassandra tạo execution plan tối ưu như RDBMS.** Hãy kiểm tra trước các toán tử thực sự được Spring Data Cassandra support ở bản đang dùng; ngay cả query được parser chấp nhận cũng phải tuân thủ key restrictions.

### 9.2. `ORDER BY` bị ràng buộc bởi clustering columns

Bảng ví dụ đã lưu `event_time DESC` trong mỗi partition. Đọc từ mới tới cũ là access pattern tự nhiên. Nhưng không thể dùng `Sort.by("status")` rồi tin framework sẽ tự sắp **toàn cluster** tại server.

Nếu API muốn “top 100 thiết bị có số đo cao nhất toàn hệ thống”, cần **bảng phục vụ truy vấn khác hoặc hệ thống tổng hợp/analytics thích hợp**. Một trường Java `Sort` không tạo global sort index.

### 9.3. Thêm index không tự cứu mọi derived query

Các kiểu index (ví dụ secondary index, SAI khi phiên bản hỗ trợ) có đặc điểm khác nhau về dữ liệu, truy vấn, write amplification và load. Không nên:

1. Viết `findByStatus` không có partition key.
2. Gặp lỗi.
3. Tự tạo index trên status ở production.
4. Mặc định query sẽ hiệu quả ở hàng tỷ row.

Hãy đánh giá **cardinality, selectivity, data distribution, RF/DC, query fanout, index build/maintenance, compaction** và phiên bản Cassandra trước khi quyết định. Với lookup nghiệp vụ cố định, một bảng denormalized theo query có thể dễ dự đoán hơn.

## 10. Phân trang: `Pageable` không đồng nghĩa SQL OFFSET

### 10.1. Vì sao Cassandra paging khác RDBMS?

Cassandra có paging dựa trên state/continuation thay vì random offset trên tập dữ liệu toàn cluster. Một API dạng:

~~~text
GET /readings?device=...&day=...&page=500000
~~~

không có nghĩa server Cassandra có thể bỏ qua 500.000 trang với chi phí nhỏ. Khi dùng Spring Data Cassandra:

- `Pageable` và `Slice` có thể được hỗ trợ theo phiên bản và loại query.
- Việc tiếp tục thường dựa trên **paging state/continuation**, không phải SQL `OFFSET`.
- Không mặc định nhảy thẳng đến arbitrary page N là thao tác rẻ/hợp lệ.
- Cần kiểm tra support thực tế đối với sorting, paging state và mapping theo driver version.
- `Page` thường cần ý nghĩa total count; Cassandra không thể đếm toàn bộ tập rộng rẻ như một số RDBMS. `Slice` thường phù hợp hơn cho “có trang tiếp”.

### 10.2. Mẫu repository có Slice

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

Slice<Reading> findByKeyDeviceIdAndKeyEventDay(
    UUID deviceId,
    LocalDate day,
    Pageable pageable);
~~~

Đây là ví dụ interface cho phiên bản Spring Data Cassandra **có hỗ trợ Slice/paging tương ứng**. Hãy kiểm tra API `CassandraPageRequest` hoặc kiểu paging token của phiên bản để lấy **trang kế**; đừng dùng `PageRequest.of(1000, 20)` và suy nó sẽ skip offset đúng như SQL.

### 10.3. LIMIT và fetch size phục vụ hai mục tiêu

~~~text
CQL LIMIT 20:
    Giới hạn tổng row mà query có thể trả.

Page/fetch size = 20:
    Giới hạn mục tiêu row mỗi page,
    KHÔNG giới hạn tổng số row của query nếu không có LIMIT.
~~~

Ngay cả khi mỗi page nhỏ, một query quét partition rộng hoặc nhiều tombstone vẫn có thể làm server quá tải. Page size không thay thế query modeling.

### 10.4. Không đưa paging state thô ra mọi nơi

Paging state có thể chứa thông tin nhạy cảm về vị trí truy vấn. Khi cần dùng như API cursor:

- Cần ràng buộc cursor với query shape/partition/filter.
- Có expiration/versioning và integrity protection nếu ra client không tin cậy.
- Không log raw paging token như request ID.
- Không tin paging state là **snapshot giao dịch** khi dữ liệu thay đổi giữa các page.
- Không giả định token cũ tương thích vô thời hạn sau nâng driver/schema.

## 11. Tối ưu query từ repository phải bắt đầu từ partition key

### 11.1. Điều kiện tốt

~~~cql
SELECT device_id, event_day, event_time,
       reading_value, status
FROM telemetry_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 20;
~~~

Driver có thể suy ra routing key từ đầy đủ partition key và metadata của prepared statement. Coordinator thường ưu tiên replica phù hợp trong local DC theo load balancing, nhưng không bảo đảm luôn không có extra network hop.

### 11.2. Điều kiện gây scan

~~~cql
-- Không phù hợp bảng demo nếu không có access path khác.
SELECT * FROM telemetry_lab.readings_by_device_day
WHERE status = 'OK';
~~~

Cassandra có thể từ chối hoặc yêu cầu một cách truy cập khác. Đừng thêm `ALLOW FILTERING` để che vấn đề thiết kế; khi dữ liệu lớn, phần server scan có thể chiếm CPU/I/O cao hơn mọi tối ưu Java.

### 11.3. Wide partition vẫn đắt dù routing đúng

Một ngày của một thiết bị có thể chứa hàng triệu row. Query “đủ partition key” vẫn có thể:

- Chạm nhiều SSTable trước compaction.
- Quét nhiều tombstone/TTL hết hạn.
- Tạo nhiều page, response bytes và client allocations.
- Khi retry tăng, làm load tập replica ấy cao hơn.

Giải pháp thường là **bucket nhỏ hơn, giới hạn thời gian, LIMIT, retention/TTL và workload test**, không chỉ đổi `List` sang `Slice`.

## 12. Khi nào cần `CassandraTemplate` thay vì repository?

### 12.1. Đường quyết định

~~~mermaid
flowchart TD
    A["Use case đọc/ghi Cassandra"] --> B{"Truy vấn đơn giản, key đúng?"}
    B -->|Có| C["CassandraRepository + derived query"]
    B -->|Không cần quá phức tạp| D["Repository @Query CQL tường minh"]
    B -->|Cần option/logic động có kiểm soát| E["CassandraTemplate / CqlTemplate"]
    E --> F{"Cần driver-level execution detail?"}
    F -->|Có| G["CqlSession prepared/bound statement"]
    F -->|Không| H["Spring mapping/template"]
    C --> I["Integration test CQL + replica load"]
    D --> I
    G --> I
    H --> I
~~~

Repository và template không phải hai engine cơ sở dữ liệu; cùng truy cập Cassandra qua driver và phải tuân thủ CQL.

### 12.2. Khi template hữu ích

- Truy vấn động trong **tập allowlist đã kiểm soát**.
- Cần áp dụng option câu lệnh/kết quả không diễn đạt tốt bằng repository method.
- Cần kết hợp nhiều query steps với mapping object chuyên dụng.
- Cần đọc dữ liệu theo token range cho job có throttle/checkpoint.
- Muốn tái sử dụng lớp mapping mà không viết hàng trăm tên derived.
- Đọc/ghi có TTL/timestamp/conditional behavior cần cấu hình rõ theo version.

Tuy nhiên **template cũng không thêm JOIN hay global ORDER BY cho CQL**. Nếu query không phù hợp schema, phải **đổi thiết kế bảng/luồng dữ liệu**, không chỉ đổi API Java.

### 12.3. Khi cần `CqlSession` trực tiếp

Một ví dụ Java Driver 4.x:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.LocalDate;
import java.util.UUID;

public final class ReadingCqlGateway {
    private final CqlSession session;
    private final PreparedStatement latest;

    public ReadingCqlGateway(CqlSession session) {
        this.session = session;
        this.latest = session.prepare(
            "SELECT event_time, reading_value, status " +
            "FROM telemetry_lab.readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT 20"
        );
    }

    public ResultSet fetch(UUID deviceId, LocalDate day) {
        BoundStatement bound = latest.bind(deviceId, day)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(20);
        return session.execute(bound);
    }
}
~~~

**CqlSession** cho phép kiểm soát statement/CL/page size và đọc execution info. Nhưng đừng để controller truyền raw user input thành CQL string; `PreparedStatement` + typed bind values là mặc định an toàn.

Khi dùng driver trực tiếp, tầng application cần chủ động mapping `Row`, null handling, paging và retry semantics. Với Spring repository, một phần mã này đã được abstraction xử lý, nhưng chi phí truy vấn không tự biến mất.

## 13. `@Query`, bind parameters và định danh động

### 13.1. Giá trị được bind khác tên bảng hoặc cột

Cách dùng `@Query` an toàn là ràng buộc **giá trị dữ liệu**:

~~~java
@Query(
    "SELECT device_id, event_day, event_time, " +
    "reading_value, status " +
    "FROM readings_by_device_day " +
    "WHERE device_id = ?0 AND event_day = ?1 LIMIT 20")
List<Reading> findLatest20(UUID deviceId, LocalDate day);
~~~

`device_id`, `event_day` và `readings_by_device_day` là **định danh CQL cố định** trong query template. `?0` và `?1` là các giá trị bind.

Không dùng tham số bind để thay đổi **tên bảng, keyspace, cột hoặc cấu trúc ORDER BY**:

~~~text
CQL identifier:
    table_name, column_name, keyspace, ORDER BY column

CQL value:
    UUID, LocalDate, Instant, number, text

Bind parameter áp dụng cho VALUE theo syntax được hỗ trợ;
không biến tên bảng/cột thành giá trị bind.
~~~

Nếu ứng dụng có nhiều bảng theo tenant/loại sản phẩm, **không** lấy tên bảng từ query string của HTTP request rồi nối thẳng thành CQL.

### 13.2. Khi bắt buộc chọn một bảng trong vài bảng cho phép

Thay vì nối raw input, dùng **allowlist cấu trúc** được review:

~~~java
public enum ReadingView {
    BY_DEVICE_DAY,
    BY_ALERT_DAY
}
~~~

Trong tầng truy vấn, ánh xạ mỗi enum sang **một template CQL cố định** và một repository/gateway tương ứng. Không tạo `@Query` có một tên table bất kỳ từ input không tin cậy.

Nếu bảng thay đổi theo tenant, cần đánh giá cả **multi-tenant isolation, RBAC, connection/session lifecycle và số lượng schema objects**. Không coi phép kiểm tra regex tên table là đủ để cấp quyền truy cập.

### 13.3. `@Query` không biến Spring Data thành SQL ORM

Đừng viết:

~~~java
// KHÔNG phải cách lấy global sort trên Cassandra.
@Query(
    "SELECT * FROM readings_by_device_day " +
    "WHERE reading_value > ?0 ORDER BY status ASC")
List<Reading> globalSort(double threshold);
~~~

CQL không hỗ trợ truy vấn này như SQL tùy ý trên bảng mẫu. `@Query` gửi CQL; server vẫn thực thi luật partition/clustering/index của Cassandra.

### 13.4. Tránh nối raw CQL vào `@Query` tại runtime

`@Query` annotation có nội dung tĩnh. Nếu cần query động với nhiều điều kiện tùy chọn, cân nhắc:

- Một số query templates định danh rõ theo access pattern.
- `CassandraTemplate` với điều kiện được xây dựng trong tập hợp được phép.
- `CqlSession` prepared statements với các query shapes cố định.
- Bảng chuyên biệt/index phù hợp cho access pattern mới.

Không chuyển sang string concatenation chỉ vì derived method quá dài hoặc `@Query` khó viết. Điều này thường giải quyết nhầm vấn đề: **CQL data model** chứ không phải Java syntax.

## 14. CRUD mutation, TTL và thời điểm ghi

### 14.1. Save theo full primary key là upsert

~~~java
ReadingKey key =
    new ReadingKey(deviceId, day, eventTime);

Reading reading = new Reading(key, 24.6, "OK");
repository.save(reading);
~~~

Khi ghi cùng key, Cassandra dùng mutation timestamp và reconciliation rules. Nó không vận hành như JPA entity manager với **dirty checking, transaction context và rollback tự động** của một RDBMS.

Đặc biệt:

- Hai ghi cùng primary key có thể **overwrite/merge cell** theo timestamp.
- Một số field null có thể được xử lý theo chiến lược mapping/write options của phiên bản; không giả định mọi null luôn “không ghi gì” hoặc luôn “xóa cell” nếu chưa test.
- Ghi vào hai bảng bằng hai `save` không phải giao dịch ACID đa bảng.
- Timeout không chứng minh mutation chưa được áp dụng.
- Ghi lặp chỉ an toàn khi đã đánh giá **idempotency**.

### 14.2. TTL được đặt trong mutation, không tự sinh từ repository

Ví dụ CQL:

~~~cql
INSERT INTO telemetry_lab.readings_by_device_day
(device_id, event_day, event_time, reading_value, status)
VALUES (?, ?, ?, ?, ?)
USING TTL 86400;
~~~

TTL `86400` giây trong ví dụ là **một ngày**, không phải cấu hình mặc định. Nếu dữ liệu cần giữ 30 ngày, hãy có policy riêng. TTL ảnh hưởng thời điểm row/cell hết hạn, tombstone và compaction, đồng thời có thể làm semantics retry phức tạp hơn.

Khi cần set TTL/timestamp cho từng request, hãy dùng option của **Spring Data Cassandra template** hoặc driver CQL theo phiên bản đã được xác minh. Không mặc định `repository.save()` cho phép tùy biến mọi option CQL bằng cùng một signature.

### 14.3. DELETE và tombstone

~~~java
repository.deleteById(new ReadingKey(deviceId, day, eventTime));
~~~

Xóa trong Cassandra thường tạo tombstone để replica học về deletion theo quy tắc consistency/repair. **Không** kết luận xóa một row sẽ giảm disk usage ngay lập tức; tombstone có thể tồn tại đến khi compaction và các điều kiện an toàn liên quan.

Hệ quả:

- Không lặp delete với timestamp mới khi concurrent writes chưa được đánh giá.
- Không dựa trên `deleteById` như một transaction rollback cho nhiều repository calls.
- Theo dõi tombstone read amplification nếu delete/TTL rất nhiều.

## 15. LWT, conditional writes và tính nhất quán nghiệp vụ

### 15.1. Không nhầm `save` với `IF NOT EXISTS`

Một yêu cầu “chỉ chèn nếu chưa có bản ghi” **không tương đương** `repository.save(reading)`. CQL có conditional write:

~~~cql
INSERT INTO telemetry_lab.readings_by_device_day
(device_id, event_day, event_time, reading_value, status)
VALUES (?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

LWT có thêm chi phí đồng thuận/Paxos và semantics riêng; không dùng cho mọi INSERT chỉ để có boolean “thành công”. Khi dùng driver, có thể kiểm tra `ResultSet.wasApplied()` cho câu conditional phù hợp.

Trong Spring Data Cassandra, support conditional operations và cách nhận kết quả có thể khác giữa repository, template và driver; **kiểm tra API/version**. Nếu ứng dụng cần quan sát `[applied]` chính xác, `CqlSession` hoặc template có hỗ trợ điều kiện rõ ràng thường dễ kiểm chứng hơn một `save` thông thường.

### 15.2. Có thể bị timeout sau khi LWT đã áp dụng

Giả sử lần đầu `IF NOT EXISTS` đã tạo row nhưng client timeout. Khi retry, câu lệnh có thể trả `wasApplied() == false` vì row nay đã tồn tại. **Điều đó không chứng minh lần đầu thất bại**.

Cần:

1. Identity của logical operation ổn định.
2. Đối soát giá trị hiện hữu và invariant.
3. Retry budget và timeout hợp lý.
4. Không phát lại side effect bên ngoài một cách mù quáng.

### 15.3. Consistency level là thiết kế dữ liệu, không phải annotation làm đẹp

| CL | Ý nghĩa khái quát khi RF=3 ở một DC | Tác động |
|---|---|---|
| `ONE` | Cần một replica phản hồi phù hợp | Ít ACK hơn nhưng không có bảo đảm quorum |
| `LOCAL_QUORUM` | Quorum local DC, tức 2/3 ở ví dụ | Cân bằng consistency/availability theo topology |
| `ALL` | Mọi replica liên quan | Nhạy với node lỗi/chậm |
| `EACH_QUORUM` | Với thao tác ghi được hỗ trợ, quorum theo từng DC | Chi phí/availability phức tạp hơn |

**Không chọn CL chỉ vì một derived method chậm.** Nếu ứng dụng dùng consistency profile, phải kiểm chứng policy trong Spring Data/driver, RF và tên datacenter theo release hiện tại. `LOCAL_QUORUM` ở dc1 không bảo đảm quorum ở dc2 đã ACK khi trả success.

### 15.4. Lớp nào cấu hình CL?

Có các đường tích hợp khác nhau:

- Driver execution profile/session defaults.
- Statement-level consistency khi dùng `CqlSession`.
- Operation/query options ở `CassandraTemplate` nếu phiên bản hỗ trợ.
- Cơ chế annotation/options của Spring Data theo phiên bản.

Không tự khẳng định mọi phương thức repository đều có thể gắn một annotation CL cùng tên trên mọi Spring Data version. **Integration test và driver telemetry** phải chứng minh consistency thực tế, đặc biệt với đọc/ghi quan trọng.

## 16. Spring Data Cassandra imperative và reactive khác nhau

### 16.1. Hai loại repository

Imperative repository:

~~~java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface ReadingRepository
        extends CassandraRepository<Reading, ReadingKey> {
}
~~~

Reactive repository (nếu starter/driver/framework hỗ trợ):

~~~java
import org.springframework.data.cassandra.repository.ReactiveCassandraRepository;
import reactor.core.publisher.Flux;

public interface ReactiveReadingRepository
        extends ReactiveCassandraRepository<Reading, ReadingKey> {

    // Signature được kiểm chứng theo Spring Data Cassandra version.
    Flux<Reading> findByKeyDeviceIdAndKeyEventDay(
        UUID deviceId, LocalDate eventDay);
}
~~~

Hai ví dụ là **lựa chọn kiến trúc**, không phải yêu cầu tạo cả hai interface cùng tên/bean rồi inject tùy tiện trong một ứng dụng. Trong code thực, đặt tên rõ và xác minh auto-configuration/scanning của repository type được sử dụng.

### 16.2. Reactive không làm CQL trở thành truy vấn streaming vô hạn

Khi một reactive repository trả `Flux<Reading>`:

- Query vẫn chạy qua Cassandra và tuân thủ partition key/CL.
- Paging và backpressure có thể hỗ trợ quản lý bộ nhớ, tùy stack.
- `Flux` không phải CDC stream tự phát row mới mãi mãi.
- `Flux.collectList()` vẫn có thể gom toàn bộ partition vào heap.
- Mỗi subscription/retry có thể tạo query mới tùy semantics Publisher.
- Cancellation không hoàn tác mutation đã được replica áp dụng.

Chỉ chuyển sang reactive nếu **toàn bộ pipeline có thể xử lý nonblocking và bounded concurrency**. Đừng bọc reactive trong `block()` trên WebFlux event loop; nếu service đồng bộ, imperative repository có thể phù hợp hơn.

### 16.3. Derived query giới hạn giống nhau ở phần server

Một phương thức reactive `findByStatus(...)` không bỗng trở thành truy vấn hợp lệ nếu imperative `findByStatus(...)` không có access path. **Reactive chỉ thay đổi cách nhận kết quả**, không thay luật CQL.

## 17. Schema migration và rolling deployment

### 17.1. Tránh để ứng dụng tự ý recreate schema

Trong production, nên tách:

1. Định nghĩa CQL được review.
2. Thay đổi schema có kế hoạch, kiểm tra **schema agreement**.
3. Triển khai ứng dụng có khả năng đọc schema cũ/mới nếu cần.
4. Backfill dữ liệu khi đổi partition key hoặc query-specific table.
5. Đối soát trước khi chuyển reads.
6. Thu hồi bảng cũ sau retention/rollback window.

Đổi từ `PRIMARY KEY ((device_id, event_day), event_time)` sang kiểu partition khác **không phải chỉ sửa `@PrimaryKeyColumn` trong entity**. Cassandra không tự viết lại toàn bộ dữ liệu theo token mới chỉ vì Java class thay đổi.

### 17.2. Expand / contract với field mới

Ví dụ thêm cột thường:

~~~cql
-- Chạy theo change process và kiểm tra phiên bản CQL.
ALTER TABLE telemetry_lab.readings_by_device_day
ADD quality text;
~~~

Sau đó:

- Code cũ có thể không biết `quality`, nhưng query cũ vẫn phải được kiểm thử.
- Row lịch sử có thể có `quality = null`.
- Code mới không được assume mọi row đều có quality hợp lệ.
- Nếu query thêm `WHERE quality = 'GOOD'`, việc thêm cột **không tự tạo index/access path**.
- Nếu `quality` cần là một phần partition key, phải tạo bảng mới và migration.

### 17.3. Đổi query shape có thể cần bảng mới

Nếu hệ thống bắt đầu cần “10 thiết bị cảnh báo mới nhất trong một site”, bảng `readings_by_device_day` không được thiết kế để trả lời trực tiếp. Có thể tạo bảng thứ hai:

~~~cql
-- Chỉ là ví dụ access pattern; kiểm tra cardinality/bucketing.
CREATE TABLE telemetry_lab.alerts_by_site_day (
    site_id uuid,
    alert_day date,
    event_time timestamp,
    device_id uuid,
    message text,
    PRIMARY KEY ((site_id, alert_day), event_time, device_id)
) WITH CLUSTERING ORDER BY (
    event_time DESC, device_id ASC
);
~~~

Ứng dụng có thể dual-write hoặc phát event tới writer cho bảng mới, **nhưng hai ghi không trở thành giao dịch ACID nhiều bảng**. Cần idempotency, đối soát/backfill và rollback plan.

### 17.4. Compaction và dung lượng trong migration

Khi giữ cả bảng cũ lẫn bảng mới:

- Dung lượng physical tăng theo RF, nén, token distribution.
- Memtable flush sinh SSTable mới.
- Compaction cần I/O và dung lượng tạm.
- Repair/streaming có thể cạnh tranh resource.
- Backfill không được dùng repository `findAll()` để quét vô hạn.
- Phải dùng token ranges/partition work items, checkpoint và rate/bytes limits theo kế hoạch.

Spring Data repository giúp code sạch hơn, nhưng không tự điều tiết hệ số replication, write amplification hoặc disk headroom.

## 18. Kiểm thử repository trên Cassandra thật, không chỉ mock

### 18.1. Vì sao mock không đủ?

Một unit test kiểu `when(repository.findLatest20(...)).thenReturn(...)` chỉ chứng minh **service xử lý dữ liệu giả đúng**. Nó không chứng minh:

- Tên property derived được Spring Data parser hiểu đúng.
- CQL do `@Query` sinh ra hợp lệ theo version CQL/server.
- Composite key mapping giữ đúng thứ tự và type.
- Cassandra có thể phục vụ `WHERE` mà không cần scan rộng.
- `LIMIT`, sorting trong partition, null và paging hoạt động đúng.
- Local DC, RF và CL đáp ứng tính đúng đã thiết kế.

Hãy giữ unit tests cho business logic, và tạo **integration tests kết nối Cassandra lab** để kiểm tra mapper, repository và query execution thật.

### 18.2. Kiểm thử với `@DataCassandraTest`

Ví dụ định hướng cho project đã cấu hình một Cassandra test instance hoặc Testcontainers bằng hạ tầng kiểm thử riêng:

~~~java
package demo.telemetry;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.cassandra.DataCassandraTest;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@DataCassandraTest
class ReadingRepositoryIntegrationTest {

    @Autowired
    ReadingRepository repository;

    @Test
    void queryByFullPartitionKeyAndLimit() {
        UUID device = UUID.randomUUID();
        LocalDate day = LocalDate.of(2026, 11, 21);
        Instant older = Instant.parse("2026-11-21T09:00:00Z");
        Instant newer = Instant.parse("2026-11-21T10:00:00Z");

        ReadingKey oldKey = new ReadingKey(device, day, older);
        ReadingKey newKey = new ReadingKey(device, day, newer);

        repository.save(new Reading(oldKey, 21.5, "OK"));
        repository.save(new Reading(newKey, 22.0, "OK"));

        List<Reading> latest = repository.findLatest20(device, day);

        assertEquals(2, latest.size());
        assertEquals(newer, latest.get(0).getKey().getEventTime());
        assertTrue(repository.findById(oldKey).isPresent());
    }
}
~~~

**Điều kiện để test đáng tin:**

- Test slice **không tự khởi động Cassandra server**; cần provisioning Testcontainers/external test cluster và cấu hình kết nối phù hợp.
- Keyspace/table phải có sẵn qua migration test; đừng cho test recreate schema production.
- RF/CL phải phù hợp topology lab; nếu dùng RF=3 mà chỉ một node, `LOCAL_QUORUM` có thể không đạt.
- Đọc ngay sau ghi cần được thiết kế consistency phù hợp; nếu test yêu cầu read-your-writes, hãy cấu hình/kiểm chứng CL hoặc test harness tương ứng.
- UUID ngẫu nhiên giảm khả năng đụng dữ liệu test khác; vẫn cần cleanup/TTL/isolated keyspace theo policy.
- `@DataCassandraTest` và repository scanning/imports có chi tiết khác theo Spring Boot version; xác minh bean wiring thực tế.

Ví dụ thể hiện **ý tưởng integration test** chứ không tuyên bố mọi stack chạy nguyên đoạn mà không cần cấu hình.

### 18.3. Test các đường thất bại

| Test | Kết quả cần quan sát |
|---|---|
| Derived method đủ partition key | Generated CQL hợp lệ, chỉ vào đúng partition |
| Query thiếu một partition key | Bị từ chối/không được đưa vào production, không bật filtering mù |
| `@Query` có LIMIT 20 | Không trả quá 20 row |
| Range event_time | Đúng boundary và clustering order |
| Query theo status đơn lẻ | Kiểm tra server constraint rõ ràng |
| Row thiếu reading_value | DTO giữ null, không tự chuyển thành 0.0 |
| `findById` với đầy đủ key | Tìm một row; không trả cả partition |
| Thay alias/projection | Mapper không âm thầm sai |
| Slice/paging nhiều page | Không skip/duplicate do logic paging ứng dụng |
| Schema mới có cột optional | Row cũ vẫn đọc an toàn |
| Một replica down trong lab | Kiểm chứng CL/availability được thiết kế |
| Lỗi driver timeout | HTTP không trả “không có row” giả |
| Read/writes theo tenant | Principal không đọc được partition của tenant khác |
| Version upgrade | Repository parser, type codec và dependencies vẫn tương thích |

Không stress test hệ thống production bằng cách sinh hàng triệu row chỉ để xác minh `findAll()` có chậm không. Dùng data volume đại diện trên môi trường an toàn và quan sát tài nguyên.

### 18.4. Kiểm thử time/timezone

CQL `timestamp` là mốc thời gian; mapping thường dùng `Instant`. `date` tương ứng ngày lịch `LocalDate`. Với bucket theo ngày, phải thống nhất **timezone chọn ngày** (ví dụ UTC), đặc biệt khi có event quanh nửa đêm.

Không lấy `LocalDate.now()` theo timezone ngầm định của JVM rồi mặc định giống server/khách hàng. Một hàng được ghi vào **event_day khác** có thể làm repository “không tìm thấy” dù row tồn tại ở partition khác.

## 19. Security: multi-tenant và quyền truy cập

### 19.1. Repository parameter không phải kiểm soát quyền

Giả sử API nhận:

~~~text
GET /tenants/{tenantId}/devices/{deviceId}/readings
~~~

Nếu bảng dùng partition key `(tenant_id, device_id, event_day)`, việc Spring Data **bind được tenantId** không chứng minh người gọi có quyền truy cập tenant ấy.

Trong tầng service cần:

1. Authentication và principal tin cậy.
2. Xác minh principal được phép truy cập tenant.
3. Lấy tenant/role từ context đã được xác thực hoặc kiểm quyền rõ.
4. Bind đúng tenant vào query.
5. Cấu hình quyền Cassandra theo nguyên tắc **least privilege**.
6. Không log dữ liệu/sensitive partition keys tùy tiện.

### 19.2. `@Query` bind value tránh CQL injection nhưng không che lỗ hổng quyền

~~~java
@Query(
    "SELECT device_id, event_day, event_time, " +
    "reading_value, status FROM readings_by_device_day " +
    "WHERE device_id = ?0 AND event_day = ?1 LIMIT 20")
List<Reading> findLatest20(UUID deviceId, LocalDate day);
~~~

Nếu người gọi có thể cung cấp UUID của thiết bị người khác và ứng dụng không kiểm tra ownership, query **không có lỗi injection** nhưng **vẫn rò dữ liệu**.

Không dùng regex UUID hoặc validation type làm thay thế authorization.

### 19.3. Kiểm soát quyền ở nhiều lớp

- Application principal/role và tenant authorization.
- Cassandra role/RBAC theo keyspace/table nếu được bật.
- TLS app↔cluster và xác thực certificate/credentials.
- Secret rotation và connection pool lifecycle.
- Query/metric logging làm sạch bind values.
- Quy định quyền quản trị schema tách khỏi tài khoản runtime.

Trong Cassandra, phân quyền ở bảng/keyspace **không nhất thiết tự cung cấp row-level security** cho từng tenant. Nếu nhiều tenant cùng bảng và cùng role Cassandra, app phải thực hiện isolation đúng; cân nhắc mô hình dữ liệu/kiến trúc nếu cần bảo đảm cách ly mạnh hơn.

## 20. Observability: repository method nào đang làm Cassandra chậm?

### 20.1. Ba nguồn đo

| Nguồn | Metric hữu ích | Ý nghĩa |
|---|---|---|
| **Spring API/service** | Endpoint QPS, p50/p95/p99, 5xx, total rows/bytes | Ảnh hưởng đến người dùng |
| **Java Driver/Spring repository** | Query ID, in-flight, CL, timeout, retry, coordinator, paging | Biết shape/query nào đang gây tải |
| **Cassandra node** | Read/write latency, compaction, SSTables per read, tombstones, disk, CPU/GC | Tìm bottleneck ở replica |

Nên đặt **query ID cố định** như `read_latest20_by_device_day` cho repository method thay vì log raw query có bind values.

### 20.2. Lệnh quan sát trong cluster

~~~bash
# Trạng thái node, DC/rack, token ownership.
nodetool status

# Pending/active/dropped messages theo stage.
nodetool tpstats

# Các compaction task và backlog.
nodetool compactionstats

# Metrics theo bảng, gồm storage/read/write tùy phiên bản.
nodetool tablestats telemetry_lab.readings_by_device_day

# Histogram theo bảng nếu phiên bản hỗ trợ.
nodetool tablehistograms telemetry_lab readings_by_device_day

# Streaming khi repair/bootstrap/replace.
nodetool netstats
~~~

`netstats` trống **không chứng minh** Java `findAll()` không đang tạo tải CQL; nó chủ yếu báo SSTable streaming. `nodetool status` báo `UN` cũng không chứng minh latency đạt SLO.

### 20.3. Đọc p99 cùng error rate

Nếu repository `findLatest20` trả p99 100 ms khi thành công nhưng timeout rate tăng từ 0,1% lên 5%, hệ thống **không nhất thiết khỏe hơn**. Những request chậm bị timeout có thể không xuất hiện trong histogram thành công.

Không tính p99 cluster bằng cách lấy trung bình p99 của từng node. Hãy dùng histogram/phân bố được tổng hợp đúng, xem cả driver timeout, server read/write timeout, unavailable và retry amplification.

### 20.4. Table-level pressure

Một phương thức `findByKeyDeviceIdAndKeyEventDay(...)` không có LIMIT có thể tải 500.000 row từ một partition. Sau deploy, dashboard có thể thấy:

~~~text
Time UTC   API p99   Response bytes   ReadStage Pending   Heap use
09:00      120 ms          10 KiB               15          35%
09:15      750 ms         900 KiB              180          68%
09:30     1800 ms           8 MiB              740          91%
~~~

**Các số là minh họa**, không phải benchmark. Kiểm tra thêm p95, request timeout, network, GC, SSTable count, compaction và data distribution trước khi kết luận query là nguyên nhân duy nhất.

## 21. Runbook A — Derived query compile được nhưng runtime báo invalid CQL

**Tình huống:** Sau deploy, `findByStatus(String status)` được gọi và Cassandra trả lỗi do lọc thiếu partition key hoặc không có access path phù hợp.

1. **Xác minh schema:** `PRIMARY KEY`, cột indexed, options, Cassandra version.
2. **Xác minh Java mapping:** tên property, `@Column` và key class/ordinal.
3. **Xác minh CQL thực:** dùng query logging có kiểm soát hoặc driver instrumentation, tránh ghi bind values/PII.
4. **Phân biệt lỗi parser và lỗi server:** Spring Data có tạo query không? Server từ chối ở điều kiện nào?
5. **Không thêm `ALLOW FILTERING` mặc định** để “cho qua” incident.
6. **Thiết kế lại access path**: partition/bucket, query-specific table hoặc index đã đánh giá.
7. **Dùng `@Query` nếu vấn đề là biểu đạt**, không phải data model. `@Query` không giải quyết một access path không tồn tại.
8. **Kiểm thử tải/timeout** với dữ liệu đại diện trước khi bật toàn bộ traffic.

**Kết quả mong muốn:** không chỉ “endpoint trả 200”, mà còn query đúng, p99/bytes/s hợp lý và không tạo full cluster scan.

## 22. Runbook B — Spring Boot start được nhưng repository báo query không có table

**Tình huống:** Service deploy thành công, connection tới Cassandra hoạt động, nhưng `findLatest20` lỗi “unconfigured table” hoặc metadata mapping không đúng.

1. Ghi phiên bản Boot, Spring Data, driver, keyspace, endpoint, local DC và change ID.
2. Kiểm tra `spring.cassandra.keyspace-name` có đúng cluster, không nhầm test/prod.
3. Kiểm tra table `readings_by_device_day` thực sự tồn tại trong keyspace.
4. So DDL/schema agreement, tên cột và quoted/unquoted identifiers.
5. So `@Table`, `@PrimaryKeyClass`, `@PrimaryKeyColumn`, `@Column` với CQL thật.
6. Kiểm tra user/role có `SELECT` hay không; auth error không giống thiếu table.
7. Đối chiếu compatibility matrix khi vừa nâng driver/framework hoặc schema.
8. Không bật schema auto-recreate trên production để chữa lỗi thiếu table. Chạy migration schema qua change process.
9. Kiểm thử lại `findById`, derived query và `@Query` trên cùng keyspace.

**Đừng xóa/recreate bảng khi chưa có kế hoạch backup/rollback**. Một lỗi mapping Java không phải bằng chứng bảng Cassandra bị hỏng.

## 23. Runbook C — Repository method gây timeout và heap tăng

**Tình huống:** Đổi API sang `List<Reading> findByKeyDeviceIdAndKeyEventDay`; một số partition rất lớn, request p99/GC tăng.

1. **Đo số row và response bytes** trên những partition bị ảnh hưởng; xác định hot/wide partition.
2. Kiểm tra có `LIMIT`/paging/stop condition hay chưa.
3. Xác minh query dùng đúng full partition key và không scan nhiều partition.
4. Kiểm tra `ResultSet`/mapping: có gom mọi row vào List/collectList không?
5. So `tpstats`, SSTables per read, tombstone warnings, compaction và disk I/O.
6. Giảm concurrency, rate và tải backfill/reporting không cần thiết khi quá tải.
7. Đổi sang query **bounded** (ví dụ `@Query LIMIT 20`), Slice/cursor hoặc thiết kế bucket mới.
8. Nếu API cần nhiều ngày hoặc toàn lịch sử, dùng pipeline job với checkpoint và quota; không ép request HTTP đọc toàn bộ.
9. Đối chiếu p99, timeout, heap/GC và error budget sau thay đổi.

**Không chỉ tăng request timeout** khi một query đang trả quá nhiều dữ liệu. Nó có thể giữ request/heap lâu hơn và làm sự cố nặng hơn.

## 24. Runbook D — Page tiếp theo bị lặp/mất row sau thay đổi schema

**Tình huống:** API “next page” dùng số trang kiểu SQL; khi dữ liệu mới đến hoặc schema thay đổi, client thấy thiếu hoặc lặp row.

1. Xác minh query shape, partition key, clustering order và tập dữ liệu đang thay đổi.
2. Kiểm tra API có đang dùng offset giả thông qua fetch/bỏ row không.
3. Xem Spring Data Cassandra version hỗ trợ `Slice`, `CassandraPageRequest`/continuation ra sao.
4. Ràng buộc cursor với query template, partition và tham số; có kiểm soát integrity/expiry.
5. Nếu cần ổn định theo thời gian, cân nhắc keyset pagination dựa trên clustering key hoặc read snapshot được thiết kế.
6. Đối soát boundary condition `<`/`<=` để không bỏ trùng ở những page.
7. Test cùng load, insert/delete/TTL xen kẽ giữa các page.
8. Không mặc định paging state cũ mãi hợp lệ khi driver/server/schema thay đổi.

**CQL paging không phải transaction snapshot**. “Page 2” trong UI cần hợp đồng dữ liệu rõ, không chỉ một số nguyên.

## 25. So sánh lựa chọn truy vấn

| Trường hợp | API được cân nhắc | Vì sao |
|---|---|---|
| Lookup một row theo toàn primary key | `repository.findById(fullKey)` | Đơn giản, đúng phạm vi |
| Lấy dữ liệu một partition nhỏ | Derived `findByKeyDeviceIdAndKeyEventDay` | Dễ đọc nếu method/parser được test |
| Lấy 20 row mới nhất | `@Query` với explicit projection và LIMIT | Ràng buộc số row, rõ CQL |
| Range clustering theo thời gian | `@Query` hoặc template | Diễn đạt range/limit rõ ràng |
| Điều kiện động trong tập allowlist | `CassandraTemplate` | Linh hoạt nhưng vẫn kiểm soát CQL |
| Deadline/CL/statement tracing rất cụ thể | `CqlSession` prepared/bound hoặc template options | Điều khiển driver-level theo version |
| Dataset lớn cần liên tục xử lý | Paging/async/reactive có quota, job checkpoint | Tránh gom vào List/HTTP |
| Search đa điều kiện không có partition key | Tạo bảng/index/search/analytics phù hợp | Không ép `findBy...` |
| Join giữa bảng | Denormalization hoặc tầng service | Cassandra không có SQL JOIN tổng quát |
| Change stream liên tục | CDC/event pipeline | Repository SELECT không phải event subscription |
| Conditional write | LWT API được hỗ trợ | `save` thường không tự làm CAS |
| Tổng hợp count toàn cluster | Bảng tổng hợp/counter phù hợp, analytics | Tránh `count()` lặp trên bảng lớn |

## 26. Những ngộ nhận phổ biến

| Nhận định | Thực tế |
|---|---|
| “Có `findByStatus` thì Cassandra lọc status tốt.” | Query phải có access path, không do tên Java quyết định |
| “Derived query giống JPA trên PostgreSQL.” | Spring Data Cassandra bị ràng buộc bởi CQL/partition model |
| “`@Query` cho phép mọi SQL.” | Nó chứa CQL, không phải SQL tổng quát |
| “Đổi sang `@Query` sẽ sửa full scan.” | Không nếu vẫn WHERE thiếu partition key |
| “`findById` của entity key ghép chỉ cần deviceId.” | Phải có toàn bộ primary key gồm clustering component |
| “`List` là kết quả an toàn vì framework paging tự động.” | Có thể gom rất nhiều row vào bộ nhớ |
| “`findAll()` phù hợp để xuất toàn bộ table lúc nào cũng được.” | Có thể tạo scan rất lớn, cần job có throttle |
| “`count()` trên Cassandra luôn rẻ.” | Có thể tốn nhiều reads; tùy table và phạm vi |
| “Spring Data thêm JOIN cho Cassandra.” | CQL không có arbitrary server-side JOIN |
| “`ORDER BY status` được vì có Spring Sort.” | CQL ORDER BY phụ thuộc clustering schema |
| “Có pageSize=50 thì tổng row không quá 50.” | Page size chỉ điều tiết từng page |
| “Pageable luôn có random page N như SQL.” | Cassandra thường cần continuation/paging state |
| “Thêm cột tự tạo giá trị ở row lịch sử.” | Cột mới có thể null ở dữ liệu cũ |
| “Sửa partition key annotation sẽ tự di chuyển dữ liệu.” | Cần bảng mới/backfill/cutover |
| “Repository save là ACID transaction nhiều bảng.” | Không; Cassandra mutation/CL/LWT có semantics riêng |
| “`save` luôn là IF NOT EXISTS.” | Thường là upsert, không phải CAS mặc định |
| “TTL chỉ ảnh hưởng Java mapper.” | TTL ảnh hưởng dữ liệu sống, tombstone, compaction |
| “Spring reactive tự tạo CDC.” | Reactive query vẫn là truy vấn CQL hữu hạn |
| “Bật `ALLOW FILTERING` để khỏi thiết kế bảng.” | Có thể scan và tăng latency/I/O rất lớn |
| “Token-aware routing giải quyết mọi hot partition.” | Partition nóng vẫn tập trung vào tập replica |
| “Boot startup UP nghĩa tất cả query hợp lệ.” | Cần integration/smoke tests theo method thực |
| “Dùng UUID hợp lệ đủ ngăn rò tenant.” | Cần authorization theo principal và RBAC |
| “Hạ consistency level không ảnh hưởng correctness.” | CL thay đổi bảo đảm replica phản hồi |

## 27. Bài tập và đáp án

### Câu 1 — Khóa phân vùng

Bảng có `PRIMARY KEY ((device_id, event_day), event_time)`. Partition key gồm những cột nào?

**Đáp án:** `device_id` và `event_day`. `event_time` là clustering key; toàn primary key gồm cả ba cột.

### Câu 2 — `findById`

Repository có kiểu ID `ReadingKey`. Muốn tìm mọi row ngày 21/11, có nên gọi `findById(new ReadingKey(device, day, null))`?

**Đáp án:** Không. Full primary key cần `event_time` hợp lệ. Tìm partition bằng derived query/`@Query` dùng device/day.

### Câu 3 — Derived query

Tên `findByKeyDeviceIdAndKeyEventDay` có thể tìm dữ liệu trong một partition. Có thể bảo đảm nó chỉ trả 20 row không?

**Đáp án:** Không, bản không LIMIT/paging có thể trả toàn partition. Cần query bounded hoặc pagination.

### Câu 4 — Query theo status

Một API mới cần `findByStatus("ALERT")` trên bảng ví dụ. Chỉ thêm method là đủ?

**Đáp án:** Không. `status` không phải thành phần key. Cần thiết kế access path khác: query-specific table/index được đánh giá hoặc xử lý phù hợp.

### Câu 5 — `@Query`

Sử dụng `@Query("SELECT ... WHERE device_id = ?0 ...")` giúp gì?

**Đáp án:** Biểu đạt CQL tường minh, bind values và kiểm soát projection/LIMIT/conditions. Nó không bypass server CQL constraints.

### Câu 6 — Bind tên bảng

Có thể dùng `?0` để bind tên bảng theo input người dùng không?

**Đáp án:** Không như bind value thông thường. Tên bảng là identifier; dùng template allowlist/enum và kiểm quyền, không nối raw untrusted input.

### Câu 7 — Clustering order

Muốn lấy 20 row mới nhất trong device/day. Bảng có `event_time DESC`. Truy vấn nào phù hợp?

**Đáp án:** CQL theo cả `device_id` và `event_day` với `LIMIT 20`, chọn projection cần thiết. Không cần sort toàn bảng.

### Câu 8 — Global sort

Muốn `ORDER BY reading_value DESC` trên mọi thiết bị, `Sort` ở repository có giải quyết được không?

**Đáp án:** Không. Cassandra không hỗ trợ arbitrary global sorting như SQL; cần bảng/index/analytics thiết kế theo access pattern.

### Câu 9 — Paging

Page size 50 có giới hạn tổng SELECT 50 row không?

**Đáp án:** Không. Nó là mục tiêu mỗi page; dùng `LIMIT`/cursor/stop condition phù hợp cho tổng kết quả.

### Câu 10 — Offset

Client muốn nhảy tới page 10.000 bằng `PageRequest.of(10000,20)`. Có nên kỳ vọng Cassandra skip hiệu quả như RDBMS không?

**Đáp án:** Không. Cassandra paging thường theo continuation state. Cần thiết kế cursor/keyset và kiểm tra support Spring Data version.

### Câu 11 — TTL

Retry một INSERT dùng TTL mới có thể thay đổi điều gì?

**Đáp án:** Thời điểm cell hết hạn và timestamp reconciliation; không mặc định retry luôn idempotent về nghiệp vụ.

### Câu 12 — LWT

`repository.save` có mặc định tương đương `INSERT ... IF NOT EXISTS`?

**Đáp án:** Không. `save` thường là upsert. Muốn conditional write phải dùng API/statement hỗ trợ LWT với semantics rõ.

### Câu 13 — Schema change

Thay `event_day` sang `event_month` trong Java key annotation có tự phân bố lại SSTable cũ không?

**Đáp án:** Không. Đổi partition key cần bảng mới, backfill, đối soát và cutover.

### Câu 14 — Multi-tenant

Người gọi bind `device_id` hợp lệ thuộc tenant khác. Câu query không bị injection. Đã đủ an toàn chưa?

**Đáp án:** Chưa. Phải kiểm tra quyền/ownership dựa trên principal và thiết kế cách ly tenant.

### Câu 15 — Error handling

`findLatest20` timeout nhưng service trả List rỗng. Vì sao nguy hiểm?

**Đáp án:** Nó biến lỗi cơ sở dữ liệu thành “không có dữ liệu”, gây quyết định nghiệp vụ sai. Phải phân biệt timeout với kết quả SELECT rỗng hợp lệ.

### Câu 16 — Reactive

Một reactive repository trả `Flux<Reading>`. Điều này tự bảo đảm không bị OOM không?

**Đáp án:** Không. `collectList`, buffer không giới hạn, fan-out và row lớn vẫn có thể tiêu tốn heap; cần backpressure/concurrency.

### Câu 17 — Integration test

Mock repository trả đúng danh sách. Có đủ chứng minh derived query sinh CQL hợp lệ không?

**Đáp án:** Không. Cần integration test trên Cassandra lab theo version, keyspace/schema và data distribution.

### Câu 18 — Compaction

Sau backfill bảng mới, disk free giảm và compaction pending tăng. Chuyển từ repository sang `CqlSession` có tự giải quyết được không?

**Đáp án:** Không. Nguyên nhân nằm ở volume writes, RF, compaction và storage headroom; cần throttle/monitor/capacity plan.

### Câu 19 — Consistency

Keyspace RF=3, CL=`LOCAL_QUORUM`, một DC chỉ còn một replica khỏe. Spring repository có thể tự làm request thành công mà không đổi consistency không?

**Đáp án:** Không thể bảo đảm. Local quorum yêu cầu hai replica trong ví dụ; cần khôi phục khả năng phục vụ hoặc cân nhắc chính sách CL qua quyết định nghiệp vụ.

### Câu 20 — Tổng hợp truy vấn

API cần báo cáo tổng số sự kiện theo site mỗi ngày trên nhiều tỷ row. Có nên dùng `repository.count()` mỗi lần mở dashboard?

**Đáp án:** Thường không. Cần thiết kế bảng aggregation/materialized counters/event processing có bảo đảm dữ liệu và semantics phù hợp, hoặc hệ thống analytics riêng.

## 28. Checklist trước khi merge Spring Data Cassandra repository

### 28.1. Schema và mapping

~~~text
[ ] Query shapes thực tế đã được viết ra trước khi tạo method.
[ ] Partition key/clustering key, thứ tự và type khớp CQL.
[ ] @PrimaryKeyClass/@PrimaryKeyColumn/@PrimaryKey mapping có test.
[ ] Entity @Table/@Column khớp keyspace/table/column thật.
[ ] Nullable field và Instant/LocalDate timezone được xử lý.
[ ] DDL/schema changes được quản lý ngoài startup production.
[ ] Mọi thay đổi primary key đều có migration/backfill/cutover.
~~~

### 28.2. Repository và truy vấn

~~~text
[ ] Không dùng findAll/count/deleteAll cho bảng lớn thiếu plan.
[ ] Derived property path và generated CQL được integration test.
[ ] @Query dùng bind value, không nối raw user input.
[ ] Projection chỉ chứa field cần, đủ key để mapping entity.
[ ] WHERE đủ partition key hoặc access path đã được duyệt.
[ ] LIMIT/page size/cursor rõ ràng và đã load test.
[ ] Không áp dụng SQL JOIN/OR/ORDER BY tùy ý như RDBMS.
[ ] @Query không được dùng để che scan/ALLOW FILTERING vô hạn.
[ ] CassandraTemplate/CqlSession chỉ dùng khi cần và có tests.
[ ] Ghi/thử lại/LWT/TTL/delete có semantics được mô tả rõ.
~~~

### 28.3. Vận hành, bảo mật và khả năng phục vụ

~~~text
[ ] Spring Boot/Driver/Spring Data/JDK versions tương thích.
[ ] Contact points, local DC, keyspace, auth/TLS đúng môi trường.
[ ] Role runtime có least privilege và tenant authorization riêng.
[ ] RF/CL/replica availability đáp ứng SLO.
[ ] Query IDs, p95/p99, errors/retries và response bytes có metrics.
[ ] tpstats/compactionstats/tablestats/disk/GC được theo dõi.
[ ] Không log raw bind values, secrets hay routing keys.
[ ] Có runbook invalid derived CQL, schema mismatch, paging, timeout.
[ ] Có test với partition lớn, TTL/tombstone, null và data changes.
[ ] Không coi Boot health UP là kiểm thử đầy đủ các repository methods.
~~~

## 29. Tổng kết

Khi dùng **Spring Boot và Spring Data Cassandra**:

1. **`CassandraRepository` giảm mã CRUD**, nhưng các method như `findAll()`/`count()`/`deleteAll()` có thể rất đắt ở bảng wide-column lớn.
2. **Derived query** phân tích tên method/property Java thành CQL; nó chỉ hữu ích khi điều kiện được CQL/schema hỗ trợ và phải được kiểm thử trên Cassandra thật.
3. **`@Query` cho phép CQL tường minh** về projection, WHERE, range và LIMIT; nó không biến CQL thành SQL hay tự tạo index.
4. **Composite primary key phải được mapping chính xác** bằng key class và annotation, bao gồm partition/clustering components, type và thứ tự.
5. **Query thiết kế theo partition key**, clustering order và access pattern; không kỳ vọng JOIN, arbitrary WHERE/OR, global ORDER BY hoặc offset pagination rẻ.
6. **Paging khác LIMIT**: page/fetch size điều tiết từng lần nhận, không hạn chế tổng số row hay đảm bảo snapshot.
7. **Template/driver là escape hatch về API**, không phải escape hatch khỏi data model hay replica load.
8. **`save` không mặc định là transaction hay LWT**; TTL, DELETE, retries, consistency và concurrent writes cần đánh giá tính đúng.
9. **Reactive repository chỉ thay cách tiêu thụ kết quả**, không thay quy tắc CQL và không tự đảm bảo memory/concurrency.
10. **Integration tests và observability là bắt buộc** để phát hiện method hợp lệ về Java nhưng sai hoặc tốn tài nguyên ở Cassandra.

Câu hỏi trước khi thêm một phương thức repository không phải **“Spring Data có diễn giải được tên hàm này không?”**, mà là **“CQL nào thực sự chạy, partition/replica nào phải phục vụ, số row/bytes tối đa là bao nhiêu, và abstraction này có giữ đúng semantics của ứng dụng trong điều kiện lỗi và schema evolution hay không?”**. Trả lời được bằng schema, tests và số liệu sẽ giúp Spring Data trở thành lớp truy cập Cassandra dễ bảo trì mà không che giấu chi phí của hệ phân tán.
