# Tạo bảng từ metadata ánh xạ của entity trong Spring Data Cassandra

Trong **Spring Data Cassandra**, một lớp Java được đánh dấu bằng `@Table` có thể mô tả tên bảng, cột, kiểu dữ liệu và cấu trúc khóa của Apache Cassandra. Spring Data đọc các chú thích này thành **mapping metadata** để thực hiện truy vấn và chuyển đổi giữa hàng CQL với đối tượng Java. Nếu ứng dụng bật **schema action** phù hợp, framework còn có thể sử dụng metadata để **tạo bảng** trong keyspace đã cấu hình.

Bài thuộc chương **Quản lý lược đồ** của module **SPRING_DATA_CASSANDRA**. Chúng ta sẽ đi từ một entity đơn giản đến khóa ghép gồm partition key và clustering key, dự đoán CQL được tạo, cấu hình Spring Boot, kiểm tra kết quả và phân biệt khởi tạo schema với migration. Điểm cần giữ xuyên suốt: **entity mapping giúp mô tả bảng; mô hình dữ liệu Cassandra vẫn phải được thiết kế theo truy vấn**. Một bảng tự sinh đúng cú pháp chưa chắc có partition key, paging hay khả năng chịu tải phù hợp.

## 1. Mapping metadata là gì?

Spring Data Cassandra dùng thông tin từ các annotation để xây dựng mô hình về entity:

| Thành phần | Annotation/khái niệm | Ý nghĩa |
|---|---|---|
| Bảng | `@Table("device_state_by_id")` | Ánh xạ lớp Java tới bảng CQL |
| Khóa đơn | `@PrimaryKey("device_id")` | Cột là toàn bộ primary key khi bảng chỉ có một khóa |
| Khóa ghép | `@PrimaryKeyClass`, `@PrimaryKeyColumn` | Phân biệt thành phần partition key và clustering column |
| Cột | `@Column("updated_at")` | Tên cột CQL và thuộc tính Java |
| Thuộc tính không lưu | `@Transient` | Không đưa thuộc tính vào mapping persistence |
| Kiểu Java | `UUID`, `String`, `Instant`, `BigDecimal` | Được bộ chuyển đổi kiểu ánh xạ sang kiểu Cassandra phù hợp |
| Thứ tự clustering | `ordering = Ordering.DESCENDING` | Tác động đến khai báo thứ tự clustering khi sinh schema |

Đường đi khái quát:

~~~text
Lớp Java + annotation
          |
          v
Spring Data Cassandra MappingContext
          |
          +--> CassandraRepository / CassandraTemplate
          |       đọc, ghi, ánh xạ Row <-> Entity
          |
          +--> Schema creation (khi schema-action cho phép)
                  ánh xạ metadata thành DDL
                            |
                            v
                       Cassandra CQL
~~~

**Hai chức năng độc lập:** việc ánh xạ entity để đọc/ghi không yêu cầu framework tạo bảng. Một ứng dụng production có thể sử dụng repository và `CassandraTemplate` bình thường với `schema-action: NONE`, miễn schema đã được provision hoặc migration trước đó.

## 2. Những điều kiện cần trước khi tạo bảng

Để Spring Data Cassandra tạo bảng từ entity, tối thiểu cần:

1. **Kết nối Cassandra hợp lệ**: contact points, local datacenter, authentication/TLS khi cluster yêu cầu.
2. **Keyspace đã tồn tại**: session phải có keyspace mục tiêu. Chỉ đặt `keyspace-name` không tự tạo keyspace mới.
3. **Entity nằm trong phạm vi mapping scan**: Spring phải biết lớp có `@Table` trước khi xây dựng metadata để tạo bảng.
4. **Schema action cho phép tạo bảng**: ví dụ `CREATE_IF_NOT_EXISTS` khi khởi động ứng dụng.
5. **Tài khoản có quyền tạo bảng**: khác với tài khoản chỉ có quyền `SELECT`/`MODIFY` dữ liệu.

Ví dụ môi trường học tập dùng một datacenter `dc1`, một node và replication factor 1:

~~~sql
-- Chạy bằng vai trò quản trị. Thông số chỉ minh họa môi trường học.
CREATE KEYSPACE IF NOT EXISTS learning_data
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 1
}
AND durable_writes = true;
~~~

Tên `dc1` phải trùng **tên datacenter thực tế** trong cluster. Ở production, chọn replication factor theo số node, số datacenter và yêu cầu chịu lỗi/consistency; không copy RF=1 chỉ vì ví dụ có một node.

## 3. Entity đơn giản: một UUID làm partition key

Giả sử API cần lấy trạng thái hiện tại của một thiết bị theo `device_id`. Thiết kế bảng có đúng một hàng cho mỗi thiết bị:

~~~java
package example.cassandra.model;

import java.time.Instant;
import java.util.UUID;
import org.springframework.data.annotation.Transient;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("device_state_by_id")
public class DeviceState {

    @PrimaryKey("device_id")
    private UUID deviceId;

    @Column("status")
    private String status;

    @Column("updated_at")
    private Instant updatedAt;

    @Transient
    private String displayLabel;

    public DeviceState() {
    }

    public DeviceState(UUID deviceId, String status, Instant updatedAt) {
        this.deviceId = deviceId;
        this.status = status;
        this.updatedAt = updatedAt;
    }

    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID deviceId) { this.deviceId = deviceId; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }
    public String getDisplayLabel() { return displayLabel; }
    public void setDisplayLabel(String displayLabel) {
        this.displayLabel = displayLabel;
    }
}
~~~

Khi ánh xạ này được đưa vào quá trình tạo schema, bảng kỳ vọng về mặt cấu trúc:

~~~sql
-- CQL minh họa cấu trúc tương đương với metadata.
CREATE TABLE IF NOT EXISTS learning_data.device_state_by_id (
    device_id uuid PRIMARY KEY,
    status text,
    updated_at timestamp
);
~~~

`displayLabel` không xuất hiện trong bảng vì `@Transient`. `Instant` thường được ánh xạ đến CQL `timestamp`; `UUID` tới `uuid`. Cú pháp DDL thực tế do phiên bản Spring Data Cassandra sinh có thể khác về thứ tự cột, cách quote tên hoặc tùy chọn bảng; điều cần so sánh là **schema tương đương về ngữ nghĩa**.

### 3.1. Vì sao phải chỉ rõ tên cột?

Đặt `@Column("updated_at")` làm ví dụ dễ đọc và giảm phụ thuộc vào naming strategy của ứng dụng. Nếu bỏ annotation, framework dùng cơ chế đặt tên theo mapping configuration đang áp dụng; đừng dự đoán tên CQL từ cách viết camelCase một cách chủ quan.

Đặc biệt, thay tên field trong Java không được xem là thao tác rename cột an toàn trên Cassandra. Nó có thể làm mapping trỏ đến cột khác, trong khi dữ liệu cũ và schema vật lý chưa thay đổi.

## 4. Bật tạo bảng trong Spring Boot

Giả sử ứng dụng Spring Boot 3.x dùng dependency tương thích với **Spring Data Cassandra**. Cấu hình ở môi trường **local/dev**:

~~~yaml
# application-local.yml
spring:
  cassandra:
    contact-points:
      - 127.0.0.1:9042
    local-datacenter: dc1
    keyspace-name: learning_data
    schema-action: CREATE_IF_NOT_EXISTS
~~~

Khi profile `local` được kích hoạt, Spring Boot cấu hình session và thành phần Spring Data Cassandra theo classpath. Với metadata entity được scan và quyền CQL phù hợp, schema action có thể tạo các bảng còn thiếu khi khởi động.

> **Chỉ bật chủ động ở môi trường phù hợp.** Không nên mặc định cấp quyền DDL cho tài khoản chạy dịch vụ production. Đối với production đã có migration riêng, chọn `schema-action: NONE` hoặc bỏ cơ chế tạo tự động theo chính sách phiên bản framework và dự án.

Các lựa chọn phổ biến của schema action:

| Schema action | Ý định sử dụng | Điều cần nhớ |
|---|---|---|
| `NONE` | Không tạo hoặc sửa schema từ entity | Thích hợp khi schema được quản lý bằng migration |
| `CREATE_IF_NOT_EXISTS` | Chỉ tạo bảng chưa tồn tại theo metadata | Không phải công cụ cập nhật schema hiện hữu |
| `CREATE` | Thực hiện tạo schema theo metadata | Có thể thất bại nếu đối tượng đã tồn tại; dùng có kiểm soát |
| Các chế độ `RECREATE` | Tạo lại đối tượng theo mapping | Có khả năng **làm mất dữ liệu**; chỉ dùng trên dữ liệu có thể hủy và khi hiểu chính xác semantics của phiên bản |

Danh sách và semantics chi tiết của các giá trị `SchemaAction` cần đối chiếu với phiên bản Spring Data Cassandra đang dùng. Đối với bài thực hành này, chỉ cần `CREATE_IF_NOT_EXISTS` cho schema mới và `NONE` cho môi trường không cho phép quản lý schema tự động.

### 4.1. Không nhầm tiền tố thuộc tính của Spring Boot

Ở Spring Boot 3.x, các thuộc tính Cassandra thường có tiền tố `spring.cassandra.*`. Một số dự án Spring Boot 2.x cũ dùng `spring.data.cassandra.*`. Hãy kiểm tra version và configuration metadata của dự án thực tế; copy YAML từ dự án khác dòng phiên bản có thể khiến các thuộc tính bị bỏ qua.

### 4.2. Schema creation xảy ra khi nào?

Trong cơ chế tạo schema được bật, framework sử dụng metadata khi thiết lập hạ tầng Cassandra lúc khởi động. Đây không phải câu lệnh DDL được chạy trước **mỗi lần** gọi `repository.save()` hoặc `template.insert()`.

Nếu không có bean entity tương ứng trong phạm vi mapping, framework cũng không có đủ metadata để tạo bảng đó. Cần kiểm tra package scan, cấu hình Spring Data Cassandra và việc lớp dùng đúng `@Table`, chứ không chỉ nhìn file YAML.

## 5. Tạo bảng có partition key ghép và clustering column

Hầu hết bài toán Cassandra không dừng lại ở bảng tra một ID. Ví dụ sản phẩm cần đọc **100 sự kiện mới nhất của một thiết bị trong một ngày**. Cần partition key gồm `device_id` và `day_bucket`, đồng thời sắp xếp theo `event_time` giảm dần.

Truy vấn mong muốn:

~~~sql
SELECT *
FROM events_by_device_day
WHERE device_id = ?
  AND day_bucket = ?
LIMIT 100;
~~~

Khóa tương ứng:

~~~sql
CREATE TABLE IF NOT EXISTS learning_data.events_by_device_day (
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Ở đây, **cả cặp** `(device_id, day_bucket)` là partition key. `event_time` và `event_id` là clustering columns. Thêm `event_id` giúp phân biệt hai sự kiện có cùng timestamp.

### 5.1. Mô tả khóa ghép trong Java

~~~java
package example.cassandra.model;

import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class DeviceEventKey implements Serializable {

    @PrimaryKeyColumn(name = "device_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID deviceId;

    @PrimaryKeyColumn(name = "day_bucket", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private LocalDate dayBucket;

    @PrimaryKeyColumn(name = "event_time", ordinal = 2,
            type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant eventTime;

    @PrimaryKeyColumn(name = "event_id", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED, ordering = Ordering.ASCENDING)
    private UUID eventId;

    public DeviceEventKey() {
    }

    public DeviceEventKey(UUID deviceId, LocalDate dayBucket,
                          Instant eventTime, UUID eventId) {
        this.deviceId = deviceId;
        this.dayBucket = dayBucket;
        this.eventTime = eventTime;
        this.eventId = eventId;
    }

    public UUID getDeviceId() { return deviceId; }
    public LocalDate getDayBucket() { return dayBucket; }
    public Instant getEventTime() { return eventTime; }
    public UUID getEventId() { return eventId; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof DeviceEventKey)) return false;
        DeviceEventKey that = (DeviceEventKey) o;
        return Objects.equals(deviceId, that.deviceId)
                && Objects.equals(dayBucket, that.dayBucket)
                && Objects.equals(eventTime, that.eventTime)
                && Objects.equals(eventId, that.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(deviceId, dayBucket, eventTime, eventId);
    }
}
~~~

Annotation `@PrimaryKeyColumn` có hai thông tin đặc biệt quan trọng: `type = PARTITIONED/CLUSTERED` và `ordinal`. Đặt sai một trong hai có thể tạo bảng có **đường truy cập khác hẳn** ý định, dù code Java vẫn biên dịch.

### 5.2. Entity chứa khóa ghép

~~~java
package example.cassandra.model;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_device_day")
public class DeviceEvent {

    @PrimaryKey
    private DeviceEventKey id;

    @Column("event_type")
    private String eventType;

    @Column("payload")
    private String payload;

    public DeviceEvent() {
    }

    public DeviceEvent(DeviceEventKey id, String eventType, String payload) {
        this.id = id;
        this.eventType = eventType;
        this.payload = payload;
    }

    public DeviceEventKey getId() { return id; }
    public void setId(DeviceEventKey id) { this.id = id; }
    public String getEventType() { return eventType; }
    public void setEventType(String eventType) { this.eventType = eventType; }
    public String getPayload() { return payload; }
    public void setPayload(String payload) { this.payload = payload; }
}
~~~

Khi đọc bảng được tạo, cần xác nhận cấu trúc CQL giống bảng minh họa: hai thành phần partition key, hai clustering columns theo đúng thứ tự và loại dữ liệu tương ứng. Đừng chỉ kiểm tra có bảng `events_by_device_day` là coi như đạt.

### 5.3. Vì sao phải tách partition key khỏi clustering key?

Giả sử một người sửa annotation, biến cả `event_time` thành partition key. Khi đó từng thời điểm có thể nằm ở partition khác, làm mất khả năng lấy 100 event gần nhất trong **một partition**. Ngược lại, dùng `device_id` làm partition key duy nhất có thể khiến sự kiện tích lũy thành partition quá lớn.

**Metadata phải xuất phát từ query-driven design**, trong đó xem xét:

- Truy vấn nào luôn có điều kiện `WHERE`?
- Một partition có thể chứa bao nhiêu sự kiện sau một ngày, một tháng và một năm?
- Độ trễ, throughput, paging và số partition phải đọc có phù hợp với SLA?
- Có cần time bucket hoặc shard để tránh hot partition không?

## 6. Dùng bảng đã được tạo với repository và CassandraTemplate

Khi bảng tồn tại, repository và template truy cập cùng schema:

~~~java
package example.cassandra.repository;

import example.cassandra.model.DeviceEvent;
import example.cassandra.model.DeviceEventKey;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {
}
~~~

Để đọc theo toàn bộ khóa của một hàng:

~~~java
DeviceEventKey key = new DeviceEventKey(
        deviceId, LocalDate.parse("2026-11-25"),
        eventTime, eventId);

Optional<DeviceEvent> event = repository.findById(key);
~~~

Trong đó `deviceId`/`eventId` là `UUID` và `eventTime` là `Instant` được cung cấp từ nghiệp vụ. Muốn đọc nhiều sự kiện trong một ngày, dùng query tương ứng thay vì `findAll()`:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.cassandra.repository.Query;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {

    @Query("SELECT * FROM events_by_device_day " +
           "WHERE device_id = ?0 AND day_bucket = ?1 LIMIT 100")
    List<DeviceEvent> findRecentInDay(UUID deviceId, LocalDate dayBucket);
}
~~~

`CassandraTemplate` cũng có thể tạo câu truy vấn theo partition key:

~~~java
import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

// Ví dụ trong service đã inject CassandraTemplate template:
Query query = Query.query(Criteria.where("device_id").is(deviceId))
        .and(Criteria.where("day_bucket").is(dayBucket))
        .limit(100);

List<DeviceEvent> events = template.select(query, DeviceEvent.class);
~~~

Hai lối truy cập này chỉ hiệu quả khi bảng có **partition key phù hợp**. Nếu API sau đó cần tìm mọi sự kiện theo `event_type` trên toàn bộ thiết bị, việc thêm phương thức `findByEventType` vào repository không tự tạo ra một đường đọc tối ưu. Có thể cần **bảng truy cập khác** hoặc chỉ mục/giải pháp phân tích thích hợp.

## 7. Kiểm tra bảng thật sau khi ứng dụng khởi động

Có hai lớp cần kiểm chứng: **mapping của Java** và **schema Cassandra thực tế**. Không nên chỉ dựa vào log “Application started”.

### 7.1. Kiểm tra qua cqlsh

~~~text
-- Các lệnh DESCRIBE dưới đây là lệnh của cqlsh, không phải câu lệnh
-- CQL gửi trực tiếp qua prepared statement của Java Driver.
DESCRIBE KEYSPACE learning_data;
DESCRIBE TABLE learning_data.device_state_by_id;
DESCRIBE TABLE learning_data.events_by_device_day;
~~~

So sánh tên cột, kiểu CQL, partition key, thứ tự clustering, table options và keyspace. Có thể kiểm tra bằng truy vấn tới schema metadata:

~~~sql
SELECT table_name
FROM system_schema.tables
WHERE keyspace_name = 'learning_data';

SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'learning_data'
  AND table_name = 'events_by_device_day';
~~~

Trong `system_schema.columns`, `kind` cho biết cột là `partition_key`, `clustering`, `regular` hoặc dạng khác. `position` giúp kiểm tra thứ tự thành phần khóa; bản thân thao tác `SELECT` vào bảng system schema chỉ đọc metadata.

### 7.2. Kiểm tra bằng một truy vấn nhỏ

Ví dụ kiểm tra đường đọc theo partition key:

~~~sql
SELECT device_id, status, updated_at
FROM learning_data.device_state_by_id
WHERE device_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848;
~~~

Không có hàng trả về là tình huống hợp lệ nếu ID chưa được ghi; điều đó khác với lỗi `unconfigured table`, không tìm thấy keyspace hoặc lỗi authorization. Một truy vấn có thể chạy được vẫn cần được đo tải và xác minh key design trước khi đi production.

## 8. Những gì schema generation làm được và không làm được

Một entity có thể tạo bảng mới, nhưng **không phải mọi thay đổi annotation sẽ được chuyển tự động sang schema đang có**. Đây là điểm quyết định khi đưa dự án lên môi trường lâu dài.

| Thao tác trên entity | Kỳ vọng khi bảng **chưa tồn tại** | Khi bảng **đã tồn tại** với `CREATE_IF_NOT_EXISTS` |
|---|---|---|
| Thêm `@Table` mới | Có thể sinh bảng mới khi entity được scan | Bảng tương ứng đã có thì thường được giữ nguyên |
| Thêm `@Column` | Được tính vào định nghĩa bảng mới | Không bảo đảm tự `ALTER TABLE ADD` |
| Đổi tên `@Column` | Bảng mới dùng tên mới | Dữ liệu và schema cũ không tự migrate |
| Đổi kiểu Java/CQL | Bảng mới dùng mapping đang khai báo | Không tự chuyển đổi dữ liệu cũ |
| Đổi partition/clustering key | Bảng mới theo khóa mới | Không tự thay primary key tại chỗ |
| Bỏ thuộc tính khỏi entity | Không có cột đó trong bảng mới | Không tự xóa cột cũ |

**CREATE_IF_NOT_EXISTS không phải một công cụ phát hiện và xử lý schema drift**. Nếu bảng đã tồn tại nhưng mapping không tương thích, framework có thể khởi động hoặc truy vấn rồi thất bại khi mapping/driver thực hiện thao tác. Không suy luận rằng ứng dụng chạy lên thành công là schema đã được đồng bộ toàn diện.

### 8.1. Thêm cột thường trong production

Giả sử cần bổ sung `firmware_version` cho trạng thái thiết bị. Một migration có kiểm soát có thể là:

~~~sql
ALTER TABLE learning_data.device_state_by_id
ADD firmware_version text;
~~~

Sau khi schema đã cập nhật, ánh xạ entity:

~~~java
@Column("firmware_version")
private String firmwareVersion;
~~~

Trường mới có thể chưa có giá trị trên các hàng cũ. Cần quyết định cách xử lý giá trị rỗng, backfill (nếu cần) và khả năng tương thích khi một số instance ứng dụng vẫn chạy phiên bản cũ.

### 8.2. Đổi primary key thường cần bảng mới

Ví dụ ban đầu:

~~~sql
PRIMARY KEY ((device_id, day_bucket), event_time, event_id)
~~~

Sau đó ứng dụng muốn tìm “100 sự kiện mới nhất theo `event_type` của toàn bộ tenant”. Chỉ đổi `@PrimaryKeyColumn` trong Java **không chuyển dữ liệu cũ** và không làm Cassandra tự tổ chức lại partition. Thiết kế một bảng truy cập mới như `events_by_tenant_type_day`, với partition key có kiểm soát kích thước, thường phù hợp hơn.

Việc chuyển đổi cần dự tính **dual-write hoặc cập nhật projection**, backfill dữ liệu lịch sử, đối soát, đo hiệu năng và chuyển traffic đọc. Nếu thay đổi vị trí của một khóa trong bảng, hãy đánh giá tác động đến consistency, paging state và API hiện có.

## 9. Những bẫy thường gặp khi tạo bảng từ metadata

| Vấn đề | Vì sao xảy ra? | Cách xử lý |
|---|---|---|
| Không có bảng sau khi chạy app | `schema-action: NONE`, entity không được scan, app không dùng profile đã định nghĩa | Kiểm tra profile, property và mapping scan |
| App báo không thể tạo bảng | Không có quyền DDL hoặc sai keyspace | Provision keyspace trước, kiểm tra grants phù hợp |
| Tạo được bảng nhưng truy vấn báo thiếu partition key | Annotation khóa không đúng query pattern | Thiết kế lại primary key dựa trên yêu cầu truy vấn |
| Bảng có tên/cột khác kỳ vọng | Naming strategy hoặc tên annotation chưa rõ | Chỉ rõ `@Table`/`@Column`, xem schema thực tế |
| Đổi entity rồi bảng không đổi | `CREATE_IF_NOT_EXISTS` không migrate bảng hiện có | Thực hiện migration CQL có kiểm soát |
| Thiếu cột sau deploy | Migration chưa chạy hoặc schema chưa đồng thuận giữa node | Kiểm tra migration và schema agreement |
| Lỗi kiểu dữ liệu sau khi đổi Java type | Type conversion không tương thích với cột CQL cũ | Lập migration/đọc tương thích; không đổi type tùy ý |
| Dữ liệu test bị mất sau restart | Dùng chế độ tạo lại schema có tính phá hủy | Đổi sang `NONE` hoặc `CREATE_IF_NOT_EXISTS` theo môi trường |
| Startup chậm hoặc lỗi khi nhiều service cùng tạo bảng | Nhiều instance cùng thực hiện DDL, phải chờ schema propagation | Chạy migration riêng trước khi tăng số instance |

Một số lỗi thuộc **schema** chứ không thuộc **kết nối**. Ví dụ `unconfigured table` cho thấy session có thể đã kết nối nhưng bảng/không gian tên không đúng. Ngược lại, nếu driver chưa truy cập được contact points thì sửa annotation entity cũng không giải quyết được.

## 10. Vòng đời schema an toàn từ local đến production

Có thể phân chia trách nhiệm như sau:

~~~mermaid
flowchart TD
    A[Thiết kế truy vấn và khóa] --> B[Định nghĩa entity mapping]
    B --> C[Dev: tạo bảng mới qua schema-action]
    C --> D[Kiểm tra CQL thực tế + benchmark]
    D --> E[Viết migration CQL có phiên bản]
    E --> F[Staging: chạy migration bằng quyền DDL]
    F --> G[Kiểm tra schema agreement và ứng dụng]
    G --> H[Production: migration trước]
    H --> I[Chạy app với schema-action NONE]
    I --> J[Theo dõi query latency và schema drift]
~~~

Trong môi trường local dùng cơ sở dữ liệu dùng một lần, schema generation tiết kiệm thao tác thủ công. Trong môi trường sản xuất, các bản thay đổi schema nên được quản lý bằng **migration rõ ràng, có version, review và khả năng quan sát**. Vai trò ứng dụng thường chỉ cần quyền `SELECT`/`MODIFY`; tài khoản migration có quyền DDL được kiểm soát riêng.

### 10.1. Gợi ý cấu hình theo môi trường

~~~yaml
# application-local.yml
spring:
  cassandra:
    schema-action: CREATE_IF_NOT_EXISTS
~~~

~~~yaml
# application-prod.yml
spring:
  cassandra:
    schema-action: NONE
~~~

Các file cấu hình này chỉ minh họa **phần schema-action**; contact points, local datacenter, keyspace và xác thực/TLS vẫn phải được cấu hình phù hợp cho từng môi trường.

### 10.2. Vì sao hạn chế tự động thay đổi schema ở production?

- Tạo hoặc thay bảng là thay đổi có ảnh hưởng toàn cluster, không giống thao tác lưu một entity.
- Một deploy có nhiều instance có thể cùng cố thực hiện schema DDL.
- Không phải mọi thay đổi entity tương thích với các phiên bản service còn chạy.
- Đổi primary key và di chuyển dữ liệu thường cần bảng mới, backfill và chuyển đọc.
- Các chế độ recreate có thể xóa dữ liệu và gây gián đoạn.
- Schema migration phải được audit, giám sát và xử lý thất bại có chủ đích.

Không cần phải viết mọi truy vấn CRUD bằng CQL tay để quản lý schema an toàn. Ứng dụng vẫn có thể dùng Spring Data Cassandra repository, `CassandraTemplate` hoặc reactive API với bảng do migration tạo sẵn.

## 11. Tương quan với consistency, paging và hiệu năng

Schema được tạo tự động chỉ đảm bảo metadata đã được đưa thành định nghĩa bảng theo cơ chế được bật. **Nó không đo hoặc đảm bảo** hiệu năng của truy vấn.

Ví dụ `events_by_device_day` có partition key theo thiết bị/ngày. Nếu một thiết bị gửi hàng triệu sự kiện mỗi ngày, partition có thể quá lớn và tạo điểm nóng dù schema hoàn toàn hợp lệ. Có thể phải bucket theo giờ hoặc shard, đồng thời đánh đổi việc đọc nhiều partition và ghép kết quả.

### 11.1. Paging không đến từ annotation

Cassandra đọc các kết quả nhiều hàng theo **paging state**. Spring Data Cassandra/Java Driver có API phân trang tương ứng; `LIMIT 100` trong ví dụ chỉ giới hạn tổng số hàng trả, không thay thế thiết kế paging của một API cần đọc tiếp hàng nghìn bản ghi.

Khi sửa cấu trúc khóa hoặc đổi access table, không thể giả định paging state cũ tương thích với truy vấn mới. Thiết kế API phân trang phải gắn với truy vấn, giá trị tham số và cách dữ liệu được phân vùng.

### 11.2. Consistency không được quyết định bởi `@PrimaryKey`

`LOCAL_ONE` và `LOCAL_QUORUM` là lựa chọn consistency cho thao tác đọc/ghi; replication factor thuộc keyspace. Chúng không được suy ra từ việc dùng `@Table`, `@PrimaryKey` hay `CassandraRepository`.

Vì vậy cần phân biệt:

- **Mapping metadata:** tên bảng, cột, khóa và kiểu.
- **Schema/keyspace:** bảng thực tế và replication theo datacenter.
- **Statement/driver settings:** consistency, timeout, retry, fetch size.
- **Access pattern:** query theo partition key, khối lượng hàng, mức đồng thời.

Muốn đo hiệu năng, theo dõi p50/p95/p99 latency, timeout, partition size, tombstones, số trang dữ liệu và lượng request đồng thời. Tối ưu chỉ bằng cách thay schema action không thay thế benchmark dưới tải thực tế.

## 12. Bài tập thực hành

Yêu cầu sản phẩm: ứng dụng quản lý đặt vé cần lấy thông tin một lượt đặt theo `booking_id` và hiển thị 30 lượt đặt mới nhất của một khách theo từng tháng.

**Bài tập A — bảng tra cứu một booking**

1. Định nghĩa `@Table("bookings_by_id")`.
2. Dùng `UUID bookingId` làm `@PrimaryKey("booking_id")`.
3. Thêm `customer_id uuid`, `created_at timestamp`, `status text`.
4. Dự đoán CQL tạo bảng và kiểm tra nó sau khi bật `CREATE_IF_NOT_EXISTS` ở local.

Một schema tương đương:

~~~sql
CREATE TABLE IF NOT EXISTS learning_data.bookings_by_id (
    booking_id uuid PRIMARY KEY,
    customer_id uuid,
    created_at timestamp,
    status text
);
~~~

**Bài tập B — bảng liệt kê booking**

Truy vấn cần hỗ trợ:

~~~sql
SELECT booking_id, status, created_at
FROM bookings_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
LIMIT 30;
~~~

Hãy tạo `@PrimaryKeyClass` với `customer_id` và `month_bucket` là hai thành phần `PARTITIONED`, `created_at` là `CLUSTERED DESCENDING`, `booking_id` là `CLUSTERED` để phá hòa. CQL mong muốn:

~~~sql
CREATE TABLE IF NOT EXISTS learning_data.bookings_by_customer_month (
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    booking_id uuid,
    status text,
    PRIMARY KEY ((customer_id, month_bucket), created_at, booking_id)
) WITH CLUSTERING ORDER BY (created_at DESC, booking_id ASC);
~~~

**Bài tập C — schema evolution**

Giả sử sản phẩm thêm `payment_method text` sau khi dữ liệu đã tồn tại. Hãy giải thích vì sao việc thêm `@Column("payment_method")` rồi restart với `CREATE_IF_NOT_EXISTS` **không phải migration**. Viết `ALTER TABLE ... ADD payment_method text`, sau đó lên kế hoạch triển khai tương thích với bản ứng dụng trước và các hàng cũ chưa có giá trị.

### Câu hỏi tự kiểm tra

1. `@Table` có tự tạo bảng nếu `schema-action: NONE` không?
2. `@PrimaryKey` trên một UUID khác gì với `@PrimaryKeyClass` có partition và clustering columns?
3. Nếu bảng đã tồn tại, `CREATE_IF_NOT_EXISTS` có đồng bộ mọi thay đổi `@Column` không?
4. Bảng được tạo đúng metadata đã đảm bảo truy vấn `WHERE event_type = ?` hiệu quả chưa?
5. Vì sao phải tạo keyspace và xác định quyền DDL trước khi bật schema creation?
6. Vì sao production nên chạy migration có kiểm soát và để `schema-action: NONE`?

**Gợi ý đáp án:** (1) không; (2) khóa đơn định danh một partition/hàng, khóa ghép tách vị trí partition và thứ tự hàng; (3) không; (4) chưa, phải có đường đọc phù hợp; (5) framework cần đích và quyền hợp lệ; (6) để tránh DDL ngoài ý muốn, quản lý tương thích phiên bản và dữ liệu lịch sử.

## 13. Checklist trước khi dùng schema generation

- [ ] Entity có `@Table`, tên bảng và cột được ánh xạ rõ ràng.
- [ ] Primary key phản ánh query contract, phân biệt chính xác partition/clustering và thứ tự.
- [ ] Đã kiểm tra kích thước partition, time bucket, hot key và paging dự kiến.
- [ ] Keyspace đã tồn tại và có replication phù hợp; tài khoản có quyền đúng mục đích.
- [ ] Ứng dụng đã cấu hình đúng contact points, local datacenter và bảo mật.
- [ ] Entity nằm trong phạm vi mapping scan và profile đang bật đúng schema action.
- [ ] Chỉ dùng `CREATE_IF_NOT_EXISTS` cho môi trường chủ động cho phép khởi tạo bảng.
- [ ] Đã đọc lại schema bằng `DESCRIBE`/`system_schema` và so sánh với metadata.
- [ ] Thay đổi cột/khóa ở schema hiện hữu có migration, backfill và kế hoạch tương thích.
- [ ] Production có quy trình DDL riêng; không cấp quyền xóa bảng cho tài khoản ứng dụng.
- [ ] Đã kiểm tra truy vấn thực tế bằng repository/`CassandraTemplate` và theo dõi độ trễ.

## Tài liệu tham khảo

- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/cassandra/object-mapping.html).
- [Spring Data Cassandra — Cassandra Configuration](https://docs.spring.io/spring-data/cassandra/reference/cassandra/configuration.html).
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Spring Boot — Working with Cassandra](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.cassandra).
- [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/ddl.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).
