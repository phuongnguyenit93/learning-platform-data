# Điều kiện clustering theo thứ tự khóa đã thiết kế

## Mục tiêu học tập

Trong Spring Data Cassandra, một phương thức repository như `findByDeviceIdAndEventDayAndOccurredAtGreaterThan(...)` trông giống một bộ lọc được sinh tự động từ tên hàm. Tuy nhiên, **tên hàm không thay đổi những quy tắc truy vấn CQL** của Apache Cassandra. Một truy vấn chỉ thực sự phù hợp khi các điều kiện trên **partition key** và **clustering columns** tuân thủ cấu trúc `PRIMARY KEY` đã được thiết kế theo nhu cầu đọc dữ liệu.

Bài học thuộc chương **Truy vấn dẫn xuất** của module `SPRING_DATA_CASSANDRA`. Trọng tâm là **thứ tự của các clustering columns**: vì sao bạn thường phải ràng buộc các cột đứng trước bằng phép bằng trước khi ràng buộc cột đứng sau, giới hạn của điều kiện khoảng, và cách chuyển các quy tắc ấy thành truy vấn dẫn xuất hoặc `@Query`.

Sau bài này, bạn có thể:

- Phân biệt thứ tự **partition key**, **clustering columns** và **regular columns** trong khai báo bảng CQL.
- Đọc thứ tự khóa để xác định những tổ hợp `WHERE` có thể truy vấn hiệu quả trong một partition.
- Hiểu nguyên tắc **tiền tố equality trước, range sau** đối với clustering columns trong các truy vấn CQL thông thường.
- Nhận diện khi tên phương thức dẫn xuất của Spring Data hợp lệ về cú pháp Java nhưng tạo ra truy vấn **không phù hợp với bảng Cassandra**.
- Viết các phương thức repository cho điều kiện bằng và điều kiện thời gian; biết lúc nào nên viết `@Query` rõ ràng.
- Phân biệt thứ tự clustering tại lưu trữ, `ORDER BY`, giới hạn `LIMIT` và paging state; đánh giá hot partition và hiệu năng.

## 1. Từ thiết kế bảng đến điều kiện truy vấn

Apache Cassandra là cơ sở dữ liệu phân tán được tối ưu cho những đường truy cập dữ liệu đã biết trước. Một bảng cần được thiết kế theo **mẫu truy vấn**, thay vì thiết kế bảng như RDBMS rồi hy vọng repository sẽ tự sinh cách quét và lọc bất kỳ.

Khi đọc một schema CQL:

```sql
PRIMARY KEY ((tenant_id, device_id, event_day), occurred_at, event_id)
```

hãy tách thành ba thành phần:

| Nhóm | Cột | Vai trò |
| --- | --- | --- |
| **Partition key tổng hợp** | `tenant_id`, `device_id`, `event_day` | Toàn bộ tổ hợp này xác định partition logic, từ đó driver/Cassandra định tuyến đến replica phù hợp. |
| **Clustering column thứ nhất** | `occurred_at` | Sắp xếp hàng trong partition theo thời gian sự kiện. |
| **Clustering column thứ hai** | `event_id` | Phân biệt các sự kiện có cùng thời điểm và tham gia thứ tự hàng. |
| **Regular columns** | Ví dụ `event_type`, `payload` | Dữ liệu của hàng; không tự cung cấp khả năng định tuyến partition. |

**Toàn bộ partition key** quyết định dữ liệu thuộc partition nào; các clustering columns tạo thứ tự **bên trong partition**, không làm tăng số partition chỉ vì có nhiều giá trị clustering.

Điều kiện `WHERE tenant_id=? AND device_id=? AND event_day=?` đủ để xác định một partition. Trong phạm vi partition ấy, Cassandra có thể tận dụng thứ tự clustering để đọc các hàng phù hợp mà không cần xử lý như một phép tìm kiếm trên regular column của toàn bảng.

## 2. Ví dụ xuyên suốt: sự kiện của thiết bị trong một ngày

Giả sử một hệ thống IoT có yêu cầu:

1. Lấy 50 sự kiện mới nhất của một thiết bị trong ngày cụ thể.
2. Lấy các sự kiện trong khoảng thời gian `[from, to)` của ngày đó.
3. Khi biết đầy đủ khóa, lấy đúng một sự kiện hoặc xác nhận sự kiện có tồn tại.
4. Không bắt ứng dụng quét toàn bộ tenant để tra `event_type` hoặc `event_id`.

Schema minh họa:

```sql
CREATE TABLE events_by_device_day (
    tenant_id uuid,
    device_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Giải nghĩa:

- Partition là tổ hợp `(tenant_id, device_id, event_day)`.
- Mỗi partition chứa sự kiện của **một thiết bị thuộc một tenant trong một ngày**.
- `occurred_at DESC` đặt những sự kiện mới hơn trước trong thứ tự clustering.
- `event_id ASC` tạo thứ tự phụ để phân biệt những sự kiện có cùng `occurred_at`.
- Giá trị `event_day` do ứng dụng tạo từ `occurred_at` theo **quy ước múi giờ nhất quán**, ví dụ UTC; nếu không, sự kiện có thể bị ghi vào bucket ngày ngoài dự tính.

Hình dung dữ liệu trong một partition:

```text
Partition (tenant=T1, device=D7, day=2026-11-25)

occurred_at DESC       event_id ASC       event_type
---------------------------------------------------
10:32:00Z              E1                 HEARTBEAT
10:32:00Z              E2                 TEMPERATURE
10:17:30Z              E3                 TEMPERATURE
09:05:10Z              E4                 ALERT
08:40:00Z              E5                 HEARTBEAT
...
```

Ví dụ trên dùng các mã E1–E5 để dễ đọc; cột `event_id` thật có kiểu `uuid`.

### Truy vấn lấy danh sách mới nhất

```sql
SELECT occurred_at, event_id, event_type, payload
FROM events_by_device_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25'
LIMIT 50;
```

Truy vấn chỉ định đủ partition key. Vì bảng có clustering order sẵn, các hàng trong partition được trả theo thứ tự clustering đã khai báo, khi không có yêu cầu sắp xếp khác. `LIMIT 50` giúp giới hạn số hàng **trả về**, nhưng không thay thế phân tích kích thước partition hoặc tải đọc/ghi.

## 3. Quy tắc thứ tự clustering: equality prefix rồi mới range

Với clustering key gồm hai cột `(occurred_at, event_id)`, một cách suy luận hữu ích cho các truy vấn thông thường là:

> Muốn ràng buộc cột clustering đứng sau, trước hết phải ràng buộc những cột clustering đứng trước bằng điều kiện phù hợp. Một điều kiện khoảng trên cột trước thường là điểm kết thúc của chuỗi điều kiện clustering có thể tận dụng trực tiếp.

Đây là quy tắc thực hành cho những điều kiện bằng/khoảng phổ biến. CQL có thêm các dạng cú pháp như điều kiện tuple hoặc một số biến thể `IN` tùy phiên bản; không nên suy rộng quy tắc đơn giản thành tuyên bố rằng mọi cú pháp khác đều không tồn tại. Trong bài này, hãy hiểu và áp dụng vững mẫu truy vấn chủ đạo trước.

### 3.1. Chỉ định partition, không lọc clustering

```sql
SELECT *
FROM events_by_device_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25';
```

Đây là truy vấn **toàn bộ một partition**. Nó hợp lệ về đường định vị, nhưng có thể trả rất nhiều hàng nếu partition lớn. Với API danh sách, nên có hạn mức và thiết kế paging.

### 3.2. Điều kiện khoảng trên clustering column đầu tiên

Muốn tìm các sự kiện từ 09:00 đến trước 10:00:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_device_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25'
  AND occurred_at >= '2026-11-25T09:00:00Z'
  AND occurred_at < '2026-11-25T10:00:00Z';
```

Điều kiện `occurred_at` dùng so sánh khoảng ngay trên **clustering column đầu tiên**, sau khi partition đã được xác định. Đây là đường truy cập tự nhiên của bảng.

Sử dụng khoảng nửa mở `[from, to)` tránh trùng dữ liệu ở ranh giới khi quét các cửa sổ giờ liên tiếp. Kiểm tra múi giờ và độ chính xác thời gian ở cả Java lẫn Cassandra để đảm bảo hai ranh giới phản ánh đúng nghiệp vụ.

### 3.3. Điều kiện bằng trên cột đầu, tiếp tục tới cột sau

Nếu biết timestamp cụ thể và muốn tìm một sự kiện duy nhất:

```sql
SELECT *
FROM events_by_device_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25'
  AND occurred_at = '2026-11-25T10:32:00Z'
  AND event_id = 33333333-3333-4333-8333-333333333333;
```

Các cột clustering được ràng buộc **theo thứ tự khai báo**: `occurred_at` bằng giá trị cố định, rồi `event_id` bằng giá trị cụ thể. Toàn bộ primary key đã được xác định; kết quả tối đa một hàng CQL.

Nếu muốn lọc một nhóm `event_id` trong cùng `occurred_at`, cần xem cú pháp phù hợp của phiên bản Cassandra đang dùng và mục đích truy vấn. Không mặc định mọi biến thể `IN` đều được dùng giống SQL.

### 3.4. Ràng buộc cột sau khi cột trước đã dùng range

Một câu hỏi thường gặp: “Cho tôi các sự kiện từ 09:00 đến 10:00 **và** `event_id` bằng E2”.

```sql
-- Phản ví dụ cho cách đặt điều kiện clustering đơn giản:
-- SELECT *
-- FROM events_by_device_day
-- WHERE tenant_id = ...
--   AND device_id = ...
--   AND event_day = ...
--   AND occurred_at >= '2026-11-25T09:00:00Z'
--   AND occurred_at <  '2026-11-25T10:00:00Z'
--   AND event_id = ...;
```

`occurred_at` đã là điều kiện khoảng; với kiểu điều kiện trên các cột riêng lẻ, không nên kỳ vọng Cassandra sử dụng tiếp equality trên `event_id` như một phép lọc chỉ mục tổng quát. Nếu đây là truy vấn trọng yếu, xem lại cách định danh/định tuyến dữ liệu hoặc thiết kế bảng khác.

Điều tương tự xảy ra khi **bỏ qua clustering column đầu tiên**:

```sql
-- Thiếu điều kiện trên occurred_at nhưng lại lọc event_id:
-- SELECT * FROM events_by_device_day
-- WHERE tenant_id = ...
--   AND device_id = ...
--   AND event_day = ...
--   AND event_id = ...;
```

Với schema hiện tại, `event_id` không phải khóa định tuyến độc lập. Sự kiện có thể nằm ở nhiều timestamp trong cùng partition; Cassandra không tự tạo một đường tìm trực tiếp theo `event_id` chỉ vì nó nằm trong primary key.

## 4. Bảng quyết định cho thứ tự điều kiện

Giả sử **đã chỉ định đầy đủ** partition key `(tenant_id, device_id, event_day)`.

| Điều kiện clustering | Đánh giá theo mô hình đang học | Giải thích |
| --- | --- | --- |
| Không có | **Phù hợp**, đọc theo partition. | Có thể trả nhiều hàng, cần giới hạn/paging. |
| `occurred_at = ?` | **Phù hợp**. | Equality trên clustering column thứ nhất. |
| `occurred_at >= ?` | **Phù hợp**. | Range trên clustering column thứ nhất. |
| `occurred_at >= ? AND occurred_at < ?` | **Phù hợp**. | Hai đầu của một khoảng trên cùng cột đầu. |
| `occurred_at = ? AND event_id = ?` | **Phù hợp**. | Equality prefix, định danh đủ hàng. |
| `occurred_at = ? AND event_id > ?` | **Có thể phù hợp**. | Equality trên cột đầu, range trên cột tiếp theo. |
| Chỉ có `event_id = ?` | **Không phù hợp với đường đọc này**. | Bỏ qua clustering column đứng trước. |
| `occurred_at > ? AND event_id = ?` | **Không phải mẫu điều kiện cột riêng nên dựa vào**. | Range ở cột trước rồi cố ràng buộc cột sau. |
| Chỉ có `event_type = ?` | **Không phải truy vấn theo primary key của bảng**. | `event_type` là regular column. |

**Điểm quan trọng:** “phù hợp” nghĩa là điều kiện cùng schema biểu đạt được một truy vấn theo khóa trong các trường hợp minh họa. Nó **không** chứng minh mọi partition đều nhỏ, mọi request đều nhanh, hay mọi biểu thức của Spring Data đều chắc chắn được hỗ trợ ở mọi phiên bản.

### Khi có ba hoặc nhiều clustering columns

Nếu primary key là:

```sql
PRIMARY KEY ((tenant_id, device_id, event_day),
             category, occurred_at, event_id)
```

thì `category` đã trở thành **clustering column thứ nhất**:

```text
Clustering order:
  category -> occurred_at -> event_id

Muốn lọc một khoảng occurred_at:
  partition key = đầy đủ
  category = một giá trị cụ thể
  occurred_at >= from
  occurred_at < to

Không thể mặc định bỏ category rồi chỉ tìm theo occurred_at.
```

Thêm `category` ở đầu clustering key có thể hỗ trợ rất tốt truy vấn **theo category + thời gian**, nhưng làm thay đổi đường truy cập **tất cả sự kiện của thiết bị theo thời gian, không phân biệt category**. Đây là đánh đổi thiết kế bảng quan trọng.

## 5. Thứ tự cột trong WHERE có giống thứ tự cột trong PRIMARY KEY không?

Phải phân biệt **thứ tự logic của ràng buộc khóa** với **thứ tự viết biểu thức trong văn bản CQL**.

Hai câu sau biểu đạt cùng tổ hợp equality cho partition key:

```sql
SELECT *
FROM events_by_device_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25';

SELECT *
FROM events_by_device_day
WHERE event_day = '2026-11-25'
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND tenant_id = 11111111-1111-4111-8111-111111111111;
```

Việc đảo thứ tự các toán hạng `AND` không làm thay đổi **thứ tự các thành phần khóa trong schema**. Với điều kiện clustering, điều quan trọng là **có ràng buộc trên cột nào và loại ràng buộc ấy là equality hay range**, chứ không phải câu lệnh `WHERE` phải viết cột từ trái sang phải đúng từng dòng.

Điều này cũng đúng với **tên phương thức repository**: Spring Data phân tích tên thành các phần điều kiện, nhưng tên viết theo một thứ tự khác không thể làm Cassandra quên đi cấu trúc clustering đã tạo. Quy tắc pháp lý cuối cùng được quyết định bởi CQL và schema thực.

## 6. Truy vấn dẫn xuất trong Spring Data Cassandra hoạt động thế nào?

Spring Data cho phép định nghĩa các phương thức repository mà không phải viết tay mọi câu `SELECT`. Framework phân tích **tên phương thức** (*derived query*) để xác định:

- Các thuộc tính Java cần lọc.
- Loại điều kiện như bằng, lớn hơn hoặc nhỏ hơn nếu được phiên bản hỗ trợ.
- Các tham số của phương thức.
- Một số lựa chọn sắp xếp hoặc giới hạn kết quả, tùy tính năng repository của phiên bản.

Ví dụ phong cách tên phương thức:

```java
findByTenantIdAndDeviceIdAndEventDay(...)

findByTenantIdAndDeviceIdAndEventDayAndOccurredAt(...)

findByTenantIdAndDeviceIdAndEventDayAndOccurredAtGreaterThanEqual(...)
```

Tên phương thức không phải một “ngôn ngữ truy vấn độc lập” khỏi Cassandra. Sau bước parse và mapping, hệ thống vẫn phải tạo CQL được Cassandra chấp nhận.

### Cần phân biệt hỗ trợ parse và hỗ trợ CQL

Một từ khóa method name có thể:

1. Được Spring Data Commons nhận diện về cú pháp.
2. Nhưng không được **module Spring Data Cassandra hoặc phiên bản đang dùng** hỗ trợ theo cách cần thiết.
3. Hoặc được framework tạo thành CQL nhưng **Cassandra từ chối** vì schema không hỗ trợ tổ hợp điều kiện đó.

Vì vậy không nên giả định rằng cứ viết `findBy...And...` hay `Between` là Cassandra có thể thực thi như một cơ sở dữ liệu quan hệ. Với điều kiện phức tạp, hãy kiểm tra từ khóa được hỗ trợ và câu CQL dự kiến; viết `@Query` tường minh khi cần.

## 7. Ánh xạ entity và repository theo khóa clustering

Để làm rõ cách tên method khớp property Java, ta dùng entity với các trường khóa được ánh xạ **trực tiếp**. Spring Data Cassandra hỗ trợ annotation `@PrimaryKeyColumn` cho thành phần khóa, cùng ordinal và loại `PARTITIONED`/`CLUSTERED`.

Ví dụ mapping minh họa:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_device_day")
public class DeviceEvent {

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

    @Column("event_type")
    private String eventType;

    @Column("payload")
    private String payload;

    // Constructor, getters/setters và phương thức nhận diện khóa.
}
```

Đây là **khung entity để minh họa thứ tự mapping**; cần bổ sung phần khởi tạo/accessors theo quy ước dự án. Các ordinal phải phản ánh đúng thứ tự cột trong schema CQL. Với lựa chọn flat composite key, Spring Data có kiểu `MapId` giúp biểu diễn ID khi cần thao tác CRUD theo toàn bộ khóa; lựa chọn khác là `@PrimaryKeyClass` với đối tượng khóa riêng.

Ví dụ repository minh họa theo các thuộc tính đặt trực tiếp trên entity:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.MapId;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, MapId> {

    // Đọc theo đúng một partition, có thể rất nhiều hàng nếu thiếu giới hạn.
    List<DeviceEvent> findByTenantIdAndDeviceIdAndEventDay(
            UUID tenantId, UUID deviceId, LocalDate eventDay);

    // Equality trên clustering column đầu tiên.
    List<DeviceEvent> findByTenantIdAndDeviceIdAndEventDayAndOccurredAt(
            UUID tenantId, UUID deviceId, LocalDate eventDay,
            Instant occurredAt);

    // Một ranh giới trên clustering column đầu tiên.
    List<DeviceEvent>
    findByTenantIdAndDeviceIdAndEventDayAndOccurredAtGreaterThanEqual(
            UUID tenantId, UUID deviceId, LocalDate eventDay,
            Instant fromInclusive);
}
```

Các phương thức dùng cú pháp method-name query derivation phổ biến. **Khả năng chấp nhận từ khóa, cách map primary-key columns và kiểu trả về cần được xác minh trên phiên bản Spring Data Cassandra thực tế**; một integration test với schema thật mới chứng minh đường truy cập hoạt động.

### Vì sao hai phương thức có cùng tên thuộc tính nhưng hiệu năng khác nhau?

`findByTenantIdAndDeviceIdAndEventDay(...)` chỉ định partition. Nếu partition chứa 200.000 sự kiện, trả `List` không giới hạn có thể gây chi phí lớn. Phương thức có `OccurredAt` hoặc `OccurredAtGreaterThanEqual` giới hạn vùng clustering, nhưng nếu vùng đó vẫn chứa rất nhiều hàng, cần tiếp tục giới hạn kết quả hoặc phân trang.

**Hợp lệ về khóa** là điều kiện cần, không phải cam kết hiệu năng. Phải xem khối lượng hàng được đọc, page size, tải đồng thời và kích thước partition.

## 8. Đọc một khoảng thời gian: khi nào dùng @Query?

Một API thực tế thường cần **hai ranh giới**:

```text
tenantId + deviceId + eventDay
AND occurredAt >= fromInclusive
AND occurredAt < toExclusive
LIMIT 100
```

Không nên phụ thuộc mù quáng vào việc ghép nhiều hậu tố `GreaterThanEqual`/`LessThan` hoặc giả định `Between` luôn có cùng ngữ nghĩa trong mọi phiên bản Spring Data Cassandra. Khi cần một hợp đồng CQL rõ ràng, dùng `@Query`:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.repository.Query;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, MapId> {

    @Query("""
        SELECT * FROM events_by_device_day
        WHERE tenant_id = ?0
          AND device_id = ?1
          AND event_day = ?2
          AND occurred_at >= ?3
          AND occurred_at < ?4
        LIMIT ?5
        """)
    List<DeviceEvent> findInTimeWindow(
            UUID tenantId,
            UUID deviceId,
            LocalDate eventDay,
            Instant fromInclusive,
            Instant toExclusive,
            int limit);
}
```

Ví dụ trên là **mẫu interface để đặt cạnh các phương thức đã minh họa**, không yêu cầu khai báo hai interface trùng tên trong cùng dự án. Khi ghép vào mã thật, hãy đưa tất cả các phương thức vào **một repository duy nhất** và bổ sung imports còn thiếu từ đoạn trước.

Lợi ích:

- Người đọc thấy ngay điều kiện CQL, gồm **đủ partition key** và **range trên clustering column đầu tiên**.
- Tham số `?0 ... ?5` có ý nghĩa rõ, tránh ghép input vào chuỗi CQL.
- Giới hạn kết quả được đặt tường minh, tránh đọc vô hạn vì tên derived query khó kiểm soát.

Với API công khai, validate `fromInclusive < toExclusive`, `limit` trong phạm vi cho phép, và kiểm tra hai mốc cùng thuộc bucket ngày mà request nhắm đến (nếu đó là hợp đồng nghiệp vụ). Đừng coi một query `LIMIT 100` là đủ để giải quyết yêu cầu paging nhiều trang.

### Khi cần truy vấn trên nhiều ngày

Schema có `event_day` trong partition key. Nếu cửa sổ thời gian kéo từ 23:55 ngày 25 sang 00:05 ngày 26, ứng dụng cần truy vấn **ít nhất hai partition ngày** và hợp nhất kết quả theo đúng yêu cầu:

```text
(tenant=T1, device=D7, day=25) -> truy vấn phần cuối ngày 25
(tenant=T1, device=D7, day=26) -> truy vấn phần đầu ngày 26
                                   |
                                   v
                        hợp nhất ở tầng ứng dụng
```

Không thể bỏ `event_day` khỏi `WHERE` rồi kỳ vọng repository “tự đọc xuyên ngày” chỉ vì `occurred_at` đã có khoảng thời gian.

## 9. ORDER BY: tuân theo thứ tự clustering, không phải Sort tùy ý

Trong schema:

```sql
WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC)
```

Cassandra đã định nghĩa thứ tự vật lý/logical của hàng trong mỗi partition. Một truy vấn có đủ partition key có thể đọc theo thứ tự clustering mặc định mà không cần thêm `ORDER BY`.

Ví dụ tường minh:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_device_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25'
ORDER BY occurred_at DESC, event_id ASC
LIMIT 50;
```

Theo quy tắc CQL, thứ tự sắp xếp qua `ORDER BY` bị ràng buộc bởi **clustering columns** và cách khai báo thứ tự ở schema. Với bảng có hướng sắp xếp trộn `DESC/ASC`, chiều đảo toàn bộ tương ứng cũng có thể được dùng theo các quy tắc của Cassandra; không được chọn tổ hợp chiều bất kỳ cho mỗi cột như trong SQL truyền thống.

### Các hiểu nhầm phổ biến

| Mong muốn | Vấn đề với schema ví dụ |
| --- | --- |
| `ORDER BY event_type` | `event_type` là regular column, không phải clustering column được thiết kế để sắp. |
| `ORDER BY event_id DESC` cho toàn partition | `event_id` đứng sau `occurred_at`; không thể tùy ý đảo/đổi cột dẫn đầu mà không xét thứ tự khóa. |
| Sắp mọi sự kiện của tenant theo thời gian qua các device/day | Các hàng nằm ở **nhiều partition**, không có một thứ tự clustering toàn cục. |
| Thêm `Sort.by("eventType")` vào method repository | Spring Data không biến regular column thành cột clustering hay một index sắp xếp. |

Nếu API cần danh sách “các sự kiện ALERT mới nhất toàn tenant”, bảng `events_by_device_day` không phục vụ trực tiếp được query đó. Cần xây một **bảng theo truy vấn** với partition key và clustering order phù hợp, hoặc một hệ thống tìm kiếm/chỉ mục phù hợp với workload.

### Method-name OrderBy không sửa bảng

Một method như:

```java
// Minh họa ý định, phải kiểm chứng với phiên bản Spring Data đang chạy.
// findByTenantIdAndDeviceIdAndEventDayOrderByOccurredAtDesc(...)
```

có thể trông hợp lý vì `occurred_at` là clustering column đầu tiên theo chiều giảm. Nhưng nếu thay thành `OrderByEventTypeDesc`, query sẽ không trở nên hợp lệ/nhanh chỉ vì cú pháp parser chấp nhận tên đó.

**Hãy đọc `CLUSTERING ORDER BY` trong schema trước khi thiết kế các method `OrderBy...` hoặc tham số `Sort`.**

## 10. IN, filtering và điều kiện regular column

Ngoài equality và range, Cassandra có một số khả năng truy vấn khác, nhưng mỗi loại đi kèm giới hạn:

### 10.1. IN không có nghĩa “truy vấn phân tán không giới hạn”

Một số dạng `IN` được hỗ trợ với điều kiện về thành phần khóa. Nhưng hiệu năng và hỗ trợ cụ thể phụ thuộc vị trí cột, số giá trị, phân vùng liên quan và phiên bản.

Ví dụ yêu cầu “lấy mọi event trong 100 ngày” không nên biến thành một danh sách `IN` rất lớn với kỳ vọng Cassandra xử lý như một lookup duy nhất rẻ tiền. Dù truy vấn cú pháp hợp lệ, fan-out, số partition và chi phí tổng hợp có thể rất lớn.

Trước khi dùng `In` trong tên derived query, hãy xác nhận vị trí cột trong khóa, cú pháp CQL thực tế, giới hạn số phần tử và bài kiểm thử tải.

### 10.2. Regular column không thể tùy tiện đặt trong WHERE

`event_type` và `payload` không nằm trong primary key. Một method:

```java
// Trông giống Spring Data JPA nhưng không tự phù hợp với bảng Cassandra:
// List<DeviceEvent> findByEventType(String eventType);
```

không tự tạo đường truy cập hiệu quả trên bảng `events_by_device_day`. Không nên dùng `ALLOW FILTERING` như lối tắt mặc định: nó có thể kéo theo việc đọc/lọc nhiều dữ liệu, khó dự đoán khi tăng trưởng.

Nếu query theo `event_type` là yêu cầu chính, cân nhắc bảng dành riêng, chẳng hạn `events_by_tenant_type_day` với các thành phần khóa thích hợp. Khi đổi bảng, cần xét fan-out, dữ liệu nhân bản và cập nhật nhiều cách nhìn.

### 10.3. Thay đổi khóa để phục vụ truy vấn mới

Nếu thường xuyên cần “mọi event của một thiết bị trong khoảng thời gian bất kể loại sự kiện”, `occurred_at` nên là clustering column đầu tiên sau partition key. Nếu thường xuyên cần “event theo loại rồi đến thời gian”, `event_type` có thể cần xuất hiện trong partition key hoặc đứng trước `occurred_at` trong clustering key của **một bảng khác**.

Không có một thứ tự clustering tối ưu cho mọi kiểu truy vấn. Đó là lý do Cassandra thường sử dụng nhiều bảng theo **query-driven design**.

## 11. LIMIT, paging và cursor

Ngay cả truy vấn có điều kiện clustering hợp lệ cũng có thể đọc dữ liệu lớn. `List<DeviceEvent>` trả toàn bộ kết quả của một vùng thời gian có thể gây tăng memory và network.

Phân biệt:

- **`LIMIT`:** số hàng tối đa yêu cầu từ câu CQL.
- **Page size của driver:** cách driver lấy kết quả thành các trang khi cần.
- **Paging state:** thông tin để tiếp tục đọc kết quả của một truy vấn tương ứng.
- **OFFSET:** khái niệm thường gặp ở SQL nhưng không phải cách nhảy đến trang sâu hiệu quả của Cassandra.

Ví dụ, một UI lấy 50 event mới nhất trong ngày nên giới hạn tổng kết quả ở 50 hoặc dùng cơ chế phân trang có cursor nếu người dùng cần xem tiếp. Đối với pagination dài:

1. Giữ ổn định partition key và các ranh giới truy vấn giữa các trang.
2. Đảm bảo thứ tự clustering/tie-breaker đủ rõ, ví dụ `occurred_at DESC, event_id ASC`.
3. Không dùng paging state của tenant/device/ngày này cho tenant/device/ngày khác.
4. Xử lý khả năng dữ liệu được ghi mới/xóa giữa các trang; paging không nhất thiết tạo một snapshot bất biến.
5. Đặt giới hạn page size và mức đồng thời theo tài nguyên cụm.

Một method repository nhận `Pageable` hoặc `Slice` (nếu phiên bản hỗ trợ cho kiểu truy vấn đó) vẫn phải tôn trọng những điều kiện CQL trên partition và clustering. Nó không cho phép sắp xếp/lọc tùy ý như repository quan hệ.

## 12. Consistency và partition nóng không biến mất nhờ derived query

Giả sử một thiết bị sinh một triệu event trong ngày, tất cả cùng:

```text
(tenant_id=T1, device_id=D7, event_day=2026-11-25)
```

Đó là **một partition logic**, dù có rất nhiều giá trị `occurred_at` và `event_id`. Truy vấn có equality đầy đủ + range hợp lý vẫn có thể chậm nếu partition quá lớn, workload quá nóng hoặc có nhiều tombstone.

Các yếu tố cần xét:

| Yếu tố | Câu hỏi cần trả lời |
| --- | --- |
| **Partition cardinality** | Có bao nhiêu tổ hợp tenant/device/day thực sự được truy cập? |
| **Partition size** | Một thiết bị phát bao nhiêu sự kiện trong một ngày? Có cần bucket theo giờ? |
| **Hot partition** | Nhiều request có tập trung vào đúng một thiết bị/ngày không? |
| **TTL/tombstone** | Sự kiện có thời hạn lưu giữ, việc xóa có tạo tải đọc/compaction không? |
| **Consistency level** | Mức phản hồi replica nào phù hợp với SLA và replication? |
| **Paging** | Query lấy bao nhiêu hàng, mỗi trang bao nhiêu, có đọc dàn trải nhiều ngày không? |

Tăng consistency level không thay đổi thứ tự clustering. Thay `@Query` thành derived query không tự phân tán một partition nóng. Nếu throughput yêu cầu, có thể xem xét chia bucket nhỏ hơn hoặc shard ổn định, nhưng phải tính lại chi phí truy vấn xuyên bucket/shard.

## 13. Lỗi thường gặp với derived query trên clustering key

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Repository khởi động nhưng query lỗi khi chạy | Method name được parse nhưng CQL không phù hợp khóa hoặc phiên bản module. | Đối chiếu query thực với `PRIMARY KEY`. |
| Query chỉ theo `event_id` không hợp lệ/không tìm được nhanh | Bỏ qua `occurred_at` hoặc partition key. | Thiết kế bảng tra cứu theo event ID hoặc yêu cầu đủ khóa. |
| Có đủ partition key nhưng thêm `event_type` làm WHERE bị lỗi/đắt | `event_type` là regular column. | Thiết kế bảng theo event type hoặc đánh giá index phù hợp. |
| Method `Between` không có ngữ nghĩa mong muốn | Khác biệt hỗ trợ keyword và cách tạo CQL theo phiên bản. | Dùng `@Query` với `>=` và `<`, kiểm tra bằng integration test. |
| Kết quả không có thứ tự như UI mong muốn | Nhầm regular column với clustering hoặc cố `Sort` không hợp lệ. | Đọc `CLUSTERING ORDER BY` và CQL thực. |
| Query trả quá nhiều event | Không có LIMIT/paging, khoảng thời gian quá rộng. | Chặn size/cửa sổ, paging/cursor phù hợp. |
| Chậm trên thiết bị phát sinh nhiều event | Partition lớn/nóng, tombstone, payload nhiều. | Đo kích thước/tải partition, xem lại bucket. |
| Không tìm được sự kiện ở ngày mong đợi | `event_day` tính khác múi giờ, key không khớp. | Chuẩn hóa bucket timezone, kiểm tra giá trị lưu. |
| Ghi dữ liệu mới nhưng trang kết quả thay đổi | Paging trong tập dữ liệu biến động. | Thiết kế cursor và xử lý trùng/bỏ sót theo yêu cầu. |

### Trình tự debug nên làm

1. Mở **schema CQL của bảng mà entity đang map tới**.
2. Tách partition key và liệt kê clustering columns **đúng thứ tự**.
3. Chuyển tên derived query thành các điều kiện CQL mong muốn; đánh dấu cột nào dùng `=`, cột nào dùng `>`/`<`.
4. Kiểm tra đã có đủ partition key chưa, và clustering có đi theo prefix hợp lệ không.
5. Kiểm tra `ORDER BY`, `LIMIT` và cách paging; tránh sort theo regular columns.
6. Kiểm tra mapping `@Table`, `@PrimaryKeyColumn`, tên property và custom conversions.
7. Chạy thử trên Cassandra test instance với dữ liệu đại diện, xác nhận lỗi/số hàng/thứ tự/độ trễ.

Không nên điều chỉnh ngẫu nhiên tên phương thức để “hết lỗi”. Phải bắt đầu từ **truy vấn nghiệp vụ**, rồi thiết kế bảng và ánh xạ method vào đúng CQL được hỗ trợ.

## 14. Kiểm thử các tổ hợp điều kiện clustering

Nên có integration test trên schema thật. Unit test kiểm tra chuỗi tên method hoặc mock repository **không chứng minh** Cassandra chấp nhận điều kiện truy vấn.

### Bộ ca thử gợi ý

| Ca kiểm thử | Dữ liệu thử | Kỳ vọng |
| --- | --- | --- |
| Đọc một partition | Nhiều event cùng device/ngày. | Trả các hàng của đúng partition theo clustering order. |
| Range theo thời gian | Event trước, trong và sau `[09:00, 10:00)`. | Chỉ trả event trong khoảng; loại đúng điểm kết thúc. |
| Equality trên `occurred_at` | Hai event trùng timestamp, khác event ID. | Trả đúng nhóm cùng timestamp. |
| Equality trên toàn khóa | Một event có `occurred_at` và `event_id` cụ thể. | Đọc đúng một hàng mục tiêu nếu tồn tại. |
| Bỏ qua clustering đầu | Chỉ có `event_id` và đủ partition key. | Không tự coi là truy vấn được hỗ trợ/hiệu quả. |
| Bỏ một phần partition key | Thiếu `event_day`. | Không mong query định vị được partition như thiết kế. |
| Thêm filter regular column | Có `event_type` trong dữ liệu. | Nhận diện hạn chế, không giả định parser giúp lọc tùy ý. |
| ORDER BY không hợp lệ | Đòi sort theo `event_type`. | Lỗi/không phù hợp theo schema; không để lộ như tính năng UI hợp lệ. |
| Trang dữ liệu lớn | Hàng nghìn event, paging/cursor. | Trang tiếp tục đúng điều kiện và giới hạn. |
| Cross-day | Sự kiện ở cuối ngày và đầu ngày sau. | Service truy vấn đúng các bucket và merge khi cần. |

### Ví dụ tạo dữ liệu thử

```sql
INSERT INTO events_by_device_day (
    tenant_id, device_id, event_day, occurred_at, event_id, event_type, payload
) VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    '2026-11-25',
    '2026-11-25T09:15:00Z',
    33333333-3333-4333-8333-333333333333,
    'TEMPERATURE',
    '{"celsius":25.5}'
);

INSERT INTO events_by_device_day (
    tenant_id, device_id, event_day, occurred_at, event_id, event_type, payload
) VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    '2026-11-25',
    '2026-11-25T10:15:00Z',
    44444444-4444-4444-8444-444444444444,
    'ALERT',
    '{"message":"High temperature"}'
);
```

Với truy vấn `occurred_at >= 09:00 AND occurred_at < 10:00`, chỉ hàng lúc 09:15 được trả về. Sau đó thêm hàng có timestamp đúng 10:00 để xác nhận ranh giới trên **không bao gồm** sự kiện ấy.

Chạy test cùng với repository method và `@Query` để đảm bảo các lớp Java đang tạo đúng CQL dự định. Nếu bảng có TTL/tombstone trong production, nên thử thêm dữ liệu đã hết hạn và nhiều hàng theo clustering để đánh giá chi phí thực.

## 15. Bài tập vận dụng

**Câu 1.** Bảng có `PRIMARY KEY ((tenant_id, device_id, event_day), occurred_at, event_id)`. API biết đủ partition key và chỉ muốn lọc các event sau 09:00. Điều kiện clustering nào phù hợp?

**Gợi ý:** `occurred_at > '2026-11-25T09:00:00Z'` sau điều kiện bằng trên cả ba thành phần partition key. Đây là range trên clustering column đầu tiên.

**Câu 2.** API biết `tenant_id, device_id, event_day, event_id` nhưng không biết `occurred_at`. Có thể viết `findByTenantIdAndDeviceIdAndEventDayAndEventId(...)` rồi mong Cassandra tìm nhanh không?

**Gợi ý:** Không nên. `event_id` là clustering column thứ hai, trong khi cột thứ nhất `occurred_at` chưa được ràng buộc. Cần đầy đủ khóa hoặc một bảng tra cứu theo event ID.

**Câu 3.** Một phương thức derived query có tên dài và được Spring Data nhận diện. Điều đó đã chứng minh CQL hợp lệ chưa?

**Gợi ý:** Chưa. Cần phân biệt việc parse tên method, hỗ trợ keyword trong module Cassandra và quy tắc khóa khi Cassandra thực thi CQL.

**Câu 4.** Thiết kế thêm `event_type` làm clustering column đầu tiên trước `occurred_at`. Truy vấn “mọi event của thiết bị theo thời gian, bất kể loại” có còn thuận tiện như trước không?

**Gợi ý:** Không mặc định. Muốn lọc khoảng trên `occurred_at` thường cần ràng buộc cột đứng trước là `event_type`; thay đổi thứ tự khóa làm thay đổi mẫu truy vấn được hỗ trợ.

**Câu 5.** UI muốn sắp danh sách sự kiện theo `payload`. Thêm `OrderByPayloadAsc` vào tên method có giúp Cassandra sắp xếp hợp lệ không?

**Gợi ý:** Không. `payload` là regular column và không phải clustering order đã thiết kế. Cần cách nhìn khác hoặc cơ chế tìm kiếm/thống kê phù hợp.

**Câu 6.** Một query có đầy đủ partition key, range trên `occurred_at` và `LIMIT 50` nhưng vẫn chậm ở một thiết bị lớn. Vì sao?

**Gợi ý:** Đúng điều kiện khóa không tự bảo đảm hiệu năng. Có thể có partition lớn/nóng, nhiều tombstone, payload lớn, tải đồng thời hoặc consistency/page size chưa phù hợp. Cần đo và điều chỉnh thiết kế/bucket khi cần.

**Câu 7.** API cần dữ liệu từ 23:50 ngày 25 đến 00:10 ngày 26. Có thể chỉ truyền ngày 25 và range timestamp qua nửa đêm không?

**Gợi ý:** Bảng được partition theo `event_day`, nên query ngày 25 chỉ đọc ngày 25. Phải xác định và truy vấn thêm partition ngày 26, rồi tổng hợp theo thứ tự phù hợp.

## Tổng kết

Trong Spring Data Cassandra, **derived query** chỉ là cách mô tả ý định truy vấn bằng tên phương thức repository; nó không làm Cassandra bỏ qua cấu trúc `PRIMARY KEY`. Với một partition đã được xác định đầy đủ, các điều kiện clustering thông thường nên đi theo **thứ tự khóa đã thiết kế**: equality trên các cột trước, rồi equality hoặc range trên cột tiếp theo. Không thể tùy ý bỏ qua clustering column đứng trước hoặc dùng regular column như một chỉ mục tự động.

Trước khi viết `findBy...`, hãy đọc **partition key, clustering columns và `CLUSTERING ORDER BY`** của bảng. Khi method derivation không rõ ràng hoặc không diễn đạt tốt range, dùng `@Query` với CQL tường minh và bind parameters. Dù dùng repository, `CassandraTemplate` hay CQL trực tiếp, vẫn phải kiểm soát **paging, consistency, kích thước partition, hot partitions và hiệu năng** theo đúng mô hình dữ liệu phân tán.
