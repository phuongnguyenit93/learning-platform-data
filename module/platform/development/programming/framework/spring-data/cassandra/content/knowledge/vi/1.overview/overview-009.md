# Ví dụ xuyên suốt: lưu sự kiện thiết bị theo thời gian

> **Phạm vi:** Spring Data Cassandra — từ nhu cầu truy vấn đến thiết kế bảng CQL, ánh xạ entity, ghi/đọc bằng repository và `CassandraTemplate`, phân trang, nhất quán và vận hành.

## 1. Bài toán và kết quả cần đạt

Giả sử một nền tảng IoT nhận sự kiện từ các thiết bị đo nhiệt độ, độ ẩm hoặc trạng thái máy. Mỗi sự kiện có:

- `deviceId`: mã thiết bị, kiểu UUID.
- `eventId`: mã sự kiện do nguồn phát sinh, ổn định khi gửi lại.
- `eventTime`: thời điểm **sự kiện xảy ra** (UTC).
- `eventType`: loại sự kiện, ví dụ `TEMPERATURE`, `BATTERY_LOW`.
- `payload`: nội dung đo hoặc thông tin phụ (ví dụ JSON).
- `receivedAt`: thời điểm máy chủ nhận sự kiện, dùng để quan sát độ trễ.

Hệ thống cần ghi liên tục và đáp ứng ba thao tác chủ đạo:

1. Hiển thị **50 sự kiện mới nhất của một thiết bị trong một ngày UTC**, theo thời gian giảm dần.
2. Xem các sự kiện của thiết bị đó trong **một khoảng thời gian thuộc một ngày**.
3. Duyệt tiếp các sự kiện cũ bằng **con trỏ phân trang**, không dùng offset.

Một yêu cầu khác là xem lịch sử trong bảy ngày. Khi đó ứng dụng cần đọc nhiều phân vùng ngày và ghép kết quả. Việc tra cứu chỉ theo `eventId` hoặc tổng hợp tất cả thiết bị theo loại sự kiện là *truy vấn khác*; nếu thật sự cần với tần suất cao, nên thiết kế thêm bảng phục vụ truy vấn ấy.

Sau bài học, bạn sẽ biết vì sao khóa chính phải được chọn theo luồng truy vấn, cách dùng `@PrimaryKeyClass` và `@PrimaryKeyColumn`, khi nào dùng repository hay `CassandraTemplate`, cùng những giới hạn về tính nhất quán, kích thước partition và paging.

## 2. Thiết kế dữ liệu bắt đầu từ truy vấn

Apache Cassandra phân phối dữ liệu theo **partition key** và sắp xếp bản ghi trong một partition theo **clustering columns**. Không nên xây bảng như một mô hình quan hệ rồi hy vọng có thể lọc tùy ý về sau.

| Nhu cầu | Điều kiện truy vấn cần có | Quyết định thiết kế |
| --- | --- | --- |
| Lịch sử một thiết bị trong ngày | `device_id` + `bucket_day` | Hai cột tạo **partition key tổng hợp** |
| Sự kiện mới nhất trước | Phân vùng đã biết, thứ tự thời gian giảm dần | `event_time` là clustering column `DESC` |
| Nhiều sự kiện trùng millisecond | Cần phân biệt bản ghi | `event_id` là clustering column thứ hai |
| Đọc một khoảng giờ | `event_time >= from` và `event_time < to` | Lọc theo dải clustering column sau khi đã chỉ rõ partition |
| Lịch sử nhiều ngày | Một partition cho mỗi ngày | Gửi nhiều truy vấn có giới hạn, ghép kết quả tại ứng dụng |

Khóa chính được chọn:

`PRIMARY KEY ((device_id, bucket_day), event_time, event_id)`

Dấu ngoặc kép quanh `(device_id, bucket_day)` biểu thị **cặp partition key**. Hai cột phía sau xác định thứ tự và tính duy nhất trong partition.

~~~text
Thiết bị A
├── ngày UTC 2026-11-24 → partition (A, 2026-11-24)
│   ├── 23:59:30 / event-3
│   └── 09:15:10 / event-2
└── ngày UTC 2026-11-25 → partition (A, 2026-11-25)
    ├── 10:05:00 / event-5
    └── 08:00:00 / event-4

Thiết bị B → các partition riêng, dù cùng ngày.
~~~

**Vì sao cần `bucket_day`?** Nếu partition chỉ có `device_id`, một thiết bị hoạt động nhiều năm có thể tạo partition cực lớn. Chia theo ngày giới hạn lượng dữ liệu mỗi partition, đồng thời vẫn hỗ trợ truy vấn thường dùng. Kích thước bucket phải dựa trên sản lượng thực tế: thiết bị tạo hàng triệu sự kiện mỗi giờ có thể cần bucket theo giờ hoặc cơ chế phân tán khác. Không có kích thước bucket đúng cho mọi hệ thống.

Ví dụ một thiết bị gửi một sự kiện mỗi 30 giây tạo khoảng **2.880 sự kiện/ngày**. Với bản ghi trung bình giả định 500 byte, riêng payload thô chiếm xấp xỉ 1,44 MB/ngày, chưa tính overhead lưu trữ, replication, index và compaction. Đây chỉ là phép ước lượng ban đầu; phải đo dữ liệu thực tế.

## 3. Tạo keyspace và bảng bằng CQL

Ví dụ dưới đây dùng Cassandra cục bộ, một node, để học tập:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': '1'
};

CREATE TABLE IF NOT EXISTS telemetry.device_events (
    device_id   uuid,
    bucket_day  date,
    event_time  timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    received_at timestamp,
    PRIMARY KEY ((device_id, bucket_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Trong triển khai nhiều node, chọn `NetworkTopologyStrategy` với hệ số nhân bản phù hợp **tên datacenter thực tế**. Ví dụ `{'class': 'NetworkTopologyStrategy', 'dc1': 3}` chỉ đúng nếu datacenter thật sự tên `dc1` và có đủ node. `SimpleStrategy` với RF=1 ở trên chỉ dành cho môi trường học tập.

Ba điểm quan trọng:

- `date` lưu **ngày bucket theo UTC**, không lấy ngày theo múi giờ máy chủ.
- `timestamp` của Cassandra có độ chính xác **millisecond**. Cần chuẩn hóa `Instant` trước khi đưa vào khóa để tránh hai giá trị Java khác nhau nhưng có cùng giá trị lưu trong Cassandra.
- `payload` đang là `text` để ví dụ gọn. Nếu thường xuyên tìm theo nhiệt độ, trạng thái hoặc một trường khác, cân nhắc lưu cột cụ thể và tạo bảng theo cách truy vấn; không kỳ vọng Cassandra lọc hiệu quả bên trong chuỗi JSON.

Dữ liệu mẫu (UUID cố định nhằm minh họa):

~~~sql
INSERT INTO telemetry.device_events
(device_id, bucket_day, event_time, event_id, event_type, payload, received_at)
VALUES (
  aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa, '2026-11-25',
  '2026-11-25T08:00:00Z', bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb,
  'TEMPERATURE', '{"celsius": 25.1}', '2026-11-25T08:00:01Z'
);

INSERT INTO telemetry.device_events
(device_id, bucket_day, event_time, event_id, event_type, payload, received_at)
VALUES (
  aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa, '2026-11-25',
  '2026-11-25T10:05:00Z', cccccccc-cccc-4ccc-8ccc-cccccccccccc,
  'BATTERY_LOW', '{"percent": 12}', '2026-11-25T10:05:03Z'
);
~~~

Đọc sự kiện của một ngày theo thứ tự đã được định nghĩa ở bảng:

~~~sql
SELECT event_time, event_id, event_type, payload
FROM telemetry.device_events
WHERE device_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND bucket_day = '2026-11-25'
LIMIT 50;
~~~

Kết quả hiển thị `10:05` trước `08:00` mà không cần sort toàn bộ dữ liệu. Đọc trong khoảng `[08:00, 09:00)`:

~~~sql
SELECT *
FROM telemetry.device_events
WHERE device_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND bucket_day = '2026-11-25'
  AND event_time >= '2026-11-25T08:00:00Z'
  AND event_time <  '2026-11-25T09:00:00Z';
~~~

Không viết truy vấn chỉ có `event_type = 'BATTERY_LOW'` trên bảng này và không thêm `ALLOW FILTERING` để che vấn đề. Bảng không được thiết kế để tìm kiếm toàn cục theo loại sự kiện. Tương tự, chỉ tìm theo `device_id` mà thiếu `bucket_day` không đáp ứng đầy đủ partition key của thiết kế hiện tại.

## 4. Kết nối ứng dụng Spring Boot

Ví dụ dùng Java 17+ và Spring Boot 3.x hoặc phiên bản tương thích với Spring Data Cassandra hiện hành. Thêm starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'
}
~~~

Cấu hình `application.yml`:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: telemetry
    schema-action: none
~~~

`datacenter1` phải trùng tên datacenter Cassandra đang chạy (kiểm tra bằng công cụ quản trị cluster). `schema-action: none` giữ việc tạo/sửa schema thuộc bước migration có kiểm soát; chạy lệnh CQL ở mục 3 trước khi khởi động ứng dụng. Với ứng dụng thực tế, cấu hình thêm xác thực, TLS, timeout và connection settings phù hợp hạ tầng.

Spring Boot tự cấu hình `CqlSession`, `CassandraTemplate` và repository khi starter cùng cấu hình hợp lệ. `CqlSession` phục vụ thao tác CQL ở tầng driver; repository phù hợp CRUD, còn template giúp biểu diễn các truy vấn động có kiểm soát.

## 5. Ánh xạ khóa chính và entity

Đặt mỗi lớp sau vào tệp Java riêng trong package của ứng dụng.

**`DeviceEventKey.java`**

~~~java
import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class DeviceEventKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(
        name = "device_id", ordinal = 0, type = PrimaryKeyType.PARTITIONED)
    private UUID deviceId;

    @PrimaryKeyColumn(
        name = "bucket_day", ordinal = 1, type = PrimaryKeyType.PARTITIONED)
    private LocalDate bucketDay;

    @PrimaryKeyColumn(
        name = "event_time", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant eventTime;

    @PrimaryKeyColumn(
        name = "event_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.ASCENDING)
    private UUID eventId;

    public DeviceEventKey() { }

    public DeviceEventKey(UUID deviceId, LocalDate bucketDay,
                          Instant eventTime, UUID eventId) {
        this.deviceId = deviceId;
        this.bucketDay = bucketDay;
        this.eventTime = eventTime;
        this.eventId = eventId;
    }

    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID value) { deviceId = value; }

    public LocalDate getBucketDay() { return bucketDay; }
    public void setBucketDay(LocalDate value) { bucketDay = value; }

    public Instant getEventTime() { return eventTime; }
    public void setEventTime(Instant value) { eventTime = value; }

    public UUID getEventId() { return eventId; }
    public void setEventId(UUID value) { eventId = value; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof DeviceEventKey that)) return false;
        return Objects.equals(deviceId, that.deviceId)
            && Objects.equals(bucketDay, that.bucketDay)
            && Objects.equals(eventTime, that.eventTime)
            && Objects.equals(eventId, that.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(deviceId, bucketDay, eventTime, eventId);
    }
}
~~~

**`DeviceEvent.java`**

~~~java
import java.time.Instant;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("device_events")
public class DeviceEvent {
    @PrimaryKey
    private DeviceEventKey key;

    @Column("event_type")
    private String eventType;

    @Column("payload")
    private String payload;

    @Column("received_at")
    private Instant receivedAt;

    public DeviceEvent() { }

    public DeviceEvent(DeviceEventKey key, String eventType,
                       String payload, Instant receivedAt) {
        this.key = key;
        this.eventType = eventType;
        this.payload = payload;
        this.receivedAt = receivedAt;
    }

    public DeviceEventKey getKey() { return key; }
    public void setKey(DeviceEventKey value) { key = value; }

    public String getEventType() { return eventType; }
    public void setEventType(String value) { eventType = value; }

    public String getPayload() { return payload; }
    public void setPayload(String value) { payload = value; }

    public Instant getReceivedAt() { return receivedAt; }
    public void setReceivedAt(Instant value) { receivedAt = value; }
}
~~~

Ánh xạ này giữ đúng bốn cột của `PRIMARY KEY` trong CQL. `@PrimaryKeyClass` biểu diễn khóa tổng hợp và cần `equals/hashCode`. `@PrimaryKey` đặt trong entity liên kết khóa với repository; `@Column` ánh xạ những cột dữ liệu còn lại. Nếu bạn thay tên cột, thứ tự `ordinal` hay hướng `ordering`, phải đồng bộ với schema CQL.

## 6. Ghi và đọc bằng CassandraRepository

Repository đơn giản hóa thao tác lưu và truy vấn đã định nghĩa sẵn. Ở đây dùng một truy vấn CQL cụ thể để tránh hiểu nhầm rằng ứng dụng có thể truy vấn mọi field theo tên phương thức.

**`DeviceEventRepository.java`**

~~~java
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Consistency;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {

    @Consistency(DefaultConsistencyLevel.LOCAL_QUORUM)
    @Query("SELECT * FROM device_events "
         + "WHERE device_id = ?0 AND bucket_day = ?1")
    Slice<DeviceEvent> findByDeviceAndDay(
        UUID deviceId, LocalDate bucketDay, Pageable page);
}
~~~

Các placeholder `?0` và `?1` được Spring Data Cassandra gắn với tham số truy vấn. `Pageable` là tham số đặc biệt cho paging, không phải cột CQL. Truy vấn chỉ chạm một partition; thứ tự giảm dần đã được xác định bởi `CLUSTERING ORDER BY`.

**`DeviceEventService.java`**

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.stereotype.Service;

@Service
public class DeviceEventService {
    private final DeviceEventRepository repository;

    public DeviceEventService(DeviceEventRepository repository) {
        this.repository = repository;
    }

    public DeviceEvent save(UUID deviceId, UUID eventId,
                            Instant occurredAt, String type, String payload) {
        Objects.requireNonNull(deviceId);
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(occurredAt);

        // Cassandra timestamp có độ chính xác millisecond.
        Instant time = occurredAt.truncatedTo(ChronoUnit.MILLIS);
        LocalDate utcDay = LocalDate.ofInstant(time, ZoneOffset.UTC);

        DeviceEventKey key =
            new DeviceEventKey(deviceId, utcDay, time, eventId);

        return repository.save(
            new DeviceEvent(key, type, payload, Instant.now()));
    }

    public Slice<DeviceEvent> firstPage(UUID deviceId, LocalDate utcDay) {
        return repository.findByDeviceAndDay(
            deviceId, utcDay, CassandraPageRequest.first(50));
    }

    public Slice<DeviceEvent> nextPage(
            UUID deviceId, LocalDate utcDay, Pageable continuation) {
        return repository.findByDeviceAndDay(
            deviceId, utcDay, continuation);
    }
}
~~~

Gọi nghiệp vụ, ví dụ trong một controller hay tác vụ nhập dữ liệu:

~~~java
UUID deviceId = UUID.fromString("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
UUID eventId = UUID.fromString("dddddddd-dddd-4ddd-8ddd-dddddddddddd");

service.save(
    deviceId, eventId, Instant.parse("2026-11-25T10:15:00Z"),
    "TEMPERATURE", "{\"celsius\": 26.4}");

Slice<DeviceEvent> first =
    service.firstPage(deviceId, LocalDate.parse("2026-11-25"));

if (first.hasNext()) {
    Slice<DeviceEvent> second =
        service.nextPage(deviceId, LocalDate.parse("2026-11-25"),
                         first.nextPageable());
}
~~~

**Tính lặp lại khi ghi:** nếu thiết bị gửi lại cùng `deviceId`, `eventId` và `eventTime` (sau chuẩn hóa) thì toàn bộ khóa chính giữ nguyên; thao tác ghi thông thường cập nhật cùng row thay vì chèn row mới. Hãy dùng ID sự kiện ổn định do nguồn cung cấp. Nếu mỗi lần retry lại tạo UUID mới, hoặc thay đổi timestamp, Cassandra sẽ xem đó là khóa khác. Không được suy diễn rằng `save` cung cấp transaction hoặc kiểm tra trùng tuyệt đối giữa nhiều khóa.

## 7. Truy vấn khoảng thời gian bằng CassandraTemplate

Khi bộ lọc thay đổi linh hoạt, `CassandraTemplate` giúp tạo truy vấn bằng `Query` và `Criteria`. Ví dụ dưới đây luôn giới hạn **cùng một ngày UTC** và yêu cầu khoảng thời gian theo nguyên tắc `[from, to)`.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class DeviceEventLookup {
    private final CassandraTemplate template;

    public DeviceEventLookup(CassandraTemplate template) {
        this.template = template;
    }

    public List<DeviceEvent> withinDay(
            UUID deviceId, Instant from, Instant to) {
        if (from == null || to == null || !from.isBefore(to)) {
            throw new IllegalArgumentException("Khoảng thời gian không hợp lệ");
        }

        LocalDate day = LocalDate.ofInstant(from, ZoneOffset.UTC);
        if (!day.equals(LocalDate.ofInstant(to.minusNanos(1), ZoneOffset.UTC))) {
            throw new IllegalArgumentException(
                "Khoảng phải nằm trong một ngày UTC");
        }

        Query q = Query.query(Criteria.where("device_id").is(deviceId))
            .and(Criteria.where("bucket_day").is(day))
            .and(Criteria.where("event_time").gte(from))
            .and(Criteria.where("event_time").lt(to))
            .limit(100);

        return template.select(q, DeviceEvent.class);
    }
}
~~~

Ví dụ `from=2026-11-25T08:00:00Z`, `to=2026-11-25T09:00:00Z` chỉ đọc một partition ngày 25/11. Nếu khoảng thời gian đi qua 00:00 UTC, hãy **tách thành từng ngày** rồi truy vấn tương ứng. Kiểm tra giới hạn thời gian, số ngày truy vấn, kích thước trang và quyền truy cập thiết bị ở lớp API.

Đoạn này dùng `limit(100)` để minh họa một lần đọc có giới hạn; khi cần duyệt toàn bộ khối dữ liệu, dùng `template.slice(query.pageRequest(CassandraPageRequest.first(100)), DeviceEvent.class)` và tiếp tục bằng `Slice.nextPageable()`. `LIMIT` trong CQL và kích thước fetch page của driver là hai khái niệm khác nhau; `LIMIT` giới hạn tổng số dòng của truy vấn.

## 8. Phân trang Cassandra không giống OFFSET của SQL

Cassandra sử dụng **paging state** để tiếp tục truy vấn theo hướng tiến. Dòng:

~~~java
Slice<DeviceEvent> page1 =
    repository.findByDeviceAndDay(deviceId, day,
                                  CassandraPageRequest.first(50));

if (page1.hasNext()) {
    Slice<DeviceEvent> page2 =
        repository.findByDeviceAndDay(deviceId, day, page1.nextPageable());
}
~~~

mang đúng ý nghĩa: đọc 50 dòng đầu và đọc tiếp từ trạng thái do Cassandra trả về. Không viết kiểu SQL `OFFSET 50000` hoặc giả định có thể nhảy thẳng đến trang 100. `Slice` hữu ích vì không cần tính tổng bản ghi để hiển thị “còn trang sau không?”.

Khi triển khai API phân trang:

- Trả kết quả cùng **continuation token** chỉ nếu còn trang sau. Token phải được mã hóa/đóng gói an toàn, có thời hạn và ràng buộc với `deviceId`, `bucketDay`, tập filter và kích thước trang. Không cho client sửa hoặc tái sử dụng tùy tiện paging state.
- Giữ **cùng truy vấn và tham số** giữa các lần gọi. State của partition ngày 25 không thể đem dùng cho partition ngày 24 hoặc một range khác.
- Nếu bản ghi đang được ghi/xóa trong lúc duyệt, paging không tạo snapshot ổn định toàn cục; cần xác định cách chấp nhận trùng/thiếu do thay đổi dữ liệu trong ứng dụng.

Muốn lịch sử 7 ngày: truy vấn lần lượt các bucket UTC từ mới đến cũ, trả trang có giới hạn và giữ trạng thái tiếp tục riêng cho từng bucket. Không dùng `ORDER BY` để mong sắp xếp đồng thời dữ liệu từ nhiều partition.

## 9. Tính nhất quán và đặc trưng hệ phân tán

Trong môi trường nhiều node, mức consistency áp dụng **trên từng thao tác đọc/ghi**:

| Mức | Ý nghĩa | Đánh đổi thực tế |
| --- | --- | --- |
| `LOCAL_ONE` | Một replica trong datacenter địa phương phản hồi | Latency thấp hơn, khả năng đọc dữ liệu chưa cập nhật cao hơn |
| `LOCAL_QUORUM` | Đa số replica trong datacenter địa phương phản hồi | Cân bằng thông dụng giữa sẵn sàng và độ mới dữ liệu |
| `ALL` | Tất cả replica liên quan phải phản hồi | Khắt khe về khả năng sẵn sàng; thường không phù hợp pipeline sự kiện liên tục |

Với RF=3 trong một datacenter, quorum là **2 replica**. Đặt cả ghi và đọc ở `LOCAL_QUORUM` giúp quorum giao nhau trong tình huống bình thường; điều này **không tự biến toàn hệ thống thành transaction tuyến tính hóa**, nhất là khi có ghi đồng thời, nhiều partition, lỗi mạng hoặc thao tác cần điều kiện. `@Consistency(DefaultConsistencyLevel.LOCAL_QUORUM)` trong repository ở mục 6 chỉ cấu hình **truy vấn đọc ấy**; mức ghi của `repository.save` cần cấu hình và kiểm tra riêng ở driver/operation. Nếu cần “chỉ ghi khi chưa tồn tại”, xem xét lightweight transaction (`IF NOT EXISTS`) và chấp nhận chi phí của cơ chế đó.

Thời gian sự kiện có thể đến sai thứ tự vì mạng, đồng hồ thiết bị bị lệch hoặc gửi bù sau mất kết nối. Đừng gộp `eventTime` với `receivedAt`. Một sự kiện tới hôm nay nhưng mang `eventTime` hôm qua phải được ghi vào bucket **hôm qua**, để lịch sử theo thời gian xảy ra vẫn nhất quán với định nghĩa dữ liệu.

## 10. Kiểm soát lưu trữ và hiệu năng

**1. Giữ partition vừa phải.** Theo dõi kích thước partition và số row/device/ngày. Nếu một thiết bị tạo ra nhiều sự kiện hơn dự kiến, bucket theo ngày có thể thành hotspot; cân nhắc bucket theo giờ hoặc chiến lược phân tán ghi kèm cơ chế ghép kết quả khi đọc. Không thêm một shard ngẫu nhiên nếu chưa thiết kế cách đọc các shard ấy.

**2. Giới hạn số ngày và số dòng mỗi API.** Một yêu cầu “toàn bộ lịch sử của mọi thiết bị” sẽ không có partition key thích hợp trong bảng này. Dùng job phân tích hoặc bảng đọc khác cho truy vấn tổng hợp; với API lịch sử, áp dụng giới hạn ngày, fetch size và concurrency.

**3. Xem xét retention và TTL.** Nếu chỉ giữ dữ liệu 30 ngày, có thể thiết kế chính sách TTL cho bản ghi mới, ví dụ:

~~~sql
ALTER TABLE telemetry.device_events
WITH default_time_to_live = 2592000;
~~~

TTL hết hạn tạo **tombstone** và làm tăng áp lực compaction nếu không được quản lý. Trước khi dùng trong sản xuất, thống nhất thời gian lưu giữ, khả năng đọc dữ liệu cũ, compaction strategy (thường cân nhắc `TimeWindowCompactionStrategy` với dữ liệu time series có vòng đời đồng nhất) và quy trình sửa/xóa dữ liệu. Không coi TTL là cơ chế xóa tức thì trên đĩa.

**4. Tránh anti-pattern khi ghi.** Ghi từng event theo khóa định tuyến đúng; hạn chế batch lớn trải nhiều partition, nhất là `LOGGED BATCH` dùng như giải pháp tăng tốc tổng quát. Cassandra được thiết kế cho nhiều ghi độc lập; batch không thay thế bulk ingestion pipeline.

**5. Quan sát chỉ số.** Theo dõi p95/p99 latency đọc/ghi, timeout, unavailable, kích thước và phân bố partition, tombstone khi đọc, compaction backlog, dropped mutations và lưu lượng theo thiết bị. Kiểm tra truy vấn thật bằng môi trường có dữ liệu và traffic đại diện; đừng đánh giá hiệu năng chỉ dựa trên vài dòng mẫu.

**6. Phòng lỗi vận hành.** Cấu hình timeout/retry có giới hạn, sử dụng bound parameters/prepared statements khi làm việc trực tiếp với `CqlSession`, ghi log `deviceId`/bucket và correlation ID ở mức phù hợp, đồng thời bảo vệ dữ liệu nhạy cảm trong `payload`.

## 11. Các lỗi thường gặp khi thực hành

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Query bị từ chối vì thiếu partition key | Không truyền đủ `device_id` và `bucket_day` | Thiết kế API buộc biết thiết bị và ngày |
| Muốn truy vấn theo `event_type` nhưng không hiệu quả | Bảng chỉ phục vụ timeline theo thiết bị/ngày | Đánh giá tạo bảng mới theo access pattern |
| Bản ghi cùng ID xuất hiện hai lần | Retry thay đổi `eventId` hoặc timestamp | Giữ ID ổn định, chuẩn hóa millisecond |
| Sự kiện mất khỏi ngày dự kiến | Bucket dựa trên timezone local hay `receivedAt` | Dùng `eventTime` UTC thống nhất ở cả ghi/đọc |
| API đọc nhiều ngày chậm | Đọc quá nhiều partition hoặc không giới hạn row | Chia ngày, giới hạn lịch sử và số trang |
| Dùng `PageRequest.of(100, 50)` để nhảy trang | Cassandra không hỗ trợ phân trang bằng offset như RDBMS | Dùng `CassandraPageRequest` và paging state |
| Ghi tốt nhưng đọc chậm theo thời gian | Partition quá lớn, tombstone nhiều, compaction quá tải | Đo size/row/tombstone, điều chỉnh bucket/TTL/compaction |
| Thấy đọc thiếu sự kiện mới ghi | Read/write consistency chưa phù hợp hoặc ghi chưa thành công | Kiểm tra RF, consistency của **cả hai** thao tác và lỗi ghi |

## 12. Bài tập vận dụng và tiêu chí tự kiểm

**Bài tập A — Lịch sử một ngày.** Ghi ba sự kiện có các mốc `08:00`, `10:05`, `09:30` vào cùng thiết bị và ngày. Truy vấn `LIMIT 2`; kiểm chứng nhận `10:05` rồi `09:30`. Ghi thêm sự kiện của thiết bị khác; kết quả của thiết bị đầu tiên phải không thay đổi.

**Bài tập B — Qua ranh giới ngày.** Ghi một sự kiện ở `23:59:59Z` và một sự kiện ở `00:00:01Z` ngày kế tiếp. Kiểm tra chúng nằm trong **hai partition khác nhau**, sau đó xây hàm đọc hai bucket và ghép theo thời gian giảm dần.

**Bài tập C — Retry và phân trang.** Gửi lại sự kiện với cùng bộ khóa chính và kiểm tra số row không tăng. Sinh hơn 100 sự kiện cùng ngày, đọc hai trang bằng `nextPageable()`; xác minh không dùng offset và không dùng state cho ngày khác.

**Bài tập D — Giới hạn thiết kế.** Giải thích vì sao `SELECT * FROM device_events WHERE event_type = 'TEMPERATURE'` không phải truy vấn chủ đích của bảng. Đề xuất primary key của một bảng mới nếu sản phẩm cần xem sự kiện nhiệt độ theo một nhóm thiết bị trong khung giờ, và nêu chi phí ghi dữ liệu sang nhiều bảng.

**Đạt yêu cầu khi:** bạn chứng minh được mỗi truy vấn timeline có đủ partition key, dữ liệu được sắp xếp đúng theo thời gian, retry có khóa ổn định, paging chuyển tiếp đúng cách, và có giới hạn kích thước/khối lượng đọc rõ ràng.

## Tài liệu tham khảo

- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): `@PrimaryKeyClass`, `@PrimaryKeyColumn` và entity.
- [Spring Data Cassandra — Cassandra Repositories](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/repositories.html): repository và `CassandraPageRequest`.
- [Spring Data Cassandra — Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html): `Slice`, `@Query`, consistency của repository.
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): `Query`, `Criteria`, `slice`.
- [Apache Cassandra — CQL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/cql_singlefile.html): partition key, clustering, `SELECT` và giới hạn truy vấn.
- [Spring Boot — Cassandra](https://docs.spring.io/spring-boot/reference/data/nosql.html): starter và `spring.cassandra.*`.
