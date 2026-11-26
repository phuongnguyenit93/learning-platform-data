# Lấy trang đầu rồi tiếp tục qua nextPageable trong Spring Data Cassandra

Trong **Spring Data Cassandra**, khi API cần hiển thị “20 sự kiện mới nhất” rồi cho người dùng nhấn **Xem thêm**, ứng dụng không nên tải toàn bộ lịch sử vào `List` rồi tự cắt trang. Apache Cassandra hỗ trợ **paging state**: một trạng thái do driver nhận từ kết quả hiện tại để **tiếp tục** truy vấn tương thích ở trang kế tiếp. Spring Data cung cấp `CassandraPageRequest.first(size)`, kết quả `Slice<T>` và đặc biệt là **`slice.nextPageable()`** để nối tiếp luồng đó.

Bài học thuộc chương **Chiếu và phân trang** của module **SPRING_DATA_CASSANDRA**. Nội dung tập trung vào thao tác **lấy trang đầu rồi tiếp tục qua `nextPageable`**, kết hợp entity mapping, repository, `CassandraTemplate`, CQL, projection (chỉ trả các thuộc tính cần thiết), partition key, clustering order, tính nhất quán và hiệu năng theo mô hình dữ liệu phân tán.

Kết thúc bài học, bạn có thể:

1. Phân biệt `Slice<T>`, `Page<T>`, `List<T>`, `LIMIT`, page size và paging state.
2. Viết repository nhận `Pageable`, gọi `CassandraPageRequest.first(20)` rồi `slice.nextPageable()` đúng cách.
3. Dùng `Query.pageRequest(pageable)` với `CassandraOperations.slice(...)` khi cần `CassandraTemplate`.
4. Kết hợp projection để giảm dữ liệu truyền về mà vẫn giữ đường truy vấn theo khóa.
5. Thiết kế API cursor an toàn và kiểm thử các lỗi thường gặp: dùng `OFFSET`, đổi filter giữa các trang, hot partition, timeout và dữ liệu thay đổi trong lúc phân trang.

## 1. Vì sao Cassandra không dùng OFFSET như SQL truyền thống?

Trong cơ sở dữ liệu quan hệ, ta thường thấy:

~~~sql
-- Ví dụ SQL quan hệ, KHÔNG phải CQL hợp lệ để phân trang Cassandra.
SELECT * FROM events
ORDER BY occurred_at DESC
LIMIT 20 OFFSET 2000;
~~~

Cassandra **không cung cấp kiểu OFFSET tổng quát** để nhảy thẳng đến trang thứ 101 theo cách này. Dữ liệu được phân phối theo **partition key**; trong partition, các hàng được sắp theo **clustering columns**. Muốn đọc tiếp một truy vấn, driver nhận một **paging state** (trạng thái tiến độ) và dùng nó khi thực thi lượt lấy dữ liệu kế tiếp.

~~~text
CQL cố định + bind values cố định
                 |
                 v
           Trang đầu tiên
          20 hàng + state A
                 |
       nextPageable() chứa
         thông tin tiếp tục
                 |
                 v
            Trang thứ hai
          20 hàng + state B
                 |
           nextPageable()
                 |
                 v
         ... đến hết kết quả
~~~

Đây là cách **di chuyển tiến một chiều** theo kết quả của câu truy vấn. Để mở “trang 101” từ đầu, thông thường phải đi qua các trang trước hoặc có cơ chế chỉ mục/cursor riêng được thiết kế theo nghiệp vụ. Không thể chỉ viết `PageRequest.of(100, 20)` rồi mong Cassandra tự nhảy đến offset 2000.

> **Điểm then chốt:** Paging state không phải thứ tự sắp xếp và cũng không phải một khóa nghiệp vụ. Nó chỉ mô tả **vị trí tiếp tục** của một truy vấn CQL trong một ngữ cảnh cụ thể.

## 2. Thiết kế bảng theo đường đọc trước khi phân trang

Giả sử API theo dõi thiết bị cần:

~~~text
GET /tenants/{tenantId}/devices/{deviceId}/events
    ?day=2026-11-25
    &pageSize=20

Hiển thị 20 sự kiện gần nhất trong ngày,
sau đó tiếp tục từng trang nếu còn dữ liệu.
~~~

Bảng phục vụ đường truy vấn này:

~~~sql
CREATE TABLE events_by_device_day (
    tenant_id uuid,
    device_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    description text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

| Cột | Vai trò | Hệ quả với phân trang |
|---|---|---|
| `tenant_id` | Thành phần partition key | Không lẫn tenant |
| `device_id` | Thành phần partition key | Xác định thiết bị cần đọc |
| `event_day` | Thành phần partition key | Chia lịch sử theo ngày |
| `occurred_at` | Clustering DESC | Sự kiện mới hơn đứng trước |
| `event_id` | Clustering ASC | Phá hòa khi hai sự kiện cùng thời gian |
| `event_type`, `description` | Cột thường | Hiển thị; không được dùng để sort tùy ý |

Truy vấn chuẩn:

~~~sql
SELECT tenant_id, device_id, event_day,
       occurred_at, event_id, event_type, description
FROM events_by_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?;
~~~

Ba dấu bind tương ứng với **đầy đủ composite partition key**. Chúng giữ nguyên ở **mọi trang**. Dữ liệu được đọc theo clustering order đã khai báo trong schema; không cần tự nối `ORDER BY description`, vì Cassandra không hỗ trợ sắp xếp theo một cột thường như vậy.

Nếu một thiết bị tạo quá nhiều sự kiện mỗi ngày, partition theo ngày có thể trở nên lớn/nóng. Khi đó cần xem xét bucket theo giờ hoặc shard, đồng thời cân nhắc chi phí đọc nhiều partition. **Giảm page size không sửa được hot partition**.

## 3. Ba loại kết quả: List, Slice, Page

| Kiểu trả về | Biết số hàng trang hiện tại? | Biết còn trang sau? | Biết tổng số trang/toàn bộ hàng? | Phù hợp cho Cassandra |
|---|---|---|---|---|
| `List<T>` | Có, vì đã tải một danh sách | Không mang metadata cursor mặc định | Không | Tập kết quả nhỏ, đã có giới hạn rõ |
| `Slice<T>` | Có | **Có, qua `hasNext()`** | Không | **Rất phù hợp** để đọc tiến một chiều |
| `Page<T>` | Có | Có | Thường đòi hỏi thông tin tổng số | Không nên mặc định vì đếm toàn bộ có thể rất đắt |

`Slice<T>` đủ cho giao diện **Xem thêm**: API chỉ cần nội dung trang hiện tại và thông tin **có thể tiếp tục hay không**. Nó không cần biết có chính xác 6.314 trang trong bảng.

**Cảnh báo về COUNT:** tính tổng hàng của truy vấn Cassandra không tương đương một phép `COUNT(*)` miễn phí trong cơ sở dữ liệu quan hệ. Nếu sản phẩm cần hiển thị tổng số sự kiện, nên đánh giá một mô hình thống kê/tổng hợp riêng theo nhu cầu, độ chính xác và nhất quán mong muốn; không tự quét bảng lớn mỗi khi người dùng mở danh sách.

### 3.1. LIMIT khác page size

~~~sql
-- Giới hạn tổng kết quả của câu query ở mức 20 hàng.
SELECT * FROM events_by_device_day
WHERE tenant_id = ? AND device_id = ? AND event_day = ?
LIMIT 20;
~~~

`LIMIT 20` thể hiện **giới hạn tổng hàng** của kết quả truy vấn. Trong khi đó `CassandraPageRequest.first(20)` cho biết ứng dụng **muốn lấy một trang tối đa 20 hàng** và còn khả năng tiếp tục ở trang sau. Không được mặc định rằng `LIMIT 20` cộng với paging 20 sẽ cho trang 2, trang 3 của *toàn bộ lịch sử*; nếu mục tiêu là duyệt hết dữ liệu thì thường **không gắn LIMIT 20 cố định** vào câu CQL.

Cũng phải phân biệt với `BoundStatement.setPageSize(20)` ở Java Driver: giá trị này điều chỉnh số hàng của **mỗi lượt fetch**, không nhất thiết giới hạn số hàng driver có thể trả khi ứng dụng tiếp tục duyệt `ResultSet`.

## 4. Entity mapping và composite primary key

Để dùng repository, ánh xạ bảng CQL vào một entity Java. Trước hết là lớp khóa:

~~~java
package example.telemetry;

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

    @PrimaryKeyColumn(name = "occurred_at", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(name = "event_id", ordinal = 4,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.ASCENDING)
    private UUID eventId;

    public DeviceEventKey() {
    }

    public DeviceEventKey(
            UUID tenantId, UUID deviceId, LocalDate eventDay,
            Instant occurredAt, UUID eventId) {
        this.tenantId = tenantId;
        this.deviceId = deviceId;
        this.eventDay = eventDay;
        this.occurredAt = occurredAt;
        this.eventId = eventId;
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID value) { tenantId = value; }
    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID value) { deviceId = value; }
    public LocalDate getEventDay() { return eventDay; }
    public void setEventDay(LocalDate value) { eventDay = value; }
    public Instant getOccurredAt() { return occurredAt; }
    public void setOccurredAt(Instant value) { occurredAt = value; }
    public UUID getEventId() { return eventId; }
    public void setEventId(UUID value) { eventId = value; }

    @Override
    public boolean equals(Object candidate) {
        if (this == candidate) return true;
        if (!(candidate instanceof DeviceEventKey)) return false;
        DeviceEventKey other = (DeviceEventKey) candidate;
        return Objects.equals(tenantId, other.tenantId)
                && Objects.equals(deviceId, other.deviceId)
                && Objects.equals(eventDay, other.eventDay)
                && Objects.equals(occurredAt, other.occurredAt)
                && Objects.equals(eventId, other.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(
                tenantId, deviceId, eventDay, occurredAt, eventId);
    }
}
~~~

**Thứ tự `ordinal`:** các thành phần partition key lần lượt 0, 1, 2; hai clustering columns lần lượt 3, 4. Đây là vị trí trên **toàn bộ khóa**. `PrimaryKeyType` được import từ `core.cql`, còn `@PrimaryKeyColumn` nằm trong `core.mapping`.

Entity:

~~~java
package example.telemetry;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_device_day")
public class DeviceEvent {

    @PrimaryKey
    private DeviceEventKey key;

    @Column("event_type")
    private String eventType;

    @Column("description")
    private String description;

    public DeviceEvent() {
    }

    public DeviceEvent(
            DeviceEventKey key, String eventType, String description) {
        this.key = key;
        this.eventType = eventType;
        this.description = description;
    }

    public DeviceEventKey getKey() { return key; }
    public void setKey(DeviceEventKey value) { key = value; }
    public String getEventType() { return eventType; }
    public void setEventType(String value) { eventType = value; }
    public String getDescription() { return description; }
    public void setDescription(String value) { description = value; }
}
~~~

`Instant` ↔ CQL `timestamp` có độ chính xác mili giây, nên khi tạo `occurredAt` phải chuẩn hóa/kiểm tra giá trị thời gian theo hợp đồng nghiệp vụ. Nếu cùng sự kiện được retry, giữ nguyên `eventId` và `occurredAt` để không sinh thêm hàng.

`@Table` chỉ mô tả mapping. Trước khi chạy ví dụ, keyspace và bảng cần tồn tại; production nên quản lý schema bằng migration CQL, không mặc định `schema-action` tự tạo/sửa primary key.

## 5. Repository: lấy trang đầu bằng CassandraPageRequest.first

Một repository rõ ràng dùng `@Query` để khóa chặt ba thành phần partition key:

~~~java
package example.telemetry;

import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {

    @Query("SELECT * FROM events_by_device_day " +
           "WHERE tenant_id = ?0 AND device_id = ?1 AND event_day = ?2")
    Slice<DeviceEvent> findInDay(
            UUID tenantId, UUID deviceId,
            LocalDate eventDay, Pageable pageable);
}
~~~

Trong service đã inject `DeviceEventRepository repository`:

~~~java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.domain.Slice;

public Slice<DeviceEvent> firstPage(
        UUID tenantId, UUID deviceId, LocalDate day) {

    return repository.findInDay(
            tenantId, deviceId, day,
            CassandraPageRequest.first(20));
}
~~~

`CassandraPageRequest.first(20)` là cách **khởi tạo lượt đọc đầu tiên** với kích thước trang 20. Trong Cassandra, nó khác với `PageRequest.of(0, 20)` từ một ví dụ SQL truyền thống: lớp Cassandra-specific hỗ trợ gắn paging state cho các trang sau.

`Slice<DeviceEvent>` cho biết:

- `slice.getContent()`: các entity trong trang hiện tại.
- `slice.getNumberOfElements()`: số phần tử thực tế của trang đó.
- `slice.hasContent()`: có phần tử hay không.
- `slice.hasNext()`: Spring Data có thông tin cho phép lấy tiếp hay không.
- `slice.nextPageable()`: `Pageable` chứa trạng thái cần thiết để **yêu cầu trang tiếp theo**.

Nội dung `Slice` được ánh xạ từ CQL qua entity mapping; nó **không** tự quyết định user được phép đọc tenant nào. Tầng API phải xác nhận `tenantId` từ ngữ cảnh xác thực và quyền truy cập `deviceId` trước khi gọi repository.

## 6. Trang tiếp theo: sử dụng đúng slice.nextPageable()

Sau khi có trang đầu, tiếp tục bằng `nextPageable()` của **chính slice đã nhận**:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.cassandra.core.query.CassandraPageRequest;

Slice<DeviceEvent> first = repository.findInDay(
        tenantId, deviceId, day, CassandraPageRequest.first(20));

// Dùng first.getContent() để trả trang đầu cho API.
List<DeviceEvent> firstRows = first.getContent();

if (first.hasNext()) {
    Pageable continuation = first.nextPageable();

    Slice<DeviceEvent> second = repository.findInDay(
            tenantId, deviceId, day, continuation);

    // second.getContent(): dữ liệu của trang tiếp theo.
}
~~~

Chú ý **ba chi tiết không được sai**:

1. **Giữ nguyên query và bind values**: `tenantId`, `deviceId`, `day` phải như trang trước. Một cursor của thiết bị A không được đem dùng cho thiết bị B.
2. **Dùng `first.nextPageable()`, không tạo lại `CassandraPageRequest.first(20)`**. Tạo lại `first(...)` sẽ bắt đầu đọc từ đầu, nên ứng dụng có thể lặp lại trang 1.
3. **Kiểm tra `hasNext()` trước**. Khi không còn trang, không gửi tiếp `nextPageable()` như một request mới; trong các phiên bản Spring Data, trạng thái “không có trang tiếp” có thể được biểu diễn bằng một `Pageable` không dành cho continuation.

### 6.1. Lấy tối đa ba trang để minh họa luồng

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Pageable;
import org.springframework.data.cassandra.core.query.CassandraPageRequest;

List<DeviceEvent> collected = new ArrayList<>();
Pageable request = CassandraPageRequest.first(20);

for (int pageIndex = 0; pageIndex < 3; pageIndex++) {
    Slice<DeviceEvent> slice =
            repository.findInDay(tenantId, deviceId, day, request);

    collected.addAll(slice.getContent());

    if (!slice.hasNext()) {
        break;
    }

    request = slice.nextPageable();
}
~~~

Đoạn code có **giới hạn ba trang** để tránh tải không kiểm soát. Trong API bình thường, không nên nối tất cả các trang thành một response vô hạn: chỉ trả một trang và cursor cho lần gọi sau. `CassandraPageRequest` được dùng để bắt đầu và các trang tiếp theo dùng `nextPageable()`.

### 6.2. Khi trang đầu rỗng

Nếu không có bản ghi cho `tenantId/deviceId/day`, `getContent()` là danh sách rỗng và thông thường `hasNext()` là `false`. Đây không phải lỗi CQL. Phân biệt:

- **Không có dữ liệu:** trả một trang rỗng, không có cursor kế tiếp.
- **Không có quyền:** trả lỗi authorization theo contract API.
- **Không tìm thấy bảng/keyspace hoặc sai kết nối:** chẩn đoán schema/session, không coi là “danh sách rỗng”.
- **Timeout:** request chưa có kết quả rõ ràng, cần quyết định retry theo idempotency và SLA.

## 7. Lấy trang bằng CassandraTemplate khi cần Query/Criteria

Ngoài repository, Spring Data Cassandra cung cấp `CassandraOperations.slice(Query, Class<T>)`. API này thích hợp khi service cần dựng điều kiện từ những input đã được kiểm soát.

~~~java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public class DeviceEventQueryService {
    private final CassandraOperations operations;

    public DeviceEventQueryService(CassandraOperations operations) {
        this.operations = operations;
    }

    public Slice<DeviceEvent> readPage(
            UUID tenantId, UUID deviceId, LocalDate day,
            Pageable pageable) {

        Query base = Query.query(
                Criteria.where("tenant_id").is(tenantId))
                .and(Criteria.where("device_id").is(deviceId))
                .and(Criteria.where("event_day").is(day));

        Query paged = base.pageRequest(pageable);
        return operations.slice(paged, DeviceEvent.class);
    }
}
~~~

Trang đầu và trang sau:

~~~java
Slice<DeviceEvent> first = service.readPage(
        tenantId, deviceId, day,
        CassandraPageRequest.first(20));

if (first.hasNext()) {
    Slice<DeviceEvent> second = service.readPage(
            tenantId, deviceId, day, first.nextPageable());
}
~~~

**Chi tiết API dễ bỏ sót:** trong các phiên bản Spring Data Cassandra hiện đại, `Query.pageRequest(pageable)` **trả về một đối tượng `Query` mới**. Vì vậy phải giữ giá trị trả về:

~~~java
// Đúng: nhận Query đã được gắn page request.
Query paged = base.pageRequest(pageable);

// Sai về ý định: bỏ qua kết quả được trả về.
base.pageRequest(pageable);
return operations.slice(base, DeviceEvent.class);
~~~

Nếu cần điều kiện khoảng thời gian theo `occurred_at`, chỉ thêm khi **đã có đầy đủ partition key** và theo quy tắc clustering của bảng. Thay đổi filter giữa các trang nghĩa là **một câu truy vấn khác**, không được giữ cursor cũ.

`CassandraOperations.slice(Statement<?>, Entity.class)` cũng tồn tại cho trường hợp ứng dụng đã tạo statement bằng driver. Khi dùng `BoundStatement`, cần đảm bảo các tùy chọn `pageSize` và paging state đã được thiết lập đúng; không nhầm `select(...)` trả `List` với `slice(...)` trả `Slice`.

## 8. Kết hợp projection với phân trang

**Projection** nghĩa là trả về **một phần thuộc tính** của entity thay vì cả đối tượng lớn. Chẳng hạn trang danh sách sự kiện chỉ cần thời điểm, loại sự kiện và ID; mô tả dài chỉ lấy khi người dùng mở chi tiết.

Spring Data hỗ trợ **interface-based projection**:

~~~java
package example.telemetry;

public interface DeviceEventPreview {

    DeviceEventKey getKey();

    String getEventType();
}
~~~

Projection này đưa ra hai thuộc tính `key` và `eventType` vốn tồn tại trong entity `DeviceEvent`. Nó là **closed projection** nếu tất cả accessor đều khớp với property đã ánh xạ; Spring Data có thể tối ưu việc lấy dữ liệu cần thiết, nhưng mức tối ưu CQL cụ thể phải được kiểm chứng theo phiên bản framework.

Trong cùng repository, có thể định nghĩa một phương thức khác:

~~~java
@Query("SELECT tenant_id, device_id, event_day, " +
       "occurred_at, event_id, event_type " +
       "FROM events_by_device_day " +
       "WHERE tenant_id = ?0 AND device_id = ?1 AND event_day = ?2")
Slice<DeviceEventPreview> findPreviewsInDay(
        UUID tenantId, UUID deviceId,
        LocalDate day, Pageable pageable);
~~~

Đoạn code là **phương thức cần đặt bên trong `DeviceEventRepository`**. CQL chủ động chọn đủ năm cột khóa để ánh xạ `DeviceEventKey`, cùng cột `event_type`; nó không đọc `description` cho màn hình danh sách. Một số cách ánh xạ projection lồng nhau có chi tiết khác giữa các phiên bản Spring Data; cần có **integration test** xác minh giá trị `getKey()` và `getEventType()` trước khi dùng production.

Luồng tiếp tục **không đổi**:

~~~java
Slice<DeviceEventPreview> first =
        repository.findPreviewsInDay(
                tenantId, deviceId, day,
                CassandraPageRequest.first(20));

if (first.hasNext()) {
    Slice<DeviceEventPreview> second =
            repository.findPreviewsInDay(
                    tenantId, deviceId, day,
                    first.nextPageable());
}
~~~

Projection **không tự giảm số partition được truy vấn**: nó chỉ giới hạn dữ liệu cần ánh xạ/truyền về ở trường hợp framework và query hỗ trợ. Truy vấn vẫn phải có đủ partition key. Nếu muốn tìm toàn bộ các sự kiện có `event_type = 'ERROR'` trên nhiều thiết bị, việc chỉ thêm accessor `getEventType()` không tạo ra đường đọc theo `event_type`; cần access table hoặc index phù hợp.

### 8.1. Closed projection, open projection và DTO

| Cách trả về | Mô tả | Điểm cần cân nhắc |
|---|---|---|
| Closed interface projection | Getter khớp property entity | Có khả năng tối ưu trường được đọc |
| Open projection dùng SpEL | Getter tính từ đối tượng `target` | Có thể cần materialize toàn entity, tối ưu kém hơn |
| DTO/record projection | Kiểu chứa đúng dữ liệu API cần | Constructor và tên tham số phải phù hợp quy tắc mapping |
| Entity đầy đủ | Toàn bộ `DeviceEvent` | Đơn giản nhưng có thể đọc payload không cần thiết |

**Không dùng projection để thay cho mô hình dữ liệu Cassandra.** Nó giúp giảm bề rộng dữ liệu và ràng buộc contract API, nhưng không sửa query thiếu partition key, không tự thêm paging state và không mang lại thứ tự toàn cục trên nhiều partition.

## 9. Khi nào kết thúc? hasNext và nextPageable

`Slice.hasNext()` là tín hiệu mà Spring Data cung cấp cho việc có thể lấy một slice tiếp theo. Hãy dựa vào metadata đó, thay vì đoán từ `getNumberOfElements() == pageSize`.

Ví dụ:

| Tình huống | `getNumberOfElements()` | Hướng xử lý |
|---|---:|---|
| Một partition có 0 hàng | 0 | Trả content rỗng; không cố lấy tiếp nếu `hasNext=false` |
| Trang đầu trong 47 hàng, page size 20 | Thường 20 | Nếu `hasNext=true`, dùng `nextPageable` |
| Trang 2 trong 47 hàng | Thường 20 | Nếu `hasNext=true`, dùng cursor mới |
| Trang cuối trong 47 hàng | Thường 7 | Không phát cursor nếu `hasNext=false` |
| Tổng số hàng vừa đúng bội số page size | Có thể là 20 | **Không suy luận** chỉ từ số hàng; kiểm tra `hasNext` |

Ví dụ 47 hàng và page size 20 chỉ để hình dung luồng; dữ liệu có thể thay đổi giữa các lượt gọi. Đừng khẳng định mỗi trang sẽ luôn đủ 20 hàng trên mọi truy vấn/configuration nếu có các yếu tố lọc, giới hạn, TTL hoặc biến động dữ liệu.

### 9.1. Tránh vòng lặp không giới hạn

Ứng dụng batch có thể muốn duyệt tất cả các trang, nhưng cần giới hạn tài nguyên:

~~~java
Pageable request = CassandraPageRequest.first(100);
int fetchedPages = 0;
int maxPages = 50;

while (fetchedPages < maxPages) {
    Slice<DeviceEvent> slice =
            repository.findInDay(tenantId, deviceId, day, request);

    processPage(slice.getContent());
    fetchedPages++;

    if (!slice.hasNext()) {
        break;
    }

    request = slice.nextPageable();
}
~~~

`processPage(...)` là phương thức của tác vụ batch cần triển khai (ví dụ ghi ra hệ lưu trữ khác). Batch phải có cơ chế checkpoint, retry idempotent, giới hạn memory và xử lý lỗi. Không mặc định một paging state có thể được lưu vô thời hạn hoặc dùng cho một schema/query đã thay đổi.

## 10. Thiết kế HTTP API với cursor

`nextPageable()` là một đối tượng **Java trong ứng dụng**, không phải dữ liệu JSON nên gửi nguyên trạng ra browser. Một API có thể trình bày:

~~~json
{
  "items": [
    {
      "eventId": "9d71c42f-2e41-4f04-a0b7-768a2bb7fa11",
      "occurredAt": "2026-11-25T09:10:00Z",
      "eventType": "SCAN"
    }
  ],
  "nextCursor": "opaque-signed-token",
  "hasNext": true
}
~~~

`nextCursor` ở đây là **giá trị minh họa**, không phải cấu trúc token thật. Ở request tiếp theo:

~~~text
GET /tenants/{tenantId}/devices/{deviceId}/events
    ?day=2026-11-25
    &pageSize=20
    &cursor=<opaque-next-cursor>
~~~

Service giải mã và **xác minh** cursor, sau đó xây `Pageable` tiếp tục hợp lệ cho Spring Data Cassandra (hoặc dùng API paging trực tiếp của driver). Các phiên bản Spring Data có `CassandraPageRequest.getPagingState()` và factory `CassandraPageRequest.of(Pageable, ByteBuffer)`; đây là những API ở tầng Java phục vụ việc mang paging state, **không phải định dạng giao thức HTTP** được cung cấp sẵn.

### 10.1. Token cursor phải ràng buộc với câu truy vấn

Những thông tin tối thiểu cần gắn logic với cursor:

| Trường logic | Lý do |
|---|---|
| Phiên bản cursor | Có cách nhận biết cấu trúc khi nâng cấp hệ thống |
| Danh tính/ủy quyền tenant | Không cho dùng token của tenant A để đọc tenant B |
| Đường truy vấn / query fingerprint | Tránh tái dùng state với CQL khác |
| `deviceId`, `eventDay` và filter | Đảm bảo bind values không thay đổi |
| Page size và sort policy | Tránh áp cursor vào giới hạn/thứ tự khác |
| Raw paging state opaque | Dữ liệu do Cassandra Driver dùng để tiếp tục |
| Hạn sử dụng | Giới hạn vòng đời cursor và khả năng tái sử dụng |

Với token stateless, dùng **chữ ký xác thực** chống chỉnh sửa; mã hóa nếu cần bảo mật dữ liệu trong token. Cần bảo vệ cookie/header, ghi log đã che token, giới hạn kích thước đầu vào và kiểm tra quyền **ở mọi request**, không chỉ trang đầu. Nếu chọn stateful cursor, lưu paging state ở server và phát cho client một ID ngẫu nhiên gắn với người dùng, query và thời hạn.

**Không tự chế thuật toán paging state**. Đó là trạng thái opaque thuộc giao thức/driver. Không sửa bytes, không đổi Base64 bằng các phép cắt nối không có kiểm tra và không suy diễn nội dung token thành vị trí hàng theo timestamp.

### 10.2. Tránh giả định cursor tồn tại mãi

Schema thay đổi, prepared statement thay đổi, cluster upgrade hoặc phiên bản driver khác có thể khiến cursor cũ không còn phù hợp. Một API nên:

- Có **thời hạn hợp lý** cho cursor.
- Trả lỗi client rõ ràng khi token sai/hết hạn/không khớp filter.
- Có đường **khởi động lại từ trang đầu** khi cursor không dùng được.
- Khi cần resume lâu dài qua triển khai/đổi schema, thiết kế **checkpoint nghiệp vụ** dựa trên khóa và chính sách sắp xếp, thay vì dựa hoàn toàn vào paging state của driver.

## 11. Dữ liệu thay đổi khi đang phân trang: không phải snapshot

Paging state hỗ trợ tiếp tục tiến độ đọc, nhưng **không tự bảo đảm một snapshot bất biến của toàn bộ dữ liệu** qua nhiều HTTP requests. Trong lúc người dùng đang xem trang 1, writer khác có thể:

- Ghi một event mới có `occurred_at` đứng trước các event đã đọc.
- Ghi event đến muộn có timestamp xen giữa hai trang.
- Xóa hàng/cho TTL hết hạn, để lại tombstone.
- Sửa dữ liệu ở bảng projection đang được đọc.

Tùy cách thay đổi và vị trí cursor, kết quả khi tiếp tục có thể không còn tương đương một snapshot tại đúng thời điểm của trang đầu. Không hứa **exactly once** hay tổng số hàng bất biến chỉ nhờ `Slice.nextPageable()`.

### 11.1. Khi cần độ ổn định cao hơn

Có thể cân nhắc ràng buộc một **upper bound** của clustering key khi bắt đầu duyệt lịch sử, ví dụ `occurred_at < fixedCutoff`, đồng thời giữ `fixedCutoff` giống nhau ở tất cả các trang. Nhưng:

- Upper bound **không khóa dữ liệu**: các ghi đến muộn trong khoảng trước cutoff vẫn có thể xuất hiện.
- Nếu nhiều event cùng timestamp, `event_id` là clustering column phá hòa; cần một hợp đồng thứ tự rõ ràng.
- Nếu yêu cầu đối soát chính xác, có thể phải dùng pipeline dữ liệu có checkpoint, event ID và logic khử trùng ở tầng nghiệp vụ.

Đối với màn hình “Xem thêm” thông thường, chấp nhận kết quả cập nhật theo thời điểm đọc có thể hợp lý. Đối với xuất dữ liệu tài chính hoặc báo cáo chính thức, cần xác định rõ **mức nhất quán nghiệp vụ** và cách tạo một tập dữ liệu ổn định.

## 12. Sort, filter, consistency và nhiều partition

### 12.1. Không đổi sort giữa hai trang

Spring Data có overload `CassandraPageRequest.first(size, Sort)`, nhưng Cassandra **không hỗ trợ sắp xếp tùy ý** theo cột thường. Với bảng minh họa, clustering order đã là `occurred_at DESC, event_id ASC`. Đừng truyền `Sort.by("eventType")` và mong framework tự sắp xếp mọi event theo loại.

Nếu API có một kiểu sort mới cần hiệu năng tốt, hãy cân nhắc một **bảng đọc khác** với clustering phù hợp và partition key được thiết kế theo nhu cầu. Khi sort policy thay đổi, paging state của truy vấn cũ không còn dùng được.

### 12.2. Không đổi filter giữa hai trang

Trang 1:

~~~sql
SELECT * FROM events_by_device_day
WHERE tenant_id=? AND device_id=? AND event_day=?;
~~~

Trang 2 mà thêm `event_type = 'ERROR'` là **truy vấn khác**, chưa kể `event_type` không nằm trong primary key và có thể bị Cassandra từ chối khi không có index phù hợp. Cần bắt đầu một phiên phân trang mới, và nếu lọc theo type là yêu cầu thường xuyên thì thiết kế access table như `events_by_device_type_day` với partition key theo type/day.

### 12.3. Consistency level không chữa lỗi cursor

`LOCAL_ONE` và `LOCAL_QUORUM` mô tả yêu cầu phản hồi replica dựa trên replication của keyspace. Chúng **không** biến paging state thành snapshot, không làm `WHERE` thiếu partition key hợp lệ và không bảo đảm các bảng denormalized được cập nhật nguyên tử.

Consistency, request timeout, retry và execution profile của driver cần được chọn cho SLA của truy vấn. Nếu timeout xuất hiện sau một trang, không tự tăng timeout vô hạn hoặc retry mù với một paging state mới tạo ngẫu nhiên. Hãy phân biệt:

1. Lỗi transport/cluster và số replica khả dụng.
2. Truy vấn quá lớn, hot partition hoặc tombstone scan.
3. Paging state không khớp câu query/bind values.
4. Dữ liệu hoặc schema đã đổi giữa các lần thực thi.

### 12.4. Khi màn hình cần dữ liệu qua nhiều ngày

Vì `event_day` là một phần partition key, `day=2026-11-25` và `day=2026-11-24` là **hai partition khác nhau**. Một `slice.nextPageable()` từ ngày 25 không thể dùng cho ngày 24.

Để hiển thị lịch sử nhiều ngày, hệ thống phải điều phối nhiều truy vấn và có logic hợp nhất:

~~~text
Partition device-1 / day 25 --> cursor A
Partition device-1 / day 24 --> cursor B
Partition device-1 / day 23 --> cursor C
             |
             v
Ứng dụng ghép theo chính sách thời gian,
giới hạn tổng số hàng và lưu cursor riêng từng luồng.
~~~

Đọc nhiều partition làm tăng số request và độ phức tạp. Nếu nhu cầu “30 sự kiện mới nhất bất kể ngày” rất thường xuyên, cân nhắc một bảng truy cập hoặc bucket phù hợp, với ranh giới kích thước và chi phí ghi được tính toán trước.

## 13. Kiểm thử first → nextPageable bằng Cassandra thật

Unit test mock repository có thể kiểm tra nhánh `hasNext()`, nhưng **không xác minh** Spring Data tạo paging state đúng hay Cassandra đọc đúng khóa. Cần integration test trên Cassandra test instance/CI với keyspace và bảng đã provision, không thử trên production.

### 13.1. Fixture: nhiều hàng, nhiều partition

Tạo tối thiểu 25 event trong partition mục tiêu và một vài event ở partition khác:

~~~text
Tenant T1, device D1, day 2026-11-25: 25 event
Tenant T1, device D1, day 2026-11-24:  3 event
Tenant T1, device D2, day 2026-11-25:  2 event
Tenant T2, device D1, day 2026-11-25:  2 event
~~~

Kết quả kỳ vọng khi page size = 10: trang đầu có 10 hàng, trang hai có 10 hàng và trang ba có 5 hàng (với fixture ổn định và không có mutation cạnh tranh). Không một event của tenant/device/day khác được lọt vào.

### 13.2. Ví dụ integration test

~~~java
package example.telemetry;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.time.LocalDate;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.domain.Slice;

@SpringBootTest
class DeviceEventPaginationIntegrationTest {

    @Autowired DeviceEventRepository repository;

    @Test
    void readsFirstSecondAndLastSlicesWithoutMixingPartitions() {
        UUID tenant = UUID.randomUUID();
        UUID device = UUID.randomUUID();
        LocalDate day = LocalDate.of(2026, 11, 25);
        Instant origin = Instant.parse("2026-11-25T00:00:00Z");

        // Dùng UUID ngẫu nhiên cho fixture riêng; thời điểm theo giây,
        // nên tương thích độ chính xác timestamp mili giây.
        for (int i = 0; i < 25; i++) {
            DeviceEventKey key = new DeviceEventKey(
                    tenant, device, day,
                    origin.plusSeconds(i), UUID.randomUUID());
            repository.save(new DeviceEvent(key, "SCAN", "event-" + i));
        }

        Slice<DeviceEvent> first = repository.findInDay(
                tenant, device, day, CassandraPageRequest.first(10));
        assertEquals(10, first.getNumberOfElements());
        assertTrue(first.hasNext());

        Slice<DeviceEvent> second = repository.findInDay(
                tenant, device, day, first.nextPageable());
        assertEquals(10, second.getNumberOfElements());
        assertTrue(second.hasNext());

        Slice<DeviceEvent> last = repository.findInDay(
                tenant, device, day, second.nextPageable());
        assertEquals(5, last.getNumberOfElements());
        assertFalse(last.hasNext());

        Set<UUID> ids = new HashSet<>();
        for (DeviceEvent item : first.getContent()) {
            assertTrue(ids.add(item.getKey().getEventId()));
            assertEquals(tenant, item.getKey().getTenantId());
            assertEquals(device, item.getKey().getDeviceId());
            assertEquals(day, item.getKey().getEventDay());
        }
        for (DeviceEvent item : second.getContent()) {
            assertTrue(ids.add(item.getKey().getEventId()));
        }
        for (DeviceEvent item : last.getContent()) {
            assertTrue(ids.add(item.getKey().getEventId()));
        }
        assertEquals(25, ids.size());
    }
}
~~~

Đây là **mẫu test để chạy khi dự án có Cassandra thật** và các dependency Spring Boot Test/Spring Data phù hợp. Trong phạm vi viết bài STEP 4, chưa chạy bộ test. Fixture nên được tạo/dọn có kiểm soát và test nên dùng consistency nhất quán; nếu hạ tầng bất ổn, phải phân biệt lỗi môi trường với lỗi paging.

### 13.3. Những test cần bổ sung

| Test | Mục tiêu |
|---|---|
| Query trả 0 hàng | `hasNext=false`, không phát cursor |
| Query có ít hơn page size | Một trang duy nhất |
| Query có đúng bội số page size | Không suy luận số trang từ độ dài `List` |
| Query có 25 hàng, size 10 | 10 → 10 → 5, không trùng/mất ID trên fixture ổn định |
| Tenant/device/day khác | Không dùng lại cursor hoặc lẫn dữ liệu |
| Thay page size/sort/filter giữa các trang | Hệ API từ chối cursor không khớp |
| Insert hoặc TTL hết hạn giữa các trang | Định nghĩa rõ giới hạn snapshot, không hứa kết quả bất biến |
| Projection `findPreviewsInDay` | Đọc đúng `getKey()`, `getEventType()`, không thiếu trường |
| Hot/large partition | Đo p95/p99, payload, tombstones và số fetch |
| Cursor không hợp lệ, hết hạn | Trả lỗi rõ ràng, không rò rỉ dữ liệu |

## 14. Lỗi thường gặp và cách xử lý

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Dùng `PageRequest.of(10, 20)` | Tưởng có thể nhảy thẳng sang trang 11 | Bắt đầu bằng `CassandraPageRequest.first` và đi tiếp bằng `nextPageable` |
| Lần nào cũng gọi `first(20)` | Trả lặp trang đầu | Giữ `Slice` hiện tại, dùng `slice.nextPageable()` |
| Gọi `nextPageable` khi `hasNext=false` | Không có continuation hợp lệ | Kiểm tra `hasNext()` trước |
| Đổi `tenantId`, `day` hoặc CQL giữa các lượt | Cursor không tương thích hoặc nguy cơ đọc nhầm | Ràng buộc token với query và xác thực tenant |
| Dùng `LIMIT 20` cố định cho toàn bộ danh sách | Không thể duyệt hết lịch sử như mong muốn | Phân biệt tổng giới hạn với page size |
| Dùng `select(...)` tải toàn bộ rồi `subList` | Tốn memory/network, không paging tại Cassandra | Dùng `Slice` hoặc `operations.slice` |
| Gọi `Query.pageRequest(...)` nhưng bỏ giá trị trả về | Query gốc không có state mong muốn | Gán lại `Query paged = base.pageRequest(pageable)` |
| Dùng `Sort.by("eventType")` | Không phù hợp clustering order | Thiết kế lại access pattern/bảng hoặc giới hạn sort |
| Cho rằng `Page<T>` luôn rẻ | Tổng số hàng có thể đòi hỏi đếm đắt đỏ | Dùng `Slice<T>` cho “Xem thêm” |
| Gửi raw `Pageable` qua JSON | Lộ chi tiết framework và cursor khó kiểm soát | Phát opaque cursor được xác thực, có expiry |
| Tin paging state là snapshot | Có thể thấy biến động khi dữ liệu thay đổi | Nêu rõ contract, dùng cutoff/checkpoint nếu cần |
| Chỉ giảm page size để chữa hot partition | Độ trễ vẫn cao | Chỉnh partition/bucket, giới hạn tải, đo cluster |
| Dùng cùng cursor cho nhiều partition | Kết quả sai hoặc bị từ chối | Mỗi truy vấn/partition có tiến độ riêng |
| Dựa vào `hasNext` để suy tổng số trang | Không có total count | Dùng thống kê riêng nếu thật sự cần |

## 15. Bài tập thực hành

Hệ thống giao nhận lưu các lần quét kiện hàng:

~~~sql
CREATE TABLE scans_by_package_day (
    package_id uuid,
    scan_day date,
    scanned_at timestamp,
    scan_id uuid,
    hub_id uuid,
    result text,
    PRIMARY KEY ((package_id, scan_day), scanned_at, scan_id)
) WITH CLUSTERING ORDER BY (scanned_at DESC, scan_id ASC);
~~~

API:

~~~text
GET /packages/{packageId}/scans?day=2026-11-25&pageSize=15

Lần đầu: trả 15 lần quét mới nhất.
Lần sau: nhận nextCursor và trả 15 lần quét tiếp theo.
~~~

**Bài tập A — xây repository**

Tạo `PackageScanKey` với `package_id`, `scan_day` là `PARTITIONED`; `scanned_at`, `scan_id` là `CLUSTERED`, đúng ordinal 0–3. Tạo `PackageScan` có field `key`. Khai báo:

~~~java
@Query("SELECT * FROM scans_by_package_day " +
       "WHERE package_id = ?0 AND scan_day = ?1")
Slice<PackageScan> findScans(
        UUID packageId, LocalDate day, Pageable pageable);
~~~

**Bài tập B — trang đầu và trang kế tiếp**

~~~java
Slice<PackageScan> first = repository.findScans(
        packageId, day, CassandraPageRequest.first(15));

if (first.hasNext()) {
    Slice<PackageScan> second = repository.findScans(
            packageId, day, first.nextPageable());
}
~~~

Giải thích vì sao **không** gọi lại `first(15)` ở lượt hai; xác định tình huống nên trả `nextCursor=null` cho client.

**Bài tập C — projection**

Màn hình chỉ cần `scanned_at`, `scan_id`, `result`. Đề xuất interface projection/DTO phù hợp, viết CQL chọn đủ các cột khóa cần ánh xạ và kiểm tra rằng trang tiếp theo vẫn có đúng thứ tự.

**Bài tập D — câu hỏi thiết kế**

Nếu client muốn:

~~~text
GET /hubs/{hubId}/scans?day=2026-11-25
~~~

thì bảng `scans_by_package_day` **không** có partition key theo hub. `Slice`, page size hay `nextPageable` không sửa đường truy vấn đó. Thiết kế `scans_by_hub_day` với partition key theo hub/day, đánh giá hot partition ở các hub nhiều lưu lượng và chính sách đồng bộ projection.

### Câu hỏi tự kiểm tra

1. Vì sao `CassandraPageRequest.first(20)` không giống `PageRequest.of(10, 20)`?
2. `Slice<T>` cung cấp gì mà `List<T>` không cung cấp?
3. Khi nào được gọi `slice.nextPageable()`?
4. Vì sao trang 2 phải giữ nguyên `tenant_id, device_id, event_day`?
5. Page size 20 khác `LIMIT 20` thế nào?
6. `Query.pageRequest(pageable)` có thể bỏ qua giá trị trả về không?
7. Projection interface có tự cho phép `WHERE event_type=?` trên bảng không có index không?
8. Vì sao paging state không phải snapshot bất biến?
9. Một cursor có được gửi nguyên trạng dưới dạng Java `Pageable` cho frontend không?
10. Nếu dữ liệu nằm trong nhiều day buckets, một paging state có đủ để duyệt tất cả không?

**Đáp án tóm tắt:** (1) Cassandra dùng paging state tiến một chiều; (2) metadata `hasNext/nextPageable`; (3) sau khi `hasNext=true`; (4) state gắn với cùng truy vấn/parameters; (5) page size là mức fetch theo trang, LIMIT là giới hạn kết quả; (6) không, phải giữ `Query` mới; (7) không; (8) dữ liệu có thể đổi giữa requests; (9) không, dùng opaque cursor bảo mật; (10) không, cần điều phối nhiều partition/cursor.

## 16. Checklist trước khi triển khai

- [ ] Đường đọc có **đầy đủ partition key**, clustering order phù hợp query contract.
- [ ] Phân biệt chính xác `Slice`, `Page`, `List`, `LIMIT`, page size và paging state.
- [ ] Trang đầu được tạo bằng `CassandraPageRequest.first(pageSize)`.
- [ ] Trang tiếp theo dùng **`slice.nextPageable()` của trang vừa đọc**, không tạo lại `first`.
- [ ] Chỉ đọc tiếp khi `slice.hasNext()` và giữ nguyên filter/bind values.
- [ ] Nếu dùng template, gọi `operations.slice(base.pageRequest(pageable), Entity.class)` và giữ `Query` mới.
- [ ] Projection truy xuất đúng các property cần thiết và đã được kiểm chứng bằng integration test.
- [ ] Không sắp xếp trên cột thường hoặc dùng OFFSET để vượt hạn chế của Cassandra.
- [ ] HTTP cursor là token opaque được xác thực, gắn với tenant/query/page size và có expiry.
- [ ] Khi dữ liệu thay đổi giữa các trang, hợp đồng không hứa snapshot/đúng một lần nếu chưa có cơ chế riêng.
- [ ] Không dùng một cursor cho nhiều partition, ngày hoặc tenant.
- [ ] Có integration test tối thiểu 25 hàng với page size 10, nhiều partition và kiểm tra không trùng.
- [ ] Có test trang rỗng, trang cuối, token lỗi/hết hạn, thay filter và biến động dữ liệu.
- [ ] Đã đo p95/p99, hot partition, tombstones, tải paging và giới hạn đồng thời.
- [ ] Khi yêu cầu đòi hỏi nhiều kiểu lọc/sort, đánh giá access table/index phù hợp, không dựa vào paging để sửa schema.

## Tài liệu tham khảo

- [Spring Data Cassandra — CassandraPageRequest API](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/query/CassandraPageRequest.html).
- [Spring Data Cassandra — Repository Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html).
- [Spring Data Cassandra — Projections](https://docs.spring.io/spring-data/cassandra/reference/repositories/projections.html).
- [Spring Data Cassandra — Query API](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/query/Query.html).
- [Spring Data Cassandra — CassandraOperations API](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/CassandraOperations.html).
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).
