# MapId và truy cập entity có nhiều thành phần khóa

## 1. Bài toán: một hàng Cassandra có thể được định danh bằng nhiều giá trị

Trong **Spring Data Cassandra**, entity mapping cho phép ánh xạ một hàng của bảng Apache Cassandra thành đối tượng Java. Với bảng có khóa chính đơn, repository thường nhận một giá trị `UUID` hoặc `String` để tìm hàng. Nhưng Cassandra thường sử dụng **composite primary key** gồm nhiều thành phần: một hoặc nhiều **partition key columns** và có thể thêm các **clustering columns**.

Ví dụ hệ thống thu thập sự kiện cần đáp ứng hai truy vấn:

- Lấy **20 sự kiện mới nhất của một tenant trong tháng** để hiển thị trang lịch sử.
- Lấy **đúng một sự kiện** khi đã có đủ tenant, tháng, thời điểm và mã sự kiện để xem hoặc sửa nội dung.

Hai truy vấn có điểm chung là schema phải thiết kế theo truy vấn. Điểm khác là chúng dùng **những phần khác nhau của khóa chính**:

| Truy vấn | Đầu vào | Số hàng dự kiến | Cách truy cập phù hợp |
| --- | --- | --- | --- |
| Đọc chính xác một sự kiện | Toàn bộ primary key | Tối đa một hàng | `MapId` với `findById`/`selectOneById` hoặc khóa Java có kiểu |
| Đọc danh sách sự kiện của tenant/tháng | Toàn bộ partition key; không bắt buộc đủ clustering key | Nhiều hàng | CQL/`@Query` hoặc `CassandraTemplate`, hỗ trợ paging |
| Tìm sự kiện toàn hệ thống theo loại | Chỉ `event_type` | Có thể nhiều partition | Cần bảng/chỉ mục hoặc thiết kế tìm kiếm riêng; không phải truy vấn theo ID |

**Mục tiêu bài học** là dùng `MapId` để biểu diễn một khóa chính gồm nhiều cặp tên cột và giá trị, sau đó truy cập entity qua repository hoặc template. Bên cạnh API, ta cần hiểu khóa Cassandra để tránh dùng `MapId` như một bộ lọc tùy ý.

Bài dùng Spring Data Cassandra/Java Driver hiện đại, với các API `org.springframework.data.cassandra.*` và `com.datastax.oss.driver.api.core.*`. Chữ ký cụ thể nên được đối chiếu với phiên bản Spring Data trong dự án. Các ví dụ giả định keyspace và bảng đã được tạo trước khi ứng dụng chạy.

## 2. Nhắc lại mô hình khóa chính của Cassandra

Giả sử cụm học tập có một node thuộc data center `dc1`. Trong `cqlsh`, tạo keyspace và bảng:

```sql
-- Cấu hình học tập một node; production cần RF/DC theo topology thực tế.
CREATE KEYSPACE IF NOT EXISTS learning
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 1
};

CREATE TABLE IF NOT EXISTS learning.events_by_bucket (
    tenant uuid,
    bucket int,
    occurred timestamp,
    event uuid,
    event_type text,
    detail text,
    PRIMARY KEY ((tenant, bucket), occurred, event)
) WITH CLUSTERING ORDER BY (occurred DESC, event ASC);
```

Các cột có vai trò:

| Cột | Kiểu CQL | Vai trò |
| --- | --- | --- |
| `tenant` | `uuid` | Thành phần thứ nhất của **partition key** |
| `bucket` | `int` | Thành phần thứ hai của **partition key**, ví dụ `202611` |
| `occurred` | `timestamp` | **Clustering column** thứ nhất, sắp xếp giảm dần |
| `event` | `uuid` | **Clustering column** thứ hai, phân biệt sự kiện có cùng thời điểm |
| `event_type`, `detail` | `text` | Dữ liệu thông thường, không thuộc primary key |

**Primary key đầy đủ** của một hàng là bộ bốn giá trị:

```text
(tenant, bucket, occurred, event)
           |                |
   partition key      clustering key
   (tenant, bucket)    (occurred, event)
```

Trong CQL, cặp `(tenant, bucket)` xác định **partition**; `(occurred, event)` xác định vị trí/hàng bên trong partition. Cassandra tính token từ partition key để chọn tập replica, sau đó dùng clustering key để sắp xếp và định danh hàng. Spring Data chỉ ánh xạ cấu trúc ấy sang Java; mapping không thay đổi cách Cassandra định tuyến.

Ví dụ ghi hai sự kiện:

```sql
INSERT INTO learning.events_by_bucket (
    tenant, bucket, occurred, event, event_type, detail
) VALUES (
    11111111-1111-1111-1111-111111111111,
    202611,
    '2026-11-25T08:00:00Z',
    22222222-2222-2222-2222-222222222222,
    'ORDER_CREATED',
    'Tạo đơn'
);

INSERT INTO learning.events_by_bucket (
    tenant, bucket, occurred, event, event_type, detail
) VALUES (
    11111111-1111-1111-1111-111111111111,
    202611,
    '2026-11-24T08:00:00Z',
    33333333-3333-3333-3333-333333333333,
    'ORDER_PAID',
    'Thanh toán'
);
```

Có thể đọc **một hàng** với đủ bốn thành phần:

```sql
SELECT tenant, bucket, occurred, event, event_type, detail
FROM learning.events_by_bucket
WHERE tenant = 11111111-1111-1111-1111-111111111111
  AND bucket = 202611
  AND occurred = '2026-11-25T08:00:00Z'
  AND event = 22222222-2222-2222-2222-222222222222;
```

Hoặc đọc **cả partition, có giới hạn kết quả**:

```sql
SELECT tenant, bucket, occurred, event, event_type, detail
FROM learning.events_by_bucket
WHERE tenant = 11111111-1111-1111-1111-111111111111
  AND bucket = 202611
LIMIT 20;
```

Hai truy vấn đều hợp lý nhưng **không thể thay cho nhau**: đọc một hàng theo ID cần đủ thành phần khóa; đọc danh sách theo partition key có thể trả về nhiều hàng và cần kiểm soát page size, `LIMIT` và kích thước partition.

## 3. MapId là gì?

`MapId` là cách biểu diễn **ID nhiều thành phần bằng các cặp tên khóa và giá trị** trong Spring Data Cassandra. `BasicMapId` cung cấp cách tạo `MapId` thuận tiện, ví dụ dùng phương thức xây dựng `id(...).with(...)`.

Giả sử ID của hàng là:

```text
tenant   = 11111111-1111-1111-1111-111111111111
bucket   = 202611
occurred = 2026-11-25T08:00:00Z
event    = 22222222-2222-2222-2222-222222222222
```

Có thể hình dung `MapId` như một cấu trúc ánh xạ:

```text
{
  tenant   -> UUID(...),
  bucket   -> 202611,
  occurred -> Instant(...),
  event    -> UUID(...)
}
```

Đây là **định danh của một hàng**, không phải điều kiện `WHERE` linh hoạt cho mọi cột. Không đưa `event_type` hoặc `detail` vào `MapId` để lọc theo nội dung vì chúng không thuộc primary key.

Đặc điểm quan trọng:

- **Tên thành phần** phải tương ứng với các thuộc tính khóa mà Spring Data Cassandra mapping. Trong bài, tên Java, tên mapped column và tên CQL đều là `tenant`, `bucket`, `occurred` và `event` để tránh nhầm lẫn. Nếu dùng Java camelCase cùng `@PrimaryKeyColumn(name = "...")`, cần kiểm tra rõ tên property/column mà API của phiên bản sử dụng.
- **Giá trị phải đúng kiểu Java** mà converter/driver chấp nhận: `UUID` cho `uuid`, `Integer` cho `int`, `Instant` cho `timestamp` theo mapping được chọn. Không nên thay chúng bằng các chuỗi chỉ vì có thể in ra được.
- **Đủ các thành phần của ID** khi muốn tìm đúng một hàng. Thiếu một clustering column không còn biểu diễn ID đầy đủ theo mô hình của bảng.
- **Không tái sử dụng một MapId rồi sửa khóa trong nhiều luồng**. Tạo ID mới theo mỗi thao tác và coi bộ giá trị khóa là bất biến ở tầng nghiệp vụ.
- `MapId` thuận tiện cho mã truy cập động hoặc generic; khi khóa là một khái niệm nghiệp vụ quan trọng, một class `@PrimaryKeyClass` có kiểu thường dễ kiểm soát hơn.

## 4. Ánh xạ entity bằng nhiều @PrimaryKeyColumn

Cách đơn giản để dùng `MapId` là khai báo các thành phần khóa trực tiếp trong entity. Đoạn code sau dùng **tên field giống chính xác tên cột CQL**.

```java
package com.example.events.domain;

import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_bucket")
public class EventRow {

    @PrimaryKeyColumn(type = PrimaryKeyType.PARTITIONED, ordinal = 0)
    private UUID tenant;

    @PrimaryKeyColumn(type = PrimaryKeyType.PARTITIONED, ordinal = 1)
    private Integer bucket;

    @PrimaryKeyColumn(
        type = PrimaryKeyType.CLUSTERED,
        ordinal = 0,
        ordering = Ordering.DESCENDING
    )
    private Instant occurred;

    @PrimaryKeyColumn(
        type = PrimaryKeyType.CLUSTERED,
        ordinal = 1,
        ordering = Ordering.ASCENDING
    )
    private UUID event;

    @Column("event_type")
    private String eventType;

    private String detail;

    public EventRow() {
    }

    public EventRow(UUID tenant, Integer bucket, Instant occurred,
                    UUID event, String eventType, String detail) {
        this.tenant = tenant;
        this.bucket = bucket;
        this.occurred = occurred;
        this.event = event;
        this.eventType = eventType;
        this.detail = detail;
    }

    public UUID getTenant() { return tenant; }
    public void setTenant(UUID tenant) { this.tenant = tenant; }

    public Integer getBucket() { return bucket; }
    public void setBucket(Integer bucket) { this.bucket = bucket; }

    public Instant getOccurred() { return occurred; }
    public void setOccurred(Instant occurred) { this.occurred = occurred; }

    public UUID getEvent() { return event; }
    public void setEvent(UUID event) { this.event = event; }

    public String getEventType() { return eventType; }
    public void setEventType(String eventType) { this.eventType = eventType; }

    public String getDetail() { return detail; }
    public void setDetail(String detail) { this.detail = detail; }
}
```

Ở đây:

1. `@Table("events_by_bucket")` ánh xạ entity sang bảng tương ứng trong **keyspace mà session đang chọn**, ví dụ `learning`.
2. Hai trường `tenant` và `bucket` có `PrimaryKeyType.PARTITIONED`; thứ tự `ordinal` phân biệt vị trí trong composite partition key.
3. Hai trường `occurred`, `event` có `PrimaryKeyType.CLUSTERED`, dùng `ordering` để biểu diễn cách sắp xếp khi khai báo/đối chiếu schema.
4. `@Column("event_type")` ánh xạ `eventType` sang cột snake_case. Trường `detail` giữ nguyên tên.
5. Constructor rỗng và getter/setter giúp ví dụ dễ dùng với cơ chế mapping thông thường. Entity phục vụ ứng dụng lớn có thể dùng bất biến/constructor binding nếu phiên bản Spring Data hỗ trợ và được kiểm thử.
6. Các thành phần khóa cần có giá trị hợp lệ trước khi lưu; primary key của Cassandra không chấp nhận giá trị `null` trong thao tác ghi. Đổi khóa của entity là thay **định danh hàng**, không phải cập nhật thuộc tính thường.

**Lưu ý về schema:** Bảng đã được tạo bằng CQL ở phần 2. Nên để Spring Boot dùng `schema-action: NONE` khi schema do migration/script quản lý, tránh việc mapping tình cờ làm thay đổi schema production.

## 5. Tạo MapId và đọc một hàng với CassandraTemplate

### 5.1. Xây dựng đầy đủ khóa

`BasicMapId` cung cấp factory để tạo `MapId` theo các thuộc tính khóa:

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.BasicMapId;
import org.springframework.data.cassandra.core.mapping.MapId;

UUID tenantId = UUID.fromString(
    "11111111-1111-1111-1111-111111111111"
);
UUID eventId = UUID.fromString(
    "22222222-2222-2222-2222-222222222222"
);
Instant occurredAt = Instant.parse("2026-11-25T08:00:00Z");

MapId id = BasicMapId.id("tenant", tenantId)
    .with("bucket", 202611)
    .with("occurred", occurredAt)
    .with("event", eventId);
```

Khi CQL và Java dùng cùng tên bốn cột khóa như ví dụ, không có vấn đề phải chuyển `customerId` sang `customer_id`. Trong schema thực tế có `@PrimaryKeyColumn(name = "...")`, hãy đối chiếu mapping metadata và kiểm thử ID được tạo theo API của phiên bản Spring Data đang dùng; lỗi tên/kiểu thành phần có thể khiến thao tác select/delete chạy sai hoặc bị Cassandra từ chối.

**Không cần thêm các trường dữ liệu thường** `event_type` và `detail` vào ID. Chúng có thể thay đổi mà không thay đổi định danh của sự kiện.

### 5.2. Đọc bằng CassandraTemplate

Inject `CassandraTemplate` được tạo từ cấu hình Spring Data Cassandra:

```java
package com.example.events.service;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.data.cassandra.core.mapping.BasicMapId;
import org.springframework.data.cassandra.core.mapping.MapId;
import org.springframework.stereotype.Service;

import com.example.events.domain.EventRow;

@Service
public class EventLookupService {

    private final CassandraTemplate template;

    public EventLookupService(CassandraTemplate template) {
        this.template = template;
    }

    public Optional<EventRow> findOne(UUID tenant, int bucket,
                                       Instant occurred, UUID event) {
        MapId id = BasicMapId.id("tenant", tenant)
            .with("bucket", bucket)
            .with("occurred", occurred)
            .with("event", event);

        return Optional.ofNullable(
            template.selectOneById(id, EventRow.class)
        );
    }

    public void deleteOne(UUID tenant, int bucket,
                          Instant occurred, UUID event) {
        MapId id = BasicMapId.id("tenant", tenant)
            .with("bucket", bucket)
            .with("occurred", occurred)
            .with("event", event);

        template.deleteById(id, EventRow.class);
    }
}
```

`selectOneById` thể hiện **truy cập hàng có khóa đầy đủ**. Khi không tồn tại hàng, method trả `null` ở các phiên bản có hợp đồng phù hợp; ở ví dụ, chuyển sang `Optional` để caller xử lý rõ ràng. `deleteById` xóa đúng hàng tương ứng nếu ID hợp lệ; thao tác xóa trong Cassandra tạo tombstone, vì vậy không dùng delete hàng loạt mà không tính đến tải và chính sách retention.

### 5.3. Vì sao ID chỉ chứa partition key chưa đủ?

Đây là một ý tưởng dễ mắc lỗi:

```java
// Không dùng như ID của một hàng khi bảng còn clustering columns.
MapId partial = BasicMapId.id("tenant", tenantId)
    .with("bucket", 202611);
```

`partial` xác định **partition**; nó không xác định duy nhất sự kiện trong partition. Nó phù hợp để hình dung **điều kiện truy vấn theo partition**, nhưng không đáp ứng hợp đồng `findById`/`selectOneById` của một entity có primary key gồm bốn thành phần.

Nếu mục tiêu là “20 sự kiện mới nhất”, dùng phương thức query phù hợp thay vì lạm dụng ID chưa đầy đủ. Khi query có cả partition key, Cassandra có thể giới hạn công việc đọc trong đúng partition; vẫn cần `LIMIT`, paging và kiểm soát kích thước partition.

## 6. Truy cập MapId qua CassandraRepository

Repository giúp lớp service không phải trực tiếp gọi template cho thao tác CRUD. Với entity khai báo nhiều `@PrimaryKeyColumn` như phần 4, ID của repository có thể là `MapId`:

```java
package com.example.events.repository;

import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.MapId;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

import com.example.events.domain.EventRow;

public interface EventRepository
        extends CassandraRepository<EventRow, MapId> {

    @Query("SELECT * FROM events_by_bucket " +
           "WHERE tenant = ?0 AND bucket = ?1 LIMIT 20")
    List<EventRow> findLatestInBucket(UUID tenant, int bucket);
}
```

Cách dùng:

```java
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.BasicMapId;
import org.springframework.data.cassandra.core.mapping.MapId;

UUID tenantId = UUID.fromString(
    "11111111-1111-1111-1111-111111111111"
);
UUID eventId = UUID.fromString(
    "22222222-2222-2222-2222-222222222222"
);
Instant at = Instant.parse("2026-11-25T08:00:00Z");

MapId id = BasicMapId.id("tenant", tenantId)
    .with("bucket", 202611)
    .with("occurred", at)
    .with("event", eventId);

Optional<EventRow> exactRow = repository.findById(id);
List<EventRow> latestRows = repository.findLatestInBucket(tenantId, 202611);
```

| API | Cần thành phần khóa nào? | Khi nào dùng? |
| --- | --- | --- |
| `repository.findById(id)` | **Toàn bộ** khóa hàng gồm partition + clustering | Xem một sự kiện cụ thể |
| `repository.existsById(id)` | Toàn bộ khóa hàng | Kiểm tra hàng theo ID, lưu ý đọc phân tán và CL |
| `repository.deleteById(id)` | Toàn bộ khóa hàng | Xóa chính xác hàng, cân nhắc tombstone |
| `repository.save(entity)` | Entity có đầy đủ giá trị primary key | Ghi/upsert hàng theo khóa |
| `findLatestInBucket(tenant, bucket)` | Đủ **partition key** | Đọc danh sách trong partition, có giới hạn |
| `CassandraTemplate` hoặc CQL tùy chỉnh | Theo truy vấn cụ thể và giới hạn CQL | Query động, paging, cấu hình statement chi tiết |

Khi `repository.save(entity)` được gọi, Cassandra ghi theo **primary key của entity**, còn `MapId` giúp biểu diễn khóa để tìm/xóa. Các hoạt động lưu dữ liệu không tự tạo ra transaction ACID nhiều bảng, không đảm bảo unique theo nghiệp vụ giữa các partition và không giúp truy vấn thiếu partition key nhanh hơn.

**Chú ý:** `CassandraRepository`, các method của `CassandraTemplate` và một số lựa chọn ID phụ thuộc phiên bản Spring Data Cassandra. Khi nâng cấp phiên bản, cần kiểm tra API của phiên bản đang chạy và chạy integration test trên schema thật. Ý nghĩa của **khóa đầy đủ** và **partition key** không đổi.

## 7. So sánh MapId và @PrimaryKeyClass có kiểu

`MapId` không phải cách duy nhất biểu diễn khóa nhiều thành phần. Spring Data Cassandra còn hỗ trợ **composite primary key class**. Khi domain cần một kiểu khóa rõ ràng, có thể khai báo:

```java
import java.io.Serializable;
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class EventKey implements Serializable {

    @PrimaryKeyColumn(
        type = PrimaryKeyType.PARTITIONED, ordinal = 0
    )
    private UUID tenant;

    @PrimaryKeyColumn(
        type = PrimaryKeyType.PARTITIONED, ordinal = 1
    )
    private Integer bucket;

    @PrimaryKeyColumn(
        type = PrimaryKeyType.CLUSTERED,
        ordinal = 0,
        ordering = Ordering.DESCENDING
    )
    private Instant occurred;

    @PrimaryKeyColumn(
        type = PrimaryKeyType.CLUSTERED,
        ordinal = 1,
        ordering = Ordering.ASCENDING
    )
    private UUID event;

    // Bổ sung constructor, getter/setter, equals và hashCode.
}
```

Entity tương ứng với cách này khai báo một trường `@PrimaryKey`:

```java
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_bucket")
public class EventWithTypedKey {

    @PrimaryKey
    private EventKey key;

    private String detail;

    // Bổ sung constructor, getter/setter và field khác khi dùng thực tế.
}
```

Khi dùng typed key, repository tương ứng sẽ dùng `CassandraRepository<EventWithTypedKey, EventKey>`. Hai kiểu entity `EventRow` (nhiều `@PrimaryKeyColumn` trực tiếp) và `EventWithTypedKey` (một `@PrimaryKey`) là **hai ví dụ mapping thay thế cho cùng schema**; không đăng ký và sử dụng cả hai mà không xác định rõ trách nhiệm. Trong dự án thật, chọn một cách biểu diễn nhất quán và hoàn thiện code cho kiểu đã chọn.

| Tiêu chí | `MapId` | `@PrimaryKeyClass` |
| --- | --- | --- |
| Khóa biểu diễn bằng | Cặp tên thuộc tính và giá trị | Một kiểu Java có field xác định |
| Kiểm tra của Java compiler | Không phát hiện mọi lỗi thiếu/sai tên khóa khi biên dịch | Type safety tốt hơn cho phần tên và kiểu field |
| Phù hợp khi | Truy cập generic/dynamic, một số tiện ích repository/template | Domain có composite key thường xuyên sử dụng, cần API rõ ràng |
| Đổi tên một thành phần | Phải sửa các chuỗi tạo ID và kiểm thử | Refactor field/class rõ hơn, nhưng vẫn phải đồng bộ CQL |
| Tính dễ đọc ở service | Tường minh khi ít trường; dài dòng khi nhiều trường | Gọn khi có constructor/factory hợp lệ |
| Chi phí thiết kế | Không cần thêm class khóa riêng | Cần thiết kế constructor, equality và lifecycle của khóa |

**Khuyến nghị thiết kế:** Với khóa gồm nhiều thành phần được truyền qua nhiều lớp, typed key thường giúp giới hạn sai sót tốt hơn. `MapId` phù hợp để hiểu cách Spring Data mô tả identity và cho các thao tác trực tiếp hoặc trường hợp generic. Lựa chọn là ở API Java; nó không đổi cấu trúc vật lý của Cassandra.

## 8. Các lỗi MapId phổ biến và cách sửa

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `findById` không tìm thấy hàng dù CQL thấy dữ liệu | Thiếu/sai một thành phần khóa; timestamp không đúng; keyspace/CL khác. | In thông tin khóa ở mức an toàn; đối chiếu đủ bốn giá trị, kiểu và keyspace trong CQL. |
| CQL báo `InvalidQueryException` hoặc lỗi restriction | ID thiếu khóa, tên property không khớp, query lọc sai clustering columns. | Đọc `PRIMARY KEY` bằng `DESCRIBE TABLE`; so sánh với `MapId` và mapping. |
| Lỗi chuyển đổi kiểu | `String` dùng thay `UUID`/`Instant`; sai custom converter. | Tạo giá trị typed rõ ràng và kiểm tra mapping converter. |
| Repository bean không tạo được | Sai package `@EnableCassandraRepositories` hoặc mapping metadata không hợp lệ. | Xem cấu hình scan repository/entity và lỗi startup. |
| Đọc danh sách quá chậm | Dùng truy vấn ngoài partition key, partition quá rộng hoặc nhiều tombstone. | Đo query, kích thước partition, page size và cải thiện mô hình bảng. |
| Sau `save` có thêm hàng thay vì cập nhật hàng cũ | Thay đổi một trong các thành phần primary key. | Giữ ID ổn định; muốn chuyển khóa phải coi đó là ghi khóa mới và xử lý hàng cũ. |
| Xóa nhiều hàng làm đọc chậm | Nhiều tombstone phát sinh từ thao tác delete/TTL. | Xem retention, số lần xóa, compaction/repair với nhóm vận hành. |
| Đọc thấy dữ liệu cũ hoặc timeout | Replica chưa đồng bộ, CL không đáp ứng hoặc node chậm. | Kiểm tra read/write CL, RF/DC, latency và retry, không đổ lỗi ngay cho `MapId`. |

### Hai lỗi thiết kế cần tránh

**Lỗi 1 — Xem MapId là cơ chế truy vấn tự do:** Tạo `MapId` với chỉ `event_type` rồi kỳ vọng Cassandra tìm tất cả sự kiện theo loại. `event_type` không phải primary key, nên yêu cầu đó cần **mô hình bảng hoặc chỉ mục thích hợp**.

**Lỗi 2 — Nhầm định danh hàng với định danh partition:** Cặp `(tenant, bucket)` đủ để xác định một partition, nhưng **chưa đủ** để xác định hàng khi `occurred` và `event` là clustering columns. Để đọc danh sách trong partition, dùng CQL query có predicate và paging; để đọc/xóa hàng cụ thể, cung cấp đủ ID.

## 9. Paging, consistency và hiệu năng với khóa tổng hợp

### 9.1. Phân trang nằm ở truy vấn danh sách, không nằm ở MapId

`findById` không phải API tải danh sách và không cần page size theo nghĩa nhiều hàng. Ngược lại, truy vấn `findLatestInBucket(tenant, bucket)` có thể trả nhiều hàng theo `occurred DESC`. Khi dữ liệu tăng, cần:

- Giới hạn dữ liệu mỗi query bằng `LIMIT` phù hợp với nhu cầu, nhưng không coi `LIMIT` là cơ chế phân trang tự động.
- Cấu hình **fetch page size** và dùng **paging state** của Java Driver/Spring Data khi cần lấy trang kế tiếp.
- Không giả lập `OFFSET` như SQL quan hệ: Cassandra không tối ưu nhảy qua một lượng hàng lớn bằng offset.
- Đo kích thước partition và phân bucket theo tải thực tế, không chỉ theo tháng một cách máy móc.
- Tránh đọc/xóa quá nhiều dữ liệu có tombstone vì có thể làm độ trễ tăng mạnh.

Ví dụ query theo partition với Java Driver:

```java
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public final class EventPageReader {

    private final CqlSession session;
    private final PreparedStatement findLatest;

    public EventPageReader(CqlSession session) {
        this.session = session;
        this.findLatest = session.prepare(
            "SELECT tenant, bucket, occurred, event, event_type, detail " +
            "FROM learning.events_by_bucket " +
            "WHERE tenant = ? AND bucket = ? LIMIT 100"
        );
    }

    public ResultSet find(UUID tenantId, int bucket) {
        return session.execute(
            findLatest.bind(tenantId, bucket)
                .setPageSize(20)
        );
    }
}
```

`LIMIT 100` đặt **số hàng tối đa** trả về của query, còn `setPageSize(20)` điều khiển **số hàng trong một lần fetch**. Tùy phiên bản Java Driver, việc lặp `ResultSet` có thể tự tải các trang kế tiếp; API bất đồng bộ và paging thủ công sẽ có cơ chế lưu/khôi phục paging state khác. Không gửi raw paging state cho client mà không kiểm soát và không dùng nó như một khóa phân trang ổn định vĩnh viễn.

### 9.2. Consistency level không thuộc MapId

`MapId` chỉ biểu diễn ID. Số replica cần phản hồi phụ thuộc vào **RF**, **read/write CL** và topology. Ví dụ trong một DC có RF = 3, đọc `LOCAL_QUORUM` cần hai replica ở local DC trả về phản hồi phù hợp; nếu một replica mất kết nối nhưng hai replica còn lại đáp ứng, request vẫn có thể thành công.

- Chọn CL theo yêu cầu nghiệp vụ: đọc sau ghi, khả năng chịu lỗi, latency và topology.
- Giữ định danh event và idempotency key ổn định nếu phải retry thao tác ghi.
- Hiểu `WriteTimeout` có thể xảy ra sau khi một số replica đã áp dụng mutation; timeout không chứng minh chưa ghi.
- Đánh giá đọc/ghi concurrent, timestamps và LWT nếu cần thao tác điều kiện; ID nhiều thành phần không tự tạo tính linearizable.
- Với môi trường học một node RF = 1, không suy ra các bảo đảm phân tán của cluster RF = 3.

### 9.3. Composite key không làm mọi truy vấn đều tốt

Thậm chí với ID đầy đủ, một số thao tác vẫn có thể bị ảnh hưởng bởi network, consistency level và node chậm. Khi query nhiều hàng, việc chọn partition key không cân bằng cũng tạo **hot partition**. Không dùng số lượng thành phần khóa làm thước đo hiệu năng; hãy dựa trên mẫu truy vấn, phân bố dữ liệu, cardinality, kích thước partition và metrics.

## 10. Thực hành đối chiếu CQL, repository và template

Có thể kiểm tra bằng một Cassandra lab với keyspace `learning`, bảng đã tạo và dữ liệu từ phần 2. Spring Boot 3.x có thể cấu hình kết nối như sau:

```yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: dc1
    keyspace-name: learning
    schema-action: NONE
```

Nếu ứng dụng chạy bên trong cùng Docker network với Cassandra, thay `127.0.0.1` bằng tên service Cassandra theo Compose network. Driver cần local DC khớp `system.local`; `schema-action: NONE` giúp tránh tạo/sửa bảng ngoài kế hoạch.

Kiểm thử theo thứ tự:

1. Chạy `DESCRIBE TABLE learning.events_by_bucket;` trong `cqlsh`, ghi lại chính xác partition/clustering key và kiểu cột.
2. Chạy `SELECT` có đủ bốn giá trị khóa, xác nhận trả về một hàng `ORDER_CREATED`.
3. Tạo `MapId` bằng `BasicMapId` với bốn giá trị tương ứng và gọi `CassandraTemplate.selectOneById`, so sánh kết quả với CQL.
4. Gọi `repository.findById(id)` để xác nhận repository dùng cùng mapping.
5. Gọi `repository.findLatestInBucket(tenant, 202611)` để đọc hai sự kiện theo `occurred DESC`. Giải thích vì sao method này **không cần** `occurred` và `event`.
6. Thử tạo `MapId` thiếu `event` **chỉ trong môi trường lab**; quan sát kết quả/lỗi và ghi nhận rằng đây không phải định danh hàng đầy đủ.
7. Kiểm tra khi ID có timestamp khác một mili giây với dữ liệu đã lưu: do giá trị clustering key khác, đó là một định danh khác.
8. Nếu cần cập nhật `detail`, giữ nguyên cả bốn thành phần primary key. Xác minh không tạo thêm hàng với khóa mới.
9. Tạo thêm dữ liệu ở một bucket khác; xác minh query partition với `bucket = 202611` không trả về bucket kia.

**Lưu ý về thời gian:** CQL `timestamp` lưu độ chính xác tới mili giây. Khi tạo `Instant` từ nguồn có nano giây, phải xác định quy tắc làm tròn/cắt về mili giây khi mapping và khớp key truy vấn; không dùng thời gian hiện tại để dựng lại một clustering key đã được lưu nếu nghiệp vụ cần đọc đúng một hàng.

### Checklist cho code review

- [ ] Đã xác định **đầy đủ partition key và clustering columns** từ DDL.
- [ ] Các trường `@PrimaryKeyColumn` có `PrimaryKeyType` và `ordinal` đúng với schema.
- [ ] `MapId` sử dụng đúng tên mapped properties và đúng kiểu giá trị; không chứa cột không thuộc khóa.
- [ ] Đọc/xóa một hàng bằng `findById`/`selectOneById` có **đủ tất cả thành phần khóa**.
- [ ] Đọc danh sách dùng query theo partition key, có `LIMIT` và paging khi cần.
- [ ] Dùng typed key `@PrimaryKeyClass` khi muốn API domain có type safety tốt hơn.
- [ ] Không đổi primary key như cập nhật thông thường; có kế hoạch khi cần chuyển khóa.
- [ ] Read/write CL, timeout, retry và idempotency được quyết định theo yêu cầu nghiệp vụ.
- [ ] Có test trên schema CQL thực tế, không chỉ unit test tạo map giá trị.
- [ ] Có theo dõi partition size, tombstone và latency cho truy vấn thực tế.

**Kết luận:** `MapId` là công cụ Spring Data Cassandra giúp diễn đạt **identity của một hàng có composite primary key** bằng nhiều giá trị. Để sử dụng đúng, phải hiểu ranh giới giữa **partition key** và **clustering columns**: tìm một hàng cần đủ định danh, còn đọc danh sách cần một truy vấn được thiết kế theo partition và được kiểm soát về paging, consistency lẫn hiệu năng.
