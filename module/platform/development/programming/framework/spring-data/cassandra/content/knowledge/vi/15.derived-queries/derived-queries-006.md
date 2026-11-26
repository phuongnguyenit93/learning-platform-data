# Sắp xếp bằng OrderBy hoặc Sort trong giới hạn Cassandra

## 1. Vì sao sắp xếp trong repository Cassandra khác cơ sở dữ liệu quan hệ?

Trong **Spring Data Cassandra**, ta có thể viết phương thức repository theo tên như `findBy...OrderBy...` hoặc truyền đối tượng `Sort` để biểu đạt yêu cầu sắp xếp. Về mặt Java, cách viết khá giống Spring Data JPA. Nhưng **Apache Cassandra không cho phép sắp xếp tùy ý theo mọi cột**: khả năng `ORDER BY` gắn chặt với **partition key**, **clustering columns** và thứ tự đã khai báo trong bảng.

Giả sử giao diện cần hai cách xem lịch sử sự kiện của một tenant:

- Xem **20 sự kiện mới nhất** trong một ngày.
- Xem **20 sự kiện cũ nhất** trong ngày đó.

Nếu bảng được thiết kế theo các truy vấn trên, ứng dụng có thể khai thác thứ tự clustering để trả kết quả mà không phải sắp xếp toàn bộ dữ liệu. Ngược lại, yêu cầu “sắp xếp theo `category` hoặc `payload` trên tất cả tenant” không trở thành truy vấn hợp lệ chỉ vì Java có `Sort.by("category")`.

Đây là bài học thuộc chương **Truy vấn dẫn xuất** của module **SPRING_DATA_CASSANDRA**. Phạm vi là dùng `OrderBy` trong **derived query method** và đối tượng `Sort` theo đúng giới hạn của Cassandra; sau đó kết nối với entity mapping, repository, `CassandraTemplate`, CQL, paging và hiệu năng phân tán.

**Mục tiêu học tập:**

1. Phân biệt **thứ tự clustering của bảng** với `ORDER BY` trong CQL và `Sort` ở Java.
2. Biết vì sao các truy vấn sắp xếp thông thường cần **xác định đầy đủ partition key**.
3. Hiểu **thứ tự khai báo** các clustering columns và quy tắc dùng hướng sắp xếp **như schema hoặc đảo ngược toàn bộ**.
4. Viết derived query `OrderBy` và sử dụng `Sort` có kiểm soát, kèm phương án `@Query` tường minh.
5. Tránh các anti-pattern: sort trên cột thường, sort xuyên partition, đổi tùy ý `ASC/DESC`, lấy hết kết quả rồi sort, `ALLOW FILTERING`.
6. Kiểm chứng câu CQL được sinh ra bằng test tích hợp, xác nhận kết quả rỗng, tie-break, `LIMIT`, paging state và các điều kiện lỗi.

## 2. Schema mẫu quyết định khả năng sắp xếp

Để đọc sự kiện theo tenant và ngày, ta tạo một bảng:

~~~sql
CREATE TABLE events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    category text,
    summary text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

| Cột | Vai trò | Ý nghĩa khi sắp xếp |
| --- | --- | --- |
| `tenant_id` | Thành phần thứ nhất của **partition key tổng hợp** | Giới hạn tập sự kiện của tenant |
| `event_day` | Thành phần thứ hai của partition key | Giới hạn sự kiện trong đúng một ngày |
| `occurred_at` | **Clustering column 1** | Thứ tự mặc định **DESC**: mới nhất trước |
| `event_id` | **Clustering column 2** | Thứ tự mặc định **ASC** giữa các sự kiện trùng thời điểm |
| `category` | Cột thường | **Không** tự cho phép `ORDER BY category` |
| `summary` | Cột thường | **Không** tự cho phép `ORDER BY summary` |

Cassandra tính token từ **toàn bộ** `(tenant_id, event_day)` và phân bố partition lên các replica theo cấu hình keyspace. Bên trong partition, các hàng được sắp theo thứ tự clustering của `(occurred_at, event_id)`. Vì vậy **cùng một tenant ở hai ngày khác nhau có hai partition logic**, và `ORDER BY` theo primary key không tạo thứ tự toàn cục giữa các partition.

~~~mermaid
flowchart TD
    A[Repository: tenantId + eventDay + yêu cầu sort] --> B[Định vị partition từ tenant_id, event_day]
    B --> C[Đọc các row theo clustering key]
    C --> D[occurred_at DESC và event_id ASC]
    D --> E[Giới hạn LIMIT hoặc xử lý paging]
    E --> F[Danh sách sự kiện trả về Java]
~~~

**Chú ý:** thứ tự clustering được khai báo trong **DDL**, không phải do tên phương thức `findBy...OrderBy...` quyết định. Repository chỉ thể hiện cách ứng dụng muốn đọc dữ liệu đã được tổ chức trong Cassandra.

## 3. Quy tắc nền tảng của ORDER BY trong Cassandra

### 3.1. Phải giới hạn partition đúng cách

Với bảng mẫu, truy vấn hợp lý là:

~~~sql
SELECT occurred_at, event_id, category
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
ORDER BY occurred_at DESC, event_id ASC
LIMIT 20;
~~~

Điều kiện `WHERE` cung cấp đủ **hai phần của partition key**. Server có thể duyệt các hàng trong một partition theo clustering order rồi lấy tối đa 20 hàng.

Ngược lại, các câu sau **không có đường đọc primary-key thông thường phù hợp** với bảng này:

~~~sql
-- Sai cho access pattern này: thiếu event_day.
SELECT * FROM events_by_tenant_day
WHERE tenant_id = ?
ORDER BY occurred_at DESC;

-- Sai cho access pattern này: không có partition key.
SELECT * FROM events_by_tenant_day
ORDER BY occurred_at DESC;

-- Sai cho access pattern này: chỉ định ngày nhưng không có tenant_id.
SELECT * FROM events_by_tenant_day
WHERE event_day = ?
ORDER BY occurred_at DESC;
~~~

Không nên thêm `ALLOW FILTERING` để làm các truy vấn trên “chạy được”. Lọc sau khi phải đọc một tập partition rộng **không tương đương** đọc theo khóa đúng và có thể tốn tài nguyên lớn. Một số phiên bản hoặc index có đường truy cập bổ sung, nhưng bài này nói về **truy vấn trực tiếp trên primary key**.

### 3.2. ORDER BY chỉ dựa trên clustering columns

Trong đường truy vấn khóa chuẩn của bảng:

~~~sql
-- Phù hợp: đúng thứ tự clustering đã khai báo.
SELECT event_id, occurred_at
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
ORDER BY occurred_at DESC, event_id ASC;
~~~

Các ví dụ không phù hợp:

~~~sql
-- category là cột thường, không phải clustering.
SELECT * FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
ORDER BY category ASC;

-- Bỏ qua clustering column đứng trước.
SELECT * FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
ORDER BY event_id ASC;
~~~

Cassandra không thực hiện global sort tùy ý như lệnh `ORDER BY arbitrary_column` trong nhiều RDBMS. Dùng `Sort.by("category")` từ Java không tạo ra một chỉ mục hoặc thao tác sắp xếp hợp lệ ở server.

### 3.3. Thứ tự mặc định và hướng đảo ngược toàn bộ

Trong ví dụ, schema có **mixed clustering order**:

~~~sql
WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC)
~~~

Hai thứ tự đầy đủ thường được phép khi truy vấn đúng partition:

| Mong muốn | ORDER BY | Đánh giá |
| --- | --- | --- |
| Mới nhất trước, tie-break ID tăng | `occurred_at DESC, event_id ASC` | **Khớp schema** |
| Cũ nhất trước, tie-break ID giảm | `occurred_at ASC, event_id DESC` | **Đảo ngược toàn bộ schema** |
| Cũ nhất trước, ID vẫn tăng | `occurred_at ASC, event_id ASC` | **Không phải phép đảo toàn bộ hợp lệ** |
| ID giảm, bỏ qua thời gian | `event_id DESC` | **Không theo tiền tố clustering** |
| Sắp theo category | `category ASC` | **Không phải clustering column** |

Các ràng buộc chi tiết về `ORDER BY`, số clustering columns có thể nêu và cú pháp phụ thuộc phiên bản Cassandra; với ví dụ có **hai clustering columns**, nên kiểm chứng câu `ORDER BY` đầy đủ khớp schema hoặc đảo ngược toàn bộ. Không nên để client tùy ý quyết định hướng của từng cột.

Một câu CQL đọc **cũ nhất trước**:

~~~sql
SELECT event_id, occurred_at, category
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
ORDER BY occurred_at ASC, event_id DESC
LIMIT 20;
~~~

### 3.4. Có cần ORDER BY khi chỉ muốn thứ tự mặc định?

Không nhất thiết. Vì bảng đã định nghĩa clustering order, đọc một partition theo truy vấn hợp lệ **không có `ORDER BY` tường minh** sẽ sử dụng thứ tự clustering mặc định của bảng:

~~~sql
SELECT occurred_at, event_id
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
LIMIT 20;
~~~

Đây là lý do quan trọng để **thiết kế thứ tự clustering theo truy vấn thường gặp nhất**. Nếu 95% request cần “sự kiện mới nhất”, đặt `occurred_at DESC` trong DDL khiến cả code và hành vi đọc mặc định đơn giản. `ORDER BY` tường minh vẫn hữu ích khi muốn biểu đạt hợp đồng đọc rõ ràng hoặc cần chiều đảo ngược.

## 4. Truy vấn dẫn xuất hoạt động như thế nào?

**Derived query** của Spring Data là phương thức repository mà framework phân tích tên để tạo truy vấn. Những cụm như `findBy`, `And`, `OrderBy` và `Asc/Desc` biểu diễn điều kiện và thứ tự mong muốn.

Ví dụ:

~~~java
List<EventRow>
findByKeyTenantIdAndKeyEventDayOrderByKeyOccurredAtDesc(
    UUID tenantId, LocalDate eventDay
);
~~~

Tên dài phản ánh đường đi của thuộc tính trong **entity Java**:

- `key.tenantId`: thành phần partition key thứ nhất.
- `key.eventDay`: thành phần partition key thứ hai.
- `key.occurredAt`: clustering column đầu tiên cần sắp xếp `DESC`.

Nhưng cần phân biệt **ba cấp độ hợp lệ**:

1. **Java compile được:** method name là một định danh Java hợp lệ.
2. **Spring Data parse được:** framework tìm đúng property path và xây được truy vấn.
3. **Cassandra chấp nhận và thực thi hiệu quả:** CQL sinh ra thỏa partition key và clustering-order rules.

Chỉ khi cả ba điều kiện cùng đạt, phương thức mới đáp ứng được yêu cầu. Một tên method đẹp **không thay đổi schema Cassandra**.

Trong ví dụ, ta sẽ dùng `@PrimaryKeyClass` để mô tả khóa và minh họa hai cách: **sắp xếp cố định bằng `OrderBy`** và **sắp xếp động bằng `Sort`**. Hỗ trợ chính xác của các query keywords, nested-property path và dynamic sort có thể khác theo phiên bản Spring Data Cassandra; cần test trên đúng bộ Spring Boot/Spring Data/driver của dự án.

## 5. Mapping khóa tổng hợp và entity

Một entity khớp bảng `events_by_tenant_day`:

~~~java
import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class EventKey implements Serializable {
    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "event_day", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(name = "occurred_at", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED)
    private Instant occurredAt;

    @PrimaryKeyColumn(name = "event_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED)
    private UUID eventId;

    protected EventKey() {}

    public EventKey(UUID tenantId, LocalDate eventDay,
                    Instant occurredAt, UUID eventId) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.eventDay = Objects.requireNonNull(eventDay);
        this.occurredAt = Objects.requireNonNull(occurredAt);
        this.eventId = Objects.requireNonNull(eventId);
    }

    public UUID getTenantId() { return tenantId; }
    public LocalDate getEventDay() { return eventDay; }
    public Instant getOccurredAt() { return occurredAt; }
    public UUID getEventId() { return eventId; }

    @Override
    public boolean equals(Object value) {
        if (this == value) return true;
        if (!(value instanceof EventKey)) return false;
        EventKey other = (EventKey) value;
        return Objects.equals(tenantId, other.tenantId)
            && Objects.equals(eventDay, other.eventDay)
            && Objects.equals(occurredAt, other.occurredAt)
            && Objects.equals(eventId, other.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, eventDay, occurredAt, eventId);
    }
}
~~~

Đối tượng khóa cần **giữ nguyên giá trị sau khi gán vào entity**. Ví dụ không cung cấp setter công khai; nếu ứng dụng cần đổi một thành phần primary key, phải tạo khóa mới và quản lý thao tác chuyển/xóa hàng tương ứng, không kỳ vọng Cassandra cập nhật khóa tại chỗ.

Entity:

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_tenant_day")
public class EventRow {
    @PrimaryKey
    private EventKey key;

    @Column("category")
    private String category;

    @Column("summary")
    private String summary;

    protected EventRow() {}

    public EventRow(EventKey key, String category, String summary) {
        this.key = key;
        this.category = category;
        this.summary = summary;
    }

    public EventKey getKey() { return key; }
    public String getCategory() { return category; }
    public String getSummary() { return summary; }
}
~~~

`@PrimaryKeyColumn` mô tả thành phần **partitioned/clustering** và thứ tự `ordinal`. Thứ tự `DESC/ASC` trong CQL phải được kiểm tra ở schema thực tế; một Java method `OrderBy...Desc` không tự sửa `CLUSTERING ORDER BY` của bảng đã được triển khai.

Với kiểu `timestamp`, Java `Instant` có thể mang nano giây nhưng Cassandra lưu đến mili giây. Khi dùng thời gian trong primary key, nên chuẩn hóa tới mili giây trước khi lưu/so sánh để tránh sai khác round-trip.

## 6. OrderBy trong tên phương thức repository

### 6.1. Sắp xếp cố định theo thời gian

Repository minh họa:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface EventRepository
        extends CassandraRepository<EventRow, EventKey> {

    // Minh họa derived query dựa trên property path của khóa tổng hợp.
    List<EventRow> findByKeyTenantIdAndKeyEventDayOrderByKeyOccurredAtDesc(
        UUID tenantId, LocalDate eventDay
    );
}
~~~

Hậu tố `OrderByKeyOccurredAtDesc` có ý định sắp xếp theo `key.occurredAt` giảm dần, sau điều kiện bằng trên `key.tenantId` và `key.eventDay`. Về ý tưởng, CQL phải tương đương:

~~~sql
SELECT *
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
ORDER BY occurred_at DESC;
~~~

**Quan trọng:** method name ở ví dụ là cách biểu đạt **ý định truy vấn dẫn xuất**. Cần xác minh trên phiên bản Spring Data Cassandra đang dùng xem property path lồng `key.*`, từ khóa `OrderBy` và tổ hợp cột clustering được hỗ trợ như mong muốn hay không. Với bảng có clustering order hỗn hợp `DESC/ASC`, cách chắc chắn hơn là **khai báo đầy đủ thứ tự đúng schema bằng `@Query`** như ở phần 8.

Không nên đọc `Desc` là lời yêu cầu Spring Data tải toàn bộ bản ghi rồi gọi `Collections.sort(...)`: repository sinh truy vấn CQL; Cassandra mới là tầng quyết định giới hạn sắp xếp hợp lệ.

### 6.2. Muốn ổn định khi có các sự kiện trùng thời điểm

Nếu chỉ nhìn vào `occurred_at`, hai sự kiện có cùng timestamp vẫn cần một **tie-breaker** để pagination và kết quả được xác định nhất quán. Trong bảng mẫu, `event_id` là clustering column thứ hai. Dạng kỳ vọng cho truy vấn mới nhất:

~~~sql
ORDER BY occurred_at DESC, event_id ASC
~~~

Về tên derived method, có thể biểu diễn ý định:

~~~java
List<EventRow>
findByKeyTenantIdAndKeyEventDayOrderByKeyOccurredAtDescKeyEventIdAsc(
    UUID tenantId, LocalDate eventDay
);
~~~

Phương thức trên cần **kiểm tra khả năng parse property path và CQL phát sinh** trong phiên bản thư viện của dự án. Nếu không được hỗ trợ hoặc CQL phát sinh không khớp schema, dùng phương thức `@Query` tường minh để kiểm soát cả hai clustering columns. Việc có tie-breaker trong schema và khi phân trang quan trọng hơn việc cố dùng cú pháp tên method rất dài.

### 6.3. LIMIT với derived query

Một số thế hệ Spring Data cung cấp từ khóa giới hạn như `Top`/`First`; với Cassandra, việc hỗ trợ và cách chuyển thành `LIMIT` phải được xác minh:

~~~java
// Ví dụ về ý định, không thay thế test tương thích Spring Data Cassandra:
List<EventRow>
findTop20ByKeyTenantIdAndKeyEventDayOrderByKeyOccurredAtDesc(
    UUID tenantId, LocalDate eventDay
);
~~~

Nếu dự án/phiên bản chưa hỗ trợ đúng tổ hợp từ khóa, **không lấy toàn bộ danh sách về rồi `subList(0, 20)`**. Hãy viết `@Query` có `LIMIT 20` hoặc API truy vấn hỗ trợ limit thực sự. Đặt giới hạn trên **Cassandra**, không chỉ giới hạn trong bộ nhớ JVM.

## 7. Dynamic Sort: linh hoạt ở Java nhưng bị giới hạn ở CQL

Spring Data định nghĩa `org.springframework.data.domain.Sort` để mô tả một hay nhiều tiêu chí sắp xếp. Một phương thức repository có thể nhận `Sort` nếu loại repository, query method và phiên bản Spring Data Cassandra hỗ trợ:

~~~java
import org.springframework.data.domain.Sort;

// Trong EventRepository:
List<EventRow> findByKeyTenantIdAndKeyEventDay(
    UUID tenantId, LocalDate eventDay, Sort sort
);
~~~

Caller muốn thứ tự mới nhất trước:

~~~java
Sort newest = Sort.by(
    Sort.Order.desc("key.occurredAt"),
    Sort.Order.asc("key.eventId")
);

List<EventRow> rows =
    repository.findByKeyTenantIdAndKeyEventDay(tenantId, eventDay, newest);
~~~

Tên thuộc tính `key.occurredAt` và `key.eventId` là **đường thuộc tính Java**, không phải tên cột CQL. Framework phải ánh xạ sang `occurred_at` và `event_id`. Đây là ví dụ minh họa; **khả năng kết hợp Sort với nested composite-key property và câu query cụ thể phải được kiểm tra ở phiên bản thư viện đang chạy**.

**Điều quan trọng:** `Sort` **không mang đến khả năng sắp xếp mới cho Cassandra**. Nếu Sort được framework chuyển thành:

~~~sql
ORDER BY category ASC
~~~

thì query vẫn không phù hợp với bảng vì `category` không phải clustering column.

### 7.1. Whitelist sort choices thay vì nhận bất kỳ tên field

Một HTTP API không nên chuyển trực tiếp mọi chuỗi `?sort=...` từ client vào `Sort.by(userField)`. Với bảng mẫu, chỉ cho phép hai ý định:

| Tham số API | Ý định | CQL được phép |
| --- | --- | --- |
| `newest` | Mới nhất trước | `occurred_at DESC, event_id ASC` |
| `oldest` | Cũ nhất trước | `occurred_at ASC, event_id DESC` |
| `category` | Sắp theo loại sự kiện | **Không hỗ trợ trên bảng này** |
| `summary` | Sắp theo mô tả | **Không hỗ trợ trên bảng này** |
| `mixed` | `occurred_at ASC, event_id ASC` | **Không khớp schema hoặc đảo toàn bộ** |

Một cách diễn đạt ý định nghiệp vụ:

~~~java
public enum TimelineOrder {
    NEWEST_FIRST,
    OLDEST_FIRST
}
~~~

Thay vì cung cấp thuộc tính và direction bất kỳ cho client, service nhận `TimelineOrder` và chọn **một trong hai câu CQL đã kiểm chứng**. Nếu dùng `Sort`, chỉ xây dựng nó từ enum đã whitelist, không đọc raw tên property từ JSON hoặc URL để ghép thẳng.

### 7.2. Sort.unsorted() không có nghĩa là ngẫu nhiên

`Sort.unsorted()` chỉ thể hiện client không yêu cầu một mệnh đề sắp xếp bổ sung. Với truy vấn **một partition** và bảng đã khai báo clustering order, Cassandra vẫn đọc theo thứ tự clustering mặc định. Tuy nhiên **đừng áp dụng kết luận này cho query đa partition** rồi hứa sẽ có một thứ tự toàn cục.

### 7.3. Lỗi runtime không phải kết quả danh sách rỗng

Nếu request Sort không phù hợp:

- Spring Data có thể từ chối tạo/phân tích truy vấn theo khả năng của phiên bản.
- Cassandra có thể từ chối CQL với `ORDER BY` không hợp lệ.
- Query bị thiếu partition key hoặc dùng tên field không ánh xạ được có thể gây lỗi riêng.

**Không được bắt mọi exception rồi trả `List.of()`**. Danh sách rỗng có nghĩa **truy vấn thành công nhưng không có hàng**; query không hợp lệ là lỗi lập trình/configuration, cần được phát hiện và sửa.

## 8. Phương án đáng tin cậy: @Query với ORDER BY và LIMIT rõ ràng

Khi truy vấn có thứ tự cố định rất quan trọng, cách đơn giản để đối chiếu với schema là viết CQL tường minh. Repository có thể khai báo:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface EventTimelineRepository
        extends CassandraRepository<EventRow, EventKey> {

    @Query("SELECT * FROM events_by_tenant_day " +
           "WHERE tenant_id = ?0 AND event_day = ?1 " +
           "ORDER BY occurred_at DESC, event_id ASC LIMIT 20")
    List<EventRow> findNewest20(UUID tenantId, LocalDate eventDay);

    @Query("SELECT * FROM events_by_tenant_day " +
           "WHERE tenant_id = ?0 AND event_day = ?1 " +
           "ORDER BY occurred_at ASC, event_id DESC LIMIT 20")
    List<EventRow> findOldest20(UUID tenantId, LocalDate eventDay);
}
~~~

Ở đây:

- Điều kiện `tenant_id = ?0 AND event_day = ?1` cung cấp **đủ partition key**.
- `ORDER BY` có **đúng hai thứ tự hợp lệ** của schema minh họa.
- `LIMIT 20` chạy trên server; mỗi query trả **không quá 20 hàng**.
- `@Query` và tham số `?0`/`?1` cho phép bind giá trị thay vì nối chuỗi từ client.
- Entity phải được mapping đúng table/keyspace. Nếu có nhiều keyspace, cần kiểm soát session/template và có thể dùng `keyspace.table` đầy đủ.

Đây là **phương án bổ sung**, không mâu thuẫn với bài học derived queries: khi độ phức tạp hoặc giới hạn Cassandra khiến tên method khó đọc/khó kiểm chứng, `@Query` giúp biểu đạt **CQL chính xác**. Cũng có thể dùng `CassandraTemplate`/`CqlTemplate` hoặc driver nếu cần thêm execution options.

### 8.1. Service chỉ chọn hai thứ tự đã được phép

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class EventTimelineService {
    private final EventTimelineRepository repository;

    public EventTimelineService(EventTimelineRepository repository) {
        this.repository = repository;
    }

    public List<EventRow> list(
            UUID tenantId, LocalDate day, TimelineOrder order) {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(day, "day");
        Objects.requireNonNull(order, "order");

        if (order == TimelineOrder.NEWEST_FIRST) {
            return repository.findNewest20(tenantId, day);
        }
        return repository.findOldest20(tenantId, day);
    }
}
~~~

Service không tạo `ORDER BY` từ chuỗi tùy ý, không tải tất cả sự kiện rồi sort trong Java, và không dùng `ALLOW FILTERING`. Khi không có sự kiện phù hợp, repository trả danh sách rỗng theo hợp đồng truy vấn nhiều hàng. Các lỗi CQL, kết nối, timeout phải được xử lý riêng ở tầng ứng dụng.

## 9. Sort theo cột thường: cần một bảng cho access pattern khác

Giả sử sản phẩm yêu cầu “liệt kê sự kiện một tenant trong một ngày, **theo mức ưu tiên cao nhất**”. Nếu `priority` chỉ là cột thường của bảng timeline, câu:

~~~sql
-- Không hợp lệ theo clustering order của bảng timeline.
SELECT * FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
ORDER BY priority DESC;
~~~

không được giải quyết bằng `Sort.by(DESC, "priority")`. Thay vào đó, nếu đây là access pattern quan trọng, thiết kế thêm bảng phục vụ nó:

~~~sql
CREATE TABLE events_by_tenant_day_priority (
    tenant_id uuid,
    event_day date,
    priority int,
    occurred_at timestamp,
    event_id uuid,
    category text,
    summary text,
    PRIMARY KEY (
        (tenant_id, event_day),
        priority,
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    priority DESC,
    occurred_at DESC,
    event_id ASC
);
~~~

Lúc này CQL có thể đọc **mức ưu tiên cao trước** trong một partition:

~~~sql
SELECT priority, event_id, occurred_at
FROM events_by_tenant_day_priority
WHERE tenant_id = ? AND event_day = ?
ORDER BY priority DESC, occurred_at DESC, event_id ASC
LIMIT 20;
~~~

**Đánh đổi của việc thêm bảng:**

1. Mỗi sự kiện có thể được **ghi vào hai bảng** phục vụ hai đường đọc khác nhau.
2. Khi `priority` thay đổi, đây là một phần **clustering key** của bảng ưu tiên; cần ghi hàng với khóa mới và loại bỏ hàng cũ, không chỉ `UPDATE SET priority` tại chỗ.
3. Cần quy trình đồng bộ, retry/idempotency và đối soát dữ liệu khi cập nhật nhiều bảng; **không mặc định có giao dịch ACID xuyên partition**.
4. Partition theo ngày vẫn có thể quá lớn/hot nếu một tenant ghi nhiều sự kiện; phải đo khối lượng và cân nhắc bucket.

**Nguyên tắc:** với Cassandra, **đường truy vấn quyết định cấu trúc bảng**, không phải một bảng trung tâm rồi yêu cầu framework tự tối ưu mọi phép sắp xếp.

## 10. Truy vấn nhiều partition có sắp xếp toàn cục không?

Giả sử API muốn “100 sự kiện mới nhất của một tenant **trong 30 ngày**”. Bảng `events_by_tenant_day` được chia partition theo ngày. Sắp xếp clustering chỉ có ý nghĩa **bên trong mỗi partition**.

Ngay cả khi ứng dụng đọc 30 partition (bằng nhiều query hoặc một cú pháp `IN` được hỗ trợ trong trường hợp cụ thể), đừng mặc định Cassandra cung cấp **global ORDER BY** với đúng semantics, giới hạn và hiệu năng như RDBMS:

- Query từng ngày trả một luồng đã có thứ tự nội bộ, không tự gộp thành một timeline duy nhất.
- Phải kiểm soát fan-out, tải coordinator, timeout và số ngày được phép truy vấn.
- Nếu ứng dụng gộp dữ liệu, cần một thuật toán merge có giới hạn và tie-break rõ ràng.
- Với access pattern liên ngày thường xuyên, cân nhắc thêm một bảng **bucket theo khoảng phù hợp** để hạn chế số partition phải đọc.
- Điều kiện `IN` và `ORDER BY` có những giới hạn riêng theo phiên bản Cassandra; không xem `IN` là lối tắt để sort trên toàn cluster.

**Không nên** nhận một `Sort` từ controller và hy vọng Spring Data “sort sau” một cách an toàn. Nếu sắp xếp ở Java, phải **chủ động lấy tập ứng viên hữu hạn** và chấp nhận rằng sắp xếp một trang dữ liệu đã tải về không bảo đảm chọn được **top N toàn cục** trong toàn bộ dataset.

## 11. ORDER BY kết hợp điều kiện clustering range

Khi cần chỉ xem những sự kiện trong một giờ, điều kiện hợp lệ vẫn phải có **đủ partition key** và khoảng ở **clustering column đầu tiên**:

~~~sql
SELECT event_id, occurred_at, category
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
  AND occurred_at >= ?
  AND occurred_at < ?
ORDER BY occurred_at DESC, event_id ASC
LIMIT 20;
~~~

Ở đây `occurred_at` là clustering column đầu tiên, nên Cassandra có thể duyệt một khoảng trong một partition theo thứ tự khóa. Hai đầu mút thường nên theo quy tắc **nửa mở** `[fromInclusive, toExclusive)` để ghép các khoảng liên tiếp không trùng ranh giới.

~~~java
Instant fromInclusive = Instant.parse("2026-11-25T09:00:00Z");
Instant toExclusive = Instant.parse("2026-11-25T10:00:00Z");
~~~

CQL `timestamp` có độ chính xác **mili giây**; cần thống nhất việc chuẩn hóa `Instant` trước khi ghi và so sánh. `event_day` cũng phải được tính theo một quy ước ngày/timezone nhất quán giữa lúc ghi và lúc đọc.

**Lưu ý về clustering prefix:** nếu đã dùng range trên `occurred_at`, không được tự suy ra rằng có thể kết hợp tùy ý điều kiện equality trên `event_id` hoặc `ORDER BY event_id` độc lập. Những hạn chế của điều kiện `WHERE` và `ORDER BY` là hai khía cạnh liên quan của cùng cấu trúc khóa.

## 12. LIMIT, Sort và paging không phải một khái niệm

### 12.1. Giới hạn số hàng để tránh tải không kiểm soát

Một repository method trả `List<EventRow>` có thể materialize toàn bộ các hàng được query. Với partition nhiều sự kiện, việc đọc danh sách không có giới hạn gây tốn mạng, heap và CPU mapper.

Trong ví dụ, `LIMIT 20` đảm bảo query chỉ trả tối đa 20 hàng. Nhưng nếu người dùng cần xem các trang tiếp theo, không thể giữ `LIMIT 20` và tự tưởng tượng Java đã có một tập kết quả lớn đang được giữ chờ.

| Cơ chế | Ý nghĩa | Có tự cho biết trang tiếp không? |
| --- | --- | --- |
| `ORDER BY` | Thứ tự các hàng được duyệt trong một partition | **Không** |
| `LIMIT 20` | Tối đa 20 hàng của **toàn truy vấn** | **Không** |
| `Sort` | Yêu cầu sắp xếp do tầng Spring Data biểu đạt | **Không**, vẫn bị giới hạn bởi CQL |
| `Page size` của driver | Số hàng được fetch theo từng đợt | Có thể phối hợp với paging state |
| `Paging state` | Trạng thái tiếp tục truy vấn | **Có**, khi API và ngữ cảnh cho phép |

### 12.2. Không dùng tư duy OFFSET như SQL quan hệ

Cassandra không hỗ trợ kiểu phân trang ngẫu nhiên với `OFFSET n` theo cách quen thuộc trong RDBMS. Driver dùng **paging state**. Token tiếp tục cần gắn với cùng query shape, bind values, sort order và bối cảnh dữ liệu phù hợp; không dùng token của `newest` cho request `oldest`.

`Page<T>` có total count có thể đòi hỏi thao tác đếm tốn kém. Với danh sách lớn, `Slice<T>` hoặc cursor theo paging state (nếu API phiên bản Spring Data hỗ trợ) thường phù hợp hơn. Nếu muốn một trang tiếp theo theo khóa cuối cùng (keyset pagination), phải xử lý **cả `occurred_at` và `event_id`**, cùng thứ tự hỗn hợp trong DDL; dùng đơn thuần `occurred_at < lastTimestamp` có thể bỏ sót sự kiện trùng timestamp.

**Không được đảo sort direction khi đang tiếp tục một paging state cũ.** Đó là một truy vấn khác, có trạng thái tiếp tục khác.

### 12.3. Danh sách rỗng khác lỗi Cassandra

Một ngày chưa có sự kiện → repository có thể trả `List.of()` hoặc một collection rỗng. Đây là kết quả hợp lệ. Ngược lại, request `Sort.by("category")` dẫn tới câu `ORDER BY` không hợp lệ hoặc một lần đọc bị `ReadTimeout` phải được phân loại thành lỗi, **không bắt exception rồi trả `[]`**.

## 13. Consistency, concurrent writes và độ ổn định của thứ tự

Trong Cassandra, **thứ tự clustering** giúp đọc kết quả có thứ tự trong một partition theo dữ liệu quan sát được, nhưng **không cung cấp snapshot bất biến** của mọi thao tác trong quá trình người dùng đọc nhiều trang.

Ví dụ người dùng đọc 20 sự kiện mới nhất, ngay sau đó hệ thống ghi thêm một sự kiện có timestamp gần nhất:

- Lượt đọc sau có thể trả một tập sự kiện khác do dữ liệu mới được thêm.
- Khi dùng paging qua nhiều request, các mutation concurrent có thể thay đổi tập dữ liệu quan sát; cần thiết kế kỳ vọng UI (refresh, deduplication theo ID, eventual consistency).
- Với một truy vấn lấy top N, **tie-breaker `event_id`** giúp xác định thứ tự giữa những sự kiện cùng `occurred_at`, nhưng không ngăn dữ liệu thay đổi.
- Consistency level như `LOCAL_QUORUM` xác định số replica phản hồi theo keyspace/topology, **không tạo ORDER BY tùy ý** và không làm một bảng sai partition key trở nên tối ưu.

Mỗi lần truy vấn vẫn có thể gặp timeout, unavailable hoặc lỗi schema. Việc chọn `Sort` hoặc `OrderBy` chỉ điều khiển thứ tự CQL được yêu cầu, không quyết định chính sách retry/idempotency.

## 14. Kiểm thử đúng cú pháp lẫn semantics trên Cassandra

### 14.1. Bộ dữ liệu để kiểm tra

Tạo bảng như phần 2 trong một keyspace thử nghiệm có replication phù hợp. Ghi dữ liệu cho:

- Tenant **A**, ngày **2026-11-25**: 25 sự kiện, có ít nhất hai sự kiện cùng `occurred_at` nhưng khác `event_id`.
- Tenant **A**, ngày **2026-11-24**: một số sự kiện.
- Tenant **B**, ngày **2026-11-25**: một số sự kiện khác.

Sử dụng `UUID` và `Instant` với giá trị cố định/chuẩn hóa mili giây để kiểm thử có thể lặp lại, thay vì phụ thuộc hoàn toàn vào thời gian hệ thống.

### 14.2. Các trường hợp test thiết yếu

| Kiểm tra | Hành động | Kỳ vọng |
| --- | --- | --- |
| Mặc định | Query đủ tenant/ngày, không `ORDER BY` | Thứ tự tương ứng clustering `DESC/ASC` |
| OrderBy | Gọi derived method `OrderBy...Desc` | Parser/CQL hỗ trợ; kết quả đúng thứ tự |
| Tie-break | Hai sự kiện cùng timestamp, khác ID | Thứ tự theo `event_id` của schema |
| Sort đúng | Truyền Sort mới nhất/cũ nhất đã whitelist | CQL hợp lệ và thứ tự đúng |
| Sort sai | Yêu cầu sort theo `category` | Bị từ chối hoặc validation ở service; không coi là danh sách rỗng |
| Thứ tự trộn sai | `occurred_at ASC, event_id ASC` | Không phải hướng đảo toàn bộ của schema |
| Thiếu partition | Chỉ cung cấp tenant | Không có truy vấn ORDER BY hiệu quả theo bảng này |
| LIMIT | 25 hàng nhưng query `LIMIT 20` | Không quá 20 hàng, đúng thứ tự |
| Rỗng | Tenant/ngày hợp lệ chưa có row | Collection rỗng, không phải timeout |
| Reverse | CQL `ASC/DESC` đảo hoàn toàn | Cũ nhất trước và tie-break đúng |
| Paging | Tiếp tục query đúng sort/bind values | Không tái sử dụng state cho sort/partition khác |
| Thêm row đồng thời | Ghi sự kiện khi đang đọc trang | Quan sát hành vi thay đổi và chiến lược ứng dụng |

### 14.3. Test tích hợp cho phương thức CQL tường minh

Ví dụ JUnit 5 rút gọn; `repository` được inject từ Spring context, bảng/keyspace đã tạo và test tự chuẩn bị fixture:

~~~java
@Test
void newestAndOldestUseOppositeClusteringOrders() {
    List<EventRow> newest = repository.findNewest20(tenantId, day);
    List<EventRow> oldest = repository.findOldest20(tenantId, day);

    assertFalse(newest.isEmpty());
    assertFalse(oldest.isEmpty());
    assertTrue(newest.size() <= 20);
    assertTrue(oldest.size() <= 20);

    Instant latestOfOldestQuery = oldest.get(oldest.size() - 1)
        .getKey().getOccurredAt();
    assertFalse(newest.get(0).getKey().getOccurredAt()
        .isBefore(latestOfOldestQuery));
}
~~~

Đoạn test minh họa logic, cần import `List`/`Instant`, JUnit, khai báo `repository`/`tenantId`/`day` và dữ liệu fixture. **Để test thứ tự thật sự**, nên duyệt **toàn bộ các cặp phần tử liên tiếp**, và kiểm tra thứ tự tie-break khi timestamp bằng nhau. Chỉ test phần tử đầu/cuối như ví dụ **chưa đủ** để chứng minh toàn bộ danh sách đã sort đúng.

### 14.4. Kiểm chứng CQL sinh ra thay vì chỉ nhìn tên method

Với derived method hoặc `Sort`, cần kiểm tra:

1. Spring có phân tích đúng `key.tenantId`, `key.eventDay`, `key.occurredAt` và `key.eventId` hay không.
2. Query có ràng buộc **đầy đủ partition key** bằng điều kiện phù hợp không.
3. Các trường `ORDER BY` có ánh xạ thành **tên cột CQL đúng** không.
4. Hướng sort có khớp **schema hoặc phép đảo toàn bộ** không.
5. Đã thực sự có `LIMIT`/paging tại **server**, hay client chỉ giới hạn sau khi tải kết quả.
6. Khi trả danh sách rỗng, có thật là query thành công và không có row, hay lỗi bị nuốt.

Một unit test với mock repository chỉ chứng minh logic service gọi đúng method; nó **không chứng minh CQL được Cassandra chấp nhận**. Do đó phải có test tích hợp, ít nhất cho những sort choices mà API cho phép.

## 15. Bài thực hành: từ tên method đến truy vấn hợp lệ

**Đề bài:** triển khai API `GET /tenants/{tenantId}/events?day=2026-11-25&order=newest`, có hai giá trị `newest` và `oldest`.

**Các bước:**

1. Tạo bảng `events_by_tenant_day` với `PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)` và `CLUSTERING ORDER BY (occurred_at DESC, event_id ASC)`.
2. Ánh xạ `EventKey` và `EventRow`; kiểm tra tên cột và thứ tự khóa.
3. Viết derived repository method với `OrderByKeyOccurredAtDesc`; chạy test để xác minh parser và CQL phát sinh.
4. Thử method có đầy đủ hai sort columns. Nếu framework/phiên bản không hỗ trợ đúng tổ hợp, chuyển sang `@Query` với `ORDER BY` rõ ràng.
5. Viết lựa chọn dynamic `Sort` cho `newest`/`oldest` nhưng **chỉ** cho hai kiểu sắp xếp hợp lệ.
6. Viết `EventTimelineRepository` với hai phương thức `@Query` có `LIMIT 20` để có phương án minh bạch, không phụ thuộc một cú pháp tên method quá dài.
7. Trong service, map tham số API sang enum `TimelineOrder`; từ chối `order=category` thay vì truyền raw tên field vào repository.
8. Test 25 sự kiện trong cùng partition; xác minh query trả 20 hàng đúng thứ tự. Ghi thêm một ngày/tenant khác để kiểm tra phạm vi partition.
9. Thử câu `ORDER BY category ASC` và `ORDER BY occurred_at ASC, event_id ASC` trong CQL lab để hiểu giới hạn.
10. Xác định hợp đồng phân trang sau 20 hàng; phân biệt **`LIMIT`, page size và paging state**, không dựa vào `OFFSET`.
11. Ghi lại ảnh hưởng của một sự kiện mới được chèn khi người dùng đang đọc trang và cách API xử lý refresh/deduplication.

**Tiêu chí hoàn thành:** người học giải thích được rằng `OrderBy`/`Sort` chỉ là **cách khai báo ý định ở Java**. Hiệu lực thực sự xuất phát từ schema Cassandra, partition key đầy đủ, clustering order hợp lệ và việc giới hạn/paging dữ liệu có kiểm soát.

## 16. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Spring Data có Sort nên Cassandra sort được mọi field.” | Sort phải chuyển thành CQL hợp lệ; Cassandra không ORDER BY cột tùy ý |
| “OrderBy...Desc sẽ tự đổi CLUSTERING ORDER BY của bảng.” | DDL quyết định clustering order; method chỉ yêu cầu cách đọc |
| “Chỉ biết tenant_id đủ để sort trên composite partition key.” | Cần ràng buộc event_day hoặc đổi access pattern |
| “Có thể đổi ASC/DESC độc lập trên từng cột clustering.” | Với mixed order, tuân thủ schema hoặc phép đảo ngược toàn bộ |
| “ORDER BY event_id là hợp lệ vì event_id cũng là clustering.” | Thứ tự clustering là một **dãy có tiền tố**, không phải các index độc lập |
| “Sort rỗng nghĩa là kết quả không có thứ tự.” | Trong một partition, mặc định vẫn theo clustering order |
| “LIMIT 20 nghĩa là Java giữ sẵn trang thứ hai.” | LIMIT giới hạn tổng kết quả của query, paging là cơ chế khác |
| “Lấy toàn bộ list rồi sort trong Java cũng như sort ở Cassandra.” | Có thể tải khổng lồ và trả sai top N toàn cục |
| “ALLOW FILTERING cho phép ORDER BY tùy ý.” | Filtering không bổ sung clustering order hay biến scan thành truy vấn tốt |
| “ORDER BY trong một partition cũng sắp xếp tất cả partition.” | Không có global sort tùy ý khi đọc phân tán |
| “Mock test thành công nghĩa là query OrderBy hợp lệ.” | Phải test tích hợp với CQL/schema thực tế |
| “Sort là một cách đảm bảo consistency.” | Thứ tự đọc và mức nhất quán replica là hai khái niệm riêng |

## 17. Câu hỏi tự kiểm tra

1. Vì sao derived method `OrderBy` vẫn có thể thất bại khi chạy trên Cassandra dù compile được?
2. Với `PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)`, cần ràng buộc những cột nào để sắp xếp một partition?
3. `CLUSTERING ORDER BY (occurred_at DESC, event_id ASC)` có ý nghĩa gì khi truy vấn không nêu `ORDER BY`?
4. Hai thứ tự đầy đủ hợp lệ khi đọc theo clustering schema mẫu là gì?
5. Vì sao `ORDER BY occurred_at ASC, event_id ASC` không phải phép đảo toàn bộ?
6. Tại sao `Sort.by("category")` không tự tạo truy vấn sắp xếp hợp lệ?
7. Khác biệt giữa `OrderBy` trong tên method và tham số động `Sort` là gì?
8. Khi lớp khóa tổng hợp là `key`, vì sao derived query có thể cần property path như `KeyTenantId` hoặc `key.occurredAt`?
9. `@Query` tường minh có lợi thế gì khi derived query hoặc Sort phức tạp?
10. Vì sao cần tie-breaker `event_id` nếu nhiều sự kiện có cùng `occurred_at`?
11. Dùng `LIMIT 20` và paging state khác nhau ở đâu?
12. Có thể tái sử dụng paging token giữa `newest` và `oldest` không?
13. Tại sao sắp xếp danh sách sau khi tải một page có thể không trả đúng top N của toàn bộ dữ liệu?
14. Nếu sản phẩm bắt buộc sort theo `priority`, schema và chi phí cập nhật cần thay đổi thế nào?
15. Một kết quả sắp xếp đúng theo clustering có đồng nghĩa người dùng thấy snapshot bất biến khi đang có ghi mới không?
16. Vì sao unit test mock chưa đủ để chứng minh CQL `ORDER BY` hợp lệ và hiệu quả?

**Ghi nhớ:** **`OrderBy` và `Sort` trong Spring Data Cassandra là các cách mô tả thứ tự mong muốn; Cassandra chỉ thực hiện được những thứ tự phù hợp partition key và clustering order của bảng**. Hãy thiết kế bảng theo đường truy vấn, whitelist các lựa chọn sort, dùng `LIMIT`/paging có chủ đích, và kiểm chứng CQL bằng test tích hợp. Đó là cách kết hợp sự tiện lợi của repository với giới hạn thực tế của mô hình dữ liệu phân tán.
