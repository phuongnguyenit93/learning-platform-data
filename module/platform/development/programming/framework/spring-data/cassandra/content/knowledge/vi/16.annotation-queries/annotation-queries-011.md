# Kiểm thử truy vấn với khóa ghép, dữ liệu thiếu và tập kết quả rỗng

> **Chương:** Truy vấn @Query  
> **Công nghệ:** Spring Data Cassandra, CassandraRepository, CassandraTemplate, Apache Cassandra, CQL và Java driver.  
> **Trọng tâm:** viết và kiểm thử các phương thức `@Query` khi bảng có **composite partition key** và **clustering columns**; phân biệt khóa chưa đủ, bản ghi không tồn tại, cột không có giá trị và trang kết quả rỗng; bảo đảm truy vấn không vô tình vượt ranh giới tenant hoặc quét dữ liệu rộng.

## 1. Vì sao một truy vấn trả rỗng chưa chắc là đúng?

Hệ thống IoT lưu sự kiện của nhiều thiết bị. API cần hỗ trợ ba thao tác:

1. Mở **đúng một sự kiện** bằng tenant, thiết bị, ngày UTC, thời điểm và event ID.
2. Đọc **50 sự kiện mới nhất** của một thiết bị trong một ngày, có thể đọc tiếp các trang.
3. Lọc một **khoảng thời gian** trong cùng thiết bị/ngày để phục vụ màn hình lịch sử.

Một phương thức repository trả `Optional.empty()` hoặc `List.of()` có thể là hành vi hoàn toàn hợp lệ nếu dữ liệu không có. Nhưng cũng có thể developer đã dựng **sai ngày UTC**, bind nhầm thứ tự tham số, bỏ sót một thành phần partition key hoặc đọc nhầm tenant.

Bởi vậy, test không nên chỉ kiểm tra “không ném exception”. Test phải chứng minh:

- Query định vị đúng partition và row.
- Query trả dữ liệu **đúng tenant, thiết bị, bucket và khoảng thời gian**.
- Một row không tồn tại được biểu diễn khác với lỗi CQL hoặc lỗi kết nối.
- Một cột regular có giá trị null không biến cả entity thành “không tồn tại”.
- Phân trang trên tập rỗng và tập nhiều trang có ngữ nghĩa rõ ràng.
- Cùng query chạy với timestamp chính xác đến millisecond và với dữ liệu ở ranh giới ngày UTC.

**Nguyên tắc:** kết quả rỗng là một dữ kiện nghiệp vụ chỉ khi truy vấn hợp lệ, đúng khóa và đã thực thi thành công. Không được “cứ catch exception rồi trả empty list”.

## 2. Bảng Cassandra dùng làm ví dụ

Cassandra phân phối dữ liệu theo partition key, rồi sắp xếp row trong partition bằng clustering columns. Ta dùng một bảng được thiết kế cho lịch sử thiết bị/ngày.

~~~sql
-- Ví dụ demo trên Cassandra một node.
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS telemetry.events_by_device_day (
    tenant_id   uuid,
    device_id   uuid,
    event_day   date,
    event_time  timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    received_at timestamp,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        event_time, event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC, event_id ASC
);
~~~

`SimpleStrategy` và RF=1 chỉ phù hợp môi trường học tập. Môi trường nhiều node/đa datacenter thường cần `NetworkTopologyStrategy` và replication factor được chốt theo topology, độ sẵn sàng và consistency.

Phân tích khóa:

| Thành phần | Vai trò | Ảnh hưởng tới test |
| --- | --- | --- |
| `tenant_id` | Partition key, vị trí đầu | Không được bỏ tenant hoặc đọc lẫn tenant khác |
| `device_id` | Partition key, vị trí thứ hai | Không được lấy sự kiện từ thiết bị khác |
| `event_day` | Partition key, vị trí thứ ba | Bucket UTC phải khớp lúc ghi và lúc đọc |
| `event_time` | Clustering thứ nhất, DESC | Kiểm tra lọc theo khoảng và thứ tự mới nhất trước |
| `event_id` | Clustering thứ hai, ASC | Hai event cùng millisecond vẫn là hai row khác nhau |
| `event_type`, `payload`, `received_at` | Regular columns | Có thể vắng giá trị; không phải thành phần khóa |

**Full primary key** ở đây có năm thành phần: `tenant_id`, `device_id`, `event_day`, `event_time` và `event_id`. **Composite partition key** chỉ gồm ba thành phần đầu.

Hai loại truy vấn cần kiểm thử riêng:

~~~sql
-- Truy cập một row chính xác bằng toàn bộ primary key:
SELECT *
FROM telemetry.events_by_device_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25'
  AND event_time = '2026-11-25T09:30:00Z'
  AND event_id = 33333333-3333-4333-8333-333333333333;
~~~

~~~sql
-- Truy cập nhiều row trong một partition:
SELECT *
FROM telemetry.events_by_device_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25'
LIMIT 50;
~~~

Một test tốt cần phân biệt **tìm một row bằng full key** với **tìm nhiều row bằng partition key**. Không phải vì cả hai có `WHERE` là dùng cùng một method được.

## 3. Mô hình Java cho composite primary key

Sử dụng `@PrimaryKeyClass` và `@PrimaryKeyColumn` để chỉ rõ các thành phần của khóa. Tránh dựa vào quy tắc đặt tên mặc định khi cần đối chiếu truy vấn CQL chính xác.

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

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "device_id", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private UUID deviceId;

    @PrimaryKeyColumn(name = "event_day", ordinal = 2,
            type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(name = "event_time", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.DESCENDING)
    private Instant eventTime;

    @PrimaryKeyColumn(name = "event_id", ordinal = 4,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.ASCENDING)
    private UUID eventId;

    public DeviceEventKey() { }

    public DeviceEventKey(UUID tenantId, UUID deviceId,
                          LocalDate eventDay, Instant eventTime,
                          UUID eventId) {
        this.tenantId = tenantId;
        this.deviceId = deviceId;
        this.eventDay = eventDay;
        this.eventTime = eventTime;
        this.eventId = eventId;
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID v) { tenantId = v; }

    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID v) { deviceId = v; }

    public LocalDate getEventDay() { return eventDay; }
    public void setEventDay(LocalDate v) { eventDay = v; }

    public Instant getEventTime() { return eventTime; }
    public void setEventTime(Instant v) { eventTime = v; }

    public UUID getEventId() { return eventId; }
    public void setEventId(UUID v) { eventId = v; }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof DeviceEventKey that)) return false;
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(deviceId, that.deviceId)
            && Objects.equals(eventDay, that.eventDay)
            && Objects.equals(eventTime, that.eventTime)
            && Objects.equals(eventId, that.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(
            tenantId, deviceId, eventDay, eventTime, eventId);
    }
}
~~~

Các kiểu Java này thường được ánh xạ sang Cassandra `uuid`, `date` và `timestamp`. `equals/hashCode` phải tính **đầy đủ thành phần khóa**; nếu chỉ so `eventId`, test/logic dùng Map hoặc Set có thể hiểu nhầm hai key khác partition là giống nhau.

`@PrimaryKeyClass` không thay đổi schema đang chạy. Migration CQL cần tạo đúng bảng trước; integration test phải dùng database có primary key thật khớp với annotation.

## 4. Entity và các giá trị regular column có thể thiếu

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

    public DeviceEvent(DeviceEventKey key,
                       String eventType, String payload,
                       Instant receivedAt) {
        this.key = key;
        this.eventType = eventType;
        this.payload = payload;
        this.receivedAt = receivedAt;
    }

    public DeviceEventKey getKey() { return key; }
    public void setKey(DeviceEventKey v) { key = v; }

    public String getEventType() { return eventType; }
    public void setEventType(String v) { eventType = v; }

    public String getPayload() { return payload; }
    public void setPayload(String v) { payload = v; }

    public Instant getReceivedAt() { return receivedAt; }
    public void setReceivedAt(Instant v) { receivedAt = v; }
}
~~~

Trường `payload` và `received_at` có thể không được ghi hoặc trả về null. Chúng **khác với primary key**: không được sử dụng giá trị null cho thành phần khóa chính.

Trong test, nên cố tình tạo một row có `event_type = "BATTERY_LOW"` nhưng `payload = null`. Khi gọi phương thức trả `Optional<DeviceEvent>`, kết quả phải có entity, còn `event.getPayload()` có thể là null. Đó là test phân biệt “**row tồn tại**” và “**một cột không có giá trị**”.

Không mặc định mọi lần ghi null cho regular column là một phép bỏ qua: một mutation null có thể có ngữ nghĩa tombstone. Bài này tập trung **kiểm thử kết quả đọc**, còn cách cập nhật null/UNSET phải được định nghĩa rõ ở luồng ghi.

## 5. Ba phương thức @Query đáp ứng ba access pattern khác nhau

Repository dùng kiểu ID là `DeviceEventKey`, không phải `UUID`:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {

    // Một row: đủ cả partition key và clustering columns.
    @Query("SELECT * FROM events_by_device_day "
         + "WHERE tenant_id = ?0 AND device_id = ?1 "
         + "AND event_day = ?2 "
         + "AND event_time = ?3 AND event_id = ?4")
    Optional<DeviceEvent> findExact(
        UUID tenantId, UUID deviceId, LocalDate eventDay,
        Instant eventTime, UUID eventId);

    // Nhiều row cùng partition: truy vấn ngày, có paging state.
    @Query("SELECT * FROM events_by_device_day "
         + "WHERE tenant_id = ?0 AND device_id = ?1 "
         + "AND event_day = ?2")
    Slice<DeviceEvent> findDay(
        UUID tenantId, UUID deviceId,
        LocalDate eventDay, Pageable pageable);

    // Khoảng thời gian trong một partition, tối đa 100 row.
    @Query("SELECT * FROM events_by_device_day "
         + "WHERE tenant_id = ?0 AND device_id = ?1 "
         + "AND event_day = ?2 "
         + "AND event_time >= ?3 AND event_time < ?4 "
         + "LIMIT 100")
    List<DeviceEvent> findInWindow(
        UUID tenantId, UUID deviceId, LocalDate eventDay,
        Instant fromInclusive, Instant toExclusive);
}
~~~

`?0`, `?1`… là **tham số theo vị trí của Spring Data**, bắt đầu từ 0; `Pageable` là tham số đặc biệt phục vụ paging. Đổi thứ tự tham số trong Java mà quên sửa placeholder có thể dẫn đến sai kiểu, sai dữ liệu hoặc query lỗi. Đây là lý do phải kiểm thử dữ liệu nhiều thiết bị, nhiều tenant và nhiều ngày.

Điều cần chú ý:

- `findExact` trả `Optional<DeviceEvent>` vì full key cho phép tối đa một row.
- `findDay` trả `Slice<DeviceEvent>` vì một partition có thể có nhiều row và cần trang tiếp.
- `findInWindow` trả `List<DeviceEvent>` nhưng giới hạn `LIMIT 100`; nên dùng `Slice`/driver paging nếu cần duyệt hơn 100 row.
- Không câu nào cần `ALLOW FILTERING` vì đều ràng buộc đủ partition key; các điều kiện clustering hợp lệ.
- Không có JOIN hay scan toàn bảng để tìm sự kiện chỉ bằng `eventId`.

**Giới hạn của CQL:** `event_time` chỉ có thể được so sánh bằng range đúng vị trí clustering trong các truy vấn thích hợp. Đừng thêm tùy ý `WHERE event_type = ...` vào các method và cho rằng `@Query` giúp bỏ qua giới hạn của Cassandra.

## 6. @Query khác với findById như thế nào?

`CassandraRepository` đã có:

~~~java
Optional<DeviceEvent> found =
    repository.findById(fullKey);
~~~

Với entity đã ánh xạ, `findById(fullKey)` tương đương về mục tiêu với `findExact(...)`: tìm một row bằng đầy đủ primary key.

| Trường hợp | Lựa chọn gợi ý | Lý do |
| --- | --- | --- |
| Biết đủ năm thành phần khóa | `findById(DeviceEventKey)` | Gọn, tận dụng mapping của repository |
| Cần biểu diễn CQL tường minh, kiểm soát projection | `@Query findExact(...)` | Câu CQL dễ review/kiểm tra |
| Biết tenant/device/day, muốn 50 event mới | `@Query findDay(...)` | Đọc tập row trong một partition |
| Biết dải time trong cùng ngày | `@Query findInWindow(...)` | Dùng range trên clustering key |
| Chỉ biết eventId | Bảng định vị theo eventId hoặc sửa contract API | EventId không phải partition key của bảng nguồn |

Không nên dựng `DeviceEventKey` chứa `eventTime=null` để giả lập “mọi sự kiện của ngày”. `findById` đòi hỏi full key; muốn nhiều row hãy dùng method truy vấn theo partition key.

Đối với bài học này, ta dùng cả `findById` và `@Query` trong test để chỉ ra rằng hai đường đọc chính xác cùng một row phải có kết quả tương ứng.

## 7. Dựng khóa đúng ngày UTC và độ chính xác millisecond

Một nguyên nhân phổ biến khiến kết quả rỗng ngoài ý muốn là writer và reader tính `event_day` khác nhau hoặc dùng `Instant` khác độ chính xác của `timestamp` Cassandra.

Cassandra `timestamp` lưu thời gian ở độ phân giải **millisecond**, còn Java `Instant` hỗ trợ nanosecond. Nên thống nhất quy tắc ngay khi xây key.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.Objects;
import java.util.UUID;

public final class EventKeyFactory {
    private EventKeyFactory() { }

    public static DeviceEventKey create(
            UUID tenantId, UUID deviceId,
            Instant occurredAt, UUID eventId) {

        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(deviceId, "deviceId");
        Objects.requireNonNull(occurredAt, "occurredAt");
        Objects.requireNonNull(eventId, "eventId");

        Instant time = occurredAt.truncatedTo(ChronoUnit.MILLIS);
        LocalDate utcDay =
            LocalDate.ofInstant(time, ZoneOffset.UTC);

        return new DeviceEventKey(
            tenantId, deviceId, utcDay, time, eventId);
    }
}
~~~

Ví dụ:

~~~text
occurredAt = 2026-11-25T23:59:59.999456789Z
time lưu   = 2026-11-25T23:59:59.999Z
event_day  = 2026-11-25 (UTC)

occurredAt = 2026-11-26T00:00:00.000Z
event_day  = 2026-11-26 (UTC)
~~~

Nếu một service dùng `ZoneId.systemDefault()` còn service khác dùng UTC, hai client có thể nhắm đến partition khác nhau tại ranh giới ngày. Test phải có sự kiện ngay trước và sau nửa đêm UTC.

**Không tạo event ID mới khi retry cùng một sự kiện.** Full key gồm `event_id`; tạo ID mới biến retry thành row mới, gây test trùng dữ liệu và báo cáo sai.

## 8. Phân loại “dữ liệu thiếu” trước khi viết test

Cụm từ **dữ liệu thiếu** có nhiều nghĩa khác nhau:

| Loại thiếu | Ví dụ | Kết quả kỳ vọng |
| --- | --- | --- |
| **Thiếu một thành phần partition key trong query** | Chỉ có `tenant_id` và `device_id` | Query không hợp lệ với access pattern của bảng; không được coi là empty result |
| **Thiếu một clustering key khi cần tìm đúng một row** | Có `event_time` nhưng không có `event_id` | Không định vị một row; cần phương thức range/prefix hợp lệ khác |
| **Full key hợp lệ nhưng row chưa từng được ghi** | Event ID không tồn tại | `Optional.empty()` |
| **Partition chưa có row** | Thiết bị khác/ngày khác | `Slice`/`List` rỗng, không phải exception |
| **Row tồn tại nhưng regular column null** | `payload=null` | Có entity, field payload null |
| **Row đã bị xóa hoặc hết TTL** | Mutation không còn hiển thị | Có thể trả rỗng tùy dữ liệu đang có và consistency |
| **Không kết nối hoặc timeout** | Node lỗi/network lỗi | Exception/đường lỗi hệ thống, **không** chuyển thành rỗng |
| **Mapping/schema sai** | Query chọn cột không tồn tại | Exception; cần sửa migration/query/mapping |

Test cần đặt tên phản ánh tình huống cụ thể: `returnsEmptyWhenRowDoesNotExist` khác hoàn toàn `rejectsQueryMissingPartitionKey`.

Đừng gom mọi `DataAccessException` thành `Collections.emptyList()`. Làm vậy khiến các sự cố production bị hiển thị thành “không có dữ liệu”, che mất lỗi kết nối và schema.

## 9. Hợp đồng kết quả: Optional, List và Slice

Với `@Query`, hãy chọn kiểu trả về theo số row mong đợi.

| Kiểu trả về | Khi có dữ liệu | Khi không có dữ liệu | Lưu ý |
| --- | --- | --- | --- |
| `Optional<DeviceEvent>` | `Optional.of(event)` | `Optional.empty()` | Phù hợp full-key query tối đa một row |
| `List<DeviceEvent>` | Danh sách row | Danh sách rỗng | Không mặc nhiên đồng nghĩa “toàn dữ liệu” nếu có `LIMIT` |
| `Slice<DeviceEvent>` | `getContent()` và thông tin trang tiếp | Content rỗng | Dùng paging state, không phải SQL offset |
| `DeviceEvent` không bọc Optional | Entity khi tìm được | Hành vi vắng mặt phụ thuộc quy ước framework/API | Ưu tiên Optional để hợp đồng vắng row rõ ràng |
| `long` từ `COUNT(*)` | Con số | Có thể là 0 | Đếm nhiều row/partition có thể đắt, không dùng thay existence test rộng |

Với một màn hình chi tiết, code dùng Optional rõ hơn:

~~~java
return repository.findExact(
    tenantId, deviceId, day, eventTime, eventId
).map(this::toDto);
~~~

Nếu `Optional.empty()`, tầng HTTP có thể trả 404 theo contract đã chốt **sau khi kiểm tra quyền truy cập**. Đừng để khác biệt giữa “thiếu event” và “không có quyền” làm lộ thông tin tenant khác. Chính sách trả 403/404 phụ thuộc bảo mật của ứng dụng.

Với timeline, `List.isEmpty()` hoặc `Slice.hasContent()` là tình huống bình thường, chẳng hạn thiết bị mới chưa phát sinh sự kiện trong ngày.

## 10. Chuẩn bị fixture phân biệt nhiều nguyên nhân trả rỗng

Một bộ fixture tốt không chỉ có “1 row đúng”. Nó cần đủ khả năng bắt lỗi **thiếu điều kiện khóa hoặc bind sai vị trí**.

Giả sử tất cả timestamp đều ở UTC:

| Fixture | Tenant | Device | Ngày | Thời điểm | Event ID | Mục đích |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | T1 | D1 | 25/11 | 09:00:00.000 | E1 | Row chính |
| A2 | T1 | D1 | 25/11 | 09:30:00.000 | E2 | Row cùng partition |
| A3 | T1 | D1 | 25/11 | 09:30:00.000 | E3 | Cùng timestamp, khác event ID |
| A4 | T1 | D1 | 25/11 | 10:00:00.000 | E4 | Kiểm thử thứ tự và paging |
| B1 | T1 | D1 | 26/11 | 00:00:00.000 | E5 | Bucket UTC khác |
| C1 | T1 | D2 | 25/11 | 09:30:00.000 | E6 | Device khác |
| D1 | T2 | D1 | 25/11 | 09:30:00.000 | E7 | Tenant khác |
| N1 | T1 | D1 | 25/11 | 10:15:00.000 | E8 | Row có `payload=null` |
| X | T1 | D1 | 25/11 | 09:30:00.000 | EX | **Không insert**: full key vắng mặt |

Dùng `UUID.randomUUID()` cho tenant/device của mỗi test suite hoặc keyspace cô lập, nhưng **cố định các ID khi test cần so thứ tự giữa hai event trùng timestamp**. Nếu ID ngẫu nhiên, đừng hard-code thứ tự tie-breaker mà không tính comparator theo thứ tự Cassandra.

Thiết kế fixture giúp phát hiện:

- Query bỏ quên `tenant_id` vẫn trả nhầm sự kiện từ T2.
- Query bỏ `device_id` vẫn trả nhầm dữ liệu từ D2.
- Query tính sai ngày UTC có thể đọc nhầm B1.
- Query chỉ lọc `event_time` nhưng thiếu `event_id` trả nhiều row dù mong đợi một.
- Query bỏ `payload` trong projection khiến mapper có field null, cần kiểm tra chủ đích.

## 11. Tổ chức integration test với Cassandra thật

Unit test mock repository có thể kiểm tra rằng service gọi đúng method, nhưng **không** xác minh Spring Data sinh CQL đúng hay Cassandra chấp nhận các điều kiện khóa. Kiểm thử `@Query` cần một **Cassandra thực tế trong môi trường test cô lập**, ví dụ Testcontainers hoặc cluster integration test được tổ chức sẵn.

Các điều kiện chuẩn bị:

1. Dùng phiên bản Cassandra gần với môi trường production.
2. Tạo keyspace/bảng bằng cùng migration đã chốt, **không** để entity tự tạo bảng rồi che thiếu migration.
3. Cấu hình local datacenter, contact points, authentication/TLS phù hợp môi trường test.
4. Nếu dùng Spring Boot 3.x, giữ starter/driver được dependency management chọn; không tự trộn driver version.
5. Chờ schema agreement trước khi mở test query.
6. Không chạy test ghi/xóa trên production keyspace.
7. Cô lập fixture bằng keyspace cho suite hoặc tenant/device UUID riêng; không gọi `deleteAll()` trên dữ liệu dùng chung.

Ví dụ cấu hình Spring Boot dành cho môi trường test đã có Cassandra đang chạy:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: telemetry_test
    schema-action: none
~~~

`telemetry_test` và bảng tương ứng phải được migration test tạo trước. `datacenter1` chỉ là ví dụ; tên thực của datacenter phải được lấy từ cluster test. Khi dùng Testcontainers, cần nối mapped port/host và giá trị datacenter thực vào cấu hình Spring bằng cơ chế test phù hợp với phiên bản dự án.

**Bài này chỉ trình bày mã minh họa**, không chạy Gradle, Docker hay Content QA. Mục tiêu là thiết kế được test có thể áp dụng vào dự án.

## 12. Mẫu integration test: tìm đúng row bằng full key

Giả sử repository đã được Spring Boot inject, schema đã tạo và một fixture có khóa chính xác:

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
    void findExact_returnsRowOnlyForFullKey() {
        UUID tenant = UUID.randomUUID();
        UUID device = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();
        Instant time = Instant.parse("2026-11-25T09:30:00.123Z");

        DeviceEventKey key =
            EventKeyFactory.create(tenant, device, time, eventId);

        DeviceEvent stored = new DeviceEvent(
            key, "TEMPERATURE", "{\"celsius\":25.4}", time);
        repository.save(stored);

        var exact = repository.findExact(
            tenant, device, key.getEventDay(),
            key.getEventTime(), eventId);

        assertThat(exact).isPresent();
        assertThat(exact.orElseThrow().getKey()).isEqualTo(key);
        assertThat(exact.orElseThrow().getEventType())
            .isEqualTo("TEMPERATURE");

        // Đường tìm theo ID kế thừa phải nhìn thấy cùng row.
        assertThat(repository.findById(key)).isPresent();

        // Chỉ eventId đổi là một full key khác, không tồn tại.
        var absent = repository.findExact(
            tenant, device, key.getEventDay(),
            key.getEventTime(), UUID.randomUUID());

        assertThat(absent).isEmpty();
    }
}
~~~

Test này cần một row có dữ liệu thật. Nếu chỉ mock `findExact(...)`, ta không chứng minh được:

- `?0…?4` có bind đúng thứ tự không.
- Tên cột trong `@Query` có khớp migration không.
- `timestamp` và `date` có chuyển đổi được không.
- Cassandra thực sự chấp nhận CQL với composite key hay không.

**Không đồng nhất “test green” với hoàn thành QA:** cần thêm negative cases, nhiều partition và paging để tránh false positive do fixture quá đơn giản.

## 13. Kiểm thử sai một thành phần khóa mà không nhầm với row vắng

Test nên thay **từng thành phần** của full key trong khi giữ nguyên những thành phần khác:

~~~java
var correct = repository.findExact(
    tenant, device, day, timestamp, eventId);

var wrongTenant = repository.findExact(
    otherTenant, device, day, timestamp, eventId);

var wrongDevice = repository.findExact(
    tenant, otherDevice, day, timestamp, eventId);

var wrongDay = repository.findExact(
    tenant, device, day.plusDays(1), timestamp, eventId);

var wrongTime = repository.findExact(
    tenant, device, day, timestamp.plusMillis(1), eventId);

var wrongEvent = repository.findExact(
    tenant, device, day, timestamp, otherEventId);
~~~

Nếu fixture chỉ có row với `correct`, các giá trị còn lại nên là `Optional.empty()`. Nhưng cần thêm fixture của **tenant/device khác** để kiểm tra truy vấn thực sự ràng buộc chúng, thay vì chỉ trả rỗng vì database không có dữ liệu nào khác.

Ví dụ: thêm một row cùng timestamp/event ID nhưng thuộc `otherTenant`, rồi khẳng định query của tenant hiện tại vẫn chỉ trả row của tenant đó. Kiểm thử này bắt được lỗi query vô tình thiếu filter tenant khi truy vấn được viết lại trong tương lai.

Dù test cho `wrongTenant` trả empty, **không nên xem đó là kiểm thử phân quyền đầy đủ**. Quyền tenant còn phải được kiểm tra ở service/controller hoặc cơ chế cô lập dữ liệu mà sản phẩm áp dụng. Repository không tự xác thực quyền người dùng HTTP chỉ vì có cột `tenant_id`.

## 14. Dữ liệu thiếu: row tồn tại nhưng payload null

Khởi tạo một row có `event_type` nhưng `payload` bị bỏ trống/null theo hợp đồng ghi:

~~~java
DeviceEvent event = new DeviceEvent(
    key,
    "BATTERY_LOW",
    null, // payload không bắt buộc
    Instant.parse("2026-11-25T10:15:00Z")
);

repository.save(event);
~~~

Sau đó kiểm tra:

~~~java
var result = repository.findExact(
    key.getTenantId(),
    key.getDeviceId(),
    key.getEventDay(),
    key.getEventTime(),
    key.getEventId()
);

assertThat(result).isPresent();
assertThat(result.orElseThrow().getEventType())
    .isEqualTo("BATTERY_LOW");
assertThat(result.orElseThrow().getPayload()).isNull();
~~~

Ý nghĩa:

- `Optional` có giá trị vì **row có full primary key đang tồn tại** và có regular column `event_type`.
- `payload == null` chỉ cho biết cột ấy không có giá trị hiển thị tại thời điểm đọc.
- Nếu API yêu cầu `payload` bắt buộc, đây là lỗi **validation/domain** cần phát hiện ở đường ghi, không nên đổi thành “event không tồn tại”.
- Tùy chiến lược ghi và phiên bản mapping, `null` có thể tương ứng một cột chưa từng ghi hoặc mutation xóa/tombstone; test không nên tự suy ra lịch sử từ kết quả null.

Khi test `@Query` chỉ chọn projection một số cột, phải kiểm tra các field **được chọn** và hiểu rằng những cột không SELECT sẽ không có dữ liệu để mapper điền. Nếu cần full entity, sử dụng `SELECT *` trong test/hành vi tương ứng; trong production nên cân nhắc projection DTO để giảm payload khi row có nhiều trường lớn.

## 15. Tập kết quả rỗng cho một partition hoàn toàn mới

Để kiểm thử query timeline không có dữ liệu, chọn một tenant/device/day chưa từng insert. Không sử dụng `eventTime=null` hoặc một key thiếu thành phần để mô phỏng partition trống.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.data.cassandra.core.query.CassandraPageRequest;

UUID tenant = UUID.randomUUID();
UUID device = UUID.randomUUID();
LocalDate day = LocalDate.of(2026, 11, 25);

var slice = repository.findDay(
    tenant, device, day, CassandraPageRequest.first(50));

assertThat(slice.getContent()).isEmpty();
assertThat(slice.hasContent()).isFalse();
assertThat(slice.hasNext()).isFalse();
~~~

Với `List<DeviceEvent>` của `findInWindow`, khi không có row khớp:

~~~java
var rows = repository.findInWindow(
    tenant, device, day,
    Instant.parse("2026-11-25T08:00:00Z"),
    Instant.parse("2026-11-25T09:00:00Z"));

assertThat(rows).isEmpty();
~~~

Không nên khẳng định `slice == null` hoặc `rows == null`: với những kiểu trả về collection/Slice thông thường, hợp đồng mong đợi là **đối tượng kết quả hợp lệ chứa 0 phần tử**, không phải một exception.

### Phân biệt với lỗi kết nối

Nếu Cassandra không khả dụng, query có thể ném exception. Đừng viết:

~~~java
// SAI: biến sự cố hạ tầng thành dữ liệu rỗng.
try {
    return repository.findDay(tenant, device, day, pageable);
} catch (Exception ex) {
    return Slice.empty();
}
~~~

Ứng dụng cần xử lý timeout/unavailable theo chính sách lỗi/retry của API, báo đúng trạng thái giám sát và không làm người dùng tin rằng “ngày đó không có sự kiện”.

## 16. Test khoảng thời gian: inclusive và exclusive

Trong `findInWindow`, điều kiện:

~~~sql
AND event_time >= ?
AND event_time < ?
~~~

diễn tả **[fromInclusive, toExclusive)**. Cách này hữu ích vì các bucket thời gian liền kề có thể ghép lại mà không đếm một event ở ranh giới hai lần.

Ví dụ:

~~~text
Range A: [09:00:00.000, 10:00:00.000)
Range B: [10:00:00.000, 11:00:00.000)
~~~

Tạo ba event:

- E1 ở `09:00:00.000Z`.
- E2 ở `09:59:59.999Z`.
- E3 ở `10:00:00.000Z`.

Test:

~~~java
var rows = repository.findInWindow(
    tenant, device, LocalDate.of(2026, 11, 25),
    Instant.parse("2026-11-25T09:00:00Z"),
    Instant.parse("2026-11-25T10:00:00Z"));

assertThat(rows).extracting(
    e -> e.getKey().getEventId()
).containsExactlyInAnyOrder(e1Id, e2Id);
~~~

E3 **không thuộc** khoảng giờ đầu. Test còn nên có dữ liệu ở `08:59:59.999Z` để chứng minh điều kiện `>=` không lấy thêm row trước phạm vi.

Nếu `from >= to`, service nên từ chối request hoặc trả rỗng theo contract đã chốt; không để client nhập mốc giờ tùy ý rồi hiểu nhầm kết quả.

## 17. Test ngày UTC ở ranh giới nửa đêm

Một event ở `2026-11-25T23:59:59.999Z` thuộc bucket `2026-11-25`, còn `2026-11-26T00:00:00.000Z` thuộc bucket `2026-11-26`.

Ví dụ:

~~~java
Instant beforeMidnight =
    Instant.parse("2026-11-25T23:59:59.999Z");
Instant afterMidnight =
    Instant.parse("2026-11-26T00:00:00.000Z");

var keyA = EventKeyFactory.create(
    tenant, device, beforeMidnight, UUID.randomUUID());
var keyB = EventKeyFactory.create(
    tenant, device, afterMidnight, UUID.randomUUID());

assertThat(keyA.getEventDay())
    .isEqualTo(LocalDate.of(2026, 11, 25));
assertThat(keyB.getEventDay())
    .isEqualTo(LocalDate.of(2026, 11, 26));
~~~

Sau khi insert cả hai row, query `findDay(..., 2026-11-25)` phải trả sự kiện A mà **không** trả B; query ngày 26 trả B.

Không dùng múi giờ máy chạy test làm nguồn sự thật. Dùng `ZoneOffset.UTC` và `Instant.parse(...)` có hậu tố `Z` để kết quả ổn định trên máy developer, CI và container.

### Thử timestamp chứa nanosecond

~~~java
Instant raw =
    Instant.parse("2026-11-25T09:30:00.123456789Z");

DeviceEventKey key =
    EventKeyFactory.create(tenant, device, raw, eventId);

assertThat(key.getEventTime())
    .isEqualTo(Instant.parse("2026-11-25T09:30:00.123Z"));
~~~

Test này giúp giữ cùng chính sách canonicalization cho writer và reader, giảm những trường hợp `Optional.empty()` do cách dựng khóa không nhất quán.

## 18. Test nhiều row cùng timestamp và thứ tự clustering

Nếu `event_time` có độ chính xác millisecond, hai event có thể cùng thời điểm. `event_id` là clustering tie-breaker để chúng có hai full key khác nhau.

Cần test:

1. Ghi E1 và E2 với **cùng** `tenant, device, day, event_time` nhưng `event_id` khác.
2. `findExact(... E1)` và `findExact(... E2)` đều có kết quả riêng.
3. `findDay(...)` không làm mất một trong hai row.
4. Các row được đọc theo `event_time DESC`; khi time bằng nhau, test thứ tự `event_id ASC` đúng với DDL.

Ví dụ chọn ID có thứ tự dễ quan sát:

~~~java
UUID firstId = UUID.fromString(
    "00000000-0000-4000-8000-000000000001");
UUID secondId = UUID.fromString(
    "00000000-0000-4000-8000-000000000002");

Instant time = Instant.parse("2026-11-25T09:30:00Z");

// Insert hai DeviceEvent cùng time, khác event_id.

var page = repository.findDay(
    tenant, device, LocalDate.of(2026, 11, 25),
    CassandraPageRequest.first(50));

// Nếu chỉ có hai fixture này trong partition và DDL như ví dụ:
assertThat(page.getContent())
    .extracting(e -> e.getKey().getEventId())
    .containsExactly(firstId, secondId);
~~~

Nếu partition còn các fixture khác, đừng dùng `containsExactly` như ví dụ hai row cô lập. Cần khởi tạo partition riêng cho test hoặc lọc đối tượng so sánh có kiểm soát.

**Không giả định ORDER BY toàn cục giữa nhiều partition.** Các test chỉ nên khẳng định thứ tự clustering trong một partition, hoặc kiểm tra riêng thuật toán merge của ứng dụng khi đọc nhiều ngày.

## 19. Test Slice nhiều trang và trang rỗng ở cuối

Muốn test paging thật, cần seed **nhiều row hơn page size**, ví dụ 5 event cùng một partition và `CassandraPageRequest.first(2)`.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.domain.Slice;

List<DeviceEvent> collected = new ArrayList<>();

Slice<DeviceEvent> page = repository.findDay(
    tenant, device, day, CassandraPageRequest.first(2));

while (true) {
    collected.addAll(page.getContent());

    if (!page.hasNext()) {
        break;
    }

    page = repository.findDay(
        tenant, device, day, page.nextPageable());
}

assertThat(collected).hasSize(5);
~~~

Ngoài số lượng, test phải khẳng định:

- Không có `eventId` bị lặp qua hai trang.
- Không thiếu event thuộc partition được seed.
- Thứ tự toàn chuỗi phù hợp `event_time DESC, event_id ASC`.
- Cursor/trang tiếp **không dùng lại** với tenant/device/day khác.
- Nếu partition trống, trang đầu có `getContent().isEmpty()` và `hasNext() == false`.
- Khi request tới cuối, vòng lặp dừng; không tiếp tục gọi `nextPageable()` tùy tiện khi `hasNext()` là false.

Cassandra paging state không phải SQL offset; không nên test bằng “`page=1000`” rồi mong nhảy tới row thứ 50.000. Nếu API cần cursor giữa hai HTTP request, phải ký/xác thực token và gắn nó với filter, quyền tenant, bucket và page size.

### Một lưu ý về dữ liệu đang thay đổi

Khi một event mới được ghi trong lúc người dùng đang duyệt các trang cũ, Cassandra không tự tạo snapshot transaction bất biến cho toàn bộ quá trình paging. Test ổn định thứ tự phải dùng fixture **không có concurrent writes**. Sau đó mới thêm test riêng cho yêu cầu nghiệp vụ khi dữ liệu thay đổi trong lúc phân trang.

## 20. Thiếu khóa không phải là một kết quả rỗng

Câu sau không cung cấp đủ composite partition key của bảng:

~~~sql
-- Không đúng access pattern của bảng:
SELECT *
FROM telemetry.events_by_device_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222;
~~~

`event_day` là thành phần thứ ba của partition key. Không có bucket ngày, Cassandra không thể định tuyến một partition duy nhất theo cách thiết kế.

Tương tự, query chỉ theo `event_id` không định vị được row:

~~~sql
-- event_id là clustering column thứ hai, không phải partition key.
SELECT *
FROM telemetry.events_by_device_day
WHERE event_id = 33333333-3333-4333-8333-333333333333;
~~~

**Không thêm `ALLOW FILTERING` vào test hoặc production chỉ để biến query sai thành “chạy được”.** Điều đó có thể làm server phải lọc nhiều partition và khiến chi phí tăng theo dữ liệu.

Nếu cần tìm event bằng `eventId` độc lập, thiết kế một bảng tra vị trí theo `event_id` hoặc thay API để client cung cấp đủ khóa. Test phải kiểm tra tính đồng bộ giữa bảng lookup và bảng nguồn nếu chọn giải pháp hai bảng.

### Negative test với Java driver

Có thể dùng `CqlSession` trực tiếp trong integration test để xác nhận một câu CQL thiếu partition key bị Cassandra từ chối, và giữ tình huống này **ngoài repository production**:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.servererrors.InvalidQueryException;

assertThatThrownBy(() -> session.execute(
    "SELECT * FROM telemetry.events_by_device_day "
  + "WHERE tenant_id = 11111111-1111-4111-8111-111111111111 "
  + "AND device_id = 22222222-2222-4222-8222-222222222222"
)).isInstanceOf(InvalidQueryException.class);
~~~

Loại exception và thông điệp có thể khác theo phiên bản Cassandra/driver và cách Spring dịch lỗi; nếu gọi qua repository/template, có thể nhận `DataAccessException` của Spring. Test nên tập trung vào **việc truy vấn sai không được chấp nhận**, thay vì so khớp nguyên văn thông báo lỗi server.

## 21. Đừng biến timeout thành Optional.empty()

Một lớp service có thể có logic:

~~~java
public Optional<DeviceEvent> findDetail(
        UUID tenantId, UUID deviceId,
        Instant occurredAt, UUID eventId) {

    DeviceEventKey key = EventKeyFactory.create(
        tenantId, deviceId, occurredAt, eventId);

    return repository.findExact(
        key.getTenantId(), key.getDeviceId(),
        key.getEventDay(), key.getEventTime(), key.getEventId());
}
~~~

Tầng service nên validate input trước khi gọi repository và chỉ chuyển `Optional.empty()` thành “không tìm thấy” theo API contract. Nếu có exception do Cassandra timeout, unavailable, schema mismatch hoặc mapping, hãy xử lý theo chính sách hạ tầng: log có ngữ cảnh, metrics, retry có kiểm soát và phản hồi lỗi phù hợp.

**Tuyệt đối tránh:**

~~~java
// Anti-pattern: che lỗi DB thành "không tìm thấy".
try {
    return repository.findExact(tenant, device, day, time, event);
} catch (RuntimeException ex) {
    return Optional.empty();
}
~~~

Một API có thể cần phân biệt HTTP 404 khi dữ liệu không tồn tại với HTTP 503/5xx khi backend không sẵn sàng. Che lỗi sẽ làm monitoring không nhìn thấy sự cố và có thể khiến người dùng đưa ra quyết định dựa trên thông tin sai.

## 22. Consistency ảnh hưởng cách diễn giải test “không tìm thấy”

Cassandra là cơ sở dữ liệu phân tán với nhiều replica. Trong cluster RF=3 ở một datacenter, một lần ghi với `LOCAL_QUORUM` cần đa số replica local xác nhận. Đọc `LOCAL_ONE` yêu cầu một replica local, nên trong một số trường hợp có thể trả dữ liệu cũ hoặc chưa thấy mutation mới nhất.

Các tình huống cần phân biệt:

- **Row chưa từng được ghi:** query hợp lệ trả rỗng.
- **Row vừa được ghi nhưng một replica còn chậm:** kết quả đọc tùy consistency và trạng thái replica.
- **Row bị xóa/hết TTL:** query có thể không thấy row.
- **Bảng projection chưa được cập nhật:** read trên bảng projection thiếu dữ liệu dù bảng nguồn đã có.
- **Đọc sai tenant/day/time:** query hợp lệ về cú pháp nhưng nhắm partition/row khác.

Với test chức năng mapping, chạy trên cluster test ổn định, chờ write xác nhận rồi kiểm tra read theo consistency đã chốt. Đừng viết unit test kết luận “`LOCAL_ONE` luôn trả dữ liệu cũ” hoặc “`LOCAL_QUORUM` bảo đảm mọi thao tác nhiều bảng nhất quán” — cả hai đều không chính xác.

Khi test fail không ổn định do timing, trước hết xác định nguyên nhân: chưa đợi container/schema, timestamp precision, eventual consistency, pipeline lag hay thực sự sai query. Không dùng `Thread.sleep(...)` tùy ý để che lỗi mô hình hoặc cấu hình.

## 23. Kiểm thử @Query không được bỏ qua tenant isolation

Bảng ví dụ đưa `tenant_id` vào partition key, nhưng **đó chưa phải toàn bộ kiểm soát truy cập**. Service phải kiểm tra người dùng có quyền với tenant và device được yêu cầu.

Test bảo vệ tối thiểu:

1. Seed tenant T1, device D1, event E1.
2. Seed tenant T2, device D1 (cùng UUID thiết bị nếu domain cho phép), event E2.
3. Gọi repository với T1; kết quả chỉ gồm event thuộc T1.
4. Gọi API với credential không được quyền T2; hệ thống phải từ chối hoặc không tiết lộ dữ liệu theo chính sách bảo mật.
5. Không cho phép request tự bỏ `tenantId` khỏi `@Query` hoặc truyền tenant khác qua một route phụ.

Trong test repository, tập trung vào ranh giới **query filter**. Trong test API/security, tập trung vào **authorization**. Hai loại test bổ sung cho nhau; không thay thế lẫn nhau.

Nếu cần kiểm tra “không có dữ liệu” nhưng thực chất do caller không có quyền, response HTTP phải theo chính sách bảo mật đã chốt, không để client suy đoán tồn tại dữ liệu tenant khác.

## 24. Truy vấn sai @Query có thể fail lúc nào?

Một lỗi thường gặp là tin rằng ứng dụng khởi động được thì mọi method `@Query` đều đã hợp lệ. Tùy phiên bản Spring Data Cassandra, driver, quá trình khởi tạo repository và CQL cụ thể, một số sai sót có thể lộ ra khi **phương thức thực sự được gọi**:

- Tên bảng/cột sai hoặc migration chưa chạy.
- Số lượng/kiểu bind values không phù hợp placeholder.
- Cột trong `WHERE` không theo partition/clustering key.
- Giá trị khóa bắt buộc null hoặc sai `date`/`timestamp`.
- Projection và entity mapping không khớp loại dữ liệu.
- Query bị Cassandra từ chối do filtering không phù hợp.

Do đó, integration test nên **gọi từng phương thức query quan trọng ít nhất một lần** trên Cassandra thật, với fixture có row. Chỉ khởi động Spring context hoặc dùng mock DAO không đủ để bảo đảm câu CQL được server chấp nhận.

Khi code có nhiều `@Query`, có thể lập test contract theo bảng:

| Method | Có dữ liệu | Không dữ liệu | Sai khóa | Phân trang |
| --- | --- | --- | --- | --- |
| `findExact` | 1 row đúng | `Optional.empty()` | Test đổi từng thành phần | Không áp dụng |
| `findDay` | Đúng partition và thứ tự | Empty `Slice` | Thiếu tenant/day không được phép | Trang đầu/giữa/cuối |
| `findInWindow` | Đúng dải và giới hạn | Empty `List` | Không được bỏ partition key | `LIMIT 100` hoặc nâng cấp `Slice` |

## 25. Kiểm thử trên dữ liệu phân bố thực tế

Một test 3–5 row là cần thiết để chứng minh hành vi, nhưng chưa đủ để kết luận query phù hợp production. Sau unit/integration tests nên có kiểm thử workload riêng:

- Nhiều row cùng millisecond nhưng khác event ID.
- Một thiết bị ít sự kiện và một thiết bị rất nhiều sự kiện.
- Partition ngày UTC rỗng, rất nhỏ và rất lớn.
- Dữ liệu ở ranh giới nửa đêm, TTL/hết hạn và event đến muộn.
- Các tenant/device có UUID giống nhau trong các chiều khác để bắt lỗi filter.
- Truy vấn read với `LIMIT`/paging ở mức tải đại diện.
- Độ trễ p95/p99, timeout, retry và số partition chạm.

**Không sử dụng `findAll()` hoặc query bỏ partition key để kiểm chứng “bảng có dữ liệu”** trên môi trường lớn. Với fixture test cô lập, có thể tìm row bằng full key hoặc query một partition đã biết để xác nhận setup.

## 26. Debug khi @Query trả rỗng bất thường

Khi API “mất dữ liệu”, làm theo trình tự thay vì vội thêm `ALLOW FILTERING`:

1. **In/ghi nhận query ID** và xác định method `@Query` đang chạy.
2. **Đối chiếu full primary key** mong đợi với các tham số đã bind: tenant, device, ngày UTC, event time, event ID.
3. **Kiểm tra timestamp precision**: cả writer và reader có dùng millisecond hay không.
4. **Kiểm tra schema thật** bằng `DESCRIBE TABLE` trong `cqlsh` hoặc `system_schema`/driver metadata.
5. **Đọc thử đúng full key** trên test/staging để phân biệt row vắng với query method sai.
6. **Đối chiếu consistency và trạng thái ghi**: write đã nhận xác nhận chưa, replica có đang chậm không.
7. **Kiểm tra TTL, delete và projection lag** nếu dữ liệu có lifecycle.
8. **Kiểm tra paging state** nếu chỉ trang sau bị thiếu/trùng.
9. **So sánh fixture tenant/device/day** để bắt lỗi thiếu điều kiện WHERE.
10. **Phân loại exception**: server từ chối query, timeout và empty result là những trạng thái khác nhau.

Khi log, chỉ ghi định danh/tracing cần thiết và thông tin thời gian được phép; không log payload nhạy cảm, mật khẩu, secret hay thông tin người dùng không cần thiết.

Một ví dụ sai rất dễ bỏ qua:

~~~text
Writer:
  event_time = 2026-11-25T23:45:00Z
  event_day  = 2026-11-25 UTC

Reader:
  event_time = 2026-11-25T23:45:00Z
  event_day  = 2026-11-26 theo múi giờ địa phương

Result:
  Optional.empty() — query có cú pháp đúng,
  nhưng đang nhìn partition ngày khác.
~~~

## 27. Anti-pattern và phương án sửa

| Anti-pattern | Vì sao sai | Cách làm phù hợp |
| --- | --- | --- |
| `findExact` chỉ bind `eventId` | Thiếu partition key và clustering prefix | Truyền full key hoặc tạo bảng lookup theo ID |
| Dùng `findById` với clustering fields null | ID của row không đầy đủ | Tạo query theo partition key cho danh sách |
| `@Query` thiếu tenant trong `WHERE` | Có nguy cơ đọc nhầm tenant/query không hợp lệ | Bind đầy đủ composite partition key |
| Test chỉ có 1 row trong 1 partition | Không bắt được lỗi bỏ điều kiện khóa | Fixture đa tenant, đa device, đa ngày |
| Dùng ngày local thay UTC | Sai bucket tại ranh giới ngày | Canonicalize UTC khi ghi và đọc |
| Dùng `Instant` nanosecond không chuẩn hóa | Full key so khớp khác dữ liệu lưu | Truncate millisecond theo policy |
| Catch mọi exception rồi trả empty | Che sự cố DB thành “không có dữ liệu” | Phân loại lỗi hệ thống và empty result |
| Kiểm tra có payload mới coi event tồn tại | Regular column null không có nghĩa row vắng | Phân biệt entity presence và field presence |
| `findDay` trả list không giới hạn | Rủi ro heap/latency khi partition lớn | `Slice`, `LIMIT` và paging có kiểm soát |
| Truy vấn nhiều ngày rồi mong global `ORDER BY` | Ordering chỉ đúng trong partition | Đọc bucket riêng và merge ở ứng dụng |
| Đếm toàn bảng để test dataset không rỗng | `COUNT(*)` rộng có chi phí lớn | Verify bằng full key hoặc test partition |
| Thêm `ALLOW FILTERING` để sửa test fail | Che access pattern sai bằng scan | Sửa CQL/schema, không dùng filtering tùy tiện |

## 28. Bài tập thực hành

### Bài A — Phân loại kết quả rỗng

Với bảng `PRIMARY KEY ((tenant_id, device_id, event_day), event_time, event_id)`, hãy phân loại năm tình huống:

1. `findExact` với full key chưa từng ghi.
2. `findDay` với một partition mới chưa có event.
3. Query `WHERE tenant_id=? AND device_id=?`.
4. Row có `event_type` nhưng `payload=null`.
5. Cassandra timeout khi chạy `findExact`.

**Gợi ý:** tương ứng: `Optional.empty()`; empty `Slice`; query không đủ partition key; entity có mặt nhưng field null; lỗi hệ thống/exception.

### Bài B — Test sai thứ tự tham số

Developer thay `@Query` thành `WHERE tenant_id=?1 AND device_id=?0` nhưng giữ nguyên chữ ký method. Với fixture đa tenant, đa device, test nào sẽ bắt lỗi? Vì sao chỉ có một row trong database dễ khiến lỗi không được phát hiện hoặc không được kiểm thử đủ?

**Gợi ý:** tạo các ID khác nhau, seed các row tại nhiều partition; khẳng định đúng kết quả và tính cách ly. Nên kiểm tra binding/type ngay khi gọi integration test.

### Bài C — Ranh giới UTC

Viết test hai sự kiện ở `23:59:59.999Z` ngày 25 và `00:00:00.000Z` ngày 26, rồi đọc `findDay` cho từng ngày. Tại sao không dùng `ZoneId.systemDefault()` khi dựng `event_day`?

### Bài D — Equal timestamp, different eventId

Tạo hai event cùng `tenant, device, day, event_time` nhưng `event_id` khác. Kiểm tra cả hai tìm được bằng `findExact`, cùng xuất hiện trong `findDay` và có thứ tự phù hợp `event_id ASC`.

### Bài E — Range query

Bảng có sự kiện lúc `09:00:00.000Z`, `09:59:59.999Z` và `10:00:00.000Z`. Gọi `findInWindow(..., 09:00, 10:00)`; khẳng định chính xác hai event đầu, không lấy event thứ ba.

### Bài F — Empty Slice và paging

Seed 5 event cùng một partition, page size 2. Viết vòng lặp `hasNext()/nextPageable()`, kiểm tra tập ID nhận được có đúng 5, không trùng, đúng thứ tự. Sau đó thử partition chưa có row; kỳ vọng gì với `hasContent()` và `hasNext()`?

### Bài G — Null field so với missing row

Ghi một event có `event_type="BATTERY_LOW"` và `payload=null`. Hãy viết test chứng minh `findExact` có entity nhưng payload null; đổi event ID sang khóa chưa có và chứng minh `Optional.empty()`.

### Bài H — Thiếu khóa và cách giải quyết nghiệp vụ

Product cung cấp chỉ `eventId` nhưng yêu cầu mở chi tiết event. Vì sao không thể dùng `@Query` theo event ID đơn lẻ trên bảng theo device/day? Thiết kế bảng lookup theo event ID và nêu cách kiểm thử dual-write, backfill và retry idempotent.

### Bài I — Đánh giá độ mới dữ liệu

Ghi ở `LOCAL_QUORUM`, đọc ở `LOCAL_ONE`. Test nào nên dùng để xác minh mapping/CQL trên cluster test ổn định? Test nào dành riêng để đánh giá replica chậm, consistency và read-your-writes? Vì sao không được khẳng định `LOCAL_ONE` lúc nào cũng cũ?

**Tiêu chí hoàn thành:** người học tự viết được `@Query` với composite partition key và clustering columns, kiểm tra các trường hợp full key/missing row/null field/empty collection, phân trang bằng `Slice`, nhận diện lỗi thiếu khóa và phân biệt dữ liệu rỗng với exception.

## 29. Checklist review trước khi merge một @Query

- [ ] Method `@Query` có xác định đúng table và keyspace?
- [ ] Query bind **đủ các thành phần partition key** cho access pattern dự kiến?
- [ ] Nếu tìm một row, có đủ các clustering columns để xác định full primary key?
- [ ] Chỉ số `?0, ?1, ...` khớp chính xác thứ tự tham số Java?
- [ ] Kiểu `UUID`/`LocalDate`/`Instant` và migration CQL tương thích?
- [ ] Bucket ngày dùng UTC và timestamp chuẩn millisecond?
- [ ] Kiểu trả về `Optional`/`List`/`Slice` khớp số row và cách phân trang?
- [ ] Test có row tồn tại, full key sai, partition trống và regular column null?
- [ ] Test có nhiều tenant/device/day, ranh giới UTC và timestamp trùng?
- [ ] Test trang đầu/giữa/cuối, không lặp/thiếu row khi đọc nhiều trang?
- [ ] Không nuốt timeout/schema exception thành kết quả rỗng?
- [ ] Không dùng `ALLOW FILTERING` hoặc `findAll()` để che query thiếu key?
- [ ] Đã kiểm tra consistency, retention/TTL và khả năng dữ liệu đến muộn?
- [ ] Đã có integration test trên Cassandra và schema do migration tạo?
- [ ] Có log/metrics đủ điều tra nhưng không lộ payload hoặc thông tin tenant nhạy cảm?

## Tài liệu tham khảo

- [Spring Data Cassandra — Repository Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html): `@Query`, bind parameters và các kiểu trả về.
- [Spring Data Cassandra — Cassandra Repositories](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/repositories.html): `CassandraRepository`, `findById`, các phương thức CRUD.
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): `@PrimaryKeyClass`, `@PrimaryKeyColumn`, entity mapping và Java types.
- [Spring Data Cassandra — Paging](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html): `Slice`, `CassandraPageRequest` và paging state.
- [Apache Cassandra — CQL SELECT](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): partition key, clustering conditions, `LIMIT` và `ALLOW FILTERING`.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/): thiết kế theo truy vấn và phân vùng.
- [Java Driver 4 — Prepared Statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/): bind parameters, kiểu dữ liệu và thực thi CQL.
