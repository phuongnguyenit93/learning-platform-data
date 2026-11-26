# findById, existsById và truy cập bằng đủ thành phần khóa

> **Chương:** Repository  
> **Công nghệ:** Spring Data Cassandra, Apache Cassandra, Spring Boot, Java và CQL.  
> **Trọng tâm:** hiểu chính xác ý nghĩa của ID trong `CassandraRepository` khi bảng dùng khóa chính tổng hợp; dùng `findById` và `existsById` đúng cách; tránh nhầm giữa tìm một row theo toàn bộ primary key với đọc nhiều row trong một partition.

## 1. Vì sao phải hiểu ID theo mô hình Cassandra?

Trong Spring Data Cassandra, repository giúp gọi những thao tác quen thuộc như `save`, `findById`, `existsById` và `deleteById`. Tên phương thức gần giống repository của các hệ quản trị khác, nhưng việc truy cập dữ liệu vẫn phải tuân theo **partition key** và **clustering columns** mà Cassandra sử dụng để phân phối và sắp xếp row.

Giả sử hệ thống IoT ghi nhiều sự kiện của mỗi thiết bị. Product có hai yêu cầu khác nhau:

1. **Chi tiết sự kiện:** mở đúng một sự kiện khi biết mã thiết bị, ngày UTC, thời điểm sự kiện và ID sự kiện.
2. **Dòng thời gian:** xem 50 sự kiện mới nhất của thiết bị trong một ngày, rồi đọc tiếp các trang cũ hơn.

Hai yêu cầu này liên quan cùng bảng nhưng **không có cùng điều kiện truy vấn**. `findById` có ý nghĩa rõ ràng với yêu cầu thứ nhất: tìm một row theo **đủ thành phần primary key**. Yêu cầu thứ hai sử dụng **partition key** để lấy một nhóm row trong partition, nên cần query method riêng.

Với Cassandra, khóa chính có thể là một cột hoặc gồm nhiều cột. Khi khóa chính gồm nhiều cột, đừng mặc định ID của entity chỉ là một UUID. Cũng không nên dùng `existsById` để “khóa” dữ liệu trước khi ghi: kết quả kiểm tra có thể thay đổi ngay sau khi phương thức trả về.

### Kết quả học tập

Sau bài này, bạn có thể:

- Đọc đúng cú pháp `PRIMARY KEY ((device_id, event_day), event_time, event_id)`.
- Ánh xạ khóa tổng hợp thành một lớp `@PrimaryKeyClass`.
- Khai báo `CassandraRepository<DeviceEvent, DeviceEventKey>` đúng kiểu ID.
- Tạo `DeviceEventKey` đầy đủ trước khi gọi `findById` hoặc `existsById`.
- Phân biệt đọc theo khóa đầy đủ và truy vấn timeline theo partition key.
- Đánh giá tác động của consistency, retry, ghi upsert, timestamp precision và race condition.
- Dùng `@Query`, `CassandraTemplate` hoặc `CqlSession` khi access pattern không còn là tìm đúng một row.
- Viết kiểm thử và xử lý lỗi với mô hình dữ liệu phân tán.

## 2. Bảng CQL được thiết kế theo truy vấn

Ta lấy bảng `events_by_device_day` làm ví dụ xuyên suốt. DDL dưới đây dành cho Cassandra cục bộ một node:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': '1'
};

CREATE TABLE IF NOT EXISTS telemetry.events_by_device_day (
    device_id   uuid,
    event_day   date,
    event_time  timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    received_at timestamp,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

`SimpleStrategy` với replication factor 1 chỉ phù hợp ví dụ học tập. Cluster nhiều node/đa datacenter thường dùng `NetworkTopologyStrategy` với số replica phù hợp từng datacenter; phải đánh giá trên hạ tầng thật.

Đọc khóa:

| Thành phần | Vai trò trong Cassandra | Ý nghĩa |
| --- | --- | --- |
| `device_id` | Partition key, thành phần thứ nhất | Mã thiết bị |
| `event_day` | Partition key, thành phần thứ hai | Bucket ngày UTC |
| `event_time` | Clustering column thứ nhất, `DESC` | Sắp xếp mới nhất trước trong partition |
| `event_id` | Clustering column thứ hai, `ASC` | Phân biệt sự kiện có cùng timestamp |
| `event_type`, `payload`, `received_at` | Regular columns | Dữ liệu ứng dụng |

Cặp `(device_id, event_day)` nằm **trong ngoặc đôi** của phần `PRIMARY KEY` vì đây là **partition key tổng hợp**. Hai cột `event_time` và `event_id` hoàn thiện **primary key của từng row**.

Mô hình trực quan:

~~~text
Partition (device A, ngày 2026-11-25)
    10:05:00 / event 3333...  -> BATTERY_LOW
    09:30:00 / event 2222...  -> TEMPERATURE
    08:00:00 / event 1111...  -> TEMPERATURE

Partition (device A, ngày 2026-11-24)
    23:59:00 / event 4444...  -> TEMPERATURE

Partition (device B, ngày 2026-11-25)
    10:20:00 / event 5555...  -> DISCONNECTED
~~~

Trong ví dụ, muốn định vị **một row chính xác** của device A ngày 25, ta cần cả `event_time` và `event_id`. Muốn đọc **nhiều row** của device A ngày 25, chỉ cần xác định partition qua `device_id` và `event_day`, rồi áp dụng giới hạn theo thời gian hoặc `LIMIT`.

## 3. Khóa đầy đủ, partition key và clustering key khác nhau

Ba thuật ngữ cần được dùng nhất quán:

- **Partition key:** các cột quyết định nơi dữ liệu được phân phối. Trong bảng này là `device_id + event_day`.
- **Clustering key/columns:** các cột sắp xếp row **bên trong partition** và phân biệt các row của cùng partition. Trong bảng này là `event_time + event_id`.
- **Full primary key:** bao gồm **toàn bộ** partition key và clustering columns. Trong bảng này có bốn thành phần.

CQL tìm đúng một row:

~~~sql
SELECT *
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-25'
  AND event_time = '2026-11-25T09:30:00Z'
  AND event_id = 22222222-2222-4222-8222-222222222222;
~~~

CQL đọc timeline một partition:

~~~sql
SELECT *
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-25'
LIMIT 50;
~~~

CQL đọc một dải clustering time trong một partition:

~~~sql
SELECT *
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-25'
  AND event_time >= '2026-11-25T08:00:00Z'
  AND event_time <  '2026-11-25T10:00:00Z'
LIMIT 50;
~~~

**Điểm dễ sai:** nếu bạn chỉ có `event_id`, bảng này **không** được thiết kế để tìm hiệu quả trên toàn cluster bằng ID ấy. `event_id` là clustering column thứ hai, nằm sau cả partition key và `event_time`. Tìm bằng `event_id` đơn lẻ cần một mô hình đọc khác nếu nghiệp vụ thường xuyên yêu cầu.

## 4. Ánh xạ composite primary key bằng Spring Data Cassandra

Sử dụng `@PrimaryKeyClass` và `@PrimaryKeyColumn` để ánh xạ bốn thành phần khóa thành một kiểu ID Java.

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

    @PrimaryKeyColumn(name = "device_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID deviceId;

    @PrimaryKeyColumn(name = "event_day", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(name = "event_time", ordinal = 2,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.DESCENDING)
    private Instant eventTime;

    @PrimaryKeyColumn(name = "event_id", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.ASCENDING)
    private UUID eventId;

    public DeviceEventKey() { }

    public DeviceEventKey(UUID deviceId, LocalDate eventDay,
                          Instant eventTime, UUID eventId) {
        this.deviceId = deviceId;
        this.eventDay = eventDay;
        this.eventTime = eventTime;
        this.eventId = eventId;
    }

    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID value) { this.deviceId = value; }

    public LocalDate getEventDay() { return eventDay; }
    public void setEventDay(LocalDate value) { this.eventDay = value; }

    public Instant getEventTime() { return eventTime; }
    public void setEventTime(Instant value) { this.eventTime = value; }

    public UUID getEventId() { return eventId; }
    public void setEventId(UUID value) { this.eventId = value; }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof DeviceEventKey that)) {
            return false;
        }
        return Objects.equals(deviceId, that.deviceId)
            && Objects.equals(eventDay, that.eventDay)
            && Objects.equals(eventTime, that.eventTime)
            && Objects.equals(eventId, that.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(deviceId, eventDay, eventTime, eventId);
    }
}
~~~

**Giải thích annotation:**

- `@PrimaryKeyClass` đánh dấu một kiểu dùng để biểu diễn **khóa chính tổng hợp**.
- `PrimaryKeyType.PARTITIONED` chỉ các cột của partition key.
- `PrimaryKeyType.CLUSTERED` chỉ các cột clustering.
- `ordinal` xác định thứ tự thành phần khóa trong từng nhóm và mapping.
- `Ordering.DESCENDING/ASCENDING` khớp `CLUSTERING ORDER BY` trên bảng.
- `equals` và `hashCode` giúp so sánh object ID theo **giá trị**, tránh phụ thuộc identity của Java object.

`UUID`, `LocalDate` và `Instant` lần lượt được ánh xạ sang `uuid`, `date` và `timestamp` qua cơ chế converter/driver tương ứng. Phải xác minh schema thực tế khớp những kiểu này, nhất là khi dự án có custom converter.

Trong Cassandra, trường khóa chính không được để null. Đừng truyền `DeviceEventKey` chứa `eventTime = null` với hy vọng repository hiểu đó là “truy vấn mọi sự kiện của ngày”. Đây là sai hợp đồng của `findById`.

## 5. Ánh xạ entity với khóa tổng hợp

**`DeviceEvent.java`**

~~~java
import java.time.Instant;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_device_day")
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
    public void setKey(DeviceEventKey value) { this.key = value; }

    public String getEventType() { return eventType; }
    public void setEventType(String value) { this.eventType = value; }

    public String getPayload() { return payload; }
    public void setPayload(String value) { this.payload = value; }

    public Instant getReceivedAt() { return receivedAt; }
    public void setReceivedAt(Instant value) { this.receivedAt = value; }
}
~~~

Trong trường hợp này, `@PrimaryKey` đặt trên trường `key` có **kiểu `DeviceEventKey`**, thay vì để `eventId` là `@Id` độc lập.

Entity mô tả bảng `events_by_device_day`. Keyspace `telemetry` có thể đặt trong cấu hình Spring Boot:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: telemetry
    schema-action: none
~~~

Tên datacenter phải đúng với Cassandra cluster đang chạy; `datacenter1` chỉ là ví dụ. `schema-action: none` giữ schema trong quy trình migration riêng; tạo keyspace/bảng trước khi sử dụng repository.

## 6. Khai báo CassandraRepository đúng kiểu ID

**`DeviceEventRepository.java`**

~~~java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {
}
~~~

Tham số generic thứ nhất là **entity**; tham số thứ hai là **kiểu ID thực tế**. Vì `DeviceEvent` dùng composite key, ID của repository phải là `DeviceEventKey`.

Các thao tác kế thừa phổ biến:

| API | Tham số | Kết quả | Ý nghĩa |
| --- | --- | --- | --- |
| `save(event)` | `DeviceEvent` chứa khóa đầy đủ | Entity sau thao tác save | Ghi dữ liệu theo primary key |
| `findById(key)` | `DeviceEventKey` đầy đủ | `Optional<DeviceEvent>` | Tìm đúng một row theo khóa |
| `existsById(key)` | `DeviceEventKey` đầy đủ | `boolean` | Kiểm tra hiện có row nhìn thấy theo truy vấn |
| `deleteById(key)` | `DeviceEventKey` đầy đủ | `void` | Ghi xóa cho row theo khóa, chịu ngữ nghĩa tombstone |
| `findAll()` | Không có điều kiện khóa | Tập entity | Cần tránh với bảng lớn; không phù hợp API lịch sử |

`findById` và `existsById` không tự suy ra một khóa khác từ dữ liệu bên trong entity. Chúng hoạt động theo kiểu ID đã được xác định trong mapping. Việc truyền `eventId` đơn lẻ sẽ không đúng kiểu method, cũng không đủ khóa cho bảng này.

**Không nên sử dụng `findAll()` để triển khai “100 sự kiện gần nhất của thiết bị”.** Nó thiếu partition key, dễ dẫn tới truy vấn tốn kém hoặc không phù hợp. Việc phân trang trong Cassandra phải bắt đầu từ access pattern có partition key rõ ràng.

## 7. Gọi findById với đủ bốn thành phần khóa

Giả sử ứng dụng cần mở chi tiết sự kiện:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

UUID deviceId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111");
UUID eventId = UUID.fromString(
    "22222222-2222-4222-8222-222222222222");

LocalDate day = LocalDate.parse("2026-11-25");
Instant time = Instant.parse("2026-11-25T09:30:00Z");

DeviceEventKey key =
    new DeviceEventKey(deviceId, day, time, eventId);

Optional<DeviceEvent> found = repository.findById(key);
~~~

Để đọc thuộc tính:

~~~java
DeviceEvent event = repository.findById(key)
    .orElseThrow(() -> new IllegalArgumentException(
        "Không tìm thấy sự kiện với khóa đã cho"));

String type = event.getEventType();
String payload = event.getPayload();
~~~

Thao tác tương ứng về ý nghĩa với `SELECT ... WHERE device_id = ? AND event_day = ? AND event_time = ? AND event_id = ?`. Cassandra có đầy đủ partition key để định tuyến, rồi xác định row bằng clustering columns.

### Vì sao event_day có mặt trong ID dù có event_time?

`event_day` là **một phần khóa phân vùng đã lưu**, không phải thông tin có thể bỏ đi khi gọi repository. Dù ứng dụng có thể tính nó từ `event_time`, vẫn phải **điền giá trị** vào đối tượng khóa.

Việc dùng ngày UTC theo `event_time` cần được thống nhất ở cả hai đường ghi/đọc. Ví dụ:

~~~java
LocalDate dayUtc = LocalDate.ofInstant(
    Instant.parse("2026-11-25T23:30:00Z"),
    java.time.ZoneOffset.UTC);
~~~

Nếu một request tính bucket theo múi giờ địa phương còn ingestion ghi theo UTC, `findById` có thể trả `Optional.empty()` dù event vẫn tồn tại ở bucket khác.

### Vì sao event_id không đủ?

Trong mô hình đang xét, `event_id` đảm nhiệm phân biệt các row có timestamp trùng nhau. Nó **không** phải partition key. Nếu product muốn “tra sự kiện trên toàn hệ thống bằng eventId”, cần một bảng định vị như `event_location_by_id` với `event_id` là partition key, hoặc access pattern khác được kiểm chứng. Không thể bắt `findById` tự chạy một truy vấn toàn cluster để tìm row bằng duy nhất `event_id`.

## 8. Chuẩn hóa timestamp khi tạo khóa

Cassandra `timestamp` lưu thời gian với độ phân giải **millisecond**. `Instant` của Java hỗ trợ nanosecond. Nếu ingestion ghi một `Instant` có nanosecond rồi API dựng lại khóa từ giá trị chưa chuẩn hóa, ứng dụng có thể nhầm rằng hai thời điểm khác nhau dù dữ liệu lưu đã bị quy về millisecond.

Đề xuất chuẩn hóa ngay ở biên ingest:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.Objects;
import java.util.UUID;

public final class EventKeys {
    private EventKeys() { }

    public static DeviceEventKey fromOccurredAt(
            UUID deviceId, Instant occurredAt, UUID eventId) {

        Objects.requireNonNull(deviceId, "deviceId");
        Objects.requireNonNull(occurredAt, "occurredAt");
        Objects.requireNonNull(eventId, "eventId");

        Instant canonicalTime =
            occurredAt.truncatedTo(ChronoUnit.MILLIS);
        LocalDate utcDay =
            LocalDate.ofInstant(canonicalTime, ZoneOffset.UTC);

        return new DeviceEventKey(
            deviceId, utcDay, canonicalTime, eventId);
    }
}
~~~

Cả writer và reader sử dụng chung quy tắc chuẩn hóa. Nếu API chấp nhận timestamp từ client, cần xác định chính sách rõ ràng: **yêu cầu đã chuẩn hóa**, hoặc chuẩn hóa ở một nơi và trả canonical timestamp cho client khi tạo event.

Tránh tình huống:

~~~text
Ingest:
  occurredAt = 2026-11-25T09:30:00.123456789Z
  CQL lưu theo precision millisecond

Read:
  eventTime = 2026-11-25T09:30:00.123456789Z
  không theo canonical timestamp của row
~~~

Ngoài ra, hai event khác nhau có cùng millisecond vẫn được phân biệt bằng `event_id`. ID này cần **ổn định qua retry**; không tạo UUID mới mỗi lần client thử lại cùng một sự kiện.

## 9. existsById trả lời câu hỏi nào?

`existsById(key)` chỉ trả lời: với **khóa đầy đủ đang hỏi**, truy vấn kiểm tra ở thời điểm và consistency được sử dụng có thấy row hay không?

~~~java
DeviceEventKey key = EventKeys.fromOccurredAt(
    deviceId,
    Instant.parse("2026-11-25T09:30:00Z"),
    eventId);

boolean found = repository.existsById(key);

if (found) {
    // Ví dụ: UI có thể cho phép mở liên kết tới chi tiết sự kiện.
}
~~~

Điều nó **không** đảm bảo:

- Không kiểm tra “đã có eventId này ở bất kỳ partition nào chưa?” nếu chỉ có `eventId`.
- Không khóa row để lần ghi tiếp theo độc quyền.
- Không đảm bảo kết quả vẫn đúng sau khi phương thức trả về.
- Không đảm bảo đọc thấy bản ghi mới nhất nếu consistency/read topology không đáp ứng yêu cầu.
- Không kiểm tra dữ liệu đã được đồng bộ sang những bảng projection khác.
- Không biến “event tồn tại” thành “người dùng được phép đọc event”.

**Không cần gọi `existsById` rồi `findById` cho cùng một request chỉ để tránh xử lý Optional.** Cách đó thực hiện thêm lượt truy cập database và có race giữa hai lần đọc. Nếu cần entity, gọi thẳng `findById` và xử lý `Optional`.

## 10. Đừng dùng existsById làm cơ chế chống trùng

Đây là anti-pattern phổ biến:

~~~java
if (!repository.existsById(key)) {
    repository.save(new DeviceEvent(
        key, "TEMPERATURE", "{\"celsius\":25.5}", Instant.now()));
}
~~~

Giả sử hai worker cùng xử lý một sự kiện:

~~~text
Worker A: existsById(key) -> false
Worker B: existsById(key) -> false
Worker A: save(key)
Worker B: save(key)
~~~

Kết quả: cả hai worker có thể ghi, dù đều “kiểm tra trước”. Đây là **race condition kiểm tra rồi mới hành động**. `existsById` không cung cấp isolation hay compare-and-swap.

Ở Cassandra, ghi thông thường theo cùng primary key là **upsert**: nếu row đã tồn tại, những cột được ghi có thể được cập nhật theo ngữ nghĩa Cassandra. Với luồng event, cách đơn giản hơn thường là **thiết kế khóa ổn định và retry idempotent**, không thực hiện một lượt `existsById` trên mọi event.

Nếu nghiệp vụ yêu cầu điều kiện chặt chẽ “**chỉ tạo nếu chưa tồn tại**”, đánh giá **lightweight transaction (LWT)** bằng CQL:

~~~sql
INSERT INTO telemetry.events_by_device_day (
    device_id, event_day, event_time, event_id,
    event_type, payload, received_at
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-25',
    '2026-11-25T09:30:00Z',
    22222222-2222-4222-8222-222222222222,
    'TEMPERATURE',
    '{"celsius": 25.5}',
    '2026-11-25T09:30:01Z'
) IF NOT EXISTS;
~~~

LWT dùng cơ chế đồng thuận cho điều kiện, có latency/tải lớn hơn ghi thường. Cần xác nhận phạm vi điều kiện và kiểm tra kết quả áp dụng của statement. Không dùng LWT mặc định cho toàn bộ IoT ingestion chỉ vì quen với mô hình “INSERT nếu chưa có”; chỉ dùng khi hợp đồng nghiệp vụ thực sự cần.

Khi dùng Java driver:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.ResultSet;

ResultSet result = session.execute(
    "INSERT INTO telemetry.events_by_device_day "
  + "(device_id, event_day, event_time, event_id, "
  + " event_type, payload, received_at) "
  + "VALUES ("
  + "11111111-1111-4111-8111-111111111111, "
  + "'2026-11-25', '2026-11-25T09:30:00Z', "
  + "22222222-2222-4222-8222-222222222222, "
  + "'TEMPERATURE', '{\"celsius\":25.5}', "
  + "'2026-11-25T09:30:01Z') IF NOT EXISTS");

boolean applied =
    result.one().getBoolean("[applied]");
~~~

Đoạn trên minh họa cách đọc `[applied]` cho một statement cố định. Trong code thực tế, dùng prepared/bound statement cho các giá trị động, xử lý kết quả không thành công và quy tắc retry của LWT. `[applied] = false` cho biết điều kiện không được áp dụng; không có nghĩa request bị lỗi kỹ thuật.

## 11. Tìm theo partition key: dùng phương thức riêng

Truy vấn “50 event mới nhất trong một ngày” **không** nên dùng `findById` vì bạn chưa biết `event_time` và `event_id` của 50 row. Hãy khai báo query phù hợp.

**`DeviceEventRepository.java` mở rộng:**

~~~java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {

    @Query("SELECT * FROM events_by_device_day "
         + "WHERE device_id = ?0 AND event_day = ?1")
    Slice<DeviceEvent> findDayEvents(
        UUID deviceId, LocalDate day, Pageable pageable);
}
~~~

Dùng `@Query` giúp nêu rõ CQL; tham số `Pageable` là tham số đặc biệt của Spring Data, không phải cột CQL. Truy vấn này cung cấp **đủ partition key**; thứ tự mới nhất trước đến từ `CLUSTERING ORDER BY` trên bảng.

Lấy trang đầu:

~~~java
import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.domain.Slice;

Slice<DeviceEvent> first =
    repository.findDayEvents(deviceId, day,
                             CassandraPageRequest.first(50));

for (DeviceEvent event : first.getContent()) {
    // Hiển thị event, hoặc chuyển thành DTO cho API.
}

if (first.hasNext()) {
    Slice<DeviceEvent> next =
        repository.findDayEvents(
            deviceId, day, first.nextPageable());
}
~~~

Cassandra sử dụng **paging state**, không phải offset SQL. `Slice` tiện cho giao diện vì không bắt buộc thực hiện truy vấn đếm tất cả row để biết còn trang tiếp hay không.

**Không** xây URL kiểu `?page=1000` rồi cố dịch sang nhảy thẳng offset 50.000 trên Cassandra. Nếu client cần phân trang qua nhiều request HTTP, ứng dụng phải quản lý continuation token gắn với đúng `deviceId`, `day`, điều kiện truy vấn và page size.

## 12. CQL có thể truy cập chính xác theo clustering prefix nào?

Cassandra cho phép nhiều loại truy vấn dựa trên khóa, nhưng không phải bỏ thành phần nào của primary key cũng hợp lệ.

| Điều kiện `WHERE` | Với bảng ví dụ | Ý nghĩa |
| --- | --- | --- |
| `device_id=? AND event_day=? AND event_time=? AND event_id=?` | Phù hợp | Một row chính xác |
| `device_id=? AND event_day=?` | Phù hợp | Tập row trong một partition |
| `device_id=? AND event_day=? AND event_time>=?` | Phù hợp | Dải clustering time của một partition |
| Chỉ `device_id=?` | Không cung cấp đủ composite partition key | Không phải truy vấn timeline được thiết kế |
| Chỉ `event_id=?` | Thiếu partition key và clustering prefix | Không định vị hiệu quả row |
| `device_id=? AND event_day=? AND event_id=?` | Bỏ qua clustering column đứng trước `event_time` | Không phải truy vấn chuẩn theo clustering key |
| Chỉ `event_type=?` | Regular column, không phải key tra cứu | Cần mô hình truy vấn khác |

`ALLOW FILTERING` không phải giải pháp mặc định để bỏ qua điều kiện của khóa. Một câu lệnh có thể chạy trong demo với dữ liệu ít nhưng tốn tài nguyên trên hàng triệu row.

Nếu cần tìm theo `eventId` độc lập, có thể tạo bảng ánh xạ từ event ID đến vị trí:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.event_location_by_id (
    event_id   uuid PRIMARY KEY,
    device_id  uuid,
    event_day  date,
    event_time timestamp
);
~~~

Luồng đọc:

~~~text
event_id
  -> tìm row trong event_location_by_id
  -> dựng DeviceEventKey đầy đủ
  -> repository.findById(key) trên events_by_device_day
~~~

Bảng thứ hai phải được ghi và đồng bộ có kiểm soát; hai lệnh ghi ở các partition khác nhau **không tự thành một transaction ACID đa bảng**. Cần chiến lược retry/replay, backfill, xóa và đối soát dữ liệu.

## 13. Truy vấn theo full primary key bằng CassandraTemplate

Nếu cần tạo câu truy vấn có điều kiện trong service thay vì gọi repository, `CassandraTemplate` vẫn phải tuân theo schema Cassandra.

~~~java
import java.util.Objects;
import java.util.Optional;

import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class EventLookup {
    private final CassandraTemplate template;

    public EventLookup(CassandraTemplate template) {
        this.template = template;
    }

    public Optional<DeviceEvent> findExact(DeviceEventKey key) {
        Objects.requireNonNull(key);

        Query query = Query.query(
            Criteria.where("device_id").is(key.getDeviceId()))
            .and(Criteria.where("event_day").is(key.getEventDay()))
            .and(Criteria.where("event_time").is(key.getEventTime()))
            .and(Criteria.where("event_id").is(key.getEventId()));

        return Optional.ofNullable(
            template.selectOne(query, DeviceEvent.class));
    }
}
~~~

Đây là minh họa cùng một access pattern với `findById(key)`. Nếu chỉ cần tìm entity theo ID, **repository đơn giản hơn**. `CassandraTemplate` hữu ích khi cần xây truy vấn động nhưng vẫn có đủ các cột khóa hợp lệ, hoặc cần khả năng mapping/cấu hình operation cụ thể.

Nếu dùng `CqlSession` trực tiếp, chuẩn bị CQL với placeholder và bind values để tránh ghép chuỗi input:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

PreparedStatement stmt = session.prepare(
    "SELECT event_type, payload "
  + "FROM telemetry.events_by_device_day "
  + "WHERE device_id=? AND event_day=? "
  + "AND event_time=? AND event_id=?");

Row row = session.execute(
    stmt.bind(
        key.getDeviceId(),
        key.getEventDay(),
        key.getEventTime(),
        key.getEventId()
    )).one();
~~~

Đường driver bỏ qua một số tiện ích entity mapping của Spring Data, nên chỉ dùng khi cần kiểm soát CQL/timeout/consistency sâu hơn. Đừng để cùng nghiệp vụ có hai đường đọc với consistency khác nhau mà không có lý do.

## 14. Bao bọc việc dựng khóa và kiểm tra dữ liệu trong service

API không nên cho các controller tự dựng `DeviceEventKey` theo cách khác nhau. Một service thống nhất giúp:

- Xác minh bốn thành phần khóa đều có.
- Chuẩn hóa `eventTime` đến millisecond và tính bucket UTC.
- Kiểm tra người dùng có quyền xem `deviceId`.
- Xử lý `Optional.empty()` theo quy ước HTTP/domain.
- Ghi nhận mã truy vết mà không log dữ liệu nhạy cảm trong `payload`.

Ví dụ:

~~~java
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import org.springframework.stereotype.Service;

@Service
public class EventDetailService {
    private final DeviceEventRepository repository;

    public EventDetailService(DeviceEventRepository repository) {
        this.repository = repository;
    }

    public Optional<DeviceEvent> find(
            UUID deviceId, Instant occurredAt, UUID eventId) {

        DeviceEventKey key =
            EventKeys.fromOccurredAt(deviceId, occurredAt, eventId);

        return repository.findById(key);
    }

    public boolean exists(
            UUID deviceId, Instant occurredAt, UUID eventId) {

        DeviceEventKey key =
            EventKeys.fromOccurredAt(deviceId, occurredAt, eventId);

        return repository.existsById(key);
    }
}
~~~

Lớp `EventKeys` được định nghĩa ở mục 8. Trong hệ thống đa tenant, phải gắn quyền truy cập với tenant/device và mô hình dữ liệu được thiết kế cho tính cách ly dữ liệu. `existsById` không phải cách “thăm dò” sự tồn tại của thiết bị không thuộc quyền của người gọi.

Nếu caller truyền `eventDay` riêng, phải kiểm tra nó khớp với ngày UTC của `eventTime`. Nếu không, yêu cầu đọc có thể nhắm sai partition và trả “không tìm thấy” dù row tồn tại.

## 15. Consistency: false không luôn là dữ liệu chưa từng tồn tại

Cassandra hỗ trợ nhiều mức consistency cho thao tác đọc/ghi. Với replication factor 3 trong một datacenter:

| Mức đọc | Cách phản hồi | Hệ quả cho `findById` / `existsById` |
| --- | --- | --- |
| `LOCAL_ONE` | Cần một replica tại local datacenter | Có thể chấp nhận độ mới thấp hơn trong một số tình huống |
| `LOCAL_QUORUM` | Cần đa số replica local, ví dụ 2/3 | Thường cải thiện bảo đảm đọc dữ liệu vừa ghi ở quorum |
| `ALL` | Cần tất cả replica liên quan | Dễ ảnh hưởng availability khi replica lỗi/chậm |

Một request trả `existsById(key) = false` có thể có nhiều nguyên nhân: khóa sai, row chưa từng được ghi, đã bị xóa/hết TTL, write chưa hoàn tất, hoặc mức consistency/replica đọc chưa đáp ứng yêu cầu độ mới. Không nên quy tất cả về “event chắc chắn không tồn tại”.

Với Spring Data Cassandra, có thể đặt consistency trên một query method thích hợp bằng annotation, ví dụ:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.data.cassandra.repository.Consistency;
import org.springframework.data.cassandra.repository.Query;

@Consistency(DefaultConsistencyLevel.LOCAL_QUORUM)
@Query("SELECT * FROM events_by_device_day "
     + "WHERE device_id = ?0 AND event_day = ?1")
Slice<DeviceEvent> findDayEventsAtQuorum(
    UUID deviceId, LocalDate day, Pageable pageable);
~~~

Đây là ví dụ **phương thức repository được annotation cụ thể**. Không suy ra annotation ấy tự áp lên toàn bộ `findById`, `existsById` hay `save` kế thừa. Muốn điều chỉnh consistency của chúng, cần kiểm tra cách cấu hình driver/template/repository trong phiên bản ứng dụng, hoặc định nghĩa đường truy vấn riêng có chính sách rõ ràng.

**LOCAL_QUORUM không tạo transaction ACID toàn hệ thống.** Ghi đồng thời, timestamp của mutation, nhiều partition và pipeline projection cần mô hình nhất quán phù hợp. Mức consistency cũng không thay thế yêu cầu idempotent khi retry ghi.

## 16. existsById và chi phí của một lần đọc bổ sung

Đối với API trả chi tiết event, hãy cân nhắc:

~~~text
Cách A:
  existsById(key) -> true
  findById(key)   -> Optional<Event>

Cách B:
  findById(key)   -> Optional<Event>
~~~

Cách A tốn thêm một lượt truy cập Cassandra và có thể tạo race: row bị xóa/hết TTL sau khi `existsById` trả true. Cách B đơn giản hơn và đáp ứng trực tiếp mục tiêu trả entity hoặc thông báo không tìm thấy.

`existsById` vẫn có giá trị khi nghiệp vụ **chỉ cần boolean**, ví dụ xác minh liên kết nội bộ hoặc hiển thị trạng thái có/không với cùng khóa. Tuy nhiên cần:

- Chỉ gọi khi biết **đủ khóa**; không triển khai nó bằng cách duyệt toàn bảng.
- Đo p95/p99 và tần suất gọi ở tải thực.
- Kiểm tra CQL được sinh ra nếu phụ thuộc vào chi phí tối ưu cụ thể; **không giả định** mọi phiên bản repository sẽ chỉ đọc đúng một cột hay dùng một phép đếm rẻ.
- Dùng cache có kiểm soát nếu số lần kiểm tra lặp lại lớn và nghiệp vụ chấp nhận stale data.
- Không dùng nó làm công cụ bảo đảm uniqueness hoặc concurrency.

Ví dụ một luồng ghi 10.000 events/giây: nếu mỗi event đều gọi `existsById` trước khi `save`, hệ thống tự tạo **ít nhất một lượt đọc thêm cho mỗi event**, tăng tải và có thể khiến pipeline ingest chậm hơn đáng kể mà vẫn không giải quyết race.

## 17. Khi save cùng khóa: upsert và idempotency

Cassandra ghi bình thường có tính chất upsert theo **full primary key**. Với trường hợp bảng event:

~~~java
DeviceEventKey key = EventKeys.fromOccurredAt(
    deviceId, occurredAt, eventId);

DeviceEvent event = new DeviceEvent(
    key, "TEMPERATURE", "{\"celsius\":25.5}", Instant.now());

repository.save(event);
~~~

Nếu retry cùng `deviceId`, `eventDay`, `eventTime` và `eventId`, Cassandra định vị cùng row. Nhưng cần phân biệt hai ý:

- **Không tạo row mới:** khóa chính giữ nguyên nên vẫn nhắm đến cùng row.
- **Giữ nguyên mọi giá trị:** không tự bảo đảm nếu retry thay `payload`, `receivedAt`, TTL hoặc write timestamp; các cột có thể được cập nhật theo quy tắc của Cassandra.

Muốn ghi lặp lại có kết quả logic ổn định, hãy dùng event ID được nguồn phát cấp một lần, timestamp canonical và nội dung bất biến hoặc một chính sách giải quyết phiên bản rõ ràng. Ghi vào bảng phụ/đẩy thông báo ra hệ ngoài cũng phải có chiến lược idempotency riêng.

**Delete** cũng đáng chú ý: `deleteById(key)` áp dụng xóa theo khóa, Cassandra lưu thông tin xóa để hòa giải replica. Với workload xóa thường xuyên, cần theo dõi tombstone và compaction; không biến event table thành nơi xóa/viết lại liên tục mà không đo.

## 18. Các lỗi phổ biến khi dùng khóa tổng hợp

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `findById(eventId)` không biên dịch | Repository khai báo ID là `DeviceEventKey` | Tạo key đầy đủ, dùng đúng kiểu generic |
| `findById(key)` trả empty dù row có | Sai `eventDay` UTC hoặc timestamp precision | Dùng hàm canonical key ở cả ghi và đọc |
| Query báo thiếu partition key | Chỉ truyền `deviceId` mà thiếu `eventDay` | Truy vấn đủ hai thành phần partition key |
| Muốn tìm bằng `eventId` đơn lẻ | `eventId` không phải partition key | Thiết kế bảng định vị theo ID nếu cần |
| `existsById=false` rồi save vẫn trùng dữ liệu nghiệp vụ | Race giữa nhiều worker hoặc event ID không ổn định | Idempotent key hoặc LWT khi cần điều kiện cứng |
| Gọi `existsById` trước `findById` làm latency tăng | Hai query cho cùng một mục tiêu | Dùng một `findById` |
| `findAll()` làm hệ thống chậm | Không giới hạn truy vấn theo partition | Tạo query theo access pattern và paging state |
| Event đọc không theo thứ tự mong muốn | Query ghép nhiều partition hoặc clustering order sai | Đọc từng bucket đúng schema, ghép tại ứng dụng |
| Kết quả mới ghi chưa hiển thị | Consistency chưa phù hợp hoặc luồng projection trễ | Kiểm tra read/write consistency và pipeline |
| API trang 2 bị thiếu/trùng | Dùng offset hoặc cursor với filter khác | Dùng `CassandraPageRequest`/paging state với cùng truy vấn |
| Lỗi mapping cột/khóa | Annotation khác schema trên cluster | Đối chiếu `@PrimaryKeyColumn` với `system_schema`/DDL |

## 19. Kiểm thử có giá trị cho findById và existsById

Không cần nhiều unit test chỉ để chứng minh một getter trả đúng giá trị; nên tập trung vào kiểm thử tích hợp với Cassandra thật/Testcontainers hoặc cluster test cô lập, vì mapping và CQL thực tế mới là phần dễ sai.

Một nhóm thử nghiệm đề xuất:

1. **Đúng khóa đầy đủ:** ghi sự kiện E, gọi `findById(DeviceEventKey)` được entity đúng; `existsById(key)` trả true.
2. **Sai một thành phần:** đổi `eventId`, `eventDay` hoặc `eventTime`; không tìm được đúng row.
3. **Cùng timestamp:** hai sự kiện cùng millisecond, khác `eventId`, tồn tại thành hai row và tìm riêng từng row.
4. **Sai bucket:** ghi lúc `23:59:59Z` rồi đọc bằng ngày local khác UTC; chứng minh vì sao cần chuẩn UTC.
5. **Precision:** giá trị `Instant` chứa micro/nanosecond được chuẩn hóa theo policy và đọc lại đúng key.
6. **Timeline:** truy vấn bằng đầy đủ partition key trả mới nhất trước; phân trang bằng `nextPageable()`.
7. **Retry:** ghi cùng event key hai lần không tạo row thứ hai, nhưng cập nhật cột khác phải được kiểm tra theo policy.
8. **Consistency:** nếu cluster test hỗ trợ mô phỏng replica chậm, kiểm tra sự khác biệt giữa mức đọc/ghi đã chọn thay vì giả định `LOCAL_ONE`/`LOCAL_QUORUM` giống nhau.

Ví dụ phác thảo integration test (giả định repository, schema và môi trường Cassandra kiểm thử đã được cấu hình):

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DeviceEventRepositoryIT {

    @Autowired
    DeviceEventRepository repository;

    @Test
    void findByFullKeyAndCheckExistence() {
        UUID deviceId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();
        Instant eventTime = Instant.parse("2026-11-25T09:30:00.123Z");

        DeviceEventKey key =
            EventKeys.fromOccurredAt(deviceId, eventTime, eventId);

        DeviceEvent stored = new DeviceEvent(
            key, "TEMPERATURE", "{\"celsius\":25.5}", Instant.now());
        repository.save(stored);

        assertThat(repository.findById(key)).isPresent();
        assertThat(repository.existsById(key)).isTrue();

        DeviceEventKey unknown = EventKeys.fromOccurredAt(
            deviceId, eventTime, UUID.randomUUID());
        assertThat(repository.findById(unknown)).isEmpty();
        assertThat(repository.existsById(unknown)).isFalse();
    }
}
~~~

Mã chỉ là ví dụ kiểm thử. Không chạy với production keyspace hoặc user có dữ liệu thật; dùng keyspace/test cluster cô lập và cleanup phù hợp. Kiểm thử `@SpringBootTest` kết nối server thật phải có Cassandra hoạt động và schema đã tạo; mock repository không chứng minh CQL hoạt động.

## 20. Bài tập thực hành

### Bài A — Dựng khóa

Cho:

~~~text
deviceId  = 11111111-1111-4111-8111-111111111111
eventTime = 2026-11-25T23:59:59.555Z
eventId   = 22222222-2222-4222-8222-222222222222
~~~

Hãy viết Java tạo `DeviceEventKey`, gọi `findById` và giải thích vì sao bucket ngày phải là `2026-11-25` theo UTC. Khi timestamp đến từ ngày kế tiếp 00:00:00Z thì partition key nào thay đổi?

### Bài B — Phân biệt hai kiểu đọc

Product yêu cầu (a) mở đúng một event, (b) xem 50 event mới nhất của thiết bị trong ngày, (c) tìm event chỉ bằng `eventId`. Hãy chọn `findById`, query theo partition hoặc bảng mới cho từng yêu cầu và giải thích theo khóa đã thiết kế.

### Bài C — Race condition

Hai worker cùng nhận event và cùng gọi `existsById(key)`, đều thấy false. Vì sao không được coi đây là cơ chế “insert nếu chưa có”? Khi nào ghi idempotent theo khóa đủ dùng, khi nào cần LWT `IF NOT EXISTS`?

### Bài D — Consistency

Keyspace RF=3 trong một datacenter, ghi ở `LOCAL_QUORUM`, đọc ở `LOCAL_ONE`. Hãy phân tích trường hợp `existsById` chưa thấy dữ liệu mới dù ghi đã được xác nhận, và hệ quả khi API quyết định có tiếp tục xử lý hay không.

### Bài E — Timestamp precision

Nguồn phát `2026-11-25T09:30:00.123456789Z` nhưng Cassandra lưu millisecond. Hãy thiết kế hàm canonicalize thời gian và chứng minh cả save và findById dùng cùng chuẩn.

### Bài F — Paging

Viết code lấy `Slice<DeviceEvent>` đầu tiên 50 row bằng `CassandraPageRequest.first(50)`, sau đó dùng `first.nextPageable()`. Vì sao `findById` không phải API dùng để lấy trang timeline? Vì sao offset kiểu SQL không phù hợp Cassandra?

### Bài G — Thiết kế bảng theo ID

Nếu hệ thống cần tra event theo `eventId` từ link chia sẻ, hãy thiết kế một bảng lookup để tìm full key rồi truy vấn bảng timeline. Nêu rủi ro ghi hai bảng, retry, backfill, xóa dữ liệu và consistency của projection.

**Tiêu chí hoàn thành:** người học giải thích đúng full primary key, dựng được ID Java không thiếu thành phần, dùng `findById`/`existsById` đúng mục tiêu, phân biệt full-key lookup với partition scan, nhận diện race/idempotency và biết chọn API theo access pattern.

## 21. Checklist khi review repository

- [ ] Kiểu ID generic của repository khớp khóa chính entity?
- [ ] `@PrimaryKeyClass` chứa đủ partition và clustering columns, đúng thứ tự/kiểu?
- [ ] `equals/hashCode` của khóa dựa trên toàn bộ thành phần?
- [ ] Dữ liệu khóa không null, ngày UTC và timestamp millisecond nhất quán?
- [ ] `findById` được gọi bằng **full primary key**?
- [ ] `existsById` chỉ dùng khi thật sự cần boolean, không làm khóa chống trùng?
- [ ] Query timeline có **đủ partition key**, giới hạn số row và paging state?
- [ ] Yêu cầu tra event chỉ bằng một phần khóa đã có bảng đọc phù hợp?
- [ ] Read/write consistency khớp hợp đồng độ mới dữ liệu?
- [ ] Ghi retry có event ID ổn định và chính sách idempotency?
- [ ] Không dùng `findAll`, `ALLOW FILTERING` hoặc offset để che mô hình sai?
- [ ] Có integration test với schema Cassandra thật và dữ liệu nhiều row?

## Tài liệu tham khảo

- [Spring Data Cassandra — Cassandra Repositories](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/repositories.html): repository và CRUD.
- [Spring Data Cassandra — Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html): `@Query`, `Slice` và paging.
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): composite key và mapping annotation.
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): truy vấn bằng template.
- [Apache Cassandra — CQL Reference](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/cql_singlefile.html): `PRIMARY KEY`, `SELECT`, điều kiện và `IF NOT EXISTS`.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/): thiết kế theo partition key và access pattern.
